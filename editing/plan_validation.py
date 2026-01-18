from __future__ import annotations


def normalize_segments(segments, min_len: float = 0.4):
    ordered = sorted(segments, key=lambda s: float(s.get("start", 0)))
    normalized = []
    last_end = 0.0
    for seg in ordered:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", 0))
        if end <= start:
            continue
        if start < last_end:
            start = last_end
        if end - start < min_len:
            continue
        normalized.append({**seg, "start": start, "end": end})
        last_end = end
    return normalized


def clamp_duration_to_range(segments, target_s: float, min_total=30.0, max_total=60.0):
    total = sum(seg["end"] - seg["start"] for seg in segments)
    if total <= max_total:
        return segments, total

    trimmed = []
    running = 0.0
    for seg in segments:
        seg_len = seg["end"] - seg["start"]
        if running + seg_len <= target_s:
            trimmed.append(seg)
            running += seg_len
        else:
            remaining = max(target_s - running, min_total - running)
            if remaining >= 0.4:
                trimmed.append({**seg, "end": seg["start"] + remaining})
                running += remaining
            break

    if running < min_total:
        return segments, total
    return trimmed, running
