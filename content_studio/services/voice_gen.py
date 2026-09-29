import logging
import os
from typing import Dict, Any, List

from content_studio.models import Scene
from content_studio.config import StudioConfig
from content_studio.connectors.elevenlabs_connector import ElevenLabsConnector

logger = logging.getLogger(__name__)

class VoiceGenerator:
    """
    Generates voice-over audio for scenes using ElevenLabs.
    """

    def __init__(self):
        self.voice_connector = ElevenLabsConnector()

    def generate(self, scenes: List[Scene], output_dir: str, config: StudioConfig, voice_name: str = 'rachel') -> Dict[str, Any]:
        """
        Generate narration audio for all scenes.
        
        Args:
            scenes: List of Scene objects to process.
            output_dir: Directory to save generated audio files.
            config: Studio configuration.
            voice_name: Voice to use for generation.
            
        Returns:
            Dict containing updated scenes, audio_files list, total_duration_sec, and is_mock flag.
        """
        logger.info(f"Generating voice for {len(scenes)} scenes using voice: {voice_name}")
        os.makedirs(output_dir, exist_ok=True)
        
        audio_files = []
        total_duration = 0.0
        is_mock_overall = False
        
        for scene in scenes:
            audio_path = os.path.join(output_dir, f"{scene.scene_id}.mp3")
            
            result = self.voice_connector.generate_narration(
                text=scene.narration_text,
                voice_name=voice_name,
                output_path=audio_path,
                config=config
            )
            
            is_mock_overall = is_mock_overall or result.get("is_mock", True)
            duration = result.get("duration_sec", 5.0)
            
            scene.audio_path = audio_path
            scene.audio_duration_sec = duration
            
            audio_files.append(audio_path)
            total_duration += duration
            
        return {
            "scenes": scenes,
            "audio_files": audio_files,
            "total_duration_sec": total_duration,
            "is_mock": is_mock_overall
        }
