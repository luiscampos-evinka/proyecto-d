#!/usr/bin/env python3
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def project_home() -> Path:
    raw = os.getenv('PROYECTO_D_HOME')
    return Path(raw).expanduser().resolve() if raw else REPO_ROOT


def default_config_path() -> Path:
    raw = os.getenv('PROYECTO_D_CONFIG')
    if raw:
        return Path(raw).expanduser().resolve()
    return (project_home() / 'config' / 'config.json').resolve()


def resolve_path(value, *, config_path: str | Path | None = None, base_dir: str | Path | None = None) -> Path | None:
    if value in (None, ''):
        return None
    expanded = os.path.expandvars(str(value))
    path = Path(expanded).expanduser()
    if path.is_absolute():
        return path.resolve()
    anchor = Path(base_dir).expanduser().resolve() if base_dir else None
    if anchor is None and config_path:
        anchor = Path(config_path).expanduser().resolve().parent
    if anchor is None:
        anchor = project_home()
    return (anchor / path).resolve()


def runtime_path(config: dict, key: str, default_value: str) -> Path:
    runtime = config.get('runtime') or {}
    config_path = config.get('_config_path')
    return resolve_path(runtime.get(key, default_value), config_path=config_path)


def session_registry_roots(config: dict) -> list[Path]:
    runtime = config.get('runtime') or {}
    roots = runtime.get('session_registry_roots') or []
    if not roots:
        env_value = os.getenv('PROYECTO_D_SESSION_ROOTS')
        if env_value:
            roots = [item for item in env_value.split(os.pathsep) if item]
    if not roots:
        roots = ['~/.openclaw/agents']
    out = []
    for item in roots:
        path = resolve_path(item, config_path=config.get('_config_path'))
        if path:
            out.append(path)
    return out
