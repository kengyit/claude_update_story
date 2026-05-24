from __future__ import annotations

import logging
from pathlib import Path

from git import Repo
from tenacity import retry, stop_after_attempt, wait_exponential

log = logging.getLogger(__name__)


class StateRepo:
    def __init__(
        self,
        *,
        workdir: Path,
        repo_full_name: str,
        branch: str,
        github_token: str,
    ) -> None:
        self.workdir = workdir
        self.repo_full_name = repo_full_name
        self.branch = branch
        self._token = github_token
        self._repo: Repo | None = None

    @property
    def _remote_url(self) -> str:
        return f"https://x-access-token:{self._token}@github.com/{self.repo_full_name}.git"

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        reraise=True,
    )
    def ensure(self) -> Repo:
        if self._repo is not None:
            return self._repo

        if (self.workdir / ".git").exists():
            self._repo = Repo(self.workdir)
            with self._repo.config_writer() as cw:
                cw.set_value("remote \"origin\"", "url", self._remote_url)
            try:
                self._repo.remotes.origin.fetch(self.branch)
                self._repo.git.checkout(self.branch)
                self._repo.remotes.origin.pull(self.branch)
            except Exception as exc:
                log.warning("pull failed (%s); continuing with local copy", exc)
            return self._repo

        self.workdir.parent.mkdir(parents=True, exist_ok=True)
        log.info("cloning %s into %s", self.repo_full_name, self.workdir)
        self._repo = Repo.clone_from(
            self._remote_url,
            self.workdir,
            branch=self.branch,
        )
        return self._repo

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=16),
        reraise=True,
    )
    def commit_and_push(self, message: str, *, author_name: str, author_email: str) -> bool:
        repo = self.ensure()
        repo.git.add(A=True)
        if not repo.is_dirty(untracked_files=True):
            log.info("no state changes to commit")
            return False
        with repo.config_writer() as cw:
            cw.set_value("user", "name", author_name)
            cw.set_value("user", "email", author_email)
        repo.index.commit(message)
        repo.remotes.origin.push(self.branch)
        log.info("pushed state update to %s@%s", self.repo_full_name, self.branch)
        return True
