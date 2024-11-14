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

url = os.getenv("POSTGRESQL_URL")
connection = psycopg2.connect(url)

with connection:
    with connection.cursor() as cursor:
        cursor.execute(CREATE_APPS_TABLE)
        cursor.execute(CREATE_USERS_TABLE)
