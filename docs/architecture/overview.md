# Kaironis — Architectuur Overzicht

**Laatste update:** 2026-03-12

---

## Systeem Overzicht

```
┌─────────────────────────────────────────────────────┐
│                    PERRY (Operator)                   │
│    Telegram → @KaironisBot / @Kaironis_test_bot      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│              PROD VPS (82.29.173.111)                │
│                    32GB RAM                          │
│                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  Telegram   │  │   Trading   │  │   Memory    │  │
│  │     Bot     │  │   Engine    │  │   System    │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  │
│  ┌─────────────────────────────────────────────────┐ │
│  │  PostgreSQL │  Redis  │  ChromaDB               │ │
│  └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│             SANDBOX VPS (72.61.167.71)               │
│                    16GB RAM                          │
│  Development, testing, paper trading                 │
│                                                      │
│  Bestaande services (Hostinger):                     │
│  - n8n (workflow automatisering, poort 5678)         │
│  - Traefik (reverse proxy, poort 80/443)             │
│  - Ollama (lokaal LLM, poort 11434)                  │
│  - tct-trading-mcp-server (poort 3001)               │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│               GITHUB (KaironisDev/kaironis)          │
│  main ← develop ← feature branches                  │
│  CI/CD via GitHub Actions                            │
│  CodeRabbit code review (TODO)                       │
└─────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Laag | Technologie | Status |
|------|-------------|--------|
| Language | Python 3.11+ | ✅ Geïnstalleerd |
| Orchestration | n8n | ✅ Draait op sandbox |
| Bot Framework | python-telegram-bot | ✅ @KaironisBot (prod) + @Kaironis_test_bot (sandbox) |
| Vector DB | ChromaDB | ✅ Beide VPS — 1046 chunks prod, 1038+ sandbox |
| State DB | PostgreSQL 15 | ✅ Draait op sandbox |
| Cache | Redis 7 | ✅ Draait op sandbox |
| Containers | Docker + Compose | ✅ Beide VPS |
| CI/CD | GitHub Actions | 🔲 Pipeline aangemaakt, testen TODO |
| Code Review | CodeRabbit | 🔲 Te integreren |
| Reverse Proxy | Traefik | ✅ Draait op sandbox |
| Lokaal LLM | Ollama (nomic-embed-text) | ✅ Prod én sandbox |

---

## Repository Structuur

```
kaironis/
├── .github/workflows/    # CI/CD pipelines
├── soul/
│   ├── SOUL.md           # Identiteit (v1.2.0) — NIET wijzigen zonder goedkeuring
│   ├── permissions.yaml  # Autonomie grenzen
│   └── risk-limits.yaml  # Harde trading limieten
├── src/
│   ├── core/             # Agent loop, beslissingen
│   ├── memory/           # Vector store, state, learnings
│   ├── trading/
│   │   ├── tct/          # TCT kennisbank, signalen
│   │   └── engines/      # Broker integraties
│   ├── orchestration/    # Telegram bot, scheduler
│   └── utils/
├── tests/
│   ├── unit/             # 40% van tests
│   ├── integration/      # 45% van tests
│   └── e2e/              # 15% van tests
├── docker/
│   ├── docker-compose.dev.yaml   # Development
│   └── docker-compose.prod.yaml  # Productie (TODO)
├── n8n/workflows/        # Geëxporteerde n8n workflows
├── scripts/              # Setup, backup scripts
└── docs/                 # Documentatie (dit bestand)
```

---

## Broker Integraties (gepland)

| Broker | Markten | Type | Status |
|--------|---------|------|--------|
| Hyperliquid | Crypto perps (DEX) | REST + WebSocket | 🔲 Gepland |
| MEXC | Crypto spot/futures | REST + WebSocket | 🔲 Gepland |
| MetaTrader 5 | Forex, Indices, Commodities | Python API | 🔲 Gepland |
| Breakout Prop | Via MT5 | Prop firm account | 🔲 Gepland |

---

## Implementatie Fasen

| Fase | Beschrijving | Status |
|------|-------------|--------|
| 1 | Foundation — VPS, repo, CI/CD, Telegram bot | ✅ Klaar |
| 2 | Memory & Knowledge — ChromaDB, PDF processing | ✅ Grotendeels klaar (kennisbank gevuld, 1038–1046 chunks) |
| 3 | Trading Core — broker integraties, risk management | 🔲 |
| 4 | Pre-planning & Orchestration | 🔲 |
| 5 | Learning System | 🔲 |
| 6 | Validatie & Live trading | 🔲 |
