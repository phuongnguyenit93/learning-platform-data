# JSON_VALUE and Version Support Requirements

## Lesson Objectives

After this lesson, you will be able to:

- Identify the minimum MySQL version that supports JSON_VALUE.
- Use JSON_VALUE to extract a scalar value from a JSON document by JSON path.
- Convert a JSON value to an SQL type using RETURNING.
- Distinguish missing values, JSON null, SQL NULL, and conversion errors.
- Choose the appropriate behavior using ON EMPTY and ON ERROR.
- Understand the default return type VARCHAR(512), character set, and collation.
- Distinguish JSON_VALUE from JSON_EXTRACT, the -> operator, and the ->> operator.
- Create a functional index on a JSON_VALUE expression and verify it with EXPLAIN.
- Choose alternatives when running MySQL older than 8.0.21.
- Avoid pitfalls involving JSON paths, return types, heterogeneous data, and wrong assumptions about error handling.

JSON is often used to store flexible attributes such as shipping information, configuration, metadata, or integration data from external systems. When filtering by an attribute inside JSON, the application must extract the value and compare it using the appropriate data type.

JSON_VALUE is a MySQL function used to extract a scalar value from a JSON document. It can convert that value to a specific SQL type via RETURNING, while letting you specify the behavior when the path finds no data or when the value cannot be converted using ON EMPTY and ON ERROR.

Important compatibility point: JSON_VALUE was introduced in MySQL 8.0.21. MySQL 8.0.22 added YEAR to the RETURNING type list. The MySQL 8.4 and 9.7 branches currently document this function in the Reference Manual. MySQL 5.7 and MySQL 8.0.20 and earlier do not support JSON_VALUE.

## 1. What Is JSON_VALUE Used For?

JSON_VALUE takes a JSON document and a JSON path, then returns the value at the selected location. If needed, it converts the result to an SQL type such as DECIMAL, UNSIGNED, DATE, or CHAR.

Example:

~~~sql
SELECT JSON_VALUE(
    '{"customer":{"name":"Nguyen An","tier":"GOLD"}}',
    '$.customer.name'
) AS customer_name;
~~~

The result is the string Nguyen An.

Retrieve a numeric value and convert it to DECIMAL:

~~~sql
SELECT JSON_VALUE(
    '{"item":"Keyboard","price":"1299.90"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
) AS price;
~~~

The result is the SQL number 1299.90, which can be used in arithmetic comparisons:

~~~sql
SELECT
    JSON_VALUE('{"price":"1299.90"}', '$.price'
        RETURNING DECIMAL(10, 2)) * 2 AS double_price;
~~~

JSON_VALUE is especially useful when the application needs to:

- Compare JSON properties as numbers, dates, or strings.
- Standardize the return type rather than keeping a JSON value.
- Set explicit rules for missing or mistyped properties.
- Create a functional index to query by a scalar path inside JSON.

JSON_VALUE is intended for a single scalar value. If you need to retrieve an object, an array, or multiple elements at once, consider JSON_EXTRACT or JSON_TABLE.

## 2. Support Requirements by MySQL Version

JSON_VALUE is not available in every MySQL version. Check the actual server version before putting the function into schemas, views, queries, or migrations.

| Version | JSON_VALUE Support | Notes |
|---|---|---|
| MySQL 5.7 | No | Use JSON_EXTRACT, JSON_UNQUOTE, JSON operators, or a generated column |
| MySQL 8.0.0 to 8.0.20 | No | JSON_VALUE does not exist yet |
| MySQL 8.0.21 | Yes | First version introducing JSON_VALUE; RETURNING YEAR not yet supported |
| MySQL 8.0.22 and later | Yes | Added RETURNING YEAR |
| MySQL 8.4 LTS | Yes | Documented in the 8.4 Reference Manual |
| MySQL 9.7 | Yes | Documented in the 9.7 Reference Manual |

### 2.1. Checking Server Version

~~~sql
SELECT VERSION() AS mysql_version;
~~~

You can also check quickly with:

~~~sql
SHOW VARIABLES LIKE 'version';
~~~

If the environment runs multiple servers or replicas, check every node that might receive the query. A query valid on a newer primary may fail when the application routes it to an older replica.

### 2.2. Milestone 8.0.21

MySQL 8.0.21 introduced JSON_VALUE. A key goal of the function is strongly typed scalar extraction and simplifying index creation on JSON columns.

Starting in this version, you can create an index on a JSON_VALUE expression, for example:

~~~sql
CREATE TABLE inventory_demo (
    attributes JSON NOT NULL,
    INDEX ix_item_name (
        (JSON_VALUE(attributes, '$.name' RETURNING CHAR(40)))
    )
);
~~~

### 2.3. Milestone 8.0.22: RETURNING YEAR

MySQL 8.0.22 added YEAR to the types that can be specified in RETURNING.

Example:

~~~sql
SELECT JSON_VALUE(
    '{"manufactured_year":2024}',
    '$.manufactured_year'
    RETURNING YEAR
) AS manufactured_year;
~~~

YEAR does not accept one- or two-digit year values in the JSON_VALUE context. Store years in four-digit form and validate input data before converting.

### 2.4. Function Availability and Support Lifecycle Are Two Different Things

A version having JSON_VALUE does not mean that release branch is still within its support period. The MySQL 8.0 Release Notes currently record that the 8.0 branch reached End of Life in April 2026, after version 8.0.46.

When choosing a deployment version, verify both conditions:

1. Whether the version supports the syntax and features the application needs.
2. Whether the release branch still complies with your organization's support, patching, and operational policies.

For new deployments, prefer a MySQL branch still actively maintained under platform policy, such as 8.4 LTS or a current Innovation release matching operational requirements.

## 3. JSON_VALUE Syntax

General syntax:

~~~text
JSON_VALUE(
    json_doc,
    path
    [RETURNING type]
    [{NULL | ERROR | DEFAULT value} ON EMPTY]
    [{NULL | ERROR | DEFAULT value} ON ERROR]
)
~~~

It can be written on a single line:

~~~text
JSON_VALUE(json_doc, path [RETURNING type] [on_empty] [on_error])
~~~

Where:

- json_doc: the JSON document to read. The value must be valid JSON; if the expression is SQL NULL, the result is SQL NULL.
- path: the JSON path pointing to the location to retrieve. MySQL requires the path argument to be a string literal.
- RETURNING type: the SQL type to which the result is converted.
- ON EMPTY: behavior when the path finds no data.
- ON ERROR: behavior when the selected value cannot be returned as a scalar of the requested type or a conversion/truncation error occurs within the scope handled by the function.

A complete example:

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"25"}',
    '$.quantity'
    RETURNING UNSIGNED
    DEFAULT 0 ON EMPTY
    ERROR ON ERROR
) AS quantity;
~~~

The example above returns an unsigned integer. If the quantity property does not exist, the function returns 0. If the value exists but cannot be converted to UNSIGNED, the statement raises an error.

### 3.1. The Path Must Be a String Literal

JSON_VALUE requires the path argument to be a literal string in the SQL statement. Do not assume you can pass a column, variable, or dynamic parameter as the path.

Example using a literal:

~~~sql
SELECT JSON_VALUE(attributes, '$.customer.id' RETURNING UNSIGNED)
FROM order_event;
~~~

If the application needs to select a path based on user input, design a path whitelist and construct the appropriate SQL statement in the application layer. Never concatenate arbitrary paths directly from untrusted input.

### 3.2. JSON Paths Start with $

The $ character represents the root of the JSON document.

Example document:

~~~json
{
  "order": {
    "id": 501,
    "status": "PAID",
    "items": [
      {"sku": "KB-01", "quantity": 2},
      {"sku": "MS-02", "quantity": 1}
    ]
  }
}
~~~

Some paths:

| JSON path | Selected Value |
|---|---|
| $ | Entire document |
| $.order | The order object |
| $.order.id | Scalar 501 |
| $.order.status | Scalar PAID |
| $.order.items[0].sku | Scalar KB-01 |
| $.order.items[1].quantity | Scalar 1 |

JSON_VALUE works best with a path pointing to a scalar such as a number, string, boolean, or a value convertible to an SQL type. A path pointing to an object or array triggers ON ERROR handling.

## 4. RETURNING and Data Types

If RETURNING is omitted, JSON_VALUE returns VARCHAR(512).

RETURNING types supported in MySQL 8.4:

- FLOAT
- DOUBLE
- DECIMAL
- SIGNED
- UNSIGNED
- DATE
- TIME
- DATETIME
- YEAR
- CHAR
- JSON

These types correspond to the non-ARRAY types supported by CAST in the JSON_VALUE context. YEAR has been available since MySQL 8.0.22.

### 4.1. Strings with Default VARCHAR(512)

~~~sql
SELECT JSON_VALUE(
    '{"name":"Mechanical Keyboard"}',
    '$.name'
) AS product_name;
~~~

Without RETURNING, the return type is VARCHAR(512). The default character set is utf8mb4 and the collation is binary, so string comparisons are case-sensitive.

When specifying character set utf8mb4 for type CHAR, the server uses that character set's default collation, which is typically case-insensitive under default MySQL 8.0/8.4 configuration.

Example:

~~~sql
SELECT JSON_VALUE(
    '{"name":"Mechanical Keyboard"}',
    '$.name'
    RETURNING CHAR(80) CHARACTER SET utf8mb4
) AS product_name;
~~~

Choose a CHAR length suitable for the data domain if the value will be used in an index.

### 4.2. Signed and Unsigned Integers

~~~sql
SELECT
    JSON_VALUE('{"id":"-25"}', '$.id' RETURNING SIGNED)
        AS signed_id,
    JSON_VALUE('{"quantity":"25"}', '$.quantity' RETURNING UNSIGNED)
        AS quantity;
~~~

SIGNED fits signed numeric domains. UNSIGNED fits non-negative integers such as quantities or numeric identifiers.

Do not use UNSIGNED if data can be negative. If the value cannot be converted, ON ERROR determines the outcome.

### 4.3. DECIMAL for Money and Rates

~~~sql
SELECT JSON_VALUE(
    '{"unit_price":"1999.95"}',
    '$.unit_price'
    RETURNING DECIMAL(12, 2)
) AS unit_price;
~~~

Use DECIMAL when exact decimal arithmetic is needed, such as money, taxes, or rates. Do not use FLOAT/DOUBLE for monetary data if business logic requires decimal precision.

### 4.4. FLOAT and DOUBLE

~~~sql
SELECT
    JSON_VALUE('{"temperature":"36.5"}', '$.temperature'
        RETURNING FLOAT) AS temperature_float,
    JSON_VALUE('{"ratio":"0.875"}', '$.ratio'
        RETURNING DOUBLE) AS ratio_double;
~~~

FLOAT and DOUBLE are approximate numeric types. They fit measurement or scientific data where floating-point rounding error is acceptable.

### 4.5. DATE, TIME, and DATETIME

~~~sql
SELECT
    JSON_VALUE('{"date":"2026-11-19"}', '$.date'
        RETURNING DATE) AS event_date,
    JSON_VALUE('{"time":"09:30:00"}', '$.time'
        RETURNING TIME) AS event_time,
    JSON_VALUE('{"created_at":"2026-11-19 09:30:00"}', '$.created_at'
        RETURNING DATETIME) AS created_at;
~~~

JSON data must be in a format convertible to the corresponding date/time type. Malformed or invalid values can trigger ON ERROR.

### 4.6. JSON

RETURNING JSON returns the JSON type. This type is useful when you want to keep a scalar as a JSON value or continue passing it to another JSON function.

~~~sql
SELECT JSON_VALUE(
    '{"feature":true}',
    '$.feature'
    RETURNING JSON
) AS feature_value;
~~~

If the goal is boolean comparison, test the conversion and expression data type on your exact server version. If the goal is retrieving an object or array, use JSON_EXTRACT instead of JSON_VALUE.

## 5. ON EMPTY: When the Path Finds No Data

ON EMPTY controls the result when the JSON path matches no location in the document.

There are three options:

| Syntax | Behavior |
|---|---|
| NULL ON EMPTY | Returns SQL NULL; this is the default |
| DEFAULT value ON EMPTY | Returns the default value |
| ERROR ON EMPTY | Raises an error |

Example document without a discount property:

~~~sql
SELECT JSON_VALUE(
    '{"price":100}',
    '$.discount'
    RETURNING DECIMAL(8, 2)
    DEFAULT 0.00 ON EMPTY
) AS discount;
~~~

The result is 0.00.

If a property is required, use ERROR ON EMPTY:

~~~sql
SELECT JSON_VALUE(
    '{"price":100}',
    '$.customer_id'
    RETURNING UNSIGNED
    ERROR ON EMPTY
) AS customer_id;
~~~

The statement raises an error if the path has no data.

### 5.1. DEFAULT Must Match the Return Type

The DEFAULT value must convert appropriately to the RETURNING type.

~~~sql
SELECT JSON_VALUE(
    '{"name":"Keyboard"}',
    '$.sku'
    RETURNING CHAR(30)
    DEFAULT 'UNKNOWN' ON EMPTY
) AS sku;
~~~

For numeric types:

~~~sql
SELECT JSON_VALUE(
    '{"name":"Keyboard"}',
    '$.stock'
    RETURNING UNSIGNED
    DEFAULT 0 ON EMPTY
) AS stock;
~~~

Do not use a default value of the wrong type. If RETURNING is UNSIGNED, use a non-negative numeric default value.

### 5.2. ON EMPTY Does Not Handle the JSON null Literal

Distinguish two cases:

- Path does not exist: ON EMPTY is triggered.
- Path exists and the value is JSON null: JSON_VALUE returns SQL NULL.

Example:

~~~sql
SELECT
    JSON_VALUE('{"status":null}', '$.status'
        RETURNING CHAR(20) DEFAULT 'MISSING' ON EMPTY) AS explicit_null,
    JSON_VALUE('{}', '$.status'
        RETURNING CHAR(20) DEFAULT 'MISSING' ON EMPTY) AS missing_value;
~~~

Results:

- explicit_null is SQL NULL because the path exists and contains JSON null.
- missing_value is MISSING because the path does not exist and ON EMPTY is triggered.

If the application needs to distinguish JSON null from a missing property, check path existence using JSON_CONTAINS_PATH.

~~~sql
SELECT
    JSON_CONTAINS_PATH('{"status":null}', 'one', '$.status')
        AS status_exists,
    JSON_CONTAINS_PATH('{}', 'one', '$.status')
        AS missing_status_exists;
~~~

The results are 1 and 0 respectively.

## 6. ON ERROR: When a Scalar Cannot Be Returned as the Requested Type

ON ERROR controls value-processing errors recognized by JSON_VALUE, including:

- The path selects an object or array instead of a scalar.
- The path contains a wildcard or range leading to multiple result locations.
- The value cannot be converted to the RETURNING type.
- The value undergoes truncation during processing.

There are three options:

| Syntax | Behavior |
|---|---|
| NULL ON ERROR | Returns SQL NULL; this is the default |
| DEFAULT value ON ERROR | Returns the default value |
| ERROR ON ERROR | Raises an error |

### 6.1. NULL ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    NULL ON ERROR
) AS quantity;
~~~

The value many cannot be converted to UNSIGNED, so the result is SQL NULL. The conversion failure still emits a warning; NULL ON ERROR does not mean all signs of bad data disappear.

### 6.2. DEFAULT ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    DEFAULT 0 ON ERROR
) AS quantity;
~~~

If conversion fails, the result is 0.

Do not arbitrarily set DEFAULT just to make queries always return data. Default values can mask data-quality issues if the application does not monitor warnings or lack source-data validation.

### 6.3. ERROR ON ERROR

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"many"}',
    '$.quantity'
    RETURNING UNSIGNED
    ERROR ON ERROR
) AS quantity;
~~~

The statement raises an error when the value cannot be converted. This is the right choice when data must adhere to a strict schema and the caller needs to know immediately when data is invalid.

### 6.4. Path Pointing to an Object or Array

~~~sql
SELECT JSON_VALUE(
    '{"customer":{"id":101}}',
    '$.customer'
    RETURNING CHAR(100)
    ERROR ON ERROR
);
~~~

Path $.customer selects an object, not a scalar. ON ERROR is triggered.

If you need to retrieve the object:

~~~sql
SELECT JSON_EXTRACT(
    '{"customer":{"id":101}}',
    '$.customer'
) AS customer_object;
~~~

If you need to turn array elements into relational rows, consider JSON_TABLE.

### 6.5. Path Returning Multiple Locations

~~~sql
SELECT JSON_VALUE(
    '[{"id":10},{"id":20}]',
    '$[*].id'
    RETURNING UNSIGNED
    ERROR ON ERROR
);
~~~

The wildcard path matches multiple values. JSON_VALUE expects a single scalar, so multiple results trigger ON ERROR.

If you need all elements, use JSON_EXTRACT or JSON_TABLE:

~~~sql
SELECT JSON_EXTRACT(
    '[{"id":10},{"id":20}]',
    '$[*].id'
) AS ids;
~~~

## 7. Distinguishing JSON Input Errors from ON ERROR

ON ERROR is not a catch-all handler for every JSON-related error.

MySQL validates the JSON document and JSON path. If the JSON input or path is invalid, the server raises an SQL error without triggering ON ERROR.

Example illustrating an invalid JSON document:

~~~sql
SELECT JSON_VALUE(
    '{bad json',
    '$.id'
    RETURNING UNSIGNED
    NULL ON ERROR
);
~~~

This statement still raises an error because the JSON document is invalid. NULL ON ERROR does not turn a JSON syntax error into NULL.

A JSON column already saved successfully in MySQL always contains valid JSON. Invalid-input cases typically happen when passing a string from the application into the function or when processing a VARCHAR column containing unvalidated JSON text.

A syntactically invalid path also raises an SQL error. Validate paths with test cases before shipping to the application.

## 8. Order of ON EMPTY and ON ERROR

If both clauses are specified, ON EMPTY must come before ON ERROR.

Valid syntax:

~~~sql
SELECT JSON_VALUE(
    '{"price":"invalid"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
    DEFAULT 0.00 ON EMPTY
    ERROR ON ERROR
);
~~~

Invalid syntax:

~~~sql
SELECT JSON_VALUE(
    '{"price":"invalid"}',
    '$.price'
    RETURNING DECIMAL(10, 2)
    ERROR ON ERROR
    DEFAULT 0.00 ON EMPTY
);
~~~

Wrong order causes a syntax error. Keep a consistent convention in queries and code reviews.

### 8.1. Defaults of the Two Clauses

If ON EMPTY is not specified, the default behavior is NULL ON EMPTY.

If ON ERROR is not specified, the default behavior is NULL ON ERROR.

Example:

~~~sql
SELECT JSON_VALUE(
    '{"price":"49.95"}',
    '$.price'
    RETURNING DECIMAL(8, 2)
);
~~~

The statement above uses both defaults. When the path is missing or conversion fails, the function returns SQL NULL according to the respective rule; however, an invalid JSON document or path still raises an SQL error.

### 8.2. Conversion Warnings Still Need Monitoring

When a conversion error occurs, MySQL emits a warning even if NULL ON ERROR or DEFAULT ... ON ERROR is specified.

In development, you can check warnings immediately after the statement:

~~~sql
SELECT JSON_VALUE(
    '{"quantity":"not-a-number"}',
    '$.quantity'
    RETURNING UNSIGNED
    NULL ON ERROR
);

SHOW WARNINGS;
~~~

In the application, consider logging mistyped source data or rejecting records at the ingest layer. Do not rely on NULL ON ERROR as a substitute for data quality controls.

## 9. JSON_VALUE Compared to JSON_EXTRACT, ->, and ->>

These functions and operators all read data from JSON, yet have different result types and purposes.

| Tool | Result | Best Used When |
|---|---|---|
| JSON_EXTRACT(doc, path) | JSON value | Need to preserve JSON structure, object, or array |
| doc -> path | Equivalent to JSON_EXTRACT | Want shorthand when retrieving a JSON value |
| doc ->> path | JSON_UNQUOTE(JSON_EXTRACT(...)) | Need a string with JSON quotes stripped |
| JSON_VALUE(doc, path) | SQL scalar, default VARCHAR(512) or RETURNING type | Need a scalar value with an explicit SQL type |

Example of JSON_EXTRACT returning a quoted JSON string:

~~~sql
SELECT JSON_EXTRACT(
    '{"name":"Keyboard"}',
    '$.name'
) AS extracted_json;
~~~

The displayed result is "Keyboard" with JSON quotes.

JSON_UNQUOTE or the ->> operator returns the unquoted string:

~~~sql
SELECT
    JSON_UNQUOTE(JSON_EXTRACT('{"name":"Keyboard"}', '$.name'))
        AS unquoted_name,
    ('{"name":"Keyboard"}' ->> '$.name')
        AS operator_name;
~~~

JSON_VALUE can directly return an SQL type:

~~~sql
SELECT JSON_VALUE(
    '{"price":"49.95"}',
    '$.price'
    RETURNING DECIMAL(8, 2)
) AS price;
~~~

Aside from cases where JSON_VALUE returns NULL, an expression with a RETURNING type is conceptually equivalent to:

~~~sql
SELECT CAST(
    JSON_UNQUOTE(JSON_EXTRACT(json_doc, path))
    AS type
);
~~~

JSON_VALUE adds ON EMPTY and ON ERROR, making it explicit how missing paths and conversion errors are handled. JSON_VALUE's NULL behavior can differ from how CAST handles certain values; do not substitute mechanically if an existing query relies on specific NULL or warning behavior.

## 10. JSON_VALUE and Functional Indexes

A JSON column cannot be indexed directly like an ordinary scalar column. When an application frequently filters by a scalar path, you can create an index on a JSON_VALUE expression.

Functional key parts have existed since MySQL 8.0.13. Because JSON_VALUE was introduced in MySQL 8.0.21, combining both features to index JSON_VALUE requires MySQL 8.0.21 or later.

Example:

~~~sql
CREATE TABLE json_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (
        (JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED))
    ),
    INDEX ix_amount (
        (JSON_VALUE(attributes, '$.amount' RETURNING DECIMAL(10, 2)))
    ),
    INDEX ix_status (
        (JSON_VALUE(attributes, '$.status' RETURNING CHAR(16)))
    )
) ENGINE = InnoDB;
~~~

Each functional key part wraps its expression in an extra pair of parentheses inside the index declaration. In the example, three indexes extract three different scalars.

### 10.1. Loading Sample Data

~~~sql
INSERT INTO json_order_demo (order_id, attributes)
VALUES
(
    1001,
    JSON_OBJECT(
        'customer_id', 101,
        'amount', 125.50,
        'status', 'PAID'
    )
),
(
    1002,
    JSON_OBJECT(
        'customer_id', 102,
        'amount', 980.00,
        'status', 'PENDING'
    )
),
(
    1003,
    JSON_OBJECT(
        'customer_id', 101,
        'amount', 2500.00,
        'status', 'PAID'
    )
),
(
    1004,
    JSON_OBJECT(
        'customer_id', 103,
        'amount', 75.25,
        'status', 'CANCELLED'
    )
);
~~~

### 10.2. Querying with the Matching Expression

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.customer_id'
    RETURNING UNSIGNED
) = 101;
~~~

The expression in WHERE matches the ix_customer_id index expression: same JSON column, same path, and same RETURNING type.

Querying by amount:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.amount'
    RETURNING DECIMAL(10, 2)
) >= 1000.00;
~~~

Querying by status:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.status'
    RETURNING CHAR(16)
) = 'PAID';
~~~

### 10.3. Verifying Index Usage with EXPLAIN

~~~sql
EXPLAIN
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(
    attributes,
    '$.customer_id'
    RETURNING UNSIGNED
) = 101;
~~~

Check the possible_keys and key columns in the execution plan. If the optimizer selects ix_customer_id, the key column displays that index name.

Having an index does not mean every query is forced to use it. The optimizer may choose a table scan when the table is small, the filter condition is not selective, or using the index costs more.

### 10.4. The Query Expression Must Match the Index Expression

When creating a functional index, use the exact same JSON path and RETURNING type in WHERE.

Example key part in the index declaration:

~~~text
INDEX ix_customer_id (
    (JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED))
)
~~~

Matching query:

~~~sql
SELECT order_id
FROM json_order_demo
WHERE JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED) = 101;
~~~

If the query omits RETURNING or changes it to CHAR, the expression no longer matches the index expression. Do not assume the optimizer will automatically rewrite all variations into the same functional key part.

For string expressions, character set and collation can also affect expression matching. Verify with EXPLAIN on the exact target version and schema.

### 10.5. When to Use a Generated Column?

A generated column remains useful when:

- You want to name the extracted JSON property so queries are easier to read.
- You want to reuse the same scalar across many queries.
- You need compatibility with versions lacking JSON_VALUE.
- You want to enforce data types, NULLability, or constraints in the schema.

Example on MySQL with JSON_VALUE:

~~~sql
CREATE TABLE json_order_generated_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    customer_id BIGINT UNSIGNED
        GENERATED ALWAYS AS (
            JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED)
        ) STORED,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (customer_id)
) ENGINE = InnoDB;
~~~

A generated column makes the extracted scalar explicit and allows querying by the column name customer_id.

## 11. Alternatives on MySQL Older Than 8.0.21

If the server does not yet support JSON_VALUE, you can use the JSON functions already available in MySQL 5.7 and MySQL 8.0 releases prior to 8.0.21.

### 11.1. JSON_EXTRACT

~~~sql
SELECT JSON_EXTRACT(
    '{"customer_id":101}',
    '$.customer_id'
) AS customer_id_json;
~~~

JSON_EXTRACT returns a JSON value. When comparing numbers or strings, understand JSON types and MySQL's comparison rules.

### 11.2. JSON_UNQUOTE Combined with CAST

~~~sql
SELECT CAST(
    JSON_UNQUOTE(
        JSON_EXTRACT('{"customer_id":"101"}', '$.customer_id')
    )
    AS UNSIGNED
) AS customer_id;
~~~

This approach mirrors the type conversion part of JSON_VALUE, but lacks JSON_VALUE's ON EMPTY and ON ERROR clauses.

If a default is needed when the path is missing, you can use COALESCE:

~~~sql
SELECT COALESCE(
    CAST(
        JSON_UNQUOTE(
            JSON_EXTRACT('{"customer_id":"101"}', '$.customer_id')
        )
        AS UNSIGNED
    ),
    0
) AS customer_id;
~~~

COALESCE only handles NULL in the result. It does not fully replace JSON_VALUE's conversion error and warning rules.

### 11.3. Generated Column on Older Versions

~~~sql
CREATE TABLE legacy_json_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    customer_id BIGINT UNSIGNED
        GENERATED ALWAYS AS (
            CAST(
                JSON_UNQUOTE(
                    JSON_EXTRACT(attributes, '$.customer_id')
                )
                AS UNSIGNED
            )
        ) STORED,
    PRIMARY KEY (order_id),
    INDEX ix_customer_id (customer_id)
) ENGINE = InnoDB;
~~~

A generated column enables creating an index on a scalar extracted from JSON. Test missing properties, JSON null, and mistyped data because CAST may emit warnings or return NULL per conversion rules.

### 11.4. Choosing a Solution by Version

| Environment | Implementation Approach |
|---|---|
| MySQL 5.7 | JSON_EXTRACT, JSON_UNQUOTE, CAST, generated column |
| MySQL 8.0.0–8.0.20 | JSON_EXTRACT, JSON_UNQUOTE, CAST, generated column |
| MySQL 8.0.21 | JSON_VALUE; functional index on JSON_VALUE expression |
| MySQL 8.0.22 and later | JSON_VALUE and RETURNING YEAR |
| MySQL 8.4 / 9.7 | JSON_VALUE, RETURNING, and index expressions per version documentation |

Do not deploy queries containing JSON_VALUE to servers older than 8.0.21. Check versions before migrations and in the release pipeline.

## 12. Common Mistakes and Misconceptions

| Mistake or Misconception | Reality | How to Handle |
|---|---|---|
| JSON_VALUE exists since MySQL 8.0.0 | The function was introduced in 8.0.21 | Check VERSION() |
| MySQL 5.7 supports JSON_VALUE | Not supported | Use JSON_EXTRACT and CAST |
| RETURNING YEAR exists since 8.0.21 | YEAR was added in 8.0.22 | Check version if using YEAR |
| JSON_VALUE returns a whole JSON document | The function targets a single scalar | Use JSON_EXTRACT for objects/arrays |
| A missing path is a conversion error | That is ON EMPTY | Choose NULL, DEFAULT, or ERROR ON EMPTY |
| JSON null is the same as a missing path | JSON null returns SQL NULL; missing path triggers ON EMPTY | Use JSON_CONTAINS_PATH if distinction is needed |
| ON ERROR catches all JSON errors | Invalid JSON documents/paths raise separate SQL errors | Validate JSON and paths beforehand |
| NULL ON ERROR emits no warnings | Conversion errors still emit warnings | Monitor warnings and data quality |
| ON ERROR can precede ON EMPTY | That order is a syntax error | Place ON EMPTY before ON ERROR |
| Default return type is JSON | The default is VARCHAR(512) | Specify RETURNING when an explicit type is needed |
| Path can be passed via an arbitrary variable | Path must be a string literal | Whitelist paths in the application |
| A JSON column can be indexed directly | Requires an expression index or generated column | Use a JSON_VALUE functional index or generated column |
| Having an index guarantees queries use it | The optimizer decides based on cost | Check EXPLAIN |
| Functional index does not need matching expressions | Path and RETURNING type must match the index expression | Use the identical expression in WHERE |
| Use UNSIGNED for all numeric values | Negative values are incompatible | Choose SIGNED or DECIMAL per data domain |
| DEFAULT ON ERROR replaces data validation | Bad values may be silently masked as defaults | Monitor warnings and validate source data |

## 13. Workflow for Adopting JSON_VALUE in Applications

When adding JSON_VALUE to a query or schema:

1. Check the MySQL version of every server receiving the query.
2. Determine whether the path points to a scalar or an object/array.
3. Determine the true SQL type of the value: CHAR, UNSIGNED, DECIMAL, DATE, or another type.
4. Specify RETURNING explicitly if the value is used in comparisons or calculations.
5. Decide whether a missing path is allowed.
6. Choose ON EMPTY matching the data contract.
7. Choose ON ERROR to raise an error, return NULL, or use DEFAULT.
8. Remember that JSON null returns SQL NULL and does not trigger ON EMPTY.
9. Inspect warnings after conversion errors.
10. If queries frequently filter by the path, consider a functional index or generated column.
11. Use the same path, RETURNING type, and character set/collation when querying the indexed expression.
12. Run EXPLAIN to verify the optimizer selects the index.
13. Test documents with missing properties, null, wrong types, arrays/objects, and invalid JSON input.
14. Verify compatibility on replicas, staging environments, and migration pipelines.

Decision flowchart:

~~~mermaid
flowchart TD
    A[Read JSON property] --> B{MySQL 8.0.21 or later?}
    B -->|No| C[JSON_EXTRACT + CAST or generated column]
    B -->|Yes| D{Does path return a scalar?}
    D -->|No| E[JSON_EXTRACT or JSON_TABLE]
    D -->|Yes| F[Choose RETURNING type]
    F --> G{Can path be missing?}
    G -->|Yes| H[Choose ON EMPTY]
    G -->|No| I[ERROR ON EMPTY]
    H --> J[Choose ON ERROR]
    I --> J
    J --> K{Filtered frequently in queries?}
    K -->|Yes| L[Functional index or generated column]
    K -->|No| M[Use directly in query]
    L --> N[EXPLAIN and test]
    M --> N
    C --> N
    E --> N
~~~

## 14. Practice Exercises

### Exercise 1: Check Version Support

Use SELECT VERSION() to check the server. Determine whether JSON_VALUE is supported. Explain the differences between MySQL 8.0.20, 8.0.21, and 8.0.22.

### Exercise 2: Extract Strings

Given a document containing a customer's name and email. Use JSON_VALUE to retrieve each property with RETURNING CHAR.

### Exercise 3: Convert Numbers

Given a quantity property stored as a string. Use RETURNING UNSIGNED and test a valid value, a negative value, and a non-numeric string.

### Exercise 4: ON EMPTY

Create a document missing the discount property. Compare NULL ON EMPTY, DEFAULT 0 ON EMPTY, and ERROR ON EMPTY.

### Exercise 5: JSON null

Compare a document where status is JSON null with a document missing status. Use JSON_CONTAINS_PATH to distinguish the two cases.

### Exercise 6: ON ERROR

Try converting the string invalid-number to DECIMAL. Compare NULL ON ERROR, DEFAULT 0 ON ERROR, and ERROR ON ERROR. Check warnings after the statement.

### Exercise 7: Objects and Arrays

Use JSON_VALUE with paths pointing to an object, an array, and a multi-result wildcard. Then rewrite them using JSON_EXTRACT.

### Exercise 8: Clause Order

Write a JSON_VALUE expression with both ON EMPTY and ON ERROR. Swap the order of the two clauses to observe the syntax error.

### Exercise 9: Functional Index

Create a table with a JSON attributes column, create an index on JSON_VALUE(attributes, '$.customer_id' RETURNING UNSIGNED), load data, and use EXPLAIN to inspect a query filtering by customer_id.

### Exercise 10: Legacy-Compatible Generated Column

Rewrite Exercise 9 using a generated column with JSON_EXTRACT, JSON_UNQUOTE, and CAST. Compare querying and schema management.

### Exercise 11: Distinguish Return Types

Compare JSON_EXTRACT, ->>, default JSON_VALUE, and JSON_VALUE RETURNING DECIMAL on the same property.

### Exercise 12: Design a Data Contract

Design rules for three JSON properties: required customer_id, optional discount, and created_at which must be a DATETIME. Choose RETURNING, ON EMPTY, and ON ERROR for each property and explain your choices.

## Conclusion

JSON_VALUE extracts a scalar from a JSON document and can convert the result to an SQL type using RETURNING. The function was introduced in MySQL 8.0.21; RETURNING YEAR has been supported since 8.0.22. If RETURNING is omitted, the default result type is VARCHAR(512).

ON EMPTY handles paths that find no data; ON ERROR handles objects/arrays, multiple results, conversion failures, or truncation within the function's scope. JSON null returns SQL NULL, while invalid JSON documents or paths raise separate SQL errors. When declaring both clauses, ON EMPTY must precede ON ERROR.

For queries frequently filtering by a scalar inside JSON, you can create a functional index on the JSON_VALUE expression and verify it with EXPLAIN. When compatibility with servers older than 8.0.21 is required, use JSON_EXTRACT combined with JSON_UNQUOTE, CAST, or a generated column.

## References

- MySQL 8.4 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/8.4/en/json-search-functions.html
- MySQL 9.7 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/9.7/en/json-search-functions.html
- MySQL 8.0 Reference Manual — Functions That Search JSON Values: https://dev.mysql.com/doc/refman/8.0/en/json-search-functions.html
- MySQL 8.0 Release Notes — Changes in MySQL 8.0.21: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-21.html
- MySQL 8.0 Release Notes — Changes in MySQL 8.0.22: https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-22.html
- MySQL 8.4 Reference Manual — CREATE INDEX Statement and Functional Key Parts: https://dev.mysql.com/doc/refman/8.4/en/create-index.html
- MySQL 8.4 Reference Manual — Generated Columns and JSON Indexing: https://dev.mysql.com/doc/refman/8.4/en/create-table-secondary-indexes.html
- MySQL 8.4 Reference Manual — JSON Data Type and JSON Path Syntax: https://dev.mysql.com/doc/refman/8.4/en/json.html
