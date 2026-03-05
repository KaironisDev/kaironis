# Kaironis — Changelog

Elke significante wijziging wordt hier gedocumenteerd.
Format: `[DATUM] - Beschrijving`

---

## [2026-03-05] - Telegram bot + CI/CD + CodeRabbit

### CodeRabbit
- Geintegreerd op GitHub repo (PRO trial)
- Vanaf nu automatische code review op elke PR

### CI/CD
- Pipeline gefixed: pytest exit code 5 opgelost
- Placeholder tests toegevoegd met risk limit sanity checks
- PR #1: documentatie, PR #2: CI fix

### Telegram Bot (PR #3 - in review)
- src/orchestration/bot.py aangemaakt
- Commando's: /start, /help, /status, /pause, /resume, /emergency
- Security: operator_only decorator
- Unit tests voor alle state transitions

### Docker Productie
- docker/Dockerfile aangemaakt
- docker/docker-compose.prod.yaml — alle services + healthchecks
- Prod: poorten alleen op localhost (security hardening)

### VPS
- Repo gecloned op prod VPS: /home/kaironis/kaironis/
- .env aangemaakt op prod (chmod 600)
- Data mappen aangemaakt: data/tct-pdfs/, logs/

### Sandbox Verkenning
- n8n: gezond, klaar voor integratie
- tct-trading-mcp-server: n8n MCP server (jij had dit al opgezet)
- Ollama: lokaal LLM beschikbaar
- Alle 3 Kaironis services al 44u stabiel uptime

### WinSCP
- Gedownload voor SFTP toegang tot VPS
- Sessie configuratie opgeslagen op Desktop

---
â€” Changelog

Elke significante wijziging wordt hier gedocumenteerd.
Format: `[DATUM] - Beschrijving`

---

## [2026-03-05] - Documentatie setup

- Aangemaakt: `docs/SETUP.md` â€” volledige herstelhandleiding
- Aangemaakt: `docs/CHANGELOG.md` â€” dit bestand
- Aangemaakt: `docs/architecture/overview.md`
- Aangemaakt: `docs/infrastructure/` structuur
- Aangemaakt: `docs/runbooks/`

---

## [2026-03-04] - Security hardening & Foundation

### VPS
- SSH poort gewijzigd: 22 â†’ 2847 (beide VPS servers)
- Root login geblokkeerd
- Wachtwoord SSH geblokkeerd
- Nieuwe `kaironis` sudo user aangemaakt
- Fail2ban geconfigureerd (max 3 pogingen, 24u ban)
- Automatische security updates ingeschakeld
- Docker groep toegevoegd aan kaironis user

### GitHub
- `develop` branch aangemaakt
- Branch protection ingesteld op `main` en `develop`
- PAT verlengd naar geen vervaldatum
- `.gitignore` gehardened
- `.env.example` template toegevoegd

### Database (Sandbox VPS)
- PostgreSQL 15 gestart (kaironis-postgres)
- Redis 7 gestart (docker-redis-1)
- ChromaDB gestart (docker-chromadb-1)
- Repo gecloned op sandbox: `/home/kaironis/kaironis`
- `.env` aangemaakt op sandbox

### SOUL.md
- Versie 1.2.0: Security sectie toegevoegd
- Prompt injection bescherming vastgelegd
- Operator goedgekeurd

### Laptop
- Processor max ingesteld op 98%
- Scherm timeout: 15 min, geen slaapstand

---

## [2026-03-03] - Infrastructure setup

### Accounts aangemaakt
- Gmail: kaironisdev@gmail.com
- GitHub: KaironisDev (via Google OAuth)
- Telegram bot: @KaironisBot

### Repository
- GitHub repo aangemaakt: `KaironisDev/kaironis`
- Volledige mapstructuur aangemaakt per ONBOARDING.md:
  - `soul/` â€” identiteitsdocumenten
  - `src/` â€” broncode (core, memory, trading, orchestration)
  - `tests/` â€” unit, integration, e2e
  - `docker/` â€” Docker Compose bestanden
  - `.github/workflows/` â€” CI/CD pipeline
- Eerste commit en push naar main

### VPS Servers
- Prod VPS (82.29.173.111) geconfigureerd:
  - Ubuntu 24.04, 32GB RAM, 387GB disk
  - Docker 29.2.1 geÃ¯nstalleerd
  - UFW firewall actief
  - fail2ban actief
- Sandbox VPS (72.61.167.71) geconfigureerd:
  - Ubuntu 24.04, 16GB RAM, 193GB disk
  - Docker 29.2.1 geÃ¯nstalleerd
  - UFW firewall actief
  - fail2ban actief

### Lokaal
- Python 3.11.9 geÃ¯nstalleerd
- pykeepass geÃ¯nstalleerd
- KeePass database aangemaakt: `Kaironis.kdbx`
- SSH keys gegenereerd (kaironis_prod, kaironis_sandbox)

---

## [2026-02-28] - Project kickoff

### Documenten ontvangen van Perry
- `ONBOARDING.md` â€” project onboarding document
- `SOUL.md` â€” Kaironis identiteit (v1.1.0)
- `Kaironis_Architecture_Plan.docx` â€” architectuur document

### Eerste sessie
- Project volledig doorgelezen en begrepen
- Planning gemaakt voor implementatie
- Besloten: foundation eerst, dan bouwen

