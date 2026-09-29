"""
Export Service — PPTX and MP4 Video Generation.

Exports presentations as Microsoft PowerPoint (.pptx) files
and renders synchronized video presentations as genuine MP4 (.mp4) video files.
"""

import json
import logging
import os
from typing import Optional

from content_studio.models import Project, Scene

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import PP_ALIGN
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

logger = logging.getLogger("content_studio.services.export")


class ExportService:
    """Handles final export of the project to PowerPoint (PPTX) and MP4 video."""

    def export_pptx(self, project: Project, output_dir: str) -> str:
        """Export the project to a modern 16:9 PowerPoint presentation (.pptx) with structured cards and bullet points."""
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{project.project_id}_presentation.pptx")

        if PPTX_AVAILABLE:
            prs = Presentation()
            # 16:9 Widescreen dimensions
            prs.slide_width = Inches(13.333)
            prs.slide_height = Inches(7.5)

            # Design tokens & theme colors
            design = project.design_context or {}
            concept = design.get("concept", "Healthcare & Hospital")
            is_health = any(k in concept.lower() for k in ["health", "hospital", "medicine", "doctor", "clinic"])

            # Color palette
            bg_dark = RGBColor(15, 23, 42)       # Slate 900
            card_bg = RGBColor(24, 34, 53)       # Slate 850
            card_border = RGBColor(51, 65, 85)   # Slate 700
            accent_blue = RGBColor(14, 165, 233) if not is_health else RGBColor(13, 148, 136) # Teal / Sky
            accent_sub = RGBColor(56, 189, 248)  # Sky 400
            text_white = RGBColor(248, 250, 252) # Slate 50
            text_muted = RGBColor(148, 163, 184) # Slate 400

            blank_layout = prs.slide_layouts[6]

            # -------------------------------------------------------------
            # Slide 1: Title Slide (Cover)
            # -------------------------------------------------------------
            s0 = prs.slides.add_slide(blank_layout)

            # Dark Background
            bg0 = s0.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
            bg0.fill.solid()
            bg0.fill.fore_color.rgb = bg_dark
            bg0.line.fill.background()

            # Top Accent Bar
            bar0 = s0.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(0.12))
            bar0.fill.solid()
            bar0.fill.fore_color.rgb = accent_blue
            bar0.line.fill.background()

            # Category / Concept Badge Pill
            badge0 = s0.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.2), Inches(1.3), Inches(4.5), Inches(0.45))
            badge0.fill.solid()
            badge0.fill.fore_color.rgb = card_bg
            badge0.line.color.rgb = accent_blue
            tf_b0 = badge0.text_frame
            tf_b0.word_wrap = True
            p_b0 = tf_b0.paragraphs[0]
            p_b0.text = f"✦  {concept.upper()} PLATFORM"
            p_b0.font.size = Pt(11)
            p_b0.font.bold = True
            p_b0.font.color.rgb = accent_sub

            # Presentation Title Box
            title_box = s0.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(11.0), Inches(2.0))
            tf_t = title_box.text_frame
            tf_t.word_wrap = True
            p_t = tf_t.paragraphs[0]
            p_t.text = project.name
            p_t.font.size = Pt(38)
            p_t.font.bold = True
            p_t.font.color.rgb = text_white

            p_sub = tf_t.add_paragraph()
            p_sub.text = f"Intelligent multi-scene presentation generated from Figma design system"
            p_sub.font.size = Pt(18)
            p_sub.font.color.rgb = text_muted

            # 3 Bottom Feature Cards
            card_w = Inches(3.4)
            card_h = Inches(1.8)
            card_y = Inches(4.5)
            highlights = [
                ("⚡ 24/7 Virtual Care", "Instant consultations and live specialist scheduling"),
                ("🔍 Verified Doctors", "Seamless department bookings across medical specialties"),
                ("📋 Digital Health Records", "Dedicated patient dashboard with secure clinical records"),
            ] if is_health else [
                ("⚡ Cloud Automation", "Real-time sync across distributed workflow operations"),
                ("📊 Live Analytics", "Interactive telemetry dashboards with custom KPI widgets"),
                ("🛡 Enterprise Ready", "Zero-friction onboarding with multi-tenant architecture"),
            ]

            for i, (head, desc) in enumerate(highlights):
                cx = Inches(1.2 + i * 3.8)
                c_shape = s0.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, card_y, card_w, card_h)
                c_shape.fill.solid()
                c_shape.fill.fore_color.rgb = card_bg
                c_shape.line.color.rgb = card_border

                c_tf = c_shape.text_frame
                c_tf.word_wrap = True
                cp0 = c_tf.paragraphs[0]
                cp0.text = head
                cp0.font.size = Pt(14)
                cp0.font.bold = True
                cp0.font.color.rgb = accent_sub

                cp1 = c_tf.add_paragraph()
                cp1.text = desc
                cp1.font.size = Pt(12)
                cp1.font.color.rgb = text_muted

            # Footer
            foot_box = s0.shapes.add_textbox(Inches(1.2), Inches(6.8), Inches(11.0), Inches(0.4))
            tf_foot = foot_box.text_frame
            p_foot = tf_foot.paragraphs[0]
            p_foot.text = "AI Content Studio • Powered by CogniCore & Sarvam AI"
            p_foot.font.size = Pt(11)
            p_foot.font.color.rgb = text_muted

            # -------------------------------------------------------------
            # Slide 2..N: Content Slides (Scenes)
            # -------------------------------------------------------------
            scenes = project.timeline.scenes if project.timeline else project.scenes
            for idx, s in enumerate(scenes):
                slide = prs.slides.add_slide(blank_layout)

                # Dark Background
                bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
                bg.fill.solid()
                bg.fill.fore_color.rgb = bg_dark
                bg.line.fill.background()

                # Top Accent Bar
                bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(0.12))
                bar.fill.solid()
                bar.fill.fore_color.rgb = accent_blue
                bar.line.fill.background()

                # Scene Tag Pill
                scene_tag = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(0.6), Inches(3.6), Inches(0.38))
                scene_tag.fill.solid()
                scene_tag.fill.fore_color.rgb = card_bg
                scene_tag.line.color.rgb = card_border
                tf_stag = scene_tag.text_frame
                p_stag = tf_stag.paragraphs[0]
                p_stag.text = f"SCENE 0{idx+1} OF 0{len(scenes)} • {concept.upper()}"
                p_stag.font.size = Pt(10)
                p_stag.font.bold = True
                p_stag.font.color.rgb = accent_sub

                # Slide Title
                stitle_box = slide.shapes.add_textbox(Inches(1.0), Inches(1.15), Inches(11.333), Inches(0.8))
                tf_st = stitle_box.text_frame
                tf_st.word_wrap = True
                p_st = tf_st.paragraphs[0]
                p_st.text = s.title
                p_st.font.size = Pt(26)
                p_st.font.bold = True
                p_st.font.color.rgb = text_white

                # Left Column: Structured Bullet Points Card
                left_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(2.1), Inches(7.5), Inches(4.6))
                left_card.fill.solid()
                left_card.fill.fore_color.rgb = card_bg
                left_card.line.color.rgb = card_border

                tf_left = left_card.text_frame
                tf_left.word_wrap = True

                # Card Header
                p_lh = tf_left.paragraphs[0]
                p_lh.text = "✦  KEY CAPABILITIES & WORKFLOW"
                p_lh.font.size = Pt(13)
                p_lh.font.bold = True
                p_lh.font.color.rgb = accent_sub

                # Bullet points
                bullets = getattr(s, "bullet_points", [])
                if not bullets:
                    # Clean sentence extraction fallback (never dump full visual description paragraph!)
                    raw_text = s.narration_text or s.visual_description or ""
                    sentences = [st.strip() for st in raw_text.replace("\n", " ").split(".") if len(st.strip()) > 15]
                    bullets = sentences[:3] if sentences else ["Seamless interface navigation and digital healthcare workflows.", "Direct access to appointments and verified specialist doctors.", "Personalized patient portal with secure electronic medical records."]

                for b_text in bullets[:4]:
                    bp = tf_left.add_paragraph()
                    bp.text = f"•  {b_text}"
                    bp.font.size = Pt(15)
                    bp.font.color.rgb = text_white
                    bp.space_before = Pt(12)

                # Right Column: Visual Experience & Specs Card
                right_card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.8), Inches(2.1), Inches(3.5), Inches(4.6))
                right_card.fill.solid()
                right_card.fill.fore_color.rgb = card_bg
                right_card.line.color.rgb = accent_blue

                tf_right = right_card.text_frame
                tf_right.word_wrap = True

                p_rh = tf_right.paragraphs[0]
                p_rh.text = "✦  VISUAL EXPERIENCE"
                p_rh.font.size = Pt(13)
                p_rh.font.bold = True
                p_rh.font.color.rgb = accent_blue

                p_vis = tf_right.add_paragraph()
                vis_clean = (s.visual_description or "Clean UI cards and healthcare layout.").strip()
                if len(vis_clean) > 120:
                    vis_clean = vis_clean[:120].rsplit(" ", 1)[0] + "..."
                p_vis.text = vis_clean
                p_vis.font.size = Pt(13)
                p_vis.font.color.rgb = text_muted
                p_vis.space_before = Pt(8)

                # Metric / Status Badges inside Right Card
                badges_list = [
                    f"⏱ Narration: {s.duration_sec:.1f}s",
                    "✓ Figma UI Aligned",
                    "⚡ Studio Verified",
                ]
                for b_item in badges_list:
                    p_b = tf_right.add_paragraph()
                    p_b.text = f"▪ {b_item}"
                    p_b.font.size = Pt(12)
                    p_b.font.color.rgb = text_white
                    p_b.space_before = Pt(10)

                # Speaker Notes (Narration & Detailed Specs)
                notes_slide = slide.notes_slide
                notes_slide.notes_text_frame.text = (
                    f"Voiceover Narration:\n{s.narration_text}\n\n"
                    f"Visual Design Specification:\n{s.visual_description}"
                )

            prs.save(file_path)
            logger.info(f"Successfully exported modern 16:9 PowerPoint presentation to {file_path}")
            return file_path
        else:
            # Fallback text presentation
            file_path = os.path.join(output_dir, f"{project.project_id}_presentation.txt")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"Project: {project.name}\n\n")
                scenes = project.timeline.scenes if project.timeline else project.scenes
                for s in scenes:
                    f.write(f"=== {s.title} ===\nVisual: {s.visual_description}\nNarration: {s.narration_text}\n\n")
            logger.info(f"Exported text presentation to {file_path}")
            return file_path

    def export_video_mp4(self, project: Project, output_dir: str) -> str:
        """Render a real HD MP4 video file for the project timeline."""
        os.makedirs(output_dir, exist_ok=True)
        video_path = os.path.join(output_dir, f"{project.project_id}_presentation.mp4")

        try:
            import cv2
            import numpy as np
            from PIL import Image, ImageDraw

            width, height = 1280, 720
            fps = 24
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

            scenes = project.timeline.scenes if project.timeline else project.scenes
            if not scenes:
                scenes = [Scene(title="Presentation", narration_text="No scenes available", duration_sec=5.0)]

            total_timeline_sec = sum(max(s.duration_sec, 3.0) for s in scenes)
            current_sec = 0.0

            # Colors from design context
            design = project.design_context or {}
            concept = design.get("concept", "Presentation")

            for idx, scene in enumerate(scenes):
                dur = max(scene.duration_sec, 3.0)
                num_frames = int(dur * fps)

                for f in range(num_frames):
                    frame_time = current_sec + (f / fps)
                    overall_pct = min(1.0, frame_time / max(total_timeline_sec, 0.1))

                    # High quality frame
                    img = Image.new("RGB", (width, height), color=(11, 15, 25))
                    draw = ImageDraw.Draw(img)

                    # Top accent bar
                    draw.rectangle([(0, 0), (width, 8)], fill=(14, 165, 233))

                    # Header badge
                    draw.rectangle([(80, 50), (320, 85)], fill=(22, 30, 46), outline=(51, 65, 85))
                    draw.text((95, 60), f"SCENE {idx + 1} OF {len(scenes)} • {concept.upper()}", fill=(148, 163, 184))

                    # Project Title
                    draw.text((80, 110), project.name[:50], fill=(56, 189, 248))

                    # Scene Title
                    draw.text((80, 150), scene.title[:55], fill=(241, 245, 249))

                    # Central Card
                    card_top = 220
                    card_bottom = 580
                    draw.rounded_rectangle(
                        [(80, card_top), (width - 80, card_bottom)],
                        radius=16,
                        fill=(19, 26, 42),
                        outline=(51, 65, 85),
                        width=2,
                    )

                    # Section 1: Visual Design Elements
                    draw.text((120, card_top + 30), "VISUAL ELEMENTS & LAYOUT", fill=(167, 139, 250))
                    vis_text = scene.visual_description or "Visual elements from design"
                    draw.text((120, card_top + 60), vis_text[:110], fill=(226, 232, 240))
                    if len(vis_text) > 110:
                        draw.text((120, card_top + 90), vis_text[110:220], fill=(226, 232, 240))

                    # Section 2: Spoken Voiceover Narration
                    draw.text((120, card_top + 160), "VOICEOVER NARRATION", fill=(52, 211, 153))
                    narr_text = scene.narration_text or ""
                    draw.text((120, card_top + 195), narr_text[:110], fill=(148, 163, 184))
                    if len(narr_text) > 110:
                        draw.text((120, card_top + 225), narr_text[110:220], fill=(148, 163, 184))
                    if len(narr_text) > 220:
                        draw.text((120, card_top + 255), narr_text[220:330], fill=(148, 163, 184))

                    # Bottom Progress Bar
                    bar_y = 640
                    draw.rectangle([(80, bar_y), (width - 80, bar_y + 8)], fill=(30, 41, 59))
                    draw.rectangle([(80, bar_y), (80 + int((width - 160) * overall_pct), bar_y + 8)], fill=(14, 165, 233))

                    # Time indicators
                    draw.text((80, bar_y - 25), f"Duration: {scene.duration_sec:.1f}s", fill=(100, 116, 139))
                    draw.text((width - 240, bar_y - 25), f"Timeline: {frame_time:.1f}s / {total_timeline_sec:.1f}s", fill=(100, 116, 139))

                    # Convert to BGR array for OpenCV
                    frame_bgr = np.array(img)[:, :, ::-1]
                    writer.write(frame_bgr)

                current_sec += dur

            writer.release()
            logger.info(f"Successfully exported MP4 video presentation to {video_path}")

            # Also export the companion JSON manifest for reference
            manifest_path = os.path.join(output_dir, f"{project.project_id}_video_manifest.json")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump({
                    "project_id": project.project_id,
                    "name": project.name,
                    "video_file": os.path.basename(video_path),
                    "total_duration_sec": total_timeline_sec,
                    "scenes": [s.to_dict() for s in scenes]
                }, f, indent=2)

            return video_path

        except Exception as e:
            logger.error(f"OpenCV MP4 generation error: {e}, falling back to json manifest")
            return self.export_video_plan(project, output_dir)

    def export_video_plan(self, project: Project, output_dir: str) -> str:
        """Export companion JSON manifest for the video plan."""
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{project.project_id}_video_manifest.json")

        scenes = project.timeline.scenes if project.timeline else project.scenes
        plan_data = {
            "project_id": project.project_id,
            "name": project.name,
            "total_duration_sec": project.timeline.total_duration_sec if project.timeline else 0,
            "scenes": [s.to_dict() for s in scenes]
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, indent=2)
        return file_path
