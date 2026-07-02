# BRAIN API Notes

Source extraction folder:

`/Users/nuthdanai/Desktop/02_Quant_Investment/WorldQuant_BRAIN_API_Documentation_Refresh_2026-07-02`

## Simulation Limits

- Successful simulations count against quota.
- Child simulations in multi-simulation responses count against quota.
- Re-simulating a previously existing alpha still counts against quota.
- Submission responses may include `X-Ratelimit-Limit`, `X-Ratelimit-Remaining`, and `X-Ratelimit-Reset`.

## Duplicate Simulation Avoidance

The full BRAIN simulation payload is hashed with sorted JSON keys. The hash includes:

- `type`
- all `settings`
- `regular` expression

If the hash exists in the local SQLite cache, the runner skips submission and reuses the cached `alpha_id`.

## Batch Behavior

- `auto` tries batch size 8 first when payloads are compatible.
- If the 8-item request is explicitly rejected, the runner tries 4-item requests.
- If a 4-item request is explicitly rejected, the runner falls back to single submissions for that chunk.
- Ambiguous transport errors and 5xx responses are not automatically retried as smaller batches, because the server may already have accepted the request.
- The runner only batches payloads with compatible `type`, `instrumentType`, `region`, `universe`, `delay`, and `language`.

## Login Behavior

- `brain-sim login --print-link` prints the Persona URL when BRAIN requires verification.
- `brain-sim login --notify-email <email>` sends the same URL by SMTP when configured, stores the link in `.brain_sim/latest_login_link.json`, and prints the challenge message.
- SMTP requires `BRAIN_SIM_SMTP_HOST`, `BRAIN_SIM_SMTP_FROM`, and optionally `BRAIN_SIM_SMTP_USER`, `BRAIN_SIM_SMTP_PASSWORD`, `BRAIN_SIM_SMTP_PORT`.
