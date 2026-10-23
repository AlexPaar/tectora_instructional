# Keycloak

Start the service `keycloak` in [docker-compose.yml](..\docker-compose.yml).

The `KEYCLOAK_PERM_ADMIN_PASSWORD` is defined in [.env](...env).

The ephemeral service `keycloak-init` in [docker-compose.yml](..\docker-compose.yml) provisions Keycloak entities as in [init-keycloak.sh](../init-keycloak.sh).

```bash
docker compose up
```

## Configure Keycloak as follows

### In realm `tectora`, create the client `langgraph-app` with the following client configuration settings

- Client type: OpenID Connect
- Client ID: langgraph-app
- Name: LangGraph App
- Description: LangGraph Application

- Client Authentication: Off
- Authentication flow: Standard flow
- Direct access grants: On
- Require PKCE: On
- PKCE Method: S256

- Valid redirect URIs:
  - [http://localhost:3000/\*](http://localhost:3000/*)
  - [http://localhost:3001/\*](http://localhost:3001/*)
  - [http://tectora.org/\*](http://tectora.org/*)
- Web origins: "+" and "\*"

### Roles in client "langgraph-app"

- Role name: langgraph-app-user
- Description: LangGraph App User

### Realm Roles

- Role name: user
- Description: User

Assign the associated client role "langgraph-app-user" to realm role "user".

### Groups

- Name: madwest-community-college
- Description: Madwest Community College

Assign the realm role `user` to the realm group `madwest-community-college`.

### Mapper

For the client `langgraph-app` and its assigned client scope `langgraph-app-dedicated`, add a mapper by configuration for the mapping `Group Membership`. The `Name` of the mapper should be `groups` and the `Token Claim Name` should be `groups`.

### Users

- Username: alice
- Password: `1234,`
- Email: [alice@example.org](alice@example.org)
- First Name: Alice
- Last Name: Albatross
- Email verified: On

Join group `madwest-community-college`.

### Add a secret key attribute to the group `madwest-community-college`

- Key: litellm_sk
- Value: sk-madwest-community-college

### Map the group attribute to the access token

For the client `langgraph-app` and its assigned client scope `langgraph-app-dedicated`, add a mapper by configuration for the mapping `User Attribute`.

- Mapper type: User Attribute
- Name: litellm_sk
- User Attribute: litellm_sk
- Token Claim Name: litellm_sk
- Claim JSON Type: String

- Add to ID token: Off
- Add to access token: On
- Add to lightweight access token: Off
- Add to userinfo: On
- Add to token introspection: On
- Multivalued: Off
- Aggregate attribute values: Off
