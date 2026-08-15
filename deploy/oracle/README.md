# Oracle Free Deployment

This deployment target assumes a single Oracle Cloud Always Free VM running Docker Compose.

## Topology

- `caddy`: public HTTPS entrypoint and reverse proxy
- `frontend`: Nuxt production server
- `backend`: Django + Daphne
- `worker`: Celery worker
- `postgres`: PostgreSQL
- `redis`: Redis for Celery and Channels

The public app is served from a single domain:

- `/` -> Nuxt frontend
- `/api/*` -> Django REST API
- `/admin/*` -> Django admin
- `/api-auth/*` -> DRF login
- `/ws/*` -> Django Channels websocket endpoint
- `/static/*` -> Django static files

That same-origin layout avoids the cross-origin cookie problems you hit on separate hosted subdomains.

## Oracle Free Fit

Oracle Always Free is a better fit for this app than Render Free because your backend, websocket server, and Celery worker stay on a VM you control instead of sleeping after inactivity.

Important Oracle caveats:

- Always Free compute can be reclaimed if Oracle considers it idle.
- Always Free capacity is sometimes unavailable in a region or availability domain.
- You are responsible for VM patching, Docker, TLS, restarts, logs, and backups.

## VM Size

Recommended:

- `VM.Standard.A1.Flex`
- `2 OCPUs`
- `12 GB RAM`

That is within Oracle's Always Free limits as documented by OCI.

## Files

- [compose.yaml](/Users/litt/Desktop/Spotify_Game/Track_Decode/deploy/oracle/compose.yaml)
- [Caddyfile](/Users/litt/Desktop/Spotify_Game/Track_Decode/deploy/oracle/Caddyfile)
- [.env.example](/Users/litt/Desktop/Spotify_Game/Track_Decode/deploy/oracle/.env.example)
- [track-decode.service](/Users/litt/Desktop/Spotify_Game/Track_Decode/deploy/oracle/track-decode.service)

## Server Prep

On the Oracle VM:

1. Install Docker Engine and the Docker Compose plugin.
2. Open ports `80` and `443` in the Oracle security list and host firewall.
3. Point your domain DNS A record to the VM public IP.
4. Clone this repo to `/opt/track-decode`.

## Environment

Create `/opt/track-decode/deploy/oracle/.env` from `.env.example`:

```bash
cp /opt/track-decode/deploy/oracle/.env.example /opt/track-decode/deploy/oracle/.env
```

Set at least:

- `APP_DOMAIN`
- `ACME_EMAIL`
- `DJANGO_SECRET_KEY`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`

## First Deploy

From `/opt/track-decode/deploy/oracle`:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
docker compose logs -f backend worker frontend caddy
```

## Spotify Callback

After the domain is live, set your Spotify app callback URL to:

```text
https://<your-domain>/api/spotify/callback/
```

## Django Admin User

Create an admin user:

```bash
docker compose exec backend python manage.py createsuperuser
```

## Optional systemd Autostart

If you want the stack to start on boot:

```bash
sudo cp /opt/track-decode/deploy/oracle/track-decode.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now track-decode.service
```

## Updates

```bash
cd /opt/track-decode
git pull
cd deploy/oracle
docker compose up -d --build
```

## Backup Advice

Oracle Free does not manage backups for these containers.

Minimum practical backup scope:

- PostgreSQL volume
- Redis volume if you care about queued tasks surviving restarts
- your `.env`

## Notes

- Caddy will automatically provision and renew TLS certificates once DNS points at the VM.
- The backend serves Django static files through WhiteNoise.
- The websocket endpoint stays at `/ws/games/<join_token>/`.
