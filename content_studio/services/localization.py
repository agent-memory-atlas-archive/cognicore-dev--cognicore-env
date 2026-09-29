import logging
from typing import Dict, Any, List

from content_studio.models import Scene
from content_studio.config import StudioConfig
from content_studio.connectors.sarvam_connector import SarvamConnector

logger = logging.getLogger(__name__)

class LocalizationService:
    """
    Service for localizing text using Sarvam AI for Indian languages.
    """

    def __init__(self):
        self.sarvam_connector = SarvamConnector()

    def localize(self, scenes: List[Scene], language: str, config: StudioConfig) -> Dict[str, Any]:
        """
        Translate scene narrations to the target language.
        
        Args:
            scenes: List of Scene objects to localize.
            language: Target language code (e.g., 'hi', 'ta'). 'en' skips translation.
            config: Studio configuration.
            
        Returns:
            Dict containing localized_scenes, token_stats, and is_mock flag.
        """
        if language.lower() == 'en':
            logger.info("Language is English, skipping localization.")
            return {
                "localized_scenes": scenes,
                "token_stats": {"original_tokens": 0, "compressed_tokens": 0, "reduction_pct": 0.0},
                "is_mock": False
            }
            
        logger.info(f"Localizing {len(scenes)} scenes to '{language}'")
        localized_scenes = []
        original_tokens = 0
        compressed_tokens = 0
        
        is_mock_overall = False
        
        for scene in scenes:
            original_tokens += len(scene.narration_text.split())
            
            translation_result = self.sarvam_connector.translate(
                text=scene.narration_text,
                target_lang=language,
                config=config
            )
            
            is_mock_overall = is_mock_overall or translation_result.get("is_mock", True)
            
            translated_text = translation_result.get("translated_text", f"{scene.narration_text} (Translated to {language})")
            
            compressed_tokens += len(translated_text.split())
            
            # Create a copy with translated narration
            loc_scene = Scene(
                scene_id=scene.scene_id,
                title=scene.title,
                narration_text=translated_text,
                visual_description=scene.visual_description,
                duration_sec=scene.duration_sec,
                audio_path=scene.audio_path,
                audio_duration_sec=scene.audio_duration_sec,
                visual_ref=scene.visual_ref
            )
            localized_scenes.append(loc_scene)
            
        reduction_pct = 0.0
        if original_tokens > 0:
            reduction_pct = max(0.0, ((original_tokens - compressed_tokens) / original_tokens) * 100)
            
        token_stats = {
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "reduction_pct": round(reduction_pct, 2)
        }
        
        return {
            "localized_scenes": localized_scenes,
            "token_stats": token_stats,
            "is_mock": is_mock_overall
        }
