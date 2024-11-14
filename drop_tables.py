import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("POSTGRESQL_URL")
connection = psycopg2.connect(url)

DROP_APPS_TABLE = "DROP TABLE IF EXISTS apps CASCADE;"
DROP_USERS_TABLE = "DROP TABLE IF EXISTS users CASCADE;"

tables_to_drop = [
    "users",
    "apps",
]

print("The following tables will be dropped:")
for table in tables_to_drop:
    print(f"- {table}")

confirm = input("Are you sure you want to drop all specified tables? (yes/no): ")
if confirm.lower() == 'yes':
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(DROP_USERS_TABLE)
            cursor.execute(DROP_APPS_TABLE)
    print("All specified tables have been dropped.")
else:
    print("Operation cancelled.")
