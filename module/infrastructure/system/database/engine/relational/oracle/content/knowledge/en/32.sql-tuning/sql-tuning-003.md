# Writing Index-Friendly Predicates and Avoiding Unintended Column Wrapping

A table already having an index yet the query still running a FULL TABLE SCAN is a common situation in Oracle SQL tuning. The cause may be that the predicate does not define a key range on the index, a function or type conversion is applied directly to the column, the column order in a composite index does not match, or the optimizer estimates a full scan is cheaper than index access.

A predicate capable of leveraging an index is commonly called a **sargable predicate** (search-argument-able predicate). The idea is that the WHERE expression should let the optimizer know it can search for key values within a defined range. For example:

~~~sql
WHERE order_date >= :from_date
  AND order_date <  :to_date
~~~

usually allows Oracle to use an index on ORDER_DATE to define a range. Conversely:

~~~sql
WHERE TRUNC(order_date) = :order_day
~~~

requests comparing the result of a function on every ORDER_DATE value. A regular B-tree index is built on raw ORDER_DATE values, so it does not directly store the order of TRUNC(ORDER_DATE). You can rewrite the predicate to compare the column directly, or create a function-based index if querying by that expression is a stable requirement.

However, sargability does not mean the optimizer is forced to use an index. Oracle still weighs selectivity, blocks to read, clustering factor, statistics, table size, parallelism, and the cost of other access paths. The goal is to enable index consideration, then verify the actual plan.

## 1. What is a sargable predicate?

A predicate can leverage an index when Oracle can use it to identify one or more key ranges in the index structure. Direct comparisons typically have this capability:

~~~sql
WHERE employee_id = :employee_id
WHERE hire_date >= :start_date
WHERE hire_date < :end_date
WHERE salary BETWEEN :min_salary AND :max_salary
WHERE department_id IN (10, 20, 30)
WHERE email IS NOT NULL
~~~

With a B-tree index on the corresponding column, Oracle can consider INDEX UNIQUE SCAN, INDEX RANGE SCAN, or another index access form depending on conditions and cost.

### 1.1 Direct predicates on columns

If there is an index:

~~~sql
CREATE INDEX orders_order_date_ix ON orders(order_date);
~~~

then the following predicates can define key ranges:

~~~sql
WHERE order_date = :p_date
WHERE order_date >= :p_start
WHERE order_date < :p_end
WHERE order_date BETWEEN :p_start AND :p_end
~~~

Operators `=`, `<`, `<=`, `>`, `>=`, and `BETWEEN` are common forms. IN-lists can also be handled through multiple index lookups or corresponding optimizer mechanisms.

### 1.2 Functions wrapping columns

Examples:

~~~sql
WHERE UPPER(last_name) = 'SMITH'
WHERE TRUNC(order_date) = DATE '2026-11-14'
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
WHERE NVL(status, 'NEW') = 'NEW'
WHERE SUBSTR(account_code, 1, 3) = 'ABC'
~~~

The expressions above no longer compare the raw column value directly. Regular B-tree indexes on LAST_NAME, ORDER_DATE, CREATED_AT, STATUS, or ACCOUNT_CODE do not necessarily support searching by function results.

Oracle can use a function-based index if the expression is indexed, or may transform certain expressions during optimization. Therefore, do not conclude based solely on syntax; check Predicate Information and access paths in the execution plan.

### 1.3 Functions on the comparison value side

Typically, applying a function to a bind or literal keeps the column in its direct form:

~~~sql
WHERE order_date >= TO_DATE(:date_text, 'YYYY-MM-DD')
~~~

An index on ORDER_DATE can still be considered because the conversion function is applied to the bind value. Still, applications should bind the proper DATE or TIMESTAMP type rather than sending strings for the database to convert every time.

Practical rules:

- Keep indexed columns in their raw form inside predicates whenever possible.
- Convert input values before comparison.
- Do not rely on implicit conversion.
- If business logic genuinely queries by an expression, consider a function-based index or virtual column.

## 2. Why do functions on columns hinder index usage?

A B-tree index stores keys ordered by the index expression values. If an index is created on ORDER_DATE, the key order is the order of raw date-time values. It does not automatically store precomputed results of TRUNC(ORDER_DATE), TO_CHAR(ORDER_DATE), or UPPER(LAST_NAME).

Example index:

~~~sql
CREATE INDEX orders_order_date_ix ON orders(order_date);
~~~

Query:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Oracle needs to find rows where the TRUNC result of each ORDER_DATE equals the requested date. The raw index is not directly sorted by TRUNC(ORDER_DATE), so a simple range scan on the raw index cannot identify all matching rows.

If the predicate is changed to:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

then the condition directly defines a time range on ORDER_DATE. The raw index can be used for a range scan.

### 2.1 Not every function prevents index usage

Important exceptions exist:

- A function-based index stores the evaluated expression values.
- A virtual column can define the expression and be indexed like a column.
- The optimizer can rewrite certain predicates into equivalent forms.
- Some functions may be supported by specialized indexes or domain indexes.
- A full scan can be cheaper than an index scan if the predicate returns most of the table.

Thus, the right principle is to avoid unnecessarily losing indexability, then verify with the actual plan.

## 3. Handling date-time conditions: avoiding TRUNC on columns

This is one of the most common cases.

### 3.1 Common but index-unfriendly predicate

~~~sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Suppose ORDER_DATE has a B-tree index. TRUNC is applied to the column for every value, so the index on ORDER_DATE may not be used for direct range access.

### 3.2 Rewriting with a half-open interval

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

The interval from the start of the day to just before the start of the next day covers every timestamp within the chosen day. The half-open form `[start, next_start)` has these advantages:

- Does not depend on assuming the end of day is 23:59:59.
- Includes fractional seconds if the column is TIMESTAMP.
- Does not overlap when querying consecutive days.
- Can use an index range scan on the raw column.

### 3.3 Using properly typed bind variables

The application should bind two DATE values:

~~~sql
WHERE order_date >= :p_day_start
  AND order_date <  :p_next_day_start
~~~

If inputs are strings:

~~~sql
WHERE order_date >= TO_DATE(:p_day_start_text, 'YYYY-MM-DD')
  AND order_date <  TO_DATE(:p_next_day_text, 'YYYY-MM-DD')
~~~

The conversion function sits on the bind side, not wrapping ORDER_DATE. Even so, binding native DATE types remains the better choice.

### 3.4 Avoiding BETWEEN when a whole day with time components is needed

BETWEEN is inclusive of both endpoints:

~~~sql
WHERE order_date BETWEEN DATE '2026-11-14'
                     AND DATE '2026-11-14'
~~~

The condition above only matches exact midnight, not all timestamps on that day. To query the entire day, use:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

Avoid setting an upper bound of 23:59:59 because TIMESTAMP can contain fractional seconds.

### 3.5 TIMESTAMP and timezones

With TIMESTAMP, still use a half-open interval, ensuring both binds share the same type and represent the exact business timezone. If the column is TIMESTAMP WITH TIME ZONE, clarify which timezone defines the day before computing start and next start. Do not assume every local day is always 24 hours long where daylight saving time transitions occur.

### 3.6 When to use a function-based index on TRUNC?

If the workload frequently filters by calendar day using TRUNC(ORDER_DATE) and SQL across many applications cannot be changed, you can create:

~~~sql
CREATE INDEX orders_order_day_fbi
    ON orders(TRUNC(order_date));
~~~

Query using the same expression:

~~~sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

The optimizer can use the function-based index if the cost is favorable. Account for index storage, INSERT/UPDATE/DELETE cost, index statistics, and expression matching with queries.

If only a single query is involved, rewriting it as a range on the raw column is usually simpler.

## 4. Avoiding implicit conversion on columns

Implicit conversion can make queries unpredictable, NLS-dependent, and lose index access if Oracle has to convert the column value itself.

### 4.1 Comparing NUMBER with strings

Suppose:

~~~sql
CREATE TABLE employees_demo (
    employee_id NUMBER,
    employee_code VARCHAR2(20)
);

CREATE INDEX employees_demo_id_ix
    ON employees_demo(employee_id);
~~~

Comparing a NUMBER column to a string:

~~~sql
WHERE employee_id = '100'
~~~

Oracle may convert the string literal/bind to NUMBER according to data type rules. However, the application should send a NUMBER bind and write:

~~~sql
WHERE employee_id = :p_employee_id
~~~

The reverse case is more dangerous. If EMPLOYEE_CODE is VARCHAR2 yet the query compares against a NUMBER:

~~~sql
WHERE employee_code = 100
~~~

Oracle must compare character values with a number; conversion rules may make the expression equivalent to `TO_NUMBER(EMPLOYEE_CODE) = 100`. This can:

- Prevent an index on EMPLOYEE_CODE from being used as expected.
- Raise ORA-01722 if the column contains non-numeric strings.
- Make behavior dependent on data and conversion rules.

Compare using matching types:

~~~sql
WHERE employee_code = '100'
~~~

If an identifier is a string, always bind VARCHAR2 and preserve string semantics. Do not convert it to NUMBER simply because current data happens to be all digits.

### 4.2 Comparing DATE with strings

Avoid writing:

~~~sql
WHERE order_date = '14-11-2026'
~~~

The string literal must be converted to DATE using the session's NLS_DATE_FORMAT. Results can vary across environments or raise errors.

Use an ANSI DATE literal:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

Or convert explicitly on the value side:

~~~sql
WHERE order_date >= TO_DATE(:p_date, 'YYYY-MM-DD')
  AND order_date <  TO_DATE(:p_next_date, 'YYYY-MM-DD')
~~~

### 4.3 Do not call TO_DATE on a DATE column

Data-type anti-pattern:

~~~sql
WHERE TO_DATE(order_date, 'YYYY-MM-DD') = :p_date
~~~

TO_DATE expects a character expression, not a DATE. When passed a DATE, Oracle may convert the DATE to a string via NLS_DATE_FORMAT and then parse that string back into a DATE. This is redundant, can impede index usage on ORDER_DATE, and creates NLS-dependent bugs.

Instead use:

~~~sql
WHERE order_date >= :p_start_date
  AND order_date <  :p_end_date
~~~

### 4.4 Checking conversions in the execution plan

Predicate Information may show a conversion applied to the column:

~~~text
filter(TO_NUMBER("EMPLOYEE_CODE")=100)
~~~

or:

~~~text
filter(TO_CHAR("ORDER_DATE")='2026-11-14')
~~~

If you see TO_NUMBER, TO_CHAR, CAST, or a conversion function wrapping an indexed column in Predicate Information, check the bind type and the column data type in the data dictionary.

## 5. Common functions and how to rewrite them

### 5.1 UPPER and LOWER

Query:

~~~sql
WHERE UPPER(last_name) = UPPER(:p_last_name)
~~~

A standard index on LAST_NAME is not ordered by UPPER(LAST_NAME). There are two approaches:

**Approach 1: Function-based index**

~~~sql
CREATE INDEX employees_upper_name_ix
    ON employees(UPPER(last_name));
~~~

Query:

~~~sql
WHERE UPPER(last_name) = UPPER(:p_last_name)
~~~

The optimizer can use this expression index.

**Approach 2: Normalize the data**

Store a separate normalized column, or use an appropriate collation for case-insensitive comparison. Queries can then compare the column directly under the designed semantics.

Do not remove UPPER arbitrarily if business rules require case-insensitive matching. Changing it could yield results different from existing comparison rules.

### 5.2 TRIM and LTRIM/RTRIM

Example:

~~~sql
WHERE TRIM(account_code) = :p_code
~~~

If data is stored inconsistently due to whitespace, you can:

- Normalize data on INSERT/UPDATE.
- Use a separate normalized column.
- Create a function-based index on TRIM(ACCOUNT_CODE).

~~~sql
CREATE INDEX account_code_trim_ix
    ON accounts(TRIM(account_code));
~~~

Do not change the predicate to `ACCOUNT_CODE = :p_code` if existing data has meaningful whitespace or has not been cleaned.

### 5.3 SUBSTR

Example:

~~~sql
WHERE SUBSTR(account_code, 1, 3) = 'ABC'
~~~

If the intent is finding strings starting with ABC, you can write:

~~~sql
WHERE account_code LIKE 'ABC%'
~~~

A B-tree index can support prefix LIKE when the pattern begins with fixed characters and the collation/comparison semantics are compatible. Patterns starting with a wildcard such as `'%ABC'` do not allow a regular B-tree range scan in the same way.

If you need to search by a middle substring or suffix, LIKE without a leading wildcard is not equivalent. In that case, consider a function-based index, Oracle Text, or a dedicated search structure.

### 5.4 NVL and COALESCE

Predicate:

~~~sql
WHERE NVL(status, 'NEW') = :p_status
~~~

applies NVL to the column. To preserve usage of a regular index on STATUS, you can rewrite it equivalently:

~~~sql
WHERE status = :p_status
   OR (status IS NULL AND :p_status = 'NEW')
~~~

This rewrite assumes NEW is the business-valid default value. It preserves NVL semantics: if STATUS is NULL, the compared value is treated as NEW.

Oracle may use OR expansion or combine access paths, though it is not guaranteed. Check the plan and actual row counts.

If the NVL/COALESCE expression is used frequently and consistently, a function-based index may fit:

~~~sql
CREATE INDEX orders_status_nvl_ix
    ON orders(NVL(status, 'NEW'));
~~~

### 5.5 CASE in WHERE

Example:

~~~sql
WHERE CASE
        WHEN :p_mode = 'A' THEN customer_id
        ELSE account_id
      END = :p_id
~~~

Applying CASE across two different columns makes it difficult for the optimizer to use separate indexes on CUSTOMER_ID or ACCOUNT_ID directly. If mode is a query-control parameter, split into two SQL statements or two branches:

~~~sql
WHERE (:p_mode = 'A' AND customer_id = :p_id)
   OR (:p_mode <> 'A' AND account_id = :p_id)
~~~

Depending on the workload, two separate SQL statements with matching binds may give the optimizer simpler plans and clearer selectivity. If using OR, inspect OR expansion and the resulting plan.

### 5.6 ABS, ROUND, and arithmetic on columns

Examples:

~~~sql
WHERE ABS(balance) > :p_limit
WHERE ROUND(amount, 2) = :p_amount
WHERE salary + 100 > :p_min_salary
~~~

Some arithmetic operations can be algebraically rearranged to isolate the column:

~~~sql
WHERE salary > :p_min_salary - 100
~~~

With ABS:

~~~sql
WHERE balance > :p_limit
   OR balance < -:p_limit
~~~

Rewrites must preserve semantics with NULLs, numeric types, rounding, and value domains. For `ROUND(amount, 2) = :p_amount`, a numeric range can be considered, but rounding rules and precision must be confirmed before rewriting. Never alter logic merely to make a predicate look sargable.

## 6. OR, IN, and optional predicates

OR does not automatically disable indexes. Oracle can use OR expansion, bitmap conversion, or multiple index access paths depending on conditions and cost.

### 6.1 OR on the same column

~~~sql
WHERE status = 'NEW'
   OR status = 'PENDING'
~~~

Can be written:

~~~sql
WHERE status IN ('NEW', 'PENDING')
~~~

IN is usually clearer, though it does not guarantee a different or faster plan in every case.

### 6.2 OR across different columns

~~~sql
WHERE customer_id = :p_id
   OR account_id = :p_id
~~~

If each column has an index, Oracle can consider OR expansion or bitmap operations. If one branch is very selective while the other returns many rows, the optimizer relies on statistics to choose a plan.

Do not split into UNION ALL if both branches can return the same row, because UNION ALL produces duplicates whereas OR returns each row once. If using UNION, account for sort/deduplication cost. To split branches, ensure conditions are mutually exclusive or handle duplicates intentionally.

### 6.3 Optional bind-style filters can destabilize plans

Common pattern:

~~~sql
WHERE (:p_status IS NULL OR status = :p_status)
~~~

This pattern is convenient because one SQL statement handles both filtered and unfiltered cases. However, when NULL is bound, the query may return nearly the whole table; when a rare status is bound, it returns only a few rows. A single plan may not work well for both scenarios.

Options:

- Use two separate SQL statements: filtered and unfiltered.
- Use dynamic SQL with bind variables to append only the needed predicates.
- Check adaptive cursor sharing if selectivity varies with binds.
- Measure and inspect child cursors instead of forcing indexes with hints.

Dynamic SQL must bind values, never concatenate user input directly into SQL text.

## 7. LIKE and index usability

### 7.1 Prefix search

~~~sql
WHERE last_name LIKE 'SMI%'
~~~

With a B-tree index on LAST_NAME, Oracle can use a range scan to find keys starting with SMI, depending on collation and optimizer cost.

### 7.2 Leading wildcard

~~~sql
WHERE last_name LIKE '%SMITH'
WHERE last_name LIKE '%MIT%'
~~~

A regular B-tree index cannot define a contiguous key range starting from a fixed value because the pattern permits any prefix. A full scan may be the suitable choice.

If the workload needs contains or linguistic search, consider Oracle Text or a dedicated search solution. Function-based indexes do not automatically solve arbitrary mid-string wildcard patterns.

### 7.3 Case-insensitive prefix

If querying:

~~~sql
WHERE UPPER(last_name) LIKE 'SMI%'
~~~

you can create:

~~~sql
CREATE INDEX employees_upper_last_name_ix
    ON employees(UPPER(last_name));
~~~

Then check the plan and collation. With NLS_SORT/NLS_COMP or declared collations, index expressions may depend on sorting rules; do not alter session NLS arbitrarily.

## 8. NULL and B-tree indexes

An Oracle B-tree index does not store an entry when all key columns of a row are NULL. This is an important point when querying:

~~~sql
WHERE nullable_column IS NULL
~~~

If there is only a single-column index on NULLABLE_COLUMN, the index contains no rows with NULL in that column. Therefore, this index cannot directly locate all NULL rows via a standard range scan.

With a composite index, a row can still have an entry if at least one other key column is NOT NULL. Example index:

~~~sql
CREATE INDEX orders_status_date_ix
    ON orders(status, order_date);
~~~

A row with STATUS NULL and a non-NULL ORDER_DATE still has an index entry. However, whether the index is used for `STATUS IS NULL` still depends on the leading column, remaining predicates, and cost.

If `IS NULL` queries are frequent, you can:

- Combine another non-NULL column into an appropriate composite index.
- Use a function-based index whose expression replaces NULL with a sentinel that cannot appear in valid data.
- Redesign data/nullable semantics if appropriate.

Example function-based index:

~~~sql
CREATE INDEX orders_status_nvl_ix
    ON orders(NVL(status, '#NULL#'));
~~~

The sentinel must be guaranteed never to be a valid value; queries must use the exact same expression. If data can contain the sentinel, results will be wrong.

## 9. Composite indexes and column order

Multi-column indexes are ordered according to the key expressions in the index definition. The leading column usually determines whether a condition can effectively narrow the search region.

Suppose:

~~~sql
CREATE INDEX orders_customer_date_ix
    ON orders(customer_id, order_date);
~~~

Predicate:

~~~sql
WHERE customer_id = :p_customer_id
  AND order_date >= :p_start
  AND order_date <  :p_end
~~~

can use both columns in proper order: equality on CUSTOMER_ID, then range on ORDER_DATE.

### 9.1 Filtering only the leading column

~~~sql
WHERE customer_id = :p_customer_id
~~~

The index can be used because CUSTOMER_ID is the leading column.

### 9.2 Filtering the second column without the leading column

~~~sql
WHERE order_date >= :p_start
  AND order_date < :p_end
~~~

An index on `(CUSTOMER_ID, ORDER_DATE)` is not typically used as a simple range scan on ORDER_DATE alone because ORDER_DATE values are grouped within each CUSTOMER_ID.

Oracle can consider INDEX SKIP SCAN if the distinct count of the leading column is low and cost is favorable, but do not design indexes relying on skip scan for primary workloads.

### 9.3 Equality first, range after

With index `(A, B, C)`, a favorable predicate pattern is:

~~~sql
WHERE A = :a
  AND B = :b
  AND C >= :c1
  AND C < :c2
~~~

Equality predicates on leading columns locate the key region, and then the range on the next column bounds the scan. Predicates on columns after the range can still be checked in the index/table, but typically do not narrow the scan range in the same way as leading equalities.

### 9.4 Choosing column order by workload

Do not order index columns solely by highest selectivity. Consider:

- Predicates that commonly appear together.
- Equality versus range predicates.
- ORDER BY/GROUP BY operations to support.
- Join columns.
- Distinct counts and data distribution.
- DML cost and index storage.
- Other queries sharing the same index.

An index ideal for one SQL statement may raise INSERT/UPDATE/DELETE costs and not necessarily benefit the overall workload.

## 10. Function-based indexes

A function-based index stores the result of a function or expression over one or more columns. This is appropriate when querying by an expression is a frequent business requirement and cannot or should not be rewritten.

### 10.1 UPPER example

~~~sql
CREATE INDEX customers_upper_email_ix
    ON customers(UPPER(email));
~~~

Query:

~~~sql
SELECT customer_id
FROM customers
WHERE UPPER(email) = UPPER(:p_email);
~~~

The optimizer can use the index if the expression is compatible and the cost is favorable.

### 10.2 Numeric expression example

~~~sql
CREATE INDEX products_net_price_ix
    ON products(price * (1 - discount_rate));
~~~

Query:

~~~sql
SELECT product_id
FROM products
WHERE price * (1 - discount_rate) < :p_max_net_price;
~~~

The index stores the computed expression values. This is helpful when an expression is complex and used repeatedly across many queries.

### 10.3 User-defined functions

If an expression uses a user-defined PL/SQL function, the function must be declared DETERMINISTIC. This is a developer guarantee that identical inputs always return identical outputs; Oracle does not automatically verify whether the logic is truly deterministic.

If the function reads other tables or depends on session state, SYSDATE, USER, NLS, or other mutable state, marking it DETERMINISTIC can leave stale or wrong values in the index. Only declare DETERMINISTIC when that guarantee genuinely holds.

When function semantics change, evaluate rebuilding the function-based index and dependent objects.

### 10.4 Gathering statistics after creation

After creating a function-based index, gather statistics on the index and table:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        cascade => TRUE
    );
END;
/
~~~

Statistics help the optimizer evaluate selectivity and cost of the expression index.

### 10.5 NLS and expression consistency

If an index expression performs implicit conversion to character or depends on NLS, session NLS changes can affect results. Avoid function-based indexes relying on date/number-to-string conversions without an explicit format. Use explicit format models and understand expression collation.

### 10.6 Inspecting indexed expressions

~~~sql
SELECT index_name,
       column_position,
       column_expression
FROM user_ind_expressions
WHERE table_name = 'CUSTOMERS'
ORDER BY index_name, column_position;
~~~

Compare the expression in metadata with the query's expression. Function names, arguments, data types, and conversions can affect whether the optimizer matches the index.

## 11. Virtual columns as a way to name expressions

A virtual column defines a column based on an expression. Its value is derived from other columns; you can create indexes and gather statistics on virtual columns.

Example:

~~~sql
ALTER TABLE customers ADD (
    normalized_email
        GENERATED ALWAYS AS (UPPER(email)) VIRTUAL
);

CREATE INDEX customers_normalized_email_ix
    ON customers(normalized_email);
~~~

Query:

~~~sql
SELECT customer_id
FROM customers
WHERE normalized_email = UPPER(:p_email);
~~~

Advantages:

- The expression has a clear business name.
- Column statistics can be gathered.
- Easily referenced from multiple SQL statements.
- Constraints or indexes can be placed on virtual columns per Oracle rules.

A virtual column does not automatically cause every equivalent query to use its index; predicates must reference the virtual column or the optimizer must match the corresponding expression.

## 12. Partition pruning and predicates on partition keys

If a table is partitioned by date or number, direct predicates on the partition key generally allow Oracle to skip irrelevant partitions (partition pruning).

Example table partitioned by ORDER_DATE:

~~~sql
SELECT *
FROM orders
WHERE order_date >= :p_start
  AND order_date <  :p_end;
~~~

A direct range on the partition key can enable pruning.

Conversely:

~~~sql
WHERE TRUNC(order_date) = :p_day
~~~

can make partition pruning harder when the partition key is raw ORDER_DATE. Rewriting as a half-open date range typically benefits both partition pruning and index range access.

Partition pruning is not index access. Oracle may prune partitions and then full scan within the remaining partition; this can still be a good plan.

With expression-based partition keys or virtual columns, inspect the partitioning strategy and pruning details in the plan. Do not infer behavior merely because a predicate looks equivalent.

## 13. Index access paths are not guaranteed

Even with a sargable predicate and a matching index, Oracle can still choose a FULL TABLE SCAN.

### 13.1 Low selectivity

If a query returns 60–90% of rows, using an index might read many index blocks and then visit many table blocks by ROWID. A full scan can be cheaper because it reads sequentially and leverages multiblock I/O.

### 13.2 Clustering factor

Clustering factor describes how closely index key order correlates with physical row locations in table blocks. If rows sharing a key are scattered across many blocks, an index range scan can incur many random table block reads.

### 13.3 Small tables

For very small tables, a full scan may only read a few blocks and be cheaper than traversing index root/branch/leaf blocks and returning to the table.

### 13.4 Inaccurate statistics

Outdated NUM_ROWS, NDV, histograms, or index statistics can cause the optimizer to misestimate cost. Gather appropriate statistics before using hints to force indexes.

### 13.5 INDEX FULL SCAN and INDEX FAST FULL SCAN

Oracle has multiple index access types:

| Operation | General meaning |
|---|---|
| INDEX UNIQUE SCAN | Look up a single unique key |
| INDEX RANGE SCAN | Scan a key range |
| INDEX RANGE SCAN DESCENDING | Scan a range in reverse order |
| INDEX SKIP SCAN | Leverage a composite index when some leading keys are missing under suitable conditions |
| INDEX FULL SCAN | Read the entire index in key order |
| INDEX FAST FULL SCAN | Read the entire index as a storage structure, without guaranteeing order |

Seeing INDEX in a plan does not automatically mean the query used a selective range scan.

## 14. How to read Predicate Information

Predicate Information reveals whether a condition is used as an access predicate or solely as a filter after fetching a row source.

Example:

~~~text
Predicate Information (identified by operation id):
---------------------------------------------------
  2 - access("ORDER_DATE">=:B1 AND "ORDER_DATE"<:B2)
  1 - filter("STATUS"='SHIPPED')
~~~

- ACCESS: predicate used to define keys/ranges for the access path.
- FILTER: predicate applied to filter rows after the operation retrieves them.

FILTER does not automatically mean bad. Some conditions cannot serve as index start/stop keys yet are cheap to filter afterward. What matters is checking row counts and cost at the operation.

### 14.1 Viewing the actual plan

Execute the SQL with runtime statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date
FROM orders
WHERE order_date >= :p_start
  AND order_date <  :p_end;
~~~

After fetching all results:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

Check:

- Which operation was chosen.
- Index name and access predicates.
- E-Rows versus A-Rows.
- Starts, Buffers, Reads, and A-Time.
- Peeked bind values (if any).
- Whether any conversions/functions wrap columns in Predicate Information.

### 14.2 Do not rely solely on EXPLAIN PLAN

EXPLAIN PLAN shows the plan generated in the explain environment. The actual runtime plan can differ due to bind values, child cursors, adaptive features, session settings, or statistics. When diagnosing production, prefer DISPLAY_CURSOR with the actual cursor's SQL_ID and child number.

## 15. Combined example: from index-unfriendly predicates to indexable predicates

Suppose `ORDERS` has:

~~~sql
CREATE INDEX orders_date_ix ON orders(order_date);
CREATE INDEX orders_upper_status_ix ON orders(UPPER(status));
~~~

Original query:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = TO_DATE(:p_day, 'YYYY-MM-DD')
  AND UPPER(status) = UPPER(:p_status)
  AND TO_CHAR(order_id) = :p_order_id;
~~~

Issues:

1. TRUNC wraps ORDER_DATE, not matching the raw ORDER_DATE index.
2. UPPER wraps STATUS, though a matching function-based index already exists.
3. TO_CHAR wraps ORDER_ID; if ORDER_ID is NUMBER and the bind is a string, conversion sits on the column side.

Rewritten version:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= :p_day_start
  AND order_date <  :p_next_day_start
  AND UPPER(status) = UPPER(:p_status)
  AND order_id = :p_order_id;
~~~

In this version:

- Binds `p_day_start` and `p_next_day_start` are DATE.
- Bind `p_order_id` is NUMBER.
- UPPER(STATUS) has a matching function-based index.
- ORDER_DATE and ORDER_ID are compared directly to binds of matching types.

The optimizer can select one of the indexes or combine access paths depending on selectivity and cost. There is no guarantee all three indexes will be used.

## 16. Lab exercise: observing predicates and index access

The following steps create an independent lab table. Run in a practice schema; do not use production table names.

### 16.1 Create the table

~~~sql
CREATE TABLE sargable_lab (
    id          NUMBER PRIMARY KEY,
    created_at  DATE NOT NULL,
    status      VARCHAR2(20),
    account_code VARCHAR2(30),
    amount      NUMBER
);
~~~

### 16.2 Load data

~~~sql
INSERT INTO sargable_lab
    (id, created_at, status, account_code, amount)
SELECT level,
       DATE '2026-01-01' + MOD(level, 365)
           + NUMTODSINTERVAL(MOD(level, 86400), 'SECOND'),
       CASE MOD(level, 4)
           WHEN 0 THEN 'NEW'
           WHEN 1 THEN 'PENDING'
           WHEN 2 THEN 'SHIPPED'
           ELSE 'CANCELLED'
       END,
       'AC' || TO_CHAR(MOD(level, 10000), 'FM0000'),
       MOD(level * 17, 100000) / 100
FROM dual
CONNECT BY level <= 200000;

COMMIT;
~~~

### 16.3 Create indexes and gather statistics

~~~sql
CREATE INDEX sargable_lab_date_ix
    ON sargable_lab(created_at);

CREATE INDEX sargable_lab_status_ix
    ON sargable_lab(status);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SARGABLE_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 16.4 Compare TRUNC against date range

Function-wrapped predicate:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sargable_lab
WHERE TRUNC(created_at) = DATE '2026-03-01';
~~~

View the plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE'
    )
);
~~~

Range predicate:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sargable_lab
WHERE created_at >= DATE '2026-03-01'
  AND created_at <  DATE '2026-03-02';
~~~

View the plan after the second statement. Compare access predicates, filter predicates, buffers, and operations. On the lab table, the optimizer might still choose a full scan if returned row counts or costs favor a full scan; the goal is observing predicate differences.

### 16.5 Try a function-based index

~~~sql
CREATE INDEX sargable_lab_trunc_date_ix
    ON sargable_lab(TRUNC(created_at));

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SARGABLE_LAB',
        cascade => TRUE
    );
END;
/
~~~

Re-run the `TRUNC(created_at)` query and observe whether the optimizer chooses the new index.

### 16.6 Clean up the lab

~~~sql
DROP TABLE sargable_lab PURGE;
~~~

Only run DROP TABLE if this is the lab table just created and contains no data you need to keep.

## 17. Common mistakes

| Mistake | Why it is disadvantageous | How to handle it |
|---|---|---|
| TRUNC(date_col) = date | Function wraps indexed column | Use half-open date range |
| TO_CHAR(date_col) = string | Converts DATE column to text, NLS-dependent if format omitted | Compare DATE/TIMESTAMP with properly typed binds |
| TO_DATE(date_col, format) | DATE converted to text then parsed back | Never call TO_DATE on a DATE column |
| TO_NUMBER(varchar_col) = number | Can block index usage and cause ORA-01722 | Bind string properly or normalize data |
| UPPER(col) when only col is indexed | Index does not contain UPPER(col) values | Function-based index or normalized column |
| NVL(col, value) = bind | Function wraps column | Rewrite with OR if equivalent or create function-based index |
| LIKE '%text' | Leading wildcard prevents standard B-tree range scan | Oracle Text or another search model |
| Filtering second column of composite index | Missing leading key | Design index for predicate workload |
| Looking only at EXPLAIN PLAN | Not guaranteed to match the executed plan | Use DBMS_XPLAN.DISPLAY_CURSOR |
| Forcing INDEX hint immediately | Can force a plan costlier than full scan | Fix predicates/stats then measure cost |
| Comparing mismatched bind types | Can trigger implicit conversion on column | Bind matching data types |
| Using a sentinel for NULL when sentinel can exist | Value collision and wrong results | Choose a constraint-protected sentinel |

## 18. Checklist when writing predicates

Before finalizing a SQL statement, ask yourself:

1. Does the column in WHERE have an index?
2. Does the predicate reference the column directly or wrap it in a function/expression?
3. Can it be rewritten as an equality or range on the raw column while preserving semantics?
4. For date-times, is a half-open interval used?
5. Do bind variables match the column's data type?
6. Is there any implicit or NLS-dependent conversion?
7. Does a LIKE pattern have a leading wildcard?
8. Can an OR predicate use IN or be split by branch?
9. If using a composite index, does the predicate include leading columns?
10. Is a function-based index or virtual column needed for a stable expression?
11. Does a function-based index depend on NLS or user-defined functions?
12. Are table and index statistics sufficiently fresh?
13. Is the predicate listed in the plan as ACCESS or FILTER?
14. Is there a large gap between E-Rows and A-Rows?
15. Is index access truly cheaper than a full scan at current selectivity?
16. Have buffers and elapsed time been measured with representative bind values?

## 19. Summary

To write index-friendly predicates in Oracle:

- Prefer direct comparisons between columns and literals or bind variables of the same data type.
- Avoid placing TRUNC, TO_CHAR, TO_NUMBER, UPPER, LOWER, NVL, SUBSTR, or unnecessary arithmetic on indexed columns.
- For date-times, use half-open intervals: greater than or equal to period start, and less than next period start.
- Avoid implicit conversions, especially when Oracle has to convert the column value itself.
- Use prefix LIKE when searching strings starting with a fixed value; leading wildcards do not support standard B-tree range scans.
- Design composite indexes around leading columns and real predicates.
- When querying by an expression is an enduring requirement, use a function-based index or virtual column.
- Do not assume an index is always better than a full scan. The optimizer chooses access paths by cost.
- Verify with actual execution plans, Predicate Information, E-Rows/A-Rows, Buffers, and runtime.

A good predicate both preserves business logic and gives the optimizer clear information about the target data range. Rewriting expressions is only worthwhile when results are equivalent; afterward, measure on representative data and bind values to confirm the benefit.

## 20. Oracle references

- Oracle Database 19c SQL Language Reference, “Data Type Comparison Rules”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html
- Oracle Database 19c SQL Language Reference, “CREATE INDEX”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html
- Oracle Database 19c SQL Tuning Guide, “Optimizer Access Paths”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html
- Oracle Database 19c Database Development Guide, “Using Indexes in Database Applications”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/indexes.html
- Oracle Database 19c SQL Tuning Guide, “Generating and Displaying Execution Plans”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html
