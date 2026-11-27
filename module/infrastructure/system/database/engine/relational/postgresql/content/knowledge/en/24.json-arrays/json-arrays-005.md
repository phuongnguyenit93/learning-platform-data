# Converting JSON to Rows, Recordsets, and Back in PostgreSQL

PostgreSQL supports both **typed relational data** and **JSON/JSONB** for flexible documents. An API might submit an order as an object containing an array of line items:

~~~json
{
  "order_id": 1001,
  "customer_id": 501,
  "status": "paid",
  "items": [
    {"sku": "BOOK-01", "quantity": 2, "unit_price": 45000.00},
    {"sku": "PEN-02", "quantity": 3, "unit_price": 12000.00}
  ]
}
~~~

To compute totals, JOIN with a products table, or enforce foreign keys, we often want to turn the `items` array into **SQL rows**:

| order_id | line_no | sku | quantity | unit_price |
|---:|---:|---|---:|---:|
| 1001 | 1 | BOOK-01 | 2 | 45000.00 |
| 1001 | 2 | PEN-02 | 3 | 12000.00 |

The reverse direction is equally common: taking `orders` and `order_items` tables and reconstructing **a JSON object with an `items` array** to return to an API or export data.

The lesson **"Converting JSON to Rows, Recordsets, and Back"**, in the **JSON and Arrays** chapter of the **Database Engine Relational PostgreSQL** module, explains both directions thoroughly:

- **JSON → SQL:** `jsonb_to_record`, `jsonb_to_recordset`, `jsonb_populate_record`, `jsonb_populate_recordset`, `jsonb_array_elements`, `jsonb_each`, `LATERAL`, and `WITH ORDINALITY`.
- **SQL → JSON:** `row_to_json`, `to_jsonb`, `jsonb_build_object`, `jsonb_agg`, and `jsonb_object_agg`.
- **Correctness:** handling missing keys, JSON null, SQL NULL, data types, array ordering, duplicate keys, JOIN row multiplication, validation, and constraints.
- **Operations:** batch imports, JDBC, payload size limits, filtering/index tuning, and reading execution plans.

> **Safety:** statements creating schemas, tables, and loading sample data in this lesson are strictly for a dedicated practice database. Never run them against production without verifying permissions, current state, and synchronization policies.

---

## 1. Two Conversion Directions to Distinguish

A JSON document can take several shapes:

~~~json
{"id":1,"name":"An"}
~~~

~~~json
[
  {"id":1,"name":"An"},
  {"id":2,"name":"Bình"}
]
~~~

~~~json
{"id":1,"items":[{"sku":"A"},{"sku":"B"}]}
~~~

Each shape calls for the right tool:

| Input Shape | Desired SQL Output | Tool |
|---|---|---|
| Single object | One row with typed columns | `jsonb_to_record` |
| Array of objects | Multiple rows | `jsonb_to_recordset` |
| Array of arbitrary values | One row per element | `jsonb_array_elements` |
| Array needing positions | Elements with 1, 2, ... index | `WITH ORDINALITY` |
| Object with dynamic keys | Multiple key/value pairs | `jsonb_each` |
| Object matching a composite type | One composite row | `jsonb_populate_record` |
| Array of objects matching a composite type | Set of composite rows | `jsonb_populate_recordset` |

Reverse direction:

| SQL Shape | Desired JSON | Tool |
|---|---|---|
| Single row/composite | JSON object | `row_to_json` or `to_jsonb` |
| Selected columns | Object with custom keys | `jsonb_build_object` |
| Multiple rows | JSON array | `jsonb_agg` |
| Key/value pairs | JSON object | `jsonb_object_agg` |
| Parent row + child rows | Object containing child array | `jsonb_build_object` + `jsonb_agg` |

No function automatically infers arbitrary nested schemas or business rules. First identify the **shape of the data**.

## 2. The json and jsonb Types

PostgreSQL supports `json` and `jsonb`.

| Property | `json` | `jsonb` |
|---|---|---|
| Representation | Stores syntax-checked JSON text | Parsed binary representation |
| Input whitespace | Preserved | Not preserved verbatim |
| Object key ordering | Preserved per input text | Not guaranteed to match input |
| Duplicate object keys | Can be retained in text | One value per key retained |
| Operators and GIN indexing | Fewer | More |
| Record conversion function | `json_to_record` | `jsonb_to_record` |
| Recordset conversion function | `json_to_recordset` | `jsonb_to_recordset` |

`jsonb` usually fits best when filtering, transforming, indexing, and processing JSON inside PostgreSQL. `json` is useful when near-verbatim input text must be retained.

**Note:** A JSON object is not an ordered business collection of keys. By contrast, a **JSON array is ordered**, so record positions whenever reproducing order matters.

### 2.1. JSON Types Differ from SQL Types

JSON distinguishes string, number, boolean, null, array, and object. SQL adds `BIGINT`, `INTEGER`, `NUMERIC(12,2)`, `TIMESTAMPTZ`, `TEXT[]`, composite types, and many more.

Casting or mapping to SQL types determines precision, value bounds, and available operators and indexes.

## 3. The ->, ->>, #>, and #>> Operators

Before turning JSON into rows, review how values are extracted:

~~~sql
SELECT
    '{"id":1001,"status":"paid"}'::jsonb -> 'id'
        AS id_jsonb,
    '{"id":1001,"status":"paid"}'::jsonb ->> 'id'
        AS id_text;
~~~

- `->`: extracts a value as JSON/JSONB.
- `->>`: extracts a value as TEXT.
- `#>`: extracts JSON/JSONB at a multi-level path.
- `#>>`: extracts TEXT at a multi-level path.

Nested path example:

~~~sql
SELECT
    '{"customer":{"address":{"city":"HCM"}}}'::jsonb
        #> '{customer,address}' AS address_json,
    '{"customer":{"address":{"city":"HCM"}}}'::jsonb
        #>> '{customer,address,city}' AS city_text;
~~~

### 3.1. ->> Does Not Return BIGINT Automatically

~~~sql
SELECT
    ('{"id":1001}'::jsonb ->> 'id')::BIGINT
        AS id_number;
~~~

`->>` returns TEXT. `::BIGINT` converts it to a number. If the input is `"abc"` or exceeds BIGINT bounds, the cast fails.

When multiple typed columns are needed, `jsonb_to_record` is usually cleaner than many individual casts.

## 4. Converting an Object to a Record with jsonb_to_record

~~~sql
SELECT x.*
FROM jsonb_to_record(
    '{
      "order_id":1001,
      "customer_id":501,
      "status":"paid",
      "amount":126000.50,
      "priority":true,
      "ordered_at":"2026-11-01T10:15:00Z",
      "note":null
    }'::jsonb
) AS x(
    order_id BIGINT,
    customer_id BIGINT,
    status TEXT,
    amount NUMERIC(12,2),
    priority BOOLEAN,
    ordered_at TIMESTAMPTZ,
    note TEXT
);
~~~

Logical result is a single row:

| order_id | customer_id | status | amount | priority | note |
|---:|---:|---|---:|---|---|
| 1001 | 501 | paid | 126000.50 | true | NULL |

`ordered_at` is parsed as `TIMESTAMPTZ`. PostgreSQL's display timezone depends on session settings, though it represents the same instant.

### 4.1. Why Must AS x(...) Be Declared?

`jsonb_to_record` returns a `record` pseudo-type with no fixed structure at function definition time. Inside `FROM`, SQL must know **the names and types of the output columns**.

Thus the required pattern is:

~~~sql
FROM jsonb_to_record(source_jsonb)
AS alias_name(column_a type_a, column_b type_b)
~~~

You cannot simply write `SELECT * FROM jsonb_to_record(...)` and expect PostgreSQL to synthesize a relational schema from all JSON keys.

### 4.2. Columns Absent from JSON

If you declare a column that does not exist in the object, its value is normally SQL NULL (unlike composite-based population with a non-null base record that retains base values).

### 4.3. Undeclared Keys

If the object also has `"trace_id":"abc"` while the `AS` list only includes `order_id` and `status`, the extra key is ignored.

### 4.4. json_to_record

When the source is `json`:

~~~sql
SELECT *
FROM json_to_record(
    '{"id":1,"name":"Mai"}'::json
) AS x(id INTEGER, name TEXT);
~~~

It performs the same mapping for `json` input.

## 5. jsonb_to_recordset: Turning an Array of Objects into Multiple Rows

~~~sql
SELECT *
FROM jsonb_to_recordset(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
      {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
    ]'::jsonb
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Result:

| sku | quantity | unit_price |
|---|---:|---:|
| BOOK-01 | 2 | 45000.00 |
| PEN-02 | 3 | 12000.00 |

You can compute totals directly:

~~~sql
SELECT
    SUM(quantity * unit_price) AS total_amount
FROM jsonb_to_recordset(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000},
      {"sku":"PEN-02","quantity":3,"unit_price":12000}
    ]'::jsonb
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Result:

\[
2\times45000+3\times12000=126000
\]

### 5.1. Empty Array

~~~sql
SELECT *
FROM jsonb_to_recordset('[]'::jsonb)
AS x(sku TEXT, quantity INTEGER);
~~~

Returns **0 rows**, not one row full of NULLs.

### 5.2. json_to_recordset

~~~sql
SELECT *
FROM json_to_recordset(
    '[{"id":1},{"id":2}]'::json
) AS x(id INTEGER);
~~~

Use this when the input is `json`.

### 5.3. Input Must Match the Expected Shape

`jsonb_to_recordset` expects an **array of objects**. For a single object, use `jsonb_to_record`. If the array contains malformed elements, conversion errors out rather than silently skipping bad rows.

## 6. jsonb_array_elements: Expanding a JSON Array Element by Element

`jsonb_array_elements` emits one row per array element, preserving each element as `jsonb`:

~~~sql
SELECT elem
FROM jsonb_array_elements(
    '[10,"hello",null,{"id":1},[1,2]]'::jsonb
) AS x(elem);
~~~

Unlike `jsonb_to_recordset`, this function:

- Does not require every element to be an object with matching columns.
- Can return scalars, objects, and arrays as `jsonb`.
- Supports multi-step handling of nested or mixed structures.
- Pairs cleanly with `WITH ORDINALITY` to capture element positions.

### 6.1. Scalar Arrays to Text

~~~sql
SELECT
    value
FROM jsonb_array_elements_text(
    '["red","blue","green"]'::jsonb
) AS x(value);
~~~

`jsonb_array_elements_text` returns `TEXT`. For numeric arrays, cast to `INTEGER` or `NUMERIC` when performing arithmetic.

### 6.2. Comparing array_elements vs. recordset Functions

| Function | What Each Row Contains |
|---|---|
| `jsonb_array_elements` | One `JSONB` column holding the whole element |
| `jsonb_array_elements_text` | One `TEXT` column holding the element as text |
| `jsonb_to_recordset` | Multiple typed columns per the `AS` definition |

Choose based on whether you want raw elements or immediate typed columns.

## 7. WITH ORDINALITY: Element Position in a JSON Array

SQL rows have **no guaranteed order** without `ORDER BY`. Meanwhile, JSON array order often carries business meaning (line 1, line 2, ...).

~~~sql
SELECT
    x.ordinality AS line_no,
    x.item
FROM jsonb_array_elements(
    '[{"sku":"A"},{"sku":"B"},{"sku":"C"}]'::jsonb
) WITH ORDINALITY AS x(item, ordinality)
ORDER BY x.ordinality;
~~~

Result:

| line_no | item |
|---:|---|
| 1 | `{"sku":"A"}` |
| 2 | `{"sku":"B"}` |
| 3 | `{"sku":"C"}` |

`WITH ORDINALITY` numbers from **1**. JSON path array indexes start from **0**, so never mix up the two conventions.

### 7.1. Combining Ordinality with jsonb_to_record

~~~sql
SELECT
    a.ordinality::INTEGER AS line_no,
    x.sku,
    x.quantity,
    x.unit_price
FROM jsonb_array_elements(
    '[
      {"sku":"BOOK-01","quantity":2,"unit_price":45000},
      {"sku":"PEN-02","quantity":3,"unit_price":12000}
    ]'::jsonb
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS x(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
)
ORDER BY a.ordinality;
~~~

Each element now has both typed columns and `line_no`. This is a clean way to persist array order into relational tables and reconstruct it when exporting JSON.

## 8. LATERAL: Expanding Each Parent Row's Array

Suppose a staging table stores one JSON object per row with an `items` array, and we want to expand each item while keeping the parent row ID.

`LATERAL` allows an item in `FROM` to reference columns from items to its left:

~~~sql
WITH docs(doc_id, payload) AS (
    VALUES
        (1, '{"items":[{"sku":"A"},{"sku":"B"}]}'::jsonb),
        (2, '{"items":[{"sku":"C"}]}'::jsonb)
)
SELECT
    d.doc_id,
    a.ordinality AS item_no,
    a.item ->> 'sku' AS sku
FROM docs AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
ORDER BY d.doc_id, a.ordinality;
~~~

Result:

| doc_id | item_no | sku |
|---:|---:|---|
| 1 | 1 | A |
| 1 | 2 | B |
| 2 | 1 | C |

### 8.1. CROSS JOIN LATERAL vs. LEFT JOIN LATERAL

If `items=[]`, `CROSS JOIN LATERAL` emits zero item rows, so the parent row is dropped from the result.

`LEFT JOIN LATERAL ... ON TRUE` retains the parent row with NULLs on the right:

~~~sql
WITH docs(doc_id, payload) AS (
    VALUES
        (1, '{"items":[{"sku":"A"}]}'::jsonb),
        (2, '{"items":[]}'::jsonb)
)
SELECT
    d.doc_id,
    a.item ->> 'sku' AS sku
FROM docs AS d
LEFT JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) AS a(item) ON TRUE
ORDER BY d.doc_id;
~~~

Row `doc_id = 2` still appears, with `sku = NULL`.

### 8.2. Functions in FROM Are Implicitly Lateral

In PostgreSQL, a table function in `FROM` can reference preceding tables even without writing `LATERAL` explicitly. Writing `CROSS JOIN LATERAL` or `LEFT JOIN LATERAL` makes parent-child semantics and row retention completely clear.

## 9. jsonb_each: Objects to Key/Value Pairs

Not all JSON uses arrays. An object with dynamic keys:

~~~json
{"red":5,"blue":8,"green":3}
~~~

can be turned into rows:

~~~sql
SELECT key, value
FROM jsonb_each(
    '{"red":5,"blue":8,"green":3}'::jsonb
);
~~~

Each row has `key TEXT` and `value JSONB`. Row order is not guaranteed without `ORDER BY`.

### 9.1. jsonb_each_text

~~~sql
SELECT key, value
FROM jsonb_each_text(
    '{"region":"VN","currency":"VND"}'::jsonb
);
~~~

In this variant, `value` is `TEXT`.

### 9.2. jsonb_object_keys

~~~sql
SELECT key
FROM jsonb_object_keys(
    '{"a":1,"b":2}'::jsonb
) AS x(key)
ORDER BY key;
~~~

Useful when inspecting which keys are present for validation or auditing dynamic fields.

### 9.3. Do Not Use jsonb_each on Arrays

`jsonb_each` is for objects; for `[1,2,3]` use `jsonb_array_elements`. The two shapes are not interchangeable.

## 10. JSON null, SQL NULL, and Missing Keys

Three payloads with different meanings:

~~~json
{"note":null}
~~~

~~~json
{}
~~~

~~~json
{"note":"null"}
~~~

- Field `note` exists with JSON null.
- Field `note` is absent.
- Field `note` holds the text literal `"null"`.

~~~sql
SELECT
    '{"note":null}'::jsonb -> 'note' AS json_null,
    '{}'::jsonb -> 'note' AS missing,
    '{"note":null}'::jsonb ->> 'note' AS null_text,
    '{"note":"null"}'::jsonb ->> 'note' AS literal_text;
~~~

`->` returns JSONB null when the key holds JSON null, and SQL NULL when the key is missing. `->>` returns SQL NULL for both JSON null and a missing key. The string literal remains `TEXT` `'null'`.

### 10.1. Checking Key Presence

~~~sql
SELECT
    '{"note":null}'::jsonb ? 'note' AS has_note,
    jsonb_typeof(
        '{"note":null}'::jsonb -> 'note'
    ) AS type_of_note,
    jsonb_typeof(
        '{}'::jsonb -> 'note'
    ) AS type_of_missing;
~~~

Logical results: `has_note = TRUE`; the first type is the string `'null'`; the missing key's type is SQL NULL.

### 10.2. When Converted to Records, Both Yield SQL NULL

~~~sql
SELECT *
FROM jsonb_to_record(
    '{"note":null}'::jsonb
) AS x(note TEXT);
~~~

and:

~~~sql
SELECT *
FROM jsonb_to_record(
    '{}'::jsonb
) AS x(note TEXT);
~~~

both produce SQL NULL for `note`. If an application uses patch semantics, a missing key may mean "leave unchanged," whereas JSON null means "clear value." In that case **you must preserve key-presence metadata** rather than relying solely on a typed record.

## 11. Type Mapping and Conversion Errors

~~~sql
SELECT *
FROM jsonb_to_record(
    '{
      "id":12,
      "price":25000.75,
      "paid":true,
      "ordered_at":"2026-11-01T09:30:00Z",
      "tags":["priority","gift"],
      "metadata":{"channel":"web"}
    }'::jsonb
) AS x(
    id BIGINT,
    price NUMERIC(12,2),
    paid BOOLEAN,
    ordered_at TIMESTAMPTZ,
    tags TEXT[],
    metadata JSONB
);
~~~

Record conversion functions can recursively convert nested SQL arrays and composite types where supported, provided the target types accept the actual data.

If:

~~~sql
SELECT *
FROM jsonb_to_record(
    '{"quantity":"not-an-integer"}'::jsonb
) AS x(quantity INTEGER);
~~~

PostgreSQL raises a conversion error. It **does not skip the failing row** and return the rest.

### 11.1. Checking Required Fields

A missing key produces SQL NULL in the declared column. A `NOT NULL` constraint on a destination table will reject it on `INSERT`; `jsonb_to_record` on its own does not replace full schema validation.

### 11.2. Avoid Storing Money as Floating Point When Decimal Precision Matters

For money, `NUMERIC(12,2)` fits better than `DOUBLE PRECISION`. Numeric type, scale, rounding, and currency rules must follow business requirements.

## 12. JSON Key Names vs. SQL Column Names

`jsonb_to_record` maps by **exact key name** and does not automatically convert `camelCase` ↔ `snake_case`.

~~~sql
SELECT x."productId" AS product_id
FROM jsonb_to_record(
    '{"productId":10}'::jsonb
) AS x("productId" BIGINT);
~~~

Declaring `product_id BIGINT` instead of `"productId" BIGINT` in this example will not map the value.

Options:

- Declare the column with the exact quoted JSON key name, then alias it in `SELECT`.
- Normalize JSON keys in the ingestion pipeline.
- Extract fields via `->>` and assign your desired SQL names.
- Enforce a consistent upstream contract.

Do not write heuristic field-name guessing if field names are part of an API contract.

## 13. Checking Root Type and Avoiding COALESCE Mistakes

Both `jsonb_to_recordset` and `jsonb_array_elements` require an array. You can check:

~~~sql
SELECT
    jsonb_typeof('[1,2]'::jsonb) AS array_type,
    jsonb_typeof('{"id":1}'::jsonb) AS object_type,
    jsonb_typeof('null'::jsonb) AS null_type;
~~~

Expected: `array`, `object`, `null`.

### 13.1. COALESCE Does Not Turn JSON null into []

~~~sql
COALESCE(payload -> 'items', '[]'::jsonb)
~~~

only replaces **SQL NULL** (such as a missing key) with an empty array. If the payload contains `"items":null`, `payload -> 'items'` is **JSONB null**, which `COALESCE` leaves untouched.

If your contract treats any non-array value as an empty array, use:

~~~sql
CASE
    WHEN jsonb_typeof(payload -> 'items') = 'array'
    THEN payload -> 'items'
    ELSE '[]'::jsonb
END
~~~

For strict imports, however, **rejecting** non-arrays is usually better than silently dropping data. Decide according to the schema contract.

## 14. Designing the Lab Schema for Orders

In an **empty practice database**, create the tables:

~~~sql
CREATE SCHEMA json_lab;

CREATE TABLE json_lab.incoming_documents (
    doc_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE json_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new','paid','cancelled')),
    source_payload JSONB NOT NULL
);

CREATE TABLE json_lab.order_items (
    order_id BIGINT NOT NULL
        REFERENCES json_lab.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Explanation:

- `incoming_documents` stages raw JSONB prior to conversion.
- `orders` holds typed headers plus the source JSONB in the lab.
- `order_items` holds one row per line item.
- `line_no` preserves array element order.
- FKs, CHECKs, and PKs guard integrity.

`CREATE` fails if the schema or tables already exist. Never `DROP` a production schema just to re-run examples; use a dedicated lab database or controlled reset.

## 15. Loading Sample JSONB Data

~~~sql
INSERT INTO json_lab.incoming_documents(payload)
VALUES
(
    '{
      "order_id":1001,
      "customer_id":501,
      "ordered_at":"2026-11-01T10:15:00Z",
      "status":"paid",
      "items":[
        {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
        {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
      ],
      "note":null
    }'::jsonb
),
(
    '{
      "order_id":1002,
      "customer_id":502,
      "ordered_at":"2026-11-02T09:00:00Z",
      "status":"new",
      "items":[
        {"sku":"BAG-03","quantity":1,"unit_price":89000.00}
      ]
    }'::jsonb
);
~~~

There are 2 order documents and 3 item objects.

Inspect root and array types:

~~~sql
SELECT
    doc_id,
    jsonb_typeof(payload) AS root_type,
    jsonb_typeof(payload -> 'items') AS items_type,
    payload ->> 'status' AS status_text
FROM json_lab.incoming_documents
ORDER BY doc_id;
~~~

These queries inspect data shapes and do not replace full business constraint validation.

## 16. Extracting Order Headers per Document

~~~sql
SELECT
    d.doc_id,
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
)
ORDER BY d.doc_id;
~~~

`jsonb_to_record` builds one typed record per JSON object. `LATERAL` links each record back to the staging row's `doc_id`.

Do not use `jsonb_to_recordset(d.payload)` here because each document's root is an **object**, not an array of orders.

## 17. Extracting Items with line_no

~~~sql
SELECT
    d.doc_id,
    (d.payload ->> 'order_id')::BIGINT AS order_id,
    a.ordinality::INTEGER AS line_no,
    i.sku,
    i.quantity,
    i.unit_price,
    i.quantity * i.unit_price AS line_total
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS i(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
)
ORDER BY d.doc_id, a.ordinality;
~~~

Expected output:

| order_id | line_no | sku | quantity | unit_price | line_total |
|---:|---:|---|---:|---:|---:|
| 1001 | 1 | BOOK-01 | 2 | 45000.00 | 90000.00 |
| 1001 | 2 | PEN-02 | 3 | 12000.00 | 36000.00 |
| 1002 | 1 | BAG-03 | 1 | 89000.00 | 89000.00 |

`jsonb_array_elements` expands the array, `WITH ORDINALITY` assigns positions, and `jsonb_to_record` maps each item into columns.

## 18. Inserting Headers into the Typed Table

After appropriate validation, `INSERT`:

~~~sql
INSERT INTO json_lab.orders (
    order_id, customer_id, ordered_at, status, source_payload
)
SELECT
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status,
    d.payload
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
);
~~~

With a fresh schema and two distinct `order_id` values, this inserts 2 rows.

### 18.1. Re-Running May Cause Key Collisions

`PRIMARY KEY(order_id)` rejects duplicate `order_id` values. A real pipeline needs an explicit policy:

- Ingest each batch only once.
- UPSERT based on source version.
- Reject duplicates.
- Use an idempotency key.
- Log already-applied events.

Never assume `ON CONFLICT DO NOTHING` is safe by default; it can silently drop a genuine update.

### 18.2. Example Conditional UPSERT

~~~sql
INSERT INTO json_lab.orders (
    order_id, customer_id, ordered_at, status, source_payload
)
SELECT
    h.order_id,
    h.customer_id,
    h.ordered_at,
    h.status,
    d.payload
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS h(
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
)
ON CONFLICT (order_id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    ordered_at = EXCLUDED.ordered_at,
    status = EXCLUDED.status,
    source_payload = EXCLUDED.source_payload;
~~~

This pattern is valid when upstream is allowed to overwrite and the input batch contains no duplicate `order_id` rows. Add version/timestamp conflict guards when needed.

## 19. Inserting Items into the Typed Table

Once headers exist:

~~~sql
INSERT INTO json_lab.order_items (
    order_id, line_no, sku, quantity, unit_price
)
SELECT
    (d.payload ->> 'order_id')::BIGINT,
    a.ordinality::INTEGER,
    i.sku,
    i.quantity,
    i.unit_price
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_array_elements(
    d.payload -> 'items'
) WITH ORDINALITY AS a(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    a.item
) AS i(
    sku TEXT,
    quantity INTEGER,
    unit_price NUMERIC(12,2)
);
~~~

Starting from an empty database, this inserts 3 item rows.

### 19.1. Why Insert Headers First?

`order_items.order_id` references `orders.order_id`. If the parent order does not exist yet and FKs are enforced immediately, inserting items fails.

### 19.2. Wrap in a Transaction

A multi-step import belongs in a single transaction:

~~~sql
BEGIN;

-- Validate payload/batch.
-- INSERT/UPSERT orders.
-- INSERT/REPLACE items according to policy.
-- Record batch processing status.

COMMIT;
~~~

This illustrates the conceptual workflow; comments do not execute steps automatically. In the lab, wrap the `INSERT` statements above inside one transaction.

### 19.3. When an Order Shrinks in Item Count

Upserting individual items does not delete lines absent from a newer snapshot. If the source sends a **full snapshot** of an order, apply a replace/soft-delete policy inside the transaction. If the source sends a **delta**, do not delete missing lines.

This is synchronization semantics, not automatic behavior of JSON conversion.

## 20. Root JSON as an Array of Orders

If the input is:

~~~json
[
  {"order_id":2001,"customer_id":601,"status":"new"},
  {"order_id":2002,"customer_id":602,"status":"paid"}
]
~~~

use:

~~~sql
SELECT *
FROM jsonb_to_recordset(
    '[
      {"order_id":2001,"customer_id":601,"status":"new"},
      {"order_id":2002,"customer_id":602,"status":"paid"}
    ]'::jsonb
) AS o(
    order_id BIGINT,
    customer_id BIGINT,
    status TEXT
);
~~~

If the array is nested inside a wrapper object:

~~~json
{"batch_id":123,"orders":[{"order_id":2001},{"order_id":2002}]}
~~~

extract `orders` first:

~~~sql
WITH src AS (
    SELECT '{
      "batch_id":123,
      "orders":[{"order_id":2001},{"order_id":2002}]
    }'::jsonb AS doc
)
SELECT o.*
FROM src
CROSS JOIN LATERAL jsonb_to_recordset(
    doc -> 'orders'
) AS o(order_id BIGINT);
~~~

Do not pass the whole root object to `jsonb_to_recordset` expecting it to locate a nested array on its own.

## 21. Composite Types and jsonb_populate_record

When multiple queries share the same row definition, define a composite type:

~~~sql
CREATE TYPE json_lab.order_header_type AS (
    order_id BIGINT,
    customer_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT
);
~~~

Then use it:

~~~sql
SELECT *
FROM jsonb_populate_record(
    NULL::json_lab.order_header_type,
    '{
      "order_id":1001,
      "customer_id":501,
      "ordered_at":"2026-11-01T10:15:00Z",
      "status":"paid"
    }'::jsonb
);
~~~

`jsonb_populate_record(base, from_jsonb)` uses **the base composite type** as the output schema. When `base` is `NULL::type`, missing fields become SQL NULL; when `base` is a non-null composite value, fields missing from JSON retain their values from `base` per the function's rules.

`json_populate_record` is the `json` counterpart.

### 21.1. When to Use a Composite Type?

- Stable payload schemas.
- Reusable typed record definitions.
- Shared across multiple functions or queries.
- Nested composites or composite arrays.

You do not need a composite type for a one-off temporary object; `jsonb_to_record` is usually simpler.

## 22. jsonb_populate_recordset

With `json_lab.order_header_type` already created:

~~~sql
SELECT *
FROM jsonb_populate_recordset(
    NULL::json_lab.order_header_type,
    '[
      {
        "order_id":2001,
        "customer_id":601,
        "ordered_at":"2026-11-01T10:00:00Z",
        "status":"new"
      },
      {
        "order_id":2002,
        "customer_id":602,
        "ordered_at":"2026-11-02T11:00:00Z",
        "status":"paid"
      }
    ]'::jsonb
);
~~~

Returns multiple rows of that composite type.

| Function | Record Count | Where Structure Is Specified |
|---|---|---|
| `jsonb_to_record` | One | `AS x(col type, ...)` |
| `jsonb_to_recordset` | Many | `AS x(col type, ...)` |
| `jsonb_populate_record` | One | Composite type of `base` |
| `jsonb_populate_recordset` | Many | Composite type of `base` |

The `json_...` variants accept `json` instead of `jsonb`.

## 23. Nested Objects: Keep as JSONB or Extract Columns

Example:

~~~json
{
  "order_id":1001,
  "customer":{"id":501,"name":"Lan"}
}
~~~

**Keep the nested object as JSONB:**

~~~sql
SELECT x.order_id, x.customer
FROM jsonb_to_record(
    '{
      "order_id":1001,
      "customer":{"id":501,"name":"Lan"}
    }'::jsonb
) AS x(order_id BIGINT, customer JSONB);
~~~

**Extract the nested object into columns:**

~~~sql
WITH src AS (
    SELECT '{
      "order_id":1001,
      "customer":{"id":501,"name":"Lan"}
    }'::jsonb AS doc
)
SELECT
    (doc ->> 'order_id')::BIGINT AS order_id,
    c.id AS customer_id,
    c.name AS customer_name
FROM src
CROSS JOIN LATERAL jsonb_to_record(
    doc -> 'customer'
) AS c(id BIGINT, name TEXT);
~~~

If only one nested field is needed, `doc #>> '{customer,name}'` can be simpler than another `LATERAL` join.

## 24. Nested Arrays: Expanding Multiple Levels

Payload:

~~~json
{
  "shipment_id":9001,
  "packages":[
    {
      "package_code":"PK-1",
      "items":[{"sku":"A","qty":2},{"sku":"B","qty":3}]
    },
    {
      "package_code":"PK-2",
      "items":[{"sku":"C","qty":1}]
    }
  ]
}
~~~

You can expand two array levels:

~~~sql
WITH src AS (
    SELECT '{
      "shipment_id":9001,
      "packages":[
        {
          "package_code":"PK-1",
          "items":[
            {"sku":"A","qty":2},
            {"sku":"B","qty":3}
          ]
        },
        {
          "package_code":"PK-2",
          "items":[{"sku":"C","qty":1}]
        }
      ]
    }'::jsonb AS doc
)
SELECT
    (s.doc ->> 'shipment_id')::BIGINT AS shipment_id,
    p.ordinality AS package_no,
    p.pkg ->> 'package_code' AS package_code,
    i.ordinality AS item_no,
    x.sku,
    x.qty
FROM src AS s
CROSS JOIN LATERAL jsonb_array_elements(
    s.doc -> 'packages'
) WITH ORDINALITY AS p(pkg, ordinality)
CROSS JOIN LATERAL jsonb_array_elements(
    p.pkg -> 'items'
) WITH ORDINALITY AS i(item, ordinality)
CROSS JOIN LATERAL jsonb_to_record(
    i.item
) AS x(sku TEXT, qty INTEGER)
ORDER BY p.ordinality, i.ordinality;
~~~

This yields 3 item rows along with package and item positions.

### 24.1. Cardinality Explosion

If 100 packages each have 1,000 items, one document expands into 100,000 rows. A wrong join against another multi-row table can multiply row counts even further. Always bound array sizes, filter early, and inspect `EXPLAIN` on large datasets.

## 25. JSON Arrays and SQL Arrays Are Different Structures

JSON array:

~~~sql
SELECT '["red","blue","green"]'::jsonb;
~~~

SQL array:

~~~sql
SELECT ARRAY['red','blue','green']::TEXT[];
~~~

To convert a JSON array into an ordered `TEXT[]`:

~~~sql
SELECT COALESCE(
    array_agg(value ORDER BY ordinality),
    ARRAY[]::TEXT[]
) AS sql_tags
FROM jsonb_array_elements_text(
    '["red","blue","green"]'::jsonb
) WITH ORDINALITY AS x(value, ordinality);
~~~

To convert a SQL array into JSONB:

~~~sql
SELECT to_jsonb(
    ARRAY['red','blue','green']::TEXT[]
) AS json_tags;
~~~

`array_agg` over 0 rows returns SQL NULL, so `COALESCE` helps if you want an empty SQL array. Do not confuse `'{}'::TEXT[]` or `ARRAY[]::TEXT[]` with JSON array `'[]'::jsonb`.

## 26. Converting Dynamic Key–Value Objects into Typed Rows

Example scores:

~~~json
{"math":8.5,"java":9.0,"sql":8.0}
~~~

~~~sql
SELECT
    key AS subject,
    value::NUMERIC(3,1) AS score
FROM jsonb_each_text(
    '{"math":8.5,"java":9.0,"sql":8.0}'::jsonb
) AS x(key, value)
ORDER BY key;
~~~

For dynamic-key objects, `jsonb_each_text` is a natural fit. If any value cannot cast to `NUMERIC`, the query fails.

For business structures with fixed field names, typed columns make constraints much easier to enforce than free-form key–value pairs.

## 27. row_to_json: Turning a SQL Row into a JSON Object

~~~sql
SELECT row_to_json(x) AS doc
FROM (
    SELECT
        1001::BIGINT AS order_id,
        501::BIGINT AS customer_id,
        'paid'::TEXT AS status
) AS x;
~~~

Result:

~~~json
{"order_id":1001,"customer_id":501,"status":"paid"}
~~~

Column names in the subquery become JSON keys. Alias columns to customize key names.

### 27.1. row_to_json Returns json

`row_to_json` returns `json`. To get `jsonb`, cast it:

~~~sql
SELECT row_to_json(x)::jsonb
FROM (
    SELECT 1001::BIGINT AS order_id
) AS x;
~~~

Or call `to_jsonb(x)` directly.

## 28. to_json and to_jsonb: SQL Values to JSON

~~~sql
SELECT
    to_jsonb(1001::BIGINT) AS numeric_json,
    to_jsonb(TRUE) AS boolean_json,
    to_jsonb(ARRAY[10,20,30]) AS array_json;
~~~

Composite row:

~~~sql
SELECT to_jsonb(x) AS doc
FROM (
    SELECT
        1001::BIGINT AS order_id,
        'paid'::TEXT AS status
) AS x;
~~~

Logical result:

~~~json
{"order_id":1001,"status":"paid"}
~~~

### 28.1. Serializing an Entire Table Row

~~~sql
SELECT to_jsonb(o) AS doc
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

This emits every column of `orders`, including `source_payload`.

**Never expose `to_jsonb(o)` unfiltered on a public API** if the table has internal or sensitive columns. Future migrations adding columns would silently leak data in responses.

Project only public columns in a subquery, or build explicit keys with `jsonb_build_object`.

## 29. jsonb_build_object: Explicit Key/Value Construction

~~~sql
SELECT jsonb_build_object(
    'order_id', 1001,
    'status', 'paid',
    'amount', 126000.00,
    'priority', TRUE
) AS doc;
~~~

Logical result:

~~~json
{
  "order_id":1001,
  "status":"paid",
  "amount":126000,
  "priority":true
}
~~~

The function takes alternating **key/value** arguments and returns a `jsonb` object (`json_build_object` returns `json`).

### 29.1. Building Objects from SQL Columns

~~~sql
SELECT jsonb_build_object(
    'id', o.order_id,
    'customer_id', o.customer_id,
    'status', o.status,
    'ordered_at', o.ordered_at
) AS doc
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

This gives a controlled output schema unaffected by adding internal columns to the underlying table.

### 29.2. Do Not Try to Store Multiple Values via Duplicate Keys

A JSONB object holds only one value per key. To store multiple values under a name, use a JSON array or an array of objects.

## 30. jsonb_agg: Multiple Rows into a JSON Array

~~~sql
SELECT jsonb_agg(
    jsonb_build_object(
        'sku', x.sku,
        'quantity', x.quantity
    )
    ORDER BY x.sku
) AS items
FROM (
    VALUES
        ('BOOK-01'::TEXT, 2::INTEGER),
        ('PEN-02'::TEXT, 3::INTEGER)
) AS x(sku, quantity);
~~~

Result:

~~~json
[
  {"sku":"BOOK-01","quantity":2},
  {"sku":"PEN-02","quantity":3}
]
~~~

`jsonb_agg` returns a `jsonb` array; `json_agg` returns a `json` array.

### 30.1. Ordering Must Be Inside the Aggregate

Never rely on rows entering `jsonb_agg` in physical order or from an incidental index scan. To guarantee order:

~~~sql
jsonb_agg(expression ORDER BY sort_column)
~~~

When outputting JSON arrays, **`ORDER BY` inside the aggregate** is essential.

### 30.2. Empty Input Sets

`jsonb_agg` over **0 rows** returns SQL NULL, not `[]`.

~~~sql
SELECT COALESCE(
    jsonb_agg(x.value),
    '[]'::jsonb
)
FROM (
    SELECT 1 AS value
    WHERE FALSE
) AS x;
~~~

Returns an empty JSON array.

### 30.3. One NULL Row Differs from 0 Rows

Aggregating a single SQL NULL value produces a JSON array containing a `null` element (`[null]`). Do not confuse this with an empty array, especially after a `LEFT JOIN`.

## 31. jsonb_object_agg: Key/Value Rows into an Object

~~~sql
SELECT
    jsonb_object_agg(x.key, x.value) AS attributes
FROM (
    VALUES
        ('red'::TEXT, 5::INTEGER),
        ('blue'::TEXT, 8::INTEGER)
) AS x(key, value);
~~~

Logical result:

~~~json
{"red":5,"blue":8}
~~~

### 31.1. NULL Keys

JSON object keys must be non-null strings. A SQL NULL key causes the aggregate to error. Validate or filter out NULL keys:

~~~sql
-- Pattern with a hypothetical attributes table:
SELECT jsonb_object_agg(key, value)
FROM attributes
WHERE key IS NOT NULL;
~~~

### 31.2. Duplicate Keys

If multiple rows share the same key, JSONB cannot retain two values for that key. Do not rely on implicit input order to pick the winner. Instead:

- Enforce a unique constraint.
- Deduplicate with a deterministic policy and tie-breaker.
- Or aggregate into an array if multiple values per key are valid.

### 31.3. Empty Object

For 0 rows, use:

~~~sql
COALESCE(
    jsonb_object_agg(key, value),
    '{}'::jsonb
)
~~~

to return an empty object matching the API contract.

## 32. Exporting Each Order's Items as a JSON Array

~~~sql
SELECT
    i.order_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'sku', i.sku,
                'quantity', i.quantity,
                'unit_price', i.unit_price
            )
            ORDER BY i.line_no
        ),
        '[]'::jsonb
    ) AS items
FROM json_lab.order_items AS i
GROUP BY i.order_id
ORDER BY i.order_id;
~~~

On the sample data:

- Order 1001 has two item objects.
- Order 1002 has one item object.

`ORDER BY i.line_no` is placed **inside `jsonb_agg`** to preserve the original JSON order.

### 32.1. When an Order Has No Items

Starting from `order_items` omits orders that have zero items. To include empty orders, start from `orders` and use a `LEFT JOIN` or correlated subquery.

## 33. Building Nested JSON Objects per Order

~~~sql
SELECT
    jsonb_build_object(
        'order_id', o.order_id,
        'customer_id', o.customer_id,
        'ordered_at', o.ordered_at,
        'status', o.status,
        'items', (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'sku', i.sku,
                        'quantity', i.quantity,
                        'unit_price', i.unit_price
                    )
                    ORDER BY i.line_no
                ),
                '[]'::jsonb
            )
            FROM json_lab.order_items AS i
            WHERE i.order_id = o.order_id
        )
    ) AS order_document
FROM json_lab.orders AS o
ORDER BY o.order_id;
~~~

Sample logical result:

~~~json
{
  "order_id":1001,
  "customer_id":501,
  "ordered_at":"2026-11-01T10:15:00+00:00",
  "status":"paid",
  "items":[
    {"sku":"BOOK-01","quantity":2,"unit_price":45000.00},
    {"sku":"PEN-02","quantity":3,"unit_price":12000.00}
  ]
}
~~~

Timestamp formatting and object key order vary by PostgreSQL/session/JSONB serialization. What matters is semantic equivalence of the values.

### 33.1. Why Does a Correlated Subquery Fit Well Here?

- Each order stays a single row.
- `items` are aggregated directly by `order_id`.
- Orders with no items yield `[]` via `COALESCE`.
- Prevents accidental item duplication when joining additional one-to-many tables.

At scale, check `EXPLAIN` and ensure proper indexes before deciding execution strategy. Do not assume a correlated subquery is always faster than every join formulation.

## 34. LEFT JOIN and the [null] Array Pitfall

Another pattern is joining and grouping:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'sku', i.sku,
                'quantity', i.quantity,
                'unit_price', i.unit_price
            )
            ORDER BY i.line_no
        ) FILTER (WHERE i.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS items
FROM json_lab.orders AS o
LEFT JOIN json_lab.order_items AS i
    ON i.order_id = o.order_id
GROUP BY o.order_id, o.customer_id
ORDER BY o.order_id;
~~~

**Why is FILTER needed?**

For an order with no items, `LEFT JOIN` still produces one parent row with NULL child columns. Aggregating that placeholder row emits `[{"sku":null,...}]` or `[null]` instead of `[]`.

`FILTER (WHERE i.order_id IS NOT NULL)` excludes the null child placeholder; `COALESCE` turns the empty aggregate into `[]`.

### 34.1. COUNT(*) After LEFT JOIN

`COUNT(*)` returns `1` for a childless order because the parent row is preserved. To count child rows, use `COUNT(i.order_id)` or another non-null child column.

## 35. Wrapping All Orders into One JSON Array

You can construct each order's JSON object first, then aggregate them into an outer array:

~~~sql
WITH order_docs AS (
    SELECT
        o.order_id,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', (
                SELECT COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'sku', i.sku,
                            'quantity', i.quantity,
                            'unit_price', i.unit_price
                        )
                        ORDER BY i.line_no
                    ),
                    '[]'::jsonb
                )
                FROM json_lab.order_items AS i
                WHERE i.order_id = o.order_id
            )
        ) AS doc
    FROM json_lab.orders AS o
)
SELECT jsonb_build_object(
    'orders',
    COALESCE(
        jsonb_agg(doc ORDER BY order_id),
        '[]'::jsonb
    )
) AS response
FROM order_docs;
~~~

Output shape:

~~~json
{
  "orders":[
    {"order_id":1001,"status":"paid","items":[...]},
    {"order_id":1002,"status":"new","items":[...]}
  ]
}
~~~

This aggregates across two levels:

1. `items` ordered by `line_no`.
2. `orders` ordered by `order_id`.

Never use this pattern to pack millions of orders into a single giant JSONB response in a normal API; paginate or stream instead.

## 36. Exporting a Keyed Object Map Dynamically

Output example:

~~~json
{"1001":"paid","1002":"new"}
~~~

~~~sql
SELECT COALESCE(
    jsonb_object_agg(
        o.order_id::TEXT,
        o.status
    ),
    '{}'::jsonb
) AS order_status_map
FROM json_lab.orders AS o;
~~~

Casting `order_id::TEXT` makes explicit that JSON object keys are strings. If input rows have duplicate `order_id` values from a join, the winning value is nondeterministic; ensure unique keys before aggregating.

## 37. JSON null in the SQL → JSON Direction

~~~sql
SELECT jsonb_build_object(
    'id', 1,
    'note', NULL
) AS doc;
~~~

Returns an object containing `"note":null`.

If the API contract requires omitting keys with null values:

~~~sql
SELECT jsonb_strip_nulls(
    jsonb_build_object(
        'id', 1,
        'note', NULL
    )
) AS doc;
~~~

Logical result:

~~~json
{"id":1}
~~~

### 37.1. [] Differs from null and Missing Keys

Three payloads:

~~~json
{"items":[]}
~~~

~~~json
{"items":null}
~~~

~~~json
{}
~~~

can carry distinct semantics: an empty list, unknown/not applicable, or field omitted. Never let `jsonb_strip_nulls` or `COALESCE` alter an API contract without an explicit policy decision.

## 38. Distinct Values, Duplicate Rows, and Multiple JOINs

To emit a JSON array of unique tags:

~~~sql
WITH tags(tag) AS (
    VALUES
        ('A'::TEXT),
        ('B'::TEXT),
        ('A'::TEXT)
),
unique_tags AS (
    SELECT DISTINCT tag
    FROM tags
)
SELECT COALESCE(
    jsonb_agg(tag ORDER BY tag),
    '[]'::jsonb
)
FROM unique_tags;
~~~

Result: `["A","B"]`.

**Do not apply `DISTINCT` indiscriminately.** Two order lines with the same SKU on different `line_no` values are still two valid lines. Deduplicating them would drop business data.

### 38.1. Join Multiplication

If an order has 3 items and 2 payments, joining `orders → items → payments` produces 6 rows. Calling `jsonb_agg(items)` on that join duplicates items.

Solution:

~~~text
orders
  +--> aggregate items separately GROUP BY order_id
  +--> aggregate payments separately GROUP BY order_id
  +--> JOIN the two aggregated results
~~~

Never rely on `DISTINCT` alone to patch a broken join, as it can silently erase distinct rows that happen to share identical attributes.

## 39. Preserving Order Across Round-Trips

To round-trip JSON arrays in order:

~~~text
Input JSON array
         |
         v
jsonb_array_elements WITH ORDINALITY
         |
         v
Save line_no (1,2,3,...) into SQL table
         |
         v
SELECT child rows by order_id
         |
         v
jsonb_agg(jsonb_build_object(...) ORDER BY line_no)
         |
         v
Output JSON array in desired order
~~~

An outer `ORDER BY order_id` only sorts the **SQL result rows**; it does not sort elements inside `jsonb_agg`. Always put `ORDER BY` at the exact level where order must be guaranteed.

## 40. Round-Trips Do Not Guarantee Byte-for-Byte Identity

JSON → SQL → JSON can alter representation:

- JSONB discards original whitespace.
- JSONB does not preserve object key order.
- Duplicate object keys are collapsed.
- `NUMERIC(12,2)` applies SQL scale and rounding.
- `TIMESTAMPTZ` formats according to the session timezone.
- Unmapped or missing fields may be omitted.
- JSON null and missing keys merge into SQL NULL if key-presence metadata is lost.

Round-trip example with typed fields:

~~~sql
WITH src AS (
    SELECT '{"order_id":1001,"status":"paid"}'::jsonb AS doc
),
typed AS (
    SELECT x.*
    FROM src
    CROSS JOIN LATERAL jsonb_to_record(
        src.doc
    ) AS x(order_id BIGINT, status TEXT)
)
SELECT to_jsonb(typed) AS rebuilt
FROM typed;
~~~

In simple cases, both objects may be equal under **JSONB semantic equality**. With unmapped keys, nested types, or precision changes, output need not equal input.

When legal or audit requirements demand verbatim originals, store raw payloads separately rather than assuming typed round-trips preserve exact text.

## 41. Aggregating Totals Directly from Recordsets

You do not need to persist into typed tables first to run SQL aggregations:

~~~sql
WITH lines AS (
    SELECT
        (d.payload ->> 'order_id')::BIGINT AS order_id,
        i.quantity,
        i.unit_price
    FROM json_lab.incoming_documents AS d
    CROSS JOIN LATERAL jsonb_to_recordset(
        d.payload -> 'items'
    ) AS i(
        sku TEXT,
        quantity INTEGER,
        unit_price NUMERIC(12,2)
    )
)
SELECT
    order_id,
    SUM(quantity * unit_price) AS total_amount
FROM lines
GROUP BY order_id
ORDER BY order_id;
~~~

Result:

| order_id | total_amount |
|---:|---:|
| 1001 | 126000.00 |
| 1002 | 89000.00 |

`jsonb_to_recordset` fits here because `line_no` is not needed for summing. When position order or per-item handling is needed, use `jsonb_array_elements WITH ORDINALITY`.

## 42. Performance: recordset or ->>?

Both forms are valid:

~~~sql
SELECT
    (payload ->> 'order_id')::BIGINT AS order_id,
    payload ->> 'status' AS status
FROM json_lab.incoming_documents;
~~~

and:

~~~sql
SELECT
    x.order_id,
    x.status
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    d.payload
) AS x(
    order_id BIGINT,
    status TEXT
);
~~~

`jsonb_to_record` is clean when extracting many typed fields; `->>` can be concise for 1–2 fields. Neither is universally faster.

Cost factors that typically matter:

- How many documents must be unpacked?
- How many elements does each document contain?
- Do predicates filter parent rows early?
- Are values cast repeatedly?
- Do joins multiply cardinality?
- Is the constructed JSON output oversized?
- Are suitable indexes present for parent predicates?

## 43. GIN and Expression Indexes on JSONB

A GIN index on JSONB:

~~~sql
CREATE INDEX idx_incoming_payload_gin
ON json_lab.incoming_documents
USING GIN (payload);
~~~

can accelerate matching predicates such as containment:

~~~sql
SELECT doc_id
FROM json_lab.incoming_documents
WHERE payload @> '{"status":"paid"}'::jsonb;
~~~

Or an expression index for a text field:

~~~sql
CREATE INDEX idx_incoming_status
ON json_lab.incoming_documents (
    (payload ->> 'status')
);
~~~

to serve:

~~~sql
SELECT doc_id
FROM json_lab.incoming_documents
WHERE payload ->> 'status' = 'paid';
~~~

### 43.1. GIN Does Not Automatically Speed Up Array Expansion

An index can **reduce how many parent documents must be processed**, yet `jsonb_to_recordset(payload->'items')` still has to expand the array of every selected document.

If you constantly join and filter on `order_id`, `customer_id`, and `status`, typed SQL columns with B-tree indexes usually outperform repeated JSONB parsing.

### 43.2. Caution with Casting Expression Indexes

An expression index such as `((payload->>'order_id')::BIGINT)` fails during creation or writes if any row holds an uncastable `order_id`. Validate source data before creating the index, or promote it to a typed column.

## 44. Filter Before Expanding Large Arrays

With many documents, avoid expanding all arrays before checking parent-level filters.

~~~sql
SELECT
    d.doc_id,
    i.sku,
    i.quantity
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_recordset(
    d.payload -> 'items'
) AS i(
    sku TEXT,
    quantity INTEGER
)
WHERE d.payload ->> 'status' = 'paid';
~~~

The optimizer may push parent predicates down in the plan, though you should inspect `EXPLAIN` for complex queries. Isolate parent filtering in a subquery or CTE when needed to clarify the input set.

### 44.1. Do Not Parse Unused Fields

If a query only needs `sku` and `quantity`, do not declare dozens of unused nested fields just because the input contains them. Extra casts and intermediate objects add unnecessary overhead.

## 45. EXPLAIN with Function Scan / LATERAL

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    d.doc_id,
    i.sku,
    i.quantity
FROM json_lab.incoming_documents AS d
CROSS JOIN LATERAL jsonb_to_recordset(
    d.payload -> 'items'
) AS i(
    sku TEXT,
    quantity INTEGER
)
WHERE d.payload ->> 'status' = 'paid';
~~~

You may observe:

- `Seq Scan` / `Index Scan` on staging.
- `Function Scan` on `jsonb_to_recordset`.
- `Nested Loop` joining parent rows with function output.
- `Aggregate` and `Sort` when grouping or ordering.

Inspect `estimated rows`, `actual rows`, `loops`, buffers, and execution time. When array lengths vary widely, intermediate row estimates can be inaccurate.

`EXPLAIN ANALYZE` executes the query; on `INSERT`/`UPDATE`/`DELETE`, it modifies real data. Only benchmark DML inside controlled test environments.

## 46. When Should You Paginate or Stream?

A query aggregating millions of rows:

~~~sql
SELECT jsonb_agg(to_jsonb(x))
FROM enormous_table AS x;
~~~

can trigger:

- Massive aggregate state.
- High CPU and memory usage.
- Huge network payloads.
- Long response times and timeouts.
- Expensive retries if failure occurs near the end.
- JSONB/result size limits.

Instead of exporting everything in a single value:

1. Select orders via keyset pagination.
2. Export in batches.
3. Use appropriate streaming or cursors.
4. Use `COPY` for bulk exports when suitable.
5. Build nested JSON only for the selected page of parent rows.

Example bounding rows before aggregating:

~~~sql
WITH selected_orders AS (
    SELECT
        order_id,
        customer_id,
        status
    FROM json_lab.orders
    WHERE order_id > 0
    ORDER BY order_id
    LIMIT 100
)
SELECT COALESCE(
    jsonb_agg(to_jsonb(o) ORDER BY o.order_id),
    '[]'::jsonb
)
FROM selected_orders AS o;
~~~

In production APIs, cursor boundaries and snapshot semantics must be designed so concurrent writes neither skip nor duplicate rows.

## 47. Multi-Layer Validation

JSON from clients is **untrusted input**. Validate across layers:

| Layer | Examples |
|---|---|
| Syntax | Valid JSON parsing/casting |
| Root shape | Object vs. array as expected |
| Field presence | Are `order_id` and `items` present? |
| JSON field types | Is `items` actually an array? |
| SQL types | Is `quantity` a valid integer? |
| Domain | `quantity > 0`, `price >= 0` |
| Uniqueness | No duplicate `order_id` / `line_no` |
| Referential integrity | Valid `order_id` / `customer_id` |
| Authorization | Caller is permitted to act on that order/tenant |
| Resource limits | Bounded JSON size and array length |
| Idempotency | Re-running a batch does not double-insert or double-count |

Syntactically valid JSON does not imply business-valid data.

### 47.1. A Cast Error Can Abort the Whole Statement

If one item in an array has `quantity = "abc"`, `jsonb_to_recordset` casting to `INTEGER` fails. PostgreSQL does not return the other 99 valid items and skip the bad one.

To handle individual item errors:

- Load raw JSON into staging.
- Expand elements via `jsonb_array_elements WITH ORDINALITY`.
- Check JSON types and formats before casting.
- Record failing positions/items in an error table.
- Insert only validated rows.
- Keep FK/CHECK/UNIQUE constraints as the final safety net.

### 47.2. Do Not Rely Only on Regex for Type Validation

An all-digit string can still overflow `INTEGER` or `BIGINT`. Check numeric bounds and conversion errors for the target type.

## 48. JDBC: Binding JSON to Recordsets

In Java, never concatenate raw JSON into SQL strings. Use bind parameters:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class JsonItemReader {
    public void readItems(
        Connection connection,
        String jsonArray
    ) throws SQLException {
        String sql = """
            SELECT x.sku, x.quantity, x.unit_price
            FROM jsonb_to_recordset(CAST(? AS jsonb))
            AS x(
                sku text,
                quantity integer,
                unit_price numeric(12,2)
            )
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setString(1, jsonArray);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    String sku = rs.getString("sku");
                    int quantity = rs.getInt("quantity");
                    java.math.BigDecimal price =
                        rs.getBigDecimal("unit_price");
                    // Process each type-mapped item.
                }
            }
        }
    }
}
~~~

This assumes Java 17+, the PostgreSQL JDBC driver, and a configured `Connection`.

### 48.1. SQL NULL with getInt

`ResultSet.getInt` returns a primitive `int`. When the SQL column is NULL, it returns `0`; call `rs.wasNull()` or use a nullable getter when NULL must be distinguished. For required quantities, enforce NOT NULL and positive checks beforehand.

### 48.2. Do Not Pass Identifiers via Bind Parameters

`?` binds values, not SQL table or column names. For dynamic query structures, whitelist identifiers/templates; never concatenate untrusted input.

## 49. Bulk Import and Batch Idempotency

When importing batches of JSON documents:

~~~text
API / file
   |
   v
Check size limits + authorization
   |
   v
Raw JSONB staging with batch_id
   |
   v
Validate root/items/typed fields
   |
   v
Classify errors, duplicates, and conflicts
   |
   v
BEGIN
   |
   +--> Upsert order headers per policy
   +--> Insert/replace items per snapshot/delta semantics
   +--> Save checkpoint and audit
   |
   v
COMMIT
~~~

**Never automatically `DELETE` items absent from a delta batch.** Only replace items when the source explicitly provides a full, bounded snapshot.

Likewise, never assume using JSONB eliminates the need for transactions, FKs, unique constraints, or authorization.

## 50. Common Mistakes

### Mistake 1 — Using recordset for a Single Object

`jsonb_to_recordset` expects an array; use `jsonb_to_record` for a single object.

### Mistake 2 — Using record for an Array

Multi-object arrays require `jsonb_to_recordset` or element-by-element expansion.

### Mistake 3 — Forgetting AS Column Definitions

Functions returning `record` require a typed column definition list.

### Mistake 4 — Thinking ->> Returns Numeric

`->>` returns `TEXT`; cast explicitly or use a typed record function.

### Mistake 5 — Expecting Automatic camelCase-to-snake_case Mapping

Key names are not auto-converted; alias or normalize explicitly.

### Mistake 6 — Confusing JSON null with Missing Keys

`->>` returns SQL NULL for both; use `?` and `jsonb_typeof` when the distinction matters.

### Mistake 7 — Expecting COALESCE to Handle JSON null

No. JSONB null is distinct from SQL NULL.

### Mistake 8 — Using jsonb_each on an Array

`jsonb_each` is for objects; `jsonb_array_elements` is for arrays.

### Mistake 9 — Relying on Row Order from recordset

SQL rows have no default ordering; use `WITH ORDINALITY` and `ORDER BY`.

### Mistake 10 — Expecting CROSS JOIN LATERAL to Keep Parents with Empty Arrays

It drops them. Use `LEFT JOIN LATERAL` to keep empty parents.

### Mistake 11 — Expecting jsonb_agg to Return [] on Empty Input

Over 0 rows, aggregates return SQL NULL. Wrap with `COALESCE`.

### Mistake 12 — LEFT JOIN Producing a Single [null] Element

Use `FILTER` to exclude null child placeholder rows.

### Mistake 13 — Passing NULL Keys to jsonb_object_agg

NULL keys are invalid; validate or filter them out.

### Mistake 14 — Using Duplicate Object Keys for Multiple Values

JSONB keeps one value per key; use an array instead.

### Mistake 15 — Expecting an Outer ORDER BY to Sort a JSON Array

Place `ORDER BY` inside `jsonb_agg`.

### Mistake 16 — Serializing Whole Table Rows to Public APIs

Can leak internal columns; whitelist keys explicitly.

### Mistake 17 — Assuming Record Conversion Enforces Business Constraints

You still need `CHECK`/`FK`/`UNIQUE`, validation, and authorization.

### Mistake 18 — Assuming One Bad Item Will Be Skipped

A cast failure aborts the entire statement.

### Mistake 19 — Joining One-to-Many Tables Before Aggregating

Duplicates items inside JSON; aggregate each child branch separately before joining.

### Mistake 20 — Treating DISTINCT as a Cure-All for Bad Joins

It can delete distinct valid lines that happen to share attributes.

### Mistake 21 — Assuming a GIN Index Speeds Up Every recordset

Indexes filter parent rows; they do not eliminate array expansion cost.

### Mistake 22 — Aggregating Millions of Rows into One JSONB Response

Blows up memory, latency, and network; paginate or stream instead.

### Mistake 23 — Expecting Byte-for-Byte Text Identity After Round-Trip

JSONB and typed conversions canonicalize representation; check semantics instead.

### Mistake 24 — Assuming Every JSON Timestamp Has a Timezone

Offsetless timestamps depend on session/contract settings; require ISO 8601 with timezone for instants.

### Mistake 25 — Assuming Valid JSON Means Authorization to Edit That Order

Authorization and tenant scoping must be enforced independently of parsing.

### Mistake 26 — Treating Re-Import as Safe to Re-INSERT

Causes PK collisions; use batch IDs, conflict policies, and idempotency.

### Mistake 27 — Importing Items Before Headers

Foreign key checks will reject them.

### Mistake 28 — Using FLOAT for Money Without Considering Rounding

Use an appropriately scaled `NUMERIC` type.

### Mistake 29 — Filtering After Expanding a Huge Array

Generates massive intermediate row sets; filter parents first when possible.

### Mistake 30 — Thinking EXPLAIN ANALYZE on DML Is Harmless

It executes the DML for real; run only in safe test environments.

## 51. Checklist for JSON → SQL Conversion

1. Is the input `json` or `jsonb`?
2. Is the root an object or an array?
3. Under which key is the nested object or array located?
4. Are JSON types verified before calling `recordset` or `array_elements`?
5. Are all required fields present?
6. Do missing keys, JSON null, and SQL NULL have distinct semantics?
7. Do destination SQL columns use the right types and ranges?
8. Are any field names camelCase or case-sensitive?
9. Must array order be preserved with `WITH ORDINALITY`?
10. Is `CROSS JOIN` or `LEFT JOIN LATERAL` appropriate?
11. Could the source contain duplicate business keys?
12. Are `CHECK`, PK, FK, authorization, and idempotency enforced?
13. Is the incoming data a full snapshot or a delta?
14. Are payload and array size limits enforced?
15. Are errors logged with `doc_id` and `ordinality`?
16. Are header and item writes wrapped in a transaction?

## 52. Checklist for SQL → JSON Conversion

1. Is the output an object, an array, or a nested object?
2. Are exported keys explicitly whitelisted?
3. Are internal and PII columns excluded?
4. Do `NUMERIC` and `TIMESTAMPTZ` representations match the contract?
5. Is `ORDER BY` placed inside `jsonb_agg`?
6. Should absent child rows produce `[]` or `null`?
7. Could `LEFT JOIN` emit a null child placeholder?
8. Are `FILTER` and `COALESCE` applied where needed?
9. Could multiple joins duplicate items?
10. Is there a clear policy for duplicate object keys?
11. Are results paginated before aggregating?
12. Are row counts, totals, and identities reconciled?
13. Are NULLs handled per the API contract?
14. Are response size and network payload bounded?
15. Have `EXPLAIN` and `BUFFERS` been checked for large payloads?

## 53. Practice Exercises

### Exercise 1 — Single Object

Convert `{"id":1,"name":"An"}` into `id INTEGER, name TEXT`.

**Hint:** `jsonb_to_record(...) AS x(id integer, name text)`.

### Exercise 2 — Array of Objects

Convert `[{"id":1},{"id":2}]` into two rows.

**Hint:** `jsonb_to_recordset`.

### Exercise 3 — json and jsonb

State two differences regarding duplicate keys, whitespace, or indexing.

**Hint:** `jsonb` normalizes structure and supports more operators and indexes.

### Exercise 4 — -> and ->>

What type does `payload->>'quantity'` return?

**Hint:** `TEXT`, not `INTEGER`.

### Exercise 5 — Numeric Casting

Convert `[{"price":12000.50}]` into `NUMERIC(12,2)`.

**Hint:** use `recordset` with a column definition list.

### Exercise 6 — Missing Field

If JSON lacks `quantity` while the column list declares `quantity INTEGER`, what value is normally produced?

**Hint:** SQL NULL.

### Exercise 7 — Extra Keys

JSON has `extra_field` omitted from `AS`. Does it automatically become a new column?

**Hint:** no.

### Exercise 8 — JSON null

How do you distinguish `{"note":null}` from `{}`?

**Hint:** `?` and `jsonb_typeof`.

### Exercise 9 — Empty Array

How many rows does `jsonb_to_recordset('[]'::jsonb)` return?

**Hint:** 0.

### Exercise 10 — Ordinality

Expand `["A","B","C"]` with positions 1, 2, 3.

**Hint:** `jsonb_array_elements_text WITH ORDINALITY`.

### Exercise 11 — LATERAL

Why can a table function expanding `d.payload->'items'` reference each row `d`?

**Hint:** `LATERAL`.

### Exercise 12 — Empty Array in LEFT JOIN

How do you preserve an order when `items` is empty?

**Hint:** `LEFT JOIN LATERAL ... ON TRUE`.

### Exercise 13 — Key/Value Object

Convert `{"A":10,"B":20}` into key/value rows.

**Hint:** `jsonb_each_text`.

### Exercise 14 — Composite Type

How does `jsonb_to_record` differ from `jsonb_populate_record`?

**Hint:** inline column list vs. a base composite type.

### Exercise 15 — Composite Recordset

Load a JSON array into `json_lab.order_header_type`.

**Hint:** `jsonb_populate_recordset(NULL::json_lab.order_header_type, ...)`.

### Exercise 16 — Nested Object

Extract `customer.name` from nested JSON.

**Hint:** `#>> '{customer,name}'`.

### Exercise 17 — Nested Arrays

A shipment has packages, and each package has items. How many array expansion layers are needed?

**Hint:** two `jsonb_array_elements` calls.

### Exercise 18 — SQL Array

Convert `["red","blue"]` into an ordered `TEXT[]`.

**Hint:** `array_agg(value ORDER BY ordinality)`.

### Exercise 19 — to_jsonb

Convert `ARRAY[1,2,3]` into a JSONB array.

**Hint:** `to_jsonb`.

### Exercise 20 — row_to_json

Convert a row with `order_id` and `status` into a JSON object.

**Hint:** `row_to_json(alias)` or `to_jsonb(alias)`.

### Exercise 21 — build_object

Create an object with keys `id`, `status`, and `active`.

**Hint:** `jsonb_build_object`.

### Exercise 22 — jsonb_agg

Aggregate product rows into a JSON array ordered by SKU.

**Hint:** `jsonb_agg(... ORDER BY sku)`.

### Exercise 23 — Empty Aggregate

Why is `COALESCE(jsonb_agg(...),'[]'::jsonb)` needed?

**Hint:** 0 rows return SQL NULL.

### Exercise 24 — LEFT JOIN Child Placeholder

Why does JSON output contain an object with NULL `sku` when an order has no items? How do you fix it?

**Hint:** `FILTER (WHERE i.order_id IS NOT NULL)`.

### Exercise 25 — Order Preservation

How do you output items ordered by `line_no`?

**Hint:** `ORDER BY` inside `jsonb_agg`.

### Exercise 26 — Object Map

Build an object mapping `order_id::TEXT -> status`.

**Hint:** `jsonb_object_agg`.

### Exercise 27 — NULL Object Key

Can SQL NULL be aggregated as a JSON object key?

**Hint:** no; validate/filter first.

### Exercise 28 — Round-Trip

Why is JSON text not guaranteed to match byte-for-byte after typed conversion?

**Hint:** JSONB canonicalization and numeric/timestamp formatting.

### Exercise 29 — Validation

Can `{"quantity":-5}` convert to `INTEGER`? Does it pass `CHECK(quantity > 0)`?

**Hint:** type conversion succeeds, but the constraint rejects it.

### Exercise 30 — Cast Failure

If one item has `quantity="abc"`, will the other items still be inserted?

**Hint:** no; the entire statement fails.

### Exercise 31 — GIN Index

Does a GIN index on `payload` automatically speed up `recordset` across every input?

**Hint:** no; it mainly accelerates matching filter predicates.

### Exercise 32 — Large JSON Output

Why should you not `jsonb_agg` millions of orders into a single response?

**Hint:** memory, latency, and network limits.

### Exercise 33 — Authorization

Can you trust `customer_id` / `tenant_id` inside client JSON to modify any order?

**Hint:** no; enforce authorization and tenant scoping.

### Exercise 34 — DISTINCT

Should two order lines with the same SKU but different `line_no` be collapsed with `DISTINCT`?

**Hint:** no, when both are valid lines.

### Exercise 35 — JOIN Multiplication

An order has 3 items and 2 payments; what is the risk of joining both and then aggregating items?

**Hint:** produces 6 intermediate rows; aggregate each branch separately.

## 54. Frequently Asked Questions

### Should I use json or jsonb?

JSONB is usually better for querying, indexing, and transforming; JSON suits cases needing near-verbatim input text. No single choice fits every application.

### Does jsonb_to_recordset preserve JSON array order?

SQL sets have no guaranteed order without `ORDER BY`. When order matters, use `jsonb_array_elements WITH ORDINALITY` and store the position.

### Does jsonb_to_record infer SQL types from JSON automatically?

No. It requires an `AS` column definition list. `jsonb_populate_record` uses a base composite type.

### Can nested objects be converted?

Yes, via JSONB columns, `LATERAL`/record conversion, JSON paths, or composite types, depending on which fields are needed.

### How does a missing key differ from JSON null?

In JSONB they are distinguishable; once converted to SQL records or extracted with `->>`, both become SQL NULL. Check key presence explicitly when business logic depends on the difference.

### Does a round-trip preserve exact original JSON text?

Not guaranteed. JSONB and SQL types canonicalize representations. Verify semantics and business fields instead.

### Is jsonb_agg suitable for exporting millions of rows?

Usually you need pagination, batching, or streaming rather than one massive JSONB aggregate.

### Should every attribute live in JSONB instead of SQL columns?

Flexible fields fit JSONB; stable fields needing FKs, `CHECK`s, joins, indexes, and analytics are easier to govern as typed columns. Both can be combined.

### Why does an entire recordset fail when one element is bad?

A single failing type conversion aborts the statement. To isolate per-item errors, stage raw JSON, expand elements, and validate before casting.

## 55. Summary

- **JSON object → one typed row:** `jsonb_to_record` / `json_to_record`.
- **JSON array of objects → multiple typed rows:** `jsonb_to_recordset` / `json_to_recordset`.
- **JSON matching an existing composite type:** `jsonb_populate_record` / `jsonb_populate_recordset`.
- **JSON array → individual elements:** `jsonb_array_elements`; add `WITH ORDINALITY` to preserve position.
- **Parent row + child array:** `CROSS JOIN LATERAL` or `LEFT JOIN LATERAL` depending on whether empty-array parents should be dropped or kept.
- **JSON object key/value → rows:** `jsonb_each` and `jsonb_each_text`.
- **`->` returns JSON(B), `->>` returns TEXT**; numeric or temporal types require casting or typed record functions.
- JSON null, SQL NULL, and missing keys differ; `COALESCE` does not turn JSONB null into `[]`.
- **SQL row → JSON object:** `row_to_json` / `to_jsonb`.
- **SQL values → custom JSON object:** `jsonb_build_object`.
- **SQL rows → JSON array:** `jsonb_agg`; **SQL key/value rows → JSON object:** `jsonb_object_agg`.
- **`ORDER BY` inside `jsonb_agg`** determines JSON array order; `WITH ORDINALITY` captures input order.
- **`FILTER` + `COALESCE`** prevents null child placeholders and returns `[]` when no items exist.
- Exporting nested JSON from multiple tables should aggregate each child relation by its key to avoid join multiplication.
- Typed conversion does not replace constraints, authorization, idempotency, or validation.
- JSONB indexes help filter source documents; they do not eliminate array expansion cost.
- Round-trips through JSONB and SQL types do not guarantee byte-for-byte identical JSON text.
- At scale, filter early, bound input/output sizes, paginate, and inspect execution plans.

The core mindset is **knowing the exact data shape before and after conversion**: single object vs. array, one row vs. many rows, parent vs. child. Separating each layer cleanly lets PostgreSQL combine JSON flexibility with relational typing, joins, aggregations, and constraints for both ETL pipelines and APIs.
