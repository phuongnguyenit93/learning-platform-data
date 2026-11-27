# EXISTS, NOT EXISTS, and Existence-Check Queries

In many queries, an application does not need to retrieve columns from a related table; it only needs to know whether at least one row satisfies a condition. For example: which customers have placed an order, which products have never been sold, which orders have at least one line item, or which accounts have had no transactions yet.

MySQL provides two predicates, EXISTS and NOT EXISTS, to express that requirement directly:

- **EXISTS** evaluates to true if the subquery returns at least one row.
- **NOT EXISTS** evaluates to true if the subquery returns zero rows.

These predicates are commonly used with correlated subqueries—subqueries referencing the current row of the outer query. EXISTS filters parent rows by the existence of child rows without multiplying parent rows when multiple matches exist. NOT EXISTS expresses queries looking for rows without any matching relationship.

This article focuses on existence checking, distinguishing EXISTS from JOIN and IN, handling NULLs, reading execution plans, and designing indexes for subqueries in MySQL.

## 1. Preparing the Illustrative Dataset

The examples use customers, orders, products, and order items:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    email       VARCHAR(255) NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status      VARCHAR(30) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    created_at  DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
) ENGINE = InnoDB;

CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    product_name VARCHAR(150) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_id   BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity   INT UNSIGNED NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id, product_id),
    KEY idx_order_items_product (product_id),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    CONSTRAINT fk_order_items_product
        FOREIGN KEY (product_id)
        REFERENCES products(product_id)
) ENGINE = InnoDB;
~~~

Primary keys and foreign keys enforce relationships between tables. The index on orders.customer_id supports looking up orders by customer. In the optimization section below, this article adds a composite index on customer_id, status, created_at for queries filtering simultaneously by customer, status, and time. The index on order_items.product_id supports finding orders containing a given product.

## 2. EXISTS Checks Whether at Least One Row Exists

### 2.1. Syntax

Basic pattern:

~~~sql
SELECT columns
FROM outer_table AS outer_alias
WHERE EXISTS (
    SELECT 1
    FROM inner_table AS inner_alias
    WHERE inner_alias.related_key = outer_alias.related_key
);
~~~

EXISTS takes a subquery. It does not care which columns the subquery selects; all that matters is whether the subquery produces at least one row.

Example finding customers who have ever placed an order:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

For each customer, MySQL checks whether any orders row has the same customer_id. If at least one order exists, the customer is included in the result.

Whether a customer has one order or a hundred orders, they still appear only once in the output because EXISTS is a true/false predicate evaluated per outer row.

### 2.2. Why Is SELECT 1 Commonly Written?

Inside EXISTS, expressions in the subquery's SELECT list are not used to build output columns. The following forms have identical existence-checking semantics:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
WHERE EXISTS (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

~~~sql
WHERE EXISTS (
    SELECT *
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

SELECT 1 is a readable convention because it signals clearly that the query only checks existence and needs no columns. It does not mean MySQL evaluates a constant column in a special way; the optimizer can transform the query to check efficiently.

There is no need to add LIMIT 1 just to make EXISTS stop after the first row. EXISTS semantics already allow the server to stop as soon as it determines whether any matching row exists; the optimizer can normally leverage that.

### 2.3. EXISTS Does Not Return Child Rows

The query:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

returns only columns from customers. If you need to display order attributes such as order_id or created_at, JOIN is usually more appropriate:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Choose EXISTS when the question is "does any match exist?"; choose JOIN when you need to pair and return data from both sides.

## 3. Correlated Subqueries: Subqueries Referencing Outer Rows

In the EXISTS example, the condition:

~~~sql
o.customer_id = c.customer_id
~~~

references alias c from the outer query. This is a correlated subquery.

You can think of the logic conceptually as:

1. Take one customer row from the outer query.
2. Use that row's customer_id as a lookup condition inside the subquery.
3. If the subquery yields at least one row, EXISTS is true.
4. If no matching row exists, EXISTS is false.
5. Proceed to evaluate the next customer.

This is a conceptual model explaining semantics, not a claim that MySQL always executes an independent subquery once per outer row. The optimizer can convert correlated EXISTS into a semijoin or pick another strategy when eligible.

### 3.1. Filtering by Multiple Conditions

Find customers who have at least one paid order:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

The subquery checks both the customer relationship and the order status simultaneously. No GROUP BY or COUNT is needed when the requirement is simply having at least one order.

### 3.2. Checking Existence Within a Time Range

Find customers with a paid order in the first quarter of 2026:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
      AND o.created_at <  '2026-04-01'
);
~~~

The time range predicate belongs inside the subquery because it defines which orders count as proof of existence. A half-open interval—inclusive of the start date and exclusive of the end date—avoids manually computing the last second of a day.

### 3.3. Checking Child Rows Satisfying Conditions on a Third Table

Find customers who have an order containing an active product:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    JOIN products AS p
        ON p.product_id = oi.product_id
    WHERE o.customer_id = c.customer_id
      AND p.active = TRUE
);
~~~

The subquery can use internal JOINs to establish a qualifying witness row. EXISTS only needs to know whether at least one matching combination of order, line item, and product exists.

## 4. NOT EXISTS Checks for Non-Existence

NOT EXISTS is true when the subquery returns zero rows. It is commonly used to find parent rows with no corresponding child rows.

Example finding customers who have never placed an order:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

For each customer, MySQL looks for matching orders. If none are found, NOT EXISTS evaluates to true and the customer is retained.

### 4.1. Finding Products Never Sold

~~~sql
SELECT
    p.product_id,
    p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
);
~~~

This query returns products that do not appear in any order line item. It does not need to count occurrences; it only needs zero matching rows.

### 4.2. Finding Orders Without Any Line Items

~~~sql
SELECT o.order_id, o.customer_id, o.created_at
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.order_id = o.order_id
);
~~~

This is a useful pattern for detecting incomplete data or parent records lacking child records.

### 4.3. Finding Customers with No Paid Orders

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

The conditions inside the subquery define exactly which child rows are excluded. The result still includes customers with zero orders as well as customers whose orders are only in non-PAID statuses.

If the requirement is "has placed an order, but has no PAID orders," combine EXISTS and NOT EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS any_order
    WHERE any_order.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS paid_order
    WHERE paid_order.customer_id = c.customer_id
      AND paid_order.status = 'PAID'
);
~~~

The two predicates express two independent requirements: at least one order of any kind, and zero paid orders.

## 5. How Do EXISTS and JOIN Differ?

JOIN combines rows from two tables. If a customer has multiple orders, JOIN produces one result row per matching order. EXISTS only checks whether matching rows exist, so each outer customer row is evaluated as a single unit.

JOIN example:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

A customer with five orders can appear five times.

EXISTS example:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Each customer appears only once regardless of how many orders they have.

| Need | Typically Suitable Construct |
|---|---|
| Retrieve columns from both tables | JOIN |
| Retrieve customers and customer details for those with orders | EXISTS |
| Retrieve customers without any orders | NOT EXISTS |
| Count orders per customer | JOIN + GROUP BY or an aggregate query |
| Check whether at least one matching row exists | EXISTS |
| Check that no matching row exists | NOT EXISTS |

You can combine JOIN with DISTINCT to get unique customers:

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

The output may match EXISTS, but JOIN first produces all matching row pairs before DISTINCT removes duplicates. DISTINCT can require an extra deduplication pass or temporary structure. EXISTS expresses the intent more directly when child columns are not needed.

There is no rule that EXISTS is always faster than JOIN. The optimizer can transform both forms; choose based on data semantics first, then check EXPLAIN on your actual workload.

## 6. EXISTS vs. IN

EXISTS and IN can express many equivalent membership queries.

Finding customers with orders using IN:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Written with EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

With a non-NULL customer_id key and equality comparison as shown, both queries usually return the same customer set. However, you must understand the NULL semantics of IN and NOT IN before substituting them.

### 6.1. IN with a Subquery

IN tests whether an expression equals any value in the set returned by the subquery:

~~~sql
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders AS o
)
~~~

IN fits nicely when expressing membership in a set of values. It works with either literal lists or subqueries.

### 6.2. EXISTS Checks for Matching Rows

EXISTS tests whether the subquery produces any rows:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

EXISTS is often more natural when the subquery needs to reference multiple columns from the outer row or express multi-condition relationships.

## 7. Beware of NOT IN and NULL

A crucial difference between NOT IN and NOT EXISTS appears when the subquery set contains NULL.

Suppose a subquery returns the set:

~~~text
10, 20, NULL
~~~

The condition:

~~~sql
30 NOT IN (10, 20, NULL)
~~~

cannot evaluate to TRUE. MySQL uses three-valued logic: comparing against NULL yields UNKNOWN, and WHERE only keeps rows where the predicate evaluates to TRUE. Consequently, the query may return none of the rows the author expected.

Example staging table with a nullable reference column:

~~~sql
CREATE TABLE imported_order_refs (
    customer_id BIGINT UNSIGNED NULL
) ENGINE = InnoDB;
~~~

If this table contains even a single NULL, the following query may return zero customers:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT r.customer_id
    FROM imported_order_refs AS r
);
~~~

The reason is that for any customer_id not present among the non-NULL values, comparing against NULL still turns NOT IN into UNKNOWN.

Rewritten with NOT EXISTS:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM imported_order_refs AS r
    WHERE r.customer_id = c.customer_id
);
~~~

A NULL row in imported_order_refs fails the equality check against the customer's customer_id, so it does not prevent other non-matching customers from appearing in the result. This is why NOT EXISTS is generally safer and easier to reason about for anti-join queries when child columns may be NULL.

### 7.1. If Using NOT IN, Handle NULLs Intentionally

If business semantics allow ignoring NULL values inside the inner set, filter them out explicitly:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT r.customer_id
    FROM imported_order_refs AS r
    WHERE r.customer_id IS NOT NULL
);
~~~

Adding IS NOT NULL changes how the set is evaluated and must align with business rules. When the goal is "no child row satisfies the comparison," NOT EXISTS usually expresses it more directly.

### 7.2. NULL on the Outer Side

NOT EXISTS also follows clear rules when the outer value is NULL. Example:

~~~sql
SELECT r.customer_id
FROM imported_order_refs AS r
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = r.customer_id
);
~~~

If r.customer_id is NULL, the comparison o.customer_id = r.customer_id is never TRUE for any row. The subquery finds no match, so NOT EXISTS evaluates to TRUE and the NULL row is returned.

If you do not want outer rows with NULL keys, add an explicit filter:

~~~sql
WHERE r.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = r.customer_id
  )
~~~

If business rules treat two NULL values as identical for reconciliation, MySQL provides the null-safe equality operator <=>. Use it only when that is genuinely the business rule; normal foreign key relationships do not treat NULL as a reference key.

## 8. LEFT JOIN ... IS NULL as an Anti-Join Pattern

Another way to find unrelated rows is a LEFT JOIN followed by checking whether a right-side column is NULL:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

LEFT JOIN preserves all customers. When no order matches, orders columns are padded with NULL. WHERE o.order_id IS NULL retains customers for whom no order was found.

Check a right-side column guaranteed NOT NULL whenever a real row exists—typically the primary key such as order_id. Never check a nullable column like status IS NULL, because a real order row in another schema might have a NULL status, falsely classifying that row as unmatched.

Compare:

~~~sql
-- Using NOT EXISTS
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);

-- Using LEFT JOIN ... IS NULL
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

Both forms can yield identical results when the join predicate and checked column are chosen properly. NOT EXISTS usually states "no related row exists" more explicitly and avoids accidentally testing a nullable column.

## 9. EXISTS Does Not Need to Count All Rows

When you only need to know whether a matching row exists, use EXISTS instead of COUNT(*) > 0:

~~~sql
-- Directly expresses an existence check
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

A count-based version:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
) > 0;
~~~

The second form requires computing the count of matching rows to compare. EXISTS only needs to confirm at least one row exists. The optimizer may optimize both forms in certain cases, yet EXISTS expresses the true goal and avoids demanding a count when none is needed.

A common mistake is writing:

~~~sql
WHERE EXISTS (
    SELECT COUNT(*)
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
~~~

Never use COUNT(*) inside EXISTS like this to test existence. A subquery with an aggregate and no GROUP BY still returns one summary row even when COUNT is 0; thus EXISTS evaluates to true every time. Use SELECT 1 with row predicates, or compare COUNT(*) > 0 as a scalar expression if an actual count is needed.

## 10. EXISTS in Common Business Requirements

### 10.1. Customers with Orders in a Recent Window

If you only need to know whether a customer placed an order in the last 30 days, use EXISTS with a timestamp boundary defined by the application or query:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.created_at >= CURRENT_DATE - INTERVAL 30 DAY
);
~~~

This illustrates placing a time predicate inside the subquery. In multi-timezone systems, align session time zones and the semantics of created_at before defining "last 30 days."

### 10.2. Customers with at Least One High-Value Order

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.total >= 10000000
);
~~~

There is no need to compute MAX(total) if you only ask whether any order meets the threshold. If you also need the maximum order value, use an aggregate or row-selection query.

### 10.3. Products Not Appearing in Any Paid Order

~~~sql
SELECT p.product_id, p.product_name
FROM products AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items AS oi
    JOIN orders AS o
        ON o.order_id = oi.order_id
    WHERE oi.product_id = p.product_id
      AND o.status = 'PAID'
);
~~~

This query retains products that have no line items in any paid order. Those products may still appear in draft or canceled orders.

### 10.4. Finding Customers Who Have Orders but No Delivered Orders

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'DELIVERED'
);
~~~

Two predicates express combined conditions cleanly without counting or grouping orders.

### 10.5. Finding Customers Who Purchased All Required Products

An advanced pattern uses double NOT EXISTS to express "there exists no required product that the customer has not purchased."

Suppose a table required_products(product_id) lists the required products:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_products AS rp
    WHERE NOT EXISTS (
        SELECT 1
        FROM orders AS o
        JOIN order_items AS oi
            ON oi.order_id = o.order_id
        WHERE o.customer_id = c.customer_id
          AND oi.product_id = rp.product_id
          AND o.status = 'PAID'
    )
);
~~~

Reading from the inside out:

1. The inner NOT EXISTS finds required products the customer has not bought in a PAID order.
2. The outer NOT EXISTS verifies that no such missing required product exists.
3. If no required product is missing, the customer is selected.

If required_products is empty, the outer condition holds for every customer. This follows standard logical semantics for "purchased every element in an empty set"; if business logic does not want that outcome, separately verify that the required list is non-empty.

## 11. EXISTS and Semijoin / Antijoin Transformations

EXISTS corresponds conceptually to a **semijoin**: keeping an outer row if at least one matching inner row exists, without duplicating the outer row per matching inner row.

NOT EXISTS corresponds conceptually to an **antijoin**: keeping an outer row if zero matching inner rows exist.

MySQL can transform certain IN or EXISTS queries into a semijoin to select an optimal execution strategy. For negated queries, the optimizer can also apply antijoin transformations under certain conditions. Eligibility depends on query structure, NULL semantics, MySQL version, and provable equivalence.

Semijoin strategies MySQL can choose include:

- **FirstMatch**: stops scanning for further matching rows as soon as the first match for the current combination is found.
- **Duplicate Weedout**: removes duplicate rows produced during join execution to preserve semijoin semantics.
- **LooseScan**: leverages index ordering to pick one representative per value group.
- **Materialization**: builds an intermediate subquery result set for lookups.
- **Table Pullout**: pulls a subquery table out into the outer join when conditions permit.

These are optimizer choices, not strategies you can force simply by writing EXISTS. Always inspect EXPLAIN instead of assuming a particular strategy.

## 12. Indexes for Correlated EXISTS and NOT EXISTS

For the query:

~~~sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND o.created_at >= '2026-01-01'
);
~~~

The lookup conditions on orders are:

- Match customer_id against the outer row.
- Filter status by equality.
- Filter created_at by range.

A composite index:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

can support finding matching rows in column order: equality on customer_id, equality on status, then range on created_at. How much an index helps still depends on data volume, value distribution, statistics, and workload.

For a query checking whether a product appears in order_items:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM order_items AS oi
    WHERE oi.product_id = p.product_id
)
~~~

an index starting with product_id supports finding line items by product. Conversely, if a query probes by order_id first, the primary key (order_id, product_id) fits that lookup path.

Guidelines:

1. Identify the join column linking the outer query and subquery.
2. Identify additional filter predicates inside the subquery.
3. Consider composite indexes ordered with equality columns first and range columns afterward.
4. Check existing indexes to avoid redundant ones.
5. Measure with EXPLAIN and realistic data before committing.

Do not add an index for every single EXISTS predicate. Indexes add overhead to INSERT, UPDATE, DELETE, and storage.

## 13. Reading Execution Plans

Use EXPLAIN to see how MySQL plans to execute the query:

~~~sql
EXPLAIN
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Key details to inspect:

- Which table is read first.
- Access types and selected indexes.
- Estimated rows to examine.
- Which predicates use index lookups versus post-filtering.
- Whether the subquery is transformed into a semijoin or materialized.

With EXPLAIN JSON or TREE formats, you can observe more detail about subqueries, nested loops, semijoins, or materialization depending on version.

Where supported, EXPLAIN ANALYZE reports actual execution metrics such as timings and rows flowing through each iterator. This command actually executes the query; run it only in suitable environments on queries whose cost has been assessed.

When a query is slow:

1. Check indexes on the correlation column in the child table.
2. Verify whether filter predicates can use the index.
3. Compare estimated rows with actual rows.
4. Refresh statistics if optimizer estimates are severely off.
5. Re-evaluate index design across the full workload, not just one query.

## 14. Common Misconceptions

**"EXISTS must return a column with a value."** No. EXISTS only cares whether a row exists; SELECT 1 is merely a common, readable convention.

**"EXISTS always runs the subquery once per outer row."** That is a simplified logical model. The optimizer can transform the query into a semijoin or choose another execution strategy.

**"EXISTS is always faster than JOIN."** There is no absolute rule. Choose by semantics—EXISTS to check existence, JOIN to retrieve combined data—then measure the execution plan.

**"Using JOIN always gives one row per parent row."** No. One parent row can match multiple child rows and get multiplied. When you only need an existence check, EXISTS naturally avoids that issue.

**"NOT IN and NOT EXISTS are always equivalent."** No. A NULL in the inner set can make NOT IN evaluate to UNKNOWN and drop unmatched outer rows. Correlated NOT EXISTS is usually better suited for anti-joins.

**"NOT EXISTS drops all rows with NULL keys."** No. If the outer key is NULL, standard equality matches nothing, making NOT EXISTS evaluate to true. Add IS NOT NULL if business logic requires excluding them.

**"EXISTS with SELECT COUNT(*) is the optimal way to count."** No. An ungrouped aggregate subquery still returns one summary row even when COUNT is 0, so EXISTS can always be true. Use SELECT 1 to test row presence.

**"Only the parent table needs an index."** No. Correlated subqueries frequently probe the child table by its linking key, making inner-table indexes critical.

## 15. Checklist for Choosing and Optimizing Existence Queries

Before writing a query, check:

1. Do you need columns from the child table, or only a yes/no answer?
2. Can one outer row match multiple child rows?
3. Which correlation predicate links the subquery to the outer row?
4. Are there status, time, or attribute filters?
5. Which columns can be NULL, and how does NULL affect the result?
6. Does NOT EXISTS or LEFT JOIN ... IS NULL express the intent more clearly?
7. Are you using NOT IN over a set that might contain NULL?
8. Do child-table indexes support the correlation and filter predicates?
9. Does EXPLAIN show semijoin, antijoin, materialization, or another access path?
10. Does the result preserve the expected outer row count without unintended multiplication?

Putting it together: find customers who have a PAID order in 2026 but have never had a DELIVERED order:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS paid
    WHERE paid.customer_id = c.customer_id
      AND paid.status = 'PAID'
      AND paid.created_at >= '2026-01-01'
      AND paid.created_at <  '2027-01-01'
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS delivered
    WHERE delivered.customer_id = c.customer_id
      AND delivered.status = 'DELIVERED'
);
~~~

EXISTS confirms at least one PAID order within the date window. NOT EXISTS confirms zero DELIVERED orders at any time. Both subqueries express independent criteria for the same customer.

## Conclusion

EXISTS checks whether a subquery returns at least one row; NOT EXISTS checks that no matching row exists. They are especially valuable for correlated subqueries, semijoins, and anti-joins: filtering parent rows by child-row presence without duplicating outer results.

Use EXISTS when you only need to know something exists, NOT EXISTS when you need to confirm absence, JOIN when you need data from both sides, and IN when testing membership in a set of values. Watch out for NULLs in NOT IN, index correlation columns, and inspect EXPLAIN to verify how MySQL executes the query.
