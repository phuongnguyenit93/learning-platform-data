# Constraint Triggers and Deferred Checks in PostgreSQL

Suppose a budgeting application stores the **approved total budget** in a `batches` table and **individual line allocations** in an `allocations` table. Once a budget batch is `sealed`, business rules require:

**The sum of amounts across all allocation lines belonging to that batch must equal the exact approved total.**

The challenge is that an application may need to execute multiple SQL statements inside a single transaction:

```sql
BEGIN;

-- Step 1: increase the first allocation from 60 to 70.
UPDATE ... SET amount = 70 WHERE line_id = 1001;

-- Mid-transaction: allocation sum is temporarily 110,
-- while the sealed budget remains 100.

-- Step 2: decrease the second allocation from 40 to 30.
UPDATE ... SET amount = 30 WHERE line_id = 1002;

-- Before COMMIT: total is back to 100.
COMMIT;
```

If "sum must equal budget" were checked **immediately after each statement**, the first UPDATE would be rejected. Yet if checked **when the transaction finishes**, both steps can execute and the transaction still guarantees a valid final state.

PostgreSQL provides a mechanism for this need: **deferrable constraint triggers**, combined with `SET CONSTRAINTS`.

```text
        BEGIN TRANSACTION
               |
               v
        UPDATE allocation A
        Temporary total = 110
               |
               +---- IMMEDIATE check ------> ERROR at end of statement
               |
               +---- DEFERRED check -------> Queue pending event
                                                |
                                                v
                                       UPDATE allocation B
                                       Total returns to 100
                                                |
                                                v
                                              COMMIT
                                                |
                                                v
                                      Run deferred checks
                                                |
                                      +---------+---------+
                                      |                   |
                                    Valid              Invalid
                                      |                   |
                                      v                   v
                                    COMMIT             ROLLBACK
```

This lesson belongs to the **Triggers and Rules** chapter in the *Database Engine Relational PostgreSQL* module. You will learn:

- What a constraint trigger is and how it differs from an ordinary trigger.
- `DEFERRABLE`, `NOT DEFERRABLE`, `INITIALLY IMMEDIATE`, and `INITIALLY DEFERRED`.
- `AFTER ROW` execution timing and how `SET CONSTRAINTS ... IMMEDIATE/DEFERRED` affects pending events.
- Key restrictions: `WHEN` is evaluated immediately; constraint triggers cannot be `BEFORE`, `STATEMENT`, or transition-table triggers.
- A two-table example enforcing allocation totals, covering `INSERT`, `UPDATE`, `DELETE`, moving lines across groups, and rollbacks.
- Differences between custom constraint triggers and `DEFERRABLE` `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, and `EXCLUDE` constraints.
- Cases where deferral **cannot** be used, such as `CHECK` and `NOT NULL`.
- Concurrency, write skew, row locks, isolation levels, N-invocation check overhead, and operational planning.
- Practice exercises with answers and a design checklist.

> **Important:** "Deferring" does not mean "skipping checks." The constraint must still hold when pending checks execute. If violated at transaction end, `COMMIT` fails and the transaction's changes are not persisted.

---

## 1. Problem Statement: Valid per Statement or Valid at Commit?

### 1.1. System invariants

An *invariant* is a condition that must hold at specified points in time. For example:

```text
A sealed budget batch:
    expected_total = SUM(amount of all allocations)
```

If the budget is 100:

```text
Allocation A = 60
Allocation B = 40
-----------------
SUM          = 100  -> valid
```

When a user reallocates:

```text
Step 1:
    A = 70
    B = 40
    SUM = 110 -> temporarily invalid

Step 2:
    A = 70
    B = 30
    SUM = 100 -> valid at commit
```

In a transaction with two UPDATE statements, uncommitted changes are generally invisible to other transactions under PostgreSQL MVCC rules. Therefore, some workflows allow states that **temporarily violate a constraint mid-transaction**, provided every check passes by transaction end.

### 1.2. Three ways to handle this

1. **Design a single atomic SQL statement** so no invalid intermediate state exists between statements; usually the simplest option when feasible.
2. **Use a native DEFERRABLE constraint** if the invariant is uniqueness, foreign key, exclusion, or another case directly supported by PostgreSQL.
3. **Use a deferrable constraint trigger** when business validation needs custom SQL, typically spanning multiple rows or tables, and cannot be expressed with native constraints.

Do not jump to triggers when `NOT NULL`, `CHECK`, `UNIQUE`, or `FOREIGN KEY` suffices. Native constraints are clearer, better optimized, and easier to operate.

### 1.3. Deferral is not an isolation level

`DEFERRABLE` controls **when checks execute**; it does not automatically:

- Raise the isolation level.
- Lock all related rows.
- Guarantee concurrent transactions see each other's uncommitted changes.
- Turn a `SELECT SUM(...)` into an infallible check immune to write skew.

Especially for multi-row and multi-table invariants, design concurrency separately rather than merely adding `INITIALLY DEFERRED`.

---

## 2. Ordinary Triggers vs. Constraint Triggers

### 2.1. Ordinary triggers

A standard PostgreSQL trigger is declared as:

```sql
CREATE TRIGGER ordinary_audit
AFTER UPDATE ON some_table
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
```

A regular `AFTER ROW` trigger executes under standard trigger mechanics after the statement; it has no `SET CONSTRAINTS` timing control.

Depending on event and trigger type, PostgreSQL also supports `BEFORE`, `AFTER`, `INSTEAD OF`, `FOR EACH STATEMENT`, and `FOR EACH ROW`.

### 2.2. Constraint triggers

A constraint trigger is declared with:

```sql
CREATE CONSTRAINT TRIGGER some_constraint_trigger
AFTER INSERT OR UPDATE OR DELETE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
```

Essential properties:

- Uses **`CREATE CONSTRAINT TRIGGER`** syntax.
- Must be **`AFTER`**.
- Must be **`FOR EACH ROW`**.
- Attaches to a **regular table**, not a foreign table or view.
- Calls a function returning **`trigger`**, following standard PL/pgSQL trigger function rules.
- With `DEFERRABLE`, invocation timing can be controlled via `SET CONSTRAINTS`.
- The function is expected to **raise an exception** when the constraint is violated.

### 2.3. "Constraint" does not make PostgreSQL understand business logic automatically

If the function merely contains:

```sql
BEGIN
    RETURN NEW;
END;
```

then the trigger **performs no check whatsoever** on the numbers. `CREATE CONSTRAINT TRIGGER` provides only the **firing and timing mechanism**; the author must implement the actual validation logic.

### 2.4. Comparison table

| Feature | Ordinary trigger | Constraint trigger |
|---|---|---|
| Creation keyword | `CREATE TRIGGER` | `CREATE CONSTRAINT TRIGGER` |
| `BEFORE ROW` | Yes | No |
| `AFTER ROW` | Yes | Yes, mandatory |
| `AFTER STATEMENT` | Yes | No |
| `INSTEAD OF` on views | Yes | No |
| `SET CONSTRAINTS` timing control | No | Yes, if `DEFERRABLE` |
| `REFERENCING NEW TABLE/OLD TABLE` | Yes, for eligible AFTER triggers | Cannot be used with constraint triggers |
| Assigning `NEW.column` before storage | Suited for BEFORE triggers | No, because it runs AFTER |
| Checking invariants at transaction end | Not directly via `SET CONSTRAINTS` | Yes |
| Per-row invocation cost risk | Yes | Yes; events can accumulate until commit |

### 2.5. Triggers and rules are not the same thing

A **Rule** in PostgreSQL is a mechanism that **rewrites** SQL queries before execution planning. Triggers react to events produced during DML execution according to trigger kind. A rule is not equivalent to an end-of-transaction constraint; never use `CREATE RULE` as a substitute for a deferrable constraint trigger.

In most modern invariant-checking scenarios, prefer native constraints, triggers, or explicit transaction protocols over complex, hard-to-predict rules.

---

## 3. DEFERRABLE and Initial Constraint Mode

### 3.1. Three modes to know

| Declaration | Meaning |
|---|---|
| `NOT DEFERRABLE` | Cannot be deferred; cannot be switched to DEFERRED via `SET CONSTRAINTS` |
| `DEFERRABLE INITIALLY IMMEDIATE` | Can be deferred, but defaults to checking at the end of each statement |
| `DEFERRABLE INITIALLY DEFERRED` | Can be deferred, and defaults to checking at transaction end |

Example:

```sql
CREATE CONSTRAINT TRIGGER sample_guard
AFTER UPDATE ON some_table
DEFERRABLE INITIALLY IMMEDIATE
FOR EACH ROW
EXECUTE FUNCTION sample_function();
```

This trigger checks after each UPDATE by default, yet a transaction can switch it to deferred mode.

### 3.2. Do not confuse DEFERRABLE and INITIALLY DEFERRED

`DEFERRABLE` means **the timing is allowed to change**; `INITIALLY DEFERRED` sets the **default mode at transaction start**.

Both configurations:

```sql
DEFERRABLE INITIALLY IMMEDIATE
```

and:

```sql
DEFERRABLE INITIALLY DEFERRED
```

can toggle between `IMMEDIATE` and `DEFERRED` inside a transaction using `SET CONSTRAINTS`.

### 3.3. "IMMEDIATE" does not always mean checked mid-row

Under the general `SET CONSTRAINTS` contract, an `IMMEDIATE` constraint is checked at **the end of the statement**. For some non-deferrable constraints like unique indexes, enforcement details can happen earlier. Do not assume every constraint category checks at the exact same per-tuple instant.

For an `AFTER ROW` constraint trigger, in immediate mode its queued events run at statement end; in deferred mode they wait until commit (or explicit switch to immediate).

### 3.4. Events are still recorded

`INITIALLY DEFERRED` does not mean PostgreSQL forgets changes. On eligible INSERT/UPDATE/DELETE:

1. An event occurs.
2. PostgreSQL evaluates whether to queue it for the trigger.
3. Execution of the function waits until transaction end if deferred.
4. When checked, the function validates the invariant and raises an error if violated.

"Which events trigger checks" is still governed by event declaration, `WHEN`, and function logic.

---

## 4. SET CONSTRAINTS: Switching Modes Inside a Transaction

### 4.1. Syntax

```sql
SET CONSTRAINTS ALL DEFERRED;
SET CONSTRAINTS ALL IMMEDIATE;

SET CONSTRAINTS constraint_name DEFERRED;
SET CONSTRAINTS constraint_name IMMEDIATE;
```

Multiple names can be listed:

```sql
SET CONSTRAINTS guard_a, guard_b DEFERRED;
```

Constraint names may be **schema-qualified**.

### 4.2. Scoped only to the current transaction

```sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
-- Execute DML steps.
COMMIT;
```

Once the transaction finishes, the next transaction starts back at each constraint's `INITIALLY ...` default.

Calling `SET CONSTRAINTS` outside a transaction block produces a warning and does not persist as a session-wide setting.

### 4.3. ALL can affect other constraints

`SET CONSTRAINTS ALL DEFERRED` defers every deferrable constraint in the transaction, including eligible FK, unique, and exclusion constraints. Do not blindly use `ALL` when you only intend to defer one business trigger.

In critical migrations or stored procedures, prefer **naming the exact constraints** you want to change.

### 4.4. DEFERRED -> IMMEDIATE applies retroactively

Important behavior:

```sql
BEGIN;

SET CONSTRAINTS some_guard DEFERRED;

-- Modify data, accumulating pending checks.

SET CONSTRAINTS some_guard IMMEDIATE;

COMMIT;
```

When switching from deferred to immediate, PostgreSQL **immediately runs all pending deferred checks**. If any fail, the `SET CONSTRAINTS ... IMMEDIATE` statement itself throws an error and fails to switch modes.

This is useful for "settling" invariants at a checkpoint before commit:

```text
BEGIN
    |
    v
Multiple temporarily invalid UPDATEs
    |
    v
Final corrective UPDATE
    |
    v
SET CONSTRAINTS ... IMMEDIATE
    |
    +--> PASS: continue other work and COMMIT
    |
    +--> FAIL: handle failed transaction / ROLLBACK
```

### 4.5. IMMEDIATE -> DEFERRED cannot "undo" a check that already failed

If a statement already failed in immediate mode and put the transaction into an aborted state, running `SET CONSTRAINTS ... DEFERRED` afterwards cannot rescue the previous statement. You must set `DEFERRED` **before** issuing DML that produces intermediate invalid states.

### 4.6. Names are not always unique within a schema

PostgreSQL allows the same constraint name on different tables. Thus `SET CONSTRAINTS schema.name` can affect multiple identically named constraints in that schema per resolution rules. Choose distinct names and avoid reusing them for unrelated domains.

---

## 5. Practice Lab: Budget Batches and Allocations

We will write a **deferrable constraint trigger** to enforce a realistic invariant.

### 5.1. Problem requirements

- Each batch has a unique `batch_id`.
- `status` may only be `draft` or `sealed`.
- `expected_total` is the expected total budget, non-negative.
- Every allocation belongs to an existing batch.
- Allocation `amount` is non-negative.
- While a batch is `draft`, allocation sums do not have to match `expected_total`.
- When a batch is `sealed`, the sum of allocations **must equal `expected_total`**.
- A sealed batch with `expected_total = 0` and zero allocations is valid in this lab model. If business rules require at least one line, add a `COUNT(*) > 0` check.

### 5.2. Create a dedicated schema

```sql
CREATE SCHEMA deferred_trigger_lab;
```

This schema is for a test database. If it already exists in a shared database, do not wipe it with `DROP SCHEMA ... CASCADE`; use a fresh lab database.

### 5.3. Create the batches table

```sql
CREATE TABLE deferred_trigger_lab.batches (
    batch_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'sealed')),
    expected_total NUMERIC(18,2) NOT NULL
        CHECK (expected_total >= 0),
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT transaction_timestamp()
);
```

Here `batch_id` is supplied explicitly so examples have predictable IDs. In production, use identity/sequences or UUIDs.

### 5.4. Create the allocations table

```sql
CREATE TABLE deferred_trigger_lab.allocations (
    line_id BIGINT PRIMARY KEY,
    batch_id BIGINT NOT NULL
        REFERENCES deferred_trigger_lab.batches(batch_id)
        ON DELETE CASCADE,
    line_name TEXT NOT NULL,
    amount NUMERIC(18,2) NOT NULL
        CHECK (amount >= 0)
);
```

**Important note:** `CHECK (amount >= 0)` validates **a single row** and cannot be deferred. The rule "sum of allocations = expected_total" reads **multiple rows**, so we enforce it with a custom check function.

### 5.5. Add an index to look up allocations by batch

```sql
CREATE INDEX allocations_batch_id_idx
ON deferred_trigger_lab.allocations (batch_id);
```

The verification function runs:

```sql
SELECT SUM(amount)
FROM deferred_trigger_lab.allocations
WHERE batch_id = ...;
```

An index on `batch_id` reduces row reads when the allocations table is large and individual batches are small fractions of the table. On tiny tables, the planner may still prefer a Seq Scan as cheaper.

### 5.6. Relationship diagram

```text
deferred_trigger_lab.batches
  batch_id (PK) ─────────────────────┐
  tenant_id                          │
  status = draft | sealed            │
  expected_total                     │
                                     │ FK
                                     ▼
deferred_trigger_lab.allocations
  line_id (PK)
  batch_id (FK)
  line_name
  amount

Invariant:
  IF batches.status = 'sealed'
  THEN batches.expected_total
       = COALESCE(SUM(allocations.amount), 0)
```

---

## 6. Writing the Invariant Verification Function

We isolate business logic into a helper function so multiple triggers can call it and we can test it manually when needed.

### 6.1. Function checking a single batch

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.assert_sealed_batch_total(
        p_batch_id BIGINT
    )
RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    v_status TEXT;
    v_expected NUMERIC;
    v_actual NUMERIC;
BEGIN
    SELECT b.status, b.expected_total
    INTO v_status, v_expected
    FROM deferred_trigger_lab.batches AS b
    WHERE b.batch_id = p_batch_id;

    -- Parent row was deleted within the transaction:
    -- no sealed batch remains to check.
    IF NOT FOUND THEN
        RETURN;
    END IF;

    -- Draft batches are allowed to be unbalanced.
    IF v_status <> 'sealed' THEN
        RETURN;
    END IF;

    SELECT COALESCE(SUM(a.amount), 0)
    INTO v_actual
    FROM deferred_trigger_lab.allocations AS a
    WHERE a.batch_id = p_batch_id;

    IF v_actual IS DISTINCT FROM v_expected THEN
        RAISE EXCEPTION
            'Batch %: expected total %, actual allocation total %',
            p_batch_id, v_expected, v_actual
            USING
                ERRCODE = '23514',
                CONSTRAINT = 'batch_total_matches_allocations';
    END IF;
END;
$function$;
```

### 6.2. Why check NOT FOUND?

When a parent batch is deleted and its allocations are deleted via `ON DELETE CASCADE`, queued trigger events may still fire at transaction end, at which point the parent no longer exists.

That is valid in this model: if no sealed parent exists, there is no invariant left to enforce for that batch. The function simply executes `RETURN;` to skip.

Never replace `IF NOT FOUND` with buggy checks like `IF v_status = NULL THEN`.

### 6.3. Why check only when sealed?

In `draft` status, users are still adding and removing allocations. Checking amounts in every state would needlessly block transactions that create a batch before inserting lines.

`IF v_status <> 'sealed' THEN RETURN; END IF;` is our lab's business rule, not a mandatory feature of constraint triggers.

### 6.4. COALESCE(SUM(...), 0)

`SUM(amount)` over zero rows returns `NULL`, not 0. Because our lab defines zero allocations as a sum of 0, we write:

```sql
COALESCE(SUM(amount), 0)
```

If business rules require a sealed batch to **have at least one line**, check `COUNT(*)` or `EXISTS` as well.

### 6.5. IS DISTINCT FROM suits data validation

Although `v_actual` and `v_expected` are non-NULL in this lab thanks to `COALESCE` and `NOT NULL`, `IS DISTINCT FROM` clearly expresses "the two values must be equal, even if types or nullability change later."

In models allowing NULL, `<>` evaluates to UNKNOWN and fails to throw when one side is NULL. Using a NULL-safe comparison is good defensive practice.

### 6.6. SQLSTATE when raising errors

`ERRCODE = '23514'` is `check_violation`. We use it for a custom business invariant check. `CONSTRAINT = 'batch_total_matches_allocations'` sets a diagnostic label; it does not mean PostgreSQL created a native SQL `CHECK` constraint of that name.

Applications should inspect `SQLSTATE` and structured error fields rather than parsing English text messages.

### 6.7. A plain function does not run automatically

At this point, the function is just a callable helper in the database:

```sql
SELECT deferred_trigger_lab.assert_sealed_batch_total(101);
```

It validates batch 101 if present, yet **does not run automatically** after INSERT/UPDATE/DELETE. We must attach triggers to all operations that can affect the invariant.

---

## 7. Writing a Shared Trigger Function for Both Tables

The invariant can be affected when modifying:

- **Batch header:** `status` or `expected_total` changes.
- **Allocation:** inserting a line, editing `amount`, moving `batch_id` to another batch, or deleting a line.
- **Deleted header:** related allocations may be deleted via FK CASCADE.

Therefore we must attach triggers to **both tables**.

### 7.1. Trigger function

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            NEW.batch_id
        );
        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            OLD.batch_id
        );
        RETURN OLD;

    ELSIF TG_OP = 'UPDATE' THEN
        -- When a line moves from an old batch to a new batch:
        -- both batches may now have an invalid total.
        IF OLD.batch_id IS DISTINCT FROM NEW.batch_id THEN
            PERFORM deferred_trigger_lab.assert_sealed_batch_total(
                OLD.batch_id
            );
        END IF;

        PERFORM deferred_trigger_lab.assert_sealed_batch_total(
            NEW.batch_id
        );
        RETURN NEW;
    END IF;

    RAISE EXCEPTION
        'Unsupported trigger event %', TG_OP
        USING ERRCODE = '22023';
END;
$function$;
```

### 7.2. Why use both NEW and OLD?

For row-level triggers:

| Event | Relevant row record |
|---|---|
| `INSERT` | `NEW` |
| `UPDATE` | `OLD` and `NEW` |
| `DELETE` | `OLD` |

`DELETE` has no `NEW` row like INSERT. Never write a trigger function that blindly reads `NEW.batch_id` without branching on `TG_OP`.

### 7.3. Updating batch_id must check both groups

Suppose allocation 1002 moves from batch 101 to batch 102:

```text
Batch 101: loses line 1002's amount
Batch 102: gains line 1002's amount
```

Checking only `NEW.batch_id` would leave batch 101 unbalanced and unchecked.

Therefore on `UPDATE`, the function validates **the old batch if the ID changed**, plus the new batch.

### 7.4. AFTER triggers cannot modify NEW

`RETURN NEW` and `RETURN OLD` reflect clean function structure, yet in an **AFTER ROW trigger** the return value does not alter the persisted row.

If the goal is normalizing `NEW.amount` before saving, that belongs in a `BEFORE` trigger, constraint, or SQL expression. Constraint triggers here strictly **verify and reject invalid transactions**.

### 7.5. Deferred functions must inspect current data

This trigger function does **not** rely on an old event's `NEW.amount` to infer totals; it queries:

```sql
SELECT COALESCE(SUM(amount), 0)
FROM deferred_trigger_lab.allocations
WHERE batch_id = ...;
```

Because the same row may be updated multiple times within a transaction, an earlier queued event carries an outdated snapshot of `NEW`. Re-reading the **current observable state at execution time** ensures a valid sequence of edits is never rejected due to stale intermediate values.

---

## 8. Creating Two INITIALLY DEFERRED Constraint Triggers

### 8.1. Trigger for the batch header

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_header
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.batches
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

### 8.2. Trigger for allocations

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_lines
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.allocations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

Both triggers share **the same function** because both tables have `batch_id` and share one invariant. This reduces duplication; in larger systems you can separate functions if event semantics diverge.

### 8.3. Why not attach the trigger only to allocations?

Suppose batch 101 is sealed at 100, and then:

```sql
UPDATE deferred_trigger_lab.batches
SET expected_total = 120
WHERE batch_id = 101;
```

Zero allocations changed, yet the invariant is broken. With a trigger only on `allocations`, editing the header **emits no check event**. Hence we need a trigger on `batches`.

### 8.4. Why not attach the trigger only to batches?

Suppose:

```sql
UPDATE deferred_trigger_lab.allocations
SET amount = 999
WHERE line_id = 1001;
```

The header did not change, so the `batches` trigger does not fire. Hence we need a trigger on `allocations`.

### 8.5. Why include INSERT, UPDATE, and DELETE?

| Event | Can affect the total? |
|---|---|
| INSERT sealed batch | Introduces an invariant that must hold at commit |
| UPDATE batch status/expected_total | Yes |
| DELETE batch | Batch disappears; queued events must handle `NOT FOUND` |
| INSERT allocation | Yes |
| UPDATE allocation amount/batch_id | Yes |
| DELETE allocation | Yes |

If business operations allow `TRUNCATE` on the tables, that is **a separate statement type** and does not fire row-level DELETE triggers per row. Restrict `TRUNCATE` privileges and manage migrations/bulk loads properly; **row-level constraint triggers do not guard against TRUNCATE**.

### 8.6. Why INITIALLY DEFERRED?

We want normal transactions to be able to:

1. Edit multiple allocation lines.
2. Temporarily leave the total unbalanced.
3. Rebalance before committing.
4. Commit only if the final invariant holds.

If most workflows perform single-statement updates and prefer immediate failure detection, choose `DEFERRABLE INITIALLY IMMEDIATE` and call `SET CONSTRAINTS ... DEFERRED` only in multi-step workflows.

---

## 9. Experiment A: Creating a Sealed Batch and Lines in One Transaction

### 9.1. Create the batch before its allocations

```sql
BEGIN;

INSERT INTO deferred_trigger_lab.batches
    (batch_id, tenant_id, status, expected_total, description)
VALUES
    (101, 1, 'sealed', 100.00, 'November allocation');
```

Immediately after INSERT, batch 101 is sealed with an allocation sum of 0. The invariant is **temporarily** broken. Because the trigger is `INITIALLY DEFERRED`, the check waits until transaction end instead of failing immediately.

### 9.2. Insert balanced lines

```sql
INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (1001, 101, 'Infrastructure', 60.00),
    (1002, 101, 'Support', 40.00);

COMMIT;
```

Within the same transaction, the final sum is 100. When deferred checks execute, batch 101 satisfies the invariant and commits cleanly (assuming no other constraint error).

### 9.3. Verify the result

```sql
SELECT
    b.batch_id,
    b.status,
    b.expected_total,
    COALESCE(SUM(a.amount), 0) AS actual_total
FROM deferred_trigger_lab.batches AS b
LEFT JOIN deferred_trigger_lab.allocations AS a
    ON a.batch_id = b.batch_id
WHERE b.batch_id = 101
GROUP BY b.batch_id, b.status, b.expected_total;
```

Expected output:

```text
batch_id | status | expected_total | actual_total
---------+--------+----------------+-------------
101      | sealed | 100.00         | 100.00
```

### 9.4. Deferral allows "fixing inside the transaction," not "persisting bad data"

If you ended the transaction right after inserting the sealed batch of 100 without adding allocations, `COMMIT` would throw an error from the trigger. The entire transaction fails to commit, preventing an invalid sealed batch from being saved.

---

## 10. Experiment B: Updating Two Lines—Temporarily Invalid, Then Valid

### 10.1. Initial state

```text
line 1001 = 60.00
line 1002 = 40.00
expected_total = 100.00
```

### 10.2. Modify across two statements

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 70.00
WHERE line_id = 1001;

-- Temporary total = 70 + 40 = 110

UPDATE deferred_trigger_lab.allocations
SET amount = 30.00
WHERE line_id = 1002;

-- Total is back to = 70 + 30 = 100

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

-- Pending checks ran and all passed.

ROLLBACK;
```

Here we finish with `ROLLBACK` to **preserve the 60/40 seed data** for subsequent experiments. In a real transaction wanting to persist 70/30, run `COMMIT` instead of `ROLLBACK` once checks pass.

### 10.3. Observing between the two UPDATEs

Inside the transaction, you can run:

```sql
SELECT
    COALESCE(SUM(amount), 0) AS current_total
FROM deferred_trigger_lab.allocations
WHERE batch_id = 101;
```

After the first UPDATE, your own transaction sees 110. The constraint has not fired yet because it is deferred.

After the second UPDATE, the sum is 100. Calling `SET CONSTRAINTS ... IMMEDIATE` evaluates the queued events and succeeds.

### 10.4. Do not think other transactions see 110

Other transactions cannot see **uncommitted** UPDATEs under standard PostgreSQL isolation levels. Allowing a temporary mid-transaction state does not expose invalid data to other sessions.

Still, visibility across concurrent transactions depends on isolation level, snapshots, and commit timing; never use deferred triggers as a substitute for transaction control.

---

## 11. Experiment C: Errors Deferred Until Transaction End

### 11.1. Error is not raised right after one UPDATE

Test separately in the lab database:

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 75.00
WHERE line_id = 1001;

-- Current sum is 75 + 40 = 115, yet the trigger is still deferred.

-- Uncomment the next line to observe the error right at COMMIT:
-- COMMIT;

ROLLBACK;
```

If `COMMIT` runs, the constraint trigger executes and raises an exception because `expected_total` 100 differs from `actual_total` 115. The transaction does not commit.

### 11.2. Catching errors early with SET CONSTRAINTS IMMEDIATE

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET amount = 75.00
WHERE line_id = 1001;

-- Uncomment the next lines to test:
-- SET CONSTRAINTS
--     deferred_trigger_lab.batch_total_guard_lines
-- IMMEDIATE;

ROLLBACK;
```

When `SET CONSTRAINTS ... IMMEDIATE` is uncommented, PostgreSQL evaluates pending events **right at the `SET CONSTRAINTS` statement** and throws an error before `COMMIT` while the total is 115.

**Lab note:** once a statement throws an exception inside a normal transaction, the session enters an aborted transaction state and needs `ROLLBACK` before continuing. Never mix intentional failure examples into a non-fault-tolerant migration script.

### 11.3. Why not just use an IF check in the application?

The application can check totals before COMMIT, yet:

- Another code path might forget to check.
- Another SQL session might modify tables directly.
- A migration might update data.
- An earlier application-side check can go stale under concurrency.

Constraint triggers **bind validation to data changes inside the database**, while still requiring concurrency and privilege controls.

---

## 12. Experiment D: Draft Need Not Balance, Sealed Must Balance

### 12.1. Create a draft batch

```sql
INSERT INTO deferred_trigger_lab.batches
    (batch_id, tenant_id, status, expected_total, description)
VALUES
    (102, 1, 'draft', 200.00, 'Draft allocation');

INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (2001, 102, 'Planning', 10.00);
```

After both INSERTs, batch 102 is still `draft`, so total 10 is not required to match expected 200.

### 12.2. Seal the batch in a transaction

```sql
BEGIN;

UPDATE deferred_trigger_lab.batches
SET status = 'sealed'
WHERE batch_id = 102;

-- Current sum = 10, expected_total = 200.
-- Not rejected yet because the trigger is deferred.

INSERT INTO deferred_trigger_lab.allocations
    (line_id, batch_id, line_name, amount)
VALUES
    (2002, 102, 'Delivery', 190.00);

COMMIT;
```

At commit time, total 10 + 190 = 200; the sealed batch invariant passes.

### 12.3. Sealing without adding the missing amount

On another draft batch totaling 10, if you simply run `UPDATE status='sealed'` and `COMMIT` without adding 190, the deferred trigger rejects the transaction.

This illustrates two layers:

- `CHECK (status IN (...))` ensures status belongs to the allowed set.
- The constraint trigger enforces **the relationship among status, expected_total, and allocations**.

### 12.4. Deferral helps when adding lines and editing headers together

An existing sealed batch of 100 can simultaneously update `expected_total=120` and insert a 20 allocation in one transaction. As long as both complete before check time, the final state is valid.

---

## 13. Experiment E: Moving an Allocation to Another Batch

Assume the current state is:

```text
Batch 101:
  expected_total = 100
  allocations = 60 + 40

Batch 102:
  expected_total = 200
  allocations = 10 + 190
```

### 13.1. One operation modifying two groups

Move line 1002 worth 40 from batch 101 to batch 102:

```sql
BEGIN;

UPDATE deferred_trigger_lab.allocations
SET batch_id = 102
WHERE line_id = 1002;

-- Batch 101: total = 60
-- Batch 102: total = 240

UPDATE deferred_trigger_lab.batches
SET expected_total = 60
WHERE batch_id = 101;

UPDATE deferred_trigger_lab.batches
SET expected_total = 240
WHERE batch_id = 102;

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

-- Validated cleanly; ROLLBACK to keep original lab data.
ROLLBACK;
```

The trigger function in Section 7 checks both `OLD.batch_id` and `NEW.batch_id` when the ID changes, because **both the old and new groups** are affected.

### 13.2. What if it checked only the new group?

If the function only ran:

```sql
PERFORM assert_sealed_batch_total(NEW.batch_id);
```

then batch 101 would lose a line without being re-checked after the move. Missing `OLD` group keys is a classic event-coverage bug in multi-group triggers.

### 13.3. Updating a batch's primary key

In the lab, `batch_id` is a PRIMARY KEY referenced by an FK. Modifying a primary key follows referential-action rules. A constraint trigger on header UPDATE can check both OLD and NEW IDs, yet **does not replace FK rules**. Avoid mutating entity primary keys without a compelling need and explicit migration.

---

## 14. WHEN on Constraint Triggers: Evaluated Immediately, Not Deferred

This is a very easy technical detail to misunderstand.

### 14.1. WHEN syntax example

```sql
-- Conceptual example; DO NOT add another trigger onto the lab table:
--
-- CREATE CONSTRAINT TRIGGER sample_sealed_check
-- AFTER INSERT OR UPDATE
-- ON deferred_trigger_lab.batches
-- DEFERRABLE INITIALLY DEFERRED
-- FOR EACH ROW
-- WHEN (NEW.status = 'sealed')
-- EXECUTE FUNCTION
--     deferred_trigger_lab.enforce_batch_total_deferred();
```

### 14.2. When is WHEN evaluated?

On a constraint trigger, the `WHEN` expression is evaluated **immediately after the row operation**, when deciding whether to queue the event; it is **not deferred until transaction end**.

If `WHEN` is FALSE or NULL, the event is **never queued** to run the deferred function later.

### 14.3. Trap when state changes multiple times

Suppose:

```text
Transaction start: batch is draft
UPDATE 1: change expected_total while status is still draft
UPDATE 2: change status to sealed
UPDATE 3: edit an allocation
Transaction end: sealed, and total must be checked
```

If only a header trigger with `WHEN (NEW.status='sealed')` ran for UPDATE 2, the last event might catch this simple sequence. In more complex workflows, an overly narrow `WHEN` can drop events affecting the invariant—especially with `OLD`/`NEW` differences, DELETEs, group reassignments, or reverse state transitions.

### 14.4. Safe strategy in the lab

We **omitted WHEN** on both constraint triggers and let the function read the final state:

```sql
IF v_status <> 'sealed' THEN
    RETURN;
END IF;
```

This queues more events, yet avoids dropping checks due to a predicate that was false at DML time but true when the invariant must be evaluated.

### 14.5. WHEN can optimize, but must be proven safe

At scale, every queued row event consumes memory and work. Early filtering with `WHEN` reduces queued events. Before optimizing, verify:

- Which INSERT/UPDATE/DELETE events can break the invariant?
- What if `OLD` and `NEW` differ in status?
- What if a line changes groups?
- What if the header is deleted or replaced within the transaction?
- Could `WHEN` skip a critical intermediate transition?

Never write `WHEN` as if it were evaluated against end-of-transaction state.

---

## 15. AFTER ROW and Transition-Table Restrictions

### 15.1. Constraint triggers must be AFTER ROW

You cannot declare a constraint trigger as:

```sql
-- Invalid for CONSTRAINT TRIGGER:
-- CREATE CONSTRAINT TRIGGER ...
-- BEFORE INSERT ON ...
-- FOR EACH STATEMENT ...
```

Constraint triggers only support **AFTER ROW** on regular tables.

### 15.2. You cannot use REFERENCING NEW TABLE with constraint triggers

An ordinary `AFTER` trigger can use transition relations:

```sql
-- Ordinary trigger syntax, NOT a constraint trigger:
-- CREATE TRIGGER ...
-- AFTER UPDATE ON some_table
-- REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
-- FOR EACH STATEMENT
-- EXECUTE FUNCTION ...;
```

Transition tables expose the statement's changed row sets. However, PostgreSQL **forbids combining `REFERENCING` transition relations with constraint triggers**.

### 15.3. Performance consequence

A statement updating 50,000 allocations queues 50,000 row-level events. When deferred, the function executes **50,000 times for the same batch** at transaction end.

Every execution re-runs `SUM(amount)`. This **repeated work** becomes very expensive when batches contain many allocations.

### 15.4. No automatic deduplication by batch

PostgreSQL does not collapse 50,000 events into a single `CHECK batch 101` just because they share the same parent ID. Design functions with that cost in mind.

### 15.5. Choosing the right optimization trade-offs

Alternative architectures:

- Issue **one atomic SQL statement** updating the whole batch, validating at statement end with an eligible ordinary trigger.
- Maintain a per-batch summary row updated atomically and validated at transaction end.
- Track "dirty" batches and run a single validation step before commit under a managed transaction protocol.
- Funnel all batch updates through a single database function rather than arbitrary ad-hoc writes.
- If the invariant can be expressed as a native constraint, switch to a native constraint.

Never remove validation triggers without ensuring every write path and transaction still enforces the invariant.

---

## 16. Constraint Triggers vs. CHECK

### 16.1. CHECK fits single-row conditions

```sql
CREATE TABLE deferred_trigger_lab.single_row_demo (
    id BIGINT PRIMARY KEY,
    amount NUMERIC NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'sealed'))
);
```

`CHECK (amount >= 0)` needs no trigger because it inspects only the row being written.

### 16.2. Do not use CHECK to SUM another table

An anti-pattern to avoid:

```sql
-- Do not build CHECK using a function scanning another table expecting
-- PostgreSQL to re-evaluate the invariant on every change:
--
-- CHECK (expected_total = custom_sum_allocations(batch_id))
```

PostgreSQL does not support `CHECK` constraints referencing other rows or tables as reliable cross-row constraints. Even if wrapping a table-reading function inside `CHECK` bypasses syntax errors, the database **never re-evaluates the parent's CHECK** when child rows change. This creates data corruption and dump/restore hazards.

### 16.3. CHECK is not DEFERRABLE

`CHECK` and `NOT NULL` are enforced immediately per PostgreSQL rules; they cannot be deferred with `SET CONSTRAINTS`.

Example:

```sql
-- Invalid:
-- CREATE TABLE bad_table (
--     amount numeric CHECK (amount >= 0)
--         DEFERRABLE INITIALLY DEFERRED
-- );
```

### 16.4. Never use a constraint trigger as an excuse to drop CHECK

The lab keeps:

```sql
amount NUMERIC(18,2) NOT NULL CHECK (amount >= 0)
```

to reject negative numbers immediately. The constraint trigger only adds the cross-row batch-total invariant. Both have distinct responsibilities.

---

## 17. Constraint Triggers vs. Deferrable UNIQUE and PRIMARY KEY

### 17.1. Native UNIQUE can be DEFERRABLE

Example of an ordered task-board card table:

```sql
CREATE TABLE deferred_trigger_lab.board_cards (
    card_id BIGINT PRIMARY KEY,
    board_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    CONSTRAINT board_position_unique
        UNIQUE (board_id, position)
        DEFERRABLE INITIALLY DEFERRED
);
```

### 17.2. Insert two positions

```sql
INSERT INTO deferred_trigger_lab.board_cards
    (card_id, board_id, position, title)
VALUES
    (1, 10, 1, 'First'),
    (2, 10, 2, 'Second');
```

### 17.3. Swap positions inside one transaction

```sql
BEGIN;

UPDATE deferred_trigger_lab.board_cards
SET position = CASE card_id
    WHEN 1 THEN 2
    WHEN 2 THEN 1
    ELSE position
END
WHERE board_id = 10
  AND card_id IN (1, 2);

COMMIT;
```

In the final state, no two cards share `(board_id, position)`. Because the unique constraint is deferred, PostgreSQL allows swaps whose intermediate step temporarily collides on key values.

### 17.4. Never write a table-scanning trigger to replace UNIQUE

When the requirement is simply "no two rows share the same key," use:

```sql
UNIQUE (...) DEFERRABLE
```

instead of:

```sql
-- Do not write manually:
-- SELECT COUNT(*) FROM table
-- WHERE key = NEW.key;
-- then RAISE EXCEPTION if > 1
```

Native unique constraints rely on specialized index and concurrency mechanics that a plain `SELECT` in a trigger **cannot replicate**.

### 17.5. PRIMARY KEY can also be DEFERRABLE

PostgreSQL allows `PRIMARY KEY` to be declared `DEFERRABLE` where appropriate. However, most entity identifiers never need in-transaction swapping; keep primary keys stable whenever possible.

### 17.6. ON CONFLICT and deferrable uniqueness

Important caveat: a deferrable unique constraint **cannot be used as a conflict arbiter** for `INSERT ... ON CONFLICT` the way a non-deferrable unique constraint/index can.

Never mark every unique key `DEFERRABLE` assuming existing upserts will keep working.

### 17.7. UNIQUE and NULL

Unique constraints have specific NULL rules; modern PostgreSQL also supports `NULLS NOT DISTINCT` when NULLs should be treated as equal. That is a matter of **key semantics**, not a reason to write custom constraint triggers.

---

## 18. Deferrable FOREIGN KEY and Insertion Order

### 18.1. Create a deferrable FK

```sql
CREATE TABLE deferred_trigger_lab.parent_nodes (
    node_id BIGINT PRIMARY KEY
);

CREATE TABLE deferred_trigger_lab.child_nodes (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT child_parent_fk
        FOREIGN KEY (parent_id)
        REFERENCES deferred_trigger_lab.parent_nodes(node_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

### 18.2. Insert child before parent in a transaction

```sql
BEGIN;

INSERT INTO deferred_trigger_lab.child_nodes
    (child_id, parent_id)
VALUES (1, 500);

-- FK is temporarily unsatisfied.

INSERT INTO deferred_trigger_lab.parent_nodes (node_id)
VALUES (500);

COMMIT;
```

With a deferred FK, parent 500 exists by commit time, so the transaction commits cleanly.

### 18.3. Why use a native FK?

Deferrable FKs are already implemented by PostgreSQL using internal referential integrity and constraint triggers. There is no reason to write a custom trigger checking:

```sql
EXISTS (SELECT 1 FROM parent WHERE parent_id = ...)
```

Native FKs provide standard locking, concurrency, and semantics that applications should leverage.

### 18.4. ON DELETE NO ACTION vs. RESTRICT

For foreign keys:

- `NO ACTION` allows the check to be deferred when the constraint is declared `DEFERRABLE`.
- `RESTRICT` is stricter and **cannot be deferred** the way `NO ACTION` can.
- `CASCADE`, `SET NULL`, and `SET DEFAULT` follow their own execution rules; do not assume `DEFERRABLE` defers cascade actions.

When business logic needs to delete or change a parent key and restore the link within the same transaction, select the right action and deferral policy.

### 18.5. Targeting the exact FK with SET CONSTRAINTS

```sql
BEGIN;

SET CONSTRAINTS
    deferred_trigger_lab.child_parent_fk
DEFERRED;

-- Changes temporarily lacking a parent.

ROLLBACK;
```

Since our lab declared the FK `INITIALLY DEFERRED`, the `SET` above illustrates naming syntax. You do not need to re-set the mode in every transaction when the default already matches.

---

## 19. EXCLUDE Constraints and Non-Overlapping Ranges

### 19.1. Scheduling problem

Two bookings for the same room must not overlap in time:

```text
room_id = 10
booking A: [09:00,10:00)
booking B: [09:30,10:30) -> overlap
```

This is a **time-range conflict** invariant and should not be checked manually with:

```sql
-- SELECT COUNT(*) WHERE room_id=... AND slot && ...
```

inside a regular trigger when a native exclusion constraint works.

### 19.2. Deferrable EXCLUDE example

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE deferred_trigger_lab.room_bookings (
    booking_id BIGINT PRIMARY KEY,
    room_id INTEGER NOT NULL,
    slot TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        slot WITH &&
    ) DEFERRABLE INITIALLY IMMEDIATE
);
```

`btree_gist` provides GiST operator classes for scalar equality inside exclusion constraints. Creating extensions requires appropriate privileges and environment setup.

### 19.3. Deferring when swapping bookings

```sql
BEGIN;

SET CONSTRAINTS ALL DEFERRED;

-- Perform schedule edits that temporarily overlap,
-- then ensure zero overlaps remain before COMMIT.

ROLLBACK;
```

In production, name the specific constraint instead of `ALL` if multiple deferrable constraints exist.

### 19.4. Why is EXCLUDE better than an overlap-checking trigger?

Exclusion constraints integrate directly with PostgreSQL indexes and concurrency control. A trigger running `SELECT ... WHERE slot && ...` on a normal snapshot suffers from race conditions. Always prefer the native constraint when it can express the invariant.

---

## 20. Constraint Triggers and Concurrency: The Biggest Hazard

### 20.1. Deferring does not make SELECTs lock data automatically

The lab's check function runs:

```sql
SELECT COALESCE(SUM(a.amount),0)
FROM deferred_trigger_lab.allocations AS a
WHERE a.batch_id = p_batch_id;
```

This is a plain aggregate SELECT. By itself, it does not carry the concurrency guarantees of a native unique or exclusion constraint.

### 20.2. Two transactions modifying the same group concurrently

Suppose multiple workers update allocations in the same batch simultaneously:

```text
Transaction A                    Transaction B
--------------------------       --------------------------
Read/compute on snapshot A       Read/compute on snapshot B
Modify allocation 1              Modify allocation 2
Deferred check near commit       Deferred check near commit
                                    |
Depending on timing and isolation: checks may not share
a consistent view of each other's effects.
```

The fact that both transactions "ran the check function" **does not prove the cross-row invariant holds under all concurrent schedules**.

### 20.3. Write skew

*Write skew* is a concurrency anomaly in which two transactions modify different rows based on reads that omit each other's uncommitted changes. Each transaction individually passes its validation, yet their combined committed state violates a cross-row invariant.

With constraint triggers executing `SELECT COUNT/SUM/EXISTS`, always assess this risk—especially under `READ COMMITTED` and `REPEATABLE READ`.

### 20.4. Locking the parent row as a coordination point

A common strategy is to **serialize all writers touching a batch via the shared parent row**:

```sql
BEGIN;

SELECT 1
FROM deferred_trigger_lab.batches
WHERE batch_id = 101
FOR UPDATE;

-- Only after acquiring the parent lock, modify allocations
-- and expected_total for batch 101.

COMMIT;
```

Crucially, **every write path must follow the same locking protocol** inside the transaction. If another job bypasses the lock, the guarantee breaks.

### 20.5. Do not try putting FOR UPDATE directly on SUM

PostgreSQL does not allow `FOR UPDATE` directly on aggregate queries to lock aggregated groups. Locking a **representative parent row** before updating is a cleaner, well-scoped strategy.

### 20.6. Multiple parents require a consistent lock order

When moving an allocation from batch A to batch B, both batches must be coordinated. If transaction 1 locks A then B while transaction 2 locks B then A, deadlocks occur.

A sound protocol should:

- Identify all affected parents.
- Lock them in a deterministic order, such as ascending `batch_id`.
- Keep transactions short.
- Handle deadlocks and serialization failures with controlled retries.

### 20.7. SERIALIZABLE and retries

`SERIALIZABLE` catches many anomalies if **all participating transactions** run at that isolation level, though PostgreSQL may abort a transaction with serialization failure `40001`. The application must safely retry **the entire transaction**.

Never use `SERIALIZABLE` as an excuse to skip designing write protocols and testing concurrency.

### 20.8. Defense at the data layer

For truly critical invariants such as financial balances or hard quotas:

1. Prefer native constraints and atomic SQL wherever possible.
2. Define explicit locking and isolation models.
3. Never trust a bare `SELECT COUNT(*)` trigger on its own.
4. Use idempotency keys for retried requests.
5. Maintain reconciliation checks and monitoring.

---

## 21. Why Can Many Deferred Events Be Very Expensive?

### 21.1. A multi-row update

```sql
UPDATE deferred_trigger_lab.allocations
SET amount = amount + 1
WHERE batch_id = 101;
```

If 10,000 rows match, the `AFTER ROW` constraint trigger queues 10,000 events.

### 21.2. Every event runs SUM once

In the current function:

```sql
PERFORM deferred_trigger_lab.assert_sealed_batch_total(...);
```

and `assert_sealed_batch_total` executes `SUM(amount)`. If 10,000 events check batch 101, that sum is recomputed 10,000 times.

### 21.3. The pending event queue consumes resources too

Deferring many events to commit increases:

- Memory and overhead to track queued trigger events.
- `COMMIT` latency while draining pending checks.
- Lock and transaction hold times.
- Risk of very late transaction rollbacks.

Never assume `INITIALLY DEFERRED` is a performance optimization; it primarily provides **check-timing semantics**.

### 21.4. Indexing helps, but does not eliminate repeated checks

`allocations_batch_id_idx` speeds up finding rows per batch, yet running it 10,000 times for the same batch still adds up to substantial total cost.

### 21.5. SET CONSTRAINTS time is also a hotspot

If a transaction queues huge numbers of events, `SET CONSTRAINTS ... IMMEDIATE` can take considerable time executing all pending checks. Never place it on a hot large-request path without benchmarking.

### 21.6. Write-pattern alternatives

When workloads routinely update thousands of rows per batch:

- Design one command updating the whole batch inside a transaction that locks the parent.
- Compute the total once before transitioning a batch to `sealed` if that is the only point where the invariant matters.
- Store totals in a summary row updated atomically, backed by periodic reconciliation.
- Use an ordinary statement-level trigger + transition table when commit-time deferral is unnecessary.
- Adjust the data model so native constraints can express the invariant.

Every option trades off correctness and latency; **never drop end-of-transaction checks if business rules require them**.

---

## 22. Inspecting Constraint Trigger Metadata

### 22.1. pg_trigger

```sql
SELECT
    t.tgname AS trigger_name,
    t.tgrelid::regclass AS table_name,
    t.tgdeferrable,
    t.tginitdeferred,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid IN (
    'deferred_trigger_lab.batches'::regclass,
    'deferred_trigger_lab.allocations'::regclass
)
  AND NOT t.tgisinternal
ORDER BY t.tgrelid::regclass::text, t.tgname;
```

Columns:

| Column | Meaning |
|---|---|
| `tgname` | Trigger name |
| `tgrelid` | Table owning the trigger |
| `tgdeferrable` | Whether it can be deferred |
| `tginitdeferred` | Whether it is deferred by default |
| `tgenabled` | Enabled mode under trigger firing rules |
| `tgisinternal` | System/internal trigger vs. user-defined trigger |

### 22.2. pg_constraint

User-defined constraint triggers are also recorded in `pg_constraint`:

```sql
SELECT
    conname,
    contype,
    conrelid::regclass AS table_name,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'deferred_trigger_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
```

Key `contype` values:

```text
c = CHECK
f = FOREIGN KEY
n = NOT NULL (on versions with corresponding catalog entries)
p = PRIMARY KEY
u = UNIQUE
x = EXCLUDE
t = user-defined constraint trigger
```

Never treat catalog queries as a substitute for testing the invariant; metadata confirms definitions and modes, not whether your function logic holds under every concurrent schedule.

### 22.3. Verify the right function is attached

```sql
SELECT
    t.tgname,
    p.proname,
    n.nspname AS function_schema
FROM pg_trigger AS t
JOIN pg_proc AS p ON p.oid = t.tgfoid
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE t.tgrelid = 'deferred_trigger_lab.allocations'::regclass
  AND NOT t.tgisinternal;
```

### 22.4. Be careful with manual maintenance

If a trigger is disabled or a function is modified, existing rows **are not automatically re-validated**. Plan migrations, full-dataset validation, and rollback strategies based on risk.

---

## 23. ALTER TABLE DISABLE TRIGGER and Bypass Risks

### 23.1. Triggers can be disabled by privileged roles

```sql
-- Illustrative only; DO NOT run on production tables:
-- ALTER TABLE deferred_trigger_lab.allocations
-- DISABLE TRIGGER batch_total_guard_lines;
```

While disabled, subsequent DML does not trigger the designed deferred checks.

### 23.2. ENABLE does not rescan existing data

```sql
-- Illustrative only:
-- ALTER TABLE deferred_trigger_lab.allocations
-- ENABLE TRIGGER batch_total_guard_lines;
```

Re-enabling a trigger does not revisit batches modified while disabled to check the invariant.

### 23.3. Migrations and backfills need independent verification

When loading legacy data or running bulk loads:

1. Record exactly when triggers were disabled/enabled and why.
2. Block or coordinate concurrent writers during the unprotected window.
3. Verify all sealed batches with a reconciliation query.
4. Remediate any drifted batches.
5. Reopen normal write traffic only after invariants pass.

### 23.4. Reconciliation query

```sql
SELECT
    b.batch_id,
    b.tenant_id,
    b.expected_total,
    COALESCE(SUM(a.amount), 0) AS actual_total
FROM deferred_trigger_lab.batches AS b
LEFT JOIN deferred_trigger_lab.allocations AS a
    ON a.batch_id = b.batch_id
WHERE b.status = 'sealed'
GROUP BY b.batch_id, b.tenant_id, b.expected_total
HAVING COALESCE(SUM(a.amount), 0)
       IS DISTINCT FROM b.expected_total
ORDER BY b.batch_id;
```

With valid lab data, this query returns zero rows. Any returned row identifies a **mismatched sealed batch** needing attention.

### 23.5. Do not treat triggers as your sole security barrier

An account with broad schema/DDL privileges or special replication/import settings can affect whether triggers fire. Managing grants, roles, privileged migrations, and audits is part of protecting invariants.

---

## 24. Transactions, SAVEPOINTs, and Errors at COMMIT

### 24.1. Transactions define the deferral boundary

`DEFERRABLE INITIALLY DEFERRED` is most meaningful when **multiple statements run inside one transaction**.

If an application runs in autocommit mode:

```text
Statement 1 -> commits immediately
Statement 2 -> separate transaction
```

then the deferred trigger from statement 1 still enforces the constraint **when that short transaction commits**. It cannot wait for statement 2 in a future transaction.

### 24.2. Using BEGIN/COMMIT properly

```sql
BEGIN;

-- Multiple changes that must be atomic together.

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_header,
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

COMMIT;
```

In application code, wrap operations in explicit transactions and handle errors on both `SET CONSTRAINTS` and `COMMIT`. Commit can fail due to other constraints, serialization conflicts, or infrastructure issues.

### 24.3. SAVEPOINT

```sql
BEGIN;

SAVEPOINT before_adjustment;

UPDATE deferred_trigger_lab.allocations
SET amount = amount + 5
WHERE line_id = 1001;

-- If you want to discard the adjustment:
ROLLBACK TO SAVEPOINT before_adjustment;

COMMIT;
```

After rolling back to a savepoint, data changes made after the savepoint are undone, and queued trigger events from those rolled-back changes are handled per transaction/subtransaction rules.

### 24.4. Retroactive checks and savepoints

When `SET CONSTRAINTS ... IMMEDIATE` fails due to a pending check, the transaction enters an error state and must roll back to an appropriate savepoint or roll back completely. Never keep sending SQL assuming the database will recover on its own.

### 24.5. PL/pgSQL BEGIN ... END is not a transaction boundary

Inside a function:

```sql
BEGIN
    UPDATE ...;
END;
```

`BEGIN/END` is merely a PL/pgSQL block, **not** a new commit point. A deferred constraint trigger fired by an UPDATE inside a function still waits until the outer caller's transaction commits.

### 24.6. Do not expect to COMMIT inside a trigger function

A trigger function is not where you commit transactions. A constraint trigger's job is to **check and raise an error if needed** within the active transaction, not to manage transaction lifecycles arbitrarily.

---

## 25. What Does RAISE EXCEPTION Mean at Commit Time?

### 25.1. When the invariant fails

In the helper:

```sql
IF v_actual IS DISTINCT FROM v_expected THEN
    RAISE EXCEPTION '...'
        USING ERRCODE = '23514';
END IF;
```

The error halts normal execution. When raised during pending constraint checks at `COMMIT`, the transaction fails to commit.

### 25.2. Do not use RAISE NOTICE to "enforce" invariants

`RAISE NOTICE` only emits diagnostic notices. If the function runs:

```sql
IF v_actual <> v_expected THEN
    RAISE NOTICE 'Totals do not match';
END IF;
```

the transaction still commits despite the mismatched total. A constraint trigger enforcing an invariant **must raise an exception** on forbidden violations.

### 25.3. Exception messages and SQLSTATE

Applications should record:

- `SQLSTATE` to classify the error.
- Constraint name if provided.
- Relevant non-sensitive group/record IDs.
- Transaction and correlation IDs in logs.

Never parse prose inside an exception message to decide whether to retry.

### 25.4. Business violations differ from serialization failures

- `23514` in the lab: invariant violated; fix the data or business flow.
- `40001`: serialization failure; retry the entire transaction safely when supported.
- `40P01`: deadlock detected; retry boundedly after reviewing lock ordering.

Never blindly retry a transaction whose total is 115 against expected 100; repeating identical work will not satisfy the constraint.

---

## 26. Workflow for Modifying a Constraint Trigger

### 26.1. Functions and triggers are separate objects

Function:

```sql
CREATE OR REPLACE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred()
RETURNS trigger ...
```

Trigger:

```sql
CREATE CONSTRAINT TRIGGER batch_total_guard_lines
AFTER ... ON ...
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION ...;
```

Updating the **function body** can use `CREATE OR REPLACE FUNCTION` when the signature matches. Changing **events, deferrability, or WHEN** on a constraint trigger requires DDL on the trigger itself.

### 26.2. Do not use CREATE OR REPLACE TRIGGER on constraint triggers like ordinary triggers

In current PostgreSQL, `CREATE OR REPLACE TRIGGER` **does not support replacing constraint triggers**. To alter a constraint trigger's definition, plan a `DROP TRIGGER` and `CREATE CONSTRAINT TRIGGER` under appropriate locking and traffic controls.

### 26.3. Migration gap risks

If you drop and recreate a constraint trigger in two separate transactions, writes occurring in between run unprotected.

Always:

- Use a single consistent DDL transaction and maintenance window when needed.
- Verify privileges and locks.
- Confirm the new trigger exists before reopening writers.
- Reconcile data if any unprotected window occurred.

### 26.4. Changing function logic does not rescan history

If a new version changes the rule:

```text
v1: allocation sum must equal expected_total
v2: allocation sum must equal expected_total
    and every sealed batch must have at least 2 lines
```

Sealed batches created before deploying v2 **do not automatically fire UPDATE events** to re-check. Run dedicated validation across existing data and remediate violations.

### 26.5. Do not treat an enabled trigger as proof of clean data

Metadata proves the trigger is active now; it does not prove historical rows never violated the rule before the trigger existed, while it was disabled, or under an older buggy function.

---

## 27. Permissions, SECURITY DEFINER, and search_path

### 27.1. Trigger creation privileges

Creating a trigger requires appropriate table privileges and `EXECUTE` on the trigger function. Never grant broad DDL privileges to application roles just to use invariants.

### 27.2. SECURITY INVOKER vs. DEFINER

PL/pgSQL functions follow their declared security mode, defaulting to `SECURITY INVOKER`.

If declared `SECURITY DEFINER`, the function executes with the owner's privileges and requires:

- A least-privileged owner role.
- A safe `search_path` preventing untrusted object shadowing.
- Schema-qualified table and function names.
- Explicit `EXECUTE` privilege controls.
- No unvalidated/unquoted dynamic SQL from untrusted inputs.

### 27.3. Tenant isolation

In multi-tenant schemas, the function filters by `batch_id` without `tenant_id` in the `SUM`. That holds in the lab **because `batch_id` is globally unique and FKs enforce ownership**. If keys are unique only per tenant, include `tenant_id` in PKs, FKs, and WHERE clauses.

Constraint triggers do not replace authorization or RLS; restrict write access to batches and allocations properly.

### 27.4. RLS inside triggers

Row-level security can filter which rows a function sees depending on role, security mode, and policies. A `SUM` function that **cannot see all allocations** will compute wrong totals.

For cross-tenant or cross-table invariants, verify ownership, execution privileges, and RLS, and test with actual runtime roles. Never use `SECURITY DEFINER` merely to bypass RLS without a security review.

---

## 28. Comparing Constraint Triggers With Other Strategies

| Problem | Preferred tool | When is a constraint trigger appropriate? |
|---|---|---|
| Column must have a value | `NOT NULL` | Almost never needed |
| Quantity must be non-negative | `CHECK` | Almost never needed |
| Unique key | `UNIQUE` / `PRIMARY KEY` | Never replace with manual `SELECT COUNT` |
| Child row requires parent | `FOREIGN KEY` | Never replace native FKs |
| Booking intervals must not overlap | `EXCLUDE` | Only if native exclusion cannot model the rule |
| Allocation sum equals header at commit | Write protocol; deferred trigger can assist | When checking multiple rows after multiple statements |
| Update timestamps/audits after DML | Ordinary trigger | Does not need deferral |
| Process all changed rows of one statement | AFTER statement + transition table | Constraint triggers do not support transition tables |
| Cross-system checks outside database | Application protocol / outbox | Triggers cannot commit atomically with external services |
| Massive bulk aggregates | Summary table / controlled procedure | Beware row-level deferred check overhead |

### 28.1. Choose native constraints first

Native constraints come with PostgreSQL planner/catalog awareness and stronger concurrency guarantees than hand-written SELECTs. Triggers should only supplement invariants that native tools cannot express.

### 28.2. Match check timing to workflow

If an operation is a single UPDATE:

```text
UPDATE row
-> invariant must hold immediately
```

no deferral is needed. If it is a multi-step transaction:

```text
Update A
Update B
Correct header
Check final total
Commit
```

deferral models the workflow much better.

### 28.3. What if an invalid intermediate state must span multiple transactions?

Do not use a deferred constraint trigger if the requirement is to **commit a temporarily invalid state and fix it in a later transaction**. Deferred checks still execute before commit.

For multi-transaction workflows, model **explicit valid lifecycle states** such as `draft`/`pending`/`approved` with appropriate constraints. Never try using `INITIALLY DEFERRED` to postpone checks indefinitely across transactions.

---

## 29. Common Mistakes

**1. "Constraint triggers are deferrable BEFORE triggers."** False. They must be `AFTER ROW`.

**2. "You can create a constraint trigger FOR EACH STATEMENT."** False.

**3. "REFERENCING NEW TABLE works with constraint triggers."** No. Transition relations cannot be used with constraint triggers.

**4. "INITIALLY DEFERRED skips validation."** False. It changes when validation runs.

**5. "DEFERRABLE and INITIALLY DEFERRED are identical."** False. One permits deferral; the other sets the default mode.

**6. "NOT DEFERRABLE can be switched to DEFERRED via SET CONSTRAINTS."** No.

**7. "SET CONSTRAINTS permanently changes session defaults."** No; it applies only to the current transaction.

**8. "SET CONSTRAINTS ... IMMEDIATE affects only future changes."** False. It checks all pending deferred events immediately.

**9. "If SET CONSTRAINTS IMMEDIATE fails, just rerun the query without ROLLBACK."** No. You must handle the aborted transaction state.

**10. "SET CONSTRAINTS ALL affects only my trigger."** No. It affects all deferrable constraints in scope.

**11. "Constraint names are always unique across the whole database."** No.

**12. "WHEN on a constraint trigger is evaluated at COMMIT."** False. It runs immediately after the row operation to decide whether to queue the event.

**13. "An overly narrow WHEN cannot miss changes."** False. DELETEs, group moves, or status changes can fail to queue.

**14. "A deferred event's NEW always holds the row's final transaction values."** No. Never trust stale queued event snapshots over querying final data.

**15. "A trigger on the child table alone protects child SUM = parent total."** False if the header changes.

**16. "A trigger on the header alone is enough."** False if allocations change.

**17. "An UPDATE changing batch_id only needs to check NEW.batch_id."** False. Both old and new groups can become invalid.

**18. "RETURN NEW in an AFTER trigger modifies the saved row."** No. Return values do not alter already-written rows.

**19. "A CONSTRAINT TRIGGER knows validation logic automatically."** No. The function must explicitly `RAISE EXCEPTION`.

**20. "RAISE NOTICE is enough to reject a bad transaction."** No.

**21. "CHECK can SELECT SUM from another table as a safe cross-row constraint."** No.

**22. "CHECK and NOT NULL can use SET CONSTRAINTS DEFERRED."** No.

**23. "A SELECT COUNT trigger replaces UNIQUE better."** No. Native uniqueness has proper concurrency mechanics.

**24. "A deferrable unique constraint still works as an ON CONFLICT arbiter."** No.

**25. "FOREIGN KEY always checks immediately and cannot be deferred."** False. `DEFERRABLE` FKs can defer appropriately.

**26. "RESTRICT FK actions defer just like NO ACTION."** No.

**27. "DEFERRABLE makes CASCADE wait until transaction end."** No; referential actions follow separate rules.

**28. "Having a deferred trigger makes SELECT SUM concurrency-safe at every isolation level."** No.

**29. "SERIALIZABLE automatically retries for the application."** No. Applications must handle serialization failures.

**30. "SELECT FOR UPDATE on a parent suffices even if other writers skip locking the parent."** No. All writers must follow the protocol.

**31. "Locking A and B in any order across transactions will never deadlock."** No. Maintain a consistent lock order.

**32. "A 50,000-row UPDATE queues one deferred event."** No. Row-level triggers queue one event per matching row.

**33. "PostgreSQL deduplicates identical-batch events into one SUM."** No.

**34. "Deferred constraints make COMMIT faster."** Not necessarily; they can shift heavy work to commit time.

**35. "With an index on batch_id, running SUM thousands of times is negligible."** Never assume that.

**36. "TRUNCATE behaves like per-row DELETE for triggers."** No.

**37. "Enabling a trigger after bulk loading automatically validates existing data."** No.

**38. "Changing check-function logic needs no check on historical rows."** False when the invariant changed.

**39. "CREATE OR REPLACE TRIGGER works identically on constraint triggers."** Not in current PostgreSQL.

**40. "Constraint triggers enforce tenant permissions."** No. Grants, RLS, and auth are still required.

**41. "An autocommit session can fix data in a second statement before the first statement's deferred trigger checks."** No. The first transaction ends and checks before the second begins.

**42. "PL/pgSQL BEGIN ... END equals SQL BEGIN/COMMIT."** No.

**43. "Data in draft status must satisfy the sealed invariant."** Not under the lab model; status determines check scope.

**44. "Commit errors can be ignored because the earlier UPDATE succeeded."** No. The transaction did not commit.

**45. "Testing sequential single-session transactions suffices for custom constraint triggers."** No. Test concurrency and failure recovery.

---

## 30. Practice Exercises and Answers

### Exercise 1 — Identifying when deferral is needed

**Scenario:** A transaction increases allocation A from 60 to 70 and then decreases B from 40 to 30; the final total must equal 100.

**Answer:** A deferrable constraint trigger can check the invariant at transaction end, permitting the temporary total of 110 after the first statement.

### Exercise 2 — Writing a deferred constraint trigger

**Answer:**

```sql
CREATE CONSTRAINT TRIGGER example_deferred_guard
AFTER INSERT OR UPDATE OR DELETE
ON deferred_trigger_lab.allocations
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION
    deferred_trigger_lab.enforce_batch_total_deferred();
```

This is a syntax sample; the lab table already has `batch_total_guard_lines` performing the same job. Do not keep two redundant triggers.

### Exercise 3 — Why must it be AFTER ROW?

**Answer:** PostgreSQL requires constraint triggers to be `AFTER ROW` on regular tables. `BEFORE` or `FOR EACH STATEMENT` are invalid for this trigger type.

### Exercise 4 — Switching from deferred to immediate

**Answer:**

```sql
BEGIN;

SET CONSTRAINTS
    deferred_trigger_lab.batch_total_guard_lines
IMMEDIATE;

COMMIT;
```

If pending events exist, they are checked right at `SET CONSTRAINTS` under retroactive evaluation rules.

### Exercise 5 — When SET CONSTRAINTS IMMEDIATE detects a violation

**Answer:** The statement fails and the transaction must be rolled back or error-handled. There is no "commit anyway and fix later."

### Exercise 6 — Can INITIALLY IMMEDIATE be deferred?

**Answer:** Yes, if declared `DEFERRABLE INITIALLY IMMEDIATE`. The transaction calls `SET CONSTRAINTS name DEFERRED` before DML needing deferral.

### Exercise 7 — NOT DEFERRABLE

**Question:** Can `SET CONSTRAINTS name DEFERRED` turn a `NOT DEFERRABLE` constraint trigger into a deferred one?

**Answer:** No. You must alter/recreate the constraint or trigger definition with `DEFERRABLE` DDL.

### Exercise 8 — Autocommit SQL

**Question:** Can two separate autocommit UPDATE statements use a deferred trigger to fix an unbalanced total between them?

**Answer:** No. The first statement ends its transaction and runs checks before the second statement starts in a new transaction.

### Exercise 9 — Checking SUM

```sql
SELECT
    b.batch_id,
    b.expected_total,
    COALESCE(SUM(a.amount),0) AS actual_total
FROM deferred_trigger_lab.batches b
LEFT JOIN deferred_trigger_lab.allocations a
    ON a.batch_id = b.batch_id
WHERE b.status = 'sealed'
GROUP BY b.batch_id, b.expected_total;
```

**Answer:** The query shows expected vs. actual totals for sealed batches. To list only discrepancies, add `HAVING COALESCE(SUM(a.amount),0) IS DISTINCT FROM b.expected_total`.

### Exercise 10 — Why COALESCE?

**Answer:** `SUM` over an empty set returns NULL. In the lab model, an empty allocation set is defined as totaling 0.

### Exercise 11 — Unbalanced draft

**Scenario:** A draft batch has expected 200 and actual 10.

**Answer:** Allowed under the lab invariant because total enforcement applies only when `status = 'sealed'`.

### Exercise 12 — Transitioning draft to sealed

**Requirement:** In one transaction, change status to `sealed` and insert the missing allocation.

**Answer:** Use `BEGIN; UPDATE batches ...; INSERT allocations ...; COMMIT;`. The deferred trigger checks the final sum at commit.

### Exercise 13 — DELETE allocation

**Question:** Why attach the trigger to DELETE?

**Answer:** Deleting a line lowers the sum; without checking after DELETE, a sealed batch could become under-allocated unnoticed.

### Exercise 14 — Moving an allocation between two batches

**Answer:** Check both `OLD.batch_id` and `NEW.batch_id` on UPDATE, because the source group loses money and the target group gains money.

### Exercise 15 — Header changed

**Scenario:** `expected_total` increases while allocations stay unchanged.

**Answer:** A constraint trigger on `batches` (or another header-guarding mechanism) is required because the child trigger emits no event when only the header changes.

### Exercise 16 — Is WHEN deferred?

**Answer:** No. `WHEN` on a constraint trigger is evaluated immediately after the row operation. If FALSE, no event is queued.

### Exercise 17 — NOT FOUND for a deleted parent

**Question:** Why does the helper execute `IF NOT FOUND THEN RETURN;` when the batch is gone?

**Answer:** A pending event may belong to a parent deleted earlier in the same transaction. The sealed invariant no longer applies to a non-existent parent.

### Exercise 18 — Why can't AFTER triggers edit NEW?

**Answer:** AFTER triggers run after the row operation occurred; the return value is not used to alter the row. Use a BEFORE trigger to modify `NEW` before storage.

### Exercise 19 — SQLSTATE

**Question:** Which SQLSTATE does the lab function emit for a mismatched total?

**Answer:** `23514` (`check_violation`), explicitly set in `RAISE EXCEPTION`.

### Exercise 20 — Deferrable UNIQUE for swapping positions

**Answer:** Declare `UNIQUE(board_id, position) DEFERRABLE INITIALLY DEFERRED`, swap inside a transaction, and ensure no duplicate positions remain at transaction end.

### Exercise 21 — UNIQUE vs. custom trigger

**Scenario:** No two users may share the same normalized email.

**Answer:** Prefer a unique constraint/index on the normalized key; never write a table-scanning constraint trigger just to count duplicate emails.

### Exercise 22 — Deferrable FK

**Requirement:** Insert child then parent in the same transaction.

**Answer:** `FOREIGN KEY (...) REFERENCES ... DEFERRABLE INITIALLY DEFERRED`, ensuring the parent is inserted before commit.

### Exercise 23 — ON DELETE RESTRICT vs. NO ACTION

**Answer:** `NO ACTION` allows deferral when the FK is deferrable; `RESTRICT` refuses to defer the rejection check.

### Exercise 24 — CHECK (amount >= 0)

**Question:** Can `SET CONSTRAINTS` defer this CHECK?

**Answer:** No. `CHECK` constraints are not deferrable in PostgreSQL.

### Exercise 25 — EXCLUDE for booking overlaps

**Answer:** Use `EXCLUDE USING gist (room_id WITH =, slot WITH &&)` with `DEFERRABLE` if schedule swaps inside a transaction are required and business rules permit.

### Exercise 26 — Concurrency

**Question:** Does two transactions each passing `SELECT SUM` inside a deferred trigger guarantee final data is always consistent?

**Answer:** Not automatically. Account for MVCC, isolation, and a protocol serializing writers on the parent row or using native constraints.

### Exercise 27 — Locking the parent

**Suggested answer:**

```sql
BEGIN;
SELECT 1
FROM deferred_trigger_lab.batches
WHERE batch_id = 101
FOR UPDATE;

-- Then apply changes to this batch.
ROLLBACK;
```

All writers must follow the protocol consistently, not just one code path.

### Exercise 28 — Two parents and deadlocks

**Answer:** When moving allocations between batch A and batch B, acquire locks in a consistent order (e.g., ascending `batch_id`) to reduce deadlock risk; still handle deadlock errors if they arise.

### Exercise 29 — SERIALIZABLE

**Question:** Can `SERIALIZABLE` abort a transaction?

**Answer:** Yes; applications must catch SQLSTATE `40001` and safely retry the whole transaction.

### Exercise 30 — Cost of 50,000 row events

**Answer:** Because constraint triggers are `AFTER ROW`, 50,000 rows queue 50,000 events. If each event re-sums the entire batch, `COMMIT` becomes extremely expensive.

### Exercise 31 — Transition tables

**Question:** Can a constraint trigger use `REFERENCING NEW TABLE` to process 50,000 rows once?

**Answer:** No. Transition relations are disallowed on constraint triggers. You can consider an ordinary AFTER statement trigger for suitable workloads, though you lose `SET CONSTRAINTS` deferral.

### Exercise 32 — Bulk load while trigger is disabled

**Answer:** After re-enabling the trigger, reconcile existing data; triggers do not retroactively check writes performed while disabled.

### Exercise 33 — Changing function logic

**Question:** Does updating the function to require at least two lines on sealed batches automatically verify all existing batches?

**Answer:** No. Separate migration/validation is needed in addition to checking new DML.

### Exercise 34 — Constraint triggers and TRUNCATE

**Answer:** `AFTER ROW` constraint triggers do not fire like row-by-row DELETEs on TRUNCATE; govern TRUNCATE privileges and bulk procedures.

### Exercise 35 — Inspecting metadata

```sql
SELECT tgname, tgdeferrable, tginitdeferred, tgenabled
FROM pg_trigger
WHERE tgrelid = 'deferred_trigger_lab.batches'::regclass
  AND NOT tgisinternal;
```

**Answer:** Shows trigger names, deferrable/default-deferred flags, and enabled modes for user-defined triggers on `batches`.

### Exercise 36 — Choosing the approach

**Scenario:** An invariant must hold immediately after every individual UPDATE, with no intermediate steps.

**Answer:** Prefer a native constraint or immediate checking. Deferral is unnecessary when no valid multi-step intermediate states exist.

---

## 31. Safe Constraint Trigger Design Checklist

### Invariant definition

1. Clarify which states require the invariant: `draft` or `sealed`?
2. Is the condition on **one row**, multiple rows, or multiple tables?
3. Can native `CHECK`/`UNIQUE`/`FK`/`EXCLUDE` express it?
4. Is a temporarily invalid state between statements in one transaction genuinely needed?
5. Are NULLs, empty sets, and deleted parents clearly defined?
6. For monetary rules, are currency, precision, and business semantics accurate?

### Trigger design

7. Use `CREATE CONSTRAINT TRIGGER` as `AFTER ROW` on an eligible table.
8. Choose `DEFERRABLE INITIALLY IMMEDIATE` or `INITIALLY DEFERRED` to fit the workflow.
9. Attach triggers to **every table** whose DML can break the invariant.
10. Cover INSERT/UPDATE/DELETE and `OLD`/`NEW` group-key changes.
11. Never add `WHEN` without proving it cannot drop needed checks.
12. Remember `WHEN` runs immediately, not at commit.
13. The trigger function must `RAISE EXCEPTION` on failure, not just `NOTICE`.
14. In AFTER triggers, never rely on return values to edit `NEW`.
15. When reading final state, never rely blindly on stale `NEW` snapshots from long-queued events.
16. Never attempt transition tables on constraint triggers.

### Transactions and concurrency

17. Multi-statement edits must share **the same transaction**.
18. Place `SET CONSTRAINTS` before the deferred phase.
19. Remember `SET CONSTRAINTS ... IMMEDIATE` checks retroactively.
20. Avoid `ALL` when only a specific group of constraints is meant.
21. Handle errors and rollbacks on both `COMMIT` and `SET CONSTRAINTS`.
22. Analyze concurrency anomalies and design locking/isolation.
23. If locking parents, ensure every writer obeys the protocol.
24. When locking multiple parents, enforce a deterministic lock order.
25. Implement appropriate retry handling for `40001` and `40P01`.

### Performance and operations

26. Can a single large statement queue excessive events?
27. Is the function re-summing the same batch thousands of times?
28. Are proper indexes present for parent/child lookups?
29. Have `COMMIT` latency and lock contention been benchmarked?
30. Can bulk loads, replication, or migrations bypass the trigger?
31. Is a periodic reconciliation query scheduled?
32. Are function logic changes paired with historical data checks?
33. Does DDL replacing constraint triggers avoid unprotected gaps?
34. Have `pg_trigger`/`pg_constraint` and privileges been verified?
35. Have NULLs, DELETEs, `batch_id` moves, and `COMMIT` failures been tested?
36. Have concurrent multi-connection tests been run rather than single-session tests only?

---

## 32. Summary

A **constraint trigger** is a specialized PostgreSQL trigger whose validation function can be deferred until transaction end. It is created with `CREATE CONSTRAINT TRIGGER`, must be **AFTER ROW** on a regular table, and can be declared `DEFERRABLE INITIALLY IMMEDIATE` or `DEFERRABLE INITIALLY DEFERRED`.

Key points:

- **`IMMEDIATE`**: checked at the applicable point for each statement.
- **`DEFERRED`**: can be postponed until the transaction-completion point.
- **`SET CONSTRAINTS ... IMMEDIATE`**: forces pending checks to run **right at the mode switch**, not just for future statements.
- **`WHEN` on a constraint trigger runs immediately at row-operation time**; if not TRUE, the event is not queued.
- Constraint triggers are **not** BEFORE triggers, statement triggers, or transition-table triggers.
- A function running `SELECT SUM(...)` must be attached to all relevant changes, handle `OLD`/`NEW` properly, and raise an exception if the invariant fails.
- **Deferral does not solve concurrency by itself.** Multi-row/multi-table invariants may require parent locks, transaction protocols, suitable isolation levels, or native constraints.
- **Prefer native constraints** whenever they model the problem: `UNIQUE`/`PRIMARY KEY`, `FOREIGN KEY`, and `EXCLUDE` support deferrability; `CHECK` and `NOT NULL` do not.
- **Validation cost can pile up at COMMIT.** Thousands of row-level events re-summing one group can create a major bottleneck.
- Changing functions, disabling triggers, or bulk-loading legacy data can leave historical rows unverified. Plan migrations, reconciliation, and monitoring.

**Closing question:** If a transaction executes three UPDATEs where the invariant fails after the first yet holds after the third, must the system reject immediately or only guarantee validity at commit? And if two separate transactions update the same group concurrently, what mechanism stops both from passing an unsafe snapshot-based check? Answering both questions clarifies when to use constraint triggers, when to defer, and when to reinforce concurrency design.

### Official PostgreSQL Documentation

- [CREATE TRIGGER — Constraint Triggers, DEFERRABLE, WHEN](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [SET CONSTRAINTS — IMMEDIATE and DEFERRED](https://www.postgresql.org/docs/current/sql-set-constraints.html).
- [Overview of Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html).
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html).
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html).
- [Constraints — CHECK, UNIQUE, FOREIGN KEY, and EXCLUDE](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [CREATE TABLE — DEFERRABLE Constraints](https://www.postgresql.org/docs/current/sql-createtable.html).
- [pg_trigger System Catalog](https://www.postgresql.org/docs/current/catalog-pg-trigger.html).
- [pg_constraint System Catalog](https://www.postgresql.org/docs/current/catalog-pg-constraint.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [CREATE INDEX — Unique and Exclusion Considerations](https://www.postgresql.org/docs/current/sql-createindex.html).
