# FIRST_VALUE, LAST_VALUE, NTH_VALUE, and Window Scope

`FIRST_VALUE()`, `LAST_VALUE()`, and `NTH_VALUE()` retrieve a value from a row within a window based on the declared ordering and frame scope. Unlike `MIN()` or `MAX()` in an aggregate query, they do not collapse multiple rows into one; every input row is preserved and augmented with a value looked up from its own frame.

The easiest trap to fall into is the **window frame**. When `ORDER BY` is present without an explicit frame, MySQL defaults to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Consequently, `LAST_VALUE()` usually returns the value at the end of the current frame rather than the last value of the entire partition. To get the partition's final value, you must extend the frame to `UNBOUNDED FOLLOWING`.

Within the `DATABASE_MYSQL` module, these functions are useful for attaching the first/last value of a group to every row, retrieving the Nth ordered element, comparing current status against initial/final milestones, or building time-series reports. This lesson focuses on choosing the right frame, handling tied rows and NULLs, and verifying results before using them in reports.

## 1. Three components of a window specification

A window specification typically has three parts:

```sql
function_name(expression) OVER (
    PARTITION BY partition_columns
    ORDER BY ordering_columns
    frame_clause
)
```

- `PARTITION BY` splits data into independent groups. Each window function is evaluated separately per partition.
- `ORDER BY` defines the row order within a partition. It determines which row is first, last, or Nth.
- `frame_clause` defines the subset of rows belonging to the current row's window. This is especially critical for `FIRST_VALUE()`, `LAST_VALUE()`, and `NTH_VALUE()`.

If `PARTITION BY` is omitted, the entire result set forms a single partition. If `ORDER BY` is omitted, there is no reliable business order for determining first, last, or Nth position. If the frame is omitted, MySQL applies the default frame per window specification rules.

## 2. Preparing practice data

Create a score table grouped by team and timestamp. Each row has a unique `id` to act as a tie-breaker when multiple events share the same timestamp.

```sql
CREATE TABLE employee_scores (
    id BIGINT UNSIGNED NOT NULL,
    team VARCHAR(30) NOT NULL,
    scored_at DATETIME NOT NULL,
    score DECIMAL(6,2) NULL,
    PRIMARY KEY (id),
    KEY idx_employee_scores_team_time (team, scored_at, id)
) ENGINE=InnoDB;

INSERT INTO employee_scores (id, team, scored_at, score)
VALUES
    (1, 'Alpha', '2026-01-01 09:00:00', 10.00),
    (2, 'Alpha', '2026-01-02 09:00:00', 20.00),
    (3, 'Alpha', '2026-01-03 09:00:00', 30.00),
    (4, 'Alpha', '2026-01-04 09:00:00', 40.00),
    (5, 'Beta',  '2026-01-01 09:00:00', NULL),
    (6, 'Beta',  '2026-01-02 09:00:00',  7.00),
    (7, 'Beta',  '2026-01-03 09:00:00', 11.00);
```

Each team has multiple events over time. Team `Beta` has a NULL first score to observe how value window functions handle NULLs.

Inspect the data:

```sql
SELECT id, team, scored_at, score
FROM employee_scores
ORDER BY team, scored_at, id;
```

## 3. `FIRST_VALUE()` retrieves the first value in the frame

Basic syntax:

```sql
FIRST_VALUE(expression) OVER (window_specification)
```

`FIRST_VALUE()` returns the expression value from the first row in the current frame according to the window `ORDER BY`.

Example retrieving the first score of each team and displaying it on every row:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

The frame covers the entire partition, so every row in the same team receives the same `first_score_in_team`. For `Alpha`, the result is `10.00`; for `Beta`, the result is NULL because that team's first row has a NULL `score`.

### FIRST_VALUE with a frame running from the start to the current row

If the frame is:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

the frame starts at the beginning of the partition and ends at the current row. `FIRST_VALUE()` still returns the first value of the partition for all subsequent rows, provided the frame does not exclude the first row.

```sql
SELECT
    id,
    team,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS first_score_so_far
FROM employee_scores
ORDER BY team, scored_at, id;
```

If the frame starts after the first row of the partition—for example `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`—the first value will be the first row within that sliding frame, no longer necessarily the first row of the entire partition.

## 4. `LAST_VALUE()` and the default frame trap

Syntax:

```sql
LAST_VALUE(expression) OVER (window_specification)
```

`LAST_VALUE()` returns the expression value from the last row in the current frame. It does not inherently mean "the last row of the partition."

With `ORDER BY` and no frame specified, MySQL uses the default frame:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

If the ordering is unique, the frame ends at the current row. In that case, `LAST_VALUE(score)` equals the `score` of the current row itself. This is a common reason results differ from expectations.

### Comparing the default frame with a full-partition frame

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
    ) AS last_value_default,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_value_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

The two columns have different meanings:

- `last_value_default`: the value at the end of the default frame, which with a unique sort key is the value of the current row.
- `last_value_in_team`: the value at the last row of the entire partition; all rows in the team receive the same result.

For `Alpha`, `last_value_in_team` is `40.00`. For `Beta`, it is `11.00`. Beta's first row still has `last_value_default = NULL` because the current row's value is NULL, while `last_value_in_team = 11.00`.

### Frame retrieving the last value up to the current row

If the goal is to retrieve the last value of a frame running from the start up to the current row, declare it explicitly:

```sql
LAST_VALUE(score) OVER (
    PARTITION BY team
    ORDER BY scored_at, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

With a unique order, the result is the current row's value. Even though the result looks simple, declaring the frame explicitly signals to readers that this is a prefix calculation and avoids relying on the default frame.

## 5. `NTH_VALUE()` retrieves the value at the Nth position in the frame

Syntax:

```sql
NTH_VALUE(expression, N) OVER (window_specification)
```

`NTH_VALUE()` returns the expression at the `N`th row in the current frame, according to `ORDER BY`. `N` is a positive integer. Position is counted from the beginning of the frame, not from the beginning of the partition if the frame starts mid-partition.

Example retrieving the second score of each team across the entire partition:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_score_in_team
FROM employee_scores
ORDER BY team, scored_at, id;
```

For `Alpha`, the second value is `20.00`; for `Beta`, the second value is `7.00`. Since the frame covers the full partition, the result is repeated on every row of the team.

### NTH_VALUE with the default frame

If you omit the frame while using `ORDER BY`, the default frame runs only from the start of the partition to the current row (including peers of the current row under RANGE). On rows where the frame does not yet contain `N` rows, `NTH_VALUE()` returns NULL.

```sql
SELECT
    id,
    team,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
    ) AS second_value_so_far
FROM employee_scores
ORDER BY team, scored_at, id;
```

On the first row of each team, the frame contains only one row, so no second position exists; the result is NULL. From the second row onward, the second position exists and the result is the value of the second row in the partition.

A NULL from `NTH_VALUE()` can have two causes: either the frame has fewer than N rows, or the Nth row exists but its expression evaluates to NULL. If you need to distinguish them, check the row count using `COUNT(*) OVER (...)` with the exact same `PARTITION BY`, `ORDER BY`, and frame as `NTH_VALUE()`; if the frame row count is less than N, the position does not yet exist, whereas if it is at least N, the NULL comes from the expression on the Nth row.

## 6. Full-partition, running, and sliding frames

The frame determines which rows the function is allowed to see. Common patterns:

| Frame | Meaning |
|---|---|
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Entire partition. |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | From the start of the partition to the current row. |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | The current row and up to two preceding rows. |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | From the current row to the end of the partition. |

Example retrieving the first, last, and second elements within a three-row sliding frame:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS first_in_last_three_rows,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_in_last_three_rows,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS second_in_last_three_rows
FROM employee_scores
ORDER BY team, scored_at, id;
```

When the frame has fewer than three rows at the start of a partition, it contains only the available rows. `NTH_VALUE(score, 2)` remains NULL until the frame has at least two rows; if the second row has a NULL score, the result is also NULL.

## 7. How do `ROWS` and `RANGE` differ?

MySQL supports two main frame units:

- `ROWS`: defines the frame by the physical number of rows before/after the current row in window order.
- `RANGE`: defines the frame by the value of the `ORDER BY` expression; rows sharing the same sort value are peers and are included together when a boundary is `CURRENT ROW`.

With unbounded frames, both units typically give identical results when ordering is unique. The clearest difference appears in frames with a `CURRENT ROW` boundary and tied rows.

### Fixture with two rows at the same timestamp

```sql
CREATE TABLE score_events_tied (
    id BIGINT UNSIGNED NOT NULL,
    team VARCHAR(30) NOT NULL,
    scored_at DATETIME NOT NULL,
    score DECIMAL(6,2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO score_events_tied (id, team, scored_at, score)
VALUES
    (1, 'Gamma', '2026-02-01 09:00:00', 10.00),
    (2, 'Gamma', '2026-02-01 09:00:00', 20.00),
    (3, 'Gamma', '2026-02-02 09:00:00', 30.00);
```

Compare cumulative row counts:

```sql
SELECT
    id,
    scored_at,
    score,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY scored_at
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_rows,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY scored_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS rows_rows
FROM score_events_tied
ORDER BY scored_at, id;
```

With `RANGE`, the two rows sharing the same `scored_at` are peers, so both see a frame containing the first two rows; `range_rows` is 2 for both. With `ROWS`, the frame grows one row position at a time; the two same-timestamp rows may receive 1 and 2 in whatever internal order the window engine chooses. Because `ORDER BY scored_at` does not determine the order between two rows with identical timestamps, you must not rely on which row receives 1 or 2.

If you need deterministic per-row ordering, add a unique tie-breaker:

```sql
ORDER BY scored_at, id
```

However, once `id` is added, the two rows are no longer peers across the entire ORDER BY expression list. Choose `ROWS` or `RANGE` based on business semantics, not merely the expected output on one sample dataset.

## 8. MySQL default frames

When `ORDER BY` is present without an explicit frame, MySQL defaults to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

When `ORDER BY` is absent and no frame is specified, the default frame spans the entire partition:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

That is why the exact same `LAST_VALUE()` can yield different results simply by adding `ORDER BY`. Without `ORDER BY`, the concepts of first and last have no deterministic business order; even though the frame spans the entire partition, which row is treated as first or last remains unstable.

Best practices:

1. Always write `ORDER BY` with a deterministic tie-breaker when row position matters.
2. Write an explicit frame for `LAST_VALUE()` and `NTH_VALUE()` when the entire partition is intended.
3. Write an explicit frame for running or sliding frames.
4. Do not rely on physical order, primary key, or insertion order unless they are explicitly listed in the window `ORDER BY`.

## 9. Tied rows and result determinism

`ORDER BY scored_at` may leave multiple rows with identical timestamps. In that case, MySQL recognizes them as peers but has no rule defining their relative order unless additional sort columns are provided.

For `FIRST_VALUE()` or `LAST_VALUE()`, if a frame starts or ends at a peer group with multiple rows, the retrieved value depends on which row happens to be ordered first or last. For `NTH_VALUE()`, the Nth position can also be unstable if multiple tied rows fall around the target position.

Recommended pattern:

```sql
ORDER BY scored_at, id
```

Here `id` is a unique key. If business rules require true ties, do not add a tie-breaker to the window just to force an arbitrary row order; instead, define explicitly how to pick a representative within the peer group or accept peer-based semantics.

Window `ORDER BY` only defines the ordering used to evaluate the function. It does not guarantee the final order of the SELECT output. If the UI requires ordered results, add an `ORDER BY` to the outermost query block.

## 10. NULL and null treatment

`FIRST_VALUE()`, `LAST_VALUE()`, and `NTH_VALUE()` respect NULLs (`RESPECT NULLS`) by default. If the first row in the frame has a NULL expression, `FIRST_VALUE()` returns NULL. If the last row has a NULL expression, `LAST_VALUE()` returns NULL. If the Nth position holds NULL, `NTH_VALUE()` also returns NULL.

MySQL only supports `RESPECT NULLS`; the `IGNORE NULLS` option is not supported. You cannot add `IGNORE NULLS` to instruct the function to skip NULL rows automatically.

You may write `RESPECT NULLS` explicitly; omitting it gives the same default behavior:

```sql
SELECT
    id,
    team,
    FIRST_VALUE(score) RESPECT NULLS OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score
FROM employee_scores
ORDER BY team, scored_at, id;
```

Verification example:

```sql
SELECT
    id,
    team,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_score_respecting_null,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_score_respecting_null
FROM employee_scores
ORDER BY team, scored_at, id;
```

For team Beta, the first score is NULL because the first event has a NULL score; the last score is 11.00. Do not confuse NULL with 0 or with "no rows in the frame."

### When business logic needs the first/last non-NULL value

Because `IGNORE NULLS` is unsupported, you can filter out NULL rows in a separate query block if the goal is to find a representative non-NULL value for the entire partition:

```sql
WITH ranked_non_null AS (
    SELECT
        team,
        score,
        scored_at,
        id,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at, id
        ) AS rn_first,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at DESC, id DESC
        ) AS rn_last
    FROM employee_scores
    WHERE score IS NOT NULL
)
SELECT
    team,
    MAX(CASE WHEN rn_first = 1 THEN score END) AS first_non_null_score,
    MAX(CASE WHEN rn_last = 1 THEN score END) AS last_non_null_score
FROM ranked_non_null
GROUP BY team;
```

This example returns the chronologically first and last non-NULL score for each team. It is not strictly equivalent to `FIRST_VALUE IGNORE NULLS` or `LAST_VALUE IGNORE NULLS` over running frames; if you need the most recent non-NULL value at each row, define the frame explicitly and construct a tailored query.

## 11. `NTH_VALUE()` and FROM FIRST / FROM LAST direction

Semantically, `NTH_VALUE(expr, N)` retrieves the Nth position counting from the start of the frame. MySQL supports counting from the start (`FROM FIRST`, which is also the default); `FROM LAST` is not supported. To count from the end, reverse the ordering inside the window:

```sql
SELECT
    id,
    team,
    score,
    NTH_VALUE(score, 2) OVER (
        PARTITION BY team
        ORDER BY scored_at DESC, id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS second_score_from_latest
FROM employee_scores
ORDER BY team, scored_at, id;
```

The frame still spans the entire partition, but the reversed order makes the second row from the start in descending order equal to the second-to-last element in ascending order.

Do not confuse `NTH_VALUE()` with `ROW_NUMBER() = N`:

- `NTH_VALUE()` returns a value and can repeat across multiple rows.
- `ROW_NUMBER()` assigns a sequence number to each row.
- `NTH_VALUE()` depends on the frame; `ROW_NUMBER()` depends on partition/order and does not use a frame.

If you only need to filter out the exact Nth row, using `ROW_NUMBER()` in a CTE or derived table is usually clearer.

## 12. Comparing value window functions with MIN/MAX

`FIRST_VALUE()` does not mean `MIN()`, and `LAST_VALUE()` does not mean `MAX()`.

Example:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_by_time,
    MIN(score) OVER (
        PARTITION BY team
    ) AS minimum_score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_by_time,
    MAX(score) OVER (
        PARTITION BY team
    ) AS maximum_score
FROM employee_scores
ORDER BY team, scored_at, id;
```

- `FIRST_VALUE` retrieves the score from the chronologically first event, even if that score is not the minimum.
- `MIN` retrieves the smallest numeric value, regardless of chronological order.
- `LAST_VALUE` retrieves the score from the chronologically last event, even if that score is not the maximum.
- `MAX` retrieves the largest numeric value, regardless of chronological order.

Choose the function matching the business question: "value at the first/last event" uses a value window function; "smallest/largest value" uses an aggregate.

## 13. Combining multiple value functions in one query

A report may need the first, second, and last score for each team:

```sql
SELECT
    id,
    team,
    scored_at,
    score,
    FIRST_VALUE(score) OVER w_full AS first_score,
    NTH_VALUE(score, 2) OVER w_full AS second_score,
    LAST_VALUE(score) OVER w_full AS last_score
FROM employee_scores
WINDOW w_full AS (
    PARTITION BY team
    ORDER BY scored_at, id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
ORDER BY team, scored_at, id;
```

The named window `w_full` avoids repeating partition, ordering, and frame clauses. All three functions use the exact same definition, making results easy to compare. If one function needs a different frame, declare a separate window rather than forcing an unsuitable shared frame.

## 14. Filtering by window function results

Window functions are evaluated after the row-filtering stages of a query block. You cannot use a window function alias directly in `WHERE` at the same level:

```sql
-- Invalid within the same query block:
-- SELECT ..., ROW_NUMBER() OVER (...) AS rn
-- FROM employee_scores
-- WHERE rn = 1;
```

Wrap it in a CTE or derived table:

```sql
WITH team_endpoints AS (
    SELECT
        id,
        team,
        scored_at,
        score,
        FIRST_VALUE(score) OVER (
            PARTITION BY team
            ORDER BY scored_at, id
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS first_score,
        LAST_VALUE(score) OVER (
            PARTITION BY team
            ORDER BY scored_at, id
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS last_score,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY scored_at DESC, id DESC
        ) AS latest_row_number
    FROM employee_scores
)
SELECT team, first_score, last_score
FROM team_endpoints
WHERE latest_row_number = 1;
```

The outer query retains only the latest row for each team while retrieving both the first and last values computed across the partition. This also avoids repeating window expressions in the filter.

## 15. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming `LAST_VALUE()` always returns partition end | Result is usually just the current row under the default frame | Specify `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. |
| Omitting `ORDER BY` when first/last/Nth is needed | Nondeterministic ordering | Sort by business columns and add a unique tie-breaker. |
| Using a non-unique `ORDER BY` | Results across peers may be unstable | Add a unique key if deterministic row order is required. |
| Confusing `RANGE` with `ROWS` | Peer-based frames and row-count frames behave differently | Choose the frame unit matching the required semantics. |
| Using `NTH_VALUE()` without checking the frame | NULL at the start of partition or when frame has fewer than N rows | Widen the frame appropriately or check frame row count. |
| Assuming NULL from `NTH_VALUE()` always means missing rows | Misses the case where the Nth row exists with a NULL expression | Check both frame row count and expression value. |
| Expecting `IGNORE NULLS` to work in MySQL | Query is unsupported | Use `RESPECT NULLS` or write a custom query to skip NULLs. |
| Using `FROM LAST` in `NTH_VALUE()` | Incompatible with MySQL | Reverse `ORDER BY` and use default counting from the start. |
| Using `MIN()` instead of `FIRST_VALUE()` | Returns smallest value instead of first row's value | Distinguish row ordering from value magnitude. |
| Assuming window ORDER BY sorts final output | Client receives rows in an unguaranteed order | Add `ORDER BY` to the outermost query block. |
| Using window alias in same-level WHERE | Error due to SQL evaluation order | Wrap the query in a CTE or derived table. |

## 16. Performance and plan inspection

Value window functions require knowing the partition, ordering, and frame. Depending on the frame and execution plan, MySQL may need to sort or buffer partition rows. A full-partition frame with `UNBOUNDED FOLLOWING` may need to read through the end of the partition before determining the final value for earlier rows.

Window functions are supported in MySQL 8.0 and later; MySQL 5.7 does not support `OVER (...)` syntax. Check the version before deploying:

```sql
SELECT VERSION();
```

Practical guidelines:

1. Select only necessary columns in the query block containing window functions.
2. Reduce input rows with business-valid filter predicates before evaluating windows.
3. Use appropriate `PARTITION BY` keys so the whole table is not processed as one partition unnecessarily.
4. Use deterministic ordering, while avoiding adding columns that alter peer semantics when ties are required.
5. Evaluate indexes ordered as `(partition_columns, order_columns)`; indexes can assist access/sorting, though they do not guarantee eliminating every sort or materialization step.
6. Avoid recomputing the same window across multiple query blocks when a named window or well-structured CTE suffices.
7. Measure with `EXPLAIN` on realistic data.

For the practice table, the index `(team, scored_at, id)` aligns with partitioning by team and ordering by timestamp/id. Inspect the query:

```sql
EXPLAIN
SELECT
    id,
    team,
    scored_at,
    score,
    LAST_VALUE(score) OVER (
        PARTITION BY team
        ORDER BY scored_at, id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_score
FROM employee_scores;
```

Where supported, `EXPLAIN ANALYZE` reports actual iterator timings, though it executes the query. Run it in a safe environment if partitions are large or queries may consume significant resources.

## 17. Practice exercises

### Exercise A — FIRST_VALUE and LAST_VALUE

1. Create the `employee_scores` table and load the fixture.
2. Compute `FIRST_VALUE(score)` per team.
3. Run `LAST_VALUE(score)` without declaring a frame.
4. Re-run with a full-partition frame.
5. Explain why the two LAST_VALUE results differ.

### Exercise B — NTH_VALUE and frames

1. Compute `NTH_VALUE(score, 2)` across the entire partition.
2. Remove the frame to observe the default frame.
3. Compute `NTH_VALUE(score, 3)` within a three-row sliding frame.
4. Observe NULL results at the beginning of a partition.
5. Distinguish NULL due to fewer than N rows from NULL stored in the Nth row's value.

### Exercise C — ROWS and RANGE

1. Create `score_events_tied` with two rows sharing the same timestamp.
2. Compare cumulative frames using `ROWS` and `RANGE`.
3. Observe peer groups and nondeterministic behavior without a tie-breaker.
4. Add `id` to ORDER BY and explain how the peer group changes.

### Exercise D — NULLs and elements from the end

1. Observe `FIRST_VALUE()` and `LAST_VALUE()` on team Beta.
2. Try writing `RESPECT NULLS` explicitly.
3. Confirm that `IGNORE NULLS` is not supported in MySQL.
4. Use `ROW_NUMBER()` over a NULL-filtered set to find the first/last non-null score.
5. Use NTH_VALUE with descending ORDER BY to retrieve the second-to-last element.

### Exercise E — Reporting and performance

1. Create a named window for the full partition.
2. Compute the first, second, and last scores in the same query.
3. Filter the latest row using a CTE and `ROW_NUMBER()`.
4. Run `EXPLAIN` with index `(team, scored_at, id)`.
5. Record differences in results, rows processed, and cost when changing frames.

You have completed this lesson when you can explain each row's frame, avoid the default `LAST_VALUE()` trap, choose `ROWS`/`RANGE` accurately, handle peers and NULLs intentionally, and use `NTH_VALUE()` at the right position within a frame.

## 18. Key principles to remember

- `FIRST_VALUE()`, `LAST_VALUE()`, and `NTH_VALUE()` read values from the current frame; they do not collapse a partition into one row.
- `PARTITION BY` groups rows, `ORDER BY` defines ordering, and the frame defines which rows the function can see.
- With `ORDER BY` and no explicit frame, MySQL defaults to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.
- `LAST_VALUE()` therefore typically returns the last value of the current frame; use `UNBOUNDED FOLLOWING` if partition end is needed.
- `NTH_VALUE(expr, N)` counts positions from the start of the frame; if the frame has fewer than N rows or that position holds NULL, the result is NULL.
- `ROWS` counts rows by position; `RANGE` includes peer rows sharing the same ORDER BY value at the CURRENT ROW boundary.
- Add a unique tie-breaker when per-row determinism is needed; omit it if it would break required peer-group semantics.
- MySQL supports `RESPECT NULLS`; `IGNORE NULLS` and `NTH_VALUE ... FROM LAST` are not supported.
- To count Nth from the end, reverse ORDER BY and use NTH_VALUE from the start.
- `FIRST_VALUE` is not `MIN`, and `LAST_VALUE` is not `MAX`; choose based on row position vs. value magnitude.
- Window ORDER BY does not sort final output; use an outer ORDER BY when needed.
- Use a CTE/derived table to filter window results and `EXPLAIN` to verify cost.

When partition, ordering, and frame are defined accurately, these three value window functions let queries retrieve first, last, and Nth milestones consistently. Explicit frame declarations, intentional peer/NULL handling, and execution plan checks ensure reports accurately reflect the data as row counts and complexity grow.
