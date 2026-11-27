# Row-Level and Statement-Level Triggers in PostgreSQL

In PostgreSQL, a **trigger** is a mechanism that automatically invokes a function when a matching data or schema event occurs. For DML triggers on tables, a choice that directly affects correctness and performance is:

- **`FOR EACH ROW` — row-level trigger:** fired once for each row involved in the operation.
- **`FOR EACH STATEMENT` — statement-level trigger:** fired once for each matching SQL statement, even if the statement affects zero rows.

Example:

~~~sql
UPDATE products
SET price = price * 1.10
WHERE category = 'office';
~~~

If 20,000 rows match the condition, an applicable `FOR EACH ROW` trigger may execute **20,000 times**, whereas an applicable `FOR EACH STATEMENT` trigger executes **once for that UPDATE statement**. However, if you need the exact **`OLD.price` and `NEW.price` of each product**, a row-level trigger is more convenient. If you need to aggregate all modified rows at once, a statement-level trigger combined with **transition tables** is usually better suited.

~~~text
                 One UPDATE statement
                         |
                BEFORE STATEMENT
                         |
                   Select rows
                         |
              +----------+----------+
              |          |          |
              v          v          v
            Row A      Row B      Row C ...
              |          |          |
           BEFORE ROW trigger (per row)
              |          |          |
                 Apply row change
              |          |          |
            AFTER ROW trigger (per row)
                         |
                AFTER STATEMENT
                         |
                  Statement ends
~~~

This diagram illustrates **logical layers**, not every internal physical detail of PostgreSQL: specifically, `AFTER ROW` events are queued and processed toward the end of the statement, before the corresponding `AFTER STATEMENT` triggers. In addition, triggers of the same kind are ordered by name, internal constraint triggers may be present, and operations like `ON CONFLICT`, `MERGE`, or partition routing have specific rules.

This is a self-contained lesson on **row-level and statement-level triggers** in the *Triggers and Rules* chapter: syntax, `OLD`/`NEW`/`RETURN` semantics, `BEFORE`/`AFTER` ordering, `WHEN`, transition tables, `TRUNCATE`, view triggers, atomicity, performance, security, catalogs, and practice exercises with answers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the invocation count of `FOR EACH ROW` vs. `FOR EACH STATEMENT`.
2. Explain why statement-level triggers still run when affecting **0 rows**.
3. Create `RETURNS trigger` functions in PL/pgSQL using `TG_OP`, `TG_WHEN`, and `TG_LEVEL`.
4. Use `NEW` and `OLD` properly across `INSERT`, `UPDATE`, and `DELETE`.
5. Distinguish the meaning of `RETURN NEW`, `RETURN OLD`, and `RETURN NULL` in `BEFORE ROW` vs. `AFTER` or `STATEMENT` triggers.
6. Apply `BEFORE ROW` to normalize or validate data before writing.
7. Apply `AFTER ROW` to write an audit entry for each applied change.
8. Apply `AFTER STATEMENT` to record a single execution of a statement.
9. Use `REFERENCING OLD TABLE/NEW TABLE` to read affected rows in batch.
10. Understand the scope of `WHEN` and `UPDATE OF column`.
11. Explain trigger behavior for `TRUNCATE`, `INSTEAD OF` on views, constraint triggers, and partitioned tables.
12. Evaluate the effects of transactions, errors, and rollbacks on data written by triggers.
13. Avoid N+1 query loops, trigger cycles, and recursive updates.
14. Inspect metadata via `pg_trigger` and `pg_get_triggerdef`, and manage enable/disable and migrations.

## 2. What Is a Trigger, and How Does It Differ From Calling a Function Manually?

A regular function is called explicitly:

~~~sql
SELECT calculate_total(1001);
~~~

A trigger function is called automatically by PostgreSQL when an event matches on an object:

~~~sql
CREATE TRIGGER trigger_name
BEFORE INSERT OR UPDATE
ON schema.table_name
FOR EACH ROW
EXECUTE FUNCTION schema.trigger_function();
~~~

A trigger involves **two objects/concepts**:

1. **Trigger function:** processing code written in a trigger-capable language, typically `plpgsql`, returning the special type `trigger`.
2. **Trigger definition:** binds the function to a table/view, event, timing, and execution level.

### 2.1. A trigger is not a cron job

Triggers do not run on a schedule. They run because a specific statement/event is executed by PostgreSQL on the object the trigger is attached to. If you need nightly data aggregation, scheduled jobs are usually more appropriate than triggers repeatedly writing per row.

### 2.2. Triggers do not replace all constraints

`NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, and data types should be the first choice for simple invariants directly supported by PostgreSQL. Triggers are useful when logic needs `OLD`/`NEW`, change logs, cross-table logic, or behavior not clearly expressible as a constraint.

### 2.3. A single SQL statement can affect many rows

~~~sql
UPDATE inventory SET quantity = quantity + 1;
~~~

This is still **one statement**, even if there are millions of rows. Do not equate statement count with modified row count.

## 3. General CREATE TRIGGER Syntax

~~~sql
CREATE TRIGGER trigger_name
    { BEFORE | AFTER | INSTEAD OF }
    { INSERT | UPDATE [ OF column_name [, ...] ] | DELETE | TRUNCATE }
    ON schema.table_name
    [ REFERENCING
        { OLD TABLE AS old_alias | NEW TABLE AS new_alias } ... ]
    [ FOR [ EACH ] { ROW | STATEMENT } ]
    [ WHEN (condition) ]
    EXECUTE FUNCTION schema.trigger_function(arguments);
~~~

This is a **syntax reference pattern**, not a single runnable statement verbatim: option combinations have specific constraints. For instance, `TRUNCATE` is statement-level only; `INSTEAD OF` is row-level on views only; transition relations apply only to eligible `AFTER` triggers.

### 3.1. Trigger level

~~~sql
FOR EACH ROW
~~~

and:

~~~sql
FOR EACH STATEMENT
~~~

specify whether the trigger runs per row or once per SQL statement.

### 3.2. Default is statement-level

If you omit the `FOR EACH ...` clause altogether, PostgreSQL defaults to creating a **statement-level trigger**. To avoid misreading by others, specify the level explicitly in DDL.

### 3.3. DML events

- `INSERT`: inserting rows.
- `UPDATE`: updating rows.
- `DELETE`: deleting rows.
- `TRUNCATE`: quickly emptying one or more tables, distinct from `DELETE FROM ...`.

### 3.4. Timing

- `BEFORE`: before the corresponding operation.
- `AFTER`: after the corresponding operation per trigger mechanics.
- `INSTEAD OF`: replaces the operation on a view with trigger logic.

## 4. Comparison Table: ROW vs. STATEMENT

| Criterion | `FOR EACH ROW` | `FOR EACH STATEMENT` |
| --- | --- | --- |
| Calls for a 100-row UPDATE | 100 times (if all rows qualify) | 1 time |
| Calls for a 0-row UPDATE | 0 | 1 |
| Access per-row `NEW` / `OLD` | Yes, for applicable events | No direct row `NEW`/`OLD` |
| Can `BEFORE` modify `NEW`? | Yes, for INSERT/UPDATE on eligible tables | No |
| Can `RETURN NULL` skip an operation on a row? | Yes, in `BEFORE ROW` | No |
| Suitable for single-record auditing | Yes | Needs transition table for multi-row detail |
| Suitable for logging a statement | Possible, but duplicates entries per row | Very suitable |
| Summing a 10,000-row batch | Easily becomes N+1 / 10,000 writes | Can be set-based with transition tables |
| `TRUNCATE` | Not supported | Yes |
| `INSTEAD OF` on views | Yes | No |
| `WHEN` in standard triggers | Supported with applicable conditions | Not supported |

**Key takeaway:** a statement trigger does not automatically know "which rows changed" from `TG_OP` alone. To get the affected row set, use transition relations or a separate source design; do not reference `NEW.price` as in a row trigger.

## 5. BEFORE ROW, AFTER ROW, and BEFORE/AFTER STATEMENT

Different levels and timings serve different purposes.

### 5.1. BEFORE ROW

Commonly used to:

- Normalize input strings before saving.
- Populate `updated_at` or a derived attribute.
- Reject changes using `RAISE EXCEPTION`.
- Skip a row via `RETURN NULL` when explicitly designed to do so.

Example:

~~~sql
CREATE TRIGGER trg_before_write
BEFORE INSERT OR UPDATE
ON schema.table_name
FOR EACH ROW
EXECUTE FUNCTION schema.prepare_row();
~~~

### 5.2. AFTER ROW

Commonly used when you need to:

- Audit values that were actually accepted.
- Sync a row to an auxiliary table **within the same transaction**.
- Compute downstream effects tied to each written row.

### 5.3. BEFORE STATEMENT

Commonly used to log the start of a batch statement, perform appropriate statement-level checks, or block the entire statement before modifying data.

### 5.4. AFTER STATEMENT

Commonly used to summarize the outcome of a DML statement, record affected row counts, or process a batch of changes via transition relations.

### 5.5. Do Not Label AFTER as "Committed"

`AFTER` means after the operation in trigger semantics, **not after transaction COMMIT**. If an error happens later and the transaction rolls back, database changes made by triggers also roll back.

## 6. Trigger Functions and TG_* Context Variables

PL/pgSQL trigger functions have access to special variables:

| Variable | Contents |
| --- | --- |
| `TG_OP` | `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER`, or `INSTEAD OF` |
| `TG_LEVEL` | `ROW` or `STATEMENT` |
| `TG_NAME` | Name of the trigger invoking the function |
| `TG_TABLE_NAME` | Name of the table/view the trigger is attached to |
| `TG_TABLE_SCHEMA` | Schema of the table/view |
| `TG_RELID` | OID of the target relation |
| `TG_NARGS` | Number of arguments in the trigger definition |
| `TG_ARGV[index]` | Trigger argument; 0-based index |
| `NEW` | New record when applicable to the row event |
| `OLD` | Old record when applicable to the row event |

Context inspection example:

~~~sql
CREATE FUNCTION trigger_lab.describe_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE
        'Trigger %, level %, timing %, op %, table %.%',
        TG_NAME, TG_LEVEL, TG_WHEN, TG_OP,
        TG_TABLE_SCHEMA, TG_TABLE_NAME;

    RETURN NULL;
END;
$$;
~~~

This function is suitable for observing **statement-level or AFTER** triggers in the lab, where the return value is ignored. Do not attach it as `BEFORE ROW` on a table returning `NULL` unless you intend to **cancel each row's operation**.

### 6.1. TG_ARGV elements are text strings

~~~sql
EXECUTE FUNCTION schema.fn('audit', 'critical');
~~~

In PL/pgSQL, `TG_ARGV[0]` is the text `'audit'`. If you need a number, parse/cast and validate it appropriately.

### 6.2. TG_* variables differ from normal function parameters

`TG_OP` has no meaning outside a trigger function context. Trigger functions are invoked by PostgreSQL with system trigger context; applications do not call them like `SELECT fn(...)`.

## 7. OLD and NEW by Event

| Row event | `OLD` | `NEW` |
| --- | --- | --- |
| `INSERT` | No old row | Record being inserted |
| `UPDATE` | Record before update | Record after update |
| `DELETE` | Record before delete | No new record |
| `TRUNCATE` | No row trigger | No row trigger |

### 7.1. INSERT

~~~sql
IF TG_OP = 'INSERT' THEN
    RAISE NOTICE 'new id=%', NEW.product_id;
END IF;
~~~

### 7.2. UPDATE

~~~sql
IF TG_OP = 'UPDATE' THEN
    RAISE NOTICE 'price: % -> %',
        OLD.price, NEW.price;
END IF;
~~~

### 7.3. DELETE

~~~sql
IF TG_OP = 'DELETE' THEN
    RAISE NOTICE 'deleting id=%',
        OLD.product_id;
END IF;
~~~

### 7.4. Do not treat OLD/NEW at statement level as a virtual row

Inside a statement trigger there is no single `NEW` representing all 10,000 rows. If you need the list, see `REFERENCING NEW TABLE AS ...` in the transition tables section.

## 8. What Does the RETURN Value Control?

This is one of the easiest areas to get wrong.

### 8.1. BEFORE INSERT/UPDATE FOR EACH ROW

- `RETURN NEW`: lets PostgreSQL proceed with writing the row; writes any modified values in `NEW`.
- `RETURN NULL`: skips the operation for **the current row**, which normally prevents subsequent row triggers for that row from running.
- You can return a different row record of matching structure, though modifying `NEW` intentionally is usually clearer.

### 8.2. BEFORE DELETE FOR EACH ROW

- `RETURN OLD`: allows deletion of the row to proceed.
- `RETURN NULL`: skips deleting **the current row**.

### 8.3. AFTER ROW

The return value is **ignored**; the function must still return the `trigger` type, yet `RETURN NULL` does not undo a change that already occurred. To reject a change, use `RAISE EXCEPTION` to fail the statement/transaction according to rules.

### 8.4. BEFORE/AFTER STATEMENT

The return value is also ignored. For statement triggers, `RETURN NULL` is usually the simplest ending and **does not skip the SQL statement**.

### 8.5. INSTEAD OF ROW on views

The return value carries special meaning: if the trigger performs the operation, return `NEW` for INSERT/UPDATE or `OLD` for DELETE; `RETURN NULL` indicates skipping that row's operation, affecting row counts and `RETURNING`. We will cover an example separately.

## 9. Lab Setup: Products Table and Two Levels of Auditing

To compare directly, let's create:

~~~text
trigger_lab.products
       |
       +--- BEFORE ROW: normalize sku and updated_at
       |
       +--- AFTER ROW: log each row into product_row_audit
       |
       +--- AFTER STATEMENT: log row count into product_statement_audit
~~~

### 9.1. Create the schema

~~~sql
CREATE SCHEMA trigger_lab;
~~~

Run only on a test database; if the schema already exists, choose another lab schema name or clean the environment intentionally before proceeding.

### 9.2. Source table

~~~sql
CREATE TABLE trigger_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    price numeric(12,2) NOT NULL CHECK (price >= 0),
    stock integer NOT NULL CHECK (stock >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 9.3. Per-row audit table

~~~sql
CREATE TABLE trigger_lab.product_row_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL,
    operation text NOT NULL,
    before_row jsonb,
    after_row jsonb,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    actor_name text NOT NULL DEFAULT current_user
);
~~~

Do not place a foreign key from audit to products: if a product is deleted, the audit log still needs to record the deleted ID and keep its snapshot. Retention and security policies for auditing should be designed separately.

### 9.4. Per-statement audit table

~~~sql
CREATE TABLE trigger_lab.product_statement_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation text NOT NULL,
    rows_affected bigint NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source_table text NOT NULL
);
~~~

This table stores **one row per statement-level trigger invocation**, rather than one row per product.

## 10. BEFORE ROW Function Normalizing Values

~~~sql
CREATE FUNCTION trigger_lab.prepare_product_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.sku := upper(btrim(NEW.sku));
    NEW.updated_at := clock_timestamp();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_10_prepare_product
BEFORE INSERT OR UPDATE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.prepare_product_row();
~~~

### 10.1. What gets modified?

Given `sku=' ab-01 '`, the trigger sets `NEW.sku='AB-01'` before the row is written.

### 10.2. Why RETURN NEW?

If the function returned `NULL` in `BEFORE ROW`, the row operation would be skipped. Returning `NEW` lets the system proceed using the normalized values.

### 10.3. updated_at and timestamps

`clock_timestamp()` reads the wall-clock time at invocation. It may vary across rows in a multi-row statement; if business rules want every row in a statement to share a single timestamp, consider `statement_timestamp()` or an explicitly supplied application timestamp.

### 10.4. Do not update the same table with UPDATE

Inside `BEFORE ROW`, assigning `NEW.sku := ...` is far better than executing:

~~~sql
UPDATE trigger_lab.products
SET sku = ...
WHERE product_id = NEW.product_id;
~~~

A nested `UPDATE` can cause trigger recursion, extra locking, and overhead. For columns on the very row being processed, modify `NEW`.

## 11. AFTER ROW Function Recording Per-Row History

~~~sql
CREATE FUNCTION trigger_lab.audit_product_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            NEW.product_id, TG_OP, NULL, to_jsonb(NEW)
        );
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            NEW.product_id, TG_OP,
            to_jsonb(OLD), to_jsonb(NEW)
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            OLD.product_id, TG_OP, to_jsonb(OLD), NULL
        );
        RETURN OLD;
    END IF;

    RAISE EXCEPTION 'Unexpected trigger operation %', TG_OP;
END;
$$;

CREATE TRIGGER trg_20_audit_product_row
AFTER INSERT OR UPDATE OR DELETE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.audit_product_row();
~~~

### 11.1. Why use AFTER?

At AFTER time, the trigger sees the row values after any relevant `BEFORE` processing, so auditing captures the actual operated data, such as normalized `sku='AB-01'`.

### 11.2. Storing JSONB snapshots

`to_jsonb(OLD)` and `to_jsonb(NEW)` store before/after row representations. This is convenient for auditing, though it can consume significant space if rows are very wide, contain sensitive fields, or have large JSONB payloads.

### 11.3. Audit entries are transactional data

Writes into `product_row_audit` occur inside **the same transaction** as the original DML. If the transaction rolls back, these audit rows also roll back. They are not immutable logs that survive every rollback or an external out-of-database audit log.

### 11.4. RETURN in AFTER ROW

The function returns `NEW`/`OLD` for clarity, yet in `AFTER ROW` the return value does not control whether the original row is written. Do not return `NULL` in AFTER hoping to cancel an INSERT.

## 12. AFTER STATEMENT Function Using Transition Tables

We want to write a single summary row for each `INSERT`, `UPDATE`, or `DELETE`; do not run `COUNT(*)` over the entire source table because that cannot tell how many rows **the current statement alone** affected.

PostgreSQL provides **transition relations** when the trigger is declared appropriately:

~~~sql
CREATE FUNCTION trigger_lab.audit_product_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT count(*)
        INTO v_rows
        FROM old_rows;
    ELSE
        SELECT count(*)
        INTO v_rows
        FROM new_rows;
    END IF;

    INSERT INTO trigger_lab.product_statement_audit (
        operation, rows_affected, source_table
    ) VALUES (
        TG_OP, v_rows, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    );

    RETURN NULL;
END;
$$;
~~~

`old_rows` and `new_rows` here **are not ordinary tables**. They are aliases provided by the trigger definition for the changed row sets during statement execution. Only the matching branch accesses the transition table available for that event type.

### 12.1. Trigger for INSERT

~~~sql
CREATE TRIGGER trg_30_products_insert_stmt
AFTER INSERT
ON trigger_lab.products
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.2. Trigger for UPDATE

~~~sql
CREATE TRIGGER trg_31_products_update_stmt
AFTER UPDATE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.3. Trigger for DELETE

~~~sql
CREATE TRIGGER trg_32_products_delete_stmt
AFTER DELETE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.4. Why split into three CREATE TRIGGER statements?

When using transition tables, PostgreSQL enforces event and trigger-definition constraints. Separating `INSERT`, `UPDATE`, and `DELETE` clarifies which `OLD TABLE`/`NEW TABLE` relations are exposed and avoids multi-event definitions that are invalid with transition relations.

### 12.5. RETURN NULL in AFTER STATEMENT

This is a valid return value and is ignored; it does not mean the executed SQL statement was cancelled.

## 13. Running a Multi-Row INSERT: Comparing Invocation Counts

~~~sql
INSERT INTO trigger_lab.products (
    product_id, sku, price, stock
) VALUES
    (1, ' ab-01 ', 10.00, 5),
    (2, ' kb-02',  20.00, 10),
    (3, 'mi-03 ',  30.00, 0);
~~~

This is **one INSERT statement** creating three rows.

### 13.1. Output from BEFORE ROW

~~~sql
SELECT
    product_id, sku, price, stock, updated_at
FROM trigger_lab.products
ORDER BY product_id;
~~~

The SKUs are normalized:

~~~text
1  AB-01  10.00   5
2  KB-02  20.00  10
3  MI-03  30.00   0
~~~

### 13.2. Row audit results

~~~sql
SELECT audit_id, operation, product_id,
       after_row ->> 'sku' AS sku
FROM trigger_lab.product_row_audit
ORDER BY audit_id;
~~~

There are **3 INSERT entries** in `product_row_audit` because the `AFTER ROW` trigger ran for all three products.

### 13.3. Statement audit results

~~~sql
SELECT operation, rows_affected, source_table
FROM trigger_lab.product_statement_audit
ORDER BY audit_id;
~~~

There is **1 INSERT entry** with `rows_affected=3`. The `new_rows` transition table held the three rows from the INSERT statement, even if the base table holds many more rows later.

### 13.4. Audit row count is not total system statements

In this lesson, logs are generated only when operations on `trigger_lab.products` fire triggers. `SELECT` statements do not fire these DML triggers; operations on the audit tables do not pass through products triggers either.

## 14. Multi-Row UPDATE: ROW Runs Multiple Times

~~~sql
UPDATE trigger_lab.products
SET price = price + 5
WHERE product_id IN (1, 2);
~~~

Result:

- Product 1: price `10.00 -> 15.00`.
- Product 2: price `20.00 -> 25.00`.
- `BEFORE ROW` ran **2 times**.
- `AFTER ROW` ran **2 times** to write audit entries.
- `AFTER STATEMENT` ran **1 time**, recording `rows_affected=2`.

### 14.1. Inspecting before/after differences

~~~sql
SELECT
    product_id,
    before_row ->> 'price' AS old_price,
    after_row ->> 'price' AS new_price
FROM trigger_lab.product_row_audit
WHERE operation = 'UPDATE'
ORDER BY audit_id;
~~~

### 14.2. Large multi-row UPDATEs

With 100,000 rows, row auditing creates 100,000 INSERTs into the audit table, sharply increasing WAL, storage, and transaction latency. Statement auditing inserts only one row, though reading the transition table (if used) still scales with the number of modified rows.

### 14.3. Do not automatically treat UPDATE as a "value change"

PostgreSQL can process `UPDATE products SET stock = stock` as a row UPDATE operation even though `stock` did not change. Row `UPDATE` triggers still run; if you only want to audit actual field changes, use `WHEN (OLD.field IS DISTINCT FROM NEW.field)` or another condition.

## 15. UPDATE Matching Zero Rows: STATEMENT Still Runs

~~~sql
UPDATE trigger_lab.products
SET stock = 999
WHERE product_id < 0;
~~~

With our lab data, no product has a negative ID.

### 15.1. Outcome

- Zero rows are actually updated.
- Zero row-level UPDATE trigger invocations occur.
- Statement-level UPDATE trigger is still invoked **once**.
- Transition table `new_rows` is empty.
- `product_statement_audit` receives one row: `UPDATE, rows_affected=0`.

### 15.2. Useful property for command logging

If the goal is knowing the application **attempted an UPDATE command**, a statement trigger captures it even when zero rows match.

### 15.3. Do not confuse this with logging every SQL query

DML statement triggers do not observe `SELECT` statements and do not log queries against other tables. They bind only to declared events on a specific relation.

### 15.4. Do failed statements produce durable audit logs?

If a statement throws an exception and the transaction rolls back, the statement audit record is not committed either. To log **failed** statements without losing them on rollback, design dedicated out-of-transaction logging/observability.

## 16. Multi-Row DELETE and OLD

~~~sql
DELETE FROM trigger_lab.products
WHERE product_id = 3;
~~~

### 16.1. BEFORE/AFTER ROW for DELETE

Only `OLD` holds the deleted product record. The audit row stores `before_row=to_jsonb(OLD)` and `after_row=NULL`.

### 16.2. Transition OLD TABLE

The statement-level DELETE trigger reads `old_rows` to inspect the **deleted row set** and count rows, rather than querying `products` after deletion (since those rows are gone).

### 16.3. Lab results

~~~sql
SELECT operation, rows_affected
FROM trigger_lab.product_statement_audit
ORDER BY audit_id;
~~~

Following the sequence of operations run so far, the statement audit rows are:

| operation | rows_affected |
| --- | ---: |
| INSERT | 3 |
| UPDATE | 2 |
| UPDATE | 0 |
| DELETE | 1 |

Row auditing has 3 INSERTs, 2 UPDATEs, and 1 DELETE—6 rows total from the basic examples.

## 17. Verifying Atomicity With ROLLBACK

Run a temporary change:

~~~sql
BEGIN;

UPDATE trigger_lab.products
SET price = price + 100
WHERE product_id = 1;

SELECT price
FROM trigger_lab.products
WHERE product_id = 1;

SELECT operation, product_id
FROM trigger_lab.product_row_audit
ORDER BY audit_id DESC
LIMIT 1;

ROLLBACK;
~~~

### 17.1. What happens?

Inside the transaction before rollback, SELECT sees the increased product price and the audit entry written by the trigger within the same transaction.

After `ROLLBACK`, both the product update **and** its corresponding audit row cease to exist.

### 17.2. Identity sequences may still leave gaps

PostgreSQL sequences do not share the same rollback semantics as table rows. After a rolled-back transaction, `audit_id` may skip numbers. Never assume auditing failed simply because IDs have gaps.

### 17.3. External side effects do not auto-rollback

If a trigger calls an extension with external side effects, sends email, or makes HTTP requests outside transaction boundaries, those actions may not be undone when the database rolls back. For reliable integrations, use a **transactional outbox** or post-commit worker architecture.

## 18. WHEN in Row Triggers

When you care only about genuine price changes, add a condition:

~~~sql
CREATE TABLE trigger_lab.price_change_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL,
    old_price numeric(12,2) NOT NULL,
    new_price numeric(12,2) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION trigger_lab.log_price_change_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.price_change_log (
        product_id, old_price, new_price
    ) VALUES (
        NEW.product_id, OLD.price, NEW.price
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_40_price_changed
AFTER UPDATE
ON trigger_lab.products
FOR EACH ROW
WHEN (OLD.price IS DISTINCT FROM NEW.price)
EXECUTE FUNCTION trigger_lab.log_price_change_row();
~~~

### 18.1. IS DISTINCT FROM beats <> when NULLs exist

`IS DISTINCT FROM` handles SQL `NULL` explicitly. In this lab price is `NOT NULL`, yet this pattern is invaluable for nullable columns.

### 18.2. Testing an unchanged price

~~~sql
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

General UPDATE triggers may still run on the row, yet `trg_40_price_changed` writes no new log entry because `OLD.price` and `NEW.price` do not differ.

### 18.3. Testing a changed price

~~~sql
UPDATE trigger_lab.products
SET price = 17.50
WHERE product_id = 1;
~~~

Now the trigger with `WHEN` fires and inserts a dedicated price-change log row.

### 18.4. WHEN is not the source statement's WHERE

`WHERE product_id = 1` selects which rows to update; `WHEN (OLD.price IS DISTINCT FROM NEW.price)` only decides **whether a row trigger invokes its function** after an affected row has been identified.

## 19. WHEN With BEFORE and AFTER

For `BEFORE ROW`, the `WHEN` expression is evaluated before invoking the trigger function. For `AFTER ROW`, the condition can be evaluated right after the row operation to avoid queuing unnecessary trigger events.

### 19.1. Statement level does not support standard WHEN

Do not write:

~~~sql
-- Invalid for a standard statement trigger:
-- CREATE TRIGGER ...
-- AFTER UPDATE ON ...
-- FOR EACH STATEMENT
-- WHEN (NEW.price > 0)
-- EXECUTE FUNCTION ...;
~~~

There is no single-row `NEW` at statement level. Conditions over the whole dataset belong inside the function, which can inspect transition tables.

### 19.2. WHEN cannot contain arbitrary subqueries

Predicates in `WHEN` have syntax restrictions, specifically disallowing direct subqueries. If logic requires looking up another table, move it inside the trigger function with explicit transaction and locking awareness rather than trying to write a `SELECT` inside `WHEN`.

### 19.3. Do not avoid WHEN just to reduce function logic, or vice versa

If a business rule is extremely complex, a function with clear, well-tested conditional branches can be easier to maintain than a sprawling `WHEN` clause. The trade-off is the function-call overhead when the condition does not match.

## 20. UPDATE OF column: Mentioned Column, Not Necessarily Value Changed

Syntax:

~~~sql
CREATE TRIGGER trg_update_price_listed
AFTER UPDATE OF price
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.log_price_change_row();
~~~

**This illustrates the event selection criterion**; if you actually create this in the lab, note that it will write a price log on every UPDATE listing `price` in `SET`, even when the price stays identical.

### 20.1. UPDATE OF price

It primarily checks whether the `UPDATE` statement references `price` as an updated target (per PostgreSQL rules), **without guaranteeing the price actually changed**.

### 20.2. Compared with WHEN

~~~sql
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

Here `UPDATE OF price` matches because `price` is listed, whereas `WHEN (OLD.price IS DISTINCT FROM NEW.price)` evaluates to false.

### 20.3. BEFORE triggers may modify additional columns

If a `BEFORE UPDATE` trigger alters `NEW.price` even though the original query omitted `price` from `SET`, that alone does not trigger `UPDATE OF price`. This is why **column-targeted events** and **OLD/NEW comparison** differ.

### 20.4. Do not arbitrarily combine UPDATE OF with transition tables

With PostgreSQL transition relations, an `UPDATE` trigger using `REFERENCING OLD TABLE/NEW TABLE` **cannot specify an `UPDATE OF column` list**. In the lab, the statement trigger uses `AFTER UPDATE` without `OF price`.

## 21. Transition Tables: Statement-Wide OLD and NEW Sets

This mechanism lets statement triggers know not just `TG_OP`, but also **the exact rows that changed**.

| DML | Common transition relation | Contents |
| --- | --- | --- |
| INSERT | `REFERENCING NEW TABLE AS new_rows` | Inserted rows |
| UPDATE | `OLD TABLE AS old_rows` and `NEW TABLE AS new_rows` | Before and after update |
| DELETE | `REFERENCING OLD TABLE AS old_rows` | Deleted rows |
| TRUNCATE | No row transition tables | No corresponding row-level set |

### 21.1. Transition relations exist only during trigger execution

You cannot run:

~~~sql
SELECT * FROM new_rows;
~~~

from a normal SQL session expecting to see a previous trigger's transition table. `new_rows` exists only inside the execution context of the trigger declaring `REFERENCING NEW TABLE AS new_rows`.

### 21.2. Distinct from per-row OLD and NEW

`OLD` and `NEW` inside a row trigger are **single records**. `old_rows` and `new_rows` from transition tables are **row sets** queryable with set-based SQL.

### 21.3. AFTER triggers are the primary scope

Transition relations are available for supported `AFTER` triggers on eligible relations. They are not a general option to turn any `BEFORE STATEMENT` trigger into one that sees all rows about to change.

### 21.4. Alias names are defined in DDL

The names `old_rows` and `new_rows` are not fixed keywords. You can pick other names:

~~~sql
REFERENCING OLD TABLE AS previous_rows
            NEW TABLE AS current_rows
~~~

Then the function must query those exact aliases.

## 22. Set-Based Aggregation With Transition Tables

Suppose we want to compute the **total price delta** of an `UPDATE` statement without writing one log row per product.

### 22.1. Create a batch log table

~~~sql
CREATE TABLE trigger_lab.price_batch_audit (
    batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_products bigint NOT NULL,
    total_price_delta numeric(14,2) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 22.2. AFTER STATEMENT function

~~~sql
CREATE FUNCTION trigger_lab.log_price_batch()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_count bigint;
    v_delta numeric(14,2);
BEGIN
    SELECT
        count(*),
        coalesce(sum(n.price - o.price), 0)
    INTO v_count, v_delta
    FROM old_rows AS o
    JOIN new_rows AS n
      ON n.product_id = o.product_id
    WHERE o.price IS DISTINCT FROM n.price;

    INSERT INTO trigger_lab.price_batch_audit (
        changed_products,
        total_price_delta
    ) VALUES (
        v_count, v_delta
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_50_price_batch
AFTER UPDATE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.log_price_batch();
~~~

### 22.3. Run a multi-row UPDATE

~~~sql
UPDATE trigger_lab.products
SET price = price + 2
WHERE product_id IN (1, 2);
~~~

The trigger computes the delta using **a single SELECT** over the two transition tables rather than issuing separate aggregate queries inside every row trigger.

### 22.4. Limitation of key-based JOINs

The example joins `old_rows`/`new_rows` on `product_id` because the lab **never changes primary keys**. If an UPDATE statement can modify the join key itself, old and new rows will fail to pair on the same key value. You would need a stable identifier or another pairing mechanism.

### 22.5. Do not assume every UPDATE changes price

`o.price IS DISTINCT FROM n.price` ensures only products whose prices actually changed are counted. An UPDATE modifying only `stock` still fires the statement trigger, yet the batch log entry records `changed_products=0` and `total_price_delta=0`.

### 22.6. Set-based is not free

PostgreSQL still builds and scans the transition row sets. For updates touching millions of rows, the cost can be substantial, though it usually avoids many internal SQL round trips and unnecessary per-row logs.

## 23. Do Not Confuse Statement Triggers With Transaction Triggers

One transaction can contain multiple SQL statements:

~~~sql
BEGIN;

UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = 1;

UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = 2;

COMMIT;
~~~

`AFTER UPDATE FOR EACH STATEMENT` will fire **twice** in this example, not once for the whole transaction.

### 23.1. One statement affecting many rows

A single statement:

~~~sql
UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id IN (1, 2);
~~~

fires the statement trigger **once**, even though two rows changed.

### 23.2. Want to audit "once per transaction"?

You cannot simply write `FOR EACH TRANSACTION` on a DML `CREATE TRIGGER`: PostgreSQL has no such DML trigger level. You can design transaction IDs, outboxes, or collectors depending on the problem, accounting for retries, savepoints, and multiple statements per transaction.

### 23.3. Transaction ID is not always "request ID"

One HTTP request may open multiple transactions; multiple operations inside one transaction do not automatically share a business request ID either. For business tracing, pass a correlation ID via an application pattern or properly managed session metadata.

## 24. TRUNCATE: Statement-Level Only

`TRUNCATE` does not process rows individually the way `DELETE` does, so it **does not fire row-level DELETE triggers**.

### 24.1. Create a TRUNCATE trigger

~~~sql
CREATE FUNCTION trigger_lab.audit_product_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.product_statement_audit (
        operation, rows_affected, source_table
    ) VALUES (
        TG_OP,
        0,
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_60_products_truncate_stmt
AFTER TRUNCATE
ON trigger_lab.products
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_truncate();
~~~

### 24.2. Meaning of rows_affected=0 in the example

This is an **illustrative/sentinel value** because TRUNCATE triggers do not have a transition table of deleted rows. It **does not claim TRUNCATE deleted exactly 0 rows**. In a real system, use a nullable column or a `count_known=false` flag instead of recording a misleading `0`.

### 24.3. Test in a transaction and roll back

~~~sql
BEGIN;

TRUNCATE TABLE trigger_lab.products;

SELECT count(*) FROM trigger_lab.products;

ROLLBACK;
~~~

After rollback, both the table data and the TRUNCATE audit row from that transaction are reverted per transaction semantics. Note that `TRUNCATE` acquires strong locks and has special MVCC considerations; test only in a lab.

### 24.4. DELETE differs from TRUNCATE

~~~sql
DELETE FROM trigger_lab.products;
~~~

fires DELETE row triggers for each product as well as DELETE statement triggers. Conversely, `TRUNCATE` fires only `ON TRUNCATE` triggers, never DELETE row audits.

### 24.5. Privileges and FKs

`TRUNCATE` requires appropriate privileges and interacts with foreign keys; it is not a universal bypass around referential integrity logic.

## 25. INSTEAD OF Triggers on Views

A view sometimes requires custom write behavior instead of updating base tables via the default path.

### 25.1. Create a simple view

~~~sql
CREATE VIEW trigger_lab.v_catalog AS
SELECT
    product_id, sku, price, stock
FROM trigger_lab.products;
~~~

### 25.2. Create an INSTEAD OF INSERT function

~~~sql
CREATE FUNCTION trigger_lab.insert_catalog_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.products (
        product_id, sku, price, stock
    ) VALUES (
        NEW.product_id, NEW.sku, NEW.price, NEW.stock
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_insert_catalog
INSTEAD OF INSERT
ON trigger_lab.v_catalog
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.insert_catalog_row();
~~~

### 25.3. INSERT through the view

~~~sql
INSERT INTO trigger_lab.v_catalog (
    product_id, sku, price, stock
) VALUES (
    4, 'ca-04 ', 15.00, 7
);

SELECT product_id, sku
FROM trigger_lab.products
WHERE product_id = 4;
~~~

In the source table, `sku` is normalized by `products`'s `BEFORE INSERT ROW` trigger, so the stored value is `CA-04`.

### 25.4. INSTEAD OF is ROW-level only

There is no `INSTEAD OF ... FOR EACH STATEMENT` equivalent. If you need a statement-level trigger on a view, PostgreSQL supports `BEFORE/AFTER STATEMENT` models, while `INSTEAD OF` for replacing each view operation is row-level.

### 25.5. RETURNING and NEW

`RETURN NEW` indicates the trigger handled the row, yet the values emitted by `INSERT ... RETURNING` on the view depend on the row record returned by the trigger. If the base table normalizes `sku`, returning the view's untouched `NEW` may still return the unnormalized input `sku`. If the API needs exact persisted values, design the trigger/view to populate `NEW` from `RETURNING *` rather than assuming view `NEW` reflects base-table transformations.

### 25.6. Do not use INSTEAD OF on regular tables

`INSTEAD OF` is for views under supported rules; on tables, use `BEFORE`/`AFTER` or standard SQL constructs.

## 26. Triggers on Partitioned Tables

Partitioning requires a clear understanding of the relationship between row-level and statement-level triggers.

### 26.1. Statement triggers attached to the parent table

When DML targets a partitioned parent, statement-level triggers on the **parent table** fire for that statement; statement-level triggers defined individually on child partitions do not automatically fire merely because rows were routed to them during the same command.

### 26.2. Row triggers execute where rows are operated on

Row-level triggers on a partitioned table are cloned/maintained onto partitions per PostgreSQL's mechanism and version. Whichever partition receives a routed row runs the corresponding row trigger on that actual partition.

### 26.3. SQL targeting a child partition directly

If an application sends `INSERT/UPDATE/DELETE` directly to a child partition instead of the parent, the statement-level trigger that runs belongs to the **targeted child partition**, not automatically the parent.

### 26.4. UPDATE moving rows across partitions

When changing a partition key moves a row to another partition, PostgreSQL may execute the row-level operation as a DELETE on the source partition and an INSERT on the destination partition, following specific row-movement trigger rules. Do not build simple audits assuming "every partition move produces a single UPDATE ROW event."

### 26.5. Transition relations on parent tables

In supported versions, transition tables on a statement trigger attached to a partitioned parent can represent affected rows across partitions per statement semantics. Test real examples on your deployed PostgreSQL version, especially when row movement occurs.

### 26.6. Do not arbitrarily change partition keys in BEFORE ROW to reroute rows

PostgreSQL places restrictions on modifying a partition key inside a BEFORE ROW trigger when that change would move the row to a different partition. If complex routing is needed, determine the partition key in the application/query or use an appropriate design rather than expecting a BEFORE trigger to reroute targets freely.

## 27. Ordering of Multiple Triggers of the Same Kind

A single table can have multiple triggers sharing the same event, timing, and level.

### 27.1. PostgreSQL orders by trigger name

Triggers of the same kind and matching event conditions are fired by PostgreSQL in **alphabetical order by trigger name**. Thus naming conventions such as:

~~~text
trg_10_normalize
trg_20_validate
trg_30_audit
~~~

help express intended execution order within a trigger tier.

### 27.2. Effects of BEFORE ROW

A `BEFORE ROW` trigger can return a modified `NEW`, and a subsequent `BEFORE ROW` trigger sees those modified values. If an earlier trigger returns `NULL`, subsequent row processing for that row is skipped.

### 27.3. AFTER ROW cannot modify NEW to rewrite the row

An AFTER ROW function receives `NEW`, yet modifying `NEW` and returning it does not alter the already-written row. To normalize columns on the target row, use `BEFORE ROW` or adjust the source SQL statement.

### 27.4. Do not rely on alphabetical order across different timings

`BEFORE`/`AFTER` and row/statement timings enforce their own execution phases. Never write logic assuming an AFTER STATEMENT trigger will run before a BEFORE ROW trigger just because its name comes first alphabetically.

## 28. ON CONFLICT and Both INSERT/UPDATE Trigger Types

~~~sql
INSERT INTO trigger_lab.products (
    product_id, sku, price, stock
) VALUES (
    1, 'AB-01', 99.00, 1
)
ON CONFLICT (product_id)
DO UPDATE SET price = EXCLUDED.price;
~~~

In an `INSERT ... ON CONFLICT DO UPDATE` statement, PostgreSQL can fire triggers along both the INSERT and UPDATE paths per detailed rules.

### 28.1. Statement-level triggers

With `ON CONFLICT DO UPDATE`, statement-level triggers for both INSERT and UPDATE can fire **even when the UPDATE branch modifies zero rows**, following PostgreSQL's ordering rules.

### 28.2. Row-level BEFORE events

On a conflicting row, effects from both `BEFORE INSERT ROW` and `BEFORE UPDATE ROW` can participate when executing the update branch. If normalization logic is not idempotent, results can be surprising.

### 28.3. Do not add statement counts as a product count

If an UPSERT statement fires both INSERT and UPDATE statement triggers, you cannot sum statement-level invocations to deduce how many products were inserted or updated. Read transition tables or per-event DML outcomes instead.

### 28.4. ON CONFLICT DO NOTHING

An INSERT that hits a conflict and takes `DO NOTHING` is still an INSERT statement; matching statement-level INSERT triggers can still run, while no new row exists to fire AFTER INSERT ROW.

### 28.5. MERGE

PostgreSQL versions supporting `MERGE` apply trigger rules according to the `INSERT`/`UPDATE`/`DELETE` actions defined in the statement and the rows actually flowing through each branch. Never assume a MERGE statement maps to a single generic trigger event; consult your version's semantics and test plans/cases.

## 29. Constraint Triggers and Deferral Timing

PostgreSQL also provides **constraint triggers** to enforce integrity checks that can be deferred across a transaction.

### 29.1. Differing from regular DML triggers

User-defined constraint triggers created with `CREATE CONSTRAINT TRIGGER` have restrictions: they are **AFTER ROW triggers** on supported relations and may be declared `DEFERRABLE` and `INITIALLY DEFERRED`.

### 29.2. Illustrative syntax example

~~~sql
-- Illustrative pattern; define enforce_rule()
-- matching an invariant before executing.
--
-- CREATE CONSTRAINT TRIGGER trg_business_rule
-- AFTER INSERT OR UPDATE
-- ON trigger_lab.products
-- DEFERRABLE INITIALLY DEFERRED
-- FOR EACH ROW
-- EXECUTE FUNCTION trigger_lab.enforce_rule();
~~~

### 29.3. SET CONSTRAINTS

For eligible constraint triggers, `SET CONSTRAINTS ... IMMEDIATE/DEFERRED` can change check timing within the transaction per PostgreSQL rules.

### 29.4. WHEN has its own timing

For a constraint trigger with `WHEN`, the row event condition is evaluated **immediately when the row changes**, not deferred until transaction end like the function invocation itself. This affects whether the event gets queued.

### 29.5. Do not replace simple FK/UNIQUE with triggers

PostgreSQL has dedicated constraint machinery for `FOREIGN KEY`, `UNIQUE`, and `CHECK`. Whenever a business rule fits a standard constraint, using the constraint is easier to make correct and optimize than rolling custom locking/checking inside triggers.

## 30. Concurrent Transactions and Correctness

Trigger functions run inside **the original DML statement's transaction**, yet that alone does not make cross-row checks free of race conditions.

### 30.1. Inventory check example

Suppose two transactions both try to buy the last 5 units of a product, and both triggers run:

~~~sql
SELECT stock
FROM trigger_lab.products
WHERE product_id = 1;
~~~

If both inspect stock without proper locking or atomic updates, both can conclude enough stock exists and oversell inventory.

### 30.2. Prefer conditional updates

A clearer pattern:

~~~sql
UPDATE trigger_lab.products
SET stock = stock - 5
WHERE product_id = 1
  AND stock >= 5
RETURNING product_id, stock;
~~~

The application checks whether a row was returned; PostgreSQL uses row locks and appropriate rechecks to serialize contention on that row. Pair this with proper transaction and business rules.

### 30.3. Isolation levels still matter

`READ COMMITTED`, `REPEATABLE READ`, and `SERIALIZABLE` have distinct semantics. Triggers do not bypass MVCC or automatically establish serializable business invariants. For complex cross-table checks, evaluate locking, constraints, isolation, and retries.

### 30.4. Do not trigger external side effects before COMMIT

A trigger calling external payment or email APIs can cause side effects even if the DB rolls back. Designing an in-transaction outbox and post-commit worker is usually far better for system integrations.

## 31. Errors in Triggers and Transaction Rollback

~~~sql
CREATE FUNCTION trigger_lab.reject_negative_stock()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.stock < 0 THEN
        RAISE EXCEPTION
            'Stock cannot be negative for product %',
            NEW.product_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
~~~

You could attach this as `BEFORE INSERT OR UPDATE FOR EACH ROW`, though the lab already has `CHECK (stock >= 0)`—this example merely contrasts mechanisms; **no redundant trigger is needed**.

### 31.1. RAISE EXCEPTION

An unhandled exception fails the statement; DML changes and trigger-written audit entries created in the statement are not committed under transaction semantics.

### 31.2. Do not confuse with RETURN NULL

`RETURN NULL` in BEFORE ROW only skips **one row**, without signaling an error to the caller the way `RAISE EXCEPTION` does. If invalid data must fail loudly, an exception or constraint is more appropriate.

### 31.3. Try/catch in PL/pgSQL

PL/pgSQL provides `EXCEPTION WHEN ...` with subtransaction semantics inside error-handling blocks. Catching every exception and ignoring it, however, can mislead the caller into thinking DML succeeded even when a business rule failed. Only catch well-understood errors and keep contracts explicit.

### 31.4. Do statement triggers run after a statement fails?

Do not rely on an AFTER STATEMENT trigger to log a successful audit entry for a failed command; exceptions abort/roll back statement and transaction flow per rules. Failure logging requires a separate mechanism.

## 32. Performance Impact: O(rows) and N+1

A row trigger firing 10,000 times can become very expensive if each invocation runs:

~~~sql
SELECT sum(...)
FROM some_large_table
WHERE ...;
~~~

### 32.1. Database-side N+1

A large SQL UPDATE can spawn N auxiliary queries inside a trigger even though the application sent **only one SQL statement**. This performance bottleneck is often missed when looking only at application-side round trips.

### 32.2. Switch to a statement trigger with transition tables

Instead of:

~~~text
10000 row trigger calls
    -> 10000 SELECTs
    -> 10000 audit row INSERTs
~~~

consider:

~~~text
1 statement trigger
    -> 1 set-based SELECT on NEW TABLE/OLD TABLE
    -> 1 summary INSERT or batch INSERT SELECT
~~~

### 32.3. Statement triggers are not always better

If you need **full per-row OLD/NEW** auditing, a simple row trigger paired with reasonable audit indexing/partitioning can be cleaner and safer. Transition tables still need to iterate over rows when recording detailed entries.

### 32.4. Measure write latency too

Evaluate triggers using:

- INSERT/UPDATE/DELETE duration.
- WAL volume and audit table size.
- Lock waits and deadlocks.
- CPU, buffer accesses, and temporary files.
- Autovacuum and audit retention.

### 32.5. Measurement tip

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

**Note:** `EXPLAIN ANALYZE` actually executes the DML statement; to measure safely, wrap it in a lab transaction and `ROLLBACK`, keeping in mind sequence values do not roll back. In many plans, PostgreSQL breaks down trigger timing statistics by trigger name.

## 33. Audit Tables: Storage and Retention

Storing both `before_row` and `after_row` as JSONB is convenient, but comes with cost.

### 33.1. Do not duplicate PII unnecessarily

If product records carry sensitive metadata, auditing duplicates that data. Apply matching masking, access control, encryption, and retention policies.

### 33.2. Store only needed fields

Sometimes you only need:

~~~text
product_id
old_price
new_price
changed_at
actor
~~~

rather than full-row snapshots.

### 33.3. Purge audits per policy

Audit tables grow with every change. Partition by time, archive, or prune according to approved retention policies; never let a lightweight audit trigger grow into an unmanaged multi-billion-row table.

### 33.4. Trigger audits are not an absolute event bus

Audit rows are written inside transactions and can roll back. They reflect only DML paths that passed through enabled triggers on covered tables. To publish events reliably to external systems after commit, consider an outbox or CDC.

## 34. Recursion and Self-Triggering Loops

A function attached to `products` executing:

~~~sql
UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = NEW.product_id;
~~~

while already handling an UPDATE on `products` can re-fire the trigger and loop.

### 34.1. Modify NEW in BEFORE ROW for same-row edits

~~~sql
NEW.stock := NEW.stock + 1;
RETURN NEW;
~~~

updates a column of the row currently being processed without issuing a new UPDATE statement.

### 34.2. pg_trigger_depth()

PostgreSQL provides `pg_trigger_depth()` to inspect current trigger nesting depth:

~~~sql
SELECT pg_trigger_depth();
~~~

Outside any trigger, it normally returns 0. Inside nested trigger chains, the depth increases accordingly.

### 34.3. Do not use depth guards to mask flawed logic

A check like:

~~~sql
IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
END IF;
~~~

may stop recursion in simple cases, yet simultaneously **skip legitimate behavior** when an operation is validly initiated by another trigger. Prefer designs free of cycles, idempotent conditions, and clear separation of responsibilities.

### 34.4. Deadlocks from cross-updating triggers

If table A's trigger updates B and table B's trigger updates A, two transactions operating in opposite orders can deadlock. Standardize lock ordering and minimize cross-table side effects in triggers.

## 35. Triggers and Foreign Key References

PostgreSQL uses internal trigger mechanisms for certain constraints such as foreign keys.

### 35.1. Never delete internal triggers

Some triggers listed in `pg_trigger` have `tgisinternal=true`; they are not equivalent to application-written audit triggers. Disabling or deleting them can break data integrity.

### 35.2. Ordering and cascades

Foreign key `ON DELETE CASCADE` or `ON UPDATE CASCADE` actions modify rows in other tables, firing triggers on those tables under PostgreSQL rules. Never look only at triggers on the initial SQL statement's table when assessing total side effects.

### 35.3. Do not replace FKs with ad-hoc "SELECT EXISTS" triggers

A `SELECT EXISTS(...)` check inside a row trigger is vulnerable to race conditions with concurrent transactions unless paired with proper locking/isolation. Standard FKs have built-in referential integrity concurrency handling.

## 36. Inspecting Triggers With pg_trigger

~~~sql
SELECT
    t.tgname AS trigger_name,
    c.oid::regclass AS table_name,
    t.tgenabled,
    t.tgisinternal,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c
  ON c.oid = t.tgrelid
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'trigger_lab'
ORDER BY c.relname, t.tgname;
~~~

### 36.1. tgenabled

Shows the trigger's enabled mode relative to session replication role. States correspond to origin/local enabled, replica-only, always, or disabled.

### 36.2. tgisinternal

Distinguishes system-generated triggers (such as constraint triggers) from user-defined triggers.

### 36.3. pg_get_triggerdef

Returns the textual DDL, letting you read events, timing, level, `WHEN`, transition tables, and target function without decoding the `tgtype` bitmask manually.

### 36.4. Inspecting the function body

~~~sql
SELECT pg_get_functiondef(
    'trigger_lab.audit_product_row()'::regprocedure
);
~~~

The trigger definition and the function body are **two separate pieces**; inspect both when investigating unexpected behavior.

## 37. Enabling, Disabling, and Dropping Triggers

### 37.1. Disabling an application-managed trigger

~~~sql
ALTER TABLE trigger_lab.products
DISABLE TRIGGER trg_20_audit_product_row;
~~~

### 37.2. Re-enabling it

~~~sql
ALTER TABLE trigger_lab.products
ENABLE TRIGGER trg_20_audit_product_row;
~~~

### 37.3. Do not toggle arbitrarily in production

While an audit trigger is disabled, UPDATEs and DELETEs proceed without writing audit rows. When re-enabled, PostgreSQL **does not retroactively backfill missed audit entries**.

### 37.4. DISABLE TRIGGER USER and ALL

`ALTER TABLE ... DISABLE TRIGGER USER` targets user triggers, whereas `ALL` affects internal constraint triggers too and requires higher privileges. Never use `DISABLE TRIGGER ALL` as an ad-hoc import speedup, as it can break integrity.

### 37.5. Dropping with table qualification

~~~sql
DROP TRIGGER IF EXISTS trg_20_audit_product_row
ON trigger_lab.products;
~~~

Removes the **trigger definition** without automatically dropping `trigger_lab.audit_product_row()`, since the function may be used elsewhere.

### 37.6. Do not confuse function and trigger

~~~sql
DROP FUNCTION trigger_lab.audit_product_row();
~~~

will be blocked if a trigger still depends on the function; never use `CASCADE` to bypass dependencies without understanding the impact.

## 38. session_replication_role and Replication Environments

PostgreSQL includes `session_replication_role` governing whether triggers and rules fire under replication modes.

### 38.1. Not a "fast-mode trigger off switch"

Changing `session_replication_role` can affect enforcement of critical constraints and triggers. Use it only under controlled DBA procedures, especially during replication or restores.

### 38.2. Distinguish ENABLE ALWAYS / ENABLE REPLICA

PostgreSQL provides trigger states controlling when triggers fire across replication roles. In logical replication setups, understand how auditing and integrity behave on the subscriber side.

### 38.3. Auditing only on primary?

Do not assume audit triggers on a subscriber run identically to the primary for every replicated change. Verify replication configuration, trigger states, and target tables.

## 39. Privileges and SECURITY DEFINER

Trigger functions can be declared `SECURITY INVOKER` or `SECURITY DEFINER` under PostgreSQL's routine security model.

### 39.1. Prefer least privilege

If a user may update products without having direct INSERT privileges on the audit table, consider a `SECURITY DEFINER` trigger function owned by a trusted role so auditing runs with the needed permissions.

### 39.2. search_path risks

When using `SECURITY DEFINER`, lock `search_path` to trusted schemas and `pg_temp` defensively, and use schema-qualified object names:

~~~sql
-- Illustrating the function declaration.
-- SECURITY DEFINER
-- SET search_path = pg_catalog, trigger_lab, pg_temp
~~~

### 39.3. Understand audit actor properly

`current_user` reflects the executing security role; inside `SECURITY DEFINER` it can be the function owner rather than the application's end user. If you need "who actually requested the change," pass a verified actor/correlation ID safely instead of blindly trusting a client-set session variable.

### 39.4. Avoid security bypasses

A `SECURITY DEFINER` function can read/write with owner privileges beyond the caller's permissions. Limit allowed operations, validate inputs, govern `EXECUTE`/ownership, and review RLS/security models.

## 40. Triggers vs. RULE: Different Mechanisms

PostgreSQL also has a **rule system** for query rewriting:

~~~sql
CREATE RULE ...
~~~

### 40.1. Rules are a rewrite mechanism

Rules transform queries during the rewrite stage; they are not "a function called after each row" like row triggers.

### 40.2. Triggers are event-driven execution

Triggers execute by defined event, timing, and level, with `TG_OP`/`OLD`/`NEW` in the appropriate context.

### 40.3. Do not use rules to emulate per-row checks

Query rewrite rules can behave surprisingly with multi-row queries and `RETURNING`. For audit or validation side effects, triggers are usually far more direct, while constraints remain preferred whenever applicable.

### 40.4. Views have multiple updatability mechanisms

Views may be automatically updatable, use `INSTEAD OF` triggers, or use rules depending on design. Do not treat them as three identical mechanisms regarding row counts, `RETURNING`, and multi-row updates.

## 41. Choosing ROW vs. STATEMENT by Use Case

| Requirement | Recommended direction |
| --- | --- |
| Normalize SKU before INSERT | `BEFORE INSERT FOR EACH ROW`, modify `NEW` |
| Set `updated_at` per row | `BEFORE UPDATE FOR EACH ROW` |
| Record OLD/NEW for each order | `AFTER UPDATE FOR EACH ROW` |
| Block an invalid value | Constraint or `BEFORE ROW` raising an exception |
| Log every UPDATE run, even 0 rows | `AFTER UPDATE FOR EACH STATEMENT` |
| Summarize all updated rows once | `AFTER STATEMENT` + transition tables |
| Batch-log all DELETEs of a statement | `AFTER DELETE` + `OLD TABLE` |
| Track TRUNCATE | Statement-level TRUNCATE trigger |
| Write through a special view | `INSTEAD OF FOR EACH ROW` |
| Deferrable constraint check | Constraint trigger if genuinely needed |
| Heavy computation across millions of rows | Set-based SQL, batch job, or statement transition table |
| Send events to external systems after COMMIT | Transactional outbox / CDC / worker |

### 41.1. A single table can use both levels

The lab showed that `BEFORE ROW` normalization, `AFTER ROW` auditing, and `AFTER STATEMENT` row counting coexist cleanly on one table.

### 41.2. Do not add work just because a trigger already exists

If a simple transformation can be solved via a generated column, constraint, or single SQL statement, putting it in a trigger adds unnecessary debugging and migration complexity.

## 42. Debugging Triggers Properly

When an UPDATE generates unexpected extra writes or logs, inspect in this order:

1. Which SQL statement executed, targeting which table/partition?
2. Which triggers are attached to that relation?
3. What are `TG_OP`, timing, and level?
4. Are multiple triggers on the same event running in alphabetical order?
5. Does a `BEFORE ROW` trigger alter `NEW` or return `NULL`?
6. Are `WHEN` or `UPDATE OF` altering firing conditions?
7. Is a statement trigger firing even on 0 rows?
8. Are `ON CONFLICT`, `MERGE`, FK cascades, or partition moves generating extra events?
9. Is there trigger recursion or side-effect DML touching other tables?
10. Did a transaction rollback remove audit entries that were visible before rollback?

### 42.1. RAISE NOTICE in the lab

~~~sql
RAISE NOTICE 'trigger=%, op=%, level=%',
    TG_NAME, TG_OP, TG_LEVEL;
~~~

A simple diagnostic tool. In production, never log per row on multi-million-row batches, as log volume will explode.

### 42.2. pg_get_triggerdef and pg_get_functiondef

A trigger may point to a function modified later via `CREATE OR REPLACE`. Always check the current definition of **both the trigger and the function**.

### 42.3. Test 0, 1, and N rows

This is the minimal test matrix for distinguishing row and statement triggers. A trigger that works for one row can fail on performance/logic with many rows, or miss logs on zero rows.

## 43. Practice Exercises

Exercises use schema `trigger_lab`. For exercises that ask to create illustrative extra triggers, you can answer in SQL without necessarily attaching them directly to the live lab tables to avoid duplicate logs. Never run destructive cleanup in production.

### Exercise 1. Invocation counts

An `UPDATE` affects 500 rows. How many times do `AFTER UPDATE FOR EACH ROW` and `AFTER UPDATE FOR EACH STATEMENT` run?

### Exercise 2. Zero rows

A `DELETE` matches zero rows. How many times do both `AFTER DELETE` trigger types run?

### Exercise 3. Default level

If you omit `FOR EACH ...` in `CREATE TRIGGER`, which level does PostgreSQL pick?

### Exercise 4. TG_OP

Write a trigger function that logs `TG_OP`, `TG_NAME`, and `TG_LEVEL` via `RAISE NOTICE`.

### Exercise 5. NEW and OLD

In an `UPDATE ROW` trigger, how do you read the price before and after the change?

### Exercise 6. BEFORE INSERT normalization

Write a function using `upper(btrim(...))` to normalize `NEW.sku` while allowing the INSERT to proceed.

### Exercise 7. RETURN NULL

What happens if `BEFORE INSERT FOR EACH ROW` returns `NULL`?

### Exercise 8. AFTER RETURN NULL

Does returning `NULL` from `AFTER INSERT FOR EACH ROW` cancel the inserted row?

### Exercise 9. Per-row audit

Write the `CREATE TRIGGER` statement attaching `audit_product_row` to INSERT/UPDATE/DELETE at ROW level.

### Exercise 10. Statement audit

Write the `CREATE TRIGGER` statement calling `audit_product_statement` after INSERT using `NEW TABLE AS new_rows`.

### Exercise 11. Transition OLD TABLE

Write the `CREATE TRIGGER` statement after DELETE using `OLD TABLE AS old_rows`.

### Exercise 12. UPDATE transition tables

Write the `CREATE TRIGGER` statement after UPDATE providing both OLD and NEW row sets.

### Exercise 13. INSERT row counts

One INSERT adds 3 products. How many rows do the row audit and statement audit tables receive in the baseline lab?

### Exercise 14. UPDATE of 0 rows

Write an UPDATE matching no IDs and explain the `rows_affected` value in statement audit.

### Exercise 15. ROLLBACK

In a transaction where a product is updated and audit triggers run, do the audit rows remain after `ROLLBACK`? Why might `audit_id` have gaps?

### Exercise 16. WHEN

Write a `WHEN` clause for an UPDATE trigger that logs only when `OLD.price` and `NEW.price` differ, including NULL cases.

### Exercise 17. UPDATE OF price

Does `UPDATE products SET price = price` match an `UPDATE OF price` trigger? Does the price necessarily have to change?

### Exercise 18. Modification by a BEFORE trigger

If an UPDATE only sets `stock` while a BEFORE trigger modifies `NEW.price`, is an `UPDATE OF price` trigger guaranteed to fire?

### Exercise 19. Aggregating price delta

Write a `SELECT` over `old_rows` JOIN `new_rows` computing total `new.price - old.price` for rows whose price changed, assuming `product_id` does not change.

### Exercise 20. Statement vs. transaction

A transaction contains two independent UPDATE statements. How many times does a statement-level UPDATE trigger run?

### Exercise 21. TRUNCATE

Does TRUNCATE fire DELETE row triggers? Write a statement-level trigger to record TRUNCATE events.

### Exercise 22. INSTEAD OF

Does an INSTEAD OF trigger attach to a base table or a view? Can it use `FOR EACH STATEMENT`?

### Exercise 23. Writing through a view trigger

Write a trigger function allowing INSERT of a row into `v_catalog` and forwarding it to `products`.

### Exercise 24. Execution order

Given two BEFORE UPDATE ROW triggers named `trg_a` and `trg_b`, which runs first when both match?

### Exercise 25. Recursion

Why does a BEFORE UPDATE trigger running `UPDATE products SET ...` on the same row easily loop? How should it be fixed?

### Exercise 26. Constraint trigger

Can a deferrable constraint trigger be statement-level? Describe how it differs from a regular row trigger.

### Exercise 27. ON CONFLICT

Why shouldn't you sum INSERT/UPDATE statement trigger calls to deduce how many rows UPSERT succeeded on?

### Exercise 28. Partitioned tables

If an UPDATE targets a partitioned parent table, do statement triggers on individual partitions run automatically?

### Exercise 29. pg_trigger

Write a query showing trigger names, enabled status, and DDL on the `products` table.

### Exercise 30. Disable trigger

Write DDL to disable and re-enable `trg_20_audit_product_row`. State the risk of disabling an audit trigger in production.

### Exercise 31. Audit actor

Why is `current_user` not always the end user when a trigger function uses `SECURITY DEFINER`?

### Exercise 32. Business invariant

Suppose two transactions concurrently buy the last 5 items; why does `SELECT stock` inside a trigger not guarantee no overselling? Propose a conditional UPDATE.

### Exercise 33. Performance

An UPDATE modifies 100,000 rows, and a row trigger queries a large table each time. What happens? How can transition tables help?

### Exercise 34. pg_trigger_depth

Explain `pg_trigger_depth()` and why `IF depth>1 THEN RETURN` should not be used as a default fix.

### Exercise 35. Triggers and RULE

What is the fundamental difference between a query rewrite rule and a DML trigger?

### Exercise 36. Transactional outbox

Why does sending an HTTP request directly from a trigger fail to stay consistent with database rollback? How does an outbox help?

### Exercise 37. Historical audit gaps

If an audit trigger is disabled for a day and then re-enabled, are missed changes automatically logged?

### Exercise 38. EXPLAIN ANALYZE

Does `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` actually execute the UPDATE and fire triggers? How do you test safely?

### Exercise 39. TRUNCATE count

Why can't a TRUNCATE statement trigger count rows via `OLD TABLE` like DELETE?

### Exercise 40. Choosing the right tool

Choose among `CHECK`, BEFORE ROW trigger, AFTER ROW trigger, and AFTER STATEMENT trigger for four goals: non-negative stock; SKU normalization; per-row price OLD/NEW audit; one log row per UPDATE even when 0 rows match.

## 44. Solution Hints

### Exercises 1–3. Frequency

500-row UPDATE: ROW 500 times, STATEMENT 1 time assuming no `WHEN` filtering or row skipping. 0-row DELETE: ROW 0, STATEMENT 1. Omitting `FOR EACH ...` defaults to STATEMENT.

### Exercise 4. TG_*

~~~sql
CREATE FUNCTION trigger_lab.log_trigger_context()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'name %, op %, level %',
        TG_NAME, TG_OP, TG_LEVEL;
    RETURN NULL;
END;
$$;
~~~

Attach only to triggers where `RETURN NULL` does not skip the underlying row (such as AFTER STATEMENT).

### Exercise 5. OLD/NEW

~~~sql
RAISE NOTICE '% -> %', OLD.price, NEW.price;
~~~

### Exercise 6. Normalization

~~~sql
CREATE FUNCTION trigger_lab.normalize_sku_answer()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.sku := upper(btrim(NEW.sku));
    RETURN NEW;
END;
$$;
~~~

Attach with `BEFORE INSERT FOR EACH ROW` on the appropriate table.

### Exercises 7–8. RETURN

`BEFORE ROW RETURN NULL` skips the operation for the current row. `AFTER ROW RETURN NULL` is ignored and **does not** cancel the written operation.

### Exercise 9. Row audit

~~~sql
CREATE TRIGGER trg_product_audit_answer
AFTER INSERT OR UPDATE OR DELETE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.audit_product_row();
~~~

Do not actually create it if the lab already has a trigger for the same purpose, as it will duplicate audit entries.

### Exercises 10–12. Transition table triggers

~~~sql
CREATE TRIGGER trg_insert_answer
AFTER INSERT ON trigger_lab.products
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();

CREATE TRIGGER trg_delete_answer
AFTER DELETE ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();

CREATE TRIGGER trg_update_answer
AFTER UPDATE ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

This is answer DDL; do not run alongside existing lab triggers if you only want to verify syntax.

### Exercises 13–14. Row count

A 3-row INSERT creates 3 row-audit rows and 1 statement-audit row with `rows_affected=3`. An UPDATE matching zero rows still produces one statement trigger invocation with `rows_affected=0` and zero row-audit entries.

~~~sql
UPDATE trigger_lab.products
SET stock = 1
WHERE product_id < 0;
~~~

### Exercise 15. Transaction

Both the update and audit writes run in the same transaction, so both roll back. Identity/sequence counters normally do not roll back allocated numbers, leaving ID gaps.

### Exercises 16–18. WHEN vs. UPDATE OF

~~~sql
WHEN (OLD.price IS DISTINCT FROM NEW.price)
~~~

`UPDATE OF price` checks columns listed in the statement; `SET price=price` can still fire it even when unchanged. A BEFORE trigger altering `price` does not automatically cause an `UPDATE OF price` trigger to match when `price` was absent from the original SET list.

### Exercise 19. Set-based delta

~~~sql
SELECT
    count(*) AS changed_products,
    coalesce(sum(n.price - o.price), 0) AS total_delta
FROM old_rows AS o
JOIN new_rows AS n
  ON n.product_id = o.product_id
WHERE n.price IS DISTINCT FROM o.price;
~~~

Execute only inside a trigger declaring those transition aliases.

### Exercise 20. Per statement

Two UPDATE statements in one transaction fire the statement-level UPDATE trigger twice.

### Exercise 21. TRUNCATE

TRUNCATE does not call DELETE row triggers. Example:

~~~sql
CREATE TRIGGER trg_truncate_answer
AFTER TRUNCATE
ON trigger_lab.products
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_truncate();
~~~

### Exercises 22–23. View trigger

`INSTEAD OF` attaches to views and supports `FOR EACH ROW` only.

~~~sql
CREATE FUNCTION trigger_lab.insert_catalog_answer()
RETURNS trigger LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.products (
        product_id, sku, price, stock
    ) VALUES (
        NEW.product_id, NEW.sku, NEW.price, NEW.stock
    );
    RETURN NEW;
END;
$$;
~~~

Attach via `CREATE TRIGGER ... INSTEAD OF INSERT ON trigger_lab.v_catalog FOR EACH ROW ...`.

### Exercises 24–25. Order and recursion

For identical kind/timing/event, `trg_a` runs before `trg_b`. Issuing a new `UPDATE` on the same table inside BEFORE ROW can re-fire the trigger and loop; instead modify `NEW.column` and `RETURN NEW`.

### Exercise 26. Constraint trigger

A deferrable constraint trigger is created as `AFTER ROW` on an eligible relation, not a standard statement-level trigger. Its evaluation can be deferred via constraint mechanics.

### Exercise 27. ON CONFLICT

UPSERT can fire both INSERT and UPDATE statement triggers under its rules, even if a branch modifies no rows. Invocation counts do not equal inserted/updated row counts.

### Exercise 28. Partition

Not automatically. When the statement targets the parent, statement triggers on the parent fire; child statement triggers do not fire automatically due to routing. Row triggers and partition row movement follow separate rules.

### Exercise 29. Catalog

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid, true)
FROM pg_trigger
WHERE tgrelid = 'trigger_lab.products'::regclass
ORDER BY tgname;
~~~

### Exercise 30. Enable/disable

~~~sql
ALTER TABLE trigger_lab.products
DISABLE TRIGGER trg_20_audit_product_row;

ALTER TABLE trigger_lab.products
ENABLE TRIGGER trg_20_audit_product_row;
~~~

Disabling leaves an audit gap during that window; re-enabling does not backfill missed logs.

### Exercise 31. Actor

Under `SECURITY DEFINER`, `current_user` can reflect the function owner instead of the end user. Use an application-supplied and safely validated actor identity mechanism.

### Exercise 32. Stock concurrency

~~~sql
UPDATE trigger_lab.products
SET stock = stock - 5
WHERE product_id = 1
  AND stock >= 5
RETURNING product_id, stock;
~~~

Check the updated row count and transaction outcome. Never just read stock and decide based on a stale snapshot.

### Exercise 33. Performance

A row trigger firing 100,000 times and querying a large table each time causes severe N+1, I/O, and locking overhead. Move summary logic to an AFTER STATEMENT trigger reading transition tables set-based, or batch outside triggers if business logic permits.

### Exercise 34. Depth

`pg_trigger_depth()` measures current trigger nesting depth, yet blocking all calls with depth>1 can suppress valid work triggered by another trigger. Clean separation of concerns and idempotent design are better.

### Exercise 35. RULE

Rules transform queries at rewrite time; DML triggers invoke functions by event/timing/level with `OLD`/`NEW`/`TG` context.

### Exercise 36. Outbox

External HTTP side effects cannot be rolled back by the database when a transaction fails. A transactional outbox writes events to a table in the same transaction; a worker processes only committed events with designed delivery, retry, and idempotency.

### Exercise 37. Missing audits

No. While disabled, the trigger did not capture those changes. Reconcile or backfill from other sources if business rules require it.

### Exercise 38. EXPLAIN

`EXPLAIN ANALYZE` executes the real statement and fires matching triggers. Measure only in a lab, for example:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_lab.products
SET stock = stock
WHERE product_id = 1;
ROLLBACK;
~~~

### Exercise 39. TRUNCATE count

TRUNCATE does not provide an `OLD TABLE` like DELETE transition relations and does not fire row DELETE triggers. If exact pre-TRUNCATE row counts are required, use a separate measurement design while accounting for locking and consistency.

### Exercise 40. Choosing the right tool

| Goal | Solution |
| --- | --- |
| Non-negative stock | `CHECK (stock >= 0)` |
| SKU normalization | `BEFORE INSERT/UPDATE FOR EACH ROW` |
| Audit price OLD/NEW | `AFTER UPDATE FOR EACH ROW` with WHEN |
| One log per UPDATE even on 0 rows | `AFTER UPDATE FOR EACH STATEMENT` |

## 45. Quick Reference Table

| Question | Tool / Key point |
| --- | --- |
| Runs per row? | `FOR EACH ROW` |
| Runs per SQL statement? | `FOR EACH STATEMENT` |
| Default if level omitted? | `FOR EACH STATEMENT` |
| UPDATE affecting 0 rows? | Statement trigger still runs; row trigger does not |
| Modify values before writing? | `BEFORE ROW`, modify `NEW`, `RETURN NEW` |
| Skip a row before writing? | `BEFORE ROW RETURN NULL` |
| Reject with an error? | `RAISE EXCEPTION` / constraint |
| Log updated row? | `AFTER UPDATE FOR EACH ROW` |
| Identify event type? | `TG_OP` |
| Check level/timing? | `TG_LEVEL`, `TG_WHEN` |
| Read OLD/NEW on UPDATE ROW? | `OLD.column`, `NEW.column` |
| Read entire INSERT batch? | `REFERENCING NEW TABLE AS new_rows` |
| Read entire DELETE batch? | `REFERENCING OLD TABLE AS old_rows` |
| Read before/after UPDATE batch? | `OLD TABLE` + `NEW TABLE` |
| Only when price actually changes? | `WHEN (OLD.price IS DISTINCT FROM NEW.price)` |
| When column appears in UPDATE SET? | `UPDATE OF price` |
| TRUNCATE? | Statement-level TRUNCATE trigger |
| View write handler? | `INSTEAD OF ... FOR EACH ROW` |
| Multiple triggers of same kind? | Alphabetical order by trigger name |
| Does ROLLBACK remove DB audits? | Yes, if audit was written in the same transaction |
| Do HTTP side effects roll back? | Not automatically; consider outbox |
| Trigger function return type? | `RETURNS trigger` |
| View trigger definitions? | `pg_trigger`, `pg_get_triggerdef` |
| View function body? | `pg_get_functiondef` |
| Disable/enable a trigger? | `ALTER TABLE ... DISABLE/ENABLE TRIGGER ...` |
| Avoid trigger recursion? | Modify `NEW`, isolate DML flows / idempotency |
| Check nesting depth? | `pg_trigger_depth()` |
| Measure cost? | `EXPLAIN (ANALYZE, BUFFERS)` in a lab |

## 46. Pre-Production Trigger Checklist

1. Is a trigger truly required, or would a constraint, generated column, SQL statement, or batch job suffice?
2. Is the requirement **per row** or **once per statement**?
3. Have 0, 1, and multi-thousand-row cases been tested?
4. Does the function use `NEW`/`OLD` strictly for events where they exist?
5. Could `BEFORE ROW` accidentally `RETURN NULL` and drop rows?
6. Is an `AFTER` trigger mistakenly assumed to run "after COMMIT"?
7. Do `WHEN` or `UPDATE OF` conditions match business intent?
8. If batch-level access is needed, do transition tables support the target event and relation?
9. Could an UPDATE modify primary keys and break `OLD`/`NEW` joins?
10. Do `INSERT ... ON CONFLICT` or `MERGE` affect event counts?
11. Do partition routing/movement or FK cascades spawn extra trigger events?
12. Could trigger recursion or cross-table update cycles lead to deadlocks?
13. Does a row trigger execute a heavy SQL query N times?
14. Does the audit table have suitable schema, indexes, retention, and PII controls?
15. Do exceptions roll back side effects as intended?
16. Are external side effects handled via a transactional outbox or CDC?
17. Does `SECURITY DEFINER` use a safe owner and `search_path`?
18. Is there a proper actor/correlation ID mechanism rather than trusting `current_user` alone?
19. Can unauthorized roles disable triggers or alter `session_replication_role`?
20. Has behavior been verified on replication subscribers?
21. Are trigger/function DDLs under version control and proper migrations?
22. Have `pg_trigger`/`pg_get_triggerdef` been inspected before modifying anything?
23. Have write latency, WAL volume, and lock waits been measured at realistic scale?
24. Have transaction rollbacks, retries, and deadlocks been tested?
25. Is there a plan to disable, recover, or backfill if the trigger causes an incident?

## 47. Summary

The two trigger levels address **two distinct DML scopes**:

- **`FOR EACH ROW`** executes logic for each affected row; in `BEFORE ROW`, the function can validate and edit `NEW` or skip a row with `RETURN NULL`. In `AFTER ROW`, it excels at auditing per-row `OLD`/`NEW` values.
- **`FOR EACH STATEMENT`** executes once for the whole SQL statement, **even when 0 rows are affected**. It fits command/batch logging, and when combined with `AFTER` and `REFERENCING OLD TABLE/NEW TABLE`, it lets you aggregate changed rows as a set instead of iterating row by row.

The most common misconceptions are **statement != transaction**, **AFTER != post-COMMIT**, **`RETURN NULL` only skips rows in valid `BEFORE ROW` contexts**, **`UPDATE OF` does not guarantee column values actually changed**, and **`TRUNCATE` does not fire DELETE ROW triggers**. Furthermore, `INSTEAD OF` on views, constraint triggers, partitioned tables, and `ON CONFLICT` each have specific rules to master.

If a trigger slows down your system, do not rush to disable it: check whether logic running per row actually only needs to run once per statement; consider transition tables, set-based SQL, outboxes, or background jobs. Measure write impact while preserving integrity, privileges, audit/rollback correctness, and safe deployment.

**Practical rule of thumb:** use **constraints** for simple invariants; **BEFORE ROW** when normalizing a single row; **AFTER ROW** when per-change history is required; and **AFTER STATEMENT + transition tables** when processing an entire batch. Design for the right event scope first, then optimize performance.
