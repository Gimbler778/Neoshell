# Neoshell CLI Reference (`neoshell`)

The Neoshell CLI (`neoshell-cli` package) provides a modern terminal interface to upload, download, share, list, and manage files in your Neoshell personal cloud.

---

## Installation

### Recommended: `pipx` (isolated tool environment)

```bash
pipx install neoshell-cli
```

### Alternative: `pip`

```bash
pip install --user neoshell-cli
```

### Local Development / From Source

```bash
git clone https://github.com/Gimbler778/Neoshell.git
cd Neoshell
pip install -e ./client
```

---

## Configuration & Precedence

Neoshell resolves server connection details and credentials using strict precedence (highest first):

1. **CLI Flags**: `--url <URL>`, `--token <TOKEN>`
2. **Environment Variables**:
   - `NEOSHELL_URL` and `NEOSHELL_TOKEN`
   - Legacy: `SERVER_URL` and `AUTH_TOKEN`
3. **Saved Configuration File**: `config.toml`
4. **Default**: `http://127.0.0.1:8080` (URL only, local development)

### Config File Location

Neoshell stores configuration at standard user directories:
- **Linux:** `~/.config/neoshell/config.toml`
- **macOS:** `~/Library/Application Support/neoshell/config.toml`
- **Windows:** `%APPDATA%\neoshell\config.toml`

> Override directory: You can set `NEOSHELL_CONFIG_DIR=/custom/path` to relocate the configuration directory (useful for testing or multi-profile setups).

---

## Global Options

The following flags can be passed globally before any command or as command arguments:

- `--version`, `-v`: Display CLI version and exit.
- `--url TEXT`: Server base URL (e.g. `https://my-app.koyeb.app` or `http://127.0.0.1:8080`).
- `--token TEXT`: Shared Bearer authentication token.
- `--json`: Output machine-readable JSON where applicable.
- `--quiet`, `-q`: Suppress non-essential progress bars and styling.
- `--timeout FLOAT`: Request timeout in seconds (default: `30.0`).
- `--help`: Show command documentation.

---

## Commands

### `neoshell login`

Verify server connectivity (`/health`) and save configuration.

```bash
# Configure both URL and token
neoshell login --url https://my-app.koyeb.app --token my_secret_token

# Update only token for existing server
neoshell login --token new_token
```

### `neoshell logout`

Clear saved authentication credentials or remove entire configuration.

```bash
# Clear saved token
neoshell logout

# Delete complete configuration file
neoshell logout --all
```

### `neoshell status`

Display server connectivity status, health check response, token configuration, file count, and config path.

```bash
neoshell status
neoshell status --json
```

### `neoshell list`

List all stored files including name, size, SHA-256 checksum, and upload timestamp.

```bash
neoshell list
neoshell list --json
```

### `neoshell upload`

Upload one or more local files. Displays transfer progress with dynamic speed and ETA. Continues past errors if multiple files are provided.

```bash
# Single file
neoshell upload ./photo.jpg

# Multiple files
neoshell upload file1.txt file2.zip file3.tar.gz
```

### `neoshell download`

Download a file from storage, verify its SHA-256 checksum against server headers, and atomically save it.

```bash
# Download to current directory
neoshell download photo.jpg

# Download to custom path or folder
neoshell download photo.jpg -o ./downloads/photo.jpg
neoshell download photo.jpg -o ./downloads/
```

### `neoshell share`

Generate a temporary presigned S3 download link for instant file sharing.

```bash
# Share with default 24h expiration
neoshell share document.pdf

# Specify duration (supports s, m, h, d, max 7d)
neoshell share document.pdf --expires 1h
neoshell share document.pdf --expires 7d

# Automatically copy generated link to system clipboard
neoshell share document.pdf --expires 2h --clip
```

### `neoshell delete`

Delete one or more files from remote storage and metadata database.

```bash
# Interactive confirmation
neoshell delete document.pdf

# Skip confirmation prompt
neoshell delete document.pdf --yes

# Delete multiple files
neoshell delete file1.txt file2.txt -y
```

### `neoshell info`

Inspect file metadata and checksum without downloading the payload.

```bash
neoshell info document.pdf
neoshell info document.pdf --json
```

---

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Runtime error (e.g. transfer failed, invalid credentials, file not found) |
| `2` | CLI usage error (e.g. invalid arguments or unknown options) |
