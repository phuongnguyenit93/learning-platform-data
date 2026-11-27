# CROSS JOIN, Self Joins, and Row Multiplication Risks

`CROSS JOIN` produces a Cartesian product between two row sets: every row on the left is combined with every row on the right. A self join joins a table to itself, typically to represent same-entity relationships such as employees and managers, parent-child categories, or comparisons among records within the same group. Both techniques are useful, but without controlling row counts and join conditions, result sets can grow rapidly or multiply unintentionally.

In the `DATABASE_MYSQL` module, understanding join cardinality helps you write accurate queries, read `EXPLAIN`, select indexes, and avoid reporting errors caused by duplicate counting. This lesson uses MySQL 8.x and InnoDB.

## Objectives

After this lesson, you will be able to:

- Explain Cartesian products and predict the row count of a `CROSS JOIN`.
- Use `CROSS JOIN` to generate all combinations when business logic genuinely requires them.
- Write self joins using aliases to connect rows within the same table.
- Distinguish parent-child, same-group, and record-pair comparison self joins.
- Identify why a join causes unexpected row growth.
- Avoid double counting when a join key matches multiple rows on both sides.
- Use `EXPLAIN`, group statistics, and indexes to verify cardinality.
- Know when to use a recursive CTE instead of a fixed chain of self joins.

## 1. CROSS JOIN Creates a Cartesian Product

`CROSS JOIN` combines every row of the first table with every row of the second table. If table A has (m) rows and table B has (n) rows, the unfiltered result has:

\[
m \times n
\]

rows. If either input has zero rows, the result also has zero rows.

Syntax:

```sql
SELECT column_list
FROM table_a
CROSS JOIN table_b;
```

Small example:

```sql
CREATE TABLE shirt_color (
    color_code VARCHAR(20) NOT NULL PRIMARY KEY
);

CREATE TABLE shirt_size (
    size_code VARCHAR(10) NOT NULL PRIMARY KEY
);

INSERT INTO shirt_color VALUES ('BLACK'), ('WHITE'), ('BLUE');
INSERT INTO shirt_size VALUES ('S'), ('M'), ('L'), ('XL');

SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
ORDER BY c.color_code, s.size_code;
```

The colors table has 3 rows and the sizes table has 4 rows, so the result has (3 \times 4 = 12) combinations. This is the intended behavior if a store needs to generate the list of all color-size variants before deciding which variants are actually sold.

### 1.1. Intentional CROSS JOIN

`CROSS JOIN` is useful when you need every combination across small, independent sets:

- Colors × sizes to build a product variant matrix.
- Dates × time slots to generate a schedule template.
- Regions × report types to generate a list of jobs to run.
- Test parameters × scenarios to build a test matrix.

Example generating a region and sales channel matrix:

```sql
SELECT
    r.region_code,
    c.channel_code
FROM sales_region AS r
CROSS JOIN sales_channel AS c
ORDER BY r.region_code, c.channel_code;
```

With 20 regions and 8 channels, the query produces 160 combinations. Before running on larger sets, estimate the product and confirm whether the application truly needs every combination.

### 1.2. CROSS JOIN Followed by WHERE Filtering

You can filter a Cartesian product after forming the logical combinations:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
WHERE c.color_code <> 'WHITE'
  AND s.size_code <> 'XL';
```

The query still describes all color-size combinations and then excludes unwanted ones. For a key-based join relationship, write `INNER JOIN ... ON ...` to express the join condition directly; do not use `CROSS JOIN` as a roundabout way of writing an unconstrained join.

## 2. Predicting and Checking CROSS JOIN Row Counts

Before running a large `CROSS JOIN`, count the rows in each input:

```sql
SELECT COUNT(*) AS color_count FROM shirt_color;
SELECT COUNT(*) AS size_count FROM shirt_size;
```

For two independent sets, the unfiltered result row count equals the product of the two counts. You can estimate it directly:

```sql
SELECT
    (SELECT COUNT(*) FROM shirt_color) AS color_count,
    (SELECT COUNT(*) FROM shirt_size) AS size_count,
    (SELECT COUNT(*) FROM shirt_color)
      * (SELECT COUNT(*) FROM shirt_size) AS expected_combinations;
```

With large tables, the product can easily exceed processing capacity or application result transfer limits. For example, 100,000 rows combined with 50,000 rows yields 5 billion pairs before filtering. Even if each result row has only a few columns, CPU, I/O, temporary memory, sorting, and network costs can still be enormous.

### 2.1. LIMIT Does Not Replace Controlling Cardinality

Adding `LIMIT 100` only restricts how many rows are returned to the client:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
LIMIT 100;
```

That does not justify a Cartesian product design if the application actually needs a conditional relationship. Depending on the execution plan and processing order, MySQL may stop early once enough rows are found for some queries, but `LIMIT` does not guarantee avoiding the cost of preceding joins, sorts, or filters. Fix the root cardinality issue first.

### 2.2. CROSS JOIN with an Empty Table

If either side is empty, no pairs are produced:

```sql
SELECT c.color_code, s.size_code
FROM shirt_color AS c
CROSS JOIN shirt_size AS s
WHERE s.size_code = 'XXL';
```

If there is no `XXL` size, the result is empty. This differs from an aggregate query over an empty set (which may still return one summary row) versus a query returning row pairs directly.

## 3. What Is a Self Join?

A self join joins a table with itself. Inside the statement, you must use distinct aliases to differentiate the role of each occurrence:

```sql
SELECT ...
FROM employees AS employee
JOIN employees AS manager
  ON employee.manager_id = manager.employee_id;
```

Both aliases reference the `employees` table, but one alias represents the employee and the other represents the manager. A self join does not create a new kind of table; it simply references the same table twice in one query.

Self joins are commonly used to:

- Find each employee's direct manager.
- List employees in the same department.
- Find pairs of products with matching attributes or duplicate record pairs.
- Compare one version of a record with another version in the same table.
- Query parent-child relationships stored via a self-referencing foreign key.

## 4. Self Join Example: Employees and Managers

An employees table can store `manager_id` referencing `employee_id` of another row in the same table. Top-level executives may have no manager, so `manager_id` allows `NULL`.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    employee_name VARCHAR(120) NOT NULL,
    department_id BIGINT UNSIGNED NOT NULL,
    manager_id BIGINT UNSIGNED NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_manager (manager_id),
    KEY idx_employees_department (department_id),
    CONSTRAINT fk_employees_manager
        FOREIGN KEY (manager_id)
        REFERENCES employees (employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO employees
    (employee_id, employee_name, department_id, manager_id)
VALUES
    (1, 'Lan', 10, NULL),
    (2, 'Minh', 10, 1),
    (3, 'Huy', 10, 1),
    (4, 'Trang', 20, NULL),
    (5, 'Khanh', 20, 4),
    (6, 'Phuc', 20, 4),
    (7, 'An', 10, 2);
```

In the sample data, Lan and Trang are senior managers; Minh and Huy report to Lan; Khanh and Phuc report to Trang; An reports to Minh.

### 4.1. INNER Self Join: Only Employees with a Manager

```sql
SELECT
    e.employee_id,
    e.employee_name AS employee_name,
    m.employee_name AS manager_name
FROM employees AS e
INNER JOIN employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

`e` is the employee, and `m` is the manager. The join condition uses the primary key of the manager alias to match the `manager_id` foreign key of the employee alias. Because it is an `INNER JOIN`, Lan and Trang are excluded from the result since their `manager_id` is `NULL`.

### 4.2. LEFT Self Join: Preserving Employees Without a Manager

If you also want to display top-level executives:

```sql
SELECT
    e.employee_id,
    e.employee_name AS employee_name,
    m.employee_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id
ORDER BY e.employee_id;
```

With `LEFT JOIN`, every employee on the `e` side appears. If no manager matches, columns from alias `m` are `NULL`. Do not place `m.employee_name IS NOT NULL` in `WHERE` if your goal is to keep employees without managers, because that condition drops null-extended rows and makes the result behave like an inner join.

### 4.3. Counting Direct Reports for Each Manager

```sql
SELECT
    m.employee_id,
    m.employee_name AS manager_name,
    COUNT(e.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS e
    ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.employee_name
ORDER BY m.employee_id;
```

Use `COUNT(e.employee_id)` because that column is the primary key of the employee table on the right side. Managers without direct reports still appear with a count of 0. If you used `COUNT(*)`, the padded row generated by `LEFT JOIN` for someone with no direct reports would be counted as 1.

## 5. Self Join to Find Pairs in the Same Group

Another case is finding employees in the same department. The `employees` table is used twice, with each alias representing one member of the pair:

```sql
SELECT
    e1.employee_id AS employee_1_id,
    e1.employee_name AS employee_1,
    e2.employee_id AS employee_2_id,
    e2.employee_name AS employee_2,
    e1.department_id
FROM employees AS e1
INNER JOIN employees AS e2
    ON e2.department_id = e1.department_id
   AND e1.employee_id < e2.employee_id
ORDER BY e1.department_id, e1.employee_id, e2.employee_id;
```

The condition `e1.employee_id < e2.employee_id` has two effects:

- Excludes pairing an employee with themselves.
- Keeps only one direction of each pair, such as `(Minh, Huy)`, without also returning `(Huy, Minh)`.

If a department has `k` employees, the number of unordered pairs is:

\[
\frac{k(k-1)}{2}
\]

For `k = 4`, the result has 6 pairs. If you used `e1.employee_id <> e2.employee_id`, each pair would appear twice because both `(A, B)` and `(B, A)` are kept.

### 5.1. Why an Underspecified Join Condition Generates Extra Rows

If you only write:

```sql
SELECT e1.employee_name, e2.employee_name
FROM employees AS e1
JOIN employees AS e2
    ON e1.department_id = e2.department_id;
```

every employee in a department pairs with every other employee in the same department, including themselves. A department with `k` people produces `k × k` rows. This is not a syntax error; it is the exact result of the join condition as written, though usually not what the user intended.

If you want distinct pairs, add the condition excluding self-pairs and reversed pairs as in the previous example. If you want directional comparisons, keeping `<>` may make sense, but understand that the row count doubles.

## 6. Row Multiplication Risk in JOINs

The row count after a join depends on the number of matching rows on both sides. For a given join key value, if the left side has `m` rows and the right side has `n` rows with that key, the join can produce `m × n` rows for that key.

For example, if a customer has 3 orders and each order has 4 line items, joining customers directly to both orders and line items can produce 12 rows for that customer. That may be the right result at the detail grain, but if you then sum order totals across those 12 rows, each order gets counted once per line item.

### 6.1. Multiplication Example When Joining Two Multi-Row Relationships

```sql
CREATE TABLE customer_tag (
    customer_id BIGINT UNSIGNED NOT NULL,
    tag_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (customer_id, tag_name)
) ENGINE=InnoDB;

CREATE TABLE customer_channel (
    customer_id BIGINT UNSIGNED NOT NULL,
    channel_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (customer_id, channel_name)
) ENGINE=InnoDB;

INSERT INTO customer_tag VALUES
    (1, 'VIP'), (1, 'LOYAL'), (1, 'NEWSLETTER');

INSERT INTO customer_channel VALUES
    (1, 'WEB'), (1, 'MOBILE');
```

Joining the two tables solely on `customer_id`:

```sql
SELECT t.customer_id, t.tag_name, c.channel_name
FROM customer_tag AS t
JOIN customer_channel AS c
    ON c.customer_id = t.customer_id
WHERE t.customer_id = 1;
```

Customer 1 has 3 tags and 2 channels, so the result has 6 rows. Each tag appears with both channels. If the goal is to display every tag-channel combination, this is correct; if you only wanted a list of tags or a tag count, this join inflates the row count unintentionally.

### 6.2. Avoiding Duplicated Sums

Suppose `orders` stores the order-level total, while `order_items` has multiple lines per order. The following query risks summing order totals multiple times:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS total_amount
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

If an order has 3 line items, `o.total_amount` appears 3 times after the join. Do not solve this with `SUM(DISTINCT o.total_amount)`, because two different orders can have the exact same total amount; `DISTINCT` would drop a legitimate value.

One approach is to aggregate at the order grain before joining with detail relationships, or use `EXISTS` if you only need to check whether an order has line items:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS total_amount
FROM orders AS o
WHERE EXISTS (
    SELECT 1
    FROM order_items AS i
    WHERE i.order_id = o.order_id
)
GROUP BY o.customer_id;
```

If you need to include orders without line items as well, drop the `EXISTS` filter or handle it per business rules. If you need line-item-level metrics, aggregate `order_items` by `order_id` first and then join the grouped result to `orders`.

### 6.3. Pre-Aggregating Each Side Before Joining

When combining multiple independent child tables, consider aggregating each table to the target grain before joining:

```sql
WITH item_totals AS (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
),
payment_totals AS (
    SELECT order_id, SUM(paid_amount) AS paid_total
    FROM payments
    GROUP BY order_id
)
SELECT
    o.order_id,
    o.total_amount,
    it.item_total,
    pt.paid_total
FROM orders AS o
LEFT JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
    ON pt.order_id = o.order_id;
```

Each CTE has at most one row per `order_id` because it groups by the order key. When joined to `orders`, rows are not multiplied by multiple line items or multiple independent payments. Decide how to handle `NULL` values and orders without items or payments in downstream display or calculations.

## 7. Accidental CROSS JOIN vs. Underspecified INNER JOIN

A common mistake is listing two tables in `FROM` while forgetting the join condition:

```sql
-- Produces a Cartesian product; usually a bug if the goal is a key-based join.
SELECT o.order_id, c.customer_name
FROM orders AS o, customers AS c;
```

In MySQL, comma-separated table syntax without a linking condition produces a Cartesian product. Write it explicitly instead:

```sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
```

Writing explicit `JOIN` syntax lets reviewers immediately see the join condition. With `CROSS JOIN`, omitting a join condition is intentional and should be clearly documented in code and specifications.

### 7.1. Incomplete Join Conditions

In a multi-tenant model, a `project_id` might only be unique within each tenant. If the real key is `(tenant_id, project_id)` but a query joins only on `project_id`, rows from another tenant can mismatch or multiply.

```sql
-- Missing part of the composite key: can match the wrong tenant.
SELECT t.task_id, p.project_name
FROM project_task AS t
JOIN tenant_project AS p
    ON p.project_id = t.project_id;

-- Use all key components.
SELECT t.task_id, p.project_name
FROM project_task AS t
JOIN tenant_project AS p
    ON p.tenant_id = t.tenant_id
   AND p.project_id = t.project_id;
```

Join on the full business/foreign key, not just on one column that happens to look unique in sample data.

## 8. Self Joins with Hierarchical Data

The `employees.manager_id` pattern is an adjacency list: each row stores the ID of its direct parent. A simple self join retrieves one management level. If you need a fixed number of levels, you can join the table multiple times:

```sql
SELECT
    e.employee_name AS employee_name,
    m.employee_name AS manager_name,
    d.employee_name AS department_head_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id
LEFT JOIN employees AS d
    ON d.employee_id = m.manager_id;
```

The query above traverses up at most two levels. It does not automatically walk every level of a tree. When depth is arbitrary, MySQL 8.0 supports recursive CTEs:

```sql
WITH RECURSIVE employee_chain AS (
    SELECT
        employee_id,
        employee_name,
        manager_id,
        0 AS depth
    FROM employees
    WHERE employee_id = 7

    UNION ALL

    SELECT
        manager.employee_id,
        manager.employee_name,
        manager.manager_id,
        chain.depth + 1
    FROM employees AS manager
    JOIN employee_chain AS chain
        ON manager.employee_id = chain.manager_id
)
SELECT employee_id, employee_name, manager_id, depth
FROM employee_chain
ORDER BY depth;
```

The CTE starts at employee 7 and walks upward to managers, stopping when `manager_id` is `NULL` or no matching row remains. Hierarchical data must prevent cycles, such as an employee managing themselves or A managing B while B manages A. Recursive CTEs have recursion depth limits and require an appropriate cycle-detection strategy if data validity is not guaranteed.

If you only need a single level of relationship, a self join is usually simpler and easier to optimize. Use a recursive CTE when traversing an unbounded number of levels.

## 9. NULL in JOIN Conditions

Standard join conditions using `=` do not match two `NULL` values:

```sql
SELECT a.id, b.id
FROM table_a AS a
JOIN table_b AS b
    ON a.optional_code = b.optional_code;
```

If both `a.optional_code` and `b.optional_code` are `NULL`, the comparison evaluates to `UNKNOWN`, not `TRUE`, so the two rows do not match. In most foreign key relationships, this is the intended behavior because `NULL` indicates no reference key exists.

If business logic genuinely requires treating two `NULL`s as a match, MySQL provides the null-safe equality operator `<=>`:

```sql
SELECT a.id, b.id
FROM table_a AS a
JOIN table_b AS b
    ON a.optional_code <=> b.optional_code;
```

Be careful: if there are `p` null rows in A and `q` null rows in B, `<=>` pairs them into `p × q` rows. Do not use `<=>` casually on keys if null rows do not represent the same business entity.

## 10. Indexes and Execution Plans

### 10.1. Indexes for Self Joins

For an employee-manager self join:

```sql
ON m.employee_id = e.manager_id
```

`employee_id` is the primary key, while `manager_id` should have an index to look up direct reports for a manager. The `idx_employees_manager(manager_id)` index in the example supports finding subordinates and counting direct reports.

For a same-department self join, an index `(department_id, employee_id)` can support finding rows in the same department and comparing IDs:

```sql
CREATE INDEX idx_employees_department_employee
ON employees (department_id, employee_id);
```

Do not add an index merely because a column appears in `ON`. Consider selectivity, row count, query frequency, write overhead, and existing indexes. The primary key or an existing composite index may already cover the query.

### 10.2. Reading EXPLAIN

Inspect the plan of a self join:

```sql
EXPLAIN
SELECT
    e.employee_name,
    m.employee_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON m.employee_id = e.manager_id;
```

Inspect the plan of a same-department pair query:

```sql
EXPLAIN FORMAT=TREE
SELECT e1.employee_id, e2.employee_id
FROM employees AS e1
JOIN employees AS e2
    ON e2.department_id = e1.department_id
   AND e1.employee_id < e2.employee_id;
```

Observe:

- Which table/alias is read first.
- Which `key` or access path is chosen.
- Estimated row counts at each step.
- Which conditions act as join conditions versus filters.
- Whether sorting, materialization, or temporary tables occur.

In MySQL 8.0.18 and later, `EXPLAIN ANALYZE` reports actual row counts and execution times for each iterator. This command actually executes the query; only run it on safe read queries against lab or staging data when cost is not yet understood.

## 11. How to Detect Unexpected Row Growth from a JOIN

When a result has more rows than expected, check in this order:

1. Count the rows in each table before joining.
2. Verify whether the join key is unique on the side you expect to be one-to-one.
3. Count rows per key on both sides.
4. Confirm the join condition includes every component of any composite key.
5. Check whether a self join condition excludes pairing a row with itself.
6. Check whether you need ordered pairs or only one unordered pair.
7. Clarify the result grain: one row per customer, per order, per line item, or per pair.
8. Aggregate data at the proper grain before joining multiple independent child tables.
9. Use `EXPLAIN` to verify estimated cardinality and access paths.

Example checking row counts per key:

```sql
SELECT customer_id, COUNT(*) AS rows_per_customer
FROM customer_tag
GROUP BY customer_id
ORDER BY rows_per_customer DESC;

SELECT customer_id, COUNT(*) AS rows_per_customer
FROM customer_channel
GROUP BY customer_id
ORDER BY rows_per_customer DESC;
```

If a customer has 3 tags and 2 channels, joining these two sets by `customer_id` produces 6 combinations. That is multiplication by each key's cardinality, not a random MySQL bug.

## 12. CROSS JOIN and Self Joins in Reporting

Before placing a query into a report or API, define the output grain. For example:

| Requirement | Desired Grain | Appropriate Approach |
|---|---|---|
| List of all color-size combinations | One row per color-size pair | `CROSS JOIN` two small sets |
| List of employees and direct managers | One row per employee | Self `LEFT JOIN` |
| Count of direct reports | One row per manager | Self `LEFT JOIN` + `COUNT(child.id)` |
| Distinct employee pairs in the same department | One row per unordered pair | Self join with `id < other_id` |
| All customer tag-channel combinations | One row per tag-channel pair | Join both sets by customer; expect the product |
| Total spend per customer from orders and line items | One row per customer | Aggregate at the right grain before joining |

If the grain is not defined upfront, `COUNT`, `SUM`, `AVG`, or pagination can yield wrong results even though the SQL syntax is completely valid.

## 13. Hands-On Exercises

Run these in a dedicated lab database with `shirt_color`, `shirt_size`, `employees`, `customer_tag`, and `customer_channel`:

1. Run a `CROSS JOIN` of colors and sizes; verify the row count equals the product of the two input counts.
2. Insert a new size and verify the number of combinations increases by exactly the current number of colors.
3. Try a `CROSS JOIN` with an empty input set; verify the result has zero rows.
4. Write a self `INNER JOIN` to get employees and their direct managers; explain why top-level executives do not appear.
5. Rewrite it using `LEFT JOIN` to keep employees without managers; count direct reports using `COUNT(employee_id)` on the child side.
6. Write a self join query listing employees in the same department; compare `<>` and `<` to observe reversed pairs and row counts.
7. Calculate the expected pair count per department using `k * (k - 1) / 2`, then compare it against the self join query using `<`.
8. Join `customer_tag` with `customer_channel` on `customer_id`; explain why a customer with 3 tags and 2 channels generates 6 rows.
9. Try counting tags after joining channels; compare with counting directly from `customer_tag` and explain the duplication.
10. Write a query summing order totals while joining `order_items`; fix the query using `EXISTS` or an aggregated CTE to prevent double-summing.
11. Run `EXPLAIN` and `EXPLAIN FORMAT=TREE` on the self join queries; inspect indexes on `manager_id` and `(department_id, employee_id)`.
12. Create a table with a composite tenant-project key; test a join omitting `tenant_id`, then add the full condition and compare results.
13. Test joining two nullable columns with `=` and `<=>`; insert multiple `NULL` rows on both sides to observe the row multiplication risk.

You have completed this lesson when you can predict row counts before running a join, write self joins with proper alias roles, and explain why an aggregation query suffers from data duplication.

## 14. Key Principles to Remember

- `CROSS JOIN` produces all row pairs; unfiltered row count equals the product of the two input cardinalities.
- Only use `CROSS JOIN` when every combination is genuinely meaningful; estimate expected row counts beforehand.
- A self join uses the same table multiple times with distinct aliases; aliases clarify each side's role.
- For parent-child relationships, `INNER JOIN` drops rows without a parent; `LEFT JOIN` keeps them with `NULL` in parent columns.
- Use `COUNT(child.primary_key)` to count child rows after a `LEFT JOIN`, avoiding counting padded rows with `COUNT(*)`.
- A group-based self join can produce `k * k` rows; use `id < other_id` when you need each unordered pair once.
- When both sides have multiple rows per key, results for that key can scale as `m × n`.
- Join on the full composite key; never assume a single component column is unique if the schema does not guarantee it.
- Aggregate each child table to the right grain before joining if you want to avoid duplicated metrics.
- Check indexes on join columns and use `EXPLAIN` to understand cardinality and access paths.
- Use a recursive CTE for trees with arbitrary depth; chained self joins only suit fixed depths.
- The `=` operator does not match two `NULL` values; `<=>` can cross-match many `NULL` rows into a large product, so only use it when business logic requires it.
