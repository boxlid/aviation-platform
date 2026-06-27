"""Sonic Flight — FastAPI application entrypoint."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, scheduler
from .api import router as api_router
from .config import ROOT
from .logs import get_logger

HERE = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
log = get_logger("platform")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_pool()
    db.apply_schema(os.path.join(ROOT, "db", "schema.sql"),
                    os.path.join(ROOT, "db", "schema_platform.sql"))
    log.info("schema applied")
    scheduler.start()
    log.info("Sonic Flight platform online")
    yield
    scheduler.shutdown()


app = FastAPI(title="Sonic Flight", lifespan=lifespan)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


def page(request: Request, template: str, **ctx):
    return templates.TemplateResponse(template, {"request": request, "active": ctx.pop("active", ""), **ctx})


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return page(request, "dashboard.html", active="dashboard", title="Dashboard")


@app.get("/fleet", response_class=HTMLResponse)
def fleet_page(request: Request):
    return page(request, "fleet.html", active="fleet", title="Fleet")


@app.get("/operators", response_class=HTMLResponse)
def operators_page(request: Request):
    return page(request, "operators.html", active="operators", title="Operators")


@app.get("/operator/{designator}", response_class=HTMLResponse)
def operator_detail_page(request: Request, designator: str):
    return page(request, "operator_detail.html", active="operators", title="Operator", designator=designator)


@app.get("/fsdo", response_class=HTMLResponse)
def fsdo_detail_page(request: Request):
    return page(request, "fsdo_detail.html", active="operators", title="FSDO")


@app.get("/routes", response_class=HTMLResponse)
def routes_page(request: Request):
    return page(request, "routes.html", active="routes", title="Charter Routes")


@app.get("/emails", response_class=HTMLResponse)
def emails_page(request: Request):
    return page(request, "emails.html", active="emails", title="Emails")


@app.get("/settings/services", response_class=HTMLResponse)
def services_page(request: Request):
    return page(request, "services.html", active="services", title="Services")


@app.get("/settings/services/{name}", response_class=HTMLResponse)
def service_detail_page(request: Request, name: str):
    return page(request, "service_detail.html", active="services", title="Service", service_name=name)
