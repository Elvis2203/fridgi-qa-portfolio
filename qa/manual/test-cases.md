# Test cases

Expected behaviour comes from the [product contract](../../docs/product-contract.md) (P = pantry, R = recipes, U = interface).

## Main risks

| Risk | Technique | Covered by |
| --- | --- | --- |
| Pantry data lost after reload | State transition | M01, M05 |
| Duplicates merged wrongly, or different foods merged | Equivalence partitioning | M02 |
| Name length limit wrong; part of a bad batch saved | Boundary values, negative test | M03 |
| Preferences and exclusions ignored or mixed up | Decision table | M04 |
| Old recipe result still shown after changing requirements | State transition | M04 |
| Layout breaks with long names; delete not usable by keyboard | Exploratory, regression, keyboard check | M05 |

## Decision table: requirements

| Must use | Prefer to avoid | Do not use | Expected |
| --- | --- | --- | --- |
| No | No | No | Recipe may contain the food |
| Yes | Yes | No | Recipe must contain it; show a preference warning |
| No | Yes | No | Recipe may contain it; warning if it does |
| Yes | Any | Yes | Request rejected before generating (422) |
| No | Any | Yes | A recipe containing it is rejected |

## M01 – Free-form input survives reload (P1–P3)

Start: offline demo, empty pantry.

1. Add `eggs, leftover roast chicken`, a new line, then `homemade tomato sauce` in one submission.
2. Check that three separate items appear, then reload the page.
3. Compare names and IDs with `GET /api/pantry` and SQL query Q1.

Expected: all three items are still there after reload with the same IDs. Custom foods are accepted.

## M02 – Duplicates, alias and different foods (P2–P3)

1. Add `Chicken, chicken, CHICKEN` in one submission.
2. Add `greek yoghurt`, then `Greek yogurt`.
3. Add `tomato, cherry tomatoes`.
4. Reload and check the stored rows with SQL Q1/Q3.

Expected: one chicken, one `Greek yogurt` (the yoghurt spelling is a supported alias), and two separate tomato items: four items in total. The first spelling entered is kept as the original input.

## M03 – Name length limit and whole-batch rejection (P1)

1. Add a name of exactly 99 `a` characters, then one of 100 `b` characters.
2. Add `eggs` together with a name of 101 `c` characters in the same submission.
3. Read the error message, reload, and check `GET /api/pantry`.

Expected: 99 and 100 are accepted. The third submission is rejected completely: neither `eggs` nor the 101-character name is saved.

## M04 – Preference, exclusion and old results (R1–R6)

1. Save `Greek yogurt, oats`. Set Prefer to avoid to `apple` and click Try a sample recipe.
2. Check the recipe card: apple under Missing ingredients, plus a preference warning.
3. Clear Prefer to avoid and put `apple` in Do not use. Check that the old result disappeared, then request the sample again.
4. Save `eggs`, tick it under Must use and also type `eggs` in Do not use. Submit and check the response in the Network tab.

Expected: step 1 shows the recipe with apple missing and a warning. Editing a field clears the old result. Step 3 shows no recipe card and a rejection message. Step 4 returns 422 (conflicting requirements) before any recipe is generated.

## M05 – Long name layout, keyboard and delete (P4, U1)

1. Add a 100-character name with no spaces, and one short name.
2. At window widths of 1000 and 500 px, check the list and the Delete button. Use Tab to reach Delete on the long name and press Enter.
3. Reload and compare `GET /api/pantry` with the list.

Expected: the long name wraps inside its row, the input box keeps its size, Delete stays visible and works with the keyboard, the deletion is still there after reload, and the short name remains.
