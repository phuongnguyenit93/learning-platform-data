# Impact of Collation, Type Conversion, and Functions Wrapping Columns

A column may have an index, yet a query still scans many rows because of how the `WHERE` condition is written. MySQL must compare values according to exact character sets, collations, and data types. If a predicate forces the engine to convert every column value or compute a function on the column before comparing, the B-tree order may no longer be directly usable for that search.

Predicates capable of using an index are commonly called *sargable predicates*. The goal is to write comparisons so MySQL can locate the region to read using the index's native order. When a different comparison rule or computed expression is required, you can design column collations, functional indexes, or generated columns so the index reflects how queries actually filter.

## Objectives

After this lesson, you will be able to:

- Explain how character sets and collations affect comparisons, sorting, and unique indexes.
- Recognize implicit type conversions that can prevent a column predicate from using an index.
- Distinguish direct column filters from predicates wrapping columns in functions or expressions.
- Rewrite date/time, string, and numeric queries to leverage B-tree indexes.
- Use functional indexes or generated columns when business logic genuinely requires searching by an expression.
- Verify index selection with `EXPLAIN` and confirm actual comparison semantics.

Examples assume MySQL 8.0 or later and InnoDB. Specific optimizer plans still depend on data, statistics, and server version.

## 1. Why does WHERE syntax determine index usability?

A B-tree index stores keys in a defined order. When a condition aligns with that order, MySQL can seek to a starting position and read a narrow portion of the index. Example:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    email VARCHAR(255) CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs NOT NULL,
    created_at DATETIME NOT NULL,
    KEY ix_customers_email (email),
    KEY ix_customers_created_at (created_at)
) ENGINE = InnoDB;
```

The following condition compares the column's value directly:

```sql
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';
```

If types and collations are compatible with the index, MySQL can use a point lookup (`ref` or `const`, depending on context) to find the email.

Conversely, the following condition requires computing a function for each value:

```sql
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

A regular index on `email` stores `email` values, not `LOWER(email)` results. MySQL cannot assume the order of `email` matches the order of `LOWER(email)`, so the query may have to compute the function across many rows and filter. You can resolve this by changing comparison rules, rewriting the predicate, or indexing the expression if it is a frequent requirement.

## 2. Character sets and collations

A **character set** defines how characters map to bytes. A **collation** defines how strings in that character set are compared and sorted. Two strings can have different bytes yet be considered equal under a collation.

Common collation suffixes:

| Suffix | Meaning |
|---|---|
| `_ci` | Case-insensitive: ignores uppercase vs. lowercase differences |
| `_cs` | Case-sensitive: distinguishes uppercase and lowercase |
| `_ai` | Accent-insensitive: ignores accents/diacritics |
| `_as` | Accent-sensitive: distinguishes accents/diacritics |
| `_bin` | Compares according to binary character-code values of the character set |

For example, with a case- and accent-insensitive collation like `utf8mb4_0900_ai_ci`, strings like `Lan`, `LAN`, and accented variants can be treated as equivalent under collation rules. With a case- and accent-sensitive collation like `utf8mb4_0900_as_cs`, comparisons are stricter.

### Collation determines index order

An index on a string column is built according to the column's collation at index creation time. Collation therefore affects:

- Results of `=`, `<>`, `ORDER BY`, `GROUP BY`, and many string comparisons.
- Whether a unique index permits two byte-different strings treated as equal by the collation.
- The key interval a prefix or range query can locate in the B-tree.

For instance, if `email` uses a case-insensitive collation, a unique index on `email` will reject two values differing only in case. This is a data rule, not merely a display option. Choose collation based on the business semantics of the data before creating unique indexes.

### PAD SPACE and NO PAD

Collations also carry rules for handling trailing spaces. Under `PAD SPACE` collations, trailing spaces can be ignored when comparing non-binary strings. Under `NO PAD`, trailing spaces are significant in comparisons. For example, `utf8mb4_0900_ai_ci` belongs to `NO PAD`; many older collations use `PAD SPACE` rules.

This difference can change comparison outcomes and `UNIQUE` constraints. When upgrading collations or migrating from legacy collations to UCA 9.0 collations, check whether existing data contains values differing solely by trailing spaces or letter case.

### Literals and columns with different collations

When comparing a column against a literal, MySQL applies coercibility rules to determine the collation used for comparison. Typically, a column's explicit collation has higher precedence than a literal's collation, so:

```sql
SELECT customer_id
FROM customers
WHERE email = 'Lan@example.com';
```

follows `email`'s collation. The connection collation (`collation_connection`) influences how literals are constructed, yet you should not assume it overrides a column's collation.

If two columns have incompatible character sets/collations, MySQL may have to convert one side or raise an `Illegal mix of collations` error. Especially when joining two tables, design join-key columns with matching character sets and collations so comparisons are unambiguous and indexes can be used effectively.

Check column configuration and collation:

```sql
SHOW FULL COLUMNS FROM customers;
SHOW CREATE TABLE customers;

SELECT CHARSET(email),
       COLLATION(email),
       COERCIBILITY(email)
FROM customers
LIMIT 1;

SHOW VARIABLES LIKE 'collation%';
```

### Using COLLATE deliberately

You can specify a collation on an expression:

```sql
SELECT customer_id
FROM customers
WHERE email COLLATE utf8mb4_0900_as_cs =
      'Lan@example.com' COLLATE utf8mb4_0900_as_cs;
```

This alters comparison rules for the query. However, if the index on `email` is sorted by a different collation, applying `COLLATE` to the column can prevent that index from serving point or range lookups under the new order. MySQL may still choose another access path or scan the index, yet you should not assume an efficient index lookup will occur.

If an alternate collation rule is needed frequently, consider declaring that collation directly on the column with a matching index, or creating a generated column/functional index with the appropriate expression and collation. Always verify with `EXPLAIN`.

Note: a `_bin` collation is a string comparison rule; it is not the same as changing the column type to `BINARY` or `VARBINARY`, which store and compare data as raw bytes.

## 3. Implicit type conversion can disable index lookups

When two sides of a comparison have different types, MySQL may convert one or both sides according to type conversion rules. If conversion is performed on an indexed column, the original B-tree order may no longer help locate values.

### Comparing a string column with a number

Suppose a table stores product codes as strings because codes can contain leading zeros or letters:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    product_code VARCHAR(30) NOT NULL,
    KEY ix_products_code (product_code)
) ENGINE = InnoDB;
```

The following query compares a `VARCHAR` against a number:

```sql
SELECT product_id
FROM products
WHERE product_code = 123;
```

When comparing a string with a number, MySQL may convert string values to numeric form for comparison. Strings like `'123'`, `'0123'`, `' 123'`, or `'123x'` exhibit numeric conversion behavior differing from pure string comparison. Because multiple distinct strings can convert to the same numeric value, MySQL cannot always use the string index as a single equality lookup.

If `product_code` is a string identifier, pass a string parameter:

```sql
SELECT product_id
FROM products
WHERE product_code = '123';
```

This preserves the identifier's semantics and lets the index on `product_code` be used directly. Do not turn string identifiers into numbers merely because most current values look numeric.

### Numeric columns compared with strings

For numeric columns, passing parameters with the matching numeric type remains clearest:

```sql
SELECT product_id
FROM products
WHERE product_id = 123;
```

MySQL can typically convert a string literal like `'123'` to the column's numeric type and still use the index on a numeric column, yet specific behavior should be verified with `EXPLAIN`. Do not rely on implicit conversion for invalid or non-standard data formats.

### Date/time columns and literals

Comparing a `DATETIME` column against a valid date/time literal generally allows MySQL to convert the literal to date/time type and use the index:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00';
```

From application code, bind parameters with an appropriate date/time type and explicit format. Avoid passing malformed date strings or relying on format parsing quirks under `sql_mode`.

With `TIMESTAMP`, account for the session time zone because MySQL converts between the session time zone and UTC on store/read. Construct time boundaries using the same time zone convention as the queried data.

### Explicit type casting

Using `CAST()` or `CONVERT()` on the parameter is usually easier to optimize than wrapping the column:

```sql
-- Can prevent index lookup on product_code:
SELECT product_id
FROM products
WHERE CAST(product_code AS UNSIGNED) = 123;

-- Preserves string comparison if product_code is a string identifier:
SELECT product_id
FROM products
WHERE product_code = CAST(123 AS CHAR);
```

Choose syntax matching data semantics. If a product code is a string, do not coerce the column to a number for searching. If the column is genuinely numeric, store it as a numeric type and pass numeric parameters.

## 4. Functions wrapping columns hinder B-tree usage

A regular index stores column values in sorted order. Writing a function around a column forces MySQL to evaluate that expression before knowing whether a value satisfies the condition. Common patterns:

```sql
WHERE LOWER(email) = 'lan@example.com'
WHERE DATE(created_at) = '2026-11-19'
WHERE YEAR(created_at) = 2026
WHERE CAST(customer_id AS CHAR) = '100'
WHERE COALESCE(status, '') = 'ACTIVE'
WHERE amount + 10 > 100
```

These conditions typically cannot use a regular column index for a direct range lookup. Many cases can be rewritten so computation moves to the constant side or turns into a range on the column.

### DATE() and YEAR() on date/time columns

Suppose there is an index:

```sql
CREATE INDEX ix_orders_created_at ON orders (created_at);
```

The condition:

```sql
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-11-19';
```

evaluates `DATE()` on every `created_at` value. Rewrite it as a half-open interval:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

The interval `[start of day, start of next day)` captures every instant on that date without guessing fractional microsecond end-of-day precision, and can use a range scan on the `created_at` index.

Similarly, replace `YEAR(created_at) = 2026` with a time interval:

```sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2027-01-01 00:00:00'
```

If the column is `TIMESTAMP`, compute both boundary timestamps in the business time zone and bind session-aligned values; do not blindly add 24 hours in UTC when local dates include daylight saving transitions.

### LOWER() and UPPER() on strings

If the `email` column uses a case-insensitive collation aligned with business rules, compare directly:

```sql
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';
```

There is no need for `LOWER(email)` solely for case-insensitive comparison if the column's collation already provides those exact semantics. If business logic requires custom string normalization, store a normalized column or create a functional index.

### COALESCE(), IFNULL(), and arithmetic expressions

The condition:

```sql
WHERE COALESCE(status, '') = 'ACTIVE'
```

can be rewritten as:

```sql
WHERE status = 'ACTIVE'
```

Both predicates are equivalent when `NULL` is not treated as `'ACTIVE'`. If you need to match both `NULL` and `'ACTIVE'`, write it explicitly:

```sql
WHERE status = 'ACTIVE'
   OR status IS NULL
```

For arithmetic expressions, replace `amount + 10 > 100` with `amount > 90` when data types and rounding rules make the transformation equivalent. Avoid algebraic rewrites that change semantics for `NULL`, floating-point values, overflow, or division.

## 5. LIKE, prefixes, and collation

With a B-tree index on strings, prefix searches can leverage the index:

```sql
SELECT customer_id
FROM customers
WHERE email LIKE 'lan%';
```

MySQL can convert the fixed prefix into an index range obeying the column's collation. Collation determines case and accent sensitivity inside `LIKE`.

A condition with a leading wildcard:

```sql
WHERE email LIKE '%@example.com'
```

typically cannot use a B-tree index to locate a starting point because there is no fixed prefix. If suffix searching is a frequent requirement, consider storing a reversed string column or using an appropriate search solution, while defining clear semantics and accounting for write cost.

Do not replace `LIKE` with `LOWER(column) LIKE ...` by default. First select an appropriate collation; if you must search by a normalized expression, consider indexing that expression itself.

## 6. Functional indexes and generated columns

If querying by an expression is a recurring requirement and cannot be rewritten into a base-column predicate, you can index the expression.

### Functional index

MySQL supports functional key parts starting in version 8.0.13:

```sql
CREATE INDEX ix_customers_lower_email
ON customers ((LOWER(email)));
```

Queries must use the matching expression:

```sql
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

The query expression must match the functional index expression for the optimizer to recognize and use it. Result type, collation, and expression phrasing all matter. Check `EXPLAIN`; never assume all mathematically equivalent variants map to the same index.

Functional indexes consume storage and raise `INSERT`, `UPDATE`, and `DELETE` costs because index values must be computed and maintained. Expressions must also obey functional key-part restrictions, such as disallowing nondeterministic functions or references outside the row.

### Indexed generated column

You can materialize an expression as a generated column for clearer naming and explicit typing:

```sql
ALTER TABLE customers
ADD COLUMN email_normalized VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    GENERATED ALWAYS AS (LOWER(email)) STORED,
ADD INDEX ix_customers_email_normalized (email_normalized);
```

Query using the generated column:

```sql
SELECT customer_id
FROM customers
WHERE email_normalized = 'lan@example.com';
```

A generated column can be `VIRTUAL` or `STORED`. `VIRTUAL` computes values on read, while `STORED` stores values in the row; when a generated column is indexed, InnoDB still maintains index entries for the expression. Choose the mode based on workload and expression restrictions.

Creating a generated column is unnecessary if the base column's collation already meets requirements. Before adding one, check whether the new index introduces different data rules than an existing index, especially when using `UNIQUE`.

## 7. Verifying with EXPLAIN

You cannot determine whether an index is used just by looking at SQL text. Compare plans across predicate styles:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE email = 'lan@example.com';

EXPLAIN
SELECT customer_id
FROM customers
WHERE LOWER(email) = 'lan@example.com';
```

Columns to inspect:

| Column | Meaning |
|---|---|
| `type` | Access type, e.g., `const`, `ref`, `range`, `index`, `ALL` |
| `possible_keys` | Indexes the optimizer can consider |
| `key` | Index actually selected |
| `key_len` | Length of the index portion used |
| `rows` | Estimated rows to read |
| `filtered` | Estimated percentage of rows remaining after filter conditions |
| `Extra` | Additional info such as `Using where`, `Using index` |

`type = ALL` is typically a full table scan; `type = index` can be a full index scan, which does not automatically mean an efficient lookup. Conversely, the optimizer may deliberately choose a scan when a table is small or a condition returns a large fraction of rows. The goal is not forcing every query to use an index, but minimizing total execution cost.

If you just created a functional index or generated column, re-run `EXPLAIN` with a query matching the exact expression. When data changes significantly, refresh statistics with `ANALYZE TABLE` if needed and re-evaluate the plan.

## 8. Quick diagnostic table

| Symptom | Possible cause | Resolution |
|---|---|---|
| String index unused when comparing against a number | MySQL must convert string column values to numbers | Pass string literals/parameters or fix column type if truly numeric |
| `LOWER(column)` causes query to scan many rows | Regular index stores raw values, not function results | Use suitable collation, functional index, or generated column |
| `DATE(datetime_column)` skips desired range index | Function applied to every column value | Write half-open interval condition on the raw column |
| Comparing two columns raises collation error | Incompatible character sets/collations | Align schema or convert deliberately; check index usage afterward |
| Unique index rejects visually distinct strings | Collation treats values as equal or `PAD SPACE` applies | Check collation, accents, and trailing spaces before modifying data |
| `LIKE '%text'` scans many rows | Leading wildcard cannot form a prefix range | Design another search approach or use an appropriate search index |
| Functional index exists yet optimizer ignores it | Different expression, type/collation mismatch, or scan is cheaper | Compare expressions, inspect `EXPLAIN`, and check statistics |

## 9. Query rewriting workflow

When a query fails to use an index as expected, follow this sequence:

1. Identify column data type, character set, collation, and indexes via `SHOW CREATE TABLE`.
2. Check the data type of literals or parameters bound by the application.
3. Locate functions, arithmetic, `CAST`, `CONVERT`, or `COLLATE` applied to the column.
4. Confirm intended collation and conversion rules per business semantics; never change semantics solely to force index usage.
5. Rewrite predicates into direct comparisons or column ranges when equivalent.
6. If the expression is a fixed requirement, consider a functional index or generated column.
7. Run `EXPLAIN`, compare `key`, `type`, `rows`, and verify returned results remain identical.

## 10. Practice exercises

Given tables `customers(customer_id, email, created_at)` and `products(product_id, product_code)`, assume indexes exist on `email`, `created_at`, and `product_code`.

1. Compare `email = 'Lan@example.com'` results when the column uses `_ai_ci` vs. `_as_cs` collations. Explain the impact on unique indexes.
2. Run `EXPLAIN` for `product_code = 123` and `product_code = '123'`. Observe differences in index lookup and explain why string identifiers should be compared as strings.
3. Run `EXPLAIN` for `DATE(created_at) = '2026-11-19'`, then rewrite it as an interval from start of day to start of next day. Compare plans.
4. Create a functional index on `LOWER(email)`, then test the query `LOWER(email) = 'lan@example.com'`.
5. Test `LIKE 'lan%'` and `LIKE '%lan'`. Explain the effect of wildcard placement.
6. Check `CHARSET()`, `COLLATION()`, and `COERCIBILITY()` of a string column and a literal. Explain how to handle joins between two columns with different collations.

## Key takeaways

- String indexes are ordered by the column's collation; collation affects comparison results and uniqueness.
- Implicit type conversion on an indexed column can prevent MySQL from using desired point or range lookups.
- Functions or expressions wrapping a column typically make predicates non-sargable for regular indexes.
- Prefer direct column comparisons with parameters of matching type and semantics.
- Express date/time filters as half-open intervals; use functional indexes or generated columns when searching by an expression is unavoidable.
- Always verify with `EXPLAIN` and check query results to ensure optimizations do not alter business semantics.
