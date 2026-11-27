# Conditional DELETE and Deleting Parent-Child Relational Data in Oracle

The **DELETE** statement removes rows from a table. In a system with multiple tables linked by foreign keys, deleting a parent row also depends on the child rows referencing it. Therefore, a safe delete operation must answer three questions: **which rows need to be deleted, where are the related rows, and what does the foreign key relationship dictate when deleting a parent?**

This lesson covers writing **DELETE ... WHERE**, verifying scope before deleting, deleting data across multi-level parent-child hierarchies, and choosing between deleting children first, **ON DELETE CASCADE**, or **ON DELETE SET NULL**. Examples use Oracle Database and can be run in a dedicated practice schema.

## 1. DELETE Is a DML Statement

Basic syntax:

~~~sql
DELETE FROM table_name
WHERE condition;
~~~

- **DELETE FROM** specifies the target table.
- **WHERE** identifies which rows matching the condition will be deleted.
- If **WHERE** is omitted, Oracle deletes **all rows** in the table.
- The table, columns, indexes, and constraints remain intact after DELETE.

Example:

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE';
~~~

This statement deletes task rows with status DONE. Rows with other statuses remain.

**DELETE** is DML (Data Manipulation Language). Changes belong to the current transaction and can be **COMMIT**ted or **ROLLBACK**ed according to Oracle transaction rules. This differs from DDL statements like **TRUNCATE TABLE** or **DROP TABLE**, which have implicit commit behavior per Oracle DDL rules.

### 1.1. DELETE Without WHERE

~~~sql
DELETE FROM lab_del_task;
~~~

This statement deletes every row in **LAB_DEL_TASK**. It does not drop the table and can be rolled back if the transaction has not been committed. However, the blast radius is huge; confirm the exact schema, table, and target before running.

### 1.2. DELETE vs. TRUNCATE and DROP

| Statement | Impact | Has WHERE? | Can ROLLBACK like uncommitted DML? | Object after statement |
|---|---|:---:|---|---|
| **DELETE** | Deletes selected rows | Yes | Yes | Table remains intact |
| **DELETE** without WHERE | Deletes all rows | No | Yes | Table remains intact |
| **TRUNCATE TABLE** | Deletes all data via DDL | No | No | Table remains intact |
| **DROP TABLE** | Removes table object | No | Not via DML rollback | Table removed from schema/recycle bin depending on options |

Do not choose TRUNCATE just for speed if you need conditional deletion or transactional rollback.

## 2. Setting Up a Practice Schema with Parent-Child Relationships

Let us create three data levels:

- **LAB_DEL_DEPARTMENT**: departments, the top-level parent table.
- **LAB_DEL_EMPLOYEE**: employees, referencing departments.
- **LAB_DEL_TASK**: tasks, referencing employees.

Hierarchy:

~~~text
LAB_DEL_DEPARTMENT
        |
        | 1 department has many employees
        v
LAB_DEL_EMPLOYEE
        |
        | 1 employee has many tasks
        v
LAB_DEL_TASK
~~~

In the first set of tables, the foreign keys **do not declare ON DELETE CASCADE**. This is the common default: Oracle prevents deleting a parent row while referencing child rows still exist.

### 2.1. Create Parent Table

~~~sql
CREATE TABLE lab_del_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);
~~~

### 2.2. Create First-Level Child Table

~~~sql
CREATE TABLE lab_del_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    employee_status VARCHAR2(20 CHAR) NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT fk_lab_del_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_del_department (department_id),
    CONSTRAINT ck_lab_del_emp_status
      CHECK (employee_status IN ('ACTIVE', 'INACTIVE'))
);
~~~

**DEPARTMENT_ID** is a foreign key referencing department. The column is declared **NOT NULL** because every employee in the example must belong to a department.

### 2.3. Create Second-Level Child Table

~~~sql
CREATE TABLE lab_del_task (
    task_id     NUMBER(7) PRIMARY KEY,
    employee_id NUMBER(6) NOT NULL,
    task_name   VARCHAR2(100 CHAR) NOT NULL,
    task_status VARCHAR2(20 CHAR) NOT NULL,
    created_at  DATE NOT NULL,
    CONSTRAINT fk_lab_del_task_emp
      FOREIGN KEY (employee_id)
      REFERENCES lab_del_employee (employee_id),
    CONSTRAINT ck_lab_del_task_status
      CHECK (task_status IN ('OPEN', 'DONE', 'CANCELLED'))
);
~~~

An employee can have many tasks. The foreign key **FK_LAB_DEL_TASK_EMP** ensures a task only references an existing employee.

### 2.4. Insert Sample Data

~~~sql
INSERT INTO lab_del_department VALUES (10, 'Sales');
INSERT INTO lab_del_department VALUES (20, 'Support');
INSERT INTO lab_del_department VALUES (30, 'Legal');

INSERT INTO lab_del_employee VALUES
  (101, 10, 'An',   'ACTIVE',   DATE '2022-01-10');
INSERT INTO lab_del_employee VALUES
  (102, 10, 'Binh', 'INACTIVE', DATE '2020-03-15');
INSERT INTO lab_del_employee VALUES
  (201, 20, 'Chi',  'ACTIVE',   DATE '2021-07-01');
INSERT INTO lab_del_employee VALUES
  (301, 30, 'Dung', 'ACTIVE',   DATE '2023-05-01');

INSERT INTO lab_del_task VALUES
  (1001, 101, 'Prepare sales report', 'DONE', DATE '2024-01-05');
INSERT INTO lab_del_task VALUES
  (1002, 101, 'Call customer',        'OPEN', DATE '2026-01-10');
INSERT INTO lab_del_task VALUES
  (1003, 102, 'Archive old contract', 'DONE', DATE '2023-12-20');
INSERT INTO lab_del_task VALUES
  (2001, 201, 'Resolve support case', 'OPEN', DATE '2026-02-02');

COMMIT;
~~~

### 2.5. Inspect Data and Relationships

~~~sql
SELECT * FROM lab_del_department ORDER BY department_id;
SELECT * FROM lab_del_employee ORDER BY employee_id;
SELECT * FROM lab_del_task ORDER BY task_id;
~~~

Summary:

| Department | Employees | Tasks |
|---|---|---|
| Sales (10) | An (101), Binh (102) | 1001, 1002 for An; 1003 for Binh |
| Support (20) | Chi (201) | 2001 |
| Legal (30) | Dung (301) | No tasks yet |

The dataset includes an inactive employee, completed tasks, open tasks, and a department whose employee has no tasks. These cases help test delete predicates and foreign key behavior.

## 3. Deleting Data with WHERE Conditions

WHERE conditions can filter by a single column, multiple columns, date ranges, value lists, or subqueries.

### 3.1. Deleting by Primary Key

~~~sql
DELETE FROM lab_del_task
WHERE task_id = 1001;
~~~

**TASK_ID** is the primary key, so the condition matches at most one row. This is the exact delete pattern when the record identifier is known.

### 3.2. Deleting with Multiple Conditions

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

Only tasks that both have status DONE and were created before Jan 1, 2025 are selected. **AND** requires both sides to be true.

When using **OR**:

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'CANCELLED'
   OR created_at < DATE '2024-01-01';
~~~

A row satisfying either condition is deleted. Distinguish AND and OR carefully because they can drastically change the number of affected rows.

### 3.3. Deleting by List

~~~sql
DELETE FROM lab_del_employee
WHERE employee_id IN (102, 301);
~~~

IN is suitable for an explicit list of keys. However, this example will be blocked by the foreign key if employee 102 still has task 1003. Child rows must be handled first or via a constraint delete policy.

### 3.4. Deleting by Date Range

For Oracle DATE columns containing both date and time, use a half-open interval when deleting for a day/month/year:

~~~sql
DELETE FROM lab_del_task
WHERE created_at >= DATE '2024-01-01'
  AND created_at <  DATE '2025-01-01';
~~~

This condition covers every timestamp in 2024 without relying on manually specifying the end of Dec 31. DATE literals avoid string parsing tied to session NLS settings.

### 3.5. Deleting Rows with NULL Columns

Do not use **= NULL**:

~~~sql
-- Not the intended check:
DELETE FROM lab_del_task
WHERE task_status = NULL;

-- Correct NULL check:
DELETE FROM lab_del_task
WHERE task_status IS NULL;
~~~

In the lab table, **TASK_STATUS** is NOT NULL, so the second statement deletes zero rows. When a column is actually nullable, **IS NULL** is the proper check.

In SQL, a condition evaluating to UNKNOWN (such as comparing with NULL) is not kept by WHERE. Keep three-valued logic (TRUE/FALSE/UNKNOWN) in mind when writing delete filters.

## 4. Verifying Scope Before DELETE

A practical workflow should start with a SELECT using the exact same condition as the DELETE.

Suppose we need to delete DONE tasks created before 2025:

**Step 1 — preview rows that will be affected:**

~~~sql
SELECT task_id, employee_id, task_name, task_status, created_at
FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01'
ORDER BY task_id;
~~~

**Step 2 — count rows:**

~~~sql
SELECT COUNT(*) AS rows_to_delete
FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

**Step 3 — execute DELETE with the same condition:**

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
  AND created_at < DATE '2025-01-01';
~~~

**Step 4 — verify row count and post-delete results:**

SQL clients usually display the number of deleted rows. In PL/SQL, you can read **SQL%ROWCOUNT** immediately after DELETE:

~~~sql
DECLARE
    v_deleted PLS_INTEGER;
BEGIN
    DELETE FROM lab_del_task
    WHERE task_status = 'DONE'
      AND created_at < DATE '2025-01-01';

    v_deleted := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Deleted rows: ' || v_deleted);

    ROLLBACK;
END;
/
~~~

The PL/SQL example above rolls back to demonstrate counting affected rows without keeping changes. When performing an actual delete, choose COMMIT or ROLLBACK based on verification results and application transaction rules.

### 4.1. Note on SQL%ROWCOUNT

**SQL%ROWCOUNT** is an implicit cursor attribute in PL/SQL reporting the number of rows affected by the most recent DML statement. Read it immediately after the DELETE being measured; another SQL statement can overwrite the implicit cursor state.

Do not rely solely on deleted row count as proof of correctness. Also verify the keys of selected rows, child tables, and business state.

## 5. Transactions: COMMIT, ROLLBACK, and SAVEPOINT

DELETE is DML, so changes belong to the current transaction:

~~~sql
DELETE FROM lab_del_task
WHERE task_id = 1001;

-- If a mistake is found:
ROLLBACK;
~~~

After ROLLBACK, task row 1001 is restored provided no COMMIT or other transaction boundary occurred.

If deleting multiple groups of data in one transaction, you can set a SAVEPOINT:

~~~sql
SAVEPOINT before_cleanup;

DELETE FROM lab_del_task
WHERE task_status = 'DONE';

-- Check results; if not right:
ROLLBACK TO before_cleanup;
~~~

**ROLLBACK TO** undoes changes after the savepoint while keeping the transaction open. **COMMIT** ends the transaction and makes changes permanent; afterward, ROLLBACK cannot restore deleted rows.

### 5.1. Implicit COMMIT and Client Tools

Oracle automatically commits before and after certain DDL commands. **DELETE** is not DDL and does not commit on its own. However, SQL Developer, SQL*Plus, JDBC clients, or other tools may have an autocommit option. Know your tool's transaction mode before testing delete operations.

## 6. Default Foreign Key Behavior: Cannot Delete Parent While Children Exist

In the lab schema, foreign key **FK_LAB_DEL_EMP_DEPT** does not specify an ON DELETE action. While employees reference department 10, the statement:

~~~sql
DELETE FROM lab_del_department
WHERE department_id = 10;
~~~

will be rejected by Oracle with the common error:

~~~text
ORA-02292: integrity constraint (SCHEMA.FK_LAB_DEL_EMP_DEPT) violated - child record found
~~~

The message means child rows still reference the primary key of the department being deleted. Oracle protects referential integrity: it forbids creating employees whose **DEPARTMENT_ID** points to a nonexistent department.

Similarly, deleting employee 101 while task 1001 or 1002 still references that employee is blocked by **FK_LAB_DEL_TASK_EMP**.

### 6.1. Deleting Bottom-Up from Children to Parent

If the design does not use ON DELETE CASCADE, child rows must be deleted first:

~~~sql
-- Deepest level: tasks of employees in department 10.
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id = 10
);

-- After tasks are deleted, delete employees in department 10.
DELETE FROM lab_del_employee
WHERE department_id = 10;

-- Finally, delete the department.
DELETE FROM lab_del_department
WHERE department_id = 10;
~~~

The order is:

1. Delete tasks (children of employee).
2. Delete employees (children of department).
3. Delete department (parent).

If an employee has multiple types of child records across different tables, handle **all child tables** before deleting the employee. If a department has additional child tables like history, budgets, or assets, inspect those foreign keys before deleting the department.

### 6.2. Inspect Each Level Before Deleting

Before deleting tasks in department 10:

~~~sql
SELECT t.*
FROM lab_del_task t
JOIN lab_del_employee e
  ON e.employee_id = t.employee_id
WHERE e.department_id = 10
ORDER BY t.task_id;
~~~

Check employees:

~~~sql
SELECT *
FROM lab_del_employee
WHERE department_id = 10
ORDER BY employee_id;
~~~

Check department:

~~~sql
SELECT *
FROM lab_del_department
WHERE department_id = 10;
~~~

These SELECTs help confirm related datasets before running the DELETE sequence. They do not lock or freeze the row set if other sessions can modify data concurrently; for operations requiring strict consistency, design appropriate transactions, locks, and isolation levels.

## 7. Using EXISTS to Delete Child Rows by Parent Condition

A common requirement is deleting tasks belonging to inactive employees or matching a specific parent status.

Example: deleting tasks of inactive employees:

~~~sql
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.employee_status = 'INACTIVE'
);
~~~

**EXISTS** checks whether at least one employee row satisfies the condition for the current task. The correlated subquery references **t.employee_id** from the candidate row.

An alternative uses IN:

~~~sql
DELETE FROM lab_del_task
WHERE employee_id IN (
    SELECT employee_id
    FROM lab_del_employee
    WHERE employee_status = 'INACTIVE'
);
~~~

Both forms work when the subquery returns a list of keys. EXISTS expresses correlated relationships clearly; IN is also readable for key sets. When using NOT IN, pay special attention to NULLs in the subquery result, as NULL can prevent the condition from returning TRUE. **NOT EXISTS** is usually safer to reason about when deleting rows without related records.

### 7.1. Deleting Employees with No Remaining Child Rows

Example deleting inactive employees who have no tasks:

~~~sql
DELETE FROM lab_del_employee e
WHERE e.employee_status = 'INACTIVE'
  AND NOT EXISTS (
      SELECT 1
      FROM lab_del_task t
      WHERE t.employee_id = e.employee_id
  );
~~~

NOT EXISTS ensures only employees with zero related tasks are selected. This is the business filter; the foreign key remains the final safeguard if data changes concurrently.

### 7.2. Deleting Parent Rows Based on Child Table Conditions

Example: deleting an employee only when all tasks are completed. You must also define what happens if there are zero tasks. One way to express "has at least one task and has no unfinished tasks":

~~~sql
DELETE FROM lab_del_employee e
WHERE EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
)
AND NOT EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
      AND t.task_status <> 'DONE'
);
~~~

Before using this, remember that the foreign key does not cascade: tasks still exist, so DELETE on employee will still hit ORA-02292. The predicate only identifies employees meeting the business criteria; you still must delete tasks first or use an appropriate cascade design.

## 8. Deleting Multi-Level Hierarchical Data

Given a hierarchy:

~~~text
DEPARTMENT
  ├── EMPLOYEE
  │     ├── TASK
  │     └── EMPLOYEE_NOTE
  └── DEPARTMENT_DOCUMENT
~~~

To delete a department without cascade, delete every deepest child branch first, then work upward:

1. Delete TASK and EMPLOYEE_NOTE belonging to employees in the department.
2. Delete EMPLOYEE belonging to the department.
3. Delete DEPARTMENT_DOCUMENT belonging to the department.
4. Delete DEPARTMENT.

Do not look only at direct relationships. A parent row may be referenced by multiple independent child tables; even a single remaining child row will cause its foreign key to block the delete.

### 8.1. Deleting a Branch with EXISTS

Pattern for a child table:

~~~sql
DELETE FROM child_table c
WHERE EXISTS (
    SELECT 1
    FROM parent_table p
    WHERE p.parent_id = c.parent_id
      AND p.parent_id = :target_parent_id
);
~~~

This pattern deletes child rows belonging to a target parent ID. For a grandchild table, join through the child table to identify the ancestor:

~~~sql
DELETE FROM grandchild_table g
WHERE EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.child_id = g.child_id
      AND c.parent_id = :target_parent_id
);
~~~

Substitute table names, keys, and conditions for your real schema. Run a SELECT with the same condition to verify the exact branch to be deleted.

## 9. ON DELETE CASCADE: Automatically Deleting Children When Parent Is Deleted

If business rules dictate that child rows have no independent meaning once the parent row is deleted, you can declare the foreign key with **ON DELETE CASCADE**.

This action is declared on the **foreign key in the child table**:

~~~sql
CREATE TABLE lab_c_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_c_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_c_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_c_department (department_id)
      ON DELETE CASCADE
);

CREATE TABLE lab_c_task (
    task_id     NUMBER(7) PRIMARY KEY,
    employee_id NUMBER(6) NOT NULL,
    task_name   VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT fk_lab_c_task_emp
      FOREIGN KEY (employee_id)
      REFERENCES lab_c_employee (employee_id)
      ON DELETE CASCADE
);
~~~

Insert data:

~~~sql
INSERT INTO lab_c_department VALUES (10, 'Sales');
INSERT INTO lab_c_department VALUES (20, 'Support');

INSERT INTO lab_c_employee VALUES (101, 10, 'An');
INSERT INTO lab_c_employee VALUES (102, 10, 'Binh');
INSERT INTO lab_c_employee VALUES (201, 20, 'Chi');

INSERT INTO lab_c_task VALUES (1001, 101, 'Prepare report');
INSERT INTO lab_c_task VALUES (1002, 101, 'Call customer');
INSERT INTO lab_c_task VALUES (1003, 102, 'Archive contract');
INSERT INTO lab_c_task VALUES (2001, 201, 'Resolve case');

COMMIT;
~~~

When deleting department 10:

~~~sql
DELETE FROM lab_c_department
WHERE department_id = 10;
~~~

Oracle automatically deletes employees in department 10 via **FK_LAB_C_EMP_DEPT**; subsequently, tasks referencing those employees are also deleted via **FK_LAB_C_TASK_EMP**.

Check:

~~~sql
SELECT * FROM lab_c_department ORDER BY department_id;
SELECT * FROM lab_c_employee ORDER BY employee_id;
SELECT * FROM lab_c_task ORDER BY task_id;
~~~

After DELETE:

- Department 10 is gone.
- Employees 101 and 102 are gone.
- Tasks 1001, 1002, and 1003 are gone.
- Department 20, employee 201, and task 2001 remain.

This is a multi-level cascade delete because each parent-child relationship declares the corresponding cascade action.

### 9.1. ON DELETE CASCADE Is Not DELETE Clause Syntax

~~~sql
-- Not valid Oracle syntax:
DELETE FROM lab_c_department
WHERE department_id = 10
CASCADE;
~~~

Oracle has no `DELETE ... CASCADE` clause like that. Cascade behavior is an attribute of the foreign key constraint, defined when creating or altering the constraint.

### 9.2. When Should You Use Cascade?

Suitable when:

- Child rows depend entirely on the parent row.
- Child data does not need to exist once the parent is deleted.
- Delete rules are consistent across all applications and database access paths.
- Cascade scope is well understood and controlled.

Unsuitable or requires careful thought when:

- Child rows are history, vouchers, logs, or data governed by retention policies.
- Child data is referenced by multiple independent workflows.
- Users need per-level audit trails or deletion reasons.
- One parent delete could unexpectedly wipe massive amounts of data.

Cascade simplifies DELETE sequences, but it expands the blast radius of a parent delete. Before using it, list every cascade relationship along the path.

## 10. ON DELETE SET NULL: Keep Children, Clear Link to Parent

Some domains want to keep child rows while allowing them to no longer belong to a parent row. In that case, use **ON DELETE SET NULL**:

~~~sql
CREATE TABLE lab_s_department (
    department_id   NUMBER(4) PRIMARY KEY,
    department_name VARCHAR2(60 CHAR) NOT NULL
);

CREATE TABLE lab_s_employee (
    employee_id   NUMBER(6) PRIMARY KEY,
    department_id NUMBER(4) NULL,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_s_emp_dept
      FOREIGN KEY (department_id)
      REFERENCES lab_s_department (department_id)
      ON DELETE SET NULL
);
~~~

Insert data:

~~~sql
INSERT INTO lab_s_department VALUES (10, 'Sales');
INSERT INTO lab_s_employee VALUES (101, 10, 'An');
INSERT INTO lab_s_employee VALUES (102, 10, 'Binh');
COMMIT;
~~~

Delete department:

~~~sql
DELETE FROM lab_s_department
WHERE department_id = 10;
~~~

Result:

| EMPLOYEE_ID | DEPARTMENT_ID | EMPLOYEE_NAME |
|---:|---:|---|
| 101 | NULL | An |
| 102 | NULL | Binh |

Employee rows remain, but **DEPARTMENT_ID** is set to NULL. Therefore, the foreign key column must allow NULL. If the column is declared NOT NULL, SET NULL cannot succeed due to constraint conflict.

### 10.1. Choosing RESTRICT, CASCADE, or SET NULL

Oracle does not use a separate RESTRICT keyword in foreign key syntax like some other DBMSs. When neither **ON DELETE CASCADE** nor **ON DELETE SET NULL** is declared, the default behavior blocks parent deletion when referencing child rows exist.

| Foreign key configuration | When parent row is deleted |
|---|---|
| No ON DELETE action declared | Blocked if referencing child rows exist |
| **ON DELETE CASCADE** | Referencing child rows are deleted |
| **ON DELETE SET NULL** | Foreign key column on child rows is set to NULL |

Choose based on data rules, not just statement convenience.

## 11. Cascading Multiple Parent Rows and Blast Radius

With cascade, one DELETE can modify multiple tables. For example:

~~~sql
DELETE FROM lab_c_department
WHERE department_id IN (10, 20);
~~~

This statement can delete all employees and tasks belonging to both departments. The affected row count reported for the target table does not fully reflect total cascaded rows in child tables.

Before running, check each level:

~~~sql
SELECT COUNT(*) AS departments_to_delete
FROM lab_c_department
WHERE department_id IN (10, 20);

SELECT COUNT(*) AS employees_affected
FROM lab_c_employee
WHERE department_id IN (10, 20);

SELECT COUNT(*) AS tasks_affected
FROM lab_c_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_c_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id IN (10, 20)
);
~~~

These count queries reveal the expected scale per table. After deleting, re-verify both the parent table and child tables to confirm impact.

## 12. Deleting with Subqueries and Cross-Table Relationships

Oracle allows subqueries in DELETE predicates. Common patterns:

### 12.1. Deleting Tasks Belonging to a Department

~~~sql
DELETE FROM lab_del_task t
WHERE EXISTS (
    SELECT 1
    FROM lab_del_employee e
    WHERE e.employee_id = t.employee_id
      AND e.department_id = 20
);
~~~

### 12.2. Deleting Employees Without Tasks

~~~sql
DELETE FROM lab_del_employee e
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_del_task t
    WHERE t.employee_id = e.employee_id
);
~~~

### 12.3. Deleting Orders Without Detail Lines

~~~sql
DELETE FROM lab_order_header h
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_order_line l
    WHERE l.order_id = h.order_id
);
~~~

This is an illustrative pattern; these table names are not part of the lab schema created in section 2. If the detail table has a foreign key referencing the order header, orders without detail lines can be deleted without violating that relationship.

### 12.4. DELETE with EXISTS Does Not Automatically Delete Child Tables

**EXISTS** only filters rows of the **DELETE target table**. It does not delete rows from other tables. To delete across multiple tables, issue multiple DELETEs in proper order or use configured ON DELETE CASCADE.

## 13. One DELETE Targets Only One Table

Standard Oracle DELETE removes rows from a single target table or updatable view. Do not use syntax from other SQL dialects:

~~~sql
-- Not valid Oracle DELETE JOIN syntax:
DELETE e, t
FROM employee e
JOIN task t ON t.employee_id = e.employee_id;
~~~

To delete from one table based on another table, use a correlated subquery/EXISTS:

~~~sql
DELETE FROM employee e
WHERE EXISTS (
    SELECT 1
    FROM department d
    WHERE d.department_id = e.department_id
      AND d.department_status = 'CLOSED'
);
~~~

If you need to delete both employees and tasks, delete tasks first then employees, or configure cascade on the corresponding foreign key. Do not assume a single DELETE can delete multiple tables simultaneously like a JOIN operation.

## 14. Deleting in Self-Referencing Relationships

A table can contain a foreign key referencing itself, such as employees having managers:

~~~sql
CREATE TABLE lab_del_org_employee (
    employee_id NUMBER(6) PRIMARY KEY,
    manager_id  NUMBER(6),
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    CONSTRAINT fk_lab_del_manager
      FOREIGN KEY (manager_id)
      REFERENCES lab_del_org_employee (employee_id)
);
~~~

If a manager still has subordinate employees referencing them, deleting the manager is blocked by the foreign key by default. Two design directions exist:

- Delete subordinates first, moving from leaves to root, if the entire branch must be removed.
- Declare **ON DELETE SET NULL** if subordinates remain in the system when a manager leaves and need their link cleared.

For deep organizational trees, identify all descendants before deleting. Oracle supports hierarchical queries with **CONNECT BY**:

~~~sql
SELECT employee_id, manager_id, LEVEL AS hierarchy_level
FROM lab_del_org_employee
START WITH employee_id = :root_employee_id
CONNECT BY PRIOR employee_id = manager_id;
~~~

The query lists the root employee and all subordinates. To delete a tree in a non-cascading self-referencing relationship, delete leaf nodes before parent nodes; this order can be built using descending LEVEL in a key-selection step, though you must handle multi-branch trees, data cycles, and specific foreign keys. Never run DELETE on the root before handling descendants.

## 15. DEFERRABLE Constraints and Foreign Key Check Timing

Normally, Oracle checks foreign keys immediately when the DML statement requires integrity checking. A constraint declared **DEFERRABLE** can defer checking until the end of the transaction or a specified point.

Example declaration:

~~~sql
CONSTRAINT fk_child_parent
  FOREIGN KEY (parent_id)
  REFERENCES parent_table(parent_id)
  DEFERRABLE INITIALLY IMMEDIATE
~~~

Within a transaction, you can request deferral:

~~~sql
SET CONSTRAINTS fk_child_parent DEFERRED;
~~~

This can allow a sequence of operations to temporarily violate the relationship within the transaction as long as it is valid when constraints are checked. However, it does not delete child data automatically and does not replace a cascade policy. Only use it when the business model truly requires deferred checking; by default, deleting children before parents is clearer.

## 16. Triggers and Side Effects of DELETE

A table can have **BEFORE DELETE** or **AFTER DELETE** triggers at row level or statement level. Triggers can write audits, update other tables, or enforce additional business rules.

Before deleting in production, check:

- Are there DELETE triggers on the target table?
- Do triggers write logs or update related tables?
- Are there cascading foreign keys leading to multiple tables?
- Do cascade operations fire triggers on child tables per Oracle behavior for those constraints/triggers?
- Is there an audit policy or CDC/replication mechanism tracking deletes?

Do not assume the row count reported by DELETE reflects the full impact of triggers and cascades. If business triggers exist, inspect the trigger code and test in an appropriate test environment.

## 17. Multi-Row DELETE: Undo, Redo, Locks, and Performance

DELETE creates data changes that can be rolled back, so Oracle stores undo information and generates redo according to database mechanisms. On large datasets, the operation can:

- Take time scanning rows, checking constraints, and firing triggers.
- Generate significant undo/redo volume.
- Hold row locks until the transaction ends.
- Cause other sessions to wait if they access the same rows or related resources.
- Multiply cascade cost if one parent row has many children across multiple levels.

### 17.1. Batch Deletion

If you need to delete large volumes in batches, you can select a set of ROWIDs and delete them:

~~~sql
DELETE FROM lab_del_task
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid
        FROM lab_del_task
        WHERE task_status = 'DONE'
          AND created_at < DATE '2025-01-01'
        ORDER BY created_at, task_id
    )
    WHERE ROWNUM <= 1000
);
~~~

This pattern illustrates batches of up to 1000 rows per run. The subquery sorts candidates and uses ROWNUM to limit ROWIDs. Repeat in a controlled loop until no matching rows remain; each batch can be committed per application transaction policy.

Batching changes transaction characteristics: if you commit after each batch, earlier batches cannot be rolled back together with later batches. For parent-child data, ensure correct delete order in every batch and never leave a parent deleted while children remain.

### 17.2. No Direct DELETE ... LIMIT Like Some Dialects

~~~sql
-- Not valid Oracle DELETE syntax:
DELETE FROM lab_del_task
WHERE task_status = 'DONE'
LIMIT 1000;
~~~

Use a subquery selecting ROWID/keys with ROWNUM or syntax appropriate to your Oracle version.

### 17.3. Indexes on Foreign Keys

Oracle does not automatically create an index for every foreign key. An index on a foreign key column can help locate child rows, perform JOINs, and support certain parent maintenance/delete operations. When deleting a parent, Oracle's check for referencing child rows can be expensive if the child table is large and the FK column lacks a suitable index.

Do not create indexes mechanically: examine read/write workload, cardinality, selectivity, and execution plans. Indexes add overhead to INSERT/UPDATE/DELETE on the child table.

## 18. Locking and Concurrent Changes

Between running a preview SELECT and executing DELETE, another session can insert or modify related rows. Therefore, an earlier SELECT does not guarantee the row set will be identical when DELETE runs.

Key points to understand:

- DELETE locks affected rows under Oracle's row locking mechanism.
- Locks are held until COMMIT or ROLLBACK.
- Foreign key checks and cascades can extend the impact to multiple related rows.
- If you need to stabilize the parent set before deleting within a transaction, consider **SELECT ... FOR UPDATE** on the relevant parent rows; note this does not automatically lock unselected child rows and requires synchronization across write paths.
- Isolation levels, lock ordering, and deadlock retries must fit the application.

Do not keep large delete transactions open longer than necessary. Conversely, do not split transactions arbitrarily if business logic requires all parent-child operations to succeed or fail together.

## 19. Inspecting Foreign Keys and ON DELETE Actions in the Data Dictionary

You can view constraints in the current schema via **USER_CONSTRAINTS**:

~~~sql
SELECT
    constraint_name,
    table_name,
    constraint_type,
    status,
    delete_rule,
    deferrable,
    deferred
FROM user_constraints
WHERE constraint_type = 'R'
  AND table_name IN (
      'LAB_DEL_EMPLOYEE',
      'LAB_DEL_TASK',
      'LAB_C_EMPLOYEE',
      'LAB_C_TASK'
  )
ORDER BY table_name, constraint_name;
~~~

Notable columns:

- **CONSTRAINT_TYPE = 'R'**: foreign key.
- **STATUS**: whether the constraint is ENABLED or DISABLED.
- **DELETE_RULE**: referential delete action, such as NO ACTION, CASCADE, or SET NULL per Oracle metadata.
- **DEFERRABLE** and **DEFERRED**: check deferral capability and state.

To see which columns participate in a foreign key, join **USER_CONS_COLUMNS**:

~~~sql
SELECT
    c.constraint_name,
    c.table_name,
    cc.column_name,
    c.r_constraint_name,
    c.delete_rule
FROM user_constraints c
JOIN user_cons_columns cc
  ON cc.constraint_name = c.constraint_name
WHERE c.constraint_type = 'R'
ORDER BY c.table_name, c.constraint_name, cc.position;
~~~

When inspecting objects in other schemas with appropriate privileges, use **ALL_CONSTRAINTS/ALL_CONS_COLUMNS** or **DBA_CONSTRAINTS/DBA_CONS_COLUMNS** according to granted privileges. DBA privileges are not needed just to practice in your own schema.

## 20. Why Should You Not Disable Foreign Keys to Delete a Parent?

A dangerous shortcut is disabling a foreign key, deleting a parent row, and forgetting to check or re-enable the constraint. The child table can then contain foreign keys with no matching parent row (orphans).

If special maintenance truly requires it, there must be a plan:

1. Identify all affected relationships and data.
2. Have backups/recovery capability aligned with operational procedures.
3. Perform within a controlled maintenance window.
4. Check for orphans before re-enabling the constraint.
5. Re-enable the constraint and verify ENABLED/VALIDATED status.

In normal application operations, keep foreign keys enabled and delete children first, or use a properly designed ON DELETE action.

## 21. DELETE and TRUNCATE When a Table Is Referenced

Conditional **DELETE** can remove partial data and respects foreign keys. **TRUNCATE** is DDL removing all rows of a table; Oracle enforces restrictions when a parent table is referenced by an enabled foreign key. In that case, TRUNCATE on the parent table can be rejected (e.g., **ORA-02266**) even when the child table has zero referencing rows, depending on constraint configuration.

Do not switch from DELETE to TRUNCATE just to avoid handling parent-child relationships. Choose the statement based on transaction requirements, filter conditions, and data relationships.

## 22. Common Errors and Troubleshooting

| Error/Symptom | Cause | Resolution |
|---|---|---|
| **ORA-02292: child record found** | Deleting parent while child rows still reference it | Delete children first or use designed ON DELETE CASCADE/SET NULL |
| **ORA-02291: parent key not found** | Inserting/updating FK pointing to nonexistent parent | Create parent first or fix foreign key |
| **ORA-01400: cannot insert NULL** | SET NULL action conflicts with NOT NULL column | Make column nullable or choose another delete policy |
| More rows deleted than expected | Overly broad WHERE, wrong AND/OR, or wrong subquery selection | Run SELECT with same predicate, COUNT, and check keys first |
| Cannot delete even though SELECT sees data | Privileges, views, triggers, constraints, or another session | Read exact Oracle error and inspect related objects |
| Session waiting on lock | Another transaction holds row lock | Identify blocker, handle timeout/retry per application workflow |
| Parent deleted but child data remains | FK has no cascade or SET NULL, or only one branch deleted | Check DELETE_RULE and all related FKs |
| Orphans after maintenance | Constraint disabled or data loaded improperly | Check referential data and enable/validate constraint |

## 23. Practice Exercises

### Exercise 1 — Simple Conditional Delete

Delete tasks with status CANCELLED in table **LAB_DEL_TASK**.

**Hint:**

~~~sql
DELETE FROM lab_del_task
WHERE task_status = 'CANCELLED';
~~~

Before running, use SELECT with the same condition to inspect the selected tasks.

### Exercise 2 — Delete by Date Range

Delete DONE tasks created in 2024.

**Hint:** use the range **created_at >= DATE '2024-01-01' AND created_at < DATE '2025-01-01'**.

### Exercise 3 — Delete Tasks of Inactive Employees

Write a DELETE using EXISTS to delete tasks belonging to employees with **EMPLOYEE_STATUS = 'INACTIVE'**.

**Question:** Why is EXISTS more suitable than direct JOIN syntax in DELETE used in some other DBMSs?

**Guidance:** Oracle DELETE targets one table; EXISTS filters target table rows based on the related table.

### Exercise 4 — Non-Cascading Department Delete

Delete department 10 in schema **LAB_DEL_***. List the DELETE sequence needed to avoid violating foreign keys.

**Guidance answer:** delete tasks of employees in department 10; delete employees in department 10; finally delete department 10.

### Exercise 5 — Observe ORA-02292

On undeleted lab data, try deleting a department that has employees without deleting children first.

**Question:** Which constraint blocks the operation and why?

**Guidance:** **FK_LAB_DEL_EMP_DEPT** references department from employee.

### Exercise 6 — Test ON DELETE CASCADE

Recreate the **LAB_C_*** tables, delete department 10, then check employees/tasks.

**Question:** Why can a single DELETE on the department table remove multiple rows across two child tables?

**Guidance:** the corresponding foreign keys are declared ON DELETE CASCADE at each level.

### Exercise 7 — Test ON DELETE SET NULL

Create the **LAB_S_*** tables, delete department 10, and check employees.

**Question:** Why do employees still exist while department_id becomes NULL?

**Guidance:** the foreign key declares ON DELETE SET NULL and the department_id column allows NULL.

### Exercise 8 — Count Deletion Scope

Write three SELECT COUNT queries to count affected departments, employees, and tasks if one department is cascade-deleted.

**Guidance:** count parent by key condition; count children by FK; count grandchildren using EXISTS joined through the child table.

### Exercise 9 — Batch Delete

Write a DELETE using ROWID and ROWNUM to delete up to 100 old DONE tasks per batch.

**Question:** If you commit after each batch, can you roll back all committed batches together?

**Answer:** No. Each COMMIT ends that batch's transaction; rollback only undoes uncommitted changes in the current transaction.

## 24. Safe Parent-Child Deletion Workflow

Before a delete operation involving multiple tables, follow this workflow:

1. **Identify target table and keys:** which parent rows need deletion, and what predicate identifies them accurately?
2. **Look up foreign keys:** which tables reference the target table, directly and indirectly?
3. **Determine delete rule:** default block, CASCADE, or SET NULL?
4. **Preview affected data:** SELECT and COUNT at every level, checking the deepest child branches.
5. **Choose strategy:** delete children first, designed cascade, or business-driven set null.
6. **Execute in an appropriate transaction:** use SAVEPOINT when needed, never commit before verifying.
7. **Verify results:** check parent, children, grandchildren, and related audit/status data.
8. **End transaction:** COMMIT when results are right; ROLLBACK if discrepancies appear.

Decision diagram:

~~~text
Need to delete parent row?
        |
        v
Are there referencing child rows?
       / \
     No   Yes
      |    |
      |    v
      |  Check ON DELETE rule
      |       |
      |   +---+---+
      |   |       |
      |   v       v
      | CASCADE  SET NULL
      |   |       |
      |   v       v
      | Delete    Keep child, clear FK
      | children  (column must be nullable)
      | auto      |
      |   |       |
      |   +---+---+
      |       |
      |       v
      |    Check impact
      |
      +------> DELETE parent
                 |
                 v
           Verify result
                 |
            +----+----+
            |         |
          Right     Wrong
            |         |
            v         v
          COMMIT    ROLLBACK
~~~

**DELETE ... WHERE** determines **which rows are deleted**; foreign keys determine **whether a parent row can be deleted while children exist and how child data is handled**. Understanding both parts lets you delete data accurately under conditions, preserve referential integrity, and control impact across the entire parent-child hierarchy.
