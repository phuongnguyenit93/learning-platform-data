# UPDATE FROM and the Risk of Multiple Source Rows Matching One Target Row in PostgreSQL

In sales systems, product prices can be updated from a new price feed table; inventory balances can be aggregated from multiple movements; order statuses can be updated from payment events. PostgreSQL supports the **`UPDATE ... FROM`** syntax to pull data from one or more source tables when modifying a target table. This syntax is concise and powerful, but carries a major risk: **if the same target row matches multiple source rows, PostgreSQL does not guarantee which source row will be chosen to supply the updated value**.

For example, suppose the `products` table has SKU `BK-01`, while the incoming price feed has two proposals for that SKU: `110000` and `115000`. Running `UPDATE products SET price = feed.new_price FROM price_feed AS feed WHERE products.sku = feed.sku` may replace the price with either proposal. The actual result depends on query execution, **not a "latest row wins" rule**, unless you explicitly express that rule in SQL.

This lesson focuses on:

1. Syntax and semantics of `UPDATE ... FROM` in PostgreSQL.
2. Recognizing **one-to-one**, **many-to-one**, and **one-target-matching-many-source** relationships.
3. Why `RETURNING` or arbitrary `ORDER BY` clauses do not turn an ambiguous update into a correct one.
4. Remediation strategies: **`GROUP BY`**, **`DISTINCT ON` with a deterministic total ordering**, **`ROW_NUMBER()`**, **scalar subqueries**, and **staging tables with `UNIQUE`**.
5. Handling unmatched sources, `NULL` values, duplicates introduced by multi-table joins, transactions, concurrency, performance, and pre-write impact checks.

The examples are written for modern PostgreSQL with self-contained data in a practice schema. Statements that modify data are wrapped in transactions with `ROLLBACK` when the goal is inspection. **Never practice directly on production tables.**

## 1. Learning Objectives

After this lesson, you should be able to:

- Read `UPDATE target AS t SET ... FROM source AS s WHERE ...` and distinguish the `SET` assignments from source row selection.
- Explain why **each target row must match at most one meaningful source row** to avoid ambiguous updates.
- Detect multiply matched SKUs/IDs beforehand using `SELECT` and `GROUP BY ... HAVING COUNT(*) > 1`.
- Select the intended source row by rules like **latest timestamp, highest priority, valid status**, using secondary keys as *tie-breakers*.
- Understand why plain `DISTINCT`, `MAX(price)`, or `LIMIT 1` without a clear order usually fail to solve the problem.
- Compare `UPDATE ... FROM` with **scalar subqueries** when the source returns 0, 1, or multiple rows.
- Use `RETURNING`, transactions, and staging tables to make data modifications auditable.
- Identify scenarios requiring indexes, unique constraints, concurrent-write controls, or data model changes.

## 2. General Syntax of UPDATE FROM

Core pattern:

~~~sql
UPDATE target_table AS t
SET target_column = s.source_value
FROM source_table AS s
WHERE t.business_key = s.business_key;
~~~

Role of each component:

| Component | Meaning |
| --- | --- |
| `UPDATE target_table AS t` | Identifies the table **being modified** |
| `SET target_column = ...` | Specifies the new value for the target column |
| `FROM source_table AS s` | Supplies the **data source** table/relation for expressions and predicates |
| `WHERE t.key = s.key` | Joins target rows to source rows and selects which target rows are updated |
| `RETURNING ...` | Returns information about the updated rows |

### 2.1. How Does It Differ from SELECT JOIN?

A `SELECT ... JOIN` query can return **multiple result rows** for the same left-hand row when multiple matches exist. In `UPDATE ... FROM`, PostgreSQL builds the join for the update; if the join yields multiple rows for the same target row, **one joined row is used** to supply values for that target row, yet PostgreSQL **makes no promise about which one is picked**.

~~~text
Target table products              Source table price_feed
-------------------------          ------------------------------
SKU = BK-01 | price=100000          SKU=BK-01 | new_price=110000
                                    SKU=BK-01 | new_price=115000

JOIN result:
    BK-01 + 110000
    BK-01 + 115000
          |
          v
UPDATE receives only one source row for BK-01,
with no rule guaranteeing 110000 or 115000.
~~~

**Do not interpret this as two sequential updates to the same product.** PostgreSQL documentation notes that when multiple joined rows match a single target row, only **one** of the joined rows is used to update the target row, and which one is unpredictable. In business systems, treat this case as a **query design bug** until a single deterministic source row is ensured.

### 2.2. Never Assume PostgreSQL Will Pick the "Last Row"

Dangerous assumptions:

- "The newer row was inserted into the source later, so `UPDATE` picks the newer row."
- "`feed_id` is larger, so it gets chosen automatically."
- "In my test `SELECT` this row came first, so `UPDATE` will use it."
- "Adding an index will make the selection order deterministic."
- "I ran it three times and got the same price, so the behavior is guaranteed."

None of these are **semantic guarantees** of `UPDATE ... FROM` when multiple source rows match. PostgreSQL can switch execution plans whenever data, statistics, indexes, or server versions change.

### 2.3. The WHERE Condition Must Be Carefully Designed

In PostgreSQL, `UPDATE` does not syntactically require `WHERE`. However, omitting or miswriting the join predicate can update **far too many target rows unintentionally**:

~~~sql
-- WARNING: example missing a proper join condition.
-- Do not run on real data.
--
-- UPDATE products AS p
-- SET unit_price = f.new_price
-- FROM price_feed AS f;
~~~

This query fails to join `p.sku` with `f.sku`; it forms a cross-join between target and source and can assign arbitrary values. `FROM` **does not automatically infer join keys**.

## 3. Creating the Practice Dataset

We simulate an application synchronizing **current product prices** from price-proposal records. Each product has a unique SKU; each SKU can receive multiple price proposals over time.

Run this in a lab database where you have schema-creation privileges. If `upd_lab_201` already exists with data, use another schema name rather than deleting existing data.

### 3.1. Target Table: products

~~~sql
CREATE SCHEMA upd_lab_201;

CREATE TABLE upd_lab_201.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    price_source_note TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

`sku` is the business key used for matching data. `UNIQUE(sku)` ensures each SKU maps to a single target product in this table.

~~~sql
INSERT INTO upd_lab_201.products
    (product_id, sku, product_name, unit_price)
VALUES
    (1, 'BK-01',    'PostgreSQL Book',    100000),
    (2, 'MOUSE-01', 'Wireless Mouse',     250000),
    (3, 'PEN-01',   'Ballpoint Pen',       15000),
    (4, 'CABLE-01', 'USB-C Cable',        120000),
    (5, 'BAG-01',   'Backpack',           200000);
~~~

### 3.2. Source Table: price_feed

~~~sql
CREATE TABLE upd_lab_201.price_feed (
    feed_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    new_price NUMERIC(12, 2) NOT NULL
        CHECK (new_price >= 0),
    feed_at TIMESTAMPTZ NOT NULL,
    provider TEXT NOT NULL,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_price_feed_sku_approved_time
ON upd_lab_201.price_feed
    (sku, feed_at DESC, feed_id DESC)
WHERE is_approved;
~~~

There is no `UNIQUE(sku)` on the feed table because **multiple price proposals per SKU are valid data**. Nor is there an FK from `price_feed.sku` to `products.sku`, allowing us to observe source rows whose SKU does not exist in the target.

### 3.3. Load Price-Proposal Records

~~~sql
INSERT INTO upd_lab_201.price_feed
    (
        feed_id, sku, new_price, feed_at,
        provider, is_approved
    )
VALUES
    (
        101, 'BK-01', 110000,
        TIMESTAMPTZ '2026-11-11 09:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        102, 'BK-01', 115000,
        TIMESTAMPTZ '2026-11-12 09:00:00+07',
        'VENDOR-B', TRUE
    ),
    (
        103, 'MOUSE-01', 270000,
        TIMESTAMPTZ '2026-11-12 11:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        104, 'PEN-01', 16000,
        TIMESTAMPTZ '2026-11-12 12:00:00+07',
        'VENDOR-A', FALSE
    ),
    (
        105, 'CABLE-01', 130000,
        TIMESTAMPTZ '2026-11-13 09:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        106, 'CABLE-01', 125000,
        TIMESTAMPTZ '2026-11-13 09:00:00+07',
        'VENDOR-B', TRUE
    ),
    (
        107, 'UNKNOWN-01', 90000,
        TIMESTAMPTZ '2026-11-13 15:00:00+07',
        'VENDOR-A', TRUE
    ),
    (
        108, 'MOUSE-01', 265000,
        TIMESTAMPTZ '2026-11-10 09:00:00+07',
        'VENDOR-B', TRUE
    );
~~~

The dataset is intentionally designed to cover diverse scenarios:

| SKU | Feed Rows | Characteristics |
| --- | --- | --- |
| `BK-01` | 101, 102 | **Two approved rows**, different timestamps |
| `MOUSE-01` | 103, 108 | **Two approved rows**, newest price differs from older one |
| `CABLE-01` | 105, 106 | Two approved rows with **identical timestamps**, requires tie-break |
| `PEN-01` | 104 | Only has an **unapproved** proposal |
| `BAG-01` | None | Product **has no source rows** |
| `UNKNOWN-01` | 107 | Source has a SKU **absent from target** |

### 3.4. Inspect Data Before Updating

~~~sql
SELECT
    product_id, sku, unit_price, price_source_note
FROM upd_lab_201.products
ORDER BY product_id;
~~~

Expected:

| ID | SKU | Current Price |
| ---: | --- | ---: |
| 1 | BK-01 | 100.000 |
| 2 | MOUSE-01 | 250.000 |
| 3 | PEN-01 | 15.000 |
| 4 | CABLE-01 | 120.000 |
| 5 | BAG-01 | 200.000 |

Every `price_source_note` starts as `NULL`.

## 4. A Valid UPDATE FROM Example When the Source Is Unique

Suppose we update only from one explicitly identified feed row:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET
    unit_price = f.new_price,
    price_source_note = 'feed=' || f.feed_id::text,
    updated_at = clock_timestamp()
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.feed_id = 103
  AND f.is_approved
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    f.feed_id AS chosen_feed_id;

ROLLBACK;
~~~

Here `feed_id` is the primary key. `f.feed_id=103` identifies **exactly one** source row, targeting `MOUSE-01` with price `270000`. The statement updates **one** target row in the transaction, then `ROLLBACK` preserves the seed data.

**Key takeaway:** `UPDATE ... FROM` is not inherently flawed. It works cleanly when the join condition produces **at most one source row per target row** or when you have explicitly reduced the source to a unique relationship.

## 5. Dangerous Example: Multiple Feed Rows Matching the Same Product

Consider:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET
    unit_price = f.new_price,
    price_source_note = 'feed=' || f.feed_id::text
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    f.feed_id AS chosen_feed_id;

-- Inspect inside transaction only; do not commit an ambiguous example.
ROLLBACK;
~~~

The problem:

- `BK-01` matches two rows `101`/`102`, priced `110000`/`115000`.
- `MOUSE-01` matches two rows `103`/`108`, priced `270000`/`265000`.
- `CABLE-01` matches two rows `105`/`106`, priced `130000`/`125000`.

PostgreSQL **does not guarantee** picking the newest feed, highest ID, or highest price. `RETURNING f.feed_id` only lets you **observe which source row happened to be used on that run**; it does not make the choice deterministic.

### 5.1. Three Target Rows, Six Joined Rows

Before running `UPDATE`, inspect the join set:

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.unit_price AS old_price,
    f.feed_id,
    f.new_price,
    f.feed_at
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
WHERE f.is_approved
ORDER BY p.product_id, f.feed_at DESC, f.feed_id DESC;
~~~

The result has **6 joined rows** for **3 target products**:

| Product | Matching Feed Rows |
| --- | --- |
| BK-01 | 102, 101 |
| MOUSE-01 | 103, 108 |
| CABLE-01 | 106, 105 |

`PEN-01` does not match because its only proposal is unapproved; `BAG-01` has no feed; `UNKNOWN-01` has no target product.

### 5.2. Do Not Confuse Joined Row Count with Updated Row Count

Seeing six rows from `SELECT ... JOIN` does **not** mean PostgreSQL will update six products. Three target SKUs have matching sources, so three product rows are updated; the ambiguity lies in **which feed row supplies the values for each product row**.

When constraints, triggers, or complex expressions exist in `SET`, uncertainty over which source row is selected is even worse than picking the wrong price: it can record wrong metadata, timestamps, or business audit logs.

### 5.3. Repeated Runs Returning the Same Result Do Not Prove Safety

Never try to "fix" this by re-running until the desired value appears. Physical row order, insertion order, indexes, and query plans **are not source-selection contracts**. Your SQL must deterministically define a single winner before writing.

## 6. Checking for Ambiguity Risk Before UPDATE

An essential preflight step is to **run a `SELECT` reproducing the exact join and filters planned for `UPDATE`**, and count matching source rows per target key.

~~~sql
SELECT
    p.product_id,
    p.sku,
    COUNT(*) AS matching_source_rows,
    ARRAY_AGG(f.feed_id ORDER BY f.feed_at DESC, f.feed_id DESC)
        AS feed_ids
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
WHERE f.is_approved
GROUP BY p.product_id, p.sku
HAVING COUNT(*) > 1
ORDER BY p.product_id;
~~~

Result:

| product_id | sku | matching_source_rows | feed_ids |
| ---: | --- | ---: | --- |
| 1 | BK-01 | 2 | `{102,101}` |
| 2 | MOUSE-01 | 2 | `{103,108}` |
| 4 | CABLE-01 | 2 | `{106,105}` |

**This check is especially crucial in ETL/migration pipelines**, because a source table that "looks like one row per code" may have accumulated multiple versions over time.

### 6.1. Checking All Match Counts Including Zero

~~~sql
SELECT
    p.product_id,
    p.sku,
    COUNT(f.feed_id) AS approved_feed_rows
FROM upd_lab_201.products AS p
LEFT JOIN upd_lab_201.price_feed AS f
    ON f.sku = p.sku
   AND f.is_approved
GROUP BY p.product_id, p.sku
ORDER BY p.product_id;
~~~

| sku | approved_feed_rows |
| --- | ---: |
| BK-01 | 2 |
| MOUSE-01 | 2 |
| PEN-01 | 0 |
| CABLE-01 | 2 |
| BAG-01 | 0 |

With `LEFT JOIN`, use `COUNT(f.feed_id)` or a source column that is **NOT NULL whenever a source row exists**. Using `COUNT(*)` returns **1** even for products with no feed because the outer join emits one null-extended row.

### 6.2. Counting by Source Key Before Joining

If the target table already enforces `sku UNIQUE`, you can check duplicates directly in the feed table:

~~~sql
SELECT
    sku,
    COUNT(*) AS approved_rows
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
~~~

However, in real queries involving **multiple source tables**, checking each table individually is not enough. Joining an auxiliary table with a 1:N relationship can **multiply rows** even if the main feed has one row per SKU. Always verify the **final combined source relation** fed into `UPDATE`.

### 6.3. Check Values, Not Only Counts

~~~sql
SELECT
    sku,
    COUNT(*) AS rows_count,
    COUNT(DISTINCT new_price) AS distinct_prices,
    MIN(new_price) AS min_price,
    MAX(new_price) AS max_price
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku
ORDER BY sku;
~~~

Two source rows with the **same price** are still two matching source rows. They may agree on `unit_price`, yet differ in `feed_id`, `provider`, or other attributes. Therefore **`COUNT(DISTINCT new_price)=1` does not prove the join is one-to-one**.

## 7. Defining a Transparent Source-Selection Rule

For the lab dataset, we define the business rule:

> Among **approved** proposals for the same SKU, take the proposal with the latest `feed_at`; if multiple proposals share the same timestamp, choose the one with the largest `feed_id`.

This establishes a **total ordering** within each SKU because `feed_id` is the primary key and `feed_at` is non-NULL. Two rows sharing the same `feed_at` are deterministically broken by `feed_id`.

Expected winners:

| SKU | Chosen `feed_id` | `new_price` | Reason |
| --- | ---: | ---: | --- |
| BK-01 | 102 | 115.000 | Newer timestamp than 101 |
| MOUSE-01 | 103 | 270.000 | Newer timestamp than 108 |
| CABLE-01 | 106 | 125.000 | Same timestamp as 105, higher ID |
| UNKNOWN-01 | 107 | 90.000 | Source winner, but no target product exists |

`PEN-01` has no approved source; `BAG-01` has no source at all. Neither product will be **updated** by an `UPDATE ... FROM` inner join.

### 7.1. Why Is a Tie-Breaker Necessary?

If you only write:

~~~sql
ORDER BY sku, feed_at DESC
~~~

then for `CABLE-01` two source rows share the same timestamp. Picking the "first row" without a tiebreaker **does not uniquely determine a winner** per business rules. For *reproducibility*, add `feed_id DESC` or another business-approved priority attribute.

**Largest ID here is simply the tiebreaker chosen for this lab**, not a universal rule for all systems. If the source has revision numbers, vendor priority tiers, or distinct approval states, agree on the appropriate winner rule.

## 8. Approach 1: DISTINCT ON to Pick Exactly One Source per SKU

PostgreSQL supports `DISTINCT ON (key)`, keeping the **first row** of each key group according to the accompanying `ORDER BY`. It is especially convenient for **latest row per group** problems.

### 8.1. Preview Winners Before Updating

~~~sql
SELECT DISTINCT ON (f.sku)
    f.sku,
    f.feed_id,
    f.new_price,
    f.feed_at,
    f.provider
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY
    f.sku,
    f.feed_at DESC,
    f.feed_id DESC;
~~~

With `DISTINCT ON (f.sku)`, PostgreSQL retains one row per SKU. **`ORDER BY` must begin with the `DISTINCT ON` expressions**, followed by `feed_at DESC, feed_id DESC` to determine the group winner.

### 8.2. UPDATE FROM on the Deduplicated Source

~~~sql
BEGIN;

WITH latest_approved AS (
    SELECT DISTINCT ON (f.sku)
        f.sku,
        f.feed_id,
        f.new_price,
        f.feed_at,
        f.provider
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
    ORDER BY
        f.sku,
        f.feed_at DESC,
        f.feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = s.new_price,
    price_source_note = 'feed=' || s.feed_id::text,
    updated_at = clock_timestamp()
FROM latest_approved AS s
WHERE p.sku = s.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    p.price_source_note,
    s.feed_id AS chosen_feed_id;

-- Inspect inside transaction, then roll back the example.
ROLLBACK;
~~~

**Three target products** with approved sources are updated using their winners:

| SKU | Price After UPDATE in Transaction | `feed_id` |
| --- | ---: | ---: |
| BK-01 | 115.000 | 102 |
| MOUSE-01 | 270.000 | 103 |
| CABLE-01 | 125.000 | 106 |

`PEN-01` and `BAG-01` remain unchanged; `UNKNOWN-01` does not create a new product because `UPDATE` only modifies existing rows in the target table.

### 8.3. DISTINCT ON Is Not DISTINCT

~~~sql
SELECT DISTINCT sku, new_price
FROM upd_lab_201.price_feed
WHERE is_approved;
~~~

`DISTINCT sku, new_price` removes rows that match **across both columns**, yet for `BK-01` with prices `110000` and `115000`, the two rows **differ**, so both remain. Hence:

- `DISTINCT` **does not guarantee** unique `sku` when prices differ.
- `DISTINCT ON (sku)` keeps one row per SKU, yet picking the **right winner** still requires a complete `ORDER BY`.

### 8.4. ORDER BY Without a Tiebreaker Is Still Incomplete

Without `feed_id DESC`, `CABLE-01` remains ambiguous in priority. `DISTINCT ON` still picks one row, but **there is no guarantee it is the row your business rules intend**. A query returning one row is **not enough**; the selection rule for that row must also be deterministic.

## 9. Approach 2: ROW_NUMBER() Filtering rn = 1

The window function `ROW_NUMBER()` numbers rows within each partition, letting you pick the winner in the desired order.

### 9.1. Rank the Source First

~~~sql
SELECT
    f.sku,
    f.feed_id,
    f.new_price,
    f.feed_at,
    ROW_NUMBER() OVER (
        PARTITION BY f.sku
        ORDER BY f.feed_at DESC, f.feed_id DESC
    ) AS rn
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY f.sku, rn;
~~~

Each SKU has one row with `rn = 1` as its winner. `PARTITION BY sku` groups rows by SKU; `ORDER BY feed_at DESC, feed_id DESC` establishes priority inside each group.

### 9.2. UPDATE Using the Filtered Winner

~~~sql
BEGIN;

WITH ranked AS (
    SELECT
        f.sku,
        f.feed_id,
        f.new_price,
        f.provider,
        ROW_NUMBER() OVER (
            PARTITION BY f.sku
            ORDER BY f.feed_at DESC, f.feed_id DESC
        ) AS rn
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
),
winner AS (
    SELECT
        sku, feed_id, new_price, provider
    FROM ranked
    WHERE rn = 1
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    w.feed_id AS chosen_feed_id;

ROLLBACK;
~~~

The winning rows match the `DISTINCT ON` approach: 102, 103, 106 for the three target products.

### 9.3. ROW_NUMBER Differs from RANK and DENSE_RANK

When two rows share the same `feed_at`:

~~~sql
SELECT
    sku,
    feed_id,
    feed_at,
    ROW_NUMBER() OVER (
        PARTITION BY sku
        ORDER BY feed_at DESC
    ) AS row_number_by_time,
    RANK() OVER (
        PARTITION BY sku
        ORDER BY feed_at DESC
    ) AS rank_by_time
FROM upd_lab_201.price_feed
WHERE is_approved
ORDER BY sku, feed_id;
~~~

For `CABLE-01`, two rows with the same timestamp both receive `RANK() = 1`. Consequently, **filtering `RANK() = 1` does not guarantee one source row per SKU** on ties. `ROW_NUMBER() = 1` picks one row, yet if the `ORDER BY` only contains tied timestamps, the winner still lacks a deterministic tiebreaker.

**Correct practice:** use `ROW_NUMBER()` with `ORDER BY ... feed_id DESC` (or a complete tiebreak rule).

### 9.4. When to Use DISTINCT ON vs. ROW_NUMBER?

| Scenario | Convenient Tool |
| --- | --- |
| PostgreSQL, need only the single latest row per SKU | `DISTINCT ON` is often concise |
| Need top-N per group | `ROW_NUMBER`, filter `rn <= N` |
| Need to inspect ranks and debug ties | Window functions |
| Want portable SQL across multiple DBMSs | `ROW_NUMBER()` is more widely supported than `DISTINCT ON` |
| Need to guarantee a single winner row | Either, **when ordering is completely deterministic** |

Never pick one solely on the assumption that a syntax is "always faster." Benchmark on real data; indexes and how PostgreSQL executes sorts/windows also affect performance.

## 10. Approach 3: GROUP BY When Business Logic Truly Requires Aggregation

Not every multi-row source problem is "pick the latest record." In inventory systems, a source table can contain **multiple movements that must be summed**:

~~~text
SKU BK-01:
    receipt +10
    sale     -3
    count    +2
Net movement: +9
~~~

If business rules require the **sum of movements**, you must not pick a single row with `DISTINCT ON` or `ROW_NUMBER`, because that would drop the other transactions. You must **aggregate by key first** and then update each target row with the single aggregated value.

### 10.1. Create Sample Stock Balance and Movement Tables

~~~sql
CREATE TABLE upd_lab_201.stock_balance (
    sku TEXT PRIMARY KEY,
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0)
);

CREATE TABLE upd_lab_201.stock_movements (
    movement_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL,
    delta_qty INTEGER NOT NULL,
    is_posted BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO upd_lab_201.stock_balance
    (sku, on_hand)
VALUES
    ('BK-01', 50),
    ('MOUSE-01', 20),
    ('PEN-01', 100);

INSERT INTO upd_lab_201.stock_movements
    (movement_id, sku, delta_qty, is_posted)
VALUES
    (1, 'BK-01', 10, TRUE),
    (2, 'BK-01', -3, TRUE),
    (3, 'BK-01', 2, TRUE),
    (4, 'MOUSE-01', -5, TRUE),
    (5, 'MOUSE-01', 99, FALSE),
    (6, 'PEN-01', -10, TRUE);
~~~

### 10.2. Wrong: Direct UPDATE from Multiple Movements

~~~sql
-- WARNING: demonstrates flawed design only; do not run as business logic.
-- UPDATE upd_lab_201.stock_balance AS b
-- SET on_hand = b.on_hand + m.delta_qty
-- FROM upd_lab_201.stock_movements AS m
-- WHERE b.sku = m.sku
--   AND m.is_posted;
~~~

For `BK-01` with three movements, that query **does not mean "add 10, subtract 3, then add 2."** It picks just one joined row to supply `delta_qty` for `BK-01`. That is a **lost-transactions bug**, not just picking the wrong latest record.

### 10.3. Right: Aggregate Deltas First

~~~sql
BEGIN;

WITH movement_totals AS (
    SELECT
        sku,
        SUM(delta_qty) AS total_delta
    FROM upd_lab_201.stock_movements
    WHERE is_posted
    GROUP BY sku
)
UPDATE upd_lab_201.stock_balance AS b
SET on_hand = b.on_hand + t.total_delta
FROM movement_totals AS t
WHERE b.sku = t.sku
  AND b.on_hand + t.total_delta >= 0
RETURNING
    b.sku,
    b.on_hand AS new_on_hand,
    t.total_delta;

ROLLBACK;
~~~

Results inside the transaction:

| SKU | Initial Stock | Posted Delta Sum | New Stock |
| --- | ---: | ---: | ---: |
| BK-01 | 50 | +9 | 59 |
| MOUSE-01 | 20 | -5 | 15 |
| PEN-01 | 100 | -10 | 90 |

`movement_totals` has **one row per SKU** thanks to `GROUP BY sku`. Note that `SUM(delta_qty)` must still enforce business rules: posted status, duplicate prevention, cancellations, and which batches were already applied—`GROUP BY` alone does not enforce those.

### 10.4. GROUP BY Is No Excuse for Arbitrary MAX()

~~~sql
SELECT sku, MAX(new_price)
FROM upd_lab_201.price_feed
WHERE is_approved
GROUP BY sku;
~~~

This query yields **one row per SKU**, but selects the **highest price**, not the **latest proposal**. For `CABLE-01`, the highest price is `130000` (feed 105), whereas the latest + highest-ID rule picks `125000` (feed 106).

**Unique output per key does not prove business correctness.** Know whether you need **`SUM`/`MAX`/`MIN`/`AVG`** or an **ordered record selection**.

## 11. Approach 4: Scalar Subquery as a Cardinality Check

PostgreSQL supports assigning values with a **single-column subquery**:

~~~sql
UPDATE target AS t
SET value = (
    SELECT s.value
    FROM source AS s
    WHERE s.key = t.key
)
WHERE ...;
~~~

With a scalar subquery:

- **One row** → uses that row's value.
- **Zero rows** → the scalar subquery evaluates to `NULL`.
- **More than one row** → PostgreSQL raises an error because an expression subquery must return **at most one row** (typically `SQLSTATE 21000`, cardinality violation).

This differs from `UPDATE ... FROM`, where multiple matching source rows can silently produce an unpredictable update.

### 11.1. Failing Loudly Instead of Choosing Arbitrarily

On the dataset with two approved feeds for `BK-01`, the following statement is **designed to fail**:

~~~sql
BEGIN;
SAVEPOINT before_scalar_demo;

UPDATE upd_lab_201.products AS p
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
WHERE p.sku = 'BK-01';
-- Expected: ERROR:
-- more than one row returned by a subquery used as an expression
-- SQLSTATE is typically 21000.

ROLLBACK TO SAVEPOINT before_scalar_demo;
ROLLBACK;
~~~

If your SQL client stops immediately on error, explicitly roll back in your session before continuing. In PostgreSQL, a failed statement puts the current transaction into an aborted state until you roll back or roll back to a savepoint.

### 11.2. A Scalar Subquery Does Not Solve the Problem by Itself

A cardinality error **only detects** that the query violated the single-row assumption; it does not choose the right winner. If you write:

~~~sql
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
    LIMIT 1
)
~~~

the error disappears, yet **`LIMIT 1` without a complete `ORDER BY` still picks an arbitrary row**. That is not a proper fix.

### 11.3. Scalar Subquery with ORDER BY and LIMIT 1

When you want one source selected by explicit order:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET unit_price = (
    SELECT f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
    ORDER BY f.feed_at DESC, f.feed_id DESC
    LIMIT 1
)
WHERE EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
RETURNING p.sku, p.unit_price;

ROLLBACK;
~~~

`ORDER BY` plus `LIMIT 1` deterministically chooses one price per product (`feed_id` is unique). `WHERE EXISTS` is crucial: it ensures only products **with at least one approved source** are updated.

### 11.4. No Source Rows: UPDATE FROM vs. Scalar Subquery Differ

Suppose `BAG-01` has no feed records:

- `UPDATE ... FROM feed WHERE p.sku=f.sku` → no joined row, **does not update `BAG-01`**.
- `UPDATE products SET unit_price=(SELECT ...)` **without `WHERE EXISTS`** → the scalar subquery returns `NULL`, either overwriting the target with `NULL` or failing a `NOT NULL` constraint.

Keep this difference in mind when rewriting between update forms.

### 11.5. A Performance Consideration

Correlated scalar subqueries can be planned and executed differently from join updates; on large tables, the cost may differ. Do not assume scalar subqueries are always slower or always faster than `UPDATE ... FROM`. Express cardinality correctly first, then measure the plan with `EXPLAIN` on representative data.

## 12. Enforcing a Single Source via a Staging Table with UNIQUE

If an ETL job regularly processes batches, a durable solution is to **normalize the source into a staging table with a unique key** on the join key to the target.

Example inside a transaction:

~~~sql
BEGIN;

CREATE TEMP TABLE selected_price_feed (
    sku TEXT PRIMARY KEY,
    feed_id BIGINT NOT NULL UNIQUE,
    new_price NUMERIC(12, 2) NOT NULL
) ON COMMIT DROP;

INSERT INTO selected_price_feed (sku, feed_id, new_price)
SELECT DISTINCT ON (f.sku)
    f.sku,
    f.feed_id,
    f.new_price
FROM upd_lab_201.price_feed AS f
WHERE f.is_approved
ORDER BY f.sku, f.feed_at DESC, f.feed_id DESC;

-- Only one winner row per SKU due to PRIMARY KEY(sku).
SELECT sku, feed_id, new_price
FROM selected_price_feed
ORDER BY sku;

UPDATE upd_lab_201.products AS p
SET
    unit_price = s.new_price,
    price_source_note = 'feed=' || s.feed_id::text
FROM selected_price_feed AS s
WHERE p.sku = s.sku
RETURNING p.product_id, p.sku, p.unit_price;

ROLLBACK;
~~~

`PRIMARY KEY(sku)` on the staging table acts as a **technical guardrail**. If a buggy step tries to insert two winners for the same SKU, the staging `INSERT` fails instead of silently letting `UPDATE` pick arbitrarily.

### 12.1. What Does the Unique Constraint Guarantee?

It proves the staging table has **at most one row per SKU**. However, it **does not prove** the chosen winner is business-correct. If upstream sorted timestamps wrong or picked the wrong vendor, staging still has one row per SKU, just with the wrong price.

Therefore you need two layers:

1. **Correct winner selection rule**: latest, validly approved, explicit tiebreaker.
2. **Cardinality constraint**: normalized staging has `UNIQUE(sku)`.

### 12.2. Staging for Real Batch Imports

In production, you might add columns like:

~~~text
batch_id
source_system
ingested_at
validation_status
approved_by
source_row_hash
~~~

and an appropriate unique key such as `(batch_id, sku)` if each batch selects one price per SKU. Then `UPDATE` must join on **the exact `batch_id`** to avoid mixing prices across imports.

## 13. Risk of Duplicates Introduced by Additional JOINs

Even after reducing `price_feed` to **one winner per SKU**, joining an auxiliary table with a one-to-many relationship can multiply source rows again.

Suppose each provider has multiple contacts:

~~~sql
CREATE TABLE upd_lab_201.provider_contacts (
    contact_id BIGINT PRIMARY KEY,
    provider TEXT NOT NULL,
    contact_name TEXT NOT NULL
);

INSERT INTO upd_lab_201.provider_contacts
    (contact_id, provider, contact_name)
VALUES
    (1, 'VENDOR-A', 'Contact A1'),
    (2, 'VENDOR-A', 'Contact A2'),
    (3, 'VENDOR-B', 'Contact B1');
~~~

A `VENDOR-A` price proposal matches **two** contacts. Query:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    latest.sku,
    latest.feed_id,
    c.contact_id,
    c.contact_name
FROM latest
JOIN upd_lab_201.provider_contacts AS c
    ON c.provider = latest.provider
ORDER BY latest.sku, c.contact_id;
~~~

`VENDOR-A` winners get multiplied across two contacts. Feeding this entire join into `UPDATE FROM` and using `contact_name` in the update reintroduces **multiple source choices** per target row.

### 13.1. Check Cardinality After All JOINs

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
),
source_rows AS (
    SELECT
        latest.sku,
        latest.feed_id,
        c.contact_id
    FROM latest
    JOIN upd_lab_201.provider_contacts AS c
        ON c.provider = latest.provider
)
SELECT sku, COUNT(*) AS source_rows_per_sku
FROM source_rows
GROUP BY sku
HAVING COUNT(*) > 1
ORDER BY sku;
~~~

**Do not check uniqueness only on the `latest` CTE and assume downstream joins stay one-row-per-SKU.** Uniqueness can be lost at any 1:N join.

### 13.2. When You Only Need to Confirm a Contact Exists

Use `EXISTS` instead of joining detail rows:

~~~sql
WITH latest AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    l.sku, l.feed_id, l.new_price
FROM latest AS l
WHERE EXISTS (
    SELECT 1
    FROM upd_lab_201.provider_contacts AS c
    WHERE c.provider = l.provider
);
~~~

`EXISTS` only tests existence without multiplying the winner by contact count. If you need to store one specific contact, define a **preferred contact** (for example via a primary flag + unique constraint, or deterministic ordering + tiebreaker).

## 14. Misplaced LIMIT, ORDER BY, or DISTINCT

### 14.1. ORDER BY in a Verification SELECT Does Not Control UPDATE

~~~sql
SELECT *
FROM upd_lab_201.price_feed
ORDER BY feed_at DESC;
~~~

Running a `SELECT` that displays the source newest-first **does not cause a separate `UPDATE` statement to pick rows in that order**.

### 14.2. ORDER BY Inside a Source Subquery Still Leaves Multiple Matching Rows

~~~sql
-- STILL AMBIGUOUS when multiple rows share the same SKU:
-- UPDATE upd_lab_201.products AS p
-- SET unit_price = s.new_price
-- FROM (
--     SELECT sku, new_price
--     FROM upd_lab_201.price_feed
--     WHERE is_approved
--     ORDER BY feed_at DESC
-- ) AS s
-- WHERE p.sku = s.sku;
~~~

The subquery has `ORDER BY`, yet **does not eliminate other rows for the same SKU**. Cardinality remains greater than 1; `UPDATE ... FROM` remains ambiguous.

### 14.3. A Global LIMIT 1 Does Not Pick One Row per SKU

~~~sql
SELECT sku, feed_id, new_price
FROM upd_lab_201.price_feed
WHERE is_approved
ORDER BY feed_at DESC, feed_id DESC
LIMIT 1;
~~~

This query returns **one row for the entire table**, not **one row per SKU**. Using it as the `UPDATE` source leaves almost all products unmatched.

To get **one row per SKU group**, use `DISTINCT ON (sku)`, `ROW_NUMBER() OVER (PARTITION BY sku ...)`, or an equivalent design.

### 14.4. DISTINCT Only Deduplicates Across All Selected Columns

~~~sql
SELECT DISTINCT sku, new_price
FROM upd_lab_201.price_feed
WHERE is_approved;
~~~

Two `BK-01` records with different prices remain two rows. Even when two records share the same price with different `feed_id`s, deduplicating `(sku, new_price)` still fails to express "latest approved proposal."

## 15. UPDATE ... FROM When Sources Do Not Match

An unmatched source does not automatically set target columns to `NULL`. With an inner-join style update:

~~~sql
UPDATE upd_lab_201.products AS p
SET unit_price = f.new_price
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved;
~~~

only products with at least one approved feed row are updated. On our dataset:

- `PEN-01` has no **approved** source → price remains unchanged.
- `BAG-01` has no feed at all → price remains unchanged.
- `UNKNOWN-01` exists in the feed without a target → no new product is created.

### 15.1. If Business Logic Must Update Unmatched Target Rows Too

Express that condition separately. For example, flagging products without an approved feed for review:

~~~sql
BEGIN;

UPDATE upd_lab_201.products AS p
SET status = 'INACTIVE'
WHERE NOT EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
RETURNING p.sku, p.status;

ROLLBACK;
~~~

In the dataset, this affects `PEN-01` and `BAG-01`. **This is strictly a syntax illustration**, not a recommendation that products without new feeds should be deactivated. Real workflows may require keeping old prices and active statuses.

### 15.2. Avoid Setting Prices to NULL via Empty Scalar Subqueries

If you must handle missing sources alongside updates, use `CASE`, `COALESCE`, or two distinct `UPDATE` statements—but first define **what `NULL` means**. For `unit_price NOT NULL`, setting an unknown price to `NULL` violates the constraint, while defaulting to 0 just to "avoid errors" creates incorrect sale prices.

## 16. NULLs in Join Keys and Update Data

In `WHERE t.key = s.key`, if either key is `NULL`, `=` does not return `TRUE`, so those rows do not join under that predicate.

Example:

~~~sql
SELECT
    NULL::text = NULL::text AS regular_equality,
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS null_safe_equality;
~~~

Results: `NULL` and `TRUE`.

### 16.1. Should You Join NULL to NULL?

In systems using business keys such as SKU, **SKUs generally should not be nullable**. Enforcing `NOT NULL` and `UNIQUE` on the target identifies entities cleanly.

If a relation genuinely treats two `NULL` values as an equivalent key, PostgreSQL provides `IS NOT DISTINCT FROM` for null-safe comparison:

~~~sql
-- Semantic illustration only; apply only if business rules require it.
-- WHERE t.optional_key IS NOT DISTINCT FROM s.optional_key
~~~

However, if **multiple** source rows have a `NULL` key, a null-safe join matches **all** of them against a `NULL`-keyed target row, reintroducing multi-match ambiguity. Do not mask missing keys by blindly replacing `=` with `IS NOT DISTINCT FROM`.

### 16.2. Do Not Use COALESCE to Hide Missing Source Prices

~~~sql
SET unit_price = COALESCE(s.new_price, p.unit_price)
~~~

This keeps the old price if `new_price` is `NULL`. That makes sense when sources allow "no price change," yet it masks import errors if **a new price is mandatory**. In our lab, `new_price NOT NULL` eliminates that ambiguity at the schema level.

When updating multiple columns, check each one:

- `NULL` new price → skip, reject, or retain old price?
- `NULL` `provider` → should it overwrite an existing note?
- Earlier `feed_at` → should out-of-order older versions be rejected?

A succeeding `UPDATE` only guarantees SQL constraint compliance; **it does not prove every business rule holds**.

## 17. RETURNING to Inspect Updated Rows

PostgreSQL supports `RETURNING` after `UPDATE`:

~~~sql
UPDATE target AS t
SET column = expression
FROM source AS s
WHERE ...
RETURNING t.id, t.column;
~~~

When the source is referenced in `FROM`, you can also return related source expressions in `RETURNING`, such as `s.feed_id`.

### 17.1. Verify Post-Update State Instead of Guessing from Row Counts

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku
RETURNING
    p.product_id,
    p.sku,
    p.unit_price AS applied_price,
    w.feed_id;

ROLLBACK;
~~~

In the lab transaction, `RETURNING` shows the three affected products and which feed was applied. In production, this output can feed application logs or reconciliation, subject to access-control, data-sensitivity, and logging policies.

### 17.2. UPDATE Can Write a Row Even When the Price Did Not Change

For example:

~~~sql
UPDATE products
SET unit_price = unit_price
WHERE product_id = 1;
~~~

still executes an `UPDATE` on the matching row. In PostgreSQL, this can write a new row version and trigger triggers, WAL, and bloat depending on context. Thus never equate `UPDATE` row count with "number of rows whose values actually changed."

### 17.3. Update Only When the Price Actually Differs

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
  AND p.unit_price IS DISTINCT FROM w.new_price
RETURNING p.sku, p.unit_price, w.feed_id;

ROLLBACK;
~~~

`IS DISTINCT FROM` is null-safe; if both prices match, the predicate is `FALSE` and no update occurs. However, if **the price is unchanged yet the source metadata must still be recorded**, filtering solely on price would skip updating metadata. Define clearly which columns constitute a "meaningful change."

## 18. Recording Old and New Prices for Reconciliation

In many systems, administrators want to see after an update:

~~~text
product_id | old_price | new_price | chosen_feed_id
~~~

One lab approach is snapshotting pre-update prices into a temporary table before updating. In modern PostgreSQL, `RETURNING` returns post-update values by default; features accessing both old and new values directly in `RETURNING` are version-dependent, so the pattern below intentionally avoids relying on extended old/new `RETURNING` syntax.

### 18.1. Snapshot Before UPDATE in the Same Transaction

~~~sql
BEGIN;

CREATE TEMP TABLE before_prices ON COMMIT DROP AS
SELECT
    product_id,
    sku,
    unit_price AS old_price
FROM upd_lab_201.products;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
),
applied AS (
    UPDATE upd_lab_201.products AS p
    SET unit_price = w.new_price
    FROM winner AS w
    WHERE p.sku = w.sku
    RETURNING p.product_id, p.sku, p.unit_price, w.feed_id
)
SELECT
    a.product_id,
    a.sku,
    b.old_price,
    a.unit_price AS new_price,
    a.feed_id
FROM applied AS a
JOIN before_prices AS b
    ON b.product_id = a.product_id
ORDER BY a.product_id;

ROLLBACK;
~~~

In a **lab with no concurrent writes**, this query gives an easy before/after comparison. In production, snapshotting and then updating under default isolation **does not automatically prevent** another transaction from changing prices between the snapshot and the update. Design locking, isolation, and audit trails according to consistency requirements if exact historical prices are mandatory.

### 18.2. When True Price History Is Required

A production-grade system may store history:

~~~text
product_price_history(
    history_id,
    product_id,
    old_price,
    new_price,
    feed_id,
    changed_at,
    changed_by,
    batch_id
)
~~~

Recording history must be coordinated **in the same transaction** as the price change via explicit DML, triggers, or an intentional audit mechanism. Never rely on a separate `SELECT` run at another time to reconstruct old prices reliably.

## 19. Executing Changes Safely Inside a Transaction

A production workflow should have three phases: **prepare, verify, write and confirm**.

<escape>**Step 1 — Prepare the winner source:**</escape> include only approved records, scoped to a clear batch, ordered properly, verified at one row per SKU.

<escape>**Step 2 — Verify expected impact:**</escape> run a `SELECT` joining winners to targets, compare old vs. new prices, count products, and inspect unmatched sources and anomalies.

<escape>**Step 3 — UPDATE inside a transaction:**</escape> apply the exact verified winners, inspect `RETURNING`/row counts, write required audits, and only then `COMMIT` if every check passes.

Practice template with a winner CTE:

~~~sql
BEGIN;

-- In the lab, cap lock wait and statement duration.
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '20s';

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    p.sku,
    p.unit_price AS old_price,
    w.new_price,
    w.feed_id
FROM upd_lab_201.products AS p
JOIN winner AS w
    ON w.sku = p.sku
ORDER BY p.sku;

-- Only after verifying impact, execute the matching UPDATE.
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text
FROM winner AS w
WHERE p.sku = w.sku
RETURNING p.sku, p.unit_price, w.feed_id;

-- Always roll back in the lab to preserve seed data.
ROLLBACK;
~~~

### 19.1. Why Keep Transaction Duration Reasonable?

`UPDATE` acquires locks on modified target rows and can contend with other transactions. Long-running transactions can:

- Block other write requests.
- Increase deadlock risk when multiple jobs update rows in different orders.
- Hold onto old row versions longer, hurting vacuum and increasing bloat.
- Make massive changes slow to roll back or recover if scope is too large.

Never leave a production transaction open while waiting minutes or hours for manual approval. Prepare and verify in staging first, then deploy controlled batches with proper auditing.

### 19.2. Preflight and UPDATE Are Two Separate SQL Statements

Even under `READ COMMITTED`, two statements can observe different source data if another transaction commits in between. **A clean preflight at time T does not automatically guarantee the `UPDATE` at T+1 sees the exact same source snapshot.**

If you must **apply the exact approved feed snapshot**:

- Materialize winners into staging with a unique key and fixed `batch_id`.
- Prevent edits to staging once the batch is locked.
- Execute the update from that stable winner set.
- Choose isolation/locking suited to your concurrency requirements.

`BEGIN` lets you roll back your own transaction's changes, but **does not magically freeze mutable source tables into a cross-statement immutable snapshot**.

## 20. Risks When Multiple Transactions UPDATE Concurrently

Suppose jobs A and B concurrently update `BK-01` from different batches:

~~~text
Job A: reads approved feed, picks price 115000
Job B: receives newer approved feed, picks price 119000
Job A: UPDATE BK-01
Job B: UPDATE BK-01
~~~

The final price depends on transaction policy, commit order, update guards, and version checks. **Picking a unique winner inside each job does not prevent out-of-order overwrites between jobs.**

### 20.1. Enforce a Rule Against Overwriting Newer Data with Stale Sources

A common design tracks applied metadata on the target:

~~~text
products.applied_feed_at
products.applied_feed_id
~~~

Then only allow applying a source if its version is **newer** than the currently recorded one. When ordering by timestamp, include the ID tiebreaker and put the version guard **directly inside the `UPDATE` statement**, not only in a preceding `SELECT`.

This is an extended design: the initial lab schema lacks these two columns, so the snippet below is **conceptual**, not runnable directly:

~~~sql
-- Conceptual guard if schema includes applied_feed_at and applied_feed_id:
-- WHERE p.sku = w.sku
--   AND (
--       p.applied_feed_at IS NULL
--       OR (p.applied_feed_at, p.applied_feed_id)
--          < (w.feed_at, w.feed_id)
--   )
~~~

When both target columns are `NOT NULL` after initialization, tuple comparison is simpler. If `applied_feed_id` can be `NULL`, handle all `NULL` cases explicitly rather than relying on tuple comparisons that can evaluate to `UNKNOWN`.

### 20.2. Row Locks and WHERE Predicates

PostgreSQL locks target rows during update; another transaction trying to update the same row must wait. Under `READ COMMITTED`, PostgreSQL re-evaluates the `WHERE` condition against the updated target row after waiting in applicable cases. Still, **implicit row locking alone does not enforce application-defined versioning rules**.

Combine:

- A business-meaningful source ordering;
- Version-comparison guards in `UPDATE`;
- Idempotent batches tracking applied feeds;
- Appropriate locking/isolation when multiple writers contend;
- Bounded retries on deadlocks or serialization failures where business rules allow.

### 20.3. Never Blindly Retry Data Errors

A `23505` unique violation or `21000` multi-row scalar subquery error usually indicates a **data or logic defect**, not a reason to retry identically until it "gets lucky." Conversely, deadlock `40P01` or serialization failure `40001` can be retried across the **entire transaction** under an appropriate retry policy.

## 21. UPDATE FROM with Self-Joins

PostgreSQL allows referencing the same table as the source in `FROM`, provided you distinguish the **target table** from the **aliased source instance**.

Example staff table with managers:

~~~sql
CREATE TABLE upd_lab_201.staff (
    staff_id BIGINT PRIMARY KEY,
    manager_id BIGINT NULL
        REFERENCES upd_lab_201.staff(staff_id),
    staff_name TEXT NOT NULL,
    manager_name_cache TEXT NULL
);

INSERT INTO upd_lab_201.staff
    (staff_id, manager_id, staff_name)
VALUES
    (1, NULL, 'An'),
    (2, 1, 'Binh'),
    (3, 1, 'Chi');
~~~

Each `manager_id` points to **at most one** manager because `staff.staff_id` is the primary key:

~~~sql
BEGIN;

UPDATE upd_lab_201.staff AS employee
SET manager_name_cache = manager.staff_name
FROM upd_lab_201.staff AS manager
WHERE employee.manager_id = manager.staff_id
RETURNING
    employee.staff_id,
    employee.staff_name,
    employee.manager_name_cache;

ROLLBACK;
~~~

Because `manager.staff_id` is unique, each employee matches at most one manager row. This self-join is cardinality-safe.

### 21.1. Why Are Aliases Required?

If the target table also appears in `FROM`, assign **distinct aliases** to clarify each reference's role. Do not write:

~~~sql
-- Not a valid self-join form:
-- UPDATE staff SET ... FROM staff WHERE ...;
~~~

expecting PostgreSQL to guess which row is the employee and which is the manager. Using aliases like `employee` and `manager` clarifies which is the **write target** and which is the **read source**.

### 21.2. Denormalization Is a Separate Design Decision

`manager_name_cache` is strictly a practice example. In production, renaming a manager makes cached names stale; many systems should **JOIN at read time** instead of duplicating names. If caching is truly necessary, build synchronization or staleness-tolerance mechanisms.

## 22. UPDATE FROM with Multi-Step CTEs

A `WITH` clause can structure logic into clear steps: filter feeds, rank, select winners, then update.

~~~sql
BEGIN;

WITH approved AS (
    SELECT
        feed_id, sku, new_price, feed_at, provider
    FROM upd_lab_201.price_feed
    WHERE is_approved
),
ranked AS (
    SELECT
        approved.*,
        ROW_NUMBER() OVER (
            PARTITION BY sku
            ORDER BY feed_at DESC, feed_id DESC
        ) AS rn
    FROM approved
),
winner AS (
    SELECT
        feed_id, sku, new_price, feed_at, provider
    FROM ranked
    WHERE rn = 1
),
applied AS (
    UPDATE upd_lab_201.products AS p
    SET
        unit_price = w.new_price,
        price_source_note = 'feed=' || w.feed_id::text
    FROM winner AS w
    WHERE p.sku = w.sku
    RETURNING
        p.product_id,
        p.sku,
        p.unit_price,
        w.feed_id
)
SELECT *
FROM applied
ORDER BY product_id;

ROLLBACK;
~~~

Splitting into CTEs makes **each layer's responsibility** explicit:

1. `approved` excludes unapproved proposals.
2. `ranked` makes priority ordering explicit.
3. `winner` guarantees one row per SKU.
4. `applied` performs the **write** and returns results.

**CTEs do not automatically make a join one-to-one.** If `winner` is flawed, multiple rows per SKU can still slip through. Safety comes from **your selection rules and cardinality checks**, not from using `WITH`.

### 22.1. CTEs Do Not Lock Source Rows

A CTE reads data within a single statement, but does not lock source rows against concurrent updates by other sessions. If you require a fixed snapshot across multiple statements, design appropriate transactions, isolation, or staging.

### 22.2. Do Not Treat CTE MATERIALIZED as a Cure for Non-Determinism

Forcing materialization of a source containing **two rows for the same SKU** does not tell `UPDATE ... FROM` which row should win. `MATERIALIZED` affects query planning and CTE reuse, **not duplicate-join semantics**.

## 23. How Do MERGE and INSERT ON CONFLICT DO UPDATE Differ?

PostgreSQL offers other data-modification constructs:

- `UPDATE ... FROM`: updates existing target rows from a source set.
- `INSERT ... ON CONFLICT DO UPDATE`: inserts new rows or updates on conflict against a valid unique constraint/index.
- `MERGE` (PostgreSQL 15+): expresses `WHEN MATCHED`/`WHEN NOT MATCHED` branches and corresponding actions.

**Changing syntax does not automatically fix duplicate sources.** Each construct has its own duplicate/cardinality rules—consult the documentation for your server version.

### 23.1. ON CONFLICT DO UPDATE Forbids Updating the Same Row Twice in One Command

In PostgreSQL, a single `INSERT ... ON CONFLICT DO UPDATE` command cannot affect the same target row more than once. If input rows conflict on the same key multiple times, it raises a cardinality error.

Conceptual example:

~~~sql
-- Do not run in production; illustrates duplicate SKU input:
-- INSERT INTO products(sku, unit_price, ...)
-- VALUES ('BK-01', 110000, ...),
--        ('BK-01', 115000, ...)
-- ON CONFLICT (sku) DO UPDATE
-- SET unit_price = EXCLUDED.unit_price;
~~~

When upserting from a feed, still **reduce the feed to one row per SKU** according to business rules first.

### 23.2. MERGE Is Not a Drop-In Replacement for UPDATE FROM

`MERGE` supports branching actions for matches and non-matches, yet non-unique sources can still cause cardinality errors or unintended behavior. When one target row matches multiple source rows and multiple actions attempt to modify it, PostgreSQL enforces different checks than `UPDATE ... FROM`. Always ensure clean source cardinality before using `MERGE`.

Choose the tool based on whether you need **update**, **upsert**, or **multi-branch actions**—never switch to `MERGE` merely to dodge unique-source rules.

## 24. Indexes and Performance

### 24.1. Indexes on the Target Table

~~~sql
CREATE TABLE upd_lab_201.products (
    ...
    sku TEXT NOT NULL UNIQUE,
    ...
);
~~~

`UNIQUE(sku)` already creates an index supporting SKU lookups and guaranteeing one target product per SKU. Do not create a redundant B-tree index on `products(sku)` without a specific reason.

### 24.2. Indexes on the Source Table

The lab already creates:

~~~sql
CREATE INDEX idx_price_feed_sku_approved_time
ON upd_lab_201.price_feed
    (sku, feed_at DESC, feed_id DESC)
WHERE is_approved;
~~~

This is a **partial B-tree index** covering approved rows, ordered by SKU and winner-selection keys. It can help plans compute `DISTINCT ON (sku) ORDER BY sku, feed_at DESC, feed_id DESC` when filter predicates align.

Still, an index does not guarantee the fastest plan or that the planner will choose it. Sort cost, row counts, selectivity, statistics, and write overhead all matter.

### 24.3. Inspect Plans with EXPLAIN Before Running

~~~sql
EXPLAIN
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku;
~~~

`EXPLAIN` without `ANALYZE` only displays the estimated plan; **it does not execute the `UPDATE`**.

If you run:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE ...;
~~~

PostgreSQL **actually executes the `UPDATE`** to measure runtime stats. Only run that inside a rolled-back transaction in a practice environment or after assessing impact; external side effects from triggers/functions may not roll back cleanly.

### 24.4. Avoid Unnecessary Updates When Prices Have Not Changed

`UPDATE` creates new row versions and writes WAL even when assigning the identical value. On tables with millions of products, consider filtering:

~~~sql
AND p.unit_price IS DISTINCT FROM w.new_price
~~~

to avoid redundant writes, unless business rules require refreshing metadata/audits even when price stays the same.

### 24.5. Large Batches and Lock Contention

Updating hundreds of thousands of products in one transaction can hold locks too long and generate heavy WAL. Consider:

- Batching by stable key ranges on `product_id`.
- Bounding row counts per transaction with checkpoints/audits.
- Freezing the source per batch so chunks do not read inconsistent prices.
- Monitoring `pg_stat_activity`, lock waits, and replication lag.
- Having retry, rollback, and idempotency strategies.

**Never place `LIMIT` directly hoping it caps `UPDATE ... FROM` per SKU.** PostgreSQL `UPDATE` lacks MySQL-style `LIMIT`; to batch, select a distinct set of target keys first in a CTE/subquery and update that set with proper locking and contention planning.

## 25. Checking Source Cardinality Before Writing

In ETL batches, clarify expectations with three read queries:

### 25.1. Does the Selected Source Have at Most One Row per SKU?

~~~sql
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    sku,
    COUNT(*) AS rows_per_sku
FROM winner
GROUP BY sku
HAVING COUNT(*) > 1;
-- Expected: zero rows.
~~~

This is an observational query; for physical enforcement, insert the results into staging with `PRIMARY KEY(sku)`.

### 25.2. Which Sources Have No Target Product?

~~~sql
WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
SELECT
    w.sku,
    w.feed_id,
    w.new_price
FROM winner AS w
LEFT JOIN upd_lab_201.products AS p
    ON p.sku = w.sku
WHERE p.product_id IS NULL
ORDER BY w.sku;
-- UNKNOWN-01, feed_id 107.
~~~

Never auto-create dummy products in production just to "make sources match." Route unknown SKUs to a review queue or create products through a dedicated workflow.

### 25.3. Which Products Received No Approved Source?

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.unit_price
FROM upd_lab_201.products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM upd_lab_201.price_feed AS f
    WHERE f.sku = p.sku
      AND f.is_approved
)
ORDER BY p.product_id;
-- PEN-01 and BAG-01.
~~~

**Sources without targets** and **targets without sources** are two distinct anomalies. Pipeline reports should classify them separately instead of lumping them into "missing rows."

## 26. Common Mistakes and Fixes

| Symptom / Pattern | Risk | Fix |
| --- | --- | --- |
| `UPDATE FROM` joins feed only by SKU while feed has multiple versions | Nondeterministic source selection | Use `DISTINCT ON`/`ROW_NUMBER` with complete ordering |
| Putting `ORDER BY` in an earlier `SELECT` query | Does not control `UPDATE` | Select the winner **inside the `UPDATE` source itself** |
| `DISTINCT sku, price` | One SKU still has multiple prices | Use `DISTINCT ON (sku)` or proper grouping |
| `RANK() = 1` | Ties yield multiple rows at rank 1 | Use `ROW_NUMBER() = 1` with a tiebreaker |
| `LIMIT 1` without `ORDER BY` | Arbitrary row chosen | Add a complete, deterministic `ORDER BY` |
| Global `LIMIT 1` on source table | Returns only one row total | Pick one row **per key** |
| `MAX(new_price)` to get latest price | Confuses highest price with latest timestamp | Pick record ordered by `feed_at` + tiebreaker |
| `SUM(...)` on price version records | Sums multiple version prices into sale price | Aggregate only when business logic requires summing |
| Joining a 1:N auxiliary table after winner selection | Re-multiplies source rows | Check cardinality **after all joins**; use `EXISTS` if appropriate |
| Missing join condition | Cross-join updating wrong rows | Specify target–source keys and batch filters |
| Scalar subquery returns >1 row | Cardinality error `21000` | Fix source selection rule; don't slap on `LIMIT 1` blindly |
| Scalar subquery returns 0 rows | Evaluates to `NULL`, overwriting or failing `NOT NULL` | Add `WHERE EXISTS` or explicit missing-row handling |
| Seeing 3 rows in `RETURNING` and assuming no duplicates | Target row count does not reveal matched source multiplicity | Preflight `COUNT(*)` per target key |
| Using `COUNT(*)` after `LEFT JOIN` to count sources | Unmatched rows count as 1 | Use `COUNT(source_not_null_key)` |
| Checking only `COUNT(DISTINCT price)=1` | Multiple rows differing in metadata go unnoticed | Check `COUNT(*)` and source keys |
| Overwriting newer price with late batch | Lost ordering/business version | Track applied version and guard inside `UPDATE` |
| Using `COALESCE(new_price, old_price)` to "avoid errors" | Hides malformed feed data | Define `NULL` semantics and reject invalid sources |
| Holding transactions open too long | Lock contention, deadlocks, bloat | Finalize staging, batch reasonably, monitor |
| Trusting `MATERIALIZED` to fix duplicates | Materialization does not choose a winner | Fix cardinality and ordering explicitly |
| Switching to `MERGE` or `ON CONFLICT` to dodge duplicates | Still has its own cardinality/semantics rules | Deduplicate or aggregate source per business rules |

## 27. Practice Exercises

### Exercise 1 — Inspect the Join Before Updating

Write a `SELECT` joining `products` to `price_feed` where `is_approved = TRUE`. Return `sku`, `unit_price`, `feed_id`, and `new_price`, ordered by SKU and descending timestamp.

**Expected:** **6 joined rows** for **3 target products**: `BK-01`, `MOUSE-01`, `CABLE-01`.

### Exercise 2 — Detect Duplicate Sources

Write:

~~~sql
SELECT
    p.sku,
    COUNT(*) AS matched_source_rows
FROM upd_lab_201.products AS p
JOIN upd_lab_201.price_feed AS f
    ON p.sku = f.sku
WHERE f.is_approved
GROUP BY p.sku
HAVING COUNT(*) > 1;
~~~

**Answer:** `BK-01`, `MOUSE-01`, and `CABLE-01` each have **2** source rows.

### Exercise 3 — Evaluate an Ambiguous UPDATE

Using the original dataset, explain why:

~~~sql
UPDATE upd_lab_201.products AS p
SET unit_price = f.new_price
FROM upd_lab_201.price_feed AS f
WHERE p.sku = f.sku
  AND f.is_approved;
~~~

does not guarantee picking the latest price. **Do not run it without wrapping in a rolled-back transaction.**

### Exercise 4 — Select Winners with DISTINCT ON

Write `SELECT DISTINCT ON (sku)` picking approved records with the latest timestamp, breaking ties with `feed_id DESC`.

**Winner answers:** `102` for `BK-01`, `103` for `MOUSE-01`, `106` for `CABLE-01`, `107` for `UNKNOWN-01`.

### Exercise 5 — UPDATE FROM Using Winners

Wrap in a transaction:

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (sku)
        sku, feed_id, new_price
    FROM upd_lab_201.price_feed
    WHERE is_approved
    ORDER BY sku, feed_at DESC, feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET unit_price = w.new_price
FROM winner AS w
WHERE p.sku = w.sku
RETURNING p.sku, p.unit_price, w.feed_id;

ROLLBACK;
~~~

**Answer:** `BK-01` → 115000; `MOUSE-01` → 270000; `CABLE-01` → 125000. `PEN-01` and `BAG-01` remain untouched.

### Exercise 6 — Select Winners with ROW_NUMBER

Use `ROW_NUMBER() OVER (PARTITION BY sku ORDER BY feed_at DESC, feed_id DESC)` and filter `rn = 1`. Compare selected feeds with Exercise 4.

**Expected:** identical winners.

### Exercise 7 — Why Doesn't RANK Guarantee One Row?

Run `RANK() OVER (PARTITION BY sku ORDER BY feed_at DESC)` for `CABLE-01`. Explain why two feeds sharing a timestamp both get `RANK = 1`. If you filter `RANK = 1` and feed it to `UPDATE FROM`, what risk remains?

### Exercise 8 — Same Timestamp, Different Prices

For `CABLE-01`, does `MAX(new_price)` return **130000** or **125000**? What does `feed_at DESC, feed_id DESC` pick?

**Answer:** `MAX` picks 130000; winner ordering picks 125000. Explain why "latest" cannot be replaced by `MAX(price)`.

### Exercise 9 — Business-Accurate Inventory Aggregation

From `stock_movements`, sum `SUM(delta_qty)` per SKU where `is_posted = TRUE` and apply `UPDATE FROM` to `stock_balance`.

**Answer inside transaction:** `BK-01 = 59`, `MOUSE-01 = 15`, `PEN-01 = 90`. Then roll back.

### Exercise 10 — Picking a Single Movement Is a Bug

If you write `SET on_hand = on_hand + m.delta_qty` when each SKU has multiple movements, what happens? Does PostgreSQL apply all movements sequentially?

**Answer:** No; only one joined row supplies `delta_qty`, dropping the remaining movements.

### Exercise 11 — Multi-Row Scalar Subquery

Write a scalar subquery fetching `new_price` of approved feeds for `BK-01` **without limiting row count**, inside a transaction with a savepoint. Observe the cardinality error and roll back to the savepoint. Explain why this error helps catch flawed cardinality assumptions.

### Exercise 12 — Scalar Subquery with No Rows

If you run `SET unit_price = (SELECT new_price FROM feed WHERE sku=p.sku AND is_approved)` across all products without `WHERE EXISTS`, what happens to `BAG-01`? Why does `unit_price NOT NULL` cause the command to fail?

### Exercise 13 — Sources Without Targets

Find approved SKUs in the feed that do not exist in `products` using `LEFT JOIN` or `NOT EXISTS`.

**Answer:** `UNKNOWN-01` (feed 107).

### Exercise 14 — Targets Without Approved Sources

Find products that have no approved source.

**Answer:** `PEN-01` and `BAG-01`.

### Exercise 15 — Duplicates from Auxiliary Joins

Join the per-SKU winners to `provider_contacts`. Count rows per SKU after the join. Explain why already-unique winners **can still be multiplied**, and when to use `EXISTS` instead of joining.

### Exercise 16 — Update Only When Price Changes

Add the condition:

~~~sql
AND p.unit_price IS DISTINCT FROM w.new_price
~~~

to the winner-based `UPDATE`. Run it twice **in the same transaction** (without rolling back between runs) and compare `RETURNING` row counts between the first and second run, then roll back at the end. Why does updating `price_source_note` metadata need a different rule?

### Exercise 17 — Staging Table with Primary Key

Create `TEMP TABLE selected_price_feed(sku PRIMARY KEY, ...)`, insert winners, and try inserting another row **with the same SKU** and a different price. Observe unique violation `23505` inside a savepoint, then roll back to the savepoint. Explain the benefit of this constraint in ETL pipelines.

### Exercise 18 — Multi-Step CTE

Structure the query as `approved` → `ranked` → `winner` → `UPDATE RETURNING`. Verify that each CTE has a single clear responsibility.

### Exercise 19 — Self-Join

Run `UPDATE staff AS employee SET manager_name_cache = manager.staff_name FROM staff AS manager WHERE employee.manager_id = manager.staff_id` on the lab table. Why does `staff_id PRIMARY KEY` guarantee each manager matches at most one source row?

### Exercise 20 — Checking COUNT(*) After LEFT JOIN

Write a report counting approved feed rows across **all products** using `LEFT JOIN`. Compare `COUNT(*)` vs. `COUNT(f.feed_id)` for `BAG-01`.

**Answer:** `COUNT(*) = 1` on the unmatched outer-join row; `COUNT(f.feed_id) = 0`.

### Exercise 21 — Idempotent Batch Design

Design `batch_id`, `feed_id`, and `applied_feed_at` metadata so re-running the same batch never reverts prices backward. Present the **winner rule**, **version guard**, and **audit trail** needed before deployment.

### Exercise 22 — Inspecting the Plan

Run `EXPLAIN` (without `ANALYZE`) on the `DISTINCT ON` `UPDATE`. List the plan nodes observed (source scan, unique/sort, join to target, update) and explain why actual plans depend on statistics.

### Exercise 23 — Code Review of a Dangerous Statement

A colleague proposes:

~~~sql
UPDATE product AS p
SET price = s.price
FROM (
    SELECT sku, price
    FROM supplier_prices
    ORDER BY changed_at DESC
) AS s
WHERE s.sku = p.sku;
~~~

List at least **5 issues/questions** to resolve before approving:

1. How many source rows exist per SKU?
2. Does `ORDER BY` actually pick a single winner per SKU?
3. If timestamps tie, what tiebreaker applies?
4. Are sources approved/valid?
5. What happens to SKUs with no source?
6. Should applied version/source metadata be stored?
7. Are transaction/audit/rollback plans and impact estimates in place?

### Exercise 24 — Choosing the Right Strategy

For these four scenarios, pick the pre-processing approach for `UPDATE FROM`:

| Scenario | Hint |
| --- | --- |
| Multiple price proposals over time | Pick one winner by timestamp + tiebreaker |
| Multiple stock receipt/issue movements | `GROUP BY` and `SUM(delta_qty)` |
| Require strictly one row per SKU in staging | `PRIMARY KEY`/`UNIQUE` on staging |
| Only need to verify a provider has a valid contact | `EXISTS` instead of a 1:N join |

Explain why **no single deduplication approach** fits every business rule.

## 28. Reusable Safe Workflow Pattern

<escape>**1. Identify the target key:**</escape> what entity does each target row represent? `sku`, `order_id`, `user_id`, or a composite key? Is it `UNIQUE`?

<escape>**2. Define source semantics:**</escape> are multiple records **superseding versions**, **transactions to sum**, or **secondary details**?

<escape>**3. Produce one meaningful source row per key:**</escape> use `DISTINCT ON`/`ROW_NUMBER` with deterministic ordering, `GROUP BY` with aggregation, or a `UNIQUE` staging table.

<escape>**4. Verify final cardinality:**</escape> after **all joins**, group by target key and check `HAVING COUNT(*) > 1`. Do not trust only the initial source's uniqueness.

<escape>**5. Classify missing/unmatched cases:**</escape> targets without sources, sources without targets, `NULL`/corrupt values, unapproved records, stale batches.

<escape>**6. Preview impact:**</escape> `SELECT` target keys, old prices, new prices, source IDs, and expected row counts. Never rely on `RETURNING` after writing as your sole check.

<escape>**7. Protect against concurrency:**</escape> freeze batches, compare versions, choose isolation/locking and idempotency when multiple workers can update the same rows.

<escape>**8. UPDATE and audit inside a transaction:**</escape> bound scope, use `RETURNING`, verify counts, and record history per business rules.

<escape>**9. Verify before committing:**</escape> if results look wrong, roll back. In production, follow approved migrations/runbooks with recovery plans.

### 28.1. A Safe Execution Template for the Lab

~~~sql
BEGIN;

WITH winner AS (
    SELECT DISTINCT ON (f.sku)
        f.sku,
        f.feed_id,
        f.new_price
    FROM upd_lab_201.price_feed AS f
    WHERE f.is_approved
    ORDER BY f.sku, f.feed_at DESC, f.feed_id DESC
)
UPDATE upd_lab_201.products AS p
SET
    unit_price = w.new_price,
    price_source_note = 'feed=' || w.feed_id::text,
    updated_at = clock_timestamp()
FROM winner AS w
WHERE p.sku = w.sku
  AND (
      p.unit_price IS DISTINCT FROM w.new_price
      OR p.price_source_note
         IS DISTINCT FROM ('feed=' || w.feed_id::text)
  )
RETURNING
    p.product_id,
    p.sku,
    p.unit_price,
    p.price_source_note,
    w.feed_id;

ROLLBACK;
~~~

Highlights:

- The `winner` source yields one row per SKU using latest timestamp + highest ID on ties.
- `WHERE p.sku = w.sku` joins on the target's unique business key.
- `IS DISTINCT FROM` skips writes when **both price and source note already match**.
- `RETURNING` reveals which products were affected.
- `ROLLBACK` lets you practice repeatedly without mutating seed data.

In production, this pattern still needs version/batch guards, data validation rules, and auditing tailored to your goals. **Never copy-paste this verbatim into a system without confirmed pricing policies.**

## 29. Official PostgreSQL Documentation

- [UPDATE — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM` syntax, warnings about multiple joined rows matching one target row, `RETURNING`, and subqueries.
- [SELECT / DISTINCT ON](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `ORDER BY`, and first-row-per-group selection.
- [Window Functions](https://www.postgresql.org/docs/current/functions-window.html): `ROW_NUMBER`, `RANK`, `PARTITION BY`.
- [Common Table Expressions](https://www.postgresql.org/docs/current/queries-with.html): `WITH`, data-modifying statements, and `RETURNING`.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots and concurrent update behavior.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): match/no-match branches and cardinality notes.
- [INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): upsert syntax and conflict cardinality constraints.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): plan analysis and the fact that `EXPLAIN ANALYZE` executes the statement.

`/docs/current/` URLs point to the current stable documentation. When running a specific major version, verify syntax and behavior against that version's docs, especially for newer `RETURNING` or `MERGE` features.

## 30. Summary

**`UPDATE ... FROM` is a convenient tool for updating a target table from source data, yet it does not automatically ensure a single source row per target row.** If a join matches multiple source rows to one target row, PostgreSQL picks one joined row to apply with **no guarantee of which one**. Consequently, never treat insertion order, indexes, `ORDER BY` without winner selection, or lucky test runs as proof of query correctness.

The right fix depends on source semantics: for **multiple versions**, pick the priority record via `DISTINCT ON` or `ROW_NUMBER() = 1` with a tiebreaker; for **multiple additive movements**, aggregate with `GROUP BY`/`SUM`; for strict batches, use a **staging table with `PRIMARY KEY`/`UNIQUE`**. A scalar subquery errors on multiple rows instead of picking arbitrarily, yet you still must define the source rule and handle zero-row cases.

Before writing, **verify cardinality after all joins**, preview changes with `SELECT`, classify unmatched sources/targets, guard transactions and concurrency, and reconcile with `RETURNING`. An update affecting the **right number of rows** does not guarantee updating the **right values**: the quality of `UPDATE ... FROM` is determined first and foremost by the **uniqueness and clarity of the source data you construct**.
