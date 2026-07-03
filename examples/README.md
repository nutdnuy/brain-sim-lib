# brain-sim Examples

This folder contains beginner-first, Riskfolio-Lib-style tutorial notebooks and deterministic sample assets for learning `brain-sim`.

The tutorials are offline-safe by default. Live BRAIN sections are included, but notebook code only submits to WorldQuant BRAIN when `BRAIN_SIM_RUN_LIVE=1` is set.

## New To This?

Start here:

- [Tutorial 0 - Start Here For Beginners](Tutorial%200%20-%20Start%20Here%20For%20Beginners.ipynb)

This notebook avoids login, live BRAIN calls, API classes, and batch internals. It only explains the core workflow: Excel input, simulation output, summary review, and the first live command to run later.

Recommended beginner path:

1. Tutorial 0 - Start Here For Beginners
2. Tutorial 1 - Installation And Project Tour
3. Tutorial 9 - Simulation Settings Deep Dive
4. Tutorial 10 - Data Fields And Field Types
5. Tutorial 3 - Excel Alpha Queue And Payloads
6. Tutorial 4 - Live Excel Batch Simulation
7. Tutorial 6 - Duplicate Cache And Re-Runs
8. Tutorial 7 - Results Raw Logs And Recordsets

## Settings And Data Fields Path

Use this path before running large batches:

1. Read the [settings and data fields reference](../docs/brain-settings-and-datafields.md).
2. Open [Tutorial 9 - Simulation Settings Deep Dive](Tutorial%209%20-%20Simulation%20Settings%20Deep%20Dive.ipynb).
3. Open [Tutorial 10 - Data Fields And Field Types](Tutorial%2010%20-%20Data%20Fields%20And%20Field%20Types.ipynb).
4. Only then prepare the Excel queue in Tutorial 3.

## Tutorials

| # | Tutorial | Main features | Assets |
|---|---|---|---|
| 0 | [Tutorial 0 - Start Here For Beginners](Tutorial%200%20-%20Start%20Here%20For%20Beginners.ipynb) | plain-English workflow, sample Excel preview, summary CSV preview, first safe live commands | [tutorial_04_live_alphas.xlsx](data/tutorial_04_live_alphas.xlsx), [tutorial_04_live_offline_summary.csv](expected/tutorial_04_live_offline_summary.csv) |
| 1 | [Tutorial 1 - Installation And Project Tour](Tutorial%201%20-%20Installation%20And%20Project%20Tour.ipynb) | editable install, CLI help, repo layout, ignored safety paths | - |
| 2 | [Tutorial 2 - Login And Persona Verification](Tutorial%202%20-%20Login%20And%20Persona%20Verification.ipynb) | credentials format, Persona link, SMTP notification, cookie reload | safe local demo artifacts |
| 3 | [Tutorial 3 - Excel Alpha Queue And Payloads](Tutorial%203%20-%20Excel%20Alpha%20Queue%20And%20Payloads.ipynb) | Excel schema, settings overrides, metadata, payload hashing, validation errors | [tutorial_03_mixed_settings.xlsx](data/tutorial_03_mixed_settings.xlsx), [tutorial_03_invalid_missing_expression.xlsx](data/tutorial_03_invalid_missing_expression.xlsx) |
| 4 | [Tutorial 4 - Live Excel Batch Simulation](Tutorial%204%20-%20Live%20Excel%20Batch%20Simulation.ipynb) | live guarded CLI flow, `auto`/`8`/`4`/`1` batching, timeout settings | [tutorial_04_live_alphas.xlsx](data/tutorial_04_live_alphas.xlsx), [tutorial_04_live_offline_summary.csv](expected/tutorial_04_live_offline_summary.csv) |
| 5 | [Tutorial 5 - Batch Fallback Timeouts And Retry Queue](Tutorial%205%20-%20Batch%20Fallback%20Timeouts%20And%20Retry%20Queue.ipynb) | 8 -> 4 fallback, pending timeouts, retry queue review | [tutorial_05_fallback_alphas.xlsx](data/tutorial_05_fallback_alphas.xlsx), [tutorial_05_fallback_summary.csv](expected/tutorial_05_fallback_summary.csv) |
| 6 | [Tutorial 6 - Duplicate Cache And Re-Runs](Tutorial%206%20-%20Duplicate%20Cache%20And%20Re-Runs.ipynb) | SQLite cache, skipped duplicates, hash-changing rules | [tutorial_06_duplicate_alphas.xlsx](data/tutorial_06_duplicate_alphas.xlsx), [tutorial_06_second_run_summary.csv](expected/tutorial_06_second_run_summary.csv) |
| 7 | [Tutorial 7 - Results Raw Logs And Recordsets](Tutorial%207%20-%20Results%20Raw%20Logs%20And%20Recordsets.ipynb) | summary CSV, raw JSONL, alpha details, `pnl`/`sharpe` recordsets | [tutorial_07_recordset_alphas.xlsx](data/tutorial_07_recordset_alphas.xlsx), [tutorial_07_recordset_summary.csv](expected/tutorial_07_recordset_summary.csv) |
| 8 | [Tutorial 8 - Python API Workflow](Tutorial%208%20-%20Python%20API%20Workflow.ipynb) | `BrainAuth`, `BrainClient`, `BatchRunner`, `RunStore`, custom automation | [tutorial_08_api_alphas.xlsx](data/tutorial_08_api_alphas.xlsx) |
| 9 | [Tutorial 9 - Simulation Settings Deep Dive](Tutorial%209%20-%20Simulation%20Settings%20Deep%20Dive.ipynb) | UI setting labels, `SimulationSettings`, payload settings, beginner rules | [tutorial_09_settings_examples.xlsx](data/tutorial_09_settings_examples.xlsx) |
| 10 | [Tutorial 10 - Data Fields And Field Types](Tutorial%2010%20-%20Data%20Fields%20And%20Field%20Types.ipynb) | Data Explorer checklist, Matrix data field, Vector data field, Group data field, operator matching | [tutorial_10_datafield_examples.xlsx](data/tutorial_10_datafield_examples.xlsx) |

## Run Locally

Install the project in editable mode:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pip install notebook
```

Open the examples:

```bash
jupyter notebook examples
```

## Live BRAIN Runs

Live examples consume WorldQuant BRAIN simulation quota and require cookies from `brain-sim login`.

Run live notebook cells only after you intentionally enable them:

```bash
export BRAIN_SIM_RUN_LIVE=1
jupyter notebook examples
```

Keep credentials outside notebooks. Use `~/.brain_credentials` or `brain-sim login --prompt`, and never commit `.brain_sim/`, `runs/`, or `examples/runs/`.
