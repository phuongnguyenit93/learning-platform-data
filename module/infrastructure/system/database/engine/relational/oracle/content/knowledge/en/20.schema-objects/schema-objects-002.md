# Updatable Views, Key-Preserved Tables, and WITH CHECK OPTION

In Oracle Database, a **view** is a schema object that stores a query definition and presents data from one or more tables or other views. Views are commonly used to simplify queries, restrict visible columns/rows, and provide a stable data interface for applications. Some views allow INSERT, UPDATE, or DELETE directly through the view name; others are read-only.

Updatability depends on the structure of the defining query and the relationships among source tables. For a simple view on a single table, Oracle can usually identify the source row to modify. For a JOIN view, the concept of a **key-preserved table** determines which source table can be safely modified through the view. Two additional key options are:

- **WITH CHECK OPTION**: requires that rows inserted or updated through the view still satisfy the view's condition after the change.
- **WITH READ ONLY**: forbids DML through the view.

If a complex view cannot be updated directly, an **INSTEAD OF trigger** can be used to define how an operation on the view translates into DML on the underlying tables.

This lesson covers updatable views, key preservation, DML restrictions on join views, common Oracle errors, WITH CHECK OPTION, WITH READ ONLY, metadata for checking updatability, and hands-on examples.

## 1. Views as a Logical Interface Over Data

A standard view is created with CREATE VIEW:

~~~sql
CREATE OR REPLACE VIEW v_employee_public AS
SELECT employee_id,
       full_name,
       department_id
FROM employees
WHERE status = 'ACTIVE';
~~~

The view V_EMPLOYEE_PUBLIC does not store a copy of employee data the way a materialized view does. It stores a query definition. When querying the view, Oracle parses the definition and retrieves data from the source objects according to the statement's snapshot.

You can read a view like a table:

~~~sql
SELECT employee_id, full_name
FROM v_employee_public
ORDER BY employee_id;
~~~

Views can be used as sources for JOINs, subqueries, aggregates, and many other SELECT operations.

### 1.1. Views Are Not Necessarily Read-Only

With a simple view, the following operation can be valid:

~~~sql
UPDATE v_employee_public
SET full_name = 'An Nguyen'
WHERE employee_id = 101;
~~~

If the view is updatable and the FULL_NAME column maps directly to a base table column, Oracle can update EMPLOYEES.

Similarly, you can INSERT or DELETE through a view if updatability rules, required columns, and constraints are satisfied.

### 1.2. Views Are Not Data Copies

~~~sql
CREATE VIEW v_active_orders AS
SELECT order_id, customer_id, status
FROM orders
WHERE status = 'ACTIVE';
~~~

When the ORDERS table changes and the transaction COMMITs, subsequent queries against the view reflect the underlying data according to statement read consistency. There is no need to refresh the view like a materialized view.

This also means DML through the view affects the base table. If an UPDATE through V_ACTIVE_ORDERS succeeds, the corresponding ORDERS row changes.

## 2. Simple Updatable Views

A simple view typically selects columns directly from a single base table, optionally with a WHERE condition:

~~~sql
CREATE OR REPLACE VIEW v_employee_edit AS
SELECT employee_id,
       full_name,
       department_id,
       salary,
       status
FROM employees
WHERE department_id = 10;
~~~

This is a type of view that is usually updatable because each view row maps to a single row in EMPLOYEES and the exposed columns are direct columns.

Example:

~~~sql
UPDATE v_employee_edit
SET salary = salary + 1000000
WHERE employee_id = 101;
~~~

Oracle updates the corresponding row in EMPLOYEES. If EMPLOYEE_ID does not belong to department 10, that row does not appear in the view and is not matched by the UPDATE statement.

### 2.1. Common Conditions That Prevent Automatic Updatability

Query constructs that can make a view or some of its columns non-updatable include:

- DISTINCT.
- Aggregates such as SUM, AVG, COUNT, MIN, MAX in the select list.
- GROUP BY or HAVING.
- Set operators such as UNION, UNION ALL, INTERSECT, MINUS.
- Certain hierarchical queries or other complex query constructs.
- Computed expressions in the select list, with respect to those expression columns themselves.

Example of an aggregate view:

~~~sql
CREATE OR REPLACE VIEW v_department_salary AS
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id;
~~~

This view represents one row per department, not a specific employee row. Oracle cannot infer which employee's SALARY an UPDATE on AVG_SALARY should change. Therefore, direct DML on an aggregate view is not automatically meaningful.

### 2.2. Expression Columns Are Not Updatable Base Columns

~~~sql
CREATE OR REPLACE VIEW v_employee_compensation AS
SELECT employee_id,
       salary,
       salary * 12 AS annual_salary
FROM employees;
~~~

The SALARY column maps directly to EMPLOYEES.SALARY. The ANNUAL_SALARY column is an expression computed from SALARY.

You can update the base column if the view and other conditions permit:

~~~sql
UPDATE v_employee_compensation
SET salary = 25000000
WHERE employee_id = 101;
~~~

You cannot directly assign a value to ANNUAL_SALARY as though it were an independent stored column. Oracle does not automatically infer the inverse transformation from annual salary back to salary.

### 2.3. Views with WHERE Clauses Can Still Be Updatable

A WHERE clause by itself does not make a view read-only:

~~~sql
CREATE OR REPLACE VIEW v_high_salary_employee AS
SELECT employee_id, full_name, salary
FROM employees
WHERE salary >= 20000000;
~~~

An UPDATE on the view can modify SALARY of an existing row. Without WITH CHECK OPTION, the operation can leave the row no longer satisfying the WHERE condition and cause it to disappear from the view after the update.

This is why WITH CHECK OPTION matters when a view is used as a conditional DML interface.

## 3. What Is a Key-Preserved Table?

A **key-preserved table** is a table whose key remains unique in the JOIN result of a view. In other words, each row of that table appears at most once in the join result under the relationship being evaluated.

Oracle needs to determine that a view row corresponds to one specific row of a base table in order to know exactly which row DML must modify. If a base table row is multiplied into several rows in the join result, updating or deleting through the view would be ambiguous.

A table is considered key-preserved when its key remains a key of the join result. Oracle determines this from appropriate key/unique constraint metadata, not merely by observing that current data happens to have no duplicates.

### 3.1. Department and Employee Relationship Example

Suppose:
- DEPARTMENTS has one row per DEPARTMENT_ID.
- EMPLOYEES has multiple employees within the same DEPARTMENT_ID.
- EMPLOYEES.DEPARTMENT_ID references DEPARTMENTS.DEPARTMENT_ID.

Relationship:

~~~text
DEPARTMENTS
+---------------+-----------------+
| DEPARTMENT_ID | DEPARTMENT_NAME |
+---------------+-----------------+
| 10            | Sales           |
| 20            | Engineering     |
+---------------+-----------------+

EMPLOYEES
+-------------+---------------+-----------+
| EMPLOYEE_ID | DEPARTMENT_ID | FULL_NAME |
+-------------+---------------+-----------+
| 101         | 10            | An        |
| 102         | 10            | Binh      |
| 201         | 20            | Chi       |
+-------------+---------------+-----------+
~~~

JOIN:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Result:

| EMPLOYEE_ID | FULL_NAME | DEPARTMENT_ID | DEPARTMENT_NAME |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Sales |
| 102 | Binh | 10 | Sales |
| 201 | Chi | 20 | Engineering |

Each employee appears only once because DEPARTMENTS.DEPARTMENT_ID is a unique key. EMPLOYEE_ID remains unique in the JOIN result, so EMPLOYEES is a key-preserved table.

Conversely, the DEPARTMENTS row with DEPARTMENT_ID = 10 appears twice, once for An and once for Binh. The key of DEPARTMENTS is no longer unique in the JOIN result. DEPARTMENTS is not a key-preserved table in this view.

### 3.2. Key Preservation Depends on JOIN Direction and Constraints

For the view:

~~~sql
SELECT e.employee_id,
       e.full_name,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

- EMPLOYEES can be key-preserved because each EMPLOYEE_ID appears only once.
- DEPARTMENTS is not key-preserved because one department can match multiple employees.

If the relationship changes to one-to-one and both sides have appropriate key/unique constraints, both tables can be key-preserved. Even then, DML rules on join views still restrict each DML statement to modifying only one base table.

### 3.3. Current Data Does Not Replace Constraints

Suppose the DEPARTMENTS table currently has no two rows with duplicate DEPARTMENT_ID, but lacks a PRIMARY KEY or UNIQUE constraint enforcing it. Oracle cannot rely solely on current data to guarantee that the JOIN will not duplicate rows in the future.

For Oracle to recognize key preservation, declare the appropriate key:

~~~sql
ALTER TABLE departments
ADD CONSTRAINT pk_departments
PRIMARY KEY (department_id);
~~~

If business rules require department IDs to be unique without being the primary key, an appropriate UNIQUE constraint can be used. Constraints must reflect actual data rules; do not create a constraint just to force a view to be updatable if business data does not uphold it.

## 4. Join Views and DML Restrictions

A **join view** is a view whose defining query joins multiple tables. The updatability of a join view depends on key-preserved tables and Oracle rules.

Key principles:

1. A single DML statement on a join view can modify only one base table.
2. UPDATE can modify only columns mapped to a key-preserved table.
3. INSERT must map the insertion to a single base table and satisfy its required columns/constraints.
4. DELETE on a join view has specific rules: Oracle must identify a single key-preserved table from which to delete rows. If it cannot identify exactly one required table, the statement may raise ORA-01752.
5. If the view does not meet automatic updatability criteria, an INSTEAD OF trigger may be required.

### 4.1. Updating Columns of a Key-Preserved Table

In the EMPLOYEE_DEPARTMENT join view, EMPLOYEES is key-preserved. The following UPDATE statement can be valid:

~~~sql
UPDATE v_employee_department
SET full_name = 'An Nguyen'
WHERE employee_id = 101;
~~~

FULL_NAME belongs to EMPLOYEES and each employee row appears at most once in the view. Oracle can identify the exact employee row to update.

### 4.2. Updating Columns of a Non-Key-Preserved Table

The following statement attempts to modify the department name through the join view:

~~~sql
UPDATE v_employee_department
SET department_name = 'Sales North'
WHERE employee_id = 101;
~~~

In a one-department-to-many-employees model, DEPARTMENTS is not key-preserved in the join view. Oracle does not allow updating a column of a non-key-preserved table this way and may raise:

~~~text
ORA-01779: cannot modify a column which maps to a non key-preserved table
~~~

If the goal is to rename the department, UPDATE the DEPARTMENTS table directly by key:

~~~sql
UPDATE departments
SET department_name = 'Sales North'
WHERE department_id = 10;
~~~

Do not use a join view to modify a table whose key is duplicated in the JOIN result.

### 4.3. A Single UPDATE Cannot Modify Two Base Tables

You cannot use one UPDATE through a join view to simultaneously change columns in EMPLOYEES and DEPARTMENTS:

~~~sql
-- Invalid: the two columns belong to two different base tables.
UPDATE v_employee_department
SET full_name = 'An Nguyen',
    department_name = 'Sales North'
WHERE employee_id = 101;
~~~

Oracle may raise ORA-01776:

~~~text
ORA-01776: cannot modify more than one base table through a join view
~~~

Execute two separate UPDATE statements on the two base tables within the same transaction if the business logic requires both changes to succeed or fail together:

~~~sql
UPDATE employees
SET full_name = 'An Nguyen'
WHERE employee_id = 101;

UPDATE departments
SET department_name = 'Sales North'
WHERE department_id = 10;

COMMIT;
~~~

Both DML statements can still belong to the same transaction. The single-base-table limit applies per DML statement through a join view, not to how many tables a transaction can modify.

### 4.4. INSERT Through a Join View

INSERT through a join view can be valid when Oracle can identify the target base table and the supplied columns belong to the appropriate key-preserved table. A single INSERT cannot attempt to insert into multiple base tables simultaneously.

For example, if the view contains EMPLOYEE_ID, FULL_NAME, and DEPARTMENT_ID from EMPLOYEES along with DEPARTMENT_NAME from DEPARTMENTS, an INSERT supplying only employee columns can insert into EMPLOYEES if:
- EMPLOYEES is a key-preserved table.
- DEPARTMENT_ID references an existing department.
- Every NOT NULL column without a default on EMPLOYEES is supplied.
- No other view/constraint restrictions block DML.

Example:

~~~sql
INSERT INTO v_employee_department (
    employee_id,
    full_name,
    department_id
)
VALUES (301, 'Dung', 10);
~~~

Oracle inserts one EMPLOYEES row. The INSERT does not simultaneously create a new department; DEPARTMENT_ID=10 must exist.

If you try supplying both employee columns and the department name column to create two rows in two tables via one INSERT, Oracle may raise ORA-01776. Insert into each table in order within the same transaction instead.

### 4.5. DELETE Through a Join View

Oracle allows DELETE from a join view only when it can identify a single unique key-preserved table as the deletion target. If the view has multiple key-preserved tables or does not have exactly one eligible table, you may encounter:

~~~text
ORA-01752: cannot delete from view without exactly one key-preserved table
~~~

In the many-employees-to-one-department example, EMPLOYEES is the only key-preserved table. DELETE through the view can delete the corresponding employee row:

~~~sql
DELETE FROM v_employee_department
WHERE employee_id = 101;
~~~

This operation deletes employee 101's EMPLOYEES row; it does not delete department 10. Do not assume that deleting a row displayed in a join view deletes both source rows.

If the goal is to delete a department, perform DML directly on DEPARTMENTS and handle foreign keys/cascades according to business rules.

## 5. WITH CHECK OPTION: Enforcing That Rows Still Satisfy the View Condition

A view can restrict rows with a WHERE clause. If DML through the view causes a row to no longer satisfy the WHERE clause, the row disappears from the view. Sometimes this is undesirable because the application treats the view as a fixed-policy data scope.

**WITH CHECK OPTION** requires that every row inserted or updated through the view continues to satisfy the view's condition after the operation.

Syntax:

~~~sql
CREATE OR REPLACE VIEW view_name AS
SELECT column_list
FROM table_name
WHERE condition
WITH CHECK OPTION [CONSTRAINT constraint_name];
~~~

The constraint name is optional. Naming it makes error messages and metadata easier to identify.

### 5.1. View Without CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_active_employee AS
SELECT employee_id,
       full_name,
       department_id,
       status
FROM employees
WHERE status = 'ACTIVE';
~~~

Suppose employee row 101 has STATUS='ACTIVE'. The statement:

~~~sql
UPDATE v_active_employee
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

can succeed if other updatability conditions are met. After the UPDATE, row 101 no longer satisfies WHERE STATUS='ACTIVE', so it no longer appears in the view.

This is valid behavior if the application accepts that updating a row can cause it to leave the view.

### 5.2. View with WITH CHECK OPTION

Create the view:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_checked AS
SELECT employee_id,
       full_name,
       department_id,
       status
FROM employees
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_active_employee_ck;
~~~

Test:

~~~sql
UPDATE v_active_employee_checked
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle rejects the operation because the row after UPDATE would no longer satisfy STATUS='ACTIVE'. Common error:

~~~text
ORA-01402: view WITH CHECK OPTION where-clause violation
~~~

The row keeps its pre-UPDATE state because the statement is rejected.

### 5.3. INSERT Must Also Satisfy the View Condition

~~~sql
INSERT INTO v_active_employee_checked (
    employee_id,
    full_name,
    department_id,
    status
)
VALUES (501, 'Mai', 10, 'ACTIVE');
~~~

The INSERT can succeed if base table constraints are satisfied.

Conversely:

~~~sql
INSERT INTO v_active_employee_checked (
    employee_id,
    full_name,
    department_id,
    status
)
VALUES (502, 'Nam', 10, 'INACTIVE');
~~~

is rejected because the new row does not satisfy the view condition.

If STATUS is omitted from the INSERT column list and the base column has a default of ACTIVE, the row can satisfy the condition; if there is no default and the column is NOT NULL, the operation can fail due to the base table constraint before or during checking.

### 5.4. CHECK OPTION Applies Only to DML Through the View

If updating the base table directly:

~~~sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

the WITH CHECK OPTION condition of V_ACTIVE_EMPLOYEE_CHECKED is not applied as a table-wide constraint to block this operation. WITH CHECK OPTION governs DML operations passing through that view.

If you need to guarantee STATUS only accepts a certain set of values, use a CHECK constraint on the base table. If users must only modify a subset of rows/columns, consider privileges, views, VPD, or appropriate security mechanisms.

### 5.5. CHECK OPTION Does Not Replace Table Constraints

Suppose a view filters DEPARTMENT_ID=10. WITH CHECK OPTION prevents DML through the view from moving rows out of department 10. However, it does not replace:
- PRIMARY KEY.
- UNIQUE.
- NOT NULL.
- CHECK constraint.
- FOREIGN KEY.

Base table constraints still apply. WITH CHECK OPTION only adds the condition from the view's defining query.

### 5.6. DELETE Does Not Require Rows to Keep Satisfying the Condition

DELETE removes a row from the base table; the row no longer exists to be checked against the WHERE clause. WITH CHECK OPTION primarily governs INSERT and UPDATE operations that change row state. It does not prevent deleting a row merely because the deleted row will no longer appear in the view.

DELETE privileges, foreign keys, and related constraints still apply.

## 6. WITH CHECK OPTION in Nested Views

A view can be built on top of another view. For example:

~~~sql
CREATE OR REPLACE VIEW v_department_10 AS
SELECT employee_id, full_name, department_id, status
FROM employees
WHERE department_id = 10
WITH CHECK OPTION CONSTRAINT v_dept10_ck;
~~~

Create a child view:

~~~sql
CREATE OR REPLACE VIEW v_active_dept_10 AS
SELECT employee_id, full_name, department_id, status
FROM v_department_10
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_active_dept10_ck;
~~~

DML through the outer view must obey the outer view's condition and any check option conditions inherited from underlying views per Oracle rules. In this example:
- DEPARTMENT_ID must be 10.
- STATUS must be ACTIVE.

An UPDATE moving the row to department 20 or INACTIVE status will violate one of the checked conditions.

When designing nested views, explicitly review WHERE conditions at each layer. Do not treat the outer view as an isolated filter if an underlying view already has a check option.

## 7. WITH READ ONLY: Forbidding DML Through a View

If a view must be read-only, declare:

~~~sql
CREATE OR REPLACE VIEW v_employee_report AS
SELECT employee_id,
       full_name,
       department_id,
       salary
FROM employees
WITH READ ONLY;
~~~

SELECT remains valid:

~~~sql
SELECT *
FROM v_employee_report;
~~~

But DML through the view is rejected:

~~~sql
UPDATE v_employee_report
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

Oracle raises an error because the view is declared read-only, typically ORA-42399:

~~~text
ORA-42399: cannot perform a DML operation on a read-only view
~~~

### 7.1. READ ONLY on a View Does Not Make Base Tables Read-Only

The view V_EMPLOYEE_REPORT only forbids DML through the view itself. If a user has direct UPDATE privilege on EMPLOYEES, they can still update the base table according to their granted privileges.

~~~sql
UPDATE employees
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

This statement does not go through V_EMPLOYEE_REPORT. To prevent users from modifying underlying data, manage privileges on base tables and grant appropriate privileges on views.

### 7.2. READ ONLY and CHECK OPTION Serve Different Goals

| Attribute | WITH CHECK OPTION | WITH READ ONLY |
| --- | --- | --- |
| SELECT | Allowed | Allowed |
| INSERT through view | Allowed if row satisfies condition and view is insertable | Forbidden |
| UPDATE through view | Allowed if modified row still satisfies condition and view is updatable | Forbidden |
| DELETE through view | Can be allowed if view is updatable | Forbidden |
| Goal | Keep rows within view condition scope | Allow reading only through the view |

These two options express different policies; do not combine both as if they complement the same behavior. When read-only is required, use WITH READ ONLY. When DML is allowed but the predicate must be preserved, use WITH CHECK OPTION.

## 8. Checking Updatability Metadata

Oracle provides data dictionary views to inspect which columns of a view can be inserted, updated, or deleted according to database-determined updatability.

Example:

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name = 'V_EMPLOYEE_EDIT'
ORDER BY column_name;
~~~

Columns:
- UPDATABLE: column can be updated through the view.
- INSERTABLE: column can be included in an INSERT operation through the view.
- DELETABLE: metadata indicating delete capability through the view per view rules.

View names in the data dictionary are typically stored in uppercase if created without quoted identifiers. If the view belongs to another schema, query ALL_UPDATABLE_COLUMNS or DBA_UPDATABLE_COLUMNS as permitted.

### 8.1. Metadata Does Not Replace DML Testing

A column with UPDATABLE='YES' does not guarantee every UPDATE statement will succeed. A statement can still fail because:
- WHERE finds no matching rows.
- Base table constraints are violated.
- Base table triggers reject the change.
- Check option is violated.
- Privileges are missing.
- Locks or transaction conflicts occur.
- Bind values are invalid.

Metadata indicates capability at the view structure level; specific execution conditions still apply.

### 8.2. Viewing View Definitions

~~~sql
SELECT view_name,
       text
FROM user_views
WHERE view_name = 'V_EMPLOYEE_EDIT';
~~~

USER_VIEWS shows view definitions in the current schema. ALL_VIEWS and DBA_VIEWS provide broader scope based on privileges.

The view definition helps check:
- Which columns map directly to base tables.
- Whether JOINs exist.
- Which WHERE predicates are applied.
- Whether aggregates, DISTINCT, or DML-restricting constructs exist.
- Whether a check option or read-only clause exists in corresponding metadata.

## 9. INSTEAD OF Triggers for Non-Updatable Views

Some views are designed to present aggregated data or combine multiple tables. Automatic DML mapping is ambiguous, yet applications still want to perform operations against the view interface.

Oracle supports **INSTEAD OF triggers** on views. The trigger runs instead of the DML operation sent to the view and explicitly issues INSERT/UPDATE/DELETE statements against base tables.

Example view joining EMPLOYEE and DEPARTMENT:

~~~sql
CREATE OR REPLACE VIEW v_employee_department_report AS
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

To allow an INSERT on the view to create an employee row, an INSTEAD OF trigger can map the columns:

~~~sql
CREATE OR REPLACE TRIGGER trg_v_emp_dept_insert
INSTEAD OF INSERT ON v_employee_department_report
FOR EACH ROW
BEGIN
    INSERT INTO employees (
        employee_id,
        full_name,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.full_name,
        :NEW.department_id
    );
END;
/
~~~

The trigger inserts only into EMPLOYEES. DEPARTMENT_NAME is exposed in the view but is not used to create DEPARTMENTS rows. DEPARTMENT_ID must reference an existing department; foreign keys enforce this.

### 9.1. INSTEAD OF Triggers Must Define Rules Explicitly

If a view contains multiple tables, the trigger must decide:
- Which columns are written to which table.
- On INSERT, whether to create rows across multiple base tables.
- On UPDATE, how to identify keys for each table.
- On DELETE, which table to delete from and in what order.
- How to handle constraints, duplicates, NULLs, and errors.
- Whether changes must remain atomic within the same transaction.

A trigger does not automatically make an ambiguous operation business-valid. It merely provides a place to program the mapping rules.

### 9.2. INSTEAD OF Triggers and Transactions

DML inside a standard trigger participates in the calling statement's transaction. If the trigger raises an error and the statement fails, statement changes are rolled back per statement-level rules. Transaction COMMIT/ROLLBACK should be managed by the caller; do not place arbitrary COMMIT statements inside triggers.

Do not use autonomous transactions for the main DML of an INSTEAD OF trigger if base table changes must roll back with the view statement.

### 9.3. INSTEAD OF Triggers Are Not the Default for Every View

If a view is simple and natively updatable, do not add a trigger just to forward a direct UPDATE to the base table. Triggers add complexity:
- Harder to trace actual DML.
- Can introduce inconsistent bidirectional update logic.
- Require testing many NULL/duplicate edge cases.
- Can impact performance.
- Prone to unpredictable side effects.

Use them only when the view genuinely needs a customized DML interface.

## 10. Full Example: Key Preservation and DML

This section creates two sandbox tables, a JOIN view, and a view with check option to observe the rules in action.

### 10.1. Create the Department Table

~~~sql
CREATE TABLE dept_view_demo (
    department_id   NUMBER(4)
        CONSTRAINT pk_dept_view_demo PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);
~~~

### 10.2. Create the Employee Table

~~~sql
CREATE TABLE emp_view_demo (
    employee_id   NUMBER(6)
        CONSTRAINT pk_emp_view_demo PRIMARY KEY,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    department_id NUMBER(4) NOT NULL,
    salary        NUMBER(12,2),
    status        VARCHAR2(10 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT fk_emp_dept_view_demo
        FOREIGN KEY (department_id)
        REFERENCES dept_view_demo(department_id),
    CONSTRAINT ck_emp_status_view_demo
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

### 10.3. Load Data

~~~sql
INSERT INTO dept_view_demo VALUES (10, 'Sales');
INSERT INTO dept_view_demo VALUES (20, 'Engineering');

INSERT INTO emp_view_demo
VALUES (101, 'An', 10, 20000000, 'ACTIVE');

INSERT INTO emp_view_demo
VALUES (102, 'Binh', 10, 18000000, 'ACTIVE');

INSERT INTO emp_view_demo
VALUES (201, 'Chi', 20, 30000000, 'ACTIVE');

COMMIT;
~~~

Department 10 has two employees; department 20 has one employee.

### 10.4. Create the Join View

~~~sql
CREATE OR REPLACE VIEW v_emp_dept_demo AS
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary,
       d.department_name
FROM emp_view_demo e
JOIN dept_view_demo d
  ON d.department_id = e.department_id;
~~~

EMP_VIEW_DEMO is key-preserved because EMPLOYEE_ID remains unique in the result. DEPT_VIEW_DEMO is not key-preserved because the department 10 row appears twice.

### 10.5. UPDATE Employee Column Through the View

~~~sql
UPDATE v_emp_dept_demo
SET salary = 21000000
WHERE employee_id = 101;

COMMIT;
~~~

The statement updates EMP_VIEW_DEMO.SALARY. Verify:

~~~sql
SELECT employee_id, salary
FROM emp_view_demo
WHERE employee_id = 101;
~~~

SALARY is 21,000,000.

### 10.6. Attempt to UPDATE Department Column Through the View

~~~sql
-- May raise ORA-01779 because DEPT_VIEW_DEMO is not key-preserved.
UPDATE v_emp_dept_demo
SET department_name = 'Sales North'
WHERE employee_id = 101;
~~~

The statement attempts to modify a column of a non-key-preserved table in the join view. Update the department name directly instead:

~~~sql
UPDATE dept_view_demo
SET department_name = 'Sales North'
WHERE department_id = 10;

COMMIT;
~~~

Both employees in department 10 will see the new department name when querying the view.

### 10.7. Create a View with WITH CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_emp_active_demo AS
SELECT employee_id,
       full_name,
       department_id,
       salary,
       status
FROM emp_view_demo
WHERE status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT v_emp_active_ck_demo;
~~~

Attempt to update status:

~~~sql
UPDATE v_emp_active_demo
SET status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle rejects it because the updated row no longer satisfies STATUS='ACTIVE'. Try changing SALARY instead; that operation still satisfies the predicate and can succeed:

~~~sql
UPDATE v_emp_active_demo
SET salary = salary + 500000
WHERE employee_id = 101;

COMMIT;
~~~

### 10.8. Create a READ ONLY View

~~~sql
CREATE OR REPLACE VIEW v_emp_report_ro_demo AS
SELECT employee_id,
       full_name,
       department_id,
       salary
FROM emp_view_demo
WITH READ ONLY;
~~~

SELECT through the view is valid. UPDATE through the view is rejected:

~~~sql
UPDATE v_emp_report_ro_demo
SET salary = salary + 100000
WHERE employee_id = 101;
~~~

However, if the user has privileges on the base table, updating EMP_VIEW_DEMO directly is a separate operation that does not pass through the READ ONLY view.

### 10.9. Inspect Metadata

~~~sql
SELECT table_name,
       column_name,
       updatable,
       insertable,
       deletable
FROM user_updatable_columns
WHERE table_name IN (
    'V_EMP_DEPT_DEMO',
    'V_EMP_ACTIVE_DEMO',
    'V_EMP_REPORT_RO_DEMO'
)
ORDER BY table_name, column_name;
~~~

The output shows how Oracle classifies updatability for each column in these views. Do not assume all columns in a join view share the same status.

### 10.10. Clean Up Sandbox Tables

~~~sql
DROP VIEW v_emp_report_ro_demo;
DROP VIEW v_emp_active_demo;
DROP VIEW v_emp_dept_demo;

DROP TABLE emp_view_demo PURGE;
DROP TABLE dept_view_demo PURGE;
~~~

Drop only sandbox objects created by this lesson when you are certain the data is no longer needed. DROP is DDL and issues an implicit commit; perform cleanup separately rather than mixing it with DML transactions that may need rollback.

## 11. Common Oracle Errors

| Error Code | Common Meaning in View Context | Resolution |
| --- | --- | --- |
| ORA-01779 | Updating a column mapped to a non-key-preserved table in a join view | Update the base table directly or redesign the view/constraints |
| ORA-01776 | A single DML statement through a join view attempts to modify multiple base tables | Split into multiple DML statements in the same transaction or use a clearly defined INSTEAD OF trigger |
| ORA-01752 | DELETE through a join view cannot identify exactly one key-preserved table | DELETE directly from the base table or design an appropriate view |
| ORA-01732 | Data manipulation operation not legal on this view | Check aggregates, DISTINCT, GROUP BY, set operators, and view structure |
| ORA-01402 | DML violates WHERE clause of a view with WITH CHECK OPTION | Keep rows within predicate or revise business requirements |
| ORA-42399 | DML attempted on a view declared WITH READ ONLY | Read only through the view or use a separately privileged write interface |
| ORA-01400 | INSERT supplies NULL for a NOT NULL column of the base table | Provide a value or configure a valid default |
| ORA-02291 | Foreign key value has no corresponding parent row | Create/select a valid parent key before INSERT/UPDATE |

Specific error messages may depend on the view structure and DML statement. When diagnosing, inspect the view definition, constraints, triggers, and the specific column being updated.

## 12. Access Privileges and Security When Using Views

A view can provide an interface exposing only a subset of data:

~~~sql
CREATE OR REPLACE VIEW v_employee_directory AS
SELECT employee_id,
       full_name,
       department_id
FROM employees;
~~~

A DBA can grant SELECT on the view to a user instead of granting SELECT on the entire base table, depending on the privilege and ownership model.

~~~sql
GRANT SELECT ON v_employee_directory TO reporting_user;
~~~

If the user only has privileges through the view, they can read the columns exposed by the view via the appropriate privilege chain. To allow DML through the view, check required privileges on the view/base tables, object ownership, and Oracle's privilege mechanisms.

**WITH READ ONLY is not a complete authorization mechanism.** It prevents DML through the view but does not revoke direct DML privileges on the base table. Security must be designed with GRANT/REVOKE, schema ownership, VPD, or appropriate mechanisms.

### 12.1. Row-Filtering Views Are Not Automatically an Absolute Security Boundary

A view with WHERE STATUS='ACTIVE' helps provide a restricted dataset. However, if a user has direct privileges on the base table, they can query rows outside the view. If row-level security must be enforced regardless of which object a query uses, consider Oracle Virtual Private Database (VPD) or database-tier security policies.

WITH CHECK OPTION only governs DML through the view; it is not a row-level security policy.

### 12.2. Grant DML Privileges on Views Deliberately

If an application only needs to update SALARY through a view, restrict privileges and columns to what is needed. Do not grant broader privileges than necessary. Whether DML actually succeeds also depends on base tables, view owner, invoker/definer rights, and Oracle privilege rules.

## 13. Designing Maintainable Updatable Views

When creating a view as a data-write interface:

- Include only necessary columns in the view.
- Keep column mappings direct; avoid unnecessary expressions on columns that need UPDATE.
- Place a WHERE clause representing a clear data scope.
- Use WITH CHECK OPTION if rows must remain within the view's scope after INSERT/UPDATE.
- Use WITH READ ONLY if the intent is read-only.
- For join views, establish key-preserved tables using PK/UNIQUE constraints and JOIN relationships.
- Do not attempt to modify two base tables in a single DML statement on a join view.
- Use an INSTEAD OF trigger when a custom DML interface is needed for a complex view.
- Check USER_UPDATABLE_COLUMNS and test DML in a sandbox schema.
- Verify triggers, foreign keys, NOT NULL, CHECK constraints, and access privileges.
- Document expected behavior when an UPDATE moves a row out of the view.
- Do not rely on a view as the sole security mechanism if users still hold direct base table privileges.

### 13.1. Updatable Does Not Mean Every DML Statement Will Succeed

A view marked updatable is still subject to rules:
- The WHERE clause may find no matching rows.
- UPDATE may violate a CHECK constraint.
- INSERT may omit a NOT NULL column.
- FK may not find a parent row.
- Base table triggers may reject the operation.
- Another transaction may hold locks.
- WITH CHECK OPTION may reject the modified row.

Updatability is a structural property of the view; whether a specific DML statement succeeds also depends on data, constraints, triggers, privileges, and concurrency.

## 14. Comparing Ways to Control DML Through Views

| Mechanism | Goal | Allows DML Through View? | Scope |
| --- | --- | --- | --- |
| Simple updatable view | Map DML directly to base table | Yes, for valid columns and structure | Single base table |
| Key-preserved join view | Allow modifying table whose key stays unique in join | With restrictions | Key-preserved table |
| WITH CHECK OPTION | Keep rows within view predicate | Yes, if view is updatable and row satisfies condition | DML through the view |
| WITH READ ONLY | Block all DML through the view | No | DML through that view |
| INSTEAD OF trigger | Define custom DML mapping on view | Yes, per trigger logic | Tables handled by the trigger |
| Table constraints | Protect data validity | Can block invalid DML | Base table |
| GRANT/REVOKE | Control who can access/modify | Per granted privileges | User/role and object |

No single mechanism completely replaces the others. A solid design combines views, constraints, privileges, and triggers according to specific requirements.

## 15. Process for Determining Whether a View Is Updatable

When encountering a view that needs DML, check in order:

1. Read the view definition in USER_VIEWS/ALL_VIEWS.
2. Determine whether the view is based on one table or multiple tables.
3. Check for DISTINCT, GROUP BY, HAVING, aggregates, or set operators.
4. Identify which columns map directly to base table columns and which are expressions.
5. If it is a join view, list PK/UNIQUE constraints of each table.
6. Check which table is key-preserved in the JOIN result.
7. Determine whether the DML statement intends to modify exactly one base table or multiple tables.
8. Check whether INSERT covers all NOT NULL columns and valid FK values.
9. If a WHERE predicate exists, decide whether WITH CHECK OPTION is needed.
10. If read-only, consider WITH READ ONLY and base table privileges.
11. If the view is not natively updatable but requires DML, design an INSTEAD OF trigger.
12. Inspect USER_UPDATABLE_COLUMNS.
13. Test INSERT/UPDATE/DELETE against sandbox data.
14. Verify errors, constraints, triggers, privileges, and transaction boundaries.
15. Confirm applications lack direct privileges bypassing the view policy if the view is used for security.

## 16. Common Misconceptions

**All views are read-only.** False. Simple views can permit DML if their structure and columns satisfy Oracle rules.

**All JOIN views are non-updatable.** False. Join views can allow modifying columns of a key-preserved table.

**A table with a primary key is always key-preserved in every join view.** False. Key preservation depends on whether the key remains unique in the JOIN result.

**Having no duplicates in current data is enough for Oracle to treat a table as key-preserved.** False. Oracle relies on appropriate constraint/unique metadata, not incidental current data.

**You can UPDATE columns of any table in a join view.** False. Columns must map to a key-preserved table and obey the one-base-table-per-DML limit.

**A single UPDATE through a join view can modify two base tables at once.** False. Split into separate DML statements within the same transaction or use a well-designed trigger.

**DELETE through a join view deletes from all joined tables.** False. Oracle identifies a single key-preserved table as the deletion target per join view rules.

**WITH CHECK OPTION prevents every UPDATE that modifies data.** False. It only prevents INSERT/UPDATE through the view from violating the view's condition; modifying other columns can still be allowed.

**WITH CHECK OPTION is a table-wide constraint.** False. Direct DML on the base table is not checked against the view's check option predicate.

**WITH READ ONLY locks the base table.** False. It blocks DML through the view, not direct DML on the base table.

**Views with a WHERE clause are automatically non-updatable.** False. WHERE can appear in updatable views; check option determines whether rows are allowed to leave the view's scope.

**Computed columns can be updated backward to source columns.** False. Oracle does not automatically infer inverse transformations for expression columns.

**INSTEAD OF triggers automatically make all DML safe.** False. The trigger itself must define mappings, keys, constraints, and transaction behavior.

**USER_UPDATABLE_COLUMNS='YES' guarantees an UPDATE statement will always succeed.** False. Constraints, triggers, privileges, data, and locks can still cause DML to fail.

## 17. Practice Exercises

1. Create a view selecting EMPLOYEE_ID, FULL_NAME, SALARY from EMPLOYEES. Test UPDATE through the view and verify the base table.
2. Create a view with WHERE STATUS='ACTIVE'. If you UPDATE STATUS to INACTIVE without CHECK OPTION, what happens to the row in the view?
3. Recreate the view with WITH CHECK OPTION and try the same UPDATE. Explain the error.
4. INSERT an ACTIVE row through a view with CHECK OPTION. Then try inserting an INACTIVE row.
5. Explain why WITH CHECK OPTION does not prevent direct UPDATEs on the base table.
6. Create a view with WITH READ ONLY. Test SELECT, INSERT, UPDATE, and DELETE.
7. If a view is READ ONLY but the user has UPDATE privilege on the base table, are direct operations on the base table blocked?
8. Create an EMPLOYEES JOIN DEPARTMENTS view. Identify which table is key-preserved in a one-department-to-many-employees relationship.
9. Why is DEPARTMENTS not key-preserved in a join view if each department has multiple employees?
10. Test updating FULL_NAME through the join view. Explain why it can succeed.
11. Test updating DEPARTMENT_NAME through the join view. Explain ORA-01779.
12. Why can't FULL_NAME and DEPARTMENT_NAME be modified in the same UPDATE through a join view?
13. Write two direct UPDATE statements on both tables within the same transaction and COMMIT.
14. Test inserting an employee through the join view using columns belonging to EMPLOYEES. Which FK condition must be satisfied?
15. Why can't inserting a row into both EMPLOYEES and DEPARTMENTS be performed by a single INSERT through a standard join view?
16. Explain ORA-01752 when deleting from a join view with multiple key-preserved tables or without exactly one eligible table.
17. Create an aggregate view with COUNT(*) by DEPARTMENT_ID. Why can't the view automatically identify an employee row to UPDATE?
18. Query USER_UPDATABLE_COLUMNS and explain UPDATABLE, INSERTABLE, and DELETABLE.
19. Create an INSTEAD OF trigger on a join view to INSERT into EMPLOYEES. Is the DEPARTMENT_NAME column used?
20. If an INSTEAD OF trigger raises an error, to what scope are the view DML statement's changes rolled back?
21. Why should you not COMMIT inside a normal trigger?
22. Compare WITH CHECK OPTION and WITH READ ONLY.
23. A view filtering STATUS='ACTIVE' is used as a security interface. Why must direct privileges on the base table be audited?
24. When should VPD be used instead of relying solely on WHERE in a view?
25. A view has column SALARY*12 AS ANNUAL_SALARY. Which column can be updated and why?
26. Create nested views with two WHERE conditions and CHECK OPTION. Identify which predicates must be preserved.
27. Explain why UNIQUE/PRIMARY KEY constraints are important for Oracle to determine key preservation.
28. A view has a WHERE clause without CHECK OPTION. What can happen when inserting through the view with values that do not satisfy WHERE?
29. When DML through a view fails with ORA-01732, which elements of the view definition should you inspect?
30. Design an updatable view for an application that is only allowed to modify ACTIVE employees in department 10, while ensuring UPDATEs cannot move rows to another department or INACTIVE status.

**An updatable view permits DML when Oracle can identify the base table row to modify. For join views, a key-preserved table determines which table can be safely modified; WITH CHECK OPTION keeps rows within the view's condition, while WITH READ ONLY blocks DML through the view.** When a complex view requires custom write rules, an INSTEAD OF trigger can map operations to base tables. Properly combining views, constraints, and privileges keeps the data interface clear while protecting data integrity.
