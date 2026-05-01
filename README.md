# BGFT-Wizard-Web-Tool

Web tool + HTTP API to compile BGFT PS4 payloads on demand.

## Web routes

- Builder UI: `/`
- API Docs page: `/docs`

The `/docs` page uses the current host automatically and provides copy buttons for command examples.

## Important curl note (Windows)

On PowerShell, `curl` is often an alias for `Invoke-WebRequest`. Use `curl.exe` to run the commands exactly as written.

## Base URL

Default local base URL:

```text
http://127.0.0.1:51584
```

## Session behavior

- User logs are isolated by session cookie.
- Server logs remain only in `logs/server.log` and terminal output.
- If you call `/api/logs` from terminal, keep cookies to stay in the same session:

```bash
curl.exe -c cookies.txt -b cookies.txt "http://127.0.0.1:51584/api/status"
```

Use `-c cookies.txt -b cookies.txt` in the other commands when you want persistent session logs.

---

## API Reference

### 1) GET `/api/status`

Returns environment setup status.

**Response fields**

- `ready` (boolean): `true` when build environment is ready.
- `error` (string or null): setup error reason if initialization failed.

**Command**

```bash
curl.exe "http://127.0.0.1:51584/api/status"
```

**Example response**

```json
{
  "ready": true,
  "error": null
}
```

---

### 2) GET `/api/logs`

Returns session-scoped user-visible logs.

**Response fields**

- `logs` (array of strings): timestamped log lines for current session only.

**Command**

```bash
curl.exe -c cookies.txt -b cookies.txt "http://127.0.0.1:51584/api/logs"
```

**Example response**

```json
{
  "logs": [
    "[12:00:00] Extracting metadata from: https://example.com/game.pkg",
    "[12:00:05] Compiling payload: GAME TITLE"
  ]
}
```

---

### 3) GET `/api/meta`

Extracts metadata from a PKG or manifest URL.

**Query parameters**

- `url` (required, string): direct PKG URL or manifest URL.

**Command**

```bash
curl.exe -c cookies.txt -b cookies.txt --get "http://127.0.0.1:51584/api/meta" --data-urlencode "url=https://example.com/game.pkg"
```

**Success response fields**

- `success` (boolean)
- `title` (string)
- `title_id` (string)
- `content_id` (string)
- `category` (string)
- `pkg_size` (integer, bytes)
- `pkg_type` (string, ex: `PS4GD`)
- `icon_path` (string URL or null)

**Error response**

- HTTP `400`: missing `url`
- HTTP `500`: extraction failed (`error` field)

**Success example**

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

---

### 4) GET `/api/build`

Compiles payload and returns generated output filename.

**Query parameters**

- `url` (required, string): PKG/manifest URL.
- `name` (required, string): package title.
- `id` (required, string): title/content id.
- `icon` (optional, string URL): icon URL.
- `type` (optional, string): defaults to `PS4GD`.
- `size` (optional, integer): package size in bytes.

**Command**

```bash
curl.exe -c cookies.txt -b cookies.txt --get "http://127.0.0.1:51584/api/build" --data-urlencode "url=https://example.com/game.pkg" --data-urlencode "name=My Game" --data-urlencode "id=CUSA00000" --data-urlencode "icon=http://127.0.0.1:51584/api/icon/GameName_CUSA00000.png" --data-urlencode "type=PS4GD" --data-urlencode "size=1234567890"
```

**Success response fields**

- `success` (boolean)
- `file` (string): generated filename (random `.bin` in temp output)
- `size` (integer): output size in bytes
- `logs` (array[string]): session logs related to build

**Error response**

- HTTP `400`: environment not ready or required params missing
- HTTP `500`: build failed (`error` + `logs`)

**Success example**

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

---

### 5) GET `/api/download/<filename>`

Downloads previously built payload as attachment (`payload.bin`).

**Path parameter**

- `filename` (required): value from `/api/build` response `file`.

**Command**

```bash
curl.exe -L "http://127.0.0.1:51584/api/download/0123456789abcdef0123456789abcdef.bin" -o payload.bin
```

**Error response**

- HTTP `400`: environment not ready
- HTTP `404`: file not found

---

### 6) GET `/api/icon/<filename>`

Returns extracted icon as PNG.

**Path parameter**

- `filename` (required): icon file name returned by metadata step.

**Command**

```bash
curl.exe -L "http://127.0.0.1:51584/api/icon/GameName_CUSA00000.png" -o icon.png
```

---

### 7) POST `/api/cleanup`

Deletes old temporary payload files from output directory.

**Command**

```bash
curl.exe -X POST "http://127.0.0.1:51584/api/cleanup"
```

**Example response**

```json
{
  "success": true
}
```

---

## Typical API flow for external integrations

1. Call `/api/status` and check `ready=true`.
2. Call `/api/meta` with package URL.
3. Call `/api/build` using metadata values.
4. Download with `/api/download/<file>`.
5. Optional: read `/api/logs` during steps for session progress.

## Run

```bash
pip install -r requirements.txt
python main.py
```
