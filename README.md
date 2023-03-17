# BSP Finalizer

Finalisation and reward processor for consensus block specimens sessions and block results session using the covalent db and proofchain. It functions at the end of the BSP stack within the following pipeline `bsp-geth -> bsp-agent -> bsp-staking -> bsp-finalizer -> rudder/refiner`

The "finalizer" fns for the network can be called by anyone with gas available in their account. The function is a simple call to the proof chain smart contract with chain ID and the block height being finalized for block specimens whose sessions have been started by a submission and the submissions period has ended (so no more participants can submit a valid hash). A valid session is created for each hash that is submitted by an operator.

Three issues are possible during submission -

- "Session not past deadline" - trying to finalize a session that's not reached a deadline for submissions yet
- "Session cannot be finalized" - issues on the proofchain contract end
- "Session not started" - trying to finalize a session for a block number that's not been started by any parrticipant yet.

The process of finalization invokes the reward paid out to all the contributors to the consensus blocks and also produces a finalization hash which is then indexed by the covalent db. The covalent db is used as a reference point for finalized vs un-finalized blocks and any gaps in the indexing of finalized hashes will result in interim hiccups in this process.

```sol
finalizeAndRewardSpecimenSession(uint64 chainId, uint64 blockHeight)
```

The finalizer will also be extended for block results and their respective finalizations and rewards pay outs.

```sol
finalizeAndRewardResultSession(uint64 chainId, uint64 blockHeight)
```

## Standalone Run

In order to run access to the covalent db is required. Please ask the code owners of this repo @noslav or @kitti-katy for access.

1. Place appropriate values in an `.envrc` or `.env` file:

```envrc
    export RPC_ENDPOINT="http://endpoint-to-where-proofchain-is-deployed"
    export BLOCK_ID_START="1910104892088990000"
    export PROOFCHAIN_ADDRESS="0x19492a5019B30471aA8fa2c6D9d39c99b5Cda20C" 
    export FINALIZER_PRIVATE_KEY="0xprivatekeyoffinalizerwithgas"
    export FINALIZER_ADDRESS="0xpublicaddressofaboveprivatekey"
    export DB_USER="db_access_user"
    export DB_PASSWORD="db_access_user_password"
    export DB_HOST="replica.reach.point"
    export DB_DATABASE="blockchains"
    export CHAIN_TABLE_NAME="chain_moonbeam_moonbase_alpha"
    export GAS_PRICE=1
    export GAS_LIMIT=300000
```

2. Load environment variables:

```bash
    direnv allow .
```

3. Create directories for logging:

```bash
    mkdir -p logs/{Contract,Finalizer,DB}
```

4. Install python packages (virtualenv):

```bash
    python3 -m virtualenv ./.venv
    source .venv/bin/activate
    brew install openssl # In case you don't have it already installed
    export LDFLAGS="-L/opt/homebrew/opt/openssl@3/lib"; pip install -r requirements.txt
```

5. Run the script:

```bash
    python3 src/main.py
```

## Docker run

Login to GCR for docker images with -

```bash
    gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin https://gcr.io
```

Add an `.env` file with all the env variables mentioned above.

Pull the images and run (arm64) -

```bash
    docker pull gcr.io/covalent-project/bsp-finalizer:latest-arm64
    docker run --env-file .env gcr.io/covalent-project/bsp-finalizer:latest-arm64
```

Pull the images and run (amd64) -

```bash
    docker pull gcr.io/covalent-project/bsp-finalizer:latest
    docker run --env-file .env gcr.io/covalent-project/bsp-finalizer:latest
```

If the run is successful you should see logs such as below.

```log
INFO DB (dbmanager.py:74) - Connecting to the database...
INFO DB (dbmanager.py:76) - Initial scan block_id=1870737934539735450
DEBUG Finalizer (finalizer.py:43) - Nothing ready to finalize height=3958481 openSessions=0..
```
