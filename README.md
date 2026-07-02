# brain-sim

Professional Python library and CLI for WorldQuant BRAIN alpha simulation.

## Scope

- Login with Persona link printing or email notification.
- Build `/simulations` payloads from Excel or Python objects.
- Avoid exact duplicate simulations with a local SQLite hash cache.
- Submit simulations in batch size 8, batch size 4, or single fallback.
- Persist raw API responses, polling events, alpha details, recordsets, summaries, and retry queues.

## Install

```bash
cd /Users/nuthdanai/Desktop/02_Quant_Investment/brain-sim-lib
/Users/nuthdanai/.local/bin/python3.11 -m venv .venv
. .venv/bin/activate
python --version
python -m pip install -e ".[dev]"
```

## Credentials

Store credentials in `~/.brain_credentials` as:

```json
["email@example.com", "password"]
```

The library reads credentials only for authentication. It stores the resulting cookie jar in `.brain_sim/cookies.json`.
