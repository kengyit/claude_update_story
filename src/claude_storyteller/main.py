from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config, load_config
from .dedupe import ExplainedStore
from .github_repos import GitHubRepoLister
from .sources import (
    AnthropicDocsSource,
    AnthropicNewsSource,
    ClaudeCodeReleasesSource,
    ClaudeProbeSource,
    Feature,
    FeatureSource,
)
from .state_repo import StateRepo
from .storyteller import Storyteller
from .telegram_bot import TelegramSender

log = logging.getLogger("claude_storyteller")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _build_sources(cfg: Config) -> list[FeatureSource]:
    return [
        AnthropicDocsSource(),
        AnthropicNewsSource(),
        ClaudeCodeReleasesSource(github_token=cfg.github_token),
        ClaudeProbeSource(api_key=cfg.anthropic_api_key, model=cfg.story_model),
    ]


def _collect_features(sources: list[FeatureSource]) -> list[Feature]:
    seen: dict[str, Feature] = {}
    for src in sources:
        try:
            for feat in src.fetch():
                seen.setdefault(feat.stable_id, feat)
        except Exception as exc:
            log.exception("source %s failed: %s", src.name, exc)
    return list(seen.values())


def run_once(cfg: Config, *, dry_run: bool = False, limit: int | None = None) -> int:
    state_repo = StateRepo(
        workdir=cfg.state_workdir,
        repo_full_name=cfg.state_repo,
        branch=cfg.state_repo_branch,
        github_token=cfg.github_token,
    )
    if not dry_run:
        state_repo.ensure()

    store = ExplainedStore(cfg.state_file)
    store.load()

    sources = _build_sources(cfg)
    all_features = _collect_features(sources)
    log.info("collected %d candidate features across sources", len(all_features))

    new_features = store.filter_new(all_features)
    new_features.sort(key=lambda f: f.title.lower())
    if limit is not None:
        new_features = new_features[:limit]
    log.info("%d feature(s) to explain this run", len(new_features))

    if not new_features:
        return 0

    repos = GitHubRepoLister(cfg.github_token, cfg.github_username).list_repos()
    storyteller = Storyteller(api_key=cfg.anthropic_api_key, model=cfg.story_model)
    sender = TelegramSender(cfg.telegram_bot_token, cfg.telegram_chat_id) if not dry_run else None

    sent = 0
    for feature in new_features:
        try:
            story = storyteller.tell(feature, repos)
        except Exception as exc:
            log.exception("story generation failed for %s: %s", feature.title, exc)
            continue

        if dry_run:
            print("=" * 60)
            print(f"FEATURE: {feature.title}")
            print(f"SOURCE:  {feature.source}")
            print("-" * 60)
            print(story)
            print()
            sent += 1
            continue

        try:
            message_id = sender.send(story) if sender else None
        except Exception as exc:
            log.exception("telegram send failed for %s: %s", feature.title, exc)
            continue

        store.mark_explained(feature, telegram_message_id=message_id)
        store.save()
        sent += 1
        time.sleep(cfg.message_delay_seconds)

    if not dry_run and sent > 0:
        try:
            state_repo.commit_and_push(
                message=f"explain {sent} feature(s) on {datetime.utcnow():%Y-%m-%d}",
                author_name="claude-storyteller",
                author_email="claude-storyteller@users.noreply.github.com",
            )
        except Exception as exc:
            log.exception("state repo push failed: %s", exc)

    return sent


def _parse_daily_time(value: str) -> tuple[int, int]:
    hh, mm = value.split(":", 1)
    return int(hh), int(mm)


def serve(cfg: Config) -> None:
    log.info("starting claude-storyteller scheduler; daily at %s", cfg.daily_run_at)

    # Catch-up tick on boot.
    try:
        run_once(cfg)
    except Exception as exc:
        log.exception("initial run failed: %s", exc)

    hour, minute = _parse_daily_time(cfg.daily_run_at)
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        lambda: run_once(cfg),
        CronTrigger(hour=hour, minute=minute),
        id="daily-run",
        max_instances=1,
        coalesce=True,
    )

    def _shutdown(signum, _frame):
        log.info("received signal %s; shutting down", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.start()


def cli() -> None:
    parser = argparse.ArgumentParser(prog="claude-storyteller")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single discovery+send pass and exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate stories but do not send to Telegram or commit state.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of features processed in this run (useful for testing).",
    )
    args = parser.parse_args()

    cfg = load_config()
    _configure_logging(cfg.log_level)

    if args.once or args.dry_run:
        count = run_once(cfg, dry_run=args.dry_run, limit=args.limit)
        log.info("run complete: %d feature(s) processed", count)
        return

    serve(cfg)


if __name__ == "__main__":
    cli()
