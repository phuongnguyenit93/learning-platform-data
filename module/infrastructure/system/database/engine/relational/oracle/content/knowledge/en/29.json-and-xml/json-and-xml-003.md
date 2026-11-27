# SQL/JSON Path, JSON_VALUE, JSON_QUERY, and JSON_EXISTS

Oracle provides SQL/JSON functions to query JSON data directly inside SQL statements. Instead of fetching an entire JSON document into the application and parsing it manually, the database can locate a property, convert a JSON value to a SQL type, return a JSON object/array, or check whether a path exists.

Three functions to distinguish:

- **JSON_VALUE**: extracts a scalar value from JSON and converts it to a SQL type such as VARCHAR2 or NUMBER.
- **JSON_QUERY**: extracts a JSON object or array and returns it as JSON text/LOB.
- **JSON_EXISTS**: checks whether a JSON path matches at least one value; typically used in WHERE.

These functions use a **SQL/JSON path expression** to specify the target location. A path has its own syntax, starting from the root with `$`, traversing object properties, array elements, wildcards, and filters. Understanding paths, return types, and behavior when data is missing helps avoid confusing SQL NULL with JSON null, prevents errors when a path returns multiple values, and lets you write queries that can leverage indexes.

This lesson uses Oracle Database 19c, with JSON stored in VARCHAR2 or CLOB columns. Topics include path syntax, lax/strict mode, the three query functions, PASSING, ON ERROR/ON EMPTY, JSON null, filtering data, indexing, a hands-on lab, and common errors.

## 1. JSON in Oracle Database

Oracle 19c stores JSON in SQL data types such as VARCHAR2, CLOB, BLOB, or other types appropriate to version limits. Data is stored as text/bytes; Oracle validates and queries the content using SQL/JSON functions.

Example JSON document:

~~~json
{
  "orderId": 501,
  "customer": {
    "id": 101,
    "name": "Nguyễn An"
  },
  "status": "PAID",
  "total": 1250.5,
  "items": [
    {
      "sku": "KB-01",
      "name": "Bàn phím",
      "quantity": 2,
      "price": 500
    },
    {
      "sku": "MS-02",
      "name": "Chuột",
      "quantity": 1,
      "price": 250.5
    }
  ],
  "note": null
}
~~~

JSON paths retrieve values such as:

| Content | SQL/JSON path |
| --- | --- |
| Order ID | $.orderId |
| Customer name | $.customer.name |
| First element of items | $.items[0] |
| SKU of all items | $.items[*].sku |
| Note | $.note |

JSON arrays use 0-based indexing. This differs from typical nested table or VARRAY indexes in PL/SQL, which usually start at 1.

### 1.1. Validating a JSON Column

In Oracle 19c, you can add a CHECK constraint with the IS JSON condition:

~~~sql
CREATE TABLE orders_json (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT orders_json_payload_ck
        CHECK (payload IS JSON)
);
~~~

The constraint prevents content that is not valid JSON from being stored in the column. If the column can be NULL, consider NOT NULL separately because a CHECK constraint does not automatically forbid SQL NULL.

You can use VARCHAR2 instead of CLOB when documents are small and fit within type limits. CLOB suits large documents. BLOB can store JSON as bytes, but must adhere to a JSON encoding supported by Oracle; in practice, use UTF-8 for JSON exchange.

### 1.2. Checking Existing Data

~~~sql
SELECT order_id
FROM orders_json
WHERE payload IS NOT JSON;
~~~

This query is useful when inspecting legacy tables without a constraint. For columns containing SQL NULL, the IS NOT JSON condition may not evaluate to TRUE like an invalid JSON string; check NULL separately:

~~~sql
SELECT order_id
FROM orders_json
WHERE payload IS NULL
   OR payload IS NOT JSON;
~~~

## 2. SQL/JSON Path Expressions

A SQL/JSON path is an expression indicating a location inside a JSON document. A path normally starts with the `$` symbol representing the JSON root.

### 2.1. Root and Object Members

~~~text
$
$.orderId
$.customer
$.customer.name
$.customer.id
~~~

- `$` selects the entire document.
- `$.customer` selects the `customer` property at the root.
- `$.customer.name` navigates further into the `name` property of the `customer` object.

Member names are case-sensitive. The path `$.customer.name` differs from `$.Customer.Name`.

### 2.2. Array Index

~~~text
$.items[0]
$.items[1].sku
$.items[0].quantity
~~~

Array indexes start at 0. `$.items[0]` is the first element; `$.items[1]` is the second element.

If the index does not exist, the path has no match. Subsequent SQL behavior depends on the function called and ON ERROR/ON EMPTY clauses.

### 2.3. Wildcards

~~~text
$.items[*]
$.items[*].sku
$.customer.*
~~~

- `[*]` selects all elements of an array.
- `.*` selects the members of an object.

Wildcards can return multiple values. JSON_VALUE normally requires a single scalar; JSON_QUERY can return an object/array or multiple results when using a wrapper; JSON_EXISTS only needs to know whether a match exists.

### 2.4. Member Names with Special Characters

If a property name contains dots, spaces, or characters requiring quoting, enclose the member name in double quotes per path syntax:

~~~text
$."customer-name"
$."display name"
~~~

Do not confuse double quotes inside the path with SQL string quotes. When writing the path in SQL, the entire path remains a string literal.

### 2.5. Filter Expressions

A filter is placed after a path step using a question mark and parentheses:

~~~text
$.items[*]?(@.quantity > 1)
$.items[*]?(@.sku == "KB-01")
~~~

Inside the filter:

- `@` represents the current element being evaluated.
- `@.quantity` retrieves the `quantity` property of the current element.
- Comparison operators test the element's value.

Example of JSON_EXISTS using a filter:

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity > 1)'
);
~~~

The query returns orders that have at least one item with quantity greater than 1.

### 2.6. Lax and Strict Mode

Oracle SQL/JSON paths default to lax mode. Lax mode allows flexible conversions between objects and arrays, such as automatically wrapping or unwrapping array layers in specified situations.

You can specify strict mode in a path:

~~~text
lax $.items[*].sku
strict $.items[*].sku
~~~

Strict mode requires tighter structural matching. A path that matches in lax mode may fail to match in strict mode if the structural type is not as expected.

When writing APIs, know whether your JSON structure is stable. If document schemas are tightly controlled, strict paths can help catch structural mismatches. With data from heterogeneous sources, lax mode can be convenient, but monitor results and errors carefully.

### 2.7. Path Variables

Paths can use variables passed via PASSING:

~~~text
$.items[*]?(@.sku == $wantedSku)
~~~

Variable names in paths begin with `$`. Values are bound from SQL expressions in the PASSING clause:

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $wantedSku)'
    PASSING 'KB-01' AS "wantedSku"
);
~~~

The variable name in the path and the alias after AS must match according to SQL/JSON variable naming rules. Use PASSING to pass values rather than concatenating input strings into the path or SQL text.

## 3. JSON_VALUE: Extracting a Scalar as a SQL Type

JSON_VALUE extracts a scalar value from a JSON document and converts it to the requested SQL type.

General syntax:

~~~sql
JSON_VALUE(
    json_expression,
    path_expression
    [RETURNING sql_type]
    [NULL ON ERROR | ERROR ON ERROR | DEFAULT value ON ERROR]
    [NULL ON EMPTY | ERROR ON EMPTY | DEFAULT value ON EMPTY]
)
~~~

ON ERROR and ON EMPTY options depend on syntax/version and placement in the call. In Oracle 19c, check the SQL Language Reference when using default expressions or special return types.

### 3.1. Extracting a String

~~~sql
SELECT
    JSON_VALUE(payload, '$.status') AS order_status
FROM orders_json;
~~~

By default, JSON_VALUE returns VARCHAR2 if RETURNING is omitted. For a string scalar, the result is the string content converted to SQL type.

### 3.2. Extracting a Number

~~~sql
SELECT
    JSON_VALUE(
        payload,
        '$.total'
        RETURNING NUMBER
    ) AS total_amount
FROM orders_json;
~~~

RETURNING NUMBER requires that the JSON value be convertible to NUMBER. If the data is not a number or the path returns an object/array, error handling depends on ON ERROR.

### 3.3. Extracting Date/Time

If JSON stores date/time as an ISO string, extract it as VARCHAR2 and convert using an explicit format:

~~~sql
SELECT TO_TIMESTAMP_TZ(
           JSON_VALUE(payload, '$.createdAt'),
           'YYYY-MM-DD"T"HH24:MI:SS.FF TZH:TZM'
       ) AS created_at
FROM orders_json;
~~~

Do not rely on the default NLS_DATE_FORMAT to convert a JSON string with a fixed format. If the API stores dates as epoch timestamps or a custom format, define the corresponding conversion rule.

### 3.4. JSON_VALUE Only Returns Scalars

JSON_VALUE fits strings, numbers, booleans with SQL mapping rules, and JSON null. It is not meant to return entire objects or arrays.

Examples:

~~~sql
JSON_VALUE(payload, '$.customer.name')
JSON_VALUE(payload, '$.items[0].sku')
~~~

However, paths like `$.customer` or `$.items` select objects/arrays, not scalars. Default ON ERROR behavior may turn the result into SQL NULL; if you need to detect shape mismatches, use ERROR ON ERROR.

### 3.5. Handling Paths with No Result

By default, JSON_VALUE uses NULL ON ERROR and NULL ON EMPTY in their respective cases. This is convenient for queries tolerating optional fields, but can mask malformed data.

~~~sql
SELECT
    JSON_VALUE(
        payload,
        '$.customer.id'
        RETURNING NUMBER
        ERROR ON ERROR
        NULL ON EMPTY
    ) AS customer_id
FROM orders_json;
~~~

This example raises an error if the document/path has a conversion error or invalid structure per ON ERROR, while returning NULL if the member does not exist per ON EMPTY.

### 3.6. DEFAULT ON ERROR

You can specify a default value when an error occurs:

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.priority'
           RETURNING NUMBER
           DEFAULT 0 ON ERROR
       ) AS priority
FROM orders_json;
~~~

Only use DEFAULT when the fallback value makes business sense. If JSON contains `"high"` when a NUMBER is expected, silently turning it into 0 can hide corrupt data. For critical data, ERROR ON ERROR usually catches errors sooner.

### 3.7. JSON null and SQL NULL

JSON has its own `null` literal. When JSON_VALUE extracts a JSON null value, Oracle maps it to SQL NULL.

Therefore, any of the following cases can produce SQL NULL from JSON_VALUE:

- The property does not exist.
- The property exists with a JSON `null` value.
- A path/conversion error occurred and ON ERROR selects NULL.

If you need to distinguish whether a member exists, use JSON_EXISTS. JSON_EXISTS can return TRUE for a path pointing to an existing property with JSON null, whereas JSON_VALUE returns SQL NULL.

## 4. JSON_QUERY: Extracting an Object or Array

JSON_QUERY extracts a JSON object or array and returns the JSON content. It is the right function when you want a branch of the document without converting it to a SQL scalar.

General syntax:

~~~sql
JSON_QUERY(
    json_expression,
    path_expression
    [RETURNING VARCHAR2 | CLOB | BLOB]
    [WITH WRAPPER | WITHOUT WRAPPER | WITH CONDITIONAL WRAPPER]
    [KEEP QUOTES | OMIT QUOTES]
    [ON ERROR]
)
~~~

Check the SQL Language Reference for your Oracle release for exact option details and return types. For large documents, choose CLOB to avoid small SQL string limits.

### 4.1. Extracting the customer Object

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.customer'
           RETURNING CLOB
       ) AS customer_json
FROM orders_json;
~~~

The result is a JSON object, for example:

~~~json
{"id":101,"name":"Nguyễn An"}
~~~

### 4.2. Extracting the items Array

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.items'
           RETURNING CLOB
       ) AS items_json
FROM orders_json;
~~~

The result is a JSON array preserving the item structures.

### 4.3. Returning Multiple Values with WITH WRAPPER

A wildcard path can match multiple values:

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.items[*].sku'
           WITH WRAPPER
           RETURNING CLOB
       ) AS sku_array
FROM orders_json;
~~~

WITH WRAPPER wraps matching results into a JSON array. This is useful when a path selects multiple individual scalars/objects but the API needs a single JSON document.

Do not confuse WITH WRAPPER with JSON_VALUE: the wrapper turns the result set into a JSON array for JSON_QUERY to return, while JSON_VALUE remains a scalar extraction function.

### 4.4. WITHOUT WRAPPER

WITHOUT WRAPPER requires the result to fit a single JSON object/array per function rules. If the path matches multiple items without a wrapper, an error may be raised or handled per ON ERROR. When unsure of match count, use WITH WRAPPER or narrow the path to select a single structure.

### 4.5. KEEP QUOTES and OMIT QUOTES

Quote options affect how JSON_QUERY returns scalar strings in supported cases. By default, JSON strings must retain double quotes to remain valid JSON. OMIT QUOTES can strip quotes in eligible cases, though the result is no longer a complete JSON string in the same way. Only use it when the caller expects that exact format.

### 4.6. JSON_QUERY Is Not for Ordinary Scalar Extraction

If you need a numeric value for addition, comparison, or joining, use JSON_VALUE RETURNING NUMBER. JSON_QUERY is suitable for extracting an object/array or a JSON structure to forward to an application.

## 5. JSON_EXISTS: Checking Path Existence

JSON_EXISTS is a SQL condition returning TRUE when a path expression matches at least one value, and FALSE when it does not. It commonly appears in WHERE clauses to filter JSON documents.

Syntax:

~~~sql
JSON_EXISTS(
    json_expression,
    path_expression
    [PASSING expr AS "var_name" ...]
    [ERROR ON ERROR]
)
~~~

### 5.1. Checking Member Existence

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.customer.id');
~~~

The query returns documents where the `customer.id` path matches.

### 5.2. Checking an Array Element

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.items[0]');
~~~

The condition evaluates to true if the first element of `items` exists along the path.

### 5.3. Checking Values with a Filter

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

The filter is evaluated for array elements. JSON_EXISTS returns TRUE if at least one item has quantity greater than or equal to 2.

### 5.4. PASSING to Bind Values

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $sku)'
    PASSING :p_sku AS "sku"
);
~~~

`:p_sku` is a SQL bind variable. Its value is assigned to the path variable `$sku`. This is a safe and clear way to search for a dynamic SKU.

### 5.5. JSON null Is Still an Existing Value

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(o.payload, '$.note');
~~~

If a document has `"note": null`, the path `$.note` still exists, so JSON_EXISTS returns TRUE. Meanwhile:

~~~sql
JSON_VALUE(payload, '$.note')
~~~

returns SQL NULL. This is an important distinction between checking presence and extracting a scalar value.

### 5.6. Using NOT JSON_EXISTS

~~~sql
SELECT order_id
FROM orders_json o
WHERE NOT JSON_EXISTS(o.payload, '$.shipping.address');
~~~

The query finds documents lacking the `shipping.address` path. If JSON data is malformed or an expression errors, define explicit ON ERROR behavior and IS JSON constraints; do not use NOT JSON_EXISTS as a substitute for document validation.

## 6. Comparing the Three Functions

| Question | Function to Use | Result Type |
| --- | --- | --- |
| Extract customer name as VARCHAR2 | JSON_VALUE | SQL scalar |
| Extract total amount as NUMBER | JSON_VALUE RETURNING NUMBER | SQL scalar |
| Extract the entire customer object | JSON_QUERY | JSON object |
| Extract the items array | JSON_QUERY | JSON array |
| Extract all SKUs into one JSON array | JSON_QUERY WITH WRAPPER | JSON array |
| Find documents containing customer.id | JSON_EXISTS | TRUE/FALSE condition |
| Find documents with item quantity > 2 | JSON_EXISTS with filter | TRUE/FALSE condition |
| Distinguish missing field from JSON null | JSON_EXISTS combined with JSON_VALUE | Condition + scalar |

Example using all three in a single query:

~~~sql
SELECT
    o.order_id,
    JSON_VALUE(o.payload, '$.customer.name') AS customer_name,
    JSON_VALUE(o.payload, '$.total' RETURNING NUMBER) AS total_amount,
    JSON_QUERY(o.payload, '$.items' RETURNING CLOB) AS items_json
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

The query retrieves only orders with at least one item of quantity 2 or more, while projecting customer name, total amount, and the entire items array.

## 7. ON ERROR and ON EMPTY

These two clauses handle two different situations:

- ON ERROR: handles errors during JSON/path evaluation or value conversion, depending on the function.
- ON EMPTY: handles the case where the path finds no value.

### 7.1. JSON_VALUE Defaults

When unspecified, JSON_VALUE typically uses NULL ON ERROR and NULL ON EMPTY. This prevents a query from failing because one document is missing a field, but can make corrupt data look like missing data.

### 7.2. ERROR ON ERROR

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.total'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM orders_json;
~~~

If `total` cannot be converted to NUMBER or the path returns an incompatible type, the query raises an error instead of returning NULL.

### 7.3. NULL ON EMPTY

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.optionalField'
           NULL ON EMPTY
       )
FROM orders_json;
~~~

A non-existent field is treated as optional and returns SQL NULL. If the field is mandatory, consider ERROR ON EMPTY or checking with JSON_EXISTS.

### 7.4. DEFAULT ON EMPTY

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.priority'
           RETURNING NUMBER
           DEFAULT 0 ON EMPTY
       )
FROM orders_json;
~~~

DEFAULT ON EMPTY fits when the data contract clearly defines a default value for a missing field. Do not use it to mask type errors; that is the role of ON ERROR.

### 7.5. Distinguishing Missing Fields, JSON null, and Type Errors

Example JSON:

~~~json
{
  "a": 10,
  "b": null,
  "c": "not-a-number"
}
~~~

Conceptual results:

| Path | JSON_EXISTS | JSON_VALUE RETURNING NUMBER |
| --- | --- | --- |
| $.a | TRUE | 10 |
| $.b | TRUE | SQL NULL |
| $.missing | FALSE | SQL NULL when ON EMPTY is NULL |
| $.c | TRUE | conversion error or chosen ON ERROR behavior |

To distinguish `b` from `missing`, combine JSON_EXISTS and JSON_VALUE. To distinguish a type mismatch from NULL, use ERROR ON ERROR or validate schema/contract upfront.

## 8. SQL/JSON Path Filters in Detail

Filter expressions let you select elements based on JSON content conditions.

### 8.1. Numeric Comparisons

~~~text
$.items[*]?(@.quantity > 1)
$.items[*]?(@.price <= 500)
~~~

### 8.2. String Comparisons

~~~text
$.items[*]?(@.sku == "KB-01")
$.items[*]?(@.name != "Chuột")
~~~

String values in paths use JSON-style double quotes. The SQL string containing the path can still use outer single quotes.

### 8.3. Combining Conditions

~~~text
$.items[*]?(@.quantity >= 2 && @.price < 1000)
~~~

The `&&` operator represents AND in a filter. You can use logical operators supported by SQL/JSON paths to combine conditions; exact syntax should follow Oracle's SQL/JSON path language.

### 8.4. PASSING Multiple Variables

~~~sql
SELECT order_id
FROM orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= $minQty && @.price <= $maxPrice)'
    PASSING :p_min_qty AS "minQty",
            :p_max_price AS "maxPrice"
);
~~~

PASSING keeps the static path separate from search values. Input data is bound rather than concatenated into the path string.

### 8.5. Do Not Turn Paths into SQL Injection

Do not concatenate user strings into SQL statements or path expressions:

~~~sql
-- Avoid building SQL text from untrusted input.
-- Use bind variables and PASSING instead.
~~~

If an application lets users choose fields, whitelist the supported paths. PASSING binds comparison values; it does not automatically make an arbitrary path safe.

## 9. Querying JSON in WHERE, SELECT, and JOIN

### 9.1. Filtering by Scalar

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

JSON_VALUE converts `status` to VARCHAR2 for comparison with a SQL string.

### 9.2. Filtering by Number

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.total'
          RETURNING NUMBER
          ERROR ON ERROR
      ) >= 1000;
~~~

RETURNING NUMBER avoids comparing numbers as strings, where lexicographical order can differ from numerical order.

### 9.3. Joining with Relational Tables

~~~sql
SELECT
    o.order_id,
    c.customer_name,
    JSON_VALUE(o.payload, '$.total' RETURNING NUMBER) AS total_amount
FROM orders_json o
JOIN customers c
  ON c.customer_id =
     JSON_VALUE(o.payload, '$.customer.id' RETURNING NUMBER);
~~~

JSON_VALUE allows using a JSON field as a join key. However, if the field is an important relational key, consider storing the key in a dedicated relational column or creating a virtual column/index to avoid repeated parsing and support constraints.

### 9.4. JSON_QUERY to Return a Document Branch

~~~sql
SELECT
    order_id,
    JSON_QUERY(payload, '$.customer' RETURNING CLOB) AS customer_json
FROM orders_json;
~~~

The application can receive the JSON object without the database converting it into multiple SQL columns.

### 9.5. JSON_TABLE When Multiple Columns/Rows Are Needed

JSON_TABLE is another SQL/JSON function useful when projecting multiple fields or unnesting an array into relational rows:

~~~sql
SELECT
    o.order_id,
    jt.sku,
    jt.quantity,
    jt.price
FROM orders_json o,
     JSON_TABLE(
         o.payload,
         '$.items[*]'
         COLUMNS (
             sku VARCHAR2(30) PATH '$.sku',
             quantity NUMBER PATH '$.quantity',
             price NUMBER PATH '$.price'
         )
     ) jt;
~~~

JSON_VALUE suits one scalar at a time; JSON_QUERY suits a JSON structure; JSON_EXISTS suits condition checks; JSON_TABLE suits transforming JSON structures into SQL rows/columns.

## 10. Indexes for JSON_VALUE and JSON Queries

If queries frequently filter on a JSON scalar, a function-based index on JSON_VALUE can help Oracle avoid parsing the full document for every row.

### 10.1. Function-Based Index

~~~sql
CREATE INDEX orders_json_status_ix
ON orders_json (
    JSON_VALUE(
        payload,
        '$.status'
        RETURNING VARCHAR2(20)
    )
);
~~~

The query should use an expression compatible with the index expression:

~~~sql
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

The return type and path must match how the index is defined. The optimizer still decides whether to use the index based on statistics, selectivity, and cost.

### 10.2. Virtual Column

You can create a virtual column for a frequently used JSON field:

~~~sql
ALTER TABLE orders_json ADD (
    json_status VARCHAR2(20)
        GENERATED ALWAYS AS (
            JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
        ) VIRTUAL
);

CREATE INDEX orders_json_vstatus_ix
ON orders_json(json_status);
~~~

Applications can query JSON_STATUS like a regular column. This also makes explicit which JSON fields are treated as key queryable attributes.

### 10.3. JSON_EXISTS and Indexes

JSON_EXISTS can be optimized depending on path shape, indexes, and Oracle version. For complex filter conditions or multi-field searches, consider a JSON search index if system features and licensing/configuration support it. Do not assume every path expression can use the same index.

Measure execution plans and real workloads:

~~~sql
EXPLAIN PLAN FOR
SELECT order_id
FROM orders_json
WHERE JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20)) = 'PAID';

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

## 11. Vietnamese JSON Data

JSON text can contain Unicode. With an AL32UTF8 database, CLOB/VARCHAR2 can store full Vietnamese characters. Path member names and string values are case-sensitive based on JSON content.

### 11.1. Extracting Vietnamese with JSON_VALUE

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.customer.name'
           RETURNING VARCHAR2(100)
       ) AS customer_name
FROM orders_json;
~~~

The result is SQL VARCHAR2. Correct display also depends on client encoding/fonts, but database paths do not lose diacritics if data was stored properly.

### 11.2. Extracting the Whole Object with JSON_QUERY

~~~sql
SELECT JSON_QUERY(
           payload,
           '$.customer'
           RETURNING CLOB
       )
FROM orders_json;
~~~

JSON_QUERY preserves the JSON object content, including Unicode strings.

### 11.3. Unicode Escapes in JSON

JSON can represent characters using Unicode escapes, for example:

~~~json
{"name":"Nguy\u1ec5n An"}
~~~

This is a valid JSON representation equivalent to the corresponding accented Vietnamese string. The Oracle SQL/JSON parser decodes escapes when extracting values.

Do not confuse JSON escapes with SQL escapes. When constructing JSON literals in scripts, both SQL quoting and JSON escaping layers must be valid.

## 12. Data Control and Performance

### 12.1. Validating Input JSON

Define an IS JSON constraint to block non-JSON text. If an API has a strict business schema, also validate required fields, data types, array size bounds, and value rules.

### 12.2. Fixed Paths

Prefer fixed, tested paths in SQL. If clients are allowed to select fields, map choices to a whitelisted set of paths. Never concatenate client strings directly into SQL.

### 12.3. Choosing RETURNING Types

Choose a SQL type matching the business meaning:

- Codes/names/statuses: VARCHAR2.
- Quantities/monetary amounts: NUMBER.
- Dates/times: appropriate date/time types or conversion with explicit formats.
- Objects/arrays: JSON_QUERY RETURNING CLOB.

Do not extract numbers as VARCHAR2 and compare lexicographically. Do not extract dates/times and rely on default NLS settings.

### 12.4. Intentional Error Handling

For trusted data, NULL ON ERROR can be convenient. For integration or financial data, ERROR ON ERROR helps catch type and structural mismatches. Choose ON EMPTY according to whether fields are mandatory or optional.

### 12.5. Avoid Extracting Entire JSON When Only One Field Is Needed

If you only need `total`, use JSON_VALUE instead of JSON_QUERY to fetch the whole object and parse it in the application. If you need all items, use JSON_QUERY or JSON_TABLE depending on the goal.

### 12.6. Size Limits

For large documents, use CLOB and RETURNING CLOB where appropriate. Avoid defaulting to VARCHAR2 if results may exceed the SQL string limit for your configuration/release. Read LOBs via streaming on the client if content is large.

## 13. Hands-On Lab

This lab creates an orders table with a JSON payload, then uses JSON_VALUE, JSON_QUERY, and JSON_EXISTS in sequence.

### 13.1. Create the Table

~~~sql
CREATE TABLE lab_orders_json (
    order_id NUMBER PRIMARY KEY,
    payload CLOB NOT NULL,
    CONSTRAINT lab_orders_json_ck CHECK (payload IS JSON)
);
~~~

### 13.2. Insert Data

~~~sql
INSERT INTO lab_orders_json(order_id, payload)
VALUES (
    501,
    TO_CLOB(q'~{
      "orderId": 501,
      "customer": {"id": 101, "name": "Nguyễn An"},
      "status": "PAID",
      "total": 1250.5,
      "items": [
        {"sku": "KB-01", "name": "Bàn phím", "quantity": 2, "price": 500},
        {"sku": "MS-02", "name": "Chuột", "quantity": 1, "price": 250.5}
      ],
      "note": null
    }~')
);

INSERT INTO lab_orders_json(order_id, payload)
VALUES (
    502,
    TO_CLOB(q'~{
      "orderId": 502,
      "customer": {"id": 102, "name": "Trần Bình"},
      "status": "PENDING",
      "total": 300,
      "items": [
        {"sku": "MS-02", "name": "Chuột", "quantity": 1, "price": 300}
      ]
    }~')
);

COMMIT;
~~~

The literals containing Vietnamese assume the script is submitted in a Unicode-supporting encoding with a compatible database character set. You can substitute UNISTR if the environment creating the SQL file does not guarantee UTF-8.

### 13.3. JSON_VALUE

~~~sql
SELECT
    order_id,
    JSON_VALUE(payload, '$.customer.name') AS customer_name,
    JSON_VALUE(payload, '$.status') AS status,
    JSON_VALUE(payload, '$.total' RETURNING NUMBER) AS total_amount
FROM lab_orders_json
ORDER BY order_id;
~~~

The result returns scalars as SQL types.

### 13.4. JSON_QUERY

~~~sql
SELECT
    order_id,
    JSON_QUERY(payload, '$.customer' RETURNING CLOB) AS customer_json,
    JSON_QUERY(payload, '$.items' RETURNING CLOB) AS items_json
FROM lab_orders_json
ORDER BY order_id;
~~~

The result returns the `customer` object and `items` array.

### 13.5. JSON_EXISTS

~~~sql
SELECT order_id
FROM lab_orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.quantity >= 2)'
);
~~~

Only order 501 has an item with quantity 2 or more.

### 13.6. PASSING

~~~sql
SELECT order_id
FROM lab_orders_json o
WHERE JSON_EXISTS(
    o.payload,
    '$.items[*]?(@.sku == $wantedSku)'
    PASSING 'MS-02' AS "wantedSku"
);
~~~

The result includes orders containing SKU MS-02.

### 13.7. Distinguishing null and missing

~~~sql
SELECT
    order_id,
    JSON_EXISTS(payload, '$.note') AS has_note,
    JSON_VALUE(payload, '$.note') AS note_value
FROM lab_orders_json
ORDER BY order_id;
~~~

Order 501 has `note` present with JSON null: JSON_EXISTS is TRUE, JSON_VALUE returns SQL NULL. Order 502 has no `note`: JSON_EXISTS is FALSE, and JSON_VALUE also returns SQL NULL by default.

### 13.8. Testing Conversion Errors

Test JSON_VALUE RETURNING NUMBER on a string field:

~~~sql
SELECT JSON_VALUE(
           payload,
           '$.status'
           RETURNING NUMBER
           ERROR ON ERROR
       )
FROM lab_orders_json;
~~~

The query raises a conversion error because `status` is a string such as PAID/PENDING, not a NUMBER. This example illustrates how ERROR ON ERROR catches type mismatches.

### 13.9. Create an Index

~~~sql
CREATE INDEX lab_orders_status_ix
ON lab_orders_json (
    JSON_VALUE(payload, '$.status' RETURNING VARCHAR2(20))
);
~~~

Query with the same path and return type:

~~~sql
SELECT order_id
FROM lab_orders_json
WHERE JSON_VALUE(
          payload,
          '$.status'
          RETURNING VARCHAR2(20)
      ) = 'PAID';
~~~

Use EXPLAIN PLAN/DBMS_XPLAN to observe whether the optimizer chooses the index.

## 14. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| JSON_VALUE returns NULL despite expected field | Path does not match or ON ERROR/ON EMPTY returns NULL | Check JSON_EXISTS, path, and data |
| JSON_VALUE errors when extracting an object | Function requires a scalar | Use JSON_QUERY |
| JSON_QUERY returns NULL | Path does not match, error occurred, or ON ERROR | Check ON ERROR/ON EMPTY and inspect JSON |
| JSON_QUERY errors when path matches multiple values | Missing appropriate wrapper | Use WITH WRAPPER or narrow the path |
| JSON_EXISTS FALSE on mistyped path | Path does not match or default error handling | Use ERROR ON ERROR and check syntax |
| JSON_EXISTS TRUE but JSON_VALUE is NULL | Field exists with JSON null | Distinguish presence from scalar value |
| Wrong array item retrieved | Mistakenly assuming 1-based indexing | JSON array indexes start at 0 |
| Property name fails to match | Paths are case-sensitive | Match the exact member name in JSON |
| Incorrect numeric filtering | JSON_VALUE returned string and compared lexicographically | Use RETURNING NUMBER |
| Filter ignores bound value | Wrong PASSING variable name or alias | Ensure `$var` and `AS "var"` match |
| Malformed JSON enters table | Missing IS JSON constraint | Add CHECK constraint and audit legacy data |
| SQL injection via path | Untrusted input concatenated into path/SQL | Use PASSING and whitelist paths |
| Index is not used | Expression/path/returning type mismatch or optimizer picks another plan | Compare index expression and execution plan |
| Vietnamese text displays incorrectly | Wrong client encoding or source data | Check charset and Unicode at every boundary |

## 15. SQL/JSON Query Design Checklist

Before shipping a query to production:

1. Does the JSON column have an IS JSON constraint or equivalent validation?
2. Does the path use exact member names with correct casing?
3. Are array indexes 0-based?
4. Can the path match a single scalar or multiple values?
5. Are JSON_VALUE and JSON_QUERY used for their intended purposes?
6. Is JSON_EXISTS needed to distinguish missing fields from JSON null?
7. Does the RETURNING type match the business type?
8. Do ON ERROR and ON EMPTY reflect the data contract?
9. Are dynamic values bound via PASSING?
10. Are dynamic paths whitelisted?
11. Do frequent queries need a function-based index or virtual column?
12. Are large CLOB results read via streaming?
13. Is Vietnamese/Unicode data passed through clients in the correct encoding?

## 16. Practice Exercises

Use LAB_ORDERS_JSON from Section 13.

### Exercise 1 — Basic Paths

Write JSON_VALUE expressions to extract `orderId`, `customer.id`, `customer.name`, and `status`. Specify the SQL return types explicitly.

### Exercise 2 — Array Index and Wildcards

Extract the SKU of the first element using JSON_VALUE. Use JSON_QUERY WITH WRAPPER to extract the SKUs of all items as a JSON array.

### Exercise 3 — JSON_EXISTS Filter

Find orders with an item whose quantity is greater than 1 and price is below 600. Write the filter expression and verify the result.

### Exercise 4 — PASSING

Write a query accepting SKU and min quantity from bind variables. Use PASSING with two path variables.

### Exercise 5 — JSON null and missing

Insert one order with `note` set to `null` and one order without `note`. Use JSON_EXISTS combined with JSON_VALUE to distinguish the two cases.

### Exercise 6 — ON ERROR/ON EMPTY

Try extracting `status` with RETURNING NUMBER. Compare NULL ON ERROR, DEFAULT ON ERROR, and ERROR ON ERROR. Test a non-existent path with NULL ON EMPTY and ERROR ON EMPTY.

### Exercise 7 — JSON_TABLE

Unnest `items` into rows containing `sku`, `quantity`, and `price`. Calculate the total amount of items using SQL.

### Exercise 8 — Index

Create a function-based index on JSON_VALUE for `status`. Run EXPLAIN PLAN for a status filter query and explain when the optimizer chooses the index.

## 17. Cleaning Up Lab Data

Run only in your dedicated lab schema after completing the exercises:

~~~sql
DROP TABLE lab_orders_json PURGE;
~~~

Do not run cleanup commands on production/business tables.

## Summary

SQL/JSON paths start from the root `$` and traverse object members, array indexes, wildcards, or filters. JSON arrays use 0-based indexing. Oracle defaults to lax mode; strict mode requires tighter structural matching. Member names are case-sensitive, and dynamic values should be passed via PASSING.

JSON_VALUE extracts a scalar and converts it to a SQL type, commonly using RETURNING NUMBER or VARCHAR2. JSON_QUERY extracts a JSON object/array and can use WITH WRAPPER when a path returns multiple results. JSON_EXISTS checks whether a path matches, making it ideal for WHERE clauses and array filters. JSON null causes JSON_VALUE to return SQL NULL while JSON_EXISTS remains TRUE; missing members typically cause JSON_EXISTS to return FALSE and JSON_VALUE to return NULL by default.

Validate input JSON, choose ON ERROR/ON EMPTY according to your contract, use proper RETURNING types, avoid concatenating user input into paths, and create function-based indexes or virtual columns for frequently queried fields. When transforming multiple JSON elements into SQL rows/columns, consider JSON_TABLE.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SQL/JSON Path Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/json-path-expressions.html) — root, members, arrays, wildcards, filters, and lax/strict mode.
- [Oracle Database SQL Language Reference — JSON_VALUE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_VALUE.html) — scalar extraction, RETURNING, and error handling.
- [Oracle Database SQL Language Reference — JSON_QUERY (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_QUERY.html) — object/array extraction and wrappers.
- [Oracle Database SQL Language Reference — JSON_EXISTS (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/condition-JSON_EXISTS.html) — path match testing, filters, and PASSING.
- [Oracle Database SQL Language Reference — JSON_TABLE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/function-JSON_TABLE.html) — converting JSON into relational rows and columns.
- [Oracle Database JSON Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/) — storing, validating, querying, and indexing JSON.

When deploying on an Oracle release other than 19c, consult the JSON Developer's Guide and SQL Language Reference for your exact version, especially regarding path grammar, RETURNING types, ON ERROR/ON EMPTY, wrappers, and index support.
