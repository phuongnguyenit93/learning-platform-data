# Hierarchical Queries with START WITH and CONNECT BY in Oracle

Much relational data is not merely a list of independent rows. It describes **hierarchical relationships**: employees belonging to a manager, departments having a parent department, categories with groups and subgroups, accounts with parent accounts, or a product composed of subcomponents. In a relational table model, these relationships are commonly stored using a *self-referencing foreign key*: each row holds the identifier of its parent row.

Oracle supports **hierarchical queries** with two clauses: `START WITH` and `CONNECT BY`. `START WITH` selects the root rows; `CONNECT BY` describes how to move from a current row to the next child or parent row. From there, Oracle can return a multi-level tree without writing a separate JOIN clause for each level.

This lesson belongs to the **Advanced Queries** topic of *Database Engine Relational Oracle*. The content focuses on:

- The parent–child model and how to read `PRIOR`.
- Selecting roots with `START WITH` and traversing the tree with `CONNECT BY`.
- The pseudocolumns `LEVEL`, `CONNECT_BY_ROOT`, `SYS_CONNECT_BY_PATH`, `CONNECT_BY_ISLEAF`, and `CONNECT_BY_ISCYCLE`.
- Ordering branches with `ORDER SIBLINGS BY`.
- Distinguishing row filtering from branch pruning, and handling cycles with `NOCYCLE`.
- Combining JOINs, indexes, execution plans, and hands-on SQL practice.

## 1. Hierarchical Data in a Relational Table

An employee table can contain both employee information and the direct manager's ID:

| EMPLOYEE_ID | EMPLOYEE_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | An | NULL |
| 2 | Binh | 1 |
| 3 | Chi | 1 |
| 4 | Dung | 2 |
| 5 | Ha | 2 |
| 6 | Lan | 3 |

`MANAGER_ID` references the manager's `EMPLOYEE_ID`. An's row has `MANAGER_ID IS NULL`, so An is the root of the tree in this example. Binh and Chi are direct children of An; Dung and Ha are children of Binh; Lan is a child of Chi.

~~~mermaid
flowchart TD
    A["An (1)"] --> B["Binh (2)"]
    A --> C["Chi (3)"]
    B --> D["Dung (4)"]
    B --> E["Ha (5)"]
    C --> F["Lan (6)"]
~~~

Parent–child relationships are stored as separate rows rather than storing the entire tree in a single column. A hierarchical query reconstructs the path based on the join condition between the parent row's key and the child row's foreign key.

### Creating the practice table

The following example uses a learning schema with `CREATE TABLE` privilege and an appropriate quota:

~~~sql
CREATE TABLE lab_employees_tree (
    employee_id   NUMBER(6) PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    manager_id    NUMBER(6),
    sort_order    NUMBER(4),
    CONSTRAINT fk_lab_emp_tree_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees_tree (employee_id)
);

INSERT INTO lab_employees_tree VALUES (1, 'An',   NULL, 1);
INSERT INTO lab_employees_tree VALUES (2, 'Binh', 1,    1);
INSERT INTO lab_employees_tree VALUES (3, 'Chi',  1,    2);
INSERT INTO lab_employees_tree VALUES (4, 'Dung', 2,    1);
INSERT INTO lab_employees_tree VALUES (5, 'Ha',   2,    2);
INSERT INTO lab_employees_tree VALUES (6, 'Lan',  3,    1);

COMMIT;
~~~

This is a self-referencing foreign key: `MANAGER_ID` must point to an existing `EMPLOYEE_ID` or be NULL. The foreign key constraint prevents references to a non-existent parent row, but **does not by itself prevent all hierarchical cycles**. For example, a row can reference one of its own child rows and still satisfy the FK; additional rules or cycle checks are needed if business logic disallows cycles.

## 2. START WITH and CONNECT BY Syntax

Basic pattern:

~~~sql
SELECT ...
FROM table_name
START WITH root_condition
CONNECT BY PRIOR parent_key = child_parent_key;
~~~

- `START WITH` identifies one or more starting rows (root rows).
- `CONNECT BY` defines the relationship between the current row and the next row in the tree.
- `PRIOR` references an expression in the **current parent row** during traversal.

With the employee table, querying from the top-level manager down to subordinate employees:

~~~sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS tree_level
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Reading the condition:

`PRIOR employee_id = manager_id`

means **the current parent row's employee_id equals the next child row's manager_id**. Oracle finds rows whose `MANAGER_ID` equals the `EMPLOYEE_ID` of the current row, then continues downward.

The result contains rows at multiple levels. `LEVEL` indicates the depth: An is at level 1, Binh/Chi at level 2, Dung/Ha/Lan at level 3.

### START WITH selecting multiple roots

A tree is not required to have only a single root. If multiple rows satisfy the condition, Oracle starts a tree from each matching row:

~~~sql
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

If a table contains multiple independent organizations, each with a root employee, the query returns the corresponding trees. You can select a specific root:

~~~sql
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH employee_id = 2
CONNECT BY PRIOR employee_id = manager_id;
~~~

The result starts from Binh and contains only Binh's branch and descendants. An does not appear because An is not within the downward scope from the selected root.

### What if START WITH is omitted?

In a hierarchical query without `START WITH`, Oracle can treat qualifying rows in the data source as starting points for the hierarchy. This often produces more paths and repeated results per root than intended. In business queries, always specify the root condition explicitly so the tree scope is clear and controllable.

## 3. Understanding PRIOR and Traversal Direction Accurately

`PRIOR` is a unary operator in the `CONNECT BY` condition. It applies to the expression immediately following it, and that expression is evaluated on the parent row of the current step.

### Traversing from parent to child

With the structure:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
~~~

Oracle takes the `EMPLOYEE_ID` of the parent row and finds rows whose `MANAGER_ID` equals that value. This is the most common way to write a query from a root down to its descendants.

### Traversing from child to parent

If you start at an employee and want to trace back up to the managers:

~~~sql
SELECT employee_id,
       employee_name,
       manager_id,
       LEVEL AS distance_from_employee
FROM lab_employees_tree
START WITH employee_id = 4
CONNECT BY PRIOR manager_id = employee_id;
~~~

Here `PRIOR manager_id` takes the manager ID of the current row; Oracle finds the next row whose `EMPLOYEE_ID` equals that ID. Starting from Dung (4), the result walks up to Binh (2), then An (1).

~~~mermaid
flowchart TD
    A["An (1)"] --> B["Binh (2)"] --> D["Dung (4)"]
    D -. "Reverse traversal from Dung" .-> B
    B -. "Continue up to parent" .-> A
~~~

The two `PRIOR` conditions above **cannot be swapped arbitrarily**. Clearly determine:

1. Which row is the root?
2. At each step, do you need to find the children of the current row or the parent of the current row?
3. Which column holds the identifying key of the current row?
4. Which column holds the key referencing the related row?

### PRIOR can be placed on the other side

Oracle allows `PRIOR` to precede an expression on either side of the condition, but the meaning remains that the expression is evaluated on the parent row. For example, the following two forms express the same parent–child relationship:

~~~sql
CONNECT BY PRIOR employee_id = manager_id

CONNECT BY manager_id = PRIOR employee_id
~~~

Writing the first form is usually easier to read because the parent's key sits next to `PRIOR`.

### Multi-column relationships

If the identifying key is a composite key, the CONNECT BY condition can join multiple components:

~~~sql
CONNECT BY PRIOR tenant_id = tenant_id
       AND PRIOR node_id = parent_node_id
~~~

This keeps traversal bounded within the same tenant. Omitting a key component can mistakenly connect trees across tenants or produce invalid paths.

## 4. LEVEL: Depth of a Row in the Tree

`LEVEL` is a pseudocolumn that is meaningful only in a hierarchical query:

- The root has `LEVEL = 1`.
- Direct children of the root have `LEVEL = 2`.
- Grandchildren have `LEVEL = 3`.
- Each subsequent step increases LEVEL by one.

Example of indented display:

~~~sql
SELECT LPAD(' ', 2 * (LEVEL - 1)) || employee_name AS hierarchy_name,
       employee_id,
       manager_id,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

`LPAD` adds spaces to visualize the structure. It only formats the output and does not alter the parent–child relationships.

### Limiting depth

If only the first three levels are needed, you can limit them in the CONNECT BY condition:

~~~sql
SELECT employee_id, employee_name, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= 3;
~~~

This condition prevents Oracle from expanding branches beyond level 3. Unlike filtering with `WHERE LEVEL <= 3` after building the tree, placing the condition in CONNECT BY can stop traversal at that limit. For very deep tables, limiting depth can significantly reduce work.

## 5. Key Pseudocolumns

Oracle provides several pseudocolumns and functions to retrieve information about a row's position in the tree:

| Component | Returns | Purpose |
| --- | --- | --- |
| `LEVEL` | Current depth, root is 1 | Displaying organizational tiers, limiting depth. |
| `CONNECT_BY_ROOT expr` | Value of the expression at the root of the current branch | Associating each row with its corresponding root. |
| `SYS_CONNECT_BY_PATH(col, delimiter)` | Path string from the root to the current row | Displaying breadcrumbs/paths. |
| `CONNECT_BY_ISLEAF` | 1 if the current row is a leaf, 0 if it still has children in the result tree | Finding terminal nodes/employees who manage no one. |
| `CONNECT_BY_ISCYCLE` | 1 if the current row has a child that is its ancestor, 0 otherwise | Identifying edges that form a cycle when using NOCYCLE. |

### CONNECT_BY_ROOT: retrieving information from the root

For example, each employee needs to know the name of the top-level manager in the tree:

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ROOT employee_name AS top_manager
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

If there are multiple roots, each descendant row carries the `TOP_MANAGER` value of the exact root where that path began. This is useful when grouping personnel by top-level unit or identifying tree branches.

### SYS_CONNECT_BY_PATH: building a path

~~~sql
SELECT employee_id,
       employee_name,
       SYS_CONNECT_BY_PATH(employee_name, ' / ') AS org_path
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

Example paths:

- ` / An`
- ` / An / Binh`
- ` / An / Binh / Dung`
- ` / An / Chi / Lan`

`SYS_CONNECT_BY_PATH` returns a string representing the path from the root to the current row. Choose a delimiter that will not collide with name contents; if data may contain the delimiter, apply escaping rules or return individual components separately.

### CONNECT_BY_ISLEAF: finding leaf nodes

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ISLEAF AS is_leaf
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

The rows Dung, Ha, and Lan are leaves in the example tree because no child employees are found under the CONNECT BY condition. Leaf is a concept **relative to the current tree and traversal condition**; if a filter excludes some child rows, a node can become a leaf in that query's result even though the source table still has other children.

Filtering to return only leaves:

~~~sql
SELECT employee_id, employee_name
FROM lab_employees_tree
WHERE CONNECT_BY_ISLEAF = 1
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

Hierarchical pseudocolumns must be referenced in the query block that has the corresponding START WITH/CONNECT BY clauses.

### CONNECT_BY_ISCYCLE: detecting cycles

When traversal encounters a row that could create a path back to an ancestor, Oracle raises an error unless `NOCYCLE` is enabled. When using `NOCYCLE`, you can select `CONNECT_BY_ISCYCLE` to identify rows that have a child which is an ancestor:

~~~sql
SELECT employee_id,
       employee_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS cycle_edge
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR employee_id = manager_id;
~~~

If the data has no cycles, this column is typically 0. It marks the current row in the traversal that has a child pointing to an ancestor; it is not a general flag meaning "every row belonging to a component that has a cycle".

## 6. Ordering a Tree with ORDER SIBLINGS BY

A tree with multiple branches needs to preserve parent–child ordering. A standard `ORDER BY` sorts the entire result set by the specified expressions, which can break the hierarchical display order.

Use `ORDER SIBLINGS BY` to sort **rows sharing the same parent** while preserving the hierarchical order:

~~~sql
SELECT LPAD(' ', 2 * (LEVEL - 1)) || employee_name AS tree_name,
       employee_id,
       manager_id,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER SIBLINGS BY sort_order, employee_name;
~~~

`SORT_ORDER` determines the order of siblings at the same level; `EMPLOYEE_NAME` serves as the tie-breaker. Oracle still displays children after their parent following the hierarchical structure.

Compare:

~~~sql
-- Sorts all rows without preserving tree order as required for display.
SELECT employee_id, employee_name, manager_id, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id
ORDER BY employee_name;
~~~

If the UI needs to display a tree, `ORDER SIBLINGS BY` is normally used. If only a flat list sorted by an attribute is needed, `ORDER BY` may be the right choice. Either way, result ordering is guaranteed only when an ordering clause is specified.

## 7. WHERE vs. CONNECT BY: Row Filtering or Branch Pruning?

This is a critical distinction in hierarchical queries. Oracle processes the query in a general order:

1. Process JOINs if present.
2. Determine the hierarchical relationships according to `CONNECT BY`.
3. Apply `WHERE` conditions to the resulting rows according to hierarchical query rules.

A WHERE condition filters individual returned rows; it **does not necessarily eliminate all descendants** of a filtered-out row. If the goal is to prevent traversal from passing through a row or to prune an entire branch, the condition generally must be placed in CONNECT BY.

Suppose the table has an additional `ACTIVE_FLAG` column and a manager is inactive:

~~~sql
SELECT employee_id, employee_name, manager_id, active_flag, LEVEL
FROM lab_employees_tree
WHERE active_flag = 'Y'
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

The WHERE condition can hide the inactive row from the output, yet that row's descendants can still be discovered during hierarchy traversal and appear in the result. This surprises writers who assume WHERE prunes the entire branch.

If you want to traverse only through active rows:

~~~sql
SELECT employee_id, employee_name, manager_id, active_flag, LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
       AND active_flag = 'Y'
CONNECT BY PRIOR employee_id = manager_id
       AND active_flag = 'Y';
~~~

The additional condition in CONNECT BY checks the child row being connected into the branch. The condition in START WITH also ensures the root itself is active.

### Decision rules for predicate placement

| Goal | Typical placement |
| --- | --- |
| Select valid roots | `START WITH` |
| Expand only to children meeting a condition | `CONNECT BY ... AND child_condition` |
| Hide certain rows from output while still allowing traversal through them | `WHERE` |
| Limit traversal depth | Condition in `CONNECT BY`, e.g., `LEVEL <= 4` |
| Display only leaves or roots after the tree is built | `WHERE` combined with the appropriate pseudocolumn |

If the goal is "do not display inactive managers, but still display active employees beneath them", WHERE may be appropriate. If the goal is "an inactive manager's branch must not be traversed", the predicate needs to prune traversal in CONNECT BY. Write a small test case to verify the semantics before applying it to critical reports.

## 8. NOCYCLE and Cyclic Data

An ideal tree model has one root per component and no path leading back to itself. Real-world data, however, can contain cycles due to import errors, incorrect parent key updates, or because the underlying model is actually a graph rather than a tree.

Example cycle:

~~~text
Node 1 -> Node 2 -> Node 3 -> Node 1
~~~

For a hierarchical query without `NOCYCLE`, Oracle may raise:

`ORA-01436: CONNECT BY loop in user data`

Add `NOCYCLE`:

~~~sql
SELECT node_id,
       parent_id,
       LEVEL,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_graph
START WITH node_id = 1
CONNECT BY NOCYCLE PRIOR node_id = parent_id;
~~~

`NOCYCLE` prevents infinite looping over a cycle and allows the query to return the traversable rows. It **does not fix the data**, does not delete invalid edges, and does not guarantee that every cycle in the table is found if they lie outside the traversal scope from the selected root.

### Lab table for testing cycles

To create a cycle, use a table without a self-referencing FK (since the exercise intentionally allows anomalous graph data):

~~~sql
CREATE TABLE lab_graph (
    node_id   NUMBER(6) PRIMARY KEY,
    parent_id NUMBER(6),
    node_name VARCHAR2(40 CHAR)
);

INSERT INTO lab_graph VALUES (1, 3, 'One');
INSERT INTO lab_graph VALUES (2, 1, 'Two');
INSERT INTO lab_graph VALUES (3, 2, 'Three');
COMMIT;
~~~

Run:

~~~sql
SELECT node_id,
       parent_id,
       node_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS is_cycle
FROM lab_graph
START WITH node_id = 1
CONNECT BY NOCYCLE PRIOR node_id = parent_id;
~~~

The path from node 1 can go 1 → 2 → 3; row 3 has node 1 as a child, which is already an ancestor. `CONNECT_BY_ISCYCLE` marks the spot where that back-edge is detected. The exact row count and display should be observed on the Oracle version you are studying.

### Detecting missing parent data

This is not a cycle, but is also a hierarchical data error:

~~~sql
SELECT c.node_id, c.parent_id
FROM lab_graph c
LEFT JOIN lab_graph p
  ON p.node_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.node_id IS NULL;
~~~

The query finds child rows referencing a non-existent parent. A self-referencing FK can prevent this error when ENABLEd and VALIDATEd; the lab graph table has no FK so it can be checked via SQL.

### Cycles and graph models

If a node can have multiple parents, the data is no longer a simple tree but a graph with multiple paths. A hierarchical query may return the same node multiple times along different paths. `NOCYCLE` handles looping back to an ancestor along a path, but it does not turn a graph into a tree and does not automatically pick one representative parent. You must determine whether business logic allows multiple parents, whether all paths or only one path are needed, and whether results must be deduplicated by node ID.

## 9. Combining Hierarchical Queries with JOINs

A hierarchical query can JOIN with description tables, permission tables, or attribute tables. Oracle processes joins before applying CONNECT BY; therefore, a one-to-many join can duplicate input rows and cause the tree to have multiple paths or unexpected results.

For example, each employee has multiple certificates. If you JOIN employees with certificates before traversing the tree, an employee with three certificates can appear as three rows in the hierarchical source. The tree structure can be multiplied.

### Using an inline view to build the tree first

~~~sql
SELECT t.employee_id,
       t.employee_name,
       t.manager_id,
       t.tree_level,
       c.certificate_name
FROM (
    SELECT employee_id,
           employee_name,
           manager_id,
           LEVEL AS tree_level
    FROM lab_employees_tree
    START WITH manager_id IS NULL
    CONNECT BY PRIOR employee_id = manager_id
) t
LEFT JOIN employee_certificates c
  ON c.employee_id = t.employee_id
ORDER BY t.tree_level, t.employee_id;
~~~

Here the tree is built in the inline view first, and certificates are JOINed afterward. The final output can still have multiple rows per employee if they hold multiple certificates, but **the hierarchical paths are not constructed over a source already multiplied by the certificates table**.

If you only need to know whether an employee has a certificate, use EXISTS or an aggregate to keep one row per employee instead of JOINing all certificates.

### Using a CTE to filter the input set

~~~sql
WITH eligible_employees AS (
    SELECT employee_id, employee_name, manager_id, sort_order
    FROM lab_employees_tree
    WHERE employee_id > 0
)
SELECT employee_id, employee_name, manager_id, LEVEL
FROM eligible_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;
~~~

A CTE clarifies the dataset used to build the tree. Remember that predicates inside the CTE alter the source rows visible to CONNECT BY; if a parent row is excluded, its descendants may lose their path from the root in the filtered source.

## 10. Performance and Indexes for Hierarchical Queries

A hierarchical query can expand across many levels. Cost depends on the number of roots, average fan-out per node, maximum depth, row width, and expressions evaluated along each path.

### Index on the parent key column

For the common condition:

~~~sql
CONNECT BY PRIOR employee_id = manager_id
~~~

Oracle needs to find child rows whose `MANAGER_ID` equals the current parent row's `EMPLOYEE_ID`. An index on `MANAGER_ID` is often helpful:

~~~sql
CREATE INDEX ix_lab_emp_tree_manager
ON lab_employees_tree (manager_id);
~~~

The primary key `EMPLOYEE_ID` typically already has an index to look up a node by ID, which helps reverse traversal from child to parent. However, an index does not guarantee the query will always use it; the optimizer also considers table size, clustering factor, cardinality, statistics, and how many rows must be read.

### Controlling depth and number of roots

If only one branch is needed, select a specific root rather than initializing every root. If business rules limit the number of levels, put the depth condition in CONNECT BY. This reduces the number of expanded nodes.

~~~sql
SELECT employee_id, employee_name, LEVEL
FROM lab_employees_tree
START WITH employee_id = :root_employee_id
CONNECT BY PRIOR employee_id = manager_id
       AND LEVEL <= :max_depth;
~~~

Bind `:root_employee_id` and `:max_depth` with appropriate types. This limit is part of business requirements; do not arbitrarily truncate depth if users need all descendants.

### Avoiding overly wide path expressions when unnecessary

`SYS_CONNECT_BY_PATH` constructs a string for every row. For deep trees or long names, path strings grow with depth and consume CPU/memory. Select the path only when the UI or report requires it; if only node ID and LEVEL are needed, avoid building unnecessary paths.

### Measuring with an execution plan

Example:

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id,
       employee_name,
       LEVEL
FROM lab_employees_tree
START WITH manager_id IS NULL
CONNECT BY PRIOR employee_id = manager_id;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Read the actual plan to inspect access paths, actual row counts, buffer gets, and operations related to hierarchical processing. `EXPLAIN PLAN` only produces an estimated plan and does not measure actual rows/time/TEMP usage. Privileges to read cursors and statistics depend on database configuration.

## 11. When to Use CONNECT BY vs. Recursive Subquery Factoring?

`START WITH ... CONNECT BY` is Oracle's familiar, concise syntax for hierarchical queries based on parent–child relationships. Oracle also supports **recursive subquery factoring** (recursive WITH clause), which can express traversal using an anchor member and a recursive member.

Example in recursive WITH form:

~~~sql
WITH org_tree (employee_id, employee_name, manager_id, tree_level) AS (
    SELECT employee_id, employee_name, manager_id, 1
    FROM lab_employees_tree
    WHERE manager_id IS NULL

    UNION ALL

    SELECT child.employee_id,
           child.employee_name,
           child.manager_id,
           parent.tree_level + 1
    FROM lab_employees_tree child
    JOIN org_tree parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, employee_name, manager_id, tree_level
FROM org_tree
ORDER BY tree_level, employee_id;
~~~

Recursive WITH is often useful when you need to combine multiple calculations/relationships in each iteration or express recursion in a general SQL structure. Depending on the Oracle version, Oracle also supports `SEARCH` and `CYCLE` clauses in recursive subquery factoring. `CONNECT BY` offers dedicated pseudocolumns such as LEVEL, CONNECT_BY_ROOT, and SYS_CONNECT_BY_PATH, making it very convenient for traditional tree queries.

There is no rule that one syntax is always faster than the other. Choose based on requirements, readability, Oracle version, cycle handling, and the actual plan.

## 12. Common Pitfalls and How to Fix Them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Only roots appear, no children | CONNECT BY condition has wrong PRIOR direction or joins wrong columns | Verify `PRIOR parent_key = child_fk`. |
| Traversing up to managers, but result goes downward | PRIOR placed on the wrong side | For upward traversal to parent, use `PRIOR child_parent_key = parent_key` according to the model. |
| Rows appear multiple times | Multiple roots/paths or source multiplied by a JOIN | Check graph/tree structure, roots, and cardinality; build tree before a one-to-many JOIN. |
| Results are not in branch order | Using global ORDER BY or no ORDER BY | Use ORDER SIBLINGS BY when tree structure must be preserved. |
| ORA-01436 | Data contains a cycle along the path | Use NOCYCLE to query safely; inspect and fix cyclic data per business rules. |
| WHERE hides a parent but children still appear | WHERE filters rows after the tree is built | If you want to prune the branch, put the predicate in CONNECT BY. |
| Tree has no root | Root condition does not match or data has cycles/bad parents | Check START WITH, orphan rows, and cycles. |
| Query returns too many rows | Too many roots, large depth, many-to-many relationships, or missing conditions | Restrict roots/depth per business rules; check join keys and indexes. |
| Leaf flag does not match table structure | Leaf is determined by the tree after traversal conditions | Check the CONNECT BY predicate and the traversed source set. |

## 13. Comprehensive Hands-On Lab

Run in a learning schema with table creation privileges and appropriate quota. DDL statements perform an implicit commit in Oracle. Do not run delete/drop statements on real production tables.

### Step 1: create an organization tree

~~~sql
CREATE TABLE lab_org_nodes (
    node_id       NUMBER(6) PRIMARY KEY,
    parent_id     NUMBER(6),
    node_name     VARCHAR2(80 CHAR) NOT NULL,
    display_order NUMBER(4),
    CONSTRAINT fk_lab_org_parent
        FOREIGN KEY (parent_id) REFERENCES lab_org_nodes(node_id)
);

INSERT INTO lab_org_nodes VALUES (1, NULL, 'Head Office', 1);
INSERT INTO lab_org_nodes VALUES (2, 1, 'Engineering', 1);
INSERT INTO lab_org_nodes VALUES (3, 1, 'Operations', 2);
INSERT INTO lab_org_nodes VALUES (4, 2, 'Platform', 1);
INSERT INTO lab_org_nodes VALUES (5, 2, 'Applications', 2);
INSERT INTO lab_org_nodes VALUES (6, 3, 'Finance', 1);
INSERT INTO lab_org_nodes VALUES (7, 3, 'Support', 2);
INSERT INTO lab_org_nodes VALUES (8, 5, 'Web Team', 1);
COMMIT;
~~~

### Step 2: query the entire tree

~~~sql
SELECT node_id,
       parent_id,
       node_name,
       LEVEL AS tree_level
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order, node_name;
~~~

Explain why `Head Office` is at LEVEL 1, `Engineering` is at LEVEL 2, and `Web Team` is at LEVEL 4.

### Step 3: retrieve only one branch

~~~sql
SELECT node_id, parent_id, node_name, LEVEL
FROM lab_org_nodes
START WITH node_id = 2
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order;
~~~

The result must be limited to Engineering and its descendants; Operations does not belong to the branch.

### Step 4: retrieve root, path, and leaf

~~~sql
SELECT node_id,
       node_name,
       CONNECT_BY_ROOT node_name AS root_name,
       SYS_CONNECT_BY_PATH(node_name, ' / ') AS node_path,
       LEVEL,
       CONNECT_BY_ISLEAF AS is_leaf
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
ORDER SIBLINGS BY display_order;
~~~

Identify the leaf rows and explain why a root may not be a leaf.

### Step 5: limit depth

~~~sql
SELECT node_id, node_name, LEVEL
FROM lab_org_nodes
START WITH parent_id IS NULL
CONNECT BY PRIOR node_id = parent_id
       AND LEVEL <= 2
ORDER SIBLINGS BY display_order;
~~~

Compare with `WHERE LEVEL <= 2` and explain the difference between stopping tree expansion and filtering output.

### Step 6: traverse from a node up to the root

~~~sql
SELECT node_id, node_name, parent_id, LEVEL
FROM lab_org_nodes
START WITH node_id = 8
CONNECT BY PRIOR parent_id = node_id;
~~~

The result walks from Web Team up to Applications, Engineering, and then Head Office. Explain how to read `PRIOR parent_id = node_id`.

### Step 7: check for orphans and cycles

The lab table has an FK, so a non-existent parent cannot be inserted while the constraint is ENABLEd. Test checking for orphans using a LEFT JOIN:

~~~sql
SELECT c.node_id, c.parent_id
FROM lab_org_nodes c
LEFT JOIN lab_org_nodes p
  ON p.node_id = c.parent_id
WHERE c.parent_id IS NOT NULL
  AND p.node_id IS NULL;
~~~

To test cycles, use a separate `LAB_GRAPH` table without an FK as in the NOCYCLE section. Record the `CONNECT_BY_ISCYCLE` result and why `NOCYCLE` does not automatically fix the data.

### Step 8: clean up data

~~~sql
DROP TABLE lab_org_nodes PURGE;
~~~

Run this only if you created the table in a practice schema and no longer need to keep the data. If you created `LAB_GRAPH`, drop that table only when no longer needed. `PURGE` bypasses the Recycle Bin; DROP TABLE is DDL and cannot be rolled back like uncommitted DML.

## 14. Self-Check Questions

1. **What is START WITH used for?** Selects one or more root rows to begin traversal.
2. **What does CONNECT BY define?** The relationship between the current parent row and the next child/parent row during traversal.
3. **What does `PRIOR employee_id = manager_id` mean?** Finds child rows whose manager_id equals the employee_id of the current parent row.
4. **How do you write a query to go from an employee up to managers?** With this model, use `PRIOR manager_id = employee_id`.
5. **What number does LEVEL start at?** The root has LEVEL = 1.
6. **What does CONNECT_BY_ROOT return?** The value of the expression at the root of the current path.
7. **What is SYS_CONNECT_BY_PATH used for?** Builds a path string from the root to the current row.
8. **What does CONNECT_BY_ISLEAF = 1 mean?** The current row has no further children in the tree under the traversal condition.
9. **Under what condition is CONNECT_BY_ISCYCLE used?** Used in a hierarchical query with NOCYCLE to identify rows that have a child which is an ancestor.
10. **Does NOCYCLE fix bad data?** No; it prevents the query from looping infinitely and allows observing paths that contain cycles.
11. **How does ORDER BY differ from ORDER SIBLINGS BY?** ORDER BY sorts the entire result set; ORDER SIBLINGS BY sorts siblings while preserving tree order.
12. **Does WHERE automatically prune all descendants of a filtered row?** Not necessarily; WHERE filters output rows, whereas predicates in CONNECT BY can prevent branch expansion.
13. **Why can JOINing a one-to-many table before CONNECT BY multiply the tree?** JOINs are processed before hierarchical processing, so one node can become multiple input rows.
14. **Which index is typically useful for parent-to-child traversal?** An index on the parent key column in the child row, such as MANAGER_ID.
15. **When should you consider recursive WITH?** When flexible recursion or complex operations in each iteration are needed; CONNECT BY is convenient for traditional Oracle trees.

Tree queries in Oracle require three clear decisions: **where to start, which relationship to follow, and when to stop**. `START WITH` selects roots, `CONNECT BY` together with `PRIOR` defines join direction, and `LEVEL` plus the pseudocolumns describe each node's position. When data may contain cycles, multiple parents, or one-to-many JOINs, control traversal scope and inspect the execution plan to avoid duplicated results or unexpected cost.
