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


def test_run_sync_with_fake_metadata(tmp_path):
    import plistlib
    # Create a minimal valid .djayMetadata plist
    meta_dir = tmp_path / "meta"
    meta_dir.mkdir()
    plist_data = {
        "info": {"Name": "Test Track", "Artist": "Test Artist", "Duration": 200, "source": 1},
        "keyInfo": {"keyIndex": 0, "keyConfidence": 0.9, "keyReferenceTuning": 440.0},
        "deepBeatTrackerInfo": {"bpm": 128.0, "bpmConfidence": 0.8, "straightGrid": True,
                                "straightGridDistance": 0.05, "firstDownBeatIndex": 0,
                                "timeSignatureIndex": 4},
        "newGainInfo": {"AutoTitleGain": -10.0, "AutoTitleGainLoudnessRange": 6.0},
    }
    plist_path = meta_dir / "test.djayMetadata"
    with open(plist_path, "wb") as f:
        plistlib.dump(plist_data, f)

    db_path = str(tmp_path / "test.db")
    result = run_sync(db_path, metadata_dir=str(meta_dir))
    assert result["added"] == 1
    assert result["skipped"] == 0
