# INNER JOIN on Single Keys, Composite Keys, and Multi-Column Conditions in Oracle Database

`INNER JOIN` combines rows from two or more tables when the join condition between them is satisfied. In the relational model, join conditions are typically based on primary keys and foreign keys, though multiple columns can also be used to identify a matching record.

Three cases should be distinguished:

- **Single-key join:** one column in one table matches one column in the other table, for example `EMPLOYEES.DEPT_ID = DEPARTMENTS.DEPT_ID`.
- **Composite-key join:** multiple columns that make up the key must all match, for example `(TENANT_ID, PROJECT_CODE)`.
- **Multi-condition join:** a row matches only when multiple conditions in the `ON` clause are simultaneously satisfied, usually combined with `AND`.

If a component of a composite key is omitted, the query may mismatch data across tenants or produce more rows than expected. If the nature of `INNER JOIN` is misunderstood, a query author may unintentionally exclude rows that have no matching record in the other table.

This lesson covers Oracle SQL syntax, reading parent–child relationships, handling single and composite keys, combining multi-column conditions, controlling row counts after a join, common pitfalls, and practical exercises.

## 1. What is INNER JOIN?

### 1.1. Meaning

`INNER JOIN` returns only combinations of rows for which the join condition evaluates to **TRUE**. Rows that cannot find a matching row on the other side will not appear in the result.

Example of a departments and employees model:

```text
DEMO_DEPARTMENTS                 DEMO_EMPLOYEES
+---------+-------------+         +--------+----------+---------+
| DEPT_ID | DEPT_NAME  |         | EMP_ID | EMP_NAME | DEPT_ID |
+---------+-------------+         +--------+----------+---------+
| 10      | Engineering |         | 101    | An       | 10      |
| 20      | Sales       |         | 102    | Binh     | 10      |
| 30      | Finance     |         | 103    | Chi      | 20      |
+---------+-------------+         | 104    | Dung     | NULL    |
                                  +--------+----------+---------+
                 DEPT_ID = DEPT_ID
                         |
                         v
                 INNER JOIN result
                 +--------+----------+-------------+
                 | EMP_ID | EMP_NAME | DEPT_NAME   |
                 +--------+----------+-------------+
                 | 101    | An       | Engineering |
                 | 102    | Binh     | Engineering |
                 | 103    | Chi      | Sales       |
                 +--------+----------+-------------+
```

- Employees 101 and 102 belong to department 10.
- Employee 103 belongs to department 20.
- Employee 104 has `DEPT_ID=NULL`, so they do not match under the `=` comparison.
- Department 30 has no employees, so it does not appear in the result either.

### 1.2. ANSI JOIN Syntax in Oracle

Recommended syntax:

```sql
SELECT select_list
FROM   table_a a
INNER JOIN table_b b
        ON a.key_column = b.key_column;
```

Example:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
ORDER  BY e.emp_id;
```

Components:

- `DEMO_EMPLOYEES e`: employees table, alias `e`.
- `DEMO_DEPARTMENTS d`: departments table, alias `d`.
- `ON d.dept_id = e.dept_id`: join condition.
- `SELECT` retrieves only the columns needed for output.
- `ORDER BY` specifies the result order; a join by itself does not guarantee order.

In Oracle, writing `JOIN` without specifying the join type defaults to an inner join in some forms of syntax. However, explicitly writing `INNER JOIN` makes the intent immediately clear to readers.

### 1.3. How does INNER JOIN differ from WHERE?

Legacy syntax can place the join condition in `WHERE`:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e,
       demo_departments d
WHERE  d.dept_id = e.dept_id;
```

For a simple inner join, the result is equivalent to ANSI syntax:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id;
```

However, you should use the ANSI `JOIN ... ON` syntax to clearly separate **table join conditions** from **row filter conditions**. When queries involve multiple tables or outer joins, this separation is especially helpful and avoids errors caused by mixing legacy and modern syntax.

## 2. Preparing Single-Key Practice Data

### 2.1. Create the departments table

```sql
CREATE TABLE demo_departments (
    dept_id   NUMBER(5) PRIMARY KEY,
    dept_name VARCHAR2(100) NOT NULL
);
```

### 2.2. Create the employees table

```sql
CREATE TABLE demo_employees (
    emp_id   NUMBER(10) PRIMARY KEY,
    emp_name VARCHAR2(100) NOT NULL,
    dept_id  NUMBER(5),
    CONSTRAINT fk_demo_emp_dept
        FOREIGN KEY (dept_id)
        REFERENCES demo_departments(dept_id)
);
```

The `DEPT_ID` column in the employees table is a foreign key referencing the departments primary key. This column allows NULL because `NOT NULL` is not declared.

### 2.3. Insert data

```sql
INSERT INTO demo_departments VALUES (10, 'Engineering');
INSERT INTO demo_departments VALUES (20, 'Sales');
INSERT INTO demo_departments VALUES (30, 'Finance');

INSERT INTO demo_employees VALUES (101, 'An', 10);
INSERT INTO demo_employees VALUES (102, 'Binh', 10);
INSERT INTO demo_employees VALUES (103, 'Chi', 20);
INSERT INTO demo_employees VALUES (104, 'Dung', NULL);

COMMIT;
```

This dataset contains:
- Three departments.
- Four employees.
- Two employees in the same department 10.
- One employee not yet assigned to a department.
- Department 30 with no employees yet.

### 2.4. Joining on a single key

```sql
SELECT e.emp_id,
       e.emp_name,
       e.dept_id,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON e.dept_id = d.dept_id
ORDER  BY e.emp_id;
```

Result:

| EMP_ID | EMP_NAME | DEPT_ID | DEPT_NAME |
| ---: | --- | ---: | --- |
| 101 | An | 10 | Engineering |
| 102 | Binh | 10 | Engineering |
| 103 | Chi | 20 | Sales |

Employee row 104 is not returned because `NULL = 10` or `NULL = NULL` does not evaluate to TRUE in the join condition. The Finance department does not appear either because no employee matches it.

### 2.5. A single key does not mean a one-to-one relationship

A primary key in a parent table can be referenced by multiple rows in a child table. In the example:

- `DEMO_DEPARTMENTS.DEPT_ID` is unique.
- `DEMO_EMPLOYEES.DEPT_ID` can repeat.
- One department can have many employees.

This is a **one-to-many (1:N)** relationship. When joined, a department row can appear multiple times, once for each matching employee.

If the join column is unique in both tables, the result can be one-to-one. If uniqueness does not hold on both sides, a single value can match multiple rows in both tables and produce a many-to-many result.

## 3. Single-Key Join with Filter Conditions

### 3.1. Filtering a table after joining

For example, retrieving only employees in Engineering:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
WHERE  d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

`ON` specifies how the two tables link by `DEPT_ID`. `WHERE` filters the joined rows by department name.

### 3.2. Filter conditions and join conditions can both reside in ON

Example:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
       AND d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

Because this is an `INNER JOIN`, moving the corresponding filter condition from `ON` to `WHERE` usually produces the same result set. Even so, the style should be consistent and readable:

- `ON` describes how two tables match each other.
- `WHERE` describes the result filtering criteria.

With `LEFT JOIN` or `RIGHT JOIN`, condition placement can significantly change the meaning; do not mechanically move conditions between ON and WHERE.

### 3.3. Chaining joins across multiple tables

For example, a system with employees, departments, and work locations:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name,
       l.city
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
INNER JOIN demo_department_locations dl
        ON dl.dept_id = d.dept_id
INNER JOIN demo_locations l
        ON l.location_id = dl.location_id
ORDER  BY e.emp_id;
```

Each `INNER JOIN` adds another relationship to the result set. A row remains in the result only if it satisfies the join condition at every step.

The `DEMO_DEPARTMENT_LOCATIONS` and `DEMO_LOCATIONS` tables in this example are an extended illustrative model; they must be created and populated before running the query. Do not run the query if those tables do not yet exist.

### 3.4. Aliases help avoid ambiguity

When multiple tables share columns with the same name, always use aliases:

```sql
SELECT e.emp_id,
       e.dept_id AS employee_dept_id,
       d.dept_id AS department_id
FROM   demo_employees e
INNER JOIN demo_departments d
        ON e.dept_id = d.dept_id;
```

If you write `SELECT dept_id` when both tables have a `DEPT_ID` column, Oracle may raise `ORA-00918: column ambiguously defined`. Use `e.dept_id` or `d.dept_id` to qualify the column source.

## 4. INNER JOIN on a Composite Key

### 4.1. What is a composite key?

A composite key consists of **two or more columns combined** to uniquely identify a row. Individual columns may repeat, but their combination is unique.

For example, a multi-tenant system may have the same project code across tenants:

| TENANT_ID | PROJECT_CODE | PROJECT_NAME |
| ---: | --- | --- |
| 1 | ERP | ERP - Tenant A |
| 2 | ERP | ERP - Tenant B |
| 1 | CRM | CRM - Tenant A |

Here `PROJECT_CODE` is not globally unique across the table because both tenant 1 and tenant 2 have an ERP project. The true identifying key is:

```text
(TENANT_ID, PROJECT_CODE)
```

Joining only on `PROJECT_CODE` omits part of the key and can match one tenant's project with another tenant's tasks.

### 4.2. Create a parent table with a composite primary key

```sql
CREATE TABLE demo_projects (
    tenant_id    NUMBER(5) NOT NULL,
    project_code VARCHAR2(20) NOT NULL,
    project_name VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_projects
        PRIMARY KEY (tenant_id, project_code)
);
```

Oracle enforces that the combination of `TENANT_ID` and `PROJECT_CODE` is unique.

### 4.3. Create a child table referencing the composite key

```sql
CREATE TABLE demo_project_tasks (
    task_id      NUMBER(10) PRIMARY KEY,
    tenant_id    NUMBER(5) NOT NULL,
    project_code VARCHAR2(20) NOT NULL,
    task_name    VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_task_project
        FOREIGN KEY (tenant_id, project_code)
        REFERENCES demo_projects (tenant_id, project_code)
);
```

The column order in the FK must correspond to the column order in the referenced key:

- First column: `TENANT_ID`.
- Second column: `PROJECT_CODE`.

This composite foreign key ensures each task references a project that matches both the tenant and the project code.

### 4.4. Insert data for two tenants sharing a project code

```sql
INSERT INTO demo_projects VALUES (1, 'ERP', 'ERP - Tenant A');
INSERT INTO demo_projects VALUES (2, 'ERP', 'ERP - Tenant B');
INSERT INTO demo_projects VALUES (1, 'CRM', 'CRM - Tenant A');

INSERT INTO demo_project_tasks VALUES (
    101, 1, 'ERP', 'Build finance module'
);
INSERT INTO demo_project_tasks VALUES (
    102, 2, 'ERP', 'Build sales module'
);
INSERT INTO demo_project_tasks VALUES (
    103, 1, 'CRM', 'Design customer screen'
);

COMMIT;
```

### 4.5. Correct INNER JOIN on both key columns

```sql
SELECT t.task_id,
       t.task_name,
       t.tenant_id,
       t.project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
ORDER  BY t.task_id;
```

Result:

| TASK_ID | TASK_NAME | TENANT_ID | PROJECT_CODE | PROJECT_NAME |
| ---: | --- | ---: | --- | --- |
| 101 | Build finance module | 1 | ERP | ERP - Tenant A |
| 102 | Build sales module | 2 | ERP | ERP - Tenant B |
| 103 | Design customer screen | 1 | CRM | CRM - Tenant A |

Each task is matched only with the project that has the **right tenant and right project code**.

### 4.6. Mistake: joining on only one key component

Incorrect query:

```sql
SELECT t.task_id,
       t.tenant_id AS task_tenant,
       t.project_code,
       p.tenant_id AS project_tenant,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.project_code = t.project_code
ORDER  BY t.task_id, p.tenant_id;
```

For `PROJECT_CODE='ERP'`:

- Task 101 of tenant 1 matches both ERP of tenant 1 and ERP of tenant 2.
- Task 102 of tenant 2 also matches both ERP projects.
- Task 103 of CRM tenant 1 matches one CRM project.

The result has **5 rows instead of 3**. Both ERP tasks are duplicated and may display project information from the wrong tenant.

This is a critical bug in multi-tenant systems: data can leak or mix across customers/tenants. You must join on all identifying components of the key.

### 4.7. Matching column names alone do not define a join key

If two tables have columns with the same name, that does not prove they belong to the same key. Conversely, columns with different names can still represent the same business identifier.

Example:

```sql
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.owner_tenant
       AND p.project_code = t.parent_project_code;
```

This is an illustrative example of joining columns that have different names but share the same meaning in the data model. The query runs only if the table has the corresponding `OWNER_TENANT` and `PARENT_PROJECT_CODE` columns; in the demo table above, the column names are `TENANT_ID` and `PROJECT_CODE`.

## 5. Multi-Column Join Conditions with AND

### 5.1. Each condition describes one component of the relationship

A join condition can contain multiple expressions:

```sql
SELECT ...
FROM   table_a a
INNER JOIN table_b b
        ON a.col_1 = b.col_1
       AND a.col_2 = b.col_2
       AND a.col_3 = b.col_3;
```

All conditions must evaluate to true for the rows to be paired. This is commonly a composite-key join or a join on a set of business attributes.

### 5.2. Example: matching a price table by region and SKU

Suppose product prices vary by region. The SKU code can be the same across multiple regions, so joining by SKU alone is insufficient.

Create the price table:

```sql
CREATE TABLE demo_region_prices (
    region_code VARCHAR2(10) NOT NULL,
    sku         VARCHAR2(30) NOT NULL,
    unit_price  NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_demo_region_prices
        PRIMARY KEY (region_code, sku)
);
```

Create the sales lines table:

```sql
CREATE TABLE demo_sales_lines (
    line_id     NUMBER(10) PRIMARY KEY,
    region_code VARCHAR2(10) NOT NULL,
    sku         VARCHAR2(30) NOT NULL,
    quantity    NUMBER(10) NOT NULL
);
```

Insert data:

```sql
INSERT INTO demo_region_prices VALUES ('NORTH', 'SKU-A', 100);
INSERT INTO demo_region_prices VALUES ('SOUTH', 'SKU-A', 120);
INSERT INTO demo_region_prices VALUES ('NORTH', 'SKU-B', 200);

INSERT INTO demo_sales_lines VALUES (1, 'NORTH', 'SKU-A', 2);
INSERT INTO demo_sales_lines VALUES (2, 'SOUTH', 'SKU-A', 3);
INSERT INTO demo_sales_lines VALUES (3, 'NORTH', 'SKU-B', 1);

COMMIT;
```

Join properly by region and SKU:

```sql
SELECT s.line_id,
       s.region_code,
       s.sku,
       s.quantity,
       p.unit_price,
       s.quantity * p.unit_price AS line_total
FROM   demo_sales_lines s
INNER JOIN demo_region_prices p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
ORDER  BY s.line_id;
```

Result:

| LINE_ID | REGION_CODE | SKU | QUANTITY | UNIT_PRICE | LINE_TOTAL |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | NORTH | SKU-A | 2 | 100 | 200 |
| 2 | SOUTH | SKU-A | 3 | 120 | 360 |
| 3 | NORTH | SKU-B | 1 | 200 | 200 |

If you join only on `SKU`, the NORTH/SKU-A sales line could be wrongly paired with the SOUTH/SKU-A price. The `REGION_CODE` condition is mandatory to determine the right price.

### 5.3. Adding status or validity matching conditions

Some models require matching by key plus a status condition:

```sql
SELECT o.order_id,
       o.customer_id,
       c.customer_name
FROM   orders o
INNER JOIN customers c
        ON c.customer_id = o.customer_id
       AND c.is_active = 'Y';
```

This query returns only orders whose corresponding customer is active. The `IS_ACTIVE` condition is not necessarily part of the primary key, but it is an additional condition determining which rows may participate in the result.

If the goal is to return all orders and display the customer name only when the customer is active, that is a different requirement, usually needing a `LEFT JOIN`. Do not change the join type or move conditions elsewhere without clarifying the requirement.

### 5.4. Multi-column conditions can use operators other than equality

Not every join is an equality join. For example, matching employees against salary ranges or grade tables:

```sql
SELECT e.emp_id,
       e.salary,
       g.grade_name
FROM   employees e
INNER JOIN salary_grades g
        ON e.salary >= g.min_salary
       AND e.salary <  g.max_salary;
```

This is a **range join**. An employee is matched only with the salary grade whose interval contains their salary.

Range conditions must ensure that intervals do not unintentionally overlap. If two rows in the grade table both satisfy the condition, an employee can appear multiple times. In this example, the half-open interval convention `[min_salary, max_salary)` prevents two adjacent grades from both matching a salary right on the boundary, provided the range data is designed contiguously.

## 6. Multi-Table INNER JOINs and Logical Order

### 6.1. Joining along a chain of relationships

For example, employees → departments → companies:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name,
       c.company_name
FROM   employees e
INNER JOIN departments d
        ON d.dept_id = e.dept_id
INNER JOIN companies c
        ON c.company_id = d.company_id
ORDER  BY c.company_name, d.dept_name, e.emp_name;
```

Each join clause adds a table and its corresponding condition. If an employee has no department or a department has no matching company, that row is excluded from the inner join result.

### 6.2. Joining on multiple columns across a multi-table chain

```sql
SELECT l.line_id,
       o.order_no,
       p.product_name,
       w.warehouse_name
FROM   order_lines l
INNER JOIN orders o
        ON o.tenant_id = l.tenant_id
       AND o.order_id = l.order_id
INNER JOIN products p
        ON p.tenant_id = l.tenant_id
       AND p.product_id = l.product_id
INNER JOIN warehouses w
        ON w.tenant_id = l.tenant_id
       AND w.warehouse_id = l.warehouse_id
ORDER  BY o.order_no, l.line_id;
```

Example for a multi-tenant system: each relationship is joined on both tenant and entity ID. The tenant condition must be repeated for each relationship if tenant is part of the identifier or data scope.

Not every system needs a tenant column in every table. Base joins on actual keys and constraints in the schema; do not add tenant conditions if they do not belong to the data model.

### 6.3. Aliases and column names across multiple tables

Best practices:
- Use short but meaningful aliases, such as `e` for employees and `d` for departments.
- Qualify columns with alias prefixes in `SELECT`, `ON`, and `WHERE`.
- Assign clear output names using `AS` when two columns have the same name.
- Keep join conditions close to the table being joined for readability.

Example:

```sql
SELECT o.order_id,
       o.customer_id AS order_customer_id,
       c.customer_id AS matched_customer_id,
       c.customer_name
FROM   orders o
INNER JOIN customers c
        ON c.customer_id = o.customer_id;
```

## 7. NULLs in INNER JOIN Conditions

### 7.1. NULL does not match NULL with equality

Example:

```sql
SELECT a.id,
       a.code,
       b.description
FROM   source_a a
INNER JOIN source_b b
        ON a.code = b.code;
```

If `A.CODE` and `B.CODE` are both NULL, the condition `A.CODE = B.CODE` does not return TRUE; the result is UNKNOWN. Therefore, two NULL rows do not match each other in an inner join using `=`.

### 7.2. What if NULL means "both undetermined"?

Ordinarily, two NULLs should not automatically be treated as the same key. If the business logic truly requires two missing-data states to be considered a match, express the rule explicitly, for example:

```sql
ON (
       a.code = b.code
       OR (a.code IS NULL AND b.code IS NULL)
   )
```

However, this approach pairs every NULL row in table A with every NULL row in table B, potentially generating many unwanted pairs. Before using it, verify whether NULL represents a valid grouping value or merely unknown information.

### 7.3. NVL/COALESCE in join conditions

You may encounter code written as:

```sql
ON NVL(a.code, '#NULL#') = NVL(b.code, '#NULL#')
```

This replaces NULL with a dummy sentinel value. If that dummy value actually appears in the data, non-NULL rows can be erroneously matched; additionally, wrapping columns in functions can affect index usage.

If a NULL-safe comparison is needed, use a controlled expression and choose a sentinel guaranteed by data constraints never to appear, or write `a.code = b.code OR (a.code IS NULL AND b.code IS NULL)`. Do not use arbitrary sentinel values.

## 8. Cardinality: Why Can a Join Produce Many Rows?

### 8.1. One-to-many relationship

With departments and employees:

- One department row can match multiple employee rows.
- The result has one row for each department–employee pair.
- The number of result rows does not necessarily equal the row count of the smaller table.

For example, the Engineering department has two employees, so it appears twice. This is not a bug; it is the exact result of a 1:N relationship.

### 8.2. Many-to-many or non-unique keys

If the join column is not unique on both sides, a single value can match multiple rows from table A and multiple rows from table B.

Suppose code `X` has 2 rows in table A and 3 rows in table B; an inner join on code will produce:

\[
2 \times 3 = 6 \text{ rows}
\]

This combines every pair satisfying the condition. If the result contains more rows than expected, check the uniqueness of the join key and the occurrence counts in each table.

### 8.3. Checking for duplicate keys

Example:

```sql
SELECT tenant_id,
       project_code,
       COUNT(*) AS row_count
FROM   demo_projects
GROUP  BY tenant_id, project_code
HAVING COUNT(*) > 1;
```

If the table already has an enabled composite primary key `(TENANT_ID, PROJECT_CODE)`, this query returns no rows. For staging tables or unconstrained source data, it helps detect duplicate key combinations before joining.

### 8.4. Checking the match count per row

```sql
SELECT t.task_id,
       COUNT(p.project_code) AS matched_projects
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
GROUP  BY t.task_id
HAVING COUNT(p.project_code) <> 1;
```

Because the child table has an enabled composite FK and the parent table has an enabled composite PK, each valid task typically has exactly one matching project. Returning no rows is the expected outcome in this data state. If constraints are disabled/novalidated or data comes from an uncontrolled source, this is a way to verify actual cardinality.

## 9. INNER JOIN and Foreign Keys: Related but Distinct

### 9.1. JOIN does not require a FOREIGN KEY

SQL allows joining two columns even when the database has no FK constraint:

```sql
SELECT a.source_id,
       b.reference_name
FROM   import_rows a
INNER JOIN reference_data b
        ON b.external_code = a.external_code;
```

A join condition only requires comparable expressions. However, having no FK means Oracle does not automatically enforce that every code in the import table exists in the reference table.

### 9.2. FOREIGN KEY does not automatically create a JOIN query

An FK is a **data integrity constraint**. It ensures valid relationships according to the constraint configuration. Query authors must still write `JOIN` when retrieving columns from both tables in a SELECT statement.

For example:
- The FK ensures `EMPLOYEES.DEPT_ID` references a valid department when the constraint is enabled and validated according to its state.
- INNER JOIN uses that relationship to retrieve `DEPT_NAME` alongside the employee.

### 9.3. Joining on the referenced unique key

When joining on a single key or composite key, understand which side is guaranteed unique:
- PK/UK on the parent table ensures each key has at most one corresponding row.
- FK on the child table can repeat across multiple rows.
- If you join on the full parent key, each valid child row matches at most one parent row.

If you use only a non-unique column of the parent table, results can duplicate even when the table has a valid FK on another set of columns.

## 10. USING and NATURAL JOIN in Oracle

### 10.1. USING when join columns share the same name

Oracle supports the `USING` syntax when join columns share the same name:

```sql
SELECT e.emp_id,
       e.emp_name,
       dept_id,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        USING (dept_id);
```

`USING (dept_id)` is equivalent to joining on the identically named `DEPT_ID` column. In the SELECT list, the column specified in `USING` is referenced as a shared column; do not write `e.dept_id` or `d.dept_id` for that USING column.

When joining on a composite key with matching names, list all columns:

```sql
SELECT t.task_id,
       tenant_id,
       project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        USING (tenant_id, project_code);
```

The USING syntax is shorter, though `ON` is usually more flexible when column names differ or additional conditions exist.

### 10.2. When to prefer ON

Use `ON` when:
- The two join columns have different names.
- Multiple combined conditions are needed.
- Validity/status conditions are needed.
- You want to explicitly qualify columns from each table.
- Expressions other than comparing identically named columns are needed.

Example:

```sql
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;
```

### 10.3. Be cautious with NATURAL JOIN

`NATURAL JOIN` automatically uses **all columns with matching names** between two tables as the join condition. This can produce unpredictable results when the schema changes.

For example, two tables both contain `TENANT_ID`, `STATUS`, and `CREATED_AT`. `NATURAL JOIN` will use all identically named columns according to Oracle's rules, not just the key the author had in mind.

Therefore, for application queries and reports that require stability, explicitly write `ON` or `USING` so maintainers see the exact join columns. Do not choose NATURAL JOIN just to save characters in SQL.

## 11. Optimization and Indexes for INNER JOIN

### 11.1. Indexes on join key columns

In the single-key example, the parent table has a PK on `DEPT_ID`, and Oracle typically uses a unique index to support that constraint. The child table may need an index on `DEPT_ID` depending on queries and workload.

For a composite key:

```sql
PRIMARY KEY (tenant_id, project_code)
```

Oracle creates an index mechanism supporting the primary key. Column order in a composite index matters for queries filtering on index prefixes. An index on the child table may be considered:

```sql
CREATE INDEX idx_demo_task_project
ON demo_project_tasks (tenant_id, project_code);
```

This index can support joins and tenant/project queries, but you should not create duplicates of existing indexes or add one solely for a single join query. Check `USER_INDEXES` and `USER_IND_COLUMNS` before changing the schema.

### 11.2. Column order in a composite index

An index:

```sql
(tenant_id, project_code)
```

typically suits conditions like:
- `tenant_id = :tenant_id`;
- `tenant_id = :tenant_id AND project_code = :project_code`.

A query filtering only on `project_code` may not utilize this index as effectively as a query starting with the leading column, depending on the optimizer and index structure. Do not reorder columns arbitrarily; base decisions on actual queries and data distribution.

### 11.3. The optimizer can change join execution order

The order in which tables are written in SQL is not necessarily the order in which Oracle accesses them. The cost-based optimizer evaluates:
- Table/column/index statistics.
- Expected row counts after each condition.
- Selectivity and data distribution.
- Available access paths.
- Join cost and memory.

Therefore, do not force join order merely based on how the SQL statement reads. Inspect the execution plan and actual metrics when tuning is needed.

### 11.4. Viewing the execution plan

Example:

```sql
EXPLAIN PLAN FOR
SELECT t.task_id,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan. The actual plan may differ due to bind values, statistics, data, and environment. For production workloads, use tools/plans from executed cursors and runtime metrics per granted privileges.

Join methods such as nested loops, hash join, or sort merge join are chosen by the optimizer based on cost. No single join method is always best for every data size and distribution.

### 11.5. Selecting explicit columns instead of SELECT *

When joining multiple tables, avoid `SELECT *` if all columns are not needed:
- Reduces data transferred to the client.
- Avoids duplicate column names in the output.
- Clarifies which table supplies each piece of data.
- Limits application dependency on columns added later.

Example:

```sql
SELECT t.task_id,
       t.task_name,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code;
```

## 12. Common Mistakes When Writing INNER JOIN

### 12.1. ORA-00918: column ambiguously defined

**Cause:** selecting a column with the same name from multiple tables without qualifying it with an alias.

Ambiguous:

```sql
SELECT dept_id
FROM   demo_employees e
JOIN   demo_departments d
       ON d.dept_id = e.dept_id;
```

Explicit:

```sql
SELECT e.dept_id AS employee_dept_id,
       d.dept_id AS department_id
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id;
```

### 12.2. More rows returned than expected

Common causes:
- Missing a component of a composite key in the join.
- The column chosen as a key is not unique.
- Source data contains duplicates.
- Joining multiple 1:N tables causes row multiplication.

How to resolve:
1. Identify the desired result grain.
2. Check PK/UK and the join columns.
3. Count rows per key on both sides.
4. Add all necessary join conditions.
5. Aggregate before joining if the target report is at a different granularity.

Do not mechanically add `DISTINCT` to mask a join bug. DISTINCT can eliminate completely identical output rows, but it cannot restore the true relationship if other columns differ or aggregates have already been multiplied.

### 12.3. Missing rows in the result

Causes:
- Using INNER JOIN when some rows have no matching record.
- One component of a composite key does not match.
- A join column contains NULL.
- Extra conditions in ON are too restrictive.
- A WHERE clause filters out rows after the join.
- Mismatched data types or differences in trailing spaces/collation.

If the requirement is to keep unmatched rows as well, evaluate `LEFT JOIN` instead of trying to force an inner join to preserve them.

### 12.4. Joining on only one column of a composite key

Incorrect example:

```sql
ON p.project_code = t.project_code
```

If the true key is `(TENANT_ID, PROJECT_CODE)`, the condition must be:

```sql
ON p.tenant_id = t.tenant_id
AND p.project_code = t.project_code
```

Omitting tenant can leak or mix data across customer scopes.

### 12.5. Using mismatched data types in join conditions

For example, one table uses `NUMBER` while the other uses `VARCHAR2` to store an ID. Oracle may perform implicit conversion or raise errors when encountering strings that cannot convert to numbers.

Standardize data types on both sides for the same attribute, or perform controlled conversion in the proper place. Avoid wrapping large-table columns in conversion functions in join conditions without evaluating performance impact.

### 12.6. Placing conditions in the wrong clause

With INNER JOIN, some filter conditions can move between ON and WHERE without changing the result. However, when a query is changed to an OUTER JOIN, a condition in WHERE can filter out null-extended rows and make the result behave like an inner join.

Keep relationship conditions clearly in ON and general filters in WHERE to avoid unintended semantic shifts when extending queries.

### 12.7. Joining columns with the same name but different meanings

For example, both tables have `STATUS`, where one is order status and the other is payment status. Never join `a.status = b.status` just because the column names match. Join conditions must reflect business keys/relationships, not coincidental name matches.

## 13. Workflow for Building an INNER JOIN Query

Before writing SQL, determine:

1. **Base table:** which entity should each result row represent?
2. **Additional tables needed:** what information resides in other tables?
3. **Join key:** single key or composite key?
4. **Uniqueness:** does the parent key have a PK/UK? Could it match multiple rows?
5. **NULLs:** can join columns be NULL, and what does NULL mean?
6. **Additional conditions:** are tenant, status, effective period, or region conditions required?
7. **Cardinality:** is the expected result one-to-one, one-to-many, or many-to-many?
8. **Join type:** do you want only matched pairs (INNER) or do you need to preserve unmatched rows (OUTER)?
9. **Output columns:** explicitly pick columns and aliases.
10. **Performance:** are indexes, statistics, and the execution plan appropriate?

Single-key template:

```sql
SELECT a.id,
       a.description,
       b.display_name
FROM   table_a a
INNER JOIN table_b b
        ON b.id = a.b_id
WHERE  a.status = 'ACTIVE';
```

Composite-key template:

```sql
SELECT c.child_id,
       p.parent_name
FROM   child_table c
INNER JOIN parent_table p
        ON p.tenant_id = c.tenant_id
       AND p.parent_code = c.parent_code;
```

Multi-column condition template:

```sql
SELECT s.line_id,
       p.unit_price
FROM   sales_lines s
INNER JOIN price_list p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
       AND p.currency_code = s.currency_code;
```

These examples are syntax skeletons; table and column names must match the actual schema.

## 14. Comprehensive Practice Exercises

The tables `DEMO_DEPARTMENTS`, `DEMO_EMPLOYEES`, `DEMO_PROJECTS`, `DEMO_PROJECT_TASKS`, `DEMO_REGION_PRICES`, and `DEMO_SALES_LINES` were created in the earlier sections. Run these in your practice schema.

### Exercise 1 — Single-key INNER JOIN

Retrieve employee ID, employee name, and department name:

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
ORDER  BY e.emp_id;
```

**Expected:** three rows for employees An, Binh, and Chi. Dung has no department and therefore does not appear.

### Exercise 2 — Filtering on the parent table

Retrieve only employees in the Sales department:

```sql
SELECT e.emp_id, e.emp_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
WHERE  d.dept_name = 'Sales';
```

**Expected:** employee 103.

### Exercise 3 — Composite-key INNER JOIN

```sql
SELECT t.task_id,
       t.tenant_id,
       t.project_code,
       p.project_name
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.tenant_id = t.tenant_id
       AND p.project_code = t.project_code
ORDER  BY t.task_id;
```

**Expected:** three tasks, each matched to the right project within its tenant.

### Exercise 4 — Observing the bug from omitting one key component

Run intentionally in the demo environment:

```sql
SELECT t.task_id,
       t.tenant_id AS task_tenant,
       p.tenant_id AS project_tenant,
       t.project_code
FROM   demo_project_tasks t
INNER JOIN demo_projects p
        ON p.project_code = t.project_code
ORDER  BY t.task_id, p.tenant_id;
```

**Expected:** five rows, in which the two ERP tasks are paired with both tenants. Compare with Exercise 3 to observe the fan-out.

### Exercise 5 — Joining on two business conditions

```sql
SELECT s.line_id,
       s.region_code,
       s.sku,
       s.quantity,
       p.unit_price,
       s.quantity * p.unit_price AS line_total
FROM   demo_sales_lines s
INNER JOIN demo_region_prices p
        ON p.region_code = s.region_code
       AND p.sku = s.sku
ORDER  BY s.line_id;
```

**Expected:** three rows with prices matching each region.

### Exercise 6 — Counting tasks per project

```sql
SELECT p.tenant_id,
       p.project_code,
       p.project_name,
       COUNT(t.task_id) AS task_count
FROM   demo_projects p
INNER JOIN demo_project_tasks t
        ON t.tenant_id = p.tenant_id
       AND t.project_code = p.project_code
GROUP  BY p.tenant_id, p.project_code, p.project_name
ORDER  BY p.tenant_id, p.project_code;
```

**Expected:** each of the three projects has one task. If you also want to display projects with zero tasks, consider LEFT JOIN.

### Exercise 7 — Detecting duplicate keys in source data

```sql
SELECT region_code,
       sku,
       COUNT(*) AS duplicate_count
FROM   demo_region_prices
GROUP  BY region_code, sku
HAVING COUNT(*) > 1;
```

**Expected:** no rows because the region/SKU combination is protected by the composite primary key.

### Exercise 8 — Distinguishing JOIN conditions from filters

```sql
SELECT e.emp_id,
       e.emp_name,
       d.dept_name
FROM   demo_employees e
INNER JOIN demo_departments d
        ON d.dept_id = e.dept_id
       AND d.dept_name = 'Engineering'
ORDER  BY e.emp_id;
```

Rewrite by moving the department name condition to `WHERE`. With this inner join, the result must be equivalent.

### Exercise 9 — Using USING with identically named columns

```sql
SELECT emp_id,
       emp_name,
       dept_id,
       dept_name
FROM   demo_employees
INNER JOIN demo_departments
        USING (dept_id)
ORDER  BY emp_id;
```

**Expected:** the same rows as Exercise 1. Note that the `DEPT_ID` column in `USING` is referenced as a shared column.

### Exercise 10 — Inspecting index metadata

```sql
SELECT i.index_name,
       i.table_name,
       c.column_name,
       c.column_position
FROM   user_indexes i
JOIN   user_ind_columns c
       ON c.index_name = i.index_name
      AND c.table_name = i.table_name
WHERE  i.table_name IN (
         'DEMO_PROJECTS',
         'DEMO_PROJECT_TASKS',
         'DEMO_REGION_PRICES',
         'DEMO_SALES_LINES'
       )
ORDER  BY i.table_name, i.index_name, c.column_position;
```

**Objective:** observe indexes created to support PKs and user-created indexes. Do not assume that every FK automatically generates an index on the child table.

## 15. Self-Check Questions

1. Which rows from two tables does `INNER JOIN` return?
2. Why does an employee with `DEPT_ID=NULL` not appear in an inner join using `=`?
3. How does a single key differ from a composite key?
4. If the parent key is `(TENANT_ID, PROJECT_CODE)`, how many join conditions are required to match the key properly?
5. What can happen if you join only on `PROJECT_CODE` when project codes repeat across tenants?
6. What does `AND` in the ON clause mean when joining on multiple columns?
7. A department has three employees. After an inner join, how many rows can that department appear in?
8. Does INNER JOIN require tables to declare a FOREIGN KEY?
9. Does a FOREIGN KEY automatically generate a SELECT JOIN query?
10. Why should table aliases be used in multi-table queries?
11. How does `USING (dept_id)` differ syntactically from `ON e.dept_id = d.dept_id`?
12. Why should you be cautious with NATURAL JOIN?
13. If both join columns are NULL, does equality make them match?
14. A join returns more rows than expected. What should you check before adding DISTINCT?
15. Why can `COUNT(*)` after a join be greater than the row count of the parent table?
16. Are filter conditions in ON and WHERE always equivalent?
17. When joining a price table by region and SKU, why can joining by SKU alone be wrong?
18. Is Oracle forced to execute joins in the exact table order written in FROM?
19. Which types of conditions are well supported by a composite index `(TENANT_ID, PROJECT_CODE)`?
20. If you need to keep rows that have no matching record, should you continue using INNER JOIN?

**Answer hints:**

1. Only combinations of rows where the join condition evaluates to TRUE.
2. Comparing with NULL yields UNKNOWN, not TRUE.
3. A single key has one column; a composite key has two or more columns forming a single identifier.
4. Both columns must be matched.
5. It can cross-match tenants and duplicate rows.
6. All conditions must be true for two rows to be paired.
7. Three rows, one per employee pair in the result.
8. No; JOIN is query syntax and can join on conditions even without an FK.
9. No; an FK is a constraint, and queries must still write JOIN explicitly.
10. To avoid column name ambiguity and clarify data sources.
11. USING requires identically named columns; ON allows expressions and different column names.
12. It automatically uses all identically named columns, so schema changes can alter join conditions.
13. No; NULL = NULL evaluates to UNKNOWN.
14. Check join keys, uniqueness, duplicates, and cardinality.
15. Because one parent row can match multiple child rows.
16. No; with outer joins, condition placement can change the result.
17. The same SKU can have different prices across regions.
18. No; the optimizer can choose a different execution order.
19. Conditions with tenant_id and optionally project_code; the tenant_id prefix is also often helpful.
20. No; consider LEFT JOIN depending on which unmatched rows must be preserved.

## 16. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT syntax, join clause, ON, and USING.
- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): join types and combining tables.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): tables, keys, relationships, and data integrity.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): optimizer, access paths, and join methods.
- [Oracle Database Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/): index metadata, constraints, and dictionary views.

When writing an INNER JOIN, identify **the right keys and all components of those keys** before adding filter conditions. For composite keys, every required component must be matched accordingly; for multi-column conditions, use `AND` to express simultaneous relationships. Then verify uniqueness and cardinality to understand why the result has its row count. Using aliases, selecting explicit columns, and checking the execution plan when tuning will make Oracle queries easier to understand and more reliable.
