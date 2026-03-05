# Kaironis — Changelog

Elke significante wijziging wordt hier gedocumenteerd.
Format: `[DATUM] - Beschrijving`

---

## [2026-03-05] - Documentatie setup

- Aangemaakt: `docs/SETUP.md` — volledige herstelhandleiding
- Aangemaakt: `docs/CHANGELOG.md` — dit bestand
- Aangemaakt: `docs/architecture/overview.md`
- Aangemaakt: `docs/infrastructure/` structuur
- Aangemaakt: `docs/runbooks/`

---

## [2026-03-04] - Security hardening & Foundation

### VPS
- SSH poort gewijzigd: 22 → 2847 (beide VPS servers)
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
  - `soul/` — identiteitsdocumenten
  - `src/` — broncode (core, memory, trading, orchestration)
  - `tests/` — unit, integration, e2e
  - `docker/` — Docker Compose bestanden
  - `.github/workflows/` — CI/CD pipeline
- Eerste commit en push naar main

### VPS Servers
- Prod VPS (82.29.173.111) geconfigureerd:
  - Ubuntu 24.04, 32GB RAM, 387GB disk
  - Docker 29.2.1 geïnstalleerd
  - UFW firewall actief
  - fail2ban actief
- Sandbox VPS (72.61.167.71) geconfigureerd:
  - Ubuntu 24.04, 16GB RAM, 193GB disk
  - Docker 29.2.1 geïnstalleerd
  - UFW firewall actief
  - fail2ban actief

### Lokaal
- Python 3.11.9 geïnstalleerd
- pykeepass geïnstalleerd
- KeePass database aangemaakt: `Kaironis.kdbx`
- SSH keys gegenereerd (kaironis_prod, kaironis_sandbox)

---

## [2026-02-28] - Project kickoff

### Documenten ontvangen van Perry
- `ONBOARDING.md` — project onboarding document
- `SOUL.md` — Kaironis identiteit (v1.1.0)
- `Kaironis_Architecture_Plan.docx` — architectuur document

### Eerste sessie
- Project volledig doorgelezen en begrepen
- Planning gemaakt voor implementatie
- Besloten: foundation eerst, dan bouwen
