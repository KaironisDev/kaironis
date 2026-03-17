#!/bin/bash
# deploy_bot.sh — Deploy bot update naar sandbox en/of prod
#
# Gebruik:
#   ./scripts/deploy_bot.sh sandbox
#   ./scripts/deploy_bot.sh prod
#   ./scripts/deploy_bot.sh both
#
# Vereisten: SSH key in ~/.ssh/kaironis_sandbox en ~/.ssh/kaironis_prod
#            Hostkeys van de servers moeten gepind zijn in ~/.ssh/known_hosts
#            Bootstrap: ssh-keyscan -p 2847 <host> >> ~/.ssh/known_hosts

set -euo pipefail

TARGET="${1:-both}"
# Gebruik de BRANCH env-var als die gezet is, anders de huidige git-branch
BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"

deploy_to() {
    local name="$1"
    local host="$2"
    local port="$3"
    local key="$4"

    echo ""
    echo "=== Deploying naar $name ($host:$port) ==="

    # Geen StrictHostKeyChecking=no — hostkey moet gepind zijn in known_hosts
    ssh -i "$key" -p "$port" kaironis@"$host" bash << REMOTE
        set -euo pipefail
        cd /opt/kaironis || { echo "ERROR: /opt/kaironis niet gevonden"; exit 1; }

        echo "[1/3] Git pull ($BRANCH)..."
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"

        echo "[2/3] Docker image bouwen en deployen..."
        docker compose -f docker/docker-compose.sandbox.yaml build --no-cache kaironis-bot
        docker compose -f docker/docker-compose.sandbox.yaml up -d kaironis-bot

        echo "[3/3] Database tabel aanmaken..."
        python3 - << 'PYEOF'
import asyncio, os, sys
sys.path.insert(0, '/opt/kaironis')
from src.memory.reflection import ReflectionLog

async def main():
    dsn = os.getenv('DATABASE_URL')
    if not dsn:
        print("WARN: DATABASE_URL niet ingesteld, tabel aanmaken overgeslagen")
        return
    log = ReflectionLog(dsn=dsn)
    await log.initialize()
    await log.close()
    print("Tabel aangemaakt/geverifieerd")

asyncio.run(main())
PYEOF

        echo "=== Deploy klaar ==="
REMOTE
    echo "✅ $name deploy succesvol"
}

case "$TARGET" in
    sandbox)
        deploy_to "sandbox" "72.61.167.71" "2847" "$HOME/.ssh/kaironis_sandbox"
        ;;
    prod)
        deploy_to "prod" "82.29.173.111" "2847" "$HOME/.ssh/kaironis_prod"
        ;;
    both)
        deploy_to "sandbox" "72.61.167.71" "2847" "$HOME/.ssh/kaironis_sandbox"
        deploy_to "prod" "82.29.173.111" "2847" "$HOME/.ssh/kaironis_prod"
        ;;
    *)
        echo "Gebruik: $0 [sandbox|prod|both]"
        exit 1
        ;;
esac

echo ""
echo "Verificeer met: /status, /ask test, /note test, /notes"
