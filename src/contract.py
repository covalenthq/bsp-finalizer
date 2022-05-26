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
        self.nonce = None
        self.counter = 0
        self.finalizer_address = finalizer_address
        self.finalizer_prvkey = finalizer_prvkey
        self.provider: Web3.HTTPProvider = Web3.HTTPProvider(rpc_endpoint)
        self.w3: Web3 = Web3(self.provider)
        self.gas = os.getenv("GAS_LIMIT")
        self.gasPrice = web3.auto.w3.toWei(os.getenv('GAS_PRICE'), 'gwei')
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

    class Receipt():
        def __init__(self, fields):
            self.blockNumber = fields['blockNumber']
            self.cumGasUsed = fields['cumulativeGasUsed']
            self.gasUsed = fields['gasUsed']
            self.status = fields['status']
            self.txHash = fields['transactionHash'].hex()
            self.txIndex = fields['transactionIndex']

        def succeeded(self):
            return self.status == 1

        def __str__(self):
            return (
                f"blockNumber={self.blockNumber}"
                f" cumGasUsed={self.cumGasUsed}"
                f" gasUsed={self.gasUsed}"
                f" status={self.status}"
                f" txHash={self.txHash}"
                f" txIndex={self.txIndex}"
            )

    def _retry_with_backoff(self, fn, retries=2, backoff_in_seconds=1, **kwargs):
        retries_left = retries
        while True:
            try:
                match fn(**kwargs):
                    case (True, result):
                        return result

                    case (False, sleep_interval):
                        if sleep_interval > 0:
                            time.sleep(sleep_interval)
                        retries_left -= 1

            except Exception as ex:
                if retries_left == 0:
                    raise

                self.logger.warning(f"exception occurred (will retry): {type(ex).__name__}: {ex}")
                sleep_interval = (backoff_in_seconds * (2 ** i)) + random.uniform(0, 1)
                time.sleep(sleep_interval)
                retries_left -= 1

    def send_finalize(self, **kwargs):
        return self._retry_with_backoff(self._attempt_send_finalize, **kwargs)

    def _attempt_send_finalize(self, chainId, blockHeight, timeout=None):
        if self.nonce is None:
            self._refresh_nonce()

        transaction = self.contract.functions.finalizeAndRewardSpecimenSession(
            chainId,
            blockHeight).buildTransaction({
            'gas': self.gas,
            'gasPrice': self.gasPrice,
            'from': self.finalizer_address,
            'nonce': self.nonce
        })
        signed_txn = self.w3.eth.account.signTransaction(transaction, private_key=self.finalizer_prvkey)

        balance_before_send = self.w3.eth.get_balance(self.finalizer_address)

        tx_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)

        self.logger.info(
            f"sent a transaction for {chainId} {blockHeight}"
            f" sender_balance={balance_before_send}"
            f" using_nonce={self.nonce}"
        )

        if timeout is not None:
            try:
                self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=1.0)
                receipt = Receipt(self.w3.eth.get_transaction_receipt(tx_hash))

                if receipt.succeeded():
                    self.logger.info(f"transaction mined with {receipt}")
                else:
                    self.logger.warning(f"transaction failed with {receipt}")

                return (True, None)

            except TimeExhausted as ex:
                self.increase_gas_price()
                # retry immediately
                return (False, 0)

            except ValueError as ex:
                if len(ex.args) != 1 or type(ex.args[0]) != dict:
                    raise

                jsonrpc_err = ex.args[0]
                if 'code' not in jsonrpc_err or 'message' not in jsonrpc_err:
                    raise

                match (jsonrpc_err['code'], jsonrpc_err['message']):
                    case (-32603, 'nonce too low'):
                        time.sleep(60) # wait for pending txs to clear
                        self._refresh_nonce()

                        # retry immediately (we already waited)
                        return (False, 0)
                    case _:
                        raise

    def _refresh_nonce(self):
        self.nonce = self.w3.eth.get_transaction_count(self.finalizer_address)

    def block_number(self):
        return self._retry_with_backoff(self._attempt_block_number)

    def _attempt_block_number(self):
        return (True, self.w3.eth.get_block('latest').number)

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

    def increase_gas_price(self):
        # try to replace the unmined trx next time in emergency cases
        self.gasPrice *= 1.15
