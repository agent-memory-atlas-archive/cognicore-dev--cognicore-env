"""
Canva Connector — Presentation and Video Generation via Canva Connect API & AI.

Supports:
1. Live Canva Connect Import API: uploads PPTX directly to Canva so all slides and text are populated!
2. Live Canva Connect Designs API: creates presentations and video designs.
3. Fallback structured plans when offline.
"""

import base64
import json
import logging
import os
import time
import requests
from typing import Any, Dict, List

from content_studio.connectors.base import ConnectorBase
from content_studio.config import StudioConfig
from content_studio.models import Scene

logger = logging.getLogger("content_studio.connectors.canva")

CANVA_API_BASE = "https://api.canva.com/rest/v1"


class CanvaConnector(ConnectorBase):
    """Connector for generating presentations and videos via Canva Connect API and Canva AI."""

    @property
    def is_mock(self) -> bool:
        """Returns True if running in mock mode or not authorized with Canva OAuth."""
        token = getattr(self.config, "CANVA_ACCESS_TOKEN", "")
        return self.force_mock or self.config.MOCK_MODE or not bool(token)

    def import_pptx_to_canva(self, pptx_path: str, title: str) -> Dict[str, Any]:
        """Import a generated PPTX into Canva so all slides and text are fully populated."""
        token = getattr(self.config, "CANVA_ACCESS_TOKEN", "")
        if not token or not os.path.exists(pptx_path):
            return {"is_mock": True, "error": "No Canva token or file not found"}

        logger.info(self._label(f"Importing {pptx_path} into Canva via /v1/imports..."))
        try:
            title_b64 = base64.b64encode(title.encode("utf-8")).decode("ascii")
            metadata = json.dumps({
                "title_base64": title_b64,
                "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            })

            with open(pptx_path, "rb") as f:
                pptx_bytes = f.read()

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "Import-Metadata": metadata,
            }

            resp = requests.post(
                f"{CANVA_API_BASE}/imports",
                headers=headers,
                data=pptx_bytes,
                timeout=30,
            )

            if resp.status_code in (200, 201):
                job_data = resp.json().get("job", {})
                job_id = job_data.get("id")
                logger.info(f"Canva import job started: {job_id}. Waiting for conversion...")

                # Poll for up to 15 seconds for Canva to parse all slides
                for _ in range(15):
                    time.sleep(1)
                    poll_resp = requests.get(
                        f"{CANVA_API_BASE}/imports/{job_id}",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=10,
                    )
                    if poll_resp.status_code == 200:
                        poll_data = poll_resp.json().get("job", {})
                        status = poll_data.get("status")
                        if status == "success":
                            designs = poll_data.get("result", {}).get("designs", [])
                            if designs:
                                d = designs[0]
                                edit_url = d.get("urls", {}).get("edit_url")
                                view_url = d.get("urls", {}).get("view_url")
                                logger.info(f"Canva import complete! Edit URL: {edit_url}")
                                return {
                                    "design_id": d.get("id"),
                                    "edit_url": edit_url,
                                    "view_url": view_url,
                                    "title": d.get("title", title),
                                    "is_mock": False,
                                }
                        elif status == "failed":
                            logger.error(f"Canva import failed: {poll_data.get('error')}")
                            break
            else:
                logger.warning(f"Canva import API error: {resp.status_code} {resp.text}")

        except Exception as e:
            logger.error(f"Failed to import PPTX to Canva: {e}")

        return {"is_mock": True}

    def create_presentation(self, scenes: List[Scene], design_context: dict) -> Dict[str, Any]:
        """Create a Canva presentation design."""
        title = design_context.get("project_name", "AI Content Studio Presentation")
        token = getattr(self.config, "CANVA_ACCESS_TOKEN", "")

        if not self.is_mock and token:
            try:
                resp = requests.post(
                    f"{CANVA_API_BASE}/designs",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "design_type": {"type": "preset", "name": "presentation"},
                        "title": title,
                    },
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("design", {})
                    return {
                        "design_id": data.get("id"),
                        "edit_url": data.get("urls", {}).get("edit_url"),
                        "view_url": data.get("urls", {}).get("view_url"),
                        "title": data.get("title", title),
                        "is_mock": False,
                    }
            except Exception as e:
                logger.error(f"Canva presentation creation failed: {e}")

        # Structured slide plan fallback
        slides = []
        for i, s in enumerate(scenes):
            slides.append({
                "slide_number": i + 1,
                "title": s.title or f"Slide {i + 1}",
                "content": s.visual_description,
                "speaker_notes": s.narration_text,
            })

        return {
            "slide_plan": slides,
            "title": title,
            "canva_import_url": "https://www.canva.com/upload",
            "is_mock": True,
        }

    def create_video(self, scenes: List[Scene], design_context: dict, timeline: Any = None) -> Dict[str, Any]:
        """Create a Canva video design."""
        title = design_context.get("project_name", "AI Content Studio Video")
        token = getattr(self.config, "CANVA_ACCESS_TOKEN", "")

        if not self.is_mock and token:
            try:
                resp = requests.post(
                    f"{CANVA_API_BASE}/designs",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "design_type": {"type": "preset", "name": "video"},
                        "title": title,
                    },
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    data = resp.json().get("design", {})
                    return {
                        "design_id": data.get("id"),
                        "edit_url": data.get("urls", {}).get("edit_url"),
                        "view_url": data.get("urls", {}).get("view_url"),
                        "title": data.get("title", title),
                        "is_mock": False,
                    }
            except Exception as e:
                logger.error(f"Canva video creation failed: {e}")

        # Structured video plan fallback
        clips = []
        for i, s in enumerate(scenes):
            clips.append({
                "clip_number": i + 1,
                "title": s.title or f"Clip {i + 1}",
                "visuals": s.visual_description,
                "audio": s.narration_text,
                "duration": s.duration_sec,
            })

        return {
            "video_plan": clips,
            "title": title,
            "canva_import_url": "https://www.canva.com/upload",
            "is_mock": True,
        }
