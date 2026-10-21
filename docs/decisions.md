# Design decisions

Fridgi is a local, single-user application. The design keeps the path from a browser action to a database row small enough to inspect and test.

## Preserve ingredient identity

Input is open-ended: an unknown food can still be saved. Whitespace, Unicode normalization and case folding handle obvious duplicates. Reviewed aliases map Greek yoghurt to Greek yogurt; there is no fuzzy matching or automatic merging of tomato and cherry tomatoes.

This accepts some near-duplicates rather than silently merging different foods. The original input and normalization version remain available for investigation. A future alias change would need a data-reconciliation decision, not just a new string replacement.

## Use SQLite transactions and stable IDs

SQLite avoids a database-service dependency for local use. Unique and foreign-key constraints protect the stored data, and a batch either commits or rolls back. The second migration prevents deleted pantry IDs being reused, so an old selection cannot accidentally point to a new ingredient. Tests cover concurrent duplicate submissions and migration preservation.

The single-owner model and per-process recipe lock are deliberate local limits. Authentication and deployment would require further design; the existing ownership filters are not an authentication system.

## Validate recipes outside the provider

Providers return candidates. Application code validates their shape, required ingredient identities, exclusions and pantry membership. Preferences produce warnings; a firm exclusion rejects a candidate. A contradictory request stops before generation. Requests have bounded time/response size and no automatic retry or provider fallback.

The fixed recipe and injected providers make most tests repeatable without accounts, network access or charges. Name checks cannot verify sauce contents, food safety, nutrition or the meaning of cooking instructions. Those limitations are visible in the interface.

## Keep automation at the useful level

Most combinations belong in domain/API tests. Selenium covers three complete workflows: pantry persistence, recipe preferences/exclusions and the long-name layout regression. Explicit waits follow observable page state. Each test owns its database and server; failures retain a screenshot, page HTML, browser details and server log where available.
