# Extracting JSON Using Key and Path Operators in PostgreSQL

In a sales system, each order may contain customer details, an address, product line items, classification tags, and flexible attributes. When part of that data is stored in a `jsonb` column, you can query an attribute deep inside the document without bringing the entire JSON into Java to parse it.

For example, given the document:

~~~json
{
  "customer": {
    "id": 101,
    "name": "An",
    "address": {"city": "Hà Nội"}
  },
  "items": [
    {"sku": "BOOK-01", "qty": 2},
    {"sku": "PEN-01", "qty": 1}
  ],
  "paid": true
}
~~~

PostgreSQL supports very concise ways to retrieve values:

~~~sql
-- Sub-JSON/JSONB value:
SELECT payload -> 'customer' FROM orders;

-- SQL text string:
SELECT payload -> 'customer' ->> 'name' FROM orders;

-- JSON/JSONB at a multi-level path:
SELECT payload #> '{customer,address,city}' FROM orders;

-- Text at a multi-level path:
SELECT payload #>> '{customer,address,city}' FROM orders;
~~~

The most important distinction is between **operators that return JSON/JSONB** and **operators that return text**, between **object keys** and **array positions**, and between a **missing key**, **JSON null**, and **SQL NULL**. Only when these differences are properly understood can you safely cast, filter, join, index, and handle heterogeneous data.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `json` and `jsonb`, and know when to use each type.
2. Use `->` and `->>` to extract by **object key** or **array element index**.
3. Use `#>` and `#>>` with a **`text[]` path** across multiple object/array levels.
4. Chain nested accesses such as `payload -> 'customer' -> 'address' ->> 'city'`.
5. Distinguish `jsonb`, `json`, `text`, `boolean`, and `numeric` outputs after type conversions.
6. Correctly handle **missing keys**, **JSON null**, **SQL NULL**, **empty arrays**, **mismatched types**, and **out-of-range indexes**.
7. Query keys containing dots, spaces, commas, or special characters without confusing them with path notation.
8. Extract array elements by position and expand JSON arrays into rows using `jsonb_array_elements` / `LATERAL`.
9. Use `jsonb_typeof` to check types before casting to numbers, booleans, or timestamps.
10. Distinguish `text[]` paths in `#>` / `#>>` from **SQL/JSON paths** starting with `$`.
11. Write `WHERE`, `ORDER BY`, and expression indexes on values extracted from JSON.
12. Recognize when a B-tree expression index or a GIN index is appropriate, instead of creating the wrong index type.
13. Use safe query parameterization in Java/JDBC applications, avoiding direct concatenation of user-supplied keys/paths into SQL.
14. Complete scenario-based exercises on nested JSON documents in PostgreSQL.

## 2. JSON and JSONB: Essential Foundations

PostgreSQL has two data types for storing JSON documents:

| Criterion | `json` | `jsonb` |
| --- | --- | --- |
| Storage | Stores the JSON text content after syntax validation | Stores a parsed and normalized binary representation |
| Whitespace/key order | Preserves presentation details of the input | Does not guarantee preserving whitespace or key order |
| Duplicate object keys | Can retain duplicate keys in stored text | Does not keep duplicates as separate pairs; the last value wins |
| Reading/querying | Has extraction operators | Has extraction operators plus more supporting operators and indexes |
| Indexing JSON structure | More limited | Supports GIN for containment/key/path queries |
| Common use case | When the original JSON text needs to be preserved | Frequent querying and updating of JSON documents |

In most applications that need to search by JSON fields, **`jsonb` is the sensible starting point**. However, never equate JSONB with a strictly schema-constrained relational table: without constraints or validation, two rows can have the same field holding completely different types.

### 2.1. Creating JSON and JSONB Values

~~~sql
SELECT
    '{"name":"An","age":20}'::json AS as_json,
    '{"name":"An","age":20}'::jsonb AS as_jsonb;
~~~

The `::json` and `::jsonb` casts force PostgreSQL to validate document syntax. An invalid JSON string raises an error rather than being stored as a valid object.

### 2.2. JSON Values and SQL Values Are Not the Same

~~~sql
SELECT
    pg_typeof('{"x":1}'::jsonb) AS column_type,
    pg_typeof('{"x":1}'::jsonb -> 'x') AS json_result_type,
    pg_typeof('{"x":1}'::jsonb ->> 'x') AS text_result_type;
~~~

Corresponding **SQL types** returned:

| Expression | SQL Type |
| --- | --- |
| `'{"x":1}'::jsonb` | `jsonb` |
| `'{"x":1}'::jsonb -> 'x'` | `jsonb` |
| `'{"x":1}'::jsonb ->> 'x'` | `text` |

The JSON value `1` is a **JSON number**; when using `->>`, PostgreSQL returns the SQL string `'1'`. To perform arithmetic, an appropriate check/cast step is needed.

### 2.3. Do Not Use JSONB in Place of Every Relational Column

Order primary keys, foreign key relationships, monetary amounts, business timestamps, and heavily queried fields often fit explicitly typed columns better. JSONB suits flexible structures or heterogeneous attributes; do not automatically dump all data into a JSONB blob and cast on every query.

## 3. Lab Dataset Used Throughout This Lesson

The examples below belong to a dedicated schema `json_lab_307`. Only run table creation/write statements in a lab database or an authorized environment. If the schema already exists, rename it instead of deleting data from an unknown source.

### 3.1. Creating the Table

~~~sql
CREATE SCHEMA json_lab_307;

CREATE TABLE json_lab_307.orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB
);
~~~

`payload` intentionally **allows SQL NULL** to illustrate the case where no JSON document exists. Production systems can use `payload JSONB NOT NULL` and a constraint requiring the root to be an object.

### 3.2. Loading Documents with Objects, Arrays, Nulls, and Missing Keys

~~~sql
INSERT INTO json_lab_307.orders
    (order_id, created_at, payload)
VALUES
(
    1,
    TIMESTAMPTZ '2026-11-12 09:00:00+07',
    $json$
    {
      "customer": {
        "id": 101,
        "name": "An",
        "contact": {"email": "An@Example.com"},
        "address": {
          "city": "Hà Nội",
          "postal_code": "100000"
        }
      },
      "items": [
        {"sku": "BOOK-01", "qty": 2, "price": 120000},
        {"sku": "PEN-01",  "qty": 1, "price": 15000}
      ],
      "tags": ["new", "vip"],
      "paid": true,
      "total": 255000,
      "coupon": null,
      "note": "",
      "a.b": {"x y": "special-value"}
    }
    $json$::jsonb
),
(
    2,
    TIMESTAMPTZ '2026-11-13 11:30:00+07',
    $json$
    {
      "customer": {
        "id": 102,
        "name": "Bình",
        "contact": {"email": "binh@example.com"},
        "address": {"city": "Đà Nẵng"}
      },
      "items": [
        {"sku": "MOUSE-01", "qty": 1, "price": 320000}
      ],
      "tags": [],
      "paid": false,
      "total": 320000,
      "coupon": "WELCOME"
    }
    $json$::jsonb
),
(
    3,
    TIMESTAMPTZ '2026-11-14 08:00:00+07',
    $json$
    {
      "customer": {
        "id": 103,
        "name": "Chi",
        "address": {"city": "TP Hồ Chí Minh"}
      },
      "items": [],
      "tags": ["vip"],
      "paid": true,
      "total": 0
    }
    $json$::jsonb
),
(
    4,
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    $json$
    {
      "customer": {
        "id": 104,
        "name": "Dũng",
        "address": null
      },
      "items": null,
      "paid": true,
      "total": 50000
    }
    $json$::jsonb
),
(
    5,
    TIMESTAMPTZ '2026-11-14 10:00:00+07',
    $json$
    {
      "customer": {
        "id": 105,
        "name": "Em"
      },
      "items": {"sku": "NOT-AN-ARRAY"},
      "tags": ["trial"],
      "paid": false,
      "total": "50000",
      "coupon": null
    }
    $json$::jsonb
),
(
    6,
    TIMESTAMPTZ '2026-11-14 11:00:00+07',
    NULL
);
~~~

**Intent of the lab cases:**

| order_id | Scenario |
| ---: | --- |
| 1 | Multi-level object, 2-element array, JSON null, empty string, keys `a.b` and `x y` |
| 2 | Single-element array, `tags=[]`, boolean false, string coupon |
| 3 | `items=[]`, missing `contact` and `coupon` |
| 4 | `address=null` and `items=null` (JSON null), missing `tags` |
| 5 | `items` is an object rather than an array; `total` is a JSON string instead of a number |
| 6 | `payload` is **SQL NULL** rather than a JSON object |

The anomalous rows (4–6) are designed to teach **safe reading when structures vary**. Never assume production JSON has a uniform schema unless the database enforces it.

### 3.3. Inspecting Root Data Types

~~~sql
SELECT
    order_id,
    pg_typeof(payload) AS sql_type,
    jsonb_typeof(payload) AS json_root_type
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Rows 1–5 have root `object`; row 6 returns SQL NULL for both `payload` and `jsonb_typeof(payload)`.

## 4. The Four Core Extraction Operators

| Operator | Right Operand | Behavior | SQL Return Type for `jsonb` |
| --- | --- | --- | --- |
| `->` | `text` (key) or `integer` (array index) | Extracts child value, preserving JSON | `jsonb` |
| `->>` | `text` or `integer` | Extracts child value as text | `text` |
| `#>` | `text[]` (multi-element path) | Extracts JSON at path | `jsonb` |
| `#>>` | `text[]` | Extracts text at path | `text` |

If the **source is `json`** instead of `jsonb`, `->` and `#>` return `json`; `->>` and `#>>` still return `text`. PostgreSQL does not force-convert the entire document to `jsonb` just because you access a field.

### 4.1. Minimal Example

~~~sql
SELECT
    '{"x":{"value":42}}'::jsonb -> 'x'
        AS nested_object,
    '{"x":{"value":42}}'::jsonb ->> 'x'
        AS nested_object_as_text,
    '{"x":{"value":42}}'::jsonb #> '{x,value}'
        AS json_number,
    '{"x":{"value":42}}'::jsonb #>> '{x,value}'
        AS text_number;
~~~

Interpretation:

| Column | Value Description | Type |
| --- | --- | --- |
| `nested_object` | `{"value": 42}` | `jsonb` |
| `nested_object_as_text` | SQL string representing the JSON object | `text` |
| `json_number` | JSON number `42` | `jsonb` |
| `text_number` | SQL string `'42'` | `text` |

**`->>` is not only for JSON strings**. It also renders JSON numbers, booleans, objects, and arrays as text; if you need to traverse further into nested structures, **keep JSON with `->` / `#>` first**, and only convert to text at the final level.

### 4.2. Operator Selection Flowchart

~~~mermaid
flowchart TD
    A["Need to read data in JSON/JSONB"] --> B{"Single level or multi-level access?"}
    B -->|Single level| C{"Want JSON or SQL text?"}
    C -->|JSON| D["->"]
    C -->|text| E["->>"]
    B -->|Multi-level| F{"Is the path already a text[]?"}
    F -->|Yes| G{"Want JSON or text?"}
    F -->|No| H["Chain multiple -> operators"]
    G -->|JSON| I["#>"]
    G -->|text| J["#>>"]
    H --> K["Use ->> at the final level to get text"]
~~~

## 5. The -> Operator: Getting JSON by Key

~~~sql
SELECT
    order_id,
    payload -> 'customer' AS customer_json,
    payload -> 'items' AS items_json,
    payload -> 'paid' AS paid_json
FROM json_lab_307.orders
WHERE order_id IN (1, 2)
ORDER BY order_id;
~~~

For order 1:

- `payload -> 'customer'` is a **JSON object**.
- `payload -> 'items'` is a **JSON array**.
- `payload -> 'paid'` is a **JSON boolean** `true`, **not a SQL boolean**.

### 5.1. Keeping JSON for Further Traversal

~~~sql
SELECT
    payload -> 'customer' -> 'address' AS address_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

The result is a JSON object containing `city` and `postal_code`.

~~~sql
SELECT
    payload -> 'customer' -> 'address' -> 'city'
        AS city_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

The result is still a JSON string (for instance displayed as `"Hà Nội"`, including JSON quotes).

### 5.2. Key Lookup Only Checks the Current Level

~~~sql
SELECT
    payload -> 'city' AS top_level_city,
    payload -> 'customer' -> 'address' -> 'city'
        AS nested_city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`payload -> 'city'` returns **SQL NULL** because there is no `city` key at the root. PostgreSQL does not recursively search for keys of the same name across all nested objects.

### 5.3. Distinguishing Result Types

~~~sql
SELECT
    pg_typeof(payload -> 'customer') AS customer_type,
    jsonb_typeof(payload -> 'customer') AS customer_json_kind,
    pg_typeof(payload -> 'paid') AS paid_sql_type,
    jsonb_typeof(payload -> 'paid') AS paid_json_kind
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`pg_typeof` reports the **PostgreSQL column/expression type**; `jsonb_typeof` reports the **JSON value kind inside JSON**.

## 6. The ->> Operator: Getting SQL Text by Key

~~~sql
SELECT
    order_id,
    payload ->> 'paid' AS paid_as_text,
    payload ->> 'total' AS total_as_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 5)
ORDER BY order_id;
~~~

In the output, `paid_as_text` is the string `'true'` or `'false'`; `total_as_text` is a numeric string. Even though the original JSON had `"total":255000` (a number), `->>` still returns `text`.

### 6.1. When to Choose ->>?

Commonly used when you want to:

- Select text such as customer name, email, or city;
- Compare strings in `WHERE`;
- Pass values into `LOWER`, `BTRIM`, or other text functions;
- Explicitly cast to `integer`, `numeric`, `boolean`, or timestamp **after checking the schema**.

~~~sql
SELECT
    order_id,
    payload -> 'customer' ->> 'name' AS customer_name
FROM json_lab_307.orders
WHERE order_id BETWEEN 1 AND 5
ORDER BY order_id;
~~~

### 6.2. Do Not Use ->> Mid-Chain If You Still Need JSON Access

**Wrong approach:**

~~~sql
-- payload ->> 'customer' returns text, no longer JSONB.
-- Chaining -> 'address' on text raises an operator type error.
--
-- SELECT payload ->> 'customer' -> 'address'
-- FROM json_lab_307.orders;
~~~

**Correct:**

~~~sql
SELECT
    payload -> 'customer' -> 'address' ->> 'city'
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Rule of thumb:** use `->` for every intermediate level; use `->>` at the final level if you want text.

### 6.3. JSON Numbers and SQL numeric

~~~sql
SELECT
    order_id,
    payload ->> 'total' AS total_text,
    (payload ->> 'total')::numeric AS total_numeric
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 4, 5)
ORDER BY order_id;
~~~

In the lab dataset, `'50000'` from order 5 casts to numeric even though the original JSON **was a string**, which does not prove the document obeys the schema. If another row contains `"total":"not-a-number"`, `::numeric` raises an error.

### 6.4. JSON Booleans and SQL boolean

~~~sql
SELECT
    order_id,
    payload ->> 'paid' AS paid_text,
    (payload ->> 'paid')::boolean AS paid_boolean
FROM json_lab_307.orders
WHERE order_id BETWEEN 1 AND 5
ORDER BY order_id;
~~~

To preserve exact JSON semantics, especially with heterogeneous data, check `jsonb_typeof(payload -> 'paid') = 'boolean'` before casting.

## 7. Multi-Level Access by Chaining -> and ->>

Deeply nested JSON object:

~~~json
{
  "customer": {
    "contact": {
      "email": "An@Example.com"
    }
  }
}
~~~

Query:

~~~sql
SELECT
    order_id,
    payload -> 'customer' -> 'contact' ->> 'email'
        AS customer_email
FROM json_lab_307.orders
ORDER BY order_id;
~~~

When an intermediate level does not exist, the extraction result is normally **SQL NULL**, without throwing an error just because a key is missing. For instance, order 3 has `customer` without `contact`, so email returns NULL.

### 7.1. Left-to-Right Evaluation Rule

~~~text
payload
   |
   +-- -> 'customer' : jsonb object
            |
            +-- -> 'contact' : jsonb object
                     |
                     +-- ->> 'email' : SQL text
~~~

If you want to keep email as a **JSON string**, use `-> 'email'` at the final step instead of `->>`.

### 7.2. Add Parentheses for Readability

~~~sql
SELECT
    ((payload -> 'customer') -> 'address') ->> 'city'
        AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

For simple chains, PostgreSQL supports writing them sequentially without grouping parentheses at each step. When mixing with casts, comparisons, or other operators, **use parentheses to avoid ambiguity over types and precedence**.

## 8. #> and #>>: Paths as text[]

Instead of repeating `->`, you can supply the entire path as a **PostgreSQL `text[]` array**.

~~~sql
SELECT
    order_id,
    payload #> '{customer,address,city}' AS city_json,
    payload #>> '{customer,address,city}' AS city_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

When the source is `jsonb`:

- `#>` returns `jsonb`, with a JSON string value such as `"Hà Nội"`.
- `#>>` returns `text`, with the SQL string `Hà Nội` (without JSON quotation marks).

### 8.1. The Path Is text[], Not an "a.b.c" String

The literal:

~~~sql
'{customer,address,city}'::text[]
~~~

represents **three text elements**: `customer`, `address`, `city`. This is **PostgreSQL array literal syntax**, not JSONPath and not JavaScript dot notation.

### 8.2. Readable and Parameterizable ARRAY[] Syntax

~~~sql
SELECT
    payload #>> ARRAY['customer', 'address', 'city']
        AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`ARRAY['customer', 'address', 'city']` resolves to a `text[]` matching the operator context; write `::text[]` explicitly when needed.

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']::text[]
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 8.3. Comparing the Two Syntaxes

~~~sql
SELECT
    payload -> 'customer' -> 'address' ->> 'city'
        AS by_chaining,
    payload #>> '{customer,address,city}'
        AS by_path
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Both expressions share the same goal of extracting the **SQL text of `city`**. Do not assume they have identical cost/plan in every context; check when workloads are large enough.

### 8.4. Extracting a Sub-Object or Sub-Array with #>

~~~sql
SELECT
    payload #> '{customer,address}' AS address_json,
    payload #> '{items}' AS items_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`#>` is useful when you need to keep an object or array for further processing with JSONB functions or to return the sub-structure intact.

### 8.5. Single-Element Paths Are Also Valid

~~~sql
SELECT
    payload #> '{customer}' AS customer_json,
    payload #>> '{paid}' AS paid_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

For a single key, `->` / `->>` is usually easier to read, while `#>` / `#>>` is convenient when the application already has a dynamic array path.

## 9. Accessing JSON Array Elements by Index

In PostgreSQL, **JSON array indexes start at 0**:

~~~text
JSON array items:

[
  {"sku": "BOOK-01", "qty": 2},  <- index 0
  {"sku": "PEN-01",  "qty": 1}   <- index 1
]
~~~

### 9.1. Getting the Element at Index 0

~~~sql
SELECT
    payload -> 'items' -> 0 AS first_item_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

The result is the JSON object for `BOOK-01`. `-> 0` uses an **integer operand**, not the text key `'0'`.

### 9.2. Getting a Field Inside an Array Element

~~~sql
SELECT
    payload -> 'items' -> 0 ->> 'sku'
        AS first_sku,
    payload -> 'items' -> 0 ->> 'qty'
        AS first_quantity_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

| Result | Value | SQL Type |
| --- | --- | --- |
| `first_sku` | `BOOK-01` | `text` |
| `first_quantity_text` | `2` | `text` |

If you need numeric quantity:

~~~sql
SELECT
    (payload -> 'items' -> 0 ->> 'qty')::integer
        AS first_quantity
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Wrap the entire extraction in parentheses **before casting**.

### 9.3. Array Paths with #> and #>>

~~~sql
SELECT
    payload #> '{items,0}' AS first_item_json,
    payload #>> '{items,0,sku}' AS first_sku,
    payload #>> '{items,1,sku}' AS second_sku
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

The path `'{items,0,sku}'` is interpreted as:

1. From the root object, take key `items`;
2. On that JSON array, take element index `0`;
3. From that element object, take key `sku`.

### 9.4. Negative Indexes Count from the End of the Array

JSON extraction operators allow **negative indexes** to count from the end of the array:

~~~sql
SELECT
    payload -> 'items' -> -1 ->> 'sku' AS last_sku,
    payload #>> '{items,-1,sku}' AS last_sku_by_path
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

In order 1, both expressions return `PEN-01`. `-1` is the last element, `-2` is the second-to-last element if it exists. Do not confuse this syntax with standard SQL array indexing.

### 9.5. Out-of-Range Indexes

~~~sql
SELECT
    payload -> 'items' -> 99 AS out_of_range_json,
    payload -> 'items' ->> 99 AS out_of_range_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Both values are **SQL NULL**. JSON extraction operators normally return NULL when the requested structure cannot be traversed; they do not throw an error merely because an index is out of bounds.

### 9.6. Getting the Last Element When Length Varies

~~~sql
SELECT
    order_id,
    payload -> 'items' -> -1 AS last_item
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

- Order 1: item `PEN-01`.
- Order 2: item `MOUSE-01`.
- Order 3: SQL NULL because `items=[]`.

This is the benefit of negative indexing: you do not need to compute the array length before fetching the last element. However, if business logic needs **every** element, do not hardcode fixed indexes `0`, `1`, `2`; use a **set-returning function** such as `jsonb_array_elements`.

## 10. JSON Arrays Differ from PostgreSQL SQL Arrays

A very common point of confusion:

| Structure | Example | Indexing |
| --- | --- | --- |
| JSON array | `'[10,20,30]'::jsonb` | **0, 1, 2** |
| Default PostgreSQL SQL array | `ARRAY[10,20,30]` | Typically **1, 2, 3** |
| `text[]` passed to `#>` | `ARRAY['items','0','sku']` | Elements are **keys/indexes inside JSON** |

~~~sql
SELECT
    '[10,20,30]'::jsonb -> 0 AS first_json_value,
    (ARRAY[10,20,30])[1] AS first_sql_array_value;
~~~

To subscript an inline SQL array expression, put parentheses around `ARRAY[...]`:

~~~sql
SELECT
    (ARRAY[10,20,30])[1] AS first_sql_array_value,
    '[10,20,30]'::jsonb -> 0 AS first_json_value;
~~~

Both logical values are `10`, but one is `integer` and the other is `jsonb`. SQL arrays can also be created with lower bounds other than 1; **do not apply SQL array defaults as rules for JSON arrays**.

### 10.1. text[] Paths Are Not Indexed Like JSON

In:

~~~sql
payload #>> ARRAY['items', '0', 'sku']
~~~

`ARRAY[...]` is merely **a container of three path components** passed to the operator. The string `'0'` is interpreted by PostgreSQL as a **JSON array index** at the `items` level, not as indexing element `0` of the SQL array literal itself.

### 10.2. An Object with Key "0" Is Still an Object

~~~sql
SELECT
    '{"0":"object-value"}'::jsonb -> '0'
        AS from_object,
    '["array-value"]'::jsonb -> 0
        AS from_array;
~~~

A `text` operand looks up an object key; an `integer` operand indexes a JSON array. If you are unsure of the structure, check `jsonb_typeof` before extracting.

## 11. Keys Containing Dots, Spaces, or Commas

JSON allows keys to be arbitrary strings, not just valid SQL column names.

Order 1 contains:

~~~json
{
  "a.b": {
    "x y": "special-value"
  }
}
~~~

### 11.1. A Dot Is Part of the Key Name

~~~sql
SELECT
    payload -> 'a.b' ->> 'x y' AS special_value
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Result: `special-value`.

`'a.b'` is **one single key**, not automatically split into `a` and then `b`.

### 11.2. Use #>> with ARRAY[] to Avoid Syntax Confusion

~~~sql
SELECT
    payload #>> ARRAY['a.b', 'x y']::text[]
        AS special_value
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Building `text[]` with `ARRAY[]` is usually clearer than hand-writing a literal full of quotes and escapes, especially when keys contain commas, spaces, braces, or special characters.

### 11.3. When a Key Contains a Comma

Standalone example:

~~~sql
SELECT
    '{"a,b":{"c d":77}}'::jsonb
        #>> ARRAY['a,b', 'c d']::text[]
        AS extracted;
~~~

The result is the text string `77`. This avoids confusing a comma inside a key name with the comma **separating elements** in a PostgreSQL array literal.

### 11.4. JSON Does Not Use SQL Identifier Quoting

Do not write:

~~~sql
-- Wrong semantics for a JSON key:
-- payload -> "customer"
~~~

In SQL, double quotes `"customer"` denote an **identifier**, such as a column name. For a JSON key named `customer`, use a **string literal** `'customer'`, or bind a text parameter safely.

## 12. Missing Keys, JSON null, and SQL NULL

This is critical when filtering JSON data:

1. **Missing key:** the object does not contain that key.
2. **JSON null:** the object contains the key with JSON literal value `null`.
3. **SQL NULL:** a SQL column/expression has no value, or extraction could not find the structure.
4. **String `"null"`:** JSON string `"null"` or SQL text `'null'`, **distinct from** JSON null.
5. **Empty string:** `""`, **distinct from** null and distinct from a missing key.

### 12.1. Comparing an Object Containing null vs. a Missing Key

~~~sql
SELECT
    '{"coupon":null}'::jsonb -> 'coupon'
        AS present_json_null,
    '{"coupon":null}'::jsonb -> 'missing'
        AS absent_sql_null;
~~~

- `present_json_null` is a **JSONB null value**; the SQL expression itself is not SQL NULL.
- `absent_sql_null` is **SQL NULL** because the key `missing` does not exist.

### 12.2. Checking with IS NULL

~~~sql
SELECT
    ('{"coupon":null}'::jsonb -> 'coupon') IS NULL
        AS json_null_is_sql_null,
    ('{"coupon":null}'::jsonb -> 'missing') IS NULL
        AS missing_is_sql_null;
~~~

| Expression | Result |
| --- | --- |
| `json_null_is_sql_null` | `false` |
| `missing_is_sql_null` | `true` |

**Do not guess from how a SQL client prints `null`**: some clients render SQL NULL and JSONB null identically on screen. Use `IS NULL` or `jsonb_typeof` to tell them apart.

### 12.3. Using ->> Turns JSON null into SQL NULL

~~~sql
SELECT
    ('{"coupon":null}'::jsonb ->> 'coupon') IS NULL
        AS json_null_text_is_null,
    ('{"coupon":null}'::jsonb ->> 'missing') IS NULL
        AS missing_text_is_null;
~~~

Both expressions evaluate to `true`. Once extracted as text via `->>`, you can **no longer distinguish** "key exists with JSON null" from "key does not exist" by the return value alone.

### 12.4. Using the ? Operator to Check Key Existence

~~~sql
SELECT
    order_id,
    payload ? 'coupon' AS has_coupon_key,
    payload -> 'coupon' AS coupon_as_json,
    payload ->> 'coupon' AS coupon_as_text
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 5)
ORDER BY order_id;
~~~

Semantic results:

| order_id | `has_coupon_key` | `coupon_as_json` | `coupon_as_text` |
| ---: | --- | --- | --- |
| 1 | true | JSON null | SQL NULL |
| 2 | true | JSON string `"WELCOME"` | `WELCOME` |
| 3 | false | SQL NULL | SQL NULL |
| 5 | true | JSON null | SQL NULL |

**`?` is a `jsonb` operator that checks existence at the current level** (an object key or a top-level string element of an array), not an extraction operator like `->`.

### 12.5. Checking JSON Value Type

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'coupon') AS coupon_json_type
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3, 5)
ORDER BY order_id;
~~~

| order_id | Type |
| ---: | --- |
| 1 | text string `null` (JSON null type name) |
| 2 | `string` |
| 3 | SQL NULL (no key) |
| 5 | `null` |

`jsonb_typeof` returns **text describing the JSON type** such as `'object'`, `'array'`, `'string'`, `'number'`, `'boolean'`, or `'null'`. For a **SQL NULL input**, the result is SQL NULL.

### 12.6. Finding Rows Where the Key Exists and Equals JSON null

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ? 'coupon'
  AND payload -> 'coupon' = 'null'::jsonb
ORDER BY order_id;
~~~

Result: **1** and **5**.

### 12.7. Finding Rows Missing a Key

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE jsonb_typeof(payload) = 'object'
  AND NOT (payload ? 'coupon')
ORDER BY order_id;
~~~

Result: **3** and **4**. Row 6 has a **SQL NULL document**, so it is not treated as an empty object missing a key; the root object condition excludes it.

If the application wants to include NULL documents in the "no coupon" group, define that explicitly:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload IS NULL
   OR NOT (payload ? 'coupon')
ORDER BY order_id;
~~~

### 12.8. COALESCE Hides Differences If Used Carelessly

~~~sql
SELECT
    order_id,
    COALESCE(payload ->> 'coupon', '<none>')
        AS display_coupon
FROM json_lab_307.orders
ORDER BY order_id;
~~~

`COALESCE` is convenient for **display**, but `'<none>'` collapses JSON null, missing key, and SQL NULL into a single representation. Do not use this for audit data that needs to distinguish all three cases.

### 12.9. Comparing with = NULL Is Always Wrong

~~~sql
-- Does not find SQL NULL:
-- WHERE payload ->> 'coupon' = NULL
~~~

In SQL, normal equality comparison with NULL yields **UNKNOWN**, not true. Use `IS NULL` or `IS NOT NULL`, then add `?` / `jsonb_typeof` if you need to separate JSON null from missing keys.

## 13. Empty JSON String, JSON null, and Missing Values

Lab order 1 has `"note":""`. Query:

~~~sql
SELECT
    payload -> 'note' AS note_json,
    payload ->> 'note' AS note_text,
    (payload ->> 'note') = '' AS is_empty_text,
    (payload ->> 'note') IS NULL AS is_sql_null
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`is_empty_text=true` while `is_sql_null=false`. An empty string should not be treated the same as a missing key if business rules distinguish "user intentionally cleared the note" from "note field was not provided."

### 13.1. A JSON String Containing the Word "null" Is Also Different

~~~sql
SELECT
    '"null"'::jsonb AS json_string_null,
    'null'::jsonb AS json_null_value,
    jsonb_typeof('"null"'::jsonb) AS kind_1,
    jsonb_typeof('null'::jsonb) AS kind_2;
~~~

`kind_1='string'`, `kind_2='null'`. JSON number `0`, boolean `false`, and string `"false"` are likewise distinct values.

## 14. Deep Access When the Structure Has the Wrong Type

`->` / `->>` / `#>` / `#>>` normally return **SQL NULL** when the structure at some level does not match, instead of raising an "object expected" error on every mismatched path.

For example, order 4 has `"customer":{"address":null}`:

~~~sql
SELECT
    payload -> 'customer' -> 'address' AS address_value,
    payload -> 'customer' -> 'address' ->> 'city'
        AS city_text
FROM json_lab_307.orders
WHERE order_id = 4;
~~~

`address_value` is **JSON null**, while `city_text` is **SQL NULL** because you cannot look up key `city` inside JSON null.

### 14.1. Field Is Not an Array

Order 5 has `"items":{"sku":"NOT-AN-ARRAY"}`. The query:

~~~sql
SELECT
    payload -> 'items' -> 0 AS first_item
FROM json_lab_307.orders
WHERE order_id = 5;
~~~

finds no array element and returns **SQL NULL**. However, calling:

~~~sql
-- Raises an error on order 5:
-- SELECT jsonb_array_length(payload -> 'items')
-- FROM json_lab_307.orders WHERE order_id = 5;
~~~

**errors out** because `jsonb_array_length` expects a JSON array, whereas the input is an object. This is a major difference: **extraction operators are lenient on mismatched paths; several JSON processing functions enforce strict type checks**.

### 14.2. Do Not Infer Type from "Index 0 Returned NULL"

If `payload -> 'items' -> 0` returns NULL, the cause could be:

- Empty array;
- Index out of bounds;
- Missing `items` key;
- `items` value is JSON null;
- `items` is an object or scalar rather than an array;
- `payload` itself is SQL NULL.

If business logic needs to know why, query the **structure type** using `jsonb_typeof` and key existence before drawing conclusions.

### 14.3. Inspecting All Cases in the Lab

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload) AS root_type,
    jsonb_typeof(payload -> 'items') AS items_type,
    payload -> 'items' -> 0 ->> 'sku' AS first_sku
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Result:

| order_id | Root type | Items type | First SKU |
| ---: | --- | --- | --- |
| 1 | object | array | BOOK-01 |
| 2 | object | array | MOUSE-01 |
| 3 | object | array | SQL NULL |
| 4 | object | null | SQL NULL |
| 5 | object | object | SQL NULL |
| 6 | SQL NULL | SQL NULL | SQL NULL |

**Do not rely on `first_sku IS NULL` alone to conclude the customer bought nothing**: several kinds of malformed data produce the exact same symptom.

## 15. Filtering by JSON Text Values

With path extraction:

~~~sql
SELECT
    order_id,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

Result: order **1**.

### 15.1. Distinguishing Text Comparison vs. JSON Comparison

These two expressions perform different comparisons:

~~~sql
-- SQL text comparison:
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'customer' ->> 'name' = 'An';

-- JSONB string value comparison:
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'customer' -> 'name' = '"An"'::jsonb;
~~~

Both match order 1, but the right-hand side of the second comparison is a **JSONB string**, including the quotes of a JSON literal. When working with plain text, `->>` is easier to read and parameterize.

### 15.2. Type-Safe Boolean Comparison

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload -> 'paid' = 'true'::jsonb
ORDER BY order_id;
~~~

Result: **1, 3, 4**. This condition requires a JSON boolean `true`, not a JSON string `"true"`.

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ->> 'paid' = 'true'
ORDER BY order_id;
~~~

In the lab dataset both queries happen to return the same set. However, the text query would also match a JSON string `"true"` in inconsistent documents. **If you must enforce type**, use `jsonb_typeof(payload -> 'paid') = 'boolean'` or compare against a JSONB boolean.

### 15.3. Filtering Numbers: Avoid Lexicographical Text Comparisons

~~~sql
-- Wrong for numeric semantics:
-- WHERE payload ->> 'total' > '90000'
~~~

This is a **text** comparison using collation order, not arithmetic. For instance, `'100000'` compares differently from the number 100000 in lexicographical order.

**Correct when numeric data is valid:**

~~~sql
SELECT
    order_id,
    (payload ->> 'total')::numeric AS total_numeric
FROM json_lab_307.orders
WHERE (payload ->> 'total')::numeric >= 100000
ORDER BY order_id;
~~~

Result: **1** and **2**. However, this query is only safe when every `total` value parses as `numeric` or SQL NULL; if a row contains a non-numeric string, the query fails. The next section shows guarded casting patterns.

## 16. Safe Casting After JSON Extraction

A key principle for systems with flexible data:

> **Do not blindly cast an extracted value if the field may be missing or change type.** Verify the JSON type or enforce schema validation before casting.

### 16.1. JSON Numbers Differ from SQL numeric

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'total') AS json_type,
    pg_typeof(payload ->> 'total') AS extracted_sql_type,
    payload ->> 'total' AS extracted_text
FROM json_lab_307.orders
ORDER BY order_id;
~~~

In rows 1–4, `total` is a JSON number. In row 5, `total` is a JSON **string**, even though the extracted text looks numeric. Row 6 is SQL NULL.

### 16.2. Guarding Casts by JSON Type with CASE

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS strict_total_numeric
FROM json_lab_307.orders
ORDER BY order_id;
~~~

In this example, order 5 is treated as **type-invalid**, so `strict_total_numeric` evaluates to SQL NULL even though the string `"50000"` would parse.

### 16.3. Why Use CASE Instead of Two AND Conditions?

A seemingly safe pattern:

~~~sql
-- Do not rely on evaluation order to guard a cast:
-- WHERE jsonb_typeof(payload -> 'total') = 'number'
--   AND (payload ->> 'total')::numeric > 100000
~~~

PostgreSQL can reorder evaluation of Boolean expressions in `WHERE` according to optimization rules. **Do not rely on "the left-hand condition runs first" to prevent a failing cast.**

When guarding a cast that could fail, place it inside `CASE`:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END >= 100000
ORDER BY order_id;
~~~

Result on lab data: **1, 2**.

### 16.4. If Business Rules Allow Numeric Strings

Some JSON sources send `"50000"` instead of `50000`. If business rules allow both, define a **validation rule** before casting.

For example, accepting only simple non-negative numeric strings with an optional decimal fraction:

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        WHEN jsonb_typeof(payload -> 'total') = 'string'
             AND (payload ->> 'total')
                 ~ '^[0-9]+(\.[0-9]+)?$'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS normalized_total
FROM json_lab_307.orders
ORDER BY order_id;
~~~

The regex is only an example of a **simple input policy**; it does not cover negative signs, scientific notation, whitespace, or all business-valid number formats. For monetary amounts, you must also validate **range, precision/scale, currency, and rounding**; a regex does not replace full validation.

### 16.5. Casting JSON Booleans Semantically

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'paid') = 'boolean'
        THEN (payload ->> 'paid')::boolean
        ELSE NULL
    END AS paid_boolean
FROM json_lab_307.orders
ORDER BY order_id;
~~~

If `paid` is the JSON string `"true"`, this rule **does not silently coerce** it to boolean. That is intentional so schema violations surface clearly.

### 16.6. String Timestamps Need Timezone Handling

With JSON:

~~~json
{"shipping":{"requested_at":"2026-11-14T10:30:00+07:00"}}
~~~

Basic conversion:

~~~sql
SELECT
    (
      '{"shipping":{"requested_at":"2026-11-14T10:30:00+07:00"}}'::jsonb
      #>> '{shipping,requested_at}'
    )::timestamptz AS requested_at;
~~~

**Warning:** `::timestamptz` fails on malformed date strings, and a string without an offset/timezone is interpreted using the session's `TimeZone`. To store an unambiguous instant across systems, require a standard format with an explicit timezone/offset and validate on ingestion.

### 16.7. Do Not Compare Numbers as Text

~~~sql
SELECT
    ('100'::text < '9'::text) AS text_comparison,
    (100::numeric < 9::numeric) AS numeric_comparison;
~~~

These two expressions yield opposite results because one compares characters while the other compares numbers. With `ORDER BY payload ->> 'total'`, PostgreSQL sorts by **text**, not numerically. For money and quantities, use proper numeric/integer types.

## 17. Checking Array Length and Type Before Processing

The function:

~~~sql
jsonb_array_length(jsonb_value)
~~~

returns the length of a **JSON array**. However, it raises an error if the input is not an array (for example an object, JSON null, or other scalar).

### 17.1. Valid Case

~~~sql
SELECT
    order_id,
    jsonb_array_length(payload -> 'items') AS item_count
FROM json_lab_307.orders
WHERE order_id IN (1, 2, 3)
ORDER BY order_id;
~~~

Result: order 1 has 2, order 2 has 1, order 3 has 0 elements.

### 17.2. Guarding Across the Whole Dataset

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'items') = 'array'
        THEN jsonb_array_length(payload -> 'items')
        ELSE NULL
    END AS item_count_if_array
FROM json_lab_307.orders
ORDER BY order_id;
~~~

This distinguishes a **valid empty array (0 elements)** from a **field with the wrong type**. If business logic prefers treating any non-array value as empty, `ELSE` could return 0, though you should consider whether that hides data errors.

### 17.3. COALESCE Is Not a Substitute for Type Checking

~~~sql
-- If items is JSON null (distinct from SQL NULL), COALESCE
-- does not replace it with an empty array:
-- jsonb_array_length(COALESCE(payload -> 'items', '[]'::jsonb))
~~~

For order 4, `payload -> 'items'` is **JSONB null** rather than SQL NULL, so `COALESCE` keeps the JSON null value and `jsonb_array_length` still fails. **Use `jsonb_typeof`** when normalizing data types.

## 18. Extracting All Elements with jsonb_array_elements

The `-> 0` operator fits when you want **a specific position**. To list every product in an order, PostgreSQL provides the **set-returning function**:

~~~sql
jsonb_array_elements(jsonb_array)
~~~

It expands the elements of a JSON array into **multiple SQL rows**, each still typed as `jsonb`.

### 18.1. Example Order with a Valid Array

~~~sql
SELECT
    o.order_id,
    item.value AS item_json,
    item.value ->> 'sku' AS sku,
    (item.value ->> 'qty')::integer AS qty
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    AS item(value)
WHERE o.order_id = 1;
~~~

Result has two rows:

| order_id | sku | qty |
| ---: | --- | ---: |
| 1 | BOOK-01 | 2 |
| 1 | PEN-01 | 1 |

### 18.2. What Is LATERAL?

`LATERAL` allows a subquery or table function in `FROM` to **reference columns from rows to its left**, here `o.payload`.

~~~mermaid
flowchart LR
    A["Each orders row o"] --> B["Extract o.payload -> 'items'"]
    B --> C["jsonb_array_elements(...)"]
    C --> D["0..N JSONB rows"]
    D --> E["Extract sku, qty, price"]
    E --> F["Multi-row relational result"]
~~~

With `CROSS JOIN LATERAL`, if the array is empty, the table function returns 0 rows and **the order row does not appear** in the output either.

### 18.3. Watch Out for Wrong Types in Other Rows

Calling `jsonb_array_elements(o.payload -> 'items')` can fail when `items` is an object (order 5) or JSON null (order 4). **Do not rely on `WHERE o.order_id = 1` to "guarantee" safety in every complex query**; with heterogeneous data, normalize the input passed to the table function.

### 18.4. Type-Safe LATERAL Expansion

~~~sql
SELECT
    o.order_id,
    line.item ->> 'sku' AS sku,
    line.item ->> 'qty' AS qty_text
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS line(item)
ORDER BY o.order_id, sku;
~~~

Result:

| order_id | sku | qty_text |
| ---: | --- | --- |
| 1 | BOOK-01 | 2 |
| 1 | PEN-01 | 1 |
| 2 | MOUSE-01 | 1 |

Orders 3–6 produce no item rows because non-array inputs are substituted with an empty array. This is a **lenient read policy**; if you do not want to mask bad data, log/flag `jsonb_typeof(items) != 'array'` for error reporting or auditing at the application layer.

### 18.5. Keeping Orders with No Items Using LEFT JOIN LATERAL

~~~sql
SELECT
    o.order_id,
    line.item ->> 'sku' AS sku
FROM json_lab_307.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS line(item)
ON TRUE
ORDER BY o.order_id, sku;
~~~

With `LEFT JOIN LATERAL ... ON TRUE`, orders with empty or invalid arrays still appear once with a SQL NULL `sku`. This is helpful for reports that **count orders even when they have no items**.

### 18.6. WITH ORDINALITY: Getting Element Positions

~~~sql
SELECT
    o.order_id,
    line.position AS sql_ordinality,
    line.position - 1 AS json_index,
    line.item ->> 'sku' AS sku
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    WITH ORDINALITY AS line(item, position)
WHERE o.order_id = 1
ORDER BY line.position;
~~~

**`WITH ORDINALITY` starts numbering at 1**, like SQL row positions, whereas JSON array indexes **start at 0**:

| sql_ordinality | json_index | sku |
| ---: | ---: | --- |
| 1 | 0 | BOOK-01 |
| 2 | 1 | PEN-01 |

Do not pass `position = 1` directly into `-> 1` expecting the **first element**; by JSON indexing rules that retrieves the second element.

### 18.7. jsonb_array_elements_text

For arrays containing only scalar strings:

~~~sql
SELECT tag.value AS tag
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.payload -> 'tags')
    AS tag(value)
WHERE o.order_id = 1;
~~~

Result: two rows `new` and `vip`, of type `text`. When an array contains objects, `jsonb_array_elements_text` returns text representations of the objects and **does not keep them as `jsonb` for further `->` traversal**.

### 18.8. Query Computing Line Totals per Item

~~~sql
SELECT
    o.order_id,
    li.item ->> 'sku' AS sku,
    (li.item ->> 'qty')::integer AS qty,
    (li.item ->> 'price')::numeric AS unit_price,
    (li.item ->> 'qty')::integer
        * (li.item ->> 'price')::numeric
        AS line_total
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS li(item)
WHERE o.order_id IN (1, 2)
ORDER BY o.order_id, sku;
~~~

Result:

| order_id | sku | qty | price | line_total |
| ---: | --- | ---: | ---: | ---: |
| 1 | BOOK-01 | 2 | 120000 | 240000 |
| 1 | PEN-01 | 1 | 15000 | 15000 |
| 2 | MOUSE-01 | 1 | 320000 | 320000 |

With real data, validate `qty` and `price` before casting and apply business constraints such as non-negativity, precision/scale, and currency codes. This example relies on the **valid item lines in the lab**.

## 19. Mapping an Object to Multiple Columns with jsonb_to_record

To map a **JSON object** to SQL columns with fixed names and types, use `jsonb_to_record`:

~~~sql
SELECT
    o.order_id,
    customer.id,
    customer.name
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_to_record(o.payload -> 'customer')
    AS customer(id integer, name text)
WHERE o.order_id = 1;
~~~

Result: customer ID 101, name An. PostgreSQL matches by field name (`id`/`name`); missing fields become SQL NULL, and fields whose type or value cannot convert to the requested SQL type raise an error.

### 19.1. jsonb_to_recordset for Arrays of Objects

~~~sql
SELECT
    o.order_id,
    li.sku,
    li.qty,
    li.price
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_to_recordset(o.payload -> 'items')
    AS li(sku text, qty integer, price numeric)
WHERE o.order_id IN (1, 2)
ORDER BY o.order_id, li.sku;
~~~

When the input is a valid JSON array of matching objects, this function converts it directly into a typed recordset. **It is not an unconditional replacement for validation**: orders 4 and 5 have `items` as JSON null and object, so you must guard or filter/flag invalid rows before running it across the whole table.

### 19.2. Which Tool Fits Which Need?

| Need | Usually Best Tool |
| --- | --- |
| Read a single nested field | `->`, `->>`, `#>`, `#>>` |
| Access one element by position | `-> integer` or `#> text[]` |
| Expand all array elements | `jsonb_array_elements` |
| Expand scalar array as text | `jsonb_array_elements_text` |
| Convert object to typed columns | `jsonb_to_record` |
| Convert array of objects to typed rows | `jsonb_to_recordset` |
| Search by structural/path pattern | JSONPath or GIN/containment where appropriate |

**Core extraction operators remain the foundation**; set-returning functions simply extend them when JSON data holds multiple elements.

## 20. Iterating Over Object Keys with jsonb_each

When key names are not known ahead of time, `jsonb_each` turns an object into `(key, value)` rows:

~~~sql
SELECT
    kv.key,
    kv.value
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_each(o.payload -> 'customer')
    AS kv(key, value)
WHERE o.order_id = 1
ORDER BY kv.key;
~~~

Result includes keys such as `address`, `contact`, `id`, and `name`. `value` is `jsonb`, so you can continue using `->` if it is an object or array.

### 20.1. jsonb_each_text

~~~sql
SELECT
    kv.key,
    kv.value AS text_value
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_each_text(o.payload -> 'customer')
    AS kv(key, value)
WHERE o.order_id = 1;
~~~

`value` is `text`. Nested objects become their JSON text representation; they do not automatically expand into typed SQL columns or child rows.

### 20.2. Use Only on Valid Objects

`jsonb_each` expects an object; calling it on an array or scalar raises an error. In the lab, `customer` in orders 1–5 is always an object, while order 6 has a SQL NULL payload. With untrusted sources, check `jsonb_typeof` first or enforce constraints.

## 21. text[] Paths and SQL/JSON Paths Are Different Syntaxes

This is a frequent source of confusion when moving from `#>` / `#>>` to JSONPath functions:

| Path Kind | Example | Used By |
| --- | --- | --- |
| PostgreSQL `text[]` path | `'{customer,address,city}'::text[]` | `#>`, `#>>`, `jsonb_extract_path` |
| SQL/JSON `jsonpath` | `'$.customer.address.city'::jsonpath` | `jsonb_path_query_first`, `jsonb_path_exists`, `@?`, `@@` |

**Do not write `payload #>> '$.customer.address.city'`**: `#>>` expects `text[]`, not `jsonpath` or a dot-notation string.

### 21.1. Same Value, Two Path Languages

~~~sql
SELECT
    payload #>> '{customer,address,city}'
        AS city_by_text_array,
    jsonb_path_query_first(
        payload,
        '$.customer.address.city'
    ) AS city_by_jsonpath
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Key differences:

- `city_by_text_array` is **SQL text**.
- `jsonb_path_query_first` returns **`jsonb`** (a JSON string).

To obtain text from a JSONPath result, you need an appropriate conversion step once the value type is known, or simply use `#>>` when the exact path is already known.

### 21.2. JSONPath Has Wildcards; text[] Paths Do Not

~~~sql
SELECT
    jsonb_path_query_first(
        payload,
        '$.items[*].sku'
    ) AS one_sku_as_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`[*]` is a wildcard selecting array elements in JSONPath. In `'{items,*,sku}'::text[]`, `*` **does not act as a wildcard** for `#>`; it is treated as a literal text key `' * '` and will not iterate over all array elements.

### 21.3. Returning Multiple JSONPath Matches

~~~sql
SELECT
    o.order_id,
    sku.value AS sku_json
FROM json_lab_307.orders AS o
CROSS JOIN LATERAL
    jsonb_path_query(
        o.payload,
        '$.items[*].sku'
    ) AS sku(value)
WHERE o.order_id = 1;
~~~

On order 1, this returns two JSONB strings `"BOOK-01"` and `"PEN-01"`. For queries needing **quantity and price columns** for each object, `jsonb_array_elements` or `jsonb_to_recordset` is usually more direct.

### 21.4. JSONPath lax vs. strict Modes

SQL/JSON path in PostgreSQL supports **lax** and **strict** structural modes. In lax mode, PostgreSQL may automatically adapt minor structural mismatches (such as wrapping or unwrapping arrays in appropriate cases); strict mode requires an exact structural match and raises errors otherwise.

**Do not assume JSONPath `$.items[*].sku` and `#> '{items,0,sku}'` behave identically on mistyped data such as `items` being an object in order 5.** JSONPath and `text[]` path operators have different semantics and leniency.

### 21.5. Keys Containing Dots in JSONPath

~~~sql
SELECT
    payload #>> ARRAY['a.b', 'x y']::text[]
        AS by_text_array,
    jsonb_path_query_first(
        payload,
        '$."a.b"."x y"'
    ) AS by_jsonpath
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

In JSONPath, wrap keys in double quotes so `a.b` is treated as **a single key** instead of two path levels. Again, `#>>` returns text while the JSONPath function in this example returns JSONB.

### 21.6. Version Support

JSONPath operators and functions such as `@?`, `@@`, and `jsonb_path_query` were introduced in PostgreSQL 12; do not assume they exist on older servers. The four operators `->` / `->>` / `#>` / `#>>` form the baseline for deterministic path access.

## 22. Searching by Path with JSONPath and Supporting Operators

When you only want a specific value, `#>>` is usually most readable. When you want to ask "**does any element in the array satisfy a condition?**", JSONPath can be a better fit:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @? '$.items[*] ? (@.sku == "BOOK-01")'
ORDER BY order_id;
~~~

On the lab data, the result is order **1**.

### 22.1. @? Differs from the Single ? Operator

- `payload ? 'coupon'`: checks whether a key/element exists **at the top level** of the current JSONB value.
- `payload @? '$.items[*] ? (...)'`: checks whether a **JSONPath** returns any matching item.

The two operators look similar in name but take different operand types and have different semantics.

### 22.2. @@ Evaluates a JSONPath Predicate

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @@ '$.paid == true'
ORDER BY order_id;
~~~

`@@` evaluates a JSONPath predicate and interprets the Boolean outcome under JSONPath semantics. On uniform data like the lab set, it matches orders 1, 3, and 4. Type mismatches, JSON null, and lax-mode behavior must be tested before relying on it for critical access rules.

### 22.3. Pick the Right Tool for the Goal

If you only need `customer.address.city`, do not pull in a JSONPath engine just because the syntax looks familiar. When you need to filter array elements across multiple conditions or traverse wildcards, JSONPath can reduce manual boilerplate.

### 22.4. Never Concatenate Untrusted JSONPath into SQL

Dynamic JSONPath expressions should be passed as a **parameterized value of type `jsonpath`** in queries, never built by string concatenation from user input. Beyond SQL injection, you must also restrict **which paths a user is permitted to read**, because a JSON document may hold sensitive fields in other branches.

## 23. jsonb_extract_path and jsonb_extract_path_text

PostgreSQL provides two functions that express paths as variadic text arguments:

~~~sql
jsonb_extract_path(jsonb_value, VARIADIC text[])
jsonb_extract_path_text(jsonb_value, VARIADIC text[])
~~~

In purpose:

- `jsonb_extract_path` corresponds to `#>` for JSONB extraction.
- `jsonb_extract_path_text` corresponds to `#>>` for text extraction.

### 23.1. Example with Multiple Key Arguments

~~~sql
SELECT
    order_id,
    jsonb_extract_path(
        payload, 'customer', 'address', 'city'
    ) AS city_json,
    jsonb_extract_path_text(
        payload, 'customer', 'address', 'city'
    ) AS city_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 23.2. Comparing Function vs. Operator

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']
        AS via_operator,
    jsonb_extract_path_text(
        payload,
        'customer',
        'address',
        'city'
    ) AS via_function
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Both extract the text `Hà Nội` in this example. Choose whichever is cleaner to read and parameterize in your application, then inspect the plan if it is a performance-critical query path.

### 23.3. Passing an Existing Path Array

~~~sql
SELECT
    jsonb_extract_path_text(
        payload,
        VARIADIC ARRAY['customer','address','city']::text[]
    ) AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

With `VARIADIC text[]`, you can pass an array of path components instead of listing them one by one. The `#>>` operator is usually more concise:

~~~sql
SELECT
    payload #>> ARRAY['customer','address','city']::text[] AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

### 23.4. Matching Functions for the json Type

If the source is `json` instead of `jsonb`, PostgreSQL provides `json_extract_path` and `json_extract_path_text`. Match the function signature to the actual column type; there is no need to cast to `jsonb` merely to use a basic `#>>` extraction.

## 24. Dynamic Paths and Prepared Statements

Sometimes an application lets callers choose among a set of allowed fields:

~~~text
customer.address.city
customer.contact.email
customer.name
~~~

Instead of concatenating strings into SQL, pass an **array of path components**:

~~~sql
PREPARE find_orders_by_json_path(text[], text) AS
SELECT order_id
FROM json_lab_307.orders
WHERE payload #>> $1 = $2
ORDER BY order_id;

EXECUTE find_orders_by_json_path(
    ARRAY['customer','address','city']::text[],
    'Hà Nội'
);

DEALLOCATE find_orders_by_json_path;
~~~

Result: order **1**.

### 24.1. Benefits

- Keys and paths are sent as **data values**, not SQL source code.
- No manual construction of `'{"a","b"}'` literals with complex escaping.
- Easy to enforce depth limits, allowed fields, and result types.
- Eliminates SQL injection risk from ad-hoc string concatenation.

### 24.2. Parameterization Does Not Replace Authorization

If the application lets callers pass **any arbitrary path** into JSON, users might probe fields not meant for them (such as private contact details or internal metadata).

Maintain a **path allowlist** in the API and enforce access control on the underlying SQL/JSON data. Bound parameters only make SQL syntactically safe; they **do not enforce business authorization**.

### 24.3. Dynamic Paths May Not Use Fixed Expression Indexes

An expression index on:

~~~sql
payload #>> '{customer,address,city}'
~~~

is built for **one specific path**. A query with `payload #>> $1::text[]` will not automatically be matched by the optimizer to that expression for **arbitrary** values of `$1` in a generic plan.

If a few key fields need indexing, create dedicated indexes for those access paths and keep query predicates matching; do not expect a single B-tree expression index to accelerate arbitrary dynamic paths.

## 25. ORDER BY and GROUP BY Queries on JSON Fields

### 25.1. GROUP BY City

~~~sql
SELECT
    payload #>> '{customer,address,city}' AS city,
    COUNT(*) AS orders_count
FROM json_lab_307.orders
WHERE payload IS NOT NULL
GROUP BY payload #>> '{customer,address,city}'
ORDER BY city NULLS LAST;
~~~

Orders 4 and 5 lack a readable `city`, so they fall into the **SQL NULL** group during grouping. This highlights why **missing fields** must be distinguished from empty city strings.

### 25.2. GROUP BY with a Fallback Label

~~~sql
SELECT
    COALESCE(
        payload #>> '{customer,address,city}',
        '<unknown>'
    ) AS city_bucket,
    COUNT(*) AS orders_count
FROM json_lab_307.orders
GROUP BY
    COALESCE(
        payload #>> '{customer,address,city}',
        '<unknown>'
    )
ORDER BY city_bucket;
~~~

Good for display reports, though it merges missing `city`, JSON null, and SQL NULL documents into `'<unknown>'`. For data quality analysis, separate error buckets using `CASE` and `jsonb_typeof`.

### 25.3. Numeric ORDER BY Must Use a Numeric Type

~~~sql
SELECT
    order_id,
    CASE
        WHEN jsonb_typeof(payload -> 'total') = 'number'
        THEN (payload ->> 'total')::numeric
        ELSE NULL
    END AS total_numeric
FROM json_lab_307.orders
ORDER BY total_numeric DESC NULLS LAST, order_id;
~~~

Writing `ORDER BY payload ->> 'total'` sorts by **text** and produces wrong orderings for numeric values.

### 25.4. Do Not Assume Every Path Has a Stable Column Schema

A `city` field could be text in one row and an object or array in another if unconstrained. `#>>` returns the text representation of an object/array; grouping on it creates buckets of serialized text that may have no business meaning. Check JSON types or enforce schemas at the source.

## 26. Creating a B-tree Expression Index for a Path

If city queries run frequently and the table is large enough, consider an expression index:

~~~sql
CREATE INDEX idx_orders_customer_city_307
ON json_lab_307.orders (
    (payload #>> '{customer,address,city}')
);
~~~

### 26.1. Usage

~~~sql
EXPLAIN
SELECT
    order_id,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

Because the index stores the result of `#>> '{customer,address,city}'`, PostgreSQL can use a B-tree equality lookup when the query uses a matching expression.

### 26.2. Queries Must Match the Indexed Expression

An index on `#>> '{customer,address,city}'` is not automatically used for every query that looks semantically equivalent:

~~~sql
WHERE payload -> 'customer' -> 'address' ->> 'city'
      = 'Hà Nội'
~~~

Both forms return the same result on valid documents, but the optimizer **is not obligated to deduce all structural equivalences across extraction operators** to match an expression index. On indexed query paths, standardize on one expression form and verify with `EXPLAIN`.

### 26.3. Expression Indexes Are Not Free

When `INSERT` or `UPDATE` modifies referenced columns, PostgreSQL must compute and maintain the extracted index key. Creating too many indexes for rarely queried JSON fields will:

- Increase index storage and WAL;
- Slow down `INSERT` and `UPDATE`;
- Reduce HOT update eligibility;
- Increase VACUUM and maintenance work;
- Incur expression evaluation overhead across rows.

**Do not index every path just because JSON has many keys.** Prioritize frequently queried, selective predicates.

### 26.4. Tiny Lab Tables

With only six rows, `EXPLAIN` can choose `Seq Scan` even after creating the expression index. This is a **rational cost decision**, not proof that the index is broken. Benchmarks require representative data volumes and distributions.

### 26.5. Indexing Extracted Numeric Values

If `total` has a schema requiring a JSON number, consider:

~~~sql
CREATE INDEX idx_orders_total_numeric_307
ON json_lab_307.orders (
    ((payload ->> 'total')::numeric)
);
~~~

In the current lab, order 5's JSON string `"50000"` still parses to numeric, so index creation succeeds. However, a new insert containing `"total":"error"` causes index key computation to fail and aborts the write statement.

If you want to enforce **JSON numbers only**, add explicit constraints/validation instead of relying on a cast that "happens to accept" numeric strings.

### 26.6. Do Not Index Non-IMMUTABLE Functions

PostgreSQL requires functions in expression indexes to have proper immutability. Fixed JSON extraction on `jsonb` satisfies this; however, wrapping it in a UDF that depends on other tables, session timezones, or the current clock while falsely marking it `IMMUTABLE` can leave stale keys in the index.

## 27. GIN Indexes for Containment and Key/Path Operators

In some workloads, rather than querying **a fixed path**, you want to ask whether a JSONB document contains a given structure:

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @> '{"paid":true}'::jsonb
ORDER BY order_id;
~~~

`@>` is the **JSONB containment** operator: whether the left-hand document contains the structure/value on the right under JSONB containment semantics.

### 27.1. Full-Column GIN Index on jsonb

~~~sql
CREATE INDEX idx_orders_payload_gin_307
ON json_lab_307.orders
USING gin (payload);
~~~

A GIN index can support JSONB search patterns such as containment, key existence, and certain JSONPath queries depending on the operator class. It serves a different purpose from a B-tree index on `payload #>> '{customer,address,city}'`.

### 27.2. Containment on Nested Objects

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload @> $json$
{
  "customer": {
    "address": {"city": "Hà Nội"}
  }
}
$json$::jsonb;
~~~

Result: order **1**.

### 27.3. jsonb_ops and jsonb_path_ops

Common GIN operator classes:

| Operator Class | General Characteristics |
| --- | --- |
| `jsonb_ops` | Default; supports broad JSONB operators including top-level key existence `?` and containment |
| `jsonb_path_ops` | More compact/optimized for some containment and JSONPath workloads; does not support key-existence operators like `jsonb_ops` |

Optional alternative:

~~~sql
CREATE INDEX idx_orders_payload_pathops_307
ON json_lab_307.orders
USING gin (payload jsonb_path_ops);
~~~

Do not keep both GIN indexes in production without evidence of need. They consume disk and add write overhead; choose the operator class based on **actual `WHERE` operators**.

### 27.4. Do Not Confuse @> with -> and #>>

- `payload #>> '{customer,address,city}'`: **extracts a text value**.
- `payload @> '{"customer":{"address":{"city":"Hà Nội"}}}'`: **checks containment**, returning boolean.

A full-column GIN index can accelerate `@>`, but does not automatically let PostgreSQL look up the text expression `#>>` like a dedicated B-tree index. Conversely, a B-tree on city text does not support arbitrary JSONB containment or path predicates.

### 27.5. JSONPath and GIN Do Not Automatically Accelerate Every Query

Some JSONPath predicates can extract indexable search conditions for GIN; complex path expressions, wildcards, or unsupported conditions may not use the index effectively. **`EXPLAIN` and realistic data** remain essential.

## 28. Choosing an Index Type by Actual SQL Pattern

| Common SQL | Candidate Index |
| --- | --- |
| `WHERE payload #>> '{customer,address,city}' = 'Hà Nội'` | B-tree expression index on the exact `#>>` path |
| `WHERE payload ->> 'status' = 'paid'` | B-tree expression index on `payload ->> 'status'` |
| `WHERE payload @> '{"paid":true}'::jsonb` | GIN on `payload` |
| `WHERE payload ? 'coupon'` | GIN `jsonb_ops` on `payload` when beneficial |
| `WHERE payload @? '$.items[*] ? (...)'` | GIN can support certain indexable path predicates |
| `WHERE (payload ->> 'total')::numeric > 100000` | B-tree numeric expression index if data is validated and query is frequent |
| `ORDER BY created_at DESC LIMIT 20` | B-tree on the **`created_at` column** is usually better than a JSON index |

### 28.1. Query Plans and Statistics

~~~sql
ANALYZE json_lab_307.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab_307.orders
WHERE payload #>> '{customer,address,city}' = 'Hà Nội';
~~~

`EXPLAIN ANALYZE` executes the SQL statement. Safe to demonstrate on a small lab `SELECT`; for DML or `SELECT` statements containing side-effecting functions, assess impact before enabling `ANALYZE`.

### 28.2. Inspecting Index Definitions

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'json_lab_307'
ORDER BY tablename, indexname;
~~~

Verify the **exact expression**, operator class, partial predicate, and return type. Never rely on a name like `idx_city` to guess which key was indexed.

### 28.3. A Dynamic Path May Not Use a Fixed Expression Index

If the application passes an arbitrary path like `'{customer,address,city}'` today and `'{customer,contact,email}'` tomorrow, a B-tree on the city path does not serve the email path. Define important fields as fixed access paths, or consider relational columns or GIN when the workload justifies it.

## 29. JSONB Subscripting: Another Syntax for Nested Reads

Modern PostgreSQL versions (PostgreSQL 14 and later) support **JSONB subscripting**:

~~~sql
SELECT
    payload['customer']['address']['city']
        AS city_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

This returns the **`jsonb`** value corresponding to the JSON string `"Hà Nội"`. The syntax resembles object/array access in programming languages, with key caveats:

- Keys use **SQL strings** like `'customer'`, not unquoted identifiers.
- JSON array indexes still start at **0**.
- Basic subscripting **returns JSONB**, not the text type produced by `->>` / `#>>`.
- Syntax availability depends on **major version**, and assignment semantics differ from native SQL arrays.

### 29.1. Accessing Array Elements with Subscripting

~~~sql
SELECT
    payload['items'][0]['sku'] AS sku_json
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

This returns a JSONB string value. If the API needs a SQL string, `payload #>> '{items,0,sku}'` or `payload -> 'items' -> 0 ->> 'sku'` is usually clearer.

### 29.2. Do Not Mix Up Return Types

~~~sql
SELECT
    pg_typeof(payload['customer']['name']) AS subscript_type,
    pg_typeof(payload -> 'customer' ->> 'name') AS arrow_text_type
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`subscript_type` is `jsonb`, whereas `arrow_text_type` is `text`.

### 29.3. Index Expressions Must Match Queries

An index on `payload #>> '{customer,address,city}'` does not automatically mean PostgreSQL treats every subscripting expression as equivalent and uses the same index. Standardize key SQL expressions and verify with `EXPLAIN`.

## 30. Paths When Updating JSON: Related but Different from Reading

When updating a nested value, PostgreSQL provides `jsonb_set`:

~~~sql
jsonb_set(target jsonb, path text[], new_value jsonb, create_if_missing boolean)
~~~

The `text[]` path looks identical to `#>` / `#>>`, but the action differs: it replaces part of the JSONB value and returns a **new JSONB document**.

### 30.1. Lab UPDATE with Rollback

~~~sql
BEGIN;

UPDATE json_lab_307.orders
SET payload = jsonb_set(
    payload,
    '{customer,address,city}',
    to_jsonb('Huế'::text),
    false
)
WHERE order_id = 1;

SELECT
    order_id,
    payload #>> '{customer,address,city}' AS new_city
FROM json_lab_307.orders
WHERE order_id = 1;

ROLLBACK;
~~~

Inside the transaction, `new_city = Huế`; after `ROLLBACK`, the data reverts to `Hà Nội`.

### 30.2. Non-Existent Intermediate Paths

`create_if_missing` does not mean PostgreSQL automatically creates **every missing intermediate object** along a deep path. If `customer` or `address` is missing or has the wrong type, define explicit update logic and structure checks.

### 30.3. Do Not Turn a Read Operation into a Data Mutation

`->`, `->>`, `#>`, `#>>` in `SELECT` **do not modify JSON**. `jsonb_set`, JSONB subscripting assignment, or `UPDATE` is a write operation subject to MVCC, WAL, locks, and index maintenance.

Never implement a "read by updating an auxiliary value" workflow just to inspect a nested field.

## 31. Controlling JSON Schema and Data Quality

JSONB is flexible, but that does not mean data needs no schema. Define:

- Must the root be an object, or can it be an array/scalar?
- Must `customer.id` be a number/integer, and is it a foreign key?
- Can `customer.address.city` be missing or null?
- Must `items` be an array, and can it be empty?
- Inside `items`, must `qty`/`price` be positive numbers, or could they arrive as strings?
- Is `total` a number or a numeric string? Who keeps it consistent with item totals?
- How does a missing `coupon` differ from JSON null?
- Are there PII fields that must be hidden from arbitrary path queries?

### 31.1. A CHECK Constraint for the Root

If business logic allows SQL NULL, but when JSON is present the root must be an object:

~~~sql
ALTER TABLE json_lab_307.orders
ADD CONSTRAINT ck_orders_payload_root_object_307
CHECK (
    payload IS NULL
    OR jsonb_typeof(payload) = 'object'
);
~~~

This constraint passes on all six lab rows: 1–5 are objects, 6 is SQL NULL. It **only validates the root**, not nested fields inside.

### 31.2. Constraint for items Once Data Is Clean

Concept:

~~~sql
-- Apply ONLY AFTER fixing rows with mistyped items.
-- In the current lab, orders 4 and 5 would fail this CHECK.
--
-- ALTER TABLE json_lab_307.orders
-- ADD CONSTRAINT ck_items_are_arrays
-- CHECK (
--     payload IS NULL
--     OR NOT (payload ? 'items')
--     OR jsonb_typeof(payload -> 'items') = 'array'
-- );
~~~

Do not add constraints and blindly delete "broken" rows without a business decision. You may need to clean existing records or quarantine invalid ones for reconciliation.

### 31.3. Simple Numeric Type Constraint

To require `total`, when present, to be a JSON number:

~~~sql
-- Conceptual example; blocked by order 5 in the lab:
--
-- ALTER TABLE json_lab_307.orders
-- ADD CONSTRAINT ck_total_is_number
-- CHECK (
--     payload IS NULL
--     OR NOT (payload ? 'total')
--     OR jsonb_typeof(payload -> 'total') = 'number'
-- );
~~~

This CHECK does not enforce non-negativity or monetary bounds; additional business rules must still be defined.

### 31.4. When customer_id Is Critical Relational Data

If `customer.id` must link to `customers(customer_id)`, you cannot expect `payload #>> '{customer,id}'` to provide the full foreign-key guarantees of a regular SQL column.

When referential integrity, joins, and unique constraints are central, consider **promoting `customer_id` to a typed column** (or an appropriate stored generated field, subject to immutability constraints) and applying explicit constraints.

### 31.5. Do Not Let Raw JSON Dictate All API Response Types

If clients expect `total` as a number while some records contain strings, the API must:

1. Enforce the schema at ingestion;
2. Or validate and normalize before returning;
3. Or return a controlled data error;
4. Never silently turn an invalid string into zero.

Differences between JSON null, missing, and SQL NULL must be documented in the data contract.

## 32. Pattern for Classifying Anomalous Data

### 32.1. Classifying items

~~~sql
SELECT
    order_id,
    CASE
        WHEN payload IS NULL THEN 'sql_null_document'
        WHEN jsonb_typeof(payload) <> 'object'
             THEN 'unexpected_root_type'
        WHEN NOT (payload ? 'items')
             THEN 'missing_items_key'
        WHEN jsonb_typeof(payload -> 'items') = 'null'
             THEN 'json_null_items'
        WHEN jsonb_typeof(payload -> 'items') = 'array'
             THEN 'valid_array'
        ELSE 'wrong_items_type'
    END AS items_status
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Expected output:

| order_id | items_status |
| ---: | --- |
| 1 | valid_array |
| 2 | valid_array |
| 3 | valid_array |
| 4 | json_null_items |
| 5 | wrong_items_type |
| 6 | sql_null_document |

This query pattern is useful for **auditing incoming data** without collapsing distinct states behind `COALESCE(..., '[]')`.

### 32.2. Classifying coupon

~~~sql
SELECT
    order_id,
    CASE
        WHEN payload IS NULL
             THEN 'sql_null_document'
        WHEN NOT (payload ? 'coupon')
             THEN 'missing_coupon'
        WHEN jsonb_typeof(payload -> 'coupon') = 'null'
             THEN 'json_null_coupon'
        WHEN jsonb_typeof(payload -> 'coupon') = 'string'
             THEN 'coupon_code'
        ELSE 'wrong_coupon_type'
    END AS coupon_status
FROM json_lab_307.orders
ORDER BY order_id;
~~~

Output:

| order_id | coupon_status |
| ---: | --- |
| 1 | json_null_coupon |
| 2 | coupon_code |
| 3 | missing_coupon |
| 4 | missing_coupon |
| 5 | json_null_coupon |
| 6 | sql_null_document |

### 32.3. Aggregating Record Counts by Error Category

~~~sql
WITH classification AS (
    SELECT
        CASE
            WHEN payload IS NULL THEN 'sql_null_document'
            WHEN NOT (payload ? 'items') THEN 'missing_items'
            WHEN jsonb_typeof(payload -> 'items') = 'array'
                 THEN 'array'
            WHEN jsonb_typeof(payload -> 'items') = 'null'
                 THEN 'json_null'
            ELSE 'wrong_type'
        END AS kind
    FROM json_lab_307.orders
)
SELECT kind, COUNT(*) AS row_count
FROM classification
GROUP BY kind
ORDER BY kind;
~~~

This query groups records without calling `jsonb_array_length` on non-array values, avoiding mid-query errors.

## 33. Java/JDBC Integration: Returning Properly Typed Text or JSON

In a Java application, if you only need one text field, let PostgreSQL extract `text` via `#>>` and read it with `ResultSet.getString`.

### 33.1. PreparedStatement with a Fixed Path

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JsonOrderQueries {
    public static String findCity(Connection connection, long orderId)
            throws SQLException {
        String sql = """
            SELECT payload #>> '{customer,address,city}' AS city
            FROM json_lab_307.orders
            WHERE order_id = ?
            """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, orderId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // order_id does not exist.
                }
                return rs.getString("city");
                // NULL here could be a missing path, JSON null, or
                // a SQL NULL document; they cannot be distinguished here.
            }
        }
    }
}
~~~

This example uses Java text blocks (Java 15+). On older Java versions, replace with valid Java string concatenation.

### 33.2. Passing a text[] Path from Java

~~~java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class JsonPathLookup {
    public static void findOrdersByCity(Connection conn)
            throws SQLException {
        String sql = """
            SELECT order_id, payload #>> ?::text[] AS city
            FROM json_lab_307.orders
            WHERE payload #>> ?::text[] = ?
            ORDER BY order_id
            """;

        String[] components = {"customer", "address", "city"};
        Array sqlPath = conn.createArrayOf("text", components);

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setArray(1, sqlPath);
            ps.setArray(2, sqlPath);
            ps.setString(3, "Hà Nội");

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long orderId = rs.getLong("order_id");
                    String city = rs.getString("city");
                    System.out.println(orderId + ": " + city);
                }
            }
        } finally {
            sqlPath.free();
        }
    }
}
~~~

**Note:** `?::text[]` is a JDBC `?` placeholder followed by a PostgreSQL cast. All paths and comparison values are passed via bound parameters; no SQL strings are concatenated from requests.

### 33.3. Restricting Dynamic Paths with an Allowlist

~~~java
import java.util.Map;

Map<String, String[]> allowedPaths = Map.of(
    "customerName", new String[]{"customer", "name"},
    "customerCity", new String[]{"customer", "address", "city"},
    "contactEmail", new String[]{"customer", "contact", "email"}
);
~~~

The API can accept a logical field name such as `customerCity`, look it up in a controlled map, and pass the corresponding `String[]` to `createArrayOf("text", ...)`. Avoid letting clients send arbitrary paths that could expose restricted data.

### 33.4. Choosing -> vs. ->> in APIs

~~~sql
SELECT
    payload -> 'customer' AS customer_json,
    payload ->> 'paid' AS paid_text
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

`customer_json` is PostgreSQL `jsonb`; the driver may return a driver-specific type such as `PGobject` from `getObject`, depending on driver and configuration. `paid_text` is `text`, so `getString` returns `"true"` as a Java string (not a Java `boolean`).

Do not call `String paid = rs.getString("paid_text")` and assume it is a typed boolean; if the API needs a boolean, cast and validate in SQL or Java per the data contract.

### 33.5. Reading SQL NULL from ResultSet

~~~java
String city = rs.getString("city");
if (city == null) {
    // Could be a missing key, JSON null, or SQL NULL document.
}
~~~

With `getString`, SQL NULL maps to Java `null`. When using primitive getters like `getInt` or `getBoolean`, check `rs.wasNull()` right after the getter whenever SQL NULL is meaningful.

### 33.6. Application-Side JSON Parsing Still Has Its Place

If an API needs the full object or complex validation across large arrays, a Java library like Jackson is appropriate for parsing JSON returned from the database. Still, do not ship **the entire JSONB payload** by default when you only need a city or SKU: extracting fields in SQL reduces network traffic and application parsing overhead.

## 34. Querying JSON: Performance, Consistency, and Storage Cost

### 34.1. Fetch Only Needed Fields

~~~sql
SELECT
    order_id,
    payload #>> '{customer,name}' AS customer_name,
    payload #>> '{customer,address,city}' AS city
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Avoid `SELECT payload` if the client only displays two fields. For large JSON documents, projecting only needed fields cuts network and serialization cost.

### 34.2. JSONB Does Not Automatically Index Every Field

A `jsonb` column lets you read many fields, yet PostgreSQL does not automatically create a B-tree on every path. If city queries are slow, check:

- How many rows exist, and how selective is `city`?
- Does the query match an expression index?
- Can it be rewritten as containment with GIN?
- Is the data uniform enough to cast safely?
- What is the index maintenance cost vs. read benefit?

### 34.3. Avoid Disabling Indexes with Expression Transformations

If an index stores `payload #>> '{customer,address,city}'`, a query filtering on `lower(payload #>> '{customer,address,city}')` uses a **different expression**. If case-insensitive lookup is genuinely common, you may need an index on `lower(...)`, mindful of collation and immutability rules.

### 34.4. JSONB Updates Can Rewrite Tuples

Replacing a deeply nested field via `jsonb_set` in an `UPDATE` is still an MVCC write operation. It is not "updating a few bytes in place without index or WAL work" in all cases. When JSONB documents are large and updates are frequent, consider moving volatile fields to relational columns or child tables.

### 34.5. Flexible Schemas Still Require Versioning Discipline

If clients wrote `address.city` in schema v1 and schema v2 moves it to `shipping.address.city`, `#>> '{customer,address,city}'` only reads v1. You need:

- Explicit schema versions and contracts;
- Migrations or deliberate backward-compatible queries;
- Metrics on missing and mistyped field rates;
- Never silently collapsing bad rows into NULL and ignoring them.

### 34.6. Do Not Rely on JSONB Object Key Order

`jsonb` does not preserve input object key order. If line-item order matters, store items in a **JSON array** and use indexes or `WITH ORDINALITY`. Never try to use object key order to represent business ordering.

### 34.7. Do Not Treat PostgreSQL as a Universal JSON Search Engine

JSONB excels at storing and querying semi-structured data, but full-text search, massive analytical aggregations, or queries requiring heavy joins and constraints may fit better in relational columns, full-text indexes, materialized views, or dedicated analytics systems. Let the workload and data model guide the choice.

## 35. Verification Workflow for a JSON Extraction Query

Before shipping a query using `->` / `#>>` to production, ask:

1. **Is the root `json` or `jsonb`?** What SQL type does the operator return?
2. **Is the field an object or an array?** Is the path component a text key or an integer index?
3. **Do you want JSON or SQL text?** Choose `->` / `#>` vs. `->>` / `#>>`.
4. **Is a missing key distinct from JSON null?** Do you need `?` or `jsonb_typeof`?
5. **Can the field have the wrong type?** Does casting need `CASE` or schema validation?
6. **Can the JSON array be empty?** Should you index element 0 or expand with `LATERAL`?
7. **Must array order be preserved?** Use `WITH ORDINALITY`.
8. **Do path keys contain special characters?** Use `ARRAY[...]::text[]` or quote JSONPath keys properly.
9. **Is an index needed?** Which predicates run frequently? B-tree expression or GIN?
10. **What access controls are needed?** Are there PII fields or user-controlled paths?
11. **Is the SQL parameterized?** Avoid concatenating dynamic SQL strings.
12. **Is the schema versioned?** How must the query handle older versions?
13. **Has it been measured with `EXPLAIN` on realistic volume?** Do not judge plans from a handful of lab rows.
14. **Do return types match the API contract?** For example, numeric/boolean instead of raw text?
15. **Should the field become a relational column?** Especially if it needs FKs, constraints, or frequent updates.

## 36. Common Mistakes

| Mistake / Misconception | Consequence | Fix |
| --- | --- | --- |
| `->` and `->>` are the same | Wrong SQL type, broken comparisons/casts | `->` keeps JSON; `->>` returns text |
| Using `->>` mid-chain then `->` | Operator error on `text` | Use `->` for intermediate steps |
| Writing `payload #>> 'a.b.c'` | Not a `text[]` path | `#>> '{a,b,c}'` or `ARRAY[...]` |
| Writing `payload -> "name"` | Double quotes denote a SQL identifier | Use `'name'` |
| Treating `'a.b'` as two path levels | Extracts the wrong field | `-> 'a.b'` is a single key |
| Assuming JSON array index starts at 1 | Off-by-one element access | JSON indexes start at 0 |
| Assuming `WITH ORDINALITY` starts at 0 | Off-by-one position | Ordinality starts at 1 |
| Assuming `-1` is the first element | Gets the wrong item | Negative indexes count from the end |
| Assuming a missing key throws an error | Misinterpreting SQL NULL | Extraction operators normally return NULL when a path fails |
| Treating JSON null and SQL NULL identically | Cannot distinguish missing vs. null | Inspect with `IS NULL`, `?`, `jsonb_typeof` |
| Expecting `->>` to preserve missing vs. JSON null | Information lost | Use `?` / `->` before converting to text |
| Using `= NULL` to match NULL | Evaluates to SQL UNKNOWN | Use `IS NULL` |
| Thinking `'null'` is JSON null | Wrong value type | Distinguish JSON string from JSON null |
| Treating empty string `''` like NULL | Breaks business semantics | Explicitly check for empty text |
| Calling `jsonb_array_length` on objects/null | Query errors out | Guard with `jsonb_typeof` |
| Expecting `COALESCE(jsonb_null, '[]')` to return empty array | JSON null is not SQL NULL | Use `CASE` on JSON type |
| Assuming `payload -> 'items' -> 0 IS NULL` means 0 items | Wrong when `items` is an object or null | Classify type first |
| Running `jsonb_array_elements` across all rows | Fails when a field is not an array | Normalize or validate input |
| Using `CROSS JOIN LATERAL` and expecting empty orders | Orders with no items are dropped | Use `LEFT JOIN LATERAL` if needed |
| Treating `jsonb_to_recordset` as a validator | Casts can error or accept bad data | Perform separate schema validation |
| Writing `payload ->> 'total' > '90000'` | Lexicographical text comparison | Guard and cast to numeric |
| Assuming `WHERE` guards evaluate strictly left-to-right | Cast can still fail due to optimizer reordering | Use `CASE` or constraints |
| Checking `jsonb_typeof(...) = 'number'` without handling null | SQL NULL still arises | Define missing/null behavior explicitly |
| Treating `#>>` and JSONPath `$.x.y` as the same syntax | Type/semantics errors | `text[]` path differs from `jsonpath` |
| Writing `'{items,*,sku}'` to match all items | `*` is not a wildcard in `text[]` | Use JSONPath `$.items[*].sku` or `LATERAL` |
| Assuming JSONPath lax/strict matches `#>` | Behavior differs on malformed structures | Pick the needed mode and test edge cases |
| Expecting `?` to search keys at all nesting depths | Only checks the current level | Traverse into child objects or use JSONPath |
| Assuming JSONB auto-indexes every key | Seq Scan may occur | Add B-tree expression or GIN per workload |
| Assuming GIN on payload optimizes every `#>>` | Different operator/access pattern | Add an expression index when warranted |
| Expecting a B-tree on city to help arbitrary dynamic paths | Fixed index key | Index primary fields or use another index type |
| Assuming `EXPLAIN ANALYZE` is always read-only | Executes the SQL, including DML | Test safely on lab `SELECT` queries |
| Concatenating user-supplied JSONPath into SQL | SQL injection and data exposure | Bind parameters + allowlist + authorization |
| Assuming JSONB preserves object key order | Key order is not guaranteed | Use a JSON array for ordered data |
| Assuming JSONB replaces all FKs and constraints | Missing relational integrity | Store critical fields in typed columns |
| Using `COALESCE(..., '')` to hide all errors | Masks missing/null/wrong-type issues | Classify and report data quality |

## 37. Practice Exercises

The exercises below use `json_lab_307.orders` unless standalone JSON literals are specified. Some ask you to **predict errors**; intentionally broken queries do not all need to be executed. Whenever requested, state the **SQL type** of the result.

### Exercise 1 — Extracting a Root Key with ->

Write a query to retrieve `payload -> 'customer'` for order 1.

**Question:** is the result SQL text or JSONB? Which keys does it contain?

**Hint:** `->` preserves `jsonb`; `customer` is an object with `id`, `name`, `contact`, and `address`.

### Exercise 2 — Getting Customer Name as Text

Retrieve the customer name for order 1 using:

~~~sql
SELECT payload -> 'customer' ->> 'name' AS customer_name
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Result:** An; the SQL type is `text`.

### Exercise 3 — Two Paths to City

Write two expressions for city:

~~~sql
payload -> 'customer' -> 'address' ->> 'city'
payload #>> '{customer,address,city}'
~~~

**Question:** for order 1, what do both return? Is the type JSONB or text?

**Answer:** both return the SQL text `Hà Nội`.

### Exercise 4 — #> vs. #>>

~~~sql
SELECT
    payload #> '{customer,address,city}' AS a,
    payload #>> '{customer,address,city}' AS b
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Explain why `a` is a JSONB string while `b` is SQL text. What do you expect from `pg_typeof(a)` and `pg_typeof(b)`?

### Exercise 5 — Do Not Use ->> Too Early

Why is the following query invalid due to operator types?

~~~sql
-- Invalid:
-- SELECT payload ->> 'customer' ->> 'name'
-- FROM json_lab_307.orders;
~~~

**Answer:** after `->> 'customer'`, the value is `text`, so `->>` cannot be applied again as on JSONB. Fix it to `payload -> 'customer' ->> 'name'`.

### Exercise 6 — First Index of items

Write a query to extract the SKU of the first item in order 1 using `-> 0`.

**Answer:** `BOOK-01`. Why is using `-> 1` for the first element wrong?

### Exercise 7 — Getting the Second Item by Path

Use `#>> '{items,1,sku}'` on order 1.

**Answer:** `PEN-01`.

### Exercise 8 — Getting the Last Item

Use negative indexing with `->` or `#>>` to retrieve the last SKU in orders 1 and 2.

**Result:** order 1 `PEN-01`; order 2 `MOUSE-01`.

### Exercise 9 — Out-of-Range Index

Predict the output:

~~~sql
SELECT payload -> 'items' ->> 50
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

**Answer:** SQL NULL. Explain why the operator does not raise an error.

### Exercise 10 — SQL Array vs. JSON Array

Compare:

~~~sql
SELECT
    (ARRAY[10,20,30])[1] AS sql_first,
    '[10,20,30]'::jsonb -> 0 AS json_first;
~~~

**Question:** are the two logical values equal? What is the SQL type of each?

**Answer:** both represent the number 10, but `integer` vs. `jsonb`.

### Exercise 11 — Keys with Dots and Spaces

Extract `special-value` from order 1 in two ways:

~~~sql
payload -> 'a.b' ->> 'x y'
payload #>> ARRAY['a.b','x y']::text[]
~~~

Explain why `a.b` is **a single key**, not two levels.

### Exercise 12 — Keys with Commas

Given:

~~~json
{"a,b":{"c d":77}}
~~~

write `#>>` using `ARRAY['a,b','c d']::text[]`, and explain why this is less error-prone for escaping than a hand-written text-array literal.

### Exercise 13 — Missing Key vs. JSON null

On order 1:

~~~sql
payload -> 'coupon'
payload -> 'not_found'
~~~

**Question:** which expression is JSONB null and which is SQL NULL? How do their `IS NULL` checks differ?

### Exercise 14 — When ->> Erases the Distinction

On order 1:

~~~sql
payload ->> 'coupon'
payload ->> 'not_found'
~~~

**Answer:** both are SQL NULL. Which operation reveals whether the `coupon` key actually exists?

**Hint:** `payload ? 'coupon'`.

### Exercise 15 — Finding Orders with JSON null coupon

Write a query returning only orders that have the `coupon` key equal to JSON null.

**Suggested solution:**

~~~sql
SELECT order_id
FROM json_lab_307.orders
WHERE payload ? 'coupon'
  AND payload -> 'coupon' = 'null'::jsonb
ORDER BY order_id;
~~~

**Result:** 1 and 5.

### Exercise 16 — Identifying Missing coupon

Write a query finding orders whose root is an object lacking the `coupon` key.

**Result:** 3 and 4. Why does order 6 need separate handling if business logic wants to include SQL NULL documents?

### Exercise 17 — Empty String vs. null

In order 1, does `payload ->> 'note'` equal `''`? Is it `IS NULL`?

**Answer:** it equals the empty string, and is not SQL NULL.

### Exercise 18 — JSON String "null"

Compare:

~~~sql
SELECT
    jsonb_typeof('"null"'::jsonb),
    jsonb_typeof('null'::jsonb);
~~~

**Answer:** `string` and `null`.

### Exercise 19 — Checking the Type of items

~~~sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'items') AS items_type
FROM json_lab_307.orders
ORDER BY order_id;
~~~

**Question:** how do orders 3, 4, 5, and 6 differ?

**Hint:** empty array, JSON null, mistyped object, and SQL NULL document.

### Exercise 20 — Guarded jsonb_array_length

Write a `CASE` returning the length of `items` when `jsonb_typeof(...) = 'array'`, and SQL NULL otherwise.

**Result:** order 1 = 2, order 2 = 1, order 3 = 0, rows 4–6 = NULL.

### Exercise 21 — Why Is COALESCE Insufficient?

Explain:

~~~sql
jsonb_array_length(
    COALESCE(payload -> 'items', '[]'::jsonb)
)
~~~

Why can this still fail on order 4?

**Answer:** JSONB null is a non-SQL-NULL value; `COALESCE` keeps the JSON null and the function requires an array.

### Exercise 22 — Extracting total as a Number

Write `(payload ->> 'total')::numeric` for orders 1 and 2.

**Question:** what error would a string `"total":"abc"` cause in principle? Why is validation needed?

### Exercise 23 — Enforcing Numeric JSON for total

Write `CASE WHEN jsonb_typeof(payload -> 'total')='number' THEN (payload ->> 'total')::numeric ELSE NULL END`.

**Question:** does order 5 return SQL NULL or 50000? Why?

**Answer:** SQL NULL because `total`'s JSON type is `string`, even though the text `"50000"` could parse.

### Exercise 24 — Numeric vs. Text Comparison

Explain why:

~~~sql
WHERE payload ->> 'total' > '90000'
~~~

is not equivalent to finding orders with a total greater than 90,000. Rewrite it as a guarded numeric comparison.

### Exercise 25 — True Boolean vs. Boolean String

Compare:

~~~sql
payload -> 'paid' = 'true'::jsonb
payload ->> 'paid' = 'true'
~~~

**Question:** if a document contains `"paid":"true"` (a JSON string), which expression matches? Which checks for an actual JSON boolean?

### Exercise 26 — Expanding items into Rows

Write a `CROSS JOIN LATERAL jsonb_array_elements` query extracting `sku` and `qty` from order 1.

**Result:** BOOK-01 / 2 and PEN-01 / 1.

### Exercise 27 — LATERAL on Mistyped Data

Orders 4 and 5 have `items` that are not arrays.

**Exercise:** use `CASE` to substitute `'[]'::jsonb` before passing into `jsonb_array_elements`. Why is this step needed?

### Exercise 28 — Keeping Orders with No items

Replace `CROSS JOIN LATERAL` with `LEFT JOIN LATERAL ... ON TRUE` using the guarded input.

**Question:** do orders 3–6 appear? What is their `sku` value?

**Answer:** each order appears once with a SQL NULL `sku`.

### Exercise 29 — WITH ORDINALITY

On order 1, use `WITH ORDINALITY` to return `position` and `position - 1 AS json_index`.

**Result:** BOOK-01 has SQL position 1 / JSON index 0; PEN-01 has SQL position 2 / JSON index 1.

### Exercise 30 — jsonb_to_recordset

Write a query mapping each item in orders 1 and 2 into `(sku text, qty integer, price numeric)` using `jsonb_to_recordset`.

**Question:** what happens if `items` is not an array or `qty` holds a non-integer string?

### Exercise 31 — jsonb_each

List the keys of `payload -> 'customer'` in order 1 using `jsonb_each`.

**Question:** is `value` typed as `jsonb` or `text`? How does `jsonb_each_text` differ?

### Exercise 32 — text[] Path vs. JSONPath

Given:

~~~text
{items,0,sku}
$.items[0].sku
~~~

**Exercise:** how is the first used with `#>>`, and how is the second used with `jsonb_path_query_first`? Do both return the same SQL type?

### Exercise 33 — Wildcard

Why does `#> '{items,*,sku}'` not mean "get all SKUs" like `jsonb_path_query(payload,'$.items[*].sku')`?

**Answer:** `text[]` paths have no `*` wildcard; each element is a literal key or index.

### Exercise 34 — JSONPath Keys with Dots

Extract `a.b -> x y` using JSONPath:

~~~sql
SELECT jsonb_path_query_first(
    payload,
    '$."a.b"."x y"'
)
FROM json_lab_307.orders
WHERE order_id = 1;
~~~

Explain the effect of double quotes in JSONPath.

### Exercise 35 — @? and ?

Compare two requirements:

1. Does the payload have a `coupon` key at the root?
2. Does any item have SKU `BOOK-01`?

**Hint:** requirement 1 uses `?`; requirement 2 uses `@?` with JSONPath, or `LATERAL` + `EXISTS`.

### Exercise 36 — B-tree Expression Index

Create the index:

~~~sql
CREATE INDEX idx_city_practice_307
ON json_lab_307.orders (
    (payload #>> '{customer,address,city}')
);
~~~

Then run `EXPLAIN` on a query filtering by city. Why might the planner still choose Seq Scan on a six-row table?

### Exercise 37 — GIN Containment

Write the query `payload @> '{"paid":true}'::jsonb` and explain how it differs from reading `payload ->> 'paid'`.

**Result:** orders 1, 3, and 4 on the lab data.

### Exercise 38 — Operator Classes

Explain why `jsonb_ops` supports key existence `?`, whereas `jsonb_path_ops` targets containment/JSONPath and supports a different operator set.

**Never conclude that every JSONB query workload needs both GIN indexes.**

### Exercise 39 — Prepared text[] Path

Write `PREPARE find_orders(text[], text)` checking `payload #>> $1 = $2`, then `EXECUTE` it with the city path and `'Hà Nội'`.

**Question:** why is passing `text[]` via a bound parameter safer than concatenating user-supplied SQL paths?

### Exercise 40 — Java/JDBC

Write a Java method using `PreparedStatement`, `Connection.createArrayOf("text", ...)`, and `ResultSet` to extract an order's city.

**Requirements:** do not construct SQL by concatenating user values, close resources properly, and define SQL NULL behavior.

### Exercise 41 — Path Allowlist

An API accepts `field=customerCity`, `field=contactEmail`, or `field=customerName`.

**Exercise:** build a map from logical field names to fixed path-component arrays. Why should you not allow arbitrary JSONPath access across all payload branches?

### Exercise 42 — CASE Data Classification

Write a query classifying `items` into: `valid_array`, `json_null_items`, `wrong_items_type`, and `sql_null_document`.

**Answer:** orders 1–3 valid array, order 4 JSON null, order 5 wrong type, order 6 SQL NULL document.

### Exercise 43 — GROUP BY city

Write a query with `GROUP BY payload #>> '{customer,address,city}'`.

**Question:** how are orders 4, 5, and 6 grouped when city extraction yields SQL NULL? When using `COALESCE(..., '<unknown>')`, are malformed rows merged together?

### Exercise 44 — Properly Typed ORDER BY total

Write a query sorting `total` descending as numeric, using `CASE` to accept only JSON numbers, with `NULLS LAST`.

**Question:** where does order 5 appear? If business rules allow numeric strings, how must validation and normalization change?

### Exercise 45 — JSONB UPDATE with Rollback

Inside a lab transaction, use `jsonb_set` to change order 1's city to Huế, then `ROLLBACK`.

**Question:** what does `#>>` read while the transaction is open, and what does it read after rollback? Why is `#>>` read-only while `jsonb_set` in an UPDATE is a write?

### Exercise 46 — CHECK Constraint

Design a CHECK ensuring `payload` is SQL NULL or a JSON object. Why is this constraint not enough to guarantee `items` is an array and `total` is a number?

### Exercise 47 — Monetary Data Rules

Should a JSON field `"price":"100000"` (string) be treated identically to JSON number `100000`? If a financial application requires exactness, where should casting happen, what numeric scale should be used, and how should invalid values be handled?

### Exercise 48 — Schema Design

An application must join millions of orders with customers by `customer.id` inside the payload, requiring foreign keys and uniqueness.

**Question:** when should you create a dedicated `customer_id BIGINT` column instead of storing the field only inside nested JSON? What are the benefits of typed relational columns?

### Exercise 49 — The String Key "0" Case

Compare JSON object `{"0":"A"}` with JSON array `["A"]`.

**Exercise:** which source type matches `-> '0'` and which matches `-> 0`?

### Exercise 50 — Capstone: Safe Queries and API

Design an order-reading API with these requirements:

- Return `order_id`, `customerName`, and `city`;
- Return numeric `total`, but only when its JSON type is valid;
- Distinguish missing coupon, JSON null coupon, and a coupon code;
- List items with `sku`, `qty`, and `price`;
- Preserve item order from the JSON array;
- Do not fail on empty order 3 or mistyped orders 4/5; instead surface data quality status;
- Do not let clients read arbitrary JSON paths;
- Provide an indexing strategy for frequent city lookups or JSON containment searches;
- Use prepared statements for all client-supplied inputs.

**Implementation approach:**

1. Use `#>>` for name/city; `CASE + jsonb_typeof` for total.
2. Use `payload ? 'coupon'` and `payload -> 'coupon'` to distinguish coupon states.
3. Use `LEFT JOIN LATERAL jsonb_array_elements(CASE ...) WITH ORDINALITY` for items.
4. Report schema-invalid `items` rows separately rather than silently turning them into "orders with 0 items."
5. Use a B-tree expression index for fixed city queries and GIN when containment workloads justify it.
6. Pass bound SQL parameters safely and restrict which fields callers may request.
7. At scale, inspect plans with `EXPLAIN`, verify output types, and test JSON null, missing key, wrong-type, and empty-array cases.

## 38. Checklist When Designing JSON Queries in PostgreSQL

1. [ ] Verified whether the column is `json` or `jsonb`.
2. [ ] Verified the JSON root type.
3. [ ] Distinguished object keys from array indexes.
4. [ ] Treated JSON array indexes as 0-based, without confusing them with `WITH ORDINALITY`.
5. [ ] Accessed intermediate levels with `->` or `#>` whenever JSON is still needed.
6. [ ] Used `->>` or `#>>` at the final step when SQL text is needed.
7. [ ] Avoided confusing `text[]` paths with SQL/JSON paths.
8. [ ] Properly quoted/escaped keys containing dots, spaces, or commas.
9. [ ] Defined separate rules for missing keys, JSON null, SQL NULL, and empty strings.
10. [ ] Used `jsonb_typeof` / constraints before potentially failing casts.
11. [ ] Never compared numeric values as text.
12. [ ] Never relied on `WHERE` clause evaluation order to guard casts.
13. [ ] Never called `jsonb_array_length` / `jsonb_array_elements` on objects or scalars.
14. [ ] Chose `CROSS` vs. `LEFT JOIN LATERAL` appropriately for preserving empty orders.
15. [ ] Used `WITH ORDINALITY` when array order matters.
16. [ ] Avoided turning missing fields into defaults that mask critical errors.
17. [ ] Identified fields that should be stored as typed relational columns.
18. [ ] Validated JSON documents arriving from untrusted sources.
19. [ ] Created matching indexes (exact expression/operator) for frequent queries.
20. [ ] Weighed B-tree expression indexes vs. GIN containment and write overhead.
21. [ ] Measured planner behavior on representative volumes rather than forcing indexes on tiny tables.
22. [ ] Bound all parameters; enforced allowlists and authorization on dynamic paths.
23. [ ] Verified Java/JDBC handling of SQL NULL and JSONB values.
24. [ ] Added tests for NULL documents, JSON null, missing keys, wrong types, and empty arrays.
25. [ ] Planned schema versioning and migrations for path changes.

## 39. Official PostgreSQL Documentation

When implementing, consult the documentation for the **exact PostgreSQL major version** you are running. The links below point to current PostgreSQL documentation:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): differences between `json` and `jsonb`, storage, containment, indexing, and JSONPath.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): reference for `->`, `->>`, `#>`, `#>>`, `?`, `@>`, `@?`, `@@`, and JSON/JSONB functions.
- [SQL/JSON Path Language](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-SQLJSON-PATH): `$` syntax, accessors, filters, lax, and strict modes.
- [Array Functions and Operators](https://www.postgresql.org/docs/current/functions-array.html): PostgreSQL SQL arrays, distinct from JSON arrays.
- [Array Types](https://www.postgresql.org/docs/current/arrays.html): SQL array subscripting and lower bounds.
- [Set Returning Functions](https://www.postgresql.org/docs/current/functions-srf.html): expanding data into multiple rows.
- [LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL): `LATERAL` in `FROM`, pairing table functions with left-hand rows.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, GIN, GiST, and access methods.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): B-tree indexes on values extracted from JSON.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): index methods, operator classes, expression indexes, and limitations.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): reading optimizer plans and the execution effect of `ANALYZE`.
- [Data Definition / Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, FK, and relational constraints.
- [PREPARE](https://www.postgresql.org/docs/current/sql-prepare.html): statement parameterization.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): updating rows using `jsonb_set` in SET expressions.
- [JSONB Subscripting](https://www.postgresql.org/docs/current/datatype-json.html#DATATYPE-JSONB-SUBSCRIPTING): JSONB subscripting syntax in supported versions.

The extraction operators `->`, `->>`, `#>`, and `#>>` are longstanding PostgreSQL fundamentals. Newer additions such as SQL/JSON path and JSONB subscripting have version requirements; never copy syntax from current docs onto older servers without verifying support.

## 40. Summary

**JSON extraction in PostgreSQL** centers on four operators to remember:

| Operator | Quick Reference |
| --- | --- |
| **`->`** | Extracts an object key or JSON array index, **returns JSON/JSONB** |
| **`->>`** | Extracts an object key or JSON array index, **returns SQL text** |
| **`#>`** | Traverses multiple levels via a **`text[]` path**, **returns JSON/JSONB** |
| **`#>>`** | Traverses multiple levels via a **`text[]` path**, **returns SQL text** |

For nested objects, you can write `payload -> 'customer' -> 'address' ->> 'city'` or `payload #>> '{customer,address,city}'`. For arrays, JSON indexes start at **0**; negative indexes count from the end, and SQL's `WITH ORDINALITY` **starts at 1**. When every array element is needed, expand with `jsonb_array_elements` / `LATERAL` rather than hardcoding fixed indexes.

When working with heterogeneous data, **never conflate** missing keys, JSON null, SQL NULL, empty strings, and mistyped fields. Extraction operators normally return SQL NULL when a path fails, whereas functions like `jsonb_array_length` raise errors if the input is not an array. `jsonb_typeof`, `?`, `CASE`, and validation/constraints let you identify each case accurately before casting.

The `text[]` path of `#>` / `#>>` differs from **SQL/JSON paths** such as `$.customer.address.city`. JSONPath supports wildcards and filter predicates, while `#>>` is simpler and ideal when the exact levels are known. For multi-row queries, choose indexes matching your real operators: a **B-tree expression index** for a fixed extracted path, or **GIN** for supported JSONB containment, key, and path conditions.

Ultimately, **type correctness and access control matter more than concise syntax**. Parameterize paths in JDBC, restrict readable fields, maintain explicit JSON schemas, and promote core fields to typed relational columns when needed. Mastering these four operators along with null, array, and type edge cases gives you flexible JSON querying without sacrificing PostgreSQL's correctness, maintainability, or performance.
