# Intentional Denormalization and Consistency Trade-offs in PostgreSQL

In relational database design, **normalization** gives every business fact a single clear home, reduces redundant data, and limits update anomalies. However, real-world systems must also support fast reads, complex reporting, and displaying data "captured" at a historical point in time. When measurements show that always recomputing or joining many tables incurs significant cost, a team may consider **intentional denormalization**.

Denormalization is not simply "skipping normalization to go fast". It is a deliberate decision to **store an additional representation of information already derivable from another source**, or arrange data in a shape tailored to a specific query pattern. Every extra copy of information brings key questions: **who updates it, when is it updated, and if two copies disagree, which one is right?**

For example, an order's total amount can be computed from `order_items` rows. Storing `orders.total_amount` speeds up reading order lists, yet if a line item changes without updating the total, the database can return wrong numbers. Conversely, storing `customer_name_at_order` on an order can be completely correct because the business needs **the customer's name at the time of ordering**, even after their current name in `customers` changes.

This lesson explains how to distinguish **risky redundancy** from **historical data with independent meaning**, common denormalization patterns in PostgreSQL, how to maintain consistency via transactions/triggers or embrace eventual consistency, and safe measurement and operational practices.

## 1. Reviewing Normalization: Where Should Each Fact Live?

In relational design, one goal of normalization is removing unnecessary dependencies between attributes and records. For example:

```text
customers
  customer_id  -> full_name, email

orders
  order_id     -> customer_id, created_at, status

order_items
  (order_id, line_no) -> product_code, quantity, unit_price
```

Under these relations, a customer's current name should be read via `customers`; an order's total can be computed from `order_items`. Information does not need to be copied into multiple values that must always change in lockstep.

### 1.1. Anomalies Normalization Aims to Reduce

Suppose an `orders_flat` table stores multiple line items and repeats customer details:

| order_id | line_no | customer_id | customer_name | product | quantity |
| ---: | ---: | ---: | --- | --- | ---: |
| 101 | 1 | 1 | Lan | BOOK-SQL | 2 |
| 101 | 2 | 1 | Lan | NOTE-A5 | 1 |
| 102 | 1 | 1 | Lan | PEN-BLUE | 3 |

If Lan changes her name:

- **Update anomaly:** multiple rows must be updated; missing one row leaves the same `customer_id` with two different names.
- **Insert anomaly:** if customer info is required on order-line rows, it becomes awkward to create customers who have not ordered yet.
- **Delete anomaly:** deleting the last order can wipe out customer information if no separate customers table exists.

Normalization separates entities and data dependencies. Normal forms such as 1NF, 2NF, 3NF, or BCNF help spot structures prone to duplication, though they do not replace defining proper **keys, constraints, and business rules**.

### 1.2. Normalization Does Not Mean Forbidding JOINs

A query reading from multiple tables is normal in a relational database:

```sql
SELECT
    o.order_id,
    c.full_name,
    o.created_at,
    o.status
FROM commerce_lab.orders AS o
JOIN commerce_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id = 1
ORDER BY o.created_at DESC;
```

PostgreSQL has a query optimizer, indexes, statistics, and multiple JOIN algorithms. **The mere presence of a JOIN does not prove a schema needs denormalization**. Measure actual cost first.

## 2. What Is Intentional Denormalization?

**Denormalization** places information derivable from other data into a location serving a defined purpose. Redundancy is accepted because it delivers a measured benefit, such as fewer JOINs, avoiding repeated aggregations, or accelerating dashboard queries.

| Technique | Value Source | Expected Benefit | Main Risk |
| --- | --- | --- | --- |
| Storing `orders.total_amount` | Sum of `order_items` lines | Reading order lists without summing line items | Total can drift if line items change without updating the total. |
| Storing `orders.customer_name_at_order` | Customer name at order confirmation | Preserves history, displays point-in-time invoice accurately | Easy to confuse with current name if semantics aren't explicit. |
| `daily_sales_summary` table | Orders aggregated by day | Dashboards read few rows quickly | May update late, double-count, or drop events. |
| Materialized view | `SELECT` query result at refresh time | Speeds up repeated reporting queries | Stale results between refreshes. |
| JSONB holding config/detail snapshots | Data from relations or external systems | Convenient single-document response | Schema drift, harder validation and querying if overused. |

A solid design does not just say "add a column for speed", it documents:

1. What is the **source of truth**?
2. Must the extra stored value **always match the source**, or does it intentionally capture a point in time?
3. What **staleness/lag** is acceptable?
4. What mechanism maintains or refreshes the data?
5. Is there a way to **detect and repair drift**?
6. Have measured gains been shown to outweigh write and operational costs?

### 2.1. Three Very Different Kinds of Data

| Type | Example | Semantics |
| --- | --- | --- |
| **Derived value kept in sync** | `orders.total_amount = SUM(order_items)` | If line items change, the total must change accordingly; any mismatch is a data bug. |
| **Intentional historical snapshot** | `customer_name_at_order` | Once the order is finalized, this name may differ from the current name; differing is not an error. |
| **Read replica / lag-tolerant projection** | Revenue summary table updated every 5 minutes | Lag is acceptable within an agreed window, yet catch-up/reconciliation must exist. |

Without classifying upfront, operations teams may accidentally "fix" historical names to match current names, or conversely treat a broken order total as a valid snapshot.

## 3. A Normalized Schema as the Starting Point

Use the `commerce_lab` schema in a test PostgreSQL environment. This example separates customers, orders, and order items to clearly define keys and relationships.

```sql
CREATE SCHEMA IF NOT EXISTS commerce_lab;

CREATE TABLE commerce_lab.customers (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE commerce_lab.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES commerce_lab.customers(customer_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'cancelled'))
);

CREATE TABLE commerce_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES commerce_lab.orders(order_id),
    line_no integer NOT NULL CHECK (line_no > 0),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Constraints protecting the foundational truth:

- `customers.customer_id` is the customer identifier.
- `orders.customer_id` references a valid customer.
- Each line item is identified by `(order_id, line_no)`.
- `quantity > 0` and `unit_price >= 0` prevent invalid values at the database level.
- `numeric` is more suitable than `float` for monetary calculations requiring exact decimal precision under business rules.

Sample data:

```sql
INSERT INTO commerce_lab.customers (customer_id, full_name, email)
VALUES
    (1, 'Lan', 'lan@example.test'),
    (2, 'Minh', 'minh@example.test');

INSERT INTO commerce_lab.orders
    (order_id, customer_id, created_at, status)
VALUES
    (101, 1, '2026-10-05 09:00:00+07', 'draft'),
    (102, 2, '2026-10-06 10:30:00+07', 'confirmed');

INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 1, 'BOOK-SQL', 2, 150000.00),
    (101, 2, 'NOTE-A5',  1,  30000.00),
    (102, 1, 'PEN-BLUE', 3,  12000.00);
```

Manual IDs here make exercise outputs easy to read. When using identity columns in real applications, remember to resynchronize sequence state if mixing manual ID inserts with subsequent auto-generated IDs.

### 3.1. Computing Totals Without Storing Extra Columns

```sql
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity::numeric * i.unit_price), 0)
        AS calculated_total
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Example output:

| order_id | calculated_total |
| ---: | ---: |
| 101 | 330000.00 |
| 102 | 36000.00 |

`LEFT JOIN` paired with `COALESCE` ensures orders without line items still return `0`. This computes totals directly from the **source of truth**, evaluated over the records visible in the query's MVCC snapshot.

### 3.2. When Is Dynamic Aggregation Enough?

If a screen displays only a few orders, each order has few lines, and `PRIMARY KEY (order_id, line_no)` supports looking up lines by `order_id`, summing dynamically can be very cheap. Storing `total_amount` before observing a bottleneck adds complexity without meaningful gain.

Conversely, a listing screen loading 500 orders per request, served thousands of times per second, and filtering/sorting by total amount can incur noticeable repeated aggregation cost. **Workload and query plans**, not intuition about table counts, should drive the decision.

## 4. Optimizing Normalized Design Before Denormalizing

Before adding redundant columns, evaluate lower-risk options.

### 4.1. Indexing for the Query Pattern

For a screen fetching orders by customer and timestamp:

```sql
CREATE INDEX idx_orders_customer_created
ON commerce_lab.orders (customer_id, created_at DESC)
INCLUDE (status);
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.created_at, o.status
FROM commerce_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.created_at DESC
LIMIT 50;
```

`INCLUDE` lets non-key columns be stored inside a B-tree index. PostgreSQL **can** use an index-only scan when the visibility map and plan allow it; never assume a query skips heap fetches solely because `INCLUDE` is present.

If a query is slow due to a missing index, denormalizing customer names or order totals may not even address the real bottleneck.

### 4.2. Rewriting Queries Instead of Duplicating Data

For example, you don't always need to join all line items before narrowing down the orders:

```sql
SELECT
    o.order_id,
    o.created_at,
    (
        SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
        FROM commerce_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ) AS total_amount
FROM commerce_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.created_at DESC
LIMIT 20;
```

This correlated subquery pattern can work well when fetching only a few orders with an index on `order_id`. However, do **not assume** it always beats `GROUP BY`: PostgreSQL chooses plans based on order counts, row distribution, and statistics. Benchmark both approaches on representative data.

### 4.3. A VIEW Does Not Physically Denormalize

A standard view is a saved query definition:

```sql
CREATE VIEW commerce_lab.v_order_totals AS
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS total_amount
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id;
```

Then:

```sql
SELECT *
FROM commerce_lab.v_order_totals
WHERE order_id = 101;
```

Views help reuse logic and expose a consistent read interface, yet **do not automatically persist results**. PostgreSQL still plans queries over the underlying view definition. Persisting precomputed results requires a materialized view or a summary table maintained by the application or triggers.

## 5. Storing Order Totals: A Clear Denormalization Case

Suppose measurements show that summing line items across large order lists is too expensive. We can store `orders.total_amount`:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN total_amount numeric(18, 2) NOT NULL DEFAULT 0
    CHECK (total_amount >= 0);
```

From this point on, the same fact exists in two places:

```text
order_items:
  (quantity, unit_price) per line item
            |
            | SUM(quantity * unit_price)
            v
orders.total_amount
```

The **data invariant** that must hold is:

```text
For every order_id:

orders.total_amount
    = SUM(order_items.quantity * order_items.unit_price)

Convention: an order with no line items has total_amount = 0
```

In this example, the total excludes tax, shipping fees, discounts, and refunds. If the business includes those components, the total formula must be defined explicitly; never treat `SUM(quantity * unit_price)` as a universal revenue formula.

### 5.1. Bugs When Updating Two Places Separately

Example bug:

```sql
-- Increase quantity on one line item.
UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101 AND line_no = 1;

-- Forgot to update commerce_lab.orders.total_amount.
```

If the application reads `orders.total_amount`, it may still show `330000.00` while the true line-item sum has become `480000.00`. **Even the best index cannot fix a wrongly stored value.**

### 5.2. Three Strategies for Maintaining Derived Values

| Strategy | How It Works | Expected Consistency |
| --- | --- | --- |
| **Application/service transaction** | Every line-item change and total update runs inside the same transaction | Strong if every writer obeys the protocol and handles concurrency properly. |
| **Database trigger** | PostgreSQL updates the total whenever `order_items` rows change | Synchronous within the same transaction, provided triggers cover all write paths. |
| **Asynchronous processing** | Workers/streams consume events and update totals/projections | Introduces lag; requires idempotency, retries, and reconciliation. |

Choose based on **actual write paths**, ownership of the source of truth, and consistency requirements. With a single PostgreSQL database and totals affecting financial transactions, **same-transaction** updates are usually easier to reason about than lag-prone projections.

## 6. Enforcing Strong Consistency with PostgreSQL Transactions

Transactions allow updating multiple tables under a single commit boundary:

```sql
BEGIN;

INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 3, 'PEN-BLUE', 2, 12000.00);

UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 101;

COMMIT;
```

If an error occurs before `COMMIT` and the transaction rolls back, both changes are reverted. Once committed, readers outside the transaction never see a "new line item exists while total is stale" state because both operations share one transaction—**assuming all related write paths follow the same process**.

However, this example is a **simple transaction illustration**, not yet safe against all concurrent writes. Two transactions concurrently adding line items and recomputing the total under different snapshots can still produce mismatched results without proper locking/synchronization.

### 6.1. Locking the Parent Row Before Modifying Line Items

One consistent write pattern requires every writer modifying items of an order to **lock the `orders` row first**, then edit line items and recompute the total.

```sql
BEGIN;

-- All writers for the same order_id must follow this convention.
SELECT order_id
FROM commerce_lab.orders
WHERE order_id = 101
FOR UPDATE;

UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101
  AND line_no = 1;

UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 101;

COMMIT;
```

If all writers lock `orders(order_id)` before modifying `order_items`, they serialize per order at lock acquisition. Total recalculation cannot race against another compliant writer at the same moment.

**Limitation:** if another code path inserts/edits line items without following the locking convention, consistency can break again. A note in a README is not a database-enforced constraint. Protecting all write paths requires privilege management or database-level mechanisms.

### 6.2. Do Not Treat Transactions as Magic

Merely wrapping two `UPDATE`s in `BEGIN ... COMMIT` is **not enough** to eliminate all race conditions:

- Reading first and computing from stale values can cause *lost updates* without locks or atomic update expressions.
- Transactions acquiring locks in different orders can deadlock.
- Under `SERIALIZABLE` isolation, PostgreSQL can abort transactions with a serialization error; the application must retry the **entire transaction** safely.
- Database transaction boundaries do not automatically wrap changes in external systems outside PostgreSQL.

For denormalized data, design **concurrency rules** just as explicitly as business constraints.

## 7. Maintaining Totals with Same-Transaction Triggers

A PostgreSQL trigger can automatically adjust `orders.total_amount` whenever `order_items` changes. The example below uses **delta updates**, adding only the net change instead of rescanning and resumming all line items.

Because `orders` just received a `total_amount` column defaulting to 0, before enabling the trigger for existing rows, **backfill** totals from stored line items (in the lab with no concurrent writers):

```sql
UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
);
```

In a live production system with concurrent writes, never run a backfill over an arbitrary snapshot and assume it remains accurate: plan write coordination, locking, two-phase migrations, or appropriate watermark/reconciliation mechanisms. This example assumes the lab is synchronized before creating the trigger.

### 7.1. Delta Trigger Function

```sql
CREATE OR REPLACE FUNCTION commerce_lab.adjust_order_total()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id bigint;
    v_old_amount numeric(18, 2) := 0;
    v_new_amount numeric(18, 2) := 0;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;
        v_new_amount := NEW.quantity * NEW.unit_price;

    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;
        v_old_amount := OLD.quantity * OLD.unit_price;

    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.order_id IS DISTINCT FROM NEW.order_id THEN
            RAISE EXCEPTION
                'Changing order_id is not supported by adjust_order_total';
        END IF;

        v_order_id := NEW.order_id;
        v_old_amount := OLD.quantity * OLD.unit_price;
        v_new_amount := NEW.quantity * NEW.unit_price;
    END IF;

    UPDATE commerce_lab.orders
    SET total_amount =
        total_amount + v_new_amount - v_old_amount
    WHERE order_id = v_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % does not exist', v_order_id;
    END IF;

    RETURN NULL; -- Return value of an AFTER row trigger is ignored.
END;
$$;

CREATE TRIGGER trg_adjust_order_total
AFTER INSERT OR UPDATE OR DELETE
ON commerce_lab.order_items
FOR EACH ROW
EXECUTE FUNCTION commerce_lab.adjust_order_total();
```

Inside the trigger:

- `INSERT` applies a positive delta equal to the new line amount.
- `DELETE` applies a negative delta equal to the deleted line amount.
- `UPDATE` subtracts old amount from new amount.
- Moving a line item across orders by changing `order_id` in one `UPDATE` is rejected because it would require synchronizing **two orders** and more complex lock ordering. Here the trigger raises an error so the transaction rolls back.
- `UPDATE orders SET total_amount = total_amount + delta` updates the `orders` row under PostgreSQL's row-locking and transaction rules, avoiding client-computed overwrites.

**Key point:** an `AFTER ROW` trigger executes inside the **same transaction** as the triggering statement. If adjusting the total fails, the statement that fired the trigger cannot commit normally either.

### 7.2. Testing INSERT, UPDATE, and DELETE

Once the trigger is installed, each operation adjusts the total automatically:

```sql
-- Add a line 2 * 12,000 = 24,000 to order 101.
INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 3, 'PEN-BLUE', 2, 12000.00);

-- Increase line 1 quantity from 2 to 3: total increases by 150,000.
UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101 AND line_no = 1;

-- Delete line 3: total decreases by 24,000.
DELETE FROM commerce_lab.order_items
WHERE order_id = 101 AND line_no = 3;
```

If following the lab sequentially, note that section 6 already demonstrated an `INSERT` with `line_no = 3`. **Do not run both snippets back-to-back as a single script when line 3 already exists**, or the primary key will reject the duplicate insert. Reset the lab, skip the duplicate insert, or pick an unused line number.

Verify consistency:

```sql
SELECT
    o.order_id,
    o.total_amount AS stored_total,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS calculated_total
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
ORDER BY o.order_id;
```

### 7.3. Risks and Limitations of Triggers

Triggers centralize logic in the database, yet do not mean "drift is impossible":

1. **All operation types must be covered.** Row-level `INSERT/UPDATE/DELETE` triggers do not fire per row on `TRUNCATE`; restrict or govern alternative operational paths that mutate source data.
2. **Higher write cost.** Every line-item change also mutates the `orders` row. An order with many concurrent writers can become a lock contention hotspot.
3. **Deadlocks remain possible.** Multiple transactions modifying multiple orders in different orders can acquire locks in opposite sequences. Enforce consistent lock ordering and safe deadlock retries.
4. **Special write paths need attention.** Bulk imports, partition swaps, triggers disabled by privileged roles, or external write paths may bypass expectations.
5. **Parent deletions need careful design.** This example uses the default foreign key, not `ON DELETE CASCADE`. If cascading deletes are used, analyze trigger ordering and parent row updates during deletion.
6. **Avoid split or duplicated logic.** Never have both the application add to `total_amount` and a trigger add to it a second time.

Triggers fit best when all related changes happen inside the same PostgreSQL database and you want the database to enforce derived updates. In systems spanning multiple data stores, external event processing, or intentional lag tolerances, another pattern may be easier to operate.

## 8. Understanding Triggers Under Concurrency

Suppose transactions A and B concurrently add two different line items to order 101.

```text
Transaction A                           Transaction B
--------------                          --------------
INSERT item A                            INSERT item B
  |                                        |
  v                                        v
AFTER trigger                            AFTER trigger
UPDATE orders.total_amount              UPDATE orders.total_amount
  |                                        |
  +---- acquires lock on orders(101) ------+
  |                                        |
COMMIT                         waits / resumes once lock is released
                                           |
                                         COMMIT
```

When both triggers execute `total_amount = total_amount + delta`, PostgreSQL serializes updates on the same row via row locks and transaction ordering, preventing the classic "both read 330,000 and overwrite each other" bug seen with unlocked client-side calculations.

Still:

- If A holds the lock for long, B must wait, increasing write latency.
- If one transaction updates orders `101 → 102` while another updates `102 → 101`, a deadlock can occur.
- If trigger logic performs extra queries or complex side effects, evaluate isolation levels, lock ordering, and retry behavior.

**Not every aggregate calculation is automatically safe just because it runs inside a trigger.** A trigger doing "SELECT SUM(...) then overwrite total" can still race when its query sees a snapshot before another concurrent transaction commits. The delta pattern illustrates a simpler approach, yet still requires benchmarking under realistic concurrency.

### 8.1. SERIALIZABLE Does Not Eliminate Error Handling

PostgreSQL supports `SERIALIZABLE` isolation, which prevents outcomes inconsistent with a serial execution order by detecting conflicts and aborting transactions. Upon hitting SQLSTATE `40001` (`serialization_failure`), applications generally must retry the **entire transaction logic** under a bounded retry policy.

Therefore, do not turn on `SERIALIZABLE` and assume all derived updates will succeed effortlessly with zero errors or overhead. Pick isolation levels based on the invariant being protected, retry capability, and measured performance.

## 9. Historical Snapshots: Differing from the Source Isn't Always Wrong

Suppose customer Lan changes her name after placing an order:

```sql
UPDATE commerce_lab.customers
SET full_name = 'Lan Nguyen'
WHERE customer_id = 1;
```

In the customer directory or account page, the current name is `'Lan Nguyen'`. Yet on an invoice issued before the rename, the system may need to display **the name at the time of purchase**, not the new name.

In that case, storing a snapshot column is completely valid:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN customer_name_at_order text;
```

Upon order confirmation, the application can capture the value inside the same transaction:

```sql
BEGIN;

UPDATE commerce_lab.orders AS o
SET
    customer_name_at_order = c.full_name,
    status = 'confirmed'
FROM commerce_lab.customers AS c
WHERE o.customer_id = c.customer_id
  AND o.order_id = 101
  AND o.status = 'draft';

COMMIT;
```

After confirmation, `customer_name_at_order` carries independent historical meaning. If the customer's current name changes again later, **you should not automatically sync the snapshot to match `customers.full_name`**, unless business and regulatory rules explicitly call for an amendment.

### 9.1. Name Columns to Reflect Update Policy

Compare:

```text
orders.customer_name                -- Ambiguous: current or at order time?
orders.customer_name_at_order       -- Clear: snapshot at order placement
orders.current_customer_name_cache  -- Clear: read cache requiring sync
```

Clear naming and documentation help readers distinguish an **intentional snapshot** from a **cached duplicate**. Two columns may hold different values while only one case represents a bug.

### 9.2. Valid Snapshot Examples

- Unit price, tax rate, and terms applied when the order was placed.
- Shipping address confirmed by the customer for that specific order.
- Company name printed on an invoice at issuance time.
- Policy/configuration version active during the transaction.

A product currently costing 200,000 does not mean last month's finalized order lines should update to 200,000. In many systems, `order_items.unit_price` is inherently a **transaction-time price**, not a synchronized copy of `products.current_price`.

**The right question is not "is data repeated?" but "do these two columns represent the same fact at the same point in time, or two facts from different points in time?"**

## 10. Materialized Views: Persisting Query Results for Reporting

PostgreSQL supports `MATERIALIZED VIEW`: persisting the output of a query as materialized data. Queries reading the materialized view do not re-execute the full underlying query on every read.

Example daily order count and gross amount report in Vietnam time:

```sql
CREATE MATERIALIZED VIEW commerce_lab.mv_daily_sales AS
SELECT
    (o.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sale_date,
    count(*) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS gross_amount
FROM commerce_lab.orders AS o
WHERE o.status = 'confirmed'
GROUP BY (o.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
WITH DATA;
```

Then:

```sql
SELECT *
FROM commerce_lab.mv_daily_sales
ORDER BY sale_date DESC
LIMIT 30;
```

Here:

- `gross_amount` relies on `orders.total_amount` maintained per system policy; if that column drifts, the materialized view inherits the error.
- Filtering on `'confirmed'` only is an **example convention**, not a universal accounting revenue definition.
- Converting `timestamptz` to date uses an explicit `'Asia/Ho_Chi_Minh'` time zone so report dates do not shift depending on session `TimeZone`.

### 10.1. Materialized Views Do Not Auto-Update

When base tables change, a materialized view **does not refresh automatically**:

```sql
REFRESH MATERIALIZED VIEW commerce_lab.mv_daily_sales;
```

This statement recomputes the stored data from the query as of the refresh run. Until the next refresh, readers can see older aggregates.

That creates a **consistency trade-off**:

```text
orders updated         10:00
user reads MV          10:01  -> may see stale data
REFRESH MV             10:05
user reads MV          10:06  -> sees results from the refresh
```

Actual freshness depends on the refresh schedule and how long the refresh takes. Never label this a "real-time dashboard" without an update mechanism meeting real-time SLAs.

### 10.2. REFRESH CONCURRENTLY

To avoid blocking concurrent reads on a materialized view during refresh, PostgreSQL supports:

```sql
CREATE UNIQUE INDEX ux_mv_daily_sales_date
ON commerce_lab.mv_daily_sales (sale_date);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    commerce_lab.mv_daily_sales;
```

`CONCURRENTLY` has prerequisites. A central requirement is that the materialized view is already populated and has **at least one suitable UNIQUE index on column names only, covering all rows** (not an expression index or partial index). Here `sale_date` serves as the unique key because each date has one row.

`CONCURRENTLY` reduces read blocking on `SELECT`s compared to a standard refresh, yet **is not free**: it requires extra I/O/CPU work and does not allow multiple concurrent refreshes on the same view. Measure refresh duration and load on the source tables.

### 10.3. When to Use Materialized Views?

Good fit when:

- Aggregation queries are expensive and read frequently.
- Point-in-refresh staleness is acceptable.
- Row-by-row instantaneous updates after every transaction are not required.
- Refresh scheduling, monitoring, and failure handling are in place.

Poor fit if every payment transaction must immediately read exact up-to-the-second totals across all entities, or if full-refresh cost outweighs the read benefit.

## 11. Summary Tables Updated Incrementally by Events

Instead of refreshing an entire materialized view, you can maintain an **incremental summary table**.

Example daily sales table:

```sql
CREATE TABLE commerce_lab.daily_sales_summary (
    sale_date date PRIMARY KEY,
    confirmed_order_count bigint NOT NULL DEFAULT 0
        CHECK (confirmed_order_count >= 0),
    gross_amount numeric(18, 2) NOT NULL DEFAULT 0
);
```

When an order-confirmed event succeeds, the corresponding worker or transaction can upsert:

```sql
INSERT INTO commerce_lab.daily_sales_summary
    (sale_date, confirmed_order_count, gross_amount)
VALUES
    (DATE '2026-10-05', 1, 330000.00)
ON CONFLICT (sale_date)
DO UPDATE SET
    confirmed_order_count =
        commerce_lab.daily_sales_summary.confirmed_order_count
        + EXCLUDED.confirmed_order_count,
    gross_amount =
        commerce_lab.daily_sales_summary.gross_amount
        + EXCLUDED.gross_amount;
```

`ON CONFLICT` handles contention on `sale_date` and applies additive updates on the appropriately locked row. However, **it does not automatically know whether two incoming messages represent the same business event**.

If an "order 101 confirmed" event is processed twice, the exact same statement will add it twice. The database remains transactionally consistent while **business metrics become wrong due to duplicate events**.

### 11.1. Updating Summaries with an Idempotency Key

One approach is recording processed events inside the exact same PostgreSQL transaction:

```sql
CREATE TABLE commerce_lab.processed_projection_events (
    projection_name text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (projection_name, event_id)
);
```

Example event handler using a CTE:

```sql
BEGIN;

WITH accepted AS (
    INSERT INTO commerce_lab.processed_projection_events
        (projection_name, event_id)
    VALUES
        ('daily_sales', '1fa80ca8-e121-43cf-8afe-27124d141f42'::uuid)
    ON CONFLICT (projection_name, event_id) DO NOTHING
    RETURNING event_id
)
INSERT INTO commerce_lab.daily_sales_summary
    (sale_date, confirmed_order_count, gross_amount)
SELECT
    DATE '2026-10-05', 1, 330000.00
FROM accepted
ON CONFLICT (sale_date)
DO UPDATE SET
    confirmed_order_count =
        commerce_lab.daily_sales_summary.confirmed_order_count + 1,
    gross_amount =
        commerce_lab.daily_sales_summary.gross_amount
        + EXCLUDED.gross_amount;

COMMIT;
```

If the same `event_id` is reprocessed for the `daily_sales` projection, the `accepted` CTE returns zero rows; the subsequent `INSERT ... SELECT` inserts nothing and adds nothing to the summary. If either step fails before `COMMIT`, the entire transaction rolls back.

Key points to remember:

- Event IDs must remain **stable across retries**, never generating a fresh UUID on each retry of the same event.
- Recording the event and updating the summary must sit inside the **same transaction** to prevent "marked processed without adding" or vice versa.
- Emitting events from the source and delivering them to consumers outside PostgreSQL still require dedicated design. This example only covers **consumer-side idempotency within one database**.
- For order cancellations or refunds, the system also needs compensating events, not just positive sales increments.

### 11.2. Eventual Consistency Levels

If a worker consumes events from a queue and updates `daily_sales_summary` seconds or minutes later, this table is a **lagging projection**. Define an explicit SLA:

```text
Policy example:
  Source data commits at time T.
  Projection must catch up within 60 seconds under normal load.
  If lag > 60 seconds: alert and mark dashboard stale.
```

The 60-second figure is a product example, not a PostgreSQL guarantee. Measure lag **from source transaction commit** to completion of projection application, not merely queue delivery latency.

## 12. Synchronizing via Application, Trigger, or CDC?

Decision tree:

```text
                   Extra data needs storing
                            |
                 Must it be consistent
                 immediately at COMMIT?
                    /                 \
                  Yes                 No
                   |                   |
        Same database/transaction?   Lag SLA + reconciliation ready?
             /          \             /          \
           Yes           No         Yes           No
            |             |          |            |
      Transaction/     Design     Event/CDC    Not ready
      trigger          workflow   projection   for reliable
                       & errors   + retries    replication
```

| Mechanism | Advantages | Risks / Costs |
| --- | --- | --- |
| Application transaction | Business logic centralized in service; can coordinate multiple tables | Other writers might bypass the workflow; needs locking and concurrency testing. |
| Database trigger | Enforces sync at DB layer inside the same transaction | Logic hidden from calling SQL; slower writes, lock contention, migration management. |
| Materialized view + refresh | No custom delta logic; queried like a table | Stale between refreshes; refresh cost and scheduling overhead. |
| Event-driven projection | Decouples read/write load, scales consumers | Retries, duplicates, out-of-order events, lag, backfills, and reconciliation. |
| Logical decoding / CDC | Streams DB changes without modifying every code path | WAL retention, slots, schema evolution, event ordering, connector operations. |

### 12.1. CDC Does Not Automatically Guarantee Exactly-Once

PostgreSQL supports **logical decoding** and logical replication under suitable configurations. A connector can read changes from WAL and publish events to downstream systems.

However, a committed source transaction and a message sent to a broker are **two separate boundaries**. If a connector publishes an event and crashes before checkpointing progress, that event may be redelivered. That is why consumers still need **idempotency** and key-based ordering where required.

Additionally, replication slots can retain WAL when a consumer falls behind; introducing new projections requires slot monitoring, disk limits, and recovery plans if WAL history is lost.

### 12.2. Transactional Outbox

When an application both writes an order and needs to emit an event for an external projection, a common pattern is the **transactional outbox**:

```text
BEGIN PostgreSQL transaction
   UPDATE orders
   INSERT outbox_events
COMMIT
          |
          v
Publisher/CDC reads outbox
          |
          v
Broker / consumer
          |
          v
Projection updated idempotently
```

The outbox records the business mutation and the **intent to emit an event** inside the same PostgreSQL transaction. It does not turn broker delivery into a distributed atomic transaction; publishers can redeliver, consumers can reprocess, and retries plus monitoring remain mandatory.

Denormalization over event streams is reliable only when the system has **event identity, retry policies, required ordering guarantees, and reconciliation**.

## 13. JSONB and Nested Data: Not Always Denormalization

PostgreSQL provides the `jsonb` type, useful when an entity has flexible attributes or needs a document snapshot.

For example, an order storing a shipping address snapshot:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN shipping_address_snapshot jsonb;

UPDATE commerce_lab.orders
SET shipping_address_snapshot = jsonb_build_object(
    'recipient', 'Lan',
    'city', 'Ho Chi Minh City',
    'street', 'Example Street 12'
)
WHERE order_id = 101;
```

This is a reasonable snapshot: a finalized order's delivery address should not silently change when the customer edits their default account address.

Conversely, embedding the entire customer profile, copies of product records, and payment history inside each order's JSONB solely to avoid JOINs brings steep costs:

- Data is duplicated repeatedly with unclear ownership for updates.
- Foreign keys between nested JSON fields and other tables cannot be enforced like standard relational columns.
- Queries/updates may require specialized JSONB path syntax and indexes.
- Schema evolution gets messy when multiple payload versions coexist.
- Updating part of a JSONB value still creates a new MVCC tuple version—it is not free just because it looks document-shaped.

**JSONB is neither inherently worse nor better than relational tables.** Use it for flexible structures or well-bounded snapshots, while data needing joins, uniqueness, referential integrity, and independent updates generally belongs in keyed, constrained tables and columns.

### 13.1. JSONB Indexes Still Follow Workload

For repeated JSONB path queries, PostgreSQL supports GIN and expression indexes where appropriate.

```sql
CREATE INDEX idx_orders_shipping_snapshot
ON commerce_lab.orders
USING gin (shipping_address_snapshot);
```

Extra indexes consume disk space and slow down writes. Do not add GIN indexes to every JSONB column if queries mostly fetch the whole object by primary key.

## 14. Generated Columns: Storing Derived Values Within One Row

PostgreSQL supports **generated columns**, letting the database maintain a value from an expression referencing columns of the **same row**, subject to expression and version rules.

For example, adding a line total per row:

```sql
ALTER TABLE commerce_lab.order_items
ADD COLUMN line_total numeric(18, 2)
GENERATED ALWAYS AS (quantity * unit_price) STORED;
```

Then:

```sql
SELECT
    order_id, line_no, quantity, unit_price, line_total
FROM commerce_lab.order_items
WHERE order_id = 101
ORDER BY line_no;
```

PostgreSQL computes `line_total` from `quantity` and `unit_price` automatically, reducing the chance an application writes an inconsistent **single-row** line total.

However, you cannot directly make `orders.total_amount` a generated column using a `SUM(order_items)` expression referencing other rows/tables. Generated columns have strict rules around immutability, no cross-table/subquery references, and storage semantics by PostgreSQL version.

| Need | Suitable Tool to Consider |
| --- | --- |
| `line_total = quantity * unit_price` within one row | Generated column, or compute at query time. |
| `order_total = SUM(items)` across multiple rows | Query/`VIEW`, trigger, transaction, or projection table. |
| Daily sales across millions of orders | Materialized view or maintained summary table. |
| Customer address at order confirmation | Snapshot with explicit immutability rules. |

Generated columns do not solve every denormalization scenario, yet they eliminate manual sync places for sufficiently simple row-local expressions.

## 15. Consistency Models: Strong, Eventual, and Historical

Before making trade-offs, name the **consistency guarantee users and services actually require**.

### 15.1. Synchronous Consistency at Commit

For instance, an order must never be confirmed unless its stored total equals the sum of its line items.

```text
COMMIT succeeds
     |
     v
order_items and orders.total_amount
must reflect the same business state
```

When all mutations execute inside one transaction with proper concurrency control, other readers never observe a half-committed transaction. This is standard for decision-critical data such as amounts due, balances, credit limits, or inventory.

### 15.2. Eventual Consistency

For instance, a management dashboard can tolerate new order counts lagging by 30 seconds.

```text
10:00:00 order confirmed in orders
10:00:03 event emitted
10:00:12 projection updated
10:00:12 dashboard reflects new order
```

Actual lag must be measured and monitored. "Eventual" is not a guarantee that data will **automatically** become right without error handling, backfills, or reconciliation. A stalled consumer can leave a projection stale indefinitely if undetected.

### 15.3. Historical Snapshots

`customer_name_at_order` differing from `customers.full_name` after a rename can be 100% correct. It is not "waiting to sync"—it **must not be overwritten by routine syncs** because the two values belong to different points in time.

### 15.4. One System Can Combine Multiple Models

| Data | Suggested Guarantee (Business-Dependent) | Rationale |
| --- | --- | --- |
| Account balance used for payment authorization | Strong consistency in transaction | Financial decisions cannot rely on an unguarded stale copy. |
| Order total on a finalized order | Synced with line items at checkout | Invoices must never carry wrong amounts. |
| Name on an issued invoice | Historical snapshot | Preserves the exact value at issuance time. |
| Internal revenue chart | Eventual per SLA | Can optimize read speed, tolerating communicated lag. |
| Product listing page cache | Eventual via TTL/invalidation | Reconstructible from source of truth upon expiration. |

The goal is not picking "strong" everywhere or "eventual" everywhere, but **defining the right guarantee for each business flow**.

## 16. PostgreSQL MVCC: Consistent Reads Still Require Defining the Source

PostgreSQL uses MVCC. At `READ COMMITTED` (the default isolation level), each statement sees a snapshot consistent as of statement start. That prevents an aggregate query from reading uncommitted half-changes from another transaction.

Yet two things must be distinguished:

1. A `SELECT` over normalized data reads a consistent snapshot under the active isolation rules.
2. A cache column updated incorrectly by an earlier transaction is **business-corrupted committed data**. MVCC does not heal it.

Example:

```sql
SELECT
    o.total_amount,
    (
        SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
        FROM commerce_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ) AS calculated_total
FROM commerce_lab.orders AS o
WHERE o.order_id = 101;
```

If the two values differ in the same row, investigate the derived-update rules. Raising the isolation level alone will not retroactively reconcile past bad writes.

### 16.1. Separate SELECTs Can See Different Points in Time

Under `READ COMMITTED`, two consecutive `SELECT` statements inside one transaction can observe newer committed state in the second query. If a report runs multiple separate queries and expects all of them to share a single snapshot, choose an appropriate isolation level/snapshot.

Example reading a consistent multi-query reconciliation snapshot:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM commerce_lab.orders;
SELECT count(*) FROM commerce_lab.order_items;

COMMIT;
```

This helps **multi-statement read reports**, though holding long-running transactions carries MVCC overhead and can block cleanup of dead tuples. Never hold a read transaction open for hours just to avoid designing a proper reporting/snapshot mechanism.

## 17. Detecting Drift Through Reconciliation

Even with carefully written application logic or triggers, a long-lived denormalized system should support **reconciling stored copies against the source of truth**.

Example finding orders whose `total_amount` disagrees with line items:

```sql
SELECT
    o.order_id,
    o.total_amount AS stored_total,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS recalculated_total,
    o.total_amount
        - COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS difference
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
       COALESCE(SUM(i.quantity * i.unit_price), 0)
ORDER BY o.order_id;
```

If the query returns no rows, the checked totals match within that query's snapshot. If rows return, diagnose the **root cause** before overwriting:

- Did a write path bypass the trigger or miss the transaction?
- Did an import or maintenance script mutate `order_items` directly?
- Were events duplicated or out of order in an async projection?
- Did the total formula change (discounts, taxes, refunds) without backfilling old rows?
- Was there a race during migration rollout or cutover?

### 17.1. Reconciliation Does Not Mean Blindly Overwriting Everything

A blanket fix:

```sql
UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
);
```

may be fine in a **lab with all writers stopped**. In live production, it can cause heavy lock contention or overwrite fresh writes with totals computed from a stale snapshot.

A production repair workflow should:

1. Identify affected keys and blast radius.
2. Confirm the source of truth and exact formula.
3. Choose a controlled write window or lock/batch strategy to repair subsets safely.
4. Log repair actions and re-measure drift afterward.
5. Fix the root cause: trigger, worker, idempotency, migration, or concurrency locks.

Without fixing the root cause, a nightly reconciliation job merely hides recurring daytime corruption.

### 17.2. Drift Metrics to Monitor

For async projections, monitor:

- **Lag:** delay between source commit and projection application.
- **Count divergence:** record count mismatch between source and projection per key/period.
- **Value divergence:** differences in quantities, amounts, statuses, or group hashes.
- **Retry / dead-letter rates:** failed, retried, or unprocessable events.
- **Backfill progress:** keys processed, cursor/watermark position, verified range.

For financial data, define clear alert thresholds and incident response procedures. Never tolerate an indefinitely wrong summary table simply because you chose eventual consistency.

## 18. Migrating from Normalized to Denormalized

Adding a redundant column to a table used by multiple applications is a **data and write-ownership migration**, not just an `ALTER TABLE`.

A controlled plan:

### Phase 1 — Define the Invariant and Owner

Document explicitly:

```text
orders.total_amount:
  source of truth = order_items
  formula         = SUM(quantity * unit_price)
  consistency     = synchronous per transaction
  writer          = database trigger OR single application service
  repair          = recompute under controlled locking/window
```

Without a spec, one backend service may update totals, a batch job may also update totals, and a trigger may add them a third time—each "working as intended" while producing broken data.

### Phase 2 — Add the New Structure

Add the column nullable or with a safe default per migration plan:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN total_amount_new numeric(18, 2);
```

The name `total_amount_new` illustrates a multi-phase rollout strategy—**do not create this extra column if the lab already has `total_amount`**. In production, avoid leaving two ambiguous target columns around.

### Phase 3 — Protect New Writes and Backfill Old Rows

A classic race condition:

```text
T1: Backfill job reads order 101 total = 330,000
T2: App adds a line item and updates total = 354,000
T3: Backfill job writes back 330,000

Result: total column is stale due to a race, even though both ran valid SQL.
```

Pick an explicit mitigation strategy:

- A maintenance window pausing related writers, backfilling, and verifying.
- Batched backfills by key range with proper locking and writer coordination.
- Event log/watermarks to replay any changes occurring between snapshot and cutover.
- Controlled dual-write, comparing both read paths before switching reads.

No single `UPDATE all rows` statement is automatically safe against active concurrent writers.

### Phase 4 — Shadow-Compare Before Switching Reads

During a parallel validation period, the application can compute totals from `order_items` and compare against the new column to catch mismatches. Emit discrepancies to controlled metrics/logs without leaking sensitive data.

Once discrepancy rate falls within the **business-required tolerance** (typically zero for strictly synced totals), switch UI screens/endpoints to read the stored column.

### Phase 5 — Cutover and Rollback

When switching reads:

- Record compatible application and schema versions.
- Keep a fallback path to recompute from source if the cached column misbehaves.
- Continue drift monitoring for a soak period after cutover.
- Do not rush to drop source code or constraints until the new mechanism is proven stable.

**Rolling back application code does not automatically roll back DDL**: schema and data changes need their own reversal plan. Migration design aims both to reduce data corruption risk and to avoid breaking overlapping service deployments.

## 19. Quantifying Benefits and Costs

Denormalization is justified only with evidence of a bottleneck and expected net gain.

### 19.1. A Simple Cost Model

Suppose:

```text
System A:
  100,000 order-total reads/hour
  1,000 line-item writes/hour

Normalized approach:
  every read sums the related line items

Denormalized approach:
  every read fetches orders.total_amount
  every write incurs extra total computation/update
```

If total read savings significantly exceed added write cost, storing the total may pay off. Measure all dimensions:

| Cost Dimension | Normalized | Denormalized |
| --- | --- | --- |
| Reading one order by ID | Query may need to `SUM` line items | Reads one extra stored column. |
| Writing/editing a line item | Updates one table and its indexes | Also updates parent total/triggers and parent WAL. |
| Lock contention | Mostly on the modified line item | Can introduce hotspots on `orders`. |
| Storage | Fewer duplicate data copies | Extra columns, indexes, summaries, WAL, backups. |
| Correctness | Fewer derived states to maintain | Requires invariants, tests, and reconciliation. |
| Operations | Fewer sync mechanisms | Extra refresh jobs/consumers/monitors if using projections. |

A conceptual decision formula:

```text
Measured read benefit
    > Extra write cost
      + synchronization cost
      + monitoring/reconciliation cost
      + data-error risk & incident cost
```

Never reduce everything to raw milliseconds without weighing business impact. One wrong financial total can cost far more than a few milliseconds saved on a query.

### 19.2. EXPLAIN (ANALYZE, BUFFERS)

PostgreSQL lets you measure query plans with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM commerce_lab.orders AS o
JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id = 1
GROUP BY o.order_id;
```

And compare after introducing the derived column:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM commerce_lab.orders
WHERE customer_id = 1;
```

Note: these two queries differ on orders without items because the first uses an inner `JOIN`. For an exact business comparison covering all orders, use `LEFT JOIN` as shown earlier.

`EXPLAIN ANALYZE` actually executes the query, so weigh load before running it in production. On tiny datasets, the planner often chooses sequential scans, making benchmarks unrepresentative of multi-million-row tables. Benchmark on data with realistic volumes, distributions, read/write ratios, and indexes.

### 19.3. Measure the Write Side Too

Do not benchmark only the dashboard read query. When adding triggers or `orders.total_amount` updates, measure:

- `INSERT/UPDATE/DELETE order_items` latency.
- Transactions waiting for locks on `orders` rows.
- Deadlock and serialization failure rates.
- Extra WAL volume, table/index bloat, and autovacuum pressure.
- Behavior when 10–100 concurrent writers update the same order or hot summary key.
- Backup/recovery times and replication lag impact.

An optimization cutting read latency by 20% while causing lock contention severe enough to stall checkouts under peak load is a net loss.

## 20. Security and Access Control for Denormalized Data

Copying data across tables or projections also creates **additional access paths and storage locations for sensitive data**.

For example:

- Storing customer email on every order allows any role with `SELECT` on `orders` to read emails even without access to `customers`.
- A materialized view might expose aggregated or snapshotted names, phone numbers, or addresses.
- A JSONB snapshot may retain personal data longer than the source table's retention policy allows.
- Logs or event streams can replicate identifying data into brokers and downstream projections.

Therefore, beyond performance and consistency, verify:

1. **Permission boundaries:** which roles may read derived tables, materialized views, or JSONB payloads?
2. **Sensitive fields:** are unnecessary PII fields being copied downstream?
3. **Retention:** when records are deleted or anonymized per policy, are caches/snapshots handled accordingly?
4. **Auditability:** can you trace which source created or updated a copied record?
5. **Backups:** are derived copies backed up and restorable, or reliably rebuildable from the source of truth?

A slightly slower JOIN that keeps sensitive columns inside a tightly protected table can be far safer. Thus, denormalization is never purely an SQL question.

## 21. Decision Checklist Before Adding a Redundant Column

For each proposal, answer in order:

1. **Which exact query is slow?** Do you have `EXPLAIN (ANALYZE, BUFFERS)`, p95/p99 latency, and call frequency?
2. **Is there a non-redundant alternative?** Better indexes, query rewrites, pagination, app-level summary, or TTL caching?
3. **Is the copied info the same current fact or a historical snapshot?**
4. **Where is the source of truth?** One table, multiple tables, or an external system?
5. **Must updates be synchronous on commit, or is lag acceptable?** If lag is allowed, what is the SLA and how is staleness shown?
6. **Which writers can modify the source?** Are there maintenance scripts, migrations, bulk imports, or CDC streams?
7. **How are concurrency and retries handled?** Lock ordering, idempotency, deadlocks, `SERIALIZABLE`, and connection failures.
8. **Is drift detection in place?** Reconciliation queries, alerts, repair playbooks, and operational ownership.
9. **Is there a safe migration and rollback path?** Do backfill and cutover avoid overwriting fresh writes?
10. **Does the extra data impact permissions or retention?** PII exposure, snapshots, auditing, downstream consumers.

Without maintenance and reconciliation mechanisms, "speeding up by storing another column" merely trades query cost for **silent data corruption risk**.

## 22. Common Mistakes

**1. "JOINs are slow, so eliminate JOINs everywhere."** PostgreSQL executes JOINs very efficiently with proper indexes and statistics. Denormalization must follow measurements, not bias against JOINs.

**2. "Because we use transactions, cached columns are always right."** Transactions guarantee atomicity, yet bypassed code paths, unlocked read-modify-writes, or flawed migrations can still break invariants.

**3. "Triggers automatically handle every kind of update."** Triggers depend on event types, row/statement scope, and execution conditions; `TRUNCATE` does not fire per-row `DELETE` triggers. Triggers must cover all write paths.

**4. "Just store the SUM in a generated column."** Standard generated columns evaluate expressions within the same row under PostgreSQL's immutability rules—they do not aggregate child table rows.

**5. "Materialized views auto-refresh when base tables change."** False. You need `REFRESH MATERIALIZED VIEW` or a separate update mechanism.

**6. "REFRESH CONCURRENTLY is free and instantaneous."** It reduces read blocking via a specific mechanism, requires a qualifying unique index, and still consumes significant I/O and CPU.

**7. "Snapshot data differing from the current customer table is a sync bug."** Not always. Names, addresses, or prices at transaction time are often intentionally preserved for historical accuracy.

**8. "ON CONFLICT guarantees exactly-once consumer processing."** It guards against key conflicts on the summary row; if the same event is processed twice against the same summary key, `ON CONFLICT DO UPDATE` will still double-count metrics.

**9. "Eventual consistency means no monitoring is needed."** False. If a consumer stalls, projections fall behind indefinitely. You still need lag SLAs, retries, idempotency, and reconciliation.

**10. "Raising isolation level fixes previously corrupted values."** Isolation governs how concurrent transactions observe and contend on data; it never repairs previously committed wrong values.

**11. "JSONB always speeds up queries by avoiding JOINs."** It can cause heavy duplication, higher update costs, and weaker constraints; benchmark real query paths.

**12. "Reporting tables only hold aggregates, so permissions don't matter."** Projections can still expose sensitive business metrics or PII that require strict access control.

**13. "Backfills don't interfere with live writes."** A backfill writing totals from an old snapshot can overwrite newer service updates; coordinate cutover carefully.

**14. "With a summary table, we don't need to store event IDs."** If events are redelivered, totals get double-counted; event identity and idempotency are usually essential.

**15. "Pre-store lots of extra columns just in case."** Unused redundant data adds storage, WAL, migration friction, and drift surface area for zero benefit.

## 23. Practice Exercises

These exercises use the `commerce_lab` schema created in section 3. Run triggers and data-mutating snippets only in a dedicated lab environment. Several sections show **alternative strategies**; do not run all DML blocks sequentially in one script while ignoring data changes from prior steps.

### Exercise 1. Identifying Derived Data vs. Snapshots

Given the columns:

```text
orders.total_amount
orders.customer_name_at_order
orders.current_customer_name_cache
order_items.unit_price
daily_sales_summary.confirmed_order_count
```

Classify:

- Which values **must stay in sync** with a source after every commit?
- Which values are **point-in-time business snapshots**?
- Which values can be **eventually consistent** if SLAs permit?

**Suggested Answer:** `total_amount` must match the line-item sum per the defined formula; `customer_name_at_order` and `unit_price` on finalized order lines are typically historical snapshots; `current_customer_name_cache` requires a sync policy matching current names; `daily_sales_summary` can lag within SLA. Final classification always depends on the product's business definitions.

### Exercise 2. Query to Detect Mismatched Order Totals

```sql
SELECT
    o.order_id,
    o.total_amount AS stored,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS calculated
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
       COALESCE(SUM(i.quantity * i.unit_price), 0);
```

**Question:** Why use `LEFT JOIN` instead of `JOIN`?

**Explanation:** `LEFT JOIN` keeps orders without any line items so they are reconciled against an expected total of 0; an inner `JOIN` would skip those orders.

### Exercise 3. Transactions and Rollback

With trigger `trg_adjust_order_total` active in the lab:

```sql
BEGIN;

UPDATE commerce_lab.order_items
SET quantity = quantity + 1
WHERE order_id = 101 AND line_no = 1;

SELECT total_amount
FROM commerce_lab.orders
WHERE order_id = 101;

ROLLBACK;
```

**Question:** After `ROLLBACK`, does `total_amount` keep the increment applied by the trigger?

**Answer:** No. The trigger runs inside the same transaction, so changes to both `order_items` and `orders.total_amount` roll back together.

### Exercise 4. Two Writers Updating the Same Order

Suppose transactions A and B simultaneously add line items to order 101. Explain why:

```sql
UPDATE commerce_lab.orders
SET total_amount = total_amount + 12000
WHERE order_id = 101;
```

is generally safer than reading `total_amount` into application memory, adding 12,000, and writing back a precomputed number without locking.

**Hint:** `UPDATE ... total_amount + delta` performs the addition atomically on the database row inside the transaction alongside row locking. Unlocked client-side read-modify-write can lose updates when two clients read the same old value.

### Exercise 5. Can a Materialized View Go Stale?

Create and query `mv_daily_sales`, then confirm a new order in `orders` without refreshing the view.

**Question:** Why doesn't `SELECT * FROM mv_daily_sales` show the new order?

**Answer:** A materialized view holds results from the previous refresh. Updating it requires running `REFRESH MATERIALIZED VIEW` per operational policy.

### Exercise 6. Redelivered Event

A worker receives the same event twice:

```text
event_id = 1fa80ca8-e121-43cf-8afe-27124d141f42
sale_date = 2026-10-05
amount = 330000
```

**Question:** If you only run the additive upsert twice, what goes wrong? How do you fix it?

**Answer:** Sales totals are counted twice. The consumer must record the event uniquely per projection within the same transaction that updates the summary—for example using `processed_projection_events` and `ON CONFLICT DO NOTHING`.

### Exercise 7. Designing a Backfill Without Overwriting Fresh Writes

A job reads order totals at T1, while a service updates line items at T2, and the job writes the old total at T3.

**Task:** Propose two ways to reduce this risk.

**Hint:** Run the backfill during a controlled write window; lock/serialize per order alongside writers; or capture change watermarks to replay events occurring after the snapshot and reconcile before cutover. Pick one concrete workflow and test under concurrency.

### Exercise 8. Weighing the Cost

An endpoint reads order totals 5 times per second, each order has only a few lines, and `EXPLAIN ANALYZE` shows dynamic summing is very fast. The team wants to add `total_amount` solely to avoid a JOIN.

**Evaluation:** There is no evidence justifying denormalization. Keep the current query or tune indexes/data fetching. Tiny read gains are unlikely to outweigh trigger overhead, lock contention, and reconciliation burden.

### Exercise 9. Proposing an Appropriate Denormalization

A reporting system covers the last 30 days, ingesting millions of event rows per hour, and the dashboard must load within 2 seconds. Data may lag by up to 2 minutes.

**Approach:** Consider a scheduled materialized view or an incremental summary table. Measure refresh cost, lag, missed-event detection, `last_refresh` visibility, and query latency. Do not treat `orders.total_amount` alone as the solution if the true bottleneck is aggregating across all daily orders.

## 24. Summary

Intentional denormalization is a decision to **trade away the simplicity and natural consistency of normalized schemas in exchange for read speed, reporting capability, or historical preservation**. That trade-off is sound only when you clearly know the source of truth, the semantics of each copy, and the synchronization guarantee.

Core principles:

- **Normalization is the starting point.** Measure with `EXPLAIN (ANALYZE, BUFFERS)` and try indexing or query rewrites first—never eliminate JOINs out of habit.
- **Not every copy should stay in sync.** Names, addresses, or prices snapshotted at transaction time are right to differ from current master data.
- **Derived data must have an explicit invariant.** If storing `orders.total_amount`, define its formula, transaction boundaries, and authorized write paths.
- **Transactions and triggers enforce synchronous updates within one PostgreSQL database** when logic and concurrency are designed properly; they still carry write overhead, locking, and testing demands.
- **Materialized views and async projections trade freshness for read speed.** They require SLAs, refresh/retry pipelines, idempotency, and reconciliation.
- **JSONB, generated columns, and summary tables solve different problems.** No single denormalization technique fits every workload.
- **Migrations must prevent races.** Backfills, dual-writes, and cutovers must be coordinated so stale jobs never overwrite newly committed changes.
- **Reconciliation is part of the design**, not an emergency patch bolted on after users report wrong numbers.

A well-justified choice can be stated in one clear sentence: **"We store extra value X to optimize measured query Y; the source of truth is Z; data refreshes via mechanism M within maximum lag T; job R detects and repairs drift."** Only when you can answer that sentence and back it with measurements is denormalization truly intentional rather than unmanageable redundancy.
