import logging
import re
from typing import List, Dict, Any

from content_studio.memory.cognicore_layer import CogniCoreLayer

logger = logging.getLogger(__name__)

class ConversationCompressor:
    """
    Compresses conversation history to save tokens.
    """
    
    def estimate_tokens(self, text: str) -> int:
        """
        Returns a rough token count estimate.
        """
        return int(len(text.split()) * 1.3)
        
    def compress(self, conversation: List[dict]) -> Dict[str, Any]:
        """
        Compresses conversation turns into a denser format.
        Strips filler words, abbreviates roles, and removes redundancy.
        """
        role_map = {
            "user": "U",
            "agent": "A",
            "system": "S"
        }
        
        filler_words = ["please", "could you", "I would like", "can you", "thank you", "thanks", "sure", "ok", "okay"]
        
        original_text = ""
        compressed_lines = []
        
        for turn in conversation:
            role = turn.get("role", "unknown").lower()
            content = turn.get("content", "")
            
            original_text += f"{role}: {content}\n"
            
            # Abbreviate role
            abbr_role = role_map.get(role, role[0].upper())
            
            # Remove filler words (simple case-insensitive replacement)
            compressed_content = content
            for filler in filler_words:
                compressed_content = re.sub(r'\b' + filler + r'\b', '', compressed_content, flags=re.IGNORECASE)
                
            # Normalize whitespace
            compressed_content = " ".join(compressed_content.split())
            
            compressed_lines.append(f"{abbr_role}:{compressed_content}")
            
        compressed_text = "\n".join(compressed_lines)
        original_tokens = self.estimate_tokens(original_text)
        compressed_tokens = self.estimate_tokens(compressed_text)
        reduction_pct = 0
        if original_tokens > 0:
            reduction_pct = ((original_tokens - compressed_tokens) / original_tokens) * 100
            
        return {
            "compressed_text": compressed_text,
            "original_tokens": original_tokens,
            "compressed_tokens": compressed_tokens,
            "reduction_pct": round(reduction_pct, 2)
        }
        
    def store_compressed(self, project_id: str, compressed: dict, cognicore_layer: CogniCoreLayer) -> None:
        """
        Stores the compressed conversation via CogniCoreLayer.
        """
        cognicore_layer.store_workflow_event(
            project_id=project_id,
            step_name="conversation_compression",
            status="completed",
            data=compressed
        )
        logger.info(f"Stored compressed conversation for project {project_id}, reduction: {compressed['reduction_pct']}%")
