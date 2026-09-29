"""
LLM Connector — Script and Storyboard Generation.

Uses Groq with Qwen (qwen/qwen3.8-27b) or OpenAI-compatible models to generate
content based directly on extracted Figma design tokens and page text.
"""

import json
import logging
from typing import Any, Dict, List, Tuple

from content_studio.connectors.base import ConnectorBase
from content_studio.config import StudioConfig
from content_studio.models import Scene

logger = logging.getLogger("content_studio.connectors.llm")


class LLMConnector(ConnectorBase):
    """Connector for script generation via LLM (Groq / OpenAI compatible)."""

    @property
    def is_mock(self) -> bool:
        return self.force_mock or self.config.MOCK_MODE or not bool(getattr(self.config, "GROQ_API_KEY", ""))

    def generate_script(
        self,
        design_context: dict,
        output_type: str,
        scene_count: int = 3,
    ) -> Tuple[str, List[Scene]]:
        """Generate a script and structured scenes from design context.

        Args:
            design_context: Extracted design data (texts, frames, colors, concept).
            output_type: "pptx" or "video".
            scene_count: Number of scenes to generate.

        Returns:
            Tuple of (script_text, list_of_Scene).
        """
        if self.is_mock:
            logger.info(self._label("Returning contextual mock script."))
            return self._mock_script(design_context, output_type)

        logger.info(self._label(f"Generating script via {self.config.LLM_PROVIDER} ({self.config.LLM_MODEL})"))
        try:
            import openai

            client = openai.OpenAI(
                base_url=self.config.LLM_BASE_URL,
                api_key=self.config.GROQ_API_KEY,
            )

            concept = design_context.get("concept", "Product")
            file_name = design_context.get("file_name", "Design")
            texts = design_context.get("texts", [])[:25]
            frames = design_context.get("frames", [])[:15]
            colors = design_context.get("colors", [])
            fonts = design_context.get("fonts", [])

            prompt = f"""You are an executive presentation designer and scriptwriter.
Analyze the extracted Figma design data below and write an engaging {scene_count}-scene presentation/video script for a '{output_type}'.

CRITICAL INSTRUCTIONS:
- The content MUST be specifically about the actual subject matter in the design (e.g. if the design is for a hospital, clinic, or healthcare app, write specifically about patient care, doctor appointments, emergency facilities, and medical specialties).
- For each scene, provide 3 to 4 crisp, presentation-ready bullet points (short, high-impact statements suitable for executive slide presentation, NOT descriptive paragraphs).
- Provide a smooth spoken narration for voiceover (2-3 natural sentences).

EXTRACTED FIGMA DESIGN DATA:
- Project / File Name: {file_name}
- Concept: {concept}
- Key Text Content: {json.dumps(texts, ensure_ascii=False)}
- Pages & Frames: {json.dumps(frames, ensure_ascii=False)}
- Color Theme: {colors}

Return ONLY a valid JSON object matching this exact structure:
{{
  "script": "Full narration script connecting all scenes together into a cohesive walkthrough",
  "scenes": [
    {{
      "title": "Clear scene title (e.g. 24/7 Emergency Care, Doctor Consultations)",
      "bullet_points": [
        "First slide bullet point highlighting key feature or patient benefit",
        "Second slide bullet point with operational detail or availability",
        "Third slide bullet point emphasizing outcome, quality, or technology"
      ],
      "narration_text": "Spoken voiceover narration describing this feature in detail (2-3 sentences)",
      "visual_description": "Visual layout and UI element notes",
      "duration_sec": 8.0
    }}
  ]
}}"""

            response = client.chat.completions.create(
                model=self.config.LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1200,
                temperature=0.4,
            )
            content = response.choices[0].message.content.strip()

            # Clean JSON formatting
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            parsed = json.loads(content)
            script_text = parsed.get("script", "")
            scenes = []
            for s in parsed.get("scenes", []):
                scenes.append(Scene(
                    title=s.get("title", "Scene"),
                    bullet_points=s.get("bullet_points", []),
                    narration_text=s.get("narration_text", ""),
                    visual_description=s.get("visual_description", ""),
                    duration_sec=float(s.get("duration_sec", 8.0)),
                ))

            if not script_text:
                script_text = "\n\n".join(s.narration_text for s in scenes)

            logger.info(f"Successfully generated {len(scenes)} scenes via LLM.")
            return script_text, scenes

        except Exception as e:
            logger.error(f"LLM generation failed: {e}, falling back to contextual script")
            return self._mock_script(design_context, output_type)

    def _mock_script(self, design_context: dict, output_type: str) -> Tuple[str, List[Scene]]:
        """Return deterministic contextual script data."""
        concept = design_context.get("concept", "Healthcare & Hospital")
        texts = design_context.get("texts", [])

        if "hospital" in concept.lower() or "medicine" in concept.lower() or any("hospital" in t.lower() or "doctor" in t.lower() for t in texts):
            scenes = [
                Scene(
                    title="Welcome to HealthTrack Hospital & Medical Center",
                    bullet_points=[
                        "Comprehensive digital healthcare companion for seamless patient care",
                        "Instant access to top-rated doctors, clinical specialties, and local clinics",
                        "User-friendly splash screen transitioning into personalized patient dashboard",
                    ],
                    narration_text="Welcome to HealthTrack, your comprehensive digital healthcare companion. Our journey begins with an intuitive interface designed for ease of use. Users can effortlessly search for specific medical specialities or top-rated doctors, select their city, and instantly book consultations.",
                    visual_description="Modern hospital exterior and welcoming reception lobby with doctor directory and emergency contact banners.",
                    duration_sec=8.0,
                ),
                Scene(
                    title="Specialized Departments & Doctor Appointments",
                    bullet_points=[
                        "Direct booking across Cardiology, Neurology, Pediatrics, and Oncology",
                        "Real-time specialist availability schedule with verified doctor credentials",
                        "One-click appointment confirmation with calendar sync and SMS reminders",
                    ],
                    narration_text="Explore our comprehensive clinical departments including Cardiology, Neurology, Pediatrics, and Oncology. Easily book appointments with leading specialists through our seamless digital patient portal.",
                    visual_description="Department cards displaying specialist doctors, consultation hours, and an interactive 'Book Appointment' interface.",
                    duration_sec=12.0,
                ),
                Scene(
                    title="24/7 Emergency & Diagnostic Services",
                    bullet_points=[
                        "Round-the-clock emergency trauma response and ambulance dispatch",
                        "Advanced diagnostic imaging (MRI, CT, Ultrasound) with rapid lab results",
                        "Integrated health records accessible securely from any device",
                    ],
                    narration_text="In an emergency, every second counts. Our 24/7 trauma center, advanced diagnostic imaging, and intensive care units ensure immediate, life-saving medical attention whenever you need it.",
                    visual_description="Emergency hotline highlight, ICU overview, and diagnostic lab equipment with rapid test result notifications.",
                    duration_sec=10.0,
                ),
            ]
        else:
            scenes = [
                Scene(
                    title="Platform Overview & Architecture",
                    bullet_points=[
                        "Unified modern cloud platform engineered for mission-critical reliability",
                        "Intuitive user interface with rapid onboarding and smart navigation",
                        "Scalable multi-tenant infrastructure with enterprise-grade security",
                    ],
                    narration_text=f"Welcome to our {concept.lower()} platform. Designed to deliver an intuitive, high-performance experience tailored to modern workflows.",
                    visual_description="Clean hero section with brand identity, key highlights, and primary call to action.",
                    duration_sec=8.0,
                ),
                Scene(
                    title="Key Capabilities & Workflow Automation",
                    bullet_points=[
                        "Real-time automated sync across distributed team operations",
                        "Interactive data analytics with customized KPI dashboards",
                        "Modular component architecture for effortless third-party integration",
                    ],
                    narration_text="Our system offers seamless integration, real-time analytics, and intelligent automation to help you achieve your goals faster.",
                    visual_description="Interactive feature grid showcasing modular components and live metrics.",
                    duration_sec=10.0,
                ),
                Scene(
                    title="Getting Started & Instant Deployment",
                    bullet_points=[
                        "Zero-friction setup with automated migration and role configuration",
                        "Dedicated 24/7 enterprise support and proactive monitoring",
                        "Start your transformation today with a guided product walkthrough",
                    ],
                    narration_text="Join thousands of users transforming their operations today. Get started in minutes with our comprehensive onboarding.",
                    visual_description="Closing slide with onboarding steps, customer reviews, and registration button.",
                    duration_sec=7.0,
                ),
            ]

        script_text = "\n\n".join(
            f"[Scene {i+1}: {s.title}]\n{s.narration_text}"
            for i, s in enumerate(scenes)
        )
        script_text = f"[MOCK] Script generated for {concept} ({output_type.upper()}):\n\n{script_text}"
        return script_text, scenes
