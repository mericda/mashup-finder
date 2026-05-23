# Mashup Finder Database Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate Mashup Finder from re-parsing Djay Pro plists on every launch to a SQLite-backed architecture with instant startup, full data extraction (waveforms, beats, transients, BPM segments), and a clean REST API.

**Architecture:** Split `djay-mashup-app.py` into four focused modules: `matching.py` (scoring logic), `db.py` (schema), `importer.py` (plist→SQLite ETL with sync), `server.py` (HTTP REST API + embedded frontend), and `app.py` (orchestrator). DB lives at `~/.mashup-finder/library.db`. All binary blobs stored compressed as-is from plist.

**Tech Stack:** Python 3 stdlib only — `sqlite3`, `zlib`, `struct`, `plistlib`, `http.server`. Tests use `pytest`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `matching.py` | Create | Key/camelot logic, pair scoring, `score_pair`, `find_pairs_for_track`, `precompute_top_pairs` |
| `db.py` | Create | Schema DDL, `init_db()`, `get_conn()` |
| `importer.py` | Create | Plist parsing, blob extraction, derived metrics, `run_sync()` |
| `server.py` | Create | All HTTP endpoints + embedded `HTML_PAGE` from legacy file |
| `app.py` | Create | Orchestrator: `run_sync()` then `MashupServer` |
| `djay-mashup-app.py` | Keep | Legacy reference — do not delete |
| `tests/__init__.py` | Create | Empty |
| `tests/test_matching.py` | Create | Unit tests for scoring and key logic |
| `tests/test_db.py` | Create | Schema creation tests |
| `tests/test_importer.py` | Create | Plist parsing and derived metrics tests |
| `tests/test_server.py` | Create | Integration tests for API endpoints |

---

### Task 1: Extract matching.py

**Files:**
- Create: `matching.py`
- Create: `tests/__init__.py`
- Create: `tests/test_matching.py`

- [ ] **Step 1: Write failing tests**

Create `tests/__init__.py` (empty file), then create `tests/test_matching.py`:

```python
import pytest
from matching import (
    key_index_to_camelot, key_index_to_name, get_compatible_keys,
    key_match_type, score_pair, _is_same_track, _artist_tokens,
    build_key_groups, find_pairs_for_track,
)


def test_key_index_to_camelot():
    assert key_index_to_camelot(0) == "8B"
    assert key_index_to_camelot(1) == "8A"
    assert key_index_to_camelot(23) == "1A"
    assert key_index_to_camelot(-1) is None
    assert key_index_to_camelot(24) is None


def test_get_compatible_keys():
    keys = get_compatible_keys("8B")
    assert keys == {"8B", "7B", "9B", "8A"}


def test_get_compatible_keys_wraps():
    keys = get_compatible_keys("1B")
    assert "12B" in keys
    assert "2B" in keys
    assert "1A" in keys


def test_key_match_type():
    assert key_match_type("8B", "8B") == "same"
    assert key_match_type("8B", "8A") == "relative"
    assert key_match_type("8B", "7B") == "adjacent"
    assert key_match_type("8B", "9B") == "adjacent"
    assert key_match_type("1B", "12B") == "adjacent"
    assert key_match_type("8B", "5A") is None


def test_is_same_track_exact():
    assert _is_same_track({"name": "Song", "artist": "A"}, {"name": "Song", "artist": "A"})


def test_is_same_track_feat_variant():
    a = {"name": "Song (feat. X)", "artist": "A"}
    b = {"name": "Song", "artist": "A"}
    assert _is_same_track(a, b)


def test_is_same_track_different():
    assert not _is_same_track({"name": "Song A", "artist": "A"}, {"name": "Song B", "artist": "A"})


def _track(**kw):
    defaults = dict(id=1, name="T", artist="A", bpm=128.0, camelot="8B",
                    key_conf=0.9, energy=-10.0, dyn_range=6.0, straight=True,
                    grid_dev=0.05, tuning=440.0, second_key=None,
                    bpm_stability=0.01, bpm_segment_count=1)
    return {**defaults, **kw}


def test_score_pair_same_key():
    a = _track(id=1)
    b = _track(id=2)
    result = score_pair(a, b, bpm_range=6)
    assert result is not None
    assert result["score"] > 0.9
    assert result["key_match"] == "same"
    assert result["bpm_match"] == "direct"
    assert result["warnings"] == []


def test_score_pair_bpm_out_of_range():
    a = _track(id=1)
    b = _track(id=2, bpm=145.0)
    assert score_pair(a, b, bpm_range=6) is None


def test_score_pair_double_time():
    a = _track(id=1, bpm=128.0)
    b = _track(id=2, bpm=64.0)
    result = score_pair(a, b, bpm_range=6)
    assert result is not None
    assert result["bpm_match"] == "double"


def test_score_pair_variable_bpm_warning():
    a = _track(id=1)
    b = _track(id=2, bpm_segment_count=3)
    result = score_pair(a, b, bpm_range=6)
    assert "variable_bpm" in result["warnings"]


def test_build_key_groups():
    tracks = [_track(id=1, camelot="8B"), _track(id=2, camelot="8B"), _track(id=3, camelot="7A")]
    groups = build_key_groups(tracks)
    assert 1 in groups["8B"]
    assert 2 in groups["8B"]
    assert 3 in groups["7A"]


def test_find_pairs_for_track():
    t1 = _track(id=1, camelot="8B", artist="Artist A")
    t2 = _track(id=2, camelot="8B", artist="Artist B")
    t3 = _track(id=3, camelot="3A", artist="Artist C")  # incompatible key
    tracks_by_id = {1: t1, 2: t2, 3: t3}
    key_groups = build_key_groups([t1, t2, t3])
    pairs = find_pairs_for_track(t1, tracks_by_id, key_groups, bpm_range=6)
    ids = [p["track"]["id"] for p in pairs]
    assert 2 in ids
    assert 3 not in ids
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_matching.py -v 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'matching'`

- [ ] **Step 3: Create matching.py**

```python
import heapq
import re
from collections import defaultdict

KEYINDEX_TO_CAMELOT = [
    "8B", "8A", "3B", "3A", "10B", "10A", "5B", "5A",
    "12B", "12A", "7B", "7A", "2B", "2A", "9B", "9A",
    "4B", "4A", "11B", "11A", "6B", "6A", "1B", "1A",
]
KEYINDEX_TO_NAME = [
    "C maj", "A min", "Db maj", "Bb min", "D maj", "B min",
    "Eb maj", "C min", "E maj", "C# min", "F maj", "D min",
    "Gb maj", "Eb min", "G maj", "E min", "Ab maj", "F min",
    "A maj", "F# min", "Bb maj", "G min", "B maj", "Ab min",
]

_NORM_RE = re.compile(r'[^a-z0-9]')
_FEAT_RE = re.compile(r'[\(\[][^)\]]*\b(?:feat|ft)\.?[^)\]]*[\)\]]', re.IGNORECASE)
_ARTIST_SPLIT_RE = re.compile(r'[,&]| and | feat\.? | ft\.? ', re.IGNORECASE)


def key_index_to_camelot(key_index):
    if key_index < 0 or key_index > 23:
        return None
    return KEYINDEX_TO_CAMELOT[key_index]


def key_index_to_name(key_index):
    if key_index < 0 or key_index > 23:
        return "Unknown"
    return KEYINDEX_TO_NAME[key_index]


def _parse_camelot(s):
    return int(s[:-1]), s[-1]


def get_compatible_keys(camelot):
    num, let = _parse_camelot(camelot)
    prev_n = 12 if num == 1 else num - 1
    next_n = 1 if num == 12 else num + 1
    return {camelot, f"{prev_n}{let}", f"{next_n}{let}", f"{num}{'A' if let == 'B' else 'B'}"}


def key_match_type(cam1, cam2):
    if cam1 == cam2:
        return "same"
    n1, l1 = _parse_camelot(cam1)
    n2, l2 = _parse_camelot(cam2)
    if n1 == n2 and l1 != l2:
        return "relative"
    if l1 == l2:
        diff = abs(n1 - n2)
        if diff == 1 or diff == 11:
            return "adjacent"
    return None


def _normalize(s):
    return _NORM_RE.sub('', s.lower())


def _strip_feat(name):
    return _FEAT_RE.sub('', name).strip()


def _artist_tokens(artist):
    parts = _ARTIST_SPLIT_RE.split(artist)
    return {_normalize(p) for p in parts if _normalize(p)}


def _is_same_track(a, b):
    na = _normalize(_strip_feat(a["name"]))
    nb = _normalize(_strip_feat(b["name"]))
    ta = _artist_tokens(a["artist"])
    tb = _artist_tokens(b["artist"])
    overlap = bool(ta & tb)
    if na == nb and overlap:
        return True
    if overlap and min(len(na), len(nb)) > 4 and (na in nb or nb in na):
        return True
    if _normalize(a["name"]) == _normalize(b["name"]) and _normalize(a["artist"]) == _normalize(b["artist"]):
        return True
    return False


def score_pair(t, other, bpm_range=6):
    """Score two track dicts. Returns result dict or None if BPM-incompatible."""
    diff = abs(t["bpm"] - other["bpm"])
    bpm_match, eff_diff = "direct", diff
    if diff > bpm_range:
        d2 = abs(t["bpm"] - other["bpm"] * 2)
        d3 = abs(t["bpm"] * 2 - other["bpm"])
        if d2 <= bpm_range:
            eff_diff, bpm_match = d2, "double"
        elif d3 <= bpm_range:
            eff_diff, bpm_match = d3, "half"
        else:
            return None

    km = key_match_type(t["camelot"], other["camelot"])
    bpm_score = max(0, 1 - eff_diff / bpm_range)
    key_score = {"same": 1.0, "relative": 0.7, "adjacent": 0.5}.get(km, 0)
    conf = (t["key_conf"] + other["key_conf"]) / 2
    energy_diff = abs(t["energy"] - other["energy"])
    energy_score = max(0, 1 - energy_diff / 12)
    both_straight = bool(t["straight"]) and bool(other["straight"])
    grid_score = 1.0 if both_straight else (0.5 if bool(t["straight"]) == bool(other["straight"]) else 0.3)
    dr_diff = abs(t["dyn_range"] - other["dyn_range"])
    dr_score = max(0, 1 - dr_diff / 10)
    tuning_diff = abs(t["tuning"] - other["tuning"])
    tuning_ok = tuning_diff <= 3.0
    tuning_score = 1.0 if tuning_diff <= 1.0 else (0.7 if tuning_ok else 0.3)
    second_key_bonus = 0.05 if (t.get("second_key") and t["second_key"] == other.get("second_key")) else 0

    avg_stability = ((t.get("bpm_stability") or 0) + (other.get("bpm_stability") or 0)) / 2
    stability_penalty = min(0.1, avg_stability * 0.5) if avg_stability > 0.05 else 0

    score = round(
        bpm_score * 0.25 + key_score * 0.30 + energy_score * 0.15
        + grid_score * 0.10 + dr_score * 0.05 + tuning_score * 0.10
        + conf * 0.05 + second_key_bonus - stability_penalty,
        3,
    )

    warnings = []
    if not tuning_ok:
        warnings.append("tuning")
    if energy_diff > 8:
        warnings.append("energy")
    if bool(t["straight"]) != bool(other["straight"]):
        warnings.append("grid")
    if (t.get("bpm_segment_count") or 1) > 1 or (other.get("bpm_segment_count") or 1) > 1:
        warnings.append("variable_bpm")

    return {
        "score": score, "bpm_diff": round(eff_diff, 1), "bpm_match": bpm_match,
        "key_match": km, "energy_diff": round(energy_diff, 1),
        "grid_match": both_straight, "tuning_diff": round(tuning_diff, 1),
        "dr_diff": round(dr_diff, 1), "warnings": warnings,
        "bpm_score": round(bpm_score, 3), "key_score": round(key_score, 3),
        "energy_score": round(energy_score, 3), "grid_score": round(grid_score, 3),
        "dr_score": round(dr_score, 3), "tuning_score": round(tuning_score, 3),
        "conf_score": round(conf, 3), "second_key_match": second_key_bonus > 0,
        "bpm_a": t["bpm"], "bpm_b": other["bpm"],
        "energy_a": t["energy"], "energy_b": other["energy"],
        "tuning_a": t["tuning"], "tuning_b": other["tuning"],
        "dr_a": t["dyn_range"], "dr_b": other["dyn_range"],
        "straight_a": t["straight"], "straight_b": other["straight"],
        "grid_dev_a": t["grid_dev"], "grid_dev_b": other["grid_dev"],
        "second_key_a": t.get("second_key"), "second_key_b": other.get("second_key"),
    }


def build_key_groups(tracks):
    groups = defaultdict(list)
    for t in tracks:
        groups[t["camelot"]].append(t["id"])
    return dict(groups)


def find_pairs_for_track(track, tracks_by_id, key_groups, bpm_range=6, limit=200):
    pairs = []
    for ck in get_compatible_keys(track["camelot"]):
        for other_id in key_groups.get(ck, []):
            if other_id == track["id"]:
                continue
            other = tracks_by_id[other_id]
            if _is_same_track(track, other):
                continue
            result = score_pair(track, other, bpm_range)
            if result is None:
                continue
            pairs.append({"track": other, **result})
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs[:limit]


def precompute_top_pairs(tracks, key_groups, top_n=500):
    tracks_by_id = {t["id"]: t for t in tracks}
    heap, seen = [], set()
    for t in tracks:
        for p in find_pairs_for_track(t, tracks_by_id, key_groups, bpm_range=6, limit=10):
            oid = p["track"]["id"]
            canon = (min(t["id"], oid), max(t["id"], oid))
            if canon in seen:
                continue
            seen.add(canon)
            if _artist_tokens(t["artist"]) & _artist_tokens(p["track"]["artist"]):
                continue
            entry = {"track_a": t, "track_b": p["track"],
                     **{k: v for k, v in p.items() if k != "track"}}
            if len(heap) < top_n:
                heapq.heappush(heap, (p["score"], canon, entry))
            elif p["score"] > heap[0][0]:
                heapq.heapreplace(heap, (p["score"], canon, entry))
    return [item[2] for item in sorted(heap, key=lambda x: x[0], reverse=True)]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_matching.py -v
```

Expected: All 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add matching.py tests/__init__.py tests/test_matching.py
git commit -m "feat: extract matching.py with bpm_stability penalty and variable_bpm warning"
```

---

### Task 2: Create db.py — schema and connection helper

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
import os, tempfile
from db import init_db


def test_init_creates_tables():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "tracks" in tables
        assert "top_pairs" in tables
        conn.close()
    finally:
        os.unlink(path)


def test_tracks_has_required_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(tracks)")}
        for col in ["name", "artist", "camelot", "bpm", "bpm_stability",
                    "bpm_segments", "beats_blob", "waveform_colors",
                    "transient_pos", "transient_energy", "source",
                    "persistent_id", "file_path", "file_mtime"]:
            assert col in cols, f"Missing column: {col}"
        conn.close()
    finally:
        os.unlink(path)


def test_top_pairs_has_required_columns():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(top_pairs)")}
        for col in ["track_a_id", "track_b_id", "score", "warnings", "second_key_match"]:
            assert col in cols, f"Missing column: {col}"
        conn.close()
    finally:
        os.unlink(path)


def test_init_idempotent():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        conn.close()
        conn2 = init_db(path)  # must not raise
        conn2.close()
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_db.py -v 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 3: Create db.py**

```python
import os
import sqlite3

DEFAULT_DB_PATH = os.path.expanduser("~/.mashup-finder/library.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    artist            TEXT NOT NULL,
    duration          INTEGER,
    source            TEXT,
    persistent_id     TEXT,
    quality           INTEGER,
    camelot           TEXT,
    key_name          TEXT,
    key_conf          REAL,
    second_key        TEXT,
    tuning            REAL,
    bpm               REAL,
    analyzed_bpm      REAL,
    bpm_conf          REAL,
    straight          INTEGER,
    forced_straight   INTEGER,
    grid_dev          REAL,
    first_downbeat    INTEGER,
    time_signature    INTEGER,
    beat_count        INTEGER,
    bpm_stability     REAL,
    bpm_segment_count INTEGER,
    bpm_segments      TEXT,
    energy            REAL,
    dyn_range         REAL,
    transient_count   INTEGER,
    waveform_low      BLOB,
    waveform_max      BLOB,
    waveform_colors   BLOB,
    beats_blob        BLOB,
    transient_pos     BLOB,
    transient_energy  BLOB,
    file_path         TEXT UNIQUE,
    file_mtime        REAL
);

CREATE TABLE IF NOT EXISTS top_pairs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    track_a_id       INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    track_b_id       INTEGER REFERENCES tracks(id) ON DELETE CASCADE,
    score            REAL,
    bpm_diff         REAL,
    bpm_match        TEXT,
    key_match        TEXT,
    energy_diff      REAL,
    grid_match       INTEGER,
    tuning_diff      REAL,
    dr_diff          REAL,
    warnings         TEXT,
    bpm_score        REAL,
    key_score        REAL,
    energy_score     REAL,
    grid_score       REAL,
    dr_score         REAL,
    tuning_score     REAL,
    conf_score       REAL,
    second_key_match INTEGER
);

CREATE INDEX IF NOT EXISTS idx_tracks_camelot ON tracks(camelot);
CREATE INDEX IF NOT EXISTS idx_tracks_bpm ON tracks(bpm);
CREATE INDEX IF NOT EXISTS idx_top_pairs_score ON top_pairs(score DESC);
"""


def init_db(path=DEFAULT_DB_PATH):
    """Create DB file + schema if needed. Returns open connection."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def get_conn(path=DEFAULT_DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_db.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: add db.py with full SQLite schema for tracks and top_pairs"
```

---

### Task 3: Create importer.py

**Files:**
- Create: `importer.py`
- Create: `tests/test_importer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_importer.py
import json, os, struct, tempfile, zlib
import pytest
from importer import (
    _decode_float32_blob, _compute_bpm_stability,
    _parse_bpm_segments, SOURCE_MAP, parse_plist_file, run_sync,
)
from db import init_db


def _make_blob(values):
    """Pack values as big-endian float32 and zlib-compress."""
    return zlib.compress(struct.pack(f">{len(values)}f", *values))


def test_decode_float32_blob_roundtrip():
    values = [0.5, 1.0, 1.5, 2.0]
    result = _decode_float32_blob(_make_blob(values))
    assert len(result) == 4
    assert abs(result[0] - 0.5) < 0.001
    assert abs(result[3] - 2.0) < 0.001


def test_decode_float32_blob_empty():
    assert _decode_float32_blob(None) == []
    assert _decode_float32_blob(b"") == []


def test_compute_bpm_stability_metronomic():
    beats = [i * 0.5 for i in range(20)]
    assert _compute_bpm_stability(beats) < 0.001


def test_compute_bpm_stability_variable():
    beats = [0.0, 0.5, 1.2, 1.5, 2.3, 2.8]
    assert _compute_bpm_stability(beats) > 0.05


def test_compute_bpm_stability_too_few():
    assert _compute_bpm_stability([]) == 0.0
    assert _compute_bpm_stability([1.0]) == 0.0


def test_parse_bpm_segments():
    result = _parse_bpm_segments(_make_blob([0.2, 60.0]), _make_blob([128.0, 130.0]))
    assert len(result) == 2
    assert abs(result[0]["bpm"] - 128.0) < 0.1
    assert abs(result[1]["time"] - 60.0) < 0.1


def test_source_map():
    assert SOURCE_MAP[1] == "local"
    assert SOURCE_MAP[3] == "tidal"
    assert SOURCE_MAP[4] == "soundcloud"
    assert SOURCE_MAP[7] == "apple_music"


def test_run_sync_populates_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    # run_sync against real Djay Pro library
    result = run_sync(db_path)
    assert isinstance(result["added"], int)
    assert result["added"] > 0
    conn = init_db(db_path)
    count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
    assert count == result["added"]
    top = conn.execute("SELECT COUNT(*) FROM top_pairs").fetchone()[0]
    assert top > 0
    conn.close()


def test_run_sync_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    r1 = run_sync(db_path)
    r2 = run_sync(db_path)  # no files changed
    assert r2["added"] == 0
    assert r2["updated"] == 0
    assert r2["removed"] == 0
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_importer.py -v 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'importer'`

- [ ] **Step 3: Create importer.py**

```python
import glob
import json
import os
import plistlib
import struct
import zlib
from statistics import stdev

from db import init_db, DEFAULT_DB_PATH
from matching import key_index_to_camelot, key_index_to_name, build_key_groups, precompute_top_pairs

METADATA_DIR = os.path.expanduser(
    "~/Library/Group Containers/VJXTL73S8G.com.algoriddim.userdata/"
    "Library/Application Support/Algoriddim/Metadata"
)

SOURCE_MAP = {1: "local", 3: "tidal", 4: "soundcloud", 7: "apple_music"}


def _decode_float32_blob(blob):
    if not blob:
        return []
    try:
        data = zlib.decompress(blob)
        n = len(data) // 4
        return list(struct.unpack(f">{n}f", data[:n * 4]))
    except Exception:
        return []


def _compute_bpm_stability(beat_times):
    if len(beat_times) < 2:
        return 0.0
    intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
    if len(intervals) < 2:
        return 0.0
    return round(stdev(intervals), 6)


def _parse_bpm_segments(change_times_blob, bpms_blob):
    times = _decode_float32_blob(change_times_blob)
    bpms = _decode_float32_blob(bpms_blob)
    return [{"time": round(float(t), 3), "bpm": round(float(b), 2)}
            for t, b in zip(times, bpms)]


def parse_plist_file(path):
    """Parse a .djayMetadata file into a DB-ready dict. Returns None on failure."""
    try:
        with open(path, "rb") as f:
            d = plistlib.load(f)
    except Exception:
        return None

    info = d.get("info", {})
    ki = d.get("keyInfo", {})
    bi = d.get("deepBeatTrackerInfo", {})
    gi = d.get("newGainInfo", {})
    wave = d.get("waveInfoCompact", {})
    colors = d.get("waveColorsInfo", {})

    name = info.get("Name", "")
    if not name:
        return None

    key_index = ki.get("keyIndex", -1)
    camelot = key_index_to_camelot(key_index)
    bpm = bi.get("bpm", 0)
    if bpm <= 0 or camelot is None:
        return None

    beats_blob = bi.get("compressedBeats")
    beat_times = _decode_float32_blob(beats_blob)
    bpm_segments = _parse_bpm_segments(
        bi.get("compressedBPMChangeTimes"), bi.get("compressedPrevalentBPMs")
    )

    return {
        "name": name,
        "artist": info.get("Artist", ""),
        "duration": int(info.get("Duration", 0)),
        "source": SOURCE_MAP.get(info.get("source"), "local"),
        "persistent_id": info.get("persistentID", ""),
        "quality": info.get("quality", 0),
        "camelot": camelot,
        "key_name": key_index_to_name(key_index),
        "key_conf": round(ki.get("keyConfidence", 0), 4),
        "second_key": key_index_to_camelot(ki.get("secondKeyIndex", -1)),
        "tuning": round(ki.get("keyReferenceTuning", 440), 2),
        "bpm": round(bpm, 1),
        "analyzed_bpm": round(bi.get("analyzedBPM", bpm), 1),
        "bpm_conf": round(bi.get("bpmConfidence", 0), 4),
        "straight": int(bi.get("straightGrid", False)),
        "forced_straight": int(bi.get("forcedStraightGrid", False)),
        "grid_dev": round(bi.get("straightGridDistance", 0), 4),
        "first_downbeat": bi.get("firstDownBeatIndex", 0),
        "time_signature": bi.get("timeSignatureIndex", 4),
        "beat_count": len(beat_times),
        "bpm_stability": _compute_bpm_stability(beat_times),
        "bpm_segment_count": len(bpm_segments),
        "bpm_segments": json.dumps(bpm_segments),
        "energy": round(gi.get("AutoTitleGain", -11), 2),
        "dyn_range": round(gi.get("AutoTitleGainLoudnessRange", 6), 2),
        "transient_count": len(_decode_float32_blob(bi.get("compressedTransientPositions"))),
        "waveform_low": wave.get("compressedLowRateWaveSamples"),
        "waveform_max": wave.get("compressedLowRateWaveSamplesMax"),
        "waveform_colors": colors.get("compressedNormalRateWaveSamplesColors"),
        "beats_blob": beats_blob,
        "transient_pos": bi.get("compressedTransientPositions"),
        "transient_energy": bi.get("compressedTransientEnergies"),
        "file_path": path,
        "file_mtime": os.path.getmtime(path),
    }


def _upsert_track(conn, track):
    cols = [c for c in track if c != "file_path"]
    sql = f"""
        INSERT INTO tracks (file_path, {', '.join(cols)})
        VALUES (?, {', '.join('?' for _ in cols)})
        ON CONFLICT(file_path) DO UPDATE SET
        {', '.join(f'{c}=excluded.{c}' for c in cols)}
    """
    conn.execute(sql, [track["file_path"]] + [track[c] for c in cols])


def _recompute_top_pairs(conn):
    rows = conn.execute(
        "SELECT id, name, artist, bpm, camelot, key_conf, energy, dyn_range, "
        "straight, grid_dev, tuning, second_key, bpm_stability, bpm_segment_count "
        "FROM tracks"
    ).fetchall()
    tracks = [dict(r) for r in rows]
    key_groups = build_key_groups(tracks)
    top = precompute_top_pairs(tracks, key_groups, top_n=500)

    conn.execute("DELETE FROM top_pairs")
    for p in top:
        conn.execute("""
            INSERT INTO top_pairs
            (track_a_id, track_b_id, score, bpm_diff, bpm_match, key_match,
             energy_diff, grid_match, tuning_diff, dr_diff, warnings,
             bpm_score, key_score, energy_score, grid_score, dr_score,
             tuning_score, conf_score, second_key_match)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            p["track_a"]["id"], p["track_b"]["id"],
            p["score"], p["bpm_diff"], p["bpm_match"], p["key_match"],
            p["energy_diff"], int(p["grid_match"]), p["tuning_diff"], p["dr_diff"],
            json.dumps(p["warnings"]),
            p["bpm_score"], p["key_score"], p["energy_score"], p["grid_score"],
            p["dr_score"], p["tuning_score"], p["conf_score"], int(p["second_key_match"]),
        ])
    conn.commit()


def run_sync(db_path=DEFAULT_DB_PATH):
    """Sync Djay Pro metadata → SQLite. Returns {added, updated, removed}."""
    conn = init_db(db_path)

    existing = {
        r["file_path"]: (r["id"], r["file_mtime"])
        for r in conn.execute("SELECT id, file_path, file_mtime FROM tracks")
    }

    on_disk = set(glob.glob(os.path.join(METADATA_DIR, "**", "*.djayMetadata"), recursive=True))
    added = updated = removed = 0

    for path in on_disk:
        mtime = os.path.getmtime(path)
        if path in existing:
            if abs(mtime - existing[path][1]) < 0.01:
                continue
            track = parse_plist_file(path)
            if track:
                _upsert_track(conn, track)
                updated += 1
        else:
            track = parse_plist_file(path)
            if track:
                _upsert_track(conn, track)
                added += 1

    for path, (track_id, _) in existing.items():
        if path not in on_disk:
            conn.execute("DELETE FROM tracks WHERE id=?", [track_id])
            removed += 1

    conn.commit()

    if added or updated or removed:
        _recompute_top_pairs(conn)

    conn.close()
    return {"added": added, "updated": updated, "removed": removed}
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_importer.py -v
```

Expected: All tests pass. `test_run_sync_populates_db` and `test_run_sync_idempotent` will take a minute on first run (parsing real library). Subsequent runs are fast.

- [ ] **Step 5: Commit**

```bash
git add importer.py tests/test_importer.py
git commit -m "feat: add importer.py with full plist extraction, blobs, sync logic"
```

---

### Task 4: Create server.py

**Files:**
- Create: `server.py`
- Create: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server.py
import json, tempfile, os, threading, time, urllib.request, urllib.error
import pytest
from db import init_db
from server import MashupServer

PORT_BASE = 19800


def _start(db_path, port):
    srv = MashupServer(db_path=db_path, port=port, auto_open=False)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    return srv


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


@pytest.fixture
def seeded_db(tmp_path):
    path = str(tmp_path / "t.db")
    conn = init_db(path)
    for i, (name, artist, bpm, camelot) in enumerate([
        ("Track A", "Artist A", 128.0, "8B"),
        ("Track B", "Artist B", 129.0, "8B"),
        ("Track C", "Artist C", 95.0, "3A"),
    ]):
        conn.execute("""
            INSERT INTO tracks (name, artist, bpm, camelot, key_name, key_conf, bpm_conf,
                duration, energy, dyn_range, straight, grid_dev, tuning, second_key,
                bpm_stability, bpm_segment_count, bpm_segments, source, file_path, file_mtime)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [name, artist, bpm, camelot, "key", 0.9, 0.8, 210, -10.0, 6.0,
              1, 0.05, 440.0, None, 0.01, 1, "[]", "local",
              f"/fake/{i}.djayMetadata", 0.0])
    conn.commit()
    conn.close()
    return path


def test_stats(seeded_db):
    srv = _start(seeded_db, PORT_BASE)
    data = _get(f"http://127.0.0.1:{PORT_BASE}/api/stats")
    assert data["track_count"] == 3
    assert "8B" in data["key_counts"]
    srv.shutdown()


def test_tracks_no_blobs(seeded_db):
    srv = _start(seeded_db, PORT_BASE + 1)
    data = _get(f"http://127.0.0.1:{PORT_BASE+1}/api/tracks")
    assert len(data["tracks"]) == 3
    for t in data["tracks"]:
        assert "waveform_colors" not in t
        assert "beats_blob" not in t


def test_tracks_search(seeded_db):
    srv = _start(seeded_db, PORT_BASE + 2)
    data = _get(f"http://127.0.0.1:{PORT_BASE+2}/api/tracks?q=track+a")
    assert len(data["tracks"]) == 1
    assert data["tracks"][0]["name"] == "Track A"
    srv.shutdown()


def test_pairs(seeded_db):
    srv = _start(seeded_db, PORT_BASE + 3)
    tracks = _get(f"http://127.0.0.1:{PORT_BASE+3}/api/tracks")["tracks"]
    tid = next(t["id"] for t in tracks if t["name"] == "Track A")
    data = _get(f"http://127.0.0.1:{PORT_BASE+3}/api/pairs?track={tid}&bpm_range=6")
    assert "pairs" in data
    ids = [p["track"]["id"] for p in data["pairs"]]
    assert any(True for t in tracks if t["name"] == "Track B" and t["id"] in ids)
    srv.shutdown()


def test_waveform_endpoint(seeded_db):
    srv = _start(seeded_db, PORT_BASE + 4)
    tracks = _get(f"http://127.0.0.1:{PORT_BASE+4}/api/tracks")["tracks"]
    tid = tracks[0]["id"]
    data = _get(f"http://127.0.0.1:{PORT_BASE+4}/api/tracks/{tid}/waveform")
    for key in ["beats", "waveform_low", "waveform_max", "waveform_colors",
                "transient_pos", "transient_energy"]:
        assert key in data
    srv.shutdown()


def test_status_returns_ready(seeded_db):
    srv = _start(seeded_db, PORT_BASE + 5)
    data = _get(f"http://127.0.0.1:{PORT_BASE+5}/api/status")
    assert data["stage"] == "ready"
    srv.shutdown()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_server.py -v 2>&1 | head -5
```

Expected: `ModuleNotFoundError: No module named 'server'`

- [ ] **Step 3: Create server.py — copy HTML_PAGE then add server code**

First, copy the `HTML_PAGE` string from `djay-mashup-app.py` (lines 383–1681). Then create `server.py` with this structure:

```python
import base64
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_conn, DEFAULT_DB_PATH
from matching import find_pairs_for_track, build_key_groups

# ── paste HTML_PAGE from djay-mashup-app.py lines 383–1681 here ──
HTML_PAGE = r"""<!DOCTYPE html>
...
"""
# ─────────────────────────────────────────────────────────────────

TRACK_SCALAR_COLS = [
    "id", "name", "artist", "bpm", "analyzed_bpm", "camelot", "key_name",
    "key_conf", "second_key", "tuning", "bpm_conf", "duration", "energy",
    "dyn_range", "straight", "forced_straight", "grid_dev", "first_downbeat",
    "time_signature", "beat_count", "bpm_stability", "bpm_segment_count",
    "bpm_segments", "transient_count", "source", "persistent_id",
]

_WAVEFORM_RE = re.compile(r"^/api/tracks/(\d+)/waveform$")


def _row_to_dict(row, cols):
    return {c: row[c] for c in cols if c in row.keys()}


class MashupHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB_PATH

    def do_GET(self):
        parsed = urlparse(self.path)
        path, params = parsed.path, parse_qs(parsed.query)

        if path == "/":
            self._html(HTML_PAGE)
            return

        conn = get_conn(self.db_path)
        try:
            if path == "/api/status":
                self._json({"stage": "ready", "detail": "Ready"})

            elif path == "/api/stats":
                count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
                rows = conn.execute(
                    "SELECT camelot, COUNT(*) n FROM tracks GROUP BY camelot"
                ).fetchall()
                self._json({"track_count": count,
                            "key_counts": {r["camelot"]: r["n"] for r in rows}})

            elif path == "/api/tracks":
                q = params.get("q", [""])[0].lower()
                key = params.get("key", [None])[0]
                limit = int(params.get("limit", [99999])[0])
                sql = f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks WHERE 1=1"
                args = []
                if q:
                    sql += " AND (LOWER(name) LIKE ? OR LOWER(artist) LIKE ?)"
                    args += [f"%{q}%", f"%{q}%"]
                if key:
                    sql += " AND camelot=?"
                    args.append(key)
                sql += f" LIMIT {limit}"
                rows = conn.execute(sql, args).fetchall()
                self._json({"tracks": [_row_to_dict(r, TRACK_SCALAR_COLS) for r in rows]})

            elif path == "/api/pairs":
                track_id = params.get("track", [None])[0]
                bpm_range = float(params.get("bpm_range", [6])[0])
                limit = int(params.get("limit", [9999])[0])
                if track_id is None:
                    self._json({"pairs": []})
                    return
                track_id = int(track_id)
                row = conn.execute(
                    f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks WHERE id=?",
                    [track_id]
                ).fetchone()
                if not row:
                    self._json({"pairs": []})
                    return
                track = _row_to_dict(row, TRACK_SCALAR_COLS)
                all_rows = conn.execute(
                    f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks"
                ).fetchall()
                all_tracks = [_row_to_dict(r, TRACK_SCALAR_COLS) for r in all_rows]
                tracks_by_id = {t["id"]: t for t in all_tracks}
                key_groups = build_key_groups(all_tracks)
                pairs = find_pairs_for_track(track, tracks_by_id, key_groups, bpm_range, limit)
                self._json({"pairs": pairs})

            elif path == "/api/top-pairs":
                offset = int(params.get("offset", [0])[0])
                limit = int(params.get("limit", [50])[0])
                min_score = float(params.get("min_score", [0])[0])
                q = params.get("q", [""])[0].lower()
                key = params.get("key", [None])[0]
                match_types = params.get("match", [None])[0]
                allowed = set(match_types.split(",")) if match_types else None

                rows = conn.execute("""
                    SELECT tp.*,
                        a.id a_id, a.name a_name, a.artist a_artist,
                        a.bpm a_bpm, a.camelot a_camelot,
                        b.id b_id, b.name b_name, b.artist b_artist,
                        b.bpm b_bpm, b.camelot b_camelot,
                        a.bpm_segment_count a_bsc, b.bpm_segment_count b_bsc
                    FROM top_pairs tp
                    JOIN tracks a ON tp.track_a_id = a.id
                    JOIN tracks b ON tp.track_b_id = b.id
                    WHERE tp.score >= ?
                    ORDER BY tp.score DESC
                """, [min_score]).fetchall()

                results = []
                for r in rows:
                    if q and not any(q in (r[f] or "").lower()
                                     for f in ["a_name", "a_artist", "b_name", "b_artist"]):
                        continue
                    if key and r["a_camelot"] != key and r["b_camelot"] != key:
                        continue
                    if allowed and r["key_match"] not in allowed:
                        continue
                    results.append({
                        "track_a": {"id": r["a_id"], "name": r["a_name"],
                                    "artist": r["a_artist"], "bpm": r["a_bpm"],
                                    "camelot": r["a_camelot"],
                                    "bpm_segment_count": r["a_bsc"]},
                        "track_b": {"id": r["b_id"], "name": r["b_name"],
                                    "artist": r["b_artist"], "bpm": r["b_bpm"],
                                    "camelot": r["b_camelot"],
                                    "bpm_segment_count": r["b_bsc"]},
                        "score": r["score"], "bpm_diff": r["bpm_diff"],
                        "bpm_match": r["bpm_match"], "key_match": r["key_match"],
                        "energy_diff": r["energy_diff"], "grid_match": r["grid_match"],
                        "tuning_diff": r["tuning_diff"], "dr_diff": r["dr_diff"],
                        "warnings": json.loads(r["warnings"] or "[]"),
                        "bpm_score": r["bpm_score"], "key_score": r["key_score"],
                        "energy_score": r["energy_score"], "grid_score": r["grid_score"],
                        "dr_score": r["dr_score"], "tuning_score": r["tuning_score"],
                        "conf_score": r["conf_score"],
                        "second_key_match": r["second_key_match"],
                    })
                self._json({"pairs": results[offset:offset + limit], "total": len(results)})

            elif _WAVEFORM_RE.match(path):
                track_id = int(_WAVEFORM_RE.match(path).group(1))
                row = conn.execute(
                    "SELECT beats_blob, waveform_low, waveform_max, waveform_colors, "
                    "transient_pos, transient_energy FROM tracks WHERE id=?",
                    [track_id]
                ).fetchone()
                if not row:
                    self.send_error(404)
                    return
                self._json({k: base64.b64encode(row[k] or b"").decode()
                            for k in ["beats_blob", "waveform_low", "waveform_max",
                                      "waveform_colors", "transient_pos", "transient_energy"]})

            else:
                self.send_error(404)
        finally:
            conn.close()

    def do_POST(self):
        if self.path == "/api/import":
            from importer import run_sync
            self._json(run_sync(self.db_path))
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


class MashupServer:
    def __init__(self, db_path=DEFAULT_DB_PATH, port=8080, auto_open=True):
        handler = type("H", (MashupHandler,), {"db_path": db_path})
        self._server = HTTPServer(("127.0.0.1", port), handler)
        if auto_open:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")

    def serve_forever(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()
```

**Note on `HTML_PAGE`:** In the `do_GET` handler, the `/api/tracks` response now includes `bpm_stability`, `bpm_segment_count`, `source`, `analyzed_bpm` fields that the old frontend doesn't use yet — that's fine. The old frontend JS will ignore unknown fields.

- [ ] **Step 4: Copy HTML_PAGE from legacy file**

Open `djay-mashup-app.py` and copy the `HTML_PAGE = r"""..."""` assignment (lines 383–1681) into `server.py`, replacing the placeholder `HTML_PAGE = r"""..."""`.

- [ ] **Step 5: Run tests**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/test_server.py -v
```

Expected: All 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add server.py tests/test_server.py
git commit -m "feat: add server.py reading from SQLite with all API endpoints"
```

---

### Task 5: Create app.py — orchestrator

**Files:**
- Create: `app.py`

- [ ] **Step 1: Create app.py**

```python
#!/usr/bin/env python3
"""
Mashup Finder
Usage: python3 app.py [--port 8080] [--no-open] [--db PATH]
"""
import argparse

from db import DEFAULT_DB_PATH
from importer import run_sync
from server import MashupServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    print("Syncing Djay Pro library...", flush=True)
    result = run_sync(args.db)
    if result["added"] or result["updated"] or result["removed"]:
        print(f"  +{result['added']} added, {result['updated']} updated, "
              f"{result['removed']} removed", flush=True)
    else:
        print("  Library up to date.", flush=True)

    print(f"\n  Mashup Finder running at http://127.0.0.1:{args.port}\n", flush=True)
    server = MashupServer(db_path=args.db, port=args.port, auto_open=not args.no_open)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: End-to-end smoke test**

```bash
cd /Users/mericda/mashup-finder && python app.py --no-open &
sleep 3
curl -s http://127.0.0.1:8080/api/stats | python -m json.tool
curl -s "http://127.0.0.1:8080/api/tracks?limit=2" | python -m json.tool
kill %1
```

Expected: `track_count` > 0; tracks include `bpm_stability`, `source`, `analyzed_bpm` fields.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add app.py — sync on launch then start server"
```

---

### Task 6: Frontend — Import button + variable_bpm warning

**Files:**
- Modify: `server.py` (inside `HTML_PAGE`)

- [ ] **Step 1: Add Import button to header**

In `server.py`, inside `HTML_PAGE`, find:

```html
  <div class="badge"><span id="trackCount">...</span> tracks loaded</div>
</div>
```

Replace with:

```html
  <div class="badge"><span id="trackCount">...</span> tracks loaded</div>
  <button id="importBtn" onclick="triggerImport()" style="margin-left:auto;padding:6px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-size:12px;font-weight:600;cursor:pointer;transition:border-color 0.15s" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">↻ Import</button>
  <div id="importStatus" style="font-size:12px;color:var(--text2);display:none;white-space:nowrap"></div>
</div>
```

- [ ] **Step 2: Add triggerImport() JS — place after the esc() function at the bottom of the `<script>` block**

```javascript
async function triggerImport() {
  const btn = document.getElementById('importBtn');
  const status = document.getElementById('importStatus');
  btn.textContent = '↻ Syncing...';
  btn.disabled = true;
  status.style.display = 'none';
  try {
    const data = await fetch('/api/import', { method: 'POST' }).then(r => r.json());
    status.textContent = `+${data.added} added, ${data.updated} updated, ${data.removed} removed`;
    status.style.display = 'block';
    if (data.added || data.updated || data.removed) {
      const res = await api('/api/tracks?limit=99999');
      allTracks = res.tracks;
      document.getElementById('trackCount').textContent = allTracks.length.toLocaleString();
      applyFiltersAndSort();
      if (currentMode === 'top') loadTopPairs();
    }
  } catch(e) {
    status.textContent = 'Import failed';
    status.style.display = 'block';
  }
  btn.textContent = '↻ Import';
  btn.disabled = false;
}
```

- [ ] **Step 3: Add variable_bpm badge to pairHTML()**

In `pairHTML()`, find:

```javascript
  else if (p.energy_diff !== undefined && p.energy_diff <= 3) detailHTML += `<span class="badge-good">NRG ≈</span>`;
```

Add immediately after:

```javascript
  if (warns.includes('variable_bpm')) detailHTML += '<span class="badge-warn">VAR BPM</span>';
```

- [ ] **Step 4: Add variable_bpm badge to topPairHTML()**

In `topPairHTML()`, find:

```javascript
  const bpmBadge = p.bpm_match === 'double' ...
```

Add after that line:

```javascript
  const varBpmBadge = (p.warnings && p.warnings.includes('variable_bpm'))
    ? '<span class="badge-warn" style="font-size:9px;padding:2px 5px">VAR BPM</span>' : '';
```

Then in the returned HTML, find `${bpmBadge}` inside `.pair-badges` and add `${varBpmBadge}` after it.

- [ ] **Step 5: Add variable_bpm to detail modal**

In `showDetailModal()`, find:

```javascript
  if (warns.includes('grid')) badgesHTML += `<span class="modal-badge badge-warn">Grid Mismatch</span>`;
```

Add after:

```javascript
  if (warns.includes('variable_bpm')) badgesHTML += `<span class="modal-badge badge-warn">Variable BPM</span>`;
```

- [ ] **Step 6: Run app and verify Import button in browser**

```bash
cd /Users/mericda/mashup-finder && python app.py --no-open &
sleep 2
open http://127.0.0.1:8080
```

Verify: Import button appears top-right of header. Click it — status shows `+0 added, 0 updated, 0 removed` (already synced). Open DevTools console — no errors.

```bash
kill %1
```

- [ ] **Step 7: Commit**

```bash
git add server.py
git commit -m "feat: add Import button and variable_bpm warning to frontend"
```

---

### Task 7: Frontend — waveform canvas in pair detail modal

**Files:**
- Modify: `server.py` (inside `HTML_PAGE`)

- [ ] **Step 1: Add waveform CSS to the `<style>` block**

Inside `HTML_PAGE`, find the closing `</style>` tag and insert before it:

```css
.waveform-wrap { margin-top: 20px; }
.waveform-label {
  font-size: 11px; color: var(--text2); text-transform: uppercase;
  letter-spacing: 0.5px; font-weight: 600; margin-bottom: 4px;
}
.waveform-canvas {
  width: 100%; height: 64px; border-radius: 6px;
  background: var(--surface2); display: block; margin-bottom: 12px;
}
```

- [ ] **Step 2: Add canvas elements to showDetailModal()**

In `showDetailModal()`, find the last line of `document.getElementById('modalBody').innerHTML = \`...\``:

```javascript
  ${badgesHTML ? '<div class="modal-badges">' + badgesHTML + '</div>' : ''}
`;
  document.getElementById('detailModal').style.display = 'flex';
```

Replace with:

```javascript
  ${badgesHTML ? '<div class="modal-badges">' + badgesHTML + '</div>' : ''}
  <div class="waveform-wrap">
    <div class="waveform-label">${esc(trackA.name)}</div>
    <canvas id="waveformA" class="waveform-canvas" height="64"></canvas>
    <div class="waveform-label">${esc(trackB.name)}</div>
    <canvas id="waveformB" class="waveform-canvas" height="64"></canvas>
  </div>
`;
  document.getElementById('detailModal').style.display = 'flex';
  loadWaveforms(trackA.id, trackB.id);
```

- [ ] **Step 3: Add waveform rendering JS — after closeModal() function**

```javascript
async function loadWaveforms(idA, idB) {
  const [dataA, dataB] = await Promise.all([
    api(`/api/tracks/${idA}/waveform`),
    api(`/api/tracks/${idB}/waveform`),
  ]);
  renderWaveform('waveformA', dataA);
  renderWaveform('waveformB', dataB);
}

function _b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function _zlibDecompress(bytes) {
  // Strip 2-byte zlib header, use raw deflate
  const ds = new DecompressionStream('deflate-raw');
  const writer = ds.writable.getWriter();
  const reader = ds.readable.getReader();
  const chunks = [];
  const done = reader.read().then(function pump({ done, value }) {
    if (done) return;
    chunks.push(value);
    return reader.read().then(pump);
  });
  writer.write(bytes.slice(2));
  writer.close();
  await done;
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.length; }
  return out;
}

async function renderWaveform(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const W = canvas.parentElement ? canvas.parentElement.clientWidth || 424 : 424;
  const H = 64;
  canvas.width = W;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'var(--surface2)';
  ctx.fillRect(0, 0, W, H);

  if (!data.waveform_colors) return;
  let colorBytes, ampBytes;
  try { colorBytes = await _zlibDecompress(_b64ToBytes(data.waveform_colors)); } catch(e) { return; }
  try { ampBytes = await _zlibDecompress(_b64ToBytes(data.waveform_low)); } catch(e) {}

  const nColor = colorBytes.length >> 1;
  const nAmp = ampBytes ? (ampBytes.length >> 1) : 0;
  let maxAmp = 0;
  if (nAmp > 0) {
    for (let i = 0; i < nAmp; i++) {
      const v = ((ampBytes[i*2] << 8) | ampBytes[i*2+1]);
      if (v > maxAmp) maxAmp = v;
    }
  }

  for (let x = 0; x < W; x++) {
    const ci = Math.floor(x / W * nColor);
    const hi = colorBytes[ci * 2], lo = colorBytes[ci * 2 + 1];
    const rgb = (hi << 8) | lo;
    const r = ((rgb >> 11) & 0x1F) << 3;
    const g = ((rgb >> 5) & 0x3F) << 2;
    const b = (rgb & 0x1F) << 3;

    let barH = H * 0.5;
    if (nAmp > 0 && maxAmp > 0) {
      const ai = Math.floor(x / W * nAmp);
      const amp = ((ampBytes[ai*2] << 8) | ampBytes[ai*2+1]) / maxAmp;
      barH = Math.max(2, amp * H);
    }
    const y0 = (H - barH) / 2;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(x, y0, 1, barH);
  }

  // Beat tick marks
  if (data.beats_blob) {
    try {
      const beatBytes = await _zlibDecompress(_b64ToBytes(data.beats_blob));
      const view = new DataView(beatBytes.buffer);
      const nBeats = beatBytes.length >> 2;
      if (nBeats > 1) {
        const lastBeat = view.getFloat32((nBeats - 1) * 4, false);
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1;
        for (let i = 0; i < nBeats; i++) {
          const t = view.getFloat32(i * 4, false);
          const x = Math.floor(t / lastBeat * W);
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
        }
      }
    } catch(e) {}
  }
}
```

- [ ] **Step 4: Test waveform in browser**

```bash
cd /Users/mericda/mashup-finder && python app.py --no-open &
sleep 2
open http://127.0.0.1:8080
```

Select any track → click the ⓘ button on a pair → detail modal opens. Scroll down — two colored waveforms should appear with white beat tick marks. Open DevTools console — no errors.

```bash
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add server.py
git commit -m "feat: add colored waveform canvas with beat markers to pair detail modal"
```

---

### Task 8: Full test suite + final verification

**Files:**
- No new files

- [ ] **Step 1: Run all tests**

```bash
cd /Users/mericda/mashup-finder && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify DB was created and has reasonable size**

```bash
ls -lh ~/.mashup-finder/library.db
sqlite3 ~/.mashup-finder/library.db "SELECT COUNT(*) FROM tracks; SELECT COUNT(*) FROM top_pairs;"
```

Expected: file exists; track count > 0; top_pairs count up to 500.

- [ ] **Step 3: Verify second launch is fast (sync finds nothing to do)**

```bash
cd /Users/mericda/mashup-finder && time python app.py --no-open &
sleep 8 && kill %1
```

Expected: "Library up to date." printed quickly; server ready in under 3 seconds.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: database migration complete — SQLite backend, waveform rendering, Import button"
```

---

## Spec Coverage Check

| Spec requirement | Task |
|---|---|
| Split into matching.py, db.py, importer.py, server.py, app.py | Tasks 1–5 |
| SQLite at `~/.mashup-finder/library.db` | Task 2 |
| Full track schema — all plist scalar fields | Task 3 |
| All blob columns (waveform_low/max/colors, beats, transients) | Tasks 2–3 |
| `bpm_stability` computed from beat timestamps | Task 3 |
| `bpm_segments` JSON from BPMChangeTimes + PrevalentBPMs | Task 3 |
| `source` mapping (1→local, 3→tidal, 4→soundcloud, 7→apple_music) | Task 3 |
| Auto-sync on launch with mtime comparison | Task 3 |
| `DELETE FROM top_pairs` + recompute after any change | Task 3 |
| `POST /api/import` manual re-sync | Task 4 |
| `GET /api/tracks/:id/waveform` serving blobs as base64 | Task 4 |
| `/api/tracks` never returns blob columns | Task 4 |
| Import button in header with progress status | Task 6 |
| `variable_bpm` warning in pair cards, top pairs, detail modal | Task 6 |
| `bpm_stability` penalty in scoring | Task 1 |
| Waveform canvas (RGB565) in pair detail modal | Task 7 |
| Beat tick markers on waveform | Task 7 |
| Zero new Python dependencies | All tasks |
