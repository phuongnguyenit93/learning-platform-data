# Writing Index-Friendly Predicates and Avoiding Unintended Type Conversions

A query may have a suitable index, yet MySQL can still end up scanning many rows if the WHERE condition wraps the column in a function, performs arithmetic on the column, or compares two sides with incompatible data types. A predicate written so the optimizer can use an index to locate the data range is commonly called a **sargable predicate**.

For the **DATABASE_MYSQL** module, writing sargable predicates helps reduce rows read, leverage index range/ref lookups, and avoid incorrect results caused by implicit conversions. This lesson focuses on writing predicates on numbers, strings, and dates/times; handling collations; binding parameters with the right types in Java/JDBC; and verifying with EXPLAIN.

## 1. What Is a Sargable Predicate?

Sargable refers to a condition that can be translated into an index search operation. For example, if there is an index on created_at:

~~~sql
-- Can use an index range scan on created_at
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

The predicate defines a clear range over values stored in the index. MySQL can locate the starting point and read only the entries in the required range.

Conversely:

~~~sql
-- Function is applied to the indexed column
SELECT order_id, created_at
FROM orders
WHERE YEAR(created_at) = 2026;
~~~

With a standard B-tree index on created_at, the optimizer cannot directly use the value of YEAR(created_at) to locate a key range like the first statement. It may have to evaluate the function across many rows or choose a different plan.

Sargable does not guarantee the optimizer will always choose the index. If the condition matches most of the table, a table scan can still be cheaper. Sargability simply gives the optimizer the opportunity to use an index effectively.

## 2. Avoid Wrapping Indexed Columns in Functions

A practical rule: if you want to leverage a B-tree index on a column, keep the column bare in the predicate and transform the input value instead of transforming every row of the column.

### Dates and Times

Avoid:

~~~sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
~~~

Rewrite as a half-open range:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
~~~

The second predicate can use an index range scan on created_at and does not miss fractional microseconds at the end of the day.

### Arithmetic on Columns

Suppose there is an index on salary. Avoid:

~~~sql
WHERE salary * 1.10 > 10000
~~~

You can move the arithmetic to the constant side:

~~~sql
WHERE salary > 10000 / 1.10
~~~

This is an algebraic transformation for a simple example. With DECIMAL, scale, rounding, and parameter types must be chosen carefully to preserve exact business rules. Do not apply mechanically if the transformation changes precision or NULL handling.

### Normalized Strings

If email is indexed and its collation is already case-insensitive as required, do not call LOWER on the column:

~~~sql
-- May hinder lookup using a regular index
WHERE LOWER(email) = LOWER(?)

-- Compare directly if collation/schema already satisfies the rule
WHERE email = ?
~~~

If business logic mandates comparing in a normalized form while preserving the original value in the column, consider a generated column storing the normalized value or a functional index. Verify the expression, collation, and MySQL version before applying.

## 3. Compare Values of the Same Data Type

MySQL can implicitly convert types when comparing two expressions of different types. Implicit conversion makes SQL flexible, but it can:

- Produce results that differ from business intent.
- Prevent the optimizer from using an index on the column.
- Generate warnings when strings fail to convert to numbers or dates.
- Strip leading zeros from identifier codes.
- Cause discrepancies due to signed/unsigned or character set/collation mismatches.

Choose the right data type in the schema and pass comparison values with the exact same type as the column.

This rule also applies to JOINs. If customers.customer_id is BIGINT UNSIGNED while orders.customer_id is VARCHAR, the join expression may require type conversion and impair index usage on one or both sides. Align data types, signedness, and data semantics of linked columns directly in the schema:

~~~sql
-- Linked columns should share the same type and signedness
customers.customer_id BIGINT UNSIGNED NOT NULL
orders.customer_id    BIGINT UNSIGNED NOT NULL
~~~

Do not work around schema mismatches by CASTing columns in every JOIN query. If legacy data must be migrated, standardize the type in a migration or add a transitional indexed column during the rollout.

### Non-Numeric Identifier Strings

Suppose customer_code is VARCHAR and indexed:

~~~sql
CREATE TABLE external_customers (
    customer_code VARCHAR(32) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (customer_code)
) ENGINE=InnoDB;
~~~

Do not compare string codes against numbers:

~~~sql
-- MySQL may convert strings to numbers for comparison
SELECT customer_code, full_name
FROM external_customers
WHERE customer_code = 123;
~~~

When comparing a string column with a number, MySQL may cast string values to numeric values. Strings like '00123', '123', or strings containing non-digit characters may be interpreted numerically instead of being compared as literal codes. This risks both business bugs and preventing the string index from being used for efficient lookup.

Write with the matching type:

~~~sql
SELECT customer_code, full_name
FROM external_customers
WHERE customer_code = '00123';
~~~

If codes can contain leading zeros, hyphens, or letters, store and compare them as CHAR/VARCHAR. Do not turn identifiers into numbers just because most characters happen to be digits.

### Numeric Columns Should Be Compared with Numeric Values

If order_id is BIGINT UNSIGNED, bind a corresponding unsigned integer parameter:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE order_id = 123456;
~~~

Avoid passing an arbitrary string and relying on MySQL to coerce it. For out-of-range values or invalid strings, conversion can emit warnings or errors depending on context.

## 4. Watch Out for Signed and Unsigned

MySQL distinguishes signed and unsigned numeric types. For instance, INT and INT UNSIGNED have different value ranges. When comparing two expressions with different signedness, type conversion rules can alter results at boundary values.

If a primary key is declared as:

~~~sql
customer_id BIGINT UNSIGNED NOT NULL
~~~

use the matching parameter type and never pass negative numbers. In Java, long is signed; before binding, validate that the value is non-negative and within the BIGINT UNSIGNED range supported by the application. If the business range exceeds Java long capacity, use BigInteger and an appropriate bind/serialization strategy.

Do not CAST the key column to SIGNED or UNSIGNED in WHERE just to make both sides match:

~~~sql
-- Can prevent direct index usage on customer_id
WHERE CAST(customer_id AS SIGNED) = ?
~~~

Normalize the parameter type in the application layer or CAST the parameter value to the column type when there is a clear reason. Keep the column bare so the index can be leveraged.

## 5. Avoid Implicit Date/Time Conversions

For DATE, DATETIME, or TIMESTAMP, pass literals in the ISO format MySQL understands unambiguously:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Do not pass locale-dependent date strings like '01/02/2026' and expect MySQL to guess whether it means February 1 or January 2.

If the source is a custom-formatted string, convert the string on the input value side:

~~~sql
WHERE created_at >= STR_TO_DATE(?, '%d/%m/%Y')
  AND created_at <  STR_TO_DATE(?, '%d/%m/%Y')
~~~

In the application, it is better to parse the string into LocalDate/LocalDateTime and bind the proper JDBC type. When filtering a single day on DATETIME, build a range from start of day to before start of next day; do not call DATE() on the column if you want a regular index range scan.

With TIMESTAMP, understand the session time_zone and how the driver converts instants. Never strip the offset from source data and assume the remaining string is UTC. Parameter types and timezone rules must align with the schema and business logic.

## 6. Avoid Unintended Character Set and Collation Conversions

String comparisons depend on character set and collation. Collation determines comparison rules such as case sensitivity or accent sensitivity.

Inspect column configuration:

~~~sql
SHOW FULL COLUMNS FROM customers;

SELECT
    CHARSET(customer_code),
    COLLATION(customer_code)
FROM customers
LIMIT 1;
~~~

If a column uses a case-insensitive collation, comparisons may treat 'ABC' and 'abc' as equal. If identifiers must be case-sensitive, choose an appropriate collation in the schema from the start.

Do not arbitrarily apply COLLATE or CONVERT to an indexed column in every query:

~~~sql
-- Changes the compared expression and restricts using the existing index
WHERE customer_code COLLATE utf8mb4_bin = ?
~~~

If you need a collation different from the current storage rule, consider altering the column/index collation or creating a normalized column/functional index. Changing collation can affect unique constraints because two previously distinct strings may become equal under the new rule; check for duplicates before migrating.

## 7. LIKE and B-Tree Index Usability

With an index on customer_code, searching a fixed prefix can typically form a range:

~~~sql
SELECT customer_code
FROM external_customers
WHERE customer_code LIKE 'CUS-2026%';
~~~

A leading wildcard prevents MySQL from knowing where the prefix starts:

~~~sql
-- Usually cannot use a B-tree for prefix lookup
WHERE customer_code LIKE '%2026'
~~~

If the business requires searching substrings at any position, consider FULLTEXT for suitable text content, a search engine, or a specialized data structure. FULLTEXT is not equivalent to exact substring matching for all strings/codes.

LIKE results also depend on collation and escaping of wildcards '%' and '_'. If users enter literal strings containing wildcards, the application must escape them properly and specify ESCAPE if needed.

## 8. OR, IN, and Negation Conditions

An IN condition on the same column can be turned by the optimizer into multiple lookups/ranges:

~~~sql
SELECT order_id
FROM orders
WHERE status IN ('PAID', 'SHIPPED', 'DELIVERED');
~~~

An OR condition across different indexed columns may use Index Merge in some cases:

~~~sql
SELECT customer_id, full_name
FROM customers
WHERE email = 'a@example.com'
   OR phone = '+84123456789';
~~~

However, not every OR uses indexes well. If one branch is unselective or unindexed, the optimizer may choose a scan. Check EXPLAIN before rewriting.

Do not automatically replace OR with UNION ALL: a row satisfying both branches will appear twice unless duplicates are handled, changing semantics. If rewritten with UNION, deduplication adds overhead and may eliminate rows that were legitimately allowed to repeat.

Negation conditions such as <> or NOT IN are often unselective and may have to read many rows. NOT IN also carries a NULL trap in subqueries; if the intent is an anti-join, consider NOT EXISTS and check nullability.

## 9. NULL and Index-Friendly Predicates

Do not use equality to test for NULL:

~~~sql
-- Wrong semantics: comparison evaluates to UNKNOWN
WHERE deleted_at = NULL

-- Correct
WHERE deleted_at IS NULL
~~~

MySQL B-tree indexes can store NULL values; IS NULL predicates can use an index if the optimizer finds it beneficial. However, if most rows are NULL, the condition may not be selective enough for an index to help.

When a null-safe comparison between two expressions is needed, MySQL provides the <=> operator. However, do not wrap a column in COALESCE/IFNULL solely to replace NULL with a dummy value if doing so changes semantics or blocks index usage:

~~~sql
-- Function on column
WHERE COALESCE(deleted_at, '9999-12-31') > ?

-- If business logic agrees, split the predicate directly
WHERE deleted_at > ?
   OR deleted_at IS NULL
~~~

The two statements are equivalent only when business rules define NULL as greater than every timestamp. Verify semantics before rewriting; OR may require a different plan and must be measured with EXPLAIN.

## 10. Composite Indexes and Predicate Order

Suppose queries commonly filter by status and a created_at range:

~~~sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at);
~~~

Query:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

The index has equality on the leading column status and a range on created_at, so both parts can narrow the key range. Column order in the index matters more than the order predicates are written in WHERE.

If a query filters only by created_at without status, this index lacks a matching leftmost prefix for direct created_at lookup. A separate index starting with created_at may be needed if the actual workload requires it.

Do not create an index for every column permutation. Each index adds storage and write overhead; group queries by filter patterns and sort orders to select a minimal beneficial set of indexes.

## 11. When Should You Use a Generated Column or Functional Index?

Sometimes business requirements genuinely require searching by an expression, such as case-insensitive email lookup while keeping the original value stored. You can create a normalized generated column and index it:

~~~sql
CREATE TABLE users (
    user_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255)
        GENERATED ALWAYS AS (LOWER(email)) STORED,
    PRIMARY KEY (user_id),
    KEY idx_users_email_normalized (email_normalized)
) ENGINE=InnoDB;
~~~

Query:

~~~sql
SELECT user_id, email
FROM users
WHERE email_normalized = LOWER(?);
~~~

Functional indexes are supported starting in MySQL 8.0.13:

~~~sql
CREATE INDEX idx_users_lower_email
    ON users ((LOWER(email)));
~~~

The query expression must match the functional key part according to MySQL rules. An explicit generated column is often easier to inspect and reuse in the schema. Both approaches incur storage/maintenance overhead on data changes; do not add one merely to preserve a non-sargable predicate without measuring the benefit.

## 12. Bind Parameters with Correct Types in Java/JDBC

PreparedStatement separates data from SQL structure and lets the driver send values with the proper types. Do not concatenate parameters into SQL strings and do not bind every value as a String.

### Strings

~~~java
String sql = "SELECT customer_code, full_name " +
             "FROM external_customers " +
             "WHERE customer_code = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "00123");
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            String code = rs.getString("customer_code");
        }
    }
}
~~~

### Integers

~~~java
String sql = "SELECT order_id FROM orders WHERE order_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 123456L);
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
        }
    }
}
~~~

### Decimals

~~~java
String sql = "SELECT payment_id FROM payments WHERE amount >= ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBigDecimal(1, new BigDecimal("1000.00"));
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long paymentId = rs.getLong("payment_id");
        }
    }
}
~~~

### Dates

~~~java
String sql = "SELECT order_id FROM orders WHERE order_date = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, LocalDate.of(2026, 1, 15));
    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
        }
    }
}
~~~

The examples assume java.sql.PreparedStatement, java.sql.ResultSet, java.math.BigDecimal, and java.time.LocalDate are imported, and connection is an open JDBC Connection. String concatenation for the SQL literal works even on Java versions prior to text blocks. setObject(LocalDate) requires a JDBC driver supporting JDBC 4.2; for DATETIME/TIMESTAMP, use LocalDateTime/Instant or JDBC temporal types aligned with application and driver timezone rules.

PreparedStatement does not automatically fix a mismatched schema. If a column is VARCHAR while the application binds a number, or the column is BIGINT while the application sends arbitrary strings, type normalization at the application boundary is still necessary.

## 13. CAST the Parameter or CAST the Column?

If input arrives as a string while the column is numeric, casting the parameter is generally preferable:

~~~sql
-- Prefer keeping the indexed column bare
WHERE order_id = CAST(? AS UNSIGNED)

-- Avoid wrapping the column
WHERE CAST(order_id AS CHAR) = ?
~~~

However, it is still best to parse the input and bind the exact type from Java. Parameter CASTing should only be used when protocol or expression type constraints require it; it does not replace validation.

If source data is invalid, CAST may return a converted value with a warning or raise an error depending on type and SQL mode. Do not treat CAST as a validator. Validate data before querying or writing.

## 14. Verify with EXPLAIN

Do not assume an index will be used merely from the shape of the SQL. Check the plan:

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00';
~~~

Columns to inspect:

- type: access method such as range, ref, index, or ALL.
- possible_keys: indexes considered by the optimizer.
- key: the index actually selected.
- key_len: length of the key prefix used.
- rows: estimated number of rows to read.
- filtered: percentage of rows remaining after additional filter conditions.
- Extra: Using index, Using index condition, Using where, Using filesort...

Compare with the column-wrapped predicate:

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-01-15';
~~~

Plans can vary by data, indexes, version, and statistics. Not every query using ALL is wrong; small tables or predicates matching most rows can make a table scan cheaper.

If you need to measure actual rows and timing, use EXPLAIN ANALYZE on an appropriate SELECT in an environment whose load has been assessed. This command actually executes the query, so do not run it carelessly on heavy queries.

## 15. Workflow for Fixing Non-Sargable Predicates

1. Identify the indexed column and its declared data type.
2. Inspect WHERE, JOIN, and ORDER BY expressions for functions, arithmetic, or casts on columns.
3. Verify the types of literals and parameters on the application side.
4. Confirm business semantics for NULL, collation, signedness, and timezone.
5. Rewrite the predicate to keep the column bare and transform the input value side.
6. If querying by an expression is truly required, consider a generated column or functional index.
7. Run EXPLAIN before and after with the same parameter set.
8. Measure with EXPLAIN ANALYZE when appropriate to compare actual rows and timing.
9. Verify business results remain identical, especially at boundary values and with invalid inputs.
10. Measure write cost too if adding an index or generated column.

## 16. Common Mistakes

| Pattern | Potential issue | How to fix |
|---|---|---|
| YEAR(date_col) = 2026 | Function wrapping date column | Use a date range |
| DATE(date_col) = date | Function wrapping DATETIME column | Use a half-open range |
| numeric_col + 1 = ? | Arithmetic on column | Transform the parameter side if equivalent |
| varchar_code = 123 | Comparing string with number, losing code semantics | Bind string with the proper type |
| CAST(indexed_col AS CHAR) = ? | Casting on column | Bind/CAST the parameter |
| LOWER(indexed_col) = ? | Function on column | Suitable collation or generated/functional index |
| LIKE '%suffix' | Leading wildcard | Alternative search strategy if substring search is needed |
| COALESCE(indexed_col, ...) = ? | Function on column and altered NULL semantics | Split conditions if aligned with business rules |
| Binding every parameter with setString | Implicit conversion and type mismatch | Use setLong, setBigDecimal, setString, setObject appropriately |

## 17. Pre-Production Query Checklist

1. Do filter/join columns have suitable indexes?
2. Are any functions, arithmetic operations, or CASTs applied directly to indexed columns?
3. Do parameter types match column types and signedness?
4. Are string identifiers being compared as numbers?
5. Do strings use the character set/collation required by business rules?
6. Do date/time predicates use clear ranges and the right timezone?
7. Are NULLs handled with IS NULL/IS NOT NULL or proper logic?
8. Does LIKE have a fixed prefix or a leading wildcard?
9. Are composite indexes used along their leftmost prefix?
10. Does EXPLAIN pick an access path appropriate for data selectivity?
11. Have results been tested on boundary values, invalid strings, and NULL data?
12. If adding a functional index/generated column, do read gains outweigh write and storage costs?

## 18. Practice Exercises

1. Create an index on orders.created_at using CREATE INDEX idx_orders_created_at ON orders (created_at); compare EXPLAIN for YEAR(created_at) = 2026 vs a 2026 date range condition.
2. Create an external_customers table with customer_code VARCHAR and an index; compare customer_code = 123 with customer_code = '00123'.
3. Test code values '00123', '123', and '123A'; explain the risks of comparing strings with numbers.
4. Write a query salary * 1.1 > ? and rewrite it to keep salary bare; verify results at boundary values.
5. Compare LIKE 'CUS-2026%' and LIKE '%2026' on the same indexed column.
6. Use PreparedStatement with setString, setLong, and setBigDecimal matching the column types.
7. Inspect CHARSET and COLLATION of a column; test a case-sensitive query as required.
8. Create a LOWER(email) generated column, index it, and compare its plan against a LOWER(email) query without a functional index.
9. Use EXPLAIN and EXPLAIN ANALYZE to compare estimated vs actual rows after fixing a predicate.
10. Write a short note explaining why the rewritten query preserves semantics while achieving a better access path.

You complete this lesson when you can identify non-sargable predicates, transform input values instead of wrapping columns, bind parameters with matching types, and prove the improvement with EXPLAIN. The goal is to preserve exact business semantics while enabling MySQL to locate data via indexes.
