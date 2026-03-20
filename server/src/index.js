const fs = require('fs');
const path = require('path');
const net = require('net');
const crypto = require('crypto');
const { Pool } = require('pg');

const PORT = Number(process.env.PORT || 4000);
const UPLOAD_DIR = process.env.UPLOAD_DIR || path.join(process.cwd(), 'uploads');
const DATABASE_URL = process.env.NEON_DATABASE_URL;
const AUTH_TOKEN = process.env.AUTH_TOKEN || '';
const DB_SSL = String(process.env.DB_SSL || '').toLowerCase();

if (!DATABASE_URL) {
  console.error('Missing NEON_DATABASE_URL in environment.');
  process.exit(1);
}

fs.mkdirSync(UPLOAD_DIR, { recursive: true });

const shouldUseSsl =
  DB_SSL === 'true' ||
  DB_SSL === '1' ||
  /sslmode=require/i.test(DATABASE_URL);

const poolConfig = {
  connectionString: DATABASE_URL,
};

if (shouldUseSsl) {
  poolConfig.ssl = { rejectUnauthorized: false };
}

const pool = new Pool(poolConfig);

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

function sendJsonLine(socket, payload) {
  socket.write(`${JSON.stringify(payload)}\n`);
  socket.end();
}

function parseHeader(line) {
  const [command, ...args] = line.trim().split(/\s+/);
  return { command: (command || '').toUpperCase(), args };
}

function sanitizeFilename(input) {
  const name = path.basename(input || '');
  if (!name || name === '.' || name === '..') return null;
  return name;
}

function authorizeArgs(args) {
  if (!AUTH_TOKEN) return { ok: true, args };

  const [providedToken, ...rest] = args;
  if (!providedToken || providedToken !== AUTH_TOKEN) {
    return { ok: false, error: 'Unauthorized.' };
  }

  return { ok: true, args: rest };
}

async function handleList(socket) {
  const result = await pool.query(
    `SELECT name, size_bytes, sha256, created_at
     FROM file_metadata
     ORDER BY created_at DESC, name ASC`
  );
  sendJsonLine(socket, { ok: true, files: result.rows });
}

async function handleDelete(socket, filenameArg) {
  const filename = sanitizeFilename(filenameArg);
  if (!filename) {
    sendJsonLine(socket, { ok: false, error: 'Invalid filename.' });
    return;
  }

  const result = await pool.query(
    'DELETE FROM file_metadata WHERE name = $1 RETURNING stored_path',
    [filename]
  );

  if (result.rowCount === 0) {
    sendJsonLine(socket, { ok: false, error: `File not found: ${filename}` });
    return;
  }

  const storedPath = result.rows[0].stored_path;
  if (storedPath && fs.existsSync(storedPath)) {
    fs.unlinkSync(storedPath);
  }

  sendJsonLine(socket, { ok: true, message: `Deleted ${filename}` });
}

function createSendHandler(socket, args, initialPayloadBuffer) {
  if (args.length < 3) {
    sendJsonLine(socket, { ok: false, error: 'SEND requires filename, size, and sha256.' });
    return null;
  }

  const filename = sanitizeFilename(args[0]);
  const size = Number(args[1]);
  const expectedSha = String(args[2]).toLowerCase();

  if (!filename) {
    sendJsonLine(socket, { ok: false, error: 'Invalid filename.' });
    return null;
  }
  if (!Number.isInteger(size) || size < 0) {
    sendJsonLine(socket, { ok: false, error: 'Invalid size.' });
    return null;
  }
  if (!/^[a-f0-9]{64}$/.test(expectedSha)) {
    sendJsonLine(socket, { ok: false, error: 'Invalid sha256.' });
    return null;
  }

  const storedPath = path.join(UPLOAD_DIR, filename);
  const tmpPath = `${storedPath}.part`;
  const fileWrite = fs.createWriteStream(tmpPath);
  const hash = crypto.createHash('sha256');

  let received = 0;
  let completed = false;

  const consumeChunk = async (chunk) => {
    if (completed) return;

    const remaining = size - received;
    const toTake = Math.min(remaining, chunk.length);
    const data = chunk.subarray(0, toTake);

    if (toTake > 0) {
      received += toTake;
      hash.update(data);
      if (!fileWrite.write(data)) {
        await new Promise((resolve) => fileWrite.once('drain', resolve));
      }
    }

    if (received === size) {
      completed = true;
      fileWrite.end();
      await new Promise((resolve) => fileWrite.once('finish', resolve));

      const actualSha = hash.digest('hex');
      if (actualSha !== expectedSha) {
        fs.unlinkSync(tmpPath);
        sendJsonLine(socket, { ok: false, error: 'Checksum mismatch.' });
        return;
      }

      if (fs.existsSync(storedPath)) {
        fs.unlinkSync(storedPath);
      }
      fs.renameSync(tmpPath, storedPath);

      await pool.query(
        `INSERT INTO file_metadata(name, size_bytes, sha256, stored_path)
         VALUES($1, $2, $3, $4)
         ON CONFLICT (name)
         DO UPDATE SET
           size_bytes = EXCLUDED.size_bytes,
           sha256 = EXCLUDED.sha256,
           stored_path = EXCLUDED.stored_path,
           created_at = NOW()`,
        [filename, size, actualSha, storedPath]
      );

      sendJsonLine(socket, {
        ok: true,
        message: `Stored ${filename}`,
        file: { name: filename, size_bytes: size, sha256: actualSha },
      });
    }
  };

  if (initialPayloadBuffer && initialPayloadBuffer.length > 0) {
    consumeChunk(initialPayloadBuffer).catch((error) => {
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
      sendJsonLine(socket, { ok: false, error: error.message });
    });
  }

  return {
    consumeChunk,
    onSocketEnd: () => {
      if (!completed) {
        if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
        sendJsonLine(socket, { ok: false, error: 'Connection ended before upload completed.' });
      }
    },
  };
}

async function startServer() {
  await initDb();

  const server = net.createServer((socket) => {
    let headerDone = false;
    let lineBuffer = Buffer.alloc(0);
    let sendState = null;

    socket.on('data', (chunk) => {
      (async () => {
        if (sendState) {
          await sendState.consumeChunk(chunk);
          return;
        }

        if (!headerDone) {
          lineBuffer = Buffer.concat([lineBuffer, chunk]);
          const newlineIndex = lineBuffer.indexOf(0x0a);
          if (newlineIndex === -1) {
            if (lineBuffer.length > 4096) {
              sendJsonLine(socket, { ok: false, error: 'Header too large.' });
            }
            return;
          }

          headerDone = true;
          const header = lineBuffer.subarray(0, newlineIndex).toString('utf8');
          const rest = lineBuffer.subarray(newlineIndex + 1);
          const { command, args } = parseHeader(header);
          const auth = authorizeArgs(args);

          if (!auth.ok) {
            sendJsonLine(socket, { ok: false, error: auth.error });
            return;
          }

          try {
            if (command === 'LIST') {
              await handleList(socket);
            } else if (command === 'DELETE') {
              await handleDelete(socket, auth.args[0]);
            } else if (command === 'SEND') {
              sendState = createSendHandler(socket, auth.args, rest);
            } else {
              sendJsonLine(socket, { ok: false, error: `Unknown command: ${command}` });
            }
          } catch (error) {
            sendJsonLine(socket, { ok: false, error: error.message });
          }
        }
      })().catch((error) => {
        sendJsonLine(socket, { ok: false, error: error.message });
      });
    });

    socket.on('end', () => {
      if (sendState) {
        sendState.onSocketEnd();
      }
    });

    socket.on('error', () => {
      socket.destroy();
    });
  });

  server.listen(PORT, '0.0.0.0', () => {
    console.log(`TCP server listening on port ${PORT}`);
  });
}

startServer().catch((error) => {
  console.error('Failed to start server:', error.message);
  process.exit(1);
});
