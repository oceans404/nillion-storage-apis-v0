# Blind Confessions App FastAPI APIs

## Description

FastAPI implementation of APIs for managing secrets for the Confessions App, integrating with Nillion for secure secret storage.

## API Endpoints

### POST Endpoints

- **`/api/user`**: Creates a new user with a Nillion seed. Returns the newly created user's ID.
- **`/api/topic`**: Creates a new topic with a specified name. Returns the ID of the newly created topic.
- **`/api/secret`**: Creates a new secret associated with a user. Requires a Nillion seed and the secret value. Returns the secret ID and store ID.

### GET Endpoints

- **`/api/users`**: Retrieves a list of all users, including their IDs and Nillion user IDs.
- **`/api/topics`**: Retrieves a list of all topics, including their IDs and names.
- **`/api/users/count`**: Returns the total number of users in the database.
- **`/api/users/with_secrets/count`**: Returns the count of users who have stored secrets.
- **`/api/secrets`**: Retrieves a paginated list of secrets, including their IDs, user IDs, store IDs, and creation timestamps.
- **`/api/secrets/topic/{topic_id}`**: Retrieves a paginated list of secrets associated with a specific topic ID.
- **`/api/secret/retrieve/{store_id}`**: Retrieves a secret by its store ID. Returns the store ID and the secret value.
- **`/api/wallet`**: Retrieves the wallet address currently funding the API calls.

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL
- Redis

### Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Create a virtual environment and activate it:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
   ```

3. Install the required packages:

   ```bash
   pip install -r requirements.txt
   ```

4. Copy the `.env.example` file to create your own `.env` file:

   ```bash
   cp .env.example .env
   ```

5. Edit the `.env` file and add your own environment variables:

- `POSTGRESQL_URL`: URL for your PostgreSQL database
- `REDIS_URL`: URL for your Redis instance
- `NILLION_PRIVATE_KEY`: Your Nillion private key

### Running the App

To start the application in development mode, run:

```bash
uvicorn app:app --reload
```

This will start the FastAPI development server and allow you to access the API endpoints at http://127.0.0.1:8000/

For production deployment, use a production ASGI server like Gunicorn with Uvicorn workers:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## API Documentation

FastAPI provides automatic interactive API documentation. Once the server is running, you can access interfaces and test all API endpoints directly from your browser:

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
