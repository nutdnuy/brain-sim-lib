# BRAIN Simulation Settings And Data Fields

This page explains the settings shown in the WorldQuant BRAIN simulation UI and how those settings map to `brain-sim` Excel/API fields.

Use this page with:

- `examples/Tutorial 9 - Simulation Settings Deep Dive.ipynb`
- `examples/Tutorial 10 - Data Fields And Field Types.ipynb`

This is an unofficial learning reference. Treat live platform rules as the source of truth when BRAIN changes.

## Quick Mental Model

An Alpha expression is evaluated into a daily vector across a selected universe. BRAIN then applies simulation settings such as delay, neutralization, decay, truncation, pasteurization, NaN handling, and unit handling before producing portfolio weights, PnL, metrics, checks, and artifacts.

Changing settings changes the experiment. Do not compare two Alpha results unless the settings are comparable enough for the comparison to mean something.

## UI To brain-sim Mapping

| BRAIN UI label | brain-sim Excel/API field | Default in `SimulationSettings` | Type | Beginner meaning |
|---|---|---|---|---|
| Language | `language` | `FASTEXPR` | text | Expression language. Current tutorials use Fast Expression. |
| Instrument Type | `instrumentType` | `EQUITY` | text | Asset class. Current package defaults to equity simulation. |
| Region | `region` | `USA` | text | Country or regional market coverage. |
| Delay | `delay` | `1` | integer | Data timing. Delay 1 uses prior-day information for next-day trading. |
| Universe | `universe` | `TOP3000` | text | Stock set used in the simulation. Affects liquidity, coverage, and sub-universe checks. |
| Neutralization | `neutralization` | `SUBINDUSTRY` | text | Removes group-level exposure from the Alpha vector. |
| Decay | `decay` | `15` | integer | Smooths the Alpha vector through time. Can reduce turnover but can weaken fast signals. |
| Truncation | `truncation` | `0.08` | float | Caps extreme single-name weights before final portfolio construction. |
| Pasteurization | `pasteurization` | `ON` | text | Controls whether data outside the selected universe is treated as unavailable. |
| Unit Handling | `unitHandling` | `VERIFY` | text | Warns about incompatible units in expressions. |
| NaN Handling | `nanHandling` | `OFF` | text | Controls whether missing values are preserved or handled by platform rules. |
| Test Period | `testPeriod` | `P1Y6M` | text | Train/test split display inside in-sample review. |
| Max Trade | `maxTrade` | `ON` | text | Platform control for limiting trade size. The package passes it through as a setting. |
| Max Position | not implemented in `SimulationSettings` yet | not available | UI setting | Shown in the BRAIN UI screenshot. Add API support only after confirming exact API field name from live payloads. |
| Visualization | `visualization` | `False` | boolean | Controls whether visualization artifacts are requested. |

## Settings Explained

### `language`

Use `FASTEXPR` for standard WorldQuant BRAIN Fast Expression formulas. Do not mix Python syntax with Fast Expression syntax.

### `instrumentType`

The current library defaults to `EQUITY`. Keep this fixed unless the API documentation and your account explicitly support another instrument type.

### `region`

Region defines the market. It changes field availability, universe names, liquidity, calendar behavior, and evaluation context.

Beginner default: `USA`.

### `universe`

Universe defines which instruments are eligible. Larger universes improve breadth but can include less liquid names. Smaller universes are often more liquid but can make signals more crowded or harder to diversify.

Beginner default: `TOP3000`.

### `delay`

Delay controls when information is assumed to be tradable.

- `delay=1`: safer default for prior-day information.
- `delay=0`: same-day style work with stricter standards and higher risk of timing mistakes.

Beginner rule: use Delay 1 until you can explain why same-day timing is valid.

### `neutralization`

Neutralization removes average exposure inside a group. It is part of the Alpha definition, not a cosmetic setting.

Common levels:

- `MARKET`: removes broad market direction.
- `SECTOR`: keeps sector-relative effects.
- `INDUSTRY`: stronger peer comparison.
- `SUBINDUSTRY`: most granular common default.

Changing neutralization can make the same expression behave like a different Alpha.

### `decay`

Decay smooths the Alpha vector through time. Higher decay can lower turnover because target weights change more slowly, but it can weaken fast signals.

Beginner starting points:

- Short-horizon reversion: try low to medium decay.
- Slow fundamental signal: try medium to higher decay.
- Very sparse event field: inspect coverage first, then choose decay.

### `truncation`

Truncation caps extreme values and helps control concentration. It is not a substitute for a broad, well-covered signal.

Beginner default: `0.08`.

### `pasteurization`

Pasteurization controls whether data outside the selected universe is allowed into the calculation. `ON` is the safer beginner default because it keeps the expression aligned with the selected universe.

### `unitHandling`

Unit handling checks whether expression components have compatible units. `VERIFY` should be treated as research feedback. Unit warnings often mean the expression combines fields that are not economically comparable.

### `nanHandling`

NaN handling controls missing values. Leaving it `OFF` keeps missingness visible to operators. Turning it on can increase coverage, but may blur the difference between "missing", "zero", and "not applicable".

Beginner rule: do not turn NaN handling on only to make an Alpha look cleaner. First understand why the field is missing.

### `testPeriod`

Test period controls the visible train/test split inside the simulation review. It helps identify overfitting inside the in-sample window, but it is not the same as hidden out-of-sample validation.

Default: `P1Y6M`.

### `maxTrade`

Max Trade is an investability control. The API documentation discusses investability-constrained performance using MaxTrade. In `brain-sim`, `maxTrade` is passed through in the settings payload.

### Max Position

Max Position appears in the BRAIN UI screenshot, but this package does not expose it in `SimulationSettings` yet because the exact API field name must be confirmed from live payloads or official API documentation. Do not add a guessed field name just because it appears in the UI.

### `visualization`

Visualization controls whether visualization artifacts are requested. Leave it `False` for batch research unless you specifically need visual artifacts.

## Recommended Beginner Presets

| Purpose | Settings idea | Why |
|---|---|---|
| First stable test | USA, TOP3000, Delay 1, Industry or Subindustry neutralization, Decay 10-20 | Conservative, readable baseline. |
| Fast price/volume idea | Delay 1, lower decay, verify turnover | Avoid smoothing away the signal while watching turnover. |
| Slow fundamental idea | Delay 1, medium/high decay, Industry neutralization | Fundamentals usually update slowly and differ by industry. |
| Sparse event field | Check coverage first, consider `ts_backfill`, then simulate small batches | Sparse data can create narrow books and unstable PnL. |
| Debugging comparison | Change one setting at a time | Makes the cause of performance changes interpretable. |

## Data Field Mental Model

Data fields are not interchangeable numbers. Before writing an expression, inspect the field in Data Explorer.

Important checks:

- coverage: percentage of instruments covered by the field.
- date coverage: percentage of days with usable history.
- cadence: how often the field updates.
- region: where the field is available.
- delay: whether the field is compatible with the chosen delay setting.
- description: what the field actually measures.
- data type: matrix, vector, group, text/id, or metadata-like field.
- popularity: Alpha Count and User Count can indicate whether the field is crowded or hard to use.

## Data Field Types

### Matrix data field

A Matrix data field has one value per instrument per date. It can usually be used with normal cross-sectional and time-series operators.

Example patterns:

```text
rank(close)
rank(ts_mean(volume, 20))
group_rank(ts_mean(close, 20), industry)
```

Common mistakes:

- ranking a field with very low coverage without checking missingness.
- using a short time-series window on a field that updates slowly.
- combining fields with incompatible units without ranking or z-scoring first.

### Vector data field

A Vector data field has multiple values per instrument per date. Reduce it with a vector operator before using normal matrix-style operators.

Useful vector operators include:

- `vec_avg`
- `vec_sum`
- `vec_count`
- `vec_min`
- `vec_max`
- `vec_stddev`

Example pattern:

```text
rank(vec_avg(news_sentiment_vector))
```

Beginner rule: do not write `rank(vector_field)` until you have reduced the vector into one number per instrument-date.

### Group data field

A Group data field contains labels such as sector, industry, subindustry, country, exchange, or custom buckets. Use it as the grouping argument in group operators.

Example patterns:

```text
group_rank(rank(ts_mean(volume, 20)), industry)
group_neutralize(rank(close), subindustry)
```

Common mistakes:

- treating a group label like a numeric signal.
- using groups with too few members.
- forgetting that group choice changes the comparison peer set.

## Field Selection Workflow

1. Start in Data Explorer.
2. Confirm field type, coverage, date coverage, region, delay, and cadence.
3. Remove identifier-like fields such as ISIN, CUSIP, raw timestamps, and labels that do not express a tradable hypothesis.
4. Pick one field from a family of similar fields before expanding the search.
5. Match operator family to the field:
   - time-series operators for persistence, change, smoothing, and backfill.
   - cross-sectional operators for daily comparison.
   - group operators for peer-relative logic.
   - vector operators for vector fields.
6. Run a small batch first. The official BRAIN API guidance suggests testing a small search space before scaling.
7. Record expression, settings, payload hash, result metrics, and failure reason.

## Operator Matching Rules

| Situation | First operator family to consider | Example |
|---|---|---|
| Field is noisy daily data | Time Series | `rank(ts_mean(volume, 20))` |
| Field is sparse event data | Time Series backfill | `rank(ts_backfill(event_score, 60))` |
| Field is vector typed | Vector | `rank(vec_avg(vector_field))` |
| Raw levels differ by industry | Group | `group_rank(raw_signal, industry)` |
| Units are incompatible | Cross Sectional normalization | `rank(x) - rank(y)` |
| Turnover is too high | Smoothing/decay/gating | wider window, higher `decay`, or `hump` |
| Weight is concentrated | Breadth/outlier control | broader field, `winsorize`, `truncate`, group rank |

## How Settings And Data Fields Interact

- `region` and `universe` decide whether a field has enough usable coverage.
- `delay` decides whether the field timing is valid.
- `neutralization` decides the peer comparison and risk exposure.
- `decay` decides how quickly the portfolio reacts to changes in the field.
- `truncation` and Max Position style controls affect concentration.
- `pasteurization` and `nanHandling` affect how missing or out-of-universe data flows through the expression.
- `unitHandling` catches expression construction problems that are easy to miss in batch automation.

## Duplicate And Quota Discipline

The official BRAIN API guidance says successful simulations consume quota, including child simulations inside multi-simulation and repeated simulations of existing Alphas. `brain-sim` therefore hashes the full payload. If expression or settings change, the hash changes and the run is a different experiment.

Beginner rules:

- Do not brute-force 10,000 expressions until a small sample shows signal.
- Keep duplicate cache enabled.
- Change one axis at a time when learning.
- Stop when remaining quota is low.
- Review raw logs and summary files before expanding the batch.

## Checklist Before Simulating

- I know the thesis of the Alpha.
- I checked field type in Data Explorer.
- I checked coverage, date coverage, cadence, region, and delay.
- Vector fields are reduced with operators such as `vec_avg`.
- Group fields are used as groups, for example with `group_rank`.
- Missing data behavior is intentional.
- Settings match the comparison I want to make.
- I am not re-running an identical payload unless I intend to test duplicate handling.

## Checklist After Simulating

- Review Sharpe, Fitness, Returns, Turnover, Drawdown, Margin, long/short count, and weight concentration together.
- Compare train/test behavior when Test Period is enabled.
- Check warning and failure artifacts, not only `summary.csv`.
- If a run failed, classify the failure: syntax, field coverage, unit handling, batch rejection, timeout, quota, or platform transport issue.
- If a run succeeded, record the exact settings and payload hash.

## What Not To Do

- Do not compare results across different settings as if only the expression changed.
- Do not use vector fields without vector reduction.
- Do not use group fields as numeric values.
- Do not hide missing data without understanding why it is missing.
- Do not add UI-only settings to the API payload until the exact API field name is confirmed.
- Do not treat in-sample PnL as proof of future returns.

