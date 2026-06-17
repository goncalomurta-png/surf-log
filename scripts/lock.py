#!/usr/bin/env python3
"""
Lockfile para coordenação Builder/Auditor/Codex.

Uso:
  python3 scripts/lock.py check               → FREE | LOCKED:<role>:<s>s
  python3 scripts/lock.py acquire <role>      → ACQUIRED:<role> | LOCKED:<role>:<s>s
  python3 scripts/lock.py release <role>      → RELEASED | NOT_OWNER
  python3 scripts/lock.py refresh <role>      → REFRESHED | NOT_OWNER

O lock expira automaticamente após 5 minutos (evita bloqueio por crash).
"""
import json, sys, time
from pathlib import Path

LOCK_FILE = Path(__file__).parent.parent / ".claude" / "active.lock"
MAX_AGE   = 300  # 5 minutos


def _read():
    try:
        return json.loads(LOCK_FILE.read_text())
    except Exception:
        return None


def _write(data):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps(data))


def _remaining(data):
    return max(0, int(MAX_AGE - (time.time() - data.get("ts", 0))))


def main():
    cmd  = sys.argv[1] if len(sys.argv) > 1 else "check"
    role = sys.argv[2] if len(sys.argv) > 2 else ""

    if cmd == "check":
        data = _read()
        if data and _remaining(data) > 0:
            print(f"LOCKED:{data['role']}:{_remaining(data)}s")
            sys.exit(1)
        print("FREE")

    elif cmd == "acquire":
        data = _read()
        if data and _remaining(data) > 0 and data.get("role") != role:
            print(f"LOCKED:{data['role']}:{_remaining(data)}s")
            sys.exit(1)
        _write({"role": role, "ts": time.time()})
        print(f"ACQUIRED:{role}")

    elif cmd == "release":
        data = _read()
        if data and data.get("role") == role:
            LOCK_FILE.unlink(missing_ok=True)
            print(f"RELEASED:{role}")
        else:
            print("NOT_OWNER")
            sys.exit(1)

    elif cmd == "refresh":
        data = _read()
        if data and data.get("role") == role:
            data["ts"] = time.time()
            _write(data)
            print(f"REFRESHED:{role}")
        else:
            print("NOT_OWNER")
            sys.exit(1)

    else:
        print(f"comando desconhecido: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
