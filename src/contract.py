import statistics
import traceback

from web3.exceptions import TimeExhausted
from web3.middleware import geth_poa_middleware
import web3.auto
import os
from web3 import Web3

import logformat

PATH = os.getenv('PATH')
class ProofChainContract:
    def __init__(self, rpc_endpoint, finalizer_address, finalizer_prvkey, proofchain_address):
        self.counter = 0
        self.finalizer_address = finalizer_address
        self.finalizer_prvkey = finalizer_prvkey
        self.provider: Web3.HTTPProvider = Web3.HTTPProvider(rpc_endpoint)
        self.w3: Web3 = Web3(self.provider)
        self.gas = 270000
        self.gasPrice = web3.auto.w3.toWei('102', 'gwei')
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.contractAddress: str = proofchain_address
        with open(PATH+"/abi/ProofChainContractABI", "r") as f:
            self.contract = self.w3.eth.contract(
                address=self.contractAddress,
                abi=f.read()
            )

        self.logger = logformat.LogFormat.init_logger("Contract", console_mode=True)

    # asynchronous defined function to loop
    # this loop sets up an event filter and is looking for new entires for the "PairCreated" event
    # this loop runs on a poll interval
    # async def _log_loop(self, event_filter, poll_interval, cb):
    #     while True:
    #         try:
    #             for PairCreated in event_filter.get_new_entries():
    #                 cb(PairCreated)
    #             await asyncio.sleep(poll_interval)
    #         except Exception as e:
    #             print(e)
    #             self.subscribe_on_event(cb)

    def send_finalize(self, chainId, blockHeight, timeout=None):
        self.nonce = self.w3.eth.get_transaction_count(self.finalizer_address)
        transaction = self.contract.functions.finalizeAndRewardSpecimenSession(
            chainId,
            blockHeight).buildTransaction({
            'gas': self.gas,
            'gasPrice': self.gasPrice,
            'from': self.finalizer_address,
            'nonce': self.nonce
        })
        signed_txn = self.w3.eth.account.signTransaction(transaction, private_key=self.finalizer_prvkey)
        tx_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        self.logger.info("sent a transaction for {} {} nonce: {} balance: {}"
                         .format(chainId, blockHeight, self.nonce, self.w3.eth.get_balance(self.finalizer_address)))
        if timeout is not None:
            try:
                self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout)
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)

                if receipt['status'] == 0:
                    self.logger.warning(
                        "transaction failed with blockNumber {} comGasUsed {} gasUsed {} status {} trxHash {} trxIndex {} "
                            .format(receipt['blockNumber'],
                                    receipt['cumulativeGasUsed'],
                                    receipt['gasUsed'],
                                    receipt['status'],
                                    receipt['transactionHash'].hex(),
                                    receipt['transactionIndex'],
                                    )
                    )
                else:
                    self.logger.info(
                        "transaction mined with blockNumber {} comGasUsed {} gasUsed {} status {} trxHash {} trxIndex {} "
                            .format(receipt['blockNumber'],
                                    receipt['cumulativeGasUsed'],
                                    receipt['gasUsed'],
                                    receipt['status'],
                                    receipt['transactionHash'].hex(),
                                    receipt['transactionIndex'],
                                    )
                    )
            except TimeExhausted as ex:
                # TODO what can we do?
                self.increase_gas_price(self.gas)
                self.logger.critical(''.join(
                    traceback.format_exception(etype=type(ex), value=ex, tb=ex.__traceback__)))

    def block_number(self):
        return self.w3.eth.get_block('latest').number

    # def subscribe_on_event(self, cb, from_block=1):
    #     event_filter = self.contract.events.SessionStarted.createFilter(fromBlock=from_block)
    #     loop = asyncio.get_event_loop()
    #     try:
    #         loop.run_until_complete(
    #             asyncio.gather(
    #                 self._log_loop(event_filter, 2, cb)))
    #         # log_loop(block_filter, 2),
    #         # log_loop(tx_filter, 2)))
    #     finally:
    #         # close loop to free up system resources
    #         loop.close()
    def estimate_gas_price(self):
        pending_transactions = self.provider.make_request("parity_futureTransactions", [])
        gas_prices = []
        gases = []
        print(pending_transactions)
        for tx in pending_transactions["result"[:10]]:
            gas_prices.append(int((tx["gasPrice"]),16))
            gases.append(int((tx["gas"]),16))
        print("Average:")
        print("-"*80)
        print("gasPrice: ", statistics.mean(gas_prices))
        print(" ")
        print("Median:")
        print("-"*80)
        print("gasPrice: ", statistics.median(gas_prices))

    def increase_gas_price(self, gasPrice):
        # try to replace the unmined trx next time in emergency cases
        self.gasPrice = gasPrice * 1.15
