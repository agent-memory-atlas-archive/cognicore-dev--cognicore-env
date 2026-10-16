"""
NEXUS triggers: the task queue and the integrations that feed it.

  - GitHub Issues: auto-fix labeled issues, open PRs   (github_issues)
  - CI Fixer:      auto-repair failed GitHub Actions   (ci_fixer)
  - Slack:         @nexus mention triggers             (slack)
  - Linear:        ticket assignment triggers          (linear)
  - Scheduler:     cron-based recurring tasks          (scheduler)
  - PR Reviewer:   memory-backed code review           (pr_reviewer)
  - Webhooks:      one server for all of the above     (webhook_server)

Usage:
  cognicore integrations setup    # Interactive setup
  cognicore integrations test     # Test connections
  cognicore integrations status   # Health check
  cognicore webhooks start        # Start webhook server
"""
