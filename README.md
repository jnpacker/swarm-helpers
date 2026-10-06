# swarm-helpers

Public runtime library for prompts and agents that cannot access the private
source repositories or install their full skill collections. Files are
mirrored from their documented upstream sources by a private maintenance
repository's manifest and sync script.

Use the raw links below to fetch a skill, tool, or companion asset at runtime.
The repository paths are stable and preserve each skill's companion-file
layout.

## Skills and companion files

### Jira issue specialists

| Skill / asset | Purpose |
|---|---|
| [`skills/bug-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/bug-specialist/SKILL.md) | Bug analysis, reproduction, and remediation planning |
| [`skills/bug-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/bug-specialist/template.md) | Bug description structure |
| [`skills/epic-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/epic-specialist/SKILL.md) | Multi-sprint epic planning |
| [`skills/epic-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/epic-specialist/template.md) | Epic description structure |
| [`skills/feature-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/feature-specialist/SKILL.md) | Customer-facing feature strategy |
| [`skills/feature-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/feature-specialist/template.md) | Feature description structure |
| [`skills/initiative-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/initiative-specialist/SKILL.md) | Internal capability and process improvements |
| [`skills/initiative-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/initiative-specialist/template.md) | Initiative description structure |
| [`skills/jira-create/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/jira-create/SKILL.md) | Interactive Jira issue creation, duplicate review, and quality grading |
| [`skills/outcome-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/outcome-specialist/SKILL.md) | Strategic outcomes and measurable results |
| [`skills/outcome-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/outcome-specialist/template.md) | Outcome description structure |
| [`skills/outcome-specialist/strategic-goal-template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/outcome-specialist/strategic-goal-template.md) | Strategic Goal description structure |
| [`skills/spike-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/spike-specialist/SKILL.md) | Research and time-boxed technical investigation |
| [`skills/spike-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/spike-specialist/template.md) | Spike description structure |
| [`skills/story-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/story-specialist/SKILL.md) | User stories and acceptance criteria |
| [`skills/story-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/story-specialist/template.md) | Story description structure |
| [`skills/task-specialist/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/task-specialist/SKILL.md) | Internal task breakdown and implementation planning |
| [`skills/task-specialist/template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/task-specialist/template.md) | Task description structure |
| [`skills/task-specialist/subtask-template.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/task-specialist/subtask-template.md) | Sub-task description structure |

### Development workflow and PR tools

| Skill / asset | Purpose |
|---|---|
| [`skills/start-work/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/start-work/SKILL.md) | Start Jira-backed implementation work |
| [`skills/finish-work/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/finish-work/SKILL.md) | Finish implementation, prepare commits and PRs, update Jira |
| [`skills/pr-fix/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/pr-fix/SKILL.md) | Resolve PR review feedback, CI failures, and merge conflicts |
| [`skills/pr-hygiene/SKILL.md`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/pr-hygiene/SKILL.md) | Audit PR age, review state, and staleness |
| [`skills/pr-hygiene/scripts/pr-hygiene.py`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/pr-hygiene/scripts/pr-hygiene.py) | PR hygiene scanner used by the skill |
| [`skills/pr-review/scripts/summarize-pr.py`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/pr-review/scripts/summarize-pr.py) | Collect and summarize PR context for review |
| [`skills/pr-review/scripts/prepare-worktree.py`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/skills/pr-review/scripts/prepare-worktree.py) | Prepare an isolated worktree for PR review |
| [`scripts/gh-commit.py`](https://raw.githubusercontent.com/jnpacker/swarm-helpers/main/scripts/gh-commit.py) | Create a verified GitHub commit and open a PR |

## Dependency and maintenance notes

- Skill companions are grouped with their entrypoint above and retain the
  source-relative path. If a skill refers to `template.md` or a `scripts/`
  file, fetch that exact sibling path from this repository.
- `jira-create` links to the specialist skills and templates in this catalog;
  load those public helper URLs when the local agent environment does not have
  the skills installed.
- The PR review and hygiene scripts declare their Python dependencies inline;
  see each script's header for the runtime requirements.
- `scripts/gh-commit.py` uses the GitHub API and its declared inline Python
  dependencies; provide the credentials and repository context required by
  the consuming prompt.
- The upstream source, destination path, and mirror status for each file are
  indexed in `scripts/swarm-helpers-manifest.txt` in the private maintenance
  repository.
