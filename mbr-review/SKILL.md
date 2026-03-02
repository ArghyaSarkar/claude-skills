---
name: mbr-review
description: Review Monthly Business Reviews (MBRs) for accountability, progress integrity, and operational rigor. Use when asked to review, critique, or audit an MBR document. Triggers include "review this MBR," "critique my team's MBR," "audit this monthly review," "check this progress update," or when a user shares a status document with OKRs, RAG statuses, dependencies, and metrics. Do NOT use for proposal evaluation (use proposal-review) or document structure checks (use document-quality-review). This skill focuses on whether progress claims are honest, metrics are meaningful, and blockers are being actively managed.
---

# MBR Review Skill

Review Monthly Business Reviews for accountability, progress integrity, and operational rigor.

## The Core Question

Every MBR review comes down to one question:

**Is this document telling the truth about where we are, what's blocking us, and what we're doing about it?**

Not "is the formatting nice?" Not "is the team working hard?" — is the status accurate and are blockers being actively managed?

## Citation Requirements

Every critique must cite its source. Format: `Section → Subsection → Table/Field`

**Good:** "Pre-Auth is at 4% vs 80% target, marked Green (Goal 1 → OKR table)"

**Bad:** "Some RAG statuses seem inflated"

**Good:** "Competition is running 0% commission + discounts (BAU → International), Porter is 23-34% more expensive (Competition → UAE → Pricing → Pickup 1Ton), and 19% of customers cite pricing as the switch reason (Voice of Customer → International)"

**Bad:** "There's competitive pressure on pricing"

Citations serve two purposes:
1. The MBR owner can verify and respond
2. The reviewer forces themselves to ground claims in evidence, not impression

## Before Reading the Document

Gather context first:

1. **What is the review period?** Monthly, quarterly, what timeframe?
2. **What is the OKR period end date?** When do targets need to be hit?
3. **Is a previous period's MBR available?** Comparison reveals slippage and recurring blockers.
4. **Who is the audience?** Leadership, peers, cross-functional stakeholders?
5. **What is the reviewer's role?** Are they the team's manager, a peer lead, or an executive?

If context is missing, ask for it. The review quality depends on understanding what "on track" means.

6. **What is the document structure?** Extract the outline first. Never dive into content without knowing the full structure.

If the document is large or has multiple periods/workstreams, always extract the outline and confirm scope with the user before reviewing any section.

## Anomaly Scanning and Cross-Section Narratives

This is the primary methodology. It comes before everything else.

MBRs are typically written section-by-section by different authors. Nobody owns cross-section coherence. The reviewer's unique value is reading across sections and finding the stories that fall between the cracks.

Individual anomalies — a RAG mismatch, a blank metric, a vague concern — are evidence, not findings. The finding is the business story they tell together. The connected stories are what leadership can't see from reading the MBR themselves.

### Step 1: Collect anomalies while reading

An anomaly is anything that looks off within its section:
- A metric spiking or dropping without explanation
- A blank cell where there should be data
- A trend reversing from the previous month
- A RAG status that doesn't match the numbers next to it
- A concern that contradicts the workstream's overall RAG
- A "happy about" item that's actually an input, not an outcome
- A data table telling a different story than the narrative around it

An anomaly can also be an absence:
- An entire section that's empty when it should represent a strategic priority
- A workstream that exists in the outline but has no content — is it deprioritized, or just forgotten?
- A topic the org is clearly invested in (from other sections' references) that has no dedicated coverage

Don't evaluate anomalies as you find them. Just collect them. A 5x ticket spike might mean nothing alone.

### Step 2: Look for corroboration across sections

For each anomaly, ask: does any other section explain, contradict, or echo this?

- Does the same issue surface in a different workstream's concerns?
- Does a metrics table in BAU corroborate a trend flagged in Goals?
- Does a concern in one section reveal the root cause of an anomaly in another?
- Are multiple workstreams complaining about the same constraint without naming it as shared?

### Step 3: Stitch into a business narrative

When two or more anomalies from different sections point at the same underlying issue, that's a finding. Name the business issue, cite the evidence from each section, and end with the question the MBR should have asked but didn't.

### Example

> Finance Products marks itself Green. But the OKR table shows 96.9% vs 99.9% target with no remarks. The concerns section lists four active blockers including platform delays and no frontend engineers for three weeks. The metrics table shows L3/L4 invoicing tickets spiked 5x (46 → 239) in the same month. The uptime metric cell is blank.
>
> Separately, the invoicing platform delays are blocking CN/DN and EY-recommended compliance changes, both targeted for March.
>
> **The narrative:** The invoicing platform is the critical path for compliance readiness, and it's behind schedule with active blockers — but the RAG signals Green to leadership. The risk isn't engineering timelines; it's regulatory exposure if EY changes slip past the quarter.
>
> **The question:** What is the realistic ship date, and what is the compliance exposure if these don't land in Q4 FY26?

### What makes a strong cross-section finding

- Connects 2+ sections that aren't explicitly connected in the MBR
- Identifies a business risk or strategic question — not a document quality issue
- Ends with a question the MBR owner should answer
- Would be invisible to someone reading only one section

## The Strategic Lens

After anomaly scanning, step back and ask one question the MBR never asks itself:

**Is this team working on the right things?**

- **Portfolio balance:** Is investment distributed across the right mix of build vs. maintain vs. scale? Are too many bets concentrated on a single risk?
- **Strategic alignment:** Do the OKRs connect to what the business needs this quarter? Are any workstreams solving problems that are no longer top priority?
- **Adoption vs. build:** Is the team shipping things that get used, or building things that sit on a shelf? What's the adoption signal for what shipped last quarter?
- **ROI clarity:** Can you tell, from this MBR, whether this team's work is creating business value? If not, that's a finding.

This is not a check to apply mechanically. It's the question that separates an operational review from a strategic one. If the anomaly scan reveals that the team is efficiently executing on the wrong things, that's the highest-severity finding.

### Leadership Lenses

Every review should surface questions that matter across leadership perspectives. Apply all of these — don't pick one based on who requested the review.

- **Head of Function** (e.g., Head of Data): Is the portfolio balanced? Are shipped products getting adopted? Where are cross-team dependencies that need intervention? Is the team levelling up or running on a treadmill?
- **CEO / Executive:** Is this team enabling better decisions across the org? What's the total ROI of what's been built? Where should investment be reallocated? What's the one thing that needs unblocking?
- **Head of Product / Peer Lead:** Are data products solving real user problems or just technical milestones? Where are our dependencies interacting badly? What can other teams learn from what's working here?

Findings that only matter to one lens are fine. The goal is to ensure the review doesn't have blind spots — a review that only asks operational questions misses strategy; one that only asks strategy misses execution gaps.

## The Eight Checks

Use these checks to gather evidence while reading. They are your scanning lens, not your output structure.

A RAG mismatch is not a finding — "leadership is seeing Green while two OKRs are below target with active blockers" is a finding. Always frame check results as business consequences, not document observations.

### 1. RAG Status Integrity

RAG should reflect current state, not future optimism.

**Anti-patterns:**
- **Green inflation:** Items marked Green that are not started, 0% complete, or significantly below target
- **Inconsistent logic:** Some RAGs are current-state, others are forward-looking ("will improve after X release")
- **Missing RAG:** Rows or sections without any status
- **Amber as comfort zone:** Everything is Amber — nothing Red, nothing Green — signals avoidance

**Test:** For each Green item, check: Is current value ≥ target, or within acceptable variance? If not, why is it Green?

**Principle:** *Forward-looking optimism belongs in Remarks, not RAG status.*

### 2. Dependency & Blocker Management

Dependencies need owners, ETAs, and escalation paths.

**Anti-patterns:**
- **Dependencies without ETAs:** "In Progress" with no target date
- **Recurring blockers:** Same blocker appearing across multiple months without escalation
- **Passive waiting:** "Blocked on X" without active mitigation
- **Single owner, multiple blockers:** One team/person owns 3+ unresolved dependencies
- **No escalation path:** Blockers exist but no mention of escalation

**Test:** For each dependency, can you answer: Who owns it? When is it expected? What happens if it slips?

**Principle:** *A dependency table without ETAs is a wishlist. A recurring blocker without escalation is acceptance.*

### 3. Metrics Discipline

Metrics need SLOs, and misses need recovery plans.

**Anti-patterns:**
- **SLO = "TBD":** Core metrics without defined success thresholds
- **Below SLO, no recovery plan:** Metric misses without documented path to recovery
- **"Flat" without context:** "Flat from last month" — is flat good or bad?
- **External attribution without playbook:** "Due to festivals/elections" — predictable events treated as surprises
- **Regression normalized:** GREEN → AMBER framed as "slight impact"

**Test:** For each metric below SLO, is there a recovery plan? For "TBD" SLOs in February of a Q1 cycle, why isn't it defined yet?

**Principle:** *A metric without an SLO is a vanity metric. A metric below SLO without a recovery plan is unmanaged.*

### 4. Progress vs. Activity

Progress is value delivered or risk retired. Activity is motion.

**Anti-patterns:**
- **Celebrating starts:** "Development started for X" — starting is not completing
- **Artifacts as outcomes:** "HLD completed, LLD in progress" — documents are inputs, not value
- **Planning as progress:** "New plan to be created by Friday" — a plan to make a plan
- **Recalibration as win:** "Recalibrated release train" after a slip — this is recovery, not progress

**Test:** For each "happy about" item, ask: Did users/customers receive value, or did we complete an internal milestone?

**Principle:** *Celebrate outcomes, not inputs. Completing documents is not shipping software.*

### 5. Concerns Section Quality

Empty or vague concerns are a red flag.

**Anti-patterns:**
- **Empty concerns:** Nothing in "What are we concerned about" — signals denial or fear of surfacing reality
- **Vague concerns:** "Dependencies taking longer than expected" — which ones? how much longer? what's the mitigation?
- **Structural concerns only:** "Multiple reviews and discussions" — process friction, not delivery risk
- **No mitigation:** Concerns listed without any action or owner

**Test:** For each concern, can you answer: What specifically? How bad? What are we doing about it? Who owns the fix?

**Principle:** *Concerns should be specific, quantified, and have mitigation paths.*

### 6. Risk Visibility

Are problems surfaced where decision-makers will see them?

**Anti-patterns:**
- **Buried risks:** Crisis metric in a table, but not mentioned in Executive Summary or Concerns
- **Disconnected sections:** Competition shows pricing gap, Voice of Customer confirms it, but Goals don't address it
- **Happy section longer than Concerns:** More space celebrating wins than acknowledging risks
- **Stress metrics without escalation:** Items in crisis for 2+ months with no escalation path

**Test:** For each Stress Metric or crisis indicator, is it acknowledged in the Executive Summary or Concerns? If not, why is it hidden?

**Principle:** *A crisis that only appears in a data table is a crisis that hasn't been escalated.*

### 7. Accountability Signals

Every item needs an owner who can be held accountable.

**Anti-patterns:**
- **No DRI on blockers:** Dependencies with no owner column or blank owners
- **Passive voice:** "Is blocked on", "waiting for", "to be picked"
- **Distributed blame:** "Multiple teams need to align" — who's driving?
- **Absent owners:** Named owners who haven't updated their sections

**Test:** For each blocker or at-risk item, can you name one person who owns the resolution?

**Principle:** *Every blocker needs an owner, an ETA, and an escalation trigger.*

### 8. Temporal Consistency

Compare to previous periods to catch hidden slippage.

**Anti-patterns:**
- **Targets beyond OKR period:** March OKR with May targets
- **Milestone slippage unmarked:** Date changed from last month with no acknowledgment
- **"No new updates" everywhere:** Multiple items with no progress — is work happening?
- **Revision frequency:** "Will be revised Friday" — how often is this plan changing?
- **Silent date changes:** Target date in December MBR was Feb 7; now it's Feb 13 with no callout

**Test:** If you have the previous MBR, compare key dates and targets. Flag any changes that aren't explicitly acknowledged.

**Principle:** *Slips should be acknowledged, not quietly updated.*

## Document Navigation

Before reviewing content, extract the outline, present it, and confirm scope. Default to consolidated review. Section-by-section delivery is only for documents too large to review at once.

Parse headers including variants: `▶## Section Name`, `▶## <span ...>Section Name</span>`. Read all content within scope before writing any findings.

## Review Process

The Anomaly Scanning section above IS the review process. Read → Collect → Connect → Write. This section adds two additional lenses to apply during the Write phase.

### Identify Strengths

Before writing critiques, identify 2-3 sections that demonstrate genuine strength:

- **Real outcomes** — shipped, validated, adopted — not plans or documents
- **Well-structured concerns** — specific issue/mitigation format, named root causes
- **User-outcome framing** — OKRs as user pain points and success outcomes, not engineering metrics
- **Honest self-assessment** — acknowledging delays with root causes, surfacing uncomfortable truths
- **Business-framed metrics** — cost as ROI, impact quantified in business terms

Strengths earn credibility for the critique and show the MBR owner what "good" looks like in their own document.

### Editorial Observations

Template placeholders, date typos, formatting issues — note once at the end if they indicate a process concern. Never elevate to primary findings.

**Every finding must answer: "So what for the business?"**

## Operational Flags

After business findings, scan for items that need action before the next MBR but don't rise to a cross-section business theme. These are the follow-up checklist — not the strategic narrative.

### Inclusion Criteria

A flag must be:
- **Assignable** — one person or team should act
- **Actionable** — there's a specific thing to do (set an ETA, kill a stale item, resolve an ambiguity, establish a process), not just "add more detail"
- **Not already covered** — the business findings don't already address this action

### Exclusions

- **RAG/signaling issues** — if a RAG mismatch matters, it's evidence in a business finding. If it doesn't, the MBR owner can catch it in self-review.
- **Editorial issues** — placeholder links, empty numbered lists, template hygiene
- **Isolated misses** — single-workstream items the owner already knows about and can fix. If they don't, it becomes compounding neglect next month.

### Categories

| Category | Definition | Why the reviewer adds value |
|----------|-----------|---------------------------|
| **Compounding neglect** | Overdue 2+ weeks with no acknowledgment, or ambiguity sitting unresolved across review cycles. | Owner hasn't self-corrected — naming it creates accountability |
| **Cross-team blind spot** | Affects multiple teams but visible in only one section, or requires coordination nobody owns. Includes unresolved questions whose answer affects multiple workstreams. | Owner can't self-correct — only a cross-section reader sees the full picture |

When listing flags, note patterns across items (e.g., "three overdue items from one owner = bandwidth signal, not three independent misses").

## Output Format

### What's Strong

Open with 2-3 specific acknowledgments before any critique. Keep them tight — name the section, say what it does well, and why it matters. This is not filler; it's the benchmark the rest of the review is measured against.

**Good:** "The QMOS concerns section names four risks, each with an explicit Issue/Mitigation structure. This is the standard the other workstreams should follow — Architecture Leverage and Data Platform 2.0 have empty concerns sections by comparison."

**Bad:** "There are some good parts of the MBR."

Each acknowledgment should be 2-3 sentences: what's strong, where it is, and why it matters for the business or for the quality of the review itself.

### Summary Table

Start with a summary of findings by business theme:

| Theme | Severity |
|-------|----------|
| [Business theme name] | [High/Medium/Low] |
| [Business theme name] | [High/Medium/Low] |

Name themes in business terms: "Fraud Economics", "Invoicing Platform Cascade", "Capacity vs. Mandate" — not "RAG Integrity Issues" or "Metrics Discipline Problems."

### Workstream Scorecards

Before business findings, provide a scannable per-workstream table so each goal owner gets directed feedback without parsing the full review. One row per workstream with:

| Column | What goes here |
|--------|---------------|
| **Workstream** | Name as it appears in the MBR |
| **Owner** | Named owner from the MBR |
| **Status Read** | 1-2 sentence honest read of where this workstream stands. Not a summary of the section — a judgment. |
| **Key Risk** | The single biggest risk for this workstream. Can reference a business finding if applicable. |
| **Directed Action** | One specific thing this owner should do before next MBR. Actionable, not vague. |

Keep each cell tight — this is a 10-second read per row. The business findings provide the deeper "why it matters" context; the scorecards provide the "what should I do" per owner.

### Business-Themed Findings

Each finding:

1. **Name the issue** in business terms
2. **Build the case with citations** — cite evidence from multiple sections
3. **Connect the dots** — show how the evidence tells a story the MBR doesn't tell itself
4. **End with a question** — what should the MBR owner answer?

**Example:**

```
## The Invoicing Platform Cascade

Finance Products is marked Green. Two of three OKRs are below target with six weeks to go.

Invoice compliance: 96.9% vs 99.9% target, marked Green, no remarks (FP → OKR table).
OMS dependency: 10/month vs 0/month target, marked Green (FP → OKR table).

The concerns section lists invoicing platform delays, UAT issues, no FE engineers for
three weeks (FP → Concerns). L3/L4 tickets spiked 5x in the same month (FP → Metrics).
The platform is the critical path for CN/DN and EY compliance changes, both targeted
for March.

The question: What is the realistic ship date, and what is the compliance exposure if
EY changes don't land this quarter?
```

### Operational Flags

After business findings, list actionable items in two categories: Compounding Neglect and Cross-Team Blind Spots. Each flag: cite the item, state the action needed, keep it to one line. Note patterns across flags when multiple items share a root cause.

Aim for 5-15 flags. Fewer than 5 means you're not scanning thoroughly. More than 15 means you're including isolated misses or editorial issues that should be excluded.

### Org-Level Synthesis

After the findings, add a brief (2-3 sentence) synthesis answering: "What does this MBR tell us about where this team is as a whole?" This is the question that connects workstream-level findings into a team-level assessment. It should be an honest read — not a summary of findings, but a judgment.

### Questions Before Next MBR

End with 3-5 business questions. Questions should be **actionable** — they should suggest a specific response, not just name a gap.

**Good:** "Should adoption targets with named DRIs be added to each workstream's KRs for next quarter?"

**OK:** "Who owns adoption for shipped products?"

**Bad:** "Can the Concerns section be more specific?"

## Severity Calibration

| Severity | Criteria |
|----------|----------|
| **High** | Business risk is active now, financial exposure is quantifiable, or leadership is receiving a materially wrong signal |
| **Medium** | Execution risk is building, adoption gap threatens ROI of shipped work, or a cross-section pattern reveals unmanaged dependency |
| **Low** | Operational hygiene gap, missing data that would improve future reviews, or isolated anomaly without cross-section corroboration |

## Tone Calibration

The default tone is **direct and principle-backed**. Adjust based on context:

- **For peer review:** Direct, collegial, focused on improvement
- **For leadership review:** Scathing where warranted, but fair — every critique tied to a principle
- **For self-review:** Constructive, focused on "what would make this stronger"

When critiquing:
- Name the specific issue
- State why it matters (the principle)
- Suggest what "good" looks like (if not obvious)

**Be concise.** State the issue. Cite the evidence. Ask the question. Each finding should be 3-5 tight paragraphs. If a finding takes a full page, the evidence isn't tight enough or you're making multiple points that should be split. Cut scaffolding sentences ("Let me now turn to...", "This is significant because..."). Let the evidence speak.

**Watch granularity.** Individual anomalies (one experiment running 112 days, one uptime miss) are evidence, not findings. Use them to support a business narrative — don't let them become standalone paragraphs. The right level is the business pattern, not the individual data point.

**Aim for 3-5 findings.** More than 5 dilutes impact — merge weaker findings into stronger ones as supporting evidence. If you can't get below 5, the findings aren't thematic enough.

**Flag missing context.** If information that's essential for assessment (total team cost, previous period's data, adoption baselines) isn't in the MBR, note what's absent and why it matters — don't just work around the gap.

Avoid:
- Softening language that obscures the point
- Critique without principle ("this feels off")
- Piling on — if a pattern is established, note it once and reference it

### Good vs. Bad Critiques

| Bad (document-focused) | Good (business-focused) |
|------------------------|------------------------|
| "The Concerns section lacks specificity" | "FP cites four blockers to invoicing rollout but no recovery path. Who is managing the cascade into CN/DN and EY compliance?" |
| "RAG logic is inconsistent" | "Finance Products is Green but two of three OKRs are below target with active blockers. Leadership is seeing a signal that doesn't match the data." |
| "This section could use more detail" | "Account sharing grew 45% over three months while the countermeasure isn't live. What is the financial exposure of this delay?" |
| "Missing recovery plan" | "Undercut losses are ₹1.23 Cr/month and rising. The real-time detection system isn't live yet. What's the monthly burn rate until it ships?" |
| "Empty section" | "Three workstreams cite bandwidth constraints independently. The cross-thread dependencies section is empty. Who owns the trade-off?" |

## Publishing to Notion

After the review is complete, publish it to Notion under the **Arghya MBR Reviews** parent page.

### Workflow

1. **Search** for "Arghya MBR Reviews" using the Notion search tool. If it doesn't exist, create it as a workspace-level page.
2. **Create** the review as a subpage under it, titled: `[Document Name] — [Month Year] MBR Review` (e.g., "Central Data — February 2026 MBR Review").
3. **Format** using Notion-flavored markdown:
   - Use `<table>` with `header-row="true"` for the Summary Table and Operational Flags tables
   - Use `<callout>` blocks for questions (yellow\_bg) and pattern notes (blue\_bg)
   - Use `<span color="red">` / `<span color="orange">` for severity indicators in the summary table
   - Use `---` dividers between major sections
4. **Share** the Notion URL with the user when done.

### Page Structure

The subpage should contain, in order: review metadata (period, OKR end date, missing context), What's Strong, Summary Table, Business-Themed Findings (each ending with a question callout), Operational Flags (tables + pattern callouts), Org-Level Synthesis, Questions Before Next MBR.

## Relationship to Other Skills

- **proposal-review:** Evaluates whether a proposed solution solves a business problem. Use for strategy docs, RFCs, architecture proposals.
- **document-quality-review:** Evaluates structure, flow, vocabulary, and writing clarity. Use for any document where readability matters.
- **mbr-review (this skill):** Evaluates operational honesty — are status claims accurate, are blockers managed, are metrics meaningful.

These skills can be combined. An MBR that's operationally honest but poorly structured might benefit from document-quality-review as a follow-up.
