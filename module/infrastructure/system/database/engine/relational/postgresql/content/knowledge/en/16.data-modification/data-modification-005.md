# DELETE USING and Scope Control in PostgreSQL

When operating a multi-tenant system, deleting data is rarely as simple as `DELETE FROM orders WHERE id = 1`. Real-world requirements typically look like: "Delete orders cancelled before the archive cutoff, **only** for the target tenant and **only** when the customer has closed their account," "Clean up rows whose keys no longer exist in a reference table," or "Delete in batches of 100 eligible records without blocking other processes."

In PostgreSQL, the **`DELETE ... USING`** syntax lets you include **other tables, subqueries, or CTEs** when determining which target-table rows to delete. It is especially useful when deletion conditions depend on data in related tables.

However, a syntactically valid statement can still cause data loss if:

- The `WHERE` clause or a join condition is missing.
- The `tenant_id` filter is forgotten in a multi-tenant system.
- `AND`/`OR` precedence is misapplied, widening the scope beyond intent.
- Joining on a key that is only unique **per tenant** forgets to match tenant IDs.
- Joined row count is mistaken for the number of **target rows** to be deleted.
- Foreign keys with `ON DELETE CASCADE`, triggers, partitions, or dependent tables are overlooked.
- A preview `SELECT` is run first and assumed unchanged when `DELETE` executes afterward.
- Someone attempts to write `DELETE ... LIMIT` as in some other database engines.

This lesson belongs to the **Data Modification** chapter of the *Database Engine Relational PostgreSQL* module. Its goal is to establish accurate semantics for `DELETE USING` and build a workflow of **define scope – preview – check dependencies – delete in a transaction – verify – audit/recover**.

> **Practice warning:** `DELETE` mutates data directly. All tables in this lesson use a dedicated `delete_lab` schema, synthetic values, and `BEGIN ... ROLLBACK` blocks so experiments are repeatable. Never run `DELETE` or `DROP` on live data without verifying permissions, scope, backups, and your team's approval process.

## 1. Basic DELETE: Which Rows of Which Table?

### 1.1. Minimal Syntax

```sql
DELETE FROM some_table
WHERE some_condition;
```

PostgreSQL deletes rows **of the table named after `DELETE FROM`** that satisfy the condition. Without `WHERE`, there is no target-row filter:

```sql
-- Extremely dangerous when the table holds real data:
-- DELETE FROM some_table;
```

That statement deletes all deletable rows in the table. **Never** treat adding `USING` as an automatic safeguard; join and filter predicates govern the scope.

### 1.2. Deleting Rows Differs from Dropping or Truncating Tables

| Command | Effect | Row-Level WHERE? |
|---|---|---|
| `DELETE FROM table WHERE ...` | Deletes matching rows | Yes |
| `DELETE FROM table` | Deletes all rows allowed by privileges/policies | No |
| `TRUNCATE table` | Empties the table via its own mechanism | No |
| `DROP TABLE table` | Drops table definition along with its data | No |

`DELETE` does not drop table structure, indexes, or schemas. In PostgreSQL, deleted rows may occupy physical space for some time due to MVCC; `VACUUM`/autovacuum reclaims dead tuple versions according to system conditions.

### 1.3. DELETE and UPDATE Do Not Mean the Same Thing

If business rules require **keeping history** or "marking inactive," it may be more appropriate to run:

```sql
UPDATE some_table
SET deleted_at = CURRENT_TIMESTAMP
WHERE ...;
```

This is a **soft delete**, not a physical deletion. It carries its own implications for queries, uniqueness, security, and retention policies. Never assume soft deletes automatically satisfy regulatory hard-deletion mandates.

## 2. DELETE USING: PostgreSQL Syntax and Semantics

Basic pattern:

```sql
DELETE FROM target_table AS t
USING related_table AS r
WHERE t.related_id = r.id
  AND r.some_flag = 'yes'
RETURNING t.id;
```

Components:

- **`DELETE FROM target_table AS t`**: names the **target table** whose rows will be deleted.
- **`USING related_table AS r`**: introduces an extra data source for evaluating predicates; **does not delete rows from `r`**.
- **`WHERE t.related_id = r.id`**: joins target rows to related source rows.
- **`AND r.some_flag = 'yes'`**: filters rows meeting business criteria.
- **`RETURNING t.id`**: returns data from the deleted target rows.

The semantics are straightforward:

> Delete a row **`t`** if there is any combination of rows from `USING` sources that makes the `WHERE` expression true.

If one target row matches **multiple** source rows, the target row itself can still only be deleted **once** in that statement. However, a `SELECT` using the same join may emit multiple rows; distinguish those two counts carefully.

### 2.1. Comparison with MySQL DELETE JOIN

Do not use syntax like:

```sql
-- This is NOT PostgreSQL DELETE JOIN syntax:
-- DELETE o
-- FROM orders AS o
-- JOIN customers AS c ON c.customer_id = o.customer_id
-- WHERE c.status = 'closed';
```

In PostgreSQL, write:

```sql
-- PostgreSQL syntax example:
-- DELETE FROM orders AS o
-- USING customers AS c
-- WHERE c.customer_id = o.customer_id
--   AND c.status = 'closed';
```

`USING` brings additional sources into the deletion condition, rather than placing a `JOIN` immediately after the target table as in MySQL syntax.

### 2.2. Target Table Alias

When you declare:

```sql
DELETE FROM delete_lab.orders AS o
...
```

use the alias **`o`** throughout the rest of the statement to reference the target table. PostgreSQL binds the alias as the target table's name in query scope; referencing the original unaliased table name can cause errors.

### 2.3. Which Table Is Deleted?

In:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE ...
```

only rows of **`delete_lab.orders`** are direct deletion targets. `customers` acts purely as a condition source and is not deleted by this command.

**Indirect exception:** foreign keys with `ON DELETE CASCADE`, triggers, or other database mechanisms can modify **related tables**. Thus "only the target table is named" does not mean "only that table changes across the entire database."

## 3. Setting Up a Two-Tenant Practice Environment

We model a multi-tenant application. `customer_id` is only unique **within one tenant**; customer names or IDs can be reused across tenants. A proper deletion query must check both **`tenant_id`** and **`customer_id`**.

### 3.1. Create Schema

```sql
CREATE SCHEMA IF NOT EXISTS delete_lab;

CREATE TABLE delete_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    customer_name TEXT NOT NULL,
    account_status TEXT NOT NULL
        CHECK (account_status IN ('active', 'closed')),
    PRIMARY KEY (tenant_id, customer_id)
);

CREATE TABLE delete_lab.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled', 'refunded')),
    created_at TIMESTAMPTZ NOT NULL,
    cancelled_at TIMESTAMPTZ,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES delete_lab.customers(tenant_id, customer_id),
    CONSTRAINT chk_cancel_date
        CHECK (status <> 'cancelled' OR cancelled_at IS NOT NULL)
);
```

**Design note:** `orders.order_id` is a table-wide primary key, while the customer relationship uses the **composite key** `(tenant_id, customer_id)`. This prevents an order in tenant 10 from accidentally referencing a customer in tenant 20 with the same `customer_id`.

### 3.2. Customer Data

```sql
INSERT INTO delete_lab.customers
    (tenant_id, customer_id, customer_name, account_status)
VALUES
    (10, 101, 'An',       'active'),
    (10, 102, 'Binh',     'closed'),
    (10, 103, 'Chi',      'closed'),
    (10, 104, 'Dung',     'active'),
    (20, 101, 'Ha',       'closed'),
    (20, 201, 'Khanh',    'closed'),
    (20, 202, 'Lan',      'active'),
    (20, 203, 'Minh',     'closed');
```

**Intentional trap:** both tenant 10 and tenant 20 have `customer_id = 101`, yet tenant 10's customer is **active** while tenant 20's is **closed**. Joining solely on `customer_id` would wrongly pull in the wrong tenant's customer status.

### 3.3. Order Data

```sql
INSERT INTO delete_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, cancelled_at, amount)
VALUES
    ( 1, 10, 101, 'paid',
      '2026-09-01 09:00+07', NULL, 300),
    ( 2, 10, 102, 'cancelled',
      '2026-09-01 10:00+07', '2026-09-05 12:00+07', 180),
    ( 3, 10, 103, 'cancelled',
      '2026-09-10 09:00+07', '2026-09-12 14:00+07', 250),
    ( 4, 10, 104, 'pending',
      '2026-10-04 08:00+07', NULL, 75),
    ( 5, 10, 101, 'cancelled',
      '2026-09-20 08:00+07', '2026-09-20 10:00+07', 95),
    ( 6, 20, 101, 'cancelled',
      '2026-08-01 07:00+07', '2026-08-11 09:00+07', 210),
    ( 7, 20, 202, 'paid',
      '2026-10-03 15:00+07', NULL, 140),
    ( 8, 20, 203, 'cancelled',
      '2026-09-03 10:00+07', '2026-09-12 11:00+07', 120),
    ( 9, 10, 101, 'refunded',
      '2026-10-07 10:00+07', NULL, 85),
    (10, 10, 102, 'cancelled',
      '2026-10-08 09:00+07', '2026-10-09 10:00+07', 155),
    (11, 20, 201, 'cancelled',
      '2026-09-28 13:00+07', '2026-09-29 12:00+07', 265),
    (12, 20, 203, 'paid',
      '2026-10-12 11:00+07', NULL, 190);
```

There are **12 orders** total. Every timestamp includes `+07` so date boundaries in the examples are unambiguous.

### 3.4. Order Line Items and Processing Flags

To observe child-table impacts when orders are deleted, create `order_items` with `ON DELETE CASCADE`:

```sql
CREATE TABLE delete_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES delete_lab.orders(order_id)
        ON DELETE CASCADE,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO delete_lab.order_items
    (item_id, order_id, sku, quantity)
VALUES
    (1001, 2, 'SKU-A', 1),
    (1002, 2, 'SKU-B', 2),
    (1003, 3, 'SKU-A', 1),
    (1004, 5, 'SKU-C', 1),
    (1005, 6, 'SKU-D', 1),
    (1006, 7, 'SKU-B', 1),
    (1007, 8, 'SKU-A', 1),
    (1008, 9, 'SKU-D', 1),
    (1009, 10, 'SKU-B', 1);
```

Add a flags table where **one order can match multiple flags**:

```sql
CREATE TABLE delete_lab.order_flags (
    order_id BIGINT NOT NULL
        REFERENCES delete_lab.orders(order_id)
        ON DELETE CASCADE,
    flag TEXT NOT NULL,
    PRIMARY KEY (order_id, flag)
);

INSERT INTO delete_lab.order_flags(order_id, flag)
VALUES
    (2, 'expired'),
    (2, 'reviewed'),
    (3, 'expired'),
    (5, 'expired'),
    (6, 'expired');
```

Both `order_items` and `order_flags` have FKs pointing to `orders`. Deleting order 2 also cascades to delete two item rows and two flag rows. **The row count from `DELETE FROM orders ... RETURNING` reflects only target order rows**, not cascaded child rows.

## 4. Define Deletion Requirements Before Writing SQL

Suppose the requirement is:

> "Delete orders belonging to **tenant 10**, with status **`cancelled`**, cancelled **before 00:00 on 2026-10-01 +07**, and only when the **customer in the same tenant** has closed their account."

Break this down into verifiable conditions:

| Requirement | SQL Expression |
|---|---|
| Tenant 10 only | `o.tenant_id = 10` |
| Cancelled orders only | `o.status = 'cancelled'` |
| Cancelled before cutoff | `o.cancelled_at < TIMESTAMPTZ '2026-10-01 00:00:00+07'` |
| Match customer in same tenant | `c.tenant_id = o.tenant_id` |
| Match exact customer | `c.customer_id = o.customer_id` |
| Customer closed account | `c.account_status = 'closed'` |

**The expected target set is two orders: `order_id = 2` and `order_id = 3`**, not all old cancelled orders.

Why are the other orders excluded?

- Order 5: tenant 10, old cancelled, yet customer 101 in tenant 10 is **still active**.
- Order 10: tenant 10, closed customer, yet `cancelled_at` is **after** the cutoff.
- Orders 6, 8, 11: old cancelled, closed customers, yet belong to **tenant 20**.
- Orders 1, 4, 9: not `cancelled`.

This is the core of "deletion scope control": you should have an explicit **target list and exclusion rationale**, not just a `WHERE` clause that looks plausible.

## 5. Preview with SELECT Before DELETE

First, write a `SELECT` reflecting **the exact same joins and filters** you intend to use for deletion:

```sql
SELECT
    o.order_id,
    o.tenant_id,
    o.customer_id,
    c.customer_name,
    c.account_status,
    o.status,
    o.cancelled_at,
    o.amount
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

Expected rows:

| order_id | tenant_id | customer_id | customer_name | status | account_status |
|---:|---:|---:|---|---|---|
| 2 | 10 | 102 | Binh | cancelled | closed |
| 3 | 10 | 103 | Chi | cancelled | closed |

### 5.1. Count Targets First

```sql
SELECT COUNT(*) AS target_orders
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

Because each order matches exactly one customer on the composite key, the count is **2**. When a `USING` source has a one-to-many relationship, `COUNT(*)` on an equivalent `JOIN` can double-count orders—see Section 8.

### 5.2. You Can List Only IDs for Approval

```sql
SELECT o.order_id
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON (c.tenant_id, c.customer_id)
     = (o.tenant_id, o.customer_id)
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

The row comparison above is just shorthand for the two equality predicates. On `NOT NULL` key columns in this lab, both are semantically equivalent. For easier production SQL reviews, many teams still prefer writing **two explicit join predicates**.

**Warning:** running `SELECT` beforehand does not "lock in" that the subsequent `DELETE` will match those exact two IDs. If another transaction changes data between the two statements, the matching set can differ. Section 13 explains how to mitigate this risk.

## 6. DELETE USING Matching the Requirement

PostgreSQL statement:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.status,
    o.cancelled_at;
```

Run on the intact lab data, this deletes **exactly orders 2 and 3**.

### 6.1. Why Are Join Conditions Placed in WHERE?

In PostgreSQL, `USING` introduces source tables into the statement; join predicates linking to the target table are written in **`WHERE`**:

```sql
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
```

If you forget `c.customer_id = o.customer_id` while any `closed` customer exists in tenant 10, many orders in that tenant match that unrelated closed customer, invalidating the customer-status filter.

If you forget `c.tenant_id = o.tenant_id`, overlapping `customer_id`s across tenants pull in the wrong tenant's customer status. This lab deliberately puts customer `101` in both tenant 10 and tenant 20 to expose that trap.

### 6.2. Tenant Filters Should Not Appear Only on the USING Side

Never rely on:

```sql
-- Insufficient to guard scope without joining tenants properly:
-- WHERE c.tenant_id = 10
--   AND c.account_status = 'closed'
--   AND o.customer_id = c.customer_id
```

If `customer_id` is only unique per tenant, orders from another tenant can match a tenant 10 customer. Enforce all of:

```sql
o.tenant_id = 10
AND c.tenant_id = o.tenant_id
AND c.customer_id = o.customer_id
```

In systems using RLS, tenant predicates must also align with security policies; see Section 15.

### 6.3. RETURNING Reveals Which Target Rows Were Deleted

`RETURNING` is valuable in operations because it:

- Captures the exact deleted IDs.
- Confirms whether the intended target set was actually deleted.
- Lets you route deleted rows into an audit table inside a data-modifying statement.
- Avoids guessing from `"DELETE 2"` without knowing which two IDs were removed.

It **does not** automatically create a durable backup, does not list all cascaded child rows, and does not let you restore data after `COMMIT` without an archiving/backup plan.

## 7. Test Deletion in a Transaction and ROLLBACK

To learn or verify impact before committing, wrap the operation in a transaction:

```sql
BEGIN;

SELECT
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.cancelled_at
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id, o.tenant_id, o.customer_id;

-- Inspect state inside the current transaction:
SELECT order_id
FROM delete_lab.orders
WHERE order_id IN (2, 3)
ORDER BY order_id;

-- Abort test: revert this transaction's changes.
ROLLBACK;
```

After `ROLLBACK`, both orders and any cascaded child rows inside the transaction remain intact (assuming no external changes occurred).

### 7.1. ROLLBACK Is a Testing Tool, Not Long-Term Backup

Once a deletion is `COMMIT`ted, you cannot run `ROLLBACK` afterward to undo the finished transaction. You must rely on **backups, archives, audit trails, point-in-time recovery**, or a pre-established restore workflow.

### 7.2. Verify Before COMMIT

In production, before `COMMIT`ting, reconcile:

- Number of target rows deleted.
- List of keys/tenants in `RETURNING`.
- Child-table cascade impacts and trigger-generated changes.
- Out-of-scope records remaining untouched.
- Audit logs and transaction health.

If row counts differ from expectations, **`ROLLBACK`** and investigate—never try to "patch conditions quickly" after a bad commit.

## 8. One Order Matching Multiple USING Rows Is Still Deleted Only Once

In `order_flags`, order 2 has two flags: `expired` and `reviewed`.

Inspect the `JOIN` output:

```sql
SELECT
    o.order_id,
    f.flag
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed')
ORDER BY o.order_id, f.flag;
```

The result has **three joined rows**:

| order_id | flag |
|---:|---|
| 2 | expired |
| 2 | reviewed |
| 3 | expired |

Yet the set of **unique target orders** contains only **2 IDs**.

Test inside a transaction:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.order_flags AS f
WHERE f.order_id = o.order_id
  AND o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed')
RETURNING o.order_id;

ROLLBACK;
```

`DELETE RETURNING` returns each deleted target order **once**, not ID 2 twice just because two `order_flags` rows matched. This is the difference between **joined row count** and **deleted row count**.

### 8.1. Count Deletion Targets Accurately in SELECT

When a source has fan-out:

```sql
SELECT
    COUNT(*) AS join_rows,
    COUNT(DISTINCT o.order_id) AS target_orders
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
  AND f.flag IN ('expired', 'reviewed');
```

Result: `join_rows = 3`, `target_orders = 2`.

Never use `COUNT(*)` on a one-to-many join to report "3 orders will be deleted," as that skews scope verification and row-count thresholds.

### 8.2. DISTINCT in Preview SELECTs

You can view one row per order:

```sql
SELECT DISTINCT
    o.order_id,
    o.tenant_id
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND f.flag IN ('expired', 'reviewed')
ORDER BY o.order_id;
```

However, adding `f.flag` to `SELECT` makes rows with different flags distinct, so `DISTINCT` no longer collapses to one row per order. When the goal is simply **"has at least one matching flag,"** `EXISTS` expresses intent more cleanly.

## 9. DELETE USING vs. WHERE EXISTS

A `DELETE` conditioned on another table can be written with `USING` or `EXISTS`.

### 9.1. USING: Explicit Join

```sql
-- Example inside a test transaction:
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id;

ROLLBACK;
```

### 9.2. EXISTS: Existence Condition

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND EXISTS (
      SELECT 1
      FROM delete_lab.customers AS c
      WHERE c.tenant_id = o.tenant_id
        AND c.customer_id = o.customer_id
        AND c.account_status = 'closed'
  )
RETURNING o.order_id;

ROLLBACK;
```

With the data, keys, and predicates in this example, both statements target the same orders: **2 and 3**.

### 9.3. When to Choose Which?

| Criterion | `DELETE USING` | `DELETE WHERE EXISTS` |
|---|---|---|
| Expressing conditions across multiple tables | Natural via `USING` sources | Natural via subqueries |
| Expressing "at least one related row exists" | Possible, though joins can create fan-out | **Very clear semantics** |
| One-to-many source | Can produce match fan-out | Semantically indifferent to extra matches past the first |
| Returning/referencing related columns in predicates | Convenient | Convenient inside the subquery |
| Performance | Plan-dependent | Plan-dependent |

Never assume `USING` is always faster than `EXISTS` or vice versa. The PostgreSQL optimizer chooses plans based on statistics, indexes, row counts, and predicates; run `EXPLAIN` on representative data.

### 9.4. NOT EXISTS: Deleting Unmatched Rows

Another common requirement is "delete staging rows whose external code **no longer** exists in the valid reference table." This is an anti-join, usually expressed with `NOT EXISTS`.

Example staging tables:

```sql
CREATE TABLE delete_lab.import_candidates (
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, external_code)
);

CREATE TABLE delete_lab.valid_external_codes (
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    PRIMARY KEY (tenant_id, external_code)
);

INSERT INTO delete_lab.import_candidates
    (tenant_id, external_code, imported_at)
VALUES
    (10, 'A-01', '2026-09-01 00:00+07'),
    (10, 'X-99', '2026-09-01 00:00+07'),
    (20, 'X-99', '2026-09-01 00:00+07');

INSERT INTO delete_lab.valid_external_codes
    (tenant_id, external_code)
VALUES
    (10, 'A-01'),
    (20, 'X-99');
```

Preview rows **lacking a valid code within the same tenant**:

```sql
SELECT i.tenant_id, i.external_code
FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
ORDER BY i.external_code;
```

Only `(10, 'X-99')` is returned.

Test deletion:

```sql
BEGIN;

DELETE FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
RETURNING i.tenant_id, i.external_code;

ROLLBACK;
```

`DELETE USING` with ordinary inner-matching **cannot directly express** "no matching reference row exists." Using `NOT EXISTS` clarifies semantics and avoids `LEFT JOIN ... IS NULL` confusion in delete queries.

## 10. Scope Control via Keys and Business Predicates

Before bulk deletions, list every dimension that narrows the scope:

### 10.1. Tenant / Organization

```sql
WHERE o.tenant_id = 10
```

If data is partitioned logically by tenant, this filter is usually **non-negotiable**. Putting it on only one table is insufficient; `JOIN` predicates must also prevent cross-tenant matching.

### 10.2. Status

```sql
AND o.status = 'cancelled'
```

Do not filter solely by `cancelled_at IS NOT NULL` if statuses can be reopened or `cancelled_at` is kept as historical metadata. Establish a single source of truth for status.

### 10.3. Correct Timestamp Column

```sql
AND o.cancelled_at <
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
```

If the requirement says "cancelled before Oct 1," filter by **cancellation time**, not `created_at`. An order created in August and cancelled yesterday **must not be treated as cancelled back in August** just because its creation date is old.

### 10.4. Half-Open Bounds

`< TIMESTAMPTZ '2026-10-01 00:00+07'` cleanly excludes **exact midnight on Oct 1**. Avoid writing "before Oct 1" as `<= '2026-09-30 23:59:59'` because timestamps carry fractional seconds and easily leave gaps.

### 10.5. Reference Table Conditions

```sql
AND c.account_status = 'closed'
```

Confirm whether the column reflects **current status** or status at the time the order was cancelled. If legal/business rules depend on historical status, the current `customers` table may be insufficient; use an appropriate fact/event source.

### 10.6. Caller Privileges

Even when SQL contains proper filters, the database account should hold **least-privilege permissions**. For routine purge jobs, consider dedicated roles, RLS policies, job approvals, and auditing.

**Business filters and authorization are two separate layers**: writing `o.tenant_id = 10` does not mean a role is inherently authorized to delete tenant 10's data.

## 11. AND, OR, and Parentheses Traps

A very common flawed deletion condition:

```sql
-- Do not run: can delete 'cancelled' orders from other tenants!
-- DELETE FROM delete_lab.orders
-- WHERE tenant_id = 10 AND status = 'pending'
--    OR status = 'cancelled';
```

Because `AND` has higher precedence than `OR`, PostgreSQL evaluates it as:

```sql
WHERE (tenant_id = 10 AND status = 'pending')
   OR (status = 'cancelled')
```

The second branch **has no tenant restriction**, so tenant 20's `cancelled` orders get deleted too.

If the intent is "delete `pending` or `cancelled` orders **within tenant 10**," write:

```sql
WHERE tenant_id = 10
  AND status IN ('pending', 'cancelled')
```

or:

```sql
WHERE tenant_id = 10
  AND (status = 'pending' OR status = 'cancelled')
```

### 11.1. Test Conditions with SELECT First

```sql
SELECT order_id, tenant_id, status
FROM delete_lab.orders
WHERE tenant_id = 10
  AND status IN ('pending', 'cancelled')
ORDER BY order_id;
```

If the scope is wider than intended, fix the `SELECT` **before** converting it to `DELETE`.

### 11.2. Watch Out for NULLs in WHERE

`status <> 'paid'` excludes `NULL` values on nullable columns because comparing against `NULL` yields `UNKNOWN`. On our `status NOT NULL` lab table that trap does not trigger, yet in other schemas consider:

```sql
-- Example logic when status is nullable:
-- WHERE status IS DISTINCT FROM 'paid'
```

`IS DISTINCT FROM` evaluates cleanly even when one side is `NULL`. Never swap it in for `<>` blindly without checking requirements: expanding the candidate deletion set can violate business rules.

## 12. RETURNING and Auditing Deleted Rows

### 12.1. DELETE ... RETURNING

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.order_id IN (2, 3)
RETURNING
    o.order_id,
    o.tenant_id,
    o.customer_id,
    o.status,
    o.amount;

ROLLBACK;
```

On intact data, `RETURNING` returns exactly two rows, making it easy to reconcile against an approved list.

### 12.2. Counting Deleted Rows in the Same Statement

You can use a data-modifying CTE:

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    USING delete_lab.customers AS c
    WHERE c.tenant_id = o.tenant_id
      AND c.customer_id = o.customer_id
      AND o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
    RETURNING o.order_id
)
SELECT COUNT(*) AS deleted_order_count
FROM removed;

ROLLBACK;
```

Result is **2** when lab data is intact.

This counts **rows deleted from `orders`** and returned through the CTE—not child items or customer rows.

### 12.3. Understanding Snapshots in Data-Modifying CTEs

In PostgreSQL, a data-modifying CTE inside `WITH` executes and `RETURNING` is the explicit channel passing results to the outer query. Sub-statements within one statement follow specific snapshot visibility rules; **never** replace `RETURNING` by expecting an outer `SELECT` on the target table in the same statement to observe modifications in an imagined sequential order.

**Practical rule:** to see which rows were deleted by a statement, **use `RETURNING`**. To verify table state afterward, run `SELECT` **in the next statement of the same transaction**.

### 12.4. Recording Audits in the Same Transaction

Deleted records can be written to an audit table **before committing**. Example:

```sql
CREATE TABLE delete_lab.deleted_order_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL,
    old_status TEXT NOT NULL,
    old_amount NUMERIC(12, 2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Test operation:

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.order_id IN (2, 3)
    RETURNING
        o.order_id,
        o.tenant_id,
        o.customer_id,
        o.status,
        o.amount
)
INSERT INTO delete_lab.deleted_order_audit
    (order_id, tenant_id, customer_id, old_status, old_amount)
SELECT
    order_id, tenant_id, customer_id, status, amount
FROM removed;

SELECT order_id, tenant_id, old_status, old_amount
FROM delete_lab.deleted_order_audit
ORDER BY audit_id;

ROLLBACK;
```

If the transaction commits, both deletion and audit insertion share one transaction boundary; if it rolls back, both revert together. Still, this audit table saves only **a subset of `orders` columns** and **does not** archive `order_items` or all dependencies. Audits alone do not replace full backups/archiving.

### 12.5. Archive Before Deleting and Recovery Responsibility

For critical data, you may need **complete** archival before deleting: snapshots, child records, metadata, timestamp/actor, schema version, checksums, or restore-tested backups.

Never assume `RETURNING id` alone is enough to reconstruct orders, line items, and processing history. **Retention depth must match real recovery requirements.**

## 13. Preview SELECT and DELETE Can See Different Data

Under default **`READ COMMITTED`** isolation, each statement takes its own snapshot. A preview `SELECT` followed by `DELETE` can see different sets if another transaction commits changes in between.

Example:

```text
Time T1: SELECT finds order_id 2 and 3 eligible
Time T2: another transaction changes status of order 3
Time T3: DELETE runs with a fresh snapshot/check

Deleted rows are no longer guaranteed to be exactly 2 and 3.
```

Additionally, a new row might become eligible between statements, causing a **dynamic-predicate `DELETE`** to remove rows absent from the initial preview.

### 13.1. Locking Candidate Rows with SELECT FOR UPDATE

To inspect **existing rows** and lock them prior to deletion within the same transaction:

```sql
BEGIN;

SELECT
    o.order_id,
    o.tenant_id,
    o.status,
    o.cancelled_at
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id
FOR UPDATE OF o;

-- Next step can DELETE by the approved ID set.
-- For lab testing only, finish with:
ROLLBACK;
```

`FOR UPDATE OF o` locks the selected **`orders`** rows so concurrent updates/deletes on those rows must coordinate with the current transaction. However:

- It **does not lock `customers` rows** because `OF o` restricts locking to `o`.
- It **does not prevent newly inserted rows** from entering the matching set after preview unless additional consistency/scope mechanisms exist.
- Holding transactions/row locks too long causes blocking and operational overhead.
- Queries needing stability relative to `customers` must account for **customer status** changes too.

Never claim that simply adding `FOR UPDATE` guarantees "an immutable snapshot where nothing can change."

### 13.2. Delete by Approved ID List

When the requirement is **delete only pre-approved IDs**, filter by those explicit keys while keeping critical guards:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE o.order_id IN (2, 3)
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND c.account_status = 'closed'
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

Advantage: you cannot accidentally delete **new IDs** outside `2, 3` that just became eligible. At the same time, the remaining guards protect against business states changing right before deletion.

If the ID list is large or client-supplied, use parameterized queries or controlled staging tables and validate tenant ownership. Never string-concatenate `IN (...)` from untrusted input.

### 13.3. Repeatable Read and Serializable Do Not Replace Deletion Logic

Under `REPEATABLE READ`, statements in the same transaction share a consistent snapshot per PostgreSQL rules; concurrent modifications can trigger serialization errors requiring retry. `SERIALIZABLE` enforces stronger transactional consistency yet may raise serialization failures requiring full-transaction retries.

Example transaction reading and deleting by explicit list:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT order_id
FROM delete_lab.orders
WHERE tenant_id = 10
  AND order_id IN (2, 3)
ORDER BY order_id;

DELETE FROM delete_lab.orders
WHERE tenant_id = 10
  AND order_id IN (2, 3)
RETURNING order_id;

ROLLBACK;
```

Never treat an isolation level as magic that fixes a broken `WHERE`. Isolation does not know your business rule is "delete cancelled orders of closed customers" if your query omits it.

### 13.4. Pattern for Selecting and Deleting Keys in One Statement

A variant using a key-selection CTE:

```sql
BEGIN;

WITH candidates AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    JOIN delete_lab.customers AS c
        ON c.tenant_id = o.tenant_id
       AND c.customer_id = o.customer_id
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
)
DELETE FROM delete_lab.orders AS o
USING candidates AS d
WHERE o.order_id = d.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

`MATERIALIZED` explicitly requests separate CTE evaluation where supported in modern PostgreSQL; it is **not an approval step**, nor does it lock rows or prevent `customers` from changing outside the transaction. Its main benefit is making candidate selection clear and joining `DELETE` cleanly on target keys.

## 14. PostgreSQL DELETE Does Not Support LIMIT Directly

Some SQL dialects support `DELETE ... LIMIT 100`, but **PostgreSQL does not allow `LIMIT` directly at the end of `DELETE`** that way.

```sql
-- NOT valid PostgreSQL syntax:
-- DELETE FROM delete_lab.orders
-- WHERE status = 'cancelled'
-- LIMIT 100;
```

To delete in batches, select a **batch of keys** in a CTE or subquery and `DELETE` matching those keys.

### 14.1. Deleting at Most Two Orders with a CTE

```sql
BEGIN;

WITH batch AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
    ORDER BY o.order_id
    LIMIT 2
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

Here the CTE selects **at most two IDs**, and `DELETE` removes the matching `orders` rows. `ORDER BY` makes candidate selection predictable on stable data. It does not order `DELETE RETURNING` output itself (PostgreSQL does not guarantee `DELETE RETURNING` row order unless wrapped and sorted in an outer query).

### 14.2. Multi-Worker Batch Pattern: FOR UPDATE SKIP LOCKED

A large cleanup job may run across multiple concurrent workers. To avoid workers contending on the same rows:

```sql
BEGIN;

WITH batch AS MATERIALIZED (
    SELECT o.order_id
    FROM delete_lab.orders AS o
    JOIN delete_lab.customers AS c
        ON c.tenant_id = o.tenant_id
       AND c.customer_id = o.customer_id
    WHERE o.tenant_id = 10
      AND o.status = 'cancelled'
      AND o.cancelled_at <
          TIMESTAMPTZ '2026-10-01 00:00:00+07'
      AND c.account_status = 'closed'
    ORDER BY o.order_id
    LIMIT 100
    FOR UPDATE OF o SKIP LOCKED
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id, o.tenant_id;

ROLLBACK;
```

In this example:

- `ORDER BY o.order_id` establishes predictable candidate order.
- `LIMIT 100` caps batch size.
- `FOR UPDATE OF o` acquires row locks on selected orders.
- `SKIP LOCKED` skips rows currently locked by other transactions instead of blocking.
- `DELETE ... USING batch` deletes only the locked keys.

**Limitations of `SKIP LOCKED`:**

- It intentionally presents an **incomplete/inconsistent view** by skipping locked rows—suitable for worker queues, not financial reporting.
- "Zero rows in this batch" does not prove **no eligible rows remain** if some rows were locked or concurrent transactions are inserting.
- Workers need retry logic, rescan schedules, termination checks, and progress monitoring.
- `FOR UPDATE OF o` does not lock `customers` rows in `c`; if customer statuses can change, add appropriate guards or workflows.
- Batch selection and deletion can still encounter deadlocks in complex workloads; lock ordering, FKs, and triggers remain important.

### 14.3. Batching Is Not Always Needed

Deleting 50 rows from a small table is cleaner in one statement. Batching helps when:

- Deletion volume is very large.
- You need to bound lock duration per transaction.
- You want resumable, pausable progress.
- You need to throttle WAL generation, autovacuum pressure, replica lag, or transaction logs.

However, multiple batches still incur total I/O and take longer overall while allowing concurrent changes between batches. Size batches by benchmarking and understanding consistency requirements.

## 15. Row-Level Security and DELETE Privileges

A multi-tenant application should enforce access control across multiple layers.

### 15.1. DELETE Requires Appropriate Privileges

To run `DELETE`, a role needs `DELETE` privilege on the target table. Columns read in `WHERE`, `USING`, and `RETURNING` can also require `SELECT` privilege per PostgreSQL rules.

Never grant unrestricted `DELETE` to every application account hoping developers always remember tenant predicates. Consider dedicated roles for purge operations.

### 15.2. Row-Level Security (RLS)

PostgreSQL **RLS** restricts which rows a role may affect. For `DELETE`, a policy restricts deletable rows via its `USING` expression.

Structural concept:

```sql
-- Illustrative syntax for a properly designed authorization model:
-- ALTER TABLE delete_lab.orders ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY orders_delete_policy
-- ON delete_lab.orders
-- FOR DELETE
-- TO application_role
-- USING (tenant_id = current_setting('app.tenant_id')::integer);
```

**Do not run this blindly in the lab:** `application_role` and how `app.tenant_id` is set must be separately defined, secured, and tested. An arbitrary custom GUC freely settable by clients **does not constitute trusted authentication**; tenant context must be set through a trusted, authorized boundary.

RLS also has nuances involving table owners, `BYPASSRLS` roles, multiple policies, and read privileges. Never assume every user is constrained identically by RLS without checking role settings and policy definitions.

### 15.3. RLS Does Not Replace Business Filters

RLS restricts which rows are **permitted to be deleted**, but it does not know "only delete orders cancelled before the cutoff whose customers closed their accounts." Business rules still belong in `WHERE`/`USING`.

Conversely, application tenant filters do not replace sound database authorization. These are **two complementary layers**, not substitutes.

## 16. Foreign Keys, ON DELETE CASCADE, and Triggers

### 16.1. FK Behaviors When Deleting Parent Rows

Suppose `orders` is referenced by `order_items`:

| Child Table FK Clause | General Behavior When Parent Row Is Deleted |
|---|---|
| `ON DELETE CASCADE` | Referencing child rows are deleted as well |
| `ON DELETE RESTRICT` | Forbids deleting parent if referencing child rows exist |
| `ON DELETE NO ACTION` (default) | FK violation if references remain at check time; may involve deferred constraints |
| `ON DELETE SET NULL` | Child FK column is set to `NULL` if nullable and configured |
| `ON DELETE SET DEFAULT` | Child FK column is set to its default; must still satisfy FK |

You cannot look solely at `DELETE ... RETURNING` on the parent table to claim how many total rows changed across the database.

### 16.2. Cascade Impact in the Lab

Orders 2 and 3 have line items:

```sql
SELECT
    order_id,
    COUNT(*) AS item_rows
FROM delete_lab.order_items
WHERE order_id IN (2, 3)
GROUP BY order_id
ORDER BY order_id;
```

Result:

| order_id | item_rows |
|---:|---:|
| 2 | 2 |
| 3 | 1 |

If orders 2 and 3 are deleted and committed, **three item rows** are also deleted via `ON DELETE CASCADE`. Dependent rows in `order_flags` are also cascaded.

Therefore, never report the impact as "deleted 2 rows system-wide"; distinguish **2 direct `orders` rows** from cascaded child rows.

### 16.3. Triggers Can Affect Deletion Workflows

`BEFORE DELETE`, `AFTER DELETE` triggers, or application hooks can:

- Write audit logs.
- Reject deletion under specific conditions.
- Synchronize statuses or write related records.
- Alter affected counts if a `BEFORE DELETE` trigger suppresses deletion of a row.

Before running a major purge, inspect all deployed schema dependencies and triggers; never judge impact from the `DELETE` SQL text alone.

### 16.4. Deletion Privileges and Audit Semantics

If auditing is handled by a trigger, verify **which transaction it runs in**, whether it invokes external side effects, and whether audit data persists or rolls back on failure. External actions (such as messages sent to another service) **do not automatically roll back** with the database; never emit "deleted successfully" events before commit in ways that create phantom events.

For integrated systems, consider the **transactional outbox** pattern so events and deletions remain consistent.

## 17. EXPLAIN, Indexes, and Deletion Cost

### 17.1. Columns That May Need Indexes

For our example query:

```sql
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

you can consider an index supporting filtering by tenant, status, and cancellation time:

```sql
CREATE INDEX orders_purge_candidate_idx
ON delete_lab.orders
    (tenant_id, status, cancelled_at, customer_id);
```

`customers`'s primary key on `(tenant_id, customer_id)` already provides an index for composite-key lookups. Optimal indexing still depends on cardinality, `account_status` selectivity, and planner join order.

### 17.2. Partial Index When Only Purging Cancelled Orders

If the table is huge and the purge job only targets `status = 'cancelled'`:

```sql
CREATE INDEX orders_cancelled_purge_idx
ON delete_lab.orders (tenant_id, cancelled_at, customer_id)
WHERE status = 'cancelled';
```

This partial index stores only rows matching the predicate, saving space compared to indexing every status. Still, it adds write overhead and **does not guarantee** the planner will use it for every query.

These two indexes serve overlapping purposes; in production, never create both just because documentation mentions them—measure your workload and avoid redundant indexes.

### 17.3. Indexes on Child Foreign-Key Columns

`order_items.order_id` and `order_flags.order_id` are queried during cascade checks. `order_flags` has primary key `(order_id, flag)`, whose index leads with `order_id`. `order_items` only has a PK on `item_id`, so consider:

```sql
CREATE INDEX order_items_order_id_idx
ON delete_lab.order_items (order_id);
```

PostgreSQL does **not** automatically index child foreign-key columns. When deleting or updating keys on many parent rows, scanning unindexed child tables can be very expensive.

### 17.4. EXPLAIN SELECT Before DELETE

```sql
EXPLAIN
SELECT o.order_id
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

This is a low-risk way to inspect the **candidate selection plan**, though it does not show the full physical delete cost, FK checks, cascades, triggers, and WAL.

### 17.5. EXPLAIN on DELETE Without ANALYZE

```sql
EXPLAIN
DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed';
```

`EXPLAIN` **without `ANALYZE`** prints the estimated plan without executing the deletion. It displays the `Delete on ...` node and how target rows are located.

**Never run `EXPLAIN (ANALYZE, BUFFERS) DELETE ...` carelessly on production**: `ANALYZE` executes the statement and deletes real data. In a lab or controlled environment, if you must measure actual execution, wrap it in a rolled-back transaction and understand that non-transactional external side effects will not roll back.

### 17.6. Deleting Many Rows Does Not Immediately Reclaim Disk Space

PostgreSQL uses MVCC. After `DELETE`, old row versions remain in table pages for older snapshots; autovacuum/`VACUUM` makes that space reusable over time.

Do not expect table files to shrink immediately after deletion. Aggressive space-reclamation commands like `VACUUM FULL` are expensive and take heavy locks; never run them casually after a purge job.

### 17.7. WAL, Replicas, and Batching

A large deletion generates significant WAL, affecting replication lag, autovacuum, index maintenance, and concurrent queries. Batching helps bound lock durations and make incremental progress, though total work remains.

With read replicas, monitor WAL replay lag and read-after-delete behavior; never mistake a lagging replica's query result for the primary failing to delete.

## 18. Partitioning and Deletion Scope

In partitioned tables, `DELETE FROM partitioned_parent WHERE ...` acts on partitions containing matching rows, leveraging partition pruning where possible.

When tables are partitioned by day or month, filtering on the partition key reduces scanned partitions. Still:

- `DELETE` remains a row-by-row operation, distinct from detaching or dropping an entire partition.
- Cascades, triggers, FKs, and privileges still apply.
- `TRUNCATE`/`DETACH PARTITION` cannot replace `DELETE USING` when deleting only a subset of rows within a partition or when per-row auditing is needed.
- A single partition can contain data from multiple tenants; dropping an entire partition because one tenant expired would destroy other tenants' data.

When the requirement is removing **all data for an entire time window** aligned with partition boundaries, partition lifecycle management can be a better strategy—after auditing data boundaries and dependencies.

## 19. DELETE or TRUNCATE?

### 19.1. TRUNCATE Differs Fundamentally

`TRUNCATE` empties a table efficiently for full-table cleanup, yet:

- It has no `WHERE` clause to target one tenant or status.
- It acquires strong locks and handles FKs/`CASCADE` differently from `DELETE`.
- It does not fire **row-level `DELETE` triggers** like `DELETE`; it has separate `TRUNCATE` triggers.
- It has distinct MVCC behavior; verify carefully when concurrent transactions and older snapshots exist.

In PostgreSQL, `TRUNCATE` is transactionally rollbackable, yet **that does not make it safer than `DELETE`** for selective deletions.

### 19.2. Selection Guide

| Requirement | Typical Choice |
|---|---|
| Delete orders by tenant + status + cutoff | `DELETE WHERE` or `DELETE USING` |
| Delete based on presence/absence in reference table | `DELETE USING`, `EXISTS`, `NOT EXISTS` |
| Bulk cleanup in batches by ID | Candidate CTE + `DELETE USING` |
| Empty an entire dedicated staging table | Consider `TRUNCATE` checking locks/FKs/triggers |
| Keep rows hidden from UI | `UPDATE deleted_at` / soft delete |
| Purge an entire partition's data | Partition lifecycle management, not selective row deletion |

Never force one tool onto every deletion scenario.

## 20. Self-Deleting Based on Other Rows in the Same Table

Sometimes you want to delete duplicate versions or older records per key.

### 20.1. Self-Join in USING Requires Distinct Aliases

Example on a hypothetical `dedupe_events` table:

```sql
-- Structural illustration; the practice tables below are created separately.
-- DELETE FROM dedupe_events AS old
-- USING dedupe_events AS newer
-- WHERE old.tenant_id = newer.tenant_id
--   AND old.business_key = newer.business_key
--   AND old.version_no < newer.version_no;
```

One table plays **two roles**: `old` is the **deletion target**, while `newer` is the **comparison source**. Their aliases must differ.

### 20.2. Sample Data

```sql
CREATE TABLE delete_lab.event_versions (
    event_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    business_key TEXT NOT NULL,
    version_no INTEGER NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (tenant_id, business_key, version_no)
);

INSERT INTO delete_lab.event_versions
    (event_id, tenant_id, business_key, version_no, payload)
VALUES
    (100, 10, 'A', 1, 'A v1'),
    (101, 10, 'A', 2, 'A v2'),
    (102, 10, 'A', 3, 'A v3'),
    (103, 10, 'B', 1, 'B v1'),
    (104, 20, 'A', 1, 'Tenant 20 A v1'),
    (105, 20, 'A', 2, 'Tenant 20 A v2');
```

Requirement: for **tenant 10**, keep only the highest `version_no` per `business_key`.

Preview:

```sql
SELECT DISTINCT
    old.event_id,
    old.business_key,
    old.version_no
FROM delete_lab.event_versions AS old
JOIN delete_lab.event_versions AS newer
    ON newer.tenant_id = old.tenant_id
   AND newer.business_key = old.business_key
   AND newer.version_no > old.version_no
WHERE old.tenant_id = 10
ORDER BY old.business_key, old.version_no;
```

Result: events 100 and 101; event 102 is the newest version, and event 103 has no newer version.

Test deletion:

```sql
BEGIN;

DELETE FROM delete_lab.event_versions AS old
USING delete_lab.event_versions AS newer
WHERE old.tenant_id = 10
  AND newer.tenant_id = old.tenant_id
  AND newer.business_key = old.business_key
  AND newer.version_no > old.version_no
RETURNING old.event_id, old.tenant_id,
          old.business_key, old.version_no;

ROLLBACK;
```

**Important:** One `old` row can match multiple `newer` rows, yet is still deleted only once. To avoid deleting the wrong row, confirm whether `version_no` truly defines "latest" in your business rules. If multiple records can share the same version with different payloads, define an explicit tiebreaker/key rule.

### 20.3. Using ROW_NUMBER for Other Deduplication Rules

When keeping "one latest row by timestamp and `event_id`":

```sql
-- Illustrative structure applicable if a table has event_time.
-- WITH ranked AS (
--   SELECT event_id,
--          ROW_NUMBER() OVER (
--            PARTITION BY tenant_id, business_key
--            ORDER BY event_time DESC, event_id DESC
--          ) AS rn
--   FROM event_table
--   WHERE tenant_id = 10
-- )
-- DELETE FROM event_table AS e
-- USING ranked AS r
-- WHERE e.event_id = r.event_id
--   AND e.tenant_id = 10
--   AND r.rn > 1;
```

Include a unique tiebreaker in `ROW_NUMBER`'s `ORDER BY` so which row is kept never depends on arbitrary ordering across tied timestamps.

Never deduplicate in production without checking FKs, event history, and record semantics.

## 21. Deleting Across Multi-Table Relationships

`USING` can list multiple sources, yet every additional table increases the risk of a missing join predicate.

Example target: delete orders in tenant 10 if the customer is closed and the order has flag `expired`:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING
    delete_lab.customers AS c,
    delete_lab.order_flags AS f
WHERE o.tenant_id = 10
  AND c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND c.account_status = 'closed'
  AND f.order_id = o.order_id
  AND f.flag = 'expired'
  AND o.status = 'cancelled'
RETURNING o.order_id;

ROLLBACK;
```

Join conditions cover both **tenant/customer** and **order_id/flag**. Omitting `f.order_id = o.order_id` lets any single `expired` flag anywhere in `order_flags` match every order via a Cartesian product.

### 21.1. Referencing Multiple Tables Does Not Delete Multiple Tables

The statement above names only **`orders`** as the target. `customers` and `order_flags` are lookup sources; `order_flags` only loses rows via FK cascade when parent `orders` rows are deleted.

If you need to delete directly from two tables **without FK CASCADE**, run separate statements in dependency order inside one transaction, or adjust storage design. Never assume `USING a, b` deletes both `a` and `b`.

### 21.2. Subqueries in USING

`USING` also accepts a derived table to clarify logic:

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING (
    SELECT tenant_id, customer_id
    FROM delete_lab.customers
    WHERE tenant_id = 10
      AND account_status = 'closed'
) AS closed_customers
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND closed_customers.tenant_id = o.tenant_id
  AND closed_customers.customer_id = o.customer_id
RETURNING o.order_id;

ROLLBACK;
```

A derived table makes the lookup set readable, yet **does not** force PostgreSQL to execute the subquery first and `DELETE` second procedurally. Reason about result semantics and actual execution plans, not SQL clause order.

## 22. Error Handling and Results in Java/JDBC

In Java applications, never concatenate tenant, status, or cutoff parameters into SQL strings. Use `PreparedStatement` to bind values.

### 22.1. Example DELETE USING with RETURNING

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderCleanupRepository {
    public List<Long> deleteEligibleOrders(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        if (cutoff == null) {
            throw new IllegalArgumentException("cutoff is required");
        }

        String sql = """
            DELETE FROM delete_lab.orders AS o
            USING delete_lab.customers AS c
            WHERE c.tenant_id = o.tenant_id
              AND c.customer_id = o.customer_id
              AND o.tenant_id = ?
              AND o.status = 'cancelled'
              AND o.cancelled_at < CAST(? AS timestamptz)
              AND c.account_status = 'closed'
            RETURNING o.order_id
            """;

        List<Long> ids = new ArrayList<>();
        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setInt(1, tenantId);
            ps.setObject(2, cutoff);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("order_id"));
                }
            }
        }
        return ids;
    }
}
```

This example uses Java text blocks (Java 15+) and a JDBC driver supporting `OffsetDateTime`. This method **actually deletes** data; returning a list of IDs does not make it a "dry run." Production applications must wrap it in proper approval, transaction, and logging flows.

### 22.2. Commit, Rollback, and Exceptions

Service-layer transaction skeleton:

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.List;

public final class OrderCleanupService {
    private final OrderCleanupRepository repository =
        new OrderCleanupRepository();

    public List<Long> run(
            Connection connection,
            int tenantId,
            OffsetDateTime cutoff
    ) throws SQLException {
        boolean oldAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);
        try {
            List<Long> ids =
                repository.deleteEligibleOrders(
                    connection, tenantId, cutoff
                );

            // In production: enforce row-count threshold,
            // write audit/outbox, and run extra guards before commit.
            if (ids.size() > 1000) {
                throw new IllegalStateException(
                    "Row count exceeds allowed threshold"
                );
            }

            connection.commit();
            return ids;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        } finally {
            connection.setAutoCommit(oldAutoCommit);
        }
    }
}
```

**Code-sample caveat:** for connections managed by a pool or framework, transactions are normally owned by the transaction manager. Never toggle `autoCommit` or call `commit` manually on framework-managed connections. This sample merely illustrates rolling back and checking row counts **before commit**; restoring connection state in `finally` also requires proper pool/error handling in real systems.

### 22.3. Distinguishing Foreign Key and Other Errors

A deletion can fail due to:

- `23503` — `foreign_key_violation`: child table FK blocks deletion.
- `42501` — `insufficient_privilege`: role lacks permissions.
- `40001` — `serialization_failure`: transaction under strict isolation requires retry.
- `40P01` — `deadlock_detected`: deadlock, typically requiring a full-transaction retry under a safe policy.

Never treat every error as "order not found" or "no rows to delete." `DELETE 0` can mean zero eligible candidates; an exception is an entirely different state.

## 23. Monitoring a Scheduled Deletion Job

A reliable cleanup job typically records at least:

| Field | Meaning |
|---|---|
| `job_id` | Run identifier |
| `tenant_id` | Tenant scope |
| `cutoff` | Fixed time boundary for the run |
| `filter_version` | Deletion rule version |
| `candidate_count` | Pre-deletion candidate count |
| `deleted_count` | Target rows actually deleted |
| `deleted_ids` or checksum/audit log | Reconciliation evidence |
| `started_at` / `finished_at` | Execution timestamps |
| `transaction_status` | Committed, rolled back, failed |
| `dependent_changes` | Measured/logged dependent effects if needed |

### 23.1. Set Safety Thresholds

Examples:

- Cap each batch at 100 or 1,000 rows depending on workload.
- Abort if `candidate_count` exceeds the expected ceiling.
- Process only allowlisted tenants.
- Pause during active incidents or when backups are unhealthy.
- Halt and alert on sudden spikes in deleted row counts.

These are **operational safeguards**, not built-in features of `DELETE USING`. Build them into your job orchestration, transactions, and monitoring.

### 23.2. Multi-Worker Deletion Requires Job Idempotency

If a batch commits but the worker drops the connection before receiving the response, a retry may see **0 rows** because they are already gone. That is not necessarily an error if the job is designed to be **safely re-runnable**.

However, retries must never use a sliding cutoff or changed filter that unexpectedly deletes additional data. Persist the **fixed cutoff and job scope**, mark completed batches, and reconcile audits properly.

### 23.3. Backups Must Be Restore-Tested

Merely "having a backup file" does not prove recoverability:

- Does the backup cover the needed tables and point in time?
- Is WAL/point-in-time recovery available if needed?
- Are encryption keys and restore permissions available?
- Has restoration been tested on the target schema, extensions, and version?
- Are there compliance rules forbidding restoring permanently erased user data?

These questions are not answered by SQL `DELETE`, yet they are mandatory for sensitive or high-stakes data deletion workflows.

## 24. Common Misconceptions

**1. "`USING` deletes both tables."** False. Only the table after `DELETE FROM` is the direct target; secondary effects occur only via FKs/triggers.

**2. "`DELETE USING` without `WHERE` is safe because a lookup table is listed."** False. Missing join/filter predicates create a Cartesian product and delete far more rows.

**3. "Having `tenant_id` on `customers` is enough."** False if the `JOIN` omits `orders.tenant_id` or lacks proper tenant filtering.

**4. "`customer_id` is always globally unique."** Not when the schema defines a composite `(tenant_id, customer_id)` key.

**5. "If `SELECT JOIN` returns 3 rows, `DELETE` will delete 3 rows."** False when one target row matches multiple `USING` rows.

**6. "`RETURNING` emits one row per matching `USING` row."** False. It emits once per deleted target row.

**7. "`COUNT(DISTINCT order_id)` in `SELECT` also counts cascaded child rows."** False. It counts distinct order IDs only.

**8. "Running `SELECT` before `DELETE` prevents concurrent changes."** No. Snapshots can change between statements.

**9. "`BEGIN` freezes all data automatically even in `READ COMMITTED`."** No. Each statement still gets a fresh snapshot.

**10. "`FOR UPDATE OF orders` locks all `USING` tables too."** No. `OF` limits row locking to the specified table(s).

**11. "`SKIP LOCKED` guarantees the batch saw every candidate."** No. It skips rows locked by other transactions.

**12. "`DELETE ... LIMIT 100` is valid PostgreSQL syntax."** No. Select candidate keys in a CTE and delete by key.

**13. "`ORDER BY` in a CTE guarantees `DELETE RETURNING` row order."** Not guaranteed. Sort in an outer query or presentation layer if order matters.

**14. "`ON DELETE CASCADE` does not expand impact scope."** False. It deletes referencing rows in child tables.

**15. "`TRUNCATE` is identical to `DELETE` without `WHERE`."** No. Locking, triggers, FKs, MVCC, and execution mechanisms differ.

**16. "`DELETE` immediately shrinks table files on disk."** No. PostgreSQL MVCC requires `VACUUM`/space reuse.

**17. "`EXPLAIN ANALYZE DELETE` does not actually delete."** False. `ANALYZE` executes the statement.

**18. "`SELECT DISTINCT` after a join fixes every impact calculation."** No. It only deduplicates the `SELECT` projection, not a broken deletion filter.

**19. "`DELETE` returning 0 rows proves no matching data exists."** Not necessarily—RLS, roles, locks/batches, filters, or snapshot changes may explain it; check context.

**20. "Using `OR` without parentheses is fine because `tenant_id` comes first."** False. `AND` binds tighter than `OR`.

**21. "`WHERE status <> 'paid'` automatically includes `NULL`."** No; comparisons with `NULL` yield `UNKNOWN` on nullable columns.

**22. "You can `ROLLBACK` after `COMMIT` to recover."** No. You must use a prior backup/recovery plan.

**23. "Auditing a few columns is a full backup."** Not if child tables, metadata, or full history must be restored.

**24. "Filtering by `created_at` equals filtering by `cancelled_at`."** No. Those two events can be far apart.

**25. "RLS handles all business rules automatically."** No. Eligibility rules and authorization policies are separate layers.

**26. "Adding more indexes always speeds up `DELETE`."** No. Indexes add write maintenance overhead and can become redundant.

**27. "Deleting parent rows is fast even if child tables are huge."** No. FK checks and cascades can be slow if child FK columns lack indexes.

**28. "`WHERE IN (2, 3)` is enough even when the API must isolate tenants."** No. Tenant and authorization guards are still required.

**29. "`DELETE USING` is the only way to express existence conditions."** No. `EXISTS` is often clearer.

**30. "`NOT EXISTS` can be rewritten using an inner `USING` join with an empty-match assumption."** No. Anti-existence requires proper negation logic.

## 25. Practice Exercises with Guided Answers

### Exercise 1 — Translate Requirements into Conditions

**Requirement:** delete orders in tenant 10, cancelled before 2026-10-01 (+07), whose customer in the same tenant has closed their account.

**Answer:** key predicates:

```sql
o.tenant_id = 10
AND o.status = 'cancelled'
AND o.cancelled_at <
    TIMESTAMPTZ '2026-10-01 00:00:00+07'
AND c.tenant_id = o.tenant_id
AND c.customer_id = o.customer_id
AND c.account_status = 'closed'
```

On the initial dataset, only orders **2 and 3** qualify.

### Exercise 2 — Preview the List

**Requirement:** select IDs and customer names prior to deletion.

**Answer:**

```sql
SELECT o.order_id, c.customer_name
FROM delete_lab.orders AS o
JOIN delete_lab.customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
ORDER BY o.order_id;
```

### Exercise 3 — Write DELETE USING

**Requirement:** delete the exact scope from Exercise 2 and return IDs.

**Answer (run only inside a lab transaction):**

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
USING delete_lab.customers AS c
WHERE c.tenant_id = o.tenant_id
  AND c.customer_id = o.customer_id
  AND o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND c.account_status = 'closed'
RETURNING o.order_id;

ROLLBACK;
```

### Exercise 4 — Catching a Missing Tenant Key

**Scenario:** `customers` has customer 101 in tenant 10 (active) and tenant 20 (closed). The `JOIN` uses only `customer_id`.

**Answer:** tenant 10 orders for customer 101 can wrongly match tenant 20's closed status. Also join on:

```sql
AND c.tenant_id = o.tenant_id
```

and enforce target scope with `o.tenant_id = 10`.

### Exercise 5 — Fan-Out

**Question:** order 2 has two flags `expired` and `reviewed`. When `USING order_flags` matches both flags, how many times does `RETURNING order_id` emit order 2?

**Answer:** **Once**, because the target row is deleted once even though the join had two rows.

### Exercise 6 — Does COUNT(*) Equal Expected Orders?

**Answer:** No, if the `USING` table matches multiple rows per order. Use:

```sql
SELECT COUNT(DISTINCT o.order_id)
FROM delete_lab.orders AS o
JOIN delete_lab.order_flags AS f
    ON f.order_id = o.order_id
WHERE o.tenant_id = 10
  AND f.flag IN ('expired', 'reviewed');
```

### Exercise 7 — Write WHERE EXISTS

**Requirement:** delete old cancelled orders in tenant 10 if a closed customer exists in the same tenant.

**Answer:**

```sql
BEGIN;

DELETE FROM delete_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.status = 'cancelled'
  AND o.cancelled_at <
      TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND EXISTS (
      SELECT 1
      FROM delete_lab.customers AS c
      WHERE c.tenant_id = o.tenant_id
        AND c.customer_id = o.customer_id
        AND c.account_status = 'closed'
  )
RETURNING o.order_id;

ROLLBACK;
```

### Exercise 8 — Anti-Join NOT EXISTS

**Requirement:** delete tenant 10 staging rows whose code is missing from `valid_external_codes` for that tenant.

**Answer:**

```sql
BEGIN;

DELETE FROM delete_lab.import_candidates AS i
WHERE i.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM delete_lab.valid_external_codes AS v
      WHERE v.tenant_id = i.tenant_id
        AND v.external_code = i.external_code
  )
RETURNING i.external_code;

ROLLBACK;
```

Result is only `X-99`.

### Exercise 9 — Spotting the AND/OR Bug

**Question:** does `tenant_id = 10 AND status = 'pending' OR status = 'cancelled'` delete cancelled orders in tenant 20?

**Answer:** **Yes, it can**, because the `OR status = 'cancelled'` branch is unrestricted by tenant. Fix to:

```sql
tenant_id = 10
AND status IN ('pending', 'cancelled')
```

### Exercise 10 — Purge 100 Rows

**Requirement:** PostgreSQL lacks `DELETE LIMIT`. Use a CTE to select up to 100 rows.

**Answer:**

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM delete_lab.orders
    WHERE tenant_id = 10
      AND status = 'cancelled'
    ORDER BY order_id
    LIMIT 100
)
DELETE FROM delete_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
  AND o.tenant_id = 10
RETURNING o.order_id;

ROLLBACK;
```

When multiple workers run concurrently, consider `FOR UPDATE SKIP LOCKED` and retries.

### Exercise 11 — How Many Rows Are Affected by Cascade?

**Question:** deleting orders 2 and 3 in the lab triggers `ON DELETE CASCADE` on `order_items`. If those orders have 2 and 1 item rows respectively, how many rows does `DELETE orders RETURNING` emit? How many item rows are cascade-deleted?

**Answer:** **2** `orders` rows in `RETURNING`; **3** `order_items` rows cascade-deleted. `order_flags` also has dependent rows that cascade accordingly.

### Exercise 12 — DELETE RETURNING and Audit

**Requirement:** get the deleted row count and list of IDs in the same statement.

**Answer:**

```sql
BEGIN;

WITH removed AS (
    DELETE FROM delete_lab.orders AS o
    WHERE o.tenant_id = 10
      AND o.order_id IN (2, 3)
    RETURNING o.order_id
)
SELECT
    COUNT(*) AS deleted_count,
    ARRAY_AGG(order_id ORDER BY order_id) AS deleted_ids
FROM removed;

ROLLBACK;
```

Result is `deleted_count = 2` and `deleted_ids = {2,3}` on intact data. If zero rows match, `COUNT(*) = 0` and `ARRAY_AGG` returns `NULL` unless wrapped with `COALESCE`.

### Exercise 13 — Is SELECT Before DELETE Strictly Safe?

**Answer:** No. Another transaction can commit between statements. Consider locking candidate rows, freezing an ID list, keeping guards in `DELETE`, using appropriate isolation, and controlling transactions. Wrapping `BEGIN` in `READ COMMITTED` alone does not freeze snapshots.

### Exercise 14 — EXPLAIN ANALYZE

**Question:** Does `EXPLAIN (ANALYZE) DELETE FROM orders ...` delete real data?

**Answer:** **Yes**, because `ANALYZE` executes the statement. To view the estimated plan only, run `EXPLAIN DELETE ...` without `ANALYZE`. To measure execution in a lab, wrap in a rolled-back transaction and account for non-transactional side effects.

### Exercise 15 — Deleting Old Versions via Self-Join

**Requirement:** in tenant 10, keep only the highest `version_no` per `business_key`.

**Answer:**

```sql
BEGIN;

DELETE FROM delete_lab.event_versions AS old
USING delete_lab.event_versions AS newer
WHERE old.tenant_id = 10
  AND newer.tenant_id = old.tenant_id
  AND newer.business_key = old.business_key
  AND newer.version_no > old.version_no
RETURNING old.event_id, old.business_key, old.version_no;

ROLLBACK;
```

Test deletion removes events **100, 101** without touching tenant 20 events.

### Exercise 16 — Deletion State and Soft Delete

**Question:** A table requires 5-year history retention while immediately hiding cancelled orders from the UI. Should physical `DELETE` be used by default?

**Answer:** That cannot be decided from SQL alone. If history must be retained, use `deleted_at`/`archived_at` columns with proper query filters and retention policies. If data must eventually be purged per retention policy, schedule a subsequent purge. Keeping personal data "hidden" does not automatically satisfy all legal erasure requirements.

### Exercise 17 — Scope by Which Timestamp?

**Requirement:** delete orders **cancelled before Oct 1**, not orders **created before Oct 1**.

**Answer:** The primary filter must use `cancelled_at` alongside status/business predicates, not `created_at`.

### Exercise 18 — Returning 0 Rows

**Question:** `DELETE ... RETURNING` returns an empty set. Can you conclude there are no old cancelled orders in the system?

**Answer:** Insufficient evidence to conclude that. There may be no rows matching **all current predicates and privileges**, tenant filtering may exclude them, snapshots may differ, or rows may have already been deleted. If `SKIP LOCKED` was used, locked rows may simply have been skipped.

### Exercise 19 — When to Delete Child Tables First?

If the FK from `order_items` to `orders` uses `ON DELETE NO ACTION` instead of `CASCADE` and items exist, deleting an order raises an FK violation.

**Answer:** Decide business policy: forbid deleting orders that have items, delete children before the parent in the same transaction, or intentionally choose `ON DELETE CASCADE` when appropriate. Never switch an FK to `CASCADE` solely to silence an error if line-item history must be protected.

### Exercise 20 — Why Require a Tenant Predicate Even When ID Is a Global PK?

**Answer:** Global PK `order_id` uniquely locates a row, yet `tenant_id = :authorizedTenant` remains a vital **authorization/business scope guard**. A user must never be able to delete another tenant's order simply by guessing or submitting its `order_id`.

## 26. Pre-COMMIT Checklist for DELETE USING

Before any major purge job, check in order:

1. **Right target:** is the table after `DELETE FROM` the intended deletion target?
2. **Right tenant:** are explicit scope filters and tenant `JOIN` predicates present?
3. **Right status:** which statuses are eligible, and do retention/recovery rules apply?
4. **Right timestamp:** filtering by `created_at`, `cancelled_at`, `paid_at`, or another timestamp? Using proper timezone and bounds?
5. **Right JOIN keys:** do all `USING` tables have complete join predicates, avoiding Cartesian products?
6. **Right AND/OR:** are parentheses or `IN` used so tenant limits bind every branch?
7. **Previewed:** did `SELECT` list all IDs and expected row counts?
8. **Fan-out checked:** is `JOIN` `COUNT(*)` inflating counts for one target ID?
9. **Concurrency handled:** do snapshots, row locks, batch IDs, and guards meet consistency needs?
10. **FKs/triggers checked:** what child data gets deleted/updated, and what could block deletion?
11. **Audits and backups:** are logging and recovery paths verified before mistakes happen?
12. **Thresholds:** will unexpected or excessive row counts trigger rollback?
13. **Proper batching:** for large tables, are key/`ORDER BY`, batch size, and `SKIP LOCKED` configured correctly?
14. **Least privilege:** are roles, RLS, and approvals appropriate?
15. **Performance measured:** have JOIN/FK indexes, `EXPLAIN`, WAL, locks, autovacuum, and replica lag been evaluated?
16. **In-transaction check:** does `RETURNING` match the target set before `COMMIT`?
17. **Post-run verification:** remaining counts, audits, job metrics, error logs, and recovery readiness?
18. **No post-COMMIT ROLLBACK illusion:** do operators understand transaction boundaries?

## 27. Summary

**`DELETE ... USING` is PostgreSQL's syntax for deleting rows from a table using predicates involving other data sources.** It does not delete tables listed in `USING`, nor does it automatically enforce tenant or status boundaries.

Key principles:

- **The target table follows `DELETE FROM`; `USING` tables only assist in selecting rows to delete.**
- **Join predicates must be complete**, especially when business keys are unique only within a tenant. Never let one tenant's records match another tenant's rows.
- **Preview with `SELECT`**, remembering that one-to-many joins can emit multiple rows per target; use `COUNT(DISTINCT target_pk)` or `EXISTS` to count target rows accurately.
- **Use `RETURNING`** to confirm which target rows were actually deleted, and **transactions + `ROLLBACK`** to test before committing.
- **Do not overlook indirect impacts:** `ON DELETE CASCADE`, triggers, foreign keys, RLS, WAL, and MVCC.
- **A preview `SELECT` does not freeze the dataset.** For strict accuracy or concurrent jobs, consider explicit key lists, row locks, isolation, and guards inside `DELETE`.
- **PostgreSQL has no direct `DELETE ... LIMIT`**; select a key batch in a CTE and `DELETE ... USING` against it, optionally with `FOR UPDATE SKIP LOCKED`.
- **`EXPLAIN ANALYZE DELETE` actually deletes rows**, so use it only under strict control; plain `EXPLAIN` without `ANALYZE` inspects the estimated plan safely.

**Final rule:** before deleting, always answer **"which rows are deleted, why are they eligible, which rows are guaranteed untouched, and what other records are affected?"** Execute SQL only after those answers are encoded as predicates, previewed, bounded in a transaction, and made reconcilable.

### Official PostgreSQL Documentation

- [DELETE — USING, WHERE, and RETURNING syntax](https://www.postgresql.org/docs/current/sql-delete.html).
- [WITH Queries and Data-Modifying Statements in WITH](https://www.postgresql.org/docs/current/queries-with.html).
- [Explicit Locking and FOR UPDATE / SKIP LOCKED](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Foreign Keys and ON DELETE](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html).
