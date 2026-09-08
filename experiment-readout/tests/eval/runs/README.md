# Captured runs

One directory per run id. `probe02/` is the real measured run described in the
top-level README (2 cases with-skill, 1 baseline, 4 triggering prompts).

Layout:
```
<run-id>/
  with/<case_id>.jsonl          stream-json transcript, skill available
  without/<case_id>.jsonl       stream-json transcript, --safe-mode (baseline)
  triggering/<prompt_id>.jsonl  one per trigger prompt
  prompts/<case_id>.txt         the exact prompt sent
  scorecard.json / .txt         machine cells + 12-point rollup
  judge_queue.json              cells needing the LLM judge
  human_queue.json              cells needing a human
  human_labels.json             YOU create this (see PROCEDURE_HUMAN.md step 3)
```

Rescore existing transcripts for free after a check-logic change:
`./run_eval.sh --score-only <run-id>`
