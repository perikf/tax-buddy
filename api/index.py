"""Vercel entry: /calculate and /health are rewritten here; Vercel serves the SPA."""
from backend.main import app

__all__ = ["app"]
