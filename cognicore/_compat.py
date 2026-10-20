"""
Old module paths, kept working after the repository restructure.

Modules moved into subpackages (e.g. ``cognicore.advanced_memory`` is now
``cognicore.memory.semantic``). Every old path still imports, and resolves to
the *same module object* as the new path, so ``isinstance`` checks,
``mock.patch("old.path.X")``, pickles, ``uvicorn old.path:app`` and
``python -m old.path`` all keep working.

New code should use the new paths. The old ones will be removed in a future
major release.
"""

import importlib
import importlib.abc
import importlib.util
import sys

# old module path -> new module path
MOVED_MODULES = {
    # Memory
    "cognicore.advanced_memory": "cognicore.memory.semantic",
    "cognicore.memory_manager": "cognicore.memory.manager",
    "cognicore.multi_memory": "cognicore.memory.multi_tier",
    # Agents
    "cognicore.smart_agents": "cognicore.agents.smart",
    "cognicore.agent_builder": "cognicore.agents.builder",
    "cognicore.persistence": "cognicore.agents.persistence",
    "cognicore.lifelong": "cognicore.agents.lifelong",
    "cognicore.knowledge_transfer": "cognicore.agents.knowledge_transfer",
    "cognicore.fingerprint": "cognicore.agents.fingerprint",
    "cognicore.strategy": "cognicore.agents.strategy",
    "cognicore.swarm": "cognicore.agents.swarm",
    # Safety
    "cognicore.safety_layer": "cognicore.safety.layer",
    "cognicore.adversarial": "cognicore.safety.adversarial",
    "cognicore.red_blue": "cognicore.safety.red_blue",
    # Evaluation
    "cognicore.benchmark": "cognicore.evaluation.benchmark",
    "cognicore.leaderboard": "cognicore.evaluation.leaderboard",
    "cognicore.analytics": "cognicore.evaluation.analytics",
    "cognicore.report": "cognicore.evaluation.report",
    "cognicore.experiment": "cognicore.evaluation.experiment",
    "cognicore.intelligence": "cognicore.evaluation.intelligence",
    "cognicore.difficulty": "cognicore.evaluation.difficulty",
    "cognicore.augmentation": "cognicore.evaluation.augmentation",
    # Training
    "cognicore.curriculum": "cognicore.training.curriculum",
    "cognicore.evolution": "cognicore.training.evolution",
    "cognicore.auto_improve": "cognicore.training.auto_improve",
    "cognicore.meta_rewards": "cognicore.training.meta_rewards",
    "cognicore.finetuning": "cognicore.training.finetuning",
    "cognicore.prompt_optimizer": "cognicore.training.prompt_optimizer",
    # Observability
    "cognicore.debugger": "cognicore.observability.debugger",
    "cognicore.explainer": "cognicore.observability.explainer",
    "cognicore.thought_trace": "cognicore.observability.thought_trace",
    "cognicore.predictive": "cognicore.observability.predictive",
    "cognicore.causal": "cognicore.observability.causal",
    "cognicore.cost_tracker": "cognicore.observability.cost_tracker",
    "cognicore.webhooks": "cognicore.observability.webhooks",
    # Environments, UI, utilities
    "cognicore.compose": "cognicore.envs.compose",
    "cognicore.multi_agent": "cognicore.envs.multi_agent_base",
    "cognicore.dashboard": "cognicore.ui.dashboard",
    "cognicore.studio": "cognicore.ui.studio",
    "cognicore.cache": "cognicore.utils.cache",
    "cognicore.rate_limiter": "cognicore.utils.rate_limiter",
    "cognicore.profiles": "cognicore.core.profiles",
    # Experimental systems
    "cognicore.dream": "cognicore.experimental.dream",
    "cognicore.oracle": "cognicore.experimental.oracle",
    "cognicore.timetravel": "cognicore.experimental.timetravel",
    "cognicore.civilization": "cognicore.experimental.civilization",
    "cognicore.conscience": "cognicore.experimental.conscience",
    "cognicore.dna": "cognicore.experimental.dna",
    # Hosted MCP connectors (Claude, ChatGPT)
    "cognicore.extension.remote": "cognicore.connectors.remote",
    "cognicore.extension.oauth": "cognicore.connectors.oauth",
    "cognicore.integrations.chatgpt": "cognicore.connectors.chatgpt",
    "cognicore.integrations.auth": "cognicore.connectors.supabase_auth",
    "cognicore.integrations.elevenlabs": "cognicore.fabric.plugins.elevenlabs",
    # NEXUS triggers
    "cognicore.integrations.task_queue": "cognicore.nexus.triggers.task_queue",
    "cognicore.integrations.slack": "cognicore.nexus.triggers.slack",
    "cognicore.integrations.github_issues": "cognicore.nexus.triggers.github_issues",
    "cognicore.integrations.linear": "cognicore.nexus.triggers.linear",
    "cognicore.integrations.ci_fixer": "cognicore.nexus.triggers.ci_fixer",
    "cognicore.integrations.pr_reviewer": "cognicore.nexus.triggers.pr_reviewer",
    "cognicore.integrations.webhook_server": "cognicore.nexus.triggers.webhook_server",
    "cognicore.integrations.scheduler": "cognicore.nexus.triggers.scheduler",
    "cognicore.integrations.setup_wizard": "cognicore.nexus.triggers.setup_wizard",
}

# Folders and files moved outside the package (old path -> new path). These are
# scripts and docs, not importable modules, so they have no alias; listed here
# so tools (scripts/checks/restructure_guard.py) and people can trace them.
MOVED_PATHS = {
    "cognicore_benchmarks": "benchmarks",
    "cognicore_bench": "benchmarks/agent_learning",
    "scratch": "benchmarks/longmemeval/analysis",
    "demos": "examples",
    "PROGRESS.md": "docs/internal/PROGRESS.md",
    "docs/claude-extension-audit.md": "docs/internal/claude-extension-audit.md",
    "docs/mcp_validation_plan.md": "docs/internal/mcp_validation_plan.md",
    "docs/chatgpt-app": "docs/internal/chatgpt-app",
}


class _AliasLoader(importlib.abc.Loader):
    """Loads an old module path by returning the module at its new path."""

    def __init__(self, new_name):
        self.new_name = new_name
        self._real_spec = None

    def create_module(self, spec):
        module = importlib.import_module(self.new_name)
        self._real_spec = module.__spec__
        return module

    def exec_module(self, module):
        # The import system set __spec__ to the alias spec; put the real one back.
        if self._real_spec is not None:
            module.__spec__ = self._real_spec

    # Let ``python -m old.path`` run the new module's code.
    def get_code(self, fullname):
        spec = importlib.util.find_spec(self.new_name)
        return spec.loader.get_code(self.new_name)

    def is_package(self, fullname):
        spec = importlib.util.find_spec(self.new_name)
        return spec.submodule_search_locations is not None


class _AliasFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        new_name = MOVED_MODULES.get(fullname)
        if new_name is None:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(new_name))


def install():
    """Make old module paths importable. Runs when this module is imported."""
    if not any(isinstance(f, _AliasFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _AliasFinder())


def alias_loaded():
    """Register old paths for modules that are already imported.

    ``import cognicore`` used to import the top-level modules directly, which
    made e.g. ``cognicore.advanced_memory`` available as an attribute right
    away. Keep that true for modules ``cognicore/__init__.py`` now imports from
    their new paths. Existing attributes are never replaced:
    ``cognicore.auto_improve`` is the function, not the module.
    """
    for old, new in MOVED_MODULES.items():
        module = sys.modules.get(new)
        parent_name, _, child = old.rpartition(".")
        parent = sys.modules.get(parent_name)
        # Without its parent loaded, leave the old path to the finder, which
        # also sets the parent attribute when the old path is imported.
        if module is None or parent is None:
            continue
        sys.modules.setdefault(old, module)
        if not hasattr(parent, child):
            setattr(parent, child, module)


install()
