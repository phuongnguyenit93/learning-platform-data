# ORA-00001, ORA-02291, ORA-02292, and Data Integrity Violations

Oracle Database uses constraints to protect data correctness. Primary key, unique key, foreign key, NOT NULL, and CHECK constraints prevent invalid states from entering a table. When an INSERT, UPDATE, or DELETE violates these rules, Oracle rejects the operation and returns an error.

Three common errors when handling relationships between tables:

- **ORA-00001: unique constraint violated.** A primary key or unique key value is duplicated; the error can also come from a unique index, including a function-based index.
- **ORA-02291: integrity constraint violated - parent key not found.** A child row being inserted or updated references a parent key that does not exist or is not visible within the transaction.
- **ORA-02292: integrity constraint violated - child record found.** A parent row being deleted or having its key modified still has referencing child rows.

These are typically data/business logic or transaction ordering issues, not errors to fix by disabling constraints. The proper approach is to identify the constraint, inspect the related rows, understand the transaction boundaries, and correct the operation or data according to business rules.

## 1. Data Integrity and Constraints

Constraints are rules enforced by the database to ensure data satisfies required conditions. Placing rules in the database ensures every application, batch job, script, and user complies with the same standard.

Main constraint types:

| Type | Meaning | Example |
|---|---|---|
| PRIMARY KEY | Uniquely identifies a row, disallows NULL | EMPLOYEE_ID |
| UNIQUE | Disallows duplicate unique key values | EMAIL |
| FOREIGN KEY | Value in child table must reference a valid key in parent table | DEPARTMENT_ID |
| NOT NULL | Column must have a non-null value | EMPLOYEE_NAME |
| CHECK | Value must satisfy an expression | SALARY >= 0 |

Example:

~~~sql
CREATE TABLE departments (
    department_id NUMBER
        CONSTRAINT departments_pk PRIMARY KEY,
    department_name VARCHAR2(100)
        CONSTRAINT departments_name_nn NOT NULL
);

CREATE TABLE employees (
    employee_id NUMBER
        CONSTRAINT employees_pk PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT employees_email_uk UNIQUE,
    department_id NUMBER,
    salary NUMBER(12,2)
        CONSTRAINT employees_salary_ck CHECK (salary >= 0),
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES departments (department_id)
);
~~~

In this example:

- `EMPLOYEES_PK` ensures each employee has a unique `employee_id`.
- `EMPLOYEES_EMAIL_UK` prevents two rows from having the same `email` under Oracle's `UNIQUE` rules.
- `EMPLOYEES_DEPARTMENT_FK` ensures non-NULL `department_id` values reference a valid department.
- `EMPLOYEES_SALARY_CK` prevents negative salaries.

## 2. ORA-00001: unique constraint violated

ORA-00001 occurs when an INSERT or UPDATE produces a key value that duplicates an existing row in a unique constraint or unique index.

Example:

~~~sql
INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    101,
    'an@example.com',
    10,
    5000
);

INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    101,
    'binh@example.com',
    10,
    6000
);
~~~

Since `EMPLOYEE_ID` is the primary key, the second INSERT is rejected because `101` already exists.

### 2.1 Common Causes

- Inserting an already-existing primary key.
- Inserting an already-existing business key, such as an email or contract code.
- Updating multiple rows to the same unique value.
- A sequence being misused, reset, or the application supplying duplicate IDs manually.
- Multiple sessions generating the same business key concurrently.
- Application checking existence before INSERT while another transaction inserts first.
- A unique index using an expression such as `UPPER(EMAIL)`, `TRIM(CODE)`, or `CASE`.
- Data differing in casing or whitespace that normalizes to the same value via an index or collation.
- A `MERGE` executing concurrently with another transaction and hitting a unique conflict.

### 2.2 Constraints and Unique Indexes

The error message usually takes the form:

~~~text
ORA-00001: unique constraint (APP.EMPLOYEES_EMAIL_UK) violated
~~~

In some cases, the message names a unique index rather than a constraint. Do not assume every ORA-00001 comes from a primary key. It may come from:

- A primary key constraint.
- A unique constraint.
- A standalone unique index.
- A function-based unique index.

Take the exact object name from the error message and query the data dictionary.

### 2.3 Finding the Violated Constraint

If connected to the owning schema:

~~~sql
SELECT constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred,
       index_name
FROM user_constraints
WHERE constraint_name = UPPER(:constraint_name);
~~~

If the constraint belongs to another schema and the user has visibility:

~~~sql
SELECT owner,
       constraint_name,
       constraint_type,
       table_name,
       status,
       validated,
       deferrable,
       deferred,
       index_owner,
       index_name
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name);
~~~

Common `CONSTRAINT_TYPE` values:

- `P`: Primary key.
- `U`: Unique.
- `R`: Referential integrity/foreign key.
- `C`: Check constraint; `NOT NULL` constraints are also represented in this category in the dictionary.

### 2.4 Finding Columns Belonging to a Unique Constraint

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       column_name,
       position
FROM all_cons_columns
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
ORDER BY position;
~~~

If the error names a standalone index, inspect `ALL_INDEXES` and `ALL_IND_COLUMNS`:

~~~sql
SELECT owner,
       index_name,
       table_name,
       uniqueness,
       status
FROM all_indexes
WHERE owner = UPPER(:owner)
  AND index_name = UPPER(:index_name);

SELECT index_owner,
       index_name,
       table_name,
       column_name,
       column_position
FROM all_ind_columns
WHERE index_owner = UPPER(:owner)
  AND index_name = UPPER(:index_name)
ORDER BY column_position;
~~~

For a function-based index, view the expression in `ALL_IND_EXPRESSIONS`:

~~~sql
SELECT index_owner,
       index_name,
       column_position,
       column_expression
FROM all_ind_expressions
WHERE index_owner = UPPER(:owner)
  AND index_name = UPPER(:index_name)
ORDER BY column_position;
~~~

### 2.5 Finding Duplicate Data

Suppose there is a unique constraint on `EMAIL`:

~~~sql
SELECT email,
       COUNT(*) AS duplicate_count
FROM employees
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

For a composite key:

~~~sql
SELECT company_id,
       external_code,
       COUNT(*) AS duplicate_count
FROM customer_accounts
GROUP BY company_id, external_code
HAVING COUNT(*) > 1;
~~~

For a case-insensitive unique index:

~~~sql
SELECT UPPER(email) AS normalized_email,
       COUNT(*) AS duplicate_count
FROM employees
WHERE email IS NOT NULL
GROUP BY UPPER(email)
HAVING COUNT(*) > 1;
~~~

Duplicate-detection criteria must mirror the exact index/constraint definition. If the index uses `TRIM`, `LOWER`, `NLSSORT`, or `CASE`, group by that exact expression.

### 2.6 NULLs in UNIQUE Constraints

`UNIQUE` is not the same as `PRIMARY KEY`. A unique key can contain `NULL`; a primary key cannot.

For a single-column unique constraint, Oracle allows multiple rows with `NULL` in that column. For a multi-column unique key, understand how Oracle handles combinations of `NULL` and non-`NULL` values; do not rely on `NULL` to represent an arbitrary business key.

Oracle treats empty `VARCHAR2` strings as `NULL`. Therefore, application data sending empty strings may behave differently than in other databases. If a business key is mandatory, use `NOT NULL` and normalize data before writing.

## 3. ORA-02291: parent key not found

ORA-02291 occurs when a child row references a parent key that does not exist under a foreign key constraint.

Example:

~~~sql
INSERT INTO employees (
    employee_id,
    email,
    department_id,
    salary
)
VALUES (
    102,
    'mai@example.com',
    99,
    5500
);
~~~

If `DEPARTMENTS` has no `DEPARTMENT_ID = 99`, Oracle rejects the INSERT and returns ORA-02291.

### 3.1 How Foreign Keys Work

~~~text
DEPARTMENTS (parent)
--------------------
DEPARTMENT_ID  PK
10
20
30
       |
       | referenced by
       v
EMPLOYEES (child)
-----------------
EMPLOYEE_ID    PK
DEPARTMENT_ID  FK
101             10
102             20
103             99  <-- invalid: parent 99 does not exist
~~~

A foreign key guarantees that the foreign key value in the child table matches a referenced key in the parent table, unless `NULL` is permitted under the foreign key rules.

### 3.2 Common Causes

- Inserting a child row before creating the parent row in a transaction with immediate constraint checking.
- Updating a foreign key to a value missing from the parent table.
- The parent row was deleted or never created.
- The parent was inserted in another session that has not committed yet, so the current session cannot see it.
- The application is connected to the wrong schema, PDB, service, or database.
- Confusing a display code with an internal key.
- Composite foreign key columns bound in the wrong order.
- Parent key and child key values differ after normalization.
- Migration importing data in the wrong parent-child order.

### 3.3 Finding the Violated Foreign Key

The error message usually takes the form:

~~~text
ORA-02291: integrity constraint (APP.EMPLOYEES_DEPARTMENT_FK) violated - parent key not found
~~~

Look up the constraint:

~~~sql
SELECT owner,
       constraint_name,
       table_name AS child_table,
       constraint_type,
       r_owner AS parent_owner,
       r_constraint_name AS parent_constraint,
       status,
       validated,
       deferrable,
       deferred
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
  AND constraint_type = 'R';
~~~

### 3.4 Finding the Parent Table and Referenced Columns

A foreign key stores the referenced constraint name in `R_OWNER` and `R_CONSTRAINT_NAME`. Join with the parent constraint:

~~~sql
SELECT child.owner AS child_owner,
       child.table_name AS child_table,
       child.constraint_name AS foreign_key,
       child_col.column_name AS child_column,
       parent.owner AS parent_owner,
       parent.table_name AS parent_table,
       parent.constraint_name AS parent_key,
       parent_col.column_name AS parent_column,
       child_col.position
FROM all_constraints child
JOIN all_constraints parent
  ON parent.owner = child.r_owner
 AND parent.constraint_name = child.r_constraint_name
JOIN all_cons_columns child_col
  ON child_col.owner = child.owner
 AND child_col.constraint_name = child.constraint_name
JOIN all_cons_columns parent_col
  ON parent_col.owner = parent.owner
 AND parent_col.constraint_name = parent.constraint_name
 AND parent_col.position = child_col.position
WHERE child.owner = UPPER(:child_owner)
  AND child.constraint_name = UPPER(:constraint_name)
  AND child.constraint_type = 'R'
ORDER BY child_col.position;
~~~

The output shows which child table column references which parent table column, in the exact order of a composite key.

### 3.5 Checking the Parent Row

For a single-column `DEPARTMENT_ID` foreign key:

~~~sql
SELECT department_id,
       department_name
FROM departments
WHERE department_id = :department_id;
~~~

If no row is returned, determine:

- Is the department ID accurate?
- Has the parent row been created yet?
- Was the parent row deleted in another transaction?
- Are you connected to the right PDB/service?
- Are you checking the right schema/table?

Do not create a dummy parent row just to let the child INSERT succeed. The parent must exist according to business rules.

### 3.6 Order of Inserting Parent and Child

In a normal transaction, insert the parent first, then the child:

~~~sql
INSERT INTO departments (department_id, department_name)
VALUES (40, 'Research');

INSERT INTO employees (
    employee_id, email, department_id, salary
)
VALUES (
    104, 'lan@example.com', 40, 7000
);

COMMIT;
~~~

The same transaction can see its own uncommitted changes. You do not need to COMMIT the parent before inserting the child if both happen in the same transaction even with immediate constraints; committing together preserves atomicity.

If the parent is created by a different transaction, that transaction must commit before the child transaction can rely on the parent's existence.

## 4. ORA-02292: child record found

ORA-02292 occurs when an operation on a parent row is blocked because child rows still reference it.

Example:

~~~sql
DELETE FROM departments
WHERE department_id = 10;
~~~

If employees in `EMPLOYEES` still have `DEPARTMENT_ID = 10`, Oracle rejects the DELETE and returns ORA-02292.

### 4.1 Why Oracle Blocks It

If the department were deleted while employees still reference it, their foreign keys would point to a nonexistent parent key. The database blocks the operation to preserve referential integrity.

### 4.2 Common Causes

- Deleting a parent row while child rows still exist.
- Updating a parent primary/unique key, orphaning child foreign keys.
- Deleting data in parent-before-child order in a script.
- Import/cleanup running in the wrong order.
- Another child table exists that the operator was unaware of.
- Child rows reside in a different schema.
- The application deletes the parent without handling dependent relationships.

### 4.3 Finding the Child Table from the Constraint Name

The error message usually takes the form:

~~~text
ORA-02292: integrity constraint (APP.EMPLOYEES_DEPARTMENT_FK) violated - child record found
~~~

Look up the foreign key metadata:

~~~sql
SELECT owner,
       table_name AS child_table,
       constraint_name,
       r_owner AS parent_owner,
       r_constraint_name AS parent_constraint,
       delete_rule
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND constraint_name = UPPER(:constraint_name)
  AND constraint_type = 'R';
~~~

Then find the parent table and columns using the `ALL_CONSTRAINTS`/`ALL_CONS_COLUMNS` join shown in the ORA-02291 section.

### 4.4 Finding Referencing Child Rows

~~~sql
SELECT employee_id,
       email,
       department_id
FROM employees
WHERE department_id = :department_id;
~~~

If rows are returned, these are the records blocking the parent deletion. When a parent has multiple child tables, check all foreign keys referencing that parent key.

### 4.5 Do Not Delete Child Rows Blindly

Before deleting child rows:

- Determine whether child rows are historical data that must be retained.
- Check grandchild/descendant relationships in deeper tables.
- Verify the cascade policy.
- Check triggers and side effects.
- Confirm business rules permit deletion.
- Count the expected affected rows.

If child rows are business records that must be preserved, you may need to archive, soft-delete, or reassign the relationship per policy instead of executing `DELETE`.

## 5. Comparing the Three Errors

| Error | Typical Operation | Violation | First Question |
|---|---|---|---|
| ORA-00001 | INSERT/UPDATE | Duplicate unique/primary key | Which key is duplicated? |
| ORA-02291 | INSERT/UPDATE child | Missing parent key | Where is the parent row? |
| ORA-02292 | DELETE/UPDATE parent | Referencing child rows still exist | Which child table holds references to the parent? |

Quick examples:

- ORA-00001: two employees have the same `employee_id`.
- ORA-02291: an employee references a nonexistent `department_id`.
- ORA-02292: deleting a department that still has employees assigned to it.

## 6. General Diagnostic Procedure

When encountering a constraint error, follow this order:

1. Record the full error stack, SQL operation, and timestamp.
2. Identify the database, PDB, schema, and session/application.
3. Extract the exact owner and constraint/index name from the error.
4. Query `ALL_CONSTRAINTS`/`ALL_CONS_COLUMNS` or `ALL_INDEXES`.
5. Identify the tables, columns, and parent-child relationship.
6. Inspect the related data using `SELECT`.
7. Check transactions, commit order, and concurrent sessions.
8. Identify the business rule being protected.
9. Decide how to fix the data or adjust DML ordering.
10. Re-run inside a rollback-capable transaction and verify results.
11. Commit only after all business conditions are satisfied.

Never disable a constraint before understanding the error. Disabling constraints lets invalid data enter the database and creates harder-to-fix problems later.

## 7. Essential Constraint Metadata

Commonly used data dictionary views:

| View | Scope | Purpose |
|---|---|---|
| USER_CONSTRAINTS | Current schema | Constraints owned by the user |
| ALL_CONSTRAINTS | Objects visible to the user | Constraints within access scope |
| DBA_CONSTRAINTS | Entire database | DBA inventory and investigation |
| USER_CONS_COLUMNS | Current schema | Constraint columns |
| ALL_CONS_COLUMNS | Objects visible to the user | Constraint columns |
| DBA_CONS_COLUMNS | Entire database | Constraint columns database-wide |
| ALL_INDEXES | Indexes visible to the user | Unique indexes and statuses |
| ALL_IND_COLUMNS | Index columns | Index column order |
| ALL_IND_EXPRESSIONS | Index expressions | Function-based indexes |

### 7.1 View Constraints on a Table

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       delete_rule
FROM all_constraints
WHERE owner = UPPER(:owner)
  AND table_name = UPPER(:table_name)
ORDER BY constraint_type, constraint_name;
~~~

### 7.2 View Columns of All Constraints on a Table

~~~sql
SELECT constraint_name,
       column_name,
       position
FROM all_cons_columns
WHERE owner = UPPER(:owner)
  AND table_name = UPPER(:table_name)
ORDER BY constraint_name, position;
~~~

### 7.3 View Which Parent Tables a Table's Foreign Keys Reference

~~~sql
SELECT fk.owner AS child_owner,
       fk.table_name AS child_table,
       fk.constraint_name AS fk_name,
       pk.owner AS parent_owner,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_key,
       fk.delete_rule,
       fk.status,
       fk.validated
FROM all_constraints fk
JOIN all_constraints pk
  ON pk.owner = fk.r_owner
 AND pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.owner = UPPER(:owner)
  AND fk.table_name = UPPER(:table_name)
ORDER BY fk.constraint_name;
~~~

### 7.4 Find All Foreign Keys Referencing a Parent Table

~~~sql
SELECT fk.owner AS child_owner,
       fk.table_name AS child_table,
       fk.constraint_name AS foreign_key,
       pk.owner AS parent_owner,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_key,
       fk.delete_rule
FROM all_constraints fk
JOIN all_constraints pk
  ON pk.owner = fk.r_owner
 AND pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND pk.owner = UPPER(:parent_owner)
  AND pk.table_name = UPPER(:parent_table)
ORDER BY fk.owner, fk.table_name, fk.constraint_name;
~~~

This query is valuable before deleting a parent or modifying a parent key. `ALL_*` views only cover objects visible to the current user; DBAs can use `DBA_CONSTRAINTS` for a complete inventory.

## 8. Distinguishing Constraint Status and Validation

Oracle manages constraint states with attributes such as `ENABLE`/`DISABLE` and `VALIDATE`/`NOVALIDATE`.

| State | General Meaning |
|---|---|
| ENABLE VALIDATE | Existing data has been checked and new DML must comply |
| ENABLE NOVALIDATE | New DML must comply; existing data is not fully verified |
| DISABLE VALIDATE | Constraint does not enforce new DML; has specific data/segment rules |
| DISABLE NOVALIDATE | Constraint is disabled and existing data is unverified |

Do not infer solely from the `STATUS` column that all existing rows are valid. Check `VALIDATED`, index state, and how the constraint was created/enabled.

### 8.1 ENABLE NOVALIDATE

Example:

~~~sql
ALTER TABLE employees
ENABLE NOVALIDATE CONSTRAINT employees_department_fk;
~~~

This state is sometimes used during data transition plans: Oracle begins enforcing the constraint for new DML without scanning and validating all existing data yet. That does not make existing data valid on its own.

After cleaning historical data, validate it:

~~~sql
ALTER TABLE employees
ENABLE VALIDATE CONSTRAINT employees_department_fk;
~~~

If violating rows remain, validation will fail. Locate and fix those rows first.

### 8.2 DISABLING a Constraint

~~~sql
ALTER TABLE employees
DISABLE CONSTRAINT employees_department_fk;
~~~

Disabling a constraint allows invalid data to enter. Use only within controlled load/migration procedures that include verification and re-enabling with `VALIDATE`. Never disable constraints to hide application bugs.

## 9. Deferrable Constraints and Checking Timing

By default, constraints are checked immediately at the statement level. A constraint can be declared `DEFERRABLE` to postpone checking until the end of the transaction.

Example:

~~~sql
CREATE TABLE task_items (
    item_id NUMBER,
    parent_item_id NUMBER,
    CONSTRAINT task_items_pk
        PRIMARY KEY (item_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT task_items_parent_fk
        FOREIGN KEY (parent_item_id)
        REFERENCES task_items(item_id)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

With a `DEFERRABLE` constraint, you can control checking timing:

~~~sql
SET CONSTRAINTS task_items_parent_fk DEFERRED;
~~~

Or check immediately:

~~~sql
SET CONSTRAINTS task_items_parent_fk IMMEDIATE;
~~~

### 9.1 INITIALLY IMMEDIATE vs. INITIALLY DEFERRED

- `INITIALLY IMMEDIATE`: checks after each statement by default; a transaction can switch it to deferred if the constraint is deferrable.
- `INITIALLY DEFERRED`: defers checking until the end of the transaction by default.

Only constraints declared `DEFERRABLE` can be deferred. A `NOT DEFERRABLE` constraint cannot be switched to deferred via `SET CONSTRAINTS`.

### 9.2 Why Use Deferred Constraints?

For example, a dataset with circular references or multi-row inserts in an order disallowed by immediate constraints. Deferred constraints allow intermediate steps to be temporarily inconsistent, provided the final state is valid when checked at the end of the transaction.

### 9.3 Errors Surfacing at COMMIT

With deferred constraints, `INSERT`/`UPDATE` statements can succeed while `COMMIT` fails because the final transaction state still violates the constraint.

Therefore, do not assume an operation succeeded simply because `executeUpdate` returned a row count. Check the `COMMIT` outcome and handle rollback if the commit is rejected.

### 9.4 Inspecting Attributes

~~~sql
SELECT constraint_name,
       deferrable,
       deferred,
       status,
       validated
FROM user_constraints
WHERE table_name = UPPER(:table_name)
ORDER BY constraint_name;
~~~

Do not convert all constraints to deferred as a way to avoid errors. That shifts when violations are detected and causes failures to surface late at the end of a transaction.

## 10. ON DELETE CASCADE and ON DELETE SET NULL

By default, foreign keys block deleting a parent if referencing children exist. Oracle supports explicit deletion behaviors:

- `NO ACTION`/default: forbids deleting the parent while referencing children exist.
- `ON DELETE CASCADE`: deletes related child rows when the parent is deleted.
- `ON DELETE SET NULL`: sets the child foreign key to `NULL` when the parent is deleted, if the column is nullable.

### 10.1 ON DELETE CASCADE

~~~sql
CREATE TABLE order_items (
    order_item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    product_id NUMBER NOT NULL,
    CONSTRAINT order_items_order_fk
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE
);
~~~

When an `ORDERS` row is deleted, referencing `ORDER_ITEMS` rows are deleted automatically in the same transaction.

Use `CASCADE` only when child rows genuinely have no independent meaning outside the parent, such as line items of an order in an appropriate model. Never use cascade when child rows are financial documents, history, or audit-retained records.

### 10.2 ON DELETE SET NULL

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER,
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id)
        ON DELETE SET NULL
);
~~~

When a department is deleted, `department_id` on related employees is set to `NULL`. The foreign key column must allow `NULL`, and business logic must permit employees without a department.

### 10.3 Oracle Does Not Support ON UPDATE CASCADE

Oracle does not provide `ON UPDATE CASCADE` as a standard foreign key behavior. Good design uses stable parent keys, such as surrogate primary keys, and never mutates primary key values during normal operations.

If a parent key must change, plan controlled child updates or use a stable surrogate key alongside a separate mutable business key.

## 11. Indexes on Foreign Keys

Oracle automatically creates or uses indexes for primary key and unique constraints as needed, but does not automatically create indexes for every foreign key.

Indexing foreign keys is commonly helpful when:

- Deleting or updating parent keys.
- Frequently joining parent and child tables.
- Looking up child rows by parent key.
- Avoiding full table scans on large child tables.
- Reducing certain locking/contention scenarios associated with parent operations.

Example:

~~~sql
CREATE INDEX employees_department_ix
ON employees(department_id);
~~~

An index does not replace a foreign key constraint. It improves access and can reduce parent check/delete cost, while the constraint continues to enforce integrity.

For composite foreign keys, choose an index column order that aligns with queries and parent operations. Measure execution plans and DML overhead before creating indexes.

## 12. Safely Resolving ORA-00001

Procedure:

1. Extract the constraint/index name from the error stack.
2. Look up the unique key columns or expression.
3. Query the existing row holding that value.
4. Determine whether the new value is valid under business rules.
5. Check concurrent sessions and ID-generation logic.
6. Choose insert/update/upsert or return an appropriate business error.
7. Never delete existing rows just to free a unique key without approval.

### 12.1 Checking Before INSERT Does Not Prevent Race Conditions

A common anti-pattern:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE email = :email;

-- If count = 0 then INSERT.
~~~

Two sessions can both see `count = 0` and both attempt `INSERT`. One succeeds; the other receives ORA-00001.

The unique constraint remains the final safeguard. The application must catch the duplicate error and translate it into a business response such as "email is already registered."

### 12.2 MERGE Does Not Eliminate All Race Conditions

`MERGE` is convenient for upserts, yet two concurrent sessions processing the same business key can still collide on a unique constraint. Applications must handle contention and implement conditional retries where appropriate.

### 12.3 Sequences and Primary Keys

Sequences are commonly used to assign IDs:

~~~sql
CREATE SEQUENCE employees_seq
START WITH 1
INCREMENT BY 1
CACHE 100;
~~~

~~~sql
INSERT INTO employees (
    employee_id, email, department_id, salary
)
VALUES (
    employees_seq.NEXTVAL, :email, :department_id, :salary
);
~~~

Sequences do not guarantee gapless numbers. Gaps can appear due to rollbacks, sequence caching, instance restarts, or concurrency. Never treat a gap as a sign of duplicates.

If ORA-00001 still occurs when using a sequence, check:

- Is a session/application assigning IDs manually?
- Was the sequence reset below existing table data?
- Are multiple systems writing to the same table?
- Does a trigger assign a different ID than the application?
- Is the wrong sequence being referenced?
- Is a unique constraint other than the primary key being violated?

### 12.4 Normalizing Business Keys

If emails are case-insensitive, define the unique key on a normalized expression or use an appropriate collation. Example function-based index:

~~~sql
CREATE UNIQUE INDEX customers_email_uix
ON customers(UPPER(TRIM(email)));
~~~

Before creating the index, find duplicates using the same expression:

~~~sql
SELECT UPPER(TRIM(email)) AS normalized_email,
       COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY UPPER(TRIM(email))
HAVING COUNT(*) > 1;
~~~

## 13. Safely Resolving ORA-02291

Procedure:

1. Identify the foreign key name.
2. Locate the child table, parent table, and matching columns.
3. Inspect the foreign key value on the row being written.
4. Verify the parent row exists in the right PDB/schema.
5. Verify the parent transaction has committed.
6. Check data load ordering.
7. Fix source data or DML order.
8. Re-run inside a transaction and verify commit.

### 13.1 Loading Parent Data Before Child Data

When importing from files:

~~~text
1. Load DEPARTMENTS
2. Load EMPLOYEES
3. Validate foreign keys
~~~

For multi-tier relational schemas, build a topological load order from the dependency graph. Parent tables must be loaded before child tables when immediate constraints are enabled.

### 13.2 Composite Foreign Keys

Suppose:

~~~sql
CREATE TABLE product_versions (
    product_id NUMBER,
    version_no NUMBER,
    CONSTRAINT product_versions_pk
        PRIMARY KEY (product_id, version_no)
);

CREATE TABLE order_lines (
    order_line_id NUMBER PRIMARY KEY,
    product_id NUMBER,
    version_no NUMBER,
    CONSTRAINT order_lines_product_version_fk
        FOREIGN KEY (product_id, version_no)
        REFERENCES product_versions(product_id, version_no)
);
~~~

A parent row must exist matching both `product_id` and `version_no`. A partial match is not enough.

### 13.3 NULLs in Foreign Keys

For a single-column foreign key, `NULL` does not reference a parent row. For a composite foreign key, Oracle permits partial `NULL` combinations according to Oracle's foreign key rules; if business rules require either all columns to be `NULL` or all non-`NULL`, add a `CHECK` constraint to enforce that rule.

All-or-none example:

~~~sql
ALTER TABLE order_lines ADD CONSTRAINT order_lines_product_pair_ck
CHECK (
    (product_id IS NULL AND version_no IS NULL)
    OR
    (product_id IS NOT NULL AND version_no IS NOT NULL)
);
~~~

## 14. Safely Resolving ORA-02292

Procedure:

1. Identify the foreign key in the error message.
2. Look up the child table and parent key.
3. Find all child rows referencing the parent.
4. Determine whether child rows must be retained.
5. Check deeper child relationships beneath the child table.
6. Choose between deleting children, cascade, set null, soft delete, or keeping the parent.
7. Execute within a rollback-capable transaction.
8. Count affected rows and verify results.

### 14.1 Deleting Children Before the Parent

If business rules allow deleting all details:

~~~sql
DELETE FROM order_items
WHERE order_id = :order_id;

DELETE FROM orders
WHERE order_id = :order_id;

COMMIT;
~~~

Both statements belong to the same transaction. If the second statement fails, rolling back restores the deleted child rows.

### 14.2 Keeping the Parent via Logical Deletion

For financial, HR, or audit-sensitive data, instead of `DELETE`, use a status column:

~~~sql
UPDATE departments
SET status = 'INACTIVE',
    closed_at = SYSTIMESTAMP
WHERE department_id = :department_id;
~~~

This is soft deletion. Design unique keys, application queries, and retention policies carefully so inactive rows do not cause logical conflicts.

### 14.3 Intentional Cascade

Declare `ON DELETE CASCADE` only if the child's lifecycle depends entirely on the parent and automatic child deletion is a business requirement. Cascading deletes can affect far more rows and tables than the initial `DELETE` statement.

## 15. Transactions and Concurrency

Constraints are evaluated within transaction context. Two sessions can interact such that one statement sees a different state than what the application just read.

### 15.1 Race Condition When Creating a Business Key

~~~text
Session A                  Session B
---------                  ---------
SELECT email -> none
                           SELECT email -> none
INSERT email
                           INSERT same email
COMMIT
                           ORA-00001
~~~

This is expected behavior: the unique constraint guarantees only one row owns that business key.

### 15.2 Uncommitted Parent Insert

~~~text
Session A                  Session B
---------                  ---------
INSERT parent
                           INSERT child referencing parent
                           (parent not yet committed)
COMMIT
~~~

Session B cannot rely on Session A's uncommitted parent row as an independently existing row. Depending on locks and timing, the operation may wait or fail validation. Transaction design must ensure the parent commits before another transaction depends on it.

If the parent and child belong to the same unit of work, create them in a single transaction whenever possible.

### 15.3 Do Not Infinitely Retry Constraint Errors

ORA-00001, ORA-02291, and ORA-02292 are usually logic/data errors. Immediately retrying the same SQL with the same data will keep failing.

Retrying is appropriate only when the application changes inputs or detects a transient race condition with a strategy to re-read state. All retries must be bounded and idempotent.

## 16. Handling Errors in PL/SQL

PL/SQL provides the predefined exception `DUP_VAL_ON_INDEX` for duplicate keys.

~~~sql
BEGIN
    INSERT INTO employees (
        employee_id, email, department_id, salary
    )
    VALUES (
        employees_seq.NEXTVAL,
        'an@example.com',
        10,
        5000
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'Employee key or unique value already exists'
        );
END;
/
~~~

For foreign key errors, inspect `SQLCODE`:

~~~sql
BEGIN
    -- DML statement
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -2291 THEN
            DBMS_OUTPUT.PUT_LINE('Referenced parent key not found');
        ELSIF SQLCODE = -2292 THEN
            DBMS_OUTPUT.PUT_LINE('Child rows still reference parent');
        ELSE
            RAISE;
        END IF;
END;
/
~~~

The examples above illustrate branching only. In production applications, never swallow errors after printing to `DBMS_OUTPUT`. Log with a correlation ID, return a clear business error, and roll back when the transaction cannot continue.

### 16.1 SQLCODE and SQLERRM

- `SQLCODE` returns the numeric error code inside an exception handler.
- `SQLERRM` returns the error message.
- `DBMS_UTILITY.FORMAT_ERROR_STACK` helps record the error stack.
- `DBMS_UTILITY.FORMAT_ERROR_BACKTRACE` helps pinpoint the PL/SQL line raising the error.

Example:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(DBMS_UTILITY.FORMAT_ERROR_BACKTRACE);
        RAISE;
~~~

Keep `RAISE` so the error continues propagating to the caller unless explicit recovery is performed.

## 17. Handling Errors in Java/JDBC

JDBC represents SQL errors with `SQLException` and its subclasses. Constraint violations generally map to SQLState class `23`; Oracle JDBC exposes the corresponding vendor error code.

Example:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO customers(customer_id, email) VALUES (?, ?)")) {
    ps.setLong(1, customerId);
    ps.setString(2, email);
    ps.executeUpdate();
} catch (SQLIntegrityConstraintViolationException e) {
    connection.rollback();
    int oracleCode = e.getErrorCode();

    if (oracleCode == 1) {
        throw new DuplicateCustomerException(
            "Customer key or email already exists", e);
    }
    throw e;
}
~~~

Depending on the driver and framework exception wrapping, the error may surface as `SQLException` or `DataAccessException`. You may need to traverse `getNextException`/`getCause` to locate the underlying vendor error code.

Do not rely solely on parsing error message text, as messages can vary by locale or driver version. Use vendor error codes/SQLState and operation context.

### 17.1 Identifying Which Unique Rule Was Violated

ORA-00001 only tells you a unique rule was violated. The application needs to identify the exact constraint/index to return an accurate message:

- Customer ID already exists.
- Email is already registered.
- Duplicate order code.
- Idempotency key has already been processed.

Do not return a generic "database error" when you can safely map it to a clear business error.

### 17.2 BatchUpdateException

When running JDBC batches, constraint errors can halt the batch or return update counts depending on the driver and batch mode. Inspect:

- `getUpdateCounts()`.
- `getNextException()`.
- Transaction state.
- Which rows were processed prior to the error.

Do not assume batches are always atomic across the entire batch. Use explicit transactions and rollbacks when all-or-nothing semantics are required.

## 18. Bulk DML and SAVE EXCEPTIONS

In PL/SQL `FORALL`, `SAVE EXCEPTIONS` allows processing remaining elements while recording per-iteration errors.

~~~sql
DECLARE
    TYPE id_array_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_array_t := id_array_t(101, 102, 103, 104);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        DELETE FROM employees
        WHERE employee_id = l_ids(i);
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -24381 THEN
            FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
                DBMS_OUTPUT.PUT_LINE(
                    'Index=' ||
                    SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                    ', Code=' ||
                    SQL%BULK_EXCEPTIONS(i).ERROR_CODE
                );
            END LOOP;
        ELSE
            RAISE;
        END IF;
END;
/
~~~

`SAVE EXCEPTIONS` is useful for large batches that need per-row error capture. Design commit/rollback semantics explicitly: DML operations that succeeded before the exception remain in the active transaction and must be rolled back if full-batch atomicity is required.

## 19. DML Error Logging

Oracle supports DML error logging via `DBMS_ERRLOG` and the `LOG ERRORS` clause for certain DML operations. This mechanism logs select row-level errors into an error table so failing rows can be handled separately.

Create the error logging table:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'EMPLOYEES',
        err_log_table_name => 'ERR$_EMPLOYEES'
    );
END;
/
~~~

Example:

~~~sql
INSERT INTO employees (
    employee_id, email, department_id, salary
)
SELECT employee_id, email, department_id, salary
FROM employees_stage
LOG ERRORS INTO err$_employees ('IMPORT_BATCH_01')
REJECT LIMIT UNLIMITED;
~~~

Whether each constraint error type is logged depends on the statement, constraint type, DML mode, and Oracle release restrictions. Do not assume all ORA-00001/02291/02292 errors are captured in the error table. Test with the exact SQL statement and database version before adopting it in data-loading pipelines.

Error logging does not replace source-data validation. After loading, summarize logged errors, fix source rows, and reprocess rejected records.

## 20. Intentional Constraint Design

### 20.1 Clear Naming

Constraint names should indicate both table and role:

~~~text
EMPLOYEES_PK
EMPLOYEES_EMAIL_UK
EMPLOYEES_DEPARTMENT_FK
EMPLOYEES_SALARY_CK
EMPLOYEES_NAME_NN
~~~

Readable names identify errors much faster than Oracle-generated `SYS_C00...` names.

### 20.2 Stable Primary Keys

Use surrogate keys such as numeric IDs or UUIDs per system standards. Avoid mutating primary keys because foreign keys depend on them.

Business keys such as email, customer code, or contract number can carry separate `UNIQUE` constraints.

### 20.3 Defining a Delete Policy

For each relationship, answer:

- Can the parent ever be deleted?
- Can the child exist independently?
- When deleting a parent, should children cascade, set null, archive, or block?
- Is soft delete needed?
- How long must historical data be retained?

Never pick `CASCADE` merely to avoid ORA-02292.

### 20.4 Selective Foreign Key Indexing

Create indexes when workloads look up children by parent, join parent-child tables, or delete/update parents. Measure the added write overhead and index storage.

## 21. Cleaning Data Before Enabling Constraints

When migrating an existing table with data, adding `UNIQUE`/`PK`/`FK` constraints fails if existing rows violate them.

### 21.1 Finding Duplicates Before Adding UNIQUE

~~~sql
SELECT email,
       COUNT(*) AS row_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

For composite keys:

~~~sql
SELECT tenant_id,
       external_id,
       COUNT(*) AS row_count
FROM external_customers
GROUP BY tenant_id, external_id
HAVING COUNT(*) > 1;
~~~

### 21.2 Finding Orphaned Children Before Adding FK

~~~sql
SELECT e.employee_id,
       e.department_id
FROM employees e
WHERE e.department_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM departments d
      WHERE d.department_id = e.department_id
  );
~~~

### 21.3 Controlled Data Cleanup

Options:

- Map legacy codes to valid parent keys.
- Create missing parent rows if genuinely valid per business rules.
- Move child rows to a pending status.
- Quarantine invalid rows into a staging/quarantine table.
- Deduplicate using an approved merge rule.
- Remove confirmed test/junk rows.

Do not mechanically pick `MIN`/`MAX` or delete duplicate rows blindly. Duplicate keys may represent two distinct customers or transactions that must be distinguished.

## 22. Constraints in Imports and Migrations

When loading multiple related tables:

1. Create schemas and parent tables.
2. Load parent/reference data.
3. Load child tables.
4. Resolve duplicates per business rules.
5. Validate foreign key and unique constraints.
6. Create/rebuild indexes per the chosen strategy.
7. Reconcile row counts and business totals.

With Data Pump, you can use metadata/data filters and proper import ordering, but never rely on disabling all constraints without a plan to re-validate them.

### 22.1 Temporarily Deferring Constraints During Migration

If disabling/deferring is necessary:

- Document which constraints and why.
- Define start and end windows.
- Restrict execution privileges.
- Retain logs of loaded row counts.
- Run duplicate/orphan detection queries.
- Enable `VALIDATE` before opening the application for writes.

### 22.2 Unvalidated Constraints

`ENABLE NOVALIDATE` can enforce rules on new DML while legacy data is being remediated. However, this state must be tracked with a clear validation plan. Do not consider a migration complete while historical data still violates requirements.

## 23. Checking Transactions Before Committing

For multi-table workflows, group related operations into one transaction:

~~~sql
SAVEPOINT before_order;

INSERT INTO orders (order_id, customer_id, status)
VALUES (9001, 100, 'NEW');

INSERT INTO order_items (order_item_id, order_id, product_id)
VALUES (1, 9001, 200);

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 200;

-- Check row counts and business conditions.
COMMIT;
~~~

If an error occurs:

~~~sql
ROLLBACK TO before_order;
~~~

or roll back the entire transaction per design. Never leave a partial commit when business logic requires all tables to change together.

## 24. Constraints and Triggers

Triggers can issue additional DML or alter values before/after an operation. A unique or foreign key error can originate from a statement inside a trigger rather than the outer statement sent by the application.

When triggers appear in the error stack:

- Inspect triggers on the table.
- Check which procedures/packages the trigger calls.
- Inspect secondary DML executed.
- Check for autonomous transactions if any.
- Read the complete error stack and backtrace.

Do not disable triggers immediately upon seeing a constraint error. First verify whether the trigger is enforcing a valid business rule.

## 25. Constraints and Partitioning

In partitioned tables, unique constraints are subject to restrictions regarding partition key columns and global/local index types. Unique keys must conform to Oracle's partitioning rules.

When creating or modifying unique constraints on partitioned tables:

- Determine local vs. global indexing.
- Verify whether the partition key must be included in the unique key.
- Check index usability.
- Assess partition maintenance impact.
- Test DDL on the exact target release.

Do not attempt to fix ORA-00001 by creating duplicate indexes before understanding existing indexes and constraints.

## 26. Data Protection and Error Logging

Investigation logs should include:

- Error code and constraint name.
- Operation (`INSERT`/`UPDATE`/`DELETE`).
- Table/schema.
- Business correlation ID.
- Transaction/request ID.
- Timestamp and service.
- Keys masked or tokenized per policy.

Do not log full row payloads, passwords, tokens, emails/identifiers, or personal data unnecessarily. Use correlation IDs to inspect records inside authorized systems.

## 27. End-to-End Investigation Example

Suppose an employee creation API returns ORA-02291 on constraint `APP.EMPLOYEES_DEPARTMENT_FK`.

### Step 1: Identify the Relationship

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       r_owner,
       r_constraint_name
FROM all_constraints
WHERE owner = 'APP'
  AND constraint_name = 'EMPLOYEES_DEPARTMENT_FK';
~~~

### Step 2: Identify the Parent Key

~~~sql
SELECT owner,
       table_name,
       constraint_name,
       constraint_type
FROM all_constraints
WHERE owner = 'APP'
  AND constraint_name = :parent_constraint;
~~~

### Step 3: Check the Parent Row

~~~sql
SELECT department_id,
       department_name
FROM app.departments
WHERE department_id = :department_id;
~~~

### Step 4: Inspect the Request

Cross-check `department_id` in the request against master data. Check whether the application passed a department code from another tenant or PDB.

### Step 5: Fix the Logic

If the department is valid but missing, create the parent via the proper business workflow. If the request sent an invalid ID, return a validation error to the client. Never disable the foreign key.

### Step 6: Test Concurrency

Test when the parent is created concurrently by another transaction. Confirm transaction boundaries and commit ordering.

## 28. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| Disabling unique constraint on ORA-00001 | Allows duplicate data | Identify the key and fix data/logic |
| Using only `SELECT` before `INSERT` | Race conditions still create duplicates | Keep `UNIQUE` constraint and handle error |
| Assuming ORA-00001 is always the primary key | Overlooks other unique indexes | Look up constraint/index name |
| Ignoring function-based indexes | Confused why distinct strings collide | Check `ALL_IND_EXPRESSIONS` |
| Assuming sequences never collide | Resets/manual IDs cause collisions | Check sequence and all ID sources |
| Creating child before parent in another transaction | ORA-02291 | Ensure parent commits first |
| Creating dummy parents to bypass FK | Corrupts business data | Verify master data |
| Deleting parent before child | ORA-02292 | Define delete policy and check dependencies |
| Enabling `ON DELETE CASCADE` to avoid errors | Unintended cascading data loss | Use only when business rules require it |
| Disabling FK during import and forgetting to enable | Orphaned data persists | Validate before completion |
| Treating `ENABLE NOVALIDATE` as `VALIDATE` | Legacy data may remain invalid | Track `VALIDATED` and validate |
| Swallowing exceptions in PL/SQL | App believes operation succeeded | Log, roll back, and `RAISE` appropriately |
| Retrying constraint errors infinitely | Increases load without fixing cause | Retry only under clear conditions |
| Omitting FK indexes on large tables | Parent deletes/joins become expensive | Evaluate and index when appropriate |
| Logging full row data | Leaks sensitive data | Log masked keys and correlation IDs |

## 29. Self-Check Exercises

Run these in a lab schema with dummy data.

### Exercise 1 — ORA-00001 from Primary Key

Create a table with a primary key, `INSERT` the same ID twice, and inspect the reported constraint name.

### Exercise 2 — ORA-00001 from Unique Key

Create a unique constraint on `EMAIL`, attempt to `INSERT` a duplicate email, and query `USER_CONSTRAINTS`.

### Exercise 3 — Function-Based Unique Index

Create a unique index on `UPPER(TRIM(email))`. Test two emails differing in casing or whitespace and explain the result.

### Exercise 4 — Finding Duplicates

Write a `GROUP BY`/`HAVING` query to detect duplicates before adding a unique constraint.

### Exercise 5 — ORA-02291

Insert a child row referencing a nonexistent parent ID. Query `ALL_CONSTRAINTS` and `ALL_CONS_COLUMNS`.

### Exercise 6 — Composite Foreign Key

Create a composite parent key and composite foreign key. Test right/wrong column orders and `NULL` cases.

### Exercise 7 — ORA-02292

Create parent and child rows, attempt to `DELETE` the parent. Find the child rows and delete in the right order.

### Exercise 8 — ON DELETE CASCADE

Create lab tables with cascade. Delete the parent and count child rows before and after within the transaction.

### Exercise 9 — DEFERRABLE

Create a `DEFERRABLE INITIALLY DEFERRED` constraint. Create a temporarily invalid intermediate state, fix it before `COMMIT`, and also test committing while still invalid.

### Exercise 10 — Concurrency

Use two sessions inserting the same business key concurrently. Observe one session receiving a duplicate error and translate it into a business response.

### Exercise 11 — JDBC Exception

Catch `SQLIntegrityConstraintViolationException`/`SQLException`, inspect SQLState, vendor code, and next exception; map to an application error.

### Exercise 12 — Migration Validation

Load data containing duplicates/orphans into staging, clean the data, and run `ENABLE VALIDATE` on the constraints.

## 30. Incident Handling Checklist

**Error Capture**

- Do you have the full error stack?
- Do you have the owner and constraint/index name?
- Do you know the SQL operation and bind key?
- Do you know the database/PDB/service and transaction ID?

**Metadata Lookup**

- Have you identified the constraint type?
- Have you identified the exact table and columns?
- For FKs, have you found both parent and child tables?
- For unique indexes, have you checked expressions?

**Data and Transactions**

- Have you checked for duplicate/orphan rows?
- Does the parent row exist and is it committed?
- Are concurrent sessions involved?
- Is the constraint immediate or deferred?
- Are triggers issuing secondary DML?

**Remediation**

- Does the fix align with business rules?
- Should child rows be deleted/updated or the parent kept?
- Is cascade truly required by business logic?
- Can changes be rolled back if validation fails?
- Are constraints kept enabled rather than disabled to hide errors?

**Post-Remediation**

- Are constraints `ENABLE` and `VALIDATED` properly?
- Is existing data valid?
- Was concurrency tested?
- Do logs include sufficient context without exposing sensitive data?
- Are metrics in place to detect recurring violations?

## 31. Key Takeaways

| Error/Concept | Key Point |
|---|---|
| ORA-00001 | Unique constraint/index violation |
| ORA-02291 | Child references nonexistent parent key |
| ORA-02292 | Parent blocked because referencing children remain |
| PRIMARY KEY | Unique and NOT NULL |
| UNIQUE | Unique by key/index, with specific NULL rules |
| FOREIGN KEY | Enforces parent-child referential integrity |
| USER_CONSTRAINTS | Constraints in the current schema |
| ALL_CONSTRAINTS | Constraints visible to the user |
| ALL_CONS_COLUMNS | Constraint columns |
| ALL_IND_EXPRESSIONS | Function-based index expressions |
| ENABLE VALIDATE | Constraint enabled and existing data validated |
| ENABLE NOVALIDATE | New DML checked, existing data unverified |
| DEFERRABLE | Allows deferring constraint validation |
| SET CONSTRAINTS | Changes checking timing for deferrable constraints |
| ON DELETE CASCADE | Automatically deletes children when parent is deleted |
| ON DELETE SET NULL | Sets child FK to NULL when parent is deleted |
| SAVE EXCEPTIONS | Captures per-iteration errors in `FORALL` |
| DBMS_ERRLOG | Logs select row-level DML errors to an error table |
| SQLIntegrityConstraintViolationException | JDBC exception class for integrity violations |

ORA-00001 indicates a duplicate unique value; inspect the exact constraint/index and the columns or expressions forming the key. ORA-02291 indicates a child row could not find a valid parent; check the foreign key, parent data, and commit order. ORA-02292 indicates child rows still reference a parent being deleted or having its key altered; locate the child tables and apply the business delete policy. Use data dictionary views to identify true relationships, keep constraints enabled as integrity safeguards, and handle transactions and concurrency properly. Use cascades, deferred constraints, or disable/enable only under controlled plans with full validation and final data reconciliation.
