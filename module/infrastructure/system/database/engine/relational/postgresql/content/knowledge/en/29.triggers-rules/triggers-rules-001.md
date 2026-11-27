# Distinguishing Triggers, Constraints, Default Values, and Application Logic in PostgreSQL

When designing a PostgreSQL table, you often encounter requirements that sound similar:

- If no order status is passed, automatically set it to `draft`.
- Do not allow a negative total amount.
- Do not allow an order to reference a non-existent customer.
- Automatically calculate the total after discount.
- When an order is modified, update `updated_at`.
- Do not allow a cancelled order to transition back to confirmed.
- Record change history for auditing.
- After an order is confirmed, send a notification to the buyer.
- Display a user-friendly message if the user enters invalid data.

You could try solving all of these with **triggers**. However, doing so easily creates a system that is hard to understand, slow, difficult to test, and unclear about where data is actually protected. Nor can you validate only in the **application**, because data may be written through another API, psql, batch imports, migrations, or multiple concurrent clients.

A sustainable approach is to **place each rule in the most appropriate mechanism**:

| Mechanism | Primary question | Example |
| --- | --- | --- |
| **`DEFAULT`** | When the writer omits a value, what should be filled in? | `status DEFAULT 'draft'` |
| **Constraints** (`NOT NULL`, `CHECK`, `UNIQUE`, `FK`, …) | Which data state must **never be allowed to exist**? | `discount <= subtotal` |
| **Generated column** | Which value is computed purely from columns in the same row? | `total = subtotal - discount` |
| **Trigger** | Before/after a DML event, what logic must run that depends on the operation, `OLD`/`NEW`, or recording a transactional side effect? | Write audit logs, block `cancelled -> confirmed` transition |
| **Application logic** | What should the UI, orchestration, and external integrations do? | Validation for friendly errors, calling payment gateways, sending emails |
| **Transaction/service** | How should multi-step writes maintain consistency and handle concurrency? | Create order + reserve inventory + outbox in a single transaction |

This lesson belongs to the **Triggers and Rules** chapter, module **Database Engine Relational PostgreSQL**. This is a self-contained document featuring a complete orders lab, verification queries, concurrency scenarios, exercises with answers, and a deployment checklist.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Choose properly among `DEFAULT`, `CHECK`, `UNIQUE`, `FOREIGN KEY`, generated columns, triggers, and application logic.
2. Understand when each mechanism is applied and what happens when data is invalid.
3. Write `BEFORE` and `AFTER` triggers on `INSERT`, `UPDATE`, and `DELETE`.
4. Distinguish row-level triggers (`FOR EACH ROW`) from statement-level triggers (`FOR EACH STATEMENT`).
5. Use `OLD`, `NEW`, `TG_OP`, and `RETURN NEW/OLD/NULL` in the right context.
6. Use triggers for rules that depend on the **before and after** state of a record.
7. Avoid using triggers instead of constraints when a constraint can express the rule directly.
8. Understand that changes made by a trigger belong to the **same transaction** and do not auto-commit.
9. Evaluate race conditions, row locking, deadlocks, and the limitations of triggers for multi-row rules.
10. Choose to emit external events via a transactional outbox rather than sending HTTP/email directly inside a trigger.
11. Distinguish defaults, generated columns, and application logic in terms of "who is the source of truth."
12. Inspect triggers, plan migrations, and test different write paths.

## 2. Decision Map Before Writing Code

A mental flowchart:

~~~mermaid
flowchart TD
    R["A new rule is needed"] --> Q{"Only needs a value when INSERT omits a field?"}
    Q -->|"Yes"| D["DEFAULT / IDENTITY"]
    Q -->|"No"| C{"Is it an invariant expressible with a constraint?"}
    C -->|"Yes"| K["NOT NULL / CHECK / UNIQUE / FK / EXCLUDE"]
    C -->|"No"| G{"Computed purely from columns in the same row?"}
    G -->|"Yes"| GC["Generated column or expression on SELECT"]
    G -->|"No"| T{"Depends on DML event, OLD/NEW, or needs transactional audit?"}
    T -->|"Yes"| TR["Consider a narrow-scoped trigger"]
    T -->|"No"| A["Application / service / transaction coordinator"]
    TR --> E{"Needs to call an external system after commit?"}
    E -->|"Yes"| O["Outbox in DB + post-commit worker"]
    E -->|"No"| X["Measure and test the trigger"]
~~~

This is a **priority guideline**, not a rigid decision tree. Some requirements require coordinating multiple layers: the application reports errors early, constraints still protect the data, triggers record audit logs, and services handle post-commit events.

**Core principle:** if a data invariant can be expressed with a declarative constraint, prefer the constraint over writing a trigger just to raise a similar error.

## 3. Four Mechanisms With Different Purposes

### 3.1. DEFAULT: a fallback value when input is missing

~~~sql
status text NOT NULL DEFAULT 'draft'
~~~

If an `INSERT` statement omits the `status` column or uses the `DEFAULT` keyword, PostgreSQL uses the default value. If the application explicitly passes `NULL`, `DEFAULT` does **not** automatically replace it with `draft`; `NOT NULL` may raise an error.

### 3.2. Constraint: an invariant that must be enforced

~~~sql
discount numeric(12,2) NOT NULL
    DEFAULT 0
    CHECK (discount >= 0)
~~~

`CHECK` prevents certain invalid data states regardless of whether the write comes from JDBC, psql, a background job, or another trigger.

### 3.3. Trigger: reacting to data events

~~~sql
CREATE TRIGGER ...
BEFORE UPDATE ON ...
FOR EACH ROW
EXECUTE FUNCTION ...;
~~~

A trigger has `OLD`/`NEW` context and knows the `INSERT`/`UPDATE`/`DELETE` operation. It can modify `NEW` in `BEFORE ROW`, insert an audit row in `AFTER ROW`, or block historical state transitions.

### 3.4. Application: orchestrating user experience and external systems

The application knows who the user is, which workflow the request belongs to, how errors should be presented, and when to call email/payment providers. A trigger running inside the database **does not inherently know the full request intent** and is not a good place to make slow network API calls or non-rollbackable calls.

## 4. "Checking in the Application" Does Not Replace Constraints

Suppose a Java API has:

~~~java
if (discount.compareTo(subtotal) > 0) {
    throw new IllegalArgumentException(
        "Discount cannot exceed subtotal"
    );
}
~~~

This is useful validation for returning immediate feedback, but another write path can still run:

~~~sql
UPDATE orders
SET discount = 1000
WHERE order_id = 1;
~~~

If the table has no constraint, PostgreSQL does not automatically know that rule.

Sensible layering:

- **Application**: catch errors early, messages in the user's language.
- **Database constraint**: guarantee invariants across all permitted write paths.
- **Service/transaction**: handle multi-table workflows, concurrency, and external systems.

Do not treat "app-only" or "DB-only" as mutually exclusive choices.

## 5. When Does DEFAULT Work?

Standalone example:

~~~sql
CREATE TEMP TABLE default_demo (
    id integer GENERATED ALWAYS AS IDENTITY,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

INSERT INTO default_demo DEFAULT VALUES;

INSERT INTO default_demo (status)
VALUES (DEFAULT);

SELECT id, status, created_at
FROM default_demo
ORDER BY id;
~~~

Both INSERTs receive the status `draft`.

### DEFAULT is not an UPDATE trigger

Afterwards:

~~~sql
UPDATE default_demo
SET status = 'confirmed'
WHERE id = 1;
~~~

`DEFAULT 'draft'` will never re-run automatically and overwrite `confirmed`. `DEFAULT` resolves a value at row insertion time or when the `DEFAULT` keyword is used explicitly, not as a lifecycle hook for every UPDATE.

### DEFAULT does not guarantee validity on its own

~~~sql
status text DEFAULT 'draft'
~~~

still allows the value `'unexpected'` if there is no constraint. To restrict the value domain, you need `CHECK`/enum/domain or an appropriate reference model.

## 6. Explicit NULL Differs From Omitting a Column

~~~sql
CREATE TEMP TABLE default_null_demo (
    id integer PRIMARY KEY,
    state text NOT NULL DEFAULT 'new'
);

-- Valid: omit state, receives DEFAULT.
INSERT INTO default_null_demo(id) VALUES (1);

-- INTENTIONAL ERROR: explicit NULL violates NOT NULL.
INSERT INTO default_null_demo(id, state)
VALUES (2, NULL);
~~~

The second statement will raise an error. If inside an explicit SQL transaction, the transaction enters an aborted state until rolled back according to PostgreSQL rules.

**Do not configure an application serializer to always send every field as null** and expect the database to apply DEFAULT automatically. To use DEFAULT, omit the column from INSERT or specify `DEFAULT` explicitly.

## 7. Common Types of DEFAULT

| Need | How to express it |
| --- | --- |
| Initial status | `status DEFAULT 'draft'` |
| Creation timestamp | `created_at DEFAULT transaction_timestamp()` |
| Auto-incrementing identifier | `GENERATED ... AS IDENTITY` |
| UUID ID (depending on version/setup) | Default calling an appropriate UUID function |
| Default configuration value | `language DEFAULT 'vi'` |
| Value depending on another column | Do **not** use DEFAULT directly referencing columns in the same row; see generated columns |
| Value auto-updated on every UPDATE | Does **not** happen automatically via DEFAULT; see trigger/app |

### DEFAULT can use time functions

~~~sql
created_at timestamptz NOT NULL
    DEFAULT transaction_timestamp()
~~~

`transaction_timestamp()` reflects the start time of the transaction. `statement_timestamp()` and `clock_timestamp()` have different semantics. Choose one consistent approach so the auditing system interprets timestamps accurately; do not assume all `now()`/`clock_timestamp()` functions behave identically inside long transactions.

### A default is not a historical rule

`status DEFAULT 'draft'` does not prevent `cancelled -> confirmed`. It only supplies an initial value when status is not passed.

## 8. Generated Columns Differ From DEFAULT

If a value is computed directly from columns in the same row:

~~~sql
subtotal numeric(12,2) NOT NULL,
discount numeric(12,2) NOT NULL DEFAULT 0,
total numeric(12,2)
    GENERATED ALWAYS AS (subtotal - discount) STORED
~~~

then `total` is not a value "only filled on INSERT"; it is a value computed from `subtotal` and `discount`.

### Differences

| Criterion | DEFAULT | Generated column |
| --- | --- | --- |
| When computed | When a default value is needed for INSERT or a DEFAULT operation | By the generated expression when the row is written |
| Can reference other columns in the same row? | Not in standard default expressions | Yes, within expression restrictions |
| Can an arbitrary value be entered for the column? | Yes, if constraints allow | `GENERATED ALWAYS` does not accept normal user-supplied values |
| Used for `updated_at` based on wall-clock time? | Does not run automatically on UPDATE | Generated expressions have immutability restrictions; not a solution for clock timestamps |
| Can be replaced by a SELECT expression? | Depends on needs | Can omit storing the column if only needed at read time |

Generated columns in PostgreSQL require expressions that satisfy immutability restrictions and only reference permitted data. **Do not use them to read other tables or execute arbitrary logic with side effects**.

## 9. Constraints: The Declarative Data Protection Layer

Common constraints:

| Constraint | Typical invariant |
| --- | --- |
| `NOT NULL` | Email/total amount cannot be NULL |
| `CHECK` | Discount is non-negative and not greater than subtotal |
| `UNIQUE` | No two normalized emails are identical |
| `PRIMARY KEY` | Has a unique, non-NULL identifier |
| `FOREIGN KEY` | An order must reference an existing customer |
| `EXCLUDE` | Prevents rows from overlapping under specified operator comparisons |
| `DEFERRABLE` on supported types | Defers certain checks until the end of the transaction |

A constraint is a promise that data must satisfy. PostgreSQL may use different internal mechanisms to enforce them, but **declarative intent** is still clearer than a hand-written trigger doing the same job.

## 10. CHECK Only Evaluates Row State and Requires Care With NULL

~~~sql
CREATE TEMP TABLE check_demo (
    id integer PRIMARY KEY,
    discount numeric CHECK (discount >= 0)
);
~~~

`CHECK (discount >= 0)` **does not automatically prevent NULL**: in SQL, `NULL >= 0` evaluates to UNKNOWN, and a CHECK generally passes as long as the condition is not FALSE.

To disallow NULL:

~~~sql
CREATE TEMP TABLE check_strict_demo (
    id integer PRIMARY KEY,
    discount numeric NOT NULL
        CHECK (discount >= 0)
);
~~~

### CHECK can combine multiple columns in the same row

~~~sql
CHECK (discount <= subtotal)
~~~

This is a single-row invariant, well-suited for CHECK. There is no need for a `BEFORE INSERT OR UPDATE` trigger just to perform the same comparison.

### CHECK is not suitable for inspecting data in other rows

A condition on the total amount across multiple orders or total inventory across multiple products **should not** be solved by having CHECK call a function that reads entire other tables. PostgreSQL does not re-evaluate CHECK against changes in other rows as a cross-table assertion and relies on expression immutability assumptions.

For multi-row rules, you must design appropriate constraints (UNIQUE/FK/EXCLUDE), transaction locking, or a different data model.

## 11. UNIQUE and PRIMARY KEY Are Stronger Than a Duplicate-Counting Trigger

A wrong way to prevent duplicate emails:

~~~text
BEFORE INSERT trigger:
  SELECT count(*) WHERE email = NEW.email
  IF count > 0 THEN RAISE EXCEPTION
~~~

Two transactions can both fail to see each other's email, and both pass the check.

**A UNIQUE index/constraint is enforced by PostgreSQL concurrently** under its internal mechanisms, making it far more suitable for uniqueness invariants.

Example:

~~~sql
CREATE TEMP TABLE unique_demo (
    id integer PRIMARY KEY,
    email text NOT NULL UNIQUE
);
~~~

There is no need to write a trigger "if SELECT doesn't find the email yet, allow INSERT" to replace UNIQUE.

### Multi-column uniqueness or active-row uniqueness only

You can have `UNIQUE (tenant_id, external_id)` or a **partial unique index** to restrict only non-soft-deleted rows:

~~~sql
-- Conceptual example, independent of the main lab:
CREATE UNIQUE INDEX ux_live_email
ON some_schema.users (tenant_id, lower(email))
WHERE deleted_at IS NULL;
~~~

This is illustrative syntax: the corresponding table/columns must exist for it to run. A partial unique index is not a regular UNIQUE constraint that can be made DEFERRABLE in the same way; understand its implications when choosing it.

## 12. FOREIGN KEY Is More Than a Simple Existence Check

~~~sql
customer_id bigint NOT NULL
    REFERENCES customers(customer_id)
~~~

A foreign key has semantics covering concurrency, parent row updates/deletes, and `ON DELETE`/`ON UPDATE` actions.

PostgreSQL implements many FK behaviors via internal triggers, but application authors should declare a **FOREIGN KEY** whenever the goal is referential integrity.

**Do not replace an FK with a trigger that SELECTs the parent before allowing INSERT**; hand-rolled designs are prone to race conditions and miss cascade, locking, or transactional edge cases.

### When is an FK not enough?

If you need "only allow orders for customers with state = active", an FK only guarantees the customer exists, not the `active` condition on the related row. That rule may require service-level transactions/locks or a different model. A trigger checking state must also handle concurrent updates on the customers table, not just run a SELECT.

## 13. Lab: Creating the Store Schema

The lab uses four tables:

- `customers`: customers and normalized emails.
- `orders`: orders, statuses, and amounts.
- `order_audit`: DML history for orders.
- `outbox`: committed events for an external worker to send notifications.

**Warning:** `DROP SCHEMA ... CASCADE` deletes all objects in the lab schema. Run this only in a **dedicated practice database**, never run this statement verbatim on production.

~~~sql
-- RUN ONLY ON A LAB DATABASE.
DROP SCHEMA IF EXISTS guardrail_lab CASCADE;
CREATE SCHEMA guardrail_lab;

CREATE TABLE guardrail_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL,
    normalized_email text
        GENERATED ALWAYS AS (lower(btrim(email))) STORED,
    full_name text NOT NULL,
    state text NOT NULL DEFAULT 'active'
        CHECK (state IN ('active', 'blocked')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    CONSTRAINT uq_customers_normalized_email
        UNIQUE (normalized_email)
);

CREATE TABLE guardrail_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES guardrail_lab.customers(customer_id)
        ON DELETE RESTRICT,
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'cancelled')),
    subtotal numeric(12,2) NOT NULL DEFAULT 0
        CHECK (subtotal >= 0),
    discount numeric(12,2) NOT NULL DEFAULT 0
        CHECK (discount >= 0),
    total numeric(12,2)
        GENERATED ALWAYS AS (subtotal - discount) STORED,
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    updated_at timestamptz NOT NULL
        DEFAULT transaction_timestamp(),
    CONSTRAINT chk_order_discount
        CHECK (discount <= subtotal),
    CONSTRAINT chk_confirmed_order_positive
        CHECK (status <> 'confirmed' OR subtotal > discount)
);

CREATE TABLE guardrail_lab.order_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    operation text NOT NULL
        CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    old_row jsonb,
    new_row jsonb,
    recorded_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    db_role name NOT NULL
        DEFAULT current_user
);

CREATE TABLE guardrail_lab.outbox (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    delivery_status text NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'processing', 'sent')),
    created_at timestamptz NOT NULL
        DEFAULT clock_timestamp()
);
~~~

### Why use each mechanism?

| Need | Mechanism in the lab |
| --- | --- |
| Customer has a normalized email | Generated `normalized_email` |
| No duplicate normalized emails | `UNIQUE (normalized_email)` |
| Initial customer state active | `DEFAULT 'active'` |
| Initial order status draft | `DEFAULT 'draft'` |
| No unknown status values | `CHECK status IN (...)` |
| No negative amounts / discount exceeding subtotal | `CHECK` combined with `NOT NULL` |
| Total = subtotal - discount | Generated `total` |
| Only orders with an existing customer | `FOREIGN KEY` |
| Update timestamp on modification | Trigger created later |
| Prevent forbidden reverse transitions | Trigger comparing `OLD.status`/`NEW.status` |
| Change history | AFTER trigger writing audit within the transaction |
| Send notification after commit | Trigger/outbox + application worker |

**`db_role = current_user` is the executing DB role**; it does not automatically guarantee the true end-user identity when multiple requests share a connection role. Production-grade auditing requires strict identity design and write permissions.

## 14. Inserting Seed Data

~~~sql
INSERT INTO guardrail_lab.customers (
    customer_id, email, full_name
)
VALUES
    (101, 'Lan@Example.Test', 'Lan'),
    (102, 'minh@example.test', 'Minh');

-- Temporarily create orders before installing the audit trigger.
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal, discount
)
VALUES
    (101, 'draft',     120.00, 20.00),
    (101, 'confirmed',  60.00,  0.00),
    (102, 'cancelled',  50.00, 10.00);

SELECT
    order_id,
    customer_id,
    status,
    subtotal,
    discount,
    total,
    created_at,
    updated_at
FROM guardrail_lab.orders
ORDER BY order_id;
~~~

After resetting the schema, identity will assign expected `order_id` values 1, 2, and 3. If you have already run multiple DML exercises with INSERTs, sequence numbers may jump and are not reused after rollback; in that case do not assume IDs are contiguous.

Business results:

| order_id | status | subtotal | discount | total |
| ---: | --- | ---: | ---: | ---: |
| 1 | draft | 120.00 | 20.00 | 100.00 |
| 2 | confirmed | 60.00 | 0.00 | 60.00 |
| 3 | cancelled | 50.00 | 10.00 | 40.00 |

### Querying to test defaults

~~~sql
BEGIN;

INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (101, 75.00)
RETURNING order_id, status, subtotal, discount, total;

ROLLBACK;
~~~

Inside the transaction, status is `draft`, discount is 0, and total is 75.00. This is **DEFAULT + generated column**, with no trigger needed.

## 15. Testing Constraints With Individual Statements

The examples below **intentionally cause errors**, so run each statement separately; after an error inside an explicit SQL transaction, you must roll back before running another example.

### Non-existent customer

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (999, 10.00);
~~~

Expected: `foreign_key_violation`, SQLSTATE `23503`.

### Discount exceeds subtotal

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal, discount
)
VALUES (101, 10.00, 50.00);
~~~

Expected: `check_violation`, SQLSTATE `23514`.

### Status outside the allowed set

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal
)
VALUES (101, 'delivered', 10.00);
~~~

Expected: `check_violation`, no trigger needed to check a simple list of values.

### Confirmed but total is not positive

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, status, subtotal, discount
)
VALUES (101, 'confirmed', 20.00, 20.00);
~~~

Expected: `chk_confirmed_order_positive` prevents the row from being saved. Because the rule only depends on columns of **the same row in its new state**, CHECK is more appropriate than a history trigger.

## 16. Triggers Only Become Necessary When Operation History Matters

The orders table has the constraint:

~~~sql
CHECK (status IN ('draft', 'confirmed', 'cancelled'))
~~~

This constraint allows three values, but does not know what the **previous value** was. Some state transition rules require `OLD` and `NEW`:

- `draft -> confirmed`: allowed if other CHECKs pass.
- `draft -> cancelled`: allowed.
- `confirmed -> cancelled`: allowed.
- `confirmed -> draft`: disallowed.
- `cancelled -> confirmed/draft`: disallowed.
- Keeping status unchanged while editing other fields: allowed if remaining constraints pass.

~~~mermaid
flowchart LR
    A["draft"] -->|"confirm"| B["confirmed"]
    A -->|"cancel"| C["cancelled"]
    B -->|"cancel"| C
    B -.->|"forbidden: back to draft"| A
    C -.->|"forbidden: reopen"| B
~~~

This is a **historical rule**, not just a single current value. A regular `CHECK` cannot access `OLD`. A `BEFORE UPDATE` trigger is an appropriate choice if all write paths must obey the state machine.

## 17. Writing a Trigger Function for Transitions

In PostgreSQL, a trigger invokes a **trigger function** with return type `trigger`:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.enforce_order_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF OLD.status = 'cancelled'
       AND NEW.status IS DISTINCT FROM OLD.status
    THEN
        RAISE EXCEPTION
            'Cancelled order % cannot change status from % to %',
            OLD.order_id, OLD.status, NEW.status
            USING ERRCODE = 'P2001';
    END IF;

    IF OLD.status = 'confirmed'
       AND NEW.status = 'draft'
    THEN
        RAISE EXCEPTION
            'Confirmed order % cannot return to draft',
            OLD.order_id
            USING ERRCODE = 'P2002';
    END IF;

    RETURN NEW;
END;
$fn$;
~~~

Attach it to the table:

~~~sql
CREATE TRIGGER trg_orders_10_transition
BEFORE UPDATE ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.enforce_order_transition();
~~~

### Why RETURN NEW?

For `BEFORE ... FOR EACH ROW`, the trigger function returns `NEW` so PostgreSQL proceeds with the operation on the record (which may have been modified). Returning `NULL` in BEFORE ROW instructs PostgreSQL to skip the operation for that row, a behavior that can surprise callers.

If the goal is to **reject invalid operations**, use an explicit `RAISE EXCEPTION` rather than silently returning `NULL` and causing `UPDATE 0`.

### Triggers do not replace CHECK

The function above **does not** check `discount <= subtotal` and does not enumerate all valid statuses. Those rules already have constraints. Separating responsibilities makes the code shorter, gives clearer error codes, and reduces duplication.

## 18. Which Events Have OLD and NEW?

| Trigger event | `OLD` | `NEW` |
| --- | --- | --- |
| Row-level `INSERT` | No old row | New row |
| Row-level `UPDATE` | Row before update | Row after update |
| Row-level `DELETE` | Row before delete | No new row |
| `TRUNCATE` | No per-row OLD/NEW | No per-row OLD/NEW |

`TG_OP` indicates the operation name, such as `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`.

Other context variables include `TG_TABLE_NAME`, `TG_TABLE_SCHEMA`, `TG_NAME`, `TG_WHEN`, `TG_LEVEL`, `TG_ARGV`, and `TG_NARGS`.

**Do not use `NEW` in a DELETE trigger or `OLD` in an INSERT trigger** expecting them to hold a meaningful row.

## 19. BEFORE, AFTER, and INSTEAD OF Differ

| Trigger type | Timing/primary use |
| --- | --- |
| `BEFORE ROW` | Validate/modify `NEW` before saving the row; can skip the row |
| `AFTER ROW` | React after the row operation, suited for transactional audit/side effects |
| `BEFORE STATEMENT` | Once before the DML statement, without per-row OLD/NEW |
| `AFTER STATEMENT` | Once after the DML statement, can use transition relations in supported contexts |
| `INSTEAD OF` | Usually on views to define how DML is handled instead of the default operation |

### Practical choices

- **Normalize values before writing:** you can use BEFORE ROW, though consider generated columns/DEFAULT if appropriate.
- **Write audit logs after the row has passed appropriate processing:** AFTER ROW.
- **Capture multi-row changes at once:** AFTER STATEMENT combined with transition tables if appropriate.
- **DML through complex views:** INSTEAD OF trigger when automatic updatable view mechanisms cannot be used.

There is no reason to make every trigger BEFORE. Execution timing changes the semantics and available data.

## 20. Trigger to Update updated_at on UPDATE

`DEFAULT transaction_timestamp()` only fills in the initial `updated_at`. It **does not re-run automatically on UPDATE**.

Create a BEFORE trigger:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.stamp_order_update()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW IS DISTINCT FROM OLD THEN
        NEW.updated_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_orders_20_stamp
BEFORE UPDATE ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.stamp_order_update();
~~~

### Why use the IS DISTINCT FROM condition?

If an update request does not actually change any fields, the trigger tries to avoid needlessly changing `updated_at`.

**Still, keep in mind:** an `UPDATE` that runs on a row may still create a new tuple version even when column values do not differ. Just because the trigger preserves the old timestamp **does not mean PostgreSQL skips the entire cost of the UPDATE**.

If the API receives many idempotent/no-op requests, you can add a `WHERE ... IS DISTINCT FROM ...` condition to avoid issuing an unnecessary UPDATE.

### Use clock_timestamp or transaction_timestamp?

- `transaction_timestamp()` produces the same timestamp throughout a transaction.
- `clock_timestamp()` reads the current wall-clock time at invocation, which may differ across rows.
- Pick one semantics and document it. There is no single right choice for every audit/system.

## 21. Trigger Names and Ordering Among the Same Type

In PostgreSQL, when multiple triggers of the **same timing and same event** exist on a table, their execution order generally follows **alphabetical order by trigger name**, not creation date.

In the lab we have:

~~~text
trg_orders_10_transition
trg_orders_20_stamp
~~~

This expresses the intent: check transitions first, then stamp the timestamp (both are BEFORE UPDATE ROW).

**Do not build overly complex business logic relying solely on naming conventions.** If two actions are tightly coupled, consider combining them into one function with explicit ordering; test behavior whenever adding new triggers or renaming them.

### BEFORE triggers can modify NEW

Another BEFORE trigger modifying `NEW.status` can alter the condition seen by subsequent triggers. Thus correctness depends not only on the initial `UPDATE SET status=...` statement, but also on the trigger pipeline.

## 22. Testing Status and Timestamp Updates

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1
RETURNING
    order_id,
    status,
    subtotal,
    discount,
    total,
    updated_at;

ROLLBACK;
~~~

Inside the transaction:

- `draft -> confirmed` is valid.
- CHECK ensures total > 0.
- The stamp trigger assigns a new `updated_at`.
- No state error occurs.
- `ROLLBACK` reverts both the change and the timestamp.

### Testing a forbidden transition

~~~sql
-- INTENTIONAL ERROR on the initial seed:
UPDATE guardrail_lab.orders
SET status = 'draft'
WHERE order_id = 2;
~~~

The trigger raises `P2002` because order 2 is already confirmed.

With explicit transactions, you must `ROLLBACK` after an erroneous SQL statement before continuing; do not try to run multiple examples inside an already aborted transaction.

## 23. Recording History With an AFTER ROW Trigger

The audit log needs to store:

- Order ID.
- Operation type.
- Row state **before** and **after**.
- Timestamp recorded.
- Executing database role.

Function:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.audit_order_change()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'INSERT', NULL, to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            NEW.order_id, 'UPDATE',
            to_jsonb(OLD), to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO guardrail_lab.order_audit (
            order_id, operation, old_row, new_row
        )
        VALUES (
            OLD.order_id, 'DELETE',
            to_jsonb(OLD), NULL
        );

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$fn$;

CREATE TRIGGER trg_orders_90_audit
AFTER INSERT OR UPDATE OR DELETE
ON guardrail_lab.orders
FOR EACH ROW
EXECUTE FUNCTION guardrail_lab.audit_order_change();
~~~

### Why AFTER?

We want to audit the final state of the row after BEFORE triggers and the DML step. For an AFTER ROW trigger, the return value from the trigger function **is ignored by PostgreSQL** regarding whether the row is written. Returning `NEW`/`OLD` in the function is readable, but **does not carry row-modification semantics** like BEFORE ROW.

### An audit trigger does not protect the audit table by itself

For trustworthy auditing:

- Restrict UPDATE/DELETE privileges on `order_audit`.
- Control table ownership, migration roles, and trigger-disabling permissions.
- Plan retention, partitioning/archival as audit data grows.
- Do not rely on `current_user` as unforgeable proof of end-user identity.
- Evaluate compliance requirements if an independent immutable/tamper-evident audit trail is needed.

An audit trigger is a **transactional observation mechanism**, not a complete tamper-resistant auditing system by itself.

## 24. The Audit Trigger Also Belongs to the Same SQL Transaction

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET discount = 25.00
WHERE order_id = 1;

SELECT
    audit_id,
    order_id,
    operation,
    old_row ->> 'discount' AS old_discount,
    new_row ->> 'discount' AS new_discount
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Inside the transaction, the audit row for the UPDATE is visible. After `ROLLBACK`, both the order change and the new audit row are discarded.

**There is no automatic autonomous commit** for AFTER triggers. If a transaction is rolled back, audit rows written in that transaction are also rolled back.

This is why requirements must be separated:

- Auditing **committed changes**: a same-transaction trigger is usually appropriate.
- Recording **every failed or rolled-back attempt**: requires application-side logging/observability or a separate channel with clear semantics.

## 25. What Happens If a Trigger Fails?

Suppose an AFTER audit trigger INSERT into the audit table hits a constraint error. If the error is not handled by a valid mechanism, the original statement fails.

Conceptual flow:

~~~text
UPDATE orders
  -> BEFORE transition passes
  -> UPDATE row
  -> AFTER audit INSERT fails
  -> SQL statement fails
  -> changes from the statement are rolled back
~~~

Inside an explicit transaction, an error puts the transaction into a failed state until rolled back or handled via a savepoint/subtransaction context.

This is sometimes desirable because the goal is **"no order update without an audit record"**. However, it can also create unintended operational coupling: a full audit table causes every order UPDATE to fail.

**You must decide clearly whether auditing is mandatory or best-effort.** Do not swallow audit errors in a trigger with `WHEN OTHERS THEN NULL` if requirements demand audit integrity.

## 26. An AFTER Trigger Cannot "Modify NEW" to Change the Row

Misguided approach:

~~~sql
CREATE FUNCTION ... RETURNS trigger AS $fn$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$fn$ LANGUAGE plpgsql;

-- If this function is attached AFTER UPDATE,
-- modifying NEW does not automatically change the already-written row version.
~~~

To modify the contents of the row being written, use a **BEFORE ROW** trigger or an appropriate declarative mechanism.

To create transactional side effects after the change succeeds, use **AFTER**.

### Why not UPDATE the same table immediately in an AFTER trigger?

An AFTER UPDATE trigger executing `UPDATE orders SET ... WHERE order_id = NEW.order_id` can trigger **a new round of UPDATE triggers**, causing recursion, wasted work, or errors. To stamp a timestamp on the same row, modifying `NEW` in BEFORE ROW is generally much simpler.

## 27. What Does RETURN NULL Mean in BEFORE ROW?

~~~sql
CREATE FUNCTION guardrail_lab.skip_some_rows()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.subtotal = 0 THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$fn$;
~~~

If attached to `BEFORE INSERT FOR EACH ROW`, returning `NULL` instructs PostgreSQL to **skip the operation for that row**. Subsequent row triggers for the skipped row may not run under trigger semantics.

This is a very sensitive choice:

- The caller may think an INSERT succeeded when no row was actually inserted.
- `RETURNING` and affected row counts may be lower than expected.
- Invalid data may be silently skipped instead of raising an error.

**If the rule is "disallow subtotal = 0", use CHECK; if it is "disallow state transition", use an explicit RAISE EXCEPTION.** RETURN NULL is only appropriate when skipping rows is an intentionally designed business behavior.

## 28. Row-Level and Statement-Level Triggers

A statement:

~~~sql
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE status = 'draft';
~~~

may update multiple rows.

| Type | Invocation count |
| --- | --- |
| `FOR EACH ROW` | Once per affected row |
| `FOR EACH STATEMENT` | Once for the entire statement, even if the statement modifies zero rows in many cases |

Row-level is suitable when you need `OLD`/`NEW` for each individual row. Statement-level is suitable when you need aggregate logic or to record a single event for the entire statement.

### Statement triggers and transition tables

PostgreSQL supports **transition relations** for certain AFTER triggers, allowing access to the set of OLD/NEW rows for the statement.

Conceptual example:

~~~sql
CREATE TRIGGER trg_orders_bulk_audit
AFTER UPDATE ON guardrail_lab.orders
REFERENCING
    OLD TABLE AS old_orders
    NEW TABLE AS new_orders
FOR EACH STATEMENT
EXECUTE FUNCTION guardrail_lab.some_statement_trigger();
~~~

This statement **illustrates syntax** and cannot run standalone because `some_statement_trigger` has not been created. Transition tables have specific syntax, event, and table-type restrictions; they cannot be combined arbitrarily with every trigger mode or `UPDATE OF ...`.

### Choosing row or statement?

- Need to modify `NEW.updated_at` per row -> BEFORE ROW.
- Need to audit each row's state -> AFTER ROW.
- Need to process a large batch as a set of rows -> consider AFTER STATEMENT with transition tables.
- Need general DML counting -> a statement trigger may fit, though avoid inserting many rows or rescanning the whole table unnecessarily.

## 29. ON CONFLICT and Triggers Need Separate Understanding

An application might use:

~~~sql
INSERT INTO guardrail_lab.orders (
    customer_id, subtotal
)
VALUES (101, 20.00);
~~~

However, upserts commonly use `INSERT ... ON CONFLICT ... DO UPDATE` on a table with a suitable unique key.

**Do not assume a single SQL statement fires only one type of trigger event.** With `INSERT ... ON CONFLICT DO UPDATE`, PostgreSQL has specific rules for firing INSERT/UPDATE triggers depending on whether a conflict occurs and the trigger type. Certain BEFORE INSERT triggers may run before the conflict branch is determined; results from BEFORE triggers can affect the data processed in the UPDATE branch.

### Consequences

- Avoid triggers with surprising or non-idempotent side effects.
- Test all branches: INSERT, conflict DO NOTHING, and conflict DO UPDATE.
- Do not rely solely on the SQL verb "INSERT" to deduce that no UPDATE triggers will fire.
- For auditing, ensure you know which DML actually occurred so you record the right operation.

If the goal is simply handling normal key duplicates, **UNIQUE + ON CONFLICT** is usually better than a trigger running SELECT to check whether a key already exists.

## 30. Locks, Concurrency, and Trigger Limitations

Triggers run within the same transaction, but **having a trigger does not automatically make multi-row rules concurrency-safe**.

Wrong example:

~~~text
Trigger BEFORE INSERT orders:
  SELECT count(*) FROM orders WHERE customer_id = NEW.customer_id;
  IF count >= 5 THEN reject;
~~~

Two transactions can both observe 4 existing orders and both INSERT, resulting in 6 orders if there is no proper synchronization mechanism.

### How to handle multi-row rules

- If expressible with UNIQUE/FK/EXCLUDE, prefer the corresponding constraint/index.
- For quotas, consider a **counter row** locked/updated atomically or an appropriate reservation design.
- Use `SELECT ... FOR UPDATE` on a coordinating row when the transaction needs to hold a stable lock.
- Consider `SERIALIZABLE` isolation and full-transaction retry logic where appropriate.
- Design a consistent lock acquisition order to reduce deadlocks.
- Do not simply add a SELECT inside a trigger and assume race conditions disappear.

### Triggers using OLD/NEW on the same row

The transition rule in the lab compares `OLD.status`/`NEW.status` of the very row being updated. PostgreSQL coordinates row locking and row versions during UPDATE according to isolation semantics, making this far more suitable than a trigger reading and counting multiple rows elsewhere.

Under `REPEATABLE READ`/`SERIALIZABLE`, transactions may encounter `40001`; the application must retry properly rather than swallowing the error or assuming success.

## 31. Application Logic Still Needs to Exist

For example, when a user submits a request to confirm an order:

1. Authenticate identity and check authorization.
2. Validate cart details / payment gateway state.
3. Validate form inputs to return user-friendly errors.
4. Start a transaction.
5. Execute SQL statements updating data and the outbox.
6. Commit; return status according to the API contract.
7. Worker processes email / payment webhooks once the event is committed.

Database constraints and triggers protect data, but **cannot replace the entire workflow communicating with users and external systems**.

### Do not expect triggers to make HTTP calls

A trigger that sends HTTP/email immediately when an order updates carries many risks:

- The external request may succeed while the DB transaction later rolls back.
- Network timeouts hold row locks/transactions open too long.
- Trigger re-executions may cause duplicate sends.
- Transaction retries may produce multiple sends.
- Difficult to manage timeouts, circuit breakers, and observability.
- Introduces network access privileges and security risks from the database.

Use a **transactional outbox** when you need to tie DB events to post-commit processing.

## 32. Transactional Outbox: Record the Intent to Send, Not Immediate Delivery

The `guardrail_lab.outbox` table was created in the lab. When an order transitions to confirmed, we want a pending event.

Function:

~~~sql
CREATE OR REPLACE FUNCTION guardrail_lab.queue_order_confirmed()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    INSERT INTO guardrail_lab.outbox (
        event_key,
        event_type,
        payload
    )
    VALUES (
        'order-confirmed-' || NEW.order_id::text,
        'order.confirmed',
        jsonb_build_object(
            'order_id', NEW.order_id,
            'customer_id', NEW.customer_id,
            'total', NEW.total
        )
    )
    ON CONFLICT (event_key) DO NOTHING;

    RETURN NEW;
END;
$fn$;

CREATE TRIGGER trg_orders_80_outbox
AFTER UPDATE ON guardrail_lab.orders
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'confirmed'
)
EXECUTE FUNCTION guardrail_lab.queue_order_confirmed();
~~~

### Why is WHEN placed on CREATE TRIGGER?

The condition filters for UPDATEs that change status to `confirmed`. UPDATEs that only change discount or updated_at while status remains confirmed do not emit a new event.

### Why ON CONFLICT?

`event_key` is unique, illustrating idempotency for a "first-time order confirmation" event type. Each domain must choose an appropriate event identity. If re-confirming after cancellation were allowed, a key based solely on order_id would **not be enough** to distinguish separate confirmations; a version/event ID would be needed.

### Outbox does not send emails by itself

An external worker looks for committed events with `delivery_status='pending'`, performs delivery, and updates status under a protocol with retry/idempotency.

**An outbox typically provides the foundation for at-least-once delivery, not automatically exactly-once email delivery.** Consumers/providers need mechanisms to avoid duplicate processing.

## 33. Testing Outbox Within the Same Transaction

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1
RETURNING order_id, status, total;

SELECT
    event_key,
    event_type,
    payload,
    delivery_status
FROM guardrail_lab.outbox
ORDER BY event_id;

SELECT
    operation,
    old_row ->> 'status' AS old_status,
    new_row ->> 'status' AS new_status
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Inside the transaction:

- Order 1 changes draft -> confirmed.
- Audit has an UPDATE row.
- Outbox has a pending `order.confirmed` event.
- All three belong to the same transaction.

After `ROLLBACK`, the status change, new audit row, and pending event are all discarded. An external worker on another connection never sees uncommitted outbox rows under standard transaction isolation.

### Do not send an email in a trigger hoping ROLLBACK will "unsend the email"

An email already sent cannot be rolled back by SQL. Only the **intent to send** is recorded transactionally; the worker sends after commit succeeds.

## 34. Why Might You Write to the Outbox in the Service Instead of a Trigger?

The outbox does not have to be populated by a trigger.

**Service transaction approach:**

~~~text
BEGIN
  UPDATE orders SET status = 'confirmed' ...
  INSERT INTO outbox (...)
COMMIT
~~~

**Trigger approach:**

~~~text
BEGIN
  UPDATE orders SET status = 'confirmed' ...
  AFTER UPDATE trigger writes to outbox
COMMIT
~~~

| Factor | Service writes outbox | Trigger writes outbox |
| --- | --- | --- |
| Business intent visible in service code | Usually high | Can be hidden inside the DB |
| Coverage across multiple DB write paths | Requires all write paths to follow the workflow | Trigger covers relevant DML while active |
| Visibility during code review | Usually easy | Requires inspecting schema/trigger functions as well |
| Risk of accidentally emitting events from migrations/batches | Service controls explicitly | Trigger may fire during batch updates |
| Ties DB state and event in same transaction | Yes, if in the same transaction | Yes, because the trigger runs in the same transaction |
| Fits every system | No | No |

**Design recommendation:** if an event must be emitted for every state change regardless of write path, a trigger can be useful. If the event is tightly coupled to a specific business action, an explicit service transaction can be easier to maintain. Whichever you choose, tests and idempotency are required.

## 35. App Logic Cannot Guarantee a Cross-Request Constraint Alone

Example of an API checking duplicate emails manually:

~~~text
Request A: SELECT email -> not found
Request B: SELECT email -> not found
Request A: INSERT email
Request B: INSERT email
~~~

Without UNIQUE, both may succeed.

With UNIQUE(normalized_email):

- Only one INSERT is accepted for the same normalized value.
- The other request receives an appropriate error, such as SQLSTATE `23505`.
- The service can map it to HTTP `409 Conflict` (depending on the API contract).

### Do not predict exclusively from a SELECT query

A pre-check can still improve UX, but **the constraint is the final source of enforcement**. The service must handle constraint errors when a race occurs.

Nor should you catch every 23505 error and assume it means a duplicate email: a transaction could violate a UNIQUE constraint on another column or table. Controlled inspection of the constraint name may be necessary.

## 36. Triggers Do Not Automatically Create Unbreakable Data Invariants

A custom trigger can:

- Be altered or disabled by a role with sufficient privileges.
- Not fire under certain replication modes or special operational configurations.
- Be flawed if its logic uses unlocked SELECTs.
- Fire on one event while missing another event.
- Incur overhead and side effects during batch data imports.

Meanwhile, declarative constraints express rules directly and are usually more visible in catalog/schema diffs.

### Security and deployment permissions

If your threat model includes someone with superuser/owner privileges modifying the schema, no constraint or trigger in the same database is an "untouchable invariant" against them. You need privilege governance, independent auditing, backups, and production change-control processes.

Do not use triggers as a substitute for proper authorization.

## 37. Row-Level Security and Access Privileges Differ From Triggers

RLS serves a different purpose:

- Restricts which rows a DB role can `SELECT/INSERT/UPDATE/DELETE`.
- Should not be replaced solely with triggers.
- Should not be replaced solely with application filters if the system relies on DB-level isolation.

Conceptual example:

~~~sql
ALTER TABLE some_schema.tenant_orders
ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_policy
ON some_schema.tenant_orders
USING (tenant_id = current_setting('app.tenant_id')::bigint)
WITH CHECK (tenant_id = current_setting('app.tenant_id')::bigint);
~~~

This is **illustrative** and does not run directly because the table has not been created and requires a secure tenant-context policy. Values from `current_setting` set by a session are not automatically trustworthy in every trust model; letting a caller set an arbitrary tenant ID can break isolation.

RLS also has bypass conditions for table owners and special roles depending on configuration. Therefore, test using the **actual application role**, not just a superuser.

### Quick distinction

- Constraint: is the data valid?
- RLS/privileges: who can view or modify which rows?
- Trigger: how to react to write events?
- Application: which workflows is the caller actually allowed to execute?

## 38. Triggers and Rules (CREATE RULE) Are Different

This chapter is titled **"Triggers and Rules"**; in PostgreSQL, `CREATE RULE` is a separate **query rewrite** mechanism, not identical to triggers.

| Criterion | Trigger | Rule |
| --- | --- | --- |
| Phase | Bound to DML event execution | Bound to query rewrite |
| Has `OLD`/`NEW` per trigger function | Yes, in row triggers | Uses pseudo-relations under different rule mechanics |
| Suitable for per-row auditing | Usually yes | Usually not the preferred choice |
| Can modify row contents BEFORE write | Yes | Not the same mechanism |
| Used for views | `INSTEAD OF` triggers can be suitable | Rules can participate in updatable views/rewrites |
| Easy to reason about for everyday business logic | Usually clearer | Rewrite semantics can be surprising |

`CREATE RULE` is not a "constraint rule" intended to replace general validation logic. Rules have complex interactions with multi-row queries, RETURNING, and side effects; PostgreSQL generally encourages considering triggers first for most row-reactive business needs.

**Do not use a rewrite rule to simulate a constraint or audit trigger without a verified reason.**

## 39. BEFORE Triggers and Generated Columns Relate to Evaluation Timing

In the lab:

~~~sql
total numeric(12,2)
    GENERATED ALWAYS AS (subtotal - discount) STORED
~~~

If a BEFORE trigger alters `NEW.subtotal` or `NEW.discount`, the generated column is computed from the input data that passed through the appropriate pipeline steps. Do not try to access or assign a stored generated column inside a BEFORE trigger as if it were a normal column to customize it arbitrarily.

### Is a manual trigger to compute total needed?

No:

~~~text
BEFORE INSERT OR UPDATE:
  NEW.total := NEW.subtotal - NEW.discount
~~~

duplicates generated column logic when the expression is purely a formula over columns in the same row.

A generated column clearly declares the origin of the value and avoids having to ensure triggers are attached to every right event and not forgotten when adding new write paths.

### When not to use a generated column?

If total depends on shipping fees from another system, historical pricing, multi-table data, or time-varying events, the formula is no longer purely immutable from columns in the same row. In that case, design a proper domain model, snapshot prices at transaction time, and use transaction logic rather than forcing an inappropriate generated expression.

## 40. Historical Constraints Differ From Current-State Invariants

In orders there are two kinds of rules:

**Current-state invariant:**

~~~sql
CHECK (
    status <> 'confirmed'
    OR subtotal > discount
)
~~~

Regardless of how the row arrived at this state, if it is confirmed then the total must be positive.

**State-transition invariant:**

~~~text
OLD.status = cancelled
NEW.status = confirmed
=> forbidden
~~~

Checking the second rule requires knowing **OLD/NEW** of the operation, hence a trigger or a service transition method with equivalent protection.

### Are both needed?

Possibly. A trigger blocking invalid transitions does not mean all financial fields are validated; CHECK prevents an invalid final state even if a trigger misses a branch.

Conversely, CHECK cannot forbid confirmed -> draft on its own because draft is a valid value when inspecting only the current row.

## 41. Deferrable Constraints and Constraint Triggers

Some constraints can be `DEFERRABLE`, allowing checks to be postponed until an appropriate point in the transaction:

~~~sql
-- Conceptual FK example:
CONSTRAINT fk_order_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
DEFERRABLE INITIALLY DEFERRED
~~~

However:

- PostgreSQL does not allow every constraint (such as regular CHECK/NOT NULL) to be made DEFERRABLE in the same way.
- Unique, primary key, exclusion, and foreign key constraints have their own deferral capabilities and limitations.
- `SET CONSTRAINTS ...` affects eligible constraints and depends on mode.

PostgreSQL also provides `AFTER ROW` **constraint triggers** that can be declared `DEFERRABLE` according to rules:

~~~sql
CREATE CONSTRAINT TRIGGER constraint_name
AFTER INSERT OR UPDATE ON some_schema.some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_schema.some_trigger_function();
~~~

This is a syntax example and cannot run unless the corresponding objects are created. **Do not infer from this that any BEFORE/AFTER trigger can be deferred.**

### When to consider it?

When a rule should only be checked after a set of changes within a transaction, evaluate whether a deferrable FK/UNIQUE/EXCLUDE expresses it more accurately. Custom constraint triggers require deep understanding of semantics and concurrency and are not the default choice.

## 42. Triggers and Bulk Operations

Statement:

~~~sql
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE status = 'draft';
~~~

can fire:

- BEFORE UPDATE ROW for each row.
- AFTER UPDATE ROW for each row.
- Statement-level triggers for the event.
- Index/constraint checks and attached audit/outbox logic.

### Things to account for

- If 100,000 rows are updated, row-level auditing may generate nearly 100,000 audit entries.
- If a trigger runs a complex SELECT query per row, it can turn into an N+1 query pattern.
- If the UPDATE causes multiple sessions to hold locks concurrently, latency and deadlock risk rise.
- A statement error caused by a single row violating a constraint can fail the entire statement; do not assume "99,999 rows succeeded."

**Do not benchmark a trigger on a single-row UPDATE and claim a 100,000-row batch will be cheap.** For heavy workloads, investigate statement-level transition tables, batching/partitioning, queues, and reducing repeated queries.

## 43. COPY and Other Write Paths

Write paths into PostgreSQL include:

- JDBC prepared statements.
- psql or pgAdmin.
- Batch ETL.
- `COPY FROM`.
- Other services in the system.
- Stored procedures.
- Migration scripts.
- Replication/apply processes with their own rules.

An `INSERT` trigger can fire when data is imported via `COPY FROM` under PostgreSQL trigger rules, not just through the UI.

However, you should not claim that **every write path always runs every trigger identically** regardless of replication mode, disabled triggers, or special permissions.

### Especially with logical replication

Replication apply has trigger-firing modes that differ from normal client execution; `ENABLE REPLICA TRIGGER`/`ENABLE ALWAYS TRIGGER` and related settings can alter behavior. When using logical replication, verify exact triggers, constraints, and generated columns on both publisher and subscriber.

**Triggers are not absolute proof that data imported from every source ran through the same business workflow.**

## 44. Do Not Accidentally Create Recursion

An AFTER UPDATE trigger containing:

~~~sql
UPDATE guardrail_lab.orders
SET updated_at = clock_timestamp()
WHERE order_id = NEW.order_id;
~~~

can update the same row again, firing a new UPDATE trigger and looping.

Therefore:

- Stamp the same row using **BEFORE ROW** modifying `NEW`.
- Avoid updating the same table from an AFTER trigger unless an explicit recursion-prevention mechanism is designed.
- Do not rely on `pg_trigger_depth()` as a "silver bullet" to patch flawed designs; it only helps inspect nesting depth, has limits, and does not replace sound transaction logic.
- For auditing, writing to a separate table is less likely to cause recursion, though triggers on that audit table must still be controlled.

## 45. Triggers and Locks: Logic Can Be Slow Even for Simple UPDATEs

An UPDATE statement can incur:

1. Cost of locating rows via index/scan.
2. Cost of tuple/transaction locking.
3. Cost of invoking multiple trigger functions.
4. Cost of auxiliary queries inside triggers.
5. Cost of constraint checks and index maintenance.
6. Cost of WAL, dirty buffers, and subsequent vacuuming.
7. Contention cost when multiple sessions write concurrently.

When a trigger executes 3 extra SQL queries per row, a 10,000-row batch can multiply work significantly compared to a set-based expression.

### What should a trigger function do?

- Keep side effects minimal and scope clear.
- Make no network calls.
- Avoid scanning entire tables per row whenever possible.
- Do not depend on uncontrolled session state.
- Do not raise vague errors.
- Do not duplicate validations already covered by CHECK/UNIQUE/FK.

Measure with realistic workloads before optimizing or relocating logic elsewhere.

## 46. Transaction Boundaries and Rollback

A combined example:

~~~sql
BEGIN;

UPDATE guardrail_lab.orders
SET status = 'confirmed'
WHERE order_id = 1;

SELECT *
FROM guardrail_lab.outbox
ORDER BY event_id;

SELECT *
FROM guardrail_lab.order_audit
WHERE order_id = 1
ORDER BY audit_id;

ROLLBACK;
~~~

Even though the triggers executed and inserted into audit/outbox, **ROLLBACK** removes all changes within the transaction.

### What if the client loses connection after COMMIT?

Situations can occur where the client does not know whether commit succeeded. This is why critical business operations need an **idempotency key** and a status-query mechanism rather than relying solely on "whether the client saw an exception."

Triggers do not solve this distributed-systems problem on their own.

## 47. Trigger Errors Should Have a SQLSTATE/Error Contract

The lab uses:

- `P2001`: cancelled order cannot change status.
- `P2002`: confirmed cannot return to draft.

The codes `P2001`/`P2002` are example **application-chosen codes**, not universal defaults across every PostgreSQL deployment.

Standard constraint errors:

| Error | SQLSTATE |
| --- | --- |
| `unique_violation` | `23505` |
| `foreign_key_violation` | `23503` |
| `check_violation` | `23514` |
| `not_null_violation` | `23502` |
| `serialization_failure` | `40001` |
| `deadlock_detected` | `40P01` |

The application should map errors **by known categories** into structured API responses. Do not expose raw SQL statements or internal schema details if that information could be sensitive.

### Why not use message text as the error identifier?

Messages can change due to localization, PostgreSQL versions, or wording adjustments. `SQLSTATE` and constraint names (when reliable) are more stable for classification.

## 48. JDBC: Catching Constraint Errors at the Right Layer

Illustrative Java example:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public static void createDraftOrder(
        Connection connection,
        long customerId,
        java.math.BigDecimal subtotal
) throws SQLException {

    String sql = """
        INSERT INTO guardrail_lab.orders (customer_id, subtotal)
        VALUES (?, ?)
        """;

    try (PreparedStatement ps =
             connection.prepareStatement(sql)) {

        ps.setLong(1, customerId);
        ps.setBigDecimal(2, subtotal);
        ps.executeUpdate();

    } catch (SQLException ex) {
        switch (ex.getSQLState()) {
            case "23503" ->
                throw new IllegalArgumentException(
                    "Customer does not exist", ex);
            case "23514" ->
                throw new IllegalArgumentException(
                    "Invalid order amounts", ex);
            default ->
                throw ex;
        }
    }
}
~~~

### Operational notes

- `SQLException.getSQLState()` returns the SQLSTATE provided by the JDBC driver; handle `null` or chained exception forms if using specialized drivers.
- The example uses Java switch arrow syntax; older Java projects require equivalent syntax.
- Inside a failed transaction, the caller must manage rollback/savepoints according to transaction semantics. **Catching a Java exception does not make a failed transaction valid again.**
- Client-side validation messages can be more detailed than database errors, while constraints remain the protective layer.
- Do not convert every SQL error into HTTP 400; operational or connectivity errors must be handled differently.

## 49. When to Use a Service Transaction Instead of a Trigger?

For an order with a complex workflow:

~~~text
validate request
authorize user
get inventory/pricing snapshot
BEGIN
  reserve inventory
  create/update order
  write order event/outbox
COMMIT
return response
async worker sends notification
~~~

When logic depends on objects from multiple services, retry policies, and external coordination, a **service transaction** can be clearer than triggers.

You still need:

- FK/UNIQUE/CHECK in PostgreSQL.
- Appropriate DB transactions and row locks.
- RLS/privileges where applicable.
- Testing across all write paths.
- An outbox for post-commit side effects.

**Do not replace constraints with services**, and do not cram an entire service into a trigger just so "everything is automatic."

## 50. Design Decision Comparison Table

| Requirement | Preferred choice | Why | Avoid by default |
| --- | --- | --- | --- |
| Initial status is draft | DEFAULT | Handles omitted field on INSERT | BEFORE trigger |
| Disallow statuses outside enum | CHECK/enum/domain | Data invariant | Trigger checking an IN list |
| Disallow negative discount | NOT NULL + CHECK | Single-row invariant | App-only validation |
| Disallow duplicate emails | UNIQUE/unique index | Handles concurrency properly | Trigger with SELECT COUNT |
| Order must have a customer | FOREIGN KEY | Referential integrity | Trigger selecting parent |
| total = subtotal - discount | Generated column or SELECT expression | Purely computed on same row | Trigger manually assigning total |
| updated_at changes on UPDATE | BEFORE ROW trigger or controlled service | DEFAULT does not do this | Generated column using clock |
| Block cancelled -> confirmed | BEFORE UPDATE trigger or DB-protected state-transition service | Requires OLD/NEW | CHECK status IN |
| Audit committed changes | AFTER ROW trigger or explicit service write in same transaction | Driven by DML events | DEFAULT |
| Email after confirmation | Outbox + worker | Waits for commit, supports retry | HTTP inside trigger |
| Display friendly errors | Application | UX/localization | RAISE NOTICE as UI |
| Tenant/user authorization | Privileges/RLS + app policy | Access control | CHECK or triggers alone |
| Multi-row quota | Constraint/counter model/lock/transaction | Needs concurrency control | Unlocked trigger SELECT COUNT |
| DML through complex view | INSTEAD OF trigger when appropriate | Maps DML through view | Writing directly to arbitrary views |

**Order of thinking:** DEFAULT to fill values, generated columns to derive values, constraints to protect invariants, triggers for events/history, and app/service for orchestration and user-facing behavior.

## 51. Changing Schemas and Migrating Logic With Existing Data

Adding a new constraint on a production table is not just writing SQL. If existing data already violates it, DDL may fail.

A typical plan includes:

1. Inspect existing data.
2. Fix or decide policy for invalid cases.
3. Add the constraint using an appropriate mechanism, possibly `NOT VALID` for supported constraint types.
4. Check/`VALIDATE CONSTRAINT` according to version and constraint type rules.
5. Deploy application code compatible with the new schema.
6. Monitor errors/latency.
7. Clean up duplicate trigger/app code after verification.

### NOT VALID does not apply to every constraint type

For example, CHECK/FK have `NOT VALID` mechanisms; do not assume UNIQUE/PK can be added with `NOT VALID` identically to CHECK. Check the `ALTER TABLE` documentation for your major version.

### Adding a trigger to a table with existing data

Triggers apply to events **after creation** and do not automatically run once across all historical rows. If you need audit/backfill or outbox creation for existing state, you need a clear migration/backfill plan to avoid sending unintended mass emails.

## 52. When Modifying a Trigger Function

`CREATE OR REPLACE FUNCTION` replaces the function body, which does not mean you have tested every table calling that function.

Before making changes:

- List which triggers depend on the function.
- Check permissions, `search_path`, and SQLSTATE codes.
- Verify logic with OLD/NEW across every event.
- Test batch DML, rollback, and concurrency.
- Have a deployment and backward-compatibility plan.
- Check effects on replication/apply jobs.
- Never silently change trigger semantics without notifying services that rely on it.

A trigger function may be shared by multiple tables; a function written for specific column names must not be attached arbitrarily to other tables.

## 53. Inspecting Triggers in System Catalogs

List user-defined triggers on the orders table:

~~~sql
SELECT
    tgname AS trigger_name,
    tgenabled,
    pg_get_triggerdef(oid) AS definition
FROM pg_trigger
WHERE tgrelid = 'guardrail_lab.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Columns:

- `tgname`: trigger name.
- `tgenabled`: enabled status under relevant firing modes.
- `pg_get_triggerdef`: human-readable trigger definition.
- `tgisinternal`: distinguishes internal triggers such as FK mechanics.

### Why are catalogs important?

Application code may only show `UPDATE orders` without mentioning trigger names. To understand all actual side effects, you must inspect the deployed schema, not just Java source files.

Never modify `pg_trigger` directly. Use PostgreSQL-supported DDL managed through migrations.

## 54. EXPLAIN and Evaluating Trigger Overhead

You can run:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE guardrail_lab.orders
SET discount = discount + 1
WHERE order_id = 1;

ROLLBACK;
~~~

**Warning:** `EXPLAIN ANALYZE UPDATE` **actually executes the UPDATE**. Wrap it in a rolled-back transaction on a lab database so changes are not persisted. The `WAL` option depends on PostgreSQL version (available since PostgreSQL 13).

Some EXPLAIN reports for DML may display trigger execution times and activity. Not every version or plan shows the same level of detail.

Beyond statement duration, measure:

- Number of rows affected.
- CPU/IO from auxiliary SQL inside triggers.
- WAL records/bytes and dirty buffers where supported by tools.
- Lock waits during concurrent updates.
- Audit/outbox growth and index overhead.
- API TPS and p95/p99 latency.
- Autovacuum and dead tuples after write workloads.

**Do not conclude triggers are always slow or always fast.** Cost depends on row count, internal logic, indexes, data volume, and concurrency.

## 55. Testing Every Write Path in the Lab

A minimal test suite:

| Test | Operation | Expected |
| --- | --- | --- |
| 1 | INSERT order omitting status | status = draft |
| 2 | INSERT explicit NULL status | NOT NULL error |
| 3 | INSERT discount > subtotal | CHECK error |
| 4 | INSERT non-existent customer_id | FK error |
| 5 | INSERT confirmed order with total = 0 | CHECK error |
| 6 | UPDATE draft -> confirmed | Succeeds if amounts valid |
| 7 | UPDATE confirmed -> draft | Trigger error P2002 |
| 8 | UPDATE cancelled -> confirmed | Trigger error P2001 |
| 9 | UPDATE subtotal/discount | Generated total recalculates |
| 10 | Valid UPDATE | updated_at is stamped |
| 11 | Valid UPDATE | audit records OLD/NEW |
| 12 | UPDATE to confirmed | outbox receives pending event |
| 13 | Rollback transaction | Order/audit/outbox roll back together |
| 14 | UPDATE multiple rows | Row-level trigger runs for each matching row |
| 15 | Concurrent updates | Invariants hold under proper locking/isolation design |
| 16 | Trigger fails during audit insert | Original statement fails |
| 17 | Write via batch/COPY | Verify triggers/constraints behave as expected |
| 18 | DML using application role | Test permissions/RLS, not just owner |

### Tests require separate transactions

Do not run the whole table of error-inducing tests in a single transaction and continue as if nothing happened. A SQLSTATE constraint failure puts the transaction in an aborted state. Roll back or use controlled savepoints/test harnesses for each case.

## 56. Practice Exercises With Answers

The exercises below are based on `guardrail_lab` after running the lab. For DML, use `BEGIN; ... ROLLBACK;` so state does not change for subsequent exercises. Statements that intentionally fail must close their transaction appropriately before continuing.

### Exercise 1. Where should the initial status of an order be set?

**Answer:** `status text NOT NULL DEFAULT 'draft'`. This supplies the value when INSERT omits status.

### Exercise 2. What happens if the application passes an explicit NULL for status?

**Answer:** `DEFAULT` is not used automatically; `NOT NULL` raises an error.

### Exercise 3. What prevents a negative subtotal?

**Answer:** `subtotal numeric NOT NULL CHECK (subtotal >= 0)`. No trigger is needed to compare a column against a constant.

### Exercise 4. What prevents discount > subtotal?

**Answer:** `CHECK (discount <= subtotal)` with appropriate NOT NULL columns. This is a single-row invariant.

### Exercise 5. Why does CHECK(amount > 0) not forbid NULL?

**Answer:** CHECK accepts UNKNOWN/NULL results from an expression; add `NOT NULL` if required.

### Exercise 6. How should total be derived from subtotal - discount?

**Answer:** A generated column with an immutable expression over columns in the same row, or computed at SELECT time if storing is unnecessary.

### Exercise 7. Does DEFAULT updated_at change automatically on UPDATE?

**Answer:** No. You need a BEFORE UPDATE trigger or an application contract that writes timestamps properly; DEFAULT only applies when default values are resolved.

### Exercise 8. How should duplicate normalized emails be prevented?

**Answer:** Generated normalized_email + UNIQUE constraint/index, or an appropriately designed unique expression index; do not use a `SELECT count(*)` trigger instead of UNIQUE.

### Exercise 9. Customer_id must exist?

**Answer:** FOREIGN KEY referencing customers, not a trigger doing its own SELECT on the parent.

### Exercise 10. Status may only be draft/confirmed/cancelled?

**Answer:** CHECK (status IN (...)) with NOT NULL; if a domain type is needed, consider enum/domain depending on migration requirements.

### Exercise 11. Disallow cancelled -> confirmed?

**Answer:** A rule requiring OLD/NEW, suited to a BEFORE UPDATE trigger or a state-transition service properly protected in DB/transaction. CHECK status IN is insufficient.

### Exercise 12. What must a BEFORE ROW function return to continue an UPDATE?

**Answer:** Usually `RETURN NEW;`. Returning `NULL` skips the operation for that row under BEFORE ROW trigger semantics.

### Exercise 13. Does AFTER ROW RETURN NEW update the row?

**Answer:** No. The return value of an AFTER ROW trigger does not determine the written row; use BEFORE ROW if you want to modify `NEW`.

### Exercise 14. What does TG_OP mean?

**Answer:** The type of operation that fired the trigger, such as INSERT, UPDATE, DELETE, or TRUNCATE for supported events.

### Exercise 15. Is OLD meaningful during INSERT?

**Answer:** There is no old row for INSERT; NEW represents the row being inserted.

### Exercise 16. Does DELETE have NEW?

**Answer:** There is no new row for DELETE; use OLD to access the deleted row's state in a row trigger.

### Exercise 17. Audit before or after UPDATE?

**Answer:** AFTER ROW is usually suitable for storing OLD/NEW after DML processing; use BEFORE ROW if you need to intervene on the row itself.

### Exercise 18. How many times does an UPDATE of 100 rows fire a row trigger?

**Answer:** In principle, once per affected row for each row-level trigger; a statement trigger fires once per statement.

### Exercise 19. Does an audit trigger commit separately on its own?

**Answer:** No. The audit insert belongs to the original statement's transaction; an outer rollback cancels both.

### Exercise 20. Why is sending emails inside a trigger risky?

**Answer:** The DB transaction can roll back after the email was already sent; slow networks hold locks, and retries can send duplicates. Use an outbox + post-commit worker.

### Exercise 21. Does an outbox event guarantee exactly-once email delivery?

**Answer:** No. An outbox keeps recording the intent atomic with the DB transaction, while the worker needs retries/idempotency; external delivery is typically at-least-once.

### Exercise 22. What concurrency advantage does UNIQUE have over a COUNT trigger?

**Answer:** UNIQUE is enforced by the DB to guarantee uniqueness across concurrent transactions; a duplicate-counting trigger without proper locking has race conditions.

### Exercise 23. Two transactions both seeing 4 orders before INSERT is what kind of bug?

**Answer:** A race condition / multi-row logic flaw. A SELECT in a trigger does not enforce quotas. Proper counters, locking, constraints, or isolation levels are required.

### Exercise 24. Why is updating the same table inside AFTER UPDATE error-prone?

**Answer:** It can issue another UPDATE and trigger repeated firing (recursion). Stamping `NEW` in BEFORE ROW is simpler.

### Exercise 25. Users table needs unique email only when deleted_at IS NULL?

**Answer:** Use a conditional partial unique index if appropriate; understand partial index limitations and migrations.

### Exercise 26. Where should multi-tenant authorization live?

**Answer:** Application authorization and, when DB-level isolation is required, RLS/privileges; do not replace it with CHECK or simple triggers.

### Exercise 27. What happens if a trigger is disabled during a batch import?

**Answer:** Trigger logic may not run; you need privilege policies, import/replication procedures, and appropriate data validation/backfill steps. Never assume triggers run for every write method.

### Exercise 28. Can a trigger replace CREATE RULE?

**Answer:** Not always equivalent. Rules perform query rewrites, while triggers react at execution events; choose based on semantics, views, and use case.

### Exercise 29. What should forbid a confirmed order with total = 0?

**Answer:** `CHECK (status <> 'confirmed' OR subtotal > discount)`; it does not need OLD, so CHECK is better than a trigger.

### Exercise 30. Why is a generated column better than a trigger assigning total?

**Answer:** It clearly declares the formula from columns in the same row, PostgreSQL maintains it via generated column mechanics, and it reduces the risk of missing events or duplicating logic.

### Exercise 31. How do you view triggers attached to orders?

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid)
FROM pg_trigger
WHERE tgrelid = 'guardrail_lab.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

**Answer:** The catalog shows trigger names, states, and definitions on the table.

### Exercise 32. What SQLSTATEs correspond to CHECK and FK?

**Answer:** CHECK violation `23514`; foreign key violation `23503`.

### Exercise 33. What if a batch UPDATE fails on the last row?

**Answer:** The SQL statement fails and the statement's transactional effects are not partially committed under normal execution; roll back properly and do not assume earlier rows succeeded.

### Exercise 34. Why shouldn't audit logs be deletable if long-term auditing is desired?

**Answer:** Auditing usually needs strict privileges and clear retention, avoiding allowing the application to edit or delete records freely. A logging trigger alone does not guarantee tamper-evident auditing.

### Exercise 35. When should application validation still be used even when the DB has constraints?

**Answer:** To report errors early, guide users, support localization, and validate inputs before opening a transaction; the DB remains the final enforcement layer.

### Exercise 36. When should logic be moved to the service layer?

**Answer:** When workflows depend on user permissions, multiple services, external payment/email calls, retries, and orchestration. Keep using DB constraints and transactions to preserve invariants.

## 57. Common Mistakes

### 57.1. Using triggers for everything

Default values, single-row calculations, and UNIQUE/FK usually have better declarative mechanisms.

### 57.2. Validating only in the application

Another write path or race condition can bypass app-level checks.

### 57.3. Thinking DEFAULT runs on UPDATE

DEFAULT does not automatically stamp `updated_at` on every UPDATE.

### 57.4. Thinking explicit NULL gets replaced by DEFAULT

No; omit the column or use the DEFAULT keyword.

### 57.5. Thinking CHECK automatically forbids NULL

CHECK expressions evaluating to UNKNOWN/NULL are not treated as FALSE; add NOT NULL when needed.

### 57.6. Computing total with a trigger when a generated column suffices

This duplicates formulas and makes write paths harder to keep consistent.

### 57.7. Using a COUNT trigger instead of UNIQUE

Race conditions across transactions can cause duplicate data.

### 57.8. Using a trigger selecting parent instead of FOREIGN KEY

Easily misses locking, cascade, and concurrency semantics.

### 57.9. Checking only status IN while forgetting transition rules

A valid status value can still be reached via a forbidden transition.

### 57.10. Using RETURN NULL to "reject" without an error

Callers may not realize the row was skipped.

### 57.11. Modifying NEW in an AFTER trigger expecting the row to change

AFTER return values do not modify the written row the way BEFORE ROW does.

### 57.12. Updating the same table inside AFTER UPDATE

Can trigger recursion and redundant writes.

### 57.13. Ignoring ordering of BEFORE triggers

Triggers on the same event follow ordering rules; modifying NEW in an earlier trigger affects later ones.

### 57.14. Thinking audit triggers always commit

Auditing shares the transaction; a rollback rolls back the audit too.

### 57.15. Sending HTTP/email inside a trigger

External side effects cannot roll back with the database.

### 57.16. Thinking an outbox guarantees exactly-once delivery

Workers can still send duplicates; idempotency is required.

### 57.17. Confusing DB role with end-user identity

`current_user` is typically the connection role and does not automatically represent the end user.

### 57.18. Failing to govern disabled triggers or replication modes

Special write paths may not execute the same business behavior.

### 57.19. Catching all trigger errors and silently continuing

Can break consistency, auditing, and application contracts.

### 57.20. Ignoring per-row trigger cost

Row triggers execute repeatedly in batch DML.

### 57.21. Attaching triggers to the wrong object type (view/table)

INSTEAD OF, BEFORE/AFTER, and ROW/STATEMENT have different supported targets.

### 57.22. Treating RULE as equivalent to trigger

Rules rewrite queries; triggers react at execution. Misusing them causes unpredictable semantics.

### 57.23. Adding constraints to production without checking existing data

DDL can fail or cause locks/load affecting operations.

### 57.24. Adding a trigger and expecting historical audit records automatically

Triggers do not retroactively run once across existing rows; a separate backfill is needed.

### 57.25. Not testing SQLSTATE codes and rollbacks

Error paths are the clearest place to verify whether constraints and triggers actually protect data.

## 58. Project Implementation Checklist

- [ ] Classify each requirement as default, invariant, derived, event, workflow, or authorization.
- [ ] Prefer `NOT NULL`/`CHECK`/`UNIQUE`/`FK`/`EXCLUDE` when they accurately express an invariant.
- [ ] Use `DEFAULT` for values when INSERT omits a column; do not expect it to run on UPDATE.
- [ ] Use generated columns for immutable expressions over columns in the same row when appropriate.
- [ ] Identify which transitions require OLD/NEW and which trigger events protect them.
- [ ] Write BEFORE triggers to validate/modify NEW; AFTER triggers for transactional side effects.
- [ ] Avoid `RETURN NULL` unless skipping rows is intentional.
- [ ] Never modify NEW in AFTER expecting the row to change.
- [ ] Distinguish ROW/STATEMENT triggers and consider transition relations for batches.
- [ ] Control recursion and ordering among dependent triggers.
- [ ] Use clear SQLSTATE codes/constraint names rather than vague messages.
- [ ] Never use triggers to invoke email or payment HTTP calls directly.
- [ ] Use an outbox + worker with retry/idempotency for external side effects.
- [ ] Test transaction rollback across order, audit, and outbox together.
- [ ] For multi-row invariants, evaluate locks, isolation, and race conditions.
- [ ] Do not replace UNIQUE/FK with custom SELECT/COUNT triggers.
- [ ] Choose DB privileges/RLS and app authorization matching the threat model.
- [ ] Configure roles, privileges, and SECURITY DEFINER/search_path if privileged routines exist.
- [ ] Prevent application roles from arbitrarily disabling or altering triggers.
- [ ] Verify trigger behavior under COPY, batch imports, replication, and migrations.
- [ ] Plan backfills when adding triggers to tables with existing data.
- [ ] Measure write cost by row count, index maintenance, WAL, and lock waits.
- [ ] Measure p95/p99 API latency rather than only EXPLAINing a single UPDATE.
- [ ] Test all INSERT/UPDATE/DELETE paths, invalid data, and concurrency.
- [ ] Standardize migration/schema reviews so triggers do not become "invisible logic."
- [ ] Never run DROP SCHEMA or heavy DML benchmarks in production.

## 59. Notes on SECURITY DEFINER and search_path

Trigger functions execute by default with the caller's privileges, though sometimes they need permission to write to audit/outbox tables that the application role should not have directly. A `SECURITY DEFINER` routine can be part of the solution, but it **increases security responsibility**.

Principles:

- Only create SECURITY DEFINER when truly necessary.
- The function owner should be the least-privileged role required.
- Set a safe `search_path` so callers cannot redirect object resolution to untrusted schemas.
- Schema-qualify critical tables and functions.
- Control `EXECUTE` privileges.
- Do not use dynamic SQL with unvalidated or improperly quoted identifiers/values from input.
- Test using the actual application role.

In the lab, functions mostly schema-qualify tables like `guardrail_lab.order_audit` so write targets are obvious. In real deployments, conduct a dedicated security review rather than elevating privileges on every trigger by default.

## 60. Official PostgreSQL Documentation

Consult documentation for the **exact PostgreSQL major version you are running**:

- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html) — BEFORE/AFTER/INSTEAD OF, ROW/STATEMENT, WHEN, transition relations, and constraint triggers.
- [Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html) — `NEW`, `OLD`, `TG_OP`, return semantics.
- [Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html) — trigger firing and execution timing.
- [CREATE RULE](https://www.postgresql.org/docs/current/sql-createrule.html) — query rewrite rules vs. triggers.
- [DDL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html) — NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, EXCLUDE.
- [Default Values](https://www.postgresql.org/docs/current/ddl-default.html) — defaults on INSERT.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html) — conditions and semantics of generated columns.
- [Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html) — GENERATED AS IDENTITY.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — INSERT, DEFAULT, RETURNING, ON CONFLICT.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html) — UPDATE/RETURNING and DML.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html) — adding/validating constraints, enabling/disabling triggers by privilege.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS and its limitations.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — MVCC and concurrency.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, deadlocks.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html) — LANGUAGE, security definer.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — execution plans and costs.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — table/index statistics.

The `/current/` path points to the current PostgreSQL release documentation. If your system runs an older major version, cross-check generated columns, transition tables, MERGE/ON CONFLICT, and specific trigger rules against that version.

## 61. Summary

**Not every automatic behavior in a database should be written as a trigger.** PostgreSQL offers distinct mechanisms, each with a clear contract.

1. **DEFAULT** supplies values when INSERT omits a column; it does not re-run on UPDATE and does not replace explicit NULL.
2. **Constraints** guard against invalid states. `CHECK` handles single-row invariants, `UNIQUE` handles uniqueness, and `FK` handles references; prefer them over custom validation triggers.
3. **Generated columns** express values computed purely from columns in the same row, such as `total = subtotal - discount`.
4. **BEFORE ROW triggers** fit cases requiring comparison of `OLD`/`NEW` or modifying `NEW`, such as preventing reverse state transitions and stamping `updated_at`.
5. **AFTER ROW triggers** can write audit/outbox rows tied to row changes, but those writes **belong to the same transaction** and roll back with the statement/caller.
6. **Application logic** orchestrates user permissions, UX, payments, notifications, retries, and external services outside the database.
7. **Outboxes** record event-emission intent atomically with data changes; workers still need idempotency and retries for external side effects.
8. **Triggers do not automatically eliminate race conditions**, especially for multi-row rules. Proper constraints/indexes, locking, isolation, or data modeling are required.
9. **Triggers carry operational considerations and costs**: recursion, batch overhead, migrations, permissions, replication modes, catalog visibility, and debugging.
10. **Good design combines layers intentionally**, rather than dumping every responsibility into one place.

When you know **which rules belong to data, which belong to events, and which belong to workflows**, you will build PostgreSQL systems that are clear, verifiable, concurrency-safe, and easy to maintain long term.
