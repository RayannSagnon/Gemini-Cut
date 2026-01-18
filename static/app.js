const API_BASE =
  window.location.port === "5173" || window.location.port === "3000"
    ? "http://localhost:8000"
    : "";

const state = {
  file: null,
  platform: "Shorts",
  duration: 45,
  style: "Storytelling",
  intensity: "Medium",
  captions: true,
  language: "FR",
  resolution: "1080x1920",
  sourceType: "upload",
  sourceUrl: "",
  jobId: null,
};

const elements = {
  dropzone: document.getElementById("dropzone"),
  videoInput: document.getElementById("video-input"),
  uploadInfo: document.getElementById("upload-info"),
  fileName: document.getElementById("file-name"),
  fileDuration: document.getElementById("file-duration"),
  fileType: document.getElementById("file-type"),
  settingsSection: document.getElementById("settings-section"),
  platform: document.getElementById("platform"),
  duration: document.getElementById("duration"),
  durationValue: document.getElementById("duration-value"),
  notifyEmail: document.getElementById("notify-email"),
  captionsToggle: document.getElementById("captions-toggle"),
  captionsStatus: document.getElementById("captions-status"),
  contentPreset: document.getElementById("content-preset"),
  outputResolution: document.getElementById("output-resolution"),
  reframeMode: document.getElementById("reframe-mode"),
  fps: document.getElementById("fps"),
  captionTemplate: document.getElementById("caption-template"),
  captionPosition: document.getElementById("caption-position"),
  captionSize: document.getElementById("caption-size"),
  captionSafe: document.getElementById("caption-safe"),
  captionMaxChars: document.getElementById("caption-max-chars"),
  captionHighlight: document.getElementById("caption-highlight"),
  transitionType: document.getElementById("transition-type"),
  transitionDuration: document.getElementById("transition-duration"),
  audioEnhance: document.getElementById("audio-enhance"),
  audioLoudnorm: document.getElementById("audio-loudnorm"),
  audioCompressor: document.getElementById("audio-compressor"),
  audioDenoise: document.getElementById("audio-denoise"),
  audioIsolation: document.getElementById("audio-isolation"),
  sfxEnabled: document.getElementById("sfx-enabled"),
  sttCaptions: document.getElementById("stt-captions"),
  voiceoverEnabled: document.getElementById("voiceover-enabled"),
  voiceoverText: document.getElementById("voiceover-text"),
  voiceoverVoiceId: document.getElementById("voiceover-voice-id"),
  voiceoverSpeed: document.getElementById("voiceover-speed"),
  voiceoverMode: document.getElementById("voiceover-mode"),
  musicEnabled: document.getElementById("music-enabled"),
  musicDucking: document.getElementById("music-ducking"),
  musicVolume: document.getElementById("music-volume"),
  musicFile: document.getElementById("music-file"),
  aiVisualsEnabled: document.getElementById("ai-visuals-enabled"),
  aiVisualsTransparent: document.getElementById("ai-visuals-transparent"),
  aiVisualsStyle: document.getElementById("ai-visuals-style"),
  aiVisualsIntensity: document.getElementById("ai-visuals-intensity"),
  aiVisualsMax: document.getElementById("ai-visuals-max"),
  aiBrollEnabled: document.getElementById("ai-broll-enabled"),
  aiBrollMode: document.getElementById("ai-broll-mode"),
  aiVideoModel: document.getElementById("ai-video-model"),
  previewBox: document.getElementById("preview-box"),
  previewVideo: document.getElementById("preview-video"),
  previewPlaceholder: document.getElementById("preview-placeholder"),
  previewName: document.getElementById("preview-name"),
  previewSize: document.getElementById("preview-size"),
  generateBtn: document.getElementById("generate-btn"),
  progressSection: document.getElementById("progress-section"),
  progressFill: document.getElementById("progress-fill"),
  progressStatus: document.getElementById("progress-status"),
  progressValue: document.getElementById("progress-value"),
  progressError: document.getElementById("progress-error"),
  resultSection: document.getElementById("result-section"),
  resultPlayer: document.getElementById("result-player"),
  resultDuration: document.getElementById("result-duration"),
  resultStyle: document.getElementById("result-style"),
  downloadBtn: document.getElementById("download-btn"),
  restartBtn: document.getElementById("restart-btn"),
  stepItems: document.querySelectorAll(".steps li"),
  ttsText: document.getElementById("tts-text"),
  ttsVoiceId: document.getElementById("tts-voice-id"),
  ttsSpeed: document.getElementById("tts-speed"),
  ttsGenerate: document.getElementById("tts-generate"),
  ttsUse: document.getElementById("tts-use"),
  ttsAudio: document.getElementById("tts-audio"),
  ttsMessage: document.getElementById("tts-message"),
  stsAudio: document.getElementById("sts-audio"),
  stsVoiceId: document.getElementById("sts-voice-id"),
  stsGenerate: document.getElementById("sts-generate"),
  stsOutput: document.getElementById("sts-output"),
  stsMessage: document.getElementById("sts-message"),
  sttAudio: document.getElementById("stt-audio"),
  sttLang: document.getElementById("stt-lang"),
  sttGenerate: document.getElementById("stt-generate"),
  sttOutput: document.getElementById("stt-output"),
  sttMessage: document.getElementById("stt-message"),
  sfxPrompt: document.getElementById("sfx-prompt"),
  sfxDuration: document.getElementById("sfx-duration"),
  sfxGenerate: document.getElementById("sfx-generate"),
  sfxOutput: document.getElementById("sfx-output"),
  sfxMessage: document.getElementById("sfx-message"),
  isolateAudio: document.getElementById("isolate-audio"),
  isolateGenerate: document.getElementById("isolate-generate"),
  isolateOutput: document.getElementById("isolate-output"),
  isolateMessage: document.getElementById("isolate-message"),
  musicPrompt: document.getElementById("music-prompt"),
  musicDuration: document.getElementById("music-duration"),
  musicGenerate: document.getElementById("music-generate"),
  musicOutput: document.getElementById("music-output"),
  musicMessage: document.getElementById("music-message"),
  voiceName: document.getElementById("voice-name"),
  voiceDesc: document.getElementById("voice-desc"),
  voiceGenerate: document.getElementById("voice-generate"),
  voiceOutput: document.getElementById("voice-output"),
  voiceMessage: document.getElementById("voice-message"),
};

let pollTimer = null;
let ttsBlob = null;
let ttsFilename = "tts.mp3";
let useTtsInVideo = false;
let previewUrl = null;

function showSettings() {
  elements.settingsSection.classList.remove("hidden");
}

function enableGenerate() {
  if (state.sourceType === "url") {
    elements.generateBtn.disabled = !state.sourceUrl;
  } else {
    elements.generateBtn.disabled = !state.file;
  }
}

function setPillActive(group, value) {
  const buttons = document.querySelectorAll(`[data-pill="${group}"] .pill`);
  buttons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.value === value);
  });
}

function detectType(fileName) {
  const lower = fileName.toLowerCase();
  if (lower.includes("screen")) return "Screen recording";
  if (lower.includes("podcast")) return "Podcast";
  return "Facecam";
}

function loadVideoMetadata(file) {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      resolve(video.duration);
      URL.revokeObjectURL(video.src);
    };
    video.src = URL.createObjectURL(file);
  });
}

async function handleFile(file) {
  if (!file) return;
  state.file = file;
  state.sourceType = "upload";
  state.sourceUrl = "";
  elements.uploadInfo.classList.remove("hidden");
  elements.fileName.textContent = file.name;
  elements.previewName.textContent = file.name;
  elements.previewSize.textContent = `Size: ${(file.size / 1e6).toFixed(1)} MB`;
  elements.fileType.textContent = `Detected: ${detectType(file.name)}`;
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
  }
  previewUrl = URL.createObjectURL(file);
  elements.previewVideo.src = previewUrl;
  elements.previewVideo.load();
  elements.previewBox.classList.add("has-video");
  const duration = await loadVideoMetadata(file);
  elements.fileDuration.textContent = `Duration: ${duration.toFixed(1)}s`;
  showSettings();
  enableGenerate();
}

elements.dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
});

elements.dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  handleFile(event.dataTransfer.files[0]);
});

elements.dropzone.addEventListener("click", (event) => {
  if (event.target.closest('label[for="video-input"]')) {
    return;
  }
  elements.videoInput.click();
});

const uploadLabel = document.querySelector('label[for="video-input"]');
if (uploadLabel) {
  uploadLabel.addEventListener("click", (event) => {
    event.stopPropagation();
  });
}

elements.videoInput.addEventListener("change", (event) => {
  handleFile(event.target.files[0]);
});

const queryParams = new URLSearchParams(window.location.search);
if (queryParams.get("open") === "upload") {
  setTimeout(() => {
    elements.videoInput.click();
  }, 200);
}

elements.duration.addEventListener("input", (event) => {
  state.duration = Number(event.target.value);
  elements.durationValue.textContent = `${state.duration}s`;
});

elements.platform.addEventListener("change", (event) => {
  state.platform = event.target.value;
});

document.querySelectorAll(".pill-group").forEach((group) => {
  group.addEventListener("click", (event) => {
    const btn = event.target.closest(".pill");
    if (!btn) return;
    const groupName = group.dataset.pill;
    setPillActive(groupName, btn.dataset.value);
    if (groupName === "style") state.style = btn.dataset.value;
    if (groupName === "intensity") state.intensity = btn.dataset.value;
    if (groupName === "language") state.language = btn.dataset.value;
    if (groupName === "resolution") state.resolution = btn.dataset.value;
  });
});

elements.captionsToggle.addEventListener("click", () => {
  state.captions = !state.captions;
  elements.captionsToggle.classList.toggle("active", state.captions);
  elements.captionsStatus.textContent = state.captions ? "ON" : "OFF";
});

function updateProgress(status, value) {
  elements.progressStatus.textContent = status;
  elements.progressValue.textContent = `${value}%`;
  elements.progressFill.style.width = `${value}%`;
  elements.stepItems.forEach((item) => item.classList.remove("active"));
  if (status === "fetching_url" || status === "downloading" || status === "queued") {
    elements.stepItems[0].classList.add("active");
  } else if (status === "analyzing") {
    elements.stepItems[1].classList.add("active");
  } else if (status === "planning") {
    elements.stepItems[2].classList.add("active");
  } else if (status === "rendering") {
    elements.stepItems[3].classList.add("active");
  } else {
    elements.stepItems[0].classList.add("active");
  }
}

function showProgress() {
  elements.progressSection.classList.remove("hidden");
  elements.progressError.classList.add("hidden");
}

function showResult() {
  elements.resultSection.classList.remove("hidden");
}

function resetState() {
  state.file = null;
  state.sourceType = "upload";
  state.sourceUrl = "";
  state.jobId = null;
  elements.videoInput.value = "";
  elements.uploadInfo.classList.add("hidden");
  elements.settingsSection.classList.add("hidden");
  elements.progressSection.classList.add("hidden");
  elements.resultSection.classList.add("hidden");
  if (previewUrl) {
    URL.revokeObjectURL(previewUrl);
    previewUrl = null;
  }
  elements.previewVideo.removeAttribute("src");
  elements.previewVideo.load();
  elements.previewBox.classList.remove("has-video");
  elements.previewName.textContent = "No file selected";
  elements.previewSize.textContent = "Size: --";
  elements.fileDuration.textContent = "Duration: --";
  enableGenerate();
}


function showAudio(element, blob) {
  const url = URL.createObjectURL(blob);
  element.src = url;
  element.classList.remove("hidden");
}

function setMessage(element, message, isError = false) {
  if (!element) return;
  element.textContent = message;
  element.classList.toggle("error", isError);
  element.classList.remove("hidden");
}

function clearMessage(element) {
  if (!element) return;
  element.textContent = "";
  element.classList.add("hidden");
  element.classList.remove("error");
}

if (elements.ttsGenerate) {
  elements.ttsGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    const text = elements.ttsText.value.trim();
    clearMessage(elements.ttsMessage);
    if (!text) {
      setMessage(elements.ttsMessage, "Please enter text.", true);
      return;
    }
    setMessage(elements.ttsMessage, "Generating...");
    const payload = {
      text,
      voice_id: elements.ttsVoiceId.value.trim() || undefined,
        speed: Number(elements.ttsSpeed.value),
    };
    const response = await fetch(`${API_BASE}/elevenlabs/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
      if (!response.ok) {
        const message = await response.text();
      setMessage(elements.ttsMessage, message || "TTS failed.", true);
        return;
      }
    const blob = await response.blob();
    ttsBlob = blob;
    showAudio(elements.ttsAudio, blob);
    setMessage(elements.ttsMessage, "Ready.");
  });
}

if (elements.ttsUse) {
  elements.ttsUse.addEventListener("click", (event) => {
    event.preventDefault();
    clearMessage(elements.ttsMessage);
    if (!ttsBlob) {
      setMessage(elements.ttsMessage, "Generate TTS first.", true);
      return;
    }
    if (state.sourceType === "url") {
      setMessage(
        elements.ttsMessage,
        "Use video upload to embed this voice-over.",
        true
      );
      return;
    }
    useTtsInVideo = true;
    elements.voiceoverEnabled.checked = true;
    elements.voiceoverText.value = "";
    elements.voiceoverSpeed.value = "1";
    setMessage(elements.ttsMessage, "Voice-over linked to video.", false);
  });
}

if (elements.stsGenerate) {
  elements.stsGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    clearMessage(elements.stsMessage);
    if (!elements.stsAudio.files[0]) {
      setMessage(elements.stsMessage, "Please upload audio.", true);
      return;
    }
    setMessage(elements.stsMessage, "Converting...");
    const formData = new FormData();
    formData.append("audio", elements.stsAudio.files[0]);
    formData.append("voice_id", elements.stsVoiceId.value.trim());
    const response = await fetch(`${API_BASE}/elevenlabs/sts`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.stsMessage, message || "Speech to Speech failed.", true);
      return;
    }
    const blob = await response.blob();
    showAudio(elements.stsOutput, blob);
    setMessage(elements.stsMessage, "Ready.");
  });
}

if (elements.sttGenerate) {
  elements.sttGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    clearMessage(elements.sttMessage);
    if (!elements.sttAudio.files[0]) {
      setMessage(elements.sttMessage, "Please upload audio.", true);
      return;
    }
    setMessage(elements.sttMessage, "Transcribing...");
    const formData = new FormData();
    formData.append("audio", elements.sttAudio.files[0]);
    if (elements.sttLang.value.trim()) {
      formData.append("language", elements.sttLang.value.trim());
    }
    const response = await fetch(`${API_BASE}/elevenlabs/stt`, {
      method: "POST",
      body: formData,
    });
    const data = await response.json();
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.sttMessage, message || "Speech to Text failed.", true);
      return;
    }
    elements.sttOutput.value = JSON.stringify(data, null, 2);
    elements.sttOutput.classList.remove("hidden");
    setMessage(elements.sttMessage, "Ready.");
  });
}

if (elements.sfxGenerate) {
  elements.sfxGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    const prompt = elements.sfxPrompt.value.trim();
    clearMessage(elements.sfxMessage);
    if (!prompt) {
      setMessage(elements.sfxMessage, "Please describe a sound.", true);
      return;
    }
    setMessage(elements.sfxMessage, "Generating...");
    const payload = {
      prompt,
      duration_s: Number(elements.sfxDuration.value),
    };
    const response = await fetch(`${API_BASE}/elevenlabs/sfx`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.sfxMessage, message || "SFX failed.", true);
      return;
    }
    const blob = await response.blob();
    showAudio(elements.sfxOutput, blob);
    setMessage(elements.sfxMessage, "Ready.");
  });
}

if (elements.isolateGenerate) {
  elements.isolateGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    clearMessage(elements.isolateMessage);
    if (!elements.isolateAudio.files[0]) {
      setMessage(elements.isolateMessage, "Please upload audio.", true);
      return;
    }
    setMessage(elements.isolateMessage, "Isolating...");
    const formData = new FormData();
    formData.append("audio", elements.isolateAudio.files[0]);
    const response = await fetch(`${API_BASE}/elevenlabs/isolate`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.isolateMessage, message || "Audio isolation failed.", true);
      return;
    }
    const blob = await response.blob();
    showAudio(elements.isolateOutput, blob);
    setMessage(elements.isolateMessage, "Ready.");
  });
}

if (elements.musicGenerate) {
  elements.musicGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    const prompt = elements.musicPrompt.value.trim();
    clearMessage(elements.musicMessage);
    if (!prompt) {
      setMessage(elements.musicMessage, "Please describe the music.", true);
      return;
    }
    setMessage(elements.musicMessage, "Generating...");
    const payload = {
      prompt,
      duration_s: Number(elements.musicDuration.value),
    };
    const response = await fetch(`${API_BASE}/elevenlabs/music`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.musicMessage, message || "Music generation failed.", true);
      return;
    }
    const blob = await response.blob();
    showAudio(elements.musicOutput, blob);
    setMessage(elements.musicMessage, "Ready.");
  });
}

if (elements.voiceGenerate) {
  elements.voiceGenerate.addEventListener("click", async (event) => {
    event.preventDefault();
    const name = elements.voiceName.value.trim();
    const description = elements.voiceDesc.value.trim();
    clearMessage(elements.voiceMessage);
    if (!name || !description) {
      setMessage(elements.voiceMessage, "Name and description required.", true);
      return;
    }
    setMessage(elements.voiceMessage, "Creating...");
    const payload = { name, description };
    const response = await fetch(`${API_BASE}/elevenlabs/voice`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      const message = await response.text();
      setMessage(elements.voiceMessage, message || "Voice generation failed.", true);
      return;
    }
    elements.voiceOutput.value = JSON.stringify(data, null, 2);
    elements.voiceOutput.classList.remove("hidden");
    setMessage(elements.voiceMessage, "Ready.");
  });
}

function startPolling(jobId) {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const response = await fetch(`${API_BASE}/status/${jobId}`);
      const data = await response.json();
      updateProgress(data.status, data.progress || 0);

      if (data.status === "done") {
        clearInterval(pollTimer);
        elements.downloadBtn.dataset.jobId = jobId;
        elements.resultStyle.textContent = state.style;
        elements.resultDuration.textContent = `${state.duration}s`;
        elements.resultPlayer.src = `${API_BASE}/download/${jobId}`;
        showResult();
      }
      if (data.status === "error") {
        clearInterval(pollTimer);
        elements.progressError.textContent = data.error || "Unknown error";
        elements.progressError.classList.remove("hidden");
      }
    } catch (err) {
      clearInterval(pollTimer);
      elements.progressError.textContent = err.message;
      elements.progressError.classList.remove("hidden");
    }
  }, 1200);
}

elements.generateBtn.addEventListener("click", async () => {
  if (state.sourceType === "upload" && !state.file) return;

  showProgress();
  const sharedPayload = {
    platform: state.platform,
    duration: String(state.duration),
    style: state.style,
    cut_intensity: state.intensity,
    language: state.language,
    captions: state.captions ? "ON" : "OFF",
    resolution: state.resolution,
    content_preset: elements.contentPreset.value,
    output_resolution: elements.outputResolution.value,
    reframe_mode: elements.reframeMode.value,
    fps: elements.fps.value,
    filters_enabled: false,
    filter_preset: "none",
    brightness: 0,
    contrast: 1,
    saturation: 1,
    gamma: 1,
    sharpness: 0,
    denoise: false,
    vignette: false,
    grain: false,
    captions_enabled: state.captions,
    caption_template: elements.captionTemplate.value,
    caption_position: elements.captionPosition.value,
    caption_size: elements.captionSize.value,
    caption_safe_margin: elements.captionSafe.value,
    caption_highlight_keywords: elements.captionHighlight.checked,
    caption_max_chars_per_line: elements.captionMaxChars.value,
    transition_type: elements.transitionType.value,
    transition_duration: elements.transitionDuration.value,
    notify_email: elements.notifyEmail ? elements.notifyEmail.value : "",
    audio_enhance: elements.audioEnhance.checked,
    audio_loudnorm: elements.audioLoudnorm.checked,
    audio_compressor: elements.audioCompressor.checked,
    audio_denoise: elements.audioDenoise.checked,
    audio_isolation_enabled: elements.audioIsolation.checked,
    sfx_enabled: elements.sfxEnabled.checked,
    stt_captions: elements.sttCaptions.checked,
    voiceover_enabled: elements.voiceoverEnabled.checked,
    voiceover_text: elements.voiceoverText.value,
    voiceover_voice_id: elements.voiceoverVoiceId.value,
    voiceover_speed: elements.voiceoverSpeed.value,
    voiceover_mode: elements.voiceoverMode.value,
    music_enabled: elements.musicEnabled.checked,
    music_volume: elements.musicVolume.value,
    music_ducking: elements.musicDucking.checked,
    ai_visuals_enabled: elements.aiVisualsEnabled.checked,
    ai_visuals_style: elements.aiVisualsStyle.value,
    ai_visuals_intensity: elements.aiVisualsIntensity.value,
    ai_visuals_max_overlays: elements.aiVisualsMax.value,
    ai_visuals_transparent_png: elements.aiVisualsTransparent.checked,
    ai_broll_enabled: elements.aiBrollEnabled.checked,
    ai_broll_mode: elements.aiBrollMode.value,
    ai_video_model: elements.aiVideoModel.value,
  };

  let response;
  if (state.sourceType === "url") {
    response = await fetch(`${API_BASE}/start_from_url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: state.sourceUrl, ...sharedPayload }),
    });
  } else {
    const formData = new FormData();
    formData.append("file", state.file);
    Object.entries(sharedPayload).forEach(([key, value]) =>
      formData.append(key, value)
    );
    if (useTtsInVideo && ttsBlob) {
      formData.append("voiceover_file", ttsBlob, ttsFilename);
      formData.append("voiceover_pre_sped", "true");
      formData.set("voiceover_text", "");
      formData.set("voiceover_speed", "1");
    }
    if (elements.musicFile.files[0]) {
      formData.append("music_file", elements.musicFile.files[0]);
    }
    response = await fetch(`${API_BASE}/start`, { method: "POST", body: formData });
  }

  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || item.type).join(" | ")
      : detail || "Failed to start.";
    elements.progressError.textContent = message;
    elements.progressError.classList.remove("hidden");
    return;
  }
  state.jobId = data.job_id;
  startPolling(state.jobId);
});

elements.downloadBtn.addEventListener("click", () => {
  if (!state.jobId) return;
  window.location.href = `${API_BASE}/download/${state.jobId}`;
});

elements.restartBtn.addEventListener("click", () => {
  resetState();
  window.scrollTo({ top: 0, behavior: "smooth" });
});

enableGenerate();