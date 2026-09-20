"""Daily latest-version checks with staged validation and bounded retry-on-use."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime
from email.parser import BytesParser
from importlib.metadata import version
from pathlib import Path

from filelock import FileLock, Timeout
from grok_client import DEFAULT_CONFIG, atomic_write
from packaging.version import Version

PACKAGE = "XClientTransaction"
PACKAGE_SPEC = "XClientTransaction>=1.0.3"
SKILL_DIR = Path(__file__).resolve().parents[1]
RETRY_SECONDS = 3600
STATE_NAME = ".x-grok-transaction-maintenance.json"


class MaintenanceError(Exception):
    pass


def managed_environment() -> bool:
    prefix = Path(sys.prefix).resolve()
    allowed = {
        (SKILL_DIR / ".venv").resolve(),
        (Path.home() / ".local/share/x-grok-client/.venv").resolve(),
    }
    return sys.prefix != sys.base_prefix and prefix in allowed


def run(arguments: list[str], *, timeout=180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [sys.executable, *arguments], capture_output=True, text=True, timeout=timeout
        )
    except (subprocess.TimeoutExpired, OSError):
        raise MaintenanceError(
            "The maintenance subprocess timed out or could not run; raw logs were withheld."
        ) from None


def pip(*arguments: str) -> None:
    result = run(["-m", "pip", "--disable-pip-version-check", "--no-input", *arguments])
    if result.returncode != 0:
        raise MaintenanceError(
            "pip failed; check the dedicated environment, network, package index, and dependency compatibility."
        )


def probe(config: Path, *, target: Path | None = None) -> dict:
    script = str(SKILL_DIR / "scripts/grok_client.py")
    if target is None:
        arguments = [script, "--config", str(config), "check-transaction"]
    else:
        code = "import runpy,sys;target,script,config=sys.argv[1:];sys.path.insert(0,target);sys.argv=[script,'--config',config,'check-transaction'];runpy.run_path(script,run_name='__main__')"
        arguments = ["-c", code, str(target), script, str(config)]
    result = run(arguments, timeout=130)
    try:
        data = json.loads(result.stdout if result.returncode == 0 else result.stderr)
    except (ValueError, TypeError):
        raise MaintenanceError("The transaction ID probe returned no valid result.") from None
    if not isinstance(data, dict) or (result.returncode == 0 and data.get("ok") is not True):
        raise MaintenanceError("The transaction ID probe returned an invalid result structure.")
    return data


def download(spec: str, destination: Path) -> Path:
    destination.mkdir()
    pip("download", "--no-deps", "--only-binary=:all:", "--dest", str(destination), spec)
    wheels = list(destination.glob("*.whl"))
    if len(wheels) != 1:
        raise MaintenanceError("Package download did not return exactly one wheel.")
    return wheels[0]


def wheel_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise MaintenanceError("Invalid candidate package metadata.")
        data = BytesParser().parsebytes(archive.read(names[0]))
    if data.get("Name", "").lower().replace("-", "").replace("_", "") != PACKAGE.lower():
        raise MaintenanceError("The candidate package name does not match.")
    value = data.get("Version", "")
    if Version(value).is_prerelease or Version(value).is_devrelease:
        raise MaintenanceError("Automatic maintenance does not install prerelease versions.")
    return value


def maintain_locked(config: Path) -> dict:
    """Caller holds the environment lock, including during the following Grok call."""
    state = Path(sys.prefix) / STATE_NAME
    now = time.time()
    today = datetime.now().astimezone().date().isoformat()
    previous = {}
    if state.exists():
        try:
            previous = json.loads(state.read_text())
            attempted = float(previous["attempted_at"])
            if not math.isfinite(attempted):
                raise ValueError()
        except (OSError, ValueError, TypeError, KeyError):
            raise MaintenanceError(
                "The maintenance record is invalid; stopped. Inspect it manually."
            ) from None
        if previous.get("status") in {"installing", "rollback_failed"}:
            raise MaintenanceError(
                "The previous upgrade was interrupted or rollback failed; repair the dedicated environment before calling again."
            )
        if previous.get("checked_day") == today:
            return {"ok": True, "usable": True, "status": "already_checked"}
        if (
            previous.get("status") not in {"up_to_date", "updated"}
            and now - attempted < RETRY_SECONDS
        ):
            return {
                "ok": False,
                "usable": True,
                "status": "retry_deferred",
                "next_attempt_at": attempted + RETRY_SECONDS,
            }

    old = version(PACKAGE)
    record = {"attempted_at": now, "previous_version": old, "status": "checking"}
    atomic_write(state, json.dumps(record))

    def finish(status: str, *, success=False, usable=True, new=None) -> dict:
        record.update(status=status)
        if success:
            record["checked_day"] = today
        if new is not None:
            record["version"] = new
        atomic_write(state, json.dumps(record))
        result = {
            "ok": success,
            "usable": usable,
            "status": status,
            "previous_version": old,
            "version": new or old,
            "request_replayed": False,
        }
        if not success:
            result["next_attempt_at"] = now + RETRY_SECONDS
        return result

    with tempfile.TemporaryDirectory(prefix="x-grok-package-check-") as folder:
        root = Path(folder)
        try:
            candidate = download(PACKAGE_SPEC, root / "candidate")
            new = wheel_version(candidate)
            if Version(new) <= Version(old):
                return finish("up_to_date", success=True, new=old)
            pip("check")
            trial = root / "trial"
            pip("install", "--no-deps", "--no-index", "--target", str(trial), str(candidate))
            tested = probe(config, target=trial)
            if not tested.get("ok") or tested.get("version") != new:
                return finish("candidate_validation_failed")
            backup = download(f"{PACKAGE}=={old}", root / "backup")
            if wheel_version(backup) != old:
                raise MaintenanceError("The backup does not match the installed version.")
        except Exception:
            return finish("check_failed")

        record["status"] = "installing"
        atomic_write(state, json.dumps(record))
        try:
            pip("install", "--force-reinstall", "--no-deps", "--no-index", str(candidate))
            pip("check")
            tested = probe(config)
            if not tested.get("ok") or tested.get("version") != new or version(PACKAGE) != new:
                raise MaintenanceError("Post-installation validation failed.")
        except Exception:
            try:
                pip("install", "--force-reinstall", "--no-deps", "--no-index", str(backup))
                pip("check")
                if version(PACKAGE) != old:
                    raise MaintenanceError("The rollback version does not match.")
            except Exception:
                return finish("rollback_failed", usable=False)
            return finish("rolled_back")
        result = finish("updated", success=True, new=new)
        result.update(transaction_id_generated=True, server_acceptance_checked=False)
        return result


@contextmanager
def runtime_maintenance(config: Path):
    if not managed_environment():
        yield {"ok": True, "usable": True, "status": "unmanaged_environment"}
        return
    try:
        with FileLock(str(Path(sys.prefix) / ".x-grok-runtime.lock"), timeout=0, mode=0o600):
            result = maintain_locked(config)
            if not result["usable"]:
                raise MaintenanceError(
                    "Dependency rollback failed; Grok calls have stopped. Repair the dedicated environment."
                )
            yield result
    except Timeout:
        raise MaintenanceError(
            "This environment is processing another call or update; no Grok request was sent."
        ) from None


def update(config: Path) -> dict:
    if not managed_environment():
        raise MaintenanceError(
            "Automatic updates require the project .venv or ~/.local/share/x-grok-client/.venv."
        )
    with runtime_maintenance(config) as result:
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    args = parser.parse_args()
    try:
        result = update(Path(args.config).expanduser().resolve())
    except MaintenanceError as exc:
        result = {"ok": False, "error": "maintenance_failed", "message": str(exc)}
    except Exception:
        result = {
            "ok": False,
            "error": "maintenance_failed",
            "message": "Unexpected maintenance error; check the environment and maintenance record.",
        }
    print(
        json.dumps(result, ensure_ascii=False), file=sys.stdout if result.get("ok") else sys.stderr
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
