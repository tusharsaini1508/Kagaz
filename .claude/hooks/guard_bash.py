#!/usr/bin/env python3
"""PreToolUse guard for Bash: deny catastrophic commands, ask before risky ones."""
import json
import re
import shlex
import sys

PROTECTED = re.compile(r"(^|[\s:+/])(main|master|trunk|develop|prod|production|release[\w./-]*)$")
CATASTROPHIC_TARGETS = {"/", "/*", "//", "/.", "~", "~/", "~/*", "$HOME", "$HOME/", "$HOME/*",
                        "${HOME}", "${HOME}/", ".", "./", "./*", "..", "../", "*", ".*"}
SYSTEM_DIR = re.compile(r"^/(bin|boot|dev|etc|home|lib|lib64|opt|proc|root|sbin|srv|sys|usr|var|"
                        r"Users|System|Applications|Library)/?\*?$")
PIPE_TO_SHELL = re.compile(
    r"\b(curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^\n]*\|\s*(sudo\s+)?"
    r"(ba|z|k|da|fi)?sh\b"
    r"|\b(curl|wget)\b[^\n]*\|\s*(sudo\s+)?(python3?|node|perl|ruby)\b"
    r"|\b(curl|wget|iwr|irm)\b[^\n]*\|\s*(iex|invoke-expression)\b"
    r"|\b(ba|z)?sh\s+<\(\s*(curl|wget)\b"
    r"|\beval\s+[\"']?\$\(\s*(curl|wget)\b", re.I)
FORK_BOMB = re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")
SQL_DROP = re.compile(r"\b(drop\s+(database|schema|table)|truncate\s+(table\s+)?[\w.\"]+)", re.I)
SQL_DELETE_ALL = re.compile(r"\bdelete\s+from\s+[\w.\"]+\s*(;|$|[\"'])", re.I)
INFRA_ASK = [
    (re.compile(r"\baws\s+s3\s+(rb|rm)\b.*--recursive|\baws\s+s3\s+rb\b", re.I), "deletes S3 data/buckets"),
    (re.compile(r"\bgsutil\s+(-m\s+)?rm\s+-r|\bgcloud\s+storage\s+rm\s+-r", re.I), "deletes cloud storage data"),
    (re.compile(r"\bgcloud\s+projects\s+delete|\baz\s+group\s+delete", re.I), "deletes a cloud project/resource group"),
    (re.compile(r"\bkubectl\s+delete\s+(ns|namespace|all)\b|\bkubectl\s+delete\b.*--all\b", re.I), "mass-deletes Kubernetes resources"),
    (re.compile(r"\bdocker\s+(system|volume)\s+prune\b|\bdocker\s+volume\s+rm\b", re.I), "deletes Docker volumes/data"),
    (re.compile(r"\bredis-cli\b.*\bflush(all|db)\b", re.I), "flushes Redis data"),
    (re.compile(r"\bdropdb\b|\bmongo(sh)?\b.*dropDatabase", re.I), "drops a database"),
]
WRAPPERS = {"time", "nohup", "nice", "command", "builtin", "exec", "noglob", "stdbuf", "xargs", "ionice"}
PIP_VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i", "--index-url",
                   "--extra-index-url", "-t", "--target", "--prefix", "-f", "--find-links", "--root",
                   "--src", "--python-version", "--platform", "--only-binary", "--no-binary"}
DEP_ADVICE = ("verify each exists on the official registry under this exact name, is maintained, widely "
              "used and license-compatible, and that existing deps/stdlib can't do the job")


def split_segments(cmd):
    parts = re.split(r"\|\||&&|;|\n|(?<![|>])\|(?!\|)|(?<![&>])&(?![&>])", cmd)
    subs = re.findall(r"\$\(([^()]*)\)", cmd) + re.findall(r"`([^`]*)`", cmd)
    return [p.strip() for p in parts + subs if p and p.strip()]


def tokenize(segment):
    try:
        toks = shlex.split(segment, posix=True)
    except ValueError:
        toks = segment.split()
    env = {}
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            k, _, v = t.partition("=")
            env[k] = v
            i += 1
        elif t in ("sudo", "doas"):
            env["__sudo__"] = "1"
            i += 1
        elif t == "env":
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or "=" in toks[i]):
                if "=" in toks[i]:
                    k, _, v = toks[i].partition("=")
                    env[k] = v
                i += 1
        else:
            break
    return toks[i:], env


def is_local(arg):
    return (arg in (".", "..") or arg.startswith(("./", "../", "/", "~", "file:"))
            or arg.endswith((".whl", ".tar.gz", ".zip")))


def decide(found, level, why):
    if why not in found[level]:
        found[level].append(why)


def check_rm(args, found):
    flags = [a for a in args if a.startswith("-") and a != "--"]
    targets = [a for a in args if not a.startswith("-")]
    if "--no-preserve-root" in flags:
        decide(found, "deny", "rm --no-preserve-root")
    recursive = any(f == "--recursive" or (not f.startswith("--") and "r" in f.lower()) for f in flags)
    if not recursive:
        return
    for t in targets:
        if t in CATASTROPHIC_TARGETS or SYSTEM_DIR.match(t):
            decide(found, "deny", f"recursive delete of '{t}' would destroy the project, home, or system")
        elif t.rstrip("/") in (".git", "./.git"):
            decide(found, "ask", "deletes the git repository history (.git)")


def check_git(args, env, found):
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 1
    if i >= len(args):
        return
    sub = args[i]
    rest = args[i + 1:]
    if env.get("HUSKY") in ("0", "false") or "SKIP" in env:
        decide(found, "deny", "HUSKY=0 / SKIP=... bypasses git hooks (secret scanning, linters)")
    if sub == "commit":
        if "--no-verify" in rest or "-n" in rest:
            decide(found, "deny", "git commit --no-verify/-n bypasses pre-commit hooks")
    elif sub == "push":
        if "--no-verify" in rest:
            decide(found, "deny", "git push --no-verify bypasses hooks")
        if any(a in ("--force", "--force-with-lease") for a in rest):
            decide(found, "ask", "force-push rewrites remote history")
    elif sub == "reset" and "--hard" in rest:
        decide(found, "ask", "git reset --hard discards uncommitted work")
    elif sub == "clean" and any(re.match(r"^-[A-Za-z]*f", a) for a in rest):
        decide(found, "ask", "git clean -f permanently deletes untracked files")
    elif sub in ("filter-branch", "filter-repo"):
        decide(found, "ask", "rewrites git history")
    elif sub == "add" and any(a in ("-f", "--force") for a in rest):
        decide(found, "ask", "force-adds ignored files (may include secrets or build artifacts)")


def check_deps(prog, args, found):
    pkgs = []
    if prog in ("npm", "pnpm", "yarn", "bun"):
        if args and args[0] in ("install", "i", "add", "in"):
            pkgs = [a for a in args[1:] if not a.startswith("-") and not is_local(a)]
    elif prog in ("pip", "pip3") and args[:1] == ["install"]:
        pkgs = [a for a in args[1:] if not a.startswith("-") and not is_local(a)]
    elif prog in ("uv", "poetry", "pipenv", "conda") and args[:1] == ["add"]:
        pkgs = [a for a in args[1:] if not a.startswith("-") and not is_local(a)]
    elif prog in ("apt", "apt-get", "yum", "dnf", "brew", "choco", "winget") and args[:1] in (["install"], ["add"], ["-S"]):
        pkgs = [a for a in args[1:] if not a.startswith("-")]
    if pkgs:
        decide(found, "ask", f"adds new dependencies {pkgs[:6]} — {DEP_ADVICE}")


def check_segment(seg, found, depth=0):
    argv, env = tokenize(seg)
    if not argv:
        return
    prog = argv[0].rsplit("/", 1)[-1].lower()
    args = argv[1:]
    if env.get("__sudo__"):
        decide(found, "ask", "runs with sudo (elevated privileges)")
    if prog in ("bash", "sh", "zsh") and "-c" in args and depth < 2:
        idx = args.index("-c")
        if idx + 1 < len(args):
            for inner in split_segments(args[idx + 1]):
                check_segment(inner, found, depth + 1)
    if prog == "rm":
        check_rm(args, found)
    elif prog == "git":
        check_git(args, env, found)
    elif prog.startswith("mkfs") or prog in ("fdisk", "parted", "wipefs"):
        decide(found, "deny", "formats or repartitions a disk")
    elif prog == "dd" and any(a.startswith("of=/dev/") for a in args):
        decide(found, "deny", "dd writes directly to a device")
    elif prog in ("python", "python3", "py") and args[:2] == ["-m", "pip"]:
        check_deps("pip", args[2:], found)
    else:
        check_deps(prog, args, found)
    if re.search(r">\s*/dev/(sd[a-z]|nvme\d|hd[a-z]|disk\d|xvd[a-z])", seg):
        decide(found, "deny", "writes to a raw disk device")
    if SQL_DROP.search(seg):
        decide(found, "ask", "destructive SQL (DROP/TRUNCATE) — confirm the target database and that a backup exists")
    if SQL_DELETE_ALL.search(seg):
        decide(found, "ask", "DELETE without a WHERE clause")
    for rx, why in INFRA_ASK:
        if rx.search(seg):
            decide(found, "ask", why)


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("guard_bash: could not parse hook input; skipping", file=sys.stderr)
        return 0

    if data.get("tool_name") != "Bash":
        return 0

    cmd = (data.get("tool_input") or {}).get("command") or ""
    if not cmd.strip():
        return 0

    found = {"deny": [], "ask": []}
    if FORK_BOMB.search(cmd):
        decide(found, "deny", "fork bomb")
    if PIPE_TO_SHELL.search(cmd):
        decide(found, "deny", "pipes downloaded content straight into an interpreter — download, inspect, and verify a checksum first")
    for seg in split_segments(cmd):
        check_segment(seg, found)

    if found["deny"]:
        decision = "deny"
        reason = "Blocked by guard_bash: " + "; ".join(found["deny"]) + ". Do not work around this; explain why it's needed and let the user run it."
    elif found["ask"]:
        decision = "ask"
        reason = "guard_bash: " + "; ".join(found["ask"])
    else:
        return 0

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
