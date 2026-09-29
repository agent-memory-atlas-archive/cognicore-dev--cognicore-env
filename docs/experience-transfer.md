# Experience Transfer

**Agents don't share conversations. They share experience.**

CogniCore introduces a multi-agent lifecycle for memory:
1. **Candidate**: An agent tries an approach.
2. **Observed**: The agent asserts if it worked or failed.
3. **Verified**: CogniCore requires independent validation (e.g. running `pytest`).
4. **Promoted**: The memory is sealed as a verified experience.
5. **Transferable**: Available for other agents to query.

### Failures are First-Class Citizens
If an approach fails, the failure and reason are recorded. When another agent attempts a similar task, they receive the failure warning, effectively preventing them from making the same mistake.

See `demos/experience_transfer/` for executable code demonstrations.
