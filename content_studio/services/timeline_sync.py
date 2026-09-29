import logging
from typing import List

from content_studio.models import Scene, Timeline

logger = logging.getLogger(__name__)

class TimelineSync:
    """
    Synchronizes scene durations, particularly updating them based on actual audio durations.
    """

    def synchronize(self, scenes: List[Scene]) -> Timeline:
        """
        Synchronize timeline across scenes.
        
        If a scene has `audio_duration_sec`, its `duration_sec` is updated to match.
        Computes the total duration and determines the sync status.
        
        Args:
            scenes: List of Scene objects to synchronize.
            
        Returns:
            Timeline object representing the synchronized timeline.
        """
        logger.info(f"Synchronizing timeline for {len(scenes)} scenes")
        
        total_duration = 0.0
        scenes_with_audio = 0
        
        for scene in scenes:
            if scene.audio_duration_sec is not None and scene.audio_duration_sec > 0:
                old_duration = scene.duration_sec
                scene.duration_sec = scene.audio_duration_sec
                logger.debug(f"Scene {scene.scene_id} duration updated: {old_duration}s -> {scene.duration_sec}s")
                scenes_with_audio += 1
            else:
                logger.debug(f"Scene {scene.scene_id} using estimated duration: {scene.duration_sec}s")
                
            total_duration += scene.duration_sec
            
        if scenes_with_audio == len(scenes) and len(scenes) > 0:
            sync_status = "synced"
        elif scenes_with_audio > 0:
            sync_status = "partial"
        else:
            sync_status = "unsynced"
            
        logger.info(f"Timeline sync complete. Total duration: {total_duration}s, Status: {sync_status}")
        
        return Timeline(
            scenes=scenes,
            total_duration_sec=total_duration,
            sync_status=sync_status
        )
