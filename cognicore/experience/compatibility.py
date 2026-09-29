"""
Graduated compatibility model for experiences.

Provides EnvironmentChecker to evaluate the applicability of an experience
from a source environment/repository to a target environment/repository.
It differentiates between hard blockers (e.g., Python 2 vs Python 3) and
minor warnings (e.g., minor version bumps).
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Tuple

from cognicore.experience.schema import EnvironmentContext, RepositoryContext

logger = logging.getLogger('cognicore.experience')

def _parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse 'X.Y.Z' or 'X.Y' or 'X' into (major, minor, patch) tuple.
    
    Handles malformed strings gracefully by returning (0, 0, 0).
    """
    if not version_str:
        return (0, 0, 0)
    
    match = re.search(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', str(version_str))
    if not match:
        return (0, 0, 0)
        
    major = int(match.group(1)) if match.group(1) else 0
    minor = int(match.group(2)) if match.group(2) else 0
    patch = int(match.group(3)) if match.group(3) else 0
    return (major, minor, patch)


@dataclass
class CompatibilityResult:
    """Result of a compatibility check.
    
    Graduated compatibility model:
    - hard blocker: precludes transferring the experience completely.
    - warning: minor mismatch that might require adaptation.
    """
    compatible: bool
    score: float
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confidence_modifier: float = 1.0


class EnvironmentChecker:
    """Evaluates environment and repository compatibility for experiences."""
    
    def check(self, source_env: EnvironmentContext, target_env: EnvironmentContext) -> CompatibilityResult:
        """Check compatibility between two environments."""
        score = 1.0
        blockers: List[str] = []
        warnings: List[str] = []
        
        # Check python_version
        if source_env.python_version and target_env.python_version:
            s_major, s_minor, _ = _parse_version(source_env.python_version)
            t_major, t_minor, _ = _parse_version(target_env.python_version)
            
            if s_major != t_major:
                blockers.append(f"Python major version mismatch: {s_major} vs {t_major}")
                score -= 0.5
            else:
                diff = abs(s_minor - t_minor)
                if diff > 2:
                    warnings.append(f"Python minor version mismatch > 2: {s_minor} vs {t_minor}")
                    score -= 0.1
                elif diff >= 1:
                    warnings.append(f"Python minor version mismatch: {s_minor} vs {t_minor}")
                    score -= 0.05
                    
        # Check framework
        if source_env.framework and target_env.framework:
            if source_env.framework.lower() != target_env.framework.lower():
                blockers.append(f"Framework mismatch: {source_env.framework} vs {target_env.framework}")
                score -= 0.4
            else:
                if source_env.framework_version and target_env.framework_version:
                    s_fmajor, s_fminor, _ = _parse_version(source_env.framework_version)
                    t_fmajor, t_fminor, _ = _parse_version(target_env.framework_version)
                    
                    if s_fmajor != t_fmajor:
                        blockers.append(f"Framework major version mismatch: {s_fmajor} vs {t_fmajor}")
                        score -= 0.3
                    elif s_fminor != t_fminor:
                        warnings.append(f"Framework minor version mismatch: {s_fminor} vs {t_fminor}")
                        score -= 0.05
                        
        # Check dependencies
        for dep, s_ver in source_env.dependencies.items():
            if dep in target_env.dependencies:
                t_ver = target_env.dependencies[dep]
                s_dmajor, s_dminor, _ = _parse_version(s_ver)
                t_dmajor, t_dminor, _ = _parse_version(t_ver)
                
                if s_dmajor != t_dmajor:
                    blockers.append(f"Dependency major mismatch for {dep}: {s_ver} vs {t_ver}")
                    score -= 0.2
                elif s_dminor != t_dminor:
                    warnings.append(f"Dependency minor mismatch for {dep}: {s_ver} vs {t_ver}")
                    score -= 0.02
            else:
                warnings.append(f"Dependency {dep} in source but missing in target")
                
        # Check os
        if source_env.os and target_env.os and source_env.os.lower() != target_env.os.lower():
            warnings.append(f"OS mismatch: {source_env.os} vs {target_env.os}")
            score -= 0.05
            
        score = max(0.0, min(1.0, score))
        compatible = len(blockers) == 0
        confidence_modifier = max(0.1, score)
        
        return CompatibilityResult(
            compatible=compatible,
            score=score,
            blockers=blockers,
            warnings=warnings,
            confidence_modifier=confidence_modifier
        )

    def check_repository(self, source_repo: RepositoryContext, target_repo: RepositoryContext) -> CompatibilityResult:
        """Check compatibility between two repository contexts."""
        score = 1.0
        blockers: List[str] = []
        warnings: List[str] = []
        
        if source_repo.repo_id and target_repo.repo_id and source_repo.repo_id != target_repo.repo_id:
            blockers.append("Different repository")
            score -= 0.8
            
        if source_repo.repo_id == target_repo.repo_id and source_repo.commit and target_repo.commit and source_repo.commit != target_repo.commit:
            warnings.append("Different commit in same repository")
            score -= 0.1
            
        s_files = set(source_repo.affected_files)
        t_files = set(target_repo.affected_files)
        if s_files and t_files and s_files.intersection(t_files):
            score += 0.2
            
        score = max(0.0, min(1.0, score))
        compatible = len(blockers) == 0
        confidence_modifier = max(0.1, score)
        
        return CompatibilityResult(
            compatible=compatible,
            score=score,
            blockers=blockers,
            warnings=warnings,
            confidence_modifier=confidence_modifier
        )
        
    def full_check(self, source_env: EnvironmentContext, target_env: EnvironmentContext, source_repo: RepositoryContext, target_repo: RepositoryContext) -> CompatibilityResult:
        """Perform a full compatibility check combining environment and repository contexts."""
        env_res = self.check(source_env, target_env)
        repo_res = self.check_repository(source_repo, target_repo)
        
        blockers = env_res.blockers + repo_res.blockers
        warnings = env_res.warnings + repo_res.warnings
        score = env_res.score * repo_res.score
        
        score = max(0.0, min(1.0, score))
        compatible = len(blockers) == 0
        confidence_modifier = max(0.1, score)
        
        return CompatibilityResult(
            compatible=compatible,
            score=score,
            blockers=blockers,
            warnings=warnings,
            confidence_modifier=confidence_modifier
        )
