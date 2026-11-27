# Distinguishing WHERE and HAVING

In a SELECT query, both WHERE and HAVING filter data, but they filter at two different stages. **WHERE filters individual rows before grouping and aggregation; HAVING filters groups after GROUP BY and aggregate calculations are performed.**

Understanding this distinction helps write accurate reports, avoid placing aggregate conditions in the wrong clause, and reduce the amount of data processed. In MySQL, you also need to pay attention to logical processing order, alias usage, the ONLY_FULL_GROUP_BY SQL mode, and NULL behavior in aggregate functions.

This article uses the illustrative tables customers and orders:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL,
    shipped_at  DATETIME NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;
~~~

## 1. WHERE Filters Rows Before Grouping

WHERE determines which rows are passed into subsequent steps of the query. Rows that do not satisfy the WHERE condition are eliminated from the intermediate result set before GROUP BY forms groups.

Example: select only paid orders:

~~~sql
SELECT order_id, customer_id, total
FROM orders
WHERE status = 'PAID';
~~~

Here each row is an order. WHERE checks status on each order and retains only rows with status PAID.

Multiple row-level predicates can be combined:

~~~sql
SELECT order_id, customer_id, total, created_at
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01';
~~~

These conditions do not require aggregating data. They describe which rows qualify to participate in the query.

WHERE is commonly used for:

- Filtering by keys or row attributes.
- Filtering by status, dates, or numeric ranges.
- Narrowing the data scope before GROUP BY.
- Join and row-filtering conditions in multi-table queries (distinguish ON from WHERE when using outer joins).

## 2. HAVING Filters Groups After Aggregation

HAVING is applied after GROUP BY to inspect each group. It is commonly used with aggregate functions such as COUNT(), SUM(), AVG(), MIN(), and MAX().

Example: find customers with at least three orders:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 3;
~~~

Process:

1. MySQL reads rows from orders.
2. GROUP BY groups rows sharing the same customer_id.
3. COUNT(*) counts the orders in each group.
4. HAVING keeps only groups with three or more orders.

If you replace HAVING with WHERE:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS order_count
FROM orders
WHERE COUNT(*) >= 3
GROUP BY customer_id;
~~~

This query is invalid because WHERE is processed before groups are formed; COUNT(*) has no value at that stage yet. Conditions that depend on aggregate results must be placed in HAVING.

## 3. Logical Processing Order of SELECT

To determine where to place a condition, picture the standard logical processing order of a SELECT query as follows:

~~~text
FROM / JOIN
     |
     v
WHERE       Filter individual rows
     |
     v
GROUP BY    Form groups
     |
     v
HAVING      Filter groups
     |
     v
SELECT      Evaluate expressions and aggregate functions
     |
     v
ORDER BY    Sort results
     |
     v
LIMIT       Limit number of returned rows
~~~

This is a logical order for understanding semantics, not a guarantee that MySQL physically executes each step strictly in this sequence. The optimizer may transform the plan as long as it preserves the SQL semantic result.

Key points:

- WHERE cannot reference the result of an aggregate function at the same SELECT level.
- HAVING sees the groups and aggregate results.
- An alias created in the SELECT list cannot be used in the WHERE clause of the same query level.
- MySQL allows referencing SELECT-expression aliases in HAVING as an extension; consider portability if your SQL must run across multiple database systems.

## 4. Combining WHERE and HAVING in the Same Query

In real-world reporting, you often need to filter rows first and then filter groups.

Requirement: find customers with at least three paid orders in 2026 whose total value is at least 1,000,000.

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING COUNT(*) >= 3
   AND SUM(total) >= 1000000
ORDER BY paid_total DESC;
~~~

Condition placement breakdown:

| Condition | Placement | Reason |
|---|---|---|
| status = 'PAID' | WHERE | Attribute of each individual order |
| created_at within 2026 | WHERE | Time attribute of each individual order |
| COUNT(*) >= 3 | HAVING | Number of rows in each group |
| SUM(total) >= 1000000 | HAVING | Total value after grouping |

If you put the status condition in HAVING, the query may have to feed many unnecessary rows into grouping only to discard those groups afterward. Row conditions should be placed in WHERE as long as doing so does not change the report semantics.

## 5. Conditions on Grouping Columns: WHERE or HAVING?

A condition on a grouping column can syntactically appear in either place, but the timing of filtering differs.

The following two queries share the same goal: count orders for customer 42.

~~~sql
-- Filter customers before grouping
SELECT customer_id, COUNT(*) AS order_count
FROM orders
WHERE customer_id = 42
GROUP BY customer_id;

-- Form groups first, then retain only customer 42's group
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING customer_id = 42;
~~~

In this simple example, the result is usually the same. However, WHERE eliminates other customers' rows before grouping; HAVING creates groups and then discards non-matching groups.

Because customer_id = 42 is a condition on source rows, prefer WHERE. This expresses intent clearly and typically allows reducing the number of input rows to the aggregation step. Do not move every condition into HAVING simply because a query has GROUP BY.

## 6. Aggregate Functions Commonly Used with HAVING

### 6.1. COUNT()

COUNT(*) counts all rows in a group:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 10;
~~~

COUNT(column) counts only rows where the column expression is not NULL:

~~~sql
SELECT customer_id, COUNT(shipped_at) AS shipped_count
FROM orders
GROUP BY customer_id
HAVING COUNT(shipped_at) = 0;
~~~

The second example requires the shipped_at column to exist in the table. If the column allows NULL, COUNT(shipped_at) equal to 0 means the group has no non-NULL shipped_at values; it does not necessarily mean there are no orders.

### 6.2. SUM()

Find customers with a large total order value:

~~~sql
SELECT customer_id, SUM(total) AS total_spent
FROM orders
GROUP BY customer_id
HAVING SUM(total) >= 5000000;
~~~

SUM() adds non-NULL values. If the summed expression is nullable and a group has no non-NULL values, SUM() can return NULL; comparing NULL with a number evaluates to UNKNOWN and the group does not pass HAVING.

### 6.3. AVG()

Find customers whose average order value exceeds a threshold:

~~~sql
SELECT
    customer_id,
    AVG(total) AS average_order_value
FROM orders
GROUP BY customer_id
HAVING AVG(total) > 750000;
~~~

AVG() ignores NULL values. When interpreting results, understand that the denominator is the count of non-NULL values, not necessarily the total number of rows in the group.

### 6.4. MIN() and MAX()

Find customers whose largest order meets a threshold:

~~~sql
SELECT
    customer_id,
    MAX(total) AS largest_order
FROM orders
GROUP BY customer_id
HAVING MAX(total) >= 10000000;
~~~

MIN() and MAX() can be applied to numbers, datetimes, and strings according to the comparison rules of the data type/collation.

## 7. Using Aliases in HAVING

MySQL allows referencing SELECT-expression aliases in HAVING:

~~~sql
SELECT
    customer_id,
    SUM(total) AS total_spent
FROM orders
GROUP BY customer_id
HAVING total_spent >= 5000000;
~~~

This form is concise and readable. However, aliases are not available in the WHERE clause of the same query level:

~~~sql
-- Invalid: total_spent is an alias created in SELECT
SELECT
    customer_id,
    SUM(total) AS total_spent
FROM orders
WHERE total_spent >= 5000000
GROUP BY customer_id;
~~~

If you need to filter on an aggregate result in an outer query, use a derived table or CTE:

~~~sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total) AS total_spent
    FROM orders
    GROUP BY customer_id
)
SELECT customer_id, total_spent
FROM customer_totals
WHERE total_spent >= 5000000;
~~~

In the outer query, total_spent is already a column of the derived result, so WHERE can use it. A CTE helps express logic step by step; the optimizer may merge or materialize the CTE depending on the query and version.

## 8. HAVING Without GROUP BY

If a query uses aggregate functions without GROUP BY, the entire row set is treated as a single group:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(total) AS gross_value
FROM orders
HAVING COUNT(*) > 0;
~~~

The query returns one row if the aggregated group satisfies HAVING; otherwise, it returns no rows. This is useful when you want to conditionally return a table-wide summary.

MySQL also permits HAVING in certain queries without GROUP BY as an extension. For ordinary row-level filtering, use WHERE to express the proper semantics and improve SQL portability.

## 9. WHERE, HAVING, and ONLY_FULL_GROUP_BY

ONLY_FULL_GROUP_BY is a SQL mode that controls non-aggregated expressions appearing in SELECT, HAVING, or ORDER BY of a grouped query.

When this mode is enabled, columns not in GROUP BY typically must:

- Be used inside an aggregate function; or
- Have a functional dependency on the grouping columns; or
- Be constrained so MySQL can prove only a single value is valid in a supported context.

MySQL 8.0 enables ONLY_FULL_GROUP_BY in the default SQL mode configuration. Check the current session:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Semantically unsafe example:

~~~sql
SELECT
    customer_id,
    status,
    COUNT(*) AS order_count
FROM orders
GROUP BY customer_id;
~~~

A customer may have multiple orders with different statuses. If MySQL cannot determine a single status value per group, the query is rejected when ONLY_FULL_GROUP_BY is enabled. When the mode is disabled, MySQL may pick an indeterminate status value within the group; do not rely on such results.

Fix it to match the business intent. If you want to count orders by both customer and status:

~~~sql
SELECT customer_id, status, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id, status;
~~~

If you want to filter groups with a high total order count:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
HAVING COUNT(*) >= 5;
~~~

### 9.1. Functional Dependency

MySQL may allow selecting a column not listed in GROUP BY if it can prove the column is functionally dependent on the grouping columns. For example, customers.customer_id is a primary key and therefore uniquely determines customers.full_name:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
~~~

In MySQL, functional dependency based on a NOT NULL unique key can make a query valid when ONLY_FULL_GROUP_BY is enabled. Even so, explicitly listing the column in GROUP BY sometimes makes intent clearer, especially when SQL must be portable across database engines.

Do not disable ONLY_FULL_GROUP_BY just to make a semantically broken query run. Clarify what each group represents and which columns have a single value per group.

## 10. WHERE and HAVING with JOIN

With JOIN, conditions can appear in ON, WHERE, or HAVING. These three locations serve different roles:

- ON determines which rows match when combining two tables.
- WHERE filters row results after JOIN and before GROUP BY.
- HAVING filters groups after aggregation.

Example: list all customers and their paid order counts, including customers with no orders yet:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name;
~~~

The o.status = 'PAID' condition is inside ON, so only paid orders are joined; customers without matching orders still appear with NULL in all orders columns. COUNT(o.order_id) returns 0 for that group.

If you move the status condition to WHERE:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.full_name;
~~~

The NULL-extended rows for customers without orders are eliminated by WHERE. The result no longer retains customers without matching orders; the LEFT JOIN effectively behaves like an INNER JOIN.

If you only want to keep customers with at least three paid orders, add HAVING:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.full_name
HAVING COUNT(o.order_id) >= 3;
~~~

The condition in HAVING applies to the order count in each group, not to individual order rows.

## 11. NULL and HAVING Conditions

Aggregate functions do not handle NULL identically:

| Function | How NULL is handled |
|---|---|
| COUNT(*) | Counts every row |
| COUNT(column) | Counts only non-NULL column values |
| SUM(column) | Ignores NULL; returns NULL if there are no non-NULL values |
| AVG(column) | Ignores NULL when computing the average |
| MIN()/MAX() | Ignores NULL; returns NULL if there are no non-NULL values |

Example:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS row_count,
    COUNT(shipped_at) AS shipped_count,
    MAX(shipped_at) AS last_shipped_at
FROM orders
GROUP BY customer_id
HAVING COUNT(shipped_at) = 0;
~~~

This query retains customers who have orders but no non-NULL shipped_at value in their group. If you want to sum and treat a group with no values as 0, you can use COALESCE:

~~~sql
SELECT
    customer_id,
    COALESCE(SUM(total), 0) AS total_spent
FROM orders
GROUP BY customer_id
HAVING COALESCE(SUM(total), 0) = 0;
~~~

Use COALESCE only when business rules genuinely define having no values as equivalent to the number 0. NULL and 0 carry different meanings in many reports.

## 12. Performance: Placing Conditions at the Right Stage

WHERE usually helps reduce the number of rows fed into the GROUP BY step. Whenever a condition can filter on source columns, prefer WHERE:

~~~sql
SELECT customer_id, SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING SUM(total) >= 1000000;
~~~

In this example:

- WHERE restricts data by status and time range.
- GROUP BY groups the remaining data by customer.
- HAVING keeps only groups whose total meets the threshold.

An appropriate index can help MySQL locate the needed rows faster. For example, an index starting with status and including created_at can assist this filter, though the exact index choice depends on selectivity, column order, row count, and other queries.

HAVING typically must evaluate aggregate expressions after groups are formed. You cannot simply create an index on total and expect the index to directly satisfy SUM(total) >= ... per group. However, the optimizer may push down certain HAVING conditions that do not depend on aggregates to an earlier filtering stage if safe.

Check the plan:

~~~sql
EXPLAIN
SELECT customer_id, SUM(total) AS paid_total
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY customer_id
HAVING SUM(total) >= 1000000;
~~~

Inspect access type, key, estimated rows, and Extra. EXPLAIN shows the estimated plan; if you need execution metrics, you can use EXPLAIN ANALYZE on a supported version and suitable environment, as that command actually executes the SELECT.

Do not move a condition from WHERE to HAVING just to test performance if doing so changes the input row set and report semantics.

## 13. Common Query Patterns

### 13.1. Filter Rows Then Sum by Month

~~~sql
SELECT
    YEAR(created_at) AS order_year,
    MONTH(created_at) AS order_month,
    COUNT(*) AS order_count,
    SUM(total) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2027-01-01'
GROUP BY YEAR(created_at), MONTH(created_at)
HAVING SUM(total) > 10000000
ORDER BY order_year, order_month;
~~~

WHERE restricts paid orders within the year; HAVING keeps only months with revenue above the threshold.

### 13.2. Count by Status and Keep Only Large Groups

~~~sql
SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
HAVING COUNT(*) >= 100;
~~~

Each group is a status. HAVING filters out statuses with fewer than 100 orders.

### 13.3. Row and Group Conditions on the Same Column

~~~sql
SELECT customer_id, AVG(total) AS average_paid_order
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING AVG(total) >= 500000;
~~~

WHERE determines which orders count toward the average; HAVING decides which customers meet the average threshold.

### 13.4. Using DISTINCT Inside an Aggregate

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) AS status_count
FROM orders
GROUP BY customer_id
HAVING COUNT(DISTINCT status) >= 3;
~~~

COUNT(DISTINCT status) counts distinct statuses, ignoring NULL. HAVING filters for customers who have at least three distinct statuses.

## 14. Common Mistakes and Misconceptions

**"WHERE and HAVING are both just filters and can be swapped freely."** No. WHERE filters rows before grouping; HAVING filters groups after aggregation. Swapping them can alter the data being aggregated and the final result.

**"Whenever GROUP BY is used, all conditions must go in HAVING."** No. Conditions on source rows should still go in WHERE. Only conditions requiring aggregate results or group-level conditions belong in HAVING.

**"You can call SUM() or COUNT() in WHERE."** No. Aggregates for the current query level have not been computed at the WHERE stage. Use HAVING or a subquery/CTE.

**"SELECT aliases work everywhere."** No. SELECT aliases cannot be used in WHERE at the same query level. MySQL allows aliases in HAVING as an extension, but consider portability.

**"HAVING is always slower than WHERE."** You cannot conclude that from the clause name alone. The two clauses have different semantics; the optimizer can push certain eligible conditions down earlier. Place conditions according to semantics and verify with EXPLAIN.

**"COUNT(column) is the same as COUNT(*)."** No. COUNT(column) ignores NULL, whereas COUNT(*) counts all rows.

**"Disabling ONLY_FULL_GROUP_BY is how you fix grouped queries."** No. Disabling the mode can cause MySQL to pick indeterminate values for columns that are neither grouped nor aggregated. Fix GROUP BY and SELECT expressions to match the intended meaning.

**"Putting a condition on the right-hand table of a LEFT JOIN in WHERE is always equivalent to putting it in ON."** No. WHERE can eliminate NULL-extended rows and lose rows that had no matching record. Decide whether the condition controls matching or filters the post-JOIN result.

## 15. Decision Process for Placing Conditions

When writing a query, ask yourself in order:

1. Does the condition check an attribute of each individual source row? If yes, it usually belongs in WHERE.
2. Does the condition determine which rows are allowed to match in an OUTER JOIN? If yes, consider placing it in ON.
3. Does the condition depend on COUNT, SUM, AVG, MIN, MAX, or group-level results? If yes, place it in HAVING.
4. Is the condition filtering the output of an already-aggregated subquery or CTE? In that case, WHERE can be used in the outer query.
5. Do non-aggregated columns comply with ONLY_FULL_GROUP_BY and clearly determine a single value per group?
6. Can the WHERE condition use an index and reduce the number of rows before grouping?

Complete example:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.total) AS paid_total
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
  AND o.created_at >= '2026-01-01'
  AND o.created_at <  '2027-01-01'
GROUP BY c.customer_id, c.full_name
HAVING COUNT(o.order_id) >= 3
   AND SUM(o.total) >= 1000000
ORDER BY paid_total DESC
LIMIT 20;
~~~

Here JOIN defines the relationship between customers and orders; WHERE limits the orders included in the report; GROUP BY forms customer groups; HAVING filters by count and total value; ORDER BY sorts the qualifying groups; LIMIT takes only the top 20 groups.

## Conclusion

WHERE filters individual rows before GROUP BY and aggregations. HAVING filters groups after functions like COUNT(), SUM(), AVG(), MIN(), and MAX() are computed. A reporting query often uses both: WHERE narrows down source data, and HAVING selects groups meeting aggregate criteria.

Place each condition at the exact data level it describes, keeping in mind logical processing order, NULL, ONLY_FULL_GROUP_BY, and the impact of conditions in JOINs. This separation makes queries easier to read, keeps results business-accurate, and gives MySQL the opportunity to reduce the volume of data that must be aggregated.
