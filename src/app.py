from datetime import datetime, timezone
from dateutil import parser
from urllib.parse import quote_plus

from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
import databases

import humanize


class Settings(BaseSettings):
    database_url: str 
    root_path: str 
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
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            last_accessed TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    yield

    # Event on shutdown
    await database.disconnect()


app = FastAPI(lifespan=lifespan, root_path=settings.root_path)
print(f"Mounting static files at {settings.root_path}/static")
app.mount(f"/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")


class Pastes(BaseModel):
    id: int
    title: str
    content: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_accessed: datetime | None = None
    human_updated_at: str | None = None
    human_last_accessed: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    rows = await database.fetch_all("""
        SELECT id, title, updated_at, last_accessed
        FROM pastes 
        ORDER BY last_accessed DESC;
    """)
    pastes = [Pastes(
        id=row.id,
        title=row.title,
        human_updated_at=humanize.naturaltime(datetime.now(timezone.utc) - row.updated_at),
        human_last_accessed=humanize.naturaltime(datetime.now(timezone.utc) - row.last_accessed),
    ) for row in rows]
    return templates.TemplateResponse(request=request, name="app.html", context={ "pastes":pastes })


@app.get("/new", response_class=HTMLResponse)
async def new_paste_form(request: Request):
    return templates.TemplateResponse(request=request, name="paste.html", context={ "paste": None })


@app.post("/new")
async def create_paste(title: str = Form(...), content: str = Form(...)):
    id = await database.execute("""
        INSERT INTO pastes (title, content) 
        VALUES (:title, :content)
        RETURNING id;
    """, { "title": title, "content": content })

    response = Response(status_code=200)
    flash_message = quote_plus("Paste uploaded")
    response.headers["HX-Redirect"] = f"{settings.root_path}/{id}?flash={flash_message}"
    return response


@app.get("/search", response_class=HTMLResponse)
async def query(request: Request, q: str = Query(...)):
    rows = await database.fetch_all("""
        SELECT id, title, last_accessed, updated_at
        FROM pastes
        WHERE title ILIKE :q
        ORDER BY last_accessed DESC
    """, { "q": f"%{q}%" })

    pastes = [Pastes(**row) for row in rows]
    return templates.TemplateResponse(request=request, name="_tblrow.html", context={ "pastes": pastes })


@app.get("/{paste_id}", response_class=HTMLResponse)
async def view(request: Request, paste_id: int, flash: str | None = None):
    await database.execute("""
       UPDATE pastes
       SET last_accessed = NOW()
       WHERE id = :id;
    """, { "id": paste_id })

    row = await database.fetch_one("""
        SELECT id, title, content
        FROM pastes 
        WHERE id = :id
        ORDER BY last_accessed DESC
    """, { "id": paste_id })
    paste = Pastes(**row)

    return templates.TemplateResponse(
        request=request, 
        name="paste.html", 
        context={ "paste": paste, "flash": flash }
    )


@app.put("/{paste_id}")
async def put(request: Request, paste_id: int, title: str = Form(...), content: str = Form(...)):
    await database.execute("""
        UPDATE pastes
        SET title = :title, content = :content, updated_at = NOW()
        WHERE id = :id
    """, { "id": paste_id, "title": title, "content": content })

    response = Response(status_code=200)
    flash_message = quote_plus("Paste updated")
    response.headers["HX-Redirect"] = f"{settings.root_path}/{paste_id}?flash={flash_message}"
    return response


@app.delete("/{paste_id}", response_class=HTMLResponse)
async def remove_paste(paste_id: int):
    await database.execute("DELETE FROM pastes WHERE id = :id", { "id": paste_id })
    return HTMLResponse("")
