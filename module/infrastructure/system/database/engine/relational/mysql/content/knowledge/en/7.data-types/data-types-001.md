# Choosing Data Types Based on Value Domain, Precision, and Storage Cost

Choosing data types is a critical design decision for a MySQL table. A data type must represent every valid business value, preserve the required precision, and carry an appropriate storage cost. If you choose a type that is too small, data may overflow or be rejected on write. If you choose an inappropriate type, such as using floating-point numbers for money or numbers to store identifiers, results may be inaccurate or difficult to handle. If you choose overly wide types for every column, indexes and data can consume more memory, disk, and I/O than necessary.

This lesson belongs to the `DATABASE_MYSQL` module, where you practice table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, and relational database operations. The goal is to design data types based on actual value domains, precision, comparison behavior, and storage cost rather than choosing types out of habit.

After this lesson, you will be able to:

- Identify value domains and validation rules before choosing a data type.
- Choose integer, decimal, and floating-point types based on range and precision.
- Distinguish between `CHAR`, `VARCHAR`, `TEXT`, `BINARY`, `VARBINARY`, and special string types.
- Choose date and time types according to temporal semantics and time zone handling.
- Decide when to use `JSON`, `ENUM`, `SET`, or a lookup table.
- Understand the impact of column size, charset, collation, and indexes on resources.
- Validate data, check SQL modes, and perform safe type conversions when schemas change.

## 1. Data Type Selection Process

Before writing `CREATE TABLE`, answer the following questions for each column:

1. **What does the column represent?** An addable/subtractable quantity, a monetary amount, an identifier, text, a point in time, or binary data?
2. **What is the valid value domain?** Minimum and maximum values, whether negative values or fractional numbers are allowed, and maximum length?
3. **What precision is required?** Does every decimal digit need to be represented accurately, or is an approximate error acceptable?
4. **Does the value have formatting rules?** Are there leading zeros, hyphens, case sensitivity, Unicode characters, or fixed-length codes?
5. **What is the temporal meaning?** A calendar date, a duration, a local wall-clock time, or an absolute point on the timeline?
6. **How is the column queried and indexed?** Is the column part of a primary key, foreign key, filter condition, join, sort, or group?
7. **Can the value be absent?** Does `NULL` carry a distinct meaning, or is the column required to have a value?

A practical workflow is to document the value domain first, pick a type that satisfies that domain, and then check storage size and test boundary values. Do not start with "which type is the smallest?"; start with "which type accurately represents this data?".

| Criterion | Question to Determine | Example |
| --- | --- | --- |
| Value domain | Min/max values, signed/unsigned, number of digits | Inventory quantity from 0 to several million |
| Precision | Exact precision required or approximate? | Money requires exactness to 2 decimal places |
| Semantics | Arithmetic calculations or just a code? | A phone number is a string, not a number to add |
| Length | Fixed length or variable length? | Country code is fixed, person name is variable |
| Comparison | Case-sensitive, accent-sensitive, or byte-by-byte? | Email has normalization rules and a clear collation |
| Lifecycle | Need time zones or store absolute instants? | Payment timestamp requires a UTC convention |
| Querying | Used as a key or index? | `customer_id` is used in joins and foreign keys |

## 2. Integer Types

Integer types are suitable for counts, numeric IDs, numeric status codes, and values that do not require a fractional part. MySQL provides `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, and `BIGINT`.

### 2.1. Value Domains and Sizes

| Type | Storage | `SIGNED` Range | `UNSIGNED` Range |
| --- | ---: | --- | --- |
| `TINYINT` | 1 byte | -128 to 127 | 0 to 255 |
| `SMALLINT` | 2 bytes | -32,768 to 32,767 | 0 to 65,535 |
| `MEDIUMINT` | 3 bytes | -8,388,608 to 8,388,607 | 0 to 16,777,215 |
| `INT` | 4 bytes | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |
| `BIGINT` | 8 bytes | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 0 to 18,446,744,073,709,551,615 |

`SIGNED` is the default. `UNSIGNED` omits the negative range to expand the positive range. Only choose `UNSIGNED` when the business domain truly has no negative values and referencing columns have a compatible type. The data type and signedness of a foreign key column must match between the parent and child tables.

Example:

```sql
CREATE TABLE inventory_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    reorder_level SMALLINT UNSIGNED NOT NULL DEFAULT 10,
    is_active TINYINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

Here, `item_id` may grow over time, so it uses `BIGINT UNSIGNED`; `quantity` has a non-negative domain; `reorder_level` has a smaller range; `is_active` only needs a small domain. In real-world applications, if a status has multiple values or state transition rules, consider a lookup table or a `CHECK` constraint rather than relying on a meaningless number.

### 2.2. Choosing a Right-Sized Type

Do not use `BIGINT` for every column just because it has a large range. The difference per row may seem small, but with hundreds of millions of rows and multiple indexes, wider types increase data size, index size, buffer pool usage, and I/O.

Conversely, do not choose `TINYINT` for a counter that might exceed 255 just because the current dataset is small. Forecast growth rate and data lifespan. For auto-incrementing IDs, estimate the maximum number of records over the table's lifetime, including deleted records, because `AUTO_INCREMENT` can leave gaps.

### 2.3. Notes on Integer Attributes

- `AUTO_INCREMENT` is typically used for an indexed integer column. Incrementing values are not guaranteed to be contiguous and should not be used as business sequence numbers where gaps are disallowed.
- A display width such as `INT(11)` does not allow `INT` to store more digits. Display width for integers was deprecated in MySQL 8.0.17; do not use it to control value domains.
- `BOOL` and `BOOLEAN` are aliases for `TINYINT(1)`, not an independent boolean type. MySQL can still store values other than 0 and 1 without a constraint.
- `ZEROFILL` has been deprecated and automatically makes the column `UNSIGNED`; do not use it for formatting data. Format values during display in the application layer.
- If you need sequence numbers with leading zeros such as `000123`, consider storing the code as a string or keeping the numeric value and formatting on display, depending on whether the leading zeros are intrinsic to the identifier.

## 3. Exact Decimal and Approximate Floating-Point Numbers

MySQL has `DECIMAL`/`NUMERIC`, `FLOAT`, and `DOUBLE` types. Choosing the right numeric group is crucial for money, rates, measurements, and scientific calculations.

### 3.1. DECIMAL for Values Requiring Exactness

`DECIMAL(p, s)` stores decimal numbers with fixed precision. `p` is the maximum total number of digits (precision), and `s` is the number of digits in the fractional part (scale). In MySQL, the maximum precision is 65 and the maximum scale is 30, and scale cannot exceed precision.

Example:

```sql
CREATE TABLE product_prices (
    product_id BIGINT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

`DECIMAL(12,2)` represents up to 10 integer digits and 2 fractional digits. `DECIMAL(5,4)` suits a rate with 4 digits after the decimal point, with a maximum positive value below 10. Choose `p` and `s` based on the business contract rather than copying examples mechanically.

`DECIMAL` is stored in a packed decimal format; storage size depends on the number of digits before and after the decimal point, grouped in chunks of 9 digits. Therefore, it does not always occupy the same number of bytes as an integer. In return, decimal arithmetic avoids the binary rounding errors common in floating-point types.

For currency, product prices, balances, and taxes, `DECIMAL` is usually the right choice. However, you still need to define rounding rules, the order of tax/discount calculation, and the scale of results. A data type alone does not decide business rounding policies.

### 3.2. FLOAT and DOUBLE for Approximate Numbers

`FLOAT` typically uses 4 bytes and `DOUBLE` typically uses 8 bytes. They store floating-point numbers in binary representation, so many decimal values cannot be represented with absolute exactness.

```sql
SELECT
    0.1 + 0.2 AS approximate_sum,
    CAST(0.1 AS DECIMAL(10, 2)) + CAST(0.2 AS DECIMAL(10, 2)) AS decimal_sum;
```

The floating-point result may be close to `0.3` but is not guaranteed to be exact. This is an inherent property of floating-point arithmetic, not a bug specific to MySQL.

Use `FLOAT` or `DOUBLE` when approximate error is acceptable, such as sensor readings, scientific calculations, coordinates, or statistical models. Do not use them to store money that requires exact reconciliation. When comparing floating-point numbers, an epsilon threshold is usually needed instead of an exact `=` check.

| Need | Typically Suitable Type | Reason |
| --- | --- | --- |
| Prices, balances, taxes | `DECIMAL(p,s)` | Exact decimal digits according to scale |
| Integer quantities | `INT` or appropriate integer type | No fractional part |
| Sensor temperature, measurements | `FLOAT` or `DOUBLE` | Approximate error is acceptable |
| Financial rates requiring reconciliation | `DECIMAL(p,s)` | Exact control over number of digits |
| Scientific simulations, statistics | Usually `DOUBLE` | Larger range and precision than FLOAT |

## 4. String Types and Binary Data

Before choosing a string type, determine whether the data is text governed by language rules or a sequence of bytes that must be preserved verbatim. These two categories have different comparison rules, charsets, and collations.

### 4.1. CHAR and VARCHAR

`CHAR(M)` represents a string with a fixed declared length, whereas `VARCHAR(M)` represents a variable-length string. `M` is measured in characters, while the number of bytes required for storage depends on the charset. `CHAR` has a maximum declared length of 255 characters; the effective length of `VARCHAR` also depends on the row byte limit and other columns.

| Type | Characteristics | Suitable Use Cases |
| --- | --- | --- |
| `CHAR(M)` | Fixed length, space-padding semantics | Fixed-length codes, 2-character country codes |
| `VARCHAR(M)` | Variable length, stores actual length alongside data | Names, emails, addresses, variable-length codes |
| `TINYTEXT` | Text up to 255 bytes | Small text snippets where VARCHAR limits are less needed |
| `TEXT` | Text up to 65,535 bytes | Long text content |
| `MEDIUMTEXT` | Text up to 16,777,215 bytes | Longer content such as articles |
| `LONGTEXT` | Theoretical maximum limit of 4,294,967,295 bytes | Very large content; practical limits depend on packets, memory, and environment |

`VARCHAR` is usually suitable for most text attributes with clear business length limits. Do not choose `TEXT` just to avoid thinking about length. `TEXT` types can affect indexing, querying, and storage; indexes on `TEXT` typically require a prefix length or an alternative strategy.

`VARCHAR` storage consists of the character data plus 1 or 2 length bytes, depending on the maximum byte length. With a multibyte charset like `utf8mb4`, a single character can require up to 4 bytes. Thus, `VARCHAR(100)` does not always take 100 bytes, and a table's practical limit is also subject to MySQL's row size limit.

### 4.2. BINARY and VARBINARY

`BINARY(M)` and `VARBINARY(M)` store raw bytes without applying text charsets or collations. Use them for binary data or tokens with byte-wise comparison rules.

```sql
CREATE TABLE api_tokens (
    token_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    token_hash BINARY(32) NOT NULL,
    token_label VARCHAR(100) NOT NULL,
    PRIMARY KEY (token_id),
    UNIQUE KEY uk_api_token_hash (token_hash)
) ENGINE = InnoDB;
```

This example stores a SHA-256 hash as 32 bytes. If stored as a 64-character hex string, the column requires at least 64 ASCII characters; the binary representation is more compact if the application can convert consistently.

### 4.3. BLOB

`BLOB`, `MEDIUMBLOB`, and `LONGBLOB` store binary data with size limits corresponding to the `TEXT` group. Use BLOB when the data is truly raw bytes, such as binary payloads or small objects that must be stored inside the database.

For large files, consider storing objects in object storage and saving metadata, checksums, MIME types, sizes, and paths in MySQL. This decision depends on transaction requirements, backups, access control, read load, and recovery procedures.

## 5. How Charset and Collation Affect Strings

A charset determines how characters are encoded into bytes. A collation determines how strings are compared and sorted, including case-sensitivity and accent-sensitivity rules.

For modern applications requiring Vietnamese and multiple languages, `utf8mb4` is usually the right choice:

```sql
CREATE TABLE people (
    person_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (person_id),
    UNIQUE KEY uk_people_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` is a common collation in MySQL 8.0+; `ai` indicates accent-insensitive and `ci` indicates case-insensitive. This means comparisons and unique indexes may treat strings that differ only by accents or case as equivalent under collation rules. That can be useful for search, but requires careful consideration when applied to identifiers or data requiring exact distinction.

Not every text column should use the same collation. For example, token codes or technical codes may require binary/case-sensitive comparisons. Choose charset/collation based on each column's semantics and ensure that columns used in comparisons, joins, and foreign keys have compatible attributes.

## 6. Date and Time Types

MySQL provides `DATE`, `TIME`, `DATETIME`, `TIMESTAMP`, and `YEAR`. Choose based on the meaning of the data, not merely on how the string is displayed.

| Type | Meaning | Base Storage | Range / Notes |
| --- | --- | ---: | --- |
| `DATE` | Calendar date | 3 bytes | `1000-01-01` to `9999-12-31` |
| `TIME` | Time of day or duration | 3 bytes | Range from `-838:59:59` to `838:59:59` |
| `DATETIME` | Calendar date and time | 5 bytes | `1000-01-01 00:00:00` to `9999-12-31 23:59:59` |
| `TIMESTAMP` | Point in time converted per session time zone | 4 bytes | `1970-01-01 00:00:01` UTC to `2038-01-19 03:14:07` UTC |
| `YEAR` | Year | 1 byte | Typically 1901 to 2155, plus the value `0000` |

`TIME`, `DATETIME`, and `TIMESTAMP` can store fractional seconds with a precision from 0 to 6 digits, such as `DATETIME(3)` or `TIMESTAMP(6)`. Fractional seconds add up to 3 extra bytes of storage.

### 6.1. DATE, DATETIME, and TIMESTAMP

- Use `DATE` for birth dates, release dates, or business dates without a time component.
- Use `DATETIME` for calendar timestamps that must be stored verbatim according to application conventions, such as a scheduled appointment at a location. MySQL does not automatically convert `DATETIME` values based on the session time zone.
- Use `TIMESTAMP` for absolute points in time that need conversion according to the session `time_zone`. MySQL converts values from the session time zone to UTC when storing and from UTC to the session time zone when reading.

Example:

```sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
```

`starts_at` preserves the scheduled calendar date and time according to application conventions. `created_at` records when the row was created; with `TIMESTAMP`, the displayed result depends on the session time zone. Standardize storage and time zone conversion conventions at the application layer.

Check the current time zone:

```sql
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();
```

`NOW()` returns the time in the session time zone; `UTC_TIMESTAMP()` returns UTC time. Do not assume the server, application, and end users are using the same time zone.

### 6.2. TIME Is Not Just Time of Day

`TIME` represents a time or duration and can hold negative values or values exceeding 24 hours. If the business requires a specific time of day paired with a calendar date, use `DATETIME` or `TIMESTAMP` depending on temporal semantics. If long durations are needed, consider storing seconds or smaller units using an integer type when calculations and business bounds are clear.

### 6.3. Avoid Storing Dates and Times as Strings

Storing dates and times as `VARCHAR` makes sorting, range filtering, validation, and temporal arithmetic much harder. Using temporal types allows MySQL to apply comparisons and time functions with the proper semantics.

## 7. JSON, ENUM, and SET

### 7.1. JSON

The `JSON` type validates that input is valid JSON and stores it in an internal binary format that enables element access. JSON works well for flexible attributes or payloads with evolving structures, but it should not replace all relational columns.

```sql
CREATE TABLE product_metadata (
    product_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

INSERT INTO product_metadata (product_id, attributes)
VALUES (1, '{"color":"black","weight_gram":850,"wireless":true}');

SELECT
    product_id,
    attributes->>'$.color' AS color,
    attributes->>'$.weight_gram' AS weight_gram
FROM product_metadata;
```

Attributes that are frequently filtered, joined, sorted, or subject to constraints should be considered for extraction into dedicated strongly typed columns. JSON values can be indexed using generated columns or appropriate functional indexes, provided the extracted type and missing/null value handling are clearly defined.

### 7.2. ENUM

`ENUM` represents a single value chosen from a pre-declared list of options:

```sql
CREATE TABLE support_tickets (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status ENUM('new', 'in_progress', 'resolved', 'closed') NOT NULL DEFAULT 'new',
    PRIMARY KEY (ticket_id)
) ENGINE = InnoDB;
```

`ENUM` uses an internal index to represent values, typically taking 1 byte if the list has up to 255 elements and 2 bytes if more (up to 65,535 elements). Comparison and sorting order depends on declaration order, not alphabetical order. When modifying the list, consider migrations and application compatibility.

`ENUM` can be useful for a small, stable set of values. If a status has metadata, transition rules, translations, or frequent changes, a lookup table is usually more flexible.

### 7.3. SET

`SET` represents a subset of a pre-declared list of elements. It fits certain rarely changing scenarios, but its storage and manipulation can cause friction when an application needs many-to-many relationships or individual option queries. For extensible option sets or flexible filtering/joining, consider a junction table instead of `SET`.

`SET` supports up to 64 elements; storage size ranges from 1 to 8 bytes depending on the number of declared elements. Like `ENUM`, ordering and representation are tied to the declared list, so evaluate carefully if the list might change.

## 8. NULL, DEFAULT, and Data Constraints

`NULL` indicates an unknown, not applicable, or absent value according to the column's semantics. It is not the same as zero, an empty string, or a default date. Use `NOT NULL` when the business requires a value to always exist; use `NULL` when the absent state has meaning.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(100) NULL,
    salary DECIMAL(12, 2) NOT NULL,
    terminated_at DATETIME NULL,
    PRIMARY KEY (employee_id),
    CONSTRAINT chk_employee_salary CHECK (salary >= 0)
) ENGINE = InnoDB;
```

`middle_name` may not exist; `terminated_at` is `NULL` while the employee is still active. `salary` is required and non-negative. `CHECK` constraints are enforced in MySQL 8.0.16 and later, though you should still check the server version if deploying to older environments.

Important rules:

- Compare `NULL` using `IS NULL` or `IS NOT NULL`, never `= NULL`.
- Operations involving `NULL` usually yield `NULL`; use `COALESCE` when there is a clear fallback rule.
- `COUNT(column)` ignores `NULL` values; `COUNT(*)` counts rows.
- `DEFAULT` supplies a value when an `INSERT` statement omits the column under MySQL rules. It does not replace deciding whether the column is required.
- Avoid using sentinel values like `0`, `''`, or `'1900-01-01'` to mean "no data" if those values could be valid in the business domain.

## 9. Storage Cost and Impact on Indexes

Data types affect row size, index size, buffer pool usage, the number of data pages read, and network transfer cost. A wide key column repeated across multiple secondary indexes can increase total index size substantially.

### 9.1. Column Size Is More Than Just Row Size

Some baseline sizes:

| Group | Examples | Size / Characteristics |
| --- | --- | --- |
| Integers | `INT`, `BIGINT` | 4 bytes and 8 bytes |
| Floating-point | `FLOAT`, `DOUBLE` | Typically 4 bytes and 8 bytes |
| Exact numeric | `DECIMAL(p,s)` | Packed decimal, depends on number of digits |
| Temporal | `DATE`, `DATETIME`, `TIMESTAMP` | 3, 5, and 4 bytes respectively before fractional seconds |
| Strings | `CHAR`, `VARCHAR` | Depends on character count, charset, and length overhead |
| Large text/binary | `TEXT`, `BLOB` | May be stored off-row depending on size and row format |

These are baseline figures, not the exact formula for total row size. MySQL also requires metadata, NULL bitmaps, variable-length headers, indexes, and storage engine structures. `VARCHAR` uses 1 or 2 length bytes; multibyte strings can occupy more bytes than their character count.

### 9.2. Primary Keys and Secondary Indexes

In InnoDB, the primary key is the clustered index. Secondary indexes store the primary key value to locate rows. Consequently, a long primary key makes every secondary index larger. Choosing a compact, stable, business-appropriate primary key helps keep index size under control.

For example, a `BIGINT` primary key takes 8 bytes whereas an `INT` takes 4 bytes. If the value domain is guaranteed not to exceed the `INT` limit, using `INT` can reduce key size. However, if the table needs more than 2.1 billion positive signed IDs or is planned to grow past that limit, choosing `BIGINT` from the start can avoid a costly migration later.

### 9.3. Row Size Limit

MySQL enforces a maximum row size limit of 65,535 bytes at the SQL layer, excluding off-row `BLOB`/`TEXT` data. With multibyte charsets, declaring many very wide `VARCHAR` columns can exceed this limit even when actual data is typically short. Design against maximum byte sizes and test DDL when adding multiple columns.

## 10. Type Conversion and Input Validation

MySQL can perform implicit type conversions in expressions or during writes. Implicit conversion can cause data loss, produce unexpected comparison results, or prevent the optimizer from using an index effectively.

For instance, if `customer_id` is an `INT` but the application passes an arbitrary string in a comparison predicate, MySQL may convert values according to type conversion rules. Use properly typed parameters and do not rely on implicit casting to sanitize data.

Check the SQL mode:

```sql
SELECT @@sql_mode;
```

Strict mode helps MySQL reject or raise errors for many out-of-range values instead of silently adjusting or truncating them where conversion is permitted. Exact behavior still depends on the data type, statement, and SQL mode. Applications should validate input upfront and handle write errors explicitly.

When changing a column's type:

1. Profile min/max values, maximum lengths, `NULL` values, and invalid values.
2. Inspect application code, APIs, reports, imports/exports, and referencing tables.
3. Determine whether the conversion causes data loss, rounding, string truncation, or collation changes.
4. Back up and test the migration on a copy of the data.
5. Evaluate table/index rebuild duration, locking, and temporary disk space.
6. After migration, verify row counts, boundary values, constraints, indexes, and critical queries.

## 11. Domain-Driven Table Design Example

Suppose an e-commerce system needs to store customers, orders, and order line items. An initial design might look like this:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_code VARCHAR(32) NOT NULL,
    status ENUM('pending', 'paid', 'cancelled', 'refunded') NOT NULL DEFAULT 'pending',
    total_amount DECIMAL(14, 2) NOT NULL,
    placed_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    UNIQUE KEY uk_orders_code (order_code),
    KEY idx_orders_customer_placed (customer_id, placed_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT chk_orders_total CHECK (total_amount >= 0)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_items_product (product_code),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT chk_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_order_items_price CHECK (unit_price >= 0)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;
```

Explanation of decisions:

- IDs use `BIGINT UNSIGNED` because they can grow long-term and cannot be negative. Foreign key columns use the exact same type and signedness.
- `email`, `full_name`, `phone_number`, `order_code`, and `product_code` are strings because they are identifying or display data, not arithmetic quantities. Phone numbers may include `+`, spaces, or leading zeros.
- Monetary values use `DECIMAL` to preserve decimal precision.
- `quantity` and `line_no` are unsigned integers; `line_no` has a smaller range.
- `placed_at` is `DATETIME` to store the order's calendar time per application conventions; `created_at` is `TIMESTAMP` recording the creation instant.
- `status` uses `ENUM` because the example has a small, stable set of statuses. If status workflows change frequently or require metadata, switch to a lookup table.
- `CHECK` constraints prevent negative amounts or invalid quantities at the database level.

This is an illustrative schema. A production system must define email uniqueness policies under collation rules, phone number normalization, multi-currency storage, time zones, status lifecycles, and data growth requirements before finalizing the design.

## 12. Common Poor Choices

| Poor Choice | Problem | Better Choice |
| --- | --- | --- |
| Using `FLOAT` for money | Can introduce binary rounding errors | Use `DECIMAL(p,s)` with business-defined scale |
| Using `INT` for phone numbers | Strips leading zeros, cannot keep `+`, no arithmetic meaning | Use `VARCHAR` |
| Using `VARCHAR` for dates and times | Comparisons, sorting, and time arithmetic are error-prone | Use `DATE`, `DATETIME`, or `TIMESTAMP` |
| Using `BIGINT` for every column | Unnecessarily increases row and index size | Choose the smallest integer covering the expected domain |
| Using `TEXT` for every string | Hard to constrain data length and complicates indexing | Use `VARCHAR(M)` when there is a clear business limit |
| Using `CHAR` for variable-length strings | Can waste space and cause trailing-space handling differences | Use `VARCHAR(M)` |
| Using `NULL` for every status | Ambiguous semantics and queries must handle extra cases | Clearly define `NULL`, defaults, and business statuses |
| Using `ENUM` for constantly changing lists | Hard to manage migrations and value ordering | Use a lookup table when extensibility is needed |
| Treating `DATETIME` and `TIMESTAMP` as identical | Can cause offsets across time zone conversions | Choose based on wall-clock vs. instant semantics |

## 13. Pre-Schema-Freeze Checklist

- [ ] Documented min/max value domains and growth potential for every numeric column.
- [ ] Identified which columns need exact decimal precision vs. acceptable approximate error.
- [ ] Distinguished string-based identifier data from arithmetic quantities.
- [ ] Selected string lengths based on character count and charset while accounting for byte limits.
- [ ] Selected charset/collation according to language and comparison rules.
- [ ] Defined time zone conventions for `DATETIME` and `TIMESTAMP`.
- [ ] Decided explicitly which columns allow `NULL` and what defaults signify.
- [ ] Verified types and signedness of all foreign key columns.
- [ ] Evaluated primary key size and its impact on secondary indexes.
- [ ] Tested boundary values, Unicode data, `NULL` values, and invalid inputs.
- [ ] Checked SQL mode and type conversion behavior of the deployment environment.

## 14. Practice Exercises

1. Design a column to store product quantities that may grow up to 5 million. Choose an integer type and explain its value domain.
2. Design a column for product prices with up to 8 integer digits and 2 fractional digits. Write the DDL and explain precision/scale.
3. Store Vietnamese phone numbers, postal codes, and order codes that may contain leading zeros. Explain why integer types should not be used.
4. Create a table storing Vietnamese names using `utf8mb4`. Compare a case-insensitive/accent-insensitive collation with a binary or case-sensitive collation on sample data.
5. Choose `DATE`, `DATETIME`, or `TIMESTAMP` for birth dates, scheduled appointments, and payment timestamps. State the time zone convention for each case.
6. Run `0.1 + 0.2` using floating-point numbers and `DECIMAL`. Explain why the results can differ.
7. Create a `JSON` column for rarely queried attributes and extract a frequently filtered attribute into a separate column or an indexed generated column. Compare the query patterns.
8. Use `CHECK` constraints to enforce quantity > 0 and non-negative prices. Attempt to insert out-of-domain data and observe the results.
9. Use `EXPLAIN` to observe the impact of a wider key/index on a test query; explain the potential effect on storage size and index page count.

## 15. Completion Criteria

You have completed this lesson when you can determine value domains and precision before choosing types, explain the difference between exact and approximate numbers, select the right string and temporal types by semantics, configure appropriate charsets/collations, make explicit `NULL` decisions, and explain how column sizes affect rows, keys, and indexes. You should also be able to design a small schema with appropriate data types, clear constraints, and boundary-value validation.
