import threading
import time
import traceback

import logformat
from contract import ProofChainContract
from finalizationrequest import FinalizationRequest


class Finalizer(threading.Thread):
    def __init__(self, cn: ProofChainContract):
        super().__init__()
        self.contract = cn
        self.logger = logformat.get_logger("Finalizer")
        self.observer_chain_block_height = 0

    def wait_for_next_observer_chain_block(self):
        while True:
            try:
                bn = self.contract.block_number()
                if bn > self.observer_chain_block_height:
                    self.observer_chain_block_height = bn
                    return
                else:
                    time.sleep(4.0)
            except Exception as ex:
                self.logger.critical(''.join(traceback.format_exception(ex)))
                time.sleep(4.0)

    def __main_loop(self):
        self.wait_for_next_observer_chain_block()
        self.refinalize_rejected_requests()

        ready_to_finalize = []
        open_session_count = 0

        for fr in FinalizationRequest.get_requests_to_be_finalized():
            if fr.deadline < self.observer_chain_block_height:
                ready_to_finalize.append(fr)
            else:
                open_session_count += 1


        if len(ready_to_finalize) == 0:
            self.logger.debug(f"Nothing ready to finalize height={self.observer_chain_block_height} openSessions={open_session_count}")
            return

        self.logger.info(f"Finalizing {len(ready_to_finalize)} proof-sessions...")
        for fr in ready_to_finalize:
            self._attempt_to_finalize(fr)
        self.logger.info(f"Finalized {len(ready_to_finalize)} proof-sessions")

    def run(self) -> None:
        # we need to avoid recursion in order to avoid stack depth exceeded exception
        while True:
            try:
                self.__main_loop()
            except:
                # this should never happen
                pass

    def refinalize_rejected_requests(self):
        to_send = []
        for fr in FinalizationRequest.get_requests_to_be_confirmed():
            if fr.finalized_time < time.time() - 600:
                to_send.append(fr)
        num_to_send = len(to_send)
        if num_to_send == 0:
            return
        self.logger.info(f"Refinalizing {num_to_send} proof-sessions...")
        while len(to_send) > 0:
            i = 0
            for fr in to_send[:1000]:
                self._attempt_to_finalize(fr)
                i += 1
            to_send = to_send[1000:]
            self.logger.info("Refinalized {num_to_send - len(to_send)} proof-sessions")

    def _attempt_to_finalize(self, fr):
        try:
            self.contract.send_finalize(chainId=int(fr.chainId), blockHeight=int(fr.blockHeight), timeout=300)
            fr.finalize_request()
            fr.confirm_later()
        except Exception as ex:
            self.logger.critical(''.join(traceback.format_exception(ex)))

