import {
    App,
    Notice,
    Plugin,
    PluginSettingTab,
    Setting,
    TFile,
    arrayBufferToBase64,
    requestUrl,
} from "obsidian";

interface Note2CmsSettings {
    apiUrl: string;
    apiToken: string;
    uploadImages: boolean;
    writeBackFrontmatter: boolean;
    copyPermalink: boolean;
}

const DEFAULT_SETTINGS: Note2CmsSettings = {
    apiUrl: "http://localhost:8000",
    apiToken: "",
    uploadImages: true,
    writeBackFrontmatter: true,
    copyPermalink: true,
};

const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif"]);
const MD_IMG_RE = /!\[[^\]]*\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g;
const WIKI_IMG_RE = /!\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]/g;

export default class Note2CmsPlugin extends Plugin {
    settings: Note2CmsSettings = DEFAULT_SETTINGS;

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
            },
        });

        this.addCommand({
            id: "note2cms-pull-note",
            name: "Pull current note from blog",
            callback: async () => {
                await this.pullActiveNote();
            },
        });

        this.addCommand({
            id: "note2cms-delete-note",
            name: "Delete current note from blog",
            callback: async () => {
                await this.deleteActiveNote();
            },
        });

        this.addCommand({
            id: "note2cms-rebuild",
            name: "Rebuild entire blog",
            callback: async () => {
                await this.rebuildBlog();
            },
        });

        this.addSettingTab(new Note2CmsSettingTab(this.app, this));
    }

    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    async saveSettings() {
        await this.saveData(this.settings);
    }

    private getBaseUrl(): string {
        return this.settings.apiUrl.replace(/\/+$/, "");
    }

    private ensureTitleFrontmatter(raw: string, fallbackTitle: string): string {
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

    private extractImageRefs(markdown: string): string[] {
        const refs = new Set<string>();
        for (const match of markdown.matchAll(MD_IMG_RE)) {
            refs.add(match[1].trim());
        }
        for (const match of markdown.matchAll(WIKI_IMG_RE)) {
            refs.add(match[1].trim());
        }
        return Array.from(refs);
    }

    private async collectAssets(markdown: string, sourceFile: TFile): Promise<Record<string, string>> {
        const assets: Record<string, string> = {};
        if (!this.settings.uploadImages) {
            return assets;
        }

        for (const ref of this.extractImageRefs(markdown)) {
            if (/^(https?:|data:|\/posts\/)/i.test(ref)) {
                continue;
            }
            const cleanRef = decodeURIComponent(ref).replace(/^\.\//, "");
            const linked = this.app.metadataCache.getFirstLinkpathDest(cleanRef, sourceFile.path);
            if (linked && linked instanceof TFile && IMAGE_EXTENSIONS.has(linked.extension.toLowerCase())) {
                const binary = await this.app.vault.readBinary(linked);
                assets[ref] = arrayBufferToBase64(binary);
            }
        }
        return assets;
    }

    private getConfiguredSlug(file: TFile): string | null {
        const cache = this.app.metadataCache.getFileCache(file);
        const slug = cache?.frontmatter?.slug;
        return typeof slug === "string" && slug.trim() ? slug.trim() : null;
    }

    async publishActiveNote() {
        const file = this.app.workspace.getActiveFile();
        if (!file) {
            new Notice("note2cms: No active Markdown note.");
            return;
        }
        if (!this.settings.apiToken) {
            new Notice("note2cms: Please set API Token in plugin settings.");
            return;
        }

        try {
            new Notice(`Publishing "${file.basename}"...`);
            const rawContent = await this.app.vault.read(file);
            const markdown = this.ensureTitleFrontmatter(rawContent, file.basename);
            const assets = await this.collectAssets(markdown, file);

            const body: Record<string, unknown> = { markdown };
            if (Object.keys(assets).length > 0) {
                body.assets = assets;
            }

            const resp = await requestUrl({
                url: `${this.getBaseUrl()}/publish`,
                method: "POST",
                headers: {
                    Authorization: `Bearer ${this.settings.apiToken}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(body),
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

            if (this.settings.copyPermalink && navigator?.clipboard) {
                await navigator.clipboard.writeText(data.permalink);
            }

            new Notice(`Published: ${data.permalink}`);
        } catch (err) {
            console.error(err);
            new Notice(`note2cms publish failed: ${(err as Error).message}`);
        }
    }

    async pullActiveNote() {
        const file = this.app.workspace.getActiveFile();
        if (!file) {
            new Notice("note2cms: No active Markdown note.");
            return;
        }
        const slug = this.getConfiguredSlug(file);
        if (!slug) {
            new Notice("note2cms: Active note frontmatter has no 'slug'.");
            return;
        }
        try {
            const resp = await requestUrl({
                url: `${this.getBaseUrl()}/posts/${encodeURIComponent(slug)}/source`,
                method: "GET",
                headers: {
                    Authorization: `Bearer ${this.settings.apiToken}`,
                },
            });
            await this.app.vault.modify(file, resp.text);
            new Notice(`Pulled latest source for "${slug}".`);
        } catch (err) {
            console.error(err);
            new Notice(`note2cms pull failed: ${(err as Error).message}`);
        }
    }

    async deleteActiveNote() {
        const file = this.app.workspace.getActiveFile();
        if (!file) {
            new Notice("note2cms: No active Markdown note.");
            return;
        }
        const slug = this.getConfiguredSlug(file);
        if (!slug) {
            new Notice("note2cms: Active note frontmatter has no 'slug'.");
            return;
        }
        try {
            await requestUrl({
                url: `${this.getBaseUrl()}/posts/${encodeURIComponent(slug)}`,
                method: "DELETE",
                headers: {
                    Authorization: `Bearer ${this.settings.apiToken}`,
                },
            });
            new Notice(`Deleted "${slug}" from blog.`);
        } catch (err) {
            console.error(err);
            new Notice(`note2cms delete failed: ${(err as Error).message}`);
        }
    }

    async rebuildBlog() {
        try {
            const resp = await requestUrl({
                url: `${this.getBaseUrl()}/rebuild`,
                method: "POST",
                headers: {
                    Authorization: `Bearer ${this.settings.apiToken}`,
                },
            });
            new Notice(`Rebuilt ${resp.json?.posts ?? 0} post(s).`);
        } catch (err) {
            console.error(err);
            new Notice(`note2cms rebuild failed: ${(err as Error).message}`);
        }
    }
}

class Note2CmsSettingTab extends PluginSettingTab {
    plugin: Note2CmsPlugin;

    constructor(app: App, plugin: Note2CmsPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();

        containerEl.createEl("h2", { text: "note2cms Publisher Settings" });

        new Setting(containerEl)
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

        new Setting(containerEl)
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

        new Setting(containerEl)
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

        new Setting(containerEl)
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

        new Setting(containerEl)
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
