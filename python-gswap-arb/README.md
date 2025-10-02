# python-gswap-arb

`python-gswap-arb` provides a home for arbitrage automation examples and tooling built on top of the [`python-gswap-sdk`](../README.md). The project is designed to help market makers experiment with cross-pair opportunities on GalaChain's gSwap exchange while preserving the SDK's decimal-first approach to asset pricing and position management.

## Goals

* Offer a thin CLI wrapper that can be scripted or automated to monitor pools and submit trades through `python-gswap-sdk`.
* Demonstrate how to compose higher level arbitrage strategies without sacrificing decimal safety.
* Establish standard Python tooling so contributors can iterate quickly and confidently.

## Getting Started

1. **Install the project** (preferably into a virtual environment):

   ```bash
   pip install -e .[dev]
   ```

2. **Run the CLI** to confirm everything is wired up:

   ```bash
   gswap-arb --help
   ```

   The command surfaces basic configuration options and ensures Decimal precision is configured before any network calls are made.

3. **Explore strategy development** by importing `gswap_arb` in a Python session and building workflows that re-use the core SDK clients. Because the project depends on `python-gswap-sdk`, all signed transactions and REST helpers are immediately available.

## Tooling

The repository configures Black, Ruff, MyPy, and Pytest via `pyproject.toml`. These tools enforce formatting, type safety, linting, and fast feedback loops, respectively. Continuous integration stubs mirror the SDK's decimal-first philosophy by ensuring every workflow validates Decimal precision before running project checks.

## Relationship to `python-gswap-sdk`

This repository is intentionally small and focused. Rather than duplicating functionality from the SDK, it imports the official package and layers arbitrage-centric helpers on top. Improvements discovered here should flow back into the SDK whenever they generalize beyond arbitrage use cases.
