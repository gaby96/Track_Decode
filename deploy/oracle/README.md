# Oracle Free Deployment

This deployment target assumes a single Oracle Cloud Always Free VM running Docker Compose.

## Topology

- `caddy`: public HTTPS entrypoint and reverse proxy
- `frontend`: Nuxt production server
- `backend`: Django + Daphne
- `worker`: Celery worker
- `sqlite`: shared SQLite database file on a Docker volume
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

## SQLite Note

This Oracle target now uses SQLite instead of PostgreSQL.

That is acceptable for a small single-VM deployment, but there is an important tradeoff:

- Django and Celery will both write to the same SQLite file.
- SQLite supports only limited concurrent writes.
- For a hobby deployment with a small number of players, this is usually workable.
- For heavier usage, PostgreSQL is still the better database.

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

- `DEBUG`
- `APP_HOST`
- `APP_ORIGIN`
- `APP_DOMAIN`
- `DJANGO_SECRET_KEY`
- `SQLITE_PATH`
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`

Optional:

- `ACME_EMAIL`
  Use a real email if you want ACME expiry notices. The stack can obtain certificates without it.

For a real domain deployment:

- `APP_HOST` should be the bare hostname only, for example `quiz.example.com`
- `APP_ORIGIN` should be the full public HTTPS origin, for example `https://quiz.example.com`
- `APP_DOMAIN` should match the hostname Django should accept

Temporary IP-only testing is possible with values like:

- `DEBUG=true`
- `APP_HOST=http://130.162.244.167`
- `APP_ORIGIN=http://130.162.244.167`
- `APP_DOMAIN=130.162.244.167`

That is only for initial bring-up. Spotify login and a proper secure deployment should use a real domain with HTTPS.

## Domain Cutover

Once your DNS A record points at the Oracle VM public IP, switch the stack to the real domain:

```bash
cd /opt/track-decode/deploy/oracle
./cutover-to-domain.sh quiz.example.com admin@example.com
```

What that does:

- sets `DEBUG=false`
- sets `APP_HOST` to the bare hostname for Caddy TLS
- sets `APP_ORIGIN=https://<your-domain>`
- sets `APP_DOMAIN=<your-domain>`
- updates `ACME_EMAIL`
- recreates the backend, worker, frontend, and Caddy containers

After that, update the Spotify app callback URL to:

```text
https://<your-domain>/api/spotify/callback/
```

Then verify:

```bash
docker compose ps
docker compose logs -f caddy backend frontend
curl -I https://<your-domain>
curl -I https://<your-domain>/api/healthz/
```

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

- SQLite volume
- Redis volume if you care about queued tasks surviving restarts
- your `.env`

## Notes

- Caddy will automatically provision and renew TLS certificates once DNS points at the VM.
- The backend serves Django static files through WhiteNoise.
- The websocket endpoint stays at `/ws/games/<join_token>/`.
