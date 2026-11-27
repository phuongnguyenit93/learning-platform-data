# Updatable Views and WITH CHECK OPTION

Views are commonly used as logical tables to simplify queries, restrict exposed columns, or create a business perspective over underlying tables. In MySQL, some views also allow direct INSERT, UPDATE, and DELETE operations. When a view has a filter condition, modifying data through the view can cause the newly written row to disappear from that very view. WITH CHECK OPTION helps prevent this situation by requiring inserted or updated rows to continue satisfying the view's condition.

In the DATABASE_MYSQL module, you need to understand two separate questions: whether a view is updatable, and if updatable, which conditions must remain satisfied after writing. This lesson explains updatable view criteria, how to use LOCAL/CASCADED CHECK OPTION, behavior when writing through nested views, and how to inspect metadata as well as access privileges.

## 1. What Is a View and When Is It Updatable?

A view is a database object that stores a SELECT definition. When querying a view, MySQL executes that definition to retrieve data from underlying tables or views. Regular views do not store a separate copy of data like materialized views; data is read from the source objects.

Example:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(120) NOT NULL,
    department_id INT NOT NULL,
    employment_status VARCHAR(20) NOT NULL,
    salary DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE=InnoDB;

INSERT INTO employees
    (employee_id, employee_name, department_id, employment_status, salary)
VALUES
    (101, 'An', 10, 'ACTIVE', 1200.00),
    (102, 'Binh', 10, 'ACTIVE', 1500.00),
    (103, 'Chi', 20, 'INACTIVE', 1300.00);
~~~

Create a view showing only active employees:

~~~sql
CREATE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

Query the view:

~~~sql
SELECT *
FROM v_active_employees;
~~~

With this simple view, each view row corresponds directly to a row in employees. MySQL can identify the original row to modify when receiving UPDATE or DELETE through the view. This is the core characteristic of an updatable view: there must be a sufficiently clear mapping between view rows and source table rows.

Try updating:

~~~sql
UPDATE v_active_employees
SET salary = 1600.00
WHERE employee_id = 101;
~~~

If the view meets updatability conditions and the user has the required privileges, the statement modifies the corresponding row in the employees table.

## 2. Characteristics That Often Make a View Non-Updatable

MySQL cannot update through a view when it cannot map a result row to a single source row or when the result consists of aggregated data. Constructs that typically make a view non-updatable include:

- Aggregate functions such as SUM, COUNT, AVG, MIN, or MAX.
- DISTINCT.
- GROUP BY or HAVING.
- UNION or UNION ALL.
- Certain JOIN constructs that do not preserve a clear row mapping.
- Subqueries in the select list.
- An underlying view that is itself non-updatable.
- ALGORITHM=TEMPTABLE.

Example of an aggregate view:

~~~sql
CREATE VIEW v_department_salary AS
SELECT
    department_id,
    AVG(salary) AS average_salary,
    COUNT(*) AS employee_count
FROM employees
GROUP BY department_id;
~~~

You cannot update average_salary and expect MySQL to deduce which employee's salary to change. This value is computed from multiple source rows, so there is no one-to-one mapping for executing DML.

Views with JOINs must be evaluated per definition. Some join views remain updatable if MySQL can identify the target table and appropriate row relationship; however, operations have restrictions. With multi-table views, a single UPDATE can only modify columns belonging to one source table per statement. INSERT through a join view is even more restricted and is generally unsuitable when rows need to be created simultaneously across multiple tables. When stable DML is needed, single-table views are usually easiest to understand and control.

Even when the overall view is deemed updatable, a column computed by an expression such as salary * 1.1 AS salary_with_bonus is not a direct source column to assign values to. Update the original column in the source table or via a direct column exposed by the view.

## 3. How ALGORITHM Affects Updatability

MySQL supports the following view processing algorithms:

| ALGORITHM | How It Works | Updatability |
|---|---|---|
| MERGE | Merges the view definition into the referencing query | Can be updatable if the view definition meets the conditions |
| TEMPTABLE | Creates an internal temporary table to hold view results | Not updatable |
| UNDEFINED | Lets MySQL choose the appropriate algorithm | Depends on the chosen algorithm and the view definition |

You can explicitly declare MERGE:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

MERGE does not turn an inherently non-updatable view into an updatable one. It only allows MySQL to process the view by merging the definition; conditions regarding row mapping and SELECT structure must still be satisfied.

If TEMPTABLE is declared, the view cannot be used as the target of INSERT, UPDATE, or DELETE. When DML through a view is required, do not choose TEMPTABLE. For general views, you can let MySQL decide with UNDEFINED and inspect the metadata.

## 4. The Problem When Updating Through a View with WHERE

The view v_active_employees only shows rows with employment_status = 'ACTIVE'. Without CHECK OPTION, a user could change a row so that it no longer satisfies the view's WHERE clause:

~~~sql
UPDATE v_active_employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 102;
~~~

If the view does not have CHECK OPTION, the statement may succeed because the source row still exists and is updatable. After the UPDATE, that row no longer satisfies employment_status = 'ACTIVE', so it disappears from v_active_employees results.

Similarly, INSERT through a view can create a row that does not satisfy the filter condition if the required columns are supplied and source table constraints permit:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (104, 'Dung', 10, 'INACTIVE', 1400.00);
~~~

After inserting, the row will not appear in the view. This often surprises applications because the write succeeds, yet a subsequent SELECT from the view does not see the newly written data.

## 5. What Problem Does WITH CHECK OPTION Solve?

WITH CHECK OPTION requires every row INSERTed or UPDATEd through the view to satisfy the view's condition after the operation. If the row fails the condition, MySQL rejects the change.

CHECK OPTION applies only to updatable views; it does not turn a view containing GROUP BY, DISTINCT, or other non-updatable constructs into a writable view.

Recreate the view with CHECK OPTION:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE VIEW v_active_employees AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
FROM employees
WHERE employment_status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Now try updating an ACTIVE row to INACTIVE:

~~~sql
UPDATE v_active_employees
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

MySQL rejects it because the updated row no longer satisfies the view's condition. The typical error is 1369 (CHECK OPTION failed).

Attempting to INSERT an INACTIVE row through the view is also rejected:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (105, 'Ha', 10, 'INACTIVE', 1450.00);
~~~

Meanwhile, INSERTing an ACTIVE row that satisfies the condition can succeed:

~~~sql
INSERT INTO v_active_employees (
    employee_id,
    employee_name,
    department_id,
    employment_status,
    salary
)
VALUES (106, 'Khanh', 10, 'ACTIVE', 1550.00);
~~~

CHECK OPTION does not replace PRIMARY KEY, UNIQUE, NOT NULL, CHECK constraints, or access privileges. It only checks the view's filter condition within the specified scope.

## 6. CHECK OPTION Checks INSERT and UPDATE, Not DELETE

CHECK OPTION ensures rows created or modified through the view continue to satisfy the view condition. DELETE does not create a new row or alter values to make a row leave the filter condition, so CHECK OPTION does not prevent DELETE.

Example:

~~~sql
DELETE FROM v_active_employees
WHERE employee_id = 106;
~~~

If the view is updatable and the user has DELETE privileges, the statement deletes the corresponding source row. CHECK OPTION does not turn a view into a read-only zone and does not restrict delete privileges.

If users are only allowed to view or edit a subset of data, you need to combine appropriate GRANT privileges, a properly designed view, and business rules at the application/database layer. Do not treat CHECK OPTION as a complete authorization mechanism.

## 7. LOCAL and CASCADED CHECK OPTION

The difference between LOCAL and CASCADED becomes clear when one view is defined on top of another view.

- LOCAL only checks the condition of the view being defined.
- CASCADED checks the condition of the current view and underlying views in the definition chain.
- If neither LOCAL nor CASCADED is specified, MySQL defaults to CASCADED.

### Creating an Underlying View Without CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_staff_active AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM employees
WHERE employment_status = 'ACTIVE';
~~~

The underlying view only shows ACTIVE employees, but does not yet require rows written through it to maintain this condition.

### Nested View with LOCAL CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_department_10_local AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM v_staff_active
WHERE department_id = 10
WITH LOCAL CHECK OPTION;
~~~

LOCAL only checks the condition department_id = 10 of the current view. Because the underlying view v_staff_active has no CHECK OPTION and LOCAL does not check the underlying view's condition, a row with department_id = 10 but employment_status = 'INACTIVE' can be written through the nested view if other update conditions permit. After writing, that row will no longer appear in v_staff_active.

Test in a test environment:

~~~sql
INSERT INTO v_department_10_local (
    employee_id,
    employee_name,
    department_id,
    employment_status
)
VALUES (107, 'Lan', 10, 'INACTIVE');
~~~

### Nested View with CASCADED CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_department_10_cascaded AS
SELECT
    employee_id,
    employee_name,
    department_id,
    employment_status
FROM v_staff_active
WHERE department_id = 10
WITH CASCADED CHECK OPTION;
~~~

CASCADED checks both the condition department_id = 10 of the current view and employment_status = 'ACTIVE' of the underlying view. Therefore, an INSERT or UPDATE producing an INACTIVE row is rejected.

~~~sql
INSERT INTO v_department_10_cascaded (
    employee_id,
    employee_name,
    department_id,
    employment_status
)
VALUES (108, 'Minh', 10, 'INACTIVE');
~~~

This statement is rejected by the nested view's CHECK OPTION.

| Action Through Nested View | LOCAL | CASCADED |
|---|---|---|
| Write department_id other than 10 | Rejected | Rejected |
| Write department_id = 10, status = INACTIVE | May be accepted if underlying view has no CHECK OPTION | Rejected |
| Write department_id = 10, status = ACTIVE | Accepted if other constraints are satisfied | Accepted if other constraints are satisfied |

If you need to ensure all filter conditions across the view chain are checked on writes, use CASCADED. Do not rely on LOCAL to protect the underlying view's WHERE condition; LOCAL only enforces checking the current view's condition.

## 8. NULL Values and CHECK OPTION

A WHERE condition in SQL only selects rows when the expression evaluates to TRUE. Both FALSE and UNKNOWN are excluded. UNKNOWN typically occurs when a comparison involves NULL.

Example:

~~~sql
CREATE OR REPLACE VIEW v_high_salary AS
SELECT employee_id, employee_name, salary
FROM employees
WHERE salary >= 1000
WITH CHECK OPTION;
~~~

If salary is NULL, the expression salary >= 1000 evaluates to UNKNOWN. A row with NULL salary does not satisfy the view condition and cannot be INSERTed/UPDATEd through the view with CHECK OPTION. In the example schema, salary is NOT NULL so this situation does not arise; if a column allows NULL, explicitly define the business rule.

Do not use COALESCE or default values inside the view merely to make CHECK OPTION easier to pass. Decide clearly whether NULL is allowed and what data rule the filter condition should reflect.

## 9. Hidden Columns and Requirements on INSERT

CHECK OPTION does not automatically populate required columns of the source table. If a view does not expose a NOT NULL column with no DEFAULT, an INSERT through the view can fail because the underlying table does not receive a value for that column.

For example, if employees additionally had:

~~~sql
hire_date DATE NOT NULL
~~~

but the view does not select hire_date, an INSERT through the view cannot supply the required value. You need to:

- Include the column in the view if users are permitted to supply the value.
- Declare a valid DEFAULT on the source table if business rules allow.
- Use a stored procedure or write API if value-generation logic needs to be applied.

Do not confuse a missing required column error with a CHECK OPTION error. One comes from a source table constraint; the other comes from the view condition.

## 10. Checking Whether a View Is Updatable

MySQL provides metadata in INFORMATION_SCHEMA.VIEWS:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION,
    SECURITY_TYPE,
    DEFINER
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN (
      'v_active_employees',
      'v_active_employees_secure',
      'v_staff_active',
      'v_department_10_local',
      'v_department_10_cascaded'
  );
~~~

Useful columns:

- IS_UPDATABLE indicates whether MySQL evaluates the view as updatable.
- CHECK_OPTION indicates NONE, LOCAL, or CASCADED.
- SECURITY_TYPE indicates whether the view executes under DEFINER or INVOKER privileges.
- DEFINER indicates the account that defined the view.

Metadata helps confirm the state MySQL recognizes, though you should still test DML on test data to understand the exact behavior of the view definition.

You can inspect the view definition:

~~~sql
SHOW CREATE VIEW v_active_employees;
~~~

This command helps verify whether SELECT, ALGORITHM, DEFINER, SQL SECURITY, and CHECK OPTION were saved as expected.

## 11. Access Privileges When Writing Through a View

A view can use SQL SECURITY DEFINER or SQL SECURITY INVOKER:

- DEFINER: statements access underlying objects using the privileges of the view's defining account.
- INVOKER: statements access underlying objects using the privileges of the caller.

Example:

~~~sql
CREATE OR REPLACE ALGORITHM = MERGE
SQL SECURITY DEFINER
VIEW v_active_employees_secure AS
SELECT employee_id, employee_name, department_id, employment_status, salary
FROM employees
WHERE employment_status = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Users still need appropriate privileges on the view for SELECT, INSERT, UPDATE, or DELETE operations. With DEFINER, privileges on the source table are checked according to the view's security mechanism; with INVOKER, the caller must have the necessary privileges on accessed objects.

CHECK OPTION does not grant privileges and does not restrict a user to modifying only certain columns. If column restriction is needed, expose only the appropriate columns in the view and grant column/view privileges properly; also check privileges on source tables and related routines.

## 12. When Should You Use an Updatable View?

Updatable views are suitable when:

- An application needs a simple write interface over a single source table.
- You want to expose only a subset of columns to a user group.
- You want to restrict writable rows using a fixed condition.
- You want to encapsulate repeated filter conditions into a clearly named database object.

For example, an active employees view lets an application operate only on active staff. CHECK OPTION ensures updates through the view do not accidentally move rows out of the allowed dataset.

Do not use a view as the sole security boundary if there are many complex rules. Table constraints, GRANT privileges, stored procedures, and application-layer checks may need to work together to ensure integrity.

## 13. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Assuming every view is updatable | DML fails on aggregate views or views lacking row mapping | Check IS_UPDATABLE and the SELECT definition |
| Using GROUP BY/DISTINCT and trying to UPDATE | Cannot identify the source row to modify | Update the source table by specific key or use a routine |
| Forgetting CHECK OPTION | UPDATE can cause rows to vanish from the view | Add LOCAL/CASCADED according to the scope needing protection |
| Using LOCAL when underlying view conditions must be protected | Rows can violate underlying view conditions if the underlying view lacks CHECK OPTION | Use CASCADED |
| Thinking CHECK OPTION blocks DELETE | DELETE can still remove rows if privileges allow | Grant DELETE privileges at the appropriate level |
| Thinking CHECK OPTION replaces constraints | Duplicate key, NULL, or FK/NOT NULL errors can still happen | Keep constraints on source tables |
| Using ALGORITHM=TEMPTABLE for views needing DML | View becomes non-updatable | Use MERGE or UNDEFINED appropriately |
| Failing to check hidden required columns | INSERT through the view fails | Expose the column, use DEFAULT, or use a routine |

## 14. Process for Designing an Updatable View

1. Identify the source table and the business rows the view represents.
2. Select columns to expose; keep identifying keys so MySQL can map rows.
3. Write a simple SELECT, avoiding aggregates, DISTINCT, GROUP BY, HAVING, and UNION if DML is needed.
4. Check required columns of the source table and DEFAULT values.
5. Choose an appropriate ALGORITHM; do not use TEMPTABLE if updates are needed.
6. Define the WHERE condition that every row written through the view must satisfy.
7. Choose WITH LOCAL CHECK OPTION or WITH CASCADED CHECK OPTION based on the view chain.
8. Verify IS_UPDATABLE and CHECK_OPTION in INFORMATION_SCHEMA.VIEWS.
9. Test INSERT/UPDATE that keeps rows satisfying the condition, and test violating operations to confirm rejection.
10. Test NULLs, duplicate keys, and source columns omitted from the view.
11. Verify SELECT/INSERT/UPDATE/DELETE privileges and SQL SECURITY.
12. Document write-through-view rules so applications do not make wrong assumptions about newly updated rows.

## 15. Hands-on Exercises

1. Create the employees table from the example and create a view showing only ACTIVE employees.
2. UPDATE an employee's status to INACTIVE through a view without CHECK OPTION; confirm the row disappears from the view while remaining in the source table.
3. Recreate the view with WITH CASCADED CHECK OPTION; try the same UPDATE and read the error.
4. INSERT one ACTIVE employee and one INACTIVE employee through the view; compare the results.
5. Create view v_staff_active without CHECK OPTION and a nested view filtering department_id = 10 with LOCAL CHECK OPTION; try writing an INACTIVE row in department 10.
6. Recreate the nested view with CASCADED CHECK OPTION; confirm the underlying view's employment_status condition is also checked.
7. Try creating an aggregate view grouped by department_id and inspect IS_UPDATABLE.
8. Compare SHOW CREATE VIEW and INFORMATION_SCHEMA.VIEWS for the created views.
9. Test a NOT NULL source column with no DEFAULT that is not exposed in the view; distinguish constraint errors from CHECK OPTION errors.
10. Create two views with SQL SECURITY DEFINER and INVOKER in a test environment; grant minimal privileges and observe DML operations.

You have completed this lesson when you can identify which views are updatable, explain why certain SELECT constructs cannot be updated, choose LOCAL or CASCADED CHECK OPTION appropriately, and demonstrate that rows violating conditions are rejected. Treat views as a data interface with explicit rules; constraints and privileges on source tables remain an essential layer of protection.
