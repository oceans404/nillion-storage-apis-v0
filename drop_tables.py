import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("POSTGRESQL_URL")
connection = psycopg2.connect(url)

# SQL commands to drop the tables
DROP_USERS_TABLE = "DROP TABLE IF EXISTS users;"
DROP_TOPICS_TABLE = "DROP TABLE IF EXISTS topics;"
DROP_SECRETS_TABLE = "DROP TABLE IF EXISTS secrets;"
DROP_SECRET_TOPICS_TABLE = "DROP TABLE IF EXISTS secret_topics;"

tables_to_drop = [
    "users",
    "topics",
    "secrets",
    "secret_topics"
]

# Print the tables that would be dropped
print("The following tables will be dropped:")
for table in tables_to_drop:
    print(f"- {table}")

confirm = input("Are you sure you want to drop all specified tables? (yes/no): ")
if confirm.lower() == 'yes':
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(DROP_SECRET_TOPICS_TABLE)
            cursor.execute(DROP_SECRETS_TABLE)
            cursor.execute(DROP_TOPICS_TABLE)
            cursor.execute(DROP_USERS_TABLE)

    print("All specified tables have been dropped.")
else:
    print("Operation cancelled.")
