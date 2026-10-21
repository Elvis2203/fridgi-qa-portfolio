import logging
from contextlib import asynccontextmanager
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.db import database_url, make_engine
from app.domain import InvalidBatch, parse_batch
from app.pantry import add_items, delete_item, list_items
from app.recipe_models import SuggestionsInput, SuggestionsOutput
from app.recipe_provider import SAMPLE_RECIPE, ProviderUnavailable, configured_provider
from app.recipes import (
    InvalidRecipeOutput,
    RecipeContextTooLarge,
    load_context,
    validate_candidates,
)
from app.requirements import (
    ConflictingRequirements,
    InvalidExclusions,
    UnavailablePantryItems,
    check_requirements,
    parse_exclusions,
)
from app.schemas import (
    BatchInput,
    BatchOutput,
    ErrorOutput,
    PantryOutput,
    RequirementsInput,
    RequirementsOutput,
)

logger = logging.getLogger("uvicorn.error.fridgi")


def create_app(url: str | None = None, recipe_provider=None) -> FastAPI:
    engine = make_engine(url or database_url())
    provider = recipe_provider if recipe_provider is not None else configured_provider()
    generation_lock = Lock()

    @asynccontextmanager
    async def lifespan(_):
        yield
        engine.dispose()

    app = FastAPI(title="Fridgi API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def request_identifier(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        logger.info(
            "request_id=%s method=%s path=%s status=%s",
            request.state.request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response

    def error(request, status, code, message, field=None, entry_index=None, reason_codes=None):
        return JSONResponse(
            status_code=status,
            content={
                "error": {
                    "code": code,
                    "message": message,
                    "field": field,
                    "entry_index": entry_index,
                    "request_id": request.state.request_id,
                    **({"reason_codes": reason_codes} if reason_codes else {}),
                }
            },
        )

    @app.exception_handler(InvalidBatch)
    async def invalid_batch(request: Request, exc: InvalidBatch):
        return error(request, 422, "INVALID_BATCH", str(exc), "text", exc.entry_index)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"][1:]) or "body"
        return error(request, 422, "INVALID_REQUEST", first["msg"], location)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        # Do not log SQL parameters (which can contain the user's original input).
        logger.error(
            "request_id=%s database_error=%s", request.state.request_id, type(exc).__name__
        )
        return error(
            request,
            503,
            "DATABASE_UNAVAILABLE",
            "The pantry database is unavailable. Check the server setup and retry.",
        )

    errors = {422: {"model": ErrorOutput}, 503: {"model": ErrorOutput}}

    @app.exception_handler(InvalidExclusions)
    async def invalid_exclusions(request: Request, exc: InvalidExclusions):
        return error(request, 422, "INVALID_EXCLUSIONS", str(exc), "excluded_text")

    @app.exception_handler(ConflictingRequirements)
    async def conflicting_requirements(request: Request, exc: ConflictingRequirements):
        return error(request, 422, "CONFLICTING_REQUIREMENTS", str(exc), "excluded_text")

    @app.get("/api/pantry", response_model=PantryOutput, responses={503: errors[503]})
    def get_pantry():
        with Session(engine) as session:
            return PantryOutput(items=list_items(session))

    @app.post(
        "/api/pantry/bulk",
        response_model=BatchOutput,
        status_code=201,
        responses={**errors, 200: {"model": BatchOutput, "description": "Only duplicates"}},
    )
    def add_pantry(body: BatchInput, response: Response):
        entries = parse_batch(body.text)
        with Session(engine) as session, session.begin():
            result = add_items(session, entries)
        response.status_code = 201 if result.added_count else 200
        return result

    @app.delete(
        "/api/pantry/{item_id}",
        response_model=PantryOutput,
        responses={**errors, 404: {"model": ErrorOutput}},
    )
    def delete_pantry(item_id: int, request: Request):
        with Session(engine) as session, session.begin():
            if not delete_item(session, item_id):
                return error(
                    request,
                    404,
                    "PANTRY_ITEM_NOT_FOUND",
                    "This ingredient is no longer in your pantry. Refresh the pantry to update it.",
                )
            result = PantryOutput(items=list_items(session))
        return result

    @app.post("/api/recipe-requests/check", response_model=RequirementsOutput, responses=errors)
    def check_recipe_requirements(body: RequirementsInput, request: Request):
        try:
            entries = parse_batch(body.prefer_to_avoid_text, allow_empty=True)
        except InvalidBatch as exc:
            return error(
                request,
                422,
                "INVALID_PREFERENCES",
                str(exc),
                "prefer_to_avoid_text",
                exc.entry_index,
            )
        try:
            with Session(engine) as session:
                return check_requirements(
                    session, body.must_use_item_ids, entries, parse_exclusions(body.excluded_text)
                )
        except UnavailablePantryItems as exc:
            return error(request, 422, "UNAVAILABLE_PANTRY_ITEMS", str(exc), "must_use_item_ids")

    @app.get("/api/recipes/capabilities")
    def recipe_capabilities():
        return {
            "sample_available": True,
            "live_available": provider.configured,
            "live_source": provider.source,
        }

    @app.post(
        "/api/recipes/suggestions",
        response_model=SuggestionsOutput,
        responses={**errors, **{status: {"model": ErrorOutput} for status in (409, 429, 502)}},
    )
    def suggest_recipes(body: SuggestionsInput, request: Request):
        try:
            with Session(engine) as session:
                context = load_context(session, body)
        except InvalidBatch as exc:
            return error(
                request,
                422,
                "INVALID_PREFERENCES",
                str(exc),
                "prefer_to_avoid_text",
                exc.entry_index,
            )
        except UnavailablePantryItems as exc:
            return error(request, 422, "UNAVAILABLE_PANTRY_ITEMS", str(exc), "must_use_item_ids")
        except RecipeContextTooLarge as exc:
            return error(request, 422, "RECIPE_CONTEXT_TOO_LARGE", str(exc))
        acquired = False
        try:
            if body.source != "sample":
                if body.source != provider.source:
                    raise ProviderUnavailable(
                        "The recipe provider changed. Reload the page before trying again.",
                        "PROVIDER_MISMATCH",
                    )
                acquired = generation_lock.acquire(blocking=False)
                if not acquired:
                    return error(
                        request,
                        429,
                        "GENERATION_BUSY",
                        "A recipe request is already running. Please wait before retrying.",
                    )
                payload = provider.generate(context.provider_input())
            else:
                payload = {"recipes": [SAMPLE_RECIPE]}
            with Session(engine) as session:
                try:
                    current = load_context(session, body)
                except (UnavailablePantryItems, RecipeContextTooLarge):
                    current = None
            if (
                current is None
                or context.pantry != current.pantry
                or context.aliases != current.aliases
            ):
                return error(
                    request,
                    409,
                    "PANTRY_CHANGED",
                    "Your pantry changed while preparing recipes. Refresh and try again.",
                )
            return validate_candidates(payload, current, body.source)
        except ProviderUnavailable as exc:
            logger.warning(
                "request_id=%s recipe_service_reason=%s upstream_status=%s",
                request.state.request_id,
                exc.reason,
                exc.upstream_status,
            )
            return error(
                request, 503, "RECIPE_SERVICE_UNAVAILABLE", str(exc), reason_codes=[exc.reason]
            )
        except InvalidRecipeOutput as exc:
            return error(request, 502, "INVALID_RECIPE_OUTPUT", str(exc), reason_codes=exc.codes)
        finally:
            if acquired:
                generation_lock.release()

    return app


app = create_app()
