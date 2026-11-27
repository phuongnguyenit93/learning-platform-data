# Verifying Join Results with Data Containing NULLs and Missing Relationships in PostgreSQL

A `JOIN` query can run cleanly without raising any SQL error, and even return rows that look plausible, yet still be **wrong from a business perspective**. This often happens when data is not as "clean" as in idealized examples: customers who have not placed any orders, orders not yet linked to a customer, import tables containing non-existent customer IDs, join columns containing `NULL`, or a key assumed to be unique that actually matches multiple rows on the right-hand table.

For example, a report of "all customers and their order counts" using `INNER JOIN` will **drop customers who have made no purchases**. A report using `LEFT JOIN` that places a paid-order filter in `WHERE` can also inadvertently turn the result into something nearly identical to `INNER JOIN`. Meanwhile, `COUNT(*)` on a `LEFT JOIN` result can report that a customer with no orders still has "1 order", because the customer themselves still produces one output row with all right-hand columns set to `NULL`.

Therefore, testing a `JOIN` is not just checking whether the result is syntactically valid. We need to build a **test dataset intentionally containing edge cases**, predict the row counts and key sets before running, and verify the invariants of the result.

This lesson walks through a verification workflow that can be executed directly in PostgreSQL, covering `INNER JOIN`, `LEFT/RIGHT/FULL OUTER JOIN`, `NULL`, `ON` versus `WHERE`, anti-joins, orphan data in staging, one-to-many relationships, and counting/aggregation operations. It also shows how to turn those checks into reconciliation queries and exercises with expected results.

## 1. What Questions Must a "Correct JOIN" Answer?

Before reading a SQL statement, write down the requirements:

1. **What is the unit of a single output row?** One customer, one order, or one customer–order pair?
2. **Which side must preserve all its rows?** All customers, all orders, or only matched pairs?
3. **Can the join key be `NULL`?** If so, does `NULL` mean "unknown", "not applicable", or a distinct business value?
4. **Is missing relationship data valid?** A customer with no orders is normal; a non-existent `customer_id = 999` might be an import error.
5. **Can multiple rows match a single key?** A customer having multiple orders is expected; two delivery zone records with the same code can duplicate report rows.
6. **Which rows should filters exclude?** Filter right-hand rows during the join, or exclude left-hand rows from the final result as well?
7. **What row counts, key sets, or aggregate values should be verified?**

This is a more important starting point than memorizing "INNER is intersection, LEFT keeps the left".

### 1.1. Thinking in Terms of Data Grain (*grain*)

Consider two tables:

```text
customers:  1 row / customer_id
orders:     1 row / order_id, multiple rows can share the same customer_id
```

When joining on `customer_id`, a customer with three orders produces **three joined rows**. A summary table expecting one row per customer needs `GROUP BY` or another aggregation method to return to the "customer" grain.

If you do not determine the grain beforehand, you might run `SUM(customers.credit_limit)` after a JOIN and accidentally multiply the customer's credit limit by their number of orders.

## 2. Building an Intentional Test Dataset

We will create two core tables and one staging table in an isolated schema. The dataset is designed to cover **all test case categories** rather than just a few rows with complete relationships.

### 2.1. Creating the Schema

Only run this on an authorized lab database or schema:

```sql
CREATE SCHEMA IF NOT EXISTS join_check;

CREATE TABLE join_check.customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    region_code text
);

CREATE TABLE join_check.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint
        REFERENCES join_check.customers(customer_id),
    order_status text NOT NULL
        CHECK (order_status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0)
);

CREATE TABLE join_check.order_imports (
    import_id bigint PRIMARY KEY,
    external_customer_id bigint,
    source_name text NOT NULL
);
```

Note the differences:

- `join_check.orders.customer_id` **allows SQL NULL** but enforces a foreign key whenever the value is non-NULL. This supports the case of an order awaiting customer assignment while still protecting declared references.
- `join_check.order_imports.external_customer_id` intentionally has **no foreign key** because it simulates a staging table receiving unverified external data. This table can contain a non-existent ID like 999.
- `customers.region_code` allows NULL to test joins on an optional attribute rather than a primary key.

If `NOT NULL` were enforced on `orders.customer_id`, the unassigned order rows in this lesson could not be inserted; that might fit another business requirement, but it would eliminate the exact case we need to verify here.

### 2.2. Inserting Customers

```sql
INSERT INTO join_check.customers
    (customer_id, customer_name, region_code)
VALUES
    (1, 'An',   'Bac'),
    (2, 'Binh', NULL),
    (3, 'Chi',  'Nam'),
    (4, 'Dung', 'Trung'),
    (5, 'Ha',   'Nam'),
    (6, 'Lan',  NULL);
```

### 2.3. Inserting Orders

```sql
INSERT INTO join_check.orders
    (order_id, customer_id, order_status, amount)
VALUES
    (101, 1,    'paid',      120000.00),
    (102, 1,    'pending',    50000.00),
    (103, 2,    'paid',       90000.00),
    (104, 3,    'cancelled',  30000.00),
    (105, NULL, 'pending',    40000.00),
    (106, 3,    'paid',       20000.00),
    (107, 5,    'paid',       70000.00),
    (108, NULL, 'cancelled',  10000.00);
```

### 2.4. Inserting Unverified Import Data

```sql
INSERT INTO join_check.order_imports
    (import_id, external_customer_id, source_name)
VALUES
    (201, 1,    'batch-A'),
    (202, 999,  'batch-A'),
    (203, NULL, 'batch-B'),
    (204, 4,    'batch-B');
```

If you re-run these `INSERT` statements on the same data, primary keys will raise duplicate key errors. Initialize a fresh lab schema or clear the data using a safe procedure before re-running; do not carelessly use `DROP SCHEMA ... CASCADE` in a database containing real objects.

### 2.5. Relationship Diagram

```text
customers                       orders
---------                       ------
1 An    ----------------------> 101, 102
2 Binh  ----------------------> 103
3 Chi   ----------------------> 104, 106
4 Dung  ----------------------> (no orders)
5 Ha    ----------------------> 107
6 Lan   ----------------------> (no orders)

                                 105 -> customer_id NULL
                                 108 -> customer_id NULL

order_imports (staging, NO FK)
  201 -> 1        (matches customer)
  202 -> 999      (non-existent customer ID: orphan)
  203 -> NULL     (no ID provided)
  204 -> 4        (matches customer)
```

### 2.6. Predicting Counts Before Running JOINs

| Characteristic | Count | Identifiers |
| --- | ---: | --- |
| Total customers | 6 | 1, 2, 3, 4, 5, 6 |
| Total orders | 8 | 101–108 |
| Orders with a valid customer | 6 | 101, 102, 103, 104, 106, 107 |
| Orders with `customer_id IS NULL` | 2 | 105, 108 |
| Customers with at least one order | 4 | 1, 2, 3, 5 |
| Customers with no orders | 2 | 4, 6 |
| Staging rows with non-existent customer ID | 1 | import 202, customer 999 |
| Staging rows with NULL customer ID | 1 | import 203 |

These numbers serve as the **test oracle** for this lesson: when a query unexpectedly returns 7, 9, or 12 rows, explain exactly why instead of adding `DISTINCT` until the output looks nice.

## 3. INNER JOIN: Keeping Only Matching Pairs

`INNER JOIN` produces an output row only when a pair of left and right rows makes the `ON` condition evaluate to TRUE.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM join_check.customers AS c
INNER JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

Expected result:

| customer_id | customer_name | order_id | order_status | amount |
| ---: | --- | ---: | --- | ---: |
| 1 | An | 101 | paid | 120000 |
| 1 | An | 102 | pending | 50000 |
| 2 | Binh | 103 | paid | 90000 |
| 3 | Chi | 104 | cancelled | 30000 |
| 3 | Chi | 106 | paid | 20000 |
| 5 | Ha | 107 | paid | 70000 |

The result has **6 rows**, not 4, because each order matches one customer, while a single customer can appear multiple times.

Two groups of data disappear from the result:

- Customers 4 and 6 because they have **no orders**.
- Orders 105 and 108 because `customer_id` is NULL and cannot match a customer primary key via `=`.

### 3.1. Checking the Key Set Rather Than Just Row Counts

```sql
SELECT
    array_agg(o.order_id ORDER BY o.order_id) AS matched_order_ids
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

Expected result:

```text
{101,102,103,104,106,107}
```

Counting 6 rows is necessary but not sufficient: a buggy query might return 6 rows with the **wrong IDs**. Checking the key set or key pairs provides much stronger evidence when verifying JOIN logic.

### 3.2. Omitting Right-Hand Columns Still Lets JOIN Change Row Counts

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
```

Even though the select list only picks columns from `c`, customers 1 and 3 still appear twice because they each have two orders. **The SELECT column list does not determine the cardinality of a JOIN.**

If you want each customer with orders to appear once, use `EXISTS` or an aggregation suited to the requirement rather than blindly slapping on `SELECT DISTINCT c.*` without verifying the logic.

## 4. LEFT JOIN: Preserving Every Left-Hand Row

When you want to display **all customers, including those without orders**, put customers on the left:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Result:

| customer_id | customer_name | order_id | amount |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 120000 |
| 1 | An | 102 | 50000 |
| 2 | Binh | 103 | 90000 |
| 3 | Chi | 104 | 30000 |
| 3 | Chi | 106 | 20000 |
| 4 | Dung | NULL | NULL |
| 5 | Ha | 107 | 70000 |
| 6 | Lan | NULL | NULL |

There are **8 rows**: 6 matched pairs plus 2 unmatched customers. For the two customers with no orders, PostgreSQL emits **an extended row with all right-hand columns set to SQL NULL**.

No actual `orders.order_id = NULL` record is stored for customer 4 or 6. Those NULL values exist **only in the outer join output**.

### 4.1. Swapping the Left Side Changes the Meaning

To preserve **all orders**, including orders without a `customer_id`:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name,
    o.amount
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

This query returns **8 rows**; orders 105 and 108 remain present with `customer_name = NULL`, while customers 4 and 6 do not appear because they have no orders to generate output rows.

Both `LEFT JOIN` queries return 8 rows on this dataset, yet **the two result sets are completely different**. Comparing only `COUNT(*)` is therefore an insufficient check.

### 4.2. Rules to Remember

- `LEFT JOIN` preserves **each left-hand row at least once** before any outer filtering is applied; if there are multiple matches, a left-hand row can appear multiple times.
- A right-hand row with no partner on the left **does not appear on its own**.
- A NULL right-hand column in an outer join row **does not necessarily mean the source data contained NULL**; it may be a NULL-padded row produced due to a missing partner.
- When writing `WHERE`, you can accidentally filter out those preserved rows — we will verify this in the upcoming sections.

## 5. RIGHT JOIN: Preserving Every Right-Hand Row

`RIGHT JOIN` preserves the rows of the right-hand source:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.customers AS c
RIGHT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.order_id;
```

In this example, the query above is semantically equivalent in data output to:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Both preserve all 8 orders, including 105 and 108 without customers.

There is no rule saying `RIGHT JOIN` is wrong; however, in many queries readers find `LEFT JOIN` with the preserved table on the left easier to follow. What matters is **which side's rows are preserved**, not syntactic preference.

## 6. FULL OUTER JOIN: Preserving Unmatched Rows from Both Sides

`FULL OUTER JOIN` pairs matching rows; when there is no match, it still preserves rows from both the left and right sides by filling the missing side with NULLs.

```sql
SELECT
    c.customer_id AS customer_row_id,
    c.customer_name,
    o.order_id,
    o.customer_id AS order_customer_id
FROM join_check.customers AS c
FULL OUTER JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY
    c.customer_id NULLS LAST,
    o.order_id NULLS LAST;
```

Prediction:

```text
6 matched pairs
+ 2 customers without orders (4, 6)
+ 2 orders without customers (105, 108)
= 10 rows
```

In the output:

- Customers 4 and 6 have `customer_row_id` populated but `order_id = NULL`.
- Orders 105 and 108 have `order_id` populated but `customer_row_id = NULL`.
- Both groups are preserved separately rather than being joined to each other.

### 6.1. Separating Unmatched Rows on Each Side

```sql
SELECT
    c.customer_id AS customer_row_id,
    o.order_id,
    o.customer_id AS order_customer_id,
    CASE
        WHEN c.customer_id IS NULL
            THEN 'order_without_matched_customer'
        WHEN o.order_id IS NULL
            THEN 'customer_without_order'
        ELSE 'matched'
    END AS join_class
FROM join_check.customers AS c
FULL JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY join_class, c.customer_id, o.order_id;
```

In this example, both `c.customer_id` and `o.order_id` are `NOT NULL` primary keys in the base tables. Thus, when they become NULL in the outer join result, we can rely on them as **indicators of a missing counterpart row**.

If you test a right-hand column that **can naturally be NULL** to check "whether a right-hand row exists", your conclusion can be wrong. Always choose a guaranteed `NOT NULL` column, typically the primary key, or an explicit presence flag.

### 6.2. Avoid Using COALESCE to Hide Provenance When Debugging

In reports, keys are sometimes merged:

```sql
SELECT
    COALESCE(c.customer_id, o.customer_id) AS displayed_customer_id,
    o.order_id
FROM join_check.customers AS c
FULL JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

That can be convenient for presentation, but when debugging, keep **both original key columns**. A coalesced display value can mask which side the row came from, especially when staging data contains invalid customer IDs.

## 7. NULL in ON Conditions: Not Like an Ordinary Value

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`.

```sql
SELECT
    NULL::bigint = NULL::bigint AS equality_of_nulls,
    NULL::bigint IS NULL AS left_is_null,
    NULL::bigint IS NOT DISTINCT FROM NULL::bigint
        AS null_safe_equality;
```

Semantic result:

| Expression | Result |
| --- | --- |
| `NULL = NULL` | SQL NULL / UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT DISTINCT FROM NULL` | TRUE |

The condition `JOIN ... ON a = b` considers a pair of rows matched only when the comparison evaluates to **TRUE**. If one or both sides are NULL, `a = b` does not yield TRUE; the pair does not match.

### 7.1. Why Doesn't Order 105 Join to a "NULL Customer"?

In this dataset, `orders.customer_id` is NULL on orders 105 and 108, while `customers.customer_id` is a primary key that cannot be NULL. Yet even when another table allows nullable join keys on **both sides**, `a.key = b.key` still does not treat two NULL values as equal.

This is the difference between assuming "both lack an ID, so they match" and SQL semantics. Two unknown IDs provide **no evidence that they refer to the same entity**.

### 7.2. Source-Data NULL Differs from Outer-Join-Generated NULL

With:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_id AS matched_customer_id
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

On order 105:

- `o.customer_id IS NULL` because the column in the **source orders row** has no ID assigned.
- `c.customer_id IS NULL` because **no matching customers row exists**, and the outer join generated NULL for the right-hand side.

Both columns are NULL, yet they stem from two distinct causes. During data-quality checks, do not collapse both causes into a single label.

## 8. Distinguishing Customers Without Orders from Orders Without Customers

These are two opposite-direction business questions.

### 8.1. Finding Customers Who Have Never Placed an Order

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

The correct result is customers **4 and 6**. Here `o.order_id` is a non-nullable primary key, so checking `IS NULL` identifies customer rows with no counterpart in `orders`.

### 8.2. Finding Orders Not Linked to a Customer

```sql
SELECT
    order_id,
    order_status,
    amount
FROM join_check.orders
WHERE customer_id IS NULL
ORDER BY order_id;
```

The correct result is orders **105 and 108**.

No JOIN is needed to detect this case: the unassigned value lives directly in the `orders` column. Only add a JOIN if you also need to distinguish other causes, such as an ID that is present but missing from the parent table.

### 8.3. The Two Answers Are Not Interchangeable

"Customers without orders" takes customers as the subject under inspection. "Orders without customers" takes orders as the subject. A query that returns the right row count while reversing the two sides still fails the requirement.

## 9. Missing Relationships With and Without FOREIGN KEYs

An important question: if `orders.customer_id` references `customers.customer_id` via a foreign key, how can an order still fail to match a customer?

Because in this example, the foreign key column **allows NULL**. Under PostgreSQL's default `MATCH SIMPLE` behavior, a single-column foreign key reference is not checked when the foreign key value is NULL.

```sql
-- Valid in the lab schema because customer_id is nullable:
INSERT INTO join_check.orders (
    order_id, customer_id, order_status, amount
)
VALUES (109, NULL, 'pending', 1000.00);
```

This statement is a standalone illustration — **do not run it if you want to preserve the 8-order dataset counts**. If you did run it, expected results in other sections must be updated because the table now contains order 109.

### 9.1. Non-Existent IDs Are Blocked by the FK

```sql
-- Illustration of a statement NOT to run in a fixed-count lab:
-- INSERT INTO join_check.orders
--     (order_id, customer_id, order_status, amount)
-- VALUES (110, 999, 'paid', 1000.00);
```

If `customer_id = 999` does not exist, a normal foreign key rejects that row. Thus, on a table with a valid, enforced PostgreSQL foreign key, "key has a value but parent not found" should not occur in normal committed state.

Operational exceptions to check during real-world investigations include legacy rows prior to constraint validation, constraints deferred within a transaction, or unsafe data ingestion paths. Never disable constraints in production just to reproduce an orphan for testing.

### 9.2. Staging Data Without FKs Can Contain Orphans

`join_check.order_imports` is a staging table intentionally lacking a foreign key constraint. Finding records with a **non-NULL customer ID that does not exist**:

```sql
SELECT
    i.import_id,
    i.external_customer_id,
    i.source_name
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
WHERE i.external_customer_id IS NOT NULL
  AND c.customer_id IS NULL
ORDER BY i.import_id;
```

The result contains only:

| import_id | external_customer_id | source_name |
| ---: | ---: | --- |
| 202 | 999 | batch-A |

The two predicates `IS NOT NULL` and `IS NULL` serve **two distinct purposes**:

- `i.external_customer_id IS NOT NULL`: the sender provided a customer ID.
- `c.customer_id IS NULL`: PostgreSQL found no matching customer row for that ID.

If you omit the first condition, import 203 with `external_customer_id = NULL` also appears in the list, mixing two separate error categories together.

### 9.3. Classifying Staging Data into Three Groups

```sql
SELECT
    i.import_id,
    i.external_customer_id,
    CASE
        WHEN i.external_customer_id IS NULL
            THEN 'missing_customer_id'
        WHEN c.customer_id IS NULL
            THEN 'unknown_customer_id'
        ELSE 'valid_customer_id'
    END AS data_quality_class
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
ORDER BY i.import_id;
```

Expected:

| import_id | external_customer_id | data_quality_class |
| ---: | ---: | --- |
| 201 | 1 | valid_customer_id |
| 202 | 999 | unknown_customer_id |
| 203 | NULL | missing_customer_id |
| 204 | 4 | valid_customer_id |

This turns a JOIN result into **actionable import diagnostics**: a missing ID differs from a provided-but-invalid ID.

## 10. ON vs. WHERE in OUTER JOINs: The Most Common Source of Bugs

A `LEFT JOIN` query routinely "loses" unmatched rows when a condition on the right-hand table is placed in `WHERE`.

### 10.1. Placing the Condition in WHERE

Requirement: "Find customers who have paid orders."

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id;
```

The result contains paid orders **101, 103, 106, 107** — 4 rows. Customers 4 and 6 are excluded because on their outer-joined rows, `o.order_status` is NULL and `NULL = 'paid'` evaluates to UNKNOWN, not TRUE.

Even customers who placed orders, if all their orders are unpaid, are excluded as well. Hence this result represents **customers with at least one paid order**, not "all customers and their paid orders if any".

### 10.2. Placing the Condition in ON

A different requirement: "Show **all customers**, attaching their paid orders if any exist."

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The result has **6 rows**, one per customer in this dataset:

| customer_id | customer_name | order_id | order_status |
| ---: | --- | ---: | --- |
| 1 | An | 101 | paid |
| 2 | Binh | 103 | paid |
| 3 | Chi | 106 | paid |
| 4 | Dung | NULL | NULL |
| 5 | Ha | 107 | paid |
| 6 | Lan | NULL | NULL |

Here:

- `ON` defines **which right-hand rows qualify as matching partners**.
- If no paid order matches, the customer row is still preserved with NULL order columns.
- The sample data happens to have at most one paid order per customer; in a real system, a customer with multiple paid orders still produces multiple rows.

**There is no rule stating that moving any condition from `WHERE` to `ON` preserves the result.** In an outer join, changing clause placement can alter the business meaning itself.

### 10.3. Direct Comparison

| Condition | Rows | Meaning |
| --- | ---: | --- |
| `LEFT JOIN ... ON key; WHERE o.order_status = 'paid'` | 4 | Only customers with at least one paid order and those paid orders. |
| `LEFT JOIN ... ON key AND o.order_status = 'paid'` | 6 | All customers; shows paid orders if any exist. |
| `INNER JOIN ... ON key AND o.order_status = 'paid'` | 4 | Only matched customer–paid order pairs. |

Seeing the words `LEFT JOIN` in a SQL query **does not guarantee that left-hand rows survive after `WHERE` is applied**.

## 11. WHERE Containing IS NULL: Reading the Semantics Correctly

Suppose you need "customers with no paid orders", **including customers who have pending/cancelled orders**. Write:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

In the current dataset, customers 4 and 6 have no orders at all; none of the 6 customers has only pending/cancelled orders. The result is **4, 6**.

However, the two requirements:

- "Customers with **no orders**."
- "Customers with **no paid orders**."

are not equivalent in general. As soon as you add a customer who has a pending order and no paid order, the second query will include them while the first will not.

### 11.1. Why Not Write WHERE o.order_status <> 'paid'?

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status <> 'paid';
```

This query finds **customer–non-paid order pairs**. It does not find "customers with no paid orders", because a customer with both a paid order and a pending order still appears via their pending order.

In our dataset, customer 1 has pending order 102 and therefore still appears, even though they **already have paid order 101**. Use an anti-join or `NOT EXISTS` to check for the absence of **all** paid orders rather than merely checking for the presence of at least one non-paid order.

## 12. Anti-Join: Finding What Has NO Relationship

An anti-join queries for "left-hand rows that have no qualifying row on the right".

### 12.1. LEFT JOIN ... IS NULL

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL
ORDER BY c.customer_id;
```

Result: customers 4 and 6.

### 12.2. NOT EXISTS

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

The result is also 4 and 6.

`NOT EXISTS` directly expresses the intent "no matching order row exists". It is often easier to verify when the right-hand query has multiple conditions or when you do not need to return any columns from the right-hand table.

### 12.3. NOT EXISTS Can Be Safer Than NOT IN When NULLs Exist

A very common trap:

```sql
SELECT
    customer_id,
    customer_name
FROM join_check.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM join_check.orders
)
ORDER BY customer_id;
```

In this dataset, the subquery also returns `NULL` because orders 105 and 108 are unassigned. For any `customer_id` not present among the non-NULL values, `NOT IN (..., NULL)` evaluates to UNKNOWN and is rejected by `WHERE`. The result here is **zero rows**, even though customers 4 and 6 truly have no orders.

If you still want to use `NOT IN` against a `NOT NULL` left-hand key column, you must filter out NULLs in the comparison source:

```sql
SELECT customer_id, customer_name
FROM join_check.customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM join_check.orders
    WHERE customer_id IS NOT NULL
)
ORDER BY customer_id;
```

This returns 4 and 6. Still, for missing-relationship checks, `NOT EXISTS` usually expresses intent more clearly and avoids bugs caused by NULLs in the subquery set.

### 12.4. NOT EXISTS with Business Predicates

"Customers with **no** paid orders":

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'paid'
)
ORDER BY c.customer_id;
```

On the current dataset, the result is 4 and 6. If customer 7 is later added with only a pending order, they will also belong to the set of customers with no paid orders despite having an order.

## 13. EXISTS and Why JOIN Can Multiply Rows

"Get customers who have at least one order" can be written as:

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

The result has **4 customers**: 1, 2, 3, 5; one row per customer.

By contrast:

```sql
SELECT c.customer_id, c.customer_name
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

returns **6 rows**, because An and Chi each have two orders.

When you only need an existence check, `EXISTS` avoids generating duplicate joined rows that then have to be deduplicated. The PostgreSQL optimizer can choose an appropriate semi-join plan; actual performance still needs to be measured on real data.

**Do not reach for `SELECT DISTINCT` as a knee-jerk fix for row multiplication**. Confirm the grain first: per customer, per order, or per pair.

## 14. COUNT(*) vs. COUNT(right-hand column) After LEFT JOIN

One of the subtlest reporting bugs occurs in counting:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS rows_after_join,
    COUNT(o.order_id) AS actual_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Result:

| customer_id | customer_name | rows_after_join | actual_orders |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 2 |
| 2 | Binh | 1 | 1 |
| 3 | Chi | 2 | 2 |
| 4 | Dung | 1 | 0 |
| 5 | Ha | 1 | 1 |
| 6 | Lan | 1 | 0 |

Why does customer 4 have `rows_after_join = 1`?

Because the outer join keeps **one customer row** even with no orders; `COUNT(*)` counts that output row. Meanwhile, `COUNT(o.order_id)` counts only **non-NULL** `o.order_id` values, yielding 0 for customers with no orders.

**Important rule:** when counting matched right-hand rows from an outer join, pick a **guaranteed NOT NULL right-hand identifier column** and count that column instead of defaulting to `COUNT(*)`.

### 14.1. COUNT(nullable column) Can Also Undercount

If `orders.note` allows NULL, `COUNT(o.note)` will skip orders without notes. To count **orders**, use `COUNT(o.order_id)` because `order_id` is a non-NULL primary key.

You must answer: "Do I want to count **related rows**, or do I want to count **populated values**?" The two requirements are not equivalent.

### 14.2. Totalling Values with SUM

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(SUM(o.amount), 0) AS total_order_amount
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Expected:

| customer_id | total_order_amount |
| ---: | ---: |
| 1 | 170000.00 |
| 2 | 90000.00 |
| 3 | 50000.00 |
| 4 | 0 |
| 5 | 70000.00 |
| 6 | 0 |

`SUM` ignores NULL values. For a group with no numeric values to sum, `SUM` returns NULL; `COALESCE(..., 0)` turns that into 0 **if business rules treat having no orders as a total of 0**.

Do not conflate "no data to sum" with "actual sum equals 0" if the report needs to distinguish between those two cases.

## 15. Conditional Aggregation Without Dropping Customers

Count paid orders per customer, including customers with 0 paid orders:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'pending'
    ) AS pending_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Result:

| customer_id | paid_orders | pending_orders |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 1 | 0 |
| 3 | 1 | 0 |
| 4 | 0 | 0 |
| 5 | 1 | 0 |
| 6 | 0 | 0 |

`FILTER (WHERE ...)` scopes the condition to **one specific aggregate**, without removing customers from the result before grouping.

Another option is pushing the condition into `ON`:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Both approaches are valid for counting paid orders, though `FILTER` is convenient when multiple metrics with different conditions are needed from the same JOIN.

## 16. Verifying Row Counts and Preservation with Equations

For the one-to-many relationship `customers (1) → orders (n)` in the current dataset:

```text
INNER JOIN:
  6 orders rows with valid customer_id
  = 6 joined rows

customers LEFT JOIN orders:
  6 joined rows
  + 2 customers without orders
  = 8 rows

orders LEFT JOIN customers:
  6 joined rows
  + 2 orders without customers
  = 8 rows

FULL OUTER JOIN:
  6 joined rows
  + 2 customers without orders
  + 2 orders without customers
  = 10 rows
```

This equation applies **to a dataset with the described key uniqueness and cardinality**, not as a rigid formula for arbitrary JOINs.

### 16.1. Checking Total Row Counts in SQL

```sql
SELECT
    (SELECT COUNT(*)
     FROM join_check.customers) AS customers_count,
    (SELECT COUNT(*)
     FROM join_check.orders) AS orders_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS inner_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS customers_left_count,
    (SELECT COUNT(*)
     FROM join_check.orders AS o
      LEFT JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id) AS orders_left_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
      FULL JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id) AS full_count;
```

Expected in order: `6, 8, 6, 8, 8, 10`.

### 16.2. Do Not Rely on a Single COUNT

Suppose a JOIN mistakenly equates `order_id` with `customer_id`, yet happens by coincidence to return 6 rows on another dataset. The count looks "right" while the relationship is completely wrong.

Stronger verification combines:

- Total row count.
- `COUNT(DISTINCT ...)` or full ID sets.
- Rows that **must be present**.
- Rows that **must be absent**.
- Hand-calculated aggregate values.
- Unmatched classification per side.

## 17. Preventing Unintended Row Multiplication When Keys Are Non-Unique

`customers`'s primary key guarantees at most one customer per `customer_id`. But if you join on a **non-unique** attribute, row counts can blow up.

Create a delivery zones table intentionally containing duplicate region codes:

```sql
CREATE TABLE join_check.delivery_zones (
    zone_id bigint PRIMARY KEY,
    region_code text,
    zone_label text NOT NULL
);

INSERT INTO join_check.delivery_zones
    (zone_id, region_code, zone_label)
VALUES
    (10, 'Bac',  'North standard'),
    (20, 'Nam',  'South urban'),
    (21, 'Nam',  'South suburban'),
    (30, NULL,   'Unassigned zone'),
    (40, 'Tay',  'West');
```

Thus:

```text
region_code = 'Bac' -> 1 zones row
region_code = 'Nam' -> 2 zones rows
region_code IS NULL  -> 1 zones row, but does not match via =
```

### 17.1. Joining Customers with Delivery Zones

```sql
SELECT
    c.customer_id,
    c.customer_name,
    c.region_code,
    z.zone_id,
    z.zone_label
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
ORDER BY c.customer_id, z.zone_id;
```

The result has **5 rows**:

- An is in region Bac, matching zone 10: 1 row.
- Chi is in Nam, matching zones 20 and 21: 2 rows.
- Ha is in Nam, matching zones 20 and 21: 2 rows.
- Binh and Lan have `region_code = NULL`: do not match the NULL zone row via `=`.
- Dung has `Trung`: no zone exists with code Trung.

If the business expects **exactly one zone per customer**, duplicate zone region codes broke the cardinality assumption. Adding `DISTINCT c.customer_id` might hide the symptom without resolving the rule for choosing between the urban and suburban zone.

### 17.2. Multi-Table JOINs Can Double Revenue

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS distinct_orders,
    SUM(o.amount) AS summed_amount_after_join
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Expected:

| customer_id | joined_rows | distinct_orders | summed_amount_after_join |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 170000.00 |
| 3 | 4 | 2 | 100000.00 |
| 5 | 2 | 1 | 140000.00 |

Why did Chi's total jump from 50,000 to 100,000, and Ha's from 70,000 to 140,000?

Because each of their orders **matched two `delivery_zones` rows** sharing code `Nam`. `SUM(o.amount)` runs **after the JOIN multiplies rows**, so each amount is added twice.

**Do not fix this with `SUM(DISTINCT o.amount)`.** Two legitimate orders with the exact same dollar amount would have one of them dropped. The proper fix is to correct the relationship or separate the aggregation from any multiplying source.

### 17.3. How to Avoid Row Multiplication When Only Zone Existence Is Needed

If the requirement is simply "customers with at least one declared delivery zone", use `EXISTS`:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM join_check.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
ORDER BY c.customer_id;
```

The result contains customers 1, 3, 5 — once per customer, unaffected by how many zones share a region code.

If you genuinely need to pick one zone among multiple Nam zones, there must be a **business rule** (priority, effective date, district code, address type, etc.) defining the valid zone. Never pick an arbitrary row using `LIMIT 1` without a proper `ORDER BY` and selection criterion.

## 18. NULL-Safe Equality: IS NOT DISTINCT FROM

Normally, SQL does not consider `NULL = NULL` to be TRUE. However, some problems genuinely require treating two nullable values as equivalent, such as grouping data standardized to represent the same "undeclared" state.

PostgreSQL provides the `IS NOT DISTINCT FROM` operator:

```sql
SELECT
    NULL::text IS NOT DISTINCT FROM NULL::text
        AS both_null_equal,
    'Nam'::text IS NOT DISTINCT FROM 'Nam'::text
        AS same_region,
    'Nam'::text IS NOT DISTINCT FROM NULL::text
        AS region_and_null;
```

The results are TRUE, TRUE, FALSE.

### 18.1. Comparing Two JOIN Styles on a Nullable Attribute

Using the `delivery_zones` table created earlier:

```sql
-- Join using standard equality.
SELECT COUNT(*) AS normal_join_rows
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON c.region_code = z.region_code;
```

Result: **5**.

If replaced with:

```sql
SELECT COUNT(*) AS null_safe_join_rows
FROM join_check.customers AS c
JOIN join_check.delivery_zones AS z
    ON c.region_code IS NOT DISTINCT FROM z.region_code;
```

Result: **7**, because in addition to the previous 5 rows:

- Binh (`region_code = NULL`) matches zone 30, which has a NULL code.
- Lan (`region_code = NULL`) also matches zone 30.

### 18.2. Should Every NULL Be Treated as One Region?

**Not by default.** If NULL means "customer's region unknown", matching every unknown customer to an "unassigned zone" may be useful for display, but it does not prove they belong to **the same geographic region**.

Use `IS NOT DISTINCT FROM` only when business logic explicitly defines two NULLs as representing the same group or state to match on. For entity identifier keys, joining "unknown ID" to "unknown ID" is usually wrong.

### 18.3. Using COALESCE to Join NULLs Can Mask Collisions

A risky pattern:

```sql
-- Not recommended as a default for identifier keys:
-- ON COALESCE(c.region_code, 'UNKNOWN')
--    = COALESCE(z.region_code, 'UNKNOWN')
```

If the string `'UNKNOWN'` is also a real data value, you could join NULLs onto a value with its own distinct meaning. `IS NOT DISTINCT FROM` expresses NULL-safe intent much more cleanly, though you still must verify data semantics.

## 19. FULL JOIN and Many-to-One / One-to-One Reconciliation with Missing Data

A `FULL JOIN` can be used to **reconcile two systems**: for example, a catalog table from source A and source B. Yet reconciliation is not just "checking whether rows are missing on one side"; you must also verify **whether the join key is truly unique**.

Consider two hypothetical tables:

```text
Source A                    Source B
--------                    --------
code K1, value 10           code K1, value 10
code K2, value 20           code K3, value 30
code NULL, value 99         code NULL, value 99
```

If joined on `a.code = b.code`:

- K1 matches.
- K2 exists only in A.
- K3 exists only in B.
- The two NULL-code rows **do not match each other**, so each still appears separately after `FULL JOIN`.

Do not interpret rows with `COALESCE(a.code, b.code) IS NULL` as "matched two NULLs". There may actually be **two orphaned rows, one on each side**.

### 19.1. Checking Key Uniqueness Before FULL JOIN

For a source expected to have a one-to-one relationship, check:

```sql
SELECT region_code, COUNT(*) AS row_count
FROM join_check.delivery_zones
GROUP BY region_code
HAVING COUNT(*) > 1;
```

The result shows region `Nam` has 2 rows. If `region_code` were used as a one-to-one reconciliation key, this signals a **failed assumption**, even though the SQL JOIN itself would run without error.

Note: `GROUP BY` collects NULLs into a single group during aggregation, which does not mean `=` in `ON` treats two NULLs as equal.

## 20. Distinguishing Missing Data, Missing Relationships, and Non-Unique Relationships

Three failure categories produce distinct symptoms:

| Category | Symptom | How to Verify |
| --- | --- | --- |
| Child key is NULL | `orders.customer_id IS NULL` | Filter directly on the child table; no JOIN needed. |
| Key present but parent not found | `external_customer_id IS NOT NULL` and no parent row matches | `LEFT JOIN ... WHERE parent.pk IS NULL` or `NOT EXISTS`. |
| Single key matches unexpectedly many rows | Joined row count exceeds target-grain row count | `GROUP BY join_key HAVING COUNT(*) > 1`, `COUNT(DISTINCT ...)`, constraint checks. |

An import row with key 999 and an order with `customer_id = NULL` require **two different remedies**: one has an invalid code, while the other lacks an assigned code. Do not slap the same `orphan` label on both if the business workflow needs to distinguish them.

### 20.1. Complete Data and Incomplete Data Serve Different Purposes

In production environments:

- Foreign keys, `NOT NULL`, and `UNIQUE` constraints **prevent** many kinds of bad data from entering core tables.
- Staging may permit incomplete data in order to **ingest and validate** it before loading into core tables.
- Diagnostic JOINs on staging help **explain** why a row could not yet be imported.
- Historical snapshots or rows hidden by retention policies can lead to a relationship being modeled differently from the day-to-day operational schema.

Sound JOIN verification is always tied to the **purpose of the table** and the data states that table is allowed to hold.

## 21. Filtering Rules in ON vs. WHERE Across Multiple Tables

When a query has multiple JOINs, a predicate on one right-hand table can trigger a cascading effect.

For example:

```sql
SELECT
    c.customer_id,
    o.order_id,
    z.zone_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
WHERE z.zone_label = 'South urban'
ORDER BY c.customer_id, o.order_id;
```

`WHERE z.zone_label = 'South urban'` drops every customer without a zone matching that label. Thus, despite using two `LEFT JOIN`s, the final preserved customer set **is no longer complete**.

If the requirement is to keep all customers and only display zones matching the chosen label:

```sql
SELECT
    c.customer_id,
    o.order_id,
    z.zone_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code
   AND z.zone_label = 'South urban'
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

Then the remaining customers stay present, with `zone_id` set to NULL when no matching zone is found.

### 21.1. Be Careful When Joining More Tables After an OUTER JOIN

If table `z` were joined on a column from `o` instead of `c`, customers without orders would carry NULLs on the `o` side. A subsequent `INNER JOIN` referencing `o` can wipe out those customers. A JOIN structure must be analyzed **according to the actual chain of sources and conditions**, not merely by checking whether the keyword `LEFT` appeared first.

## 22. Checking for Duplicate Rows After JOIN Using Keys, Not Eyeballing

To check whether a result at the "one row per order" grain was multiplied:

```sql
WITH joined AS (
    SELECT
        o.order_id,
        c.customer_id
    FROM join_check.orders AS o
    LEFT JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id
)
SELECT
    order_id,
    COUNT(*) AS rows_per_order
FROM joined
GROUP BY order_id
HAVING COUNT(*) <> 1
ORDER BY order_id;
```

On this dataset, the query returns **zero rows** because each order yields exactly one row after LEFT JOINing against a customer table with a unique primary key.

If you swap the right-hand table for a source with duplicate keys, this check query immediately surfaces every order appearing more than once.

### 22.1. COUNT(DISTINCT) Does Not Fix Inflated Sums

```sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(DISTINCT o.order_id) AS unique_orders,
    SUM(o.amount) AS summed_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
JOIN join_check.delivery_zones AS z
    ON z.region_code = c.region_code;
```

`COUNT(DISTINCT o.order_id)` reveals that joined rows exceed unique orders, yet **`SUM(o.amount)` is still multiplied**. To compute totals accurately, eliminate the multiplication effect by choosing the right relationship or aggregating at the order grain first.

One way to sum without multiplication from the zones table:

```sql
SELECT
    c.customer_id,
    SUM(o.amount) AS total_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Here `EXISTS` only checks zone existence without multiplying order rows by the number of zones sharing a code.

## 23. Verifying Results with Set Reconciliation Operations

Instead of manually inspecting a 10,000-row table, you can write queries to find **missing identifiers** between expected and actual sets.

### 23.1. EXCEPT: Customers Missing from the Result Set

Suppose a query must preserve every customer:

```sql
WITH result_customers AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
)
SELECT customer_id
FROM join_check.customers
EXCEPT
SELECT customer_id
FROM result_customers;
```

The result returns **no rows**. This proves every current customer ID appears in the result at least once.

If `WHERE o.order_status = 'paid'` were accidentally placed in the CTE, `EXCEPT` would flag customers 4 and 6 as missing from the result.

### 23.2. Checking Both Directions

When comparing two key sets, check both:

- **Missing:** keys that should be present but are absent.
- **Extra:** keys that do not belong in the expected set yet appeared.

`EXCEPT` deduplicates by default, making it great for **membership** checks, though it cannot replace **multiplicity** checks. If both sets contain the same IDs while one ID is tripled, `EXCEPT` can still return empty.

Combine `EXCEPT` with `GROUP BY ... HAVING COUNT(*) > 1` or `EXCEPT ALL` whenever duplicate counts matter.

### 23.3. Checking Aggregates

For example, total sales across orders that have a customer:

```sql
SELECT SUM(amount) AS source_amount
FROM join_check.orders
WHERE customer_id IS NOT NULL;
```

Expected: `380000.00`.

Compared against:

```sql
SELECT SUM(o.amount) AS joined_amount
FROM join_check.orders AS o
JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id;
```

Expected is also `380000.00` given the foreign key and current data.

If the totals differ, rows were either lost or multiplied after the JOIN. Even when totals match, however, that alone does not guarantee every row is right since discrepancies can cancel out; always reconcile keys and cardinality as well.

## 24. Writing SQL Tests with PASS/FAIL Results

You can turn predictions into read-only assertion queries. This is useful in notebooks, migration verification, or validation steps after modifying a JOIN.

```sql
SELECT
    (
        SELECT COUNT(*)
        FROM join_check.customers
    ) = 6 AS customers_pass,
    (
        SELECT COUNT(*)
        FROM join_check.orders
    ) = 8 AS orders_pass,
    (
        SELECT COUNT(*)
        FROM join_check.customers AS c
        JOIN join_check.orders AS o
            ON o.customer_id = c.customer_id
    ) = 6 AS inner_join_pass,
    (
        SELECT COUNT(*)
        FROM join_check.customers AS c
        FULL JOIN join_check.orders AS o
            ON o.customer_id = c.customer_id
    ) = 10 AS full_join_pass;
```

All four columns are expected to be `true`.

### 24.1. Verifying the Exact Key Set

```sql
SELECT (
    SELECT array_agg(o.order_id ORDER BY o.order_id)
    FROM join_check.orders AS o
    JOIN join_check.customers AS c
        ON c.customer_id = o.customer_id
) = ARRAY[101, 102, 103, 104, 106, 107]::bigint[]
  AS inner_join_ids_pass;
```

This check catches wrong-key-pair bugs in many scenarios that row counts miss.

### 24.2. Verifying Customers Without Orders

```sql
WITH actual AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM join_check.orders AS o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT
    array_agg(customer_id ORDER BY customer_id)
        = ARRAY[4, 6]::bigint[] AS no_orders_pass
FROM actual;
```

### 24.3. Verifying Staging Orphans

```sql
WITH invalid_refs AS (
    SELECT i.import_id
    FROM join_check.order_imports AS i
    LEFT JOIN join_check.customers AS c
        ON c.customer_id = i.external_customer_id
    WHERE i.external_customer_id IS NOT NULL
      AND c.customer_id IS NULL
)
SELECT
    array_agg(import_id ORDER BY import_id)
        = ARRAY[202]::bigint[] AS orphan_import_pass
FROM invalid_refs;
```

When applying this pattern in production, do not hardcode lab numbers. Replace them with **business invariants or independently derived expected sets**, along with logging evidence and handling mismatches.

## 25. Remember Three-Valued Logic When Filtering with NULL

In `WHERE`:

- `TRUE`: the row is kept.
- `FALSE`: the row is dropped.
- `UNKNOWN`: the row is also dropped.

```sql
SELECT
    NULL::integer = 1 AS null_equals_one,
    NULL::integer <> 1 AS null_not_equals_one,
    NULL::integer IS NULL AS null_is_null;
```

The first two expressions return SQL NULL (UNKNOWN), while the last returns TRUE.

Example:

```sql
SELECT order_id, customer_id
FROM join_check.orders
WHERE customer_id <> 1
ORDER BY order_id;
```

This query does **not** return orders 105 and 108 with NULL `customer_id`, even though intuition might say "NULL isn't customer 1". SQL cannot evaluate `NULL <> 1` as TRUE.

If the requirement is "all orders not belonging to customer 1 **or unassigned**":

```sql
SELECT order_id, customer_id
FROM join_check.orders
WHERE customer_id IS DISTINCT FROM 1
ORDER BY order_id;
```

`IS DISTINCT FROM` has clear NULL semantics. You can also write `customer_id <> 1 OR customer_id IS NULL`, choosing whichever best fits business intent.

### 25.1. Putting a Left-Side Filter in ON Also Changes Meaning

The reverse mistake:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND c.customer_id = 1;
```

This query does **not** return only customer 1. The other customers are still preserved by `LEFT JOIN`, merely matching no orders because `c.customer_id = 1` in `ON` fails for them.

If you actually want only customer 1, put the customer filter in `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 1;
```

This demonstrates that **placing each condition in the right clause depends on exactly which entity is being filtered**.

## 26. GROUP BY, NULL, and How They Differ from JOIN Equality

PostgreSQL's `GROUP BY` treats NULL values of a grouping expression as belonging to **the same group**:

```sql
SELECT
    customer_id,
    COUNT(*) AS orders_count
FROM join_check.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
```

The result includes groups for customers 1, 2, 3, 5 plus **one NULL `customer_id` group containing the two orders 105 and 108**.

This is not evidence that both orders "belong to the same unknown customer". They are simply placed into the same **aggregate bucket labeled NULL**.

Differences:

| Operation | Two NULL values |
| --- | --- |
| `a = b` in `ON` | Does not yield TRUE. |
| `a IS NOT DISTINCT FROM b` | Yields TRUE. |
| `GROUP BY a` | Rows where `a` is NULL are placed in one group. |
| `DISTINCT a` | Retains a single NULL representative in the result set. |
| `COUNT(a)` | Does not count NULL values of `a`. |
| `COUNT(*)` | Counts every row, including rows with NULL columns. |

Understanding these rules prevents confusion when moving from JOINs to aggregation or reconciliation.

## 27. Checking Multiple Left-Hand Rows with No Right-Hand Match

A table having a NULL key does not mean there is only **one** unmatched row.

In `orders`, both orders 105 and 108 have `customer_id = NULL`. In `orders LEFT JOIN customers`:

```sql
SELECT
    o.order_id,
    o.customer_id,
    c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
ORDER BY o.order_id;
```

The result still has **two rows** — one row per order, never collapsed into a single "NULL customer" row.

Conversely, if you write:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS number_of_orders
FROM join_check.orders AS o
GROUP BY o.customer_id
ORDER BY o.customer_id NULLS LAST;
```

then the two NULL orders are counted into one group. Distinguish **JOIN preserving individual entities** from **GROUP BY collapsing by key value**.

## 28. Never Let Joins Depend on Uncontrolled Transformations

Sometimes two sources use different code formats: one has trailing spaces, another uses uppercase, or one is text while the other is numeric.

Illustrative example:

```sql
SELECT
    ' ABC '::text AS raw_code,
    trim(' ABC ') AS normalized_code,
    lower(trim(' ABC ')) AS normalized_lower;
```

You can join using expressions:

```sql
-- Structural example; substitute real tables and business rules.
-- ON lower(trim(a.code)) = lower(trim(b.code))
```

Yet normalizing keys on the fly during a JOIN carries trade-offs:

- It can merge two distinct values into one if case or whitespace actually carries meaning.
- Expressions on keys may require expression indexes or dedicated normalized columns to achieve acceptable performance.
- A table containing multiple rows after normalization can create multiple matches, causing the JOIN to multiply rows.
- Unchecked casts can fail when staging data contains unparseable strings.

In ingestion pipelines, it is usually better to separate **normalization, validation, and duplicate-key detection** from critical business JOINs.

## 29. Inspecting Execution Plans Without Confusing Them with Correctness

PostgreSQL may pick a nested loop, hash join, or merge join depending on table sizes and statistics. Never treat a particular JOIN algorithm as proof that a query is right or wrong.

```sql
EXPLAIN
SELECT
    c.customer_id,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

`EXPLAIN` shows the estimated plan. If you want to measure execution:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

`EXPLAIN ANALYZE` actually executes the query to measure runtime statistics. In a lab, read-only queries are safe under light load; in production, always consider the execution cost of the specific SQL query.

### 29.1. Two Separate Axes of Verification

| Axis | Question | Tools |
| --- | --- | --- |
| **Data correctness** | Are all customers kept? Are key pairs right? Are rows multiplied? | Edge-case datasets, key-set comparisons, COUNT, EXCEPT, NOT EXISTS, aggregate checks. |
| **Performance** | How many rows does the JOIN read? Which indexes are used? Are there heavy sorts/hashes? | EXPLAIN, ANALYZE, BUFFERS, statistics, latency measurement. |

Do not skip correctness checks just because an execution plan looks "clean". A query that uses an index very efficiently while joining on the wrong column just returns the wrong business answer faster.

## 30. Handling NULL Results in Java/JDBC Applications

When PostgreSQL returns a `LEFT JOIN`, right-hand table columns can be SQL NULL due to no matching row.

Example:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

The Java application must preserve the exact meaning:

- For customer 4, `order_id` means **no matching order**, not an order with ID 0.
- If using `ResultSet.getLong("order_id")`, JDBC returns primitive `long`, which becomes 0 when the SQL value is NULL; you must call `wasNull()` to tell them apart.
- You can use `ResultSet.getObject("order_id", Long.class)` with compatible drivers to receive a nullable `Long` and avoid primitive-zero bugs.
- A DTO representing "no order object" should use an appropriate nullable/optional type rather than fabricating a fake order with ID 0.

Illustrative Java snippet:

```java
try (ResultSet rs = preparedStatement.executeQuery()) {
    while (rs.next()) {
        long customerId = rs.getLong("customer_id");
        Long orderId = rs.getObject("order_id", Long.class);

        if (orderId == null) {
            // Customer exists, but the LEFT JOIN row has no matching order.
        } else {
            // Real order exists with ID orderId.
        }
    }
}
```

This snippet assumes `preparedStatement` has already been created and executed in a valid JDBC context. Its purpose is interpreting NULL values in results, not replacing a complete application mapping layer.

### 30.1. COALESCE Can Fit Display Labels, Never IDs

```sql
SELECT
    c.customer_name,
    COALESCE(o.order_status, 'No orders yet') AS order_label
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id;
```

This is a display-label formatting choice, which can be convenient for a UI. However:

```sql
-- Do not arbitrarily convert a missing order into ID 0:
-- COALESCE(o.order_id, 0) AS order_id
```

When an ID column identifies an entity, a fake value of 0 can be mistaken by the application for a valid entity or trigger bad requests. Keeping IDs nullable and handling missing relationships explicitly is far safer.

## 31. JOIN Verification Checklist Before Shipping Reports

A short checklist you can apply to every query:

1. **State the expected grain.** One customer, one order, one customer–order pair, one date bucket?
2. **Identify which side must be preserved.** Choose INNER, LEFT, RIGHT, or FULL according to the goal.
3. **Inspect join keys.** Data types, NULLs, uniqueness, FKs, and potential multi-row matches.
4. **Prepare edge cases.** Include matched rows, left/right unmatched rows, NULL keys, staging orphans, and duplicate keys.
5. **Predict row counts and IDs.** Do not wait for output before deciding what counts as right.
6. **Check ON vs. WHERE.** Especially for filters on the right-hand table of an outer join.
7. **Count properly.** `COUNT(*)` differs from `COUNT(right.pk)`; `SUM` can be inflated by row multiplication.
8. **Verify anti-joins.** `NOT EXISTS` is usually safer than `NOT IN` when subqueries can yield NULL.
9. **Reconcile key sets, not just totals.** Use `EXCEPT`, `COUNT(DISTINCT)`, or expected-set assertions.
10. **Keep unmatched semantics clear.** NULL is not synonymous with a non-existent ID or a constraint violation.
11. **Check Java/API output.** Nullability in ResultSets and DTOs must accurately reflect the data.
12. **Measure performance only after correctness.** `EXPLAIN` is no substitute for proving business correctness.

## 32. Practice Exercises

The following exercises use the **6 customers, 8 orders, 4 staging rows** dataset created in section 2; if you ran the `INSERT` example adding order 109 or modified the tables, reset the lab data before comparing against the fixed solutions.

### Exercise 1. Predicting INNER JOIN

Write a query displaying `order_id` and `customer_name` for orders with a valid customer. Predict the row count and list of `order_id`s.

**Hint:** use `JOIN ... ON c.customer_id = o.customer_id`, then order by `order_id`.

### Exercise 2. Preserving All Customers

Write a query displaying all customers and their `order_id` if any, including customers 4 and 6.

**Hint:** `customers LEFT JOIN orders` without filtering right-hand columns in `WHERE`.

### Exercise 3. Preserving All Orders

Write a query displaying all orders and the customer name if any. Verify orders 105 and 108 stay in the result.

**Hint:** `orders LEFT JOIN customers`.

### Exercise 4. FULL JOIN

Write a `FULL OUTER JOIN` to count three groups: matched, customer_without_order, and order_without_customer. Predict each group's count and the total.

**Hint:** use `CASE` on the two non-NULL primary keys.

### Exercise 5. Two Versions of Filtering Paid Orders

Write two queries:

1. Only customers **who have paid orders**.
2. **All customers**, attaching paid orders if any exist.

Place `order_status = 'paid'` appropriately in `WHERE` or `ON`. Explain why the row counts differ.

### Exercise 6. COUNT(*) vs. COUNT(order_id)

Write a summary per customer showing both `COUNT(*)` and `COUNT(o.order_id)` after a `LEFT JOIN`. Explain why customer Dung returns 1 and 0.

### Exercise 7. Staging Orphans

Find `order_imports` records whose `external_customer_id` is non-NULL yet matches no customer. Distinguish them from records lacking an ID.

**Expected:** import 202 is an unknown ID, 203 is a missing ID.

### Exercise 8. NOT IN and NULL

Try three ways to find customers without orders: `NOT EXISTS`, `LEFT JOIN ... IS NULL`, and `NOT IN` with a subquery that does not filter out NULLs. Explain why the third fails to return 4 and 6 on this dataset.

### Exercise 9. NULL-Safe JOIN

Join `customers.region_code` to `delivery_zones.region_code` using `=` and using `IS NOT DISTINCT FROM`. Compare the 5-row and 7-row results.

### Exercise 10. Row Multiplication from Duplicate Zone Data

Join `customers`, `orders`, and `delivery_zones` to compute total amount per customer. Why are Chi's and Ha's totals doubled? Fix it using `EXISTS` if you only need to filter for customers with at least one zone.

### Exercise 11. Finding Orders Without Customers

Find orders with `customer_id IS NULL`; compare against `orders LEFT JOIN customers WHERE c.customer_id IS NULL`. On a table with an FK and current data, do both match? On staging without an FK, how would orphan detection differ?

### Exercise 12. Right Row Count, Wrong ID Set

Suppose two queries both return 6 rows. Propose at least two additional checks to tell which query is right.

**Hint:** sorted `order_id` set, `(customer_id, order_id)` pairs, and two-way `EXCEPT`.

### Exercise 13. Paid Aggregation Per Customer Without Dropping Unpaid Customers

Write `COUNT(o.order_id) FILTER (WHERE ...)` to return paid order counts for all customers, including customers with 0 paid orders.

### Exercise 14. WHERE on the Left-Hand Table

Compare:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND c.customer_id = 1;
```

with:

```sql
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 1;
```

Explain why the first query does not return only customer 1.

### Exercise 15. Writing an Automated Check

Write a single `SELECT` returning boolean `pass` if:

- INNER JOIN has 6 rows.
- FULL JOIN has 10 rows.
- The set of customers without orders is exactly `{4,6}`.

Do not use any data modification or table-dropping statements.

## 33. Solutions and Explanations

### Solution 1: INNER JOIN

```sql
SELECT o.order_id, c.customer_name
FROM join_check.orders AS o
JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

Result has 6 orders: 101, 102, 103, 104, 106, 107.

### Solution 2: All Customers

```sql
SELECT c.customer_id, c.customer_name, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id NULLS LAST;
```

8 rows, including customers 4 and 6 with `order_id = NULL`.

### Solution 3: All Orders

```sql
SELECT o.order_id, o.customer_id, c.customer_name
FROM join_check.orders AS o
LEFT JOIN join_check.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
```

8 rows, in which orders 105 and 108 have `customer_name = NULL`.

### Solution 4: FULL JOIN Three Groups

```sql
WITH classified AS (
    SELECT
        CASE
            WHEN c.customer_id IS NULL
                THEN 'order_without_customer'
            WHEN o.order_id IS NULL
                THEN 'customer_without_order'
            ELSE 'matched'
        END AS join_class
    FROM join_check.customers AS c
    FULL JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
)
SELECT join_class, COUNT(*) AS row_count
FROM classified
GROUP BY join_class
ORDER BY join_class;
```

Expected: matched = 6; customer_without_order = 2; order_without_customer = 2; total = 10.

### Solution 5: WHERE vs. ON

```sql
-- Only customer–paid order pairs:
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.order_status = 'paid';

-- All customers, attaching paid orders if any:
SELECT c.customer_id, o.order_id
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid';
```

The first query has 4 rows; the second has 6 rows on this dataset.

### Solution 6: COUNT

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS orders_count
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Customers 4 and 6 have no orders yet still produce one NULL-extended row, so `COUNT(*) = 1` and `COUNT(o.order_id) = 0`.

### Solution 7: Distinguishing Staging Orphans

```sql
SELECT
    i.import_id,
    CASE
        WHEN i.external_customer_id IS NULL THEN 'missing_id'
        WHEN c.customer_id IS NULL THEN 'unknown_id'
        ELSE 'valid_id'
    END AS import_status
FROM join_check.order_imports AS i
LEFT JOIN join_check.customers AS c
    ON c.customer_id = i.external_customer_id
ORDER BY i.import_id;
```

Expected: 201 valid, 202 unknown, 203 missing, 204 valid.

### Solution 8: Anti-Join and NULL

```sql
SELECT c.customer_id
FROM join_check.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_check.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
```

Returns 4 and 6. `NOT IN` with a subquery containing NULL evaluates to UNKNOWN for non-matching keys, causing `WHERE` to reject them.

### Solution 9: NULL-Safe Equality

```sql
SELECT
    (SELECT COUNT(*)
     FROM join_check.customers AS c
     JOIN join_check.delivery_zones AS z
       ON z.region_code = c.region_code) AS normal_count,
    (SELECT COUNT(*)
     FROM join_check.customers AS c
     JOIN join_check.delivery_zones AS z
       ON z.region_code IS NOT DISTINCT FROM c.region_code)
       AS null_safe_count;
```

Results 5 and 7. The difference comes from Binh and Lan having `region_code = NULL`, which matches the NULL zone when using `IS NOT DISTINCT FROM`.

### Solution 10: Avoiding Sum Multiplication

```sql
SELECT
    c.customer_id,
    SUM(o.amount) AS total_amount
FROM join_check.customers AS c
JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
WHERE EXISTS (
    SELECT 1
    FROM join_check.delivery_zones AS z
    WHERE z.region_code = c.region_code
)
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Matches source data: An 170,000; Chi 50,000; Ha 70,000. Orders are not multiplied by zone row counts.

### Solution 11: Unassigned Orders

```sql
SELECT order_id
FROM join_check.orders
WHERE customer_id IS NULL
ORDER BY order_id;
```

Returns 105 and 108. With a valid FK on `orders` and the current data, `orders LEFT JOIN customers WHERE c.customer_id IS NULL` also returns those two orders. On staging without an FK, you must distinguish **NULL IDs** from **non-existent IDs** as shown in section 9.

### Solution 12: Multi-Dimensional Verification

You can compare `array_agg(order_id ORDER BY order_id)`, run `EXCEPT` on ID sets or ID pairs, and check `GROUP BY order_id HAVING COUNT(*) > 1` to catch row multiplication. `COUNT(*)` alone is not enough.

### Solution 13: Counting Paid Orders While Keeping All Customers

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_orders
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Expected across customers 1 through 6: `1,1,1,0,1,0`.

### Solution 14: Condition on the Left Table

In `ON`, `c.customer_id = 1` only controls which customer–order pairs get joined; the other customers still appear because `LEFT JOIN` preserves the left side. In `WHERE`, the condition excludes all other customer rows from the output.

### Solution 15: PASS/FAIL

```sql
WITH missing_customers AS (
    SELECT c.customer_id
    FROM join_check.customers AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM join_check.orders AS o
        WHERE o.customer_id = c.customer_id
    )
)
SELECT
    (
        (SELECT COUNT(*)
         FROM join_check.customers AS c
         JOIN join_check.orders AS o
           ON o.customer_id = c.customer_id) = 6
        AND
        (SELECT COUNT(*)
         FROM join_check.customers AS c
         FULL JOIN join_check.orders AS o
           ON o.customer_id = c.customer_id) = 10
        AND
        (SELECT array_agg(customer_id ORDER BY customer_id)
         FROM missing_customers) = ARRAY[4, 6]::bigint[]
    ) AS pass;
```

Expected: `true`.

## 34. A Complete Verification Test for a Customer Report

Suppose a real requirement states:

> Display all customers, their paid order count, and their total paid amount. Customers with no purchases or no paid orders must still appear with 0.

### 34.1. Query Satisfying the Requirement

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS paid_total
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
   AND o.order_status = 'paid'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Expected result:

| customer_id | customer_name | paid_order_count | paid_total |
| ---: | --- | ---: | ---: |
| 1 | An | 1 | 120000.00 |
| 2 | Binh | 1 | 90000.00 |
| 3 | Chi | 1 | 20000.00 |
| 4 | Dung | 0 | 0 |
| 5 | Ha | 1 | 70000.00 |
| 6 | Lan | 0 | 0 |

Properties:

- Every customer gets one row thanks to `GROUP BY` on the customer key.
- Pending/cancelled orders are not counted because the paid condition lives in `ON`.
- Customers without paid orders are not dropped because `LEFT JOIN` keeps them.
- `COUNT(o.order_id)` returns 0 when there are no paid orders.
- `COALESCE(SUM(o.amount), 0)` returns 0 for groups with no amounts to sum, matching the stated reporting rule.

### 34.2. An Alternative Using FILTER

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) FILTER (
        WHERE o.order_status = 'paid'
    ) AS paid_order_count,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.order_status = 'paid'
        ),
        0
    ) AS paid_total
FROM join_check.customers AS c
LEFT JOIN join_check.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

On the lesson dataset, both approaches return the exact same result. Using `FILTER` can be easier to extend if you later want pending, cancelled, and paid order counts in the same report table.

### 34.3. Reconciling the Paid Total

The total amount across all paid orders that have a customer is:

```sql
SELECT SUM(o.amount) AS paid_source_total
FROM join_check.orders AS o
WHERE o.order_status = 'paid'
  AND o.customer_id IS NOT NULL;
```

Expected: `300000.00` (120000 + 90000 + 20000 + 70000).

The sum of `paid_total` after grouping across all customers must also equal 300000.00 when no row multiplication occurs:

```sql
WITH report AS (
    SELECT
        c.customer_id,
        COALESCE(SUM(o.amount), 0) AS paid_total
    FROM join_check.customers AS c
    LEFT JOIN join_check.orders AS o
        ON o.customer_id = c.customer_id
       AND o.order_status = 'paid'
    GROUP BY c.customer_id
)
SELECT SUM(paid_total) AS report_total
FROM report;
```

This is an **additional aggregate check**. To be certain the output is right, also reconcile order counts, key sets, and unmatched cases.

## 35. Summary

Verifying a `JOIN` in PostgreSQL means verifying the **semantics of the output data**, not merely checking whether SQL runs.

Core principles:

- **`INNER JOIN` keeps only matched pairs.** It excludes both customers without orders and orders without customers.
- **`LEFT/RIGHT/FULL OUTER JOIN` preserve their respective sides**, with unmatched rows padded with SQL NULL; those rows can still be eliminated by `WHERE`.
- **`NULL = NULL` does not evaluate to TRUE** in `ON` conditions. Use `IS NOT DISTINCT FROM` only when the business truly considers two NULLs equivalent.
- **NULL keys differ from non-existent keys.** A table with a nullable FK can legally hold NULL; an ID like 999 without a parent is normally blocked by an FK, except in unconstrained models such as staging.
- **Conditions in `ON` versus `WHERE` can change outer join results.** To keep the full left side while joining only paid orders, put the paid condition in `ON` or use aggregate `FILTER`.
- **`COUNT(*)` differs from `COUNT(right.pk)`.** A customer without orders still gets a row in `LEFT JOIN`, so you must count the right-hand key to obtain an order count of 0.
- **Joining on non-unique keys can multiply rows and inflate `SUM`.** Check cardinality and use `EXISTS` when you only need to know a relationship exists.
- **`NOT EXISTS` is usually the right fit for anti-joins**, whereas `NOT IN` over a subquery containing NULLs easily yields an unexpected empty set.
- **Do not compare row counts alone.** Check ID sets, required rows, unmatched groups, aggregate totals, and per-key multiplicity.
- **Handle NULLs properly in applications** so a missing relationship is never turned into a fake entity.

Whenever you write any `JOIN` for a report or API, ask yourself: **"If one side has no data at all, if the join key is NULL, or if the other side has two rows sharing the same key, what exactly will this query return?"** When you have a test dataset and reconciliation SQL queries answering that question, confidence in your query will be far higher than from merely running it on data that happens to be complete.
