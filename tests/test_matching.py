import pytest
from matching import (
    key_index_to_camelot, key_index_to_name, get_compatible_keys,
    key_match_type, score_pair, _is_same_track, _artist_tokens,
    build_key_groups, find_pairs_for_track, precompute_top_pairs,
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


def test_key_index_to_name():
    assert key_index_to_name(0) == "C maj"
    assert key_index_to_name(1) == "A min"
    assert key_index_to_name(-1) == "Unknown"


def test_precompute_top_pairs():
    tracks = [
        _track(id=1, camelot="8B", artist="Artist A"),
        _track(id=2, camelot="8B", artist="Artist B"),
        _track(id=3, camelot="8B", artist="Artist A"),  # same artist as id=1, should be excluded from pairs with id=1
        _track(id=4, camelot="3A", artist="Artist D"),  # incompatible key
    ]
    key_groups = build_key_groups(tracks)
    pairs = precompute_top_pairs(tracks, key_groups, top_n=10)
    # Returns a list
    assert isinstance(pairs, list)
    # Same-artist pairs should be excluded
    for p in pairs:
        assert p["track_a"]["artist"] != p["track_b"]["artist"]
    # No duplicate pairs
    seen = set()
    for p in pairs:
        canon = (min(p["track_a"]["id"], p["track_b"]["id"]), max(p["track_a"]["id"], p["track_b"]["id"]))
        assert canon not in seen
        seen.add(canon)
    # Sorted by score descending
    scores = [p["score"] for p in pairs]
    assert scores == sorted(scores, reverse=True)


def test_score_pair_half_time():
    a = _track(id=1, bpm=64.0)
    b = _track(id=2, bpm=128.0)
    result = score_pair(a, b, bpm_range=6)
    assert result is not None
    assert result["bpm_match"] == "half"


def test_score_pair_tuning_warning():
    a = _track(id=1, tuning=440.0)
    b = _track(id=2, tuning=445.0)
    result = score_pair(a, b)
    assert "tuning" in result["warnings"]


def test_score_pair_energy_warning():
    a = _track(id=1, energy=-10.0)
    b = _track(id=2, energy=-20.0)
    result = score_pair(a, b)
    assert "energy" in result["warnings"]


def test_score_pair_grid_warning():
    a = _track(id=1, straight=True)
    b = _track(id=2, straight=False)
    result = score_pair(a, b)
    assert "grid" in result["warnings"]


def test_is_same_track_substring():
    a = {"name": "Levels (Original Mix)", "artist": "Avicii"}
    b = {"name": "Levels", "artist": "Avicii"}
    assert _is_same_track(a, b)
