import json
import unittest
from unittest.mock import Mock, call, patch
import subprocess

from server import BridgeError, VoiceInkBridge, validate_mode


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


if __name__ == "__main__":
    unittest.main()
