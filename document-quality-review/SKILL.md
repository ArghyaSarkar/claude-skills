---
name: document-quality-review
description: Review documents for structural clarity, logical flow, vocabulary consistency, and argumentative rigour. Use when asked to check document structure, improve flow, trace vocabulary, audit section transitions, or critique how a document is written (as opposed to whether the solution it proposes is sound). Also use when iteratively drafting a proposal — checking each revision for structural improvements, clearer argumentation, and tighter flow as the document evolves. Triggers include "check the flow," "improve the structure," "is this well-written," "critique the document quality," "review my draft," or when a user shares a multi-section document and asks specifically about clarity, readability, or structural issues. Do NOT use when the user wants to evaluate whether a proposed solution actually solves a business problem — use the proposal-review skill for that.
---

# Document Quality Review Skill

Review documents for structure, continuity, and flow using these eleven checks.

## The Eleven Checks

### 1. Earned claims
Every section must earn what it claims. If a section presents conclusions, prior reasoning must show how they were derived.

**Test:** Can you trace each claim back to something established earlier? If not, the section is asserting rather than deriving.

### 2. Section bridging
Sections must connect, not just follow. The end of Section N should raise a question that Section N+1 answers.

**Test:** Is there an explicit handoff? Does the reader know why Section N+1 comes next?

### 3. Vocabulary introduction
New terms must be defined before they do load-bearing work.

**Test:** For every key term, can you point to where it was defined? If not, the reader is guessing.

### 4. Vocabulary tracing (late-document terms)
Terms appearing in later sections (especially recommendations, scope, or conclusions) must trace back to explicit introduction in earlier sections.

**Test:** List all key noun phrases in the final 1-2 sections. For each, find where it was first introduced and defined. Flag any term whose first appearance is in the application/conclusion sections.

### 5. Comparison standards
Assertions like "X doesn't fit" need a visible standard. State what X would need to fit before claiming it doesn't.

**Test:** If something is compared or excluded, have the criteria been stated first?

### 6. Tables over prose
Structured comparisons belong in tables, not paragraphs.

**Test:** If comparing two or more things across multiple dimensions, would a table make the structure scannable?

### 7. Visible inheritance
If something continues or repeats across states/phases, the structure should show it — not explain it in prose.

**Test:** Can the reader see the pattern, or must they hold an explanation in their head?

### 8. Derive, don't re-argue
Later sections should reference earlier reasoning, not repeat it with variations that create ambiguity.

**Test:** Does this section add new reasoning, or restate? If restating, can it just reference?

### 9. Earned scope restrictions
"X is out of scope" needs reasoning traced to criteria, not assertion.

**Test:** Can you trace the scope decision back to a framework established earlier?

### 10. Cut redundant prose
If a table already conveys the point, narrating it in prose is redundant.

**Test:** If the prose is removed, does the table still convey the point?

### 11. Defer implementation details
Framework documents should establish the framework before diving into execution specifics.

**Test:** Does this detail affect the framework decision, or is it about execution after the decision is made?

## Review Process

### Phase 1: Section-by-section audit
For each section, ask:
- What claim does this section make?
- Is the claim earned from prior sections?
- Does it bridge to the next section?
- Are new terms defined before use?

### Phase 2: Vocabulary trace
Before checking flow, list all key noun phrases in the final 1-2 sections (scope, recommendations, conclusions). For each term:
- Find its first appearance in the document
- Verify it was explicitly introduced/defined at that point
- Flag terms that first appear in application sections without prior introduction

Common culprits: compound nouns, category names, role labels, system names.

### Phase 3: Flow check
Read section transitions in sequence:
- End of Section 1 → Start of Section 2
- End of Section 2 → Start of Section 3
- (continue...)

Flag any transition where the connection is implicit or missing.

### Phase 4: Representation check
For each prose block longer than ~100 words, ask:
- Is this a comparison? → Consider table
- Is this listing items? → Consider table or bullets
- Is this explaining inheritance/repetition? → Can the structure show it instead?

### Phase 5: Redundancy check
For each section, ask:
- Does this re-argue something already established?
- Does a table already show what this prose narrates?
- Is this implementation detail that can be deferred?

## Output Format

Structure feedback as:

```
## Section [N]: [Title]

**Claim:** [What the section asserts]

**Issues:**
- [Check #]: [Specific problem]
- [Check #]: [Specific problem]

**Suggested fix:** [Concrete recommendation]
```

After section-by-section review, add:

```
## Vocabulary Trace

| Term | First appears | Introduced/defined? | Action needed |
|---|---|---|---|
| [term] | Section [N] | Yes/No | [fix] |
```

End with a summary of cross-cutting issues affecting multiple sections.

## Relationship to proposal-review

This skill evaluates document quality — structure, flow, vocabulary, and clarity. If the user wants to evaluate whether the proposed solution actually solves the business problem, use the `proposal-review` skill instead. The two are complementary:

- **document-quality-review:** Is the document well-structured and clearly written?
- **proposal-review:** Does the solution solve the problem?

Offer the proposal-review as an alternative if the user seems to be asking about solution fitness rather than document quality. Both skills can be used together if the user wants a full review.
