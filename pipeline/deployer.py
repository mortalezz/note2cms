"""
Deployers — push built static HTML & assets to GitHub Pages (single-commit Git Data API)
or to the local filesystem.
"""

import base64
import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import httpx


@dataclass
class DeployBatch:
    """Collection of file writes and deletions applied atomically per publish."""

    writes: dict[str, Union[bytes, str]] = field(default_factory=dict)
    deletes: set[str] = field(default_factory=set)
    delete_prefixes: set[str] = field(default_factory=set)

    def add(self, path: str, content: Union[bytes, str]) -> None:
        norm = path.lstrip("/")
        self.deletes.discard(norm)
        self.writes[norm] = content

    def remove(self, path: str) -> None:
        norm = path.lstrip("/")
        self.writes.pop(norm, None)
        self.deletes.add(norm)

    def remove_prefix(self, prefix: str) -> None:
        norm = prefix.lstrip("/")
        if norm and not norm.endswith("/"):
            norm += "/"
        if norm:
            self.delete_prefixes.add(norm)


class LocalDeployer:
    """Deploys a DeployBatch to the local static directory."""

    def __init__(self, static_dir: Path):
        self.static_dir = Path(static_dir)

    def _resolve_local_path(self, repo_path: str) -> Path:
        norm = repo_path.lstrip("/")
        if norm.startswith("posts/"):
            norm = norm[len("posts/"):]
        return self.static_dir / norm

    async def deploy_batch(self, batch: DeployBatch, message: str = "") -> bool:
        self.static_dir.mkdir(parents=True, exist_ok=True)

        for prefix in batch.delete_prefixes:
            target = self._resolve_local_path(prefix.rstrip("/"))
            if target.exists() and target.is_dir():
                shutil.rmtree(target)

        for path in batch.deletes:
            target = self._resolve_local_path(path)
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                    parent = target.parent
                    while parent != self.static_dir and parent.exists():
                        try:
                            parent.rmdir()
                            parent = parent.parent
                        except OSError:
                            break

        for path, content in batch.writes.items():
            target = self._resolve_local_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")

        return True


class GitHubPagesDeployer:
    """
    Deploys static HTML & media files to a GitHub Pages repository.

    Uses GitHub's Git Data API to commit an entire DeployBatch in a single
    atomic commit, falling back to Contents API when initializing an empty branch.
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
        self.repo_api = f"https://api.github.com/repos/{repo}"
        self.api_base = f"{self.repo_api}/contents"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def deploy_batch(self, batch: DeployBatch, message: str = "publish") -> bool:
        """Apply all writes and deletions in one single GitHub commit."""
        if not batch.writes and not batch.deletes and not batch.delete_prefixes:
            return True

        async with httpx.AsyncClient(timeout=60.0) as client:
            for attempt in range(2):
                ref_resp = await client.get(
                    f"{self.repo_api}/git/ref/heads/{self.branch}",
                    headers=self.headers,
                )
                if ref_resp.status_code == 404:
                    # Empty/uninitialized branch: bootstrap via Contents API
                    return await self._fallback_sequential_writes(batch, message)
                if ref_resp.status_code != 200:
                    print(f"[deploy] GitHub ref error {ref_resp.status_code}: {ref_resp.text[:200]}")
                    return False

                base_commit_sha = ref_resp.json()["object"]["sha"]
                commit_resp = await client.get(
                    f"{self.repo_api}/git/commits/{base_commit_sha}",
                    headers=self.headers,
                )
                if commit_resp.status_code != 200:
                    print(f"[deploy] GitHub commit error {commit_resp.status_code}: {commit_resp.text[:200]}")
                    return False

                base_tree_sha = commit_resp.json()["tree"]["sha"]
                tree_items = []

                # Expand deletions only when requested
                if batch.deletes or batch.delete_prefixes:
                    tree_list_resp = await client.get(
                        f"{self.repo_api}/git/trees/{base_tree_sha}",
                        params={"recursive": "1"},
                        headers=self.headers,
                    )
                    if tree_list_resp.status_code == 200:
                        existing_paths = {
                            item["path"]
                            for item in tree_list_resp.json().get("tree", [])
                            if item.get("type") == "blob"
                        }
                        to_delete = {p for p in batch.deletes if p in existing_paths}
                        for prefix in batch.delete_prefixes:
                            for ep in existing_paths:
                                if ep.startswith(prefix):
                                    to_delete.add(ep)
                        for del_path in sorted(to_delete):
                            if del_path not in batch.writes:
                                tree_items.append({
                                    "path": del_path,
                                    "mode": "100644",
                                    "type": "blob",
                                    "sha": None,
                                })

                # Prepare writes (blobs for binary or large text, inline for small text)
                for path, data in batch.writes.items():
                    if isinstance(data, bytes) or len(data) > 100_000:
                        blob_sha = await self._create_blob(client, data)
                        if not blob_sha:
                            return False
                        tree_items.append({
                            "path": path,
                            "mode": "100644",
                            "type": "blob",
                            "sha": blob_sha,
                        })
                    else:
                        tree_items.append({
                            "path": path,
                            "mode": "100644",
                            "type": "blob",
                            "content": data,
                        })

                if not tree_items:
                    return True

                new_tree_resp = await client.post(
                    f"{self.repo_api}/git/trees",
                    json={"base_tree": base_tree_sha, "tree": tree_items},
                    headers=self.headers,
                )
                if new_tree_resp.status_code not in (200, 201):
                    print(f"[deploy] GitHub tree error {new_tree_resp.status_code}: {new_tree_resp.text[:200]}")
                    return False
                new_tree_sha = new_tree_resp.json()["sha"]

                new_commit_resp = await client.post(
                    f"{self.repo_api}/git/commits",
                    json={
                        "message": message,
                        "tree": new_tree_sha,
                        "parents": [base_commit_sha],
                    },
                    headers=self.headers,
                )
                if new_commit_resp.status_code not in (200, 201):
                    print(f"[deploy] GitHub commit create error {new_commit_resp.status_code}: {new_commit_resp.text[:200]}")
                    return False
                new_commit_sha = new_commit_resp.json()["sha"]

                patch_resp = await client.patch(
                    f"{self.repo_api}/git/refs/heads/{self.branch}",
                    json={"sha": new_commit_sha},
                    headers=self.headers,
                )
                if patch_resp.status_code in (200, 201):
                    return True
                if patch_resp.status_code in (409, 422) and attempt == 0:
                    continue

                print(f"[deploy] GitHub ref update error {patch_resp.status_code}: {patch_resp.text[:200]}")
                return False

        return False

    async def _create_blob(self, client: httpx.AsyncClient, data: Union[bytes, str]) -> Optional[str]:
        if isinstance(data, bytes):
            payload = {
                "content": base64.b64encode(data).decode("ascii"),
                "encoding": "base64",
            }
        else:
            payload = {"content": data, "encoding": "utf-8"}

        resp = await client.post(
            f"{self.repo_api}/git/blobs",
            json=payload,
            headers=self.headers,
        )
        if resp.status_code in (200, 201):
            return resp.json().get("sha")
        print(f"[deploy] GitHub blob error {resp.status_code}: {resp.text[:200]}")
        return None

    async def _fallback_sequential_writes(self, batch: DeployBatch, message: str) -> bool:
        for path, content in batch.writes.items():
            ok = await self.deploy_file(path, content, message)
            if not ok:
                return False
        return True

    async def deploy_file(
        self,
        path: str,
        content: Union[str, bytes],
        message: str = "publish",
    ) -> bool:
        """
        Create or update a single file in the GitHub Pages repo (Contents API).
        """
        url = f"{self.api_base}/{path}"
        raw_bytes = content.encode("utf-8") if isinstance(content, str) else content
        encoded = base64.b64encode(raw_bytes).decode("ascii")

        async with httpx.AsyncClient(timeout=30.0) as client:
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

            resp = await client.request("DELETE", url, json=payload, headers=self.headers)
            return resp.status_code == 200

    async def deploy_post(self, slug: str, html: str) -> bool:
        """Deploy a single post's HTML."""
        return await self.deploy_file(
            path=f"posts/{slug}/index.html",
            content=html,
            message=f"publish: {slug}",
        )

    async def deploy_index(self, html: str) -> bool:
        """Deploy the blog index page in one commit."""
        batch = DeployBatch()
        batch.add("posts/index.html", html)
        batch.add("index.html", html)
        return await self.deploy_batch(batch, message="rebuild index")

    async def delete_post(self, slug: str) -> bool:
        """Remove a post and its assets from GitHub Pages."""
        batch = DeployBatch()
        batch.remove(f"posts/{slug}/index.html")
        batch.remove_prefix(f"posts/assets/{slug}/")
        return await self.deploy_batch(batch, message=f"delete: {slug}")

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
