---
name: jira-create
description: Create a new Jira issue interactively — duplicate detection, specialist-drafted content, activity type interview, quality grading gate, and field confirmation before creation.
---

# Jira Create

Create a new Jira issue interactively. Includes duplicate detection, structured field collection, and a quality grading gate before creation.

## Instructions

Follow these steps in order. Use `AskUserQuestion` for each step. Do NOT skip steps or guess values.

### Step 1: Issue Type

Use `AskUserQuestion` to ask the user what type of issue to create:

- **Story** — User-facing functionality with acceptance criteria
- **Bug** — Defect report with reproduction steps
- **Task** — Internal technical work, non-user-facing
- **Spike** — Research, investigation, or proof-of-concept
- **Feature** — Significant customer-facing capability
- **Epic** — Large body of work spanning multiple sprints
- **Initiative** — Internal capability or architectural improvement; typically ~6 months, or no larger than a single Quarter/Release
- **Outcome** — Strategic business result tied to corporate objectives
- **Sub-task** — Child task under an existing issue

### Step 2: Duplicate Search

Before collecting any other fields, search for similar open issues using JQL. Read the project key from personal config (tool-aware fallback chain — see `AGENTS.md`).

Run: `issuetype = [selected type] AND project = [PROJECT] AND summary ~ "[keywords from user's intent]" AND status != Closed ORDER BY updated DESC`

If similar issues are found, present them to the user and ask whether to proceed with a new issue or use an existing one. If no duplicates are found, continue.

### Step 3: Delegate to Specialist Agent

Based on the issue type selected, launch the appropriate specialist agent to help craft the content. The agent should help formulate the summary, description, and any type-specific fields.

| Issue Type | Agent | Template to reference |
|------------|-------|-----------------------|
| Story | `story-specialist` | `skills/story-specialist/template.md` |
| Bug | `bug-specialist` | `skills/bug-specialist/template.md` |
| Task | `task-specialist` | `skills/task-specialist/template.md` |
| Spike | `spike-specialist` | `skills/spike-specialist/template.md` |
| Feature | `feature-specialist` | `skills/feature-specialist/template.md` |
| Epic | `epic-specialist` | `skills/epic-specialist/template.md` |
| Initiative | `initiative-specialist` | `skills/initiative-specialist/template.md` |
| Outcome | `outcome-specialist` | `skills/outcome-specialist/template.md` |
| Sub-task | `task-specialist` | `skills/task-specialist/subtask-template.md` |

The agent should return a proposed **summary** and **description**. Present them to the user for approval or editing via `AskUserQuestion`.

### Step 3b: Type-Appropriateness Check

For **Outcome, Feature, and Initiative** issue types only, evaluate the drafted summary and description against the signal table below. Now that there is actual content to assess, ask 1–2 targeted clarifying questions if any signals are present.

| Selected Type | Key clarifying question |
|---|---|
| **Outcome** | "Does this describe a measurable change in human behavior or business result that would warrant a press-release-level announcement — or is it primarily a product capability or internal improvement?" |
| **Feature** | "Is the primary beneficiary an external customer (not a Red Hat associate), and is there a clear customer value statement beyond grouping Epics?" |
| **Initiative** | "Is the result primarily an internal capability improvement for Red Hat associates (not a customer-facing product feature), within a ~6 month timeframe, or no larger than a single Quarter/Release?" |

If the drafted content raises a type mismatch signal, recommend the more appropriate type and ask whether to switch. If switching, return to Step 3 with the correct type. If the type is confirmed correct (intentional scope), note it and proceed.

For all other types (Story, Bug, Task, Spike, Epic, Sub-task), skip this step.

### Step 4: Structured Field Interview

Use `AskUserQuestion` to collect all remaining required fields in **one pass** — group logically (up to 4 questions per call).

**Before collecting any fields, ask whether this issue has a parent** (e.g., an Epic for a Story, an Initiative for an Epic, a parent Task for a Sub-task). Asking early lets you inherit Activity Type from the parent rather than asking the user to re-enter it.

If a parent key is provided:
1. Fetch the parent issue using the Jira MCP tool.
2. Read its `customfield_10464` value (Activity Type).
3. If the parent has an Activity Type set, automatically inherit it — do not ask the user to select one. Inform them: _"Activity Type copied from parent [KEY]: [value]."_ Give them the option to override.
4. If the parent has no Activity Type set, fall through to the normal Activity Type selection below.

If no parent is provided, proceed with the normal Activity Type selection.

**Priority** (default: Normal):
- Blocker
- Critical
- Major
- Normal (Recommended)
- Minor
- Trivial

**Activity Type** (required — must always be set; never leave unset or skip) — If inherited from the parent (see above), confirm the inherited value with the user and allow override. Otherwise, present all options with a brief recommendation based on the issue type and description, using the decision tree below.

Jira field key: `customfield_10464`. Set via MCP as `"customfield_10464": {"id": "<option_id>"}`.

| Activity Type | Option ID | Best for |
|---------------|-----------|----------|
| Associate Wellness & Development | 10604 | Onboarding, training, team health |
| BU Features | 10605 | Business unit feature commitments |
| Future Sustainability | 10606 | Tooling, architecture, upstream |
| Incidents & Support | 10607 | Escalations, customer support |
| Quality / Stability / Reliability | 10608 | Bugs, tech debt, toil reduction |
| Security & Compliance | 10609 | CVEs, vulnerabilities, compliance |
| Product / Portfolio Work | 10610 | Features, outcomes, strategic work |

**Decision tree** (ask in order, use the first match):
1. Is this about people? (onboarding, training, team health) → **Associate Wellness & Development**
2. Is this a customer escalation or support case? → **Incidents & Support**
3. Is this a CVE, vulnerability, or compliance requirement? → **Security & Compliance**
4. Is this a bug, tech debt, SLO, chore, or toil reduction? → **Quality / Stability / Reliability**
5. Is this improving tooling, architecture, upstream, or team processes? → **Future Sustainability**
6. Is this delivering a feature, outcome, or strategic initiative? → **Product / Portfolio Work**
7. None of the above or unclear? → ask the user directly rather than guessing

**Original Estimate** (e.g., '2h', '1d', '30m')

**Story Points** (default: 1) — MUST always be prompted for via `AskUserQuestion`. If the user does not provide a value, use 1.

### Step 5: Collect Categorization Fields

Use `AskUserQuestion` to collect:

**Component** — Ask the user for relevant components. If unsure what components are available, fetch them from the Jira project. Suggest based on keywords in the summary/description.

**Labels** — Ask if they want to add any labels (free text, comma-separated).

**Target Version** — Ask for the target version (fetch available versions using the registered Jira MCP tools if needed). Use `customfield_10855` for target version (NOT fix version for new/in-progress issues).

### Step 6: Parent / Linking

If a parent was already provided in Step 4, use that key here — do not ask again. Otherwise, use `AskUserQuestion` to ask if there is a parent or related issue.

- If **Sub-task**: The parent issue key is required. Set the `parent` field on create.
- If **any other type** and a parent is provided: Create the issue first, then link it. Ask which link type to use (Blocks, Depends, Related, Incorporates, etc.).
- If **Epic**: Ask for an `epic_name` (required for Epics).

### Step 7: Quality Grade

Before creating, evaluate the planned issue content against the matching template (from the specialist's `template.md`).

Score the content on these 5 dimensions:

| Dimension | Weight |
|-----------|--------|
| Completeness | 25% |
| Linkage | 20% |
| Clarity | 25% |
| Sizing / Scoping | 15% |
| Measurability | 15% |

Assign an overall grade: **[A] READY**, **[B] MINOR GAPS**, **[C] NEEDS WORK**, or **[D] NOT READY**.

- **[A] or [B]**: Proceed to confirmation.
- **[C] or [D]**: Present the grade and specific gaps to the user. Ask whether to improve the content or proceed anyway. Do not proceed without explicit confirmation.

### Step 8: Confirm and Create

Before calling the create MCP tool, display a summary of ALL fields and the quality grade. Ask for confirmation.

Always set:
- `project_key`: from personal config (tool-aware — see `AGENTS.md` fallback chain)
- `security_level`: "Red Hat Employee" (ID: `10034`)
- `assignee`: from personal config (tool-aware — see `AGENTS.md` fallback chain)

Call the registered Jira MCP create tool with all collected fields.

After creation, if linking is needed, call the link MCP tool.

### Step 9: Post-Creation

After successful creation:
1. Display the created issue key and link
2. If this is an Epic, ask if the user wants to create child stories/tasks now
3. If this is a Feature, ask if the user wants to create related epics or stories

## Error Handling

- Validate date formats (YYYY-MM-DD)
- Validate time estimates use Jira format (e.g., '1h 30m', '2d')
- If the create call fails, show the error and ask the user what to fix
- Never retry creation without user confirmation
