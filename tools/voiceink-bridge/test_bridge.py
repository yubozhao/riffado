from array import array
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import wave
import unittest
from unittest.mock import Mock, call, patch
import subprocess

from server import BridgeError, VoiceInkBridge, same_recording, validate_mode


class ModeSafetyTests(unittest.TestCase):
    def mode(self, **overrides):
        result = {"id": "local", "name": "Riffado Local", "isEnabled": True,
                  "selectedTranscriptionModelName": "parakeet-tdt-0.6b-v3",
                  "isAIEnhancementEnabled": False}
        result.update(overrides)
        return result

    def preferences(self, modes, **extra):
        return {"modeConfigurationsV2": json.dumps(modes).encode(), **extra}

    def test_accepts_local_mode_without_enhancement(self):
        expected = self.mode()
        self.assertEqual(validate_mode(self.preferences([expected]), "Riffado Local"), expected)

    def test_refuses_cloud_transcription(self):
        with self.assertRaises(BridgeError):
            validate_mode(self.preferences([self.mode(selectedTranscriptionModelName="whisper-1")]), "Riffado Local")

    def test_refuses_enhancement_and_missing_enhancement_flag(self):
        for value in [True, None]:
            with self.subTest(value=value), self.assertRaises(BridgeError):
                validate_mode(self.preferences([self.mode(isAIEnhancementEnabled=value)]), "Riffado Local")

    def test_refuses_another_active_mode_even_when_local_mode_exists(self):
        modes = [self.mode(), self.mode(id="other", name="Cloud", selectedTranscriptionModelName="whisper-1")]
        with self.assertRaises(BridgeError):
            validate_mode(self.preferences(modes, activeConfigurationId="other"), "Riffado Local")

    def test_default_takes_precedence_over_first_enabled_mode(self):
        modes = [self.mode(), self.mode(id="other", name="Other", isDefault=True)]
        with self.assertRaises(BridgeError):
            validate_mode(self.preferences(modes), "Riffado Local")

    def test_disabled_mode_is_not_used(self):
        with self.assertRaises(BridgeError):
            validate_mode(self.preferences([self.mode(isEnabled=False)]), "Riffado Local")


class AutomationRecoveryTests(unittest.TestCase):
    def test_observes_started_job_without_pressing_start_again(self):
        for state in ["processing", "completed"]:
            with self.subTest(state=state):
                bridge = object.__new__(VoiceInkBridge)
                bridge.control = Mock(side_effect=[BridgeError("AX timeout"), state])
                bridge.start_once("unique.wav")
                self.assertEqual(bridge.control.call_args_list,
                                 [call("start", "unique.wav"), call("status", "unique.wav")])

    def test_stale_queue_reference_is_only_tolerated_for_reading_status(self):
        bridge = object.__new__(VoiceInkBridge)
        failed = subprocess.CompletedProcess([], 1, "", "Invalid index. (-1719)")
        with patch("server.subprocess.run", return_value=failed):
            self.assertEqual(bridge.control("status", "unique.wav"), "transition")
            with self.assertRaises(BridgeError):
                bridge.control("start", "unique.wav")

    def test_stops_when_an_uncertain_start_has_not_processed_the_file(self):
        bridge = object.__new__(VoiceInkBridge)
        bridge.control = Mock(side_effect=[BridgeError("AX timeout"), "pending"])
        with self.assertRaises(BridgeError):
            bridge.start_once("unique.wav")
        self.assertEqual(bridge.control.call_count, 2)

    def test_unresponsive_status_during_inference_does_not_repeat_start(self):
        bridge = object.__new__(VoiceInkBridge)
        timeout = subprocess.TimeoutExpired("osascript", 25)
        with patch("server.subprocess.run", side_effect=timeout):
            self.assertEqual(bridge.control("status", "unique.wav"), "transition")
            with self.assertRaises(BridgeError):
                bridge.control("start", "unique.wav")


class FullRecordingTests(unittest.TestCase):
    def wav(self, path, samples):
        with wave.open(str(path), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(array("h", samples).tobytes())

    def test_matches_gain_normalization_but_rejects_wrong_or_truncated_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            source, saved = Path(directory) / "source.wav", Path(directory) / "saved.wav"
            samples = [index % 1000 - 500 for index in range(16000)]
            self.wav(source, samples)
            self.wav(saved, [sample * 2 for sample in samples])
            self.assertTrue(same_recording(source, saved))
            self.wav(saved, [sample * -2 for sample in samples])
            self.assertFalse(same_recording(source, saved))
            self.wav(saved, samples[:-1])
            self.assertFalse(same_recording(source, saved))

    def test_history_recovery_requires_matching_audio_mode_model_and_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recordings = root / "Recordings"
            recordings.mkdir()
            source, saved = root / "source.wav", recordings / "saved.wav"
            self.wav(source, list(range(-8000, 8000)))
            self.wav(saved, list(range(-8000, 8000)))
            bridge = object.__new__(VoiceInkBridge)
            bridge.mode_name, bridge.history = "Riffado Local", root / "default.store"
            with sqlite3.connect(bridge.history) as connection:
                connection.execute("CREATE TABLE ZTRANSCRIPTION (ZTEXT, ZAUDIOFILEURL, ZMODENAME, ZTRANSCRIPTIONMODELNAME, ZDURATION, ZTIMESTAMP)")
                connection.execute("INSERT INTO ZTRANSCRIPTION VALUES (?, ?, ?, ?, ?, ?)",
                                   ("Full result", saved.as_uri(), "Riffado Local", "Parakeet V3", 1.0, 1))
            self.assertEqual(bridge.history_text(source, 1), "Full result")
            self.assertIsNone(bridge.history_text(source, 2))
            self.wav(saved, [5] * 16000)
            self.assertIsNone(bridge.history_text(source, 1))

    def bridge(self, directory):
        bridge = object.__new__(VoiceInkBridge)
        bridge.root, bridge.mode_name, bridge.timeout = Path(directory), "Riffado Local", 1
        bridge.ffmpeg = "ffmpeg"
        bridge.mode = Mock(return_value={"id": "local", "selectedTranscriptionModelName": "parakeet-tdt-0.6b-v3"})
        bridge.control = Mock(return_value="closed")
        return bridge

    def conversion(self, seconds):
        def run(command, **kwargs):
            self.assertNotIn("-t", command)
            frames = int(seconds * 16000)
            with open(command[-1], "wb") as stream:
                stream.write(struct.pack("<4sI4s4sIHHIIHH4sI", b"RIFF", frames * 2 + 36,
                                         b"WAVE", b"fmt ", 16, 1, 1, 16000, 32000, 2, 16, b"data", frames * 2))
            return subprocess.CompletedProcess(command, 0)
        return run

    def test_over_two_hours_recovers_full_result_without_ui_and_caches_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = self.bridge(directory)
            bridge.history_text = Mock(return_value="Full recording text")
            with patch("server.subprocess.run", side_effect=self.conversion(7205)) as run:
                result = bridge.run_job(b"entire upload")
                self.assertEqual(result["duration"], 7205)
                self.assertTrue(result["recovered"])
                self.assertEqual(bridge.run_job(b"entire upload"), result)
                self.assertEqual(run.call_count, 1)
            bridge.control.assert_not_called()

    def test_quitting_during_job_does_not_reopen_the_app(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = self.bridge(directory)
            bridge.history_text = Mock(return_value=None)
            with patch("server.subprocess.run") as run:
                with self.assertRaisesRegex(BridgeError, "VoiceInk quit"):
                    bridge.wait_for_history(Path(directory) / "audio.wav", 60)
                run.assert_not_called()
            bridge.control.assert_called_once_with("running")

    def test_new_job_waits_for_history_without_native_save_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = self.bridge(directory)
            bridge.control = Mock(return_value="ready")
            bridge.history_text = Mock(return_value=None)
            bridge.wait_for = Mock(return_value="pending")
            bridge.start_once = Mock()
            bridge.wait_for_history = Mock(return_value="Whole transcript")
            convert = self.conversion(10000)
            with patch("server.subprocess.run", side_effect=lambda command, **kw: convert(command) if command[0] == "ffmpeg" else subprocess.CompletedProcess(command, 0)):
                result = bridge.run_job(b"full long audio")
            self.assertEqual(result["text"], "Whole transcript")
            bridge.wait_for_history.assert_called_once()
            self.assertFalse(any(args.args[0] == "export" for args in bridge.control.call_args_list))


if __name__ == "__main__":
    unittest.main()
