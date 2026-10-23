#!/bin/bash
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE keycloak ENCODING 'UTF8';
    CREATE DATABASE litellm ENCODING 'UTF8';
    CREATE DATABASE langgraph ENCODING 'UTF8';
EOSQL
