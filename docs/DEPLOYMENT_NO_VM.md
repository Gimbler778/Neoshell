# Cloud Deployment Without a VM

Neoshell is an HTTP service. It can run on a managed Docker web service while file bytes live in S3-compatible object storage and metadata lives in Neon.

## Recommended free stack

- **App:** Koyeb free web service, or Render free web service
- **Files:** Backblaze B2 S3 API
- **Database:** Neon PostgreSQL
- **Alternative files:** Cloudflare R2

Free web services can sleep when idle. Expect a cold-start delay after inactivity. Provider upload-size limits may also apply.

## Create the services

### Neon

1. Create a Neon project and database.
2. Copy the pooled connection string.
3. Set `NEON_DATABASE_URL` to that value and `DB_SSL=true`.

### Backblaze B2

1. Create a private bucket.
2. Create an application key restricted to the bucket with read/write access.
3. Record the key ID, application key, bucket name, and S3 endpoint.
4. Use the endpoint shown for the bucket region, such as `https://s3.us-west-004.backblazeb2.com`.

Set:

```text
S3_BUCKET=YOUR_B2_BUCKET
S3_ACCESS_KEY_ID=YOUR_B2_KEY_ID
S3_SECRET_ACCESS_KEY=YOUR_B2_APPLICATION_KEY
S3_REGION=YOUR_B2_REGION
S3_ENDPOINT=https://s3.YOUR_B2_REGION.backblazeb2.com
S3_FORCE_PATH_STYLE=false
```

### Cloudflare R2 alternative

Create an R2 bucket and an API token with object read/write permissions. Use:

```text
S3_BUCKET=YOUR_R2_BUCKET
S3_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
S3_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
S3_REGION=auto
S3_ENDPOINT=https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
S3_FORCE_PATH_STYLE=false
```

R2 activation can ask for a payment method, depending on the account.

## Deploy on Koyeb

1. Create an App and choose Docker or GitHub deployment.
2. Select this repository and set the Dockerfile path to `server/Dockerfile`.
3. Add the environment variables from the `.env.example` file, replacing all placeholders.
4. Expose the HTTP service port. Koyeb supplies `PORT`, so do not hard-code it.
5. Set the health check path to `/health` using HTTP.
6. Deploy and verify `https://YOUR-APP.koyeb.app/health` returns `{"ok":true}`.

## Deploy on Render

1. Create a new Web Service from this repository.
2. Choose Docker and set the Dockerfile path to `server/Dockerfile` if Render asks for it.
3. Add the same database, auth, and S3 environment variables.
4. Set the health check path to `/health`.
5. Deploy and verify the generated HTTPS URL.

## Use the deployed API

Install the CLI package locally:

```bash
pipx install neoshell-cli
# or: pip install neoshell-cli
```

Authenticate once:

```bash
neoshell login --url https://YOUR-APP.example.com --token YOUR_AUTH_TOKEN
```

Then run commands directly without specifying `--url` or `--token` every time:

```bash
neoshell list
neoshell upload sample.txt
neoshell download sample.txt
neoshell share sample.txt --expires 24h
neoshell delete sample.txt --yes
neoshell status
```

Keep `AUTH_TOKEN` private. The `/health` endpoint intentionally remains unauthenticated for platform health checks.

## Local, LAN, and Tailscale use

The same HTTP server works locally or across LAN / Tailscale:

```bash
# Point CLI to local instance
neoshell login --url http://127.0.0.1:8080 --token YOUR_AUTH_TOKEN

# Or for LAN / Tailscale:
neoshell login --url http://100.x.y.z:8080 --token YOUR_AUTH_TOKEN
```

## Troubleshooting

- `401 Unauthorized`: verify the Bearer token matches `AUTH_TOKEN`.
- `/health` fails: confirm the platform is routing HTTP and that the service listens on its supplied `PORT`.
- S3 errors: verify bucket name, region, endpoint, key permissions, and `S3_FORCE_PATH_STYLE`.
- Upload size failures: check the platform's request body limit; the current MVP uses one HTTP POST per file.
