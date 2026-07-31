# Feature: [Feature Name]

**Issue Type:** Feature (Level 4 — Business Unit Strategy)
**JIRA Key:** [PROJ-XXX]
**Status:** [New/Refinement/Backlog/In Progress/Review/Closed]
**Assignee:** [Engineering Manager or equivalent — accountable for execution]
**Created:** [YYYY-MM-DD]

---

## Feature Overview (Goal Summary)

> **Purpose:** Describes a tangible piece of value delivered to customers, typically within a Quarter/Release. Focus on the **What** and the **Why** — not the How. Completion is equivalent to a line item in published release notes.

[What is this feature and why does it matter to customers? Describe the tangible capability being delivered.]

---

## Goals (Expected User Outcomes)

> **Guidance:** The observable functionality that customers now have as a result of receiving this Feature. "The customer can now do X."

**After this Feature is delivered, customers will be able to:**

1. [User capability 1]
2. [User capability 2]
3. [User capability 3]

**Value Proposition:**
- [Benefit to customer 1]
- [Benefit to customer 2]

---

## Requirements (Acceptance Criteria)

> **Guidance:** Specific needs or objectives that must be delivered for the Feature to be considered complete. Used to scope Epics.

### Functional Requirements

1. [Requirement 1 — specific, testable]
2. [Requirement 2 — specific, testable]
3. [Requirement 3 — specific, testable]

### Non-Functional Requirements

**Security:** [Security requirement]
**Reliability:** [Reliability requirement]
**Performance:** [Performance requirement with metrics]
**Scalability:** [Scale requirement with numbers]
**Usability:** [Usability requirement]

---

## Supported Clients

| Client Type | Supported | Notes |
|-------------|-----------|-------|
| CLI | ( ) Yes ( ) No ( ) N/A | |
| Web UI | ( ) Yes ( ) No ( ) N/A | |
| API | ( ) Yes ( ) No ( ) N/A | |
| Terraform/IaC | ( ) Yes ( ) No ( ) N/A | |

---

## Supported Offerings

| Offering | Supported | Notes |
|----------|-----------|-------|
| [Offering 1] | ( ) Yes ( ) No ( ) N/A | |
| [Offering 2] | ( ) Yes ( ) No ( ) N/A | |
| [Compliance/Regulated] | ( ) Yes ( ) No ( ) N/A | |

---

## Use Cases

### Use Case 1: [Name]

**Actor:** [Who is using this feature]
**Preconditions:** [What must be true before this use case]

**Main Success Scenario:**
1. [Step 1]
2. [Step 2]
3. [Result]

**Alternative Flows:**
- [Alternative path]

---

## Out of Scope

> High-level list of items explicitly NOT included in this Feature.

- [Out of scope item 1]
- [Out of scope item 2]

---

## Background

**Problem Statement:** [What problem are we solving?]
**Current State:** [How do things work today?]
**Desired Future State:** [How will things work after this Feature?]

---

## Customer Considerations

**Target Customers:** [Customer segment(s)]
**Migration/Upgrade Path:** [How will existing customers adopt this?]

---

## Related Work

**Parent Outcome:** [PROJ-XXX: Outcome Name] *(link via Parent Link field in Jira)*

**Epics:** *(Feature is complete when all dependent Epics have been delivered)*
- [EPIC-XXX: Epic Name]
- [EPIC-XXX: Epic Name]

**Dependencies / Related Features:**
- [Dependency or related Feature]

---

## Roles and Responsibilities

> **Guidance:** All three roles must be named. These are collectively accountable for the Feature's definition and delivery — not a hand-off chain.

| Role | Jira Field | Person | Responsibility |
|---|---|---|---|
| **Product Manager** | Product Manager field | [Name] | What & Why — defines desired results and customer value, anchors to business impact |
| **Architect** | Architect field | [Name] | How — defines technical approach, ensures architectural alignment |
| **Assignee** | Assignee field | [Name — Engineering Manager or equivalent] | Execution — staffing, delivery, escalation |
| **Contributors** | Contributors field | [Name(s)] | QE Lead, Docs Lead, other contributors |

---

## Workflow Exit Criteria

| Status | Exit Criteria |
|---|---|
| **New** | Stakeholders identified, Product Manager identified, Architect identified, Assignee identified, SMEs identified, goals documented, high-level use cases documented |
| **Refinement** | MVP described, risks and dependencies outlined, Epics produced, priority assigned, acked by all functions, roadmaps updated |
| **Backlog** | Refinement complete, Epics linked, priority assigned — queued pending capacity or scheduling decision |
| **In Progress** | Development work completed, QE testing completed, Docs written |
| **Review** | All development, QE, and documentation complete; undergoing final stakeholder/leadership review before closure |
| **Closed** | Resolution value set, all underlying Epics developed, tested, and released |

---

## Scope Signals — Questions to Consider

> These are guidelines, not hard rules. Leadership may intentionally scope differently. Surface these as questions, not rejections.

- Does this Feature describe something **customers** can do in the product? If the primary beneficiary is Red Hat associates, an Initiative may be a better fit.
- Is the Feature scoped to deliver within a **single Quarter/Release**? If it spans releases, confirm whether splitting is appropriate or if the broader scope is intentional.
- Is there a clear **customer value statement** (not just a list of Epics)? A Feature should describe what customers will do differently, not just what engineering will build.

---

## Notes

[Additional notes, links to designs, prototypes, research, etc.]
