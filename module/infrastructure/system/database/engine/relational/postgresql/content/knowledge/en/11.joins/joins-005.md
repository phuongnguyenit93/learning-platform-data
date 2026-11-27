# Self Joins and Simple Hierarchies in PostgreSQL

In a relational database, two related entities do not always live in two separate tables. An employee may report to **another employee in the same table**; a category may belong to **a parent category in the same table**; a comment may reply to another comment. PostgreSQL lets you represent these cases using a **self-referencing foreign key** and query them via a **self join**.

This lesson focuses on using `JOIN` with multiple aliases of the same table, distinguishing `INNER JOIN` from `LEFT JOIN`, querying one-level, two-level, and multi-level parent–child relationships, counting subordinates, and finding root/leaf nodes. When tree depth is not fixed, the lesson introduces `WITH RECURSIVE` as a natural extension of self joins.

## 1. What Is a Self Join?

**A self join is not a new SQL keyword.** It is simply using one table in **two or more roles** within the same `JOIN` statement. Each role needs an alias to identify which columns come from the child record and which come from the parent record.

Suppose we have an `employees` table:

| employee_id | full_name | manager_id |
| ---: | --- | ---: |
| 1 | Linh | NULL |
| 2 | An | 1 |
| 3 | Binh | 1 |
| 4 | Chi | 2 |
| 5 | Dung | 2 |

The `manager_id` values reference `employee_id` in the same table:

- Linh has no manager, so `manager_id IS NULL`.
- An and Binh report to Linh.
- Chi and Dung report to An.

~~~mermaid
flowchart TD
    L["Linh (1)"] --> A["An (2)"]
    L --> B["Binh (3)"]
    A --> C["Chi (4)"]
    A --> D["Dung (5)"]
~~~

To display the manager's name next to the employee's name:

~~~sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id;
~~~

`e` and `m` **are not two different tables**: both read `employees`, yet play two logical roles. The condition `m.employee_id = e.manager_id` pairs an employee with their corresponding manager row.

## 2. How Does a Self-Referencing Foreign Key Differ from a Self Join?

| Concept | Function | Example |
| --- | --- | --- |
| Self-referencing foreign key | Enforces validity of stored data | `manager_id REFERENCES employees(employee_id)` |
| Self join | Combines two roles of the same table in a query result | `employees e JOIN employees m ON ...` |
| Adjacency list | Model storing hierarchical data via a parent column | `employee_id` and `manager_id` |
| Recursive CTE | Queries relationships across an unknown number of levels | `WITH RECURSIVE hierarchy AS (...)` |

A self join can be executed even without a declared foreign key. However, without an FK, the database could store a `manager_id` pointing to a non-existent employee.

Conversely, a table with a self-referencing FK does not require every query to use a self join. If you only want employees with `manager_id = 1`, `WHERE manager_id = 1` suffices.

## 3. Preparing the Practice Environment

The examples run in a **dedicated practice** database, such as `pg_hierarchy_lab`. The script below drops the `hier_lab` schema to recreate sample data: **do not run it on a database containing real data or a shared schema**.

### 3.1. Building the Employees Table

~~~sql
-- Run only in a database dedicated to practice.
DROP SCHEMA IF EXISTS hier_lab CASCADE;
CREATE SCHEMA hier_lab;

CREATE TABLE hier_lab.employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL,
    department text NOT NULL,
    manager_id integer NULL,

    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES hier_lab.employees(employee_id)
        ON DELETE SET NULL,

    CONSTRAINT chk_no_direct_self_manager
        CHECK (
            manager_id IS NULL
            OR manager_id <> employee_id
        )
);

CREATE INDEX idx_employees_manager
    ON hier_lab.employees(manager_id);
~~~

Explanation:

- `employee_id PRIMARY KEY` uniquely identifies an employee row.
- `manager_id` has the same `integer` type, storing the direct manager's ID.
- `manager_id NULL` allows top-level employees to exist.
- Foreign key `fk_employee_manager` ensures any non-NULL manager ID exists in `employees`.
- `ON DELETE SET NULL` is an **illustrative** policy, meaning deleting a manager clears the direct link for their reports. It is not automatically suitable for real HR systems.
- `CHECK` prevents an employee from **directly** referencing themselves as their own manager.
- Index `idx_employees_manager` helps locate employees sharing the same `manager_id`.

**Warning:** the foreign key and `CHECK(manager_id <> employee_id)` do not prevent a longer cycle such as A → B → C → A. Multi-row invariants require additional enforcement mechanisms.

### 3.2. Loading Data Parent-First, Child-Second

~~~sql
INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (1, 'Linh', 'Engineering', NULL),
    (7, 'Giang', 'Operations', NULL);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (2, 'An',   'Engineering', 1),
    (3, 'Binh', 'Sales',       1),
    (8, 'Hoa',  'Operations',  7);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (4, 'Chi',  'Engineering', 2),
    (5, 'Dung', 'Engineering', 2),
    (6, 'Em',   'Sales',       3);

INSERT INTO hier_lab.employees
    (employee_id, full_name, department, manager_id)
VALUES
    (9, 'Khang', 'Engineering', 5);
~~~

Full dataset:

| ID | Employee | manager_id | Department |
| ---: | --- | ---: | --- |
| 1 | Linh | NULL | Engineering |
| 2 | An | 1 | Engineering |
| 3 | Binh | 1 | Sales |
| 4 | Chi | 2 | Engineering |
| 5 | Dung | 2 | Engineering |
| 6 | Em | 3 | Sales |
| 7 | Giang | NULL | Operations |
| 8 | Hoa | 7 | Operations |
| 9 | Khang | 5 | Engineering |

~~~mermaid
flowchart TD
    L["Linh (1)"] --> A["An (2)"]
    L --> B["Binh (3)"]
    A --> C["Chi (4)"]
    A --> D["Dung (5)"]
    D --> K["Khang (9)"]
    B --> E["Em (6)"]
    G["Giang (7)"] --> H["Hoa (8)"]
~~~

This is a **forest** of two trees because there are two root nodes, Linh and Giang. A self-referencing foreign key does not force the entire table to have only one root.

Read back:

~~~sql
SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
ORDER BY employee_id;
~~~

The sample data does not depend on clocks, randomness, or identity sequences, keeping results in this lesson reproducible.

## 4. Fetching Employees and Managers with LEFT SELF JOIN

~~~sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    e.manager_id,
    m.full_name AS manager_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

Result:

| employee_id | employee_name | manager_id | manager_name |
| ---: | --- | ---: | --- |
| 1 | Linh | NULL | NULL |
| 2 | An | 1 | Linh |
| 3 | Binh | 1 | Linh |
| 4 | Chi | 2 | An |
| 5 | Dung | 2 | An |
| 6 | Em | 3 | Binh |
| 7 | Giang | NULL | NULL |
| 8 | Hoa | 7 | Giang |
| 9 | Khang | 5 | Dung |

### Why Must We Use LEFT JOIN?

`LEFT JOIN` preserves **every row on the employee side `e`**. When `e.manager_id` is NULL, `m.employee_id = e.manager_id` finds no matching manager, so `m.full_name` is NULL while the employee is still returned.

If replaced with `INNER JOIN`:

~~~sql
SELECT
    e.full_name AS employee,
    m.full_name AS manager
FROM hier_lab.employees AS e
INNER JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

then Linh and Giang disappear. On the sample data:

- `INNER JOIN`: **7 rows** (employees who have a manager).
- `LEFT JOIN`: **9 rows** (all employees).

Both are right depending on the question. "List all employees with their manager if any" needs `LEFT JOIN`; "only employees who have a manager" can use `INNER JOIN`.

## 5. Why Are Aliases Essential?

In a self join, aliases identify the role of each table reference:

~~~sql
FROM hier_lab.employees AS employee
LEFT JOIN hier_lab.employees AS manager
    ON manager.employee_id = employee.manager_id
~~~

Here `employee` and `manager` are not new schemas or tables—they are aliases scoped to the query.

A very easy mistake to make:

~~~sql
-- Semantically wrong: pairs each employee with themselves.
ON manager.employee_id = employee.employee_id
~~~

That condition can return seemingly "clean" output because every employee's primary key always matches itself, yet `manager_name` becomes the employee's own name instead of the manager's name.

Correct:

~~~sql
ON manager.employee_id = employee.manager_id
~~~

When adding more levels, use clear aliases like `e`, `m`, and `gm`, or `child`, `parent`, and `grandparent`. For long queries, role-based names are much easier to audit than meaningless aliases like `a`, `b`, `c`.

## 6. Finding Direct Reports of a Manager

Querying from the manager side to subordinate employees:

~~~sql
SELECT
    manager.employee_id AS manager_id,
    manager.full_name AS manager_name,
    employee.employee_id AS report_id,
    employee.full_name AS report_name
FROM hier_lab.employees AS manager
JOIN hier_lab.employees AS employee
    ON employee.manager_id = manager.employee_id
WHERE manager.employee_id = 1
ORDER BY employee.employee_id;
~~~

Result:

| manager_name | report_id | report_name |
| --- | ---: | --- |
| Linh | 2 | An |
| Linh | 3 | Binh |

These are Linh's **direct reports**. Chi, Dung, Em, and Khang are also in the organization under Linh, though they do not report directly to Linh.

If you only need the IDs and names of direct reports without fetching manager details from the second table role:

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1
ORDER BY employee_id;
~~~

This query is simpler and directly answers the question. **Do not JOIN just for the sake of JOINing.** Choose a self join when the output genuinely needs data from both roles or a comparison between them.

## 7. Finding Roots: Nodes Without a Parent

In an adjacency list, roots typically have `manager_id IS NULL`:

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL
ORDER BY employee_id;
~~~

Result: Linh (1) and Giang (7).

`WHERE manager_id = NULL` is wrong because in SQL any equality comparison with NULL never returns TRUE. You must use `IS NULL`.

### Can You Use a Self Join to Find Roots?

~~~sql
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE m.employee_id IS NULL
ORDER BY e.employee_id;
~~~

With a valid FK, the result matches `WHERE e.manager_id IS NULL`. However, the two queries differ in a table **without an FK**:

- `e.manager_id IS NULL` finds records **that declare no parent**.
- `m.employee_id IS NULL` after a LEFT JOIN also catches records whose parent ID **does not exist** (*orphans*).

Therefore, when asking for "root nodes," using `manager_id IS NULL` directly is clearer. When diagnosing orphan records, use LEFT JOIN with distinguishing predicates.

## 8. Finding Leaves: Employees Managing Nobody

A leaf is a node **with no direct children**. Using a self join:

~~~sql
SELECT
    manager.employee_id,
    manager.full_name
FROM hier_lab.employees AS manager
LEFT JOIN hier_lab.employees AS report
    ON report.manager_id = manager.employee_id
WHERE report.employee_id IS NULL
ORDER BY manager.employee_id;
~~~

Result:

| ID | Employee |
| ---: | --- |
| 4 | Chi |
| 6 | Em |
| 8 | Hoa |
| 9 | Khang |

Dung is not a leaf because Dung manages Khang.

You can also use `NOT EXISTS` to express "has no children":

~~~sql
SELECT
    e.employee_id,
    e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
~~~

Both queries return the same result on the sample data. `NOT EXISTS` expresses the existence check very cleanly, while `LEFT JOIN ... IS NULL` is convenient when practicing join patterns.

**Root is not the opposite of leaf.** A single-node tree has one node that is both a root and a leaf. In our sample data, both roots have children, so neither is a leaf.

## 9. Counting Direct Reports with a Self Join

~~~sql
SELECT
    manager.employee_id,
    manager.full_name AS manager_name,
    COUNT(report.employee_id) AS direct_report_count
FROM hier_lab.employees AS manager
LEFT JOIN hier_lab.employees AS report
    ON report.manager_id = manager.employee_id
GROUP BY manager.employee_id, manager.full_name
ORDER BY manager.employee_id;
~~~

Result:

| ID | manager_name | direct_report_count |
| ---: | --- | ---: |
| 1 | Linh | 2 |
| 2 | An | 2 |
| 3 | Binh | 1 |
| 4 | Chi | 0 |
| 5 | Dung | 1 |
| 6 | Em | 0 |
| 7 | Giang | 1 |
| 8 | Hoa | 0 |
| 9 | Khang | 0 |

### Why COUNT(report.employee_id) Instead of COUNT(*)?

With `LEFT JOIN`, a manager with no reports still produces **one result row** where all `report` columns are NULL. `COUNT(*)` counts that row too, returning 1 for someone with zero direct reports. `COUNT(report.employee_id)` ignores NULLs and correctly returns 0.

Distinguish:

- `direct_report_count` = number of direct children.
- `total_descendant_count` = number of people below at **all depths**.

Linh has 2 direct reports yet **6 descendants** (An, Binh, Chi, Dung, Em, Khang). Counting all descendants requires traversing multiple levels.

## 10. Finding Two Employees Sharing the Same Manager

In a tree, two nodes sharing the same parent are called **siblings**. We use a self join where both aliases represent employees:

~~~sql
SELECT
    a.employee_id AS first_id,
    a.full_name AS first_employee,
    b.employee_id AS second_id,
    b.full_name AS second_employee,
    a.manager_id
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.manager_id, a.employee_id, b.employee_id;
~~~

Result:

| first_employee | second_employee | manager_id |
| --- | --- | ---: |
| An | Binh | 1 |
| Chi | Dung | 2 |

The condition `a.employee_id < b.employee_id` both prevents pairing an employee with themselves and avoids returning the same pair in reverse order (An, Binh) and (Binh, An). Writing `a.employee_id <> b.employee_id` would return each pair **twice** in reversed order.

`WHERE a.manager_id IS NOT NULL` makes it explicit that siblings must have an actual manager. Two roots with `NULL` `manager_id` would not match under `=` anyway, since SQL does not treat `NULL = NULL` as TRUE.

### Finding Employees in the Same Department with the Same Manager

You can extend it:

~~~sql
SELECT a.full_name, b.full_name, a.department
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.department = b.department
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.employee_id, b.employee_id;
~~~

In the sample data, Chi and Dung are both in Engineering and share manager An. An is in Engineering while Binh is in Sales, so the An–Binh pair is excluded once the department condition is added.

## 11. Two-Level Self Join: Fetching Manager and Grand-Manager

When querying **two fixed levels**, use three aliases:

~~~sql
SELECT
    employee.employee_id,
    employee.full_name AS employee_name,
    manager.full_name AS manager_name,
    grand_manager.full_name AS grand_manager_name
FROM hier_lab.employees AS employee
LEFT JOIN hier_lab.employees AS manager
    ON manager.employee_id = employee.manager_id
LEFT JOIN hier_lab.employees AS grand_manager
    ON grand_manager.employee_id = manager.manager_id
ORDER BY employee.employee_id;
~~~

Partial result:

| employee | manager | grand_manager |
| --- | --- | --- |
| Linh | NULL | NULL |
| An | Linh | NULL |
| Chi | An | Linh |
| Dung | An | Linh |
| Em | Binh | Linh |
| Khang | Dung | An |
| Giang | NULL | NULL |
| Hoa | Giang | NULL |

Because each level uses `LEFT JOIN`, nodes with only one level or no manager are still preserved.

If `INNER JOIN` were used for `grand_manager`, many completely valid employees would be dropped simply because they do not have two full management levels above them.

### Three Fixed Levels

For Khang:

~~~sql
SELECT
    e.full_name AS employee_name,
    m.full_name AS manager_name,
    gm.full_name AS grand_manager_name,
    t.full_name AS third_level_manager_name
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN hier_lab.employees AS gm
    ON gm.employee_id = m.manager_id
LEFT JOIN hier_lab.employees AS t
    ON t.employee_id = gm.manager_id
WHERE e.employee_id = 9;
~~~

Result: **Khang → Dung → An → Linh**.

This is easy to follow if the requirement is genuinely fixed at "up to three levels above." However, if an organization can have two, five, or ten levels, do not keep adding aliases indefinitely; use recursion.

## 12. Decision Table: When Is a Self Join Enough?

| Requirement | Recommendation |
| --- | --- |
| Direct parent's name | `LEFT JOIN` on the same table |
| All direct children of a given ID | `WHERE parent_id = ?` |
| Nodes without a parent | `WHERE parent_id IS NULL` |
| Nodes without children | `NOT EXISTS` or `LEFT JOIN ... IS NULL` |
| Count direct children | `LEFT JOIN` + `COUNT(child.id)` |
| Pairs sharing the same parent | Self join with two child aliases |
| Parent and grandparent (two levels) | Two self joins |
| All ancestors or descendants, variable tree depth | `WITH RECURSIVE` |
| Total people under a manager across all levels | Recursive CTE + `COUNT` |
| Check entire graph for cycles | Dedicated hierarchy validation routine |

One self join traverses **one edge** of the relationship. Adding another alias steps one more level; a recursive CTE repeats the join rule dynamically according to the data.

## 13. Limitations of Multi-Level Self Joins

Suppose an organization has this hierarchy:

~~~text
CEO
 └── VP
     └── Director
         └── Manager
             └── Team Lead
                 └── Engineer
~~~

A query with three self joins sees at most three levels above Engineer. If a seventh level is added later, the SQL query must be rewritten. Several drawbacks:

- Requires many aliases, making `ON` conditions error-prone.
- Output column count is fixed: `parent_1`, `parent_2`, `parent_3`...
- Cannot retrieve all descendants when depth is unknown in advance.
- Awkward for computing branch depth or building full display paths.
- Has no built-in mechanism to detect cycles in data.

PostgreSQL provides **recursive common table expressions (CTEs)** to traverse a variable number of edges in a self-referencing relationship.

## 14. WITH RECURSIVE: Traversing from Roots Down to All Levels

A recursive CTE has two parts:

1. **Anchor:** selects starting nodes, such as roots where `manager_id IS NULL`.
2. **Recursive term:** from the nodes found so far, self-joins the employees table to fetch direct children, repeating iteratively.

~~~mermaid
flowchart TD
    A["Anchor: root nodes"] --> B["Current node set"]
    B --> C["JOIN to find child nodes"]
    C --> D{"Any new child nodes?"}
    D -->|"Yes"| B
    D -->|"No"| E["Result set complete"]
~~~

Query:

~~~sql
WITH RECURSIVE employee_tree AS (
    -- Anchor: all employees without a manager.
    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        0 AS depth,
        ARRAY[e.employee_id] AS path_ids
    FROM hier_lab.employees AS e
    WHERE e.manager_id IS NULL

    UNION ALL

    -- Find employees whose manager is at a known level.
    SELECT
        child.employee_id,
        child.full_name,
        child.manager_id,
        parent.depth + 1,
        parent.path_ids || child.employee_id
    FROM hier_lab.employees AS child
    JOIN employee_tree AS parent
        ON child.manager_id = parent.employee_id
    WHERE NOT child.employee_id = ANY(parent.path_ids)
)
SELECT
    employee_id,
    full_name,
    manager_id,
    depth,
    path_ids
FROM employee_tree
ORDER BY path_ids;
~~~

Explanation:

- `depth = 0` for roots, incrementing by 1 each step down to a child.
- `path_ids` is an array of `employee_id`s from the root to the current node.
- `UNION ALL` combines anchor rows with recursive iterations without automatically deduplicating rows.
- `NOT child.employee_id = ANY(parent.path_ids)` avoids revisiting an ID already on the current path; this guards against loops when traversing a branch.
- `ORDER BY path_ids` sorts output deterministically by ID path, independent of physical table order.

Depth results:

| ID | Employee | depth |
| ---: | --- | ---: |
| 1 | Linh | 0 |
| 2 | An | 1 |
| 3 | Binh | 1 |
| 4 | Chi | 2 |
| 5 | Dung | 2 |
| 6 | Em | 2 |
| 7 | Giang | 0 |
| 8 | Hoa | 1 |
| 9 | Khang | 3 |

**Output ordering is not guaranteed by recursion itself**; when meaningful display order is needed, add `ORDER BY` in the final query.

### Limitations of Path-Based Cycle Guards

The path-array check only prevents revisiting **a node already along the same path**. It does not remove cycles stored in the table. Moreover, a cyclic component **disconnected from any root** will never be visited when the anchor selects only roots. Inspecting the entire graph requires separate diagnostic logic.

## 15. Querying an Employee's Entire Subtree

Fetch all employees under An (ID 2) by setting An as the anchor:

~~~sql
WITH RECURSIVE subtree AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        s.depth + 1,
        s.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN subtree AS s
        ON e.manager_id = s.employee_id
    WHERE NOT e.employee_id = ANY(s.path_ids)
)
SELECT employee_id, full_name, depth
FROM subtree
ORDER BY depth, employee_id;
~~~

Result:

| ID | Employee | depth from An |
| ---: | --- | ---: |
| 2 | An | 0 |
| 4 | Chi | 1 |
| 5 | Dung | 1 |
| 9 | Khang | 2 |

To return **descendants only**, exclude the anchor in the outer query:

~~~sql
-- Placed inside the same WITH RECURSIVE ... SELECT statement.
SELECT employee_id, full_name, depth
FROM subtree
WHERE depth > 0
ORDER BY depth, employee_id;
~~~

The CTE name `subtree` exists only within **a single SQL statement**. You cannot run `SELECT FROM subtree` in a subsequent statement without rewriting the CTE or wrapping it in a view/function.

## 16. Counting Total Descendants, Not Just Direct Reports

To count all employees under Linh (ID 1):

~~~sql
WITH RECURSIVE branch AS (
    SELECT
        employee_id,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 1

    UNION ALL

    SELECT
        e.employee_id,
        e.manager_id,
        b.depth + 1,
        b.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN branch AS b
        ON e.manager_id = b.employee_id
    WHERE NOT e.employee_id = ANY(b.path_ids)
)
SELECT COUNT(*) AS total_descendants
FROM branch
WHERE depth > 0;
~~~

Result: **6** (An, Binh, Chi, Dung, Em, and Khang).

Meanwhile:

~~~sql
SELECT COUNT(*) AS direct_reports
FROM hier_lab.employees
WHERE manager_id = 1;
~~~

returns **2**. These are two distinct metrics. Organization reports must be explicit on whether "subordinate count" means direct reports or all descendants.

## 17. Finding All Ancestors from an Employee Up to the Root

Recursion can also walk **upward**, from child records to parents:

~~~sql
WITH RECURSIVE manager_chain AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS steps_up,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE employee_id = 9

    UNION ALL

    SELECT
        m.employee_id,
        m.full_name,
        m.manager_id,
        c.steps_up + 1,
        c.path_ids || m.employee_id
    FROM hier_lab.employees AS m
    JOIN manager_chain AS c
        ON m.employee_id = c.manager_id
    WHERE NOT m.employee_id = ANY(c.path_ids)
)
SELECT employee_id, full_name, steps_up
FROM manager_chain
ORDER BY steps_up;
~~~

Result:

| ID | Employee | steps_up |
| ---: | --- | ---: |
| 9 | Khang | 0 |
| 5 | Dung | 1 |
| 2 | An | 2 |
| 1 | Linh | 3 |

We see the path: **Khang → Dung → An → Linh**. A two-level self join would only reach Dung and An; the recursive CTE climbs until no manager remains above.

### Querying a Branch's Root

If you only need Khang's root, filter in the final SELECT:

~~~sql
-- Inside the same WITH RECURSIVE manager_chain AS (...):
SELECT employee_id, full_name
FROM manager_chain
WHERE manager_id IS NULL;
~~~

On valid data, this finds Linh. If data is orphaned or cyclic, the chain may never reach a root, so an empty result does not necessarily mean the employee "does not exist."

## 18. Building a Display Path for the Tree

Applications often want to display paths like:

~~~text
Linh > An > Dung > Khang
~~~

We can extend the recursive CTE:

~~~sql
WITH RECURSIVE employee_paths AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth,
        full_name::text AS display_path,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        p.depth + 1,
        p.display_path || ' > ' || e.full_name,
        p.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN employee_paths AS p
        ON e.manager_id = p.employee_id
    WHERE NOT e.employee_id = ANY(p.path_ids)
)
SELECT employee_id, full_name, depth, display_path
FROM employee_paths
ORDER BY path_ids;
~~~

Expected rows:

~~~text
Linh
Linh > An
Linh > An > Chi
Linh > An > Dung
Linh > An > Dung > Khang
Linh > Binh
Linh > Binh > Em
Giang
Giang > Hoa
~~~

`display_path` is for **display**, while `path_ids` uses stable keys to track visited nodes and prevent cycles along the current path. Never use names as identifiers because two employees can share a name or change names.

## 19. Product Categories: Another Self-Referencing Example

Hierarchical self joins also appear in product catalogs:

~~~sql
CREATE TABLE hier_lab.categories (
    category_id integer PRIMARY KEY,
    category_name text NOT NULL,
    parent_id integer NULL
        REFERENCES hier_lab.categories(category_id)
        ON DELETE RESTRICT,
    CHECK (parent_id IS NULL OR parent_id <> category_id)
);

CREATE INDEX idx_categories_parent
ON hier_lab.categories(parent_id);
~~~

Load data:

~~~sql
INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES (10, 'Products', NULL);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (11, 'Electronics', 10),
    (12, 'Books', 10);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES
    (13, 'Phones', 11),
    (14, 'Laptops', 11),
    (15, 'Fiction', 12),
    (16, 'Nonfiction', 12);

INSERT INTO hier_lab.categories
    (category_id, category_name, parent_id)
VALUES (17, 'Smartphones', 13);
~~~

Diagram:

~~~mermaid
flowchart TD
    P["Products (10)"] --> E["Electronics (11)"]
    P --> B["Books (12)"]
    E --> PH["Phones (13)"]
    E --> LP["Laptops (14)"]
    PH --> S["Smartphones (17)"]
    B --> F["Fiction (15)"]
    B --> N["Nonfiction (16)"]
~~~

### 19.1. Categories and Direct Parents

~~~sql
SELECT
    c.category_id,
    c.category_name,
    p.category_name AS parent_name
FROM hier_lab.categories AS c
LEFT JOIN hier_lab.categories AS p
    ON p.category_id = c.parent_id
ORDER BY c.category_id;
~~~

Products has no parent; Electronics has parent Products; Phones has parent Electronics.

### 19.2. Two Parent Levels via Self Join

~~~sql
SELECT
    child.category_name AS category,
    parent.category_name AS parent_category,
    grandparent.category_name AS grandparent_category
FROM hier_lab.categories AS child
LEFT JOIN hier_lab.categories AS parent
    ON parent.category_id = child.parent_id
LEFT JOIN hier_lab.categories AS grandparent
    ON grandparent.category_id = parent.parent_id
WHERE child.category_id = 17;
~~~

Result for Smartphones:

~~~text
category             = Smartphones
parent_category      = Phones
grandparent_category = Electronics
~~~

To reach Products, add one more self join level or switch to a recursive CTE.

### 19.3. All Descendants of Electronics

~~~sql
WITH RECURSIVE category_tree AS (
    SELECT
        c.category_id,
        c.category_name,
        c.parent_id,
        0 AS depth,
        ARRAY[c.category_id] AS path_ids
    FROM hier_lab.categories AS c
    WHERE c.category_id = 11

    UNION ALL

    SELECT
        child.category_id,
        child.category_name,
        child.parent_id,
        parent.depth + 1,
        parent.path_ids || child.category_id
    FROM hier_lab.categories AS child
    JOIN category_tree AS parent
        ON child.parent_id = parent.category_id
    WHERE NOT child.category_id = ANY(parent.path_ids)
)
SELECT category_id, category_name, depth
FROM category_tree
WHERE depth > 0
ORDER BY depth, category_id;
~~~

Result:

| ID | Category | depth |
| ---: | --- | ---: |
| 13 | Phones | 1 |
| 14 | Laptops | 1 |
| 17 | Smartphones | 2 |

For category trees, the relation is still **a single self-referencing table**, only renaming `manager_id` to `parent_id`. The JOIN pattern remains fundamentally unchanged.

## 20. Adjacency List: Pros and Cons

Storing a `parent_id` column in each row is called an **adjacency list**.

**Advantages:**

- Simple structure; each record stores its direct parent.
- Foreign keys enforce parent existence.
- Adding a node or reparenting usually updates only a single row.
- Single-level queries are straightforward and easy to index.
- `WITH RECURSIVE` enables multi-level queries without pre-storing paths.

**Limitations:**

- Computing all ancestors/descendants requires recursion.
- Cycle prevention cannot rely solely on FKs.
- Very deep or wide trees can make traversal expensive.
- If path queries are extremely frequent, supplementary models like closure tables or materialized paths may be worth considering.

Other hierarchical models exist, such as **materialized path**, **closure table**, and **nested sets**. They shift trade-offs between read speed and update cost. For simple hierarchies, an adjacency list is usually the sensible starting point before optimizing.

## 21. Why Is a Foreign Key Not Enough to Prevent Cycles?

The constraint:

~~~sql
CHECK (manager_id IS NULL OR manager_id <> employee_id)
~~~

only blocks a row from directly pointing to itself, such as `employee_id = 2, manager_id = 2`.

It does not block:

~~~text
An (2) -> Khang (9) -> Dung (5) -> An (2)
~~~

because every `manager_id` points to a different valid employee and satisfies the FK.

An example **strictly for experimenting inside a transaction and then ROLLBACK**:

~~~sql
BEGIN;

UPDATE hier_lab.employees
SET manager_id = 9
WHERE employee_id = 2;

SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
WHERE employee_id IN (2, 5, 9)
ORDER BY employee_id;

ROLLBACK;
~~~

If committed, An reports to Khang, Khang reports to Dung, and Dung reports to An, forming a cycle. PostgreSQL does not reject this with the current FK/check constraints alone.

### What Is Needed to Protect Tree Structure?

- Before moving a node to a new parent, verify the new parent **is not among the node's descendants**.
- Perform the check and update inside a transaction with proper concurrency handling.
- Under concurrent writers, prevent two transactions from modifying links based on stale snapshots and introducing a cycle upon commit.
- Consider triggers/constraint triggers or database-enforced hierarchy checks when integrity is mandatory.
- When reading, use path guards or `CYCLE` (on supported versions) to avoid infinite traversal.

**Preventing infinite loops at query time is not the same as preventing invalid data writes.** Both problems need independent solutions.

## 22. CYCLE in PostgreSQL 14 and Later

PostgreSQL supports the `CYCLE` clause in recursive CTEs starting in **PostgreSQL 14**. This syntax tracks keys visited along a traversal path:

~~~sql
WITH RECURSIVE descendants AS (
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth
    FROM hier_lab.employees
    WHERE employee_id = 2

    UNION ALL

    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        d.depth + 1
    FROM hier_lab.employees AS e
    JOIN descendants AS d
        ON e.manager_id = d.employee_id
)
CYCLE employee_id SET is_cycle USING cycle_path
SELECT
    employee_id,
    full_name,
    depth,
    is_cycle
FROM descendants
ORDER BY cycle_path;
~~~

`CYCLE` generates the `is_cycle` flag and `cycle_path` array while preventing infinite expansion when an ID repeats along a path. It helps diagnose trees containing corrupted links.

On PostgreSQL **13 and earlier**, do not use this syntax; use a manual guard with a `path_ids` array as shown in earlier queries.

`CYCLE` is **not a table-wide constraint** and does not repair corrupt data. To stop writes from creating cycles, transaction, constraint, and business-level guards are still needed.

## 23. Distinguishing Roots, Orphans, and Cycle Components

A row can exist in several states:

| State | parent_id | Does parent row exist? | Meaning |
| --- | --- | --- | --- |
| Root | NULL | Not needed | Valid root node |
| Child | Non-NULL ID | Yes | Valid child node |
| Orphan | Non-NULL ID | No | Dangling reference, usually due to missing FK or bad data |
| Cycle component | Non-NULL ID | All parents may exist | Structure is no longer a tree |

If a cyclic component is completely **disconnected from any root**, a recursive query anchored at `manager_id IS NULL` will never reach it.

### Query to Find Orphans

~~~sql
SELECT
    e.employee_id,
    e.full_name,
    e.manager_id
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE e.manager_id IS NOT NULL
  AND m.employee_id IS NULL
ORDER BY e.employee_id;
~~~

With valid FK protection as in the lab, the result is **empty**.

Equivalent query using `NOT EXISTS`:

~~~sql
SELECT e.employee_id, e.full_name, e.manager_id
FROM hier_lab.employees AS e
WHERE e.manager_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM hier_lab.employees AS m
      WHERE m.employee_id = e.manager_id
  );
~~~

A valid FK prevents orphans, yet does not automatically guarantee **cycle-freedom** or a **single root**.

## 24. Reparenting and Managing Relationship Lifecycles

Suppose you want to move Dung (5) from manager An (2) to manager Binh (3):

~~~sql
BEGIN;

UPDATE hier_lab.employees
SET manager_id = 3
WHERE employee_id = 5;

SELECT
    e.full_name AS employee,
    m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
WHERE e.employee_id = 5;

ROLLBACK;
~~~

Inside the transaction, Dung's manager is Binh. After rollback, Dung reports to An again.

In production, applications should verify: is the new manager authorized to manage the employee; does moving the branch create a cycle; must reporting-line history be recorded; can concurrent writers modify the tree simultaneously?

### What Happens When Deleting a Parent?

The lab declared:

~~~sql
ON DELETE SET NULL
~~~

Deleting An clears the direct manager of Chi and Dung, while Khang still has manager Dung.

~~~sql
BEGIN;

DELETE FROM hier_lab.employees
WHERE employee_id = 2;

SELECT employee_id, full_name, manager_id
FROM hier_lab.employees
WHERE employee_id IN (4, 5, 9)
ORDER BY employee_id;

ROLLBACK;
~~~

Inside the transaction:

- Chi (4) has `manager_id NULL`.
- Dung (5) has `manager_id NULL`.
- Khang (9) still has `manager_id = 5`.

Using `ON DELETE CASCADE` instead of `SET NULL` could delete an entire employee subtree through cascading relations. For HR data, that behavior is rarely appropriate. When choosing `ON DELETE`, consider the **data lifecycle**, not just SQL validity.

## 25. Indexing Hierarchical Tables

Two common access paths:

- Looking up a node by `employee_id`: already indexed by `PRIMARY KEY`.
- Looking up child nodes by `manager_id`: consider a dedicated index.

~~~sql
CREATE INDEX idx_employees_manager
ON hier_lab.employees(manager_id);
~~~

An index on the child FK column **is not created automatically by PostgreSQL in all cases**. If queries frequently fetch children by parent, a `manager_id` index is usually helpful.

If you also need children sorted by ID:

~~~sql
CREATE INDEX idx_employees_manager_child
ON hier_lab.employees(manager_id, employee_id);
~~~

This composite index can serve both `manager_id` filtering and `employee_id` ordering, depending on the plan. Before keeping both indexes in a real app, evaluate whether the composite index alone suffices to avoid extra write and storage overhead.

### Using EXPLAIN

~~~sql
EXPLAIN
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

On a nine-row table, PostgreSQL may pick a sequential scan despite the index; that does not mean the index is broken. Evaluate real row counts, statistics, and workloads.

Recursive CTEs over large trees can consume significant memory or generate many intermediate rows. Define anchors clearly, guard against cycles, consider business depth limits, and benchmark on representative data rather than extrapolating from tiny examples.

## 26. Same Manager vs. Same Tree Depth

There are at least two meanings of "same level":

- **Same parent**: siblings, found via a self join with `a.manager_id = b.manager_id`.
- **Same depth from root**: identical `depth`, even across different branches or separate trees.

In the sample data, An, Binh, and Hoa all have `depth = 1`, yet Hoa reports to Giang, not Linh.

### Querying Depth Across the Entire Table

~~~sql
WITH RECURSIVE tree AS (
    SELECT
        employee_id,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS path_ids
    FROM hier_lab.employees
    WHERE manager_id IS NULL

    UNION ALL

    SELECT
        e.employee_id,
        e.manager_id,
        t.depth + 1,
        t.path_ids || e.employee_id
    FROM hier_lab.employees AS e
    JOIN tree AS t
        ON e.manager_id = t.employee_id
    WHERE NOT e.employee_id = ANY(t.path_ids)
)
SELECT
    t.depth,
    e.employee_id,
    e.full_name
FROM tree AS t
JOIN hier_lab.employees AS e
    ON e.employee_id = t.employee_id
ORDER BY t.depth, t.employee_id;
~~~

A single-level self join cannot compute arbitrary depth because depth results from **following multiple edges** of the relationship.

## 27. Common Mistakes

### 27.1. Forgetting Role Aliases

Referencing the same table multiple times requires clear aliases. Use `employee` and `manager` or `child` and `parent`.

### 27.2. Joining on the Row's Own ID

`m.employee_id = e.employee_id` matches each employee with themselves. The right predicate is `m.employee_id = e.manager_id`.

### 27.3. Using INNER JOIN and Losing Roots

Roots have `NULL` `manager_id`, so they have no manager row. When you want to keep all employees, use `LEFT JOIN`.

### 27.4. Comparing NULL with Equals

`WHERE manager_id = NULL` finds no roots. Use `IS NULL`.

### 27.5. Using COUNT(*) to Count Children After LEFT JOIN

People with no reports still produce a preserved row. Use `COUNT(child.employee_id)`.

### 27.6. Confusing Direct Reports with All Descendants

A single self join traverses one level. Use a recursive CTE when you need an entire subtree of varying depth.

### 27.7. Querying Siblings Without Eliminating Symmetric Pairs

`a.employee_id <> b.employee_id` returns both (A,B) and (B,A). Use `a.employee_id < b.employee_id` when each pair should appear once.

### 27.8. Assuming FKs Prevent All Cycles

An FK only ensures the parent exists; a single-row CHECK only blocks direct self-links. Multi-row cycles need dedicated protection.

### 27.9. Traversing from Roots and Assuming All Rows Were Seen

A disconnected cyclic component never appears when the anchor selects only `manager_id IS NULL`.

### 27.10. Recursive CTE Without a Cycle Guard on Cyclic Data

`UNION ALL` over a cyclic edge generates rows endlessly. Use a path guard or `CYCLE` as appropriate.

### 27.11. Expecting Deterministic Order from a Recursive CTE

SQL output has no guaranteed ordering without `ORDER BY`. Sort explicitly by path, depth, and ID.

### 27.12. Deleting a Manager with CASCADE Without Checking Data Lifecycle

That can wipe out an entire subtree; verify retention and business rules first.

### 27.13. Adding Indexes Out of Habit

Indexes speed up reads yet cost storage and write overhead. Compare plans before keeping overlapping indexes.

### 27.14. Using Recursion for a Single-Level Query

If you only need direct reports, `WHERE manager_id = ?` is far simpler.

## 28. Practice Exercises with Solutions

Use the data from section 3; do not commit experimental updates or deletes.

### Exercise 1. Employees and Direct Managers

~~~sql
SELECT e.full_name AS employee, m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
~~~

**Result:** Linh and Giang have NULL managers; An/Binh report to Linh; Chi/Dung report to An; Em reports to Binh; Hoa reports to Giang; Khang reports to Dung.

### Exercise 2. Direct Reports of Linh

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1
ORDER BY employee_id;
~~~

**Result:** An (2), Binh (3).

### Exercise 3. Root Nodes

~~~sql
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL
ORDER BY employee_id;
~~~

**Result:** Linh and Giang; there are two roots, so this is a forest.

### Exercise 4. Employees with No Subordinates

~~~sql
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
~~~

**Result:** Chi, Em, Hoa, Khang.

### Exercise 5. Count An's Direct Reports

~~~sql
SELECT COUNT(*) AS direct_reports
FROM hier_lab.employees
WHERE manager_id = 2;
~~~

**Result:** 2 (Chi, Dung).

### Exercise 6. Find Pairs Sharing the Same Manager

~~~sql
SELECT a.full_name AS first_name, b.full_name AS second_name
FROM hier_lab.employees AS a
JOIN hier_lab.employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
WHERE a.manager_id IS NOT NULL
ORDER BY a.manager_id, a.employee_id;
~~~

**Result:** (An, Binh) and (Chi, Dung).

### Exercise 7. Khang's Manager and Grand-Manager

~~~sql
SELECT
    e.full_name AS employee,
    m.full_name AS manager,
    gm.full_name AS grand_manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN hier_lab.employees AS gm
    ON gm.employee_id = m.manager_id
WHERE e.employee_id = 9;
~~~

**Result:** Khang → Dung → An.

### Exercise 8. Linh's Total Descendants

Use the recursive CTE from section 16 with anchor `employee_id = 1`.

**Result:** 6, distinct from the 2 direct reports.

### Exercise 9. Management Path from Khang to Root

Use the recursive CTE from section 17 with anchor `employee_id = 9`.

**Result:** Khang → Dung → An → Linh.

### Exercise 10. Direct Subcategories of Electronics

~~~sql
SELECT category_id, category_name
FROM hier_lab.categories
WHERE parent_id = 11
ORDER BY category_id;
~~~

**Result:** Phones (13), Laptops (14).

### Exercise 11. Descendants of Electronics

Use the recursive CTE from section 19 anchored at category 11.

**Result:** Phones and Laptops at depth 1; Smartphones at depth 2.

### Exercise 12. Why Does CHECK Not Block Multi-Hop Cycles?

If A points to B, B points to C, and C points to A, every individual row satisfies `parent_id <> id`, yet the overall structure forms a cycle. **Answer:** multi-row/transactional validation is needed, not just a single-row CHECK.

### Exercise 13. Why Are Two Roots Not Paired as Siblings?

`NULL = NULL` does not evaluate to TRUE. Moreover, in an org chart, two roots do not share an actual manager. Grouping roots requires an explicit business rule rather than treating them as siblings by default.

### Exercise 14. Which Self Join Returns 7 Rows, and Which Returns 9 Rows?

`INNER JOIN` from employees to managers returns 7 by dropping both roots. `LEFT JOIN` returns 9 by keeping Linh and Giang even with NULL manager columns.

## 29. Workflow for Solving a Hierarchical Query Requirement

When asked to write SQL over a parent–child relationship, follow these steps:

1. Identify the **unique ID** of each node.
2. Identify the `parent_id`/`manager_id` column and whether NULL denotes a root.
3. Verify the self-referencing FK and integrity constraints.
4. Determine whether the task requires one level, a fixed number of levels, or all levels.
5. For one level, choose `JOIN`/`LEFT JOIN` or `WHERE parent_id=?`.
6. Name aliases by role: child, parent, grandparent.
7. For roots or leaves, use `IS NULL` or `NOT EXISTS` appropriately.
8. For variable depth, use `WITH RECURSIVE` with a clear anchor and self-joining recursive term.
9. Add cycle guards and depth limits when data integrity cannot be assumed.
10. Add `ORDER BY` when tree order or stable output is required.
11. Consider indexing the child-side parent ID and check plans with `EXPLAIN`.
12. Define reparenting/deletion policies and concurrency controls when multiple writers operate simultaneously.

You do not need a separate table for every management tier. One self-referencing table suffices to store an adjacency list hierarchy; the rest is **querying the right depth and protecting the relationships allowed by business rules**.

## 30. Summary

A self join in PostgreSQL simply **uses the same table in multiple roles**, commonly seen in hierarchical data:

~~~sql
-- Direct manager's name for every employee.
SELECT e.full_name, m.full_name AS manager
FROM hier_lab.employees AS e
LEFT JOIN hier_lab.employees AS m
    ON m.employee_id = e.manager_id;

-- Employees who are roots.
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id IS NULL;

-- Employees reporting directly to Linh (ID 1).
SELECT employee_id, full_name
FROM hier_lab.employees
WHERE manager_id = 1;

-- Employees with no subordinates.
SELECT e.employee_id, e.full_name
FROM hier_lab.employees AS e
WHERE NOT EXISTS (
    SELECT 1
    FROM hier_lab.employees AS child
    WHERE child.manager_id = e.employee_id
);
~~~

When you only need one or two levels, `LEFT JOIN`/`INNER JOIN` with clear aliases is the direct solution. When you need **all levels in a tree**, use `WITH RECURSIVE` to repeat the parent–child join until no nodes remain.

A self-referencing foreign key guarantees **parents exist**, yet does not automatically guarantee **cycle-freedom** or a single root. Combining proper constraints, write validation, indexes, and query logic turns a simple adjacency list hierarchy into a reliable, scalable, and maintainable design in PostgreSQL.
