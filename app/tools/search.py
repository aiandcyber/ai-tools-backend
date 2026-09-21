"""Enterprise-oriented people/topic search via SearXNG.

TODO(app): Official LinkedIn/Meta/X/Google/Bing API keys required for reliable social/people search. See /home/tar_a/ai-tools/TODO.md


Designed for Tools UI and future realtime-ai integration (news, recommendations,
user-request search). Profile fields are accepted now for ranking and will be
used more deeply by an agent later.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app import config

REGION_PROFILES: dict[str, dict] = {
    "SG": {
        "label": "Singapore",
        "language": "en",
        "tlds": (".sg", ".com.sg", ".edu.sg", ".gov.sg"),
        "hosts": (
            "straitstimes.com",
            "channelnewsasia.com",
            "todayonline.com",
            "businesstimes.com.sg",
            "mothership.sg",
            "gov.sg",
            "linkedin.com",
        ),
        "tokens": ("singapore", "singapura", "sg"),
    },
    "IN": {
        "label": "India",
        "language": "en",
        "tlds": (".in", ".co.in", ".gov.in", ".ac.in", ".org.in"),
        "hosts": (
            "timesofindia.indiatimes.com",
            "hindustantimes.com",
            "indianexpress.com",
            "thehindu.com",
            "ndtv.com",
            "linkedin.com",
        ),
        "tokens": ("india", "indian", "bharat"),
    },
    "MY": {
        "label": "Malaysia",
        "language": "en",
        "tlds": (".my", ".com.my", ".gov.my", ".edu.my"),
        "hosts": ("thestar.com.my", "malaymail.com", "nst.com.my", "linkedin.com"),
        "tokens": ("malaysia", "malaysian", "kuala lumpur"),
    },
    "US": {
        "label": "United States",
        "language": "en",
        "tlds": (".us", ".gov", ".edu", ".mil"),
        "hosts": ("nytimes.com", "washingtonpost.com", "cnn.com", "linkedin.com"),
        "tokens": ("united states", "usa", "american"),
    },
    "GB": {
        "label": "United Kingdom",
        "language": "en",
        "tlds": (".uk", ".co.uk", ".gov.uk", ".ac.uk", ".org.uk"),
        "hosts": ("bbc.co.uk", "theguardian.com", "telegraph.co.uk", "linkedin.com"),
        "tokens": ("united kingdom", "britain", "british", "england", "london"),
    },
    "AU": {
        "label": "Australia",
        "language": "en",
        "tlds": (".au", ".com.au", ".gov.au", ".edu.au"),
        "hosts": ("abc.net.au", "smh.com.au", "theage.com.au", "linkedin.com"),
        "tokens": ("australia", "australian", "sydney", "melbourne"),
    },
    "GLOBAL": {
        "label": "Global",
        "language": "en",
        "tlds": (),
        "hosts": (),
        "tokens": (),
    },
}

PERSON_CATEGORIES = ("general", "social media", "news", "science")
TOPIC_CATEGORIES = ("general", "news", "social media", "science", "it")

CATEGORY_WEIGHT = {
    "news": 8.0,
    "social media": 7.0,
    "general": 5.0,
    "science": 4.0,
    "it": 3.0,
}

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def web_search(
    query: str,
    mode: str = "auto",
    region: str = "",
    language: str = "en",
    interests: str = "",
    industry: str = "",
    location: str = "",
    limit: int = 20,
) -> dict:
    text = (query or "").strip()
    if not text:
        raise ValueError("Enter a person name or topic")

    resolved_mode = _resolve_mode(text, mode)
    region_code = _resolve_region(region)
    region_info = REGION_PROFILES[region_code]
    lang = (language or region_info["language"] or "en").strip() or "en"
    max_results = max(1, min(int(limit or 20), 40))

    interest_list = _split_csv(interests)
    industry_text = (industry or "").strip()
    location_text = (location or "").strip() or region_info["label"]

    categories = PERSON_CATEGORIES if resolved_mode == "person" else TOPIC_CATEGORIES
    query_plan = _build_queries(
        text,
        resolved_mode,
        region_info,
        location_text,
        interest_list,
        industry_text,
    )

    raw_hits: list[dict] = []
    unresponsive: list[dict] = []
    queried: list[dict] = []

    jobs: list[tuple[str, str, str]] = []
    for category in categories:
        for q in query_plan.get(category, query_plan["default"]):
            jobs.append((q, category, lang))

    with ThreadPoolExecutor(max_workers=min(8, len(jobs) or 1)) as pool:
        futures = {
            pool.submit(_fetch_searx, q, category, lang): (q, category)
            for q, category, lang in jobs
        }
        for future in as_completed(futures):
            q, category = futures[future]
            try:
                payload = future.result()
            except Exception as exc:  # noqa: BLE001 - collect per-engine failures
                unresponsive.append({"query": q, "category": category, "error": str(exc)[:200]})
                continue
            queried.append({"query": q, "category": category, "count": len(payload.get("results") or [])})
            for item in payload.get("results") or []:
                hit = _normalize_hit(item, category, q)
                if hit:
                    raw_hits.append(hit)
            for engine, reason in payload.get("unresponsive_engines") or []:
                unresponsive.append(
                    {"engine": engine, "reason": reason, "category": category, "query": q}
                )

    merged = _merge_hits(raw_hits)
    ranked = _rank_hits(
        merged,
        text=text,
        mode=resolved_mode,
        region_code=region_code,
        region_info=region_info,
        interests=interest_list,
        industry=industry_text,
        location=location_text,
    )
    results = ranked[:max_results]

    meta = {
        "mode": resolved_mode,
        "region": region_code,
        "region_label": region_info["label"],
        "language": lang,
        "categories": list(categories),
        "queries": queried,
        "unresponsive": _dedupe_unresponsive(unresponsive)[:30],
        "total_raw": len(raw_hits),
        "total_unique": len(merged),
        "profile": {
            "interests": interest_list,
            "industry": industry_text,
            "location": location_text,
        },
        "for": ["tools-ui", "realtime-ai-news", "realtime-ai-recommendations", "realtime-ai-search"],
    }

    if not results:
        engines = ", ".join(
            sorted(
                {
                    f"{item.get('engine')}: {item.get('reason')}"
                    for item in meta["unresponsive"]
                    if item.get("engine")
                }
            )
        )
        detail = f" Engines unavailable: {engines}." if engines else ""
        return {
            "message": f"No results for “{text}” in {region_info['label']}.{detail}".strip(),
            "results": [],
            "meta": meta,
        }

    return {
        "message": f"Found {len(results)} {resolved_mode} results (region: {region_info['label']})",
        "results": results,
        "meta": meta,
    }


def _resolve_mode(query: str, mode: str) -> str:
    value = (mode or "auto").strip().lower()
    if value in {"person", "people", "name"}:
        return "person"
    if value in {"topic", "news", "subject"}:
        return "topic"
    # auto: short multi-word without stopwords → person; else topic
    words = [w for w in re.split(r"\s+", query.strip()) if w]
    if 1 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][\w'.-]*", w) for w in words):
        stop = {"the", "and", "for", "with", "about", "news", "ai", "how", "what", "why"}
        if not any(w.lower() in stop for w in words):
            return "person"
    return "topic"


def _resolve_region(region: str) -> str:
    code = (region or config.SEARCH_DEFAULT_REGION or "SG").strip().upper()
    if code in {"", "ALL", "WORLD", "WW"}:
        code = "GLOBAL"
    return code if code in REGION_PROFILES else "GLOBAL"


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _build_queries(
    text: str,
    mode: str,
    region_info: dict,
    location: str,
    interests: list[str],
    industry: str,
) -> dict[str, list[str]]:
    region_label = region_info["label"]
    quoted = f'"{text}"' if " " in text else text

    if mode == "person":
        base = [text, quoted, f"{text} profile", f"{text} biography"]
        if region_label and region_label != "Global":
            base.append(f"{text} {region_label}")
        if location and location.lower() not in {region_label.lower(), "global"}:
            base.append(f"{text} {location}")
        if industry:
            base.append(f"{text} {industry}")
        social = [text, f"{text} linkedin", f"{text} twitter", f"{text} github"]
        news = [text, f"{text} news"]
        if region_label != "Global":
            news.append(f"{text} {region_label} news")
        science = [text, f"{text} researcher", f"{text} scholar"]
        return {
            "default": _unique(base),
            "general": _unique(base),
            "social media": _unique(social),
            "news": _unique(news),
            "science": _unique(science),
        }

    base = [text]
    if region_label != "Global":
        base.append(f"{text} {region_label}")
    if interests:
        base.append(f"{text} {' '.join(interests[:3])}")
    if industry:
        base.append(f"{text} {industry}")
    news = [text, f"{text} news", f"{text} latest"]
    if region_label != "Global":
        news.append(f"{text} {region_label} news")
    social = [text, f"{text} discussion"]
    science = [text, f"{text} research"]
    it = [text, f"{text} documentation", f"{text} github"]
    return {
        "default": _unique(base),
        "general": _unique(base),
        "news": _unique(news),
        "social media": _unique(social),
        "science": _unique(science),
        "it": _unique(it),
    }


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out[:4]


def _fetch_searx(query: str, category: str, language: str) -> dict:
    response = httpx.get(
        f"{config.SEARXNG_URL}/search",
        params={
            "q": query,
            "format": "json",
            "categories": category,
            "language": language,
            "pageno": 1,
        },
        headers={"Accept": "application/json"},
        timeout=35.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"SearXNG {response.status_code}: {response.text[:300]}")
    return response.json()


def _normalize_hit(item: dict, category: str, query_used: str) -> dict | None:
    url = (item.get("url") or "").strip()
    if not url:
        return None
    title = (item.get("title") or "(no title)").strip()
    snippet = (item.get("content") or item.get("snippet") or "").replace("\n", " ").strip()
    engines = item.get("engines") or []
    if isinstance(engines, str):
        engines = [engines]
    try:
        host = urlparse(url).hostname or ""
    except Exception:  # noqa: BLE001
        host = ""
    return {
        "title": title,
        "url": url,
        "canonical_url": _canonical_url(url),
        "snippet": snippet,
        "category": category,
        "engine": (item.get("engine") or (engines[0] if engines else "") or ""),
        "engines": list(engines),
        "score": float(item.get("score") or 0),
        "published": item.get("publishedDate") or item.get("pubdate") or "",
        "thumbnail": item.get("thumbnail") or item.get("img_src") or "",
        "host": host.lower().removeprefix("www."),
        "query_used": query_used,
    }


def _canonical_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k.lower() not in _TRACKING_PARAMS
        ]
        path = parsed.path.rstrip("/") or "/"
        return urlunparse(
            (
                parsed.scheme.lower(),
                (parsed.netloc or "").lower().removeprefix("www."),
                path,
                "",
                urlencode(query),
                "",
            )
        )
    except Exception:  # noqa: BLE001
        return url.strip().lower()


def _merge_hits(hits: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    for hit in hits:
        key = hit["canonical_url"] or hit["url"]
        existing = by_url.get(key)
        if not existing:
            by_url[key] = {
                **hit,
                "categories": [hit["category"]],
                "engines": list(dict.fromkeys(hit.get("engines") or ([hit["engine"]] if hit.get("engine") else []))),
                "queries_used": [hit["query_used"]],
            }
            continue
        existing["score"] = max(existing["score"], hit["score"])
        if hit["category"] not in existing["categories"]:
            existing["categories"].append(hit["category"])
        for engine in hit.get("engines") or ([hit["engine"]] if hit.get("engine") else []):
            if engine and engine not in existing["engines"]:
                existing["engines"].append(engine)
        if hit["query_used"] not in existing["queries_used"]:
            existing["queries_used"].append(hit["query_used"])
        if len(hit["snippet"]) > len(existing["snippet"]):
            existing["snippet"] = hit["snippet"]
        if not existing.get("thumbnail") and hit.get("thumbnail"):
            existing["thumbnail"] = hit["thumbnail"]
        if not existing.get("published") and hit.get("published"):
            existing["published"] = hit["published"]
    return list(by_url.values())


def _rank_hits(
    hits: list[dict],
    *,
    text: str,
    mode: str,
    region_code: str,
    region_info: dict,
    interests: list[str],
    industry: str,
    location: str,
) -> list[dict]:
    query_tokens = {tok.lower() for tok in re.findall(r"[A-Za-z0-9']+", text) if len(tok) > 1}
    interest_tokens = {tok.lower() for item in interests for tok in re.findall(r"[A-Za-z0-9']+", item)}
    industry_tokens = {tok.lower() for tok in re.findall(r"[A-Za-z0-9']+", industry) if len(tok) > 1}
    location_tokens = {tok.lower() for tok in re.findall(r"[A-Za-z0-9']+", location) if len(tok) > 1}
    region_tokens = {tok.lower() for tok in region_info.get("tokens", ())}
    tlds = tuple(region_info.get("tlds") or ())
    preferred_hosts = tuple(region_info.get("hosts") or ())

    ranked: list[dict] = []
    for hit in hits:
        blob = f"{hit.get('title', '')} {hit.get('snippet', '')} {hit.get('host', '')}".lower()
        host = hit.get("host") or ""
        score = float(hit.get("score") or 0) * 10.0

        for category in hit.get("categories") or [hit.get("category")]:
            score += CATEGORY_WEIGHT.get(category or "", 1.0)

        regional = 0.0
        if any(host.endswith(tld) for tld in tlds):
            regional += 28.0
        if any(host == pref or host.endswith("." + pref) for pref in preferred_hosts):
            regional += 18.0
        if any(token in blob for token in region_tokens | location_tokens):
            regional += 12.0
        score += regional

        title = (hit.get("title") or "").lower()
        if mode == "person" and text.lower() in title:
            score += 22.0
        overlap = len(query_tokens & set(re.findall(r"[A-Za-z0-9']+", blob)))
        score += min(overlap * 3.0, 18.0)

        if interest_tokens & set(re.findall(r"[A-Za-z0-9']+", blob)):
            score += 14.0
        if industry_tokens & set(re.findall(r"[A-Za-z0-9']+", blob)):
            score += 10.0

        if mode == "person" and any(
            marker in host
            for marker in ("linkedin.com", "github.com", "x.com", "twitter.com", "facebook.com", "instagram.com")
        ):
            score += 10.0
        if mode == "topic" and "news" in (hit.get("categories") or []):
            score += 6.0

        reasons: list[str] = []
        if regional >= 18:
            reasons.append("regional")
        if mode == "person" and text.lower() in title:
            reasons.append("name-match")
        if interest_tokens & set(re.findall(r"[A-Za-z0-9']+", blob)):
            reasons.append("profile-interest")
        if "news" in (hit.get("categories") or []):
            reasons.append("news")
        if "social media" in (hit.get("categories") or []):
            reasons.append("social")

        ranked.append(
            {
                "title": hit["title"],
                "url": hit["url"],
                "snippet": hit["snippet"],
                "category": (hit.get("categories") or [hit.get("category") or "general"])[0],
                "categories": hit.get("categories") or [hit.get("category") or "general"],
                "engine": hit.get("engine") or "",
                "engines": hit.get("engines") or [],
                "published": hit.get("published") or "",
                "thumbnail": hit.get("thumbnail") or "",
                "host": host,
                "region": region_code,
                "regional_score": round(regional, 2),
                "relevance_score": round(score, 2),
                "reasons": reasons,
            }
        )

    ranked.sort(key=lambda item: (-item["relevance_score"], item["title"].lower()))
    return ranked


def _dedupe_unresponsive(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = f"{item.get('engine')}|{item.get('reason')}|{item.get('category')}|{item.get('error', '')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
