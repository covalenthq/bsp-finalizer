import time


class FinalizationRequest:
    requests_to_be_finalized = dict()
    requests_to_be_confirmed = dict()

    @staticmethod
    def get_requests_to_be_finalized() -> []:
        values = list(FinalizationRequest.requests_to_be_finalized.values())
        frs = []
        for v in values:
            for fr in v.values():
                frs.append(fr)
        return frs

    @staticmethod
    def get_requests_to_be_confirmed() -> []:
        values = list(FinalizationRequest.requests_to_be_confirmed.values())
        frs = []
        for v in values:
            for fr in v.values():
                frs.append(fr)
        return frs

    def __init__(self, chainId, blockHeight, deadline, block_id):
        self.deadline = deadline
        self.chainId = chainId
        self.blockHeight = blockHeight
        self.session_started_block_id = block_id
        self.finalized_time = None

    def update_block_id(self, bid):
        self.block_id = bid

    def confirm_request(self):
        if self.chainId in FinalizationRequest.requests_to_be_confirmed.keys():
            FinalizationRequest.requests_to_be_confirmed[self.chainId].pop(self.blockHeight, None)

    def finalize_request(self):
        if self.chainId in FinalizationRequest.requests_to_be_finalized.keys():
            FinalizationRequest.requests_to_be_finalized[self.chainId].pop(self.blockHeight, None)

        self.finalized_time = time.time()

    def finalize_later(self):
        if self.chainId not in FinalizationRequest.requests_to_be_finalized:
            FinalizationRequest.requests_to_be_finalized[self.chainId] = dict()
        reqs_for_chain = FinalizationRequest.requests_to_be_finalized[self.chainId]
        if self.blockHeight in reqs_for_chain:
            return False
        reqs_for_chain[self.blockHeight] = self
        return True

    def confirm_later(self):
        if self.chainId not in FinalizationRequest.requests_to_be_confirmed:
            FinalizationRequest.requests_to_be_confirmed[self.chainId] = dict()
        reqs_for_chain = FinalizationRequest.requests_to_be_confirmed[self.chainId]
        if self.blockHeight in reqs_for_chain:
            return False
        reqs_for_chain[self.blockHeight] = self
        return True

    def waiting_for_confirm(self):
        if self.chainId in FinalizationRequest.requests_to_be_confirmed.keys():
            if self.blockHeight in FinalizationRequest.requests_to_be_confirmed[self.chainId].keys():
                return True
        return False

    def waiting_for_finalize(self):
        if self.chainId in FinalizationRequest.requests_to_be_finalized.keys():
            if self.blockHeight in FinalizationRequest.requests_to_be_finalized[self.chainId].keys():
                return True
        return False
