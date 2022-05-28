import statistics
import traceback
import random
import time

from web3.exceptions import TimeExhausted
from web3.middleware import geth_poa_middleware
import web3.auto
import eth_hash.auto
import os
from web3 import Web3
import pathlib

import logformat

MODULE_ROOT_PATH = pathlib.Path(__file__).parent.parent.resolve()

class LoggableReceipt():
    def __init__(self, fields, fail_reason=None):
        self.blockNumber = fields['blockNumber']
        self.gasUsed = fields['gasUsed']
        self.status = fields['status']
        self.txHash = fields['transactionHash'].hex()
        self.txIndex = fields['transactionIndex']

    def succeeded(self):
        return self.status == 1

    def __str__(self):
        return (
            f"txHash=0x{self.txHash}"
            f" includedAs={self.blockNumber}/{self.txIndex}"
            f" spentGas={self.gasUsed}"
        )

class LoggableBounce():
    def __init__(self, tx_hash, err, details={}):
        self.txHash = tx_hash.hex()
        self.err = err
        self.details = details

    def __str__(self):
        detail_parts = ''.join([f" {k}={v}" for k, v in self.details.items()])

        return (
            f"txHash=0x{self.txHash}"
            f" err={self.err}"
            f"{detail_parts}"
        )


class ProofChainContract:
    def __init__(self, rpc_endpoint, finalizer_address, finalizer_prvkey, proofchain_address):
        self.nonce = None
        self.counter = 0
        self.finalizer_address = finalizer_address
        self.finalizer_prvkey = finalizer_prvkey
        self.provider: Web3.HTTPProvider = Web3.HTTPProvider(rpc_endpoint)
        self.w3: Web3 = Web3(self.provider)
        self.gas = int(os.getenv("GAS_LIMIT"))
        self.gasPrice = web3.auto.w3.toWei(os.getenv('GAS_PRICE'), 'gwei')
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        self.contractAddress: str = proofchain_address
        with (MODULE_ROOT_PATH / 'abi' / 'ProofChainContractABI').open('r') as f:
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

    def _retry_with_backoff(self, fn, retries=2, backoff_in_seconds=1, **kwargs):
        retries_left = retries
        exp = 0
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

                ex_desc = "\n".join(traceback.format_exception_only(ex))
                self.logger.warning(f"exception occurred (will retry): {ex_desc}")
                sleep_interval = (backoff_in_seconds * (2 ** exp)) + random.uniform(0, 1)
                time.sleep(sleep_interval)
                retries_left -= 1
                exp += 1

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

        balance_before_send_wei = self.w3.eth.get_balance(self.finalizer_address)
        balance_before_send_glmr = web3.auto.w3.fromWei(balance_before_send_wei, 'ether')

        predicted_tx_hash = eth_hash.auto.keccak(signed_txn.rawTransaction)

        self.logger.info(
            f"sending a tx to finalize {chainId}/{blockHeight}"
            f" senderBalance={balance_before_send_glmr}GLMR"
            f" senderNonce={self.nonce}"
            f" txHash=0x{predicted_tx_hash.hex()}"
        )

        tx_hash = None
        err = None
        try:
            tx_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
            return self.report_transaction_receipt(tx_hash, timeout)
        except ValueError as ex:
            if len(ex.args) != 1 or type(ex.args[0]) != dict:
                raise

            jsonrpc_err = ex.args[0]
            if 'code' not in jsonrpc_err or 'message' not in jsonrpc_err:
                raise

            match (jsonrpc_err['code'], jsonrpc_err['message']):
                case (-32603, 'nonce too low'):
                    self.report_transaction_bounce(predicted_tx_hash, err="nonce too low", details={"txNonce": self.nonce})
                    self.logger.info("pausing to allow pending txs to clear, then refreshing nonce...")
                    time.sleep(60)
                    self._refresh_nonce()

                    # retry immediately (we already waited)
                    return (False, 0)
                case _:
                    raise

    def report_transaction_bounce(self, predicted_tx_hash, err, details):
        bounce = LoggableBounce(predicted_tx_hash, err=err, details=details)
        self.logger.info(f"tx bounced with {bounce}")

    def report_transaction_receipt(self, tx_hash, timeout=None, **kwargs):
        if timeout is None:
            return (True, None)

        try:
            self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout, poll_latency=1.0)
            receipt = LoggableReceipt(self.w3.eth.get_transaction_receipt(tx_hash), **kwargs)

            if receipt.succeeded():
                self.nonce += 1
                self.logger.info(f"tx mined with {receipt}")
            else:
                self.logger.warning(f"tx failed with {receipt}")

            return (True, None)

        except TimeExhausted as ex:
            self.increase_gas_price()
            # retry immediately
            return (False, 0)

    def _refresh_nonce(self):
        self.nonce = self.w3.eth.get_transaction_count(self.finalizer_address)
        self.logger.info(f"refreshed nonce; new nonce is {self.nonce}")

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
