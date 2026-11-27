# Detecting Loops with NOCYCLE and CONNECT_BY_ISCYCLE in Oracle Database
Oracle Database supports *hierarchical queries* to traverse parent–child data such as employee–manager charts, multi-level categories, directory trees, or organizational structures. A dangerous issue is a **loop (cycle)**: following parent–child relationships and returning to a row that already appeared earlier on the same path.

For example, Alice manages Bob, Bob manages Carol, yet Carol is recorded as Alice's manager. The path Alice → Bob → Carol → Alice forms a cycle. If a hierarchical query continues traversing, Oracle can raise an error:

```text
ORA-01436: CONNECT BY loop in user data
```

Oracle provides two features to handle this:
- **`NOCYCLE`** allows the query to return rows even when the data contains loops, while preventing a branch from expanding further across the edge that closes the loop.
- **`CONNECT_BY_ISCYCLE`** is a pseudocolumn that returns 1 if the current row has a child row that already appeared in its ancestor path; otherwise it returns 0. This pseudocolumn is valid only when `NOCYCLE` is specified in `CONNECT BY`.

`NOCYCLE` prevents the query from failing due to a loop error; `CONNECT_BY_ISCYCLE` helps identify where to investigate. **These two features do not fix the data** and do not guarantee that the entire hierarchical model is valid.

## 1. Loops in Hierarchical Data

### 1.1. Normal parent–child structure

An employee table can store the manager ID in each row:

```text
EMP_ID  EMP_NAME  MANAGER_ID
------  --------  ----------
1       Alice     NULL
2       Bob       1
3       Carol     1
4       David     2
```

Diagram:

```text
             Alice (1)
             /      \
          Bob (2)  Carol (3)
            |
         David (4)
```

Alice is the root node; Bob and Carol are direct reports; David reports to Bob. Paths from manager down to employee do not return to an already-visited row.

### 1.2. Indirect loops

Erroneous data might look like:

| EMP_ID | EMP_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | Alice | 3 |
| 2 | Bob | 1 |
| 3 | Carol | 2 |

When traversing from manager down to subordinate:

```text
Alice (1)
   |
   v
Bob (2)
   |
   v
Carol (3)
   |
   +----------> Alice (1)
```

The cycle involves three rows. A loop can also consist of a single self-referencing row or more rows.

Distinctions:
- **Self-loop:** row A points to A itself.
- **Multi-node cycle:** A → B → C → A.
- **Multiple branches:** a node is reached from different branches; this is not automatically a cycle.
- **Orphan data:** the referenced parent key does not exist; this is a different error from a cycle.

### 1.3. Why can't a foreign key prevent a cycle?

A self-referencing foreign key ensures that a non-NULL `MANAGER_ID` must point to an existing employee when the constraint is enabled and validated. However, an FK does not analyze paths:

```text
1 -> 2 -> 3 -> 1
```

Every manager ID in the cycle exists, so the FK remains satisfied. Ensuring an acyclic structure requires hierarchical validation logic or separate business rules.

## 2. Hierarchical Query Syntax and NOCYCLE

### 2.1. General structure

```sql
SELECT ...
FROM   table_name
[WHERE row_filter]
[START WITH root_condition]
CONNECT BY [NOCYCLE] parent_child_condition
[ORDER SIBLINGS BY sort_expression];
```

- `START WITH` selects starting rows (roots or seeds).
- `CONNECT BY` describes the relationship between the current row and the next row.
- `PRIOR` specifies the expression taken from the parent row in the previous step.
- `NOCYCLE` enables detecting and stopping loop-forming branches.
- `ORDER SIBLINGS BY` sorts rows at the same level under a parent while preserving hierarchical order.

### 2.2. Traversing from manager down to employee

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id;
```

The condition `PRIOR emp_id = manager_id` means: the employee ID on the parent row equals the manager ID on the child row. Oracle finds employees whose `MANAGER_ID` equals the `EMP_ID` of the current row.

### 2.3. Traversing from employee up to manager

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH emp_id = :employee_id
CONNECT BY PRIOR manager_id = emp_id;
```

Here the query walks in the reverse direction: taking the current row's manager_id and finding the row with the matching emp_id. Traversal direction changes the ancestors on the path and can change which row is flagged as a cycle.

### 2.4. Adding NOCYCLE

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   employees
START WITH emp_id = :start_employee
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

`NOCYCLE` is placed immediately after `CONNECT BY`. It allows Oracle to return the traversable portion of the hierarchy without continuing to loop on a path that encounters a cycle. It only controls the query; it does not update `MANAGER_ID`, delete rows, or repair parent–child relationships.

## 3. CONNECT_BY_ISCYCLE

### 3.1. Syntax and meaning

`CONNECT_BY_ISCYCLE` is a pseudocolumn with no parameters:

```sql
SELECT emp_id,
       emp_name,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   employees
START WITH emp_id = :start_employee
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

| CYCLE_FLAG | Meaning |
| ---: | --- |
| 0 | The current row has no child row that is an ancestor on the path |
| 1 | The current row has at least one child row that already appeared in its ancestor path; continuing would create a cycle |

**This pseudocolumn requires `NOCYCLE` in the `CONNECT BY` clause.** Do not use `CONNECT_BY_ISCYCLE` in a hierarchical query without `NOCYCLE`.

### 3.2. Which row gets flagged?

Suppose the path being traversed is:

```text
1 -> 2 -> 3
```

Row 3 has a child row 1. However, 1 is already an ancestor of 3 on the current path. Therefore row 3 is marked `CONNECT_BY_ISCYCLE=1`. Oracle does not need to return row 1 again to indicate the loop.

Key points to remember:
- The flagged row is the **current row immediately before the loop-closing edge**.
- The repeated ancestor row is not added to the branch as a new occurrence.
- A cycle is evaluated along the current path, not simply whether an ID ever appeared in any branch.

### 3.3. How NOCYCLE and CONNECT_BY_ISCYCLE work together

`NOCYCLE` allows the hierarchical query to continue and stop a branch at the loop point; `CONNECT_BY_ISCYCLE` provides a flag to identify when the current row has a child edge pointing back to an ancestor. Combining them lets the query both return useful data and pinpoint where to inspect.


## 4. Hands-On: Creating Data with Cycles

### 4.1. Creating a self-referencing table

Create a dedicated demo table in a learning schema:

```sql
CREATE TABLE demo_org_employees (
    emp_id     NUMBER(10) PRIMARY KEY,
    emp_name   VARCHAR2(100) NOT NULL,
    manager_id NUMBER(10),
    CONSTRAINT fk_demo_org_manager
        FOREIGN KEY (manager_id)
        REFERENCES demo_org_employees(emp_id)
);
```

The self-referencing FK allows a NULL manager, while a non-NULL manager must exist. The FK does not check multi-row cycles.

### 4.2. Insert rows first, then establish relationships

Insert rows with NULL manager first to satisfy the FK:

```sql
INSERT INTO demo_org_employees VALUES (1, 'Alice', NULL);
INSERT INTO demo_org_employees VALUES (2, 'Bob',   NULL);
INSERT INTO demo_org_employees VALUES (3, 'Carol', NULL);
INSERT INTO demo_org_employees VALUES (4, 'David', NULL);
COMMIT;
```

Then update the relationships:

```sql
UPDATE demo_org_employees SET manager_id = 3 WHERE emp_id = 1;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 2;
UPDATE demo_org_employees SET manager_id = 2 WHERE emp_id = 3;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 4;
COMMIT;
```

The table now holds:

| EMP_ID | EMP_NAME | MANAGER_ID |
| ---: | --- | ---: |
| 1 | Alice | 3 |
| 2 | Bob | 1 |
| 3 | Carol | 2 |
| 4 | David | 1 |

Alice, Bob, and Carol form a cycle; David reports to Alice.

### 4.3. Querying without NOCYCLE

In the demo environment, run:

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY PRIOR emp_id = manager_id;
```

The path Alice → Bob → Carol → Alice creates a loop. Oracle may raise:

```text
ORA-01436: CONNECT BY loop in user data
```

### 4.4. Querying with NOCYCLE and CONNECT_BY_ISCYCLE

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Sample output:

| EMP_ID | EMP_NAME | MANAGER_ID | HIERARCHY_LEVEL | CYCLE_FLAG | ID_PATH |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | Alice | 3 | 1 | 0 | /1 |
| 2 | Bob | 1 | 2 | 0 | /1/2 |
| 3 | Carol | 2 | 3 | 1 | /1/2/3 |
| 4 | David | 1 | 2 | 0 | /1/4 |

Carol has child Alice, who is already in path `/1/2/3`; therefore Carol gets flag 1. David's branch is traversed separately and does not form a cycle.

`SYS_CONNECT_BY_PATH` constructs the path from the root to the current row, which is useful during investigation. Long paths on large tables can increase cost and the volume of returned data.

### 4.5. The current row and the loop-causing edge

In the example, Carol (3) is the flagged row. The next edge under the hierarchical condition would go from Carol back to Alice (1). Since Alice is already an ancestor, the Carol → Alice edge closes the loop.

Do not interpret flag 1 as Carol self-referencing herself. Inspect Carol's child rows and the ancestor path to identify which edge causes the loop.


## 5. Tracing the Loop-Closing Edge

### 5.1. Filtering rows with the cycle flag

Place the hierarchical query in a CTE and filter in the outer query:

```sql
WITH hierarchy_rows AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           LEVEL AS hierarchy_level,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT emp_id,
       emp_name,
       manager_id,
       hierarchy_level,
       id_path
FROM   hierarchy_rows
WHERE  cycle_flag = 1;
```

The query returns current rows that have a child row acting as an ancestor on the path. Separating into a CTE makes tree traversal and reporting logic easier to read.

### 5.2. Finding the child row that is an ancestor

With integer ID keys where `/` cannot appear in an ID, you can use the path to identify the loop-closing edge:

```sql
WITH hierarchy_rows AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT h.emp_id AS current_employee,
       h.emp_name AS current_name,
       child.emp_id AS ancestor_employee,
       child.emp_name AS ancestor_name,
       h.id_path
FROM   hierarchy_rows h
JOIN   demo_org_employees child
       ON child.manager_id = h.emp_id
WHERE  h.cycle_flag = 1
AND    INSTR(
         h.id_path || '/',
         '/' || TO_CHAR(child.emp_id) || '/'
       ) > 0;
```

Output:

| CURRENT_EMPLOYEE | CURRENT_NAME | ANCESTOR_EMPLOYEE | ANCESTOR_NAME | ID_PATH |
| ---: | --- | ---: | --- | --- |
| 3 | Carol | 1 | Alice | /1/2/3 |

The `INSTR` condition checks whether the child row's ID appears in the path. Trailing and leading `/` delimiters prevent confusing ID 1 with ID 11. This is a demonstration query for numeric keys; if keys are strings that may contain the delimiter, encode them or choose an appropriate comparison method.

### 5.3. Using CONNECT_BY_ROOT

`CONNECT_BY_ROOT expression` returns the value of the expression at the root row of the path:

```sql
SELECT CONNECT_BY_ROOT emp_id AS root_emp_id,
       emp_id,
       emp_name,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

When a query has multiple seeds, this pseudocolumn identifies which root's path each row belongs to.

### 5.4. The cycle flag is not a list of every error in the table

`CONNECT_BY_ISCYCLE` only detects when a child row is already an ancestor on the currently traversed path. It does not automatically list every cycle in the schema, components unreachable from START WITH, all invalid edges, all orphan rows, or duplicate rows appearing on different paths.

You must determine the seed scope and traversal direction before concluding that the result covers the entire dataset.

## 6. START WITH and Detection Scope

### 6.1. Traverses only branches reachable from seeds

Query:

```sql
SELECT emp_id,
       emp_name,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

After creating the cycle in the demo data, no row has `MANAGER_ID IS NULL`, so the query may return 0 rows. That **does not prove the table has no cycles**; there are simply no seeds matching START WITH to begin traversal.

If you know a row belonging to the faulty component, you can use it as a seed via `START WITH emp_id = 1`.

### 6.2. Without START WITH

When `START WITH` is omitted, Oracle treats all rows as roots of the hierarchical query. This approach can help investigate components that lack a natural root:

```sql
SELECT emp_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

The query can generate many paths from multiple starting points and repeat rows across different paths. Use only on controlled datasets; do not treat this as a routine reporting query for large tables.

### 6.3. Traversal direction changes results

Traversing from manager down to employee:

```sql
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
```

Traversing from employee up to manager:

```sql
CONNECT BY NOCYCLE PRIOR manager_id = emp_id
```

Ancestors along each path differ, so the row with `CONNECT_BY_ISCYCLE=1` can also differ. Always read the PRIOR condition to understand traversal direction.

### 6.4. WHERE placement in hierarchical queries

Oracle processes joins first, then determines the hierarchy via START WITH/CONNECT BY, and then applies WHERE conditions according to hierarchical query rules. WHERE does not necessarily prune an entire branch before the tree is built.

If a condition decides which rows are allowed to participate in parent–child relationships, consider placing it in `CONNECT BY` or filtering the source with an inline view before traversal. Do not assume WHERE always stops Oracle from traversing through a filtered-out row.


## 7. Cycles vs. Other Data Issues

| Case | Example | Meaning |
| --- | --- | --- |
| Self-loop | A points manager to A | A single row referencing itself |
| Multi-node cycle | A → B → C → A | Path returns to an ancestor |
| Orphan data | manager_id points to a non-existent ID | Invalid reference |
| Multiple children | One manager has 20 employees | Normal 1:N relationship |
| Multiple paths | A node is reachable from different branches | Not necessarily a cycle |

A self-referencing FK can prevent orphan data but cannot prevent multi-node cycles. A node reached from two different branches is not automatically a cycle; it must match an ancestor on the same path.

## 8. Fixing Data After Detecting a Cycle

### 8.1. Verify before updating

Do not delete a row with a cycle flag merely because it is flagged. That row may be a valid employee; the manager relationship or an edge from a child row is the bad data.

Process:
1. Record the path and related rows.
2. Identify the loop-closing edge.
3. Verify the correct relationship with the business owner.
4. Fix the erroneous relationship inside a controlled transaction.
5. Re-run the hierarchical query over the appropriate scope.
6. Confirm no cycles remain and the data is business-correct.

### 8.2. Fixing the demo data

If business rules confirm Alice should be the root, Alice's manager can be set to NULL:

```sql
UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;

COMMIT;
```

Tree after the fix:

```text
Alice (1)
  |
  +---- Bob (2)
  |       |
  |       +---- Carol (3)
  |
  +---- David (4)
```

This is correct only under the assumption that Alice is the root. In a real system, an authorized owner must confirm the right relationship; never set NULL just to make query errors go away.

### 8.3. Re-checking

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level,
       CONNECT_BY_ISCYCLE AS cycle_flag,
       SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

With the fixed data, Alice is the root; Bob and David are direct reports; Carol reports to Bob. Rows in this tree have cycle flag 0. If another disconnected cyclic component exists, START WITH manager_id IS NULL may not find it.

## 9. Preventing Cycles When Changing a Manager

### 9.1. Principle

Suppose you want to change the manager of employee `:emp_id` to `:new_manager_id`. The change will create a cycle if the new manager is the employee themselves or lies within that employee's subordinate subtree.

Example:
- Bob is currently a subordinate of Alice.
- You cannot set Alice to report to Bob while keeping Bob reporting to Alice.
- Doing so creates Alice → Bob → Alice.

### 9.2. Finding the current subordinate subtree

```sql
SELECT emp_id,
       emp_name,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH emp_id = :emp_id
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

The result set contains the target employee and subordinates reachable from that employee under current relationships. If `:new_manager_id` appears in this set, assigning that person as the new manager will create a loop.

Check:

```sql
SELECT COUNT(*) AS would_create_cycle
FROM (
    SELECT emp_id
    FROM   demo_org_employees
    START WITH emp_id = :emp_id
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
) descendants
WHERE descendants.emp_id = :new_manager_id;
```

A count greater than 0 means the new manager lies inside the current subordinate branch. This is an illustrative logic check; an application also needs to verify that the manager exists, check for pre-existing cycles, enforce permissions, and handle concurrent changes.

### 9.3. Direct self-reference

The condition `:new_manager_id <> :emp_id` prevents an employee from managing themselves, but does not prevent multi-row cycles. Path checking is still required.

### 9.4. Caution with concurrent transactions

A SELECT check before an UPDATE may be insufficient if multiple sessions modify relationships concurrently. Two transactions can both validate against the old state and then commit updates that form a new cycle.

Real systems must synchronize tree modifications using transactions, appropriate locking, or business mechanisms that serialize related changes. Implementation depends on the schema and concurrency requirements.


## 13. Hands-On Practice

The exercises use `DEMO_ORG_EMPLOYEES` created in section 4.

### Exercise 1 — Traverse the tree after fixing

After Alice is the root:

```sql
SELECT emp_id,
       emp_name,
       manager_id,
       LEVEL AS hierarchy_level
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Expected: Alice level 1; Bob and David level 2; Carol level 3.

### Exercise 2 — Recreate the cycle

```sql
UPDATE demo_org_employees SET manager_id = 3 WHERE emp_id = 1;
UPDATE demo_org_employees SET manager_id = 1 WHERE emp_id = 2;
UPDATE demo_org_employees SET manager_id = 2 WHERE emp_id = 3;
COMMIT;
```

Run the query without NOCYCLE to observe ORA-01436, then re-run with NOCYCLE.

### Exercise 3 — Flag the row before the loop-closing edge

```sql
SELECT emp_id,
       emp_name,
       LEVEL,
       CONNECT_BY_ISCYCLE AS cycle_flag
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id
ORDER SIBLINGS BY emp_id;
```

Expected: Carol (3) has cycle flag 1.

### Exercise 4 — Filter the cycle flag with a CTE

```sql
WITH h AS (
    SELECT emp_id,
           emp_name,
           manager_id,
           LEVEL AS hierarchy_level,
           CONNECT_BY_ISCYCLE AS cycle_flag,
           SYS_CONNECT_BY_PATH(TO_CHAR(emp_id), '/') AS id_path
    FROM   demo_org_employees
    START WITH emp_id = 1
    CONNECT BY NOCYCLE PRIOR emp_id = manager_id
)
SELECT emp_id,
       emp_name,
       manager_id,
       hierarchy_level,
       id_path
FROM   h
WHERE  cycle_flag = 1;
```

Expected: Carol's row with path `/1/2/3`.

### Exercise 5 — Find the child row that is an ancestor

Use the query in section 5.2. Expected loop-closing edge is Carol → Alice.

### Exercise 6 — Test START WITH

```sql
SELECT emp_id,
       CONNECT_BY_ISCYCLE
FROM   demo_org_employees
START WITH manager_id IS NULL
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;
```

Expected: no rows when the cyclic component has no NULL-manager root. An empty result does not prove the table has no cycles.

### Exercise 7 — Investigate from all seeds

Omit START WITH and observe the different paths. Run only on the small demo table because output can repeat across many paths.

### Exercise 8 — Fix the cycle

If Alice should be the root:

```sql
UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;
COMMIT;
```

Re-run the query from the root and confirm cycle flag is 0 in that tree.

### Exercise 9 — Self-reference

In the demo schema, try setting manager_id equal to emp_id itself, observe NOCYCLE, then restore the data. Do not run on production tables.

### Exercise 10 — Check the FK

```sql
SELECT constraint_name,
       constraint_type,
       status,
       validated
FROM   user_constraints
WHERE  table_name = 'DEMO_ORG_EMPLOYEES'
ORDER  BY constraint_name;
```

Verify the PK and self-referencing FK; explain why the FK still allows multi-row cycles.

## 14. Common Misconceptions

**"NOCYCLE fixes bad data."** No. It only controls how the query stops loop-forming branches.

**"CONNECT_BY_ISCYCLE flags the repeated row."** It flags the current row that has a child which is an ancestor on the path.

**"Cycle flag 1 means that row manages itself."** No. A cycle can involve multiple rows.

**"Having a self-referencing FK makes cycles impossible."** An FK only ensures the parent key exists; it does not check paths.

**"START WITH manager_id IS NULL returning no rows means there is no cycle."** No. A cyclic component may lack a natural root.

**"NOCYCLE eliminates all duplicate rows."** No. It prevents loops along the same path, not across different paths.

**"CONNECT_BY_ISCYCLE can be used without NOCYCLE."** No. This pseudocolumn requires NOCYCLE.

**"DISTINCT can fix ORA-01436."** No. DISTINCT does not replace NOCYCLE and does not fix relationships.

**"Traversal direction does not affect which row is flagged."** Incorrect. PRIOR direction and seeds determine the ancestor path.

**"WHERE always filters before CONNECT BY."** Do not assume that; hierarchical queries have their own processing order.

## 15. Self-Check Questions

1. What is a cycle in hierarchical data?
2. How does a self-loop differ from a multi-row cycle?
3. Which direction does `CONNECT BY PRIOR emp_id = manager_id` traverse?
4. Does NOCYCLE modify data in the table?
5. Does CONNECT_BY_ISCYCLE=1 flag the current row or the repeated ancestor row?
6. Why does this pseudocolumn require NOCYCLE?
7. With path 1 → 2 → 3 → 1, which row is flagged when traversing downward from 1?
8. Which case can START WITH manager_id IS NULL miss?
9. If START WITH is omitted, how does Oracle treat rows?
10. Why is NOCYCLE not equivalent to DISTINCT?
11. What does a self-referencing FK protect against, and what does it not protect against?
12. How does SYS_CONNECT_BY_PATH aid investigation?
13. How do you identify the loop-closing child row from a cycle-flagged row?
14. Can reversing traversal direction change which row gets flagged?
15. Why shouldn't you fix manager_id based solely on the flagged row?
16. Why must a pre-UPDATE check account for concurrent transactions?
17. How does a cycle differ from orphan data?
18. Is a node appearing in two branches always a cycle?
19. How does ORDER SIBLINGS BY differ from ORDER BY?
20. What should be re-checked after fixing the data?

**Suggested answers:**

1. A parent–child path returning to a row that already appeared in the same path.
2. A self-loop is a row pointing to itself; a multi-row cycle passes through intermediate rows.
3. From parent down to child.
4. No.
5. The current row that has an ancestor as a child.
6. Oracle requires NOCYCLE when using this pseudocolumn.
7. Row 3, because its next child 1 is already an ancestor.
8. A cyclic component where no row has a NULL manager.
9. Every row can be treated as a root.
10. NOCYCLE prevents looping along a path; DISTINCT removes duplicate rows in output.
11. An FK ensures the parent key exists; it does not ensure the graph is acyclic.
12. Builds the path from the root to the current row.
13. Join direct child rows and check whether the child ID appears in the path.
14. Yes; traversal direction changes the ancestor path.
15. The flagged row is the node before the loop-closing edge; the erroneous relationship must be verified.
16. Two transactions can both validate against the old state and then create a cycle upon updating.
17. A cycle returns to an ancestor; orphan data points to a non-existent key.
18. No; it must be on the same ancestor path to be a cycle.
19. ORDER SIBLINGS BY sorts siblings within the tree; ORDER BY can flatten the result set.
20. Check the full required seed scope, not just one root, and confirm the business relationship is right.

## 16. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Hierarchical Queries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Hierarchical-Queries.html): START WITH, CONNECT BY, and NOCYCLE.
- [Oracle Database SQL Language Reference — Hierarchical Query Pseudocolumns](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Hierarchical-Query-Pseudocolumns.html): LEVEL, CONNECT_BY_ISCYCLE, CONNECT_BY_ISLEAF, and CONNECT_BY_ROOT.
- [Oracle Database SQL Language Reference — SYS_CONNECT_BY_PATH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SYS_CONNECT_BY_PATH.html): building hierarchical paths.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT syntax and hierarchical queries.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): relational model, constraints, and data integrity.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/oracle/oracle-database/19/errmg/): Oracle error message lookup, including ORA-01436.

When investigating hierarchical data, determine the `PRIOR` direction, choose appropriate seeds with `START WITH`, add `NOCYCLE` so the query does not halt on a loop, and use `CONNECT_BY_ISCYCLE` to locate the row immediately preceding the loop-closing edge. Then trace the path, verify the proper relationship with the business owner, and repair in a controlled manner. **NOCYCLE is a tool for querying and detecting loops; ultimate integrity must still be guaranteed through sound data and update procedures.**


## 10. Related Hierarchical Pseudocolumns

| Pseudocolumn | Meaning |
| --- | --- |
| `LEVEL` | Depth of the row in the tree; root is level 1 |
| `CONNECT_BY_ISCYCLE` | 1 if the current row has a child that is an ancestor; requires NOCYCLE |
| `CONNECT_BY_ISLEAF` | 1 if the current row is a leaf under the CONNECT BY condition |
| `CONNECT_BY_ROOT expression` | Value of the expression at the root row of the path |

`SYS_CONNECT_BY_PATH(column, delimiter)` creates a path from the root to the current row, useful for investigation and breadcrumb display.

`ORDER SIBLINGS BY` sorts rows sharing the same parent while preserving tree structure. A regular `ORDER BY` can flatten the entire result set and lose the desired branch presentation.

Do not confuse:
- `CONNECT_BY_ISCYCLE` detects an edge that would return to an ancestor.
- `CONNECT_BY_ISLEAF` indicates whether a row has children under the CONNECT BY condition.
- `LEVEL` indicates depth, not the number of cycles.

## 11. Performance and Operations

### 11.1. NOCYCLE still traverses data

`NOCYCLE` does not make a hierarchical query free. Oracle still searches for child rows and tracks the path to detect repeats.

In an employee model, an index on `MANAGER_ID` can help locate subordinates when traversing downward from managers. With composite keys, indexes should match the components in the CONNECT BY condition. Inspect workload, statistics, and execution plans before creating indexes.

### 11.2. NOCYCLE does not eliminate duplicate paths

If a row can be reached via multiple different paths, it can still appear multiple times in the output. NOCYCLE only prevents ancestor loops along the same path; it is not a global DISTINCT.

Do not mechanically add DISTINCT to mask multi-row results. First understand the relationship model and cardinality.

### 11.3. CONNECT BY condition must be complete

If the hierarchical key is a composite key, match all identifying components completely:

```sql
CONNECT BY NOCYCLE
       PRIOR tenant_id = tenant_id
   AND PRIOR node_code = parent_node_code
```

This is an illustrative template; column names and relationship direction must match the actual schema. Omitting tenant or a key component can cross-join data and create spurious paths.

### 11.4. Viewing the execution plan

```sql
EXPLAIN PLAN FOR
SELECT emp_id,
       emp_name,
       LEVEL,
       CONNECT_BY_ISCYCLE
FROM   demo_org_employees
START WITH emp_id = 1
CONNECT BY NOCYCLE PRIOR emp_id = manager_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows the estimated plan. When investigating real queries, inspect the cursor plan and appropriate runtime statistics. Do not extrapolate production performance from a very small demo table.

### 11.5. Avoid arbitrary broad diagnostics

Omitting `START WITH` or treating every row as a root can generate many paths and multiply intermediate rows. On large tables, narrow scope by schema/tenant/object, use suspected seeds, monitor the execution plan, and avoid returning long paths if only the cycle flag is needed.

## 12. Cycle Investigation Workflow in Real Systems

1. **Identify the relationship:** which column identifies a node, which references the parent, and the desired traversal direction.
2. **Check constraints:** is the FK ENABLE/VALIDATE; can orphan data exist?
3. **Choose seeds:** valid roots, objects reporting errors, or a node belonging to the suspected component.
4. **Run with NOCYCLE:** retrieve LEVEL and CONNECT_BY_ISCYCLE.
5. **Record paths:** use SYS_CONNECT_BY_PATH when tracing is needed.
6. **Find the loop-closing edge:** check whether a child of the flagged row is an ancestor in the path.
7. **Verify with business owners:** determine the correct relationship.
8. **Fix in a controlled way:** update the wrong edge inside an appropriate transaction/audit.
9. **Re-run the query:** confirm no cycles remain in the checked scope.
10. **Prevent recurrence:** validate before changing relationships and synchronize concurrent updates.

### 12.1. Inspecting data before fixing

```sql
SELECT emp_id,
       emp_name,
       manager_id
FROM   demo_org_employees
WHERE  emp_id IN (1, 2, 3);
```

This is a read-only query. For real data, preserve history per audit/backup policy; do not rely solely on on-screen output.

### 12.2. Using transactions for DML

```sql
SAVEPOINT before_cycle_fix;

UPDATE demo_org_employees
SET manager_id = NULL
WHERE emp_id = 1;

-- Re-run the hierarchical query to verify.

-- COMMIT only after confirming the relationship is correct.
-- If you need to discard the demo change:
ROLLBACK TO before_cycle_fix;
```

`SAVEPOINT` and `ROLLBACK TO` apply to uncommitted DML. Do not run DDL between steps if relying on a savepoint because Oracle DDL performs an implicit commit.
