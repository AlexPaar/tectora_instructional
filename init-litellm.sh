#!/bin/sh
set -e

echo "Waiting for LiteLLM to respond..."

until curl -s -f http://litellm:4000/health/readiness > /dev/null 2>&1; do
  sleep 2
done

echo "LiteLLM is ready."

# Teams

echo "Provisioning teams..."

curl --location 'http://litellm:4000/team/new' \
--header "Content-Type: application/json" \
--header "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
--data '{
    "team_alias": "Development",
    "team_id": "development",
    "models": [
        "gpt-4o-mini",
        "claude-haiku-4-5",
        "text-embedding-3-small"
    ],
    "metadata": {
        "keycloak_group": "development"
    }
}'

curl --location 'http://litellm:4000/team/new' \
--header "Content-Type: application/json" \
--header "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
--data '{
    "team_alias": "Madwest Community College",
    "team_id": "madwest-community-college",
    "models": [
        "gpt-4o-mini",
        "claude-haiku-4-5",
        "text-embedding-3-small"
    ],
    "metadata": {
        "keycloak_group": "madwest-community-college"
    }
}'

printf "\n"

# Virtual Keys

echo "Provisioning virtual keys..."

curl --location 'http://litellm:4000/key/generate' \
--header "Content-Type: application/json" \
--header "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
--data "{
    \"key\": \"${SK_DEVELOPMENT}\",
    \"key_alias\": \"Development\",
    \"team_id\": \"development\",
    \"key_type\": \"llm_api\"
}"

curl --location 'http://litellm:4000/key/generate' \
--header "Content-Type: application/json" \
--header "Authorization: Bearer ${LITELLM_MASTER_KEY}" \
--data "{
    \"key\": \"${SK_MADWEST_COMMUNITY_COLLEGE}\",
    \"key_alias\": \"Madwest Community College\",
    \"team_id\": \"madwest-community-college\",
    \"key_type\": \"llm_api\"
}"

printf "\n"
