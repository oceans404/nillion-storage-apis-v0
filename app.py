import os
import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import py_nillion_client as nillion
from py_nillion_client import UserKey, NodeKey
from nillion_python_helpers import get_quote_and_pay, create_nillion_client, create_payments_config
from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.keypairs import PrivateKey
import uuid  
import redis
import json
from typing import List, Optional
from psycopg2 import pool

load_dotenv()

# Nillion Testnet Config
nillion_testnet_default_config = {
    "cluster_id": 'b13880d3-dde8-4a75-a171-8a1a9d985e6c',
    "grpc_endpoint": 'https://testnet-nillion-grpc.lavenderfive.com',
    "chain_id": 'nillion-chain-testnet-1',
    "bootnodes": ['/dns/node-1.testnet-photon.nillion-network.nilogy.xyz/tcp/14111/p2p/12D3KooWCfFYAb77NCjEk711e9BVe2E6mrasPZTtAjJAPtVAdbye']
}

# User id for a user key seeded with "public"
PUBLIC_USER_SEED = "public"
USER_ID_PUBLIC_SEED = "32HBC8A6ukxwL7B7K2fYcBHqiG5xy4sdLbME7MXmYB7pedooQwu2rgYUrT8nAVzrsEYuviRdcN5Hpb3ZJYcd25kL"
default_secret_name = "confession"

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

app = FastAPI()

# environment variable for frontend url
allowed_origin = os.getenv("ALLOWED_ORIGIN")
origins = [
    "http://localhost:3000",
    "http://localhost:3001"
]

if allowed_origin:
    origins.append(allowed_origin)  # Add the environment variable if it exists

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a connection pool
db_pool = pool.SimpleConnectionPool(1, 20, dsn=os.getenv("POSTGRESQL_URL"))

# Database connection
def get_db_connection():
    connection = db_pool.getconn()
    try:
        yield connection
    finally:
        db_pool.putconn(connection)  # Return the connection to the pool

# Create a Redis connection pool
redis_pool = redis.ConnectionPool.from_url(os.getenv("REDIS_URL"))

# Redis connection pool
def get_redis_client():
    redis_client = redis.Redis(connection_pool=redis_pool)
    try:
        yield redis_client
    finally:
        pass

# Pydantic models
class UserCreate(BaseModel):
    nillion_seed: str = "user"

class TopicCreate(BaseModel):
    name: str = "my_topic"

class SecretCreate(BaseModel):
    nillion_seed: str ="user"
    nillion_secret: str = "my super secret confession"
    secret_name: Optional[str] = "confession"
    topics: List[int] = [1]

class SecretItem(BaseModel):
    id: int
    nillion_user_id: str  
    store_id: str
    created_at: str 
    secret_name: str

class UserResponse(BaseModel):
    id: int

class TopicResponse(BaseModel):
    topic_id: int

class SecretResponse(BaseModel):
    secret_id: int
    store_id: str

class SecretItem(BaseModel):
    id: int
    nillion_user_id: str 
    store_id: str
    created_at: str
    secret_name: str

class SecretsResponse(BaseModel):
    total_count: int
    secrets: List[SecretItem]

class TopicSecretsCountResponse(BaseModel):
    total_secrets_for_topic: int

class SecretCountResponse(BaseModel):
    total_secrets: int

class UserListItem(BaseModel):
    id: int
    nillion_user_id: str

class UserListResponse(BaseModel):
    users: List[UserListItem]

class TopicItem(BaseModel):
    id: int
    name: str

class TopicsResponse(BaseModel):
    topics: List[TopicItem]

class TotalUsersResponse(BaseModel):
    total_users: int

class TotalUsersWithSecretsResponse(BaseModel):
    total_users_with_secrets: int

class SecretRetrieveResponse(BaseModel):
    store_id: str
    secret: str  # Adjust the type if the secret structure is more complex

class WalletInfoResponse(BaseModel):
    nillion_address: str

# Base response model
class BaseSecretsResponse(BaseModel):
    total_count: int
    secrets: List[SecretItem]

class SecretsResponseWithTopic(BaseSecretsResponse):
    topic_name: str  

# API routes
@app.post("/api/user", response_model=UserResponse)
async def create_user(user: UserCreate, connection=Depends(get_db_connection)):
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
    return UserResponse(id=user_id)

@app.get("/api/users", response_model=UserListResponse)
async def get_users(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, nillion_user_id FROM users;")
        users = cursor.fetchall()
    return UserListResponse(users=[UserListItem(id=user[0], nillion_user_id=user[1]) for user in users])

@app.post("/api/topic", response_model=TopicResponse)
async def create_topic(topic: TopicCreate, connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO topics (name) VALUES (%s) RETURNING id;", (topic.name,))
        topic_id = cursor.fetchone()[0]

        # Create a new table for the topic's secret count
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS topic_{topic_id}_secret_count (
                total_records INT NOT NULL DEFAULT 0
            );
        """)
        cursor.execute(f"INSERT INTO topic_{topic_id}_secret_count (total_records) VALUES (0);")

    connection.commit()
    return TopicResponse(topic_id=topic_id)

@app.post("/api/secret", response_model=SecretResponse)
async def create_secret(secret: SecretCreate, connection=Depends(get_db_connection)):
    userkey = UserKey.from_seed(secret.nillion_seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    nillion_user_id = client.user_id

    new_secret = nillion.NadaValues(
        {
            secret.secret_name: nillion.SecretBlob(bytearray(secret.nillion_secret.encode('utf-8')))
        }
    )

    permissions = nillion.Permissions.default_for_user(nillion_user_id)
    permissions.add_retrieve_permissions(set([USER_ID_PUBLIC_SEED]))
    memo_store_values = f"petnet operation: store_values; name: {secret.secret_name}; user_id: {nillion_user_id}"

    try:
        receipt_store = await get_quote_and_pay(
            client,
            nillion.Operation.store_values(new_secret, ttl_days=5),
            payments_wallet,
            payments_client,
            nillion_testnet_default_config["cluster_id"],
            memo_store_values,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quote failed for store values: {str(e)}")

    try:
        store_id = await client.store_values(
            nillion_testnet_default_config["cluster_id"], new_secret, permissions, receipt_store
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store values in the client: {str(e)}")

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
        user = cursor.fetchone()
        
        if user is None:
            cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))

        cursor.execute("INSERT INTO secrets (nillion_user_id, store_id, secret_name) VALUES (%s, %s, %s) RETURNING id;", (nillion_user_id, store_id, secret.secret_name))
        secret_id = cursor.fetchone()[0]
        
        cursor.execute("UPDATE secret_count SET total_records = total_records + 1;")
        
        for topic_id in secret.topics:
            cursor.execute("INSERT INTO secret_topics (secret_id, topic_id) VALUES (%s, %s);", (secret_id, topic_id))
            cursor.execute(f"UPDATE topic_{topic_id}_secret_count SET total_records = total_records + 1;")

    connection.commit()
    return SecretResponse(secret_id=secret_id, store_id=store_id)

@app.get("/api/topics", response_model=TopicsResponse)
async def get_topics(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM topics;")
        topics = cursor.fetchall()
    return TopicsResponse(topics=[TopicItem(id=topic[0], name=topic[1]) for topic in topics])

@app.get("/api/users/count", response_model=TotalUsersResponse)
async def get_total_users(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users;")
        total_users = cursor.fetchone()[0]
    return TotalUsersResponse(total_users=total_users)

@app.get("/api/users/with_secrets/count", response_model=TotalUsersWithSecretsResponse)
async def get_users_with_secrets_count(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(DISTINCT nillion_user_id) FROM secrets;")
        total_users_with_secrets = cursor.fetchone()[0]
    return TotalUsersWithSecretsResponse(total_users_with_secrets=total_users_with_secrets)

@app.get("/api/secrets", response_model=SecretsResponse)
async def get_secrets(page: int = 1, page_size: int = 10, connection=Depends(get_db_connection)):
    total_count_response = await get_secret_count(connection)
    total_count = total_count_response.total_secrets 

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, nillion_user_id, store_id, created_at, secret_name
            FROM secrets 
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
        """, (page_size, (page - 1) * page_size))
        secrets = cursor.fetchall()

    return SecretsResponse(
        total_count=total_count,
        secrets=[SecretItem(id=secret[0], nillion_user_id=str(secret[1]), store_id=secret[2], created_at=secret[3].isoformat(), secret_name=secret[4]) for secret in secrets]
    )

@app.get("/api/secrets/topic/{topic_id}", response_model=SecretsResponseWithTopic)
async def get_secrets_by_topic(topic_id: int, page: int = 1, page_size: int = 10, connection=Depends(get_db_connection)):
    total_count_response = await get_secret_count_by_topic(topic_id, connection)
    total_secrets_for_topic = total_count_response.total_secrets_for_topic

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.id, s.nillion_user_id, s.store_id, s.created_at, s.secret_name, t.name AS topic_name
            FROM secrets s
            JOIN secret_topics st ON s.id = st.secret_id
            JOIN topics t ON st.topic_id = t.id
            WHERE st.topic_id = %s
            ORDER BY s.created_at DESC
            LIMIT %s OFFSET %s;
        """, (topic_id, page_size, (page - 1) * page_size))
        secrets = cursor.fetchall()

    topic_name = secrets[0][5] if secrets else None  
    return SecretsResponseWithTopic(
        total_count=total_secrets_for_topic,
        secrets=[
            SecretItem(
                id=secret[0],
                nillion_user_id=str(secret[1]), 
                store_id=secret[2],
                created_at=secret[3].isoformat(),
                secret_name=secret[4]
            ) for secret in secrets
        ],
        topic_name=topic_name  # Include the topic name in the response
    )

@app.get("/api/secret/retrieve/{store_id}", response_model=SecretRetrieveResponse)
async def get_secret_by_store_id(store_id: str, secret_name: str = default_secret_name, redis_client=Depends(get_redis_client)):

    redis_key = f"secret:{store_id}:{secret_name}"
    cached_secret = redis_client.get(redis_key)
    if cached_secret:
        print(f"got from redis: {redis_key}")
        secret_data = json.loads(cached_secret)
        return SecretRetrieveResponse(store_id=store_id, secret=secret_data)

    try:
        seed = PUBLIC_USER_SEED
        userkey = UserKey.from_seed(seed)
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

    retrieved_secret = result[1].value.decode('utf-8')
    
    cache_expiry = 3600 * 24  # expire after 1 day
    redis_client.set(redis_key, json.dumps(retrieved_secret), ex=cache_expiry)
    
    return SecretRetrieveResponse(store_id=store_id, secret=retrieved_secret)

@app.get("/api/wallet", response_model=WalletInfoResponse)
def get_wallet_info():
    wallet_address = payments_wallet.address() 
    return WalletInfoResponse(nillion_address=str(wallet_address))

@app.get("/api/secret/count", response_model=SecretCountResponse)
async def get_secret_count(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT total_records FROM secret_count;")
        result = cursor.fetchone()
        
        if result is None:
            cursor.execute("INSERT INTO secret_count (total_records) VALUES (0);")
            connection.commit()  
            total_records = 0
        else:
            total_records = result[0]
    
    return SecretCountResponse(total_secrets=total_records)

@app.get("/api/secrets/synccount")
async def sync_secret_count(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        # Get the current count of secrets
        cursor.execute("SELECT COUNT(*) FROM secrets;")
        current_count = cursor.fetchone()[0]

        # Update the total_records in the secret_count table
        cursor.execute("UPDATE secret_count SET total_records = %s;", (current_count,))
        connection.commit()

    return {"total_secrets_synced": current_count}

@app.get("/api/secret/count/topic/{topic_id}", response_model=TopicSecretsCountResponse)
async def get_secret_count_by_topic(topic_id: int, connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        # Query the total_records from the topic's secret count table
        cursor.execute(f"SELECT total_records FROM topic_{topic_id}_secret_count;")
        result = cursor.fetchone()
        
        if result is None:
            # If no record exists, initialize it
            cursor.execute(f"INSERT INTO topic_{topic_id}_secret_count (total_records) VALUES (0);")
            connection.commit()
            total_records = 0
        else:
            total_records = result[0]
    
    return TopicSecretsCountResponse(total_secrets_for_topic=total_records)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
