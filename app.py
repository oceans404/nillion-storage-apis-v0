import os
import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
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

# Database connection
def get_db_connection():
    url = os.getenv("POSTGRESQL_URL")
    connection = psycopg2.connect(url)
    try:
        yield connection
    finally:
        connection.close()

# Redis connection
# Redis connection
def get_redis_client():
    redis_url = os.getenv("REDIS_URL")
    if redis_url is None:
        raise RuntimeError("REDIS_URL is not set in the .env file. Add your Redis URL to the .env file.")

    try:
        redis_client = redis.Redis.from_url(redis_url)
    except Exception as e:
        raise RuntimeError(f"Failed to connect to Redis: {str(e)}")
    try:
        yield redis_client
    finally:
        redis_client.close()

# Pydantic models
class UserCreate(BaseModel):
    nillion_seed: str

class UserResponse(BaseModel):
    id: int

class TopicCreate(BaseModel):
    name: str

class TopicResponse(BaseModel):
    topic_id: int

class SecretCreate(BaseModel):
    nillion_seed: str
    nillion_secret: str
    secret_name: Optional[str] = "confession"
    topics: List[int] = []

class SecretResponse(BaseModel):
    secret_id: int
    store_id: str

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

@app.get("/api/users")
async def get_users(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, nillion_user_id FROM users;")
        users = cursor.fetchall()
    return [{"id": user[0], "nillion_user_id": user[1]} for user in users]

@app.post("/api/topic", response_model=TopicResponse)
async def create_topic(topic: TopicCreate, connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO topics (name) VALUES (%s) RETURNING id;", (topic.name,))
        topic_id = cursor.fetchone()[0]
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

    receipt_store = await get_quote_and_pay(
        client,
        nillion.Operation.store_values(new_secret, ttl_days=5),
        payments_wallet,
        payments_client,
        nillion_testnet_default_config["cluster_id"],
        memo_store_values,
    )

    store_id = await client.store_values(
        nillion_testnet_default_config["cluster_id"], new_secret, permissions, receipt_store
    )

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
        user = cursor.fetchone()
        
        if user is None:
            cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))
            user_id = cursor.fetchone()[0]
        else:
            user_id = user[0]

        cursor.execute("INSERT INTO secrets (user_id, store_id, secret_name) VALUES (%s, %s, %s) RETURNING id;", (user_id, store_id, secret.secret_name))
        secret_id = cursor.fetchone()[0]
        
        for topic_id in secret.topics:
            cursor.execute("INSERT INTO secret_topics (secret_id, topic_id) VALUES (%s, %s);", (secret_id, topic_id))

    connection.commit()
    return SecretResponse(secret_id=secret_id, store_id=store_id)

@app.get("/api/topics")
async def get_topics(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM topics;")
        topics = cursor.fetchall()
    return [{"id": topic[0], "name": topic[1]} for topic in topics]

@app.get("/api/users/count")
async def get_total_users(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users;")
        total_users = cursor.fetchone()[0]
    return {"total_users": total_users}

@app.get("/api/users/with_secrets/count")
async def get_users_with_secrets_count(connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(DISTINCT user_id) FROM secrets;")
        total_users_with_secrets = cursor.fetchone()[0]
    return {"total_users_with_secrets": total_users_with_secrets}

@app.get("/api/secrets")
async def get_secrets(page: int = 1, page_size: int = 10, connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, user_id, store_id, created_at, secret_name
            FROM secrets 
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s;
        """, (page_size, (page - 1) * page_size))
        secrets = cursor.fetchall()
    return [{"id": secret[0], "user_id": secret[1], "store_id": secret[2], "created_at": secret[3], "secret_name": secret[4]} for secret in secrets]

@app.get("/api/secrets/topic/{topic_id}")
async def get_secrets_by_topic(topic_id: int, page: int = 1, page_size: int = 10, connection=Depends(get_db_connection)):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT s.id, s.user_id, s.store_id, s.created_at
            FROM secrets s
            JOIN secret_topics st ON s.id = st.secret_id
            WHERE st.topic_id = %s
            ORDER BY s.created_at DESC
            LIMIT %s OFFSET %s;
        """, (topic_id, page_size, (page - 1) * page_size))
        secrets = cursor.fetchall()
    return [{"id": secret[0], "user_id": secret[1], "store_id": secret[2], "created_at": secret[3]} for secret in secrets]

@app.get("/api/secret/retrieve/{store_id}")
async def get_secret_by_store_id(store_id: str, secret_name: str = default_secret_name, redis_client=Depends(get_redis_client)):
    seed = PUBLIC_USER_SEED
    userkey = UserKey.from_seed(seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])

    redis_key = f"secret:{store_id}:{secret_name}"
    cached_secret = redis_client.get(redis_key)
    if cached_secret:
        print(f"got from redis: {redis_key}")
        secret_data = json.loads(cached_secret)
        return {
            "store_id": store_id,
            "secret": secret_data
        }

    memo_retrieve_value = f"petnet operation: retrieve_value; name: {secret_name}; store_id: {store_id}"
    receipt_retrieve = await get_quote_and_pay(
        client,
        nillion.Operation.retrieve_value(),
        payments_wallet,
        payments_client,
        nillion_testnet_default_config["cluster_id"],
        memo_retrieve_value
    )

    try:
        result = await client.retrieve_value(
            nillion_testnet_default_config["cluster_id"], store_id, secret_name, receipt_retrieve
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve secret with name: {secret_name}. Error: {str(e)}")

    retrieved_secret = result[1].value.decode('utf-8')
    
    cache_expiry = 3600 * 24  # expire after 1 day
    redis_client.set(redis_key, json.dumps(retrieved_secret), ex=cache_expiry)
    
    return {
        "store_id": store_id,
        "secret": retrieved_secret
    }

@app.get("/api/wallet")
def get_wallet_info():
    wallet_address = payments_wallet.address() 
    return {
        "nillion_address": str(wallet_address),
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
