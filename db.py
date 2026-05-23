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
