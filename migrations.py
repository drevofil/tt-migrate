#!/usr/bin/env python3
"""
Скрипт для автоматического применения миграций Tarantool EE через утилиту tt.
Работает с плоской структурой директорий (файлы .lua непосредственно в MIGRATIONS_DIR).
Все локальные миграции публикуются (каждый файл отдельно) и затем применяются по очереди.
Если в хранилище есть миграции, отсутствующие локально, выводится предупреждение
(можно подавить через QUIET_EXTRA). Применяются только локальные миграции.

Все параметры задаются через переменные окружения.

Переменные окружения:
  TT_BIN                             - путь к исполняемому файлу tt (по умолчанию: tt)
  TARANTOOL_CONFIG_URI                - URI config storage (обязательная)
  MIGRATIONS_DIR                      - директория с Lua-файлами миграций (по умолчанию: migrations)
  QUIET_EXTRA                         - если "true"/"1"/"yes", не выводить предупреждение о лишних миграциях
  LOG_LEVEL                           - уровень логирования (DEBUG, INFO, WARNING, ERROR; по умолчанию INFO)
  DEBUG                                - если установлена в "1" или "true", включает DEBUG уровень (переопределяет LOG_LEVEL)

  TT_CLI_CONFIG_STORAGE_USERNAME      - имя пользователя для config storage (опционально)
  TT_CLI_CONFIG_STORAGE_PASSWORD      - пароль для config storage (опционально)
  TT_CLI_USERNAME                     - имя пользователя для Tarantool кластера (опционально)
  TT_CLI_PASSWORD                     - пароль для Tarantool кластера (опционально)

  SSL-параметры для подключения к Tarantool кластеру (опционально):
    TT_CLI_SSL_CERTFILE               --tarantool-sslcertfile
    TT_CLI_SSL_KEYFILE                --tarantool-sslkeyfile
    TT_CLI_SSL_CAFILE                 --tarantool-sslcafile
    TT_CLI_SSL_CIPHERS                --tarantool-sslciphers
    TT_CLI_SSL_PASSWORD               --tarantool-sslpassword
    TT_CLI_SSL_PASSWORDFILE           --tarantool-sslpasswordfile
    TT_CLI_USE_SSL                    --tarantool-use-ssl (если переменная равна "true" или "1")

  Таймауты (опционально):
    TT_CLI_CONNECT_TIMEOUT            --tarantool-connect-timeout (секунды)
    TT_CLI_EXECUTION_TIMEOUT          --execution-timeout (секунды)
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Set

# Настройка логирования
def setup_logging():
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
        log_level = "DEBUG"
    numeric_level = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(level=numeric_level, format="%(levelname)s: %(message)s")

setup_logging()
logger = logging.getLogger("tarantool-migrations")

def get_tt_bin() -> str:
    """Возвращает путь к исполняемому файлу tt."""
    return os.environ.get("TT_BIN", "tt")

def run_cmd(cmd: List[str], check: bool = True) -> None:
    """Выполняет команду, выводя её stdout/stderr в консоль. При ошибке завершает скрипт."""
    logger.debug("Running: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=check, text=True, capture_output=False)
    except subprocess.CalledProcessError as e:
        logger.error("Command failed with exit code %d", e.returncode)
        sys.exit(e.returncode)

def get_published_migrations(config_uri: str) -> Set[str]:
    """
    Возвращает множество имён миграций, опубликованных в config storage.
    Использует 'tt migrations status --display-mode=config-storage'.
    """
    tt_bin = get_tt_bin()
    cmd = [tt_bin, "migrations", "status", config_uri, "--display-mode=config-storage"]

    if os.environ.get("TT_CLI_CONFIG_STORAGE_USERNAME"):
        cmd.extend(["--config-storage-username", os.environ["TT_CLI_CONFIG_STORAGE_USERNAME"]])
    if os.environ.get("TT_CLI_CONFIG_STORAGE_PASSWORD"):
        cmd.extend(["--config-storage-password", os.environ["TT_CLI_CONFIG_STORAGE_PASSWORD"]])
    if os.environ.get("TT_CLI_USERNAME"):
        cmd.extend(["--tarantool-username", os.environ["TT_CLI_USERNAME"]])
    if os.environ.get("TT_CLI_PASSWORD"):
        cmd.extend(["--tarantool-password", os.environ["TT_CLI_PASSWORD"]])

    logger.debug("Running command: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, check=True, text=True, capture_output=True)
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        logger.debug("Combined output: %s", combined.strip())
        if not combined.strip() or "no scenarios" in combined.lower():
            return set()
        migrations = set()
        for line in combined.splitlines():
            found = re.findall(r'\S+\.lua', line)
            migrations.update(found)
        logger.debug("Parsed published migrations: %s", migrations)
        return migrations
    except subprocess.CalledProcessError as e:
        logger.error("Command failed with exit code %d", e.returncode)
        logger.error("stdout: %s", e.stdout.strip() if e.stdout else "")
        logger.error("stderr: %s", e.stderr.strip() if e.stderr else "")
        sys.exit(e.returncode)

def get_local_migrations(migrations_dir: Path) -> Set[str]:
    """Возвращает множество имён файлов .lua в указанной директории (плоская структура)."""
    if not migrations_dir.is_dir():
        logger.error("Migrations directory not found: %s", migrations_dir)
        sys.exit(1)
    files = [f.name for f in migrations_dir.glob("*.lua") if f.is_file()]
    return set(sorted(files))

def publish_migration(config_uri: str, file_path: Path) -> None:
    """Публикует один файл миграции."""
    tt_bin = get_tt_bin()
    cmd = [tt_bin, "migrations", "publish", config_uri, str(file_path)]
    if os.environ.get("TT_CLI_CONFIG_STORAGE_USERNAME"):
        cmd.extend(["--config-storage-username", os.environ["TT_CLI_CONFIG_STORAGE_USERNAME"]])
    if os.environ.get("TT_CLI_CONFIG_STORAGE_PASSWORD"):
        cmd.extend(["--config-storage-password", os.environ["TT_CLI_CONFIG_STORAGE_PASSWORD"]])
    logger.info("Publishing %s...", file_path.name)
    run_cmd(cmd)

def apply_migration(config_uri: str, migration_name: str) -> None:
    """Применяет одну миграцию по имени."""
    tt_bin = get_tt_bin()
    cmd = [tt_bin, "migrations", "apply", config_uri, "--migration", migration_name]
    # Добавляем параметры аутентификации Tarantool и SSL
    if os.environ.get("TT_CLI_USERNAME"):
        cmd.extend(["--tarantool-username", os.environ["TT_CLI_USERNAME"]])
    if os.environ.get("TT_CLI_PASSWORD"):
        cmd.extend(["--tarantool-password", os.environ["TT_CLI_PASSWORD"]])
    # SSL и таймауты
    ssl_map = {
        "TT_CLI_SSL_CERTFILE": "--tarantool-sslcertfile",
        "TT_CLI_SSL_KEYFILE": "--tarantool-sslkeyfile",
        "TT_CLI_SSL_CAFILE": "--tarantool-sslcafile",
        "TT_CLI_SSL_CIPHERS": "--tarantool-sslciphers",
        "TT_CLI_SSL_PASSWORD": "--tarantool-sslpassword",
        "TT_CLI_SSL_PASSWORDFILE": "--tarantool-sslpasswordfile",
    }
    for env, opt in ssl_map.items():
        if val := os.environ.get(env):
            cmd.extend([opt, val])
    if os.environ.get("TT_CLI_USE_SSL", "").lower() in ("true", "1", "yes"):
        cmd.append("--tarantool-use-ssl")
    if timeout := os.environ.get("TT_CLI_CONNECT_TIMEOUT"):
        cmd.extend(["--tarantool-connect-timeout", timeout])
    if timeout := os.environ.get("TT_CLI_EXECUTION_TIMEOUT"):
        cmd.extend(["--execution-timeout", timeout])

    logger.info("Applying %s...", migration_name)
    run_cmd(cmd)

def should_quiet_extra() -> bool:
    """Проверяет, нужно ли подавлять предупреждение о лишних миграциях."""
    return os.environ.get("QUIET_EXTRA", "").lower() in ("true", "1", "yes")

def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    config_uri = os.environ.get("TARANTOOL_CONFIG_URI")
    if not config_uri:
        logger.error("TARANTOOL_CONFIG_URI is not set")
        sys.exit(1)

    migrations_dir = Path(os.environ.get("MIGRATIONS_DIR", "migrations"))
    if not migrations_dir.is_dir():
        logger.error("Migrations directory not found: %s", migrations_dir)
        sys.exit(1)

    published = get_published_migrations(config_uri)
    local = get_local_migrations(migrations_dir)
    logger.info("Local migrations: %d file(s)", len(local))
    logger.debug("Published migrations: %d file(s)", len(published))

    extra = published - local
    if extra and not should_quiet_extra():
        logger.warning("Extra migrations in config storage (missing locally): %s. They will be ignored.",
                       ", ".join(sorted(extra)))

    logger.info("Publishing all local migrations...")
    for migration_name in sorted(local):
        file_path = migrations_dir / migration_name
        publish_migration(config_uri, file_path)

    logger.info("Applying all local migrations...")
    for migration_name in sorted(local):
        apply_migration(config_uri, migration_name)

    logger.info("All done.")

if __name__ == "__main__":
    main()