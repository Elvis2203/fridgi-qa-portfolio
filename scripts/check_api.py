"""Run Newman against a disposable, offline Fridgi instance; retain reports and logs."""

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from demo.processes import stop_process

ROOT = Path(__file__).resolve().parents[1]


def main():
    node = shutil.which("node")
    newman = ROOT / "qa/api/node_modules/newman/bin/newman.js"
    if not node or not newman.exists():
        raise SystemExit("Install Node and run: npm --prefix qa/api ci")
    reports = ROOT / "test-results"
    reports.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="fridgi-api-") as directory:
        temporary = Path(directory)
        (temporary / "backend").mkdir()
        config = (
            (ROOT / "backend/alembic.ini")
            .read_text()
            .replace("%(here)s/migrations", (ROOT / "backend/migrations").as_posix())
        )
        (temporary / "backend/alembic.ini").write_text(config)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), FRIDGI_RECIPE_PROVIDER="groq")
        for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "FRIDGI_ENABLE_AI", "FRIDGI_DATABASE_URL"):
            env.pop(key, None)
        code = (
            "from pathlib import Path; import uvicorn; from demo.server import demo_app; "
            f"uvicorn.run(demo_app(Path({str(temporary)!r})), host='127.0.0.1', port={port})"
        )
        with (reports / "newman-server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-c", code],
                env=env,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                deadline = time.monotonic() + 20
                url = f"http://127.0.0.1:{port}"
                while True:
                    try:
                        with urlopen(url + "/api/pantry", timeout=1):
                            break
                    except OSError:
                        if process.poll() is not None or time.monotonic() >= deadline:
                            raise RuntimeError(
                                "API did not start; see test-results/newman-server.log"
                            ) from None
                        time.sleep(0.1)
                return subprocess.run(
                    [
                        node,
                        str(newman),
                        "run",
                        str(ROOT / "qa/api/Fridgi.postman_collection.json"),
                        "--env-var",
                        f"base_url={url}",
                        "--reporters",
                        "cli,json,junit",
                        "--reporter-json-export",
                        str(reports / "newman.json"),
                        "--reporter-junit-export",
                        str(reports / "newman.xml"),
                    ],
                    cwd=ROOT,
                    check=False,
                ).returncode
            finally:
                stop_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
