# Manifesto

*Write where you think. Publish where they look. Own everything in between.*

---

I am highly opinionated. I believe the browser is for consuming, not creating.
I believe your notes app already won the authoring war. I believe static HTML
is the only format that respects both the reader and the passage of time.

But I also believe that nothing should get too opinionated in my output.

note2cms is KISS, decoupled to the details, with minimum needed functionality
only. Anything is easily pluggable somewhere into the pipelines. Pipelines
themselves are easily created as needed. Switching the React SSR build step to
something like Jinja2 templates is one fine thing — and it should be. Replacing
SQLite with Postgres, or with a flat JSON file, or with nothing at all — also
fine. The architecture has opinions about separation. It has no opinions about
implementation.

## What I Am

A valve. Markdown goes in, static HTML comes out, and everything that made the
transformation happen dies when the job is done. The browser serves the result —
its original and only purpose. The build infrastructure does not persist. The
workers are stateless, headless, and ephemeral. They exist for the moment of
transformation and then they are erased.

Four endpoints. Two pipelines. One SQLite file that could be deleted and rebuilt
from source Markdown in seconds. That is the entire system.

## What I Am Not

I am not a framework. Frameworks accumulate. They start small, grow features,
develop opinions about your database, your auth, your templates, your deployment.
They become the thing you maintain instead of the thing that helps you ship.

I am not a platform. Platforms want your content, your audience, your data. They
offer convenience in exchange for control. They enshittify the moment the
economics change.

I am not batteries-included. The ecosystem already has best-in-class tools for
every concern I could bundle internally. Notes apps for writing. React for
theming. SQLite for indexing. Static hosts for serving. Social media for
discussion. I do not rebuild what already exists. I connect what already works.

## Principles

**The Markdown files are the system of record.** Everything else — the database,
the static HTML, the index page — is derived. Delete it all, rebuild from source
in seconds. Your words are the only thing that survives, because your words are
the only thing that matters.

**O(1) builds.** One post published, one post built. The five hundred posts
already in your archive are untouched. Their HTML doesn't change, their cache
headers stay valid, their directories aren't rewritten. The architecture scales
with your publishing frequency, not your backlog.

**The build pipeline is disposable.** It wakes up, transforms input to output,
and vanishes. No residual state. No background processes. No daemon. The next
publish gets a fresh pipeline that knows nothing about the last one. This is not
minimalism for aesthetics. It is architectural honesty about what is needed.

**A theme is a function.** It receives props. It returns HTML. Whether that
function is written in React, Jinja2, Svelte, Handlebars, or tagged template
literals in plain JavaScript — the pipeline does not know and does not care.
The theming contract is the simplest possible interface: data in, markup out.

**The browser serves static files.** That is what browsers were built to do.
No JavaScript runtime on the reader's device. No hydration. No client-side
routing. No loading spinners. Just HTML and CSS, delivered instantly, readable
forever, archivable by the Wayback Machine, printable on paper.

**Infrastructure is replaceable.** The server doesn't matter. The hosting
doesn't matter. The build tool doesn't matter. The domain matters. The words
matter. Everything in between is plumbing, and plumbing should be replaceable
without calling a plumber.

## On Complexity

Modern developers forgot that the complexity of frameworks and workflows was
born out of necessity. These tools were solving problems as it was possible at
the time. With stateless worker pipelines today, layers of that complexity can
be discarded for good — if you think creatively first.

Static site generators were designed before CI/CD existed. To trigger a build,
you sat at a desktop and ran a command. Nobody would trigger two different
builder pipelines somewhere in the cloud, performed by absolutely headless
stateless workers. Times have changed. We should utilize it fully.

In the end there will be a new thinking paradigm: what in your framework
actually serves the result to the intended recipient, and what is just builder
toolkit that is not needed once the job is done — but somehow it persists, it
is heavyweight, and its burly silhouette deters junior developers from the
craft of building things.

## On Features I Don't Have

No admin panel. The API is the interface. Your terminal, your Shortcuts app,
your HTTP client of choice — that is the admin panel.

No comments. Comments were a solution to the problem of "how do people respond
to this" in an era before social media. The permalink is the bridge. Share it,
discuss it where discussion actually happens.

No editor. You already have one. It is the app where you think.

No collaboration workflow. Give your collaborator a token. Revoke it when done.
The entire access control system is a string in an environment variable.

These are not missing features. They are unnecessary features that other
platforms built because they had no alternative, and then kept because removing
them would break the customers who learned to depend on them. note2cms starts
from zero and adds nothing that the ecosystem does not already provide better.

## On Cost

A personal blog should not cost money beyond a domain name. The FastAPI process
fits on any free-tier Python runtime. The static output fits on any free-tier
static host. SQLite is a file that rides along with the process. The total cost
of self-owned, beautifully typeset, permanently archived publishing: twelve
dollars a year for a `.com`.

Your words, your server, your domain, nobody's platform.

---

*You are not gifting your writings to some dirty SaaS. You own it.*
