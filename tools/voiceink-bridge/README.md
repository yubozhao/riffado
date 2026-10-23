# VoiceInk Mac app bridge

This optional self-host companion lets Riffado send audio to the **installed
VoiceInk app**, then save VoiceInk's completed transcript through Riffado's normal
encrypted transcription path. It uses AppleScript UI automation, not a separate
copy of VoiceInk's inference engine. Verified with VoiceInk 2.21 on Apple Silicon.

## Requirements and setup

- macOS with a logged-in desktop session; VoiceInk installed in `/Applications`.
- Python 3 (standard library only) and `ffmpeg` available on the host PATH.
- A local Parakeet model downloaded in VoiceInk.
- Automation access to System Events and Accessibility access for the terminal
  or application running the bridge. Grant these yourself in macOS if requested.
  The bridge does not change permissions or install a background login agent.

In VoiceInk, create an enabled mode named **Riffado Local**, select **Parakeet
V3**, turn **AI Enhancement off**, and select that mode. The bridge verifies the
effective mode's saved configuration before starting. Cloud models and enabled
enhancement are refused. This version supports the Parakeet V3 mode only.
Model downloads remain a manual VoiceInk action.

Create a private bridge key once:

```sh
mkdir -p "$HOME/.local/share/riffado"
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path.home() / '.local/share/riffado/voiceink.env'
with p.open('x') as f:
    f.write('RIFFADO_VOICEINK_KEY=' + secrets.token_hex(24) + '\n')
p.chmod(0o600)
PY
sh tools/voiceink-bridge/start.sh
```

Keep that terminal running. In Riffado Settings → Providers select **VoiceInk**:

- Base URL: `http://host.docker.internal:8084/v1` for Riffado in Docker, or
  `http://127.0.0.1:8084/v1` when Riffado runs directly on the Mac.
- API key: the `RIFFADO_VOICEINK_KEY` value from the private file above.
- Model: `voiceink-app`.
- Use for transcription: enabled. Enhancement is unsupported.

Upload audio or choose Transcribe from a recording. Keep automatic title and
summary generation off if transcription is the only desired operation.

## Behavior and limitations

The loopback server accepts authenticated OpenAI-compatible multipart requests at
`POST /v1/audio/transcriptions`. Concurrent requests wait for their turn; one
request runs at a time, with a cross-process file lock around VoiceInk operations.
Requests above 512 MiB are
refused. There is no recording-duration cutoff; conversion preserves the entire
audio track. Riffado sends VoiceInk the original audio without Whisper-specific
lossy compression. `GET /health` reports server status and `GET /v1/models` lists
the model.

Each job receives a unique filename. The bridge opens the entire file in VoiceInk
and presses Start once. It reads completed text from VoiceInk's local history
using a read-only SQLite connection. Candidates must match the dedicated mode,
Parakeet V3 model, duration and exact decoded frame count; distributed waveform
samples across the recording must also match after VoiceInk's gain normalization.
It never writes VoiceInk's database or reads the clipboard. This requires the
VoiceInk 2.21 history schema and its retained converted audio.

There is no Save dialog automation. Completed matching history results can be
recovered after an interrupted request without transcribing again. Successful
bridge responses are also cached by the uploaded audio's SHA-256 hash.

Auto-transcribe remains supported: VoiceInk automatically processes newly synced
or uploaded recordings. Existing untranscribed recordings are not retried on every
sync with this provider. Use Transcribe manually to retry an older recording.
VoiceInk opens when a new job needs it; idle syncs and result recovery do not open
its window. Closing its window during a job allows transcription and result
collection to finish in the background. Quitting the app stops waiting without relaunching it.
A later new recording can open it again.

Keep the Mac unlocked and avoid interacting with VoiceInk during a job. The
bridge uses AppleScript only for importing/starting a recording. It refuses to
start while other files are pending or active and never clears queues or deletes
history. Automation expects English VoiceInk controls. A locked/headless Mac
cannot run this bridge. Docker hosts must support access to host loopback through
`host.docker.internal` (verified with OrbStack).

The result is VoiceInk's plain transcript text. This integration does not add
speaker labels or timestamps that VoiceInk did not produce, and makes no claim
about reaching a target transcription accuracy. Select language and formatting
in the dedicated VoiceInk mode. The API accepts `auto` and `en` but does not
override that mode's language settings.

Jobs, transcripts and status files live privately under
`~/.local/share/riffado/voiceink-jobs`. Successful jobs remove the bridge's
temporary audio. Failed jobs retain the WAV and mark `needs_review`; inspect
VoiceInk and resolve its pending work before submitting another recording.
There is no automatic retry of Start or failed desktop actions. A one-hour
processing timeout stops waiting but does not truncate the recording. A later
manual retry can recover the completed local result. HTTP failures use
422 for failed desktop actions. The VoiceInk provider preset disables automatic
SDK request retries, including retries after a lost connection. No cloud fallback is
provided, and no transcript or recording is uploaded to an inference service.

Run bridge tests with `python3 -B -m unittest discover -s tools/voiceink-bridge -v`.
