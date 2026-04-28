"""Build the JSON `email-content` document Omnisend's PUT endpoint expects.

This is the canonical FMS skeleton: 3 sections (logo, main, footer) where
sections 0 and 2 are byte-identical across all days, and section 1 is the
menu + 19 banner blocks + Mystery Bundle.

Block IDs come from the brand config (template-reused). Image source IDs
come from the Omnisend image library. The `resizeHeight` is computed from
the source height — never hardcoded.

Ported from reference_skill/scripts/build_day_content.py with:
- BrandConfig drives all the constants (no hardcoded fabricmegastore.com)
- Per-block render is exposed as a public function (used by edits)
- Footer/logo bodies are the literal strings from the FMS template
"""
from __future__ import annotations

from typing import Any

from .config import BrandConfig
from .models import Banner

# Footer block IDs (from references/template.md). These don't vary per email.
_FOOTER_SECTION_ID = "617907d759b3af4e5159b634"
_FOOTER_ROW_ID = "617907d759b3af4e5159b635"
_FOOTER_COL_ID = "617907d759b3af4e5159b636"
_FOOTER_SOCIAL_ID = "62162bb9fcf43715207baf47"
_FOOTER_COPYRIGHT_ID = "617907ec59b3af4e5159b638"
_FOOTER_ADDRESS_ID = "617907de59b3af4e5159b637"
_FOOTER_UNSUB_ID = "617907ef59b3af4e5159b639"

# Logo section IDs.
_LOGO_SECTION_ID = "6215fec5d3ad0a41ac6e0130"
_LOGO_ROW_ID = "6215fec5d3ad0a41ac6e0131"
_LOGO_COL_ID = "6215fec5d3ad0a41ac6e0132"
_LOGO_BLOCK_ID = "6220ab215ec14498ae421638"

# Main content section IDs.
_MAIN_SECTION_ID = "6098c67f66c23deb72eb779a"
_MAIN_ROW_ID = "6098c67f66c23deb72eb779b"
_MAIN_COL_ID = "6098c67f66c23deb72eb779c"
_MENU_BLOCK_ID = "69a0bd05741c607aa2964079"
_MENU_ITEM_IDS = [
    "69a0bd05741c607aa296407a",
    "69a0bd05741c607aa296407b",
    "69a0bd05741c607aa296407c",
    "69a0bd94741c607aa296407d",
]

# Mystery Bundle is always the same image, same block, last in the stack.
_MYSTERY_HEIGHT = 565
_MYSTERY_RESIZE_HEIGHT = 531.75


def image_block(block_id: str, banner: Banner, brand: BrandConfig) -> dict[str, Any]:
    """Render one image block. Used by build (top-level) and edits (in-place swap)."""
    rh = brand.banner_sizes.resize_height(banner.height)
    sid = banner.source_id
    return {
        "id": block_id,
        "type": "image",
        "image": {
            "altText": banner.title,
            "height": banner.height,
            "id": sid,
            "link": f"{brand.shopify_base_url}/collections/{banner.handle}",
            "resizeHeight": rh,
            "resizeWidth": brand.banner_sizes.display_width,
            "source": f"/image/newsletter/{sid}",
            "width": brand.banner_sizes.source_width,
        },
        "styleProperties": {
            "alignment": "center",
            "color": "#0e1b4d",
            "paddingBottom": "0px",
            "paddingLeft": "0px",
            "paddingRight": "0px",
            "paddingTop": "0px",
        },
    }


def mystery_block(brand: BrandConfig) -> dict[str, Any]:
    sid = brand.template.mystery_image_id
    return {
        "id": brand.block_ids.mystery,
        "type": "image",
        "image": {
            "altText": "",
            "height": _MYSTERY_HEIGHT,
            "id": sid,
            "link": brand.template.mystery_product_url,
            "resizeHeight": _MYSTERY_RESIZE_HEIGHT,
            "resizeWidth": brand.banner_sizes.display_width,
            "source": f"/image/newsletter/{sid}",
            "width": brand.banner_sizes.source_width,
        },
        "styleProperties": {
            "alignment": "center",
            "color": "#0e1b4d",
            "paddingBottom": "0px",
            "paddingLeft": "0px",
            "paddingRight": "0px",
            "paddingTop": "0px",
        },
    }


def menu_block(brand: BrandConfig) -> dict[str, Any]:
    if len(brand.template.menu_handles) != len(brand.template.menu_labels):
        raise ValueError("menu_handles and menu_labels must be the same length")
    if len(brand.template.menu_handles) != 4:
        raise ValueError("FMS template expects exactly 4 menu items")

    components = []
    for i, (handle, label) in enumerate(
        zip(brand.template.menu_handles, brand.template.menu_labels, strict=True)
    ):
        href = f"{brand.shopify_base_url}/collections/{handle}"
        text = (
            f'<p><a class="menu-block-link" href="{href}" '
            f'style="color: #0e1b4d;font-weight: bold;" target="_blank">{label}</a></p>'
        )
        components.append(
            {
                "id": _MENU_ITEM_IDS[i],
                "type": "text",
                "role": "menu_text",
                "stylePresetID": "paragraph",
                "styleProperties": {"alignment": "center", "color": "#0e1b4d"},
                "text": text,
            }
        )

    return {
        "id": _MENU_BLOCK_ID,
        "type": "menu",
        "stylePresetID": "paragraph",
        "styleProperties": {
            "color": "#0e1b4d",
            "paddingBottom": "12px",
            "paddingLeft": "12px",
            "paddingRight": "12px",
            "paddingTop": "12px",
        },
        "components": components,
    }


def _logo_section(brand: BrandConfig) -> dict[str, Any]:
    return {
        "id": _LOGO_SECTION_ID,
        "rows": [
            {
                "id": _LOGO_ROW_ID,
                "columns": [
                    {
                        "id": _LOGO_COL_ID,
                        "width": "800px",
                        "blocks": [
                            {
                                "id": _LOGO_BLOCK_ID,
                                "type": "logo",
                                "logo": {
                                    "link": "[[account.website]]",
                                    "resizeWidth": 528,
                                },
                                "styleProperties": {
                                    "alignment": "center",
                                    "paddingBottom": "0px",
                                    "paddingLeft": "0px",
                                    "paddingRight": "0px",
                                    "paddingTop": "0px",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
        "styleProperties": {
            "backgroundColor": "#FFFFFF",
            "isBackgroundPaddingsExcluded": True,
            "paddingBottom": "0px",
            "paddingLeft": "0px",
            "paddingRight": "0px",
            "paddingTop": "0px",
            "verticalAlign": "middle",
        },
        "visibility": {"isDesktopVisible": True, "isMobileVisible": True},
    }


def _footer_section() -> dict[str, Any]:
    """Hard-coded FMS footer. Required: text block must contain [[unsubscribe_link]]."""
    return {
        "id": _FOOTER_SECTION_ID,
        "rows": [
            {
                "id": _FOOTER_ROW_ID,
                "columns": [
                    {
                        "id": _FOOTER_COL_ID,
                        "width": "752px",
                        "blocks": [
                            {
                                "id": _FOOTER_SOCIAL_ID,
                                "type": "social",
                                "social": {
                                    "icons": [
                                        {
                                            "link": "https://facebook.com/fabricmegastore",
                                            "source": "dynamicImage/social/facebook/48/24/default",
                                            "type": "facebook",
                                        },
                                        {
                                            "link": "https://instagram.com/fabricmegastore",
                                            "source": "dynamicImage/social/instagram/48/24/default",
                                            "type": "instagram",
                                        },
                                        {
                                            "link": "https://twitter.com/FabricMegaStore",
                                            "source": "dynamicImage/social/twitter/48/24/default",
                                            "type": "twitter",
                                        },
                                        {
                                            "link": "https://tiktok.com/",
                                            "source": "dynamicImage/social/tiktok/48/24/default",
                                            "type": "tiktok",
                                        },
                                    ],
                                    "shape": "circle",
                                    "size": "24px",
                                },
                                "styleProperties": {"alignment": "left", "padding": "12px"},
                            },
                            {
                                "id": _FOOTER_COPYRIGHT_ID,
                                "type": "text",
                                "stylePresetID": "footnote",
                                "styleProperties": {
                                    "color": "#FFFFFF",
                                    "linkColor": "#d66083",
                                    "padding": "12px",
                                },
                                "text": '<p style="margin: 0px;">© [[account.name]]</p>',
                            },
                            {
                                "id": _FOOTER_ADDRESS_ID,
                                "type": "text",
                                "stylePresetID": "footnote",
                                "styleProperties": {
                                    "color": "#FFFFFF",
                                    "linkColor": "#d66083",
                                    "padding": "12px",
                                },
                                "text": (
                                    '<p style="margin: 0px;">[[account.address]], '
                                    "[[account.city]], [[account.country]], "
                                    '[[account.zipCode]]<br id="isPasted"></p>'
                                    '<p style="margin: 0px;" '
                                    'data-translation-key="permission_reminder"><br>'
                                    "This email was sent to [[contact.email]] because "
                                    "you've subscribed on our site or made a purchase.</p>"
                                ),
                            },
                            {
                                "id": _FOOTER_UNSUB_ID,
                                "type": "text",
                                "stylePresetID": "footnote",
                                "styleProperties": {
                                    "color": "#FFFFFF",
                                    "linkColor": "#d66083",
                                    "padding": "12px",
                                },
                                "text": (
                                    '<p style="margin: 0px;">'
                                    '<a href="[[preference_link]]" target="_blank" '
                                    'data-translation-key="preference">'
                                    "Update preferences</a> | "
                                    '<a href="[[unsubscribe_link]]" target="_blank" '
                                    'data-translation-key="unsubscribe">Unsubscribe</a></p>'
                                ),
                            },
                        ],
                    }
                ],
            }
        ],
        "styleProperties": {
            "backgroundColor": "#0e1b4d",
            "paddingBottom": "24px",
            "paddingLeft": "24px",
            "paddingRight": "24px",
            "paddingTop": "24px",
        },
        "visibility": {"isDesktopVisible": True, "isMobileVisible": True},
    }


def _general_settings(brand: BrandConfig) -> dict[str, Any]:
    return {
        "body": {"backgroundColor": "#FFFFFF"},
        "buttonPresets": [
            {
                "id": "primary_button",
                "name": "Primary button",
                "styles": {
                    "backgroundColor": "#d66083",
                    "border": "0px solid #FFFFFF",
                    "borderRadius": "0px",
                    "color": "#FFFFFF",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "16px",
                    "paddingBottom": "16px",
                    "paddingLeft": "16px",
                    "paddingRight": "16px",
                    "paddingTop": "16px",
                },
            },
            {
                "id": "secondary_button",
                "name": "Secondary button",
                "styles": {
                    "backgroundColor": "#FFFFFF",
                    "border": "2px solid #0e1b4d",
                    "borderRadius": "0px",
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "16px",
                    "paddingBottom": "16px",
                    "paddingLeft": "16px",
                    "paddingRight": "16px",
                    "paddingTop": "16px",
                },
            },
            {
                "id": "tertiary_button",
                "name": "Tertiary button",
                "styles": {
                    "backgroundColor": "#0e1b4d",
                    "border": "2px solid #FFFFFF",
                    "borderRadius": "0px",
                    "color": "#FFFFFF",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "16px",
                    "paddingBottom": "16px",
                    "paddingLeft": "16px",
                    "paddingRight": "16px",
                    "paddingTop": "16px",
                },
            },
        ],
        "content": {
            "backgroundColor": "#FFFFFF",
            "color": "#212121",
            "fontFamily": "Arial, sans-serif",
            "fontSize": "14px",
            "width": "800px",
        },
        "logo": {
            "height": 169,
            "id": brand.template.logo_image_id,
            "isCustom": True,
            "source": f"/image/newsletter/{brand.template.logo_image_id}",
            "width": 850,
        },
        "textPresets": [
            {
                "id": "heading_large",
                "name": "Heading Large",
                "styles": {
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "36px",
                    "lineHeight": "125%",
                },
            },
            {
                "id": "heading_medium",
                "name": "Heading Medium",
                "styles": {
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "30px",
                    "lineHeight": "125%",
                },
            },
            {
                "id": "heading_small",
                "name": "Heading Small",
                "styles": {
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "24px",
                    "lineHeight": "125%",
                },
            },
            {
                "id": "paragraph",
                "name": "Paragraph",
                "styles": {
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "14px",
                    "lineHeight": "150%",
                },
            },
            {
                "id": "footnote",
                "name": "Footnote",
                "styles": {
                    "color": "#0e1b4d",
                    "fontFamily": "Arial, sans-serif",
                    "fontSize": "12px",
                    "lineHeight": "150%",
                },
            },
        ],
    }


def build_content(
    email_content_id: str,
    feature: Banner,
    fillers: list[Banner],
    brand: BrandConfig,
) -> dict[str, Any]:
    """Return the full email-content document. Caller writes to disk and PUTs."""
    if len(fillers) != 18:
        raise ValueError(f"Expected 18 fillers, got {len(fillers)}")
    if len(brand.block_ids.images) != 19:
        raise ValueError(f"brand.block_ids.images must have 19 entries, got {len(brand.block_ids.images)}")

    banners = [feature, *fillers]
    image_blocks = [
        image_block(brand.block_ids.images[i], banner, brand) for i, banner in enumerate(banners)
    ]
    section1_blocks = [menu_block(brand), *image_blocks, mystery_block(brand)]

    return {
        "id": email_content_id,
        "generalSettings": _general_settings(brand),
        "sections": [
            _logo_section(brand),
            {
                "id": _MAIN_SECTION_ID,
                "rows": [
                    {
                        "id": _MAIN_ROW_ID,
                        "columns": [
                            {"id": _MAIN_COL_ID, "width": "800px", "blocks": section1_blocks}
                        ],
                    }
                ],
                "styleProperties": {
                    "backgroundColor": "#FFFFFF",
                    "isBackgroundPaddingsExcluded": True,
                    "padding": "32px",
                    "paddingBottom": "5px",
                    "paddingLeft": "0px",
                    "paddingRight": "0px",
                    "paddingTop": "5px",
                    "verticalAlign": "middle",
                },
                "visibility": {"isDesktopVisible": True, "isMobileVisible": True},
            },
            _footer_section(),
        ],
    }


def get_image_blocks(content: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract image blocks from section 1 (menu + banners + mystery)."""
    blocks = content["sections"][1]["rows"][0]["columns"][0]["blocks"]
    return [b for b in blocks if b.get("type") == "image"]
