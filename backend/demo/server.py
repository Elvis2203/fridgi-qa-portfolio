"""Offline demo: the built frontend and API with a separate database and sample recipes only."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.main import create_app


class OfflineProvider:
    source = "groq"
    configured = False

    def generate(self, _):
        from app.recipe_provider import ProviderUnavailable

        raise ProviderUnavailable("This demonstration is offline. Use the sample recipe.")


def demo_app(root: Path):
    root = root.resolve()
    folder = root / ".local-demo"
    folder.mkdir(exist_ok=True)
    url = f"sqlite:///{(folder / 'pantry.db').as_posix()}"
    config = Config(str(root / "backend/alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")
    app = create_app(url, OfflineProvider())
    app.state.demo_database = str(folder / "pantry.db")

    assets = root / "frontend/dist/assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        return FileResponse(root / "frontend/dist/favicon.svg", media_type="image/svg+xml")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def homepage():
        index = root / "frontend/dist/index.html"
        if not index.exists():
            return Response(
                "Build the frontend first: npm --prefix frontend run build", status_code=503
            )
        banner = (
            '<aside aria-label="Environment" style="padding:12px;text-align:center;'
            'background:#253d31;color:white;font:16px system-ui">'
            "OFFLINE DEMO — fixed sample recipes. Separate test data.</aside>"
        )
        return index.read_text(encoding="utf-8").replace("<body>", "<body>" + banner)

    return app
