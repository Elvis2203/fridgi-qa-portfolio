"""Stop owned test servers, including Windows virtual-environment launcher children."""

import os
import subprocess


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Killing only the venv launcher can leave its Python child holding SQLite open.
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode and process.poll() is None:
            raise RuntimeError(f"Could not stop test server: {result.stderr.strip()}")
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
