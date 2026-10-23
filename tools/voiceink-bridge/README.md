# VoiceInk Mac app bridge

This optional self-host companion lets Riffado send audio to the **installed
VoiceInk app**, then save VoiceInk's exported transcript through Riffado's normal
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
`POST /v1/audio/transcriptions`. One request runs at a time, with a cross-process
file lock around VoiceInk operations. Requests above 128 MiB or two hours are
refused. `GET /health` reports server status and `GET /v1/models` lists the model.

Each job receives a unique filename. The bridge opens the file in VoiceInk,
presses Start, waits for that exact queue row, and exports that row as TXT. It
does not read VoiceInk's history database or clipboard. It does not clear queues
or delete history, and refuses to start while other files are pending or active.
VoiceInk retains its own history and converted audio under its normal settings.

Export brings VoiceInk to the foreground and uses its native Save dialog. Keep
the Mac unlocked and do not interact with VoiceInk during a job. Automation is
sensitive to VoiceInk UI changes and currently expects English controls. A
locked/headless Mac cannot run this bridge. Docker hosts must support access to
host loopback through `host.docker.internal` (verified with OrbStack).

The result is VoiceInk's plain exported text. This integration does not add
speaker labels or timestamps that VoiceInk did not produce, and makes no claim
about reaching a target transcription accuracy. Select language and formatting
in the dedicated VoiceInk mode. The API accepts `auto` and `en` but does not
override that mode's language settings.

Jobs, transcripts and status files live privately under
`~/.local/share/riffado/voiceink-jobs`. Successful jobs remove the bridge's
temporary audio. Failed jobs retain the WAV and mark `needs_review`; inspect
VoiceInk and resolve its pending work before submitting another recording.
There is no automatic retry of Start, export, or failed jobs. HTTP failures use
422 for failed desktop actions. The VoiceInk provider preset disables automatic
SDK request retries, including retries after a lost connection. No cloud fallback is
provided, and no transcript or recording is uploaded to an inference service.

Run bridge tests with `python3 -B -m unittest discover -s tools/voiceink-bridge -v`.
