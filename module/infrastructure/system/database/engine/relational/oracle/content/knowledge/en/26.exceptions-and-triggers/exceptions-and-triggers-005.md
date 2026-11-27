# BEFORE, AFTER, Row-Level, and Statement-Level Triggers in Oracle

A DML trigger is a PL/SQL program that Oracle automatically invokes when an INSERT, UPDATE, or DELETE event occurs on a table or view. Triggers allow you to implement logic tied to data changes, such as normalizing values before writing, recording audit trails, maintaining auxiliary data, or enforcing rules that must run regardless of whether data is modified from an application, SQL client, or batch job.

When designing a trigger, you must distinguish two independent axes:

- **Timing:** whether the trigger runs before or after the DML operation — BEFORE or AFTER.
- **Granularity:** whether the trigger runs once for the entire statement or once for each affected row — statement-level or row-level.

Combining these two axes produces four common timing points: BEFORE STATEMENT, BEFORE EACH ROW, AFTER EACH ROW, and AFTER STATEMENT. Each type has a different data scope and purpose. Choosing the wrong timing or granularity can lead to repeated logic execution, inability to access :OLD/:NEW, mutating table errors, or hard-to-control data changes.

This lesson explains the trigger lifecycle, :OLD/:NEW pseudorecords, the WHEN condition, behavior with multi-row DML, execution order, compound triggers, transactions, errors, security, administration, and testing.

## 1. What Is a DML Trigger?

A trigger is a stored PL/SQL unit automatically executed by the database when a declared event occurs. For a DML trigger on a table, the event can be:

- INSERT: adding rows.
- UPDATE: modifying rows.
- DELETE: removing rows.

Example of a simple trigger that records order creation time:

~~~sql
CREATE OR REPLACE TRIGGER orders_before_insert
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at IS NULL THEN
        :NEW.created_at := CAST(SYSTIMESTAMP AS TIMESTAMP);
    END IF;
END;
/
~~~

This trigger is invoked before Oracle writes each inserted row. The FOR EACH ROW keyword defines this as a row-level trigger. The trigger can assign a value to :NEW before the row is stored.

If you omit FOR EACH ROW, the trigger becomes a statement-level trigger and runs once for the INSERT statement, regardless of how many rows the statement affects.

### 1.1. How Triggers Differ from Explicitly Called Procedures

A procedure only runs when a program calls it. A trigger is automatically invoked by Oracle when the corresponding event occurs.

| Characteristic | Procedure | DML trigger |
|---|---|---|
| Invocation | Caller invokes directly | Database invokes automatically when a DML event occurs |
| Timing | Follows program flow | Follows the declared timing point |
| Parameters | Can declare IN/OUT/IN OUT | Does not accept parameters like a procedure |
| Old/new row data | Caller must pass or query | Row triggers have :OLD and :NEW |
| Visibility | Call usually appears in caller source | Can be hidden behind a DML statement |
| Purpose | Database API, intentionally invoked processing | Reacting to data events |


## 2. Two Classification Axes: BEFORE/AFTER and Row/Statement

### 2.1. BEFORE and AFTER

- **BEFORE trigger:** runs before Oracle performs the DML operation at the corresponding timing point. A BEFORE row trigger is suitable for validating or normalizing :NEW.
- **AFTER trigger:** runs after the DML operation at the corresponding timing point. An AFTER row trigger is suitable for writing audit records about changes made; an AFTER statement trigger is suitable for overall processing after the statement.

BEFORE/AFTER describes when the trigger runs relative to the DML statement and the rows being processed. It does not mean an AFTER trigger runs after COMMIT. An AFTER trigger still runs within the same transaction as the DML statement; if the transaction rolls back, changes made by the trigger also roll back, unless an autonomous transaction is deliberately used.

### 2.2. Row-Level and Statement-Level

- **Row-level trigger:** has FOR EACH ROW and runs once for each row affected by the DML statement.
- **Statement-level trigger:** does not have FOR EACH ROW and runs once for each DML statement that fires the trigger.

Example of an UPDATE affecting 100 rows:

| Trigger type | Execution count |
|---|---:|
| BEFORE STATEMENT | 1 |
| BEFORE EACH ROW | 100 |
| AFTER EACH ROW | 100 |
| AFTER STATEMENT | 1 |

If the UPDATE statement finds no rows, statement-level triggers still run for that statement; row-level triggers have no rows to process so they are not invoked.

### 2.3. Four Timing Points

| Timing point | Granularity | Suitable work |
|---|---|---|
| BEFORE STATEMENT | Once per statement | Initialize state, record start, check statement-level conditions |
| BEFORE EACH ROW | Once per row | Assign defaults, normalize :NEW, validate row values |
| AFTER EACH ROW | Once per row | Audit each change, record :OLD/:NEW values |
| AFTER STATEMENT | Once per statement | Aggregate or process after all rows have been handled |

A single trigger can declare multiple DML events, such as INSERT OR UPDATE OR DELETE. In that case, the timing points execute for each corresponding event type.

## 3. Syntax for Creating a DML Trigger

Simple syntax template:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
    BEFORE | AFTER
    INSERT OR UPDATE OR DELETE
    ON table_name
    [FOR EACH ROW]
    [WHEN (condition)]
DECLARE
    -- Local declarations if needed
BEGIN
    -- Trigger body
END;
/
~~~

Main parts:

- CREATE OR REPLACE TRIGGER: creates a new trigger or replaces trigger source.
- BEFORE/AFTER: selects the timing.
- INSERT/UPDATE/DELETE: selects the event(s).
- ON table_name: the table or view the trigger is attached to.
- FOR EACH ROW: selects row-level; omitting it makes it statement-level.
- WHEN: additional condition for a row-level trigger.
- DECLARE: optional declaration section.
- BEGIN ... END: PL/SQL body.

Example of a trigger that only runs when salary is listed in the SET list:

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_salary_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_at
    ) VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

UPDATE OF salary specifies that the trigger is attached to UPDATE statements that reference the salary column in the SET clause. This does not automatically guarantee that the actual value changed. For example, UPDATE employees SET salary = salary can still fire the trigger because the salary column appears in the SET list. If you only want to write an audit record when the value differs, you must compare :OLD and :NEW inside the trigger.

## 4. Row-Level Triggers and :OLD, :NEW Pseudorecords

In a row-level trigger, Oracle provides two pseudorecords:

- :OLD: row values before the DML operation.
- :NEW: row values after the DML operation or values about to be written.

They are special structures provided by Oracle inside triggers, not record variables declared by the developer.

### 4.1. :OLD and :NEW by Event

| Event | :OLD | :NEW |
|---|---|---|
| INSERT | No old row values; do not use as a valid row | Row about to be inserted |
| UPDATE | Row before update | Row after update |
| DELETE | Row before delete | No new row values |

For INSERT, :OLD fields do not have old row values; for DELETE, :NEW does not have new row values. Do not write logic that depends on values that do not exist for the corresponding operation.

### 4.2. BEFORE EACH ROW Can Modify :NEW

Example normalizing email and setting creation time:

~~~sql
CREATE OR REPLACE TRIGGER customers_before_write
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    IF INSERTING AND :NEW.created_at IS NULL THEN
        :NEW.created_at := CAST(SYSTIMESTAMP AS TIMESTAMP);
    END IF;

    IF :NEW.email IS NOT NULL THEN
        :NEW.email := LOWER(TRIM(:NEW.email));
    END IF;
END;
/
~~~

A BEFORE row trigger can assign :NEW fields for INSERT and UPDATE. This allows normalizing values right before Oracle writes the row.

You cannot assign values to :OLD. Nor can you use :NEW to modify the row in an AFTER row trigger; at the AFTER point, the row operation has already occurred. If you need to change the stored value, use a BEFORE row trigger or place the normalization into the DML statement/API.

### 4.3. AFTER EACH ROW Reads Before and After Values

Audit example:

~~~sql
CREATE TABLE employee_salary_audit (
    employee_id NUMBER,
    old_salary  NUMBER,
    new_salary  NUMBER,
    changed_by  VARCHAR2(128),
    changed_at  TIMESTAMP
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_audit
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    INSERT INTO employee_salary_audit (
        employee_id,
        old_salary,
        new_salary,
        changed_by,
        changed_at
    ) VALUES (
        :OLD.employee_id,
        :OLD.salary,
        :NEW.salary,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYSTIMESTAMP
    );
END;
/
~~~

Each updated row creates an audit record in the same transaction. If the main transaction rolls back, this audit record also rolls back.

### 4.4. Do Not Use a Colon in the WHEN Clause

In the trigger body, pseudorecord references use the syntax :OLD.column and :NEW.column. In the WHEN clause, the reference syntax does not include a colon:

~~~sql
CREATE OR REPLACE TRIGGER employees_high_salary
AFTER INSERT OR UPDATE OF salary ON employees
FOR EACH ROW
WHEN (NEW.salary >= 100000)
BEGIN
    INSERT INTO high_salary_log (
        employee_id,
        salary_value,
        recorded_at
    ) VALUES (
        :NEW.employee_id,
        :NEW.salary,
        SYSTIMESTAMP
    );
END;
/
~~~

WHEN is only used for row-level triggers. Do not declare WHEN for statement-level triggers. Oracle evaluates the WHEN condition for each row before invoking the trigger body.

### 4.5. NULL and Comparing Old/New Values

In Oracle, the expression :OLD.salary <> :NEW.salary evaluates to UNKNOWN if either side is NULL. If you need to detect transitions from NULL to a value or vice versa, you must write explicit NULL-handling conditions.

~~~sql
IF (:OLD.salary <> :NEW.salary)
   OR (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
   OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
THEN
    -- Value actually changed
    NULL;
END IF;
~~~

If the column is declared NOT NULL, a simple comparison condition may suffice. Determine nullability and desired semantics before writing the audit condition.


## 5. Statement-Level Triggers

A statement-level trigger runs once per DML statement, without FOR EACH ROW.

Example recording when an UPDATE statement starts and ends:

~~~sql
CREATE TABLE dml_statement_log (
    table_name  VARCHAR2(128),
    action_name VARCHAR2(10),
    phase_name  VARCHAR2(20),
    logged_at   TIMESTAMP,
    session_user_name VARCHAR2(128)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_update_statement
BEFORE UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'BEFORE',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

The trigger runs once before the UPDATE statement, even if the UPDATE affects multiple rows or no rows at all.

You can create an AFTER statement trigger to record the completion phase:

~~~sql
CREATE OR REPLACE TRIGGER employees_update_after_stmt
AFTER UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'AFTER',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

This is an illustrative technical audit. For formal security auditing and traceability requirements, evaluate Oracle Unified Auditing or a centrally managed auditing mechanism; custom triggers do not replace all database auditing capabilities.

### 5.1. Statement Triggers Do Not Have :OLD/:NEW

A statement-level trigger is not tied to a specific row, so it does not have the :OLD and :NEW pseudorecords. You cannot access :NEW.employee_id inside a statement-level trigger.

If you need per-row values, you must use a row-level trigger or a compound trigger with an EACH ROW section.

### 5.2. Statement Triggers Still Run When No Rows Match

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = -999;
~~~

If no employees belong to department -999:
- BEFORE STATEMENT still runs once.
- AFTER STATEMENT still runs once.
- BEFORE EACH ROW and AFTER EACH ROW do not run because no rows are processed.

This is useful when you need to track DML statements submitted, even statements that modify zero rows.

## 6. Lifecycle and Timing Point Order

For a DML statement on a table with all corresponding triggers, the general order is:

~~~text
DML statement begins
        |
        v
BEFORE STATEMENT trigger
        |
        v
For each row processed:
    BEFORE EACH ROW trigger
        |
        v
    Oracle performs the row change
        |
        v
    AFTER EACH ROW trigger
        |
        v
Repeat for next row
        |
        v
AFTER STATEMENT trigger
        |
        v
DML statement completes
        |
        v
Caller continues the transaction
        |
        v
COMMIT or ROLLBACK decided by the transaction owner
~~~

The diagram illustrates the order of timing points. It does not mean AFTER STATEMENT occurs after COMMIT. Triggers still run before the transaction is committed.

### 6.1. Multi-Row UPDATE Example

~~~sql
UPDATE employees
SET salary = salary * 1.10
WHERE department_id = 20;
~~~

Suppose 25 rows are affected:
- BEFORE STATEMENT runs once.
- BEFORE EACH ROW runs 25 times.
- AFTER EACH ROW runs 25 times.
- AFTER STATEMENT runs once.

If there are multiple triggers at the same timing point and for the same event, do not rely on an implicit order among them. Combine dependent logic into a single trigger or use the FOLLOWS clause when supported by your Oracle version and trigger type, and document the order.

### 6.2. A Single Trigger Declaring Multiple Events

~~~sql
CREATE OR REPLACE TRIGGER employees_dml_audit
AFTER INSERT OR UPDATE OR DELETE ON employees
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

The conditional predicates INSERTING, UPDATING, and DELETING indicate which DML type fired the trigger. They can be used in the trigger body to branch logic.

You can check whether a specific column was mentioned in the SET list using UPDATING('COLUMN_NAME'). This checks whether the column appears in the SET clause, not whether the value actually changed.

### 6.3. UPDATE OF and Actual Value Changes

~~~sql
CREATE OR REPLACE TRIGGER employees_salary_change
AFTER UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    IF :OLD.salary <> :NEW.salary THEN
        NULL; -- Handle actual change
    END IF;
END;
/
~~~

The following statement can still fire the trigger because salary is in the SET list:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 101;
~~~

However, the condition in the body will not execute if the old and new values are equal (assuming salary is not NULL). You must distinguish between a column specified in the statement and data actually changing.

## 7. BEFORE EACH ROW: Normalization and Row Validation

A BEFORE row trigger is commonly suited for:
- Assigning default values if omitted by the caller.
- Normalizing strings.
- Checking rules that depend on row values.
- Setting certain technical attributes before saving.
- Generating keys if not using identity/default/sequence directly.

Example validating quantity:

~~~sql
CREATE OR REPLACE TRIGGER order_items_validate
BEFORE INSERT OR UPDATE OF quantity ON order_items
FOR EACH ROW
BEGIN
    IF :NEW.quantity IS NULL OR :NEW.quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20101,
            'Quantity must be greater than zero'
        );
    END IF;
END;
/
~~~

However, if a rule can be expressed using a CHECK constraint, prefer the constraint:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT order_items_quantity_ck
CHECK (quantity > 0);
~~~

Constraints are more transparent, enforced directly by the database, and do not require a trigger for a simple check. Triggers are more appropriate when logic cannot be expressed as a declarative constraint.

### 7.1. Assigning IDs in a Trigger

Legacy systems may use a BEFORE INSERT trigger to fetch NEXTVAL:

~~~sql
CREATE OR REPLACE TRIGGER orders_assign_id
BEFORE INSERT ON orders
FOR EACH ROW
WHEN (NEW.order_id IS NULL)
BEGIN
    :NEW.order_id := orders_seq.NEXTVAL;
END;
/
~~~

On Oracle versions that support identity columns or appropriate DEFAULT sequence expressions, consider declarative mechanisms instead of triggers. The choice depends on compatibility requirements, existing schema, and sequence management practices.

## 8. AFTER EACH ROW: Auditing and Reacting Per Row

An AFTER row trigger is suitable when you need to read old/new values after Oracle processes the row.

Example auditing INSERT, UPDATE, and DELETE:

~~~sql
CREATE TABLE employee_change_audit (
    employee_id NUMBER,
    operation   VARCHAR2(10),
    old_salary  NUMBER,
    new_salary  NUMBER,
    changed_at  TIMESTAMP,
    changed_by  VARCHAR2(128)
);
~~~

~~~sql
CREATE OR REPLACE TRIGGER employees_change_audit
AFTER INSERT OR UPDATE OF salary OR DELETE ON employees
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :NEW.employee_id, 'INSERT', NULL, :NEW.salary,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF UPDATING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :NEW.employee_id, 'UPDATE', :OLD.salary, :NEW.salary,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );

    ELSIF DELETING THEN
        INSERT INTO employee_change_audit (
            employee_id, operation, old_salary, new_salary,
            changed_at, changed_by
        ) VALUES (
            :OLD.employee_id, 'DELETE', :OLD.salary, NULL,
            SYSTIMESTAMP, SYS_CONTEXT('USERENV', 'SESSION_USER')
        );
    END IF;
END;
/
~~~

The example focuses on illustrating pseudorecords and conditional predicates. In a real system, you need to determine audit columns, sensitive data handling, audit access permissions, retention policies, and error handling.

### 8.1. Same-Transaction Audit Triggers

DML inside a regular trigger belongs to the same transaction as the statement that fired it. If the audit insert fails and the exception is not handled appropriately, the main DML statement can fail. If the caller rolls back, both the business change and the audit row in the same transaction roll back.

This is usually the desired behavior when the audit must accurately reflect committed changes. If the requirement is to record failed attempts as well, you must intentionally design independent logging and understand autonomous transactions.

## 9. AFTER STATEMENT: Processing After the Entire Statement

An AFTER statement trigger is suitable when you need to perform work once after all rows of the DML statement have been processed.

~~~sql
CREATE OR REPLACE TRIGGER employees_after_update_stmt
AFTER UPDATE ON employees
BEGIN
    INSERT INTO dml_statement_log (
        table_name,
        action_name,
        phase_name,
        logged_at,
        session_user_name
    ) VALUES (
        'EMPLOYEES',
        'UPDATE',
        'STATEMENT_COMPLETE',
        SYSTIMESTAMP,
        SYS_CONTEXT('USERENV', 'SESSION_USER')
    );
END;
/
~~~

If an UPDATE statement modifies 5,000 rows, the trigger still inserts only one statement log row. If you need to log 5,000 individual changes, use a row-level trigger.

### 9.1. Statement Triggers Have No Automatic List of Rows

A statement-level trigger does not provide a collection containing the rows that were just modified. If you need to aggregate over affected rows, you can:
- Use a row-level trigger to collect information.
- Use a compound trigger to share state across timing points.
- Move aggregation processing into an explicitly called procedure/API.
- Use a subsequent set-based SQL statement from the application or package.

Do not assume a statement trigger can read :OLD/:NEW for individual rows.


## 10. Mutating Tables and Error ORA-04091

A common error with row-level triggers is a **mutating table**. While Oracle is modifying a table, a row-level trigger on that same table cannot directly query or modify the table currently undergoing mutation in many normal DML contexts. Doing so can cause Oracle to raise ORA-04091: table is mutating, trigger/function may not see it.

Example likely to cause this error:

~~~sql
CREATE OR REPLACE TRIGGER employees_check_department
AFTER UPDATE OF department_id ON employees
FOR EACH ROW
DECLARE
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE department_id = :NEW.department_id;
END;
/
~~~

The trigger is running for one row of EMPLOYEES yet queries the entire EMPLOYEES table while the UPDATE statement is still processing rows. Oracle does not allow querying a mutating table in this manner because results could be inconsistent between already-processed and not-yet-processed rows.

### 10.1. Resolution Approaches

- Move the aggregate query to AFTER STATEMENT, once the statement has finished processing rows.
- Use a compound trigger to collect the necessary keys in EACH ROW and then query the table in AFTER STATEMENT.
- Move the logic to a procedure called explicitly after the DML.
- If the rule is a simple invariant, consider a constraint or a different data model.

Do not arbitrarily use an autonomous transaction to bypass a mutating table error. Doing so alters transaction semantics, can read inconsistent data, and introduces new logic bugs.

## 11. Compound Triggers: Sharing State Across Timing Points

A compound DML trigger allows declaring multiple timing sections within the same trigger body:

- BEFORE STATEMENT
- BEFORE EACH ROW
- AFTER EACH ROW
- AFTER STATEMENT

Variables declared in the shared declaration section are shared across sections during a single statement execution. This is a useful way to collect data from each row and then process it once after the statement finishes.

### 11.1. Example Collecting Department IDs

Suppose there is a summary table of employee counts per department:

~~~sql
CREATE TABLE department_headcount_summary (
    department_id NUMBER PRIMARY KEY,
    employee_count NUMBER NOT NULL,
    refreshed_at TIMESTAMP
);
~~~

A compound trigger collects the old/new department IDs of modified rows, then recalculates employee counts in AFTER STATEMENT:

~~~sql
CREATE OR REPLACE TRIGGER employees_headcount_ct
FOR INSERT OR UPDATE OR DELETE ON employees
COMPOUND TRIGGER

    TYPE t_dept_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_dept_ids t_dept_ids;
    g_count    PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF INSERTING OR UPDATING THEN
            IF :NEW.department_id IS NOT NULL THEN
                g_count := g_count + 1;
                g_dept_ids(g_count) := :NEW.department_id;
            END IF;
        END IF;

        IF DELETING OR UPDATING THEN
            IF :OLD.department_id IS NOT NULL THEN
                g_count := g_count + 1;
                g_dept_ids(g_count) := :OLD.department_id;
            END IF;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_employee_count NUMBER;
    BEGIN
        FOR i IN 1 .. g_count LOOP
            SELECT COUNT(*)
            INTO l_employee_count
            FROM employees
            WHERE department_id = g_dept_ids(i);

            MERGE INTO department_headcount_summary d
            USING (
                SELECT g_dept_ids(i) AS department_id,
                       l_employee_count AS employee_count
                FROM dual
            ) s
            ON (d.department_id = s.department_id)
            WHEN MATCHED THEN
                UPDATE SET
                    d.employee_count = s.employee_count,
                    d.refreshed_at = SYSTIMESTAMP
            WHEN NOT MATCHED THEN
                INSERT (department_id, employee_count, refreshed_at)
                VALUES (s.department_id, s.employee_count, SYSTIMESTAMP);
        END LOOP;
    END AFTER STATEMENT;

END employees_headcount_ct;
/
~~~

The example above illustrates moving the read operation on EMPLOYEES to AFTER STATEMENT to avoid querying a mutating table from AFTER EACH ROW. It may recalculate the same department multiple times if multiple rows belong to that department; in production implementations, deduplicate department IDs or group them into an appropriate collection/set to avoid redundant work.

The summary table must also be initialized in sync with existing data and have a concurrency strategy. If multiple transactions update the same department concurrently, evaluate locking and the correctness of summary maintenance.

### 11.2. A Compound Trigger Is Not Four Independent Triggers

The timing sections belong to the same trigger and share common state during a statement execution. It provides better lifecycle control when an algorithm needs information across multiple timing points.

A compound trigger is still subject to Oracle's trigger and transaction rules. Do not use it as a way to bypass constraints or turn all business logic into triggers.

## 12. Ordering Between Multiple Triggers

A table can have multiple triggers for the same event and timing point. Do not rely on the default execution order between triggers of the same type if that order has not been declared.

If trigger B depends on the outcome of trigger A, this design easily creates coupling. Better approaches:
- Consolidate dependent logic into the same trigger/package.
- Create a shared procedure for triggers to call in an explicit order.
- Use the FOLLOWS clause where supported by Oracle and verified for your version.
- Avoid deep trigger chains or triggers firing DML on each other.

The overall timing point order still applies: BEFORE STATEMENT before row processing, BEFORE EACH ROW before the row operation, AFTER EACH ROW after the row operation, and AFTER STATEMENT after all rows. However, the order among multiple triggers at the same timing point must be managed separately.

## 13. Triggers and MERGE

MERGE can execute UPDATE and INSERT branches depending on target row state. When MERGE fires triggers, you must test all DML branches actually used:
- Rows matching the condition and being UPDATEd.
- Rows not matching and being INSERTed.
- The DELETE branch if the MERGE syntax includes an appropriate DELETE clause.

Triggers attached to the corresponding INSERT/UPDATE/DELETE events may be invoked according to the operations performed. For statement-level triggers and multiple branches in MERGE, verify behavior against the documentation for your release and through actual testing; do not infer from a single standalone INSERT or UPDATE statement.

Do not rely on triggers to replace explicit MERGE logic. If you need exact row counts per branch or want to emit business events, consider an orchestrating API/package or an explicit recording mechanism.

## 14. Triggers on Views and INSTEAD OF Triggers

Standard BEFORE/AFTER DML triggers attach to tables. For views that cannot be updated directly in a manner supported by Oracle, you can use an INSTEAD OF trigger to define an alternative action when DML is applied to the view.

~~~sql
CREATE OR REPLACE TRIGGER order_view_insert
INSTEAD OF INSERT ON order_entry_view
FOR EACH ROW
BEGIN
    INSERT INTO orders (
        order_id,
        customer_id,
        status
    ) VALUES (
        :NEW.order_id,
        :NEW.customer_id,
        'NEW'
    );
END;
/
~~~

An INSTEAD OF trigger is a distinct type, typically row-level, that runs in place of direct DML on a view. Do not confuse INSTEAD OF with BEFORE or AFTER on a table.

## 15. Triggers, Constraints, and Application Logic

Triggers are a powerful tool, but they are not the first choice for every rule.

| Requirement | Mechanism to typically consider |
|---|---|
| Column must have a value | NOT NULL constraint |
| Value must fall within a valid domain | CHECK constraint |
| No duplicate keys | UNIQUE/PRIMARY KEY |
| Valid parent-child relationship | FOREIGN KEY |
| Simple input normalization before write | Application or BEFORE row trigger; consider datatype/default |
| Audit each modified row | AFTER row trigger or appropriate Oracle auditing |
| Record once per DML statement | AFTER statement trigger |
| Multi-step workflow called intentionally | Procedure/package |
| Sending emails, publishing messages | Application worker/outbox |
| Rule applying only to one interface | Application/service layer |

Declarative constraints are clearly visible in the schema, understood by the optimizer, and consistently enforced by the database. Triggers are suitable for reactions that constraints cannot express, though they increase DML complexity.


## 16. Transactions and COMMIT in Triggers

Regular triggers run inside the transaction that fired them. Therefore:

- A trigger must not COMMIT or ROLLBACK the main transaction.
- DML executed by the trigger participates in the same transaction.
- If a trigger raises an unhandled exception, the firing DML statement can fail and the statement's changes are rolled back according to Oracle's mechanism.
- The caller still decides whether to COMMIT or ROLLBACK the transaction after the statement completes.

Example:

~~~sql
CREATE OR REPLACE TRIGGER orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        event_name,
        event_time
    ) VALUES (
        :NEW.order_id,
        'CREATED',
        SYSTIMESTAMP
    );
END;
/
~~~

If the caller rolls back the transaction that created the order, the audit record also rolls back.

### 16.1. Autonomous Transactions in Triggers

You can declare an autonomous transaction in a trigger following Oracle's permitted rules, commonly used in certain independent logging scenarios. However, an autonomous transaction has its own transaction boundary:
- It can commit log entries even if the main DML rolls back.
- It does not see uncommitted changes of the main transaction as committed data.
- It can encounter locks or deadlocks if accessing data held by the main transaction.
- It should not be used to make a trigger always commit business changes.

Only use it when independent audit/logging requirements are clearly defined and tested. Do not use autonomous transactions to bypass mutating table errors or force the main DML to succeed.

## 17. Exceptions in Triggers

If a trigger raises an error, Oracle generally propagates the error back to the statement that fired the trigger. Example:

~~~sql
CREATE OR REPLACE TRIGGER orders_validate_amount
BEFORE INSERT OR UPDATE OF total_amount ON orders
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20110,
            'Order amount cannot be negative'
        );
    END IF;
END;
/
~~~

The application receives the Oracle error and can map it to a business error. If a trigger swallows exceptions with WHEN OTHERS THEN NULL, the caller may not know that part of the processing failed.

### 17.1. Do Not Swallow Errors Arbitrarily

Avoid:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

If additional context is needed, record the error using a designed mechanism and re-RAISE it. Be cautious with logging inside an autonomous transaction because it can persist even when the main transaction rolls back.

### 17.2. Triggers Causing DML Failure

If a trigger inserts into an audit table, and the audit table runs out of quota, lacks privileges, or violates a constraint, the main DML statement can fail. This is why triggers must be tested together with the real schema, privileges, tablespaces, and workload.

## 18. Trigger Administration: Viewing, Enabling, Disabling, and Compiling

Commonly used dictionary views:

- USER_TRIGGERS: triggers owned by the current schema.
- ALL_TRIGGERS: triggers the user has privileges to view.
- DBA_TRIGGERS: all triggers in the database, requiring appropriate privileges.
- USER_OBJECTS: object status.
- USER_ERRORS: compile errors for triggers and other stored objects.

### 18.1. Listing Triggers

~~~sql
SELECT trigger_name,
       table_name,
       triggering_event,
       trigger_type,
       status,
       when_clause
FROM user_triggers
ORDER BY table_name, trigger_name;
~~~

### 18.2. Viewing Compile Errors

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### 18.3. Enabling and Disabling

~~~sql
ALTER TRIGGER orders_before_insert DISABLE;
ALTER TRIGGER orders_before_insert ENABLE;
~~~

You can enable/disable all triggers on a table using ALTER TABLE per Oracle syntax:

~~~sql
ALTER TABLE orders DISABLE ALL TRIGGERS;
ALTER TABLE orders ENABLE ALL TRIGGERS;
~~~

Disabling triggers can prevent trigger-based normalization, auditing, or invariants from running. Only use this in maintenance procedures whose impact has been assessed and that include a plan to re-enable triggers and verify affected data.

### 18.4. Recompiling

~~~sql
ALTER TRIGGER orders_before_insert COMPILE;
~~~

After compiling, check STATUS in USER_TRIGGERS or USER_OBJECTS and inspect USER_ERRORS if the object remains INVALID. Do not treat a successful COMPILE command as proof that the trigger works correctly in business logic.

## 19. Performance and Operational Risks

Triggers execute on the DML path, so every cost incurred by a trigger adds to data manipulation time.

Common reasons triggers become slow:
- Row-level triggers executing multiple SELECT/DML statements per row.
- Calling expensive functions/procedures for every row.
- Re-querying the source table or related tables with unsuitable indexes.
- Auditing too many columns or large data volumes.
- Multi-layered trigger chains.
- Lock contention between main and auxiliary tables.
- Calling external services or performing long-running processing.
- Frequent exceptions/rollbacks caused by trigger logic.

### 19.1. Row-Level Triggers and Per-Row Cost

If an UPDATE statement affects 100,000 rows, a row-level trigger runs 100,000 times. Executing even one SELECT/DML inside each invocation can generate a large workload.

If you only need one aggregate operation after the statement, use a statement-level trigger or compound trigger to collect data and process it once.

### 19.2. Do Not Call External Services Directly

Do not have triggers call email services, HTTP endpoints, or message brokers on the main DML path. External services can be slow or fail, holding transactions and locks open longer, and they do not roll back with the Oracle transaction.

You can write events to an outbox table within the same transaction and have an application worker send them after COMMIT. The worker needs retry and idempotency mechanisms.

### 19.3. Do Not Create Triggers to Replace Every API

If the application needs a clear workflow, an explicitly called procedure/package is usually easier to read and test. Triggers should react to data events with a narrow scope, clear purpose, and no surprises for the caller.

## 20. DML Trigger Design Checklist

Before creating a trigger, determine:

1. Is the event INSERT, UPDATE, DELETE, or a combination?
2. Does the trigger need to run BEFORE or AFTER?
3. Does it need to run once per statement or per row?
4. Are :OLD/:NEW needed?
5. Do you need to assign :NEW? If so, it must be a BEFORE row trigger.
6. Is UPDATE OF checking the column in the SET list or an actual value change?
7. Is a WHEN condition needed? WHEN is only for row-level triggers.
8. Does the trigger query/modify the same mutating table?
9. Can a constraint or set-based SQL replace it?
10. Does the trigger write audits in the same transaction or require independent logging?
11. Could the trigger swallow exceptions or cause unexpected DML failures?
12. Are there multiple triggers at the same timing point with order dependencies?
13. Does it handle multi-row DML, zero-row statements, and MERGE?
14. Does it call external services or hold transactions too long?
15. Are privileges, dependencies, deployment, enable/disable, and rollback plans in place?

## 21. Controlled Hands-On Exercises

The exercises use the EMPLOYEES table if the sample schema is available. Otherwise, create a separate lab table in an authorized DEV/TEST schema. Do not create triggers on production business tables without an approved plan.

### 21.1. Creating the Lab Table

~~~sql
CREATE TABLE lab_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    employee_name VARCHAR2(100),
    salary NUMBER(12,2),
    created_at TIMESTAMP
);

INSERT ALL
    INTO lab_employees VALUES (1, 10, 'An', 1000, NULL)
    INTO lab_employees VALUES (2, 10, 'Binh', 1500, NULL)
    INTO lab_employees VALUES (3, 20, 'Chi', 2000, NULL)
SELECT 1 FROM dual;

COMMIT;
~~~

### Exercise 1 — BEFORE EACH ROW

Create a BEFORE INSERT trigger on LAB_EMPLOYEES:
- If created_at is NULL, assign the current timestamp.
- Normalize employee_name using TRIM.
- Do not COMMIT inside the trigger.

Insert a row missing created_at and verify the assigned value.

### Exercise 2 — AFTER EACH ROW

Create a separate audit table and an AFTER UPDATE OF salary trigger:
- Record employee_id.
- Record old and new salary.
- Record session user and timestamp.
- Test single-row UPDATE and multi-row UPDATE.

Count the audit rows to see that the row-level trigger runs per row.

### Exercise 3 — BEFORE STATEMENT and AFTER STATEMENT

Create a statement log table. Create two triggers:
- BEFORE UPDATE statement logging phase START.
- AFTER UPDATE statement logging phase END.

Run an UPDATE affecting multiple rows. Verify there are only two log rows for the two statement triggers.

### Exercise 4 — Statement Affecting Zero Rows

Run an UPDATE with a condition matching no rows. Verify that statement-level triggers still run, while row-level triggers do not.

### Exercise 5 — UPDATE OF and Actual Value Changes

Create an UPDATE OF salary trigger. Run:
- SET salary = salary.
- SET salary = salary + 100.

Observe that the trigger fires in both cases, but the :OLD/:NEW comparison condition only detects the actual change.

### Exercise 6 — Mutating Table

Create a row trigger that queries LAB_EMPLOYEES while updating that table. Observe error ORA-04091 in the lab environment. Then move the query part to AFTER STATEMENT or a compound trigger.

### Exercise 7 — Compound Trigger

Create a compound trigger that collects old/new department IDs in AFTER EACH ROW, then counts employees per department in AFTER STATEMENT. Cross-check the results with a direct GROUP BY query.

### Exercise 8 — Transaction Rollback

Perform an UPDATE that causes the trigger to write an audit record, then ROLLBACK. Check both the main data and the audit row. Explain why a regular trigger shares the same transaction as the DML statement.

### Exercise 9 — Exceptions

Create a trigger checking non-negative salary using RAISE_APPLICATION_ERROR. Try inserting/updating a negative salary and verify the DML statement is rejected. Compare with a CHECK constraint.

### Exercise 10 — Trigger Administration

Query USER_TRIGGERS, disable a lab trigger, perform DML to observe behavior, then re-enable it. Check STATUS and USER_ERRORS.

### Cleaning Up Lab Data

Only after confirming the objects are the ones you created in DEV/TEST and are not used by anyone else, disable/drop the lab triggers first and then drop the related tables. Example:

~~~sql
DROP TRIGGER lab_employees_before_insert;
DROP TRIGGER lab_employees_salary_audit;
DROP TABLE lab_employee_audit PURGE;
DROP TABLE lab_employees PURGE;
~~~

Adjust names to match the actual objects created. DDL in Oracle issues an implicit commit; do not run cleanup commands on objects outside the lab scope.


## 22. Review Questions

**Question 1.** What do BEFORE and AFTER describe?

**Answer:** When the trigger runs relative to the DML operation at the corresponding timing point.

**Question 2.** How does a row-level trigger differ from a statement-level trigger?

**Answer:** A row-level trigger has FOR EACH ROW and runs once for each affected row; a statement-level trigger runs once for the DML statement.

**Question 3.** If an UPDATE affects 100 rows, how many times does AFTER EACH ROW run?

**Answer:** 100 times.

**Question 4.** If an UPDATE affects zero rows, do statement triggers run?

**Answer:** Yes. Statement-level triggers run for the statement; row-level triggers do not run because no rows are processed.

**Question 5.** Where are :OLD and :NEW used?

**Answer:** In row-level triggers. Statement-level triggers do not have per-row pseudorecords.

**Question 6.** What can BEFORE EACH ROW do with :NEW?

**Answer:** It can assign values to :NEW fields before the row is written. It cannot assign to :OLD.

**Question 7.** Can AFTER EACH ROW modify :NEW?

**Answer:** No. If you need to normalize the stored value, use BEFORE EACH ROW or handle it in the DML statement.

**Question 8.** What does UPDATE OF salary check?

**Answer:** Whether the salary column appears in the SET list; it does not guarantee that the salary value actually changed.

**Question 9.** Which triggers use the WHEN clause?

**Answer:** Row-level triggers. In the WHEN clause, NEW/OLD are referenced without a colon.

**Question 10.** What is ORA-04091 mutating table?

**Answer:** An error raised when a row-level trigger queries or modifies a table currently being mutated by DML in a context Oracle does not permit.

**Question 11.** How do compound triggers help?

**Answer:** They allow sharing state across timing points, such as collecting data in EACH ROW and then processing the table after the statement to avoid mutating table errors.

**Question 12.** Does an AFTER trigger run after COMMIT?

**Answer:** No. AFTER means after the row or statement operation, still within the transaction; the caller commits or rolls back afterward.

**Question 13.** Can a regular trigger issue COMMIT?

**Answer:** A regular trigger cannot commit or roll back the main transaction. Autonomous transactions are a separate mechanism and require careful consideration of semantics.

**Question 14.** Why should you not send emails directly inside a trigger?

**Answer:** Email is an external side effect outside the Oracle transaction; it could be sent even if the transaction rolls back, or it can slow down or fail the DML. Use an outbox and a post-commit worker.

**Question 15.** When should you use a constraint instead of a trigger?

**Answer:** When the rule can be expressed with NOT NULL, CHECK, UNIQUE, PRIMARY KEY, or FOREIGN KEY. Constraints are transparent and directly enforced by the database.

**Question 16.** Can you assume the execution order between two triggers at the same timing point?

**Answer:** You should not. If ordering is required, consolidate logic or use FOLLOWS where supported and verified for your version.

## Conclusion

BEFORE/AFTER determines when a trigger runs; row-level/statement-level determines whether the scope is a single row or the entire DML statement. BEFORE EACH ROW is suitable for validating and normalizing :NEW; AFTER EACH ROW is suitable for recording changes using :OLD/:NEW; BEFORE STATEMENT and AFTER STATEMENT run once per statement and do not have per-row pseudorecords.

With multi-row DML, row triggers run per row while statement triggers run once, even when the statement affects zero rows. You must distinguish UPDATE OF from actual value changes, use WHEN within its proper scope, avoid querying a mutating table from a row trigger, and consider compound triggers when you need to collect per-row data and process it after the statement. Regular triggers run inside the firing transaction, must not commit on their own, and can cause DML to fail if they raise errors. Prefer constraints for simple invariants, keep triggers small and observable, avoid calling external services directly, and test with multi-row DML, rollbacks, exceptions, and concurrency.

## Oracle References

- [Oracle Database 19c PL/SQL Language Reference — DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): timing points, row/statement triggers, :OLD/:NEW, WHEN, and compound triggers.
- [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): trigger creation syntax.
- [Oracle Database 19c Error Messages — ORA-04091](https://docs.oracle.com/en/error-help/db/ora-04091/): causes and resolution of mutating table errors.
- [Oracle Database 19c Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): trigger metadata in the current schema.
