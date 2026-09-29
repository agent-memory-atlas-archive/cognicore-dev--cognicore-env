import logging
import os
import json
from typing import Dict, Any, List

from content_studio.models import Scene
from content_studio.config import StudioConfig

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

logger = logging.getLogger(__name__)

class VisualGenerator:
    """
    Generates visual artifacts (PPTX or Video Plan) based on scenes and design context.
    """

    def generate(self, scenes: List[Scene], design_context: Dict[str, Any], output_type: str, output_dir: str, config: StudioConfig) -> Dict[str, Any]:
        """
        Generate visual content based on the requested output type.
        
        Args:
            scenes: List of Scene objects.
            design_context: Dictionary with design guidelines (colors, etc.).
            output_type: 'PPTX' or 'VIDEO'.
            output_dir: Directory to save the generated visual artifact.
            config: Studio configuration.
            
        Returns:
            Dict containing file_path (if PPTX), plan (if VIDEO), and is_mock flag.
        """
        os.makedirs(output_dir, exist_ok=True)
        
        if output_type.upper() == "PPTX":
            if PPTX_AVAILABLE:
                file_path = self._generate_pptx(scenes, design_context, output_dir)
                return {"file_path": file_path, "is_mock": False}
            else:
                logger.warning("python-pptx not available, falling back to mock PPTX generation.")
                file_path = os.path.join(output_dir, "mock_presentation.txt")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("Mock PPTX Generation\n")
                    for scene in scenes:
                        f.write(f"Slide: {scene.title}\n{scene.visual_description}\nNotes: {scene.narration_text}\n\n")
                return {"file_path": file_path, "is_mock": True}
                
        elif output_type.upper() == "VIDEO":
            plan = {
                "title": design_context.get("project_name", "Video Project"),
                "scenes": [
                    {
                        "id": s.scene_id,
                        "visuals": s.visual_description,
                        "duration": s.duration_sec
                    } for s in scenes
                ],
                "mock_status": "[MOCK]"
            }
            plan_path = os.path.join(output_dir, "video_plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, indent=2)
                
            return {"plan": plan, "file_path": plan_path, "is_mock": True}
        else:
            raise ValueError(f"Unsupported output_type: {output_type}")
            
    def _generate_pptx(self, scenes: List[Scene], design_context: Dict[str, Any], output_dir: str) -> str:
        from content_studio.services.export import ExportService
        from content_studio.models import Project
        
        proj_name = design_context.get("project_name") or design_context.get("file_name") or "Generated Presentation"
        temp_project = Project(
            project_id="presentation",
            name=proj_name,
            design_context=design_context,
            scenes=scenes,
            output_type="pptx",
        )
        exp_svc = ExportService()
        return exp_svc.export_pptx(temp_project, output_dir)

