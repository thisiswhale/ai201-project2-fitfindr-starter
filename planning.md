# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items matching a keyword description, with optional filters for size and price ceiling. It scores each listing by keyword overlap and returns only results with at least one match, sorted best-first.

**Input parameters:**
- `description` (str): Keywords describing the item the user wants (e.g., `"vintage graphic tee"`).
- `size` (str | None): Size string to filter by; matching is case-insensitive so `"M"` also matches `"S/M"`; pass `None` to skip size filtering.
- `max_price` (float | None): Maximum price (inclusive) in dollars; pass `None` to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance (best match first); returns an empty list if nothing matches — does not raise an exception. Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str: one of `tops`, `bottoms`, `outerwear`, `shoes`, `accessories`), `style_tags` (list[str]), `size` (str), `condition` (str: `excellent`, `good`, or `fair`), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str: one of `depop`, `thredUp`, `poshmark`).

**What happens if it fails or returns nothing:**
The agent skips Steps 2 and 3, responds to the user with "No listings matched your search," and asks them to broaden their criteria (e.g., raise the price limit or simplify the description).

---

### Tool 2: suggest_outfit

**What it does:**
Uses an LLM to suggest 1–2 complete outfit combinations that pair the new thrifted item with pieces the user already owns. If the wardrobe is empty, it falls back to general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict for the item the user is considering buying (same fields as a `search_listings` result).
- `wardrobe` (dict): A dict with an `items` key containing a list of wardrobe item dicts; the list may be empty.

**What it returns:**
A non-empty string with 1–2 outfit suggestions; if the wardrobe has items, suggestions reference specific named pieces from it; if the wardrobe is empty, the string contains general styling ideas (what categories of clothing pair well, what aesthetic it suits).

**What happens if it fails or returns nothing:**
If the wardrobe is empty the agent still calls the LLM with a general-styling prompt rather than skipping the tool; it never returns an empty string or raises an exception.

---

### Tool 3: create_fit_card

**What it does:**
Uses an LLM (with higher temperature for variety) to generate a short, shareable outfit caption in the style of a real OOTD social media post. It naturally weaves in the item name, price, and platform without sounding like a product description.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by `suggest_outfit()`.
- `new_item` (dict): The listing dict for the thrifted item (same fields as a `search_listings` result); used for title, price, and platform.

**What it returns:**
A 2–4 sentence string suitable as an Instagram or TikTok caption; casual and authentic in tone, mentioning the item name, price, and platform each exactly once, and capturing the outfit vibe in specific terms.

**What happens if it fails or returns nothing:**
If `outfit` is empty or whitespace-only, the tool returns a descriptive error message string (e.g., `"Could not generate a fit card: outfit description is missing."`) — it does not raise an exception.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**

1. **Initialize.** Call `_new_session(query, wardrobe)` to create the session dict with all fields set to their empty defaults.

2. **Parse the query.** Extract `description` (str), `size` (str or None), and `max_price` (float or None) from the user's natural language query using an LLM call or regex. Store the result in `session["parsed"]`.

3. **Call `search_listings`.** Pass `session["parsed"]["description"]`, `session["parsed"]["size"]`, and `session["parsed"]["max_price"]` as arguments. Store the returned list in `session["search_results"]`.
   - If `session["search_results"]` is empty → set `session["error"] = "No listings matched your search. Try a simpler description or raise your price limit."` and return the session immediately. Do not proceed.
   - If `session["search_results"]` is not empty → set `session["selected_item"] = session["search_results"][0]` and continue.

4. **Call `suggest_outfit`.** Pass `new_item=session["selected_item"]` and `wardrobe=session["wardrobe"]`. Store the returned string in `session["outfit_suggestion"]`. No early exit here — the tool handles an empty wardrobe internally by returning general styling advice instead.

5. **Call `create_fit_card`.** Pass `outfit=session["outfit_suggestion"]` and `new_item=session["selected_item"]`. Store the returned string in `session["fit_card"]`. No early exit — the tool handles an empty outfit string internally by returning an error message string.

6. **Done.** Return the session. `session["error"]` is still `None`, signaling success; callers check this field first.

---

## State Management

**How does information from one tool get passed to the next?**
<!-- Describe how your agent stores and accesses state within a session. What data is tracked? How is it passed between tool calls? -->

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to `"No listings found for '[description]' in size [size] under $[max_price]. Try a broader description, a different size, or raise your price limit."` Return the session immediately — do not call `suggest_outfit` or `create_fit_card`. |
| suggest_outfit | Wardrobe is empty | Do not exit early. Call the LLM with a general-styling prompt: `"The user has no saved wardrobe items. Suggest 1–2 outfit combinations that would pair well with this item in general, including what categories of clothing and shoe styles work best."` Return the LLM's response string as `outfit_suggestion` and continue to `create_fit_card`. |
| create_fit_card | Outfit input is missing or incomplete | Return the string `"Could not generate a fit card: outfit description is empty."` without raising an exception. Store this string in `session["fit_card"]` so the caller always has a non-None value to display. |

---

## Architecture

```
User: natural language query + wardrobe
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Planning Loop                               │
│                        run_agent()                                  │
│                                                                     │
│  Step 1: _new_session(query, wardrobe)                              │
│          └─► Session: { query, parsed={}, search_results=[],        │
│                         selected_item=None, wardrobe,               │
│                         outfit_suggestion=None, fit_card=None,      │
│                         error=None }                                │
│                                                                     │
│  Step 2: Parse query → description (str), size (str|None),         │
│          max_price (float|None)                                     │
│          └─► Session: parsed = { description, size, max_price }    │
│                                          │                          │
│                                          ▼                          │
│  Step 3: search_listings(description, size, max_price) ────────────┼──► [Tool 1]
│          │                                                          │
│          ├─ results = []                                            │
│          │       └─► Session: error = "No listings matched..."     │
│          │                        │                                 │
│          │                        ▼                                 │
│          │               [ERROR EXIT] return session ◄─────────────┘
│          │
│          └─ results = [item, ...]
│                  └─► Session: search_results = results
│                               selected_item  = results[0]
│                                          │
│                                          ▼
│  Step 4: suggest_outfit(selected_item, wardrobe) ──────────────────────► [Tool 2]
│          │                                                                    │
│          ├─ wardrobe["items"] is empty                                        │
│          │       └─► LLM prompt: general styling advice (no early exit)       │
│          │                                                                    │
│          └─ wardrobe["items"] has items                                       │
│                  └─► LLM prompt: wardrobe-matched outfit combinations ◄───────┘
│                                          │
│                               Session: outfit_suggestion = "..."
│                                          │
│                                          ▼
│  Step 5: create_fit_card(outfit_suggestion, selected_item) ────────────► [Tool 3]
│          │                                                                    │
│          ├─ outfit_suggestion is empty/whitespace                             │
│          │       └─► returns error string (no exception raised)  ◄───────────┘
│          │
│          └─ outfit_suggestion is valid
│                  └─► LLM prompt: social caption (casual tone, higher temp)
│                                          │
│                               Session: fit_card = "..."
│                                          │
└──────────────────────────────────────────┼──────────────────────────────────────┘
                                           ▼
                              Return session
                              (check session["error"] first;
                               None = success, str = early exit)
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**

**`search_listings`**
I'll give Claude the Tool 1 block from planning.md (what it does, all three input parameters with types, the full listing dict field list, and the empty-results failure mode) plus the `load_listings()` docstring from `utils/data_loader.py`. I'll ask it to implement `search_listings()` in `tools.py` using `load_listings()`, filtering by `max_price` and `size` first, then scoring by keyword overlap with `description`, dropping zero-score results, and returning the list sorted highest-score first.

Before running it, I'll read the generated code and check that: (1) it filters by all three parameters, (2) size matching is case-insensitive, (3) it returns `[]` rather than raising when nothing matches. Then I'll test it with three queries — one that returns multiple results (`"graphic tee"`, size `"M"`, max `$30`), one that returns nothing (`"ballgown"`, size `"XXS"`, max `$5`), and one with no size or price filter to confirm `None` parameters are skipped.

**`suggest_outfit`**
I'll give Claude the Tool 2 block from planning.md (both parameters with their dict shapes, the two wardrobe branches, and the return value description) and ask it to implement `suggest_outfit()` in `tools.py` using the Groq client from `_get_groq_client()`. I expect it to produce: a check for `wardrobe["items"]` being empty, two distinct LLM prompts (one for general styling, one that lists wardrobe pieces by name), and a `return` of the LLM response string.

Before running it, I'll check that the code never returns an empty string and that both prompt branches are present. I'll test it twice: once with `get_example_wardrobe()` (should reference specific wardrobe items by name) and once with `get_empty_wardrobe()` (should still return a non-empty general styling suggestion).

**`create_fit_card`**
I'll give Claude the Tool 3 block from planning.md (both parameters with types, the caption style guidelines, and the empty-outfit guard behavior) and ask it to implement `create_fit_card()` in `tools.py` using the Groq client with a higher temperature setting. I expect it to produce: a whitespace guard that returns an error string without raising, an LLM prompt that supplies item name, price, platform, and outfit suggestion, and a `return` of the 2–4 sentence caption.

Before running it, I'll check that the guard condition triggers on `""` and `"   "` and that the prompt instructs the LLM to mention name, price, and platform each exactly once. I'll test it with the band-tee example from the walkthrough and verify the output reads like a real OOTD caption, not a product description. I'll run it twice to confirm the caption varies between calls (higher temperature working).

---

**Milestone 4 — Planning loop and state management:**

I'll give Claude the Planning Loop section, the State Management section, and the Architecture diagram from planning.md, and ask it to implement `run_agent()` in `agent.py`. I expect it to produce: a call to `_new_session()`, a query-parsing step that populates `session["parsed"]`, the `search_listings` call with the early-return branch that sets `session["error"]` and returns when results are empty, the `selected_item = results[0]` assignment, the `suggest_outfit` call storing into `session["outfit_suggestion"]`, and the `create_fit_card` call storing into `session["fit_card"]`.

Before running it, I'll read the code and verify every session field from `_new_session()` is written to at the correct step and that the early-return branch does not call `suggest_outfit` or `create_fit_card`. I'll verify correctness with the two CLI test cases already in `agent.py`: the happy path (`"vintage graphic tee under $30"` with `get_example_wardrobe()`) must return a non-None `fit_card` and `error=None`; the no-results path (`"designer ballgown size XXS under $5"`) must return a non-None `error` and `fit_card=None`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The user's query triggers the agent to initialize a new session and call `search_listings("vintage graphic tee", size="M", max_price=30.0)`, returning 3 listings sorted by relevance; the top result ("Faded Band Tee — $22, Depop, Good condition") is stored in `session["selected_item"]`. If no listings match, the agent skips Steps 2 and 3, tells the user no results were found, and asks them to broaden their search (e.g., raise the price limit or use a simpler description).

**Step 2:**
With `session["selected_item"]` populated, the planning loop triggers `suggest_outfit(new_item=session["selected_item"], wardrobe=session["wardrobe"])`, which returns "Pair this with your wide-leg jeans and chunky sneakers for a classic 90s grunge look" stored in `session["outfit_suggestion"]`. If the wardrobe is empty, the agent skips personalization and generates a generic styling tip for the item instead of a wardrobe-matched suggestion.

**Step 3:**
With both `session["selected_item"]` and `session["outfit_suggestion"]` set, the planning loop triggers `create_fit_card(outfit=session["outfit_suggestion"], new_item=session["selected_item"])` and stores the result in `session["fit_card"]`, marking the session complete. If outfit data is missing or incomplete, the agent falls back to returning the raw outfit suggestion as plain text rather than a styled card.

**Final output to user:**
The user sees the finished fit card: "thrifted this faded band tee off depop for $22 and honestly it was made for my wide-legs 🖤 full look in my stories."