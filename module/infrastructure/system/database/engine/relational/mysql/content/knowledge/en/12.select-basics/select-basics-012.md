# Verifying Queries with Minimal Data and Edge Cases

A `SELECT` statement that runs without errors does not prove the query returns the right results. A `WHERE` condition might drop rows, a `JOIN` might multiply data, `NULL` might make a filter behave unexpectedly, and an `ORDER BY` without a tie-breaker column might cause row order to shift across runs. To trust a query, you must test it with a small dataset specifically designed to expose potential bugs.

Verifying a query with minimal data means building a small fixture, defining the expected output beforehand, and comparing it against actual results. Each row in the fixture should represent an important scenario: normal data, boundary values, `NULL`, zero values, duplicate content, unmatched parent rows, or exact boundary timestamps. A small, purposeful example usually uncovers bugs far faster than running a query against a large database without knowing what the exact answer should be.

This lesson belongs to the `DATABASE_MYSQL` module, where you practice table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan reading, and query optimization. The goal is to verify `SELECT` correctness first, and only then evaluate execution plans and performance on appropriately scaled data.

After this lesson, you will be able to:

- Design a small fixture to test a query purposefully.
- Define the expected result before running SQL.
- Test empty sets, single-row, multi-row, duplicate, `NULL`, and zero-value cases.
- Catch bugs in `JOIN`, `WHERE`, `GROUP BY`, aggregates, and time-range conditions.
- Ensure sorting and pagination outputs have deterministic ordering.
- Compare actual results against expected results using SQL or application-layer tests.
- Distinguish correctness verification from performance inspection with `EXPLAIN`.

## 1. Workflow for Verifying a Query

Before creating a fixture, rephrase the query as a concrete business question. For example: "For each customer, what are the total number of paid orders and the total paid amount, including customers with no orders?" This question immediately reveals the cases to test: multiple orders, orders in excluded statuses, `NULL` amounts, zero totals, and customers without orders.

A practical workflow consists of these steps:

1. **Define the output contract:** which columns and types does the query return, one row or multiple rows, and must unmatched rows be preserved?
2. **List scenarios:** happy path, low/high boundaries, `NULL`, empty set, duplicates, equal values, and invalid data.
3. **Create a minimal fixture:** include only the rows needed to distinguish the scenarios.
4. **Write the expected result first:** record the exact rows and values that must appear, including `NULL`s and ordering when order is part of the contract.
5. **Run the query and compare:** do not just check row count; compare every important value.
6. **Test bug-inducing variants:** change `LEFT JOIN` to `INNER JOIN`, drop a condition, replace `IS NULL` with `= NULL`, or drop the tie-breaker from `ORDER BY` to confirm the test catches discrepancies.
7. **Inspect the execution plan separately:** once output is correct, use `EXPLAIN` to evaluate access paths and indexes.

A good fixture does not need to simulate all of production. It should be as small as possible while still distinguishing correct behavior from broken behavior.

## 2. Creating a Minimal Fixture for Practice

The running example uses two tables: customers and orders. We intentionally include duplicate amounts, a `NULL` amount, a zero amount, an excluded status, and a customer with no orders.

Run this entire section in the same MySQL session because temporary tables exist only within the connection that created them.

```sql
DROP TEMPORARY TABLE IF EXISTS orders;
DROP TEMPORARY TABLE IF EXISTS customers;

CREATE TEMPORARY TABLE customers (
    customer_id INT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NULL,
    placed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_status_date (customer_id, status, placed_at)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name) VALUES
(1, 'An'),
(2, 'Binh'),
(3, 'Chi'),
(4, 'Dung');

INSERT INTO orders (order_id, customer_id, status, amount, placed_at) VALUES
(101, 1, 'PAID',    100.00, '2026-11-19 00:00:00.000000'),
(102, 1, 'PENDING',  20.00, '2026-11-19 12:00:00.000000'),
(103, 1, 'PAID',      NULL, '2026-11-19 23:59:59.999999'),
(104, 2, 'PAID',    150.00, '2026-11-20 00:00:00.000000'),
(105, 2, 'PAID',    150.00, '2026-11-20 08:30:00.000000'),
(106, 3, 'PAID',      0.00, '2026-11-19 12:00:00.000000');
```

The fixture covers these intentional scenarios:

| Row | Scenario Being Tested |
| --- | --- |
| Customer 1 | Multiple orders, including one `PENDING` order, one normal amount, and one `NULL` amount |
| Customer 2 | Two paid orders with the same amount to test duplicate values and tie ordering |
| Customer 3 | One paid order with an amount of zero |
| Customer 4 | No orders, to test `LEFT JOIN` |
| Order 101 | Exactly at the start of 2026-11-19 |
| Order 103 | Exactly at the final microsecond of 2026-11-19 |
| Order 104 | Exactly at the start of the next day, which must fall outside the 2026-11-19 range |

This is a test fixture, not a production schema. Foreign keys are omitted so the examples can focus on how `SELECT` handles rows and relationships; both temporary tables are automatically dropped when the session ends.

## 3. Writing the Expected Result Before Running the Query

Suppose the requirement is: "List every customer, their count of paid orders, their count of orders with a provided amount, and their total paid amount."

Expected result:

| customer_id | customer_name | paid_order_count | amount_count | paid_total |
| ---: | --- | ---: | ---: | ---: |
| 1 | An | 2 | 1 | 100.00 |
| 2 | Binh | 2 | 2 | 300.00 |
| 3 | Chi | 1 | 1 | 0.00 |
| 4 | Dung | 0 | 0 | `NULL` |

Explanation:

- Customer 1 has two `PAID` orders, but one has `amount = NULL`. `COUNT(order_id)` is 2, `COUNT(amount)` is 1, and `SUM(amount)` is 100.00.
- Customer 2 has two orders each worth 150.00; both are counted, totaling 300.00.
- Customer 3 has one order worth 0.00. The sum is 0, distinct from having no values to sum.
- Customer 4 has no `PAID` orders. `LEFT JOIN` keeps the customer, order count is 0, and `SUM()` returns `NULL` because there are no input values.

Writing the expected table upfront helps uncover ambiguous requirements early. For instance, does "total amount" include `PENDING` orders? Does `NULL` mean unknown amount or count as 0? Those decisions must come from business rules, never inferred from SQL output.

## 4. Verifying JOINs and Filter Conditions

### 4.1. Place Right-Table Conditions in ON When Preserving Unmatched Rows

Correct query for the requirement in Section 3:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COUNT(o.amount) AS amount_count,
    SUM(o.amount) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

The `o.status = 'PAID'` condition sits inside `ON` because the requirement is to keep all customers and match paid orders if present. When no matching order is found, columns from `orders` receive `NULL`, yet the customer row still appears.

Bug-prone query:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

The condition in `WHERE` removes rows where `o.status` is `NULL`, causing customer 4 to vanish. The output effectively collapses to an `INNER JOIN` for this condition. Having an orderless customer in the fixture catches this bug immediately.

### 4.2. COUNT(*) Differs from COUNT(Right-Table Column)

With a `LEFT JOIN`, a customer without orders still produces an output row with `NULL` in `orders` columns:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_row_count,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

For customer 4, `COUNT(*)` is 1 because the left row exists; `COUNT(o.order_id)` is 0 because `order_id` in the padded row is `NULL`. When counting child records after a `LEFT JOIN`, count a non-nullable key column of the child table.

### 4.3. Use EXISTS When Only Checking for Related Rows

If the requirement is "list customers with at least one paid order," there is no need to join all orders and deduplicate:

```sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Expected result includes customers 1, 2, and 3. Customer 4 does not appear. `EXISTS` directly expresses existence checking and avoids multiplying a customer when multiple matching orders exist.

## 5. Checking NULL, 0, Empty Strings, and Empty Sets

### 5.1. NULL Is Not 0

SQL uses three-valued logic: a condition can be `TRUE`, `FALSE`, or `UNKNOWN`. Comparing against `NULL` with the `=` operator never yields `TRUE`.

```sql
-- Does not find rows where amount is NULL
SELECT order_id
FROM orders
WHERE amount = NULL;

-- Correctly finds rows where amount is NULL
SELECT order_id
FROM orders
WHERE amount IS NULL;

-- MySQL-specific NULL-safe comparison operator
SELECT order_id
FROM orders
WHERE amount <=> NULL;
```

The latter two queries return order 103. `<=>` is MySQL's NULL-safe equality operator; in portable SQL, use `IS NULL` to check for null values.

The condition `amount <> 100.00` also skips rows where `amount IS NULL`, because the comparison evaluates to `UNKNOWN`. If business rules want rows without an amount included, write explicitly:

```sql
WHERE amount <> 100.00 OR amount IS NULL
```

### 5.2. NOT IN Can Be Affected by NULL

Create an exclusion list containing a `NULL` value:

```sql
DROP TEMPORARY TABLE IF EXISTS excluded_customers;

CREATE TEMPORARY TABLE excluded_customers (
    customer_id INT UNSIGNED NULL
) ENGINE = InnoDB;

INSERT INTO excluded_customers (customer_id) VALUES (1), (NULL);
```

The following query does not return the customers authors usually expect:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM excluded_customers AS e
);
```

Because the subset contains `NULL`, `NOT IN` can evaluate to `UNKNOWN` for non-matching values, so zero rows pass `WHERE`. For exclusion relationships, `NOT EXISTS` is usually safer:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM excluded_customers AS e
    WHERE e.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Expected result: 2, 3, and 4. The `NULL` row in the exclusion table matches no customer ID and does not break the existence check.

### 5.3. Empty Strings and Whitespace-Only Strings

The empty string `''`, a string containing spaces, and `NULL` are three distinct values:

```sql
SELECT
    '' IS NULL AS empty_is_null,
    '   ' IS NULL AS spaces_are_null,
    NULL IS NULL AS null_is_null,
    NULLIF('', '') IS NULL AS empty_after_nullif,
    NULLIF(TRIM('   '), '') IS NULL AS spaces_after_trim;
```

If business rules treat empty or whitespace-only strings as missing values, normalize explicitly with `TRIM()` and `NULLIF()` or validate in the application layer. Do not assume MySQL automatically converts empty strings to `NULL`.

### 5.4. Zero Rows vs. One Aggregate Row with Value 0

```sql
-- No detail rows
SELECT order_id, amount
FROM orders
WHERE customer_id = 999;

-- Aggregate without GROUP BY still returns one row
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS amount_sum
FROM orders
WHERE customer_id = 999;
```

The first query returns an empty result set. The second returns one row with `row_count = 0` and `amount_sum = NULL`. Using `COALESCE(SUM(amount), 0)` displays 0, though that is a reporting semantics choice. Distinguish "no transactions" from "transactions present summing to 0" when business logic requires it.

## 6. Checking Duplicate Data and Row-Multiplying JOINs

Orders 104 and 105 share the same `amount = 150.00`, yet they are two distinct orders because their `order_id` values differ. A total query must include both:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM orders
WHERE customer_id = 2
  AND status = 'PAID'
GROUP BY customer_id;
```

Expected result: `order_count = 2`, `total_amount = 300.00`. If you used `SUM(DISTINCT amount)`, the result would be 150.00, violating the requirement to sum all orders. `DISTINCT` deduplicates values, not records with distinct keys.

When joining multiple one-to-many child tables, a parent row can multiply by the product of child row counts. For example, an order with 2 line items and 3 payments joined directly to both tables can produce 6 rows. Then `COUNT(order_id)` or `SUM(line_total)` can be inflated. How to verify:

- Build a fixture with 2 rows in the first child table and 3 rows in the second child table.
- Count rows after each join step.
- Compare totals before and after adding each join.
- Consider aggregating each child table to one row per parent key before joining.

Example of pre-aggregating before joining:

```sql
SELECT
    o.order_id,
    item_totals.item_total,
    payment_totals.payment_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS item_total
    FROM order_items
    GROUP BY order_id
) AS item_totals
    ON item_totals.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, SUM(amount) AS payment_total
    FROM payments
    GROUP BY order_id
) AS payment_totals
    ON payment_totals.order_id = o.order_id;
```

This pattern illustrates a schema with `order_items` and `payments`; these tables are not part of the Section 2 fixture. Each derived table holds at most one row per `order_id`, preventing multiplication across the two one-to-many relationships.

## 7. Testing Boundary Conditions and Operators

### 7.1. Numeric Boundary Comparisons

For range conditions, verify whether both endpoints are inclusive. `BETWEEN` includes both bounds:

```sql
SELECT order_id, amount
FROM orders
WHERE amount BETWEEN 100.00 AND 150.00
ORDER BY order_id;
```

The equivalent condition is `amount >= 100.00 AND amount <= 150.00`. Test values just below, exactly equal to, and just above each threshold. With `DECIMAL`, test values such as `99.99`, `100.00`, and `100.01` to verify boundaries clearly.

### 7.2. Combining AND and OR

Do not rely on memory or prose reading to infer logical precedence. Use parentheses whenever conditions mix `AND` and `OR`:

```sql
SELECT order_id, status, amount
FROM orders
WHERE status = 'PAID'
  AND (amount = 0 OR amount >= 100.00)
ORDER BY order_id;
```

The fixture confirms orders 101, 104, 105, and 106 are selected; order 103 has `amount` `NULL` and does not match, while order 102 fails the status check. Try removing the parentheses and comparing results to observe operator precedence bugs.

### 7.3. LIKE and Wildcards

In `LIKE`, `%` matches any sequence of characters and `_` matches a single character. If users enter wildcard characters literally, escape them:

```sql
SELECT customer_name
FROM customers
WHERE customer_name LIKE 'B%'
ORDER BY customer_id;
```

When searching for strings containing literal `%` or `_`, define an escape character and apply the same rule in the query. Never concatenate user input directly into SQL; use `PreparedStatement` and escape wildcards according to search requirements.

## 8. Testing Date/Time Boundaries

With a `DATETIME(6)` column, the condition "all orders on 2026-11-19" should be written as a half-open interval:

```sql
SELECT order_id, placed_at
FROM orders
WHERE placed_at >= '2026-11-19 00:00:00'
  AND placed_at <  '2026-11-20 00:00:00'
ORDER BY placed_at, order_id;
```

Expected result: orders 101, 102, 103, and 106. Order 101 at the exact start of the day is included; order 103 at the final microsecond of the day is included; order 104 at the exact start of the next day is excluded.

Do not write:

```sql
WHERE placed_at BETWEEN '2026-11-19 00:00:00'
                     AND '2026-11-19 23:59:59'
```

This condition misses values with fractional microseconds after `23:59:59.000000`. Also avoid `DATE(placed_at) = '2026-11-19'` when aiming to use a regular B-tree index on `placed_at`; applying a function to the column can make the predicate non-sargable.

If the column is `TIMESTAMP`, compute bounds in the business timezone and pass corresponding timestamps according to session settings. Do not treat UTC midnight as local start-of-day if the requirement specifies another timezone.

## 9. Testing ORDER BY, Ties, and LIMIT

A query without `ORDER BY` makes no commitment on row order. Any observed ordering in one run is not a SQL contract.

Customer 2's two orders share the same amount. When sorting descending by amount, add a unique tie-breaker key:

```sql
SELECT order_id, amount
FROM orders
WHERE customer_id = 2
ORDER BY amount DESC, order_id ASC;
```

Expected order: 104 before 105. Writing only `ORDER BY amount DESC` allows tied rows to appear in varying order across execution plans.

For pagination:

```sql
SELECT order_id, placed_at
FROM orders
ORDER BY placed_at ASC, order_id ASC
LIMIT 2 OFFSET 2;
```

Adding `order_id` keeps order deterministic when multiple rows share the same `placed_at`. When data changes between requests, offset pagination can still skip or repeat rows as positions shift. For large or frequently changing datasets, consider keyset pagination based on the last sort-key pair.

Test edge cases: `LIMIT 0`, zero rows, fewer rows than page size, exact page size, and more rows than page size. Verify that offset is 0-based and confirm how the API handles page indexing.

## 10. Checking GROUP BY and Aggregates

Aggregates follow specific rules for `NULL` and empty sets:

| Expression | Behavior to Verify |
| --- | --- |
| `COUNT(*)` | Counts rows, including rows with NULL columns |
| `COUNT(column)` | Counts only rows where `column` is non-NULL |
| `SUM(column)` | Ignores NULL; returns NULL if there are no values to sum |
| `AVG(column)` | Ignores NULL; returns NULL if there are no numeric values |
| `MIN()` / `MAX()` | Ignores NULL; returns NULL if there are no values |
| `COUNT(DISTINCT column)` | Counts distinct values, ignoring NULL |

Test on the fixture:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(DISTINCT amount) AS distinct_amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM orders
WHERE customer_id = 1
  AND status = 'PAID';
```

Expected result: `row_count = 2`, `amount_count = 1`, `distinct_amount_count = 1`, `amount_sum = 100.00`, `amount_avg = 100.00`, `min_amount = 100.00`, `max_amount = 100.00`. Order 103 has `amount` `NULL` and is therefore excluded from aggregates over the `amount` column.

With `GROUP BY`, each group appears only if it has at least one input row. If the input set is empty, a query with `GROUP BY` returns 0 groups; an ungrouped aggregate query usually returns one summary row. Test both cases when an API must distinguish "no groups" from "a group summing to 0."

In MySQL, keeping `ONLY_FULL_GROUP_BY` enabled catches many queries that select ungrouped columns or columns not validly functionally dependent on grouping columns. Do not disable this mode just to make a query run; decide which columns must be aggregated or added to `GROUP BY`.

## 11. Comparing Actual Results Against Expected Results

For critical queries, you can store expected results in a fixture table and diff the two datasets. The approach below compares values by primary key and uses `<=>` for NULL-safe comparison.

Create the expected table:

```sql
DROP TEMPORARY TABLE IF EXISTS expected_customer_totals;
DROP TEMPORARY TABLE IF EXISTS actual_customer_totals;

CREATE TEMPORARY TABLE expected_customer_totals (
    customer_id INT UNSIGNED NOT NULL,
    paid_order_count INT NOT NULL,
    amount_count INT NOT NULL,
    paid_total DECIMAL(12, 2) NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE actual_customer_totals LIKE expected_customer_totals;

INSERT INTO expected_customer_totals VALUES
(1, 2, 1, 100.00),
(2, 2, 2, 300.00),
(3, 1, 1,   0.00),
(4, 0, 0,    NULL);
```

Insert the output of the query under test into the actual table:

```sql
INSERT INTO actual_customer_totals
    (customer_id, paid_order_count, amount_count, paid_total)
SELECT
    c.customer_id,
    COUNT(o.order_id),
    COUNT(o.amount),
    SUM(o.amount)
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id;
```

Find missing or mismatched rows:

```sql
SELECT 'missing_or_different' AS problem, e.customer_id
FROM expected_customer_totals AS e
LEFT JOIN actual_customer_totals AS a
    ON a.customer_id = e.customer_id
WHERE a.customer_id IS NULL
   OR NOT (
       a.paid_order_count <=> e.paid_order_count
       AND a.amount_count <=> e.amount_count
       AND a.paid_total <=> e.paid_total
   )

UNION ALL

SELECT 'unexpected' AS problem, a.customer_id
FROM actual_customer_totals AS a
LEFT JOIN expected_customer_totals AS e
    ON e.customer_id = a.customer_id
WHERE e.customer_id IS NULL
ORDER BY problem, customer_id;
```

If the query returns zero rows, the two result sets match across the checked columns. If any rows appear, the `problem` column flags missing/different rows or unexpected rows.

This technique works when each output row has a unique identifying key. If results can contain multiple identical rows with no distinguishing key, compare occurrence counts of each value tuple (multiset comparison) rather than relying solely on `DISTINCT` or simple anti-joins.

In Java applications, verify via integration tests: load fixtures inside a transaction, invoke the repository, compare the returned DTO list against an expected list, check order if the API guarantees ordering, and roll back or clean up afterward. Never assert only `list.size()`; two lists with identical row counts can still contain wrong values.

## 12. Separating Correctness Verification from Performance Testing

A query can return right answers slowly; conversely, a fast query that drops or multiplies rows is still wrong. Keep the two checks separate.

**Correctness verification:**

- Use a small fixture with clear expected results.
- Check individual column values, row counts, `NULL`s, duplicates, and ordering.
- Test empty inputs, boundary values, and unmatched cases.
- Test the same query against bug-exposing data variants.

**Performance testing:**

- Run `EXPLAIN` to inspect access type, key, estimated rows, and Extra.
- Check whether indexes fit filter, join, and sort conditions.
- Benchmark on datasets whose scale and distribution resemble production.
- Use `EXPLAIN ANALYZE` when actual query execution is acceptable.
- Measure multiple times, observing variance, caching effects, and concurrent load.

A minimal fixture proves logic on selected scenarios, but is insufficient for drawing performance conclusions over millions of records. Small datasets often cause the optimizer to choose a table scan; that alone does not prove a production index is useless.

## 13. Common Testing Mistakes

| Testing Mistake | Why It Is Insufficient | How to Improve |
| --- | --- | --- |
| Running a query once against production data | Unknown ground truth and hard to reproduce | Build a small fixture and expected results |
| Asserting only row count | Values can be wrong even when row count matches | Compare keys and all important columns |
| Having no NULL rows | Misses SQL three-valued logic bugs | Add NULLs and verify `IS NULL` and aggregates |
| Having no duplicate values | Fails to catch JOIN multiplication or wrong DISTINCT usage | Add two rows with distinct keys but identical values |
| Having no parent row without children | Misses `LEFT JOIN` accidentally turned into `INNER JOIN` | Include at least one parent row with no child rows |
| Having no zero values | Easy to confuse 0 with NULL or missing rows | Test 0, NULL, and empty sets separately |
| Skipping time-boundary checks | Can miss microseconds or spill into the next day | Test range start, range end, and next-range start |
| Relying on default ordering | Order is unguaranteed without `ORDER BY` | Add a unique tie-breaker key |
| Benchmarking on tiny data and concluding speed | Cardinality and distribution differ from production | Benchmark separately on representative data |
| Using `DISTINCT` to hide JOIN errors | May mask multiplied data instead of fixing the root cause | Check cardinality per relationship and aggregate before joining |

## 14. Checklist Before Trusting a SELECT

- [ ] Business question and output contract are clearly written down.
- [ ] Fixture includes normal, boundary, `NULL`, 0, duplicate, and unmatched cases as needed.
- [ ] Expected results are defined before running the query.
- [ ] Right-table filter predicates in `LEFT JOIN` are placed in the proper clause.
- [ ] Child rows are counted via non-nullable columns, without confusing `COUNT(*)` and `COUNT(child.id)`.
- [ ] Aggregates are tested against empty sets and `NULL` values.
- [ ] `NOT IN`, `NOT EXISTS`, `IN`, and `NULL` operations are verified for exact semantics.
- [ ] Numeric and date/time boundary conditions are tested.
- [ ] `ORDER BY` includes a tie-breaker key for deterministic order where needed.
- [ ] Pagination is tested with rows sharing identical sort values.
- [ ] Results are compared by value, not merely by row count.
- [ ] Performance checks using `EXPLAIN`/representative data are separated from logic verification.

## 15. Practice Exercises

1. Run the fixture in Section 2 and write down the expected result of the aggregate query before executing SQL.
2. Move `o.status = 'PAID'` from `ON` to `WHERE`. Record which customer disappears and explain why.
3. Replace `COUNT(o.order_id)` with `COUNT(*)`. Compare customers with and without orders.
4. Test `amount = NULL`, `amount IS NULL`, and `amount <=> NULL`. Explain each query's output.
5. Add `NULL` to an exclusion set. Compare `NOT IN` against `NOT EXISTS`.
6. Compare `SUM(amount)` against `SUM(DISTINCT amount)` for customer 2.
7. Test a time condition with `BETWEEN` ending at `23:59:59` versus a half-open interval. Identify the missed order.
8. Remove `order_id` from `ORDER BY amount DESC`. Explain why the order between orders 104 and 105 is not guaranteed.
9. Create expected/actual temporary tables and run the comparison query in Section 11. Intentionally alter one expected value to confirm the check catches the mismatch.
10. Run `EXPLAIN` on a query filtering by `customer_id`, `status`, and `placed_at`; observe whether the composite index in the fixture is selected. Do not draw production performance conclusions from a tiny fixture.

## 16. Completion Criteria

You have completed this lesson when you can construct a small fixture that distinguishes key scenarios, write expected results upfront, test `NULL`/0/empty-set/duplicate cases, spot bugs caused by `JOIN` condition placement and aggregates, verify date/time boundaries, ensure deterministic pagination order, and diff actual results against expected results. You should also be able to explain why logic verification with minimal data and performance evaluation with representative data are two separate activities.
