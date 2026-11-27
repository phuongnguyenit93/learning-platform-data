# Row-Level Triggers and Limitations Compared to Statement-Level Triggers

A trigger is a stored program automatically invoked by MySQL when an INSERT, UPDATE, or DELETE event occurs on a table. A critical point in MySQL is that triggers always execute at the row level: every affected row fires the corresponding trigger. MySQL does not support statement-level triggers—triggers that execute only once for an entire SQL statement.

This distinction directly affects audit design, data validation, summary table updates, and the performance of multi-row write commands. This lesson in the DATABASE_MYSQL module helps you understand FOR EACH ROW, OLD/NEW, BEFORE/AFTER, trigger invocation counts, MySQL trigger limitations, and ways to structure logic that must run once for an entire statement.

## 1. What Is a Row-Level Trigger?

A row-level trigger is declared with FOR EACH ROW. When a DML statement affects multiple rows, the trigger body executes separately for each row.

Example:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

If the UPDATE affects 200 rows, the corresponding BEFORE UPDATE or AFTER UPDATE trigger may be invoked 200 times, each bound to a single row. The trigger receives the old and new values of the current row through OLD and NEW.

If the statement affects no rows, no row trigger invocations occur. If the statement inserts 500 rows via INSERT ... SELECT, the INSERT trigger runs once per inserted row.

Row-level triggers suit tasks that must process individual records:

- Normalizing or validating values before writing.
- Writing audits for each row's changes.
- Maintaining a secondary table dependent on each row's values.
- Enforcing data rules regardless of which application performs the write.

## 2. MySQL Does Not Support Statement-Level Triggers

Some database management systems provide two types of triggers:

- Row-level trigger: runs once for each affected row.
- Statement-level trigger: runs once for the entire DML statement, regardless of how many rows the statement affects.

MySQL only supports row-level triggers. The CREATE TRIGGER syntax requires FOR EACH ROW; there is no FOR EACH STATEMENT option.

| Scenario | Row-level trigger in MySQL | Statement-level trigger |
|---|---|---|
| UPDATE affects 1 row | Runs once | If supported, runs once |
| UPDATE affects 200 rows | Runs 200 times | If supported, still runs once |
| UPDATE matches 0 rows | Does not run | On systems supporting statement triggers, it may still run once |
| INSERT ... SELECT inserts 500 rows | Runs for 500 inserted rows | If supported, runs once |
| Need all rows before/after statement | Only sees OLD/NEW of each row | Some systems support transition tables or statement context |

You cannot replace FOR EACH ROW with another syntax to create a statement trigger in MySQL. If business logic must run once for the entire command, place that step in a stored procedure or the application layer orchestrating the DML.

## 3. CREATE TRIGGER Syntax

General syntax:

~~~sql
CREATE
    [DEFINER = user]
    TRIGGER trigger_name
    trigger_time trigger_event
    ON table_name
    FOR EACH ROW
    trigger_body;
~~~

Where:

- trigger_time is BEFORE or AFTER.
- trigger_event is INSERT, UPDATE, or DELETE.
- table_name is the table the trigger is attached to.
- FOR EACH ROW specifies the trigger is called for each row.
- trigger_body is typically a single statement or a BEGIN ... END block.

Simple trigger example:

This example assumes the employees table already exists according to the structure in section 6; create the table before running CREATE TRIGGER.

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_bi_validate
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

DELIMITER is a MySQL client command used to change the statement terminator when sending a trigger definition containing multiple semicolons. The server receives the complete CREATE TRIGGER statement; DELIMITER is not a server SQL statement.

## 4. How Do BEFORE and AFTER Differ?

MySQL supports two activation timings:

- BEFORE: runs before the row operation is applied.
- AFTER: runs after the row operation has been performed successfully.

Supported events:

| Event | BEFORE | AFTER | Meaning |
|---|---|---|---|
| INSERT | Yes | Yes | Before or after adding a row |
| UPDATE | Yes | Yes | Before or after modifying a row |
| DELETE | Yes | Yes | Before or after deleting a row |

BEFORE is commonly used to validate or normalize data about to be written. AFTER is commonly used to record audits or update other tables based on changes that have occurred.

AFTER does not mean the transaction has COMMITted. The trigger still runs in the context of the active statement and transaction. If the transaction rolls back, transactional changes made by the trigger also roll back.

## 5. OLD and NEW by Event Type

OLD and NEW are two pseudo-records for referencing a row's values:

| Event | OLD | NEW |
|---|---|---|
| INSERT | Not available | Row about to be inserted or just inserted |
| UPDATE | Value before update | Value after update |
| DELETE | Row about to be deleted or just deleted | Not available |

Example with UPDATE:

~~~sql
IF OLD.salary <> NEW.salary THEN
    -- Salary changed.
END IF;
~~~

For INSERT, do not read OLD because there is no row prior to insertion. For DELETE, do not read NEW because no new row exists. Referencing an invalid pseudo-record for the corresponding event causes an error during trigger creation or execution.

OLD is read-only. In BEFORE INSERT and BEFORE UPDATE, a trigger can assign values to NEW.column to modify the row to be written. You cannot assign OLD.column and cannot modify NEW in an AFTER trigger.

## 6. Assigning NEW in a BEFORE Trigger

Suppose the source table has the following structure:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(120) NOT NULL,
    department_id INT NOT NULL,
    employment_status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE=InnoDB;
~~~

Example normalizing employee names and setting the update timestamp:

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_bi_normalize
BEFORE INSERT ON employees
FOR EACH ROW
BEGIN
    SET NEW.employee_name = TRIM(NEW.employee_name);

    IF NEW.employee_name IS NULL OR NEW.employee_name = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Employee name is required';
    END IF;

    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

CREATE TRIGGER trg_employees_bu_normalize
BEFORE UPDATE ON employees
FOR EACH ROW
BEGIN
    SET NEW.employee_name = TRIM(NEW.employee_name);
    SET NEW.updated_at = CURRENT_TIMESTAMP(6);

    IF NEW.employee_name IS NULL OR NEW.employee_name = '' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Employee name is required';
    END IF;

    IF NEW.salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Salary cannot be negative';
    END IF;
END//

DELIMITER ;
~~~

In BEFORE INSERT, NEW contains the values supplied by the application or initial default values. If the table uses AUTO_INCREMENT, the NEW value of the auto-increment column may still be 0 in BEFORE INSERT; do not rely on it to obtain the final ID. In AFTER INSERT, the generated AUTO_INCREMENT value can be read via NEW.

If data normalization is needed, define clear rules consistent with collations, data types, and application-layer validation. Triggers should not silently transform data according to rules unknown to the caller.

## 7. OLD/NEW for Row-by-Row Auditing

Audit triggers are a classic example of row-level behavior. Each time a row changes, the trigger writes a corresponding history record.

Create the audit table:

~~~sql
CREATE TABLE employee_salary_audit (
    audit_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_id BIGINT UNSIGNED NOT NULL,
    old_salary DECIMAL(12,2) NOT NULL,
    new_salary DECIMAL(12,2) NOT NULL,
    changed_at DATETIME(6) NOT NULL,
    connection_user VARCHAR(288) NOT NULL,
    PRIMARY KEY (audit_id),
    KEY idx_salary_audit_employee_time (employee_id, changed_at)
) ENGINE=InnoDB;
~~~

Create the AFTER UPDATE trigger:

~~~sql
DELIMITER //

CREATE TRIGGER trg_employees_au_salary_audit
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    IF NOT (OLD.salary <=> NEW.salary) THEN
        INSERT INTO employee_salary_audit (
            employee_id,
            old_salary,
            new_salary,
            changed_at,
            connection_user
        )
        VALUES (
            OLD.employee_id,
            OLD.salary,
            NEW.salary,
            CURRENT_TIMESTAMP(6),
            USER()
        );
    END IF;
END//

DELIMITER ;
~~~

The <=> operator is MySQL's null-safe comparison operator. It returns TRUE when two values are equal, even if both are NULL; the expression NOT (OLD.salary <=> NEW.salary) is true only when the two values differ. In this example salary is NOT NULL, but null-safe comparison makes the logic pattern clearer when applied to nullable columns.

USER() records the session's connection account. A trigger executes under the DEFINER's privilege context; CURRENT_USER() inside a trigger reflects the DEFINER account, not necessarily the end application user. If you need to record a business actor such as the employee performing the action, the application should pass the actor through a controlled data contract rather than inferring it from DEFINER.

## 8. How Many Times Does a Multi-Row Statement Invoke a Trigger?

Consider the statement:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;
~~~

If 75 rows belonging to department 10 are updated, the corresponding BEFORE UPDATE and AFTER UPDATE triggers fire for each processed row. The trigger does not run once for the whole UPDATE statement.

This can be visualized as:

~~~mermaid
flowchart TD
    A[UPDATE employees WHERE department_id = 10] --> B[MySQL processes first row]
    B --> C[BEFORE UPDATE trigger]
    C --> D[Apply row change]
    D --> E[AFTER UPDATE trigger]
    E --> F{More matching rows?}
    F -->|Yes| B
    F -->|No| G[Finish UPDATE statement]
~~~

If the same UPDATE command affects 75 rows, the trigger body runs 75 times for each matching trigger. If there are two triggers with the same timing/event, both run for each row in their defined order.

This can cause a seemingly simple DML command to generate many secondary operations. An audit trigger will insert 75 audit rows; a trigger maintaining a summary table may perform correspondingly many additional reads/writes.

## 9. Testing with Multi-Row INSERT

With:

~~~sql
INSERT INTO employees (
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES
    ('An', 10, 'ACTIVE', 1200.00),
    ('Binh', 10, 'ACTIVE', 1500.00),
    ('Chi', 20, 'ACTIVE', 1300.00);
~~~

BEFORE INSERT and AFTER INSERT triggers are invoked for each inserted row. A trigger can inspect NEW for each row and reject invalid rows with SIGNAL.

If a trigger raises an error while the statement is inserting multiple rows, the statement can fail. With InnoDB, statement changes and transactional operations performed by the trigger are rolled back together. Do not assume non-transactional engines provide the same guarantee.

INSERT ... SELECT and LOAD DATA can also fire INSERT triggers for each added row. Bulk inserts do not turn row triggers into statement triggers.

## 10. Verifying Row-Level Triggers via Auditing

After creating the audit trigger, run:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT
    employee_id,
    old_salary,
    new_salary,
    changed_at
FROM employee_salary_audit
ORDER BY audit_id;
~~~

If three employees in department 10 are updated and salary changes for all three, the audit table will contain three records. If the WHERE clause matches no rows, the trigger does not run and no new audit records are created.

You can count audit records before and after a test operation to confirm per-row execution counts. When testing, use transactions and dedicated test data so business audits are not polluted.

Note: the AFTER UPDATE trigger in the example only writes an audit when salary changes. If an UPDATE only changes status or another column, the trigger is still called for each row, but the IF condition does not insert a salary audit.

## 11. Why Doesn't MySQL Have Transition Tables for Statement Triggers?

Statement-level triggers in some DBMSs can access the old/new row sets of the entire statement through transition tables or equivalent constructs. This enables computing an aggregate change once after DML finishes.

MySQL row triggers only provide OLD and NEW for the current row. They do not provide a virtual table containing all rows affected by the statement for batch processing inside the trigger.

Therefore, you cannot write a MySQL trigger saying "after UPDATE, sum all changed rows exactly once" using statement-level syntax. If aggregation is needed, consider:

- A set-based SQL statement running after the DML inside the same stored procedure.
- The application orchestrating the DML and aggregation operation inside the same transaction.
- A staging table holding the affected key set, then processing that set with a single SQL statement.
- An asynchronous synchronization mechanism if business requirements allow eventual consistency.

Choose an approach based on consistency requirements, data scale, and control over the write path.

## 12. Executing Logic Once for an Entire Statement

If the application can call a stored procedure instead of sending arbitrary DML, the procedure can group operations into one unit:

~~~sql
CREATE TABLE department_change_log (
    log_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id INT NOT NULL,
    increase_amount DECIMAL(12,2) NOT NULL,
    department_total DECIMAL(14,2) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    PRIMARY KEY (log_id)
) ENGINE=InnoDB;

DELIMITER //

CREATE PROCEDURE increase_department_salary(
    IN p_department_id INT,
    IN p_increase DECIMAL(12,2)
)
BEGIN
    DECLARE v_department_total DECIMAL(14,2) DEFAULT 0.00;

    UPDATE employees
    SET salary = salary + p_increase
    WHERE department_id = p_department_id;

    SELECT COALESCE(SUM(salary), 0.00)
    INTO v_department_total
    FROM employees
    WHERE department_id = p_department_id;

    INSERT INTO department_change_log (
        department_id,
        increase_amount,
        department_total,
        recorded_at
    )
    VALUES (
        p_department_id,
        p_increase,
        v_department_total,
        CURRENT_TIMESTAMP(6)
    );
END//

DELIMITER ;
~~~

The UPDATE still fires row triggers for each employee. The INSERT into department_change_log runs only once inside the procedure. This is how to achieve business-level/statement-level behavior using explicit logic rather than a statement-level trigger.

If the procedure must ensure UPDATE and log succeed or fail together, clearly define transaction ownership. The procedure can run inside a caller-managed transaction or manage transactions according to a designed contract; never arbitrarily COMMIT a transaction owned by the caller.

## 13. Row Trigger Performance

Trigger cost scales linearly with the number of rows. Even a simple per-row trigger can create significant overhead when DML affects hundreds of thousands of rows.

For example, updating one million rows can result in:

- One million invocations of BEFORE UPDATE.
- One million invocations of AFTER UPDATE.
- One million audit INSERTs if the audit condition holds.
- Many additional constraint checks, index updates, and log writes.

Optimization principles:

1. Keep triggers short, avoiding unnecessary repeated queries.
2. Only write audits when tracked values actually change.
3. Create appropriate indexes for secondary queries inside triggers.
4. Avoid calling stored procedures or performing heavy calculations per row when set-based processing can be used.
5. Avoid triggers that produce unpredictable chains of secondary writes.
6. Measure DML duration with triggers enabled versus an equivalent environment without secondary logic.
7. Test with realistic batch sizes, not just a single row.

Do not use triggers to update a summary table via per-row SELECT-then-UPDATE if changes can be grouped and totals updated once in a procedure or job.

## 14. Important Limitations When Writing MySQL Triggers

Triggers are stored programs, but they have specific restrictions:

- Cannot return a result set to the client. You can use SELECT ... INTO to assign variables, but cannot use a standalone SELECT to return data from a trigger.
- Cannot use START TRANSACTION, COMMIT, or ROLLBACK to manage transactions inside a trigger.
- Cannot modify a table already used by the statement that fired the trigger. For instance, an UPDATE on employees firing a trigger that also runs UPDATE on employees will fail.
- Cannot invoke triggers directly with CALL; triggers only fire via the corresponding DML event.
- No OLD in INSERT and no NEW in DELETE.
- Cannot assign NEW in an AFTER trigger.
- No FOR EACH STATEMENT or transition tables.

If a trigger needs to modify data, it usually writes to another table. For example, an audit trigger INSERTs into employee_salary_audit when the original statement UPDATEs employees. Avoid creating unbounded write loops across multiple triggers.

## 15. Cannot Update the Table Used by the Triggering Statement

A common mistake is creating an AFTER UPDATE trigger on employees and then running UPDATE on employees inside the trigger:

~~~sql
-- Anti-pattern illustration; do not create this trigger.
CREATE TRIGGER trg_employees_au_bad
AFTER UPDATE ON employees
FOR EACH ROW
BEGIN
    UPDATE employees
    SET updated_at = CURRENT_TIMESTAMP
    WHERE employee_id = NEW.employee_id;
END;
~~~

MySQL does not allow a trigger or stored function invoked by a trigger to modify a table already used by the statement that fired the trigger. A common error is 1442. To fix this, assign NEW.updated_at in a BEFORE UPDATE trigger:

~~~sql
CREATE TRIGGER trg_employees_bu_timestamp
BEFORE UPDATE ON employees
FOR EACH ROW
SET NEW.updated_at = CURRENT_TIMESTAMP(6);
~~~

This matches the intended purpose of BEFORE triggers: modifying row values before MySQL writes them.

## 16. Ordering When Multiple Triggers Share Event and Timing

MySQL allows multiple triggers attached to the same table, event, and timing in modern versions (since MySQL 5.7.2). When multiple triggers exist, the default order is creation order. You can specify relative ordering using FOLLOWS or PRECEDES when creating a new trigger.

Example:

~~~sql
CREATE TRIGGER trg_employees_bi_audit_context
BEFORE INSERT ON employees
FOR EACH ROW
FOLLOWS trg_employees_bi_normalize
BEGIN
    -- Additional logic before the row is inserted.
    SET NEW.created_at = COALESCE(
        NEW.created_at,
        CURRENT_TIMESTAMP(6)
    );
END;
~~~

FOLLOWS/PRECEDES only defines relative order among triggers on the same table, event, and timing. If execution order carries business meaning, document it explicitly in the design and verify ACTION_ORDER in metadata.

Do not split tightly coupled logic into multiple triggers merely to create smaller units. One larger trigger with clear sequence can be easier to maintain than a chain of interdependent triggers.

## 17. Operations That Do Not Fire Triggers Like Regular DML

Triggers do not monitor every physical table change. Certain operations do not fire the corresponding triggers:

- TRUNCATE TABLE does not fire DELETE triggers.
- DROP TABLE does not run DELETE triggers for each row before dropping the table.
- Foreign key cascade actions such as ON DELETE CASCADE or ON UPDATE CASCADE do not fire triggers on rows affected by the cascade.

If the system relies on triggers to audit row deletions, do not assume TRUNCATE or foreign key cascades will produce audit records. Control DDL privileges, use intentional DML operations, or design auditing at another layer for those change paths.

## 18. Transactions and Errors in Triggers

With InnoDB, triggers execute synchronously in the same statement and transaction as the DML operation that fired them. If a trigger writes an audit to an InnoDB table and the statement fails, transactional changes within the statement roll back.

Example:

~~~sql
START TRANSACTION;

UPDATE employees
SET salary = salary + 100
WHERE employee_id = 101;

-- Check audit within the same transaction.
SELECT *
FROM employee_salary_audit
WHERE employee_id = 101
ORDER BY audit_id DESC;

ROLLBACK;
~~~

After ROLLBACK, both the salary change and the audit row created by the trigger are reverted if both tables use InnoDB and no non-transactional actions occurred. If a table uses a non-transactional engine, there is no equivalent rollback guarantee for changes on that table.

A trigger can use SIGNAL to reject data:

~~~sql
IF NEW.salary < 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Salary cannot be negative';
END IF;
~~~

When a trigger raises an error, the DML statement fails. With InnoDB, statement changes roll back; the transaction caller may need to ROLLBACK depending on the error and handling policy. Do not treat triggers as places to COMMIT or ROLLBACK transactions themselves.

## 19. Definer and Execution Privileges

Triggers have a DEFINER. Statements inside the trigger execute under the definer's security context. The account creating the trigger needs the TRIGGER privilege on the attached table and the privileges required for operations inside the trigger.

This matters when deploying across environments:

- The DEFINER account must exist or be handled appropriately on the target server.
- The definer needs minimum privileges to execute the SELECT/INSERT/UPDATE statements required by the trigger.
- Do not grant broader privileges just to make a trigger work.
- Verify SHOW CREATE TRIGGER and metadata after migrations.

CURRENT_USER() inside a trigger reflects the trigger's security account (DEFINER). USER() reflects the connecting account. These two values serve different purposes; pick the right one if recording audits.

## 20. Inspecting and Managing Triggers

List triggers:

~~~sql
SHOW TRIGGERS FROM app_db;
~~~

View a specific definition:

~~~sql
SHOW CREATE TRIGGER app_db.trg_employees_au_salary_audit;
~~~

Query metadata:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_ORDER,
    DEFINER,
    SQL_MODE
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA = 'app_db'
ORDER BY EVENT_OBJECT_TABLE, EVENT_MANIPULATION, ACTION_TIMING, ACTION_ORDER;
~~~

These columns help determine which table, event, timing, order, and definer a trigger belongs to. When a trigger causes write errors, check the definition, the SQL_MODE stored when the trigger was created, and definer privileges.

Drop a trigger:

~~~sql
DROP TRIGGER IF EXISTS app_db.trg_employees_au_salary_audit;
~~~

DROP TRIGGER is DDL. Deploy trigger changes through reviewed migrations, preserve existing definitions, and assess impact on write paths before applying.

## 21. When Is Statement-Level Logic Needed?

If a business requirement needs one-time processing for an entire DML statement, do not try to simulate it with session variables inside a row trigger. Choose a mechanism with an explicit statement context:

| Need | Suitable Design Approach |
|---|---|
| Validate each row before writing | BEFORE row trigger or constraint |
| Audit old/new values per row | AFTER row trigger |
| Write one log per request/batch | Application service or stored procedure |
| Recompute totals after updating many rows | A single aggregate/set-based query after DML |
| Process the set of affected keys | Staging table followed by set-based processing |
| Emit events to external systems | Transactional outbox or appropriate messaging mechanism |

Session variables like @statement_id do not create a statement trigger. Connection pools may reuse sessions, multiple statements may share a connection, and mid-execution errors can leave stale state behind. If a correlation ID is needed, pass it explicitly through a procedure or write it to an outbox table within a transaction with a clear contract.

## 22. Row Trigger Design Workflow

1. Identify the event (INSERT, UPDATE, or DELETE) and timing (BEFORE/AFTER).
2. Determine whether the logic truly belongs per row or to the whole statement.
3. Check which columns are read from OLD and NEW based on the event.
4. Choose BEFORE if you need to assign NEW or reject a row before writing.
5. Choose AFTER if you need to record audits or reflect applied changes.
6. Keep the trigger short and avoid updating the table that fired it.
7. Use SIGNAL for invalid data conditions.
8. Ensure source and audit tables use a transactional engine if atomic rollback is required.
9. Test behavior when DML affects 0, 1, and many rows.
10. Check whether bulk operations, TRUNCATE, and foreign key cascades bypass the trigger.
11. Verify DEFINER, privileges, and ordering if multiple triggers share the event/timing.
12. Measure performance with representative batch sizes and document additional overhead.

## 23. Practice Exercises

1. Create the employees table and a BEFORE INSERT trigger to TRIM employee_name and reject empty names.
2. Create a BEFORE UPDATE trigger to assign updated_at and reject negative salary.
3. Create the employee_salary_audit table and an AFTER UPDATE trigger that writes only when salary changes.
4. Run UPDATEs affecting one row, multiple rows, and zero rows; count the corresponding audit records.
5. Run a multi-row INSERT and confirm the trigger is called once per inserted row.
6. Test SIGNAL in a BEFORE trigger and confirm the DML does not write invalid data.
7. Try updating employees from a trigger attached to employees in a test environment; read the error and replace it with assigning NEW in BEFORE UPDATE.
8. Perform an UPDATE inside a transaction and then ROLLBACK; confirm both the source row and InnoDB audit row revert to their prior state.
9. Create a procedure that updates salaries for a department and writes one batch log row; distinguish the single log write from multiple row trigger invocations.
10. Inspect SHOW CREATE TRIGGER and INFORMATION_SCHEMA.TRIGGERS; note event, timing, definer, and action order.
11. Try TRUNCATE on a test table with a DELETE trigger; confirm the DELETE trigger is not invoked.
12. Write an explanation of why MySQL cannot create FOR EACH STATEMENT triggers and propose how to handle once-per-batch logic.

You have completed this lesson when you can explain why MySQL only has row-level triggers, accurately predict how many times a trigger runs for multi-row DML, use OLD/NEW correctly by event and timing, and choose stored procedures or the application layer for logic that must run once at the statement level. Good trigger design accounts for transactions, definer privileges, and per-row overhead.
