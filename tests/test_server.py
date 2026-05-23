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
    srv.shutdown()


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
