# Руководство по миграции с Leapcell на FastAPI Cloud + Neon

Это руководство предназначено для пользователей, чей бэкенд ранее работал на **Leapcell**, и которым необходимо перенести сервис на **FastAPI Cloud** с сохранением всех уже опубликованных постов блога.

---

## 1. В чём разница между Leapcell и новой архитектурой

* **Было (Leapcell)**: Leapcell предоставлял сервис «всё в одном» — контейнер с FastAPI и встроенный PostgreSQL.
* **Стало (FastAPI Cloud + Neon)**:
  * **FastAPI Cloud** (`fastapicloud.com`) — бессерверный хостинг API от создателей FastAPI (масштабирование в ноль, автоматический HTTPS, деплой через CLI).
  * **Neon** (`neon.tech`) — бессерверный PostgreSQL, интегрируемый с FastAPI Cloud в один клик.
  * **GitHub Pages** — статическое хранилище сгенерированного HTML (остаётся без изменений).
  * **Obsidian (`note2cms-publisher`)** — клиентский плагин (в коде ничего менять не нужно, только обновить `API URL`).

---

## 2. Пошаговый процесс миграции

### Шаг 1. Обновление репозитория бэкенда

Убедитесь, что в репозитории `note2cms` присутствуют актуальные файлы:
* `pyproject.toml` с `[tool.setuptools] packages = ["api", "pipeline"]` и `[tool.fastapi] entrypoint = "api.main:app"`
* `requirements.txt` с зависимостями `fastapi[standard]`, `psycopg[binary]`, `markdownify`

### Шаг 2. Деплой бэкенда в FastAPI Cloud

1. В терминале:
   ```bash
   cd note2cms
   fastapi login
   fastapi deploy
   ```
2. FastAPI Cloud соберёт образ и выдаст рабочий URL (например: `https://note2cms-xxxx.fastapicloud.dev`).

### Шаг 3. Подключение базы данных Neon

В панели управления **FastAPI Cloud** (`fastapicloud.com`):
1. Откройте проект приложения `note2cms`.
2. Перейдите во вкладку **Integrations** → выберите **Neon** → нажмите **Connect resource** (или Provision).
3. FastAPI Cloud автоматически создаст базу данных в Neon и подключит переменную `DATABASE_URL`.

*(Альтернативно: если у вас уже есть база на [neon.tech](https://neon.tech), просто вставьте её Connection String в переменную `DATABASE_URL`).*

### Шаг 4. Настройка переменных окружения

В разделе **Environment Variables** приложения в FastAPI Cloud задайте переменные:

| Переменная | Значение / Описание |
|---|---|
| `API_TOKEN` | Секретный токен для публикации из Obsidian (сгенерируйте пароль 32+ символа) |
| `DATABASE_URL` | *(Автоматически добавлено интеграцией Neon, либо вставьте вручную)* |
| `SITE_TITLE` | Название блога (например, `stenAgram`) |
| `SITE_URL` | Адрес вашего блога на GitHub Pages: `https://YOUR_USERNAME.github.io/blog` *(без слэша на конце!)* |
| `ACTIVE_THEME` | `default` |
| `GITHUB_TOKEN` | Ваш GitHub Personal Access Token (с правами `Contents: Read and write`) |
| `GITHUB_REPO` | `YOUR_USERNAME/blog` |
| `GITHUB_BRANCH` | `gh-pages` |
| `DEPLOY_TARGET` | `github_pages` |

---

## 3. Восстановление уже опубликованных постов

Поскольку база Leapcell недоступна, все опубликованные статьи восстанавливаются напрямую из репозитория GitHub Pages (`gh-pages`).

### Способ А: В 1 клик через Swagger UI (Рекомендуемый, без знания паролей БД)

1. Откройте в браузере интерактивную документацию вашего развёрнутого бэкенда:  
   `https://ВАШ_СЕРВИС.fastapicloud.dev/docs`
2. Нажмите зелёную кнопку **Authorize** в правом верхнем углу и введите ваш `API_TOKEN`.
3. Разверните эндпоинт **POST `/import-from-blog`**.
4. Нажмите **Try it out** → **Execute**.
5. Бэкенд сам прямо из облака скачает все посты из GitHub Pages, переведёт их в Markdown с YAML-frontmatter и сохранит в базу Neon. Ответ сервера:
   ```json
   { "status": "ok", "imported": 30, "repo": "YOUR_USERNAME/blog" }
   ```

*(Либо через терминал / curl):*
```bash
curl -X POST https://ВАШ_СЕРВИС.fastapicloud.dev/import-from-blog \
  -H "Authorization: Bearer ВАШ_API_TOKEN"
```

### Способ Б: Локальный бэкап заметок в Markdown

Если вам нужны копии всех статей в виде `.md` файлов на вашем компьютере:
```bash
python migrate_from_blog.py --repo "YOUR_USERNAME/blog" --save-markdown ./content
```
Все статьи сохранятся в папку `./content/` со всеми метаданными, датами и тегами.

---

## 4. Переключение плагина в Obsidian

1. В Obsidian откройте **Настройки** → **note2cms Publisher**.
2. Измените поле **API URL**: укажите новый адрес `https://ВАШ_СЕРВИС.fastapicloud.dev`.
3. В поле **API Token** укажите ваш `API_TOKEN`.
4. Нажмите **Test connection** — появится зелёное уведомление об успехе.
5. Запустите команду `Manage published posts` — вы сразу увидите все восстановленные посты блога.
