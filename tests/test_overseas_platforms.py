# -*- coding: utf-8 -*-
"""海外平台技能（skill-x-publisher / skill-x-reply / skill-global-*）与共享脚本的离线 selftest。"""
import os
import subprocess
import sys
from pathlib import Path

EASEL = Path(__file__).resolve().parents[1]
SKILLS = EASEL / "skills" / "builtin"
SHARED = EASEL / "skills" / "shared" / "scripts"


def run_selftest(script):
    env = dict(os.environ, EASEL_ROOT=str(EASEL), EASEL_NO_NOTIFY="1")
    env.pop("X_BEARER_TOKEN", None)
    return subprocess.run([sys.executable, str(script), "selftest"],
                          capture_output=True, text=True, env=env)


def test_cadence_gate_selftest():
    r = run_selftest(SHARED / "cadence_gate.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_deai_check_selftest():
    r = run_selftest(SHARED / "deai_check.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_x_reply_selftest():
    r = run_selftest(SKILLS / "skill-x-reply" / "scripts" / "x_reply.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_x_auto_selftest_offline():
    r = run_selftest(SKILLS / "skill-x-reply" / "scripts" / "x_auto.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_x_post_selftest():
    r = run_selftest(SKILLS / "skill-x-publisher" / "scripts" / "x_post.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_x_news_selftest():
    r = run_selftest(SKILLS / "skill-x-publisher" / "scripts" / "x_news.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_global_topics_subreddit_mode_registered():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "global_topics_t", SKILLS / "skill-global-creator" / "scripts" / "global_topics.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "subreddit_top") and callable(mod.subreddit_top)


def test_all_skills_have_easel_meta():
    names = ["skill-x-publisher", "skill-x-reply", "skill-global-creator", "skill-global-deai",
             "skill-linkedin-publisher", "skill-blogger-publisher", "skill-reddit-gaming"]
    for n in names:
        assert (SKILLS / n / "EASEL-META.md").is_file(), n
