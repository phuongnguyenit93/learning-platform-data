# first_value, last_value, nth_value, and Frame Effects in PostgreSQL

## 1. The problem: "first", "last", and "nth" within which scope?

Suppose a sales table contains transactions for each business team. A report needs to display, on **each transaction row**:

- The name of the person who made the team's **first sale**.
- The name of the person who made the team's **last sale**.
- The name of the person who made the team's **second sale**.
- The value of the **first sale among the three most recent sales**, up to the current row.

PostgreSQL provides three suitable window functions:

- `first_value(expression)`: retrieves the value from the **first row in the window frame**.
- `last_value(expression)`: retrieves the value from the **last row in the window frame**.
- `nth_value(expression, n)`: retrieves the value from the **nth row, counting from the start of the window frame**, where `n` is a positive ordinal.

These functions do not simply pick the first, last, or nth row **of the entire table**. They operate within the context of a **window** consisting of a partition, an ordering, and especially a **frame**.

Example:

```sql
SELECT
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_seller
FROM window_lab.sales;
```

A beginner might expect every row of each team to show the seller of the **last sale in the team**. However, with `ORDER BY` and PostgreSQL's default frame, `last_value` typically returns the **current row's own seller** (when the ordering is unique).

To retrieve the last value of the **entire partition**, specify the frame:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

**Core takeaway of this lesson:** the names `first_value`, `last_value`, and `nth_value` describe positions **inside the frame**, without dictating how far that frame spans. Without understanding the default frame, you can write syntactically valid SQL that yields business-incorrect results.

## 2. Lesson objectives

After completing this lesson, you will be able to:

1. Distinguish `PARTITION BY`, `ORDER BY`, and the **window frame**.
2. Use `first_value`, `last_value`, and `nth_value` with realistic data.
3. Explain the default `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` when a window has `ORDER BY`.
4. Understand **peer rows**: rows sharing equal values across the entire `ORDER BY` key of the window.
5. Use `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` to get the first/last value of the **entire partition**.
6. Use sliding frames such as `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`.
7. Distinguish `ROWS`, `RANGE`, and `GROUPS` when multiple rows share the same sort key.
8. Handle `NULL`s, missing nth rows, and non-deterministic ordering.
9. Recognize when to use `LAG`/`LEAD`, `ROW_NUMBER`, `DISTINCT ON`, or subqueries instead of a frame value function.
10. Write reports with stable results, accurate scope, and no unintended row multiplication.

## 3. Creating PostgreSQL data for practice

This lesson uses the `window_lab` schema in a test database, without touching real production tables.

### 3.1. Creating the sales table

```sql
CREATE SCHEMA IF NOT EXISTS window_lab;

CREATE TABLE window_lab.sales (
    sale_id bigint PRIMARY KEY,
    team text NOT NULL,
    seller text NOT NULL,
    sold_on date NOT NULL,
    revenue numeric(12,2)
);
```

In this example:

- `sale_id` is a unique transaction ID, used as a tie-breaker when multiple sales occur on the same date.
- `team` identifies the group.
- `seller` is the text value we want to extract with window functions.
- `sold_on` is the transaction date.
- `revenue` allows `NULL` to illustrate the difference between **missing value** and **missing row**.

### 3.2. Loading intentional test data

```sql
INSERT INTO window_lab.sales
    (sale_id, team, seller, sold_on, revenue)
VALUES
    (1,  'North', 'An',    DATE '2026-01-03', 100.00),
    (2,  'North', 'Bình',  DATE '2026-01-05', 180.00),
    (3,  'North', 'Chi',   DATE '2026-01-05', NULL),
    (4,  'North', 'Dung',  DATE '2026-01-09',  90.00),
    (5,  'North', 'Em',    DATE '2026-01-12', 140.00),
    (6,  'South', 'Giang', DATE '2026-01-02', 200.00),
    (7,  'South', 'Hà',    DATE '2026-01-06', 120.00),
    (8,  'South', 'Huy',   DATE '2026-01-07', 120.00),
    (9,  'South', 'Khánh', DATE '2026-01-10', 300.00),
    (10, 'East',  'Lan',   DATE '2026-01-08', 250.00);
```

The table now has **three teams**:

| team | sale_id | seller | sold_on | revenue |
| --- | ---: | --- | --- | ---: |
| North | 1 | An | 2026-01-03 | 100.00 |
| North | 2 | Bình | 2026-01-05 | 180.00 |
| North | 3 | Chi | 2026-01-05 | NULL |
| North | 4 | Dung | 2026-01-09 | 90.00 |
| North | 5 | Em | 2026-01-12 | 140.00 |
| South | 6 | Giang | 2026-01-02 | 200.00 |
| South | 7 | Hà | 2026-01-06 | 120.00 |
| South | 8 | Huy | 2026-01-07 | 120.00 |
| South | 9 | Khánh | 2026-01-10 | 300.00 |
| East | 10 | Lan | 2026-01-08 | 250.00 |

We intentionally included:

1. Team **North** having two sales on the same date `2026-01-05` (IDs 2 and 3).
2. One sale with `revenue = NULL` (ID 3).
3. Team **East** having only **one sale** (crucial for `nth_value(..., 2)`).
4. Different group sizes.

You can inspect the data in deterministic order:

```sql
SELECT sale_id, team, seller, sold_on, revenue
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Note:** re-running `INSERT` on already-loaded data will raise a duplicate primary key error in PostgreSQL. Use a fresh practice database/schema or manage reloads deliberately.

## 4. Reviewing `OVER`: partition, order, and frame

Window functions use the `OVER` clause:

```sql
function_name(...) OVER (
    PARTITION BY ...
    ORDER BY ...
    ROWS BETWEEN ... AND ...
)
```

These three concepts are **distinct**:

| Component | What does it decide? | Example |
| --- | --- | --- |
| `PARTITION BY` | Splits rows into independent partitions | Each `team` |
| `ORDER BY` inside `OVER` | Sets the logical order of rows inside a partition | Sale date, then ID |
| **Frame** | Selects which rows, within the partition and chosen order, fall inside the scope visible to the function | From group start to current row, or whole group |

A diagram:

```text
All sales
       |
       | PARTITION BY team
       v
+--------------------+------------------+-------------+
| North              | South            | East        |
| 1, 2, 3, 4, 5      | 6, 7, 8, 9       | 10          |
+--------------------+------------------+-------------+
       |
       | ORDER BY sold_on, sale_id
       v
Stable order within each team
       |
       | ROWS BETWEEN ...
       v
Frame corresponding to each current row
       |
       v
first_value / last_value / nth_value
```

### 4.1. `PARTITION BY` is not `GROUP BY`

`GROUP BY` usually **collapses** multiple rows into one aggregated row per group.

```sql
SELECT team, COUNT(*) AS sales_count
FROM window_lab.sales
GROUP BY team
ORDER BY team;
```

Result has three rows: East 1, North 5, South 4.

Conversely:

```sql
SELECT
    sale_id,
    team,
    seller,
    COUNT(*) OVER (PARTITION BY team) AS team_sales_count
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

the result **still has 10 rows**, with each row enriched by the team's sale count.

`first_value`, `last_value`, and `nth_value` likewise preserve each input row and append a value calculated over the window.

### 4.2. `ORDER BY` inside `OVER` does not sort the returned result

```sql
SELECT
    sale_id,
    team,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales;
```

`ORDER BY sold_on, sale_id` **inside `OVER`** is the ordering used for window evaluation. It **does not guarantee the order of returned rows**.

For readable and stable output:

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

The `ORDER BY` at the **end of `SELECT`** governs the displayed row order.

## 5. `first_value`: value at the start of the frame

Syntax:

```sql
first_value(expression) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

The function returns the value of `expression` at the **first row in the current frame**, with the expression's data type.

### 5.1. First seller in each team

```sql
SELECT
    team,
    sale_id,
    seller,
    sold_on,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Summary result:

| team | sale_id | seller | first_seller |
| --- | ---: | --- | --- |
| East | 10 | Lan | Lan |
| North | 1 | An | An |
| North | 2 | Bình | An |
| North | 3 | Chi | An |
| North | 4 | Dung | An |
| North | 5 | Em | An |
| South | 6 | Giang | Giang |
| South | 7 | Hà | Giang |
| South | 8 | Huy | Giang |
| South | 9 | Khánh | Giang |

Because the default frame starts at the **beginning of the partition**, `first_value` here produces the same person on every row of the team.

However, that conclusion holds only for **this frame**. If the frame is restricted to the three most recent sales, the "first row of the frame" slides along with the current row.

### 5.2. First is not necessarily the smallest value

```sql
SELECT
    sale_id,
    seller,
    revenue,
    first_value(revenue) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_revenue,
    MIN(revenue) OVER (
        PARTITION BY team
    ) AS smallest_nonnull_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

In North:

- `first_revenue` is **100.00**: revenue of the **chronologically first sale**.
- `smallest_nonnull_revenue` is **90.00**: the smallest monetary amount, ignoring `NULL` per `MIN` rules.

Thus:

- `first_value(revenue ORDER BY sold_on)` means **chronological position**.
- `MIN(revenue)` means **smallest numeric value**.

Never replace `first_value` with `MIN` just because both evoke "first/minimum".

### 5.3. First by which criterion?

If you want the seller with the highest revenue:

```sql
SELECT
    team,
    sale_id,
    seller,
    revenue,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY revenue DESC NULLS LAST, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS seller_with_highest_revenue
FROM window_lab.sales
ORDER BY team, sale_id;
```

Now **"first" means the leading row when sorted by descending revenue**, not the earliest seller by date.

For North, the highest-revenue seller is **Bình (180.00)**, not An. `NULLS LAST` prevents a `NULL` revenue from accidentally sorting ahead of numeric values under descending order.

## 6. `last_value`: the most frequently misunderstood function

Syntax:

```sql
last_value(expression) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

This function retrieves the value at the **last row of the frame**.

### 6.1. Example that looks like team-last, but actually gets default-frame-last

```sql
SELECT
    sale_id,
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_seller_default
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | last_seller_default |
| ---: | --- | --- |
| 1 | An | An |
| 2 | Bình | Bình |
| 3 | Chi | Chi |
| 4 | Dung | Dung |
| 5 | Em | Em |

Why is the team's final seller **Em** not repeated on all five rows?

Because when a window has `ORDER BY` and no explicit frame, PostgreSQL defaults to a frame running from the **start of the partition to the current row and its peer rows**. With `ORDER BY sold_on, sale_id`, the key pair is unique, so each row is its own sole peer.

For row ID 2, the frame is:

```text
North by (sold_on, sale_id)

[An, Bình] | Chi, Dung, Em
 ^-------^
 frame for Bình's row

last_value(seller) = 'Bình'
```

The function cannot see Dung or Em because they lie **beyond the current frame**.

### 6.2. Correct: extending the frame to the end of the partition

```sql
SELECT
    sale_id,
    team,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller_in_team
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | last_seller_in_team |
| ---: | --- | --- |
| 1 | An | Em |
| 2 | Bình | Em |
| 3 | Chi | Em |
| 4 | Dung | Em |
| 5 | Em | Em |

The clause:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
```

extends the frame to the **beginning and end of the entire partition**, regardless of which row is being evaluated.

This is the single most important pattern when the business requirement is the **final value of the entire group**.

### 6.3. Directly comparing default and full-frame results

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_in_running_frame,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_in_partition
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

For South:

| sale_id | seller | last_in_running_frame | last_in_partition |
| ---: | --- | --- | --- |
| 6 | Giang | Giang | Khánh |
| 7 | Hà | Hà | Khánh |
| 8 | Huy | Huy | Khánh |
| 9 | Khánh | Khánh | Khánh |

Neither query has a syntax error; the difference lies in the **frame**, so business logic must first clarify **"last of what?"**.

## 7. `nth_value`: value at the nth position in the frame

Syntax:

```sql
nth_value(expression, n) OVER (
    PARTITION BY ...
    ORDER BY ...
    frame_clause
)
```

In PostgreSQL, `n` is **1-based**, not 0-based array indexing.

- `nth_value(value, 1)`: value of the first row in the frame.
- `nth_value(value, 2)`: value of the second row.
- `nth_value(value, 3)`: value of the third row.

`n` must be a valid positive integer per syntax/function rules. If the frame contains **fewer than n rows**, the function returns **NULL**.

### 7.1. Second sale of each team

```sql
SELECT
    team,
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Result:

| team | sale_id | seller | second_seller |
| --- | ---: | --- | --- |
| East | 10 | Lan | NULL |
| North | 1 | An | Bình |
| North | 2 | Bình | Bình |
| North | 3 | Chi | Bình |
| North | 4 | Dung | Bình |
| North | 5 | Em | Bình |
| South | 6 | Giang | Hà |
| South | 7 | Hà | Hà |
| South | 8 | Huy | Hà |
| South | 9 | Khánh | Hà |

Team East has only one row, so **no second row exists**; returning `NULL` is right.

### 7.2. Without specifying a frame: the second row may not have "appeared" yet

```sql
SELECT
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS second_in_running_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | second_in_running_frame |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | Bình |
| 3 | Chi | Bình |
| 4 | Dung | Bình |
| 5 | Em | Bình |

On the first row, the default frame only holds **one row**, so there is no second value yet. From row 2 onward, the frame already contains Bình's sale at position 2.

With a full frame, `second_seller` is Bình **even on North's first row**. The difference is **growing running frame vs. entire partition**.

### 7.3. The nth row exists, yet its value is NULL

North has `sale_id = 3` at the third position in order, with `revenue = NULL`.

```sql
SELECT
    sale_id,
    seller,
    nth_value(revenue, 3) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

`third_revenue` returns **NULL across all five rows** of North, **even though the third row actually exists**.

Compare:

- East: `nth_value(seller, 2)` is `NULL` because **there is no second row**.
- North: `nth_value(revenue, 3)` is `NULL` because **the third row has a NULL revenue value**.

To tell them apart, check the **row count in the frame** or inspect the source row/value. Never conclude "there is no third row" solely from the function returning `NULL`.

### 7.4. Using n as a business parameter

Suppose a report asks for the seller at position `n` passed in by an API:

```sql
PREPARE nth_seller(integer) AS
SELECT
    team,
    sale_id,
    nth_value(seller, $1) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS requested_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;

EXECUTE nth_seller(3);

DEALLOCATE nth_seller;
```

The application must **validate that n is a positive integer** within reasonable bounds before sending it. If you want to extract a position **counting from the end**, `nth_value` in current PostgreSQL does not support a `FROM LAST` option; see the workaround in a later section.

## 8. The default frame in PostgreSQL: source of many misconceptions

When a window has `ORDER BY` but **no explicit frame**, PostgreSQL uses a default frame equivalent to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND CURRENT ROW
```

Crucially, `CURRENT ROW` in **`RANGE`** mode does not always mean "stop strictly at the current individual row". It includes **peer rows** sharing the exact same values across all `ORDER BY` expressions.

### 8.1. Default is not the entire partition

For example:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
)
```

has the same semantics as:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    RANGE BETWEEN UNBOUNDED PRECEDING
              AND CURRENT ROW
)
```

Because `sale_id` breaks ties, no two rows in the same team share both keys. The frame at North's third row contains An, Bình, and Chi; **it excludes Dung and Em**.

### 8.2. What if `ORDER BY` is omitted entirely inside `OVER`?

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
    ) AS last_without_order
FROM window_lab.sales
ORDER BY team, sale_id;
```

Without a window `ORDER BY`, all rows in the partition are peers; the default frame encompasses the **entire partition**. However, **who "the last row" is has no business definition** without logical ordering.

Do not assume that `ORDER BY team, sale_id` at the end of the query sets the ordering for `last_value`. It only sorts the output after window values have been computed.

**Rule:** whenever you want "first", "last", or "nth", define **`ORDER BY` inside `OVER`**. When you want group-wide scope, also define a **full frame**.

## 9. Peer rows: two rows can tie at the same position

Two rows are **peers** if they share **identical values for all expressions in the window's `ORDER BY`**.

In North:

| sale_id | seller | sold_on |
| ---: | --- | --- |
| 1 | An | 2026-01-03 |
| 2 | Bình | 2026-01-05 |
| 3 | Chi | 2026-01-05 |
| 4 | Dung | 2026-01-09 |
| 5 | Em | 2026-01-12 |

With:

```sql
ORDER BY sold_on
```

Bình and Chi are peers because both share date `2026-01-05`.

With:

```sql
ORDER BY sold_on, sale_id
```

they are **no longer peers**, because their `sale_id` values differ.

### 9.1. Observing how the default frame includes peers

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS default_range_count,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS exact_row_count
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | default_range_count | exact_row_count |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 1 |
| 2 | Bình | 3 | 2 |
| 3 | Chi | 3 | 3 |
| 4 | Dung | 4 | 4 |
| 5 | Em | 5 | 5 |

At Bình's row (ID 2), the default `RANGE` frame includes **Chi as well** because Chi shares the same date. Hence `default_range_count = 3`, even though Bình is only the second row by `sale_id`.

### 9.2. How do peer rows affect `last_value`?

If you write:

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS last_in_default_range
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

on `2026-01-05`, the frame ends at the **last peer of the entire 05th group**, not simply Bình or Chi individually.

Because sorting is only by `sold_on`, the relative order between Bình and Chi is **undefined**. The output of `last_value(seller)` within the peer group can depend on whichever row happens to sit last in physical processing order; never build business rules on that accident.

**Fix:** add a meaningful tie-breaker key, such as:

```sql
ORDER BY sold_on, sale_id
```

If `sale_id` is unique, the window ordering becomes deterministic.

### 9.3. Why is "same date" insufficient for "last sale"?

In reality, `sold_on` is a `date`, so it does not tell which transaction occurred **later on the same day**. `sale_id` in this lesson is merely used as a **tie-breaker** convention.

If business logic demands **actual occurrence time**, the design should include `occurred_at timestamptz` and sort by:

```sql
ORDER BY occurred_at, sale_id
```

Never assume IDs always match chronological order. If IDs are generated in distributed systems, re-imports, or batch jobs, ID order can diverge from event timestamps.

## 10. `ROWS`, `RANGE`, and `GROUPS`: three ways to interpret a frame

PostgreSQL supports three primary frame units:

| Unit | Counts/interprets boundaries by | Primary meaning |
| --- | --- | --- |
| `ROWS` | Number of **physical rows in window order** | "Previous two transactions" |
| `RANGE` | **`ORDER BY` key values** and peer groups | "Transactions within a value interval" |
| `GROUPS` | Number of **peer groups** | "One preceding date group" |

These three modes can return different results on the exact same data.

### 10.1. `ROWS`: counting rows

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 1 PRECEDING
                 AND CURRENT ROW
    ) AS current_and_previous_row
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | current_and_previous_row |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 2 |
| 3 | Chi | 2 |
| 4 | Dung | 2 |
| 5 | Em | 2 |

This is a frame of at most **two rows**: the current row and one preceding row under `(sold_on, sale_id)`. It does not care whether those two rows are one day or many days apart.

### 10.2. `RANGE`: by value interval

With `date`, we can demonstrate on a cast `timestamp` column so the `INTERVAL` offset is explicit:

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on::timestamp
        RANGE BETWEEN INTERVAL '4 days' PRECEDING
                  AND CURRENT ROW
    ) AS rows_within_four_days
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result on the sample dataset:

| sale_id | seller | rows_within_four_days |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 3 |
| 3 | Chi | 3 |
| 4 | Dung | 3 |
| 5 | Em | 2 |

Explanation:

- On Jan 05: the range from Jan 01 to Jan 05 includes An, Bình, and Chi → 3 rows.
- On Jan 09: the range from Jan 05 to Jan 09 includes Bình, Chi, and Dung → 3 rows.
- On Jan 12: the range from Jan 08 to Jan 12 includes Dung and Em → 2 rows.

**Important:** when `RANGE` uses a `PRECEDING`/`FOLLOWING` offset, PostgreSQL requires a single `ORDER BY` key whose data type supports compatible offset addition/subtraction. Do not write two keys `ORDER BY sold_on, sale_id` and arbitrarily attach a `RANGE` offset.

### 10.3. `GROUPS`: counting peer groups

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING
                   AND CURRENT ROW
    ) AS current_and_previous_date_group
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Peer groups by date in North:

```text
Group 1: 2026-01-03 -> An             (1 row)
Group 2: 2026-01-05 -> Bình, Chi      (2 rows)
Group 3: 2026-01-09 -> Dung           (1 row)
Group 4: 2026-01-12 -> Em             (1 row)
```

Result:

| sale_id | seller | current_and_previous_date_group |
| ---: | --- | ---: |
| 1 | An | 1 |
| 2 | Bình | 3 |
| 3 | Chi | 3 |
| 4 | Dung | 3 |
| 5 | Em | 2 |

`GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` includes **the current date group and the previous date group**, not strictly two rows.

If dates contain varying numbers of transactions, the actual row count inside the frame varies accordingly.

### 10.4. When to choose which unit?

| Business question | Appropriate frame to consider |
| --- | --- |
| "Last three transactions" | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| "Seven days leading up to transaction date" | `RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW` on a suitable timestamp, or build a dedicated date axis |
| "This transaction date and the prior date with data" | `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` with `ORDER BY sold_on` |
| "Start and end of the entire group" | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |
| "Cumulative from group start to current row" | `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` with deterministic ordering |

Do not pick `ROWS` simply because "row" feels familiar: if the report specifies "days", verify whether it means **calendar days** or **transactions**.

## 11. Sliding frames and their effect on all three functions

A common sliding frame:

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

At each row, the frame contains at most the **three most recent rows** in window order.

### 11.1. Visual illustration on team North

```text
Current row     Frame                   Frame start  Frame end
An              [An]                    An           An
Bình            [An, Bình]              An           Bình
Chi             [An, Bình, Chi]         An           Chi
Dung            [Bình, Chi, Dung]       Bình         Dung
Em              [Chi, Dung, Em]         Chi          Em
```

As the window slides:

- `first_value` is no longer always An.
- `last_value` remains the current row when the frame ends at `CURRENT ROW` with unique ordering.
- `nth_value(..., 2)` is the second row **inside the three-row frame**, not the second row **of the entire team**.

### 11.2. Complete query

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    first_value(seller) OVER w AS first_in_last_three,
    last_value(seller) OVER w AS last_in_last_three,
    nth_value(seller, 2) OVER w AS second_in_last_three
FROM window_lab.sales
WHERE team = 'North'
WINDOW w AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
ORDER BY sold_on, sale_id;
```

Result:

| sale_id | seller | first_in_last_three | last_in_last_three | second_in_last_three |
| ---: | --- | --- | --- | --- |
| 1 | An | An | An | NULL |
| 2 | Bình | An | Bình | Bình |
| 3 | Chi | An | Chi | Bình |
| 4 | Dung | Bình | Dung | Chi |
| 5 | Em | Chi | Em | Dung |

The first row has a one-row frame, so there is no second position. At Dung, the frame is `[Bình, Chi, Dung]`, so the **second row in the frame** is Chi.

### 11.3. Looking forward using a different frame

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS last_from_current_forward,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_current_forward
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

For North:

- `last_from_current_forward` is **Em** on all five rows.
- `second_from_current_forward` is **Bình, Chi, Dung, Em, NULL** respectively.

`nth_value(..., 2)` in a frame starting at the current row resembles the **next row's** value. Still, when the real goal is "row N steps back/ahead", `LAG`/`LEAD` usually expresses it more clearly.

## 12. Two meanings of `CURRENT ROW` to distinguish

In a `ROWS` frame:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

`CURRENT ROW` means the **current row** in row order.

In a `RANGE` or `GROUPS` frame:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

or:

```sql
GROUPS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

as an end boundary, `CURRENT ROW` can include the **last peer** of the current row; as a start boundary, it can represent the **first peer**.

Therefore, never glance at `CURRENT ROW` and assume the frame holds the exact row count seen in a single run. Inspect both the **frame unit** and the **`ORDER BY` keys**.

### 12.1. Impact on `last_value` within peer groups

With:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on
)
```

rows sharing the same `sold_on` are peers, so `last_value` resolves to the **last peer** in the frame. If order among peers is unspecified, the result can be unstable in business terms.

With:

```sql
last_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

each row has a well-defined position, and the frame end is strictly the current row itself.

### 12.2. Avoid testing only on tie-free data

If every date has only one sale, `ROWS` and `RANGE` often feel identical across many queries. As soon as two sales share a date, the frames can diverge sharply.

When building reports with window functions, always test at least these cases:

- Two rows sharing the same `ORDER BY` key.
- First and last rows of a partition.
- A single-row partition.
- `NULL` expression values.
- `n` larger than the row count.

## 13. Full partition: write it explicitly instead of relying on defaults

When the requirement is "first, last, and third person of the whole team", the explicit pattern is:

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER w_full AS first_seller,
    last_value(seller)  OVER w_full AS last_seller,
    nth_value(seller, 3) OVER w_full AS third_seller
FROM window_lab.sales
WINDOW w_full AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

Expected values:

| team | first_seller | last_seller | third_seller |
| --- | --- | --- | --- |
| East | Lan | Lan | NULL |
| North | An | Em | Chi |
| South | Giang | Khánh | Huy |

Each triple is **repeated across every row belonging to that team**.

### 13.1. Why use `ROWS` if full `RANGE` also covers the whole group?

You could write:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND UNBOUNDED FOLLOWING
```

and all peers would fall inside the frame. Yet when the intent is **every row in the partition**, `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` is clearer and communicates "all rows" directly.

Even so, **`ORDER BY` must still be sufficiently deterministic**: widening the frame does not resolve ambiguity about which row is last if sort keys tie.

### 13.2. Is a full frame needed for `first_value`?

With the default frame starting at the partition's beginning up to the current row, `first_value` already picks the first person in deterministic order. However, when displaying **first/last/nth of the entire group together**, sharing a full frame across all three functions:

- Makes the semantic contract immediately visible.
- Avoids relying on readers memorizing default frame rules.
- Lets all three reuse one named window cleanly.
- Reduces risk when editing frames in one part of a query.

## 14. Named windows: reusing consistent definitions

PostgreSQL supports the `WINDOW` clause to name a window configuration.

### 14.1. One window for the entire partition

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER whole_team AS team_first,
    last_value(seller)  OVER whole_team AS team_last,
    nth_value(seller, 2) OVER whole_team AS team_second
FROM window_lab.sales
WINDOW whole_team AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

Every function uses the **exact same partition, ordering, and frame**.

### 14.2. Two windows for two different purposes

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER w_full AS team_first,
    last_value(seller) OVER w_full AS team_last,
    first_value(seller) OVER w_recent AS earliest_in_last_three
FROM window_lab.sales
WINDOW
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ),
    w_recent AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    )
ORDER BY team, sold_on, sale_id;
```

Here, `w_full` and `w_recent` clearly communicate intent. They are not two different functions; they are **two frame configurations**.

### 14.3. Avoid ambiguous window names

Names like `w1` and `w2` are hard to read in long reports. Descriptive names like `whole_team`, `running_history`, and `recent_three` help anyone maintaining the SQL immediately spot when a value spans the whole group vs. a sliding window.

**Note:** you cannot arbitrarily copy or modify a named window that already defines a frame using `OVER (w ... )`. To avoid frame-copying errors, define separate explicit named windows as above whenever two goals use different frames.

## 15. How frames affect `nth_value` with peer groups

Suppose you want the **second seller of each team** chronologically.

### 15.1. If ordering only by date

```sql
SELECT
    sale_id,
    seller,
    sold_on,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller_by_date_only
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Bình and Chi share date Jan 05. With only `ORDER BY sold_on`, **there is no criterion deciding who is second and who is third**. Consequently, `second_seller_by_date_only` may not be business-stable.

Using a full frame does not fix a missing tie-breaker key.

### 15.2. Adding `sale_id` when exact position matters

```sql
nth_value(seller, 2) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

With the unique `(sold_on, sale_id)` key, North's second seller is Bình under the **defined ordering convention**.

### 15.3. Does "second" mean second row or second date?

These two requirements are **different**:

1. "Who made the **second sale**?" → refers to the **second row**; `nth_value(seller, 2)` in deterministic order.
2. "Who made sales on the **second active date**?" → refers to the **second date group**, which can involve **multiple people** (Bình and Chi).

`nth_value` extracts **one row**, not an entire peer group.

If you need everyone from the second active date, use `DENSE_RANK` ordered by date:

```sql
WITH ranked AS (
    SELECT
        team,
        sale_id,
        seller,
        sold_on,
        DENSE_RANK() OVER (
            PARTITION BY team
            ORDER BY sold_on
        ) AS day_rank
    FROM window_lab.sales
)
SELECT team, sale_id, seller, sold_on
FROM ranked
WHERE day_rank = 2
ORDER BY team, sold_on, sale_id;
```

For North, the second active date is Jan 05 and returns **both Bình and Chi**. For South, it is Jan 06 (Hà). For East, no second date exists.

**Takeaway:** clarify "nth **row**" vs. "nth **distinct key group**" before picking a function.

## 16. `NULL`s and PostgreSQL's `RESPECT NULLS` behavior

In the SQL standard, some systems provide options like `RESPECT NULLS` and `IGNORE NULLS` for value-navigation functions.

In current PostgreSQL, `first_value`, `last_value`, and `nth_value` **do not support an `IGNORE NULLS` option**. Default behavior corresponds to **respecting NULLs** (*RESPECT NULLS*).

### 16.1. If the value at the selected position is NULL, the result is NULL

```sql
SELECT
    sale_id,
    seller,
    nth_value(revenue, 3) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

The third row is Chi with `revenue NULL`, so the returned value is `NULL`. PostgreSQL **does not skip Chi** to return Dung's revenue as the third value.

### 16.2. Do not use `IGNORE NULLS` syntax from other DBMSs

Some SQL snippets found online write:

```sql
-- Not supported syntax in PostgreSQL:
first_value(revenue) IGNORE NULLS OVER (...)
```

Do not copy such syntax verbatim from another database product. Design a PostgreSQL-compatible solution instead.

### 16.3. Getting the first non-NULL revenue per team

A clear approach is filtering non-NULL records before picking the position:

```sql
WITH first_nonnull AS (
    SELECT DISTINCT ON (team)
        team,
        revenue AS first_nonnull_revenue,
        sale_id AS source_sale_id
    FROM window_lab.sales
    WHERE revenue IS NOT NULL
    ORDER BY team, sold_on, sale_id
)
SELECT
    s.team,
    s.sale_id,
    s.seller,
    n.first_nonnull_revenue,
    n.source_sale_id
FROM window_lab.sales AS s
LEFT JOIN first_nonnull AS n
    ON n.team = s.team
ORDER BY s.team, s.sold_on, s.sale_id;
```

Explanation:

- `WHERE revenue IS NOT NULL` explicitly excludes rows without revenue before picking the first row.
- `DISTINCT ON (team)` picks the first row per team according to `ORDER BY team, sold_on, sale_id`.
- `LEFT JOIN` brings that value back onto all transactions of the team.

On the current data, North's first non-NULL revenue is still 100. Yet this query also works even if the **very first row has NULL revenue**.

### 16.4. Getting the last non-NULL revenue

```sql
WITH last_nonnull AS (
    SELECT DISTINCT ON (team)
        team,
        revenue AS last_nonnull_revenue,
        sale_id AS source_sale_id
    FROM window_lab.sales
    WHERE revenue IS NOT NULL
    ORDER BY team, sold_on DESC, sale_id DESC
)
SELECT
    s.sale_id,
    s.team,
    s.seller,
    n.last_nonnull_revenue,
    n.source_sale_id
FROM window_lab.sales AS s
LEFT JOIN last_nonnull AS n
    ON n.team = s.team
ORDER BY s.team, s.sold_on, s.sale_id;
```

In North, the last sale with non-NULL revenue is Em (140.00). Even if a team's final sale has `NULL` revenue, this still finds the **latest row with a value** under the sort convention.

### 16.5. Using `LATERAL` when needed row by row

Example finding the most recent non-NULL revenue **as of each transaction**:

```sql
SELECT
    s.sale_id,
    s.team,
    s.seller,
    s.revenue,
    prev.revenue AS latest_nonnull_so_far
FROM window_lab.sales AS s
LEFT JOIN LATERAL (
    SELECT s2.revenue
    FROM window_lab.sales AS s2
    WHERE s2.team = s.team
      AND s2.revenue IS NOT NULL
      AND (
          s2.sold_on < s.sold_on
          OR (
              s2.sold_on = s.sold_on
              AND s2.sale_id <= s.sale_id
          )
      )
    ORDER BY s2.sold_on DESC, s2.sale_id DESC
    LIMIT 1
) AS prev ON TRUE
ORDER BY s.team, s.sold_on, s.sale_id;
```

For Chi (ID 3), `revenue` is `NULL` while `latest_nonnull_so_far` is **180.00** from Bình. This is a "last non-null so far" problem, **different** from default `last_value(revenue)`.

Running a correlated query like this on large tables can be costly; consider an index on `(team, sold_on, sale_id)` and workload-appropriate strategies.

## 17. "Nth from the end": deliberately reversing sort direction

PostgreSQL does not offer `FROM LAST` syntax for `nth_value` found in some other DBMSs.

If you want the **second-to-last person** chronologically, **reverse the `ORDER BY`**:

```sql
SELECT
    team,
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_last
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Result per team:

| team | second_from_last |
| --- | --- |
| East | NULL |
| North | Dung |
| South | Huy |

North explanation:

```text
Ascending:  An, Bình, Chi, Dung, Em
Descending: Em, Dung, Chi, Bình, An
                 ^
     second position in descending order = Dung
```

In the diagram above, the second position is **Dung**; do not confuse caret alignment spacing with list position.

**Mandatory condition:** when reversing sort direction, reverse **the tie-breaker too**. If the forward order is `ORDER BY sold_on, sale_id`, the exact reverse order is `ORDER BY sold_on DESC, sale_id DESC`.

### 17.1. Getting the team's last person using `first_value` with descending order

Another way to get the newest seller:

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS latest_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

Corresponding results:

- East → Lan.
- North → Em.
- South → Khánh.

With `first_value` and stable descending order, the first row of the frame is the last sale in ascending order.

### 17.2. Should `last_value` always be replaced by `first_value DESC`?

Not necessarily. Both are valid provided:

- Ordering is defined consistently.
- Frames are configured properly.
- `NULL`s and ties follow requirements.
- The exact same input row set is used.

In a report where many functions share ascending order, **`last_value` + full frame** can be clearer. In a query seeking only a single newest row, **`ORDER BY ... DESC LIMIT 1`** or `DISTINCT ON` may be simpler.

## 18. Comparison with `LAG` and `LEAD`

These functions are all window functions yet select values differently.

| Function | Where does it read from? | Depends on `OVER`'s frame? |
| --- | --- | --- |
| `first_value` | First row of the **current frame** | **Yes** |
| `last_value` | Last row of the **current frame** | **Yes** |
| `nth_value` | Nth row **inside the frame** | **Yes** |
| `lag` | Preceding row by chosen offset **in the partition** | Not constrained by the frame in the same way |
| `lead` | Following row by chosen offset **in the partition** | Not constrained by the frame in the same way |

### 18.1. Directly comparing `LEAD` with `nth_value`

```sql
SELECT
    sale_id,
    seller,
    LEAD(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS next_seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN CURRENT ROW
                 AND UNBOUNDED FOLLOWING
    ) AS next_by_forward_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

In this example, both columns yield the same sequence:

```text
Bình, Chi, Dung, Em, NULL
```

Yet `LEAD(seller)` directly expresses "seller in the next row" without constructing a forward frame from `CURRENT ROW`. Whenever you want a value **n steps** from the current row, `LAG` or `LEAD` is usually the natural choice.

### 18.2. Striking difference when the frame runs cumulatively

```sql
SELECT
    sale_id,
    seller,
    LEAD(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS next_seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS last_in_default_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

`LEAD` still looks ahead to the next seller in partition order, while `last_value` with the default frame usually returns the current seller if the sort key is unique.

Never substitute one for the other without confirming the semantics of "end of frame" vs. "next row".

## 19. When you want strictly one row per group

`first_value` and `last_value` normally **return a repeated value across multiple rows**, rather than shrinking the result to one row per group.

If the goal is strictly **one latest sale per team**, a row-selection query may fit better.

### 19.1. PostgreSQL `DISTINCT ON`

```sql
SELECT DISTINCT ON (team)
    team,
    sale_id,
    seller,
    sold_on,
    revenue
FROM window_lab.sales
ORDER BY team, sold_on DESC, sale_id DESC;
```

Result has three rows:

| team | sale_id | seller |
| --- | ---: | --- |
| East | 10 | Lan |
| North | 5 | Em |
| South | 9 | Khánh |

`DISTINCT ON (team)` retains the first row **in the specified `ORDER BY` order** for each team.

Difference:

- Full-frame `last_value`: still returns **all sales**, alongside the team's final seller.
- `DISTINCT ON`: returns only **one sale per team**.

### 19.2. `ROW_NUMBER` when picking top 1

```sql
WITH ranked AS (
    SELECT
        team,
        sale_id,
        seller,
        sold_on,
        revenue,
        ROW_NUMBER() OVER (
            PARTITION BY team
            ORDER BY sold_on DESC, sale_id DESC
        ) AS rn
    FROM window_lab.sales
)
SELECT team, sale_id, seller, sold_on, revenue
FROM ranked
WHERE rn = 1
ORDER BY team;
```

Also finds the latest sale per team.

The advantage of `ROW_NUMBER` is that `rn <= 3` retrieves top 3 **rows**. To keep all tied rows, consider `RANK` or `DENSE_RANK` per requirements.

### 19.3. Cannot filter a window alias in the same SELECT's `WHERE`

Wrong:

```sql
-- Invalid: rn is not yet available in WHERE at the same query level.
SELECT
    team,
    seller,
    ROW_NUMBER() OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
    ) AS rn
FROM window_lab.sales
WHERE rn = 1;
```

Correct: use an outer CTE or subquery to filter window results as shown above.

PostgreSQL evaluates window functions at the appropriate stage of `SELECT`, **after the same-level `WHERE` filter**. To filter by a window value, introduce an outer query level.

## 20. `PARTITION BY` changes the meaning of first/last/nth

### 20.1. Without `PARTITION BY`: the whole result is one partition

```sql
SELECT
    sale_id,
    team,
    seller,
    first_value(seller) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_over_all_sales
FROM window_lab.sales
ORDER BY sold_on, sale_id;
```

Here `first_over_all_sales` is the earliest seller **across all rows passing `WHERE`** (in the sample data: Giang, on Jan 02), not each team's earliest seller.

### 20.2. Adding `PARTITION BY team`

```sql
first_value(seller) OVER (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

Result per team:

- North → An.
- South → Giang.
- East → Lan.

### 20.3. `WHERE` filters before window evaluation

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_seller_in_filtered_set
FROM window_lab.sales
WHERE sold_on >= DATE '2026-01-06'
ORDER BY team, sold_on, sale_id;
```

Because `WHERE sold_on >= '2026-01-06'` removes earlier sales **before computing the window**, the first person in the filtered set is **no longer** An for North or Giang for South.

In the filtered set:

- North starts at Dung (Jan 09).
- South starts at Hà (Jan 06).
- East starts at Lan (Jan 08).

**This is a crucial business distinction.**

### 20.4. Filtering display rows while still evaluating over full history

Move the window calculation into a CTE first, then filter outside:

```sql
WITH with_team_bounds AS (
    SELECT
        sale_id,
        team,
        seller,
        sold_on,
        first_value(seller) OVER (
            PARTITION BY team
            ORDER BY sold_on, sale_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND UNBOUNDED FOLLOWING
        ) AS first_seller_ever
    FROM window_lab.sales
)
SELECT
    team,
    sale_id,
    seller,
    sold_on,
    first_seller_ever
FROM with_team_bounds
WHERE sold_on >= DATE '2026-01-06'
ORDER BY team, sold_on, sale_id;
```

Now the report shows only sales from Jan 06 onward, yet `first_seller_ever` remains:

- North → An.
- South → Giang.
- East → Lan.

**Always distinguish:** "first value **within the reporting period**" vs. "first value **across all history**, displayed on rows of the reporting period".

## 21. Frames and effects of `UNBOUNDED`, `PRECEDING`, `FOLLOWING`

Common frame bounds:

| Keyword | Meaning |
| --- | --- |
| `UNBOUNDED PRECEDING` | From the start of the partition |
| `n PRECEDING` | Back n frame units before the current row/group/value |
| `CURRENT ROW` | Current row or peer group depending on frame unit |
| `n FOLLOWING` | Ahead n frame units after the current row/group/value |
| `UNBOUNDED FOLLOWING` | To the end of the partition |

### 21.1. Common frames

**From start to current:**

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND CURRENT ROW
```

Fits running totals, history up to current row, and `first_value` from group start.

**Entire partition:**

```sql
ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
```

Fits group-wide first/last/nth.

**Last three rows, including current:**

```sql
ROWS BETWEEN 2 PRECEDING
         AND CURRENT ROW
```

Fits first/last values over a three-transaction sliding window.

**Current row and next row:**

```sql
ROWS BETWEEN CURRENT ROW
         AND 1 FOLLOWING
```

Fits local comparisons and simple "next event" lookups.

**Five rows centered around current row:**

```sql
ROWS BETWEEN 2 PRECEDING
         AND 2 FOLLOWING
```

Fits neighborhood analysis, noting frames near partition start/end contain fewer rows.

### 21.2. Not every boundary combination is valid

Frame syntax enforces ordering rules: the start bound cannot follow the end bound in valid order, nor can arbitrary offset types/combinations be mixed.

Furthermore, if a frame expression evaluates to an invalid value such as a negative offset, PostgreSQL will raise a runtime error. Application parameters must be validated rather than blindly concatenated into SQL strings.

### 21.3. Short frames and `nth_value`

When a frame holds fewer rows than position `n`, `nth_value` returns `NULL`. This also occurs where frames shrink near partition start/end boundaries.

Do not assume every frame always holds the exact requested count just because you wrote `2 PRECEDING` or `2 FOLLOWING`. Rows outside the partition are never included.

## 22. Frames can exclude specific rows with `EXCLUDE`

PostgreSQL supports frame exclusion syntax such as:

- `EXCLUDE CURRENT ROW`.
- `EXCLUDE GROUP`.
- `EXCLUDE TIES`.
- `EXCLUDE NO OTHERS`.

These alter which rows **actually remain in the frame** once boundaries are determined.

### 22.1. Excluding the current row itself

```sql
SELECT
    sale_id,
    seller,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS earlier_row_count
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

`earlier_row_count` returns **0, 1, 2, 3, 4**.

While not required for the three value functions, this shows that **rows can still be excluded from a frame** after start/end bounds are chosen.

### 22.2. Effect on `last_value`

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS previous_seller_by_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

With unique ordering, this gives the last seller among **strictly preceding rows**:

| sale_id | seller | previous_seller_by_frame |
| ---: | --- | --- |
| 1 | An | NULL |
| 2 | Bình | An |
| 3 | Chi | Bình |
| 4 | Dung | Chi |
| 5 | Em | Dung |

It looks like `LAG(seller)`, expressed differently via frame and exclusion. If you just want the preceding row, `LAG` remains clearer.

### 22.3. `EXCLUDE GROUP` and `EXCLUDE TIES`

With `ORDER BY sold_on` and two sales on the same date:

- `EXCLUDE GROUP` removes the entire current **peer group** from the frame, including the current row.
- `EXCLUDE TIES` removes **other peers** of the current row while keeping the current row (if inside the frame).

These options help analyze "earlier date groups excluding the current date" or control peer handling.

Still, before reaching for them, ask whether business rules count **transactions** or **active dates**. Often a CTE aggregating by day first is much simpler than a multi-layered frame.

## 23. Quick comparison: running frame vs. full frame

The same function can give different answers:

| Function | Running frame: start to current | Full frame: entire partition |
| --- | --- | --- |
| `first_value(seller)` | First person from group start (usually constant) | First person of entire group |
| `last_value(seller)` | Last person **up to current**; often the current row | Last person of **entire group** |
| `nth_value(seller, 2)` | `NULL` until frame has two rows; then second person | Second person of entire group, even on row 1 |
| `nth_value(revenue, 3)` | `NULL` until three rows; also `NULL` if third value is `NULL` | Value of third row of entire group, possibly `NULL` |

An illustrative query:

```sql
SELECT
    sale_id,
    seller,
    first_value(seller) OVER w_running AS first_running,
    last_value(seller)  OVER w_running AS last_running,
    nth_value(seller, 2) OVER w_running AS second_running,
    first_value(seller) OVER w_full AS first_full,
    last_value(seller)  OVER w_full AS last_full,
    nth_value(seller, 2) OVER w_full AS second_full
FROM window_lab.sales
WHERE team = 'North'
WINDOW
    w_running AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY sold_on, sale_id;
```

For North, the *full* columns are always:

```text
first_full  = An
last_full   = Em
second_full = Bình
```

Whereas *running* changes by row; in particular, `last_running` tracks the current seller.

## 24. Practical example: initial, final, and third price

Suppose a price table tracks daily history:

```sql
CREATE TABLE window_lab.product_prices (
    price_id bigint PRIMARY KEY,
    product_id text NOT NULL,
    effective_on date NOT NULL,
    price numeric(12,2) NOT NULL
);

INSERT INTO window_lab.product_prices
    (price_id, product_id, effective_on, price)
VALUES
    (11, 'P-A', DATE '2026-01-01', 100.00),
    (12, 'P-A', DATE '2026-01-10', 120.00),
    (13, 'P-A', DATE '2026-01-20', 110.00),
    (14, 'P-B', DATE '2026-01-05',  50.00),
    (15, 'P-B', DATE '2026-01-15',  60.00);
```

### 24.1. First and last historical price per product

```sql
SELECT
    product_id,
    effective_on,
    price,
    first_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_price,
    last_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_price,
    nth_value(price, 3) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS third_price
FROM window_lab.product_prices
ORDER BY product_id, effective_on, price_id;
```

Result by product:

| product_id | first_price | last_price | third_price |
| --- | ---: | ---: | ---: |
| P-A | 100.00 | 110.00 | 110.00 |
| P-B | 50.00 | 60.00 | NULL |

**Do not confuse last price with MAX(price):** for product P-A, the last historical price is **110**, whereas the highest recorded price was **120**.

### 24.2. Difference from initial price

```sql
SELECT
    product_id,
    effective_on,
    price,
    price - first_value(price) OVER (
        PARTITION BY product_id
        ORDER BY effective_on, price_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS change_from_initial_price
FROM window_lab.product_prices
ORDER BY product_id, effective_on, price_id;
```

For P-A:

- Jan 01: 100 − 100 = 0.
- Jan 10: 120 − 100 = 20.
- Jan 20: 110 − 100 = 10.

This is a clean fit for `first_value`: the first price serves as a **baseline** against which all subsequent rows are compared.

### 24.3. Period-start and period-end require specifying the filtered set

If you analyze prices in February yet no rows have `effective_on` in February, restricting `WHERE effective_on` to February produces an **empty set** with no start/end prices, even though products carry active prices from January.

For **"price active on date X"**, you need logic picking the latest record with `effective_on <= X`, not simply `last_value` over rows created **during** date X.

Window functions are powerful, yet they do not replace distinguishing "events occurring in a period" from "state effective during a period".

## 25. Practical example: cohort reporting and each user's first/last event

Suppose a user-event table has:

```text
user_id
event_id
event_time
event_type
```

To attach each user's **first** and **last** event type onto every event:

```sql
-- Illustrative schema, not part of the demo tables created:
SELECT
    user_id,
    event_id,
    event_time,
    event_type,
    first_value(event_type) OVER (
        PARTITION BY user_id
        ORDER BY event_time, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_event_type,
    last_value(event_type) OVER (
        PARTITION BY user_id
        ORDER BY event_time, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_event_type
FROM user_events;
```

Key points:

- `event_time` needs clear time semantics, typically `timestamptz`.
- `event_id` breaks ties when two events share the same timestamp.
- If `WHERE` narrows to a date range in the same `SELECT`, "first/last" is within the **filtered range**.
- To keep the first event type across **all history**, compute in an unfiltered query layer before filtering output.

### 25.1. First and last do not define user sessions

If you need the first or last event of a *session*, you need a `session_id` and defined session rules. An event stream does not split into sessions merely by being sorted chronologically.

Similarly, `nth_value(event_type, 3)` returns the **third event in order**, not "the third event of a session" unless you `PARTITION BY user_id, session_id`.

## 26. `ORDER BY` with NULLs and collations

Not only can `expression` be `NULL`; the **sort key** itself can be `NULL` in other datasets.

In `window_lab.sales`, `sold_on` is `NOT NULL` so ordering is simple. If a date column allows `NULL`, decide:

- Should `NULL` sort before valid dates?
- Does `NULL` mean "unknown date" or "not applicable"?
- Should `NULL` rows be excluded before computing first/last?

### 26.1. Using `NULLS FIRST` or `NULLS LAST`

Example sorting descending by revenue:

```sql
SELECT
    sale_id,
    seller,
    revenue,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY revenue DESC NULLS LAST, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS highest_recorded_seller
FROM window_lab.sales
ORDER BY team, sale_id;
```

`NULLS LAST` ensures rows with `revenue NULL` are not selected first simply because of PostgreSQL's default descending NULL placement.

If you want "first sale" chronologically, do not sort by revenue; choose the right business key.

### 26.2. Text ORDER BY and collations

If sorting by name:

```sql
ORDER BY seller
```

ordering depends on the expression's collation. Accented Vietnamese names can compare differently across locales/collations.

If business rules require "first alphabetically", define the collation and case/accent handling. When a deterministic tie-break among equal names is needed, append a unique key:

```sql
ORDER BY seller, sale_id
```

Choosing a collation is a **data-semantics decision**; not every system should force `COLLATE "C"` solely for byte order.

## 27. Window frames and aggregate functions: same syntax, different impact

Frames do not only govern `first_value`, `last_value`, and `nth_value`. Aggregates used as window functions also depend on frames.

### 27.1. Running total

```sql
SELECT
    sale_id,
    seller,
    revenue,
    SUM(revenue) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_revenue
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

In North, `SUM` ignores `NULL` and accumulates as:

| sale_id | revenue | running_revenue |
| ---: | ---: | ---: |
| 1 | 100.00 | 100.00 |
| 2 | 180.00 | 280.00 |
| 3 | NULL | 280.00 |
| 4 | 90.00 | 370.00 |
| 5 | 140.00 | 510.00 |

Unlike `last_value(revenue)` on row 3 returning **NULL**, `SUM(revenue)` remains 280 because aggregates **ignore NULL values**.

### 27.2. Full-partition sum

```sql
SUM(revenue) OVER (
    PARTITION BY team
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
```

or simply:

```sql
SUM(revenue) OVER (PARTITION BY team)
```

yields the full group sum. Without `ORDER BY`, the default frame spans the entire partition.

Practical note: for an aggregate seeking the full group total, **omitting `ORDER BY` inside `OVER`** is usually clearest. For `first_value` and `last_value`, omitting `ORDER BY` makes "first/last" lack deterministic meaning.

### 27.3. Not all window functions use frames identically

`ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, and `LEAD` have their own partition/ordering semantics; frames do not control their output the same way they control `first_value`, `last_value`, `nth_value`, or frame-based aggregates.

Even if you understand frames for `SUM`, keep **positional value functions** clearly in mind; never extrapolate mechanically from one window function category to all others.

## 28. Performance: sorting, partitioning, and row volume

Window functions shine by avoiding repeated self-JOINs, yet on large data they carry cost.

### 28.1. PostgreSQL must establish the required order

A query like:

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales;
```

may need to sort by `(team, sold_on, sale_id)` or leverage pre-ordered data from an appropriate scan/index.

On tiny tables, sorting is negligible. On millions of records, sorting consumes CPU, memory, and I/O.

### 28.2. Candidate index

```sql
CREATE INDEX idx_sales_team_date_id
ON window_lab.sales (team, sold_on, sale_id);
```

This is a **candidate** because its index key matches the frequently used partition and window order.

However, creating an index does not mean every window query uses it efficiently. PostgreSQL may still pick sequential scan + sort, especially when reading most of the table or needing many non-index columns.

Evaluate indexes based on:

- Table size.
- `WHERE` predicates.
- Cardinality/distribution of `team`.
- Row count and size per partition.
- Heap fetch cost vs. index scan cost.
- Write throughput and index maintenance overhead.

### 28.3. Inspecting `EXPLAIN`

```sql
EXPLAIN
SELECT
    sale_id,
    team,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

You may encounter:

- `WindowAgg`: evaluates window functions.
- `Sort` or `Incremental Sort`: prepares ordering.
- `Seq Scan` / `Index Scan`: reads table data.
- Other nodes depending on the plan.

`EXPLAIN (ANALYZE, BUFFERS)` executes the query to measure actual rows, timing, and buffers. Do not run it on production without assessing load; on write statements, `EXPLAIN ANALYZE` executes the side effects.

### 28.4. Full frames may buffer more data than running frames

When a function needs the last value of the **entire partition**, the engine must reach or track the final row; depending on the plan, this can involve buffering/spooling large partitions. Consequently, `ROWS ... UNBOUNDED FOLLOWING` does not always have the exact same resource profile as a running sum needing only past rows.

Still, never claim full frames are always slower: actual cost depends on the function, row width, partition count, indexes, memory, and planner execution.

If you strictly need **one final row per group**, `DISTINCT ON` or `ROW_NUMBER() ... WHERE rn=1` at an outer query level can be simpler than computing the final value and repeating it across every transaction.

### 28.5. Multiple window definitions can add extra sorts

If a report computes simultaneously:

- First by ascending date.
- First by descending revenue.
- Second-from-last by descending date.

then the windows have **different sort orders**. PostgreSQL may need extra `Sort`/`WindowAgg` steps. Share one ordering convention when business rules allow, and reverse order only where genuinely required.

Never alter report semantics solely to merge functions into one `WINDOW`: correctness always takes precedence over performance.

## 29. Common mistakes with the three value functions

| Mistake or misconception | Consequence | How to fix |
| --- | --- | --- |
| `last_value` with no frame specified | Usually returns current row / last peer, not team end | Use a full frame when partition end is needed |
| Treating `CURRENT ROW` in `RANGE` as strictly current row | Includes/ignores peer rows unexpectedly | Understand peer groups or use `ROWS` appropriately |
| `ORDER BY sold_on` with ties | First/last/nth can be unstable | Add `sale_id` or a tie-breaker criterion |
| Omitting `ORDER BY` inside `OVER` | "First/last" lacks business ordering | Put `ORDER BY` inside `OVER` |
| Only having `ORDER BY` at the end of `SELECT` | Does not define window order | `ORDER BY` must be inside `OVER` |
| Using `nth_value(..., 2)` expecting values on all rows | Early running frame has fewer than two rows | Open a full frame if group-wide 2nd is needed |
| `nth_value` returns `NULL` and concluding no row exists | Row may exist with a `NULL` expression | Check position, row count, and `NULL`s |
| Treating `nth_value` as "nth from end" | PostgreSQL counts from frame start | Reverse `ORDER BY` appropriately |
| Using `MIN` instead of `first_value` | Picks smallest value rather than earliest | Clarify the ordering criterion |
| Using `MAX` instead of `last_value` | Picks largest value rather than chronologically last | Use `last_value`/full frame |
| Using `first_value` to return one row per group | Retains all source rows | Use `DISTINCT ON` or `ROW_NUMBER` |
| Filtering with `WHERE` before window when full history is needed | First/last computed over filtered data | Compute window in a CTE before display filtering |
| Treating `ROWS 2 PRECEDING` as "2 days prior" | Counts rows, not days | Use time-based `RANGE` or a calendar |
| Treating `GROUPS` as row count | A peer group can span multiple rows | Remember `GROUPS` counts peer groups |
| Writing `RANGE` offset with multiple `ORDER BY` keys | Violates `RANGE` offset syntax rules | Use a single compatible `ORDER BY` key |
| Expecting `IGNORE NULLS` like another DBMS | PostgreSQL does not support that option | Filter non-nulls in a separate query/CTE |
| Sorting revenue `DESC` without `NULLS LAST` | `NULL`s can sort first | Specify `NULLS LAST` when business logic requires |
| Testing only on tie-free datasets | Peer-group bugs stay hidden | Test multiple rows sharing identical keys |
| Treating ID as timestamp without verification | "Last" can be business-wrong | Use timestamp + tie-breaker key |
| Running uncontrolled windows on millions of rows | Heavy sort/buffer resource usage | Check `EXPLAIN`, suitable indexes, workload limits |
| Filtering window alias in same-level `WHERE` | Query error | Use an outer CTE or subquery |

## 30. Practice exercises with answers

All exercises below use `window_lab.sales`, except those explicitly specifying `product_prices`.

### Exercise 1. First seller per team

Requirement: add a column showing the first seller by `(sold_on, sale_id)` on **every transaction row**.

```sql
SELECT
    team,
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS first_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Answer:** East → Lan; North → An; South → Giang.

### Exercise 2. Last seller per team

```sql
SELECT
    team,
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Answer:** East → Lan; North → Em; South → Khánh.

### Exercise 3. Why does the following query not repeat Em on every North row?

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS result
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** the default frame is `RANGE UNBOUNDED PRECEDING ... CURRENT ROW`, and unique ordering ends the frame at the current row. `last_value` returns the current row's seller, not Em across all rows.

### Exercise 4. Second sale of each team

```sql
SELECT
    team,
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_seller
FROM window_lab.sales
ORDER BY team, sold_on, sale_id;
```

**Answer:** East `NULL`; North Bình; South Hà.

### Exercise 5. Why does East return `nth_value(seller, 2) = NULL`?

**Answer:** East has only one row, so within the full frame there is no second row.

### Exercise 6. Why does North return `nth_value(revenue, 3) = NULL` despite having five rows?

**Answer:** the third row is Chi, and `Chi.revenue` is `NULL`. It is not a missing third row.

### Exercise 7. Running `nth_value(seller, 2)` on the default frame

```sql
SELECT
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
    ) AS second_so_far
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** `NULL, Bình, Bình, Bình, Bình` respectively.

### Exercise 8. Which two same-date sales form a peer group?

In North:

```sql
ORDER BY sold_on
```

**Answer:** Bình (ID 2) and Chi (ID 3) are peers, sharing date Jan 05.

If `sale_id` is added to `ORDER BY`, they are no longer peers.

### Exercise 9. What is the default RANGE count at Bình?

```sql
SELECT
    sale_id,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
    ) AS cnt
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** at Bình, `cnt = 3`, because the default frame includes An and both Jan 05 peer rows.

### Exercise 10. Getting the first seller among the three most recent sales

```sql
SELECT
    sale_id,
    seller,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    ) AS oldest_in_last_three
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** An, An, An, Bình, Chi.

### Exercise 11. Getting the second seller among the three most recent sales

**Answer:**

```sql
SELECT
    sale_id,
    seller,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS second_in_frame
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

Result: `NULL`, Bình, Bình, Chi, Dung.

### Exercise 12. Why is `ROWS 2 PRECEDING` not two days earlier?

**Answer:** `ROWS` counts **rows**, not time intervals. If a single day has 100 transactions, two rows prior can still fall on the current date.

### Exercise 13. Difference between `ROWS` and `GROUPS`

```sql
SELECT
    sale_id,
    sold_on,
    COUNT(*) OVER (
        PARTITION BY team
        ORDER BY sold_on
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS cnt
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** row counts in the date-based frame are 1, 3, 3, 3, 2. `GROUPS` counts date groups, not one preceding row.

### Exercise 14. Getting the second-to-last sale of each team

```sql
SELECT
    team,
    sale_id,
    nth_value(seller, 2) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS second_from_end
FROM window_lab.sales
ORDER BY team, sale_id;
```

**Answer:** East `NULL`; North Dung; South Huy.

### Exercise 15. Getting each team's last seller using `first_value`

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on DESC, sale_id DESC
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS newest_seller
FROM window_lab.sales
ORDER BY team, sale_id;
```

**Answer:** East Lan; North Em; South Khánh.

### Exercise 16. How do two approaches for getting the latest row differ?

Compare:

- Full-frame `last_value(seller)`.
- `SELECT DISTINCT ON (team) ... ORDER BY team, sold_on DESC, sale_id DESC`.

**Answer:** the first appends the final seller to **every row of the team**; the second **keeps only one representative latest row** per team.

### Exercise 17. Retrieving everyone on North's second active sale date

```sql
WITH by_day AS (
    SELECT
        sale_id,
        team,
        seller,
        sold_on,
        DENSE_RANK() OVER (
            PARTITION BY team
            ORDER BY sold_on
        ) AS day_rank
    FROM window_lab.sales
)
SELECT sale_id, seller, sold_on
FROM by_day
WHERE team = 'North' AND day_rank = 2
ORDER BY sale_id;
```

**Answer:** Bình and Chi, both on Jan 05. `nth_value(...,2)` only picks **one row**, not all peers.

### Exercise 18. If filtering to sales from Jan 06 onward before `first_value`, does North still have An?

**Answer:** no. `WHERE sold_on >= '2026-01-06'` removes An, Bình, and Chi before the window runs. First in North's filtered set is Dung.

If you need **all-time first** in the current report, compute the window in a CTE first and filter outside.

### Exercise 19. Is the last historical price always `MAX(price)`?

Using `window_lab.product_prices`.

**Answer:** no. P-A has a final price of 110, yet its max price was 120 on Jan 10. One function depends on **chronological order**, the other on **maximum value**.

### Exercise 20. Finding Chi's nearest non-NULL revenue

**Answer:** `180.00` from Bình. `last_value(revenue)` with a running frame at Chi returns `NULL` because `Chi.revenue` is `NULL`; PostgreSQL does not support `IGNORE NULLS` for this function. Use `LATERAL` or a dedicated query filtering `revenue IS NOT NULL` to pick the nearest row.

### Exercise 21. What does `EXCLUDE CURRENT ROW` do?

```sql
SELECT
    sale_id,
    seller,
    last_value(seller) OVER (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
        EXCLUDE CURRENT ROW
    ) AS previous_seller
FROM window_lab.sales
WHERE team = 'North'
ORDER BY sold_on, sale_id;
```

**Answer:** `NULL`, An, Bình, Chi, Dung. For this simple requirement, `LAG(seller)` is usually shorter.

### Exercise 22. Why is `NULLS LAST` needed when ordering by revenue DESC?

**Answer:** omitting the `NULL` rule lets a row without revenue sort ahead of real values under PostgreSQL's descending order. That could make `first_value(seller)` pick a seller with unknown revenue instead of the highest-revenue seller.

### Exercise 23. When should `RANGE INTERVAL '4 days' PRECEDING` be used?

**Answer:** when you want transactions from the **past four days up to the current row**, instead of a fixed **row count**. It requires a single time-based `ORDER BY` key and a compatible offset.

### Exercise 24. What should be used to read the preceding row without caring about frames?

**Answer:** `LAG`; for the following row use `LEAD`. `first_value`, `last_value`, and `nth_value` fit when you need a position inside a **frame**.

### Exercise 25. Distinguishing ORDER BY inside OVER vs. outside SELECT

```sql
SELECT
    sale_id,
    team,
    first_value(seller) OVER (
        PARTITION BY team ORDER BY sold_on, sale_id
    ) AS first_seller
FROM window_lab.sales
ORDER BY sale_id DESC;
```

**Answer:** the window still orders by `sold_on, sale_id` within each team. `ORDER BY sale_id DESC` at the end merely displays the result rows in descending ID order.

### Exercise 26. Can `first_value` change across rows of the same team?

**Answer:** yes. With a **sliding frame** like `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`, the first row of the frame advances from An to Bình and Chi as new sales arrive.

### Exercise 27. Why does a full frame not resolve tie ordering?

**Answer:** a full frame defines the **scope of rows**, yet if `ORDER BY sold_on` has multiple rows on the same date, who comes before/after within the peer group remains undefined. A meaningful tie-breaker key is required.

### Exercise 28. Writing two named windows: full and recent

```sql
SELECT
    sale_id,
    team,
    seller,
    last_value(seller) OVER w_full AS last_of_team,
    first_value(seller) OVER w_recent AS first_in_recent_three
FROM window_lab.sales
WINDOW
    w_full AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ),
    w_recent AS (
        PARTITION BY team
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING
                 AND CURRENT ROW
    )
ORDER BY team, sold_on, sale_id;
```

**Answer:** the SQL retrieves both the team-wide last seller and the first seller among the three most recent sales without repeating verbose frame definitions.

## 31. Checklist before using `first_value`, `last_value`, `nth_value` in an application

| Question | What to determine |
| --- | --- |
| "First" and "last" by what criterion? | Date, timestamp, price, ID, or priority |
| Is partitioning needed? | `PARTITION BY` the right business key |
| Is ordering uniquely determined? | Add a tie-breaker key if ties exist |
| Need in-period values or full history? | Placement of `WHERE` and CTE layers |
| Need full partition or running frame? | Specify the frame explicitly |
| Using default `RANGE`? | Remember it includes peers at `CURRENT ROW` |
| Sample has multiple rows on the same date? | Test `ROWS`, `RANGE`, and `GROUPS` as appropriate |
| Need n rows or n days? | `ROWS` differs from `RANGE` and `GROUPS` |
| Could `nth_value` have too few rows? | Handle `NULL`s early in the period or in small groups |
| Could the value at the selected position be `NULL`? | `NULL` does not always mean a missing row |
| Need to ignore `NULL`s? | PostgreSQL has no `IGNORE NULLS`; use a separate query |
| Need nth from the end? | Reverse sort direction properly, including the tie-breaker |
| Only need one row per group? | Consider `DISTINCT ON`/`ROW_NUMBER` |
| Need preceding/following row? | `LAG`/`LEAD` usually expresses it better |
| Is `ORDER BY` outside `SELECT` enough? | No: windows need their own `ORDER BY` |
| Multiple frames in one `SELECT`? | Use meaningful named windows |
| Sliding frame near partition boundary? | Actual row count may be less than n |
| Using collations or `NULLS` ordering? | Define text and `NULL` ordering explicitly |
| Does an index match partition + order? | Inspect `EXPLAIN`, do not guess |
| High sort/buffer cost? | Measure on realistic data and workloads |
| Tested single-row and tied-key groups? | Those edge cases reveal bugs quickly |
| Verified output against business rules? | Valid SQL execution alone does not prove correctness |

## 32. Summary

All three window value functions in PostgreSQL share the same foundation: **selecting a value from a position inside a window frame**.

1. **`first_value(expression)`** reads the **first row of the frame**.
2. **`last_value(expression)`** reads the **last row of the frame**. By default when `ORDER BY` is present, it is **not necessarily** the end of the entire partition.
3. **`nth_value(expression, n)`** reads the **nth row from the start of the frame**, starting at `n = 1`; it returns `NULL` if fewer than `n` rows exist or if the value at that position is `NULL`.
4. **`PARTITION BY`** defines groups; **`ORDER BY` inside `OVER`** defines order; the **frame** defines which rows the function sees.
5. **The default frame with `ORDER BY`** equals `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` and includes **peer rows**.
6. To get the **first/last/nth of the entire group**, explicitly write `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`.
7. To get values across the **three most recent transactions**, use `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`; first/nth then slide with the current position.
8. **`ROWS`, `RANGE`, and `GROUPS` are not interchangeable**: they count rows, value intervals, and peer groups differently.
9. **`ORDER BY` must be deterministic** for stable nth or last rows. When ties exist, add a meaningful tie-breaker.
10. PostgreSQL **does not support `IGNORE NULLS`** for these functions. To obtain the first/last non-NULL value, select non-NULL rows via another approach.
11. Window functions **do not collapse a group into one row**. For top 1 per group, consider `DISTINCT ON` or `ROW_NUMBER`.
12. **`WHERE` filters before window evaluation** at the same query level. To display all-time values on filtered rows, compute in a CTE/subquery first and filter outside.

An easy-to-remember safe pattern for reporting first/last/nth per group:

```sql
SELECT
    team,
    sale_id,
    first_value(seller) OVER whole_group AS first_seller,
    last_value(seller)  OVER whole_group AS last_seller,
    nth_value(seller, 2) OVER whole_group AS second_seller
FROM window_lab.sales
WINDOW whole_group AS (
    PARTITION BY team
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
)
ORDER BY team, sold_on, sale_id;
```

**Core rule:** before choosing `first_value`, `last_value`, or `nth_value`, answer three questions: **which partition, which ordering, and which frame?** It is usually the third answer that determines whether the query returns the exact "first/last/nth" users expect.
