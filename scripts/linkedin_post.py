#!/usr/bin/env python3
"""Upload a PDF carousel to LinkedIn as a draft (or published) post.

One-time setup
--------------
1. Go to https://www.linkedin.com/developers/apps/ → New app
2. Under "Products", add **Share on LinkedIn**
3. Under "Auth" → OAuth 2.0 settings → add Authorized Redirect URL:
       http://localhost:8080/callback
4. Copy Client ID and Client Secret into .env:
       LINKEDIN_CLIENT_ID=your_client_id
       LINKEDIN_CLIENT_SECRET=your_client_secret
5. Run the auth flow (opens a browser tab once):
       uv run python scripts/linkedin_post.py --auth
   Approve the app on LinkedIn → token saved to .linkedin_token.json

Usage
-----
    # Save as draft (default — nothing is public yet)
    uv run python scripts/linkedin_post.py \\
        --pdf artifacts/carousel_prod_20260527.pdf

    # Custom caption
    uv run python scripts/linkedin_post.py \\
        --pdf artifacts/carousel_prod_20260527.pdf \\
        --caption "Your post text here..."

    # Publish immediately instead of drafting
    uv run python scripts/linkedin_post.py \\
        --pdf artifacts/carousel_prod_20260527.pdf --publish

Notes
-----
- Drafts created via the API are stored under lifecycleState=DRAFT and may
  not appear in LinkedIn's browser draft editor. To publish a draft later,
  re-run with --publish (which creates a new PUBLISHED post).
- Access tokens expire after 60 days; refresh tokens after 365 days.
  This script refreshes automatically when the access token is near expiry.
- API surface used (v2, verified 2026-05):
    POST /v2/assets?action=registerUpload
    PUT  {uploadUrl}          (binary document upload)
    POST /v2/ugcPosts
    GET  /v2/me
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_FILE = Path(".linkedin_token.json")
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API_BASE = "https://api.linkedin.com/v2"
SCOPES = ["r_liteprofile", "w_member_social"]
REDIRECT_URI = "http://localhost:8080/callback"

DEFAULT_CAPTION = """\
I tested two RAG architectures on 10 adversarial banking compliance questions.

Basic RAG retrieves once and generates. Agentic RAG grades its own retrieval \
quality and rewrites the query when it knows it fetched the wrong documents.

Score gap on the hardest question (audit threshold + hallucination detected): \
0.67 → 0.97.

Swipe to see the full breakdown →

Built with LangGraph + Claude Sonnet 4.6 + voyage-law-2 embeddings on NCUA \
regulatory corpus.

#RAG #AgenticAI #LLM #FinancialCompliance #LangGraph #Anthropic #Claude"""


# ---------------------------------------------------------------------------
# Pure request-body builders (exported for unit testing)
# ---------------------------------------------------------------------------


def _build_register_upload_body(person_urn: str) -> dict:
    """Build the payload for POST /v2/assets?action=registerUpload."""
    return {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-document"],
            "owner": person_urn,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }
            ],
        }
    }


def _build_ugc_post_body(
    person_urn: str,
    asset_urn: str,
    caption: str,
    publish: bool = False,
) -> dict:
    """Build the payload for POST /v2/ugcPosts."""
    return {
        "author": person_urn,
        "lifecycleState": "PUBLISHED" if publish else "DRAFT",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption},
                "shareMediaCategory": "DOCUMENT",
                "media": [
                    {
                        "status": "READY",
                        "description": {"text": caption[:200]},
                        "media": asset_urn,
                        "title": {"text": "Agentic vs Basic RAG: Banking Compliance Demo"},
                    }
                ],
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def _load_token() -> dict | None:
    if TOKEN_FILE.exists():
        return json.loads(TOKEN_FILE.read_text())
    return None


def _save_token(token: dict) -> None:
    TOKEN_FILE.write_text(json.dumps(token, indent=2))


def _refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    data = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _get_valid_token(client_id: str, client_secret: str) -> str:
    """Return a valid access token, refreshing if near expiry."""
    token = _load_token()
    if not token:
        raise SystemExit(
            "No token found. Run first: uv run python scripts/linkedin_post.py --auth"
        )
    if token.get("expires_at", 0) - time.time() < 300:
        refreshed = _refresh_access_token(
            client_id, client_secret, token["refresh_token"]
        )
        token.update(refreshed)
        token["expires_at"] = time.time() + refreshed["expires_in"]
        _save_token(token)
    return token["access_token"]


# ---------------------------------------------------------------------------
# OAuth 2.0 flow (Authorization Code + local callback server)
# ---------------------------------------------------------------------------


def run_auth_flow(client_id: str, client_secret: str) -> None:
    """Open a browser, capture the OAuth callback, and save the token."""
    state = secrets.token_urlsafe(16)
    params = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": " ".join(SCOPES),
            "state": state,
        }
    )
    auth_url = f"{AUTH_URL}?{params}"

    captured: dict = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/callback":
                qs = urllib.parse.parse_qs(parsed.query)
                captured["code"] = qs.get("code", [None])[0]
                captured["state"] = qs.get("state", [None])[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h2>Authorized. You can close this tab.</h2>")

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("localhost", 8080), _Handler)
    webbrowser.open(auth_url)
    print("Waiting for LinkedIn authorization (browser should have opened)…")
    while "code" not in captured:
        server.handle_request()
    server.server_close()

    if captured.get("state") != state:
        raise SystemExit("OAuth state mismatch — possible CSRF. Aborting.")

    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": captured["code"],
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    with urllib.request.urlopen(req) as resp:
        token = json.loads(resp.read())

    token["expires_at"] = time.time() + token.get("expires_in", 3600 * 24 * 60)
    _save_token(token)
    print(f"✓ Token saved → {TOKEN_FILE}")


# ---------------------------------------------------------------------------
# LinkedIn API calls
# ---------------------------------------------------------------------------


def _api_json(method: str, path: str, access_token: str, body: dict | None = None) -> dict:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("X-Restli-Protocol-Version", "2.0.0")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _get_person_id(access_token: str) -> str:
    return _api_json("GET", "/me", access_token)["id"]


def _register_document_upload(access_token: str, person_urn: str) -> tuple[str, str]:
    """Returns (upload_url, asset_urn)."""
    result = _api_json(
        "POST",
        "/assets?action=registerUpload",
        access_token,
        _build_register_upload_body(person_urn),
    )
    upload_url = result["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = result["value"]["asset"]
    return upload_url, asset_urn


def _upload_pdf(upload_url: str, pdf_path: Path, access_token: str) -> None:
    pdf_bytes = pdf_path.read_bytes()
    req = urllib.request.Request(upload_url, data=pdf_bytes, method="PUT")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(req):
        pass


def _create_post(
    access_token: str,
    person_urn: str,
    asset_urn: str,
    caption: str,
    publish: bool = False,
) -> str:
    result = _api_json(
        "POST",
        "/ugcPosts",
        access_token,
        _build_ugc_post_body(person_urn, asset_urn, caption, publish),
    )
    return result.get("id", "")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    from dotenv import load_dotenv
    from rich.console import Console

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Upload a PDF carousel to LinkedIn.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Run --auth first (once) to authorize; then use --pdf for uploads.",
    )
    parser.add_argument(
        "--auth",
        action="store_true",
        help="Run OAuth flow to obtain and save a LinkedIn token.",
    )
    parser.add_argument("--pdf", metavar="PATH", help="PDF file to upload as a carousel.")
    parser.add_argument(
        "--caption",
        metavar="TEXT",
        default=DEFAULT_CAPTION,
        help="Post caption (default: built-in project caption).",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Publish immediately. Default: save as DRAFT.",
    )
    args = parser.parse_args(argv)

    console = Console()

    client_id = os.getenv("LINKEDIN_CLIENT_ID", "")
    client_secret = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        console.print(
            "[red]Error:[/red] Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET in .env\n"
            "See .env.example for setup instructions."
        )
        raise SystemExit(1)

    if args.auth:
        run_auth_flow(client_id, client_secret)
        return

    if not args.pdf:
        parser.error("--pdf PATH is required (or use --auth for first-time setup)")

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        console.print(f"[red]Error:[/red] PDF not found: {pdf_path}")
        raise SystemExit(1)

    access_token = _get_valid_token(client_id, client_secret)

    console.print("[dim]Fetching LinkedIn profile…[/dim]")
    person_id = _get_person_id(access_token)
    person_urn = f"urn:li:person:{person_id}"

    console.print(f"[dim]Registering document upload ({pdf_path.name})…[/dim]")
    upload_url, asset_urn = _register_document_upload(access_token, person_urn)

    size_kb = pdf_path.stat().st_size / 1024
    console.print(f"[dim]Uploading {size_kb:.1f} KB…[/dim]")
    _upload_pdf(upload_url, pdf_path, access_token)

    mode = "PUBLISHED" if args.publish else "DRAFT"
    console.print(f"[dim]Creating {mode} post…[/dim]")
    post_urn = _create_post(access_token, person_urn, asset_urn, args.caption, args.publish)

    label = "Published" if args.publish else "Draft saved"
    console.print(f"[green]✓[/green] {label} — post URN: {post_urn}")
    if not args.publish:
        console.print(
            "[dim]Re-run with --publish when ready to go live.[/dim]"
        )


if __name__ == "__main__":
    main()
