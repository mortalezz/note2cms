# Contributing

You might read the manifesto, the protocol spec, the API specification, and think: this person is opinionated to the point of being difficult. The architecture is rigid. The principles are non-negotiable. The spec uses the word "must" like it's punctuation.

You would be correct about the opinions. You would be wrong about the difficulty.

## Why the Walls Are High

The walls around the core are high so that the space outside them can be unlimited.

note2cms has four endpoints, a strict Markdown contract, and a protocol that forbids browser-based editors. These constraints are not ego. They are load-bearing walls. Remove any one of them and the architecture collapses into the same accidental complexity that every other CMS accumulated over two decades.

The rigidity of the core is what makes everything else free. You can build any client — Obsidian, Bear, vim, a shell script, an iOS Shortcut, an Android app — because the API contract is small enough to implement against in an afternoon. You can build any theme — serif, sans-serif, brutalist, vaporwave, calligraphic — because the data contract is stable and the pipeline doesn't care what your CSS looks like. You can deploy anywhere — GitHub Pages, Cloudflare, S3, a Raspberry Pi — because the output is static HTML with zero runtime dependencies.

If the core were permissive, none of this would work. A flexible API is an unpredictable API. An accommodating pipeline is a leaky pipeline. A core that says yes to everything becomes a core that guarantees nothing.

I am religious about the architecture because the architecture is what sets you free. Nothing will work if the author is less religious about his work. That is not arrogance. That is structural engineering.

## What I Will Protect

The four endpoints and their contracts. The Markdown-in, static-HTML-out pipeline. The stateless build model. The theme-as-a-function interface. The PBPP protocol principles.

If your contribution modifies any of these, I will push back. Not because your idea is bad — it might be brilliant — but because the protocol's value comes from its constraints. A PBPP implementation that relaxes its principles is not a better PBPP implementation. It is a different thing pretending to be PBPP.

## What I Will Never Gatekeep

Everything outside the core. Which is almost everything.

### Themes

Build one. Any aesthetic, any CSS framework, any visual trick. The only requirement is that your theme satisfies the data contract — it receives the documented variables and produces valid HTML. Beyond that, go wild. Put scanlines on it. Make it brutalist. Make it look like a 1997 GeoCities page. I will merge it if it works and if it has a personality.

Read `THEMING.md` for the three-layer contract and the visual flair principle.

### Clients

Build one for your favorite notes app. Obsidian, Bear, Notion, Drafts, Ulysses, Emacs, whatever. The API is four endpoints with a bearer token. If your client can POST JSON over HTTPS, it can publish to note2cms. You do not need my approval to build a client. You do not need to open a PR. The API is the interface. Build against it and ship.

If you want your client listed in the README or included in the repository under `clients/`, open a PR. I will merge it.

### Deployment Targets

Write a deployer for a platform we don't support yet. The deployer interface is simple — it receives an HTML string and a path, and it puts the HTML where readers can find it. The GitHub Pages deployer is the reference implementation. Write one for Cloudflare Pages, Netlify, S3, FTP, carrier pigeon. Open a PR.

### Documentation

Fix a typo. Clarify an instruction. Translate a guide. Add a tutorial. Documentation PRs are merged fast because documentation helps people and never breaks the protocol.

### Bug Fixes

If something is broken, fix it and open a PR. Include what was wrong, what you changed, and how to verify the fix. Bug fixes that don't alter the API contract or protocol principles are merged without debate.

## What I Ask

**Read the spec before proposing changes to the core.** `PROTOCOL.md` defines the principles. `API.md` defines the wire format. If your proposal conflicts with either, it will be declined — not because it's wrong, but because it's a different protocol.

**Build outside the core when possible.** The architecture was designed so that most valuable contributions don't require core changes. Themes, clients, deployers, documentation — all of these extend the system without modifying it. If you find yourself needing to change the core, ask whether the extension point is missing rather than whether the core should change.

**One PR, one concern.** A theme in one PR. A bug fix in another. A new deployer in a third. Small PRs are reviewed fast. Large PRs are reviewed slowly. Enormous PRs are reviewed never.

**Test your contribution.** Publish a post through it. View the output. Click the links. Check mobile. If it's a theme, check dark mode. If it's a client, check error handling. If it's a deployer, check that the permalink resolves.

## The Paradox

Someone will read this document and call me opinionated. They will be right. But they will be wrong about what the opinions protect.

The opinions do not protect my ego. They do not protect my vision of what your blog should look like. They do not protect my preference for how you write or where you write or what you write about.

The opinions protect the contract that makes all of your freedom possible. The four endpoints. The static output. The stateless pipeline. The theme interface. The protocol principles. These are the constraints that guarantee you can build anything on top of this system without asking anyone's permission.

I am opinionated so that you do not have to be.

The system says no so the maintainer does not have to. And the contributing guide says "the walls are high" so that everything on the other side of them can be limitless.

---

*Opinionated on input. Free on output. Strict on architecture. Silent on creation.*
