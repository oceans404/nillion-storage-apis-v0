# Nillion Storage APIs

## Overview

These API wrappers provides an interface for storing and retrieving secrets while maintaining a persistent record of store IDs (secret locations on the Nillion network) through PostgreSQL. Only Store IDs and metadata are stored in the database -- secrets are stored on the Nillion Network Testnet. Check out [Quickstart.md](Quickstart.md) for a step-by-step usage guide.

Note: A Testnet wallet is used to fund Nillion operations for these Storage APIs, allowing users to interact with the APIs without needing to manage payments directly.

### System Flow

```mermaid
flowchart LR
    subgraph "Client Applications"
        C1[App ID: b4c2a1]
        C2[App ID: e9f3d5]
    end

    subgraph "APIs"
        API[Register App, Store Secret, Retrieve Secret, List Store IDs]
    end

    subgraph "PostgreSQL"
        PG1[(Store IDs for app id: b4c2a1)]
        PG2[(Store IDs for app id: e9f3d5)]
    end

    subgraph "Nillion Network"
        N1[Secret at store id: abc123]
        N2[Secret at store id: def456]
        N3[Secret at store id: ghi789]
    end

    C1 --> API
    C2 --> API
    API -->|by app_id| PostgreSQL
    API -->|by store_id| N1
    API -->|by store_id| N2
    API -->|by store_id| N3
```

## Features

- **Application Management**: Create and manage multiple apps
- **Store ID Tracking**: Maintain a database of all Store IDs with metadata like creation date and TTL
- **Secret Management**: Store and retrieve permissioned secrets on the Nillion Network Testnet
- **User Management**: Create Nillion User IDs from a user seed
- **Automatic TTL**: Secrets have a TTL and expire after 30 days (configurable)

## Architecture

- **FastAPI Backend**: High-performance async API framework
- **PostgreSQL**: Stores application metadata and Store IDs
- **Nillion Network**: Secure secret storage and computation platform

## API Endpoints

### Application Management

- `POST /api/apps/register` - Create a new application
- `GET /api/apps` - List all registered applications

### Secret Management

- `POST /api/apps/{app_id}/secrets` - Store a new secret
- `GET /api/apps/{app_id}/store_ids` - List Store IDs for an application
- `GET /api/secret/retrieve/{store_id}` - Retrieve a secret by Store ID

### User Management

- `POST /api/user` - Create a new user identity
- `GET /api/users` - List all registered users

### Wallet Management

- `GET /api/wallet` - Get Nillion wallet address

## Setup & Installation

### Prerequisites

- Python 3.11+
- PostgreSQL
- Nillion Network Account with funded wallet

### Environment Setup

1. Clone the repository

2. Create and activate virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure environment variables:

```bash
cp .env.example .env
```

Required environment variables:

```
POSTGRESQL_URL=postgresql://user:password@localhost:5432/dbname
NILLION_PRIVATE_KEY=your_funded_nillion_testnet_private_key
```

### Database Initialization

Use `python3 create_tables.py` to create the necessary tables (apps and users).

### Running the Service

Development mode:

```bash
uvicorn app:app --reload
```

Production mode:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Considerations

- Make sure your Nillion private key remains private and the corresponding wallet has sufficient funds: https://faucet.testnet.nillion.com/
- Review and set user permissions (by user id) when storing secrets
- Monitor TTL expirations for critical secrets

## Documentation

Interactive API documentation with complete request/response schemas is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Error Handling

The API uses standard HTTP status codes:

- `400`: Invalid request parameters
- `404`: Resource not found
- `500`: Internal server error

All error responses include a detail message explaining the issue.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License: MIT
