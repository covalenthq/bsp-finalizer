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
        self.logger = logformat.LogFormat.init_logger("Finalizer", console_mode=True)

    def __main_loop(self):
        # self.contract.estimate_gas_price()
        self.refinalize_rejected_requests()
        frs = FinalizationRequest.get_requests_to_be_finalized()
        # while len(frs) > 0:
        ready_to_finalize = []
        bn = self.contract.block_number()
        for fr in frs:
            if fr.deadline < bn:
                ready_to_finalize.append(fr)
        if len(ready_to_finalize) == 0:
            return
        self.logger.info("Finalizing {} sessions.".format(len(ready_to_finalize)))
        for fr in ready_to_finalize:
            self._attempt_to_finalize(fr)
        self.logger.info("{} sessions have been finalized.".format(len(ready_to_finalize)))

    def run(self) -> None:
        # we need to avoid recursion in order to avoid stack depth exceeded exception
        while True:
            time.sleep(12)
            try:
                self.__main_loop()
            except:
                # this should never happen
                self.__main_loop()

    def refinalize_rejected_requests(self):
        to_send = []
        for fr in FinalizationRequest.get_requests_to_be_confirmed():
            if fr.finalized_time < time.time() - 200:
                to_send.append(fr)
        if len(to_send) == 0:
            return
        self.logger.info("Refinalizing {} sessions.".format(len(to_send)))
        while len(to_send) > 0:
            i = 0
            for fr in to_send[:1000]:
                self._attempt_to_finalize(fr)
                i += 1
            to_send = to_send[1000:]
            self.logger.info("{} sessions have been refinalized.".format(i))

    def _attempt_to_finalize(self, fr):
        try:
            self.contract.send_finalize(int(fr.chainId), int(fr.blockHeight), 60)
        except Exception as ex:
            self.logger.critical(''.join(traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))
        fr.finalize_request()
        fr.confirm_later()
