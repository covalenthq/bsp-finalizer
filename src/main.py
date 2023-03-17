import logging
import time
import sys
import os

from dotenv import load_dotenv
from contract import ProofChainContract
from dbmanager import DBManager
from finalizer import Finalizer


def is_any_thread_alive(threads):
    return True in [t.is_alive() for t in threads]


if __name__ == "__main__":
    load_dotenv()

    BLOCK_ID_START = os.getenv("BLOCK_ID_START", "-1")
    PROOFCHAIN_ADDRESS = os.getenv("PROOFCHAIN_ADDRESS")
    FINALIZER_PRIVATE_KEY = os.getenv("FINALIZER_PRIVATE_KEY")
    FINALIZER_ADDRESS = os.getenv("FINALIZER_ADDRESS")
    RPC_ENDPOINT = os.getenv("RPC_ENDPOINT")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_DATABASE = os.getenv("DB_DATABASE")
    CHAIN_TABLE_NAME = os.getenv("CHAIN_TABLE_NAME")

    logging.basicConfig(
        stream=sys.stdout,
        format="%(levelname)s %(name)s (%(filename)s:%(lineno)d) - %(message)s",
        level=logging.INFO,
    )
    contract = ProofChainContract(
        rpc_endpoint=RPC_ENDPOINT,
        proofchain_address=PROOFCHAIN_ADDRESS,
        finalizer_prvkey=FINALIZER_PRIVATE_KEY,
        finalizer_address=FINALIZER_ADDRESS,
    )
    dbm = DBManager(
        starting_point=int(BLOCK_ID_START),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        host=DB_HOST,
        chain_table=CHAIN_TABLE_NAME,
    )
    dbm.daemon = True

    finalizer = Finalizer(contract)
    finalizer.daemon = True
    dbm.start()

    finalizer.start()

    while is_any_thread_alive([finalizer, dbm]):
        time.sleep(0.3)

    #
    # contract.send_finalize(4, 10430382)
    # contract.subscribe_on_event(handle_event)

    # dbm.join()
    # finalizer.join()
