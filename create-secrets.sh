#!/bin/bash
mkdir -p secrets
echo "postgres_$(openssl rand -hex 16)" > secrets/postgres_password.txt
echo "redis_$(openssl rand -hex 16)" > secrets/redis_password.txt
echo "api_$(openssl rand -hex 32)" > secrets/api_auth_token.txt
echo "grafana_$(openssl rand -hex 16)" > secrets/grafana_password.txt
echo "https://discord.com/api/webhooks/your-webhook" > secrets/discord_webhook.txt
echo "https://hooks.slack.com/services/your-webhook" > secrets/slack_webhook.txt
chmod 600 secrets/*
echo "Secrets created in ./secrets/"
