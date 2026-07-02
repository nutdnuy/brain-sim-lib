# brain-sim

Professional Python library and CLI for running WorldQuant BRAIN alpha simulations from Excel.

`brain-sim` focuses on a narrow production workflow: authenticate once, submit alpha expressions in safe batches, avoid duplicate submissions, preserve raw API responses, and export reviewable run artifacts.

> This is an unofficial research tool. It is not affiliated with, endorsed by, or maintained by WorldQuant or WorldQuant BRAIN.

## Features

- BRAIN login with Persona verification link support.
- Two login modes: print the verification link or email it through SMTP.
- Excel-driven alpha simulation.
- Batch policy for `8`, `4`, `1`, or `auto` batch sizing.
- Automatic fallback from rejected multi-submit payloads to smaller batches.
- Local duplicate protection through a SQLite simulation cache.
- Raw submit/poll JSONL logs for auditability.
- Summary CSV and retry queue outputs for failed, pending, and timed-out simulations.
- Optional alpha detail and recordset capture.
- Unit tests use fake HTTP responses and do not call the live BRAIN API.

## Install

```bash
git clone https://github.com/nutdnuy/brain-sim-lib.git
cd brain-sim-lib
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Check the CLI:

```bash
brain-sim --version
brain-sim --help
```

## Credentials

Create `~/.brain_credentials`:

```json
["email@example.com", "password"]
```

The credential file is read only during login. Runtime cookies are stored locally in `.brain_sim/cookies.json`, which is ignored by git.

## Login

Print the Persona verification link:

```bash
brain-sim login --print-link --credentials-file ~/.brain_credentials
```

If BRAIN requires Persona verification, open the printed link, complete verification, then run the same login command again to save cookies.

Email the Persona verification link:

```bash
export BRAIN_SIM_SMTP_HOST="smtp.example.com"
export BRAIN_SIM_SMTP_PORT="587"
export BRAIN_SIM_SMTP_FROM="sender@example.com"
export BRAIN_SIM_SMTP_USER="sender@example.com"
export BRAIN_SIM_SMTP_PASSWORD="smtp-password"

brain-sim login --notify-email "me@example.com" --credentials-file ~/.brain_credentials
```

## Excel Format

Required column:

- `expression`

Optional columns:

- `id`
- `region`
- `universe`
- `delay`
- `decay`
- `neutralization`
- `truncation`
- `maxTrade`
- `pasteurization`
- `testPeriod`
- `unitHandling`
- `nanHandling`
- `language`
- `visualization`

Default simulation settings are conservative USA equity settings unless overridden by the Excel row.

## Simulate

Live BRAIN simulations require saved cookies from `brain-sim login` and consume WorldQuant BRAIN simulation quota.

Run automatic batching:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size auto
```

Run fixed 8-item or 4-item batches:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size 8
brain-sim simulate-excel alphas.xlsx --batch-size 4
```

Fetch extra recordsets after successful simulation:

```bash
brain-sim simulate-excel alphas.xlsx --recordset pnl --recordset sharpe
```

Use a longer polling timeout for busy BRAIN queues:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size 4 --poll-timeout-seconds 1800
```

## Examples

Start with the tutorial suite:

- [Examples index](examples/README.md)
- [Tutorial 1 - Installation And Project Tour](examples/Tutorial%201%20-%20Installation%20And%20Project%20Tour.ipynb)
- [Tutorial 2 - Login And Persona Verification](examples/Tutorial%202%20-%20Login%20And%20Persona%20Verification.ipynb)
- [Tutorial 3 - Excel Alpha Queue And Payloads](examples/Tutorial%203%20-%20Excel%20Alpha%20Queue%20And%20Payloads.ipynb)
- [Tutorial 4 - Live Excel Batch Simulation](examples/Tutorial%204%20-%20Live%20Excel%20Batch%20Simulation.ipynb)
- [Tutorial 5 - Batch Fallback Timeouts And Retry Queue](examples/Tutorial%205%20-%20Batch%20Fallback%20Timeouts%20And%20Retry%20Queue.ipynb)
- [Tutorial 6 - Duplicate Cache And Re-Runs](examples/Tutorial%206%20-%20Duplicate%20Cache%20And%20Re-Runs.ipynb)
- [Tutorial 7 - Results Raw Logs And Recordsets](examples/Tutorial%207%20-%20Results%20Raw%20Logs%20And%20Recordsets.ipynb)
- [Tutorial 8 - Python API Workflow](examples/Tutorial%208%20-%20Python%20API%20Workflow.ipynb)

The notebooks cover installation, login, Excel schemas, payload hashing, live guarded batch simulation, fallback behavior, duplicate cache, output artifacts, recordsets, and Python API automation.

Notebook code is offline-safe by default. Live BRAIN cells run only when `BRAIN_SIM_RUN_LIVE=1` is set and still require cookies from `brain-sim login`.

## Batch Policy

`auto` tries larger compatible batches first:

1. Submit compatible groups of 8.
2. If BRAIN explicitly rejects the multi-submit payload, split into 4.
3. If a 4-item request is explicitly rejected, split into singles.

Transport errors and ambiguous server errors are preserved for review instead of blindly resubmitting, because the server may already have accepted the simulation.

## Output

Each run folder contains:

- `manifest.json`
- `simulation_cache.sqlite`
- `raw/submit-*.jsonl`
- `raw/poll-*.jsonl`
- `alphas/<alpha_id>.json`
- `recordsets/<alpha_id>/<recordset>.json`
- `summary.csv`
- `retry_queue.jsonl`

`summary.csv` includes the row id, alpha hash, status, alpha id, simulation location, core metrics, check summaries, and error text.

`retry_queue.jsonl` preserves the original payload, row metadata, alpha id when known, and simulation location when BRAIN accepted the request but polling did not complete.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
```

Build a local package:

```bash
python -m build
```

## Safety

Do not commit:

- `.brain_sim/`
- `runs/`
- `.venv/`
- `dist/`
- credential files such as `~/.brain_credentials`

These paths are excluded by `.gitignore`.
