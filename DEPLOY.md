# Déploiement simulé — StageL2

Ce guide installe le site sur une machine virtuelle **Ubuntu Server 24.04** (Python 3.12 minimum, exigé par Django 6.1),
accessible depuis le réseau du labo à l'adresse **https://jobs.lab.local**.

```
Navigateur ──HTTPS──▶ Nginx (port 443) ──▶ Gunicorn (127.0.0.1:8000) ──▶ Django ──▶ SQLite
                       │ sert /static/          1 processus, 4 threads
                       └ redirige HTTP → HTTPS
systemd : jobsapp.service (le site) · jobsapp-scrape.timer (scraping 2×/jour) · jobsapp-backup.timer (sauvegarde nocturne)
```

| Quoi | Où |
|---|---|
| Code | `/srv/jobsapp/app` |
| Environnement Python | `/srv/jobsapp/venv` |
| Fichiers statiques (CSS/JS) | `/srv/jobsapp/staticfiles` |
| Base de données + sauvegardes | `/var/lib/jobsapp/` |
| Journal de sécurité (`security.log`) | `/var/log/jobsapp/` |
| Configuration secrète | `/etc/jobsapp/jobsapp.env` |

Toutes les commandes ci-dessous se lancent sur la VM, avec un compte qui a `sudo`.

---

## 1. Paquets système

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git openssl
```

## 2. Utilisateur et dossiers

L'application tourne sous un utilisateur dédié `jobsapp`, sans mot de passe ni shell :
si le site est compromis, l'attaquant n'obtient pas les droits root.

```bash
sudo adduser --system --group --home /srv/jobsapp jobsapp
sudo mkdir -p /srv/jobsapp/staticfiles /var/lib/jobsapp /var/log/jobsapp /etc/jobsapp
sudo chown jobsapp:jobsapp /srv/jobsapp /srv/jobsapp/staticfiles /var/lib/jobsapp /var/log/jobsapp
```

## 3. Code et dépendances

```bash
sudo -u jobsapp git clone -b deploy https://github.com/Solaire006/StageL2.git /srv/jobsapp/app
sudo -u jobsapp python3 -m venv /srv/jobsapp/venv
sudo -u jobsapp /srv/jobsapp/venv/bin/pip install -r /srv/jobsapp/app/requirements.txt
```

## 4. Configuration (`.env`)

```bash
sudo cp /srv/jobsapp/app/.env.example /etc/jobsapp/jobsapp.env
sudo chown root:jobsapp /etc/jobsapp/jobsapp.env
sudo chmod 640 /etc/jobsapp/jobsapp.env      # lisible seulement par root et l'app
# générer une clé secrète :
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
sudo nano /etc/jobsapp/jobsapp.env
```

À modifier au minimum :
- `DJANGO_SECRET_KEY` → la clé générée ci-dessus (**jamais** dans Git) ;
- `DJANGO_ALLOWED_HOSTS` → `jobs.lab.local` + l'adresse IP de la VM ;
- la partie e-mail : sans serveur mail dans le labo, supprimez la ligne `EMAIL_BACKEND=...smtp...`
  et les e-mails de réinitialisation apparaîtront dans `journalctl -u jobsapp`.

⚠️ Pas d'espace autour du `=` et pas de commentaire à la fin d'une ligne (systemd les garderait dans la valeur).

## 5. Base de données, fichiers statiques, compte admin

```bash
M="sudo -u jobsapp /srv/jobsapp/app/deploy/manage.sh"
$M migrate
$M collectstatic --noinput
$M createsuperuser
$M check --deploy        # doit afficher au plus l'avertissement HSTS (W004), normal avec un certificat auto-signé
```

## 6. Certificat HTTPS auto-signé

Pour un déploiement simulé, un certificat auto-signé suffit (le navigateur affichera un avertissement
qu'on accepte une fois). En production réelle on utiliserait Let's Encrypt (`certbot`).

```bash
sudo mkdir -p /etc/ssl/jobsapp
sudo openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
  -subj "/CN=jobs.lab.local" -addext "subjectAltName=DNS:jobs.lab.local" \
  -keyout /etc/ssl/jobsapp/jobsapp.key -out /etc/ssl/jobsapp/jobsapp.crt
sudo chmod 600 /etc/ssl/jobsapp/jobsapp.key
```

## 7. Nginx

```bash
sudo cp /srv/jobsapp/app/deploy/nginx/jobsapp.conf /etc/nginx/sites-available/jobsapp
sudo ln -s /etc/nginx/sites-available/jobsapp /etc/nginx/sites-enabled/jobsapp
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

## 8. Services systemd

```bash
sudo cp /srv/jobsapp/app/deploy/systemd/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now jobsapp.service jobsapp-scrape.timer jobsapp-backup.timer
```

Le serveur est en UTC par défaut ; pour que le scraping tourne à 7 h et 14 h heure de Madagascar :
`sudo timedatectl set-timezone Indian/Antananarivo`.

## 9. Pare-feu

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

Gunicorn écoute seulement sur `127.0.0.1` : il n'est pas joignable depuis l'extérieur, tout passe par Nginx.

## 10. Accès depuis un poste du labo

Sans DNS dans le labo, ajoutez sur chaque poste client la ligne suivante
(`/etc/hosts` sous Linux/Mac, `C:\Windows\System32\drivers\etc\hosts` sous Windows) :

```
10.10.20.10   jobs.lab.local
```
(remplacez par l'IP réelle de la VM), puis ouvrez https://jobs.lab.local.

---

## Vérifications

```bash
systemctl status jobsapp                          # doit être "active (running)"
curl -I  http://jobs.lab.local                    # 301 vers https
curl -k  https://jobs.lab.local/healthz/          # "ok"
systemctl list-timers 'jobsapp-*'                 # prochains scraping et sauvegarde
sudo systemctl start jobsapp-scrape && journalctl -u jobsapp-scrape -n 20   # scraping manuel
sudo tail -f /var/log/jobsapp/security.log        # connexions, échecs, blocages
```

Test du blocage anti-force brute : 5 mauvais mots de passe sur le même compte → page « Trop de tentatives »
(code 429) et une ligne `LOCKOUT` dans `security.log`. Un admin peut débloquer dans
*Administration → Axes → Access attempts*.

## Mettre à jour le site

```bash
cd /srv/jobsapp/app && sudo -u jobsapp git pull
sudo -u jobsapp /srv/jobsapp/venv/bin/pip install -r requirements.txt
M="sudo -u jobsapp /srv/jobsapp/app/deploy/manage.sh"
$M migrate && $M collectstatic --noinput
sudo systemctl restart jobsapp
```

## Sauvegarde et restauration

Une copie de la base est faite chaque nuit dans `/var/lib/jobsapp/backups/` (14 dernières conservées).
Sauvegarde immédiate : `sudo systemctl start jobsapp-backup`.

Restaurer :
```bash
sudo systemctl stop jobsapp jobsapp-scrape.timer
sudo -u jobsapp cp /var/lib/jobsapp/backups/db_AAAAMMJJ_HHMMSS.sqlite3 /var/lib/jobsapp/db.sqlite3
sudo systemctl start jobsapp jobsapp-scrape.timer
```

## Limites connues (acceptables pour une simulation)

- **SQLite** convient pour quelques utilisateurs ; au-delà, passer à PostgreSQL.
- **Un seul processus Gunicorn** : nécessaire tant que le bouton « Lancer le scraping » garde son état en mémoire.
  Pour monter en charge, retirer ce bouton et ne garder que le timer systemd (ou passer à Celery).
- Si un scraping manuel et le timer tournent en même temps, il n'y a pas de doublons (URL unique),
  mais l'un des deux peut être ralenti.

## En cas de problème

| Symptôme | Où regarder |
|---|---|
| 502 Bad Gateway | l'app ne tourne pas : `journalctl -u jobsapp -n 50` |
| `DJANGO_SECRET_KEY must be set` | clé manquante dans `/etc/jobsapp/jobsapp.env` |
| `Cannot create the log folder` | `sudo chown jobsapp:jobsapp /var/log/jobsapp` |
| 400 Bad Request | le nom ou l'IP utilisé n'est pas dans `DJANGO_ALLOWED_HOSTS` |
| 403 CSRF au login | `DJANGO_CSRF_TRUSTED_ORIGINS` doit être exactement `https://jobs.lab.local` |
| Pages sans mise en forme | relancer `collectstatic` ; vérifier le chemin `/static/` dans la conf Nginx |
