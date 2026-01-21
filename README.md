# Backend - FastAPI Application

## Setup
1. Create virtual environment: `python -m venv venv`
2. Activate: `source venv/bin/activate` (Unix) or `venv\Scripts\activate` (Windows)
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and update values
5. Run: `uvicorn app.main:app --reload`

## API Documentation
Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc