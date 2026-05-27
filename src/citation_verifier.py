"""Citation Verifier — search, verify, and download cited references.

Integrates: isbnlib, habanero (CrossRef), scholarly (Google Scholar),
libgen-api-enhanced (Library Genesis).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from . import config

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CitationRecord:
    """One citation extracted from the document."""
    index: int = 0
    raw_text: str = ""
    authors: str = ""
    title: str = ""
    publisher: str = ""
    year: str = ""
    pages: str = ""
    isbn: str = ""
    doi: str = ""
    citation_type: str = ""          # book | journal | thesis | same_as_above | unknown

    # Verification results (filled by verify())
    isbn_valid: bool | None = None
    metadata_found: bool = False
    metadata_source: str = ""
    metadata: dict = field(default_factory=dict)
    download_url: str = ""
    download_path: str = ""
    download_source: str = ""
    scholar_results: list = field(default_factory=list)
    verification_notes: list = field(default_factory=list)
    overall_status: str = "pending"  # verified | partial | failed | skipped


# ---------------------------------------------------------------------------
# ISBN verification (isbnlib)
# ---------------------------------------------------------------------------

def verify_isbn(isbn: str) -> dict:
    """Validate ISBN and fetch metadata via isbnlib."""
    try:
        import isbnlib
    except ImportError:
        return {"error": "isbnlib not installed"}

    cleaned = isbnlib.canonical(isbn)
    if not cleaned:
        return {"valid": False, "error": "Invalid ISBN format"}

    is_valid = isbnlib.is_isbn10(cleaned) or isbnlib.is_isbn13(cleaned)
    result = {"isbn": cleaned, "valid": is_valid}

    if is_valid:
        try:
            meta = isbnlib.meta(cleaned)
            if meta:
                result["metadata"] = meta
                result["found"] = True
            else:
                result["found"] = False
        except Exception as e:
            result["meta_error"] = str(e)
            result["found"] = False

    return result


# ---------------------------------------------------------------------------
# CrossRef DOI / title search (habanero)
# ---------------------------------------------------------------------------

def search_crossref(title: str = "", author: str = "", doi: str = "") -> list[dict]:
    """Search CrossRef for a citation by title, author, or DOI."""
    try:
        from habanero import Crossref
    except ImportError:
        return []

    cr = Crossref(mailto="reviewer@example.com")
    results = []
    try:
        if doi:
            r = cr.works(ids=[doi])
            if r and "message" in r:
                msg = r["message"]
                results.append(_crossref_to_dict(msg))
        else:
            query = title
            if author:
                query = f"{author} {title}"
            r = cr.works(query=query, limit=3)
            for item in r.get("message", {}).get("items", []):
                results.append(_crossref_to_dict(item))
    except Exception:
        pass
    return results


def _crossref_to_dict(item: dict) -> dict:
    titles = item.get("title", [])
    authors_raw = item.get("author", [])
    authors = ", ".join(
        f'{a.get("family", "")} {a.get("given", "")}'.strip()
        for a in authors_raw
    )
    pub_date = item.get("published-print") or item.get("published-online") or {}
    year = ""
    if pub_date.get("date-parts"):
        year = str(pub_date["date-parts"][0][0])
    return {
        "title": titles[0] if titles else "",
        "authors": authors,
        "doi": item.get("DOI", ""),
        "publisher": item.get("publisher", ""),
        "year": year,
        "type": item.get("type", ""),
        "url": item.get("URL", ""),
        "source": "crossref",
    }


# ---------------------------------------------------------------------------
# Google Scholar search (scholarly)
# ---------------------------------------------------------------------------

def search_scholar(title: str, author: str = "", timeout: int = 30) -> list[dict]:
    """Search Google Scholar for a publication (with timeout)."""
    try:
        from scholarly import scholarly as sch
    except ImportError:
        return []

    import concurrent.futures

    def _do_search():
        results = []
        query = f'{author} "{title}"' if author else title
        search_results = sch.search_pubs(query)
        for _ in range(3):
            try:
                pub = next(search_results)
                bib = pub.get("bib", {})
                results.append({
                    "title": bib.get("title", ""),
                    "authors": ", ".join(bib.get("author", [])),
                    "year": bib.get("pub_year", ""),
                    "venue": bib.get("venue", ""),
                    "abstract": bib.get("abstract", "")[:200],
                    "url": pub.get("pub_url") or pub.get("eprint_url", ""),
                    "eprint_url": pub.get("eprint_url", ""),
                    "num_citations": pub.get("num_citations", 0),
                    "source": "google_scholar",
                })
            except StopIteration:
                break
        return results

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        print(f"        Google Scholar 搜索超时（{timeout}s）", flush=True)
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Library Genesis search & download (libgen-api-enhanced)
# ---------------------------------------------------------------------------

def search_libgen(title: str, author: str = "", timeout: int = 20) -> list[dict]:
    """Search Library Genesis for a book (with timeout to avoid hanging)."""
    try:
        from libgen_api_enhanced import LibgenSearch
    except ImportError:
        return []

    import concurrent.futures

    def _do_search():
        s = LibgenSearch()
        raw = s.search_title(title)
        if not raw and author:
            raw = s.search_author(author)
        return raw

    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_do_search)
            try:
                raw = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                print(f"        LibGen 搜索超时（{timeout}s），跳过", flush=True)
                return []
        for item in (raw or [])[:5]:
            results.append({
                "title": item.get("Title", ""),
                "authors": item.get("Author", ""),
                "year": item.get("Year", ""),
                "publisher": item.get("Publisher", ""),
                "pages": item.get("Pages", ""),
                "language": item.get("Language", ""),
                "extension": item.get("Extension", ""),
                "size": item.get("Size", ""),
                "md5": item.get("MD5", ""),
                "mirror_1": item.get("Mirror_1", ""),
                "mirror_2": item.get("Mirror_2", ""),
                "source": "libgen",
            })
    except Exception:
        pass
    return results


def download_from_libgen(libgen_result: dict, save_dir: Path, filename: str = "") -> str | None:
    """Try to download a book from LibGen mirror links."""
    try:
        from libgen_api_enhanced import LibgenSearch
    except ImportError:
        return None

    if not libgen_result:
        return None

    save_dir.mkdir(parents=True, exist_ok=True)
    ext = libgen_result.get("extension", "pdf")
    if not filename:
        title = libgen_result.get("title", "unknown")[:60]
        safe = re.sub(r'[<>:"/\\|?*]', '_', title).strip()
        filename = f"{safe}.{ext}"

    target = save_dir / filename
    if target.exists():
        return str(target)

    # Try to resolve download URL
    try:
        s = LibgenSearch()
        links = s.resolve_download_links(libgen_result)
        for key in ["GET", "Cloudflare", "IPFS.io"]:
            url = links.get(key, "")
            if url:
                try:
                    _download_file(url, target)
                    if target.exists() and target.stat().st_size > 1000:
                        return str(target)
                except Exception:
                    continue
    except Exception:
        pass

    return None


def _download_file(url: str, target: Path, timeout: int = 60):
    """Download a file from URL."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        target.write_bytes(resp.read())


# ---------------------------------------------------------------------------
# Unified verification pipeline
# ---------------------------------------------------------------------------

def _quick_download(rec: CitationRecord, refs_dir: Path) -> CitationRecord:
    """Phase 1: fast local verification — ISBN + LibGen download only."""
    if rec.citation_type == "same_as_above":
        rec.overall_status = "skipped"
        rec.verification_notes.append("同上书引用，跳过独立核验")
        return rec

    print(f"    [{rec.index}] 快速下载: {rec.title[:50]}...", flush=True)

    # ISBN verification
    if rec.isbn:
        isbn_result = verify_isbn(rec.isbn)
        rec.isbn_valid = isbn_result.get("valid", False)
        if isbn_result.get("found"):
            rec.metadata_found = True
            rec.metadata_source = "isbnlib"
            rec.metadata = isbn_result.get("metadata", {})
            rec.verification_notes.append(f"ISBN {rec.isbn} 验证通过")

    # LibGen search & download (fastest source for full PDFs)
    if rec.title:
        try:
            lg_results = search_libgen(title=rec.title, author=rec.authors)
            if lg_results:
                best = lg_results[0]
                rec.verification_notes.append(
                    f"LibGen 找到 {len(lg_results)} 条"
                    f"（{best.get('extension', '?')} / {best.get('size', '?')}）"
                )
                dl_path = download_from_libgen(best, refs_dir)
                if dl_path:
                    rec.download_path = dl_path
                    rec.download_source = "libgen"
                    rec.overall_status = "verified"
                    rec.verification_notes.append(f"已下载: {Path(dl_path).name}")
                    return rec
                else:
                    if best.get("mirror_1"):
                        rec.download_url = best["mirror_1"]
        except Exception as e:
            rec.verification_notes.append(f"LibGen: {e}")

    rec.overall_status = "pending"  # needs online verification
    return rec


def _online_verify(rec: CitationRecord, refs_dir: Path) -> CitationRecord:
    """Phase 2: slower online verification — CrossRef + Google Scholar."""
    print(f"    [{rec.index}] 在线核验: {rec.title[:50]}...", flush=True)

    # CrossRef
    if rec.doi or rec.title:
        print(f"        CrossRef 搜索...", flush=True)
        cr_results = search_crossref(title=rec.title, author=rec.authors, doi=rec.doi)
        if cr_results:
            best = cr_results[0]
            if not rec.metadata_found:
                rec.metadata_found = True
                rec.metadata_source = "crossref"
                rec.metadata = best
            rec.verification_notes.append(f"CrossRef 找到 {len(cr_results)} 条结果")
        else:
            rec.verification_notes.append("CrossRef 未找到匹配")

    # Google Scholar — disabled: scholarly library hangs on Windows due to
    # Google anti-bot (CAPTCHA). Most citations in this corpus are news/policy
    # sources that Scholar can't find anyway. CrossRef + LibGen are sufficient.
    # To re-enable, set env ENABLE_SCHOLAR=1.
    if rec.title and os.environ.get("ENABLE_SCHOLAR"):
        print(f"        Google Scholar 搜索...", flush=True)
        try:
            gs_results = search_scholar(title=rec.title, author=rec.authors)
            rec.scholar_results = gs_results
            if gs_results:
                rec.verification_notes.append(
                    f"Scholar 找到 {len(gs_results)} 条"
                    f"（被引 {gs_results[0].get('num_citations', '?')} 次）"
                )
                for r in gs_results:
                    if r.get("eprint_url"):
                        rec.download_url = r["eprint_url"]
                        rec.download_source = "google_scholar"
                        break
            else:
                rec.verification_notes.append("Scholar 未找到匹配")
        except Exception as e:
            rec.verification_notes.append(f"Scholar 出错: {e}")

    # Final status
    if rec.download_path:
        rec.overall_status = "verified"
    elif rec.metadata_found or rec.scholar_results:
        rec.overall_status = "partial"
    else:
        rec.overall_status = "unverifiable"
        rec.verification_notes.append("暂时无法核验（来源可能为新闻网页、内部文件等非学术出版物）")

    return rec


def verify_citation(rec: CitationRecord, refs_dir: Path) -> CitationRecord:
    """Run all verification steps on a single CitationRecord (two-phase)."""
    rec = _quick_download(rec, refs_dir)
    if rec.overall_status in ("verified", "skipped"):
        return rec
    rec = _online_verify(rec, refs_dir)
    return rec
