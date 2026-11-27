# LEVEL, PRIOR, CONNECT_BY_ROOT, and SYS_CONNECT_BY_PATH

In many systems, data has a hierarchical structure: employees report to managers, categories have parent and child groups, accounts have parent accounts, or a product has multiple classification levels. Data is commonly stored in **a single table with a self-referencing key**: each row stores its own ID and its parent row's ID.

Oracle Database supports **hierarchical queries** to traverse parent-child relationships directly in SQL. Four essential components are:

- `LEVEL`: indicates the depth of a row in the result tree.
- `PRIOR`: specifies the expression taken from the parent row at each traversal step.
- `CONNECT_BY_ROOT`: retrieves a value from the root row and displays it on descendant rows.
- `SYS_CONNECT_BY_PATH`: builds a path string from the root to the current row.

This lesson uses an employee–manager model to explain how Oracle constructs the tree, how to choose traversal direction, how to read depth and paths, as well as how to handle multiple roots, cycles, filtering, and display ordering.

## 1. Hierarchical Relationships Stored in a Single Table

Suppose the `EMPLOYEES` table has the following structure:

| Column | Meaning |
|---|---|
| `EMPLOYEE_ID` | Employee ID, primary key |
| `EMPLOYEE_NAME` | Employee name |
| `MANAGER_ID` | Manager ID, references `EMPLOYEE_ID` in the same table |
| `DEPARTMENT_ID` | Department ID |
| `STATUS` | Employee status |

The parent-child relationship is represented as follows:

~~~text
EMPLOYEE_ID = 100  (CEO, MANAGER_ID = NULL)
    |
    +-- EMPLOYEE_ID = 110  (VP, MANAGER_ID = 100)
    |       |
    |       +-- EMPLOYEE_ID = 111  (Manager, MANAGER_ID = 110)
    |       |       |
    |       |       +-- EMPLOYEE_ID = 112  (Staff, MANAGER_ID = 111)
    |       |
    |       +-- EMPLOYEE_ID = 113  (Staff, MANAGER_ID = 110)
    |
    +-- EMPLOYEE_ID = 120  (VP, MANAGER_ID = 100)
            |
            +-- EMPLOYEE_ID = 121  (Manager, MANAGER_ID = 120)
~~~

In this model, a row is a **child** if its `MANAGER_ID` equals the parent row's `EMPLOYEE_ID`. The `MANAGER_ID` column can be NULL in the root row because the CEO has no manager within the scope of the tree being examined.

This relationship is commonly called a *self-referencing relationship*. It does not have to be strictly a single tree: one table can hold multiple roots, multiple branches, or erroneous data that forms cycles.

## 2. Preparing the Practice Table

In a practice schema permitted to create tables, run the following DDL once:

~~~sql
CREATE TABLE lab_employees (
    employee_id    NUMBER(6) PRIMARY KEY,
    employee_name  VARCHAR2(60 CHAR) NOT NULL,
    manager_id     NUMBER(6),
    department_id  NUMBER(4),
    status         VARCHAR2(12 CHAR) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT fk_lab_emp_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id)
);
~~~

The self-referencing foreign key prevents `MANAGER_ID` values from pointing to non-existent employees. It does not by itself prevent cycles such as A managing B and B managing A; avoiding cycles requires additional business rules or validation logic.

Load sample data:

~~~sql
INSERT ALL
    INTO lab_employees VALUES (100, 'An - CEO',       NULL, 10, 'ACTIVE')
    INTO lab_employees VALUES (110, 'Binh - VP',      100, 10, 'ACTIVE')
    INTO lab_employees VALUES (120, 'Chi - VP',       100, 20, 'ACTIVE')
    INTO lab_employees VALUES (111, 'Dung - Manager', 110, 10, 'ACTIVE')
    INTO lab_employees VALUES (113, 'Giang - Staff',  110, 10, 'ACTIVE')
    INTO lab_employees VALUES (121, 'Hanh - Manager',120, 20, 'ACTIVE')
    INTO lab_employees VALUES (112, 'Khanh - Staff',  111, 10, 'ACTIVE')
    INTO lab_employees VALUES (122, 'Lan - Staff',   121, 20, 'INACTIVE')
    INTO lab_employees VALUES (200, 'Minh - Director',NULL, 30, 'ACTIVE')
    INTO lab_employees VALUES (210, 'Nam - Manager',  200, 30, 'ACTIVE')
SELECT 1 FROM dual;

COMMIT;
~~~

The two rows `100` and `200` are two independent roots. Tree `100` belongs to departments 10/20; tree `200` belongs to department 30. A hierarchical query can return a **forest** consisting of multiple roots.

Inspect the source data:

~~~sql
SELECT employee_id, employee_name, manager_id,
       department_id, status
FROM lab_employees
ORDER BY employee_id;
~~~

## 3. Hierarchical Query Syntax Framework

Common pattern:

~~~sql
SELECT select_list
FROM table_name
START WITH root_condition
CONNECT BY [NOCYCLE] parent_child_condition
ORDER SIBLINGS BY sibling_sort_expression;
~~~

Components:

| Component | Role |
|---|---|
| `START WITH` | Selects the starting rows, i.e., the roots of each traversed branch |
| `CONNECT BY` | Defines how the current row connects to the parent/child row at the next step |
| `PRIOR` | Specifies the expression taken from the parent row in the hierarchical condition |
| `NOCYCLE` | Allows the query to stop a branch when a cycle is detected instead of raising a cycle error |
| `LEVEL` | Pseudocolumn giving the row's depth in the result tree |
| `ORDER SIBLINGS BY` | Sorts rows sharing the same parent while preserving hierarchical order |

First example:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

The result starts from employees without managers and moves down through subordinate tiers. `START WITH` identifies the roots; `CONNECT BY` finds rows whose `MANAGER_ID` equals the previous parent row's `EMPLOYEE_ID`.

If `START WITH` is omitted, Oracle treats all qualifying rows in the source as starting points of the hierarchical query. In most parent-child tree problems, you should specify the roots explicitly to avoid duplicate branches or unintended output.

## 4. LEVEL: Depth of a Row in the Tree

`LEVEL` is an Oracle pseudocolumn used only in hierarchical queries:

- The root starts at `LEVEL = 1`.
- Direct children of the root are at `LEVEL = 2`.
- Grandchildren are at `LEVEL = 3`.
- Each downward edge increases LEVEL by 1.

Example:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Expected result:

| TREE_LEVEL | EMPLOYEE_ID | EMPLOYEE_NAME |
|---:|---:|---|
| 1 | 100 | An - CEO |
| 2 | 110 | Binh - VP |
| 3 | 111 | Dung - Manager |
| 4 | 112 | Khanh - Staff |
| 3 | 113 | Giang - Staff |
| 2 | 120 | Chi - VP |
| 3 | 121 | Hanh - Manager |
| 4 | 122 | Lan - Staff |

The order of siblings at the same level depends on sorting. `ORDER SIBLINGS BY employee_id` ensures siblings are sorted by ID while keeping parents before children.

### 4.1 Retrieving only a specific number of levels

If only the root and two child levels are needed:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= 3
ORDER SIBLINGS BY employee_id;
~~~

The depth condition in `CONNECT BY` prevents Oracle from expanding branches past level 3. You can use `WHERE LEVEL <= 3` to filter result rows by depth; when you need to limit **tree expansion**, placing the appropriate condition in `CONNECT BY` makes the intent clearer.

### 4.2 LEVEL is not a column stored in the table

`TREE_LEVEL` in the result does not come from a physical column. Oracle computes it while traversing the tree. Therefore:

- You do not need to add a `LEVEL` column to the table.
- The same physical row can appear at different depths if multiple valid paths reach it.
- Changing the root or the `CONNECT BY` condition can change LEVEL values even when table data does not change.

## 5. PRIOR: Identifying the Parent Row and Child Row

`PRIOR` is a unary operator used in the `CONNECT BY` condition. The expression immediately following `PRIOR` is evaluated on the **parent row from the previous step**; the rest is evaluated on the candidate current row (the child row in top-down traversal).

### 5.1 Traversing from manager down to employee

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 100
CONNECT BY PRIOR employee_id = manager_id;
~~~

Reading the condition:

~~~sql
PRIOR employee_id = manager_id
~~~

- `PRIOR employee_id`: employee ID of the parent row.
- `manager_id`: manager ID of the candidate row.
- The candidate row is a child if its `manager_id` equals the parent row's `employee_id`.

Thus the tree traverses in this direction:

~~~text
100 -> 110 -> 111 -> 112
100 -> 110 -> 113
100 -> 120 -> 121 -> 122
~~~

This is the common direction when displaying an org chart from the CEO down to staff.

### 5.2 Traversing from employee up to manager

If you start at employee `112` and want to trace back up the management chain:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 112
CONNECT BY PRIOR manager_id = employee_id;
~~~

Reading the condition in reverse:

- `PRIOR manager_id`: manager ID of the current row from the previous step.
- `employee_id`: employee ID of the next candidate row.
- Oracle finds the row whose `EMPLOYEE_ID` equals the previous row's `MANAGER_ID`, moving up to the parent tier.

The resulting path starts at employee 112, then goes to 111, 110, and 100. `LEVEL = 1` here is employee 112 because that row is the root of **the running query**, even though it is not the CEO in the company-wide org chart.

### 5.3 PRIOR placement determines traversal direction

| Condition | How to read | Common direction |
|---|---|---|
| `PRIOR employee_id = manager_id` | Parent ID equals child's MANAGER_ID | Manager down to employee |
| `PRIOR manager_id = employee_id` | Current row's MANAGER_ID equals next parent row's ID | Employee up to manager |

You can place `PRIOR` on the right-hand side:

~~~sql
CONNECT BY manager_id = PRIOR employee_id
~~~

This is equivalent in meaning to `CONNECT BY PRIOR employee_id = manager_id`. Side placement does not change the relationship as long as both sides remain matched properly.

### 5.4 PRIOR can apply to expressions

`PRIOR` is not limited to a single column:

~~~sql
CONNECT BY PRIOR department_id = department_id
       AND PRIOR employee_id = manager_id
~~~

However, when joining on multiple attributes, ensure the relationship truly identifies parent-child accurately. If you compare only `DEPARTMENT_ID`, employees in the same department would cross-connect into many invalid branches. In an employee–manager model, `EMPLOYEE_ID` and `MANAGER_ID` form the primary identifying relationship.

## 6. START WITH: Selecting the Tree Roots

`START WITH` identifies the starting row or set of rows. Each qualifying row can initiate its own tree.

### 6.1 Starting from all employees without a manager

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

This query creates a forest consisting of trees rooted at 100 and 200. This is typically how you retrieve the entire org chart when data guarantees every branch connects to a root employee.

### 6.2 Starting from a specific employee

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH employee_id = 110
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

The result contains only VP 110's branch and lower tiers. Employee 120 and their tree are not traversed because they are not descendants of root 110.

### 6.3 Multiple roots based on conditions

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       department_id
FROM lab_employees
START WITH manager_id IS NULL
       AND status = 'ACTIVE'
CONNECT BY PRIOR employee_id = manager_id;
~~~

The `START WITH` clause can contain multiple conditions. In this example, only ACTIVE employees without managers become roots. If a branch has an INACTIVE root, that branch is not initialized from that root row.

## 7. CONNECT_BY_ROOT: Retrieving the Root Value for All Descendants

`CONNECT_BY_ROOT` is a unary operator in hierarchical queries. It returns the value of an expression at the **root row of the current path**, regardless of which level the result row is at.

Example:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       CONNECT_BY_ROOT employee_id AS root_employee_id,
       CONNECT_BY_ROOT employee_name AS root_employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Sample output:

| LEVEL | EMPLOYEE_ID | EMPLOYEE_NAME | ROOT_EMPLOYEE_ID | ROOT_EMPLOYEE_NAME |
|---:|---:|---|---:|---|
| 1 | 100 | An - CEO | 100 | An - CEO |
| 2 | 110 | Binh - VP | 100 | An - CEO |
| 3 | 111 | Dung - Manager | 100 | An - CEO |
| 4 | 112 | Khanh - Staff | 100 | An - CEO |
| 3 | 113 | Giang - Staff | 100 | An - CEO |
| 2 | 120 | Chi - VP | 100 | An - CEO |
| 3 | 121 | Hanh - Manager | 100 | An - CEO |
| 4 | 122 | Lan - Staff | 100 | An - CEO |
| 1 | 200 | Minh - Director | 200 | Minh - Director |
| 2 | 210 | Nam - Manager | 200 | Minh - Director |

`ROOT_EMPLOYEE_ID` tells you which root tree each row belongs to. This is very useful when:

- A query returns multiple trees.
- You need to aggregate by top-level leader.
- You need to identify the origin of each descendant row.
- You need to display the top-level unit name beside each employee.

### 7.1 CONNECT_BY_ROOT vs. PRIOR

These two components serve different purposes:

| Component | Value retrieved | Scope |
|---|---|---|
| `PRIOR employee_id` in CONNECT BY | Column of the parent row at the current traversal step | One parent-child step |
| `CONNECT_BY_ROOT employee_id` | Column of the root row of the current path | The entire path from root to the row being evaluated |

`PRIOR` answers "who is the immediate parent row?". `CONNECT_BY_ROOT` answers "which root did this path start from?".

### 7.2 Using CONNECT_BY_ROOT with other attributes

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       CONNECT_BY_ROOT department_id AS root_department_id
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

In the example, each row carries the root's `DEPARTMENT_ID`. Keep in mind this is the **value at the root row**, not the current row's department value. If employees change departments while the reporting hierarchy has not changed, the two values may differ.

`CONNECT_BY_ROOT` cannot be used in `START WITH` or `CONNECT BY` conditions. It is an operator for retrieving root values in the expression list of a hierarchical query, not an operator for defining parent-child relationships.

## 8. SYS_CONNECT_BY_PATH: Building a Path from the Root to the Current Row

`SYS_CONNECT_BY_PATH(column, separator)` constructs a string representing the path from the root row to the row being evaluated. The first argument is the character expression to concatenate; the second argument is the separator.

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS employee_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_id;
~~~

Sample paths:

~~~text
 / An - CEO
 / An - CEO / Binh - VP
 / An - CEO / Binh - VP / Dung - Manager
 / An - CEO / Binh - VP / Dung - Manager / Khanh - Staff
 / An - CEO / Chi - VP / Hanh - Manager / Lan - Staff
~~~

The path contains values from the root to the current node, following the query traversal direction. The separator is placed between levels; on the root row, the path begins with the separator followed by the root value.

### 8.1 Paths using IDs instead of names

Names can be duplicated or change over time. If you want a more stable path:

~~~sql
SELECT employee_id,
       SYS_CONNECT_BY_PATH(TO_CHAR(employee_id), '/') AS id_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Example:

~~~text
/100
/100/110
/100/110/111
/100/110/111/112
~~~

`TO_CHAR` converts the numeric ID to a character expression to build the path. If you need to store or compare paths, define a stable ID formatting rule and avoid NLS-dependent number formatting.

### 8.2 Combining LEVEL, root, and path

A common query in tree reports:

~~~sql
SELECT LEVEL AS tree_level,
       employee_id,
       employee_name,
       manager_id,
       CONNECT_BY_ROOT employee_id AS root_id,
       SYS_CONNECT_BY_PATH(
           employee_name,
           ' > '
       ) AS hierarchy_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

The three additional columns answer three questions:

- `TREE_LEVEL`: what level is it at?
- `ROOT_ID`: which employee did this tree start from?
- `HIERARCHY_PATH`: who is on the path from the root to the current employee?

This is a useful combination for hierarchical reports, catalog exports, breadcrumb displays, or inspecting a node's path.

### 8.3 Path is VARCHAR2, not an unlimited CLOB

`SYS_CONNECT_BY_PATH` returns a string of type `VARCHAR2` in the corresponding character set. Very deep paths or very long node names can exceed the SQL string expression limit of the environment, depending on `MAX_STRING_SIZE` and the character set. Do not treat the path as an unlimited text field.

If the path is for display, limit depth/length and decide how to handle oversized paths. If you need to store extremely large path contents, design an appropriate alternative mechanism; do not assume this function automatically returns a `CLOB`.

### 8.4 The separator can appear in the data

If an employee name contains `' / '`, the path string can become ambiguous when parsed back. You can choose a delimiter unlikely to appear, normalize/escape values before concatenation, or store paths in a separate structure. `SYS_CONNECT_BY_PATH` is a string-building tool for readability; it does not automatically encode delimiters into a safe serialization format.

## 9. ORDER SIBLINGS BY: Sorting Siblings Without Breaking the Tree

In a hierarchical query, if you need to sort rows sharing the same parent, use:

~~~sql
ORDER SIBLINGS BY employee_name
~~~

Example:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

Oracle sorts sibling rows under the same parent by name while preserving the parent-before-child structure. Do not use a plain `ORDER BY employee_name` when the goal is to keep hierarchical order; a final `ORDER BY` can re-sort the entire result set and make the tree hard to read.

You can sort by multiple criteria:

~~~sql
ORDER SIBLINGS BY status, employee_name
~~~

When you need to prioritize ACTIVE before INACTIVE within the same branch, you can use an expression:

~~~sql
ORDER SIBLINGS BY
    CASE WHEN status = 'ACTIVE' THEN 1 ELSE 2 END,
    employee_name
~~~

Sibling ordering affects display order only; it does not change parent-child relationships or `LEVEL` values.

## 10. Filtering Data in a Hierarchical Query

Where a filter condition is placed affects how the tree is expanded.

### 10.1 WHERE filters result rows

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       status
FROM lab_employees
WHERE status = 'ACTIVE'
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

The `WHERE` condition filters result rows after Oracle has determined the hierarchical relationships. An INACTIVE row may be excluded from the output, yet its descendants can still be found via parent-child relationships if those descendants themselves satisfy the `WHERE` condition.

For example, employee 121 is ACTIVE while employee 122 is INACTIVE: with `WHERE status = 'ACTIVE'`, 122 is hidden, while ACTIVE rows beneath a hidden node can still appear in the tree structure.

### 10.2 CONNECT BY restricts branch expansion

If you want to traverse only through ACTIVE employees:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       status
FROM lab_employees
START WITH manager_id IS NULL
       AND status = 'ACTIVE'
CONNECT BY PRIOR employee_id = manager_id
       AND status = 'ACTIVE';
~~~

The status condition in `CONNECT BY` restricts candidate rows connected into the tree. If an INACTIVE employee sits in the middle of a branch, Oracle does not expand through that row under this condition; descendants below may not be traversed.

| Condition placement | Main effect |
|---|---|
| `START WITH` | Selects which nodes become roots |
| `CONNECT BY` | Determines which relationships are expanded and which child nodes are connected into the tree |
| `WHERE` | Filters rows in the result after the tree is built; does not by default delete all descendants of a filtered row |

This is an important distinction when writing org reports: "display only ACTIVE employees" differs from "traverse only through branches where every tier is ACTIVE".

### 10.3 Filtering by LEVEL

You can retrieve only levels from 2 onward:

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name
FROM lab_employees
WHERE LEVEL >= 2
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

The roots are filtered out of the output, while child rows can still appear. If you want to limit traversal depth, put a condition in `CONNECT BY` rather than only filtering the final rows.

## 11. NOCYCLE and Detecting Cycles

Valid hierarchical data normally has no cycles: an employee cannot be their own ancestor. However, data can become corrupted due to manager updates, imports, or sync jobs. For example:

~~~text
EMPLOYEE 300 -> MANAGER 310
EMPLOYEE 310 -> MANAGER 300
~~~

These two rows form a cycle. If a query follows the parent-child relationship without handling it, Oracle may raise:

~~~text
ORA-01436: CONNECT BY loop in user data
~~~

### 11.1 Using NOCYCLE to avoid loop errors

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

`NOCYCLE` tells Oracle not to continue into a loop that creates a cycle. The query can return results instead of failing with a loop error; however, **it does not mean the data has been fixed**. The cycle remains a data quality issue requiring investigation.

### 11.2 CONNECT_BY_ISCYCLE identifies loop-causing rows

In a hierarchical query with `NOCYCLE`, the `CONNECT_BY_ISCYCLE` pseudocolumn returns:

- `1` if the current row has a child row that is one of its ancestors, i.e., an edge creating a cycle is detected during traversal.
- `0` otherwise.

Example:

~~~sql
SELECT LEVEL,
       employee_id,
       manager_id,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_employees
START WITH employee_id = 300
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

This example is meaningful only when the data actually has a cycle reachable from root 300. If row 300 does not exist or there is no cyclic path, the output will not demonstrate a cycle. In a dedicated practice environment, you can create a test table without a foreign key to simulate corrupted data; do not intentionally break relationships in production tables.

### 11.3 NOCYCLE does not replace data validation

After finding a cycle, you should:

1. Identify the node IDs participating in the cycle.
2. Identify the source of the bad data: manual update, import, or sync.
3. Choose the business rule to repair the parent-child relationship.
4. Re-check the entire tree, not just a single root.

`NOCYCLE` is useful for diagnosing or shielding queries from loop errors, but quietly relying on it in reports allows bad organizational data to persist.

## 12. Multiple Roots and a Node Appearing Multiple Times

With the sample data, the two roots 100 and 200 produce two trees. `CONNECT_BY_ROOT` distinguishes their origins:

~~~sql
SELECT CONNECT_BY_ROOT employee_id AS root_id,
       LEVEL,
       employee_id,
       employee_name
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

In a single-parent model, each employee usually belongs to one tree. However, a general hierarchical query can produce **multiple paths to the same row** if a composite relationship allows a node to have multiple parents or the `CONNECT BY` condition does not define a unique relationship. In that case:

- The same `EMPLOYEE_ID` can appear in multiple rows.
- Each occurrence can have a different `LEVEL`.
- `CONNECT_BY_ROOT` and `SYS_CONNECT_BY_PATH` can differ along each path.

Do not assume a hierarchical query always returns a unique row per primary key. It returns **occurrences per traversed path**. If the data is truly a multi-parent graph, clarify whether you want to list all paths or only one path.

## 13. Combining CONNECT_BY_ROOT and SYS_CONNECT_BY_PATH in Reports

A complete query:

~~~sql
SELECT CONNECT_BY_ROOT employee_id AS root_id,
       CONNECT_BY_ROOT employee_name AS root_name,
       LEVEL AS depth,
       employee_id,
       manager_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS full_path
FROM lab_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY employee_name;
~~~

The output provides:

| Column | Purpose |
|---|---|
| `ROOT_ID` | Identifies the root tree |
| `ROOT_NAME` | Name of the head of the tree |
| `DEPTH` | Tier of the node in the tree |
| `EMPLOYEE_ID` | Current node |
| `MANAGER_ID` | Parent relationship stored in the table |
| `FULL_PATH` | Path string from root to the current node |

### 13.1 Aggregating employee counts by root

You can wrap a hierarchical query in a CTE and then aggregate:

~~~sql
WITH employee_tree AS (
    SELECT CONNECT_BY_ROOT employee_id AS root_id,
           employee_id,
           LEVEL AS depth
    FROM lab_employees
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
)
SELECT root_id,
       COUNT(*) AS nodes_in_tree,
       MAX(depth) AS maximum_depth
FROM employee_tree
GROUP BY root_id
ORDER BY root_id;
~~~

The result counts node occurrences in each tree and the maximum depth. In a single-parent model without cycles, `COUNT(*)` matches the number of employees in the tree. If join conditions produce multiple paths, the same node can be counted multiple times; in that case you must decide whether to count **paths** or **distinct nodes**.

If you need to count distinct nodes per root:

~~~sql
COUNT(DISTINCT employee_id)
~~~

but use this only when the business definition is truly the number of distinct employees belonging to that tree.

### 13.2 Finding all employees under a leader

~~~sql
SELECT LEVEL,
       employee_id,
       employee_name,
       CONNECT_BY_ROOT employee_name AS selected_root,
       SYS_CONNECT_BY_PATH(employee_id, '/') AS id_path
FROM lab_employees
START WITH employee_id = :manager_id
CONNECT BY PRIOR employee_id = manager_id;
~~~

Binding `:manager_id` allows the application to choose the root node. When using JDBC, bind the numeric ID with `setLong`/`setBigDecimal` as appropriate; do not concatenate ID strings directly into SQL.

## 14. JOIN Conditions and Hierarchical Queries

A hierarchical query can combine data from multiple tables, but you must understand the order in which Oracle processes joins and the tree. At a high level, Oracle:

1. Processes JOINs in the query source.
2. Builds the hierarchy according to `START WITH` and `CONNECT BY`.
3. Applies remaining `WHERE` conditions to filter result rows.

Example:

~~~sql
SELECT LEVEL,
       e.employee_id,
       e.employee_name,
       d.department_name
FROM lab_employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
START WITH e.manager_id IS NULL
CONNECT BY PRIOR e.employee_id = e.manager_id
ORDER SIBLINGS BY e.employee_name;
~~~

The hierarchical query still traverses the employee–manager relationship; department name is merely an added attribute. If a JOIN produces multiple rows for one employee, the tree can be multiplied or paths duplicated. Verify that the JOIN relationship is one-to-one or many-to-one at the right grain before placing it in the hierarchical query source.

If you only need lookup attributes for a node, another clear approach is to build the tree first in a CTE and then JOIN the result with the lookup table afterward:

~~~sql
WITH employee_tree AS (
    SELECT LEVEL AS depth,
           employee_id,
           manager_id,
           CONNECT_BY_ROOT employee_id AS root_id
    FROM lab_employees
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
)
SELECT t.depth,
       t.root_id,
       t.employee_id,
       d.department_name
FROM employee_tree t
LEFT JOIN departments d
  ON d.department_id = (
      SELECT e.department_id
      FROM lab_employees e
      WHERE e.employee_id = t.employee_id
  );
~~~

This illustrates separating the steps, not a mandatory optimal pattern; in production systems you can bring `DEPARTMENT_ID` directly into the CTE to avoid a subquery. The key point is not letting a JOIN alter parent-child relationships or create unwanted extra paths.

## 15. Version Conditions and Compatibility

`LEVEL`, `PRIOR`, `CONNECT_BY_ROOT`, and `SYS_CONNECT_BY_PATH` are longstanding Oracle hierarchical query features supported across common Oracle releases, including 11g and 19c. However, when using related features such as recursive subquery factoring, syntax and limits may depend on the version.

Check the server version:

~~~sql
SELECT banner
FROM v$version;
~~~

Or if granted privileges:

~~~sql
SELECT instance_name, version
FROM v$instance;
~~~

Confirm the right PDB/service:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name
FROM dual;
~~~

Do not infer the Oracle Database version from the SQL Developer, SQLcl, or JDBC driver version. A newer client can still connect to an older server.

### 15.1 Hierarchical queries vs. recursive subquery factoring

Oracle also supports recursive subquery factoring with recursive CTEs in eligible versions. Both approaches can solve certain tree problems, though they are not identical:

| Hierarchical query | Recursive subquery factoring |
|---|---|
| Uses `START WITH` and `CONNECT BY` | Uses `WITH ... AS (...)` with an anchor branch and a recursive branch |
| Has the `LEVEL` pseudocolumn | Can compute a custom depth column in the CTE |
| Has `PRIOR` to reference the parent row | Recursive join condition references the CTE alias |
| Has `CONNECT_BY_ROOT` and `SYS_CONNECT_BY_PATH` | Typically carries root/path explicitly in CTE columns |
| Has `NOCYCLE` and related pseudocolumns | Has version-dependent cycle syntax/rules |

When maintaining systems that use `CONNECT BY`, there is no need to rewrite them solely because recursive CTEs exist. Choose the expression suited to the version, complexity, and maintainability.

## 16. Common Errors and Scenarios

| Error/symptom | Possible cause | What to check |
|---|---|---|
| `ORA-01436: CONNECT BY loop in user data` | Data forms a cycle in the hierarchy | Check the parent-child chain; use `NOCYCLE` to investigate and fix data |
| Query returns no rows | `START WITH` matches no roots or `CONNECT BY` condition has wrong direction | Run the root condition alone; check parent-child keys |
| Only roots returned, no children | Reversed `PRIOR` sides or mismatched MANAGER_ID data | Confirm `PRIOR employee_id = manager_id` for downward traversal |
| Tree has duplicated branches | JOIN multiplies source or a node has multiple paths | Check grain, many-to-many relationships, and join conditions |
| Child rows still appear when parent is filtered out | Predicate placed in `WHERE` filters individual rows, not the whole branch | Place branch-limiting condition in `CONNECT BY` when business logic requires it |
| Path too long | `SYS_CONNECT_BY_PATH` returns VARCHAR2 and exceeds expression limit | Limit depth/length, consider alternative representation |
| Path hard to parse | Node value contains the separator itself | Choose an appropriate delimiter or escape data |
| Tree order broken | Using regular `ORDER BY` | Use `ORDER SIBLINGS BY` to sort siblings |
| CONNECT_BY_ROOT rejected in condition | Operator restricted in `START WITH`/`CONNECT BY` | Use it in an appropriate SELECT expression |
| LEVEL not as expected | Different root chosen or multiple roots | Remember LEVEL starts at 1 at the query's root |
| Duplicate rows when a node has multiple parents | Hierarchical query returns per path | Distinguish distinct node count from path count |
| Tree disappears after adding status condition | Condition placed in CONNECT BY prevents branch expansion | Decide whether to hide rows or prune branches |

## 17. Self-Check Practice Exercises

Use the `LAB_EMPLOYEES` table created in section 2. The exercises do not require creating additional business data.

### Exercise 1 — Traverse the entire chart

Write a query:

- Start from all rows where `MANAGER_ID IS NULL`.
- Traverse from manager down to employee.
- Display `LEVEL`, employee ID, manager ID, and name.
- Sort siblings by `EMPLOYEE_NAME`.

Explain why both roots 100 and 200 appear at LEVEL 1.

### Exercise 2 — Reverse PRIOR direction

Start at `EMPLOYEE_ID = 112` and walk back up to the CEO. Write the appropriate `CONNECT BY` condition. Record the row order and LEVEL. Why does employee 112 have LEVEL 1 even though they are not the organizational root?

### Exercise 3 — Display the root

Add `CONNECT_BY_ROOT employee_id` and `CONNECT_BY_ROOT employee_name`. Identify which root all employees under root 100 share; which root does employee 210 belong to?

### Exercise 4 — Build paths

Use `SYS_CONNECT_BY_PATH(employee_name, ' / ')` to build paths. Then replace names with IDs converted with `TO_CHAR`. Compare the human-readable path with the path that stays stable when names change.

### Exercise 5 — Limit depth

Traverse at most 3 levels including the root. Write the condition in `CONNECT BY`. Also write a `WHERE LEVEL <= 3` variant and describe the difference in row filtering.

### Exercise 6 — Filter ACTIVE

Compare two queries:

~~~sql
WHERE status = 'ACTIVE'
~~~

and:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
       AND status = 'ACTIVE'
~~~

How is INACTIVE employee 122 handled? If there were an ACTIVE employee beneath an INACTIVE manager, would that row be traversed in each case?

### Exercise 7 — Multiple trees

Use `START WITH manager_id IS NULL` and add `CONNECT_BY_ROOT` to group employees by root leader. Count the number of nodes and the maximum depth of each tree.

### Exercise 8 — Sort siblings

Try `ORDER SIBLINGS BY employee_name` and compare with `ORDER BY employee_name`. Why can the second approach cause parent-child rows to lose readable tree order?

### Exercise 9 — Cycles

In a separate practice table without a foreign key, create a two-node cycle. Observe the error when running a normal hierarchical query; then add `NOCYCLE` and `CONNECT_BY_ISCYCLE`. Explain why the query running successfully does not mean the data is valid.

### Exercise 10 — Count distinct nodes or paths?

Suppose a category allows a node to have two parents. Explain why the same node can appear twice in a hierarchical query result and when to use `COUNT(*)` versus `COUNT(DISTINCT node_id)`.

## 18. Key Takeaways

| Component | Question it answers | How to use |
|---|---|---|
| `START WITH` | Which rows do we start traversing from? | Select one or multiple roots |
| `CONNECT BY` | How is the parent-child relationship defined? | Write the tree expansion condition |
| `PRIOR` | Which expression comes from the parent row? | `PRIOR parent_id = child_parent_id` according to traversal direction |
| `LEVEL` | What depth is the row at? | Root 1, child 2, grandchild 3... |
| `CONNECT_BY_ROOT` | Which node did the path start from? | Retrieve the root's value for every row in the tree |
| `SYS_CONNECT_BY_PATH` | What is the path from root to node? | Concatenate level values into a string |
| `ORDER SIBLINGS BY` | How to sort siblings while keeping the tree? | Sort nodes sharing the same parent |
| `NOCYCLE` | How to keep the query from failing on a loop? | Skip cycle-forming branches and investigate data |
| `CONNECT_BY_ISCYCLE` | Does the current row have an edge to an ancestor? | Detect cycles in NOCYCLE queries |

When writing a hierarchical query, determine the **roots**, **traversal direction**, and **parent-child relationship** first, then choose how to display the output. `LEVEL` describes depth; `PRIOR` controls the relationship at each step; `CONNECT_BY_ROOT` retains root information; `SYS_CONNECT_BY_PATH` builds the path. Combining these four components properly with `ORDER SIBLINGS BY`, appropriate filter conditions, and `NOCYCLE` when needed makes tree queries clear, verifiable, and free of confusion between a single node, a branch, and an entire forest.
