# Mashup Finder — Developer Guide

## What this is

A Djay Pro mashup compatibility finder. Reads `.djayMetadata` plist files from Djay Pro's library, stores everything in SQLite, and serves a web UI for finding harmonically compatible track pairs.

Runs as a native Mac app (WKWebView) or in a browser via `make run`.

## Architecture

| File | Responsibility |
|---|---|
| `matching.py` | Pure scoring logic — Camelot key compatibility, BPM matching, `score_pair`, `precompute_top_pairs` |
| `db.py` | SQLite schema, `init_db()`, `get_conn()` |
| `importer.py` | Djay Pro plist → SQLite ETL, mtime-based sync, blob extraction |
| `server.py` | HTTP REST API + embedded HTML/JS frontend (`HTML_PAGE`) |
| `app.py` | CLI entry point: sync then start server |
| `djay-mashup-app.py` | Legacy single-file app — reference only, do not delete |
| `Makefile` | `make run` / `make install` / `make test` |

**DB lives at:** `~/.mashup-finder/library.db` (~1GB, survives code changes and reinstalls)

**Djay Pro metadata path:**
`~/Library/Group Containers/VJXTL73S8G.com.algoriddim.userdata/Library/Application Support/Algoriddim/Metadata`

## Common tasks

```bash
make run       # start server, open in browser (dev mode)
make test      # run tests (skips slow integration tests)
make install   # bundle Python modules into .app and push to /Applications
```

### After changing any Python code
```bash
make install
```
This copies `matching.py db.py importer.py server.py` into the .app bundle and reinstalls to `/Applications`. Always does `rm -rf` before `cp -R` — merging leaves stale files (caused a crash once).

### Editing the frontend
All HTML/JS/CSS is inside `HTML_PAGE` in `server.py` — one big raw string. After editing, verify with `python -c "import server"` before running `make install`.

### DB schema changes
1. Update `_SCHEMA` in `db.py`
2. Update `TRACK_COLS` in `importer.py`
3. Update `TRACK_SCALAR_COLS` in `server.py` (scalar fields only — no blobs)
4. Update column tests in `tests/test_db.py`
5. Warn user: existing `~/.mashup-finder/library.db` won't auto-migrate, needs to be deleted and re-synced

## API endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/status` | Always returns `{"stage": "ready"}` |
| `GET` | `/api/stats` | Track count + key distribution |
| `GET` | `/api/tracks` | Scalar fields only, supports `q`, `key`, `limit` — never returns blobs |
| `GET` | `/api/pairs` | Live scoring via matching.py |
| `GET` | `/api/top-pairs` | Precomputed pairs, supports `offset`, `limit`, `min_score`, `q`, `key`, `match` |
| `GET` | `/api/tracks/:id/waveform` | Base64 blobs: `beats`, `waveform_low`, `waveform_max`, `waveform_colors`, `transient_pos`, `transient_energy` |
| `POST` | `/api/import` | Trigger manual re-sync |

## Gotchas

**Blob format:** All blobs are zlib-compressed big-endian. Beat timestamps are `float32 BE` — little-endian gives garbage values. Stored as-is in SQLite (don't decompress before storing).

**Frontend decompression:** Browser uses `DecompressionStream('deflate-raw')` — must strip the 2-byte zlib header first: `bytes.slice(2)`.

**Waveform API key:** The endpoint returns `beats` (not `beats_blob`) — renamed on the way out.

**bpm_stability:** `statistics.stdev` needs ≥ 2 intervals = ≥ 3 beats. Guard is `if len(beat_times) < 4`.

**SQLite foreign keys:** Not enforced by default. `PRAGMA foreign_keys = ON` is set in `db._open()` on every connection.

**Mac app install:** Always `rm -rf "/Applications/Mashup Finder.app"` before `cp -R` — merging leaves stale files. `make install` handles this.

**top_pairs recompute:** Runs only when tracks change. Takes ~5 min on 12k tracks. Second launch is ~1s (nothing changed).

## Mac app structure

```
Mashup Finder.app/Contents/
  MacOS/launcher          # shell script, finds Python with PyObjC
  Resources/native_app.py # PyObjC WKWebView wrapper
  Resources/*.py          # bundled copies of matching/db/importer/server
```

`native_app.py` adds `Resources/` to `sys.path` — the bundled `.py` files are completely independent of the project directory.

## Tests

```bash
python -m pytest tests/ -v                            # all tests (~10min, hits real Djay library)
python -m pytest tests/ -v -k "not run_sync_populates_db or run_sync_idempotent"  # fast
```

Slow tests (`test_run_sync_populates_db`, `test_run_sync_idempotent`) parse 14k real metadata files. Only run when changing `importer.py` significantly.
