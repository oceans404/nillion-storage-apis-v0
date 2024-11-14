# Nillion Storage APIs

## Description

FastAPI implementation of APIs for

- Creating applications (app id)
- Managing Nillion secrets for an app
- Retrieving Nillion Store IDs for an app
- Retrieving Nillion secret values by Store ID.

## API Endpoints

## Endpoints

### Register a New App ID

- **Method:** `POST`
- **Path:** `/api/apps/register`
- **Description:** Registers a new application and creates a table that will hold the app's store IDs.

### Create App Secret

- **Method:** `POST`
- **Path:** `/api/apps/{app_id}/secrets`
- **Description:** Creates a new secret for a specified app ID. Stores the resulting Store ID in the app's table.

### Get Store IDs for App

- **Method:** `GET`
- **Path:** `/api/apps/{app_id}/store_ids`
- **Description:** Retrieves all store IDs associated with a specified app ID, with pagination support.

### Retrieve Secret by Store ID

- **Method:** `GET`
- **Path:** `/api/secret/retrieve/{store_id}`
- **Description:** Retrieves a secret using its store ID.

### Get Wallet Info

- **Method:** `GET`
- **Path:** `/api/wallet`
- **Description:** Retrieves the Nillion address of the private key used by the app for reference in case it runs out of funds

### Create User

- **Method:** `POST`
- **Path:** `/api/user`
- **Description:** Creates a new user based on the provided Nillion seed. Helpful for checking what the user's Nillion User ID is for a given user seed.

### Get Users

- **Method:** `GET`
- **Path:** `/api/users`
- **Description:** Retrieves a list of all user ids.

## Error Handling

All endpoints return appropriate HTTP status codes and error messages in case of failure. Common status codes include:

- `400 Bad Request`: Invalid input.
- `404 Not Found`: Resource not found.
- `500 Internal Server Error`: Unexpected server error.

## Getting Started

### Prerequisites

- Python 3.11+
- PostgreSQL

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
- `NILLION_PRIVATE_KEY`: Your Nillion private key. This will be used to pay for any operations on the Nillion Testnet.

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
