# Execution Order, Nested Triggers, and Unintended Side Effects

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Exceptions and Triggers  
> **Objective:** Understand DML trigger execution order in Oracle; distinguish statement-level and row-level triggers; control ordering among multiple triggers at the same timing point; identify nested triggers, recursion, and mutating-table errors; use compound triggers when per-row processing must be combined with statement-level aggregation; understand transactions, exceptions, and side effects; diagnose trigger behavior via the data dictionary; and establish a safe testing workflow.

## 1. Why Can Triggers Cause Unintended Behavior?

A trigger is PL/SQL code automatically invoked by Oracle when an event occurs on a table, view, schema, or database. For DML triggers, the event is typically `INSERT`, `UPDATE`, or `DELETE`.

A seemingly simple statement:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 100;
~~~

can invoke multiple pieces of code:

1. `BEFORE STATEMENT` trigger on `ORDERS`.
2. `BEFORE EACH ROW` trigger for the updated row.
3. DML modifying the row.
4. `AFTER EACH ROW` trigger for that row.
5. `AFTER STATEMENT` trigger on `ORDERS`.
6. Triggers on other tables if an earlier trigger executes `INSERT`/`UPDATE`/`DELETE`.
7. Subsequent triggers along the resulting DML chain.

Thus, the actual impact of a DML statement can be much broader than the visible SQL. An audit trigger might fire triggers on the audit table; a status-sync trigger might modify another table; a trigger on the target table might update the source table back.

Without understanding execution order and transaction boundaries, systems can suffer from:

- Data updated multiple times or in an unexpected order.
- Triggers calling each other, forming hard-to-trace DML chains.
- `ORA-04091` from accessing a mutating table.
- `ORA-04088` when an error occurs during trigger execution.
- A primary statement failing because an auxiliary trigger failed.
- Audits or external notifications failing to reflect true commit outcomes.
- Unpredictable performance as one DML statement spawns many additional SQL statements.

The key lesson is to treat triggers as part of the execution path and transaction, not isolated code running "at the end."

## 2. DML Trigger Timing Points

Oracle supports four main timing points for table DML triggers:

- `BEFORE STATEMENT`
- `BEFORE EACH ROW`
- `AFTER EACH ROW`
- `AFTER STATEMENT`

A single DML statement can fire triggers at multiple timing points. Statement-level triggers run once per statement; row-level triggers run once per affected row.

### 2.1. Basic Order of an UPDATE Statement

Suppose an `UPDATE` affects three rows and all four trigger types exist:

~~~text
UPDATE ... (one statement)
        |
        v
BEFORE STATEMENT trigger
        |
        v
For each affected row:
    BEFORE EACH ROW trigger
        |
        v
    Oracle performs the row modification
        |
        v
    AFTER EACH ROW trigger
        |
        v
Repeat for the next row
        |
        v
AFTER STATEMENT trigger
        |
        v
Statement completes if no errors occur
~~~

If the statement affects three rows:

- `BEFORE STATEMENT` runs once.
- `BEFORE EACH ROW` runs three times.
- `AFTER EACH ROW` runs three times.
- `AFTER STATEMENT` runs once.

Row-processing order is not guaranteed merely because a table has a primary key or queries appear to return rows in a familiar sequence. Never build business logic assuming row-level triggers always run in `ROWID`, index, or prior `INSERT` order.

### 2.2. Statement-Level Triggers Run Even When No Rows Match

An `UPDATE` statement might match zero rows:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = -1;
~~~

If the table has an applicable statement-level trigger, that trigger still fires because the statement executed. Row-level triggers do not run because no rows were affected.

This matters for statement-count auditing, batch tracking, or start/end checks. Never assume statement-level triggers only run when `SQL%ROWCOUNT` is greater than 0.

### 2.3. Row-Level Triggers Only Run When Rows Are Affected

A trigger with `FOR EACH ROW` is called for each row actually affected by the DML:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_row
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

If an `UPDATE` modifies 100 rows, the trigger body can run 100 times. This generates 100 audit `INSERT`s along with the cost of indexes, constraints, and any triggers on `ORDER_AUDIT`.

### 2.4. BEFORE and AFTER Serve Different Purposes

| Timing Point | Common Purpose |
|---|---|
| `BEFORE STATEMENT` | Statement-wide checks or state initialization |
| `BEFORE EACH ROW` | Normalize or assign `:NEW`; validate each row before writing |
| `AFTER EACH ROW` | Record row changes; processing needing `:OLD`/`:NEW` after row DML |
| `AFTER STATEMENT` | Aggregate processing after all rows of the statement are processed |

With a `BEFORE EACH ROW` trigger on a table, you can assign values to `:NEW` on `INSERT` or `UPDATE`. Example setting creation timestamp:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.created_at IS NULL THEN
        :NEW.created_at := SYSTIMESTAMP;
    END IF;
END;
/
~~~

Do not assign `:NEW` inside an `AFTER EACH ROW` trigger. If values must be modified before saving, use `BEFORE EACH ROW` or perform the adjustment in application-layer DML.

## 3. :OLD, :NEW, and Event Detection Predicates

In a row-level DML trigger, Oracle provides the `:OLD` and `:NEW` pseudorecords:

| Operation | :OLD | :NEW |
|---|---|---|
| `INSERT` | No old row values (fields are `NULL`) | Row about to be inserted |
| `UPDATE` | Values before change | New values |
| `DELETE` | Row being deleted | No new row values (fields are `NULL`) |

Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:NEW.order_id, 'INSERT', SYSTIMESTAMP);

    ELSIF UPDATING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:NEW.order_id, 'UPDATE', SYSTIMESTAMP);

    ELSIF DELETING THEN
        INSERT INTO order_audit(order_id, action_name, changed_at)
        VALUES (:OLD.order_id, 'DELETE', SYSTIMESTAMP);
    END IF;
END;
/
~~~

The `INSERTING`, `UPDATING`, and `DELETING` predicates let the trigger identify which DML event fired it.

### 3.1. UPDATE OF column Does Not Mean the Value Necessarily Changed

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_salary_update
BEFORE UPDATE OF salary ON employees
FOR EACH ROW
BEGIN
    DBMS_OUTPUT.PUT_LINE('SALARY is in the SET list');
END;
/
~~~

The trigger is evaluated whenever an `UPDATE` includes `SALARY` in the `SET` list. For example:

~~~sql
UPDATE employees
SET salary = salary
WHERE employee_id = 100;
~~~

`SALARY` is still listed in `SET` even though before and after values are identical. Hence, `UPDATE OF SALARY` does not imply the salary value actually changed.

If you only want to react when the value actually differs, compare `:OLD` and `:NEW`. For nullable columns, handle `NULL` explicitly:

~~~sql
IF (:OLD.salary IS NULL AND :NEW.salary IS NOT NULL)
   OR (:OLD.salary IS NOT NULL AND :NEW.salary IS NULL)
   OR (:OLD.salary <> :NEW.salary)
THEN
    -- Value actually changed
    NULL;
END IF;
~~~

You can use `DECODE` to compare two values under `DECODE`'s `NULL` semantics, but choose whichever expression is clearest and fits the data types.

### 3.2. WHEN Clause

A row trigger can use a `WHEN` clause to run the trigger body only when a condition holds:

~~~sql
CREATE OR REPLACE TRIGGER trg_large_order
AFTER INSERT ON orders
FOR EACH ROW
WHEN (NEW.total_amount >= 10000)
BEGIN
    INSERT INTO large_order_alert(order_id, created_at)
    VALUES (:NEW.order_id, SYSTIMESTAMP);
END;
/
~~~

In the `WHEN` clause, pseudorecord references omit the colon; in the trigger body, use `:NEW` and `:OLD`.

The `WHEN` clause applies only to row-level triggers. Keep the condition concise and clear; if logic is complex, move it into the trigger body or a called package.

## 4. Multiple Triggers at the Same Timing Point: Ordering Can Be Nondeterministic

A table can have multiple triggers for the same event and timing point—for example, two `BEFORE INSERT FOR EACH ROW` triggers both modifying data.

Unless an ordering relationship supported by Oracle is explicitly declared, never rely on trigger creation order or trigger names to infer which trigger runs first. Execution order among triggers at the same timing point can be nondeterministic.

For instance, never assume a trigger named `NORMALIZE` always runs before a trigger named `VALIDATE`. Object names and `CREATE` timestamps are not execution-order contracts.

### 4.1. Design to Be Order-Independent

Ideally, each trigger should be as independent as possible. If multiple actions must coordinate at the same timing point, consider:

- Merging logic into a single trigger in an explicit sequence.
- Calling package procedures in an explicit sequence.
- Separating validation, normalization, and auditing so they do not overwrite one another.
- Using constraints for data rules expressible as constraints.

Example of an orchestrating trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_bir
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    order_rules.normalize_new_order(:NEW);
    order_rules.validate_new_order(:NEW);
    order_rules.set_default_priority(:NEW);
END;
/
~~~

This is a design sketch; the called procedures must have signatures compatible with passing `:NEW` records or be implemented using individual column parameters. The purpose is to make the call sequence explicit in one place.

### 4.2. FOLLOWS to Specify Order

Oracle supports the `FOLLOWS` clause in qualifying DML trigger cases to specify that one trigger runs after another at the corresponding timing point.

Example of two `BEFORE INSERT` row triggers:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_normalize
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    :NEW.order_code := UPPER(TRIM(:NEW.order_code));
END;
/

CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
FOLLOWS trg_orders_normalize
BEGIN
    IF :NEW.order_code IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'ORDER_CODE is required');
    END IF;
END;
/
~~~

`FOLLOWS` indicates that `TRG_ORDERS_VALIDATE` must follow `TRG_ORDERS_NORMALIZE` within Oracle's supported scope.

Limitations to remember:

- `FOLLOWS` does not turn triggers at different timing points into an arbitrary chain.
- The referenced trigger must exist and satisfy ordering compatibility conditions.
- With compound triggers, ordering applies to the matching timing sections; missing sections can limit ordering.
- Exact capabilities and syntax details depend on the Oracle release.

Consult the SQL Language Reference for your running version before deploying. When ordering is essential to business rules, a single orchestrating trigger is usually easier to control and maintain than multiple interdependent triggers.

### 4.3. Do Not Use Trigger Ordering as an Implicit Business Contract

Even when `FOLLOWS` works, avoid building a long trigger web where trigger A depends on B, B depends on C, and C modifies data that A already validated. Such dependency chains are hard to debug and easily broken when new triggers are added or timing points change.

Express business workflows with procedures/services containing explicit calls whenever possible.

## 5. Nested Triggers and Recursive Triggers

Nested/cascading triggers occur when a trigger executes DML on another table, and that DML fires another trigger.

Example:

~~~text
UPDATE ORDERS
   |
   v
TRG_ORDERS_AFTER_UPDATE
   |
   +-- INSERT ORDER_AUDIT
             |
             v
       TRG_AUDIT_AFTER_INSERT
             |
             +-- UPDATE CUSTOMER_SUMMARY
                       |
                       v
                 TRG_CUSTOMER_SUMMARY
~~~

A single `UPDATE` on `ORDERS` can trigger multiple DML statements and additional triggers. These operations typically remain within the original statement's transaction.

### 5.1. Nested Triggers vs. Self-Calling Recursive Triggers

- **Cascading trigger:** a trigger on table A modifies table B; a trigger on B modifies table C.
- **Recursive trigger:** a trigger directly or indirectly causes DML that fires that same trigger again.

For example, a trigger on `CUSTOMERS` updating `CUSTOMERS` again can create a loop or hit mutating-table restrictions depending on how it accesses the table.

Not every trigger chain is a bug. However, chains need clear termination points, must avoid redundant repeated updates, and must remain traceable.

### 5.2. Example of a Valid Trigger Chain with Hidden Cost

Audit trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_audit
AFTER UPDATE ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

If `ORDER_AUDIT` has a trigger performing validation or writing further audit rows, that trigger also fires. An `UPDATE` of 10,000 rows can generate 10,000 `INSERT`s into `ORDER_AUDIT` and fire 10,000 more row triggers on the audit table.

Account for the cost of the entire chain, not just the initial SQL statement.

### 5.3. Avoiding Trigger Loops

A dangerous example:

- Trigger A after `UPDATE` on table A updates table B.
- Trigger B after `UPDATE` on table B updates table A.
- Trigger A fires again, then B fires again.

To prevent loops:

- Avoid bidirectional update relationships unless truly required.
- Check for actual value changes before issuing downstream DML.
- Design unidirectional synchronization flows.
- Move synchronization into an orchestrating procedure/service instead of triggers firing each other.
- Use idempotent operations: repeated runs do not corrupt data further.
- Do not rely solely on global package flags to mask loops; flags can fail to reset on exceptions or create confusing behavior.

Oracle enforces a limit on trigger cascade depth. Designs exceeding the limit raise runtime errors; never treat this limit as an architectural guardrail to rely upon.

## 6. Mutating Tables and ORA-04091

A common error when writing row-level triggers occurs when the trigger queries or modifies the very table being modified by the DML statement.

Example where `EMPLOYEES` has an after-each-row `UPDATE` trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_check
AFTER UPDATE OF salary ON employees
FOR EACH ROW
DECLARE
    l_avg_salary NUMBER;
BEGIN
    SELECT AVG(salary)
    INTO l_avg_salary
    FROM employees
    WHERE department_id = :NEW.department_id;

    IF :NEW.salary > l_avg_salary * 3 THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Salary exceeds department threshold'
        );
    END IF;
END;
/
~~~

During an `UPDATE` on `EMPLOYEES`, the table is mutating for row-level triggers. Querying `EMPLOYEES` again inside the trigger can raise:

~~~text
ORA-04091: table ... is mutating, trigger/function may not see it
~~~

Oracle prevents row-level triggers from observing a table mid-change in potentially inconsistent ways.

### 6.1. Why Does the Error Occur?

In a multi-row `UPDATE`, Oracle processes rows in row-level steps. When one row's trigger queries the whole table, some rows have changed while others have not; the intermediate result does not represent the completed state of the statement.

If the trigger uses that result to make decisions, behavior depends on row-processing order and becomes inconsistent. The mutating-table restriction prevents this approach.

### 6.2. Changing AFTER to BEFORE Does Not Solve It

Switching the trigger from `AFTER EACH ROW` to `BEFORE EACH ROW` does not remove the underlying issue: the trigger is still a row-level trigger on the table being modified.

Nor should you use an autonomous transaction to dodge `ORA-04091`. An autonomous transaction does not turn a mid-change state into a consistent snapshot and creates an independent transaction with its own side effects.

## 7. Compound Triggers for Statement-Level Data Processing

A compound DML trigger groups multiple timing sections into one trigger and shares PL/SQL state throughout a single DML statement.

Sections can include:

- `BEFORE STATEMENT`
- `BEFORE EACH ROW`
- `AFTER EACH ROW`
- `AFTER STATEMENT`

Not every section is required. The shared declarative section can hold collections or variables used across sections.

A common technique:

1. In `AFTER EACH ROW`, only collect keys or data needed for checks into a collection.
2. Once all rows are processed, `AFTER STATEMENT` runs.
3. In `AFTER STATEMENT`, query the table after row-level processing completes and validate the aggregated data.
4. On violation, raise an exception so the original statement fails.

Illustrative example collecting department IDs:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_salary_check
FOR UPDATE OF salary ON employees
COMPOUND TRIGGER

    TYPE dept_id_list_t IS TABLE OF employees.department_id%TYPE
        INDEX BY PLS_INTEGER;

    g_department_ids dept_id_list_t;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        IF :NEW.department_id IS NOT NULL THEN
            g_count := g_count + 1;
            g_department_ids(g_count) := :NEW.department_id;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_avg_salary NUMBER;
    BEGIN
        FOR i IN 1 .. g_count LOOP
            SELECT AVG(salary)
            INTO l_avg_salary
            FROM employees
            WHERE department_id = g_department_ids(i);

            -- Illustrative example: check aggregate rules
            -- after the statement has processed all rows.
            NULL;
        END LOOP;
    END AFTER STATEMENT;

END trg_employee_salary_check;
/
~~~

In production code, deduplicate department IDs before querying to avoid repeating the same check multiple times. An associative array used as a set or a suitable collection can handle deduplication.

The key point: `AFTER STATEMENT` runs after the statement's row-level changes, so it is no longer subject to the row-trigger mutating restriction when querying that table.

### 7.1. Compound Triggers Share State Within a Single Statement

Variables declared in the declarative section belong to a single compound-trigger invocation. They are shared across timing sections for that statement and expire when the statement ends.

Do not treat these variables as persistent state across multiple SQL statements or sessions. Each session and each statement has its own context.

### 7.2. Use Compound Triggers Selectively

Compound triggers fit when coordinating row-level capture with statement-level processing. There is no need to use them for every trigger.

If you only need to assign defaults before `INSERT`, a `BEFORE EACH ROW` trigger is simpler. If you only need per-row audit inserts, `AFTER EACH ROW` may suffice.

## 8. Triggers Across Multiple Tables and Ordering Across Statements

A trigger can perform DML on another table:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
FOR EACH ROW
BEGIN
    UPDATE customer_summary
    SET order_count = order_count + 1
    WHERE customer_id = :NEW.customer_id;
END;
/
~~~

If `CUSTOMER_SUMMARY` has a trigger, that trigger is fired by the resulting `UPDATE`.

### 8.1. Do Not Assume Row Ordering

If an `INSERT ... SELECT` inserts rows for multiple customers, the row-level trigger is invoked in Oracle's internal processing order. Never use triggers to assign business sequence numbers relying on that implicit order.

If ordering is required, generate sequence numbers with a sequence or process the dataset with `ORDER BY` in a separate step with a clear contract.

### 8.2. Avoid Unsafe Read-Modify-Write Counter Updates

A trigger can increment a counter:

~~~sql
UPDATE customer_summary
SET order_count = order_count + 1
WHERE customer_id = :NEW.customer_id;
~~~

The addition executes in SQL and Oracle locks the matching row appropriately, which is safer than selecting the counter into a PL/SQL variable, incrementing it, and updating an absolute value. Still, many orders for the same customer can contend on a single summary row and create a hotspot.

Consider:

- Building summaries in batches or via materialized views where suitable.
- Using data structures built for write concurrency.
- Evaluating the cost of updating a single counter row per order.
- Measuring row lock waits and throughput.

## 9. MERGE and Triggers

`MERGE` can perform `UPDATE` for matched rows and `INSERT` for unmatched rows; some syntax forms also include `DELETE` for updated rows matching a condition.

Example:

~~~sql
MERGE INTO customers t
USING customer_stage s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_name = s.customer_name
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name)
    VALUES (s.customer_id, s.customer_name);
~~~

Triggers associated with the actual operations performed by `MERGE` can fire:

- Updated rows fire corresponding `UPDATE` triggers.
- Inserted rows fire corresponding `INSERT` triggers.
- If a `DELETE` clause is present and rows are deleted, corresponding `DELETE` triggers can fire.

Do not write code assuming `MERGE` fires only one type of trigger. Test both matched and not-matched branches, as well as the `DELETE` clause if used.

`MERGE` remains a single statement; both statement-level and row-level triggers must be evaluated according to the DML operations executed. If triggers depend on ordering or aggregated state, compound triggers and orchestrated designs may be required.

## 10. Triggers, Constraints, and Validation

Not every data rule should be implemented with a trigger.

Use constraints when rules can be expressed directly:

- `NOT NULL` for required columns.
- `CHECK` for single-row conditions.
- `UNIQUE`/`PRIMARY KEY` for uniqueness.
- `FOREIGN KEY` for referential integrity.

Example:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT ck_orders_total
CHECK (total_amount >= 0);
~~~

Constraints are usually clearer than triggers, understood by the optimizer and database as integrity metadata, and prevent duplicating validation logic in multiple places.

Triggers may fit when you need to:

- Write per-change audit logs.
- Assign or normalize values according to specialized rules.
- Coordinate logic that cannot be expressed with constraints.
- Maintain auxiliary data intentionally.
- Reject operations via `RAISE_APPLICATION_ERROR`.

### 10.1. Triggers Are Not Safe Solutions for All Cross-Row Rules

If a trigger queries a table to verify "no duplicate rows exist" before allowing an `INSERT`, multiple concurrent sessions can all observe zero existing rows and all insert. This is a race condition unless proper locking or constraints are in place.

Use `UNIQUE` constraints/indexes to protect uniqueness. Use proper transactions and locking for rules requiring synchronization. Triggers can supplement logic; they do not replace concurrency control.

## 11. Transactions and Errors in Triggers

DML executed by a trigger normally belongs to the same transaction as the DML statement that fired the trigger.

Example:

1. Session runs `UPDATE ORDERS`.
2. Trigger inserts into `ORDER_AUDIT`.
3. Trigger updates `CUSTOMER_SUMMARY`.
4. Statement completes.
5. Caller runs `COMMIT`.

If the caller rolls back the transaction, changes to `ORDERS`, `ORDER_AUDIT`, and `CUSTOMER_SUMMARY` within that transaction are all rolled back.

### 11.1. Errors in Triggers Cause the Original Statement to Fail

Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'TOTAL_AMOUNT cannot be negative'
        );
    END IF;
END;
/
~~~

When an `INSERT` has a negative `TOTAL_AMOUNT`, the error returns to the caller and the `INSERT` fails.

If the trigger already executed some DML before raising an unhandled error, changes belonging to that statement are rolled back by Oracle under statement atomicity. Earlier successful statements in the transaction can still remain pending; never infer that a trigger error automatically rolls back the entire transaction.

### 11.2. ORA-04088 Is the Wrapper Error

When an error occurs during trigger execution, Oracle may report `ORA-04088` alongside the root error:

~~~text
ORA-04088: error during execution of trigger ...
ORA-20020: TOTAL_AMOUNT cannot be negative
~~~

`ORA-04088` indicates trigger execution failed; read the underlying error and trigger PL/SQL line to find the cause.

### 11.3. Do Not COMMIT/ROLLBACK Inside a Normal Trigger

Triggers execute within the transaction of the triggering statement. Never call `COMMIT` or `ROLLBACK` directly inside a normal trigger. Attempting to do so can raise `ORA-04092`.

Transaction ownership should belong to the caller/service or a clearly designed workflow. Triggers must not decide on their own to commit partial business data.

## 12. Autonomous Transactions and External Side Effects

Some triggers call procedures declared with `PRAGMA AUTONOMOUS_TRANSACTION`. An autonomous transaction has its own transaction context and can `COMMIT` independently.

This example illustrates the behavior only:

~~~sql
CREATE OR REPLACE PROCEDURE write_independent_log (
    p_message IN VARCHAR2
) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO independent_log(message, created_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END;
/
~~~

A trigger can call that procedure. If the original statement later rolls back, the row in `INDEPENDENT_LOG` still remains because it committed in an independent transaction.

### 12.1. Why Can This Become an Unintended Side Effect?

Suppose a trigger logs `"ORDER CREATED"` via an autonomous transaction, yet the `INSERT` into `ORDERS` subsequently fails and rolls back. The independent log still records `ORDER CREATED` even though the order does not exist.

This can be useful for certain diagnostic logs, but is inappropriate for business audits that must accurately reflect committed data.

Other risks:

- An autonomous transaction can deadlock if it tries to access resources locked by the parent transaction.
- Callers may observe logs reporting an uncommitted event.
- Parent transaction failures do not roll back already committed autonomous data.
- Log data can drift out of sync with business state.

Use autonomous transactions only when independent semantics are intentional and documented.

### 12.2. Calling Email, HTTP, or Message Brokers from Triggers

A network call does not participate in an Oracle transaction in a way that can roll back. For example, if a trigger sends an email and the statement later fails, the email has still been sent.

Never call external services synchronously inside business triggers when notifications must only be sent after the transaction commits successfully.

### 12.3. Transactional Outbox

A safer pattern:

1. The trigger or application writes an event row into an `OUTBOX` table in the same transaction as the business DML.
2. If the statement/transaction rolls back, the outbox row rolls back as well.
3. After `COMMIT`, a separate worker reads unsent events.
4. The worker sends the message/email to the external system.
5. The worker updates status and retries with bounded attempts.
6. Consumers handle messages idempotently to tolerate duplicate deliveries.

Example table:

~~~sql
CREATE TABLE event_outbox (
    event_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_id NUMBER NOT NULL,
    event_type VARCHAR2(50) NOT NULL,
    payload CLOB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

A trigger can insert events into `OUTBOX` and a worker processes them post-commit. In larger systems, the application service can write directly to the outbox in the same transaction so business flow is clearer than hidden triggers.

## 13. Compound Triggers and Mutating Table Handling Example

A more concrete example requires checking a department's total salary after updating one or more employees. A row trigger must not query `EMPLOYEES` while the table is mutating.

We can collect department IDs and run the check in `AFTER STATEMENT`.

~~~sql
CREATE OR REPLACE TRIGGER trg_check_dept_salary
FOR UPDATE OF salary ON employees
COMPOUND TRIGGER

    TYPE dept_set_t IS TABLE OF BOOLEAN
        INDEX BY VARCHAR2(100);

    g_dept_set dept_set_t;

    AFTER EACH ROW IS
        l_key VARCHAR2(100);
    BEGIN
        IF :NEW.department_id IS NOT NULL THEN
            l_key := TO_CHAR(:NEW.department_id);
            g_dept_set(l_key) := TRUE;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        l_key VARCHAR2(100);
        l_total_salary NUMBER;
    BEGIN
        l_key := g_dept_set.FIRST;

        WHILE l_key IS NOT NULL LOOP
            SELECT SUM(salary)
            INTO l_total_salary
            FROM employees
            WHERE department_id = TO_NUMBER(l_key);

            -- Perform validation or update summary here.
            -- Avoid redundant repeated DML.
            l_key := g_dept_set.NEXT(l_key);
        END LOOP;
    END AFTER STATEMENT;

END trg_check_dept_salary;
/
~~~

This example uses an associative array as a key set to deduplicate; in real systems, choose key types matching your column data types, formatting, and conversion rules. If department ID is `NUMBER`, you can use a numeric-indexed collection with custom deduplication or an SQL collection type. The goal here is illustrating collection in the row section and querying after the statement.

Do not copy examples into production without testing data types, nullability, row volumes, performance, and validation semantics. If `AFTER STATEMENT` raises an error, the original statement fails and its changes are rolled back.

## 14. Diagnosing Triggers and Execution Order

When a DML statement produces unexpected side effects, inspect triggers on the table before modifying application code.

### 14.1. Listing Triggers in a Schema

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       table_name,
       status,
       action_type
FROM user_triggers
ORDER BY table_name, trigger_name;
~~~

These columns show whether each trigger is statement/row, which event it handles, which table it belongs to, and whether it is `ENABLED` or `DISABLED`.

### 14.2. Viewing Triggers for a Specific Table

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       status,
       when_clause
FROM user_triggers
WHERE table_name = 'ORDERS'
ORDER BY trigger_name;
~~~

Do not infer execution order from `ORDER BY trigger_name`. The query merely sorts names; firing order across multiple triggers at the same timing point is not alphabetical.

### 14.3. Viewing Columns Monitored by UPDATE OF Triggers

~~~sql
SELECT trigger_name,
       table_name,
       column_name,
       column_list,
       column_usage
FROM user_trigger_cols
WHERE table_name = 'EMPLOYEES'
ORDER BY trigger_name, column_name;
~~~

This view helps check which columns a trigger is attached to.

### 14.4. Viewing Compilation Errors

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

If a trigger is `INVALID` or fails compilation, inspect all errors and source lines. Across schemas, DBAs can use `ALL_TRIGGERS`/`DBA_TRIGGERS` and `ALL_ERRORS`/`DBA_ERRORS` according to privileges.

### 14.5. Viewing Trigger Source

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'TRG_ORDERS_AUDIT'
  AND type = 'TRIGGER'
ORDER BY line;
~~~

You can use `DBMS_METADATA.GET_DDL` to extract trigger DDL when authorized:

~~~sql
SELECT DBMS_METADATA.GET_DDL(
    'TRIGGER',
    'TRG_ORDERS_AUDIT',
    USER
)
FROM dual;
~~~

### 14.6. Enabling, Disabling, and Compiling

~~~sql
ALTER TRIGGER trg_orders_audit DISABLE;
ALTER TRIGGER trg_orders_audit ENABLE;
ALTER TRIGGER trg_orders_audit COMPILE;
~~~

Disabling a trigger can stop auditing or validation during that window. Only disable under controlled procedures, understand what data changes happen while disabled, and reconcile afterward upon re-enabling.

## 15. Practice: Observing Statement and Row Trigger Order

Use a dedicated lab schema.

### 15.1. Create Tables and Log Table

~~~sql
CREATE TABLE lab_trigger_orders (
    order_id NUMBER PRIMARY KEY,
    amount NUMBER NOT NULL,
    status VARCHAR2(20)
);

CREATE TABLE lab_trigger_log (
    log_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    trigger_name VARCHAR2(50),
    timing_point VARCHAR2(30),
    order_id NUMBER,
    logged_at TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

### 15.2. Create BEFORE STATEMENT

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_before_stmt
BEFORE UPDATE ON lab_trigger_orders
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_BEFORE_STMT', 'BEFORE STATEMENT', NULL
    );
END;
/
~~~

### 15.3. Create BEFORE EACH ROW

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_before_row
BEFORE UPDATE ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_BEFORE_ROW', 'BEFORE EACH ROW', :OLD.order_id
    );
END;
/
~~~

### 15.4. Create AFTER EACH ROW

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_after_row
AFTER UPDATE ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_AFTER_ROW', 'AFTER EACH ROW', :NEW.order_id
    );
END;
/
~~~

### 15.5. Create AFTER STATEMENT

~~~sql
CREATE OR REPLACE TRIGGER lab_orders_after_stmt
AFTER UPDATE ON lab_trigger_orders
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDERS_AFTER_STMT', 'AFTER STATEMENT', NULL
    );
END;
/
~~~

### 15.6. Insert Data and Run a Multi-Row UPDATE

~~~sql
INSERT INTO lab_trigger_orders VALUES (1, 100, 'NEW');
INSERT INTO lab_trigger_orders VALUES (2, 200, 'NEW');
INSERT INTO lab_trigger_orders VALUES (3, 300, 'NEW');
COMMIT;

UPDATE lab_trigger_orders
SET status = 'CHECKED'
WHERE order_id IN (1, 2, 3);

SELECT trigger_name,
       timing_point,
       order_id,
       logged_at
FROM lab_trigger_log
ORDER BY log_id;

COMMIT;
~~~

Observations:

- `BEFORE STATEMENT` has one log entry.
- `BEFORE EACH ROW` has three log entries.
- `AFTER EACH ROW` has three log entries.
- `AFTER STATEMENT` has one log entry.

Do not treat `LOG_ID` ordering across rows as a business contract. It simply records the order observed in that specific lab run.

### 15.7. UPDATE Matching Zero Rows

~~~sql
UPDATE lab_trigger_orders
SET status = 'NONE'
WHERE order_id = -1;

SELECT trigger_name, timing_point, order_id
FROM lab_trigger_log
ORDER BY log_id;

ROLLBACK;
~~~

Statement-level triggers still create log entries; row-level triggers create none because no rows matched.

## 16. Practice: Nested Triggers

Create an auxiliary table:

~~~sql
CREATE TABLE lab_trigger_summary (
    order_id NUMBER PRIMARY KEY,
    status VARCHAR2(20)
);

CREATE OR REPLACE TRIGGER lab_log_after_insert
AFTER INSERT ON lab_trigger_log
FOR EACH ROW
BEGIN
    NULL;
END;
/
~~~

Example trigger on `ORDERS` inserting an audit row:

~~~sql
CREATE OR REPLACE TRIGGER lab_order_insert_audit
AFTER INSERT ON lab_trigger_orders
FOR EACH ROW
BEGIN
    INSERT INTO lab_trigger_log(
        trigger_name, timing_point, order_id
    )
    VALUES (
        'LAB_ORDER_INSERT_AUDIT', 'AFTER INSERT', :NEW.order_id
    );
END;
/
~~~

If `LAB_TRIGGER_LOG` has another trigger performing downstream DML, the trigger chain continues. Add triggers one at a time, check the number of generated DML statements, and avoid creating unbounded loops.

After testing, roll back the transaction and clean up lab objects when no longer needed.

## 17. Common Errors and Effects

| Error / Impact | Common Cause | Resolution |
|---|---|---|
| `ORA-04091` | Row trigger queries/updates mutating table | Use compound trigger or move processing to statement-level |
| `ORA-04088` | Error occurred during trigger execution | Read root error and trigger line number |
| `ORA-04092` | Trigger attempted `COMMIT`/`ROLLBACK` | Let caller manage transaction |
| `ORA-04098` | Trigger invalid and revalidation/recompile failed on fire | Inspect `USER_ERRORS`, compile source and dependencies |
| `ORA-04084` | Assigning `:NEW` in an `AFTER` row trigger | Move assignment to `BEFORE` row |
| `ORA-04082` | `NEW`/`OLD` disallowed in statement trigger | Use pseudorecords only in row-level triggers |
| Trigger runs many times | Row-level trigger runs once per row | Check DML row count and timing point |
| Unstable execution order | Relying on unguaranteed trigger/row order | Use `FOLLOWS` where appropriate or consolidate logic |
| Audit data persists after rollback | Autonomous transaction or external side effect | Use same transaction/outbox when consistency is required |
| Unusually slow DML | Long trigger chains and excessive auxiliary DML | Measure entire chain, reduce row-by-row work |
| Infinite trigger loop | A updates B, B updates A back | Eliminate circular dependencies, ensure idempotency |
| `MERGE` triggers more actions than expected | Both `INSERT`/`UPDATE`/`DELETE` branches have triggers | Test each `MERGE` branch |

An error code is only the starting point. Inspect trigger source, call stack, the triggering SQL, and transaction state.

## 18. Principles for Designing Controllable Triggers

### 18.1. Keep Triggers Short

Triggers should perform small tasks with clear names and purposes. When logic grows long, call independently testable package procedures.

### 18.2. Do Not Hide Transaction Boundaries

Triggers must not `COMMIT` on their own. Callers need to know which changes belong to the same transaction and when they become durable.

### 18.3. Prefer Constraints for Integrity

Whenever a rule can use `CHECK`, `UNIQUE`, `PK`, `FK`, or `NOT NULL`, prefer the constraint. Triggers should handle only logic that constraints cannot express.

### 18.4. Do Not Trigger Non-Rollbackable Side Effects

Emails, HTTP requests, or messages sent directly inside a trigger escape transaction rollback. Use a transactional outbox or an appropriate post-commit mechanism.

### 18.5. Avoid Deep Trigger Chains

A DML statement should have an easily explainable execution path. A trigger on an audit table should never modify business tables back in ways that create unpredictable loops.

### 18.6. Test Both Statement and Row Semantics

Test DML affecting 0, 1, and many rows; `INSERT`, `UPDATE`, `DELETE`; `UPDATE OF`; `MERGE`; exceptions; rollbacks; and concurrent sessions.

### 18.7. Monitor Overall Performance

Measure elapsed time, logical reads, redo, audit row counts, auxiliary DML counts, wait events, and locks. Never benchmark only the top-level SQL statement while ignoring trigger cost.

## 19. Pre-Deployment Trigger Checklist

- [ ] Confirm whether the trigger is statement-level or row-level.
- [ ] Confirm `BEFORE`/`AFTER`/`INSTEAD OF` is appropriate.
- [ ] Know whether the trigger runs once or once per row.
- [ ] Do not rely on implicit ordering among multiple triggers at the same timing point.
- [ ] If using `FOLLOWS`, verify trigger/timing compatibility and Oracle release.
- [ ] Do not rely on row-level processing order.
- [ ] Verify `:OLD`/`:NEW` usage matches `INSERT`/`UPDATE`/`DELETE`.
- [ ] Use `BEFORE` row if assigning `:NEW`.
- [ ] Never query a mutating table from a row-level trigger.
- [ ] Use a compound trigger when collecting per-row data for post-statement processing.
- [ ] Trace trigger chains and potential recursion paths.
- [ ] Ensure repeated operations are idempotent or have clear stop conditions.
- [ ] Never `COMMIT`/`ROLLBACK` in normal triggers.
- [ ] Clearly understand autonomous transactions and external side effects.
- [ ] Use an outbox for events that must be sent post-commit.
- [ ] Test all `INSERT`/`UPDATE`/`DELETE` branches when using `MERGE`.
- [ ] Check `USER_TRIGGERS`, `USER_TRIGGER_COLS`, and `USER_ERRORS`.
- [ ] Test 0, 1, and many rows; rollbacks and exceptions.
- [ ] Measure the entire DML/trigger chain before deploying to production.

## 20. Key Takeaways

- A single DML statement can activate multiple timing points and nested triggers.
- The basic execution order is `BEFORE STATEMENT`, `BEFORE EACH ROW`, row modification, `AFTER EACH ROW`, then `AFTER STATEMENT`.
- Statement-level triggers run once per matching statement even when zero rows are affected; row-level triggers run only for rows actually processed.
- Never rely on creation order or names of multiple triggers at the same timing point; use `FOLLOWS` where supported or consolidate logic into an orchestrating trigger.
- `:OLD` and `:NEW` are only meaningful in row-level triggers; `:NEW` can be assigned in `BEFORE EACH ROW`.
- `UPDATE OF column` only indicates the column appeared in the `SET` list, not that its value actually changed.
- Nested triggers occur when a trigger executes DML that fires other triggers; circular dependencies must be eliminated.
- `ORA-04091` occurs when a row-level trigger accesses a mutating table; compound triggers can collect data in row sections and process it in `AFTER STATEMENT`.
- Normal DML triggers run inside the triggering transaction; trigger errors cause the triggering statement to fail and roll back its changes.
- Autonomous transactions and external side effects can survive rollbacks; use them deliberately, preferring a transactional outbox for post-commit events.
- Use constraints for integrity rules expressible as constraints; keep triggers short and testable.
- Inspect metadata, source, compilation errors, call stacks, and the entire trigger chain when investigating unexpected behavior.

### Official Oracle Documentation to Cross-Check

- [Oracle Database PL/SQL Language Reference — DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html) — Timing points, row/statement triggers, `:OLD`/`:NEW`, trigger ordering, and compound triggers.
- [Oracle Database PL/SQL Language Reference — Compound DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html) — Compound trigger sections, shared state, and mutating-table workarounds.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, statement-level atomicity, locks, and read consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — `CREATE TRIGGER`, `FOLLOWS`, `MERGE`, and DML semantics.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — `USER_TRIGGERS`, `USER_TRIGGER_COLS`, `USER_ERRORS`, and `USER_SOURCE`.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_METADATA`, `DBMS_ASSERT`, and transaction utilities.

Trigger ordering, compound trigger restrictions, `MERGE` firing details, and certain online/runtime behaviors depend on the Oracle release. Verify against documentation for your exact version and test 0/1/n-row scenarios, rollbacks, exceptions, nested triggers, and concurrent DML in a lab schema before deploying.
