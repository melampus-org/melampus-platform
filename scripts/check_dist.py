"""Verify installed artifacts and bundled UI independently of the source checkout."""

import subprocess
import tempfile
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
wheels = list(
    (root / "dist").glob("melampus_platform-" + (root / "VERSION").read_text().strip() + "-*.whl")
)
assert len(wheels) == 1
with zipfile.ZipFile(wheels[0]) as archive:
    for path in (
        "static/index.html",
        "static/app.js",
        "static/style.css",
        "static/favicon.svg",
        "static/mesh.js",
        "py.typed",
    ):
        assert "melampus_platform/" + path in archive.namelist(), path
with tempfile.TemporaryDirectory() as tmp:
    subprocess.run(["uv", "venv", tmp + "/env"], check=True)
    python = tmp + "/env/bin/python"
    subprocess.run(
        ["uv", "pip", "install", "--python", python, str(wheels[0]), "httpx"], check=True
    )
    subprocess.run(
        [
            python,
            "-c",
            "from fastapi.testclient import TestClient; from melampus_platform.app import create_app; "
            "c=TestClient(create_app(':memory:')); "
            "c.__enter__(); assert c.get('/healthz').status_code == 200; "
            "assert 'Trace Explorer' in c.get('/').text; assert c.get('/static/app.js').status_code == 200; "
            "c.__exit__(None,None,None); print('Installed platform smoke passed.')",
        ],
        cwd=tmp,
        check=True,
    )
