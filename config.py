import os
from dotenv import load_dotenv

# =========================
# APP PATHS & ENVIRONMENT
# =========================
# Centralized configuration so all pages/modules use the same paths.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "knowledge_base.db")
INDEX_PATH = os.path.join(BASE_DIR, "knowledge_base.index")
ENV_PATH = os.path.join(BASE_DIR, ".env")


def load_environment():
    """Load environment variables from local .env file."""
    load_dotenv(ENV_PATH)


def get_openai_api_key():
    """Read OpenAI API key from environment."""
    load_environment()
    return os.getenv("OPENAI_API_KEY", "").strip()
