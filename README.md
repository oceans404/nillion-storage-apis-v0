# Blind Confessions App Flask APIs

## Description

Simple Flask APIs for managing secrets for the Confessions App.

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

- **`/api/secrets/topic/<int:topic_id>`**: Retrieves a paginated list of secrets associated with a specific topic ID.

- **`/api/secret/retrieve/<string:store_id>`**: Retrieves a secret by its store ID. Returns the store ID and the secret value.

- **`/api/wallet`**: Retrieves the wallet address currently funding the API calls.

## Getting Started

### Prerequisites

Install Python and Flask.

### Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. Create a virtual environment and install the required packages:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Copy the `.env.example` file to create your own `.env` file and add your own postgres db url and nilion private key

### Running the App

To start the application, run:

```bash
flask run
```

This will start the Flask server and allow you to access the API endpoints at http://127.0.0.1:5000/*

Optionally use the included Insomnia project file to test the API endpoints.
