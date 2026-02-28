from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from router import chat, file_upload

# Suggestion: Use your settings to configure the app title/version!
app = FastAPI(
    title=settings.api.title,
    version=settings.api.version,
    description=settings.api.description,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    # In local development Flutter Web uses dynamic localhost ports.
    # This keeps strict explicit origins from settings, while allowing
    # localhost/127.0.0.1 on any port during development.
    allow_origin_regex=(
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        if settings.is_development
        else None
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(file_upload.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return {
        "status": "running",
    }
