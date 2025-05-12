from datetime import datetime

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
import databases


class Settings(BaseSettings):
    database_url: str 
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
database = databases.Database(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Execute on startup
    await database.connect()
    await database.execute("""
        CREATE TABLE IF NOT EXISTS pastes (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    yield

    # Event on shutdown
    await database.disconnect()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")


class Pastes(BaseModel):
    id: int
    title: str
    content: str
    created_at: datetime


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rows = await database.fetch_all("""
        SELECT id, title, LEFT(content, 75) AS content, created_at
        FROM pastes 
        ORDER BY created_at DESC;
    """)
    pastes = [Pastes(**row) for row in rows]
    return templates.TemplateResponse(request=request, name="app.html", context={ "pastes":pastes })


@app.get("/search", response_class=HTMLResponse)
async def query(request: Request, q: str):
    rows = await database.fetch_all("""
        SELECT id, title, LEFT(content, 75) AS content, created_at
        FROM pastes
        WHERE title ILIKE :q OR content ILIKE :q
        ORDER BY created_at DESC
    """, { "q": f"%{q}%" })

    pastes = [Pastes(**row) for row in rows]
    return templates.TemplateResponse(request=request, name="_tblrow.html", context={ "pastes": pastes })


@app.delete("/{paste_id}", response_class=HTMLResponse)
async def remove_paste(paste_id: int):
    await database.execute("DELETE FROM pastes WHERE id = :id", { "id": paste_id })
    return HTMLResponse("")
