# Миграции Tarantool EE через утилиту `tt`

Скрипт на Python для автоматического применения миграций Tarantool Enterprise Edition с использованием утилиты `tt`.  
Предназначен для использования в CI/CD (GitLab CI, GitHub Actions) и в Kubernetes (как отдельный Job или init-контейнер).

## Функциональность

- Плоская структура директории: файлы `.lua` лежат непосредственно в папке.
- Публикация всех локальных файлов в централизованное хранилище конфигурации.
- Последовательное применение каждой миграции (лексикографический порядок).
- Идемпотентность: повторные запуски безопасны.
- Если в хранилище есть миграции, отсутствующие локально — предупреждение в лог (можно отключить).

## Поведение скрипта

1. Проверяет существование `MIGRATIONS_DIR` и наличие в ней файлов `.lua`.
2. Получает список опубликованных миграций через `tt migrations status --display-mode=config-storage`.
3. Если в хранилище есть миграции, которых нет локально, и `QUIET_EXTRA` не включён — выводит предупреждение в stderr.
4. Публикует все локальные файлы через `tt migrations publish`.
5. Применяет все локальные файлы через `tt migrations apply --migration <filename>` в лексикографическом порядке.
6. При ошибке любой команды завершается с ненулевым кодом, выводя ошибку в stderr.

## Переменные окружения

Все параметры задаются через переменные окружения. Обязательные отмечены.

| Переменная | Описание | Обязательная | По умолчанию |
|------------|----------|--------------|--------------|
| `TARANTOOL_CONFIG_URI` | URI хранилища конфигурации (etcd или Tarantool). Пример: `http://user:pass@etcd:2379/tarantool` | ✅ | — |
| `MIGRATIONS_DIR` | Путь к директории с `.lua` файлами миграций внутри контейнера. | | `migrations` |
| `QUIET_EXTRA` | Не выводить предупреждение о миграциях в хранилище, которых нет локально (значения `true`/`1`/`yes`). | | `false` |
| `LOG_LEVEL` | Уровень логирования (`DEBUG`, `INFO`, `WARNING`, `ERROR`). | | `INFO` |
| `DEBUG` | Включает `DEBUG` режим (переопределяет `LOG_LEVEL`) при `true`/`1`/`yes`. | | `false` |

### Аутентификация для хранилища конфигурации

| Переменная | Описание |
|------------|----------|
| `TT_CLI_CONFIG_STORAGE_USERNAME` | Имя пользователя для config storage. |
| `TT_CLI_CONFIG_STORAGE_PASSWORD` | Пароль для config storage. |

### Аутентификация для Tarantool-кластера

| Переменная | Описание |
|------------|----------|
| `TT_CLI_USERNAME` | Имя пользователя для подключения к Tarantool. |
| `TT_CLI_PASSWORD` | Пароль для подключения к Tarantool. |

### SSL-параметры для Tarantool-кластера

| Переменная | Опция `tt` |
|------------|------------|
| `TT_CLI_SSL_CERTFILE` | `--tarantool-sslcertfile` |
| `TT_CLI_SSL_KEYFILE` | `--tarantool-sslkeyfile` |
| `TT_CLI_SSL_CAFILE` | `--tarantool-sslcafile` |
| `TT_CLI_SSL_CIPHERS` | `--tarantool-sslciphers` |
| `TT_CLI_SSL_PASSWORD` | `--tarantool-sslpassword` |
| `TT_CLI_SSL_PASSWORDFILE` | `--tarantool-sslpasswordfile` |
| `TT_CLI_USE_SSL` | `--tarantool-use-ssl` (если `true`/`1`/`yes`) |

### Таймауты

| Переменная | Опция `tt` | По умолчанию |
|------------|------------|--------------|
| `TT_CLI_CONNECT_TIMEOUT` | `--tarantool-connect-timeout` (сек) | 3 |
| `TT_CLI_EXECUTION_TIMEOUT` | `--execution-timeout` (сек) | 3600 |

## Сборка Docker-образа

Утилита `tt` не включена в образ, так как распространяется только с Tarantool EE.  
Перед сборкой поместите бинарный файл `tt` в директорию сборки (рядом с Dockerfile).

**Dockerfile:**

```dockerfile
ARG BASE_IMAGE=registry.red-soft.ru/ubi8/python-313-minimal:3.13
FROM $BASE_IMAGE
USER 0
COPY tt /usr/local/bin/tt
RUN chmod +x /usr/local/bin/tt

COPY migrations.py /usr/local/bin/migrate.py
RUN chmod +x /usr/local/bin/migrate.py

USER 1001
WORKDIR /workspace
ENTRYPOINT ["python3", "/usr/local/bin/migrate.py"]
```

### Сборка через docker

```bash
# Поместите файл tt в текущую папку
cp /path/to/tt .

# Соберите образ
docker build -t docker-registry.example.com/namespace/tt-migrations:0.1.0 .

# Загрузите в registry
docker push docker-registry.example.com/namespace/tt-migrations:0.1.0
```

### Сборка через buildah

```bash
buildah bud -t docker-registry.example.com/namespace/tt-migrations:0.1.0 .
buildah push docker-registry.example.com/namespace/tt-migrations:0.1.0
```

При необходимости базовый образ можно переопределить через аргумент `--build-arg`:

```bash
docker build --build-arg BASE_IMAGE=my-registry/custom-python:3.13 -t my-image .
```

## Использование

### Локально

```bash
export TARANTOOL_CONFIG_URI="http://etcd:2379/tarantool/myapp"
export MIGRATIONS_DIR="./migrations"
export TT_CLI_USERNAME="admin"
export TT_CLI_PASSWORD="admin_password"
python3 migrations.py
```

### GitLab CI

```yaml
migrate:
  stage: migrate
  image: docker-registry.example.com/namespace/tt-migrations:0.1.0
  variables:
    TARANTOOL_CONFIG_URI: "http://etcd:2379/tarantool/myapp"
    MIGRATIONS_DIR: "migrations"
  script:
    - /usr/local/bin/migrate.py
  rules:
    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH
```


### GitHub Actions

```yaml
name: Tarantool Migrations

on:
  push:
    branches: [ "main" ]

jobs:
  migrate:
    runs-on: ubuntu-latest
    container:
      image: docker-registry.example.com/namespace/tt-migrations:0.1.0
    env:
      TARANTOOL_CONFIG_URI: ${{ vars.TARANTOOL_CONFIG_URI }}
      MIGRATIONS_DIR: "migrations"
      TT_CLI_USERNAME: ${{ secrets.TARANTOOL_USER }}
      TT_CLI_PASSWORD: ${{ secrets.TARANTOOL_PASSWORD }}
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Run migrations
        run: /usr/local/bin/migrate.py
```

### Kubernetes:

**ConfigMap с файлами миграций:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: migrations-scripts
data:
  001_init.lua: |
    -- содержимое миграции
  002_update.lua: |
    -- содержимое
```

**Job:**

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: tarantool-migrations
spec:
  template:
    spec:
      containers:
      - name: migrations
        image: docker-registry.example.com/namespace/tt-migrations:0.1.0
        env:
        - name: TARANTOOL_CONFIG_URI
          value: "http://etcd:2379/tarantool/myapp"
        - name: MIGRATIONS_DIR
          value: "/migrations"
        - name: TT_CLI_USERNAME
          valueFrom:
            secretKeyRef:
              name: tarantool-auth
              key: username
        - name: TT_CLI_PASSWORD
          valueFrom:
            secretKeyRef:
              name: tarantool-auth
              key: password
        volumeMounts:
        - name: migrations
          mountPath: /migrations
      volumes:
      - name: migrations
        configMap:
          name: migrations-scripts
      restartPolicy: Never
  backoffLimit: 2
```

### Kubernetes: init-контейнер в Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-app
spec:
  template:
    spec:
      initContainers:
      - name: migrations
        image: docker-registry.example.com/namespace/tt-migrations:0.1.0
        env:
        - name: TARANTOOL_CONFIG_URI
          value: "http://etcd:2379/tarantool/myapp"
        - name: MIGRATIONS_DIR
          value: "/migrations"
        - name: TT_CLI_USERNAME
          valueFrom:
            secretKeyRef:
              name: tarantool-auth
              key: username
        - name: TT_CLI_PASSWORD
          valueFrom:
            secretKeyRef:
              name: tarantool-auth
              key: password
        volumeMounts:
        - name: migrations
          mountPath: /migrations
      volumes:
      - name: migrations
        configMap:
          name: migrations-scripts
      containers:
      - name: app
        image: my-app:latest
        # ...
```

### Запуск через docker run

```bash
docker run --rm \
  -e TARANTOOL_CONFIG_URI="http://etcd:2379/tarantool/myapp" \
  -e MIGRATIONS_DIR="/migrations" \
  -e TT_CLI_USERNAME="admin" \
  -e TT_CLI_PASSWORD="admin_password" \
  -v $(pwd)/migrations:/migrations \
  docker-registry.example.com/namespace/tt-migrations:0.1.0
```

## Примечания

- Все настройки передаются через переменные окружения.
- Миграции должны лежать непосредственно в `MIGRATIONS_DIR` (без поддиректорий).
- Для хранения конфиденциальных данных используйте переменные окружения или Kubernetes Secrets.
- Убедитесь, что в образе есть Python 3 и бинарный файл `tt`, скопированный из дистрибутива Tarantool EE.
```