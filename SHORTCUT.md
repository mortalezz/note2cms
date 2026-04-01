# iOS Shortcuts Client

Publish to note2cms from any app on your iPhone. No terminal. No Obsidian. Just the share sheet.

## Setup

Open the Shortcuts app and create a new shortcut named "Publish to Blog."

### Steps

**1. Ask for Input**
- Type: Text
- Prompt: "Paste Markdown"
- Allow Multiple Lines: On

**2. Text**
- Paste your API URL:
```
https://note2cms-mortalezz9537-3k6s86pf.leapcell.dev/publish
```
- (This is a variable so Shortcuts can reference it as a URL)

**3. Get Contents of URL**
- URL: select the **Text** variable from step 2
- Method: **POST**
- Headers:
  - `Authorization`: `Bearer YOUR_TOKEN_HERE`
- Request Body: **JSON**
  - Key: `markdown`
  - Value: select the **Ask for Input** variable from step 1

**4. Get Dictionary Value**
- Key: `permalink`
- From: Contents of URL (step 3 output)

**5. Copy to Clipboard**
- Input: Dictionary Value from step 4

**6. Show Notification** (optional)
- Title: "Published!"
- Body: Dictionary Value from step 4

## Usage

**From any app:** Write in Apple Notes, Bear, or any text app. Select all. Share. "Publish to Blog."

**From home screen:** Tap the shortcut. Paste Markdown with frontmatter. Get permalink.

**From Siri:** "Hey Siri, Publish to Blog."

## Frontmatter

Your Markdown must start with frontmatter:

```
---
title: Your Post Title
tags: [tag1, tag2]
date: 2026-03-22
---

Your content here.
```

Without a title in frontmatter, the parser will reject the post.

## Troubleshooting

**"Couldn't convert from Rich Text to URL"** — the URL field has a variable instead of the actual URL text. Use a separate Text step for the URL.

**"Internal Server Error" (500)** — the input is Rich Text instead of plain text. Add a "Get text from" step after "Ask for Input" to strip formatting. Use that plain text variable for the markdown body field.

**"Bad Request" (400)** — the frontmatter is malformed. Make sure each field is on its own line with straight quotes, not curly quotes. Turn off Smart Punctuation in iOS Settings > General > Keyboard.

## The Point

The browser was never opened. Apple Notes is now a note2cms client. The share sheet is the interface. The Shortcut is the client. The protocol holds.
