import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import py_nillion_client as nillion
from py_nillion_client import UserKey, NodeKey
from nillion_python_helpers import create_nillion_client
from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.keypairs import PrivateKey
import uuid  
from typing import Dict, List, Optional, Set, Union
from psycopg2 import pool
import time
from collections import defaultdict
import threading

load_dotenv()

ttl_days=30

# Nillion Testnet Config: https://docs.nillion.com/network
nillion_testnet_default_config = {
    "cluster_id": 'b13880d3-dde8-4a75-a171-8a1a9d985e6c',
    "grpc_endpoint": 'https://testnet-nillion-grpc.lavenderfive.com',
    "chain_id": 'nillion-chain-testnet-1',
    "bootnodes": ['/dns/node-1.testnet-photon.nillion-network.nilogy.xyz/tcp/14111/p2p/12D3KooWCfFYAb77NCjEk711e9BVe2E6mrasPZTtAjJAPtVAdbye']
}

default_secret_name = "my_secret"
default_nillion_user_seed = "user_123"

import py_nillion_client as nillion
from cosmpy.aerial.client import NetworkConfig
from cosmpy.aerial.client.utils import prepare_and_broadcast_basic_transaction
from cosmpy.aerial.tx import Transaction
from cosmpy.crypto.address import Address


async def get_quote_and_pay(
    client: nillion.NillionClient,
    operation: nillion.Operation,
    payments_wallet,
    payments_client,
    cluster_id,
    memo: str | None = None,
) -> nillion.PaymentReceipt:
    """
    Initiates a payment for the specified operation using the Nillion client.

    Args:
        client (nillion.NillionClient): The Nillion client instance.
        operation (nillion.Operation): The operation for which to request a price quote and make a payment.
        payments_wallet: The wallet to be used for the payment.
        payments_client: The client used to process the payment transaction.
        cluster_id: The cluster identifier for the Nillion network.
        memo (str | None, optional): An optional memo to include with the transaction. Defaults to None.

    Returns:
        nillion.PaymentReceipt: The receipt of the payment containing the quote and transaction hash.
    """
    print("Getting quote for operation...")
    quote = await client.request_price_quote(cluster_id, operation)
    if quote.cost.total > 250000:
        raise HTTPException(status_code=400, detail=f"Quote {quote.cost.total} cost exceeds the maximum allowed limit of 250000 unil.")
    address = str(Address(payments_wallet.public_key(), "nillion"))
    message = nillion.create_payments_message(quote, address)
    tx = Transaction()
    tx.add_message(message)

    # Pass the memo parameter to prepare_and_broadcast_basic_transaction, default to an empty string if memo is None
    submitted_tx = prepare_and_broadcast_basic_transaction(
        payments_client, tx, payments_wallet, gas_limit=1000000, memo=memo
    )

    submitted_tx.wait_to_complete()
    print(
        f"Submitting payment receipt {quote.cost.total} unil, tx hash {submitted_tx.tx_hash}"
    )
    return nillion.PaymentReceipt(quote, submitted_tx.tx_hash)


async def get_quote(
    client: nillion.NillionClient,
    operation: nillion.Operation,
    cluster_id,
):
    """
    Retrieves a price quote for the specified operation using the Nillion client.

    Args:
        client (nillion.NillionClient): The Nillion client instance.
        operation (nillion.Operation): The operation for which to request a price quote.
        cluster_id: The cluster identifier for the Nillion network.

    Returns:
        nillion.PriceQuote: The price quote for the operation.
    """
    print("Getting quote for operation...")
    quote = await client.request_price_quote(cluster_id, operation)
    print("QUOTE",quote)
    return quote


async def pay_with_quote(
    quote: nillion.PriceQuote,
    payments_wallet,
    payments_client,
) -> nillion.PaymentReceipt:
    """
    Processes a payment using an existing price quote.

    Args:
        quote (nillion.PriceQuote): The price quote for the operation.
        payments_wallet: The wallet to be used for the payment.
        payments_client: The client used to process the payment transaction.

    Returns:
        nillion.PaymentReceipt: The receipt of the payment containing the quote and transaction hash.
    """
    address = str(Address(payments_wallet.public_key(), "nillion"))
    message = nillion.create_payments_message(quote, address)
    tx = Transaction()
    tx.add_message(message)
    submitted_tx = prepare_and_broadcast_basic_transaction(
        payments_client, tx, payments_wallet, gas_limit=1000000
    )
    submitted_tx.wait_to_complete()
    print(
        f"Submitting payment receipt {quote.cost.total} unil, tx hash {submitted_tx.tx_hash}"
    )
    return nillion.PaymentReceipt(quote, submitted_tx.tx_hash)


def create_payments_config(chain_id, payments_endpoint, scheme="grpc"):
    """
    Creates a network configuration for the payments client.

    Args:
        chain_id: The chain ID of the network.
        payments_endpoint: The http or https endpoint URL for the payments service.
        scheme: The scheme to use for the URL. Defaults to "grpc".

    Returns:
        NetworkConfig: The network configuration object.
    """
    if not payments_endpoint.startswith(("http://", "https://")):
        print(
            "Deprecation warning: payments_endpoint should start with http:// or https://"
        )
        payments_endpoint = f"http://{payments_endpoint}"

    return NetworkConfig(
        chain_id=chain_id,
        url=f"{scheme}+{payments_endpoint}/",
        fee_minimum_gas_price=0,
        fee_denomination="unil",
        staking_denomination="unil",
        faucet_url=None,
    )


# Create payments config, client and wallet
payments_config = create_payments_config(nillion_testnet_default_config["chain_id"], nillion_testnet_default_config["grpc_endpoint"])
payments_client = LedgerClient(payments_config)

# Check that private key is set in the .env file
try:
    private_key = PrivateKey(bytes.fromhex(os.getenv("NILLION_PRIVATE_KEY")))
except Exception as e:
    raise RuntimeError(f"Make sure to set a funded Nillion Testnet private key in the .env file.")

payments_wallet = LocalWallet(
    private_key,
    prefix="nillion",
)
class RateLimiter:
    def __init__(self):
        self.requests_per_minute = 30
        self.window_size = 60  # seconds
        self.request_counts = defaultdict(list)
        self.lock = threading.Lock()

    def is_rate_limited(self, client_ip: str) -> bool:
        current_time = time.time()
        
        with self.lock:
            # Clean old requests
            self.request_counts[client_ip] = [
                req_time for req_time in self.request_counts[client_ip]
                if current_time - req_time < self.window_size
            ]
            
            if len(self.request_counts[client_ip]) >= self.requests_per_minute:
                return True
                
            self.request_counts[client_ip].append(current_time)
            return False

# Create a single instance of RateLimiter
rate_limiter = RateLimiter()

# Your existing Nillion config...

app = FastAPI(title="Nillion Storage APIs")

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host
    
    if rate_limiter.is_rate_limited(client_ip):
        return Response(
            content="Rate limit exceeded. Please try again later.",
            status_code=429
        )
    
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Optional: Add endpoint to check rate limit status
@app.get("/rate-limit-status")
async def check_rate_limit(request: Request):
    client_ip = request.client.host
    current_time = time.time()
    
    recent_requests = len([
        req_time for req_time in rate_limiter.request_counts[client_ip]
        if current_time - req_time < rate_limiter.window_size
    ])
    
    return {
        "remaining_requests": rate_limiter.requests_per_minute - recent_requests,
        "total_limit": rate_limiter.requests_per_minute,
        "window_size_seconds": rate_limiter.window_size
    }

# Create a connection pool
db_pool = pool.SimpleConnectionPool(1, 20, dsn=os.getenv("POSTGRESQL_URL"))

# Database connection
def get_db_connection():
    connection = db_pool.getconn()
    try:
        yield connection
    finally:
        db_pool.putconn(connection)

# Pydantic models
class UserCreate(BaseModel):
    nillion_seed: str = default_nillion_user_seed

class SecretCreate(BaseModel):
    nillion_seed: str = default_nillion_user_seed
    secret_value: Union[str, int] = "hello, world"
    secret_name: Optional[str] = default_secret_name

class StoreIdItem(BaseModel):
    id: int
    nillion_user_id: str  
    store_id: str
    created_at: str 
    secret_name: str
    ttl_expires_at: str

class UserResponse(BaseModel):
    nillion_user_id: str

class CreateAppSecretResponse(BaseModel):
    store_id: str

class GetStoreIdsResponse(BaseModel):
    store_ids: List[StoreIdItem]

class UserListItem(BaseModel):
    id: int
    nillion_user_id: str

class UserListResponse(BaseModel):
    users: List[UserListItem]

class SecretRetrieveResponse(BaseModel):
    store_id: str
    secret: Union[str, int]

class WalletInfoResponse(BaseModel):
    nillion_address: str

class UserIdPermissions(BaseModel):
    retrieve: List[str] = ["user_id_1"]
    update: List[str] = ["user_id_1"]   
    delete: List[str] = ["user_id_1"]
    compute: Dict[str, Set[str]] = {
      "user_id_1": {
        "program_id_1",
        "program_id_2"
      }
    }

class AppResponse(BaseModel):
    app_id: str

@app.post("/api/apps/register")
async def register_new_app_id(connection=Depends(get_db_connection)):
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO apps DEFAULT VALUES RETURNING app_id;")
            app_id = cursor.fetchone()[0]
            connection.commit() 
            table_name = f"store_ids_{app_id}"
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                id SERIAL PRIMARY KEY,
                nillion_user_id TEXT NOT NULL,
                store_id TEXT NOT NULL,
                secret_name TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                ttl_expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '{ttl_days} days'),
                FOREIGN KEY(nillion_user_id) REFERENCES users(nillion_user_id) ON DELETE CASCADE
            );"""
            
            cursor.execute(create_table_query)
            connection.commit()
            return {"app_id": app_id}
        
    except Exception as e:
        print(f"Error during registration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/apps", response_model=List[AppResponse], include_in_schema=False)
async def get_all_apps(connection=Depends(get_db_connection)):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, app_id FROM apps;")
            apps = cursor.fetchall()
            return [AppResponse(app_id=str(app[1])) for app in apps]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/apps/{app_id}/secrets", response_model=CreateAppSecretResponse)
async def create_app_secret(app_id: str, secret: SecretCreate, permissions: UserIdPermissions, connection=Depends(get_db_connection)):
    table_name = f"store_ids_{app_id}"
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT to_regclass('{table_name}');
        """)
        table_exists = cursor.fetchone()[0] is not None
        if not table_exists:
            raise HTTPException(status_code=404, detail=f"App id '{table_name}' does not exist.")

    userkey = UserKey.from_seed(secret.nillion_seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    nillion_user_id = client.user_id

    if isinstance(secret.secret_value, str):
        new_secret = nillion.NadaValues(
        {
            secret.secret_name: nillion.SecretBlob(bytearray(secret.secret_value.encode('utf-8')))
        })

    elif isinstance(secret.secret_value, int):
        new_secret = nillion.NadaValues(
        {
            secret.secret_name: nillion.SecretInteger(secret.secret_value),
        })

    else:
        raise HTTPException(status_code=400, detail="secret_value must be a string or an integer.")

    permissions_instance = nillion.Permissions.default_for_user(nillion_user_id)
    permissions_instance.add_retrieve_permissions(set(permissions.retrieve))
    permissions_instance.add_update_permissions(set(permissions.update))
    permissions_instance.add_delete_permissions(set(permissions.delete))
    permissions_instance.add_compute_permissions(permissions.compute)

    memo_store_values = f"petnet operation: store_values; name: {secret.secret_name}; user_id: {nillion_user_id}"

    try:
        receipt_store = await get_quote_and_pay(
            client,
            nillion.Operation.store_values(new_secret, ttl_days=ttl_days),
            payments_wallet,
            payments_client,
            nillion_testnet_default_config["cluster_id"],
            memo_store_values,
        )
       
        print(receipt_store)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote failed for store values: exceeds 250000 unil {str(e)}")

    try:
        store_id = await client.store_values(
            nillion_testnet_default_config["cluster_id"], new_secret, permissions_instance, receipt_store
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store values in the client: {str(e)}")

    with connection.cursor() as cursor:
        # Check if the user exists
        cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
        user = cursor.fetchone()
        
        if user is None:
            cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))
        
        # Insert the secret into the store_ids_{app_id} table
        cursor.execute(f"""
            INSERT INTO "{table_name}" (nillion_user_id, store_id, secret_name) 
            VALUES (%s, %s, %s) RETURNING id;
        """, (nillion_user_id, store_id, secret.secret_name))
        
        secret_id = cursor.fetchone()[0]
        

    connection.commit()
    return CreateAppSecretResponse(store_id=store_id)

@app.get("/api/apps/{app_id}/store_ids", response_model=GetStoreIdsResponse)
async def get_secret_store_ids_for_app_id(app_id: str, page: int = 1, page_size: int = 100, connection=Depends(get_db_connection)):
    # Make sure the app exists
    table_name = f"store_ids_{app_id}"
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT to_regclass('{table_name}');
        """)
        table_exists = cursor.fetchone()[0] is not None
        if not table_exists:
            raise HTTPException(status_code=404, detail=f"App id '{table_name}' does not exist.")

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT id, nillion_user_id, store_id, created_at, secret_name, ttl_expires_at
            FROM "{table_name}" 
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
        """, (page_size, (page - 1) * page_size))
        store_ids = cursor.fetchall()

    return GetStoreIdsResponse(
        store_ids=[
            StoreIdItem(
                id=store_id[0],
                nillion_user_id=str(store_id[1]), 
                store_id=store_id[2],
                created_at=store_id[3].isoformat(),
                secret_name=store_id[4],
                ttl_expires_at=store_id[5].isoformat()
            ) for store_id in store_ids
        ]
    )

@app.get("/api/secret/retrieve/{store_id}", response_model=SecretRetrieveResponse)
async def retrieve_secret_by_store_id(store_id: str, retrieve_as_nillion_user_seed: str = default_nillion_user_seed,secret_name: str = default_secret_name):
    try:
        userkey = UserKey.from_seed(retrieve_as_nillion_user_seed)
        nodekey = NodeKey.from_seed(str(uuid.uuid4()))
        client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
        memo_retrieve_value = f"petnet operation: retrieve_value; name: {secret_name}; store_id: {store_id}"
        receipt_retrieve = await get_quote_and_pay(
            client,
            nillion.Operation.retrieve_value(),
            payments_wallet,
            payments_client,
            nillion_testnet_default_config["cluster_id"],
            memo_retrieve_value
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote failed for retrieve value: {str(e)}")

    try:
        result = await client.retrieve_value(
            nillion_testnet_default_config["cluster_id"], store_id, secret_name, receipt_retrieve
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve secret with name: {secret_name}. Error: {str(e)}")

    if isinstance(result[1].value, (bytes, bytearray)):
        retrieved_secret = result[1].value.decode('utf-8')
    else:
        retrieved_secret = result[1].value
    
    return SecretRetrieveResponse(store_id=store_id, secret=retrieved_secret)

@app.get("/api/wallet", response_model=WalletInfoResponse)
def get_wallet_info():
    wallet_address = payments_wallet.address() 
    return WalletInfoResponse(nillion_address=str(wallet_address))

@app.post("/api/user", response_model=UserResponse)
async def get_nillion_user_id_by_seed(user: UserCreate, connection=Depends(get_db_connection)):
    userkey = UserKey.from_seed(user.nillion_seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    nillion_user_id = client.user_id

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
        existing_user = cursor.fetchone()

        if existing_user is None:
            cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))
            user_id = cursor.fetchone()[0]
        else:
            user_id = existing_user[0]

    connection.commit()
    return UserResponse(nillion_user_id=nillion_user_id)

@app.get("/api/users", response_model=UserListResponse, include_in_schema=False)
async def get_users(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, nillion_user_id FROM users;")
        users = cursor.fetchall()
    return UserListResponse(users=[UserListItem(id=user[0], nillion_user_id=user[1]) for user in users])

@app.put("/api/apps/{app_id}/secrets/{store_id}", response_model=SecretRetrieveResponse)
async def update_secret(app_id: str, store_id: str, secret: SecretCreate, connection=Depends(get_db_connection)):
    table_name = f"store_ids_{app_id}"
    
    # Check if the table exists
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT to_regclass('{table_name}');
        """)
        table_exists = cursor.fetchone()[0] is not None
        if not table_exists:
            raise HTTPException(status_code=404, detail=f"App id '{app_id}' does not exist.")

    # Check if the store_id exists in the table
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT id FROM "{table_name}" WHERE store_id = %s;
        """, (store_id,))
        existing_secret = cursor.fetchone()
        if existing_secret is None:
            raise HTTPException(status_code=404, detail=f"Store id '{store_id}' does not exist in app '{app_id}'.")

    userkey = UserKey.from_seed(secret.nillion_seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])

    # Create new secret value
    if isinstance(secret.secret_value, str):
        new_secret = nillion.NadaValues(
        {
            secret.secret_name: nillion.SecretBlob(bytearray(secret.secret_value.encode('utf-8')))
        })
    elif isinstance(secret.secret_value, int):
        new_secret = nillion.NadaValues(
        {
            secret.secret_name: nillion.SecretInteger(secret.secret_value),
        })
    else:
        raise HTTPException(status_code=400, detail="secret_value must be a string or an integer.")

    # Update the secret in the Nillion client
    try:
        receipt_update = await get_quote_and_pay(
            client,
            nillion.Operation.store_values(new_secret, ttl_days=ttl_days),
            payments_wallet,
            payments_client,
            nillion_testnet_default_config["cluster_id"],
            f"petnet operation: update_value; store_id: {store_id}",
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote failed for update value: {str(e)}")
    
    try:
        await client.update_values(
            nillion_testnet_default_config["cluster_id"], store_id, new_secret, receipt_update
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update values in the client: {str(e)}")


    # Commit the update in the database
    with connection.cursor() as cursor:
        # First, check if the store_id exists
        cursor.execute(f"""
            SELECT id FROM "{table_name}" WHERE store_id = %s;
        """, (store_id,))
        
        existing_secret = cursor.fetchone()
        if existing_secret is None:
            raise HTTPException(status_code=404, detail=f"Store id '{store_id}' does not exist in app '{app_id}'.")

        # Proceed with the update
        cursor.execute(f"""
            UPDATE "{table_name}" 
            SET secret_name = %s 
            WHERE store_id = %s;
        """, (secret.secret_name, store_id))

        # Check if any rows were affected
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"No changes made for store_id '{store_id}'.")

    # Commit the transaction
    connection.commit()
    return SecretRetrieveResponse(store_id=store_id, secret=secret.secret_value)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
