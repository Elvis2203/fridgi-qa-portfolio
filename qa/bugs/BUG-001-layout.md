# BUG-001: Ingredient input box changes width after deleting a long name

**Status:** Fixed, retested  
**Found by:** me, during manual test TC-S1-005 (boundary test)  
**Severity:** Minor (cosmetic / usability)  
**Priority:** Medium: it happens during a normal action (deleting an ingredient) and is very visible, but nothing is blocked  
**Requirement:** U1, long names must not change the layout after deletion  
**Environment:** Windows 10, Firefox 158.0 (64-bit), window width about 1000 px, development app  

## Steps to reproduce

1. Keep the browser window at the same width.
2. In the Ingredients field, type a 100-character word with no spaces (e.g. 100 × `a`) and click **Add to my pantry**.
3. Click **Delete** next to the long name.

## Expected result

The ingredients input box keeps the same size.

## Actual result

As soon as the long name is deleted, the ingredients input box becomes much wider. Height does not change.

## Cause and fix

The status message shown after deleting ("… deleted from your pantry.") contained the long name without spaces. It could not wrap, so it pushed one grid column wider. The fix (in `frontend/src/styles.css`) lets the message wrap (`overflow-wrap: anywhere`) and stops the grid columns from growing. The fix was implemented with AI assistance. The screenshots below were captured with browser automation while reproducing it.

## Retest

- Retested manually as part of [M05](../manual/test-execution.md#m01m05-run) at 1000 px and 500 px: the input box kept its size and the long name wrapped. **Pass.**
- A Selenium regression test, `test_long_name_deletion_layout_regression` in `qa/automation/test_browser.py`, adds a 100-character name, deletes it and checks that the input box keeps its width, at 1000 and 500 px.

## Evidence

[Before the fix](../evidence/layout-before.png) · [After the fix](../evidence/layout-after.png)
