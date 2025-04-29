from fastapi import FastAPI, Request  # Added Request import here
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.routers import logs, consensus
from app.database import create_tables

app = FastAPI()

# Create the tables at the startup
create_tables()

# Include routers
app.include_router(logs.router)
app.include_router(consensus.router)

# Setup templates and static files
BASE_DIR = Path(__file__).parent.parent
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", include_in_schema=False)
async def read_root(request: Request):  # Now properly typed with imported Request
    return templates.TemplateResponse("logs.html", {"request": request})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)