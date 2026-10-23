# Tectora 🏛️ - The Agentic Fabric for Research Data

```text
  _____         _
 |_   _|__  ___| |_ ___  _ _ __ _
   | |/ -_)/ _|  _/ _ \| '_/ _` | 🏛️
   |_|\___|\__|\__\___/|_| \__,_|

   The Agentic Fabric for Research Data
   [tectora.org] • [v0.1.0-alpha]
```

## API Keys

Create API keys on the following platforms.

- [LangSmith](https://smith.langchain.com/)
- [OpenAI](https://platform.openai.com/api-keys)
- [Anthropic](https://platform.claude.com/settings/keys)
- [Hugging Face](https://huggingface.co/settings/tokens)
- [OpenWeather](https://home.openweathermap.org/api_keys)
- [GitHub](https://github.com/settings/personal-access-tokens)

## Conventions

### rich

With [rich](https://pypi.org/project/rich/), use the following styles:

- INFORMATION: `[dim]`
- ERROR: `[yellow]`
- SUCCESS: `[bold green]`
- BYE: `[bold blue]`

## Components

- [PostgreSQL](./docs/postgresql.md)
- [Redis](./docs/redis.md)
- [MongoDB Atlas](./docs/mongodb.md)
- [Keycloak](./docs/keycloak.md)
- [LiteLLM](./docs/litellm.md)
- [Open WebUI](./docs/open-webui.md)

## Running the Agent

### CLI Agent

Start the agent from the command line.

```bash
python agent.py
```

### LangGraph Dev and Agent Chat UI

Start the LangGraph local development server.

- Runs directly as a single process in your local environment.
- Hot Reloading: Automatically updates and reloads your agent code as you make changes.
- Local Storage: Persists state and checkpoint data directly to a local directory (.langgraph_api).
- Studio Integration: Connects seamlessly to LangGraph Studio for visual debugging, tracing, and interacting with your agent graphs in real time.
- Fast Startup: Launches quickly to accelerate the active development loop.

The `langgraph dev` default port is `2024`.

```bash
langgraph dev --config langgraph.json --allow-blocking --no-browser --debug-port 5678
```

Start [Agent Chat UI](https://docs.langchain.com/oss/python/langchain/ui).

```bash
git clone https://github.com/langchain-ai/agent-chat-ui.git
cd agent-chat-ui
pnpm install
pnpm dev
```

## Self-hosting the Agent

The agent can be self-hosted with the LangGraph API server, PostgreSQL, and Redis. The
Compose file starts PostgreSQL and Redis, while `langgraph build` creates the API server
image from [graphs/langgraph.json](./graphs/langgraph.json).

### Prerequisites

- Docker Desktop with Docker Compose
- Python 3.11 or newer
- The LangGraph CLI

Install the CLI with the in-memory development extra:

```bash
pip install -U "langgraph-cli[inmem]"
```

The project dependencies are declared in [pyproject.toml](./pyproject.toml). Keep the
existing `.env` file available in the project root because Docker Compose uses it for
passwords and agent environment variables.

### Build the Agent Server image

Run this command from the Tectora project root:

```bash
langgraph build -c graphs/langgraph.json -t tectora:latest
```

The graph registered as `agent` in `graphs/langgraph.json` is included in the image. The
exported graph does not need an application-owned checkpointer; the Agent Server injects
its PostgreSQL-backed checkpointer at runtime.

### Start the self-hosted stack

Start the built image with the PostgreSQL and Redis services:

```bash
docker compose up -d
```

The LangGraph API is available at `http://localhost:8123`. Check that the Agent Server is ready:

```bash
curl http://localhost:8123/ok
```

Expected response:

```json
{ "ok": true }
```

View service logs with:

```bash
docker compose logs -f langgraph
```

The Docker Compose service passes `DATABASE_URI` to the Agent Server for PostgreSQL metadata,
threads, runs, stores, and checkpoints. `REDIS_URI` configures Redis for task queueing
and streaming. Use the `agent` graph ID when calling the API or connecting Agent Chat UI.

### Stop the stack

```bash
docker compose down
```

Add `--volumes` when you want to delete the local PostgreSQL and Redis data volumes.
