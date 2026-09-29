"""
Sarvam AI Connector — Indian-language translation and localization.

Uses Sarvam AI's chat completions endpoint for translation.
In mock mode, returns placeholder translations with language tags.
"""

import logging
from typing import Any, Dict, List

from content_studio.connectors.base import ConnectorBase
from content_studio.config import StudioConfig, SUPPORTED_LANGUAGES

logger = logging.getLogger("content_studio.connectors.sarvam")

SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
SARVAM_MODEL = "sarvam-105b-conversations"



class SarvamConnector(ConnectorBase):
    """Connector for Sarvam AI translation and localization."""

    @property
    def is_mock(self) -> bool:
        return self.force_mock or self.config.MOCK_MODE or not self.config.SARVAM_API_KEY

    def translate(self, text: str, target_language: str) -> Dict[str, Any]:
        """Translate text to the target language.

        Args:
            text: Source text (English).
            target_language: ISO 639-1 language code (e.g., "hi", "ta").

        Returns:
            Dict with translated_text, token_stats, and is_mock flag.
        """
        lang_name = SUPPORTED_LANGUAGES.get(target_language, target_language)

        if self.is_mock:
            logger.info(self._label(f"Mock translation to {lang_name}"))
            return {
                "translated_text": f"[MOCK: Sarvam → {lang_name}] {text}",
                "token_stats": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                },
                "is_mock": True,
            }

        logger.info(self._label(f"Translating to {lang_name} via Sarvam AI"))

        try:
            import requests

            system_prompt = (
                f"Translate the following text to {lang_name}. "
                f"Provide a natural, culturally appropriate translation — "
                f"not a word-for-word transliteration. Return only the translated text."
            )

            payload = {
                "model": SARVAM_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                "temperature": 0.3,
            }

            def call_sarvam():
                resp = requests.post(
                    SARVAM_URL,
                    headers={
                        "Authorization": f"Bearer {self.config.SARVAM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=30,
                )
                resp.raise_for_status()
                return resp.json()

            data = self.retry_with_backoff(call_sarvam)
            translated = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})

            return {
                "translated_text": translated,
                "token_stats": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
                "is_mock": False,
            }

        except Exception as e:
            logger.error(f"Sarvam translation failed: {e}")
            return {
                "translated_text": f"[Sarvam Error] {text}",
                "error": str(e),
                "is_mock": False,
            }

    def generate_canva_prompt(
        self,
        design_context: Dict[str, Any],
        scenes: List[Any] = None,
        language: str = "en",
    ) -> str:
        """Generate a high-impact, professional prompt specifically for Canva AI / Magic Design.

        Uses Sarvam AI (sarvam-105b-conversations) to synthesize the design concept,
        topics, and visual theme into an optimal Canva presentation prompt.
        """
        concept = design_context.get("concept", "Healthcare & Hospital")
        file_name = design_context.get("file_name", "Presentation")
        colors = design_context.get("colors", ["#0284c7", "#059669", "#ffffff", "#0f172a"])
        texts = design_context.get("texts", [])[:15]

        scene_titles = []
        if scenes:
            for s in scenes:
                t = getattr(s, "title", "") if not isinstance(s, dict) else s.get("title", "")
                if t:
                    scene_titles.append(t)

        if self.is_mock:
            return (
                f"Design a modern, pitch-ready 5-slide presentation for '{concept}' ({file_name}). "
                f"Include slides for: {', '.join(scene_titles) if scene_titles else 'Overview, Core Services, Patient Care, Diagnostics, and Emergency Support'}. "
                f"Use a clean aesthetic with medical blue, calming teal, and crisp white tones ({', '.join(colors[:3])}). "
                f"Feature rounded feature cards, high-contrast bold headings, minimalist healthcare icons, and generous whitespace."
            )

        try:
            import requests

            prompt_input = (
                f"You are an expert presentation designer and prompt engineer for Canva AI (Magic Design).\n"
                f"Create a single-paragraph, high-impact Canva AI prompt for a presentation with this context:\n"
                f"- Concept / Domain: {concept}\n"
                f"- Project Name: {file_name}\n"
                f"- Topics: {', '.join(scene_titles[:4]) if scene_titles else ', '.join(texts[:5])}\n"
                f"- Palette: {', '.join(colors[:4])}\n\n"
                f"Instructions for Canva AI: Specify exact presentation style, slide breakdown (Title, Feature Cards, Workflow, Impact), "
                f"visual aesthetic, color scheme, and modern typography so Canva Magic Design generates a stunning, pitch-ready deck. "
                f"Return ONLY the prompt string for Canva AI, with no markdown intro or outro."
            )

            payload = {
                "model": SARVAM_MODEL,
                "messages": [
                    {"role": "user", "content": prompt_input}
                ],
                "temperature": 0.4,
            }

            resp = requests.post(
                SARVAM_URL,
                headers={
                    "Authorization": f"Bearer {self.config.SARVAM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=25,
            )
            if resp.status_code == 200:
                result = resp.json()["choices"][0]["message"]["content"].strip()
                # Clean up any surrounding quotes or bold tags if needed
                if result.startswith('"') and result.endswith('"'):
                    result = result[1:-1]
                logger.info(f"Sarvam AI generated Canva prompt ({len(result)} chars)")
                return result
            else:
                logger.warning(f"Sarvam prompt gen failed with {resp.status_code}, using fallback.")
        except Exception as e:
            logger.error(f"Error calling Sarvam for Canva prompt: {e}")

        # Fallback prompt
        return (
            f"Create a sleek, professional presentation for '{concept}' featuring {', '.join(scene_titles) if scene_titles else 'Overview, Services, and Patient Portal'}. "
            f"Use modern healthcare colors (teal, slate blue, and clean white), cards with icons, clear bold headings, and minimal text for maximum visual clarity."
        )
