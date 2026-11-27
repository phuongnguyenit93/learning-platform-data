# Set-Based Processing Instead of Loops When Appropriate in PL/pgSQL

When learning PL/pgSQL, Java or Python developers often bring element-by-element iteration habits into PostgreSQL: fetch a list of orders, write a `FOR ... LOOP`, check each order, and run an `UPDATE` per row. That style can trigger thousands or millions of separate SQL executions from PL/pgSQL even when the task is actually **a set-level data transformation**.

Consider the requirement: "Apply a 10% reduction to the amount due for all orders currently in `pending` status before 2026-11-01." Row-by-row style:

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM orders
        WHERE status = 'pending'
          AND ordered_at < DATE '2026-11-01'
    LOOP
        UPDATE orders
        SET amount = amount * 0.90
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;
```

In many cases, the entire loop can be replaced by:

```sql
UPDATE orders
SET amount = amount * 0.90
WHERE status = 'pending'
  AND ordered_at < DATE '2026-11-01';
```

The second statement expresses **the goal at the row-set level**: PostgreSQL chooses how to find matching rows, applies the filter predicates, and updates them. We do not ask the server to execute a fresh `UPDATE` statement for each individual order ID.

This is **set-based processing**: describing the *input dataset* and the *output transformation rule*, letting the SQL planner and executor carry it out rather than driving every row manually in a PL/pgSQL loop. It does not mean SQL skips scanning rows internally—the executor still processes tuples and indexes. The payoff is eliminating repetitive SQL invocations, leveraging PostgreSQL optimizer strategies, and making business intent clear.

This lesson examines when to refactor loops into SQL, common replacement patterns, real costs and transactional consistency, risks of batching too aggressively into one statement, and cases where **a loop remains the right choice**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish *row-by-row* processing (sometimes called RBAR — *Row By Agonizing Row*) from set-based processing.
2. Explain why a single SQL statement is usually better than thousands of identical statements executed inside a `FOR LOOP`.
3. Rewrite loops into `INSERT ... SELECT`, `UPDATE ... FROM`, `DELETE ... USING`, and `INSERT ... ON CONFLICT` when semantics match.
4. Use `CASE`, `COALESCE`, `FILTER`, window functions, `DISTINCT ON`, `LATERAL`, and CTEs to express transformations previously built with temporary variables and loops.
5. Understand how set-based SQL interacts with MVCC, locks, triggers, constraints, and statement atomicity.
6. Avoid conversion pitfalls: non-unique source rows in `UPDATE ... FROM`, join row multiplication, non-deterministic top-N selection, and assuming unguaranteed update ordering.
7. Read `EXPLAIN (ANALYZE, BUFFERS)` and benchmark fairly.
8. Recognize when PL/pgSQL is still necessary: control flow, controlled batching, order-dependent stateful logic, transactional retries, and stateful algorithms.
9. Design large batch jobs to avoid overly long transactions, WAL spikes, and lock contention.
10. Structure readable, business-accurate, testable PostgreSQL code.

## 2. Why Does PL/pgSQL Have `LOOP` If We Shouldn't Overuse It?

PL/pgSQL is a procedural language providing variable declarations, `IF`, `CASE`, `LOOP`, `FOR`, `WHILE`, exception handling, and SQL calls. It shines when a workflow needs procedural control flow beyond a single SQL query.

Relational data, however, is naturally set-oriented. For example, "change status on all old unpaid orders" is a set filter via `WHERE` combined with an update to `status`—there is no need for each row to pass through a separate procedural loop iteration.

### 2.1. Two Execution Layers

```text
FOR r IN SELECT ... LOOP
    UPDATE ... WHERE id = r.id;
END LOOP;

PL/pgSQL layer:       pick one row -> bind to variable r
                     -> issue UPDATE -> continue loop

SQL executor layer:   plan/execute UPDATE,
                     find record, check locks/constraints
                     -> return control to PL/pgSQL
                     -> repeat for next row.
```

Compared with:

```text
UPDATE table SET ... WHERE ...;

SQL layer:            describe the entire row set
                     -> planner chooses scan/join
                     -> executor updates per plan
                     -> statement completes.
```

PL/pgSQL caches query plans and reduces dispatch overhead, so it is **not** accurate to claim every loop iteration always re-parses and re-plans SQL from scratch. Even so, context switches and individual statement executions can still add up enormously.

### 2.2. Three Distinct Kinds of Loops

1. **Row loops issuing per-row SQL:** e.g., `FOR r IN SELECT ... LOOP UPDATE ... WHERE id = r.id`. Primary candidates for set-based refactoring.
2. **In-memory computational loops:** e.g., array manipulation or stateful algorithms that would become unreadable if forced into SQL.
3. **Batch or coarse work-unit loops:** e.g., processing 10,000 IDs per chunk and committing/monitoring between chunks where permitted. That is batch-level iteration, not row-by-row RBAR, and can be operationally sound.

Never declare every `LOOP` bad blindly. Ask **how much work each iteration does and whether procedural ordering/control is truly required**.

## 3. Practice Dataset

Create a dedicated schema so all examples can run inside a lab database. Never run these on live production tables.

### 3.1. Customer and Order Tables

```sql
CREATE SCHEMA IF NOT EXISTS set_lab;

CREATE TABLE set_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    tier text NOT NULL
        CHECK (tier IN ('gold', 'silver', 'bronze'))
);

CREATE TABLE set_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES set_lab.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    discount numeric(12, 2) NOT NULL DEFAULT 0
        CHECK (discount >= 0)
);

CREATE TABLE set_lab.customer_totals (
    customer_id integer PRIMARY KEY
        REFERENCES set_lab.customers(customer_id),
    total_paid numeric(14, 2) NOT NULL DEFAULT 0,
    paid_orders bigint NOT NULL DEFAULT 0,
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE set_lab.audit_notes (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

### 3.2. Customer Data

```sql
INSERT INTO set_lab.customers (
    customer_id, full_name, tier
)
VALUES
    (1, 'Lan',  'gold'),
    (2, 'Minh', 'silver'),
    (3, 'Hoa',  'bronze'),
    (4, 'An',   'gold');
```

### 3.3. Order Data

```sql
INSERT INTO set_lab.orders (
    customer_id, ordered_at, status, amount
)
VALUES
    (1, DATE '2026-11-01', 'paid',      100.00),
    (1, DATE '2026-11-02', 'paid',       80.00),
    (1, DATE '2026-11-03', 'pending',    50.00),
    (2, DATE '2026-11-01', 'paid',      200.00),
    (2, DATE '2026-11-02', 'cancelled',  70.00),
    (3, DATE '2026-11-02', 'paid',       40.00),
    (4, DATE '2026-11-01', 'paid',      150.00),
    (4, DATE '2026-11-04', 'pending',   120.00);
```

Run these `INSERT` statements **once on empty tables**. Re-running them on `orders` generates new identity IDs and extra rows, throwing off counts in later examples. For exercises with `UPDATE`/`DELETE`, wrap them in `BEGIN; ...; ROLLBACK;` to keep the dataset clean.

### 3.4. Inspecting the Sample Set

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM set_lab.orders
GROUP BY status
ORDER BY status;
```

Results on the initial dataset:

| status | order_count | total_amount |
| --- | ---: | ---: |
| cancelled | 1 | 70.00 |
| paid | 5 | 570.00 |
| pending | 2 | 170.00 |

Total orders: **8**; total amount: **810.00**. This tiny dataset illustrates syntax and semantics, not a large enough benchmark to measure performance gains.

### 3.5. Relational Data Has Order Only with `ORDER BY`

Even though identity values are generated sequentially on insert, never assume `SELECT * FROM set_lab.orders` always returns rows sorted by `order_id`. Any exercise asking for "first" or "latest" uses an explicit `ORDER BY` with a tie-breaker.

## 4. Pattern 1: Many Small `UPDATE`s into One `UPDATE ... WHERE`

**Requirement:** set `discount = 5.00` on every `pending` order, without inspecting individual rows separately.

### 4.1. Loop Approach

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'pending'
    LOOP
        UPDATE set_lab.orders
        SET discount = 5.00
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;

ROLLBACK;
```

This yields the expected result in the lab, yet for one million `pending` orders it would dispatch one million internal `UPDATE` statements.

### 4.2. Set-Based Approach

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

SELECT order_id, status, amount, discount
FROM set_lab.orders
WHERE status = 'pending'
ORDER BY order_id;

ROLLBACK;
```

A single `UPDATE` describes every row to change. PostgreSQL can choose a sequential scan, index scan, bitmap scan, or other path based on table size and statistics.

### 4.3. Using `RETURNING` to Inspect Updated Rows

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
RETURNING order_id, customer_id, amount, discount;

ROLLBACK;
```

`RETURNING` reports the modified rows directly without looping back to `SELECT` each order ID. **The output order of `RETURNING` is not guaranteed without an enclosing sorted query.**

### 4.4. Do Not Assume `UPDATE` Eliminates WAL Overhead Completely

A set-based `UPDATE` still creates MVCC row versions, updates indexes, invokes triggers, writes WAL, and acquires row locks on updated rows. Its main wins are **better global execution plans and fewer statement dispatches**, not bypassing PostgreSQL's transactional guarantees.

## 5. Pattern 2: Per-Row `IF`/`ELSE` into `CASE` Inside `UPDATE`

**Requirement:** apply a discount rate to `paid` orders based on customer tier:

- Gold: 10%.
- Silver: 5%.
- Bronze: 0%.

### 5.1. A Familiar Loop

```sql
BEGIN;

DO $$
DECLARE
    r record;
    v_rate numeric;
BEGIN
    FOR r IN
        SELECT o.order_id, o.amount, c.tier
        FROM set_lab.orders AS o
        JOIN set_lab.customers AS c
          ON c.customer_id = o.customer_id
        WHERE o.status = 'paid'
    LOOP
        IF r.tier = 'gold' THEN
            v_rate := 0.10;
        ELSIF r.tier = 'silver' THEN
            v_rate := 0.05;
        ELSE
            v_rate := 0;
        END IF;

        UPDATE set_lab.orders
        SET discount = round(r.amount * v_rate, 2)
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;

ROLLBACK;
```

### 5.2. Set-Based SQL Using `CASE` and `UPDATE ... FROM`

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
      CASE c.tier
        WHEN 'gold' THEN 0.10
        WHEN 'silver' THEN 0.05
        ELSE 0
      END,
    2
)
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid'
RETURNING o.order_id, o.customer_id, o.amount, o.discount;

ROLLBACK;
```

Both the join condition and the tier lookup are folded into **a single SQL plan**.

### 5.3. Logical Result

Across the five initial `paid` orders:

| customer_id | amount | tier | discount |
| ---: | ---: | --- | ---: |
| 1 | 100.00 | gold | 10.00 |
| 1 | 80.00 | gold | 8.00 |
| 2 | 200.00 | silver | 10.00 |
| 3 | 40.00 | bronze | 0.00 |
| 4 | 150.00 | gold | 15.00 |

Total discount is **43.00**. Row order from `RETURNING` may vary; the table illustrates the result set.

### 5.4. When Branching Grows Large

A `CASE` expression with hundreds of branches becomes hard to maintain; if discount rates are business data, store a `tier → rate` mapping table with appropriate constraints and `JOIN` to it. Set-based does not mean stuffing every rule into one unreadable expression.

## 6. Pattern 3: Row-by-Row `INSERT` into `INSERT ... SELECT`

**Requirement:** record an audit note for every `paid` order.

### 6.1. Row-by-Row Insert Loop

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'paid'
    LOOP
        INSERT INTO set_lab.audit_notes(order_id, note)
        VALUES (r.order_id, 'Order paid');
    END LOOP;
END;
$$;

ROLLBACK;
```

### 6.2. Single `INSERT ... SELECT`

```sql
BEGIN;

INSERT INTO set_lab.audit_notes (order_id, note)
SELECT
    o.order_id,
    'Order paid'
FROM set_lab.orders AS o
WHERE o.status = 'paid'
RETURNING audit_id, order_id, note;

ROLLBACK;
```

On the sample data, `INSERT ... SELECT` produces **5 audit rows**. It is especially effective for:

- Moving rows into staging tables.
- Copying rows according to rules.
- Generating bulk internal notifications.
- Populating summary/result tables from joins and selects.

### 6.3. Idempotency Does Not Appear Automatically

Re-running the same `INSERT ... SELECT` without constraints or deduplication inserts **five more duplicate rows**. Set-based does not automatically mean idempotent.

If the system requires at most one `paid` audit note per order, design an explicit business key such as `(order_id, event_type)` and use `ON CONFLICT DO NOTHING` rather than relying on arbitrary unnormalized text as a unique key.

### 6.4. Do Not Confuse with `COPY`

`INSERT ... SELECT` transforms and inserts rows coming from an SQL query. For ingesting massive datasets from external files or streams, benchmark PostgreSQL `COPY`. Both avoid sending single-row `INSERT` commands from a client, yet they serve different workflows.

## 7. Pattern 4: Grouping Aggregates Instead of Accumulation Loops

**Requirement:** compute total `paid` amount and `paid` order count per customer.

### 7.1. Multi-Query Procedural Approach

Easy to write, high overhead:

```sql
DO $$
DECLARE
    r record;
    v_total numeric;
    v_count bigint;
BEGIN
    FOR r IN
        SELECT customer_id FROM set_lab.customers
    LOOP
        SELECT
            COALESCE(SUM(amount), 0),
            COUNT(*)
        INTO v_total, v_count
        FROM set_lab.orders
        WHERE customer_id = r.customer_id
          AND status = 'paid';

        RAISE NOTICE
            'customer %, revenue %, count %',
            r.customer_id, v_total, v_count;
    END LOOP;
END;
$$;
```

With 100,000 customers, this dispatches an aggregate query per customer. Without a matching index, each iteration could scan significant parts of `orders`.

### 7.2. Single `GROUP BY` Over the Set

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Result:

| customer_id | total_paid | paid_orders |
| ---: | ---: | ---: |
| 1 | 180.00 | 2 |
| 2 | 200.00 | 1 |
| 3 | 40.00 | 1 |
| 4 | 150.00 | 1 |

PostgreSQL can select `HashAggregate`, `GroupAggregate`, sorting, or hybrid plans depending on table statistics and indexes. You simply declare the aggregation.

### 7.3. Including Customers Without Any `paid` Orders

`GROUP BY` on `orders` alone only returns customers with at least one `paid` row. To include **every customer**, even those with none, use `LEFT JOIN` with properly scoped filtering:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ) AS total_paid,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

**Do not** casually move `o.status = 'paid'` into the `WHERE` clause if you must preserve customers without orders. Filtering a `LEFT JOIN`'s right-hand table in `WHERE` discards unmatched rows, defeating the goal of listing all customers.

### 7.4. `FILTER` Instead of Multiple `IF`s When Summarizing

```sql
SELECT
    customer_id,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS revenue
FROM set_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

One aggregate pass can compute multiple metrics simultaneously. If a group has zero matching `paid` rows, `SUM(...) FILTER (...)` returns SQL `NULL`; wrap it in `COALESCE(..., 0)` when the contract expects `0`.

## 8. Pattern 5: Bulk `UPSERT` Instead of Per-Key `SELECT`/`IF`/`UPDATE` Loops

**Requirement:** refresh `customer_totals` with current `paid` totals.

### 8.1. Per-Customer Loop

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT
            customer_id,
            SUM(amount) AS total_paid,
            COUNT(*) AS paid_orders
        FROM set_lab.orders
        WHERE status = 'paid'
        GROUP BY customer_id
    LOOP
        INSERT INTO set_lab.customer_totals (
            customer_id, total_paid, paid_orders
        )
        VALUES (
            r.customer_id, r.total_paid, r.paid_orders
        )
        ON CONFLICT (customer_id) DO UPDATE
            SET total_paid = EXCLUDED.total_paid,
                paid_orders = EXCLUDED.paid_orders,
                calculated_at = clock_timestamp();
    END LOOP;
END;
$$;

ROLLBACK;
```

### 8.2. Single `INSERT ... SELECT ... ON CONFLICT`

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id,
    total_paid,
    paid_orders
)
SELECT
    customer_id,
    SUM(amount),
    COUNT(*)
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp()
RETURNING
    customer_id, total_paid, paid_orders;

ROLLBACK;
```

Inside `ON CONFLICT`, `EXCLUDED` refers to the proposed row that triggered a key conflict; this is PostgreSQL's `UPSERT` mechanism.

### 8.3. Avoid Updating the Same Target Row Multiple Times

`INSERT ... ON CONFLICT DO UPDATE` does not permit one command to affect **the same existing target row more than once** nondeterministically. If the input `SELECT` emits two rows sharing a conflict key, PostgreSQL raises a cardinality violation. Deduplicate or aggregate inputs first, such as `GROUP BY customer_id` above.

### 8.4. Disappearing Groups

If a customer **no longer has any `paid` orders**, aggregating solely over `WHERE status = 'paid'` omits that customer. The `UPSERT` in 8.2 will **not automatically reset `total_paid = 0`** on an older `customer_totals` row. That is the difference between "upserting active groups" and "synchronizing complete state."

To include all customers, drive the query from `LEFT JOIN`:

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ),
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    )
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();

SELECT * FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

This resets customers without `paid` orders to `(0, 0)`. If a customer is deleted entirely from `customers` while stale summary rows remain, handle that separately via FK/cascade/cleanup policies.

### 8.5. `UPSERT` Is Not Always the Fastest Rebuild Strategy

When every row of a summary table needs rebuilding and brief read interruption or locking is acceptable, `TRUNCATE + INSERT` inside a transaction or swapping versioned tables can be cleaner. For live readers, weigh locks, consistency, and cost. Do not default to `UPSERT` blindly for rebuilding hundreds of millions of rows.

## 9. Pattern 6: Conditional/Relational `DELETE` Instead of Loops

**Requirement:** delete audit notes belonging to `cancelled` orders.

### 9.1. Row-by-Row Delete Loop

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'cancelled'
    LOOP
        DELETE FROM set_lab.audit_notes
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;
```

### 9.2. `DELETE ... USING`

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
USING set_lab.orders AS o
WHERE a.order_id = o.order_id
  AND o.status = 'cancelled'
RETURNING a.audit_id, a.order_id, a.note;

ROLLBACK;
```

This is a single `DELETE` statement with a join predicate. If no matching audit notes exist yet in the lab, deleting **0 rows** is expected.

### 9.3. `DELETE ... WHERE EXISTS`

A semantically clear alternative:

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
WHERE EXISTS (
    SELECT 1
    FROM set_lab.orders AS o
    WHERE o.order_id = a.order_id
      AND o.status = 'cancelled'
);

ROLLBACK;
```

`EXISTS` checks whether at least one matching row exists without requiring the subquery to yield a single row per target. PostgreSQL can plan it as a semijoin or suitable scan.

### 9.4. Respect Business Deletion Rules

A set-based `DELETE` can remove huge numbers of rows in a single transaction, creating heavy WAL, dead tuples, and lock contention. Always review retention rules, foreign keys, triggers, audit trails, and row volume before replacing a loop with an unbounded `DELETE`.

## 10. Pattern 7: `UPDATE ... FROM` Driven by a Result Set

In SQL, `UPDATE ... FROM` updates a target table using rows from a source relation or subquery:

```sql
UPDATE target AS t
SET target_column = s.computed_value
FROM (
    SELECT key, expression AS computed_value
    FROM source
) AS s
WHERE t.key = s.key;
```

The cardinal rule is that **each target row should match at most one source row**.

### 10.1. Correct Example: Mapping `customer_id` to `tier`

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = CASE c.tier
    WHEN 'gold' THEN round(o.amount * 0.10, 2)
    WHEN 'silver' THEN round(o.amount * 0.05, 2)
    ELSE 0
END
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid';

ROLLBACK;
```

`customers.customer_id` is a `PRIMARY KEY`, so joining on it matches at most one customer row per order.

### 10.2. Dangerous Example: Multiple Source Rows per Key

```sql
-- Semantically wrong if you want the total amount per customer:
-- UPDATE set_lab.customer_totals AS t
-- SET total_paid = o.amount
-- FROM set_lab.orders AS o
-- WHERE t.customer_id = o.customer_id;
```

One customer has multiple orders: one target row in `customer_totals` matches multiple rows in `orders`. PostgreSQL updates the target row from **one of the matching source rows**, with **no guarantee which one**. Never rely on `SELECT` order, heap layout, or `ORDER BY` to define behavior here.

### 10.3. Fix: Aggregate Before `UPDATE`

```sql
BEGIN;

INSERT INTO set_lab.customer_totals (
    customer_id, total_paid, paid_orders
)
SELECT
    customer_id, 0, 0
FROM set_lab.customers
ON CONFLICT (customer_id) DO NOTHING;

UPDATE set_lab.customer_totals AS t
SET
    total_paid = s.total_paid,
    paid_orders = s.paid_orders,
    calculated_at = clock_timestamp()
FROM (
    SELECT
        customer_id,
        SUM(amount) AS total_paid,
        COUNT(*) AS paid_orders
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS s
WHERE t.customer_id = s.customer_id;

SELECT * FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

`GROUP BY customer_id` yields at most one source row per target key, making the update deterministic. Customers with zero `paid` orders still need handling if they must be reset to `0`, because `GROUP BY` over `paid` orders produces no row for them.

### 10.4. Joins Multiplying Numbers in Calculations

If you join `orders` to `order_items` (one order with many items), taking `SUM(o.amount)` after joining inflates order totals by item count. That is a classic metric bug when collapsing loops into one large query.

The fix is aggregating at the **correct grain** prior to joining, or summing line-item values directly if intended. Never try to salvage it with `SUM(DISTINCT o.amount)`, which collapses two legitimate orders sharing the same dollar amount.

## 11. Pattern 8: Running Totals and Previous-Row Comparisons via Window Functions

A common excuse for loops is "each row needs the running sum of preceding rows." Often, SQL window functions express that directly.

### 11.1. Running Total per Customer

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_paid_total
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Explanation:

- `PARTITION BY customer_id` defines a logical window per customer.
- `ORDER BY ordered_at, order_id` fixes row order inside each partition.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` spans from the start of the partition up to the current row.
- `SUM(amount) OVER (...)` computes the running total without a loop or accumulator `v_sum`.

For customer 1, the two `paid` orders of 100 and 80 yield running totals **100** and **180**.

### 11.2. `LAG` to Access the Previous Row

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_paid_amount
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

`LAG` returns SQL `NULL` when no preceding row exists in the partition. Use `COALESCE` if business logic wants a fallback, while still distinguishing "no prior row" from an actual `0` order amount.

### 11.3. `ROWS` vs. `RANGE` in Window Frames

Never treat `ROWS` and `RANGE` as interchangeable when rows can tie on the `ORDER BY` key. For order-by-order running totals, `ROWS` paired with a unique `order_id` tie-breaker gives predictable results.

### 11.4. When Complex Stateful Algorithms Are Still Needed

If every step alters state based on prior outcomes in ways window functions or recursive CTEs cannot express cleanly, procedural logic can fit well. Even then, check window functions first before coding an accumulator or "find previous order" loop by hand.

## 12. Pattern 9: Picking the Latest Row per Group Without Loops

**Requirement:** find each customer's most recent order.

### 12.1. Loop Approach

```sql
DO $$
DECLARE
    r record;
    v_order record;
BEGIN
    FOR r IN SELECT customer_id FROM set_lab.customers
    LOOP
        SELECT order_id, ordered_at, status
        INTO v_order
        FROM set_lab.orders
        WHERE customer_id = r.customer_id
        ORDER BY ordered_at DESC, order_id DESC
        LIMIT 1;

        RAISE NOTICE 'customer %, order %',
            r.customer_id, v_order.order_id;
    END LOOP;
END;
$$;
```

This runs N separate queries for N customers. At scale, multiple set-based alternatives exist.

### 12.2. PostgreSQL `DISTINCT ON`

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status
FROM set_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
```

`DISTINCT ON (customer_id)` keeps one representative row per group. `ORDER BY` starts with the grouping key, then orders newest first, using `order_id DESC` as tie-breaker for same-day orders.

`DISTINCT ON` is a convenient PostgreSQL extension, not standard SQL across every RDBMS.

### 12.3. `ROW_NUMBER` per Group

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM set_lab.orders
)
SELECT customer_id, order_id, ordered_at, status
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

This is standard portable SQL. `ROW_NUMBER` also generalizes smoothly to top-N per group via `WHERE rn <= N`.

### 12.4. `LATERAL` When Each Group Suits an Indexed Subquery

```sql
SELECT
    c.customer_id,
    o.order_id,
    o.ordered_at,
    o.status
FROM set_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, ordered_at, status
    FROM set_lab.orders
    WHERE customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS o ON TRUE
ORDER BY c.customer_id;
```

`LATERAL` lets the subquery reference `c.customer_id`. Internally it may still perform indexed lookups per customer inside the execution plan, yet **without bouncing every row across PL/pgSQL**. With an index on `(customer_id, ordered_at DESC, order_id DESC)` and sparse outer keys, it can be very effective depending on planner estimates and workload.

### 12.5. Never Replace a Loop with an Unordered Set Query

`DISTINCT ON` or `ROW_NUMBER` with only `ORDER BY ordered_at DESC` (omitting the tie-breaker) picks arbitrarily between same-day orders. Procedural code can suffer the same bug if `LIMIT 1` lacks deterministic sorting. Always ensure **"latest" is completely specified** during conversion.

## 13. Pattern 10: Replacing Date/Number Generation Loops with `generate_series`

PL/pgSQL often uses loops to generate reporting periods:

```sql
DO $$
DECLARE
    v_day date := DATE '2026-11-01';
BEGIN
    WHILE v_day <= DATE '2026-11-07' LOOP
        RAISE NOTICE '%', v_day;
        v_day := v_day + 1;
    END LOOP;
END;
$$;
```

When the goal is producing a **series of dates** to join against, PostgreSQL offers `generate_series`:

```sql
SELECT g.day_ts::date AS sale_date
FROM generate_series(
    TIMESTAMP '2026-11-01',
    TIMESTAMP '2026-11-07',
    INTERVAL '1 day'
) AS g(day_ts)
ORDER BY sale_date;
```

### 13.1. Calendar Table with Daily Revenue

```sql
WITH days AS (
    SELECT g.day_ts::date AS sale_date
    FROM generate_series(
        TIMESTAMP '2026-11-01',
        TIMESTAMP '2026-11-07',
        INTERVAL '1 day'
    ) AS g(day_ts)
),
revenue AS (
    SELECT
        ordered_at AS sale_date,
        SUM(amount) AS revenue
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY ordered_at
)
SELECT
    d.sale_date,
    COALESCE(r.revenue, 0) AS revenue
FROM days AS d
LEFT JOIN revenue AS r
  ON r.sale_date = d.sale_date
ORDER BY d.sale_date;
```

Days without `paid` orders still appear with `0` revenue—no per-day `INSERT`/`SELECT` loop needed.

### 13.2. `generate_series` Isn't Limited to Dates

```sql
SELECT n
FROM generate_series(1, 10) AS s(n);
```

Still, never generate billions of rows into one giant CTE just to eliminate a loop that belongs in batches. Evaluate cardinality, output volume, and true purpose.

## 14. Pattern 11: Handling Arrays with `UNNEST` or `= ANY`

A PL/pgSQL function receives `integer[]` of customer IDs and iterates:

```sql
DO $$
DECLARE
    v_ids integer[] := ARRAY[1, 2, 4];
    v_id integer;
BEGIN
    FOREACH v_id IN ARRAY v_ids LOOP
        RAISE NOTICE 'customer ID %', v_id;
    END LOOP;
END;
$$;
```

When the goal is filtering, no loop is necessary.

### 14.1. `ANY` with an Array Parameter

```sql
SELECT
    order_id, customer_id, amount, status
FROM set_lab.orders
WHERE customer_id = ANY(ARRAY[1, 2, 4]::integer[])
ORDER BY customer_id, order_id;
```

With `$1::integer[]` in a prepared query, the same predicate receives the entire list from the client. The planner chooses the scan path based on cardinality and statistics.

### 14.2. `UNNEST` to Turn an Array into a Relation

```sql
SELECT
    ids.customer_id,
    c.full_name
FROM unnest(ARRAY[1, 2, 4]::integer[])
    AS ids(customer_id)
JOIN set_lab.customers AS c
  ON c.customer_id = ids.customer_id
ORDER BY ids.customer_id;
```

`UNNEST` shines when you need to `JOIN` or treat the input array as a table. If the array contains duplicate IDs, `UNNEST` preserves duplicates, which multiplies joined rows unless deduplicated. By contrast, `= ANY(...)` tests membership without multiplying customer rows per duplicate array item.

### 14.3. Arrays Containing `NULL`

`customer_id = ANY(ARRAY[NULL::integer])` yields SQL `UNKNOWN` rather than `FALSE`. If non-`NULL` membership semantics are desired, sanitize input arrays or define `NULL` handling explicitly to avoid three-valued logic surprises.

### 14.4. Huge ID Lists

For millions of IDs, a gigantic array stresses memory and transport; bulk-loading into a staging/temporary table, indexing, and running `ANALYZE` can perform better. Set-based never mandates stuffing everything into **one colossal array expression**.

## 15. Pattern 12: `JSONB` Arrays and Expanding Row Sets

A JSON payload carrying multiple items:

```json
{"items":[{"sku":"A","qty":2},{"sku":"B","qty":1}]}
```

Instead of parsing each object inside an SQL/PLpgSQL loop, expand the JSON array into rows with `jsonb_array_elements`:

```sql
SELECT
    item ->> 'sku' AS sku,
    (item ->> 'qty')::integer AS qty
FROM jsonb_array_elements(
    '[
        {"sku":"A","qty":2},
        {"sku":"B","qty":1}
    ]'::jsonb
) AS i(item);
```

### 15.1. Using `jsonb_to_recordset` When Schema Is Known

```sql
SELECT sku, qty
FROM jsonb_to_recordset(
    '[
        {"sku":"A","qty":2},
        {"sku":"B","qty":1}
    ]'::jsonb
) AS x(sku text, qty integer);
```

The result is a relation with typed columns ready to join against reference tables to validate SKUs before inserting.

### 15.2. Validate Input Before Casting

Recordset/cast expressions fail if `qty` is non-numeric or the JSON is not an array. For user input, validate missing keys, JSON `null`s, negative quantities, duplicate SKUs, and max element counts.

Set-based expansion eliminates the import loop, yet it does not enforce schema contracts or authorization on its own.

### 15.3. Bulk `INSERT` from JSON

```sql
CREATE TABLE set_lab.order_item_staging (
    sku text NOT NULL,
    qty integer NOT NULL CHECK (qty > 0)
);

INSERT INTO set_lab.order_item_staging (sku, qty)
SELECT sku, qty
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb
) AS x(sku text, qty integer);
```

This is a minimal illustration turning a JSON array into rows. In real imports, staging tables require batch IDs, duplicate checks, and clear commit/rollback/cleanup policies.

## 16. Using CTEs to Break Transformations into Intermediate Sets

When a transformation is complex, you do not have to cram a loop into one dense, cryptic SQL statement. **Common Table Expressions (CTEs)** let you name intermediate row sets inside one statement.

### 16.1. Multi-Step Example: Compute Revenue, Rank, and Filter Customers

```sql
WITH revenue_by_customer AS (
    SELECT
        customer_id,
        SUM(amount) AS revenue
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        DENSE_RANK() OVER (
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM revenue_by_customer
)
SELECT
    c.customer_id,
    c.full_name,
    r.revenue,
    r.revenue_rank
FROM ranked AS r
JOIN set_lab.customers AS c
  ON c.customer_id = r.customer_id
WHERE r.revenue_rank <= 3
ORDER BY r.revenue_rank, r.customer_id;
```

In the lab, customer revenues are 200, 180, 150, 40. The top three are customers 2, 1, and 4.

### 16.2. A CTE Is Not a PL/pgSQL Variable

A CTE is a relational expression scoped to one SQL statement; it does not persist data across multiple statements like a temporary table, does not commit per step, and cannot be referenced by a subsequent statement.

### 16.3. The Planner Can Inline CTEs

In modern PostgreSQL major versions, non-recursive, side-effect-free CTEs meeting optimizer rules can be folded/inlined into the parent query instead of always being materialized; `MATERIALIZED` and `NOT MATERIALIZED` allow explicit overrides where applicable.

Never claim "`WITH` always builds a temp table first before running the next step." Always check `EXPLAIN` instead of guessing.

### 16.4. Data-Modifying CTEs

PostgreSQL supports *data-modifying CTEs* under valid syntactic rules, passing changed rows to the outer statement via `RETURNING`:

```sql
BEGIN;

WITH changed AS (
    UPDATE set_lab.orders
    SET discount = 2.00
    WHERE status = 'pending'
    RETURNING order_id, discount
)
INSERT INTO set_lab.audit_notes(order_id, note)
SELECT
    order_id,
    'Discount changed to ' || discount::text
FROM changed
RETURNING audit_id, order_id, note;

ROLLBACK;
```

**Goal:** feed the exact rows modified by `UPDATE` straight into the audit `INSERT`, without re-querying the table per order ID.

### 16.5. Avoid Relying on Unspecified Execution Order Among DML CTEs

If a statement has multiple data-modifying CTEs, never assume they execute sequentially in top-to-bottom source order or see each other's table edits directly. PostgreSQL runs them under the same snapshot with an implementation-defined order; pass data via `RETURNING` rather than re-reading the target table expecting another CTE's writes.

Never update the same target row twice inside one complex statement relying on CTE text order to pick the winner.

## 17. Set-Based SQL and Transactional Consistency

A loop:

```sql
FOR r IN SELECT ... LOOP
    UPDATE ... WHERE id = r.id;
END LOOP;
```

and a single `UPDATE ... WHERE ...` can differ in **duration, snapshots, and visibility of concurrent changes**, not just speed.

### 17.1. Statement Atomicity

A standard `UPDATE` statement is atomic within its transaction. If an error occurs and the transaction rolls back, PostgreSQL does not leave "the first half of the statement's rows" committed. Uncommitted changes roll back per transaction semantics.

### 17.2. A Loop Inside One Transaction Is Also Atomic

If an entire `DO $$ ... LOOP ... $$` runs inside a single transaction without per-row exception handlers swallowing errors, PostgreSQL does not auto-commit each iteration either. Hence it is **inaccurate** to claim loops inherently commit early rows while failing later ones.

Real differences lie in statement dispatch counts, lock timing, snapshot boundaries, and how errors are handled.

### 17.3. `READ COMMITTED` Uses Multiple Command Snapshots

At the default `READ COMMITTED` isolation level, consecutive SQL statements take fresh snapshots. If a loop fires a new `UPDATE` for every row, concurrent transactions can commit in between iterations, altering what subsequent iterations see.

A single set-based `UPDATE` follows **one-statement** snapshot/MVCC/locking rules. When refactoring, confirm whether the business logic expects "one consistent point-in-time row set" or "re-evaluating concurrent commits per step."

### 17.4. A Large `UPDATE` Does Not Freeze Readers Entirely

It acquires the appropriate table lock mode and row-level locks on modified rows. Plain `SELECT` readers keep reading via MVCC snapshots, while concurrent writers touching the same rows block or contend.

Never interpret set-based as "lock-free."

### 17.5. Statements After `UPDATE` Inside the Same Transaction

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

SELECT COUNT(*)
FROM set_lab.orders
WHERE status = 'pending'
  AND discount = 5.00;

ROLLBACK;
```

Subsequent `SELECT`s in the same transaction see the transaction's own writes per PostgreSQL visibility rules, while other sessions cannot see uncommitted changes.

### 17.6. When Rows Must Be Locked Before Deciding

Certain workflows—like assigning orders to workers—must pick unprocessed items and **claim exclusive ownership** so two workers never process the same item. Set-based SQL can pair with `SELECT ... FOR UPDATE SKIP LOCKED`, while accounting for fairness, retries, and skipped rows.

Never use `SKIP LOCKED` as a shortcut to speed up reporting `SELECT`s: it intentionally omits locked rows, yielding incomplete reports.

## 18. Risks of Packing Too Much Into One Giant Statement

A single SQL statement can modify ten million rows. That removes loop overhead, yet intensifies operational pressure:

- Transactions holding row locks for a long time.
- Large WAL spikes and replication lag.
- Heavy dead-tuple generation and autovacuum load after massive `UPDATE`/`DELETE`.
- Temp disk spills from large sorts/hashes.
- Expensive rollback if the statement aborts late.
- Contention against concurrent OLTP transactions.
- Read/write latency spikes from saturated I/O.

### 18.1. Set-Based Does Not Always Mean "One Monolithic Statement"

To update 100 million rows in production, break the work into **multiple batches**, where each batch executes one set-based SQL statement—say 5,000–50,000 rows along a stable key—committing at clean boundaries via an external orchestrator or eligible procedure.

### 18.2. Sizing Batches Empirically

No universal "5,000 is optimal" rule fits every database. Measure:

- Rows and bytes modified per batch.
- Lock and transaction duration.
- WAL and temp volume generated.
- Peak-hour throughput.
- Autovacuum catch-up and replication lag.
- Latency SLAs for concurrent writers.

Batch size is an **operational parameter to benchmark**, not an arbitrary constant in code.

## 19. Batch `UPDATE` Over a Bounded Key Set

PostgreSQL has no direct `UPDATE ... LIMIT N` syntax like some other databases. A common idiom selects a bounded ordered key batch and updates via `FROM`:

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM set_lab.orders
    WHERE status = 'pending'
      AND discount = 0
    ORDER BY order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE set_lab.orders AS o
SET discount = 5.00
FROM batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id, o.discount;

ROLLBACK;
```

### 19.1. Why Use a Deterministic Unique Key?

`ORDER BY order_id` selects a deterministic batch. Because `order_id` is a `PRIMARY KEY`, no target row ever matches multiple source rows.

`FOR UPDATE SKIP LOCKED` locks the chosen rows while skipping rows locked by other transactions—handy for **queue-style worker patterns**. Note that skipped rows are bypassed in this pass and must be revisited in subsequent runs.

### 19.2. Batching Is Not `OFFSET` Pagination

Looping with:

```sql
-- Wrong concept on a changing dataset:
-- OFFSET 0 LIMIT 100
-- OFFSET 100 LIMIT 100
-- OFFSET 200 LIMIT 100
```

skips or double-processes rows whenever updates change what matches `WHERE` or change sort order. When flipping `discount = 0` to `5`, each batch should keep selecting **remaining `discount = 0` rows** instead of shifting `OFFSET`.

### 19.3. Who Coordinates Multiple Batches?

An external orchestrator or an eligible PostgreSQL procedure can:

1. Execute one set-based `UPDATE` batch.
2. Check affected row count.
3. `COMMIT`.
4. Check elapsed time and system health.
5. Repeat until no eligible rows remain—with retries for rows skipped via `SKIP LOCKED`.

**Never** wrap all batches inside one giant transaction and expect the lock, WAL, or rollback footprint of separate small transactions.

### 19.4. When `SKIP LOCKED` Is Inappropriate

If a batch must compute an exact report or guarantee processing every single row under one consistent snapshot, skipping locked rows produces incomplete work. Use blocking waits, retries, or maintenance windows instead.

## 20. PL/pgSQL `PROCEDURE` and Batched `COMMIT`

PostgreSQL distinguishes:

- **Functions** invoked via `SELECT function(...)`: cannot arbitrarily `COMMIT` inside.
- **Procedures** invoked via `CALL procedure(...)`: can perform transaction control in valid call contexts.
- **`DO` blocks**: support transaction control under eligible conditions, subject to constraints—especially when nested inside an explicit transaction block.

### 20.1. Do Not Write `COMMIT` Inside Arbitrary Loops

Never write:

```sql
-- Invalid pattern inside a PL/pgSQL FUNCTION:
-- LOOP
--     UPDATE ...;
--     COMMIT;
-- END LOOP;
```

Transaction control in PostgreSQL depends on call stack and caller context; not every function, procedure, or `DO` block may issue `COMMIT`.

### 20.2. Batch Loops Still Use Set-Based SQL Inside

Even inside a batched procedure, each chunk should run a set-based statement:

```sql
WITH batch AS (
    SELECT id FROM work_queue
    WHERE status = 'ready'
    ORDER BY id
    LIMIT 5000
    FOR UPDATE SKIP LOCKED
)
UPDATE work_queue AS q
SET status = 'processing'
FROM batch AS b
WHERE q.id = b.id;
```

This is a **pattern template** (`work_queue` is not part of the lab schema). It demonstrates **looping at the batch level while executing set-based SQL inside**, rather than running 5,000 single-row `UPDATE` iterations.

### 20.3. Transaction Control Conditions

Procedures called via top-level `CALL` or eligible nested `CALL`/`DO` chains can run `COMMIT`/`ROLLBACK`, provided no explicit outer transaction block or disallowed intermediate `SELECT` blocks it per PostgreSQL rules. A `CALL` issued inside a framework-managed JDBC transaction typically **forbids** `COMMIT` inside the procedure.

Check the documentation for your **exact PostgreSQL major version** and design commit orchestration intentionally instead of moving a function into a procedure solely to inject `COMMIT`.

### 20.4. `EXCEPTION` Blocks Restrict Transaction Control

A PL/pgSQL block with an `EXCEPTION` handler creates a subtransaction, and PostgreSQL forbids terminating the transaction inside a block containing exception handlers. If batches must both commit individually and catch errors, design the procedure/orchestration structure accordingly.

### 20.5. When Exact Checkpoints and Retries Matter

For huge migrations, external job runners are often easier to observe: persist the last completed key/range, commit each batch independently, enforce idempotent retries, and emit alerts. Procedures can work too, provided logging, timeouts, and crash-recovery logic are explicitly engineered.

## 21. Triggers: A Set-Based `UPDATE` Can Still Fire Row-Level Logic

A common misconception is "switching a loop to one `UPDATE` skips triggers." In PostgreSQL, if a table defines a **row-level trigger**, a single `UPDATE` touching 10,000 rows still fires that trigger **10,000 times—once per row**.

### 21.1. What Does a Row Trigger Do?

```text
UPDATE orders SET discount = ... WHERE ...
        |
        +--> row 1: BEFORE/AFTER ROW trigger
        +--> row 2: BEFORE/AFTER ROW trigger
        +--> ...
        +--> row N: BEFORE/AFTER ROW trigger
```

Consolidating into one SQL statement does not eliminate constraints, triggers, or index maintenance per row. If the row trigger itself runs heavy per-row SQL, it becomes the new bottleneck once the outer loop is gone.

### 21.2. Statement-Level Triggers

PostgreSQL also supports `FOR EACH STATEMENT` triggers, fired once per statement rather than once per row.

Where **transition relations** apply, an `AFTER ... FOR EACH STATEMENT` trigger can read the entire set of `OLD` and `NEW` rows at once.

Standalone illustrative example below—**create it only at the end of the lab** because it alters subsequent `UPDATE` behavior:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.audit_discount_changes_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO set_lab.audit_notes(order_id, note)
    SELECT
        n.order_id,
        'Discount: '
        || o.discount::text
        || ' -> '
        || n.discount::text
    FROM new_rows AS n
    JOIN old_rows AS o USING (order_id)
    WHERE o.discount IS DISTINCT FROM n.discount;

    RETURN NULL;
END;
$$;

CREATE TRIGGER tr_audit_discount_statement
AFTER UPDATE ON set_lab.orders
REFERENCING
    OLD TABLE AS old_rows
    NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION
    set_lab.audit_discount_changes_statement();
```

Test:

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 9.00
WHERE status = 'pending';

SELECT order_id, note
FROM set_lab.audit_notes
ORDER BY audit_id;

ROLLBACK;
```

Within that transaction, the trigger inserts audit notes only for **rows whose discount actually changed**, using a single `INSERT ... SELECT` over transition tables. `ROLLBACK` undoes the test update and audit notes while keeping the trigger definition you created.

### 21.3. Limits of Transition Tables

Not every trigger can use transition tables—they carry restrictions on events, timing, relation types, and syntax (available on eligible `AFTER` triggers). You cannot mechanically convert a `BEFORE ROW` trigger into `AFTER STATEMENT` and keep identical semantics.

If business rules must validate or mutate **each `NEW` row prior to storage**, a `BEFORE ROW` trigger remains necessary, because statement triggers cannot modify incoming `NEW` row fields row by row.

### 21.4. Trigger Side Effects Can Alter Semantics

Switching from N `UPDATE` statements to 1 `UPDATE` changes:

- How many times statement-level triggers fire.
- Row counts visible inside transition tables.
- Ordering/timing of audits, notifications, and validation.
- Values of `statement_timestamp()`, `clock_timestamp()`, or volatile functions.

Therefore, SQL rewrites must preserve **full business behavior**, not just final column values.

## 22. Per-Row `EXCEPTION` Loops: Set-Based Changes Error Semantics

An import workflow sometimes skips malformed rows while continuing to process valid ones:

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT ... LOOP
        BEGIN
            -- Process a record.
        EXCEPTION WHEN unique_violation THEN
            -- Record error/duplicate and continue.
            NULL;
        END;
    END LOOP;
END;
$$;
```

This is a structural skeleton; do not run it verbatim since `SELECT ...` is a placeholder.

### 22.1. A Set-Based `INSERT` Can Fail the Entire Statement

If rewritten as:

```sql
INSERT INTO target (...)
SELECT ...
FROM import_staging;
```

and a single row violates a constraint, **the entire statement** fails and rolls back its work. That differs from a per-row `EXCEPTION` loop whose subtransactions preserve prior valid rows within the same transaction.

### 22.2. Set-Based Pipelines Can Pre-Classify Errors

Often the cleaner solution is:

1. Load raw data into a **staging table** with permissive text/raw columns.
2. Use set-based SQL to classify valid vs. invalid rows.
3. Write invalid rows to an error table or report.
4. `INSERT` valid rows into the target table.
5. Handle expected duplicate keys with `ON CONFLICT` per business policy.

There is no reason to open a subtransaction per row merely to catch validation errors predictable via SQL checks.

### 22.3. Catching Numeric Format Errors via Staging

```sql
CREATE TABLE set_lab.raw_amounts (
    source_id text PRIMARY KEY,
    amount_text text
);

INSERT INTO set_lab.raw_amounts (source_id, amount_text)
VALUES
    ('A', '100.50'),
    ('B', 'bad'),
    ('C', NULL),
    ('D', '0'),
    ('E', '19.123');
```

Classify and conditionally cast:

```sql
SELECT
    source_id,
    amount_text,
    CASE
        WHEN amount_text ~
            '^[0-9]+([.][0-9]{1,2})?$'
        THEN amount_text::numeric(12,2)
        ELSE NULL
    END AS amount_value,
    CASE
        WHEN amount_text IS NULL
            THEN 'MISSING'
        WHEN amount_text ~
            '^[0-9]+([.][0-9]{1,2})?$'
            THEN 'VALID_FORMAT'
        ELSE 'INVALID_FORMAT'
    END AS validation_status
FROM set_lab.raw_amounts
ORDER BY source_id;
```

Here, A and D have valid format; B and E are rejected; C is missing. Note that a regex check **alone is not enough** to guarantee every huge number fits into `numeric(12,2)`, due to precision/scale bounds; production pipelines must validate range/overflow as well.

### 22.4. When Per-Row Exceptions Are Still Needed

Some extension functions or external conversions fail in ways impractical to anticipate safely in SQL predicates. When isolating per-row errors truly requires catching exceptions, a loop with `EXCEPTION` is valid—just keep in mind that each exception block carries subtransaction overhead.

Never turn every exception into "ignore silently" just to keep a batch green. Enforce auditing, retry policies, and error thresholds.

## 23. Order-Dependent Stateful Logic: Where Set-Based Is Not Equivalent

Consider a stateful sequence:

```text
initial balance = 100
txn 1: subtract 60
txn 2: subtract 60 if sufficient
```

Processed in strict order:

1. Transaction 1 succeeds; balance drops to 40.
2. Transaction 2 fails due to insufficient funds.

You cannot blindly collapse this into `SUM(-60 - 60)` and check the final balance, ignoring per-step admission checks, ordering, and individual accept/reject outcomes.

### 23.1. Loops Fit When Each Step Alters the Conditions for the Next

Examples:

- Sequential ledger balance checks rejecting overdrafts step by step.
- Stateful graph algorithms awkward to express cleanly in SQL.
- Invoking a function whose arguments depend on the previous step's output.
- Workflows involving external I/O with per-step retries.

### 23.2. Still Check Window Functions / Recursive CTEs First

If you only need to **analyze** running balances and flag overdraft points, window functions work nicely:

```sql
WITH payments AS (
    SELECT 1 AS seq, -60 AS delta
    UNION ALL
    SELECT 2 AS seq, -60 AS delta
)
SELECT
    seq,
    delta,
    100 + SUM(delta) OVER (
        ORDER BY seq
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS hypothetical_balance
FROM payments
ORDER BY seq;
```

This yields hypothetical balances 40 and -20. It **detects the problem**, yet it **does not execute the accept/reject branching that skips subtracting the second transaction**. Whenever decisions depend on previously accepted state, design the stateful algorithm explicitly.

### 23.3. Recursive CTEs for Well-Defined Recursion

```sql
WITH RECURSIVE sequence(n) AS (
    VALUES (1)
    UNION ALL
    SELECT n + 1
    FROM sequence
    WHERE n < 7
)
SELECT n
FROM sequence
ORDER BY n;
```

This is a toy integer example (`generate_series(1, 7)` is simpler). For hierarchies, parent-child graphs, and iterative data traversals, recursive CTEs can replace procedural loops.

Still, ensure termination conditions, cycle prevention, and bounded working tables; never cram multi-step I/O or transactional orchestration into a recursive CTE solely to avoid writing `LOOP`.

## 24. Optimizing at Scale: Indexes and Statistics Still Matter

Set-based SQL describes *what* to do, not *how* fast storage is accessed. PostgreSQL still needs proper access paths:

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
  AND ordered_at < DATE '2026-11-10';
```

If the table has 500 million rows and only 0.1% are `pending`, a targeted index shrinks the scan dramatically:

```sql
CREATE INDEX idx_orders_pending_date
ON set_lab.orders (ordered_at, order_id)
WHERE status = 'pending';
```

A partial index containing only `pending` rows accelerates matching queries, while requiring index maintenance when rows enter or leave `pending`. Never create indexes without measuring your write/read workload.

### 24.1. An Index May Legitimately Be Skipped

On our 8-order lab table, PostgreSQL picks a `Seq Scan` even with indexes because scanning one tiny page is cheapest. Never judge a set-based query slow just because an 8-row test shows `Seq Scan`.

### 24.2. `ANALYZE` and Cardinality Estimates

```sql
ANALYZE set_lab.orders;
```

Statistics help the planner estimate matching rows for `WHERE` and pick scan/join strategies. After bulk loads or major distribution shifts, stale stats can yield poor plans.

### 24.3. Match Composite Indexes to Access Patterns

If hot queries filter by `customer_id = ?` and `ordered_at`, `(customer_id, ordered_at)` fits well. Conversely, an `UPDATE` modifying most of the table won't benefit from it. Design indexes for specific critical queries, not arbitrary column combinations.

### 24.4. Excess Indexes Slow Down Writes

Every `INSERT`/`UPDATE`/`DELETE` maintains affected indexes. When a set-based rewrite updates millions of rows, index maintenance can dominate runtime. Always weigh write amplification alongside `SELECT` speed.

## 25. Reading `EXPLAIN` to Compare Instead of Guessing

PostgreSQL offers:

```sql
EXPLAIN
SELECT *
FROM set_lab.orders
WHERE status = 'pending';
```

`EXPLAIN` without `ANALYZE` prints estimated plan costs only. Adding `ANALYZE` actually runs the SQL and records measured metrics.

### 25.1. Safely Benchmarking an `UPDATE` in the Lab

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

ROLLBACK;
```

**Critical:** `EXPLAIN (ANALYZE) UPDATE` actually modifies rows. `ROLLBACK` restores the lab afterwards. Never run write benchmarks casually in production without a deliberate plan.

### 25.2. Timing a Loop with `clock_timestamp()`

```sql
BEGIN;

DO $$
DECLARE
    v_started timestamptz := clock_timestamp();
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'pending'
    LOOP
        UPDATE set_lab.orders
        SET discount = 5.00
        WHERE order_id = r.order_id;
    END LOOP;

    RAISE NOTICE 'Loop elapsed ms: %',
        1000 * EXTRACT(
            EPOCH FROM clock_timestamp() - v_started
        );
END;
$$;

ROLLBACK;
```

This shows basic internal timing; timing 8 rows proves nothing meaningful. To compare fairly, build a realistic dataset in an isolated lab and measure repeatedly under identical indexes and transaction states.

### 25.3. Metrics Worth Inspecting

| Metric | Meaning in set-based tuning |
| --- | --- |
| Actual rows / loops | How many rows and iterations actually executed? |
| Buffers hit / read | How many buffer accesses and disk reads occurred? |
| Planning Time | Overhead spent planning large SQL statements |
| Execution Time | Measured runtime for the statement |
| Sort/Hash memory/disk | Did operations spill to temp disk? |
| Rows Removed by Filter | Are predicates as selective as expected? |
| Trigger time | Are row triggers dominating DML cost? |
| External WAL/disk metrics | Is write load or replication lag spiking? |

`EXPLAIN (ANALYZE, BUFFERS)` reports a subset of these depending on query and PostgreSQL version; WAL statistics require the `WAL` option or external tools rather than appearing automatically.

### 25.4. Make Comparisons Fair

Ensure that:

1. Both the loop and set-based query perform **identical business work**.
2. Data, indexes, and distributions match.
3. Row volume is large enough to expose real overhead.
4. Both start from equivalent cache/table state, with proper resets/rollbacks.
5. Multiple runs are measured to smooth cache/CPU/I/O noise.
6. Lock contention and WAL are observed alongside single-run duration.

Never benchmark a 100-row loop against a 1-million-row SQL `UPDATE` and draw conclusions.

## 26. PL/pgSQL `RETURN NEXT` vs. `RETURN QUERY`

A set-returning PL/pgSQL function can loop row by row:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_loop()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT
            o.order_id, o.customer_id, o.amount
        FROM set_lab.orders AS o
        WHERE o.status = 'paid'
    LOOP
        order_id := r.order_id;
        customer_id := r.customer_id;
        amount := r.amount;
        RETURN NEXT;
    END LOOP;
END;
$$;
```

When no per-row logic is genuinely needed, use `RETURN QUERY`:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_set()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.order_id, o.customer_id, o.amount
    FROM set_lab.orders AS o
    WHERE o.status = 'paid';
END;
$$;
```

Test:

```sql
SELECT *
FROM set_lab.list_paid_orders_set()
ORDER BY customer_id, order_id;
```

### 26.1. Benefits

`RETURN QUERY` expresses the result set as a single SQL query without copying fields into output variables and calling `RETURN NEXT` repeatedly.

### 26.2. Returning Sets Does Not Guarantee Row-by-Row Streaming

PL/pgSQL set-returning functions using `RETURN NEXT` or `RETURN QUERY` currently **materialize their result set** (in memory/temp storage bounded by `work_mem`); never assume they stream rows to the client the instant `RETURN NEXT` runs.

If you only need to return a `SELECT` without procedural logic, an **SQL function** or direct query/view is simpler and lets the planner optimize/inline cleanly where eligible:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_sql()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT o.order_id, o.customer_id, o.amount
    FROM set_lab.orders AS o
    WHERE o.status = 'paid';
$$;
```

Never mark a function reading mutable table data as `IMMUTABLE`; always declare volatility accurately.

## 27. PL/pgSQL `SELECT INTO`, `PERFORM`, and SQL Call Counts

In PL/pgSQL:

```sql
SELECT COUNT(*)
INTO v_count
FROM set_lab.orders
WHERE status = 'paid';
```

is a single scalar query—completely idiomatic. Set-based thinking never forbids `SELECT INTO` or `PERFORM`.

### 27.1. Watch Out When Inside Unnecessary Loops

Writing:

```sql
FOR r IN SELECT customer_id FROM set_lab.customers LOOP
    SELECT COUNT(*)
    INTO v_count
    FROM set_lab.orders
    WHERE customer_id = r.customer_id;
END LOOP;
```

issues one aggregation/lookup per customer. If you simply need counts across customers, `GROUP BY` or `LEFT JOIN + FILTER` is clearer.

### 27.2. `GET DIAGNOSTICS ROW_COUNT`

After an SQL `UPDATE`/`DELETE`, PL/pgSQL can read the affected row count without iterating over `RETURNING`:

```sql
DO $$
DECLARE
    v_affected bigint;
BEGIN
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending';

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'Rows processed by UPDATE: %',
        v_affected;
END;
$$;
```

This modifies data; to test without persisting:

```sql
BEGIN;

DO $$
DECLARE
    v_affected bigint;
BEGIN
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RAISE NOTICE 'Affected rows: %', v_affected;
END;
$$;

ROLLBACK;
```

`ROW_COUNT` reports rows processed by the command per SQL semantics; do not infer from it that every column value physically changed or that triggers had no additional effects.

### 27.3. `FOUND`

`FOUND` is a special PL/pgSQL boolean indicating whether supported statements affected or returned at least one row. When you need the **exact row count**, `GET DIAGNOSTICS ... ROW_COUNT` right after the statement is clearer.

### 27.4. `PERFORM` Does Not Cure N+1 Calls

`PERFORM some_function(...)` runs an expression or query and discards the result in PL/pgSQL. Calling it inside a loop does not merge iterations into set execution. If the function has side effects, confirm whether per-row calls are genuinely needed.

## 28. Turning Per-Row Java/JDBC Calls into Set-Based Operations

PL/pgSQL is not the only place RBAR appears. Java code frequently creates application-side loops:

```java
for (Long orderId : orderIds) {
    // One database call per iteration:
    jdbcTemplate.update(
        "UPDATE set_lab.orders " +
        "SET discount = 5 WHERE order_id = ?",
        orderId
    );
}
```

This incurs N network round trips from the app to PostgreSQL in addition to N SQL executions.

### 28.1. When Driven by a Business Predicate, Push the `UPDATE` to PostgreSQL

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';
```

Never pull a list of IDs into Java only to loop back when PostgreSQL can identify the target set via a `WHERE` predicate close to the data.

### 28.2. When the Application Already Holds an Explicit ID Set

A parameterized query:

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE order_id = ANY($1::bigint[]);
```

passes the ID list as a PostgreSQL array. In Java JDBC:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;

Long[] ids = {1L, 3L, 8L};

try (Connection conn = dataSource.getConnection()) {
    Array idArray = conn.createArrayOf("int8", ids);

    try (PreparedStatement ps = conn.prepareStatement(
        "UPDATE set_lab.orders " +
        "SET discount = 5.00 " +
        "WHERE order_id = ANY(?::bigint[])"
    )) {
        ps.setArray(1, idArray);
        ps.executeUpdate();
    } finally {
        idArray.free();
    }
}
```

This assumes a valid `dataSource` and PostgreSQL driver supporting `int8` arrays, with exception/transaction management at the service layer. In real applications, also enforce tenant/authorization predicates to confirm callers may update those IDs.

### 28.3. JDBC Batching Differs from Set-Based SQL

`PreparedStatement.addBatch()` / `executeBatch()` cuts round trips and improves wire efficiency, yet it still sends multiple parameter sets for a DML statement executed repeatedly—**it is not equivalent to a single `UPDATE ... WHERE` or `INSERT ... SELECT`**.

Batching fits well when each row has distinct inputs hard to express relationally, whereas set-based SQL is clearer whenever one predicate covers the set.

### 28.4. Temporary Tables for Huge ID Sets

For millions of IDs, instead of sending an enormous array:

```sql
CREATE TEMP TABLE tmp_order_ids (
    order_id bigint PRIMARY KEY
) ON COMMIT DROP;

-- Application bulk-loads IDs into tmp_order_ids
-- using COPY or an appropriate technique.

UPDATE set_lab.orders AS o
SET discount = 5.00
FROM tmp_order_ids AS x
WHERE o.order_id = x.order_id;
```

This is an **operational skeleton**—running it without the load step leaves the temp table empty—and remember `ON COMMIT DROP` drops the table when the transaction commits, so wrap create, load, and update inside one transaction.

For large staging sets, running `ANALYZE tmp_order_ids` alongside the primary-key index helps the planner.

### 28.5. ORM N+1 `SELECT`s

An app fetching customers and then querying orders per customer creates N+1 overhead. Fixes often involve `JOIN`s, projections, or ORM batch fetching rather than writing PL/pgSQL functions. Aim to trim redundant round trips and optimize **the payload transferred across the network**.

### 28.6. Never Build `IN (...)` Strings from Untrusted IDs

Wrong:

```java
// Never concatenate untrusted input into SQL:
String sql =
    "SELECT * FROM set_lab.orders WHERE order_id IN (" +
    untrustedIds + ")";
```

Always use bind parameters, PostgreSQL arrays, staging tables, or parameterized builders—never sacrifice SQL injection safety to save round trips.

## 29. Set-Based SQL Handles Multi-Column Conditional Logic Cleanly

**Requirement:** set discount to `0` for `pending`, tier-based for `paid`, and `0` for `cancelled`. Set-based:

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount =
    CASE
        WHEN o.status = 'paid' THEN
            round(
                o.amount
                * CASE c.tier
                    WHEN 'gold' THEN 0.10
                    WHEN 'silver' THEN 0.05
                    ELSE 0
                  END,
                2
            )
        ELSE 0
    END
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
RETURNING o.order_id, o.status, o.amount, o.discount;

ROLLBACK;
```

All rows are evaluated in one `UPDATE`. Note that "setting a column to its already identical value" still produces a new MVCC tuple version and fires triggers in PostgreSQL `UPDATE`. Add an inequality predicate when only truly changed rows should be touched.

### 29.1. Avoiding No-Op Updates with `IS DISTINCT FROM`

Update `pending` rows only when discount is not already `5.00`:

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
  AND discount IS DISTINCT FROM 5.00;

ROLLBACK;
```

`IS DISTINCT FROM` handles SQL `NULL` differently from `<>`, always yielding a definite boolean. Since `discount` is `NOT NULL` in the lab schema, `<>` works there too, while the `NULL`-safe pattern shines on nullable columns.

### 29.2. Do Not Assume `SET` Expressions Execute Sequentially

A statement like:

```sql
-- Conceptual example:
-- UPDATE t SET a = a + 1, b = a * 2;
```

must not be read like Java:

```java
a = a + 1;
b = a * 2; // new a
```

In PostgreSQL, `SET` right-hand expressions reference the pre-update source row values rather than mutating left-to-right like Java assignments. If `b` needs the updated `a`, write `(a + 1) * 2` explicitly or compute it in a subquery.

### 29.3. Why Avoid Cramming Hundreds of Exceptions Into One `CASE`?

When rules grow to hundreds of configurable branches, a lookup table with primary-key/range constraints and a `JOIN` is far easier to test and maintain. Set-based SQL favors **clean relational modeling**, not unmaintainable mega-expressions.

## 30. Idempotency and Uniqueness in Set-Based Jobs

Scheduled jobs can re-run after crashes. Always ask whether running twice corrupts data.

### 30.1. Setting a Fixed Value

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';
```

Running twice leaves the same final `discount` value (setting aside side effects like triggers, `updated_at`, or WAL). It is idempotent with respect to **final column state**.

### 30.2. Incremental Accumulation Is Not Automatically Idempotent

```sql
UPDATE set_lab.orders
SET discount = discount + 5.00
WHERE status = 'pending';
```

Running twice adds `10` instead of `5`. Even as a single set-based statement, the operation is not idempotent.

### 30.3. `INSERT ... SELECT` Can Insert Duplicates

Re-running an audit-note job can duplicate events. With an events table enforcing `UNIQUE(order_id, event_type)`, you can write:

```sql
-- Illustrative template on a table with a matching constraint:
-- INSERT INTO order_events(order_id, event_type)
-- SELECT order_id, 'paid'
-- FROM orders WHERE status = 'paid'
-- ON CONFLICT (order_id, event_type) DO NOTHING;
```

Never tack on `ON CONFLICT DO NOTHING` just to silence unexpected uniqueness errors; the conflict target must express a deliberate business invariant.

### 30.4. Idempotency Under Concurrency

Two workers running the same set-based job concurrently can collide on target rows, wait on locks, or trigger duplicate-key errors. Combine unique constraints, transaction isolation, advisory locks or worker coordination, and explicit state machines. Replacing a loop with one SQL query does not solve concurrency by itself.

## 31. Security and Multi-Tenancy in Set-Based SQL

A major hazard when scaling up to set-based operations is **omitting the `tenant_id` predicate**. Instead of corrupting one row, a missing filter updates every tenant at once.

When scoping pending updates to one tenant:

```sql
-- The lab schema uses customer_id as a grouping key,
-- not production tenant_id:
UPDATE set_lab.orders
SET discount = 5.00
WHERE customer_id = 1
  AND status = 'pending';
```

In production multi-tenant designs:

- Enforce tenant scope from verified authentication identity.
- Bind parameters safely rather than concatenating strings.
- Apply Row Level Security where required.
- Restrict privileges on batch-execution roles.
- Inspect `RETURNING`, `ROW_COUNT`, and audit logs.
- For destructive operations, verify expected `SELECT COUNT(*)` under identical filters prior to execution when appropriate.

Never cite "set-based" as a reason to skip authorization or run every job as superuser.

## 32. A Good Query Plan Matters More Than "Short" Syntax

An apparently set-based SQL query lacking indexes or written with a bad join can run slower than a well-designed batched loop.

### 32.1. Correlated Subqueries May or May Not Optimize Away

```sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM set_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total_orders
FROM set_lab.customers AS c;
```

This is a single SQL statement, yet it can produce a **correlated subplan** executed repeatedly. PostgreSQL may decorrelate or index-scan it well, yet you cannot assume every "single SQL statement" automatically beats `JOIN + GROUP BY`.

An equivalent form:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS total_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Use `EXPLAIN` on representative data to pick the faster plan rather than counting lines of SQL.

### 32.2. Watch Out for Cartesian Products

Omitting a join predicate:

```sql
-- Wrong because it creates a Cartesian product without an appropriate ON clause:
-- SELECT * FROM customers CROSS JOIN orders;
```

can explode row counts inside a set-based query, causing nondeterministic `UPDATE` matches or inflated aggregates. Verifying join keys, cardinality, and expected output grain is mandatory.

### 32.3. Do Not Force Everything Into One Monster CTE

Avoid chaining huge CTEs solely because they look "set-based." When a workflow has checkpoints, isolated error paths, retries, and external side effects, multiple smaller set-based statements are often clearer and safer than one giant query.

## 33. Decision Matrix: Choosing the Right Strategy

| Requirement | Try first | When `LOOP` may still be right |
| --- | --- | --- |
| `UPDATE` rows matching predicate | Single `UPDATE ... WHERE` | Each row needs external I/O or independent error capture |
| `UPDATE` from mapping table | `UPDATE ... FROM` on unique key | Stateful chain depending on prior iteration results |
| `INSERT` many rows from SQL data | `INSERT ... SELECT` | Per-row non-transactional side effects cannot batch |
| Group totals by customer/day | `GROUP BY` + `FILTER` | Stateful algorithm hard to express via aggregates |
| Top-N per group | `DISTINCT ON`, `ROW_NUMBER`, `LATERAL` | Each group requires a separate multi-step workflow |
| Running totals | `SUM(...) OVER (...)` | Step-by-step accept/reject decisions change state |
| Load JSON array | `jsonb_to_recordset`, `jsonb_array_elements` | Elements require external validation service per item |
| Generate dates/numbers | `generate_series` | Sequence depends on state outside SQL |
| Process relational IDs | `JOIN`, `ANY`, `UNNEST`, temp table | External API call per ID or per-item retry orchestration |
| Relational delete | `DELETE ... USING`/`EXISTS` | Deletion requires per-unit approval or audit |
| Maintain PK summaries | `INSERT ... SELECT ON CONFLICT` | No clean conflict key or complex multi-table sync |
| Update hundreds of millions of rows | Multiple small set-based batches | Batch-level `LOOP`, never row-level `LOOP` |
| Imports with some malformed rows | Stage, classify, insert valid rows | Per-row exception capture when pre-validation is impossible |
| Per-row trigger logic | Evaluate statement triggers / transition tables | `BEFORE ROW` mutation/validation semantics are essential |

### 33.1. Four Questions Before Writing a `LOOP`

1. **Does the decision for every row depend solely on data already in tables?** If yes, `WHERE`/`CASE`/`JOIN` usually handles it.
2. **Does processing row N+1 depend on row N?** If it is just a running total or previous column, try window functions; true sequential state transitions may justify procedural logic.
3. **Do rows need isolated commits or per-row error handling?** Consider staging and batching first; occasionally per-unit loops still fit.
4. **Are there external side effects or essential trigger/ordering semantics?** Never delete necessary side effects merely to shorten SQL.

## 34. Case Study A: Computing Commissions Across Millions of Orders

**Context:** 5 million `paid` orders; every customer has a tier; recompute discount/commission for the period.

### 34.1. Loop Design

`FOR r IN SELECT orders JOIN customers LOOP UPDATE orders ...` issues an `UPDATE` per order—millions of separate statements, excessive lock/executor cycles.

### 34.2. Set-Based Design

```sql
UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
        CASE c.tier
            WHEN 'gold' THEN 0.10
            WHEN 'silver' THEN 0.05
            ELSE 0
        END,
    2
)
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid';
```

### 34.3. What to Check

- Is `customers.customer_id` unique/PK? Without uniqueness, `UPDATE ... FROM` is nondeterministic.
- Did customer tier change over time, or should historical periods use current tier?
- Are there `BEFORE`/`AFTER UPDATE` triggers?
- What point-in-time snapshot of tiers is needed?
- Should millions of rows be split into date/ID batches?
- Do indexes support the `paid`/`ordered_at` filter and FK join?

### 34.4. Conclusion

Algorithmically, set-based is the direct fit. At multi-million-row scale, split it into multiple set-based batches with proper versioning/transactions instead of one monolithic transaction.

## 35. Case Study B: Refreshing Customer Summary Metrics

**Context:** hourly job refreshes `total_paid` and `paid_orders` for all customers so APIs read fast.

### 35.1. Avoid Per-Customer Loops

Do not issue 100,000 separate `SELECT SUM` queries and 100,000 `UPSERT`s when one `GROUP BY` computes everything.

### 35.2. Single Set-Based `UPSERT`

```sql
INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ),
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    )
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();
```

### 35.3. Limits

- This is a full aggregate rebuild from source tables, **not an incremental per-order update**.
- Customers removed from `customers` may still need cleanup depending on FK/cascade rules.
- If a join duplicates rows due to bad keys, `SUM` inflates even when the query runs fast.
- Two concurrent runs can lock-contend; enforce scheduling or locking coordination.

## 36. Case Study C: Importing 200,000 Records with 2% Malformed Rows

**Context:** users upload a CSV file; ingest valid rows and log errors for malformed ones.

### 36.1. Naive Approach

Read CSV rows one by one in PL/pgSQL with a per-row `BEGIN ... EXCEPTION` `INSERT`. Works functionally, at the cost of 200,000 subtransactions and inserts.

### 36.2. Set-Based Staging Pipeline

```text
COPY -> staging raw text
        |
        v
SQL validation (format/key/range/duplicates)
        |
        +--> invalid rows -> error table
        |
        v
valid rows -> INSERT ... SELECT / ON CONFLICT
        |
        v
batch result counts + audit
```

Validation SQL uses `CASE`, regex checks, joins against reference tables, and uniqueness checks. Unexpected per-row failures can still use targeted error isolation without defaulting to 200,000 subtransactions upfront.

### 36.3. Conclusion

Most bulk business imports benefit hugely from **file-level or large-batch set processing** while preserving detailed row error reporting. Ensure invalid rows never sneak through via silent `NULL`/`0` defaults or skipped key checks.

## 37. Case Study D: Multiple Workers Claiming from a Queue

**Context:** `work_queue` holds 100,000 jobs; ten workers run concurrently, each claiming up to 100 rows.

### 37.1. Never `SELECT` Then `UPDATE` Unprotected

If Worker A and Worker B both `SELECT` `status = 'ready'` IDs before updating, they grab overlapping jobs. That is a race condition, not merely a performance flaw.

### 37.2. Set-Based Claim Pattern

```sql
-- Pseudocode on a work_queue table with PK(id):
WITH claimed AS (
    SELECT id
    FROM work_queue
    WHERE status = 'ready'
    ORDER BY id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE work_queue AS w
SET status = 'processing'
FROM claimed AS c
WHERE w.id = c.id
RETURNING w.id;
```

This claims the batch atomically in a single statement, closing the unlocked `SELECT` → `UPDATE` race window.

### 37.3. Processing Outside the Claim Transaction

Commit immediately after claiming IDs. Workers execute tasks in application code and update final status using leases, timeouts, and retries. If a worker crashes mid-flight, a reclaim sweep must recover stuck jobs—`SKIP LOCKED` does not provide exactly-once delivery, leases, or idempotency on its own.

### 37.4. Conclusion

Under concurrency, set-based SQL pairs cleanly with row locks to claim **multi-row batches**, provided queue semantics, fairness, and skipped items are properly handled.

## 38. Case Study E: Order-Dependent Sequential Updates

**Context:** financial transactions execute chronologically, verifying available balance before each debit, potentially rejecting a later debit while keeping earlier ones.

### 38.1. Should This Become `SUM(delta)`?

No, whenever business rules depend on intermediate balances and per-step accept/reject decisions. Taking `SUM` hides steps that ought to be rejected mid-stream.

### 38.2. Picking the Right Tool

Options include:

- Transactional functions/procedures with row locks and ordered state logic.
- Recursive CTEs only if semantics are proven accurate and safe for workload size.
- Individual ordered SQL transactions coordinated cleanly.
- Dedicated ledger structures if strict auditability/consistency demands it.

### 38.3. Conclusion

**The goal is never to eradicate every loop at all costs.** The goal is preserving correctness while stripping out overhead wherever work is genuinely set-oriented.

## 39. Case Study F: Backfilling Historical Data Without Disruption

**Context:** backfill an estimated column across 30 million records during busy traffic hours.

### 39.1. One Huge `UPDATE` Causes Trouble

Updating 30 million rows in one shot creates a long transaction, heavy WAL/bloat, and severe lock contention with online traffic.

### 39.2. Better Strategy

- Define clean predicates, key ranges, and primary-key bounds.
- Run multiple `UPDATE ... FROM batch` chunks, each statement set-based.
- Commit each chunk separately from an orchestrator or eligible procedure.
- Monitor elapsed time, locks, WAL, and replication lag.
- Skip no-op rows via `WHERE old_value IS DISTINCT FROM new_value`.
- Persist checkpoints, retry safely, and throttle throughput.

### 39.3. Conclusion

Here, **batched set-based SQL** beats both extremes: 30 million row-by-row updates and one giant lock-holding 30-million-row transaction.

## 40. Common Mistakes When Converting `LOOP` to SQL

### Mistake 1. Counting SQL Statements Instead of Verifying Semantics

Shorter SQL can alter concurrency/ordering rules, drop audits, or touch wrong tenants. Speed never excuses wrong business results.

### Mistake 2. `UPDATE ... FROM` with Multiple Source Rows

When one target row matches multiple source rows, PostgreSQL picks one nondeterministically. Always aggregate or deduplicate source keys first.

### Mistake 3. `INSERT ... SELECT` Without Deduplicating Inputs

If the target has a `UNIQUE` constraint and the source yields duplicate keys, `INSERT` fails—and `ON CONFLICT DO UPDATE` raises a cardinality violation. Deduplicate or aggregate upstream.

### Mistake 4. `LEFT JOIN` Filtered in `WHERE` on the Right Table

Placing right-table conditions in `WHERE` converts a `LEFT JOIN` into an effective `INNER JOIN`, dropping unmatched left rows. Put them in `ON` or `FILTER`.

### Mistake 5. Double-Counting `SUM` Across One-to-Many Joins

Multiplying parent rows across child joins inflates parent amounts. Aggregate at the proper grain before joining.

### Mistake 6. Omitting Deterministic Ordering in Top-N

`LIMIT 1` without `ORDER BY` + tie-breaker leaves "latest" undefined; `DISTINCT ON` needs matching deterministic `ORDER BY` too.

### Mistake 7. Thinking Set-Based SQL Never Loops Internally

The executor still iterates over tuples. The advantage is declarative set optimization and fewer context switches, not skipping row work magically.

### Mistake 8. Assuming Every CTE Materializes

Modern PostgreSQL may inline eligible CTEs; data-modifying and recursive CTEs carry specific rules. Verify with `EXPLAIN`, never guess.

### Mistake 9. Expecting `RETURNING` in Business Order

`RETURNING` offers no ordering guarantee. Wrap or sort at the appropriate presentation/query layer when order matters.

### Mistake 10. Ignoring Row-Level Triggers

A 100,000-row set `UPDATE` still runs row triggers 100,000 times. Profile trigger time and consider statement-level triggers with transition tables where suitable.

### Mistake 11. Confusing Statement Count with Transaction Count

A PL/pgSQL loop inside one transaction does not commit every row. Collapsing to one `UPDATE` lowers statement overhead without eliminating transactional lock scope.

### Mistake 12. Running `EXPLAIN ANALYZE UPDATE` Without Expecting Side Effects

`EXPLAIN (ANALYZE)` executes the `UPDATE` for real. Always wrap lab tests in `BEGIN`/`ROLLBACK` and treat production writes carefully.

### Mistake 13. Running One Giant Monolithic Transaction

Updating 100 million rows in a single transaction can overwhelm WAL, locks, rollback, and autovacuum. Batching is often essential.

### Mistake 14. Using `OFFSET` to Paginate a Mutating Set

Updating rows changes `WHERE` eligibility and shifts offsets, skipping or repeating rows. Keep querying `LIMIT N` on the remaining unupdated predicate or keyset/checkpoint ranges.

### Mistake 15. Using `SKIP LOCKED` for Analytical Reports

`SKIP LOCKED` omits locked rows on purpose and produces inconsistent report snapshots.

### Mistake 16. Using `WHERE NOT IN` with Nullable Inputs Without `NULL` Care

`NOT IN` produces `UNKNOWN` whenever the subquery includes `NULL`, returning zero rows unexpectedly. Prefer `NOT EXISTS` for nullable anti-joins alongside explicit constraints.

### Mistake 17. Assuming Batch `UPDATE`s Are Inherently Idempotent

`SET amount = amount + x` run twice adds `2x`. Idempotency requires job IDs, deduplication, unique keys, or absolute target values from stable sources.

### Mistake 18. Building Dynamic `IN (...)` Strings from ID Lists

String-concatenated lists invite SQL injection, quoting bugs, and plan-cache bloat. Use arrays, parameters, or temp tables.

### Mistake 19. Swallowing Per-Row Exceptions Silently

A loop with `EXCEPTION WHEN OTHERS THEN NULL` hides corrupt records. Stage, classify, and audit errors instead of silently ignoring failures.

### Mistake 20. Ignoring Plans and Statistics

A set-based query with missing indexes or stale stats can still crawl. Set-based performance still requires `EXPLAIN`, `ANALYZE`, and smart indexing.

### Mistake 21. Expecting a `VOLATILE` Function to Run Once per Set

A volatile function inside a `SELECT`/`UPDATE` can execute per row, not once globally. Understand function volatility and evaluation rules.

### Mistake 22. Equating `LANGUAGE sql` Functions with PL/pgSQL `RETURN QUERY`

They differ in inlining and result accumulation. For plain queries, SQL functions or views are simpler; use PL/pgSQL when procedural logic is required.

### Mistake 23. Forgetting Authorization and Tenant Filters

An unscoped set `UPDATE` modifies every tenant at once. Always attach verified tenant/authorization filters and monitor affected row counts.

### Mistake 24. Equating JDBC Batching with Set-Based SQL

JDBC batching saves round trips while still running multiple parameterized executions. A single `UPDATE ... WHERE` or `INSERT ... SELECT` is a different pattern; choose based on row variation.

### Mistake 25. Treating Every Loop as Evil

Stateful algorithms, transaction boundaries, and external side effects sometimes require loops. What to avoid is **per-row SQL statement loops when SQL expresses the set rule cleanly**.

## 41. `MERGE`: Another Set-Based Option for Synchronization

Added in PostgreSQL 15, `MERGE` describes conditional actions when source rows **match** or **do not match** target rows under a join predicate, supporting conditional updates, inserts, and deletes depending on version.

### 41.1. `MERGE` Example Into the Summary Table

```sql
BEGIN;

MERGE INTO set_lab.customer_totals AS t
USING (
    SELECT
        customer_id,
        SUM(amount) AS revenue,
        COUNT(*) AS paid_orders
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS s
ON t.customer_id = s.customer_id
WHEN MATCHED THEN
    UPDATE SET
        total_paid = s.revenue,
        paid_orders = s.paid_orders,
        calculated_at = clock_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        total_paid,
        paid_orders
    )
    VALUES (
        s.customer_id,
        s.revenue,
        s.paid_orders
    );

SELECT *
FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

### 41.2. Why `MERGE` Does Not Replace Every `UPSERT`

- `MERGE` and `INSERT ... ON CONFLICT` have **different concurrency and conflict semantics**. Never assume `MERGE` automatically retries when a concurrent transaction inserts a duplicate unique key mid-flight; it can raise a unique violation.
- Matching one target row against multiple source rows can trigger cardinality errors or unexpected behavior; aggregate/deduplicate the source on the join key first.
- `MERGE` does not automatically delete/zero disappeared groups unless explicitly programmed (e.g., via `WHEN NOT MATCHED BY SOURCE` where supported or separate cleanup).
- `MERGE` requires PostgreSQL 15+; check version support before deploying.

### 41.3. When Does `MERGE` Shine?

When sync logic requires multiple matched/unmatched branches in a single statement and concurrency semantics have been evaluated. For atomic single-row or conflict-key insert-or-update under high concurrency, `INSERT ... ON CONFLICT` remains the standard tool.

Never write a loop checking `IF EXISTS THEN UPDATE ELSE INSERT` when a clean `UPSERT` or `MERGE` fits.

## 42. Practice Exercises

Exercises use `set_lab.customers`, `set_lab.orders`, `set_lab.customer_totals`, and `set_lab.audit_notes` from Section 3. Whenever an exercise writes data, wrap it in a **lab transaction** and `ROLLBACK` so the dataset stays untouched for later exercises. Hypothetical tables like `work_queue` are explicitly marked as pseudocode and do not exist in the lab schema.

### Exercise 1. Identifying RBAR

Explain why `FOR r IN SELECT order_id ... LOOP UPDATE ... WHERE order_id = r.order_id` typically carries higher overhead than an equivalent `UPDATE ... WHERE`.

### Exercise 2. Refactoring a Per-Row `UPDATE`

Write one SQL statement setting `discount = 7.50` on all `pending` orders, using `RETURNING` to report affected orders.

### Exercise 3. `CASE` by Customer Tier

Write an `UPDATE` calculating `discount` on `paid` orders: gold 10%, silver 5%, bronze 0%, rounded to 2 decimal places.

### Exercise 4. Concrete Calculation

On the initial lab dataset, what is the total discount across the five `paid` orders under Exercise 3?

### Exercise 5. `INSERT ... SELECT`

Write a single statement inserting the audit note `'Paid'` for every `paid` order without a loop.

### Exercise 6. Why Is the Job Non-Idempotent?

If Exercise 5 runs twice without an appropriate business uniqueness constraint, what happens?

### Exercise 7. Per-Customer Aggregation

Write a `SELECT` computing `total_paid` and `paid_orders` for every customer who has at least one `paid` order.

### Exercise 8. Including Customers Without `paid` Orders

Write a query returning **every customer** and their `paid` revenue, showing `0` for customers with zero `paid` orders.

### Exercise 9. `FILTER`

In one query, count `paid` and `pending` orders per customer.

### Exercise 10. Set-Based `UPSERT`

Write `INSERT ... SELECT ... ON CONFLICT` updating `customer_totals` from `paid` orders per `customer_id`.

### Exercise 11. Disappeared Groups

After all `paid` orders of a customer are cancelled, does an `UPSERT` driven strictly by `orders WHERE status = 'paid' GROUP BY customer_id` reset that customer's total to `0`?

### Exercise 12. Duplicate Conflict Keys in Input

Why can `INSERT ... ON CONFLICT DO UPDATE` fail if the source emits two rows with the same `customer_id`? How do you prevent that upstream?

### Exercise 13. `DELETE ... USING`

Write a `DELETE` removing audit notes belonging to `cancelled` orders by joining with `orders`.

### Exercise 14. Non-Unique `UPDATE ... FROM`

Target row `customer_totals(customer_id = 1)` matches two `paid` orders of customer 1. Why is `SET total_paid = o.amount FROM orders o` wrong when you want the sum?

### Exercise 15. Unique Source Set

Write a `GROUP BY` subquery yielding exactly one source row per `customer_id` for `UPDATE ... FROM`.

### Exercise 16. Running Total

Write a `SELECT` returning each `paid` order alongside its cumulative `amount` per customer ordered by `ordered_at, order_id`.

### Exercise 17. Previous Row

Write a query using `LAG` to retrieve the previous `paid` order amount within each customer.

### Exercise 18. Latest Order per Customer

Write a PostgreSQL `DISTINCT ON` query fetching each customer's latest order, breaking same-day ties deterministically.

### Exercise 19. `ROW_NUMBER`

Write a query returning the **top 2 latest orders per customer** using a window function.

### Exercise 20. `LATERAL`

Write a query returning one row for every customer along with their latest order ID if one exists, keeping customers with zero orders.

### Exercise 21. `generate_series`

Generate all dates from `2026-11-01` through `2026-11-07` in SQL without a `WHILE` loop.

### Exercise 22. Array Membership

Fetch all orders for customer IDs in `ARRAY[1, 2, 4]` without a loop.

### Exercise 23. `UNNEST` vs. Duplicate IDs

How can `unnest(ARRAY[1, 1, 2]) JOIN customers` differ in returned row count from `WHERE customer_id = ANY(ARRAY[1, 1, 2])`?

### Exercise 24. JSON Recordset

Expand `'[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb` into two rows with typed columns `sku text, qty integer`.

### Exercise 25. Data-Modifying CTE

Write one statement updating `discount` on `pending` orders and inserting audit notes solely for those updated rows using `RETURNING`.

### Exercise 26. CTE Materialization

Is it true that every CTE in PostgreSQL always materializes a physical temp table before the parent query executes? Why or why not?

### Exercise 27. `READ COMMITTED` and Snapshots

Why can multiple `UPDATE` statements inside a loop observe concurrent commits differently than one single `UPDATE` statement?

### Exercise 28. Locks and WAL

Does a 10-million-row set-based `UPDATE` avoid row locks, MVCC versions, WAL, or autovacuum impact? When should you batch?

### Exercise 29. Batch Claim

Write a CTE selecting up to 100 `pending` rows with `ORDER BY order_id FOR UPDATE SKIP LOCKED` and updating `discount` in a single statement.

### Exercise 30. `OFFSET` Inside Batches

Why can using `OFFSET 0`, `OFFSET 100`, `OFFSET 200` skip rows when each batch alters the rows matching `WHERE`?

### Exercise 31. `PROCEDURE` and `COMMIT`

Can `COMMIT` be used freely inside a PL/pgSQL function? Why might `CALL` on a procedure inside a Java/Spring-opened transaction block fail to commit internally as expected?

### Exercise 32. Per-Row `EXCEPTION`

An import has 2% malformed rows. Propose a set-based pipeline that ingests valid rows and logs invalid ones instead of opening a per-row exception block.

### Exercise 33. Row vs. Statement Triggers

A set-based `UPDATE` modifies 50,000 rows on a table with a row-level `AFTER UPDATE` trigger. How many times does the trigger run, and can some workloads use a statement-level design instead?

### Exercise 34. `EXPLAIN ANALYZE UPDATE`

What happens when running `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...`? Show how to test it safely in the lab.

### Exercise 35. JDBC Batching

Is `PreparedStatement.executeBatch()` identical to a set-based SQL `UPDATE ... WHERE ...`? When Java already holds a list of IDs, what options should you consider?

### Exercise 36. `RETURN QUERY`

In a multi-row PL/pgSQL function, when is `RETURN QUERY SELECT ...` clearer than a `RETURN NEXT` loop? Does it guarantee row-by-row streaming?

### Exercise 37. Idempotency

Compare running `SET discount = 5` twice against running `SET discount = discount + 5` twice.

### Exercise 38. Stateful Ordered Algorithms

Initial balance `100`, two sequential debits of `60` each allowed only if funds remain. Why isn't checking `SUM(-120)` equivalent to processing each debit in order?

### Exercise 39. `MERGE`

Which PostgreSQL major version introduced `MERGE`? Why shouldn't you blindly assume `MERGE` shares identical concurrency behavior with `INSERT ... ON CONFLICT`?

### Exercise 40. Choosing a Strategy

A 30-million-row table needs an update during peak traffic, with 3 million matching rows. Should you pick a row-by-row loop, one giant `UPDATE`, or multiple set-based batches, and what metrics would you measure?

## 43. Suggested Solutions

### Solution 1. RBAR

The loop iterates through order IDs and dispatches one `UPDATE` per ID. Even with PL/pgSQL plan caching, N SQL statements incur repeated executor dispatch, row lookups, lock acquisition, and index probes. A single `UPDATE ... WHERE` lets PostgreSQL choose one optimal scan/update plan in one statement. On tiny data the gap may be negligible; always benchmark.

### Solution 2. Updating `pending` Orders

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 7.50
WHERE status = 'pending'
RETURNING order_id, amount, discount;

ROLLBACK;
```

On the initial lab dataset, this updates two `pending` orders. `RETURNING` order is unspecified.

### Solution 3. `CASE` and `JOIN`

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
        CASE c.tier
            WHEN 'gold' THEN 0.10
            WHEN 'silver' THEN 0.05
            ELSE 0
        END,
    2
)
FROM set_lab.customers AS c
WHERE o.customer_id = c.customer_id
  AND o.status = 'paid';

ROLLBACK;
```

Since `customers.customer_id` is a `PRIMARY KEY`, each order matches at most one customer row.

### Solution 4. Total Discount

The discounts are 10, 8, 10, 0, and 15, totaling **43.00**. This holds for the initial dataset with no prior committed modifications.

### Solution 5. `INSERT ... SELECT`

```sql
BEGIN;

INSERT INTO set_lab.audit_notes (order_id, note)
SELECT order_id, 'Paid'
FROM set_lab.orders
WHERE status = 'paid'
RETURNING audit_id, order_id, note;

ROLLBACK;
```

Inserts five audit rows on the sample dataset.

### Solution 6. Duplicate `INSERT`s

Each execution inserts five more audit notes, leaving 10 equivalent notes after two runs. Idempotency requires a proper business key / unique constraint and conflict policy, not just collapsing a loop into one SQL statement.

### Solution 7. `GROUP BY`

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Results: customer 1 → 180 / 2; 2 → 200 / 1; 3 → 40 / 1; 4 → 150 / 1.

### Solution 8. `LEFT JOIN` and `FILTER`

```sql
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ) AS total_paid,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Customers without `paid` orders still show `0` / `0`. `COUNT(o.order_id)` does not count the `NULL`-padded row from `LEFT JOIN`.

### Solution 9. Multiple Aggregates in One `SELECT`

```sql
SELECT
    customer_id,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders
FROM set_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

No separate `paid` and `pending` counts inside a per-customer loop are required.

### Solution 10. Set-Based `UPSERT`

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    customer_id,
    SUM(amount),
    COUNT(*)
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();

ROLLBACK;
```

Because the input uses `GROUP BY`, there is at most one row per conflict key. To include customers with zero `paid` orders, see the next solution.

### Solution 11. Disappeared Groups

No. If a customer has zero `paid` orders, `SELECT ... WHERE status = 'paid'` produces no row for that customer, so `UPSERT` leaves any existing total unchanged rather than resetting it to `0`. Fix by deriving the source from all `customers LEFT JOIN orders` using `FILTER` and `COALESCE`, or running a dedicated cleanup/zeroing pass per contract.

### Solution 12. Duplicate Conflict Keys

`INSERT ... ON CONFLICT DO UPDATE` would attempt to modify the same existing target row multiple times within one statement and raise a cardinality error. Use `GROUP BY key`, deterministic `DISTINCT ON`, or staged `UNIQUE` validation to guarantee **one source row per conflict key**.

### Solution 13. `DELETE ... USING`

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
USING set_lab.orders AS o
WHERE a.order_id = o.order_id
  AND o.status = 'cancelled'
RETURNING a.audit_id, a.order_id;

ROLLBACK;
```

With an empty `audit_notes` table in the fresh lab, this deletes 0 rows.

### Solution 14. Non-Unique Source

Customer 1 has two `paid` orders (`100` and `80`). `UPDATE customer_totals SET total_paid = o.amount FROM orders o` does not sum them to `180`; the target row matches two source rows and picks one nondeterministically. Aggregate first with `SUM(amount)` grouped by `customer_id`.

### Solution 15. Unique `GROUP BY`

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id;
```

This yields at most one source row per `customer_id` for `UPDATE ... FROM`; missing groups still require separate handling.

### Solution 16. Window Running Total

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Customer 1 gets running totals 100 and 180. The `order_id` tie-breaker keeps ordering deterministic on identical `ordered_at` dates.

### Solution 17. `LAG`

```sql
SELECT
    customer_id,
    order_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_paid_amount
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Each customer's first order has `NULL` for `previous_paid_amount` since no earlier row exists.

### Solution 18. `DISTINCT ON`

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status
FROM set_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
```

`DISTINCT ON` keeps the first row per customer group per `ORDER BY`. `order_id DESC` resolves ties on the same date.

### Solution 19. Top 2 per Group

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM set_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

No per-customer `LIMIT 2` query loop needed.

### Solution 20. `LEFT JOIN LATERAL`

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at
FROM set_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, ordered_at
    FROM set_lab.orders
    WHERE customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS o ON TRUE
ORDER BY c.customer_id;
```

`LEFT JOIN LATERAL` keeps customers without orders while allowing the correlated subquery to reference the outer `customer_id`. Internally it may still do per-customer lookups in the plan, without needing a PL/pgSQL loop.

### Solution 21. `generate_series`

```sql
SELECT x.day_ts::date AS day
FROM generate_series(
    TIMESTAMP '2026-11-01',
    TIMESTAMP '2026-11-07',
    INTERVAL '1 day'
) AS x(day_ts)
ORDER BY day;
```

Returns seven consecutive days inclusive without incrementing a date variable in `WHILE`.

### Solution 22. `ANY`

```sql
SELECT order_id, customer_id, status, amount
FROM set_lab.orders
WHERE customer_id =
    ANY(ARRAY[1,2,4]::integer[])
ORDER BY customer_id, order_id;
```

When the list comes from Java/JDBC, bind it as a parameter instead of concatenating SQL text.

### Solution 23. `UNNEST` and Duplicates

`UNNEST(ARRAY[1, 1, 2])` emits three rows (ID 1 twice); joining to `customers` returns customer 1 twice. `customer_id = ANY(ARRAY[1, 1, 2])` evaluates membership per customer row (`TRUE`/`FALSE`/`UNKNOWN`) without duplicating customers due to duplicates in the array.

To obtain distinct IDs from `UNNEST`:

```sql
SELECT DISTINCT customer_id
FROM unnest(ARRAY[1,1,2]::integer[])
    AS ids(customer_id);
```

### Solution 24. JSON Recordset

```sql
SELECT sku, qty
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb
) AS x(sku text, qty integer);
```

Produces two rows (`A`/2 and `B`/1); validate fields and types whenever JSON originates from clients.

### Solution 25. CTE `UPDATE ... RETURNING`

```sql
BEGIN;

WITH changed AS (
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending'
    RETURNING order_id, discount
)
INSERT INTO set_lab.audit_notes(order_id, note)
SELECT
    order_id,
    'Discount set to ' || discount::text
FROM changed;

ROLLBACK;
```

`RETURNING` passes the exact rows updated without re-selecting by order ID. Add `IS DISTINCT FROM` to the `UPDATE` if you only want to audit rows whose value actually changed.

### Solution 26. CTEs Do Not Always Materialize

False. Modern PostgreSQL can inline/fold eligible non-recursive, side-effect-free CTEs unless forced otherwise (`MATERIALIZED`/`NOT MATERIALIZED`). Data-modifying and recursive CTEs have distinct semantics. Always inspect `EXPLAIN`.

### Solution 27. `READ COMMITTED`

Under `READ COMMITTED`, separate SQL commands take separate snapshots, allowing concurrent transactions to commit between loop iterations. A single `UPDATE` operates under one-statement snapshot/locking rules. Always verify concurrency requirements alongside `WHERE` predicates.

### Solution 28. Large `UPDATE`s

No. DML still acquires row locks, creates MVCC versions, writes WAL, updates indexes, and affects autovacuum. When row counts are high enough to hurt lock duration, WAL, or replication lag, break work into controlled set-based batches committed separately.

### Solution 29. CTE Batch Claim

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM set_lab.orders
    WHERE status = 'pending'
      AND discount = 0
    ORDER BY order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE set_lab.orders AS o
SET discount = 5.00
FROM batch AS b
WHERE b.order_id = o.order_id
RETURNING o.order_id, o.discount;

ROLLBACK;
```

This single statement updates up to 100 claimed rows instead of running 100 separate `UPDATE`s. Only two `pending` rows exist in the initial dataset. Rows skipped due to `SKIP LOCKED` require a retry sweep.

### Solution 30. `OFFSET` Fails on Mutating Sets

After batch 1 turns `discount = 0` into `5`, those rows drop out of the next batch's `WHERE` set. Applying `OFFSET 100` skips the next 100 remaining rows! Keep querying `LIMIT N` on the remaining condition or advance via a stable keyset/checkpoint.

### Solution 31. Function vs. Procedure `COMMIT`

PL/pgSQL functions cannot arbitrarily execute `COMMIT`. Procedures called via `CALL` or `DO` blocks can manage transactions only in permitted contexts; when nested inside an explicit transaction block opened by Spring/JDBC, internal `COMMIT` is rejected by PostgreSQL. Separate transaction orchestration cleanly or design procedures around your major version's rules.

### Solution 32. Importing Faulty Data

Typical pipeline:

```text
CSV -> staging raw text
    -> SQL validate (regex, NULL, key, range, references)
    -> INSERT invalid rows into error table
    -> INSERT valid rows into target
    -> record batch counts
```

Guard casts with `CASE` checks so a single bad value does not abort the whole `INSERT`. Reserve per-row `EXCEPTION` loops for failures impossible to validate ahead of time as a set.

### Solution 33. Row vs. Statement Triggers

A row-level `AFTER UPDATE` trigger fires **50,000 times** on a 50,000-row `UPDATE`. An `AFTER STATEMENT` trigger can read `old_rows`/`new_rows` transition tables to insert audit records via one `INSERT ... SELECT` where applicable. Never convert `BEFORE ROW` triggers blindly, as their timing and mutation capabilities differ.

### Solution 34. `EXPLAIN ANALYZE UPDATE`

It **actually runs the `UPDATE`**. Safe lab pattern:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

ROLLBACK;
```

Never run on production without explicit write authorization. Plain `EXPLAIN` (without `ANALYZE`) only estimates the plan.

### Solution 35. JDBC Batching vs. Set-Based

They are not identical. JDBC batching sends multiple parameter sets to save network round trips while the database still executes multiple statements. When Java holds a list of IDs:

- Use `WHERE id = ANY($1::bigint[])` for moderate lists.
- Use `UNNEST`/joins when relational transformation is needed.
- Use temp/staging tables + bulk load for huge lists.
- If the filter predicate lives entirely in the database, run `UPDATE ... WHERE` directly.

Always bind parameters safely and benchmark.

### Solution 36. `RETURN QUERY`

When a function simply returns a `SELECT` without per-row procedural steps, `RETURN QUERY SELECT ...` is cleaner than a `RETURN NEXT` loop. It **does not guarantee row-by-row streaming**; PL/pgSQL set-returning functions materialize results, consuming memory/temp disk on large sets.

### Solution 37. Idempotency

Running `SET discount = 5` twice leaves `discount = 5` (excluding triggers/audit metadata). Running `SET discount = discount + 5` twice adds `10` and is non-idempotent. Enforce job IDs, deduplication, or values computed from stable sources across retries.

### Solution 38. Ordered Stateful Algorithms

Under the rule requiring sufficient balance before each debit: the first `-60` succeeds (balance `40`), and the second `-60` is rejected. `SUM(-120)` yields `-20` and loses per-step accept/reject outcomes. Use procedural logic or a set-based formulation proven equivalent to the state transitions.

### Solution 39. `MERGE`

PostgreSQL introduced `MERGE` in **major version 15**. Although it supports matched/unmatched branches, its concurrency rules differ from `INSERT ... ON CONFLICT`—for instance, concurrent duplicate-key inserts do not automatically resolve cleanly like `UPSERT` conflict retries. Verify unique constraints and concurrency tests.

### Solution 40. Strategy for 3 Million Rows

**Multiple set-based batches** is typically best if benchmarks show one huge `UPDATE` causes unacceptable lock waits, WAL spikes, or replication lag; during an offline maintenance window, one `UPDATE` might also work. Per-row loops are unattractive when the update rule is uniform and per-row transactions aren't needed.

Measure: rows per batch, elapsed time, concurrent p95 latency, lock waits, disk I/O, WAL, replication lag, bloat/autovacuum, index maintenance, rollback footprint, and restartability.

## 44. Checklist for Refactoring PL/pgSQL Loops to Set-Based SQL

Before rewriting procedural code into set-based SQL, verify all of the following.

### 44.1. Business Correctness

1. **Goal:** Is it a uniform transformation over a matching set, or a stateful sequential chain?
2. **Scope:** Are `WHERE`, tenant, and authorization predicates tight enough?
3. **Inputs:** Can source data contain `NULL`s or duplicate keys?
4. **Join cardinality:** Does every target row match at most one source row?
5. **Aggregation grain:** Are `SUM`/`COUNT` computed at the exact business granularity?
6. **Missing groups:** Should empty groups become `0`, remain untouched, or be deleted?
7. **Ordering:** Does any "first/latest" requirement need a deterministic tie-breaker?
8. **SQL types:** Are `numeric` rounding, dates/timezones, and `NULL` semantics exact?
9. **Idempotency:** Can a retry run safely without doubling values or inserting duplicates?
10. **Audits:** Do row/statement triggers or external side effects change behavior?

### 44.2. Transactions and Concurrency

11. Does one statement vs. multiple statements alter `READ COMMITTED` snapshot boundaries?
12. Is `SELECT ... FOR UPDATE` needed to lock rows before modifying?
13. Are concurrent writers competing on the same rows?
14. Does the isolation level adequately protect invariants?
15. Could deadlocks occur and require SQLSTATE-based transaction retries?
16. Did the loop previously commit or catch errors row by row, altering atomicity?
17. Do constraints/triggers let one bad row abort the whole statement?
18. When using `SKIP LOCKED`, will skipped rows definitely be retried later?

### 44.3. Performance and Operations

19. Do suitable indexes exist for filters, joins, and sorts?
20. Do planner statistics reflect real data distributions?
21. Did you inspect `EXPLAIN (ANALYZE, BUFFERS)` on a representative dataset?
22. Did you check actual rows, loops, buffer reads, and trigger overhead?
23. Should large updates be chunked into batches to cap transaction duration and WAL?
24. Have reader/writer latency, replication lag, and bloat been measured?
25. Did you benchmark across multiple runs instead of trusting an 8-row sample?
26. Is there a rollback, checkpoint, and retry plan if the job stops mid-way?

### 44.4. Architecture and Maintainability

27. Can `INSERT ... SELECT`, `UPDATE ... FROM`, or `DELETE ... USING` replace the loop?
28. Can `GROUP BY`, `FILTER`, window functions, `DISTINCT ON`, or `LATERAL` simplify logic?
29. For array/JSON inputs, do `UNNEST` or `jsonb_to_recordset` fit?
30. For multi-step SQL, do CTEs and `RETURNING` clarify intermediate sets?
31. If batching, does iteration happen at the batch level rather than per row?
32. Is a plain SQL function or view better than PL/pgSQL just to wrap a `SELECT`?
33. If using `MERGE`, have PostgreSQL major version and concurrency rules been verified?
34. Are parameters bound safely from JDBC/ORMs rather than concatenated into SQL text?
35. Is the rewritten code easier to read and test than the original?
36. Whenever keeping a `LOOP`, is the business or transactional reason documented explicitly?

## 45. Summary

**Set-based processing is the right default mindset for relational data.** Whenever the rule is "transform every row matching a predicate uniformly," express it directly in SQL instead of issuing one SQL statement per row in PL/pgSQL.

Core patterns:

- **`UPDATE ... WHERE`** replaces per-key `UPDATE` loops.
- **`UPDATE ... FROM`** pulls values from mapping tables—always guarantee source keys do not multiply target rows.
- **`INSERT ... SELECT`** populates rows from queries—design explicit idempotency when jobs retry.
- **`DELETE ... USING`** or **`DELETE ... WHERE EXISTS`** replaces relational delete loops.
- **`GROUP BY` and `FILTER`** replace manual grouping and accumulation loops.
- **Window functions** (`SUM OVER`, `LAG`, `ROW_NUMBER`) replace ordered accumulation and previous-row loops.
- **`DISTINCT ON` or `LATERAL`** solve latest-row / top-N per group cleanly.
- **`generate_series`, `UNNEST`, and `jsonb_to_recordset`** turn calendars, arrays, and JSON into SQL-queryable relations.
- **CTEs and `RETURNING`** chain intermediate modifications without looping back to re-select rows.
- **`ON CONFLICT` and `MERGE`** handle key-based synchronization when uniqueness and concurrency are accounted for.

Equally critical boundaries:

- Set-based SQL **is not exempt** from MVCC, row locks, WAL, triggers, or constraints.
- Huge `UPDATE`s often need **batched set-based SQL** instead of one giant transaction.
- `UPDATE ... FROM` must never join a one-to-many source expecting a predictable pick.
- One SQL statement **is not automatically fast**; plans, indexes, stats, and join cardinality still rule.
- Collapsing a per-row exception loop into one statement changes **error-handling atomicity**.
- Order-dependent stateful algorithms sometimes **genuinely require loops/procedures** or dedicated transactional flows.
- `EXPLAIN (ANALYZE)` on DML **executes the DML**, so protect lab tests with `ROLLBACK`.
- Java/JDBC faces the same N+1 traps; JDBC batching and set-based SQL solve different layers.

A rule worth remembering:

> **Let PostgreSQL operate on whole row sets whenever the logic is relational. Use PL/pgSQL for orchestration when procedural control is truly needed—and if you must iterate, loop over batches rather than individual rows.**

The goal is never fewer lines of code or outlawing the `LOOP` keyword; it is **semantically accurate, readable, optimizable designs that hold up under real production load**.

## 46. References

Official PostgreSQL documentation (match your exact major version):

- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): `LOOP`, `FOR`, `FOREACH`, `RETURN QUERY`, exceptions, and control flow.
- [PL/pgSQL Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html): SQL inside PL/pgSQL, `SELECT INTO`, `PERFORM`, `EXECUTE`, and `GET DIAGNOSTICS`.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `INSERT ... SELECT`, `ON CONFLICT`, `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM`, join cardinality, and `RETURNING`.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html): `DELETE ... USING`, `RETURNING`.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): syntax and conditional branches by major version.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `LATERAL`, `GROUP BY`, `WINDOW`.
- [Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): window definitions, `PARTITION BY`, and ordering.
- [WITH Queries (Common Table Expressions)](https://www.postgresql.org/docs/current/queries-with.html): CTEs, recursion, materialization, and data-modifying statements.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks and transaction coordination.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots, `READ COMMITTED`, and concurrency semantics.
- [PL/pgSQL Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): transaction control restrictions in procedures and `DO`.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): executing `EXPLAIN ANALYZE` and reading query plans.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): row/statement triggers and transition relations.
