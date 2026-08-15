# Track Decode

Track Decode is a Django + Channels backend with a Nuxt frontend for a live team music quiz.

## Oracle deployment

Oracle Free is the better fit for this realtime app if you want a single always-on VM instead of Render Free sleep behavior.

Deployment assets for Oracle are in [deploy/oracle/README.md](/Users/litt/Desktop/Spotify_Game/Track_Decode/deploy/oracle/README.md).

## Render deploy

This repo now includes [render.yaml](/Users/litt/Desktop/Spotify_Game/Track_Decode/render.yaml) for a full Render Blueprint deployment:

- `track-decode-backend` web service
- `track-decode-frontend` Nuxt web service
- `track-decode-db` Postgres database
- `track-decode-redis` Render Key Value instance

On the free Render setup, the Celery worker runs inside the same `track-decode-backend` web service as Django/Daphne.

To deploy:

1. Push this repo to GitHub.
2. In Render, choose `New > Blueprint`.
3. Connect the `Track_Decode` repo and deploy the root `render.yaml`.
4. During the initial Blueprint setup, provide:
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
5. After the backend is live, set your Spotify app callback URL to:
   - `https://<your-backend-service>.onrender.com/api/spotify/callback/`

Important:

- The Blueprint is configured for Render `free` plans.
- `track-decode-backend` runs both Daphne and Celery in one container because free Render does not give you a separate always-on worker without moving off the free web-service model.
- Free Render web services spin down after 15 minutes of no inbound traffic, so both the Django app and the embedded Celery worker stop when the backend sleeps.
- Free Render Postgres expires 30 days after creation.
- Free Render Key Value is in-memory only and can lose its data on restart.
- For custom production domains, add them in Render after the first deploy.
