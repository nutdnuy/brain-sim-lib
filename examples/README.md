# brain-sim Examples

This folder contains tutorial notebooks and sample assets for learning `brain-sim`.

The tutorials are designed to run offline first. They use deterministic fake BRAIN clients unless a section explicitly shows terminal commands for a live authenticated run.

## Tutorials

| Tutorial | Description | Assets |
|---|---|---|
| [Tutorial 1 - Excel Batch Alpha Simulation.ipynb](Tutorial%201%20-%20Excel%20Batch%20Alpha%20Simulation.ipynb) | Build an Excel alpha queue, run an offline batch simulation, and inspect `summary.csv` / `retry_queue.jsonl`. | [data/tutorial_01_alphas.xlsx](data/tutorial_01_alphas.xlsx), [expected/tutorial_01_summary.csv](expected/tutorial_01_summary.csv) |

## Run Locally

Install the project in editable mode:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Open the notebook:

```bash
jupyter notebook "examples/Tutorial 1 - Excel Batch Alpha Simulation.ipynb"
```

If Jupyter is not installed, read the notebook on GitHub and run the CLI examples from a terminal.

## Live BRAIN Runs

The tutorial includes live command examples, but the executable notebook cells are offline by default. Live runs consume WorldQuant BRAIN simulation quota and require a valid Persona-authenticated cookie created by `brain-sim login`.
