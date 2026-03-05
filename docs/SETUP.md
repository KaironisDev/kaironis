# Kaironis — Complete Setup Handleiding

> Dit document beschrijft **elke stap** om Kaironis volledig opnieuw op te bouwen
> vanaf nul. Bij een laptop crash of server verlies is dit het startpunt.

**Laatste update:** 2026-03-05
**Versie:** 1.1.0

---

## Inhoudsopgave

1. [Vereisten](#1-vereisten)
2. [Windows Laptop Setup](#2-windows-laptop-setup)
3. [SSH Keys aanmaken](#3-ssh-keys-aanmaken)
4. [GitHub Setup](#4-github-setup)
5. [VPS Setup - Prod](#5-vps-setup---prod)
6. [VPS Setup - Sandbox](#6-vps-setup---sandbox)
7. [KeePass Database](#7-keepass-database)
8. [OpenClaw Setup](#8-openclaw-setup)

---

## 1. Vereisten

### Accounts
| Account | Email | Opgeslagen in |
|---------|-------|---------------|
| GitHub | kaironisdev@gmail.com | KeePass → GitHub |
| Gmail (Kaironis) | kaironisdev@gmail.com | KeePass → Email |
| Hostinger (VPS) | Perry's persoonlijke email | Perry's KeePass |
| Telegram Bot | @KaironisBot | KeePass → Telegram Bots |

### Software (Windows)
- Python 3.11+ (`winget install Python.Python.3.11`)
- Git (`winget install Git.Git`)
- KeePass Password Safe 2 (`C:\Program Files\KeePass Password Safe 2\`)
- OpenClaw (npm global)
- Docker Desktop
- Chrome (voor OpenClaw browser control)

---

## 2. Windows Laptop Setup

### Python installeren
```powershell
winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
```
Python pad na installatie: `C:\Users\Perry\AppData\Local\Programs\Python\Python311\python.exe`

### pykeepass installeren
```powershell
pip install pykeepass
```

### Power instellingen
```powershell
# Scherm uit na 15 min, NOOIT slaapstand
powercfg /change standby-timeout-ac 0
powercfg /change standby-timeout-dc 0
powercfg /change monitor-timeout-ac 15
powercfg /change monitor-timeout-dc 15

# Processor max 98% (nooit 100% om stabiliteit te garanderen)
$plan = ((powercfg /getactivescheme) -split 'GUID: ')[1].Split(' ')[0]
powercfg /setacvalueindex $plan SUB_PROCESSOR PROCTHROTTLEMAX 98
powercfg /setdcvalueindex $plan SUB_PROCESSOR PROCTHROTTLEMAX 98
powercfg /setactive $plan
```

### Git configureren
```powershell
git config --global user.email "kaironisdev@gmail.com"
git config --global user.name "KaironisDev"
```

---

## 3. SSH Keys aanmaken

```powershell
$sshDir = "$env:USERPROFILE\.ssh"
New-Item -ItemType Directory -Force -Path $sshDir

# Prod VPS key
"" | ssh-keygen -t ed25519 -C "kaironis-prod" -f "$sshDir\kaironis_prod" -N '""'

# Sandbox VPS key
"" | ssh-keygen -t ed25519 -C "kaironis-sandbox" -f "$sshDir\kaironis_sandbox" -N '""'
```

### SSH Config (`~/.ssh/config`)
```
# Kaironis - Prod VPS
Host kaironis-prod
    HostName 82.29.173.111
    User kaironis
    IdentityFile ~/.ssh/kaironis_prod
    Port 2847
    StrictHostKeyChecking no

# Kaironis - Sandbox VPS
Host kaironis-sandbox
    HostName 72.61.167.71
    User kaironis
    IdentityFile ~/.ssh/kaironis_sandbox
    Port 2847
    StrictHostKeyChecking no
```

### Public keys toevoegen aan VPS
Log in via Hostinger webconsole (hpanel.hostinger.com) als root:
```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "PLAK_HIER_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Fix newline als keys aaneengesloten zijn:
python3 -c "
f = open('/root/.ssh/authorized_keys', 'r+')
c = f.read().replace('#hostinger-managed-key', '#hostinger-managed-key\n')
f.seek(0); f.write(c); f.truncate(); f.close()
print('Done')
"
```

---

## 4. GitHub Setup

### Account
- **URL:** https://github.com/KaironisDev
- **Repo:** https://github.com/KaironisDev/kaironis
- **PAT:** Opgeslagen in KeePass → GitHub → kaironis-dev-token

### Repo clonen
```powershell
$token = "PAT_UIT_KEEPASS"
git clone "https://KaironisDev:$token@github.com/KaironisDev/kaironis.git"
cd kaironis
git remote set-url origin "https://KaironisDev:$token@github.com/KaironisDev/kaironis.git"
```

### Branch structuur
- `main` — productie, alleen via PR
- `develop` — development, alleen via PR
- Feature branches: `feature/naam-van-feature`

### Branch protection (beide branches)
Ingesteld via GitHub Settings → Branches:
- Pull request verplicht voor merge
- Conversations moeten resolved zijn

---

## 5. VPS Setup — Prod (82.29.173.111)

### Specs
- **RAM:** 32GB
- **Disk:** 387GB
- **OS:** Ubuntu 24.04
- **SSH Poort:** 2847
- **SSH User:** kaironis

### Initiële setup (als root via Hostinger console)
```bash
# Updates
apt-get update -qq && apt-get upgrade -y -qq

# Essentials
apt-get install -y curl wget git ufw fail2ban python3 python3-pip unattended-upgrades

# Docker
curl -fsSL https://get.docker.com | sh
systemctl enable docker && systemctl start docker

# Docker Compose
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Firewall
ufw --force enable
ufw allow 2847/tcp  # SSH custom poort
ufw allow 80/tcp
ufw allow 443/tcp
```

### Security hardening (als root)
```bash
# Nieuwe sudo user
useradd -m -s /bin/bash -G sudo kaironis
mkdir -p /home/kaironis/.ssh
cp /root/.ssh/authorized_keys /home/kaironis/.ssh/authorized_keys
chown -R kaironis:kaironis /home/kaironis/.ssh
chmod 700 /home/kaironis/.ssh && chmod 600 /home/kaironis/.ssh/authorized_keys

# Wachtwoord instellen
passwd kaironis  # gebruik: K@ir0n1s_VPS_2026!

# NOPASSWD sudo
echo "kaironis ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/kaironis
chmod 440 /etc/sudoers.d/kaironis

# Docker groep
usermod -aG docker kaironis

# SSH hardening
cat > /etc/ssh/sshd_config.d/kaironis-hardening.conf << 'EOF'
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
X11Forwarding no
AllowAgentForwarding no
AllowTcpForwarding no
ClientAliveInterval 300
ClientAliveCountMax 2
Port 2847
EOF

# SSH socket override voor poort 2847
mkdir -p /etc/systemd/system/ssh.socket.d
cat > /etc/systemd/system/ssh.socket.d/override.conf << 'EOF'
[Socket]
ListenStream=
ListenStream=2847
EOF

systemctl daemon-reload
systemctl restart ssh.socket
systemctl restart ssh

# Fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3
banaction = ufw

[sshd]
enabled = true
port = 2847
maxretry = 3
bantime = 86400
EOF

systemctl restart fail2ban
```

---

## 6. VPS Setup — Sandbox (72.61.167.71)

### Specs
- **RAM:** 16GB
- **Disk:** 193GB
- **OS:** Ubuntu 24.04
- **SSH Poort:** 2847
- **SSH User:** kaironis

### Zelfde setup als Prod (zie sectie 5)

### Extra: bestaande services op Sandbox
Hostinger heeft pre-installed:
- **n8n** — workflow automatisering (poort 5678, localhost only)
- **Traefik** — reverse proxy (poort 80/443)
- **Ollama** — lokaal LLM (poort 11434, intern)
- **tct-trading-mcp-server** — MCP server voor TCT context (poort 3001)

### Kaironis Docker services (sandbox)
```bash
# Als kaironis user
cd /home/kaironis/kaironis

# .env aanmaken
cat > .env << 'EOF'
ENVIRONMENT=development
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=kaironis
POSTGRES_USER=kaironis
POSTGRES_PASSWORD=Kaironis_DB_2026!
REDIS_HOST=redis
REDIS_PORT=6379
CHROMA_HOST=chromadb
CHROMA_PORT=8000
TELEGRAM_BOT_TOKEN=zie_keepass
TELEGRAM_OPERATOR_CHAT_ID=98661271
LOG_LEVEL=DEBUG
EOF
chmod 600 .env

# Services starten
sudo docker compose -f docker/docker-compose.dev.yaml up -d
```

Draaiende containers:
- `kaironis-postgres` — PostgreSQL 15
- `docker-redis-1` — Redis 7
- `docker-chromadb-1` — ChromaDB

---

## 7. KeePass Database

**Locatie:** `C:\Users\Perry\Documents\Kaironis.kdbx`
**Master wachtwoord:** In Perry's hoofd (niet hier opgeslagen)

### Structuur
```
Root/
├── Infrastructure/
│   ├── Prod VPS - SSH Public Key
│   ├── Prod VPS - Root Access (IP: 82.29.173.111)
│   ├── Sandbox VPS - SSH Public Key
│   ├── Sandbox VPS - Root Access (IP: 72.61.167.71)
│   └── SSH Key Location (C:\Users\Perry\.ssh\)
├── Telegram Bots/
│   └── KaironisBot (token + URL)
├── Brokers/
│   ├── Breakout Prop - MT5 (leeg, later invullen)
│   ├── Hyperliquid API Key (leeg, later invullen)
│   └── MEXC API Key (leeg, later invullen)
├── GitHub/
│   ├── GitHub - Kaironis Account (KaironisDev)
│   └── GitHub PAT - kaironis-dev-token (geen vervaldatum)
└── Email Accounts/
    └── Gmail - KaironisDev (kaironisdev@gmail.com)
```

### KeePass opnieuw aanmaken (bij crash)
```powershell
pip install pykeepass
python C:\pad\naar\create_keepass.py  # script opnieuw schrijven met alle credentials
```

---

## 8. OpenClaw Setup

OpenClaw is de AI assistant die Kaironis bouwt en beheert.

### Configuratie
- **Config:** `C:\Users\Perry\.openclaw\openclaw.json`
- **Workspace:** `C:\Users\Perry\.openclaw\workspace\`
- **Telegram bot token:** In OpenClaw config (niet in KeePass)

### Browser control
```powershell
# OpenClaw browser extensie installeren
openclaw browser extension install

# Browser starten (voor web automatisering)
openclaw browser --browser-profile openclaw start
```

### Bij herstart na crash
1. OpenClaw opnieuw installeren
2. Telegram bot token opnieuw configureren
3. Browser extensie opnieuw installeren
4. Memory files terugzetten vanuit backup

---

*Dit document wordt bijgehouden na elke significante wijziging.*
*Zie ook: `docs/CHANGELOG.md` voor de volledige geschiedenis.*
