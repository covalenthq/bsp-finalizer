# bsp-finalizer

# Running

Put appropriate values on the `.env` file:

```
RPC_ENDPOINT=""
BLOCK_ID_START="1606150927003422917" # The block ID from which DB thread starts reading off
PROOFCHAIN_ADDRESS="0x48bb0d9653D30b977439c71B3F6C4557137dD0ad"
FINALIZER_PRIVATE_KEY=""
FINALIZER_ADDRESS=""
DB_USER=""
DB_PASSWORD=""
DB_HOST="master.datamodel.db.covalenthq.com"
DB_DATABASE="blockchains"
```

Load environment variables:
```
direnv allow
```

Create directories for logging:

```
mkdir -p logs/{Contract,Finalizer,DB}
```

Install python packages (venv):

```
python3 -m venv ./.venv
source .venv/bin/activate
brew install openssl # In case you don't already installed it
export LDFLAGS="-L/opt/homebrew/opt/openssl@3/lib"; pip install -r requirements.txt
```

Run the script:
```
python3 src/main.py
```