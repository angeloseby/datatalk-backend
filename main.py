from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from router import file_upload

# Suggestion: Use your settings to configure the app title/version!
app = FastAPI(
    title=settings.api.title,
    version=settings.api.version,
    description=settings.api.description
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(file_upload.router)

@app.get("/")
def root():
    return {
        "status": "running",
    }