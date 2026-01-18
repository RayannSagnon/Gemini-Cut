# Auto-Shorts 9:16 (MVP)

Web app complète qui génère automatiquement un Short vertical 9:16 à partir d'une vidéo, avec Gemini API + FFmpeg.

## Prérequis

- Python 3.10+
- FFmpeg installé localement
- Clé API Gemini

## Installation (Windows)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Installer FFmpeg:
- Télécharger depuis https://ffmpeg.org/download.html
- Ajouter `ffmpeg` au `PATH`

## Installation (macOS/Linux)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Installer FFmpeg:
- macOS: `brew install ffmpeg`
- Ubuntu: `sudo apt-get install ffmpeg`

## Configuration

Définir la clé Gemini:

Windows (PowerShell):
```powershell
setx GEMINI_API_KEY "votre_cle"
```

macOS/Linux:
```bash
export GEMINI_API_KEY="votre_cle"
```

Optionnel (ElevenLabs):

Windows (PowerShell):
```powershell
setx ELEVENLABS_API_KEY "votre_cle"
setx ELEVENLABS_VOICE_ID "votre_voice_id"
```

macOS/Linux:
```bash
export ELEVENLABS_API_KEY="votre_cle"
export ELEVENLABS_VOICE_ID="votre_voice_id"
```

## Notifications email (optionnel)

Configure SMTP pour envoyer un email quand la vidéo est prête:

Windows (PowerShell):
```powershell
setx SMTP_HOST "smtp.votreprovider.com"
setx SMTP_PORT "587"
setx SMTP_USER "you@example.com"
setx SMTP_PASS "motdepasse"
setx SMTP_FROM "you@example.com"
```

macOS/Linux:
```bash
export SMTP_HOST="smtp.votreprovider.com"
export SMTP_PORT="587"
export SMTP_USER="you@example.com"
export SMTP_PASS="motdepasse"
export SMTP_FROM="you@example.com"
```

Si besoin, tu peux surcharger les endpoints ElevenLabs:
`ELEVENLABS_BASE_URL`, `ELEVENLABS_TTS_ENDPOINT`, `ELEVENLABS_STT_ENDPOINT`,
`ELEVENLABS_STS_ENDPOINT`, `ELEVENLABS_SFX_ENDPOINT`,
`ELEVENLABS_ISOLATE_ENDPOINT`, `ELEVENLABS_MUSIC_ENDPOINT`,
`ELEVENLABS_VOICES_ENDPOINT`.

Activer le téléchargement depuis plateformes (optionnel):

```bash
export ENABLE_PLATFORM_DL=true
```

Pour YouTube/TikTok/Instagram, installer `yt-dlp` (optionnel):

```bash
pip install yt-dlp
```

## Lancer l'app

```bash
uvicorn app:app --reload
```

Ouvrir: http://localhost:8000

## Dossiers

- `uploads/` : vidéos d'entrée
- `runs/` : outputs par job
- `static/` : interface web

## Notes

- L'app ne stocke rien en base de données, tout est local.
- La clé API reste côté serveur.
- Les URLs supportées sont soit directes (.mp4/.mov/.webm), soit des plateformes publiques si `ENABLE_PLATFORM_DL=true`.