#!/usr/bin/env python3
"""Check upstream GitHub repos for all recipes/*/recipe.json and emit CI build matrices."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gh_get_json(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "oldcook-upstream-checker",
    }
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fetch_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "oldcook-upstream-checker"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_github_slug(repo_url: str) -> str:
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", repo_url)
    if not m:
        raise ValueError(f"Unsupported non-GitHub repo URL: {repo_url}")
    return m.group(1)


def extract_flutter_version(pubspec_text: str) -> str | None:
    # Matches `flutter: 3.47.9` or `flutter: "3.47.9"` under `environment:`
    m = re.search(r"^\s{2}flutter\s*:\s*['\"]?([0-9]+\.[0-9]+\.[0-9]+)['\"]?\s*$", pubspec_text, re.M)
    return m.group(1) if m else None


def engine_release_exists(self_repo: str | None, flutter_ver: str) -> bool:
    if not self_repo or not flutter_ver:
        return False
    tag = f"engine-{flutter_ver}-ios12"
    data = gh_get_json(f"https://api.github.com/repos/{self_repo}/releases/tags/{tag}")
    return bool(data and data.get("assets"))


def check_one_recipe(recipe_dir: Path, self_repo: str | None, force: bool) -> dict:
    cfg = json.loads((recipe_dir / "recipe.json").read_text(encoding="utf-8"))
    state_file = recipe_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {}

    slug = parse_github_slug(cfg["repo"])
    track = cfg.get("track", "release")
    resolved_ref = cfg.get("ref", "main")

    if track == "release":
        rel = gh_get_json(f"https://api.github.com/repos/{slug}/releases/latest")
        if isinstance(rel, dict) and rel.get("tag_name"):
            resolved_ref = rel["tag_name"]
        else:
            commit = gh_get_json(f"https://api.github.com/repos/{slug}/commits/{resolved_ref}")
            if isinstance(commit, dict) and commit.get("sha"):
                resolved_ref = commit["sha"][:12]
    else:
        commit = gh_get_json(f"https://api.github.com/repos/{slug}/commits/{resolved_ref}")
        if isinstance(commit, dict) and commit.get("sha"):
            resolved_ref = commit["sha"][:12]

    flutter_ver = None
    if cfg.get("type", "flutter") == "flutter":
        pubspec = fetch_text(f"https://raw.githubusercontent.com/{slug}/{resolved_ref}/pubspec.yaml")
        if pubspec:
            flutter_ver = extract_flutter_version(pubspec)

    changed = force or (state.get("last_built_ref") != resolved_ref)
    has_engine = engine_release_exists(self_repo, flutter_ver) if flutter_ver else True

    return {
        "recipe": recipe_dir.name,
        "name": cfg.get("name", recipe_dir.name),
        "upstream_slug": slug,
        "resolved_ref": resolved_ref,
        "previous_ref": state.get("last_built_ref"),
        "flutter_version": flutter_ver or "stable",
        "needs_build": changed,
        "needs_engine_build": bool(flutter_ver and not has_engine),
    }


def record_success(recipe_name: str, ref: str, flutter_ver: str) -> None:
    state_file = ROOT / "recipes" / recipe_name / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "last_built_ref": ref,
                "last_flutter_version": flutter_ver,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[ok] Recorded state in {state_file}: ref={ref}, flutter={flutter_ver}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", help="GitHub owner/repo of this factory (checks prebuilt engine releases)")
    ap.add_argument("--force", default="", help="Comma-separated recipe names (or 'all') to force rebuild")
    ap.add_argument("--github-output", type=Path, help="Path to $GITHUB_OUTPUT file")
    ap.add_argument("--record-success", help="Recipe name to update state.json after a passing build")
    ap.add_argument("--ref", help="Upstream ref for --record-success")
    ap.add_argument("--flutter", default="", help="Flutter version for --record-success")
    args = ap.parse_args()

    if args.record_success:
        if not args.ref:
            print("[err] --ref is required with --record-success", file=sys.stderr)
            return 1
        record_success(args.record_success, args.ref, args.flutter)
        return 0

    force_set = {x.strip() for x in args.force.split(",") if x.strip()}
    recipes_root = ROOT / "recipes"
    checks = []

    for rdir in sorted(recipes_root.iterdir()):
        if not (rdir / "recipe.json").exists():
            continue
        do_force = ("all" in force_set) or (rdir.name in force_set)
        info = check_one_recipe(rdir, args.repo, force=do_force)
        checks.append(info)
        status = "UPDATE" if info["needs_build"] else "UP-TO-DATE"
        print(
            f"[{status}] {info['recipe']}: upstream={info['resolved_ref']} "
            f"(prev={info['previous_ref']}) flutter={info['flutter_version']} "
            f"needs_engine={info['needs_engine_build']}"
        )

    to_build = [c for c in checks if c["needs_build"]]
    engines = sorted({c["flutter_version"] for c in to_build if c["needs_engine_build"] and c["flutter_version"] != "stable"})

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as out:
            out.write(f"has_updates={'true' if to_build else 'false'}\n")
            out.write(f"has_engines={'true' if engines else 'false'}\n")
            out.write(f"engines_matrix={json.dumps(engines)}\n")
            out.write(f"recipes_matrix={json.dumps(to_build)}\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
