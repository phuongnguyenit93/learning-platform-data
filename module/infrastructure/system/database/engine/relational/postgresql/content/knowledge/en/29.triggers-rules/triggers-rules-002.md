# BEFORE, AFTER, INSTEAD OF Triggers and Execution Timing in PostgreSQL

Suppose a sales system stores purchase orders in PostgreSQL. When inserting an order, the application needs to normalize the customer name; when updating an order, it needs to record change history; and an admin UI operates through a **view** instead of accessing the base table directly. These three needs can use three types of triggers with different **execution timings**:

- **`BEFORE`:** runs before the corresponding `INSERT`, `UPDATE`, or `DELETE` operation; can inspect and modify `NEW` in a row-level trigger or skip a row.
- **`AFTER`:** runs after the operation has been applied to the corresponding row or statement; suited for auditing, updating dependent tables, or processing the set of changed rows.
- **`INSTEAD OF`:** only used for **row-level triggers on views**; performs actions instead of the DML operation the user sent to the view.

A common point of confusion is that **trigger timing** (`BEFORE`/`AFTER`/`INSTEAD OF`) and **trigger level/granularity** (`FOR EACH ROW`/`FOR EACH STATEMENT`) are two independent dimensions. A statement affecting 0 rows can still fire statement-level triggers, whereas row-level triggers run only for the affected rows. Furthermore, all trigger actions still obey PostgreSQL's transaction/MVCC rules: **`AFTER` does not mean "after `COMMIT`"**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe triggers, trigger functions, and the `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE` events.
2. Distinguish **timing** from **granularity**, and identify which combinations are supported on tables vs. views.
3. Explain accurately when `BEFORE ROW`, `AFTER ROW`, `BEFORE STATEMENT`, and `AFTER STATEMENT` fire.
4. Use `NEW` and `OLD` per event type, along with `TG_OP`, `TG_WHEN`, and `TG_LEVEL`.
5. Write `RETURNS trigger` trigger functions in PL/pgSQL and register them with `CREATE TRIGGER`.
6. Know when to return `NEW`, `OLD`, or `NULL` in `BEFORE ROW` and `INSTEAD OF ROW`.
7. Explain why the return value of `AFTER` triggers and statement-level triggers is ignored.
8. Use `BEFORE` to normalize data while keeping `CHECK`/`FK`/`NOT NULL` constraints as the primary line of defense.
9. Use `AFTER` to write audit records that roll back together with the transaction.
10. Use **transition tables** (`OLD TABLE`, `NEW TABLE`) for statement-level aggregate triggers.
11. Create `INSTEAD OF` triggers to perform `INSERT`/`UPDATE`/`DELETE` through a view.
12. Understand execution ordering when multiple triggers of the same type exist and the effects of `WHEN` and `UPDATE OF`.
13. Recognize deferrable `AFTER ROW` **constraint triggers**, as opposed to regular AFTER triggers.
14. Anticipate edge cases with `ON CONFLICT DO UPDATE`, `TRUNCATE`, cascading FKs, and partition row movement.
15. Avoid trigger recursion, unintended writes, N+1 overhead, security risks, and hard-to-debug behavior.
16. Inspect metadata, logs/EXPLAIN, and data changes inside a transaction.

## 2. What Is a Trigger?

A **trigger** is a mechanism by which PostgreSQL automatically invokes an execution function/routine in response to an event on a table or view. In standard PostgreSQL practice, we:

1. Create a **trigger function** using `CREATE FUNCTION ... RETURNS trigger`.
2. Attach it to a table or view via `CREATE TRIGGER ... EXECUTE FUNCTION ...`.
3. Run DML commands; PostgreSQL invokes the trigger function when the event and conditions match.

Example:

~~~sql
CREATE FUNCTION public.demo_before_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_demo_before_insert
BEFORE INSERT ON public.demo_orders
FOR EACH ROW
EXECUTE FUNCTION public.demo_before_insert();
~~~

This is only a **syntax sample**; `public.demo_orders` is a hypothetical table. The lab section below creates an actual table in its own schema.

### 2.1. Triggers Differ From DEFAULT and CHECK

| Tool | Typical need | Characteristic |
| --- | --- | --- |
| `DEFAULT` | Initial value when INSERT omits the column | No trigger function needed |
| `GENERATED` column | Value derived from an expression | Computed by the database per column rule |
| `NOT NULL`/`CHECK` | Enforce valid data | Schema constraint; preferred for simple invariants |
| `FOREIGN KEY` | Preserve referential integrity | Database enforces the relationship |
| `BEFORE` trigger | Normalization, complex business checks, modifying `NEW` | Can alter the row before writing |
| `AFTER` trigger | Auditing, side-table updates, per-row/set verification | Sees the effect of the DML |
| `INSTEAD OF` trigger | DML through a non-auto-updatable view or custom logic | Executes in place of the view action |

**Do not turn every data rule into a trigger.** When a `CHECK` or `UNIQUE` constraint can express an invariant, the constraint is usually clearer and easier to verify.

### 2.2. Triggers Are Not Synonymous With RULEs

PostgreSQL also has a **rule system** (`CREATE RULE`) used to **rewrite queries** before execution. Triggers run during DML execution. Both can support updating through views, but **they are not synonymous syntax**.

### 2.3. Triggers Are Not Post-COMMIT Callbacks

~~~text
BEGIN
  UPDATE main table
     └── AFTER ROW trigger writes audit
  ... other statements ...
ROLLBACK
~~~

If the transaction rolls back, **both the main table data and the audit records created in that transaction roll back**. The word `AFTER` describes timing relative to the DML operation, **not** after durable transaction commit.

## 3. Two Dimensions to Distinguish: Timing and Level

### 3.1. Timing

| Timing | Meaning |
| --- | --- |
| `BEFORE` | Before the corresponding row or statement operation |
| `AFTER` | After the corresponding row or statement operation |
| `INSTEAD OF` | Executes **instead of** the operation on a view; row-level only |

### 3.2. Level

| Level | Meaning |
| --- | --- |
| `FOR EACH ROW` | Once per affected row, following each event's semantics |
| `FOR EACH STATEMENT` | Once per statement for the corresponding event, even if 0 rows are modified |

### 3.3. Key Support Matrix

| Object | `BEFORE ROW` | `AFTER ROW` | `BEFORE STATEMENT` | `AFTER STATEMENT` | `INSTEAD OF ROW` |
| --- | --- | --- | --- | --- | --- |
| Regular table | Yes for INSERT/UPDATE/DELETE | Yes for INSERT/UPDATE/DELETE | Yes | Yes | **No** |
| View | **No** | **No** | Yes | Yes | Yes for INSERT/UPDATE/DELETE |
| Foreign table | Supports BEFORE ROW in applicable cases | Check foreign-table trigger limitations by version/FDW | Check version support | Check version support | **No**, since it is not a view |

**For `TRUNCATE`:** only **statement-level BEFORE/AFTER triggers** exist; there is no row-level `TRUNCATE` trigger. There is no `INSTEAD OF TRUNCATE`.

**For views:** `INSTEAD OF` only supports `FOR EACH ROW`; `BEFORE`/`AFTER` triggers on views must be **statement-level**. If a view is automatically updatable, PostgreSQL can update it natively; `INSTEAD OF` is only needed when you want custom control or the view is not auto-updatable.

### 3.4. Common CREATE TRIGGER Syntax

~~~sql
CREATE TRIGGER trigger_name
BEFORE INSERT OR UPDATE OR DELETE
ON schema_name.table_name
FOR EACH ROW
EXECUTE FUNCTION schema_name.trigger_function();
~~~

For column-specific `UPDATE`:

~~~sql
CREATE TRIGGER trg_amount_changed
AFTER UPDATE OF amount ON schema_name.orders
FOR EACH ROW
WHEN (OLD.amount IS DISTINCT FROM NEW.amount)
EXECUTE FUNCTION schema_name.audit_amount_change();
~~~

`UPDATE OF amount` checks whether **the column is listed in the SET list**; `WHEN (OLD.amount IS DISTINCT FROM NEW.amount)` checks whether **the value actually differs**, including NULL cases. Both nuances are examined in detail later.

## 4. Execution Timing Within a Statement

A conceptual view for a multi-row `UPDATE` on a regular table:

~~~text
Client sends UPDATE
  |
  +-- BEFORE STATEMENT triggers
  |
  +-- For each matching row:
  |     +-- BEFORE ROW triggers: inspect OLD/NEW, may change NEW or skip row
  |     +-- PostgreSQL applies the row change if not skipped
  |     +-- Row-level AFTER events are queued
  |
  +-- AFTER ROW triggers are processed per PostgreSQL semantics
  |
  +-- AFTER STATEMENT triggers
  |
  +-- Statement finishes or raises an error
  |
  +-- COMMIT/ROLLBACK decided by the caller's transaction
~~~

This is a **mental model**, not a guarantee of an internal order across every optimization or trigger category. Deferred constraint triggers, cascading FKs, partition row movement, and multi-action statements such as `ON CONFLICT DO UPDATE` introduce additional details.

### 4.1. BEFORE STATEMENT

Runs **before** PostgreSQL processes the corresponding row modifications of the statement. There are no specific `NEW`/`OLD` rows to read or modify in a statement trigger.

### 4.2. BEFORE ROW

Runs on each operated row before the row change is applied. Typically uses `NEW` (INSERT/UPDATE), `OLD` (UPDATE/DELETE), and the return value decides whether processing continues for that row or skips it.

### 4.3. AFTER ROW

Runs after the corresponding row change has occurred. Suited for *in-database* side effects and auditing. **You cannot modify the written row simply by assigning `NEW.foo := ...` and `RETURN NEW` inside an AFTER trigger**, because the return value of an AFTER trigger is ignored.

### 4.4. AFTER STATEMENT

Runs after the statement's row operations. An `AFTER STATEMENT` trigger can use transition tables to inspect **the set of rows** just affected, rather than executing once per row.

### 4.5. INSTEAD OF ROW

Applies only to views. When a client sends `INSERT`/`UPDATE`/`DELETE` to a view, the trigger operates on underlying base tables or executes custom logic **in place of the default action**. It returns a non-NULL row to report that a row was handled, and NULL if not handled.

### 4.6. AFTER Does Not Mean "Data Is Committed"

A statement can run multiple AFTER triggers and later encounter an exception and roll back. Rows written inside AFTER triggers **still belong to the same transaction**, so they roll back with the statement/transaction according to PostgreSQL rules.

## 5. Trigger Functions: RETURNS trigger

A standard PL/pgSQL trigger function is declared as:

~~~sql
CREATE FUNCTION schema_name.function_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- NEW, OLD, TG_OP, TG_WHEN, TG_LEVEL...
    RETURN NEW;
END;
$$;
~~~

### 5.1. Special Variables

| Variable | Meaning |
| --- | --- |
| `NEW` | New row for INSERT/UPDATE row-level triggers |
| `OLD` | Row before modification for UPDATE/DELETE row-level triggers |
| `TG_OP` | `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER`, `INSTEAD OF` |
| `TG_LEVEL` | `ROW` or `STATEMENT` |
| `TG_TABLE_NAME` | Name of the table/view the trigger is attached to |
| `TG_TABLE_SCHEMA` | Schema of the table/view |
| `TG_RELID` | OID of the relation the trigger is attached to |
| `TG_NAME` | Trigger name |
| `TG_NARGS` | Number of arguments passed to the trigger |
| `TG_ARGV[n]` | Trigger argument as text, **0-based** index |

**`NEW` is unavailable for DELETE and `OLD` is unavailable for INSERT.** For statement-level triggers, there is no single row assigned to `NEW`/`OLD`.

### 5.2. Branching With TG_OP

~~~sql
CREATE FUNCTION public.example_trigger_function()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        RAISE NOTICE 'Inserted by trigger %', TG_NAME;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        RAISE NOTICE 'Updated row';
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE NOTICE 'Deleting row';
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;
~~~

This function illustrates multiple **row-level** events. When used for statement-level or `INSTEAD OF`, return rules differ and the relation type must be considered.

### 5.3. Trigger Function Arguments

Trigger functions do not declare regular SQL parameters in their signature to receive `TG_ARGV`:

~~~sql
CREATE TRIGGER trg_audit_named
AFTER INSERT ON some_schema.some_table
FOR EACH ROW
EXECUTE FUNCTION some_schema.audit_function('orders', 'important');
~~~

At runtime, the function reads `TG_ARGV[0]` as `orders` and `TG_ARGV[1]` as `important`. These strings are **trigger arguments**, distinct from parameters of a normally called function.

## 6. Return Values: NEW, OLD, and NULL

This is the single most important rule when writing row-level triggers.

| Trigger | `RETURN NEW` | `RETURN OLD` | `RETURN NULL` |
| --- | --- | --- | --- |
| `BEFORE INSERT ROW` | Allows row to proceed, using modified `NEW` if altered | Inappropriate since `OLD` does not exist | **Skips** inserting this row |
| `BEFORE UPDATE ROW` | Allows UPDATE to proceed with modified `NEW` | Can produce unintended results by substituting old row for new row | **Skips** updating this row |
| `BEFORE DELETE ROW` | No `NEW` | Allows DELETE to proceed | **Skips** deleting this row |
| `AFTER ROW` | Return value ignored | Return value ignored | Return value ignored |
| `BEFORE/AFTER STATEMENT` | Return value ignored | Return value ignored | Return value ignored |
| `INSTEAD OF INSERT/UPDATE ROW` | Signals row handled, supplies row for RETURNING | Inappropriate when OLD is absent | Signals row not handled |
| `INSTEAD OF DELETE ROW` | No NEW | Signals DELETE handled | Signals row not handled |

### 6.1. A Row-Level BEFORE Trigger Returning NULL

When `BEFORE ROW` returns NULL:

- PostgreSQL **skips the corresponding row action**.
- Subsequent row-level triggers for that operation do not run for the skipped row.
- The row does not appear in `RETURNING` as a modified row.
- Statement-level triggers still run because the statement was issued.

Returning NULL to "silently drop invalid rows" is usually bad for business clarity. If input is invalid, **`RAISE EXCEPTION` or constraints** are generally better so the caller knows about the failure.

### 6.2. BEFORE UPDATE Returning OLD: Technically Valid, Easily Misunderstood

A row-level BEFORE UPDATE trigger can return a row value other than `NEW`, but be very careful: `RETURN OLD` must not be confused with "skipping UPDATE like `RETURN NULL`". It can cause the old values to be used for the row operation, creating unexpected effects while still treating the row as processed. For UPDATE, you should normally only `RETURN NEW` or `RETURN NULL` as designed.

### 6.3. AFTER Triggers Cannot Modify the Row via Return Value

~~~sql
-- Wrong approach:
-- CREATE FUNCTION ... RETURNS trigger AS $$
-- BEGIN
--   NEW.amount := 0;
--   RETURN NEW;
-- END; $$ LANGUAGE plpgsql;
-- Attaching this AFTER UPDATE will NOT set the updated row's amount to 0.
~~~

If you need to modify values of **the very row being INSERTed/UPDATEd**, normally use `BEFORE ROW`. If you need to update another row after the event, `AFTER` can execute a separate `UPDATE`, while watching out for **trigger recursion and locking/concurrency**.

### 6.4. INSTEAD OF Triggers and RETURNING

An `INSTEAD OF ROW` trigger on a view should normally return an appropriate row when the operation was performed. PostgreSQL uses the return value to determine the affected row count and can populate output for `INSERT/UPDATE/DELETE ... RETURNING` on the view. `RETURN NULL` means the row was not processed, **not merely "nothing to return"**.

## 7. Lab Dataset: Orders and History Tables

The examples create a **dedicated schema** `trg_lab_367`. Run this DDL and DML only in an authorized lab database, never paste into a production schema containing real data. The examples target modern PostgreSQL with `plpgsql`.

### 7.1. Create the Schema

~~~sql
CREATE SCHEMA trg_lab_367;
~~~

If the schema already exists from an earlier practice session, pick another lab name or reset intentionally after confirming the data can be deleted. **Do not run `DROP SCHEMA ... CASCADE` on a schema whose origin you are unsure of.**

### 7.2. Orders Table

~~~sql
CREATE TABLE trg_lab_367.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'paid', 'cancelled')),
    note text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 7.3. Audit Table

~~~sql
CREATE TABLE trg_lab_367.order_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint,
    action text NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    changed_by name NOT NULL DEFAULT current_user
);
~~~

We omit an FK from audit -> orders in the lab so **DELETE auditing** can still store the order_id after the source row is deleted. In production, choose an appropriate retention policy, history model, and PII access controls.

### 7.4. Trace Table for Observing Timing

~~~sql
CREATE TABLE trg_lab_367.trigger_trace (
    trace_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    timing text NOT NULL,
    trigger_level text NOT NULL,
    order_id bigint,
    detail text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`trigger_trace` is for **in-transaction observation**; writes to this table also roll back if the transaction containing the main DML rolls back. Do not treat it as an external tamper-proof audit log.

### 7.5. Initialization Verification Query

~~~sql
SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'trg_lab_367'
ORDER BY table_name;
~~~

With no orders yet, `SELECT COUNT(*) FROM trg_lab_367.orders` returns 0. We will create triggers before loading data so we can observe both `BEFORE` and `AFTER` from the very first row.

## 8. BEFORE ROW: Normalizing and Validating Before Writing

Suppose we want to trim leading/trailing whitespace from customer names, reject whitespace-only names, and automatically update `updated_at`.

### 8.1. Create the Trigger Function

~~~sql
CREATE FUNCTION trg_lab_367.normalize_order_before()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.customer_name IS NULL
       OR btrim(NEW.customer_name) = '' THEN
        RAISE EXCEPTION
            'customer_name must not be blank'
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.customer_name := btrim(NEW.customer_name);
    NEW.updated_at := clock_timestamp();

    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, order_id, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        NEW.order_id,
        'name normalized before the row is stored'
    );

    RETURN NEW;
END;
$$;
~~~

### 8.2. Attach to the Table

~~~sql
CREATE TRIGGER trg_10_normalize_order
BEFORE INSERT OR UPDATE
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.normalize_order_before();
~~~

`BEFORE INSERT OR UPDATE` means the trigger runs before both operations. `FOR EACH ROW` means once per affected row, not once for the entire statement.

### 8.3. Order of Operations Inside the Function

1. Read the new data from `NEW`.
2. Validate the name before writing.
3. Modify `NEW.customer_name`.
4. Modify `NEW.updated_at`.
5. Insert a trace record within the same transaction.
6. `RETURN NEW` so PostgreSQL uses the modified row version.

### 8.4. Caveat on Auto-Updating Columns

If name is required, `NOT NULL` already guarantees no SQL NULL is stored, though it does not reject empty or whitespace-only strings. The trigger above enforces a blank-string policy. You could use `CHECK (btrim(customer_name) <> '')` for simple validation; a trigger is useful when you genuinely need to **transform data** before storing it.

### 8.5. Triggers Do Not Automatically Fix Existing Data

`CREATE TRIGGER` does not retroactively run `BEFORE INSERT/UPDATE` on rows already sitting in the table. When adding a normalization trigger to an existing system, plan backfills, historical input checks, and corresponding indexes/constraints.

## 9. BEFORE STATEMENT: Event Before a Statement

Statement-level triggers do not have a specific row; use them for event logging, initializing aggregate state, or policies concerning the **entire statement**.

### 9.1. Trigger Function

~~~sql
CREATE FUNCTION trg_lab_367.trace_before_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'statement started'
    );

    RETURN NULL;
END;
$$;
~~~

### 9.2. Register for Three Events

~~~sql
CREATE TRIGGER trg_01_before_statement
BEFORE INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_before_statement();
~~~

`RETURN NULL` in a statement-level trigger **does not skip the statement**. Return values from statement-level triggers are ignored by PostgreSQL; this is a key difference from `BEFORE ROW`.

### 9.3. Do Not Read Single-Row NEW or OLD

~~~sql
-- Not appropriate in a statement-level trigger:
-- RAISE NOTICE '%', NEW.customer_name;
~~~

With `FOR EACH STATEMENT`, `NEW`/`OLD` do not represent a single record. To read multiple changed rows, consider an **AFTER statement trigger with transition tables** (covered later), rather than trying to force a statement-level trigger to look like a row trigger.

## 10. AFTER ROW: Recording Audit After Row Modification

We want to know the contents before and after the operation. An `AFTER ROW` trigger can insert into the audit table after PostgreSQL has applied the change.

### 10.1. Create the Audit Trigger Function

~~~sql
CREATE FUNCTION trg_lab_367.audit_order_after()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'INSERT', NULL, to_jsonb(NEW)
        );

    ELSIF TG_OP = 'UPDATE' THEN
        v_order_id := NEW.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW)
        );

    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'DELETE', to_jsonb(OLD), NULL
        );
    END IF;

    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, order_id, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        v_order_id,
        'row change audited'
    );

    RETURN NULL;  -- Valid: AFTER ROW return value is ignored.
END;
$$;
~~~

### 10.2. Attach the AFTER Trigger

~~~sql
CREATE TRIGGER trg_90_audit_order
AFTER INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.audit_order_after();
~~~

### 10.3. Why Is AFTER Suitable for Auditing?

In a row-level `AFTER` trigger, PostgreSQL has already applied the action to the row. For `UPDATE`, `NEW` reflects the actual new data operated upon, including modifications made by earlier `BEFORE ROW` triggers.

`BEFORE` can also write audit rows, but if other triggers can still modify `NEW`, an audit record written in `BEFORE` risks not reflecting the final row version. **AFTER** is usually the more natural choice when you need before/after snapshots.

### 10.4. Auditing Within the Same Transaction

If an audit trigger raises an error, the DML statement containing it can fail and roll back. If the caller rolls back the entire transaction after the audit has run, audit records from that transaction also disappear. **A trigger-based audit table is not an immutable logging system that survives transaction rollbacks.**

### 10.5. Permission and Sensitive Data Considerations

`to_jsonb(NEW)` copies **all columns** of the row into the audit table. In production, tables may hold addresses, personal data, or payment details. Establish rules for field selection, masking/encryption, retention, and permissions; do not blindly copy all columns without a data policy.

## 11. AFTER STATEMENT: End-of-Statement Timing

Create a trigger that logs an event when the statement finishes its table operations:

~~~sql
CREATE FUNCTION trg_lab_367.trace_after_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'statement finished its row operations'
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_99_after_statement
AFTER INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_after_statement();
~~~

### 11.1. Diagram of the Three Trigger Types in the Lab

~~~mermaid
flowchart TD
    A["INSERT / UPDATE / DELETE"] --> B["BEFORE STATEMENT: trace_before_statement"]
    B --> C["For each affected row"]
    C --> D["BEFORE ROW: normalize_order_before (INSERT/UPDATE)"]
    D --> E["DML row operation"]
    E --> F["AFTER ROW: audit_order_after"]
    F --> G["AFTER STATEMENT: trace_after_statement"]
    G --> H["Statement ends; transaction still controlled by caller"]
~~~

For `DELETE`, `normalize_order_before` does not run because it is only registered for `INSERT OR UPDATE`. For a statement affecting 0 rows, only the corresponding statement-level triggers run.

### 11.2. Statement-Level Triggers Run Even When Zero Rows Match

~~~sql
UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE order_id = -999999;
~~~

In the lab, this updates zero rows, yet the **BEFORE STATEMENT** and **AFTER STATEMENT** UPDATE triggers still run. **BEFORE ROW** and **AFTER ROW** have no rows to process.

### 11.3. A Statement Modifying 1,000 Rows

- `BEFORE STATEMENT`: typically once.
- `BEFORE ROW`: once per row actually processed by the trigger.
- `AFTER ROW`: once per modified row (excluding skipped rows or special cases).
- `AFTER STATEMENT`: once.

This is why per-row validation or auditing can be very expensive during bulk UPDATEs. For aggregate needs, transition tables can reduce individual SQL executions.

## 12. Loading Data and Observing BEFORE/AFTER

After creating the triggers, run:

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status, note
)
VALUES
    ('  An  ', 120000, 'new', 'first order'),
    (' Bình ', 95000, 'new', 'second order'),
    ('Chi', 0, 'new', 'gift order')
RETURNING order_id, customer_name, amount, updated_at;
~~~

### 12.1. Expected Results

`customer_name` has leading/trailing whitespace trimmed:

| Input name | Stored name |
| --- | --- |
| `'  An  '` | `An` |
| `' Bình '` | `Bình` |
| `'Chi'` | `Chi` |

Each inserted row has an audit record containing the normalized `new_data`. `RETURNING` also reflects the output of `BEFORE` row triggers.

### 12.2. Inspecting the Main Table

~~~sql
SELECT
    order_id,
    customer_name,
    amount,
    status,
    updated_at
FROM trg_lab_367.orders
ORDER BY order_id;
~~~

### 12.3. Inspecting the Audit Table

~~~sql
SELECT
    audit_id,
    order_id,
    action,
    old_data,
    new_data
FROM trg_lab_367.order_audit
ORDER BY audit_id;
~~~

There are three `INSERT` records for the three rows. `old_data` is SQL NULL; `new_data` is a JSONB snapshot of the row after `BEFORE ROW` normalization.

### 12.4. Inspecting the Trace Table

~~~sql
SELECT
    trace_id,
    event_name,
    timing,
    trigger_level,
    order_id,
    detail
FROM trg_lab_367.trigger_trace
ORDER BY trace_id;
~~~

In a normal three-row `INSERT`, the trace contains one `BEFORE STATEMENT`, three `BEFORE ROW`, three `AFTER ROW`, and one `AFTER STATEMENT`—that is, **eight** trace records produced by the four trigger functions in the lab.

Do not infer physical row-processing order solely from `trace_id` when a SQL statement has multiple row sources, parallel execution, or other auxiliary triggers; the lab test demonstrates **timing categories**, not a row-ordering guarantee beyond an `ORDER BY` on the read query.

### 12.5. Updating a Row

~~~sql
UPDATE trg_lab_367.orders
SET customer_name = '  An Nguyễn  ',
    amount = 125000
WHERE customer_name = 'An'
RETURNING order_id, customer_name, amount, updated_at;
~~~

`BEFORE ROW` changes the name to `An Nguyễn` and updates the timestamp; `AFTER ROW` records `old_data`/`new_data`. Statement-level triggers run only once for the entire UPDATE.

### 12.6. Deleting a Row

~~~sql
DELETE FROM trg_lab_367.orders
WHERE customer_name = 'Chi'
RETURNING order_id, customer_name, amount;
~~~

For DELETE, there is no `NEW`. `AFTER ROW` auditing uses `OLD` to capture the snapshot of the deleted row. `DELETE ... RETURNING` retrieves appropriate data from the deleted row per PostgreSQL semantics.

### 12.7. Trigger Traces Also Roll Back

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE customer_name = 'Bình';

-- You can observe trace/audit changes right inside this transaction.
ROLLBACK;
~~~

After `ROLLBACK`, the row changes and the audit/trace records generated by the UPDATE no longer exist as committed changes. If you need evidence of **failed or rolled-back SQL statements**, you need out-of-transaction logging/auditing or an appropriate observability mechanism, not just a trigger audit table.

## 13. BEFORE ROW: Returning NULL to Skip a Row

To avoid affecting the main orders data, create an auxiliary lab table:

~~~sql
CREATE TABLE trg_lab_367.import_queue (
    import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_value text NOT NULL
);
~~~

### 13.1. Keep Only Non-Blank Strings

~~~sql
CREATE FUNCTION trg_lab_367.skip_blank_import()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF btrim(NEW.source_value) = '' THEN
        RETURN NULL; -- Skip only this INSERT row.
    END IF;

    NEW.source_value := btrim(NEW.source_value);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_skip_blank_import
BEFORE INSERT ON trg_lab_367.import_queue
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.skip_blank_import();
~~~

### 13.2. Inserting Multiple Rows

~~~sql
INSERT INTO trg_lab_367.import_queue(source_value)
VALUES ('  accepted  '), ('   '), ('second')
RETURNING import_id, source_value;
~~~

Only **two** rows—`accepted` and `second`—result. The whitespace-only input row is not inserted. It does not appear in `RETURNING` and does not produce a row-level `AFTER INSERT` event on this table.

### 13.3. The Problem With Silently Skipping Rows

If an import file has 1,000 lines and a statement processes 998 without raising an error, the system needs to know **which two rows were skipped and why**. `RETURN NULL` is usually only appropriate when business logic intentionally accepts silent skipping; if invalid values require explicit errors, use `RAISE EXCEPTION` or store failed rows in a dedicated import stream.

### 13.4. Identity Columns May Have Gaps

The sequence backing identity values may have allocated a number before a row was skipped or a transaction rolled back. Thus `import_id` is not guaranteed to be contiguous. **Do not use ID gaps as proof that a row was deleted or a transaction was committed.**

## 14. BEFORE DELETE: Controlling Delete Operations

A `BEFORE DELETE` trigger can return `OLD` to allow deletion to continue or `NULL` to skip the row.

~~~sql
CREATE FUNCTION trg_lab_367.protect_paid_order()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'paid' THEN
        RAISE EXCEPTION
            'Paid order % cannot be deleted', OLD.order_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_20_protect_paid_order
BEFORE DELETE ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.protect_paid_order();
~~~

### 14.1. Why RAISE EXCEPTION Instead of RETURN NULL?

If "paid orders cannot be deleted" is a **business invariant**, raising an explicit error is usually better than silently skipping. `RETURN NULL` causes DELETE to affect zero rows for that record, and a client that does not inspect row counts might assume the DELETE succeeded.

### 14.2. Deleting Multiple Rows When One Row Is Forbidden

~~~sql
DELETE FROM trg_lab_367.orders
WHERE status IN ('new', 'paid');
~~~

If the target set includes a `paid` order and the trigger throws an exception, the DELETE statement fails. Changes made within **the same statement** are rolled back under statement/transaction atomicity; earlier row deletions in that same statement are not kept as partial successes.

### 14.3. Triggers Do Not Replace DELETE Privileges

Control permissions with `GRANT`, Row-Level Security (where appropriate), API authorization, and state data. Triggers can enforce supplemental rules, but should not be treated as the sole substitute for access-control policies.

## 15. UPDATE OF column: Mentioned in SET vs. Value Actually Changed?

PostgreSQL lets a trigger run only on UPDATEs that mention specific columns:

~~~sql
CREATE TRIGGER trg_amount_update
AFTER UPDATE OF amount
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION some_schema.some_trigger_function();
~~~

**The `UPDATE OF amount` condition primarily checks whether `amount` is listed as a target in the UPDATE statement**, not whether the before and after values differ.

### 15.1. Two UPDATE Statements With the Same Value but Different Trigger Behavior

~~~sql
-- Mentions amount in SET:
UPDATE trg_lab_367.orders
SET amount = amount
WHERE order_id = 1;

-- Does not mention amount in SET:
UPDATE trg_lab_367.orders
SET note = 'metadata only'
WHERE order_id = 1;
~~~

If you only use `AFTER UPDATE OF amount` without `WHEN`:

- The first statement can fire the trigger even though `amount` did not change.
- The second statement does not fire the column-specific trigger, even if another `BEFORE UPDATE` trigger happened to modify `NEW.amount`.

That is the difference between **a column targeted for update** and **an actual value change**.

### 15.2. Creating a Separate Table to Log Real Amount Changes

~~~sql
CREATE TABLE trg_lab_367.amount_change_log (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    old_amount numeric(12,2),
    new_amount numeric(12,2),
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 15.3. Function to Log Amount Changes

~~~sql
CREATE FUNCTION trg_lab_367.log_amount_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.amount_change_log(
        order_id, old_amount, new_amount
    )
    VALUES (NEW.order_id, OLD.amount, NEW.amount);

    RETURN NULL; -- AFTER: return value is ignored.
END;
$$;
~~~

### 15.4. Attaching UPDATE OF Combined With WHEN

~~~sql
CREATE TRIGGER trg_80_amount_changed
AFTER UPDATE OF amount
ON trg_lab_367.orders
FOR EACH ROW
WHEN (OLD.amount IS DISTINCT FROM NEW.amount)
EXECUTE FUNCTION trg_lab_367.log_amount_change();
~~~

The `WHEN` condition filters for cases where before and after `amount` values actually differ. For `AFTER ROW` triggers, PostgreSQL can **evaluate WHEN at row-operation time** and only queue the trigger event when the condition is true, reducing unnecessary trigger function calls for unchanged rows.

### 15.5. Why IS DISTINCT FROM Is Useful

~~~sql
SELECT
    (NULL::integer = NULL::integer) AS equal_with_null,
    (NULL::integer IS DISTINCT FROM NULL::integer) AS distinct_with_null,
    (NULL::integer IS DISTINCT FROM 10) AS distinct_from_ten;
~~~

`=` can return SQL NULL when either side is NULL; `IS DISTINCT FROM` yields a clear boolean even with NULLs. Although the lab's `amount` column is `NOT NULL`, this pattern applies cleanly to nullable columns as well.

### 15.6. Comparing Three Scenarios

| UPDATE statement | `UPDATE OF amount`? | `WHEN OLD.amount IS DISTINCT FROM NEW.amount`? | Log function called? |
| --- | --- | --- | --- |
| `SET amount = amount` | Yes | No | No |
| `SET amount = amount + 100` | Yes | Yes (if genuinely changed) | Yes |
| `SET note = 'new'` | No | Not evaluated | No |

If business rules require logging **every actual change to amount**, even when another trigger alters `amount` despite the column not appearing in the SET list, use `AFTER UPDATE ON ... WHEN (...)` **without `OF amount`**. The design choice depends on exactly what needs to be captured.

### 15.7. UPDATE OF Does Not Guarantee Final Value Tracking

Another `BEFORE UPDATE` trigger can modify `NEW.amount`. `UPDATE OF amount` still relies on the SQL statement's target list rather than automatically tracking BEFORE trigger edits. Do not rely on `UPDATE OF` as the sole check for whether a column's value changed.

## 16. WHEN Clause: Condition Before Calling the Trigger Function

`CREATE TRIGGER` can include `WHEN (condition)` to restrict when the trigger fires.

### 16.1. BEFORE ROW WHEN

~~~sql
-- Example normalizing only when the client supplies a different name than before:
CREATE TRIGGER trg_example_name_change
BEFORE UPDATE ON trg_lab_367.orders
FOR EACH ROW
WHEN (OLD.customer_name IS DISTINCT FROM NEW.customer_name)
EXECUTE FUNCTION trg_lab_367.normalize_order_before();
~~~

In this example, `normalize_order_before` also updates `updated_at`. If you used this trigger **instead of** the existing normalize trigger, it would only update the timestamp when the name changes, not on every UPDATE. Pick the right contract; do not deploy accidentally to production.

For the active lab that already has `trg_10_normalize_order`, **do not create this extra example trigger** unless you intend to change behavior; the snippet illustrates `WHEN` syntax and semantics.

### 16.2. AFTER ROW WHEN

~~~sql
WHEN (OLD.status IS DISTINCT FROM NEW.status)
~~~

is well-suited to emit an event only when the order status genuinely changes. Note that `INSERT` has no `OLD`, and `DELETE` has no `NEW`. Never write a `WHEN` expression referencing a variable that does not exist for that event.

### 16.3. INSTEAD OF Does Not Support WHEN

`INSTEAD OF` triggers on views **cannot specify `WHEN`**. If you need conditional skipping or routing on a view, write `IF ... THEN` logic inside the trigger function and return a row or NULL per the rules.

### 16.4. WHEN Cannot Contain Subqueries

In `CREATE TRIGGER` syntax, the `WHEN` expression has restrictions, including a prohibition on SQL subqueries. If complex conditional logic needs to query external data, put it inside the trigger function with full awareness of transactions, locks, and overhead.

### 16.5. WHEN on Deferred Constraint Triggers

For a deferrable constraint trigger, the `WHEN` expression is still evaluated **immediately after the row modification**, deciding whether to queue the trigger event. Do not assume `WHEN` will be re-evaluated at the end of the transaction when the deferred event executes.

## 17. Multiple Triggers With the Same Timing: Alphabetical Name Order

PostgreSQL specifies that when **multiple triggers of the same kind** share the same event, timing, and level on a relation, they execute in **alphabetical order by trigger name**.

Example:

~~~text
BEFORE UPDATE ROW on orders:
  trg_10_normalize_order
  trg_20_check_something
  trg_30_add_metadata
~~~

If all three apply, alphabetical naming helps predict how one trigger sees `NEW` modified by an earlier trigger.

### 17.1. Note on Return Value Interactions

~~~text
trg_10 -> modifies NEW, RETURN NEW
trg_20 -> receives modified row, RETURN NEW
trg_30 -> RETURN NULL
        -> skips row operation; subsequent row triggers do not run.
~~~

If renaming a trigger changes alphabetical order, the outcome can change. However, **do not build workflows overly dependent on many interacting triggers**; a single trigger function with clear responsibilities is often easier to maintain.

### 17.2. Alphabetical Order Does Not Override Timing

Naming a trigger `zzz_before_row` will not make it run after `aaa_after_row`: **timing and level** still determine the execution phase. Alphabetical ordering applies only among triggers of the same category.

### 17.3. Do Not Use Naming to Simulate Transaction Boundaries

Triggers within the same statement still do not commit independently; ordered naming does not create new transactions.

### 17.4. Inspecting Existing Trigger Names

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_catalog.pg_get_triggerdef(oid) AS definition
FROM pg_catalog.pg_trigger
WHERE tgrelid = 'trg_lab_367.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

This is a read-only metadata query, useful for identifying similarly named triggers or triggers created by older migrations.

## 18. Transition Tables: Inspecting the Entire Changed Row Set

During bulk DML, if you want to compute `COUNT(*)` or `SUM(amount)` for **the newly inserted rows**, running a separate SELECT inside every AFTER ROW trigger would be costly. PostgreSQL supports **transition relations**:

- `REFERENCING NEW TABLE AS ...`: the set of new rows from the statement.
- `REFERENCING OLD TABLE AS ...`: the set of old rows before UPDATE/DELETE.

Transition tables are used with **AFTER triggers** on regular tables (subject to `CREATE TRIGGER` restrictions), not with `BEFORE` or `INSTEAD OF`. Specifically, an `UPDATE` trigger with transition tables **cannot specify `UPDATE OF column_name`**.

### 18.1. Create a Statement Summary Table

~~~sql
CREATE TABLE trg_lab_367.statement_summary (
    summary_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    changed_rows bigint NOT NULL,
    amount_delta numeric(14,2),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 18.2. AFTER INSERT STATEMENT With NEW TABLE

~~~sql
CREATE FUNCTION trg_lab_367.summarize_insert_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.statement_summary(
        event_name, changed_rows, amount_delta
    )
    SELECT
        'INSERT',
        COUNT(*),
        COALESCE(SUM(amount), 0)
    FROM inserted_orders;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_95_summarize_insert
AFTER INSERT ON trg_lab_367.orders
REFERENCING NEW TABLE AS inserted_orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.summarize_insert_statement();
~~~

The name `inserted_orders` is a **transition relation** declared on the trigger, usable like a temporary table scoped to that trigger event context; there is no need to run `CREATE TEMP TABLE inserted_orders`.

### 18.3. Testing Multi-Row INSERT in a Single Statement

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES
    ('Dũng', 10000, 'new'),
    ('Em', 20000, 'new');

SELECT
    event_name,
    changed_rows,
    amount_delta
FROM trg_lab_367.statement_summary
ORDER BY summary_id;
~~~

In this two-row INSERT example, the new summary has `changed_rows=2` and `amount_delta=30000`. It does not count all rows in the table, only **the rows belonging to the current INSERT event**.

### 18.4. An INSERT Adding Zero Rows Still Fires the Statement Trigger

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
SELECT
    'Nothing',
    0,
    'new'
WHERE FALSE;
~~~

The statement-level AFTER INSERT trigger still runs; the transition relation `inserted_orders` is empty, so the summary records `changed_rows=0` and `amount_delta=0`. This directly demonstrates the difference between a **statement trigger** and a row trigger.

### 18.5. AFTER UPDATE STATEMENT With OLD and NEW TABLE

~~~sql
CREATE FUNCTION trg_lab_367.summarize_update_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.statement_summary(
        event_name, changed_rows, amount_delta
    )
    SELECT
        'UPDATE',
        COUNT(*),
        COALESCE(SUM(n.amount - o.amount), 0)
    FROM new_orders AS n
    JOIN old_orders AS o USING (order_id);

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_96_summarize_update
AFTER UPDATE ON trg_lab_367.orders
REFERENCING
    OLD TABLE AS old_orders
    NEW TABLE AS new_orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.summarize_update_statement();
~~~

In the lab, `order_id` is the primary key and examples do not modify primary keys, so joining `OLD`/`NEW` on `order_id` works. In domains that **allow updating the primary key**, joining on a mutated key breaks down; you need a different matching strategy or to forbid primary-key updates via constraints/design.

### 18.6. Testing Set-Based UPDATE

~~~sql
UPDATE trg_lab_367.orders
SET amount = amount + 1000
WHERE status = 'new';

SELECT
    summary_id,
    event_name,
    changed_rows,
    amount_delta
FROM trg_lab_367.statement_summary
ORDER BY summary_id;
~~~

If there are three `new` orders at execution time, the new UPDATE summary shows `changed_rows=3` and `amount_delta=3000`. The exact row count depends on which DELETE/UPDATE examples you ran earlier in the lab.

### 18.7. Transition Tables vs. Row NEW/OLD

| Row-level trigger | Statement-level with transition relation |
| --- | --- |
| `NEW.amount` of one row | `SELECT SUM(amount) FROM new_orders` |
| `OLD.status` of one row | `SELECT ... FROM old_orders` |
| Executes per row | Once per statement (subject to event/special limits) |
| Not ideal for bulk aggregates | Usually far more efficient for set-based aggregates |

### 18.8. UPDATE OF and Transition Tables

Do not write:

~~~sql
-- Syntax not supported together with transition tables:
-- CREATE TRIGGER ...
-- AFTER UPDATE OF amount ON ...
-- REFERENCING OLD TABLE AS ... NEW TABLE AS ...
~~~

If you only care about `amount` changes, create `AFTER UPDATE` (without `OF amount`) with transition tables, then compare `old_rows.amount` and `new_rows.amount` inside the transition relation query/function.

### 18.9. Transition Relations Are Not Full-Table Snapshots

`NEW TABLE`/`OLD TABLE` contain only the rows touched by the statement, not the entire relation. Do not use them to compute global system revenue or total order counts while ignoring untouched rows.

### 18.10. When Partitioning or FK Cascades Are Involved

In certain special cases, a statement can split into multiple event sets/transition relations due to trigger semantics. Check documentation for your running version and write tests before assuming "there is always a single transition table for any complex logic."

## 19. INSTEAD OF: Special Triggers on Views

When an application operates through a view, there are two cases:

- The view is **automatically updatable**, so PostgreSQL can map INSERT/UPDATE/DELETE directly to the base table when supported conditions hold.
- The view contains joins, aggregates, computed expressions, or complex logic and is **not automatically updatable**; or we want to govern DML under custom policy. In that case, use an **`INSTEAD OF` trigger**.

An `INSTEAD OF` trigger is a **row-level trigger** that executes instead of `INSERT`, `UPDATE`, or `DELETE` on a view; it does not apply to base tables like regular `BEFORE`/`AFTER` triggers.

### 19.1. Create a View With a Computed Column

~~~sql
CREATE VIEW trg_lab_367.v_order_editor AS
SELECT
    order_id,
    customer_name,
    amount,
    status,
    note,
    amount * 1.05 AS gross_estimate
FROM trg_lab_367.orders
WHERE status <> 'cancelled';
~~~

`gross_estimate` is a computed expression, meaning this view **does not automatically satisfy all requirements of a simple automatically updatable view**. We intentionally use `INSTEAD OF` to define how writes map to the base table while preventing clients from directly assigning the computed column.

### 19.2. Designing the View Contract

| Operation sent to view | Action inside trigger |
| --- | --- |
| `INSERT` | Insert into `orders`; base-table BEFORE trigger normalizes name |
| `UPDATE` | Update base row by `OLD.order_id`; return updated row |
| `DELETE` | Delete base row; base-table BEFORE DELETE can reject paid orders |
| `RETURNING` | Return matching view row if the operation succeeded |
| Assigning `gross_estimate` | Disallow treating as an independent writable field; recompute from amount |

### 19.3. Write One Trigger Function Handling All Three Operations

~~~sql
CREATE FUNCTION trg_lab_367.edit_order_view()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_base trg_lab_367.orders%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.order_id IS NOT NULL THEN
            RAISE EXCEPTION
                'order_id is generated by the database';
        END IF;

        IF NEW.status = 'cancelled' THEN
            RAISE EXCEPTION
                'Cancelled orders are not writable through this view';
        END IF;

        INSERT INTO trg_lab_367.orders(
            customer_name, amount, status, note
        )
        VALUES (
            NEW.customer_name,
            NEW.amount,
            COALESCE(NEW.status, 'new'),
            NEW.note
        )
        RETURNING * INTO v_base;

        NEW.order_id := v_base.order_id;
        NEW.customer_name := v_base.customer_name;
        NEW.amount := v_base.amount;
        NEW.status := v_base.status;
        NEW.note := v_base.note;
        NEW.gross_estimate := v_base.amount * 1.05;

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.order_id IS DISTINCT FROM OLD.order_id THEN
            RAISE EXCEPTION
                'order_id cannot change through this view';
        END IF;

        IF NEW.status = 'cancelled' THEN
            RAISE EXCEPTION
                'Cannot move a row outside this view by UPDATE';
        END IF;

        UPDATE trg_lab_367.orders AS o
        SET customer_name = NEW.customer_name,
            amount = NEW.amount,
            status = NEW.status,
            note = NEW.note
        WHERE o.order_id = OLD.order_id
        RETURNING * INTO v_base;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;

        NEW.customer_name := v_base.customer_name;
        NEW.amount := v_base.amount;
        NEW.status := v_base.status;
        NEW.note := v_base.note;
        NEW.gross_estimate := v_base.amount * 1.05;

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM trg_lab_367.orders AS o
        WHERE o.order_id = OLD.order_id
        RETURNING * INTO v_base;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;
~~~

**Example scope:** this function assumes view rows are not unexpectedly altered by concurrent clients mid-processing. `UPDATE/DELETE` targets the row key rather than `customer_name` to avoid duplicate-name collisions. In production, review permissions, concurrency, soft-delete policies, and exposing computed columns.

### 19.4. Attach the Trigger to the View

~~~sql
CREATE TRIGGER trg_v_order_editor
INSTEAD OF INSERT OR UPDATE OR DELETE
ON trg_lab_367.v_order_editor
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.edit_order_view();
~~~

Do not write `FOR EACH STATEMENT` for `INSTEAD OF`. Here the trigger function's `NEW`/`OLD` use the **row shape of the view**, which differs from the base table's row shape whenever the view adds or omits columns.

### 19.5. INSERT Through the View

~~~sql
INSERT INTO trg_lab_367.v_order_editor(
    customer_name, amount, status, note
)
VALUES (
    '  Hà  ',
    23000,
    'new',
    'inserted through view'
)
RETURNING order_id, customer_name, amount, gross_estimate;
~~~

Execution flow:

1. The view's `INSTEAD OF INSERT` trigger is called with `NEW`.
2. The trigger executes an `INSERT` into base table `orders`.
3. `BEFORE INSERT` and `AFTER INSERT` triggers **on the base table** run normally.
4. `customer_name` in the base table is normalized to `Hà`.
5. The view trigger retrieves the written row and returns the view's `NEW` so `RETURNING` sees the proper order_id/name/gross_estimate.

The value `gross_estimate = 23000 * 1.05 = 24150` matches the example. This is only an **illustrative value**; do not use this simple multiplication as a real tax/pricing model where rounding, currency, or complex tax rules apply.

### 19.6. UPDATE Through the View

~~~sql
UPDATE trg_lab_367.v_order_editor
SET customer_name = ' Hà Nguyễn ',
    amount = 26000
WHERE note = 'inserted through view'
RETURNING
    order_id,
    customer_name,
    amount,
    gross_estimate;
~~~

The view trigger runs a separate `UPDATE` on the base table and returns the row version after the base-table BEFORE trigger normalized the name. `AFTER UPDATE` triggers on the base table also run, so the audit table gets an `UPDATE` record.

### 19.7. DELETE Through the View

~~~sql
DELETE FROM trg_lab_367.v_order_editor
WHERE note = 'inserted through view'
RETURNING order_id, customer_name, amount;
~~~

The view trigger deletes the base row, generates a DELETE audit record via the base-table AFTER trigger, and returns the view's `OLD`. If the base row no longer exists at DELETE time, the function returns NULL to indicate the row was not processed.

### 19.8. What Does RETURN NULL Do in INSTEAD OF?

For an `INSTEAD OF` row trigger:

- `RETURN NULL` means **the row was not handled**: not counted as an affected row and not emitted as a processed row in `RETURNING`.
- Returning `NEW` (INSERT/UPDATE) or `OLD` (DELETE) as designed signals the row was handled.
- The return value does not write to the base table by itself. The **INSERT/UPDATE/DELETE statements inside the trigger function** perform the actual work.

This is a fundamental difference from `BEFORE ROW` on a base table, where returning `NEW` tells PostgreSQL to proceed with the original row DML operation.

### 19.9. INSTEAD OF Views Do Not Create New Transactions

`INSERT INTO view`, base-table operations inside the trigger, and audit rows all belong to the same transaction under PostgreSQL semantics. If any step throws an exception failing the statement, changes within that statement roll back, excluding external non-transactional side effects outside database control.

### 19.10. Avoid Arbitrary Dynamic SQL in DML Handlers

Relation and field names inside trigger functions should be schema-qualified and explicitly named. If dynamic SQL is unavoidable, distinguish identifier quoting from value parameterization (`format('%I', ...)`, `USING`) to prevent injection. Never assume view permissions automatically replace all base-table protections.

## 20. INSTEAD OF vs. Automatically Updatable Views

A simple view:

~~~sql
CREATE VIEW trg_lab_367.v_simple_orders AS
SELECT
    order_id,
    customer_name,
    amount,
    status
FROM trg_lab_367.orders
WHERE status <> 'cancelled';
~~~

can be **automatically updatable** under PostgreSQL's supported conditions without needing an `INSTEAD OF` trigger.

### 20.1. When is INSTEAD OF unnecessary?

- The view selects from a single simple table;
- There are no constructs that break auto-updatability;
- Base-row update semantics are straightforward;
- `WITH CHECK OPTION` can help ensure modified rows stay within the view predicate when appropriate.

### 20.2. When should you consider INSTEAD OF?

- The view involves joins or expressions that are not auto-updatable;
- A single view operation must fan out across multiple base tables;
- Custom mapping or validation logic is needed;
- You want explicit control over `RETURNING` output and affected row counts;
- You do not want to expose the entire base-table structure to the API.

### 20.3. When should you avoid INSTEAD OF?

- Overly complex logic makes the view unpredictable;
- A single UPDATE through the view triggers unintended cascading side effects;
- Performance suffers because one view row generates many repeated DML queries;
- An explicit API or procedure with a clear transaction contract would be cleaner;
- The security model has not been thoroughly reviewed.

### 20.4. Do Not Confuse View Triggers With Base-Table Triggers

In our example:

~~~text
INSERT INTO v_order_editor
       |
       +-- INSTEAD OF INSERT ROW on view
               |
               +-- INSERT INTO orders
                       |
                       +-- BEFORE INSERT triggers on orders
                       +-- Write orders
                       +-- AFTER INSERT triggers on orders
~~~

A view trigger does not bypass constraints or triggers on the base table when it executes SQL against the base table. Base-table triggers can still raise errors and roll back the entire statement.

## 21. AFTER Constraint Triggers: Deferrable Unlike Regular AFTER Triggers

Not every `AFTER` trigger has to execute immediately at the end of the statement. PostgreSQL supports **constraint triggers** of the form:

~~~sql
CREATE CONSTRAINT TRIGGER trigger_name
AFTER INSERT OR UPDATE OR DELETE
ON table_name
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION trigger_function();
~~~

This trigger type is typically used to enforce multi-row or cross-table business constraints that must be evaluated at the **end of the transaction**, adjustable via `SET CONSTRAINTS`.

### 21.1. Key Points to Remember

- Constraint triggers use **AFTER ROW**, not BEFORE or INSTEAD OF.
- They can be declared `DEFERRABLE`, `INITIALLY IMMEDIATE`, or `INITIALLY DEFERRED`.
- Execution can occur **at the end of the transaction** when deferred.
- `SET CONSTRAINTS ... IMMEDIATE` causes pending deferred trigger events to run immediately at mode switch time.
- This mechanism differs from regular `AFTER ROW` triggers, which run at statement time.

### 21.2. Business Example: Paid Orders Must Have Positive Amount

The rule that `status='paid'` is only valid when `amount > 0` is actually expressed **better** as a CHECK constraint:

~~~sql
-- Simpler constraint example that should be preferred:
-- CHECK (status <> 'paid' OR amount > 0)
~~~

However, to study **deferred constraint triggers**, we intentionally simulate a rule evaluated against **end-of-transaction** data.

### 21.3. Create the Final-State Verification Function

~~~sql
CREATE FUNCTION trg_lab_367.check_paid_order_deferred()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_status text;
    v_amount numeric(12,2);
BEGIN
    -- Read the CURRENT state of the row, rather than relying only on the NEW snapshot
    -- captured when the event was queued.
    SELECT
        o.status,
        o.amount
    INTO v_status, v_amount
    FROM trg_lab_367.orders AS o
    WHERE o.order_id = NEW.order_id;

    IF FOUND
       AND v_status = 'paid'
       AND v_amount <= 0 THEN
        RAISE EXCEPTION
            'Paid order % must have positive amount',
            NEW.order_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 21.4. Register the Deferred Constraint Trigger

~~~sql
CREATE CONSTRAINT TRIGGER trg_paid_amount_deferred
AFTER INSERT OR UPDATE
ON trg_lab_367.orders
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
WHEN (NEW.status = 'paid')
EXECUTE FUNCTION trg_lab_367.check_paid_order_deferred();
~~~

`WHEN (NEW.status='paid')` is evaluated **immediately when the row event occurs**, deciding whether to queue the event. The function then **reads the row's current state when it actually executes**, checking whether later changes in the same transaction fixed the rule.

### 21.5. Two Steps Within the Same Transaction

Suppose we insert a test order:

~~~sql
INSERT INTO trg_lab_367.orders(customer_name, amount, status)
VALUES ('Demo deferred', 0, 'new')
RETURNING order_id;
~~~

Note the returned `order_id`, assuming `:test_id` is a client-supplied variable/placeholder. Then:

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE order_id = :test_id;

-- Temporarily status='paid', amount=0 inside the transaction.

UPDATE trg_lab_367.orders
SET amount = 50000
WHERE order_id = :test_id;

COMMIT;
~~~

Because the trigger is deferred and no other constraint blocks the intermediate state, validation can occur at commit, observe the final state `paid` with `amount=50000`, and allow the transaction to succeed.

**`:test_id` is an illustrative placeholder, not standard PostgreSQL SQL syntax.** In psql you can use substitution variables; in JDBC use `?`. Do not paste `:test_id` verbatim into a SQL client that does not support it.

### 21.6. If Amount Is Not Fixed Before Commit

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid', amount = 0
WHERE order_id = :test_id;

COMMIT; -- may raise an error from the deferred constraint trigger
~~~

When commit invokes the deferred trigger and the rule fails, the transaction is not committed. PostgreSQL preserves transaction atomicity; the client must handle the error and verify session state.

### 21.7. SET CONSTRAINTS IMMEDIATE

~~~sql
BEGIN;

SET CONSTRAINTS trg_paid_amount_deferred IMMEDIATE;

-- From here on, events applying this trigger are processed
-- in immediate mode; pending events may be checked here.

ROLLBACK;
~~~

The constraint trigger name may need schema qualification if duplicate names exist. `SET CONSTRAINTS` applies to deferrable constraints; it does not turn ordinary AFTER triggers into deferred triggers.

### 21.8. Practical Limitations

A deferred trigger that re-reads rows via `SELECT` at check time must be carefully engineered for concurrency, deletions, and multi-table invariants. For a simple single-row condition like `amount>0`, a **CHECK constraint is clearer and stronger**. Never use a deferred trigger merely to postpone a simple error without a genuine business reason.

### 21.9. AFTER Does Not Always Mean After Every Constraint

Constraints like CHECK/NOT NULL, FK actions, and immediate/deferred constraint triggers each have distinct semantics. An `AFTER ROW` trigger typically sees the modified row, but **does not guarantee all deferred constraints in the transaction have already been validated**. Distinguish "after the row change" from "after all transaction constraints are checked."

## 22. TRUNCATE: Statement-Level Triggers Only

`TRUNCATE` removes rows from a table using a different mechanism than `DELETE`. PostgreSQL supports:

~~~sql
CREATE TRIGGER trg_before_truncate
BEFORE TRUNCATE ON some_schema.some_table
FOR EACH STATEMENT
EXECUTE FUNCTION some_schema.trigger_function();
~~~

And `AFTER TRUNCATE FOR EACH STATEMENT`. **There is no `FOR EACH ROW` trigger for TRUNCATE**, because PostgreSQL does not process rows individually in a way that fires DELETE row triggers.

### 22.1. Create an Auxiliary Lab Table

~~~sql
CREATE TABLE trg_lab_367.temp_items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label text NOT NULL
);

INSERT INTO trg_lab_367.temp_items(label)
VALUES ('A'), ('B'), ('C');
~~~

### 22.2. BEFORE TRUNCATE Trigger

~~~sql
CREATE FUNCTION trg_lab_367.trace_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'truncate event'
    );

    RETURN NULL; -- Statement trigger: return value is ignored.
END;
$$;

CREATE TRIGGER trg_before_truncate_items
BEFORE TRUNCATE ON trg_lab_367.temp_items
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_truncate();

CREATE TRIGGER trg_after_truncate_items
AFTER TRUNCATE ON trg_lab_367.temp_items
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_truncate();
~~~

### 22.3. Testing Inside a Transaction and Rolling Back

~~~sql
BEGIN;

TRUNCATE trg_lab_367.temp_items;

SELECT COUNT(*) AS rows_after_truncate
FROM trg_lab_367.temp_items;

ROLLBACK;

SELECT COUNT(*) AS rows_after_rollback
FROM trg_lab_367.temp_items;
~~~

Inside the transaction, the table is truncated and `rows_after_truncate=0`. After `ROLLBACK`, the original rows are restored thanks to PostgreSQL's transaction-safe `TRUNCATE`. Trace records for TRUNCATE belong to the same rolled-back transaction and are not committed either.

### 22.4. Differences Between DELETE and TRUNCATE

| Criterion | DELETE | TRUNCATE |
| --- | --- | --- |
| Fires row-by-row triggers | Can fire row-level DELETE triggers | **No** |
| Statement triggers | BEFORE/AFTER DELETE STATEMENT | BEFORE/AFTER TRUNCATE STATEMENT |
| WHERE predicate | Yes | No |
| RETURNING rows | Yes | No |
| MVCC/locking semantics | Follows DELETE | TRUNCATE has special locking/visibility effects |
| Rollbackable in a transaction | Yes | Yes in standard PostgreSQL |

**Do not use TRUNCATE to "quickly clear" a table that relies on BEFORE/AFTER DELETE row triggers for business integrity.** Foreign keys and privileges also have specific rules to verify.

## 23. INSERT ... ON CONFLICT DO UPDATE: Two Trigger Types Can Participate

In PostgreSQL, UPSERT:

~~~sql
INSERT INTO some_table(...)
VALUES (...)
ON CONFLICT (unique_key)
DO UPDATE SET ...;
~~~

has more complex trigger semantics than a plain INSERT or UPDATE.

### 23.1. Row-Level BEFORE INSERT and BEFORE UPDATE

When **a conflict occurs and branches to DO UPDATE**, PostgreSQL can execute:

1. `BEFORE INSERT ROW` triggers on the proposed INSERT row;
2. Unique conflict detection;
3. `BEFORE UPDATE ROW` triggers on the existing row;
4. Row update if `ON CONFLICT DO UPDATE ... WHERE` allows;
5. Corresponding `AFTER UPDATE ROW` triggers.

Modifications made by `BEFORE INSERT` to `NEW` can affect the `EXCLUDED` values read in `DO UPDATE`. Thus **a single SQL statement can pass through both BEFORE INSERT and BEFORE UPDATE stages**.

### 23.2. Statement-Level Triggers for Both INSERT and UPDATE

When a statement contains `ON CONFLICT DO UPDATE`, PostgreSQL can fire **both INSERT and UPDATE statement-level triggers** per defined rules, even if the set of rows actually conflicting/updating is empty. Statement-level ordering matters:

~~~text
BEFORE INSERT statement
BEFORE UPDATE statement
... row-level actions ...
AFTER UPDATE statement
AFTER INSERT statement
~~~

Do not deduce from "0 rows updated" that `AFTER UPDATE STATEMENT` will not run; **statement-level triggers do not depend solely on affected row count**.

### 23.3. Create a Dedicated Demo Table

~~~sql
CREATE TABLE trg_lab_367.upsert_demo (
    demo_key text PRIMARY KEY,
    value_text text NOT NULL
);
~~~

We do not need to install every trigger onto the demo table to see the mechanics; you can attach similar `CREATE TRIGGER` statements during advanced lab practice.

~~~sql
INSERT INTO trg_lab_367.upsert_demo(demo_key, value_text)
VALUES ('A', 'first')
ON CONFLICT (demo_key)
DO UPDATE SET value_text = EXCLUDED.value_text;

INSERT INTO trg_lab_367.upsert_demo(demo_key, value_text)
VALUES ('A', 'second')
ON CONFLICT (demo_key)
DO UPDATE SET value_text = EXCLUDED.value_text;
~~~

The first operation inserts; the second updates the row with `demo_key='A'`. When attaching triggers to such a table, design `BEFORE INSERT` and `BEFORE UPDATE` so they do not repeatedly normalize fields in conflicting ways or trigger unwanted side effects.

### 23.4. ON CONFLICT DO NOTHING

With `DO NOTHING`, a conflicting row is not inserted, so there is no `AFTER INSERT ROW` for the skipped row. However, **BEFORE INSERT ROW** triggers may already have been called while preparing the candidate row, and **INSERT STATEMENT triggers** still follow statement semantics. Never assume "DO NOTHING means no triggers run."

### 23.5. Avoid Non-Rollbackable Side Effects in BEFORE INSERT

If `BEFORE INSERT` fires an external webhook and then UPSERT falls into `DO NOTHING` or the transaction rolls back, the webhook may have fired even though no new row exists. **Never execute network side effects inside triggers**; use an outbox and an independent post-commit dispatcher.

## 24. MERGE: Combined INSERT/UPDATE/DELETE Events

PostgreSQL supports `MERGE` in modern versions (since PostgreSQL 15). It is a statement that can specify multiple action branches:

~~~sql
MERGE INTO target_table AS t
USING source_table AS s
ON t.id = s.id
WHEN MATCHED THEN
    UPDATE SET value_text = s.value_text
WHEN NOT MATCHED THEN
    INSERT (id, value_text)
    VALUES (s.id, s.value_text);
~~~

### 24.1. No "MERGE" Trigger Event Exists

PostgreSQL triggers for `MERGE` bind to the corresponding **INSERT/UPDATE/DELETE** events rather than introducing a separate `TG_OP='MERGE'` DML event.

### 24.2. Statement-Level Triggers

If a `MERGE` defines `INSERT`/`UPDATE`/`DELETE` branches, statement-level triggers for those specified action types may run **even when a particular branch applies to zero rows**. Row-level triggers fire only for the row actions actually executed, according to each branch's semantics.

### 24.3. Why Testing Matters

If a procedure relies on statement-level auditing to count rows, it cannot treat "trigger fired" as proof that at least one row was inserted, updated, or deleted. You need row counts or transition relations and must verify behavior for your exact major version.

### 24.4. Distinguishing MERGE From ON CONFLICT

Both `MERGE` and `INSERT ON CONFLICT` can trigger multiple kinds of row actions, yet they differ significantly in semantics and trigger firing. **Do not copy trigger-timing assumptions from UPSERT to MERGE without checking the corresponding documentation.**

## 25. FOREIGN KEY Cascading Actions and Triggers

PostgreSQL implements parts of foreign key referential actions using internal triggers. When using:

~~~sql
CREATE TABLE parent_table (
    id bigint PRIMARY KEY
);

CREATE TABLE child_table (
    id bigint PRIMARY KEY,
    parent_id bigint NOT NULL
        REFERENCES parent_table(id)
        ON DELETE CASCADE
);
~~~

deleting a parent can cascade to delete child rows.

### 25.1. Child Row Triggers Can Fire

If the child table has an `AFTER DELETE ROW` audit trigger, child deletions triggered by `ON DELETE CASCADE` can also fire it per trigger semantics. Never assume only direct DELETE statements issued against the child table generate audit logs.

### 25.2. Not a Separate Transaction Outside the Trigger

Cascading actions happen **within the original statement's transaction**; if a child trigger fails, the transaction/statement can roll back. Do not view cascades as separate committed asynchronous jobs.

### 25.3. Issues With Multiple Related Tables

A parent DELETE can affect multiple child and grandchild tables, each with its own row and statement triggers. Business logic relying on a **global interaction order** across triggers on multiple relations must be modeled and tested carefully—never deduce full cascade order from trigger names on a single table.

### 25.4. Internal Triggers vs. User Triggers

In `pg_trigger`, `tgisinternal` distinguishes triggers created by constraint mechanisms. Never disable or manually edit FK-backing internal triggers for a quick migration; doing so can corrupt referential integrity.

### 25.5. Using Triggers to Audit FK Changes

If you need to know which child rows were indirectly deleted, attaching an audit trigger to the child table captures that information within the same transaction. However, those audit records roll back if the parent DELETE transaction rolls back. For legal auditing that requires recording failed attempts, use an external logging system.

## 26. Partitioned Tables: Triggers When UPDATE Moves a Row Between Partitions

Modern PostgreSQL allows row-level triggers on partitioned tables under specific rules; creating a row-level trigger on a partitioned parent creates/maintains **cloned triggers** on the partitions.

### 26.1. UPDATE Causing Partition Movement

Suppose a table is partitioned by day/month and an UPDATE changes the partition key so a row moves from partition A to partition B.

In PostgreSQL, **row movement** is generally executed as a **DELETE from the old partition + INSERT into the new partition**, rather than an in-place UPDATE within a single heap relation.

### 26.2. Row-Level Events to Remember

When an UPDATE moves a row:

- `BEFORE UPDATE ROW` and `BEFORE DELETE ROW` may run on the source partition.
- `BEFORE INSERT ROW` runs on the destination partition.
- `AFTER DELETE ROW` and `AFTER INSERT ROW` can fire for the row movement.
- **`AFTER UPDATE ROW` does not fire as a normal UPDATE ROW** for a row that moved partitions, because the operation became a delete/insert.

### 26.3. Statement-Level Triggers Still Follow UPDATE

Statement-level triggers attached to the original SQL **UPDATE** have their own semantics; do not assume statement-level INSERT/DELETE triggers automatically fire simply because row movement performs delete/insert at the row level.

### 26.4. Implications for Auditing

If audit logic only attaches to `AFTER UPDATE ROW`, it can **miss partition-key changes that cause row movement**. Account for DELETE+INSERT events or design statement-level auditing, and test directly against your partitioned schema.

### 26.5. Versions and Design

Partition trigger details have evolved across PostgreSQL major versions; before deploying to production, read the `Partitioning` and `Trigger Behavior` sections for your exact version. Never transfer assumptions from plain tables unmodified to partition moves.

## 27. COPY FROM Also Fires INSERT Triggers

When loading data via:

~~~sql
COPY trg_lab_367.orders (
    customer_name, amount, status
)
FROM STDIN WITH (FORMAT csv);
~~~

`COPY FROM` inserts rows into the table and **fires INSERT triggers** according to PostgreSQL semantics. This means:

- `BEFORE INSERT ROW` can normalize each row;
- `AFTER INSERT ROW` can write audit records for each row;
- Statement-level INSERT triggers can run for the COPY operation;
- Very large imports can become slow if triggers run additional per-row SQL.

### 27.1. Do Not Disable Triggers for Fast Imports Without Governance

Some bulk-load procedures consider disabling user triggers or using staging tables, yet disabling triggers without proper controls can bypass validation/auditing and leave invalid data. In particular, never alter settings affecting FK or replication-trigger behavior as an ad-hoc speed hack.

### 27.2. A Safer Staging Pattern

~~~text
COPY into staging table
    |
    +-- Validate/normalize and record rejected rows
    |
    +-- INSERT ... SELECT from staging into main table
            |
            +-- BEFORE/AFTER triggers + constraints
~~~

This lets you control input quality and count rejected rows, rather than using `RETURN NULL` to silently drop bad data mid-import.

## 28. GENERATED Columns and BEFORE/AFTER Timing

PostgreSQL supports generated columns, for example:

~~~sql
CREATE TABLE trg_lab_367.generated_demo (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity integer NOT NULL,
    unit_price numeric(12,2) NOT NULL,
    line_total numeric(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

### 28.1. Evaluation Timing of Stored Generated Columns

For a **stored generated column**, PostgreSQL computes the expression **after `BEFORE ROW` triggers and before `AFTER ROW` triggers inspect the written row values**.

This means:

- A `BEFORE ROW` trigger can adjust `NEW.quantity`/`NEW.unit_price`.
- `line_total` is computed from the final base values under generated-column rules.
- An `AFTER ROW` trigger can read the finalized generated column value.
- Do not rely on `NEW.line_total` inside a `BEFORE ROW` trigger as if it were already finalized.

### 28.2. Do Not Use a Trigger to Manually Recompute a Generated Column

~~~sql
-- Avoid:
-- NEW.line_total := NEW.quantity * NEW.unit_price;
~~~

`line_total` is a PostgreSQL-managed generated column. If the requirement is simply an arithmetic formula from other columns in the row, a generated column is usually cleaner than a manual trigger.

### 28.3. Updating Inputs Recomputes the Value

~~~sql
INSERT INTO trg_lab_367.generated_demo(
    quantity, unit_price
)
VALUES (2, 10000)
RETURNING item_id, quantity, unit_price, line_total;
~~~

`line_total` is 20000. Updating quantity to 3 automatically updates the generated value accordingly.

### 28.4. PostgreSQL Versions

Generated column capabilities (STORED/VIRTUAL) and their constraints vary by major version. This example uses **STORED** to demonstrate evaluation order. When using an older server or virtual generated columns on a newer server, consult the documentation for that version.

## 29. Constraints and Timing: BEFORE Cannot Bypass NOT NULL/CHECK/FK

A row-level `BEFORE` trigger can modify `NEW`, yet **it has no power to let an invalid constraint commit**.

### 29.1. Table With CHECK amount >= 0

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('Invalid', -10, 'new');
~~~

The normalization trigger may run, but afterwards `CHECK (amount >= 0)` blocks the invalid row. Neither the row nor any inserts performed by the trigger in that statement are committed.

### 29.2. Do Not Oversimplify the Order

PostgreSQL defines timing rules for BEFORE triggers, generated columns, constraints, AFTER triggers, and deferred constraint triggers. Some checks can be deferred while others cannot; foreign key enforcement also uses internal triggers.

**Do not build applications assuming all constraints strictly run before all AFTER triggers or vice versa in a single rigid list across all versions.** What matters is that non-deferred constraints are enforced per statement semantics, while deferred constraints may check up to transaction end.

### 29.3. Do Not Mask Errors With RETURN NULL

If `BEFORE INSERT` returns NULL, the row is skipped and constraints for that row are not evaluated the way they would be for a normal INSERT, since the row is never inserted. Never use `RETURN NULL` in place of a mandatory `CHECK`/validation whose failure the caller needs to know.

### 29.4. Triggers Are Not a UNIQUE Column

To keep emails or order codes unique, use a `UNIQUE` constraint/index, not a trigger:

~~~sql
-- Prone to race conditions if relying only on a trigger:
-- IF EXISTS(SELECT 1 FROM orders WHERE code = NEW.code) THEN
--     RAISE EXCEPTION ...;
-- END IF;
~~~

Two concurrent transactions can fail to see each other's uncommitted rows and create duplicates without proper unique constraints or locking. Triggers are a supporting layer, not a drop-in replacement for concurrency-safe constraints.

## 30. Triggers and Transactions: All DML Remains Rollbackable

Effects inside a trigger function are part of the statement/transaction containing the original DML; they do not run in an independent transaction.

### 30.1. Audit Rollback Example

~~~sql
BEGIN;

INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('Rollback Demo', 1000, 'new');

-- Within this transaction the new row and audit/trace are visible.

ROLLBACK;
~~~

After rollback, the new row and its corresponding audit and trace entries are gone. Allocated sequence/identity values, however, may still remain consumed.

### 30.2. BEFORE and AFTER Cannot Self-COMMIT

A PL/pgSQL trigger function is a **function**, not a top-level procedure invoked via `CALL`. You cannot place `COMMIT`/`ROLLBACK` inside a trigger function hoping audit records will survive transaction rollback.

Even if a trigger function calls a procedure containing `COMMIT`, the trigger function's call context does not become a top-level `CALL` eligible for transaction control. If you need logging independent of the main transaction, design external logging or streaming outside the transaction.

### 30.3. Exceptions Inside Triggers

~~~sql
RAISE EXCEPTION
    'order % cannot be updated', NEW.order_id;
~~~

Normally fails the statement. If the caller is inside an explicit transaction and does not catch the error in a suitable subtransaction context, the transaction enters an aborted state and requires `ROLLBACK`.

### 30.4. EXCEPTION Blocks Inside Triggers

PL/pgSQL supports `BEGIN ... EXCEPTION ... END` to handle recoverable errors. A block with an exception handler is backed by a subtransaction; SQL changes inside the failing portion of the block roll back. Use sparingly, and never silently swallow core errors and continue.

### 30.5. External Side Effects

Sending emails, calling payment APIs, or firing HTTP webhooks directly inside a trigger is not covered by PostgreSQL ACID rollback. If the transaction rolls back, the email/webhook may already have fired. Use a **transactional outbox** or an event pipeline designed for post-commit delivery with idempotency.

## 31. Trigger Recursion: When a Trigger Writes Back to Its Own Triggering Table

A common mistake:

~~~sql
-- Illustrating a structure that causes recursion:
CREATE FUNCTION public.bad_after_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.some_table
    SET updated_at = clock_timestamp()
    WHERE id = NEW.id;

    RETURN NULL;
END;
$$;
~~~

If this function is attached `AFTER UPDATE` on **`public.some_table`**, the inner UPDATE can fire the exact same trigger again:

~~~text
UPDATE row
  -> AFTER UPDATE trigger
      -> UPDATE same row
          -> AFTER UPDATE trigger
              -> UPDATE same row
                  -> ...
~~~

This can cause infinite loops, stack depth exceeded errors, lock contention, or heavy overhead.

### 31.1. The Natural Approach: BEFORE UPDATE Modifying NEW

~~~sql
CREATE FUNCTION public.set_timestamp_before()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

`BEFORE ROW` can modify `NEW` **without issuing another SQL UPDATE against the same table**, avoiding loops caused by an AFTER trigger updating its own row.

### 31.2. pg_trigger_depth()

PostgreSQL provides:

~~~sql
SELECT pg_trigger_depth();
~~~

This function returns the current nesting level of trigger executions. It is useful as a **diagnostic signal**, not as a design substitute for enforcing invariants. Writing `IF pg_trigger_depth() > 1 THEN RETURN NEW; END IF;` can mask legitimate work triggered by other triggers and depends heavily on call context.

### 31.3. Strategies to Avoid Recursion

- Choose `BEFORE ROW` to modify **the same row**.
- If `AFTER` must write to another table, ensure that table does not loop back to the original table.
- Keep trigger logic simple with clear separation of concerns.
- Only UPDATE when values actually change.
- Use `WHEN (OLD.x IS DISTINCT FROM NEW.x)` where appropriate.
- Design side-table events to be idempotent.
- Test nested DML, cascades, UPSERT, and concurrent transactions.

### 31.4. Recursion Is Not Limited to the Same Table

~~~text
orders AFTER UPDATE -> UPDATE customers
customers AFTER UPDATE -> UPDATE orders
orders AFTER UPDATE -> ...
~~~

This is **cross-table recursion**; draw the dependency graph and eliminate cyclic dependencies rather than patching with arbitrary depth thresholds.

## 32. Performance: Row-Level Triggers Can Create an N+1 Effect

Suppose an UPDATE modifies 100,000 rows and an `AFTER ROW` trigger executes one extra `SELECT` and one `INSERT` audit per row. The total internal statement count becomes massive.

### 32.1. Row vs. Statement

| Design | For 100,000 rows |
| --- | --- |
| `BEFORE ROW` normalizing a field | ~100,000 trigger function invocations |
| `AFTER ROW` auditing each row | ~100,000 invocations + audit inserts |
| `AFTER STATEMENT` without transition table | 1 invocation, but lacks the changed row set without another mechanism |
| `AFTER STATEMENT` + transition table | 1 invocation and can process all 100,000 rows with set-based SQL |

These figures are conceptual; with partitioning, foreign-key transition sets, or internal sub-statements, exact invocation counts can vary.

### 32.2. Prefer Set-Based Operations

If you only need **total row count or amount delta for the whole statement**, `AFTER STATEMENT` with a transition table cuts down SQL call count compared to `AFTER ROW`.

If you need **detailed per-row history**, row-level auditing still fits, though you can also consider a transition table followed by a set-based `INSERT INTO audit SELECT ... FROM changed_rows` where semantics permit.

### 32.3. In-Transaction Cost

Audit writes increase WAL volume, index updates, and lock footprints. If a trigger function touches multiple tables, a simple application UPDATE turns into a heavy transaction. When diagnosing slow statements, include trigger work rather than looking only at the main DML query plan.

### 32.4. Inspecting Trigger Timings in EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trg_lab_367.orders
SET note = 'performance demo'
WHERE status = 'new';
~~~

On most PostgreSQL versions, `EXPLAIN ANALYZE` displays trigger call counts and execution times alongside the UPDATE plan. **The command above actually updates data**; run it only on a lab database or wrap it in a transaction followed by ROLLBACK when impact is controlled.

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trg_lab_367.orders
SET note = 'temporary benchmark'
WHERE status = 'new';

ROLLBACK;
~~~

### 32.5. Do Not Assume ROLLBACK Has Zero Operational Impact

An `EXPLAIN ANALYZE` + ROLLBACK still consumes CPU, I/O, WAL, and locks while running, potentially impacting the live system. In production, use proper benchmarking plans instead of relying on rollback as total protection.

### 32.6. Check Indexes on the Audit Table

Audit tables can grow faster than main tables when every UPDATE writes a record. Design indexes tailored to history lookup queries, plan retention/partitioning, and enforce data access controls instead of indexing every JSONB column.

### 32.7. Never Make Per-Row Network Calls in Triggers

Even if the SQL DML takes only 100ms, a trigger making 100 sequential API requests turns the statement into a multi-second operation holding transaction locks while waiting on the network. Offload external processing to an outbox and independent worker.

## 33. Trigger Function Security: INVOKER, DEFINER, and search_path

Trigger functions normally execute with the **caller's** privileges (`SECURITY INVOKER` by default). In certain designs, a trigger function is defined with `SECURITY DEFINER` so it can write to an audit table that the application role is not allowed to INSERT into directly.

### 33.1. Risks of SECURITY DEFINER

A function running with owner privileges can be exploited if it:

- Uses unqualified table/function names in schemas where an attacker can create objects;
- Uses dynamic SQL concatenating unquoted or unbound input;
- Has an overly privileged owner;
- Allows untrusted roles to alter the trigger function;
- Grants `EXECUTE` on the function more broadly than intended.

### 33.2. Reference Pattern

~~~sql
CREATE FUNCTION trg_lab_367.secure_audit_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trg_lab_367, pg_temp
AS $$
DECLARE
    v_order_id bigint;
    v_old jsonb;
    v_new jsonb;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;
        v_old := NULL;
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        v_order_id := NEW.order_id;
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;
        v_old := to_jsonb(OLD);
        v_new := NULL;
    ELSE
        RAISE EXCEPTION 'Unsupported trigger operation %', TG_OP;
    END IF;

    INSERT INTO trg_lab_367.order_audit(
        order_id, action, old_data, new_data
    )
    VALUES (
        v_order_id, TG_OP, v_old, v_new
    );

    RETURN NULL;
END;
$$;
~~~

This is an **illustrative example of privileges and search_path**, not advice to convert every audit trigger to `SECURITY DEFINER` automatically. Branching on `TG_OP` avoids accessing `NEW` fields during DELETE or `OLD` fields during INSERT. Before using this in production, audit the owner role, `GRANT EXECUTE`, audit read permissions, and recursion potential; install it only if that privilege model is genuinely required.

### 33.3. Do Not Turn Triggers Into a Privilege-Escalation Path

A role permitted to UPDATE the main table without permission to view sensitive fields must not be able to use triggers or views to leak another user's data. Review Row-Level Security, view privileges, ownership, `SECURITY DEFINER`, and audit read access.

### 33.4. Trigger Arguments Are Not Unconditionally Trusted

`TG_ARGV[]` holds configuration strings set when the trigger was created. Anyone authorized to alter triggers can change those arguments and alter trigger behavior. Separate migration/owner privileges from business data submitted by clients in row columns.

### 33.5. Do Not Habitually Disable Triggers to Patch Data

~~~sql
-- Dangerous command if applied without control:
-- ALTER TABLE trg_lab_367.orders DISABLE TRIGGER USER;
~~~

Disabling user triggers skips normalization, auditing, and validation logic. `DISABLE TRIGGER ALL` and commands affecting system constraint triggers have even broader impact, may require elevated privileges, and can break integrity if misused.

Any trigger state change requires migration/owner governance, maintenance windows, data verification, and proper re-enabling; never use it as a "shortcut" to bypass confusing triggers.

## 34. Trigger Governance and Migration Lifecycle

Trigger definitions are bound to relations. When deploying changes:

1. Design trigger functions with clear versioning and contracts.
2. Check dependencies if multiple triggers invoke the same function.
3. Remember `CREATE OR REPLACE FUNCTION` changes the logic of **every trigger pointing to that function**.
4. Use versioned migrations and verify schema qualification/`search_path`.
5. Test INSERT/UPDATE/DELETE/ROLLBACK/cascades in a lab environment.
6. Measure bulk DML cost and concurrency behavior.
7. Have a rollback or fix-forward plan.

### 34.1. Renaming a Trigger Can Change Execution Order

Because triggers of the same kind run alphabetically, renaming a trigger can change behavior when triggers interact via `NEW`. Never treat renaming as purely cosmetic if business logic depends on order.

### 34.2. DROP TRIGGER Does Not Drop the Function

~~~sql
DROP TRIGGER IF EXISTS trg_10_normalize_order
ON trg_lab_367.orders;
~~~

This removes the trigger from the table; it **does not automatically drop the trigger function** `trg_lab_367.normalize_order_before()` without a separate statement. In the current lab, do not run this command if you still want to observe normalization behavior in later steps.

### 34.3. CREATE OR REPLACE FUNCTION

~~~sql
CREATE OR REPLACE FUNCTION trg_lab_367.some_trigger_function()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN NEW;
END;
$$;
~~~

This illustrates updating a function body; in production, inspect signature, volatility/security/`search_path`, dependencies, and transaction timing. Never modify a shared function used by multiple triggers without assessing the blast radius.

### 34.4. Checking Trigger Enabled Mode

~~~sql
SELECT
    t.tgname,
    t.tgenabled,
    t.tgisinternal,
    c.relname AS relation_name,
    n.nspname AS schema_name,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'trg_lab_367'
ORDER BY c.relname, t.tgname;
~~~

`tgenabled` has multiple states tied to replication roles, not just a simple boolean. When a trigger appears "enabled" in metadata yet does not fire, check the session replication mode and the DML origin per operational rules.

### 34.5. Do Not Arbitrarily Alter session_replication_role

`session_replication_role` affects trigger and rule firing, including triggers enforcing referential integrity; changing it can leave data unconstrained. Never use this switch as a quick bulk-loading trick in production without strict design and privilege controls.

## 35. Inspecting Live Triggers: Metadata Queries

The SQL queries below are primarily **read-only metadata inspections** to identify which triggers are attached to a relation and which functions they call. Do not execute `ALTER TABLE DISABLE TRIGGER` or `DROP TRIGGER` before understanding dependencies.

### 35.1. Listing Triggers and Functions

~~~sql
SELECT
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_mode,
    p.oid::regprocedure AS function_signature,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc AS p
    ON p.oid = t.tgfoid
WHERE n.nspname = 'trg_lab_367'
ORDER BY n.nspname, c.relname, t.tgname;
~~~

### 35.2. User-Defined Triggers Only

~~~sql
SELECT
    t.tgname,
    pg_catalog.pg_get_triggerdef(t.oid)
FROM pg_catalog.pg_trigger AS t
WHERE t.tgrelid = 'trg_lab_367.orders'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

On tables with foreign keys, system/internal triggers enforce referential integrity; do not confuse them with application-authored business triggers.

### 35.3. information_schema.triggers

~~~sql
SELECT
    trigger_schema,
    trigger_name,
    event_manipulation,
    event_object_schema,
    event_object_table,
    action_timing,
    action_orientation
FROM information_schema.triggers
WHERE event_object_schema = 'trg_lab_367'
ORDER BY event_object_table, trigger_name;
~~~

`information_schema` provides a portable view of trigger metadata, though PostgreSQL-specific details such as enabled mode, constraint deferral, internal triggers, and transition relation definitions require `pg_catalog` and `pg_get_triggerdef`.

### 35.4. Inspecting Function Definitions

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.prosecdef AS security_definer,
    p.proconfig,
    pg_catalog.pg_get_functiondef(p.oid) AS function_definition
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'trg_lab_367'::regnamespace
  AND p.prorettype = 'pg_catalog.trigger'::regtype
ORDER BY p.oid::regprocedure::text;
~~~

Pay special attention to `SECURITY DEFINER` functions, writes to auxiliary tables, dynamic SQL, `RAISE EXCEPTION`, and `TG_OP` branches.

### 35.5. Inspecting Traces and Audits

~~~sql
SELECT
    event_name,
    timing,
    trigger_level,
    COUNT(*) AS invocations_recorded
FROM trg_lab_367.trigger_trace
GROUP BY event_name, timing, trigger_level
ORDER BY event_name, timing, trigger_level;
~~~

Trace counts reflect only the lab triggers that log to the trace table. They do **not** count every trigger invocation if a function does not log, when statements roll back, or when other commands write to the trace table.

## 36. Trigger Troubleshooting Runbook

### Phase A — Identify Event and Timing

Gather:

1. Was the original DML `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `COPY`, `MERGE`, or UPSERT?
2. How many rows did the statement affect?
3. Which row-level and statement-level triggers are attached to the relation?
4. Are there BEFORE, AFTER, INSTEAD OF, or deferred constraint triggers?
5. Are views, partitions, or foreign-key cascades involved?
6. Which transaction is the session in, and has it committed or rolled back?

### Phase B — Diagnose Anomalous Behavior

| Symptom | Diagnostic question |
| --- | --- |
| INSERT returns 0 rows despite sending a row | Is there a `BEFORE INSERT ROW RETURN NULL` or `INSTEAD OF ... RETURN NULL`? |
| UPDATE writes the wrong column value | Are multiple BEFORE UPDATE triggers modifying `NEW` in alphabetical order? |
| Modifying `NEW` in AFTER UPDATE has no effect | Is the function using `RETURN NEW` expecting to alter the row after UPDATE? |
| Statement log appears when 0 rows were affected | Statement-level triggers still run on 0 rows |
| Same-value UPDATE still creates an audit record | `UPDATE OF` only checks the SET list; missing `WHEN IS DISTINCT FROM` |
| View INSERT does not write to the base table | Does the INSTEAD OF trigger execute an actual INSERT? |
| View RETURNING emits 0 rows | Is the INSTEAD OF trigger returning NULL instead of the processed row? |
| Audit records are occasionally missing | Transaction rollback? Trigger disabled? Wrong firing event? |
| More audit records than expected | FK cascades, UPSERT, MERGE, triggers on multiple relations? |
| Expecting trigger to run after commit? | Regular AFTER triggers run inside the transaction, not post-commit |
| Deleting a paid order raises an error | BEFORE DELETE guard or constraint is blocking it |
| TRUNCATE bypasses DELETE audit | No row-level TRUNCATE triggers exist |
| Partition-key UPDATE skips AFTER UPDATE ROW | Row movement turns into DELETE+INSERT |
| High latency/CPU during bulk updates | N+1 SQL inside row triggers or recursion |
| Stack depth exceeded | Trigger updating the same table or cross-table cycle? |
| Constraint fails only at COMMIT | Deferred constraint trigger or deferred FK? |
| Trigger not firing in replication flow | Enabled mode / `session_replication_role`? |

### Phase C — Reproduce Safely

In a lab schema or representative test environment:

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET note = 'test run'
WHERE order_id = 1;

SELECT *
FROM trg_lab_367.trigger_trace
ORDER BY trace_id DESC
LIMIT 10;

SELECT *
FROM trg_lab_367.order_audit
ORDER BY audit_id DESC
LIMIT 10;

ROLLBACK;
~~~

This test lets you inspect trigger writes **within the current transaction** and roll back lab changes. Note: it still incurs I/O, WAL, and locking overhead during execution; it is not a zero-impact operation.

### Phase D — Diagnose Performance

Run `EXPLAIN (ANALYZE, BUFFERS)` on the lab DML or a non-production benchmark, inspecting:

- Main table operation plan;
- Trigger execution times and call counts where displayed;
- Buffer hits/reads and WAL activity via available metrics;
- Row counts and lock waits;
- Auxiliary queries executed inside triggers;
- Growth rate of audit/side tables.

`EXPLAIN ANALYZE` **actually executes the DML**. Never run it in production assuming it only prints a plan.

### Phase E — Propose Minimal Fix

- To modify the current row: use `BEFORE ROW RETURN NEW`, not an AFTER self-UPDATE.
- For auditing: `AFTER ROW` or AFTER statement + transition tables.
- For summary tables: prefer set-based SQL, avoid N+1 queries.
- For DML through views: check auto-updatability vs. INSTEAD OF.
- For invariants: prefer constraints when sufficient; use deferred constraint triggers only when genuinely required.
- For external notifications: use an outbox, never network calls inside triggers.
- To detect real value changes: use `IS DISTINCT FROM`.
- With multiple triggers: inspect alphabetical ordering and consider merging coupled logic.

### Phase F — Deploy With Monitoring

Document trigger ownership, before/after SQL function definitions, migration version, rollback plan, data backfills, latency/lock metrics, and privilege policies. Never disable triggers to fix a performance issue without assessing integrity risks.

## 37. Rules for Choosing the Right Trigger Type

| Requirement | Preferred choice | Why |
| --- | --- | --- |
| Trim customer name before INSERT | `BEFORE INSERT FOR EACH ROW` | Modifies `NEW` right before storage |
| Update row `updated_at` | `BEFORE UPDATE FOR EACH ROW` | Avoids self-UPDATE in AFTER |
| Reject DELETE of paid orders | `BEFORE DELETE FOR EACH ROW` + exception | Explicitly blocks forbidden changes |
| Audit OLD/NEW after UPDATE | `AFTER UPDATE FOR EACH ROW` | Sees the row after BEFORE changes |
| Summarize 10,000 inserted rows per statement | `AFTER INSERT FOR EACH STATEMENT REFERENCING NEW TABLE` | Processes the entire inserted set |
| Record statement events even for 0 rows | `BEFORE/AFTER ... FOR EACH STATEMENT` | Fires per statement |
| Write through join/computed view | `INSTEAD OF ... FOR EACH ROW` | Custom DML mapping to base tables |
| Block TRUNCATE | `BEFORE TRUNCATE FOR EACH STATEMENT` or TRUNCATE privileges | No row-level TRUNCATE exists |
| Cross-row constraint checked at transaction end | Deferred `AFTER ROW CONSTRAINT TRIGGER` | Can be deferred when declared |
| Unique customer code | `UNIQUE` constraint | Built-in concurrency protection |
| Simple column/type validation | `CHECK`/`NOT NULL` | Transparent and predictable |
| Referential FK | `FOREIGN KEY` | Avoid hand-rolled race-prone triggers |
| Send email after DB write succeeds | Outbox + post-commit worker | Avoids external API calls in triggers |

### 37.1. Choose Level Based on Logic Scope

If logic inspects or alters **a single row**, choose row-level. If logic computes **statement-wide totals**, choose statement-level with transition tables when supported. Never use statement-level and try to read `NEW.amount` as a single row; conversely, never use row-level to re-run a full-table aggregate for every row.

### 37.2. Choose Timing Based on Purpose

**BEFORE** is for row preprocessing and blocking. **AFTER** is for post-change recording and row sets. **INSTEAD OF** is for view DML mapping. These are useful design principles, though every business requirement must also account for transactions, constraints, security, and performance.

### 37.3. When Not to Use Triggers

- Logic is hard to debug and spans many tables and external services;
- The API needs clearer return/error flows than implicit side effects;
- Constraints, generated columns, or defaults can express it directly;
- Triggers introduce cyclic dependencies;
- Bulk DML incurs unacceptable latency;
- Multiple teams change schemas without trigger migration/testing discipline.

In such cases, explicit functions/procedures, the service layer, an outbox, constraints, or data pipelines are easier to govern.

## 38. Practice Exercises — Fundamentals and Execution Timing

Exercises use the `trg_lab_367` schema and triggers created in this lesson. Since several examples modify data, **actual row counts depend on the order in which you ran commands**; when needed, insert fresh lab data with distinct keys/names rather than assuming `order_id` equals a specific number. Never run error-inducing examples, DROP, or TRUNCATE in production.

### Exercise 1 — Identifying the Three Timings

An orders table needs: (a) name normalization before saving; (b) audit logging after modification; (c) updates through a view containing a computed column.

**Question:** choose `BEFORE`, `AFTER`, or `INSTEAD OF` for each need?

**Sample answer:** (a) BEFORE ROW; (b) AFTER ROW or AFTER STATEMENT + transition table depending on granularity; (c) INSTEAD OF ROW on the view.

### Exercise 2 — Timing vs. Level

Analyze four triggers:

~~~sql
BEFORE UPDATE FOR EACH ROW
BEFORE UPDATE FOR EACH STATEMENT
AFTER UPDATE FOR EACH ROW
AFTER UPDATE FOR EACH STATEMENT
~~~

**Question:** for an UPDATE affecting exactly 5 rows, how many times does each trigger normally fire?

**Answer:** 5, 1, 5, 1 in the simple case with no skipped rows or special mechanisms.

### Exercise 3 — Statement Affecting 0 Rows

~~~sql
UPDATE trg_lab_367.orders
SET note = 'nothing'
WHERE order_id = -999999;
~~~

**Question:** do statement-level triggers still run? How many times do row-level triggers run?

**Answer:** statement-level BEFORE/AFTER still run; row-level runs 0 times.

### Exercise 4 — Predicting TG_OP

A trigger function is attached with `AFTER INSERT OR UPDATE OR DELETE`.

**Question:** what strings can `TG_OP` hold? Can it be `'AFTER'`?

**Answer:** `'INSERT'`, `'UPDATE'`, `'DELETE'`; the timing `'AFTER'` is in `TG_WHEN`.

### Exercise 5 — NEW and OLD

Complete the table:

| DML | Has NEW row? | Has OLD row? |
| --- | --- | --- |
| INSERT | ? | ? |
| UPDATE | ? | ? |
| DELETE | ? | ? |

**Answer:** INSERT has NEW; UPDATE has both; DELETE has OLD.

### Exercise 6 — TG_LEVEL

What is `TG_LEVEL` for an `AFTER UPDATE ... FOR EACH STATEMENT` trigger? Does the function's return value determine whether the UPDATE runs?

**Answer:** `STATEMENT`; the return value is ignored.

### Exercise 7 — BEFORE INSERT Normalization

Run:

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('  Thảo  ', 45000, 'new')
RETURNING customer_name;
~~~

**Question:** what value is stored and displayed by `RETURNING`?

**Answer:** `Thảo`, because the `BEFORE INSERT ROW` trigger modifies `NEW` and returns `NEW`.

### Exercise 8 — Blank Name

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('   ', 1000, 'new');
~~~

**Question:** should the normalization trigger silently return NULL or `RAISE EXCEPTION`? Impact on the caller?

**Sample answer:** the lab raises an exception so the caller knows the input is invalid; the statement does not commit the row.

### Exercise 9 — Returning NULL in BEFORE INSERT

~~~sql
INSERT INTO trg_lab_367.import_queue(source_value)
VALUES ('valid'), ('   ');
~~~

**Question:** how many new rows are in the table when the second input hits `BEFORE ROW RETURN NULL`?

**Answer:** one row (`valid`); the blank value is skipped.

### Exercise 10 — RETURN NULL at Statement Level

A `BEFORE UPDATE FOR EACH STATEMENT` trigger function always executes `RETURN NULL`.

**Question:** does it cause PostgreSQL to skip the entire UPDATE?

**Answer:** no, the return value of a statement-level trigger is ignored.

### Exercise 11 — RETURN NULL in AFTER ROW

The `audit_order_after()` function returns NULL. Why is the original row still inserted/updated/deleted?

**Answer:** AFTER trigger return values are ignored; the row operation has already occurred under trigger semantics.

### Exercise 12 — Modifying NEW in AFTER ROW

A developer assigns `NEW.amount := 0` and `RETURN NEW` inside `AFTER UPDATE` to discount an order.

**Question:** does the row's stored amount actually change?

**Answer:** not that way. You must use BEFORE UPDATE to modify `NEW`, or a separate controlled SQL UPDATE avoiding recursion if truly needed.

### Exercise 13 — DELETE on a Paid Order

After transitioning an order to `paid`, try deleting it.

**Question:** which trigger blocks the operation? Why is `RAISE EXCEPTION` usually clearer than `RETURN NULL` when business logic forbids deletion?

### Exercise 14 — Does AFTER Mean After COMMIT?

~~~sql
BEGIN;
UPDATE trg_lab_367.orders
SET note = 'temporary'
WHERE order_id = 1;
ROLLBACK;
~~~

**Question:** do the newly created audit/trace entries survive after rollback?

**Answer:** no, if they belong to the same transaction and have no external side effects.

### Exercise 15 — Reading OLD/NEW of an UPDATE

Write a query reading `order_audit` for `UPDATE` actions, extracting:

~~~sql
old_data ->> 'customer_name'
new_data ->> 'customer_name'
~~~

**Question:** did the AFTER trigger read the name before or after BEFORE normalization?

### Exercise 16 — CHECK and BEFORE Triggers

INSERT an order with `amount=-100`, `customer_name=' Valid '`.

**Question:** even though the BEFORE trigger normalizes the name, what does the CHECK constraint do to the transaction?

**Answer:** rejects the invalid row; none of the statement's changes are committed.

### Exercise 17 — UPDATE OF amount

~~~sql
UPDATE trg_lab_367.orders
SET amount = amount
WHERE order_id = 1;
~~~

**Question:** is the `UPDATE OF amount` trigger considered? With `WHEN OLD.amount IS DISTINCT FROM NEW.amount`, does the amount logging function execute?

**Answer:** the target column is specified; WHEN evaluates to false when the value is unchanged, so the function does not run.

### Exercise 18 — IS DISTINCT FROM

Explain the difference:

~~~sql
OLD.note <> NEW.note
OLD.note IS DISTINCT FROM NEW.note
~~~

**Question:** if one side is `NULL`, which produces a clear boolean?

### Exercise 19 — BEFORE Trigger Modifying a Column Omitted From UPDATE SET

A SQL statement runs `UPDATE orders SET note='x'`, yet a BEFORE trigger modifies `NEW.amount`.

**Question:** does `AFTER UPDATE OF amount` automatically detect that amount changed?

**Answer:** not necessarily; `UPDATE OF` checks the SQL target list. Use `AFTER UPDATE ... WHEN OLD.amount IS DISTINCT FROM NEW.amount` when you must catch every actual change.

### Exercise 20 — WHEN on INSTEAD OF

A developer tries to write `INSTEAD OF INSERT ON view ... WHEN (...)`.

**Question:** does PostgreSQL support WHEN on INSTEAD OF triggers? Where should the condition go?

**Answer:** no; put an `IF` inside the trigger function.

### Exercise 21 — Multiple Triggers of the Same Type

Two BEFORE UPDATE triggers named `trg_b_trim` and `trg_a_uppercase` both modify `NEW.customer_name`.

**Question:** which trigger runs first and why does that order matter?

**Answer:** triggers of the same kind run alphabetically by name; `trg_a_uppercase` runs before `trg_b_trim`.

### Exercise 22 — WHEN in AFTER ROW

Add trigger `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status)`.

**Question:** does it need to invoke the function for rows whose status did not change? Why does WHEN reduce overhead?

### Exercise 23 — Row-Level Audit vs. Statement Aggregate

A statement inserts 10,000 rows and requires both per-row auditing and a statement total of `amount`.

**Exercise:** choose trigger timing/level for both requirements and explain the benefit of transition tables.

### Exercise 24 — NEW TABLE

Create `AFTER INSERT ... REFERENCING NEW TABLE AS inserted_rows`, using:

~~~sql
SELECT COUNT(*), SUM(amount) FROM inserted_rows;
~~~

**Question:** does `inserted_rows` hold the entire table or only the statement's rows?

**Answer:** only the new rows from the current INSERT event.

### Exercise 25 — INSERT of 0 Rows

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
SELECT 'Nobody', 0, 'new'
WHERE FALSE;
~~~

**Question:** does the AFTER STATEMENT trigger still run? How many rows are in the transition `NEW TABLE`?

**Answer:** the trigger runs, and the transition relation is empty.

### Exercise 26 — OLD TABLE and NEW TABLE for UPDATE

Write an `AFTER UPDATE FOR EACH STATEMENT` trigger with:

~~~sql
REFERENCING OLD TABLE AS old_orders
            NEW TABLE AS new_orders
~~~

**Exercise:** compute total `new.amount - old.amount` joined on the primary key in the lab; when can joining on the primary key fail if the key itself is updated?

### Exercise 27 — UPDATE OF Combined With Transition Relations

**Question:** why does PostgreSQL forbid `AFTER UPDATE OF amount ... REFERENCING ...`?

**Hint:** use `AFTER UPDATE` without a column list, then compare old/new sets inside the function.

### Exercise 28 — NEW Inside a Statement Trigger

Inside `AFTER UPDATE FOR EACH STATEMENT`, a developer writes `NEW.amount`.

**Question:** why is there no single representative NEW row? What should be used instead to inspect all updated rows?

### Exercise 29 — INSTEAD OF INSERT

~~~sql
INSERT INTO trg_lab_367.v_order_editor(
    customer_name, amount, status
)
VALUES ('  My  ', 10000, 'new')
RETURNING order_id, customer_name, gross_estimate;
~~~

**Question:** which operation actually inserts into the base table? Why can `RETURNING` show the normalized `customer_name`?

### Exercise 30 — INSTEAD OF DELETE and OLD

Write the `TG_OP='DELETE'` branch deleting the base row by `OLD.order_id` and returning `OLD` when handled.

**Question:** how does `RETURN NULL` affect the view's row count and `RETURNING`?

### Exercise 31 — Automatically Updatable Views

Create a view selecting columns from a single table without joins, aggregates, or complex expressions.

**Question:** is an INSTEAD OF trigger always needed? State the conditions for a simple view to be auto-updatable and when `WITH CHECK OPTION` is meaningful.

### Exercise 32 — View With a Computed Column

View `v_order_editor` has `gross_estimate = amount * 1.05`.

**Question:** why must the view trigger recompute `gross_estimate` when returning for `RETURNING`? Why should clients not treat it as an independently updatable field?

### Exercise 33 — Base-Table AFTER ROW When Writing Through a View

Call `INSERT INTO trg_lab_367.v_order_editor(...)`.

**Exercise:** trace the chain `INSTEAD OF INSERT ROW on view -> INSERT orders -> BEFORE INSERT ROW -> AFTER INSERT ROW`. Which audit records are written to which tables?

### Exercise 34 — Deferred Constraint Trigger

Create a constraint trigger `AFTER INSERT OR UPDATE DEFERRABLE INITIALLY DEFERRED`.

**Question:** when can it execute? How does it differ from a regular AFTER ROW trigger?

### Exercise 35 — WHEN on a Constraint Trigger

An UPDATE inside a transaction temporarily turns an order into `paid` with `amount=0`, then a subsequent UPDATE sets `amount=50000`.

**Question:** when is `WHEN (NEW.status='paid')` evaluated? Why should the deferred trigger function read the **final state** instead of checking only the previously captured NEW snapshot?

### Exercise 36 — SET CONSTRAINTS

Inside a transaction:

~~~sql
SET CONSTRAINTS trg_paid_amount_deferred IMMEDIATE;
~~~

**Question:** how does this affect pending constraint-trigger events? Does it convert regular AFTER ROW triggers into deferred/immediate constraint triggers?

### Exercise 37 — TRUNCATE

Attach a `BEFORE DELETE ROW` audit trigger to `temp_items` and run `TRUNCATE`.

**Question:** does the DELETE ROW trigger fire? Which triggers can fire on TRUNCATE?

**Answer:** DELETE ROW does not run; `BEFORE/AFTER TRUNCATE FOR EACH STATEMENT`.

### Exercise 38 — TRUNCATE Rollback

~~~sql
BEGIN;
TRUNCATE trg_lab_367.temp_items;
ROLLBACK;
~~~

**Question:** are the rows restored? Do records written by a TRUNCATE trigger inside the transaction survive rollback?

### Exercise 39 — UPSERT on Conflict

A table has `BEFORE INSERT` normalizing `NEW.name` and `BEFORE UPDATE` assigning `NEW.updated_at`.

**Question:** when `INSERT ... ON CONFLICT DO UPDATE` hits a conflict, why can both BEFORE ROW trigger types participate? What happens to `EXCLUDED` values?

### Exercise 40 — Statement Triggers in UPSERT

A statement uses `ON CONFLICT DO UPDATE`, yet no conflict actually occurs.

**Question:** can the statement-level UPDATE trigger still fire? Why does a statement-level trigger firing not imply at least one row changed?

### Exercise 41 — ON CONFLICT DO NOTHING

A `BEFORE INSERT ROW` trigger stamps a timestamp, then the INSERT hits a unique conflict and takes `DO NOTHING`.

**Question:** could `BEFORE INSERT ROW` have run? Does `AFTER INSERT ROW` apply to the skipped row?

### Exercise 42 — MERGE

A `MERGE` has both INSERT and UPDATE branches.

**Exercise:** distinguish statement-level events evaluated from actual row-level events, and explain why there is no `TG_OP='MERGE'` trigger operation.

### Exercise 43 — FK ON DELETE CASCADE

A parent has a child FK with `ON DELETE CASCADE`. The child table has an `AFTER DELETE ROW` audit trigger.

**Question:** when deleting the parent deletes children, can the child's audit trigger run? Is it in a different transaction?

### Exercise 44 — Partition Movement

An UPDATE on a partition key moves a row from January's partition to February's partition.

**Exercise:** explain why `AFTER UPDATE ROW` may not run for row movement, whereas `AFTER DELETE ROW` and `AFTER INSERT ROW` on the partitions can run.

### Exercise 45 — Generated Column

`line_total GENERATED ALWAYS AS (quantity * unit_price) STORED`.

**Question:** can a BEFORE trigger modify `quantity` before the generated value is computed? Which `line_total` does the AFTER trigger see?

### Exercise 46 — Trigger Recursion

An AFTER UPDATE trigger executes `UPDATE orders SET updated_at=... WHERE order_id=NEW.order_id`.

**Exercise:** draw the loop and fix it with `BEFORE UPDATE ... NEW.updated_at := clock_timestamp(); RETURN NEW;`.

### Exercise 47 — Slow Bulk UPDATE

An `UPDATE` changes 200,000 rows; an AFTER ROW trigger executes three extra SQL queries per row.

**Exercise:** estimate the number of trigger invocations, describe the N+1 overhead, and propose a set-based transition table if business only needs aggregates.

### Exercise 48 — SECURITY DEFINER

An audit trigger function needs to write to a separate table where the application lacks INSERT privileges.

**Question:** when using `SECURITY DEFINER`, how must you control owner, `search_path`, dynamic SQL, and `EXECUTE` privileges?

### Exercise 49 — EXPLAIN ANALYZE on DML

A developer runs `EXPLAIN (ANALYZE) DELETE FROM orders` in production thinking it only prints the plan.

**Question:** what is the risk? Why does wrapping in a transaction and rolling back in a lab still consume locks/WAL?

### Exercise 50 — Capstone: Sales Workflow

Design a schema comprising:

- Table `orders` with amount, status, customer_name, and updated_at.
- Admin view with a calculated display total column.
- Audit table storing OLD/NEW for all INSERT/UPDATE/DELETE operations.
- Per-statement report of new order count and total amount.
- Disallow deleting paid orders.
- Allow bulk COPY imports without silently dropping invalid input.
- Clear transaction commit/rollback semantics.
- External post-commit notification mechanism via an outbox.

**Deliverables:**

1. Choose `BEFORE`/`AFTER`/`INSTEAD OF` and row/statement level for each operation.
2. Write at least three PL/pgSQL trigger functions and corresponding `CREATE TRIGGER` statements.
3. Explain `NEW`/`OLD` and return values in each function.
4. Use `WHEN`/`IS DISTINCT FROM` for a field audited only when changed.
5. Use a transition relation for per-statement totals.
6. Describe the view's `RETURNING` contract.
7. Write an `UPDATE ... WHERE FALSE` test proving statement triggers still run.
8. Write a `BEGIN; DML; ROLLBACK;` test proving AFTER audit rolls back.
9. Verify UPSERT, DELETE cascade, and partition row movement if applicable in the target model.
10. Identify at least three performance risks, two security risks, and one migration rollback plan.

**Self-explanation criteria:** Learners must explain **when a trigger runs, which data it sees, what returning NEW/OLD/NULL means, and whether trigger actions commit independently**. Do not merely recite `CREATE TRIGGER` syntax.

## 39. Trigger Design and Implementation Checklist

### 39.1. Semantics

- [ ] Identified the event: `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE`.
- [ ] Selected timing `BEFORE`/`AFTER`/`INSTEAD OF` matching the purpose.
- [ ] Selected level `ROW`/`STATEMENT` matching the granularity.
- [ ] Did not create row-level TRUNCATE triggers.
- [ ] Did not create INSTEAD OF triggers on base tables or statement-level triggers with row assumptions on views.
- [ ] Did not access `NEW` on DELETE or `OLD` on INSERT.
- [ ] Row-level BEFORE returns `NEW`/`OLD` for the event or `NULL` only when intentionally skipping.
- [ ] AFTER/statement-level triggers do not use return values to alter or skip DML.
- [ ] INSTEAD OF triggers execute real base-table SQL and return an appropriate row for affected rows/`RETURNING`.
- [ ] Do not treat AFTER as "after COMMIT."
- [ ] Do not treat statement trigger execution as proof that at least one row changed.

### 39.2. Correctness

- [ ] Constraints exist for simple invariants instead of overusing triggers.
- [ ] `CHECK`/`UNIQUE`/`FOREIGN KEY` are placed where appropriate.
- [ ] Distinguished `UPDATE OF` target lists from actual value changes.
- [ ] Used `IS DISTINCT FROM` for comparing nullable fields.
- [ ] Checked alphabetical ordering across multiple triggers of the same kind.
- [ ] Tested interactions across multiple BEFORE triggers.
- [ ] Accounted for evaluation timing when generated columns exist.
- [ ] Accounted for when `WHEN` is evaluated on deferred constraint triggers.
- [ ] Did not confuse subtransactions/AFTER triggers with independent transactions.
- [ ] Included rollback and exception-handling tests.

### 39.3. Views and Complex Operations

- [ ] Checked whether the view is auto-updatable before adding INSTEAD OF.
- [ ] Defined clear mapping between view rows and base-table DML.
- [ ] Tested `INSERT/UPDATE/DELETE ... RETURNING` through the view.
- [ ] Remembered base-table triggers still run on DML issued inside view triggers.
- [ ] Tested UPSERT and associated statement-level behavior.
- [ ] Verified TRUNCATE does not fire DELETE row triggers.
- [ ] Tested FK cascades with child-table auditing.
- [ ] Tested partition row movement when partitioning is used.
- [ ] Tested COPY and bulk imports.

### 39.4. Performance and Operations

- [ ] Avoided unnecessary N+1 queries inside row triggers.
- [ ] Used transition tables/set-based logic for statement-level summaries when possible.
- [ ] Made no network/external API calls inside trigger transactions.
- [ ] Added guards against trigger recursion and cross-table cycles.
- [ ] Benchmarked with representative data/row counts and inspected EXPLAIN if needed.
- [ ] Monitored locks, WAL, latency, and audit-table growth.
- [ ] Planned retention/partitioning for large audit tables.
- [ ] Never disabled user or system triggers without proper governance.
- [ ] Prepared migration and rollback plans.
- [ ] Did not treat sequence gaps as proof of rollbacks or missing audits.

### 39.5. Security

- [ ] Used schema-qualified names inside trigger functions.
- [ ] If using SECURITY DEFINER, configured safe `search_path` and least-privilege owner.
- [ ] Never concatenated untrusted data into dynamic SQL without proper quoting/binding.
- [ ] Restricted `EXECUTE` privileges on functions, table/trigger permissions, and audit read access.
- [ ] Established masking/retention policies for sensitive data in OLD/NEW snapshots.
- [ ] Verified Row-Level Security/views/roles in multi-tenant systems.
- [ ] Did not rely on triggers as the sole authentication or authorization mechanism.

## 40. Frequently Asked Questions

### 40.1. Does BEFORE always run before every constraint?

`BEFORE ROW` runs before the row change is applied and can typically adjust `NEW` before final values are checked/stored. However, constraints have their own immediate/deferred phases and internal triggers. To guarantee simple invariants, use constraints rather than relying on the ordering of a complex trigger chain.

### 40.2. Why can't AFTER modify NEW?

PostgreSQL ignores the **return value** of an `AFTER ROW` trigger; the row has already been processed. To modify the row being written, `BEFORE ROW` is the right phase. AFTER can execute auxiliary SQL, yet doing so against the same table easily causes recursion.

### 40.3. Why does deleting 0 rows still write a trace?

Because statement-level triggers are invoked once per SQL statement without requiring a matching row. Row-level DELETE triggers have no rows and do not run.

### 40.4. Can INSTEAD OF be attached to a table?

No. PostgreSQL defines `INSTEAD OF` for **row-level triggers on views**. On tables, use BEFORE/AFTER for supported events and levels.

### 40.5. Can I make a join view editable using an INSTEAD OF trigger?

Yes, provided you build a clear DML mapping down to the base tables. You must handle row identity, concurrency, permissions, constraints, `RETURNING`, and partial failures; there is no default mapping valid for all joins.

### 40.6. When an AFTER trigger writes an audit row and the transaction rolls back, does the audit survive?

No, if the audit INSERT belongs to the same transaction. To record rolled-back or failed attempts, build an appropriately designed **out-of-transaction** logging/audit system.

### 40.7. How do I tell if amount actually changed?

In row-level UPDATE:

~~~sql
OLD.amount IS DISTINCT FROM NEW.amount
~~~

rather than relying only on `UPDATE OF amount`, since a column listed in SET may retain the exact same value.

### 40.8. Can RETURN NULL block a DELETE?

Yes, from `BEFORE DELETE ROW`. However, if business rules require an error when attempting to delete a paid order, `RAISE EXCEPTION` is much clearer than silently skipping.

### 40.9. Why does a trigger run multiple times for a single INSERT statement?

Because row-level triggers fire per **affected row**, not per statement. In addition, UPSERT, FK cascades, view triggers issuing base-table DML, or partitioning can produce additional trigger events.

### 40.10. Can AFTER STATEMENT access all newly inserted rows?

Yes, using **`REFERENCING NEW TABLE AS ...`** when trigger, event, and relation meet support requirements. Without a transition table, a statement trigger has no `NEW` variable holding the row set.

### 40.11. Can a deferred constraint trigger run after COMMIT?

It can be **deferred until the transaction-completion phase**, before the transaction is accepted as committed. Do not think of it as an asynchronous callback running outside the transaction after commit has finished.

### 40.12. Why do triggers get slower on large tables?

Row-level functions may issue N+1 SQL calls, audit tables may grow rapidly, or there may be heavy indexing/WAL overhead, recursion, lock waits, or unindexed auxiliary queries. Inspect with EXPLAIN/metrics and consider transition tables or refactoring logic outside triggers.

### 40.13. Can a trigger send an email after INSERT?

Technically extensions or UDFs can reach external systems, yet that **cannot transactionally roll back external side effects** and holds locks while waiting on the network. Use an outbox plus an independent worker instead.

### 40.14. Should triggers be disabled during bulk imports for speed?

Never do so arbitrarily. Disabling triggers can skip validation and auditing, and altering system triggers can compromise FK integrity. Consider staging tables, set-based transformations, batch sizing, index maintenance, and controlled migrations.

### 40.15. Trigger vs. rule: which should be used to make a view writable?

First check whether an **automatically updatable view** works. When custom per-row mapping is needed, an `INSTEAD OF` trigger is usually easier to write and trace at execution time than query-rewrite rules. Still, the choice depends on the view design, performance, and business requirements.

## 41. Official PostgreSQL Documentation

The following links point to current PostgreSQL documentation. When applying to production, consult the **exact PostgreSQL major version** you run (especially for partition triggers, MERGE, generated columns, and transition relations):

- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): timing syntax, `FOR EACH ROW/STATEMENT`, `WHEN`, `UPDATE OF`, `REFERENCING`, and constraint triggers.
- [Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html): timing/level, trigger ordering, row modifications, and complex events.
- [Overview of Trigger Behavior](https://www.postgresql.org/docs/current/triggers.html): overview of how triggers work in PostgreSQL.
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): `RETURNS trigger`, `NEW`, `OLD`, `TG_OP`, `TG_WHEN`, `TG_LEVEL`, `TG_ARGV`, and return values.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): declaring trigger functions and `SECURITY DEFINER` semantics.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT` and `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): updating rows, `RETURNING`, and partition row movement cases.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html): DELETE and `RETURNING`.
- [TRUNCATE](https://www.postgresql.org/docs/current/sql-truncate.html): differences from DELETE, triggers, and transaction behavior.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): combining INSERT/UPDATE/DELETE actions in one statement.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): loading data and effects on triggers.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): updatable views and view options.
- [Updatable Views](https://www.postgresql.org/docs/current/rules-views.html): view updating mechanisms, rule rewriting, and choosing triggers.
- [CREATE RULE](https://www.postgresql.org/docs/current/sql-createrule.html): query rewrite rules, distinct from triggers.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): evaluation timing relative to BEFORE/AFTER triggers.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): row movement and trigger limitations on partitions.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, UNIQUE, FOREIGN KEY, and deferred checks.
- [SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): switching immediate/deferred constraint behavior.
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE`, SQLSTATE, and error handling.
- [PL/pgSQL Error Trapping](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING): exception blocks and subtransaction semantics.
- [Security-Definer Functions](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY): `search_path` and privilege notes.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): execution impact of `ANALYZE` and timing information.
- [System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html): metadata, enabled mode, and internal triggers.
- [Information Schema triggers](https://www.postgresql.org/docs/current/infoschema-triggers.html): portable trigger metadata.

## 42. Summary

**BEFORE, AFTER, and INSTEAD OF are three execution timings with distinct purposes**, not interchangeable ways of writing the same thing:

| Timing | Mnemonic | Typical use case |
| --- | --- | --- |
| **`BEFORE`** | **Before the row/statement is executed** | Normalize `NEW`, validate, optionally skip row or raise error |
| **`AFTER`** | **After the row operation/statement** | Auditing, processing modified data, transition tables, constraint triggers |
| **`INSTEAD OF`** | **In place of the operation sent to a view** | DML into base tables through a view with custom mapping |

Do not forget the second dimension: **row-level** runs once per affected row, while **statement-level** runs once per statement, **even when 0 rows are affected**. In `BEFORE ROW`, `RETURN NEW`/`RETURN OLD` lets the row proceed, while `RETURN NULL` skips it. In `AFTER ROW` and statement-level triggers, return values are ignored. In `INSTEAD OF ROW`, the return value tells PostgreSQL the row was handled and feeds `RETURNING`/affected-row counts.

When working with UPDATEs, `UPDATE OF col` only indicates that the column appeared in the SET list, **not that its value actually changed**; use `OLD.col IS DISTINCT FROM NEW.col` when needed. For bulk DML, `AFTER STATEMENT` with `REFERENCING OLD/NEW TABLE` processes the entire row set rather than running per-row aggregates in every row trigger.

**AFTER does not mean post-COMMIT.** Trigger changes—including audit INSERTs—still belong to the transaction and roll back when the transaction fails or cancels. Separately, constraint triggers can be **deferred** until the transaction-completion phase, whereas TRUNCATE has no row-level triggers, UPSERT/MERGE can emit multiple event kinds, and partition-moving UPDATEs become DELETE+INSERT at the row level.

A solid trigger design answers four questions clearly: **when does it run; which NEW/OLD or row set does it see; what can it modify or skip; and which transaction owns its changes?** Only then should you evaluate constraints, N+1 performance, recursion, `SECURITY DEFINER` privileges, transition tables, transaction rollbacks, and special-case testing. Triggers help keep rules close to data, yet remain safe and maintainable only when timing, level, side effects, and ownership are transparent.
