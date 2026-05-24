# claude-storyteller

A small Python service that watches for new Claude features (API, Claude
Code CLI, Claude apps, SDKs) and explains each one as a short, vivid story
a secondary-school student could follow. Each story is grounded in your own
GitHub repositories: the bot suggests how the feature could be *applied* to
one of your repos and how it could *enhance* something a repo already does.
Stories are delivered to your Telegram, and the bot never explains the same
feature twice.

Designed to run on a Mac mini as a macOS LaunchAgent so it survives reboots.

## How it works

```
launchd  ─►  claude_storyteller (Python, runs forever)
              │
              ├── APScheduler: daily run at DAILY_RUN_AT (default 09:00)
              ├── Feature discovery (4 sources, union + dedupe):
              │     • docs.claude.com changelog pages
              │     • Anthropic news RSS
              │     • GitHub releases for anthropics/claude-code
              │     • A "what's new" probe to Claude itself
              ├── Dedupe: state/explained.json in this same repo
              ├── Storyteller: claude-sonnet-4-6 writes the story + ideas
              ├── Telegram: one message per new feature
              └── Commit + push the updated state file
```

## Quick start (Mac mini)

1. **Clone the repo:**
   ```bash
   git clone https://github.com/kengyit/claude_update_story.git ~/code/claude_update_story
   cd ~/code/claude_update_story
   ```

2. **Install uv** (Python project manager):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Set up your secrets:**
   ```bash
   mkdir -p ~/.config/claude-storyteller
   cp .env.example ~/.config/claude-storyteller/.env
   $EDITOR ~/.config/claude-storyteller/.env
   ```
   You will need:
   - `ANTHROPIC_API_KEY` — from console.anthropic.com (with billing enabled)
   - `TELEGRAM_BOT_TOKEN` — create a bot via @BotFather on Telegram
   - `TELEGRAM_CHAT_ID` — your personal chat id (@userinfobot tells you)
   - `GITHUB_TOKEN` — classic PAT with `repo` scope (needed for private repos)
   - `GITHUB_USERNAME` — your GitHub login

4. **Smoke-test without sending anything:**
   ```bash
   uv run python -m claude_storyteller.main --dry-run --limit 1
   ```
   This prints one generated story to stdout. Nothing is sent or committed.

5. **Send one real message to make sure Telegram works end-to-end:**
   ```bash
   uv run python -m claude_storyteller.main --once --limit 1
   ```

6. **Install as a LaunchAgent so it auto-starts on every reboot:**
   ```bash
   ./deploy/install.sh
   ```
   This renders the plist, registers it with `launchctl`, and kickstarts it.
   The service will (a) immediately do a catch-up run, and (b) trigger
   daily at `DAILY_RUN_AT` from then on.

7. **Verify it survives a reboot:**
   ```bash
   sudo shutdown -r now      # then after reboot:
   launchctl list | grep claude-storyteller
   tail -f ~/Library/Logs/claude-storyteller.out.log
   ```

## Command-line flags

| Flag | What it does |
|---|---|
| (no flags) | Long-running service: catch-up + daily schedule |
| `--once` | Do one discovery+send pass and exit |
| `--dry-run` | Generate stories but do NOT send to Telegram or commit |
| `--limit N` | Cap to N features this run (useful for testing) |

## First-run backlog

The first time the service runs, `state/explained.json` is empty, so every
feature it discovers (50–100+) is new. The bot will send them one-by-one
with a 3-second pause between messages. Expect Telegram to be busy for
several minutes; from day 2 onward it's incremental.

If you'd rather drip-feed the backlog instead, edit `DAILY_RUN_AT` and use
`--limit 5` runs manually until caught up.

## State / dedupe

`state/explained.json` is committed back to this repo after every run.
That means:
- you can browse on GitHub to see what's been explained
- nothing is duplicated if the Mac mini is reinstalled
- no local DB to back up

## Project layout

```
src/claude_storyteller/
├── main.py                # CLI + scheduler
├── config.py              # loads .env
├── sources/               # feature discovery (one file per source)
├── github_repos.py        # list your repos for the prompt
├── storyteller.py         # Anthropic call that writes the story
├── dedupe.py              # explained.json read/write
├── state_repo.py          # git clone/pull/commit/push
└── telegram_bot.py        # Telegram delivery with retry
deploy/
├── com.kengyit.claude-storyteller.plist   # LaunchAgent template
├── install.sh             # render + launchctl bootstrap
└── uninstall.sh
```

## Uninstall

```bash
./deploy/uninstall.sh
```

## License

MIT
