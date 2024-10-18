import os
import psycopg2
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import py_nillion_client as nillion
from py_nillion_client import UserKey, NodeKey
from nillion_python_helpers import get_quote_and_pay, create_nillion_client, create_payments_config
from cosmpy.aerial.client import LedgerClient
from cosmpy.aerial.wallet import LocalWallet
from cosmpy.crypto.keypairs import PrivateKey
import uuid  

load_dotenv()

# use the Nillion Testnet Config: https://docs.nillion.com/network-configuration#testnet
nillion_testnet_default_config = {
    "cluster_id": 'b13880d3-dde8-4a75-a171-8a1a9d985e6c',
    "grpc_endpoint": 'https://testnet-nillion-grpc.lavenderfive.com',
    "chain_id": 'nillion-chain-testnet-1',
    "bootnodes": ['/dns/node-1.testnet-photon.nillion-network.nilogy.xyz/tcp/14111/p2p/12D3KooWCfFYAb77NCjEk711e9BVe2E6mrasPZTtAjJAPtVAdbye']
}

# user id for a user key seeded with "public"
# This user is granted retrieve permission to the secret confessions stored
PUBLIC_USER_SEED = "public"
USER_ID_PUBLIC_SEED = "32HBC8A6ukxwL7B7K2fYcBHqiG5xy4sdLbME7MXmYB7pedooQwu2rgYUrT8nAVzrsEYuviRdcN5Hpb3ZJYcd25kL"
default_secret_name = "confession"

# Create 1 payments config, client and wallet to use for any payments made to the network by the api
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

CREATE_USERS_TABLE = (
    "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, nillion_user_id TEXT NOT NULL);"
)

CREATE_TOPICS_TABLE = (
    "CREATE TABLE IF NOT EXISTS topics (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"
)

CREATE_SECRETS_TABLE = (
    """CREATE TABLE IF NOT EXISTS secrets (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL,
        store_id TEXT NOT NULL,
        secret_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );"""
)

CREATE_SECRET_TOPICS_TABLE = (
    """CREATE TABLE IF NOT EXISTS secret_topics (
        secret_id INTEGER NOT NULL,
        topic_id INTEGER NOT NULL,
        PRIMARY KEY (secret_id, topic_id),
        FOREIGN KEY(secret_id) REFERENCES secrets(id) ON DELETE CASCADE,
        FOREIGN KEY(topic_id) REFERENCES topics(id) ON DELETE CASCADE
    );"""
)

url = os.getenv("POSTGRESQL_URL")
connection = psycopg2.connect(url)

app = Flask(__name__)

with connection:
    with connection.cursor() as cursor:
        cursor.execute(CREATE_USERS_TABLE)
        cursor.execute(CREATE_TOPICS_TABLE)
        cursor.execute(CREATE_SECRETS_TABLE)
        cursor.execute(CREATE_SECRET_TOPICS_TABLE)

# create a new user
@app.post("/api/user")
def create_user():
    data = request.get_json()
    seed =  data["nillion_seed"]
    userkey = UserKey.from_seed(seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    nillion_user_id = client.user_id
    print("NEW USER", seed, nillion_user_id)

    with connection:
        with connection.cursor() as cursor:
            # Check if the nillion_user_id already exists
            cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
            user = cursor.fetchone()

            if user is None:
                # Insert the new user only if it doesn't exist
                cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))
                user_id = cursor.fetchone()[0]
            else:
                user_id = user[0]  # Get the existing user_id

    return jsonify({"id": user_id, }), 201

# retrieve all users
@app.get("/api/users")
def get_users():
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, nillion_user_id FROM users;")
            users = cursor.fetchall()

    return jsonify([{"id": user[0], "nillion_user_id": user[1]} for user in users]), 200

# create a new topic
@app.post("/api/topic")
def create_topic():
    data = request.get_json()
    topic_name = data["name"]

    with connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO topics (name) VALUES (%s) RETURNING id;", (topic_name,))
            topic_id = cursor.fetchone()[0]

    return jsonify({"topic_id": topic_id}), 201

# create a new secret
@app.post("/api/secret")
async def create_secret():
    data = request.get_json()
    seed =  data["nillion_seed"]
    secret =  data["nillion_secret"]
    secret_name = data.get("secret_name", default_secret_name)  
    userkey = UserKey.from_seed(seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    nillion_user_id = client.user_id

    new_secret = nillion.NadaValues(
        {
            secret_name: nillion.SecretBlob(bytearray(secret.encode('utf-8')))
        }
    )

    permissions = nillion.Permissions.default_for_user(nillion_user_id)
    permissions.add_retrieve_permissions(set([USER_ID_PUBLIC_SEED]))
    memo_store_values = f"petnet operation: store_values; name: {secret_name}; user_id: {nillion_user_id}"

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
    topics = data.get("topics", [])

    with connection:
        with connection.cursor() as cursor:
            # Retrieve user_id based on nillion_user_id
            cursor.execute("SELECT id FROM users WHERE nillion_user_id = %s;", (nillion_user_id,))
            user = cursor.fetchone()
            
            if user is None:
                # If user doesn't exist, insert it into the users table
                cursor.execute("INSERT INTO users (nillion_user_id) VALUES (%s) RETURNING id;", (nillion_user_id,))
                user_id = cursor.fetchone()[0]  # Get the new user_id
            else:
                user_id = user[0]  # Get the existing user_id

            cursor.execute("INSERT INTO secrets (user_id, store_id, secret_name) VALUES (%s, %s, %s) RETURNING id;", (user_id, store_id, secret_name))
            secret_id = cursor.fetchone()[0]
            
            for topic_id in topics:
                cursor.execute("INSERT INTO secret_topics (secret_id, topic_id) VALUES (%s, %s);", (secret_id, topic_id))

    return jsonify({"secret_id": secret_id, "store_id": store_id}), 201

# retrieve all topics
@app.get("/api/topics")
def get_topics():
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM topics;")
            topics = cursor.fetchall()

    return jsonify([{"id": topic[0], "name": topic[1]} for topic in topics]), 200

# get the total number of users
@app.get("/api/users/count")
def get_total_users():
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM users;")
            total_users = cursor.fetchone()[0]

    return jsonify({"total_users": total_users}), 200

# get the count of users with secrets
@app.get("/api/users/with_secrets/count")
def get_users_with_secrets_count():
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(DISTINCT user_id) FROM secrets;")
            total_users_with_secrets = cursor.fetchone()[0]

    return jsonify({"total_users_with_secrets": total_users_with_secrets}), 200

# retrieve secrets with pagination
@app.get("/api/secrets")
def get_secrets():
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=10, type=int)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, user_id, store_id, created_at, secret_name
                FROM secrets 
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s;
            """, (page_size, (page - 1) * page_size))
            secrets = cursor.fetchall()

    return jsonify([{"id": secret[0], "user_id": secret[1], "store_id": secret[2], "created_at": secret[3],"secret_name": secret[4]} for secret in secrets]), 200

# retrieve secrets by topic with pagination
@app.get("/api/secrets/topic/<int:topic_id>")
def get_secrets_by_topic(topic_id):
    page = request.args.get('page', default=1, type=int)
    page_size = request.args.get('page_size', default=10, type=int)

    with connection:
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

    return jsonify([{"id": secret[0], "user_id": secret[1], "store_id": secret[2], "created_at": secret[3]} for secret in secrets]), 200

# Endpoint to retrieve a secret by store_id
@app.get("/api/secret/retrieve/<string:store_id>")
async def get_secret_by_store_id(store_id):
    seed =  PUBLIC_USER_SEED
    userkey = UserKey.from_seed(seed)
    nodekey = NodeKey.from_seed(str(uuid.uuid4()))
    client = create_nillion_client(userkey, nodekey, nillion_testnet_default_config["bootnodes"])
    data = request.get_json()
    if data:
        secret_name = data["secret_name"]
    else:
        secret_name = default_secret_name

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
        return jsonify({"error": f"Failed to retrieve secret with name: {secret_name}. Error {str(e)}"}), 500 

    return jsonify({
        "store_id":store_id,
        "secret": result[1].value.decode('utf-8')
    }), 200

# Endpoint to retrieve the wallet address currently funding these api calls
@app.get("/api/wallet")
def get_wallet_info():
    wallet_address = payments_wallet.address() 
    return jsonify({
        "nillion_address": str(wallet_address),
    }), 200
