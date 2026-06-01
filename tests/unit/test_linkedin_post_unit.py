"""Unit tests for pure helpers in scripts/linkedin_post.py.

No network calls, no OAuth, no file I/O.
"""

from __future__ import annotations

import pytest

from scripts.linkedin_post import (
    DEFAULT_CAPTION,
    SCOPES,
    _build_register_upload_body,
    _build_ugc_post_body,
)

PERSON_URN = "urn:li:person:abc123"
ASSET_URN = "urn:li:digitalmediaAsset:xyz789"
CAPTION = "Test caption for the post."


# ---------------------------------------------------------------------------
# _build_register_upload_body
# ---------------------------------------------------------------------------


class TestBuildRegisterUploadBody:
    def test_contains_feedshare_document_recipe(self):
        body = _build_register_upload_body(PERSON_URN)
        recipes = body["registerUploadRequest"]["recipes"]
        assert "urn:li:digitalmediaRecipe:feedshare-document" in recipes

    def test_owner_set_to_person_urn(self):
        body = _build_register_upload_body(PERSON_URN)
        assert body["registerUploadRequest"]["owner"] == PERSON_URN

    def test_service_relationship_is_owner_type(self):
        body = _build_register_upload_body(PERSON_URN)
        rel = body["registerUploadRequest"]["serviceRelationships"][0]
        assert rel["relationshipType"] == "OWNER"

    def test_different_person_urns_produce_different_bodies(self):
        b1 = _build_register_upload_body("urn:li:person:aaa")
        b2 = _build_register_upload_body("urn:li:person:bbb")
        assert b1 != b2


# ---------------------------------------------------------------------------
# _build_ugc_post_body
# ---------------------------------------------------------------------------


class TestBuildUgcPostBody:
    def test_lifecycle_state_draft_by_default(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION)
        assert body["lifecycleState"] == "DRAFT"

    def test_lifecycle_state_published_when_requested(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION, publish=True)
        assert body["lifecycleState"] == "PUBLISHED"

    def test_author_is_person_urn(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION)
        assert body["author"] == PERSON_URN

    def test_asset_urn_in_media(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION)
        media = body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"]
        assert media[0]["media"] == ASSET_URN

    def test_caption_in_share_commentary(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION)
        text = body["specificContent"]["com.linkedin.ugc.ShareContent"][
            "shareCommentary"
        ]["text"]
        assert text == CAPTION

    def test_share_media_category_is_document(self):
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, CAPTION)
        cat = body["specificContent"]["com.linkedin.ugc.ShareContent"][
            "shareMediaCategory"
        ]
        assert cat == "DOCUMENT"

    def test_description_truncated_to_200_chars(self):
        long_caption = "X" * 300
        body = _build_ugc_post_body(PERSON_URN, ASSET_URN, long_caption)
        desc = body["specificContent"]["com.linkedin.ugc.ShareContent"]["media"][0][
            "description"
        ]["text"]
        assert len(desc) <= 200


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_caption_is_non_empty(self):
        assert len(DEFAULT_CAPTION.strip()) > 0

    def test_scopes_include_w_member_social(self):
        assert "w_member_social" in SCOPES

    def test_scopes_include_profile_read(self):
        assert any("profile" in s or "liteprofile" in s for s in SCOPES)
