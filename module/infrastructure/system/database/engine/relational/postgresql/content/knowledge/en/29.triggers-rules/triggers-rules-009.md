# Trigger Ordering, Recursion, and Side-Effect Loops in PostgreSQL

## 1. Why Understanding Trigger Ordering Matters

A single table can have multiple triggers attached to it: normalizing data, validating business rules, updating summary tables, writing change history, emitting notifications, or synchronizing state to another table. When an `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` statement runs, triggers do not fire arbitrarily; PostgreSQL follows specific rules for **timing**, **firing level**, **ordering within the same category**, **`OLD`/`NEW` values**, and **transactions**.

If a trigger executes SQL that modifies a table that also has triggers, a nested call chain can form:

~~~text
UPDATE orders
    |
    v
AFTER UPDATE trigger orders
    |
    +--> UPDATE accounts
              |
              v
         AFTER UPDATE trigger accounts
              |
              +--> UPDATE orders
                           |
                           v
                    AFTER UPDATE trigger orders
                           ...
~~~

This can be a valid business workflow if it has a termination condition, or it can cause **infinite recursion, lock contention, duplicate audit logs, stack-depth errors, or side effects executing multiple times**.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish between **BEFORE**, **AFTER**, **INSTEAD OF**, **row-level**, and **statement-level** triggers.
- Determine the firing order when multiple triggers of the same kind exist; understand how trigger names affect ordering.
- Know which triggers fire when a statement **affects zero rows**.
- Understand how **BEFORE ROW** triggers modify `NEW` and affect subsequent triggers; distinguish between `RETURN NEW`, `RETURN OLD`, and `RETURN NULL`.
- Explain how SQL run inside a trigger can fire other triggers, even on the same table.
- Use `pg_trigger_depth()` to observe call depth without **overusing it as the sole anti-recursion mechanism**.
- Design loop-prevention techniques: `WHEN` conditions, `IS DISTINCT FROM`, conditional DML, idempotency, locks/constraints, and scope limits.
- Distinguish **in-transaction** side effects from external effects that **cannot be rolled back**.
- Understand additional rules for **constraint triggers**, `SET CONSTRAINTS`, `ON CONFLICT DO UPDATE`, partitioned tables, cascading actions, and transition tables.
- Query `pg_trigger`, `pg_get_triggerdef`, and `pg_stat_user_functions`, and use a SQL lab to observe behavior in a controlled way.
- Complete scenario-based exercises with solutions.

> **Safety boundary:** create and run all examples only in a permitted practice database. Do not create triggers with unbounded recursion on production just to observe the error. Commands such as `DROP`, `ALTER TABLE DISABLE TRIGGER`, HTTP calls, or emitting events outside a transaction must be evaluated separately before running in a live system.

---

## 2. What Is a Trigger and What Types Exist?

A trigger is an object attached to a **table**, **view**, or in certain cases **foreign table**, automatically invoked by PostgreSQL for a matching SQL event. A trigger references a trigger function/procedure with the appropriate syntax; in PL/pgSQL, a trigger function is typically declared with `RETURNS trigger`.

### 2.1. Three Common Timings

| Timing | Primary Purpose | Key Behavior to Remember |
|---|---|---|
| **BEFORE** | Modify/validate a row before the operation | For a row-level trigger, can modify `NEW` or `RETURN NULL` to skip the row |
| **AFTER** | Write audit records or update dependents after a successful change in the statement | The row has already been processed; the trigger function's return value does not decide whether the row is accepted |
| **INSTEAD OF** | Handle INSERT/UPDATE/DELETE on a **view** | Replaces the operation on the view with logic defined by the trigger function; used on row-level views |

`AFTER` does not mean "after COMMIT." An ordinary AFTER trigger still runs **inside the statement's transaction**, before COMMIT.

### 2.2. Two Firing Levels

- **FOR EACH ROW**: fires once for each affected row (under the supported conditions of the event/timing).
- **FOR EACH STATEMENT**: fires once per triggering statement, including statements that affect **0 rows** in many cases, provided the trigger matches the statement.

### 2.3. Events

| Event | BEFORE | AFTER | INSTEAD OF |
|---|---|---|---|
| `INSERT` | Table, row/statement | Table, row/statement | View, row |
| `UPDATE` | Table, row/statement | Table, row/statement | View, row |
| `DELETE` | Table, row/statement | Table, row/statement | View, row |
| `TRUNCATE` | Table, **statement** | Table, **statement** | Not used |

Do not write `FOR EACH ROW TRUNCATE` expecting a valid trigger. `TRUNCATE` does not fire row-level DELETE triggers.

### 2.4. Simplified Timing Model

~~~text
A simple UPDATE targeting a base table

BEFORE STATEMENT triggers
          |
          v
For each updated row:
    BEFORE ROW triggers
         |
         +--> can modify NEW or RETURN NULL
         |
         v
    UPDATE the row if not skipped
         |
         v
    AFTER ROW triggers (fired via AFTER mechanism)
          |
          v
AFTER STATEMENT triggers
          |
          v
End of statement
          |
          v
Transaction COMMIT/ROLLBACK controlled by the caller
~~~

This is a conceptual diagram. With multiple rows, modified rows may be processed in an order that depends on the execution plan; AFTER ROW triggers are queued and executed at the appropriate phase, and must not be relied upon to guarantee "row A always runs before row B." For a **deferred constraint trigger**, the actual firing time can be even later, near the end of the transaction.

---

## 3. The Most Important Ordering Rule: Triggers of the Same Kind Run by Name

If multiple triggers with the **same event, same timing, and same relation** apply to a statement, PostgreSQL executes them **in alphabetical order of the trigger name** (name ordering), not in the order you ran `CREATE TRIGGER`.

Example:

~~~sql
CREATE TRIGGER b_10_normalize
BEFORE INSERT ON demo.items
FOR EACH ROW EXECUTE FUNCTION demo.normalize_item();

CREATE TRIGGER b_20_validate
BEFORE INSERT ON demo.items
FOR EACH ROW EXECUTE FUNCTION demo.validate_item();
~~~

On a qualifying INSERT operation, `b_10_normalize` is invoked before `b_20_validate`. Changing the order in which the triggers were created does **not** change this invocation order.

### 3.1. Trigger Names Are Part of Behavioral Design

Readable prefixed names:

- `b_10_normalize`: normalize input.
- `b_20_validate`: validate after normalization.
- `a_10_audit`: write audit record.
- `a_20_derived_data`: update derived data.

Prefixes express intent, but they do not turn the trigger system into a workflow engine. Triggers of the same kind must still be designed to handle **data and transaction state** correctly.

### 3.2. Ordering Only Matters When Triggers Are Invoked Together

Do not assume every trigger on a table runs in a single global name-sorted list. First, PostgreSQL classifies by **timing, event, row/statement, and eligibility**; the name is used to sort triggers within the same firing group.

A `BEFORE ROW` trigger cannot run after an `AFTER STATEMENT` trigger just because its name starts with `z_`.

### 3.3. Distinguish Trigger Ordering from Row Ordering

~~~sql
UPDATE demo.items
SET quantity = quantity + 1
WHERE quantity >= 0;
~~~

Across multiple rows, SQL **does not guarantee** that rows with smaller `item_id` are processed first. If an audit table has an ascending sequence ID, the observed sequence order can depend on the execution plan, trigger scheduling, and concurrency; do not treat it as a durable business order.

### 3.4. Do Not Treat Renaming as a "Harmless Migration"

Renaming a trigger can change the order in which it runs relative to other triggers in the same group. When one trigger expects to receive `NEW` already normalized by another trigger, careless renaming can break business logic.

### 3.5. When Ordering Dependencies Are Too Tight, Consider a Coordinating Trigger

If the logic requires a strict `normalize -> validate -> derive fields` order, you can use **a single BEFORE trigger function** that executes those steps deliberately. This is often clearer than a web of many triggers with fragile long-term name-based ordering.

---

## 4. OLD, NEW, TG_OP, and Return Values

### 4.1. Special Variables in a Trigger Function

| Variable | Meaning |
|---|---|
| `NEW` | The new row in INSERT/UPDATE row triggers, where applicable |
| `OLD` | The old row in UPDATE/DELETE row triggers |
| `TG_OP` | Event string: `INSERT`, `UPDATE`, `DELETE`, or `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER`, or `INSTEAD OF` |
| `TG_LEVEL` | `ROW` or `STATEMENT` |
| `TG_TABLE_SCHEMA` | Schema name of the triggering relation |
| `TG_TABLE_NAME` | Name of the triggering relation |
| `TG_NAME` | Name of the currently executing trigger |
| `TG_ARGV` / `TG_NARGS` | String arguments declared on the trigger |

Do not access `NEW.col` when the trigger does not have a valid `NEW` record, or `OLD.col` in an INSERT-only trigger. Statement-level triggers do not have a specific `OLD`/`NEW` row to modify.

### 4.2. BEFORE ROW INSERT/UPDATE: Return NEW to Continue

~~~sql
CREATE FUNCTION demo.normalize_item()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.code := upper(btrim(NEW.code));
    RETURN NEW;
END;
$$;
~~~

If the trigger returns `NEW`, PostgreSQL continues processing the modified row; subsequent BEFORE triggers can observe the normalized `NEW.code`.

### 4.3. BEFORE ROW: RETURN NULL to Skip the Operation on That Row

~~~sql
IF NEW.quantity < 0 THEN
    RETURN NULL;
END IF;
~~~

`RETURN NULL` in a BEFORE ROW trigger **skips the operation for the current row**, and subsequent row-level triggers for that row are not invoked in the normal path. It **does not raise an exception** on its own; the statement can finish successfully while affecting fewer rows than expected.

Do not use `RETURN NULL` to silently drop rows that violate critical data rules if the business requires an explicit error. Consider `RAISE EXCEPTION` or a constraint instead.

### 4.4. BEFORE DELETE: Typically Return OLD

~~~sql
CREATE FUNCTION demo.guard_delete()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.is_protected THEN
        RETURN NULL;
    END IF;
    RETURN OLD;
END;
$$;
~~~

For DELETE, `OLD` is the row before deletion; `NEW` is not applicable. The return value of a BEFORE DELETE trigger only needs to be non-NULL to allow the operation, and `RETURN OLD` is standard.

### 4.5. AFTER ROW: Return Value Is Ignored

~~~sql
CREATE FUNCTION demo.audit_after()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO demo.audit_log(...) VALUES (...);
    RETURN NULL;
END;
$$;
~~~

In an AFTER trigger, the return value **does not modify the row that was written**; by convention it is usually `RETURN NULL`. Do not write `NEW.amount := ...; RETURN NEW;` in an AFTER trigger expecting the base table row to update automatically.

### 4.6. INSTEAD OF ROW Trigger on a View

An INSTEAD OF trigger replaces the operation on a view. Returning non-NULL generally signals that a row was handled, affecting the statement's row count through the view, while returning NULL indicates the row was not handled. The code must perform the appropriate underlying DML and return the row expected by the operation/`RETURNING`; do not mechanically apply regular table BEFORE/AFTER rules.

---

## 5. Before Writing a Trigger, Identify Whether Side Effects Are Transactional

A side effect can be:

- **SQL in the same transaction:** writing an audit row, updating a summary table, modifying dependent rows.
- **Operations in another DB or external system:** HTTP requests, message brokers, sending emails, payment APIs.
- **Special operations in PostgreSQL:** `nextval()`, `pg_notify()`, advisory locks, extension functions.

Not all side effects share the same rollback semantics:

| Side Effect | Reversible by Transaction Rollback? | Important Considerations |
|---|---|---|
| INSERT into audit table in same transaction | **Yes**, if the transaction rolls back | Audit row is lost along with the failed transaction |
| UPDATE summary table in same transaction | **Yes** | Can fire other triggers and cause loops |
| DELETE row in same transaction | **Yes** | Cascade triggers and FK checks may still run |
| Sequence `nextval()` | **No**, issued sequence values are not reclaimed | Sequence IDs have gaps after rollback |
| `pg_notify()` called in transaction | Notification is sent after COMMIT; rollback sends nothing | Payload/notification is not a durable queue |
| Sending HTTP/email from trigger extension/function | Usually **cannot auto-roll back** in external systems | Retries/rollbacks can cause duplicate sends |
| Writing external files/logs outside DB | Rollback not guaranteed | Do not treat as an exactly-once side effect |
| Insert into outbox table in same transaction | Outbox row rolls back cleanly | Worker publishes event after commit; idempotency still needed |

**Rule:** an AFTER trigger runs inside the transaction, not "after commit." If you need to trigger external work after commit, consider a **transactional outbox + worker** rather than making direct network calls from a trigger.

---

## 6. Standalone SQL Lab

The lab uses the `trigger_order_lab` schema. Create it only in a test database you control.

### 6.1. Create the Schema and Tables

~~~sql
CREATE SCHEMA IF NOT EXISTS trigger_order_lab;

CREATE TABLE trigger_order_lab.items (
    item_id bigint PRIMARY KEY,
    code text NOT NULL,
    quantity integer NOT NULL,
    note text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_items_qty_nonnegative CHECK (quantity >= 0)
);

CREATE TABLE trigger_order_lab.fire_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_name text NOT NULL,
    timing text NOT NULL,
    operation text NOT NULL,
    item_id bigint,
    observed_code text,
    observed_quantity integer,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`fire_log` is an **in-transaction** event log table using an identity column for observation. Gaps in `log_id` do not prove whether an audit row committed; identity/sequence values are not rolled back once allocated.

### 6.2. Trigger Function #1: BEFORE ROW Normalization

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_normalize_item()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.code := upper(btrim(NEW.code));
    NEW.updated_at := clock_timestamp();

    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NEW;
END;
$$;
~~~

This function normalizes on both INSERT and UPDATE. It does **not** issue a new UPDATE against `items`; instead, it modifies `NEW` directly, avoiding a common form of recursion.

### 6.3. Trigger Function #2: BEFORE ROW Validation

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_validate_item()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.code = '' THEN
        RAISE EXCEPTION 'code must not be empty'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.quantity < 0 THEN
        RAISE EXCEPTION 'quantity must not be negative'
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NEW;
END;
$$;
~~~

The table's CHECK constraint remains the authoritative data-integrity layer; the trigger illustrates ordering and custom messages. In real systems, avoid duplicating the same validation in multiple places without a clear reason.

### 6.4. Trigger Function #3: AFTER ROW Audit

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_audit_after()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NULL; -- Return value of AFTER ROW is ignored.
END;
$$;
~~~

### 6.5. Create Triggers with Intentional Names

~~~sql
CREATE TRIGGER b_10_normalize
BEFORE INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_normalize_item();

CREATE TRIGGER b_20_validate
BEFORE INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_validate_item();

CREATE TRIGGER a_10_audit
AFTER INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

### 6.6. Test INSERT and Observe

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id, code, quantity, note)
VALUES
    (101, ' alpha ', 3, 'first');

SELECT item_id, code, quantity, note
FROM trigger_order_lab.items
WHERE item_id=101;

SELECT log_id,trigger_name,timing,operation,
       item_id,observed_code
FROM trigger_order_lab.fire_log
WHERE item_id=101
ORDER BY log_id;
~~~

Expected result: the item code becomes `ALPHA`, and the log for this single-row INSERT shows:

1. `b_10_normalize` (BEFORE, observing `ALPHA`).
2. `b_20_validate` (BEFORE, observing `ALPHA`).
3. `a_10_audit` (AFTER, observing `ALPHA`).

In this example, log IDs increase in firing order within an uncontended session; do not extrapolate this into a global audit order across concurrent transactions.

### 6.7. Test UPDATE

~~~sql
UPDATE trigger_order_lab.items
SET code=' beta ', quantity=5
WHERE item_id=101;

SELECT item_id,code,quantity
FROM trigger_order_lab.items
WHERE item_id=101;

SELECT log_id,trigger_name,operation,observed_code
FROM trigger_order_lab.fire_log
WHERE item_id=101
ORDER BY log_id;
~~~

The update also passes through both BEFORE triggers and the AFTER trigger; `code` is normalized to `BETA`.

### 6.8. When BEFORE Validation Raises an Error

~~~sql
-- Run standalone to observe the exception; do not include in a migration.
UPDATE trigger_order_lab.items
SET code='   '
WHERE item_id=101;
~~~

`b_10_normalize` turns `code` into an empty string, and `b_20_validate` raises an exception. The failing statement is rolled back, including the `fire_log` INSERT executed by `b_10_normalize` in the same transaction. If the statement runs inside a larger multi-statement transaction, final behavior depends on transaction boundaries and how the caller handles exceptions.

---

## 7. One Trigger Can Observe the Output of a Previous Trigger

Two BEFORE ROW triggers on the same row receive and transform `NEW` sequentially.

~~~text
Input: code = " alpha "
       |
       v
b_10_normalize
  NEW.code = "ALPHA"
  RETURN NEW
       |
       v
b_20_validate
  checks NEW.code = "ALPHA"
  RETURN NEW
       |
       v
Row is INSERTed/UPDATEd with code="ALPHA"
       |
       v
a_10_audit
  writes audit of the row after all BEFORE triggers
~~~

If `b_20_validate` were renamed to `b_05_validate`, the validator would run **before** the normalizer. This changes the data that the validator sees. Therefore:

- Determine whether execution order is truly a dependency.
- If it is, document it in the contract/migration.
- Consider a single consolidated trigger for a row-manipulation pipeline.
- Rely on constraints to enforce final invariants.
- Verify behavior with tests, not just by reading function names.

### 7.1. Columns Modified by a BEFORE Trigger

If BEFORE trigger A sets `NEW.code`, BEFORE trigger B sees the modified value. A subsequent BEFORE trigger can also reassign and overwrite it. The **final row** is decided only after all required BEFORE triggers finish without returning NULL or raising an exception.

### 7.2. BEFORE ROW `WHEN` Evaluates State at Trigger Evaluation Time

Example:

~~~sql
CREATE TRIGGER b_30_log_nonempty
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (NEW.code <> '')
EXECUTE FUNCTION trigger_order_lab.fn_validate_item();
~~~

A `WHEN` clause on BEFORE ROW is evaluated right before the corresponding trigger function executes, so it sees `NEW` as modified by earlier BEFORE triggers. **This snippet is illustrative only; do not create duplicate validation triggers unnecessarily if the lab already has `b_20_validate`.**

### 7.3. AFTER ROW Cannot Modify the Row via Return Value

If you need to alter column values on the same row, do it in a BEFORE trigger via `NEW` whenever appropriate. An AFTER trigger would have to execute `UPDATE items ...` to actually modify the row, and that UPDATE can in turn fire new triggers and cause recursion. This is why the design distinction between BEFORE and AFTER matters so much.

---

## 8. Statement-Level Triggers: Firing Even When Zero Rows Match

### 8.1. A Function to Trace Each Statement

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_trace_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name,timing,operation,item_id,
         observed_code,observed_quantity)
    VALUES
        (TG_NAME,TG_WHEN,TG_OP,NULL,NULL,NULL);

    RETURN NULL;
END;
$$;
~~~

### 8.2. Attach Two Statement Triggers

~~~sql
CREATE TRIGGER s_10_before_update
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_statement();

CREATE TRIGGER s_90_after_update
AFTER UPDATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_statement();
~~~

### 8.3. An UPDATE Affecting 0 Rows Still Fires Statement Triggers

~~~sql
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=-999;

SELECT log_id,trigger_name,timing,operation
FROM trigger_order_lab.fire_log
WHERE item_id IS NULL
ORDER BY log_id;
~~~

When an UPDATE statement executes even if no rows match, `s_10_before_update` and `s_90_after_update` still fire according to statement-level semantics.

However, **row-level** update triggers do not run because no rows were updated.

### 8.4. Application Affected-Row Count Remains 0

A statement-level trigger may INSERT an audit or log row for a statement that affected zero rows. That does **not** turn the outer UPDATE's affected-row count into 1; DML inside a trigger is a separate side effect.

### 8.5. Do Not Use Statement-Level Triggers to Modify a Specific Row's NEW

Because a statement can affect 0, 1, or many rows, a statement-level trigger has no single `NEW` record representing one row. For per-row logic, use a row-level trigger or appropriate transition tables.

---

## 9. Multi-Row Triggers: Avoid Ordering Assumptions

### 9.1. One Statement Affecting Multiple Rows

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity,note)
VALUES
    (102,' gamma ',5,'second'),
    (103,' delta ',7,'third'),
    (104,' epsilon ',2,'fourth');
~~~

Each row passes through the matching row-level triggers. However, **never base business rules on the order** in which PostgreSQL processes rows during a multi-row `INSERT ... SELECT` or `UPDATE ... WHERE`.

### 9.2. After a Multi-Row UPDATE

~~~sql
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id IN (101,102,103,104);
~~~

With statement-level UPDATE triggers present, we get:

- BEFORE STATEMENT: once.
- BEFORE ROW: once per affected row.
- AFTER ROW: once per processed row.
- AFTER STATEMENT: once.

**The exact order across different rows is not guaranteed.** Multiple triggers of the same event/timing on **a single row** still follow name ordering. Do not use `ORDER BY` inside a subquery to force trigger side-effect order across rows.

### 9.3. Need Chronological Ordering in Audit Logs?

If you need to reconstruct history, record **transaction ID, business version, created_at, and identity event ID**, and design appropriate conflict resolution. A sequence/identity provides numbers increasing in allocation order, not proof of commit order; timestamps can also tie or differ from commit order.

### 9.4. Do Not Recompute Aggregates per Row If Statements Touch Many Rows

A row trigger that updates a summary table for every item can be very expensive and increase lock contention. For large batches, consider an **AFTER STATEMENT trigger + transition tables** to compute set-based deltas, where supported by your PostgreSQL version and table type.

---

## 10. Triggers Calling Triggers: How Recursion Forms

A trigger function can execute SQL. That SQL can fire additional triggers, whether it targets the same table or a different table.

~~~text
Application: UPDATE A
      |
      v
AFTER UPDATE A: trigger ta
      |
      +--> UPDATE B
                |
                v
          AFTER UPDATE B: trigger tb
                |
                +--> UPDATE A
                         |
                         v
                    AFTER UPDATE A: trigger ta
                         ...
~~~

### 10.1. Direct Recursion

An `AFTER UPDATE ON items` trigger executes:

~~~sql
UPDATE trigger_order_lab.items
SET updated_at=clock_timestamp()
WHERE item_id=NEW.item_id;
~~~

If every UPDATE fires that same trigger and the trigger has no termination condition, the chain can invoke itself indefinitely. PostgreSQL does not automatically infer "this update came from a trigger, skip triggers" for you.

### 10.2. Indirect Recursion

Trigger A updates B, trigger B updates C, and trigger C updates A. Indirect cycles are harder to spot because no single function calls itself directly.

### 10.3. Valid Recursion

Recursion is not automatically a bug. Examples include propagating state up a parent-child tree, adjusting multi-level dependent data, or converging toward a fixed point. However, you must **prove that the algorithm terminates**, avoid revisiting records needlessly, and ensure complexity stays within production limits.

### 10.4. What Happens If It Does Not Terminate?

- High CPU, I/O, and WAL growth.
- Transactions hold row locks for a long time, blocking other queries.
- Stack-depth / excessive call-nesting errors can occur.
- Errors can roll back the entire statement/transaction.
- If non-rollbackable side effects exist, external systems may already have received many requests.
- Even if stopped by `statement_timeout`, hitting a timeout is not a proper design.

Do not treat `max_stack_depth` or `statement_timeout` as a recursion-prevention mechanism in place of proper termination logic.

---

## 11. Anti-Pattern: AFTER UPDATE Just to Set `updated_at`

### 11.1. Dangerous Pattern

~~~sql
-- BAD EXAMPLE ILLUSTRATION, DO NOT CREATE THIS TRIGGER.
CREATE FUNCTION bad_fn_touch()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE some_schema.items
       SET updated_at=clock_timestamp()
     WHERE item_id=NEW.item_id;

    RETURN NULL;
END;
$$;

-- If attached as AFTER UPDATE on items itself without a guard,
-- the inner UPDATE can repeatedly fire the same trigger.
~~~

### 11.2. Correct Pattern for Same-Row Timestamp: BEFORE UPDATE

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_new()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

Mutating `NEW` in BEFORE ROW does not issue a second UPDATE against the same table. In the lab, `fn_normalize_item` already updates `NEW.updated_at`, so **do not attach an extra overlapping touch trigger** unless you want multiple triggers overwriting the same column.

### 11.3. Update `updated_at` Only When Business Data Changes

If you want to avoid bumping the timestamp on a no-op `UPDATE SET quantity=quantity`:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_if_changed()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code IS DISTINCT FROM NEW.code
       OR OLD.quantity IS DISTINCT FROM NEW.quantity
       OR OLD.note IS DISTINCT FROM NEW.note THEN
        NEW.updated_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$$;
~~~

Use `IS DISTINCT FROM` for **NULL-safe** comparison. Do not write only `OLD.col <> NEW.col` on nullable columns: `NULL <> 'x'` evaluates to UNKNOWN, causing the IF branch not to run.

### 11.4. `WHEN` Can Avoid Unnecessary Function Calls

~~~sql
CREATE TRIGGER b_30_touch_if_changed
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (
    OLD.code IS DISTINCT FROM NEW.code
    OR OLD.quantity IS DISTINCT FROM NEW.quantity
    OR OLD.note IS DISTINCT FROM NEW.note
)
EXECUTE FUNCTION trigger_order_lab.fn_touch_new();
~~~

This is a **standalone alternative** to replace an existing timestamp design, not a command recommended to run on top of the lab since `b_10_normalize` already assigns `updated_at`. With multiple BEFORE triggers, remember that `WHEN` checks `NEW` at the moment that trigger is evaluated and can reflect modifications made by earlier triggers.

---

## 12. A Bounded-Recursion Example on a Separate Lab Table

The following example uses a dedicated table to observe trigger depth **without creating an infinite loop**.

### 12.1. Create Tables

~~~sql
CREATE TABLE trigger_order_lab.chain_counter (
    id integer PRIMARY KEY,
    val integer NOT NULL CHECK (val BETWEEN 0 AND 3)
);

CREATE TABLE trigger_order_lab.depth_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id integer NOT NULL,
    depth integer NOT NULL,
    old_val integer,
    new_val integer
);

INSERT INTO trigger_order_lab.chain_counter(id,val) VALUES (1,0);
~~~

### 12.2. AFTER UPDATE Function with a Termination Condition

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_increment_to_three()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.depth_log
        (id,depth,old_val,new_val)
    VALUES
        (NEW.id, pg_trigger_depth(), OLD.val, NEW.val);

    IF NEW.val < 3 THEN
        UPDATE trigger_order_lab.chain_counter
           SET val = val+1
         WHERE id=NEW.id
           AND val=NEW.val
           AND val<3;
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 12.3. Attach the Trigger

~~~sql
CREATE TRIGGER a_10_increment_to_three
AFTER UPDATE ON trigger_order_lab.chain_counter
FOR EACH ROW
WHEN (OLD.val IS DISTINCT FROM NEW.val)
EXECUTE FUNCTION trigger_order_lab.fn_increment_to_three();
~~~

### 12.4. Run Inside a Transaction and ROLLBACK

~~~sql
BEGIN;

UPDATE trigger_order_lab.chain_counter
SET val=1
WHERE id=1 AND val=0;

SELECT id,val FROM trigger_order_lab.chain_counter;

SELECT log_id,id,depth,old_val,new_val
FROM trigger_order_lab.depth_log
ORDER BY log_id;

ROLLBACK;
~~~

In a clean lab run, the initial update from 0 -> 1 fires the trigger at depth 1; that trigger updates `val` to 2, firing depth 2; then to 3, firing depth 3. When `NEW.val=3`, `NEW.val < 3` is false so no further UPDATE is issued; the stopping point is explicit.

Inside the transaction, the expected final value is **3**, and `depth_log` rows have depths around **1, 2, 3** along the nested call path. Actual values should always be verified against the specific query/call stack; adding other triggers on the table could also affect depth.

### 12.5. Why Should This Pattern Still Not Be Used Indiscriminately?

- One initial UPDATE updates the same row multiple times.
- It generates extra row versions, WAL, locks, index updates, and trigger invocations.
- An outer `UPDATE ... RETURNING` does not necessarily reflect the final state after nested updates.
- Under concurrent writers, careful concurrency control is required.
- For simple problems, a direct `UPDATE ... SET val=3` is clearer and far cheaper.

The lab's purpose is to **observe bounded recursion**, not to encourage using triggers as a loop construct until a condition holds.

---

## 13. `pg_trigger_depth()`: Measuring Trigger Call Depth

### 13.1. Syntax

~~~sql
SELECT pg_trigger_depth();
~~~

Outside any trigger context, the value is normally **0**. Inside the top-level trigger of a statement, it is normally **1**; a trigger invoked by SQL inside that first trigger sees **2**, increasing with each nested level.

### 13.2. Using It for Debugging

~~~sql
RAISE NOTICE 'Trigger %, operation %, depth %',
    TG_NAME,TG_OP,pg_trigger_depth();
~~~

Or log the `depth` column to an in-transaction log table like `trigger_order_lab.depth_log`.

### 13.3. A Common Guard Pattern

~~~sql
IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
END IF;
~~~

This pattern **can be useful in a very specific context**, but it is not a reliable general-purpose anti-recursion solution for every system.

### 13.4. Why a Depth Guard Alone Is Insufficient

Suppose:

~~~text
UPDATE orders
  -> trigger orders
      -> UPDATE inventory
          -> trigger inventory
~~~

The `inventory` trigger runs at depth 2, yet that may be a **valid** business flow that must execute. A blanket `pg_trigger_depth() > 1` guard would silently break that legitimate update path.

Conversely, recursion can span multiple statements or transactions outside a single call stack — for example, a worker reading an outbox table and updating a business table, emitting a new event. `pg_trigger_depth()` reflects only the **current trigger call stack**, not cross-system idempotency.

### 13.5. Do Not Substitute It for Proving Termination

Use `pg_trigger_depth()` primarily for:

- Debugging nested DML.
- Defensive limits within an operation that has a clear contract.
- Logging call paths.

Sound design still requires **data conditions**, **guard predicates**, **idempotency**, and **constraints**.

---

## 14. Stopping Loops by Checking for Real Data Changes

### 14.1. Comparing OLD and NEW

~~~sql
IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
    RETURN NEW;
END IF;
~~~

This skips extra work when the status did not change, without **canceling the caller's UPDATE**. In a BEFORE trigger it means "no further modification needed; allow the row update to proceed."

### 14.2. Trigger `WHEN` Clause

~~~sql
CREATE TRIGGER a_20_status_changed
AFTER UPDATE ON some_schema.orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION some_schema.fn_after_status_changed();
~~~

This pattern applies in a schema where the corresponding table and function already exist; do not run it verbatim in the lab unless those objects have been created.

For AFTER ROW triggers, `WHEN` avoids **queueing** an event for the function when the condition is false, which is usually more efficient than invoking the function for every row only to return immediately on an IF check.

### 14.3. Conditional DML `WHERE` Clauses to Prevent Self-Loops

In an AFTER trigger updating a secondary table:

~~~sql
UPDATE some_schema.account_totals AS t
SET last_status = NEW.status
WHERE t.account_id = NEW.account_id
  AND t.last_status IS DISTINCT FROM NEW.status;
~~~

The `IS DISTINCT FROM` predicate ensures the statement updates only when the value actually differs, cutting down unnecessary nested triggers.

### 14.4. Not Enough If Both Directions Always Produce Different Values

If table A's trigger increments B and table B's trigger increments A, then "update only when different" will still always be true:

~~~text
A.x = A.x + 1  ->  B.y = B.y + 1
        ^                |
        +----------------+
~~~

You must **remove one edge of the cycle**, make derived data unidirectional, or enforce an algorithm with a guaranteed fixed point.

### 14.5. Idempotency by Business Event

If an audit or event side effect must execute at most once for a given event, design around it:

~~~text
source_event_id (unique)
       |
       v
INSERT INTO processed_events(event_id, ...)
ON CONFLICT(event_id) DO NOTHING
       |
       v
Execute downstream work only when the INSERT actually succeeds
~~~

Unique constraints and transactions handle retries and concurrency far better than checking `pg_trigger_depth()` alone.

---

## 15. `UPDATE OF column` and the No-Value-Change Trap

### 15.1. Fires Whenever the Column Appears in the `SET` List

~~~sql
CREATE TRIGGER a_30_note_updated
AFTER UPDATE OF note ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

An `UPDATE OF note` trigger looks at **whether the column is targeted in the `SET` clause** of the UPDATE. The column might be assigned its own existing value.

### 15.2. Does Not Mean the Value Changed

~~~sql
UPDATE trigger_order_lab.items
SET note=note
WHERE item_id=101;
~~~

An `UPDATE OF note` trigger can still fire even though `OLD.note` and `NEW.note` are identical.

### 15.3. BEFORE Trigger Modifying a Column Not Listed in `SET`

If an UPDATE statement only mentions `quantity`, and a BEFORE trigger modifies `NEW.note`, a trigger declared as `UPDATE OF note` **does not automatically fire solely because the BEFORE trigger changed `note`**. Trigger column lists check the columns targeted by the original UPDATE statement.

### 15.4. How to Express an Actual Value Change

~~~sql
CREATE TRIGGER a_40_note_value_changed
AFTER UPDATE OF note ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.note IS DISTINCT FROM NEW.note)
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

Combining `UPDATE OF note` and `WHEN` avoids logging on `SET note=note`, yet **still misses the case where a BEFORE trigger silently alters `note` when the UPDATE statement did not name `note`**. If you need to catch every final change to `note`, use `AFTER UPDATE` without a column list paired with `WHEN`.

### 15.5. Do Not Overuse "Skip UPDATE If `old = new`"

A BEFORE trigger returning `RETURN NULL` whenever all columns match can affect:

- The statement's affected-row count.
- AFTER ROW triggers / audits.
- Business workflows that intentionally record an UPDATE even when values match.
- Concurrency visibility and row versions.

If you only want to skip an unnecessary **side effect**, put `WHEN` or an IF check in the **AFTER** trigger rather than canceling the row update without an explicit contract.

---

## 16. Two-Table Side-Effect Chains: How to Analyze Cycles

### 16.1. A Classic Design Bug

~~~text
orders AFTER UPDATE
   -> UPDATE customers.total_spent
       -> customers AFTER UPDATE
           -> UPDATE orders.sync_flag
               -> orders AFTER UPDATE
                   -> ...
~~~

If `orders AFTER UPDATE` fires for **any** column change, updating `sync_flag` re-triggers `orders` even when customer totals do not meaningfully change.

### 16.2. Approach 1: Narrow Firing to Business Fields

~~~sql
CREATE TRIGGER a_10_recalc_customer_total
AFTER UPDATE OF amount,status,customer_id ON some_schema.orders
FOR EACH ROW
WHEN (
    OLD.amount IS DISTINCT FROM NEW.amount
    OR OLD.status IS DISTINCT FROM NEW.status
    OR OLD.customer_id IS DISTINCT FROM NEW.customer_id
)
EXECUTE FUNCTION some_schema.fn_recalc_customer_total();
~~~

This is a **design pattern**, not DDL to run directly in the lab: the referenced objects must exist first.

Updating only `sync_flag` no longer triggers recalculation. This breaks one edge of the cycle based on business-field relevance.

### 16.3. Approach 2: Keep Derived Data Ownership One-Way

Design explicitly:

~~~text
orders (authoritative source of truth)
       |
       v
customer_totals (projection derived from orders)
       |
       X do not write back to orders
~~~

Derived tables can be maintained directly via a single-direction trigger, a batch job, or a materialized view. Avoid letting derived side effects write back to the source of truth unless there is a compelling reason and a provable termination mechanism.

### 16.4. Approach 3: Commands/Events Instead of Ping-Pong Triggers

Complex workflows should use explicit command handlers or outbox events; events are processed idempotently with a well-defined state machine and transition guards. Do not use two triggers ping-ponging updates back and forth to simulate an ownerless workflow.

### 16.5. Conditional SQL to Protect Locks and Write Load

If maintaining a summary table synchronously is mandatory:

~~~sql
UPDATE some_schema.customer_totals AS t
SET total_amount = v_calculated
WHERE t.customer_id = NEW.customer_id
  AND t.total_amount IS DISTINCT FROM v_calculated;
~~~

This predicate avoids redundant updates, though you must still account for concurrency, foreign keys, and how `v_calculated` is computed. Computing totals from a `SELECT` under a snapshot while concurrent transactions modify orders can yield stale aggregates unless appropriate locking or atomic delta updates are used.

---

## 17. Synchronizing Summary Tables: Multi-Row and Contention Issues

### 17.1. Row Trigger Updating Totals per Row

A trigger after inserting an order might run:

~~~sql
UPDATE some_schema.customer_totals
SET total_amount = total_amount + NEW.amount
WHERE customer_id=NEW.customer_id;
~~~

This delta update can work if the summary table is initialized properly and row locking keeps the delta atomic. However, you must cover all cases:

- New INSERTs.
- DELETEs reversing the delta.
- UPDATEs to amount, status, or owner.
- Moving an order from one customer to another.
- Status transitions like `paid -> refunded` and back.
- Constraint errors and transaction rollbacks.
- Bulk DML touching millions of rows.

Logic that only adds on INSERT **will drift** after DELETEs or UPDATEs.

### 17.2. Hotspots

If many concurrent transactions insert orders for the same customer, every trigger updates the same `customer_totals` row, causing **hot-row contention**. Even logically correct trigger code can become a severe performance bottleneck.

### 17.3. AFTER STATEMENT + Transition Tables

When a batch UPDATE affects 100,000 rows, transition tables let you aggregate deltas **as a set** instead of issuing 100,000 individual summary UPDATEs. The next section covers this in detail.

### 17.4. Idempotent Reconciliation

Another safeguard: periodically verify summary tables against the source of truth with a query to detect drift and recompute if needed. Without reconciliation tests, subtle multi-branch trigger bugs can stay hidden indefinitely.

---

## 18. AFTER STATEMENT and Transition Tables

### 18.1. What Is a Transition Relation?

Certain AFTER triggers can declare **transition tables** containing the set of old/new rows touched by the statement:

- `OLD TABLE`: old row images for rows affected by UPDATE/DELETE.
- `NEW TABLE`: new row images for rows affected by INSERT/UPDATE.

They enable set-based SQL inside triggers.

### 18.2. Example: Counting Rows Whose `quantity` Changed

~~~sql
CREATE TABLE trigger_order_lab.change_batches (
    batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_rows bigint NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION trigger_order_lab.fn_count_updated_items()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_changed bigint;
BEGIN
    SELECT COUNT(*)
      INTO v_changed
      FROM old_rows AS o
      JOIN new_rows AS n USING (item_id)
     WHERE o.quantity IS DISTINCT FROM n.quantity;

    INSERT INTO trigger_order_lab.change_batches(changed_rows)
    VALUES (v_changed);

    RETURN NULL;
END;
$$;

CREATE TRIGGER s_80_count_item_changes
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_updated_items();
~~~

Here `old_rows` and `new_rows` are transition relation names referenced in the trigger function's SQL. They are temporary row sets scoped to the trigger context, not permanent tables in the schema.

### 18.3. Try It

~~~sql
BEGIN;

UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id IN (101,102,103);

SELECT * FROM trigger_order_lab.change_batches
ORDER BY batch_id DESC LIMIT 1;

ROLLBACK;
~~~

If items 101..103 exist and `quantity` actually changes, `changed_rows=3`. `s_80_count_item_changes` fires only once for the statement rather than once per row. If the UPDATE matches 0 rows, the statement trigger still runs and inserts `changed_rows=0`.

### 18.4. Limitations to Keep in Mind

Transition tables have syntax and applicability restrictions:

- Available on supported AFTER triggers on ordinary tables depending on PostgreSQL version.
- Not supported on constraint triggers.
- For `UPDATE` triggers with transition tables, you cannot specify a column list such as `UPDATE OF quantity` on the same trigger.
- The transition relations declared in `REFERENCING` must match the event.
- With partitioned tables, multi-stage operations, and FK actions, transition relation contents/routing should be tested against your target PostgreSQL version.

### 18.5. Do Not Use Transition Tables to Infer Row Order

A transition table represents a **set of rows**, with no processing-order guarantee. When aggregating, join and `GROUP BY` on keys; never rely on identity/log IDs to pick "the first row" from a transition relation.

---

## 19. Constraint Triggers and Deferred Execution

### 19.1. How Constraint Triggers Differ from Ordinary Triggers

A user-defined **constraint trigger** is created with `CREATE CONSTRAINT TRIGGER`; it supports eligible AFTER ROW cases and can be declared `DEFERRABLE`.

PostgreSQL also implements some referential-integrity checks using internal constraint triggers. Do not manually alter or disable those internal triggers as if they were application audit triggers.

### 19.2. What Does Deferred Mean?

- `NOT DEFERRABLE`: checks cannot be postponed to the end of the transaction via `SET CONSTRAINTS`.
- `DEFERRABLE INITIALLY IMMEDIATE`: runs early by default, but can be switched via `SET CONSTRAINTS ... DEFERRED` within a transaction.
- `DEFERRABLE INITIALLY DEFERRED`: queued to run at the deferred check point, normally before commit unless `SET CONSTRAINTS` switches it to immediate.

**"AFTER" does not mean deferred:** a normal AFTER trigger and a deferred constraint trigger have different execution timing.

### 19.3. Example Syntax

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_constraint_probe()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE
        'Constraint trigger %, item %, depth %',
        TG_NAME, NEW.item_id, pg_trigger_depth();
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER ct_item_probe
AFTER INSERT OR UPDATE ON trigger_order_lab.items
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_constraint_probe();
~~~

This trigger uses **NOTICE** purely to demonstrate timing, not as a real data-invariant check. Never rely on a diagnostic probe like this as proof of data invariants. With sensitive data, avoid logging row fields indiscriminately.

### 19.4. Testing `SET CONSTRAINTS`

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (190,' deferred ',2);

-- Observe firing time when switching to IMMEDIATE.
SET CONSTRAINTS ct_item_probe IMMEDIATE;

ROLLBACK;
~~~

In PostgreSQL, switching a deferrable constraint from deferred to immediate evaluates pending queued events right at the `SET CONSTRAINTS` call. Otherwise, deferred events are normally checked before commit.

### 19.5. When Is a Constraint Trigger's `WHEN` Clause Evaluated?

If a constraint trigger has a `WHEN` clause, the condition **is evaluated immediately after the row operation**, not deferred along with the function call. If `WHEN` is false, the event is not queued. If `TRUE`, execution of the function can be deferred according to deferral settings.

### 19.6. A Deferred Trigger May See Different DB State Than When Queued

If the function executes at transaction end, subsequent statements in the same transaction may have modified related rows. Do not assume a `SELECT` inside a deferred trigger sees the exact snapshot state from right after the statement that queued it. Invariant logic should verify current state.

### 19.7. `SET CONSTRAINTS` Does Not Control Every Trigger

`SET CONSTRAINTS` applies to matching **deferrable constraints / constraint triggers**; it does not defer ordinary AFTER ROW triggers. Do not treat it as a switch to "make all triggers run after commit."

---

## 20. Foreign Key Internal Triggers and Cascading Actions

### 20.1. Foreign Keys Rely on Trigger Machinery

PostgreSQL uses internal constraint triggers to enforce referential integrity checks and actions where appropriate.

Example:

~~~sql
CREATE TABLE trigger_order_lab.parents (
    parent_id integer PRIMARY KEY
);

CREATE TABLE trigger_order_lab.children (
    child_id integer PRIMARY KEY,
    parent_id integer NOT NULL
      REFERENCES trigger_order_lab.parents(parent_id)
      ON DELETE CASCADE
);
~~~

When deleting a parent, `ON DELETE CASCADE` deletes matching child rows and can fire DELETE triggers defined on `children`.

### 20.2. Cascades Can Trigger Multi-Level Side Effects

~~~text
DELETE parent
      |
      v
FK ON DELETE CASCADE
      |
      v
DELETE child
      |
      +--> child BEFORE DELETE trigger
      |
      +--> child AFTER DELETE trigger
                |
                +--> DML on another table
                          |
                          +--> more triggers...
~~~

This is a form of **nested DML** that does not originate from SQL you wrote directly inside your trigger function.

### 20.3. Do Not Guard Globally with `depth > 1`

A child DELETE trigger can legitimately run at a nested depth because of a valid FK referential action. Writing "if `pg_trigger_depth() > 1` then `RETURN NULL`" can silently skip critical audits or validation during cascades.

### 20.4. Constraint Timing vs. FK Action Timing Differ Across Cases

Some FK checks can be deferred, while referential actions such as cascade or set-null follow specific FK and action timing rules. Do not assume that marking an FK `DEFERRABLE` postpones all cascade side effects until COMMIT.

### 20.5. Never Disable Internal Triggers to Avoid Loops

`ALTER TABLE ... DISABLE TRIGGER ALL` or `session_replication_role='replica'` can bypass referential integrity machinery in certain contexts. This is **not** a proper fix for trigger recursion; it risks orphaned data. Fix the trigger graph and constraint design instead of bypassing engine validation.

---

## 21. `INSERT ... ON CONFLICT DO UPDATE`: Can Fire Both INSERT and UPDATE Triggers

### 21.1. UPSERT Is Not Simply "Either INSERT or UPDATE, Only One Side"

A statement like:

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES
    (101,' changed ',10)
ON CONFLICT (item_id)
DO UPDATE SET
    code=EXCLUDED.code,
    quantity=EXCLUDED.quantity;
~~~

can cause both **BEFORE ROW INSERT** and **BEFORE ROW UPDATE** triggers to execute for the same row when a conflict routes into `DO UPDATE`, in addition to statement-level triggers for the participating events.

### 21.2. Role of `EXCLUDED`

Changes made by **BEFORE INSERT row triggers** are reflected in the `EXCLUDED` values seen by the `DO UPDATE` clause. If BEFORE INSERT uppercases `code`, `DO UPDATE` using `EXCLUDED.code` receives the uppercased value, and then BEFORE UPDATE runs on it as well.

Therefore, avoid **non-idempotent** transformations in triggers, such as unconditionally prepending a prefix on every run:

~~~text
Input: A
BEFORE INSERT -> PREFIX_A
DO UPDATE -> BEFORE UPDATE -> PREFIX_PREFIX_A
~~~

If the rule is "prefix exactly once," enforce a guard or idempotent check so it never doubles up.

### 21.3. Statement-Level Trigger Order in UPSERT

For `INSERT ... ON CONFLICT DO UPDATE`, statement-level triggers generally follow the event sequence:

1. BEFORE INSERT statement.
2. BEFORE UPDATE statement.
3. AFTER UPDATE statement.
4. AFTER INSERT statement.

Even if zero rows end up being updated in a given execution, statement-level UPDATE triggers can still fire because the `DO UPDATE` clause is present. Thus, statement-level triggers can easily log a false "update succeeded" message if they do not inspect row counts or transition relations.

### 21.4. `ON CONFLICT DO NOTHING`

When a row is skipped due to `DO NOTHING`, row-level BEFORE INSERT triggers may already have executed for the proposed row values, even though no row is actually inserted and AFTER ROW INSERT does not fire for that skipped row. If BEFORE INSERT wrote a transactional SQL log row, that side effect remains if the statement finishes cleanly under `DO NOTHING`.

**Do not equate "BEFORE INSERT trigger ran" with "a row was inserted."**

### 21.5. UPSERT Whose Update Condition Evaluates to False

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (101,' alpha ',3)
ON CONFLICT (item_id)
DO UPDATE SET quantity=EXCLUDED.quantity
WHERE trigger_order_lab.items.quantity IS DISTINCT FROM EXCLUDED.quantity;
~~~

If the existing quantity already equals the proposed value, the conflict is detected without **updating the row** because the `WHERE` predicate is false. Statement-level triggers still follow UPSERT semantics; do not infer from statement triggers alone that a row was updated.

### 21.6. Avoid Double-Auditing One Business Event

If you write audit records in both BEFORE INSERT and AFTER UPDATE, a conflicting UPSERT can log twice. Base audits on **the completed actual change** — typically in AFTER row/statement triggers with change predicates and appropriate event-key idempotency.

---

## 22. `MERGE` and Trigger Ordering

### 22.1. `MERGE` Has Multiple Action Branches

PostgreSQL 15+ supports `MERGE`, allowing conditional INSERT/UPDATE/DELETE actions on matched and unmatched rows. Exact `MERGE` trigger behavior has event- and version-specific details, but the core rules are:

- Statement-level triggers can fire for the action types present in `MERGE`, which does not prove rows were affected in every branch.
- Row-level triggers fire for rows that actually undergo the corresponding action.
- If a trigger action performs further SQL DML, nested triggers can fire.

### 22.2. Do Not Write Statement-Level Audits Claiming "Updated N Rows" Without Knowing N

An `AFTER UPDATE FOR EACH STATEMENT` trigger can fire even if the `MERGE` UPDATE branch touches zero rows. To know how many rows actually changed per action, use transition relations, command status, or version-appropriate instrumentation rather than relying solely on `TG_OP='UPDATE'` in a statement trigger.

### 22.3. `MERGE` Differs from UPSERT

Do not assume the exact per-row sequence of `ON CONFLICT DO UPDATE` applies identically to `MERGE`. Verify the event semantics of the specific statement and PostgreSQL version rather than guessing from "upsert-like" labels.

### 22.4. When Exact Action Counts Matter

Instead of logging "MERGE executed" from a trigger, consider explicit caller/workflow auditing or transition-table aggregation. The key is **counting actual changed rows and avoiding duplicate events**.

---

## 23. Partitioned Tables and Triggers Across Different Physical Relations

### 23.1. Parent vs. Leaf Partitions

A partitioned table consists of a logical parent and physical leaf partitions holding the rows:

~~~text
events (partitioned parent)
    |
    +-- events_2026_10
    +-- events_2026_11
    +-- events_2026_12
~~~

When SQL targets the parent, PostgreSQL routes rows to leaves. Statement-level triggers on the parent and row-level triggers on partitions operate at different scopes.

### 23.2. Row-Level Triggers on a Partitioned Parent

When you create a row-level trigger on a partitioned parent table, PostgreSQL creates cloned triggers on matching partitions (subject to supported options and version). Be mindful of trigger names and cloned triggers during `ATTACH`/`DETACH` partition operations.

### 23.3. Statement-Level Triggers on the Parent

If SQL targets the parent, the **parent's** statement-level triggers fire; a statement-level trigger attached directly to a leaf does not automatically fire merely because a parent-targeted statement routed rows into that leaf.

If SQL targets a leaf directly, statement-level triggers are determined by the actual target relation.

### 23.4. An UPDATE Changing the Partition Key Can Trigger Row Movement

When an UPDATE moves a row across partitions:

- BEFORE UPDATE row triggers can fire on the **source partition**.
- BEFORE INSERT row triggers can fire on the **destination partition**.
- AFTER ROW events typically follow a DELETE on the source partition and an INSERT on the destination partition rather than a simple AFTER UPDATE row trigger.

Consequently, audit logic listening "only to AFTER UPDATE row triggers" can miss or misinterpret cross-partition row movement. Test on your actual PostgreSQL version and design audits to cover row movement.

### 23.5. Do Not Use BEFORE ROW to Arbitrarily Re-Route Across Partitions

Modifying the partition key inside a BEFORE ROW trigger so a row belongs to a different partition runs into declarative partitioning constraints; do not assume PostgreSQL will re-route a row after a trigger changes `NEW` to another partition's key range. Set the routing key before INSERT, or design statements/APIs to supply the right key up front.

### 23.6. Cascades and Partitioning Complicate the Trigger Graph

A cascading parent DELETE or partition-key UPDATE can generate events across multiple physical relations. Use `TG_TABLE_SCHEMA`, `TG_TABLE_NAME`, event type, and business identity when diagnosing rather than looking only at the parent table named in the initial SQL.

---

## 24. `INSTEAD OF` Triggers on Views

### 24.1. Views Do Not Store Rows Like Regular Tables

A view may involve projections or joins. When you want clients to INSERT/UPDATE/DELETE through a non-automatically-updatable view, an `INSTEAD OF` trigger defines the actual underlying behavior.

~~~sql
CREATE VIEW trigger_order_lab.v_items AS
SELECT item_id,code,quantity
FROM trigger_order_lab.items;
~~~

This simple view is already auto-updatable; the example below adds `INSTEAD OF` merely to illustrate event interception, not because such a simple view requires one.

### 24.2. `INSTEAD OF UPDATE` Function

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_update_item_view()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE trigger_order_lab.items AS i
       SET code=NEW.code,
           quantity=NEW.quantity
     WHERE i.item_id=OLD.item_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER io_10_update_item
INSTEAD OF UPDATE ON trigger_order_lab.v_items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_update_item_view();
~~~

An UPDATE on the view now **executes an UPDATE on the base `items` table**. The base table's `b_10_normalize`, `b_20_validate`, `a_10_audit`, and matching statement triggers fire **nested inside**.

### 24.3. Do Not Assume Returning `NEW` Auto-Updates the Base Table

In an `INSTEAD OF` trigger, the function itself must perform the underlying work. `RETURN NEW` does not tell PostgreSQL to write `NEW` into a base table automatically like a BEFORE trigger on a table.

### 24.4. Beware of Indirect Recursion Through Views

An `INSTEAD OF` trigger that updates a base table whose AFTER trigger updates the view creates a `view -> table -> view` cycle. Audit the dependency graph and termination conditions.

### 24.5. View Triggers and Security

Trigger functions have their own `SECURITY INVOKER`/`DEFINER` mode; permission to access a view does not automatically grant permission to modify underlying tables. If a trigger function is `SECURITY DEFINER`, harden `search_path` and privileges according to least privilege. Misconfiguration here is a potential privilege-escalation vector.

---

## 25. `TRUNCATE` Does Not Fire `DELETE ROW` Triggers

### 25.1. Two Very Different Statements

~~~sql
DELETE FROM trigger_order_lab.items;
~~~

and

~~~sql
TRUNCATE TABLE trigger_order_lab.items;
~~~

do not share trigger behavior:

- `DELETE` fires matching `DELETE ROW` and `DELETE STATEMENT` triggers.
- `TRUNCATE` fires matching **`TRUNCATE STATEMENT`** triggers, without invoking per-row `DELETE ROW` triggers for deleted rows.

### 25.2. Why This Threatens Auditing

If a system audits deletions solely via `AFTER DELETE FOR EACH ROW`, a `TRUNCATE` bypasses per-row auditing. If `TRUNCATE` is allowed, add dedicated `TRUNCATE` auditing/controls or **revoke `TRUNCATE` privilege** from application roles.

### 25.3. `TRUNCATE` Event Trigger

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_trace_truncate()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name,timing,operation,item_id)
    VALUES (TG_NAME,TG_WHEN,TG_OP,NULL);
    RETURN NULL;
END;
$$;

CREATE TRIGGER s_10_before_truncate
BEFORE TRUNCATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_truncate();
~~~

**Do not run `TRUNCATE` on a lab containing data you need to keep** without a recovery plan. You can test it inside a lab transaction followed by `ROLLBACK` since PostgreSQL `TRUNCATE` is transaction-safe for table data, though it still takes strong locks and has snapshot/concurrency caveats.

### 25.4. `TRUNCATE CASCADE`

`TRUNCATE ... CASCADE` can affect multiple tables via FK dependencies; `TRUNCATE` triggers on all affected relations can fire. Do not assume the statement touches only the first table named.

---

## 26. `RETURN NULL` and Side Effects That Already Ran

### 26.1. A BEFORE ROW Trigger Can Cancel a Row

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_skip_zero_quantity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.quantity=0 THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;
~~~

When attached as BEFORE INSERT, a row with `quantity=0` is skipped. No row is inserted, yet the SQL statement succeeds with command tag `INSERT 0 0`.

### 26.2. Logs Written Before `RETURN NULL` Can Still Persist

Suppose BEFORE trigger `b_10_normalize` inserted a row into `fire_log`. A later BEFORE trigger returns `NULL` to skip the INSERT. Because no exception was raised, **log rows inserted before the row was skipped remain in the transaction and commit**, even though the item was never inserted.

This is critical: never use **BEFORE audits** as proof that a row was persisted.

### 26.3. What If `RAISE EXCEPTION` Runs Instead of `RETURN NULL`?

If a trigger raises an error and the statement rolls back, SQL side effects performed within that statement's transaction are rolled back (aside from non-transactional effects like sequence values). If a caller catches the exception in a PL/pgSQL `EXCEPTION` block, subtransaction rollback undoes changes inside that block.

### 26.4. AFTER Triggers Are Better for Auditing "Row Passed DML"

An AFTER ROW trigger fires only after the row operation succeeds at the statement level. However, **AFTER is still before COMMIT**; a subsequent transaction rollback will roll back the audit row too. If an audit record must survive even failed transactions, you need an out-of-band/independent auditing design carefully balanced for security and consistency, not just an AFTER trigger.

### 26.5. Prevent Duplicate Audits with Event Identity

If an UPSERT, nested UPDATE, or retry causes the same business change to pass through triggers multiple times, audit records can duplicate. Use an explicit event key (transaction/request/business event ID) and a `UNIQUE` constraint when the contract requires one record per event. Never assume "an AFTER trigger fires only once in an order's lifetime."

---

## 27. Transactional Outbox: The Solution for External Side Effects

### 27.1. The Problem

A trigger inserts a payment and immediately makes an HTTP call to send an email. Later, a constraint fails and the transaction rolls back. The email was sent, yet the payment does not exist.

Or the HTTP call succeeds while the response times out; the application retries the transaction, and the email is sent twice.

### 27.2. Using an Outbox in the Same Transaction

~~~text
Application writes order/payment
         |
         v
PostgreSQL transaction
   |
   +-- INSERT/UPDATE business table
   |
   +-- INSERT outbox event  <-- trigger or application
   |
   +-- COMMIT
         |
         v
Worker reads committed outbox rows
         |
         +-- Send to broker/email/webhook
         |
         +-- Record delivered/retry
~~~

If the transaction rolls back, **both the business change and the outbox row roll back**. The worker sees only committed outbox events.

### 27.3. Example Outbox Schema

~~~sql
CREATE TABLE trigger_order_lab.outbox (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    processed_at timestamptz
);

CREATE INDEX idx_outbox_pending
ON trigger_order_lab.outbox(created_at,event_id)
WHERE processed_at IS NULL;
~~~

### 27.4. AFTER Trigger Writing to the Outbox

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_outbox_item_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.outbox
        (aggregate_type,aggregate_id,event_type,payload)
    VALUES
        ('item',NEW.item_id,'quantity_changed',
         jsonb_build_object(
             'old_quantity',OLD.quantity,
             'new_quantity',NEW.quantity
         ));

    RETURN NULL;
END;
$$;

CREATE TRIGGER a_70_outbox_quantity_changed
AFTER UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
EXECUTE FUNCTION trigger_order_lab.fn_outbox_item_change();
~~~

An UPDATE that actually changes `quantity` writes an outbox row **in the same transaction**. On ROLLBACK, the outbox row disappears too.

### 27.5. Worker Delivers Events After COMMIT

An external worker polls unprocessed outbox rows, claims jobs with appropriate locking (often `FOR UPDATE SKIP LOCKED` when suitable), delivers the event, and marks it processed.

Receivers should still be **idempotent**, because a worker crashing after delivery but before updating `processed_at` can re-send. A transactional outbox provides atomicity between *DB state and intent to publish*, not automatic external exactly-once delivery.

### 27.6. Keep Event Payloads Sufficient Without Over-Exposing Data

Do not dump secrets, passwords, or unnecessary PII into the outbox merely because `row_to_json(NEW)` is convenient. Include only fields consumers truly need, and apply encryption, access controls, and retention policies.

---

## 28. PostgreSQL `NOTIFY` Is After-Commit Delivery, Not a Durable Queue

### 28.1. A Trigger Can Call `pg_notify`

~~~sql
PERFORM pg_notify(
    'item_change',
    NEW.item_id::text
);
~~~

When called inside a transaction, the notification is delivered only after **transaction commit**; a rollback discards it.

### 28.2. However, `NOTIFY` Does Not Replace a Durable Message Broker

- Disconnected listeners miss notifications.
- Payload size is limited and unsuitable for large objects.
- Duplicate notifications within the same transaction may be coalesced under PostgreSQL rules.
- `LISTEN`/`NOTIFY` depends on transaction semantics and active client connections.
- There is no durable retry or acknowledgement queue as with an outbox table.

### 28.3. Combining Outbox and `NOTIFY`

A common architecture:

1. Trigger or application inserts an outbox row inside the transaction.
2. Call `NOTIFY` as a **wake-up hint** for consumers.
3. After commit, the listener wakes up.
4. The worker **reads the outbox** as the durable source of truth.
5. If a notification is missed, periodic polling still sweeps the outbox.

This pattern avoids treating `NOTIFY` as a guaranteed-delivery queue.

### 28.4. Do Not Call External APIs Directly from Transaction Triggers

Making HTTP calls directly inside a trigger keeps the transaction open across network latency, increasing lock duration and coupling. On errors or timeouts, coordinating DB transactions with external state becomes error-prone. An outbox is normally much safer.

---

## 29. Sequences, Time, and Non-Rollbackable Side Effects

### 29.1. Sequence Values Are Not Reclaimed on Rollback

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.outbox
    (aggregate_type,aggregate_id,event_type,payload)
VALUES
    ('demo',0,'test','{}'::jsonb);

ROLLBACK;
~~~

The outbox row rolls back, yet the sequence/identity may have allocated an `event_id` that **does not decrement back**. ID gaps are completely normal.

### 29.2. Do Not Treat Sequence Gaps as Proof of Deleted Audit Rows

An audit table having log IDs 1, 2, 5 does not prove someone deleted rows 3 and 4; it can result from rolled-back transactions, sequence caching, conflicts, or other normal events.

### 29.3. Transaction Timestamps vs. Clock Timestamps

- `now()` / `transaction_timestamp()`: start time of the current transaction per PostgreSQL semantics.
- `statement_timestamp()`: start time of the current statement.
- `clock_timestamp()`: actual wall-clock time, which advances between calls.

When observing trigger order within a single statement, multiple rows share the same transaction and statement timestamp. `clock_timestamp()` has finer resolution yet still does not guarantee a strict total commit order across concurrent transactions.

### 29.4. Do Not Substitute Timestamps for Business Versions

If you require "apply only the latest event," store a business version or sequence enforced via constraints/transactions rather than comparing timestamps that can tie or diverge from commit order.

---

## 30. Exception Handling and Rollback in Triggers

### 30.1. Caught Exceptions Roll Back SQL Inside Their Block

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_example_exception()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        INSERT INTO trigger_order_lab.fire_log
            (trigger_name,timing,operation,item_id)
        VALUES ('before_error','AFTER',TG_OP,NEW.item_id);

        RAISE EXCEPTION 'demo error';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Error caught in nested block';
    END;

    RETURN NULL;
END;
$$;
~~~

In a subblock with `EXCEPTION`, row changes executed before the exception are rolled back when the error is caught. `RAISE NOTICE` is still visible to the client; never mistake logs or notices for proof of commit.

### 30.2. Swallowing Exceptions Causes Data Drift

If an audit or summary trigger hits an error but does:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RETURN NEW;
~~~

it can allow the business row to commit while audit or derived rows are silently missing. Never swallow all errors just to make transactions "succeed" when dependent data must stay consistent.

### 30.3. When Should You Fail Fast?

If a mandatory invariant cannot be upheld (e.g., balance totals, FKs, unique event IDs, permissions), raising an exception is usually better than persisting partial state and hoping a later job repairs it. Decide based on system contracts and availability requirements.

### 30.4. External Side Effects Do Not Undo on Rollback

If a trigger already sent an HTTP request or email before raising an exception, PostgreSQL's rollback cannot "unsend the email." That is another reason to prefer outboxes and idempotency over direct external side effects.

### 30.5. Do Not Confuse Subtransactions with Independent Transactions

A PL/pgSQL `EXCEPTION` block gives internal subtransaction rollback, not an independent committed transaction for auditing. PostgreSQL does not provide a mechanism for a trigger to "autonomously commit part of its changes" inside a caller's transaction that way.

---

## 31. Triggers vs. `RECURSIVE` Queries and Rules

### 31.1. Triggers Have No `RECURSIVE` Keyword for Business Loops

`WITH RECURSIVE` belongs to SQL recursive CTEs. A trigger function looping because its SQL fires another trigger is **nested trigger execution**, not a recursive CTE.

### 31.2. What If SQL Inside a Trigger Uses a Recursive CTE?

A `WITH RECURSIVE` query might compute ancestors/descendants and then UPDATE those rows. Those UPDATEs can still fire triggers, involving **two distinct mechanisms**:

- Recursive query evaluation of the CTE.
- DML-driven trigger invocation.

Cycle prevention inside a recursive CTE (via path tracking or `CYCLE` detection) does not automatically prevent cycles in the trigger graph.

### 31.3. Rules Are a Rewrite Layer, Different from Triggers

PostgreSQL also has `CREATE RULE` (query rewrite rules). Rules rewrite statements before execution; triggers run via event semantics during DML execution. Do not apply trigger-ordering tables to rules merely because both can synchronize data.

### 31.4. Do Not Abuse Rules to Avoid Recursion

Turning a looping trigger into a rewrite rule rarely fixes underlying business semantics; it often makes `RETURNING`, multi-row statements, and side effects even harder to reason about. Choose the tool suited to your goal and PostgreSQL's documentation.

---

## 32. Inspecting Trigger Definitions in System Catalogs

### 32.1. `pg_trigger` and `pg_get_triggerdef`

~~~sql
SELECT
    t.tgname AS trigger_name,
    t.tgrelid::regclass AS relation_name,
    pg_get_triggerdef(t.oid, true) AS definition,
    t.tgenabled AS enabled_state,
    t.tgisinternal AS is_internal
FROM pg_trigger AS t
WHERE t.tgrelid = 'trigger_order_lab.items'::regclass
ORDER BY t.tgname;
~~~

This quickly lists triggers on a table. `pg_get_triggerdef` reveals timing, events, `WHEN`, and the called function without manually decoding the `tgtype` bitmask.

### 32.2. Values of `tgenabled`

| `tgenabled` | General Meaning |
|---|---|
| `O` | Enabled in normal origin/local replication modes |
| `D` | Disabled |
| `R` | Enabled when replication role is replica |
| `A` | Always enabled |

This state interacts with `session_replication_role`. Never change `session_replication_role` simply to "bypass" a trigger causing recursion; you risk disabling FK/integrity triggers too.

### 32.3. `pg_trigger.tgisinternal`

`tgisinternal=true` marks internal triggers. System FK/constraint triggers show up with this flag. Never run scripts that blindly disable or drop every trigger on a table just because it does not appear in application DDL.

### 32.4. Inspecting the Referenced Trigger Function

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS target_relation,
    t.tgfoid::regprocedure AS trigger_function,
    pg_get_functiondef(t.tgfoid) AS function_definition
FROM pg_trigger AS t
WHERE t.tgrelid='trigger_order_lab.items'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

When debugging loops, read **the SQL inside the function bodies too**, because a trigger can UPDATE other tables in ways catalog metadata alone does not depict as a graph.

### 32.5. Listing User Triggers Across a Schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c ON c.oid=t.tgrelid
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='trigger_order_lab'
  AND NOT t.tgisinternal
ORDER BY c.relname,t.tgname;
~~~

If partitions exist, you must also inspect cloned triggers and child relations. Never inspect only the parent and assume you have mapped the entire graph.

### 32.6. Inspecting Constraint Triggers

~~~sql
SELECT
    conname,
    contype,
    conrelid::regclass AS relation_name,
    confrelid::regclass AS referenced_relation,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace='trigger_order_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

`pg_constraint` shows constraints, but **does not replace `pg_trigger`** for seeing all internal/user trigger definitions. When diagnosing FKs, inspect both.

---

## 33. Debugging Recursion: Map the Graph Instead of Guessing

### 33.1. Observing Depth

~~~sql
RAISE NOTICE 'trigger=% table=%.% event=% depth=%',
    TG_NAME,TG_TABLE_SCHEMA,TG_TABLE_NAME,TG_OP,pg_trigger_depth();
~~~

Enable verbose logging only in lab/staging or with strict log-volume limits. A tight loop can emit huge numbers of notices quickly.

### 33.2. Draw the Graph from Actual Executed SQL

Example:

~~~text
orders AFTER UPDATE (status)
  -> UPDATE customer_totals
       -> customer_totals AFTER UPDATE (total_amount)
           -> UPDATE orders (sync_flag)
               -> orders AFTER UPDATE (all columns)
                   -> UPDATE customer_totals ...
~~~

Find the **cycle-closing edge**: the `orders` trigger refired because `sync_flag` was updated even though `status` had not changed. Tightening the event/WHEN predicate eliminates the cycle.

### 33.3. Questions to Ask for Every Edge

For each trigger function, document:

- Target relation and triggering events.
- BEFORE/AFTER, ROW/STATEMENT.
- Any `WHEN` predicate.
- Tables it INSERTs/UPDATEs/DELETEs.
- Which columns actually change.
- `WHERE` conditions determining whether nested DML touches 0, 1, or many rows.
- Any HTTP/NOTIFY/sequence calls.
- Whether it can be reached via FK cascades, UPSERTs, partition movement, or other triggers.
- Where the termination condition is enforced.

### 33.4. Do Not Draw Conclusions from a Single `pg_trigger_depth` Log Entry

Depth indicates only the **current nesting level**, not the full graph, event identity, or commit state. A trigger at `depth=2` may be a legitimate FK cascade rather than a bug. Conversely, a cross-transaction loop may run at `depth=1` in every individual transaction.

### 33.5. Trace by Event ID and Transaction

For complex auditing, consider storing request/correlation IDs and business event IDs. `txid_current()` or related transaction functions help internal diagnostics, though they are not cross-system primary keys or commit-order guarantees.

### 33.6. Catching Exceptions Does Not Fix Broken Contracts

When a loop fails, do not catch `WHEN OTHERS THEN RETURN NEW` just to let requests keep returning success. A recursion error likely signals an unfinished invariant or side effect; swallowing it creates silent corruption.

---

## 34. `EXPLAIN` and Testing Queries That Have Side Effects

### 34.1. `EXPLAIN` Without `ANALYZE`

~~~sql
EXPLAIN
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;
~~~

This displays the **estimated plan** without executing the UPDATE. It does not measure actual trigger runtime.

### 34.2. `EXPLAIN ANALYZE` Actually Executes DML and Triggers

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;

ROLLBACK;
~~~

This pattern rolls back **in-transaction DML**. However:

- Sequence identities can still advance.
- External network calls, emails, and file writes may not roll back.
- Locks and I/O still occur during execution.
- If trigger code errors, the transaction enters an aborted state and requires `ROLLBACK`.

Use only in lab environments, never against heavy loads or sensitive data in production.

### 34.3. Trigger Timing in `EXPLAIN`

`EXPLAIN ANALYZE` for DML can display timing and call counts for triggers, such as:

~~~text
Trigger a_10_audit: time=... calls=...
Execution Time: ...
~~~

Exact output depends on PostgreSQL version, trigger paths, and plan presentation. Some cost may reside inside nested statements or functions; do not judge overall graph performance from a single number.

### 34.4. `pg_stat_user_functions`

If `track_functions` is configured appropriately, you can inspect function statistics:

~~~sql
SELECT
    funcid::regprocedure AS function_name,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname='trigger_order_lab'
ORDER BY total_time DESC;
~~~

Counters depend on configuration, observation window, and statistics resets. If tracking is disabled, zero rows do not mean a trigger never ran.

### 34.5. Monitoring Locks

Multi-table trigger DML lengthens transactions; you can inspect locks/sessions via:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname=current_database()
  AND pid<>pg_backend_pid();
~~~

Visibility into other sessions' queries depends on PostgreSQL privileges. Do not try to identify "which trigger is buggy" from a single snapshot alone; combine it with the dependency graph, plans, and logs.

---

## 35. Why You Should Not `DISABLE TRIGGER` to Fix Logic Bugs

### 35.1. Difference Between `USER` and `ALL`

~~~sql
-- Example DDL; DO NOT execute without understanding the consequences:
ALTER TABLE trigger_order_lab.items DISABLE TRIGGER USER;
ALTER TABLE trigger_order_lab.items ENABLE TRIGGER USER;
~~~

`USER` affects user-defined triggers under PostgreSQL semantics. `ALL` also includes internal constraint triggers, usually requires high privileges, and can break referential integrity.

### 35.2. Bypassing Audits, Validation, and Projections

Disabling triggers can:

- Skip trigger-enforced validations.
- Omit audit entries.
- Leave derived/cache tables stale.
- Cause divergence between sources of truth and projections.

Even when DB `CHECK`/`FK` constraints still guard certain invariants, trigger-only invariants will stop being enforced.

### 35.3. `session_replication_role`

`session_replication_role` controls which triggers and rules fire based on replication role (`origin`/`local`/`replica`). Changing it has sweeping effects, including skipping FK checks in applicable setups. Never set it to `replica` in regular application code just to suppress recursion.

### 35.4. Proper Alternatives

- Fix the trigger function to enforce termination conditions.
- Narrow firing using `UPDATE OF` / `WHEN` appropriately.
- Adopt a one-way derived data model.
- Use idempotent UPSERTs and unique constraints.
- Move external side effects to an outbox.
- Reconcile drifted data if triggers were previously disabled.

### 35.5. Planned Maintenance Exceptions

Legitimate migration, backfill, or replication workflows sometimes control trigger firing, but they require a formal runbook covering backups, lock budgets, privileges, post-operation validation, and rollback. Never use trigger disabling as a blanket shortcut.

---

## 36. Privileges, `SECURITY DEFINER`, and `search_path`

### 36.1. Under Whose Privileges Does a Trigger Function Run?

PL/pgSQL functions default to `SECURITY INVOKER`. A trigger function can instead be defined with `SECURITY DEFINER`, executing with the privileges of the function owner.

### 36.2. `SECURITY DEFINER` Is a Privilege Boundary

For example, a function can use owner privileges to insert into an audit table that callers cannot INSERT into directly. That can be intentional, yet if written carelessly, callers may exploit it to read or write beyond their authorization.

### 36.3. Hardening `SECURITY DEFINER`

Illustrative pattern:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_secure_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trigger_order_lab, pg_temp
AS $$
BEGIN
    -- Use schema-qualified references for sensitive relations.
    INSERT INTO trigger_order_lab.fire_log
      (trigger_name,timing,operation,item_id)
    VALUES
      (TG_NAME,TG_WHEN,TG_OP,NEW.item_id);

    RETURN NEW;
END;
$$;
~~~

Do not blindly mark every trigger `SECURITY DEFINER` simply because callers lack audit table access. Ensure:

- A least-privileged owner, never superuser unless strictly required.
- A safe `search_path` preventing untrusted schemas from shadowing objects.
- No dynamic SQL constructed from untrusted input.
- Proper verification of `CREATE`/`TRIGGER`/`EXECUTE`/`ALTER` privileges at deployment.
- Review of RLS bypass behavior and underlying table permissions.
- Logging only permitted fields.
- Audits of schema/role grants and deployments.

### 36.4. `EXECUTE` Privilege and Trigger Creation

To create a trigger referencing a function, the creator needs the required privileges, including `TRIGGER` on the relation and `EXECUTE` on the function per PostgreSQL rules. Do not assume a later `REVOKE EXECUTE` automatically disables existing triggers; manage trigger objects and privileges directly.

### 36.5. Triggers Cannot Partially Commit Independently

Even under `SECURITY DEFINER`, a trigger function still runs inside the caller's DML transaction context. Function privileges do not turn an audit INSERT into a separate transaction immune to the caller's rollback.

---

## 37. Common Mistakes and Misconceptions

| Mistake / Misconception | Consequence | Correct Understanding |
|---|---|---|
| Triggers run in `CREATE` order | Validator may run before normalizer | Same timing/event/level sort alphabetically by name |
| Different trigger names always form one global order | Confusing BEFORE vs. AFTER or row vs. statement | Timing, level, and event determine firing groups first |
| `ORDER BY` in an UPDATE forces row-trigger order | Relying on unguaranteed row processing order | Use set-based logic or explicit locking |
| AFTER triggers run after COMMIT | Email sent before transaction rolls back | AFTER still runs inside the transaction |
| A BEFORE trigger returning NEW skips later triggers | Expecting validation/audit to be bypassed | Subsequent BEFORE triggers see the modified NEW |
| `RETURN NULL` in BEFORE is an error | Caller gets no exception even though row was skipped | It quietly skips the operation on that row |
| `RETURN NEW` in AFTER updates the row | Data does not change as expected | AFTER return value is ignored |
| A BEFORE audit log proves the row was INSERTed | Row may be skipped later | Audit in AFTER or outbox as appropriate |
| Self-UPDATE for timestamp in AFTER is harmless | Nested UPDATE can recurse | Modify `NEW` in BEFORE ROW |
| `pg_trigger_depth() > 1` always means buggy recursion | Skips valid FK cascades or chained updates | Guard with business state and event identity |
| `pg_trigger_depth() = 1` means no loop | Loop can span multiple transactions | Use idempotency and reconciliation |
| `OLD <> NEW` always detects changes on nullable columns | `NULL` yields UNKNOWN | Use `IS DISTINCT FROM` |
| `UPDATE OF col` fires only when the value changes | `SET col=col` still fires it | Add `WHEN (OLD.col IS DISTINCT FROM NEW.col)` |
| A BEFORE trigger altering a column fires `UPDATE OF that_col` | Column list reflects the SQL `SET` clause | Use `AFTER UPDATE` without `OF` + `WHEN` if needed |
| Statement triggers only fire when rows are affected | `UPDATE` touching 0 rows still fires them | Never infer success merely from statement trigger firing |
| AFTER ROW triggers fire in primary-key order | Row processing has no fixed order contract | Never depend on row processing order |
| AFTER constraint triggers always run immediately | `DEFERRABLE` triggers can be postponed | Check `DEFERRABLE` and `SET CONSTRAINTS` |
| A deferred trigger's `WHEN` also waits until commit | `WHEN` is evaluated at event time | Only the function execution can be deferred |
| FK cascades never fire user triggers | Dependent DELETE/UPDATE can fire triggers | Inspect the nested DML graph |
| Conflicting UPSERT only fires UPDATE triggers | BEFORE INSERT can run too | Analyze `ON CONFLICT` semantics |
| UPSERT statement UPDATE trigger proves a row updated | `DO UPDATE` may affect 0 rows | Measure actual updated rows |
| `TRUNCATE` fires `DELETE ROW` audits | Audits are bypassed | Use dedicated `TRUNCATE STATEMENT` triggers |
| Partitioned parent row triggers work like standalone without clones | Misses leaf triggers or row movement | Check partitioning trigger semantics |
| `RETURN NULL` in `INSTEAD OF` behaves just like AFTER | Breaks affected row count / handled status | `INSTEAD OF` must execute the actual DML |
| `NOTIFY` is a durable queue | Events lost when listeners are offline | Outbox + optional `NOTIFY` |
| Continuous sequence IDs are a security guarantee | Gaps happen naturally on rollback | Never infer missing data from sequence gaps |
| Emails sent from triggers roll back with SQL | Email is already sent | Outbox + idempotency |
| AFTER audit rows survive transaction rollback | Audit row rolls back too | Same transaction boundary |
| `DISABLE TRIGGER ALL` fixes recursion | Drops FKs, audits, and constraints | Fix trigger logic, do not bypass checks |
| `WHEN OTHERS THEN RETURN NEW` is always safe | Hides broken state | Catch specific errors or rethrow |
| `EXPLAIN ANALYZE UPDATE` only simulates | UPDATE and triggers actually execute | Test inside a transaction, watch external effects |
| Having an index makes bulk row triggers cheap | Row-by-row side effects can still be expensive | Measure locks, WAL, and timing |
| Audit triggers logging full `NEW` are always right | Leaks PII and bloat | Log only required fields |
| `SECURITY DEFINER` triggers are always safe | Privilege escalation and `search_path` attacks | Least privilege and hardening |
| Renaming a trigger is purely cosmetic | Can alter execution order | Run regression tests |
| Rules and triggers are the same mechanism | Query rewrite differs from trigger execution | Distinguish `CREATE RULE` from `CREATE TRIGGER` |

---

## 38. Review Checklist for Triggers with Side Effects

### 38.1. Events and Ordering

- [ ] Which relation and event types are targeted?
- [ ] BEFORE/AFTER/INSTEAD OF and ROW/STATEMENT?
- [ ] Are there multiple triggers with the same timing/event? Was alphabetical order checked?
- [ ] Does any trigger depend on `NEW` values modified by an earlier trigger?
- [ ] Are `WHEN` predicates, `UPDATE OF` column lists, and return semantics appropriate?
- [ ] Were zero-row statements and multi-row DML considered?

### 38.2. Recursion and Termination

- [ ] Which tables does the function INSERT/UPDATE/DELETE?
- [ ] Does any downstream table have triggers writing back to the source?
- [ ] Can FK cascades, partition row movement, UPSERT, or MERGE trigger unexpected paths?
- [ ] Is termination proven from data/business state?
- [ ] Is `IS DISTINCT FROM` used for nullable fields?
- [ ] Is the logic idempotent under retries?
- [ ] Is `pg_trigger_depth()` used only for debugging/bounded guards rather than masking valid nested flows?

### 38.3. Transactions and External Side Effects

- [ ] Is in-transaction SQL audit/outbox behavior aligned with requirements?
- [ ] Are there non-rollbackable HTTP/email/extension calls?
- [ ] Is `NOTIFY` mistakenly treated as a durable queue?
- [ ] Are sequence gaps and transaction rollbacks properly understood?
- [ ] Could an exception handler swallow errors and cause data drift?
- [ ] Is there an outbox worker with duplicate-delivery handling?
- [ ] Is there a clean `ROLLBACK` path for migrations and tests?

### 38.4. Performance and Privileges

- [ ] Can bulk DML trigger expensive row-by-row trigger loops?
- [ ] Should statement-level transition tables and set aggregation be used?
- [ ] Is there hot-row contention on summary tables?
- [ ] Do indexes support `WHERE` clauses inside triggers?
- [ ] Have lock duration and deadlock potential been evaluated?
- [ ] Are `SECURITY DEFINER`/`INVOKER` and `search_path` hardened?
- [ ] Do audit/outbox payloads avoid unnecessary sensitive fields?
- [ ] Was testing done under actual application roles?

### 38.5. Deployment

- [ ] Was a catalog snapshot of existing triggers captured?
- [ ] Could a trigger-renaming migration alter firing order?
- [ ] Do tests cover INSERT/UPDATE/DELETE, UPSERT, zero rows, and multi-row batches?
- [ ] Do tests cover rollbacks and mid-transaction failures?
- [ ] Is monitoring in place for WAL, locks, trigger calls, outbox backlog, and audit drift?
- [ ] Does the rollback plan avoid disabling FKs/internal triggers?
- [ ] Is there a reconciliation job if derived data can drift?

---

## 39. Scenario 1 — Orders Updating Customer Totals

### Context

Orders have `status`, `customer_id`, and `amount`. Reporting needs `customer_totals.total_paid`.

A naive approach: `AFTER UPDATE` on `orders` recalculates totals and updates `customers`; `AFTER UPDATE` on `customers` updates a flag on `orders`. The two triggers can form a loop.

### Better Design

1. **Authoritative source:** `orders`.
2. `customer_totals` holds only a derived projection.
3. Enforce one-way sync **orders -> totals**; never write back to `orders` from a totals trigger.
4. Fire the trigger only when `status`/`amount`/`customer_id` genuinely changes.
5. For large batches, consider statement-level transition tables and aggregation.
6. Maintain a reconciliation query: `SELECT customer_id, SUM(amount) FROM orders WHERE status='paid' GROUP BY customer_id`.
7. Run inside transactions and test concurrent updates, especially on hot customer IDs.

If you need a "customer reached VIP threshold" business event, emit a dedicated **outbox event** when the threshold transition happens rather than bouncing updates back to `orders` across triggers.

---

## 40. Scenario 2 — Synchronizing `updated_at`

### Requirement

Set `updated_at` whenever business fields change, without creating recursion.

### Sound Choice

Use a **BEFORE UPDATE FOR EACH ROW** function that assigns `NEW.updated_at`, with a `WHEN` clause comparing business columns that actually changed; do not run a second UPDATE on the same table.

~~~sql
-- Skeleton pattern; choose the table's real business columns.
IF OLD.name IS DISTINCT FROM NEW.name
   OR OLD.status IS DISTINCT FROM NEW.status THEN
    NEW.updated_at := clock_timestamp();
END IF;

RETURN NEW;
~~~

Never use an AFTER trigger that issues an UPDATE against the current row just to set a timestamp. If other BEFORE triggers normalize data, check **trigger ordering** and whether comparison occurs before or after normalization.

---

## 41. Scenario 3 — Sending Email After Payment

### Dangerous Design

An `AFTER UPDATE` trigger on `payments` makes an HTTP call to send an email. Later, the transaction fails and rolls back; the email was still sent. A retry sends it a second time.

### Safer Design

- Emit an event only on a **genuine state transition** to `paid`.
- Write to an outbox table with a unique business event ID inside the same DB transaction.
- Have a worker read committed events and send emails idempotently.
- Track processed state/attempts and retry failures cleanly.
- Optionally use `NOTIFY` to wake up the worker, never as the source of truth.
- Keep sensitive payment details out of payloads unless consumers require them.
- Do not emit multiple events merely because an UPSERT invokes both BEFORE INSERT and AFTER UPDATE triggers.

### SQL Predicate for Status Transition

~~~sql
-- Apply to a payments table when the schema exists:
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

`WHEN` prevents queueing an AFTER ROW event when status does not change. Ensuring **exactly one business event** externally still requires idempotency/unique keys and retry handling outside the DB.

---

## 42. Practice Exercises

Unless stated otherwise, exercises use `trigger_order_lab` from this lesson. Several ask you to write DDL **for analysis**, not necessarily to run immediately: some create overlapping lab triggers, alter audit data, or involve destructive actions. Run only in a dedicated test database, inspect dependencies, and wrap tests in `ROLLBACK` transactions where appropriate. If you executed earlier DML sections, table state may differ from the clean initial setup.

### Exercise 1 — Same-Kind Ordering

A table has three BEFORE UPDATE ROW triggers named `b_50_c`, `b_10_a`, and `b_20_b`, created in the order c, a, b. In what order do they fire when updating a row?

### Exercise 2 — Different-Timing Ordering

A table has `z_before` (`BEFORE UPDATE ROW`) and `a_after` (`AFTER UPDATE ROW`). Since `a_after` comes earlier alphabetically, does it run before `z_before`? Why?

### Exercise 3 — Zero-Row Statement

`UPDATE items SET quantity=quantity+1 WHERE item_id=-99` matches zero rows. Which lab triggers still run if statement-level UPDATE triggers exist? Do row-level UPDATE triggers run?

### Exercise 4 — Multi-Trigger Invocation Count

An UPDATE affects 100 rows; two BEFORE ROW, one AFTER ROW, one BEFORE STATEMENT, and one AFTER STATEMENT triggers all apply. What is the maximum invocation count (assuming no nested SQL, no skipped rows, and no `WHEN` filters) for each trigger kind?

### Exercise 5 — `NEW` Flowing Through Multiple BEFORE Triggers

`b_10_normalize` turns code `' alpha '` into `'ALPHA'`. What string does `b_20_validate` see? If the validator were renamed to `b_05_validate`, what might change?

### Exercise 6 — BEFORE `RETURN NULL`

A first BEFORE INSERT trigger writes a log row, and a second trigger executes `RETURN NULL` when `quantity=0`. Is the item inserted? Can the log row from the first trigger still persist if the transaction commits?

### Exercise 7 — AFTER `RETURN NEW`

An AFTER UPDATE trigger sets `NEW.quantity := 10; RETURN NEW;`. Does this change the updated row's `quantity`? What is the right approach if you want to modify it before persistence?

### Exercise 8 — BEFORE DELETE

In a DELETE row trigger, do you inspect `OLD` or `NEW` to see the row being deleted? What should you return to allow the DELETE to proceed? What should you return to skip deleting the row?

### Exercise 9 — Trigger Function Context

Write PL/pgSQL using `TG_NAME`, `TG_WHEN`, `TG_OP`, `TG_TABLE_NAME`, and `pg_trigger_depth()` to print a diagnostic notice.

### Exercise 10 — Timestamp Recursion

Why can an AFTER UPDATE trigger running `UPDATE items SET updated_at=clock_timestamp() WHERE id=NEW.id` create an infinite loop? Write a pattern that avoids the second UPDATE.

### Exercise 11 — NULL-Safe Comparison

Write a condition checking whether `OLD.note` and `NEW.note` actually differ even when one side is `NULL`.

### Exercise 12 — `UPDATE OF`

Does `AFTER UPDATE OF note` fire on `SET note=note`? If a BEFORE trigger changes `note` while the statement only `SET`s `quantity`, does `UPDATE OF note` fire automatically?

### Exercise 13 — `WHEN` Guard

Write an AFTER UPDATE ROW trigger that runs only when `quantity` actually changes. Explain the difference between `UPDATE OF quantity` and `WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)`.

### Exercise 14 — Trigger Names and Migrations

Why can renaming a trigger change runtime behavior? Name two ways to reduce that risk.

### Exercise 15 — Observing Depth

What is `pg_trigger_depth()` normally outside a trigger? What is it typically in a top-level trigger and in a trigger fired by a nested UPDATE?

### Exercise 16 — `depth > 1` Guard

Why can `IF pg_trigger_depth()>1 THEN RETURN NEW; END IF;` break legitimate behavior in an FK cascade or synchronization trigger?

### Exercise 17 — Breaking a Loop with Conditions

An `orders` trigger updates `customer_totals`, and a `totals` trigger updates `orders.sync_flag`, causing the `orders` trigger to recompute totals again. Propose a condition or graph change to break the loop.

### Exercise 18 — Termination Proof

Provide an invariant or bounded monotonic measure proving that a nested trigger chain terminates, rather than relying on timeouts.

### Exercise 19 — Row Order

An UPDATE without `ORDER BY` affects 10,000 rows. Can you rely on AFTER ROW trigger firing order to assign business sequence numbers ordered by primary key? Why?

### Exercise 20 — Transition Tables

Write an AFTER UPDATE FOR EACH STATEMENT trigger using `REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows` to count rows where `quantity` actually changed.

### Exercise 21 — Transition Table Restrictions

Is a trigger defined as `AFTER UPDATE OF quantity ... REFERENCING OLD TABLE/NEW TABLE` valid on a single relation? Why must the column list be omitted in this pattern?

### Exercise 22 — Deferred Constraint Trigger

Explain the difference between an ordinary AFTER ROW trigger and `CREATE CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`. When can the constraint trigger's function run?

### Exercise 23 — `WHEN` on a Deferred Trigger

If a deferred constraint trigger has a `WHEN` clause, is `WHEN` evaluated immediately when the row event occurs or postponed until transaction end?

### Exercise 24 — `SET CONSTRAINTS`

Write a transaction using `SET CONSTRAINTS ct_item_probe IMMEDIATE` and explain its effect on pending trigger events when switching from deferred to immediate.

### Exercise 25 — FK `CASCADE`

Parent-child tables have `ON DELETE CASCADE`, and `children` has an `AFTER DELETE ROW` audit trigger. When deleting a parent row, does the child audit trigger fire? Why?

### Exercise 26 — `TRUNCATE` vs. `DELETE`

Why does an `AFTER DELETE ROW` trigger fail to audit `TRUNCATE TABLE items`? What kind of trigger is needed to intercept `TRUNCATE`?

### Exercise 27 — UPSERT Trigger Paths

With `INSERT ... ON CONFLICT DO UPDATE`, why can a conflicting row pass through both BEFORE INSERT and BEFORE UPDATE ROW triggers? What are the implications for input normalization and auditing?

### Exercise 28 — UPSERT That Updates Zero Rows

Can `ON CONFLICT DO UPDATE ... WHERE false` still cause a statement-level UPDATE trigger to fire? Can you rely on that trigger firing to confirm a row was updated?

### Exercise 29 — Partition Movement

An UPDATE changes a partition key, moving a row from the October leaf to the November leaf. How can row triggers on source/destination differ from a regular single-table UPDATE?

### Exercise 30 — `INSTEAD OF` View Trigger

An `INSTEAD OF UPDATE` trigger on a view only runs `RETURN NEW` without updating the base table. Does the underlying row get updated automatically? If the function updates the base table, can nested base-table triggers fire?

### Exercise 31 — External HTTP

An AFTER UPDATE trigger sends an email, then the transaction rolls back. Is the email recalled automatically? Propose an architecture to reduce inconsistency.

### Exercise 32 — `pg_notify`

Does `pg_notify()` called in a rolled-back transaction emit a notification? Why doesn't `LISTEN/NOTIFY` replace a durable outbox?

### Exercise 33 — Sequence Gaps

An audit INSERT trigger uses an identity column, and the transaction later rolls back. Why can the next `log_id` jump even though the audit row no longer exists?

### Exercise 34 — BEFORE Audit vs. AFTER Audit

When a BEFORE INSERT trigger writes an audit record and a later trigger skips the row with `RETURN NULL`, how does the audit result differ from a normal AFTER INSERT ROW trigger?

### Exercise 35 — Exception Handler

A trigger catches `WHEN OTHERS` and returns `NEW` even when inserting into a summary table fails. Which data can drift out of sync? How should this be handled if the summary table must stay transactionally consistent?

### Exercise 36 — Trigger Catalog Query

Write a query listing trigger name, relation, function, and `pg_get_triggerdef` in `trigger_order_lab`, distinguishing internal triggers.

### Exercise 37 — `tgenabled`

Explain values `O`, `D`, `R`, and `A` of `pg_trigger.tgenabled`. Why shouldn't you set `session_replication_role='replica'` to dodge recursion?

### Exercise 38 — `EXPLAIN ANALYZE`

Why does `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` still produce side effects? Does wrapping it in a `ROLLBACK` transaction undo all emails and allocated sequence values?

### Exercise 39 — `SECURITY DEFINER`

A `SECURITY DEFINER` trigger function writes audit rows. List at least five hardening measures before exposing it to untrusted application roles.

### Exercise 40 — Aggregate Contention

Every order INSERT updates the same `customer_totals` row. At 10,000 orders/sec for one customer, what problems arise? Name two ways to reduce contention.

### Exercise 41 — Rules vs. Triggers

Do `CREATE RULE` and `CREATE TRIGGER` share execution timing and alphabetical ordering? Why won't converting a looping trigger into a rule necessarily fix the bug?

### Exercise 42 — Match Issues to Solutions

Match each issue to its primary fix:
1. AFTER trigger updates timestamp on the same row.
2. Two tables update each other endlessly without changing business state.
3. Email is sent before the transaction commits.
4. A 1-million-row UPDATE refreshes a summary table one row at a time.
5. Audits duplicate when an API retries.

### Exercise 43 — End-to-End Workflow Design

An e-commerce system has `orders` and `customer_totals`, needs to audit every transition to `paid`, and must deliver a partner webhook. Propose an architecture using properly timed triggers, zero loops, DB transactional atomicity, and duplicate-webhook protection.

### Exercise 44 — Debugging a Production Loop

An API UPDATE spikes CPU/locks and throws stack-depth errors. Outline a safe runbook to map the trigger graph, isolate the root cause, roll back deployment, protect data, and add regression tests — without disabling constraint triggers as a test.

### Exercise 45 — Capstone Synthesis

A single `INSERT ... ON CONFLICT DO UPDATE` statement targets a partitioned parent table with triggers on parent and child, an FK cascade, an AFTER ROW outbox trigger, and a deferrable constraint trigger. Why can't you claim "triggers always run in one alphabetical name list and then reliably fire the webhook"? Explain the layers of timing, routing, nested DML, deferral, and COMMIT involved.

---

## 43. Solution Guide — Exercises 1 to 20

### Exercise 1 — Name Ordering

The three qualifying BEFORE UPDATE ROW triggers run in the order **`b_10_a` -> `b_20_b` -> `b_50_c`**, regardless of `CREATE` order. PostgreSQL sorts triggers by name within the same event/timing/relation group.

### Exercise 2 — Timing Precedes Name

No. `z_before` is still BEFORE ROW, running before the row is updated; `a_after` is AFTER ROW, running after the row change under AFTER semantics. Name ordering never mixes separate timing phases.

### Exercise 3 — Zero-Row UPDATE

Matching **BEFORE UPDATE FOR EACH STATEMENT** and **AFTER UPDATE FOR EACH STATEMENT** triggers still run (in the lab, `s_10_before_update`, `s_90_after_update`, and any statement triggers added later). Because zero rows are updated, row-level UPDATE triggers have no rows to fire on.

### Exercise 4 — Invocation Counts

With no skipped rows, nested DML, or false `WHEN` clauses:

- BEFORE STATEMENT: **1**.
- BEFORE ROW: **2 x 100 = 200**.
- AFTER ROW: **1 x 100 = 100**.
- AFTER STATEMENT: **1**.

Total: 302 trigger-function invocations under these assumptions. Returning `NULL` in BEFORE ROW or adding other triggers changes the counts.

### Exercise 5 — `NEW` Flow

`b_20_validate` sees `NEW.code='ALPHA'` because `b_10_normalize` already modified it. Renaming the validator to `b_05_validate` causes it to see the unnormalized string `' alpha '`, potentially altering validation behavior.

### Exercise 6 — Skipped Row and Log

The `quantity=0` row is skipped when the second BEFORE trigger returns `NULL`, so it is not inserted. If the first trigger inserted a SQL log row and no exception occurs later, that log row **can still commit** because `RETURN NULL` does not roll back earlier SQL statements. Therefore, BEFORE audits do not prove a row was saved.

### Exercise 7 — AFTER Return Value

No. The return value of an AFTER ROW trigger is ignored. To alter the row before it is written, set `NEW.quantity` in a BEFORE INSERT/UPDATE ROW trigger and `RETURN NEW`. If you must react in AFTER UPDATE on the same table, guard carefully against recursive UPDATEs, though timestamp/normalization tasks almost always belong in BEFORE.

### Exercise 8 — DELETE

`OLD` contains the row being deleted; `NEW` is not used for ordinary DELETE row triggers. In BEFORE DELETE, return non-NULL (typically `RETURN OLD`) to allow deletion, or `RETURN NULL` to skip deleting that row. To reject a business violation explicitly, use `RAISE EXCEPTION` rather than silently skipping.

### Exercise 9 — Diagnostic Notice

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_log_context()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'name=%, timing=%, event=%, table=%, depth=%',
        TG_NAME,TG_WHEN,TG_OP,TG_TABLE_NAME,pg_trigger_depth();

    IF TG_OP='DELETE' THEN
        RETURN OLD;
    ELSIF TG_LEVEL='ROW' THEN
        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$;
~~~

This generic template works across events; when attaching a specific trigger, verify timing/return semantics and avoid spamming notices in production batches.

### Exercise 10 — Timestamp Update

An AFTER UPDATE trigger on `items` updating `items` causes nested UPDATEs that re-trigger the same AFTER trigger endlessly without a stopping rule. Proper pattern:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_answer()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

Attach as BEFORE UPDATE ROW as needed. If timestamps should only change when business columns change, add `WHEN` or an IF check using `IS DISTINCT FROM`.

### Exercise 11 — NULL-Safe Comparison

~~~sql
OLD.note IS DISTINCT FROM NEW.note
~~~

Evaluates to `TRUE` when one side is NULL and the other is non-NULL, or when both values differ; `FALSE` when both are NULL or equal. Never rely solely on `<>` as a guard for nullable columns.

### Exercise 12 — `UPDATE OF`

`UPDATE OF note` can fire on `SET note=note` because the column appears in the `SET` clause. If the UPDATE only sets `quantity` and a BEFORE trigger changes `NEW.note`, `UPDATE OF note` **does not automatically fire** solely because a trigger modified `note`.

### Exercise 13 — `WHEN` Guard

~~~sql
CREATE TRIGGER a_50_quantity_value_changed
AFTER UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

`UPDATE OF quantity` inspects columns listed in `SET`; `WHEN` compares actual `OLD` and `NEW` values. They can be combined, but to capture every final change including ones made by BEFORE triggers when the column wasn't in `SET`, omit `OF` and keep `WHEN`.

### Exercise 14 — Renaming Affects Order

If two BEFORE ROW triggers depend on each other, renaming can flip their alphabetical order and change normalization/validation results. Two mitigations:

1. Use ordered naming prefixes and review trigger renames as behavioral migrations.
2. Consolidate tightly coupled steps into one trigger function, or add integration tests asserting the exact outcome.

### Exercise 15 — Depth

`pg_trigger_depth()` is normally 0 outside triggers; 1 inside a trigger fired directly by top-level DML; and 2 or higher inside triggers fired by nested DML from another trigger. It reflects only the current call stack, not cross-transaction time order.

### Exercise 16 — Depth Guard Can Block Valid Logic

Triggers fired by FK cascades, partition-related DML, or another legitimate trigger run at `depth > 1`. A blanket `IF depth > 1 THEN RETURN NEW` can silently skip audits and validations (and for DELETE, returning `NEW` is wrong for the event anyway—you'd need `OLD` to proceed). Use business state, `WHEN`, idempotency, and graph analysis instead.

### Exercise 17 — Breaking the `orders <-> totals` Loop

One option: fire the `orders` trigger only when `OLD.status IS DISTINCT FROM NEW.status` or real business fields change, ignoring updates to `sync_flag`. Better yet: keep `totals` as a **one-way** projection from `orders` and eliminate the trigger writing back to `orders`. Update `totals` only when the new value actually differs via `IS DISTINCT FROM`.

### Exercise 18 — Termination Proof

Example measure: `remaining_steps = 3 - val` strictly decreases on each nested UPDATE while `val < 3`; once `val = 3`, the predicate prevents further UPDATEs. Backed by constraint `0 <= val <= 3`, the chain runs a bounded number of steps. Timeouts do not prove correctness; base termination on real data guards.

### Exercise 19 — No Stable Row Order

No. Multi-row SQL UPDATEs do not guarantee processing rows in ascending primary-key order, so AFTER ROW firing order is not a valid sequence contract. If business sequence numbers are required, use a dedicated business sequence/version mechanism with proper constraints and locking.

### Exercise 20 — Transition Tables

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_count_quantity_delta()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_changed bigint;
BEGIN
    SELECT count(*) INTO v_changed
    FROM old_rows AS o
    JOIN new_rows AS n USING (item_id)
    WHERE o.quantity IS DISTINCT FROM n.quantity;

    RAISE NOTICE 'changed rows=%',v_changed;
    RETURN NULL;
END;
$$;

CREATE TRIGGER s_75_quantity_batch
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_quantity_delta();
~~~

One UPDATE touching many rows invokes the trigger once and counts changed rows via the transition relations. If zero rows match, `count=0`.

---

## 44. Solution Guide — Exercises 21 to 45

### Exercise 21 — `UPDATE OF` Cannot Be Combined Directly with Transition Tables

When declaring transition tables on an UPDATE trigger in supported configurations, PostgreSQL forbids a column list like `UPDATE OF quantity` on the same trigger. Instead:

~~~sql
CREATE TRIGGER s_85_count_quantity
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_updated_items();
~~~

Inside the function, filter rows where `OLD.quantity IS DISTINCT FROM NEW.quantity`. Not every row in the transition table necessarily changed `quantity` if the UPDATE only changed another column.

### Exercise 22 — Deferred Constraint Trigger

An ordinary AFTER ROW trigger fires as part of the statement's AFTER phase; `AFTER` alone does not make it deferred. A constraint trigger declared `DEFERRABLE INITIALLY DEFERRED` can be queued until the deferred constraint check time (usually before COMMIT) or flushed earlier via `SET CONSTRAINTS ... IMMEDIATE`.

### Exercise 23 — `WHEN` Is Evaluated Immediately

The `WHEN` condition on a deferred constraint trigger is **evaluated when the row event occurs**. If `TRUE`, the event is queued for deferred execution; if `FALSE`, it is not queued. When the function later runs, database state may have changed further since `WHEN` was checked.

### Exercise 24 — `SET CONSTRAINTS`

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (191,' deferred-check ',1);

SET CONSTRAINTS ct_item_probe IMMEDIATE;

ROLLBACK;
~~~

If `ct_item_probe` exists and is deferred, switching it to `IMMEDIATE` causes pending queued events to execute right away. That does not mean a COMMIT happened; `ROLLBACK` still undoes all row changes in the transaction.

### Exercise 25 — FK `CASCADE` Fires Child Triggers

Yes. When FK `ON DELETE CASCADE` deletes child rows, it performs DML on the child table, firing matching DELETE triggers on `children`. This is legitimate nested DML, which is why a naive `pg_trigger_depth() > 1` guard can wrongly suppress child auditing.

### Exercise 26 — `TRUNCATE` Is Not `DELETE ROW`

`TRUNCATE` does not invoke `DELETE FOR EACH ROW` triggers to audit individual rows. To capture `TRUNCATE`, create:

~~~sql
CREATE TRIGGER s_before_truncate_answer
BEFORE TRUNCATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_truncate();
~~~

This is a **statement-level trigger**, not per-row. Create it only if the function exists and no equivalent trigger is present; do not run `TRUNCATE` on data you need to keep.

### Exercise 27 — `ON CONFLICT DO UPDATE`

A proposed INSERT row can pass through BEFORE INSERT, then hit a conflict routed to UPDATE and pass through BEFORE UPDATE as well. `EXCLUDED` can carry modifications made by BEFORE INSERT. Non-idempotent normalizations can run twice, and BEFORE INSERT audits can log even when no row is inserted. Audit **actual resulting changes** and make event processing idempotent.

### Exercise 28 — Statement-Level UPDATE Trigger Does Not Prove a Row Updated

Yes: in `ON CONFLICT DO UPDATE`, statement-level UPDATE triggers can fire even if the UPDATE branch modified zero rows due to conflict evaluation or an update `WHERE` clause. Never conclude "a row was updated" simply because `AFTER UPDATE STATEMENT` fired; check actual affected rows and distinguish action paths.

### Exercise 29 — Partition Movement Emits Different Events

When an UPDATE moves a row between leaves:

- BEFORE UPDATE ROW can fire on the source partition.
- BEFORE INSERT ROW can fire on the destination partition.
- Corresponding AFTER row events can be a DELETE on the source and an INSERT on the destination rather than a single AFTER UPDATE on one leaf.

Thus, an audit attached only to AFTER UPDATE on a leaf can miss a logical UPDATE that moves partitions.

### Exercise 30 — `INSTEAD OF` Trigger Must Do the Real Work

No. `RETURN NEW` from an `INSTEAD OF` trigger does not automatically update the base table. The function must execute the appropriate DML, e.g., `UPDATE trigger_order_lab.items ... WHERE item_id=OLD.item_id`. That inner DML fires triggers on the base table, creating nested trigger execution. Avoid `view -> base -> view` loops.

### Exercise 31 — Emails Do Not Roll Back with the Database

Emails sent via SMTP or HTTP APIs are not retracted when PostgreSQL rolls back. A better design:

1. Trigger or app writes an outbox row inside the same order/payment transaction.
2. A worker reads only committed outbox rows.
3. The worker delivers emails/webhooks with idempotency keys and retry policies.
4. Maintain processed/deduplication state, monitoring, and dead-letter/incident handling.

### Exercise 32 — `NOTIFY` and Durability

`pg_notify()` inside a rolled-back transaction emits nothing. Still, `LISTEN`/`NOTIFY` lacks a durable queue for offline/restarted listeners and has no broker-style ack/retry semantics. Use an outbox as the source of truth and `NOTIFY` only as an optional wake-up signal.

### Exercise 33 — Sequence Gaps Are Normal

`GENERATED AS IDENTITY` uses a sequence. PostgreSQL does not roll back allocated sequence values when a transaction rolls back. The log row disappears while the sequence remains incremented. Hence `log_id` values 1, 2, 5 do not prove anyone deleted logs 3 and 4.

### Exercise 34 — BEFORE vs. AFTER Audit

A BEFORE audit inserts a log row before the row change is finalized. If a later BEFORE trigger returns `NULL` to skip the row, the earlier log row still commits if the transaction commits. An AFTER INSERT ROW trigger does not run for skipped rows because no row INSERT completed at the statement level. Still, an AFTER audit will roll back if the transaction later rolls back.

### Exercise 35 — Catching `OTHERS` and Swallowing Errors Causes Drift

If a projection trigger fails and catches `WHEN OTHERS THEN RETURN NEW`, the business row commits while the projection/audit is missing or inconsistent. If the projection is a mandatory transactional invariant, **do not swallow the error**: handle only genuinely recoverable cases and `RAISE;` everything else so the transaction fails atomically. If eventual consistency is acceptable, move it to an outbox/worker with reconciliation.

### Exercise 36 — Catalog Query

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS relation_name,
    t.tgfoid::regprocedure AS trigger_function,
    t.tgisinternal AS is_internal,
    t.tgenabled,
    pg_get_triggerdef(t.oid,true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c ON c.oid=t.tgrelid
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='trigger_order_lab'
ORDER BY relation_name::text,t.tgname;
~~~

Do not filter out internal triggers when mapping the **FK/cascade graph**; filter with `NOT t.tgisinternal` when inspecting only application user triggers.

### Exercise 37 — `tgenabled` and Replication

- `O`: enabled in origin/local modes.
- `D`: disabled.
- `R`: enabled in replica role.
- `A`: always enabled.

`session_replication_role='replica'` broadly alters trigger/rule firing and can bypass FK checks where applicable; never use it as a hack around recursion. Fix the DML graph and conditions instead.

### Exercise 38 — `EXPLAIN ANALYZE UPDATE`

`EXPLAIN ANALYZE` **executes** the UPDATE and its trigger functions. Wrap it:

~~~sql
BEGIN;

EXPLAIN (ANALYZE,BUFFERS)
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;

ROLLBACK;
~~~

`ROLLBACK` reverts in-transaction DB row changes, yet **allocated sequence values** can leave gaps, and external HTTP/email calls do not roll back. Never run this on production if triggers have external side effects.

### Exercise 39 — `SECURITY DEFINER`

At least five hardening measures:

1. Grant the function owner minimal required privileges, avoiding superuser.
2. Pin a safe `SET search_path` and schema-qualify all object references.
3. Never interpolate untrusted input into dynamic SQL.
4. Restrict `CREATE`/`TRIGGER`/`EXECUTE` grants to necessary roles only.
5. Audit every table and function reachable inside the trigger body.
6. Verify RLS/`BYPASSRLS`/owner identity and privilege boundaries.
7. Never log secrets or tokens via `RAISE` or audit tables.
8. Test under actual caller roles; add regression tests for owner/`search_path` changes.
9. Avoid writing functions that expose uncontrolled external side effects.

### Exercise 40 — Hot-Row Contention

Many concurrent order INSERTs updating the same `customer_totals` row contend on a single row lock, raising latency, lock waits, WAL volume, and retry failures. Two mitigations:

- Use **statement-level transition tables** to aggregate deltas per customer per batch, cutting down summary UPDATEs.
- Move to asynchronous projection/outbox processing or sharded counters/bucketization if business rules allow eventual consistency.

Also ensure proper indexes, reconciliation, and concurrency control without trading away accuracy unless approved by business requirements.

### Exercise 41 — Rules vs. Triggers

`CREATE RULE` performs **query rewriting** before statement execution; triggers execute event-driven logic during DML phases. Rules do not follow alphabetical trigger-name ordering. Rewriting a looping trigger as a rule alters `RETURNING` and multi-row behavior and does not inherently eliminate cycles.

### Exercise 42 — Match Solutions

1. AFTER trigger updates timestamp on same row -> **BEFORE ROW modifying `NEW`**.
2. Two tables update each other endlessly without changing business state -> **break a graph edge, `WHEN`/`IS DISTINCT FROM`, one-way projection**.
3. Email sent before commit -> **transactional outbox + idempotent worker**.
4. One million rows update a summary table row-by-row -> **statement-level transition tables + set-based aggregation**, or async projection.
5. Duplicate audits on API retry -> **business event ID + `UNIQUE`/idempotency**, not just a depth guard.

### Exercise 43 — `orders` + `totals` + Webhook Workflow

Illustrative architecture:

~~~text
App UPDATEs order.status: new -> paid
           |
           v
AFTER UPDATE ROW trigger on orders
 WHEN OLD.status IS DISTINCT FROM NEW.status
  AND NEW.status = 'paid'
           |
           +--> Update customer_totals (one-way)
           |
           +--> INSERT order_audit (same transaction)
           |
           +--> INSERT outbox(unique event_id, order_id, status)
           |
           v
COMMIT succeeds
           |
           v
Worker reads committed outbox rows
           |
           +--> Deliver webhook idempotently
           |
           +--> Mark processed / retry / dead-letter
~~~

Detailed requirements:

- `orders` is the single source of truth.
- No trigger on `totals` writes back to `orders`.
- Trigger `WHERE`/`WHEN` updates totals only on real status/amount changes.
- Handle amount edits after `paid`, deleting paid orders, cancellations, customer reassignments, or reconcile totals with a source-of-truth query.
- Audit and outbox rows live in the same transaction; constraint errors roll them back atomically with the business row.
- Outbox rows carry a unique event identity; consumers enforce idempotency keys.
- Workers can retry and send duplicates, so webhook receivers must deduplicate too.
- Choose synchronous totals vs. async projections based on freshness needs and lock budgets.

### Exercise 44 — Runbook for Suspected Production Recursion

1. Record the error timestamp, statement, role, target relation, and latest deployment version; scrub sensitive data from logs.
2. If impact is severe, use an approved deployment rollback or feature flag and throttle traffic; **never blindly disable FK/internal triggers**.
3. Inspect active sessions, locks, and `pg_stat_activity` for blocked/looping backends; cancel offending queries per authorization/runbook.
4. Query `pg_trigger`, `pg_get_triggerdef`, and function definitions for involved tables, including internal FK triggers where needed.
5. Map the `event -> trigger -> DML -> event` graph; trace `A -> B -> A` edges and `WHEN`/`UPDATE OF` conditions.
6. Test with `pg_trigger_depth()` logging in staging; do not enable unbounded notices in production.
7. Reproduce in lab/staging inside transactions with tight timeouts.
8. Add business-field/`IS DISTINCT FROM` guards, break graph cycles, or move external side effects to an outbox.
9. Add regression tests for INSERT, UPDATE, DELETE, UPSERT, zero rows, batches, cascades, rollbacks, and concurrency.
10. Deploy with monitoring on query latency, lock waits, WAL rate, trigger call counts, outbox backlog, and audit drift.
11. If prior transactions failed, verify committed DB state and external side effects directly rather than guessing from sequence gaps.
12. Reconcile totals and audits to detect drift and repair via approved data-recovery procedures.

### Exercise 45 — Multiple Ordering Layers in a Partitioned-Table UPSERT

It cannot be collapsed into "one alphabetically sorted list of triggers" because:

- **Statement-level** and **row-level** triggers belong to separate phases.
- **BEFORE**, **AFTER**, and **deferred constraint** triggers fire at different times.
- `ON CONFLICT DO UPDATE` can exercise both INSERT and UPDATE trigger paths.
- Partition parent/leaf routing and row movement determine which physical relation receives row triggers.
- FK actions can introduce nested DELETE/UPDATE triggers on other relations.
- `pg_trigger_depth()` measures call-stack depth, not global business order.
- BEFORE triggers can mutate `NEW` or `RETURN NULL`; AFTER triggers can write outbox SQL that still rolls back on abort.
- Deferred constraint triggers can run statements later, right before commit.
- Outbox rows only count once committed; the worker sends the webhook **after commit**, needing retry and idempotency.
- Triggers sharing an event, timing, and relation do run in alphabetical name order, but that governs only **one slice** of the full execution graph.

---

## 45. PostgreSQL Reference Documentation

Always consult the official documentation matching your server's **actual major version** when finalizing production designs:

- [PostgreSQL — Overview of Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html): BEFORE/AFTER, row/statement, transition relations, partitioning, and trigger ordering.
- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): timing, events, `WHEN`, constraint triggers, `REFERENCING`, and ordering among triggers of the same type.
- [PostgreSQL — PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): `NEW`, `OLD`, `TG_OP`, `TG_WHEN`, and return semantics.
- [PostgreSQL — Trigger Procedures](https://www.postgresql.org/docs/current/triggers.html): trigger functions and invocation mechanics.
- [PostgreSQL — System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html): `tgenabled`, `tgisinternal`, `tgfoid`, `tgrelid`.
- [PostgreSQL — CREATE TABLE / Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): FOREIGN KEY, CASCADE, and constraints.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): switching from DEFERRED to IMMEDIATE.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO UPDATE` and `RETURNING`.
- [PostgreSQL — MERGE](https://www.postgresql.org/docs/current/sql-merge.html): multi-action DML and version-specific trigger effects.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): row routing and partitioned trigger behavior.
- [PostgreSQL — LISTEN / NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html): transaction-aware notifications and limitations.
- [PostgreSQL — Sequence Manipulation Functions](https://www.postgresql.org/docs/current/functions-sequence.html): non-rollbackable `nextval()`.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): inspecting plans and measuring trigger overhead appropriately.
- [PostgreSQL — Function Security](https://www.postgresql.org/docs/current/perm-functions.html): privileges and `SECURITY DEFINER` hardening.

`/current/` URLs reflect the latest PostgreSQL release and may differ from your deployed version. In particular, verify `MERGE`, transition tables, partitioned triggers, `ON CONFLICT` concurrency nuances, and privilege rules against your target major version.

---

## 46. Summary

**Trigger ordering, recursion, and side-effect loops are three facets of a single reality: one SQL statement can trigger far more work than the outer command suggests.** To design safely, separate each layer:

1. **Phase ordering:** BEFORE STATEMENT, BEFORE ROW, row modification, AFTER ROW, and AFTER STATEMENT form the core sequence. Deferred constraint triggers can run later still.
2. **Name ordering:** triggers sharing timing, event, and relation fire alphabetically by trigger name; naming determines how later BEFORE triggers observe `NEW`.
3. **No default business row order:** multi-row statements do not guarantee row triggers fire in primary-key or `INSERT` order.
4. **Return semantics:** BEFORE ROW can mutate `NEW` or `RETURN NULL` to skip a row; AFTER ROW return values are ignored; view `INSTEAD OF` triggers must run the underlying DML themselves.
5. **Nested DML:** SQL inside triggers, FK cascades, UPSERTs, partition movement, or view `INSTEAD OF` triggers can fire more triggers and build recursive graphs.
6. **Recursion requires data-driven termination:** use `IS DISTINCT FROM`, `WHEN`, conditional UPDATEs, one-way projections, and idempotency. `pg_trigger_depth()` helps debugging, not replacing business guards.
7. **Set timestamps in BEFORE ROW via `NEW`:** avoid self-updating the same row in AFTER without a clear termination design.
8. **`UPDATE OF` does not mean "value changed":** it checks columns listed in `SET`. Compare values with `WHEN OLD.field IS DISTINCT FROM NEW.field`.
9. **Statement-level triggers run even on 0 affected rows:** never treat statement trigger invocation as proof that INSERT/UPDATE/DELETE modified rows.
10. **Transition tables** enable set-based aggregation in supported AFTER STATEMENT triggers, cutting row-by-row DML and lock contention.
11. **Deferred constraint triggers** follow distinct timing; `WHEN` is checked at event time while the function can be queued until later.
12. **Audits must respect transaction boundaries:** in-trigger SQL audits/outboxes roll back with the transaction; AFTER does not mean after-commit.
13. **External side effects do not roll back with PostgreSQL:** HTTP/email/webhooks belong in a transactional outbox with workers, idempotency, and retries; `NOTIFY` is only a non-durable wake-up signal.
14. **Sequence ID gaps are normal:** `nextval()` never rolls back; do not treat gaps as proof of lost data.
15. **Diagnostics and maintenance:** inspect `pg_trigger`/`pg_get_triggerdef`, use bounded `pg_trigger_depth()` logging, measure `EXPLAIN ANALYZE` in lab, and monitor locks, WAL, and audit drift.
16. **Never fix bugs by disabling all triggers:** `DISABLE TRIGGER ALL` or altering replication roles bypasses FKs, audits, and invariants.
17. **Privileges and correctness:** `SECURITY DEFINER` trigger functions require strict hardening; never abuse privileges to paper over logic bugs.

Compact design workflow: **define events/timings -> list triggers by name and relation -> map all nested DML edges -> prove termination -> eliminate reverse/redundant UPDATEs -> keep DB side effects transactional or in an outbox -> design idempotency -> test 0/1/many rows, UPSERT, FK cascades, partitions, rollbacks, and concurrency -> deploy with catalog snapshots, monitoring, and a rollback plan**.
