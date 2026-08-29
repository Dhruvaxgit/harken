# Changes

Local fork changes on top of upstream [VladUZH/harken](https://github.com/VladUZH/harken), tracked here since they aren't upstream commits.

---

## 2026-08-28 — Fix X/Twitter source re-billing the same tweet on every poll

**Files:** `src/harken/sources/x.py`, `tests/test_sources.py`

**What was wrong:**
`XSource.fetch_page()` passes a `since` timestamp to X's recent-search endpoint as
`start_time`. Under normal operation (no leftover pagination — the common case
for a low-volume keyword), `store.py` resets the saved `incremental_since` to
`None` after each scan, so the next scan's `since` falls back to `newest_at` —
the exact timestamp of the last tweet already seen. `_recent_start()` passed
that timestamp to X verbatim, with no offset.

X's `start_time` parameter is inclusive, so the already-seen "newest" tweet
was being returned — and re-billed, under X's pay-per-post-read pricing — on
**every subsequent poll**, not just once. At a 10-minute poll interval this
added roughly 144 redundant billed reads/day (~4,300/month, ~$21.60/month at
$0.005/post) on top of genuine new-mention volume, regardless of how much
real activity the tracked keyword actually had.

**Fix:**
`_recent_start()` now nudges the boundary forward by one second
(`boundary + timedelta(seconds=1)`) before formatting it as `start_time`, so
the already-seen tweet is excluded from the next scan instead of being
re-fetched. One-line change in `src/harken/sources/x.py`.

Updated the corresponding assertion in `tests/test_sources.py`
(`test_x_fetch_page_...`) to expect the +1s boundary instead of the raw
`since` value.

**Verified:** `pytest tests/test_sources.py -q` — 17 passed.

**Impact:** brings estimated X-source cost at a 10-min poll interval for a
1–20 mentions/day keyword down from ~$21.75–$24.60/month to ~$0.15–$3.00/month
(genuine mention volume only, plus a small one-time initial-scan cost).
