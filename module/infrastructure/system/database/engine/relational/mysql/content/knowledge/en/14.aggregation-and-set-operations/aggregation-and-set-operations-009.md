# UNION, UNION ALL, and Branch Data Type Compatibility

When you need to combine rows from multiple queries with the same structure, MySQL provides the UNION set operation. For example, an application may have a current orders table and an archive table, yet reports need to treat them as a single unified list. UNION lets you combine rows from multiple SELECT statements into one result set.

The two key variants are UNION DISTINCT (the default when written simply as UNION) and UNION ALL. UNION removes duplicate rows across the combined result; UNION ALL retains every row, including identical ones. Beyond choosing the right variant, you must ensure all branches have the same number of columns, matching column positions by meaning, and safely compatible data types.

This lesson falls within the DATABASE_MYSQL scope: SQL querying, multi-source data aggregation, data type control, duplicate handling, execution plan reading, and designing queries that stay resilient as schemas evolve.

## 1. What Is UNION?

UNION combines the results of two or more SELECT statements into a single result set. Each SELECT is called a branch (query block). Branches must return the same number of columns, and corresponding columns must have compatible data types.

Basic syntax:

~~~sql
SELECT column_a, column_b
FROM source_a

UNION [ALL | DISTINCT]

SELECT column_x, column_y
FROM source_b;
~~~

UNION matches by column position, not by column alias. The first column of the first SELECT pairs with the first column of the next SELECT; the second column pairs with the second column, and so on.

Example:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, customer_name
FROM customer_store;
~~~

The output contains rows from both sources. Even if the two tables use different column names, what matters is that corresponding column positions and meanings align.

### 1.1. How Does UNION Differ from JOIN?

UNION stacks rows from multiple results vertically. JOIN combines columns from tables horizontally based on row relationships.

| Criterion | UNION | JOIN |
|---|---|---|
| Combination method | Appends rows | Joins columns |
| Output column count | Follows the SELECT structure of the branches | Follows columns selected from the joined tables |
| Combination condition | Branches share the same column count and compatible types | Join condition between tables, except CROSS JOIN |
| Example | Combining current and archived orders | Pairing orders with customer details |

To combine customer lists from two systems, use UNION. To fetch orders along with customer names from a customer table, use JOIN.

## 2. UNION DISTINCT and UNION ALL

### 2.1. UNION Defaults to Removing Duplicate Rows

If ALL is omitted, UNION defaults to DISTINCT. MySQL eliminates duplicate rows in the combined result set.

~~~sql
SELECT 10 AS customer_id
UNION
SELECT 10
UNION
SELECT 20;
~~~

The result has only two rows: 10 and 20.

This can be written explicitly:

~~~sql
SELECT 10 AS customer_id
UNION DISTINCT
SELECT 10
UNION DISTINCT
SELECT 20;
~~~

UNION DISTINCT compares every column of the output row to determine whether two rows are duplicates. It has no awareness of primary keys or business keys.

### 2.2. UNION ALL Preserves Every Row

~~~sql
SELECT 10 AS customer_id
UNION ALL
SELECT 10
UNION ALL
SELECT 20;
~~~

The result has three rows: 10, 10, and 20. There is no deduplication step.

UNION ALL is appropriate when:
- Data sources represent non-overlapping partitions.
- You need to preserve multiplicity for summing or counting.
- Duplicate rows across sources still carry business meaning.
- You want to avoid unnecessary deduplication overhead.

Do not use UNION DISTINCT just to feel "safe." If duplicate records are valid, removing them corrupts the figures.

### 2.3. Comparing the Two Variants

| Criterion | UNION / UNION DISTINCT | UNION ALL |
|---|---|---|
| Retains duplicate rows | No | Yes |
| Default behavior | Yes, when writing plain UNION | Must write ALL |
| Duplicate handling | Must detect and remove duplicate rows in output | Does not deduplicate |
| Execution cost | Can be higher due to deduplication | Usually lower when deduplication is unnecessary |
| Output order | Not guaranteed without ORDER BY | Not guaranteed without ORDER BY |
| Suitable use case | Need a result set with no identical duplicate rows | Need to keep all rows from every branch |

UNION ALL avoids deduplication work, though that does not mean every UNION ALL query is dramatically faster. Actual cost depends on row count, execution plan, I/O, expressions, and how MySQL materializes results.

## 3. Structural Rules Across Branches

### 3.1. Branches Must Have the Same Number of Columns

Valid example:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, customer_name
FROM customer_store;
~~~

Invalid example because the first branch has two columns while the second has only one:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id
FROM customer_store;
~~~

MySQL raises an error because the SELECT statements do not have an equal number of columns.

If one source lacks a corresponding attribute, supply a placeholder value with an appropriate type:

~~~sql
SELECT customer_id, customer_name, email
FROM customer_online

UNION ALL

SELECT customer_id, customer_name, CAST(NULL AS CHAR(255))
FROM customer_store;
~~~

In this example, the store branch has no email, so it returns NULL in the email column position.

### 3.2. Column Order Must Match in Meaning

UNION does not match by alias or column name. The following example has the same two columns but in the wrong order:

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_name, customer_id
FROM customer_store;
~~~

If the two types are mutually convertible, the query may execute while placing data in the wrong columns. This is a dangerous logic bug because it does not necessarily raise a syntax error.

Always write explicit column lists in every branch, in the same order and with the same meaning. Avoid SELECT * in UNION because a schema change on one table can break column order or column count compatibility.

### 3.3. Output Column Names Come from the First SELECT

Column names of the UNION result are determined by the first SELECT list. Aliases in subsequent branches do not rename the output columns.

~~~sql
SELECT customer_id AS id, customer_name AS display_name
FROM customer_online

UNION ALL

SELECT store_customer_id AS customer_key, full_name AS full_name
FROM customer_store;
~~~

The result has columns named id and display_name, taken from the first SELECT. The aliases customer_key and full_name in the second branch are not used for output column names.

Therefore, put meaningful aliases in the first branch and ensure all branches align to those exact positions.

## 4. Data Type Compatibility Between Branches

Corresponding columns do not have to be declared with the exact same type, but their types must be combinable. MySQL determines each output column's type from the expressions across all branches.

This can introduce implicit type conversions. Without explicit control, the output can end up with unexpected precision, value range, or formatting.

Example:

~~~sql
SELECT 100 AS amount
UNION ALL
SELECT 25.50;
~~~

The result must represent both integers and decimals. MySQL synthesizes an output type capable of holding values from both branches. For financial data, proactively use DECIMAL rather than letting the result type depend on input literals/expressions.

### 4.1. Matching Value Domains with Explicit CAST

Suppose one source uses INT and another uses BIGINT UNSIGNED. If the output column is a non-negative identifier, cast explicitly:

~~~sql
SELECT
    CAST(customer_id AS UNSIGNED) AS customer_id,
    customer_name
FROM customer_online

UNION ALL

SELECT
    CAST(customer_key AS UNSIGNED),
    full_name
FROM customer_store;
~~~

Choose the target type based on the actual domain range. Do not cast every ID to INT if one source may hold values exceeding the INT range.

### 4.2. Monetary Values and DECIMAL

Do not mix DECIMAL with FLOAT/DOUBLE for monetary values when exact decimal arithmetic is needed.

~~~sql
SELECT
    CAST(total_amount AS DECIMAL(15, 2)) AS amount
FROM current_order

UNION ALL

SELECT
    CAST(archived_total AS DECIMAL(15, 2))
FROM archived_order;
~~~

Both branches return the exact same type DECIMAL(15,2). Choose a precision large enough for the largest possible values. If the target type is too narrow, data may be rounded, trigger warnings, or raise errors depending on SQL mode and context.

### 4.3. Strings and Lengths

If branches return strings of different lengths, MySQL derives result metadata capable of holding values across branches. However, proactively CAST when a stable data contract is needed for APIs, views, or temporary tables.

~~~sql
SELECT
    CAST(code AS CHAR(40)) AS reference_code
FROM current_reference

UNION ALL

SELECT
    CAST(legacy_code AS CHAR(40))
FROM old_reference;
~~~

If strings contain Unicode, ensure compatible character sets. You can specify the character set in CAST when needed:

~~~sql
SELECT
    CAST(code AS CHAR(100) CHARACTER SET utf8mb4) AS label
FROM source_a

UNION ALL

SELECT
    CAST(old_label AS CHAR(100) CHARACTER SET utf8mb4)
FROM source_b;
~~~

Do not use CAST to arbitrarily truncate data. The target length must be large enough to hold valid values.

### 4.4. Collation of String Branches

Two branches may use different character sets or collations. When MySQL combines the result expressions, it must resolve an applicable collation. If the branches are incompatible, the query can raise an Illegal mix of collations error.

Example proactively aligning both branches to the same character set/collation:

~~~sql
SELECT
    customer_name COLLATE utf8mb4_0900_ai_ci AS customer_name
FROM customer_online

UNION ALL

SELECT
    full_name COLLATE utf8mb4_0900_ai_ci
FROM customer_store;
~~~

The target collation must be compatible with the expression's character set and exist on the running MySQL version. If character sets differ, convert using CONVERT(... USING utf8mb4) before applying COLLATE.

Collation also affects duplicate detection in UNION DISTINCT. Two strings differing only in case or diacritics may be treated as equal under the resulting collation. Consequently, changing collation can change the row count produced by UNION DISTINCT.

### 4.5. NULL Values and Result Types

When one branch lacks data for a column, NULL can serve as a placeholder. However, if every branch returns untyped NULL or ambiguous types, the result metadata may not match expectations. CAST NULL to the target type:

~~~sql
SELECT
    customer_id,
    CAST(NULL AS CHAR(100)) AS note
FROM customer_online

UNION ALL

SELECT
    customer_id,
    note
FROM customer_store;
~~~

If the target column is decimal:

~~~sql
CAST(NULL AS DECIMAL(15, 2)) AS amount
~~~

If the target column is a date:

~~~sql
CAST(NULL AS DATE) AS effective_date
~~~

Casting placeholders ensures clients, views, and downstream processing receive stable data types.

### 4.6. Dates, Times, and Temporal Types

Do not mix date/time types with plain text strings just because both can render similarly. Standardize on DATE, DATETIME, or TIMESTAMP according to data semantics.

~~~sql
SELECT
    CAST(order_date AS DATETIME(6)) AS event_time
FROM current_order

UNION ALL

SELECT
    CAST(created_at AS DATETIME(6))
FROM archived_order;
~~~

If one source has only DATE and another has DATETIME, define the default time-of-day convention. Do not assume a date represents a point in a specific time zone if the data carries no time-zone information.

## 5. UNION DISTINCT Deduplicates Across the Entire Row

UNION DISTINCT has no knowledge of table business keys. It compares all selected columns.

Example:

~~~sql
SELECT 10 AS customer_id, 'An' AS customer_name
UNION
SELECT 10, 'An'
UNION
SELECT 10, 'Anh';
~~~

The result has two rows:
- (10, 'An')
- (10, 'Anh')

Even though customer_id repeats, the two rows are not identical because customer_name differs.

If you add a source column:

~~~sql
SELECT 10 AS customer_id, 'An' AS customer_name, 'online' AS source
UNION
SELECT 10, 'An', 'store';
~~~

The result has two rows because the source value differs. This is critical: adding source metadata makes rows distinct to UNION DISTINCT.

### 5.1. NULL in Deduplication

During UNION DISTINCT deduplication, rows that match across every column—including corresponding NULL positions—are treated as duplicates, retaining only one row.

~~~sql
SELECT NULL AS note
UNION
SELECT NULL;
~~~

The result has only one NULL row.

By contrast:

~~~sql
SELECT NULL AS note
UNION ALL
SELECT NULL;
~~~

The result has two NULL rows.

This rule applies specifically to set-result deduplication; do not infer that the SQL expression NULL = NULL evaluates to TRUE. Ordinary equality comparison between two NULLs still returns UNKNOWN.

## 6. UNION ALL for Current and Archive Tables

A practical use case is data split into an active table and a historical table, where reports need to view both sources.

Suppose two tables share the same structure:

~~~sql
CREATE TABLE orders_current (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE orders_archive (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(15, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE = InnoDB;
~~~

Combined query:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    'current' AS source_name
FROM orders_current

UNION ALL

SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    'archive'
FROM orders_archive;
~~~

Use UNION ALL when current and archive data are partitioned without overlap, or when every record must be kept. If the same order_id can exist in both tables, UNION ALL keeps both; handle that via explicit business rules rather than relying on blind deduplication.

### 6.1. Filtering Within Each Branch

You can place predicates in each SELECT to reduce the number of rows combined:

~~~sql
SELECT order_id, customer_id, total_amount, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'

UNION ALL

SELECT order_id, customer_id, total_amount, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01';
~~~

Predicates are applied at the source. If created_at is indexed, each branch can leverage an appropriate range scan.

### 6.2. Sorting and Limiting Results After Combining

~~~sql
SELECT order_id, customer_id, total_amount, created_at
FROM orders_current

UNION ALL

SELECT order_id, customer_id, total_amount, created_at
FROM orders_archive

ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

ORDER BY and LIMIT at the end apply to the entire UNION result set. If you want the 100 newest rows from each source before combining, wrap each branch in parentheses with its own ORDER BY/LIMIT.

## 7. ORDER BY and LIMIT in UNION

### 7.1. Final ORDER BY Applies to the Combined Result

~~~sql
SELECT customer_id, customer_name
FROM customer_online

UNION ALL

SELECT customer_id, full_name
FROM customer_store

ORDER BY customer_name ASC;
~~~

An ORDER BY placed after the final branch sorts the combined result. Column names/aliases referenced in a UNION's ORDER BY must use the output column names, which come from the first SELECT.

Do not rely on the incidental order in which MySQL returns branches. Without an outer ORDER BY, row order is not guaranteed.

### 7.2. Per-Branch ORDER BY and LIMIT

To limit each source before combining, use parentheses:

~~~sql
(SELECT order_id, total_amount, created_at
 FROM orders_current
 ORDER BY created_at DESC
 LIMIT 10)

UNION ALL

(SELECT order_id, total_amount, created_at
 FROM orders_archive
 ORDER BY created_at DESC
 LIMIT 10)

ORDER BY created_at DESC
LIMIT 10;
~~~

The query fetches at most 10 rows from each source, then combines them and takes the 10 newest rows overall.

ORDER BY inside a branch determines which rows are selected by that branch's LIMIT. The outer ORDER BY determines the final order. Without the final ORDER BY, the combined result still has no guaranteed ordering.

### 7.3. Aliases in ORDER BY

Output column names come from the first SELECT. Example:

~~~sql
SELECT total_amount AS amount
FROM orders_current

UNION ALL

SELECT archived_total
FROM orders_archive

ORDER BY amount DESC;
~~~

ORDER BY uses the alias amount from the first branch. Aliases in later branches do not rename the result.

If you need to sort by a complex expression that is awkward to reference directly, wrap the UNION in a derived table:

~~~sql
SELECT
    combined.order_id,
    combined.total_amount
FROM (
    SELECT order_id, total_amount
    FROM orders_current

    UNION ALL

    SELECT order_id, archived_total
    FROM orders_archive
) AS combined
ORDER BY combined.total_amount DESC;
~~~

## 8. Business-Key Deduplication Differs from UNION DISTINCT

Suppose an order_id can appear in both the current table and the archive table, and you want to prefer the current record. UNION DISTINCT will not solve this if other columns differ, because it only removes rows that are identical across all columns.

Use UNION ALL to retain rows and then pick one row per business key:

~~~sql
WITH combined_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        1 AS source_priority,
        'current' AS source_name
    FROM orders_current

    UNION ALL

    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        2 AS source_priority,
        'archive' AS source_name
    FROM orders_archive
),
ranked_orders AS (
    SELECT
        combined_orders.*,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY source_priority
        ) AS row_num
    FROM combined_orders
)
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at,
    source_name
FROM ranked_orders
WHERE row_num = 1;
~~~

ROW_NUMBER numbers rows within each order_id. The row with the smaller source_priority is selected. This explicitly encodes the priority rule and can be extended with criteria such as update timestamp.

Using CTEs and window functions requires MySQL 8.0 or later. On older versions, use an alternative strategy such as an anti-join or a staging table with row selection rules.

If two rows share the same order_id and source_priority, selection between them is non-deterministic. Add a stable tie-breaker such as updated_at DESC followed by a unique secondary key.

## 9. Data Type Compatibility: Comprehensive Example

When combining multiple sources, standardize the data type at every column position.

Example: a report pulling transactions from two systems with different column types:

~~~sql
SELECT
    CAST(transaction_id AS UNSIGNED) AS transaction_id,
    CAST(amount AS DECIMAL(15, 2)) AS amount,
    CAST(event_time AS DATETIME(6)) AS event_time,
    CAST(description AS CHAR(200) CHARACTER SET utf8mb4) AS description
FROM payment_current

UNION ALL

SELECT
    CAST(legacy_id AS UNSIGNED),
    CAST(legacy_amount AS DECIMAL(15, 2)),
    CAST(processed_at AS DATETIME(6)),
    CAST(legacy_note AS CHAR(200) CHARACTER SET utf8mb4)
FROM payment_legacy;
~~~

Before casting, check:
- Minimum and maximum value ranges.
- Number of decimal places to preserve.
- Maximum string length.
- Character set and collation.
- Date/time type and fractional seconds precision.
- Nullability of each column.

CAST can lose information if the target type is too narrow. For critical data, test on a copy and check warnings and boundary values before deploying.

### 9.1. Using Properly Typed NULL Placeholders

One branch may not have a corresponding column:

~~~sql
SELECT
    employee_id,
    employee_name,
    CAST(NULL AS DATE) AS terminated_date
FROM current_employee

UNION ALL

SELECT
    employee_id,
    employee_name,
    terminated_date
FROM former_employee;
~~~

Casting NULL makes the output type explicit and ensures clients receive consistent metadata.

### 9.2. Avoid Implicit Conversions Between Numbers and Strings

Do not write a query where one branch returns a numeric ID and another returns a string code without a unified representation rule:

~~~sql
SELECT customer_id AS reference_id
FROM customer_numeric

UNION ALL

SELECT external_code
FROM customer_external;
~~~

If the result should be a string identifier, convert both branches to a sufficiently long string type. If the result must be numeric, you cannot arbitrarily convert external_code when it contains letters.

~~~sql
SELECT CAST(customer_id AS CHAR(40)) AS reference_id
FROM customer_numeric

UNION ALL

SELECT CAST(external_code AS CHAR(40))
FROM customer_external;
~~~

Use this only if treating both identifiers as text matches business semantics. Do not cast merely to silence errors without verifying data meaning.

## 10. UNION and Text Collation

When applying UNION to string columns, MySQL must determine the result character set and collation. If branches use different collations, coercibility rules determine the resulting collation or raise an incompatibility error.

Inspect source column metadata:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.columns
WHERE TABLE_NAME IN ('customer_online', 'customer_store')
  AND COLUMN_NAME IN ('customer_name', 'full_name');
~~~

To unify them, convert branches to the same character set and collation:

~~~sql
SELECT
    customer_name COLLATE utf8mb4_0900_ai_ci AS display_name
FROM customer_online

UNION ALL

SELECT
    full_name COLLATE utf8mb4_0900_ai_ci
FROM customer_store;
~~~

If two columns do not yet share the same character set, use CONVERT(... USING utf8mb4) before COLLATE. Verify that the target collation exists on the server.

Note: collation also affects UNION DISTINCT deduplication. Under a case-insensitive collation, strings differing only by case may be treated as duplicates. If identifier data requires exact comparison, choose the right collation before using UNION DISTINCT.

## 11. UNION in Reporting and Data Aggregation

UNION is often used to combine uniformly structured datasets so an outer query can filter, group, or aggregate across them.

Example: consolidate revenue from two channels:

~~~sql
WITH all_sales AS (
    SELECT
        'ONLINE' AS channel,
        order_date,
        total_amount
    FROM online_sales

    UNION ALL

    SELECT
        'STORE' AS channel,
        sale_date,
        amount
    FROM store_sales
)
SELECT
    channel,
    YEAR(order_date) AS sales_year,
    SUM(total_amount) AS revenue,
    COUNT(*) AS transaction_count
FROM all_sales
GROUP BY channel, YEAR(order_date)
ORDER BY sales_year, channel;
~~~

Branches can use different column names in the first and later SELECTs, while output column names come from the first branch. Here, sale_date and amount from the store branch map by position to order_date and total_amount in the combined result.

Use UNION ALL to preserve individual transactions. Using UNION DISTINCT could collapse two genuinely distinct transactions that happened to occur on the same date for the same amount in the same channel.

## 12. UNION and Performance

### 12.1. When Is UNION DISTINCT Expensive?

UNION DISTINCT must identify and remove duplicate rows. On large datasets, this step can require temporary structures, many row comparisons, and additional CPU, memory, or I/O.

UNION ALL skips deduplication. When business logic does not require deduplication, choose ALL to avoid unnecessary work.

### 12.2. Push Filters Down into Each Branch

Instead of combining entire tables before filtering, filter inside each branch:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'
  AND status = 'PAID'

UNION ALL

SELECT order_id, customer_id, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01'
  AND status = 'PAID';
~~~

This gives each branch the chance to use appropriate indexes and reduces the number of rows combined. The optimizer may also push certain outer-query predicates down into branches, but verify the execution plan rather than assuming.

### 12.3. Select Only Necessary Columns

Avoid SELECT * when combining data. Selecting only required columns shrinks intermediate row width, data transfer volume, and deduplication overhead if DISTINCT is used.

### 12.4. Indexing Each Branch

Each SELECT is optimized using the tables and indexes of its own branch. If filtering by created_at on both tables, evaluate an index on created_at for each table. If filtering by status and a date range, a composite index may fit depending on workload.

UNION does not create a shared index over its combined output. If the combined result must be queried repeatedly like a table, consider a materialized table managed by the application or an ETL job.

### 12.5. Inspecting with EXPLAIN

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders_current
WHERE created_at >= '2025-01-01'

UNION ALL

SELECT order_id, customer_id, created_at
FROM orders_archive
WHERE created_at >= '2025-01-01';
~~~

Examine access type, possible_keys, key, estimated rows, and Extra for each branch. For complex queries, use EXPLAIN FORMAT=TREE or EXPLAIN ANALYZE in an appropriate environment to inspect the plan and actual execution metrics.

EXPLAIN ANALYZE executes the query to measure iterators. Do not run it casually on data-modifying queries or overly heavy queries in production.

## 13. UNION and Per-Branch ORDER BY

The final ORDER BY sorts the overall result. If you need per-branch ORDER BY/LIMIT, enclose each SELECT in parentheses.

Example: fetch the 5 newest transactions from each source and then pick the 5 newest overall:

~~~sql
(SELECT transaction_id, amount, created_at
 FROM payment_current
 ORDER BY created_at DESC
 LIMIT 5)

UNION ALL

(SELECT transaction_id, amount, created_at
 FROM payment_archive
 ORDER BY created_at DESC
 LIMIT 5)

ORDER BY created_at DESC
LIMIT 5;
~~~

If you omit parentheses or place ORDER BY in the wrong position, MySQL may interpret it as the ORDER BY for the entire UNION or raise a syntax error. Use parentheses to clarify the scope of LIMIT.

If you need deterministic results when multiple rows share the same created_at, add a unique tie-breaker to ORDER BY, such as created_at DESC, transaction_id DESC.

## 14. UNION with Views and CTEs

You can define a view that unifies multiple sources:

~~~sql
CREATE VIEW all_customer_events AS
SELECT event_id, customer_id, event_type, occurred_at
FROM current_customer_event

UNION ALL

SELECT event_id, customer_id, event_type, occurred_at
FROM archived_customer_event;
~~~

Then query it like a single data source:

~~~sql
SELECT customer_id, COUNT(*) AS event_count
FROM all_customer_events
GROUP BY customer_id;
~~~

A standard view does not pre-store results; querying the view is processed according to the view definition and optimizer plan. If you need stored results for fast reads, use a physical table or a system-managed materialization process.

A CTE lets you name a temporary combined result set within a single statement:

~~~sql
WITH all_events AS (
    SELECT event_id, customer_id, occurred_at
    FROM current_customer_event

    UNION ALL

    SELECT event_id, customer_id, occurred_at
    FROM archived_customer_event
)
SELECT customer_id, MAX(occurred_at) AS last_event_at
FROM all_events
GROUP BY customer_id;
~~~

CTEs organize queries into named steps, though they are not automatically faster than subqueries or views. Always check the execution plan.

## 15. Parameterizing UNION Queries in Applications

When branches take input parameters from an application, use prepared statements. Each placeholder in each branch is bound individually in order of appearance.

JDBC example:

~~~java
String sql = """
    SELECT order_id, total_amount, created_at
    FROM orders_current
    WHERE customer_id = ?
      AND created_at >= ?

    UNION ALL

    SELECT order_id, total_amount, created_at
    FROM orders_archive
    WHERE customer_id = ?
      AND created_at >= ?

    ORDER BY created_at DESC
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setTimestamp(2, fromTime);
    ps.setLong(3, customerId);
    ps.setTimestamp(4, fromTime);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read the combined result.
        }
    }
}
~~~

Never concatenate user input directly into SQL. Table names, column names, and keywords cannot be bound as parameter values; if query structure must vary dynamically, validate against a strict whitelist of allowed choices.

## 16. Common Pitfalls

| Error or Misconception | Cause | Solution |
|---|---|---|
| UNION reports column count mismatch | SELECTs have different numbers of columns | List columns explicitly and add typed placeholders |
| Data lands in wrong columns yet query still runs | Branches order columns differently | Standardize column order and meaning per position |
| Aliases from later branches do not appear | Result column names come from the first SELECT | Place aliases in the first branch |
| UNION drops valid rows | UNION defaults to DISTINCT | Use UNION ALL when all rows must be preserved |
| UNION DISTINCT fails to merge records sharing an ID | Other columns differ so full rows are not identical | Deduplicate by business key via GROUP BY/window logic |
| Adding source_name increases row count | Source column makes rows differ | Decide whether source belongs in deduplication criteria |
| Illegal mix of collations | String branches have incompatible collations | CONVERT and COLLATE to a common rule |
| Monetary amounts lose precision | Numeric types across branches mismatch or CAST is too narrow | Use DECIMAL with sufficient precision/scale |
| NULL placeholder gets unwanted metadata | NULL is not explicitly cast | CAST(NULL AS target_type) |
| ORDER BY sorts the wrong scope | Confusing branch ORDER BY with whole-UNION ORDER BY | Use trailing ORDER BY or parentheses per branch |
| Result order changes between runs | Missing outer ORDER BY | Specify outer ORDER BY with a tie-breaker |
| Slow query | DISTINCT, high row volume, or large branch scans | Consider ALL, early filtering, indexes, and EXPLAIN |

## 17. Safe UNION Design Process

Before combining multiple SELECT statements, follow these steps:

1. Decide whether the goal is combining all rows or producing a strictly unique row set.
2. Choose UNION ALL if every occurrence must be kept; choose UNION DISTINCT if full-row deduplication is genuinely required.
3. List output columns and the meaning of each position.
4. Ensure every branch returns the same number of columns in the same order.
5. Check data types, value ranges, precision, scale, string lengths, and NULLs.
6. Standardize character set/collation when branches return strings.
7. Explicitly CAST mismatched types or NULL placeholders when a stable output contract is required.
8. Place aliases in the first SELECT.
9. Place trailing ORDER BY/LIMIT for the whole result; use parentheses if individual branches need limits.
10. Filter early in each branch and select only needed columns to reduce intermediate data.
11. Run EXPLAIN and measure on representative data.
12. Handle business-key deduplication separately if uniqueness by ID is required.

## 18. Hands-on Exercises

### Exercise 1: UNION and UNION ALL

Run:

~~~sql
SELECT 1 AS value
UNION
SELECT 1
UNION
SELECT 2;
~~~

Then change UNION to UNION ALL. Count the rows in each result and explain the difference.

### Exercise 2: Combining Tables with Similar Structure

Create tables customer_online and customer_store. Combine customer_id, name, and email using UNION ALL. Try swapping column order in the second branch to observe the logic bug.

### Exercise 3: Standardizing Data Types

Create two sources whose amount columns are INT and DECIMAL, respectively. Combine them and inspect result type metadata. Rewrite both branches using CAST AS DECIMAL(15,2).

### Exercise 4: NULL Placeholders

Combine a current-employee table and a former-employee table where only the former-employee table has terminated_date. Use CAST(NULL AS DATE) in the current branch and verify the resulting column type.

### Exercise 5: Collation

Create two tables with name columns using different collations. Test UNION DISTINCT with values differing only in case or diacritics. Then align both branches to the same collation and compare row counts.

### Exercise 6: Deduplication by Business Key

Create two tables with overlapping order_id values but different total_amount values. Compare UNION DISTINCT with UNION ALL combined with ROW_NUMBER() OVER (PARTITION BY order_id). Prefer records from a designated source and explain why the two approaches differ.

### Exercise 7: ORDER BY and LIMIT

Take the 5 newest rows from each source, combine with UNION ALL, and take the 5 newest rows overall. Try removing parentheses around each branch and observe the scope of ORDER BY/LIMIT.

### Exercise 8: Reading EXPLAIN

Create indexes on filter columns of each source. Run EXPLAIN on UNION ALL and UNION DISTINCT over a larger dataset. Record access type, key, rows, and deduplication overhead.

## 19. Checklist Before Deploying UNION in Production

- [ ] Selected the right variant (UNION DISTINCT or UNION ALL) per business rules.
- [ ] Every branch has the exact same number of columns.
- [ ] Corresponding columns match in meaning and position.
- [ ] Output column names are defined in the first SELECT.
- [ ] Checked numeric types, precision/scale, string lengths, and temporal types.
- [ ] Used explicit CAST wherever a stable output type is needed.
- [ ] Checked character sets and collations across branches.
- [ ] Typed NULL placeholders explicitly.
- [ ] Understood that UNION DISTINCT deduplicates across entire rows.
- [ ] Used dedicated logic if business-key deduplication is needed.
- [ ] Scoped ORDER BY/LIMIT appropriately.
- [ ] Placed an outer ORDER BY when stable result ordering is required.
- [ ] Filtered early, selected only needed columns, and verified indexes per branch.
- [ ] Used prepared statements for input parameters.
- [ ] Verified EXPLAIN and results on representative data.

## 20. Conclusion

UNION combines SELECT results vertically. UNION defaults to DISTINCT and removes completely identical rows; UNION ALL keeps every row. The two variants are not interchangeable, as choosing the wrong one can either lose data or incur unnecessary deduplication cost.

For reliable UNION queries, branches must share the same column count, column position semantics, and compatible data types. Result column names come from the first SELECT; result data types are derived across branches. CAST explicitly to control precision, length, temporal types, NULL placeholders, or collations. If you need deduplication by business key, use key-based row selection logic rather than relying on UNION DISTINCT. Finally, scope ORDER BY properly, filter early, and inspect execution plans with EXPLAIN.

## Official References

- [MySQL 8.4 Reference Manual – UNION Clause](https://dev.mysql.com/doc/refman/8.4/en/union.html)
- [MySQL 8.4 Reference Manual – Set Operations](https://dev.mysql.com/doc/refman/8.4/en/set-operations.html)
- [MySQL 8.4 Reference Manual – CAST() and CONVERT()](https://dev.mysql.com/doc/refman/8.4/en/cast-functions.html)
- [MySQL 8.4 Reference Manual – Type Conversion in Expression Evaluation](https://dev.mysql.com/doc/refman/8.4/en/type-conversion.html)
- [MySQL 8.4 Reference Manual – Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.4/en/charset-collation-coercibility.html)
- [MySQL 8.4 Reference Manual – WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
