from __future__ import annotations

import re
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from src.config import ROBOTS_TIMEOUT_SECONDS, ROBOTS_URL, USER_AGENT


class RobotsUnverifiedError(RuntimeError):
    """Raised when robots.txt cannot be fetched or parsed."""


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    body = re.escape(pattern)
    body = body.replace(r"\*", ".*")
    if body.endswith(r"\$"):
        body = body[:-2] + "$"
        return re.compile("^" + body)
    return re.compile("^" + body)


def _path_query(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _rules_for_star(text: str) -> tuple[list[str], list[str]]:
    allows: list[str] = []
    disallows: list[str] = []
    in_star = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            if in_star:
                continue
            continue
        lowered = line.lower()
        if lowered.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            in_star = agent == "*"
            continue
        if not in_star:
            continue
        if lowered.startswith("disallow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                disallows.append(value)
        elif lowered.startswith("allow:"):
            value = line.split(":", 1)[1].strip()
            if value:
                allows.append(value)
        elif lowered.startswith("user-agent:"):
            in_star = False
    return allows, disallows


class RobotsPolicy:
    def __init__(self, text: str, user_agent: str) -> None:
        if not text.strip():
            raise RobotsUnverifiedError("robots.txt was empty; scrape aborted")
        self.text = text
        self.user_agent = user_agent
        self.parser = RobotFileParser()
        self.parser.set_url(ROBOTS_URL)
        try:
            self.parser.parse(text.splitlines())
        except Exception as exc:
            raise RobotsUnverifiedError(
                f"Could not parse robots.txt ({exc}). Scrape aborted."
            ) from exc
        allows, disallows = _rules_for_star(text)
        self.allow_patterns = [(_pattern_to_regex(p), p) for p in allows]
        self.disallow_patterns = [(_pattern_to_regex(p), p) for p in disallows]

    def can_fetch(self, url: str) -> bool:
        path = _path_query(url)
        allow_len = max(
            (len(pattern) for regex, pattern in self.allow_patterns if regex.search(path)),
            default=0,
        )
        disallow_len = max(
            (len(pattern) for regex, pattern in self.disallow_patterns if regex.search(path)),
            default=0,
        )
        if disallow_len and disallow_len >= allow_len:
            return False
        if allow_len:
            return True
        try:
            return bool(self.parser.can_fetch(self.user_agent, url))
        except Exception:
            return False


def load_robots(session: requests.Session) -> RobotsPolicy:
    try:
        response = session.get(ROBOTS_URL, timeout=ROBOTS_TIMEOUT_SECONDS)
        response.raise_for_status()
        return RobotsPolicy(response.text, USER_AGENT)
    except requests.RequestException as exc:
        raise RobotsUnverifiedError(
            f"Could not verify robots.txt ({exc}). Scrape aborted."
        ) from exc
