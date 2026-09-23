# .claude

Shared Claude Code configuration for this repository. It is committed on purpose:
these are guardrails the whole team relies on, not personal preferences.

```
settings.json        permission rules and the hooks below. Shared.
settings.local.json  your own overrides. Gitignored, never committed.
hooks/               scripts that run before a tool call and can block it
skills/              repeatable procedures Tushar runs by name
```

## Hooks

Both run before a tool call and can deny it or ask first. Neither makes a
network call, and neither reads or writes any file. They take the pending tool
call on standard input and print a decision. If anything goes wrong they allow
the call rather than blocking work.

| Hook | Runs on | What it stops |
|---|---|---|
| `guard_secrets.py` | Read, Edit, Write, Bash, PowerShell | Opening or referencing `.env` files, private keys, cloud credentials, Terraform state. Asks before dumping all environment variables |
| `guard_bash.py` | Bash | Recursive deletes of the project, home or system directories. Piping a download straight into a shell. Writing to a raw disk. Bypassing git hooks. Asks before force pushes, destructive SQL, cloud deletions and new dependencies |

They need Python on the path. The command tries `python3` first, then `python`,
which is what Windows machines have.

## Skills

Run them by name in Claude Code.

| Skill | When |
|---|---|
| `/sprint-prd` | Day 1 of a sprint. Drafts `docs/prd/sprint-N.md` for Tushar to rewrite in his own words |
| `/pr-check` | Before opening any pull request. Checks the branch against the rules and reports READY or FIX FIRST |

## Changing anything in here

`.claude/` is owned by Vrushit in CODEOWNERS, so any change needs his review.
This matters more than usual: these files run on a maintainer's machine, and
the repository is public, so anyone can propose a change to them.
