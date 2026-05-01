# BGFT-Wizard-Web-Tool

Tool/API to compile on-demand BGFT installer payloads for PS4 via web.

## Web UI

- Main builder: `/`
- API documentation page: `/docs`

The docs page is generated with the current host automatically (for ready-to-copy curl examples).

## API Overview

Base URL example:

```bash
http://127.0.0.1:51584
```

### 1) Server Status

- Method: `GET`
- Endpoint: `/api/status`
- Description: Returns setup state.

```bash
curl -s "http://127.0.0.1:51584/api/status"
```

Example response:

```json
{
  "ready": true,
  "error": null
}
```

### 2) Session Logs

- Method: `GET`
- Endpoint: `/api/logs`
- Description: Returns logs for the current user session only.

```bash
curl -s "http://127.0.0.1:51584/api/logs"
```

Example response:

```json
{
  "logs": [
    "[12:00:00] Extracting metadata from: https://example.com/game.pkg",
    "[12:00:05] Compiling payload: GAME TITLE"
  ]
}
```

### 3) Extract PKG Metadata

- Method: `GET`
- Endpoint: `/api/meta`
- Query params:
  - `url` (required): PKG or manifest URL

```bash
curl -G -s "http://127.0.0.1:51584/api/meta" \
  --data-urlencode "url=https://example.com/game.pkg"
```

Success response (example):

```json
{
  "success": true,
  "title": "Game Name",
  "title_id": "CUSA00000",
  "content_id": "UP0000-CUSA00000_00-GAME000000000000",
  "category": "gd",
  "pkg_size": 1234567890,
  "pkg_type": "PS4GD",
  "icon_path": "http://127.0.0.1:51584/api/icon/GameName_CUSA00000.png"
}
```

### 4) Build Payload

- Method: `GET`
- Endpoint: `/api/build`
- Query params:
  - `url` (required)
  - `name` (required)
  - `id` (required)
  - `icon` (optional)
  - `type` (optional, default `PS4GD`)
  - `size` (optional, integer)

```bash
curl -G -s "http://127.0.0.1:51584/api/build" \
  --data-urlencode "url=https://example.com/game.pkg" \
  --data-urlencode "name=My Game" \
  --data-urlencode "id=CUSA00000" \
  --data-urlencode "icon=http://127.0.0.1:51584/api/icon/GameName_CUSA00000.png" \
  --data-urlencode "type=PS4GD" \
  --data-urlencode "size=1234567890"
```

Success response (example):

```json
{
  "success": true,
  "file": "0123456789abcdef0123456789abcdef.bin",
  "size": 270336,
  "logs": [
    "[12:01:01] Compiling payload: My Game",
    "[12:01:08] payload.bin generated successfully"
  ]
}
```

### 5) Download Compiled Payload

- Method: `GET`
- Endpoint: `/api/download/<filename>`
- Description: Downloads the file as `payload.bin`.

```bash
curl -L "http://127.0.0.1:51584/api/download/0123456789abcdef0123456789abcdef.bin" -o payload.bin
```

### 6) Get Icon

- Method: `GET`
- Endpoint: `/api/icon/<filename>`
- Description: Returns PNG icon extracted from package/manifest.

```bash
curl -L "http://127.0.0.1:51584/api/icon/GameName_CUSA00000.png" -o icon.png
```

### 7) Cleanup Old Payloads

- Method: `POST`
- Endpoint: `/api/cleanup`
- Description: Removes old temp payload files.

```bash
curl -X POST -s "http://127.0.0.1:51584/api/cleanup"
```

## Security Notes

- Full logs are server-side only (`logs/server.log` and process output).
- Browser/API clients only receive per-session user logs via `/api/logs` and build responses.

## Run

```bash
pip install -r requirements.txt
python main.py
```
