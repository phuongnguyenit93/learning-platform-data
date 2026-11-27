# When to Use Constraints, Application Code, or Triggers in Oracle

When designing a data rule, Oracle Database provides multiple places to enforce it: **constraints** in the schema, **application code** in the service/client layer, and **triggers** that run automatically when a database event occurs. All three can validate or alter data, but their guarantees and execution timing differ greatly.

A rule like "each email may appear only once" needs to be protected across every session and every application writing to the table. A UNIQUE constraint is the natural choice because Oracle enforces uniqueness even when multiple transactions write concurrently. The application should still validate early to show a friendly message, but a pre-INSERT query check cannot replace a constraint under contention. Triggers are useful when you need to react to DML events, write audits, or apply logic that cannot be expressed as a constraint, yet triggers also make write behavior implicit and harder to trace.

This lesson belongs to the **Exceptions and Triggers** topic of *Database Engine Relational Oracle*. It focuses on:

- Roles and limitations of constraints, application validation, and triggers.
- How to choose the right place to enforce integrity rules.
- Oracle constraints: NOT NULL, CHECK, UNIQUE, PRIMARY KEY, and FOREIGN KEY.
- Integrity under concurrency and transactions.
- When to use application code for validation and workflows.
- When triggers are useful, along with their risks and limitations.
- Combining layers, error handling, and diagnostics.
- SQL hands-on exercises comparing the three approaches.

## 1. Three Places Where Data Rules Can Be Enforced

### Constraints: Rules Guaranteed by the Database

A constraint is a schema declaration describing a condition data must satisfy. Oracle checks constraints on INSERT/UPDATE and at times governed by the constraint's state/attributes. Because the rule lives in the database itself, every application, batch job, script, or user with DML privileges is subject to the exact same rule.

Example:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT nn_customers_email NOT NULL,
    status VARCHAR2(20)
        CONSTRAINT ck_customers_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

The database guarantees customer_id is unique and non-NULL, email is non-NULL, and status is within the allowed set of values. Callers cannot bypass these rules merely by using a different application.

### Application Code: Validation and Use-Case Rules

Application code can validate input before sending DML to Oracle. It understands UI context, user identity, requests, approval workflows, and can return friendly messages.

For example, a service can check:

- Whether an email matches product formatting rules.
- Whether a delivery date falls within a user-selectable range.
- Whether the user is authorized to create orders in the current tenant.
- Whether an action is permitted in the current workflow state.
- Whether related fields were supplied together.

Application code is the right place for logic dependent on request context or user experience. However, if the same data can be written from multiple applications, batches, or scripts, validation in only one client does not provide shared integrity guarantees.

### Triggers: Automatic Reactions to Database Events

A trigger is a PL/SQL program automatically executed by the database when a specified event occurs, such as INSERT, UPDATE, or DELETE on a table, a DDL event, or a database event. Triggers are not called directly like ordinary procedures; Oracle fires them according to the declared event and timing.

Audit trigger example:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_status_audit
AFTER UPDATE OF status ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_status_audit (
        customer_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.customer_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

Every time status is updated, the trigger records old/new values in the same transaction. Triggers can ensure behavior runs for all DML on the table, including DML that bypasses the primary application.

## 2. Principles for Choosing Where to Enforce

Before writing code, classify which category the rule belongs to:

1. **Data invariant:** every row must satisfy the condition regardless of who writes the data. Prefer constraints.
2. **Request validation:** needs early checking, user-friendly errors, or user context. Place in the application, while still using constraints for expressible invariants.
3. **Database event reaction:** needs auditing, consistent behavior for all DML, or compatibility with legacy schemas/views. Consider a trigger if no clearer mechanism exists.
4. **Multi-step business workflow:** needs service calls, notifications, approvals, or external system integration. Place in the application/service layer or an event/outbox system; do not turn triggers into a workflow engine.

### Quick Decision Table

| Need | Preferred choice | Reason |
| --- | --- | --- |
| Column must have a value | NOT NULL constraint | Simple rule, guaranteed by the database. |
| Value must lie in a valid domain | CHECK constraint | Clear declaration, applies to all DML. |
| Keys must not duplicate | UNIQUE/PRIMARY KEY constraint | Oracle handles concurrency across transactions. |
| Foreign key must reference parent row | FOREIGN KEY constraint | Protects inter-table relationships. |
| Show friendly error before submit | Application validation | Close to UI and request context. |
| Operation permissions by user/tenant | Application authorization and appropriate database controls | Requires identity and security context. |
| Record changes from all DML sources | Audit trigger or appropriate auditing mechanism | Runs automatically in the database. |
| Normalize input values | Usually in application; can use virtual column/index/trigger per requirements | Choose a place that maintains a single rule. |
| Send email or call external API after save | Application/outbox | Avoids non-transactional side effects in triggers. |
| Rule requires querying multiple rows to verify | Redesign schema/constraints appropriately or use transactional service; triggers only if concurrency is fully understood | Simple SELECT checks can race and row triggers can hit mutating tables. |

### Questions Before Deciding

- Must the rule apply to all data-writing sources or just one use case?
- Can Oracle express the rule via a constraint or index?
- Could two concurrent transactions both pass the validation step?
- Does the rule need user info, request context, or external services?
- Is automatic behavior needed per row, per statement, or for DDL/database events?
- Who will understand, test, and operate the logic once it lives in a trigger?
- Can the logic be written explicitly in a SQL statement or API rather than creating implicit side effects?

## 3. Constraints: First Choice for Data Integrity

Constraints are the clearest declarative mechanism for many common integrity rules. Oracle can use constraint metadata to validate data and assist the optimizer in some cases.

### NOT NULL

Use when a column must always have a value:

~~~sql
CREATE TABLE products (
    product_id NUMBER PRIMARY KEY,
    product_name VARCHAR2(200) NOT NULL
);
~~~

The application should still report "Product name is required" before submitting. Yet NOT NULL guarantees another batch job or script cannot write NULL into the column.

### CHECK

Use for single-row conditions:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2)
        CONSTRAINT ck_employees_salary
        CHECK (salary >= 0),
    status VARCHAR2(20)
        CONSTRAINT ck_employees_status
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'LEFT'))
);
~~~

A CHECK constraint permits expressions that evaluate to TRUE or UNKNOWN; a row with NULL may not be rejected by CHECK alone. If the column is also required, declare NOT NULL separately.

A CHECK constraint is not a general tool to query other tables, check multi-row aggregates, or call APIs. Keep CHECK expressions scoped to the row and conditions Oracle supports.

### UNIQUE and PRIMARY KEY

~~~sql
CREATE TABLE app_users (
    user_id NUMBER
        CONSTRAINT pk_app_users PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT uq_app_users_email UNIQUE
);
~~~

PRIMARY KEY identifies rows and disallows NULL on key columns. UNIQUE guarantees unique keys per Oracle semantics, though nullable columns may allow NULLs. If email is required, combine with NOT NULL.

Oracle typically uses a unique index to enforce non-deferrable PK/UNIQUE constraints; for DEFERRABLE constraints, index behavior may differ. A standalone index does not automatically create a constraint in metadata.

### FOREIGN KEY

~~~sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

FOREIGN KEY ensures non-NULL customer_id values reference a valid key in the parent table. If a customer is required, add NOT NULL on customer_id. Oracle does not automatically create an index on the child table's FK column; consider indexing based on query workload and parent-key delete/update operations.

### Constraints for Multi-Column Rules

~~~sql
CREATE TABLE booking_slots (
    booking_id NUMBER PRIMARY KEY,
    room_id NUMBER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    CONSTRAINT ck_booking_time
        CHECK (end_time > start_time)
);
~~~

CHECK can validate relationships between columns in the same row. A rule like "no two overlapping bookings in the same room" spans multiple rows and cannot be expressed with a standard CHECK constraint; it requires key/slot design, transaction serialization, locked application logic, or another suitable solution.

## 4. Application Code: Validation, Workflows, and Authorization

Application validation runs close to the request and can give early feedback before the database runs DML. This is the right place for rules needing context the schema lacks, such as current user, tenant, resource permissions, screen contents, or workflow state.

### Input Validation

Example service handling an account creation request:

~~~text
Request
  |
  v
Validate required fields and format
  |
  v
Check business rules and caller permissions
  |
  v
Attempt INSERT
  |
  v
Database constraints are final integrity guard
~~~

The application can check valid email format, name length, date of birth, user status, or required fields. At the same time, the database should still have corresponding NOT NULL, CHECK, UNIQUE, or FK constraints when the rule is a data invariant.

Early validation helps users fix mistakes easily. Constraints ensure data cannot be corrupted if another write path exists or two requests run concurrently.

### Application Code Fits Context-Dependent Rules

Examples:

- Users may only update orders they created themselves.
- Only team leads may approve requests in their own team.
- An order is confirmed only when the payment service returns a valid status.
- Delivery dates must match regional operating schedules.
- Each customer may have at most one pending request in a given workflow.

These rules may require identity, tenant, permissions, external service data, or multiple steps. They usually belong in the service layer, though if the final rule can also be represented by a constraint, declare the constraint as well to protect the data.

### Check-Then-INSERT Has a Race Condition

A common bug is checking whether an email exists before INSERTing:

~~~sql
SELECT COUNT(*)
INTO l_count
FROM app_users
WHERE email = p_email;

IF l_count = 0 THEN
    INSERT INTO app_users(email)
    VALUES (p_email);
END IF;
~~~

Two sessions can both run SELECT before either session INSERTs:

~~~text
Session A                    Session B
------------------------     ------------------------
SELECT email -> no row
                             SELECT email -> no row
INSERT email
                             INSERT same email
COMMIT
                             COMMIT
~~~

Without a UNIQUE constraint, both rows can be inserted. With a UNIQUE constraint, one transaction wins and the other is rejected when Oracle detects the conflict. Therefore, application pre-checks only serve early feedback; they cannot replace a unique constraint.

### Handling Constraint Errors in the Application

Applications should catch corresponding Oracle errors and map them to business messages. For example, ORA-00001 indicates unique constraint/index violation; ORA-01400 indicates inserting NULL into a NOT NULL column; ORA-02291 indicates a parent key violation on FK write; ORA-02292 indicates a parent key is still referenced on delete/update.

Do not catch every exception and simply return "invalid data." Distinguish validation errors, concurrency conflicts, connection errors, and system errors to choose appropriate messaging or retries.

### Application Code and Transactions

When a rule requires reading and then writing multiple tables, the application can wrap all steps in one transaction. However, a transaction alone does not prevent all race conditions under READ COMMITTED. Identify the invariant and select an appropriate synchronization mechanism:

- Constraints/indexes so the database resolves uniqueness and referential integrity.
- SELECT FOR UPDATE to lock a representative row when all transactions follow the same protocol.
- Advisory/application locks or DBMS_LOCK when justified and managed properly.
- An appropriate isolation level if business rules require it; understand serialization/ORA-08177 implications under SERIALIZABLE.
- Schema design representing invariants via unique keys or representative rows rather than race-prone aggregate checks.

### Authorization Is Not the Same as a Constraint

Constraints protect data validity; they do not replace user permission checks. For example, CHECK status IN ('ACTIVE','DISABLED') only restricts the value domain; it does not determine who is allowed to transition ACTIVE to DISABLED. User/tenant permissions are typically enforced in the application or appropriate database security policies like VPD/RLS depending on architecture.

Do not use triggers to guess the application user when connections share one schema account and fail to pass identity reliably. User context must be established and protected properly.

## 5. Triggers: Types, Timing, and Scope

Triggers are attached to an event. For DML triggers on tables, key choices include:

- BEFORE or AFTER: runs before or after the corresponding statement/row event.
- Statement-level or row-level: runs once per statement or once per affected row.
- INSERT, UPDATE, DELETE: selects firing DML types.
- UPDATE OF column: fires only when the UPDATE references listed columns; does not mean values actually changed.

### Statement-Level Triggers

A statement-level trigger runs once for the entire DML statement, has no current row, and therefore cannot use :OLD/:NEW:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_stmt
AFTER INSERT OR UPDATE OR DELETE ON orders
BEGIN
    DBMS_OUTPUT.PUT_LINE('DML statement affected orders');
END;
/
~~~

This trigger runs once per statement, even if the statement affects 0 rows.

### Row-Level Triggers

A row-level trigger has FOR EACH ROW and runs once for each affected row. It can use :OLD and :NEW to read before/after values:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_status
BEFORE UPDATE OF status ON orders
FOR EACH ROW
BEGIN
    IF :NEW.status IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order status cannot be NULL'
        );
    END IF;
END;
/
~~~

In a row trigger:

- INSERT: :NEW holds new row values; :OLD has no prior row.
- UPDATE: :OLD holds values before update; :NEW holds values after update.
- DELETE: :OLD holds the deleted row; :NEW has no new row.
- Do not assign directly to :OLD.
- In BEFORE EACH ROW, you can assign :NEW.column to set values before saving; AFTER EACH ROW only reads :NEW/:OLD.

The trigger above merely illustrates validation; if status must be non-NULL, a NOT NULL constraint is a more direct and reliable declarative choice.

### BEFORE Triggers vs. AFTER Triggers

| Timing | Common uses |
| --- | --- |
| BEFORE EACH ROW | Normalize or assign :NEW values; validate row attributes; set audit context. |
| AFTER EACH ROW | Write audit/side tables based on finalized values; update row-dependent logic. |
| BEFORE STATEMENT | Prepare state for statement, check overall conditions. |
| AFTER STATEMENT | Perform work needing the statement to finish row processing. |

Choose timing based on the data you need to read and desired effect. AFTER triggers cannot modify :NEW; BEFORE EACH ROW triggers can assign :NEW, yet should not replace DEFAULT or simple SQL expressions when those suffice.

## 6. When Triggers Are Useful

Triggers fit when behavior must execute automatically for all DML on an object, even when writers are outside the main application. Before creating a trigger, however, check whether DEFAULT, identity columns, constraints, virtual columns, views, or an explicit PL/SQL API meet the need more simply.

### Change Auditing

A trigger can record who/when/old and new values when a row changes:

~~~sql
CREATE TABLE customer_audit (
    audit_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_id NUMBER,
    old_status VARCHAR2(20),
    new_status VARCHAR2(20),
    changed_by VARCHAR2(128),
    changed_at TIMESTAMP
);

CREATE OR REPLACE TRIGGER trg_customer_status_audit
AFTER UPDATE OF status ON customers
FOR EACH ROW
WHEN (OLD.status <> NEW.status)
BEGIN
    INSERT INTO customer_audit (
        customer_id,
        old_status,
        new_status,
        changed_by,
        changed_at
    )
    VALUES (
        :NEW.customer_id,
        :OLD.status,
        :NEW.status,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYSTIMESTAMP
    );
END;
/
~~~

The WHEN condition in the example only illustrates changes between two non-NULL values. If OLD.status or NEW.status can be NULL, the <> comparison evaluates to UNKNOWN; write a null-safe condition matching business rules, such as using DECODE or an explicit NULL-handling expression.

An audit trigger runs for all DML changing status on the table, including scripts/batches. The audit record shares the same transaction, so it rolls back if the customer update transaction rolls back. This is usually right when audits reflect committed changes.

### Setting Defaults or Normalizing Before Save

A BEFORE EACH ROW trigger can assign :NEW:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_normalize
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    :NEW.email := LOWER(TRIM(:NEW.email));
END;
/
~~~

Use a trigger only if all write paths must apply the exact same normalization and no better declarative mechanism exists. For simple rules, you can normalize in the application, use a separate normalized column, virtual column, or function-based index. If you only need a default when a column is omitted, DEFAULT/identity is usually clearer.

### Compatibility with Complex Views

An INSTEAD OF trigger can allow INSERT/UPDATE/DELETE through a view that Oracle cannot update automatically:

~~~sql
CREATE OR REPLACE TRIGGER trg_v_employee_dept_ins
INSTEAD OF INSERT ON v_employee_department
FOR EACH ROW
BEGIN
    INSERT INTO employees (
        employee_id,
        last_name,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.last_name,
        :NEW.department_id
    );
END;
/
~~~

The example requires the corresponding view and underlying tables; its purpose is to show a trigger translating view operations into underlying table DML. INSTEAD OF triggers run in place of DML on the view and are commonly used to support join views or views with complex structures.

### Database/DDL Event Triggers

Oracle also supports DDL triggers and database event triggers for events such as CREATE, ALTER, DROP, LOGON, or LOGOFF (depending on scope and trigger type). They fit certain governance, auditing, or session-setup needs. This group of triggers has broad impact; require proper privileges, thorough testing, and avoid breaking routine administrative operations due to auxiliary logic.

### Enforcing Shared Logic for All DML Sources

If multiple systems write to the same table and must maintain a side effect in the database, a trigger can ensure the side effect runs even if callers do not know the trigger exists. Still, the more critical the logic, the more it needs clear documentation, discoverable naming, error monitoring, and test entry points. When a side effect is core business logic, an explicit PL/SQL API is often easier to control than an implicit trigger.

## 7. When Not to Use Triggers

### Do Not Use Triggers to Replace Simple Constraints

Do not write a SELECT COUNT trigger to reject duplicates when a UNIQUE constraint can do the job. Row-level triggers checking their own table can hit mutating-table errors; hand-written triggers are also prone to race conditions without proper locking and transaction coordination. Unique indexes/constraints are database mechanisms built specifically for concurrent uniqueness.

### Do Not Use Triggers to Host Long Workflows

Triggers are unsuitable for:

- Sending emails or SMS directly.
- Calling HTTP APIs on other systems.
- Waiting for user approvals.
- Running long multi-step workflows.
- Performing heavy per-row tasks during large bulk loads.

Triggers execute on the session's DML path. If a trigger calls a slow or failing external service, write operations slow down or fail. For external integration, typically use a transactional outbox: write the event to a table in the same transaction, then have a worker/application read and deliver it to the external system.

### Do Not Use Triggers Just to Copy Data If SQL Expresses It Clearer

If you need to compute derived columns within the same table, consider SQL expressions, virtual columns, or model redesign. If you need to sync summary tables, materialized views or explicit jobs may fit better. Triggers create hidden dependencies and can make a simple UPDATE touch many tables unknown to the caller.

### Do Not Put Normal COMMIT/ROLLBACK Inside Triggers

Triggers execute in the firing statement's transaction. Regular triggers cannot COMMIT or ROLLBACK the caller's transaction; transaction control inside triggers is restricted. If a trigger needs to log independently of the main transaction, an autonomous transaction can be used in special cases, but understand that the independent audit can persist even if the original DML rolls back. Do not use autonomous transactions to bypass constraints or create inconsistent side effects.

### Do not Use Triggers to Mask Access Control

Triggers do not replace authorization. If application users connect through a shared schema, SESSION_USER typically identifies only that shared database account, not the end user. To audit end users, establish an application context reliably and protect privileges for setting context; do not trust arbitrary client-sent values without authentication.

## 8. Technical Risks When Using Triggers

### Mutating Tables: ORA-04091

A row-level trigger cannot query or modify the very table currently being changed by a statement in contexts where Oracle considers the table mutating. Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_check
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM orders
    WHERE customer_id = :NEW.customer_id;
END;
/
~~~

This trigger queries ORDERS directly inside a row-level trigger on ORDERS and can raise ORA-04091 (table is mutating). While processing each row, Oracle forbids querying the modifying table in a way that could observe an incomplete state.

Do not fix the error by arbitrarily switching to an autonomous transaction or disabling the trigger. First identify the invariant; if possible, use UNIQUE/CHECK/FK constraints or rewrite as set-based SQL.

### Compound Triggers

A compound DML trigger has multiple timing sections sharing common state within a single statement scope. It can collect data in BEFORE/AFTER EACH ROW and query the table after the statement completes in AFTER STATEMENT, when the table is no longer mutating for that statement.

Illustrative skeleton:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_compound
FOR INSERT OR UPDATE ON orders
COMPOUND TRIGGER
    TYPE t_customer_ids IS TABLE OF orders.customer_id%TYPE
        INDEX BY PLS_INTEGER;
    g_customer_ids t_customer_ids;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_count := g_count + 1;
        g_customer_ids(g_count) := :NEW.customer_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_count LOOP
            -- Can query the ORDERS table here after the statement completes.
            NULL;
        END LOOP;
    END AFTER STATEMENT;
END trg_orders_compound;
/
~~~

Compound triggers can resolve certain mutating-table situations by deferring table queries to AFTER STATEMENT. They do not automatically make multi-row rules concurrency-safe; you must still design locking/transactions and avoid race-prone aggregate checks.

### Per-Row Triggers Can Be Expensive

If an UPDATE affects one million rows, a row-level trigger can run one million times. If each invocation also SELECT/INSERT/UPDATEs multiple other tables, cost can skyrocket. Consider statement-level or compound triggers, set-based SQL, bulk processing, and minimizing side effects.

### Trigger Ordering

A table can have multiple triggers for the same timing/event. If logic depends on order, design to avoid implicit dependencies or use Oracle-supported ordering mechanisms such as FOLLOWS/PRECEDES within supported scopes and trigger types. Do not assume order among triggers unless declared/guaranteed.

### Triggers Can Cause Recursion or DML Chains

A trigger updating another table can fire triggers on that table; trigger chains can create multi-layered DML, recursion errors, or hard-to-trace behavior. Avoid triggers cycling back to the same table or chain of tables, or design control flags/context carefully. Do not arbitrarily use package variables as global flags because state is session-scoped and can affect subsequent requests.

### Triggers Can Obscure DML Failures

A caller might see only an INSERT into the main table without knowing a trigger also INSERT/UPDATEs other tables. When the trigger fails, the firing statement can fail. Document triggers thoroughly, inspect USER_TRIGGERS and USER_ERRORS, and log meaningful errors. Do not catch WHEN OTHERS and ignore errors unless there is an explicit error-handling rule.

## 9. Combining Constraints, Application Code, and Triggers

In real systems, the three mechanisms usually work together rather than excluding one another. Good design places each rule in the layer able to guarantee it while avoiding duplicating complex logic.

### Example: Account Registration with Unique Email

**Database:**

~~~sql
CREATE TABLE app_users (
    user_id NUMBER GENERATED ALWAYS AS IDENTITY,
    email VARCHAR2(320) NOT NULL,
    display_name VARCHAR2(100) NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_app_users PRIMARY KEY(user_id),
    CONSTRAINT uq_app_users_email UNIQUE(email),
    CONSTRAINT ck_app_users_status
        CHECK (status IN ('ACTIVE', 'DISABLED'))
);
~~~

**Application:**

1. Check that email and display name are provided.
2. Normalize email per product rules.
3. Optionally check whether email exists for early feedback.
4. Execute INSERT.
5. Catch ORA-00001 if another request created the same email concurrently and return an appropriate message.

**Trigger:** add only if there is an auditing requirement or database-wide behavior not guaranteed by other mechanisms. No trigger is needed to check duplicate emails because the UNIQUE constraint already does that.

### Example: Auditing All Status Changes

- Constraints protect the valid status domain.
- The application verifies the user has permission to change status and the workflow permits that transition.
- A trigger records OLD/NEW status for all DML, if audits must cover scripts and batches as well.

~~~sql
ALTER TABLE app_users
ADD CONSTRAINT ck_app_users_status
CHECK (status IN ('ACTIVE', 'DISABLED', 'PENDING'));
~~~

If immutable auditing and strict controls are required, also evaluate Oracle Unified Auditing or a dedicated auditing solution instead of writing triggers by default.

### Example: Derived Values

If you need to store an order total:

- If for display only, compute via query/view.
- If using a generated expression on the same row, consider a virtual column.
- If a summary table must stay updated across multiple detail rows, consider materialized views, jobs, or events/outbox.
- A trigger can update the total on each order line change, but must handle concurrency, bulk DML, deletes/updates, and performance.

Do not pick a trigger merely because it runs automatically. Choose the mechanism with clear semantics that is easy to rebuild when recomputing data.

## 10. DEFERRABLE Constraints and End-of-Transaction Rules

Some PRIMARY KEY/UNIQUE/FOREIGN KEY constraints can be declared DEFERRABLE to postpone checking until a requested point, typically COMMIT. This is useful for transactions needing intermediate states that temporarily violate uniqueness while remaining valid by transaction end.

~~~sql
CREATE TABLE lab_priority (
    item_id NUMBER PRIMARY KEY,
    priority_no NUMBER,
    CONSTRAINT uq_lab_priority UNIQUE(priority_no)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Inside a transaction, you can temporarily swap two priority values and validate at transaction end:

~~~sql
SET CONSTRAINTS uq_lab_priority DEFERRED;

UPDATE lab_priority
SET priority_no = 20
WHERE item_id = 1;

UPDATE lab_priority
SET priority_no = 10
WHERE item_id = 2;

COMMIT;
~~~

A deferred constraint is still a database rule. It only changes when checking occurs. Applications must handle errors when SET CONSTRAINTS IMMEDIATE or COMMIT detects violations.

### Do Not Use Triggers to Emulate Deferred Constraints

If the requirement is uniqueness/referential integrity, look into DEFERRABLE constraints before considering triggers that validate final state. Triggers do not naturally share the same constraint-validation timing model and can introduce hard-to-handle concurrency bugs.

## 11. Choosing Mechanisms for Multi-Row or Multi-Table Rules

Not every rule is a single-row CHECK. For example:

- A customer's total usage must not exceed their budget.
- No two room bookings may overlap in time.
- Each customer may have only one order in OPEN status.
- Inventory quantity must not go negative under concurrent transactions.

These rules require careful design because a SELECT check followed by INSERT/UPDATE is not inherently concurrency-safe.

### Express Rules as Constraints/Indexes When Possible

For example, "at most one OPEN order per customer" can use a function-based unique index:

~~~sql
CREATE UNIQUE INDEX ux_one_open_order_per_customer
ON orders (
    CASE WHEN status = 'OPEN' THEN customer_id END
);
~~~

This guarantees at most one row with status OPEN per non-NULL customer_id. If customer_id is mandatory, declare NOT NULL. This is a conditional unique index, not a standard UNIQUE constraint with a predicate.

### Use Locking to Serialize When Invariants Depend on Aggregates

For example, budget enforcement can lock the CUSTOMER_BUDGET row representing the customer before reading remaining funds and recording a new charge:

~~~sql
SELECT remaining_amount
INTO l_remaining
FROM customer_budget
WHERE customer_id = p_customer_id
FOR UPDATE;

IF l_remaining < p_amount THEN
    RAISE_APPLICATION_ERROR(-20020, 'Budget exceeded');
END IF;

UPDATE customer_budget
SET remaining_amount = remaining_amount - p_amount
WHERE customer_id = p_customer_id;
~~~

Every transaction modifying that customer's budget must follow the exact same locking protocol. If any write path bypasses the representative lock, the invariant is no longer protected. Perform the steps in the same transaction and do not COMMIT between check and update.

### Triggers Can Participate but Do Not Automatically Solve Concurrency

Placing a summing SELECT inside a row trigger does not make it safe. The trigger still runs in the DML's transaction and can hit mutating tables, race conditions, or deadlocks. If a trigger acquires representative locks, every DML path must understand lock ordering and potential errors.

### Application Validation for Multi-Table Rules

Applications/services usually coordinate workflows, locks, and transactions; database constraints still guard declarable parts. If database-level enforcement is needed across multiple writing applications, consider a single stored procedure/API, restricted DML privileges on base tables, and forcing callers through the API. This design requires evaluating privileges, transactions, and administrative paths.

## 12. Diagnosing Constraints and Triggers in Oracle

When DML fails or a trigger behaves unexpectedly, inspect metadata instead of looking only at application source code.

### Viewing Table Constraints

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       search_condition
FROM user_constraints
WHERE table_name = 'APP_USERS'
ORDER BY constraint_type, constraint_name;
~~~

CONSTRAINT_TYPE is commonly P (primary key), U (unique), R (foreign key), C (check/not null). Dictionary views may represent NOT NULL as constraint type C.

### Viewing Columns Belonging to Constraints

~~~sql
SELECT constraint_name,
       table_name,
       column_name,
       position
FROM user_cons_columns
WHERE table_name = 'APP_USERS'
ORDER BY constraint_name, position;
~~~

### Viewing Table Triggers

~~~sql
SELECT trigger_name,
       triggering_event,
       trigger_type,
       status,
       when_clause
FROM user_triggers
WHERE table_name = 'APP_USERS'
ORDER BY trigger_name;
~~~

### Viewing Trigger Source and Compile Errors

~~~sql
SELECT name, type, line, text
FROM user_source
WHERE type = 'TRIGGER'
  AND name = 'TRG_CUSTOMERS_STATUS_AUDIT'
ORDER BY line;

SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### Checking Whether a Trigger Is ENABLED or DISABLED

~~~sql
ALTER TRIGGER trg_customers_status_audit DISABLE;
ALTER TRIGGER trg_customers_status_audit ENABLE;
~~~

Do not disable triggers in production just to let DML pass without understanding side effects. While disabled, automatic auditing/logic can be skipped; data created during that interval may go out of sync. If maintenance is needed, plan a catch-up and integrity check after re-enabling.

## 13. Mapping Oracle Errors to Business Errors

Constraints usually return standard Oracle error codes. Applications/services should recognize the exact error and translate it into meaningful responses rather than relying on whether a pre-check succeeded.

| Error code | Common cause | Suggested application response |
| --- | --- | --- |
| ORA-00001 | Unique constraint or unique index violation | Email/identifier already in use; prompt for another value. |
| ORA-01400 | Insert NULL into NOT NULL column | Missing required field. |
| ORA-02290 | CHECK constraint violation | A value fails allowed domain/condition rules. |
| ORA-02291 | FOREIGN KEY parent key violation | Parent record does not exist or invalid reference. |
| ORA-02292 | Parent key referenced by child rows | Cannot delete/update a record currently in use. |
| ORA-04091 | Mutating table in trigger | Fix trigger/logic design; do not retry DML endlessly. |
| ORA-04098 | Trigger invalid and fails revalidation at runtime | Check source, USER_ERRORS, and dependencies. |

Constraint names may appear inside ORA-00001/ORA-02290 messages; applications can use those names to distinguish specific errors. Do not rely on parsing the full message text if your driver exposes vendor error codes or constraint names directly.

### Do Not Retry All Constraint Errors

ORA-00001 is generally not resolved by retrying the same data; report a conflict or run appropriate idempotency logic. Connection/timeout errors may merit controlled retries. Classify errors before retrying to avoid creating duplicates or repeating side effects.

### Deferred Constraints Can Fail at COMMIT

If a constraint is DEFERRABLE INITIALLY DEFERRED, DML statements may succeed while COMMIT detects the violation. Applications must wrap both DML and COMMIT in the same error-handling flow, not just catch exceptions around INSERT/UPDATE.

## 14. Hands-On Exercise: Constraints, Application Validation, and Triggers

Perform in a learning schema with CREATE TABLE, CREATE SEQUENCE, and CREATE TRIGGER privileges. DDL issues an implicit commit in Oracle; do not run on real business tables.

### Step 1: Create Table and Constraints

~~~sql
CREATE TABLE lab_users (
    user_id NUMBER
        CONSTRAINT pk_lab_users PRIMARY KEY,
    email VARCHAR2(200) NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_lab_users_email UNIQUE(email),
    CONSTRAINT ck_lab_users_status
        CHECK (status IN ('ACTIVE', 'DISABLED'))
);
~~~

Try inserting valid data:

~~~sql
INSERT INTO lab_users(user_id, email, status)
VALUES (1, 'mai@example.com', 'ACTIVE');

INSERT INTO lab_users(user_id, email, status)
VALUES (2, 'an@example.com', 'ACTIVE');

COMMIT;
~~~

Test each invalid statement individually to observe errors:

~~~sql
-- Violates NOT NULL:
INSERT INTO lab_users(user_id, email)
VALUES (3, NULL);

-- Violates CHECK:
INSERT INTO lab_users(user_id, email, status)
VALUES (4, 'bad@example.com', 'UNKNOWN');

-- Violates UNIQUE:
INSERT INTO lab_users(user_id, email, status)
VALUES (5, 'mai@example.com', 'ACTIVE');
~~~

Each violating statement will be rejected by Oracle. If running in a script client that stops on errors, execute each statement individually.

### Step 2: Simulate Application Validation

An application can check early before INSERT:

~~~sql
DECLARE
    l_email lab_users.email%TYPE := 'mai@example.com';
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM lab_users
    WHERE email = l_email;

    IF l_count > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Email already exists');
    ELSE
        INSERT INTO lab_users(user_id, email)
        VALUES (10, l_email);
    END IF;
END;
/
~~~

This gives an early message if the email already exists. Remember, however, that two sessions can both check before a row exists and both attempt INSERT; the UNIQUE constraint is the final safeguard. To test the race condition, open two sessions, run SELECT before either inserts, then insert the same email. One transaction will hit a unique conflict once the other commits.

### Step 3: Create Audit Table and Sequence

~~~sql
CREATE TABLE lab_user_audit (
    audit_id NUMBER PRIMARY KEY,
    user_id NUMBER NOT NULL,
    old_status VARCHAR2(20),
    new_status VARCHAR2(20),
    changed_at TIMESTAMP NOT NULL
);

CREATE SEQUENCE seq_lab_user_audit START WITH 1 INCREMENT BY 1;
~~~

### Step 4: Create Audit Trigger

~~~sql
CREATE OR REPLACE TRIGGER trg_lab_user_status_audit
AFTER UPDATE OF status ON lab_users
FOR EACH ROW
WHEN (OLD.status <> NEW.status)
BEGIN
    INSERT INTO lab_user_audit (
        audit_id,
        user_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        seq_lab_user_audit.NEXTVAL,
        :NEW.user_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

### Step 5: Observe the Trigger

~~~sql
UPDATE lab_users
SET status = 'DISABLED'
WHERE user_id = 1;

SELECT user_id, email, status
FROM lab_users
WHERE user_id = 1;

SELECT user_id, old_status, new_status, changed_at
FROM lab_user_audit
WHERE user_id = 1;

COMMIT;
~~~

The trigger writes the audit in the same transaction. Try ROLLBACK instead of COMMIT in a separate run: both the status change and the audit row roll back. Sequence NEXTVAL does not roll back; sequences can have gaps and are not transactional counters.

### Step 6: Inspect Metadata

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'LAB_USERS'
ORDER BY constraint_type, constraint_name;

SELECT trigger_name, triggering_event, trigger_type, status
FROM user_triggers
WHERE table_name = 'LAB_USERS';

SELECT name, type, line, text
FROM user_errors
WHERE name = 'TRG_LAB_USER_STATUS_AUDIT'
ORDER BY sequence;
~~~

### Step 7: Clean Up Data

~~~sql
DROP TRIGGER trg_lab_user_status_audit;
DROP SEQUENCE seq_lab_user_audit;
DROP TABLE lab_user_audit PURGE;
DROP TABLE lab_users PURGE;
~~~

Run only after completing the lab and no longer needing the data. DROP is DDL and issues an implicit commit.

## 15. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Application sees no duplicate yet INSERT still fails with ORA-00001 | Another transaction INSERTed the same key after the pre-check | Keep the UNIQUE constraint and handle DML conflicts. |
| Batch job writes rule-violating data | Validation exists only in one application client | Move invariants to constraints or a controlled database API. |
| Audit trigger does not run | Trigger DISABLED, wrong event, or DML fails WHEN condition | Check USER_TRIGGERS, triggering_event, status, and WHEN clause. |
| Trigger error causes INSERT/UPDATE failure | Exception inside trigger fails firing statement | Check USER_ERRORS/source and fix cause; do not swallow errors arbitrarily. |
| ORA-04091 | Row-level trigger queries mutating table | Use constraints/set-based SQL or compound trigger/proper transaction design. |
| Audit row disappears on rollback | Audit insert shares transaction with main DML | Expected consistent behavior if audit reflects committed changes; use autonomous audit only when independence is clearly required. |
| Trigger calling external API slows DML | Trigger synchronously calls external service | Use an outbox and asynchronous worker. |
| Data updated multiple times unexpectedly | Trigger creates DML chains/recursion | Map dependencies, break loops, and use explicit APIs. |
| Row-level trigger slows bulk DML | Trigger runs once per row executing extra SQL | Reduce work, use compound/statement-level or set-based logic. |
| Trigger records wrong end user | SESSION_USER is shared schema account | Set application context securely or audit at user-aware layer. |
| Constraint fails at COMMIT | DEFERRABLE constraint checked at transaction end | Catch errors at transaction boundaries and identify violating data. |

## 16. Self-Check Questions

1. **What kind of rules are constraints best suited for?** Data invariants that must be guaranteed by the database for all DML sources.
2. **When is application validation appropriate?** When request context, permissions, workflows, or user-friendly feedback are needed.
3. **When are triggers appropriate?** When automatic reaction to database events across all DML sources or special view/event handling is required.
4. **Why can't a duplicate-checking SELECT replace a UNIQUE constraint?** Because two transactions can both check before either inserts.
5. **Does a CHECK constraint automatically disallow NULL?** No; UNKNOWN is not rejected like FALSE, so add NOT NULL if required.
6. **Does a FOREIGN KEY automatically create an index on the child table?** No; consider indexing based on workload.
7. **What can a BEFORE EACH ROW trigger do with :NEW?** It can assign :NEW values before the row is written.
8. **Can an AFTER EACH ROW trigger assign :NEW?** No; it only reads OLD/NEW.
9. **How many times does a statement-level trigger run?** Once per statement, even if the statement affects 0 rows.
10. **How many times does a row-level trigger run?** Once for each affected row.
11. **What is a mutating-table error?** ORA-04091 when a row trigger queries/modifies a table currently mutated by the statement in a forbidden context.
12. **How do compound triggers help?** Sharing state across timing sections and deferring table queries to AFTER STATEMENT.
13. **Can a trigger COMMIT the caller's transaction?** Regular triggers cannot control the caller's transaction.
14. **Why should you not send emails directly from a trigger?** External services can be slow/fail and are not transactional; use an outbox/worker instead.
15. **Do normal audit triggers roll back with the DML?** Yes, because the audit insert is in the same transaction.
16. **When should autonomous transactions be considered for auditing?** Only when audits must survive rollback and the system accepts those semantics.
17. **Do triggers replace authorization?** No; triggers do not inherently know the end user when sessions share a schema account.
18. **How should ORA-00001 be handled?** Identify the conflict, return a business error or run idempotency logic; do not retry blindly.
19. **When can a deferred constraint raise an error?** When switching to IMMEDIATE or when COMMIT checks the constraint.
20. **What should be checked before writing a trigger?** Constraints, DEFAULT, identity, virtual columns, views, set-based SQL, explicit packages/APIs, and built-in auditing mechanisms.

Use constraints for data invariants Oracle can express declaratively, application code for request-level validation, permissions, and workflows, and triggers for database-event behaviors that must run automatically across all DML sources. All three can work together: applications validate early, constraints guard data under concurrency, and triggers record audits or support views. Before adding a trigger, evaluate implicit side effects, mutating tables, transactions, performance, and operability; critical logic should be documented with clear diagnostic paths.
