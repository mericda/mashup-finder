# Mashup Finder — Database & Architecture Design

**Date:** 2026-05-22  
**Status:** Approved

## Overview

Migrate the Mashup Finder from a single-file app that re-parses Djay Pro's plist files on every launch into a proper SQLite-backed architecture. Goals: instant startup, resilience against Djay Pro data loss, clean REST API as the foundation for future native Mac and iOS apps, and full exploitation of all data Djay Pro stores per track — including waveforms, beat grids, transients, and variable-BPM segments.

---

## File Structure

```
mashup-finder/
  app.py           # orchestrator: runs importer then starts server
  importer.py      # Djay Pro plists → SQLite (ETL)
  server.py        # REST API reading from SQLite
  matching.py      # shared scoring logic (find_pairs, key compatibility, etc.)
  djay-mashup-app.py  # legacy single-file app, kept for reference
  docs/
    superpowers/specs/
      2026-05-22-mashup-finder-database-design.md
```

Database lives at `~/.mashup-finder/library.db` — outside the project folder so it survives code changes and is easy to back up.

---

## Database Schema

### `tracks`

```sql
CREATE TABLE tracks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Core metadata
    name              TEXT NOT NULL,
    artist            TEXT NOT NULL,
    duration          INTEGER,          -- seconds
    source            TEXT,             -- 'local', 'tidal', 'soundcloud', 'apple_music'
    persistent_id     TEXT,             -- e.g. 'tidal:track:170913220'
    quality           INTEGER,

    -- Key analysis
    camelot           TEXT,             -- e.g. '8B', '3A'
    key_name          TEXT,             -- e.g. 'C maj'
    key_conf          REAL,
    second_key        TEXT,
    tuning            REAL,             -- reference tuning in Hz (e.g. 440.0)

    -- BPM / beat grid
    bpm               REAL,             -- effective BPM (may be user-adjusted)
    analyzed_bpm      REAL,             -- raw ML-analyzed BPM
    bpm_conf          REAL,
    straight          INTEGER,          -- 0/1: straight grid detected
    forced_straight   INTEGER,          -- 0/1: user manually forced straight grid
    grid_dev          REAL,             -- straightGridDistance
    first_downbeat    INTEGER,          -- beat index of first downbeat
    time_signature    INTEGER,          -- e.g. 4 = 4/4
    beat_count        INTEGER,          -- total detected beats
    bpm_stability     REAL,             -- std dev of beat intervals (lower = more consistent)
    bpm_segment_count INTEGER,          -- >1 means variable-tempo track
    bpm_segments      TEXT,             -- JSON: [{time, bpm}, ...] for each tempo segment

    -- Gain / dynamics
    energy            REAL,             -- AutoTitleGain in dB (loudness)
    dyn_range         REAL,             -- AutoTitleGainLoudnessRange in dB

    -- Transients
    transient_count   INTEGER,

    -- Waveform / binary blobs (stored compressed, served as base64)
    waveform_low      BLOB,             -- low-rate uint16 amplitude (~2048 samples, zlib)
    waveform_max      BLOB,             -- low-rate uint16 peak amplitude (zlib)
    waveform_colors   BLOB,             -- high-rate RGB565 colored waveform ~36k samples (zlib)
    beats_blob        BLOB,             -- beat timestamps, big-endian float32 (zlib)
    transient_pos     BLOB,             -- transient timestamps, big-endian float32 (zlib)
    transient_energy  BLOB,             -- transient energies 0.0–1.0, big-endian float32 (zlib)

    -- Sync tracking
    file_path         TEXT UNIQUE,      -- source .djayMetadata path
    file_mtime        REAL              -- mtime at last import, for change detection
);

CREATE INDEX idx_tracks_camelot ON tracks(camelot);
CREATE INDEX idx_tracks_bpm     ON tracks(bpm);
```

### `top_pairs`

```sql
CREATE TABLE top_pairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    track_a_id      INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    track_b_id      INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    score           REAL,
    bpm_diff        REAL,
    bpm_match       TEXT,    -- 'direct', 'double', 'half'
    key_match       TEXT,    -- 'same', 'adjacent', 'relative'
    energy_diff     REAL,
    grid_match      INTEGER, -- 0/1
    tuning_diff     REAL,
    dr_diff         REAL,
    warnings        TEXT,    -- JSON array: ["tuning", "energy", "grid", "variable_bpm"]
    bpm_score       REAL,
    key_score       REAL,
    energy_score    REAL,
    grid_score      REAL,
    dr_score        REAL,
    tuning_score    REAL,
    conf_score      REAL,
    second_key_match INTEGER -- 0/1
);

CREATE INDEX idx_top_pairs_score ON top_pairs(score DESC);
```

---

## Data Extraction

All binary blobs in the plist are zlib-compressed and stored as-is (bytes copied directly into SQLite BLOB columns, no recompression). Format per blob:

| Column | Plist key | Format |
|---|---|---|
| `waveform_low` | `waveInfoCompact.compressedLowRateWaveSamples` | uint16 BE, ~2048 samples |
| `waveform_max` | `waveInfoCompact.compressedLowRateWaveSamplesMax` | uint16 BE, ~2048 samples |
| `waveform_colors` | `waveColorsInfo.compressedNormalRateWaveSamplesColors` | RGB565 BE, ~36k samples |
| `beats_blob` | `deepBeatTrackerInfo.compressedBeats` | float32 BE, seconds |
| `transient_pos` | `deepBeatTrackerInfo.compressedTransientPositions` | float32 BE, seconds |
| `transient_energy` | `deepBeatTrackerInfo.compressedTransientEnergies` | float32 BE, 0.0–1.0 |

### Source mapping
| `info.source` | Stored as |
|---|---|
| 1 | `local` |
| 3 | `tidal` |
| 4 | `soundcloud` |
| 7 | `apple_music` |

### Derived metrics computed during import
- **`bpm_stability`**: std dev of intervals between consecutive beat timestamps (lower = more metronomic)
- **`bpm_segment_count`** + **`bpm_segments`**: decoded from `compressedBPMChangeTimes` + `compressedPrevalentBPMs`; a track with `bpm_segment_count > 1` has variable tempo
- **`beat_count`**: count of float32s in `compressedBeats`
- **`transient_count`**: count of float32s in `compressedTransientPositions`

---

## Sync Logic

### Auto-sync on launch (`app.py`)
1. Open (or create) `~/.mashup-finder/library.db`
2. Run importer: scan all `*.djayMetadata` files, compare file mtime against `file_mtime` in DB
   - New file → parse + insert
   - Changed file → parse + update
   - DB row with no matching file → delete
3. If any rows were added/updated/deleted → `DELETE FROM top_pairs` then recompute and reinsert all 500 top pairs
4. Start HTTP server (DB is ready; no loading screen needed)

### Manual import (`POST /api/import`)
Same logic as above, triggered by UI. Returns:
```json
{ "added": 12, "updated": 3, "removed": 1, "top_pairs_recomputed": true }
```

---

## REST API

All existing endpoints are preserved. Additions and changes:

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Server readiness (now instant — no plist parsing) |
| `GET` | `/api/stats` | Track count, key distribution |
| `GET` | `/api/tracks` | Track list (no blobs; query params: `q`, `key`, `limit`) |
| `GET` | `/api/pairs` | Pairs for a track (`track`, `bpm_range`, `limit`) |
| `GET` | `/api/top-pairs` | Top precomputed pairs (`offset`, `limit`, `min_score`, `q`, `key`, `match`) |
| `GET` | `/api/tracks/:id/waveform` | Waveform + beat + transient blobs as base64 JSON |
| `POST` | `/api/import` | Trigger manual re-sync |

`/api/tracks` never returns blob columns — only scalar fields. Blobs are fetched separately via `/api/tracks/:id/waveform` only when the detail modal opens.

---

## Frontend Changes

### Import button
Added to the header. On click: calls `POST /api/import`, shows progress (`+12 tracks, 3 updated, 1 removed`), refreshes track list on completion.

### Pair detail modal — waveform section
When a pair detail opens:
1. Fetch `/api/tracks/:id/waveform` for both tracks in parallel
2. Render two waveforms side by side using the RGB565 color data (36k samples → canvas)
3. Overlay beat markers from `beats_blob`
4. Overlay transient energy as brightness variation
5. Show BPM segment dividers with tempo labels if `bpm_segment_count > 1`

### Scoring additions
- `bpm_stability` feeds into scoring: penalize pairs where either track has high BPM variance
- `bpm_segment_count > 1` adds a `variable_bpm` warning badge in the pair card and detail modal

---

## Platform Optionality

The SQLite DB at `~/.mashup-finder/library.db` and the REST API are the stable contract for future platforms:

- **Native Mac app**: wrap the Python server with py2app or Platypus; a SwiftUI shell opens a WKWebView pointed at localhost
- **iOS app**: SwiftUI app calls the same REST endpoints when on the same network as the Mac; or reads SQLite directly via GRDB if the DB is synced via iCloud Drive
- **Hosted web**: swap SQLite for Postgres, deploy server to any cloud provider — the API surface doesn't change

---

## Dependencies

Zero new Python dependencies. Everything uses stdlib: `sqlite3`, `zlib`, `struct`, `plistlib`, `http.server`.
