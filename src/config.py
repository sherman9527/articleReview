"""Global configuration for the review system."""

import os
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Paths
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
SENSITIVE_WORDS_FILE = DATA_DIR / "sensitive_words.json"

# LLM settings
CLAUDE_CMD = os.environ.get("CLAUDE_CMD", "claude")
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))  # seconds per call
MAX_TEXT_LENGTH = int(os.environ.get("MAX_TEXT_LENGTH", "80000"))  # chars per agent call

# Ensure output dir exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
