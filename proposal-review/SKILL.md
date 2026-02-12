x---
name: proposal-review
description: Evaluate whether a proposal's recommended solution actually solves the stated business problem. Use when asked to review, critique, or pressure-test a proposal, RFC, strategy doc, or architecture recommendation. Triggers include "review this proposal," "does this make sense," "should we go ahead with this," "evaluate this recommendation," or when a user shares a proposal and wants to know if the solution holds up. Do NOT use when the user only wants to check document structure, flow, or writing quality — use the document-quality-review skill for that.
---

# Proposal Review Skill

Evaluate whether a proposal's solution actually solves the business problem it claims to solve.

## Before reading the document

Always gather context first. Do not start reviewing until you understand:

1. **What triggered this proposal?** What's the business problem or pain point that led to it being written?
2. **Who is the audience?** Who needs to be convinced — engineering, leadership, a cross-functional group?
3. **What stage is this at?** Are we aligning on direction, reviewing a design, or evaluating implementation details?
4. **What is the reviewer's role?** Are they the proposal owner's peer, manager, a stakeholder from another function? What's their relationship to the proposal owner?
5. **What is the reviewer's primary concern?** Cost, feasibility, governance, team capacity, risk — what lens are they applying?

If the user doesn't volunteer this context, ask for it. The review quality depends on it.

## The core question

Every proposal review comes down to one question:

**Does the proposed solution actually solve the stated business problem?**

Not "is it well-written?" Not "is the architecture clean?" — does it solve the problem? Everything else is secondary.

## Review process

### Phase 1: Problem–solution fit

Read the proposal and test:

- **What business problem does the proposal claim to solve?** State it in one sentence.
- **Does the proposed solution solve that problem, or an adjacent one?** Many proposals correctly identify a problem, then propose a solution that solves a related but different problem. Look for this gap.
- **Does the solution solve the problem at the right layer?** If the problem is "we're emitting unnecessary data," does the solution stop the emission, or just filter it downstream? If the problem is "we can't move fast enough," does the solution remove the bottleneck, or add a new one?
- **What does the solution move, not just what does it remove?** Every solution displaces complexity somewhere. Where does it go? Who inherits it? Is that acknowledged?

### Phase 2: Alternatives and assumptions

- **Has more than one approach been considered?** If the proposal presents a single solution, flag this. There should be at least 2-3 approaches evaluated against the requirements.
- **Are there structurally different alternatives?** Not just build-vs-buy, but fundamentally different architectural shapes. Think about where logic lives, where data flows, what's centralized vs. distributed.
- **What's the "do nothing" cost?** What happens if we don't solve this? Is it quantified? If not, the urgency isn't earned.
- **What assumptions does the solution depend on?** Identify the things that must be true for the solution to work. Are they stated? Are they tested?

### Phase 3: Costs, risks, and tradeoffs

- **Is there a cost model?** Even a rough one — build cost vs. savings, infrastructure cost vs. current cost.
- **What are the failure modes?** What breaks if this system goes wrong? How is it detected? What's the blast radius?
- **What operational surface does this create?** Who runs this day-to-day? What can go wrong in operations (bad config, silent failures, debugging)?
- **Are there latency, real-time, or sequencing constraints** that the proposal doesn't address?

### Phase 4: Stage-appropriate filtering

Match feedback to the decision stage. Ruthlessly cut anything that belongs in a later stage.

- **Direction stage:** Does the solution solve the problem? Are alternatives considered? Is the cost case made? Stop here.
- **Design stage:** Migration plan, failure modes, observability, ownership, data quality, backward compatibility.
- **Implementation stage:** Specific technical tradeoffs, API design, schema details, rollout sequencing.

Only include feedback for the current stage. Note deferred items in a single line each if they're important to flag, but do not elaborate.

## Output format

### Metadata

Every review starts with a metadata table (no header row):

| | |
|---|---|
| **Reviewer** | [Name] |
| **Date** | [Date] |
| **Version** | [Version] |
| **Proposal** | [Link to proposal] |

### Changelog

Immediately after metadata, include a changelog table:

| Version | Timestamp (IST) | Changes |
|---|---|---|
| v1.0 | [Date · Time] | Initial review |

When updating a review in place, add a new row. Use timestamps (not just dates) so the user can match to Notion page history.

### Feedback structure

- **Context:** 2-3 sentences on the business problem and why this proposal exists. Anchor the review in the problem, not the document.
- **On framing (brief):** If the proposal makes valid points that are poorly emphasised or unquantified, say so in 1-2 sentences. Don't elaborate — just note what to strengthen and move on.
- **Core section — does the solution solve the problem?** This is the bulk of the review. Frame as questions, not assertions. Each point should be a short paragraph: name the concern, explain why it matters, ask the question.
- **Questions before committing:** A numbered list of specific questions the proposal owner should answer before the next step. Include alternative approaches here, framed as "have you considered X — curious if this was explored and ruled out."
- **Summary:** 3-4 sentences. Restate alignment on the problem. State the core concern. End with a collaborative invitation.

### Tone rules

- **Frame feedback as questions, not assertions.** The proposal owner stays in control. "Have you thought about X?" not "X is missing."
- **"Curious if this was explored and ruled out"** is the template for suggesting alternatives.
- **One line on what's working. Depth on what's missing.**
- **Close collaboratively.** Every review ends with an invitation to discuss, not a verdict.
- **Don't over-explain agreement or soften excessively.** Be direct, be kind, be brief.

## Relationship to document-quality-review

This skill evaluates whether the solution holds up. If the user also wants feedback on document structure, vocabulary, flow, or writing quality, use the `document-quality-review` skill as an add-on. The two are complementary:

- **proposal-review:** Does the solution solve the problem?
- **document-quality-review:** Is the document well-structured and clearly written?

Offer the document-quality-review as an optional follow-up if you notice significant structural issues, but don't mix the two in the same output unless the user asks for both.

## Notion integration

Reviews are stored in Notion under a master page ("Proposal Reviews — [Reviewer Name]"). Rules:

- **One page per proposal.** Title format: "Review: [Proposal Name] (v[X.Y])"
- **Version control:** Edit in place, bump version, add changelog row with timestamp. Previous versions are available via Notion page history.
- **Only push to Notion when the user green-lights the .md preview.**
- **Metadata table has no empty header row.** Use `header-row="false"` in Notion.
