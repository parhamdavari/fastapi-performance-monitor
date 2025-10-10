"""Tests for the CLI package convenience functions."""

from __future__ import annotations

import pytest

import fastapi_pulse.cli as cli_module


def test_main_handles_keyboard_interrupt(monkeypatch, capsys):
    def raise_interrupt():
        raise KeyboardInterrupt()

    monkeypatch.setattr(cli_module, "cli", raise_interrupt)

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main()

    assert excinfo.value.code == 130
    assert "Interrupted by user" in capsys.readouterr().err


def test_main_handles_generic_exception(monkeypatch, capsys):
    def raise_error():
        raise RuntimeError("boom")

    monkeypatch.setattr(cli_module, "cli", raise_error)

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main()

    assert excinfo.value.code == 1
    assert "Error: boom" in capsys.readouterr().err
