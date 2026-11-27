# WITH and Common Table Expressions to Name Intermediate Result Sets

## Learning Objectives

After this lesson, you will be able to:

- Write a CTE using the WITH clause in MySQL.
- Name a subquery so SQL statements are easier to read and maintain.
- Declare output column names for a CTE and understand how MySQL infers column names.
- Combine multiple CTEs, where a later CTE uses the result of an earlier CTE.
- Use CTEs in SELECT, UPDATE, and DELETE statements.
- Distinguish CTEs from derived tables, views, and temporary tables.
- Understand how the optimizer can merge or materialize a CTE and how to inspect it using EXPLAIN.
- Avoid common errors with name scope, duplicate columns, declaration order, and overly large intermediate datasets.

A Common Table Expression (CTE) is a named result set that is valid only within a single SQL statement. A CTE helps break a complex query into meaningfully named steps. Instead of nesting multiple SELECTs inside one another, you can describe each step in WITH and then reference their names in the main query.

In MySQL, a CTE is not a physical table and does not automatically make a query faster. The optimizer may merge the CTE into the outer query or materialize an intermediate result set for use. Therefore, you need to understand both the syntax and how to inspect execution plans.

## 1. What is a CTE?

A CTE is a subquery declared at the beginning of a statement and bound to a name. The main query can reference that name just like referencing a table in the FROM clause.

For example, instead of writing a subquery inline:

~~~sql
SELECT
    customer_id,
    total_amount
FROM (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
) AS customer_spending
WHERE total_amount >= 5000000;
~~~

You can name the intermediate result set using WITH:

~~~sql
WITH customer_spending AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS total_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
)
SELECT
    customer_id,
    total_amount
FROM customer_spending
WHERE total_amount >= 5000000;
~~~

The name customer_spending describes the meaning of the aggregation step. The main query clearly expresses the goal: retrieve customers whose total spending is 5 million or more.

A CTE typically has three parts:

1. The CTE name.
2. The query defining the result set enclosed in parentheses.
3. The main statement that uses the CTE.

A CTE exists only within the scope of that statement. Once the statement finishes, the CTE name can no longer be used.

## 2. WITH Syntax

General syntax for a non-recursive CTE:

~~~sql
WITH cte_name [(column_name, ...)] AS (
    subquery
)
SELECT ...
FROM cte_name;
~~~

Where:

- WITH starts the CTE list.
- cte_name is the name chosen by the author.
- The column_name list is optional and is used to name the output columns.
- AS introduces the query defining the CTE.
- subquery is the SELECT statement producing the result set.
- The SELECT that follows is the main statement using the CTE.

If there are multiple CTEs, separate the definitions with commas:

~~~sql
WITH
first_cte AS (
    SELECT ...
),
second_cte AS (
    SELECT ...
    FROM first_cte
)
SELECT ...
FROM second_cte;
~~~

Write WITH only once at the same statement level. Do not repeat WITH between CTEs in the same list.

Each CTE name must be unique within the same WITH clause. For non-recursive CTEs, do not add the RECURSIVE keyword. Only use WITH RECURSIVE when a CTE references itself; the anchor and recursive member parts will be covered in the lesson on recursive queries.

### 2.1. Naming Columns for a CTE

You can declare column names right after the CTE name:

~~~sql
WITH order_totals (order_id, item_count, order_value) AS (
    SELECT
        order_id,
        COUNT(*),
        SUM(quantity * unit_price)
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    item_count,
    order_value
FROM order_totals;
~~~

The three names in the list must correspond to the three expressions returned by SELECT. A mismatch in the number of columns will cause the statement to fail with an error.

If you omit the column list, MySQL derives names from the expressions in SELECT:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        SUM(quantity * unit_price) AS order_value
    FROM order_item
    GROUP BY order_id
)
SELECT *
FROM order_totals;
~~~

You should assign clear aliases to computed expressions. Do not rely on auto-generated column names from complex expressions, as they can be hard to read or unsuitable when referenced in a later step.

### 2.2. Column Names Must Be Clear and Unique

A CTE behaves like a logical table with output columns. Column names in a CTE need to be distinguishable so the outer query can reference them accurately.

For example, you should not return two columns both named id:

~~~sql
WITH customer_order AS (
    SELECT
        c.customer_id AS id,
        o.order_id AS id,
        o.ordered_at
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
)
SELECT *
FROM customer_order;
~~~

The fix is to assign aliases that reflect their origin:

~~~sql
WITH customer_order AS (
    SELECT
        c.customer_id,
        o.order_id,
        o.ordered_at
    FROM customer AS c
    JOIN sales_order AS o
        ON o.customer_id = c.customer_id
)
SELECT *
FROM customer_order;
~~~

If two tables have columns with the same name, specify the table alias and assign appropriate output names. This also prevents confusion when the query is extended later.

## 3. Preparing Practice Data

The following examples use a simple model consisting of customers, orders, and order lines. You can run the DDL and sample data in a practice database.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    lifetime_value DECIMAL(14, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(24) NOT NULL,
    ordered_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_order_customer_date (customer_id, ordered_at),
    KEY idx_sales_order_status_date (order_status, ordered_at),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_name VARCHAR(160) NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
) ENGINE = InnoDB;

INSERT INTO customer (customer_id, full_name)
VALUES
    (101, 'Nguyễn An'),
    (102, 'Trần Bình'),
    (103, 'Lê Chi');

INSERT INTO sales_order (
    order_id, customer_id, order_status, ordered_at
)
VALUES
    (1001, 101, 'completed', '2026-01-05 09:15:00'),
    (1002, 101, 'completed', '2026-01-20 14:30:00'),
    (1003, 102, 'pending',   '2026-02-02 10:00:00'),
    (1004, 102, 'completed', '2026-02-12 16:45:00'),
    (1005, 103, 'cancelled', '2026-02-15 11:20:00');

INSERT INTO order_item (
    order_id, line_no, product_name, quantity, unit_price
)
VALUES
    (1001, 1, 'Mechanical Keyboard', 1, 1250000.00),
    (1001, 2, 'Wireless Mouse', 2, 450000.00),
    (1002, 1, '27-inch Monitor', 1, 5200000.00),
    (1003, 1, 'Headphones', 1, 890000.00),
    (1004, 1, 'Webcam', 2, 750000.00),
    (1004, 2, 'USB Microphone', 1, 1100000.00);
~~~

Line item total value is calculated as quantity * unit_price. In this example, sales_order does not store total_amount; the queries will calculate it from order_item to illustrate how CTEs produce intermediate result sets.

## 4. Simple CTEs to Name Results

Example calculating the total amount per order:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
ORDER BY order_id;
~~~

The CTE order_totals returns one row for each order_id. The outer SELECT statement can filter, sort, or JOIN this result set as a data source.

Filtering orders with a total amount of at least 2 million:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000
ORDER BY total_amount DESC;
~~~

You can place the aggregate condition directly inside the CTE using HAVING:

~~~sql
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
    HAVING SUM(quantity * unit_price) >= 2000000
)
SELECT *
FROM order_totals;
~~~

Both approaches can return the same result, but where the condition is placed expresses different intent:

- HAVING filters groups directly during the CTE creation step.
- WHERE in the outer query filters the named result set.

Choose the approach that makes the logical boundary easy to understand. You do not need to push every condition into the CTE if that condition only serves the main query.

## 5. Combining Multiple CTEs

A query can be split into multiple steps. A CTE declared earlier can be referenced by a CTE declared later.

For example, suppose you need to calculate the total completed spending for each customer, and then retrieve customers with revenue of 2 million or more:

~~~sql
WITH
order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
),
completed_orders AS (
    SELECT
        o.order_id,
        o.customer_id,
        ot.total_amount
    FROM sales_order AS o
    JOIN order_totals AS ot
        ON ot.order_id = o.order_id
    WHERE o.order_status = 'completed'
),
customer_totals AS (
    SELECT
        customer_id,
        COUNT(*) AS completed_order_count,
        SUM(total_amount) AS spending
    FROM completed_orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.full_name,
    ct.completed_order_count,
    ct.spending
FROM customer_totals AS ct
JOIN customer AS c
    ON c.customer_id = ct.customer_id
WHERE ct.spending >= 2000000
ORDER BY ct.spending DESC;
~~~

You can read the query layer by layer:

1. order_totals calculates the total amount per order.
2. completed_orders keeps only completed orders and attaches the customer.
3. customer_totals calculates the order count and total spending per customer.
4. The final SELECT adds the customer's name and filters by the spending threshold.

Each CTE carries a specific meaning. When you need to change how the total amount is calculated, you can modify order_totals without having to repeat the expression everywhere.

### 5.1. Later CTEs Referencing Earlier CTEs

In a non-recursive WITH list, a CTE may only reference CTEs that were declared before it.

Valid:

~~~sql
WITH
base_orders AS (
    SELECT order_id, customer_id
    FROM sales_order
),
customer_order_count AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM base_orders
    GROUP BY customer_id
)
SELECT *
FROM customer_order_count;
~~~

It is invalid for base_orders to reference customer_order_count, which is declared after it. A CTE also cannot reference itself without using WITH RECURSIVE.

Therefore, order your CTEs in dependency order: base datasets first, transformation steps next, and final results last.

### 5.2. Reusing a CTE

A CTE can be referenced multiple times within the same statement:

~~~sql
WITH completed_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT
    (SELECT COUNT(*) FROM completed_orders) AS total_completed,
    (
        SELECT COUNT(DISTINCT customer_id)
        FROM completed_orders
    ) AS customer_count;
~~~

The name completed_orders is used in two scalar subqueries. The CTE allows the order_status = 'completed' condition to be defined once.

Referencing a CTE multiple times does not mean the subquery is always executed independently again. The optimizer can choose an appropriate execution strategy, including materializing the result set and reusing it. Actual behavior should be checked with EXPLAIN.

### 5.3. Using CTEs to Separate Multi-Step Transformations

Example of a monthly revenue report:

~~~sql
WITH
order_totals AS (
    SELECT
        o.order_id,
        o.ordered_at,
        SUM(oi.quantity * oi.unit_price) AS order_amount
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.order_id, o.ordered_at
),
monthly_sales AS (
    SELECT
        DATE_FORMAT(ordered_at, '%Y-%m') AS sales_month,
        COUNT(*) AS order_count,
        SUM(order_amount) AS revenue
    FROM order_totals
    GROUP BY DATE_FORMAT(ordered_at, '%Y-%m')
)
SELECT
    sales_month,
    order_count,
    revenue
FROM monthly_sales
ORDER BY sales_month;
~~~

order_totals handles calculating totals per order. monthly_sales handles grouping by month. If the report later needs the number of customers as well, you can add a CTE or an appropriate aggregate expression without rewriting the entire order-total calculation.

## 6. CTEs with JOINs and Multi-Source Queries

A CTE can be JOINed with physical tables, views, derived tables, or other CTEs.

Example finding customers who do not have any orders yet:

~~~sql
WITH customers_with_orders AS (
    SELECT DISTINCT customer_id
    FROM sales_order
)
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
LEFT JOIN customers_with_orders AS x
    ON x.customer_id = c.customer_id
WHERE x.customer_id IS NULL;
~~~

The CTE customers_with_orders represents the set of customers who have ever placed an order. The outer query uses LEFT JOIN to find unmatched customers.

You can also use NOT EXISTS:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM sales_order AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Not every query needs a CTE. For a simple condition, a direct NOT EXISTS can be shorter and easier to read. Use a CTE when naming the result set clarifies a business step or when the same logic needs to be referenced multiple times.

## 7. CTEs with UPDATE and DELETE

In MySQL, the WITH clause can precede an UPDATE or DELETE statement. The query defining the CTE provides the result set for the main DML statement to use; the CTE is a read source, while the data modifications are performed by UPDATE or DELETE.

### 7.1. UPDATE Based on a Precomputed Result Set

Example updating a customer's lifetime_value with the total value of completed orders:

~~~sql
WITH customer_spending AS (
    SELECT
        o.customer_id,
        SUM(oi.quantity * oi.unit_price) AS spending
    FROM sales_order AS o
    JOIN order_item AS oi
        ON oi.order_id = o.order_id
    WHERE o.order_status = 'completed'
    GROUP BY o.customer_id
)
UPDATE customer AS c
JOIN customer_spending AS cs
    ON cs.customer_id = c.customer_id
SET c.lifetime_value = cs.spending;
~~~

customer_spending produces one row per customer with completed orders. UPDATE uses that result set to write back lifetime_value.

Customers with no completed orders do not appear in the CTE, so the UPDATE statement above does not change their lifetime_value. If business rules require resetting those customers' values to 0, you need to write a query covering the entire customer table, such as a LEFT JOIN with COALESCE.

### 7.2. DELETE Based on an Identified Result Set

Example identifying orders cancelled before a cutoff timestamp:

~~~sql
WITH cancelled_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'cancelled'
      AND ordered_at < '2026-02-16 00:00:00'
)
DELETE so
FROM sales_order AS so
JOIN cancelled_orders AS co
    ON co.order_id = so.order_id;
~~~

The CTE only selects the set of order_ids. DELETE is what actually removes the data.

If the table has foreign keys from child tables, the delete behavior depends on the ON DELETE constraint. For business data or data requiring audit history, consider preserving, flagging status, or archiving before performing a physical delete.

### 7.3. Verifying Before Running DML

Before running an UPDATE or DELETE that affects many rows, run the equivalent SELECT to see the exact set of records:

~~~sql
WITH cancelled_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'cancelled'
      AND ordered_at < '2026-02-16 00:00:00'
)
SELECT so.*
FROM sales_order AS so
JOIN cancelled_orders AS co
    ON co.order_id = so.order_id;
~~~

In strictly controlled environments, run DML inside an InnoDB transaction when the statement and related operations allow it, verify the number of affected rows, and then COMMIT or ROLLBACK. WITH itself does not create a transaction and does not guarantee rollback.

## 8. CTE Scope and Naming Rules

### 8.1. A CTE Is Valid Only Within One Statement

Example:

~~~sql
WITH active_orders AS (
    SELECT order_id
    FROM sales_order
    WHERE order_status = 'completed'
)
SELECT *
FROM active_orders;
~~~

The next statement cannot reuse the name active_orders:

~~~sql
SELECT *
FROM active_orders;
~~~

The second statement will report that the corresponding table or view does not exist because the CTE has gone out of scope.

If you need to use the same result set across multiple statements, consider:

- A view if the logic needs to be shared long-term.
- A temporary table if you need to store results per session and reuse them across multiple statements.
- A physical table if the data needs to be persisted durably.

### 8.2. CTEs Nested Inside a Subquery

You can declare a CTE at the beginning of a subquery. The scope of that CTE belongs to the corresponding subquery:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
WHERE c.customer_id IN (
    WITH high_value_orders AS (
        SELECT customer_id
        FROM sales_order
        GROUP BY customer_id
        HAVING COUNT(*) >= 2
    )
    SELECT customer_id
    FROM high_value_orders
);
~~~

Although this syntax is valid in MySQL 8.0, you should not nest WITH too deeply if it makes the query hard to follow. You can usually move the CTE to the top of the main statement so readers see all the steps right from the start.

### 8.3. CTE Names and Table Names

Choose names that reflect the meaning of the result set, for example:

- order_totals
- active_customers
- monthly_revenue
- ranked_products
- overdue_invoices

Avoid generic names like temp1, data2, or result. Good names bring the query closer to business terminology.

MySQL has name resolution rules across CTEs, derived tables, views, and tables. A derived table can shadow a CTE; a CTE can shadow a table, temporary table, or view with the same name within the scope of the statement. Therefore, avoid naming a CTE the same as a real table being queried; a distinct name with a suffix like _cte or a clearly descriptive name is usually easier to review.

## 9. CTEs, Derived Tables, Views, and Temporary Tables

These structures can all represent a result set, but they differ in scope and how they are used.

| Characteristic | CTE | Derived table | View | Temporary table |
|---|---|---|---|---|
| Declaration | WITH ... AS (...) | Subquery in FROM | CREATE VIEW | CREATE TEMPORARY TABLE |
| Scope | One statement | The single query containing it | Multiple statements, multiple sessions by privilege | The session that created the table |
| Named | Has a CTE name | Alias required | Schema object name | Table name in session |
| Reusability | Within the same statement | Usually one place in FROM | Multiple statements | Multiple statements in the session |
| Physical storage | Not user-managed | Not user-managed | Does not store separate results by default | Stores temporary rows |
| Custom indexes | Cannot be declared directly | Cannot be declared directly | Cannot be declared directly | Indexes can be created |
| Best suited for | Splitting a query into named steps | Short, one-off subqueries | Long-term shared logic | Large intermediate sets or reuse across multiple statements |

### 9.1. CTEs and Derived Tables

Derived table:

~~~sql
SELECT
    x.customer_id,
    x.order_count
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
) AS x
WHERE x.order_count >= 2;
~~~

Using a CTE:

~~~sql
WITH customer_order_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
)
SELECT
    customer_id,
    order_count
FROM customer_order_counts
WHERE order_count >= 2;
~~~

Both approaches can describe the same logic. A CTE is more useful when the query has multiple layers or when the same result set is used multiple times. A derived table fits a small transformation placed directly inside FROM.

### 9.2. CTEs and Views

A view is created as an object in the database:

~~~sql
CREATE VIEW completed_order_summary AS
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM sales_order
WHERE order_status = 'completed'
GROUP BY customer_id;
~~~

You can then query the view across multiple statements:

~~~sql
SELECT *
FROM completed_order_summary;
~~~

A CTE does not require CREATE VIEW and does not persist after the statement. If the logic only serves a single query, a CTE is usually more convenient. If multiple reports or applications share the same definition, a view may be more appropriate.

### 9.3. CTEs and Temporary Tables

A temporary table is created explicitly:

~~~sql
CREATE TEMPORARY TABLE tmp_customer_spending (
    customer_id BIGINT UNSIGNED NOT NULL,
    spending DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (customer_id)
);
~~~

You can load data into it and use it across multiple statements within the same session. A temporary table can have user-declared indexes.

A CTE does not allow declaring custom indexes or retaining data for use in subsequent statements. If you need multiple processing steps over a large intermediate set and want to index it proactively, a temporary table may be more suitable.

## 10. How Does the Optimizer Handle CTEs?

Writing a CTE as a separate block does not mean MySQL always creates a temporary table. For non-recursive CTEs, the optimizer can choose between two main strategies:

- **Merge:** merges the CTE definition query into the outer query, similar to expanding a derived table or view.
- **Materialize:** executes the CTE query and stores the intermediate result for the outer query to read.

The chosen strategy depends on query structure, optimization eligibility, and estimated cost.

### 10.1. When a CTE Can Be Merged

A simple CTE such as filtering a table and selecting a few columns can be merged:

~~~sql
WITH recent_orders AS (
    SELECT
        order_id,
        customer_id,
        ordered_at
    FROM sales_order
    WHERE ordered_at >= '2026-01-01'
)
SELECT
    order_id,
    customer_id
FROM recent_orders
WHERE customer_id = 101;
~~~

The optimizer can combine the predicates to generate an access plan that reads sales_order directly. When merged, the CTE does not necessarily create a separate intermediate table.

### 10.2. When a CTE Needs Materialization

Certain constructs prevent merging, such as aggregates, GROUP BY, DISTINCT, window functions, or LIMIT in specified cases. In those situations, MySQL may materialize the intermediate result.

Example:

~~~sql
WITH customer_order_counts AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count
    FROM sales_order
    GROUP BY customer_id
)
SELECT *
FROM customer_order_counts
WHERE order_count >= 2;
~~~

The GROUP BY step produces an aggregated result. The optimizer may need to materialize the CTE and then apply the outer predicate, or perform other suitable optimizations.

Materialization has a cost to build and read the result set. If a CTE produces millions of rows while the outer query only needs a small subset, consider pushing filter predicates inside the CTE when doing so does not change the meaning.

### 10.3. CTEs Referenced Multiple Times

When a non-recursive CTE is referenced multiple times, MySQL can materialize it once and reuse the materialized result set. The optimizer can create appropriate internal indexes for different access patterns.

This can save re-executing the same aggregation, but a large result set still consumes resources to materialize. Do not assume a multiply-referenced CTE is always faster than rewriting the query. Measure with EXPLAIN and realistic workloads.

### 10.4. CTEs Are Not a Caching Mechanism

CTEs do not persist results across statement executions. If the same SQL statement is executed in two requests, the CTE is processed during each execution according to that statement's plan.

If you need caching or persisted aggregated results, you need a separate mechanism such as summary tables, application-managed materialized results, application-tier caching, or an architecture-appropriate solution.

## 11. Inspecting CTEs with EXPLAIN

Use EXPLAIN to see how MySQL plans to execute the query:

~~~sql
EXPLAIN
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000;
~~~

Observe:

- Which source tables are read.
- The access type and chosen indexes.
- Estimated row counts.
- Whether there is a CTE materialization step.
- Whether there is a temporary table or filesort.
- At which step filter conditions are applied.

Starting with MySQL 8.0.18, EXPLAIN ANALYZE can execute the query and provide actual timing and row counts across iterators:

~~~sql
EXPLAIN ANALYZE
WITH order_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount
    FROM order_item
    GROUP BY order_id
)
SELECT
    order_id,
    total_amount
FROM order_totals
WHERE total_amount >= 2000000;
~~~

EXPLAIN ANALYZE actually executes the SELECT statement. Do not run it casually on heavy queries or queries with side effects. For UPDATE/DELETE, verify the row set with SELECT and follow proper operational procedures before modifying data.

Do not judge good or bad solely by whether a Materialize line appears. Materializing can be reasonable if a result set is used multiple times; merging can be better if it enables early filtering. Evaluate the full plan and actual execution time.

## 12. Common Limitations and Pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Forgetting aliases for computed expressions | Output columns are hard to reference or unclearly named | Assign aliases or declare a CTE column list |
| Duplicate output column names | Ambiguous column reference or definition error | Use unique column names |
| Referencing a CTE declared later | Invalid for non-recursive CTEs | Declare in dependency order |
| Using a CTE in the next statement | CTE is already out of scope | Use a view or temporary table if reuse is needed |
| Assuming a CTE always materializes | Misunderstanding the execution plan | Inspect with EXPLAIN |
| Assuming a CTE is always faster than a subquery | May introduce extra materialization or redundant work | Compare plans and workloads |
| Using SELECT * in a large CTE | Carries unnecessary columns | Select only columns used by the outer query |
| Putting all logic into one huge CTE | Hard to read and hard to test | Split into meaningful business steps |
| Splitting into too many tiny CTEs | Increases layers to track | Combine simple steps that add no clarity |
| Confusing a CTE with a temporary table | Expecting custom indexes or cross-statement usage | Choose the right construct for scope and lifecycle |
| Failing to filter data early | Intermediate dataset may become too large | Push appropriate conditions into the source step |

### 12.1. MySQL Version Note

CTEs are supported starting in MySQL 8.0. Examples using CTEs and window functions in this lesson require MySQL 8.0 or later. EXPLAIN ANALYZE is available from MySQL 8.0.18.

Check the server version:

~~~sql
SELECT VERSION() AS mysql_version;
~~~

If the system runs MySQL 5.7 or older, MySQL 8.0 WITH syntax cannot be used. In that case, you may need derived tables, views, or temporary tables depending on the goal.

## 13. Workflow for Designing Queries with CTEs

When facing a complex query, follow this sequence:

1. **Write down the required final output:** define what one row represents, which columns are needed, and what filter conditions apply.
2. **Identify the business steps:** for example, calculating per-order totals, filtering completed orders, aggregating by customer.
3. **Name each result set:** use nouns or phrases that reflect meaning, not generic temporary names.
4. **Declare in dependency order:** source CTEs first, consumer CTEs afterward.
5. **Select only necessary columns:** avoid SELECT * when intermediate data is wide.
6. **Assign clear aliases:** every computed expression needs an understandable name.
7. **Verify each step:** run a SELECT on an individual CTE to confirm row counts and values.
8. **Assemble the main query:** JOIN or filter the CTEs to produce the final result.
9. **Inspect the plan:** use EXPLAIN, and EXPLAIN ANALYZE when appropriate.
10. **Compare alternatives:** if a materialized CTE becomes too large, try pushing filters earlier or using an indexed temporary table when reuse is needed.

## 14. Practice Exercises

### Exercise 1: Basic CTE

Use WITH to create a CTE containing completed orders from sales_order. Query the CTE to retrieve order_id, customer_id, and ordered_at. Add a condition to include only orders from January 2026.

### Exercise 2: Naming Output Columns

Create a CTE that calculates the line item count and total value for each order. Declare the column list right after the CTE name. Intentionally declare a mismatched number of columns and observe the error.

### Exercise 3: Combining Multiple CTEs

Create order_totals, completed_orders, and customer_totals. Retrieve customers with total spending greater than 2 million. Explain which part of the logic each CTE is responsible for.

### Exercise 4: Reusing a CTE

Create the CTE completed_orders and reference it in two subqueries to calculate the total number of completed orders and the number of customers who placed orders. Inspect the execution plan.

### Exercise 5: CTE with UPDATE

Use a CTE to calculate the total value of completed orders per customer. Update customer.lifetime_value. Before running UPDATE, execute the equivalent SELECT and record the expected number of rows to be modified.

### Exercise 6: CTE with DELETE

Create a CTE identifying cancelled test orders. Query the list first, then perform DELETE on the practice database. Check the impact of foreign keys.

### Exercise 7: Comparing CTEs and Derived Tables

Write the same query in two ways: using a derived table and using a CTE. Use EXPLAIN to compare the plans. Explain when the CTE style is easier to read.

### Exercise 8: Finding a CTE That Requires Materialization

Write a CTE with GROUP BY and reference it multiple times. Observe EXPLAIN to locate any materialization step. Evaluate the intermediate row count and cost.

### Exercise 9: Monthly Revenue Report

Create a CTE to calculate total amount per order, followed by a second CTE to calculate monthly revenue. Extend it to also calculate order count and average order value.

### Exercise 10: Refactoring a Multi-Level Query

Pick a query with multiple nested subqueries in a personal project. Extract meaningful steps into CTEs, keep the results identical, and compare EXPLAIN before and after.

## Conclusion

CTEs allow you to name intermediate result sets directly inside a SQL statement using WITH. This construct helps break complex queries into meaningful steps, reduces duplicated logic, and makes reading, reviewing, and testing individual parts easier.

A CTE is scoped to a single statement and is not a physical table. MySQL may merge or materialize a CTE depending on its structure and the optimization plan. Use clear names, declare CTEs in dependency order, select the right columns, and inspect with EXPLAIN. When you need to persist results across multiple statements or proactively create indexes on intermediate data, consider a view or a temporary table.

## References

- MySQL 8.4 Reference Manual — WITH (Common Table Expressions): https://dev.mysql.com/doc/refman/8.4/en/with.html
- MySQL 8.4 Reference Manual — Derived Table Optimization: https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html
- MySQL 8.4 Reference Manual — EXPLAIN Statement: https://dev.mysql.com/doc/refman/8.4/en/explain.html
- MySQL 8.4 Reference Manual — EXPLAIN ANALYZE: https://dev.mysql.com/doc/refman/8.4/en/explain.html#explain-analyze
