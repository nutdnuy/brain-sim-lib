# brain-sim

Professional Python library and CLI for WorldQuant BRAIN alpha simulation.

## Install

```bash
cd /Users/nuthdanai/Desktop/02_Quant_Investment/brain-sim-lib
/Users/nuthdanai/.local/bin/python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Credentials

Store credentials in `~/.brain_credentials` as:

```json
["email@example.com", "password"]
```

The library reads credentials only for authentication. It stores the resulting cookie jar in `.brain_sim/cookies.json`.

## Login Mode 1: Email The Verification Link

```bash
export BRAIN_SIM_SMTP_HOST="smtp.example.com"
export BRAIN_SIM_SMTP_PORT="587"
export BRAIN_SIM_SMTP_FROM="sender@example.com"
export BRAIN_SIM_SMTP_USER="sender@example.com"
export BRAIN_SIM_SMTP_PASSWORD="smtp-password"

brain-sim login --notify-email "me@example.com" --credentials-file ~/.brain_credentials
```

If BRAIN requires Persona verification, the command sends the link to the email address when SMTP is configured and writes `.brain_sim/latest_login_link.json`.

## Login Mode 2: Print The Verification Link

```bash
brain-sim login --print-link --credentials-file ~/.brain_credentials
```

If BRAIN requires Persona verification, the command prints the link. Open it in a browser, complete verification, then run login again to save the cookie.

## Excel Simulation

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

Run as many as the local batch policy allows:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size auto --recordset pnl --recordset sharpe
```

Run fixed 8-item batches:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size 8
```

Run fixed 4-item batches:

```bash
brain-sim simulate-excel alphas.xlsx --batch-size 4
```

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

## Test

```bash
pytest
```

Unit tests use fake HTTP responses and never call the live WorldQuant BRAIN API.
