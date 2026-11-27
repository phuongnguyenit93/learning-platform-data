# INSTEAD OF Triggers for Modifying Data Through Views in Oracle

## 1. Why Do We Need INSTEAD OF Triggers?

A view is a logical object defined by a `SELECT` query. Users can query data from a view just like a table, but the ability to perform `INSERT`, `UPDATE`, and `DELETE` through a view depends on the query structure defining the view.

A simple view based on a single table is often automatically updatable. Conversely, views containing complex `JOIN`s, `UNION`, `DISTINCT`, `GROUP BY`, aggregate functions, or expressions may not permit direct DML under Oracle's updatable-view rules.

When an application still wants to interact with a unified view interface, Oracle provides **INSTEAD OF triggers**. This trigger executes in place of the DML operation issued against the view. The trigger body decides which underlying base tables to `INSERT`, `UPDATE`, or `DELETE` and under which rules.

~~~text
Application
   |
   | INSERT / UPDATE / DELETE
   v
EMPLOYEE_DIRECTORY_V (view)
   |
   | INSTEAD OF trigger
   v
PL/SQL mapping logic
   |
   +------> EMPLOYEES
   |
   +------> DEPARTMENTS (if business rules require)
~~~

`INSTEAD OF` triggers are useful when:

- A view joins multiple tables yet the application needs a unified DML entry point.
- A view uses `UNION` or other non-inherently-updatable structures.
- Displayed data is aggregated/transformed and needs custom update rules.
- A single operation on the view must map to multiple DML statements across base tables.
- You want to keep a stable SQL interface while physical storage becomes more complex.

Crucially, the trigger does not infer business logic automatically. Designers must explicitly define what each `INSERT`, `UPDATE`, and `DELETE` on the view means for the base tables.

> Content targets Oracle Database 19c. Examples assume privileges to create views/triggers and required DML privileges on base tables. An `INSTEAD OF` trigger replaces DML on a view; carefully verify security, constraints, transactions, and semantics before deploying to production.

## 2. Updatable Views and Direct DML Limits

### 2.1. Simple Views Can Be Inherently Updatable

Example:

~~~sql
CREATE OR REPLACE VIEW active_employees_v AS
SELECT employee_id,
       first_name,
       last_name,
       department_id
FROM employees
WHERE department_id = 50;
~~~

The view selects columns directly from a single table. Under qualifying conditions, Oracle can permit:

~~~sql
UPDATE active_employees_v
SET last_name = 'SMITH'
WHERE employee_id = 100;
~~~

Oracle maps the `UPDATE` automatically to the `EMPLOYEES` table. An `INSTEAD OF` trigger is unnecessary if the view is inherently updatable and the DML does not violate view restrictions.

### 2.2. Complex Views May Not Be Updatable

Certain constructs typically prevent direct modification under updatable-view rules:

- Set operators such as `UNION`, `UNION ALL`, `INTERSECT`, or `MINUS`.
- `DISTINCT`.
- Aggregate functions such as `SUM`, `COUNT`, `AVG`, `MIN`, or `MAX`.
- `GROUP BY` or `HAVING`.
- Certain expressions, subqueries, or analytic functions in the select list.
- Certain `JOIN` forms that do not satisfy key-preserved table rules.
- Hierarchical constructs or `MODEL`.

Aggregate view example:

~~~sql
CREATE OR REPLACE VIEW department_salary_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary
FROM employees
GROUP BY department_id;
~~~

A statement like:

~~~sql
UPDATE department_salary_v
SET average_salary = 5000
WHERE department_id = 50;
~~~

has no unique natural mapping down to individual `EMPLOYEES` rows. Business rules are needed to decide how each employee's salary should change. An `INSTEAD OF` trigger allows coding that rule if the operation has a well-defined meaning.

### 2.3. Join Views and Key-Preserved Tables

For `JOIN` views, Oracle evaluates the concept of a **key-preserved table**. A table is considered key-preserved in a join if every key of that table still uniquely identifies at most one row in the join result under the join conditions.

Example:

~~~sql
CREATE OR REPLACE VIEW employee_department_v AS
SELECT e.employee_id,
       e.last_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

If `EMPLOYEES` has primary key `EMPLOYEE_ID` and `DEPARTMENTS` has primary key `DEPARTMENT_ID`, each employee joins with at most one department. However, automatic updatability still depends on which table is key-preserved, which columns are updated, and Oracle's join-view rules.

Oracle may permit DML on one key-preserved table in certain cases, but does not allow arbitrarily updating multiple tables through a single direct DML statement. An `INSTEAD OF` trigger enables defining an explicit mapping.

### 2.4. Checking Column Updatability

You can inspect metadata via `USER_UPDATABLE_COLUMNS`:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'EMPLOYEE_DEPARTMENT_V'
ORDER BY column_id;
~~~

The `UPDATABLE`, `INSERTABLE`, and `DELETABLE` columns indicate direct DML capability according to view metadata. If the view has an `INSTEAD OF` trigger, actual DML behavior is handled by the trigger.

## 3. How INSTEAD OF Triggers Work

### 3.1. Meaning of INSTEAD OF

When an application runs DML on a view that has an `INSTEAD OF` trigger, Oracle fires the trigger instead of performing automatic DML on the view.

Example:

~~~sql
INSERT INTO employee_department_v (
    employee_id,
    last_name,
    department_id,
    department_name
)
VALUES (9001, 'NGUYEN', 50, 'SALES');
~~~

If the view has an `INSTEAD OF INSERT` trigger, the trigger executes. The trigger can insert solely into `EMPLOYEES`, validate `DEPARTMENTS`, or perform additional operations per design rules.

Even when a view is inherently updatable, if an `INSTEAD OF` trigger exists for that event, the trigger takes precedence over automatic DML on the view. Consequently, creating a trigger can alter semantics that callers previously relied upon.

### 3.2. INSTEAD OF Only Applies to Views

You cannot declare an `INSTEAD OF` trigger directly on a table:

~~~sql
-- Invalid: INSTEAD OF does not apply to tables
CREATE OR REPLACE TRIGGER trg_orders_io
INSTEAD OF INSERT ON orders
FOR EACH ROW
BEGIN
    NULL;
END;
/
~~~

For tables, Oracle uses timing points such as `BEFORE` and `AFTER`. `INSTEAD OF` is specifically for views.

### 3.3. Row-Level Semantics Only

`INSTEAD OF` triggers fire only per row. The syntax includes `FOR EACH ROW`; there is no statement-level `INSTEAD OF` trigger.

If a statement affects 100 rows in the view, the trigger can execute 100 times, each time receiving the `:OLD` and `:NEW` pair corresponding to that row.

Example:

~~~sql
UPDATE employee_department_v
SET department_id = 60
WHERE department_id = 50;
~~~

The trigger processes each affected row. Never assume the trigger body runs only once for the entire `UPDATE` statement.

### 3.4. No BEFORE or AFTER for INSTEAD OF

You cannot declare `BEFORE INSERT` or `AFTER UPDATE` as a substitute for `INSTEAD OF`. View triggers use the `INSTEAD OF` timing point. It is called in place of the DML operation on the view.

### 3.5. Triggers Execute in the Current Transaction

An `INSTEAD OF` trigger executes within the transaction of the user who issued the DML statement. `INSERT`/`UPDATE`/`DELETE` statements against base tables belong to that same transaction.

Normally:

- The trigger does not `COMMIT` on its own.
- The trigger does not `ROLLBACK` the calling transaction on its own.
- The caller can `COMMIT` or `ROLLBACK` per use case.
- Unhandled errors cause the original DML statement to fail.

Do not design the trigger as an independent transaction.

## 4. Syntax for Creating an INSTEAD OF Trigger

General syntax:

~~~sql
CREATE [OR REPLACE] TRIGGER trigger_name
INSTEAD OF {INSERT | UPDATE | DELETE}
ON view_name
FOR EACH ROW
DECLARE
    -- Local variables (if needed)
BEGIN
    -- DML on base tables
END;
/
~~~

A single trigger can handle multiple events:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_io
INSTEAD OF INSERT OR UPDATE OR DELETE
ON employee_directory_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        ...
    ELSIF UPDATING THEN
        ...
    ELSIF DELETING THEN
        ...
    END IF;
END;
/
~~~

Event predicates:

| Predicate | Meaning |
| --- | --- |
| INSERTING | Trigger is handling an INSERT |
| UPDATING | Trigger is handling an UPDATE |
| DELETING | Trigger is handling a DELETE |
| UPDATING('COLUMN_NAME') | UPDATE statement specified that column in SET |

`UPDATING('COLUMN_NAME')` checks whether the column appeared in the `SET` clause; it does not mean the actual value necessarily changed.

## 5. :OLD and :NEW Pseudorecords

Inside a row trigger, Oracle provides correlation variables to read the values of the row being processed.

| DML Event | :OLD | :NEW |
| --- | --- | --- |
| INSERT | NULL for fields | Row values requested for insert |
| UPDATE | Values before update | New values requested |
| DELETE | Values before delete | NULL for fields |

Example:

~~~sql
IF INSERTING THEN
    INSERT INTO employees(employee_id, last_name)
    VALUES (:NEW.employee_id, :NEW.last_name);
ELSIF UPDATING THEN
    UPDATE employees
    SET last_name = :NEW.last_name
    WHERE employee_id = :OLD.employee_id;
ELSIF DELETING THEN
    DELETE FROM employees
    WHERE employee_id = :OLD.employee_id;
END IF;
~~~

### 5.1. INSTEAD OF Triggers Can Only Read :OLD and :NEW

An important Oracle rule: `INSTEAD OF` triggers can read both `:OLD` and `:NEW`, but cannot assign values to their fields.

Do not write:

~~~sql
:NEW.last_name := UPPER(:NEW.last_name);
~~~

If normalization is needed, use a local variable:

~~~sql
DECLARE
    l_last_name employees.last_name%TYPE;
BEGIN
    l_last_name := UPPER(:NEW.last_name);

    INSERT INTO employees(employee_id, last_name)
    VALUES (:NEW.employee_id, l_last_name);
END;
~~~

### 5.2. Use :OLD to Identify Rows to Update or Delete

In `UPDATE`, generally use the old key to locate the base row:

~~~sql
UPDATE employees
SET employee_id = :NEW.employee_id,
    last_name = :NEW.last_name
WHERE employee_id = :OLD.employee_id;
~~~

If `:NEW.employee_id` is used in `WHERE`, when the primary key changes the trigger may fail to find the existing row.

In `DELETE`, use `:OLD`:

~~~sql
DELETE FROM employees
WHERE employee_id = :OLD.employee_id;
~~~

### 5.3. Do Not Assume Every View Column Was Supplied

A caller may include only a subset of columns in `INSERT` or `UPDATE`. Unspecified fields may carry defaults/nulls according to DML and view semantics. The trigger must validate required values and never assume every column holds a valid value.

Encourage callers to specify an explicit column list:

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    last_name,
    department_id
)
VALUES (9001, 'NGUYEN', 50);
~~~

This clarifies the input contract and reduces breakage when columns are added to the view later.

## 6. Complete Example: DML on a Two-Table JOIN View

Suppose we have two tables:

- `EMPLOYEES` storing employee details.
- `DEPARTMENTS` storing department names.

A view displays employees along with their department names:

~~~sql
CREATE OR REPLACE VIEW employee_directory_v AS
SELECT e.employee_id,
       e.first_name,
       e.last_name,
       e.salary,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

This is a `JOIN` view. Let's define its semantics:

- `INSERT`: creates a row in `EMPLOYEES`; `DEPARTMENT_ID` must reference an existing department.
- `UPDATE`: modifies employee attributes in `EMPLOYEES`. `DEPARTMENT_NAME` is a derived display column and cannot be updated directly through this API.
- `DELETE`: deletes the employee row from `EMPLOYEES`; foreign key constraints on base tables still apply.

### 6.1. Creating the INSTEAD OF Trigger for INSERT

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_ins
INSTEAD OF INSERT ON employee_directory_v
FOR EACH ROW
BEGIN
    IF :NEW.employee_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20101, 'Employee ID is required');
    END IF;

    IF :NEW.department_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20102, 'Department ID is required');
    END IF;

    INSERT INTO employees (
        employee_id,
        first_name,
        last_name,
        salary,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.first_name,
        :NEW.last_name,
        :NEW.salary,
        :NEW.department_id
    );
END;
/
~~~

Invoke:

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    first_name,
    last_name,
    salary,
    department_id
)
VALUES (
    9001,
    'AN',
    'NGUYEN',
    2500,
    50
);
~~~

The trigger writes to `EMPLOYEES`. The `DEPARTMENT_NAME` column comes from the `JOIN`, so no direct `INSERT` into `DEPARTMENTS` is needed.

If `DEPARTMENT_ID` does not exist, the foreign key on `EMPLOYEES` (if declared) rejects the `INSERT`. An `INSTEAD OF` trigger never bypasses base-table constraints.

### 6.2. Creating the INSTEAD OF Trigger for UPDATE

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_upd
INSTEAD OF UPDATE ON employee_directory_v
FOR EACH ROW
BEGIN
    IF UPDATING('DEPARTMENT_NAME') THEN
        RAISE_APPLICATION_ERROR(
            -20103,
            'Department name is read-only in this view'
        );
    END IF;

    UPDATE employees
    SET employee_id   = :NEW.employee_id,
        first_name    = :NEW.first_name,
        last_name     = :NEW.last_name,
        salary        = :NEW.salary,
        department_id = :NEW.department_id
    WHERE employee_id = :OLD.employee_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(-20104, 'Employee row not found');
    END IF;
END;
/
~~~

Invoke:

~~~sql
UPDATE employee_directory_v
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

Oracle calls the trigger for each updated row. Each invocation updates the corresponding row in `EMPLOYEES`.

`UPDATING('DEPARTMENT_NAME')` checks whether the `UPDATE` included that column in `SET`. If the caller updates only `SALARY`, the trigger permits it. If the caller includes `DEPARTMENT_NAME` in `SET`, the trigger rejects it per the contract.

Note: the trigger updates the entire set of employee columns from `:NEW`. If you need to handle only specifically supplied columns, use `UPDATING('COLUMN_NAME')` to construct an appropriate `UPDATE`. When a view has many derived columns, clearly document which columns are writable and which are display-only.

### 6.3. Creating the INSTEAD OF Trigger for DELETE

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_del
INSTEAD OF DELETE ON employee_directory_v
FOR EACH ROW
BEGIN
    DELETE FROM employees
    WHERE employee_id = :OLD.employee_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(-20105, 'Employee row not found');
    END IF;
END;
/
~~~

Invoke:

~~~sql
DELETE FROM employee_directory_v
WHERE employee_id = 9001;
~~~

The trigger deletes the row in `EMPLOYEES`. If other tables reference `EMPLOYEES` via foreign keys, base-table referential integrity rules still govern whether the deletion succeeds.

### 6.4. Using One Trigger for All Three Events

Instead of three separate triggers, logic can be consolidated:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_dml
INSTEAD OF INSERT OR UPDATE OR DELETE
ON employee_directory_v
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO employees (
            employee_id,
            first_name,
            last_name,
            salary,
            department_id
        )
        VALUES (
            :NEW.employee_id,
            :NEW.first_name,
            :NEW.last_name,
            :NEW.salary,
            :NEW.department_id
        );

    ELSIF UPDATING THEN
        IF UPDATING('DEPARTMENT_NAME') THEN
            RAISE_APPLICATION_ERROR(
                -20103,
                'Department name is read-only in this view'
            );
        END IF;

        UPDATE employees
        SET first_name    = :NEW.first_name,
            last_name     = :NEW.last_name,
            salary        = :NEW.salary,
            department_id = :NEW.department_id
        WHERE employee_id = :OLD.employee_id;

    ELSIF DELETING THEN
        DELETE FROM employees
        WHERE employee_id = :OLD.employee_id;
    END IF;
END;
/
~~~

A single trigger consolidates event logic, though the trigger can grow long. If each event's logic is complex, extract private helper procedures into a package and call those helpers from the trigger.

Do not create multiple triggers of the same type for the same event if their execution order could affect outcomes without an explicit ordering design. When multiple ordered steps are needed, a single trigger calling helpers in a deterministic order is much easier to understand.

## 7. Example: UNION ALL View Mapping to Multiple Base Tables

`INSTEAD OF` triggers are especially useful when a view combines different entity types.

Suppose there are two tables:

~~~sql
CREATE TABLE person_contacts (
    person_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(200 CHAR) NOT NULL
);

CREATE TABLE company_contacts (
    company_id NUMBER PRIMARY KEY,
    company_name VARCHAR2(200 CHAR) NOT NULL
);
~~~

Create the unified view:

~~~sql
CREATE OR REPLACE VIEW all_contacts_v AS
SELECT person_id AS contact_id,
       full_name AS display_name,
       'PERSON' AS contact_type
FROM person_contacts
UNION ALL
SELECT company_id AS contact_id,
       company_name AS display_name,
       'COMPANY' AS contact_type
FROM company_contacts;
~~~

Because the view uses `UNION ALL`, it is not inherently updatable for direct DML. The trigger routes to the appropriate base table based on `CONTACT_TYPE`.

### 7.1. INSERT Trigger

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_ins
INSTEAD OF INSERT ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :NEW.contact_type = 'PERSON' THEN
        INSERT INTO person_contacts(person_id, full_name)
        VALUES (:NEW.contact_id, :NEW.display_name);

    ELSIF :NEW.contact_type = 'COMPANY' THEN
        INSERT INTO company_contacts(company_id, company_name)
        VALUES (:NEW.contact_id, :NEW.display_name);

    ELSE
        RAISE_APPLICATION_ERROR(-20110, 'Unknown contact type');
    END IF;
END;
/
~~~

### 7.2. UPDATE Trigger

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_upd
INSTEAD OF UPDATE ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :OLD.contact_type <> :NEW.contact_type THEN
        RAISE_APPLICATION_ERROR(
            -20111,
            'Changing contact type is not supported'
        );
    END IF;

    IF :OLD.contact_type = 'PERSON' THEN
        UPDATE person_contacts
        SET person_id = :NEW.contact_id,
            full_name = :NEW.display_name
        WHERE person_id = :OLD.contact_id;

    ELSIF :OLD.contact_type = 'COMPANY' THEN
        UPDATE company_contacts
        SET company_id = :NEW.contact_id,
            company_name = :NEW.display_name
        WHERE company_id = :OLD.contact_id;

    ELSE
        RAISE_APPLICATION_ERROR(-20112, 'Unknown old contact type');
    END IF;
END;
/
~~~

### 7.3. DELETE Trigger

~~~sql
CREATE OR REPLACE TRIGGER trg_all_contacts_del
INSTEAD OF DELETE ON all_contacts_v
FOR EACH ROW
BEGIN
    IF :OLD.contact_type = 'PERSON' THEN
        DELETE FROM person_contacts
        WHERE person_id = :OLD.contact_id;

    ELSIF :OLD.contact_type = 'COMPANY' THEN
        DELETE FROM company_contacts
        WHERE company_id = :OLD.contact_id;
    END IF;
END;
/
~~~

This example shows how a view can act as a façade over multiple base tables. However, ensure the row-identifying key is unique within each type. `CONTACT_ID` may collide between `PERSON` and `COMPANY`; therefore, the pair `CONTACT_TYPE + CONTACT_ID` is the logical identifier of a view row.

If a contact must be converted from `PERSON` to `COMPANY`, that is an entity conversion involving inserting into the target table, migrating dependent relationships, and deleting from the source table. Do not silently treat it as a simple `UPDATE` without explicitly defining those business semantics.

## 8. Multi-Row DML and Performance

### 8.1. Triggers Execute Row by Row

~~~sql
INSERT INTO all_contacts_v(contact_id, display_name, contact_type)
SELECT person_id, full_name, 'PERSON'
FROM staging_person_contacts;
~~~

If the `INSERT` creates 50,000 rows, the `INSTEAD OF` trigger can execute 50,000 times, running DML against the base table on every invocation.

This is row-by-row processing. There is no statement-level `INSTEAD OF` trigger to batch all rows of the DML statement into a single execution.

### 8.2. Avoid Unnecessary SQL Statements Inside Each Trigger Invocation

Because the trigger runs per row, repeated lookup queries introduce substantial overhead. Consider:

- Using constraints and foreign keys for integrity checks whenever possible.
- Querying only truly necessary data.
- Ensuring proper indexes exist on base-table lookup keys.
- Avoiding remote database calls or external service calls per row.
- Avoiding unnecessary DML when columns have not changed.

### 8.3. Use Set-Based SQL When Possible

If the operation is simply a bulk update on a single base table, issue set-based SQL directly against the table rather than going through a view trigger. A trigger is a mapping adapter for a view interface; it does not magically convert row-by-row execution into bulk SQL.

### 8.4. When Bulk Processing Is Needed

When processing high volumes across multiple steps, consider:

- Procedures/packages accepting collections and using `FORALL`.
- Staging tables paired with set-based `INSERT`/`UPDATE`.
- ETL or batch jobs.
- A dedicated DML API instead of a view trigger.

Do not choose an `INSTEAD OF` trigger merely to hide multiple DML steps from callers if doing so introduces severe overhead or makes transactions unpredictable.

## 9. Constraints, Defaults, and Base-Table Data

### 9.1. Base-Table Constraints Remain Active

An `INSTEAD OF` trigger does not bypass:

- `NOT NULL`.
- `PRIMARY KEY`.
- `UNIQUE`.
- `CHECK`.
- `FOREIGN KEY`.

If a trigger inserts values violating a constraint, Oracle raises an error from the base table and the statement on the view fails unless handled appropriately.

### 9.2. Default Values

If a base-table column has a `DEFAULT`, omit that column from the `INSERT` list in the trigger when you want Oracle to apply the default. If the trigger passes an explicit `NULL`, normal column defaults do not override explicit `NULL`s.

Example:

~~~sql
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
~~~

If `CREATED_AT` has a default, leave `CREATED_AT` out of the column list so Oracle applies the default. If the trigger passes `:NEW.created_at` and its value is `NULL`, the stored outcome may differ from expectations.

### 9.3. Identity and Sequences

If a base table uses an identity column or sequence, the trigger must clearly determine the key source:

- Use identity/default by omitting the identity column from `INSERT`.
- Or fetch `NEXTVAL` from the sequence per convention.
- If the view must immediately return the generated key to the caller, design a separate output API; an `INSTEAD OF` trigger cannot assign back into `:NEW`.

Do not create a second sequence if the base table already manages keys via an identity column or sequence.

### 9.4. Verifying Keys and Affected Row Counts

~~~sql
UPDATE employees
SET salary = :NEW.salary
WHERE employee_id = :OLD.employee_id;

IF SQL%ROWCOUNT <> 1 THEN
    RAISE_APPLICATION_ERROR(-20120, 'Expected one employee row');
END IF;
~~~

Checking row counts detects broken mappings or missing base rows. However, if a view row represents multiple base rows, define the exact cardinality rule explicitly.

## 10. WITH CHECK OPTION and INSTEAD OF Triggers

`WITH CHECK OPTION` on a regular view requires rows inserted or updated through the view to continue satisfying the view's `WHERE` condition.

Example:

~~~sql
CREATE OR REPLACE VIEW active_customers_v AS
SELECT customer_id, customer_name, status
FROM customers
WHERE status = 'ACTIVE'
WITH CHECK OPTION;
~~~

With direct DML handled natively by Oracle on the view, `CHECK OPTION` is enforced according to view semantics.

However, when `INSERT` or `UPDATE` is handled by an `INSTEAD OF` trigger, Oracle does not automatically enforce `WITH CHECK OPTION`. The trigger body must enforce the corresponding condition itself.

Example:

~~~sql
CREATE OR REPLACE TRIGGER trg_active_customers_ins
INSTEAD OF INSERT ON active_customers_v
FOR EACH ROW
BEGIN
    IF :NEW.status <> 'ACTIVE' THEN
        RAISE_APPLICATION_ERROR(
            -20130,
            'Only ACTIVE customers can be inserted through this view'
        );
    END IF;

    INSERT INTO customers(customer_id, customer_name, status)
    VALUES (:NEW.customer_id, :NEW.customer_name, :NEW.status);
END;
/
~~~

If this check is omitted, the trigger can insert a row that violates the view filter. That row will not appear when querying the view, confusing callers into thinking the `INSERT` failed or data disappeared.

**Rule:** When an `INSTEAD OF` trigger exists, enforce all critical view filter predicates inside the trigger logic or a validation layer invoked by the trigger.

## 11. Security: Triggers Can Alter Privilege Boundaries

### 11.1. Trigger Execution Privileges

A trigger is created in the schema owning the view and executes under the stored PL/SQL privilege model. The trigger owner needs the required privileges to operate on base tables. With definer-rights stored PL/SQL, object privileges generally must be granted directly rather than solely through roles.

If base tables belong to another schema, grant exact DML privileges to the appropriate owner:

~~~sql
GRANT INSERT, UPDATE, DELETE
ON hr.employees
TO reporting_owner;
~~~

Never grant `DBA` or overly broad privileges just to make a trigger work.

### 11.2. DML on a View Does Not Imply Arbitrary Base-Table Access

An application may be granted DML privileges only on a view while the trigger performs controlled operations on underlying base tables. This encapsulates the access path.

However, if the trigger accepts unvalidated columns or values, callers can manipulate more data than intended. The trigger must validate:

- Row keys.
- Tenant/customer scope.
- Business state.
- Allowed writable columns.
- Untrusted values supplied by the client.

### 11.3. Fine-Grained Access Control on Views

Oracle notes that if a view has a row-level security policy (Fine-Grained Access Control / VPD) and also has an `INSTEAD OF` trigger, the policy on the view is not enforced the same way as direct DML because the trigger runs instead of view DML.

This is a critical security point. If the system relies on a VPD policy on the view to restrict rows, never assume that policy still protects DML once an `INSTEAD OF` trigger is added.

You must implement tenant/row access checks directly inside the trigger or an equivalently protected layer, and verify base-table policies if present.

### 11.4. Do Not Use View Triggers to Bypass Authorization

A trigger can execute with its owner's privileges and write to tables the caller cannot access directly. While useful for controlled APIs, this becomes a privilege escalation risk if:

- The trigger accepts arbitrary table/column names.
- Dynamic SQL concatenates unsafe input.
- The caller can alter tenant ID or owner ID.
- The trigger skips business role/state checks.
- A public view permits modifying data outside the user's scope.

Expose only necessary operations and verify authorization by business identity.

## 12. Transactions, Errors, and Rollbacks

### 12.1. Do Not COMMIT Inside INSTEAD OF Triggers

The trigger runs inside the transaction of the invoking DML statement. Do not use `COMMIT` or `ROLLBACK` inside a normal trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_bad_io
INSTEAD OF INSERT ON some_view
FOR EACH ROW
BEGIN
    INSERT INTO base_table(id) VALUES (:NEW.id);
    COMMIT; -- Invalid inside a normal trigger
END;
/
~~~

Transaction control inside a trigger can raise `ORA-04092`. The caller must decide `COMMIT`/`ROLLBACK` after the use case completes.

Do not use autonomous transactions to commit business data inside a trigger. Autonomous transactions are appropriate only for certain independent tasks like technical logging, once consistency and locking implications are understood.

### 12.2. Statement Atomicity

Suppose a single `INSERT` into a view creates 100 rows. The `INSTEAD OF` trigger executes per row. If the trigger raises an unhandled exception on row 80:

- The `INSERT` on the view fails.
- Changes made by that `INSERT` and its trigger invocations for that statement are rolled back as one atomic statement.
- Changes performed earlier in the same transaction before that statement are not all automatically rolled back.
- The caller can decide whether to roll back the broader transaction.

Never catch and ignore errors if doing so leads the caller to believe the entire batch succeeded.

### 12.3. Propagate Clear Business Errors

~~~sql
IF :NEW.department_id IS NULL THEN
    RAISE_APPLICATION_ERROR(-20140, 'Department ID is required');
END IF;
~~~

Keep error codes stable and messages clear for callers. If technical errors from base tables should be preserved, let exceptions propagate or log and then `RAISE`.

### 12.4. Do Not Swallow Errors

Avoid:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

If the trigger ignores duplicate-key, FK, or conversion errors, data state can diverge from the intended view DML semantics. Handle an exception only when clear business rules dictate recovery and the caller knows the outcome.

## 13. Triggers on Views and Triggers on Base Tables

DML through a view can create a processing chain:

~~~text
INSERT INTO VIEW
       |
       v
INSTEAD OF trigger on VIEW
       |
       v
INSERT INTO BASE TABLE
       |
       +--> BEFORE/AFTER row triggers on BASE TABLE
       |
       +--> constraints / indexes
       |
       v
Result in the same transaction
~~~

Triggers on base tables can still fire when the `INSTEAD OF` trigger performs DML on those tables. Base-table constraints and indexes continue to be maintained as well.

This can introduce multiple trigger layers. Map out execution order and side effects:

- Which tables does the `INSTEAD OF` trigger touch?
- What other triggers exist on base tables?
- Do base triggers write audits or update other tables?
- Is there any risk of calling back into the view?
- Could trigger loops or recursion occur?

Never issue DML against the same view from inside its own `INSTEAD OF` trigger without anti-recursion safeguards; doing so can re-fire the same trigger and cause recursion.

Mutating-table restrictions on base-table row triggers still apply to triggers on base tables. An `INSTEAD OF` trigger does not automatically remove those restrictions.

## 14. Special Cases and Limitations

### 14.1. Editioning Views

Oracle Database 19c does not allow creating `INSTEAD OF` triggers on editioning views. Editioning views have their own rules, primarily providing a schema compatibility layer for Edition-Based Redefinition.

If a view is an editioning view, design DML around Oracle's supported capabilities for editioning views rather than attempting to add an `INSTEAD OF` trigger.

### 14.2. View Hierarchies

If a view belongs to a hierarchy, an `INSTEAD OF` trigger created on a view is not automatically inherited by subviews. Each view must be evaluated according to its own definition and triggers.

### 14.3. Nested Table View Columns

Oracle also supports `INSTEAD OF` triggers on nested table view columns. These triggers process individual elements of a nested table and can reference the parent row via corresponding correlation names.

This is a specialized case distinct from regular triggers attached to an entire view. Review nested-table-specific syntax and examples in the PL/SQL Language Reference before applying it.

### 14.4. READ ONLY Views

Views created with `WITH READ ONLY` are intended to prevent DML through the view. Do not use `INSTEAD OF` triggers as an arbitrary workaround to break a read-only contract. If DML is required by design, define an appropriate view/API and verify Oracle's `CREATE VIEW`/`CREATE TRIGGER` limits.

### 14.5. An INSTEAD OF Trigger Does Not Replace All View Design

If a view can be simplified to be inherently updatable, prefer the simpler approach. Triggers introduce hidden logic, privilege requirements, testing overhead, and maintenance cost. Use them only when DML mapping is genuinely needed.

## 15. When to Use an INSTEAD OF Trigger vs. a Procedure API

| Criterion | INSTEAD OF Trigger | Procedure/Package API |
| --- | --- | --- |
| Invocation style | Direct DML on a view | Calling a procedure/function |
| DML mapping | Trigger maps row by row | Procedure controls entire use case |
| Visibility of side effects at call site | Lower; logic hidden behind view | Higher; procedure name conveys action |
| Bulk operations | Trigger runs per row | Can be designed as set-based/BULK |
| Complex validation | Possible, though trigger grows bulky | Often easier to structure multi-step logic |
| Acting as an SQL façade | Very suitable | Caller must invoke API |
| Transaction | Uses triggering DML's transaction | Caller/API defines transaction boundaries |
| Testability | Tested via view DML and base tables | Tested directly via public routines |

`INSTEAD OF` triggers fit when callers expect to issue standard DML against a view and row-level mapping is straightforward. Package procedures fit when the operation is a multi-step use case, returns outputs, requires transaction orchestration, or processes large datasets.

Both mechanisms can coexist: views provide read models while packages provide command APIs. Do not force every data modification to go through a view.

## 16. Monitoring, Inspecting, and Managing Triggers

### 16.1. USER_TRIGGERS

~~~sql
SELECT trigger_name,
       trigger_type,
       triggering_event,
       table_name,
       status
FROM user_triggers
WHERE table_name = 'EMPLOYEE_DIRECTORY_V'
ORDER BY trigger_name;
~~~

`USER_TRIGGERS` lists triggers in the current schema. With broader privileges, query `ALL_TRIGGERS` or `DBA_TRIGGERS`.

### 16.2. Viewing Source

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'TRG_EMPLOYEE_DIRECTORY_DML'
  AND type = 'TRIGGER'
ORDER BY line;
~~~

### 16.3. Checking Compilation Errors

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'TRG_EMPLOYEE_DIRECTORY_DML'
  AND type = 'TRIGGER'
ORDER BY sequence;
~~~

Or in SQL*Plus/SQLcl:

~~~sql
SHOW ERRORS TRIGGER trg_employee_directory_dml;
~~~

### 16.4. Enabling and Disabling

~~~sql
ALTER TRIGGER trg_employee_directory_dml DISABLE;
ALTER TRIGGER trg_employee_directory_dml ENABLE;
~~~

Disabling the trigger stops DML on the view from mapping as expected or causes it to fail if the view is not inherently updatable. Only disable during maintenance windows with a recovery plan.

### 16.5. Replacing or Dropping

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_directory_dml
...
~~~

~~~sql
DROP TRIGGER trg_employee_directory_dml;
~~~

Before replacing or dropping, verify which applications rely on view DML and check associated grants.

## 17. Debugging and Testing INSTEAD OF Triggers

### 17.1. Test Each DML Event Separately

For each view, test:

- `INSERT` a valid row.
- `INSERT` missing required values.
- `INSERT` with an existing key.
- `UPDATE` an allowed column.
- `UPDATE` a read-only or derived column.
- `UPDATE` matching no rows.
- `DELETE` a row.
- `DELETE` a row that has child references.
- Multi-row DML.

### 17.2. Compare Both the View and Base Tables

After DML, do not inspect only the view:

~~~sql
SELECT *
FROM employee_directory_v
WHERE employee_id = 9001;

SELECT *
FROM employees
WHERE employee_id = 9001;
~~~

If the trigger writes to multiple base tables, inspect all affected tables and audit records.

### 17.3. Test Statement Atomicity

Test a multi-row `INSERT` where one row violates a constraint. Confirm the entire statement rolls back under Oracle semantics, and verify the prior transaction state remains as the caller expects.

### 17.4. Test Concurrency

If a trigger reads state before writing data, race conditions can occur across concurrent sessions. Use:

- Constraints to guarantee uniqueness/integrity.
- Conditional `UPDATE` statements.
- `SELECT FOR UPDATE` when row locking is needed.
- Consistent locking order to reduce deadlocks.
- Idempotency keys for retryable operations.

Do not rely on a `SELECT` existence check before `INSERT` when a unique constraint is the true final safeguard.

### 17.5. Test Privileges

Log in as the actual application user:

- Verify the user has only required privileges on the view.
- Verify the trigger can operate on base tables under the privilege model.
- Verify users cannot modify other tenants/owners.
- Verify VPD/FGA policies and row-level controls.
- Verify the trigger does not expose operations outside the public contract.

## 18. Example Walkthrough Testing DML Mapping Through a View

Assume the triggers from section 6 have been created.

### 18.1. INSERT

~~~sql
INSERT INTO employee_directory_v (
    employee_id,
    first_name,
    last_name,
    salary,
    department_id
)
VALUES (9001, 'AN', 'NGUYEN', 2500, 50);
~~~

Verify:

~~~sql
SELECT employee_id, last_name, department_id
FROM employees
WHERE employee_id = 9001;
~~~

### 18.2. UPDATE

~~~sql
UPDATE employee_directory_v
SET salary = 2700
WHERE employee_id = 9001;
~~~

Verify:

~~~sql
SELECT salary
FROM employees
WHERE employee_id = 9001;
~~~

### 18.3. DELETE

~~~sql
DELETE FROM employee_directory_v
WHERE employee_id = 9001;
~~~

Verify:

~~~sql
SELECT COUNT(*)
FROM employees
WHERE employee_id = 9001;
~~~

### 18.4. COMMIT or ROLLBACK in the Caller

~~~sql
COMMIT;
~~~

Or in a test environment:

~~~sql
ROLLBACK;
~~~

The trigger does not commit automatically. Always verify the real application's transaction boundaries.

## 19. Common Errors

| Error / Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| ORA-04098 | Trigger invalid or failed compilation on firing | Inspect `USER_ERRORS`, fix source, and recompile |
| ORA-04092 | Trigger attempted `COMMIT` or `ROLLBACK` | Remove transaction control from trigger; let caller manage it |
| ORA-01031 | Trigger owner lacks privileges on base table | Grant required object privileges directly to owner |
| ORA-01400 | Trigger inserts `NULL` into a `NOT NULL` column | Validate input or allow base-table default to apply |
| ORA-00001 | Trigger causes duplicate primary/unique key | Check key mapping and unique constraints |
| ORA-02291 | FK value has no matching parent row | Verify parent keys and operation ordering |
| ORA-02292 | Deleting parent referenced by child rows | Handle child rows per referential integrity policy |
| ORA-01403 | `SELECT INTO` inside trigger finds no rows | Handle `NO_DATA_FOUND` or adjust DML/logic |
| ORA-04091 | Base-table trigger queries/updates mutating table | Redesign base-table trigger; `INSTEAD OF` does not remove this limit |
| View DML does not update expected table | Trigger maps wrong key or wrong base table | Verify `:OLD`/`:NEW`, keys, and mapping logic |
| `UPDATE` modifies some columns, trigger overwrites others | Trigger uses all `:NEW` fields without checking `SET` columns | Use `UPDATING('COLUMN')` or update only required fields |
| Row disappears from view after `INSERT` | Base row fails view's `WHERE`/`JOIN` condition | Validate view predicates inside the trigger |
| View has `WITH CHECK OPTION`, invalid row still written | `INSTEAD OF` trigger does not auto-enforce `CHECK OPTION` | Enforce predicates manually inside the trigger |
| VPD policy on view does not restrict DML as expected | `INSTEAD OF` trigger bypasses standard view policy enforcement | Enforce authorization in trigger/base table and test as app user |
| Trigger is too slow on multi-row DML | Row-level trigger runs repeatedly with repetitive SQL | Use set-based/package/bulk processing if suitable |
| Recursive DML | Trigger operates on the same view that fired it | Run DML directly on base tables and control call graph |

## 20. Anti-Patterns to Avoid

### 20.1. Issuing DML Back on the Same View Inside the Trigger

Do not write:

~~~sql
CREATE OR REPLACE TRIGGER trg_view_io
INSTEAD OF INSERT ON employee_directory_v
FOR EACH ROW
BEGIN
    INSERT INTO employee_directory_v(employee_id, last_name)
    VALUES (:NEW.employee_id, :NEW.last_name);
END;
/
~~~

Inserting back into the view can re-fire the same trigger, creating recursion. The trigger must operate on base tables or call a package performing base-table DML.

### 20.2. Failing to Identify a Unique Key

If `DELETE` uses a non-unique condition:

~~~sql
DELETE FROM employees
WHERE last_name = :OLD.last_name;
~~~

it can delete multiple rows. Always use the primary key or a guaranteed unique business key.

### 20.3. Treating Every View Column as Writable

Views may contain derived columns, aggregates, constants/discriminators, or display-only columns. Never write those columns down to base tables without clear semantics. Explicitly mark read-only columns and reject modifications when needed.

### 20.4. Swallowing Exceptions

Never catch errors and run `NULL` simply to hide failures from the application. Callers must know when operations fail so they can roll back, retry, or return proper errors.

### 20.5. Using Triggers for Oversized Multi-Step Workflows

If DML on a view has to call multiple services, send emails, update external systems, retry failures, or coordinate multiple transactions, use a package API or application service instead. Triggers should keep DML mapping clean and synchronous with the database transaction.

## 21. INSTEAD OF Trigger Design Checklist

1. **Does the view truly need a trigger?** Check inherent updatability and `USER_UPDATABLE_COLUMNS`.
2. **What kind of view is it?** Join view, `UNION`, aggregate, object view, or nested-table view column.
3. **Are DML semantics clear?** Define which base tables `INSERT`/`UPDATE`/`DELETE` map to.
4. **What is the row key?** Use `:OLD` key to locate existing rows; ensure the key is unambiguous.
5. **Which columns are read-only?** Block `UPDATE` on derived columns or immutable discriminators.
6. **Are `:OLD`/`:NEW` used properly?** `INSTEAD OF` triggers only read them, never assign fields.
7. **Can each row trigger multiple DML statements?** Evaluate cost when statements affect many rows.
8. **How are constraints, defaults, and identity handled?** Avoid passing `NULL` where defaults should apply.
9. **Is `WITH CHECK OPTION` enforced manually?** The trigger must check the corresponding predicates.
10. **Are security policies affected?** Check VPD/FGA and tenant authorization.
11. **Does the trigger owner have direct grants?** Never rely on roles where stored PL/SQL needs direct object privileges.
12. **Do base-table triggers fire?** Map out side effects and prevent recursion/mutating table errors.
13. **Is transaction ownership clear?** Never `COMMIT`/`ROLLBACK` inside triggers.
14. **Do exceptions propagate properly?** Never swallow errors.
15. **Is multi-row DML performance acceptable?** Consider packages, set-based SQL, or bulk processing.
16. **Have all three events been tested?** Test `INSERT`, `UPDATE`, `DELETE`, and failure paths.
17. **Has it been tested as the application user?** Verify real privileges and row-level security.
18. **Could a procedure/package API replace it?** Choose an abstraction with clearer side effects when workflows grow complex.

## 22. Self-Check Questions

**Question 1.** What problem does an `INSTEAD OF` trigger solve for DML through a view?

**Question 2.** Does an inherently updatable view require an `INSTEAD OF` trigger?

**Question 3.** What is a key-preserved table in a join view?

**Question 4.** Can an `INSTEAD OF` trigger be created on a table?

**Question 5.** Do statement-level `INSTEAD OF` triggers exist?

**Question 6.** Can you declare `BEFORE` or `AFTER` on an `INSTEAD OF` trigger?

**Question 7.** Can an `INSTEAD OF` trigger modify `:NEW` values?

**Question 8.** When an `UPDATE` changes the primary key, should `:OLD` or `:NEW` be used in `WHERE` to find the original row?

**Question 9.** What are `:OLD`/`:NEW` values for `INSERT`, `UPDATE`, and `DELETE`?

**Question 10.** Can a `UNION ALL` view be made DML-capable with an `INSTEAD OF` trigger?

**Question 11.** Why must `WITH CHECK OPTION` be enforced manually inside the trigger?

**Question 12.** Can an `INSTEAD OF` trigger change the semantics of an otherwise updatable view?

**Question 13.** Why must VPD policies on a view be re-evaluated when adding an `INSTEAD OF` trigger?

**Question 14.** Can a trigger `COMMIT`?

**Question 15.** If a trigger raises an unhandled error on one row of a multi-row `INSERT`, what happens to the statement?

**Question 16.** Can base-table triggers fire when an `INSTEAD OF` trigger runs DML on that base table?

**Question 17.** Why can an `INSTEAD OF` trigger be slow on bulk DML?

**Question 18.** When is a package procedure a better choice than an `INSTEAD OF` trigger?

<details>
<summary>Answer Key</summary>

1. It provides a way to map view DML down to one or more base tables when the view is not inherently updatable or needs custom semantics.
2. No. If the view is inherently updatable and needs no custom mapping, direct DML can suffice.
3. A table whose key still uniquely identifies each row in the join output under the join conditions.
4. No. `INSTEAD OF` applies only to views.
5. No. It is row-level only.
6. No. `INSTEAD OF` is its own timing point; do not combine with `BEFORE`/`AFTER`.
7. No. You can read `:OLD`/`:NEW`, but cannot modify their fields.
8. `:OLD`, to identify the original row.
9. `INSERT`: `OLD` null, `NEW` input; `UPDATE`: `OLD` prior, `NEW` new; `DELETE`: `OLD` prior, `NEW` null.
10. Yes. The trigger can classify rows by a discriminator and perform DML on the appropriate base table.
11. Because Oracle does not enforce `CHECK OPTION` for `INSERT`/`UPDATE` handled through an `INSTEAD OF` trigger.
12. Yes. The trigger takes precedence and runs instead of automatic view DML.
13. Because policies on the view are not enforced like normal view DML when the trigger replaces the view operation.
14. No. Triggers execute within the calling transaction and must not perform normal `COMMIT`/`ROLLBACK`.
15. The DML statement fails and that statement's changes are rolled back; earlier statements in the transaction are not automatically rolled back entirely.
16. Yes. Base-table DML inside the trigger can fire base-table triggers and constraints.
17. Because the trigger executes once per row and can run repetitive SQL statements.
18. When workflows have multiple steps, need return values, transaction orchestration, bulk processing, or clear side effects at the call site.

</details>

## 23. Official Oracle Documentation

1. [Oracle Database 19c PL/SQL Language Reference — INSTEAD OF DML Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dml-triggers.html): semantics, row-level behavior, `:OLD`/`:NEW`, and `INSTEAD OF` trigger limits.
2. [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/CREATE-TRIGGER-statement.html): trigger creation syntax, event predicates, and trigger restrictions.
3. [Oracle Database 19c SQL Language Reference — CREATE VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html): view definitions, `WITH CHECK OPTION`, `WITH READ ONLY`, and editioning view restrictions.
4. [Oracle Database 19c Administrator's Guide — Managing Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-views-sequences-and-synonyms.html): updatable views, join views, and key-preserved tables.
5. [Oracle Database 19c Reference — USER_UPDATABLE_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_UPDATABLE_COLUMNS.html): metadata on `INSERT`/`UPDATE`/`DELETE` capability of view columns.
6. [Oracle Database 19c Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): trigger metadata in the current schema.
7. [Oracle Database 19c PL/SQL Language Reference — Trigger Design](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-triggers.html): trigger execution, transactions, restrictions, and design.

**Key takeaway:** An `INSTEAD OF` trigger acts as an adapter for view DML: Oracle runs the trigger instead of automatic view DML, and the trigger maps rows down to base tables. The trigger is row-level only, applies only to views, can read but not modify `:OLD`/`:NEW`, and runs inside the caller's transaction. You must manually enforce view predicates like `WITH CHECK OPTION`, verify authorization, row keys, and constraints, and evaluate performance for multi-row DML. If mapping grows into a complex workflow, a package procedure is usually a cleaner, more controllable interface.
