import logging
import requests
from typing import Dict, Any
from .base import ConnectorBase
from content_studio.config import StudioConfig

class ElevenLabsConnector(ConnectorBase):
    """Connector for generating voice narration via ElevenLabs."""

    VOICE_IDS = {
        "rachel": "21m00Tcm4TlvDq8ikWAM",
        "adam": "pNInz6obpgDQGcFmaJgB",
        "bella": "EXAVITQu4vr4xnSDxMaL"
    }

    def generate_narration(self, text: str, voice_name: str = 'rachel', stability: float = 0.75, speed: float = 0.9) -> Dict[str, Any]:
        """Generate TTS audio bytes and metadata."""
        word_count = len(text.split())
        estimated_duration = word_count / 2.5
        voice_id = self.VOICE_IDS.get(voice_name.lower(), self.VOICE_IDS["rachel"])

        if self.is_mock or not getattr(self.config, 'ELEVENLABS_API_KEY', None):
            self.logger.info(self._label(f"Returning mock audio generation for voice {voice_name}."))
            return {
                "audio_bytes": None,
                "duration_sec": estimated_duration,
                "voice_used": voice_name,
                "is_mock": True
            }

        self.logger.info(self._label("Generating TTS via ElevenLabs API."))
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        
        headers = {
            "xi-api-key": self.config.ELEVENLABS_API_KEY,
            "Content-Type": "application/json"
        }
        
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": stability,
                "similarity_boost": 0.75,
                "speed": speed
            }
        }

        def call_elevenlabs():
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.content

        try:
            audio_bytes = self.retry_with_backoff(call_elevenlabs)
            return {
                "audio_bytes": audio_bytes,
                "duration_sec": estimated_duration, # Estimate, real duration requires audio processing
                "voice_used": voice_name,
                "is_mock": False
            }
        except Exception as e:
            self.logger.error(f"Error generating narration: {e}")
            return {
                "error": str(e),
                "is_mock": False
            }
