import logging
import threading
import time
import traceback
import psycopg2
import logformat

from finalizationrequest import FinalizationRequest


class DBManager(threading.Thread):
    caught_up: bool = False
    last_block_id: int
    starting_point: int
    logger: logging.Logger

    def __init__(self, proofchain_address, schema, user, password, database, host, starting_point):
        super().__init__()
        self.host = host
        self.database = database
        self.password = password
        self.user = user
        self.schema = schema
        self.last_block_id = None

        self.logger = logformat.get_logger("DB")
        self.starting_point = starting_point

    def _process_outputs(self, outputs):
        fl = 0
        c = 0
        prev_last_block_id = self.last_block_id
        for output in outputs:
            block_id = output[1]
            blockHeight = output[4]
            chainId = output[3]
            deadline = output[5]
            finalizationHash = output[6]
            fr = FinalizationRequest(chainId=chainId, blockHeight=blockHeight, deadline=deadline, block_id=block_id)

            if finalizationHash is None:
                if not fr.waiting_for_confirm() and not fr.waiting_for_finalize():
                    if fr.finalize_later():
                        fl += 1
            else:
                if fr.waiting_for_confirm():
                    if fr.confirm_request():
                        self._update_cursor(fr.session_started_block_id)
                        c += 1
        if fl > 0:
            self.logger.info(f"Queued {fl} proof-sessions for finalization")
        if c > 0:
            self.logger.info(f"Confirmed {c} proof-sessions")
        if self.last_block_id > prev_last_block_id:
            self.logger.info(f"Updated cursor position block_id={self.last_block_id}")

        return fl + c

    def __connect(self):
        return psycopg2.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self.password
        )

    PROOF_CHAIN_VIEW_SQL = r"""
    WITH
    session_started_events AS (
      SELECT session_started.tx_hash AS observer_chain_tx_hash,
        session_started.block_id AS observer_chain_block_id,
        session_started.tx_offset AS observer_chain_tx_offset,
        session_started.topics[2]::numeric AS origin_chain_id,
        session_started.topics[3]::numeric AS origin_chain_block_height,
        abi_field(session_started.data, 0)::numeric AS proof_session_deadline
      FROM {schema_name}.block_log_events session_started
      JOIN {schema_name}.block_transactions trx
        ON (trx.block_id = session_started.block_id AND trx.tx_offset = session_started.tx_offset)
      WHERE
        session_started.block_id > {last_block_id}
        AND session_started.sender = '\x{contract_address}'::bytea
        AND session_started.topics @> ARRAY[
          '\x8b1f889addbfa41db5227bae3b091bd5c8b9a9122f874dfe54ba2f75aabe1f4c'::bytea
        ]
        AND trx.successful = TRUE
      ORDER BY session_started.block_id ASC, session_started.log_offset ASC
    ),
    block_specimen_reward_awarded_events AS (
      SELECT
        fin.tx_hash AS observer_chain_tx_hash,
        fin.topics[2]::numeric AS origin_chain_id,
        fin.topics[3]::numeric AS origin_chain_block_height
      FROM {schema_name}.block_log_events fin
      JOIN {schema_name}.block_transactions trx_1
        ON (trx_1.block_id = fin.block_id AND trx_1.tx_offset = fin.tx_offset)
      WHERE
        fin.block_id > {last_block_id}
        AND fin.sender = '\x{contract_address}'::bytea
        AND fin.topics @> ARRAY['\xf05ac779af1ec75a7b2fbe9415b33a67c00294a121786f7ce2eb3f92e4a6424a'::bytea]
        AND trx_1.successful = TRUE
      ORDER BY fin.block_id ASC, fin.log_offset ASC
    ),
    quorum_not_reached_events AS (
      SELECT
        fin.tx_hash AS observer_chain_tx_hash,
        fin.topics[2]::numeric AS origin_chain_id,
        public.abi_field(fin.data, 0)::numeric AS origin_chain_block_height
      FROM {schema_name}.block_log_events fin
      JOIN {schema_name}.block_transactions trx_1
        ON (trx_1.block_id = fin.block_id AND trx_1.tx_offset = fin.tx_offset)
      WHERE
        fin.block_id > {last_block_id}
        AND fin.sender = '\x{contract_address}'::bytea
        AND fin.topics @> ARRAY['\x398fd8f638a7242217f011fd0720a06747f7a85b7d28d7276684b841baea4021'::bytea]
        AND trx_1.successful = TRUE
      ORDER BY fin.block_id ASC, fin.log_offset ASC
    ),
    all_finalization_events AS (
      SELECT * FROM block_specimen_reward_awarded_events
      UNION ALL
      SELECT * FROM quorum_not_reached_events
    )
    SELECT
      sse.observer_chain_tx_hash AS observer_chain_session_start_tx_hash,
      sse.observer_chain_block_id AS observer_chain_session_start_block_id,
      sse.observer_chain_tx_offset AS observer_chain_session_start_tx_offset,
      sse.origin_chain_id,
      sse.origin_chain_block_height,
      sse.proof_session_deadline,
      afe.observer_chain_tx_hash AS observer_chain_finalization_tx_hash
    FROM session_started_events sse
    LEFT JOIN all_finalization_events afe ON (
      sse.origin_chain_id = afe.origin_chain_id
      AND sse.origin_chain_block_height = afe.origin_chain_block_height
    )
    {finalization_filter_part}
    ORDER BY sse.observer_chain_block_id ASC, sse.observer_chain_tx_offset ASC
    ;

    """

    def __main_loop(self):
        try:
            self.logger.info('Connecting to the database...')
            if not self.caught_up:
                self.logger.info(f"Initial scan block_id={self.last_block_id}")

                with self.__connect() as conn:
                    with conn.cursor() as cur:
                        sql = PROOF_CHAIN_VIEW_SQL.format(
                            schema_name = self.schema,
                            contract_address = self.proofchain_address,
                            last_block_id = self.last_block_id,
                            finalization_filter_part = r"WHERE afe.observer_chain_tx_hash IS NULL"
                        )
                        # we are catching up. So we only need to grab what we need to attempt for finalizing
                        cur.execute(sql)
                        outputs = cur.fetchall()

                self.logger.info(f"Processing {len(outputs)} proof-session records...")
                self._process_outputs(outputs)

                self.caught_up = True
                self.logger.info(f"Caught up with db block_id={self.last_block_id}")

            while True:
                with self.__connect() as conn:
                    with conn.cursor() as cur:
                        self.logger.info(f"Incremental scan block_id={self.last_block_id}")
                        # we need everything after last max block number
                        sql = PROOF_CHAIN_VIEW_SQL.format(
                            schema_name = self.schema,
                            contract_address = self.proofchain_address,
                            last_block_id = self.last_block_id
                        )
                        cur.execute(sql)
                        outputs = cur.fetchall()

                if self._process_outputs(outputs) == 0:
                    self.logger.info("No new proof-session records discovered")

                time.sleep(40)

        except (Exception, psycopg2.DatabaseError) as ex:
            self.logger.critical(''.join(traceback.format_exception(ex)))

    def run(self):
        # we need to avoid recursion in order to avoid stack depth exceeded exception
        if self.starting_point != -1:
            self.last_block_id = self.starting_point
        else:
            self.__fetch_last_block()
        while True:
            try:
                self.__main_loop()
                time.sleep(60)
            except (Exception, psycopg2.DatabaseError) as ex:
                self.logger.warning(''.join(traceback.format_exception(ex)))
                # this should never happen
                self.__main_loop()

    def __fetch_last_block(self):
        try:
            self.logger.info("Determining initial cursor position...")
            with self.__connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(r'SELECT observer_chain_session_start_block_id FROM reports.proof_chain_moonbeam WHERE observer_chain_finalization_tx_hash IS NULL LIMIT 1')
                    block_id = cur.fetchone()
            if block_id is not None:
                self.last_block_id = block_id[0] - 1
            else:
                self.last_block_id = 1
        except Exception as ex:
            self.logger.warning(''.join(traceback.format_exception(ex)))

    def _update_cursor(self, block_id):
        for fr in FinalizationRequest.get_requests_to_be_confirmed():
            if fr.session_started_block_id < block_id:
                return
        for fr in FinalizationRequest.get_requests_to_be_finalized():
            if fr.session_started_block_id < block_id:
                return
        self.last_block_id = block_id
