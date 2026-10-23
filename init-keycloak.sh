#!/bin/sh
set -e

KEYCLOAK_URL="http://keycloak:8080"
KCADM="/opt/keycloak/bin/kcadm.sh"

# Temporary bootstrap credentials passed from environment
BOOTSTRAP_USER="${KC_BOOTSTRAP_ADMIN_USERNAME}"
BOOTSTRAP_PASS="${KC_BOOTSTRAP_ADMIN_PASSWORD}"

# Permanent admin credentials
PERM_ADMIN_USER="${KEYCLOAK_PERM_ADMIN_USERNAME}"
PERM_ADMIN_PASS="${KEYCLOAK_PERM_ADMIN_PASSWORD}"

REALM_NAME="tectora"

echo "Waiting for Keycloak to become ready at ${KEYCLOAK_URL}..."
until (exec 3<>/dev/tcp/keycloak/8080) 2>/dev/null; do
  sleep 2
done
echo "Keycloak is up."

# 1. Authenticate with initial bootstrap admin
echo "Logging in with bootstrap credentials..."
$KCADM config credentials \
  --server "${KEYCLOAK_URL}" \
  --realm master \
  --user "${BOOTSTRAP_USER}" \
  --password "${BOOTSTRAP_PASS}"

# 2. Create the permanent admin account in master realm (if it doesn't already exist)
echo "Checking if permanent admin '${PERM_ADMIN_USER}' exists..."
USER_ID=$($KCADM get users -r master -q username="${PERM_ADMIN_USER}" --fields id --format csv --noquotes 2>/dev/null || true)

if [ -z "$USER_ID" ]; then
  echo "Creating permanent admin '${PERM_ADMIN_USER}'..."
  $KCADM create users -r master \
    -s username="${PERM_ADMIN_USER}" \
    -s enabled=true
  
  # Set permanent password (temporary=false makes it permanent)
  $KCADM set-password -r master \
    --username "${PERM_ADMIN_USER}" \
    --new-password "${PERM_ADMIN_PASS}" \
    --temporary=false

  # Assign master realm 'admin' role
  $KCADM add-roles -r master \
    --uusername "${PERM_ADMIN_USER}" \
    --rolename admin
  
  echo "Permanent admin created and granted 'admin' role."
else
  echo "Permanent admin '${PERM_ADMIN_USER}' already exists. Skipping creation."
fi

# 3. Create the realm 'tectora' (if it doesn't exist)
echo "Checking if realm '${REALM_NAME}' exists..."
if $KCADM get realms/"${REALM_NAME}" > /dev/null 2>&1; then
  echo "Realm '${REALM_NAME}' already exists."
else
  echo "Creating realm '${REALM_NAME}'..."
  $KCADM create realms -s realm="${REALM_NAME}" -s enabled=true
  echo "Realm '${REALM_NAME}' successfully created."
fi

# 4. Create the client 'langgraph-app' (if it doesn't exist)
echo "Checking if client 'langgraph-app' exists..."
CLIENT_UUID=$($KCADM get clients -r "${REALM_NAME}" -q clientId=langgraph-app --fields id --format csv --noquotes 2>/dev/null || true)

if [ -z "$CLIENT_UUID" ]; then
  echo "Creating client 'langgraph-app'..."
  $KCADM create clients -r "${REALM_NAME}" -f - <<'EOF'
{
  "clientId": "langgraph-app",
  "name": "LangGraph App",
  "description": "LangGraph Application",
  "protocol": "openid-connect",
  "publicClient": true,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": true,
  "redirectUris": ["http://localhost:3000/*", "http://localhost:3001/*", "http://tectora.org/*"],
  "webOrigins": ["+", "*"],
  "attributes": {
    "pkce.code.challenge.method": "S256"
  }
}
EOF
  CLIENT_UUID=$($KCADM get clients -r "${REALM_NAME}" -q clientId=langgraph-app --fields id --format csv --noquotes)
  echo "Client 'langgraph-app' created."
else
  echo "Client 'langgraph-app' already exists. Skipping creation."
fi

# 5. Create client role 'langgraph-app-user' on client 'langgraph-app' (if it doesn't exist)
echo "Checking if client role 'langgraph-app-user' exists..."
if $KCADM get clients/"${CLIENT_UUID}"/roles/langgraph-app-user -r "${REALM_NAME}" > /dev/null 2>&1; then
  echo "Client role 'langgraph-app-user' already exists."
else
  echo "Creating client role 'langgraph-app-user'..."
  $KCADM create clients/"${CLIENT_UUID}"/roles -r "${REALM_NAME}" \
    -s name=langgraph-app-user \
    -s description="LangGraph App User"
fi

# 6. Create realm role 'user' (if it doesn't exist)
echo "Checking if realm role 'user' exists..."
if $KCADM get roles/user -r "${REALM_NAME}" > /dev/null 2>&1; then
  echo "Realm role 'user' already exists."
else
  echo "Creating realm role 'user'..."
  $KCADM create roles -r "${REALM_NAME}" \
    -s name=user \
    -s description="User"
fi

# 7. Assign client role 'langgraph-app-user' to realm role 'user' (composite role)
echo "Checking if realm role 'user' already includes client role 'langgraph-app-user'..."
if $KCADM get roles/user/composites -r "${REALM_NAME}" | grep -q '"name" : "langgraph-app-user"'; then
  echo "Client role 'langgraph-app-user' already assigned to realm role 'user'."
else
  echo "Assigning client role 'langgraph-app-user' to realm role 'user'..."
  $KCADM add-roles -r "${REALM_NAME}" \
    --rname user \
    --cclientid langgraph-app \
    --rolename langgraph-app-user
fi

# 8. Create group 'madwest-community-college' (if it doesn't exist)
echo "Checking if group 'madwest-community-college' exists..."
GROUP_ID=$($KCADM get groups -r "${REALM_NAME}" -q search=madwest-community-college --fields id --format csv --noquotes 2>/dev/null || true)

if [ -z "$GROUP_ID" ]; then
  echo "Creating group 'madwest-community-college'..."
  $KCADM create groups -r "${REALM_NAME}" -f - <<'EOF'
{
  "name": "madwest-community-college",
  "attributes": {
    "description": ["Madwest Community College"]
  }
}
EOF
  GROUP_ID=$($KCADM get groups -r "${REALM_NAME}" -q search=madwest-community-college --fields id --format csv --noquotes)
  echo "Group 'madwest-community-college' created."
else
  echo "Group 'madwest-community-college' already exists."
fi

# 9. Assign realm role 'user' to group 'madwest-community-college'
echo "Checking if group 'madwest-community-college' already has realm role 'user'..."
if $KCADM get-roles -r "${REALM_NAME}" --gid "${GROUP_ID}" | grep -q '"name" : "user"'; then
  echo "Realm role 'user' already assigned to group 'madwest-community-college'."
else
  echo "Assigning realm role 'user' to group 'madwest-community-college'..."
  $KCADM add-roles -r "${REALM_NAME}" \
    --gid "${GROUP_ID}" \
    --rolename user
fi

# 10. Add 'Group Membership' protocol mapper to the dedicated scope of client 'langgraph-app'
echo "Checking if protocol mapper 'groups' exists on client 'langgraph-app'..."
if $KCADM get clients/"${CLIENT_UUID}"/protocol-mappers/models -r "${REALM_NAME}" | grep -q '"name" : "groups"'; then
  echo "Protocol mapper 'groups' already exists."
else
  echo "Creating protocol mapper 'groups'..."
  $KCADM create clients/"${CLIENT_UUID}"/protocol-mappers/models -r "${REALM_NAME}" -f - <<'EOF'
{
  "name": "groups",
  "protocol": "openid-connect",
  "protocolMapper": "oidc-group-membership-mapper",
  "config": {
    "claim.name": "groups",
    "full.path": "false",
    "id.token.claim": "true",
    "access.token.claim": "true",
    "userinfo.token.claim": "true"
  }
}
EOF
fi

# 11. Create user 'alice' (if it doesn't exist) and add to group 'madwest-community-college'
echo "Checking if user 'alice' exists..."
USER_ID=$($KCADM get users -r "${REALM_NAME}" -q username=alice --fields id --format csv --noquotes 2>/dev/null || true)

if [ -z "$USER_ID" ]; then
  echo "Creating user 'alice'..."
  $KCADM create users -r "${REALM_NAME}" \
    -s username=alice \
    -s email=alice@example.org \
    -s firstName=Alice \
    -s lastName=Albatross \
    -s enabled=true \
    -s emailVerified=true

  USER_ID=$($KCADM get users -r "${REALM_NAME}" -q username=alice --fields id --format csv --noquotes)

  $KCADM set-password -r "${REALM_NAME}" \
    --username alice \
    --new-password "${USER_PASSWORD_ALICE}" \
    --temporary=false

  # -n skips the GET-before-PUT merge, which this join endpoint doesn't support
  $KCADM update users/"${USER_ID}"/groups/"${GROUP_ID}" -r "${REALM_NAME}" -n \
    -s realm="${REALM_NAME}" \
    -s userId="${USER_ID}" \
    -s groupId="${GROUP_ID}"

  echo "User 'alice' created and added to group 'madwest-community-college'."
else
  echo "User 'alice' already exists. Skipping creation."
fi

# 12. Add secret key attribute 'litellm_sk' to group 'madwest-community-college'
echo "Checking if group 'madwest-community-college' already has attribute 'litellm_sk'..."
if $KCADM get groups/"${GROUP_ID}" -r "${REALM_NAME}" | grep -q '"litellm_sk"'; then
  echo "Attribute 'litellm_sk' already set on group 'madwest-community-college'."
else
  echo "Setting attribute 'litellm_sk' on group 'madwest-community-college'..."
  $KCADM update groups/"${GROUP_ID}" -r "${REALM_NAME}" \
    -s 'attributes.litellm_sk=["sk-madwest-community-college"]'
fi

# 13. Add 'User Attribute' protocol mapper 'litellm_sk' to the dedicated scope of client 'langgraph-app'
echo "Checking if protocol mapper 'litellm_sk' exists on client 'langgraph-app'..."
if $KCADM get clients/"${CLIENT_UUID}"/protocol-mappers/models -r "${REALM_NAME}" | grep -q '"name" : "litellm_sk"'; then
  echo "Protocol mapper 'litellm_sk' already exists."
else
  echo "Creating protocol mapper 'litellm_sk'..."
  $KCADM create clients/"${CLIENT_UUID}"/protocol-mappers/models -r "${REALM_NAME}" -f - <<'EOF'
{
  "name": "litellm_sk",
  "protocol": "openid-connect",
  "protocolMapper": "oidc-usermodel-attribute-mapper",
  "config": {
    "user.attribute": "litellm_sk",
    "claim.name": "litellm_sk",
    "jsonType.label": "String",
    "id.token.claim": "false",
    "access.token.claim": "true",
    "lightweight.claim": "false",
    "userinfo.token.claim": "true",
    "introspection.token.claim": "true",
    "multivalued": "false",
    "aggregate.attrs": "false"
  }
}
EOF
fi

echo "Keycloak initialization finished successfully."
