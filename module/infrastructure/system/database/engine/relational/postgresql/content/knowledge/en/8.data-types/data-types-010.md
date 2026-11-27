# json, jsonb, and Selection Criteria in PostgreSQL

In a sales system, most core information has a fairly stable structure: order ID, customer, total amount, creation time, and status. Such fields typically fit relational columns with explicit data types. However, some data is inherently flexible: product attributes that vary by category, per-customer settings, responses from external services, event payloads, or snapshots of shipping addresses. PostgreSQL provides two JSON data types—**`json`** and **`jsonb`**—to store these structures in the database.

Both types represent valid JSON data, yet they are **not equivalent in storage format, processing speed, operators, or indexing capabilities**. When looking only at a simple object like `{"status":"paid"}`, the choice might seem trivial. Once you need to filter millions of rows by `status`, update a nested key, preserve an exact partner payload, or detect duplicate keys in JSON, the difference becomes substantial.

This lesson explains:

- How PostgreSQL stores and normalizes `json` and `jsonb`.
- Differences in **key ordering, whitespace, duplicate keys, validation, and numeric precision**.
- Query operators, JSON builder functions, object/array handling, and SQL/JSON paths.
- Choosing between GIN indexes, B-tree expression indexes, or generated columns per query pattern.
- How to decide between `json`, `jsonb`, and standard relational table design.
- Limitations around updates, schema enforcement, sensitive data, migrations, and concurrency.

Examples use modern PostgreSQL, especially major versions 14 and later. Certain features were introduced in specific releases; when deploying, verify `SHOW server_version;` and consult documentation for your exact major version.

## 1. JSON Is a Data Structure, Not Just an Arbitrary String

JSON (*JavaScript Object Notation*) is a format for representing structured values. Valid JSON constructs include:

| Kind | JSON Example | Notes |
| --- | --- | --- |
| Object | `{"sku":"BOOK-SQL","quantity":2}` | Collection of name–value pairs; key names are strings. |
| Array | `["sql","database"]` | Ordered list of JSON values. |
| String | `"PostgreSQL"` | JSON strings use double quotes. |
| Number | `250000.50` | Numeric value per JSON syntax. |
| Boolean | `true` or `false` | Not the string `"true"`. |
| Null | `null` | Null **inside JSON**, distinct from SQL `NULL`. |

Objects can nest objects and arrays; arrays can contain objects and other JSON types:

```json
{
  "order_id": 1001,
  "status": "paid",
  "customer": {
    "id": 10,
    "name": "Lan"
  },
  "tags": ["priority", "gift"],
  "shipping": null,
  "items": [
    {"sku": "BOOK-SQL", "quantity": 2},
    {"sku": "NOTE-A5", "quantity": 1}
  ],
  "amount": 250000
}
```

Not every piece of text with curly braces is valid JSON. For instance, `{'status':'paid'}` is invalid JSON because it uses single quotes for keys and strings; `{"a": 1,}` is also invalid because of the trailing comma.

**Distinguish two levels of quotes:** in SQL statements, a JSON literal is wrapped in an SQL single-quoted string, while inside JSON you must use double quotes:

```sql
SELECT '{"status": "paid", "quantity": 2}'::jsonb;
```

Here the outer `'... '` is SQL literal syntax; the inner `"..."` is JSON syntax.

## 2. PostgreSQL Has Two Types: json and jsonb

PostgreSQL provides:

1. **`json`:** stores an exact copy of the **input JSON text**, after validating JSON syntax. Queries generally need to re-parse the text content during execution.
2. **`jsonb`:** converts input JSON into a **parsed binary representation**, optimized for searching, comparing, and indexing.

The `b` in `jsonb` refers to PostgreSQL's *binary* representation—**it does not mean** a universal "binary JSON" wire format you can send directly to other database engines intact. It is PostgreSQL's internal format.

### 2.1. High-Level Comparison Table

| Criterion | `json` | `jsonb` |
| --- | --- | --- |
| Storage | Syntax-validated input JSON text | Parsed and reorganized binary representation |
| Preserves original whitespace | Yes | Does not preserve |
| Preserves original object key order | Yes | Not guaranteed; PostgreSQL stores keys in its own order |
| Preserves duplicate object keys in input | Retains duplicate pairs | Keeps only one value per key, typically the **last value** in input |
| Ingestion overhead | Typically less conversion work | Must parse/convert into binary representation |
| Repeated querying | Usually re-parses text during processing | Typically faster and more convenient for most queries |
| Specialized containment/existence operators | Not directly like `jsonb` | Has `@>`, `?`, `?|`, `?&`, and more |
| GIN indexing on JSON data | Not directly supported like `jsonb` | Supports GIN with `jsonb_ops` or `jsonb_path_ops` |
| Equality comparison for GROUP BY/DISTINCT | No general equality operator on `json` values | Has full equality and comparison operators |
| Best-fit scenario | Must preserve the exact input JSON text | JSON data frequently searched, filtered, updated, validated, and indexed |

In most business applications needing to query JSON attributes, **`jsonb` is the sensible starting choice**. However, do not blindly convert every payload to `jsonb` if the system must preserve key order, duplicate keys, or exact input text formatting.

### 2.2. Example Inspecting Storage and Display

```sql
SELECT
    '{ "b": 2, "a": 1 }'::json  AS original_json,
    '{ "b": 2, "a": 1 }'::jsonb AS normalized_jsonb;
```

With `json`, the input text stays in its original form. With `jsonb`, displayed output normalizes whitespace and key order, for example:

```text
json:   { "b": 2, "a": 1 }
jsonb:  {"a": 1, "b": 2}
```

Never rely on key order in `jsonb::text` output to convey business semantics. A JSON object is inherently an unordered map, not an ordered list like a JSON array.

## 3. Duplicate Keys, Ordering, and Exact Payload Preservation

### 3.1. Duplicate Keys in Objects

A JSON object can contain the same key name multiple times in raw input text:

```sql
SELECT
    '{"status":"draft","status":"paid"}'::json
        AS raw_payload,
    '{"status":"draft","status":"paid"}'::jsonb
        AS parsed_payload;
```

With `json`, the text preserves both `status` entries. With `jsonb`, PostgreSQL keeps only one entry for `status`; when input contains duplicate keys, **the last value wins**, here `"paid"`.

If your ingestion protocol must detect and reject objects with duplicate keys, enforce an appropriate validation policy **before that distinction is lost during conversion to `jsonb`**. Casting `json` to `jsonb` does not raise an error merely for duplicate keys.

### 3.2. Arrays Are Ordered; Objects Have No Business Ordering

```sql
SELECT
    '[1,2]'::jsonb = '[2,1]'::jsonb AS arrays_equal,
    '{"a":1,"b":2}'::jsonb = '{"b":2,"a":1}'::jsonb
        AS objects_equal;
```

Expected output:

```text
arrays_equal  = false
objects_equal = true
```

Because arrays are ordered, changing element order alters equality. Key order inside objects does not affect `jsonb` equality.

### 3.3. Cases Requiring Exact Payload Preservation

Suppose an organization must archive verbatim partner responses for audits or investigations, where whitespace, key order, or duplicate keys carry evidentiary weight:

- Store the input in `json` if **verbatim JSON formatting inside the database** is sufficient and PostgreSQL's decoding/ingestion rules are acceptable.
- If you must preserve **every raw byte of an HTTP request**—including encoding, line endings, digital signatures computed over bytes, or non-JSON framing—also store the raw bytes in `bytea` or an appropriate object store. `json` is not a general wrapper for preserving transport-level details outside JSON.
- If fast querying over contents is also needed, store a **derived `jsonb` representation** in a separate column, weighing synchronization and storage overhead.

Never use `jsonb` as the sole archival record when legal or reconciliation workflows require exact byte/text matching against the original input.

## 4. Syntax Validation, Unicode, and Numeric Representation

Both `json` and `jsonb` validate input syntax per PostgreSQL rules and reject malformed JSON:

```sql
-- Valid:
SELECT '{"enabled":true,"retries":3}'::jsonb;

-- Invalid: keys and strings use single quotes in JSON.
-- SELECT '{''enabled'': true}'::jsonb;
```

`jsonb` also enforces constraints of its internal representation. For example:

- Numbers in JSON must fit within PostgreSQL's `numeric` representation when parsed into `jsonb`. Textual `json` can accept certain numeric literals that `jsonb` cannot convert into `numeric`.
- Unicode escape handling in `jsonb` is stricter in cases like Unicode null characters (`\u0000`) or invalid surrogate pairs; `json` and `jsonb` do not behave identically on all escape sequences.
- `jsonb` converts valid Unicode escapes into stored characters in its internal representation and does not guarantee retaining original escape sequences verbatim.

Therefore, if a pipeline ingests external payloads with non-standard Unicode or extreme numeric literals, **never migrate `json → jsonb` in production without testing representative data first**.

### 4.1. JSON Numbers and PostgreSQL numeric

Example:

```sql
SELECT
    jsonb_typeof('123.45'::jsonb) AS json_type,
    ('123.45'::jsonb)::numeric AS numeric_value;
```

`jsonb` stores numbers using PostgreSQL's `numeric` representation, so do not assume every JSON number is a `double precision` float.

However, if a Java application uses `double` to construct the payload before sending it to PostgreSQL, precision loss may **have already occurred before PostgreSQL received the data**. For money, limits, or decimals requiring exactness, use `BigDecimal` in Java or dedicated PostgreSQL `numeric` columns as appropriate.

## 5. Setting Up the Practice Environment

Create a schema and two tables to compare `json` and `jsonb`:

```sql
CREATE SCHEMA IF NOT EXISTS json_lab;

CREATE TABLE json_lab.raw_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload json NOT NULL
);

CREATE TABLE json_lab.orders (
    order_id bigint PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL
        CHECK (jsonb_typeof(details) = 'object')
);
```

Insert a raw text event whose formatting must be preserved:

```sql
INSERT INTO json_lab.raw_events (source_name, payload)
VALUES (
    'external_partner',
    '{ "event": "order_created", "id": 1001, "event": "order_received" }'
);
```

Insert two orders with object-structured `details`:

```sql
INSERT INTO json_lab.orders (order_id, details)
VALUES
(
    1001,
    '{
      "status": "paid",
      "customer": {"id": 10, "name": "Lan"},
      "amount": 250000,
      "tags": ["priority", "gift"],
      "shipping": null,
      "items": [
        {"sku": "BOOK-SQL", "quantity": 2},
        {"sku": "NOTE-A5", "quantity": 1}
      ]
    }'::jsonb
),
(
    1002,
    '{
      "status": "pending",
      "customer": {"id": 20, "name": "Minh"},
      "amount": 80000,
      "tags": ["standard"],
      "items": [
        {"sku": "PEN-BLUE", "quantity": 3}
      ]
    }'::jsonb
);
```

From here on, the illustrative queries can be run against `json_lab.orders` without depending on any external schema. If practicing multiple times, use a dedicated lab database/schema or reset rows carefully to avoid duplicate primary-key errors.

### 5.1. Checking Stored Types

```sql
SELECT
    order_id,
    pg_typeof(details) AS details_type,
    jsonb_typeof(details) AS root_json_type,
    details
FROM json_lab.orders
ORDER BY order_id;
```

Here `pg_typeof(details)` returns the SQL type `jsonb`; `jsonb_typeof(details)` returns the **root JSON value's type**, i.e., `object`. The two functions answer different questions.

## 6. Extracting Values with ->, ->>, #>, and #>>

PostgreSQL supports JSON extraction operators for both `json` and `jsonb`. Master the four core operators:

| Operator | Purpose | Result Type |
| --- | --- | --- |
| `->` | Get object field by key or array element by index | `json` or `jsonb` value, preserving JSON type |
| `->>` | Get field/element as text | `text` |
| `#>` | Get value at a nested path | `json` or `jsonb` |
| `#>>` | Get value at a nested path as text | `text` |

Example:

```sql
SELECT
    order_id,
    details -> 'status'              AS status_jsonb,
    details ->> 'status'             AS status_text,
    details #> '{customer,id}'       AS customer_id_jsonb,
    details #>> '{customer,name}'    AS customer_name_text
FROM json_lab.orders
ORDER BY order_id;
```

For order 1001:

```text
status_jsonb       = "paid"       -- JSON string
status_text        = paid         -- SQL text
customer_id_jsonb  = 10           -- JSON number
customer_name_text = Lan          -- SQL text
```

Crucial difference: `details -> 'status'` returns a **JSON string (displayed with double quotes)**, whereas `details ->> 'status'` returns plain SQL text for comparison against SQL string literals:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

Do not write `WHERE details -> 'status' = 'paid'` expecting PostgreSQL to treat a JSON value identically to `text`. The comparison operator and right-hand operand must have compatible types.

### 6.1. Accessing Array Elements

JSON array indexes are **0-based**:

```sql
SELECT
    order_id,
    details -> 'items' -> 0 AS first_item,
    details #>> '{items,0,sku}' AS first_sku
FROM json_lab.orders;
```

For `order_id = 1001`, the first element is the object with `sku = "BOOK-SQL"`. Extraction operators also support negative indexes counting from the end of an array (e.g., `-> -1`), per PostgreSQL documentation.

### 6.2. Nonexistent Keys

```sql
SELECT
    details ->> 'coupon_code' AS coupon_code
FROM json_lab.orders
WHERE order_id = 1001;
```

When a key does not exist, extraction operators return **SQL NULL** instead of raising an error. This is convenient for flexible schemas, yet can silently hide typos:

```sql
-- Misspelling "status" as "stats":
SELECT details ->> 'stats'
FROM json_lab.orders;
```

If a key is mandatory in the business domain, enforce it via constraints, application validation, or relational columns instead of relying on NULL returns from extraction operators.

## 7. Distinguishing SQL NULL, JSON null, and a Missing Key

This is one of the easiest areas to get wrong when querying JSON in PostgreSQL.

Consider three cases:

```sql
SELECT
    '{"shipping":null}'::jsonb AS json_with_null,
    '{}'::jsonb                AS json_without_key,
    NULL::jsonb                AS sql_null_value;
```

- `'{"shipping":null}'::jsonb` is an object containing key `shipping` with JSON value `null`.
- `'{}'::jsonb` is an object **lacking the key** `shipping`.
- `NULL::jsonb` is an **SQL NULL value** for the entire column/expression, not a JSON object.

Test distinguishing them:

```sql
SELECT
    details ? 'shipping' AS has_shipping_key,
    details -> 'shipping' IS NULL AS extraction_is_sql_null,
    jsonb_typeof(details -> 'shipping') AS shipping_json_type,
    details ->> 'shipping' AS shipping_as_text
FROM json_lab.orders
WHERE order_id = 1001;
```

For order 1001, the key `shipping` exists with a JSON null value:

- `details ? 'shipping'` is `true`.
- `details -> 'shipping'` is the `jsonb` value `null`, **not SQL NULL**.
- `jsonb_typeof(details -> 'shipping')` returns text `'null'`.
- `details ->> 'shipping'` returns SQL NULL because extracting JSON null as text produces SQL NULL.

To find objects where the key exists and holds JSON null:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping'
  AND details -> 'shipping' = 'null'::jsonb;
```

To find objects missing the key:

```sql
SELECT order_id
FROM json_lab.orders
WHERE NOT (details ? 'shipping');
```

**Do not use `->> ... IS NULL` alone to equate "missing key" with "key holds JSON null"** if the business must tell those two states apart.

### 7.1. JSON null in CHECK Constraints

PostgreSQL lets a `CHECK` constraint pass when its expression evaluates to `TRUE` **or SQL NULL**; only `FALSE` triggers a violation. Consequently, a constraint lacking an existence check can fail to catch a missing key.

Example:

```sql
-- Insufficient if status can be omitted:
-- CHECK (details ->> 'status' IN ('paid', 'pending'))
```

To require both presence and type:

```sql
CHECK (
    details ? 'status'
    AND jsonb_typeof(details -> 'status') = 'string'
    AND details ->> 'status' IN ('paid', 'pending')
)
```

When JSON schemas hold core data, enforce required conditions explicitly rather than discovering missing fields only at read time.

## 8. Containment: Operators @> and <@

A major strength of `jsonb` is testing whether **one JSON value contains the structure described by another JSON value**.

Operators:

- `left @> right`: left JSONB value **contains** right JSONB value per containment rules.
- `left <@ right`: left JSONB value **is contained in** right JSONB value.

Example:

```sql
SELECT
    '{"status":"paid","amount":250000}'::jsonb
        @> '{"status":"paid"}'::jsonb AS contains_status,
    '{"status":"paid"}'::jsonb
        <@ '{"status":"paid","amount":250000}'::jsonb
        AS is_contained;
```

Both return `true`.

Practical usage:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

For a nested object:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"customer":{"id":10}}'::jsonb;
```

PostgreSQL checks whether the matching sub-structure is present in the JSONB value without requiring exact key-for-key equality.

### 8.1. Containment with Arrays

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"tags":["priority"]}'::jsonb;
```

This finds objects whose `tags` array contains the element `"priority"`. This query pattern can often leverage a GIN index.

Distinguish **array equality** from **array containment**:

```sql
SELECT
    '[1,2,3]'::jsonb = '[3,2,1]'::jsonb
        AS equal_arrays,
    '[1,2,3]'::jsonb @> '[3,1]'::jsonb
        AS contains_elements;
```

Equality checks exact element order; JSONB containment tests whether elements are present, regardless of array ordering. Do not use `@>` to check "the array equals this exact template array".

### 8.2. Should You Cast json to jsonb Just to Use @>?

If a column is `json`:

```sql
SELECT event_id
FROM json_lab.raw_events
WHERE payload::jsonb @> '{"id":1001}'::jsonb;
```

This cast works for valid convertible payloads, yet every evaluation pays parsing/conversion overhead and changes duplicate-key/formatting semantics. For frequent filter workloads, consider storing `jsonb` or maintaining a derived representation rather than repeatedly casting across millions of rows.

## 9. Checking Key and Element Existence: ?, ?|, ?&

Specialized `jsonb` existence operators:

| Operator | Meaning |
| --- | --- |
| `?` | Does the string exist as a **top-level** object key or top-level array string element? |
| `?|` | Do any of the strings in the array exist as top-level keys/elements? |
| `?&` | Do all of the strings in the array exist as top-level keys/elements? |

Example:

```sql
SELECT
    details ? 'customer' AS has_customer,
    details ?| ARRAY['status', 'coupon_code'] AS has_any,
    details ?& ARRAY['status', 'amount'] AS has_all
FROM json_lab.orders
WHERE order_id = 1001;
```

Common pitfall: `?` does not recursively search nested objects.

```sql
-- Checks key "id" at the root object:
SELECT details ? 'id'
FROM json_lab.orders
WHERE order_id = 1001;

-- Checks key "id" inside the customer object:
SELECT (details -> 'customer') ? 'id'
FROM json_lab.orders
WHERE order_id = 1001;
```

Here `id` lives inside `customer`, not at the root. To filter nested keys, navigate to the nested object or use a suitable query form.

### 9.1. Checking Inside an Array

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

Here `details -> 'tags'` returns a JSONB array, and `?` checks for the string element at the top level of that array.

## 10. SQL/JSON Path and Nested Queries

When JSON structures are deep or you need to filter array elements by predicate, chained `->` operators become verbose. Since PostgreSQL 12, PostgreSQL supports **SQL/JSON path** functions and operators, including `jsonb_path_exists`, `jsonb_path_query`, `jsonb_path_query_first`, `@?`, and `@@`.

Example finding orders containing at least one line item with `quantity >= 2`:

```sql
SELECT order_id
FROM json_lab.orders
WHERE jsonb_path_exists(
    details,
    '$.items[*] ? (@.quantity >= 2)'
);
```

Or using the operator:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @? '$.items[*] ? (@.quantity >= 2)';
```

In the path expression:

- `$` is the root JSON value.
- `.items` accesses the `items` key.
- `[*]` iterates over array elements.
- `? (...)` filters elements matching the predicate.
- `@` represents the current item evaluated inside the filter.

Extracting matching line items:

```sql
SELECT
    order_id,
    jsonb_path_query(
        details,
        '$.items[*] ? (@.quantity >= 2)'
    ) AS matching_item
FROM json_lab.orders
ORDER BY order_id;
```

`jsonb_path_query` can emit **multiple rows** from a single JSON document. If an order has multiple matching items, the output contains multiple rows for that `order_id`.

### 10.1. @? vs. @@

- `@?` evaluates whether the path returns at least one matching item under path-existence semantics.
- `@@` evaluates a **JSONPath predicate/check expression**, returning a Boolean or SQL NULL per PostgreSQL rules.

Predicate example:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @@ '$.amount > 100000';
```

Do not treat `@?` and `@@` as universally interchangeable across all path expressions. When designing checks for existence, predicates, missing fields, and types, consult the JSONPath documentation for your major PostgreSQL version.

### 10.2. When Is JSONPath a Good Choice?

JSONPath is helpful when:

- Objects and arrays are deeply nested.
- You need to test whether an element exists matching a condition.
- You want to avoid verbose manual `jsonb_array_elements` expansions.
- Expressions match index patterns supported by PostgreSQL.

However, **not every JSONPath predicate is accelerated by GIN**. Indexability depends on the operator, operator class, and exact predicate extractability. Range comparisons like `>` on nested fields often require separate evaluation.

## 11. Expanding JSON Arrays into SQL Rows

When aggregating, joining, or validating array elements, use *set-returning functions* with `LATERAL`.

### 11.1. jsonb_array_elements

```sql
SELECT
    o.order_id,
    item.value ->> 'sku' AS sku,
    (item.value ->> 'quantity')::integer AS quantity
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.details -> 'items') AS item(value)
ORDER BY o.order_id, sku;
```

Each object in `items` becomes an SQL row. `LATERAL` lets the function reference the `details` column of the current `orders` row.

**Caution:** `jsonb_array_elements` expects a JSON array. If `items` is an object or JSON null, the query will error. For heterogeneous data, check `jsonb_typeof` or guard safely before invoking the function.

Example safely handling non-array values:

```sql
SELECT
    o.order_id,
    item.value
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.details -> 'items') = 'array'
            THEN o.details -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS item(value);
```

This `CASE` substitutes an empty array when the value is not an array. Depending on business rules, silently skipping malformed types may be undesirable; if `items` is required, validate and reject invalid payloads at write time.

### 11.2. jsonb_to_recordset

If an array consists of objects with a fairly stable schema:

```sql
SELECT
    o.order_id,
    i.sku,
    i.quantity
FROM json_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_to_recordset(o.details -> 'items')
        AS i(sku text, quantity integer)
ORDER BY o.order_id, i.sku;
```

`jsonb_to_recordset` turns each object into a typed SQL record with the declared columns. This is a convenient **extraction tool**, not a replacement for an `order_items` table with primary keys, foreign keys, and indexes when line items are queried or updated individually.

### 11.3. array_length and Value Types

```sql
SELECT
    order_id,
    jsonb_array_length(details -> 'items') AS item_count
FROM json_lab.orders;
```

This works only when `details -> 'items'` is a JSON array. Never assume every JSON property always has the expected type if the application permits arbitrary payloads.

## 12. Building JSON Using PostgreSQL Functions

Never build JSON by manually concatenating strings like `'{"name":"' || name || '"}'`. Customer names can contain quotes, newlines, or characters needing escaping; manual string concatenation easily yields invalid JSON and introduces injection/corruption risks.

PostgreSQL provides dedicated JSON builder functions:

| Function | Purpose |
| --- | --- |
| `json_build_object` | Build a JSON object from key/value pairs, returning `json` |
| `jsonb_build_object` | Same, returning `jsonb` |
| `json_build_array` / `jsonb_build_array` | Build a JSON array |
| `to_json` / `to_jsonb` | Convert an SQL value into an appropriate JSON representation |
| `row_to_json` | Convert an SQL composite/record into a JSON object |
| `json_agg` / `jsonb_agg` | Aggregate multiple values into a JSON array |
| `json_object_agg` / `jsonb_object_agg` | Aggregate key/value pairs into a JSON object |

Example:

```sql
SELECT jsonb_build_object(
    'order_id', 1001,
    'status', 'paid',
    'priority', true,
    'tags', jsonb_build_array('gift', 'priority')
) AS order_payload;
```

Building a summary object per order:

```sql
SELECT jsonb_build_object(
    'order_id', order_id,
    'status', details ->> 'status',
    'amount', details -> 'amount'
) AS summary
FROM json_lab.orders
ORDER BY order_id;
```

Here `details -> 'amount'` preserves the JSON number type instead of turning it into text, whereas `details ->> 'status'` extracts SQL text that `jsonb_build_object` encodes as a JSON string.

### 12.1. jsonb_agg and Ordering

```sql
SELECT jsonb_agg(
    jsonb_build_object(
        'order_id', order_id,
        'status', details ->> 'status'
    )
    ORDER BY order_id
) AS order_summaries
FROM json_lab.orders;
```

Placing `ORDER BY order_id` **inside** the aggregate call determines element order in the resulting JSON array. Omitting `ORDER BY` leaves aggregate input order unspecified by SQL.

### 12.2. Should JSON Be Assembled in the Database or in Java?

It depends on architectural boundaries:

- Building JSON in PostgreSQL is useful for reporting, aggregations, or complex query projections after weighing CPU/network trade-offs.
- Java can serialize DTOs using standard JSON libraries after querying relational columns.
- Never assemble a massive single-row JSON payload in one query just to bypass proper pagination or streaming in the application layer.

This choice is about responsibility boundaries and operational cost—not that every API endpoint should construct its entire JSON response inside SQL simply because `jsonb_build_object` exists.

## 13. Updating JSONB: jsonb_set, jsonb_insert, and the || Operator

A `jsonb` value can be modified using functions that return a **new JSONB value** assigned back to the column.

### 13.1. Replacing a Key's Value

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{status}',
    '"shipped"'::jsonb,
    true
)
WHERE order_id = 1001;
```

Explanation:

- First argument is the source JSONB.
- `'{status}'` is the path as a `text[]`.
- `'"shipped"'::jsonb` is a **JSON string**—not unquoted text `shipped`.
- The final `true` permits creating the **leaf key** of the path if missing, per function semantics.

Updating a nested property:

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{customer,name}',
    to_jsonb('Nguyễn Lan'::text),
    false
)
WHERE order_id = 1001;
```

`to_jsonb('Nguyễn Lan'::text)` is safer than hand-quoting JSON strings because PostgreSQL handles serialization and escaping cleanly.

**Important limitation:** `jsonb_set` does not automatically create missing intermediate objects along the path. If `customer` does not exist and the path is `'{customer,name}'`, setting `create_if_missing = true` will not synthesize missing parent objects from scratch. Ensure parent objects exist or use an appropriate update expression.

### 13.2. Deleting a Key

```sql
UPDATE json_lab.orders
SET details = details - 'shipping'
WHERE order_id = 1001;
```

For JSONB objects, `-` removes a top-level key. You can also remove by nested path using `#-`:

```sql
UPDATE json_lab.orders
SET details = details #- '{customer,name}'
WHERE order_id = 1001;
```

This alters data semantics: a missing key differs from a key holding JSON null. Clearly specify whether business logic means "remove property" or "set property to null".

### 13.3. Concatenating/Merging with ||

```sql
SELECT
    '{"status":"draft","customer":{"id":10}}'::jsonb
    ||
    '{"status":"paid","source":"api"}'::jsonb
    AS merged;
```

At the top object level, duplicate keys take the right-hand value. However, `||` is **not a general deep merge**; nested objects sharing a key are replaced wholesale at that key.

Example:

```sql
SELECT
    '{"customer":{"id":10,"name":"Lan"}}'::jsonb
    ||
    '{"customer":{"name":"Minh"}}'::jsonb;
```

Do not expect this to deep-merge and keep `customer.id`. To update only `customer.name`, use `jsonb_set` with the nested path or explicit recursive merge logic.

### 13.4. Inserting an Element into an Array

```sql
SELECT jsonb_insert(
    '["a","c"]'::jsonb,
    '{1}',
    '"b"'::jsonb
) AS inserted_array;
```

This illustrates inserting an element at a position in a JSONB array. When individual items change frequently, a dedicated child table with explicit keys and ordering is usually easier to maintain than mutating large JSON arrays.

## 14. Every JSONB UPDATE Has Real Cost

`jsonb_set` feels like patching a tiny piece of a document, yet PostgreSQL uses MVCC: a standard `UPDATE` writes a **new row version**, rather than modifying a few bytes in place inside an existing tuple.

When updating a large JSONB document:

- PostgreSQL may construct a whole new JSONB value.
- A new row version is written while the old version awaits VACUUM cleanup.
- Additional WAL, I/O, and potential index updates occur.
- For large values, PostgreSQL uses TOAST compression/out-of-line storage; updating one nested field does not guarantee only that field is written to storage.
- If GIN or expression indexes depend on the updated JSONB column, index maintenance overhead can be substantial.

For example, storing `items` as a JSONB array of thousands of elements and continually updating individual item `quantity` values usually performs worse than a separate `order_items` table keyed by `(order_id, line_no)` when items are updated/queried independently.

**Practical rule:** data primarily read/returned as a whole and rarely updated fits JSONB well; data frequently updated per element, joined, and relationally constrained usually belongs in dedicated relational columns/tables.

## 15. GIN Indexes for JSONB

When tables grow large and queries frequently filter by JSON structure, `jsonb` supports **GIN (Generalized Inverted Index)**.

Example:

```sql
CREATE INDEX idx_orders_details_gin
ON json_lab.orders
USING gin (details);
```

This uses the default `jsonb_ops` operator class. It supports query patterns such as:

```sql
-- Find documents containing a key/value pair.
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;

-- Find objects with a top-level key.
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping';

-- Find objects with at least one of two keys.
SELECT order_id
FROM json_lab.orders
WHERE details ?| ARRAY['shipping', 'coupon_code'];
```

GIN is not magic that turns every SQL query into O(1). The planner decides whether to use the index based on statistics, selectivity, and cost. A two-row lab table will naturally use a sequential scan; that does not mean the index is broken.

### 15.1. Two Important Operator Classes

PostgreSQL provides two notable GIN operator classes for JSONB:

| Operator Class | Key Supported Search Operators | Trade-off |
| --- | --- | --- |
| `jsonb_ops` | `?`, `?|`, `?&`, `@>`, `@?`, `@@` | Flexible, supports key-existence operators; typically the default |
| `jsonb_path_ops` | `@>`, `@?`, `@@` | Often produces a smaller/more specialized index for containment and supported JSONPaths; **does not support** `?`, `?|`, `?&` like `jsonb_ops` |

Example creating an index with `jsonb_path_ops`:

```sql
CREATE INDEX idx_orders_details_path
ON json_lab.orders
USING gin (details jsonb_path_ops);
```

Having both indexes on the same column in the lab merely demonstrates syntax; **do not maintain both in production** unless justified. Choose based on actual query operators, index footprint, and write overhead.

### 15.2. When Is jsonb_path_ops Appropriate?

A system primarily querying:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"customer":{"id":10}}'::jsonb;
```

can consider `jsonb_path_ops` for containment-focused indexing. However, if queries often run:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ? 'shipping';
```

then `jsonb_path_ops` does not directly support `?`. You need `jsonb_ops`, an expression index, or an alternate query predicate.

**JSONPath note:** both operator classes can accelerate certain `@?` and `@@` expressions, yet whether PostgreSQL extracts an indexable condition depends on path structure and comparisons. Never assume "having a JSONB index" accelerates every JSONPath function or check.

### 15.3. GIN Indexes Carry Overhead Too

The benefit is scanning fewer rows when predicates are selective. In return:

- Index creation takes CPU, I/O, and disk space.
- `INSERT`, `UPDATE`, and `DELETE` must maintain the GIN index.
- Indexes can grow large if documents contain many distinct keys and values.
- Low-selectivity predicates may still trigger sequential scans.
- Sorting and range queries are not inherently served by GIN.

Benchmark real workloads instead of blindly adding GIN indexes to every `jsonb` column.

## 16. B-Tree Expression Indexes for Frequently Filtered Paths

If an application almost always filters on one fixed key such as `status`, a **B-tree expression index** can be simpler and more efficient than indexing the entire document with GIN.

```sql
CREATE INDEX idx_orders_status
ON json_lab.orders ((details ->> 'status'));
```

Query:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

The query's expression must match the indexed expression so the planner can consider the index. Do not assume a B-tree index on `details ->> 'status'` accelerates containment queries like:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

That query has similar business filtering semantics here, yet **uses a different operator form**; check `EXPLAIN` to see which index the planner selects.

### 16.1. Indexing Numeric Values Inside JSONB

To filter numerically on `customer.id`:

```sql
CREATE INDEX idx_orders_customer_id
ON json_lab.orders
(((details #>> '{customer,id}')::bigint));
```

Query:

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details #>> '{customer,id}')::bigint = 10;
```

**Critical warning:** if any row has `customer.id = "abc"` or a value unconvertible to `bigint`, index creation or future writes will fail. Validate types/domains with constraints or ingestion checks before casting inside an index expression.

For keys with stable types and constraints, a standard relational `customer_id bigint` column is usually **much clearer and supports foreign keys cleanly** compared to burying critical IDs inside JSONB and repeatedly casting them.

### 16.2. Indexing a Specific JSONB Branch

Suppose `tags` is queried frequently:

```sql
CREATE INDEX idx_orders_tags_gin
ON json_lab.orders
USING gin ((details -> 'tags'));
```

Matching query:

```sql
SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

Branch indexes can be smaller than full-document indexes when queries target only a sub-tree. However, if many distinct paths are queried simultaneously, maintaining numerous expression indexes can cost more than a well-chosen GIN strategy.

## 17. EXPLAIN and Verifying Real Index Effectiveness

After creating indexes, run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"status":"paid"}'::jsonb;
```

And:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM json_lab.orders
WHERE details ->> 'status' = 'paid';
```

Key details to inspect:

- `Seq Scan`, `Index Scan`, `Bitmap Index Scan`, and `Bitmap Heap Scan`: how PostgreSQL retrieves rows.
- `Index Cond`: predicate applied at index lookup time, if any.
- `Filter`: predicate checked after fetching rows.
- `Rows Removed by Filter`: rows discarded at that step.
- `Buffers`: pages read or hit in buffer cache per EXPLAIN statistics.
- Execution time and actual vs. estimated row counts.

With only a couple of rows in the lab, PostgreSQL will likely pick `Seq Scan` because scanning one page is cheapest. Never force indexes or declare them useless based on tiny tables.

### 17.1. Measure Read and Write Costs Together

A GIN index may accelerate `@>` lookups while slowing transactions that update `details` frequently. Evaluate all of:

1. P95/P99 latency of critical read queries.
2. `INSERT`/`UPDATE`/`DELETE` latencies.
3. Table, index, and WAL storage footprint.
4. Key selectivity and actual row counts.
5. Impact on autovacuum, buffer cache, bulk loads, and concurrency.

Never adopt `jsonb` and indexes based solely on a single `LIMIT 1` test query over unrepresentative data.

### 17.2. pg_column_size Is Not a Full Benchmark

You can inspect individual value sizes:

```sql
SELECT
    pg_column_size('{"a":1,"b":2}'::json) AS json_size,
    pg_column_size('{"a":1,"b":2}'::jsonb) AS jsonb_size;
```

Yet there is no universal rule that `jsonb` is **always** smaller than `json` or vice versa. Actual size depends on document contents, representation, compression/TOAST, and metadata. `pg_column_size` here does not represent total table, index, WAL, and I/O costs across a full workload.

## 18. Enforcing JSONB Schemas with CHECK Constraints and Relational Columns

JSON is flexible, yet "flexible" should never mean "accept arbitrary malformed data".

Suppose every order must have:

- `status` in an allowed list.
- `amount` as a JSON number.
- `customer` as a JSON object whose `id` is a JSON number.
- `items` as a JSON array.

You can add constraints:

```sql
ALTER TABLE json_lab.orders
ADD CONSTRAINT ck_orders_details_shape
CHECK (
    jsonb_typeof(details) = 'object'
    AND details ? 'status'
    AND jsonb_typeof(details -> 'status') = 'string'
    AND details ->> 'status'
        IN ('pending', 'paid', 'shipped', 'cancelled')
    AND details ? 'amount'
    AND jsonb_typeof(details -> 'amount') = 'number'
    AND details ? 'customer'
    AND jsonb_typeof(details -> 'customer') = 'object'
    AND jsonb_typeof(details #> '{customer,id}') = 'number'
    AND details ? 'items'
    AND jsonb_typeof(details -> 'items') = 'array'
);
```

This validates **basic structural shape**, not a full JSON Schema specification. It does not inspect every element inside `items`, enforce that `customer.id` references a row in a customers table, or enforce all monetary rules.

### 18.1. CHECK and SQL NULL

To require a field's presence, `details ? 'status'` yields an unambiguous Boolean. When writing constraints relying solely on extraction expressions that can return SQL NULL, remember PostgreSQL `CHECK` accepts UNKNOWN/NULL just like TRUE—only FALSE fails.

Therefore, for mandatory JSON fields, check **existence, type, and value domain** rather than checking `->>` output alone.

### 18.2. When Should You Promote Fields to Relational Columns?

If `status`, `amount`, and `customer_id` are critical fields used heavily in:

- Frequent `WHERE` / `JOIN` clauses,
- Foreign keys and uniqueness constraints,
- Table partitioning,
- Column-level permissions,
- Multi-dimensional business reporting,
- Updates independent of the rest of the payload,

then a hybrid schema is usually a better fit:

```sql
CREATE TABLE json_lab.business_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    amount numeric(14, 2) NOT NULL
        CHECK (amount >= 0),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object')
);
```

Identity, monetary amounts, and status live in strictly typed, constrained columns. `attributes` holds extensible properties that vary by order category or future needs.

This is often the balanced sweet spot: combining **relational integrity** with JSONB flexibility instead of forcing everything into one document.

## 19. JSONB Does Not Automatically Replace Foreign Keys and Relational Constraints

Suppose an object contains:

```json
{"customer":{"id":10},"product_id":100}
```

Having a `product_id` key inside JSONB **does not create a foreign key** to a `products` table. PostgreSQL does not infer referential integrity across tables merely from matching JSON key names.

When a relationship is core to the business:

```sql
CREATE TABLE json_lab.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE json_lab.order_headers (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES json_lab.customers(customer_id),
    extra_attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

In this design, `customer_id` is a foreign-key column; `extra_attributes` does not take over that responsibility.

### 19.1. Array of Objects or Child Table?

Two ways to model order lines:

**In JSONB:**

```json
{"items":[{"sku":"BOOK-SQL","quantity":2},{"sku":"NOTE-A5","quantity":1}]}
```

**In a relational table:**

```sql
CREATE TABLE json_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES json_lab.order_headers(order_id),
    line_no integer NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

A child table is better whenever you must:

- Update or cancel individual lines independently.
- Enforce uniqueness on `(order_id, line_no)`.
- JOIN against products and enforce foreign keys.
- Search orders by SKU using relational indexes.
- Aggregate quantities sold per SKU across the system.

A JSONB array can fit an **infrequently updated snapshot payload**, such as an external partner response or descriptive attachment. You do not need to normalize every nested object into a table when there is no benefit, yet never treat one large document as a drop-in substitute for every one-to-many relationship.

## 20. Generated Columns Paired with JSONB

When a JSONB key is queried heavily and uses an eligible expression, consider a **generated column** to expose it with an explicit SQL type.

Example creating a table with a `status` column derived from JSONB:

```sql
CREATE TABLE json_lab.order_documents (
    order_id bigint PRIMARY KEY,
    details jsonb NOT NULL
        CHECK (jsonb_typeof(details) = 'object'),
    status text GENERATED ALWAYS AS
        (details ->> 'status') STORED
);

CREATE INDEX idx_order_documents_status
ON json_lab.order_documents (status);
```

The application can query:

```sql
SELECT order_id
FROM json_lab.order_documents
WHERE status = 'paid';
```

PostgreSQL keeps the generated column synchronized with the declared expression, eliminating the risk of a writer updating `details.status` while forgetting a separate duplicate `status` column. However:

- Generated expressions have restrictions on immutable functions and references depending on PostgreSQL version.
- Using a generated column does not automatically enforce foreign keys across arbitrary nested JSON arrays.
- If the key is missing, the extracted value is SQL NULL; add `NOT NULL` or `CHECK` if required by business rules.
- In PostgreSQL 12–17, generated columns are commonly known in stored form; newer major releases may add options. Consult the exact manual for your version when using specific syntax.

If a key is a core business field, it is often cleaner to store it directly as a normal relational column from the start and leave only extensible attributes in JSONB.

## 21. Concurrent Updates and the Risk of Document Overwrites

A common issue—not unique to JSONB, yet especially acute with large documents—is **application-side read–modify–write**.

Suppose two services both read:

```json
{"status":"pending","note":"initial"}
```

Then:

- Service A changes `status` to `paid` in its deserialized Java object.
- Service B changes `note` to `reviewed` in its deserialized Java object.
- Both write back the **entire document** based on their stale initial read.

Without a concurrency strategy, the second write overwrites the first service's change even though the two services edited completely different keys.

### 21.1. Updating Database-Side in a Single SQL Statement

Instead of writing back a full client-built document from an older snapshot:

```sql
UPDATE json_lab.orders
SET details = jsonb_set(
    details,
    '{status}',
    to_jsonb('paid'::text),
    true
)
WHERE order_id = 1002;
```

This update computes over the current `details` value inside PostgreSQL under row-level locking. It prevents certain blind whole-document overwrites from stale reads, yet **does not solve all business races**: two writers concurrently modifying `status` still need state-transition checks, versioning, or conditional `WHERE` predicates.

### 21.2. Optimistic Locking with a Version Column

A general pattern:

```sql
CREATE TABLE json_lab.versioned_documents (
    document_id bigint PRIMARY KEY,
    version_no bigint NOT NULL DEFAULT 0,
    payload jsonb NOT NULL
);
```

The application reads `version_no` and updates only if the version still matches:

```sql
UPDATE json_lab.versioned_documents
SET
    payload = jsonb_set(
        payload,
        '{status}',
        to_jsonb('paid'::text),
        true
    ),
    version_no = version_no + 1
WHERE document_id = 1001
  AND version_no = 7;
```

If 0 rows are updated, the document either does not exist or its version changed concurrently. The application should re-read, resolve the conflict, and retry per business rules—never blindly increment the version and force-overwrite data.

**Never treat MVCC as a guarantee that two client-edited copies of a document will merge cleanly key-by-key.**

## 22. Security: A Single JSONB Column Can Hold Mixed Data Sensitivity

Storing personal info, tokens, and operational metadata inside one JSONB document can widen data access scope beyond what was intended.

Example:

```json
{
  "customer_name": "Lan",
  "email": "lan@example.test",
  "internal_note": "VIP",
  "payment_reference": "masked-reference"
}
```

If a role holds `SELECT` on the `details` column, PostgreSQL **does not restrict privileges per JSON key automatically**. Anyone permitted to select the column can read all properties inside that document.

Principles:

1. Never place credentials, tokens, or secrets inside payloads readable by broad services unless strictly required.
2. Keep sensitive fields in separate columns or tables when distinct access controls are needed.
3. When exposing filtered views, verify view privileges, `SECURITY INVOKER`/`DEFINER` semantics for your major version, and all indirect query paths.
4. Apply masking/filtering in application serialization before sending JSON to APIs or logs.
5. Maintain retention and deletion policies for both raw archival copies and derived documents.

### 22.1. SQL Injection Does Not Disappear with JSONB

Always parameterize SQL statements. Never build queries by concatenating user-supplied JSONPaths, keys, or values directly into raw SQL strings.

In Java applications, use `PreparedStatement` or parameterized ORM/driver APIs. When building JSON predicates from inputs, strictly separate **bound data parameters** from **SQL syntax and JSONPath structure**; if dynamic JSONPaths are needed, validate against an allowlist and use proper API mechanisms.

JSONB is a storage type, not an automatic SQL injection shield.

## 23. Migrating from json to jsonb

A historical table may have a `payload json` column and later require fast searches across nested keys. You can consider migrating to `jsonb`:

```sql
-- ILLUSTRATIVE in a test environment:
-- ALTER TABLE json_lab.raw_events
-- ALTER COLUMN payload TYPE jsonb
-- USING payload::jsonb;
```

**Never run this directly in production without auditing data and planning the migration.** Risks include:

- Duplicate object keys collapse per `jsonb` rules; original whitespace and key ordering are discarded.
- Certain `json` values may fail conversion to `jsonb` due to Unicode or numeric limits.
- `ALTER TABLE ... TYPE` can require a full table rewrite, exclusive locks, and heavy I/O, impacting WAL and write availability.
- Dependent views, functions, indexes, prepared statements, and Java mappings may break or need updates.
- Queries relying on `payload::text` formatting will observe changed output after conversion.

### 23.1. Controlled Migration Approach

If you need both the original text and JSONB queryability:

```sql
ALTER TABLE json_lab.raw_events
ADD COLUMN parsed_payload jsonb;
```

Then:

1. Audit values that fail conversion, especially payloads from external systems.
2. Verify whether duplicate keys, key order, or verbatim text must be preserved.
3. Backfill in batches while controlling concurrent writes during transition.
4. Dual-write new updates and reconcile both columns under **agreed semantics**.
5. Test indexes, queries, and clients against the new column.
6. Switch primary readers only after verifying correctness and performance.

The SQL above only adds the column; it does not build synchronization automatically. If both columns must coexist, explicitly design triggers, application dual-writes, or backfill jobs plus conversion-error handling.

### 23.2. Should Both json and jsonb Be Stored Long-Term?

Yes, if the two columns serve **distinct purposes**, for example:

- `raw_payload json` for auditing verbatim input JSON.
- `parsed_payload jsonb` for filtering and analytics.

In return, you pay storage, synchronization, and backup costs for keeping both. When verbatim formatting is not required, storing only `jsonb` is usually simpler.

## 24. Choosing json, jsonb, or Relational Tables?

A workload-based decision matrix:

| Requirement | Option to Consider | Reason |
| --- | --- | --- |
| Preserve partner's exact JSON text for reconciliation/audit | `json`, or raw bytes separately if byte-for-byte fidelity is needed | `json` keeps input JSON text in storage; `jsonb` normalizes representation |
| Filter many records by nested JSON keys/values | `jsonb` | Offers containment, JSONPath, and GIN indexes |
| Flexible configs read/written as a unit with rare schema changes | `jsonb` | Convenient manipulation and querying without schema churn for every attribute |
| Values heavily used for JOINs, foreign keys, or UNIQUE | Relational columns | Direct relational constraints, indexes, and strict typing |
| Line-item lists updated independently and frequently | Relational child table | Clear keys, FKs, row locking, and item-level queries |
| Infrequently queried snapshots of external responses | `json` or `jsonb` depending on verbatim preservation needs | Decide whether exact text audit or search/indexing matters more |
| High-volume append-only logs/events archived and forwarded | Consider `json`, though benchmark first | Ingestion speed and verbatim retention may outweigh querying |
| Flexible attributes + stable business keys | Hybrid schema: relational columns + `jsonb` | Keeps extensibility without sacrificing core integrity constraints |
| Need `@>`, `?`, and GIN indexing over JSON | `jsonb` | Those operators and indexes are built specifically for JSONB |

### 24.1. Decision Flow

```text
Is the data to store JSON?
          |
          v
Must the exact input JSON text be preserved?
       /               \
     Yes                No
      |                  |
      v                  v
 Prefer json       Need frequent filtering/indexing on many keys?
 or raw bytes        /                  \
                   Yes                   No
                    |                     |
                    v                     v
               Prefer jsonb       JSONB still fits well,
                                  yet evaluate workload
                    |
                    v
Are there stable keys, relationships, money, or status fields?
       /                              \
     Yes                               No
      |                                 |
      v                                 v
Split relational columns/tables;    JSONB document
JSONB for flexible attributes       may suffice
```

This flow is a starting guide, not a substitute for benchmarking, data governance, and legal/audit requirements.

## 25. Common Misconceptions

**1. "json and jsonb differ only in name."** No. They differ in storage, duplicate keys, key ordering, whitespace, comparison operators, indexing, and performance.

**2. "jsonb preserves payloads for verifying original digital signatures."** No. `jsonb` can reorder keys, strip whitespace, and keep only the last value for duplicate keys. When exact bytes matter, store the raw input appropriately.

**3. "json is always wrong because it is slow."** No. When writing and returning payloads verbatim or preserving original formatting is required, `json` can be the right tool.

**4. "jsonb is always smaller than json."** There is no absolute rule; size depends on document contents, encoding overhead, TOAST, and indexes.

**5. "Since jsonb is indexed, every query runs fast."** No. Indexes accelerate specific operators and predicates; the planner still weighs selectivity and cost.

**6. "jsonb_path_ops supports ? just like jsonb_ops."** No. `jsonb_path_ops` does not support the key-existence operators `?`, `?|`, `?&` supported by the default operator class.

**7. "The ? operator searches keys at all nesting levels."** No. It checks keys or string elements **at the top level** of the JSONB value it is applied to.

**8. "@> checks array equality including element order."** No. Array containment differs from array equality; containment does not enforce element order the way equality does.

**9. "-> and ->> return the same type."** No. `->` returns a JSON value; `->>` returns SQL text.

**10. "A missing key and JSON null are the same thing."** No. Use `?`, `jsonb_typeof`, and watch SQL NULL carefully to distinguish them.

**11. "jsonb_set only patches a few bytes in the data file."** Never assume that. PostgreSQL uses MVCC, writing new tuple versions and updating TOAST/WAL/indexes.

**12. "The || operator deep-merges all nested objects."** No. Object concatenation with `||` is a shallow top-level merge, not a recursive deep merge.

**13. "Putting everything in JSONB means you don't need a schema."** No. Core data still needs explicit types, constraints, foreign keys, and access strategies.

**14. "Putting customer_id inside JSON automatically creates a foreign key."** No. PostgreSQL does not infer relational constraints from JSON key names.

**15. "A CHECK using ->> always catches missing keys."** No. SQL NULL/UNKNOWN allows CHECK to pass; explicitly verify key presence and type.

**16. "Changing json to jsonb is just a metadata change."** No. It may rewrite the table, discard verbatim formatting, and fail on unconvertible payloads.

**17. "Every JSONPath query uses a GIN index."** No. PostgreSQL can only use indexes for eligible patterns matching the operator class and extractable predicates.

**18. "JSON arrays are the best model for all one-to-many relationships."** No. When items need keys, FKs, indexes, independent updates, and large aggregations, child tables are usually better.

**19. "SELECT privilege on JSONB only exposes keys shown by the API."** No. SQL privileges on a JSONB column grant read access to the entire document; API masking does not replace database permissions.

**20. "With jsonb, you don't need to think about concurrency."** No. Two clients writing back stale whole documents can lose updates; use database-side updates or optimistic locking.

## 26. Practice Exercises

The following exercises use the `json_lab` schema created earlier. Run them on your practice database; earlier update snippets may have modified rows. If you want outputs to match initial sample data, recreate the test data in a fresh schema or reset rows to the expected state.

### Exercise 1. Which Type Retains Duplicate Keys?

```sql
SELECT
    '{"a":1,"a":2}'::json  AS raw,
    '{"a":1,"a":2}'::jsonb AS parsed;
```

**Question:** which case retains both `a` key–value pairs in text form? Which keeps only one?

**Answer:** `json` preserves the input text containing both pairs; `jsonb` keeps only one `a` key with the final value `2`.

### Exercise 2. Extracting status and Customer Name

Write a query returning `order_id`, `status` as text, and customer name from the nested object.

**Suggested answer:**

```sql
SELECT
    order_id,
    details ->> 'status' AS status,
    details #>> '{customer,name}' AS customer_name
FROM json_lab.orders
ORDER BY order_id;
```

### Exercise 3. Finding Orders with the priority Tag

Write two ways to query this:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @> '{"tags":["priority"]}'::jsonb;

SELECT order_id
FROM json_lab.orders
WHERE (details -> 'tags') ? 'priority';
```

**Question:** which index types pair well with each approach?

**Hint:** containment `@>` can leverage a full-document GIN index with an appropriate operator class. `(details -> 'tags') ? 'priority'` can use a GIN expression index on the `tags` branch; do not assume a full-document GIN index automatically accelerates every differently shaped expression.

### Exercise 4. Difference Between JSON null and a Missing Key

```sql
SELECT
    order_id,
    details ? 'shipping' AS key_exists,
    jsonb_typeof(details -> 'shipping') AS json_type
FROM json_lab.orders
ORDER BY order_id;
```

**Question:** why do orders 1001 and 1002 differ even though `details ->> 'shipping'` returns SQL NULL for both?

**Answer:** order 1001 has the key holding JSON null; order 1002 lacks the `shipping` key entirely. Extracting as text with `->>` produces SQL NULL for both, yet structurally they remain distinct.

### Exercise 5. Filtering Array Elements with JSONPath

Find orders containing an item with `quantity >= 2`:

```sql
SELECT order_id
FROM json_lab.orders
WHERE details @? '$.items[*] ? (@.quantity >= 2)';
```

**Question:** why can't a simple `?` operator on the root document replace this condition directly?

**Answer:** `?` checks top-level keys/string elements and does not traverse into objects inside an array to compare `quantity`.

### Exercise 6. Generating JSON Output for an API

Write a query returning a JSONB array containing `order_id` and `status`, ordered by ID:

```sql
SELECT jsonb_agg(
    jsonb_build_object(
        'order_id', order_id,
        'status', details ->> 'status'
    )
    ORDER BY order_id
) AS orders_json
FROM json_lab.orders;
```

**Question:** if you omit `ORDER BY` inside `jsonb_agg`, does SQL guarantee array element ordering?

**Answer:** No. Always specify ordering explicitly whenever order is part of the expected result.

### Exercise 7. Choosing an Index Strategy

A table has millions of documents; 90% of queries run `details @> '{"status":"paid"}'`, and 10% run `details ? 'shipping'`.

**Task:** compare `jsonb_ops`, `jsonb_path_ops`, and an expression index on `status`.

**Hint:** `jsonb_ops` supports both containment and existence; `jsonb_path_ops` optimizes containment but does not support `?`; an expression B-tree on `details->>'status'` helps if queries use that exact expression. Decide by measuring latency, index size, and write overhead.

### Exercise 8. Deciding How to Store Audit Payloads

A partner requires you to export the exact JSON text received, preserving key order and whitespace. The system also needs fast lookup by `event_id`.

**Approach:** keep raw JSON/text/bytes at the required fidelity; store `event_id` as a relational column, plus a derived `jsonb` representation for searching if genuinely needed. Never keep only a normalized `jsonb` copy when verbatim input text must be reproduced.

### Exercise 9. JSONB or Relational Table?

A system has 10 million orders, each with multiple line items; users frequently filter by `sku`, update individual line quantities, and JOIN product metadata.

**Assessment:** a relational `order_items` table with dedicated keys and indexes on `sku`/`order_id` is usually far better than embedding all items in JSONB and rewriting the entire document on every edit. You can still store a JSONB snapshot if business rules require exporting the original payload.

### Exercise 10. Does Converting json to jsonb Lose Information?

Given payload:

```json
{ "a": 1, "b": 2, "a": 3 }
```

**Question:** after `payload::jsonb`, can you reconstruct the exact input string with its whitespace, key order, and duplicate key?

**Answer:** No. `jsonb` normalizes formatting and retains only the last value for duplicate keys. When preserving the raw input is required, store the original copy appropriately.

## 27. Practical Data Type Selection Workflow for Production Systems

When designing a new column that might store JSON:

1. **Describe the data and lifecycle:** what objects/arrays exist, average/max size, who sends them, and is history needed?
2. **Classify core fields:** do IDs, foreign keys, statuses, monetary amounts, and dates need frequent indexes, constraints, or JOINs?
3. **Determine verbatim retention needs:** must raw JSON text, duplicate keys, or original bytes be preserved?
4. **Catalog queries:** which keys are filtered, containment vs. range, array searches, sorting, aggregations; estimate frequencies.
5. **Choose representation:** `json` for verbatim text retention, `jsonb` for queryable documents, or hybrid/relational schemas for stable structured data.
6. **Design constraints:** `NOT NULL`, `CHECK`, valid enums, nested validation; never expect JSON alone to enforce domain rules.
7. **Design indexes per query:** `jsonb_ops`, `jsonb_path_ops`, expression B-trees, or relational column indexes; avoid redundant overlapping indexes.
8. **Benchmark reads and writes:** use `EXPLAIN (ANALYZE, BUFFERS)` on representative data alongside update latency and WAL/index overhead.
9. **Design concurrency:** prevent whole-document overwrites using `jsonb_set`, state predicates, version numbers, or proper transactions.
10. **Prepare operations:** access privileges, sensitive data handling, backups, migrations, export needs, and handling missing/wrongly typed fields.

If you choose JSONB, be able to explain **why those attributes belong together in one document**, **what the critical query paths are**, and **which business constraints still belong in relational columns/tables**.

## 28. Summary

PostgreSQL's two JSON types serve different priorities:

- **`json`** stores syntax-validated input JSON text. It is useful when preserving whitespace, key order, or duplicate keys from the original text matters, yet lacks JSONB's rich operator/index ecosystem.
- **`jsonb`** stores a parsed binary representation, normalizing objects and resolving duplicate keys by retaining the last value. It excels at repeated querying, containment, existence checks, JSONPath, and GIN indexing.
- **`->`/`->>`/`#>`/`#>>`** extract values; `@>` and `?` test structure/keys; `jsonb_set` and related operators produce updated values.
- **GIN `jsonb_ops`** is flexible across operators; **`jsonb_path_ops`** targets supported containment/JSONPath queries; **B-tree expression indexes** work well for frequently filtered fixed keys.
- **JSON null, SQL NULL, and missing keys differ**, affecting both queries and `CHECK` constraints.
- **JSONB does not replace relational schemas.** Fields with foreign keys, uniqueness, monetary amounts, and core statuses usually belong in strongly typed columns/tables; reserve JSONB for genuinely flexible attributes or snapshots.
- **Updating JSONB is not free** and does not automatically solve concurrency, schema evolution, granular authorization, or raw payload preservation.

A concise selection rule: **if your primary goal is preserving raw input JSON formatting, consider `json` or raw bytes; if you need to search and manipulate JSON contents regularly, prefer `jsonb`; if attributes represent core relational entities or constraints, use relational modeling and keep JSONB only for the truly flexible parts.** Above all, verify your choice with real queries and representative data rather than guessing from type names.
