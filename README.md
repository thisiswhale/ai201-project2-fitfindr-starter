# FitFindr

FitFindr is a secondhand shopping agent that takes a natural language query, finds matching thrift listings, suggests outfit combinations using your existing wardrobe, and generates a shareable social media caption — all in one planning loop.

## Setup

```bash
pip install -r requirements.txt
```

Set your Groq API key in a `.env` file (get a free key at [console.groq.com](https://console.groq.com)):
```
GROQ_API_KEY=your_key_here
```

Run the Gradio UI:
```bash
python app.py
```

Or call the agent directly:
```python
from agent import run_agent
from utils.data_loader import get_example_wardrobe

session = run_agent("vintage graphic tee under $30", wardrobe=get_example_wardrobe())
print(session["fit_card"])   # social caption
print(session["error"])      # None on success
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Searches the mock listings dataset for items matching a keyword description, with optional filters for size and price.

**Inputs:**
- `description` (str) — keywords describing the item (e.g. `"vintage graphic tee"`); used to score listings by keyword overlap across title, description, category, and style tags
- `size` (str | None) — size to filter by; matching is case-insensitive and substring-based so `"M"` matches `"S/M"`; pass `None` to skip
- `max_price` (float | None) — maximum price in dollars, inclusive; pass `None` to skip

**Output:** `list[dict]` — matching listing dicts sorted by relevance score, highest first. Returns `[]` if nothing matches; never raises. Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Uses an LLM (Groq `llama-3.3-70b-versatile`) to suggest 1-2 outfit combinations pairing the new item with pieces the user already owns. Falls back to general styling advice if the wardrobe is empty.

**Inputs:**
- `new_item` (dict) — a listing dict returned by `search_listings`
- `wardrobe` (dict) — a dict with an `"items"` key containing a list of wardrobe item dicts; the list may be empty

**Output:** `str` — a non-empty outfit suggestion string. If wardrobe has items, references them by name. If wardrobe is empty, returns general styling ideas instead. Never returns an empty string or raises.

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Uses an LLM (higher temperature for variety) to generate a 2-4 sentence Instagram/TikTok-style caption for the outfit. Casual and authentic in tone — not a product description.

**Inputs:**
- `outfit` (str) — the outfit suggestion string from `suggest_outfit`
- `new_item` (dict) — the listing dict for the thrifted item; used for title, price, and platform

**Output:** `str` — a 2-4 sentence social caption mentioning the item name, price, and platform each exactly once. If `outfit` is empty or whitespace-only, returns `"Could not generate a fit card: outfit description is missing."` without raising.

---

## Planning Loop

`run_agent()` in `agent.py` runs a linear planning loop with one conditional branch:

1. **Initialize** — `_new_session(query, wardrobe)` creates the session dict with all fields (`parsed`, `search_results`, `selected_item`, `outfit_suggestion`, `fit_card`, `error`) set to empty defaults.

2. **Parse** — Regex extracts `description`, `size`, and `max_price` from the natural language query. Patterns like `"under $30"` capture price; `"size M"` captures size. The remaining text becomes the description. Result stored in `session["parsed"]`.

3. **Search — with branch** — `search_listings()` is called with the parsed parameters. If the returned list is empty, `session["error"]` is set to a message naming the description, size, and price the user tried, and the function returns immediately. `suggest_outfit` and `create_fit_card` are never called. If results exist, the top result is assigned to `session["selected_item"]` and the loop continues.

4. **Suggest outfit** — `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])` is called unconditionally. The tool handles the empty-wardrobe case internally; no branch in the loop.

5. **Create fit card** — `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])` is called unconditionally. The tool handles a missing outfit string internally.

6. **Return** — The completed session dict is returned. Callers check `session["error"]` first; `None` means success.

---

## State Management

All state lives in a single session dict created by `_new_session()` at the start of each `run_agent()` call. No global variables; no state shared across calls.

| Field | Set when | Used by |
|---|---|---|
| `query` | Step 1 | reference only |
| `parsed` | Step 2 (regex) | Step 3 (`search_listings`) |
| `search_results` | Step 3 | Step 4 (item selection) |
| `selected_item` | Step 4 | Steps 5 and 6 |
| `wardrobe` | Step 1 (passed in) | Step 5 (`suggest_outfit`) |
| `outfit_suggestion` | Step 5 | Step 6 (`create_fit_card`) |
| `fit_card` | Step 6 | returned to caller |
| `error` | Step 3 (on failure) | caller checks first |

Each tool receives its inputs directly from session fields — no re-parsing, no re-fetching, no hardcoded values between steps. Verified in testing by spy-wrapping both LLM tools and confirming the exact same Python objects flowed from the session into each tool call.

---

## Error Handling

### `search_listings` — no results

If the query, size, and price filters together match zero listings, the tool returns `[]`. The planning loop detects this and sets `session["error"]` with an interpolated message, then returns early without calling the remaining tools.

**Example from testing:**
```
query:  "designer ballgown size XXS under $5"
result: session["error"] = "No listings found for 'designer ballgown' in size XXS under $5.
        Try a broader description, a different size, or raise your price limit."
        session["fit_card"]          -> None
        session["outfit_suggestion"] -> None
        suggest_outfit called        -> False (confirmed via spy wrapper)
```

### `suggest_outfit` — empty wardrobe

If `wardrobe["items"]` is empty (or the `"items"` key is missing entirely), the tool does not exit early. It calls the LLM with a general-styling prompt instead of a wardrobe-matched one, and returns a non-empty string so the loop continues to `create_fit_card`.

**Example from testing:**
```
wardrobe: {"items": []}
result:   non-empty general styling string returned, no crash,
          LLM called once, loop continued to create_fit_card
```

### `create_fit_card` — missing outfit string

If `outfit` is empty or whitespace-only, the tool returns a descriptive error string without raising. The LLM is never called.

**Example from testing:**
```
create_fit_card(outfit="", new_item=SAMPLE_ITEM)
-> "Could not generate a fit card: outfit description is missing."
   LLM call count: 0 (confirmed via mock assertion in test suite)
```

---

## Spec Reflection

**One way the spec helped:** Writing the planning loop section of `planning.md` before touching `agent.py` forced a decision about query parsing upfront. The spec required stating whether to use regex, string splitting, or an LLM call — choosing regex early meant the implementation had no ambiguity about Step 2 and no wasted API calls for something simple rules could handle reliably.

**One way implementation diverged from the spec:** The error handling table in `planning.md` originally described the `create_fit_card` failure message as ending with `"outfit description is empty."` but the implementation used `"outfit description is missing."` The test suite caught the mismatch when an exact-string assertion failed. The spec was updated to match the implementation rather than the other way around, since the code was already verified and the distinction was cosmetic.

---

## AI Usage

**Instance 1 — implementing `search_listings`:**
I gave Claude the Tool 1 block from `planning.md` (parameter names and types, the full listing field list, and the empty-results failure mode) plus the `load_listings()` docstring from `data_loader.py`. I asked it to implement the function using keyword-overlap scoring across `title`, `description`, `category`, and `style_tags`, with price and size filtering applied first. Before running the output, I reviewed it and confirmed the size match used a substring check (`size.lower() in listing["size"].lower()`) — required for `"M"` to match `"S/M"` — and that `None` parameters correctly skipped their filters rather than crashing. I then tested with three queries (matching, impossible, and no-filter) before accepting it.

**Instance 2 — implementing `run_agent`:**
I gave Claude the Planning Loop section, the State Management section, and the Architecture diagram from `planning.md`. The generated code called all three tools unconditionally in sequence, missing the early-return branch after `search_listings`. I revised it to add the `if not session["search_results"]:` guard that sets `session["error"]` and returns before reaching `suggest_outfit`. The fix was verified with a spy wrapper confirming `suggest_outfit` was not called when `search_listings` returned `[]`.
