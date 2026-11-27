# Simulating FULL OUTER JOIN and Auditing Duplicate Data

`FULL OUTER JOIN` returns every row from both tables: matching rows are paired together, rows present only in the left table still appear with `NULL` in right-table columns, and rows present only in the right table still appear with `NULL` in left-table columns. MySQL does not provide direct `FULL OUTER JOIN` syntax, so the result must be simulated using available JOIN operations.

The standard pattern combines a `LEFT JOIN` with the right-only rows using `UNION ALL`. When join key values contain duplicates, the result can expand into multiple matching pairs. This is usually the correct JOIN semantics, yet it can inflate report counts or totals if the query author assumes the key is unique. This lesson shows how to simulate `FULL OUTER JOIN`, inspect cardinality and duplicate keys, distinguish duplicate records from valid matching pairs, and verify results before using them in reports.

In the `DATABASE_MYSQL` module, this skill supports data reconciliation between two systems, catalog synchronization, customer record comparison, import verification, and detecting records that exist on only one side. What matters is clearly defining the join key and `NULL` semantics before writing the query.

## 1. Which Rows Should FULL OUTER JOIN Return?

Suppose we have two datasets A and B joined on `external_code`. A `FULL OUTER JOIN` result consists of three groups:

1. **MATCHED:** an A row has at least one B row satisfying the join condition; every matching pair is returned.
2. **LEFT_ONLY:** an A row has no corresponding B row; B columns are `NULL`.
3. **RIGHT_ONLY:** a B row has no corresponding A row; A columns are `NULL`.

Illustration:

```text
Set A                    Set B
+----+------+            +-----+------+
| id | code |            | id  | code |
+----+------+            +-----+------+
| 1  | A    |            | 101 | A    |
| 2  | B    |            | 102 | C    |
| 3  | D    |            | 103 | D    |
+----+------+            +-----+------+

FULL OUTER JOIN by code:
+------+-------+--------+
| A.id | code  | B.id   |
+------+-------+--------+
| 1    | A     | 101    |  MATCHED
| 2    | B     | NULL   |  LEFT_ONLY
| 3    | D     | 103    |  MATCHED
| NULL | C     | 102    |  RIGHT_ONLY
+------+-------+--------+
```

The result must retain unmatched rows on both sides. Using only `INNER JOIN` drops mismatched rows; using only `LEFT JOIN` drops rows that exist only in the right table.

## 2. MySQL Has No Direct FULL OUTER JOIN Syntax

In MySQL, you can simulate `FULL OUTER JOIN` using two branches:

- First branch: `A LEFT JOIN B`, fetching all A rows along with matching B rows.
- Second branch: `B LEFT JOIN A`, fetching only B rows that have no matching A row.
- Combine both branches with `UNION ALL`.

General template:

```sql
SELECT
    a.id AS a_id,
    a.join_key,
    a.value AS a_value,
    b.id AS b_id,
    b.value AS b_value
FROM table_a AS a
LEFT JOIN table_b AS b
    ON b.join_key = a.join_key

UNION ALL

SELECT
    a.id AS a_id,
    b.join_key,
    a.value AS a_value,
    b.id AS b_id,
    b.value AS b_value
FROM table_b AS b
LEFT JOIN table_a AS a
    ON a.join_key = b.join_key
WHERE a.id IS NULL;
```

`a.id` must be a non-NULL identifier column, typically the primary key. `WHERE a.id IS NULL` then accurately identifies B rows with no matching A row. Avoid using the join key column itself as the anti-join marker if that join column can be `NULL`.

`UNION ALL` is an intentional choice. It preserves the multiplicity of every row pair, matching the bag/multiset semantics of SQL JOINs. Using `UNION` adds a deduplication step and can alter reconciliation counts.

## 3. Creating Sample Data with Duplicate Keys and NULLs

To clearly observe the effect of duplicate keys, create two tables with their own primary keys where `external_code` is not unique:

```sql
CREATE TABLE source_a (
    id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(20) NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_source_a_external_code (external_code)
) ENGINE=InnoDB;

CREATE TABLE source_b (
    id BIGINT UNSIGNED NOT NULL,
    external_code VARCHAR(20) NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_source_b_external_code (external_code)
) ENGINE=InnoDB;

INSERT INTO source_a (id, external_code, description)
VALUES
    (1, 'X', 'A-X-1'),
    (2, 'X', 'A-X-2'),
    (3, 'Y', 'A-Y'),
    (4, NULL, 'A-NULL');

INSERT INTO source_b (id, external_code, description)
VALUES
    (101, 'X', 'B-X-1'),
    (102, 'X', 'B-X-2'),
    (103, 'Z', 'B-Z'),
    (104, NULL, 'B-NULL');
```

The dataset includes these cases:

- Code `X` appears twice in A and twice in B.
- Code `Y` exists only in A.
- Code `Z` exists only in B.
- Each table has one row where `external_code` is `NULL`.

Inspect each source before joining:

```sql
SELECT id, external_code, description
FROM source_a
ORDER BY id;

SELECT id, external_code, description
FROM source_b
ORDER BY id;
```

## 4. Writing the Simulated FULL OUTER JOIN Query

With the two tables above, the complete query is:

```sql
SELECT
    a.id AS a_id,
    COALESCE(a.external_code, b.external_code) AS external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description,
    CASE
        WHEN b.id IS NULL THEN 'LEFT_ONLY'
        ELSE 'MATCHED'
    END AS row_type
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code

UNION ALL

SELECT
    a.id AS a_id,
    COALESCE(a.external_code, b.external_code) AS external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description,
    'RIGHT_ONLY' AS row_type
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code = b.external_code
WHERE a.id IS NULL;
```

The first branch keeps all of A. If B does not match, `b.id` is `NULL` and `row_type` is `LEFT_ONLY`; if at least one pair matches, the row has type `MATCHED`. The second branch adds only B rows that found no A match, avoiding repeating pairs already emitted by the first branch.

`COALESCE(a.external_code, b.external_code)` retrieves the code from whichever side has data when one side is absent. If both columns are `NULL`, the result remains `NULL`. For other columns, explicitly pick the source to display or use an appropriate expression.

Because the example uses `=`, the two `NULL` values do not match each other. Hence `A-NULL` is `LEFT_ONLY`, and `B-NULL` is `RIGHT_ONLY`. This is standard SQL behavior for equality comparisons.

## 5. Why Do Duplicate Keys Multiply Row Counts?

For a given key value `k`:

- Suppose A has `m` rows with key `k`.
- Suppose B has `n` rows with key `k`.
- Joining on that key produces `m × n` pairs.

In the fixture, code `X` has two rows in A and two rows in B, so the JOIN generates four pairs:

```text
A-X-1  <->  B-X-1
A-X-1  <->  B-X-2
A-X-2  <->  B-X-1
A-X-2  <->  B-X-2
```

This is not a bug in the simulated `FULL OUTER JOIN`. It is the true semantics whenever the join condition allows multiple rows per key on each side. The remaining rows contribute:

- `A-Y`: one `LEFT_ONLY` row.
- `A-NULL`: one `LEFT_ONLY` row because `NULL = NULL` evaluates to UNKNOWN.
- `B-Z`: one `RIGHT_ONLY` row.
- `B-NULL`: one `RIGHT_ONLY` row because no A row matches via `=`.

Total output rows: 8—four `MATCHED` pairs and four one-sided rows. Output row counts can exceed the row count of either input table; never assume each source row appears only once.

### When Is Multiplication Correct?

If the data models a many-to-many relationship, multiple rows sharing a key are valid. For instance, one product code may have multiple regional price rows and multiple warehouse stock rows. Joining on product code emits all price-warehouse pairs; check whether that aligns with your reporting goal.

If business logic expects a one-to-one or many-to-one relationship, the key on the supposedly unique side must be checked and enforced with a unique constraint. Do not use `DISTINCT` to cover up a key that fails to satisfy the expected cardinality.

## 6. Detecting Duplicate Keys Before Joining

Check duplicate keys in table A:

```sql
SELECT
    external_code,
    COUNT(*) AS row_count
FROM source_a
GROUP BY external_code
HAVING COUNT(*) > 1;
```

Check similarly in table B:

```sql
SELECT
    external_code,
    COUNT(*) AS row_count
FROM source_b
GROUP BY external_code
HAVING COUNT(*) > 1;
```

`GROUP BY` groups `NULL` values into one bucket, so this query can also detect multiple `NULL` rows. If you only want to inspect populated keys:

```sql
SELECT external_code, COUNT(*) AS row_count
FROM source_a
WHERE external_code IS NOT NULL
GROUP BY external_code
HAVING COUNT(*) > 1;
```

For composite keys, inspect all components matching the exact JOIN condition:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS row_count
FROM imported_customers
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

If the JOIN condition uses `(tenant_id, external_code)` but you only check `external_code`, your uniqueness conclusion will be wrong because the same code can legitimately exist in different tenants.

## 7. Counting Matching Pairs and Forecasting Cardinality

To understand row growth, count occurrences of each key on both sides:

```sql
SELECT
    'A' AS source_name,
    external_code,
    COUNT(*) AS rows_per_key
FROM source_a
GROUP BY external_code

UNION ALL

SELECT
    'B' AS source_name,
    external_code,
    COUNT(*) AS rows_per_key
FROM source_b
GROUP BY external_code
ORDER BY external_code, source_name;
```

For non-NULL keys joined with `=`, the number of matching pairs for a key equals the row count in A multiplied by the row count in B. You can compute this specifically for keys present in both tables:

```sql
SELECT
    a.external_code,
    a.rows_a,
    b.rows_b,
    a.rows_a * b.rows_b AS expected_match_pairs
FROM (
    SELECT external_code, COUNT(*) AS rows_a
    FROM source_a
    WHERE external_code IS NOT NULL
    GROUP BY external_code
) AS a
JOIN (
    SELECT external_code, COUNT(*) AS rows_b
    FROM source_b
    WHERE external_code IS NOT NULL
    GROUP BY external_code
) AS b
    ON b.external_code = a.external_code
ORDER BY a.external_code;
```

This query only predicts matching pair counts for non-NULL keys under standard equality. If the JOIN condition also involves tenant, status, date ranges, or normalization expressions, include all of those conditions in the counting step.

## 8. Auditing the Simulated Result

Reconciliation should verify at least three invariants:

1. Every row in A appears in the result at least once.
2. Every row in B appears in the result at least once.
3. Matched rows are returned pairwise; unmatched rows are tagged accurately as `LEFT_ONLY` or `RIGHT_ONLY`.

You can wrap the simulated `FULL OUTER JOIN` query in a CTE to compute summary metrics:

```sql
WITH full_result AS (
    SELECT
        a.id AS a_id,
        COALESCE(a.external_code, b.external_code) AS external_code,
        b.id AS b_id,
        CASE WHEN b.id IS NULL THEN 'LEFT_ONLY'
             ELSE 'MATCHED' END AS row_type
    FROM source_a AS a
    LEFT JOIN source_b AS b
        ON b.external_code = a.external_code

    UNION ALL

    SELECT
        a.id AS a_id,
        COALESCE(a.external_code, b.external_code) AS external_code,
        b.id AS b_id,
        'RIGHT_ONLY' AS row_type
    FROM source_b AS b
    LEFT JOIN source_a AS a
        ON a.external_code = b.external_code
    WHERE a.id IS NULL
)
SELECT
    COUNT(*) AS output_rows,
    COUNT(DISTINCT a_id) AS source_a_rows_represented,
    COUNT(DISTINCT b_id) AS source_b_rows_represented,
    SUM(row_type = 'MATCHED') AS matched_pairs,
    SUM(row_type = 'LEFT_ONLY') AS left_only_rows,
    SUM(row_type = 'RIGHT_ONLY') AS right_only_rows
FROM full_result;
```

In the fixture, `source_a_rows_represented` and `source_b_rows_represented` are both 4, `matched_pairs` is 4, `left_only_rows` is 2, and `right_only_rows` is 2; total output is 8. Distinct ID metrics verify source row coverage, whereas `matched_pairs` counts matching pairs. Those two numbers diverge whenever duplicate keys exist.

CTEs require MySQL 8.0 or newer. On MySQL 5.7, wrap the `UNION ALL` inside a derived table and compute the aggregates in the outer query.

## 9. Choosing the Right Anti-Join Column

In the second branch, the standard check is:

```sql
WHERE a.id IS NULL
```

This is safe only when `a.id` cannot be `NULL` in any real row, such as a primary key. If you use `a.external_code IS NULL` to test for absence of an A row, a real A row with a `NULL` `external_code` could be mistaken for a non-match, especially when the join uses `<=>` or complex logic.

An alternative is using `NOT EXISTS` to retrieve B rows without a matching A row:

```sql
SELECT
    b.id,
    b.external_code,
    b.description
FROM source_b AS b
WHERE NOT EXISTS (
    SELECT 1
    FROM source_a AS a
    WHERE a.external_code = b.external_code
);
```

`NOT EXISTS` directly expresses an anti-join and avoids relying on checking a `NULL` column from side A. Under standard equality, a B row with `external_code IS NULL` also finds no match in A because `a.external_code = NULL` is not TRUE, so that row is returned. Choose between `LEFT JOIN ... IS NULL` and `NOT EXISTS` by measuring on real data, not purely on style.

## 10. NULLs in Join Keys: `=` or `<=>`?

With the condition:

```sql
ON a.external_code = b.external_code
```

two `NULL`s do not match. This is standard behavior because `NULL = NULL` returns UNKNOWN.

If business logic wants to treat two `NULL` values as equivalent, MySQL provides the NULL-safe equality operator `<=>`:

```sql
ON a.external_code <=> b.external_code
```

When using `<=>`, `NULL` in A can match `NULL` in B. However, if A has `m` `NULL` rows and B has `n` `NULL` rows, the result produces `m × n` `NULL` pairs. That can generate an unexpectedly large number of rows.

If you switch to `<=>`, you must use the exact same condition in both branches of the simulated `FULL OUTER JOIN`:

```sql
SELECT a.id AS a_id, b.id AS b_id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON a.external_code <=> b.external_code

UNION ALL

SELECT a.id AS a_id, b.id AS b_id
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code <=> b.external_code
WHERE a.id IS NULL;
```

Use this only when `NULL` genuinely represents a single matchable value. In many systems, `NULL` means "code unknown," so two `NULL` rows should not be treated as the same entity. Document the `NULL` rule explicitly in reconciliation specs.

## 11. Distinguishing Source Duplicate Records from JOIN-Induced Duplicates

Two different situations often get lumped together as "duplicate data":

- **Source duplicates:** a single table has multiple rows with the same key or multiple records that are identical by business criteria.
- **Multiple valid matching pairs:** both tables have multiple rows sharing a key; the JOIN creates a Cartesian product within each key group.

For instance, code `X` has two rows in A and two rows in B. The four matched pairs are not necessarily four completely duplicated source records—they are four combinations between two A rows and two B rows.

To identify source duplicates, define the grain (uniqueness level) of each table. For example:

- `source_a.id` is unique because it is the primary key.
- `source_a.external_code` may not be unique if one code has multiple versions.
- If business rules require one unique `external_code` per tenant, the unique key must be `(tenant_id, external_code)`.

Check for records sharing multiple attributes:

```sql
SELECT
    external_code,
    description,
    COUNT(*) AS duplicate_count
FROM source_a
GROUP BY external_code, description
HAVING COUNT(*) > 1;
```

This query finds rows that match on the chosen attribute pair; it does not prove two rows are identical across all columns. Before deduplicating, define which row is canonical, which history must be preserved, and the data merging rules.

## 12. Do Not Use DISTINCT to Mask Cardinality Bugs

A common anti-pattern is slapping `DISTINCT` onto a JOIN when too many rows come back:

```sql
SELECT DISTINCT
    a.external_code,
    a.description,
    b.description
FROM source_a AS a
JOIN source_b AS b
    ON b.external_code = a.external_code;
```

`DISTINCT` only removes rows that are completely identical across the projected `SELECT` columns. It does not fix a broken JOIN condition, does not guarantee each source row appears once, and can drop valid pairs when the projection omits the identifying keys of both sides.

If you want one representative row from B per code, define a deterministic selection rule before joining—such as the latest record by `updated_at` with a primary-key tie-breaker. In MySQL 8.0, you can use `ROW_NUMBER()`:

```sql
WITH ranked_b AS (
    SELECT
        b.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_code
            ORDER BY updated_at DESC, id DESC
        ) AS rn
    FROM source_b AS b
)
SELECT
    a.id AS a_id,
    a.external_code,
    a.description AS a_description,
    b.id AS b_id,
    b.description AS b_description
FROM source_a AS a
LEFT JOIN ranked_b AS b
    ON b.external_code = a.external_code
   AND b.rn = 1;
```

This is a `LEFT JOIN` picking one B row by rule, not a complete `FULL OUTER JOIN`. If you need to simulate a `FULL OUTER JOIN` after selecting a representative record, use the same `ranked_b` set in both branches and write the anti-join for side B. Base record-selection rules on business requirements rather than arbitrarily picking `MAX(id)` if IDs do not reflect update order.

## 13. JOIN Conditions and WHERE Filters Can Drop Outer Rows

With an OUTER JOIN, condition placement matters:

```sql
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code
   AND b.status = 'ACTIVE';
```

The `b.status = 'ACTIVE'` condition in `ON` restricts which B rows can match, while preserving every A row; A rows with no active B get `NULL` for B columns.

If written as:

```sql
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code
WHERE b.status = 'ACTIVE';
```

`WHERE` removes rows where `b.status` is `NULL`, effectively dropping unmatched rows and making the query behave almost like an `INNER JOIN` for that predicate.

When simulating `FULL OUTER JOIN`, decide which conditions govern "eligible to match" and which filter the final output. If you add a filter on the right table, apply it consistently in the proper place across both branches; otherwise, you can corrupt the `LEFT_ONLY` or `RIGHT_ONLY` sets.

## 14. Key Normalization and Data Type Compatibility

Both join columns should share compatible data types and comparison rules. If one side is numeric and the other is a string, MySQL can perform implicit conversion, producing surprising results and hurting index usage.

Examples of issues to check:

- `INT` joined with `VARCHAR` containing codes with leading zeros.
- `CHAR` joined with `VARCHAR` having trailing spaces.
- Two text columns with different character sets or collations.
- One side case-sensitive and the other case-insensitive.
- Source codes with leading/trailing spaces or differing Unicode normalization.
- Composite keys missing tenant or entity type in the JOIN condition.

Avoid casually wrapping JOIN columns in `TRIM()`, `LOWER()`, or `CAST()` in every query. If normalization is needed, enforce it during data ingestion or maintain a dedicated indexed normalized column. Check `EXPLAIN` to verify whether expressions prevent index lookups.

## 15. Indexes and Performance of Simulated FULL OUTER JOIN

The simulation executes two JOIN branches, so both tables benefit from lookup paths on the join key. In the fixture, we created indexes:

```sql
KEY idx_source_a_external_code (external_code)
KEY idx_source_b_external_code (external_code)
```

Key guidelines:

- Create indexes on columns used in JOIN conditions when workload and selectivity justify them.
- For composite keys, index column order should align with key and query predicates, e.g., `(tenant_id, external_code)`.
- If a key is expected to be unique, enforce `UNIQUE` after cleaning and validating data.
- Avoid type casting or wrapping JOIN columns in functions if you rely on standard index lookups.
- Inspect both branches with `EXPLAIN`; the optimizer may choose different access paths for each branch.
- Evaluate estimated and actual row counts, especially when keys have many duplicates.

Example inspecting each side:

```sql
EXPLAIN
SELECT a.id, b.id
FROM source_a AS a
LEFT JOIN source_b AS b
    ON b.external_code = a.external_code;

EXPLAIN
SELECT a.id, b.id
FROM source_b AS b
LEFT JOIN source_a AS a
    ON a.external_code = b.external_code
WHERE a.id IS NULL;
```

`EXPLAIN ANALYZE` on supported versions executes the query to measure actual row counts and timing per iterator. Run it on staging or test datasets if the query may scan many rows.

## 16. Practical Reconciliation Between Two Systems

A standard reconciliation workflow includes these steps:

1. Define the grain of each source: what entity does one row represent?
2. Define the join key: single or composite key; are `NULL`s allowed?
3. Check data types, character sets, collations, and key normalization rules.
4. Count duplicate keys in each source before joining.
5. Estimate matching pairs via `count_A × count_B` per key.
6. Run the simulated `FULL OUTER JOIN` including both source IDs and `row_type`.
7. Check source coverage using `COUNT(DISTINCT source_id)`.
8. Analyze `LEFT_ONLY`, `RIGHT_ONLY`, and `MATCHED` separately.
9. Resolve duplicates by business rules; never wipe them out with `DISTINCT` before defining the canonical record.
10. Save reconciliation queries and metrics so they can be re-run after each sync.

Example isolating only mismatched records for investigation:

```sql
WITH full_result AS (
    SELECT
        a.id AS a_id,
        a.external_code,
        a.description AS a_description,
        b.id AS b_id,
        b.description AS b_description,
        CASE WHEN b.id IS NULL THEN 'LEFT_ONLY'
             ELSE 'MATCHED' END AS row_type
    FROM source_a AS a
    LEFT JOIN source_b AS b
        ON b.external_code = a.external_code

    UNION ALL

    SELECT
        a.id AS a_id,
        b.external_code,
        a.description AS a_description,
        b.id AS b_id,
        b.description AS b_description,
        'RIGHT_ONLY' AS row_type
    FROM source_b AS b
    LEFT JOIN source_a AS a
        ON a.external_code = b.external_code
    WHERE a.id IS NULL
)
SELECT *
FROM full_result
WHERE row_type <> 'MATCHED'
ORDER BY row_type, external_code, a_id, b_id;
```

This query focuses on records appearing in only one source. If you also need to detect content differences between rows sharing the same key, keep `MATCHED` and compare business columns using appropriate NULL-safe rules.

## 17. Checking Content Differences Between Matched Rows

A JOIN only proves two rows satisfy the key condition; it does not prove other attributes are identical. To find records with the same code but differing descriptions:

```sql
SELECT
    a.id AS a_id,
    b.id AS b_id,
    a.external_code,
    a.description AS a_description,
    b.description AS b_description
FROM source_a AS a
JOIN source_b AS b
    ON b.external_code = a.external_code
WHERE NOT (a.description <=> b.description);
```

`<=>` is MySQL's NULL-safe equality operator. `NOT (a.description <=> b.description)` finds pairs whose descriptions differ, including cases where one side is `NULL` and the other has a value; two `NULL`s are treated as equal. If you need byte-for-byte comparison instead of text collation rules, use an appropriate binary type or expression.

When duplicate keys exist, this query compares every pair sharing a key. If A has two rows and B has three rows with the same code, it evaluates six pairs. For one-to-one comparisons, select or pair records by the full business key before comparing attributes.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using a standalone `LEFT JOIN` and assuming it is a `FULL OUTER JOIN` | Drops rows present only in the right table | Add the anti-join branch from B to A. |
| Using `UNION` instead of `UNION ALL` | Deduplicates identical rows and distorts multiplicity | Use `UNION ALL` to preserve multiplicity. |
| Checking an anti-join via a nullable join column | Real rows with `NULL` keys can be misclassified as unmatched | Check a non-NULL primary key on the `LEFT JOIN`ed side. |
| Ignoring duplicate keys | Results grow as `m × n` | Count rows per key in both sources before joining. |
| Adding `DISTINCT` to shrink row counts | May drop legitimate pairs without fixing the root cause | Clarify grain and cardinality; resolve duplicates per business rules. |
| Using `=` while expecting `NULL` to match `NULL` | `NULL` rows on both sides are treated as unmatched | Use `<=>` only if `NULL` has equivalent matching semantics. |
| Using `<=>` with many `NULL`s without forecasting | Can produce an `m × n` product between two `NULL` groups | Define `NULL` semantics explicitly and measure cardinality. |
| Putting a right-side filter in `WHERE` of a `LEFT JOIN` | Drops unmatched rows | Move the match condition into `ON` if left rows must remain. |
| Checking only a code while omitting tenant or entity type | Mismatches records across scopes | Include the full business composite key. |
| Neglecting key type/collation compatibility | Implicit conversions, unexpected comparisons, or lost index usage | Standardize schemas and verify with metadata/`EXPLAIN`. |

## 19. Hands-On Exercises

### Exercise A — Simulating FULL OUTER JOIN

1. Create `source_a` and `source_b` from the fixture.
2. Write the `A LEFT JOIN B` branch.
3. Write the `B LEFT JOIN A WHERE A.id IS NULL` branch.
4. Combine them with `UNION ALL` and add `row_type`.
5. Verify `MATCHED`, `LEFT_ONLY`, and `RIGHT_ONLY` rows.

### Exercise B — Measuring Duplicate Key Impact

1. Count rows per `external_code` in each source.
2. Compute `rows_a × rows_b` for each matching key.
3. Run the JOIN and count actual matching pairs.
4. Insert one more row with code `X` into each table and predict the row growth.
5. Explain why the row growth follows from cardinality rather than a SQL bug.

### Exercise C — Testing NULL Keys

1. Run the simulation using `=`.
2. Verify the two `NULL` rows return separately on their respective sides.
3. Re-run using `<=>` in both branches.
4. Add multiple `NULL` rows to each table and count the resulting pairs.
5. Write a business policy specifying when `NULL` values are allowed to match.

### Exercise D — Content Reconciliation

1. Keep the IDs from both sources in the output.
2. Use `COUNT(DISTINCT a_id)` and `COUNT(DISTINCT b_id)` to verify source coverage.
3. Filter `LEFT_ONLY` and `RIGHT_ONLY` to locate missing records.
4. Filter `MATCHED` and use NULL-safe comparison to find differing attributes.
5. Record the metrics and duplicates that need cleanup.

### Exercise E — Query Optimization

1. Create indexes on both join key columns.
2. Run `EXPLAIN` for each branch.
3. Try a composite key `(tenant_id, external_code)`.
4. Compare plans when key columns have compatible types/collations versus implicit casting.
5. Evaluate results on data with a realistic duplicate distribution.

You have completed this lesson when you can fully simulate all three groups of a `FULL OUTER JOIN`, predict pair counts caused by duplicate keys, define `NULL` semantics, audit coverage across both sources, and explain why `UNION ALL` fits this simulation better than `UNION`.

## 20. Key Principles to Remember

- MySQL has no direct `FULL OUTER JOIN` syntax; simulate it with `LEFT JOIN` plus a right-side anti-join branch.
- Use `UNION ALL` to preserve all pairs and data multiplicity.
- Use a non-NULL primary key on the `LEFT JOIN`ed side to detect unmatched rows.
- For duplicate keys, `m` rows in A and `n` rows in B yield `m × n` matching pairs for that key.
- Distinguish source duplicates from valid multi-match pairs caused by many-to-many relationships.
- Audit duplicates and cardinality before aggregating or reconciling.
- `=` does not match two `NULL`s; `<=>` matches `NULL` with `NULL` and can multiply `NULL` row groups.
- Do not use `DISTINCT` to hide key bugs or poorly understood cardinality.
- Put matching criteria in `ON`; filters in `WHERE` can drop outer rows from an OUTER JOIN.
- Verify full composite keys, data types, charset/collation, and indexes with `EXPLAIN`.
- Reconcile using source IDs, `row_type`, distinct row counts, and attribute comparisons across `MATCHED` pairs.

When you simulate `FULL OUTER JOIN` properly and systematically audit duplicates, you can reconcile two sources without losing mismatched records or silently inflating numbers. Every result can be accounted for at the row level, the matched-pair level, and the duplicate-key group level.
