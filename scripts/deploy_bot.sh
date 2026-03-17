#!/bin/bash
# deploy_bot.sh — Deploy bot update to sandbox and/or prod
#
# Usage:
#   ./scripts/deploy_bot.sh sandbox
#   ./scripts/deploy_bot.sh prod
#   ./scripts/deploy_bot.sh both
#
# Requirements: SSH key in ~/.ssh/kaironis_sandbox and ~/.ssh/kaironis_prod
#               Server host keys must be pinned in ~/.ssh/known_hosts
#               Bootstrap: ssh-keyscan -p 2847 <host> >> ~/.ssh/known_hosts

set -euo pipefail

TARGET="${1:-both}"
# Use the BRANCH env-var if set, otherwise use the current git branch
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

deploy_to() {
    local name="$1"
    local host="$2"
    local port="$3"
    local key="$4"
    local compose_file="$5"

    echo ""
    echo "=== Deploying to $name ($host:$port) using $compose_file ==="

    # No StrictHostKeyChecking=no — host key must be pinned in known_hosts
    ssh -i "$key" -p "$port" kaironis@"$host" bash << REMOTE
        set -euo pipefail
        cd /opt/kaironis || { echo "ERROR: /opt/kaironis not found"; exit 1; }

        echo "[1/3] Git pull ($BRANCH)..."
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"

        echo "[2/3] Building and deploying Docker image..."
        docker compose -f "$compose_file" build --no-cache kaironis-bot
        docker compose -f "$compose_file" up -d kaironis-bot

        echo "[3/3] Initializing database schema..."
        docker compose -f "$compose_file" exec -T kaironis-bot python3 -c "
import asyncio, os, sys
sys.path.insert(0, '/opt/kaironis')
from src.memory.reflection import ReflectionLog

async def main():
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print('WARN: DATABASE_URL not set, skipping schema init')
        return
    log = ReflectionLog(dsn=dsn)
    await log.initialize()
    await log.close()
    print('Schema created/verified')

asyncio.run(main())
"

        echo "=== Deploy complete ==="
REMOTE
    echo "✅ $name deploy successful"
}

case "$TARGET" in
    sandbox)
        deploy_to "sandbox" "<sandbox-vps>" "2847" "$HOME/.ssh/kaironis_sandbox" "docker/docker-compose.sandbox.yaml"
        ;;
    prod)
        deploy_to "prod" "<prod-vps>" "2847" "$HOME/.ssh/kaironis_prod" "docker/docker-compose.prod.yaml"
        ;;
    both)
        deploy_to "sandbox" "<sandbox-vps>" "2847" "$HOME/.ssh/kaironis_sandbox" "docker/docker-compose.sandbox.yaml"
        deploy_to "prod" "<prod-vps>" "2847" "$HOME/.ssh/kaironis_prod" "docker/docker-compose.prod.yaml"
        ;;
    *)
        echo "Usage: $0 [sandbox|prod|both]"
        exit 1
        ;;
esac

echo ""
echo "Verify with: /status, /ask test, /note test, /notes"
