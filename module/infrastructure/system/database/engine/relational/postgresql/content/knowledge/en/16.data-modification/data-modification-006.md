# RETURNING and Capturing Modified Results in a Single PostgreSQL Statement

## 1. The Problem: After Writing Data, How Do You Get the Results?

A data-modification operation is not merely about "success or failure." Applications also frequently need to know **which rows changed** and **what their final values are**:

- Create a customer and retrieve the PostgreSQL-generated `customer_id`.
- Create an order and retrieve the order number, creation timestamp, and default status.
- Deduct inventory and know the **remaining stock**, only when sufficient stock exists.
- Transition an order's status and know **which orders actually transitioned**.
- Delete records and capture the deleted record contents to return via an API or move into an archive table.
- Insert or update by unique key (*upsert*) and receive the data actually written.
- Capture affected rows to write an audit log in **the same SQL statement**.

PostgreSQL provides the **`RETURNING`** clause for data-modifying statements:

```sql
INSERT INTO ...
VALUES (...)
RETURNING ...;

UPDATE ...
SET ...
WHERE ...
RETURNING ...;

DELETE FROM ...
WHERE ...
RETURNING ...;
```

With `RETURNING`, the statement still modifies data while simultaneously returning a **result set** containing the rows actually affected by the operation.

Short example:

```sql
INSERT INTO app_customers(email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id, email;
```

In the example above, `app_customers` is an illustrative table name. If the table exists and the `INSERT` succeeds, you immediately receive the generated ID without guessing with `MAX(id)` or issuing a second read query.

**Core idea:** `RETURNING` turns "write then ask again" into "write and receive the modified values" in a single SQL operation.

### Learning Objectives

After this lesson, you will understand and apply:

1. `RETURNING` syntax after `INSERT`, `UPDATE`, and `DELETE`.
2. The difference between **affected row count** and **returned rows**.
3. Retrieving `IDENTITY`, `DEFAULT`, timestamps, and computed columns.
4. Accurately capturing results from `UPDATE ... WHERE ...` with business conditions.
5. How `INSERT ... ON CONFLICT ... RETURNING` handles inserted, updated, and unchanged rows.
6. Using `WITH ... RETURNING` to pass data across DML steps in **one statement**.
7. Limitations of `RETURNING` regarding transactions, concurrency, triggers, and PostgreSQL versions.
8. Consuming `RETURNING` from JDBC/Java, including when zero rows are returned.
9. Common mistakes: guessing IDs, non-atomic re-reads, misunderstanding upserts, column leaks, and uncontrolled `RETURNING *`.
10. Complete practice exercises, from order creation to stock deduction and logging.

## 2. RETURNING Differs from a Follow-Up SELECT

Without `RETURNING`, an application might write:

```text
1. INSERT customer.
2. SELECT to find the new key.
3. Use the new key to create related records.
```

This adds an extra round trip between application and database. If the `SELECT` filters by a non-unique condition or reads at a different moment, it may not return the row just written.

A serious bug:

```sql
-- Unsafe in systems with concurrent writers:
SELECT MAX(customer_id) FROM customers;
```

The largest value may belong to another transaction. Even with sequences, IDs do not necessarily advance strictly in commit order.

With `RETURNING`:

```sql
INSERT INTO customers(email, full_name)
VALUES ('an@example.test', 'An')
RETURNING customer_id;
```

The returned ID belongs to **the exact row the `INSERT` affected**. No guessing from other rows is needed.

### 2.1. RETURNING Is Not a Standalone SELECT

Expressions in `RETURNING` are evaluated in the corresponding DML context. The output is not "the whole table after writing," but only **the rows touched by the modification**.

| Statement | Rows That Can Appear in RETURNING |
|---|---|
| `INSERT ... RETURNING` | Rows actually inserted |
| `UPDATE ... RETURNING` | Rows actually updated |
| `DELETE ... RETURNING` | Rows actually deleted |
| `INSERT ... ON CONFLICT DO NOTHING RETURNING` | Newly inserted rows only; skipped rows do not appear |
| `INSERT ... ON CONFLICT DO UPDATE RETURNING` | Rows inserted or actually updated |

If `WHERE` matches no rows, `UPDATE ... RETURNING` or `DELETE ... RETURNING` returns **0 rows**. That is the normal result when no eligible targets match.

### 2.2. Does RETURNING Guarantee the Transaction Is Committed?

**No.** A DML statement can return data inside an open transaction that later calls `ROLLBACK`. `RETURNING` reflects what the statement did inside the transaction, **not a guarantee that the transaction committed durably**.

## 3. Preparing the Practice Environment

We build a small lab schema for an order system. Examples are illustrative; use a **test database**. Never run delete/modify scripts on production.

### 3.1. Customers and Inventory

```sql
CREATE SCHEMA IF NOT EXISTS returning203;

CREATE TABLE returning203.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE returning203.inventory (
    sku text PRIMARY KEY,
    product_name text NOT NULL,
    stock integer NOT NULL CHECK (stock >= 0),
    unit_price numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

`GENERATED ALWAYS AS IDENTITY` delegates key allocation to a PostgreSQL identity sequence. `DEFAULT now()` records the transaction start time; if you want wall-clock time at expression evaluation, consider `clock_timestamp()` with its own semantics.

### 3.2. Orders and Inventory Movement Log

```sql
CREATE TABLE returning203.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES returning203.customers(customer_id),
    sku text NOT NULL
        REFERENCES returning203.inventory(sku),
    quantity integer NOT NULL CHECK (quantity > 0),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status text NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    client_request_id text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE returning203.inventory_movements (
    movement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL REFERENCES returning203.inventory(sku),
    stock_delta integer NOT NULL CHECK (stock_delta <> 0),
    reason text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now()
);
```

`client_request_id` is a client-generated business key distinguishing requests. A `UNIQUE` constraint helps the database detect duplicate requests, yet **retry handling and stock updates must be designed together**; `UNIQUE` alone does not make an entire workflow idempotent.

### 3.3. Load Baseline Data

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES
    ('an@example.test', 'An'),
    ('binh@example.test', 'Binh');

INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('BOOK-PG', 'PostgreSQL Book', 5, 120000.00),
    ('KEYBOARD', 'Keyboard', 2, 350000.00),
    ('MOUSE', 'Mouse', 0, 150000.00);
```

Verify baseline data:

```sql
SELECT customer_id, email, full_name
FROM returning203.customers
ORDER BY customer_id;

SELECT sku, stock, unit_price
FROM returning203.inventory
ORDER BY sku;
```

**Lab convention:** the following examples are generally **independent scenarios** starting from this initial state. Running an `UPDATE` or `DELETE` sequentially can change later examples' results. Wrap runs in `BEGIN ... ROLLBACK` when just observing, or recreate the fixture cleanly in a fresh test environment. Never assume a fixed numeric generated ID without reading the actual returned value.

## 4. INSERT ... RETURNING: Receiving New Keys and Saved Data

### 4.1. Single Row

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('chi@example.test', 'Chi')
RETURNING
    customer_id,
    email,
    full_name,
    created_at;
```

Illustrative result:

| customer_id | email | full_name | created_at |
|---:|---|---|---|
| 3 | chi@example.test | Chi | Creation timestamp recorded by DB |

The number `3` is **purely illustrative** on a fresh lab database that has consumed no other identities. In real environments, read the actual returned `customer_id` rather than adding 1 to a previous ID.

Notable values:

- `customer_id` was generated by identity.
- `created_at` came from `DEFAULT now()`.
- `email` and `full_name` are the stored values.

The application can immediately use the returned ID to create related resources without querying back by email.

### 4.2. RETURNING Accepts Expressions

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('dung@example.test', 'Dung')
RETURNING
    customer_id,
    lower(email) AS normalized_email,
    full_name,
    created_at::date AS created_date;
```

`RETURNING` is not limited to plain column names: it supports value-returning expressions such as `lower(email)` and casts like `created_at::date`.

**Note:** `created_at::date` depends on how the session time zone interprets a `timestamptz`. If an API must display dates in a specific time zone, convert time zones explicitly.

### 4.3. Multiple Rows

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES
    ('lan@example.test', 'Lan'),
    ('minh@example.test', 'Minh')
RETURNING
    customer_id,
    email,
    full_name;
```

The statement returns **two rows** if both insert successfully.

Never assume `RETURNING` row order is guaranteed across all SQL variants and plans. If deterministic ordering is required, sort in the reading layer or wrap the DML in a CTE and run `SELECT ... ORDER BY`.

### 4.4. Avoid RETURNING * in Every API

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('phuc@example.test', 'Phuc')
RETURNING *;
```

This is valid syntax and handy for learning or debugging. In production APIs, list the exact needed columns:

```sql
RETURNING customer_id, email, created_at;
```

Reasons: avoid leaking sensitive columns, reduce network payload, and prevent API contracts from breaking unexpectedly when new columns are added.

## 5. INSERT ... DEFAULT VALUES RETURNING

Some tables allow inserting rows without supplying any columns because every required column has an identity or default.

In the lab schema, create a test table:

```sql
CREATE TABLE returning203.job_tokens (
    token_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    token_state text NOT NULL DEFAULT 'CREATED',
    generated_at timestamptz NOT NULL DEFAULT now()
);
```

Insert using defaults only:

```sql
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id, token_state, generated_at;
```

Illustrative output:

```text
token_id = <actual ID issued by PostgreSQL>
token_state = CREATED
generated_at = <default timestamp>
```

On `customers`, you **cannot** use `DEFAULT VALUES` because `email` and `full_name` are required with no defaults; `RETURNING` never bypasses `NOT NULL` or other constraints.

### 5.1. RETURNING and Sequences

Identity relies on sequences. In PostgreSQL, allocated sequence values **are not necessarily reclaimed on rollback**. Therefore:

- IDs can have gaps.
- A higher ID does not prove a transaction committed later than another.
- Never estimate row counts via `MAX(id) - MIN(id) + 1`.
- Use `RETURNING` to obtain the exact ID assigned to your statement's row.

## 6. INSERT ... SELECT RETURNING

You do not have to insert from a `VALUES` list. You can insert from a query:

```sql
CREATE TABLE returning203.signup_queue (
    queue_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    email text NOT NULL,
    queued_at timestamptz NOT NULL DEFAULT now()
);
```

Example queuing customers with test-domain emails:

```sql
INSERT INTO returning203.signup_queue(customer_id, email)
SELECT c.customer_id, c.email
FROM returning203.customers AS c
WHERE c.email LIKE '%@example.test'
RETURNING queue_id, customer_id, email;
```

The result contains the rows **inserted into `signup_queue`**, with the target table's new `queue_id`. It is not the entire source `SELECT` dataset, and includes only the columns listed in `RETURNING`.

### 6.1. Returning Ordered Results

If you need a sorted list:

```sql
WITH inserted AS (
    INSERT INTO returning203.signup_queue(customer_id, email)
    SELECT c.customer_id, c.email
    FROM returning203.customers AS c
    WHERE c.email = 'an@example.test'
    RETURNING queue_id, customer_id, email
)
SELECT *
FROM inserted
ORDER BY queue_id;
```

This is **one SQL statement**: the CTE runs the `INSERT` and exposes its `RETURNING` set; the outer `SELECT` formats and sorts the output.

**Note:** re-running the `signup_queue` examples can insert duplicate customer entries because this demo schema does not define `UNIQUE(customer_id)`. Real systems need business-appropriate uniqueness and idempotency policies.

## 7. UPDATE ... RETURNING: Retrieving Post-Modification Values

Example reducing the stored price of the PostgreSQL book:

```sql
UPDATE returning203.inventory AS i
SET
    unit_price = 110000.00,
    updated_at = now()
WHERE i.sku = 'BOOK-PG'
RETURNING
    i.sku,
    i.product_name,
    i.unit_price AS new_price,
    i.updated_at;
```

If one matching SKU row is found, `RETURNING` returns its **post-UPDATE** values. If no such SKU exists, it returns 0 rows.

### 7.1. No Need to Re-SELECT Price After UPDATE

The two-statement pattern:

```sql
UPDATE returning203.inventory
SET unit_price = 110000
WHERE sku = 'BOOK-PG';

SELECT unit_price
FROM returning203.inventory
WHERE sku = 'BOOK-PG';
```

can work under proper transaction control, yet adds an extra round trip. In concurrent systems, a separate `SELECT` after committing the first transaction may observe newer changes from another transaction, rather than proving what **your `UPDATE` just wrote**.

When you only need the values your `UPDATE` produced, `UPDATE ... RETURNING` is direct and concise.

### 7.2. Multi-Row UPDATE

```sql
UPDATE returning203.inventory AS i
SET
    unit_price = ROUND(i.unit_price * 1.05, 2),
    updated_at = now()
WHERE i.stock > 0
RETURNING
    i.sku,
    i.stock,
    i.unit_price AS increased_price;
```

This can return multiple rows, one per updated inventory row. Never assume the returned order matches disk order or primary key order.

## 8. Conditional Business UPDATEs and Atomicity

An even more critical scenario than price updates is **deducting stock while verifying sufficient inventory**.

Suppose SKU `BOOK-PG` has `stock = 5` and a user requests 2 units. Write a conditional `UPDATE`:

```sql
UPDATE returning203.inventory AS i
SET
    stock = i.stock - 2,
    updated_at = now()
WHERE i.sku = 'BOOK-PG'
  AND i.stock >= 2
RETURNING
    i.sku,
    i.stock AS remaining_stock,
    i.unit_price;
```

If enough stock exists, PostgreSQL updates the row and returns `remaining_stock = 3` from the initial lab state.

If stock is insufficient or the SKU does not exist, **no row is updated**, so `RETURNING` yields an empty set.

### 8.1. Why Put the Condition Inside UPDATE?

A common unsafe pattern without proper locking/transactions:

```text
Request A: SELECT stock -> 5
Request B: SELECT stock -> 5
Request A: subtract 4
Request B: subtract 4
```

Both requests may think "there are at least 4," even though total inventory cannot serve both.

With:

```sql
UPDATE ... SET stock = stock - 4
WHERE sku = 'BOOK-PG' AND stock >= 4
RETURNING stock;
```

the condition check and row modification occur in **a single statement**. PostgreSQL serializes concurrent updates on the same row using row locks and MVCC; under `READ COMMITTED`, a waiting `UPDATE` re-evaluates the predicate against the newly committed row version before deciding whether to update.

Hence two competing transactions each trying to deduct 4 from 5 items cannot both succeed under this conditional update pattern.

### 8.2. Interpreting 0 Rows

Zero `RETURNING` rows can mean:

- The SKU does not exist.
- The SKU exists, yet stock is below the requested quantity.
- Another `WHERE` condition failed.
- Another transaction modified the row concurrently so the predicate no longer holds.

Do not automatically return an "out of stock" error on `0 rows` if the API must distinguish missing SKU from insufficient stock. You may follow up with a query to diagnose the cause, keeping in mind underlying data can continue changing concurrently.

### 8.3. RETURNING Does Not Replace CHECK

The constraint:

```sql
CHECK (stock >= 0)
```

prevents negative numbers. Meanwhile:

```sql
WHERE stock >= requested_quantity
```

prevents deducting past available inventory according to business rules.

Both complement each other: the `UPDATE` predicate decides whether to fulfill the request, while `CHECK` guards the invariant across every write path.

## 9. Returning "Before" and "After" on UPDATE: Handle with Care

In a standard `UPDATE`, `RETURNING stock` returns the **new post-update value**. It does not automatically produce `old_stock` and `new_stock` columns across all PostgreSQL versions.

If the operation strictly subtracts 2 with no triggers or rules modifying `stock`, you can **mathematically infer** it:

```sql
UPDATE returning203.inventory AS i
SET stock = i.stock - 2
WHERE i.sku = 'BOOK-PG'
  AND i.stock >= 2
RETURNING
    i.sku,
    i.stock + 2 AS previous_stock_inferred,
    i.stock AS current_stock;
```

However, `previous_stock_inferred` is **inferred from the formula**, not an independent pre-UPDATE column snapshot. If a trigger adjusts stock or the formula changes, that inference breaks.

### 9.1. When Exact Old/New Values Are Needed for Auditing

Appropriate options depending on version and architecture:

- Use old/new references directly in `RETURNING` **if supported by your PostgreSQL version**, per that version's documentation.
- Use row-level triggers with `OLD`/`NEW` to write audit rows.
- Design a transaction with proper locking/controls to read the old state before updating.
- Record an event log or outbox atomically alongside the business write.

Never write a self-join to the same table assuming `FROM` always gives a **concurrency-safe old version**. When multiple transactions modify the same row concurrently, differences between the query snapshot and the locked updated row version must be carefully handled.

### 9.2. Version-Specific Capabilities

Syntax and support for `OLD`/`NEW` values inside `RETURNING` have evolved across PostgreSQL releases. The core examples in this lesson stick to portable syntax: `INSERT/UPDATE/DELETE ... RETURNING col`. If a project relies on `old.column` or `new.column` syntax, verify the exact documentation and test on your target server version before deploying.

## 10. Conditional State Transitions

An order should typically transition to `PAID` only if it is currently `NEW`.

Seed a test order in the lab by looking up customer ID via email and existing SKU:

```sql
INSERT INTO returning203.orders(
    customer_id,
    sku,
    quantity,
    total_amount,
    status,
    client_request_id
)
SELECT
    c.customer_id,
    'BOOK-PG',
    1,
    120000.00,
    'NEW',
    'seed-order-status-203'
FROM returning203.customers AS c
WHERE c.email = 'an@example.test'
RETURNING order_id, client_request_id, status;
```

Suppose you received the actual `order_id`. You can update by `client_request_id`, avoiding guessing IDs:

```sql
UPDATE returning203.orders AS o
SET status = 'PAID'
WHERE o.client_request_id = 'seed-order-status-203'
  AND o.status = 'NEW'
RETURNING
    o.order_id,
    o.client_request_id,
    o.status AS new_status;
```

On success, it returns a row with `new_status = PAID`.

Running the exact same statement a second time fails `status = 'NEW'` and returns **0 rows**. This behavior is very useful for enforcing **state transitions** conditioned on current state.

### 10.1. Do Not Equate 0 Rows with Idempotent Success

A second call modifying nothing might mean the order is already `PAID`, or it might mean the request ID does not exist, the order is `CANCELLED`, or another filter failed.

If an API should treat "already `PAID`" as an idempotent success on retry, **verify current state and enforce proper idempotency semantics**—never blindly treat every 0-row `UPDATE` as success.

## 11. DELETE ... RETURNING: Capturing Deleted Row Data

With `DELETE`, `RETURNING` returns the data of **the deleted rows**, representing the state removed by the `DELETE`.

Example inserting a test cancelled order:

```sql
INSERT INTO returning203.orders(
    customer_id, sku, quantity, total_amount,
    status, client_request_id
)
SELECT
    c.customer_id, 'MOUSE', 1, 150000.00,
    'CANCELLED', 'seed-delete-203'
FROM returning203.customers AS c
WHERE c.email = 'binh@example.test'
RETURNING order_id, status, client_request_id;
```

Then delete it:

```sql
DELETE FROM returning203.orders AS o
WHERE o.client_request_id = 'seed-delete-203'
  AND o.status = 'CANCELLED'
RETURNING
    o.order_id,
    o.customer_id,
    o.sku,
    o.quantity,
    o.total_amount,
    o.status,
    o.created_at;
```

If the row exists and matches the status, PostgreSQL deletes it and returns the requested columns. No prior `SELECT` is required to capture those fields.

Calling `DELETE` a second time finds the row gone, so `RETURNING` yields 0 rows.

### 11.1. DELETE RETURNING vs. SELECT Then DELETE

```text
SELECT to inspect row -> DELETE row
```

uses two statements; without proper transaction/lock control, data can change between them.

`DELETE ... RETURNING` ties the returned output directly to **the row actually deleted**, preventing stale guesses.

### 11.2. Foreign Key Constraints Still Apply

If a row is referenced by a foreign key with `ON DELETE RESTRICT` or another constraint, `DELETE` fails. `RETURNING` **never bypasses foreign keys, triggers, RLS, or any constraint**.

With `ON DELETE CASCADE`, child rows deleted via cascade in other tables do not automatically appear in `DELETE ... RETURNING` on the parent table. To log cross-table deletions completely, design appropriate auditing.

## 12. RETURNING * and RETURNING Expressions

Just like `SELECT`, `RETURNING` supports columns, expressions, and aliases:

```sql
UPDATE returning203.inventory AS i
SET unit_price = ROUND(i.unit_price * 0.90, 2)
WHERE i.sku = 'KEYBOARD'
RETURNING
    i.sku AS product_code,
    i.product_name,
    i.unit_price AS discounted_price,
    ROUND(i.unit_price * 1.10, 2) AS illustrative_markup;
```

`illustrative_markup` is merely an illustrative calculation **on the new price**; it is not the original price if the update formula wasn't 10% or if a trigger altered the price.

### 12.1. Do Not Aggregate Directly Inside RETURNING

If you want a summary row ("how many SKUs changed, what is total remaining stock"), wrap the DML in a CTE and aggregate outside:

```sql
WITH changed AS (
    UPDATE returning203.inventory AS i
    SET updated_at = now()
    WHERE i.stock > 0
    RETURNING i.sku, i.stock
)
SELECT
    COUNT(*) AS changed_products,
    COALESCE(SUM(stock), 0) AS total_stock_after
FROM changed;
```

Here `changed` is the **`UPDATE RETURNING` row set**. The outer `SELECT` can apply `COUNT`/`SUM`/`GROUP BY` just as on a logical temporary table.

### 12.2. Sorting DML Output

Avoid putting `ORDER BY` directly after `RETURNING` as in a regular `SELECT`:

```sql
-- Not standard UPDATE ... RETURNING ... ORDER BY syntax.
-- UPDATE ... RETURNING sku ORDER BY sku;
```

The clean way is:

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock > 0
    RETURNING sku, stock
)
SELECT sku, stock
FROM changed
ORDER BY sku;
```

## 13. INSERT ... ON CONFLICT DO NOTHING RETURNING

Sometimes an application wants to insert a record only if its unique key does not exist yet.

For example, SKU `BOOK-PG` already exists in `inventory`:

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES ('BOOK-PG', 'PostgreSQL Book', 7, 125000.00)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, stock, unit_price;
```

Because the SKU exists, PostgreSQL skips inserting that row. `RETURNING` yields **0 rows**.

Key points:

- `DO NOTHING` does not update the existing record.
- It **does not return the existing record**.
- An empty result does not supply the existing SKU's stored values.
- If a brand-new SKU is inserted, it returns the newly created row.

### 13.1. What If You Want "Insert If Absent, Otherwise Return Existing Row"?

`DO NOTHING RETURNING` **does not satisfy this directly**. You may need an extra `SELECT` step or a dedicated upsert/idempotency strategy with proper concurrency handling.

Never treat an empty result as proof that "the key already exists with value X" without querying or proving it.

### 13.2. Partial Conflicts in Bulk Inserts

When inserting multiple rows and only some conflict:

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('BOOK-PG', 'PostgreSQL Book', 9, 130000.00),
    ('PAD-NEW', 'Mouse Pad', 5, 70000.00)
ON CONFLICT (sku) DO NOTHING
RETURNING sku, stock;
```

If `BOOK-PG` exists and `PAD-NEW` does not, only **`PAD-NEW`** is returned. This is far more accurate than assuming "two input rows means `RETURNING` always returns two rows."

## 14. INSERT ... ON CONFLICT DO UPDATE RETURNING (UPSERT)

With a unique key, one `INSERT` handles both paths:

- No conflict → **INSERT**.
- Conflict → **UPDATE** the existing row.

Example:

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES (
    'KEYBOARD', 'New Keyboard', 2, 360000.00
)
ON CONFLICT (sku) DO UPDATE
SET
    product_name = EXCLUDED.product_name,
    unit_price = EXCLUDED.unit_price,
    updated_at = now()
RETURNING
    i.sku,
    i.product_name,
    i.stock,
    i.unit_price,
    i.updated_at;
```

Meaning:

- `EXCLUDED.product_name` is the product name **proposed for insertion**.
- `i.product_name` in `RETURNING` is the value on the target row after executing the insert or update branch.
- `stock` in this example is not overwritten on conflict because `DO UPDATE SET` omits `stock`.

If `KEYBOARD` already exists, the statement updates its name/price and returns the updated row.

### 14.1. UPSERT Does Not Always Modify the Row

You can attach a condition to the `DO UPDATE` branch:

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES ('KEYBOARD', 'Keyboard', 2, 360000.00)
ON CONFLICT (sku) DO UPDATE
SET
    unit_price = EXCLUDED.unit_price,
    updated_at = now()
WHERE i.unit_price IS DISTINCT FROM EXCLUDED.unit_price
RETURNING i.sku, i.unit_price;
```

If `KEYBOARD` already exists **and its price already equals the proposed price**, the `DO UPDATE` condition is false. That row is neither updated nor **returned by `RETURNING`**.

Hence, `RETURNING` in an upsert reflects **rows actually inserted or updated**, not necessarily all input rows.

### 14.2. Why Use IS DISTINCT FROM?

`IS DISTINCT FROM` compares two expressions returning a clean `TRUE`/`FALSE` even if one value is `NULL`. It is ideal when updating only rows that genuinely changed.

In this schema `unit_price` is `NOT NULL`, so the difference from `<>` does not show; on nullable columns, `IS DISTINCT FROM` prevents surprising three-valued logic bugs.

### 14.3. Never Blindly Overwrite Business State in UPSERT

Inventory stock, balances, or order statuses should generally **not** be upserted by blindly overwriting all columns from `EXCLUDED`, because a retried request could clobber newer updates.

Decide explicitly which columns can update, under what status guards, and with what idempotency strategy. `ON CONFLICT DO UPDATE` is a data-manipulation primitive, not an automatic safe "latest write wins" policy.

## 15. Multi-Step SQL in One Statement: Data-Modifying CTEs

PostgreSQL lets you put `INSERT`, `UPDATE`, and `DELETE` inside `WITH` as **data-modifying common table expressions**, passing `RETURNING` output to subsequent steps.

Conceptual pattern:

```sql
WITH changed AS (
    UPDATE some_table
    SET ...
    WHERE ...
    RETURNING key, new_value
)
SELECT *
FROM changed;
```

Here `changed` is not a persisted table. It is the **`RETURNING` result set** scoped to the current SQL statement.

### 15.1. Why Are Data-Modifying CTEs Useful?

When you need to:

1. Modify rows in Table A.
2. Use **the exact modified rows** to insert into Table B.
3. Return results from the overall workflow.

`WITH ... RETURNING` reduces round trips between application and database while executing the statement's operations **atomically**: if the statement errors and rolls back, none of its partial modifications persist.

### 15.2. One Statement Does Not Replace Full Transaction Design

A DML CTE does not automatically validate every business case. Check:

- Conditions on parent and child rows.
- Constraints and foreign keys.
- Whether a `DO NOTHING` branch skips a step while an earlier CTE still modified data.
- Whether retries could deduct inventory twice.
- Whether external side effects (emails, HTTP calls, files) are involved.
- Whether the statement runs inside a larger transaction that might roll back.

**Database-level atomicity does not automatically make external workflows exactly-once.**

## 16. UPDATE ... RETURNING Then Insert an Audit/Movement Row in One Statement

We want to deduct 2 units of `BOOK-PG` and record one row in `inventory_movements` **only if the deduction succeeds**.

```sql
WITH reduced_stock AS (
    UPDATE returning203.inventory AS i
    SET
        stock = i.stock - 2,
        updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 2
    RETURNING
        i.sku,
        i.stock AS remaining_stock
)
INSERT INTO returning203.inventory_movements(
    sku,
    stock_delta,
    reason
)
SELECT
    r.sku,
    -2,
    'reservation'
FROM reduced_stock AS r
RETURNING
    movement_id,
    sku,
    stock_delta,
    reason,
    recorded_at;
```

How it works:

1. `reduced_stock` conditionally attempts to deduct stock.
2. If stock is sufficient, it returns one row containing SKU and updated stock.
3. `INSERT ... SELECT FROM reduced_stock` adds one movement entry for that modified SKU.
4. If stock is insufficient, the CTE returns 0 rows, giving `INSERT` **no source rows**, so no movement is added.
5. If inserting the movement violates a constraint or errors, **the entire statement fails**, and stock is not partially deducted.

The final `RETURNING` belongs to the `INSERT` into the movement log, so it returns columns of **the movement row**, not automatically the inventory columns from the first CTE.

### 16.1. Returning the New Stock Count to the Client

Use an outer `SELECT`:

```sql
WITH reduced_stock AS (
    UPDATE returning203.inventory AS i
    SET stock = i.stock - 2, updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 2
    RETURNING i.sku, i.stock, i.unit_price
)
SELECT sku, stock AS remaining_stock, unit_price
FROM reduced_stock;
```

This is a single SQL statement; the outer `SELECT` reads **the CTE's `RETURNING` output** without re-querying `inventory`.

### 16.2. Audit Logging via Trigger vs. CTE?

- **Trigger audit:** covers all write paths into a table; ideal when every change must be logged.
- **DML CTE:** explicitly models a specific business workflow, e.g. "deduct stock for order and log movement."
- **Outbox/event log:** supports external integrations; implemented transactionally or via triggers depending on design.

No single tool replaces an overall audit policy. Choose based on where control is needed and how you ensure all write paths comply.

## 17. Same Statement: Deduct Inventory and Create an Order

This is a classic pattern using `UPDATE RETURNING` output as the **source for order creation**, without re-reading inventory.

Requirement:

> "Create an order for quantity 1 of `BOOK-PG` only if the customer exists and stock is at least 1; take the order price from the inventory row that was updated."

Example in the lab schema:

```sql
WITH buyer AS (
    SELECT customer_id
    FROM returning203.customers
    WHERE email = 'an@example.test'
),
reserved AS (
    UPDATE returning203.inventory AS i
    SET
        stock = i.stock - 1,
        updated_at = now()
    WHERE i.sku = 'BOOK-PG'
      AND i.stock >= 1
      AND EXISTS (SELECT 1 FROM buyer)
    RETURNING
        i.sku,
        i.unit_price,
        i.stock AS remaining_stock
),
created_order AS (
    INSERT INTO returning203.orders(
        customer_id, sku, quantity, total_amount,
        status, client_request_id
    )
    SELECT
        b.customer_id,
        r.sku,
        1,
        r.unit_price,
        'NEW',
        'checkout-example-203'
    FROM buyer AS b
    CROSS JOIN reserved AS r
    RETURNING
        order_id,
        customer_id,
        sku,
        quantity,
        total_amount,
        status,
        client_request_id
)
SELECT *
FROM created_order;
```

Key details:

- `buyer` looks up the customer via `email UNIQUE`.
- `EXISTS (SELECT 1 FROM buyer)` in `UPDATE` prevents deducting stock if the customer does not exist.
- `reserved` returns a row only if the `UPDATE` matched and actually deducted stock.
- `created_order` gets a source row only when both `buyer` and `reserved` exist.
- `client_request_id` is `UNIQUE`. If an order with that request ID already exists, the insert fails with a unique violation and **the whole statement rolls back**; stock is not left deducted without an order.
- The final output returns the **newly created order**, not merely a boolean flag.

### 17.1. Be Careful Before Adding ON CONFLICT DO NOTHING to Order Creation

A seemingly "retry-safe" tweak:

```sql
-- Do not add this clause to the example above without redesigning the workflow:
ON CONFLICT (client_request_id) DO NOTHING
```

On a duplicate request, the order `INSERT` would be **skipped** instead of raising an error, while the `reserved` CTE already deducted stock. If the statement commits, the system **loses stock without creating a new order**.

**Design lesson:** `RETURNING` merely reports what each operation did; it **does not automatically enforce** that every DML CTE affects the same number of rows or rolls back if a downstream step skips rows.

For safe idempotent retries, track processed request state, coordinate locks/unique keys, and ensure stock is deducted only once. That is a workflow/transaction problem, not something `DO NOTHING` alone solves.

### 17.2. Never Re-Read the Updated Table in the Same Statement to Pass Values

Data-modifying CTEs within a single statement share snapshot visibility and pass modifications through **`RETURNING` sets**. Never expect a sibling `SELECT` reading `inventory` directly in the same statement to see values just written by another `UPDATE` CTE.

When you need `remaining_stock`, read `reserved.remaining_stock` from `RETURNING`; that is the channel built for this purpose.

## 18. DELETE ... RETURNING Then Move to an Archive Table

You can move cancelled records to an archive table in one statement. Example table:

```sql
CREATE TABLE returning203.orders_archive (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL,
    total_amount numeric(12, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    archived_at timestamptz NOT NULL DEFAULT now()
);
```

Suppose `CANCELLED` orders qualify for archival under retention rules. Move them directly:

```sql
WITH removed AS (
    DELETE FROM returning203.orders AS o
    WHERE o.status = 'CANCELLED'
      AND o.created_at < TIMESTAMPTZ '2026-11-01 00:00+07'
    RETURNING
        o.order_id,
        o.customer_id,
        o.sku,
        o.quantity,
        o.total_amount,
        o.status,
        o.created_at
)
INSERT INTO returning203.orders_archive(
    order_id,
    customer_id,
    sku,
    quantity,
    total_amount,
    status,
    created_at
)
SELECT
    r.order_id,
    r.customer_id,
    r.sku,
    r.quantity,
    r.total_amount,
    r.status,
    r.created_at
FROM removed AS r
RETURNING
    order_id,
    status,
    archived_at;
```

Meaning:

1. `DELETE` removes cancelled rows older than the cutoff.
2. `RETURNING` provides **all data needed** for the archive insert.
3. `INSERT` into `orders_archive` reads from `removed`.
4. If the archive `INSERT` fails (e.g., `order_id` already exists in archive), the statement fails, so the deletion does not persist partially on its own.

### 18.1. Archiving Is More Than Copying Rows

In real systems, archiving may involve:

- Foreign keys in related tables.
- Retention policies and access controls on archive data.
- Encryption of sensitive fields.
- Compliant audit trails.
- Deciding whether archival captures pre-trigger or post-trigger data.
- Batch limits to avoid long lock holds.
- Retry and idempotency handling.

The example above solely illustrates **passing deleted data via `DELETE RETURNING`** in PostgreSQL.

### 18.2. Returning Deleted Data to an API

If you only want to return the deleted record:

```sql
DELETE FROM returning203.orders
WHERE client_request_id = 'old-cancelled-order-203'
  AND status = 'CANCELLED'
RETURNING order_id, client_request_id, status;
```

If 0 rows are returned, the API must choose the HTTP status or message according to its business contract—never automatically assume "it was already deleted successfully earlier."

## 19. UPDATE ... FROM RETURNING with Source Data

PostgreSQL supports `UPDATE ... FROM` when new values are computed or pulled from another source.

Suppose a product management system sends a price list:

```sql
WITH new_prices(sku, new_price) AS (
    VALUES
        ('BOOK-PG'::text, 125000.00::numeric),
        ('KEYBOARD'::text, 365000.00::numeric)
)
UPDATE returning203.inventory AS i
SET
    unit_price = np.new_price,
    updated_at = now()
FROM new_prices AS np
WHERE i.sku = np.sku
RETURNING
    i.sku,
    i.product_name,
    np.new_price AS submitted_price,
    i.unit_price AS saved_price;
```

The output contains the SKUs actually updated.

### 19.1. A Major Trap in UPDATE ... FROM

If a target row can match **multiple source rows**, the update result depends on which joined row PostgreSQL happens to pick, which applications must never rely on.

For instance, a source price feed having two different prices for the same SKU is **non-unique** source data. Deduplicate by source key using constraints, grouping, or deterministic selection **before `UPDATE`**.

`RETURNING` returns the modified target row, yet cannot turn an ambiguous `JOIN` into a valid business price choice.

### 19.2. RETURNING Source Columns from FROM

In valid cases, `RETURNING` expressions can reference columns from `FROM` tables, such as `np.new_price` above.

When multiple tables share column names, use explicit aliases to avoid confusing proposed values with saved values.

## 20. Counting Modified Rows with RETURNING

If you want the exact **number of updated rows** plus summary metrics, use:

```sql
WITH updated AS (
    UPDATE returning203.inventory AS i
    SET updated_at = now()
    WHERE i.stock > 0
    RETURNING i.sku, i.stock
)
SELECT
    COUNT(*) AS changed_count,
    COALESCE(SUM(stock), 0) AS remaining_total_stock
FROM updated;
```

### 20.1. Outer COUNT(*) Differs from Driver Row Count

With plain `UPDATE ... RETURNING`, a driver receives a result set with one row per modified record. With an aggregating CTE like the one above, the outer result set always has **one row** carrying `changed_count`, even when `changed_count = 0`.

This matters if client code checks for "0 result rows" to detect a no-op. Wrapping in an aggregate changes that convention because `SELECT COUNT(*)` always returns one row.

### 20.2. Not Every UPDATE Changes the Underlying Business Value

The statement:

```sql
UPDATE returning203.inventory
SET stock = stock
WHERE sku = 'BOOK-PG'
RETURNING sku, stock;
```

is still an `UPDATE` on the matching row. It can fire update triggers/processing and return the row, even though `stock` stays identical.

Therefore "row was `UPDATE`d" does not automatically mean "business values changed." If you only want to update when values differ, put that predicate in `WHERE`, for example:

```sql
UPDATE returning203.inventory AS i
SET unit_price = 125000
WHERE i.sku = 'BOOK-PG'
  AND i.unit_price IS DISTINCT FROM 125000::numeric
RETURNING i.sku, i.unit_price;
```

## 21. Result Row Counts and Edge Cases

This table distinguishes "nothing returned" across statements:

| Scenario | Does DML Mutate? | RETURNING |
|---|---|---|
| INSERT one valid row | Yes | 1 row |
| INSERT three valid rows | Yes | 3 rows |
| UPDATE WHERE matches 0 rows | No | 0 rows |
| UPDATE WHERE matches 5 rows | Yes | 5 rows |
| DELETE WHERE matches 0 rows | No | 0 rows |
| DELETE WHERE deletes 2 rows | Yes | 2 rows |
| UPSERT DO NOTHING hits conflict | Does not insert conflicting row | 0 rows for that row |
| UPSERT DO UPDATE fails WHERE clause | Does not update conflicting row | 0 rows for that row |
| CTE UPDATE RETURNING then SELECT COUNT(*) | Depends on UPDATE | One count row |
| DML fails constraint/permission | Statement fails | No valid success result set |

### 21.1. RETURNING Returns Modified Rows, Not the Whole Table

Suppose `inventory` has three SKUs, yet only `BOOK-PG` matches `WHERE`:

```sql
UPDATE returning203.inventory
SET updated_at = now()
WHERE sku = 'BOOK-PG'
RETURNING sku;
```

On success, `RETURNING` contains only `BOOK-PG`, never `KEYBOARD` or `MOUSE`.

### 21.2. Omitting WHERE Can Corrupt Data

```sql
-- Do not run unless intentionally updating the entire table:
UPDATE returning203.inventory
SET unit_price = 100000
RETURNING sku, unit_price;
```

With no `WHERE` clause, this modifies **every product**. `RETURNING` does not restrict scope; it merely shows the rows you modified.

For high-risk `UPDATE`/`DELETE` operations, verify predicates carefully, test in a lab transaction, and use approvals or batching.

## 22. RETURNING with Triggers, Defaults, and Generated Columns

`RETURNING` output reflects database-computed values:

- `IDENTITY` or sequence-assigned values.
- `DEFAULT` expressions.
- PostgreSQL-supported generated columns.
- Values modified by applicable `BEFORE` triggers before writing the row.

Example:

```sql
CREATE TABLE returning203.line_items_demo (
    line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL,
    line_total numeric(14, 2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

Insert:

```sql
INSERT INTO returning203.line_items_demo(
    quantity, unit_price
)
VALUES (3, 120000.00)
RETURNING
    line_id,
    quantity,
    unit_price,
    line_total;
```

The output returns `line_total = 360000.00` without requiring the application to recompute or re-query.

### 22.1. Understanding Actual Results When Triggers Exist

A row-level `BEFORE INSERT/UPDATE` trigger can alter row fields via `NEW`. In such cases, `RETURNING` reflects the row written after the trigger's modifications.

However:

- `RETURNING` does not report all side effects of every trigger.
- An `AFTER` trigger may insert into an audit table or run other logic without appearing in `RETURNING` columns.
- If a trigger raises an exception, the statement fails.
- Never treat `RETURNING` as a replacement for mandatory auditing.

### 22.2. Should You Trust DEFAULT now() as the "Final Timestamp"?

In PostgreSQL, `now()` normally returns the transaction start timestamp, not a wall-clock reading per statement. In long transactions, multiple rows can receive the exact same `now()` timestamp.

If business logic needs an instantaneous evaluation timestamp, consider `clock_timestamp()` and understand its volatility. Regardless, even after `RETURNING` returns a timestamp, **the transaction can still roll back**.

## 23. Transactions: RETURNING Does Not Mean Committed

An example illustrating the difference:

```sql
BEGIN;

INSERT INTO returning203.customers(email, full_name)
VALUES ('rollback@example.test', 'Rollback Test Customer')
RETURNING customer_id, email;

ROLLBACK;
```

The `INSERT` returns an ID before rollback. Yet after `ROLLBACK`, the row does not exist in the database.

### 23.1. API Design Consequences

Never do:

1. Start transaction.
2. `INSERT ... RETURNING id`.
3. Send confirmation email or publish external event.
4. Transaction rolls back.

Users would receive notifications for an entity that was never committed.

When coordinating external side effects, consider the **transactional outbox** pattern: write both the business record and outbox record in the same transaction, and publish only after commit via a worker. `RETURNING` helps retrieve the ID for the outbox record, yet does not guarantee exactly-once delivery on its own.

### 23.2. Identity Gaps Can Still Occur

Even when a row rolls back, consumed identity/sequence values are not returned. Never rely on contiguous ID chains to infer which transactions committed.

### 23.3. SAVEPOINT and Constraint Errors

In manual transactions, when a statement errors, the transaction enters an aborted state until `ROLLBACK` or rolling back to a valid savepoint. `RETURNING` never suppresses constraint violations.

API workflows should let the application's transaction manager handle rollbacks properly, especially for multi-step DML statements.

## 24. RETURNING and Concurrency: Exact Result of the Operation, Not a Permanent Snapshot

Imagine two requests deducting stock for the same SKU.

The statement:

```sql
UPDATE returning203.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-PG'
  AND stock >= 1
RETURNING sku, stock;
```

returns the stock **immediately after that specific `UPDATE`**. If another request updates the row after your transaction commits, the `RETURNING` value no longer represents the **current stock at all future points in time**.

Phrase API responses accurately:

> "After this order operation, remaining stock was recorded as 3."

rather than:

> "Stock is guaranteed to stay 3 until the user refreshes the page."

### 24.1. Different Isolation Levels

Under `READ COMMITTED`, concurrent transactions updating the same row coordinate via row locks and predicate re-evaluation. Under `REPEATABLE READ` or `SERIALIZABLE`, concurrent updates can trigger serialization failures depending on the conflict.

Applications must:

- Catch relevant transaction-error SQLSTATEs.
- Roll back failed transactions.
- Retry **the entire transaction** under a valid policy, not just re-run one isolated statement.
- Use idempotency keys for retryable requests.
- Never assume `RETURNING` bypasses locks or concurrency conflicts.

### 24.2. Does RETURNING Lock Rows by Itself?

`UPDATE` and `DELETE` coordinate locks/MVCC to modify rows; `RETURNING` is strictly **a way to return results**, not a separate locking command. If you need to lock rows across multiple steps in a transaction, use an explicit locking design like `SELECT ... FOR UPDATE`, while avoiding `SELECT`-then-`UPDATE` when a single conditional `UPDATE` suffices.

## 25. Data-Modifying CTEs: Snapshot Rules and Avoiding Modifying the Same Row Twice

A statement with multiple DML CTEs is powerful, provided you follow its rules:

1. All DML CTEs in a single statement execute under **the same snapshot**; physical execution order among sibling DMLs is not a coordination mechanism applications may rely on.
2. **`RETURNING`** is the channel passing modified row data between components of the statement.
3. Never attempt to modify **the same row twice** in one statement via multiple CTEs; results of duplicate modifications are not guaranteed in a way safe for business logic.
4. A DML CTE can still execute even if its `RETURNING` result is never read, per data-modifying CTE execution rules; never assume "omitting `SELECT FROM changed` means the `UPDATE` won't run."
5. If any part of the statement raises an exception, the whole statement fails rather than committing sub-changes independently.
6. Use `RETURNING` to pass modified values instead of re-reading the base table hoping to observe a sibling CTE's effects.

### 25.1. Pattern to Avoid

```sql
-- Pattern illustrating a risky design:
WITH first_change AS (
    UPDATE inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG'
    RETURNING sku
),
second_change AS (
    UPDATE inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG'
    RETURNING sku
)
SELECT *
FROM first_change;
```

The flaw is **two DML CTEs attempting to modify the same SKU's inventory row** in one statement, not a missing `RETURNING`.

To deduct 2, write **one `UPDATE` subtracting 2** with a sufficient-stock guard; to process two separate requests, use separate transactions/synchronization rather than updating one row twice via sibling CTEs.

### 25.2. Multiple Statements in a Transaction Is Also Valid

Not every workflow has to be crammed into one huge SQL statement. A multi-statement transaction is clearer when you need to:

- Check permissions/approvals.
- Inspect data returned by the first statement.
- Evaluate business logic in application code.
- Write related tables.
- Respond via API after commit.

Use `RETURNING` appropriately in each statement. Fewer round trips in one giant SQL query is not automatically better than a clear, safe, testable multi-statement transaction.

## 26. RETURNING with Privileges and RLS

`RETURNING` can expose data from columns just inserted, deleted, or updated. Accordingly, it must obey SQL privileges and database access policies.

### 26.1. Column Read Privileges in RETURNING

Alongside `INSERT`, `UPDATE`, or `DELETE` privileges, an application may need `SELECT` privilege on columns referenced in `RETURNING` or read predicates.

For example, a role allowed to update status yet forbidden from reading a sensitive column cannot simply run:

```sql
UPDATE some_table
SET status = 'DONE'
WHERE id = 123
RETURNING secret_token;
```

without database privilege checks enforcing access rules.

### 26.2. RLS Controls Which Rows Can Be Modified or Returned

Row-Level Security (RLS) restricts which rows a role can see or modify. When policies are active, `UPDATE`/`DELETE` will not touch rows outside the role's scope; `INSERT` is checked against `WITH CHECK` policies.

`RETURNING` cannot bypass RLS. Results can be empty due to **privileges or policies**, not solely because a record does not exist.

If an API distinguishes "404 resource not found" from "403 forbidden," design security contracts carefully—even revealing whether a cross-tenant row exists can be a security leak.

### 26.3. Avoid RETURNING * on Tables with Sensitive Information

A users table may hold emails, phone numbers, password hashes, or internal fields. In APIs, write:

```sql
RETURNING user_id, display_name, created_at
```

instead of:

```sql
RETURNING *
```

This restricts exposed data and keeps API contracts stable when columns are added.

## 27. JDBC/Java: Reading ResultSets from DML RETURNING

With PostgreSQL JDBC, a statement containing `RETURNING` produces a result set. You can call `PreparedStatement.executeQuery()` to read it.

Example conditionally deducting stock:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class InventoryRepository {
    public Integer reserve(
            Connection connection,
            String sku,
            int quantity) throws SQLException {

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be greater than 0");
        }

        String sql = """
            UPDATE returning203.inventory
            SET stock = stock - ?,
                updated_at = now()
            WHERE sku = ?
              AND stock >= ?
            RETURNING stock
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {

            ps.setInt(1, quantity);
            ps.setString(2, sku);
            ps.setInt(3, quantity);

            try (ResultSet rs = ps.executeQuery()) {
                if (rs.next()) {
                    return rs.getInt("stock");
                }
                return null;
            }
        }
    }
}
```

Meaning:

- The `Integer` result is the post-UPDATE stock if a row matched.
- Java `null` here means **0 `RETURNING` rows**, not SQL `NULL` stock; `stock` is declared `NOT NULL`.
- The caller decides how to report insufficient stock vs. missing SKU.
- If the connection is in an explicit transaction, commit/rollback remains the transaction manager's responsibility.

### 27.1. Should You Use executeUpdate()?

Normally `executeUpdate()` is for DML **that returns no result set**. For PostgreSQL DML with `RETURNING`, use driver APIs meant for reading results, such as `executeQuery()` or `execute()` followed by retrieving the `ResultSet`.

Do not call `executeUpdate()` expecting to read `RETURNING` columns directly like a `SELECT` unless your driver/API explicitly exposes them.

### 27.2. Retrieving an INSERT-Generated ID

```java
String sql = """
    INSERT INTO returning203.customers(email, full_name)
    VALUES (?, ?)
    RETURNING customer_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "jdbc@example.test");
    ps.setString(2, "JDBC Customer");

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("customer_id");
            // Use the actual id in your designed workflow.
        }
    }
}
```

This Java snippet assumes a valid PostgreSQL JDBC driver, data source, and connection. In production, use unique fixture emails to avoid `UNIQUE` violations, close transactions properly, and return API responses after commit.

### 27.3. RETURNING vs. getGeneratedKeys()

JDBC also offers `getGeneratedKeys()`, which PostgreSQL JDBC supports. When you want explicit control over **multiple columns** or computed expressions, an explicit `RETURNING` clause is clearer and easier to inspect.

Do not mix both mechanisms ambiguously without knowing your driver/framework contract. Standardize on one approach per project and test it.

### 27.4. Spring/JdbcTemplate

When a query includes `RETURNING`, use a method supporting a row mapper/`ResultSet`, rather than an update method returning only an integer count.

Conceptual example:

```java
String sql = """
    UPDATE returning203.inventory
    SET stock = stock - ?
    WHERE sku = ? AND stock >= ?
    RETURNING sku, stock
    """;

List<InventoryResult> rows = jdbcTemplate.query(
    sql,
    (rs, rowNum) -> new InventoryResult(
        rs.getString("sku"),
        rs.getInt("stock")
    ),
    quantity, sku, quantity
);
```

`InventoryResult` is an application-defined type; this illustrates integration usage. In real services, handle `rows.isEmpty()`, transaction boundaries, and SQL exceptions.

## 28. RETURNING in APIs: Appropriate Error Codes and Responses

Suppose an endpoint is:

```text
POST /inventory/{sku}/reserve
{
  "quantity": 2
}
```

You can map outcomes as:

- **1 `RETURNING` row** → update succeeded; return SKU and remaining stock.
- **0 `RETURNING` rows** → no row matched predicates; diagnose cause to return the right business error code.
- **Constraint violation** → business or integrity error mapped from SQLSTATE.
- **Serialization/deadlock/timeout** → controlled retry policy.
- **Commit failure** → never treat an earlier `RETURNING` result set as a durable success.

Illustrative success response:

```json
{
  "sku": "BOOK-PG",
  "reservedQuantity": 2,
  "remainingStock": 3
}
```

This stock count reflects the state **after this operation**, with no guarantee it remains unchanged as other requests arrive.

### 28.1. Never Let Clients Assume Receiving an ID Means Permanent Persistence

If a request still sits inside an uncommitted transaction, returning success early misleads clients. APIs must define clear transaction boundaries and only confirm operations after commit succeeds.

### 28.2. Never Expose Raw DB Error Details Unnecessarily

PostgreSQL error messages can expose constraint names, key values, row contents, or table names. Detailed messages belong in internal logs; user-facing responses should be safe, sanitized, and business-oriented.

## 29. RETURNING and Idempotency: Common Pitfalls

An API may receive duplicate requests due to timeouts or client retries. `client_request_id UNIQUE` detects a previously created request, yet several subtleties remain:

- The client does not know whether the first request committed.
- The first request may have committed while the response was lost.
- Two requests with the same idempotency key may arrive **concurrently**.
- The client might reuse a key with a different payload.
- The workflow might touch multiple tables such as inventory, orders, and loyalty points.

### 29.1. The Trap of "DO NOTHING and Treating Empty RETURNING as Success"

Example:

```sql
INSERT INTO returning203.orders(...)
VALUES (...)
ON CONFLICT (client_request_id) DO NOTHING
RETURNING order_id;
```

On conflict, the result is empty. It **does not contain the previous order's `order_id`**, nor does it verify the payload matches the original request.

Using that empty result to decide whether to deduct stock again easily introduces bugs.

### 29.2. A Better Design Direction

Depending on the application:

1. Scope idempotency keys to tenant/user and business operation.
2. Store a payload hash and processing status for handled requests.
3. Coordinate concurrency via unique keys and transactions.
4. On duplicate requests, return **the stored result of the original request** instead of re-executing side effects.
5. Deduct stock and create the order once inside a safe transaction.
6. If commit fails, allow safe retries based on observable state.

`RETURNING` is great for capturing IDs and outcomes, yet does not orchestrate idempotency automatically.

## 30. Comparing RETURNING with Other Retrieval Techniques

| Approach | Purpose | Risks / Limits |
|---|---|---|
| `INSERT ... RETURNING id` | Get ID of new row | Does not guarantee commit while transaction is open |
| `SELECT MAX(id)` | Read largest ID in table | Cannot tell which row you inserted; breaks under concurrency |
| `SELECT currval(...)` | Read latest sequence value in current session | Requires knowing sequence and prior call in session; does not replace multi-column `RETURNING` |
| `SELECT` after `UPDATE` | Read table state at query time | Can observe later changes if separate statement/transaction |
| `UPDATE ... RETURNING stock` | Get stock after that `UPDATE` | Not a permanent future state |
| `DELETE ... RETURNING ...` | Retrieve deleted row data | Does not automatically write audits or backups |
| `WITH changed AS (UPDATE ... RETURNING) SELECT ...` | Turn modified rows into input for `SELECT` | Requires understanding snapshots/DML CTEs |
| `INSERT ... ON CONFLICT DO NOTHING RETURNING` | Know which rows were actually inserted | Conflicting rows are omitted |
| `INSERT ... ON CONFLICT DO UPDATE RETURNING` | Know inserted or updated rows | A `WHERE` on `DO UPDATE` can suppress update and output |
| `getGeneratedKeys()` via JDBC | Retrieve generated keys via driver API | Driver/framework contract differs from explicit `RETURNING` |

### 30.1. RETURNING Differs from SELECT ... FOR UPDATE

`SELECT ... FOR UPDATE` locks selected rows to coordinate multi-step transactions. It **does not modify data**. Conversely, `UPDATE ... RETURNING` modifies rows and immediately returns the result.

Do not reach for `FOR UPDATE` solely to read the new value: a conditional `UPDATE ... RETURNING` is cleaner when the operation needs only one atomic change.

## 31. Common Mistakes

### 31.1. Inserting Data Then Running SELECT MAX(id)

The highest ID may belong to another transaction. **Fix:** `INSERT ... RETURNING id`.

### 31.2. Assuming RETURNING Returns Every Row from the Source SELECT

`INSERT ... SELECT ... ON CONFLICT DO NOTHING RETURNING ...` returns only rows actually inserted. Skipped input rows do not appear.

### 31.3. Treating 0 RETURNING Rows as Success

A status `UPDATE` returning 0 rows might mean the row does not exist, status was wrong, a concurrent change invalidated the predicate, or RLS blocked it. **Fix:** define explicit 0-row semantics per API.

### 31.4. Omitting WHERE in UPDATE/DELETE

`RETURNING` does not stop a full-table update or delete. **Fix:** restrict target rows accurately; run practice experiments in rolled-back lab transactions.

### 31.5. Using RETURNING * and Exposing Raw Results to Clients

Risks leaking sensitive columns and coupling to schema changes. **Fix:** list explicit columns.

### 31.6. Treating Returned IDs as Committed Data

A transaction can still roll back after `RETURNING`. **Fix:** establish clear commit boundaries before confirming to API clients.

### 31.7. Using DO NOTHING on Order Insert After Already Deducting Stock

When an order hits an idempotency conflict, `INSERT` skips while stock may already be deducted. **Fix:** coordinate retries via transactions and request state tracking.

### 31.8. Expecting DO NOTHING RETURNING to Return the Existing Row

Skipped rows are not returned. **Fix:** if the existing row is needed, add a safe read path or proper upsert logic.

### 31.9. Using UPDATE FROM with Multiple Source Rows per Key

PostgreSQL does not guarantee picking the business-intended source row. **Fix:** normalize/deduplicate by source key before `UPDATE`.

### 31.10. Modifying the Same Row in Multiple Sibling DML CTEs

Modifying the same row twice in one statement has no reliable ordering guarantee. **Fix:** combine calculations into one `UPDATE` or use controlled multi-statement transactions.

### 31.11. Re-Reading the Base Table in the Same Statement to See CTE Changes

Sibling CTEs share snapshot visibility; pass changes via `RETURNING`, never by re-reading the base table expecting to see sibling modifications.

### 31.12. Treating Derived Old-Value Formulas as Absolute Proof

`RETURNING stock + quantity` infers the pre-update value only if assumptions hold and no triggers interfered. **Fix:** for strict old/new auditing, use version-supported mechanisms, triggers, or proper versioning.

### 31.13. Ignoring Errors When Reading JDBC ResultSets

Result sets can be empty. DML can fail with unique/check/FK violations, serialization failures, or timeouts. **Fix:** try-with-resources, empty-set handling, transaction rollback, and retry policies.

### 31.14. Treating RETURNING as an External Event Queue

`RETURNING` returns data to the client; it does not deliver messages to Kafka or email. **Fix:** use an outbox/event infrastructure when needed.

### 31.15. Logging Sensitive DELETE RETURNING Payloads Publicly

`DELETE RETURNING` can contain personal data. **Fix:** project only necessary fields, enforce retention, and restrict audit log access.

### 31.16. Assuming RETURNING Always Has Deterministic Order

Never assume DML result sets are sorted. **Fix:** wrap DML in a CTE and run `SELECT ... ORDER BY` when order matters.

## 32. Practice Exercises with Solutions

The exercises below assume the `returning203` lab schema has been created. If run sequentially, DML commands mutate the fixture; use distinct SKUs/request keys, run inside rolled-back transactions while learning, or inspect current state beforehand.

### Exercise 1. Create a Customer and Return the Actual ID

**Requirement:** create customer `qa-203@example.test` without guessing the ID.

```sql
INSERT INTO returning203.customers(email, full_name)
VALUES ('qa-203@example.test', 'QA Customer')
RETURNING customer_id, email, created_at;
```

**Solution:** use `INSERT ... RETURNING`; the returned ID is the actual value PostgreSQL assigned to the inserted row.

### Exercise 2. Why Is SELECT MAX(customer_id) Unsuitable?

**Solution:** the largest ID may belong to another request/transaction; sequences do not guarantee gapless numbering or alignment with commit order. `RETURNING` binds the ID directly to the inserted row.

### Exercise 3. Insert Two New SKUs and Receive Both Codes

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES
    ('PEN-203', 'Pen', 10, 10000),
    ('NOTE-203', 'Notebook', 5, 25000)
RETURNING sku, product_name, stock, unit_price;
```

**Solution:** if both rows insert successfully, `RETURNING` returns two rows. Do not assume row order without sorting.

### Exercise 4. Update Price and Receive the New Price

```sql
UPDATE returning203.inventory
SET unit_price = 115000, updated_at = now()
WHERE sku = 'BOOK-PG'
RETURNING sku, unit_price AS new_price;
```

**Solution:** the new price is returned straight from the `UPDATE`; no follow-up `SELECT` is needed.

### Exercise 5. Deduct Stock Only When Sufficient

```sql
UPDATE returning203.inventory
SET stock = stock - 2
WHERE sku = 'BOOK-PG'
  AND stock >= 2
RETURNING sku, stock AS remaining_stock;
```

**Solution:** returns one row if sufficient stock exists; 0 rows otherwise. Distinguish missing SKU from insufficient stock if the API requires it.

### Exercise 6. What If Two Transactions Concurrently Deduct 4 from Stock 5?

**Solution:** with `UPDATE ... WHERE stock >= 4 RETURNING ...`, both concurrent updates on the same row cannot succeed when the predicate is re-evaluated. One will either fail the predicate or hit a transaction serialization error depending on isolation level.

### Exercise 7. Delete a Row and Capture Deleted Data

```sql
DELETE FROM returning203.orders
WHERE client_request_id = 'unused-cancelled-203'
  AND status = 'CANCELLED'
RETURNING order_id, sku, quantity, status;
```

**Solution:** if a matching row exists, PostgreSQL returns the deleted row's values; otherwise 0 rows. No prior `SELECT` is required.

### Exercise 8. UPSERT DO NOTHING and RETURNING

```sql
INSERT INTO returning203.inventory(
    sku, product_name, stock, unit_price
)
VALUES ('BOOK-PG', 'Book', 5, 120000)
ON CONFLICT (sku) DO NOTHING
RETURNING sku;
```

**Answer:** in the sample data `BOOK-PG` already exists, so 0 rows are returned. It does not return the existing row's data.

### Exercise 9. Conditional Price UPSERT

```sql
INSERT INTO returning203.inventory AS i(
    sku, product_name, stock, unit_price
)
VALUES ('KEYBOARD', 'Keyboard', 2, 350000)
ON CONFLICT (sku) DO UPDATE
SET unit_price = EXCLUDED.unit_price
WHERE i.unit_price IS DISTINCT FROM EXCLUDED.unit_price
RETURNING i.sku, i.unit_price;
```

**Solution:** if the current price already equals the proposed price, `DO UPDATE` is skipped and `RETURNING` is empty. If different, the row is updated and returned.

### Exercise 10. Return Only the Count of Updated Rows

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock > 0
    RETURNING sku
)
SELECT COUNT(*) AS changed_count
FROM changed;
```

**Solution:** the outer `SELECT` always returns one `COUNT` row showing how many `inventory` rows were updated.

### Exercise 11. After an UPDATE CTE, What Should You Read?

**Question:** when you need the updated stock from `UPDATE ... RETURNING stock`, should you re-`SELECT` the `inventory` table or `SELECT` from the CTE?

**Answer:** within the same statement, read **the CTE's `RETURNING` set** to use the new values. Never rely on re-reading the base table expecting to see sibling CTE modifications in a specific order.

### Exercise 12. Create a Movement Row Only When Stock Deduction Succeeds

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET stock = stock - 1
    WHERE sku = 'KEYBOARD'
      AND stock >= 1
    RETURNING sku
)
INSERT INTO returning203.inventory_movements(
    sku, stock_delta, reason
)
SELECT sku, -1, 'practice-203'
FROM changed
RETURNING movement_id, sku, stock_delta;
```

**Solution:** if `UPDATE` affects 0 rows, no movement is inserted. If `INSERT` fails, the entire statement fails.

### Exercise 13. Why Not Blindly Add DO NOTHING to Order Insertion?

**Answer:** if an earlier step deducted stock while the order insert hits a conflict and gets skipped by `DO NOTHING`, the transaction could commit the stock deduction without creating a new order. Design proper idempotency and coordination across steps.

### Exercise 14. Retrieve Database-Assigned Defaults/Generated Values

```sql
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id, token_state, generated_at;
```

**Solution:** `RETURNING` captures the database-assigned ID, timestamp, and state without client-side computation.

### Exercise 15. Compute Totals After UPDATE from the RETURNING Set

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET updated_at = now()
    WHERE stock >= 1
    RETURNING sku, stock
)
SELECT
    COUNT(*) AS products_changed,
    COALESCE(SUM(stock),0) AS total_remaining
FROM changed;
```

**Solution:** aggregation runs over the updated rows, not necessarily the entire `inventory` table.

### Exercise 16. Why Doesn't RETURNING Guarantee Commit?

```sql
BEGIN;
INSERT INTO returning203.job_tokens
DEFAULT VALUES
RETURNING token_id;
ROLLBACK;
```

**Solution:** an ID can be returned inside the transaction while the row is later rolled back; sequences may still keep a gap. APIs must not confirm persistence until commit completes.

### Exercise 17. When DELETE Hits a Foreign Key?

**Answer:** if a constraint forbids deletion and no cascade applies, `DELETE` fails. `RETURNING` does not bypass constraints or turn a failed operation into a valid result set.

### Exercise 18. Reading RETURNING Results in Java

**Solution:** use `PreparedStatement` with a `ResultSet`-returning method such as `executeQuery()` on `UPDATE ... RETURNING`; check `rs.next()`, handle zero rows, and manage transactions.

### Exercise 19. Should Public Endpoints Use RETURNING *?

**Solution:** usually no. Explicitly project required columns such as `RETURNING order_id, status, created_at` to avoid leaking sensitive fields or breaking on schema evolution.

### Exercise 20. Distinguishing Point-in-Time Operations from Long-Lived Snapshots

**Question:** `UPDATE inventory SET stock=stock-1 RETURNING stock` returns 4. Moments later another request deducts 1 more. Was returning 4 wrong?

**Solution:** no. It accurately reported the value **right after the first operation**; stock became 3 once the second request finished. `RETURNING` does not create a time-frozen stock guarantee.

## 33. Knowledge Check Questions

### Question 1. Is RETURNING a SQL function?

No. It is a **clause** of PostgreSQL DML statements.

### Question 2. Does INSERT RETURNING alter how INSERT writes?

No. `INSERT` still writes the rows; `RETURNING` simply requests returning the written row data.

### Question 3. Does DELETE RETURNING keep rows in the table?

No. Once `DELETE` succeeds and the transaction commits, the rows are removed. `RETURNING` returns the values of the deleted rows within that statement.

### Question 4. Does UPDATE RETURNING return old or new values?

Standard column expressions in `UPDATE RETURNING` return **post-update** values. Accessing old and new simultaneously relies on version-specific syntax; consult your target server's documentation.

### Question 5. Does DO NOTHING RETURNING return conflicting rows?

No. Skipped rows are not inserted and do not appear in `RETURNING`.

### Question 6. Can you use expressions in RETURNING?

Yes. For example, `RETURNING quantity * unit_price AS total` over valid columns.

### Question 7. Can you SELECT from a DML CTE's RETURNING output?

Yes:

```sql
WITH changed AS (
    UPDATE ...
    RETURNING ...
)
SELECT ...
FROM changed;
```

This is a **template**; replace ellipses with concrete SQL before running.

### Question 8. Does RETURNING automatically grant permission to read all columns?

No. Appropriate DML/`SELECT` privileges, RLS, and security policies still apply.

### Question 9. Does RETURNING enforce sufficient inventory by itself?

No. `WHERE stock >= quantity` and constraints decide whether stock can be deducted. `RETURNING` merely returns rows actually affected.

### Question 10. Does RETURNING automatically create system-wide audit logs everywhere?

No. Triggers, audit tables, outboxes, or DML CTE workflows must be explicitly designed and enforced across all write paths.

## 34. Quick Reference Table

| Goal | Syntax Pattern | Key Note |
|---|---|---|
| Get ID after insert | `INSERT ... RETURNING id` | Gets the ID created by that exact statement |
| Get multiple columns | `RETURNING id, status, created_at` | Limit returned data |
| Get default value | `INSERT ... RETURNING created_at` | DB supplies the value |
| Get computed/generated column | `INSERT ... RETURNING generated_col` | Receive persisted value |
| Get post-update price | `UPDATE ... RETURNING price` | Value after modification |
| Safe stock deduction | `UPDATE ... SET stock=stock-? WHERE stock>=? RETURNING stock` | 0 rows = condition not met |
| Conditional state transition | `UPDATE ... WHERE status='NEW' RETURNING ...` | Blocks invalid transitions |
| Retrieve deleted row | `DELETE ... RETURNING ...` | Returns deleted row contents |
| Insert skipping conflicts | `ON CONFLICT DO NOTHING RETURNING ...` | Returns only actually inserted rows |
| UPSERT and get final values | `ON CONFLICT DO UPDATE ... RETURNING ...` | Reflects insert or update branch |
| UPDATE only when value differs | `WHERE col IS DISTINCT FROM proposed` | If unchanged, `RETURNING` emits no row |
| Read DML CTE output | `WITH changed AS (UPDATE ... RETURNING ...) SELECT ...` | Reads the `changed` set |
| Write audit in one statement | `WITH changed AS (...) INSERT ... SELECT FROM changed` | Understand atomicity and triggers |
| Move deleted rows to archive | `WITH removed AS (DELETE ... RETURNING ...) INSERT ... SELECT ...` | Delete + insert in one statement |
| Count modified rows | `WITH changed AS (...) SELECT COUNT(*) FROM changed` | `COUNT` returns one row |
| Sort DML output | `WITH changed AS (...) SELECT ... ORDER BY ...` | Never rely on `RETURNING` order |
| Read results in JDBC | `PreparedStatement.executeQuery()` | Inspect `ResultSet` and 0-row cases |
| Protect sensitive data | Project only needed columns in `RETURNING` | Avoid `RETURNING *` in APIs |
| Control persistence | Transaction manager / `COMMIT` | `RETURNING` is not `COMMIT` |
| Control idempotency | `UNIQUE` + proper workflow/transactions | `DO NOTHING` alone is insufficient |

## 35. Summary: Modify the Right Rows and Receive Results Immediately

`RETURNING` solves a specific yet vital requirement in PostgreSQL:

> **After an `INSERT`, `UPDATE`, or `DELETE`, how do you receive the exact values the statement just affected without guessing or issuing a separate `SELECT`?**

Three foundational patterns:

```sql
-- Create entity and retrieve generated key:
INSERT INTO returning203.customers(email, full_name)
VALUES ('new@example.test', 'New Customer')
RETURNING customer_id, created_at;
```

```sql
-- Conditionally update and return new state:
UPDATE returning203.inventory
SET stock = stock - 1
WHERE sku = 'BOOK-PG' AND stock >= 1
RETURNING sku, stock AS remaining_stock;
```

```sql
-- Delete and capture deleted row data:
DELETE FROM returning203.orders
WHERE client_request_id = 'cancelled-example-203'
  AND status = 'CANCELLED'
RETURNING order_id, sku, quantity, status;
```

When chaining operations in **one statement**, use a data-modifying CTE:

```sql
WITH changed AS (
    UPDATE returning203.inventory
    SET stock = stock - 1
    WHERE sku = 'BOOK-PG' AND stock >= 1
    RETURNING sku, stock
)
SELECT sku, stock
FROM changed;
```

Key principles to remember:

1. **`RETURNING` returns only rows actually affected**; when `WHERE` matches nothing, the result set is empty.
2. **`INSERT`** returns new rows, **`UPDATE`** returns post-update values, and **`DELETE`** returns deleted row contents under standard semantics.
3. **`DEFAULT`/`IDENTITY`/generated columns** can be returned straight from the database without guessing IDs via `MAX`.
4. **`UPSERT DO NOTHING`** does not return skipped rows; **`DO UPDATE` with `WHERE`** also omits conflicting rows that fail its predicate.
5. **`WITH ... RETURNING`** passes data between DML and `SELECT` in one statement; never re-read the base table expecting to observe sibling CTE changes.
6. **`RETURNING` does not commit**. Transactions can still roll back, and identity sequences can still have gaps.
7. **`RETURNING` does not solve concurrency or idempotency alone**. `UPDATE` predicates, `UNIQUE`/`CHECK` constraints, isolation, locking, and transactions still must be engineered properly.
8. **Security and APIs:** project only needed columns, enforce privileges/RLS, handle 0 rows, constraint errors, and commit boundaries.
9. **Prioritize readability:** single-statement CTEs are helpful, yet never force an entire workflow into one query if a multi-step transaction is clearer and safer.

**One sentence to remember:** `RETURNING` does not merely tell you "how many rows changed"—it lets you retrieve **the exact rows and values PostgreSQL just modified**, and use them immediately in your application or next SQL step.
