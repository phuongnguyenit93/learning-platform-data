# WHEN Conditions and Limiting Firing Columns

In PostgreSQL, a trigger does not have to execute its function on every INSERT, UPDATE, or DELETE event. You can declare a **`WHEN` condition** to restrict which rows qualify to run the trigger, or use **`UPDATE OF`** to react only to UPDATE statements that target specific columns. Both mechanisms are valuable for audit logs, updating derived data, emitting state-change events, business checks, and reducing the overhead of frequently fired triggers.

However, the core point of this lesson is: **`UPDATE OF column_name` does not mean "the column's value changed."** It primarily checks **whether the column is listed as a target in the UPDATE statement's SET list**. Conversely, a `WHEN (OLD.column IS DISTINCT FROM NEW.column)` condition checks **whether the old and new values actually differ**, even when one of them is NULL.

Example:

~~~sql
CREATE TRIGGER orders_status_changed
AFTER UPDATE OF status
ON orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

This trigger combines two filters: the UPDATE statement must target the `status` column and the row's status value must actually differ from before. Without `WHEN`, `UPDATE orders SET status = status` can still fire the trigger even though the value stayed the same. Without `UPDATE OF status`, the trigger can detect status changes caused by a BEFORE trigger even when the initial UPDATE statement never mentioned status.

This lesson belongs to the **Triggers and Rules** chapter in the **Database Engine Relational PostgreSQL** module. It covers `CREATE TRIGGER` syntax, `WHEN`, `UPDATE OF`, `OLD`/`NEW`, NULL semantics, BEFORE/AFTER timing, trigger interactions, statement-level trigger limits, generated columns, transition tables, performance, security, and a step-by-step PostgreSQL lab.

## 1. Where Do Triggers Fit in Data Processing?

A simplified view:

~~~text
Client sends INSERT / UPDATE / DELETE
                   |
                   v
          PostgreSQL identifies rows
                   |
                   v
         BEFORE statement triggers
                   |
                   v
       For each row to be processed:
         BEFORE row triggers
          [WHEN evaluated]
             |
             v
       Perform row operation
             |
             v
         AFTER row triggers
          [WHEN evaluated]
          [events queued to run]
                   |
                   v
          AFTER statement triggers
                   |
                   v
      Statement completes / transaction
~~~

This diagram presents the conceptual flow only; detailed execution ordering, transition tables, foreign-key actions, and cases like `INSERT ... ON CONFLICT`, partition row movement, or `MERGE` involve additional rules. Never substitute this diagram for the exact execution documentation of your PostgreSQL version.

### 1.1. Triggers are not the UPDATE's WHERE clause

An `AFTER UPDATE ... WHEN (...)` trigger does not decide whether a row is updated; it decides **whether to execute the trigger action for that row**. The main UPDATE statement still executes according to its WHERE clause and other constraints.

### 1.2. What is a trigger function?

PostgreSQL uses a function returning `trigger` to handle events, typically declared with `LANGUAGE plpgsql`. The function can read variables such as `NEW`, `OLD`, `TG_OP`, and `TG_NAME`.

### 1.3. Why limit invocation counts?

On a table with millions of rows, if every UPDATE invokes an audit function excessively, the database wastes CPU, WAL, index I/O, and storage. `UPDATE OF` and `WHEN` let you express firing conditions **directly in the trigger definition**, avoiding unnecessary work.

## 2. Relevant CREATE TRIGGER Syntax

General pattern:

~~~sql
CREATE TRIGGER trigger_name
{ BEFORE | AFTER | INSTEAD OF }
{ INSERT | UPDATE | DELETE | TRUNCATE }
ON table_name
FOR EACH { ROW | STATEMENT }
WHEN (boolean_condition)
EXECUTE FUNCTION trigger_function();
~~~

This is an abbreviated representation for explanation, **not the complete `CREATE TRIGGER` grammar**. In real SQL, you choose valid combinations of timing, event, and level. The `WHEN` condition has restrictions based on timing and level; it cannot be attached arbitrarily to every combination.

Syntax for targeting columns on UPDATE:

~~~sql
CREATE TRIGGER trigger_name
AFTER UPDATE OF status, amount
ON table_name
FOR EACH ROW
EXECUTE FUNCTION trigger_function();
~~~

They can be combined:

~~~sql
CREATE TRIGGER trigger_name
AFTER UPDATE OF status
ON table_name
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_function();
~~~

### 2.1. FOR EACH ROW

The trigger evaluates each row affected by DML. This is the context where `OLD.column` and `NEW.column` are normally used in `WHEN`.

### 2.2. FOR EACH STATEMENT

The trigger runs per **statement event**, not by the number of rows actually affected. An UPDATE modifying zero rows can still fire a corresponding statement-level trigger. Do not treat a statement-level trigger as a row filter using `OLD`/`NEW`.

### 2.3. BEFORE and AFTER

- **BEFORE row triggers** run before the row operation completes; they can modify `NEW` or skip a row operation via `RETURN NULL`.
- **AFTER row triggers** observe the result of the row operation under execution semantics and are well-suited for auditing or post-update processing.
- **INSTEAD OF triggers** normally attach to views and follow separate rules; do not treat them as AFTER/BEFORE row triggers on physical tables.

## 3. What Is WHEN?

`WHEN` is a **Boolean expression** placed in the trigger definition. PostgreSQL uses its result to decide whether to invoke the trigger function for that event/row.

~~~sql
CREATE TRIGGER accounts_low_balance
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION log_low_balance();
~~~

If the condition is not TRUE, the function is not called for that row.

### 3.1. WHEN vs. IF inside the trigger function

There are two similar ways to express this:

~~~sql
-- Approach A: check in the trigger definition
CREATE TRIGGER example_a
AFTER UPDATE ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION do_work();
~~~

~~~sql
-- Approach B: function checks internally
CREATE FUNCTION do_work()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.balance < 0 THEN
        -- Handle...
    END IF;
    RETURN NEW;
END;
$$;
~~~

Both can guard the same logic branch if the function and condition are designed accordingly, yet **their cost and evaluation timing differ**, especially for AFTER row triggers.

### 3.2. WHEN avoids calling the function when FALSE

If the WHEN condition is not TRUE, PostgreSQL skips calling the trigger function for that row. For AFTER row triggers, this also avoids queuing a trigger event for end-of-statement execution.

### 3.3. Not a general SELECT condition

The WHEN expression is restricted by the trigger context; for instance, **direct subqueries are not allowed** in WHEN. Never write `WHEN (EXISTS (SELECT ...))` expecting PostgreSQL to accept it like an arbitrary WHERE clause.

### 3.4. NULL in WHEN

Just like other SQL Boolean conditions, the trigger fires only when WHEN evaluates to **TRUE**. If the result is FALSE or NULL/UNKNOWN, the function is skipped for that row.

## 4. OLD and NEW: Values Before and After Changes

In a row-level trigger:

| Event | OLD | NEW | Meaning |
|---|---|---|---|
| INSERT | No old row | New row | Inspect values being inserted |
| UPDATE | Old row | New row | Compare before and after |
| DELETE | Old row | No new row | Inspect row being deleted |

### 4.1. WHEN for INSERT

~~~sql
CREATE TRIGGER audit_large_insert
AFTER INSERT ON payments
FOR EACH ROW
WHEN (NEW.amount >= 1000000)
EXECUTE FUNCTION log_large_payment();
~~~

### 4.2. WHEN for UPDATE

~~~sql
CREATE TRIGGER audit_status_change
AFTER UPDATE ON orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

### 4.3. WHEN for DELETE

~~~sql
CREATE TRIGGER audit_important_delete
AFTER DELETE ON customers
FOR EACH ROW
WHEN (OLD.is_vip IS TRUE)
EXECUTE FUNCTION log_vip_delete();
~~~

### 4.4. Do not use NEW on DELETE or OLD on INSERT

Those row records do not exist for the respective events. When designing a multi-event trigger function, branch on `TG_OP` before reading fields that only exist for that event.

## 5. SQL Three-Valued Logic: TRUE, FALSE, and UNKNOWN

This is a common reason WHEN fails to fire as expected.

Suppose:

| OLD.email | NEW.email | `OLD.email <> NEW.email` |
|---|---|---|
| `'a@example.test'` | `'b@example.test'` | TRUE |
| `'a@example.test'` | `'a@example.test'` | FALSE |
| NULL | `'b@example.test'` | NULL/UNKNOWN |
| `'a@example.test'` | NULL | NULL/UNKNOWN |
| NULL | NULL | NULL/UNKNOWN |

With `<>`, comparisons involving NULL return UNKNOWN, so WHEN does not fire.

### 5.1. Use IS DISTINCT FROM

~~~sql
WHEN (OLD.email IS DISTINCT FROM NEW.email)
~~~

This operator provides **NULL-safe** inequality comparison.

| OLD.email | NEW.email | `IS DISTINCT FROM` |
|---|---|---|
| `'a@example.test'` | `'b@example.test'` | TRUE |
| `'a@example.test'` | `'a@example.test'` | FALSE |
| NULL | `'b@example.test'` | TRUE |
| `'a@example.test'` | NULL | TRUE |
| NULL | NULL | FALSE |

### 5.2. When you only care about a specific target state

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

This condition fires the trigger only when status **transitions into** paid. If you only used `NEW.status='paid'`, other UPDATEs on an already-paid row would also fire the trigger.

### 5.3. When you only care about crossing a threshold

~~~sql
WHEN (
    OLD.balance >= 0
    AND NEW.balance < 0
)
~~~

This captures crossing from non-negative to negative, rather than every UPDATE on an already-negative row. If balance can be NULL, define explicitly how NULL should be handled.

## 6. UPDATE OF: Only Checks Columns Appearing in SET

Example:

~~~sql
CREATE TRIGGER orders_amount_targeted
AFTER UPDATE OF amount
ON orders
FOR EACH ROW
EXECUTE FUNCTION log_amount_update();
~~~

This trigger is considered whenever the UPDATE statement lists `amount` in `SET`, following PostgreSQL's rules.

### 6.1. Column is SET, value unchanged

~~~sql
UPDATE orders
SET amount = amount
WHERE order_id = 101;
~~~

The statement targets `amount`, so `AFTER UPDATE OF amount` **can still fire** if the row is updated. An unchanged value does not automatically suppress the trigger.

### 6.2. Another column is SET

~~~sql
UPDATE orders
SET updated_at = CURRENT_TIMESTAMP
WHERE order_id = 101;
~~~

Because `amount` is not targeted in the SET list, a column-specific trigger on `amount` generally **does not fire**, even though the row was updated.

### 6.3. Multiple columns

~~~sql
CREATE TRIGGER orders_business_columns_targeted
AFTER UPDATE OF status, amount, customer_id
ON orders
FOR EACH ROW
EXECUTE FUNCTION log_business_field_update();
~~~

The `UPDATE OF` condition is an **OR across the listed columns**: as long as at least one listed column appears in the target list, the event qualifies. It **does not require all three columns to change**.

### 6.4. Does not compare before/after values on its own

If the requirement is "audit only when the value actually changed," combine `WHEN` with `IS DISTINCT FROM`.

## 7. Why Is UPDATE OF Not a Change Detector?

An UPDATE statement can target a column while keeping its value identical:

~~~sql
UPDATE accounts
SET status = status
WHERE account_id = 1;
~~~

Conversely, **another BEFORE UPDATE trigger** might modify `NEW.status` while the original UPDATE statement only targeted `balance`.

~~~text
UPDATE accounts SET balance = 0 WHERE account_id = 1
              |
              v
BEFORE UPDATE trigger:
    NEW.status := 'suspended'
              |
              v
Row is saved with new status
              |
              v
AFTER UPDATE OF status:
    not fired merely because BEFORE trigger changed status
              |
              v
AFTER UPDATE ... WHEN OLD.status IS DISTINCT FROM NEW.status:
    detects that status actually changed
~~~

This is a **very important** distinction. A column-specific trigger relying solely on `UPDATE OF status` can miss status changes made by BEFORE triggers when the original UPDATE did not list status.

### 7.1. Use AFTER UPDATE without OF when all change sources matter

~~~sql
CREATE TRIGGER accounts_any_status_change
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

This condition does not require status to appear in SET; it inspects the old and new row states.

### 7.2. When UPDATE OF is still appropriate

If the business contract is "react to UPDATE commands explicitly targeting the status column," even if the value stayed the same, `UPDATE OF status` fits. If the business event is "status genuinely changed," check OLD/NEW and account for BEFORE triggers.

### 7.3. WHEN does not prevent the row update itself

When WHEN is FALSE, PostgreSQL may still write a new tuple version for the UPDATE depending on MVCC and plan. To avoid meaningless UPDATEs, consider putting the condition in the UPDATE's WHERE clause or intentionally handling it in BEFORE logic.

## 8. Comparing Common Trigger Definitions

| Definition | When evaluated | Checks whether value actually changed? |
|---|---|---|
| `AFTER UPDATE` | Every updated row | No |
| `AFTER UPDATE OF status` | SET mentions status | No |
| `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status)` | Every updated row, runs function only when status changed | Yes |
| `AFTER UPDATE OF status ... WHEN (OLD.status IS DISTINCT FROM NEW.status)` | SET mentions status and value changed | Yes, within UPDATE OF scope |
| `AFTER UPDATE ... WHEN (NEW.status='paid')` | Row after UPDATE is paid | Not necessarily a state transition |
| `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status='paid')` | Transitioned to paid | Yes |

### 8.1. Choose by event semantics

- "Any command targeting email" -> `UPDATE OF email`.
- "Email actually changed" -> `WHEN (OLD.email IS DISTINCT FROM NEW.email)`.
- "Email went from NULL to non-NULL" -> `WHEN (OLD.email IS NULL AND NEW.email IS NOT NULL)`.
- "Only when email is verified" -> condition on status/verification fields matching business semantics.
- "Any change including after BEFORE triggers" -> usually omit `UPDATE OF` if the column can be altered indirectly.

## 9. Timing of BEFORE Row WHEN

Example:

~~~sql
CREATE TRIGGER validate_new_amount
BEFORE UPDATE OF amount
ON orders
FOR EACH ROW
WHEN (NEW.amount < 0)
EXECUTE FUNCTION reject_negative_amount();
~~~

When a row is processed, PostgreSQL evaluates WHEN **before calling this function**.

### 9.1. When WHEN is FALSE

The function does not run. The row operation continues normally, subject to other triggers and constraints.

### 9.2. When WHEN is TRUE

The function is called and can inspect/modify `NEW` or return NULL to skip the row operation in a BEFORE row trigger, if designed to do so.

### 9.3. The condition sees NEW from earlier BEFORE triggers

When multiple BEFORE row triggers share the same event, firing order matters. An earlier BEFORE trigger can modify NEW, and a later trigger sees the modified NEW values.

### 9.4. Why avoid BEFORE triggers for simple checks?

If you only need `amount >= 0`, a `CHECK(amount >= 0)` constraint is more direct, clearer, and provides stronger integrity enforcement than a hand-written trigger function. Triggers fit cases where logic cannot be expressed as standard constraints or requires intentional side effects.

## 10. Timing of AFTER Row WHEN

For an AFTER row trigger, PostgreSQL evaluates WHEN **immediately after the row modification**, before deciding whether to queue the trigger event.

~~~sql
CREATE TRIGGER audit_status
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION write_status_audit();
~~~

### 10.1. Performance benefit

If an UPDATE modifies 100,000 rows but only 100 rows change status, WHEN avoids queuing 99,900 trigger events to run the function later.

### 10.2. Difference from IF at the top of an AFTER trigger function

If the check lives inside the function, PostgreSQL still schedules and invokes the function for many rows only to skip them immediately. Pushing simple predicates into WHEN can save significant overhead.

### 10.3. Does not reduce the number of rows updated

The WHEN condition optimizes trigger work; it does not mean the UPDATE touched only 100 rows. All 100,000 rows are still processed by the UPDATE statement.

### 10.4. Concurrency considerations

An audit row written after UPDATE still belongs to the transaction. If the transaction rolls back, the audit INSERT inside the same PostgreSQL transaction also rolls back, excluding out-of-DB side effects or sequence advancements.

## 11. Ordering of Multiple Triggers on the Same Table

PostgreSQL orders firing of triggers of the same kind/event on a relation generally by **alphabetical order of trigger name** for triggers of the same type.

Example:

~~~text
a10_normalize_status  (BEFORE UPDATE)
b20_validate_status   (BEFORE UPDATE)
c30_audit_change      (AFTER UPDATE)
~~~

### 11.1. BEFORE order affects NEW

If `a10_normalize_status` alters `NEW.status`, `b20_validate_status` sees the updated status when it executes.

### 11.2. Naming should not be the only way to express workflow

Alphabetical naming can be used intentionally when needed, yet it is fragile when adding or renaming triggers. Tightly coupled steps should often be consolidated into a single trigger function or explicit command procedure where appropriate.

### 11.3. A later trigger's WHEN depends on state at evaluation time

A BEFORE trigger with `WHEN (NEW.status='active')` may or may not run depending on how earlier BEFORE triggers modified `NEW`.

### 11.4. AFTER sees the final outcome of BEFORE

AFTER row triggers see `OLD` and `NEW` reflecting the updated row state, so they can detect changes made by BEFORE triggers, provided the trigger was not inadvertently restricted with `UPDATE OF`.

## 12. UPDATE OF With Generated Columns

PostgreSQL supports **generated columns**, such as a stored generated column computed from base columns.

~~~sql
CREATE TABLE product_names (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT
      GENERATED ALWAYS AS (lower(display_name)) STORED
);
~~~

A column-specific trigger can list the generated column:

~~~sql
CREATE TRIGGER product_normalized_target
AFTER UPDATE OF normalized_name
ON product_names
FOR EACH ROW
EXECUTE FUNCTION log_product_name_change();
~~~

### 12.1. Generated column dependencies are tracked

Per PostgreSQL semantics, if a **generated column is listed in UPDATE OF** and an UPDATE targets a base column that the generated column depends on, the column-specific trigger is considered.

### 12.2. Do not generalize this arbitrarily to all derived columns

Modifying status via a BEFORE trigger or changing a computed column inside another function is not equivalent to a PostgreSQL-managed generated-column dependency. Distinguish catalog-defined generated columns from columns maintained by applications or triggers.

### 12.3. Generated values can still remain unchanged

For example, changing case:

~~~sql
UPDATE product_names
SET display_name = 'POSTGRESQL'
WHERE product_id = 1;
~~~

If `normalized_name` is `lower(display_name)`, the generated value may remain identical. `UPDATE OF` checks target/dependency, not whether the generated result actually changed.

### 12.4. When you need actual value changes

With an AFTER row trigger on an eligible generated column, you can use:

~~~sql
WHEN (
    OLD.normalized_name
    IS DISTINCT FROM NEW.normalized_name
)
~~~

Verify your PostgreSQL version and generated-column timing relative to triggers; never assume a BEFORE row trigger sees finalized new generated column values.

## 13. UPDATE OF Cannot Target Arbitrary JSON Path Expressions

Suppose a table has a `details JSONB` column:

~~~sql
UPDATE products
SET details = jsonb_set(
    details,
    '{status}',
    '"published"'
)
WHERE product_id = 10;
~~~

A column-specific trigger:

~~~sql
AFTER UPDATE OF details
~~~

is considered because the entire **`details` column** appears in SET, not because PostgreSQL knows the path `details.status` changed.

### 13.1. Do not write UPDATE OF details->>'status'

The `UPDATE OF` list accepts target column names, not JSON path extraction expressions.

### 13.2. Use WHEN to compare extracted field values

~~~sql
WHEN (
    (OLD.details ->> 'status')
    IS DISTINCT FROM
    (NEW.details ->> 'status')
)
~~~

### 13.3. If paths have complex types

With deeply nested JSON, understand the differences among missing keys, JSON `null`, SQL `NULL`, and text coercion. An `->>` expression maps several distinct cases to SQL NULL. If business logic must distinguish them, use dedicated JSONB comparisons.

### 13.4. When invariants need protection

A CHECK constraint or well-designed typed columns may fit far better than storing all business state in JSONB and relying on triggers to decode it.

## 14. Row-Level and Statement-Level Are Not Interchangeable

Row-level example:

~~~sql
CREATE TRIGGER log_each_change
AFTER UPDATE ON accounts
FOR EACH ROW
EXECUTE FUNCTION log_row_change();
~~~

Statement-level example:

~~~sql
CREATE TRIGGER log_update_command
AFTER UPDATE ON accounts
FOR EACH STATEMENT
EXECUTE FUNCTION log_statement_change();
~~~

### 14.1. UPDATE affecting 0 rows

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = -1;
~~~

When no rows are updated:

- Row-level triggers have no rows to run on.
- Statement-level triggers for that event **still run once**.

### 14.2. Statement-level triggers have no OLD/NEW row

A statement may affect many rows; there is no single representative OLD/NEW row. To process the entire set of rows, consider transition tables where appropriate.

### 14.3. WHEN is not a row filter for statement-level triggers

In standard PostgreSQL versions, `WHEN` is specified for row-level triggers, not as an arbitrary per-row filter on `FOR EACH STATEMENT`. To filter data in a statement-level trigger, put logic in the function and/or use transition relations where supported.

### 14.4. Statement-level UPDATE OF

If you need a statement-level trigger to fire only when an UPDATE targets specific columns, check syntax/semantics for your version. Even though the trigger runs once, `UPDATE OF` still checks the command's target list, **not whether any row's value actually changed**.

## 15. Transition Tables Differ From Single-Row OLD and NEW

PostgreSQL lets AFTER triggers reference **transition relations** containing the statement's old/new row sets under supported conditions.

General example:

~~~sql
CREATE TRIGGER accounts_change_batch
AFTER UPDATE ON accounts
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION process_account_changes();
~~~

### 15.1. Why are they useful?

An UPDATE affecting 10,000 accounts can be processed as a set inside one trigger function instead of executing 10,000 row-level calls.

### 15.2. Restrictions when combined with UPDATE OF

Under PostgreSQL rules, an UPDATE trigger using transition tables cannot simultaneously specify a column list with `UPDATE OF column_list` in restricted forms. You cannot freely combine every feature into one trigger definition.

### 15.3. Transition tables must be queried properly

A function using transition relations must be written to query the relations named in `REFERENCING`; it does not receive scalar `OLD`/`NEW` records like a row-level trigger.

### 15.4. When to choose statement-level + transition tables?

For large-scale auditing or bulk derived-data updates, set-based processing can be very efficient. Weigh memory usage, partition semantics, FK effects, and PostgreSQL version capabilities.

## 16. Constraint Triggers and WHEN Conditions

PostgreSQL provides **constraint triggers** for specialized constraint checks, created via `CREATE CONSTRAINT TRIGGER` under supported conditions.

~~~sql
CREATE CONSTRAINT TRIGGER check_business_rule
AFTER UPDATE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
WHEN (NEW.status = 'final')
EXECUTE FUNCTION validate_business_rule();
~~~

This is illustrative syntax: the table, function, and rule must exist.

### 16.1. Trigger action can be deferred

A constraint trigger can be configured so its action runs at an appropriate deferred time rather than immediately at the row operation.

### 16.2. WHEN itself is not deferred

Crucial point: for constraint triggers with WHEN, **the WHEN condition is evaluated immediately after the row update**, not postponed until the deferred action executes. Only events satisfying WHEN at that moment are queued.

### 16.3. Do not equate with CHECK/FK

Core constraints have dedicated optimizations and concurrency semantics. Whenever a rule can be expressed with CHECK, UNIQUE, FOREIGN KEY, or EXCLUDE, prefer declarative constraints before writing a constraint trigger.

### 16.4. Do not use deferred triggers for every validation

Rejecting bad data as early as possible simplifies APIs; deferred checks fit invariants that can only hold at transaction end after multiple steps, though they complicate debugging and commit-time errors.

## 17. INSTEAD OF Triggers and WHEN Restrictions

`INSTEAD OF` triggers are used on views to replace INSERT/UPDATE/DELETE behavior against the view.

~~~sql
CREATE TRIGGER customer_view_update
INSTEAD OF UPDATE ON customer_view
FOR EACH ROW
EXECUTE FUNCTION update_customer_underlying_tables();
~~~

### 17.1. Different from BEFORE/AFTER table triggers

An INSTEAD OF trigger executes instead of the DML operation on the view. Do not assume every WHEN or column-specific `UPDATE OF` rule of AFTER row triggers on physical tables applies identically to INSTEAD OF triggers.

### 17.2. Best practice

If you need to inspect field changes on a view, inspect `OLD`/`NEW` explicitly inside the trigger function per INSTEAD OF semantics, or check automatically updatable views and `WITH CHECK OPTION` first.

### 17.3. Avoid confusing with rules

PostgreSQL also has rewrite rules such as `CREATE RULE`, which operate at the query-rewrite stage. Triggers and rules have different lifecycles, visibility, and execution behavior; `WHEN` in triggers is not synonymous with `WHERE` or `CREATE RULE` conditions.

## 18. Trigger WHEN vs. CHECK Constraints

If the goal is simply preventing negative balances:

~~~sql
ALTER TABLE accounts
ADD CONSTRAINT accounts_balance_nonnegative
CHECK (balance >= 0);
~~~

Usually prefer CHECK instead of:

~~~sql
CREATE TRIGGER reject_negative_balance
BEFORE INSERT OR UPDATE ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION reject_negative_balance();
~~~

### 18.1. Advantages of CHECK

- Enforces the invariant declaratively.
- Easily discovered by schema inspection tools.
- Consistent semantics across all write paths.
- No separate runtime function required for simple rules.
- Easy to manage with constraints and migrations.

### 18.2. CHECK does not do everything

CHECK cannot directly enforce cross-row aggregate invariants or perform auditing. When logic exceeds CHECK's scope, use unique/FK/exclusion constraints, transaction protocols, or triggers as appropriate.

### 18.3. Use BEFORE triggers when transformation is needed

For example, cleaning or normalizing input values before storage when generated columns or app-side preprocessing do not suffice. Ensure ordering, NULL handling, and security are clear.

## 19. Trigger WHEN vs. WHERE Clauses in UPDATE

Compare:

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = 101;
~~~

and:

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = 101
  AND status IS DISTINCT FROM 'active';
~~~

They do not have the same cost when the value is already `active`.

### 19.1. WHERE prevents pointless UPDATEs

If the row is already `active`, the second query skips modifying the row, avoiding both update work and trigger firing.

### 19.2. WHEN only blocks the trigger function

With `WHEN (OLD.status IS DISTINCT FROM NEW.status)`, the first UPDATE still executes the row operation; only the trigger function is skipped when values match.

### 19.3. MVCC implications

An UPDATE whose logical values do not change can still create a new tuple version and WAL, increasing bloat and index maintenance depending on HOT eligibility and storage. Suppressing the audit function alone does not eliminate that cost.

### 19.4. Do not overuse WHERE when side effects are intended

Some applications intentionally run UPDATE even with identical values to record a "touch," update `modified_at`, or bump a version. Clarify the event contract rather than blindly skipping all unchanged UPDATEs.

## 20. PostgreSQL Lab: Environment Setup

The lab below uses its own schema and mock data. **Run only in a test database**. If schema `trigger_when_lab` already exists, choose another schema name to avoid overwriting anything. Never DROP someone else's data.

### 20.1. Create the schema

~~~sql
CREATE SCHEMA trigger_when_lab;
~~~

### 20.2. Create the accounts table

~~~sql
CREATE TABLE trigger_when_lab.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'closed')),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    contact_email TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 20.3. Create the audit table

~~~sql
CREATE TABLE trigger_when_lab.trigger_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    account_id BIGINT,
    old_status TEXT,
    new_status TEXT,
    old_balance NUMERIC(12,2),
    new_balance NUMERIC(12,2),
    detail TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

### 20.4. Insert sample data

~~~sql
INSERT INTO trigger_when_lab.accounts (
    owner_name, status, balance, contact_email
)
VALUES
    ('Nguyen An', 'active', 500.00, 'an@example.test'),
    ('Tran Binh', 'active', 250.00, NULL),
    ('Le Chi', 'suspended', 0.00, 'chi@example.test'),
    ('Pham Dung', 'active', 1000.00, 'dung@example.test');
~~~

### 20.5. Verify data to follow the examples

~~~sql
SELECT
    account_id, owner_name, status, balance, contact_email
FROM trigger_when_lab.accounts
ORDER BY account_id;
~~~

In a fresh lab, identity IDs normally start at 1. If data or sequences remain from earlier practice, use the actual returned IDs rather than assuming 1–4.

## 21. Lab: Trigger Function Writing Audits When Columns Are Targeted

Create a shared function for AFTER UPDATE triggers:

~~~sql
CREATE FUNCTION trigger_when_lab.log_account_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name,
        operation,
        account_id,
        old_status,
        new_status,
        old_balance,
        new_balance,
        detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NEW.account_id,
        OLD.status,
        NEW.status,
        OLD.balance,
        NEW.balance,
        'row-level AFTER trigger'
    );

    RETURN NEW;
END;
$$;
~~~

### 21.1. TG_NAME and TG_OP

- `TG_NAME`: name of the trigger currently invoking the function.
- `TG_OP`: event name such as INSERT/UPDATE/DELETE.
- `OLD`/`NEW`: row records in an eligible row trigger.

### 21.2. This function is meant for UPDATE

Because it reads both OLD and NEW, use it with **row-level UPDATE**. Attaching it to INSERT or DELETE without adjusting the function causes semantic errors due to the missing record. A multi-event trigger function must branch on `TG_OP`.

### 21.3. RETURN in an AFTER trigger

The RETURN value of a row-level AFTER trigger is not used to alter the saved row. `RETURN NEW` here is simply a common convention; blocking an UPDATE via `RETURN NULL` belongs to BEFORE row trigger semantics, not AFTER.

## 22. Lab: Creating Triggers to Contrast UPDATE OF and WHEN

### 22.1. First trigger: checks only whether the column appears in SET

~~~sql
CREATE TRIGGER a10_status_targeted
AFTER UPDATE OF status
ON trigger_when_lab.accounts
FOR EACH ROW
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.2. Second trigger: checks target column and genuine change

~~~sql
CREATE TRIGGER b20_status_changed_targeted
AFTER UPDATE OF status
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.3. Third trigger: detects any status change

~~~sql
CREATE TRIGGER c30_status_changed_any_update
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.4. Where do they differ?

- `a10`: fires if the statement targets status, even when status does not change.
- `b20`: fires if the statement targets status **and** status actually changed.
- `c30`: fires if status actually changed, **without requiring** status to appear in SET.

All three triggers share the same logging function, making differences easy to trace via `trigger_name`.

## 23. Lab: UPDATE SET status = status

~~~sql
UPDATE trigger_when_lab.accounts
SET status = status
WHERE account_id = 1;
~~~

Check the audit table:

~~~sql
SELECT
    event_id, trigger_name, operation,
    old_status, new_status
FROM trigger_when_lab.trigger_events
ORDER BY event_id;
~~~

### 23.1. Expected

If account_id=1 exists:

- `a10_status_targeted` logs an event because status was mentioned in SET.
- `b20_status_changed_targeted` logs nothing because OLD.status and NEW.status are equal.
- `c30_status_changed_any_update` logs nothing because the actual value did not change.

### 23.2. Takeaway

Using `UPDATE OF status` alone **does not mean** you are logging "status changes."

### 23.3. Avoid misreading audit counts

If you re-run steps multiple times, audit rows accumulate. Filter by timestamp or inspect newly added events after each run rather than assuming the table has only one row.

## 24. Lab: Actually Changing Status

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'suspended'
WHERE account_id = 1;
~~~

Check the audit table:

~~~sql
SELECT
    event_id,
    trigger_name,
    old_status,
    new_status
FROM trigger_when_lab.trigger_events
WHERE account_id = 1
ORDER BY event_id;
~~~

### 24.1. Expected outcome of this UPDATE

If account_id=1 was previously active and all triggers are enabled:

- `a10` logs an event.
- `b20` logs an event.
- `c30` logs an event.

### 24.2. Why three events?

These are three independent triggers sharing one audit function. One status change writes three rows **because we intentionally created three triggers**. In production, keep only the trigger matching your specific contract rather than three redundant logging triggers.

### 24.3. Transition condition example

If you only care about active -> suspended, use:

~~~sql
WHEN (
    OLD.status = 'active'
    AND NEW.status = 'suspended'
)
~~~

This is stricter than "any status change."

## 25. Lab: Updating a Column Other Than Status

~~~sql
UPDATE trigger_when_lab.accounts
SET balance = balance + 50
WHERE account_id = 2;
~~~

### 25.1. Expected

Provided no other trigger modifies status, none of the three triggers **writes an audit row**:

- The two `UPDATE OF status` triggers are not considered because SET only targets balance.
- Trigger c30 may be evaluated for the row, yet WHEN is FALSE because status did not change.

### 25.2. Purpose

This shows where `WHEN` helps avoid function overhead for rows whose monitored business field stayed unchanged.

### 25.3. Do not equate with INSERT

`UPDATE OF status` applies only to UPDATE events; INSERT does not trigger it. To log initial inserted statuses, attach a separate INSERT trigger per your requirements.

## 26. Lab: BEFORE Trigger Changing Status Even When UPDATE Omits Status

Create a function enforcing a rule: if balance <= 0 after a balance UPDATE, set status to suspended.

~~~sql
CREATE FUNCTION trigger_when_lab.suspend_when_empty()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.balance <= 0
       AND NEW.status = 'active' THEN
        NEW.status := 'suspended';
    END IF;

    RETURN NEW;
END;
$$;
~~~

Attach the function to BEFORE UPDATE OF balance:

~~~sql
CREATE TRIGGER a05_suspend_on_balance_update
BEFORE UPDATE OF balance
ON trigger_when_lab.accounts
FOR EACH ROW
EXECUTE FUNCTION trigger_when_lab.suspend_when_empty();
~~~

### 26.1. Statement updating balance only

~~~sql
UPDATE trigger_when_lab.accounts
SET balance = 0
WHERE account_id = 4;
~~~

Account 4 starts active with balance=1000 in a fresh lab. The BEFORE trigger changes `NEW.status` to suspended.

### 26.2. Which AFTER triggers log an audit?

- `a10_status_targeted`: **no**, because the original UPDATE only set balance.
- `b20_status_changed_targeted`: **no**, for the same reason.
- `c30_status_changed_any_update`: **yes**, because OLD.status was active and NEW.status became suspended.

### 26.3. Verify

~~~sql
SELECT account_id, status, balance
FROM trigger_when_lab.accounts
WHERE account_id = 4;

SELECT event_id, trigger_name, old_status, new_status
FROM trigger_when_lab.trigger_events
WHERE account_id = 4
ORDER BY event_id;
~~~

### 26.4. Design implication

To audit **every actual status change**, use AFTER UPDATE with a WHEN condition comparing OLD/NEW, rather than relying entirely on `UPDATE OF status` when BEFORE triggers can alter the column.

### 26.5. Business note

Automatically switching status when balance <= 0 is purely illustrative. Real financial systems need stricter state models, transactions, and constraints; do not deploy this rule verbatim to production.

## 27. Lab: WHEN With NULL for contact_email

Create a trigger that logs only when email genuinely changes:

~~~sql
CREATE FUNCTION trigger_when_lab.log_email_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id,
        detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NEW.account_id,
        'contact_email changed'
    );

    RETURN NEW;
END;
$$;
~~~

~~~sql
CREATE TRIGGER d40_email_changed
AFTER UPDATE OF contact_email
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.contact_email
    IS DISTINCT FROM
    NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_email_change();
~~~

### 27.1. NULL -> non-NULL email

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = 'binh-new@example.test'
WHERE account_id = 2;
~~~

Trigger fires if `contact_email` was previously NULL.

### 27.2. Email -> same email

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = contact_email
WHERE account_id = 2;
~~~

Trigger does not fire because values do not differ.

### 27.3. Email -> NULL

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = NULL
WHERE account_id = 2;
~~~

Trigger fires because `IS DISTINCT FROM` detects the change in a NULL-safe manner.

### 27.4. Why isn't <> equivalent?

`OLD.contact_email <> NEW.contact_email` returns UNKNOWN when either side is NULL, so WHEN is not TRUE. That is a very common auditing bug.

## 28. Lab: Catching Only Transitions Into Closed

Suppose business rules require alerting only when an account transitions to closed, not on subsequent updates to an already-closed account.

~~~sql
CREATE TRIGGER e50_account_closed
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'closed'
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 28.1. Transitioning status to closed

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'closed'
WHERE account_id = 2;
~~~

Trigger e50 fires if status was previously not closed.

### 28.2. Updating while already closed

~~~sql
UPDATE trigger_when_lab.accounts
SET updated_at = now()
WHERE account_id = 2;
~~~

Trigger e50 does not fire because both OLD.status and NEW.status are closed.

### 28.3. Isn't NEW.status='closed' alone simpler?

No. Checking `NEW.status` alone fires whenever an already-closed row updates another column, potentially emitting duplicate "account closed" events.

### 28.4. Idempotency

Even when filtering transitions accurately inside a database statement, external event publishing still needs an outbox and consumer idempotency to survive retries and failures. WHEN does not replace an exactly-once delivery protocol.

## 29. Lab: BEFORE WHEN to Normalize Input

Create a simple function normalizing `owner_name`:

~~~sql
CREATE FUNCTION trigger_when_lab.trim_owner_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.owner_name := btrim(NEW.owner_name);
    RETURN NEW;
END;
$$;
~~~

Attach to BEFORE UPDATE OF owner_name with WHEN:

~~~sql
CREATE TRIGGER b10_trim_owner_name
BEFORE UPDATE OF owner_name
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (NEW.owner_name IS DISTINCT FROM btrim(NEW.owner_name))
EXECUTE FUNCTION trigger_when_lab.trim_owner_name();
~~~

### 29.1. When owner_name is already clean

~~~sql
UPDATE trigger_when_lab.accounts
SET owner_name = 'Nguyen An'
WHERE account_id = 1;
~~~

With no extra whitespace, WHEN is FALSE and the function skips execution.

### 29.2. When whitespace is entered

~~~sql
UPDATE trigger_when_lab.accounts
SET owner_name = '  Nguyen An  '
WHERE account_id = 1;
~~~

WHEN is TRUE and the function trims whitespace before saving.

### 29.3. Generated column or application validation?

If simple normalization without side effects suffices, consider handling it in the application or designing a generated/normalized column. Triggers are helpful when all write paths (JDBC, SQL scripts, ETL, etc.) must apply the same transformation rule.

### 29.4. Avoid expensive functions inside WHEN

If WHEN evaluates heavy expressions or calls data-access functions, you still pay that check cost per candidate row. Filtering in WHEN pays off when the predicate is cheap and avoids larger downstream work.

## 30. Lab: FOR EACH STATEMENT Trigger With 0-Row UPDATE

Create a function logging statement-level events:

~~~sql
CREATE FUNCTION trigger_when_lab.log_statement_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id, detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NULL,
        'statement-level UPDATE executed'
    );
    RETURN NULL;
END;
$$;
~~~

Attach the trigger:

~~~sql
CREATE TRIGGER z90_update_statement
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_when_lab.log_statement_update();
~~~

### 30.1. UPDATE matching zero rows

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = -999;
~~~

### 30.2. Verify

~~~sql
SELECT
    event_id, trigger_name, operation, account_id, detail
FROM trigger_when_lab.trigger_events
WHERE trigger_name = 'z90_update_statement'
ORDER BY event_id DESC;
~~~

The statement-level trigger still logs an event despite 0 rows updated; row-level triggers have no rows to evaluate.

### 30.3. Scope of the log

This event only states "an UPDATE command ran," not "N rows changed" or "a specific column changed." To obtain row counts or deltas, use appropriate instrumentation or transition tables.

## 31. Lab: When You Need to Reduce Unchanged UPDATEs

Compare two ways to update status:

~~~sql
-- May execute a row UPDATE even though status is already active.
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = 3;
~~~

~~~sql
-- Do not target the row if status is already active.
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = 3
  AND status IS DISTINCT FROM 'active';
~~~

### 31.1. Difference in rows affected

When status is already active, the first statement reports 1 row updated; the second reports 0 rows updated.

### 31.2. Difference in triggers

The first statement still fires trigger `a10` because status is in SET. The second produces no row-level events when no row satisfies WHERE.

### 31.3. Statement-level triggers still run

With trigger `z90`, even the second UPDATE matching 0 rows can still write a statement event.

### 31.4. Consider application return semantics

Many Java services inspect row counts to tell whether a record exists. When adding `IS DISTINCT FROM` to WHERE, 0 rows can mean either "the row exists with that value already" **or** "the row does not exist." Design APIs or `RETURNING` accordingly when you need to distinguish the two.

## 32. Combining UPDATE OF and WHEN Across Multiple Columns

Example auditing when at least one of three business columns changes:

~~~sql
CREATE TRIGGER important_fields_changed
AFTER UPDATE OF status, balance, contact_email
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
    OR OLD.contact_email IS DISTINCT FROM NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 32.1. Two distinct OR layers

- `UPDATE OF status, balance, contact_email`: OR across **columns appearing in SET**.
- `WHEN (a_changed OR b_changed OR c_changed)`: OR across **values actually differing**.

### 32.2. What if a BEFORE trigger edits a column omitted from SET?

For example, SET `updated_at`, while a BEFORE trigger alters `balance`. The `UPDATE OF status, balance, contact_email` trigger may **still not fire** because those columns were absent from the target list.

### 32.3. When you must audit any real change

Omit `OF`:

~~~sql
CREATE TRIGGER important_fields_any_change
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
    OR OLD.contact_email IS DISTINCT FROM NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

The two `CREATE TRIGGER` blocks above are **illustrative alternatives**; do not keep both active simultaneously in production or you will duplicate audit rows.

## 33. Whole-Row OLD/NEW Comparison

PostgreSQL can compare entire row records:

~~~sql
WHEN (OLD IS DISTINCT FROM NEW)
~~~

This detects any change in the row's representation under row-comparison semantics.

### 33.1. Benefit

Simple when you genuinely want to audit every field (and business rules actually demand it).

### 33.2. Limitations

- Changing `updated_at` counts as a change, causing audit noise.
- Comparing wide rows or large fields adds extra cost.
- Schema changes adding columns automatically change what is compared.
- Requires understanding composite/NULL comparison semantics and type comparability.

### 33.3. Prefer listing business columns explicitly when appropriate

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
)
~~~

This is clearer when the audit contract only cares about two fields.

### 33.4. Does not replace data validation

A "different" row does not mean a valid change. Business invariants still require CHECK, UNIQUE, FK, and transaction logic.

## 34. Can WHEN Conditions Contain Subqueries?

Suppose you want to audit only if the customer in another table is active:

~~~sql
-- INVALID: direct subquery inside trigger WHEN
WHEN (
    EXISTS (
        SELECT 1 FROM customers
        WHERE customer_id = NEW.customer_id
          AND status = 'active'
    )
)
~~~

### 34.1. Restriction

PostgreSQL does not allow direct subqueries inside a trigger's WHEN expression.

### 34.2. Suitable alternatives

- Move the SQL check inside the trigger function with clear transaction/concurrency semantics.
- Redesign with FK/CHECK/constraints if the rule is truly an invariant.
- Maintain a consistently updated state column or derived representation where appropriate.
- Encapsulate complex multi-table workflows in a command transaction rather than triggers.

### 34.3. Functions in WHEN are not always free

A function invoked from WHEN might run internal SQL if permitted, yet you pay the function cost for every row evaluated and risk race or visibility issues. Never hide table-reading functions inside WHEN merely to sidestep the subquery restriction without analyzing correctness.

## 35. Combining Multiple Logical Operators in WHEN

### 35.1. AND

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

Executes only when **both** conditions are TRUE.

### 35.2. OR

~~~sql
WHEN (
    OLD.email IS DISTINCT FROM NEW.email
    OR OLD.phone IS DISTINCT FROM NEW.phone
)
~~~

Fires as long as at least one of the two fields differs.

### 35.3. NOT

~~~sql
WHEN (NOT (NEW.status = 'archived'))
~~~

If `NEW.status` is NULL, the expression evaluates to UNKNOWN rather than TRUE. When status can be NULL, use `IS DISTINCT FROM` or an explicit NULL check if different behavior is desired.

### 35.4. Compound conditions need parentheses

~~~sql
WHEN (
    (
        OLD.status IS DISTINCT FROM NEW.status
        AND NEW.status = 'paid'
    )
    OR (
        OLD.balance >= 0
        AND NEW.balance < 0
    )
)
~~~

Explicit grouping clarifies operator precedence and business intent.

### 35.5. Keep heavy logic out of DDL

WHEN should express a relatively clear predicate. If conditions span many layers, multiple tables, and intricate states, refactor the business workflow or move documented logic into a function.

## 36. Performance: Measuring Before and After Limiting Triggers

A per-row trigger affects latency approximately according to this mental model:

\[
T_{\mathrm{statement}}
\approx T_{\mathrm{base\ DML}}
+ N_{\mathrm{fired}}\cdot T_{\mathrm{function}}
+ T_{\mathrm{queue/constraints}}
\]

This is an **approximate model**. Actual impact also depends on cache, WAL, locks, I/O, trigger ordering, and executor behavior.

### 36.1. UPDATE OF narrows trigger scope

If 95% of UPDATEs modify only `last_seen_at`, an `AFTER UPDATE OF email` trigger is skipped for statements not targeting email, reducing overhead.

### 36.2. WHEN reduces rows that invoke the function

If an `UPDATE SET email=email` touches one million rows, `WHEN (OLD.email IS DISTINCT FROM NEW.email)` avoids invoking the audit function for rows whose value stayed identical.

### 36.3. WHEN still has evaluation cost

The WHEN expression still runs for candidate rows. If the predicate calls an expensive function or parses complex JSON, the benefit diminishes.

### 36.4. AFTER WHEN saves queue overhead

An AFTER trigger whose function merely runs an IF check inside may have to queue events and invoke the function far more often than putting the predicate in WHEN.

### 36.5. Does not eliminate UPDATE WAL

WHEN evaluating to FALSE does not make the UPDATE free. To avoid pointless DML, examine the UPDATE's WHERE clause and application behavior.

## 37. Triggers During Bulk Updates and Migrations

A bulk UPDATE can touch millions of rows:

~~~sql
UPDATE products
SET normalized_name = lower(display_name);
~~~

### 37.1. When row triggers exist

Every updated row can invoke trigger functions once or multiple times, depending on the number of triggers and their WHEN / UPDATE OF clauses.

### 37.2. WHEN helps, but does not solve everything

If many rows already have the right `normalized_name`, `WHEN` blocks the audit function; yet the UPDATE statement itself still rewrites rows needlessly.

### 37.3. Add WHERE to skip unchanged rows

~~~sql
UPDATE products
SET normalized_name = lower(display_name)
WHERE normalized_name
      IS DISTINCT FROM lower(display_name);
~~~

This applies only when `normalized_name` is a **regular updatable column**, not a stored generated column. You cannot assign directly to a generated column this way.

### 37.4. Statement-level triggers may fit better

When updating batch aggregates or logs, transition relations and set-based SQL where supported are usually worth considering over row-by-row triggers issuing repeated SQL.

### 37.5. Watch locks and transaction length

Bulk UPDATEs still hold transactions, locks, and WAL. Triggers are no substitute for proper batch sizing, VACUUM, indexes, and migration safety.

## 38. Trigger Functions and Out-of-Database Side Effects

An audit trigger can INSERT into an audit table in the same transaction:

~~~sql
INSERT INTO audit_events (...);
~~~

When the main transaction rolls back, the audit row rolls back with it.

### 38.1. External HTTP/email is different

If a trigger function calls an extension that sends an outbound HTTP request, a PostgreSQL transaction rollback cannot recall the sent request.

### 38.2. WHEN does not make external effects exactly-once

If a transaction retries, the trigger can execute again. Under network failures, external receivers may see duplicate messages or observe messages before database commit.

### 38.3. Transactional outbox

A safer event-publishing pattern:

~~~text
UPDATE business row
    |
AFTER row trigger WHEN meaningful change
    |
INSERT event_outbox in same transaction
    |
COMMIT
    |
Out-of-database worker dispatches message
    |
Idempotent consumer
~~~

### 38.4. Do not solve duplicate semantics with WHEN alone

If a state toggles back and forth or an UPDATE retries in a new transaction, you still need event IDs, idempotency keys, schema versions, and proper consumer policies.

## 39. Trigger Recursion and Update Loops

A trigger function on `accounts` executing:

~~~sql
UPDATE trigger_when_lab.accounts
SET updated_at = clock_timestamp()
WHERE account_id = NEW.account_id;
~~~

can fire another UPDATE trigger (or itself) and cause recursion.

### 39.1. WHEN does not automatically stop all recursion

If every UPDATE keeps satisfying WHEN or another trigger keeps altering fields, loops still happen.

### 39.2. Better pattern for updated_at

A BEFORE UPDATE row trigger can set:

~~~sql
NEW.updated_at := clock_timestamp();
RETURN NEW;
~~~

modifying **the row currently being updated** without issuing a new UPDATE on the same table.

### 39.3. pg_trigger_depth()

PostgreSQL provides `pg_trigger_depth()` to observe trigger nesting depth. However, using `WHEN (pg_trigger_depth() = 0)` as a blanket guard can skip legitimate nested operations. Never rely on depth checks instead of designing non-recursive workflows.

### 39.4. Limiting via column list

A `BEFORE UPDATE OF status` trigger modifying `NEW.updated_at` does not separately fire an `UPDATE OF updated_at` trigger, because editing `NEW` is not a new `UPDATE SET` statement. Running a separate `UPDATE` statement inside the function is a different matter.

## 40. Trigger WHEN and Partitions

With declarative partitioning, row-level triggers and trigger definitions follow rules propagating to partitions depending on PostgreSQL version and hierarchy structure.

### 40.1. Inspect trigger objects on parent and leaves

When a trigger is defined on a partitioned parent, modern PostgreSQL creates/maintains corresponding triggers on partitions per specific rules. Do not assume every parent trigger runs only once for the entire logical table.

### 40.2. Row movement

Updating a partition key can move a row from one partition to another, involving physical DELETE/INSERT behavior and special trigger firing semantics. Never assume `AFTER UPDATE OF key` automatically reflects every leaf-level event identically to an unpartitioned table.

### 40.3. Transition relations and partitions

When using transition tables with partitioned tables, verify support, row scope, and firing timing for your PostgreSQL version. Restrictions on BEFORE/AFTER and column lists can still affect your design.

### 40.4. Test data across multiple partitions

For critical business events (payments, legal state transitions), test both in-partition UPDATEs and partition-key-changing UPDATEs rather than testing only on a single plain table.

## 41. ON CONFLICT DO UPDATE and MERGE

Modern SQL includes write paths beyond a standalone UPDATE.

### 41.1. INSERT ... ON CONFLICT DO UPDATE

~~~sql
INSERT INTO accounts(account_id, status)
VALUES (101, 'active')
ON CONFLICT (account_id)
DO UPDATE SET status = EXCLUDED.status;
~~~

Depending on the executed branch and PostgreSQL semantics, BEFORE/AFTER INSERT/UPDATE triggers are evaluated under specific rules. With `DO UPDATE SET status=...`, column-specific UPDATE triggers watching `status` follow the UPDATE branch's target list.

### 41.2. ON CONFLICT DO NOTHING

The branch that neither inserts nor updates a row produces no row-level AFTER INSERT/UPDATE event for that row; statement-level trigger behavior must be understood separately.

### 41.3. MERGE

PostgreSQL supports MERGE in modern versions; its INSERT/UPDATE/DELETE actions follow specific trigger semantics. Never assume a MERGE statement behaves like a simple `UPDATE OF` merely because it contains an UPDATE branch.

### 41.4. Verify against your version

When applications use UPSERT/MERGE, test actual trigger firing across INSERT, UPDATE, DO NOTHING, and conflict/WHERE cases—especially when audits or outboxes must neither duplicate nor drop events.

## 42. Triggers on Views vs. Rewrite Rules

The **Triggers and Rules** chapter also contrasts two mechanisms:

| Feature | Trigger | Rule |
|---|---|---|
| Goal | Execute a trigger function on an event | Rewrite queries via the rule system |
| Timing | BEFORE/AFTER/INSTEAD OF per type | Transforms statement at rewrite stage |
| Row values | OLD/NEW inside row triggers | OLD/NEW have separate rule semantics |
| WHEN | Boolean predicate per trigger rules | Rule conditions have different semantics |
| Auditing row changes | Row-level AFTER trigger usually fits | Should not be assumed equivalent |
| Optimization | Row/statement execution overhead | Query rewrite alters SQL |
| Understandability | Trigger function has clear control flow | Rules can produce surprising behavior if overused |

### 42.1. WHERE and WHEN differ

`WHERE` in UPDATE selects which rows are updated. Trigger `WHEN` decides whether to invoke the function for an event/row. `CREATE RULE` conditions operate at rewrite time, not as a drop-in replacement for a row-level AFTER trigger WHEN.

### 42.2. When building new audits

An AFTER ROW trigger checking value changes is far clearer than a rule writing to an audit table, because triggers execute on actual row events with proper NEW/OLD context.

### 42.3. Reading legacy rules

If an older database uses `CREATE RULE` or view rewrite rules, understand rewrite semantics thoroughly before "migrating" them to triggers; never rewrite blindly just because both mention WHEN or WHERE.

## 43. Performance and DML Ordering With Multiple Triggers

A table may have:

- BEFORE normalization.
- BEFORE validation.
- AFTER audit.
- AFTER outbox.
- AFTER statement metrics.

### 43.1. A single UPDATE can trigger many function calls

If 10,000 rows are updated and three unfiltered AFTER row triggers exist, tens of thousands of function executions occur. Triggers with WHEN clauses can cut down calls dramatically based on real data.

### 43.2. Writing audits is also DML

Inserting into an audit table incurs its own WAL, indexes, and locks. Unnecessary GIN or B-tree indexes on the audit table raise write latency. When designing, account for I/O costs as well as trigger function CPU.

### 43.3. Keep only relevant events

Use WHEN right on the AFTER trigger to discard non-meaningful rows. If an event only needs one summary row per statement, consider transition tables and set-based processing.

### 43.4. Condition cost

`OLD.status IS DISTINCT FROM NEW.status` is generally much cheaper than calling a heavy function that queries another table to "check if anything changed," though both should be evaluated against your workload.

### 43.5. Errors inside triggers

If a trigger function raises an unhandled exception, the DML statement fails and impacts the transaction. A WHEN condition does not turn a trigger into an asynchronous background task.

## 44. Diagnosing a Trigger That Did Not Fire

If you expected a trigger to fire and see no audit row:

1. Verify which DML actually ran: INSERT, UPDATE, or DELETE.
2. Check trigger timing and `FOR EACH ROW/STATEMENT`.
3. Check whether any rows actually matched the UPDATE's WHERE clause.
4. Check which columns were in SET and `UPDATE OF`.
5. Check whether earlier BEFORE triggers modified `NEW`.
6. Check whether WHEN evaluated to TRUE, FALSE, or NULL.
7. Check whether `<>` was used with NULL instead of `IS DISTINCT FROM`.
8. Check trigger enabled/disabled state in metadata and `session_replication_role`.
9. Check whether the function raised an exception or the transaction rolled back.
10. Check whether the transaction committed.
11. Check privileges, `search_path`, and schema qualification.
12. Check whether data was modified via partitions, views, UPSERT, or MERGE.
13. Verify the trigger function is attached to the right table with the right name.
14. Check generated-column dependencies in SET.
15. Verify your inspection query filters audit rows accurately.

### 44.1. Do not jump to conclusions from an empty audit table

An empty audit result can stem from WHEN being FALSE, zero matched rows, a transaction rollback, a disabled trigger, or writes going to a different table. Identify which layer prevented the event.

### 44.2. Do not immediately delete WHEN as a quick fix

Removing WHEN can flood the table with unwanted events and spike overhead. Clarify first whether the requirement is "column touched" or "value changed."

## 45. Inspecting Trigger Definitions in Catalogs

### 45.1. pg_trigger

~~~sql
SELECT
    t.tgname AS trigger_name,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid =
    'trigger_when_lab.accounts'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

### 45.2. Meaning of tgenabled

Metadata indicates the trigger's enable/replication state using PostgreSQL codes. Never assume a trigger fires just because it exists without checking whether it fires under the active session replication role.

### 45.3. pg_get_triggerdef

Reconstructs the trigger's SQL definition, including timing, `UPDATE OF`, `WHEN`, and function. This is far more reliable than guessing from trigger names.

### 45.4. pg_get_functiondef

~~~sql
SELECT pg_get_functiondef(
    'trigger_when_lab.log_account_event()'::regprocedure
);
~~~

Reads the exact definition of the function executed by the trigger.

### 45.5. information_schema.triggers

~~~sql
SELECT
    event_object_schema,
    event_object_table,
    trigger_name,
    event_manipulation,
    action_timing,
    action_orientation
FROM information_schema.triggers
WHERE event_object_schema = 'trigger_when_lab'
ORDER BY event_object_table, trigger_name;
~~~

This standardized metadata view can be subject to privilege restrictions and omits PostgreSQL-specific details shown by `pg_get_triggerdef`.

## 46. Inspecting Trigger Executions With EXPLAIN

PostgreSQL can report trigger execution time and call counts in `EXPLAIN (ANALYZE)` for data-modifying statements, depending on trigger type and plan.

Example:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_when_lab.accounts
SET status = status
WHERE account_id = 1;

ROLLBACK;
~~~

### 46.1. Why BEGIN/ROLLBACK?

`EXPLAIN ANALYZE` **actually runs the UPDATE**, including triggers and any DML inside them. Use a rolled-back transaction in the lab so writes are not kept, noting that sequence side effects do not roll back like row data.

### 46.2. What to observe

- Total execution time.
- Row counts in the plan.
- Buffers.
- Trigger call counts and timings when displayed.
- Whether the audit function actually wrote data.
- Differences between WHEN TRUE and WHEN FALSE.

### 46.3. Row-level triggers vs. index scans

An UPDATE finding rows via an Index Scan does not mean the trigger function is optimized into the index. Trigger execution and row retrieval are separate work phases.

### 46.4. A single measurement is inconclusive

On a 4-row table, trigger overhead differences are tiny and easily masked by caching or timer jitter. Reliable benchmarking requires representative data, multiple runs, and proper monitoring, though running benchmarks is separate from writing documentation.

## 47. pg_stat_user_functions and Trigger Function Stats

When `track_functions` is enabled appropriately, you can inspect call counts and timings:

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'trigger_when_lab'
ORDER BY total_time DESC;
~~~

### 47.1. Data is not populated by default

If `track_functions` is `none` or the function kind is not tracked, the view will not show expected call counts.

### 47.2. EXPLAIN and stats serve different goals

EXPLAIN shows trigger impact for one specific execution. `pg_stat_user_functions` aggregates calls and times across the cluster since the last stats reset.

### 47.3. Do not confuse call counts with changed business rows

One UPDATE can run multiple triggers on the same row; trigger call counts do not equal distinct business events, and with WHEN they can be lower than updated row counts.

## 48. Security and Privileges in Trigger Functions

Trigger functions execute under a defined security model, defaulting to `SECURITY INVOKER` unless specified otherwise. `SECURITY DEFINER` runs with owner privileges and requires careful hardening.

### 48.1. When auditing requires elevated write privileges

A caller may have UPDATE permission on business tables without direct INSERT permission on the audit table. A securely written `SECURITY DEFINER` trigger function can write audit rows using appropriate owner privileges.

### 48.2. Safe search_path

With `SECURITY DEFINER`, restrict to trusted schemas and schema-qualify objects to prevent name-resolution hijacking:

~~~sql
CREATE FUNCTION trigger_when_lab.secure_audit_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trigger_when_lab, pg_temp
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id, detail
    )
    VALUES (TG_NAME, TG_OP, NEW.account_id, 'secure audit');
    RETURN NEW;
END;
$$;
~~~

This example is for UPDATE/INSERT rows; do not use it directly on DELETE without branching on NEW/OLD.

### 48.3. RLS and owner privileges

Owner privileges, RLS policies, and `BYPASSRLS` roles can produce behavior different from the application role. Always test using the actual runtime role.

### 48.4. WHEN does not replace authorization

A condition `WHEN (NEW.tenant_id = 42)` only filters trigger events; it does not stop callers from reading or updating other tenants if SQL grants permit. Enforce access control with grants, RLS, constraints, and API authorization.

### 48.5. Do not let users disable audits

If security or compliance requires unbypassable auditing, govern `DISABLE TRIGGER` rights, owner/superuser privileges, replication settings, and bulk-ingest paths. A trigger is never an unbreakable barrier against a database administrator.

## 49. Understanding the Limitations of WHEN

| Limitation | Design consequence |
|---|---|
| Boolean condition in trigger context | Does not replace arbitrary SQL conditions |
| No direct subqueries | Cross-table checks require another design |
| NULL/UNKNOWN semantics | Use `IS DISTINCT FROM` when comparing before/after |
| OLD/NEW depend on event | Never use OLD in INSERT or NEW in DELETE |
| Timing differences | BEFORE/AFTER observe values at different phases |
| AFTER WHEN does not block row updates | To prevent DML, use WHERE, BEFORE, or constraints |
| Runs per row when row-level | Expensive predicates repeat for every row |
| Does not guarantee exactly-once external effects | Requires outbox and idempotency |
| Does not replace authorization | Must use RLS, grants, and role policies |
| Not a batch transition table | Multi-row summaries need dedicated design |

### 49.1. Limitations act as guardrails

PostgreSQL restricts arbitrary trigger conditions to keep execution semantics predictable. When requirements call for overly complex cross-table validation, the first question should be **does this even belong in a trigger?**

## 50. Understanding the Limitations of UPDATE OF

| Scenario | `UPDATE OF status` |
|---|---|
| `SET status='paid'` | May fire |
| `SET status=status` | May fire |
| `SET amount=100` | Does not fire for status |
| BEFORE trigger modifies `NEW.status`, SET only lists amount | Does not fire merely because status was altered |
| `UPDATE OF status, amount`, SET only lists amount | May fire |
| Generated column depending on a column in SET | Follows special dependency rules |
| UPDATE affecting zero rows | No row-level firing |
| INSERT/DELETE | Outside `UPDATE OF` scope |
| JSONB path inside a column | Only knows the JSONB column is in SET, not which nested field changed |
| WHEN checking OLD/NEW | Additional value filter; does not change target-list semantics |

### 50.1. Do not rely on UPDATE OF to protect every integrity invariant

If an application updates one column and a trigger indirectly changes `status` or `balance`, a column-specific trigger can miss it. For critical integrity invariants, use CHECK/FK/UNIQUE or BEFORE/AFTER checks not restricted by target lists where needed.

## 51. Checklist When Designing a New Trigger

### 51.1. Define the business event

- Do you care whether a column was **SET** or whether its value actually **changed**?
- Are you catching a specific transition or any post-UPDATE state?
- Per row or per statement?
- Writing audit/outbox entries or only validating?
- Need transactional synchronization of side effects?
- Are generated columns or BEFORE triggers modifying values?

### 51.2. Choose timing

- Does BEFORE need to modify `NEW`?
- Does AFTER need to see the persisted row?
- Will AFTER WHEN avoid unnecessary queuing/calls?
- Does INSTEAD OF on a view introduce distinct semantics?
- Is a deferred constraint trigger involved?

### 51.3. Define the predicate

- Are `OLD`/`NEW` valid for the target event?
- Can values be NULL? Should you use `IS DISTINCT FROM`?
- Are AND/OR groupings parenthesized properly?
- Are there invalid subqueries in WHEN?
- Are there expensive functions in WHEN?
- Should you omit `UPDATE OF` because another BEFORE trigger might edit the watched column?

### 51.4. Evaluate performance

- How many rows does a single UPDATE touch?
- How many row triggers exist on the table?
- Does the function run per-row SQL or external calls?
- Could set-based SQL or transition tables handle it?
- Could WHERE skip no-op UPDATEs?
- Will audit/outbox storage and WAL grow rapidly?

### 51.5. Evaluate security and operations

- Does the function run as invoker or definer?
- Are write privileges on audit tables controlled?
- Are RLS and tenant isolation preserved?
- Is `search_path` trusted and are references schema-qualified?
- Can roles arbitrarily DISABLE the trigger?
- Do migrations, partitioning, UPSERT, or MERGE affect firing behavior?
- Are monitoring, rollback, and recovery plans in place?

## 52. Common Misconceptions

### 52.1. "UPDATE OF status only fires when status differs from before"

**False.** It checks the target list, not before/after values.

### 52.2. "SET status=status will not fire UPDATE OF status"

**False.** The column still appears in SET.

### 52.3. "A BEFORE trigger changing status automatically fires every UPDATE OF status"

**False** when the original UPDATE did not target status; exceptions/rules apply specifically to generated-column dependencies.

### 52.4. "WHEN OLD.x <> NEW.x always catches every change"

**False.** With NULLs, the expression can evaluate to UNKNOWN.

### 52.5. "IS DISTINCT FROM differs from <> only in syntax"

**False.** It provides NULL-safe comparison.

### 52.6. "WHEN FALSE prevents the UPDATE from happening"

**False** for AFTER triggers; it only skips calling the trigger function.

### 52.7. "AFTER WHEN and an IF inside the AFTER function always have identical overhead"

**False.** WHEN avoids queuing the event and invoking the function.

### 52.8. "WHEN can use EXISTS (SELECT ...) directly"

**False.** Trigger WHEN forbids direct subqueries.

### 52.9. "UPDATE OF a,b requires both a and b to change"

**False.** Targeting either column suffices.

### 52.10. "UPDATE OF JSONB path targets a specific nested field"

**False.** The list takes column names, not JSON expressions.

### 52.11. "AFTER UPDATE WHEN NEW.status='paid' only catches transitions to paid"

**False.** Subsequent UPDATEs on an already-paid row still match.

### 52.12. "Statement triggers do not run when UPDATE affects 0 rows"

**False.** Statement-level triggers still run even when row count is 0.

### 52.13. "Statement-level triggers have a NEW representing all rows"

**False.** Use transition tables or another design for row sets.

### 52.14. "Deferred constraint triggers also defer WHEN evaluation"

**False.** WHEN is evaluated immediately after the row operation per supported semantics.

### 52.15. "Generated column dependencies work just like BEFORE triggers editing columns"

**False.** PostgreSQL applies specific dependency rules for generated columns listed in `UPDATE OF`.

### 52.16. "If WHEN checks value changes, UPDATE produces no WAL"

**False.** The main UPDATE can still write new tuples.

### 52.17. "Trigger audits automatically guarantee exactly-once external events"

**False.** Retries, outboxes, and idempotency are still needed.

### 52.18. "Triggers protect every tenant if WHEN checks tenant_id"

**False.** WHEN does not replace RLS or grants.

### 52.19. "RETURN NULL inside an AFTER trigger cancels the UPDATE"

**False.** Returning NULL to skip a row belongs to BEFORE row triggers; AFTER cannot undo an UPDATE via its return value.

### 52.20. "Reading the trigger name tells you everything about how it runs"

**False.** Inspect `pg_get_triggerdef`, the function definition, enabled state, and context.

### 52.21. "UPDATEs via views, partitions, and MERGE always behave like plain table UPDATEs"

**False.** Each write path has its own firing rules.

### 52.22. "Triggers with different names are independent"

**Not generally true.** BEFORE triggers can modify `NEW` and affect the WHEN conditions of subsequent triggers.

### 52.23. "CHECK constraints should be replaced with triggers for flexibility"

**Not by default.** Simple invariants usually belong in CHECK/UNIQUE/FK.

### 52.24. "A trigger function has zero cost if it only inserts an audit row"

**False.** Audit INSERTs still write WAL and indexes, hold locks, and consume storage.

### 52.25. "EXPLAIN ANALYZE UPDATE only prints the plan without modifying data"

**False.** It executes the UPDATE and triggers; wrap in a test transaction.

## 53. Practice Exercises

### Exercise 1 — Definitions

Explain the difference between `UPDATE OF status` and `WHEN (OLD.status IS DISTINCT FROM NEW.status)`.

**Hint:** Target list vs. actual value change.

### Exercise 2 — Setting the same value

A row currently has `status='active'`. You run `UPDATE ... SET status=status`. Can an `AFTER UPDATE OF status` trigger fire?

**Answer:** Yes.

### Exercise 3 — Unchanged value

If you add a WHEN checking `IS DISTINCT FROM`, does the trigger fire on `SET status=status`?

**Answer:** No, since OLD and NEW status are equal.

### Exercise 4 — Multi-column list

Does `UPDATE OF status, amount` require both status and amount to appear in SET?

**Answer:** No; mentioning either one is enough.

### Exercise 5 — BEFORE modifies status

An UPDATE only sets `balance`; a BEFORE trigger alters `NEW.status`. Does an `UPDATE OF status` trigger fire automatically?

**Answer:** No, under normal target-list rules.

### Exercise 6 — Catching all status changes

Write an AFTER trigger definition suitable when status can be changed by a BEFORE trigger.

**Hint:** `AFTER UPDATE` without `OF`, with `WHEN (OLD.status IS DISTINCT FROM NEW.status)`.

### Exercise 7 — NULL changed to text

`OLD.email=NULL` and `NEW.email='a'`. Does `OLD.email <> NEW.email` evaluate to TRUE?

**Answer:** No; UNKNOWN.

### Exercise 8 — IS DISTINCT FROM

`OLD.email=NULL`, `NEW.email='a'`. What is the result of `IS DISTINCT FROM`?

**Answer:** TRUE.

### Exercise 9 — NULL to NULL

`OLD.email=NULL`, `NEW.email=NULL`. What is `IS DISTINCT FROM`?

**Answer:** FALSE.

### Exercise 10 — Transitioning to paid

Write a WHEN clause that runs only when status actually changed and `NEW.status='paid'`.

**Hint:** `AND` between `IS DISTINCT FROM` and `NEW.status='paid'`.

### Exercise 11 — Only NEW.status='paid'

Why can this WHEN condition generate duplicate events?

**Hint:** Already-paid rows still match when other columns are updated.

### Exercise 12 — BEFORE return

What can a row-level BEFORE trigger return `NULL` for?

**Hint:** Skipping the row operation under BEFORE row trigger semantics.

### Exercise 13 — AFTER return

Does returning `NULL` from an AFTER trigger cancel the UPDATE?

**Answer:** No.

### Exercise 14 — WHEN FALSE

Does an AFTER trigger with WHEN evaluating to FALSE prevent the main UPDATE?

**Answer:** No.

### Exercise 15 — WHEN with subquery

Can you write `WHEN (EXISTS(SELECT ...))` directly?

**Answer:** No.

### Exercise 16 — Generated column

If generated `normalized_name` depends on `display_name`, can `UPDATE OF normalized_name` be considered when setting `display_name`?

**Hint:** Yes, under generated-column dependency rules.

### Exercise 17 — Generated value unchanged

If `display_name` changes casing while `lower(display_name)` stays identical, does `UPDATE OF normalized_name` guarantee `normalized_name` changed?

**Answer:** No.

### Exercise 18 — JSONB

To detect changes to path `details.status`, what should you compare?

**Hint:** `OLD.details->>'status'` and `NEW.details->>'status'` using `IS DISTINCT FROM`.

### Exercise 19 — Statement-level

Can a 0-row UPDATE run an `AFTER UPDATE FOR EACH STATEMENT` trigger?

**Answer:** Yes.

### Exercise 20 — Row-level

Does a 0-row UPDATE invoke any row-level triggers?

**Answer:** No, there are no rows to invoke on.

### Exercise 21 — Transition table

Why are transition tables advantageous when auditing 10,000 rows?

**Hint:** Enables set-based processing inside a statement-level trigger.

### Exercise 22 — UPDATE OF and transition tables

Can you freely combine an `UPDATE OF` column list with any transition relation configuration?

**Answer:** No; definition restrictions apply.

### Exercise 23 — Deferred WHEN

Does a deferred constraint trigger also defer WHEN evaluation?

**Answer:** No; WHEN is evaluated immediately per trigger semantics.

### Exercise 24 — Timing

When is AFTER row WHEN evaluated?

**Hint:** After the row operation, before deciding whether to queue the event.

### Exercise 25 — BEFORE trigger order

If BEFORE trigger `a` modifies `NEW.status` before BEFORE trigger `b`, which value does `b` see?

**Hint:** The `NEW` value already modified by `a`.

### Exercise 26 — CHECK vs. trigger

If you only need `amount >= 0`, which solution should you consider first?

**Hint:** A `CHECK` constraint.

### Exercise 27 — Avoid no-op UPDATEs

Write a WHERE clause avoiding `SET status='active'` when status is already active.

**Hint:** `status IS DISTINCT FROM 'active'`.

### Exercise 28 — Application row count

After adding that WHERE clause, what two meanings can 0 rows affected have?

**Hint:** Either the row does not exist or it already had that value.

### Exercise 29 — Recursion

Why can an UPDATE trigger on `accounts` that updates `accounts` cause recursion?

**Hint:** The new UPDATE re-fires the trigger.

### Exercise 30 — updated_at

Inside a BEFORE UPDATE trigger, how do you set `NEW.updated_at` without running a separate UPDATE?

**Hint:** Assign directly to `NEW` and `RETURN NEW`.

### Exercise 31 — Audit rollback

If a transaction rolls back, does an audit INSERT from the same transaction survive?

**Answer:** No.

### Exercise 32 — Sequence gap

Can an identity `event_id` jump after a rollback?

**Answer:** Yes.

### Exercise 33 — External webhook

Does an outbound webhook called inside a trigger roll back automatically with PostgreSQL?

**Answer:** No.

### Exercise 34 — Outbox

Why is an outbox better than calling a webhook directly from an AFTER trigger?

**Hint:** Atomic intent inside the DB and external delivery via a retrying worker.

### Exercise 35 — Enable state

Which catalog column shows a trigger's enabled state?

**Hint:** `pg_trigger.tgenabled`.

### Exercise 36 — Definition

Which function reconstructs `CREATE TRIGGER` DDL?

**Answer:** `pg_get_triggerdef`.

### Exercise 37 — Function definition

Which function prints a trigger function's definition?

**Answer:** `pg_get_functiondef`.

### Exercise 38 — EXPLAIN ANALYZE

Why must you be careful with `EXPLAIN ANALYZE UPDATE`?

**Hint:** It executes the real DML.

### Exercise 39 — Statement vs. row count

How many trigger function calls can a 100-row UPDATE statement with three row-level triggers generate at most when all fire?

**Hint:** More than 100, e.g., 300, depending on WHEN and enabled states.

### Exercise 40 — Security

Does `WHEN (NEW.tenant_id = 42)` stop callers from modifying tenant 43?

**Answer:** No.

### Exercise 41 — SECURITY DEFINER

What must you watch for in `search_path` on a `SECURITY DEFINER` trigger function?

**Hint:** Trusted schemas, schema qualification, and proper handling of `pg_temp`.

### Exercise 42 — State transition

Write a WHEN clause logging only when balance goes from >=0 to <0.

**Hint:** `OLD.balance >= 0 AND NEW.balance < 0`, with appropriate NULL semantics.

### Exercise 43 — Multi-field OR

Write a WHEN clause auditing whenever status or contact_email genuinely changes.

**Hint:** `OR` between two `IS DISTINCT FROM` comparisons.

### Exercise 44 — Whole-row comparison

When can comparing `OLD IS DISTINCT FROM NEW` create audit noise?

**Hint:** When `updated_at` or technical metadata fields change.

### Exercise 45 — Architecture

A system must audit every email change, even if modified by a BEFORE trigger and nullable. How would you define the trigger?

**Hint:** `AFTER UPDATE` (no `OF`) `FOR EACH ROW WHEN (OLD.email IS DISTINCT FROM NEW.email)` writing to audit/outbox.

### Exercise 46 — Performance exercise

An UPDATE sets `last_seen_at` on one million rows; the table has an AFTER UPDATE audit trigger, yet business only cares about status. Propose sensible restrictions.

**Hint:** `UPDATE OF status` if the contract is target column; or `AFTER UPDATE WHEN` status changed if status can change indirectly, plus WHERE to skip no-op UPDATEs.

### Exercise 47 — Diagnostic lab

Given triggers `a10`/`b20`/`c30`, predict event logs for three cases: `SET status=status`, `SET status='suspended'`, and `SET balance=0` when a BEFORE trigger transitions status.

**Suggested answer:** A: `a10` only; B: `a10`+`b20`+`c30` when actually changed; C: `c30` only for indirect status change.

### Exercise 48 — MERGE/UPSERT

Why shouldn't you assume MERGE or `INSERT ON CONFLICT DO UPDATE` always fires triggers identically to a standalone UPDATE?

**Hint:** Multiple action branches and version-specific PostgreSQL semantics.

### Exercise 49 — Constraint trigger

If validation requires deferred execution, what must you remember about WHEN?

**Hint:** WHEN is evaluated immediately; only the action is deferred.

### Exercise 50 — Complete design

An ordering application needs: emit OrderPaid only when status transitions from new to paid; update `modified_at`; avoid duplicate events on `UPDATE status=status`; publish to a broker; support bulk updates. Choose trigger timing, WHEN, update predicate, outbox, and batch strategy.

**Hint:** Emit only on real transitions (`AFTER ROW WHEN OLD.status IS DISTINCT FROM NEW.status AND NEW.status='paid'`), modify `NEW.updated_at` in BEFORE if needed; use WHERE to avoid no-ops; write to a transactional outbox with an idempotent worker; consider transition tables/set-based SQL for very large bulk loads.

## 54. Decision Flow: Choosing UPDATE OF, WHEN, or WHERE

~~~text
Need to skip the row UPDATE entirely if the value did not change?
    |
    +-- Yes -> Put IS DISTINCT FROM condition in WHERE
    |          or design appropriate BEFORE logic/constraints
    |
    +-- No / still want UPDATE -> Continue
                                   |
                Need trigger because column appears in SET?
                     |
                     +-- Yes -> UPDATE OF column_list
                     |
                     +-- No, need actual value change
                             |
                             v
                        AFTER UPDATE
                        WHEN OLD.col IS DISTINCT FROM NEW.col
                             |
                Need to restrict both target list and value?
                     |
                     +-- Yes -> UPDATE OF ... + WHEN ...
                     |
               Could a BEFORE trigger modify other fields?
                     |
                     +-- Yes -> Beware UPDATE OF can miss them
~~~

### 54.1. When you define "touched"

Use `UPDATE OF`, even if the caller assigns the old value.

### 54.2. When you define "changed"

Use OLD/NEW comparisons with explicit NULL handling.

### 54.3. When you want to prevent redundant DML

Put conditions in the SQL UPDATE's WHERE clause, because AFTER WHEN does not cancel the write.

### 54.4. When you need batch scale

Evaluate statement-level triggers, transition tables, and set-based SQL rather than only micro-optimizing WHEN on row triggers.

## 55. Quick Reference Table

| Component | Key takeaway |
|---|---|
| `WHEN (...)` | Boolean predicate filtering trigger invocation |
| `OLD` | Row before UPDATE/DELETE |
| `NEW` | New row of INSERT/UPDATE |
| `IS DISTINCT FROM` | NULL-safe inequality check |
| `UPDATE OF x` | Target list mentions `x` |
| `UPDATE OF x,y` | Target list mentions `x` or `y` |
| `SET x=x` | Can still fire `UPDATE OF x` |
| BEFORE edits `NEW.x` | Does not automatically fire `UPDATE OF x` for that same UPDATE |
| AFTER UPDATE WHEN old/new differ | Catches real changes after BEFORE triggers |
| AFTER WHEN FALSE | Does not queue or call trigger function for that row |
| BEFORE WHEN FALSE | Does not call that function |
| UPDATE WHERE value differs | Can skip unnecessary row operations |
| `<>` with NULL | UNKNOWN |
| `IS DISTINCT FROM` with NULL | Definitive TRUE/FALSE |
| JSONB key | Compare extracted fields in WHEN |
| Generated column | Has special dependency rules with `UPDATE OF` |
| `FOR EACH ROW` | One event per affected row |
| `FOR EACH STATEMENT` | Statement-level event, even on 0 rows |
| Transition tables | `OLD TABLE`/`NEW TABLE` for set-based row processing |
| Constraint trigger WHEN | WHEN evaluated immediately even if action is deferred |
| Trigger recursion | Avoid updating the same table inside a trigger needlessly |
| AFTER audit | Write log/outbox once row has changed |
| BEFORE normalize | Assign `NEW` and `RETURN NEW` |
| CHECK/UNIQUE/FK | Preferred for supported invariants |
| `pg_trigger` | Trigger metadata |
| `pg_get_triggerdef` | Inspect SQL trigger definition |
| `pg_get_functiondef` | Inspect trigger function |
| `pg_stat_user_functions` | Calls/timing when tracking is enabled |
| `EXPLAIN (ANALYZE)` | Executes real SQL, including triggers |
| Transactional outbox | Decouple external event dispatch from DB transaction |
| RLS/GRANT | Authorization, not WHEN |
| SECURITY DEFINER | Requires trusted `search_path` and least privilege |
| UPSERT/MERGE | Trigger firing follows specific rules |
| `CREATE RULE` | Query rewrite mechanism distinct from triggers |

---

## Conclusion

**`WHEN` and `UPDATE OF` answer two different questions.** `UPDATE OF` asks **which columns were targeted in the UPDATE statement**, whereas `WHEN` asks **whether the condition on the current row/event holds**. Consequently, `UPDATE ... SET status=status` can fire an `UPDATE OF status` trigger even when status did not change. Conversely, a BEFORE UPDATE trigger can alter status in `NEW` without firing `UPDATE OF status` if status was absent from the original target list.

When the business contract is **an actual value change**, the key pattern to remember is **`AFTER UPDATE FOR EACH ROW WHEN (OLD.column IS DISTINCT FROM NEW.column)`**. It provides NULL-safe comparison well-suited for auditing, outboxes, and post-update processing. If you also want to restrict to statements explicitly targeting that column, you can combine it with `UPDATE OF`, keeping in mind that doing so may miss indirect changes made by BEFORE triggers.

`WHEN` conditions can reduce trigger function invocations, especially on AFTER row triggers where PostgreSQL skips queuing events when the condition is not TRUE. Still, **WHEN is not the UPDATE's WHERE clause**, does not stop row updates, does not replace CHECK/UNIQUE/FK, does not enforce authorization, and does not make external side effects exactly-once. For bulk changes, evaluate set-based SQL, transition tables, WHERE clauses to skip no-op updates, and WAL/index/lock costs.

Design rule of thumb: **decide clearly whether you want to detect "column mentioned" or "value actually changed," pick the right timing/level, handle NULLs with `IS DISTINCT FROM`, account for BEFORE triggers, and measure cost on realistic workloads.** That keeps triggers both semantically accurate and free of wasted calls, false audits, or dropped events.
