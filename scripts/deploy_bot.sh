#!/bin/bash
# deploy_bot.sh — Deploy bot update naar sandbox en/of prod
#
# Gebruik:
#   ./scripts/deploy_bot.sh sandbox
#   ./scripts/deploy_bot.sh prod
#   ./scripts/deploy_bot.sh both
#
# Vereisten: SSH key in ~/.ssh/kaironis_sandbox en ~/.ssh/kaironis_prod

set -euo pipefail

TARGET="${1:-both}"
BRANCH="feature/memory-query-and-reflection"

deploy_to() {
    local name="$1"
    local host="$2"
    local port="$3"
    local key="$4"

    echo ""
    echo "=== Deploying naar $name ($host:$port) ==="

    ssh -i "$key" -p "$port" -o StrictHostKeyChecking=no kaironis@"$host" bash << 'REMOTE'
        set -euo pipefail
        cd /opt/kaironis || { echo "ERROR: /opt/kaironis niet gevonden"; exit 1; }

        echo "[1/4] Git pull..."
        git fetch origin
        git checkout feature/memory-query-and-reflection
        git pull origin feature/memory-query-and-reflection

        echo "[2/4] Dependencies installeren..."
        pip install asyncpg --quiet 2>/dev/null || true

        echo "[3/4] Database tabel aanmaken..."
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

        echo "[4/4] Bot herstarten..."
        if command -v systemctl &>/dev/null && systemctl is-active --quiet kaironis-bot 2>/dev/null; then
            sudo systemctl restart kaironis-bot
            echo "kaironis-bot service herstart"
        elif docker ps -q --filter name=kaironis-bot 2>/dev/null | grep -q .; then
            docker restart kaironis-bot
            echo "kaironis-bot container herstart"
        else
            echo "WARN: Geen bekende bot process gevonden om te herstarten"
            echo "Herstart de bot handmatig"
        fi

        echo "=== Deploy klaar ==="
REMOTE
    echo "✅ $name deploy succesvol"
}

case "$TARGET" in
    sandbox)
        deploy_to "sandbox" "72.61.167.71" "2847" "~/.ssh/kaironis_sandbox"
        ;;
    prod)
        deploy_to "prod" "82.29.173.111" "2847" "~/.ssh/kaironis_prod"
        ;;
    both)
        deploy_to "sandbox" "72.61.167.71" "2847" "~/.ssh/kaironis_sandbox"
        deploy_to "prod" "82.29.173.111" "2847" "~/.ssh/kaironis_prod"
        ;;
    *)
        echo "Gebruik: $0 [sandbox|prod|both]"
        exit 1
        ;;
esac

echo ""
echo "Verificeer met: /status, /ask test, /note test, /notes"
