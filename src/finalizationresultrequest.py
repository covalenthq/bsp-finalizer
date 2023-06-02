import time


class FinalizationResultRequest:
    result_requests_to_be_finalized = {}
    result_requests_to_be_confirmed = {}

    @staticmethod
    def get_result_requests_to_be_finalized() -> []:
        values = list(FinalizationResultRequest.result_requests_to_be_finalized.values())
        frs = []
        for v in values:
            for fr in v.values():
                frs.append(fr)
        return frs

    @staticmethod
    def get_result_requests_to_be_confirmed() -> []:
        values = list(FinalizationResultRequest.result_requests_to_be_confirmed.values())
        frs = []
        for v in values:
            for fr in v.values():
                frs.append(fr)
        return frs

    def __init__(self, chainId, blockHeight, deadline, block_id):
        self.deadline = deadline
        self.chainId = chainId
        self.blockHeight = blockHeight
        self.block_id = block_id
        self.finalized_time = None

    def update_block_id(self, bid):
        self.block_id = bid

    def confirm_request(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_confirmed:
            return None
        FinalizationResultRequest.result_requests_to_be_confirmed[self.chainId].pop(
            self.blockHeight, None
        )

    def finalize_request(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_finalized:
            return None
        FinalizationResultRequest.result_requests_to_be_finalized[self.chainId].pop(
            self.blockHeight, None
        )

        self.finalized_time = time.time()

    def finalize_later(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_finalized:
            FinalizationResultRequest.result_requests_to_be_finalized[self.chainId] = {}
        reqs_for_chain = FinalizationResultRequest.result_requests_to_be_finalized[self.chainId]
        if self.blockHeight in reqs_for_chain:
            return False
        reqs_for_chain[self.blockHeight] = self
        return True

    def confirm_later(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_confirmed:
            FinalizationResultRequest.result_requests_to_be_confirmed[self.chainId] = {}
        reqs_for_chain = FinalizationResultRequest.result_requests_to_be_confirmed[self.chainId]
        if self.blockHeight in reqs_for_chain:
            return False
        reqs_for_chain[self.blockHeight] = self
        return True

    def waiting_for_confirm(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_confirmed:
            return False
        return (
            self.blockHeight
            in FinalizationResultRequest.result_requests_to_be_confirmed[self.chainId]
        )

    def waiting_for_finalize(self):
        if self.chainId not in FinalizationResultRequest.result_requests_to_be_finalized:
            return False
        return (
            self.blockHeight
            in FinalizationResultRequest.result_requests_to_be_finalized[self.chainId]
        )
