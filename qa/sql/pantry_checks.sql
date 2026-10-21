-- Run SELECT statements against the demo DB (.local-demo/pantry.db), never type SQL into PowerShell.
-- Q1: UI/API/database comparison. Empty results are valid for an empty pantry.
SELECT id, display_name, original_input, normalized_key, ingredient_id
FROM pantry_items WHERE user_id = 1 ORDER BY id;

-- Q2: Uniqueness invariant. Expected: no rows.
SELECT user_id, normalized_key, COUNT(*) AS copies
FROM pantry_items GROUP BY user_id, normalized_key HAVING COUNT(*) > 1;

-- Q3: Reviewed mappings vs unresolved foods. NULL is a valid custom ingredient.
SELECT p.id, p.display_name, i.display_name AS reviewed_name
FROM pantry_items p LEFT JOIN ingredients i ON p.ingredient_id = i.id
WHERE p.user_id = 1 ORDER BY p.id;

-- Q4: Foreign key integrity. Expected: no rows.
SELECT p.id FROM pantry_items p LEFT JOIN users u ON p.user_id = u.id
WHERE u.id IS NULL;
PRAGMA foreign_key_check;

-- Q5: Compare count before and after a rejected batch / deletion.
SELECT COUNT(*) AS pantry_count,
       SUM(CASE WHEN ingredient_id IS NULL THEN 1 ELSE 0 END) AS custom_count
FROM pantry_items WHERE user_id = 1;
