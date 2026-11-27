# CALL and Transaction Control Eligibility in PostgreSQL Procedures

In PostgreSQL, a **procedure** is invoked using the `CALL` statement. Unlike a function executing inside a `SELECT` query, a procedure under eligible conditions can execute **`COMMIT`**, **`ROLLBACK`**, `COMMIT AND CHAIN`, or `ROLLBACK AND CHAIN` to end transactions during execution. This is useful for tasks such as batch processing, where you intentionally avoid holding one massive transaction across the entire job.

However, **transaction control is not automatically available on every `CALL`**. For example:

~~~sql
-- Case where COMMIT inside a procedure can be allowed:
CALL my_batch_procedure();  -- Independent top-level CALL

-- Case where a procedure is NOT allowed to self-COMMIT:
BEGIN;
CALL my_batch_procedure();
COMMIT;
~~~

If the procedure executes `COMMIT` or `ROLLBACK` in the second case, PostgreSQL raises an error such as `invalid transaction termination`. This often surprises developers accustomed to letting a Java/Spring application open a transaction before calling a procedure while still expecting the procedure to split transactions internally.

This lesson belongs to the **Functions and Procedures** chapter of the **Database Engine Relational PostgreSQL** module and focuses on: **when does `CALL` allow a procedure to control transactions, when is it forbidden, and how should batch jobs and applications be designed to preserve consistency?**

## 1. Learning objectives

After this lesson, you can:

1. Distinguish `CALL procedure(...)` from `SELECT function(...)`.
2. Create and invoke procedures using `CREATE PROCEDURE` and `CALL`.
3. Understand **who owns the transaction boundary**: the caller (application) or the procedure.
4. Explain why a top-level `CALL` can use transaction control whereas a `CALL` inside an explicit transaction block cannot.
5. Describe how PostgreSQL automatically starts a new transaction after each `COMMIT` or `ROLLBACK` inside a procedure.
6. Use `COMMIT AND CHAIN` / `ROLLBACK AND CHAIN` when transaction characteristics must carry over.
7. Recognize the rules for nested `CALL → CALL` chains and why an intervening `SELECT function(...)` blocks transaction control.
8. Explain restrictions on `SECURITY DEFINER` procedures and procedures declaring a `SET` clause.
9. Avoid placing `COMMIT`/`ROLLBACK` inside a PL/pgSQL block with an `EXCEPTION` handler.
10. Distinguish exception subtransactions from top-level transactions and understand `SAVEPOINT` limits in PL/pgSQL.
11. Analyze the impact of committing inside cursor loops, holdable cursors, and DML loops with `RETURNING`.
12. Design batch procedures with retry/idempotency guarantees and explicit handling of partial completion.
13. Integrate cleanly with JDBC `autoCommit` and Spring `@Transactional`.
14. Identify scenarios where the **application** should manage transactions instead of letting a procedure self-commit.
15. Diagnose transaction errors, locks, deadlocks, backend states, and hazardous DML statements.

## 2. Refresher on transactions and atomicity

A *transaction* is a unit of database work bounded by commit or rollback. When a transaction commits, its modifications become durable per PostgreSQL's durability guarantees; when an uncommitted transaction rolls back, its modifications are discarded.

~~~sql
BEGIN;

UPDATE wallets SET balance = balance - 100
WHERE wallet_id = 1;

UPDATE wallets SET balance = balance + 100
WHERE wallet_id = 2;

COMMIT;
~~~

In this transfer example, **both updates must belong to the same transaction**. Never try to "optimize batches" by inserting a `COMMIT` between the debit and the credit, as one half could persist while the other fails.

### 2.1. Common transaction control commands

| Command | Effect |
| --- | --- |
| `BEGIN` / `START TRANSACTION` | Opens an explicit transaction block on the client/SQL side |
| `COMMIT` | Ends the transaction and persists changes |
| `ROLLBACK` | Ends the transaction and discards uncommitted changes |
| `SAVEPOINT` | Marks a point for partial rollback inside a client-managed transaction |
| `ROLLBACK TO SAVEPOINT` | Reverts to a savepoint within the same transaction |
| `COMMIT AND CHAIN` | Commits and starts a new transaction preserving supported transaction characteristics |
| `ROLLBACK AND CHAIN` | Rolls back and starts a new transaction preserving supported characteristics |

**Note:** commands usable at the client SQL level are not all usable inside PL/pgSQL functions or procedures.

### 2.2. Two distinct transaction designs

| Design | Who decides when the transaction ends? |
| --- | --- |
| **Caller-owned transaction** | Application opens `BEGIN`, executes one or more `CALL`/DML statements, then issues `COMMIT`/`ROLLBACK`. The procedure **never ends the transaction itself**. |
| **Procedure-owned transaction boundaries** | Client issues an independent `CALL`, and the procedure runs `COMMIT` per batch. Each commit creates an **independent durable point**: later rollbacks do not undo earlier batches. |

Semantically, these two designs differ in **atomicity**, retry logic, batch visibility, and error handling. Never choose based purely on syntactic convenience.

### 2.3. A CALL without internal COMMIT is still a valid statement

~~~sql
BEGIN;
CALL update_one_order(101);
CALL update_another_order(102);
COMMIT;
~~~

This is completely valid **provided** those procedures do not attempt prohibited transaction control. The `CALL` command itself **is not forbidden** inside `BEGIN...COMMIT`; what is restricted is a procedure attempting to **terminate the transaction** inside that context.

## 3. Functions and procedures have different transaction semantics

PostgreSQL supports both functions and procedures, with key differences:

| Criterion | Function | Procedure |
| --- | --- | --- |
| Created with | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Typical SQL call | `SELECT my_func(...)`, usable in SQL expressions | `CALL my_proc(...)` |
| Result shape | Has return type; returns scalar/row/set | Can have `OUT`/`INOUT` parameters per syntax/version |
| Usable in WHERE/SELECT expressions | Yes, depending on signature | Not an SQL expression |
| Self `COMMIT`/`ROLLBACK` | **No** | **Strictly conditional** |
| DML | Depends on language, volatility, privileges, and call context | Can execute DML per privileges |
| Relationship with app transactions | Runs inside caller's transaction | Can run inside caller's transaction, but cannot self-commit if inside an explicit transaction block |

### 3.1. Simple function

~~~sql
CREATE FUNCTION public.add_two_numbers(a integer, b integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT a + b;
$$;

SELECT public.add_two_numbers(3, 5);  -- 8
~~~

A function is an **expression** with a return type. `SELECT public.add_two_numbers(...)` does not turn it into a procedure even if written in PL/pgSQL.

### 3.2. Simple procedure

~~~sql
CREATE PROCEDURE public.print_greeting(p_name text)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Hello %', p_name;
END;
$$;

CALL public.print_greeting('An');
~~~

`CALL` executes the procedure; because it performs no transaction control, it can still be called inside an explicit transaction block.

### 3.3. Functions cannot self-commit

~~~sql
-- Error illustration, DO NOT deploy as a valid function:
--
-- CREATE FUNCTION public.bad_commit()
-- RETURNS void
-- LANGUAGE plpgsql AS $$
-- BEGIN
--     COMMIT;  -- invalid transaction control for a function
-- END;
-- $$;
-- SELECT public.bad_commit();
~~~

Even when a function is called from inside a procedure, **passing through `SELECT function(...)`** blocks transaction control in any procedure nested further down, as the call-stack section explains.

### 3.4. Since PostgreSQL 11

SQL procedures and `CALL` were introduced in PostgreSQL **11**. Very old PostgreSQL versions do not support the procedure syntax covered in this lesson.

## 4. CREATE PROCEDURE and CALL syntax

Basic template:

~~~sql
CREATE PROCEDURE schema_name.procedure_name(
    IN p_id bigint,
    IN p_label text
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- SQL statements, IF, LOOP ...
END;
$$;

CALL schema_name.procedure_name(1001, 'ready');
~~~

### 4.1. IN parameters

`IN` passes values from the client into the procedure. It is the default mode in most signatures:

~~~sql
CREATE PROCEDURE public.report_status(p_status text)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'status=%', p_status;
END;
$$;

CALL public.report_status('done');
~~~

### 4.2. INOUT parameters

`INOUT` accepts an initial input value and returns the updated value after execution. Example:

~~~sql
CREATE PROCEDURE public.increment_counter(
    INOUT p_counter integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_counter := p_counter + 1;
END;
$$;

CALL public.increment_counter(5);
~~~

The client receives a **single result row** containing `p_counter=6`. Procedures do not declare `RETURNS integer` like functions.

### 4.3. OUT parameters and version differences

Modern PostgreSQL versions support procedure output parameters, though exact syntax and `OUT` passing rules evolved across major versions. When calling a procedure with `OUT` parameters from SQL, clients generally supply a placeholder argument (commonly `NULL`) in each `OUT` position per that version's `CALL` syntax; `OUT` arguments are not evaluated as business inputs.

Illustrative example:

~~~sql
-- Cross-check against the running PostgreSQL version:
-- CREATE PROCEDURE public.read_counter(
--     IN p_input integer,
--     OUT p_output integer
-- )
-- LANGUAGE plpgsql AS $$
-- BEGIN
--     p_output := p_input + 1;
-- END;
-- $$;
-- CALL public.read_counter(5, NULL);
~~~

**Do not assume `CALL` returns an SQL expression usable directly inside `SELECT fn(...)`.** When you need to compose results inside SQL queries, a function with a return type is the right tool.

### 4.4. Overloading and search_path

Procedures resolve by name and parameter types; if schemas or overloads share names, `search_path` and argument types can pick a different signature. In lab examples, always **schema-qualify** procedure and table names to prevent confusion.

### 4.5. CALL does not mean "COMMIT"

~~~sql
CALL public.print_greeting('An');
~~~

This merely invokes the procedure. If the procedure contains no transaction-control commands, it runs within the client's transaction context. **`CALL` is not shorthand for `COMMIT`.**

## 5. Fundamental conditions for a procedure to end transactions

Core rule:

> Only a procedure invoked via a **top-level `CALL`** (or inside an eligible nested chain of `CALL`/`DO` calls with no intervening command that revokes transaction control) may execute `COMMIT`/`ROLLBACK`. When `CALL` executes **inside an explicit transaction block**, the procedure **is forbidden** from terminating transactions itself.

### 5.1. Standalone CALL

~~~sql
CALL proc_lab_349.commit_one('job-A');
~~~

In a client like `psql` with normal autocommit enabled and **no explicit `BEGIN`**, procedure transaction control is permitted—provided the procedure also satisfies the other restrictions (no `SECURITY DEFINER`, no procedure-level `SET` clause, and no `COMMIT` inside an `EXCEPTION` block).

### 5.2. CALL inside an explicit transaction

~~~sql
BEGIN;
CALL proc_lab_349.commit_one('job-B');
ROLLBACK;
~~~

If `commit_one` executes `COMMIT` internally, PostgreSQL raises an error because **the procedure lacks authority to terminate the client-opened transaction**. Once the error fires, the explicit transaction enters an aborted state requiring `ROLLBACK`—do not attempt further normal SQL on that aborted transaction.

### 5.3. Omitting the word BEGIN is not always enough

Frameworks or drivers can **open an explicit transaction on your behalf**—for instance JDBC `setAutoCommit(false)`, Spring `@Transactional`, or ORM unit-of-work layers. Even if application source code shows only `CALL`, the runtime execution context can still forbid internal `COMMIT`s.

### 5.4. Valid nested CALLs

~~~text
Top-level CALL parent_proc()
             |
             +-- CALL child_proc()
                          |
                          +-- CALL grandchild_proc()
~~~

When the call stack consists strictly of eligible `CALL` (or `DO`) invocations from the top level, inner procedures **can perform transaction control** under PostgreSQL's rules.

### 5.5. Intervening commands revoke eligibility

~~~text
Top-level CALL parent_proc()
             |
             +-- SELECT helper_function()
                          |
                          +-- CALL nested_proc()
~~~

As documented in PostgreSQL, an **intervening `SELECT`** strips transaction-control eligibility from any deeper procedure calls, even though the outermost statement was a top-level `CALL`.

What matters is the **active call stack and command context**, not merely whether the procedure itself compiled cleanly.

### 5.6. DO blocks follow similar rules

A top-level `DO` block can perform transaction control when eligible, whereas a `DO` block inside an explicit transaction block cannot use `COMMIT`/`ROLLBACK` to end the caller's transaction.

### 5.7. Restrictions beyond call level

Even under a top-level `CALL`:

- A `SECURITY DEFINER` procedure **cannot** execute transaction-control statements.
- A procedure defined with a `SET configuration_parameter ...` clause **cannot** execute transaction-control statements.
- Transactions cannot be terminated inside an active PL/pgSQL `EXCEPTION`-handling block.
- Cursor loops and DML-driven loops carry additional restrictions.

These restrictions apply **regardless** of client autocommit settings.

## 6. Decision diagram for transaction ownership

~~~mermaid
flowchart TD
    A["Need to call a procedure"] --> B{"Does the procedure run COMMIT/ROLLBACK internally?"}
    B -->|No| C["Caller manages transaction normally"]
    B -->|Yes| D{"Is CALL genuinely top-level, not inside BEGIN?"}
    D -->|No| E["Fix design: remove internal COMMIT or call outside transaction"]
    D -->|Yes| F{"Valid CALL/DO call stack?"}
    F -->|No| E
    F -->|Yes| G{"SECURITY DEFINER / SET clause / EXCEPTION block?"}
    G -->|Yes| H["Adjust design and transaction boundary"]
    G -->|No| I["Conditional transaction control allowed"]
    I --> J["Ensure partial commits, retries, idempotency, and monitoring"]
~~~

This is an **architectural** decision chart, not an automatic execution guarantee. The exact same procedure can succeed in `psql` and fail inside a framework due to differing transaction contexts.

## 7. Lab dataset to observe COMMIT boundaries

The examples below create a dedicated schema `proc_lab_349` and insert sample rows to distinguish committed work from uncommitted work. **Run only in a lab database**, never testing transaction-control experiments on production business tables.

### 7.1. Create schema and log/job tables

~~~sql
CREATE SCHEMA proc_lab_349;

CREATE TABLE proc_lab_349.event_log (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL,
    phase text NOT NULL,
    recorded_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);

CREATE TABLE proc_lab_349.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_key text NOT NULL UNIQUE,
    state text NOT NULL
        CHECK (state IN ('pending', 'done')),
    processed_at timestamptz,
    last_note text
);
~~~

### 7.2. Insert sample jobs

~~~sql
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES
    ('job-001', 'pending'),
    ('job-002', 'pending'),
    ('job-003', 'pending'),
    ('job-004', 'pending'),
    ('job-005', 'pending'),
    ('job-006', 'pending');

SELECT job_id, job_key, state
FROM proc_lab_349.jobs
ORDER BY job_id;
~~~

### 7.3. Procedure with two commit points

~~~sql
CREATE PROCEDURE proc_lab_349.commit_two_phases(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'phase-1');

    COMMIT;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'phase-2');

    COMMIT;
END;
$$;
~~~

This procedure intentionally spans **two transactions** to illustrate:

~~~text
CALL starts
    |
    +-- INSERT phase-1
    +-- COMMIT             ← phase-1 is committed
    |
    +-- PostgreSQL automatically starts a new transaction
    +-- INSERT phase-2
    +-- COMMIT             ← phase-2 is committed
    |
CALL ends
~~~

### 7.4. Run standalone CALL

~~~sql
-- Run standalone, DO NOT wrap inside BEGIN ... COMMIT:
CALL proc_lab_349.commit_two_phases('case-top-level');

SELECT
    event_key,
    phase,
    recorded_at
FROM proc_lab_349.event_log
WHERE event_key = 'case-top-level'
ORDER BY event_id;
~~~

Semantically, **two rows** appear: `phase-1` and `phase-2`, committed at two distinct points.

### 7.5. Observing commit points from another session

If a procedure pauses between two transactions (for instance during real long-running batch work), another session can see `phase-1` **immediately after the first commit** while `phase-2` has not yet appeared. This **partial visibility** means already-committed work is never undone by failures in later transactions.

Never insert long `pg_sleep(...)` calls in production just to observe visibility; a lab environment with proper access is all you need.

## 8. Explicit BEGIN causes transaction-control CALLs to fail

### 8.1. Intentional error example

~~~sql
BEGIN;

CALL proc_lab_349.commit_two_phases('case-inside-begin');

-- If the procedure attempts COMMIT, the transaction errors.
ROLLBACK;
~~~

A typical error message:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... line ... at COMMIT
~~~

Exact `CONTEXT` details and line numbers depend on server version and procedure definition.

### 8.2. Is uncommitted data persisted?

In the explicit transaction above, `INSERT phase-1` ran before hitting the rejected `COMMIT`, causing the transaction to error. After `ROLLBACK`:

~~~sql
SELECT *
FROM proc_lab_349.event_log
WHERE event_key = 'case-inside-begin';
~~~

Neither row was committed from the failed call. This contrasts sharply with a top-level `CALL` that commits for real.

### 8.3. Why simply omitting BEGIN may not suffice

If your application uses JDBC with `autoCommit=false`, the driver or framework still opens a transaction. You must fix **the transaction context at the caller layer**, not merely delete `BEGIN` from an SQL string.

### 8.4. Never run COMMIT on an aborted transaction

In `psql` after an error inside an explicit transaction block, the prompt indicates an aborted transaction state. Issue `ROLLBACK` explicitly to recover—never send subsequent statements expecting PostgreSQL to ignore the initial error.

### 8.5. Do not "fix" with BEGIN inside the procedure

In PL/pgSQL, `BEGIN ... END` is a **language syntax block**, **not** a client SQL `BEGIN TRANSACTION`.

~~~sql
CREATE PROCEDURE proc_lab_349.demo_block()
LANGUAGE plpgsql
AS $$
BEGIN                 -- starts PL/pgSQL block, does NOT open a transaction
    RAISE NOTICE 'ok';
END;                  -- ends PL/pgSQL block
$$;
~~~

PostgreSQL automatically opens a fresh transaction after a valid `COMMIT`/`ROLLBACK` inside a procedure. There is no `START TRANSACTION` command to invoke inside PL/pgSQL.

## 9. COMMIT inside a procedure and automatic new transactions

In a PL/pgSQL procedure, when a valid `COMMIT` runs:

1. The current transaction finishes and its changes are persisted.
2. PostgreSQL **automatically starts a new transaction** as the procedure continues executing subsequent statements.
3. Changes after `COMMIT` belong to the **new** transaction and no longer share atomicity with prior steps.
4. If a later transaction rolls back, previously committed transactions **are not undone**.

This differs from functions called via `SELECT`, which cannot split their transactions with `COMMIT`.

### 9.1. PL/pgSQL variables survive across COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.count_phases()
LANGUAGE plpgsql
AS $$
DECLARE
    v_counter integer := 0;
BEGIN
    v_counter := v_counter + 1;
    COMMIT;

    v_counter := v_counter + 1;
    RAISE NOTICE 'counter=%', v_counter;
    COMMIT;
END;
$$;

-- Standalone CALL:
CALL proc_lab_349.count_phases();
~~~

`v_counter` is a **local variable in the procedure's execution frame**, not a committed database row. It retains its value across transaction boundaries within the same invocation.

That does **not** mean everything from the old transaction persists: row locks held by the committed transaction are released, and snapshots plus transaction-level state reset for the new transaction.

### 9.2. Temporary tables and session state

Some objects have **session** scope rather than transaction scope. However, temporary table options like `ON COMMIT DELETE ROWS` or `ON COMMIT DROP` trigger on every internal `COMMIT`.

If a procedure processes batches using temporary tables, check their **`ON COMMIT` behavior** before adding transaction control.

### 9.3. Locks, snapshots, and cursors

`COMMIT` releases transaction-level locks and closes the previous snapshot. The new transaction can observe commits made concurrently by other sessions. Therefore batch procedures **do not automatically preserve a single consistent snapshot** across their entire runtime.

Cursor loops are a notable exception because they convert into holdable cursors, discussed in a dedicated section below.

## 10. ROLLBACK inside a procedure: discards only the current transaction

Just like `COMMIT`, a valid `ROLLBACK` inside a top-level procedure:

- Discards **uncommitted** changes of the current transaction;
- Leaves changes committed in earlier transactions intact;
- Allows the procedure to continue in a fresh transaction started automatically by PostgreSQL.

### 10.1. Lab with a ROLLBACK between two writes

~~~sql
CREATE PROCEDURE proc_lab_349.rollback_middle(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'before-rollback');

    ROLLBACK;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'after-rollback');

    COMMIT;
END;
$$;

-- Run as a standalone CALL:
CALL proc_lab_349.rollback_middle('case-rollback');

SELECT event_key, phase
FROM proc_lab_349.event_log
WHERE event_key = 'case-rollback'
ORDER BY event_id;
~~~

Logical outcome: only `after-rollback` exists. `before-rollback` was discarded by the internal `ROLLBACK`.

### 10.2. ROLLBACK is not an automatic "ignore errors and keep going" command

If a normal SQL statement raises an error, the transaction enters an aborted state and procedure execution halts. Never expect execution to sail onward to a subsequent `ROLLBACK` statement to rescue itself. To handle errors in PL/pgSQL, use **`EXCEPTION` blocks** and understand subtransaction semantics. Design recovery explicitly rather than placing a `ROLLBACK` after an abort-prone statement.

### 10.3. Never use ROLLBACK for an unconditional "dry run"

A procedure may execute multiple `COMMIT`s before reaching a `ROLLBACK`. A final `ROLLBACK` **cannot** undo earlier commits. To simulate behavior without persisting writes, use lab databases, copies, or dedicated dry-run logic—never assume a trailing `ROLLBACK` undoes everything.

## 11. An error after COMMIT cannot roll back already-committed work

This is the central trade-off when deciding whether a procedure should manage transactions internally.

### 11.1. Procedure with an intentional error

~~~sql
CREATE PROCEDURE proc_lab_349.fail_after_first_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'already-committed');

    COMMIT;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'not-committed');

    RAISE EXCEPTION
        'Demo failure after first commit for %', p_key;
END;
$$;
~~~

### 11.2. Calling at top level

~~~sql
-- This intentionally raises an error; run in lab only:
CALL proc_lab_349.fail_after_first_commit('case-partial');
~~~

The `already-committed` insert completed the first transaction. The procedure then raised an exception in the next transaction. Although `CALL` returns an error to the client, **that does not mean all prior changes were undone**.

Verify in a fresh SQL query:

~~~sql
SELECT event_key, phase
FROM proc_lab_349.event_log
WHERE event_key = 'case-partial'
ORDER BY event_id;
~~~

**Expected:** `already-committed` is present; `not-committed` is absent.

### 11.3. Consequences of split atomicity

~~~text
CALL starts
   |
   +-- Transaction #1: INSERT A
   +-- COMMIT             ← A is durable
   |
   +-- Transaction #2: INSERT B
   +-- RAISE EXCEPTION    ← B is rolled back
   |
Client receives ERROR, yet A still exists.
~~~

**A procedure returning `ERROR` does not mean all earlier transactions rolled back.**

### 11.4. Why retrying the whole call can be dangerous

Suppose a procedure creates an invoice, updates a balance, and logs history across multiple commits. If a client sees an error and blindly retries everything without checking committed progress:

- Duplicate logs may be inserted;
- Financial transactions may be double-processed;
- Emails or webhooks may be sent twice;
- Unique violations may fire on the second attempt;
- Half-finished state may become hard to reconcile.

Batch procedures require **idempotency keys, persisted step states, deliberate transaction boundaries**, and targeted retry/resume logic.

## 12. COMMIT AND CHAIN and ROLLBACK AND CHAIN

Inside transaction-controlling procedures, PostgreSQL supports:

~~~sql
COMMIT AND CHAIN;
ROLLBACK AND CHAIN;
~~~

The goal is to **continue in a new transaction preserving the same transaction characteristics** from the previous one—such as isolation level and other transaction properties retained across `AND CHAIN`.

### 12.1. Comparing with plain COMMIT

~~~text
COMMIT:
  Ends the current transaction.
  Procedure continues in a new transaction with default characteristics.

COMMIT AND CHAIN:
  Ends the current transaction.
  Immediately starts a new transaction preserving supported
  transaction characteristics from the transaction just ended.
~~~

In PL/pgSQL, both forms work wherever transaction control is permitted. `AND CHAIN` does not make a prohibited call (such as `CALL` inside `BEGIN`) valid.

### 12.2. Procedure demonstrating AND CHAIN

~~~sql
CREATE PROCEDURE proc_lab_349.commit_chain_demo(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'chain-first');

    COMMIT AND CHAIN;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'chain-second');

    COMMIT;
END;
$$;

-- Must be called standalone:
CALL proc_lab_349.commit_chain_demo('case-chain');
~~~

### 12.3. When is it needed?

A procedure running consecutive transactions that must preserve specific transaction characteristics (like isolation level) can use `AND CHAIN` instead of letting subsequent transactions revert to session defaults.

**Never treat `AND CHAIN` as preserving the same MVCC snapshot across commits.** Each chained transaction is still a brand-new transaction and can observe concurrent commits per its isolation level.

### 12.4. No explicit START TRANSACTION in PL/pgSQL

~~~sql
-- Not a valid pattern to "open a new transaction" in PL/pgSQL:
-- COMMIT;
-- START TRANSACTION;
~~~

After a valid `COMMIT` or `ROLLBACK`, PostgreSQL opens the next transaction automatically. You do not need (and cannot use) `START TRANSACTION` inside a PL/pgSQL procedure body the way clients do.

## 13. Nested calls: CALL → CALL works, intervening SELECT blocks it

### 13.1. Create a child procedure with COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.child_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_key, 'child');

    COMMIT;
END;
$$;
~~~

### 13.2. Parent procedure invokes child directly via CALL

~~~sql
CREATE PROCEDURE proc_lab_349.parent_call(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    CALL proc_lab_349.child_commit(p_key);
END;
$$;

-- Standalone CALL:
CALL proc_lab_349.parent_call('case-nested-call');
~~~

When the call stack is purely `CALL parent_call() → CALL child_commit()` starting from top level, transaction control inside the child procedure is valid.

### 13.3. An intervening function call

Conceptual illustration:

~~~text
CALL parent_procedure()
  └── SELECT helper_function()
        └── CALL child_commit()
              └── COMMIT  → invalid in this call context
~~~

Even if a function could invoke a procedure internally, **routing the call stack through a `SELECT` statement** violates the call-stack rule documented in PostgreSQL's *PL/pgSQL Transaction Management*.

### 13.4. Look beyond the routine definition alone

When diagnosing `invalid transaction termination` from a child procedure:

- Who called the parent procedure?
- Did the caller already open a transaction?
- Did the call stack pass through `SELECT function(...)` or an intervening command?
- Does the child procedure have `SECURITY DEFINER` or a `SET` clause?
- Is `COMMIT` inside an exception block or restricted cursor loop?

Moving `COMMIT` around without understanding the full call context merely shifts the error elsewhere.

### 13.5. Calling from an application does not guarantee "top-level"

An ORM might wrap the call in a transaction or invoke it through a helper function. Always check **the exact SQL received by PostgreSQL** and the session's transaction state—never just a Java method named `executeProcedure`.

## 14. SECURITY DEFINER restriction

A procedure created with:

~~~sql
CREATE PROCEDURE public.privileged_operation()
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RAISE NOTICE 'Run with definer privileges';
END;
$$;
~~~

executes with the owner's privileges under `SECURITY DEFINER`. PostgreSQL **prohibits `SECURITY DEFINER` procedures from executing transaction-control statements**.

### 14.1. Never add SECURITY DEFINER to a committing procedure

~~~sql
-- Wrong idea:
-- CREATE PROCEDURE public.bad_privileged_commit()
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- AS $$
-- BEGIN
--     COMMIT; -- disallowed
-- END;
-- $$;
~~~

Enabling client autocommit cannot "fix" this: **the `SECURITY DEFINER` restriction still applies**.

### 14.2. Privileges and transaction control are separate axes

If a workflow needs elevated rights **and** batched commits:

- Review table/role privileges for a **`SECURITY INVOKER`** procedure;
- Design a clean privileged interface with caller-managed transaction boundaries;
- Split the privileged work from the batch-coordinating driver;
- Never abuse elevated rights to bypass restrictions or expose overly broad table grants to clients.

### 14.3. SECURITY DEFINER still requires a safe search_path

Even for non-committing procedures declared `SECURITY DEFINER`, ensure safe `search_path`, schema-qualified references, and tight `EXECUTE` grants to avoid object shadowing by untrusted schemas.

## 15. SET clause restriction on CREATE PROCEDURE

PostgreSQL allows procedures to attach a **`SET configuration_parameter ...` clause**:

~~~sql
CREATE PROCEDURE public.read_with_setting()
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    RAISE NOTICE 'A procedure with a SET clause';
END;
$$;
~~~

However, **any procedure with a `SET` clause in its definition is forbidden from executing transaction-control statements**, even when invoked standalone at top level.

### 15.1. Example to avoid

~~~sql
-- Invalid idea when intending internal COMMIT:
--
-- CREATE PROCEDURE public.bad_configured_commit()
-- LANGUAGE plpgsql
-- SET work_mem = '64MB'
-- AS $$
-- BEGIN
--     COMMIT;
-- END;
-- $$;
~~~

### 15.2. Distinguish a SET clause from caller SET LOCAL

`CREATE PROCEDURE ... SET search_path ...` is a **routine-level attribute in the definition**. `SET LOCAL ...` is a session command altering a GUC for the current transaction.

Do not assume they are identical: the restriction applies to **procedures defined with a `SET` clause**. Calling `SET LOCAL` from the caller depends on transaction scope and statements. When a procedure requires transaction control, schema-qualify tables/objects directly and manage settings at the appropriate layer.

### 15.3. Do not use a SET clause to "pin settings" alongside COMMIT

If transaction-level `work_mem`, `timezone`, or `search_path` is needed, clarify who owns configuration and transaction boundaries and check restrictions. **Transaction boundaries should never be altered accidentally** by a configuration tweak.

## 16. EXCEPTION blocks: subtransactions are not independent transactions

PL/pgSQL supports:

~~~sql
BEGIN
    -- statements
EXCEPTION
    WHEN unique_violation THEN
        -- handle error
END;
~~~

An `EXCEPTION` block runs inside a **subtransaction** so changes made within the block can roll back cleanly when an exception fires before transferring control to the handler.

**You cannot terminate the transaction using `COMMIT` or `ROLLBACK` while inside an active exception-handling block.**

### 16.1. Wrong pattern: COMMIT inside an EXCEPTION block

~~~sql
-- Do not use as a valid committing procedure:
--
-- CREATE PROCEDURE proc_lab_349.bad_exception_commit()
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     BEGIN
--         INSERT INTO proc_lab_349.event_log(event_key, phase)
--         VALUES ('bad', 'before');
--         COMMIT;    -- disallowed inside an EXCEPTION block
--     EXCEPTION WHEN OTHERS THEN
--         RAISE NOTICE 'error';
--     END;
-- END;
-- $$;
~~~

### 16.2. Right pattern: exit the EXCEPTION block before COMMIT

~~~sql
CREATE PROCEDURE proc_lab_349.exception_then_commit(p_key text)
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        INSERT INTO proc_lab_349.event_log(event_key, phase)
        VALUES (p_key, 'attempted');
    EXCEPTION WHEN unique_violation THEN
        RAISE NOTICE 'Duplicate key in protected operation';
    END;

    -- Already EXITED the EXCEPTION-handling block.
    COMMIT;
END;
$$;

-- Standalone CALL:
CALL proc_lab_349.exception_then_commit('case-exception');
~~~

Here, the exception-handling block finishes before `COMMIT`. If the handler triggers, changes inside that failed block roll back within **the block's subtransaction**, while the outer transaction continues safely to `COMMIT`.

### 16.3. What gets rolled back when an EXCEPTION fires?

When a statement inside the block fails and is caught by the handler:

- Persistent database writes made **inside that failed block** roll back to the start of the block;
- PL/pgSQL variables retain values assigned prior to the error per exception-handling semantics;
- Changes already committed in earlier transactions **are not** rolled back.

Thus an **`EXCEPTION` handler never replaces a transaction-level `ROLLBACK`** and cannot make earlier batch commits atomic.

### 16.4. Never use WHEN OTHERS to swallow all errors

~~~sql
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ignored';
~~~

can fool the application into thinking processing succeeded while critical database failures vanish. Catch only specific recoverable error codes, log full context, and re-`RAISE` whenever correctness cannot be guaranteed.

### 16.5. SAVEPOINT in PL/pgSQL

PostgreSQL PL/pgSQL **does not directly support `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` / `RELEASE SAVEPOINT`** statements inside procedural code. When partial rollback is needed within a block, **`BEGIN ... EXCEPTION ... END`** is the PL/pgSQL equivalent, subject to the rule against committing or rolling back inside exception-handling blocks.

At the caller SQL level, an explicit transaction can use savepoints normally—though doing so still prevents a called procedure from executing `COMMIT`.

## 17. Cursor loops and COMMIT: the holdable cursor effect

A procedure may iterate over results of a `SELECT`:

~~~sql
CREATE PROCEDURE proc_lab_349.cursor_loop_demo()
LANGUAGE plpgsql
AS $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT job_id, job_key
        FROM proc_lab_349.jobs
        ORDER BY job_id
    LOOP
        RAISE NOTICE 'job=%', r.job_key;
        COMMIT;
    END LOOP;
END;
$$;
~~~

In an eligible transaction-controlling procedure, PostgreSQL allows `COMMIT` inside a **cursor loop driven by a read-only `SELECT`**. However, there is a critical side effect.

### 17.1. The cursor converts to a holdable cursor on the first COMMIT

When a procedure runs `COMMIT` or `ROLLBACK` inside a cursor loop, the cursor automatically becomes a **holdable cursor** at the first transaction termination. PostgreSQL must **evaluate and materialize all remaining query rows** at that moment.

Consequently:

- The loop no longer streams and locks rows lazily as you might expect;
- Large result sets can consume substantial RAM and temporary disk storage;
- Row locks held by the cursor query are released upon commit;
- Iterated rows reflect the snapshot materialized at the first commit, ignoring later concurrent changes.

### 17.2. Why committing per row in a cursor loop often backfires

With 10 million rows, materializing everything at the first commit causes heavy temporary disk spill, while committing per row multiplies WAL/transaction overhead. Usually **keyset/limit batching** is far better than streaming a massive cursor across per-row commits.

### 17.3. Restrictions on DML-driven cursor loops

PostgreSQL **forbids transaction control commands inside cursor loops driven by non-read-only commands**, such as `UPDATE ... RETURNING`.

~~~sql
-- Invalid idea:
-- FOR r IN UPDATE ... RETURNING ... LOOP
--     COMMIT;   -- transaction control is restricted
-- END LOOP;
~~~

### 17.4. The SELECT FOR UPDATE loop trap

Even when the loop query looks like a `SELECT`, combining `FOR UPDATE` with internal commits does not preserve locks on remaining rows across commits. Design a **batch job-claiming algorithm** and complete updates before committing rather than relying on cursor locks surviving across commits.

### 17.5. Read-only cursor vs. safe batching algorithm

For millions of jobs, a cleaner strategy is:

1. Select up to `N` unprocessed jobs in the current transaction;
2. Lock/claim them safely under concurrency rules;
3. Update status and record results;
4. `COMMIT`;
5. Repeat with a fresh query rather than holding a giant cursor across transactions.

The next section builds a concrete procedure for this pattern.

## 18. Batch processing: COMMIT after each chunk of work

A legitimate reason to use procedure-level transaction control is processing massive job backlogs without holding locks, WAL, or snapshots open in one giant transaction.

However, splitting across transactions changes **overall job atomicity**. If a procedure processes 300 jobs and fails on job 301, those 300 committed jobs do not revert to pending automatically.

### 18.1. Target algorithm pattern

~~~text
CALL process_pending_jobs(2)
    |
    +-- Batch 1: claim up to 2 pending jobs
    |      UPDATE status → COMMIT
    |
    +-- Batch 2: claim up to 2 pending jobs
    |      UPDATE status → COMMIT
    |
    +-- Batch 3: claim up to 2 pending jobs
    |      UPDATE status → COMMIT
    |
    +-- Check: no claimable pending jobs remain
           → exit
~~~

### 18.2. Batch job-processing procedure

~~~sql
CREATE PROCEDURE proc_lab_349.process_pending_jobs(
    p_batch_size integer
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_batch_rows integer;
    v_total_rows bigint := 0;
    v_batch_number integer := 0;
BEGIN
    IF p_batch_size IS NULL OR p_batch_size < 1
       OR p_batch_size > 1000 THEN
        RAISE EXCEPTION
            'batch size must be between 1 and 1000';
    END IF;

    LOOP
        WITH next_jobs AS (
            SELECT j.job_id
            FROM proc_lab_349.jobs AS j
            WHERE j.state = 'pending'
            ORDER BY j.job_id
            LIMIT p_batch_size
            FOR UPDATE SKIP LOCKED
        )
        UPDATE proc_lab_349.jobs AS j
        SET state = 'done',
            processed_at = clock_timestamp(),
            last_note = 'Processed in batch'
        FROM next_jobs AS n
        WHERE j.job_id = n.job_id;

        GET DIAGNOSTICS v_batch_rows = ROW_COUNT;

        EXIT WHEN v_batch_rows = 0;

        v_batch_number := v_batch_number + 1;
        v_total_rows := v_total_rows + v_batch_rows;

        INSERT INTO proc_lab_349.event_log(event_key, phase)
        VALUES (
            format('batch-%s', v_batch_number),
            format('updated=%s', v_batch_rows)
        );

        COMMIT;

        RAISE NOTICE
            'Committed batch %, rows=%, total=%',
            v_batch_number, v_batch_rows, v_total_rows;
    END LOOP;
END;
$$;
~~~

This example demonstrates **purely database-internal steps** on the same tables. It neither calls external services nor assumes every business task can be processed safely by a single `UPDATE`.

### 18.3. Calling at top level

~~~sql
-- Do not use BEGIN ... CALL ... COMMIT:
CALL proc_lab_349.process_pending_jobs(2);

SELECT
    state,
    COUNT(*) AS job_count
FROM proc_lab_349.jobs
GROUP BY state
ORDER BY state;
~~~

With six initial `pending` jobs and no competing workers, the expected result is **6 `done` jobs**. The procedure commits three batches of up to two jobs each.

### 18.4. Why use GET DIAGNOSTICS ROW_COUNT?

~~~sql
GET DIAGNOSTICS v_batch_rows = ROW_COUNT;
~~~

retrieves the exact row count modified by the immediately preceding SQL statement (`UPDATE`). Rely on this actual count instead of assuming `LIMIT 2` always updates 2 rows—concurrency or remaining backlog size can yield fewer.

### 18.5. Why use SKIP LOCKED?

~~~sql
FOR UPDATE SKIP LOCKED
~~~

lets a worker claim rows **not currently locked by another transaction** without waiting on competitors' row locks. While great for multi-worker queues, it provides a **temporarily inconsistent view**: pending rows currently locked by other workers are skipped.

Hence, receiving 0 jobs while other workers are active **does not prove the entire queue is empty**. Pair with retry scheduling or reconciliation when needed.

### 18.6. COMMIT releases locks

Immediately after each `COMMIT`:

- Row locks held by that batch are released;
- Committed updates become visible to other transactions;
- A new transaction begins as the loop continues;
- The procedure preserves `v_total_rows` and `v_batch_number` across the invocation.

### 18.7. Idempotency boundaries in the lab

The predicate:

~~~sql
WHERE j.state = 'pending'
~~~

prevents a subsequent `CALL` from reprocessing already `done` jobs. This models an **idempotent database state transition** for the lab.

However, if real jobs trigger external side effects (sending email, charging cards, calling APIs), updating `state='done'` alone does not guarantee *exactly-once* delivery. You need idempotency keys, transactional outboxes/inboxes, retry rules, and explicit transaction boundaries.

### 18.8. Pitfalls of per-row commits

Running `p_batch_size = 1` over one million jobs:

- Generates one million separate commits;
- Multiplies commit/WAL flush overhead;
- Repeats worker queue scans and locking;
- Complicates cross-transaction visibility;
- Makes resuming trivial at the cost of terrible throughput.

Tune batch size based on transaction duration, lock contention, WAL rate, memory, latency, and recovery targets—**never pick 1 or 1000 blindly**.

### 18.9. When all-or-nothing is required, never use batch COMMITs

For transfers or multi-table updates that must succeed or fail together:

~~~sql
BEGIN;
CALL proc_lab_349.atomic_work_no_internal_commit(...);
COMMIT;
~~~

This is a conceptual pattern: the procedure must contain **no internal `COMMIT`/`ROLLBACK`** and preserve all invariants. You cannot recover atomicity with a trailing rollback once earlier batches have already committed.

## 19. Writing an atomic procedure where the caller controls COMMIT

To contrast, write a procedure that updates one job and writes a log **without** ending the transaction itself:

~~~sql
CREATE PROCEDURE proc_lab_349.complete_job_atomic(
    p_job_key text
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_updated integer;
BEGIN
    UPDATE proc_lab_349.jobs
    SET state = 'done',
        processed_at = clock_timestamp(),
        last_note = 'Completed atomically'
    WHERE job_key = p_job_key
      AND state = 'pending';

    GET DIAGNOSTICS v_updated = ROW_COUNT;

    IF v_updated <> 1 THEN
        RAISE EXCEPTION
            'Job % not found or not pending', p_job_key;
    END IF;

    INSERT INTO proc_lab_349.event_log(event_key, phase)
    VALUES (p_job_key, 'complete-job');
END;
$$;
~~~

### 19.1. Using inside an explicit transaction

~~~sql
-- Before running, insert a new pending job in the lab.
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES ('job-atomic-1', 'pending');

BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-1');
COMMIT;
~~~

Both `UPDATE` and `INSERT` belong to **one caller-owned transaction**. If inserting the log fails and the transaction rolls back, the job update is never committed on its own.

### 19.2. Caller ROLLBACK

~~~sql
INSERT INTO proc_lab_349.jobs(job_key, state)
VALUES ('job-atomic-2', 'pending');

BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-2');
ROLLBACK;

SELECT job_key, state
FROM proc_lab_349.jobs
WHERE job_key = 'job-atomic-2';
~~~

`job-atomic-2` stays `pending`, because the `UPDATE` ran inside the transaction rolled back by the caller.

### 19.3. Why does this design usually fit HTTP requests?

A single HTTP request often updates orders, inventory, internal ledgers, and audit logs as **one atomic unit**. The application framework opens a transaction and rolls back on failure. Procedures without internal `COMMIT` integrate seamlessly into that model.

### 19.4. Document transaction ownership in the API contract

Example API documentation:

~~~text
complete_job_atomic(job_key)
  - Does not commit/roll back internally.
  - Caller owns the transaction.
  - Safe inside @Transactional.

process_pending_jobs(batch_size)
  - Commits after every batch.
  - Must be invoked via standalone CALL, outside caller transactions.
  - May leave partial completion on failure.
  - Must be retried/reconciled safely.
~~~

Name and document both styles clearly. Never let an engineer discover during a production outage that one procedure self-commits while another does not.

## 20. Transaction orchestration: who owns the boundary?

APIs generally follow one of two patterns:

### 20.1. Pattern A — Caller-controlled

~~~text
BEGIN (caller)
    |
    +-- CALL step_1_no_commit()
    +-- CALL step_2_no_commit()
    +-- INSERT audit
    |
COMMIT (caller)
~~~

Advantages: full atomicity across steps, caller composability. Drawbacks: long transactions hold locks and snapshots longer, raising contention and delaying `VACUUM`.

### 20.2. Pattern B — Procedure-controlled

~~~text
CALL process_batch()
    |
    +-- DML batch 1 → COMMIT
    +-- DML batch 2 → COMMIT
    +-- DML batch 3 → COMMIT
~~~

Advantages: short per-batch transactions, periodic lock release, progress checkpoints. Drawbacks: loses all-or-nothing atomicity, introduces partial success, complicates retries and reconciliation.

### 20.3. Selection principle

**Data invariants and business correctness first, performance second.** Never split transactions merely because you can if business rules require synchronized updates across tables.

### 20.4. Never mix both patterns inside one explicit transaction expecting identical behavior

~~~sql
BEGIN;
CALL proc_lab_349.complete_job_atomic('job-atomic-1');
CALL proc_lab_349.process_pending_jobs(2);
COMMIT;
~~~

This fails if `process_pending_jobs` reaches an internal `COMMIT`. Inside an explicit transaction, the batch procedure has no authority to end it. Refactor the orchestration rather than trying to force a child procedure past caller boundaries.

## 21. JDBC: autoCommit and CALL statements

In JDBC, `Connection.getAutoCommit()` controls client-side transaction handling. **A procedure with internal `COMMIT`s must be invoked in a context where the application has not opened an explicit transaction block.**

### 21.1. Correct pattern for a self-committing procedure

~~~java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class BatchProcedureCaller {
    private final DataSource dataSource;

    public BatchProcedureCaller(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void runBatch(int batchSize) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(true);

            try (CallableStatement call = conn.prepareCall(
                    "CALL proc_lab_349.process_pending_jobs(?)")) {
                call.setInt(1, batchSize);
                call.execute();
            }
        }
    }
}
~~~

On a fresh connection with `autoCommit=true` and no surrounding transaction wrapper, a top-level `CALL` allows the procedure to commit provided all other restrictions are satisfied.

**Driver/framework note:** ORM transaction managers, proxies, session settings, and middleware can alter execution context. Always test against your exact **JDBC driver version** and datasource configuration.

### 21.2. Failing pattern

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try (CallableStatement call = conn.prepareCall(
            "CALL proc_lab_349.process_pending_jobs(?)")) {
        call.setInt(1, 2);
        call.execute();  // May fail with invalid transaction termination.
    }

    conn.commit();
}
~~~

`autoCommit=false` puts the caller in charge of the transaction. In PostgreSQL, internal `COMMIT`/`ROLLBACK` inside that explicit transaction context is rejected.

### 21.3. Correct pattern for an atomic procedure

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (CallableStatement call = conn.prepareCall(
                "CALL proc_lab_349.complete_job_atomic(?)")) {
            call.setString(1, "job-atomic-3");
            call.execute();
        }

        // Additional SQL statements can run in the same transaction.
        conn.commit();
    } catch (SQLException e) {
        conn.rollback();
        throw e;
    }
}
~~~

Because `complete_job_atomic` does not commit internally, the caller controls commit or rollback after all steps complete. This assumes `job-atomic-3` exists in `pending` state.

### 21.4. Do not "recover" by calling conn.commit() after CALL fails

If an internal `COMMIT` fails and the transaction enters an aborted state, calling `conn.commit()` will not complete remaining work. Roll back the transaction, diagnose the transaction-ownership mismatch, and fix the design.

### 21.5. Restore connection state cleanly

When using connection pools, changing `autoCommit`, isolation, `readOnly`, schemas, or GUCs must obey pool contracts. Never mutate state on a framework-managed connection and return it dirty to the pool. Frameworks may also cache proxy state or open transactions implicitly without explicit `BEGIN` calls.

### 21.6. An outer layer may already have opened a transaction

Even if the immediate method calling:

~~~java
callableStatement.execute();
~~~

contains no `BEGIN`, an upstream service method or transaction interceptor may already have opened a transaction. Trace the entire call path from controller/scheduler down to the datasource.

## 22. Spring @Transactional and self-committing CALLs

In Spring, `@Transactional` instructs the transaction manager to open a transaction around the annotated method:

~~~java
@Transactional
public void processJobsInOneRequest() {
    jdbcTemplate.update(
        "CALL proc_lab_349.process_pending_jobs(?)",
        2
    );
}
~~~

This snippet **conflicts** with a procedure containing internal `COMMIT`s because the `CALL` runs inside Spring's active transaction.

### 22.1. Two clean paths forward

**Option A — Caller owns the transaction:** remove internal `COMMIT`s from the procedure and invoke it inside `@Transactional`.

**Option B — Procedure owns transaction boundaries:** invoke `CALL` standalone over a connection **not participating in any active transaction**, properly configured for autocommit. Some codebases isolate it in a non-transactional service boundary or carefully verified propagation setup tied to the exact transaction manager and datasource.

### 22.2. Do not treat @Transactional(propagation=...) as a magic workaround

Propagation modes like `NOT_SUPPORTED` and `REQUIRES_NEW` behave very differently:

- `REQUIRES_NEW` **opens a brand-new transaction**, which still conflicts with internal `COMMIT`s.
- `NOT_SUPPORTED` suspends any active transaction, though you must still verify the connection/driver actually dispatches a top-level `CALL` in autocommit mode.

Choose propagation based on **the procedure's transaction contract**, never guesswork from enum names.

### 22.3. Self-invocation and proxy boundaries

With Spring's proxy-based transaction management, calling a `@Transactional` method from **within the same class** bypasses the proxy interceptor, causing differences between tests and production. When troubleshooting `invalid transaction termination`, inspect the live database transaction state rather than relying solely on annotations.

### 22.4. API design rules

A service method calling a self-committing batch procedure should:

- Represent a standalone batch task, never sit inside a multi-step ACID workflow;
- Never open an outer transaction;
- Use verified datasource and connection autocommit semantics;
- Catch failures and report **potential partial completion**;
- Inspect committed progress before retrying;
- Never assume an exception from `CALL` means nothing committed.

## 23. psql, autocommit, and practice habits

`psql` defaults to autocommit enabled: each standalone SQL statement outside an explicit `BEGIN` runs in its own PostgreSQL/psql transaction context. A standalone top-level `CALL` allows the procedure to self-commit.

### 23.1. Checking autocommit in psql

~~~text
\echo :AUTOCOMMIT
~~~

Before practicing procedures with internal `COMMIT`s, verify `psql` has autocommit enabled and is not inside an explicit transaction block.

~~~text
\set AUTOCOMMIT on
~~~

Lines starting with a backslash are **`psql` meta-commands**, not standard SQL runnable via JDBC or arbitrary SQL clients.

### 23.2. Wrapping scripts in BEGIN ... CALL breaks self-committing procedures

~~~sql
BEGIN;
CALL proc_lab_349.process_pending_jobs(2);
COMMIT;
~~~

As soon as the procedure hits a transaction-control statement, it errors. Some migration or ETL runners **automatically wrap entire SQL files in a transaction**, requiring you to run batch jobs as standalone steps or switch to caller-controlled procedures.

### 23.3. Executing multiple CALL statements

~~~sql
CALL proc_lab_349.commit_two_phases('first');
CALL proc_lab_349.commit_two_phases('second');
~~~

These are **two independent top-level statements**, each potentially committing multiple transactions internally. Never assume two `CALL`s in the same `.sql` file share one transaction.

### 23.4. JDBC and psql differ in transaction wrappers

A `CALL` succeeding in `psql` does not prove Spring or JDBC code will succeed if that code wraps the call in a transaction. Test using production-like drivers, pools, frameworks, and settings.

## 24. Transaction isolation and cross-batch consistency

PostgreSQL's transaction isolation level governs which concurrent changes a transaction can see. When a procedure self-commits multiple times, **each batch runs in a separate transaction**.

### 24.1. READ COMMITTED

Under `READ COMMITTED` (the common PostgreSQL default), each statement sees a snapshot as of that statement's start. If a procedure:

1. Queries pending jobs;
2. Commits batch 1;
3. Queries pending jobs again;

batch 2 can see newly inserted jobs committed by other sessions, or miss jobs already completed concurrently.

### 24.2. REPEATABLE READ and SERIALIZABLE

Within a single transaction, stricter isolation levels enforce stronger snapshot and anomaly guarantees. Once a procedure ends its transaction and starts a new one, **no single snapshot spans the whole procedure**. `COMMIT AND CHAIN` preserves supported characteristics, not the pre-commit transaction identity or snapshot.

### 24.3. Checkpoints and high-water marks for batching

If business rules require processing a fixed set present at job start:

- Record a boundary marker such as `max(job_id)` or a batch generation ID;
- Process only rows within that bounded set;
- Persist committed cursor/checkpoint progress;
- Separate newly arriving work after the watermark;
- Enforce locks and conditions consistently with the isolation level.

Simply looping on `state='pending'` under continuous ingestion can prevent the procedure from ever terminating or cause unintended scope drift.

### 24.4. Do not confuse SKIP LOCKED with strict global ordering

`ORDER BY job_id ... FOR UPDATE SKIP LOCKED` prefers an ordering at query time while skipping rows locked by peers. This fits multi-worker queues allowing **out-of-order processing**, not strict completion in `job_id` order.

### 24.5. SERIALIZABLE may require retries

If a `SERIALIZABLE` transaction fails with `serialization_failure` or deadlock, the application must retry **the failed transaction unit**, never blindly re-running already-committed batches. Safe retries depend on idempotency and checkpoints.

## 25. Locks and VACUUM: why avoid overly long transactions?

A very long transaction can:

- Hold row and table locks for extended periods, blocking other sessions;
- Pin old snapshots, blocking `VACUUM` from reclaiming dead tuples;
- Increase deadlock and lock-contention probability;
- Accumulate large uncommitted changes and WAL;
- Make failure rollbacks slow.

Batched commits shorten lock hold times **per batch**, yet also:

- Increase total transaction commits and WAL flushes;
- Introduce partial progress states;
- Demand tight retry and concurrency controls;
- Do not eliminate all deadlocks or lock waits.

### 25.1. Look beyond total elapsed time

A 30-minute procedure can run as:

~~~text
Style A: 1 transaction lasting 30 minutes → long locks and pinned snapshot.
Style B: 180 transactions of 10 seconds each → shorter locks,
         but must handle partial completion.
~~~

Neither style is universally right. Multi-step financial transfers demand atomicity over short locks; periodic log pruning fits batched commits well.

### 25.2. Monitoring active sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    query_start,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

`xact_start` reflects the backend's current transaction; as a procedure commits batches, `xact_start` resets on every batch. **Never infer total `CALL` duration from a single snapshot of `transaction_age`.**

### 25.3. Lock waits

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_catalog.pg_stat_activity
WHERE wait_event_type = 'Lock';
~~~

Visibility into other sessions' SQL text depends on PostgreSQL role privileges. `pg_blocking_pids` identifies blocking PIDs without granting authority to cancel other users' transactions carelessly.

### 25.4. SKIP LOCKED and deadlocks

`SKIP LOCKED` avoids waiting on **the skipped row locks** during job claiming, yet it does not prevent lock waits or deadlocks on other tables or indexes touched later in the procedure. Analyze all locked objects and lock acquisition order.

### 25.5. Never terminate backends lightly

`pg_cancel_backend` and `pg_terminate_backend` interrupt running queries or sessions, affecting active transactions and applications. In production, verify owner, rollback impact, partial commits, and operational authorization before terminating—never use them as a reflex "debug step" for slow `CALL`s.

## 26. Procedures do not replace workflow engines

A procedure can loop over database batches, yet real distributed workflows involve:

- Network errors calling external APIs;
- Message brokers and delayed deliveries;
- Idempotency keys;
- Dead-letter queues;
- Compensation and reconciliation;
- Retry backoff policies;
- Monitoring and alerting;
- Application permissions and audit trails.

### 26.1. Never treat external services as part of PostgreSQL ACID

If a procedure updates the database and calls an external email extension or outside webhook:

~~~text
DB COMMIT succeeds
External email fails
→ database and email fall out of sync.
~~~

Conversely:

~~~text
External API succeeds
DB ROLLBACK runs
→ external side effect already occurred.
~~~

A standard solution is the **transactional outbox**: write business state and an outbox message row in the same transaction, then let an external worker deliver messages with retries and idempotency. In multi-commit procedures, each batch commit releases its batch of outbox events safely.

### 26.2. Partial commits and explicit state machines

A production pipeline often needs richer states:

~~~text
PENDING → CLAIMED → PROCESSED → PUBLISHED
                   ↘ FAILED_RETRYABLE
                   ↘ FAILED_PERMANENT
~~~

Rather than a simple lab `pending/done`, explicit states prevent situations like "job marked done in DB even though the notification never sent."

### 26.3. Defense-in-depth idempotency

| Layer | Protection example |
| --- | --- |
| Database | Unique constraint on `job_key`, guarded state transitions |
| Batch checkpoint | Committed `last_processed_id` / batch ID |
| External request | Target-supported idempotency key |
| Messaging | Consumer inbox / deduplication table |
| Reconciliation | Scheduled sweeper detecting and repairing gaps |

Never treat "the `CALL` returned without an exception" as sufficient proof of completion; verify **durable state records**.

### 26.4. Network drops immediately after COMMIT

A client can lose its network connection right after PostgreSQL commits and before receiving the acknowledgment. The client sees a timeout or connection error and **cannot tell whether the commit succeeded**. Idempotency keys and status-lookup queries protect against blind retries.

## 27. Avoid DDL prohibited inside transactions

Certain PostgreSQL commands must execute outside transaction blocks or under special rules, such as `CREATE INDEX CONCURRENTLY`.

Never assume that because a top-level `CALL` can `COMMIT`, it can run outside-transaction DDL inside a procedure.

### 27.1. Pattern to avoid

~~~sql
-- Pattern to avoid:
--
-- CREATE PROCEDURE proc_lab_349.build_index()
-- LANGUAGE plpgsql
-- AS $$
-- BEGIN
--     COMMIT;
--     CREATE INDEX CONCURRENTLY ...; -- disallowed inside a procedure
-- END;
-- $$;
~~~

`CREATE INDEX CONCURRENTLY` has strict execution rules incompatible with PL/pgSQL procedure transaction contexts. For online index builds, run the command directly from your **migration runner or client** in autocommit mode and watch for `INVALID` indexes if a build fails.

### 27.2. Transaction control does not waive DDL transaction restrictions

Every SQL statement inside a procedure still obeys its own transaction rules. Procedures do not bypass isolation, lock-mode, privilege, or non-transactional DDL restrictions.

### 27.3. Consequences of committed DDL

If a procedure executes valid DDL across staged commits, a subsequent failure cannot roll back DDL committed in earlier transactions. Schema migrations demand proper change management, dependency checks, and migration-level rollback scripts rather than relying on a single job-end `ROLLBACK`.

## 28. Diagnosing invalid transaction termination

When you encounter:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... at COMMIT
~~~

do not start by swapping `COMMIT` for `ROLLBACK`: both are governed by the exact same transaction-context restrictions. Identify **which prerequisite you violated**.

### 28.1. Root-cause checklist

1. Is `CALL` running inside `BEGIN ... COMMIT`?
2. Is JDBC `autoCommit` set to `false`?
3. Did Spring `@Transactional` or an ORM transaction manager open a transaction?
4. Was the procedure called at top level, or via an intermediate `SELECT`/function?
5. Is the procedure (or a child procedure) declared `SECURITY DEFINER`?
6. Does the definition include a `SET ...` clause?
7. Is `COMMIT` inside a `BEGIN ... EXCEPTION ... END` block?
8. Is the procedure iterating over a DML `... RETURNING` cursor loop?
9. Does a migration tool or SQL client implicitly wrap statements in a transaction?
10. Is the PostgreSQL server or driver version incompatible with the syntax/behavior used?

### 28.2. Inspect how the procedure is defined

~~~sql
SELECT
    p.oid::regprocedure AS procedure_signature,
    p.prokind,
    p.prosecdef,
    p.proconfig
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'proc_lab_349'::regnamespace
  AND p.prokind = 'p'
ORDER BY p.oid::regprocedure::text;
~~~

Explanation:

- `prokind = 'p'` identifies procedures;
- `prosecdef` indicates `SECURITY DEFINER`;
- `proconfig` lists routine-level `SET` settings, if any.

Note that `p.oid::regprocedure` displays exact signatures, distinguishing overloaded procedures across parameters and namespaces.

### 28.3. Check client configuration

In `psql`:

~~~text
\echo :AUTOCOMMIT
~~~

In JDBC:

~~~java
System.out.println(connection.getAutoCommit());
~~~

In Spring: inspect active transaction interceptors, transaction managers, propagation, and call stack. **Never rely on a static config value alone to prove the backend isn't in an explicit transaction** when proxies or wrappers are involved.

### 28.4. Fixes matched to actual requirements

| Actual requirement | Recommended fix |
| --- | --- |
| Entire operation must be atomic | Remove `COMMIT`/`ROLLBACK` from the procedure; let caller manage the transaction |
| Must commit per batch | Invoke via standalone top-level `CALL` outside explicit transactions, meeting all restrictions |
| Procedure requires `SECURITY DEFINER` | Redesign privileges/boundaries or switch to caller-owned transactions |
| Procedure has a `SET` clause | Remove transaction control from that procedure; configure settings elsewhere |
| Catch per-row errors | Use an inner `EXCEPTION` block, placing `COMMIT` after the block ends |
| Save progress if a batch fails | Use explicit status/idempotency tables and retry/reconciliation |
| Large cursor loop | Refactor into keyset/limit batches instead of holding a long cursor |

### 28.5. Companion error: current transaction is aborted

After any statement fails inside an explicit transaction, subsequent commands fail with:

~~~text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
~~~

This is a **secondary consequence of an earlier error**, not the root cause. Look at **the very first error** before this message and issue `ROLLBACK` to clear the transaction.

### 28.6. Regular procedures do not hit this error

~~~sql
BEGIN;
CALL proc_lab_349.demo_block();
COMMIT;
~~~

When a procedure contains no internal transaction control (for example only `RAISE NOTICE`), calling it inside `BEGIN` is completely valid. Never claim every `CALL` inside `BEGIN` is prohibited.

## 29. Monitoring batch procedures without assuming atomicity

### 29.1. Count job states

~~~sql
SELECT
    state,
    COUNT(*) AS jobs
FROM proc_lab_349.jobs
GROUP BY state
ORDER BY state;
~~~

### 29.2. Inspect per-batch commit logs

~~~sql
SELECT
    event_id,
    event_key,
    phase,
    recorded_at
FROM proc_lab_349.event_log
WHERE event_key LIKE 'batch-%'
ORDER BY event_id;
~~~

**Caution:** the lab table writes one log row right before each batch `COMMIT`. In production, a database log row does not prove external side effects succeeded—track each external action's state independently.

### 29.3. Track a run ID across invocations

Running the procedure multiple times repeats labels like `batch-1` and `batch-2`. Production jobs should assign a unique `run_id`/`batch_id` recording:

- Start and end timestamps;
- Claimed, succeeded, and failed job counts;
- Last committed checkpoint;
- Sanitized error codes and messages;
- Retry count and owner;
- Procedure/migration version.

Never rely on identity sequence `event_id` gaps to infer committed transactions: sequence values **are consumed even when transactions roll back**.

### 29.4. Total CALL duration vs. per-transaction age

A `CALL` may run for 10 minutes while committing every 10 seconds. `pg_stat_activity.xact_start` only reflects the currently active sub-batch transaction, not **when `CALL` started**. Record **total `CALL` duration** and per-batch metrics in the application or job tracker.

### 29.5. pg_stat_statements and logging

When `pg_stat_statements` is enabled, it tracks aggregate execution stats per statement pattern, though it does not replace internal batch progress tables or batch logs. Detailed statement logging adds overhead and risk of leaking parameters; follow observability policies.

### 29.6. EXPLAIN ANALYZE with CALL

Never treat `EXPLAIN (ANALYZE) CALL ...` as a safe read-only diagnostic on self-committing procedures. `EXPLAIN` targets plannable queries like `SELECT`, not multi-transaction procedural `CALL` flows. To tune heavy SQL **inside a procedure**, extract those queries into lab benchmarks or use safe logging/`auto_explain` where permitted.

Above all, **never run data-executing plan tools on production without assessing side effects**.

## 30. Common misconceptions about CALL and transaction control

| Misconception | Reality |
| --- | --- |
| Every procedure can `COMMIT` | Only when called in an eligible context and free of all restrictions |
| `CALL` inside `BEGIN` is forbidden | `CALL` is valid; only internal transaction control is forbidden |
| A procedure with `INSERT` behaves like one with `COMMIT` | Transaction ownership differs completely |
| `CALL` from Java is always top-level | Frameworks or drivers often open implicit transactions |
| `autoCommit=false` still lets procedures self-commit | Creates an explicit transaction context where internal `COMMIT` is forbidden |
| Spring `@Transactional` makes procedure `COMMIT` safer | Spring's transaction conflicts with internal `COMMIT` |
| `REQUIRES_NEW` lets a procedure end its own transaction | `REQUIRES_NEW` still opens a caller transaction, blocking internal `COMMIT` |
| After `COMMIT` in a procedure you must run `START TRANSACTION` | PostgreSQL starts the next transaction automatically in PL/pgSQL |
| PL/pgSQL `BEGIN` equals SQL `BEGIN` transaction | `BEGIN ... END` is a code block, not a transaction |
| `COMMIT` in a procedure keeps the whole job atomic | Multiple `COMMIT`s split atomicity |
| Errors at the end of `CALL` roll back everything | Already-committed batches stay committed |
| `ROLLBACK` inside a procedure undoes earlier committed batches | Rolls back only the current uncommitted transaction |
| A trailing `ROLLBACK` acts as a full dry run | Prior commits remain permanent |
| A procedure raising an error had zero side effects | Side effects from prior committed transactions persist |
| Retrying the whole `CALL` is always safe | Can duplicate writes, emails, or charges without idempotency |
| Each `COMMIT` requires explicit `START TRANSACTION` | PostgreSQL opens the next transaction implicitly |
| `COMMIT AND CHAIN` preserves the same snapshot across commits | Preserves supported characteristics, **not** the snapshot |
| `CALL parent → CALL child` can never commit in child | Valid `CALL`/`DO` chains permit transaction control |
| Top-level `CALL` overrides an intervening `SELECT function` | Intervening `SELECT function` blocks deeper transaction control |
| `SECURITY DEFINER` only changes privileges, not `COMMIT` | `SECURITY DEFINER` procedures forbid transaction control |
| Procedure `SET search_path` does not affect `COMMIT` | Procedures with a `SET` clause forbid transaction control |
| `COMMIT` inside an `EXCEPTION` block works because it's handled | Exception blocks are subtransactions where `COMMIT`/`ROLLBACK` are forbidden |
| `WHEN OTHERS` can undo earlier committed batches | Handles only the subtransaction's errors |
| PL/pgSQL `SAVEPOINT` works like client SQL savepoints | PL/pgSQL does not support direct `SAVEPOINT` statements like SQL clients |
| `FOR r IN SELECT` + `COMMIT` streams lightly forever | Converts to a holdable cursor and materializes at first commit |
| Committing every single row is fastest | Multiplies WAL and transaction overhead |
| `UPDATE RETURNING` cursor loops also allow per-row `COMMIT` | Transaction control is forbidden in non-read-only cursor loops |
| `SKIP LOCKED` returning 0 proves zero pending jobs exist | Other workers may currently hold locks on remaining jobs |
| `SKIP LOCKED` guarantees strict processing order | Locked rows are skipped out of order |
| `SKIP LOCKED` eliminates all deadlocks | Skips only specific claimed row locks, not all table/index locks |
| Locks and snapshots survive across `COMMIT` | Transaction-level locks release; snapshots advance |
| `COMMIT AND CHAIN` keeps transactions in one ACID unit | Every `COMMIT` remains an independent atomicity boundary |
| Rolled-back identity sequences leave no gaps | Sequences advance permanently even on rollback |
| No `BEGIN` in Java code means no explicit transaction | ORMs, interceptors, or pools may open transactions |
| `CALL` working in `psql` means it will work in Spring | Transaction wrappers differ |
| `CREATE INDEX CONCURRENTLY` works in a procedure after `COMMIT` | Prohibited inside procedures due to non-transactional rules |
| `pg_stat_activity.xact_start` shows when `CALL` began | Across commits, it only shows the current batch's transaction start |
| `EXPLAIN ANALYZE CALL` previews safely without writes | Never assume `CALL` is a read-only preview |
| Swapping `COMMIT` for `ROLLBACK` fixes `invalid transaction termination` | Both are forbidden inside explicit transactions |
| Every error should be caught by `WHEN OTHERS` | Masks real failures and corrupts state |
| Partial commits are always better for performance | Must weigh against atomicity, WAL, retries, and contention |
| Schema-qualifying a procedure eliminates need for `EXECUTE` security | `EXECUTE` and table privileges still must be managed |

## 31. Practice exercises

Exercises use schema `proc_lab_349`. Some examples **intentionally raise errors**; run only in a lab database and observe transaction state. Where SQL samples show `...`, treat them as placeholders to replace with valid names/statements, not runnable SQL verbatim. Before any DML test, identify affected rows and never run against production tables.

### Exercise 1 — Distinguishing CALL and SELECT

Write two calls:

~~~sql
SELECT public.add_two_numbers(2, 3);
CALL public.print_greeting('An');
~~~

**Question:** Why can't you write `SELECT print_greeting('An')` treating the procedure like a value-returning SQL function?

### Exercise 2 — Defining a procedure

Create a procedure taking `IN p_message text` and emitting `RAISE NOTICE`. Call it with `CALL` from `psql`. **Question:** Does it need `COMMIT` to emit the notice?

### Exercise 3 — INOUT

Create a procedure with `INOUT p_counter integer` adding 1. Call `CALL(...5)` and observe the output row. **Question:** How does this differ from a function with `RETURNS integer`?

### Exercise 4 — CALL is not an automatic COMMIT

~~~sql
BEGIN;
CALL public.print_greeting('Bình');
ROLLBACK;
~~~

**Question:** Why is `CALL` still valid inside a transaction block when the procedure executes no `COMMIT`/`ROLLBACK`?

### Exercise 5 — Standalone call with two COMMITs

~~~sql
CALL proc_lab_349.commit_two_phases('exercise-05');
~~~

**Question:** How many transactions committed inside the procedure, and do the two log rows belong to the same transaction?

**Answer:** Two separate transactions.

### Exercise 6 — CALL inside BEGIN rejected

~~~sql
BEGIN;
CALL proc_lab_349.commit_two_phases('exercise-06');
ROLLBACK;
~~~

**Exercise:** Record the first error, explain why internal `COMMIT` was prohibited, and verify no log rows were committed for key `exercise-06`.

### Exercise 7 — JDBC autoCommit

A connection calls `setAutoCommit(false)` then `CALL commit_two_phases`.

**Question:** Why does driver/app-managed transaction state cause internal `COMMIT` to fail? How does `autoCommit(true)` differ when no outer wrapper exists?

### Exercise 8 — BEGIN in PL/pgSQL

In:

~~~sql
CREATE PROCEDURE public.demo()
LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'hi';
END;
$$;
~~~

**Question:** Does this `BEGIN` open an SQL transaction?

**Answer:** No, it is a PL/pgSQL block delimiter.

### Exercise 9 — Automatic new transactions

A procedure executes `INSERT A; COMMIT; INSERT B; COMMIT;`.

**Exercise:** Diagram the transaction boundaries and explain why there is no standalone `START TRANSACTION` inside the procedure body.

### Exercise 10 — Failure after first commit

~~~sql
CALL proc_lab_349.fail_after_first_commit('exercise-10');
~~~

**Question:** Even though `CALL` errored, which row committed? Verify with a fresh `SELECT`.

**Answer:** `already-committed` exists; `not-committed` was not committed.

### Exercise 11 — Mid-procedure ROLLBACK

~~~sql
CALL proc_lab_349.rollback_middle('exercise-11');
~~~

**Question:** Why does only `after-rollback` appear in the log after `CALL`?

### Exercise 12 — Retries and idempotency

A procedure spans two transactions: recording an invoice, then sending an email. Attempt 1 commits the invoice but fails on email; the client retries the entire `CALL`.

**Exercise:** Design an idempotency key, delivery status, and outbox to prevent duplicate invoices or emails.

### Exercise 13 — COMMIT AND CHAIN

Write a procedure using `COMMIT AND CHAIN` between two batches.

**Question:** What does `AND CHAIN` preserve, and what does it **not** preserve regarding transaction identity and snapshots?

### Exercise 14 — Isolation levels

Suppose a procedure runs under `READ COMMITTED`: between batch 1 and batch 2, another session inserts and commits a new job.

**Question:** Can batch 2 see the new job? If you need to process a fixed dataset, how would you design a high-water mark or snapshot boundary?

### Exercise 15 — Nested CALL

~~~sql
CALL proc_lab_349.parent_call('exercise-15');
~~~

**Question:** Why is the internal `COMMIT` inside `child_commit` allowed even though it wasn't called directly by the client?

### Exercise 16 — Intervening SELECT function

Given the call stack:

~~~text
CALL parent()
  → SELECT f()
    → CALL child()
      → COMMIT
~~~

**Exercise:** Explain why `child` is prohibited from committing even though `parent` was called at top level.

### Exercise 17 — SECURITY DEFINER

Create a `SECURITY DEFINER` procedure that only runs `RAISE NOTICE`. Then inspect what happens if `COMMIT` is added.

**Question:** Is the restriction caused by privileges or transaction context? Does autocommit make it go away?

### Exercise 18 — SET clause

Why does `CREATE PROCEDURE ... SET search_path = ...` restrict transaction control? If you need both schema safety and commits, how should you redesign it?

### Exercise 19 — EXCEPTION block

A developer writes:

~~~text
BEGIN
    INSERT ...
    COMMIT;
EXCEPTION WHEN OTHERS THEN
    ...
END;
~~~

**Question:** Why is `COMMIT` invalid inside a block with an exception handler?

### Exercise 20 — COMMIT after an EXCEPTION block

Write an inner `BEGIN ... EXCEPTION ... END` block handling SQL errors, then place `COMMIT` **outside** the inner block.

**Question:** What scope does the subtransaction roll back versus the outer transaction?

### Exercise 21 — SAVEPOINT

A PL/pgSQL routine attempts `SAVEPOINT s1; ROLLBACK TO s1;`.

**Exercise:** Explain the restriction and show how to use an `EXCEPTION` block to roll back changes made inside that block.

### Exercise 22 — Cursor loop

In `FOR r IN SELECT ... LOOP ... COMMIT; END LOOP`, what does the first `COMMIT` convert the cursor into?

**Answer:** A holdable cursor, materializing the remaining query results.

### Exercise 23 — DML RETURNING loop

A procedure tries `FOR r IN UPDATE jobs ... RETURNING ... LOOP COMMIT; END LOOP`.

**Question:** Is transaction control allowed inside a loop driven by a non-read-only command? Show how to batch using standalone `UPDATE` queries instead.

### Exercise 24 — GET DIAGNOSTICS

After a multi-row `UPDATE`, run:

~~~sql
GET DIAGNOSTICS v_count = ROW_COUNT;
~~~

**Question:** Why is relying on this actual count safer than assuming `LIMIT 100` always updates 100 jobs?

### Exercise 25 — Processing with batch size 2

Reset or insert six `pending` jobs in the lab, then run:

~~~sql
CALL proc_lab_349.process_pending_jobs(2);
~~~

**Expected without contention:** three batches, each updating and committing up to two rows.

### Exercise 26 — Invalid batch size

~~~sql
CALL proc_lab_349.process_pending_jobs(0);
~~~

**Question:** What does validating before updating protect against? Why enforce an upper bound on batch size?

### Exercise 27 — SKIP LOCKED

Session A holds a lock on job 1; session B runs `FOR UPDATE SKIP LOCKED LIMIT 2`.

**Question:** Does B necessarily claim job 1? If skipped, can you conclude job 1 is finished?

### Exercise 28 — Returning 0 rows doesn't guarantee an empty queue

A worker runs `SKIP LOCKED` and gets 0 rows even though 10 pending rows are locked by peers.

**Exercise:** Propose a scheduler, retry, or reconciliation mechanism so jobs aren't missed if peer workers roll back.

### Exercise 29 — At-most-once vs. exactly-once

A procedure sets `state='done'` and calls an external email API.

**Question:** Why doesn't database state alone guarantee an email sends exactly once? Explain the role of outbox and idempotency.

### Exercise 30 — Atomic vs. partial progress

A transfer moves 100 from wallet A to wallet B; a teammate suggests committing right after the debit to shorten lock holds.

**Exercise:** Explain the atomicity violation and why a non-committing procedure inside a caller transaction is required.

### Exercise 31 — Spring @Transactional

A `@Transactional` method invokes a self-committing procedure.

**Question:** What causes the error, and why doesn't switching to `REQUIRES_NEW` fix it?

### Exercise 32 — Spring NOT_SUPPORTED

`NOT_SUPPORTED` suspends an existing transaction, yet what else must be checked before assuming internal commits will work?

**Hint:** transaction manager, datasource, connection autocommit, driver `CALL` syntax, call stack, and `SECURITY DEFINER`/`SET`/`EXCEPTION` restrictions.

### Exercise 33 — psql autocommit

Run in `psql`:

~~~text
\echo :AUTOCOMMIT
~~~

**Question:** If autocommit is `off` and `psql` opens an implicit transaction, what error will a self-committing procedure hit?

### Exercise 34 — Migration runners

A migration tool wraps every SQL file in a single transaction, and one file contains `CALL process_pending_jobs(2)`.

**Exercise:** Explain why it fails and describe two ways to restructure it: running as a standalone job or using caller-managed transactions.

### Exercise 35 — CREATE INDEX CONCURRENTLY

A procedure runs `COMMIT; CREATE INDEX CONCURRENTLY ...`.

**Question:** Why shouldn't procedures be used to execute online index builds? How should a migration runner or client issue it directly?

### Exercise 36 — Locks

A batch procedure commits every 10,000 rows, causing p95 web-service latency to spike from lock waits.

**Exercise:** Measure `pg_stat_activity`, `pg_blocking_pids`, transaction duration, rows per batch, and retry contention; propose smaller batches or off-peak scheduling if business rules allow.

### Exercise 37 — One million commits

If a procedure commits after every single row across one million rows, what costs accumulate?

**Hint:** WAL flushes, transaction setup, lock acquisition, context switches, CPU, throughput, and replication lag depending on workload.

### Exercise 38 — pg_stat_activity xact_start

A `CALL` runs for 20 minutes committing every 10 seconds; `xact_start` shows the current transaction is 2 seconds old.

**Question:** Does that mean the whole `CALL` has only been running 2 seconds? What metric tracks total `CALL` duration?

### Exercise 39 — Sequence gaps

An `INSERT` into an identity-column table rolls back.

**Question:** Why can `event_id` show gaps even though no row exists? Why can't missing IDs prove a committed transaction disappeared?

### Exercise 40 — Invalid transaction termination runbook

The app reports:

~~~text
ERROR: invalid transaction termination
CONTEXT: PL/pgSQL function ... at COMMIT
~~~

**Exercise:** Build a minimal checklist covering explicit transactions, JDBC `autoCommit`, Spring transaction managers, nested `CALL`/`SELECT`, `SECURITY DEFINER`, `SET` clauses, `EXCEPTION` blocks, and cursor loops.

### Exercise 41 — Production incident with partial commits

A batch `CALL` timed out; the dashboard shows 75% of jobs `done`. What must you check before retrying?

**Suggested answer:** Check committed checkpoints and states, verify external side effects, ensure idempotency, and claim only remaining pending jobs or follow explicit retry rules.

### Exercise 42 — COMMIT AND CHAIN with SERIALIZABLE

A procedure runs `COMMIT AND CHAIN` after each batch under `SERIALIZABLE` isolation.

**Question:** Do batches share the same snapshot? If one batch hits a serialization failure, is retrying the entire `CALL` safe?

### Exercise 43 — Inspecting procedure metadata

Query `pg_proc` for `prokind`, `prosecdef`, and `proconfig` across procedures in `proc_lab_349`.

**Question:** Which transaction-control restriction does each column help diagnose?

### Exercise 44 — Permissions and schemas

A procedure needs permission to update tables in another schema.

**Exercise:** Explain why switching to `SECURITY DEFINER` to gain privileges breaks internal `COMMIT`s, and propose a safe alternative permission design.

### Exercise 45 — Deadlocks

Two transactions update jobs in opposite lock orders and deadlock.

**Question:** Do internal `COMMIT`s eliminate deadlocks completely? How would you standardize lock ordering, batch sizes, and retries?

### Exercise 46 — Error handling without swallowing errors

A procedure uses `WHEN OTHERS THEN RAISE NOTICE 'ignored'` and proceeds to commit.

**Exercise:** Describe the data-integrity risk. Which specific SQLSTATEs should be caught, and which errors must be re-raised?

### Exercise 47 — Managing transaction ownership

Design two APIs:

~~~text
complete_job_atomic(job_key)
process_pending_jobs(batch_size)
~~~

**Question:** Which API is safe inside `@Transactional`? Which requires an independent top-level `CALL`? Document rollback and retry contracts for both.

### Exercise 48 — Post-deployment monitoring

List metrics to watch after tuning batch transaction sizes: transaction duration, locks, deadlocks, pending/done counts, retries, WAL/replication, p95 latency, error counts, and checkpoints.

### Exercise 49 — Aborted caller transaction state

Inside an explicit transaction, a `CALL` raises an error. The next statement fails with `current transaction is aborted`.

**Question:** Which error is the root cause, and which is secondary? What recovery step must the client take?

### Exercise 50 — Capstone: order processing workflow

Design two components:

**Part A — Single-order ACID operation:** update order status, inventory, and audit log atomically in one transaction. Choose a procedure **with no internal `COMMIT`** invoked inside the application's transaction.

**Part B — Background job processing 50,000 independent orders:** select a batch size, checkpoints, and a top-level procedure committing per batch. Enforce unique business keys, safe retries, and an outbox for external notifications.

Deliverables:

1. Transaction boundary diagrams for both parts.
2. SQL signatures for the procedures.
3. Where `CALL` may and may not be wrapped in `BEGIN`.
4. Exception handling design keeping `COMMIT` outside subtransaction blocks.
5. Idempotency design and handling post-commit network timeouts.
6. Strategy to avoid lock contention and missed jobs with `SKIP LOCKED`.
7. JDBC/Spring invocation code for both styles.
8. Test suite covering mid-batch failures, deadlocks, retries, invalid inputs, and partial progress.
9. Operational metrics and rollback/fix-forward plans.
10. Explanation of why already-committed transactions cannot be undone by a trailing `ROLLBACK`.

## 32. Checklist before deploying transaction-controlling procedures

### 32.1. Transaction design

- [ ] Clearly defined whether **the caller or the procedure owns transaction boundaries**.
- [ ] For all-or-nothing work, the procedure executes **no** internal `COMMIT`/`ROLLBACK`.
- [ ] For batched commits, **partial progress** is explicitly accepted and handled.
- [ ] Every `COMMIT` documents exactly which state becomes durable.
- [ ] Idempotency and retry mechanisms avoid reprocessing committed work.
- [ ] Checkpoints, `run_id`, and run-tracking mechanisms exist.
- [ ] Policies cover network failures occurring right after `COMMIT`.
- [ ] Reconciliation exists for half-finished states.
- [ ] No logic assumes a trailing `ROLLBACK` undoes earlier commits.

### 32.2. Valid CALL conditions

- [ ] Transaction-controlling `CALL` runs at top level, outside `BEGIN`.
- [ ] Frameworks do not implicitly open an outer transaction.
- [ ] Any nested calls stay strictly within valid `CALL`/`DO` chains.
- [ ] No intervening `SELECT function(...)` blocks transaction control.
- [ ] Committing procedures are **not** `SECURITY DEFINER`.
- [ ] Committing procedures declare **no** `SET` clause.
- [ ] `COMMIT`/`ROLLBACK` never execute inside an active `EXCEPTION` block.
- [ ] Cursor loops account for holdable materialization and DML `RETURNING` limits.
- [ ] Non-transactional DDL like `CREATE INDEX CONCURRENTLY` is not invoked improperly inside procedures.
- [ ] PostgreSQL version and `EXECUTE` privileges are verified.

### 32.3. Application integration

- [ ] JDBC `autoCommit` and transaction managers are verified end-to-end.
- [ ] Spring `@Transactional` / propagation matches the procedure's contract.
- [ ] Not relying on `REQUIRES_NEW` to bypass internal commit limits.
- [ ] Connection pools reset transaction and session state cleanly.
- [ ] `CALL` invocations handle errors and execute caller rollback when needed.
- [ ] Clients distinguish **call failed** from **all work rolled back**.
- [ ] APIs document return/`OUT` semantics and partial-completion effects.
- [ ] External side effects use outboxes, idempotency keys, and reconciliation.
- [ ] Table, schema, and procedure grants follow least privilege.

### 32.4. Performance and operations

- [ ] Batch sizes are bounded and benchmarked.
- [ ] WAL volume, commit rate, lock waits, and total duration are measured.
- [ ] No giant cursors held across commits expecting unbounded streaming.
- [ ] Row-claiming queries address concurrency and starvation.
- [ ] Handled cases where `SKIP LOCKED` returns 0 despite locked pending rows.
- [ ] Appropriate timeouts and rate limits prevent holding transactions over network I/O.
- [ ] Metrics track batches, rows, retries, failures, and checkpoints.
- [ ] Tested deadlocks, serialization failures, connection drops, and process crashes.
- [ ] Post-deploy monitoring and rollback/fix-forward plans exist.
- [ ] No DML/commit demos run directly against production data.

## 33. Workflow for evaluating an existing procedure

When inheriting an existing procedure with unclear transaction ownership, follow these steps before editing code:

### Step 1 — Read the signature and definition

~~~sql
SELECT
    p.oid::regprocedure AS procedure_signature,
    pg_catalog.pg_get_functiondef(p.oid) AS definition
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'proc_lab_349'::regnamespace
  AND p.prokind = 'p'
ORDER BY p.oid::regprocedure::text;
~~~

This is a **metadata-read query**; definition visibility depends on role privileges. Check for `COMMIT`, `ROLLBACK`, `EXCEPTION`, `SECURITY DEFINER`, or `SET` clauses.

### Step 2 — Trace the application call path

~~~text
HTTP / scheduler
  |
  +-- Service method (@Transactional?)
  |
  +-- Repository / JDBC
  |
  +-- Connection (autoCommit?)
  |
  +-- CALL procedure()
        |
        +-- CALL child()?
        +-- SELECT helper()?
        +-- COMMIT?
~~~

Reading the SQL body alone is not enough; transaction-control eligibility depends on **how it is actually called at runtime**.

### Step 3 — Test mid-execution failure semantics

In a lab database:

1. Let the first batch succeed and commit.
2. Intentionally trigger a failure in a later batch.
3. Inspect committed rows.
4. Re-run the procedure.
5. Verify no duplicate writes or repeated side effects occur.
6. Verify rows do not remain stuck in an in-progress state.

### Step 4 — Measure transaction counts and locks

Observe transaction durations, lock waits, WAL generation, batch progress, and external side effects—not just the runtime of one `CALL`.

### Step 5 — Confirm the contract

| Observation | Typically appropriate decision |
| --- | --- |
| Procedure serves an HTTP request needing atomicity | Remove internal `COMMIT`; let caller/framework manage transactions |
| Background job processes independent batches | Top-level `CALL` with internal commits + idempotency |
| Procedure requires `SECURITY DEFINER` | Never use internal transaction control in that procedure |
| Caller already opens an explicit transaction | Procedure must never self-commit |
| Massive query holds cursor too long | Switch to keyset batching instead of committing inside a cursor |
| Multiple external side effects | Use transactional outbox/workflow + retry semantics |
| Task requires one consistent snapshot end-to-end | Keep in one transaction or design explicit watermarks/checkpoints; never assume `COMMIT AND CHAIN` preserves snapshots |

### Step 6 — Document operational contracts

In API and module docs, record:

- Required calling context (top-level vs. inside transaction).
- Required roles and privileges.
- Commit points.
- Success/failure result semantics.
- Idempotency and retry behavior.
- Batch size and concurrency limits.
- Critical error codes and recovery steps.
- Supported PostgreSQL versions.

## 34. Frequently asked questions

### 34.1. I ran CALL inside BEGIN and got invalid transaction termination. Does PostgreSQL not support procedures?

No. PostgreSQL supports procedures, and `CALL` inside an explicit transaction is valid as long as the procedure does not terminate the transaction. The error occurs because an **internal `COMMIT`/`ROLLBACK`** attempted to close a transaction owned by the **caller**.

### 34.2. My CALL works in psql yet fails in Spring. Why?

`psql` sends an independent top-level `CALL`, whereas Spring `@Transactional` or JDBC `autoCommit=false` opens an explicit transaction. Inspect the actual runtime transaction context and unify the contract.

### 34.3. If a procedure has no COMMIT, who commits its INSERTs?

If the caller is inside an explicit transaction, the caller decides `COMMIT`/`ROLLBACK`. If the client sends a standalone `CALL` in autocommit mode and the procedure does no transaction control, PostgreSQL wraps the statement in an implicit transaction and commits upon completion per autocommit rules.

### 34.4. Can I place COMMIT inside an IF branch?

Yes, a `COMMIT` inside an `IF` block is valid **provided the overall transaction-control context allows it**. `IF` itself creates no barrier. However, `COMMIT` inside an active `EXCEPTION` block remains prohibited.

### 34.5. Can I COMMIT inside a loop?

Conditionally, inside an eligible top-level procedure. Keep in mind cursor loops convert to holdable/materialized cursors at the first commit, and cursor loops driven by non-read-only commands (such as `UPDATE ... RETURNING`) forbid transaction control.

### 34.6. Can I ROLLBACK TO SAVEPOINT inside a procedure?

PL/pgSQL does not support direct SQL client `SAVEPOINT` commands. Use **`BEGIN ... EXCEPTION ... END` blocks** for local error recovery, remembering you cannot `COMMIT`/`ROLLBACK` while inside an active exception-handling block.

### 34.7. Does COMMIT AND CHAIN preserve the same transaction ID?

No. It starts a new transaction preserving supported transaction characteristics; the prior transaction's identity, snapshot, and locks are not carried across commits.

### 34.8. Can CREATE PROCEDURE with SECURITY DEFINER self-COMMIT with elevated privileges?

No. PostgreSQL prohibits transaction-control statements inside `SECURITY DEFINER` procedures.

### 34.9. Does adding SET work_mem to CREATE PROCEDURE affect transaction control?

Yes. Any procedure declared with a `SET` clause cannot execute transaction-control statements, even via top-level `CALL`.

### 34.10. If a procedure errors, should I retry the entire CALL?

Only when the workflow is **idempotent** and committed progress can be detected safely. A failure after an internal `COMMIT` leaves earlier transactions permanently persisted.

### 34.11. Does SKIP LOCKED guarantee every queue item executes exactly once?

No. It merely prevents workers from blocking on already-locked rows. Exactly-once external processing requires idempotency, state tracking, retries, and reconciliation.

### 34.12. How should I choose a batch size?

Base it on latency, lock contention, throughput, WAL rate, and real data. Start with a conservative size, benchmark under representative concurrency, monitor errors, and enforce a safe upper bound—no single number fits every table.

## 35. Official PostgreSQL documentation

The links below point to **current PostgreSQL documentation**; before deploying in production, switch to **your exact running major version**:

- [SQL CALL](https://www.postgresql.org/docs/current/sql-call.html): procedure invocation syntax, input/output parameters, and transaction-control limits when `CALL` runs inside an explicit transaction block.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html): procedure definitions, `SECURITY DEFINER`, `SET` clauses, and transaction restrictions.
- [PL/pgSQL — Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): core reference for `COMMIT`, `ROLLBACK`, `AND CHAIN`, top-level/nested `CALL` and `DO`, cursor loops, and subtransactions.
- [PL/pgSQL — Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE NOTICE`, `RAISE EXCEPTION`, and SQLSTATEs.
- [PL/pgSQL — Trapping Errors](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING): `BEGIN ... EXCEPTION ... END` and subtransaction semantics.
- [PL/pgSQL — Cursors](https://www.postgresql.org/docs/current/plpgsql-cursors.html): cursor usage and result-set lifecycles.
- [SQL BEGIN](https://www.postgresql.org/docs/current/sql-begin.html): client explicit transaction blocks.
- [SQL COMMIT](https://www.postgresql.org/docs/current/sql-commit.html): committing transactions and `AND CHAIN`.
- [SQL ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html): aborting transactions and `AND CHAIN`.
- [SAVEPOINT](https://www.postgresql.org/docs/current/sql-savepoint.html): SQL savepoints in caller-managed transactions.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, and snapshot semantics.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, table locks, and deadlocks.
- [SELECT ... FOR UPDATE / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): locking clauses and how `SKIP LOCKED` bypasses locked rows.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and wait events.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): `CONCURRENTLY` and its transaction restrictions.
- [SQL DO](https://www.postgresql.org/docs/current/sql-do.html): anonymous code blocks and transaction rules.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): comparing functions with procedures.

In particular, **`PL/pgSQL Transaction Management`** is the primary reference whenever you hit `invalid transaction termination`. Exact details on permissions, procedural languages, output parameters, and driver behavior vary across versions.

## 36. Summary

**`CALL` invokes a PostgreSQL procedure**—it is not an automatic commit command. Procedures can execute `COMMIT` or `ROLLBACK` to divide work across multiple transactions, **only when invoked in an eligible context**: top-level `CALL` or valid nested `CALL`/`DO` chains, outside any caller-opened explicit transaction block, and free of other restrictions.

Inside a procedure:

- **`COMMIT`** persists the current transaction; subsequent statements continue automatically in a new transaction.
- **`ROLLBACK`** discards uncommitted changes in the current transaction without undoing earlier committed transactions.
- **`COMMIT AND CHAIN` / `ROLLBACK AND CHAIN`** start a new transaction preserving supported characteristics, **without** preserving the old snapshot.
- **`SECURITY DEFINER`**, **`SET` clauses**, **`EXCEPTION` blocks**, and **cursor loops** impose specific transaction-control restrictions.

Two designs should never be mixed carelessly:

| Requirement | Appropriate design |
| --- | --- |
| Business operation needing all-or-nothing atomicity | Procedure **does not self-commit**; caller opens the transaction and decides `COMMIT`/`ROLLBACK` |
| Long batch job of independent chunks | Procedure **self-commits per batch**, invoked at top level with checkpoints, idempotency, and retries |

In Java/JDBC/Spring, **runtime transaction context** matters far more than whether source SQL literally says `BEGIN`. `setAutoCommit(false)` or `@Transactional` forbids internal `COMMIT`s even on a top-level-looking `CALL`. When batch commits are genuinely required, isolate the call boundary, avoid caller-owned transactions, and verify all procedure restrictions.

Finally, **an error from `CALL` never guarantees all work was rolled back** if the procedure already committed earlier batches. Design transaction boundaries around consistency invariants first, and account for partial progress, locking, retries, external side effects, and monitoring before enabling procedure transaction control. With clear boundaries, `CALL` cleanly encapsulates database workflows; with blurry boundaries, it becomes a source of hard-to-recover transaction bugs.
