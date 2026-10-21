# Test execution log

Environment for all runs: Windows 10, Firefox 158.0 (64-bit), local app.

## M01–M05 run

**Date:** between 17 and 20 October 2026
**App:** offline demo on port 8010, empty pantry at the start  

| Case | Result | Notes |
| --- | --- | --- |
| [M01](test-cases.md#m01--free-form-input-survives-reload-p1p3) Free-form input survives reload | Pass | Same IDs before and after reload in UI, API and SQL |
| [M02](test-cases.md#m02--duplicates-alias-and-different-foods-p2p3) Duplicates, alias, different foods | Pass | Four items in total; original spelling kept |
| [M03](test-cases.md#m03--name-length-limit-and-whole-batch-rejection-p1) Name length limit | Pass | 99 and 100 accepted; batch with a 101-character name fully rejected |
| [M04](test-cases.md#m04--preference-exclusion-and-old-results-r1r6) Preference, exclusion, old results | Pass | Warning shown; old result cleared; excluded apple rejected; eggs conflict returned 422 |
| [M05](test-cases.md#m05--long-name-layout-keyboard-and-delete-p4-u1) Long name, keyboard, delete | Pass | Also my retest of [BUG-001](../bugs/BUG-001-layout.md) |

**What I'd do better next time:** I didn't save the commit hash, the exact date or screenshots for this run. For future runs I'll record the commit, date and screenshots, as in the [bug template](../../.github/ISSUE_TEMPLATE/bug_report.md).

## Earlier checks

These were my first tests, done in the development app (ports 5173/8000) between 9 and 12 October 2026.

### Story 1 – adding ingredients

| ID | Test | Input | Expected | Result |
| --- | --- | --- | --- | --- |
| TC-S1-001 | Bulk entry, mixed separators | `chicken, rice` / `spinach` / blank line / `eggs` | 4 items, blank ignored, HTTP 201, input cleared, items still there after reload | Pass |
| TC-S1-002 | Custom food | `leftover roast chicken` | Saved even though it isn't a known ingredient (`ingredient_id` null) | Pass |
| TC-S1-003 | Duplicates and case | `eggs, EGGS` and similar | One item; duplicates counted as skipped | Pass |
| TC-S1-004 | Alias | `greek yoghurt` | Saved as Greek yogurt, original spelling kept | Pass |
| TC-S1-005 | Boundary: 101 characters | Valid name plus a 101-character name | Whole batch rejected, nothing saved | Pass |

While running TC-S1-005 I noticed the input box changing size after deleting the long name. I reported it as [BUG-001](../bugs/BUG-001-layout.md).

**Evidence problem I found in my own run:** for the reload check I captured a POST in the Network tab that created item 92, and a GET after reload that showed item 96. They were different records, so that pair didn't prove the same item survived reload. The test passed in the UI, but my evidence was weak. Since then I compare the same ID in the POST response, the GET response and SQL (as in M01).

### Story 2 – must use and prefer to avoid

| Test | Expected | Actual | Result |
| --- | --- | --- | --- |
| Must use `eggs`, prefer to avoid `eggs` | Preference warning | Warning shown | Pass |
| Change prefer to avoid from `eggs` to `rice` | Old result clears; no warning after checking again | Both happened | Pass |
| Must use `tomato`, prefer to avoid `cherry tomatoes` | I expected a warning because both are tomatoes | No warning | Not a bug |

For the tomato case I checked the requirements: `tomato` and `cherry tomatoes` are deliberately treated as different foods, so no warning is correct. My expectation was wrong, not the app.

### Story 3 – recipes

| Test | Expected | Actual | Result |
| --- | --- | --- | --- |
| Sample recipe with Greek yogurt and oats saved, prefer to avoid `apple` | Recipe shown, apple listed as missing, preference warning | All three as expected | Pass |
| Sample recipe with `eggs` as must use (negative test) | Rejected, because the sample has no eggs | No recipe card, explanation message shown | Pass |
| Live Groq generation, first attempts | Recipes returned | Errors: "recipe service could not complete the request", then "Groq denied access" | Fail, reported with request IDs |
| Live Groq after the fix | Recipes returned | Worked | Pass |
| Live Groq with `eggs` as must use | Every recipe contains eggs | 2 recipes, both with eggs | Pass |
| Read "Savory Greek Yogurt Omelette" instructions | No food used that isn't in the ingredient lists | Everything used was listed; nothing extra (not even salt) | Pass for this recipe |

The app only checks ingredient names, not the instruction text, so I checked one recipe's instructions by hand.

## API and SQL checks

| Tool | Request / query | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| Swagger (`/docs`) | GET `/api/pantry` | 200, same names as the UI | 200, names matched | Pass |
| Postman | GET `http://127.0.0.1:8000/api/pantry` | 200, same names as the UI | 200 OK, names matched | Pass |
| SQL (SQLite) | `SELECT id, display_name FROM pantry_items;` | Same ID and name as Postman | `(98, 'eggs')`, matched Postman's `id` and `display_name` | Pass |
| Postman | POST `/api/recipes/suggestions`, first attempt | 200 with the sample recipe | 422 `INVALID_REQUEST`: "Input should be a valid dictionary…", field `body` | My mistake: the body wasn't sent as a JSON object |
| Postman | Same POST with Body → raw → JSON `{"source": "sample"}` | 200, `source: sample`, apple under `missing` | 200 OK, Greek yogurt and oats in `in_pantry`, apple in `missing` with `pantry_item_id: null` | Pass |

My first SQL attempt used the wrong column name (`displayed_name`); I fixed it to `display_name`.
