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

    def __init__(self, user, password, database, host, starting_point, chain_table):
        super().__init__()
        self.host = host
        self.database = database
        self.password = password
        self.user = user
        self.last_block_id = None
        self.chain_table = chain_table

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
            fr = FinalizationRequest(
                chainId=chainId,
                blockHeight=blockHeight,
                deadline=deadline,
                block_id=block_id,
            )

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
            password=self.password,
        )

    def __main_loop(self):
        try:
            self.logger.info("Connecting to the database...")
            if not self.caught_up:
                self.logger.info(f"Initial scan block_id={self.last_block_id}")

                with self.__connect() as conn:
                    with conn.cursor() as cur:
                        # we are catching up. So we only need to grab what we need to attempt for finalizing
                        if self.chain_table == "chain_moonbeam_moonbase_alpha":
                            cur.execute(
                                r'SELECT * FROM chain_moonbeam_moonbase_alpha."_proof_chain_events" WHERE observer_chain_session_start_block_id > %s AND observer_chain_finalization_tx_hash IS NULL AND origin_chain_block_height > 16864740;',
                                (self.last_block_id,),
                            )
                        else:
                            cur.execute(
                                r'SELECT * FROM chain_moonbeam_mainnet."_proof_chain_events" WHERE observer_chain_session_start_block_id > %s AND observer_chain_finalization_tx_hash IS NULL;',
                                (self.last_block_id,),
                            )
                        outputs = cur.fetchall()

                self.logger.info(f"Processing {len(outputs)} proof-session records...")
                self._process_outputs(outputs)

                self.caught_up = True
                self.logger.info(f"Caught up with db block_id={self.last_block_id}")

            while True:
                with self.__connect() as conn:
                    with conn.cursor() as cur:
                        self.logger.info(
                            f"Incremental scan block_id={self.last_block_id}"
                        )
                        # we need everything after last max block number
                        if self.chain_table == "chain_moonbeam_moonbase_alpha":
                            cur.execute(
                                r'SELECT * FROM chain_moonbeam_moonbase_alpha."_proof_chain_events" WHERE observer_chain_session_start_block_id > %s AND origin_chain_block_height > 16864740;',
                                (self.last_block_id,),
                            )
                        else:
                            cur.execute(
                                r'SELECT * FROM chain_moonbeam_mainnet."_proof_chain_events"  WHERE observer_chain_session_start_block_id > %s;',
                                (self.last_block_id,),
                            )

                        outputs = cur.fetchall()

                if self._process_outputs(outputs) == 0:
                    self.logger.info("No new proof-session records discovered")

                time.sleep(40)

        except (Exception, psycopg2.DatabaseError) as ex:
            self.logger.critical("".join(traceback.format_exception(ex)))

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
                self.logger.warning("".join(traceback.format_exception(ex)))
                # this should never happen
                self.__main_loop()

    def __fetch_last_block(self):
        try:
            self.logger.info("Determining initial cursor position...")
            with self.__connect() as conn:
                with conn.cursor() as cur:
                    if self.chain_table == "chain_moonbeam_moonbase_alpha":
                        cur.execute(
                            r'SELECT observer_chain_session_start_block_id FROM chain_moonbeam_moonbase_alpha."_proof_chain_events" WHERE observer_chain_finalization_tx_hash IS NULL LIMIT 1'
                        )
                    else:
                        cur.execute(
                                r'SELECT observer_chain_session_start_block_id FROM chain_moonbeam_mainnet."_proof_chain_events" WHERE observer_chain_finalization_tx_hash IS NULL LIMIT 1'
                        )
                    block_id = cur.fetchone()
            if block_id is not None:
                self.last_block_id = block_id[0] - 1
            else:
                self.last_block_id = 1
        except Exception as ex:
            self.logger.warning("".join(traceback.format_exception(ex)))

    def _update_cursor(self, block_id):
        for fr in FinalizationRequest.get_requests_to_be_confirmed():
            if fr.session_started_block_id < block_id:
                return
        for fr in FinalizationRequest.get_requests_to_be_finalized():
            if fr.session_started_block_id < block_id:
                return
        self.last_block_id = block_id
