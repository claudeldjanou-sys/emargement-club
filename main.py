from datetime import datetime, timedelta, timezone
import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

app = FastAPI(title="Émargement Club")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL est obligatoire. Ajoutez une base PostgreSQL Render et sa variable DATABASE_URL.")

# Render fournit parfois postgres:// ; SQLAlchemy attend postgresql://.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS adherents (
                id SERIAL PRIMARY KEY,
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                telephone TEXT NOT NULL UNIQUE,
                equipe TEXT NOT NULL,
                qualite TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS presences (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                nom TEXT NOT NULL,
                prenom TEXT NOT NULL,
                telephone TEXT NOT NULL,
                equipe TEXT NOT NULL,
                qualite TEXT NOT NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_presences_telephone_timestamp ON presences (telephone, timestamp DESC)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_presences_equipe ON presences (equipe)"))


@app.on_event("startup")
def startup():
    init_db()


def now_utc():
    return datetime.now(timezone.utc)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"datetime": datetime.now().strftime("%d/%m/%Y %H:%M:%S")},
    )


@app.post("/api/emarger")
async def emarger(
    nom: str = Form(...),
    prenom: str = Form(...),
    telephone: str = Form(...),
    equipe: str = Form(...),
    qualite: str = Form(...),
):
    nom, prenom, telephone, equipe, qualite = [
        value.strip() for value in (nom, prenom, telephone, equipe, qualite)
    ]
    if not all((nom, prenom, telephone, equipe, qualite)):
        return JSONResponse(status_code=400, content={"message": "Tous les champs sont obligatoires."})

    now = now_utc()
    with engine.begin() as conn:
        recent = conn.execute(
            text("SELECT timestamp FROM presences WHERE telephone = :telephone ORDER BY timestamp DESC LIMIT 1"),
            {"telephone": telephone},
        ).scalar_one_or_none()

        if recent is not None and now - recent < timedelta(minutes=30):
            return JSONResponse(status_code=400, content={"message": "Présence déjà enregistrée récemment"})

        conn.execute(
            text("""
                INSERT INTO adherents (nom, prenom, telephone, equipe, qualite, updated_at)
                VALUES (:nom, :prenom, :telephone, :equipe, :qualite, NOW())
                ON CONFLICT (telephone) DO UPDATE SET
                    nom = EXCLUDED.nom,
                    prenom = EXCLUDED.prenom,
                    equipe = EXCLUDED.equipe,
                    qualite = EXCLUDED.qualite,
                    updated_at = NOW()
            """),
            {"nom": nom, "prenom": prenom, "telephone": telephone, "equipe": equipe, "qualite": qualite},
        )
        conn.execute(
            text("""
                INSERT INTO presences (timestamp, nom, prenom, telephone, equipe, qualite)
                VALUES (:timestamp, :nom, :prenom, :telephone, :equipe, :qualite)
            """),
            {"timestamp": now, "nom": nom, "prenom": prenom, "telephone": telephone, "equipe": equipe, "qualite": qualite},
        )

    return {"message": "Présence enregistrée"}


@app.get("/api/stats")
async def stats():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT equipe, COUNT(*) AS total FROM presences GROUP BY equipe ORDER BY equipe")
        ).mappings().all()
    return {row["equipe"]: int(row["total"]) for row in rows}


@app.get("/api/presences")
async def liste_presences():
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT timestamp, nom, prenom, telephone, equipe, qualite
                FROM presences
                ORDER BY timestamp DESC
            """)
        ).mappings().all()
    return [dict(row) for row in rows]


@app.get("/api/export/presences.csv")
async def export_presences():
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "nom", "prenom", "telephone", "equipe", "qualite"])
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT timestamp, nom, prenom, telephone, equipe, qualite
                FROM presences
                ORDER BY timestamp DESC
            """)
        ).all()
        for row in rows:
            writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8-sig")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=presences.csv"},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse(request=request, name="admin.html", context={})
