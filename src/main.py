import logging
import time
import threading
import sys
import os

from dotenv import load_dotenv
from dbmanspecimen import DBManagerSpecimen
from dbmanresult import DBManagerResult
from contract import ProofChainContract
from finalizer import Finalizer


def is_any_thread_alive(threads):
    return True in [t.is_alive() for t in threads]


if __name__ == "__main__":
    load_dotenv()

    BLOCK_ID_START = os.getenv("BLOCK_ID_START", "-1")
    BSP_PROOFCHAIN_ADDRESS = os.getenv("BSP_PROOFCHAIN_ADDRESS")
    BRP_PROOFCHAIN_ADDRESS = os.getenv("BRP_PROOFCHAIN_ADDRESS")
    FINALIZER_PRIVATE_KEY = os.getenv("FINALIZER_PRIVATE_KEY")
    FINALIZER_ADDRESS = os.getenv("FINALIZER_ADDRESS")
    RPC_ENDPOINT = os.getenv("RPC_ENDPOINT")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_DATABASE = os.getenv("DB_DATABASE")
    CHAIN_TABLE_NAME = os.getenv("CHAIN_TABLE_NAME")

    lock = threading.Lock()

    logging.basicConfig(
        stream=sys.stdout,
        format="%(levelname)s %(name)s (%(filename)s:%(lineno)d) - %(message)s",
        level=logging.INFO,
    )
    contract = ProofChainContract(
        rpc_endpoint=RPC_ENDPOINT,
        finalizer_address=FINALIZER_ADDRESS,
        finalizer_prvkey=FINALIZER_PRIVATE_KEY,
        bsp_proofchain_address=BSP_PROOFCHAIN_ADDRESS,
        brp_proofchain_address=BRP_PROOFCHAIN_ADDRESS,
    )

    # dbms = DBManagerSpecimen(
    #     starting_point=int(BLOCK_ID_START),
    #     user=DB_USER,
    #     password=DB_PASSWORD,
    #     database=DB_DATABASE,
    #     host=DB_HOST,
    #     chain_table=CHAIN_TABLE_NAME,
    # )

    # dbms.daemon = True

    dbmr = DBManagerResult(
        starting_point=int(BLOCK_ID_START),
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_DATABASE,
        host=DB_HOST,
        chain_table=CHAIN_TABLE_NAME,
    )

    dbmr.daemon = False

    finalizer = Finalizer(contract, lock=lock)
    finalizer.daemon = True

    # dbms.start()
    dbmr.start()
    finalizer.start()

    dbmr.join()
    finalizer.join()

    # while is_any_thread_alive([finalizer, dbmr]):
    #     time.sleep(0.3)
