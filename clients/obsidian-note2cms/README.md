# note2cms Publisher for Obsidian

Publish Markdown notes and attached images (`![[photo.jpg]]` or `![](photo.jpg)`) straight from Obsidian to your note2cms API.

## Quick Install (no build required)

1. Copy the contents of `clients/obsidian-note2cms/` (`manifest.json`, `main.js`, `styles.css`) into your vault folder:
   `<your-vault>/.obsidian/plugins/note2cms/`
2. In Obsidian: **Settings → Community plugins → Enable `note2cms Publisher`**.
3. Open plugin settings and configure:
   - **API URL** (e.g. `https://your-api.fastapicloud.dev` or `http://localhost:8000`)
   - **API Token** (`API_TOKEN` from your server `.env`)

## Usage

- Click the cloud upload icon in the left ribbon or run `note2cms Publisher: Publish current note` from the Command Palette (`Ctrl/Cmd + P`).
- Attached images referenced via `![[image.jpg]]` or `![](image.jpg)` are automatically uploaded; EXIF/GPS metadata is stripped and images larger than 1 MP are proportionally downsized on the server.
- Consecutive images in a paragraph (or inside `::: gallery ... :::`) automatically render as a pure-CSS swipeable carousel.
- Other commands:
  - `Pull current note from blog` — replaces the active note with the latest stored Markdown from the server (`GET /posts/{slug}/source`).
  - `Delete current note from blog` — deletes the note by its frontmatter `slug`.
  - `Rebuild entire blog` — triggers `POST /rebuild`.

## Building from TypeScript source

```bash
npm install
npm run build
```
