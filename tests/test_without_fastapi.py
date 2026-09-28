"""The core and the CLI must work with fastapi absent.

Each test runs a subprocess that blocks the fastapi import (a None
entry in sys.modules makes any import of it raise ImportError), which
proves the code under test never needs it.
"""

import os
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")

BLOCK_FASTAPI = "import sys; sys.modules['fastapi'] = None\n"

REGISTRY_MODULE = """\
from scope_parity import Registry, Route, Scope

registry = Registry(
    routes=[Route("GET", "/orders", "list_orders", scopes={"orders:read"})],
    scopes=[Scope("orders:read", "view orders")],
)
"""


def run_python(code: str, extra_path: str | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC if extra_path is None else os.pathsep.join([SRC, extra_path])
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", BLOCK_FASTAPI + code],
        capture_output=True,
        text=True,
        env=env,
    )


def test_core_imports_and_checks_run_without_fastapi():
    result = run_python(
        "from scope_parity import Registry, Route, Scope, run_checks\n"
        "registry = Registry(routes=[Route('GET', '/orders', 'list_orders')], scopes=[])\n"
        "findings = run_checks(registry)\n"
        "assert [f.code for f in findings] == ['route-unprotected']\n"
        "print('ok')\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_cli_runs_a_hand_written_registry_without_fastapi(tmp_path):
    (tmp_path / "ordersapp_plain.py").write_text(REGISTRY_MODULE, encoding="utf-8")
    result = run_python(
        "from scope_parity.cli import main\n"
        "import sys\n"
        "sys.exit(main(['ordersapp_plain:registry']))\n",
        extra_path=str(tmp_path),
    )
    assert result.returncode == 0, result.stderr
    assert "no findings" in result.stdout


def test_adapter_import_without_fastapi_says_what_to_install():
    result = run_python("import scope_parity.fastapi\n")
    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert 'pip install "scope-parity[fastapi]"' in result.stderr


def test_triage_flag_without_fastapi_exits_tool_failure(tmp_path):
    (tmp_path / "ordersapp_plain2.py").write_text(REGISTRY_MODULE, encoding="utf-8")
    result = run_python(
        "from scope_parity.cli import main\n"
        "import sys\n"
        "sys.exit(main(['ordersapp_plain2:registry', '--triage-unclassifiable']))\n",
        extra_path=str(tmp_path),
    )
    assert result.returncode == 2
    assert "--triage-unclassifiable requires the fastapi extra" in result.stderr
