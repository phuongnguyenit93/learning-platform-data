# Validating JSON Data and Protecting Critical Fields in PostgreSQL

## 1. Why Does Valid JSON Not Mean Valid Data?

PostgreSQL supports two common JSON data types: `json` and `jsonb`. When an application stores flexible structures in a `jsonb` column, the database can validate JSON syntax, query individual keys, build indexes, and update parts of a document. However, **a syntactically valid JSON value does not necessarily satisfy the business contract**.

For example, all four of these documents are valid JSON:

```json
{"external_id":"ORD-1001","status":"NEW","amount_cents":150000}
```

```json
{"external_id":null,"status":"NEW","amount_cents":150000}
```

```json
{"external_id":"ORD-1001","status":123,"amount_cents":-99}
```

```json
{"status":"PAID","amount_cents":"one hundred"}
```

Yet the system may require:

- `external_id` must be a **non-empty string**, immutable after creation.
- `status` may only be one of `NEW`, `PAID`, `CANCELLED`.
- `amount_cents` must be a **non-negative integer** within allowed bounds.
- `items` must be a **non-empty array**, with each element holding a valid product SKU and quantity.
- `external_id` must be **unique per tenant**.
- A `PAID` order must not silently revert to `NEW`.
- Users belonging to tenant A must not update documents belonging to tenant B.

Storing JSON in a column does not exempt the system from enforcing those rules.

> **Core principle:** separate **JSON syntax validation**, **structural validation**, **business invariant enforcement**, and **write access control**. Each layer solves a different class of problem.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish `json` vs. `jsonb`, and JSON `null` vs. SQL `NULL`.
2. Validate required keys, data types, allowed values, and nested structures.
3. Understand why PostgreSQL `CHECK` **accepts UNKNOWN/NULL**, and write constraints that do not let missing fields slip through.
4. Protect identifier fields with `UNIQUE` on expressions or relational columns.
5. Validate JSON integers and monetary amounts without relying on unsafe casts.
6. Validate JSON arrays using SQL, pure validation functions, and JSONPath where appropriate.
7. Design updates with `jsonb_set`, state preconditions, and concurrency control.
8. Block edits to immutable fields or invalid state transitions using triggers when needed.
9. Distinguish the guarantees of `CHECK`, `UNIQUE`, `FOREIGN KEY`, triggers, RLS, and column privileges.
10. Know when to extract critical fields into regular columns instead of keeping everything inside JSON.
11. Use GIN and expression indexes to query JSONB efficiently.
12. Roll out constraints gradually on tables with existing data.
13. Verify invalid and valid cases with hands-on exercises.

---

## 2. JSON, JSONB, and the Responsibility of Each Layer

### 2.1. The json Type

`json` stores syntax-validated JSON text, preserving input formatting characteristics such as whitespace, key order, and duplicate keys in the text.

Example:

```sql
SELECT
    '{"a":1, "a":2}'::json AS as_json;
```

The JSON text can contain two `a` keys in its representation. When an application relies on "last key wins" or "first key wins," duplicate keys can cause subtle mismatches between system components.

### 2.2. The jsonb Type

`jsonb` stores a parsed binary representation with broader operator and index support. It does not preserve input key order, whitespace, or duplicate keys from the raw text; for duplicate keys, only one value (the last occurrence in the input object) is retained.

```sql
SELECT
    '{"a":1, "a":2}'::jsonb AS as_jsonb;
```

Therefore, if **sending duplicate keys itself must be rejected**, storing into `jsonb` and checking afterward cannot recover the collapsed keys. Rejecting duplicate keys must happen **at parse/ingestion time** using an appropriate parser.

### 2.3. What Does JSONB Guarantee and Not Guarantee?

| Check Needed | Is a `jsonb` Column Alone Enough? |
|---|---|
| Input text is valid JSON | Yes, at conversion/cast into `jsonb` |
| Root must be an object | No; JSONB can be array, number, string, boolean, null |
| Key `external_id` is present | No |
| `external_id` is a non-empty string | No |
| `status` belongs to allowed states | No |
| `amount_cents` is non-negative | No |
| `items` is an array of valid objects | No |
| ID is unique per tenant | No |
| `external_id` is immutable after `INSERT` | No |
| Per-tenant access control | No |

Additionally, `jsonb` follows PostgreSQL's own limits and handling for strings/Unicode and numbers. Never describe it merely as "a text column that checks braces."

### 2.4. Defaulting to jsonb When Querying Is Needed

If the system routinely reads keys, filters by status, updates documents, and indexes fields, `jsonb` is the standard choice. If character-for-character original JSON text must be retained, consider `json` or storing raw payloads separately on purpose. Base the choice on audit needs, performance, and data semantics.

## 3. Distinguishing SQL NULL, JSON null, and Missing Keys

This is the foundation for writing accurate constraints.

Consider these values:

```sql
SELECT
    NULL::jsonb                   AS sql_null,
    'null'::jsonb                 AS json_null,
    '{}'::jsonb                   AS empty_object,
    '{"status":null}'::jsonb       AS object_with_json_null;
```

Three states have different meanings:

1. **SQL NULL:** the column value itself is NULL or an expression evaluates to SQL NULL.
2. **JSON null:** the JSON document contains the JSON value `null`.
3. **Missing key:** the object lacks the requested property.

### 3.1. The -> and ->> Operators

```sql
SELECT
    '{"status":null}'::jsonb -> 'status'  AS json_value,
    '{"status":null}'::jsonb ->> 'status' AS text_value,
    '{}'::jsonb -> 'status'              AS missing_json,
    '{}'::jsonb ->> 'status'             AS missing_text;
```

Meaning:

- `->` returns a `jsonb` value; for a key holding JSON null, the result is JSONB `null`.
- `->>` returns text; JSON null is represented as **SQL NULL**.
- A missing key causes extraction operators to return SQL NULL, not an error.

Therefore:

```sql
doc ->> 'status' IS NULL
```

cannot distinguish **missing `status`** from **`status` with JSON null**.

### 3.2. jsonb_typeof

```sql
SELECT
    jsonb_typeof('null'::jsonb)     AS json_null_type,
    jsonb_typeof('"hello"'::jsonb)  AS string_type,
    jsonb_typeof('123'::jsonb)      AS number_type,
    jsonb_typeof('[1,2]'::jsonb)    AS array_type,
    jsonb_typeof('{"a":1}'::jsonb)  AS object_type;
```

The function returns type strings:

```text
null
string
number
array
object
```

And also `boolean`.

Crucial point: `jsonb_typeof('null'::jsonb)` returns **the text string `'null'`**, not SQL NULL. When the argument is SQL NULL or an extracted key is missing, the result is **SQL NULL**.

### 3.3. Checking Key Existence

```sql
SELECT
    '{"status":null}'::jsonb ? 'status' AS key_present,
    '{}'::jsonb ? 'status'             AS key_missing;
```

`?` checks key existence **at the top level of the object** here.

Result:

```text
key_present = true
key_missing = false
```

However, `? 'status'` does not validate content: JSON null, empty string, or the wrong type all count as **key present**.

## 4. Critical Trap: CHECK Accepts UNKNOWN

In PostgreSQL, a `CHECK` constraint is satisfied whenever the expression evaluates to `TRUE` **or NULL/UNKNOWN**. It rejects a row only when the expression evaluates to `FALSE`.

Example of an insufficiently strict constraint:

```sql
CHECK (length(doc ->> 'external_id') > 0)
```

Given the document:

```json
{"status":"NEW"}
```

key `external_id` is missing, so:

```text
doc ->> 'external_id' = SQL NULL
length(NULL)          = SQL NULL
NULL > 0              = UNKNOWN
```

`CHECK` **does not reject the row** simply because the expression evaluated to UNKNOWN.

### 4.1. Use COALESCE When NULL Must Be Invalid

```sql
CHECK (
    COALESCE(
        length(btrim(doc ->> 'external_id')) > 0,
        FALSE
    )
)
```

When the key is missing or JSON null, the inner comparison evaluates to SQL NULL, and `COALESCE(..., FALSE)` yields `FALSE`, causing `CHECK` to reject the row.

### 4.2. Use IS TRUE

Another option:

```sql
CHECK (
    (length(btrim(doc ->> 'external_id')) > 0) IS TRUE
)
```

`IS TRUE` returns `TRUE` **only when** the expression is `TRUE`; for `FALSE` or `UNKNOWN`, it returns `FALSE`.

### 4.3. Combine Existence + Type + Value

```sql
CHECK (
    doc ? 'external_id'
    AND jsonb_typeof(doc -> 'external_id') = 'string'
    AND length(btrim(doc ->> 'external_id')) > 0
)
```

When the key is missing, `doc ? 'external_id'` is `FALSE`. Combining `FALSE AND UNKNOWN` yields `FALSE`. When the key holds JSON null, the type check returns `FALSE`.

To avoid relying on three-valued logic reasoning inside complex expressions, wrap the whole condition with `IS TRUE` or `COALESCE`.

### 4.4. Do Not Check Only Column-Level NOT NULL on JSONB

`doc jsonb NOT NULL` ensures the **entire column** is not SQL NULL; it does **not** ensure every key inside exists or is non-null.

Document protection must operate at both the column level and the attribute level per business rules.

## 5. Building the Lab Schema for JSONB Orders

Run examples in a practice database. Sample data and `UPDATE`/`ALTER` statements are for illustration; never apply them directly to production.

### 5.1. Create the Schema

```sql
CREATE SCHEMA IF NOT EXISTS json313;
```

### 5.2. Standard Order Document

In this lesson, an order has the shape:

```json
{
  "external_id": "ORD-2026-0001",
  "status": "NEW",
  "amount_cents": 250000,
  "currency": "VND",
  "items": [
    {
      "sku": "SKU-A",
      "qty": 2,
      "unit_price_cents": 100000
    },
    {
      "sku": "SKU-B",
      "qty": 1,
      "unit_price_cents": 50000
    }
  ],
  "shipping": {
    "city": "Da Nang",
    "note": null
  },
  "metadata": {
    "source": "web"
  }
}
```

This is a **sample** document, not a complete JSON Schema. Business rules will be translated into constraints and functions throughout the lesson.

### 5.3. Create the Table Storing JSONB

```sql
CREATE TABLE json313.orders (
    order_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    doc jsonb NOT NULL,
    version bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT order_doc_root_object
        CHECK (jsonb_typeof(doc) = 'object')
);
```

At this step, we only have:

- `order_pk` as the physical row identifier.
- `tenant_id` as a dedicated relational column.
- `doc` required to be non-SQL-NULL JSONB with an object root.
- `version` to demonstrate optimistic concurrency.
- `created_at` stored as a standard timestamp type.

Attribute-level constraints will be added incrementally so each step is easy to observe.

### 5.4. Insert a Valid Document

```sql
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{
      "external_id":"ORD-2026-0001",
      "status":"NEW",
      "amount_cents":250000,
      "currency":"VND",
      "items":[
        {"sku":"SKU-A","qty":2,"unit_price_cents":100000},
        {"sku":"SKU-B","qty":1,"unit_price_cents":50000}
      ],
      "shipping":{"city":"Da Nang","note":null},
      "metadata":{"source":"web"}
    }'::jsonb
)
RETURNING order_pk, tenant_id, doc;
```

Run this **once** in the lab fixture so duplicate `external_id` rows are not created before adding the unique index.

### 5.5. Inspect Individual Attributes

```sql
SELECT
    order_pk,
    tenant_id,
    doc ->> 'external_id' AS external_id,
    doc ->> 'status' AS status,
    doc -> 'amount_cents' AS amount_json,
    doc ->> 'amount_cents' AS amount_text,
    doc -> 'items' AS items_json
FROM json313.orders;
```

Note that `doc ->> 'amount_cents'` has **type `text`**, even though the underlying JSON value is a number.

## 6. Validating the Root Object

JSONB allows any root type:

```sql
SELECT
    jsonb_typeof('{}'::jsonb) AS object_type,
    jsonb_typeof('[]'::jsonb) AS array_type,
    jsonb_typeof('42'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS boolean_type,
    jsonb_typeof('"abc"'::jsonb) AS string_type,
    jsonb_typeof('null'::jsonb) AS null_type;
```

When business logic requires an **object**:

```sql
CHECK (jsonb_typeof(doc) = 'object')
```

Because `doc` is declared `NOT NULL`, SQL NULL is already blocked. JSON null also fails the object check.

### 6.1. Why Is Root Validation Necessary?

Without root validation:

```sql
INSERT INTO json313.orders(tenant_id, doc)
VALUES (7, '[]'::jsonb);
```

inserts a row where `doc->>'status'` returns SQL NULL. Application layers assuming `doc` is always an object would encounter an unexpected case.

### 6.2. JSONB Is Not a Full Schema Validation Engine

Root object checking is only the first layer. An object can still lack required keys, have mistyped keys, contain mixed-type arrays, or carry an invalid status.

Define the **data contract** clearly before adding constraints.

## 7. Validating Required Keys

Suppose every order requires:

```text
external_id
status
amount_cents
currency
items
```

For a JSONB object, check multiple top-level keys simultaneously:

```sql
SELECT
    '{
      "external_id":"ORD-1",
      "status":"NEW",
      "amount_cents":0,
      "currency":"VND",
      "items":[]
    }'::jsonb
    ?& ARRAY[
        'external_id',
        'status',
        'amount_cents',
        'currency',
        'items'
    ] AS has_all_keys;
```

`?&` checks that **all** strings in the text array appear as top-level keys of the object.

Add the constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_required_keys
CHECK (
    doc ?& ARRAY[
        'external_id',
        'status',
        'amount_cents',
        'currency',
        'items'
    ]
);
```

### 7.1. Existence Operators

| Operator | Simple Meaning |
|---|---|
| `doc ? 'x'` | Key `x` exists on top-level object, or matching string in array case |
| `doc ?\| ARRAY['a','b']` | **At least one** queried key/value exists |
| `doc ?& ARRAY['a','b']` | **All** queried keys/values exist |

These operators do not recursively search nested objects. For instance, `doc ? 'city'` does not check `shipping.city`.

### 7.2. Key Existence Alone Is Not Enough

A document:

```json
{"external_id":null,"status":null,"amount_cents":null,"currency":null,"items":null}
```

still has **all required key names**. It must be rejected by **type and value** constraints.

## 8. Validating Non-Empty Strings and Formats

Requirements for `external_id`:

- Must exist.
- Must be a JSON string.
- Must not be whitespace-only.
- Must contain only allowed characters.
- Must respect length limits.

Example constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_external_id_valid
CHECK (
    (
        jsonb_typeof(doc -> 'external_id') = 'string'
        AND length(btrim(doc ->> 'external_id'))
            BETWEEN 1 AND 64
        AND (doc ->> 'external_id')
            ~ '^ORD-[A-Za-z0-9-]+$'
    ) IS TRUE
);
```

Invalid examples:

```json
{"external_id":null}
```

```json
{"external_id":""}
```

```json
{"external_id":"    "}
```

```json
{"external_id":123}
```

```json
{"external_id":"INVALID CODE"}
```

### 8.1. Why Check jsonb_typeof Before Using ->>?

`->>` converts JSON values to text. Thus JSON number `123` extracts as string `'123'`.

If you only check a regex or string length without checking the underlying JSON type, you can accidentally accept a number in a field that must be a string.

### 8.2. btrim Does Not Normalize Stored Data

`btrim(doc->>'external_id')` inside `CHECK` only validates. It **does not rewrite** `" ORD-1 "` into `"ORD-1"`.

If you want to trim or lowercase before storing, define an explicit policy:

- Normalize in the application before writing.
- Use a controlled write layer or function.
- Use a normalization trigger if appropriate.

Never assume a validation check modifies the stored JSON value.

### 8.3. Regex Is Not Full ID Validation

A regex only checks character shape. It does not prove an ID exists in an external system, guarantee uniqueness, or prevent post-creation modification.

## 9. Validating Enums and Statuses

The `status` field may only accept:

```text
NEW
PAID
CANCELLED
```

Constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_status_valid
CHECK (
    (
        jsonb_typeof(doc -> 'status') = 'string'
        AND doc ->> 'status' IN ('NEW','PAID','CANCELLED')
    ) IS TRUE
);
```

Pay attention to parentheses around extraction and predicates; in PostgreSQL, write `->>` and `IN` clearly to avoid precedence mistakes.

### 9.1. Why Is IS TRUE Readable Here?

If `status` is missing, `doc->>'status'` returns SQL NULL; `NULL IN (...)` returns UNKNOWN. `(...) IS TRUE` guarantees only `TRUE` passes.

If `status` is JSON null, `jsonb_typeof` returns text `'null'`, failing the type check.

If `status` is a number, the type check also fails even if `->>` text happened to match an allowed string.

### 9.2. Enum Lists Can Evolve

If business statuses change often or have complex transition flows, consider promoting `status` to a dedicated relational column or a workflow/status definition table.

A fixed `CHECK` enum is easy to understand, though adding statuses later requires migrations. Place status where its contract is explicit rather than leaving it in JSON just for "flexibility."

## 10. Integers in JSONB: Do Not Trust Unchecked Casts

JSON has a single **number** type. It does not separate integers and decimals like PostgreSQL's `integer`, `bigint`, and `numeric`.

All of these are JSON numbers:

```json
100
```

```json
100.25
```

```json
-10
```

Yet `amount_cents` requires a **non-negative integer**.

### 10.1. Checking jsonb_typeof = 'number' Alone Is Not Enough

```sql
CHECK (jsonb_typeof(doc -> 'amount_cents') = 'number')
```

still allows `-10`, `100.25`, and values exceeding business limits.

### 10.2. Use CASE to Cast Only When the Type Matches

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_amount_valid
CHECK (
    CASE
        WHEN jsonb_typeof(doc -> 'amount_cents') = 'number'
        THEN
            (doc ->> 'amount_cents')::numeric >= 0
            AND (doc ->> 'amount_cents')::numeric
                <= 1000000000000
            AND (doc ->> 'amount_cents')::numeric
                = trunc((doc ->> 'amount_cents')::numeric)
        ELSE FALSE
    END
);
```

Explanation:

1. If the JSON type is not `number`, return `FALSE`.
2. If it is `number`, cast to `numeric` to check bounds.
3. `value = trunc(value)` accepts only mathematically integer values.
4. Amount upper bound reflects an illustrative business cap.
5. If the key is missing, `WHEN` is not `TRUE`, so `ELSE FALSE` rejects it.

### 10.3. Why Avoid Direct Casting Before Type Checking?

Writing:

```sql
CHECK ((doc ->> 'amount_cents')::integer >= 0)
```

throws parse or overflow errors on JSON strings like `"abc"` or large numbers. Checking type first with a guarded `CASE` makes the evaluation path safe and explicit.

Important: **never rely on SQL `AND` evaluation order** as a guarantee that PostgreSQL always evaluates `jsonb_typeof` before casting. PostgreSQL is allowed to reorder Boolean subexpressions when valid. When a cast could fail, use an explicit `CASE` guard.

### 10.4. Why numeric Instead of integer?

`jsonb` accepts JSON numbers under PostgreSQL's numeric rules. Casting straight to `integer` or `bigint` raises an error if a value lies outside that integer range.

Using `numeric` for bounds checking is clean for this lesson; in production schemas, consider storing monetary amounts in relational `bigint` or `numeric(p,s)` columns with matching bounds checks.

## 11. Validating currency

Order currency may only be `VND` or `USD` in this example:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_currency_valid
CHECK (
    (
        jsonb_typeof(doc -> 'currency') = 'string'
        AND doc ->> 'currency' IN ('VND', 'USD')
    ) IS TRUE
);
```

### 11.1. A Valid Currency Code Does Not Validate Monetary Logic

When accurate financial handling is needed, you must also define:

- Smallest currency unit for each currency.
- Amount bounds per currency.
- When exchange rates are captured.
- Rules for refunds, discounts, and taxes.
- Whether total amount must equal the sum of line items.

A simple `CHECK` on `currency` only restricts allowed codes; it does not solve accounting rules.

### 11.2. Do Not Mix Dynamic Lookup Tables with Hardcoded CHECKs

If allowed currencies, limits, or statuses live in a mutable configuration table, PostgreSQL does not allow an arbitrary `CHECK` to query another table and preserve integrity across changes.

You may need a relational column with a `FOREIGN KEY` to a currencies table, transactional protocols, or a different data model.

## 12. Validating JSON Arrays and Length

The `items` field must:

1. Exist.
2. Have JSON type `array`.
3. Contain at least one element.
4. Stay within the example maximum element limit.

Basic inspection:

```sql
SELECT
    jsonb_typeof('[1,2,3]'::jsonb) AS t,
    jsonb_array_length('[1,2,3]'::jsonb) AS n;
```

However, `jsonb_array_length` expects a JSON array. Calling it on an object or string raises an error.

### 12.1. Guard Length Checks with CASE

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_items_array_valid
CHECK (
    CASE
        WHEN jsonb_typeof(doc -> 'items') = 'array'
        THEN jsonb_array_length(doc -> 'items')
            BETWEEN 1 AND 100
        ELSE FALSE
    END
);
```

For:

```json
{"items":{}}
```

the `ELSE` branch returns `FALSE`.

For:

```json
{"items":[]}
```

the `THEN` branch evaluates `0 BETWEEN 1 AND 100`, returning `FALSE`.

For:

```json
{"items":[null]}
```

the array has length 1, so it passes the **length** check even though its element is invalid. We need the next validation layer.

### 12.2. JSON Arrays Differ from SQL Arrays

PostgreSQL has native SQL arrays like `integer[]` and `text[]`, whereas `items` here is a **JSON array** holding multi-attribute objects.

Do not call `cardinality(items)` as on a SQL array directly on a `jsonb` column; use `jsonb_array_length` for JSON arrays.

## 13. Validating Elements of a JSON Array

Suppose each `items` element must be an object like:

```json
{
  "sku":"SKU-A",
  "qty":2,
  "unit_price_cents":100000
}
```

Requirements:

- Every item is a JSON object.
- `sku` is a non-empty string.
- `qty` is a positive integer number.
- `unit_price_cents` is a non-negative integer number.
- Every item is valid, **not just one item**.

### 13.1. Expanding Elements with jsonb_array_elements

```sql
SELECT
    e.ordinality,
    e.item ->> 'sku' AS sku,
    e.item -> 'qty' AS qty_json
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items')
    WITH ORDINALITY AS e(item, ordinality)
WHERE o.tenant_id = 7
  AND o.doc ->> 'external_id' = 'ORD-2026-0001'
ORDER BY e.ordinality;
```

`WITH ORDINALITY` adds 1-based element positions. Never rely on unordered row output as an ordering guarantee for an API.

### 13.2. Finding Invalid Items for Investigation

The query below **assumes `items` is already verified to be an array** by the schema. It locates items with basic type errors:

```sql
SELECT
    o.order_pk,
    e.ordinality,
    e.item
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items')
    WITH ORDINALITY AS e(item, ordinality)
WHERE
    jsonb_typeof(e.item) IS DISTINCT FROM 'object'
    OR jsonb_typeof(e.item -> 'sku') IS DISTINCT FROM 'string'
    OR nullif(btrim(e.item ->> 'sku'), '') IS NULL
    OR jsonb_typeof(e.item -> 'qty') IS DISTINCT FROM 'number'
    OR jsonb_typeof(e.item -> 'unit_price_cents')
       IS DISTINCT FROM 'number';
```

`IS DISTINCT FROM` yields a clean boolean even for SQL NULL: if `sku` is missing, its type is SQL NULL, and `NULL IS DISTINCT FROM 'string'` is `TRUE`.

This checks basic types and strings; it does not yet check positive integer `qty` and non-negative integer price. Next we encapsulate the full logic.

## 14. Writing a Pure SQL Validation Function for Nested Arrays

A standard `CHECK` constraint cannot directly embed an arbitrary subquery scanning each element. You can define a **pure SQL function** to validate the JSON array and call that function inside `CHECK`.

Example:

```sql
CREATE OR REPLACE FUNCTION json313.valid_items(p_items jsonb)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT CASE
        WHEN jsonb_typeof(p_items) <> 'array'
        THEN FALSE

        WHEN jsonb_array_length(p_items) = 0
        THEN FALSE

        ELSE NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(p_items) AS e(item)
            WHERE
                jsonb_typeof(e.item) IS DISTINCT FROM 'object'

                OR jsonb_typeof(e.item -> 'sku')
                    IS DISTINCT FROM 'string'

                OR nullif(btrim(e.item ->> 'sku'), '')
                    IS NULL

                OR jsonb_typeof(e.item -> 'qty')
                    IS DISTINCT FROM 'number'

                OR NOT (
                    CASE
                        WHEN jsonb_typeof(e.item -> 'qty') = 'number'
                        THEN
                            (e.item ->> 'qty')::numeric > 0
                            AND
                            (e.item ->> 'qty')::numeric =
                                trunc((e.item ->> 'qty')::numeric)
                        ELSE FALSE
                    END
                )

                OR jsonb_typeof(e.item -> 'unit_price_cents')
                    IS DISTINCT FROM 'number'

                OR NOT (
                    CASE
                        WHEN jsonb_typeof(
                            e.item -> 'unit_price_cents'
                        ) = 'number'
                        THEN
                            (e.item ->> 'unit_price_cents')::numeric >= 0
                            AND
                            (e.item ->> 'unit_price_cents')::numeric =
                                trunc(
                                  (e.item ->> 'unit_price_cents')::numeric
                                )
                        ELSE FALSE
                    END
                )
        )
    END;
$$;
```

### 14.1. Why Does NOT EXISTS Fit "Every Item Is Valid"?

Rule:

```text
Every element is valid
    <=>
No invalid element exists
```

The function uses `NOT EXISTS (SELECT ... WHERE invalid_condition)`.

If you wrote only:

```sql
EXISTS (
    SELECT 1 FROM jsonb_array_elements(items) ...
    WHERE valid_item_condition
)
```

an array with one valid item and ten invalid items would pass; that tests **at least one valid item**, not **all items valid**.

### 14.2. Why IMMUTABLE and STRICT?

- `IMMUTABLE`: the result depends solely on the JSON input parameter, reading no other tables or system clock.
- `STRICT`: given a SQL NULL argument, it returns SQL NULL without executing the body.

These properties fit pure validation functions like this example. **Mark a function `IMMUTABLE` only if it is genuinely immutable.** Never falsely mark a function that reads a configuration table or `now()` as `IMMUTABLE` just to sneak it into a `CHECK` or index.

### 14.3. Using the Function in CHECK

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_items_elements_valid
CHECK (
    COALESCE(
        json313.valid_items(doc -> 'items'),
        FALSE
    )
);
```

Combined with the earlier array constraint, missing `items`, JSON null, objects, empty arrays, and malformed items are all rejected.

### 14.4. Be Careful When Modifying the Function Definition

PostgreSQL assumes functions referenced in `CHECK` constraints behave immutably for identical inputs. If you later change the logic of a validation function used in a `CHECK`, **existing rows are not automatically re-checked**.

A migration changing validation rules must:

- Identify affected historical rows.
- Audit/reconcile data against the new logic.
- Add or validate an updated constraint properly.
- Follow backup/restore and dependency procedures.
- Never run `CREATE OR REPLACE FUNCTION` alone and declare all historical rows valid.

## 15. Consistency Between amount and items

Suppose `amount_cents` must equal:

```text
SUM(item.qty * item.unit_price_cents)
```

This is a **cross-attribute invariant within the same JSON document**, not just a type check.

Example:

```json
{
  "amount_cents": 250000,
  "items": [
    {"sku":"SKU-A","qty":2,"unit_price_cents":100000},
    {"sku":"SKU-B","qty":1,"unit_price_cents":50000}
  ]
}
```

Total = 250000, valid if business rules exclude separate shipping, fees, taxes, or discounts outside the item lines.

### 15.1. Computing the Sum in SQL to Inspect

```sql
SELECT
    o.order_pk,
    o.doc ->> 'external_id' AS external_id,
    SUM(
        (e.item ->> 'qty')::numeric
        *
        (e.item ->> 'unit_price_cents')::numeric
    ) AS calculated_items_total
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.doc -> 'items') AS e(item)
WHERE json313.valid_items(o.doc -> 'items') IS TRUE
GROUP BY o.order_pk, o.doc ->> 'external_id'
ORDER BY o.order_pk;
```

This illustrative query assumes items are validated before casting. On unvalidated source data, avoid casting unverified strings.

### 15.2. Should You CHECK That Total Equals Item Sum?

Only when business rules **strictly enforce that identity**. If shipping, vouchers, taxes, rounding, or partial orders exist, a rigid `CHECK` rejects valid orders.

When needed, write a pure validator function over validated JSON, or normalize line items into a separate relational table and design appropriate invariants.

Do not promote an illustrative formula into a universal accounting rule.

## 16. JSONPath for Checking Paths and Conditions

PostgreSQL supports SQL/JSON paths via the `jsonpath` type and functions/operators such as:

- `jsonb_path_exists`.
- `jsonb_path_query`.
- `jsonb_path_query_first`.
- `@?` and `@@` with their respective semantics.

Example finding orders with at least one `SKU-A` item:

```sql
SELECT order_pk, doc ->> 'external_id' AS external_id
FROM json313.orders
WHERE doc @? '$.items[*] ? (@.sku == "SKU-A")';
```

Meaning: **at least one path** in the JSON matches the `SKU-A` filter.

### 16.1. Distinguish Existence from Universal Checks

The expression:

```sql
doc @? '$.items[*] ? (@.qty >= 1)'
```

does not prove **every item** has `qty >= 1`. It only checks whether **one item** satisfies it.

If an array has one item with `qty = 2` and another with `qty = -10`, the expression evaluates to `TRUE` even though the document is invalid overall.

For "all elements valid," negate existence of a bad item or use a full validation function as shown earlier.

### 16.2. Watch lax and strict Modes

SQL/JSON paths have evaluation rules including `lax`/`strict` modes and structural mismatch handling. Never assume a JSONPath automatically enforces strict types like JSON Schema.

Clarify:

- What happens on missing paths?
- Does auto-unwrapping of arrays occur in certain cases?
- How are cross-type comparisons handled?
- Which errors are suppressed by the operator or function?

For mandatory identifier and financial fields, explicit type `CHECK`s or relational columns are far easier to verify than compact JSONPath expressions.

## 17. Nested Objects: Protecting shipping.city

The `shipping` field can be a nested object:

```json
{
  "shipping": {
    "city": "Da Nang",
    "note": null
  }
}
```

Extracting data:

```sql
SELECT
    doc #>  '{shipping,city}' AS city_json,
    doc #>> '{shipping,city}' AS city_text
FROM json313.orders;
```

- `#>` traverses a JSON path and returns `jsonb`.
- `#>>` traverses a JSON path and returns `text`.
- If any path segment is missing, the result is SQL NULL.

### 17.1. Constraint for a Mandatory Nested Field

If business rules require every order to have a non-empty string `shipping.city`:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_shipping_city_valid
CHECK (
    (
        jsonb_typeof(doc -> 'shipping') = 'object'
        AND jsonb_typeof(doc #> '{shipping,city}') = 'string'
        AND length(btrim(doc #>> '{shipping,city}')) > 0
    ) IS TRUE
);
```

In the fixture, `city = Da Nang` passes.

### 17.2. What If shipping Is Optional?

Do not add a mandatory constraint if some orders are digital goods without shipping addresses. Instead, define a conditional predicate:

```text
If physical shipping is required:
    shipping.city must be present.
If digital delivery:
    shipping may be absent.
```

Conditional rules can be checked with `CASE` or a validation function, grounded in the actual business model rather than a single sample JSON shape.

## 18. Required Keys vs. Disallowed Extra Keys

A system can choose between two policies.

**Open policy:**

```text
Critical keys must be valid,
while arbitrary metadata is allowed.
```

**Closed policy:**

```text
Only listed keys may appear.
```

### 18.1. Why Not Always Forbid Extra Keys?

JSONB is often chosen so metadata can evolve across versions, partners, data sources, or feature flags. Blocking every unknown key reduces schema flexibility and can break rolling deployments across mismatched app versions.

### 18.2. When Unknown Keys Must Be Rejected

List top-level keys with `jsonb_object_keys` and verify none fall outside the allowlist.

Audit query pattern:

```sql
SELECT
    o.order_pk,
    k.key
FROM json313.orders AS o
CROSS JOIN LATERAL
    jsonb_object_keys(o.doc) AS k(key)
WHERE k.key NOT IN (
    'external_id',
    'status',
    'amount_cents',
    'currency',
    'items',
    'shipping',
    'metadata'
);
```

To enforce in a `CHECK`, wrap the validation in a pure `IMMUTABLE` SQL function or use an appropriate JSON Schema validation mechanism.

**Never** write a naive `CHECK` on a single top-level key list and forget about nested keys or schema versions.

## 19. Uniqueness per Tenant: UNIQUE on a JSON Expression

Each tenant needs unique `external_id` values, while two different tenants may reuse the same code.

Rule:

```text
UNIQUE (tenant_id, external_id)
```

In the lab table, `external_id` lives inside JSON, so create a **unique expression index**:

```sql
CREATE UNIQUE INDEX uq_json313_orders_tenant_external
ON json313.orders(
    tenant_id,
    (doc ->> 'external_id')
);
```

This index enforces uniqueness on the text extracted from JSON.

### 19.1. Why Is a Mandatory external_id CHECK Still Needed?

In standard unique indexes, SQL NULLs have special semantics: multiple rows with NULL values are permitted unless configured otherwise.

If `external_id` is missing or JSON null, `doc->>'external_id'` evaluates to SQL NULL. Never rely on a `UNIQUE` index as an excuse to skip required-field checks.

Proper combination:

- `CHECK` requiring `external_id` to exist, be a string, and be non-empty.
- `UNIQUE (tenant_id, external_id expression)`.

### 19.2. Testing Duplicate Codes Within the Same Tenant

Once the index exists and tenant 7's `ORD-2026-0001` is present:

```sql
-- Run separately to observe the expected unique_violation:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{
      "external_id":"ORD-2026-0001",
      "status":"NEW",
      "amount_cents":0,
      "currency":"VND",
      "items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],
      "shipping":{"city":"Hue"}
    }'::jsonb
);
```

The statement is rejected because `(7, 'ORD-2026-0001')` already exists.

### 19.3. Two Different Tenants

A row with `tenant_id = 8` and the same `external_id` succeeds because the composite key differs.

This fits when uniqueness is **per tenant**. If `external_id` must be globally unique across all tenants, scope the index accordingly.

### 19.4. Why Not Just Run SELECT NOT EXISTS Before INSERT?

Two concurrent transactions can both read "no such `external_id` exists" and then both `INSERT`. A unique index enforces uniqueness atomically under concurrency; application pre-checks **cannot replace** it.

## 20. Using Generated Columns for Important JSON Attributes

Another design option exposes an extracted value as a dedicated column.

Example using a generated column:

```sql
ALTER TABLE json313.orders
ADD COLUMN external_id text
GENERATED ALWAYS AS (doc ->> 'external_id') STORED;
```

The column is computed from `doc`; applications do not write to `external_id` directly like a normal column.

It can be indexed:

```sql
CREATE INDEX idx_json313_orders_external_id
ON json313.orders(external_id);
```

### 20.1. Expression Index vs. Generated Column

| Criterion | Expression Index | Generated Column |
|---|---|---|
| Querying by attribute | Uses matching expression | Uses explicit column name |
| Column name in SQL/ORM | Repeats expression | Has its own column name |
| Input validation | Still needs `CHECK` | Still needs `CHECK` if type/value is unguarded |
| Storage footprint | Expression value in index | Generated value stored in row, plus index if created |
| Computation rules | Expression definition | Generated expression obeying PostgreSQL restrictions |
| Schema migration | Create/drop index | Alters table columns and storage |

You do not need to create **both an expression unique index and a generated unique index** for the same key; choose one approach per your needs and avoid redundant indexes.

### 20.2. Should external_id Be a Regular Column?

If `external_id` is a **critical business key**, consider placing it in a standard relational column:

```sql
external_id text NOT NULL
```

with a standard `UNIQUE (tenant_id, external_id)`. JSON still holds flexible metadata.

Advantages:

- Clear foreign keys and referential relationships.
- Easy to design queries, indexes, and statistics.
- Value-change rules are simpler to govern.
- Clear typed contracts for ORMs and APIs.

Do not cram every critical key into JSONB just to keep the table column count down.

## 21. Protecting Immutable Fields: CHECK Does Not Compare OLD vs. NEW

A `CHECK` constraint inspects only **the new row state** and confirms values are valid.

For example:

```sql
CHECK (
    (doc ->> 'external_id') ~ '^ORD-[A-Za-z0-9-]+$'
)
```

does not prevent:

```text
Before: external_id = ORD-1001
After:  external_id = ORD-9999
```

because both values match the format.

If **an order code must never change after creation**, you must compare **OLD vs. NEW** or enforce immutability via write permissions/API design.

### 21.1. BEFORE UPDATE Trigger Protecting Identity

Example:

```sql
CREATE OR REPLACE FUNCTION json313.guard_order_fields()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN

        IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
            RAISE EXCEPTION
                'tenant_id cannot be changed'
                USING ERRCODE = '23514';
        END IF;

        IF (NEW.doc -> 'external_id')
            IS DISTINCT FROM (OLD.doc -> 'external_id') THEN
            RAISE EXCEPTION
                'external_id cannot be changed'
                USING ERRCODE = '23514';
        END IF;

        IF (OLD.doc ->> 'status') = 'PAID'
           AND (NEW.doc ->> 'status') = 'NEW' THEN
            RAISE EXCEPTION
                'PAID order cannot return to NEW'
                USING ERRCODE = '23514';
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_json313_guard_order_fields
BEFORE UPDATE ON json313.orders
FOR EACH ROW
EXECUTE FUNCTION json313.guard_order_fields();
```

### 21.2. What Scope Does a Trigger Have?

This trigger guards row updates on `json313.orders` when enabled.

It does not automatically:

- Verify the caller belongs to that tenant.
- Enforce the entire business workflow when only blocking `PAID -> NEW`.
- Block `DELETE` without dedicated rules, triggers, or policies.
- Roll back external side effects outside the database.
- Keep external systems synchronized with PostgreSQL.

To protect state properly, define the **complete state transition diagram** and validate every permitted edge.

### 21.3. Why Is IS DISTINCT FROM Appropriate?

SQL has `NULL`. Comparing `NEW.doc->'external_id' <> OLD.doc->'external_id'` evaluates to `UNKNOWN` if either side is missing.

`IS DISTINCT FROM` handles all cases unambiguously:

- Equal values → `FALSE`.
- Different values → `TRUE`.
- One side SQL NULL, the other non-NULL → `TRUE`.
- Both SQL NULL → `FALSE`.

Other constraints must still ensure `external_id` is mandatory; the trigger only detects changes.

## 22. Business Status and State Machines

The constraint:

```text
status in {NEW, PAID, CANCELLED}
```

only validates **the current value**.

Actual state transition rules might look like:

```text
NEW ------> PAID
  \          |
   \         +------> REFUNDED
    \
     +-----> CANCELLED
```

Disallowing:

```text
PAID -> NEW
CANCELLED -> PAID
REFUNDED -> NEW
```

### 22.1. A Valid Value Does Not Mean a Valid Transition

Updating `NEW` to `PAID` and updating `PAID` to `NEW` both leave `status` inside the enum set. Enum `CHECK`s **have no memory of history**.

When a state machine must be enforced in the database:

- Use an OLD/NEW trigger.
- Or enforce transitions through a single controlled write API/service with appropriate privileges.
- For complex lifecycles, consider a dedicated `status` column, transition lookup table, audit log, outbox, and workflow engine.

### 22.2. Do Not Mistake One Narrow Rule for a Complete State Machine

The earlier trigger only blocks **`PAID → NEW`**, not every invalid transition. Never ship it to production claiming the entire payment lifecycle is protected.

### 22.3. Auditing Matters

When `status` changes, you may need to record:

```text
order_id
old_status
new_status
actor
changed_at
request_id
```

Use an audit event table and transactional outbox so changes are never lost on commit. Avoid logging unnecessary sensitive fields.

## 23. jsonb_set: Updating a Single Path in JSONB

PostgreSQL provides `jsonb_set` to construct a new JSONB document with one path replaced.

General syntax:

```sql
jsonb_set(target_jsonb, path_text_array, new_jsonb_value, create_if_missing)
```

Example transitioning status to `PAID`:

```sql
UPDATE json313.orders
SET
    doc = jsonb_set(
        doc,
        '{status}',
        '"PAID"'::jsonb,
        false
    ),
    version = version + 1
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001'
  AND doc ->> 'status' = 'NEW'
RETURNING
    order_pk,
    doc ->> 'status' AS new_status,
    version;
```

### 23.1. Why Is status = 'NEW' Placed in WHERE?

This implements a **conditional state transition**:

```text
Update only if the current status is NEW.
```

Two concurrent requests updating the same row serialize on the row lock. Under `READ COMMITTED`, PostgreSQL re-evaluates `WHERE` against the latest committed row version once the competing transaction commits. The second request updates 0 rows if `status` is no longer `NEW`.

The application must inspect **the rows returned by `RETURNING`**:

- 1 row: the transition succeeded in this transaction.
- 0 rows: row not found, wrong tenant, or current status is ineligible; respond per business rules.

### 23.2. jsonb_set Does Not Patch Individual Bytes In Place

An `UPDATE` setting `doc = jsonb_set(...)` produces a **new JSONB value** at the SQL/MVCC level; there is no zero-cost guarantee of writing only a few bytes inside a large document.

For large, frequently updated documents, separating hot attributes like `status`, counters, and timestamps into dedicated columns reduces write, WAL, and index overhead.

### 23.3. Watch Out for Missing Paths

`create_if_missing = false` avoids creating the final key if missing. Still, missing intermediate steps, non-object/array types, and array indexes follow specific rules.

Therefore, never treat `jsonb_set` as a schema validator. Constraints still validate the post-update row.

## 24. Preventing Lost Updates When Clients Resubmit Whole Documents

A classic bug:

1. A reads `doc` version v1.
2. B reads the same `doc` v1.
3. A updates `shipping.city` and sends back **the entire `doc`**.
4. B updates `metadata.source` on its v1 copy and sends back **the entire `doc`**.
5. B commits second, wiping out A's shipping update.

If the application runs:

```sql
UPDATE json313.orders
SET doc = $1::jsonb
WHERE order_pk = $2;
```

with a document built from an old snapshot, the later transaction overwrites earlier changes even though the requests targeted different fields.

### 24.1. Updating Specific Paths in the Database

For targeted edits, use:

```sql
UPDATE json313.orders
SET doc = jsonb_set(
    doc,
    '{metadata,source}',
    '"mobile"'::jsonb,
    true
)
WHERE order_pk = 1;
```

This `UPDATE` uses the current row's `doc` value inside PostgreSQL instead of a stale JSON copy from the client.

You must still verify:

- Is the caller allowed to modify this path?
- Which tenant owns the record?
- May that field be edited in the current state?
- Are version checks or idempotency required?
- Do triggers and constraints validate the post-update document?

### 24.2. Optimistic Locking with Version

With each request, the client submits the version it read:

```sql
UPDATE json313.orders
SET
    doc = jsonb_set(
        doc,
        '{metadata,source}',
        '"mobile"'::jsonb,
        true
    ),
    version = version + 1
WHERE order_pk = 1
  AND tenant_id = 7
  AND version = 0
RETURNING order_pk, version;
```

If another transaction already incremented `version`, this `UPDATE` no longer matches `version = 0`; the application receives 0 rows and reloads or retries per business logic.

### 24.3. Retry the Whole Decision When Needed

If a `SERIALIZABLE` transaction aborts with SQLSTATE `40001` or deadlocks with `40P01`, roll back and retry **the entire transaction** when safe. Never replay an old decision built from a stale document without re-reading.

## 25. jsonb_set_lax and Handling SQL NULL

A subtle point: a new value passed to JSON may be **SQL NULL** or JSONB `null`.

```sql
-- JSON null:
SELECT jsonb_set(
    '{"x":1}'::jsonb,
    '{x}',
    'null'::jsonb
);
```

This sets property `x` to **JSON null**; it does not delete the key.

In PostgreSQL versions supporting it, `jsonb_set_lax` lets you choose what happens when `new_value` is **SQL NULL**—such as converting to JSON null, deleting the key, returning the target unchanged, or raising an error.

### 25.1. Do Not Confuse Setting null with Deleting a Key

```text
{"x":null}
```

and:

```text
{}
```

differ under `? 'x'`, even though `->> 'x'` returns SQL NULL for both.

If `x` is mandatory, both must be rejected: one for wrong type / JSON null, the other for missing key.

### 25.2. Do Not Use NULL to "Bypass Validation"

Sending JSON null for `amount` hoping `CHECK` evaluates to `UNKNOWN` and lets it pass is a sign of a broken constraint design. The rules in Sections 4 and 10 prevent that loophole.

## 26. Deleting JSONB Keys and Protecting Required Fields

The `-` operator deletes a key at the object level:

```sql
SELECT
    '{"external_id":"ORD-1","note":"hello"}'::jsonb
    - 'note';
```

Expected output keeps only `external_id`.

Deleting `external_id`:

```sql
SELECT
    '{"external_id":"ORD-1","note":"hello"}'::jsonb
    - 'external_id';
```

strips the identifier key from the document.

### 26.1. Constraints Must Block This Write Path

When `external_id` is mandatory, `CHECK` constraints `order_doc_external_id_valid` and `order_doc_required_keys` reject any `UPDATE` that removes the key.

An OLD/NEW trigger also blocks changing the identifier. This is **defense in depth**:

- `CHECK` rejects invalid final state.
- Triggers block identity changes.
- Write privileges and APIs restrict who may execute updates.

### 26.2. Why Not Trust Only the Frontend?

The frontend can be bypassed by batch jobs, DBA scripts, migration scripts, legacy APIs, or direct writes. When a field is a critical invariant, database constraints protect against writes outside the normal service path.

Note, however, that accounts privileged enough to alter schemas, disable triggers, or run as superuser can modify protections. Never treat constraints as a barrier against top-level administrative accounts.

## 27. Column Privileges Do Not Equal Per-Key JSON Privileges

PostgreSQL supports table/column privileges and Row Level Security at the row level. Yet a column:

```text
doc jsonb
```

is still **a single column** even if it contains dozens of attributes.

### 27.1. You Cannot Simply GRANT UPDATE on One JSON Path

A policy like:

```text
Role A may update doc.metadata
but may not update doc.external_id
```

cannot be expressed via standard column-level `UPDATE` privileges on a single **`doc` column**. Column privileges do not treat `metadata` and `external_id` as separate columns.

### 27.2. Control Mechanisms

- Extract critical fields into separate relational columns.
- Restrict applications to calling controlled write functions that validate allowed paths.
- Use OLD/NEW triggers to reject disallowed changes.
- Apply least-privilege roles and withhold direct `UPDATE` on the JSONB column from untrusted roles.
- Use RLS to scope which **rows** a role can read or modify.
- Audit sensitive modifications.

### 27.3. Column Privilege Example Is a Pattern, Not Copy-Paste Production Code

```sql
-- Assumes app_role was created and granted privileges by a DBA:
REVOKE UPDATE (doc) ON json313.orders FROM app_role;
```

Note: if the role still holds table-level `UPDATE` or inherits it from another role, revoking at the column level does not stop it from updating `doc`. Audit all inherited roles and grants.

Never create high-privilege accounts or alter production grants just to run a learning example.

## 28. RLS Protects Tenants, Not JSON Validation

In multi-tenant systems, `tenant_id` should be governed reliably, usually as a relational column outside JSON.

### 28.1. Why Should tenant_id Not Live Only Inside doc?

If you only have:

```json
{"tenant_id":7,"external_id":"ORD-1"}
```

every authorization check, index, constraint, and join involving tenant has to extract from JSON, risking mistyped values, missing keys, or inconsistent extraction.

A column:

```sql
tenant_id integer NOT NULL
```

makes composite uniqueness, foreign keys, filtering, and RLS clean and reliable.

### 28.2. RLS Protects Rows

RLS restricts which rows a role may `SELECT`, `UPDATE`, `DELETE`, or `INSERT` using policy expressions.

However, RLS does **not** verify:

- Whether `external_id` is a non-empty string.
- Whether `amount_cents` is non-negative.
- Whether `items` holds valid objects.
- Whether `status` illegally transitioned from `PAID` to `NEW`.

RLS, `CHECK`, `UNIQUE`, and triggers serve distinct roles and must work together.

### 28.3. Never Take tenant_id from Untrusted Parameters

A query:

```sql
UPDATE json313.orders
SET doc = ...
WHERE tenant_id = 7;
```

is safe only when tenant 7 comes from verified authentication and authorization context. Clients can tamper with a `7` or `8` in a payload; applications must bind tenant scope to authenticated identity, not raw JSON input.

## 29. JSON Schema: PostgreSQL Core and Extensions

JSON Schema describes JSON contracts using concepts like:

- `object` / `array` / `string` / `number` / `integer` types.
- Required properties.
- Enums.
- Regex patterns.
- Min/max bounds.
- Nested object structures.
- Array item rules.
- Combined conditionals.

Illustrative partial JSON Schema:

```json
{
  "type": "object",
  "required": [
    "external_id",
    "status",
    "amount_cents",
    "currency",
    "items"
  ],
  "properties": {
    "external_id": {
      "type": "string",
      "minLength": 1
    },
    "status": {
      "enum": ["NEW", "PAID", "CANCELLED"]
    },
    "amount_cents": {
      "type": "integer",
      "minimum": 0
    },
    "items": {
      "type": "array",
      "minItems": 1
    }
  }
}
```

**This is only a partial illustration**; it does not cover every item rule, uniqueness, state transitions, or business logic.

### 29.1. Does PostgreSQL Have a Built-In JSON Schema Validator?

Having `jsonb` and SQL/JSON functions **does not mean PostgreSQL core ships a full standard JSON Schema validator** for every column.

Third-party extensions and libraries exist (such as `pg_jsonschema`), but:

- Do not assume an extension is installed.
- Check installation permissions.
- Verify supported versions and JSON Schema dialects.
- Benchmark validation performance.
- Manage migrations when schemas evolve.

Never copy an arbitrary extension function call into production without verifying its API on your target system.

### 29.2. When Are Manual CHECKs Enough?

When only a few stable fields need enforcement, explicit `CHECK`s are simple to operate and debug.

When JSON has deep nested structures, dozens of optional rules, and multiple schema versions, an integrated JSON Schema validator may be more practical.

Either way, **cross-row business invariants** such as unique `external_id` still need `UNIQUE` and transactions; JSON Schema validates only one document at a time.

## 30. Versioning JSON Structures

A document can include `schema_version`:

```json
{
  "schema_version": 2,
  "external_id": "ORD-2026-0001",
  "status": "NEW"
}
```

This distinguishes data contracts across versions.

### 30.1. Two Common Strategies

**Upgrade all historical documents:**

- Migration transforms prior-version documents.
- Constraints then enforce the new schema.
- Fewer runtime branches once upgraded.

**Support multiple versions in parallel:**

- Validators dispatch rules by `schema_version`.
- Applications read both old and new formats.
- Migrations roll out gradually.
- Every supported version must be tested thoroughly.

### 30.2. Do Not Check Only Key Presence for Version

If `schema_version` is JSON string `"2"` in one document and JSON number `2` in another, decide explicitly whether both are valid.

For example, requiring an integer number:

```sql
CHECK (
    CASE
      WHEN jsonb_typeof(doc -> 'schema_version') = 'number'
      THEN (doc ->> 'schema_version')::numeric
           = trunc((doc ->> 'schema_version')::numeric)
      ELSE FALSE
    END
)
```

This validates type/integer-ness only; it does not yet restrict the allowed version set `1, 2, ...` or dispatch version-specific rules.

### 30.3. Avoid Accidental Data Loss During Schema Changes

When auditing matters, before migrating JSONB from v1 to v2 document:

- Which fields are renamed.
- Which fields are removed.
- What default values are assigned.
- How NULLs and missing keys are handled.
- Whether raw originals or migration events must be retained.

## 31. Adding Constraints to Tables with Existing Data

On populated tables, adding a `CHECK` scans existing rows and fails if legacy rows violate it.

A practical technique is **adding the constraint as `NOT VALID`**, auditing historical rows, and validating afterward.

Example new constraint:

```sql
ALTER TABLE json313.orders
ADD CONSTRAINT order_doc_metadata_object
CHECK (
    CASE
        WHEN doc ? 'metadata'
        THEN jsonb_typeof(doc -> 'metadata') = 'object'
        ELSE TRUE
    END
)
NOT VALID;
```

### 31.1. What Does NOT VALID Mean?

For supported `CHECK`/FK constraints:

- PostgreSQL **skips scanning all existing rows during `ADD`**.
- New `INSERT`s and `UPDATE`s must still satisfy the constraint.
- The constraint is marked as not yet validated against historical data.

It is **not** a way to disable validation on new writes.

### 31.2. Finding Historical Violations

```sql
SELECT order_pk, tenant_id, doc -> 'metadata' AS metadata_json
FROM json313.orders
WHERE doc ? 'metadata'
  AND jsonb_typeof(doc -> 'metadata') IS DISTINCT FROM 'object';
```

Fix genuinely bad rows per business rules. Never blindly overwrite mistyped `metadata` with an empty object if consumers depend on the old data.

### 31.3. VALIDATE CONSTRAINT

Once historical data is cleaned:

```sql
ALTER TABLE json313.orders
VALIDATE CONSTRAINT order_doc_metadata_object;
```

PostgreSQL scans existing rows and marks the constraint valid if all pass.

### 31.4. Do All Constraints Support NOT VALID Identically?

No. `UNIQUE`, `PRIMARY KEY`, `NOT NULL`, and other DDL constructs have their own lock and deployment mechanics. Never assume `NOT VALID` applies to every constraint type.

On very large tables, plan lock impact, scan time, and transactions per your PostgreSQL version and production requirements.

## 32. Verifying Constraints and Index Definitions

Inspect declared `CHECK`/PK/FK constraints:

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'json313.orders'::regclass
ORDER BY conname;
```

Common `contype` codes:

- `c`: `CHECK`.
- `p`: `PRIMARY KEY`.
- `u`: `UNIQUE` constraint.
- `f`: `FOREIGN KEY`.

A unique expression index such as `uq_json313_orders_tenant_external` **does not necessarily appear as a table-level `UNIQUE` constraint in `pg_constraint`** because it was created directly as an index. Also inspect:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'json313'
  AND tablename = 'orders'
ORDER BY indexname;
```

### 32.1. Inspecting Index Validity

```sql
SELECT
    c.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS c ON c.oid = i.indexrelid
WHERE i.indrelid = 'json313.orders'::regclass
ORDER BY c.relname;
```

Never claim an index protects data if it is invalid or left unfinished from a failed migration.

## 33. Finding Suspect Rows in Existing Data

In a legacy table containing loosely constrained JSONB, run audit queries.

### 33.1. Missing or Mistyped Fields

```sql
SELECT
    order_pk,
    tenant_id,
    doc
FROM json313.orders
WHERE
    jsonb_typeof(doc) IS DISTINCT FROM 'object'
    OR jsonb_typeof(doc -> 'external_id')
       IS DISTINCT FROM 'string'
    OR jsonb_typeof(doc -> 'status')
       IS DISTINCT FROM 'string'
    OR jsonb_typeof(doc -> 'amount_cents')
       IS DISTINCT FROM 'number';
```

Once constraints are added and validated, this query ideally returns zero rows. On legacy data, it surfaces rows needing repair.

### 33.2. Out-of-Set Statuses

```sql
SELECT order_pk, doc -> 'status' AS status_json
FROM json313.orders
WHERE (doc ->> 'status') NOT IN ('NEW','PAID','CANCELLED')
   OR (doc ->> 'status') IS NULL;
```

Note that `NOT IN` does not match SQL NULL, so add `IS NULL` explicitly in this audit query.

### 33.3. Checking Duplicate external_id per Tenant

```sql
SELECT
    tenant_id,
    doc ->> 'external_id' AS external_id,
    COUNT(*) AS occurrences
FROM json313.orders
GROUP BY tenant_id, doc ->> 'external_id'
HAVING COUNT(*) > 1
ORDER BY occurrences DESC, tenant_id;
```

An audit query only **detects** existing duplicates in a snapshot; to **prevent** concurrent duplicate writes you need an appropriate `UNIQUE` index/constraint.

### 33.4. Auditing JSON null

```sql
SELECT order_pk
FROM json313.orders
WHERE doc ? 'external_id'
  AND doc -> 'external_id' = 'null'::jsonb;
```

This finds JSON null stored **inside** `external_id`, without relying on `IS NULL` on extracted text.

## 34. JSONB Indexes: GIN and B-tree Expressions

Validation and query performance are distinct concerns.

### 34.1. B-tree on an Extracted Attribute

Looking up an `external_id`:

```sql
SELECT order_pk, tenant_id
FROM json313.orders
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

The unique expression index:

```sql
ON json313.orders(tenant_id, (doc ->> 'external_id'))
```

serves both uniqueness and equality lookups on both components.

### 34.2. GIN for JSONB Containment

Example query:

```sql
SELECT order_pk
FROM json313.orders
WHERE doc @> '{"status":"NEW"}'::jsonb;
```

A GIN index helps:

```sql
CREATE INDEX idx_json313_orders_doc_gin
ON json313.orders
USING gin (doc);
```

This uses the default `jsonb_ops` operator class, supporting containment and key-existence operators.

### 34.3. jsonb_ops and jsonb_path_ops

Another option:

```sql
CREATE INDEX idx_json313_orders_doc_path_gin
ON json313.orders
USING gin (doc jsonb_path_ops);
```

`jsonb_path_ops` focuses on `@>` and eligible JSONPath forms with a different entry structure. It **does not** support key-existence operators like `?` the way `jsonb_ops` does.

Do not create both GIN indexes just to match the example; pick the operator class matching your workload and measure storage and write cost.

### 34.4. GIN Does Not Replace CHECK or UNIQUE

A GIN index accelerates JSON searches; it does **not** guarantee:

- `external_id` always exists.
- `status` is a valid string.
- `amount_cents` is non-negative.
- `external_id` is unique per tenant.
- Identity cannot be modified after `INSERT`.

Data protection requires constraints, triggers, and proper column design—not indexes alone.

## 35. EXPLAIN with JSONB Queries

After loading lab data:

```sql
ANALYZE json313.orders;
```

Examples:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_pk, tenant_id
FROM json313.orders
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

and:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_pk
FROM json313.orders
WHERE doc @> '{"status":"NEW"}'::jsonb;
```

Inspect:

- `Seq Scan`, `Index Scan`, or `Bitmap Index Scan`.
- `Index Cond` and `Filter`.
- Estimated rows vs. actual rows.
- `Buffers`, timing, and loops.

### 35.1. Small Lab Tables Can Use Seq Scan

With only a handful of orders, Seq Scan is cheaper than an Index Scan. Skipping GIN or B-tree on a tiny table **does not prove the index is broken**.

To evaluate real performance, test with production-like row counts and distributions.

### 35.2. Indexes Have a Cost

Every index requires:

- Storage space.
- Maintenance on `INSERT`/`UPDATE`/`DELETE`.
- WAL and I/O.
- Build and rebuild time.
- Migration management.

On large, frequently updated JSONB documents, adding multiple whole-document indexes can sharply increase write overhead.

## 36. JSONB vs. Relational Model: Practical Boundaries

A sound hybrid layout:

**Relational columns** for:

- Primary keys.
- Tenant ID.
- External ID.
- Transaction status.
- Amounts and timestamps used in filtering/sorting.
- Foreign keys.
- Frequently updated or strongly constrained values.

**JSONB** for:

- Optional metadata.
- Flexible payloads from external providers.
- Extended attributes rarely joined.
- Versioned supplementary data.
- Small objects persisted near-verbatim for a workflow.

### 36.1. Why Not Put Everything in JSONB?

If `amount_cents`, `currency`, `tenant_id`, and `status` all live inside JSON:

- Every check must extract and cast.
- Foreign keys on attributes are hard to enforce.
- Indexing grows complex.
- Column privileges cannot separate individual JSON keys.
- Updating hot fields rewrites the entire JSONB value.
- ORMs and consumers can misread types or NULLs.

### 36.2. Why Not Normalize Every Single Attribute Either?

Unstable metadata rarely warrants splitting into dozens of extra tables and columns. JSONB delivers real value when shapes vary across sources and fields do not participate in core constraints.

Base decisions on **business role and access patterns**, not slogans like "JSON is always bad" or "schema-less is always faster."

## 37. Limits of Triggers and Constraints Under Concurrency

A `CHECK` evaluates **one row** using immutable functions on that row's data, which works well for intra-document rules.

However, some rules span **multiple rows**:

```text
Each tenant + external_id may appear only once.
```

Use `UNIQUE`.

Or:

```text
Total PAID orders for a tenant must not exceed quota.
```

This is a cross-row aggregate invariant; adding a JSON-extracting `CHECK` does not make it safe.

### 37.1. SELECT COUNT Triggers Can Race

If a trigger checks:

```text
COUNT(orders with same external_id)
```

and allows `INSERT` when count = 0, two concurrent transactions can both observe count = 0 in their own snapshots.

A unique index is the reliable mechanism for uniqueness. For complex cross-row invariants, use appropriate isolation levels, locking protocols, or summary tables with retries.

### 37.2. Do Not Treat RLS as Validation

RLS enforces row access control; it does not replace `CHECK`, `UNIQUE`, or JSON type validation.

### 37.3. Do Not Treat Triggers as Absolute Protection Against DBA Accounts

Privileged accounts can alter schemas or disable triggers. Operational security relies on role management, migration audits, and controlled deployment pipelines.

## 38. Protecting Sensitive Data in JSON and Logs

JSONB may hold emails, addresses, verification codes, payment payloads, or other PII.

When sensitive fields live in `doc`:

- Avoid `SELECT doc` for consumers that only need two columns.
- Never dump full JSON payloads into validation error logs.
- Never expose another tenant's payload through queries missing `tenant_id`.
- Evaluate encryption or tokenization where security requires it.
- Govern replicas, backups, test environments, and demo fixtures.
- Audit indexes and search vectors that might retain sensitive content.
- Review operator permissions on statistics, audits, and logs.

### 38.1. Constraint Error Messages

A SQLSTATE `23514` error can reveal a constraint name and sometimes row details. Never return raw database exceptions with full JSON payloads to clients.

Instead:

```text
HTTP 422:
  code = INVALID_ORDER_DOCUMENT
  field = amount_cents
  message = "Invalid order amount"
```

This example shows API response design, not PostgreSQL's automatic error format.

### 38.2. Database Error Codes

| SQLSTATE | Common Name | Example |
|---|---|---|
| `22P02` | `invalid_text_representation` | Invalid JSON text or cast |
| `23502` | `not_null_violation` | `doc` or `tenant_id` is SQL NULL |
| `23514` | `check_violation` | JSON fails `CHECK` type/value rules |
| `23505` | `unique_violation` | Duplicate `tenant_id` + `external_id` |
| `23503` | `foreign_key_violation` | Invalid reference when FKs exist |
| `40001` | `serialization_failure` | Transaction must roll back and retry |
| `40P01` | `deadlock_detected` | Transaction aborted due to deadlock |

Some type/range cast errors emit other SQLSTATEs. Applications should inspect actual SQLSTATE codes rather than matching substrings in exception text.

## 39. Hands-On Verification with Valid and Invalid Data

Run only in a lab database. **Intentionally invalid** examples are expected to fail; inside an explicit aborted transaction, run `ROLLBACK` or use a savepoint before the next test.

### 39.1. Missing Key

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"status":"NEW","amount_cents":0,"currency":"VND","items":[]}'
);
```

Violates required keys and other constraints.

### 39.2. JSON null

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":null,"status":"NEW","amount_cents":0,
      "currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

Key name is present, but type is not string.

### 39.3. Mistyped Status

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD1","status":3,"amount_cents":0,
      "currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

JSON number `status` is invalid.

### 39.4. Negative Amount

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD2","status":"NEW",
      "amount_cents":-1,"currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

### 39.5. Fractional Amount

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD3","status":"NEW",
      "amount_cents":10.5,"currency":"VND","items":[
        {"sku":"SKU-Z","qty":1,"unit_price_cents":0}
      ],"shipping":{"city":"Hue"}}'
);
```

### 39.6. Items Not an Array

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD4","status":"NEW",
      "amount_cents":0,"currency":"VND","items":{},
      "shipping":{"city":"Hue"}}'
);
```

### 39.7. One Bad Item Invalidates the Whole Document

```sql
-- Expected to be rejected:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-BAD5","status":"NEW",
      "amount_cents":100,"currency":"VND",
      "items":[
        {"sku":"SKU-A","qty":1,"unit_price_cents":100},
        {"sku":"SKU-B","qty":-2,"unit_price_cents":100}
      ],
      "shipping":{"city":"Hue"}}'
);
```

`NOT EXISTS (invalid item)` catches the second item's negative `qty`.

### 39.8. Duplicate external_id in the Same Tenant

After creating the unique expression index:

```sql
-- Expected unique_violation if this external_id already exists:
INSERT INTO json313.orders(tenant_id, doc)
VALUES (
    7,
    '{"external_id":"ORD-2026-0001","status":"NEW",
      "amount_cents":0,"currency":"VND",
      "items":[{"sku":"SKU-Z","qty":1,"unit_price_cents":0}],
      "shipping":{"city":"Hue"}}'
);
```

### 39.9. Changing external_id After Creation

```sql
-- Expected to be rejected by trigger:
UPDATE json313.orders
SET doc = jsonb_set(
    doc, '{external_id}', '"ORD-CHANGED"'::jsonb, false
)
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

### 39.10. Reverting PAID to NEW

After a valid order has transitioned to `PAID`, try:

```sql
-- Expected to be rejected by trigger:
UPDATE json313.orders
SET doc = jsonb_set(
    doc, '{status}', '"NEW"'::jsonb, false
)
WHERE tenant_id = 7
  AND doc ->> 'external_id' = 'ORD-2026-0001';
```

The sample trigger specifically blocks `PAID → NEW`.

## 40. Self-Practice Exercises with Solutions

### Exercise 1. Does a NOT NULL jsonb Column Allow JSON null?

**Answer:** column `NOT NULL` blocks **SQL NULL**, not the JSONB value `'null'::jsonb`. To require a root object, add `CHECK (jsonb_typeof(doc) = 'object')`.

### Exercise 2. Why Does CHECK(length(doc->>'x')>0) Let Missing Keys Pass?

**Answer:** `doc->>'x'` returns SQL NULL when missing; the comparison evaluates to UNKNOWN, which PostgreSQL `CHECK` accepts.

### Exercise 3. Fix the CHECK So Key x Must Be Non-Empty

```sql
CHECK (
    (length(btrim(doc ->> 'x')) > 0) IS TRUE
)
```

**Answer:** both `FALSE` and `UNKNOWN` are rejected.

### Exercise 4. How Do You Check Key Presence Even When Value Is JSON null?

```sql
SELECT '{"x":null}'::jsonb ? 'x';
```

**Answer:** `TRUE`.

### Exercise 5. Distinguish Missing Key from JSON null

```sql
SELECT
    '{}'::jsonb ? 'x' AS missing,
    '{"x":null}'::jsonb ? 'x' AS present_null,
    jsonb_typeof('{"x":null}'::jsonb -> 'x') AS type_of_x;
```

**Answer:** `missing = FALSE`, `present_null = TRUE`, `type_of_x` is the string `'null'`.

### Exercise 6. Why Is jsonb_typeof(...) = 'number' Not Enough for amount_cents?

**Answer:** a JSON number can be negative or fractional; you must validate bounds and integer-ness.

### Exercise 7. Why Use CASE Before Numeric Casting?

**Answer:** to cast only after verifying the JSON type, without relying on `AND` evaluation order as a guard.

### Exercise 8. Is items=[] Valid Here?

**Answer:** No. The schema requires an array of 1 to 100 elements.

### Exercise 9. Does the Length Constraint Reject items=[null]?

**Answer:** No. Array length is 1, which passes the element-count check; per-item validation is required.

### Exercise 10. Is EXISTS(valid item) Enough to Validate All Items?

**Answer:** No. You need `NOT EXISTS(invalid item)` or an equivalent validator.

### Exercise 11. Is Calling jsonb_array_elements on an Object Safe?

**Answer:** No. Guard that the input is an array with `CASE` or constraints beforehand.

### Exercise 12. What Does jsonb_path_exists Finding One SKU-A Mean?

**Answer:** **at least one** item matched the filter. It does not ensure all items are valid.

### Exercise 13. How to Verify Nested city Is a String?

```sql
jsonb_typeof(doc #> '{shipping,city}') = 'string'
```

**Answer:** combine with `IS TRUE` and a non-empty check if `city` is required.

### Exercise 14. What Index Enforces Unique external_id per Tenant?

```sql
CREATE UNIQUE INDEX ...
ON json313.orders(tenant_id, (doc ->> 'external_id'));
```

**Answer:** a unique expression index on tenant and the JSON attribute, paired with required/type `CHECK`s.

### Exercise 15. Can SELECT NOT EXISTS Before INSERT Replace UNIQUE?

**Answer:** no, it is unsafe under concurrency; two transactions can both see no row. A unique index is the primary enforcement layer.

### Exercise 16. Does a Format CHECK on external_id Stop Changing ORD-1 to ORD-2?

**Answer:** no, because both match the format. You need an OLD/NEW trigger or restricted write privileges/model.

### Exercise 17. What Advantage Does IS DISTINCT FROM Offer in Triggers?

**Answer:** it compares cleanly when one side is NULL, never returning `UNKNOWN` like `<>`.

### Exercise 18. Does an Enum CHECK on status Protect State Transitions?

**Answer:** no. An enum `CHECK` validates only the current value, not historical transitions.

### Exercise 19. Does jsonb_set Verify Caller Permissions on the Field?

**Answer:** no. Role/tenant authorization, `CHECK`s, triggers, and API checks are still required.

### Exercise 20. Why Is Rewriting the Entire doc from a Stale Read Dangerous?

**Answer:** it can overwrite concurrent updates from other transactions, causing lost updates. Use targeted path updates and/or version checks.

### Exercise 21. How Does Optimistic Locking with version Work?

**Answer:** include `WHERE version = expected` in the `UPDATE`, increment `version` on match, and check `RETURNING` / row count.

### Exercise 22. Does Column-Level REVOKE UPDATE(doc) Block Editing Individual JSON Keys?

**Answer:** only within overall PostgreSQL privileges. If a role holds table-level `UPDATE` via another grant, it can still edit `doc`. There is no native per-JSON-key `GRANT`.

### Exercise 23. Does RLS Validate amount_cents?

**Answer:** no. RLS filters rows by policy; `CHECK` and validation enforce JSON attribute rules.

### Exercise 24. Does Core PostgreSQL jsonb Implement Full JSON Schema?

**Answer:** not automatically by virtue of using `jsonb`. Use `CHECK`/custom functions or an appropriate extension/library.

### Exercise 25. When Changing an IMMUTABLE Validator Function Used in CHECK, Are Old Rows Re-Checked?

**Answer:** not automatically. Migrations must audit and validate existing rows under the new logic.

### Exercise 26. Does ADD CONSTRAINT ... NOT VALID Skip Checking New Rows?

**Answer:** no. It only skips scanning existing rows at `ADD` time for supported constraints.

### Exercise 27. Does a GIN Index Replace UNIQUE?

**Answer:** no. GIN accelerates searches; it does not enforce uniqueness of `external_id`.

### Exercise 28. When Is a B-tree Expression Index Better Than Whole-Document GIN?

**Answer:** when queries regularly do equality lookups on a scalar attribute such as `tenant + external_id`, or need uniqueness on a specific key.

### Exercise 29. Which Attributes Should Become Relational Columns?

**Answer:** typically tenant ID, business ID, FKs, key statuses and amounts, timestamps, and fields queried or updated heavily.

### Exercise 30. Can CHECK Guarantee Total PAID Orders per Tenant Stay Under Quota?

**Answer:** no, `CHECK` does not enforce cross-row invariants; use counters/locks or suitable isolation/table design.

### Exercise 31. Why Does JSON null Differ from Deleting a Key?

**Answer:** `{"x":null}` still contains `x`; `{}` does not. `? 'x'` distinguishes them, whereas `->>` returns SQL NULL for both.

### Exercise 32. What Must You Watch Before Returning Validation Errors to Clients?

**Answer:** never leak full sensitive documents. Return stable error codes and safe field/message details.

## 41. Common Mistakes

### Mistake 1 — Thinking jsonb Equals JSON Schema

`jsonb` checks JSON syntax; it does not protect business fields.

### Mistake 2 — Not Validating the Root Object

JSONB can hold an array, string, number, boolean, or JSON null at the root.

### Mistake 3 — Checking Only doc NOT NULL

Does not stop inner keys from being missing or JSON null.

### Mistake 4 — Writing CHECK Expressions That Can Evaluate to UNKNOWN

PostgreSQL `CHECK` allows UNKNOWN; use `IS TRUE`, `COALESCE`, or explicit presence predicates.

### Mistake 5 — Using ->> and Forgetting the Original JSON Type

`->>` turns multiple JSON types into text; numbers and booleans could pass as strings.

### Mistake 6 — Checking Only Key Existence

`doc ? 'status'` is `TRUE` even when `status` is JSON null or a mistyped number.

### Mistake 7 — Casting Unvalidated Data Directly to Integer

Risks parse or overflow errors; check type and range first inside `CASE`.

### Mistake 8 — Calling jsonb_array_length on an Object

Raises an error; verify JSON array type first.

### Mistake 9 — Using One Valid Item to Prove the Whole Array

Must check **`NOT EXISTS` invalid item**, not `EXISTS` one valid item.

### Mistake 10 — Thinking JSONPath Existence Validates the Entire Schema

One matching path does not prove every field and nested element is valid.

### Mistake 11 — Unique Expression Index Without a Required CHECK

Missing or JSON null fields extract to SQL NULL, bypassing expected uniqueness.

### Mistake 12 — Format CHECK Without Immutability Protection

`CHECK` never compares OLD vs. NEW; use a trigger or proper write model.

### Mistake 13 — Replacing State Machines with an Enum CHECK

Both old and new statuses belong to the enum even when the transition between them is illegal.

### Mistake 14 — Granting UPDATE on doc Expecting Per-Key Control

Column privileges do not distinguish JSON paths.

### Mistake 15 — Using RLS Instead of Validation

RLS scopes rows; it does not replace type or value constraints.

### Mistake 16 — Updating the Whole Document from a Stale Read

Overwrites concurrent edits. Use `jsonb_set`, versioning, or proper locking.

### Mistake 17 — Changing a Validator Function Without Re-Checking Old Rows

Historical rows are not revalidated automatically when a `CHECK` function body changes.

### Mistake 18 — Using NOT VALID Thinking Constraints Are Disabled

All new writes must still satisfy the constraint.

### Mistake 19 — Treating a GIN Index as a Substitute for UNIQUE

Search indexes do not enforce uniqueness.

### Mistake 20 — Putting All Critical Fields into JSONB

Makes FKs, constraints, column privileges, and frequent updates painful; prefer a hybrid model.

### Mistake 21 — Forgetting tenant_id in Queries, Updates, or Unique Indexes

Risks cross-tenant collisions or data leaks.

### Mistake 22 — Logging Full Sensitive Documents on Error

A constraint error is no reason to leak payloads into logs.

### Mistake 23 — Skipping Transaction Retries and Rollbacks

Multi-step operations can abort; external side effects must be coordinated properly.

### Mistake 24 — Assuming Legacy Rows Are Valid Just Because CHECK Exists

When added with `NOT VALID`, old rows remain unverified until audited and `VALIDATE`d.

## 42. Process for Designing Validation on a JSON Document

A practical workflow:

1. **Write the business contract:** required fields, types, bounds, enums, nested objects, uniqueness, and state transition rules.
2. **Choose data boundaries:** which values belong in relational columns and which fit JSONB.
3. **Validate syntax:** parse/cast to `jsonb` on ingestion.
4. **Validate root:** object or array as intended.
5. **Validate presence:** required keys at the right level.
6. **Validate types:** `jsonb_typeof` or equivalent validator.
7. **Validate value domains:** non-empty, enums, ranges, integers, regexes.
8. **Validate nested arrays:** every element, not just one.
9. **Validate cross-field rules:** `amount` vs. `items`, `currency` vs. `amount` when business logic demands.
10. **Enforce cross-row rules:** `UNIQUE`, `FK`, and compatible constraints.
11. **Protect state transitions:** triggers or privileged write protocols.
12. **Constrain updates:** conditional `UPDATE`, optimistic versioning, or transactions.
13. **Enforce access control:** least privilege and tenant RLS where needed.
14. **Version schemas:** explicit migration and compatibility strategy.
15. **Reconcile legacy data:** `NOT VALID` and `VALIDATE` when appropriate.
16. **Observe in production:** error codes, metrics, index usage, and safe audits.
17. **Test thoroughly:** valid, missing, JSON null, SQL NULL, wrong types, overflows, duplicates, concurrent writes.
18. **Optimize:** add indexes only from real workloads and `EXPLAIN` output.

This is practical knowledge for learners implementing PostgreSQL in real systems, not an internal QA checklist.

## 43. Quick Reference Table

| Requirement | PostgreSQL Tool / Pattern | Key Point to Remember |
|---|---|---|
| Valid JSON syntax | `jsonb` / `::jsonb` cast | Does not enforce schema |
| Root is an object | `CHECK (jsonb_typeof(doc)='object')` | `doc` also needs `NOT NULL` |
| Top-level key exists | `doc ? 'key'` | Does not rule out JSON null |
| Multiple required keys | `doc ?& ARRAY[...]` | Checks presence only |
| Value type | `jsonb_typeof(doc->'key')` | Returns SQL NULL if missing |
| Non-empty string | `length(btrim(doc->>'x'))>0` with `IS TRUE` | `CHECK` UNKNOWN pitfall |
| Enum | `doc->>'status' IN (...)` plus type check | Does not guard transitions |
| Integer/range number | `CASE` + `::numeric` + `trunc` | Avoid casting mistyped values |
| Valid array type | `jsonb_typeof(...)= 'array'` | `jsonb_array_length` requires array |
| All array items valid | `NOT EXISTS(jsonb_array_elements(...) bad item)` | Checks every element |
| Nested path | `#>` and `#>>` | Distinguish JSONB, text, and NULL |
| Find value in array | `@?` / `jsonb_path_exists` | Existence is not ALL |
| Unique ID per tenant | Unique expression index | Pair with required/type `CHECK` |
| Immutable critical key | OLD/NEW trigger, write privileges | `CHECK` sees only new row |
| Update one field | `jsonb_set` | Does not replace validation |
| Optimistic concurrency | `WHERE version=?` + increment | Check returned row count |
| Query JSON scalar | B-tree expression index | Fits equality and ranges |
| Query JSON containment | GIN `jsonb_ops` / `jsonb_path_ops` | Pick by operator class |
| Add `CHECK` incrementally | `ADD CONSTRAINT ... NOT VALID` | New writes are still checked |
| Verify legacy rows | `VALIDATE CONSTRAINT` | Repair invalid rows first |
| Tenant isolation | RLS + auth context | Does not replace JSON validation |
| Complex JSON contracts | JSON Schema + compatible validator | Extensions are not built-in |

## 44. PostgreSQL Reference Documentation

Always consult documentation matching your exact **PostgreSQL version** and system configuration:

- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html): differences between `json` and `jsonb`, storage, and syntax checking.
- [JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): `->`, `->>`, `#>`, `?`, `?&`, `jsonb_set`, JSONPath.
- [SQL/JSON Path Expressions](https://www.postgresql.org/docs/current/functions-json.html#FUNCTIONS-SQLJSON-PATH): JSONPath and behavior on nested data.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): `CHECK`, `NOT NULL`, `UNIQUE`, and `FOREIGN KEY`.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): unique/expression B-trees.
- [GIN Indexes](https://www.postgresql.org/docs/current/gin.html): JSONB indexing and operator classes.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): row-level access control.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): table and column privileges.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): guarding mutations with OLD/NEW.
- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): adding and validating constraints.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): reading query plans.

Check your environment:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

Examples in this lesson are instructional code, not outputs captured from a specific server. For production, verify DDL, constraints, privileges, and migrations on a representative staging copy.

## 45. Summary

A JSONB document can be **syntactically valid** yet **violate the data contract**. PostgreSQL offers multiple layers to protect critical fields:

```text
Application submits JSON
       |
       v
Parse/cast to jsonb
       |
       v
NOT NULL + root type check
       |
       v
Required keys + type + value checks
       |
       v
Nested arrays/objects validation
       |
       v
UNIQUE/FK for cross-row rules
       |
       v
Triggers/privileges for immutable fields
       |
       v
Transactions + concurrency + audit
       |
       v
Committed data satisfies contract
```

Key takeaways:

1. **`jsonb` is not a default JSON Schema validator.** It enforces syntax, not business fields.
2. **JSON null, SQL NULL, and missing keys are three distinct states.** Use matching operators to separate them.
3. **`CHECK` accepts UNKNOWN.** Use `IS TRUE`, `COALESCE`, and existence/type predicates to catch missing fields.
4. **Check underlying types with `jsonb_typeof` before casting** important numeric or string fields.
5. **JSON arrays must validate every element**, not merely array length or one valid item.
6. **Identifier keys require proper `UNIQUE` constraints**, not just regexes or `SELECT NOT EXISTS`.
7. **`CHECK` does not enforce immutability over time.** Use OLD/NEW triggers, write privileges, or relational columns to prevent edits to critical fields.
8. **State machines differ from enums.** Valid individual states do not guarantee valid transitions.
9. **`jsonb_set` and optimistic versioning** enable conditional updates, but do not replace authorization or constraints.
10. **RLS and column privileges do not replace JSON validation**; column grants do not understand individual JSON keys.
11. **Roll out constraints incrementally with `NOT VALID` / `VALIDATE`** to handle historical data safely.
12. **Keep JSONB for flexible attributes and relational columns for core invariants** whenever doing so makes the schema clearer and safer.

**One sentence to remember:** JSONB lets you store flexible data, yet fields governing identity, money, state, and access control must still be guarded in PostgreSQL by **constraints with clear semantics**, never merely by the fact that a document is valid JSON.
