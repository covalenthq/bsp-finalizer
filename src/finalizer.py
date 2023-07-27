import threading
import time
import traceback

import logformat

from finalizationspecimenrequest import FinalizationSpecimenRequest
from finalizationresultrequest import FinalizationResultRequest
from contract import ProofChainContract


class Finalizer(threading.Thread):
    def __init__(self, cn: ProofChainContract, lock):
        super().__init__()
        self.contract = cn
        self.logger = logformat.get_logger("Finalizer")
        self.observer_chain_block_height = 0
        self.running = True
        self.lock = lock

    def wait_for_next_observer_chain_block(self):
        while True:
            try:
                bn = self.contract.block_number()
                if bn > self.observer_chain_block_height:
                    self.observer_chain_block_height = bn
                    return
                time.sleep(1.0)
            except Exception as ex:
                self.logger.critical("".join(traceback.format_exception(ex)))
                time.sleep(1.0)

    def __main_loop(self):
        self.wait_for_next_observer_chain_block()
        # self.refinalize_rejected_specimen_requests()
        # self.refinalize_rejected_result_requests()

        ready_to_specimen_finalize = []
        open_specimen_session_count = 0

        ready_to_result_finalize = []
        open_result_session_count = 0

        for frs in FinalizationSpecimenRequest.get_requests_to_be_finalized():
            if frs.deadline < self.observer_chain_block_height:
                ready_to_specimen_finalize.append(frs)
            else:
                open_specimen_session_count += 1

        self.logger.info(f"Finalizing {len(ready_to_specimen_finalize)} specimen proof-sessions...")
        for frs in ready_to_specimen_finalize:
            self._attempt_to_finalize_specimen(frs)
        self.logger.info(f"Finalized {len(ready_to_specimen_finalize)} specimen proof-sessions")

        if len(ready_to_specimen_finalize) == 0:
            self.logger.debug(
                f"Nothing ready to finalize height={self.observer_chain_block_height} specimen openSessions={open_specimen_session_count}"
            )

        for frr in FinalizationResultRequest.get_result_requests_to_be_finalized():
            if frr.deadline < self.observer_chain_block_height:
                ready_to_result_finalize.append(frr)
            else:
                open_result_session_count += 1

        self.logger.info(f"Finalizing {len(ready_to_result_finalize)} result proof-sessions...")
        for frr in ready_to_result_finalize:
            self._attempt_to_finalize_result(frr)
        self.logger.info(f"Finalized {len(ready_to_result_finalize)} result proof-sessions")

        if len(ready_to_result_finalize) == 0:
            self.logger.debug(
                f"Nothing ready to finalize height={self.observer_chain_block_height} result openSessions={open_result_session_count}"
            )
            return

    def run(self) -> None:
        # we need to avoid recursion in order to avoid stack depth exceeded exception
        while self.running:
            try:
                self.lock.acquire()
                self.__main_loop()
                self.lock.release()
            except RecursionError:
                # this should never happen
                pass

    def refinalize_rejected_specimen_requests(self):
        to_send = []
        for frs in FinalizationSpecimenRequest.get_requests_to_be_confirmed():
            if frs.finalized_time < time.time() - 600:
                to_send.append(frs)
        num_to_send = len(to_send)
        if num_to_send == 0:
            return
        self.logger.info(f"Refinalizing {num_to_send} specimen proof-sessions...")
        while len(to_send) > 0:
            i = 0
            for frs in to_send[:1000]:
                self._attempt_to_finalize_specimen(frs)
                i += 1
            to_send = to_send[1000:]
            refinalized = num_to_send - len(to_send)
            self.logger.info(f"Refinalized {refinalized} specimen proof-sessions")

    def refinalize_rejected_result_requests(self):
        to_send = []
        for frr in FinalizationResultRequest.get_result_requests_to_be_confirmed():
            if frr.finalized_time < time.time() - 600:
                to_send.append(frr)
        num_to_send = len(to_send)
        if num_to_send == 0:
            return
        self.logger.info(f"Refinalizing {num_to_send} result proof-sessions...")
        while len(to_send) > 0:
            i = 0
            for frr in to_send[:1000]:
                self._attempt_to_finalize_specimen(frr)
                i += 1
            to_send = to_send[1000:]
            refinalized = num_to_send - len(to_send)
            self.logger.info(f"Refinalized {refinalized} result proof-sessions")

    def _attempt_to_finalize_specimen(self, frs):
        try:
            self.contract.send_specimen_finalize(
                chainId=int(frs.chainId), blockHeight=int(frs.blockHeight), timeout=60
            )
            frs.finalize_request()
            frs.confirm_later()
        except Exception as ex:
            self.logger.critical("".join(traceback.format_exception(ex)))

    def _attempt_to_finalize_result(self, frr):
        try:
            self.contract.send_result_finalize(
                chainId=int(frr.chainId), blockHeight=int(frr.blockHeight), timeout=200
            )
            frr.finalize_request()
            frr.confirm_later()
        except Exception as ex:
            self.logger.critical("".join(traceback.format_exception(ex)))
