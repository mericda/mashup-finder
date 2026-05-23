import os, tempfile
from db import init_db, get_conn


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
        for col in ["id", "name", "artist", "duration", "source", "persistent_id",
                    "quality", "camelot", "key_name", "key_conf", "second_key",
                    "tuning", "bpm", "analyzed_bpm", "bpm_conf", "straight",
                    "forced_straight", "grid_dev", "first_downbeat",
                    "time_signature", "beat_count", "bpm_stability",
                    "bpm_segment_count", "bpm_segments", "energy", "dyn_range",
                    "transient_count", "waveform_low", "waveform_max",
                    "waveform_colors", "beats_blob", "transient_pos",
                    "transient_energy", "file_path", "file_mtime"]:
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
        for col in ["id", "track_a_id", "track_b_id", "score", "bpm_diff",
                    "bpm_match", "key_match", "energy_diff", "grid_match",
                    "tuning_diff", "dr_diff", "warnings", "bpm_score",
                    "key_score", "energy_score", "grid_score", "dr_score",
                    "tuning_score", "conf_score", "second_key_match"]:
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


def test_get_conn_row_factory():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        conn.execute("INSERT INTO tracks (name, artist) VALUES ('Test', 'Artist')")
        conn.commit()
        conn.close()
        conn2 = get_conn(path)
        row = conn2.execute("SELECT name, artist FROM tracks").fetchone()
        assert row["name"] == "Test"  # sqlite3.Row dict-like access
        conn2.close()
    finally:
        os.unlink(path)


def test_on_delete_cascade():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    try:
        conn = init_db(path)
        conn.execute("INSERT INTO tracks (name, artist, file_path) VALUES ('T', 'A', '/fake/path')")
        conn.commit()
        track_id = conn.execute("SELECT id FROM tracks").fetchone()["id"]
        conn.execute(
            "INSERT INTO top_pairs (track_a_id, track_b_id, score) VALUES (?, ?, ?)",
            [track_id, track_id, 0.9]
        )
        conn.commit()
        conn.execute("DELETE FROM tracks WHERE id=?", [track_id])
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM top_pairs").fetchone()[0]
        assert count == 0  # CASCADE deleted the pair
        conn.close()
    finally:
        os.unlink(path)
