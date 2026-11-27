# Deferrable Constraints and SET CONSTRAINTS in PostgreSQL

Constraints are one of the core mechanisms PostgreSQL uses to keep data valid: `PRIMARY KEY` guarantees row identity, `UNIQUE` prevents duplicate values, `FOREIGN KEY` protects referential relationships, and `CHECK` restricts value domains. Normally, when a statement causes data to violate a constraint, PostgreSQL raises an error immediately rather than allowing an invalid state to persist.

However, some workflows must execute **multiple steps within a single transaction**. After the first step, data may temporarily fail a constraint, yet by the time the final step completes, the entire dataset is valid again.

Examples:

- Swapping two unique codes between two records.
- Inserting a child record before its parent record while guaranteeing both exist before commit.
- Constructing two rows with a cyclic reference inside one transaction.
- Temporarily moving objects across a relational hierarchy and completing the new links before the transaction ends.

PostgreSQL supports these scenarios via **deferrable constraints** and the **`SET CONSTRAINTS`** command. When configured and used properly, they shift certain checks from **statement execution time** to **transaction commit time**, while still guaranteeing that committed data satisfies every constraint.

This lesson uses modern PostgreSQL with complete examples covering `UNIQUE`, `FOREIGN KEY`, `NO ACTION`, `RESTRICT`, `SET CONSTRAINTS ... DEFERRED/IMMEDIATE`, inspecting `pg_constraint`, and considerations for transactions, migrations, and Java/JDBC applications.

## 1. Viewing the Problem Through a Multi-Step Transaction

Suppose an employees table has two badge holders:

| employee_id | badge_code |
| ---: | --- |
| 1 | A |
| 2 | B |

Due to a role rotation, the two employees need to **swap badge codes**:

~~~text
Initial:  employee 1 = A; employee 2 = B
Target:   employee 1 = B; employee 2 = A
~~~

If `badge_code` has an immediate `UNIQUE` constraint, the first update:

~~~sql
UPDATE employees
SET badge_code = 'B'
WHERE employee_id = 1;
~~~

is rejected because employee 2 **currently** holds code `B`. Yet **after both updates**, each code still appears exactly once.

With a `UNIQUE DEFERRABLE` constraint, you can structure it as:

~~~text
BEGIN
  |
  +-- SET CONSTRAINTS ... DEFERRED
  |
  +-- employee 1: A -> B     [temporarily duplicates B]
  |
  +-- employee 2: B -> A     [no longer duplicate]
  |
  +-- COMMIT
        |
        +-- PostgreSQL checks deferred constraints
        +-- Final data valid -> COMMIT succeeds
~~~

If two employees still share code `B` at transaction end, `COMMIT` fails. **Deferring does not mean skipping validation.**

### What Makes a “Temporary State”?

In PostgreSQL, a transaction groups multiple SQL statements into one atomic unit:

~~~sql
BEGIN;

-- Step 1
-- Step 2
-- ...

COMMIT;
~~~

Uncommitted changes are not visible as committed data to other transactions under MVCC. The fact that PostgreSQL lets **the active transaction itself** temporarily observe a state violating a deferred constraint does not mean other sessions can freely read uncommitted broken data.

The essential rule is to **resolve all violations before PostgreSQL checks the constraint** at `COMMIT` or at an explicit `SET CONSTRAINTS ... IMMEDIATE`.

## 2. Three Concepts to Distinguish

When creating a constraint of a type that supports deferral, PostgreSQL lets you declare:

~~~sql
CONSTRAINT constraint_name
    UNIQUE (column_name)
    DEFERRABLE INITIALLY IMMEDIATE
~~~

or:

~~~sql
CONSTRAINT constraint_name
    UNIQUE (column_name)
    DEFERRABLE INITIALLY DEFERRED
~~~

### 2.1. NOT DEFERRABLE

**`NOT DEFERRABLE`** means the constraint cannot be switched to deferred mode via `SET CONSTRAINTS`.

~~~sql
CONSTRAINT uq_email UNIQUE (email) NOT DEFERRABLE
~~~

This is the default for eligible constraints when `DEFERRABLE` is omitted. For a `NOT DEFERRABLE` constraint, `SET CONSTRAINTS ALL DEFERRED` does not make it deferrable.

### 2.2. DEFERRABLE

**`DEFERRABLE`** means the constraint **is capable of switching** between:

- **`IMMEDIATE`:** checked at the constraint's standard statement timing; does not allow a violation to persist across statements as deferred mode does.
- **`DEFERRED`:** postpones eligible checks until transaction end unless checked earlier on request.

The `DEFERRABLE` keyword **only states capability**; it does not by itself specify which mode a new transaction starts in.

### 2.3. INITIALLY IMMEDIATE and INITIALLY DEFERRED

This sets the **constraint's default mode at the start of every transaction**:

| Declaration | Can Switch to DEFERRED? | Initial Mode per Transaction |
| --- | --- | --- |
| `NOT DEFERRABLE` | No | Non-deferred checking |
| `DEFERRABLE INITIALLY IMMEDIATE` | Yes | `IMMEDIATE` |
| `DEFERRABLE INITIALLY DEFERRED` | Yes | `DEFERRED` |

If you write `DEFERRABLE` without `INITIALLY ...`, the default is **`INITIALLY IMMEDIATE`**.

A quick mnemonic:

~~~text
DEFERRABLE       = is deferral allowed?
INITIALLY ...    = when is it checked by default?
SET CONSTRAINTS  = change mode for the current transaction?
~~~

### Example Comparing Three Declarations

~~~sql
CREATE TABLE example_nondef (
    code text UNIQUE NOT DEFERRABLE
);

CREATE TABLE example_def_imm (
    code text UNIQUE DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE example_def_def (
    code text UNIQUE DEFERRABLE INITIALLY DEFERRED
);
~~~

All three tables share the same `text` column type, yet **differ in when uniqueness is checked** across multiple statements in a transaction.

## 3. Which Constraint Types Can Be Deferred?

In PostgreSQL, standard constraint types supporting `DEFERRABLE` are:

- `UNIQUE`.
- `PRIMARY KEY`.
- `FOREIGN KEY`.
- `EXCLUDE`.
- Appropriately declared **constraint triggers**.

`SET CONSTRAINTS` deferral does not apply to:

- `NOT NULL`.
- Standard `CHECK` constraints.

### Summary Table

| Type | Supports Deferral? | Example Scenario |
| --- | --- | --- |
| `UNIQUE` | Yes | Swapping two unique values |
| `PRIMARY KEY` | Yes | Multi-step key adjustments in one transaction |
| `FOREIGN KEY` | Yes | Inserting referencing child before referenced parent |
| `EXCLUDE` | Yes | Temporarily rearranging intervals / exclusion groups |
| `CHECK` | Not via this mechanism | Positive-quantity check still enforced under normal timing |
| `NOT NULL` | No | Cannot leave NULL in a required column until COMMIT |
| `CONSTRAINT TRIGGER` | Yes, when declared `DEFERRABLE` | End-of-transaction custom invariant checks |

Table example:

~~~sql
CREATE TABLE example_rules (
    id integer PRIMARY KEY DEFERRABLE,
    name text NOT NULL,
    quantity integer CHECK (quantity > 0),
    CONSTRAINT uq_name UNIQUE (name)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Even while `uq_name` is deferred, writing `name = NULL` still violates `NOT NULL` at normal timing, and `quantity = -1` still violates `CHECK`. **No `SET CONSTRAINTS ALL DEFERRED` command can defer those two rules to transaction end.**

### Distinguishing “Not Deferrable” from “Initially Immediate”

These two declarations:

~~~sql
UNIQUE (code) NOT DEFERRABLE
~~~

and:

~~~sql
UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE
~~~

both reject duplicates if statements run without changing mode, yet differ fundamentally: **only the second can be switched to `DEFERRED`** inside a transaction.

Make this decision upfront during schema design, because altering deferrability after creation works differently across constraint types.

## 4. How Does SET CONSTRAINTS Work?

Syntax:

~~~sql
SET CONSTRAINTS { ALL | constraint_name [, ...] }
    { DEFERRED | IMMEDIATE };
~~~

Example:

~~~sql
BEGIN;

SET CONSTRAINTS ALL DEFERRED;

-- Perform related updates.

SET CONSTRAINTS ALL IMMEDIATE;

COMMIT;
~~~

### 4.1. Applies Only Within the Current Transaction

`SET CONSTRAINTS` changes check timing inside the **active transaction**. It does not become a permanent session default for future transactions.

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
-- SQL statements.
COMMIT;

-- A new transaction reverts to each constraint's INITIALLY ... mode.
BEGIN;
-- Does not inherit SET CONSTRAINTS from the previous transaction.
COMMIT;
~~~

Running `SET CONSTRAINTS` **outside a transaction block** emits a warning in PostgreSQL and has no lasting effect. When deferral is needed, place it after `BEGIN` and before statements that create temporary violations.

### 4.2. ALL Does Not Mean Every Constraint Becomes Deferrable

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
~~~

This applies only to **deferrable constraints** in transaction scope; it does not alter `NOT DEFERRABLE`, `NOT NULL`, or `CHECK`.

Hence:

~~~sql
INSERT INTO some_table (required_name) VALUES (NULL);
~~~

still fails when `required_name` is `NOT NULL`, even after `SET CONSTRAINTS ALL DEFERRED`.

### 4.3. Targeting One or More Specific Constraints

To defer only a single constraint:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

-- Other constraints keep their own modes.

COMMIT;
~~~

Constraint names can be schema-qualified, and PostgreSQL resolves constraint names via schemas and `search_path`. **Constraint names are not guaranteed unique across the entire database**; if multiple matching constraints exist in scope, the command applies to all matching ones.

In migration code, using **intentional constraint names** and explicit schema qualification prevents ambiguity. Before relying on `SET CONSTRAINTS`, verify constraint names in the catalog.

### 4.4. Switching from DEFERRED to IMMEDIATE Triggers Immediate Checking

This is the most important rule of the command:

~~~sql
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;
~~~

If the constraint is currently `DEFERRED`, PostgreSQL **retroactively checks all pending violations** while switching to `IMMEDIATE`.

If any violation exists, `SET CONSTRAINTS ... IMMEDIATE` **fails**, and the mode does not change. Inside a standard transaction, that failure aborts the transaction until rollback or savepoint recovery.

Thus `SET CONSTRAINTS ... IMMEDIATE` works well as an **early verification checkpoint** before `COMMIT`, provided the application handles errors properly.

## 5. Lab 1: Swapping Two UNIQUE Values

This is the clearest example showing why deferrable uniqueness exists.

### 5.1. Creating the Schema and Table

Run in a lab database where you have schema-creation privileges:

~~~sql
CREATE SCHEMA def_lab;

CREATE TABLE def_lab.employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL,
    badge_code text NOT NULL,
    CONSTRAINT uq_badge_code
        UNIQUE (badge_code)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO def_lab.employees
    (employee_id, full_name, badge_code)
VALUES
    (1, 'Lan', 'A'),
    (2, 'Minh', 'B');
~~~

Inspect:

~~~sql
SELECT employee_id, full_name, badge_code
FROM def_lab.employees
ORDER BY employee_id;
~~~

Initial result:

~~~text
 employee_id | full_name | badge_code
-------------+-----------+-----------
           1 | Lan       | A
           2 | Minh      | B
~~~

`employee_id` is a standard `PRIMARY KEY`, while `badge_code` is protected by **`UNIQUE DEFERRABLE INITIALLY IMMEDIATE`**. These two constraints can have different check timing.

### 5.2. Trying a Direct Swap Without Deferring

~~~sql
BEGIN;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Expected error: B is currently held by employee 2.
ROLLBACK;
~~~

The `UPDATE` is rejected because `uq_badge_code` starts in `IMMEDIATE` mode. `ROLLBACK` clears the aborted transaction and leaves both codes unchanged.

Do not “solve” a swap by temporarily dropping and re-adding `UNIQUE`. Removing the constraint opens a window for concurrent transactions to write unwanted duplicates and introduces extra concurrency hazards.

### 5.3. Deferring a Specific UNIQUE Constraint

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- At this point the current transaction temporarily sees two B codes.

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- No duplicates remain.
COMMIT;
~~~

After `COMMIT`:

~~~sql
SELECT employee_id, badge_code
FROM def_lab.employees
ORDER BY employee_id;
~~~

Result:

~~~text
 employee_id | badge_code
-------------+-----------
           1 | B
           2 | A
~~~

Key takeaways:

1. Both `UPDATE` statements run in the **same transaction**.
2. `SET CONSTRAINTS` runs **before the step that creates a temporary duplicate**.
3. The constraint was declared **`DEFERRABLE`**, so switching modes is allowed.
4. At `COMMIT`, the final data satisfies `UNIQUE`, so the transaction succeeds.

### 5.4. Restoring Lab Data to Test Again

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 2;

COMMIT;
~~~

The rows return to `(1, A)` and `(2, B)`. Run this only on the lab table created in this section.

## 6. What If UNIQUE Is Still Violated at COMMIT?

Deferring never disables validation:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Employee 2's code B is never changed.
COMMIT;
~~~

This time **`COMMIT` fails** because two rows hold `badge_code = 'B'`. The transaction is rolled back, and previously committed data remains intact.

In logs and drivers, the error surfaces **at commit time**, not on the `UPDATE` that introduced the temporary duplicate.

This has direct implications for application code:

- Never assume a business operation succeeded merely because every `UPDATE` returned cleanly.
- Handle errors at `COMMIT`, not only around individual statements.
- If commit fails, never proceed assuming the transaction was saved.
- In JDBC or transaction frameworks, check exceptions thrown during `connection.commit()` or transaction-boundary completion.

If using retries, classify errors carefully and ensure operations are idempotent; **a unique violation caused by genuinely duplicate final data** will not vanish by retrying identically.

## 7. Early Verification with SET CONSTRAINTS ... IMMEDIATE

You can instruct PostgreSQL to validate mid-transaction before committing:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Code B is still duplicated here.
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;

-- The statement above is expected to fail.
ROLLBACK;
~~~

This example **intentionally fails**. In `psql`, you will see the unique violation **on `SET CONSTRAINTS ... IMMEDIATE`**.

Working version:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- Verify immediately without waiting for COMMIT.
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;

-- Uniqueness is now verified.
COMMIT;
~~~

Now the two codes are swapped again. To return to the original state, run the restore transaction from Section 5.4.

### Why Add an Early Verification Step?

In complex workflows, a transaction has several stages:

~~~text
1. Reassign identifiers
2. Verify deferrable constraints
3. Compute derived side tables
4. Write audit log inside the same transaction
5. COMMIT
~~~

Checking at step 2 catches mistakes before doing additional work. Still, if step 2 fails, the transaction must roll back or revert to a valid savepoint—never ignore the error and call `COMMIT`.

## 8. Lab 2: Deferrable FOREIGN KEY

Alongside uniqueness, a common case is **creating a child record before its parent record inside the same transaction**.

### 8.1. Creating Two Tables with a DEFERRABLE Foreign Key

~~~sql
CREATE TABLE def_lab.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE def_lab.staff (
    staff_id integer PRIMARY KEY,
    department_id integer NOT NULL,
    staff_name text NOT NULL,
    CONSTRAINT fk_staff_department
        FOREIGN KEY (department_id)
        REFERENCES def_lab.departments (department_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Explanation:

- `departments.department_id` is the referenced primary key.
- `staff.department_id` is the child's foreign key column.
- `ON DELETE NO ACTION` is the referential behavior to distinguish from `RESTRICT` when discussing deferral.
- `DEFERRABLE INITIALLY IMMEDIATE` lets `SET CONSTRAINTS` switch FK check timing.

### 8.2. Trying to Insert Staff Before Department Without Deferring

~~~sql
BEGIN;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (1001, 10, 'An');

-- Error: department_id = 10 does not exist yet.
ROLLBACK;
~~~

When checked immediately, PostgreSQL rejects a child row referencing a nonexistent parent row.

### 8.3. Deferring the FK and Populating Both Tables in One Transaction

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (1001, 10, 'An');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES
    (10, 'Engineering');

COMMIT;
~~~

The transaction commits cleanly because by commit time, `staff.department_id = 10` has a matching `departments.department_id = 10` row.

Verify:

~~~sql
SELECT
    s.staff_id,
    s.staff_name,
    d.department_name
FROM def_lab.staff AS s
JOIN def_lab.departments AS d
    ON d.department_id = s.department_id
ORDER BY s.staff_id;
~~~

Expected result shows employee `An` in `Engineering`.

**Do not conclude** that applications should routinely insert children before parents. In most normal write paths, inserting parent rows before child rows is much clearer. Deferral shines when there is a deliberate design need such as interdependent bulk imports, key rewrites, or cyclic references.

### 8.4. An FK Violation at Transaction End Still Fails

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (2002, 999, 'Binh');

-- Department 999 is never created.
COMMIT;
~~~

`COMMIT` fails due to the missing parent row. Row `staff_id = 2002` is never committed.

Deferrable constraints **enforce integrity at check time**; they never allow orphan references to be persisted.

## 9. NO ACTION vs. RESTRICT in FOREIGN KEY

This is easy to confuse because both typically **block deleting a parent row while child rows remain**.

Compare:

~~~sql
FOREIGN KEY (department_id)
REFERENCES def_lab.departments(department_id)
ON DELETE NO ACTION
DEFERRABLE INITIALLY DEFERRED
~~~

versus:

~~~sql
FOREIGN KEY (department_id)
REFERENCES def_lab.departments(department_id)
ON DELETE RESTRICT
DEFERRABLE INITIALLY DEFERRED
~~~

### 9.1. NO ACTION Allows Deferring the Referential Check

With `NO ACTION` and a deferrable FK, PostgreSQL lets you temporarily delete the parent first as long as **all referencing child rows are handled before check time**.

Current state:

~~~text
departments:  department_id = 10
staff:        staff_id = 1001, department_id = 10
~~~

Test inside a rolled-back transaction:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

DELETE FROM def_lab.departments
WHERE department_id = 10;

DELETE FROM def_lab.staff
WHERE staff_id = 1001;

-- No child rows reference department 10 anymore.
SET CONSTRAINTS def_lab.fk_staff_department IMMEDIATE;

-- Preserve real lab data:
ROLLBACK;
~~~

Because the constraint was deferred and the final state after both `DELETE`s has no violations, the check succeeds.

### 9.2. RESTRICT Does Not Wait Until Transaction End for the Delete Action

`ON DELETE RESTRICT` means **do not allow deleting a parent row while referencing child rows exist**, even if the FK constraint is declared `DEFERRABLE` in other respects.

In other words:

> **`RESTRICT` is a referential action that cannot be deferred for that restriction; `NO ACTION` is a check that can be deferred when the constraint is declared deferrable and switched to `DEFERRED`.**

If a workflow needs “temporarily delete parent, clean up children later in the same transaction”, design with `NO ACTION DEFERRABLE` and test it, rather than treating `RESTRICT` as a synonym.

### 9.3. CASCADE, SET NULL, and SET DEFAULT Also Differ

These actions:

~~~sql
ON DELETE CASCADE
ON DELETE SET NULL
ON DELETE SET DEFAULT
~~~

define **modifications PostgreSQL performs on child rows** when a parent row is deleted. They are not merely a deferrable check like `NO ACTION`; referential modifications such as deleting children or setting null/default execute per DML action rules rather than waiting until `COMMIT` simply because the constraint is deferrable.

| Referential Action | When Parent Deleted with Existing Children | Can Rely on Deferral to Temporarily Leave Children? |
| --- | --- | --- |
| `NO ACTION` | Checks relation; raises error if references remain | **Yes**, if FK is deferrable and in deferred mode |
| `RESTRICT` | Rejects parent delete while references exist | **No** for the `RESTRICT` action |
| `CASCADE` | Deletes child rows per FK rules | Not a “wait until commit then cascade” model |
| `SET NULL` | Sets child FK to null | No; must also satisfy `NOT NULL` and other constraints |
| `SET DEFAULT` | Sets child FK to default | No; new default must still satisfy final validity |

Do not confuse `ON DELETE CASCADE` in an FK with `DROP TABLE ... CASCADE` in DDL: one operates on **data rows**, the other on **schema objects**.

## 10. Lab 3: Cyclic References Between Two Tables

Some models contain cyclic relationships—for instance, each department has a leader who is an employee of that department, while every employee must belong to a department.

~~~text
departments
    department_id ──────────────────┐
    leader_staff_id ──────┐         |
                         |         |
                         v         v
                       staff
                       staff_id
                       department_id
~~~

If both FK columns are required (`NOT NULL`), initial insertion faces a chicken-and-egg ordering problem: without an employee you cannot create the department with its leader; without the department you cannot create the employee.

### 10.1. Creating Two Tables with Deferrable FKs

To avoid touching the tables from the previous section, use fresh names:

~~~sql
CREATE TABLE def_lab.teams (
    team_id integer PRIMARY KEY,
    team_name text NOT NULL,
    leader_id integer NOT NULL
);

CREATE TABLE def_lab.team_members (
    member_id integer PRIMARY KEY,
    team_id integer NOT NULL,
    member_name text NOT NULL,
    CONSTRAINT fk_member_team
        FOREIGN KEY (team_id)
        REFERENCES def_lab.teams(team_id)
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE def_lab.teams
ADD CONSTRAINT fk_team_leader
FOREIGN KEY (leader_id)
REFERENCES def_lab.team_members(member_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Both FKs default to checking at transaction end.

### 10.2. Inserting Both Linked Rows in One Transaction

~~~sql
BEGIN;

INSERT INTO def_lab.teams
    (team_id, team_name, leader_id)
VALUES
    (100, 'Payments', 1000);

INSERT INTO def_lab.team_members
    (member_id, team_id, member_name)
VALUES
    (1000, 100, 'Chi');

COMMIT;
~~~

Once both inserts finish, both referential links exist:

~~~sql
SELECT
    t.team_id,
    t.team_name,
    m.member_name AS leader_name
FROM def_lab.teams AS t
JOIN def_lab.team_members AS m
    ON m.member_id = t.leader_id;
~~~

### Limits of the Cyclic Reference Example

The two FKs above guarantee:

- `teams.leader_id` references **an existing member**.
- `team_members.team_id` references **an existing team**.

However, they **do not guarantee the leader belongs to that exact team**. Enforcing that rule requires an additional composite key/unique constraint and matching FK, or another data mechanism.

This demonstrates that deferral controls **when a constraint is checked**, without making the constraint's logical rule any stronger.

### Should Cyclic References Be Used Everywhere?

No. Cyclic relationships complicate bulk imports, deletions, FK changes, and migrations. Often an approach like:

1. Create the department without a leader yet, if the domain permits.
2. Create the employee belonging to the department.
3. Assign the leader within the transaction.

with a nullable `leader_id` during initialization is much simpler. Use cyclic deferrable FKs only when the domain genuinely demands it and relaxing nullability is not acceptable.

## 11. DEFERRABLE UNIQUE and INSERT ... ON CONFLICT

An important trade-off: PostgreSQL requires a suitable unique index/constraint as a **conflict arbiter** for:

~~~sql
INSERT INTO some_table (...)
VALUES (...)
ON CONFLICT (...) DO UPDATE ...;
~~~

However, **deferrable unique constraints cannot be used as conflict arbiters for `ON CONFLICT`** under PostgreSQL rules.

Example:

~~~sql
CREATE TABLE def_lab.promo_codes (
    promo_id integer PRIMARY KEY,
    code text NOT NULL,
    CONSTRAINT uq_promo_code
        UNIQUE (code)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

The statement below is **not a valid upsert pattern on a deferrable constraint**:

~~~sql
-- Illustrates a case NOT supported directly:
INSERT INTO def_lab.promo_codes (promo_id, code)
VALUES (1, 'SAVE10')
ON CONFLICT ON CONSTRAINT uq_promo_code
DO UPDATE SET code = EXCLUDED.code;
~~~

PostgreSQL cannot use `uq_promo_code` as an arbiter because its uniqueness constraint is deferrable.

### Why Does This Matter?

If your application relies heavily on `INSERT ... ON CONFLICT (code) DO UPDATE`, switching `UNIQUE(code)` from non-deferrable to deferrable to help one migration can **break existing production write paths**.

Before choosing deferrable uniqueness, ask:

- Does the application run UPSERTs against this column?
- Can a different non-deferrable unique key serve as the arbiter?
- Is swapping values a rare administrative task or a core frequent operation?
- Can the renaming workflow be redesigned without temporary duplicates?

Many systems should keep a **standard non-deferrable unique constraint** for keys used with `ON CONFLICT`, rather than trading away upsert support for deferral.

### CREATE UNIQUE INDEX Has No DEFERRABLE Option

Deferrability is a property of a **constraint** declared with supported syntax, not an arbitrary option on `CREATE UNIQUE INDEX`.

Right approach:

~~~sql
ALTER TABLE def_lab.some_table
ADD CONSTRAINT uq_some_code
UNIQUE (code)
DEFERRABLE INITIALLY IMMEDIATE;
~~~

This example assumes `some_table` and `code` exist. Never write `CREATE UNIQUE INDEX ... DEFERRABLE`, as that is not valid PostgreSQL syntax.

## 12. DEFERRABLE PRIMARY KEY and EXCLUDE Constraints

### 12.1. Deferrable PRIMARY KEY

~~~sql
CREATE TABLE def_lab.legacy_keys (
    old_key text NOT NULL,
    description text NOT NULL,
    CONSTRAINT pk_legacy_keys
        PRIMARY KEY (old_key)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

`PRIMARY KEY` still requires keys to be non-NULL and unique. Deferrability affects only the **uniqueness check**; it never lets you insert NULL into a PK column and fix it before `COMMIT` via `SET CONSTRAINTS ALL DEFERRED`.

When designing a primary key, account for referencing FKs, UPSERT paths, and PostgreSQL's rules on non-deferrable target keys and arbiters. Never mark every PK deferrable by habit.

### 12.2. EXCLUDE for Exclusion Rules

`EXCLUDE` is a powerful PostgreSQL constraint preventing pairs of rows from simultaneously satisfying all excluded comparisons. It is commonly used for bookings, time spans, or spatial ranges.

For example, preventing two overlapping meetings in the same room requires `btree_gist` so GiST supports equality on integer IDs:

~~~sql
-- Run only in a lab database with extension-installation privileges.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE def_lab.meeting_rooms (
    booking_id integer PRIMARY KEY,
    room_id integer NOT NULL,
    during tstzrange NOT NULL,
    CONSTRAINT ex_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            during WITH &&
        )
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Here:

- `tstzrange` represents a timezone-aware time interval.
- `&&` checks whether two intervals overlap.
- `EXCLUDE` forbids two rows for the **same room** from having overlapping intervals.
- `DEFERRABLE` allows multi-step schedule adjustments inside a single transaction.

Test insert:

~~~sql
INSERT INTO def_lab.meeting_rooms
    (booking_id, room_id, during)
VALUES
    (
        1, 10,
        tstzrange(
            '2026-11-16 09:00:00+07',
            '2026-11-16 10:00:00+07',
            '[)'
        )
    );
~~~

Inserting a second overlapping meeting in the same room fails unless the transaction is in deferred mode and resolves all overlaps before validation.

**Do not treat this example as unconditionally available:** the extension, operator classes, installation privileges, and indexes must be compatible with your target PostgreSQL environment.

## 13. Constraint Triggers and SET CONSTRAINTS

Beyond declarative constraints, PostgreSQL supports **`DEFERRABLE` constraint triggers**. This specialized trigger type can be scheduled to fire immediately or deferred until transaction end.

Syntax outline:

~~~sql
CREATE CONSTRAINT TRIGGER trigger_name
AFTER INSERT OR UPDATE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
~~~

Key details:

- It is an **`AFTER ROW` trigger** subject to constraint trigger rules.
- The trigger function must exist, return `trigger`, and implement validation and exception raising properly.
- `SET CONSTRAINTS` can control check timing for eligible constraint triggers.
- An ordinary trigger created via `CREATE TRIGGER` does not become a deferrable constraint trigger.

### When to Consider a Constraint Trigger

Example invariant that cannot be expressed as a single-row `CHECK`:

~~~text
A transfer batch must balance total debits and credits
before COMMIT, even when multiple rows are inserted mid-transaction.
~~~

A well-designed constraint trigger can validate certain business invariants at deferred check time. Still, concurrency, MVCC snapshots, locking, and concurrent transactions mean implementation is **rarely as simple as running a naive SUM at transaction end**.

Whenever `FOREIGN KEY`, `UNIQUE`, `EXCLUDE`, or cleaner schema modeling can express the rule, prefer declarative constraints. Reserve constraint triggers for rules genuinely requiring custom logic, and test them thoroughly under concurrent sessions.

## 14. Identifying DEFERRABLE Constraints via the Catalog

PostgreSQL stores constraint metadata in `pg_constraint`. Two columns are especially helpful:

- `condeferrable`: whether the constraint **can be deferred**.
- `condeferred`: whether it **starts in `DEFERRED` mode by default**.

### 14.1. Listing Constraints on Lab Tables

~~~sql
SELECT
    n.nspname AS schema_name,
    c.conrelid::regclass AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    c.condeferrable AS is_deferrable,
    c.condeferred AS initially_deferred,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_namespace AS n
    ON n.oid = c.connamespace
WHERE n.nspname = 'def_lab'
ORDER BY c.conrelid::regclass::text, c.conname;
~~~

Common `contype` values:

| `contype` | Constraint Type |
| --- | --- |
| `p` | Primary key |
| `u` | Unique |
| `f` | Foreign key |
| `x` | Exclusion |
| `c` | Check |

`pg_get_constraintdef` returns a human-readable definition that is clearer than inspecting raw flags alone.

### 14.2. Filtering Only Deferrable Constraints

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
  AND condeferrable
ORDER BY conrelid::regclass::text, conname;
~~~

This is a fast way to audit a schema before writing `SET CONSTRAINTS`. It shows **stored catalog defaults**, not temporary mode overrides active inside a running transaction.

### 14.3. Inspecting FOREIGN KEYs and Referential Actions

~~~sql
SELECT
    conname,
    conrelid::regclass AS child_table,
    confrelid::regclass AS parent_table,
    condeferrable,
    condeferred,
    confdeltype,
    confupdtype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
  AND contype = 'f'
ORDER BY conname;
~~~

Rather than decoding `confdeltype` and `confupdtype` characters manually, read `pg_get_constraintdef` to see `ON DELETE NO ACTION`, `RESTRICT`, or `CASCADE` clearly.

### 14.4. \d in psql

In `psql`:

~~~text
\d+ def_lab.employees
\d+ def_lab.staff
\d+ def_lab.teams
~~~

These are `psql` meta-commands displaying constraints and attributes formatted for your tool version. The SQL queries above are better when extracting structured metadata for audits or reports.

## 15. Converting an Existing Constraint to DEFERRABLE

Not all constraint types share the same way to change deferrability after creation.

### 15.1. ALTER CONSTRAINT for FOREIGN KEY

PostgreSQL lets you change deferrability of an existing FK using:

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY DEFERRED;
~~~

Or switch it back:

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY IMMEDIATE;
~~~

Ensure appropriate ownership privileges and plan locks/DDL impact on real tables.

### 15.2. For UNIQUE / PRIMARY KEY / EXCLUDE, Plan Another Strategy

`ALTER TABLE ... ALTER CONSTRAINT ... DEFERRABLE` in modern PostgreSQL **does not support changing all constraint types identically**; changing deferrability in place primarily applies to **foreign key constraints**.

To convert an existing `UNIQUE NOT DEFERRABLE` constraint to deferrable, you typically must **plan a controlled drop-and-recreate migration**, evaluating:

- Foreign keys or other objects depending on the old constraint or index.
- Write paths relying on `INSERT ... ON CONFLICT`.
- Lock duration and index rebuild time.
- Whether existing data is still unique.
- Rollback plans or building a replacement structure safely.

Never casually run:

~~~sql
ALTER TABLE real_orders
DROP CONSTRAINT uq_order_code;
~~~

in production just to recreate a constraint without auditing dependencies and write concurrency. During the window without the unique constraint, other transactions could write duplicates if access is not properly controlled.

## 16. Impact on Transactions and Isolation

Deferrable constraints are a **validation timing rule**, not a new isolation level.

A transaction can temporarily violate a deferred unique or FK constraint, yet:

- Other transactions still do not see uncommitted changes under MVCC.
- PostgreSQL still uses MVCC and locks to coordinate concurrent writes.
- Remaining violations are still caught at check time.
- Constraint errors can surface late, even after several prior steps succeeded.

### 16.1. Deferral Does Not Make Conflicting Concurrent Writes Valid

Suppose two sessions concurrently try to assign code `PROMO-1` to two different rows. Even if the unique constraint is deferrable, **both transactions cannot commit final states holding the same code**.

In practice, one transaction may block waiting on the other, hit a unique violation, or behave according to PostgreSQL's concurrency arbitration. Never use `SET CONSTRAINTS ALL DEFERRED` thinking it bypasses locks or lets conflicting transactions both commit.

### 16.2. Deferral Does Not Replace Locking for Complex Invariants

Rules such as:

~~~text
Total tickets sold must not exceed seat capacity.
Account balances stay non-negative after a transfer.
Each team has exactly one active leader.
~~~

may require tailored constraints, transactions, row locks, isolation levels, or concurrency control. `DEFERRABLE` only changes **when supported constraints are checked**; it does not provide an arbitrary cross-row invariant engine.

### 16.3. Avoid Unnecessarily Long Transactions

Because errors can surface late, developers are sometimes tempted to keep transactions open for a long time across many steps. That is usually harmful:

- Long transactions hold locks longer.
- They interfere with vacuum and row version cleanup.
- They waste more work if a late constraint check forces a rollback.
- They make retries and root-cause debugging harder.

Keep transactions short around the true unit of business work, using `SET CONSTRAINTS ... IMMEDIATE` checkpoints where appropriate.

## 17. SET CONSTRAINTS in Java/JDBC

Java applications using JDBC need an **explicit transaction** to control constraint modes.

Illustrative code sample:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;

public class DeferredConstraintExample {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:postgresql://127.0.0.1:5432/lab_db";
        String user = System.getenv("PG_LAB_USER");
        String password = System.getenv("PG_LAB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {

            connection.setAutoCommit(false);

            try {
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS def_lab.uq_badge_code DEFERRED"
                    );
                }

                try (PreparedStatement update =
                         connection.prepareStatement(
                             "UPDATE def_lab.employees "
                             + "SET badge_code = ? "
                             + "WHERE employee_id = ?")) {

                    update.setString(1, "B");
                    update.setInt(2, 1);
                    update.executeUpdate();

                    update.setString(1, "A");
                    update.setInt(2, 2);
                    update.executeUpdate();
                }

                // Optional: force immediate verification right here.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE"
                    );
                }

                connection.commit();
            } catch (SQLException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
~~~

This example assumes:

- Table `def_lab.employees` already exists.
- Initial rows are `(1, A)` and `(2, B)`.
- The PostgreSQL JDBC driver is on the classpath.
- Environment variables hold valid credentials.
- The database user has privileges to update those rows.

Running it a second time after the codes have already swapped can produce an unexpected state or a duplicate at transaction end. Always check preconditions and **idempotency** in real workflows.

### 17.1. Why Is setAutoCommit(false) Essential?

When JDBC runs in autocommit mode, each statement runs in its own separate transaction. There is no single transaction spanning:

~~~text
SET CONSTRAINTS DEFERRED
UPDATE step 1
UPDATE step 2
COMMIT
~~~

The goal is for **all statements to execute on the same JDBC `Connection` inside the same transaction**.

### 17.2. Errors Can Occur at Commit

Catching exceptions only around `executeUpdate()` is insufficient. `connection.commit()` can also throw `SQLException` when a deferred constraint fails.

Applications should classify errors by SQLSTATE/exception, log diagnostic context without leaking sensitive data, roll back failed transactions, and never report success to users before commit actually completes.

### 17.3. Connection Pools

With HikariCP or similar pools, `Connection.close()` returns the connection to the pool. Every request must still commit or roll back cleanly before returning the connection and never rely on leftover transaction state from an earlier request.

`SET CONSTRAINTS` is not a permanent session setting; once a transaction ends, the next transaction starts with each constraint's **`INITIALLY ...`** mode. Still, an abandoned open transaction in a pool harms data consistency, locks, and subsequent requests.

## 18. Common Errors and Root-Cause Diagnosis

### 18.1. SET CONSTRAINTS Has No Effect

Common causes:

1. Executed outside `BEGIN ... COMMIT` (no active multi-statement transaction).
2. The constraint is actually `NOT DEFERRABLE`.
3. Wrong constraint name or schema mismatch.
4. Data violated `NOT NULL` or `CHECK`, which cannot be deferred.
5. The application accidentally used different connections for steps assumed to share one transaction.

Check:

~~~sql
SELECT
    conname,
    conrelid::regclass AS table_name,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
ORDER BY conname;
~~~

### 18.2. Still Fails When Using ON DELETE RESTRICT

`RESTRICT` cannot defer its restriction check until transaction end the way `NO ACTION DEFERRABLE` can. If a workflow must temporarily delete a parent before handling child rows, review the referential action and schema model.

### 18.3. COMMIT Fails Even Though Every UPDATE Succeeded

This is the expected signature of **deferred checking**: at commit time, the final state still violates a constraint. Inspect all modified rows in the transaction and the failing constraint name rather than looking only at the last SQL statement.

### 18.4. SET CONSTRAINTS ... IMMEDIATE Raises an Error

Switching from deferred to immediate forces PostgreSQL to check pending violations right away. If temporary inconsistencies have not been fixed yet, the early check fails. Roll back the transaction or revert to an intentional savepoint.

### 18.5. ON CONFLICT Cannot Use a Deferrable UNIQUE Constraint

`ON CONFLICT` requires an eligible non-deferrable arbiter; deferrable unique and exclusion constraints are not supported as arbiters. Review your constraint design or pick a write path not relying on a deferrable arbiter.

### 18.6. ALTER CONSTRAINT Cannot Modify UNIQUE

`ALTER TABLE ... ALTER CONSTRAINT ... DEFERRABLE` does not support every constraint type uniformly. For `UNIQUE` or `PRIMARY KEY`, design a proper migration rather than assuming FK syntax applies universally.

### 18.7. A Transaction Holds Violating State Too Long

Never abuse deferrability to accumulate thousands of unrelated operations. If the transaction fails mid-way, vast work must roll back; if it runs long, locks and MVCC bloat hurt the whole system.

### 18.8. Duplicate Constraint Names

In PostgreSQL, constraint names need not be unique database-wide, and `SET CONSTRAINTS` follows schema resolution rules. Name constraints clearly, check `pg_constraint` before migrations, and schema-qualify constraint names when appropriate.

## 19. Decision Flow: Should You Use DEFERRABLE?

~~~text
                 Multi-step update required?
                              |
                    +---------+---------+
                    |                   |
                   No                  Yes
                    |                   |
        Use standard            Can intermediate states
        constraints             violate a constraint?
                                        |
                               +--------+--------+
                               |                 |
                              No                Yes
                               |                 |
                   No deferral needed    Is constraint type
                                         DEFERRABLE?
                                               |
                                      +--------+--------+
                                      |                 |
                                     No                Yes
                                      |                 |
                             Change design/tx     Does it impact
                             or validation logic  ON CONFLICT / FK
                                                  / concurrency?
                                                       |
                                                       v
                                               Test on real workload
                                               and handle COMMIT errors
~~~

Questions to answer yourself:

- **Must data really be temporarily invalid?** Or can you reorder updates so it never violates?
- **Is the constraint type eligible for deferral?** Not applicable to `CHECK` or `NOT NULL`.
- **What defines valid final state?** Must be verified at or before commit.
- **Do any paths use `ON CONFLICT` or FKs requiring non-deferrable keys?** That is an architectural constraint.
- **How high is transaction contention?** Deferral does not replace concurrency control.
- **Do multiple services write to these tables?** Good constraints must hold even as new writers appear.

## 20. Combined Practice: Safely Updating Multiple Objects

A migration or workflow might need to swap employee badge codes and assign staff to a newly created department within one transaction.

Assume:

- `def_lab.employees` has `uq_badge_code DEFERRABLE`.
- `def_lab.staff` has `fk_staff_department DEFERRABLE`.
- Both tables belong to your dedicated lab and already hold sample data.

Transaction pattern:

~~~sql
BEGIN;

SET CONSTRAINTS
    def_lab.uq_badge_code,
    def_lab.fk_staff_department
DEFERRED;

-- Swap two badge codes.
UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- Insert staff referencing a department created right after.
INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (3003, 30, 'Dung');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES
    (30, 'Analytics');

-- Check before committing.
SET CONSTRAINTS
    def_lab.uq_badge_code,
    def_lab.fk_staff_department
IMMEDIATE;

COMMIT;
~~~

This example is **not idempotent**: running it repeatedly with the same IDs will collide on primary keys. It demonstrates grouping multiple deferred constraints in one transaction. In real migrations, verify initial state, plan idempotency, assess locks, and prepare rollback steps.

`SET CONSTRAINTS ... IMMEDIATE` succeeding confirms the requested constraints pass PostgreSQL rules at that point. It **does not prove external business rules outside the database are satisfied**.

## 21. Practice Exercises

Run these in schema `def_lab` or predict the outcomes first. Execute intentionally failing examples separately and end with `ROLLBACK` as needed.

### Exercise 1. Distinguish Three Declarations

Given:

~~~sql
UNIQUE (code) NOT DEFERRABLE

UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE

UNIQUE (code) DEFERRABLE INITIALLY DEFERRED
~~~

Identify which constraints can be switched to `DEFERRED` and which begin each transaction in `DEFERRED` mode.

### Exercise 2. Swap Unique Codes

Two rows hold codes `A` and `B`. Write a transaction using `SET CONSTRAINTS` to swap them while keeping `UNIQUE` satisfied by transaction end.

### Exercise 3. COMMIT Still Fails

A transaction with a deferred unique constraint updates the first row to the second row's code without updating the second row. Why do the `UPDATE` statements succeed while `COMMIT` fails?

### Exercise 4. Early Check

Inside a transaction with a deferred constraint, run `SET CONSTRAINTS ... IMMEDIATE` while a unique violation still exists. Which statement raises the error, and why?

### Exercise 5. Insert Child Before Parent

`staff.department_id` references `departments.department_id` via an FK declared `DEFERRABLE INITIALLY IMMEDIATE`. Write a transaction inserting the staff row before the department row that still commits cleanly.

### Exercise 6. RESTRICT vs. NO ACTION

What is the core difference between `ON DELETE RESTRICT` and `ON DELETE NO ACTION` when an FK constraint is declared `DEFERRABLE`?

### Exercise 7. Non-Deferrable Constraints

After:

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
~~~

will `quantity integer NOT NULL CHECK (quantity > 0)` temporarily accept `quantity = NULL` or `quantity = -5` until commit?

### Exercise 8. SET CONSTRAINTS Outside a Transaction

An application sends `SET CONSTRAINTS ALL DEFERRED` while each statement runs in autocommit mode. Why are subsequent statements not deferred as intended?

### Exercise 9. Metadata

Write a query against `pg_constraint` listing constraint name, table, `condeferrable`, and `condeferred` in schema `def_lab`.

### Exercise 10. UPSERT and Deferrable Uniqueness

Why might a column protected only by `UNIQUE DEFERRABLE` break an application using `INSERT ... ON CONFLICT (code) DO UPDATE`?

### Exercise 11. ALTER CONSTRAINT

Suppose an FK is currently `NOT DEFERRABLE`. Write the SQL to convert it to `DEFERRABLE INITIALLY DEFERRED`. Does the exact same syntax work for every unique constraint?

### Exercise 12. Transactions and Isolation

Does a deferrable constraint expose transaction A's uncommitted data to transaction B? Does it allow two concurrent transactions assigning the same unique code to both commit?

### Exercise 13. Cyclic Design

If `teams` requires a non-NULL `leader_id` and `team_members` requires a non-NULL `team_id`, how can two mutually referencing rows be created? Does the basic FK automatically guarantee the leader belongs to that exact team?

### Exercise 14. JDBC Error Handling

An application catches exceptions only around `executeUpdate()` and not around `connection.commit()`. What risk arises when using `INITIALLY DEFERRED` constraints?

### Exercise 15. Choosing a Strategy

An e-commerce service uses `ON CONFLICT` to upsert coupon codes in most transactions. A rare admin job wants to swap two coupon codes through a temporary duplicate. Should you switch the existing unique constraint to deferrable right away? List factors to evaluate first.

### Suggested Answers

**Exercise 1:** `NOT DEFERRABLE` cannot be switched; both `DEFERRABLE` declarations can be switched. Only `INITIALLY DEFERRED` starts each transaction in deferred mode.

**Exercise 2:**

~~~sql
BEGIN;
SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

COMMIT;
~~~

**Exercise 3:** when deferred, PostgreSQL allows the temporary duplicate mid-transaction, but rejects the transaction at commit if duplicates remain.

**Exercise 4:** `SET CONSTRAINTS ... IMMEDIATE` performs retroactive validation and fails immediately if unresolved violations remain.

**Exercise 5:**

~~~sql
BEGIN;
SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES (4004, 40, 'Mai');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES (40, 'Operations');

COMMIT;
~~~

**Exercise 6:** `NO ACTION` is a check that can be deferred if the FK is deferrable and currently deferred; `RESTRICT` blocks parent deletes/updates while referencing rows exist per `RESTRICT` semantics.

**Exercise 7:** no. `NOT NULL` and `CHECK` are not deferred by `SET CONSTRAINTS`.

**Exercise 8:** `SET CONSTRAINTS` must run inside a transaction enclosing the related statements; autocommit runs each statement in its own separate transaction.

**Exercise 9:**

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

**Exercise 10:** PostgreSQL does not support deferrable unique constraints as `ON CONFLICT` arbiters. Another constraint or upsert design is needed.

**Exercise 11:**

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY DEFERRED;
~~~

Changing deferrability via `ALTER CONSTRAINT` does not apply generally to `UNIQUE`, `PRIMARY KEY`, or `EXCLUDE` constraints.

**Exercise 12:** no. MVCC and isolation still apply. Two transactions cannot both commit final states violating the same unique constraint.

**Exercise 13:** create both FKs as `DEFERRABLE INITIALLY DEFERRED`, insert both rows in one transaction, and commit. To enforce that the leader belongs to that exact team, add an appropriate composite constraint.

**Exercise 14:** constraint errors can be thrown by `commit()`, causing the app to misreport success or skip rollback and exception handling.

**Exercise 15:** do not switch it blindly. Evaluate the impact on `ON CONFLICT`, existing write paths, concurrency, swap techniques that avoid temporary duplicates, migration steps, and rollback options.

## 22. Pre-Production Checklist

| Category | Question to Answer |
| --- | --- |
| Constraint type | Is it `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `EXCLUDE`, or a constraint trigger? |
| Deferrability | Is `pg_constraint.condeferrable` actually `true`? |
| Default mode | Should it be `INITIALLY IMMEDIATE` or `INITIALLY DEFERRED`? |
| Transaction scope | Do all related operations run on the same connection in one transaction? |
| Early check | Should `SET CONSTRAINTS ... IMMEDIATE` run before expensive follow-on steps? |
| Referential action | Does the FK use `NO ACTION`, `RESTRICT`, or another action? |
| Final data | Is commit-time validity guaranteed by every code path? |
| UPSERT | Does any `ON CONFLICT` write path depend on this unique constraint? |
| Concurrency | Have multi-transaction races, deadlocks, and constraint failures been tested? |
| Exception handling | Does the app catch and handle errors on both statements and `COMMIT`? |
| Catalog | Have dependencies, constraint names, and attributes in `pg_constraint` been audited? |
| Operations | Are staging migration, backups, rollback, and lock/latency measurements ready? |

## 23. Quick Syntax Reference

| Goal | Syntax |
| --- | --- |
| Deferrable UNIQUE, checked immediately by default | `UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE` |
| Deferrable UNIQUE, deferred by default | `UNIQUE (code) DEFERRABLE INITIALLY DEFERRED` |
| Deferrable FK | `FOREIGN KEY (parent_id) REFERENCES parent(id) DEFERRABLE` |
| Defer a named constraint | `SET CONSTRAINTS schema.fk_name DEFERRED;` |
| Defer all eligible constraints | `SET CONSTRAINTS ALL DEFERRED;` |
| Immediately check deferred constraints | `SET CONSTRAINTS ALL IMMEDIATE;` |
| Change FK deferrability | `ALTER TABLE child ALTER CONSTRAINT fk_name DEFERRABLE INITIALLY DEFERRED;` |
| Inspect deferrability metadata | `SELECT conname, condeferrable, condeferred FROM pg_constraint;` |
| Finish valid transaction | `COMMIT;` |
| Abort test transaction | `ROLLBACK;` |

## 24. Summary

**`DEFERRABLE` controls whether deferral is allowed, `INITIALLY ...` sets the starting mode, and `SET CONSTRAINTS` switches modes inside the active transaction.** For supported constraint types, PostgreSQL can allow temporary violations between SQL statements, yet a transaction commits only if the data satisfies every constraint at check time.

Three points to remember:

1. **Not every constraint is deferrable.** `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, and `EXCLUDE` support it; `CHECK` and `NOT NULL` cannot be deferred via `SET CONSTRAINTS`.
2. **`NO ACTION` differs from `RESTRICT` in FK check timing.** When a workflow must temporarily adjust references across steps, that difference decides whether the design works.
3. **Applications must handle errors at `COMMIT`.** Every `UPDATE` or `INSERT` succeeding individually does not prove the final transaction state is valid.

Use deferrable constraints when **a workflow genuinely requires a temporary intermediate state** inside a short, controlled transaction with a valid final outcome. If a process routinely needs to defer almost every constraint, take that as a signal to revisit operation ordering, data modeling, or transaction boundaries before scaling the design further.
