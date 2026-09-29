import logging
from dataclasses import dataclass
from typing import List, Optional

from cognicore.experience.schema import (
    StructuredExperience,
    EnvironmentContext,
    RepositoryContext,
)
from cognicore.experience.compatibility import EnvironmentChecker, CompatibilityResult
from cognicore.memory.base import MemoryBackend, SearchResult

logger = logging.getLogger('cognicore.experience')

@dataclass
class RetrievalResult:
    """Result of an experience retrieval operation."""
    experiences: List[StructuredExperience]
    failures: List[StructuredExperience]
    compatibility_results: List[CompatibilityResult]
    total_candidates: int
    filtered_out: int


class ExperienceRetriever:
    """Retrieves and filters structured experiences from memory."""

    def __init__(self, checker: Optional[EnvironmentChecker] = None) -> None:
        """Initialize the retriever with an optional environment checker.
        
        Args:
            checker: Optional EnvironmentChecker instance. If None, a default one is created.
        """
        self.checker = checker if checker is not None else EnvironmentChecker()

    def _status_priority(self, status: str) -> int:
        """Get the priority score for a verification status.
        
        Args:
            status: The verification status string.
            
        Returns:
            An integer priority score. Higher is better.
        """
        priorities = {
            'transferable': 5,
            'promoted': 4,
            'verified': 3,
            'observed': 2,
            'candidate': 1
        }
        return priorities.get(status, 0)

    def retrieve(
        self,
        query: str,
        backend: MemoryBackend,
        current_env: Optional[EnvironmentContext] = None,
        current_repo: Optional[RepositoryContext] = None,
        include_failures: bool = True,
        require_verified: bool = True,
        top_k: int = 5
    ) -> RetrievalResult:
        """Retrieve relevant and compatible experiences for a query.
        
        Args:
            query: The search query string.
            backend: The MemoryBackend to search against.
            current_env: Optional current environment context to filter for compatibility.
            current_repo: Optional current repository context to filter for compatibility.
            include_failures: Whether to include failure experiences in the result.
            require_verified: Whether to require experiences to be verified, promoted, or transferable.
            top_k: The maximum number of successful experiences to return.
            
        Returns:
            A RetrievalResult containing experiences, failures, and metadata.
        """
        search_results: List[SearchResult] = backend.search(query, top_k=top_k * 4)
        total_candidates = len(search_results)
        
        experiences: List[StructuredExperience] = []
        failures: List[StructuredExperience] = []
        compatibility_results: List[CompatibilityResult] = []
        
        for result in search_results:
            entry = result.entry
            
            if entry.memory_type not in ('experience', 'failure'):
                continue
                
            if entry.state in ('archived', 'deleted'):
                continue
                
            if getattr(entry, 'invalidated_by', None):
                continue
                
            try:
                experience = StructuredExperience.from_memory_entry(entry)
            except Exception as e:
                logger.debug(f"Failed to deserialize experience from entry {entry.entry_id}: {e}")
                continue
            
            is_compatible = True
            comp_result = None
            
            if current_env:
                env_comp = self.checker.check(experience.environment, current_env)
                if not env_comp.compatible:
                    is_compatible = False
                comp_result = env_comp
            
            if is_compatible and current_repo:
                repo_comp = self.checker.check_repository(experience.repository, current_repo)
                if not repo_comp.compatible:
                    is_compatible = False
                elif comp_result is None:
                    comp_result = repo_comp
            
            if not is_compatible:
                continue
                
            if entry.memory_type == 'experience':
                if require_verified and experience.verification_status not in ('verified', 'promoted', 'transferable'):
                    continue
                experiences.append(experience)
                if comp_result:
                    compatibility_results.append(comp_result)
            elif entry.memory_type == 'failure':
                failures.append(experience)
                
        if not include_failures:
            failures.clear()
            
        experiences.sort(
            key=lambda x: (
                self._status_priority(x.verification_status),
                x.confidence,
                x.created_at
            ),
            reverse=True
        )
        
        experiences = experiences[:top_k]
        filtered_out = total_candidates - (len(experiences) + len(failures))
        
        return RetrievalResult(
            experiences=experiences,
            failures=failures,
            compatibility_results=compatibility_results,
            total_candidates=total_candidates,
            filtered_out=filtered_out
        )
