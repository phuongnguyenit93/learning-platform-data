# Creating Views and Using Views as a Data Access Boundary in Oracle

An application often does not need to know the entire internal table structure in a database. An employee directory screen only needs the ID, name, department, and work email; it does not need salary, banking information, or internal processing status. If the application is granted `SELECT` directly on the employee table, every query from the application can read columns it does not need. By creating a **view** that exposes only the permitted columns and rows, and then granting privileges on the view instead of the base table, the database can provide a clearer access contract.

In Oracle, a standard view is a schema object that stores a query definition. When a user queries a view, Oracle executes the view's defining query combined with the conditions of the outer query. A view does not store a copy of the results like a physical table or a materialized view. Therefore, a view acts both as a data structure abstraction layer and potentially as a privilege boundary if permissions on the underlying tables are managed properly.

This lesson belongs to the **Schema Objects** section of Database Engine Relational Oracle. It covers how to create and alter views, expose column/row contracts, grant least privilege, restrict DML with `WITH CHECK OPTION` or `WITH READ ONLY`, handle complex views with `INSTEAD OF` triggers, manage dependencies, and understand the impact of views on the optimizer.

After this lesson, you will be able to:

- Create views with CREATE VIEW and modify definitions with CREATE OR REPLACE VIEW.
- Design views with explicit column lists, stable column names, and clear business predicates.
- Use views as an access layer for applications without granting direct privileges on underlying tables.
- Understand the privileges required by the view owner and the privileges to grant to application users.
- Distinguish updatable views from read-only views.
- Use WITH CHECK OPTION, WITH READ ONLY, and INSTEAD OF triggers for their intended purposes.
- Inspect dependencies, INVALID status, and view compilation errors.
- Distinguish standard views, inline views, CTEs, synonyms, and materialized views.
- Evaluate views in execution plans and recognize the security limitations of views.

> **Example scope:** Statements use Oracle Database 19c syntax. Practice tables have the _LAB suffix. Run them in a dedicated lab schema. CREATE VIEW privileges, access to objects in other schemas, and grants to users/roles depend on database administration configuration.

## 1. What Is a View?

A view is a schema object containing the definition of a query. Users query a view just like querying a table:

~~~sql
SELECT employee_id, full_name, department_id
FROM v_employee_directory
WHERE department_id = 20;
~~~

A view definition can read from one or more tables, other views, or permitted data objects. A view can:

- Select only certain columns.
- Display only rows matching a condition.
- Rename columns or expressions to create a user-friendly interface.
- Combine multiple tables.
- Aggregate data using GROUP BY.
- Hide part of the physical structure and underlying query logic.

### 1.1. Standard Views Do Not Store Results

~~~text
APPLICATION USER
       |
       | SELECT
       v
   VIEW OBJECT
       |
       | stored query definition
       v
  BASE TABLE(S)
       |
       v
  CURRENT COMMITTED DATA
~~~

A standard view stores its query in the data dictionary. When queried, Oracle optimizes and executes the SQL statement based on the view and its underlying objects. If table data changes and the transaction is committed, subsequent queries against the view can see the new data according to read consistency.

This means a view does not automatically speed up queries. Nor is it a fixed snapshot of the data. If you need to store precomputed results, look into materialized views.

### 1.2. Why Use Views?

| Goal | How a View Helps |
| --- | --- |
| Simplify queries | Encapsulates repeated JOINs, expressions, or conditions |
| Stabilize data interface | Applications depend on view names/columns rather than internal table structures |
| Restrict columns | Exposes only necessary columns |
| Restrict rows | Exposes a subset of rows based on a predicate |
| Grant least privilege | Grants SELECT/DML on the view instead of the base table |
| Reporting | Provides a consistent read model across multiple reports |

Views are part of schema design. They do not replace primary keys, foreign keys, check constraints, row-level security, or access controls at other layers.

## 2. CREATE VIEW Syntax

Basic syntax:

~~~sql
CREATE [OR REPLACE] [FORCE | NOFORCE] VIEW view_name
    [(column_alias_1, column_alias_2, ...)]
AS
    subquery
[WITH CHECK OPTION [CONSTRAINT constraint_name]
 | WITH READ ONLY];
~~~

Key components:

- CREATE VIEW: creates a new view.
- OR REPLACE: replaces the definition of an existing view.
- FORCE/NOFORCE: controls view creation when underlying objects or privileges are not yet ready; NOFORCE is the default.
- Alias list: specifies column names for the view, useful for expressions or standardizing column names.
- AS subquery: the query defining the view.
- WITH CHECK OPTION: enforces that DML through the view keeps rows matching the view's condition.
- WITH READ ONLY: disallows DML through the view.

### 2.1. Use an Explicit Column List

Example:

~~~sql
CREATE VIEW v_department_employee AS
SELECT
    department_id,
    employee_id,
    full_name,
    work_email
FROM employee_data_lab;
~~~

You should list the columns to expose instead of using SELECT *. When new columns are added to the base table, an already created view definition will not automatically become a contract exposing all new columns. An explicit list also helps readers immediately see what information the view grants access to.

### 2.2. Provide Aliases for Expressions

~~~sql
CREATE VIEW v_department_payroll (
    department_id,
    employee_count,
    total_salary
) AS
SELECT
    department_id,
    COUNT(*),
    SUM(monthly_salary)
FROM employee_data_lab
GROUP BY department_id;
~~~

View column names are part of the interface that applications consume. Choose stable, business-meaningful names that do not depend on the internal naming conventions of a specific table.

### 2.3. CREATE OR REPLACE VIEW

~~~sql
CREATE OR REPLACE VIEW v_department_employee AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

OR REPLACE updates the definition of an existing view without needing to DROP it first. This is the standard way to deploy changes. However, changing column names, datatypes, order, or view semantics can break applications and dependent objects. Before changing a contract, check the consumers using the view.

### 2.4. FORCE and NOFORCE

NOFORCE is the default: Oracle requires the underlying objects and required privileges to be valid in order to create the view.

FORCE allows creating a view even when some underlying objects do not yet exist or some checks are not satisfied; the view may remain in an INVALID state until the dependencies are ready and the view is recompiled. FORCE is useful in certain ordered deployment scenarios, but it does not make the view valid for querying and does not grant additional privileges.

~~~sql
CREATE FORCE VIEW v_future_source AS
SELECT id, description
FROM future_source_table;
~~~

Do not use FORCE to mask missing dependency errors during normal deployments. If a view is invalid, inspect USER_ERRORS/ALL_ERRORS and fix the root cause.

## 3. Preparing the Lab Schema

### 3.1. Create the Employee Table

~~~sql
CREATE TABLE employee_data_lab (
    employee_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    work_email VARCHAR2(120 CHAR),
    monthly_salary NUMBER(12,2) NOT NULL,
    employment_status VARCHAR2(12 CHAR) NOT NULL,
    bank_account_ref VARCHAR2(40 CHAR),
    CONSTRAINT ck_employee_salary_lab
        CHECK (monthly_salary >= 0),
    CONSTRAINT ck_employee_status_lab
        CHECK (employment_status IN ('ACTIVE', 'INACTIVE', 'LEAVE'))
);
~~~

The table contains public columns for the directory, salary columns for HR reports with separate privileges, and a bank account reference that should not appear in a standard directory view.

### 3.2. Load Sample Data

~~~sql
INSERT INTO employee_data_lab VALUES
    (101, 'Nguyen An', 10, 'an@example.test', 2500, 'ACTIVE', 'BANK-REF-A');

INSERT INTO employee_data_lab VALUES
    (102, 'Tran Binh', 10, 'binh@example.test', 3200, 'ACTIVE', 'BANK-REF-B');

INSERT INTO employee_data_lab VALUES
    (103, 'Le Chi', 20, 'chi@example.test', 2800, 'ACTIVE', 'BANK-REF-C');

INSERT INTO employee_data_lab VALUES
    (104, 'Pham Dung', 20, 'dung@example.test', 3000, 'INACTIVE', 'BANK-REF-D');

COMMIT;
~~~

## 4. Creating Views as Access Contracts

### 4.1. Directory View Exposing Only Required Columns

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

This view:

- Exposes only employee_id, full_name, department_id, and work_email.
- Does not expose monthly_salary or bank_account_ref.
- Displays only employees whose employment_status is ACTIVE.
- Disallows DML through the view due to WITH READ ONLY.

The directory application can query:

~~~sql
SELECT employee_id, full_name, work_email
FROM v_employee_directory_lab
WHERE department_id = 10
ORDER BY full_name;
~~~

The application does not need to know that bank_account_ref exists. When the internal schema changes, the view can preserve the contract for consumers if the view definition is adjusted accordingly.

### 4.2. Aggregation View for Reporting

~~~sql
CREATE OR REPLACE VIEW v_department_payroll_lab AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_monthly_salary,
    AVG(monthly_salary) AS average_monthly_salary
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
GROUP BY department_id;
~~~

Reports that only need employee headcount and total salary by department can read from the view instead of duplicating the ACTIVE filter and GROUP BY logic. This is an aggregate view, and normally aggregated values cannot be updated directly through the view.

### 4.3. Multi-Table Join View

A view can encapsulate a JOIN:

~~~sql
CREATE TABLE department_data_lab (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

INSERT INTO department_data_lab VALUES (10, 'Engineering');
INSERT INTO department_data_lab VALUES (20, 'Finance');
COMMIT;

CREATE OR REPLACE VIEW v_employee_department_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.work_email,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id
WHERE e.employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

Consumers use a single interface even though the data is stored across two tables. The view also keeps JOIN logic and predicates in one place instead of duplicating them across multiple applications.

## 5. Views as a Data Access Boundary

A common architectural pattern separates the data-owning schema, the view-owning schema, and the application user:

~~~text
DATA_OWNER
  owns EMPLOYEE_DATA
  grants SELECT directly to REPORT_OWNER
           |
           v
REPORT_OWNER
  owns V_EMPLOYEE_DIRECTORY
  grants SELECT on the view to APP_READER_ROLE
           |
           v
APPLICATION USER
  receives APP_READER_ROLE
  queries the view
~~~

Schema separation helps control who can alter tables, who defines view contracts, and who is only allowed to read exposed data.

### 5.1. Privileges Required to Create a View

A user creating a view needs the CREATE VIEW system privilege in their own schema. If creating a view in another schema, appropriate CREATE ANY VIEW privileges are required and must comply with governance policies.

For underlying tables/views in another schema, the view owner must be granted the required object privileges directly. Privileges received through a role are not sufficient to define a stored view. For example:

~~~sql
-- Run by DATA_OWNER:
GRANT SELECT ON employee_data_lab TO report_owner;
~~~

Then REPORT_OWNER can create a view referencing the table on which it holds direct privileges:

~~~sql
-- Run in the REPORT_OWNER schema:
CREATE OR REPLACE VIEW v_employee_directory AS
SELECT employee_id, full_name, department_id, work_email
FROM data_owner.employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

If REPORT_OWNER only has SELECT privilege through a role, view creation may fail because stored objects require direct grants on dependencies.

### 5.2. Granting Privileges on a View to an Application

~~~sql
-- Create role if it does not exist:
CREATE ROLE app_employee_reader;

-- View owner grants privilege on the view:
GRANT SELECT ON v_employee_directory TO app_employee_reader;

-- DBA or user with grant role privilege grants the role to the app user:
GRANT app_employee_reader TO app_reader;
~~~

APP_READER can SELECT from the view via the role. The application user does not need direct SELECT granted on DATA_OWNER.EMPLOYEE_DATA if the goal is read-only access through the view.

### 5.3. Why Can a View Work When the User Lacks Base Table Privileges?

When a user queries a view, Oracle checks privileges on the view and the view owner's privileges on the underlying objects according to the view mechanism. Consequently, a user can be granted SELECT on the view without being granted direct SELECT on the base tables.

This is the foundation for using views as an access boundary. Verify that the view owner has direct privileges and the application receives only the necessary object privileges.

### 5.4. Views Do Not Protect Tables If Users Still Have Direct Privileges

If APP_READER also has:

~~~sql
GRANT SELECT ON data_owner.employee_data_lab TO app_reader;
~~~

then the user can bypass the view and query the base table directly. A view cannot restrict a broader privilege granted elsewhere.

For a view to act as a real boundary:

- Do not grant direct privileges on base tables to application users/roles.
- Do not grant broad privileges such as SELECT ANY TABLE unless necessary.
- Grant only the exact SELECT or DML privileges on the designed views.
- Audit privileges inherited through roles and other grants.
- Separate owner/schema accounts from application runtime accounts.

### 5.5. Views Restricting Columns and Rows

The directory view above restricts both columns and rows. This is a straightforward way to separate consumers by purpose:

| Consumer | Granted View | Exposed Data |
| --- | --- | --- |
| Internal directory | V_EMPLOYEE_DIRECTORY | ID, name, department, email |
| Payroll report | V_DEPARTMENT_PAYROLL | Aggregated salary by department |
| HR administration | Specialized view with broader privileges | HR data scoped by role |

Avoid creating an "all purpose" view containing every column and granting it to all applications. Multiple smaller views tailored to business contracts make privileges easier to audit and reduce data exposure risk.

### 5.6. Are Views a Complete Security Mechanism?

No. A view is a useful privilege and abstraction layer, but it must sit within an overall security model:

- If a user has base table privileges, they can bypass the view.
- If a user has broad system-level privileges, a view does not narrow those privileges.
- Static predicates in a view filter only by defined logic; they do not inherently understand tenant/user identity.
- If dynamic row policies per user/tenant across multiple access paths are needed, evaluate Oracle Virtual Private Database (VPD/FGAC), trusted application contexts, or an appropriate row-level security mechanism.
- Do not allow clients to set a spoofable context to bypass security predicates.

A view filtering tenants via SYS_CONTEXT is only secure when the context is set and protected by a trusted mechanism; do not treat a WHERE clause in a view as a complete substitute for VPD.

## 6. DML Through Views: Which Views Are Updatable?

Not all views are read-only. Some simple views allow INSERT, UPDATE, and DELETE to pass through the view to the underlying table.

### 6.1. Simple Views

~~~sql
CREATE OR REPLACE VIEW v_employee_edit_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

Example update through the view:

~~~sql
UPDATE v_employee_edit_lab
SET work_email = 'new-address@example.test'
WHERE employee_id = 101;

COMMIT;
~~~

Oracle applies the change to the base table. The view is an access interface, not an independent copy of the data.

### 6.2. Characteristics That Typically Make a View Non-Updatable

A view may not be directly updatable when its query contains constructs such as:

- Aggregate functions or GROUP BY.
- DISTINCT.
- Set operators such as UNION/UNION ALL, INTERSECT, or MINUS.
- Certain computed expressions or derived columns that do not map directly to a table column.
- A join view where the target table to modify is not identified as key-preserved.
- Other constructs restricted by Oracle's DML-through-view rules.

Example of an aggregate view:

~~~sql
CREATE OR REPLACE VIEW v_department_payroll_readonly_lab AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_salary
FROM employee_data_lab
GROUP BY department_id;
~~~

You cannot update total_salary as though it were a physical column of a single employee. This value is computed across multiple rows.

### 6.3. Key-Preserved Tables in Join Views

For a multi-table JOIN view, Oracle must determine which table has its key preserved in the JOIN result. A table is key-preserved when every row of that table appears at most once in the join result based on proven key relationships.

Example:

~~~sql
CREATE OR REPLACE VIEW v_employee_dept_edit_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id;
~~~

DEPARTMENT_DATA_LAB has primary key department_id. Each employee matches at most one department; thus employee rows are not duplicated by this join. The employee table can be key-preserved and certain updates to employee columns may be permitted, subject to Oracle's full updatable join view rules.

If a table is not key-preserved, Oracle may raise ORA-01779 when attempting to update columns of that table through the join view. You cannot conclude updatability solely from one side of the JOIN having a primary key; inspect the constraints, join conditions, and specific DML rules.

### 6.4. Computed Columns Cannot Automatically Write Back

~~~sql
CREATE OR REPLACE VIEW v_employee_compensation_lab AS
SELECT
    employee_id,
    monthly_salary,
    monthly_salary * 12 AS annual_salary
FROM employee_data_lab;
~~~

annual_salary is a computed expression. It does not correspond to an independent column in the base table. Updating annual_salary through the view has no natural reverse mapping back to monthly_salary without additional logic.

## 7. WITH CHECK OPTION: Keeping Rows Within View Scope

### 7.1. The Problem Without CHECK OPTION

View:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_edit_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE';
~~~

A user with UPDATE privilege on the view can update the status of a visible row:

~~~sql
UPDATE v_active_employee_edit_lab
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

If the view lacks CHECK OPTION, the operation can succeed; after the update, the row no longer satisfies the ACTIVE predicate and disappears from the view.

### 7.2. Adding WITH CHECK OPTION

~~~sql
CREATE OR REPLACE VIEW v_active_employee_checked_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT ck_active_employee_view_lab;
~~~

With CHECK OPTION, DML performed through the view must leave the row satisfying the view's condition. An UPDATE changing ACTIVE to INACTIVE through the view is rejected because the modified row would no longer be selected by the view.

### 7.3. CHECK OPTION Is Not a General Privilege Filter

CHECK OPTION governs DML through the view to preserve the view's predicate. It does not:

- Prevent a user with direct privileges on the base table from updating rows.
- Replace table-level constraints.
- Replace row-level security controls for other access paths.
- Enforce all multi-table business rules.

If the requirement is "the application may only modify active employees and cannot move rows outside the view's set," CHECK OPTION is an appropriate part of the design, alongside withholding base table privileges.

## 8. WITH READ ONLY: Publishing Read-Only Views

Example:

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_readonly_lab AS
SELECT employee_id, full_name, department_id, work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

WITH READ ONLY forbids INSERT, UPDATE, and DELETE through the view. This is a clear way to publish a query-only view.

Notes:

- READ ONLY applies only to DML through the view.
- It does not revoke direct DML privileges on the base table if the user has been granted them.
- A read-only view still reflects new data after transactions on the base table commit.
- If column/row restrictions are needed, you must still design the SELECT list and predicate properly.

For reporting or directory views, WITH READ ONLY generally makes the access contract clearer.

## 9. INSTEAD OF Triggers for Complex Views

A complex view may not be updatable under default rules. If business requirements call for allowing DML through the view, an INSTEAD OF trigger can define the actual actions against the underlying tables.

### 9.1. Example View Joining Department and Employee

~~~sql
CREATE OR REPLACE VIEW v_employee_department_api_lab AS
SELECT
    e.employee_id,
    e.full_name,
    e.department_id,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id;
~~~

Suppose we need to INSERT an employee through the view. A trigger can write to the employee table:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_dept_insert_lab
INSTEAD OF INSERT ON v_employee_department_api_lab
FOR EACH ROW
BEGIN
    INSERT INTO employee_data_lab (
        employee_id,
        full_name,
        department_id,
        work_email,
        monthly_salary,
        employment_status,
        bank_account_ref
    )
    VALUES (
        :NEW.employee_id,
        :NEW.full_name,
        :NEW.department_id,
        NULL,
        0,
        'ACTIVE',
        NULL
    );
END;
/
~~~

Here department_name is only a descriptive column fetched from the department table; the trigger uses department_id to create the employee row. The department table is not modified.

### 9.2. Responsibilities of an INSTEAD OF Trigger

The trigger must clearly define:

- Which columns are allowed for INSERT/UPDATE.
- Which data is written to which table.
- Behavior when a user attempts to change derived or read-only columns.
- How to handle nonexistent records or relationship violations.
- Ensuring transactions and errors propagate back to the caller.

Do not COMMIT inside a trigger to split up units of work. DML executed by the trigger participates in the calling statement's transaction; if the statement rolls back, changes made by the trigger roll back as well.

### 9.3. INSTEAD OF Triggers Are Not the Default for Every View

Triggers make write logic harder to see from outer SQL statements and can increase debugging complexity. Use them only when the view is an intentional data API and the DML mapping is clearly defined. If a simple table can be updated directly through a view, do not add a trigger merely to introduce an extra layer of indirection.

## 10. Views as a Stable Contract for Applications

### 10.1. Decoupling Physical Names from Business Names

An application can query:

~~~sql
SELECT employee_id, display_name, department_code
FROM api_employee_directory;
~~~

While the view maps these names from one or more internal tables:

~~~sql
CREATE OR REPLACE VIEW api_employee_directory (
    employee_id,
    display_name,
    department_code
) AS
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM employee_data_lab e
JOIN department_data_lab d
  ON d.department_id = e.department_id
WHERE e.employment_status = 'ACTIVE';
~~~

The application depends on the API view. Inside the database, the team can rename or split tables as long as the view's column/semantic contract is preserved.

### 10.2. View Contracts Must Also Stabilize Semantics

Not only column names need stability. Document clearly:

- Whether each row represents an employee, a department, or an aggregated record.
- Which rows are excluded by predicates.
- What NULL signifies.
- Currency units, time units, and timezones.
- Whether multiple rows can exist for the same business key.
- Whether DML is supported.
- Which privileges are granted to consumers.

Changing a view from "active employees" to "all employees" is a semantic change that can affect security and reporting even if the column schema remains unchanged.

### 10.3. Avoid SELECT * in API Views

SELECT * makes the contract opaque and can cause confusion when base tables change. List columns and aliases explicitly. When adding new columns, treat it as an intentional schema change, verify consumers, and update privileges appropriately.

### 10.4. Version Views on Breaking Changes

If a change breaks the existing contract, you can create a new version of the view:

~~~sql
CREATE VIEW api_employee_directory_v2 AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab;
~~~

Existing consumers continue using v1 during the transition window; new consumers use v2. Once no legacy consumers remain, privileges can be revoked and v1 retired according to plan.

## 11. Views, Inline Views, CTEs, Synonyms, and Materialized Views

These concepts serve different purposes:

| Object/Construct | Scope | Stores Results? | Used as Privilege Boundary? |
| --- | --- | --- | --- |
| Standard view | Reusable schema object | Does not store result set | Yes, via object privileges |
| Inline view | Query block in FROM of a single SQL statement | No | Not an independent privilege object |
| CTE (WITH clause) | Named query block within a single statement | No by default | Not an independent privilege object |
| Synonym | Alias for another object | No | No; does not grant privileges in place of target object |
| Materialized view | Schema object storing query results | Yes | Can grant object privileges, but requires refresh/data freshness management |

### 11.1. Inline View

~~~sql
SELECT department_id, employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employee_data_lab
    GROUP BY department_id
)
WHERE employee_count >= 2;
~~~

An inline view exists only within this SQL statement. If multiple applications need the same logic, a schema view may be easier to reuse and grant privileges on.

### 11.2. CTE

~~~sql
WITH active_employees AS (
    SELECT employee_id, department_id
    FROM employee_data_lab
    WHERE employment_status = 'ACTIVE'
)
SELECT department_id, COUNT(*)
FROM active_employees
GROUP BY department_id;
~~~

CTEs make multi-step SQL easier to read. They do not create a schema object and are not an independent privilege API.

### 11.3. Synonym

~~~sql
CREATE SYNONYM employee_directory
FOR report_owner.v_employee_directory;
~~~

Synonyms allow referencing an object by another name. They do not automatically grant SELECT on the view and do not make base tables safer. Users still need appropriate privileges on the target object.

### 11.4. Materialized View

A materialized view stores query results as physical data and provides refresh mechanisms. It is suitable when reducing repeated computation costs or supporting analytical reporting, provided data freshness and refresh strategy are managed.

~~~sql
CREATE MATERIALIZED VIEW mv_department_payroll_lab
BUILD IMMEDIATE
REFRESH COMPLETE ON DEMAND
AS
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(monthly_salary) AS total_salary
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
GROUP BY department_id;
~~~

This is only a basic structural example. FAST REFRESH and query rewrite capabilities depend on the definition, materialized view logs, constraints, query shape, and configuration. A materialized view is not automatically always faster or always up to date.

## 12. Views and Performance: What Does the Optimizer See?

### 12.1. Standard Views Are Not a Mandatory Physical Execution Layer

Example:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_lab AS
SELECT employee_id, department_id, full_name
FROM employee_data_lab
WHERE employment_status = 'ACTIVE';
~~~

Query:

~~~sql
SELECT employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;
~~~

The Oracle optimizer can merge the view into the outer query block (view merging) or push predicates down closer to the base table (predicate pushing) when the transformation is valid. The plan may access the base table directly and does not necessarily show a separate "VIEW" operation.

### 12.2. Do Not Assume Views Make Queries Faster

Standard views help reuse and manage logic. They do not automatically cache results. Performance depends on:

- Base table row count and predicate selectivity.
- Indexes and statistics.
- Join order, join method, and access path.
- Aggregate, DISTINCT, analytic, or set operations.
- The optimizer's ability to merge views / push predicates.
- Nesting depth of views and query complexity.

A complex view reused in many places can make queries hard to understand if consumers further nest additional views. Keep each view's grain and responsibility clear.

### 12.3. View Merging and Predicate Pushing

The optimizer can transform:

~~~sql
SELECT *
FROM v_active_employee_lab
WHERE department_id = 10;
~~~

into an equivalent query on the base table with both predicates. This enables choosing a better index/access path. Certain constructs or semantics may restrict transformation; do not rely on every view always being merged.

### 12.4. Reading Execution Plans

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

To view actual statistics for an execution:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       employee_id, full_name
FROM v_active_employee_lab
WHERE department_id = 10;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Examine operations on base tables, where predicates are applied, E-Rows/A-Rows, Starts, Buffers, and A-Time. Do not conclude a view is slow merely because the outer SQL is shorter or longer.

### 12.5. When Results Must Be Stored, Consider Materialized Views

If a heavy aggregate report runs continuously and data does not need real-time freshness on every query, a materialized view may be an option. However, you must evaluate:

- COMPLETE vs. FAST refresh.
- ON DEMAND vs. ON COMMIT.
- Acceptable data staleness.
- Refresh and storage costs.
- Materialized view logs and query rewrite capability.

Do not replace a standard view with a materialized view just to "speed it up" without measuring and confirming freshness requirements.

## 13. Dependencies and View Lifecycle

### 13.1. Views Depend on Underlying Objects

When a view references tables or other views, Oracle records dependencies in the data dictionary. If an underlying object is dropped, changed incompatibly, or required privileges are lost, the view can become INVALID or fail when queried.

Do not arbitrarily DROP/CREATE base tables when many views and packages depend on them. Deploy migrations in dependency order and inspect dependent objects.

### 13.2. Listing Views in a Schema

~~~sql
SELECT view_name, text_length
FROM user_views
ORDER BY view_name;
~~~

### 13.3. Checking Object Status

~~~sql
SELECT object_name, status, last_ddl_time
FROM user_objects
WHERE object_type = 'VIEW'
ORDER BY object_name;
~~~

VALID indicates the object is currently valid according to dictionary status; INVALID indicates it needs recompilation or dependency error resolution.

### 13.4. Inspecting Dependencies

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE type = 'VIEW'
ORDER BY name, referenced_owner, referenced_name;
~~~

ALL_DEPENDENCIES/DBA_DEPENDENCIES provide broader scope if the user has view privileges.

### 13.5. Viewing Compilation Errors

~~~sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
WHERE type = 'VIEW'
ORDER BY name, sequence;
~~~

In SQL*Plus or compatible tools, you can use SHOW ERRORS VIEW view_name. USER_ERRORS is useful when querying errors via SQL or incorporating checks into deployment scripts.

### 13.6. Recompiling a View

~~~sql
ALTER VIEW v_employee_directory_lab COMPILE;
~~~

Then check USER_OBJECTS and USER_ERRORS. COMPILE cannot fix a dropped column or lost privilege; the dependency or definition must be fixed first.

### 13.7. Retrieving View DDL

~~~sql
SELECT DBMS_METADATA.GET_DDL(
           'VIEW',
           'V_EMPLOYEE_DIRECTORY_LAB',
           USER
       )
FROM dual;
~~~

DBMS_METADATA is useful for migrations, definition reviews, and DDL backups. Metadata access may depend on user privileges and configuration.

## 14. Altering and Dropping Views

### 14.1. CREATE OR REPLACE Is the Standard Update Method

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email,
    employment_status
FROM employee_data_lab
WHERE employment_status IN ('ACTIVE', 'LEAVE')
WITH READ ONLY;
~~~

When modifying a view:

- Check output column names and datatypes.
- Check dependent consumers.
- Verify privileges on the view after deployment.
- Check VALID/INVALID status and errors.
- Run representative queries and inspect plans if the change is significant.

Changing a view definition can affect dependent views/packages. Deploy in dependency order and keep a clear DDL rollback plan.

### 14.2. DROP VIEW

~~~sql
DROP VIEW v_employee_directory_lab;
~~~

DROP VIEW removes the view object, not the base tables. However, dependent objects may become invalid or unusable. DROP VIEW is DDL and issues an implicit commit per Oracle rules.

Do not confuse DROP VIEW with DROP TABLE. Dropping a view does not delete source data.

### 14.3. View Grants and Definition Changes

When managing migrations, audit existing grants on the view and re-verify them after changes. CREATE OR REPLACE is typically used to modify a view without dropping the object first; avoid unnecessary DROP/CREATE cycles because they can create an outage window for consumers and drop required metadata/grants depending on the operation.

## 15. Common Errors

| Error/Symptom | Common Cause | Resolution |
| --- | --- | --- |
| ORA-01031 insufficient privileges on CREATE VIEW | Missing CREATE VIEW or direct privilege on base tables | Check system privileges and direct object grants |
| View INVALID | Base table/column changed, invalid dependency, or FORCE created an unready view | Check USER_ERRORS, USER_DEPENDENCIES, and recompile after fixing |
| ORA-00904 invalid identifier | Wrong column name or base column renamed/removed | Check table definition and view SQL |
| ORA-01779 cannot modify a column which maps to a non key-preserved table | DML through a join view targets a non-key-preserved table | Design explicit DML or use an INSTEAD OF trigger |
| ORA-01402 view WITH CHECK OPTION where-clause violation | DML makes the row no longer satisfy the view predicate | Fix values or redesign the view/policy |
| Application can still read sensitive columns | User still has direct table privileges or broad system privileges | Audit grants, roles, and inherited privileges |
| View does not show row after status change | View predicate excludes that row | Check WHERE clause and transaction commit |
| Deeply nested views hard to optimize | Multiple complex query layers or restricted transformations | Simplify contract, inspect execution plan |
| Assuming view stores results | Confusing standard view with materialized view | Determine freshness requirements and object type |

## 16. Comprehensive Lab: Publishing an Employee Read API

This lab demonstrates how a schema owner provides a view and the application is granted privileges only on the view.

### Step 1 — Create Table and Data

Run Section 3 in your lab schema. If the table already exists, do not recreate it; use a different lab name or clean up only tables you created.

### Step 2 — Create the Directory View

~~~sql
CREATE OR REPLACE VIEW v_employee_directory_lab AS
SELECT
    employee_id,
    full_name,
    department_id,
    work_email
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH READ ONLY;
~~~

### Step 3 — Verify Exposed Data

~~~sql
SELECT *
FROM v_employee_directory_lab
ORDER BY employee_id;
~~~

The result contains only ACTIVE employees and omits monthly_salary/bank_account_ref.

### Step 4 — Create Role and Grant Privileges on the View

~~~sql
CREATE ROLE employee_directory_reader_lab;
GRANT SELECT ON v_employee_directory_lab
TO employee_directory_reader_lab;
~~~

If the role already exists, skip CREATE ROLE. A DBA or appropriately privileged user grants the role to the application user:

~~~sql
GRANT employee_directory_reader_lab TO app_reader_lab;
~~~

Replace app_reader_lab with an actual test user. Do not grant base table privileges to this user if the goal is view-only access.

### Step 5 — Test Privileges from the Application User

Log in as app_reader_lab:

~~~sql
SELECT employee_id, full_name, department_id, work_email
FROM owner_schema.v_employee_directory_lab;
~~~

If the view is in the same schema as the user, the owner prefix can be omitted. Replace the schema name with the actual owner.

Try querying the base table:

~~~sql
SELECT bank_account_ref
FROM owner_schema.employee_data_lab;
~~~

This query must be rejected if the application user has not been granted direct or broad privileges on the base table.

Try DML through the view:

~~~sql
UPDATE owner_schema.v_employee_directory_lab
SET full_name = 'Changed Name'
WHERE employee_id = 101;
~~~

DML is rejected because the view is declared WITH READ ONLY.

### Step 6 — Test CHECK OPTION

Create an updatable view:

~~~sql
CREATE OR REPLACE VIEW v_active_employee_check_lab AS
SELECT employee_id, full_name, employment_status
FROM employee_data_lab
WHERE employment_status = 'ACTIVE'
WITH CHECK OPTION CONSTRAINT ck_active_employee_check_lab;
~~~

Try changing the status:

~~~sql
UPDATE v_active_employee_check_lab
SET employment_status = 'INACTIVE'
WHERE employee_id = 101;
~~~

Oracle rejects it because the row after UPDATE would no longer satisfy the ACTIVE predicate. Roll back if testing within a transaction:

~~~sql
ROLLBACK;
~~~

### Step 7 — Inspect Metadata

~~~sql
SELECT view_name, text_length
FROM user_views
WHERE view_name LIKE 'V_%_LAB'
ORDER BY view_name;

SELECT object_name, status
FROM user_objects
WHERE object_type = 'VIEW'
  AND object_name LIKE 'V_%_LAB'
ORDER BY object_name;
~~~

### Step 8 — Clean Up Lab Objects (Optional)

Run only when certain the objects belong to the lab and data is no longer needed:

~~~sql
DROP VIEW v_employee_directory_lab;
DROP VIEW v_department_payroll_lab;
DROP VIEW v_employee_department_lab;
DROP VIEW v_employee_edit_lab;
DROP VIEW v_active_employee_edit_lab;
DROP VIEW v_active_employee_checked_lab;
DROP VIEW v_employee_directory_readonly_lab;
DROP VIEW v_employee_dept_edit_lab;
DROP VIEW v_employee_compensation_lab;
DROP VIEW v_employee_department_api_lab;
DROP VIEW v_department_payroll_readonly_lab;
DROP VIEW api_employee_directory;
~~~

Once the views are handled, you can drop the lab triggers and tables you created in dependency order. Do not run DROP on objects whose ownership is unclear. DDL issues an implicit commit, so clean up only after practice transactions have finished.

## 17. View Design Principles for Applications

When creating views as a data access boundary, clearly define:

1. **Owner:** Which schema owns the tables, and which schema owns the views?
2. **Consumer:** Which applications, reports, or users need access?
3. **Contract:** Grain, column names, datatypes, NULL semantics, and row semantics.
4. **Projection:** Expose only the columns consumers need.
5. **Row filter:** Which rows are visible and who is authorized to change that filter?
6. **Privileges:** Does the view owner hold required direct grants; does the application role hold exact view privileges?
7. **DML policy:** Is the view read-only or updatable; is CHECK OPTION or an INSTEAD OF trigger used?
8. **Security boundary:** Do consumers still have direct base table privileges or broad system privileges?
9. **Dependency:** Are base objects and dependent views/packages managed in migrations?
10. **Performance:** Does the execution plan use appropriate access paths; are predicates pushed; do actual rows match expectations?

### 17.1. A Practical Tiered Pattern

~~~text
DATA SCHEMA
  normalized tables
  constraints and indexes
       |
       | direct grants to view owner
       v
ACCESS/API SCHEMA
  public read views
  reporting views
  controlled DML views
       |
       | object grants to application roles
       v
APPLICATION SCHEMA / SERVICE
  SELECT or permitted DML through views
~~~

A tiered schema separates responsibilities, but is only effective when grants are managed properly. If the application still uses an owner account with full table privileges, views are merely a code convention rather than a real privilege boundary.

## 18. Self-Check Questions

1. Does a standard view store the query definition or the query results?
2. Why does a view not automatically make queries faster?
3. When should CREATE OR REPLACE VIEW be used?
4. How does FORCE differ from NOFORCE?
5. Why should columns be explicitly listed rather than using SELECT * in a view?
6. What kind of privileges does a view owner need on base tables in another schema?
7. Why are privileges obtained through a role insufficient to define a stored view?
8. What privilege does an application user need to SELECT from a view?
9. Why can a user with direct SELECT on a base table bypass a view?
10. What does WITH READ ONLY restrict?
11. What condition does WITH CHECK OPTION protect?
12. Does CHECK OPTION prevent a user from updating the base table directly?
13. What does "key-preserved table" mean in a join view?
14. When might Oracle raise ORA-01779?
15. When is an INSTEAD OF trigger used?
16. Why should you not COMMIT inside an INSTEAD OF trigger?
17. Does a synonym automatically grant privileges on the target object?
18. How does a materialized view differ from a standard view?
19. What do USER_VIEWS, USER_OBJECTS, and USER_ERRORS help inspect?
20. Why must grants be verified after modifying a view?
21. Does a tenant-filtering view predicate by itself provide complete row-level security?
22. What roles do view merging and predicate pushing play?
23. When should you check the actual execution plan rather than only EXPLAIN PLAN?
24. Why must an API view stabilize semantics as well as column names?

**Suggested answers:**

1. A standard view stores the query definition; it does not store the result set.
2. The optimizer still executes the underlying query; a view does not cache results on its own.
3. When replacing an existing view's definition without dropping it first.
4. NOFORCE requires valid dependencies; FORCE can create an invalid view to be resolved later.
5. To keep the column contract explicit and avoid unintentionally exposing new columns.
6. Object privileges granted directly on the underlying objects.
7. A stored view requires direct grants, not privileges inherited through the owner's roles.
8. SELECT on the view or a role granted SELECT on the view.
9. Because broader privileges allow querying the base table directly.
10. INSERT/UPDATE/DELETE through the view.
11. Ensures rows after DML still satisfy the view's predicate.
12. No.
13. Every row of that table appears at most once in the join result based on proven key relationships.
14. When attempting DML on a non-key-preserved table through a join view.
15. When a complex view is not updatable by default rules but requires a defined DML mapping.
16. Because DML in the trigger must share the transaction of the statement that fired the trigger.
17. No; a synonym is only an alias.
18. A materialized view stores results and requires refreshes; a standard view stores only the query definition.
19. View list, object validity status, and compilation errors.
20. To ensure consumers retain the right privileges and do not unintentionally lose access.
21. No; a trusted context/VPD or appropriate row-level security mechanism is needed.
22. Allow the optimizer to merge query blocks and push predicates closer to base tables when valid.
23. When you need actual runtime rows, buffers, starts, and elapsed time.
24. Changing predicates can alter the returned dataset or access policy even when column schemas stay the same.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — CREATE VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-VIEW.html): syntax for creating views, FORCE, CHECK OPTION, and READ ONLY.
- [Oracle Database SQL Language Reference — Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Views.html): view concepts and usage.
- [Oracle Database Administrator's Guide — Managing Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-views.html): creating, altering, and managing views.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): INSTEAD OF triggers and trigger semantics.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): object privileges, least privilege, and access control.
- [Oracle Database SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): view merging and query transformations.
- [Oracle Database SQL Language Reference — CREATE MATERIALIZED VIEW](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-MATERIALIZED-VIEW.html): materialized views and refresh options.

**Key takeaway:** views establish a schema-level access contract. Expose the right columns and rows, grant privileges on views to consumers, keep base table privileges minimal, and explicitly decide whether a view is read-only or permits DML. Views help organize privileges and abstract data, but they become an effective security boundary only when broader privileges on base tables and at the system level are controlled.
