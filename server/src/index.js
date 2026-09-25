const path = require('path');
const crypto = require('crypto');
const { Transform } = require('stream');
const express = require('express');
const { Pool } = require('pg');
const {
  S3Client,
  HeadBucketCommand,
  CreateBucketCommand,
  PutObjectCommand,
  DeleteObjectCommand,
} = require('@aws-sdk/client-s3');

const PORT = Number(process.env.PORT || 8080);
const DATABASE_URL = process.env.NEON_DATABASE_URL;
const AUTH_TOKEN = process.env.AUTH_TOKEN || '';
const DB_SSL = String(process.env.DB_SSL || '').toLowerCase();
const S3_BUCKET = process.env.S3_BUCKET;
const S3_REGION = process.env.S3_REGION || 'us-east-1';

if (!DATABASE_URL) {
  console.error('Missing NEON_DATABASE_URL in environment.');
  process.exit(1);
}

if (!S3_BUCKET || !process.env.S3_ACCESS_KEY_ID || !process.env.S3_SECRET_ACCESS_KEY) {
  console.error('Missing S3_BUCKET, S3_ACCESS_KEY_ID, or S3_SECRET_ACCESS_KEY in environment.');
  process.exit(1);
}

const shouldUseSsl =
  DB_SSL === 'true' ||
  DB_SSL === '1' ||
  /sslmode=require/i.test(DATABASE_URL);

const poolConfig = { connectionString: DATABASE_URL };
if (shouldUseSsl) poolConfig.ssl = { rejectUnauthorized: false };

const pool = new Pool(poolConfig);
const s3 = new S3Client({
  region: S3_REGION,
  endpoint: process.env.S3_ENDPOINT || undefined,
  forcePathStyle: String(process.env.S3_FORCE_PATH_STYLE || '').toLowerCase() === 'true',
  credentials: {
    accessKeyId: process.env.S3_ACCESS_KEY_ID,
    secretAccessKey: process.env.S3_SECRET_ACCESS_KEY,
  },
});

async function initDb() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS file_metadata (
      name TEXT PRIMARY KEY,
      size_bytes BIGINT NOT NULL,
      sha256 TEXT NOT NULL,
      stored_path TEXT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `);
}

async function ensureBucket() {
  try {
    await s3.send(new HeadBucketCommand({ Bucket: S3_BUCKET }));
  } catch (error) {
    if (error.name !== 'NotFound' && error.$metadata?.httpStatusCode !== 404) throw error;
    await s3.send(new CreateBucketCommand({ Bucket: S3_BUCKET }));
  }
}

function sanitizeFilename(input) {
  const name = path.basename(input || '');
  if (!name || name === '.' || name === '..') return null;
  return name;
}

function authMiddleware(req, res, next) {
  if (AUTH_TOKEN && req.get('authorization') !== `Bearer ${AUTH_TOKEN}`) {
    return res.status(401).json({ ok: false, error: 'Unauthorized.' });
  }
  return next();
}

function hashAndCountStream() {
  const hash = crypto.createHash('sha256');
  let received = 0;
  const stream = new Transform({
    transform(chunk, encoding, callback) {
      received += chunk.length;
      hash.update(chunk);
      callback(null, chunk);
    },
  });
  stream.getDigest = () => hash.digest('hex');
  stream.getSize = () => received;
  return stream;
}

async function handleList(req, res) {
  const result = await pool.query(
    `SELECT name, size_bytes, sha256, created_at
     FROM file_metadata
     ORDER BY created_at DESC, name ASC`
  );
  return res.json({ ok: true, files: result.rows });
}

async function handleDelete(req, res) {
  const filename = sanitizeFilename(req.params.name);
  if (!filename) return res.status(400).json({ ok: false, error: 'Invalid filename.' });

  const result = await pool.query(
    'DELETE FROM file_metadata WHERE name = $1 RETURNING stored_path',
    [filename]
  );
  if (result.rowCount === 0) {
    return res.status(404).json({ ok: false, error: `File not found: ${filename}` });
  }

  await s3.send(new DeleteObjectCommand({ Bucket: S3_BUCKET, Key: result.rows[0].stored_path }));
  return res.json({ ok: true, message: `Deleted ${filename}` });
}

async function handleUpload(req, res) {
  const filename = sanitizeFilename(req.get('x-file-name'));
  const expectedSha = String(req.get('x-sha256') || '').toLowerCase();
  const size = Number(req.headers['content-length']);

  if (!filename) return res.status(400).json({ ok: false, error: 'Invalid filename.' });
  if (!Number.isInteger(size) || size < 0) {
    return res.status(400).json({ ok: false, error: 'Content-Length is required and must be valid.' });
  }
  if (!/^[a-f0-9]{64}$/.test(expectedSha)) {
    return res.status(400).json({ ok: false, error: 'Invalid sha256.' });
  }

  const body = hashAndCountStream();
  req.pipe(body);
  await s3.send(new PutObjectCommand({
    Bucket: S3_BUCKET,
    Key: filename,
    Body: body,
    ContentLength: size,
  }));

  const actualSha = body.getDigest();
  if (body.getSize() !== size || actualSha !== expectedSha) {
    await s3.send(new DeleteObjectCommand({ Bucket: S3_BUCKET, Key: filename }));
    return res.status(400).json({ ok: false, error: 'Checksum mismatch.' });
  }

  await pool.query(
    `INSERT INTO file_metadata(name, size_bytes, sha256, stored_path)
     VALUES($1, $2, $3, $4)
     ON CONFLICT (name)
     DO UPDATE SET
       size_bytes = EXCLUDED.size_bytes,
       sha256 = EXCLUDED.sha256,
       stored_path = EXCLUDED.stored_path,
       created_at = NOW()`,
    [filename, size, actualSha, filename]
  );

  return res.json({
    ok: true,
    message: `Stored ${filename}`,
    file: { name: filename, size_bytes: size, sha256: actualSha },
  });
}

async function startServer() {
  await initDb();
  await ensureBucket();

  const app = express();
  app.get('/health', (req, res) => res.json({ ok: true }));
  app.use('/api', authMiddleware);
  app.get('/api/files', handleList);
  app.post('/api/files', handleUpload);
  app.delete('/api/files/:name', handleDelete);
  app.use((error, req, res, next) => {
    console.error(error);
    if (res.headersSent) return next(error);
    return res.status(500).json({ ok: false, error: error.message });
  });

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`HTTP server listening on port ${PORT}`);
  });
}

startServer().catch((error) => {
  console.error('Failed to start server:', error.message);
  process.exit(1);
});
