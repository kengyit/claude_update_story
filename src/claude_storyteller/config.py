from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    github_token: str
    github_username: str
    state_repo: str
    state_repo_branch: str
    daily_run_at: str
    story_model: str
    message_delay_seconds: float
    state_workdir: Path
    log_level: str

    @property
    def state_file(self) -> Path:
        return self.state_workdir / "state" / "explained.json"


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_config() -> Config:
    env_file = os.environ.get("CLAUDE_STORYTELLER_ENV")
    if env_file:
        load_dotenv(env_file)
    else:
        for candidate in (
            Path.cwd() / ".env",
            Path.home() / ".config" / "claude-storyteller" / ".env",
        ):
            if candidate.exists():
                load_dotenv(candidate)
                break

    workdir = Path(
        os.environ.get(
            "STATE_WORKDIR",
            "~/.local/share/claude-storyteller/state-repo",
        )
    ).expanduser()

    return Config(
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        telegram_bot_token=_require("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_require("TELEGRAM_CHAT_ID"),
        github_token=_require("GITHUB_TOKEN"),
        github_username=_require("GITHUB_USERNAME"),
        state_repo=os.environ.get("STATE_REPO", "kengyit/claude_update_story"),
        state_repo_branch=os.environ.get("STATE_REPO_BRANCH", "main"),
        daily_run_at=os.environ.get("DAILY_RUN_AT", "09:00"),
        story_model=os.environ.get("STORY_MODEL", "claude-sonnet-4-6"),
        message_delay_seconds=float(os.environ.get("MESSAGE_DELAY_SECONDS", "3")),
        state_workdir=workdir,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
