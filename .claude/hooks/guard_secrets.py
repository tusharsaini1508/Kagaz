#!/usr/bin/env python3
"""PreToolUse guard: keep secrets out of the model's context and out of git.

- Read/Edit/Write/NotebookEdit: deny when the target path is a secret file.
- Bash/PowerShell: deny commands that reference secret files, ask before dumping env.
- Allowed: .env.example / .env.sample / .env.template / .env.dist, and --env-file.
"""
import json
import re
import shlex
import sys

SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")
SECRET_BASENAMES = {
    ".envrc", ".netrc", ".git-credentials", ".pypirc", "credentials", "credentials.json",
    "kubeconfig", "secrets.json", "secrets.yaml", "secrets.yml", "secrets.toml",
}
KEY_PREFIXES = ("id_rsa", "id_dsa", "id_ecdsa", "id_ed25519")
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore",
                   ".tfstate", ".tfstate.backup")
SECRET_NAME_RES = [
    re.compile(r"^service[-_]?account.*\.json$", re.I),
    re.compile(r"^serviceaccountkey.*\.json$", re.I),
]
SECRET_DIRS = {"secrets", ".secrets", ".ssh", ".aws", ".gnupg", ".kube", ".azure"}
ENV_FILE_FLAGS = ("--env-file",)
RAW_ENV_RE = re.compile(r"(?<![\w.-])\.env(?:\.(?!example\b|sample\b|template\b|dist\b)[\w-]+)?(?![\w-])")
RAW_KEY_RE = re.compile(r"\bid_(?:rsa|dsa|ecdsa|ed25519)\b(?!\.pub)|\.ssh/|\.aws/credentials|\.git-credentials")
ENV_DUMP_RE = re.compile(r"^\s*(printenv|env|set|export\s+-p|Get-ChildItem\s+env:|gci\s+env:|dir\s+env:)\s*$", re.I)


def is_env_file(name: str) -> bool:
    lower = name.lower()
    if lower == ".env":
        return True
    if lower.startswith(".env."):
        return not lower.endswith(SAFE_ENV_SUFFIXES)
    return lower.endswith(".env") and not lower.startswith(".")


def secret_reason(path: str):
    if not path:
        return None
    norm = path.replace("\\", "/")
    parts = [p for p in norm.split("/") if p not in ("", ".", "..")]
    if not parts:
        return None
    name = parts[-1]
    lower = name.lower()
    if is_env_file(name):
        return f"'{name}' is an environment/secrets file"
    if lower in SECRET_BASENAMES or (lower.startswith(KEY_PREFIXES) and not lower.endswith(".pub")):
        return f"'{name}' is a credentials/key file"
    if lower.endswith(SECRET_SUFFIXES):
        return f"'{name}' looks like a private key, keystore, or Terraform state (contains secrets)"
    if any(rx.match(name) for rx in SECRET_NAME_RES):
        return f"'{name}' looks like a cloud service-account key"
    for d in parts[:-1]:
        if d.lower() in SECRET_DIRS:
            return f"'{norm}' is inside a secrets directory ('{d}/')"
    return None


def scan_command(cmd: str):
    spaced = re.sub(r"(\|\||&&|[|;&<>()`])", r" \1 ", cmd)
    try:
        tokens = shlex.split(spaced, posix=True)
    except ValueError:
        tokens = spaced.split()
    skip_next = False
    for raw in tokens:
        if skip_next:
            skip_next = False
            continue
        tok = raw.strip("'\"")
        if tok in ENV_FILE_FLAGS:
            skip_next = True
            continue
        if tok.startswith("--env-file="):
            continue
        reason = secret_reason(tok)
        if reason:
            return "deny", reason
    for m in RAW_ENV_RE.finditer(cmd):
        if "--env-file" not in cmd[max(0, m.start() - 14):m.start()]:
            return "deny", f"command references a secrets file ('{m.group(0)}')"
    if RAW_KEY_RE.search(cmd):
        return "deny", "command references SSH/cloud credential files"
    if ENV_DUMP_RE.match(cmd):
        return "ask", "dumps all environment variables into the transcript (may expose secrets)"
    return None


def emit(decision: str, reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("guard_secrets: could not parse hook input; skipping", file=sys.stderr)
        return 0

    tool = data.get("tool_name", "")
    tin = data.get("tool_input") or {}
    advice = (
        "Secrets must never enter the model context or git. If you need a value, ask the user "
        "to configure it. To document a new variable, add a placeholder to .env.example."
    )

    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        reason = secret_reason(tin.get("file_path") or tin.get("notebook_path") or "")
        if reason:
            emit("deny", f"Blocked by guard_secrets: {reason}. {advice}")
    elif tool in ("Bash", "PowerShell"):
        result = scan_command(tin.get("command") or "")
        if result:
            decision, reason = result
            prefix = "Blocked by guard_secrets" if decision == "deny" else "guard_secrets"
            emit(decision, f"{prefix}: {reason}. {advice}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
