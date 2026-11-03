# Руководство по установке note2cms с нуля

Разверните собственный блог на связке **Obsidian + FastAPI Cloud + GitHub Pages** за ~10 минут.  
**Стоимость:** $0 (бесплатные тарифы навсегда, без привязки банковской карты).

---

## Архитектура системы

```
[Obsidian Note]
      │
      ▼ POST /publish (Токен авторизации)
┌──────────────────────────────────────────────┐
│        FastAPI Cloud (Бессерверный API)      │
│                                              │
│   FastAPI Движок                             │
│   ├── Рендеринг HTML ────────────────────────┼──► GitHub Pages (gh-pages)
│   └── Запись таксономии и исходников         │     ├── /posts/my-post/index.html
└──────────────────────┬───────────────────────┘     └── index.html (Главная)
                       │
                       ▼ PostgreSQL (DATABASE_URL)
┌──────────────────────────────────────────────┐
│           Neon Serverless PostgreSQL         │
│  - posts (метаданные, теги, время чтения)    │
│  - markdown_source (резервная копия заметок) │
└──────────────────────────────────────────────┘
```

---

## Что вам понадобится

1. **GitHub-аккаунт** — [github.com/signup](https://github.com/signup)
2. **Аккаунт FastAPI Cloud** — [fastapicloud.com](https://fastapicloud.com)
3. **Терминал и Python 3.10+** с установленным `git`

---

## Шаг 1. Форк или клон репозитория note2cms

1. Сделайте Fork репозитория [note2cms](https://github.com/garrul4ik/note2cms) в свой GitHub-аккаунт (или склонируйте его локально):
   ```bash
   git clone https://github.com/YOUR_USERNAME/note2cms.git
   cd note2cms
   ```

---

## Шаг 2. Создание репозитория для блога (GitHub Pages)

Здесь будут публиковаться готовые статические HTML-страницы вашего блога.

1. Перейдите на [github.com/new](https://github.com/new).
2. Назовите репозиторий `blog` (или любое другое имя).
3. Сделайте его **Public**.
4. **Не добавляйте** README, .gitignore или лицензию — оставьте репозиторий полностью пустым.
5. Нажмите **Create repository**.
6. Создайте ветку `gh-pages` через терминал:
   ```bash
   mkdir blog && cd blog
   git init
   git checkout -b gh-pages
   touch .nojekyll
   echo '<!DOCTYPE html><html><body><p>Скоро здесь будет блог.</p></body></html>' > index.html
   git add .
   git commit -m "init"
   git remote add origin git@github.com:YOUR_USERNAME/blog.git
   git push -u origin gh-pages
   ```
7. Включите GitHub Pages в репозитории `blog`:
   - Откройте **Settings** → вкладка **Pages**.
   - В разделе **Source** выберите **Deploy from a branch**.
   - Ветка: `gh-pages`, папка: `/ (root)`.
   - Нажмите **Save**.  
   *Через минуту блог откроется по адресу `https://YOUR_USERNAME.github.io/blog/`.*

---

## Шаг 3. Создание токена доступа GitHub (PAT)

Бэкенду `note2cms` нужны права для автоматической публикации сгенерированного HTML в репозиторий блога:

1. Откройте [github.com/settings/tokens/new](https://github.com/settings/tokens/new) (или Fine-grained Personal Access Token).
2. Название токена: `note2cms-deployer`.
3. Доступ:
   - Если Fine-grained: выберите репозиторий `blog` → права **Contents: Read and write**.
   - Если Classic: отметьте чекбокс `repo`.
4. Нажмите **Generate token** и скопируйте его (начинается на `ghp_` или `github_pat_`).

---

## Шаг 4. Деплой бэкенда в FastAPI Cloud

1. В папке проекта `note2cms` установите FastAPI CLI (если ещё не установлен):
   ```bash
   pip install "fastapi[standard]"
   ```
2. Авторизуйтесь в FastAPI Cloud:
   ```bash
   fastapi login
   ```
3. Запустите публикацию:
   ```bash
   fastapi deploy
   ```
4. FastAPI Cloud автоматически соберёт проект по файлу `pyproject.toml` и выдаст URL сервиса (вид: `https://note2cms-xxxx.fastapicloud.dev`).

---

## Шаг 5. Подключение базы данных Neon

1. В панели управления [fastapicloud.com](https://fastapicloud.com) откройте созданное приложение `note2cms`.
2. Перейдите во вкладку **Integrations** → выберите **Neon** → нажмите **Connect resource** (или Provision).
3. FastAPI Cloud автоматически создаст бесплатную базу данных в Neon и добавит защищённую переменную `DATABASE_URL` в проект.

---

## Шаг 6. Настройка переменных окружения в FastAPI Cloud

В панели приложения на **fastapicloud.com** откройте вкладку **Environment Variables** и укажите:

| Переменная | Значение / Описание |
|---|---|
| `API_TOKEN` | Ваш секретный ключ (например, сгенерируйте: `python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `DATABASE_URL` | *(Автоматически добавлено интеграцией Neon)* |
| `SITE_TITLE` | Название блога (например: `Мой Блог`) |
| `SITE_URL` | Адрес вашего блога: `https://YOUR_USERNAME.github.io/blog` *(строго без слэша на конце!)* |
| `ACTIVE_THEME` | `default` (или любая из папки `themes/`, например: `swiss`, `brutalist`, `terminal`) |
| `GITHUB_TOKEN` | Токен из Шага 3 (`ghp_...` или `github_pat_...`) |
| `GITHUB_REPO` | `YOUR_USERNAME/blog` |
| `GITHUB_BRANCH` | `gh-pages` |
| `DEPLOY_TARGET` | `github_pages` |

---

## Шаг 7. Настройка плагина в Obsidian

1. В Obsidian установите плагин **note2cms Publisher** (из каталога Community Plugins или через BRAT по репозиторию `garrul4ik/note2cms-publisher`).
2. Откройте **Settings** → **note2cms Publisher**.
3. Укажите:
   - **API URL**: Адрес из FastAPI Cloud (`https://note2cms-xxxx.fastapicloud.dev`).
   - **API Token**: Значение `API_TOKEN` из Шага 6.
4. Нажмите **Test connection** — появится зелёное уведомление об успешной связи.

---

## Шаг 8. Публикация первой заметки

1. Откройте любую заметку в Obsidian.
2. Нажмите `Ctrl+P` (или `Cmd+P` на Mac) и выберите **"Publish current note"**.
3. Плагин проверит YAML-заголовок, отправит Markdown на ваш бэкенд, и через пару секунд выдаст всплывающее окно с пермалинком на живой пост.

---

## Частые вопросы и диагностика

* **Холодный старт:** На бесплатном тарифе FastAPI Cloud и Neon засыпают при простое. Первый запрос после перерыва может занять 2–4 секунды — в плагине заложен таймаут 30 секунд, поэтому это штатное поведение.
* **Ошибка 404 на ссылках главной страницы:** Убедитесь, что в переменной `SITE_URL` **нет слэша на конце** (правильно: `https://user.github.io/blog`).
* **Как сменить тему оформления:** В настройках переменных окружения FastAPI Cloud укажите `ACTIVE_THEME` (список тем в папке `themes/`), сохраните и вызовите эндпоинт `POST /rebuild` в `https://ВАШ_СЕРВИС.fastapicloud.dev/docs`.
