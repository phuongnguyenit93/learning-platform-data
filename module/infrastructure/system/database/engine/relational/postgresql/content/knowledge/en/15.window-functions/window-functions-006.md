# ROWS, RANGE, GROUPS, and Window Frame Boundaries in PostgreSQL

Window functions allow you to compute running totals, moving averages, rankings, contribution ratios, and comparisons against neighboring rows without **losing individual detail rows** like standard `GROUP BY`. However, when you write `SUM(...) OVER (...)` or `LAST_VALUE(...) OVER (...)`, the result does not depend solely on `PARTITION BY` and `ORDER BY`. Another critical component is the **window frame**.

Imagine you have sales events:

```text
Relative day   | Event   | Revenue
---------------+---------+---------
1              | A       | 10
2              | B       | 20
2              | C       | 30
4              | D       | 40
4              | E       |  5
8              | F       | 50
```

Standing at event D (day 4), the phrase "the last two units" has at least three interpretations:

- **The last two rows:** rows C and D, giving sum 30 + 40 = **70**, assuming a deterministic row order.
- **Events within the last two days:** can cover days 2, 3, 4—namely rows B, C, D, E with sum **95**, depending on the specified value interval.
- **The last two date groups:** day 2's group and day 4's group, also comprising B, C, D, E in this dataset (sum **95**), yet diverging from a two-day interval whenever gaps exist between dates.

In PostgreSQL, those three models are expressed with `ROWS`, `RANGE`, and `GROUPS` respectively. The differences stand out sharply when `ORDER BY` has **multiple rows sharing equal values** or when timestamps/numbers have **uneven spacing**.

This lesson explains frame syntax, the boundaries `UNBOUNDED PRECEDING`, `CURRENT ROW`, `n PRECEDING`, `n FOLLOWING`, `UNBOUNDED FOLLOWING`, `EXCLUDE` options, default frames, impact on `LAST_VALUE`, and how to design stable, verifiable queries.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish **partition**, **row ordering**, and **frame** within a window function call.
2. Understand **peer groups**—groups of rows tied across all `ORDER BY` expressions.
3. Use `ROWS` for frames based on **row count**.
4. Use `RANGE` for frames based on **sort key values**, including numeric and `INTERVAL` offsets.
5. Use `GROUPS` for frames based on **number of peer groups**.
6. Write frame starts/ends using `UNBOUNDED PRECEDING`, `CURRENT ROW`, preceding/following offsets, and `UNBOUNDED FOLLOWING`.
7. Explain behavior when no frame is written: default frames, peers, and running sum outcomes.
8. Use `EXCLUDE CURRENT ROW`, `EXCLUDE GROUP`, `EXCLUDE TIES`, and `EXCLUDE NO OTHERS`.
9. Distinguish **frame-sensitive** functions like `SUM`, `AVG`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` from functions driven primarily by partition and ordering like `ROW_NUMBER`, `RANK`, `LAG`, `LEAD`.
10. Handle empty frames, `NULL`s, non-deterministic ordering on ties, timestamps, and time zones.
11. Write queries for running totals, moving averages, two-sided windows, and peer-group totals.
12. Read `EXPLAIN` to identify sort/window steps and evaluate indexes properly.

**Scope:** Syntax and examples use modern PostgreSQL supporting `GROUPS` and `EXCLUDE`; when running on older versions, verify version support. Statements creating/dropping data in this lesson should be run only in a **practice database**.

---

## 2. Quick review: window functions preserve each row

General syntax:

```sql
SELECT
    column_name,
    window_function(...) OVER (
        PARTITION BY partition_columns
        ORDER BY sort_columns
        frame_clause
    ) AS metric
FROM some_table;
```

Components:

- **`PARTITION BY`**: splits input rows into independent sets, e.g., rows per account.
- **`ORDER BY` inside `OVER`**: defines the logical order **within each partition**.
- **Frame clause**: selects a subset of the partition, relative to the current row, for frame-sensitive functions to evaluate over.
- **Window function**: uses the frame or partition/order to produce a result **for each row**.

Conceptual example:

```sql
SELECT
    account_id,
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
    ) AS account_total
FROM events;
```

Every individual event remains visible, while each `account_id` row gains the account's overall total.

Contrast with:

```sql
SELECT account_id, SUM(amount)
FROM events
GROUP BY account_id;
```

because `GROUP BY` collapses rows into **one row per account**, whereas a window function **does not collapse** detail rows.

### 2.1. Partition differs from frame

Suppose account A has six rows and account B has four rows.

`PARTITION BY account_id` creates two partitions: A and B. Then, for **each row** in A, a frame may contain one row, three rows, same-day rows, or all of A depending on its declaration.

In other words:

```text
Table after WHERE/GROUP BY/HAVING
              |
       PARTITION BY
              |
    +---------+---------+
    |                   |
 Account A            Account B
    |                   |
 ORDER BY             ORDER BY
    |                   |
 For each row         For each row
 take FRAME           take FRAME
    |                   |
 Evaluate window      Evaluate window
 function             function
              |
       Return result rows
```

A frame **never crosses partition boundaries**; preceding/following offsets look only at rows within the corresponding partition.

### 2.2. ORDER BY inside OVER vs. ORDER BY at the end of SELECT

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        ORDER BY event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM some_table
ORDER BY amount DESC;
```

`ORDER BY event_id` inside `OVER` controls the order for **calculating the running total**. `ORDER BY amount DESC` at the outermost level only sorts the displayed output. One does not substitute for the other.

For consistent display order, include an outer-level `ORDER BY` even when `OVER` already specifies `ORDER BY`.

---

## 3. Complete syntax of a window frame

A window frame takes the form:

```sql
OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Three primary frame units:

```sql
ROWS
RANGE
GROUPS
```

General syntax:

```sql
{ ROWS | RANGE | GROUPS }
BETWEEN frame_start AND frame_end
[ frame_exclusion ]
```

Or shorthand form:

```sql
{ ROWS | RANGE | GROUPS } frame_start
[ frame_exclusion ]
```

For example:

```sql
ROWS UNBOUNDED PRECEDING
```

is equivalent to:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

When `frame_end` is omitted in standard shorthand form, the default endpoint is `CURRENT ROW`.

### 3.1. Common boundary types

| Boundary | Directional meaning |
| --- | --- |
| `UNBOUNDED PRECEDING` | Starts from the beginning of the partition |
| `n PRECEDING` | Steps back n rows / peer groups / value units depending on frame type |
| `CURRENT ROW` | Current row or current peer group depending on frame type |
| `n FOLLOWING` | Steps ahead n rows / peer groups / value units |
| `UNBOUNDED FOLLOWING` | Ends at the end of the partition |

In `BETWEEN` syntax, PostgreSQL requires the start and end bounds to follow a valid order. For instance, you cannot put `UNBOUNDED FOLLOWING` as the start bound, or `UNBOUNDED PRECEDING` as the end bound.

### 3.2. Important patterns

| Frame | Idea |
| --- | --- |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` | Row-by-row running total from partition start |
| `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` | Up to three rows: two preceding plus current row |
| `ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING` | Previous, current, and next row |
| `ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING` | From current row to partition end |
| `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Entire partition |
| `RANGE BETWEEN 5 PRECEDING AND CURRENT ROW` | Sort key within the specified value range |
| `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` | Previous peer group and current peer group |

**Never read "2 PRECEDING" identically across all three frame units.** The keyword `ROWS`, `RANGE`, or `GROUPS` determines what "2" counts.

---

## 4. Practice dataset with peers and gaps

To expose the differences, we intentionally include **multiple events on the same day** and **days with no events**.

> The `DROP TABLE IF EXISTS` statements below drop any practice table with the same name. Run only in a dedicated test database, never to reset production data.

### 4.1. Creating the schema and table

```sql
CREATE SCHEMA IF NOT EXISTS window_frame_lab;

DROP TABLE IF EXISTS window_frame_lab.events;

CREATE TABLE window_frame_lab.events (
    event_id INTEGER PRIMARY KEY,
    account_id TEXT NOT NULL,
    day_no INTEGER NOT NULL CHECK (day_no > 0),
    event_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    note TEXT NOT NULL
);
```

Here:

- `event_id` is a unique key providing a tie-breaker for **row-by-row** ordering.
- `day_no` is a numeric key with **duplicate values**, suitable for `RANGE` examples with numeric offsets.
- `event_at` illustrates time intervals using `INTERVAL`.
- `account_id` lets us observe `PARTITION BY`.
- `amount` is the metric being aggregated.

### 4.2. Loading data

```sql
INSERT INTO window_frame_lab.events (
    event_id, account_id, day_no, event_at, amount, note
)
VALUES
    (101, 'A', 1, '2026-01-01 09:00:00+00', 10.00, 'A day 1'),
    (102, 'A', 2, '2026-01-02 09:00:00+00', 20.00, 'A day 2 / 1'),
    (103, 'A', 2, '2026-01-02 09:00:00+00', 30.00, 'A day 2 / 2'),
    (104, 'A', 4, '2026-01-04 09:00:00+00', 40.00, 'A day 4 / 1'),
    (105, 'A', 4, '2026-01-04 09:00:00+00',  5.00, 'A day 4 / 2'),
    (106, 'A', 8, '2026-01-08 09:00:00+00', 50.00, 'A day 8'),
    (201, 'B', 1, '2026-01-01 09:00:00+00',  7.00, 'B day 1'),
    (202, 'B', 3, '2026-01-03 09:00:00+00',  8.00, 'B day 3 / 1'),
    (203, 'B', 3, '2026-01-03 09:00:00+00',  9.00, 'B day 3 / 2'),
    (204, 'B',10, '2026-01-10 09:00:00+00', 10.00, 'B day 10');
```

Inspect:

```sql
SELECT event_id, account_id, day_no, amount
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Logical contents:

| Account | Day | Event | Amount |
| --- | ---: | ---: | ---: |
| A | 1 | 101 | 10 |
| A | 2 | 102 | 20 |
| A | 2 | 103 | 30 |
| A | 4 | 104 | 40 |
| A | 4 | 105 | 5 |
| A | 8 | 106 | 50 |
| B | 1 | 201 | 7 |
| B | 3 | 202 | 8 |
| B | 3 | 203 | 9 |
| B | 10 | 204 | 10 |

Account A total = **155**, account B total = **34**.

### 4.3. Peer groups

When writing:

```sql
ORDER BY day_no
```

events sharing the same `day_no` within the same partition are **peers**—tied rows:

```text
Account A, ORDER BY day_no:

Peer group #1: day_no = 1 -> [101]           sum 10
Peer group #2: day_no = 2 -> [102, 103]      sum 50
Peer group #3: day_no = 4 -> [104, 105]      sum 45
Peer group #4: day_no = 8 -> [106]           sum 50
```

Conversely, if you write:

```sql
ORDER BY day_no, event_id
```

each row has a distinct sort key pair in this dataset. Thus **each peer group shrinks to a single row**.

This is a major principle: **peer groups are determined by the entire `ORDER BY` expression list of the window**, not by a column named "group", `INSERT` order, or the table's primary key.

---

## 5. ROWS: counting individual rows

`ROWS` uses **row position** in the partition's ordering to define the frame.

Example:

```sql
SELECT
    event_id,
    account_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_last_two_rows
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

The frame includes the **current row and at most one immediately preceding row** within the same account.

For account A:

| Event | Amount | Frame in `(day_no,event_id)` order | SUM |
| ---: | ---: | --- | ---: |
| 101 | 10 | [101] | 10 |
| 102 | 20 | [101,102] | 30 |
| 103 | 30 | [102,103] | 50 |
| 104 | 40 | [103,104] | 70 |
| 105 | 5 | [104,105] | 45 |
| 106 | 50 | [105,106] | 55 |

Notice day 2 and day 4 have multiple events; `ROWS` still strictly counts **rows**, without merging rows sharing the same day.

### 5.1. Why use a tie-breaker?

With only:

```sql
ORDER BY day_no
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

the ordering between events 102 and 103, and between 104 and 105, is **not uniquely determined**.

One query execution might place 102 before 103; another plan/circumstance might place 103 before 102. With `ROWS`, that changes which row is "1 PRECEDING", altering `SUM`/`AVG`.

To produce **reproducible results**, add a tie-breaker key:

```sql
ORDER BY day_no ASC, event_id ASC
```

If business logic defines a real event order, pick a **business-meaningful tie-breaker** (high-resolution timestamp, sequence, or stable ID) rather than blindly assuming arbitrary IDs match chronological order.

### 5.2. ROWS for a per-row running total

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Account A result:

| Event | Amount | Running SUM |
| ---: | ---: | ---: |
| 101 | 10 | 10 |
| 102 | 20 | 30 |
| 103 | 30 | 60 |
| 104 | 40 | 100 |
| 105 | 5 | 105 |
| 106 | 50 | 155 |

Here there is no "jump" sharing one value across an entire peer group: each step adds strictly the next individual row.

### 5.3. ROWS for an N-row moving average

Compute the average of **up to the three most recent sales**, including the current sale:

```sql
SELECT
    event_id, day_no, amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS average_last_three_events,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS observations_in_frame
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

On the first two rows, the frame has fewer than three rows, so `AVG` divides by the **number of available rows**. It does not synthesize zero-value filler rows.

At event 104, the three rows in the frame are 102, 103, 104: average `(20+30+40)/3 = 30`.

**When to use ROWS?** When business logic specifies **N records**, **N transactions**, **N measurements**, or a deterministic event sequence, rather than N calendar days.

---

## 6. RANGE: value intervals in ORDER BY

`RANGE` defines the frame by **values of the sort expression**, not row counts. With `RANGE BETWEEN n PRECEDING AND CURRENT ROW`, `n` is a **distance in the key's value domain**, not a row count.

Example using numeric column `day_no`:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS sum_recent_day_range
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 104 (day 4), `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW` captures rows whose `day_no` falls in **[2,4]**, comprising 102, 103, 104, 105; sum **95**.

At event 106 (day 8), the range is **[6,8]**, containing only event 106, sum **50**. It **does not step back two populated date groups** to grab day 4 and day 2.

### 6.1. RANGE includes all peers at CURRENT ROW

When using:

```sql
ORDER BY day_no
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

the endpoint `CURRENT ROW` in `RANGE` mode does not necessarily stop at the **current physical row**. It includes **all peers sharing the exact same sort value as the current row**.

For account A:

- At event 102 (day 2), the frame covers events 101, 102, 103; sum **60**.
- At event 103 (also day 2), the frame still covers 101, 102, 103; sum **60**.
- At event 104 (day 4), the frame covers 101..105; sum **105**.
- At event 105 (day 4), the sum remains **105**.

Thus `RANGE` with `CURRENT ROW` can produce **identical results across an entire peer group**.

### 6.2. RANGE requires care with offset types

When a `RANGE` frame uses an offset like `2 PRECEDING` or `1 FOLLOWING`, PostgreSQL requires a matching `ORDER BY` structure: **a single sort expression**, with an offset type compatible with distance arithmetic on that expression.

Valid conceptual examples:

```sql
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

or with timestamps:

```sql
ORDER BY event_at
RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW
```

Do not write `RANGE ... 2 PRECEDING` on a timestamp key expecting `2` to mean two days. PostgreSQL requires a compatible `INTERVAL` type.

### 6.3. Do not use multiple ORDER BY keys when RANGE has an offset

An important syntax restriction in PostgreSQL: `RANGE` with `offset PRECEDING/FOLLOWING` requires strictly one `ORDER BY` expression.

Invalid conceptual example:

```sql
-- NOT VALID: RANGE offset with two ORDER BY keys.
SUM(amount) OVER (
    ORDER BY day_no, event_id
    RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

Because "step back two units" has no single scalar meaning when the sort key is a two-component tuple.

To preserve day grouping and day distance, use:

```sql
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

If business logic needs exact per-event ordering, consider `ROWS` with a secondary key.

### 6.4. RANGE with DESC ordering

`PRECEDING`/`FOLLOWING` indicate direction **in `ORDER BY` order**, not absolute numeric increase/decrease.

Example:

```sql
ORDER BY day_no DESC
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Under descending sort, values preceding the current day are **larger day numbers**, not smaller ones. Thus "2 PRECEDING" looks toward higher values on the number line.

When writing rolling time-series queries, explicitly use `ORDER BY event_at ASC` when the intent is "timestamps prior to the current timestamp".

---

## 7. GROUPS: counting peer groups

`GROUPS` defines the frame by **number of peer groups**, where each group contains rows sharing identical `ORDER BY` values.

Example:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS sum_current_and_previous_day_group
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Peer groups of A:

```text
G1: day 1 -> [101]      sum=10
G2: day 2 -> [102,103]  sum=50
G3: day 4 -> [104,105]  sum=45
G4: day 8 -> [106]      sum=50
```

`GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`:

- At G1: G1 only → **10**.
- At G2: G1 + G2 → **60**.
- At G3: G2 + G3 → **95**.
- At G4: G3 + G4 → **95**.

All rows in the same peer group receive the **same frame** in this `EXCLUDE`-free example.

### 7.1. Key difference compared to RANGE

On day 8:

- `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW` → spans days 6..8, containing only day 8 → **50**.
- `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` → spans the **last two active day groups**: day 4 and day 8 → **45 + 50 = 95**.

These represent two different business questions:

- "Sales over the **last three calendar days**" → `RANGE` frame by day or timestamp.
- "Sales from the **two most recent recorded trading days**" → `GROUPS` over actual appearing day groups.

Never pick `GROUPS` just because the table has a date column. Identify which unit the business actually wants to count.

### 7.2. GROUPS requires ORDER BY

To know which group comes "before" or "after", peer groups must be ordered. Hence PostgreSQL requires `ORDER BY` when using `GROUPS`.

Appropriate example:

```sql
GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
```

paired with:

```sql
ORDER BY day_no
```

If data must be grouped by month, either aggregate by month first or put a month expression inside `ORDER BY`. Understand that offsets count **ordered expression groups**, without inherently knowing business calendars.

### 7.3. GROUPS can combine multiple sort columns

Unlike `RANGE` with an offset, `GROUPS` accepts multiple `ORDER BY` expressions; peer groups are defined by the **entire tuple of values**.

Example:

```sql
ORDER BY day_no, event_id
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

Because `event_id` is unique in the lab, every group shrinks to one row. In that case `GROUPS 1 PRECEDING` yields the same scope as `ROWS 1 PRECEDING` in that order, yet it was **adding the second key** that changed the peer groups.

If the goal is grouping by day, use `ORDER BY day_no` alone for the `GROUPS` frame.

---

## 8. Comparing ROWS, RANGE, and GROUPS on the same dataset

This is the centerpiece query of the lesson:

```sql
SELECT
    event_id,
    day_no,
    amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS last_two_rows,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_two_value_units,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS last_two_peer_groups

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Expected result:

| Event | Day | Amount | ROWS: 1 preceding | RANGE: 2 value units back | GROUPS: 1 group back |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 10 | 10 | 10 | 10 |
| 102 | 2 | 20 | 30 | 60 | 60 |
| 103 | 2 | 30 | 50 | 60 | 60 |
| 104 | 4 | 40 | 70 | 95 | 95 |
| 105 | 4 | 5 | 45 | 95 | 95 |
| 106 | 8 | 50 | 55 | 50 | 95 |

Quick explanation:

- At event **102**: `ROWS` sees 101, 102 → 30; `RANGE` days [0,2] sees 101, 102, 103 → 60; `GROUPS` sees day 1 and 2 → 60.
- At event **104**: `ROWS` sees 103, 104 → 70; `RANGE` days [2,4] sees all four rows of days 2 and 4 → 95; `GROUPS` sees the two peer groups day 2 and 4 → 95.
- At event **106**: `ROWS` sees 105, 106 → 55; `RANGE` days [6,8] sees 106 → 50; `GROUPS` sees days 4 and 8 → 95.

**Note on ORDER BY:** the `ROWS` column includes `event_id` for deterministic row-by-row order; `RANGE`/`GROUPS` use only `day_no` to preserve day peer groups. All three windows are thus **deliberately defined differently**. Adding `event_id` to `RANGE`/`GROUPS` would alter peer groups, and `RANGE` with an offset rejects multiple `ORDER BY` keys.

---

## 9. The CURRENT ROW boundary does not always mean the same thing

A frequent mistake is reading:

```sql
... BETWEEN CURRENT ROW AND CURRENT ROW
```

as "strictly the current row" in every context.

In reality:

| Frame type | `CURRENT ROW` when acting as start/end boundary |
| --- | --- |
| `ROWS` | Exact position of the **current row** |
| `RANGE` | Start/end edge of the **current peer group** |
| `GROUPS` | Start/end edge of the **current peer group** |

Try:

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_row_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_range_peer_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_group_amount

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 102:

- `ROWS` current/current → event 102 only → **20**.
- `RANGE` current/current → entire day 2 group: events 102 + 103 → **50**.
- `GROUPS` current/current → entire day 2 group → **50**.

At event 104:

- `ROWS` → **40**.
- `RANGE` and `GROUPS` → day 4 group: 40 + 5 = **45**.

### 9.1. Frames starting at CURRENT ROW

Example:

```sql
ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

means from the current row to the end of the partition.

In:

```sql
RANGE BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
```

the start point is the **first peer of the current row**, so peer rows appearing earlier in physical order can still be pulled into the frame. When you need "from the current event onward" event by event, use `ROWS` with a tie-broken ordering.

---

## 10. Default frame: a frequent cause of unexpected results

When `ORDER BY` is present inside `OVER` yet **no frame is declared**, PostgreSQL uses a default frame semantically equivalent to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

It spans from partition start to the **last peer of the current row**.

Example:

```sql
SELECT
    event_id,
    day_no,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS default_running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Result:

| Event | Day | Amount | SUM with default frame |
| ---: | ---: | ---: | ---: |
| 101 | 1 | 10 | 10 |
| 102 | 2 | 20 | 60 |
| 103 | 2 | 30 | 60 |
| 104 | 4 | 40 | 105 |
| 105 | 4 | 5 | 105 |
| 106 | 8 | 50 | 155 |

This differs from a row-by-row running total because peers are **summed at the same logical step**.

### 10.1. Without ORDER BY, what is the default frame?

If `ORDER BY` is omitted inside `OVER`, all rows in the partition are treated as peers of one another in the default context, so the frame spans the **entire partition**.

Example:

```sql
SELECT
    event_id,
    account_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
    ) AS full_account_sum
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

Every account A row gets `full_account_sum = 155`; every account B row gets `full_account_sum = 34`.

Never glance at `SUM OVER(...)` and assume it is always a running sum. **Whether `ORDER BY` is present** and **how the frame is declared** determine the calculation.

### 10.2. Declare frames explicitly when business logic is sensitive

For a **row-by-row** running total, write explicitly:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

For an entire-partition total:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

or more simply:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
)
```

For cumulative sums by **day/peer**, the default `RANGE` frame may be exactly what you want, though documenting the intent in query comments is good practice.

---

## 11. Full-partition frames and CURRENT ROW to end

### 11.1. Entire partition

```sql
SELECT
    event_id,
    account_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS account_total
FROM window_frame_lab.events
ORDER BY account_id, day_no, event_id;
```

All A rows receive 155; all B rows receive 34.

Unlike `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, the frame does not grow row by row; it spans **start to end of the partition** at every position.

### 11.2. Sum from the current row to the end

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
    ) AS remaining_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

For A:

| Event | remaining_sum |
| ---: | ---: |
| 101 | 155 |
| 102 | 145 |
| 103 | 125 |
| 104 | 95 |
| 105 | 55 |
| 106 | 50 |

This can compute remaining value **starting from the current event**, rather than cumulative value prior to the event.

### 11.3. Excluding the current row to sum strictly past rows

If you only want the sum of **rows strictly preceding the current event**:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND 1 PRECEDING
    ) AS sum_before_current
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 101, the frame is empty → `SUM` returns **NULL**, not 0; at event 102, the prior sum is 10.

If business rules call for displaying 0 when no prior data exists:

```sql
COALESCE(
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND 1 PRECEDING
    ),
    0::NUMERIC
)
```

Converting `NULL` to 0 should always be a deliberate presentation choice.

---

## 12. FOLLOWING: forward-looking windows

`FOLLOWING` offsets let you inspect rows, peer groups, or values **after** the current row.

`ROWS` example:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS sum_next_two_rows
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 101: the next two rows are 102 and 103, sum **50**.

At event 105: only event 106 remains, sum **50**.

At event 106: no rows remain, the frame is empty, and `SUM` returns **NULL**.

### 12.1. Centered moving average around an event

```sql
SELECT
    event_id,
    amount,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS centered_three_row_avg
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

This is a moving average **that peeks into the future**. For retrospective reporting, that can be appropriate; for real-time forecasting models, using future rows causes **data leakage** if those events were not yet known.

### 12.2. FOLLOWING does not always mean future in wall-clock time

`FOLLOWING` strictly means "coming later in `ORDER BY`". If `ORDER BY event_at DESC`, `FOLLOWING` rows are **older** events. Verify sort direction before writing `PRECEDING`/`FOLLOWING` frames.

---

## 13. EXCLUDE: omitting part of a frame

PostgreSQL supports frame exclusion options:

```sql
EXCLUDE NO OTHERS
EXCLUDE CURRENT ROW
EXCLUDE GROUP
EXCLUDE TIES
```

Exclusion applies **after determining the base frame**; it does not alter partition definitions or window ordering.

| Option | Effect |
| --- | --- |
| `EXCLUDE NO OTHERS` | Excludes no additional rows; default |
| `EXCLUDE CURRENT ROW` | Excludes the **current row**, keeping other peers if they fall in the frame |
| `EXCLUDE GROUP` | Excludes the **current row's entire peer group**, including the current row |
| `EXCLUDE TIES` | Excludes **other peers**, while keeping the current row itself |

### 13.1. Lab with RANGE and day 2 peers

Consider event 102, account A:

```text
RANGE frame:
UNBOUNDED PRECEDING ... CURRENT ROW

Initial rows in frame:
event 101, amount 10 (day 1)
event 102, amount 20 (day 2) <- CURRENT ROW
event 103, amount 30 (day 2) <- PEER of 102
Original sum = 60
```

Each option produces:

| Exclusion | Remaining rows for event 102 | SUM |
| --- | --- | ---: |
| NO OTHERS | 101,102,103 | 60 |
| CURRENT ROW | 101,103 | 40 |
| GROUP | 101 | 10 |
| TIES | 101,102 | 30 |

For event 103:

- `EXCLUDE CURRENT ROW` keeps 101 and 102 → 10+20=30.
- `EXCLUDE TIES` keeps 101 and 103 itself → 10+30=40.
- `EXCLUDE GROUP` keeps only 101 → 10.

This demonstrates that **CURRENT ROW and TIES differ**, even when rows share identical sort values.

### 13.2. SQL illustrating all four options

```sql
SELECT
    event_id, day_no, amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE NO OTHERS
    ) AS sum_default,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS sum_without_current,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE GROUP
    ) AS sum_before_peer_group,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        EXCLUDE TIES
    ) AS sum_without_other_peers

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

### 13.3. Empty frame after exclusion

At event 101, it belongs to A's first peer group. With:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
EXCLUDE GROUP
```

the base frame contains only event 101, and exclusion removes the entire day 1 group. **0 rows** remain in the frame.

Then:

- `SUM(amount)` → **NULL**.
- `AVG(amount)` → **NULL**.
- `COUNT(*)` → **0**.

Do not equate "no rows in frame" with "rows having amount equal to 0".

### 13.4. EXCLUDE GROUP also applies to ROWS frames

`EXCLUDE GROUP` still relies on **peers under `ORDER BY`** even when the base frame uses `ROWS`. For example, if `ROWS` spans three rows while multiple peers share the current `ORDER BY` key, exclusion removes any of those peers present in the frame.

Without `ORDER BY`, all rows in the partition count as peers wherever peer identification is needed. Never use `EXCLUDE GROUP` without checking whether it can wipe out the **entire frame**.

### 13.5. Do not confuse EXCLUDE with WHERE

`EXCLUDE CURRENT ROW` does not remove the current row from the **query output**. The row is still returned; only the aggregate/window value for that row is evaluated over the reduced frame.

In contrast, a `WHERE` predicate removes rows from the input of all window functions.

---

## 14. LAST_VALUE: the default frame trap

`LAST_VALUE(expression)` returns the value at the **last row of the current frame**, not implicitly the last row of the entire partition.

This is a very easy trap.

### 14.1. Why does LAST_VALUE often look like the current value?

Try:

```sql
SELECT
    event_id,
    day_no,
    LAST_VALUE(day_no) OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS last_day_in_default_frame
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Because the default frame ends at the **last peer of the current day**, `LAST_VALUE(day_no)` returns the current day (1, 2, 2, 4, 4, 8), **not day 8 on every row**.

### 14.2. To get the partition's last row: specify a full frame

```sql
SELECT
    event_id,
    day_no,
    LAST_VALUE(day_no) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS final_day_in_account
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Now every A row gets day **8**.

If you want `LAST_VALUE(amount)` to be the amount of the **final event**, provide a unique ordering:

```sql
SELECT
    event_id, day_no, amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS final_event_amount
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Every A row gets **50**, the amount of event 106.

### 14.3. FIRST_VALUE also depends on the frame

`FIRST_VALUE` takes the value of the **first row in the frame**. With a frame from partition start to `CURRENT ROW`, it is usually the partition's first value. Yet with a sliding frame:

```sql
SELECT
    event_id, amount,
    FIRST_VALUE(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS first_amount_in_last_three
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

the `FIRST_VALUE` result shifts as the frame start advances.

### 14.4. NTH_VALUE and frames with too few rows

`NTH_VALUE(expression, n)` returns the value of the **nth row in the frame** (1-based). If the frame has fewer than `n` rows, the result is `NULL`.

Example:

```sql
SELECT
    event_id, amount,
    NTH_VALUE(amount, 3) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS third_amount_so_far
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

On the first two rows, the frame has fewer than three rows so the result is `NULL`; from event 103 onward, the third element of the frame is **30**.

Never use `NTH_VALUE` without clearly specifying ordering and frame, especially when peers exist.

---

## 15. Which functions are actually affected by the frame?

Not every function paired with `OVER` reads the frame the same way `SUM` does.

| Function category | Examples | Role of the frame |
| --- | --- | --- |
| Aggregate used as window | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` | **Uses the frame** |
| Frame positional value functions | `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | **Uses the frame** |
| Ranking functions | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `PERCENT_RANK`, `CUME_DIST` | Computed from partition/`ORDER BY`, not narrowed by the frame like aggregates |
| Offset navigation functions | `LAG`, `LEAD` | References positions in partition by `ORDER BY`, not restricted to the aggregate frame |
| Bucketing function | `NTILE` | Assigns buckets over the partition, not frame-dependent like `SUM` |

### 15.1. Example: LAG is not restricted by ROWS CURRENT ROW

```sql
SELECT
    event_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS previous_amount,

    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS current_amount_sum

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 102:

- `LAG(amount)` still returns **10** from event 101 (preceding row in partition).
- `SUM(amount)` evaluates only the current row, returning **20**.

Mistakenly assuming `LAG` searches only inside `CURRENT ROW` leads to wrong predictions.

### 15.2. RANK and DENSE_RANK still rely on peers

```sql
SELECT
    event_id, day_no,
    ROW_NUMBER() OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
    ) AS row_seq,

    RANK() OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS day_rank,

    DENSE_RANK() OVER (
        PARTITION BY account_id
        ORDER BY day_no
    ) AS day_dense_rank

FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

For A:

| Event | Day | ROW_NUMBER | RANK by day | DENSE_RANK by day |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 1 | 1 | 1 |
| 102 | 2 | 2 | 2 | 2 |
| 103 | 2 | 3 | 2 | 2 |
| 104 | 4 | 4 | 4 | 3 |
| 105 | 4 | 5 | 4 | 3 |
| 106 | 8 | 6 | 6 | 4 |

`RANK` leaves gaps after tied groups; `DENSE_RANK` does not. Ties arise from `ORDER BY day_no`, not from the frame.

---

## 16. RANGE with timestamps and INTERVAL

The `INTEGER` column `day_no` helps illustrate offset concepts, while real systems typically use `TIMESTAMP` or `TIMESTAMPTZ`.

With `event_at TIMESTAMPTZ`:

```sql
SELECT
    event_id,
    event_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY event_at
        RANGE BETWEEN INTERVAL '2 days' PRECEDING
                  AND CURRENT ROW
    ) AS amount_last_two_days
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY event_at, event_id;
```

At `2026-01-04 09:00 UTC`, the frame covers events from **`2026-01-02 09:00 UTC`** through the current timestamp, including peer rows sharing the timestamp. Total is **20 + 30 + 40 + 5 = 95**.

At `2026-01-08 09:00 UTC`, only event 106 falls in the trailing two-day window, total 50.

### 16.1. Difference between two days and two events

- `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`: at most **two events**.
- `RANGE BETWEEN INTERVAL '2 days' PRECEDING AND CURRENT ROW`: **all events with timestamps in the interval**—which could be 0, 1, or thousands of events.
- `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` with `ORDER BY event_at`: **the two most recent distinct timestamps with events** (when timestamps align with business grouping).

If every event has microsecond-unique timestamps, `GROUPS` over `event_at` effectively degenerates to counting individual events. To group by **calendar day**, define a proper daily grouping key—usually via daily aggregation or a timezone-aware date expression.

### 16.2. Time zones and daylight saving time

`TIMESTAMPTZ` represents an absolute instant, yet phrases like "yesterday", "this month", or "one calendar day" also depend on a **business time zone**.

For example:

- "Last 48 hours" is an elapsed hour duration.
- "Two local calendar days" can cross a daylight saving transition in some regions and does not always equal 48 hours.

In PostgreSQL, `INTERVAL '1 day'` and `INTERVAL '24 hours'` can behave differently when added to/subtracted from timezone-aware timestamps across DST boundaries depending on context and zone. Always verify time contracts before choosing a `RANGE` frame.

The lab dataset uses UTC, so examples encounter no DST differences.

### 16.3. For calendar-day windows, clarify data grain

Example daily sales report:

```sql
WITH day_totals AS (
    SELECT
        account_id,
        (event_at AT TIME ZONE 'UTC')::DATE AS event_day,
        SUM(amount) AS day_amount
    FROM window_frame_lab.events
    GROUP BY
        account_id,
        (event_at AT TIME ZONE 'UTC')::DATE
)
SELECT
    account_id,
    event_day,
    day_amount,
    SUM(day_amount) OVER (
        PARTITION BY account_id
        ORDER BY event_day
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_three_days_with_activity
FROM day_totals
ORDER BY account_id, event_day;
```

**Note:** after collapsing to one row per active day, `ROWS 2 PRECEDING` means the **last three days that had events**, not three consecutive calendar days if empty days exist.

For three consecutive calendar days, construct a calendar/`generate_series` or use an appropriately defined time-interval `RANGE`.

---

## 17. Difference between GROUPS and a GROUP BY table

Both contain the word "group", causing confusion:

- `GROUP BY day_no` **collapses multiple events into one row per day**.
- `GROUPS ...` in a window frame **does not collapse rows**; it counts peer groups across the input rows while keeping every individual event row.

`GROUP BY` example:

```sql
SELECT
    account_id,
    day_no,
    SUM(amount) AS day_total
FROM window_frame_lab.events
GROUP BY account_id, day_no
ORDER BY account_id, day_no;
```

Account A shrinks to four rows (days 1, 2, 4, 8).

Conversely, when using:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no
    GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
)
```

account A still has **six event rows**. Both day-2 events receive the frame sum 60 without merging into one row.

### 17.1. When to aggregate first and then use ROWS?

If the problem expects **one row per day** (e.g., a daily dashboard), `GROUP BY` day first and then compute rolling metrics over the aggregated daily rows. In that setup, `ROWS` over `day_totals` is often easier to understand.

If the problem must keep **each detailed event** while attaching context from surrounding date groups, `GROUPS` over detailed rows expresses that directly.

This is a choice of **output granularity**, not merely syntax.

---

## 18. GROUPS looking one group back and one group forward

Example:

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
    ) AS neighboring_group_total
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Based on A's day groups 1, 2, 4, 8:

| Current peer group | Groups in frame | Sum |
| --- | --- | ---: |
| Day 1 | Days 1, 2 | 10 + 50 = 60 |
| Day 2 | Days 1, 2, 4 | 10 + 50 + 45 = 105 |
| Day 4 | Days 2, 4, 8 | 50 + 45 + 50 = 145 |
| Day 8 | Days 4, 8 | 45 + 50 = 95 |

For day 2, both events 102 and 103 get 105. For day 4, both events 104 and 105 get 145.

Appropriate uses:

- Comparing a reporting period against the immediately preceding/following **populated** period.
- Building neighborhood metrics around ranked value tiers.
- Measuring sales across adjacent concurrent event clusters.

If the requirement says "one week before and one week after", `GROUPS` **does not understand calendar weeks** unless each group key is explicitly defined by business week.

---

## 19. ROWS and non-deterministic peer ordering

Suppose someone writes:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Someone might spot `ORDER BY day_no,event_id` at the end of `SELECT` and assume `ROWS` follows that exact order too. **False**: the `ROWS` window specifies only `ORDER BY day_no`; between same-day peers, internal order is unconstrained.

To make it deterministic:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

This affects:

- Row-by-row running totals.
- `LAG`/`LEAD`.
- `ROW_NUMBER`.
- Row-based `FIRST_VALUE`/`LAST_VALUE`.
- `ROWS n PRECEDING/FOLLOWING`.

**Never rely on physical disk order, `INSERT` order, or outermost display `ORDER BY` to resolve window peers.**

---

## 20. Partition start/end boundaries and empty frames

Frames can be **truncated** by partition boundaries. For example, `ROWS BETWEEN 4 PRECEDING AND CURRENT ROW` at the first row contains just one row, not five.

### 20.1. COUNT helps observe actual frame size

```sql
SELECT
    event_id,
    amount,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS frame_row_count,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS frame_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

`frame_row_count` returns `1, 2, 3, 3, 3, 3` for A.

### 20.2. What do aggregates return on an empty frame?

Example:

```sql
SELECT
    event_id,
    COUNT(*) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS next_rows_count,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
    ) AS next_rows_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 106:

- `COUNT(*)` = 0.
- `SUM(amount)` = `NULL`.

This is standard aggregate behavior over an **empty set**. Do not confuse it with a frame containing one row with `amount = 0`.

### 20.3. Offset 0 and current-point frames

`ROWS 0 PRECEDING` denotes the current row itself, analogous to `ROWS CURRENT ROW` in simple examples. With `RANGE`/`GROUPS`, offset 0 still interacts with peers; do not use 0 as a trick expecting `RANGE` to collapse to **one physical row**.

Offsets must conform to syntax/type rules, be non-negative, and be non-NULL per PostgreSQL requirements. If an application lets users specify window sizes, validate inputs before constructing SQL.

---

## 21. FILTER combined with frames: conditional calculation inside a window

PostgreSQL supports `FILTER (WHERE ...)` for eligible window aggregates.

Suppose you want to sum `amount` only for events with value at least 20, while still defining the frame over **all events**:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) FILTER (WHERE amount >= 20) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS large_amount_in_last_three_rows
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

Key points:

- The `ROWS` frame still steps across rows ordered by `day_no,event_id`.
- The aggregate only **sums rows inside that frame** satisfying `amount >= 20`.
- Smaller-amount rows still occupy slots inside the three-row window.

Conversely, filtering `WHERE amount >= 20` in the **query before the window** removes small rows from window input altogether so they no longer occupy frame slots, changing the result.

### 21.1. Illustrating the difference

At event 106 (amount 50), the three-row frame is:

```text
104: amount 40
105: amount  5
106: amount 50
```

`SUM(amount) FILTER (WHERE amount >= 20)` over this frame → **40+50=90**.

If `WHERE amount >= 20` removed event 105 beforehand, the three-row frame becomes 103, 104, 106 → **30+40+50=120**.

**Aggregate `FILTER`** and **query `WHERE`** are two distinct stages.

---

## 22. WHERE, GROUP BY, HAVING, and window evaluation position

In SQL's logical evaluation order, window functions receive rows after predicates and grouping in that query block have been applied. Hence you cannot directly use a window function inside `WHERE` of the same query block.

Invalid example:

```sql
-- INVALID: window function inside same-level WHERE.
SELECT event_id, amount
FROM window_frame_lab.events
WHERE ROW_NUMBER() OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
) <= 2;
```

To keep the first two events per account, use a derived table/CTE:

```sql
WITH numbered AS (
    SELECT
        event_id,
        account_id,
        day_no,
        amount,
        ROW_NUMBER() OVER (
            PARTITION BY account_id
            ORDER BY day_no, event_id
        ) AS rn
    FROM window_frame_lab.events
)
SELECT event_id, account_id, day_no, amount
FROM numbered
WHERE rn <= 2
ORDER BY account_id, rn;
```

### 22.1. Windows see data after WHERE

```sql
SELECT
    event_id,
    day_no,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_sum
FROM window_frame_lab.events
WHERE account_id = 'A'
  AND day_no >= 2
ORDER BY day_no, event_id;
```

Here event 101 (day 1) **does not exist in the window's input**, so the running sum starts on day 2 without adding 10 from day 1.

To compute the running total across the **entire account** and then display only from day 2 onward, evaluate the window in a subquery/CTE first and filter in the outer query:

```sql
WITH calculated AS (
    SELECT
        event_id,
        account_id,
        day_no,
        amount,
        SUM(amount) OVER (
            PARTITION BY account_id
            ORDER BY day_no, event_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_sum
    FROM window_frame_lab.events
)
SELECT *
FROM calculated
WHERE account_id = 'A'
  AND day_no >= 2
ORDER BY day_no, event_id;
```

Then event 102 gets `running_sum = 30` because event 101 was included before filtering output.

---

## 23. Frames for running totals under two business interpretations

### 23.1. Running balance immediately after each event

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS after_event_balance
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

The result updates **after every individual event**.

### 23.2. Running total after closing each day

```sql
SELECT
    event_id, day_no, amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS after_day_total
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

The result is identical across events **sharing the same day**.

Using distinct names like `after_event_balance` and `after_day_total` is very helpful. An ambiguous `running_total` column invites debate when readers do not know whether it accumulates **per event** or **per day group**.

---

## 24. When do RANGE and GROUPS coincidentally return the same result?

In A's data, if day groups were spaced exactly 1 unit apart, `RANGE 1 PRECEDING` and `GROUPS 1 PRECEDING` might happen to select the same rows.

Here there is a gap from day 4 to day 8, so they diverge.

Contrast them directly:

```sql
SELECT
    event_id,
    day_no,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        RANGE BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS one_value_unit_back,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS one_peer_group_back
FROM window_frame_lab.events
WHERE account_id = 'A'
ORDER BY day_no, event_id;
```

At event 104 (day 4):

- `RANGE` inspects [3,4] → day 4 group only → **45**.
- `GROUPS` inspects day 2 and day 4 groups → **95**.

If day 3 had an event, `GROUPS` would pick the nearest preceding group (day 3); `RANGE` [3,4] would also pick days 3 and 4. **Matching output on one dataset never proves two frames are equivalent.**

---

## 25. NULL data and peer groups

When `ORDER BY` uses a nullable expression, multiple rows with `NULL` in the sort key are considered peers under that window `ORDER BY` definition.

Structural example:

```sql
SELECT
    event_id,
    score,
    SUM(amount) OVER (
        ORDER BY score NULLS LAST
        GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
    ) AS peer_total
FROM some_table;
```

Here `some_table` is an illustrative table not created in the lab. If multiple rows have `score IS NULL`, they share a peer group positioned according to `NULLS LAST`.

Notes:

- `NULLS FIRST` / `NULLS LAST` controls where the `NULL` group sits.
- `ROWS` with multiple `NULL`-score rows needs a tie-breaker for deterministic row-level ordering.
- `RANGE` offsets on nullable keys have boundary rules worth checking by data type; do not expect arithmetic offset subtraction on `NULL`s to behave like ordinary numbers.
- If `NULL` means "transaction date unknown", decide whether those rows belong in a time-series report or should be separated.

Never blindly use `COALESCE(score,0)` to turn all `NULL`s into 0, as that creates synthetic peer ties and merges missing data with valid zero measurements.

---

## 26. Frames and multi-expression ordering

Suppose you need to sort by `day_no` then `event_id`.

### 26.1. ROWS

```sql
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

can use:

```sql
ORDER BY day_no, event_id
```

to order individual rows unambiguously.

### 26.2. GROUPS

```sql
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

also allows multi-expression ordering, though peer groups are defined by **both `day_no` and `event_id`**. When `event_id` is unique, every group becomes a single row.

### 26.3. RANGE

With `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, PostgreSQL allows multi-expression `ORDER BY` because no scalar offset distance needs to be measured. However, with `RANGE BETWEEN n PRECEDING AND CURRENT ROW`, the offset requires **a single `ORDER BY` key** supporting distance arithmetic.

That explains the difference between:

```sql
-- Multiple keys allowed when not using a value offset.
ORDER BY day_no, event_id
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

and:

```sql
-- With offset 2, use a single numeric key.
ORDER BY day_no
RANGE BETWEEN 2 PRECEDING AND CURRENT ROW
```

Do not append a secondary key to a `RANGE` window's `ORDER BY` merely to sort the final output. To sort the output, use `ORDER BY account_id, day_no, event_id` at the outer `SELECT`.

---

## 27. Using WINDOW to name a window

When multiple calculations share the same partition and ordering, PostgreSQL supports the `WINDOW` clause to reuse the definition.

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER w_rows AS sum_last_three,
    AVG(amount) OVER w_rows AS avg_last_three,
    COUNT(*) OVER w_rows AS count_last_three
FROM window_frame_lab.events
WHERE account_id = 'A'
WINDOW w_rows AS (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY day_no, event_id;
```

Benefits:

- Eliminates verbose repetition of identical frames.
- Guarantees all summary columns inspect the **exact same set of rows**.
- Prevents mismatches where `SUM` uses `ROWS` while `AVG` accidentally falls back to default `RANGE`.

### 27.1. Extending a base window definition

You can define a base window without a frame and append frames individually:

```sql
SELECT
    event_id,
    amount,
    SUM(amount) OVER (
        w ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS row_running_sum,

    AVG(amount) OVER (
        w ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_average

FROM window_frame_lab.events
WHERE account_id = 'A'
WINDOW w AS (
    PARTITION BY account_id
    ORDER BY day_no, event_id
)
ORDER BY day_no, event_id;
```

In PostgreSQL, extending window definitions follows strict rules; **you cannot arbitrarily layer a new frame onto a named window that already specifies a frame**. When multiple frames are needed, define a frame-free base window as shown or declare separate named windows.

---

## 28. Performance: Sort, WindowAgg, and frame size

Window functions may need to sort rows by partition/order before evaluation. On large tables, this can be heavy on CPU, memory, or I/O.

### 28.1. Inspecting EXPLAIN

```sql
EXPLAIN
SELECT
    event_id,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_sum
FROM window_frame_lab.events;
```

To observe actual execution of a `SELECT`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    event_id,
    AVG(amount) OVER (
        PARTITION BY account_id
        ORDER BY day_no, event_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg
FROM window_frame_lab.events;
```

`EXPLAIN ANALYZE` **executes the statement**. Here it is a pure `SELECT`; never run it casually on production DML because it will apply data modifications.

### 28.2. Nodes and metrics to watch

| Node / metric | What it indicates |
| --- | --- |
| `Sort` | PostgreSQL is sorting rows for the window or output |
| `Incremental Sort` | Can exploit partial pre-existing order |
| `WindowAgg` | Node evaluating window expressions |
| `Index Scan` | May leverage ordering from a matching index |
| `Buffers` | Buffer cache / I/O activity |
| `Disk: ...` in sort or temp I/O | Sign of data spilling out of memory |
| `actual rows` | Actual rows flowing through the node |
| `Execution Time` | Measured execution duration |
| `loops` | Number of node iterations reported by instrumentation |

An execution plan depends on PostgreSQL version, data distribution, statistics, configuration, and other windows in the query.

### 28.3. Indexes supporting ordering

Example index:

```sql
CREATE INDEX idx_events_account_day_event
ON window_frame_lab.events (
    account_id,
    day_no,
    event_id
);
```

This index can help queries using:

```sql
PARTITION BY account_id
ORDER BY day_no, event_id
```

especially with an account filter. Still, it **does not guarantee** the planner skips `Sort` or picks `Index Scan`. On the 10-row lab table, sequential scan plus sort can be cheaper.

If workloads use `RANGE`/`GROUPS` on `ORDER BY day_no`, an index prefixed with `(account_id, day_no)` can also be considered. Base index choices on production queries, rather than creating indexes for every experimental frame.

### 28.4. Wide frames and large peer groups

A window with:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

can encounter a peer group spanning millions of rows if the `ORDER BY` key has low cardinality.

A window with:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

likewise depends on the entire partition.

Depending on the function and frame, PostgreSQL may buffer or spool rows to revisit earlier/later partition entries—especially for `LAST_VALUE`/`NTH_VALUE` or far-reaching forward frames. This affects memory usage and temporary disk spills.

Never assume purely from the offset that "`ROWS 2 PRECEDING` definitely uses only three rows of memory" across all plans. Inspect `EXPLAIN (ANALYZE, BUFFERS)` and real memory behavior first.

### 28.5. Semantic equivalence first, optimization second

Swapping `RANGE` for `ROWS` simply because a plan looks faster **changes the business question**. Changing `ORDER BY day_no` to `ORDER BY day_no,event_id` eliminates peer groups.

Any valid optimization must preserve:

- Partition definition.
- Frame unit semantics.
- Peer/tie policy.
- `NULL` and boundary handling.
- Output row count.
- Calculated values on edge-case inputs.

---

## 29. Common mistakes and misconceptions

| Misconception / symptom | Cause | How to understand or fix |
| --- | --- | --- |
| "`ROWS 2 PRECEDING` means two days back." | `ROWS` counts **rows**, not days | Use `RANGE` over date/time values |
| "`GROUPS 2 PRECEDING` means two rows back." | `GROUPS` counts **peer groups** | Inspect the groups formed by `ORDER BY` |
| "`RANGE 2 PRECEDING` means two groups back." | `RANGE` measures **value** distance | If prior groups are needed, choose `GROUPS` |
| "`CURRENT ROW` is always one row." | `RANGE`/`GROUPS` `CURRENT ROW` includes peers | Check the frame unit |
| "Outermost `ORDER BY` governs `ROWS`." | Window `ORDER BY` is independent | Put `ORDER BY` with tie-breakers inside `OVER` |
| "Default `SUM OVER ORDER BY` is per-event running sum." | Default frame is `RANGE` to last peer | Specify `ROWS` explicitly |
| "Without `ORDER BY`, `SUM` still accumulates row by row." | Default frame covers the whole partition | Add `ORDER BY` and the desired frame |
| "`LAST_VALUE` is the partition's last value." | `LAST_VALUE` reads the **frame** end, not always partition end | Specify `UNBOUNDED FOLLOWING` when needed |
| "`LAG` is blocked by `CURRENT ROW` frame." | `LAG` reads positions in the partition | Distinguish frame-sensitive functions |
| "`GROUPS` is the same as `GROUP BY`." | `GROUP BY` collapses detail rows; `GROUPS` does not | Verify desired result granularity |
| "Adding `event_id` to `GROUPS` changes nothing." | Peer groups depend on all `ORDER BY` keys | Keep only intended grouping keys |
| "`RANGE` offset with two `ORDER BY` keys is valid." | PostgreSQL requires one key to measure offset distance | Use one appropriate key |
| "`RANGE` timestamp offset `2` means two days." | Offset requires a compatible type | Use an explicit `INTERVAL` |
| "`DESC PRECEDING` always means smaller values." | `PRECEDING` follows sort direction | Check `ASC`/`DESC` orientation |
| "Sliding frames always contain N rows." | Truncated at partition start/end | Check `COUNT(*) OVER` with the same frame |
| "`SUM` over an empty frame is 0." | `SUM` over zero rows is `NULL` | Use `COALESCE` when business rules call for 0 |
| "`EXCLUDE TIES` removes the current row too." | `TIES` keeps current row, excludes other peers | Distinguish `GROUP`/`TIES`/`CURRENT ROW` |
| "`EXCLUDE GROUP` works only with `GROUPS`." | Exclusion works with all supported frame units | Understand peers under `ORDER BY` |
| "Outer `WHERE` does not affect windows." | Same-block `WHERE` filters input before windowing | Use a CTE if computing first and filtering afterward |
| "`FILTER` and `WHERE` are always equivalent." | `FILTER` limits values aggregated inside frame; `WHERE` drops input rows | Choose which stage should filter |
| "`NULL` rows in `ORDER BY` have no peers." | `NULL` sort keys form a peer group | Specify `NULLS FIRST/LAST` and `NULL` policy |
| "`ROWS` is always faster than `RANGE`." | Performance depends on plan, indexes, and data size | Measure with `EXPLAIN` instead of guessing |
| "Forecasting windows can always use `FOLLOWING`." | `FOLLOWING` leaks future data into predictions | Prevent data leakage relative to decision time |

---

## 30. Practice exercises

### Exercise 1 — Default with ORDER BY

On `window_frame_lab.events`, evaluate:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no
)
```

Predict results for events 102 and 103. Why do both receive 60?

### Exercise 2 — Deterministic cumulative ROWS

Write a **per-event** running total using:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Pair with `ORDER BY day_no,event_id`. For A, the running totals should be 10, 30, 60, 100, 105, 155.

### Exercise 3 — Comparing all three frame units

Compute sums for A with:

1. `ROWS BETWEEN 1 PRECEDING AND CURRENT ROW`.
2. `RANGE BETWEEN 2 PRECEDING AND CURRENT ROW`.
3. `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW`.

Explain why at event 106 the results are **55**, **50**, and **95** respectively.

### Exercise 4 — CURRENT ROW peer groups

Write three columns:

```sql
ROWS BETWEEN CURRENT ROW AND CURRENT ROW
RANGE BETWEEN CURRENT ROW AND CURRENT ROW
GROUPS BETWEEN CURRENT ROW AND CURRENT ROW
```

Why can event 102 return 20, 50, 50 with appropriate `ORDER BY` clauses?

### Exercise 5 — Three-event moving average

Compute `AVG(amount)` over up to the three most recent events, with `event_id` as tie-breaker. Add `COUNT(*)` with the same frame. Why does the first event have only one observation?

### Exercise 6 — Two days vs. two active day groups

At `day_no = 8` for account A:

- Which days does `RANGE 2 PRECEDING` examine?
- Which peer groups does `GROUPS 1 PRECEDING` examine?

Write the SQL and explain why results differ even though both "look backward".

### Exercise 7 — FOLLOWING

Compute the sum of the **next two events**, excluding the current row:

```sql
ROWS BETWEEN 1 FOLLOWING AND 2 FOLLOWING
```

Predict sums at events 101, 105, 106; explain `NULL` on empty frames.

### Exercise 8 — Symmetric group-based frame

Use:

```sql
GROUPS BETWEEN 1 PRECEDING AND 1 FOLLOWING
```

Compute the sum for A's day 2 and day 4 peer groups. Why does day 2 get 105 while day 4 gets 145?

### Exercise 9 — EXCLUDE CURRENT ROW

At event 102, compute the sum in:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
EXCLUDE CURRENT ROW
```

Why is event 103's amount from day 2 still included?

### Exercise 10 — EXCLUDE GROUP and TIES

Use A's day 2 data to compare:

- `EXCLUDE GROUP`.
- `EXCLUDE TIES`.

Explain why for event 102, the sums are 10 and 30 respectively.

### Exercise 11 — LAST_VALUE

Run:

```sql
LAST_VALUE(day_no) OVER (
    PARTITION BY account_id
    ORDER BY day_no
)
```

Then run:

```sql
LAST_VALUE(day_no) OVER (
    PARTITION BY account_id
    ORDER BY day_no
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

Why does the first approach fail to return day 8 for every A event?

### Exercise 12 — LAG with an ultra-narrow frame

Write `LAG(amount)` and `SUM(amount)` with the same frame:

```sql
ROWS BETWEEN CURRENT ROW AND CURRENT ROW
```

At event 102, why does `LAG` still find event 101's amount of 10?

### Exercise 13 — FILTER vs. WHERE

Sum amounts >= 20 across the three most recent events, then compare with excluding `amount < 20` events in `WHERE` before window evaluation.

At event 106, explain why the two approaches give different answers.

### Exercise 14 — Timestamps and INTERVAL

Use `event_at` to compute the `SUM` of events over the trailing two days:

```sql
ORDER BY event_at
RANGE BETWEEN INTERVAL '2 days' PRECEDING
          AND CURRENT ROW
```

Why does the day 8 event exclude day 4 events? If timestamps involve local-timezone DST, what must be checked?

### Exercise 15 — Group by day first, then window

Write a `day_totals` CTE using:

```sql
GROUP BY account_id, day_no
```

Then compute a rolling total using:

```sql
ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
```

over the aggregated table. Do the per-day totals match `GROUPS 1 PRECEDING` on the detailed data? Explain the **difference in output row counts**.

### Exercise 16 — Past total excluding current row

Compute:

```sql
SUM(amount) OVER (
    PARTITION BY account_id
    ORDER BY day_no, event_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
)
```

At event 101, what is the result? When should `COALESCE(...,0)` be used?

### Exercise 17 — DESC reverses PRECEDING/FOLLOWING meaning

Write two `RANGE` offset queries on `day_no`:

1. `ORDER BY day_no ASC`.
2. `ORDER BY day_no DESC`.

Explain why "1 PRECEDING" falls on opposite numeric sides.

### Exercise 18 — Tie-breaker keys change peer groups

Compare:

```sql
ORDER BY day_no
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

with:

```sql
ORDER BY day_no, event_id
GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
```

Why does the second approach no longer keep events 102 and 103 in the same peer group?

### Exercise 19 — Compute first, then filter output

Create a CTE computing the running total for all account A events, then in the outer query keep only `day_no >= 2`.

Compare with placing `WHERE day_no >= 2` in the query computing the window. At event 102, why does one yield 30 while the other yields 20?

### Exercise 20 — EXPLAIN and indexes

Create index:

```sql
CREATE INDEX idx_events_account_day_event
ON window_frame_lab.events(account_id, day_no, event_id);
```

Run `EXPLAIN (ANALYZE, BUFFERS)` on the `ROWS 2 PRECEDING` moving sum. Why can the planner still choose a sequential scan and sort on a 10-row table?

### Exercise 21 — NULLs in the sort key

Suppose rows have `score IS NULL`. Design `GROUPS BETWEEN CURRENT ROW AND CURRENT ROW` over `ORDER BY score NULLS LAST`.

How are `NULL` rows grouped as peers? Should `NULL` automatically be replaced with 0 if 0 is also a valid score?

### Exercise 22 — Specifying a business metric

A dashboard wants:

> For each transaction, display total sales for the **last seven calendar days up to the transaction's timestamp**, including all transactions sharing that timestamp.

Would you choose `ROWS`, `RANGE`, or `GROUPS`? Explain how to express the time offset, timezone policy, peer handling, and testing on multi-transaction dates.

### Exercise 23 — Another specification: last three active trading days

A company does not have sales every day. Requirement:

> For each detail line, display total sales of the **three most recent days with transactions**, including the current day.

Which frame should you choose if individual detail rows must be kept? Under what condition should you `GROUP BY` day first and use `ROWS`?

### Exercise 24 — Empty frames and EXCLUDE

Use `EXCLUDE GROUP` on account A's cumulative `RANGE` frame. At the very first event:

- What does `SUM(amount)` return?
- What does `COUNT(*)` return?
- Should either result be considered a SQL error?

---

## 31. Checklist for designing reliable window frames

| Question | How to decide |
| --- | --- |
| How are partitions divided? | `PARTITION BY` the right business key |
| Is ordering needed for calculation? | `ORDER BY` inside `OVER` |
| What unit does "N preceding" count? | Rows → `ROWS`; values → `RANGE`; peer groups → `GROUPS` |
| Can rows tie? | Check all `ORDER BY` expressions |
| Does `ROWS` need reproducible output? | Supply a stable tie-breaker |
| Does `GROUPS` intend to group by day? | `ORDER BY` only the target date/group key |
| What type does `RANGE` offset use? | Numeric key or `INTERVAL` for time |
| Does `RANGE` offset have multiple `ORDER BY` keys? | PostgreSQL requires one compatible key |
| Using `ASC`/`DESC`? | `PRECEDING`/`FOLLOWING` follow sort direction |
| Is `CURRENT ROW` a row or a peer group? | `ROWS` vs. `RANGE`/`GROUPS` |
| Was a frame declared? | If not, check the default with `ORDER BY` |
| Need the whole partition total? | Full-partition frame or omit `ORDER BY` |
| Using `LAST_VALUE`? | Check frame end; usually requires `UNBOUNDED FOLLOWING` |
| Using `LAG`/`LEAD`/`RANK`? | Do not assume they are bounded like `SUM` |
| Need to omit current/peers? | `EXCLUDE CURRENT ROW`/`GROUP`/`TIES` |
| Could the frame be empty? | `COUNT=0`, `SUM`/`AVG` can be `NULL` |
| Using `FILTER`? | Distinguish aggregate filtering vs. input `WHERE` |
| Filtering by window results? | Use a CTE/derived table to compute first |
| Mixing calendar days and active days? | `RANGE`/calendar vs. `GROUPS`/`ROWS` after `GROUP BY` |
| Timezone/DST involved? | Clarify absolute instants vs. business periods |
| Peers with `NULL` keys? | Explicit `NULLS FIRST/LAST` and `NULL` policy |
| Multiple windows sharing a frame? | Use a named `WINDOW` or exact identical specs |
| Slow query? | Inspect `EXPLAIN`, `Sort`, `WindowAgg`, buffers, statistics |
| Appropriate index available? | Index on partition/order keys; measure actual plan |
| Using `FOLLOWING` in forecasting? | Check for future-data leakage |
| Tested edge cases? | Peers, gap days, partition start/end, `NULL`, empty frames |

## Conclusion

In PostgreSQL, **the frame determines the exact slice of data that frame-sensitive window functions aggregate or read at each row**. The exact same `SUM(amount) OVER (...)` yields vastly different numbers depending on whether you choose `ROWS`, `RANGE`, or `GROUPS`.

Key principles to remember:

- **`ROWS`** counts rows in window order. Supply a tie-breaker whenever you need deterministic per-event running totals or moving averages.
- **`RANGE`** evaluates sort key values; with offsets, it requires a compatible key and offset type—especially `INTERVAL` for time. It naturally includes multiple rows sharing a timestamp or date.
- **`GROUPS`** counts peer groups defined by `ORDER BY`, not individual rows and not absolute time durations.
- **`CURRENT ROW`** in `RANGE`/`GROUPS` can mean an **entire peer group**, unlike `CURRENT ROW` in `ROWS`.
- When `ORDER BY` is present without an explicit frame, PostgreSQL defaults to **`RANGE` from partition start to the end of the current peer group**. That is why tied rows receive identical running sums and `LAST_VALUE` does not return the partition's final value by default.
- **`EXCLUDE CURRENT ROW`, `EXCLUDE GROUP`, and `EXCLUDE TIES`** remove the current row or peers from the frame while keeping the row in the output.
- `SUM`, `AVG`, `FIRST_VALUE`, `LAST_VALUE`, and `NTH_VALUE` are frame-sensitive; `RANK`, `ROW_NUMBER`, `LAG`, and `LEAD` operate primarily on partition and order.
- **Syntactic validity is not enough**: define time units, tie policies, `NULL` handling, start/end boundaries, and `WHERE`-before-window order.

By clearly stating "**how many rows, how many value units, or how many peer groups?**", you can select the right window frame, explain every number, and write consistent analytical queries even when data contains gap days, tied timestamps, or multiple partitions.
