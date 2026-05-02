"""
ZeusDL GitHub Push — push a local folder to a GitHub repository.

Features
────────
• Creates the GitHub repo if it does not exist.
• Commits all files in the source folder (recursively).
• Supports large repos by chunking commits (max 200 files each).
• Prints progress.
• Pure stdlib + requests (no git binary needed).

CLI usage
─────────
    zeusdl github-push --token ghp_… --repo my-content --dir ./downloads

    Options:
      --token   GitHub personal access token (needs repo scope)
      --repo    Repository name to create/push to
      --dir     Local directory to push  (default: current dir)
      --owner   GitHub username/org (default: token owner)
      --branch  Branch name  (default: main)
      --private Create the repo as private  (default: public)
      --message Commit message prefix
      --chunk   Max files per commit  (default: 200)

Python API
──────────
    from zeusdl.github_push import GithubPusher

    pusher = GithubPusher(token="ghp_…", repo="my-content")
    pusher.push("./downloads")
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_API = 'https://api.github.com'
_IGNORE_PATTERNS = {'.DS_Store', 'Thumbs.db', '.git'}


# ── Low-level GitHub REST helpers ─────────────────────────────────────────────

class _GH:
    def __init__(self, token: str):
        self._headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json',
            'User-Agent': 'ZeusDL-GithubPush/1.0',
        }

    def _request(self, method: str, path: str, body=None) -> dict:
        url = f'{_API}{path}'
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                err = json.loads(raw)
            except Exception:
                err = {'message': raw.decode(errors='replace')}
            raise RuntimeError(f'GitHub API {method} {path} → {e.code}: {err.get("message", "")}')

    def get(self, path: str) -> dict:
        return self._request('GET', path)

    def post(self, path: str, body: dict) -> dict:
        return self._request('POST', path, body)

    def patch(self, path: str, body: dict) -> dict:
        return self._request('PATCH', path, body)

    def get_me(self) -> dict:
        return self.get('/user')

    def create_blob(self, owner: str, repo: str, content_b64: str) -> str:
        data = self.post(f'/repos/{owner}/{repo}/git/blobs',
                         {'content': content_b64, 'encoding': 'base64'})
        return data['sha']

    def get_ref(self, owner: str, repo: str, branch: str) -> Optional[dict]:
        try:
            return self.get(f'/repos/{owner}/{repo}/git/ref/heads/{branch}')
        except RuntimeError:
            return None

    def create_tree(self, owner: str, repo: str, base_tree: str, tree_items: list) -> str:
        body = {'tree': tree_items}
        if base_tree:
            body['base_tree'] = base_tree
        data = self.post(f'/repos/{owner}/{repo}/git/trees', body)
        return data['sha']

    def create_commit(self, owner: str, repo: str, message: str,
                      tree_sha: str, parent_shas: list) -> str:
        body = {'message': message, 'tree': tree_sha, 'parents': parent_shas}
        data = self.post(f'/repos/{owner}/{repo}/git/commits', body)
        return data['sha']

    def update_ref(self, owner: str, repo: str, branch: str, sha: str):
        self.patch(f'/repos/{owner}/{repo}/git/refs/heads/{branch}',
                   {'sha': sha, 'force': True})

    def create_ref(self, owner: str, repo: str, branch: str, sha: str):
        self.post(f'/repos/{owner}/{repo}/git/refs',
                  {'ref': f'refs/heads/{branch}', 'sha': sha})


# ── Main pusher ───────────────────────────────────────────────────────────────

class GithubPusher:
    """
    Push a local directory to a GitHub repository.

    Parameters
    ----------
    token : str
        GitHub personal access token (needs `repo` scope).
    repo : str
        Repository name (will be created if it does not exist).
    owner : str, optional
        GitHub username or org. Defaults to the token owner.
    branch : str
        Target branch. Default: 'main'.
    private : bool
        Create repo as private. Default: False.
    chunk : int
        Max files per commit (avoids GitHub tree-size limits). Default: 200.
    """

    def __init__(
        self,
        token: str,
        repo: str,
        owner: Optional[str] = None,
        branch: str = 'main',
        private: bool = False,
        chunk: int = 200,
    ):
        self._gh = _GH(token)
        self.repo = repo
        self.owner = owner or self._gh.get_me().get('login')
        self.branch = branch
        self.private = private
        self.chunk = chunk

        if not self.owner:
            raise RuntimeError('Could not determine GitHub owner from token.')

    def _ensure_repo(self, description: str = '') -> None:
        """Create the repo if it does not exist."""
        try:
            self._gh.get(f'/repos/{self.owner}/{self.repo}')
            print(f'[github-push] Repo {self.owner}/{self.repo} already exists.')
        except RuntimeError:
            print(f'[github-push] Creating repo {self.owner}/{self.repo}…')
            self._gh.post('/user/repos', {
                'name': self.repo,
                'description': description or f'ZeusDL auto-push — {self.repo}',
                'private': self.private,
                'auto_init': True,
            })
            print(f'[github-push] Repo created: https://github.com/{self.owner}/{self.repo}')

    def _collect_files(self, source_dir: Path) -> list[tuple[str, Path]]:
        """Return list of (repo_path, local_path) for all files."""
        files = []
        for root, dirs, filenames in os.walk(source_dir):
            # Prune ignored dirs
            dirs[:] = [d for d in dirs if d not in _IGNORE_PATTERNS]
            for fn in filenames:
                if fn in _IGNORE_PATTERNS:
                    continue
                local = Path(root) / fn
                repo_path = local.relative_to(source_dir).as_posix()
                files.append((repo_path, local))
        return files

    def _upload_chunk(self, files: list[tuple[str, Path]],
                      base_tree: str, parent_sha: str,
                      commit_msg: str) -> str:
        """Create blobs → tree → commit for one chunk. Returns new commit SHA."""
        tree_items = []
        total = len(files)
        for i, (repo_path, local_path) in enumerate(files, 1):
            try:
                raw = local_path.read_bytes()
            except Exception as e:
                print(f'  [!] Skipping {repo_path}: {e}', file=sys.stderr)
                continue
            content_b64 = base64.b64encode(raw).decode()
            blob_sha = self._gh.create_blob(self.owner, self.repo, content_b64)
            tree_items.append({
                'path': repo_path,
                'mode': '100644',
                'type': 'blob',
                'sha': blob_sha,
            })
            if i % 10 == 0 or i == total:
                pct = i / total * 100
                print(f'  [{i}/{total}] {pct:.0f}% — {repo_path}')

        tree_sha = self._gh.create_tree(self.owner, self.repo, base_tree, tree_items)
        commit_sha = self._gh.create_commit(
            self.owner, self.repo, commit_msg, tree_sha,
            [parent_sha] if parent_sha else [],
        )
        return commit_sha

    def push(self, source_dir: str, description: str = '',
             commit_prefix: str = 'ZeusDL auto-push') -> str:
        """
        Push all files in `source_dir` to the GitHub repo.

        Returns the final commit SHA.
        """
        source = Path(source_dir).resolve()
        if not source.is_dir():
            raise ValueError(f'Source directory does not exist: {source}')

        self._ensure_repo(description)

        # Get current branch state
        ref = self._gh.get_ref(self.owner, self.repo, self.branch)
        if ref:
            parent_sha = ref['object']['sha']
            # Get base tree from commit
            commit_data = self._gh.get(
                f'/repos/{self.owner}/{self.repo}/git/commits/{parent_sha}'
            )
            base_tree = commit_data.get('tree', {}).get('sha', '')
        else:
            parent_sha = ''
            base_tree = ''

        files = self._collect_files(source)
        total_files = len(files)
        print(f'[github-push] {total_files} files to push in {source}')

        if not files:
            print('[github-push] Nothing to push.')
            return parent_sha

        # Chunk the uploads
        chunks = [files[i:i + self.chunk] for i in range(0, len(files), self.chunk)]
        current_parent = parent_sha
        current_tree = base_tree
        final_sha = current_parent

        for idx, chunk in enumerate(chunks, 1):
            msg = f'{commit_prefix}: batch {idx}/{len(chunks)} ({len(chunk)} files)'
            print(f'\n[github-push] Commit {idx}/{len(chunks)} — {len(chunk)} files')
            final_sha = self._upload_chunk(chunk, current_tree, current_parent, msg)
            current_parent = final_sha
            # Update base_tree for next chunk
            commit_data = self._gh.get(
                f'/repos/{self.owner}/{self.repo}/git/commits/{final_sha}'
            )
            current_tree = commit_data.get('tree', {}).get('sha', current_tree)

        # Update / create the branch ref
        if ref:
            self._gh.update_ref(self.owner, self.repo, self.branch, final_sha)
        else:
            self._gh.create_ref(self.owner, self.repo, self.branch, final_sha)

        repo_url = f'https://github.com/{self.owner}/{self.repo}'
        print(f'\n✅ Push complete!')
        print(f'   Repo    : {repo_url}')
        print(f'   Branch  : {self.branch}')
        print(f'   Commit  : {final_sha}')
        print(f'   Files   : {total_files}')
        return final_sha


# ── CLI entry point ───────────────────────────────────────────────────────────

def main_github_push(argv=None):
    import argparse
    p = argparse.ArgumentParser(
        prog='zeusdl github-push',
        description='Push a local folder to a GitHub repository.',
    )
    p.add_argument('--token', required=True, help='GitHub personal access token')
    p.add_argument('--repo', required=True, help='Repository name (created if missing)')
    p.add_argument('--dir', default='.', help='Local directory to push (default: .)')
    p.add_argument('--owner', default=None, help='GitHub username/org (default: token owner)')
    p.add_argument('--branch', default='main', help='Branch name (default: main)')
    p.add_argument('--private', action='store_true', help='Make the repo private')
    p.add_argument('--message', default='ZeusDL auto-push', help='Commit message prefix')
    p.add_argument('--chunk', type=int, default=200, help='Max files per commit (default: 200)')
    p.add_argument('--description', default='', help='Repo description (used on creation)')

    args = p.parse_args(argv)

    pusher = GithubPusher(
        token=args.token,
        repo=args.repo,
        owner=args.owner,
        branch=args.branch,
        private=args.private,
        chunk=args.chunk,
    )
    pusher.push(args.dir, description=args.description, commit_prefix=args.message)
