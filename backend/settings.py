import os
from dotenv import load_dotenv

load_dotenv()

"""
    This file keeps API keys, model names and database paths out of the
    main app logic. Every backend file imports settings from here.
"""

class Settings:
    

    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")

    OPENAI_CHAT_MODEL: str = os.getenv(
        "OPENAI_CHAT_MODEL",
        "gpt-4o-mini"
    )

    OPENAI_EMBEDDING_MODEL: str = os.getenv(
        "OPENAI_EMBEDDING_MODEL",
        "text-embedding-3-small"
    )

    CHROMA_DB_DIR: str = os.getenv(
        "CHROMA_DB_DIR",
        "./db/chroma"
    )


settings = Settings()


def require_openai_key() -> str:
    """
    Returns the OpenAI API key.
    If the key is missing, this raises a clear error instead of allowing
    the app to fail later with a confusing model/embedding error.
    """
    if not settings.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY was not found. Add it to your .env file."
        )

    return settings.OPENAI_API_KEY