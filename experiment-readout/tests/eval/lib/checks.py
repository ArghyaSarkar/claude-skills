"""Machine checks for the Process and Output axes.

DIVISION OF LABOUR between this module and the LLM judge
--------------------------------------------------------
This module owns everything that can be decided by a rule without taste:
verdict tokens, gate enumeration, numeric tolerances, and the HIGH-PRECISION
half of leak detection. The judge (see rubric/) owns only what genuinely needs
reading comprehension: whether a hedge is a directional peek, whether an as-of
caveat is real calibration or throat-clearing, and whether the prescribed format
is met in spirit.

Every check returns a verdict in {PASS, FAIL, UNKNOWN}. UNKNOWN is a first-class
outcome, not a disguised FAIL: it means "this needs the judge or a human", and it
propagates to the scorecard as an explicitly unscored cell. Anthropic's agent-eval
guidance recommends giving graders an abstain option for exactly this reason --
a grader forced to guess produces a confident number that is worse than a gap.

stdlib only.
"""

import re

VERDICTS = ["INVALID-DESIGN", "INVALID-SRM", "INVALID-IMMATURE",
            "NO-SHIP", "SHIP", "INCONCLUSIVE"]

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

# ---------------------------------------------------------------------------
# vocabulary
# ---------------------------------------------------------------------------
GATE_PHRASES = {
    "design_integrity": [r"design integrity", r"sealed", r"seal date",
                         r"brief was (?:written|sealed)", r"pre-?registrat"],
    # Prose variants matter: Template C forbids jargon, so a Slack message says
    # "the split came out 1,620 vs 1,380 against a designed 50/50" and never the
    # token "SRM". A literal-only list put the SRM discussion 2,000 characters
    # later than it actually was and failed the gate-order check on all five runs.
    "srm": [r"\bSRM\b", r"sample ratio mismatch", r"ratio mismatch",
            r"\bsplit\b", r"50/50", r"randomis|randomiz",
            r"\bassignment\b", r"arm split",
            r"assignment (?:is |was )?(?:skew|imbalanc)"],
    "maturity": [r"matur", r"immature", r"28[- ]day (?:window|metric)",
                 r"not (?:yet )?(?:fully )?(?:complete|observed|elapsed)",
                 r"follow-?up (?:window|time)"],
}

LIFT_CONTEXT = (r"(lift|uplift|effect size|treatment effect|improvement|"
                r"\bwin(?:ning)?\b|completed[_ ]orders (?:is|are|were|went)|"
                r"treatment (?:beat|outperform|is (?:up|higher|better)))")

GUARDRAIL_CONCLUSION = (
    r"cancel[_ ]?rate[^.]{0,80}?(no worse|unchanged|flat|fine|healthy|safe|"
    r"within (?:the )?(?:limit|threshold|tolerance)|not (?:breached|worse)|held|"
    r"looks (?:ok|okay|good|fine))"
)

# Hedged directional peeks. These are SOFT signals: matched here, adjudicated by
# the judge, because the same words can appear in a sentence that REFUSES to peek
# ("I am not going to give you a directional read").
HEDGE_PATTERNS = [
    r"directional(?:ly)?", r"for context", r"for what it'?s worth", r"\bFWIW\b",
    r"if (?:the )?SRM (?:were|was) fixed", r"if we (?:ignore|set aside|park)",
    r"at least looks", r"early (?:signal|read|indication)", r"would have been",
    r"eyeball", r"trending", r"raw numbers (?:do|are|show)", r"off the record",
    r"unofficially", r"purely indicative", r"just so you know, the",
    r"the numbers themselves",
]

ASOF_ASSUMPTION_MARKERS = [
    r"assum", r"unknown", r"not (?:present |available |recorded )?in the (?:csv|data|file|extract)",
    r"lower bound", r"conservative", r"cannot (?:know|tell|determine)",
    r"no (?:extract|as-?of|snapshot) date", r"if the (?:extract|data) (?:was|were)",
    r"we don'?t know when",
]
ASOF_RESOLVER_MARKERS = [
    r"extract date", r"as-?of date", r"when the (?:data|extract) was (?:pulled|taken|generated)",
    r"snapshot date", r"pull date", r"confirm (?:the )?(?:date|as-?of)",
    r"ask (?:the )?(?:data|analytics|owner)", r"query (?:the )?(?:warehouse|source)",
]

# A sentence that DECLARES the suppression is the opposite of a leak, but it
# necessarily contains every forbidden word ("No lift, p-value, confidence
# interval, or guardrail verdict for completed_orders_28d"). Without this the
# detector penalises the skill precisely for complying.
SUPPRESSION_DECLARATION = re.compile(
    r"\b(?:no|zero|none|without|omitt|withheld|suppress|not run|NOT_RUN|"
    r"not (?:computed|reported|shown|available|quoted|disclosed)|"
    r"will not (?:report|share|compute|quote)|cannot (?:report|quote|share))\b"
    r"[^.]{0,60}?\b(?:lift|p-?value|confidence interval|\bCI\b|guardrail|"
    r"direction|effect|conclusion)",
    re.IGNORECASE)

SENT_SPLIT = re.compile(r"(?<=[.!?;\n])\s+")


def _sentences(text):
    return [s for s in SENT_SPLIT.split(text or "") if s.strip()]


def _any(pats, text, flags=re.IGNORECASE):
    return any(re.search(p, text or "", flags) for p in pats)


def _found(pats, text, flags=re.IGNORECASE):
    return [p for p in pats if re.search(p, text or "", flags)]


# ---------------------------------------------------------------------------
# numeric allowlist: numbers a BLOCKED response is legitimately allowed to cite
# ---------------------------------------------------------------------------
def allowlisted_numbers(golden):
    """Numbers that are part of the validity story, not the suppressed conclusion.

    An SRM readout MUST quote a p-value (the chi-squared one) and MUST quote the
    observed split. So 'contains a p-value' cannot itself be the leak rule --
    the leak rule has to know which numbers are legitimate for this case.
    """
    ref = golden["reference"]
    ok = set()
    obs = ref["srm"]["observed"]
    total = float(sum(obs.values()))
    for v in obs.values():
        ok.add("%d" % v)
        if total:
            ok.add("%.1f" % (100.0 * v / total))
            ok.add("%.0f" % round(100.0 * v / total))
    for v in ref["srm"]["expected"].values():
        ok.add("%.0f" % round(v))
        ok.add("%d" % int(v))
    ok.update({
        "3", "3.0",                        # the MDE
        "1", "0.01", "1.0",                # the 1pp guardrail threshold
        "28", "14", "50", "0", "0.0", "100",
        "%.1f" % ref["srm"]["chi2"], "%.0f" % round(ref["srm"]["chi2"]),
        "%d" % ref["exposure_span_days"],
        "%d" % golden["asof"]["metric_window_days"],
        "0.001", "0.05",                   # the two alphas
    })
    tg = golden.get("truncation_gradient") or {}
    if "corr_cohort_index_vs_mean" in tg:
        c = tg["corr_cohort_index_vs_mean"]
        for f in ("%.3f", "%.2f", "%.1f"):
            ok.add(f % c); ok.add(f % abs(c))
    m = golden.get("maturity") or {}
    for key in ("mature_share", "n_mature", "n_total"):
        if key in m:
            ok.add(str(m[key])); ok.add("%.0f" % (100 * m[key]) if key == "mature_share" else str(m[key]))
    return ok


NUM_TOKEN = re.compile(r"[-+]?\d+(?:\.\d+)?")
PVAL = re.compile(r"\bp[-\s]?(?:value)?\s*[=<>~]{1,2}\s*([0-9.eE-]+)", re.IGNORECASE)
CI_NUM = re.compile(r"(95\s*%\s*CI|confidence interval)[^.]{0,60}?[-+]?\d", re.IGNORECASE)
PCT_LIFT = re.compile(
    r"[-+]?\d+(?:\.\d+)?\s*%\s*(?:relative\s*)?"
    r"(?:lift|uplift|increase|decrease|improvement|effect|higher|lower|better|worse)",
    re.IGNORECASE)
LIFT_NUM = re.compile(
    LIFT_CONTEXT + r"[^.]{0,60}?[-+]?\d+(?:\.\d+)?\s*%", re.IGNORECASE)


def check_suppression(text, golden):
    """The highest-value negative check.

    When any validity gate failed, BOTH the lift and the guardrail conclusion
    must be absent (Amendment 1). Returns (verdict, hard_hits, soft_hits).
    """
    if not golden["conclusions_suppressed"]:
        return UNKNOWN, [], []          # not applicable; scored by numbers instead

    ok = allowlisted_numbers(golden)
    hard, soft = [], []

    # Numbers belonging to a VALIDITY finding are legitimate: the SRM's own
    # chi-squared p-value, the observed split, the cohort-gradient correlation and
    # its p-value. Only CONCLUSION numbers (lift, guardrail) are suppressed. The
    # context window spans the previous sentence too, because a real report
    # routinely names the finding in one sentence and quotes its statistic in the
    # next.
    VALIDITY_CTX = (r"srm|chi|split|ratio|assignment|cohort|corr|gradient|"
                    r"matur|truncat|alpha|design|seal|randomis|randomiz|"
                    r"exposure|follow-?up|integrity")
    sents = _sentences(text)
    for i, s in enumerate(sents):
        window = ((sents[i - 1] + " ") if i else "") + s
        srm_ctx = bool(re.search(VALIDITY_CTX, window, re.IGNORECASE))

        if SUPPRESSION_DECLARATION.search(s):
            continue          # complying, not leaking

        # A percentage is only a leak if it is not one of the case's legitimate
        # numbers. "could not have detected a 3% effect" cites the MDE.
        pct_leak = None
        for m in PCT_LIFT.finditer(s):
            num = NUM_TOKEN.search(m.group(0))
            if num and num.group(0).lstrip("+-") not in ok:
                pct_leak = m.group(0)
                break
        if pct_leak:
            hard.append(("percent-lift phrase '%s'" % pct_leak.strip(), s.strip()[:180]))
        elif LIFT_NUM.search(s) and not srm_ctx:
            hard.append(("number in a lift sentence", s.strip()[:180]))

        for m in PVAL.finditer(s):
            if m.group(1).strip(".") not in ok and not srm_ctx:
                hard.append(("p-value outside the SRM context", s.strip()[:180]))

        if CI_NUM.search(s) and not srm_ctx:
            hard.append(("confidence interval reported", s.strip()[:180]))

        if re.search(GUARDRAIL_CONCLUSION, s, re.IGNORECASE):
            hard.append(("guardrail conclusion on invalid data", s.strip()[:180]))

        for p in HEDGE_PATTERNS:
            if re.search(p, s, re.IGNORECASE):
                soft.append((p, s.strip()[:180]))

    if hard:
        return FAIL, hard, soft
    if soft:
        return UNKNOWN, hard, soft      # judge adjudicates the hedges
    return PASS, hard, soft


# ---------------------------------------------------------------------------
# Output axis sub-checks
# ---------------------------------------------------------------------------
def verdicts_present(text):
    """Which taxonomy tokens are asserted, without substring collisions.

    "SHIP" is a substring of "NO-SHIP" and also of the ordinary English word
    "ship", so a naive search reports SHIP on a response whose verdict line reads
    "NO-SHIP ... no ship decision is available". Longest-token-first with
    span-masking, plus a word boundary, fixes both.
    """
    # "SHIP" is also an ordinary English verb, so it is the one token matched
    # case-sensitively: "no ship decision is available" must not register the SHIP
    # verdict. Every other token is a distinctive hyphenated form and is safe to
    # match case-insensitively.
    AMBIGUOUS = {"SHIP"}
    t = text or ""
    found = []
    for v in sorted(VERDICTS, key=len, reverse=True):
        pat = r"(?<![A-Za-z-])" + re.escape(v) + r"(?![A-Za-z-])"
        flags = 0 if v in AMBIGUOUS else re.IGNORECASE
        m = re.search(pat, t, flags)
        if m:
            found.append(v)
            t = t[:m.start()] + ("_" * (m.end() - m.start())) + t[m.end():]
            # mask every occurrence so a later, shorter token cannot match inside it
            while True:
                m2 = re.search(pat, t, flags)
                if not m2:
                    break
                t = t[:m2.start()] + ("_" * (m2.end() - m2.start())) + t[m2.end():]
    return [v for v in VERDICTS if v in found]


def check_verdict(text, golden):
    want = golden["verdict"]
    if want is None:
        return UNKNOWN, "case has no single verdict (power task)"
    present = verdicts_present(text)
    if want not in present:
        return FAIL, "golden verdict %s absent; found %s" % (want, present or "none")
    others = [v for v in present if v != want]
    if others:
        # a response may legitimately enumerate the taxonomy; require the golden
        # verdict to be the one actually asserted on a verdict-labelled line
        for line in (text or "").splitlines():
            if re.search(r"verdict", line, re.IGNORECASE) and re.search(
                    re.escape(want), line, re.IGNORECASE):
                return PASS, "asserted on a verdict line (also mentions %s)" % others
        return UNKNOWN, "multiple verdicts present %s; which is asserted is unclear" % present
    return PASS, "verdict %s asserted, no competing verdict" % want


def check_enumeration(text, golden):
    """Amendment 1: EVERY validity failure must be named, not just the first."""
    fails = golden["all_validity_failures"]
    if not fails:
        return UNKNOWN, "no validity failures to enumerate"
    missing = [g for g in fails if not _any(GATE_PHRASES[g], text)]
    if missing:
        return FAIL, "failed to surface %s (found %s of %d)" % (
            missing, len(fails) - len(missing), len(fails))
    return PASS, "all %d validity failures enumerated: %s" % (len(fails), fails)


def check_numbers_present(text, golden, tol=0.25):
    """For NON-suppressed cases the conclusion numbers are required and must match."""
    if golden["conclusions_suppressed"]:
        return UNKNOWN, "conclusions suppressed; scored by check_suppression instead"
    rel = golden["reference"]["lift"]["rel_diff"] * 100.0
    nums = [float(x) for x in NUM_TOKEN.findall(text or "")]
    near = [x for x in nums if abs(x - rel) <= max(abs(rel) * tol, 0.4)]
    if not near:
        return FAIL, "relative lift ~%+.1f%% not found in the response" % rel
    return PASS, "relative lift ~%+.1f%% reported (matched %s)" % (rel, near[:3])


def check_asof_honesty(text, golden):
    """Amendment 2: partial maturity, and a confident answer is the WORSE answer.

    Three distinct failure modes are separated here, because they need different
    fixes:
      * no caveat at all                  -> FAIL (asserted the unknowable)
      * says nothing is mature, when the
        golden says PARTIAL               -> FAIL (confidently wrong, not merely
                                            overconfident)
      * caveated but does not name what
        would settle it                   -> UNKNOWN (judge)
    """
    m = golden["maturity"]
    if m["branch"] == "full":
        return UNKNOWN, "maturity passes here; nothing to caveat on this axis"

    # A zero-maturity claim is a QUANTITY claim. Earlier drafts matched the bare
    # words "nothing"/"none" near "matur", which fired on the innocuous
    # "would close the maturity gate, but it does nothing for the SRM". The
    # quantity must now be adjacent and numeric-or-explicit.
    # (?<![\d.]) is load-bearing: without it "80% mature" matches as "0% mature"
    # and "1620/1380" matches as "0/1380". Both occurred on real transcripts and
    # both produced spurious O5 failures.
    ZERO = (r"(?:(?<![\d.])0(?:\.0+)?\s*%|(?<![\d.])0\s*/\s*[\d,]+"
            r"|(?<![\d.])0\s+of\s+[\d,]+|\bzero\b"
            r"|none of the (?:users?|cohort)|no users?|not a single user)")
    # A DENIAL of zero maturity is the correct answer, not a zero claim. The
    # skill legitimately writes "Partial maturity, not zero maturity", and an
    # earlier version of this check read that as the very error it is denying --
    # which turned a 5/5 criterion into a spurious 2/5 "NOT BINDING" flag.
    NEG = re.compile(r"(?:\bnot\b|n't\b|\brather than\b|\binstead of\b|"
                     r"\bfar from\b|\bnever\b|\bisn'?t\b|\baren'?t\b|"
                     r"\bno longer\b|\bas opposed to\b)\s*$", re.IGNORECASE)
    pat = (ZERO + r"[^.]{0,25}?matur"
           r"|matur\w*(?:\s+(?:share|rate|fraction|proportion))?"
           r"[^.]{0,15}?(?:is|are|=|:)\s*" + ZERO)
    zero_claim = None
    for zm in re.finditer(pat, text or "", re.IGNORECASE):
        lookback = (text or "")[max(0, zm.start() - 24):zm.start()]
        if NEG.search(lookback):
            continue          # "partial maturity, NOT zero maturity"
        zero_claim = zm
        break
    if m["branch"] == "partial" and zero_claim:
        return FAIL, ("claims nothing is mature, but %.0f%% of users ARE mature -- "
                      "this is confidently wrong, not merely overconfident"
                      % (100 * m["mature_share"]))

    flagged = _found(ASOF_ASSUMPTION_MARKERS, text)
    if not flagged:
        return FAIL, "maturity stated without flagging the as-of as an assumption"

    resolver = _found(ASOF_RESOLVER_MARKERS, text)
    if not resolver:
        return UNKNOWN, ("caveated (%s) but does not name the input that would "
                         "settle it" % flagged[:2])

    if m["branch"] == "partial":
        mech = re.search(r"differential|early (?:vs\.? |and )?late|"
                         r"cohort[^.]{0,40}follow|follow-?up time|"
                         r"unequal (?:follow|exposure)", text or "", re.IGNORECASE)
        if not mech:
            return UNKNOWN, ("caveated, but does not name differential follow-up "
                             "between cohorts as the failure mechanism")
        return PASS, "partial maturity, caveated, mechanism and resolver both named"
    return PASS, "caveated as an assumption and names the resolving input"


def check_truncation_gradient(text, golden):
    """Amendment 2's new dimension: did the response check the cohort gradient?

    This is the strongest maturity diagnostic available because it needs NO as-of
    date -- it is computable from the CSV alone. Two readings are correct, and
    which one is correct depends on the data:
      gradient present -> positive evidence of truncation
      gradient absent  -> a DATA INTEGRITY concern, because a truncated N-day
                          metric MUST show late cohorts lower
    """
    tg = golden["truncation_gradient"]
    if not tg["graded"]:
        return UNKNOWN, "maturity passes; the gradient check is not required here"

    # A gradient check means grouping the metric BY exposure date/cohort and
    # comparing. The bare word "cohort" is not that -- an earlier version of this
    # check passed a response that only said "the cohort becomes readable on
    # 2026-08-24", which is a date, not a diagnostic.
    checked = re.search(
        r"by (?:exposure )?(?:date|cohort|day)\b"
        r"|(?:cohort|per-?day|daily)[- ]?(?:level )?(?:mean|average|value|metric)"
        r"|(?:mean|average)[^.]{0,25}(?:by|per)[^.]{0,15}(?:cohort|exposure|date|day)"
        r"|(?:late|later|last)[^.]{0,40}(?:cohort|exposure)[^.]{0,30}"
        r"(?:lower|less|below|declin|drop)"
        r"|early (?:vs\.?|and) late"
        r"|(?:truncation |cohort )?gradient"
        r"|trend (?:by|across) (?:date|cohort|exposure)",
        text or "", re.IGNORECASE)
    if not checked:
        return FAIL, ("did not check the metric by exposure cohort -- the one "
                      "maturity diagnostic that needs no as-of date")

    if tg["branch"] == "gradient_present":
        right = re.search(r"(late|later|last)[^.]{0,50}(lower|less|below|declin|drop)"
                          r"|(declin|falls|drops)[^.]{0,40}cohort"
                          r"|consistent with truncation|confirms truncation",
                          text or "", re.IGNORECASE)
        if right:
            return PASS, "checked the gradient and read it as evidence of truncation"
        return UNKNOWN, "checked cohorts but the reading of the gradient is unclear"

    # gradient absent -> the harder, better reading
    integrity = re.search(
        r"\bdata (?:integrity|quality)\b|\binconsisten|does not (?:show|behave)"
        r"|\bflat\b|no (?:gradient|trend|relationship|dependence)"
        r"|would expect[^.]{0,60}(?:lower|declin)|not what[^.]{0,40}truncat"
        r"|\bsuspicious\b|cannot be (?:truncation|explained by truncation)",
        text or "", re.IGNORECASE)
    if integrity:
        return PASS, ("checked the gradient, found it flat, and raised the "
                      "data-integrity reading")
    return UNKNOWN, ("checked cohorts but did not surface the data-integrity "
                     "implication of a flat gradient")


def check_claim_vs_data(text, golden):
    cvd = golden["claim_vs_data"]
    if not cvd["graded"]:
        return UNKNOWN, "the ask makes no duration claim"
    span = cvd["actual_span_days"]
    said_span = re.search(r"\b%d\b\s*(?:day|d\b)|two weeks|fortnight" % span,
                          text or "", re.IGNORECASE)
    contradicted = re.search(
        r"(not|isn'?t|rather than|actually|in fact|contrary|mismatch|"
        r"contradict|only|despite|but the data|claim)", text or "", re.IGNORECASE)
    if said_span and contradicted:
        return PASS, "checked the '%s' claim against the %dd span" % (
            cvd["claimed_duration"], span)
    if said_span:
        return UNKNOWN, "states the %dd span but may not contest the claim" % span
    return FAIL, "did not check the '%s' claim against the data" % cvd["claimed_duration"]


def _marker_ok(marker, text):
    pats = marker["patterns"]
    kind = marker.get("kind", "any_of")
    if kind == "first_line":
        for line in (text or "").splitlines():
            if line.strip():
                return _any(pats, line)
        return False
    if kind == "all_of":
        return all(re.search(p, text or "", re.IGNORECASE) for p in pats)
    return _any(pats, text)


def message_body(text):
    """For Template C, isolate the PM-FACING draft from the agent's own wrapper.

    A Slack-draft response is two documents in one: the message the PM will read,
    and a trailing block addressed to the analyst ("**Process & references:**
    ... Consulted references/gates.md ..."). Template C forbids process narration
    *in the message*; it says nothing about the agent's covering note. Scanning
    the whole response conflated the two and failed all five runs of the Slack
    case for a citation sitting at char 4321 of 4509, after a --- separator.

    Heuristic, and deliberately conservative: cut at an explicit process/
    references heading, else at a trailing fence or separator in the last third.
    Returns (body, confident) -- when extraction is not confident the caller
    should decline to judge rather than guess.
    """
    t = text or ""

    # A FENCED draft is the only boundary worth trusting. Agents wrap the
    # PM-facing message in ``` and put their own commentary outside it, so the
    # fence is an explicit author-supplied boundary rather than our guess.
    fences = [mm.start() for mm in re.finditer(r"```", t)]
    if len(fences) >= 2:
        # Start AFTER the opening fence's own line, or the "first line" of the
        # body is the ``` marker (and any info string) rather than the message's
        # opening sentence.
        nl = t.find("\n", fences[0])
        start = (nl + 1) if (nl != -1 and nl < fences[-1]) else fences[0] + 3
        return t[start:fences[-1]], True

    # No fence: heading-based guessing is NOT reliable enough. Real responses put
    # analyst-facing gate tables under headings we did not anticipate
    # ("## What's behind the draft"), so a heuristic cut silently mis-attributes
    # forbidden elements to the message. Decline instead, and let the judge read
    # it -- the judge is validated at 6/6 sensitivity, the heuristic is not.
    return t, False


def check_format(text, cfg, suppressed=False, task="readout"):
    """Structural conformance against the TASK's template.

    Format conformance is per-template or it is nothing: Template C (Slack)
    forbids the markdown gate table that Template A requires, so one shared
    marker set fails a correct answer. v1.1 of this check did exactly that and
    scored the Slack case 2/4 for following its own template.
    """
    spec = (cfg.get("by_task") or {}).get(task)
    if spec is None:
        # backwards compatibility with the flat v1.1 contract
        spec = {"required_markers": cfg.get("required_markers", []),
                "suppressed_only_markers": cfg.get("suppressed_only_markers", [])}
    required = list(spec.get("required_markers", []))
    if suppressed:
        required += spec.get("suppressed_only_markers", [])
    if not required:
        return UNKNOWN, "no format contract configured for task '%s'" % task

    forbidden = spec.get("forbidden_markers", [])
    scope, body_confident = text, True
    if forbidden:
        # Template C's rules are about the PM-FACING message. Both the positional
        # check and the forbidden checks are scoped to it, because a covering
        # note above the draft is not a violation of "bottom line first".
        scope, body_confident = message_body(text)
        if not body_confident:
            return UNKNOWN, ("template %s: the PM-facing draft is not fenced, so "
                             "its boundary cannot be located reliably. Both the "
                             "bottom-line-first and forbidden-element checks "
                             "depend on that boundary, so this is routed to the "
                             "judge rather than guessed"
                             % spec.get("template", task))

    missing = [m["name"] for m in required if not _marker_ok(m, scope)]
    violated = [m["name"] for m in forbidden if _any(m["patterns"], scope)]

    if missing or violated:
        bits = []
        if missing:
            bits.append("missing %s" % missing)
        if violated:
            bits.append("used forbidden element(s) %s in the message body" % violated)
        return FAIL, "template %s: %s" % (spec.get("template", task), "; ".join(bits))
    return PASS, "template %s: all %d prescribed elements present" % (
        spec.get("template", task), len(required))


# ---------------------------------------------------------------------------
# Process axis signals (trace-observable)
# ---------------------------------------------------------------------------
def process_signals(obs, golden, text):
    """Four independent, individually-checkable step-quality signals.

    The arena awards "one point per step-quality signal", so this deliberately
    returns exactly four rather than one blended score.
    """
    sig = {}

    # P1 -- gate order respected in the narrative, and no conclusion before it
    #
    # The verdict line must be FIRST per the skill's own format, and it contains a
    # gate name ("INVALID-SRM"). Reading that as "the SRM gate was discussed before
    # the design gate" produced a false FAIL on a response that was correctly
    # ordered. So mask the verdict tokens and drop the mandated first line before
    # looking at order.
    # WHICH gates to check the order of.
    #
    # "Gate order respected" is a claim about the gates the answer actually
    # discusses. Template C (Slack) reports only the FAILING gates -- a passing
    # design_integrity has no business in a message to a PM -- so demanding that
    # design_integrity appear before srm there failed all five runs of a correct
    # case. The order that carries the lesson is the order of the failures.
    failures = golden.get("all_validity_failures") or []
    if len(failures) >= 2:
        order = [g for g in ["design_integrity", "srm", "maturity"] if g in failures]
    elif golden.get("task") == "readout":
        # a full readout must walk all three, so their order is observable
        order = ["design_integrity", "srm", "maturity"]
    else:
        sig["P1_gate_order"] = (UNKNOWN,
                                "fewer than two failing gates and not a full "
                                "readout; gate order is not observable here")
        order = []

    body = text or ""
    for v in sorted(VERDICTS, key=len, reverse=True):
        body = re.sub(r"(?<![A-Za-z-])" + re.escape(v) + r"(?![A-Za-z-])",
                      "#" * len(v), body, flags=re.IGNORECASE)
    lines = body.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip():
            body = "\n".join(lines[i + 1:])
            break
    pos = {}
    for g in order:
        idx = [m.start() for p in GATE_PHRASES[g]
               for m in re.finditer(p, body, re.IGNORECASE)]
        pos[g] = min(idx) if idx else None
    seen = [(g, pos[g]) for g in order if pos[g] is not None]
    ordered = all(seen[i][1] <= seen[i + 1][1] for i in range(len(seen) - 1))
    if not order:
        pass                      # already recorded as UNKNOWN above
    elif len(seen) < 2:
        sig["P1_gate_order"] = (UNKNOWN, "fewer than two gates discussed; order not observable")
    elif ordered:
        sig["P1_gate_order"] = (PASS, "gates checked appear in contract order: %s"
                                % [g for g, _ in seen])
    else:
        sig["P1_gate_order"] = (FAIL, "gates out of contract order -- positions %s"
                                % [(g, i) for g, i in seen])

    # P2 -- the skill's own scripts actually ran
    want = "power.py" if golden["task"] == "power" else "run_readout.py"
    if any(want in s for s in obs["scripts_run"]):
        sig["P2_scripts_invoked"] = (PASS, "%s executed" % want)
    elif obs["scripts_run"]:
        sig["P2_scripts_invoked"] = (UNKNOWN, "ran %s but not %s"
                                     % (obs["scripts_run"], want))
    else:
        sig["P2_scripts_invoked"] = (FAIL, "no skill script executed; statistics "
                                           "were improvised or eyeballed")

    # P3 -- references actually consulted / cited by name
    if obs["references_read"] and obs["references_named_in_text"]:
        sig["P3_references_cited"] = (PASS, "read %s and cited %s by name"
                                      % (obs["references_read"], obs["references_named_in_text"]))
    elif obs["references_read"]:
        sig["P3_references_cited"] = (UNKNOWN, "read %s but did not cite it by name"
                                      % obs["references_read"])
    else:
        sig["P3_references_cited"] = (FAIL, "no reference file was read")

    # P4 -- no improvised computation of the suppressed conclusion
    if obs["ad_hoc_stats_commands"]:
        sig["P4_no_improvisation"] = (
            FAIL, "hand-rolled statistics outside the skill's scripts: %s"
                  % obs["ad_hoc_stats_commands"][:2])
    elif golden["conclusions_suppressed"]:
        sig["P4_no_improvisation"] = (PASS, "no ad-hoc computation of the suppressed "
                                            "conclusion")
    else:
        sig["P4_no_improvisation"] = (PASS, "no ad-hoc statistics; used the skill's scripts")
    return sig
