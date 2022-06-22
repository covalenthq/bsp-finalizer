import logging
import threading
import time
import traceback
import logformat

import psycopg2

from finalizationrequest import FinalizationRequest


class DBManager(threading.Thread):
    caught_up: bool = False
    last_block_id: int
    starting_point: int
    logger: logging.Logger

    def __init__(self, user, password, database, host, starting_point):
        super().__init__()
        self.host = host
        self.database = database
        self.password = password
        self.user = user
        self.last_block_id = None

        self.logger = logformat.LogFormat.init_logger("DB")
        self.starting_point = starting_point

    def _process_outputs(self, outputs):
        fl = 0
        c = 0
        for output in outputs:
            block_id = output[1]
            blockHeight = output[4]
            chainId = output[3]
            deadline = output[5]
            finalizationHash = output[6]
            fr = FinalizationRequest(chainId=chainId, blockHeight=blockHeight, deadline=deadline, block_id=block_id)

            if finalizationHash is None:
                if not fr.waiting_for_confirm() and not fr.waiting_for_finalize():
                    fr.finalize_later()
                    fl += 1
            else:
                if fr.waiting_for_confirm():
                    fr.confirm_request()
                    self.__update_cursor(fr.session_started_block_id)
                    c += 1
        if fl > 0:
            self.logger.info("{} entries were added for finalizing.".format(fl))
        if c > 0:
            self.logger.info("{} entries were confirmed.".format(c))

    def __connect(self):
        return psycopg2.connect(
            host=self.host,
            database=self.database,
            user=self.user,
            password=self.password
        )

    def __main_loop(self):
        conn = None
        try:
            self.logger.info('Connecting to the database...')
            conn = self.__connect()
            cur = conn.cursor()
            if not self.caught_up:
                self.logger.info("Started catching up with db.")
                # we are catching up. So we only need to grab what we need to attempt for finalizing
                cur.execute(
                    'select * from reports.proof_chain_moonbeam where finalization_hash IS NULL and block_id >= %s ORDER BY block_id;',
                            (self.last_block_id,))
                self.logger.info("Processing {} records from db.".format(cur.rowcount))

                while True:
                    outputs = cur.fetchmany(10_000)
                    if len(outputs) == 0 or outputs[0] == None:
                        break
                    self._process_outputs(outputs)

                self.caught_up = True

            self.logger.info("Caught up with db.")

            while True:
                self.logger.info("attempting to get more data from {}".format(self.last_block_id))
                # we need everything after last max block number
                cur.execute(
                    'select * from reports.proof_chain_moonbeam where block_id >= %s ORDER BY block_id;',
                            (self.last_block_id,))
                outputs = cur.fetchall()
                self._process_outputs(outputs)
                conn.close()
                self.logger.info('Database connection closed.')
                time.sleep(40)
                conn = self.__connect()
                cur = conn.cursor()

        except (Exception, psycopg2.DatabaseError) as ex:
            self.logger.critical(''.join(traceback.format_exception(ex)))
            if conn is not None:
                conn.close()
        finally:
            if conn is not None:
                conn.close()
                self.logger.info('Database connection closed.')

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
            conn = self.__connect()
            cur = conn.cursor()
            cur.execute('select min(block_id) from reports.proof_chain_moonbeam where finalization_hash is null')
            block_id = cur.fetchone()
            if block_id is not None:
                self.last_block_id = block_id[0]
                self.logger.info("starting from block id " + str(self.last_block_id))
            else:
                self.last_block_id = 1
        except Exception as ex:
            self.logger.warning(''.join(traceback.format_exception(ex)))

    @staticmethod
    def __update_cursor(block_id):
        for fr in FinalizationRequest.get_requests_to_be_confirmed():
            if fr.session_started_block_id < block_id:
                return
        for fr in FinalizationRequest.get_requests_to_be_finalized():
            if fr.session_started_block_id < block_id:
                return
