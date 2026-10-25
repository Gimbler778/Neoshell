# neoshell-cli

CLI client for Neoshell personal cloud file manager.

## Installation

```bash
pipx install neoshell-cli
# or
pip install neoshell-cli
```

## Quick Start

```bash
# Login to your hosted or local instance
neoshell login --url https://YOUR-APP.example.com --token YOUR_TOKEN

# Check connection status
neoshell status

# Upload files
neoshell upload ./photo.zip ./notes.txt

# List files
neoshell list

# Download a file
neoshell download photo.zip

# Create a temporary shareable link
neoshell share photo.zip --expires 24h

# Delete a file
neoshell delete photo.zip --yes

# Logout
neoshell logout
```
