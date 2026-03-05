# Disaster Recovery Runbook

> Wat te doen als er iets kapot gaat.
> Lees dit rustig door — paniek helpt niet.

---

## Scenario 1: Laptop crash / nieuwe laptop

**Tijd nodig:** ~2 uur

### Stap 1: Software installeren
Zie `docs/SETUP.md` sectie 2 (Windows Laptop Setup)

### Stap 2: KeePass herstellen
- Zet `Kaironis.kdbx` terug vanuit backup
- Of herstel vanuit KeePass Cloud sync (indien ingesteld)

### Stap 3: SSH keys herstellen
- Zet `.ssh/kaironis_prod` en `.ssh/kaironis_sandbox` terug vanuit backup
- Of genereer nieuwe keys en voeg toe aan VPS via Hostinger console
- Zie `docs/SETUP.md` sectie 3

### Stap 4: Repo clonen
```powershell
$token = "PAT_UIT_KEEPASS"
git clone "https://KaironisDev:$token@github.com/KaironisDev/kaironis.git"
```

### Stap 5: OpenClaw herstellen
- OpenClaw opnieuw installeren
- Telegram bot token opnieuw configureren
- Memory files terugzetten vanuit backup

---

## Scenario 2: VPS onbereikbaar

### Eerst: probeer Hostinger webconsole
1. Ga naar hpanel.hostinger.com
2. Log in met Perry's persoonlijke email
3. Klik op de VPS → "Browser terminal"
4. Check wat er mis is

### Als VPS echt kapot is: herinstalleren
1. Hostinger → VPS → "Reinstall OS" (Ubuntu 24.04)
2. Volg `docs/SETUP.md` sectie 5 of 6
3. Nieuwe SSH keys genereren of bestaande opnieuw toevoegen

### Services herstarten na reboot
```bash
ssh kaironis-prod

# Check wat er draait
sudo docker ps

# Herstart alle Kaironis services
cd /home/kaironis/kaironis
sudo docker compose -f docker/docker-compose.dev.yaml up -d
```

---

## Scenario 3: GitHub PAT verlopen

```powershell
# Nieuw token aanmaken via browser
# OpenClaw browser starten
openclaw browser --browser-profile openclaw start
# Navigeer naar: https://github.com/settings/tokens
# Regenereer kaironis-dev-token

# Update git remote
$newToken = "NIEUW_TOKEN"
cd C:\Users\Perry\.openclaw\workspace\kaironis
git remote set-url origin "https://KaironisDev:$newToken@github.com/KaironisDev/kaironis.git"

# Update KeePass
# Open KeePass → GitHub → kaironis-dev-token → wachtwoord bijwerken
```

---

## Scenario 4: Database verloren

```bash
ssh kaironis-sandbox  # of kaironis-prod

# Check of containers draaien
sudo docker ps

# Herstart containers
sudo docker compose -f /home/kaironis/kaironis/docker/docker-compose.dev.yaml up -d

# Als data verloren is: herstel vanuit backup (TODO: backup systeem opzetten)
```

---

## Nuttige commando's

```powershell
# SSH verbinding testen
ssh kaironis-prod "echo OK"
ssh kaironis-sandbox "echo OK"

# Status alle services op sandbox
ssh kaironis-sandbox "sudo docker ps --format 'table {{.Names}}\t{{.Status}}'"

# Fail2ban gebande IPs checken
ssh kaironis-prod "sudo fail2ban-client status sshd"

# VPS schijfruimte checken
ssh kaironis-prod "df -h /"
```
