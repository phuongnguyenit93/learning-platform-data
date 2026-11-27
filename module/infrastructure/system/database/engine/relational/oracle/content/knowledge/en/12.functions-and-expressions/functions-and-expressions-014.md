# LISTAGG, Result Length Overflow, and Oracle Version Differences

When a report needs to display a list of orders, employee names, product codes, or statuses across multiple rows in the same group, returning separate rows can be inconvenient. Oracle Database provides the **`LISTAGG`** aggregate function to concatenate multiple values into a single string in a specified order.

For example, instead of returning three status rows:

```text
CUSTOMER_ID   STATUS
-----------   ------
101           NEW
101           PAID
101           SHIPPED
```

you can produce a single row:

```text
CUSTOMER_ID   STATUS_LIST
-----------   --------------------
101           NEW, PAID, SHIPPED
```

LISTAGG is handy for reporting, yet its result has a strict length limit. When the output string exceeds the limit, older Oracle versions raise `ORA-01489: result of string concatenation is too long`. Starting in Oracle Database 12.2, `ON OVERFLOW TRUNCATE` lets you proactively truncate the list and optionally append the omitted count. Starting in Oracle Database 19c, LISTAGG supports `DISTINCT` directly to remove duplicate values.

This lesson explains LISTAGG syntax, grouping and ordering, NULL handling, byte limits, version differences, and alternatives when results exceed VARCHAR2 limits.

After this lesson, you will be able to:

- Use LISTAGG in both aggregate and analytic forms.
- Control delimiters, element order, NULL values, and duplicate elements.
- Understand why the same SQL query succeeds on one Oracle version yet raises a syntax or overflow error on another.
- Choose between `ON OVERFLOW ERROR` and `ON OVERFLOW TRUNCATE` per data requirements.
- Explain the relationship between `MAX_STRING_SIZE`, VARCHAR2 limits, and actual byte length.
- Write alternatives using DISTINCT subqueries, XMLAGG, or CLOB handling when the full list must be preserved.
- Evaluate performance, deterministic ordering, and output safety.

> This lesson targets Oracle Database 11gR2 and later. Newer syntax such as `ON OVERFLOW TRUNCATE` and `LISTAGG(DISTINCT ...)` is unavailable on older versions. Always confirm the target database version before deploying SQL.

## 1. What does LISTAGG do?

`LISTAGG` is a string aggregation function: it takes values across multiple rows, concatenates non-NULL values into one string, inserts a delimiter between elements, and orders elements according to `WITHIN GROUP (ORDER BY ...)`.

General syntax:

```sql
LISTAGG(
    [ALL | DISTINCT] measure_expr
    [, delimiter]
    [ON OVERFLOW {ERROR | TRUNCATE [truncation_indicator]
        [{WITH | WITHOUT} COUNT}]]
)
WITHIN GROUP (ORDER BY order_by_clause)
[OVER (query_partition_clause)]
```

Where:

- `measure_expr` is the expression producing values to concatenate, typically a character column.
- `delimiter` is the separator placed between adjacent elements; if omitted, it defaults to NULL (no separator added).
- `ALL` is the default behavior: preserves duplicate values.
- `DISTINCT` removes duplicate values; direct syntax is supported from Oracle 19c onward.
- `ON OVERFLOW` specifies behavior when the result exceeds the maximum length.
- `WITHIN GROUP (ORDER BY ...)` defines the order of elements inside the string.
- `OVER (PARTITION BY ...)` uses LISTAGG as an analytic function, returning the partition result on every row without collapsing rows.

LISTAGG can be used in two forms:

1. **Aggregate:** produces one string per `GROUP BY` group, or one string for the entire row set when GROUP BY is omitted.
2. **Analytic:** produces a string per partition and repeats that result across each row in the partition.

## 2. Preparing practice data

The following examples use a table prefixed with `LAB_`. Run them in a practice schema with `CREATE TABLE` privileges; if the table name already exists, choose another name instead of overwriting data.

```sql
CREATE TABLE lab_listagg_orders (
    order_id    NUMBER(10) PRIMARY KEY,
    customer_id NUMBER(10) NOT NULL,
    status      VARCHAR2(20),
    product_name VARCHAR2(80),
    amount      NUMBER(12, 2)
);

INSERT INTO lab_listagg_orders VALUES
    (1, 101, 'NEW',     'Keyboard',  50);
INSERT INTO lab_listagg_orders VALUES
    (2, 101, 'PAID',    'Mouse',     20);
INSERT INTO lab_listagg_orders VALUES
    (3, 101, 'SHIPPED', 'Monitor',  200);
INSERT INTO lab_listagg_orders VALUES
    (4, 102, 'NEW',     'Cable',     10);
INSERT INTO lab_listagg_orders VALUES
    (5, 102, 'NEW',     'Cable',     10);
INSERT INTO lab_listagg_orders VALUES
    (6, 102, NULL,      'Adapter',   15);
INSERT INTO lab_listagg_orders VALUES
    (7, 103, NULL,      'Stand',     30);

COMMIT;
```

Illustrative data:

| ORDER_ID | CUSTOMER_ID | STATUS | PRODUCT_NAME |
| ---: | ---: | --- | --- |
| 1 | 101 | NEW | Keyboard |
| 2 | 101 | PAID | Mouse |
| 3 | 101 | SHIPPED | Monitor |
| 4 | 102 | NEW | Cable |
| 5 | 102 | NEW | Cable |
| 6 | 102 | NULL | Adapter |
| 7 | 103 | NULL | Stand |

Rows with `STATUS NULL` are included intentionally to observe how LISTAGG handles NULL. Customer 102 has two `NEW` rows and duplicate `Cable` product names; customer 103 has only a NULL status.

## 3. Aggregate LISTAGG

### 3.1. Concatenating a column into one string

```sql
SELECT
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Result:

```text
NEW, PAID, SHIPPED
```

`ORDER BY order_id` inside `WITHIN GROUP` sorts the elements inside the string. Omitting the customer filter and GROUP BY makes LISTAGG produce **a single string across all rows**:

```sql
SELECT
    LISTAGG(status, ' | ')
        WITHIN GROUP (ORDER BY customer_id, order_id) AS all_statuses
FROM lab_listagg_orders;
```

### 3.2. One string per group

LISTAGG is commonly used with `GROUP BY`:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Illustrative output:

| CUSTOMER_ID | STATUS_LIST |
| ---: | --- |
| 101 | NEW, PAID, SHIPPED |
| 102 | NEW, NEW |
| 103 | NULL |

For customer 102, the row with `STATUS NULL` is skipped; both `NEW` values are kept because `ALL` is the default. For customer 103, every measure value is NULL, so the LISTAGG result is NULL.

### 3.3. Default delimiter and custom delimiters

If delimiter is omitted:

```sql
SELECT LISTAGG(status)
       WITHIN GROUP (ORDER BY order_id) AS joined_status
FROM lab_listagg_orders
WHERE customer_id = 101;
```

The result is `NEWPAIDSHIPPED`. A delimiter can be a comma, hyphen, newline, or any other string:

```sql
SELECT LISTAGG(status, CHR(10))
       WITHIN GROUP (ORDER BY order_id) AS status_lines
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Here `CHR(10)` is a line feed; clients may render items across multiple lines or display control characters depending on configuration. When exporting files, define how newlines and quoting should be handled.

Delimiters are inserted **between measure values**, not before the first element or after the last. If the delimiter is NULL, LISTAGG adds no separator.

### 3.4. LISTAGG ignores NULL measures

LISTAGG does not add an item for rows where `measure_expr` is NULL. Example:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(status) AS nonnull_status_rows,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
WHERE customer_id = 102;
```

The output has 3 rows, 2 non-NULL statuses, and the string `NEW, NEW`. LISTAGG does not emit a dangling delimiter for the NULL status.

In Oracle, zero-length character strings (`''`) are treated as NULL in standard character contexts. Therefore, a measure expression evaluating to an empty string is also ignored by LISTAGG like a NULL value. Keep this rule in mind when source data arrives from applications or string concatenation.

### 3.5. Order inside LISTAGG vs. outer ORDER BY

The two `ORDER BY` clauses serve distinct purposes:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id DESC) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id ASC;
```

- `ORDER BY order_id DESC` inside `WITHIN GROUP` determines the order of concatenated statuses.
- `ORDER BY customer_id ASC` at the end of the SQL statement determines the order of result rows (groups).

You cannot move the inner ORDER BY to the end of the query and expect the element order inside the string to change accordingly.

## 4. Deterministic ordering and duplicate sort keys

Oracle guarantees deterministic LISTAGG ordering only when the ORDER BY expression list defines a unique total order. If multiple rows share the same sort key, their relative order can be non-deterministic.

Example:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY status) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id;
```

If a customer has multiple `NEW` rows, `ORDER BY STATUS` alone does not define an order among them. When strings contain only identical statuses the output looks identical, yet when measures include additional columns or complex expressions, non-determinism becomes obvious.

Add a unique key as a tie-breaker:

```sql
SELECT
    customer_id,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY status, order_id) AS statuses
FROM lab_listagg_orders
GROUP BY customer_id;
```

Rules:

- When reproducible output across runs is needed, include enough columns in LISTAGG's ORDER BY to uniquely order relevant rows.
- With multiple sort columns, specify ASC/DESC and NULL ordering explicitly if sort columns are nullable.
- Never rely on physical table order, index order, or an accidental execution plan.

## 5. Analytic LISTAGG

LISTAGG can also operate as an analytic function using `OVER (PARTITION BY ...)`. Every source row is preserved, and each row receives the aggregated string for its partition.

```sql
SELECT
    order_id,
    customer_id,
    status,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id)
        OVER (PARTITION BY customer_id) AS customer_statuses
FROM lab_listagg_orders
ORDER BY customer_id, order_id;
```

Conceptual result:

| ORDER_ID | CUSTOMER_ID | STATUS | CUSTOMER_STATUSES |
| ---: | ---: | --- | --- |
| 1 | 101 | NEW | NEW, PAID, SHIPPED |
| 2 | 101 | PAID | NEW, PAID, SHIPPED |
| 3 | 101 | SHIPPED | NEW, PAID, SHIPPED |
| 4 | 102 | NEW | NEW, NEW |
| 5 | 102 | NEW | NEW, NEW |
| 6 | 102 | NULL | NEW, NEW |
| 7 | 103 | NULL | NULL |

Differences:

| Aggregate LISTAGG | Analytic LISTAGG |
| --- | --- |
| Usually paired with GROUP BY | Uses OVER to define partitions |
| Returns one row per group | Preserves every source row |
| Useful for summary reports | Useful when both detail rows and summary string are needed |

Do not put a trailing `ORDER BY` at the end of the SQL statement as a substitute for `WITHIN GROUP` ordering. `OVER (PARTITION BY ...)` defines the partition; `WITHIN GROUP` still governs element order within the string.

## 6. Removing duplicates: ALL, DISTINCT, and versions

### 6.1. LISTAGG preserves duplicates by default

For customer 102:

```sql
SELECT
    customer_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders
WHERE customer_id = 102
GROUP BY customer_id;
```

Result:

```text
Cable, Cable, Adapter
```

This is the default `ALL` behavior. Two separate orders both contain `Cable`, so LISTAGG displays `Cable` twice.

### 6.2. LISTAGG DISTINCT starting in Oracle 19c

Oracle Database 19c supports the `DISTINCT` keyword directly inside LISTAGG:

```sql
SELECT
    customer_id,
    LISTAGG(DISTINCT product_name, ', ')
        WITHIN GROUP (ORDER BY product_name) AS unique_products
FROM lab_listagg_orders
WHERE customer_id = 102
GROUP BY customer_id;
```

Each product appears only once:

```text
Adapter, Cable
```

`DISTINCT` removes duplicate measures before concatenating. For character data, determining whether two values are duplicates also depends on data types, collation, and active comparison rules on the database or expression.

If a business ordering other than alphabetical order is needed, consider which column defines the order of each distinct value. Avoid adding arbitrary tie-breaker columns to the ORDER BY of `LISTAGG DISTINCT` if those columns are not unique per deduplicated measure.

### 6.3. Oracle 11gR2 through pre-19c: DISTINCT via subquery

On versions that do not support `LISTAGG(DISTINCT ...)`, deduplicate in a subquery before calling LISTAGG:

```sql
SELECT
    customer_id,
    LISTAGG(product_name, ', ')
        WITHIN GROUP (ORDER BY product_name) AS unique_products
FROM (
    SELECT DISTINCT customer_id, product_name
    FROM lab_listagg_orders
    WHERE customer_id = 102
      AND product_name IS NOT NULL
)
GROUP BY customer_id;
```

When aggregating multiple customers, keep the grouping key inside the subquery as shown so deduplication does not collapse values across different groups. Handle NULLs intentionally; LISTAGG skips NULL measures automatically, so `IS NOT NULL` here mainly makes intent explicit.

### 6.4. Avoid deduplicating in the wrong scope

Incorrect scope example:

```sql
SELECT DISTINCT product_name
FROM lab_listagg_orders;
```

If you then build lists across multiple customers, that query deduplicates across the entire table, leaving each product only once overall rather than once per customer. When deduplicating per group, the subquery must include **both the grouping keys and the measure**.

## 7. Why can LISTAGG overflow its length limit?

LISTAGG produces a `VARCHAR2` result (or `RAW` when the measure is RAW). The output is subject to maximum length limits determined by data type and the `MAX_STRING_SIZE` parameter.

For VARCHAR2 output:

| MAX_STRING_SIZE | Maximum LISTAGG Result Length |
| --- | ---: |
| `STANDARD` | 4000 bytes |
| `EXTENDED` | 32767 bytes |

For RAW measures, the limits are 2000 bytes under STANDARD and 32767 bytes under EXTENDED. For RAW, the delimiter and truncation indicator must also be compatible RAW types.

**Limits are measured in bytes**, not necessarily in characters. If a database uses a multi-byte character set such as AL32UTF8, one character can occupy multiple bytes. A list of 1,500 accented Vietnamese characters does not necessarily fit in 1,500 bytes.

### 7.1. Checking MAX_STRING_SIZE

Users with parameter-viewing privileges can query:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'max_string_size';
```

Or in SQL*Plus/SQLcl:

```sql
SHOW PARAMETER max_string_size
```

Common values:

- `STANDARD`: traditional SQL VARCHAR2 limit.
- `EXTENDED`: allows larger SQL VARCHAR2/RAW limits under Oracle-supported conditions.

`MAX_STRING_SIZE` is a database-level configuration parameter with strict administrative procedures. **It cannot be changed with ALTER SESSION**, and it should never be changed merely to fix one overflowing LISTAGG report. Switching to EXTENDED carries upgrade/deployment prerequisites and compatibility impacts; leave that evaluation to a DBA.

### 7.2. ORA-01489: result of string concatenation is too long

In older versions or default LISTAGG mode, exceeding the limit causes Oracle to raise:

```text
ORA-01489: result of string concatenation is too long
```

This is an **aggregated output length** error, not necessarily caused by any single long source column. Individual measures can be short, yet thousands of measures plus delimiters exceed the ceiling.

Example generating a long string:

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS value_text
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT LISTAGG(value_text, ', ')
       WITHIN GROUP (ORDER BY id) AS long_text
FROM generated_rows;
```

Total length here exceeds 4000 bytes under STANDARD and raises ORA-01489 unless overflow is handled. Do not run large string-generation tests on production systems just to verify this.

### 7.3. Estimating result size up front

Given `n` non-NULL measures, the result length is approximately:

```text
Sum of measure lengths
+ (n - 1) × delimiter length
```

This is a conceptual estimate; calculate using **bytes**, accounting for type conversions, character set, and actual delimiters. With multi-byte text, `LENGTHB` is more appropriate than `LENGTH` for capacity estimation:

```sql
SELECT
    SUM(LENGTHB(product_name)) AS measure_bytes,
    (COUNT(product_name) - 1) * LENGTHB(', ') AS delimiter_bytes,
    SUM(LENGTHB(product_name))
      + GREATEST(COUNT(product_name) - 1, 0) * LENGTHB(', ')
        AS estimated_bytes
FROM lab_listagg_orders
WHERE customer_id = 102;
```

This estimates a specific group using delimiter `', '`. Because LISTAGG ignores NULL, use `COUNT(product_name)` rather than `COUNT(*)` to count measures actually concatenated.

Do not treat this estimate as a guarantee against overflow if measures undergo conversions, differing collations/encodings, or concurrent modifications; it is a pre-flight capacity indicator.

## 8. Overflow handling from Oracle 12.2: ON OVERFLOW ERROR/TRUNCATE

Oracle Database 12.2 added the **overflow clause** to LISTAGG.

### 8.1. ON OVERFLOW ERROR

`ON OVERFLOW ERROR` explicitly requests an error when output exceeds the limit. This is also the default behavior when no overflow clause is specified:

```sql
SELECT
    LISTAGG(product_name, ', ' ON OVERFLOW ERROR)
        WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

If the result exceeds the limit, the query raises `ORA-01489`. This mode fits when **losing any element is a data error** that the caller must handle.

### 8.2. ON OVERFLOW TRUNCATE

`ON OVERFLOW TRUNCATE` lets Oracle truncate the list so the result stays within limits and append a truncation indicator:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE
    ) WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

The default truncation indicator is `...`. You can specify a custom indicator:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '[remaining]'
    ) WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders;
```

**TRUNCATE is intentional data loss in the result.** Use it only when the application accepts an abbreviated list and can signal that the output is incomplete. If an API requires every element, choose another return type or design rather than using TRUNCATE to mask truncation.

### 8.3. WITH COUNT and WITHOUT COUNT

Starting in 12.2, you can specify:

- `WITH COUNT`: appends the number of omitted items in parentheses at the end.
- `WITHOUT COUNT`: appends only the truncation indicator without printing the omitted item count.

Example:

```sql
SELECT
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS products_with_count,
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITHOUT COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS products_without_count
FROM lab_listagg_orders;
```

If neither WITH nor WITHOUT COUNT is specified, the default is **WITH COUNT**. With `WITH COUNT`, truncation may happen earlier because Oracle reserves enough room for the final delimiter, truncation indicator, and parenthesized count (Oracle reserves buffer room per its internal rules, including up to 24 characters for the parenthesized count). Therefore, never compute the cutoff manually by subtracting only the indicator length.

Oracle truncates cleanly at measure boundaries rather than slicing inside a single measure value. The output retains whole items, followed by the indicator and optional count.

### 8.4. Choosing an appropriate indicator

The indicator should clearly signal truncation, for example:

```sql
LISTAGG(
    product_name,
    ', ' ON OVERFLOW TRUNCATE '...[truncated]' WITHOUT COUNT
)
WITHIN GROUP (ORDER BY order_id)
```

In a UI, a short indicator like `...` works well. In logs or audits, pick an unmistakable indicator and record separate metadata such as total item count, displayed count, and omitted count. Never pick an indicator string that could legitimately appear in data without an escape convention.

### 8.5. TRUNCATE does not replace CLOB handling

If a list contains 100,000 items and an API must return all of them, truncating to 4000 or 32767 bytes does not meet the requirement. Better alternatives include:

- Returning **multiple rows** and letting the application display or assemble them where needed.
- Returning a **JSON array** or typed collection instead of a delimited string.
- Using **CLOB** with a suitable CLOB aggregation method if a single long text value is truly required.
- Paginating results instead of building one massive string.

## 9. Oracle version differences

This milestone table governs syntax support:

| Version | Basic LISTAGG | ON OVERFLOW TRUNCATE | LISTAGG DISTINCT |
| --- | --- | --- | --- |
| Oracle 11g Release 2 | Yes | No | No |
| Oracle 12.1 | Yes | No | No |
| Oracle 12.2 | Yes | Yes | No |
| Oracle 18c | Yes | Yes | No |
| Oracle 19c | Yes | Yes | Yes |
| Newer releases | Yes | Yes | Yes |

Key feature milestones:

1. **11gR2:** LISTAGG introduced with `WITHIN GROUP (ORDER BY ...)`.
2. **12.2:** Added `ON OVERFLOW ERROR/TRUNCATE`, custom indicator, and `WITH/WITHOUT COUNT`.
3. **19c:** Added `DISTINCT` inside LISTAGG.
4. **MAX_STRING_SIZE:** Separate configuration parameter governing VARCHAR2/RAW limits (STANDARD/EXTENDED); does not change DISTINCT or overflow syntax availability.

When SQL must run across multiple Oracle generations, target the **lowest supported version**. A query using `ON OVERFLOW TRUNCATE` will fail to compile on older databases lacking that syntax; likewise, `LISTAGG(DISTINCT ...)` fails prior to 19c.

### 9.1. Checking the database version

Check the version:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Or with view privileges:

```sql
SELECT version, version_full
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
```

Available columns/names vary slightly by release. Another general query is:

```sql
SELECT * FROM v$version;
```

Do not confuse your SQL Developer/SQLcl client version with the **database server version**: syntax support is determined by the server.

### 9.2. Adapting SQL to server capabilities

Applications supporting multiple releases can:

- Use basic LISTAGG targeting the lowest version if data lengths are bounded.
- Add `ON OVERFLOW TRUNCATE` only when targeting server 12.2+.
- Use `DISTINCT` inside LISTAGG only when targeting server 19c+.
- Deduplicate in a subquery on older versions.
- Choose CLOB, JSON, or multi-row output for long lists instead of hoping for unsupported syntax.

Do not rely on catching runtime syntax errors to pick a query strategy. Determine server version/capabilities during deployment and test SQL on the actual target server.

## 10. MAX_STRING_SIZE and byte limits

### 10.1. STANDARD vs. EXTENDED

`MAX_STRING_SIZE` governs maximum SQL sizes for VARCHAR2/RAW types:

| Return Type | STANDARD | EXTENDED |
| --- | ---: | ---: |
| VARCHAR2 | 4000 bytes | 32767 bytes |
| RAW | 2000 bytes | 32767 bytes |

LISTAGG returns VARCHAR2 for character measures, or RAW for RAW measures per type rules. Hence, the LISTAGG limit is not a universal "4,000 characters" across all systems.

### 10.2. Multi-byte character sets

In an AL32UTF8 database, one character can take from one to several bytes. Therefore:

- `LENGTH(text)` counts characters per Oracle semantics.
- `LENGTHB(text)` counts bytes.
- VARCHAR2/LISTAGG limits are enforced in bytes.

Example:

```sql
SELECT
    LENGTH('Oracle') AS char_count,
    LENGTHB('Oracle') AS byte_count,
    LENGTH('Tiếng Việt') AS viet_char_count,
    LENGTHB('Tiếng Việt') AS viet_byte_count
FROM dual;
```

Exact byte counts depend on the database character set. Measure on your actual target environment; never use UI character counts as proof that a string stays under byte limits.

### 10.3. Do not raise MAX_STRING_SIZE just for one failing LISTAGG

Switching from STANDARD to EXTENDED is a database-wide decision with strict procedures and compatibility impacts. It does not:

- Make LISTAGG return an unlimited CLOB.
- Eliminate ORA-01489 if lists still exceed 32,767 bytes.
- Fix a query unnecessarily aggregating massive datasets.
- Solve returning hundreds of thousands of elements in one VARCHAR2.

First ask whether **users genuinely need a single concatenated string**, whether pagination or multiple rows work better, and whether CLOB or JSON fits better.

## 11. Solutions for older versions and long lists

### 11.1. Pre-12.2: no ON OVERFLOW TRUNCATE

On Oracle 11gR2/12.1, LISTAGG lacks the overflow clause. Exceeding the limit raises ORA-01489. Options include:

- Filtering the dataset before aggregating if business logic only needs a subset.
- Returning individual rows so the application paginates or formats them.
- Using a CLOB-producing approach such as XMLAGG or proper LOB processing.
- Increasing database-level VARCHAR2 limits only with an approved DBA plan when it genuinely solves the need.

### 11.2. Using XMLAGG to produce a CLOB result

A common pattern uses `XMLAGG` and `XMLELEMENT`:

```sql
SELECT
    XMLAGG(
        XMLELEMENT(e, product_name || ', ')
        ORDER BY order_id
    ).EXTRACT('//text()').GETCLOBVAL() AS product_list_clob
FROM lab_listagg_orders
WHERE customer_id = 102;
```

The result is a CLOB containing concatenated items with delimiters (this pattern leaves a trailing delimiter). `XMLAGG` aggregates `XMLType` and is not bound by LISTAGG's VARCHAR2 limit.

**Test XML special characters** such as `&`, `<`, `>`, and Unicode text. XML serialization/escaping can alter characters relative to raw text; for user data or exact round-tripping, decode/unescape per XML rules. Never assume XMLAGG is a pure string join with zero escaping side effects.

### 11.3. Building a CLOB with DBMS_LOB in PL/SQL

When you need explicit concatenation rules and CLOB output, create a temporary CLOB and append each measure. Illustrative example with VARCHAR2 measures:

```sql
SET SERVEROUTPUT ON

DECLARE
    l_result    CLOB;
    l_delimiter VARCHAR2(10) := ', ';
    l_first     BOOLEAN := TRUE;
BEGIN
    DBMS_LOB.CREATETEMPORARY(l_result, TRUE);

    FOR r IN (
        SELECT product_name
        FROM lab_listagg_orders
        WHERE customer_id = 102
        ORDER BY order_id
    ) LOOP
        IF r.product_name IS NOT NULL THEN
            IF NOT l_first THEN
                DBMS_LOB.WRITEAPPEND(
                    l_result,
                    LENGTH(l_delimiter),
                    l_delimiter
                );
            END IF;

            DBMS_LOB.WRITEAPPEND(
                l_result,
                LENGTH(r.product_name),
                r.product_name
            );
            l_first := FALSE;
        END IF;
    END LOOP;

    -- Print only the beginning for illustration; DBMS_OUTPUT has a line limit.
    DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(l_result, 4000, 1));
    DBMS_LOB.FREETEMPORARY(l_result);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_LOB.ISTEMPORARY(l_result) = 1 THEN
            DBMS_LOB.FREETEMPORARY(l_result);
        END IF;
        RAISE;
END;
/
```

This PL/SQL block demonstrates delimiter management and skipping NULL measures. In production code:

- Do not print large CLOBs via `DBMS_OUTPUT` as if console output were unlimited.
- Return the CLOB via an OUT parameter, read via JDBC LOB APIs, or store in an appropriate CLOB column.
- Free temporary LOBs along both success and exception paths.
- If measures themselves are CLOBs, use proper LOB operations instead of assuming `WRITEAPPEND` with a VARCHAR2 buffer handles arbitrary lengths.
- Include a tie-breaker in ORDER BY when reproducible ordering is needed.

### 11.4. Returning a JSON array instead of a delimited string

When the consumer is a REST API or application, a JSON array is usually safer than a comma-joined string:

```json
["Keyboard", "Mouse", "Monitor"]
```

JSON preserves element boundaries cleanly; an item containing a comma is never mistaken for multiple items. Oracle versions supporting `JSON_ARRAYAGG` and `RETURNING CLOB` can emit JSON larger than VARCHAR2 under supported conditions:

```sql
SELECT JSON_ARRAYAGG(
           product_name
           ORDER BY order_id
           RETURNING CLOB
       ) AS products_json
FROM lab_listagg_orders
WHERE customer_id = 101;
```

Verify JSON syntax/feature support on your specific server version. A JSON array is **not equivalent** to a LISTAGG string: it is a structured data type requiring a JSON parser on the consumer side.

### 11.5. When should you return multiple rows instead of aggregating?

If the application needs to:

- Paginate individual products.
- Filter or sort on the client or server.
- Open detail views for an item.
- Transfer lists potentially reaching tens of thousands of items.
- Preserve each item's native data type.

then returning multiple rows is usually far better than LISTAGG. Collapsing rows into one huge string strips per-item structure, complicates reverse parsing, and increases memory pressure on both database and client.

## 12. Data containing delimiters and reverse-parsing risks

Suppose the product list contains:

```text
Adapter, USB
Cable
```

If LISTAGG uses delimiter `', '`, the result is:

```text
Adapter, USB, Cable
```

Without escaping or quoting rules, it is impossible to tell whether this represents three products (`Adapter`, `USB`, `Cable`) or two (`Adapter, USB` and `Cable`). LISTAGG simply joins strings; it does not encode value boundaries.

When generating CSV:

- Apply standard CSV quoting and escaping rules to every field.
- Never join with commas and assume simple splitting will work.
- Properly escape embedded newlines, quotes, and delimiters.

When returning over APIs:

- Prefer a JSON array or tabular result set.
- If a single string is mandatory, explicitly define the delimiter and escape format.
- Document whether NULLs, duplicates, or truncation apply.

A LISTAGG string works great for display; using one as a **storage format for reverse parsing** requires a much stricter contract.

## 13. Performance and execution plans

LISTAGG must process all values in each group and sort them per `WITHIN GROUP`. For large groups, sorting consumes PGA/TEMP and CPU; `DISTINCT` adds deduplication overhead.

### 13.1. Filter data before aggregating

Do not aggregate more rows than business logic requires:

```sql
SELECT customer_id,
       LISTAGG(product_name, ', ')
           WITHIN GROUP (ORDER BY order_id) AS products
FROM lab_listagg_orders
WHERE status IN ('NEW', 'PAID')
GROUP BY customer_id;
```

`WHERE` shrinks the input row set before LISTAGG runs. Ensure filter predicates match business rules rather than dropping valid data just to dodge ORA-01489.

### 13.2. Indexes do not guarantee LISTAGG avoids sorting

Indexes can help access rows by group or order, yet the optimizer picks plans based on statistics, selectivity, joins, grouping, and cost. Do not assume that having an index on `(customer_id, order_id)` eliminates LISTAGG sort operations.

Inspect the execution plan using appropriate tools such as `DBMS_XPLAN` when authorized:

```sql
EXPLAIN PLAN FOR
SELECT customer_id,
       LISTAGG(status, ', ')
           WITHIN GROUP (ORDER BY order_id) AS status_list
FROM lab_listagg_orders
GROUP BY customer_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows an estimated plan; it does not replace inspecting actual execution plans and runtime statistics with appropriate privileges/tools.

### 13.3. Avoid redundant aggregation on the same partition

If a report needs both a status list and a product list, evaluate:

- Can a single grouped query compute all required aggregates?
- Do both lists share the exact same dataset and filters?
- Is a join multiplying rows before LISTAGG runs?
- Can you pre-aggregate in subqueries before joining group results to avoid row multiplication?

A one-to-many join prior to LISTAGG can cause measures to repeat unintentionally. Never slap `DISTINCT` onto LISTAGG to hide join multiplication when the join relationship itself is flawed.

### 13.4. Count items before deciding on truncation

A report can return both the item count and the display string:

```sql
SELECT
    customer_id,
    COUNT(product_name) AS product_count,
    LISTAGG(
        product_name,
        ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT
    ) WITHIN GROUP (ORDER BY order_id) AS product_list
FROM lab_listagg_orders
GROUP BY customer_id;
```

The separate count tells consumers the overall scale, while LISTAGG's indicator flags truncation. To inspect which specific items were omitted, query detail rows or paginate; the count alone does not reveal the omitted values.

## 14. Common errors and pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ORA-01489` | LISTAGG string exceeds VARCHAR2/RAW limit | From 12.2 use TRUNCATE if partial lists are acceptable; otherwise use CLOB/JSON/multiple rows |
| `ORA-00923` or syntax error at OVERFLOW | Server lacks `ON OVERFLOW TRUNCATE` or clause is misplaced | Check version; fix syntax or use older-version workaround |
| Syntax error on `LISTAGG(DISTINCT ...)` | Server is older than 19c | Use `SELECT DISTINCT` in a subquery before LISTAGG |
| List contains duplicate values | Default LISTAGG is ALL or a JOIN multiplied rows | Inspect join cardinality; use DISTINCT only when deduplication is genuinely intended |
| Element order shifts across runs | `ORDER BY` inside `WITHIN GROUP` is non-unique | Add a unique tie-breaker column |
| Result is NULL despite rows existing | All measures are NULL or expression evaluates to NULL | Check `COUNT(measure)`, NULLs, and data types |
| Unexpected repeated delimiters | Source values contain delimiter text or pre-joined strings | Clean measures and define escaping rules |
| Truncated earlier than expected | Limit is in bytes; WITH COUNT and indicator reserve space | Measure with `LENGTHB`, check character set and output type |
| DISTINCT merges seemingly different values | Collation/type rules treat them as equivalent | Check collation and comparison rules |
| LISTAGG runs slowly | Large groups, sorting, distinct, or join multiplication | Filter early, inspect plan/statistics, paginate or change shape |
| SQL runs in dev but fails to compile in prod | Server version mismatch | Target lowest supported version and write compatible SQL |
| JSON/XML output differs from raw string | Escaping/serialization rules | Use typed structures and unescape/parse per protocol |

### 14.1. ORA-01489 diagnostic checklist

1. Identify which LISTAGG expression overflows and which group has the most items.
2. Count non-NULL measures with `COUNT(measure)`.
3. Estimate bytes via `SUM(LENGTHB(measure))` plus delimiters.
4. Check `MAX_STRING_SIZE` and the database character set.
5. Determine whether the consumer accepts truncated output.
6. If acceptable, consider `ON OVERFLOW TRUNCATE` on 12.2+.
7. If complete output is required, switch to CLOB/JSON/multiple rows or apply sensible business limits.
8. Verify server version before deploying newer syntax.

Never increase `MAX_STRING_SIZE` or add `DISTINCT` just to silence the error without verifying data requirements.

## 15. Comparing implementation options

| Requirement | Solution | Notes |
| --- | --- | --- |
| Short strings, small groups, all items required | Default LISTAGG / `ON OVERFLOW ERROR` | Failing on overflow catches unexpectedly huge data |
| Display lists where abbreviation is acceptable | `LISTAGG ... ON OVERFLOW TRUNCATE` | Must clearly indicate truncation; never use when completeness is mandatory |
| Deduplication on Oracle 19c+ | `LISTAGG DISTINCT` | Check collation and deduplication semantics |
| Deduplication prior to 19c | `SELECT DISTINCT` in a subquery | Retain all grouping keys inside the subquery |
| Long CLOB output in SQL | `XMLAGG` or suitable LOB aggregation | Check XML escaping, ordering, and resource usage |
| Custom CLOB assembly | PL/SQL with `DBMS_LOB` | Manage temporary LOBs and exception cleanup |
| Structured lists for APIs | `JSON_ARRAYAGG` / JSON array | Requires server support and consumer JSON parsing |
| Very large lists needing pagination/interactivity | Return multiple rows | Preserves native types and clean item boundaries |

No single approach fits every problem. Choose based on **maximum length, completeness requirements, server version, consumer format, and pagination needs**.

## 16. Comprehensive practice lab

### Step 1 — LISTAGG by customer

```sql
SELECT
    customer_id,
    LISTAGG(status, ' -> ')
        WITHIN GROUP (ORDER BY order_id) AS status_flow
FROM lab_listagg_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Predictions:

- Customer 101 has three statuses ordered by `order_id`.
- Customer 102 has two `NEW` statuses; the NULL status is skipped.
- Customer 103 has only NULL status, so the result is NULL.

### Step 2 — Analytic LISTAGG

```sql
SELECT
    order_id,
    customer_id,
    status,
    LISTAGG(status, ', ')
        WITHIN GROUP (ORDER BY order_id)
        OVER (PARTITION BY customer_id) AS all_customer_statuses
FROM lab_listagg_orders
ORDER BY customer_id, order_id;
```

Explain why the output row count equals the source table row count while each customer's aggregated string repeats across rows in that partition.

### Step 3 — Distinct for your Oracle version

On Oracle 19c+:

```sql
SELECT customer_id,
       LISTAGG(DISTINCT product_name, ', ')
           WITHIN GROUP (ORDER BY product_name) AS products
FROM lab_listagg_orders
GROUP BY customer_id;
```

On earlier versions:

```sql
SELECT customer_id,
       LISTAGG(product_name, ', ')
           WITHIN GROUP (ORDER BY product_name) AS products
FROM (
    SELECT DISTINCT customer_id, product_name
    FROM lab_listagg_orders
)
GROUP BY customer_id;
```

Compare results for customer 102. Explain why the subquery must retain `CUSTOMER_ID`.

### Step 4 — Generate long data to test overflow

No need to insert real rows:

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT LISTAGG(item, ', ')
       WITHIN GROUP (ORDER BY id) AS item_list
FROM generated_rows;
```

Under STANDARD, this raises ORA-01489. Record your version and `MAX_STRING_SIZE` before drawing conclusions.

### Step 5 — Test ON OVERFLOW TRUNCATE on 12.2+

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT
    LISTAGG(
        item,
        ', ' ON OVERFLOW TRUNCATE '...[cut]' WITH COUNT
    ) WITHIN GROUP (ORDER BY id) AS truncated_list
FROM generated_rows;
```

Observe the indicator and count at the end. Try `WITHOUT COUNT` and explain why the list retains slightly more items.

### Step 6 — Compute byte estimates

```sql
WITH generated_rows AS (
    SELECT LEVEL AS id,
           RPAD('X', 100, 'X') AS item
    FROM dual
    CONNECT BY LEVEL <= 100
)
SELECT
    COUNT(item) AS measure_count,
    SUM(LENGTHB(item)) AS measure_bytes,
    (COUNT(item) - 1) * LENGTHB(', ') AS delimiter_bytes,
    SUM(LENGTHB(item))
      + GREATEST(COUNT(item) - 1, 0) * LENGTHB(', ')
        AS estimated_bytes
FROM generated_rows;
```

Compare the estimate against the output limit. If you replace X with accented Vietnamese characters, re-measure `LENGTHB` to see how byte length increases.

### Step 7 — Choosing a return format

An API requires a list of 20,000 products and must preserve every single item. Choose among LISTAGG, LISTAGG TRUNCATE, JSON array, CLOB, and returning multiple rows. State clearly:

- Does the consumer need to parse individual items?
- Must data types and item boundaries be preserved?
- Which length limits apply?
- Which server version must be supported?
- If returning a CLOB, how will the client stream it?

## 17. Best practices

1. **Always specify ORDER BY inside WITHIN GROUP** and add a unique tie-breaker whenever reproducible order matters.
2. **Understand NULL and DISTINCT:** LISTAGG skips NULL measures; default keeps duplicates; direct `DISTINCT` requires 19c+.
3. **Know your server version:** `ON OVERFLOW TRUNCATE` arrived in 12.2; `LISTAGG DISTINCT` arrived in 19c.
4. **Measure bytes, not just character counts:** `LENGTHB` and the character set govern VARCHAR2 limits.
5. **Never use TRUNCATE when complete data is required.** The indicator flags truncation; it cannot recover dropped items.
6. **Do not raise MAX_STRING_SIZE lightly.** EXTENDED still has limits and is a database-wide configuration change.
7. **Pick CLOB/JSON/multiple rows for large lists.** Never try to cram arbitrary datasets into one VARCHAR2.
8. **Audit joins before adding DISTINCT.** DISTINCT can mask unintended row multiplication from broken joins.
9. **Specify delimiters and escaping.** LISTAGG does not produce a round-trip-safe format on its own.
10. **Inspect execution plans and workloads.** Large groups, sorting, and distinct operations consume CPU/PGA/TEMP.

## 18. Self-check questions

1. How does LISTAGG differ from `CONCAT` regarding the number of input rows?
2. If delimiter is omitted, what does Oracle use? If a measure is NULL, is an item added?
3. Why is `ORDER BY` needed inside `WITHIN GROUP` even when the SQL query already has a trailing `ORDER BY`?
4. When `ORDER BY` is non-unique, why can the concatenated string vary across runs?
5. Can Oracle 11gR2 or 12.1 use `ON OVERFLOW TRUNCATE`?
6. Which version introduced `ON OVERFLOW TRUNCATE`? Which version introduced `LISTAGG DISTINCT`?
7. Under STANDARD and EXTENDED, what are the LISTAGG VARCHAR2 byte limits?
8. Why can 2,000 Vietnamese characters exceed a byte limit even though 2,000 is less than 4,000?
9. How does `WITH COUNT` differ from `WITHOUT COUNT`? Why can `WITH COUNT` truncate earlier?
10. When should you choose XMLAGG/CLOB over LISTAGG?
11. Why can a LISTAGG string containing delimiter characters in source values fail to parse back reliably?
12. If a JOIN causes a product to appear three times, should you immediately add `DISTINCT`? What must you check first?

## 19. Mental model

```text
Multiple rows
   │
   ▼
LISTAGG(measure, delimiter)
   │
   ├── Ignores NULL measures
   ├── Default ALL: preserves duplicates
   ├── DISTINCT: Oracle 19c+
   └── WITHIN GROUP (ORDER BY ...)
          determines element order
   │
   ▼
VARCHAR2 / RAW with byte limit
   │
   ├── Default / ON OVERFLOW ERROR
   │       → ORA-01489 if limit exceeded
   │
   └── ON OVERFLOW TRUNCATE (Oracle 12.2+)
           → indicator
           → WITH COUNT / WITHOUT COUNT

If complete and long output is required:
   → XMLAGG / CLOB
   → JSON array
   → return multiple rows / paginate
```

**Key takeaway:** LISTAGG is a convenient string-aggregation tool, yet its output remains a size-bounded type. Control ordering, NULLs, duplicates, server version, and byte length before deploying in reports or APIs. When dropping tail items is acceptable, use `ON OVERFLOW TRUNCATE` with a clear indicator; when complete long lists are mandatory, switch to CLOB, JSON, or multi-row results instead of hiding errors via truncation.
