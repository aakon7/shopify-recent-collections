"""
Facebook Post Likers → Page Invite Script
==========================================

This script fetches people who reacted to your Facebook page posts
but haven't yet liked your page, so you can invite them.

SETUP:
1. Go to https://developers.facebook.com and create an app
2. Use the Graph API Explorer to generate a Page Access Token with:
   - pages_read_engagement
   - pages_manage_metadata
   - pages_read_user_content
3. Set your PAGE_ACCESS_TOKEN and PAGE_ID below (or use env vars)

NOTE: Facebook does not provide a public API endpoint to send
"invite to like page" requests programmatically. This script
identifies who to invite — you then use Facebook's built-in
invite button on your page's post likes list.
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "YOUR_PAGE_ACCESS_TOKEN")
PAGE_ID = os.getenv("FB_PAGE_ID", "YOUR_PAGE_ID")
GRAPH_API_VERSION = "v19.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# Rate limiting: Facebook allows ~200 calls per hour per user
REQUEST_DELAY = 1.0  # seconds between API calls
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def api_get(endpoint: str, params: dict | None = None) -> dict:
    """Make a GET request to the Facebook Graph API with retry logic."""
    url = f"{GRAPH_API_BASE}/{endpoint}"
    if params is None:
        params = {}
    params["access_token"] = PAGE_ACCESS_TOKEN

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=30)

            if resp.status_code == 429:
                wait = 60 * attempt
                log.warning("Rate limited. Waiting %d seconds...", wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp.json()

        except requests.exceptions.HTTPError as exc:
            error_data = {}
            try:
                error_data = exc.response.json()
            except Exception:
                pass
            log.error(
                "API error (attempt %d/%d): %s — %s",
                attempt, MAX_RETRIES, exc, error_data,
            )
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2 * attempt)

    return {}


def paginate_all(endpoint: str, params: dict | None = None) -> list:
    """Follow pagination cursors and collect all results."""
    results = []
    data = api_get(endpoint, params)

    while True:
        results.extend(data.get("data", []))
        paging = data.get("paging", {})
        next_url = paging.get("next")
        if not next_url:
            break
        # next_url is a full URL; extract relative part
        log.info("  Fetching next page (%d collected so far)...", len(results))
        time.sleep(REQUEST_DELAY)
        try:
            resp = requests.get(next_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.error("Pagination error: %s", exc)
            break

    return results


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def verify_token() -> dict:
    """Verify the access token is valid and has required permissions."""
    log.info("Verifying access token...")
    data = api_get("me", {"fields": "id,name"})
    if "id" not in data:
        log.error("Invalid token. Response: %s", data)
        sys.exit(1)
    log.info("Authenticated as: %s (ID: %s)", data.get("name"), data.get("id"))
    return data


def get_page_posts(since_days: int = 90) -> list:
    """Fetch recent posts from the page."""
    since_ts = int((datetime.now() - timedelta(days=since_days)).timestamp())
    log.info("Fetching posts from the last %d days...", since_days)
    posts = paginate_all(
        f"{PAGE_ID}/posts",
        {"fields": "id,message,created_time", "since": since_ts},
    )
    log.info("Found %d posts.", len(posts))
    return posts


def get_post_reactions(post_id: str) -> list:
    """Fetch all reactions (likes, love, etc.) for a post."""
    return paginate_all(
        f"{post_id}/reactions",
        {"fields": "id,name,type"},
    )


def get_page_fans() -> set:
    """
    Try to get current page followers/fans.
    Note: This endpoint may not return all fans depending on permissions.
    """
    log.info("Fetching current page fans (if accessible)...")
    try:
        fans = paginate_all(f"{PAGE_ID}/fans", {"fields": "id"})
        fan_ids = {f["id"] for f in fans}
        log.info("Found %d known fans.", len(fan_ids))
        return fan_ids
    except Exception:
        log.warning(
            "Could not fetch fans list (this is normal — "
            "Facebook restricts this endpoint). "
            "All reactors will be included in results."
        )
        return set()


def collect_invitable_users(posts: list, existing_fans: set) -> dict:
    """
    For each post, collect users who reacted but are NOT existing fans.
    Returns {user_id: {"name": ..., "posts": [...], "reaction_types": set()}}.
    """
    users: dict = {}

    for i, post in enumerate(posts, 1):
        post_id = post["id"]
        snippet = (post.get("message") or "")[:50]
        log.info(
            "Processing post %d/%d: %s... (ID: %s)",
            i, len(posts), snippet, post_id,
        )

        reactions = get_post_reactions(post_id)
        log.info("  → %d reactions", len(reactions))

        for reaction in reactions:
            uid = reaction["id"]
            if uid in existing_fans:
                continue

            if uid not in users:
                users[uid] = {
                    "name": reaction.get("name", "Unknown"),
                    "posts": [],
                    "reaction_types": set(),
                }
            users[uid]["posts"].append(post_id)
            users[uid]["reaction_types"].add(reaction.get("type", "LIKE"))

    return users


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def save_results(users: dict, output_file: str):
    """Save the invite list to a JSON file."""
    # Convert sets to lists for JSON serialization
    serializable = {}
    for uid, info in users.items():
        serializable[uid] = {
            "name": info["name"],
            "post_count": len(info["posts"]),
            "reaction_types": sorted(info["reaction_types"]),
            "post_ids": info["posts"],
        }

    # Sort by number of posts interacted with (most engaged first)
    sorted_users = dict(
        sorted(serializable.items(), key=lambda x: x[1]["post_count"], reverse=True)
    )

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "total_invitable": len(sorted_users),
                "users": sorted_users,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    log.info("Results saved to %s", output_file)


def print_summary(users: dict):
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print(f"  INVITABLE USERS: {len(users)}")
    print("=" * 60)

    sorted_users = sorted(users.items(), key=lambda x: len(x[1]["posts"]), reverse=True)

    print(f"\n{'Name':<30} {'Posts':<8} {'Reactions'}")
    print("-" * 60)
    for uid, info in sorted_users[:25]:
        reactions = ", ".join(sorted(info["reaction_types"]))
        print(f"{info['name']:<30} {len(info['posts']):<8} {reactions}")

    if len(users) > 25:
        print(f"  ... and {len(users) - 25} more (see output file)")

    print("\nNEXT STEPS:")
    print("  1. Go to your Facebook Page")
    print("  2. Open a post and click on the reactions count")
    print("  3. Click 'Invite' next to each person's name")
    print("  (Facebook only allows page admins to do this manually)")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Find Facebook post likers to invite to your page.",
    )
    parser.add_argument(
        "--days", type=int, default=90,
        help="How many days of posts to look back (default: 90)",
    )
    parser.add_argument(
        "--output", type=str, default="invitable_users.json",
        help="Output JSON file path (default: invitable_users.json)",
    )
    parser.add_argument(
        "--page-id", type=str, default=None,
        help="Facebook Page ID (overrides FB_PAGE_ID env var)",
    )
    parser.add_argument(
        "--token", type=str, default=None,
        help="Page Access Token (overrides FB_PAGE_ACCESS_TOKEN env var)",
    )
    args = parser.parse_args()

    global PAGE_ACCESS_TOKEN, PAGE_ID
    if args.token:
        PAGE_ACCESS_TOKEN = args.token
    if args.page_id:
        PAGE_ID = args.page_id

    if PAGE_ACCESS_TOKEN == "YOUR_PAGE_ACCESS_TOKEN":
        print("ERROR: Set your Page Access Token via:")
        print("  --token YOUR_TOKEN")
        print("  or env var FB_PAGE_ACCESS_TOKEN")
        sys.exit(1)

    if PAGE_ID == "YOUR_PAGE_ID":
        print("ERROR: Set your Page ID via:")
        print("  --page-id YOUR_ID")
        print("  or env var FB_PAGE_ID")
        sys.exit(1)

    # Run
    verify_token()
    existing_fans = get_page_fans()
    posts = get_page_posts(since_days=args.days)

    if not posts:
        log.info("No posts found in the last %d days.", args.days)
        return

    users = collect_invitable_users(posts, existing_fans)

    if not users:
        log.info("No new users to invite — everyone already likes your page!")
        return

    save_results(users, args.output)
    print_summary(users)


if __name__ == "__main__":
    main()
