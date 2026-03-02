# MBR Review Skill — Iteration Log

Systematic skill improvement through 3 iterations, each applying the skill to the Central Data February 2026 MBR, evaluating through Head of Data / CEO / Head of Product lenses, and documenting improvements.

**Date:** 2026-02-17
**Document used:** Central Data - February 2026 Review

---

## Iteration 1

### Skill Changes Applied

| Change | Rationale |
|--------|-----------|
| Added **Strategic Lens** section | Review was purely operational — missed "is the team working on the right things?" |
| Added **Leadership Lenses** (always-on, all perspectives) | Review should surface questions for Head of Data, CEO, and Head of Product simultaneously — not pick one based on reviewer role |
| Merged **Review Process** phases into Anomaly Scanning | Phases 1-4 duplicated the Anomaly Scanning steps; collapsed to remove redundancy |
| Trimmed **Document Navigation** | Over-explained for what it contributes; reduced to essential guidance |
| Added **Severity Calibration** table | High/Medium/Low had no defined criteria; now grounded in business risk, execution risk, and hygiene |

### Review Output Assessment

**What worked:**
- Strategic Lens directly produced "Build Without Demand Signal" finding
- Leadership Lenses enabled multi-perspective questions within findings
- QMOS concerns section identified as gold standard (contrast for critique)
- DS Platform ROI framing highlighted as the model

**What didn't work:**
- No org-level synthesis — findings were workstream-level, no team-level judgment
- Data Literacy section (empty) not flagged — a strategic absence, not just a document gap
- 112-day experiment detail was too granular — individual anomaly, not business pattern
- Questions were open-ended ("Who owns adoption?") rather than actionable

### Lens Evaluation

**Head of Data:**
- Landed: DE bottleneck, adoption deficit, ROI framing gap
- Missed: Data Literacy absence, team capability gaps (QMOS citing GIT/Claude Code access issues)

**CEO:**
- Landed: ROI question, adoption as business risk, cost trajectory
- Missed: No org-level "is this team making Porter more data-driven?" synthesis; too granular on individual experiments

**Head of Product:**
- Landed: Build without demand signal, QMOS user-outcome framing
- Missed: Alternate View section as product management maturity signal

### Improvements Identified for Iteration 2

1. Add Org-Level Synthesis to output format
2. Flag notable absences (empty sections as strategic gaps)
3. Reduce granularity on isolated anomalies
4. Elevate QMOS user-pain-point framing more strongly as model

---

## Iteration 2

### Skill Changes Applied

| Change | Rationale |
|--------|-----------|
| Added **Org-Level Synthesis** to output format | Review lacked team-level judgment; findings were workstream-level only |
| Added **absence as anomaly** to scanning guidance | Empty sections representing strategic priorities were being ignored |
| Added **granularity guidance** | Individual data points (one experiment, one uptime miss) were overweighted as standalone points |
| Sharpened **question actionability** | Questions named gaps but didn't suggest specific responses |

### Review Output Assessment

**What improved from Iteration 1:**
- Org-level synthesis added: "builds well, adopts poorly" — the one sentence a Head of Data needs
- Data Literacy gap caught with cross-section evidence (concern in Ops-org, empty dedicated section)
- 112-day experiment folded into evidence, not standalone
- QMOS elevated to lead strength with "model for others" framing

**What still didn't work:**
- 5 findings — one too many; "The Empty Middle" was a collection of minor anomalies, not a business theme
- Questions still somewhat open-ended ("Who owns adoption?" vs suggesting a specific action)
- No flag on missing context (total team cost not in MBR, can't assess opportunity cost)
- Alternate View section noted but not celebrated enough as maturity signal

### Lens Evaluation

**Head of Data:**
- Landed: Org-level synthesis, DE bottleneck, Data Literacy cross-section catch
- Remaining gap: Could be more specific on what to do — "Should QMOS framing be mandated?" is more actionable than "Can the Alternate View become primary?"

**CEO:**
- Landed: ROI framing finding, org-level synthesis, adoption as risk
- Remaining gap: No total team investment number; findings still long for exec consumption; would want 3-4 findings not 5

**Head of Product:**
- Landed: Build without demand signal, QMOS as model
- Remaining gap: Alternate View as product management innovation deserves more celebration

### Improvements Identified for Iteration 3

1. Tighten to 4 findings max — merge weaker into stronger
2. Make questions more actionable — suggest specific responses
3. Note missing context explicitly (total team cost)
4. Elevate Alternate View as positive signal

---

## Iteration 3

### Skill Changes Applied

| Change | Rationale |
|--------|-----------|
| Added **finding count discipline** (aim for 3-5) | More than 5 dilutes impact; forces thematic consolidation |
| Added **"flag missing context"** guidance | Missing data was silently worked around instead of noted |
| Sharpened **question format** (Good/OK/Bad examples) | Questions should suggest specific responses, not just name gaps |

### Review Output Assessment

**What improved from Iteration 2:**
- 4 findings instead of 5 — "Empty Middle" merged into Findings #1 and #4 as evidence
- Org-level synthesis tighter: adds "inflection point" framing about the team's transition
- Questions are actionable: "Should every shipped product get an adoption KR with a named DRI?" not just "Who owns adoption?"
- Missing context flagged explicitly in Finding #2
- QMOS + Alternate View tied together as lead strength
- Multi-lens questions woven into findings naturally, not as separate commentary

**Remaining gaps (honest assessment):**
- No previous period comparison (Jan '26 MBR not available)
- Adoption numbers taken at face value (7/15 denominator completeness unknown)
- Team-level investment data absent from MBR — flagged but can't quantify
- Review leans heavily on adoption theme (3 of 4 findings). Could be genuine dominant issue or reviewer pattern-matching

---

## Delta Summary Across All Iterations

| Dimension | Iteration 1 | Iteration 2 | Iteration 3 |
|-----------|-------------|-------------|-------------|
| Finding count | 5 | 5 | 4 |
| Org-level synthesis | Missing | Added | Tighter, adds inflection framing |
| Data Literacy gap | Not mentioned | Own finding (#5) | Folded into Finding #1 as evidence |
| Granularity | 112-day expt standalone | Folded into evidence | Pattern-level only |
| Questions | Open-ended | More specific | Actionable — suggest responses |
| Missing context | Not flagged | Not flagged | Flagged in Finding #2 |
| QMOS as model | In strengths | Lead strength | Lead strength + Alternate View tie |
| Multi-lens | Present | Present | Woven into findings naturally |
| Strategic lens | Present | Present | "Should we build this at all?" |
| ROI as theme | DS Platform noted | Finding #4 | Finding #4 with recommendation |

---

## What the Skill Does Well Now (vs. Original)

- **Primary methodology is anomaly scanning -> cross-section narrative**, not checklist-driven auditing
- **Strategic Lens** asks "is the team working on the right things?" — not just "are they executing well?"
- **Leadership Lenses** ensure findings matter to Head of Data, CEO, and Head of Product simultaneously
- **Strengths section** earns credibility and provides contrast
- **Org-Level Synthesis** gives the headline judgment
- **Severity and granularity guidance** prevent the review from being too shallow or too detailed
- **Actionable questions** suggest specific responses, not just name gaps

## Post-Iteration Addition: Operational Flags

**Date:** 2026-02-18

After the 3 iterations, applied the skill to produce a full list of operational observations. This revealed a gap: the skill had no home for specific, actionable items that don't rise to cross-section business themes.

### Evolution

1. **Initial scan:** 52 raw observations — too many, no filtering framework
2. **First framework (3 categories):** Meta-failure, Compounding neglect, Cross-team blind spot, Isolated miss → 22 flags
3. **Drop RAG callouts:** RAG mismatches are either evidence in business findings or self-review items. Dropped Meta-failure category → 14 flags
4. **Drop isolated misses:** Single-workstream items the owner already knows. If unfixed, they graduate to compounding neglect next month → 10 flags
5. **Drop context-dependent exclusion:** Unresolved ambiguities ARE flags — the ambiguity itself needs resolution. Route into existing categories.
6. **Tighten threshold:** Changed compounding neglect from 1+ month to 2+ weeks (monthly MBR cadence means 1 month is already a missed cycle)

### Final Framework

Two categories only:
- **Compounding neglect** (2+ weeks overdue, no acknowledgment) — reviewer adds value because owner hasn't self-corrected
- **Cross-team blind spot** (multi-team impact, visible in one section) — reviewer adds value because owner can't self-correct

### Key Design Decisions

- **RAG mismatches excluded** — too obvious, any reader catches these. If they matter for the business, they're evidence in a finding.
- **Isolated misses excluded** — contained, owner knows. They'll age into compounding neglect if unaddressed.
- **Context-dependent questions included** — if the MBR raises a question but doesn't answer it, the ambiguity is the flag. Routes into existing categories.
- **Target: 5-15 flags** — fewer than 5 means not scanning thoroughly; more than 15 means including noise.

## What the Skill Still Doesn't Do (Conscious Scope Boundaries)

- **Temporal comparison** — relies on having previous MBR, which may not be available
- **Quantitative ROI assessment** — can flag the absence of ROI framing but can't calculate it
- **Team capability assessment** — skill gaps, hiring, enablement noticed only if surfaced in MBR
- **Competitive context** — doesn't evaluate whether team priorities match market dynamics

These are scope boundaries, not gaps. The skill is an MBR review tool, not a team assessment framework.
