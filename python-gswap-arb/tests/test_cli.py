from __future__ import annotations

from gswap_arb.cli import build_parser, main


def test_build_parser_exposes_expected_arguments() -> None:
    parser = build_parser()
    options = {action.dest for action in parser._actions}
    assert {"precision", "dry_run"}.issubset(options)


def test_main_configures_decimal_context(capsys) -> None:
    exit_code = main(["--precision", "32", "--dry-run"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "precision=32" in output
    assert "dry_run=True" in output
