#!/usr/bin/env python3
"""A loopback transcription API that operates the installed VoiceInk Mac app."""

import argparse
import email.parser
import email.policy
import fcntl
import hmac
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import threading
import time
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = Path(__file__).with_name("voiceink.applescript")
MODEL = "voiceink-app"
LOCAL_MODELS = {"parakeet-tdt-0.6b-v3"}


class BridgeError(Exception):
    pass


def validate_mode(preferences, expected_name):
    raw = preferences.get("modeConfigurationsV2")
    if not isinstance(raw, bytes):
        raise BridgeError("Create and enable the dedicated VoiceInk mode first")
    modes = json.loads(raw)
    enabled = [mode for mode in modes if mode.get("isEnabled") is True]
    active_id = preferences.get("activeConfigurationId")
    active = next((mode for mode in enabled if mode.get("id") == active_id), None)
    effective = active or next((mode for mode in enabled if mode.get("isDefault")), None)
    effective = effective or next(iter(enabled), None)
    if not effective or effective.get("name") != expected_name:
        raise BridgeError(f"Select the {expected_name!r} mode in VoiceInk before transcribing")
    if effective.get("selectedTranscriptionModelName") not in LOCAL_MODELS:
        raise BridgeError("The VoiceInk bridge requires an explicitly supported local Parakeet model")
    if effective.get("isAIEnhancementEnabled") is not False:
        raise BridgeError("Disable AI Enhancement in the VoiceInk bridge mode")
    return effective


class VoiceInkBridge:
    def __init__(self, root, mode_name, timeout=1800):
        self.root, self.mode_name, self.timeout = root, mode_name, timeout
        self.preferences = Path.home() / "Library/Preferences/com.prakashjoshipax.VoiceInk.plist"
        self.ffmpeg = shutil.which("ffmpeg")
        if not self.ffmpeg or not Path("/Applications/VoiceInk.app").is_dir():
            raise BridgeError("Install VoiceInk in /Applications and ffmpeg on this Mac")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def mode(self):
        try:
            return validate_mode(plistlib.loads(self.preferences.read_bytes()), self.mode_name)
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            raise BridgeError("Cannot read VoiceInk mode configuration") from error

    def control(self, action, *args):
        try:
            result = subprocess.run(["/usr/bin/osascript", str(SCRIPT), action, *map(str, args)],
                                    capture_output=True, text=True, timeout=25)
        except subprocess.TimeoutExpired as error:
            if action == "status":
                return "transition"
            raise BridgeError("VoiceInk automation timed out; inspect the app before trying again") from error
        if result.returncode and action == "status" and any(
                code in result.stderr for code in ("(-1719)", "(-1712)", "(-25202)")):
            return "transition"
        if result.returncode:
            print(f"VoiceInk {action} failed: {result.stderr.strip()}", flush=True)
            raise BridgeError("VoiceInk automation failed; check its window and macOS Automation/Accessibility access")
        return result.stdout.strip()

    def wait_for(self, filename, accepted, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.control("status", filename)
            if state in accepted:
                return state
            if state == "failed":
                raise BridgeError("VoiceInk reported a transcription failure; inspect its queue")
            time.sleep(0.5)
        raise BridgeError("VoiceInk did not finish in time; inspect its queue before submitting again")

    def transcribe(self, audio):
        with (self.root / "bridge.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise BridgeError("Another VoiceInk bridge process is already running") from error
            return self.run_job(audio)

    def start_once(self, filename):
        try:
            self.control("start", filename)
        except BridgeError:
            state = self.control("status", filename)
            if state == "transition":
                state = self.wait_for(filename, {"processing", "completed"}, self.timeout)
            if state not in {"processing", "completed"}:
                raise

    def run_job(self, audio):
        mode = self.mode()
        job_id = uuid.uuid4().hex
        directory = self.root / job_id
        directory.mkdir(mode=0o700)
        source, wav = directory / "upload", directory / f"riffado-{job_id}.wav"
        output = directory / "transcript.txt"
        started = time.monotonic()
        source.write_bytes(audio)
        status = {"job_id": job_id, "status": "preparing", "mode": self.mode_name}
        status_file = directory / "status.json"
        status_file.write_text(json.dumps(status))
        try:
            subprocess.run([self.ffmpeg, "-v", "error", "-nostdin", "-i", str(source),
                            "-map", "0:a:0", "-t", "7201", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                           check=True, capture_output=True, timeout=180)
            with wave.open(str(wav)) as recording:
                duration = recording.getnframes() / recording.getframerate()
            if not 0.3 <= duration <= 7200:
                raise BridgeError("Audio must be between 0.3 seconds and two hours")
            subprocess.run(["/usr/bin/open", "-a", "VoiceInk"], check=True, capture_output=True, timeout=10)
            self.control("navigate")
            if self.control("preflight") != "ready":
                raise BridgeError("VoiceInk has pending or active files; finish those before using Riffado")
            self.mode()
            subprocess.run(["/usr/bin/open", "-a", "VoiceInk", str(wav)],
                           check=True, capture_output=True, timeout=10)
            self.wait_for(wav.name, {"pending"}, 15)
            if self.mode()["id"] != mode["id"]:
                raise BridgeError("VoiceInk mode changed while preparing the recording")
            self.start_once(wav.name)
            status["status"] = "transcribing"
            status_file.write_text(json.dumps(status))
            self.wait_for(wav.name, {"completed"}, self.timeout)
            if output.exists():
                raise BridgeError("Unexpected export already exists; refusing to overwrite it")
            status["status"] = "exporting"
            status_file.write_text(json.dumps(status))
            self.control("export", wav.name, directory, output.name)
            deadline = time.monotonic() + 10
            while not output.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            if not output.is_file():
                raise BridgeError("VoiceInk did not save its export; inspect its save dialog")
            text = output.read_text().strip()
            if not text:
                raise BridgeError("VoiceInk exported an empty transcript")
            result = {"text": text, "model": MODEL, "engine_model": mode["selectedTranscriptionModelName"],
                      "mode": self.mode_name, "job_id": job_id,
                      "elapsed_seconds": round(time.monotonic() - started, 2)}
            (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
            status["status"] = "completed"
            wav.unlink()
            return result
        except Exception:
            status["status"] = "needs_review"
            raise
        finally:
            source.unlink(missing_ok=True)
            status_file.write_text(json.dumps(status))


def serve(bridge, port, api_key):
    busy = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(1900)

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"status": "ok", "busy": busy.locked(), "backend": "VoiceInk Mac app"})
            elif self.path == "/v1/models":
                self.send_json(200, {"object": "list", "data": [
                    {"id": MODEL, "object": "model", "owned_by": "local"}]})
            else:
                self.send_json(404, {"error": {"message": "Not found"}})

        def do_POST(self):
            if self.path != "/v1/audio/transcriptions":
                self.send_json(404, {"error": {"message": "Not found"}})
                return
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + api_key):
                self.send_json(401, {"error": {"message": "Invalid local bridge key"}})
                return
            if not busy.acquire(blocking=False):
                self.send_json(409, {"error": {"message": "VoiceInk is already processing a Riffado recording"}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 128 * 1024 * 1024:
                    raise ValueError("Audio upload limit is 128 MiB")
                content_type = self.headers.get("Content-Type", "")
                if not content_type.startswith("multipart/form-data;"):
                    raise ValueError("Expected multipart audio upload")
                message = email.parser.BytesParser(policy=email.policy.default).parsebytes(
                    f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + self.rfile.read(length))
                fields = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True)
                          for part in message.iter_parts()}
                if fields.get("model") != MODEL.encode():
                    raise ValueError("Select the voiceink-app model")
                if fields.get("response_format", b"verbose_json") not in (b"json", b"verbose_json"):
                    raise ValueError("Use json or verbose_json")
                if fields.get("language", b"auto") not in (b"en", b"auto"):
                    raise ValueError("Configure the transcription language in the VoiceInk mode")
                if not fields.get("file"):
                    raise ValueError("Audio file is required")
                self.send_json(200, bridge.transcribe(fields["file"]))
            except ValueError as error:
                self.send_json(400, {"error": {"message": str(error)}})
            except BridgeError as error:
                self.send_json(422, {"error": {"message": str(error)}})
            except Exception as error:
                print(f"VoiceInk bridge failed: {type(error).__name__}", flush=True)
                self.send_json(422, {"error": {"message": "VoiceInk bridge failed; inspect the app and local job artifacts"}})
            finally:
                busy.release()

    print(f"VoiceInk bridge listening on 127.0.0.1:{port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8084)
    parser.add_argument("--mode-name", default="Riffado Local")
    parser.add_argument("--artifacts", type=Path, default=Path.home() / ".local/share/riffado/voiceink-jobs")
    args = parser.parse_args()
    api_key = os.environ.get("RIFFADO_VOICEINK_KEY")
    if not api_key:
        parser.error("Set RIFFADO_VOICEINK_KEY before starting the bridge")
    serve(VoiceInkBridge(args.artifacts, args.mode_name), args.port, api_key)
