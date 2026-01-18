import json


def build_gemini_prompt(opts):
    platform = opts.get("platform", "Shorts")
    target = opts.get("duration_s", 45)
    style = opts.get("style", "Storytelling")
    cut_intensity = opts.get("cut_intensity", "Medium")
    language = opts.get("language", "FR")
    captions = opts.get("captions", "ON")

    sfx_enabled = opts.get("sfx_enabled", False)

    prompt = f"""
You are an expert short-form video editor. Produce a precise JSON editing plan for a 9:16 short.

User targets:
- Platform: {platform}
- Target duration: {target}s (must be between 30 and 60 seconds)
- Style: {style}
- Cut intensity: {cut_intensity}
- Captions language: {language}
- Captions enabled: {captions}

Editing rules (must follow):
- Final duration between 30 and 60 seconds. Target is {target}s.
- 4 to 10 segments total, ordered, no overlaps.
- Hook: the most engaging moment, must appear within the first 0–2.5s of the final edit.
- Hook text must be <= 8 words.
- Overlays: 2 to 4 items, text <= 6 words, placed on strong moments.
- Captions SRT must align to the edited timeline (not source).
- Cut intensity must strongly influence how aggressive the segments are:
  - Soft: longer segments and fewer cuts.
  - Medium: balanced cuts.
  - Hard: more frequent cuts.
- If screen-record content: prefer visible actions/results.
- If podcast/facecam: prefer punchlines or complete useful phrases.

Return JSON ONLY with this exact schema:
{{
  "target_duration_s": number,
  "segments": [{{"start": number, "end": number, "reason": "hook"|"keep"}}],
  "hook": {{"start": number, "end": number, "text": string}},
  "overlays": [{{"start": number, "end": number, "text": string}}],
  "captions_srt": string,
  "transition": "none"|"fade"|"crossfade"|"dip_black"|"swipe"
}}

If captions are disabled, return an empty string for captions_srt.
Set transition to the best choice for this content and style.
"""
    if sfx_enabled:
        prompt += """
Also include:
  "sound_effects": [{"start": number, "end": number, "text": string}]
Rules for sound_effects:
- 2 to 5 items
- text is a short sound description (<= 6 words)
- start/end aligned to the edited timeline
"""
    return prompt.strip()


def parse_json_response(text):
    return json.loads(text.strip())


def get_plan(client, file_obj, opts, model_name, fallback_models):
    prompt = build_gemini_prompt(opts)
    for model in [model_name, *fallback_models]:
        response = client.models.generate_content(
            model=model,
            contents=[prompt, file_obj],
            config={"response_mime_type": "application/json"},
        )
        try:
            return parse_json_response(response.text), prompt
        except json.JSONDecodeError:
            retry = client.models.generate_content(
                model=model,
                contents=["Return valid JSON only.", prompt, file_obj],
                config={"response_mime_type": "application/json"},
            )
            return parse_json_response(retry.text), prompt
    raise RuntimeError("Failed to generate plan.")
