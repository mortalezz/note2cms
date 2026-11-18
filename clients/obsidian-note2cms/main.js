"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

var main_exports = {};
__export(main_exports, {
  default: () => Note2CmsPlugin
});
module.exports = __toCommonJS(main_exports);

var obsidian = require("obsidian");

const DEFAULT_SETTINGS = {
  apiUrl: "http://localhost:8000",
  apiToken: "",
  uploadImages: true,
  writeBackFrontmatter: true,
  copyPermalink: true
};

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif"]);
const MD_IMG_RE = /!\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const WIKI_IMG_RE = /!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g;

class Note2CmsPlugin extends obsidian.Plugin {
  constructor() {
    super(...arguments);
    this.settings = Object.assign({}, DEFAULT_SETTINGS);
  }

  async onload() {
    await this.loadSettings();

    this.addRibbonIcon("upload-cloud", "Publish to note2cms", async () => {
      await this.publishActiveNote();
    });

    this.addCommand({
      id: "note2cms-publish-note",
      name: "Publish current note",
      callback: async () => {
        await this.publishActiveNote();
      }
    });

    this.addCommand({
      id: "note2cms-pull-note",
      name: "Pull current note from blog",
      callback: async () => {
        await this.pullActiveNote();
      }
    });

    this.addCommand({
      id: "note2cms-delete-note",
      name: "Delete current note from blog",
      callback: async () => {
        await this.deleteActiveNote();
      }
    });

    this.addCommand({
      id: "note2cms-rebuild",
      name: "Rebuild entire blog",
      callback: async () => {
        await this.rebuildBlog();
      }
    });

    this.addSettingTab(new Note2CmsSettingTab(this.app, this));
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  getBaseUrl() {
    return this.settings.apiUrl.replace(/\/+$/, "");
  }

  ensureTitleFrontmatter(raw, fallbackTitle) {
    const fmMatch = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
    if (!fmMatch) {
      const safeTitle = fallbackTitle.replace(/"/g, '\\"');
      return `---\ntitle: "${safeTitle}"\n---\n\n${raw}`;
    }
    if (/^title\s*:/m.test(fmMatch[1])) {
      return raw;
    }
    const safeTitle = fallbackTitle.replace(/"/g, '\\"');
    return `---\ntitle: "${safeTitle}"\n${fmMatch[1]}\n---\n${raw.slice(fmMatch[0].length)}`;
  }

  extractImageRefs(markdown) {
    const refs = new Set();
    for (const match of markdown.matchAll(MD_IMG_RE)) {
      refs.add(match[1].trim());
    }
    for (const match of markdown.matchAll(WIKI_IMG_RE)) {
      refs.add(match[1].trim());
    }
    return Array.from(refs);
  }

  async collectAssets(markdown, sourceFile) {
    const assets = {};
    if (!this.settings.uploadImages) {
      return assets;
    }
    for (const ref of this.extractImageRefs(markdown)) {
      if (/^(https?:|data:|\/posts\/)/i.test(ref)) {
        continue;
      }
      const cleanRef = decodeURIComponent(ref).replace(/^\.\//, "");
      const linked = this.app.metadataCache.getFirstLinkpathDest(cleanRef, sourceFile.path);
      if (linked && linked instanceof obsidian.TFile && IMAGE_EXTENSIONS.has(linked.extension.toLowerCase())) {
        const binary = await this.app.vault.readBinary(linked);
        assets[ref] = obsidian.arrayBufferToBase64(binary);
      }
    }
    return assets;
  }

  getConfiguredSlug(file) {
    const cache = this.app.metadataCache.getFileCache(file);
    const slug = cache && cache.frontmatter ? cache.frontmatter.slug : null;
    return typeof slug === "string" && slug.trim() ? slug.trim() : null;
  }

  async publishActiveNote() {
    const file = this.app.workspace.getActiveFile();
    if (!file) {
      new obsidian.Notice("note2cms: No active Markdown note.");
      return;
    }
    if (!this.settings.apiToken) {
      new obsidian.Notice("note2cms: Please set API Token in plugin settings.");
      return;
    }

    try {
      new obsidian.Notice(`Publishing "${file.basename}"...`);
      const rawContent = await this.app.vault.read(file);
      const markdown = this.ensureTitleFrontmatter(rawContent, file.basename);
      const assets = await this.collectAssets(markdown, file);

      const body = { markdown };
      if (Object.keys(assets).length > 0) {
        body.assets = assets;
      }

      const resp = await obsidian.requestUrl({
        url: `${this.getBaseUrl()}/publish`,
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.settings.apiToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(body)
      });

      const data = resp.json;
      if (this.settings.writeBackFrontmatter) {
        await this.app.fileManager.processFrontMatter(file, (fm) => {
          fm.slug = data.slug;
          fm.permalink = data.permalink;
          if (!fm.title) {
            fm.title = data.title;
          }
        });
      }

      if (this.settings.copyPermalink && navigator && navigator.clipboard) {
        await navigator.clipboard.writeText(data.permalink);
      }

      new obsidian.Notice(`Published: ${data.permalink}`);
    } catch (err) {
      console.error(err);
      new obsidian.Notice(`note2cms publish failed: ${err.message || err}`);
    }
  }

  async pullActiveNote() {
    const file = this.app.workspace.getActiveFile();
    if (!file) {
      new obsidian.Notice("note2cms: No active Markdown note.");
      return;
    }
    const slug = this.getConfiguredSlug(file);
    if (!slug) {
      new obsidian.Notice("note2cms: Active note frontmatter has no 'slug'.");
      return;
    }
    try {
      const resp = await obsidian.requestUrl({
        url: `${this.getBaseUrl()}/posts/${encodeURIComponent(slug)}/source`,
        method: "GET",
        headers: {
          Authorization: `Bearer ${this.settings.apiToken}`
        }
      });
      await this.app.vault.modify(file, resp.text);
      new obsidian.Notice(`Pulled latest source for "${slug}".`);
    } catch (err) {
      console.error(err);
      new obsidian.Notice(`note2cms pull failed: ${err.message || err}`);
    }
  }

  async deleteActiveNote() {
    const file = this.app.workspace.getActiveFile();
    if (!file) {
      new obsidian.Notice("note2cms: No active Markdown note.");
      return;
    }
    const slug = this.getConfiguredSlug(file);
    if (!slug) {
      new obsidian.Notice("note2cms: Active note frontmatter has no 'slug'.");
      return;
    }
    try {
      await obsidian.requestUrl({
        url: `${this.getBaseUrl()}/posts/${encodeURIComponent(slug)}`,
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${this.settings.apiToken}`
        }
      });
      new obsidian.Notice(`Deleted "${slug}" from blog.`);
    } catch (err) {
      console.error(err);
      new obsidian.Notice(`note2cms delete failed: ${err.message || err}`);
    }
  }

  async rebuildBlog() {
    try {
      const resp = await obsidian.requestUrl({
        url: `${this.getBaseUrl()}/rebuild`,
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.settings.apiToken}`
        }
      });
      new obsidian.Notice(`Rebuilt ${resp.json && resp.json.posts ? resp.json.posts : 0} post(s).`);
    } catch (err) {
      console.error(err);
      new obsidian.Notice(`note2cms rebuild failed: ${err.message || err}`);
    }
  }
}

class Note2CmsSettingTab extends obsidian.PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "note2cms Publisher Settings" });

    new obsidian.Setting(containerEl)
      .setName("API URL")
      .setDesc("Base URL of your note2cms FastAPI service")
      .addText((text) =>
        text
          .setPlaceholder("https://your-api.fastapicloud.dev")
          .setValue(this.plugin.settings.apiUrl)
          .onChange(async (value) => {
            this.plugin.settings.apiUrl = value.trim();
            await this.plugin.saveSettings();
          })
      );

    new obsidian.Setting(containerEl)
      .setName("API Token")
      .setDesc("Bearer API_TOKEN configured on your note2cms server")
      .addText((text) => {
        text.inputEl.type = "password";
        return text
          .setPlaceholder("Enter Bearer token")
          .setValue(this.plugin.settings.apiToken)
          .onChange(async (value) => {
            this.plugin.settings.apiToken = value.trim();
            await this.plugin.saveSettings();
          });
      });

    new obsidian.Setting(containerEl)
      .setName("Upload attached images")
      .setDesc("Bundle local images and ![[embeds]] on publish (EXIF stripped, capped at 1 MP)")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.uploadImages)
          .onChange(async (value) => {
            this.plugin.settings.uploadImages = value;
            await this.plugin.saveSettings();
          })
      );

    new obsidian.Setting(containerEl)
      .setName("Write slug & permalink back to frontmatter")
      .setDesc("Automatically save slug and permalink into the note after publishing")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.writeBackFrontmatter)
          .onChange(async (value) => {
            this.plugin.settings.writeBackFrontmatter = value;
            await this.plugin.saveSettings();
          })
      );

    new obsidian.Setting(containerEl)
      .setName("Copy permalink to clipboard")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.copyPermalink)
          .onChange(async (value) => {
            this.plugin.settings.copyPermalink = value;
            await this.plugin.saveSettings();
          })
      );
  }
}
