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
