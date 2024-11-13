import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

CREATE_APPS_TABLE = (
    """CREATE TABLE IF NOT EXISTS apps (
        id SERIAL PRIMARY KEY,
        app_id UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL
    );"""
)

CREATE_USERS_TABLE = (
    "CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, nillion_user_id TEXT UNIQUE NOT NULL);"
)

CREATE_TOPICS_TABLE = (
    "CREATE TABLE IF NOT EXISTS topics (id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL);"
)

# this table is used to store the secrets for a user with a default ttl of 30 days
CREATE_SECRETS_TABLE = (
    """CREATE TABLE IF NOT EXISTS secrets (
        id SERIAL PRIMARY KEY,
        nillion_user_id TEXT NOT NULL,
        store_id TEXT NOT NULL,
        secret_name TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        ttl_expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '30 days'),
        FOREIGN KEY(nillion_user_id) REFERENCES users(nillion_user_id) ON DELETE CASCADE
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

CREATE_SECRET_COUNT_TABLE = (
    """CREATE TABLE IF NOT EXISTS secret_count (
        total_records INT NOT NULL DEFAULT 0
    );"""
)

url = os.getenv("POSTGRESQL_URL")
connection = psycopg2.connect(url)

with connection:
    with connection.cursor() as cursor:
        cursor.execute(CREATE_APPS_TABLE)
        cursor.execute(CREATE_USERS_TABLE)
        cursor.execute(CREATE_TOPICS_TABLE)
        cursor.execute(CREATE_SECRETS_TABLE)
        cursor.execute(CREATE_SECRET_TOPICS_TABLE)
        cursor.execute(CREATE_SECRET_COUNT_TABLE)

        # cursor.execute("SELECT * FROM secrets;")
        # secrets = cursor.fetchall()
        # for secret in secrets:
        #     print(secret)
