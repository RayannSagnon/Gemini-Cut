from __future__ import annotations

import subprocess
from pathlib import Path


def _run(cmd, cmd_log: Path, stderr_log: Path):
    cmd_log.write_text("", encoding="utf-8") if not cmd_log.exists() else None
    with cmd_log.open("a", encoding="utf-8") as handle:
        handle.write(" ".join(cmd) + "\n")
    result = subprocess.run(cmd, capture_output=True)
    if result.stderr:
        with stderr_log.open("ab") as handle:
            handle.write(result.stderr + b"\n")
    if result.returncode != 0:
        raise RuntimeError("FFmpeg command failed.")


def _probe_duration(path: Path):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip() or 0)


def build_video_filter(opts):
    target_width = int(opts.get("target_width", 1080))
    target_height = int(opts.get("target_height", 1920))
    scale = (
        f"scale=w='min(iw,{target_width})':h='min(ih,{target_height})'"
        ":force_original_aspect_ratio=decrease"
    )
    pad = (
        f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2"
        ":color=black"
    )
    filters = [scale, pad]

    if opts.get("filters_enabled"):
        preset = opts.get("filter_preset", "none")
        defaults = {
            "clean": (0.02, 1.05, 1.05, 1.0),
            "cinematic": (-0.03, 1.1, 0.95, 0.95),
            "vibrant": (0.05, 1.1, 1.2, 1.0),
            "bw": (0.0, 1.0, 0.0, 1.0),
            "retro": (0.02, 0.95, 0.9, 1.05),
            "sharp": (0.0, 1.15, 1.05, 1.0),
            "soft": (0.0, 0.95, 0.95, 1.0),
        }
        base = defaults.get(preset, (0, 1, 1, 1))
        brightness = opts.get("brightness", base[0])
        contrast = opts.get("contrast", base[1])
        saturation = opts.get("saturation", base[2])
        gamma = opts.get("gamma", base[3])
        filters.append(
            f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}:gamma={gamma}"
        )
        sharpness = opts.get("sharpness", 0)
        if sharpness > 0:
            filters.append(f"unsharp=3:3:{int(sharpness*2)}")
        if opts.get("denoise"):
            filters.append("hqdn3d=1.5:1.5:6:6")
        if opts.get("vignette"):
            filters.append("vignette=0.4")
        if opts.get("grain"):
            filters.append("noise=alls=10:allf=t")
    return ",".join(filters)


def concat_clips(clip_paths, output_path: Path, cmd_log: Path, stderr_log: Path):
    concat_list = output_path.parent / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as handle:
        for clip in clip_paths:
            handle.write(f"file '{clip.as_posix()}'\n")
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        str(output_path),
    ]
    _run(cmd, cmd_log, stderr_log)


def apply_transitions(clip_paths, transition_type, duration, output_path, cmd_log, stderr_log):
    if transition_type == "none" or len(clip_paths) < 2:
        concat_clips(clip_paths, output_path, cmd_log, stderr_log)
        return

    transitions = {
        "fade": "fade",
        "crossfade": "fade",
        "dip_black": "fadeblack",
        "swipe": "wipeleft",
    }
    transition = transitions.get(transition_type, "fade")
    durations = [_probe_duration(path) for path in clip_paths]
    inputs = []
    for path in clip_paths:
        inputs += ["-i", str(path)]
    filter_complex = []
    last = "[0:v]"
    offset = durations[0] - duration
    for idx in range(1, len(clip_paths)):
        filter_complex.append(
            f"{last}[{idx}:v]xfade=transition={transition}:duration={duration}:offset={offset}[v{idx}]"
        )
        last = f"[v{idx}]"
        offset += durations[idx] - duration
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filter_complex), "-map", last, "-an", str(output_path)]
    _run(cmd, cmd_log, stderr_log)


def apply_overlays(base_path, overlays, output_path, cmd_log, stderr_log):
    if not overlays:
        base_path.replace(output_path)
        return

    inputs = ["-i", str(base_path)]
    filter_complex = []
    last = "[0:v]"
    for idx, overlay in enumerate(overlays, start=1):
        inputs += ["-i", str(overlay["path"])]
        placement = overlay.get("placement", "top_right")
        x = "W-w-40" if placement == "top_right" else "40"
        y = "40" if placement == "top_right" else "H-h-40"
        enable = f"between(t,{overlay['start']},{overlay['end']})"
        filter_complex.append(f"{last}[{idx}:v]overlay={x}:{y}:enable='{enable}'[v{idx}]")
        last = f"[v{idx}]"
    cmd = [
        "ffmpeg",
        "-y",
        *inputs,
        "-filter_complex",
        ";".join(filter_complex),
        "-map",
        last,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        str(output_path),
    ]
    _run(cmd, cmd_log, stderr_log)


def render_final(base_path, captions_ass, opts, output_path, cmd_log, stderr_log):
    filters = []
    if captions_ass:
        filters.append(f"subtitles='{captions_ass.as_posix().replace(':', '\\\\:')}'")
    filter_arg = ",".join(filters) if filters else None

    audio_filters = []
    if opts.get("audio_enhance"):
        audio_filters.extend(["loudnorm", "compand"])
    if opts.get("audio_loudnorm"):
        audio_filters.append("loudnorm")
    if opts.get("audio_compressor"):
        audio_filters.append("compand")
    if opts.get("audio_denoise"):
        audio_filters.append("afftdn")
    audio_filter_arg = ",".join(audio_filters) if audio_filters else None

    cmd = ["ffmpeg", "-y", "-i", str(base_path)]
    voiceover_path = opts.get("voiceover_path") if opts.get("voiceover_enabled") else None
    voiceover_speed = float(opts.get("voiceover_speed", 1.0))
    voiceover_pre_sped = bool(opts.get("voiceover_pre_sped", False))
    voiceover_idx = None
    if voiceover_path:
        cmd += ["-i", str(voiceover_path)]
        voiceover_idx = 1
    music_file = opts.get("music_file") if opts.get("music_enabled") else None
    music_idx = None
    if music_file:
        cmd += ["-stream_loop", "-1", "-i", str(music_file)]
        music_idx = 2 if voiceover_path else 1
    sfx_items = opts.get("sfx_items") or []
    for item in sfx_items:
        cmd += ["-i", str(item["path"])]
    if filter_arg:
        cmd += ["-vf", filter_arg]

    filter_complex = []
    audio_map = None

    voice_label = "[0:a]"
    if voiceover_path and voiceover_idx is not None:
        if not voiceover_pre_sped and abs(voiceover_speed - 1.0) > 0.01:
            speed = max(0.5, min(2.0, voiceover_speed))
            filter_complex.append(f"[{voiceover_idx}:a]atempo={speed}[vo]")
            voice_input = "[vo]"
        else:
            voice_input = f"[{voiceover_idx}:a]"
        mode = opts.get("voiceover_mode", "replace")
        if mode == "replace":
            voice_label = voice_input
        elif mode == "mix":
            filter_complex.append(
                f"[0:a]{voice_input}amix=inputs=2:duration=first:dropout_transition=2[voice]"
            )
            voice_label = "[voice]"
        else:
            filter_complex.append(
                f"[0:a]{voice_input}sidechaincompress=threshold=0.08:ratio=8[ducked]"
            )
            filter_complex.append(
                f"[ducked]{voice_input}amix=inputs=2:duration=first:dropout_transition=2[voice]"
            )
            voice_label = "[voice]"

    if sfx_items:
        sfx_labels = []
        sfx_start = music_idx + 1 if music_idx is not None else (voiceover_idx + 1 if voiceover_idx is not None else 1)
        for offset, item in enumerate(sfx_items):
            idx = sfx_start + offset
            start_ms = int(float(item.get("start", 0)) * 1000)
            volume = float(item.get("volume", 0.8))
            label = f"sfx{offset}"
            filter_complex.append(
                f"[{idx}:a]adelay={start_ms}|{start_ms},volume={volume}[{label}]"
            )
            sfx_labels.append(f"[{label}]")
        inputs = [voice_label] + sfx_labels
        filter_complex.append(
            f"{''.join(inputs)}amix=inputs={len(inputs)}:duration=first:dropout_transition=2[voice_sfx]"
        )
        voice_label = "[voice_sfx]"

    if music_file and music_idx is not None:
        music_vol = opts.get("music_volume", 0.15)
        filter_complex.append(f"[{music_idx}:a]volume={music_vol}[music]")
        if opts.get("music_ducking"):
            filter_complex.append(
                f"[music]{voice_label}sidechaincompress=threshold=0.08:ratio=8[ducked]"
            )
            filter_complex.append(
                f"{voice_label}[ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        else:
            filter_complex.append(
                f"{voice_label}[music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
        audio_map = "[aout]"
    else:
        audio_map = voice_label

    if audio_filter_arg:
        filter_complex.append(f"{audio_map}{audio_filter_arg}[afinal]")
        audio_map = "[afinal]"

    if filter_complex:
        cmd += ["-filter_complex", ";".join(filter_complex), "-map", "0:v", "-map", audio_map]
    elif audio_filter_arg:
        cmd += ["-af", audio_filter_arg]

    cmd += [
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(output_path),
    ]
    _run(cmd, cmd_log, stderr_log)
