"""
GitHub Pages deployer — pushes built static HTML to a gh-pages branch.

Uses the GitHub REST API (Contents API) to create/update files.
No git binary needed, no filesystem persistence needed.
Perfect for read-only environments like Leapcell.
"""

import os
import base64
import asyncio
import httpx
from pathlib import Path
from typing import Optional


class GitHubPagesDeployer:
    """
    Deploys static HTML files to a GitHub Pages repository.

    Instead of writing to a local filesystem, the build pipeline
    calls this deployer to push each built HTML file directly to
    the gh-pages branch via GitHub's API.
    """

    def __init__(
        self,
        token: str,
        repo: str,         # "username/repo"
        branch: str = "gh-pages",
    ):
        self.token = token
        self.repo = repo
        self.branch = branch
        self.api_base = f"https://api.github.com/repos/{repo}/contents"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def deploy_file(self, path: str, content: str, message: str = "publish") -> bool:
        """
        Create or update a file in the GitHub Pages repo.

        Args:
            path: File path within the repo (e.g., "posts/my-slug/index.html")
            content: File content as a string
            message: Commit message
        """
        url = f"{self.api_base}/{path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Retry once on 409 to handle concurrent updates by refetching SHA.
            for attempt in range(2):
                sha = await self._get_file_sha(client, url)

                payload = {
                    "message": message,
                    "content": encoded,
                    "branch": self.branch,
                }
                if sha:
                    payload["sha"] = sha

                resp = await client.put(url, json=payload, headers=self.headers)

                if resp.status_code in (200, 201):
                    return True

                if resp.status_code == 409 and attempt == 0:
                    continue

                print(f"[deploy] GitHub API error {resp.status_code}: {resp.text[:200]}")
                return False

    async def delete_file(self, path: str, message: str = "delete post") -> bool:
        """Delete a file from the GitHub Pages repo."""
        url = f"{self.api_base}/{path}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            sha = await self._get_file_sha(client, url)
            if not sha:
                return True  # Already gone

            payload = {
                "message": message,
                "sha": sha,
                "branch": self.branch,
            }

            resp = await client.delete(url, json=payload, headers=self.headers)
            return resp.status_code == 200

    async def deploy_post(self, slug: str, html: str) -> bool:
        """Deploy a single post's HTML."""
        return await self.deploy_file(
            path=f"posts/{slug}/index.html",
            content=html,
            message=f"publish: {slug}",
        )

    async def deploy_index(self, html: str) -> bool:
        """Deploy the blog index page."""
        # Deploy both /posts/index.html and root index.html
        results = await asyncio.gather(
            self.deploy_file("posts/index.html", html, "rebuild index"),
            self.deploy_file("index.html", html, "rebuild index"),
        )
        return all(results)

    async def delete_post(self, slug: str) -> bool:
        """Remove a post from GitHub Pages."""
        return await self.delete_file(
            path=f"posts/{slug}/index.html",
            message=f"delete: {slug}",
        )

    async def ensure_nojekyll(self) -> None:
        """Ensure .nojekyll exists to disable Jekyll processing."""
        await self.deploy_file(".nojekyll", "", "disable jekyll")

    async def _get_file_sha(self, client: httpx.AsyncClient, url: str) -> Optional[str]:
        """Get the SHA of an existing file (needed for updates)."""
        resp = await client.get(
            url,
            headers=self.headers,
            params={"ref": self.branch},
        )
        if resp.status_code == 200:
            return resp.json().get("sha")
        return None
