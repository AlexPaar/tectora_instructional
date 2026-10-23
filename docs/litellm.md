# LiteLLM

Start the service `litellm` in [docker-compose.yml](..\docker-compose.yml).

The `LITELLM_MASTER_KEY` and `LITELLM_SALT_KEY` are defined in [.env](...env).

The ephemeral service `litellm-init` in [docker-compose.yml](..\docker-compose.yml) provisions LiteLLM entities as in [init-litellm.sh](../init-litellm.sh).

```bash
docker compose up
```

Check out the [LiteLLM UI](http://localhost:4000/ui/).
