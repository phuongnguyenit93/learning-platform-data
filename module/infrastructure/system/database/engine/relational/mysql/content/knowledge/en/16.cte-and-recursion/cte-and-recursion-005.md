# Recursive CTE Column Data Types and the Risk of Data Truncation

In a recursive query, each iteration can produce values that are longer or larger than the previous iteration. For example, when traversing a department tree, a `path` column may append the name of each level; when computing a running total, a numeric column may grow at each step. If the CTE's column data types are inferred too narrowly from the initialization query, values in the recursive part can be truncated or trigger errors.

In MySQL 8.0 and later, the data types of columns in a recursive CTE are determined from the non-recursive part (the anchor member). MySQL does not automatically widen a column type simply because an expression in the recursive member produces a longer value. Therefore, you must design types right in the anchor using `CAST()` with sufficient length, precision, and signedness. This lesson belongs to the **DATABASE_MYSQL** module, focusing on type inference, truncation/overflow risks, and verification in tree queries.

## 1. Structure of a Recursive CTE

A recursive CTE typically has two parts:

- **Anchor member**: the initialization query that produces the initial rows. This is the non-recursive part.
- **Recursive member**: the query that references the CTE itself to generate subsequent rows.

General template:

```sql
WITH RECURSIVE hierarchy AS (
    -- Anchor member
    SELECT ...

    UNION ALL

    -- Recursive member
    SELECT ...
    FROM hierarchy AS h
    JOIN ...
)
SELECT *
FROM hierarchy;
```

MySQL starts with the anchor result, then uses the rows from the previous round to execute the recursive member and append new rows. The process continues until the recursive member produces no additional rows or hits the recursion limit.

Crucial rule about data types: **MySQL infers the names and types of the CTE columns from the anchor member**. The corresponding expressions in the recursive member must be compatible with those determined types. If the recursive member produces a longer string or a number exceeding the anchor type's range, the CTE type does not automatically widen to hold the new value.

## 2. Data Types Are Inferred from the Anchor Member

Consider a CTE with a `path` column:

```sql
WITH RECURSIVE paths AS (
    SELECT
        CAST(1 AS UNSIGNED) AS step_no,
        CAST('A' AS CHAR(1)) AS path

    UNION ALL

    SELECT step_no + 1, CONCAT(path, 'B')
    FROM paths
    WHERE step_no < 5
)
SELECT step_no, path
FROM paths;
```

The anchor produces `path` with type `CHAR(1)`. The recursive member appends the character `B`, but that does not cause the CTE column to automatically change to `CHAR(2)`, `CHAR(3)`, or a longer `VARCHAR`. Under an appropriate SQL mode, the query may raise a data truncation error; under a non-strict mode, the value may be truncated and generate a warning.

Do not rely on the expression length in the recursive member to guess the final type. Proactively declare the desired type right in the anchor:

```sql
WITH RECURSIVE paths AS (
    SELECT
        CAST(1 AS UNSIGNED) AS step_no,
        CAST('A' AS CHAR(20)) AS path

    UNION ALL

    SELECT step_no + 1, CONCAT(path, 'B')
    FROM paths
    WHERE step_no < 5
)
SELECT step_no, path
FROM paths;
```

In this example, the anchor allocates a maximum character capacity of 20 for the `path` column; the recursive member can concatenate strings within that limit.

### Types Are Not Unified by the Largest Value

In some regular `UNION` operations, authors may observe MySQL determining a common type across branches. For recursive CTEs, do not infer that the types of the anchor and recursive members will be merged into the widest sufficient type. MySQL's rule is that recursive CTE column types come from the anchor part; the recursive member does not widen that type.

Hence, treat the anchor as the place that declares the data type contract for the entire recursion process.

## 3. Practical Example: Traversing a Department Tree and Building Paths

Suppose there is a self-referencing employee table:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    employee_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_manager (manager_id),
    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (employee_id)
) ENGINE=InnoDB;
```

Each employee may have a manager; employees without a manager have `manager_id IS NULL`. We want to start from the root employee and traverse down through subordinate levels while building a name path string.

```sql
WITH RECURSIVE employee_tree (
    employee_id,
    manager_id,
    employee_name,
    path,
    depth
) AS (
    SELECT
        e.employee_id,
        e.manager_id,
        e.employee_name,
        CAST(e.employee_name AS CHAR(1000) CHARACTER SET utf8mb4) AS path,
        CAST(0 AS UNSIGNED) AS depth
    FROM employees AS e
    WHERE e.manager_id IS NULL

    UNION ALL

    SELECT
        child.employee_id,
        child.manager_id,
        child.employee_name,
        CONCAT(parent.path, ' / ', child.employee_name) AS path,
        parent.depth + 1 AS depth
    FROM employees AS child
    JOIN employee_tree AS parent
      ON child.manager_id = parent.employee_id
)
SELECT employee_id, manager_id, employee_name, path, depth
FROM employee_tree
ORDER BY path;
```

In the anchor:

- `CAST(e.employee_name AS CHAR(1000) CHARACTER SET utf8mb4)` defines `path` with a length and character set large enough to concatenate multiple levels of Unicode names.
- `CAST(0 AS UNSIGNED)` defines an unsigned integer type for `depth`.

In the recursive member:

- `CONCAT(parent.path, ' / ', child.employee_name)` appends the subordinate's name.
- `parent.depth + 1` increments depth at each level.

If you omit `CAST(... AS CHAR(1000))`, the type of `path` may be inferred from the length of `employee_name` in the anchor. When appending names in subsequent levels, the result exceeds that length and risks truncation or errors.

A length of 1000 is just an example. Estimate the maximum depth and name length according to business requirements; if paths can be longer, choose an appropriate limit or use a different storage model. `CHAR(N)` in this context defines the character type width of the CTE expression, not a guarantee that the actual path always has exactly N characters.

## 4. String Truncation and the Effect of SQL Mode

When a recursive member value is longer than the determined column type, MySQL can behave differently depending on `sql_mode` and execution context:

- With strict mode enabled, the query typically raises an error when a value is truncated instead of silently accepting it.
- When non-strict, the value may be truncated to the column width and emit a warning.

Check the SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

After a test query, you can inspect warnings:

```sql
SHOW WARNINGS;
```

Do not disable strict mode just to make a recursive query pass. If data is truncated, the resulting path or accumulated value will be wrong in ways that can be hard to spot. Fix the type in the anchor to represent the full range of values.

Note: `SHOW WARNINGS` must be run immediately after the statement being inspected; running another statement may alter the displayed warning list.

## 5. Choosing CHAR/VARCHAR Length for Recursive String Columns

When designing a string column in a recursive CTE, consider:

1. Maximum length of the value in the anchor.
2. Number of characters appended per iteration.
3. Maximum depth of the tree or number of iterations.
4. Character set: `utf8mb4` can use up to 4 bytes per character.
5. Data type limits and intermediate result size.

For example, if each node name is at most 120 characters, the path has at most 8 levels, and the separator is 3 characters long, you can estimate the required length using the formula:

\[
L_{max} = 8 \times 120 + 7 \times 3 = 981
\]

You can choose `CHAR(1000)` or another limit with safety headroom. If depth has no practical bound, do not pick an arbitrary number and assume it will always suffice.

For Unicode data, character length and byte count are not the same. `CHAR(N)`/`VARCHAR(N)` limits by number of characters; byte footprint also depends on the character set. A 1000-character `utf8mb4` string may require up to roughly 4000 bytes for character data.

## 6. Risk of Numeric Overflow and Precision Loss in Recursive Columns

Strings are not the only columns at risk of exceeding their type. Numeric columns can also exceed the anchor's data range:

- `TINYINT`/`SMALLINT` have small ranges; incrementing a counter over many rounds can overflow.
- `INT` may not suffice for large depths, cumulative sums, or large quantities.
- `DECIMAL(M,D)` has finite precision/scale; repeated addition or multiplication can produce values exceeding precision.
- `UNSIGNED` cannot store negative numbers; if recursion can decrement below 0, this type is unsuitable.

Example of a counter needing a sufficiently large type:

```sql
WITH RECURSIVE sequence_numbers (n) AS (
    SELECT CAST(1 AS UNSIGNED)

    UNION ALL

    SELECT n + 1
    FROM sequence_numbers
    WHERE n < 100
)
SELECT MAX(n) AS max_value
FROM sequence_numbers;
```

The anchor defines `n` as an unsigned integer. If the problem can generate negative values, use an appropriate signed type. If a cumulative sum can exceed `BIGINT`, consider `DECIMAL` with large enough precision or change the computation approach.

Example of a decimal running total:

```sql
WITH RECURSIVE running_totals (step_no, amount) AS (
    SELECT
        CAST(1 AS UNSIGNED),
        CAST(100.00 AS DECIMAL(20,2))

    UNION ALL

    SELECT
        step_no + 1,
        amount + CAST(25.50 AS DECIMAL(20,2))
    FROM running_totals
    WHERE step_no < 10
)
SELECT step_no, amount
FROM running_totals;
```

The anchor declares `amount` as `DECIMAL(20,2)` to provide enough precision for the addition steps. Choose precision according to the maximum value that can occur, not just the initial value.

## 7. CAST in the Anchor Member Is Where You Control Types

When a specific type is needed, cast the expression inside the anchor:

```sql
WITH RECURSIVE walk (node_id, label_path, total_weight) AS (
    SELECT
        root.node_id,
        CAST(root.label AS CHAR(2000)),
        CAST(root.weight AS DECIMAL(20,4))
    FROM graph_nodes AS root
    WHERE root.parent_id IS NULL

    UNION ALL

    SELECT
        child.node_id,
        CONCAT(w.label_path, '/', child.label),
        w.total_weight + child.weight
    FROM graph_nodes AS child
    JOIN walk AS w
      ON child.parent_id = w.node_id
)
SELECT node_id, label_path, total_weight
FROM walk;
```

In this example, the anchor determines:

- `node_id` follows the type of column `root.node_id`.
- `label_path` is a string with a width of 2000 characters.
- `total_weight` is `DECIMAL(20,4)`.

The recursive member must return expressions compatible with those three types. If the source type of `child.weight` differs, standardize the type in the schema or cast the expression appropriately. Do not cast only in the outermost SELECT, because by then the recursive calculation has already taken place using the CTE type determined from the anchor.

## 8. Column Names and Data Types Must Match Across Members

Declare the CTE column name list explicitly:

```sql
WITH RECURSIVE category_tree (
    category_id,
    parent_id,
    category_path,
    level_no
) AS (
    SELECT ...
    UNION ALL
    SELECT ...
)
SELECT * FROM category_tree;
```

The column list defines the order and meaning of each position. The anchor and recursive member branches must return the same number of columns in the exact corresponding order. If you accidentally swap `category_path` and `level_no`, MySQL will attempt positional type conversion and may raise an error or produce wrong results.

Example of what not to do:

```sql
WITH RECURSIVE bad_tree (node_id, node_path, depth) AS (
    SELECT id, CAST(name AS CHAR(500)), 0
    FROM nodes
    WHERE parent_id IS NULL

    UNION ALL

    -- Wrong expression order: depth comes before path
    SELECT child.id, parent.depth + 1,
           CONCAT(parent.node_path, '/', child.name)
    FROM nodes AS child
    JOIN bad_tree AS parent
      ON child.parent_id = parent.node_id
)
SELECT * FROM bad_tree;
```

In the recursive member, the second column returns a number instead of a string, and the third column returns a string instead of a number. Verify column ordering across all members before inspecting data logic.

## 9. Controlling Recursion Rounds and Path Length

A recursive CTE needs a clear termination condition. If data contains a cycle or the recursive condition does not converge toward a stop point, the query can hit the recursion limit and fail.

MySQL provides the `cte_max_recursion_depth` variable to limit recursion depth. A common default value is 1000; you can check it in the session:

```sql
SELECT @@SESSION.cte_max_recursion_depth;
```

You can increase the limit for the session if a valid problem requires greater depth:

```sql
SET SESSION cte_max_recursion_depth = 2000;
```

Do not raise the limit just to mask a data cycle or a missing termination condition. Verify the tree data, parent/child keys, and recursive logic first.

Besides limiting the number of rounds, you need a limit on path length. If each round appends a name, length grows with depth. A CTE might terminate properly yet still exceed string width if the anchor declared too small a size.

## 10. Avoiding Infinite Loops When Data Contains Cycles

A proper tree structure must have no cycles. However, self-referencing data can become corrupted if the application allows circular relationships, for example A is the parent of B, B is the parent of C, and C is the parent of A.

When traversing a graph that may contain cycles, track visited nodes. A simple example with numeric IDs can concatenate an ID path and check that the next node has not yet appeared:

```sql
WITH RECURSIVE graph_walk (node_id, visited_path, depth) AS (
    SELECT
        node_id,
        CAST(CONCAT('/', node_id, '/') AS CHAR(4096)),
        CAST(0 AS UNSIGNED)
    FROM graph_nodes
    WHERE node_id = 1

    UNION ALL

    SELECT
        edge.child_id,
        CONCAT(w.visited_path, edge.child_id, '/'),
        w.depth + 1
    FROM graph_edges AS edge
    JOIN graph_walk AS w
      ON edge.parent_id = w.node_id
    WHERE LOCATE(
        CONCAT('/', edge.child_id, '/'),
        w.visited_path
    ) = 0
      AND w.depth < 100
)
SELECT node_id, visited_path, depth
FROM graph_walk;
```

`visited_path` is cast to `CHAR(4096)` right in the anchor so there is enough space to store the path; `LOCATE()` checks whether the child ID has already appeared in the path; the condition `depth < 100` is an additional business safeguard. The example assumes numeric IDs delimited by `/`, avoiding confusing ID `1` with `11`.

For string IDs, path concatenation and lookup must handle escaping/delimiters so one ID is not mistaken for a substring of another ID. For large graphs or long paths, a string path may not be an efficient tracking method; consider a different data design and algorithm.

## 11. Inspecting Actual CTE Data Types

You can wrap the CTE in an outer query and use type/length inspection functions to verify the results:

```sql
WITH RECURSIVE paths AS (
    SELECT CAST('root' AS CHAR(100)) AS path

    UNION ALL

    SELECT CONCAT(path, '/child')
    FROM paths
    WHERE CHAR_LENGTH(path) < 30
)
SELECT
    path,
    CHAR_LENGTH(path) AS character_count,
    LENGTH(path) AS byte_count,
    CHARSET(path) AS character_set,
    COLLATION(path) AS collation_name
FROM paths;
```

Useful functions:

- `CHAR_LENGTH(expr)`: number of characters in the string.
- `LENGTH(expr)`: byte length of the string.
- `CHARSET(expr)`: character set of the expression.
- `COLLATION(expr)`: collation of the expression.
- `SHOW WARNINGS`: inspect warnings generated by the most recent statement.

If you need to verify exact SQL column types more precisely, you can create a view or test table from the CTE result and inspect metadata via `DESCRIBE`/`INFORMATION_SCHEMA.COLUMNS`. Do not infer type width solely from a handful of output data values.

## 12. Data Type Design Checklist for Recursive CTEs

Before deploying a recursive query, check:

1. Does the anchor member declare the exact number of columns and exact order?
2. Does each column's data type fit the largest value that can be generated?
3. Are string columns `CAST` with sufficient length in the anchor?
4. Do numeric columns use the proper signedness, integer width, or `DECIMAL` precision/scale?
5. Do string character set/collation match the concatenated data?
6. Does the recursive member return expressions compatible with the anchor types?
7. Is there any risk of truncation, rounding, or overflow?
8. Is strict SQL mode enabled to catch out-of-range data?
9. Are the termination condition and `cte_max_recursion_depth` appropriate?
10. Can the data contain cycles; if so, is there a visited-node detection mechanism?
11. Could the maximum depth cause paths to exceed the chosen character limit?
12. Has the query been tested with data deep and long enough to approach real-world limits?

## 13. Practice Exercises

1. Create a self-referencing `employees` table and write a recursive CTE traversing from the root manager down to subordinate employees.
2. Create a `path` column using `CAST(employee_name AS CHAR(20))`; use multi-level names to observe the truncation risk.
3. Increase the anchor width to `CHAR(1000)` and compare the results.
4. Remove the CAST in the anchor, inspect the result and `SHOW WARNINGS` under the current SQL mode.
5. Write a CTE counting levels using `TINYINT`, then test a larger type; explain the overflow risk.
6. Write a cumulative sum CTE using `DECIMAL(20,2)` and determine the precision required for the largest dataset.
7. Try swapping column order between the anchor and recursive members; read the error or output to understand positional column matching.
8. Create data with a cycle in an edge table and add `visited_path` along with a termination condition to prevent looping.
9. Experiment with adjusting `cte_max_recursion_depth` in the session; distinguish technical limits from business termination conditions.

You have completed this lesson when you can explain why recursive CTE data types are determined from the anchor member, cast strings/numbers wide enough right from initialization, recognize truncation or overflow risks, and control depth/cycles. Always design data types based on the maximum value that can arise throughout the entire recursion process, not just the initial value.
