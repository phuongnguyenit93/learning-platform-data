# :OLD, :NEW, and Handling INSERT/UPDATE/DELETE in Oracle Database

In Oracle DML triggers, **:OLD** and **:NEW** are two special pseudorecords that allow access to row values before and after an operation. They let a trigger know whether a row was just INSERTed, UPDATEd, or DELETEd, enabling data validation, default value assignment, auditing, or synchronization of related information.

Core understanding:

- For **INSERT**, **:NEW** contains the values of the row being inserted; **:OLD** has no prior row values.
- For **UPDATE**, **:OLD** contains the values before modification and **:NEW** contains the values after applying the change.
- For **DELETE**, **:OLD** contains the row about to be deleted; **:NEW** has no new row values.

These two pseudorecords can only be used in a row-level trigger context. Statement-level triggers do not have a specific row to reference. Inside the trigger body, write **:OLD.column_name** and **:NEW.column_name**; specifically in the trigger **WHEN** condition, use **OLD.column_name** or **NEW.column_name** without a colon.

This lesson explains the lifecycle of OLD/NEW values, differences between row-level and statement-level triggers, how to handle each DML type, checking whether columns actually changed, auditing, validation, triggers on views, mutating table errors, compound triggers, and operational principles.

## 1. The :OLD and :NEW Pseudorecords

### 1.1. What Is a Pseudorecord?

A pseudorecord is a special structure provided by Oracle inside row-level triggers. It is accessed like a record with fields corresponding to the columns of the table or view being processed by the trigger.

Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_salary
BEFORE UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Old salary = ' || :OLD.salary
    );

    DBMS_OUTPUT.PUT_LINE(
        'New salary = ' || :NEW.salary
    );
END;
/
~~~

When a row is UPDATEd, **:OLD.salary** is the salary before the operation, while **:NEW.salary** is the salary after applying the value in the UPDATE statement. In a BEFORE ROW trigger, the NEW value can still be adjusted by the trigger before the row is written.

A pseudorecord is not a PL/SQL variable declared by the developer. Do not declare OLD or NEW in the DECLARE section, and do not use them outside the corresponding trigger.

### 1.2. OLD/NEW Matrix by DML

| Operation | :OLD | :NEW | Meaning |
| --- | --- | --- | --- |
| INSERT | No prior row; OLD fields are NULL | Values of the row about to be added | Read new data, can assign :NEW in BEFORE ROW |
| UPDATE | Values before modification | Values after applying UPDATE | Compare changes, validate, or adjust :NEW in BEFORE ROW |
| DELETE | Values of the row about to be deleted | No new row; NEW fields are NULL | Read row information for auditing or checking |

You can remember it as:

~~~text
INSERT:  NULL  -> :NEW
UPDATE:  :OLD  -> :NEW
DELETE:  :OLD  -> NULL
~~~

This is the per-row view. A single DML statement can affect multiple rows, so the row trigger is called multiple times, each time with a pair of values corresponding to one row.

### 1.3. OLD and NEW Are Not Arbitrarily Modifiable Copies

- **:OLD** is pre-operation data and is read-only.
- **:NEW** can be assigned in a BEFORE EACH ROW trigger for INSERT or UPDATE.
- In an AFTER EACH ROW trigger, **:NEW** is read-only.
- In an INSTEAD OF trigger on a view, use OLD/NEW to read input values and perform DML on underlying tables; do not assign directly to the pseudorecords.
- Do not use pseudorecords in statement-level triggers.

You cannot assign **:OLD.salary := ...**. Nor should you try to assign **:NEW** in an AFTER trigger because the moment for modifying the row has already passed.

### 1.4. Accessing Column by Column

Read fields using dot notation:

~~~sql
:OLD.employee_id
:NEW.employee_id
:OLD.salary
:NEW.salary
~~~

Field names correspond to the columns of the table/view. In a multi-event trigger, some fields have no value in a specific event. For example, in a trigger handling both INSERT and DELETE, during INSERT there is no OLD row, and during DELETE there is no NEW row.

## 2. Row-Level Triggers and Statement-Level Triggers

### 2.1. Row-Level Triggers

A trigger with the FOR EACH ROW clause is a row-level trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_row
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Changed order ' || :OLD.order_id
    );
END;
/
~~~

If UPDATE affects 100 rows, the row-level trigger runs 100 times. Each time, OLD and NEW represent a different row.

Row-level triggers are suitable when you need to:
- Validate per-row values.
- Assign column values before saving.
- Compare OLD and NEW.
- Write per-row audits.
- Trigger actions dependent on specific row data.

### 2.2. Statement-Level Triggers

A trigger without FOR EACH ROW is a statement-level trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_statement
AFTER UPDATE ON orders
BEGIN
    DBMS_OUTPUT.PUT_LINE('An UPDATE statement completed');
END;
/
~~~

The trigger runs once for the UPDATE statement, not once per row. It does not have OLD or NEW, so it cannot directly know which individual rows changed.

Statement-level triggers are suitable for statement-level tasks, such as:
- Recording the start/end of a batch operation.
- Initializing or cleaning up state used across triggers.
- Computing aggregates after all rows have been processed.
- Performing work that requires re-querying the table after the statement.

### 2.3. Statements Affecting Zero Rows

For a valid DML statement, a statement-level trigger can still run once even if the predicate matches zero rows. Row-level triggers only run when rows are actually processed.

~~~sql
UPDATE orders
SET status = 'CLOSED'
WHERE order_id = -999;
~~~

If no rows match:
- The AFTER STATEMENT trigger for the UPDATE event is still invoked.
- The AFTER EACH ROW trigger is not invoked.

This point matters when using a statement trigger to log a batch execution: the trigger records that the statement ran, which does not mean any rows changed.

### 2.4. Order of Trigger Timing Points

A typical DML statement has these phases:

~~~text
BEFORE STATEMENT
       |
       v
  For each row:
  BEFORE EACH ROW
       |
       v
  Oracle applies the row change
       |
       v
  AFTER EACH ROW
       |
       v
AFTER STATEMENT
~~~

Statement-level triggers run once at the start/end of the statement. Row-level triggers run around each row's operation. When multiple triggers share the same timing/event, do not rely on an arbitrary order; if order control is needed, check the FOLLOWS/PRECEDES mechanism supported for your specific trigger type and version.

## 3. Using INSERTING, UPDATING, and DELETING

### 3.1. Event-Identification Predicates

Inside a DML trigger body, Oracle provides these predicates:
- INSERTING: the trigger is handling an INSERT branch.
- UPDATING: the trigger is handling an UPDATE branch.
- DELETING: the trigger is handling a DELETE branch.

Example of one trigger handling multiple events:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_dml
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        DBMS_OUTPUT.PUT_LINE('INSERT order ' || :NEW.order_id);

    ELSIF UPDATING THEN
        DBMS_OUTPUT.PUT_LINE('UPDATE order ' || :OLD.order_id);

    ELSIF DELETING THEN
        DBMS_OUTPUT.PUT_LINE('DELETE order ' || :OLD.order_id);
    END IF;
END;
/
~~~

In each branch, use the pseudorecord appropriate for that event.

### 3.2. UPDATING('column_name')

UPDATING('column_name') checks whether the column appears in the SET list of the UPDATE statement.

~~~sql
IF UPDATING('SALARY') THEN
    DBMS_OUTPUT.PUT_LINE('SALARY was included in SET list');
END IF;
~~~

This does not guarantee the value actually changed. For example:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 100;
~~~

UPDATING('SALARY') is still TRUE because SALARY is in the SET list, even though the old and new values are identical.

### 3.3. UPDATE OF in Trigger Declaration

You can restrict a trigger to fire only for UPDATE statements that reference certain columns:

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_change
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :OLD.salary <> :NEW.salary THEN
        DBMS_OUTPUT.PUT_LINE('Salary value changed');
    END IF;
END;
/
~~~

UPDATE OF salary is an event-declaration condition. It can still fire when a statement writes SET salary = salary; comparing OLD/NEW inside distinguishes whether the value actually changed.

### 3.4. One Trigger Handling Multiple Events

A single trigger can declare multiple DML events:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        -- Handle INSERT
        NULL;
    ELSIF UPDATING THEN
        -- Handle UPDATE
        NULL;
    ELSIF DELETING THEN
        -- Handle DELETE
        NULL;
    END IF;
END;
/
~~~

Use ELSIF to ensure each execution enters the right branch. Do not access NEW in the DELETE branch or treat OLD as having pre-existing data in INSERT.

## 4. Comparing OLD and NEW Values

### 4.1. Simple Comparison When Columns Are NOT NULL

If a column is always NOT NULL, you can use:

~~~sql
IF :OLD.status <> :NEW.status THEN
    -- Status value changed
END IF;
~~~

For nullable columns, the <> comparison yields UNKNOWN when either side is NULL. In that case, the IF condition is not treated as TRUE.

### 4.2. Comparison with NULL Handling

An explicit approach:

~~~sql
IF (:OLD.status <> :NEW.status)
   OR (:OLD.status IS NULL AND :NEW.status IS NOT NULL)
   OR (:OLD.status IS NOT NULL AND :NEW.status IS NULL)
THEN
    DBMS_OUTPUT.PUT_LINE('STATUS changed');
END IF;
~~~

This condition covers all three cases:
- Both have values and differ.
- OLD is NULL, NEW has a value.
- OLD has a value, NEW is NULL.

If both are NULL, the value did not change.

### 4.3. Using DECODE to Compare NULLs

In Oracle, DECODE treats two NULLs as equal. You can write:

~~~sql
IF DECODE(:OLD.status, :NEW.status, 0, 1) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('STATUS changed');
END IF;
~~~

This is concise, though it requires understanding DECODE rules. For critical logic, an explicit NULL-handling expression can be easier to maintain.

### 4.4. Comparing Multiple Columns

You do not need to compare every column if the trigger only cares about specific attributes. Restrict with UPDATE OF or UPDATING('COLUMN'), then compare OLD/NEW for the relevant column.

~~~sql
IF UPDATING('SALARY')
   AND (
       (:OLD.salary <> :NEW.salary)
       OR (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
       OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
   )
THEN
    -- Record salary change
END IF;
~~~

Avoid writing a single huge trigger handling every column and every business rule if the logic can be separated cleanly.

## 5. Assigning :NEW in BEFORE INSERT/UPDATE

### 5.1. Setting Values Automatically Before Saving

A BEFORE EACH ROW trigger can modify the NEW values of an INSERT or UPDATE row.

~~~sql
CREATE OR REPLACE TRIGGER trg_employees_biu
BEFORE INSERT OR UPDATE ON employees
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        :NEW.created_at := COALESCE(
            :NEW.created_at,
            SYSTIMESTAMP
        );
    END IF;

    IF UPDATING THEN
        :NEW.updated_at := SYSTIMESTAMP;
    END IF;
END;
/
~~~

On INSERT, the trigger sets CREATED_AT if the caller did not provide a value. On UPDATE, the trigger updates UPDATED_AT.

This is an illustrative example. If you only need a default value on INSERT, you can use DEFAULT on the column; if you need to update a timestamp on UPDATE, a trigger may fit or the application can manage it explicitly in the service layer.

### 5.2. Data Normalization

Email normalization example:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_email_biu
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    IF :NEW.email IS NOT NULL THEN
        :NEW.email := LOWER(TRIM(:NEW.email));
    END IF;
END;
/
~~~

The normalized value will be stored. However, consider business rules and collation; not every data field should be automatically lowercased.

### 5.3. Do Not Assign :NEW in AFTER ROW

AFTER ROW is not the right time to modify row values:

~~~sql
-- Incorrect example by intent:
CREATE OR REPLACE TRIGGER trg_bad_after
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/
~~~

If you need to modify row values, use BEFORE EACH ROW or handle it in the original DML statement. AFTER triggers are suited for observing outcomes and performing auxiliary actions.

### 5.4. Using DEFAULT When a Trigger Is Unnecessary

If a column only needs a default value at INSERT time:

~~~sql
CREATE TABLE application_events (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY,
    event_type VARCHAR2(50) NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_application_events PRIMARY KEY (event_id)
);
~~~

DEFAULT is usually simpler and clearer than a trigger used solely to assign one default value. Use a trigger when logic depends on OLD/NEW or multiple DML conditions.

## 6. Data Validation Using OLD/NEW

### 6.1. Blocking Invalid Changes

Example disallowing moving an order creation date backwards:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_date_check
BEFORE UPDATE OF created_at ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at < :OLD.created_at THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'Created date cannot move backwards'
        );
    END IF;
END;
/
~~~

RAISE_APPLICATION_ERROR returns an application-defined business error. When a trigger raises an unhandled exception, the DML statement that fired it fails.

### 6.2. Checking Salary

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_limit
BEFORE INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :NEW.salary < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20032,
            'Salary must not be negative'
        );
    END IF;
END;
/
~~~

For a simple condition checking only one column, a CHECK constraint is usually the better choice:

~~~sql
ALTER TABLE employees
ADD CONSTRAINT ck_employees_salary_nonnegative
CHECK (salary >= 0);
~~~

Prefer constraints for declarative data integrity rules. Triggers are suitable when rules require OLD/NEW, multiple steps, or logic that cannot be expressed as a constraint.

### 6.3. Preventing Identifier Key Changes

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_pk_immutable
BEFORE UPDATE OF order_id ON orders
FOR EACH ROW
BEGIN
    IF :OLD.order_id <> :NEW.order_id THEN
        RAISE_APPLICATION_ERROR(
            -20033,
            'ORDER_ID cannot be changed'
        );
    END IF;
END;
/
~~~

Consider stable PK design and application UPDATE privileges before adding a trigger. You can revoke UPDATE privileges on the column if appropriate for your privilege model.

### 6.4. Triggers Do Not Replace Constraints Under Concurrency

A trigger checking for "no duplicate codes" by running SELECT COUNT(*) and then INSERT can suffer a race condition when two sessions run concurrently. Both can see that the code does not exist yet and both INSERT.

Use a UNIQUE constraint so the database guarantees uniqueness under concurrency. Triggers are not a substitute for constraints on uniqueness rules.

## 7. Handling INSERT, UPDATE, and DELETE in an Audit Trigger

### 7.1. Creating Example Tables

~~~sql
CREATE TABLE orders_demo (
    order_id     NUMBER GENERATED ALWAYS AS IDENTITY,
    status       VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    created_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    updated_at   TIMESTAMP,
    CONSTRAINT pk_orders_demo PRIMARY KEY (order_id),
    CONSTRAINT ck_orders_demo_amount CHECK (total_amount >= 0)
);

CREATE TABLE orders_demo_audit (
    audit_id     NUMBER GENERATED ALWAYS AS IDENTITY,
    action_type  VARCHAR2(10) NOT NULL,
    order_id     NUMBER NOT NULL,
    old_status   VARCHAR2(20),
    new_status   VARCHAR2(20),
    old_amount   NUMBER(12,2),
    new_amount   NUMBER(12,2),
    changed_at   TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    changed_by   VARCHAR2(128),
    CONSTRAINT pk_orders_demo_audit PRIMARY KEY (audit_id)
);
~~~

The audit table retains before/after values for the tracked columns. It does not need a foreign key to ORDERS_DEMO if you want to preserve history after an order is deleted.

### 7.2. Trigger Updating Timestamp

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_demo_bu
BEFORE UPDATE ON orders_demo
FOR EACH ROW
BEGIN
    :NEW.updated_at := SYSTIMESTAMP;
END;
/
~~~

This trigger only modifies NEW in a BEFORE UPDATE row trigger.

### 7.3. Audit Trigger for All Three Operations

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_demo_audit
AFTER INSERT OR UPDATE OR DELETE ON orders_demo
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'INSERT',
            :NEW.order_id,
            NULL,
            :NEW.status,
            NULL,
            :NEW.total_amount,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF UPDATING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'UPDATE',
            :OLD.order_id,
            :OLD.status,
            :NEW.status,
            :OLD.total_amount,
            :NEW.total_amount,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF DELETING THEN
        INSERT INTO orders_demo_audit (
            action_type, order_id, old_status, new_status,
            old_amount, new_amount, changed_at, changed_by
        )
        VALUES (
            'DELETE',
            :OLD.order_id,
            :OLD.status,
            NULL,
            :OLD.total_amount,
            NULL,
            SYSTIMESTAMP,
            SYS_CONTEXT('USERENV', 'SESSION_USER')
        );
    END IF;
END;
/
~~~

Characteristics:
- INSERT records the ID and new values from NEW.
- UPDATE records both old values from OLD and new values from NEW.
- DELETE records old values from OLD; NEW columns are stored as NULL.
- SYS_CONTEXT('USERENV','SESSION_USER') records the logged-in database user.

### 7.4. Testing the Three Operations

INSERT:

~~~sql
INSERT INTO orders_demo (status, total_amount)
VALUES ('NEW', 250000);
~~~

UPDATE:

~~~sql
UPDATE orders_demo
SET status = 'PAID',
    total_amount = 275000
WHERE order_id = 1;
~~~

DELETE:

~~~sql
DELETE FROM orders_demo
WHERE order_id = 1;
~~~

View audit:

~~~sql
SELECT action_type,
       order_id,
       old_status,
       new_status,
       old_amount,
       new_amount,
       changed_at,
       changed_by
FROM   orders_demo_audit
ORDER  BY audit_id;
~~~

ID 1 is just an example assuming it is the first row. In shared environments, retrieve the actual ID from INSERT using RETURNING INTO or query by a known business key.

### 7.5. Audit Triggers Participate in the Transaction

The audit row is INSERTed in the same transaction as the original DML. If the application ROLLBACKs the operation on ORDERS_DEMO, the audit row added by the trigger is also rolled back.

This is usually the right behavior for auditing business data changes: the audit reflects committed changes. If you need to record rolled-back attempts as well, design a separate logging mechanism and understand the risks of autonomous transactions. Do not arbitrarily add PRAGMA AUTONOMOUS_TRANSACTION to an audit trigger just to keep logs after rollback; it can produce history that does not reflect final state and cause locking/deadlock issues.

For security or compliance auditing requirements, examine Oracle Unified Auditing and centrally managed audit mechanisms rather than building custom triggers as the sole solution.

## 8. The WHEN Condition and OLD/NEW References

### 8.1. WHEN Clause

A row-level trigger can include a WHEN clause so it only runs when a condition is true:

~~~sql
CREATE OR REPLACE TRIGGER trg_closed_order
AFTER UPDATE OF status ON orders_demo
FOR EACH ROW
WHEN (NEW.status = 'CLOSED')
BEGIN
    INSERT INTO orders_demo_audit (
        action_type, order_id, old_status, new_status,
        old_amount, new_amount, changed_at, changed_by
    )
    VALUES (
        'CLOSE',
        :OLD.order_id,
        :OLD.status,
        :NEW.status,
        :OLD.total_amount,
        :NEW.total_amount,
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

In the WHEN clause, write NEW.status without a colon. Inside the PL/SQL trigger body, write :NEW.status.

### 8.2. WHEN Is Only a Simple Condition

The WHEN clause is not a full PL/SQL block. Do not write SELECT statements, subqueries, or multi-step statements inside it. If the condition is complex, let the trigger run and evaluate the check inside BEGIN...END.

### 8.3. Do Not Use WHEN for Complex OLD/NEW Comparisons

If you need to compare OLD and NEW with NULL handling or call business functions, write an IF statement inside the trigger body. This is easier to read and control.

## 9. Mutating Tables and ORA-04091

### 9.1. What Is a Mutating Table?

While a row-level trigger is processing a table, Oracle may forbid the trigger from querying or modifying the very table undergoing DML. A table in this changing state is called a mutating table.

Example of a problematic trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bad_check
AFTER UPDATE OF status ON orders_demo
FOR EACH ROW
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO   v_count
    FROM   orders_demo
    WHERE  status = :NEW.status;
END;
/
~~~

When running UPDATE on ORDERS_DEMO, the row-level trigger selects from ORDERS_DEMO itself. Oracle can raise ORA-04091: table is mutating, trigger/function may not see it.

The reason is that at the moment the row trigger runs, the statement may have processed only part of the rows. Allowing reads of the table as if it were in a completed state could yield inconsistent results.

### 9.2. Do Not Fix by Ignoring the Exception

Do not catch ORA-04091 and ignore it. You must change the design:
- Use OLD and NEW for information about the current row.
- Use a statement-level trigger if the work needs to run after the statement completes.
- Use a compound trigger to collect data in row sections and process it in AFTER STATEMENT.
- Use constraints or another data model if the rule can be expressed declaratively.

### 9.3. Compound Triggers

A compound trigger groups multiple timing sections in one trigger and shares PL/SQL state within the scope of a single DML statement:
- BEFORE STATEMENT.
- BEFORE EACH ROW.
- AFTER EACH ROW.
- AFTER STATEMENT.

OLD/NEW pseudorecords are only available in row sections. AFTER STATEMENT does not have :OLD/:NEW, but it can use data stored in collections from the row sections.

Example capturing status changes and writing audits after the statement:

~~~sql
CREATE TABLE orders_demo_status_audit (
    audit_id    NUMBER GENERATED ALWAYS AS IDENTITY,
    order_id    NUMBER NOT NULL,
    old_status  VARCHAR2(20),
    new_status  VARCHAR2(20),
    changed_at  TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_orders_demo_status_audit PRIMARY KEY (audit_id)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_status_ct
FOR UPDATE OF status ON orders_demo
COMPOUND TRIGGER

    TYPE t_id_tab IS TABLE OF orders_demo.order_id%TYPE
        INDEX BY PLS_INTEGER;
    TYPE t_status_tab IS TABLE OF orders_demo.status%TYPE
        INDEX BY PLS_INTEGER;

    g_order_ids  t_id_tab;
    g_old_status t_status_tab;
    g_new_status t_status_tab;
    g_count      PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF (:OLD.status <> :NEW.status)
           OR (:OLD.status IS NULL AND :NEW.status IS NOT NULL)
           OR (:OLD.status IS NOT NULL AND :NEW.status IS NULL)
        THEN
            g_count := g_count + 1;
            g_order_ids(g_count) := :NEW.order_id;
            g_old_status(g_count) := :OLD.status;
            g_new_status(g_count) := :NEW.status;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF g_count > 0 THEN
            FORALL i IN 1 .. g_count
                INSERT INTO orders_demo_status_audit (
                    order_id,
                    old_status,
                    new_status,
                    changed_at
                )
                VALUES (
                    g_order_ids(i),
                    g_old_status(i),
                    g_new_status(i),
                    SYSTIMESTAMP
                );
        END IF;
    END AFTER STATEMENT;

END trg_orders_status_ct;
/
~~~

In the example:
- AFTER EACH ROW only reads OLD/NEW and stores required values into collections.
- AFTER STATEMENT runs after the statement's rows have been processed.
- AFTER STATEMENT does not directly access pseudorecords.
- FORALL writes audit rows in bulk from arrays, reducing context switches between PL/SQL and SQL.

A compound trigger has its own state per statement execution. If the statement errors and rolls back, changes made by the trigger in the transaction also roll back according to standard transaction rules.

### 9.4. When to Use a Compound Trigger?

Use it when you need to:
- Collect per-row information.
- Compute or validate after the entire statement finishes.
- Avoid querying a mutating table inside a row-level section.
- Batch auxiliary DML operations.

Do not use a compound trigger just to make code more complex. If you only need to assign NEW or write one simple audit row per row, a standard row trigger is usually easier to understand.

## 10. INSTEAD OF Triggers on Views

### 10.1. Purpose

Some views cannot be INSERTed, UPDATEd, or DELETEd directly because they contain joins, grouping, or complex structures. An INSTEAD OF trigger defines how to translate DML on the view into operations on underlying tables.

An INSTEAD OF trigger is a row-level trigger on a view. It can read OLD and NEW to inspect the values sent by the user to the view and the old values represented by the view.

### 10.2. Simple View Example

~~~sql
CREATE OR REPLACE VIEW order_summary_v AS
SELECT order_id,
       status
FROM   orders_demo;
~~~

Create trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_order_summary_v_iud
INSTEAD OF INSERT OR UPDATE OR DELETE ON order_summary_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO orders_demo (status, total_amount)
        VALUES (:NEW.status, 0);

    ELSIF UPDATING THEN
        UPDATE orders_demo
        SET status = :NEW.status
        WHERE order_id = :OLD.order_id;

    ELSIF DELETING THEN
        DELETE FROM orders_demo
        WHERE order_id = :OLD.order_id;
    END IF;
END;
/
~~~

The example assumes the underlying table allows an amount of 0. In a real application, you must properly define key generation, required values, and mapping for all necessary columns.

### 10.3. OLD/NEW in INSTEAD OF Triggers

In an INSTEAD OF trigger:
- :NEW represents the data sent by the DML statement to the view to create/update.
- :OLD represents the old data of the view row during UPDATE/DELETE.
- The trigger uses those values to execute DML on the underlying tables.
- Do not assign directly to :NEW to alter view data; decide the values to write into the underlying tables in the corresponding DML statements.

## 11. DML Scenarios to Distinguish

### 11.1. UPDATE That Does Not Change Values

~~~sql
UPDATE orders_demo
SET status = status
WHERE order_id = 10;
~~~

The UPDATE event still occurs. UPDATING('STATUS') is TRUE. If you only want to audit when the value actually differs, compare OLD/NEW with NULL handling.

### 11.2. DELETE Differs from TRUNCATE

DELETE is DML and fires DELETE triggers according to the declared row/statement scope.

TRUNCATE is DDL. It does not fire row-level DELETE triggers for each row like a DELETE statement does. Do not use a DELETE trigger expecting per-row auditing when a DBA runs TRUNCATE PARTITION or TRUNCATE TABLE.

If you need to audit truncates, manage DDL privileges, use appropriate auditing, or follow dedicated administrative procedures.

### 11.3. MERGE

MERGE can execute INSERT for unmatched rows and UPDATE for matched rows. Relevant INSERT/UPDATE triggers may fire depending on the actual operations MERGE performs.

When using triggers with MERGE:
- Test the INSERT and UPDATE branches separately.
- Use INSERTING/UPDATING in the trigger to distinguish them.
- Test both matched and not-matched cases.
- Do not assume MERGE always invokes only one trigger type.

### 11.4. Multi-Row DML

A single UPDATE statement can modify multiple rows. A row trigger runs once per row; a statement trigger runs once for the statement.

Do not assume the order in which a row-level trigger processes rows matches primary key order or SELECT order. If business logic depends on order, design a separate operation with explicit ORDER BY/processing logic rather than relying on trigger firing order.

## 12. Transactions and Exceptions in Triggers

### 12.1. Triggers Participate in the Calling Transaction

DML inside a regular trigger belongs to the same transaction as the firing statement. If the outer DML rolls back, auxiliary operations in the trigger also roll back.

Do not call COMMIT or ROLLBACK inside a regular trigger. A trigger must not unilaterally end the caller's transaction.

### 12.2. Exceptions in Triggers

If a trigger raises an unhandled exception, the error propagates to the DML statement and the statement fails. Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_amount_guard
BEFORE INSERT OR UPDATE OF total_amount ON orders_demo
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20040,
            'Total amount must be non-negative'
        );
    END IF;
END;
/
~~~

When INSERTing/UPDATEing with a negative amount, the trigger rejects the operation. However, this simple rule should be expressed using a CHECK constraint if trigger logic is not needed.

### 12.3. Autonomous Transactions Require Careful Consideration

You can declare an autonomous transaction in certain triggers to log independently of the main transaction. However, when used, the audit can commit even if the business DML rolls back. That changes the meaning of the audit and can cause deadlocks if the autonomous transaction waits on resources held by the parent transaction.

Do not use autonomous transactions as a default way to preserve logs. Only use them when business requirements clearly specify recording events independently of the main transaction and lock interactions have been evaluated.

## 13. Designing Maintainable Triggers

### 13.1. Prefer Constraints When Possible

Use:
- NOT NULL for required columns.
- CHECK for single-row conditions.
- PRIMARY KEY for identifiers.
- UNIQUE for unique values.
- FOREIGN KEY for referential relationships.

Triggers should be reserved for logic requiring OLD/NEW, custom auditing, normalization, or behavior that cannot be cleanly expressed with constraints.

### 13.2. Keep Triggers Short and Single-Purpose

Triggers run implicitly when DML occurs. If a trigger is too long or calls many sub-procedures, maintainers have a hard time understanding why an INSERT/UPDATE causes side effects.

Recommendations:
- Name triggers to reflect timing/event/purpose.
- Use INSERTING, UPDATING, and DELETING clearly.
- Access only the necessary columns.
- Do not perform heavy queries per row if processing can happen after the statement.
- Avoid calling external services or performing non-transactional operations inside triggers.
- Test both single-row and multi-row DML.

### 13.3. Avoid Triggers Depending on Unreliable Execution Order

If multiple triggers run on the same table at the same timing point, do not assume a natural order. When ordering is required, review FOLLOWS/PRECEDES syntax and applicability limits in your Oracle version. Better yet, consolidate tightly coupled steps into one trigger or a clear business API.

### 13.4. Avoid Trigger Loops

A trigger on table A might perform DML on table B, and a trigger on table B might perform DML back on A. This can create trigger chains or unexpected recursion.

Map out dependency flows clearly and avoid having triggers call back into the table currently being modified. If bidirectional synchronization is needed, consider a business service/procedure design or queue mechanism instead of hard-to-control cascading triggers.

## 14. Inspecting and Managing Triggers

### 14.1. Viewing Triggers in a Schema

~~~sql
SELECT trigger_name,
       table_name,
       trigger_type,
       triggering_event,
       status
FROM   user_triggers
ORDER  BY table_name, trigger_name;
~~~

These columns identify which table a trigger belongs to, trigger type, event, and ENABLED/DISABLED status.

### 14.2. Viewing Source Code

~~~sql
SELECT line,
       text
FROM   user_source
WHERE  type = 'TRIGGER'
AND    name = 'TRG_ORDERS_DEMO_AUDIT'
ORDER  BY line;
~~~

You can use DBMS_METADATA.GET_DDL to retrieve the full trigger DDL if you have appropriate privileges.

### 14.3. Viewing Compilation Errors

In SQL*Plus/SQLcl you can use:

~~~sql
SHOW ERRORS TRIGGER trg_orders_demo_audit;
~~~

Or query errors in the dictionary:

~~~sql
SELECT line,
       position,
       text
FROM   user_errors
WHERE  type = 'TRIGGER'
AND    name = 'TRG_ORDERS_DEMO_AUDIT'
ORDER  BY sequence;
~~~

SHOW ERRORS is a SQL*Plus/SQLcl client command and is emulated by some script runners. It is not a standard SQL statement.

### 14.4. Enabling and Disabling

~~~sql
ALTER TRIGGER trg_orders_demo_audit DISABLE;

ALTER TRIGGER trg_orders_demo_audit ENABLE;
~~~

You can enable/disable all triggers on a table with ALTER TABLE ... ENABLE/DISABLE ALL TRIGGERS. This is a high-impact administrative operation; record initial states and inspect related triggers before running it.

Do not disable triggers in production just to speed up loads without assessing the auditing, validation, synchronization, and side effects the triggers perform.

## 15. Comprehensive Hands-On Exercises

Use your learning schema and the demo tables from section 7. Do not run delete or data-modifying commands on real systems without a backup.

### Exercise 1 — Observing OLD/NEW on INSERT

Create a BEFORE INSERT row trigger that prints :NEW.status and :NEW.total_amount. Observe that there is no OLD row before INSERT.

### Exercise 2 — Observing OLD/NEW on UPDATE

Update status and amount. Print both OLD and NEW to verify the two values belong to two different points in time.

### Exercise 3 — Observing DELETE

Create a BEFORE DELETE trigger and print :OLD.order_id and :OLD.status. Explain why NEW is not used to retrieve the row about to be deleted.

### Exercise 4 — One Trigger for Three Events

Write an AFTER INSERT OR UPDATE OR DELETE trigger. Use INSERTING, UPDATING, and DELETING to select the proper branch.

### Exercise 5 — UPDATING('column')

Run UPDATE SET status = status. Observe that UPDATING('STATUS') is still TRUE. Then add an OLD/NEW comparison to only record actual changes.

### Exercise 6 — Assigning :NEW

Create a BEFORE INSERT trigger that auto-populates CREATED_AT if NULL. Create a BEFORE UPDATE trigger that updates UPDATED_AT. Verify the saved values.

### Exercise 7 — Validation

Create a trigger that rejects negative amounts using RAISE_APPLICATION_ERROR. Then replace it with a CHECK constraint and compare the declarative approach.

### Exercise 8 — Auditing Three Events

Create an audit table and trigger recording INSERT/UPDATE/DELETE. Test COMMIT and ROLLBACK to verify audit rows participate in the same transaction.

### Exercise 9 — Mutating Table

Create a row trigger that re-queries the table currently being UPDATEd. Observe ORA-04091 in the test schema. Explain why the exception should not be ignored.

### Exercise 10 — Compound Trigger

Write a compound trigger that collects IDs and OLD/NEW statuses in AFTER EACH ROW, then writes audits in AFTER STATEMENT. Test a multi-row UPDATE.

### Exercise 11 — INSTEAD OF Trigger

Create a view and a trigger translating INSERT/UPDATE/DELETE on the view into DML on the underlying table. Verify the OLD/NEW mapping.

### Exercise 12 — DELETE and TRUNCATE

Compare DELETE with TRUNCATE on a test table. Verify that the DELETE trigger does not run per row when using TRUNCATE.

### Exercise 13 — MERGE

Write a MERGE statement with both WHEN MATCHED UPDATE and WHEN NOT MATCHED INSERT branches. Observe the corresponding trigger branches.

### Exercise 14 — Trigger Firing and Multiple Rows

Create a statement-level trigger and a row-level trigger for the same event. Run DML affecting multiple rows and then DML matching zero rows. Record how many times each trigger type runs.

## 16. Common Misconceptions

**":OLD and :NEW can be used in any trigger."** No. They are for row-level triggers; statement-level triggers do not have a single-row pseudorecord.

**"INSERT has :OLD containing values before insertion."** No. There is no row before INSERT; OLD has no row values and OLD fields are NULL.

**"DELETE has :NEW containing the row after deletion."** No. DELETE only has the old row values via OLD.

**"You can modify :NEW in an AFTER trigger."** No. Only assign NEW in BEFORE EACH ROW of INSERT/UPDATE.

**"UPDATING('SALARY') means salary changed."** No. It only indicates that SALARY is present in the SET list.

**"Statement triggers run once per row."** No. They run once per statement; row triggers run per row.

**"If an UPDATE doesn't change values, the trigger won't run."** The trigger can still run because the statement is an UPDATE; compare OLD/NEW to detect actual changes.

**"Both DELETE and TRUNCATE fire DELETE triggers."** No. TRUNCATE is DDL and does not fire row DELETE triggers.

**"You can SELECT from the table being updated inside a row trigger."** You may hit ORA-04091. Use OLD/NEW or compound trigger/statement-level logic.

**"Audit triggers always keep logs even when the transaction rolls back."** No. Normal audit DML shares the transaction and rolls back with the original DML.

**"Triggers are the best place to enforce all constraints."** No. Prefer NOT NULL, CHECK, UNIQUE, PRIMARY KEY, and FOREIGN KEY whenever possible.

**"The order of multiple triggers at the same timing point is always fixed."** Do not assume that; use supported ordering mechanisms or redesign dependencies.

## 17. Oracle References

- [Oracle Database PL/SQL Language Reference — Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/triggers.html): trigger types, timing points, row-level and statement-level.
- [Oracle Database PL/SQL Language Reference — Correlation Names and Pseudorecords](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/correlation-names-and-pseudorecords.html): OLD, NEW, and accessing pseudorecords.
- [Oracle Database PL/SQL Language Reference — Compound DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): compound triggers and timing sections.
- [Oracle Database Error Messages — ORA-04091](https://docs.oracle.com/en/error-help/db/ora-04091/): mutating table error.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): trigger creation syntax and WHEN condition.
- [Oracle Database Security Guide — Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): auditing mechanisms and security controls.

:OLD and :NEW tell a trigger the row state before and after DML. INSERT mainly uses NEW, DELETE uses OLD, and UPDATE uses both. Choose row-level when per-row data is needed, statement-level for statement-level processing; use BEFORE ROW to assign NEW and AFTER ROW to observe and audit. For simple checks, prefer constraints; for logic that needs multi-row processing or must avoid mutating tables, consider compound triggers. **Always verify the correct timing, event, and transaction scope before deploying triggers to production.**
