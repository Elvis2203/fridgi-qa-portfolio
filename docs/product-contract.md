# Fridgi: product contract (expected behaviour)

Scope: a local pantry and validated recipe suggestion app. The offline demo uses a fixed recipe. The normal development app also supports optional Groq or OpenAI generation.

## Pantry

- P1: Commas and newlines separate foods. Ignore blank entries. A submission must contain 1–50 nonblank entries, at most 10,000 characters overall and at most 100 cleaned characters per name. Reject the whole batch if any entry is invalid.
- P2: Preserve custom foods, including leftovers and regional names. Compare names after Unicode normalization, whitespace cleanup and case folding. `eggs` and `EGGS` are duplicates. Keep `tomato` and `cherry tomatoes` separate. The reviewed `Greek yoghurt` alias maps to `Greek yogurt`.
- P3: Preserve the original input of the first saved entry. Duplicates keep the same ID. Adding returns 201 if at least one item is new, otherwise 200.
- P4: A successful delete removes that ID persistently. Reload must agree with the API and database. Deleting an unavailable ID returns 404. GET pantry must send `Cache-Control: no-store`.

## Requirements and recipes

- R1: Must-use IDs must belong to the local pantry. A deleted/stale selection returns 422. Preferences and exclusions accept custom names with the same limits as pantry batches, but may be empty.
- R2: A preference does not block a recipe. A matching name produces a warning. A name both required and preferred-avoid remains required.
- R3: A name both required and firmly excluded returns 422 `CONFLICTING_REQUIREMENTS` before any provider call. A candidate containing an excluded name is rejected. Only exact normalized names and reviewed aliases are checked.
- R4: The sample contains Greek yogurt, apple and oats. Derive owned/missing groups from saved pantry identities. Do not assume quantities are sufficient. Do not write pantry data while checking or generating recipes.
- R5: Validate candidate structure and all required ingredients independently of the provider. Omit invalid candidates; return 502 if none remain. No automatic retries or provider fallback. Provider failures include a request ID without exposing credentials.
- R6: Editing a requirement clears old results. Reload clears requirements and results, while pantry data stays saved.
- R7: No claim of allergy, dietary, nutrition or cooking-instruction validation. Food contents, contamination, packaging and instruction/ingredient consistency are outside the deterministic validator.

## Interface

- U1: Labels and keyboard controls must remain usable. Long names must wrap without changing the layout after deletion. Errors preserve input. Recipe cards distinguish missing ingredients and preference warnings.
- U2: The offline demo is clearly labelled, uses its own SQLite file and needs no credentials. The personal development database stays separate.

## Limits

Single local user; no authentication, quantities, nutrition calculations, diet classification, shopping list or recipe history. Do not expose the local server to the internet. These are deferred features, not completed capabilities. PUT/PATCH, authentication, mobile-device coverage and load testing are not claimed simply to increase tool coverage.
