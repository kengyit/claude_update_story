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
        ClaudeProbeSource(
            api_key=cfg.anthropic_api_key,
            model=cfg.story_model,
            cutoff_date=cfg.backlog_cutoff_date,
        ),
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


def run_once(
    cfg: Config,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    seed_cap: int | None = None,
) -> int:
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

    # When seeding the backlog, keep the first `seed_cap` features (which are
    # in source order, roughly newest-first) and silently mark the rest as
    # explained so they never spam Telegram.
    silently_skipped = 0
    if seed_cap is not None and len(new_features) > seed_cap:
        to_skip = new_features[seed_cap:]
        new_features = new_features[:seed_cap]
        for feat in to_skip:
            store.mark_explained(feat, telegram_message_id=None)
        silently_skipped = len(to_skip)
        log.info(
            "seed-cap=%d: silently marking %d older feature(s) as explained",
            seed_cap,
            silently_skipped,
        )

    if limit is not None:
        new_features = new_features[:limit]
    log.info("%d feature(s) to explain this run", len(new_features))

    if not new_features and silently_skipped == 0:
        return 0
    if not new_features and silently_skipped > 0:
        # Nothing to send, but we modified the store; persist & push.
        store.save()
        if not dry_run:
            try:
                state_repo.commit_and_push(
                    message=f"seed backlog: mark {silently_skipped} feature(s) as explained",
                    author_name="claude-storyteller",
                    author_email="claude-storyteller@users.noreply.github.com",
                )
            except Exception as exc:
                log.exception("state repo push failed: %s", exc)
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

    if not dry_run and (sent > 0 or silently_skipped > 0):
        if silently_skipped > 0:
            msg = (
                f"explain {sent} feature(s), seed-skip {silently_skipped} older "
                f"on {datetime.utcnow():%Y-%m-%d}"
            )
        else:
            msg = f"explain {sent} feature(s) on {datetime.utcnow():%Y-%m-%d}"
        try:
            state_repo.commit_and_push(
                message=msg,
                author_name="claude-storyteller",
                author_email="claude-storyteller@users.noreply.github.com",
            )
        except Exception as exc:
            log.exception("state repo push failed: %s", exc)

    return sent


def run_backlog_flagship(cfg: Config, *, dry_run: bool = False) -> int:
    """Send ONLY the curated flagship features (from the Claude probe), in
    chronological order starting with subagents/multi-agent orchestration.
    Every other feature surfaced by discovery is silently marked as explained
    so daily runs don't flood Telegram with old release-bullet noise."""
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

    # 1. Curated flagship list (probe handles ordering: subagents first).
    probe = ClaudeProbeSource(
        api_key=cfg.anthropic_api_key,
        model=cfg.story_model,
        cutoff_date=cfg.backlog_cutoff_date,
    )
    flagship_features = probe.fetch()
    log.info("curated probe returned %d flagship feature(s)", len(flagship_features))

    # 2. Everything else discovery would surface — to be silently buried.
    other_sources: list[FeatureSource] = [
        AnthropicDocsSource(),
        AnthropicNewsSource(),
        ClaudeCodeReleasesSource(github_token=cfg.github_token),
    ]
    flagship_ids = {f.stable_id for f in flagship_features}
    silently_skipped = 0
    for src in other_sources:
        try:
            for feat in src.fetch():
                if feat.stable_id in flagship_ids:
                    continue
                if feat.stable_id in store:  # already known
                    continue
                store.mark_explained(feat, telegram_message_id=None)
                silently_skipped += 1
        except Exception as exc:
            log.exception("source %s failed during backlog burial: %s", src.name, exc)
    log.info(
        "silently marked %d non-flagship feature(s) as explained",
        silently_skipped,
    )

    # 3. Filter flagship list down to ones not already explained.
    to_send = [f for f in flagship_features if f.stable_id not in store._data]
    log.info("%d flagship feature(s) to send", len(to_send))

    if not to_send and silently_skipped == 0:
        return 0

    repos = GitHubRepoLister(cfg.github_token, cfg.github_username).list_repos()
    storyteller = Storyteller(api_key=cfg.anthropic_api_key, model=cfg.story_model)
    sender = (
        TelegramSender(cfg.telegram_bot_token, cfg.telegram_chat_id)
        if not dry_run
        else None
    )

    sent = 0
    for feature in to_send:
        try:
            story = storyteller.tell(feature, repos)
        except Exception as exc:
            log.exception("story generation failed for %s: %s", feature.title, exc)
            continue

        if dry_run:
            print("=" * 60)
            print(f"FLAGSHIP: {feature.title}")
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

    if not dry_run:
        store.save()
        try:
            state_repo.commit_and_push(
                message=(
                    f"flagship backlog: send {sent}, bury {silently_skipped} "
                    f"(cutoff {cfg.backlog_cutoff_date})"
                ),
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
    log.info(
        "starting claude-storyteller scheduler; daily at %s (%s)",
        cfg.daily_run_at,
        cfg.timezone,
    )

    # Catch-up tick on boot.
    try:
        run_once(cfg)
    except Exception as exc:
        log.exception("initial run failed: %s", exc)

    hour, minute = _parse_daily_time(cfg.daily_run_at)
    scheduler = BlockingScheduler(timezone=cfg.timezone)
    scheduler.add_job(
        lambda: run_once(cfg),
        CronTrigger(hour=hour, minute=minute, timezone=cfg.timezone),
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
    parser.add_argument(
        "--seed-cap",
        type=int,
        default=None,
        help=(
            "First-run backlog cap: send up to N features, silently mark the rest "
            "as explained so they never spam Telegram. Use once before installing "
            "the LaunchAgent."
        ),
    )
    parser.add_argument(
        "--backlog-flagship",
        action="store_true",
        help=(
            "Seed the backlog with a CURATED list of revolutionary features "
            "released on or after BACKLOG_CUTOFF_DATE. Sends the curated list "
            "(subagents / multi-agent orchestration first) and silently buries "
            "all other discovered features. Run this once before installing "
            "the LaunchAgent."
        ),
    )
    args = parser.parse_args()

    cfg = load_config()
    _configure_logging(cfg.log_level)

    if args.backlog_flagship:
        count = run_backlog_flagship(cfg, dry_run=args.dry_run)
        log.info("flagship backlog complete: %d feature(s) sent", count)
        return

    if args.once or args.dry_run:
        count = run_once(
            cfg,
            dry_run=args.dry_run,
            limit=args.limit,
            seed_cap=args.seed_cap,
        )
        log.info("run complete: %d feature(s) processed", count)
        return

    serve(cfg)


if __name__ == "__main__":
    cli()
