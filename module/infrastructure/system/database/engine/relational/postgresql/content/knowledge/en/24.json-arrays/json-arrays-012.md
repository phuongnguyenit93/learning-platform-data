# Distinguishing JSON null, SQL NULL, and Missing Elements in PostgreSQL

Suppose an API receives three payloads:

```json
{"email": null}
```

```json
{}
```

```json
{"email": "null"}
```

These three payloads **are not the same**. The first has an `email` key with a **JSON null value**; the second **does not have an `email` key**; the third has an `email` key containing the **four-character text string `null`**. Furthermore, a `jsonb` column in PostgreSQL can also hold **SQL NULL**, meaning *the column itself has no SQL value*, rather than storing a JSON document containing the keyword `null`.

This distinction directly affects API PATCH logic, customer profile updates, JSONB filtering, schema validation, event synchronization, and Java/JDBC deserialization. Misunderstanding it can overwrite valid values with NULL, treat an explicitly cleared field the same as an omitted field, or lose essential state through `COALESCE`.

This lesson breaks down the three states—**SQL NULL**, **JSON null**, and **missing elements (missing key/path/index)**—and analyzes precisely how PostgreSQL handles them across JSON/JSONB operators, type-inspection functions, SQL NULL logic, updates, and constraints.

> **Core takeaway:** `'null'::jsonb` is an **existing JSONB value**, whereas `NULL::jsonb` is **SQL NULL**. When looking up a missing key with `->`, PostgreSQL returns **SQL NULL**; when the key holds JSON null, `->` returns **JSONB null**. However, `->>` converts to text, so both cases return **SQL NULL**, erasing the distinction if you only inspect the text output.

## 1. Learning objectives

After this lesson, you will be able to:

1. Define SQL NULL, JSON null, missing object keys, JSON null array elements, and out-of-bounds array indexes.
2. Distinguish the output of `->` vs. `->>` and `#>` vs. `#>>` when encountering JSON null or missing elements.
3. Use `IS NULL`, `= 'null'::jsonb`, `jsonb_typeof`, and `?` to test the exact condition you mean.
4. Understand why SQL uses **three-valued logic**—TRUE, FALSE, and UNKNOWN—when comparing against SQL NULL.
5. Avoid accidentally collapsing distinct states with `COALESCE` or text casts.
6. Distinguish keys holding JSON null from missing keys inside nested JSONB objects.
7. Understand how JSON arrays handle `null`, missing indexes, and negative indexes.
8. Know when to use `jsonb_set`, `jsonb_set_lax`, `-`, and `#-` to update or remove elements.
9. Design `CHECK`, `NOT NULL`, defaults, and unique/index strategies matching missing-field / JSON-null / SQL-NULL semantics.
10. Implement JSON PATCH/API rules and Java decoding without losing key presence information.

## 2. Three states you must distinguish

| State | Example | Meaning |
| --- | --- | --- |
| **SQL NULL** | `NULL::jsonb` | An SQL column or expression has no value. Not a JSON document holding a literal null. |
| **JSON null** | `'null'::jsonb` or `'{"email":null}'::jsonb` | A genuine JSON value whose JSON type is `null`. |
| **Missing** | `'{}'::jsonb` lacks `email` | Inside an object, the key does not exist; or in an array, the index is out of bounds. |

Additionally, none of the following values are NULL:

```json
{"email": ""}
```

```json
{"email": "null"}
```

```json
{"email": false}
```

```json
{"email": 0}
```

```json
{"email": []}
```

```json
{"email": {}}
```

These values have JSON types string, string, boolean, number, array, and object, respectively. Never treat an empty string, 0, boolean false, or an empty collection as JSON null simply because a domain uses them to represent “no information.”

### 2.1. SQL NULL operates at the SQL expression level

```sql
SELECT
    NULL::jsonb AS sql_null,
    'null'::jsonb AS json_null,
    '{}'::jsonb AS empty_object,
    '[]'::jsonb AS empty_array;
```

`NULL::jsonb` specifies **SQL NULL typed as jsonb**. By contrast, `'null'::jsonb` is a **scalar jsonb value** representing JSON null.

In a `doc jsonb` column, both can be stored unless prevented by a `NOT NULL` constraint.

### 2.2. Missing only applies to elements inside a structure

Given:

```json
{"customer":{"name":"Lan"}}
```

`customer` exists; `customer.name` exists; `customer.email` is missing. The JSON document itself is **not missing**, since it was provided.

When a PostgreSQL operator looks up a non-existent path, the result is typically represented as **SQL NULL**. That does not make the two concepts semantically identical: you can still check **key presence** on an object using the right operator.

### 2.3. JSON null is a value, not an automatic deletion marker

`{"email":null}` means a JSON object containing an `email` field whose value is JSON null. In some protocols (such as JSON Merge Patch), `null` signals *remove the field*, but that is an **application protocol rule**, not PostgreSQL's default storage or JSONB update behavior.

Run:

```sql
SELECT '{"email": null}'::jsonb;
```

PostgreSQL does not strip the `email` key on its own. Deleting a key happens only when your SQL or application explicitly chooses to do so.

## 3. json vs. jsonb: this distinction exists in both

PostgreSQL provides two JSON types:

- `json`: stores validated JSON text verbatim, preserving formatting/key quirks of the original text.
- `jsonb`: stores parsed binary JSON, supporting rich operators, membership tests, partial updates, and indexing.

Both distinguish **JSON null** from **SQL NULL**, and both support field-extraction operators. This lesson focuses on `jsonb` because it is much better suited for key-existence checks, containment, JSONPath, and updates in PostgreSQL.

### 3.1. Checking JSON types

```sql
SELECT
    json_typeof('null'::json) AS type_from_json,
    jsonb_typeof('null'::jsonb) AS type_from_jsonb;
```

Both return the **SQL text string `null`** (not SQL NULL), naming the JSON type.

Compare with:

```sql
SELECT
    json_typeof(NULL::json) AS sql_null_json_type,
    jsonb_typeof(NULL::jsonb) AS sql_null_jsonb_type;
```

Both return **SQL NULL**.

### 3.2. Do not confuse the type name text "null" with a JSON null value

`jsonb_typeof` returns **text**, so:

```sql
SELECT
    jsonb_typeof('null'::jsonb) = 'null'
        AS is_json_null,
    jsonb_typeof('null'::jsonb) IS NULL
        AS is_sql_null;
```

Returns TRUE and FALSE respectively.

Conversely:

```sql
SELECT
    jsonb_typeof(NULL::jsonb) = 'null'
        AS comparison_with_sql_null,
    jsonb_typeof(NULL::jsonb) IS NULL
        AS is_sql_null;
```

The first expression yields SQL UNKNOWN/NULL; the second yields TRUE. When placing these inside `WHERE`, remember SQL only retains rows where the predicate evaluates to TRUE.

## 4. Practice dataset covering every state

The SQL below is for a **lab database** only; never modify production data.

### 4.1. Create schema and table

```sql
CREATE SCHEMA IF NOT EXISTS json_null_lab;

CREATE TABLE json_null_lab.documents (
    id integer PRIMARY KEY,
    description text NOT NULL,
    doc jsonb
);
```

Column `doc` intentionally **allows SQL NULL** so we can practice distinguishing it from JSON null. In production, consider `NOT NULL` when every row must contain a JSON document.

### 4.2. Insert data

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    ( 1, 'SQL NULL document', NULL::jsonb),
    ( 2, 'JSON null document', 'null'::jsonb),
    ( 3, 'Empty object', '{}'::jsonb),
    ( 4, 'Email JSON null', '{"email":null}'::jsonb),
    ( 5, 'Email string null', '{"email":"null"}'::jsonb),
    ( 6, 'Email empty string', '{"email":""}'::jsonb),
    ( 7, 'Email normal string',
          '{"email":"a@example.com"}'::jsonb),
    ( 8, 'Email false', '{"email":false}'::jsonb),
    ( 9, 'Nested empty profile', '{"profile":{}}'::jsonb),
    (10, 'Nested email JSON null',
          '{"profile":{"email":null}}'::jsonb),
    (11, 'Profile JSON null', '{"profile":null}'::jsonb),
    (12, 'Nested email normal',
          '{"profile":{"email":"p@example.com"}}'::jsonb),
    (13, 'Empty array document', '[]'::jsonb),
    (14, 'Array with JSON null', '[null]'::jsonb),
    (15, 'Array with string null', '["null"]'::jsonb),
    (16, 'Mixed array', '[null,7,false,""]'::jsonb),
    (17, 'Email number zero', '{"email":0}'::jsonb),
    (18, 'Email empty object', '{"email":{}}'::jsonb);
```

Insert once into an empty table. Re-running triggers a primary key conflict on `id`. All JSON strings are synthetic test data containing no real user records.

### 4.3. Inspecting top-level document types

```sql
SELECT
    id,
    description,
    doc IS NULL AS is_sql_null,
    jsonb_typeof(doc) AS json_type
FROM json_null_lab.documents
ORDER BY id;
```

Notable rows:

| id | doc | `doc IS NULL` | `jsonb_typeof(doc)` |
| ---: | --- | --- | --- |
| 1 | SQL NULL | TRUE | SQL NULL |
| 2 | `null` | FALSE | `null` (text) |
| 3 | `{}` | FALSE | `object` |
| 4 | `{"email":null}` | FALSE | `object` |
| 13 | `[]` | FALSE | `array` |
| 14 | `[null]` | FALSE | `array` |

**Key observation:** an object containing a JSON null field still has type **`object`** at the document level. To check whether `email` is null, extract the field before calling `jsonb_typeof`.

### 4.4. Null document vs. empty object

Compare:

```sql
SELECT
    id,
    doc IS NULL AS sql_null_document,
    doc = 'null'::jsonb AS json_null_document,
    doc = '{}'::jsonb AS empty_json_object
FROM json_null_lab.documents
WHERE id IN (1, 2, 3)
ORDER BY id;
```

For `id=1`, both `doc = ...` comparisons return SQL NULL—**not FALSE**—because standard comparisons with SQL NULL yield UNKNOWN. For guaranteed boolean results, use `IS NULL`, `IS DISTINCT FROM`, or `CASE` depending on intent.

## 5. The -> operator: extracting JSON values without converting to text

The operator:

```sql
document -> 'key'
```

returns `json` or `jsonb` matching the input type. This is the key tool for **preserving the difference between JSON null and missing**.

### 5.1. When the key exists with JSON null

```sql
SELECT '{"email":null}'::jsonb -> 'email' AS email_json;
```

The result is a **JSONB null value**. That means the expression is not SQL NULL:

```sql
SELECT
    ('{"email":null}'::jsonb -> 'email') IS NULL
        AS is_sql_null,
    ('{"email":null}'::jsonb -> 'email') = 'null'::jsonb
        AS is_json_null;
```

Result:

| `is_sql_null` | `is_json_null` |
| --- | --- |
| FALSE | TRUE |

### 5.2. When the key does not exist

```sql
SELECT '{}'::jsonb -> 'email' AS email_json;
```

Since there is no `email` key, the result is **SQL NULL**:

```sql
SELECT
    ('{}'::jsonb -> 'email') IS NULL
        AS is_missing_extraction,
    ('{}'::jsonb -> 'email') = 'null'::jsonb
        AS equals_json_null;
```

Returns TRUE and SQL NULL/UNKNOWN respectively. Comparing against `'null'::jsonb` does not yield FALSE here because the left-hand side is SQL NULL.

### 5.3. When the root document is SQL NULL

```sql
SELECT NULL::jsonb -> 'email' AS extracted_value;
```

This also returns **SQL NULL**. Thus `->` alone cannot distinguish:

1. Column `doc` is SQL NULL.
2. Object lacks the `email` key.
3. A nested path cannot be traversed further.

When you need to separate all three, check the **root level** and **key existence** alongside extraction.

### 5.4. When the key holds the string "null"

```sql
SELECT
    '{"email":"null"}'::jsonb -> 'email' AS json_string,
    '{"email":null}'::jsonb -> 'email' AS json_null;
```

The two outputs are **JSONB string `"null"`** and **JSONB null `null`**, with different types and semantics.

## 6. The ->> operator: extracting SQL text and losing the distinction

The operator:

```sql
document ->> 'key'
```

returns **SQL text** instead of `jsonb`. This is commonly used when pulling JSON fields for display, text filters, or Java `String` mapping.

### 6.1. Identical text output for JSON null and missing

```sql
SELECT
    '{"email":null}'::jsonb ->> 'email'
        AS explicit_json_null,
    '{}'::jsonb ->> 'email'
        AS missing_email,
    NULL::jsonb ->> 'email'
        AS sql_null_document;
```

All three columns return **SQL NULL**.

Consequently:

```sql
WHERE doc ->> 'email' IS NULL
```

does not exclusively mean “email is present with JSON null.” It also matches a missing key or an SQL NULL document (unless restricted elsewhere).

### 6.2. The literal string "null" remains real text

```sql
SELECT
    '{"email":"null"}'::jsonb ->> 'email'
        AS string_null,
    '{"email":null}'::jsonb ->> 'email'
        AS json_null;
```

The first column is SQL text containing `null`; the second is SQL NULL. In GUI viewers or CSV exports they may **look identical** if rendered similarly, yet in SQL they are distinct.

### 6.3. Other scalars when extracted as text

```sql
SELECT
    '{"v":false}'::jsonb ->> 'v' AS false_text,
    '{"v":0}'::jsonb ->> 'v' AS zero_text,
    '{"v":""}'::jsonb ->> 'v' AS empty_text,
    '{"v":{}}'::jsonb ->> 'v' AS object_text;
```

The outputs are text `false`, `0`, empty string, and text serialization of the object—**none are SQL NULL**. Because `->>` casts to text, check JSON types beforehand or call `jsonb_typeof` if you need to know whether the source was boolean, number, or object.

### 6.4. Quick comparison

| JSON source | `-> 'email'` | `->> 'email'` |
| --- | --- | --- |
| `{"email":null}` | JSONB null | SQL NULL |
| `{}` | SQL NULL | SQL NULL |
| `{"email":"null"}` | JSONB string `"null"` | SQL text `null` |
| `{"email":""}` | Empty JSONB string | Empty SQL text |
| `{"email":false}` | JSONB boolean false | SQL text `false` |
| SQL NULL document | SQL NULL | SQL NULL |

**Rule:** if you need to tell JSON null apart from missing, **do not rely solely on `->>` output**.

## 7. jsonb_typeof: distinguishing JSON types and SQL NULL

`jsonb_typeof(value)` returns **text** holding one of the JSON type names:

| Input value | Output |
| --- | --- |
| `'null'::jsonb` | `'null'` |
| `'"hello"'::jsonb` | `'string'` |
| `'0'::jsonb` | `'number'` |
| `'false'::jsonb` | `'boolean'` |
| `'[]'::jsonb` | `'array'` |
| `'{}'::jsonb` | `'object'` |
| `NULL::jsonb` | SQL NULL |

### 7.1. Classifying an object field

```sql
SELECT
    id,
    description,
    jsonb_typeof(doc -> 'email') AS email_json_type
FROM json_null_lab.documents
WHERE id IN (3, 4, 5, 6, 7, 8, 17, 18)
ORDER BY id;
```

Expected output:

| id | Email field | `jsonb_typeof(doc -> 'email')` |
| ---: | --- | --- |
| 3 | Missing | SQL NULL |
| 4 | JSON null | Text `null` |
| 5 | JSON string `"null"` | Text `string` |
| 6 | Empty JSON string | Text `string` |
| 7 | Normal email string | Text `string` |
| 8 | JSON false | Text `boolean` |
| 17 | JSON number 0 | Text `number` |
| 18 | Empty JSON object | Text `object` |

### 7.2. Testing explicitly for JSON null

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') = 'null';
```

On the unmodified lab data, this returns **id=4**. Note `jsonb_typeof` inspects the **extracted `email` value**, not the outer document.

### 7.3. Checking missing fields via extraction result

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE (doc -> 'email') IS NULL;
```

This returns documents missing `email` **as well as SQL NULL documents and non-object roots**. If you specifically want “an object missing the `email` key,” combine an object-type check with a key-existence operator rather than relying solely on `IS NULL` over extraction.

### 7.4. Never compare a JSON type against SQL NULL with =

Wrong:

```sql
-- Does not find SQL NULL:
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') = NULL;
```

Every `= NULL` comparison returns UNKNOWN under standard SQL logic, so `WHERE` selects nothing. Use `IS NULL` when checking whether the function produced no value:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc -> 'email') IS NULL;
```

Still remember that SQL NULL from extraction can arise for multiple reasons, including missing keys and SQL NULL documents.

## 8. The ? operator: does the key exist?

On a `jsonb` object, the operator:

```sql
document ? 'email'
```

asks whether **top-level key `email` exists**, regardless of its value.

```sql
SELECT
    '{"email":null}'::jsonb ? 'email'
        AS json_null_field_present,
    '{}'::jsonb ? 'email'
        AS missing_field,
    '{"email":"null"}'::jsonb ? 'email'
        AS string_null_field_present;
```

Result:

| JSON null | Missing | String "null" |
| --- | --- | --- |
| TRUE | FALSE | TRUE |

### 8.1. Combining key presence with JSON type

To separate the states cleanly:

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL THEN 'SQL NULL document'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'Root is not an object'
        WHEN NOT (doc ? 'email')
            THEN 'Missing email key'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'Present JSON null'
        ELSE 'Present non-null JSON value'
    END AS email_state
FROM json_null_lab.documents
ORDER BY id;
```

Branch order in `CASE` is critical here. Failing to check for SQL NULL documents and root object type first conflates “not even an object” with “an object missing the key.”

### 8.2. ? does not search nested levels automatically

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb ? 'email'
        AS top_level_email,
    '{"profile":{"email":null}}'::jsonb ? 'profile'
        AS top_level_profile,
    (
        '{"profile":{"email":null}}'::jsonb -> 'profile'
    ) ? 'email' AS nested_email;
```

Results are FALSE, TRUE, TRUE. `?` on an object inspects **only the top level of the operand**.

### 8.3. ? also has semantics for arrays

On a JSONB array, `?` checks for a top-level **string array element**:

```sql
SELECT
    '["postgres","jsonb"]'::jsonb ? 'jsonb'
        AS has_string_element,
    '[null,"jsonb"]'::jsonb ? 'null'
        AS has_text_null,
    '["null"]'::jsonb ? 'null'
        AS has_string_null;
```

Results are TRUE, FALSE, TRUE. `? 'null'` matches the JSON string `"null"`, **not** literal JSON null. Never apply object-key assumptions blindly to arrays.

### 8.4. When the document is SQL NULL

```sql
SELECT NULL::jsonb ? 'email' AS exists_result;
```

Returns **SQL NULL**, not FALSE. If you want a normalized boolean “is `email` present in an object,” write:

```sql
SELECT
    id,
    COALESCE(
        jsonb_typeof(doc) = 'object'
            AND doc ? 'email',
        FALSE
    ) AS has_email_field
FROM json_null_lab.documents
ORDER BY id;
```

This deliberately classifies SQL NULL documents and non-objects as having no `email` field. That is a **classification rule** for the query, not a claim that SQL NULL is data-equivalent to `{}`.

### 8.5. ?| and ?&

PostgreSQL also provides multi-key/string top-level existence operators:

```sql
SELECT
    '{"email":null,"phone":"123"}'::jsonb
        ?| ARRAY['email','address'] AS has_any,
    '{"email":null,"phone":"123"}'::jsonb
        ?& ARRAY['email','phone'] AS has_all;
```

Both return TRUE. These operators test key/string-element presence and **do not require non-null JSON values**.

## 9. The @> operator: JSONB containment and JSON null

`@>` checks whether the left JSONB value **contains** the right JSONB structure under containment rules.

### 9.1. Object containing JSON null

```sql
SELECT
    '{"email":null}'::jsonb
        @> '{"email":null}'::jsonb AS true_case,
    '{}'::jsonb
        @> '{"email":null}'::jsonb AS false_case,
    '{"email":"null"}'::jsonb
        @> '{"email":null}'::jsonb AS different_type;
```

Results are TRUE, FALSE, FALSE.

Thus:

```sql
WHERE doc @> '{"email":null}'::jsonb
```

matches objects whose `email` key holds **JSON null at that exact path**. It does not match objects missing `email` or holding the string `"null"`.

### 9.2. Empty object containment

```sql
SELECT
    '{}'::jsonb @> '{}'::jsonb AS empty_contains_empty,
    '{"email":null}'::jsonb @> '{}'::jsonb
        AS nonempty_contains_empty;
```

Both return TRUE. Therefore:

```sql
WHERE doc @> '{}'::jsonb
```

does **not** mean “the document must be an empty object.” For exact empty objects, write:

```sql
WHERE doc = '{}'::jsonb
```

where SQL NULL rows are excluded because `=` yields UNKNOWN.

### 9.3. Containment for nested paths

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc @> '{"profile":{"email":null}}'::jsonb;
```

On the lab data, this returns **id=10**, excluding id=9 (`profile` lacks `email`) and id=11 (`profile` is JSON null).

### 9.4. Indexing support for containment

JSONB can use a GIN index with the right operator class for containment and existence queries:

```sql
CREATE INDEX idx_json_null_lab_doc_gin
ON json_null_lab.documents
USING GIN (doc);
```

On an 18-row table, the planner will naturally pick Seq Scan because index traversal isn't worthwhile. With GIN, `jsonb_ops` and `jsonb_path_ops` support **different sets of operators**; notably, `jsonb_path_ops` does not support `?` key-existence queries the way `jsonb_ops` does. Match your index choice to the queries you actually need to accelerate.

## 10. #> and #>>: extracting nested paths

The two operators:

```sql
document #>  '{profile,email}'
document #>> '{profile,email}'
```

extract a **JSON/JSONB value** and **SQL text** respectively along a multi-segment path written as `text[]` (accepting array literals like `'{profile,email}'` in typed context).

### 10.1. Path ending at JSON null

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb
        #> '{profile,email}' AS email_json,
    '{"profile":{"email":null}}'::jsonb
        #>> '{profile,email}' AS email_text;
```

`email_json` is JSONB null; `email_text` is SQL NULL.

### 10.2. Non-existent path

```sql
SELECT
    '{"profile":{}}'::jsonb
        #> '{profile,email}' AS missing_json,
    '{"profile":{}}'::jsonb
        #>> '{profile,email}' AS missing_text;
```

Both return SQL NULL.

### 10.3. Intermediate segment is JSON null

```sql
SELECT
    '{"profile":null}'::jsonb
        #> '{profile,email}' AS nested_under_null,
    '{"profile":null}'::jsonb
        -> 'profile' AS profile_value;
```

The first cannot traverse to `email` beneath a JSON scalar null and returns SQL NULL; the second returns the existing JSONB null at `profile`. Keep this rule in mind:

- **Path terminates** at JSON null: `#> ` returns JSON null.
- **Path tries to traverse through** JSON null: no child exists, so `#> ` returns SQL NULL.

### 10.4. Do not interpret every SQL NULL from #> as a deleted field

An SQL NULL output can result from:

- An SQL NULL document.
- Incompatible root type.
- A missing key anywhere along the path.
- An intermediate value that is not a traversable object/array.
- An out-of-bounds array index.

If an API must report exact causes, inspect each level rather than checking only `#> ... IS NULL`.

## 11. Separating two questions: is the field present, and what is its value?

For any object, two independent questions exist:

1. **Was the field provided?**
2. **If so, what is its type and value?**

A clear inspection query:

```sql
SELECT
    id,
    doc ? 'email' AS email_present,
    jsonb_typeof(doc -> 'email') AS email_type,
    doc ->> 'email' AS email_text
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
ORDER BY id;
```

Cases:

| Data | `email_present` | `email_type` | `email_text` |
| --- | --- | --- | --- |
| `{}` | FALSE | SQL NULL | SQL NULL |
| `{"email":null}` | TRUE | Text `null` | SQL NULL |
| `{"email":"null"}` | TRUE | Text `string` | Text `null` |
| `{"email":""}` | TRUE | Text `string` | Empty string |
| `{"email":false}` | TRUE | Text `boolean` | Text `false` |

Displaying **all three attributes** prevents code-review and debugging errors like “seeing NULL in the text column and assuming the sender explicitly transmitted JSON null.”

### 11.1. Using CASE with explicit check ordering

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL THEN 'DOCUMENT_SQL_NULL'
        WHEN jsonb_typeof(doc) = 'null'
            THEN 'DOCUMENT_JSON_NULL'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'DOCUMENT_NOT_OBJECT'
        WHEN NOT (doc ? 'email')
            THEN 'EMAIL_MISSING'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'EMAIL_JSON_NULL'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
            THEN 'EMAIL_STRING'
        ELSE 'EMAIL_OTHER_JSON_TYPE'
    END AS classification
FROM json_null_lab.documents
ORDER BY id;
```

These status labels are invented for **application semantics**, not built-in PostgreSQL enums.

### 11.2. When you only want objects with a non-NULL email

```sql
SELECT id, doc ->> 'email' AS email
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'string';
```

Note this still returns empty strings or `"null"` because they are JSON strings. If valid email addresses are required, validate emptiness, format, and normalization separately. Checking JSON type **is not** email format validation.

## 12. JSON arrays: null element vs. non-existent index

Objects use keys; arrays use positions. Given:

```json
[null, "null", 0, false]
```

the array has **four elements**, with JSON null at index 0.

### 12.1. Indexing access

```sql
SELECT
    '[null,"null",0,false]'::jsonb -> 0 AS first_json,
    '[null,"null",0,false]'::jsonb -> 1 AS second_json,
    '[null,"null",0,false]'::jsonb -> 10 AS outside_json;
```

Result:

- `-> 0`: JSONB null.
- `-> 1`: JSONB string `"null"`.
- `-> 10`: SQL NULL because the index is out of range.

### 12.2. ->> erases the difference on arrays too

```sql
SELECT
    '[null]'::jsonb ->> 0 AS present_json_null,
    '[null]'::jsonb ->> 5 AS missing_index,
    '["null"]'::jsonb ->> 0 AS string_null;
```

The first two return SQL NULL; the last returns SQL text `null`.

### 12.3. Empty arrays vs. arrays containing only JSON null

```sql
SELECT
    jsonb_array_length('[]'::jsonb) AS empty_length,
    jsonb_array_length('[null]'::jsonb) AS one_null_length,
    jsonb_array_length('[null,null]'::jsonb)
        AS two_null_length;
```

Results are **0, 1, 2**. JSON null is still an **existing indexed element**; never treat it as “missing” when measuring array length.

### 12.4. Negative indexes

PostgreSQL allows negative indexes on JSON arrays counting backward from the end:

```sql
SELECT
    '[1,2,null]'::jsonb -> -1 AS last_json,
    '[1,2,null]'::jsonb -> -4 AS outside_json;
```

`-> -1` returns the trailing JSON null; `-> -4` returns SQL NULL as out of bounds. Remember this is PostgreSQL's JSON indexing behavior—**never assume native SQL arrays work the same way**.

### 12.5. Native SQL arrays and JSON arrays are distinct types

```sql
SELECT
    ARRAY[NULL::integer, 7] AS native_sql_array,
    '[null,7]'::jsonb AS json_array;
```

`ARRAY[NULL::integer,7]` is a **native SQL integer array** containing an SQL NULL element; `'[null,7]'::jsonb` is a **JSONB array** containing JSON null. Both look conceptually similar yet use different operators, indexing, type checks, and conversions.

### 12.6. Do not call jsonb_array_length blindly on objects

`jsonb_array_length` expects a JSONB array. Calling it on objects or incompatible scalars throws an error instead of returning 0 or SQL NULL.

When input shapes are unverified, guard with:

```sql
SELECT id,
       CASE
           WHEN jsonb_typeof(doc) = 'array'
               THEN jsonb_array_length(doc)
           ELSE NULL
       END AS array_length_or_sql_null
FROM json_null_lab.documents
ORDER BY id;
```

`CASE` avoids invoking the function on non-arrays; JSON null elements still count toward array length.

## 13. SQL three-valued logic: TRUE, FALSE, and UNKNOWN

SQL evaluates boolean expressions using three-valued logic: **TRUE**, **FALSE**, and **UNKNOWN** (represented by NULL). That is why comparing SQL NULL to a value never evaluates to FALSE.

### 13.1. Comparing with SQL NULL

```sql
SELECT
    NULL::jsonb = 'null'::jsonb AS compare_equal,
    NULL::jsonb <> 'null'::jsonb AS compare_not_equal,
    NULL::jsonb IS NULL AS sql_null_check;
```

The first two comparisons return SQL NULL/UNKNOWN; the third returns TRUE.

For JSON null (**not** SQL NULL), standard `jsonb` comparisons return TRUE/FALSE:

```sql
SELECT
    'null'::jsonb = 'null'::jsonb AS both_json_null,
    '"null"'::jsonb = 'null'::jsonb AS string_vs_null,
    'false'::jsonb = 'null'::jsonb AS boolean_vs_null;
```

Returns TRUE, FALSE, FALSE.

### 13.2. WHERE keeps only rows evaluating to TRUE

Consider:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc -> 'email' <> 'null'::jsonb;
```

This is **not** “every document except those where email is JSON null.” When `email` is missing or `doc` is SQL NULL, `doc -> 'email'` is SQL NULL; `<>` returns UNKNOWN, so the row is excluded.

To select **every object where email exists and is not JSON null**:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND doc -> 'email' <> 'null'::jsonb;
```

To select objects where **email is missing or non-null JSON**:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND (
      NOT (doc ? 'email')
      OR doc -> 'email' <> 'null'::jsonb
  );
```

Each query answers a distinct question; there is no universal one-size-fits-all “exclude null” condition.

### 13.3. AND, OR, and UNKNOWN

Key truth-table outcomes:

| Logical expression | Result |
| --- | --- |
| TRUE AND UNKNOWN | UNKNOWN |
| FALSE AND UNKNOWN | FALSE |
| TRUE OR UNKNOWN | TRUE |
| FALSE OR UNKNOWN | UNKNOWN |
| NOT UNKNOWN | UNKNOWN |

Hence `WHERE (doc->>'email' = 'a@example.com') OR FALSE` skips missing/JSON-null rows, whereas `OR TRUE` selects all rows. This is standard SQL logic, not JSONB-specific.

### 13.4. IS DISTINCT FROM for NULL-safe comparisons

`IS DISTINCT FROM` treats SQL NULL as a comparable value, returning boolean TRUE/FALSE instead of UNKNOWN:

```sql
SELECT
    NULL::jsonb IS DISTINCT FROM 'null'::jsonb
        AS sql_vs_json_null,
    NULL::jsonb IS NOT DISTINCT FROM NULL::jsonb
        AS two_sql_nulls,
    'null'::jsonb IS NOT DISTINCT FROM 'null'::jsonb
        AS two_json_nulls;
```

All three return TRUE.

Testing an extracted value:

```sql
SELECT
    id,
    doc -> 'email' IS DISTINCT FROM 'null'::jsonb
        AS differs_from_json_null
FROM json_null_lab.documents
ORDER BY id;
```

This returns TRUE **both when email is missing** (since SQL NULL differs from JSONB null) and when `email` is any non-null JSON value; it does not check whether the key exists.

### 13.5. IS NULL behaves differently on JSON vs. text extractions

```sql
SELECT
    ('{"k":null}'::jsonb -> 'k') IS NULL
        AS json_extraction_is_sql_null,
    ('{"k":null}'::jsonb ->> 'k') IS NULL
        AS text_extraction_is_sql_null;
```

Returns FALSE, TRUE.

**This quick test is invaluable whenever reviewing SQL queries that inspect JSON.**

## 14. COALESCE: convenient, yet easy to erase distinctions

`COALESCE(x, default)` returns the first argument that is **not SQL NULL**. It **does not treat JSONB null as SQL NULL**.

### 14.1. COALESCE with -> preserves JSON null

```sql
SELECT
    COALESCE(
        '{"email":null}'::jsonb -> 'email',
        '"fallback"'::jsonb
    ) AS json_null_preserved,
    COALESCE(
        '{}'::jsonb -> 'email',
        '"fallback"'::jsonb
    ) AS missing_replaced;
```

Result:

- `json_null_preserved` = JSONB null.
- `missing_replaced` = JSONB string `"fallback"`.

Because JSONB null is **present**, `COALESCE` leaves it untouched.

### 14.2. COALESCE with ->> falls back on both missing and JSON null

```sql
SELECT
    COALESCE(
        '{"email":null}'::jsonb ->> 'email',
        '<fallback>'
    ) AS json_null_fallback,
    COALESCE(
        '{}'::jsonb ->> 'email',
        '<fallback>'
    ) AS missing_fallback;
```

Both return text `<fallback>`. Persisting that output **destroys whether the field was ever sent**.

### 14.3. Never apply COALESCE before finalizing business rules

An example statement:

```sql
UPDATE customer_profiles
SET email = COALESCE(
    :payload::jsonb ->> 'email',
    email
);
```

is shown **for illustration only** (do not run without the table/bind parameters). It encodes “if email is missing or JSON null, keep the existing email,” **preventing** callers from clearing email by sending JSON null.

If the requirement is:

- Missing → keep unchanged.
- JSON null → clear to SQL NULL.
- JSON string → update text.

then check key presence first and handle JSON null explicitly.

### 14.4. COALESCE and the string "null"

`{"email":"null"}` extracted via `->>` produces SQL text `null`, which **is not SQL NULL**, so `COALESCE` **does not** replace it with the fallback.

Avoid writing `NULLIF(email_text,'null')` unless your domain truly defines the literal `"null"` as a special sentinel. Otherwise you risk corrupting legitimate text data.

## 15. Full classification with CASE before normalizing

To retain all three states cleanly, classify first:

```sql
SELECT
    id,
    CASE
        WHEN doc IS NULL
            THEN 'SQL_NULL_DOCUMENT'
        WHEN jsonb_typeof(doc) <> 'object'
            THEN 'NOT_AN_OBJECT'
        WHEN NOT (doc ? 'email')
            THEN 'MISSING'
        WHEN jsonb_typeof(doc -> 'email') = 'null'
            THEN 'JSON_NULL'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
             AND doc ->> 'email' = ''
            THEN 'EMPTY_STRING'
        WHEN jsonb_typeof(doc -> 'email') = 'string'
            THEN 'STRING'
        ELSE 'OTHER_JSON_VALUE'
    END AS email_state,
    doc ->> 'email' AS email_as_text
FROM json_null_lab.documents
ORDER BY id;
```

### 15.1. Outcome breakdown

| ID | Expected state |
| ---: | --- |
| 1 | `SQL_NULL_DOCUMENT` |
| 2 | `NOT_AN_OBJECT` |
| 3 | `MISSING` |
| 4 | `JSON_NULL` |
| 5 | `STRING` |
| 6 | `EMPTY_STRING` |
| 7 | `STRING` |
| 8 | `OTHER_JSON_VALUE` |
| 9–12 | `MISSING` because `email` is absent at top level |
| 13–16 | `NOT_AN_OBJECT` |
| 17–18 | `OTHER_JSON_VALUE` |

When classifying **top-level email**, objects containing `profile.email` without a top-level `email` are rightly `MISSING`. Use the nested path if your domain checks `profile.email`.

### 15.2. Why CASE pays off

- Makes branch priority explicit.
- Independent of how SQL GUI tools render NULLs.
- Simplifies testing API inputs.
- Prevents accidentally conflating states inside `COALESCE`.
- Supports deliberate mapping to application types.

### 15.3. Distinguishing “has a value” from “is valid”

If `email` is `0` or `{}`, it **is present and not JSON null**, yet still not a valid email address. Presence/nullness checks never replace format, length, Unicode, or domain validation.

## 16. jsonb_each and jsonb_each_text: expanding an object into rows

PostgreSQL lets you iterate over key/value pairs of a JSONB object:

```sql
SELECT key, value, jsonb_typeof(value) AS json_type
FROM jsonb_each(
    '{"a":null,"b":"null","c":false}'::jsonb
)
ORDER BY key;
```

Logical output:

| key | value (JSONB) | json_type |
| --- | --- | --- |
| `a` | JSON null | Text `null` |
| `b` | JSON string `"null"` | Text `string` |
| `c` | JSON boolean false | Text `boolean` |

### 16.1. Missing keys emit zero rows

`jsonb_each('{}'::jsonb)` returns **0 rows**, not a row with `key=NULL` and `value=NULL`. That cleanly separates:

- Key exists with JSON null → emits a row with `value` = JSONB null.
- Key is missing → emits no row.

### 16.2. jsonb_each_text converts JSON null to SQL NULL

```sql
SELECT key, value, value IS NULL AS is_sql_null
FROM jsonb_each_text(
    '{"a":null,"b":"null"}'::jsonb
)
ORDER BY key;
```

For `a`, `value` is SQL NULL. For `b`, `value` is SQL text `null`. While `jsonb_each_text` still preserves **key presence** via row emission, the text `value` column loses original JSON type distinctions.

### 16.3. When doc might not be an object

`jsonb_each` requires an object root; calling it directly on a JSON array or scalar throws an error. A safe demonstration:

```sql
SELECT
    d.id,
    p.key,
    p.value,
    jsonb_typeof(p.value) AS value_type
FROM json_null_lab.documents AS d
LEFT JOIN LATERAL jsonb_each(
    CASE
        WHEN jsonb_typeof(d.doc) = 'object'
            THEN d.doc
        ELSE '{}'::jsonb
    END
) AS p(key, value)
    ON TRUE
ORDER BY d.id, p.key;
```

With `LEFT JOIN LATERAL`, documents with zero keys emit a **padding row** where `p.key` and `p.value` are SQL NULL. Never misinterpret that padding row as a real key holding JSON null; check `p.key IS NOT NULL` to identify real rows from `jsonb_each`.

### 16.4. When should you expand an object?

Expanding key/value pairs is useful for:

- Auditing which fields were supplied.
- Enforcing allowlists of permitted keys.
- Reporting statistics on JSON field presence.
- Flattening JSON objects into relational rows in ETL pipelines.

However, if JSON documents are huge and queries scan millions of rows, expanding every key burns CPU and memory. When only one field matters, `?`/`->` is much simpler.

## 17. JSONPath: path existence vs. path value

Since PostgreSQL 12, SQL/JSON path functions/operators allow querying nested paths in JSONB. A direct existence check:

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email'
    ) AS present_null,
    jsonb_path_exists(
        '{}'::jsonb,
        '$.email'
    ) AS missing;
```

Returns TRUE and FALSE. **The path exists** even when its terminal value is JSON null.

### 17.1. Testing for JSON null with a JSONPath filter

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email ? (@ == null)'
    ) AS explicit_null,
    jsonb_path_exists(
        '{}'::jsonb,
        '$.email ? (@ == null)'
    ) AS missing_null;
```

Returns TRUE and FALSE. Notice `@ == null` is a **JSONPath comparison with JSON null**, not SQL `= NULL`.

### 17.2. JSONPath on nested paths

```sql
SELECT
    id,
    jsonb_path_exists(
        doc,
        '$.profile.email'
    ) AS nested_email_present,
    jsonb_path_exists(
        doc,
        '$.profile.email ? (@ == null)'
    ) AS nested_email_json_null
FROM json_null_lab.documents
WHERE id IN (9, 10, 11, 12)
ORDER BY id;
```

With lab data:

- ID 9: `profile` is `{}` → nested `email` does not exist.
- ID 10: nested `email` exists with JSON null.
- ID 11: `profile` is JSON null, no child `email` to resolve.
- ID 12: nested `email` exists as a string.

### 17.3. SQL NULL documents with JSONPath

Passing `NULL::jsonb` into `jsonb_path_exists` returns SQL NULL due to strict NULL handling, not boolean FALSE. If your domain treats an SQL NULL document as lacking the path, apply an explicit policy such as `COALESCE(jsonb_path_exists(doc,'$.email'),FALSE)`.

### 17.4. Lax vs. strict path evaluation

PostgreSQL JSONPath defaults to **lax** mode and offers a **strict** mode with different structural error handling. Default lax mode quietly suppresses or unwraps certain structural mismatches.

If you need tight schema validation, never rely solely on a lax path expression to prove an object or array matches your schema. Verify `jsonb_typeof` at required levels or opt into `strict` behavior deliberately.

### 17.5. @? and @@ have different meanings

PostgreSQL provides JSONPath operators `@?` and `@@`:

- `@?`: does the JSONPath return any matching item?
- `@@`: evaluates a JSONPath predicate expression.

They are not interchangeable across all expressions. Testing path existence:

```sql
SELECT
    '{"email":null}'::jsonb @? '$.email'
        AS has_email_path,
    '{}'::jsonb @? '$.email'
        AS no_email_path;
```

Returns TRUE and FALSE here.

### 17.6. When should you use JSONPath?

For a single top-level key, `doc ? 'email'` is usually easier to read. JSONPath shines with deeply nested objects or complex arrays when checking “does any deep element match a filter” alongside compatible operators/GIN indexes.

Pick the simplest construct expressing your semantics rather than turning every simple email check into a long JSONPath string.

## 18. jsonb_to_record and jsonb_populate_record: turning JSON into SQL columns

When converting JSON into a typed SQL record, JSON null becomes **SQL NULL** in the target column.

### 18.1. Two payloads yielding identical typed output

```sql
SELECT *
FROM jsonb_to_record(
    '{"email":null}'::jsonb
) AS x(email text);

SELECT *
FROM jsonb_to_record(
    '{}'::jsonb
) AS x(email text);
```

Both produce `email` = **SQL NULL**. One payload supplied an explicit JSON null while the other omitted the field. Once projected into a plain nullable column, **the presence bit is gone**.

### 18.2. Preserving presence separately first

```sql
SELECT
    d.id,
    d.doc ? 'email' AS email_was_provided,
    x.email
FROM json_null_lab.documents AS d
CROSS JOIN LATERAL jsonb_to_record(
    CASE
        WHEN jsonb_typeof(d.doc) = 'object'
            THEN d.doc
        ELSE '{}'::jsonb
    END
) AS x(email text)
WHERE d.id IN (3, 4, 5, 6, 7)
ORDER BY d.id;
```

Now:

- `email_was_provided=FALSE`, `x.email=SQL NULL` → missing.
- `email_was_provided=TRUE`, `x.email=SQL NULL` → explicit JSON null.
- `email_was_provided=TRUE`, `x.email='null'` → JSON string literal `"null"`.

### 18.3. jsonb_populate_record with a base record

`jsonb_populate_record(base, jsonb)` has important semantics: values present in JSON map to typed columns, and JSON null maps to SQL NULL. For **omitted fields**, values from the `base` record are preserved if a non-null `base` row is supplied; if `base` is an SQL NULL record, missing fields become SQL NULL.

Thus using `jsonb_populate_record` for updates can behave differently from writing `doc ->> ...` field by field. Clarify whether missing should keep old values or become NULL.

### 18.4. Type conversion is not full validation

JSON strings, numbers, booleans, or objects convert to SQL types under PostgreSQL casting/coercion rules, raising errors on incompatible input. Validate JSON types and domain formats before assuming `jsonb_to_record` handles arbitrary payloads safely.

In particular, landing cleanly in a `text` column never proves a string is a valid email address.

## 19. Updating JSONB: setting null is not deleting a key

Given an existing document:

```json
{"email":"old@example.com","active":true}
```

there are at least three distinct updates:

1. Change `email` to a new string.
2. Keep the `email` key while changing its value to **JSON null**.
3. **Delete the `email` key** from the object.

PostgreSQL has distinct functions and operators for each.

### 19.1. Setting a key to JSON null with jsonb_set

```sql
SELECT jsonb_set(
    '{"email":"old@example.com","active":true}'::jsonb,
    '{email}',
    'null'::jsonb,
    true
) AS result;
```

Equivalent result:

```json
{"active": true, "email": null}
```

The `email` key **still exists**. Key display order in `jsonb` is not semantically significant and may differ from the example.

### 19.2. Deleting a key with the - operator

```sql
SELECT
    '{"email":"old@example.com","active":true}'::jsonb
        - 'email' AS result;
```

Result:

```json
{"active": true}
```

The `- 'email'` operator on a JSONB object removes the **top-level** key entirely rather than setting it to JSON null.

### 19.3. Setting a missing field to JSON null

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{email}',
    'null'::jsonb,
    true
) AS result;
```

Result: `{"email":null}`. The final `true` parameter allows creating the target leaf key if missing.

With `false`:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{email}',
    'null'::jsonb,
    false
) AS result;
```

Result remains `{}` because the leaf field did not exist and creation was disallowed.

### 19.4. Beware passing SQL NULL as new_value

```sql
SELECT jsonb_set(
    '{"email":"old@example.com"}'::jsonb,
    '{email}',
    NULL::jsonb,
    true
) AS result;
```

In `jsonb_set`, **an SQL NULL `new_value`** does not mean JSON null; strict NULL propagation causes the entire function call to return **SQL NULL**, rather than an object with `"email": null`.

Using that expression to update a `doc jsonb NOT NULL` column fails with a constraint violation, or silently wipes out the whole document if nullable! When you want JSON null, pass **`'null'::jsonb`**.

### 19.5. Nested paths and missing intermediate objects

```sql
SELECT jsonb_set(
    '{"profile":{"email":"old@example.com"}}'::jsonb,
    '{profile,email}',
    'null'::jsonb,
    true
) AS result;
```

Sets `profile.email` to JSON null.

However:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{profile,email}',
    '"new@example.com"'::jsonb,
    true
) AS result;
```

does **not** automatically create missing **intermediate objects**. When intermediate segments do not exist, PostgreSQL leaves the target unchanged rather than scaffolding `profile`.

If you need to create nested keys from scratch, construct missing parent objects explicitly and account for cases where the parent is currently scalar or JSON null.

## 20. jsonb_set_lax: explicit control over SQL NULL new_value

Added in PostgreSQL 13, `jsonb_set_lax` extends `jsonb_set` with an explicit policy whenever `new_value` is **SQL NULL**.

### 20.1. Common modes

On a JSONB object:

```sql
SELECT
    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'use_json_null'
    ) AS set_json_null,

    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'delete_key'
    ) AS remove_key,

    jsonb_set_lax(
        '{"email":"old@example.com"}'::jsonb,
        '{email}',
        NULL::jsonb,
        true,
        'return_target'
    ) AS unchanged;
```

Respective outcomes:

| Mode | Effect |
| --- | --- |
| `use_json_null` | Key `email` is set to JSON null. |
| `delete_key` | Key `email` is removed. |
| `return_target` | Target stays unchanged. |
| `raise_exception` | Throws an error when `new_value` is SQL NULL. |

### 20.2. Key distinction

- `jsonb_set(..., 'null'::jsonb)`: `new_value` is **JSON null**, performing a normal JSON-value update.
- `jsonb_set_lax(..., NULL::jsonb, ..., 'use_json_null')`: `new_value` is **SQL NULL**, explicitly converted into JSON null.
- `jsonb_set_lax(..., NULL::jsonb, ..., 'delete_key')`: `new_value` is **SQL NULL**, explicitly interpreted as a key-deletion request.

`jsonb_set_lax` does not guess your intent; you choose the mode explicitly. When `new_value` is **not SQL NULL**, it behaves like `jsonb_set` regardless of mode.

### 20.3. Do not use on unsupported versions

Servers older than PostgreSQL 13 lack `jsonb_set_lax`. On older versions, use `CASE` combined with `jsonb_set`/`-`/`#-` rather than assuming every version supports it.

## 21. Deleting nested paths with #- and stripping JSON nulls with jsonb_strip_nulls

### 21.1. Deleting a nested key

```sql
SELECT
    '{"profile":{"email":null,"phone":"123"},"active":true}'::jsonb
        #- '{profile,email}' AS result;
```

Result:

```json
{"active": true, "profile": {"phone": "123"}}
```

`#-` deletes the value at the specified path, complementing `#>` for extraction.

### 21.2. jsonb_strip_nulls

PostgreSQL provides a function to strip **object fields holding JSON null**:

```sql
SELECT jsonb_strip_nulls(
    '{"email":null,"profile":{"phone":null,"name":"Lan"},"items":[null,1]}'::jsonb
) AS result;
```

In its standard single-argument form, the output means:

```json
{"profile":{"name":"Lan"},"items":[null,1]}
```

It strips null-valued fields from objects—including nested objects—while **leaving JSON nulls inside arrays intact by default**. Newer major versions add optional arguments controlling array behavior; consult your version's docs before relying on them.

### 21.3. Top-level JSON null case

`jsonb_strip_nulls('null'::jsonb)` does not turn a root JSON scalar null into SQL NULL or `{}`. Its job is deleting **object key/value pairs** whose values are JSON null.

### 21.4. Be careful when normalizing inbound payloads

If a system runs `jsonb_strip_nulls` **immediately upon receiving an API payload**:

```json
{"email":null}
```

turns into:

```json
{}
```

erasing the distinction between “client explicitly sent JSON null” and “client omitted `email`.” Strip nulls only when your **confirmed business rules** require it.

## 22. COUNT, COUNT(*), DISTINCT, and aggregates with JSON null

A subtle class of bugs arises when counting present elements.

### 22.1. COUNT skips SQL NULL, not JSONB null

In PostgreSQL:

- `COUNT(*)` counts every input row.
- `COUNT(expression)` counts rows where `expression` is **not SQL NULL**.

On `doc`:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(doc) AS non_sql_null_documents
FROM json_null_lab.documents;
```

Across all 18 rows: `COUNT(*)=18` and `COUNT(doc)=17`, because only `id=1` is an SQL NULL document. **ID=2 is JSON null and is still counted by `COUNT(doc)`**.

### 22.2. COUNT with -> differs from COUNT with ->>

```sql
SELECT
    COUNT(doc -> 'email') AS json_value_count,
    COUNT(doc ->> 'email') AS text_value_count
FROM json_null_lab.documents;
```

On the unmodified lab table:

- `COUNT(doc -> 'email')=7`: ids 4, 5, 6, 7, 8, 17, 18 all have a top-level `email` key; **JSON null id=4 is counted**.
- `COUNT(doc ->> 'email')=6`: all of the above except id=4, because `->>` converts JSON null to SQL NULL.

These two `COUNT`s answer different questions:

1. How many rows yield a non-SQL-NULL **JSON value** via `->`?
2. How many rows yield a non-SQL-NULL **text representation**?

### 22.3. Counting presence using ? and an object check

```sql
SELECT
    COUNT(*) FILTER (
        WHERE jsonb_typeof(doc) = 'object'
          AND doc ? 'email'
    ) AS email_field_present,
    COUNT(*) FILTER (
        WHERE jsonb_typeof(doc) = 'object'
          AND jsonb_typeof(doc -> 'email') = 'null'
    ) AS email_explicit_json_null
FROM json_null_lab.documents;
```

With lab data, this yields 7 and 1.

### 22.4. COUNT(DISTINCT ...) cannot recover missingness

```sql
SELECT COUNT(DISTINCT doc -> 'email')
FROM json_null_lab.documents;
```

The aggregate drops SQL NULLs while distinguishing JSONB null from JSON string `"null"`. However, both missing keys and SQL NULL documents have already collapsed into SQL NULL on the expression and cannot be separated afterward.

### 22.5. JSON builders can collapse distinctions too

When serializing SQL data into JSON via builder functions, SQL NULL **may be serialized as JSON null** inside the resulting object/array. If consumers must distinguish “field not provided” from “field provided with null,” track presence metadata separately or omit absent keys explicitly during serialization.

Never assume seeing `null` in a JSON response proves the source held JSON null rather than SQL NULL.

## 23. Building JSON from SQL: null in the output hides its origin

Example:

```sql
SELECT
    jsonb_build_object(
        'email', NULL::text
    ) AS from_sql_null,
    jsonb_build_object(
        'email', 'null'::jsonb
    ) AS from_json_null,
    jsonb_build_object(
        'email', 'null'::text
    ) AS from_text_null;
```

Respective outputs:

```json
{"email":null}
```

```json
{"email":null}
```

```json
{"email":"null"}
```

The first two produce **identical JSON**, even though their inputs were SQL NULL and JSON null. Once serialized both ways into `{"email":null}`, source origin is lost and cannot be inferred backward from the output.

### 23.1. Omitting missing keys is an application decision

Conditional construction example:

```sql
SELECT
    CASE
        WHEN TRUE
            THEN jsonb_build_object('email', 'a@example.com')
        ELSE '{}'::jsonb
    END AS object_with_email;
```

This `CASE` simply illustrates structure: when a field was not supplied, you can emit `{}` instead of `{"email":null}`. Drive that condition from stored **presence** metadata rather than guessing from a nullable `->>` text value.

### 23.2. Preserving output shape

If clients need to distinguish “absent field” from “explicit null,” design a consistent response contract. Two common strategies:

- Preserve the full JSONB object including key presence when returning documents.
- Return typed columns alongside presence metadata for supplied fields.

Avoid stripping all nulls indiscriminately on outbound responses if clients rely on explicit `null` to display states like “unverified.”

## 24. SQL NULL vs. JSON null columns in INSERT/UPDATE

A `jsonb` column can receive either:

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (19, 'Explicit SQL NULL', NULL::jsonb),
    (20, 'Explicit JSON null', 'null'::jsonb);
```

Both rows remain distinct:

```sql
SELECT
    id,
    doc IS NULL AS sql_null,
    doc = 'null'::jsonb AS json_null
FROM json_null_lab.documents
WHERE id IN (19, 20);
```

This step is **optional**; running it changes the row counts in Section 22 from 18 rows. To experiment without altering the dataset:

```sql
BEGIN;

INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (21, 'SQL NULL within transaction', NULL::jsonb),
    (22, 'JSON null within transaction', 'null'::jsonb);

SELECT
    id,
    doc IS NULL AS is_sql_null,
    jsonb_typeof(doc) AS json_type
FROM json_null_lab.documents
WHERE id IN (21, 22);

ROLLBACK;
```

To keep the lab dataset at exactly 18 rows, **run only the `BEGIN`/`ROLLBACK` version** and skip inserting rows 19–20 permanently.

### 24.1. NOT NULL does not forbid JSON null

```sql
CREATE TABLE json_null_lab.required_docs (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL
);

INSERT INTO json_null_lab.required_docs (id, doc)
VALUES (1, 'null'::jsonb);
```

This succeeds. `NOT NULL` forbids **SQL NULL**, not JSON scalar null. If a column must always store a JSON object, add a `CHECK` constraint on `jsonb_typeof(doc)`.

### 24.2. DEFAULT '{}' does not replace incoming JSON null

```sql
CREATE TABLE json_null_lab.default_docs (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL DEFAULT '{}'::jsonb
);

INSERT INTO json_null_lab.default_docs (id)
VALUES (1);

INSERT INTO json_null_lab.default_docs (id, doc)
VALUES (2, 'null'::jsonb);
```

Row `id=1` receives `{}` from the default; `id=2` receives JSON null because the client **supplied a value**. `DEFAULT` neither replaces an explicit JSON null with `{}` nor overrides an explicit SQL NULL on a `NOT NULL` column (which errors).

## 25. CHECK constraints: how UNKNOWN lets bad rows slip through

In PostgreSQL, a `CHECK` constraint accepts a row when the expression evaluates to SQL NULL/UNKNOWN; it only rejects rows when the expression evaluates to **FALSE**. This explains why many seemingly reasonable JSON constraints turn out to be leaky.

### 25.1. Broken constraint: checking only non-empty text

Example:

```sql
CREATE TABLE json_null_lab.bad_profiles (
    id integer PRIMARY KEY,
    doc jsonb,
    CHECK (doc ->> 'email' <> '')
);
```

This constraint **does not ensure `email` exists**. When `doc='{}'::jsonb` or `doc='{"email":null}'::jsonb`:

- `doc ->> 'email'` is SQL NULL.
- `SQL_NULL <> ''` evaluates to UNKNOWN.
- `CHECK` **accepts the row** because the result is not FALSE.

Nor does it forbid an SQL NULL document unless paired with `NOT NULL`.

### 25.2. Explicit constraint for a required non-empty email

```sql
CREATE TABLE json_null_lab.validated_profiles (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT ck_document_is_object
        CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT ck_email_required_string
        CHECK (
            doc ? 'email'
            AND jsonb_typeof(doc -> 'email') = 'string'
            AND length(doc ->> 'email') > 0
        )
);
```

Here:

1. `NOT NULL` forbids SQL NULL documents.
2. Object constraint forbids JSON null documents, arrays, and scalars.
3. `doc ? 'email'` requires the key to exist.
4. `jsonb_typeof(...) = 'string'` forbids JSON null, numbers, booleans, and objects.
5. `length(...) > 0` forbids empty strings.

Real email validation still needs domain-appropriate format checks; this SQL constraint focuses on separating structural states.

### 25.3. Optional email that must be a string or JSON null when present

```sql
CREATE TABLE json_null_lab.optional_profiles (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT ck_optional_doc_object
        CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT ck_optional_email_type
        CHECK (
            NOT (doc ? 'email')
            OR jsonb_typeof(doc -> 'email')
                IN ('string', 'null')
        )
);
```

This permits:

- `{}` — missing email.
- `{"email":null}` — JSON null allowed.
- `{"email":"a@example.com"}` — string allowed.

And rejects `{"email":false}` or `{"email":0}` without making `email` mandatory.

### 25.4. Testing a few INSERTs

```sql
INSERT INTO json_null_lab.optional_profiles (id, doc)
VALUES
    (1, '{}'::jsonb),
    (2, '{"email":null}'::jsonb),
    (3, '{"email":"a@example.com"}'::jsonb);
```

Trying a boolean:

```sql
-- Expected to violate CHECK; do not run inside an active
-- transaction doing other work:
-- INSERT INTO json_null_lab.optional_profiles
-- VALUES (4, '{"email":false}'::jsonb);
```

### 25.5. Do not trust CHECK based solely on IS NOT NULL

`CHECK ((doc->>'email') IS NOT NULL)` rejects missing keys and JSON null, yet **still allows non-string types**. JSON boolean `false` and JSON number `0` both extract to non-NULL text. Whenever schema correctness matters, check `jsonb_typeof` as well.

## 26. Indexing across the three states

Frequent JSON queries need indexes, yet **indexes must match the query semantics**.

### 26.1. Expression index on extracted text

```sql
CREATE INDEX idx_documents_email_text
ON json_null_lab.documents
    ((doc ->> 'email'));
```

This helps queries like:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc ->> 'email' = 'a@example.com';
```

However, `doc ->> 'email'` evaluates to SQL NULL for all of:

- JSON null `email`.
- Missing `email`.
- SQL NULL document.

If your query must tell those three states apart, **a text-extraction expression index preserves no key-presence distinction**.

### 26.2. GIN for top-level key existence

```sql
CREATE INDEX idx_documents_jsonb_gin_ops
ON json_null_lab.documents
USING GIN (doc jsonb_ops);
```

The query:

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc ? 'email';
```

can leverage GIN operator class `jsonb_ops` when table size and selectivity justify it. Do not expect an Index Scan on the 18-row lab table; Seq Scan is faster there.

### 26.3. Partial index for explicit JSON null

```sql
CREATE INDEX idx_documents_email_json_null
ON json_null_lab.documents (id)
WHERE jsonb_typeof(doc -> 'email') = 'null';
```

This indexes only rows where the predicate holds TRUE. Queries sharing that exact predicate can benefit once tables grow large and the planner matches the partial index condition.

Never create separate indexes for every `email` state variation in production without proving query frequency and measurable gains.

### 26.4. jsonb_path_ops and key existence

GIN `jsonb_path_ops` is compact and fast for certain containment and JSONPath queries, yet **does not support the `?` operator** the way `jsonb_ops` does. If hot workloads check “does key exist?”, never choose `jsonb_path_ops` solely for smaller index size at the expense of operator support.

### 26.5. An index does not unify the three states

Indexes are access paths. Distinguishing SQL NULL, JSON null, and missing resides in your **SQL expressions and output types**. A matching index accelerates a correctly written query; it never rescues a semantically broken one like using `->> IS NULL` to detect “client sent JSON null.”

## 27. PATCH APIs: missing, JSON null, and real values are three distinct requests

Suppose a profile currently stores:

```json
{"email":"old@example.com","displayName":"Lan"}
```

A client sends one of three payloads:

```json
{}
```

```json
{"email":null}
```

```json
{"email":"new@example.com"}
```

An **application-defined** PATCH policy might be:

| Payload | Email update intent |
| --- | --- |
| `{}` | Leave email unchanged. |
| `{"email":null}` | Clear/delete the current email. |
| `{"email":"new@example.com"}` | Set email to the new value. |

This is a widespread convention, yet **not every HTTP PATCH endpoint follows it automatically**. Exact semantics depend on Content-Type and the chosen PATCH protocol.

### 27.1. JSON Merge Patch vs. JSON Patch

Two common standards behave differently:

- **JSON Merge Patch (RFC 7396, `application/merge-patch+json`):** a key set to JSON null generally signals removing that member from the target object, while an omitted key leaves it untouched. This model cannot distinguish “store literal JSON null” from “delete key” using a single plain null marker.
- **JSON Patch (RFC 6902, `application/json-patch+json`):** operations are explicit (`add`, `replace`, `remove`) against target paths. JSON null can be the value of `add`/`replace`, while `remove` is a separate operation.

When an API accepts plain JSON objects in `PATCH /profile` without declaring a standard RFC media type, the team must **explicitly specify and test** missing/null/replace rules.

### 27.2. Never handle PUT identically to PATCH

Under standard REST contracts, `PUT` replaces a resource representation whereas `PATCH` applies partial modifications. Although specific APIs vary, never blindly apply “missing preserves existing value” to `PUT` endpoints without clear API documentation.

### 27.3. Do not extract with ->> too early

If a parser immediately binds the payload into:

```text
email: nullable String
```

then both `{}` and `{"email":null}` map to `email == null`. Once the presence flag is lost, the database layer can no longer tell whether the client asked to clear `email`.

The solution is modeling three states explicitly:

```text
EmailPatch =
    Absent
  | PresentNull
  | PresentString(value)
```

or retaining the JSON tree and inspecting key presence before conversion.

## 28. Example PATCH SQL for a nullable relational column

Create a lab table:

```sql
CREATE TABLE json_null_lab.customer_profiles (
    profile_id integer PRIMARY KEY,
    email text,
    display_name text NOT NULL
);

INSERT INTO json_null_lab.customer_profiles (
    profile_id, email, display_name
)
VALUES (1, 'old@example.com', 'Lan');
```

Requirements:

- Missing `email`: keep `email` unchanged.
- `email` = JSON null: set `email` to SQL NULL.
- `email` = JSON string: update text accordingly.
- `email` = JSON number/boolean/object/array: reject in the API.

### 28.1. UPDATE leaves column unchanged when missing

```sql
BEGIN;

WITH incoming AS (
    SELECT '{}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Within the transaction, `email` stays `old@example.com` because the field was **not supplied**. `ROLLBACK` leaves lab data unchanged.

### 28.2. UPDATE clears email on JSON null

```sql
BEGIN;

WITH incoming AS (
    SELECT '{"email":null}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Within the transaction, `email` becomes **SQL NULL** because `email` was supplied and `->>` turns JSON null into SQL NULL. `ROLLBACK` restores the previous value.

### 28.3. UPDATE with a JSON string

```sql
BEGIN;

WITH incoming AS (
    SELECT '{"email":"new@example.com"}'::jsonb AS patch_doc
)
UPDATE json_null_lab.customer_profiles AS p
SET email =
    CASE
        WHEN incoming.patch_doc ? 'email'
            THEN incoming.patch_doc ->> 'email'
        ELSE p.email
    END
FROM incoming
WHERE p.profile_id = 1
  AND jsonb_typeof(incoming.patch_doc) = 'object'
  AND (
      NOT (incoming.patch_doc ? 'email')
      OR jsonb_typeof(incoming.patch_doc -> 'email')
          IN ('string', 'null')
  )
RETURNING p.profile_id, p.email;

ROLLBACK;
```

Resulting `email` in the transaction is `new@example.com`.

### 28.4. Why does WHERE validate the type?

Without type validation, `{"email":false}` extracted via `->>` turns into SQL text `false` and could be written into `email`. The check restricts present `email` values to JSON string or JSON null.

In a real API, invalid payloads must fail loudly with explicit errors (e.g., HTTP 400/422 per contract) rather than **silently updating 0 rows**. The SQL uses `WHERE` simply to keep the validation sample compact; applications should verify affected row counts and surface validation errors cleanly.

### 28.5. When PATCH updates multiple fields together

Each field needs its own presence tracking:

```text
email:       Absent | PresentNull | PresentString
displayName: Absent | PresentNull | PresentString
preferences: Absent | PresentNull | PresentObject
```

Never collapse all fields into `COALESCE(patch_doc->>field, old_value)` when null and missing carry different meanings. For mandatory fields like `displayName`, JSON null should typically **be rejected** rather than clearing the column.

## 29. Example PATCH SQL for a JSONB column

Suppose the current document is:

```json
{"email":"old@example.com","theme":"dark"}
```

Requirements:

- Missing `email` in patch → keep `email` unchanged.
- `email` = JSON null → store JSON null if business rules permit.
- `email` = JSON string → write the new string.

### 29.1. Keeping JSON null instead of deleting

```sql
SELECT
    CASE
        WHEN patch_doc ? 'email'
            THEN jsonb_set(
                current_doc,
                '{email}',
                patch_doc -> 'email',
                true
            )
        ELSE current_doc
    END AS updated_doc
FROM (
    SELECT
        '{"email":"old@example.com","theme":"dark"}'::jsonb
            AS current_doc,
        '{"email":null}'::jsonb AS patch_doc
) AS input;
```

Result contains `"email":null` while keeping `theme`.

If the patch is `{}`, `CASE` keeps `current_doc` unchanged. Because `patch_doc -> 'email'` returns JSON null (**not** SQL NULL), `jsonb_set` writes JSON null as intended.

### 29.2. Interpreting null as deleting the key

If the API contract defines JSON null as deleting `email`:

```sql
SELECT
    CASE
        WHEN NOT (patch_doc ? 'email')
            THEN current_doc
        WHEN jsonb_typeof(patch_doc -> 'email') = 'null'
            THEN current_doc - 'email'
        ELSE jsonb_set(
            current_doc,
            '{email}',
            patch_doc -> 'email',
            true
        )
    END AS updated_doc
FROM (
    SELECT
        '{"email":"old@example.com","theme":"dark"}'::jsonb
            AS current_doc,
        '{"email":null}'::jsonb AS patch_doc
) AS input;
```

Result leaves only `{"theme":"dark"}`.

### 29.3. Why both examples still need validation

In 29.1 and 29.2, if a client sends `{"email":false}`, boolean `false` gets written directly. If only string/null is allowed, reject invalid types before updating. Also verify:

- Is `patch_doc` SQL NULL?
- Is the root a JSON object?
- Is `current_doc` the expected object shape?
- Does the target record belong to the authorized tenant/user?
- Can concurrent PATCH calls from two clients overwrite each other?

Null/missing semantics are just **one part** of safe update logic.

## 30. Java/JDBC and Jackson: preserving the presence bit

In Java, binding JSON straight into a POJO with plain nullable fields merges missing keys with explicit JSON nulls. Whenever PATCH semantics matter, inspect the JSON tree or map into a three-state DTO.

### 30.1. Jackson JsonNode.get

Java snippet using Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
JsonNode root = mapper.readTree(requestBody);

if (!root.isObject()) {
    throw new IllegalArgumentException(
        "Expected a JSON object"
    );
}

JsonNode email = root.get("email");

if (email == null) {
    // Key "email" is absent from the object.
    // PATCH policy: keep existing email unchanged.
} else if (email.isNull()) {
    // Key "email" is present with JSON null.
    // PATCH policy: clear email (SQL NULL)
    // or remove the JSONB key depending on contract.
} else if (email.isTextual()) {
    String newEmail = email.textValue();
    // Validate and update.
} else {
    throw new IllegalArgumentException(
        "email must be a string or JSON null"
    );
}
```

In Jackson's tree model:

- `get("email")` on an object without the key returns **Java `null`**.
- `get("email")` when the key holds JSON null returns a **`NullNode`**, not Java `null`.
- `isNull()` tests whether the node represents JSON null.
- `isTextual()` tests for a JSON string.

This snippet illustrates request-body handling, not a complete controller or full validation/security layer.

### 30.2. Jackson path and MissingNode

Jackson also provides:

```java
JsonNode emailByPath = root.path("email");

if (emailByPath.isMissingNode()) {
    // Key is absent.
} else if (emailByPath.isNull()) {
    // JSON null was sent.
}
```

`path(...)` represents missing keys using **`MissingNode`** rather than Java `null`. Never conflate `MissingNode` with `NullNode` in any DTO mapping or serialization step if the contract distinguishes them.

### 30.3. JDBC: SQL NULL vs. the JSON string "null"

Example query:

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE id IN (1, 2, 3)
ORDER BY id;
```

Java JDBC consumer:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, doc " +
        "FROM json_null_lab.documents " +
        "WHERE id IN (1, 2, 3) ORDER BY id"
    );
    ResultSet rs = ps.executeQuery()) {

    ObjectMapper mapper = new ObjectMapper();

    while (rs.next()) {
        int id = rs.getInt("id");
        String jsonText = rs.getString("doc");

        if (jsonText == null) {
            // SQL NULL in the doc column.
            System.out.println(id + ": SQL NULL document");
            continue;
        }

        JsonNode docNode = mapper.readTree(jsonText);

        if (docNode.isNull()) {
            // JSON text 'null' from a jsonb document.
            System.out.println(id + ": JSON null document");
        } else if (docNode.isObject()) {
            // Read each field and check presence.
            System.out.println(id + ": JSON object");
        }
    }
}
```

Assuming a valid `connection`, PostgreSQL JDBC driver, Jackson on the classpath, and proper exception handling: `getString` returns Java `null` for SQL NULL, whereas a `'null'::jsonb` document arrives as the four-character text `null`, which Jackson parses into a `NullNode`.

### 30.4. ResultSet.wasNull()

In JDBC, primitive getters such as `getInt` return default primitive values (like `0`) when a column is SQL NULL; call `wasNull()` immediately afterward to detect SQL NULL:

```java
int quantity = rs.getInt("quantity");
boolean sqlNull = rs.wasNull();
```

For `getString("doc")`, Java `null` indicates SQL NULL, though `wasNull()` makes intent explicit if desired. **Never compare the string `"null"` against Java `null` as if they meant the same thing.**

### 30.5. Persisting JSONB via JDBC

When binding JSONB parameters, distinguish:

- SQL NULL parameter: bind SQL NULL with the appropriate SQL type.
- JSON null document: send JSON text `null` cast/bound as `jsonb`.
- Object with a JSON null field: send JSON text `{"email":null}`.
- Object missing the field: send `{}` if that is the desired representation.

Example SQL:

```sql
INSERT INTO json_null_lab.documents
    (id, description, doc)
VALUES
    (1001, 'SQL NULL', NULL::jsonb),
    (1002, 'JSON null', 'null'::jsonb),
    (1003, 'Missing email', '{}'::jsonb),
    (1004, 'Email JSON null', '{"email":null}'::jsonb);
```

This demonstrates semantics; with real `PreparedStatement` code, bind values safely and validate inputs/permissions. Do not execute repeatedly in the lab due to PK collisions; wrap in a transaction and `ROLLBACK` if testing.

## 31. Data pipelines and event processing: missing is not clear

Suppose a CDC/ETL pipeline receives events:

```json
{"entityId":42,"changes":{"phone":null}}
```

and:

```json
{"entityId":42,"changes":{}}
```

Under a **partial-changes** contract:

- The first event asks to clear `phone`.
- The second event leaves `phone` unmentioned.

If the pipeline projects both into a nullable staging column `phone text` without storing presence metadata, downstream consumers cannot tell whether to clear `phone` or keep the prior value.

### 31.1. Staging should preserve raw JSON or presence

Design example:

```sql
CREATE TABLE json_null_lab.change_events (
    event_id bigint PRIMARY KEY,
    entity_id bigint NOT NULL,
    received_at timestamptz NOT NULL
        DEFAULT CURRENT_TIMESTAMP,
    changes jsonb NOT NULL,
    CONSTRAINT ck_changes_object
        CHECK (jsonb_typeof(changes) = 'object')
);
```

Insert:

```sql
INSERT INTO json_null_lab.change_events
    (event_id, entity_id, changes)
VALUES
    (1, 42, '{"phone":null}'::jsonb),
    (2, 42, '{}'::jsonb),
    (3, 42, '{"phone":"0987654321"}'::jsonb);
```

Classify:

```sql
SELECT
    event_id,
    entity_id,
    CASE
        WHEN NOT (changes ? 'phone')
            THEN 'UNCHANGED'
        WHEN jsonb_typeof(changes -> 'phone') = 'null'
            THEN 'CLEAR'
        WHEN jsonb_typeof(changes -> 'phone') = 'string'
            THEN 'SET'
        ELSE 'INVALID_TYPE'
    END AS phone_action,
    changes ->> 'phone' AS phone_value
FROM json_null_lab.change_events
ORDER BY event_id;
```

Actions evaluate to `UNCHANGED`, `CLEAR`, `SET`. While `phone_value` is SQL NULL for both of the first two events, **`phone_action` keeps them distinct**.

### 31.2. Idempotency goes beyond JSON null

A `SET`/`CLEAR` event may be re-delivered. Safe replay requires event IDs or versions, ordering rules, and transactional idempotency checks. JSON field presence captures **intended change**, not deduplication or out-of-order protection.

### 31.3. Audits must preserve initial intent

If an audit log only records “email after update = NULL,” you cannot tell whether:

- The client sent JSON null.
- The client omitted `email` and buggy code overwrote it with NULL.
- Source data was already SQL NULL.
- A staging mapping dropped presence.

For full traceability, log the raw event, present fields, version/actor/timestamp, and processing outcome subject to security policies.

## 32. Querying dirty data and classifying type mismatches

When ingesting JSON from heterogeneous producers, one field may carry unexpected types:

```json
{"price":10}
```

```json
{"price":"10"}
```

```json
{"price":null}
```

```json
{}
```

You cannot rely solely on:

```sql
WHERE doc ->> 'price' IS NOT NULL
```

to assert `price` is a number. That also evaluates TRUE for JSON string `"10"`, boolean `false`, and any other scalar castable to text.

### 32.1. Filtering accurately for JSON numbers

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'number';
```

On the lab dataset, this returns **id=17**. Applying the same logic to `price`: verify key presence and JSON type before casting.

### 32.2. Casting text to numeric can fail

If a JSON string holds `"not-a-number"`:

```sql
-- Never cast without validating first:
-- SELECT (doc ->> 'price')::numeric FROM ...;
```

PostgreSQL throws an invalid input syntax error. Specify whether `price` must be a JSON number or may arrive as a numeric string, and validate before casting. JSON null and missing collapsing to SQL NULL are far from the only hazard.

### 32.3. Invalid JSON documents

The strings below are not valid JSON:

```text
{email:null}        -- Unquoted key
{"email":undefined} -- JSON has no undefined literal
{"email":NaN}       -- Standard JSON forbids bare NaN literals
```

If JavaScript code distinguishes `undefined` from `null`, remember during JSON serialization that **`undefined` is not a JSON literal**. Most serializers omit object keys whose value is `undefined`, causing PostgreSQL to see **missing** rather than JSON null (exact behavior depends on serializer configuration).

### 32.4. Duplicate keys in JSONB

`jsonb` does not retain multiple members sharing the same key name as an ordered list. When parsing a JSON object containing duplicate keys, `jsonb` retains the last occurrence, for example:

```sql
SELECT
    '{"email":null,"email":"new@example.com"}'::jsonb
        AS parsed_document;
```

Result keeps one `email` key holding the later string value. If an API must reject duplicate keys as invalid input, validate at the raw JSON parsing layer before converting to `jsonb`; once stored as `jsonb`, original duplicates are gone.

### 32.5. The special string "null" may be legitimate data

Sometimes `"null"` is genuine user input (such as a product code or surname). Never coerce it to NULL using:

```sql
NULLIF(doc ->> 'code', 'null')
```

unless the source spec explicitly defines `"null"` as a sentinel string requiring normalization. Otherwise you corrupt valid records.

## 33. Decision table: which tool for which question?

| Question / goal | Recommended expression | Caveats to know |
| --- | --- | --- |
| Is the whole JSONB column SQL NULL? | `doc IS NULL` | Excludes JSON null documents. |
| Is the document root JSON literal null? | `jsonb_typeof(doc) = 'null'` | Evaluates to UNKNOWN on SQL NULL documents. |
| Is root an object? | `jsonb_typeof(doc) = 'object'` | Pair with `NOT NULL` inside `CHECK`. |
| Does object have key `email`? | `doc ? 'email'` | Top-level only; matches string elements on arrays. |
| Does `email` hold JSON null? | `jsonb_typeof(doc -> 'email') = 'null'` | Does not verify root is an object by itself. |
| Does `email` hold any string? | `jsonb_typeof(doc -> 'email') = 'string'` | Empty strings and `"null"` still match `string`. |
| Extract `email` text for display | `doc ->> 'email'` | Collapses JSON null and missing into SQL NULL. |
| Is nested `profile.email` JSON null? | `jsonb_typeof(doc #> '{profile,email}') = 'null'` | Inspect each level if diagnosing why path is missing. |
| Does nested path exist? | `jsonb_path_exists(doc,'$.profile.email')` | PostgreSQL 12+; check lax/strict mode and root type. |
| Does object match exact `email` JSON null? | `doc @> '{"email":null}'::jsonb` | Containment is not a generic key-presence test for other types. |
| Remove `email` key | `doc - 'email'` | Removes top-level key; differs from JSON null. |
| Set key to JSON null | `jsonb_set(doc,'{email}','null'::jsonb,true)` | Intermediate objects must exist. |
| Handle SQL NULL `new_value` by mode | `jsonb_set_lax(...)` | PostgreSQL 13+ with explicit mode. |
| Strip JSON null object fields | `jsonb_strip_nulls(doc)` | Can erase explicit nulls; arrays behave differently. |
| Compare JSONB vs. SQL NULL without UNKNOWN | `IS DISTINCT FROM` | Does not report whether the key existed. |
| Count JSON values at key | `COUNT(doc -> 'email')` | Counts JSON null; skips missing. |
| Count non-SQL-NULL text values | `COUNT(doc ->> 'email')` | Skips both JSON null and missing. |

### 33.1. Example question: “email never declared”

If domain rules define *never declared* as an object whose `email` key **is absent**, use:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND NOT (doc ? 'email');
```

Never use `doc ->> 'email' IS NULL`, as that also matches explicit JSON null and non-object roots.

### 33.2. Example question: “email sent explicitly as null”

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'null';
```

Returns `id=4` on the lab data.

### 33.3. Example question: “email holds string content”

```sql
SELECT id, doc ->> 'email' AS email
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND jsonb_typeof(doc -> 'email') = 'string'
  AND length(doc ->> 'email') > 0;
```

Note the four-character string `"null"` still passes. Real email validation requires format and policy checks as well.

## 34. Common misconceptions

### Misconception 1. “JSON null and SQL NULL are identical”

False. `'null'::jsonb IS NULL` is FALSE, whereas `NULL::jsonb IS NULL` is TRUE.

### Misconception 2. “An object with email:null lacks the email key”

False. `'{"email":null}'::jsonb ? 'email'` is TRUE.

### Misconception 3. “The -> operator always returns SQL NULL when a JSON field is null”

False. `->` returns JSONB null when the key exists with JSON null; only missing keys or untraversable paths return SQL NULL.

### Misconception 4. “->> also preserves JSON types”

False. `->>` returns SQL text, turning both JSON null and missing into SQL NULL.

### Misconception 5. “jsonb_typeof('null'::jsonb) returns SQL NULL”

False. It returns **SQL text `null`**, naming the JSON type.

### Misconception 6. “jsonb_typeof(NULL::jsonb) = 'null' returns TRUE”

False. Comparing against SQL NULL returns UNKNOWN/SQL NULL; use `IS NULL` to check for an absent result.

### Misconception 7. “WHERE doc->'k' <> 'null'::jsonb includes missing keys”

False. For missing keys, `doc->'k'` is SQL NULL; `<>` returns UNKNOWN, so `WHERE` drops the row.

### Misconception 8. “COALESCE automatically replaces JSON null inside jsonb”

False. `COALESCE('null'::jsonb, '{}'::jsonb)` returns JSONB null because JSONB null **is not SQL NULL**.

### Misconception 9. “COALESCE(doc->>'k', old) preserves the missing/null distinction”

False. Both missing keys and explicit JSON nulls fall back to `old`. That is only valid when an API intentionally treats both identically.

### Misconception 10. “JSON string 'null' is JSON null”

False. JSON string `"null"` has type `string`; JSON null `null` has type `null`.

### Misconception 11. “Empty strings, false, and 0 count as null”

False. They are non-null JSON scalars with distinct values and types. Domain rules may reject them, yet they are not null.

### Misconception 12. “IS NULL on ->> selects only users wanting to clear the field”

False. It also matches omitted fields and SQL NULL documents unless guarded by additional conditions.

### Misconception 13. “The ? operator searches every depth of a JSON document”

False. On objects, `?` checks only top-level keys; on arrays, it checks top-level string elements. Nested keys require extracting child objects or using JSONPath.

### Misconception 14. “? 'null' on a JSON array finds JSON null elements”

False. It searches for the **JSON string `"null"`**, not scalar JSON null.

### Misconception 15. “Array [null] equals []”

False. `jsonb_array_length('[null]'::jsonb)=1`, whereas an empty array has length 0.

### Misconception 16. “Out-of-bounds array index and null element are identical”

False. `[null] -> 0` returns JSON null, while `[null] -> 1` returns SQL NULL.

### Misconception 17. “SQL NULL array and JSON null array share the same type”

False. Native SQL arrays store SQL-typed elements, while JSONB arrays hold JSON values; operators and conversion rules differ.

### Misconception 18. “#> and #>> return the same output type”

False. `#>` preserves JSON/JSONB, whereas `#>>` returns SQL text and collapses JSON null and missing into SQL NULL.

### Misconception 19. “profile:null and profile:{} have the same structure”

False. In the first, `profile` is a JSON scalar null; in the second, it is an empty JSON object capable of accepting child keys.

### Misconception 20. “jsonb_set(doc,'{k}',NULL::jsonb) sets k=null”

False. An SQL NULL argument is not JSONB null; pass `'null'::jsonb` to write JSON null, or use `jsonb_set_lax` with an explicit mode.

### Misconception 21. “jsonb_set automatically creates all missing intermediate objects”

False. `create_if_missing=true` does not fabricate arbitrary missing intermediate objects. Parent structures must already exist.

### Misconception 22. “jsonb_set_lax delete_key behaves like use_json_null”

False. One removes the key while the other keeps the key with JSON null.

### Misconception 23. “jsonb_strip_nulls never loses information”

False. It turns `{"email":null}` into `{}`, erasing explicit null vs. missing distinctions.

### Misconception 24. “COUNT(doc->'k') skips JSON null”

False. `COUNT` skips **SQL NULL**, whereas `doc->'k'` returns JSONB null (non-SQL-NULL) whenever the key holds explicit JSON null.

### Misconception 25. “COUNT(doc->'k') and COUNT(doc->>'k') are always equal”

False. JSON null fields are counted in `->` JSONB form, yet omitted after `->>` text conversion.

### Misconception 26. “NOT NULL prevents a jsonb column from storing literal null”

False. `doc jsonb NOT NULL` still permits `'null'::jsonb`. To require an object, add a `CHECK` on `jsonb_typeof`.

### Misconception 27. “CHECK(doc->>'email' <> '') guarantees email is present”

False. For missing keys or JSON null, the expression evaluates to UNKNOWN, and `CHECK` permits UNKNOWN. Combine `NOT NULL` with proper presence and type checks.

### Misconception 28. “GIN jsonb_path_ops accelerates every jsonb operator”

False. Different operator classes support different operators; notably, `?` is not supported by `jsonb_path_ops` the way `jsonb_ops` supports it.

### Misconception 29. “JSONPath path existence means the value is non-null”

False. A path can exist even when its terminal value is JSON null.

### Misconception 30. “JSONPath @ == null behaves like SQL = NULL”

False. In JSONPath, comparing against JSON null follows JSONPath rules; in SQL three-valued logic, `= NULL` never yields TRUE.

### Misconception 31. “Parsing JSON into a nullable text/POJO preserves field presence”

False. Without presence metadata, missing keys and explicit JSON nulls collapse into the same Java/SQL null.

### Misconception 32. “Jackson get('email') returns Java null for explicit JSON null”

False. It returns a `NullNode`; Java `null` from `get` signals the key is missing from the object.

### Misconception 33. “Jackson path('email') and get('email') behave identically”

False. `path` returns a `MissingNode` instead of Java `null` when missing, enabling `.isMissingNode()` checks.

### Misconception 34. “JSON Merge Patch uses null to store JSON null”

False under standard merge-patch rules: a null member signals removal. If you need to store literal JSON null distinct from deletion, pick a format supporting explicit operations such as JSON Patch.

### Misconception 35. “Every HTTP PATCH means null=delete”

False. Content-Type and the API contract govern PATCH behavior. Custom JSON PATCH endpoints must document missing/null/value behavior explicitly.

### Misconception 36. “JSONB preserves every duplicate object key”

False. JSONB deduplicates object keys rather than keeping multiple entries as a list; detect duplicate input keys at raw parsing time if they must be rejected.

### Misconception 37. “SELECT jsonb_build_object('x',SQL_NULL) proves the input was JSON null”

False. JSON builders render SQL NULL as JSON null, hiding the original SQL NULL vs. JSON null distinction.

### Misconception 38. “An expression index returning SQL NULL still separates missing from JSON null”

False. An index on `doc->>'email'` stores only extracted text values; both states collapse to SQL NULL inside the index.

### Misconception 39. “Rewriting a query with IS DISTINCT FROM reveals whether a field exists”

False. NULL-safe comparison compares SQL values safely, yet cannot substitute for the key-presence check `?`.

### Misconception 40. “A single nullable staging column suffices for patch events”

False whenever missing and clear carry distinct meanings. Retain raw JSON or explicit presence/action metadata.

## 35. Practice exercises

Exercises use `json_null_lab.documents` populated with 18 rows in Section 4 and the corresponding lab tables from earlier sections. Wrap any `UPDATE`/`DELETE` exercises in transactions ending with `ROLLBACK` so the test dataset stays intact. For version-specific features, review the PostgreSQL 12+/13+ notes above.

### Exercise 1. Classifying three concepts

Explain clearly how `NULL::jsonb`, `'null'::jsonb`, and `'{}'::jsonb` differ when extracting key `email`.

### Exercise 2. IS NULL at root

Evaluate:

```sql
SELECT
    NULL::jsonb IS NULL AS a,
    'null'::jsonb IS NULL AS b,
    '{}'::jsonb IS NULL AS c;
```

### Exercise 3. jsonb_typeof

What does `jsonb_typeof('null'::jsonb)` return? What does `jsonb_typeof(NULL::jsonb)` return? Why do they differ?

### Exercise 4. JSON string "null"

Write an expression distinguishing `'{"k":"null"}'::jsonb` from `'{"k":null}'::jsonb` based on the JSON type of key `k`.

### Exercise 5. -> on a key with JSON null

Evaluate:

```sql
SELECT
    ('{"k":null}'::jsonb -> 'k') IS NULL AS a,
    ('{}'::jsonb -> 'k') IS NULL AS b;
```

### Exercise 6. ->> erases differences

Why do both expressions below return SQL NULL?

```sql
'{"k":null}'::jsonb ->> 'k'
'{}'::jsonb ->> 'k'
```

### Exercise 7. Testing key existence

Write an SQL query selecting rows where `doc` is an object with the **`email` key present**, regardless of whether its value is JSON null, string, boolean, or number.

### Exercise 8. Selecting only JSON null

Write an SQL query selecting documents where **top-level `email`** is present and holds **JSON null**. Which ID matches on the unmodified lab table?

### Exercise 9. Selecting only missing keys

Write an SQL query selecting object documents **without a top-level `email`**. Should `id=1` and `id=2` be included?

### Exercise 10. SQL UNKNOWN in comparisons

Given `doc='{}'::jsonb`, is `doc->'email' <> 'null'::jsonb` TRUE, FALSE, or UNKNOWN? Does `WHERE` select that row?

### Exercise 11. IS DISTINCT FROM

What does `NULL::jsonb IS DISTINCT FROM 'null'::jsonb` return? Does it prove the field exists?

### Exercise 12. COALESCE with ->

Does:

```sql
SELECT COALESCE(
    '{"k":null}'::jsonb -> 'k',
    '"fallback"'::jsonb
);
```

return JSON null or the fallback? Why?

### Exercise 13. COALESCE with ->>

If you switch Exercise 12 to `->>` and set the fallback to SQL text `fallback`, what is returned? What information is lost?

### Exercise 14. Nested path

Compare the results of `#> '{profile,email}'` for:

```json
{"profile":{"email":null}}
```

```json
{"profile":{}}
```

```json
{"profile":null}
```

### Exercise 15. What level does ? inspect?

Evaluate:

```sql
SELECT
    '{"profile":{"email":null}}'::jsonb ? 'email'
        AS a,
    ('{"profile":{"email":null}}'::jsonb
        -> 'profile') ? 'email'
        AS b;
```

### Exercise 16. JSON array

Determine the result type of:

```sql
'[null]'::jsonb -> 0
'[null]'::jsonb -> 1
'["null"]'::jsonb -> 0
```

### Exercise 17. Array length

What is `jsonb_array_length('[null,null]'::jsonb)`? Should null elements be treated as missing from the array?

### Exercise 18. ? on arrays

Does `'[null,"null"]'::jsonb ? 'null'` return TRUE? Why?

### Exercise 19. COUNT with JSON null

On the unmodified 18-row lab table, compute:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(doc) AS non_sql_null_docs,
    COUNT(doc -> 'email') AS json_values,
    COUNT(doc ->> 'email') AS text_values
FROM json_null_lab.documents;
```

### Exercise 20. Containment

Which `@>` predicate matches objects whose top-level `email` is JSON null? Will it select objects missing `email`?

### Exercise 21. jsonb_each

How many rows does `jsonb_each('{"k":null}'::jsonb)` return? How many for `jsonb_each('{}'::jsonb)`? Is `value` in the first result SQL NULL?

### Exercise 22. jsonb_to_record

Why do converting `{}` and `{"email":null}` into a record with `email text` yield the same SQL NULL email? What metadata must you keep to tell them apart?

### Exercise 23. jsonb_set vs. deleting a key

Write two expressions transforming `{"email":"old"}` into:

1. `{"email":null}`.
2. `{}`.

### Exercise 24. jsonb_set_lax

Given `new_value=NULL::jsonb`, distinguish modes `use_json_null`, `delete_key`, and `return_target`.

### Exercise 25. jsonb_strip_nulls

Transform `{"email":null,"a":[null],"profile":{"phone":null}}` using single-argument `jsonb_strip_nulls`. Why can this break PATCH semantics?

### Exercise 26. Broken CHECK

Why does `CHECK (doc->>'email' <> '')` fail to guarantee `email` exists and is not JSON null?

### Exercise 27. Object-only CHECK

Write column and constraint definitions ensuring `doc` cannot be SQL NULL, JSON null root, an array, or a scalar string—only a JSON object.

### Exercise 28. Optional email

Write a `CHECK` constraint for an object `doc` with an optional `email` key that, when present, must be either a JSON string or JSON null.

### Exercise 29. NOT NULL with JSON null

Does a `doc jsonb NOT NULL` column permit inserting `'null'::jsonb`? When is an extra `CHECK` needed?

### Exercise 30. PATCH API

Given current profile email `old@example.com`, describe the effect of all three bodies:

```json
{}
```

```json
{"email":null}
```

```json
{"email":"new@example.com"}
```

under the contract “missing keeps old, null clears, string sets.”

### Exercise 31. Jackson

In Java Jackson, how do `root.get("email")` and `root.path("email")` differ when `email` is missing? Which check detects explicit JSON null?

### Exercise 32. JDBC

Explain why Java `String jsonText = rs.getString("doc")` returns Java `null` for an SQL NULL column, yet returns the string `"null"` when the column stores JSONB null.

### Exercise 33. JSONPath

Write two expressions using `jsonb_path_exists`:

1. Check whether path `$.email` exists.
2. Check whether that path holds JSON null.

### Exercise 34. GIN operator classes

If hot queries rely on `doc ? 'email'`, what goes wrong if you choose GIN `jsonb_path_ops` instead of `jsonb_ops`?

### Exercise 35. Native SQL arrays

Do `ARRAY[NULL::integer,7]` and `'[null,7]'::jsonb` share the same type? Should you call `jsonb_array_length` on an SQL integer array?

### Exercise 36. Data pipeline

Given three events:

```json
{"changes":{}}
```

```json
{"changes":{"phone":null}}
```

```json
{"changes":{"phone":"123"}}
```

under a patch contract, name the three corresponding actions and explain why a lone nullable `phone text NULL` column fails to capture intent.

### Exercise 37. jsonb_build_object

Compare outputs:

```sql
jsonb_build_object('email', NULL::text)
jsonb_build_object('email', 'null'::jsonb)
jsonb_build_object('email', 'null'::text)
```

Can you determine from the JSON output whether the source was SQL NULL or JSON null?

### Exercise 38. Text false and number 0

Why is `doc->>'email' IS NOT NULL` insufficient to ensure `email` is a JSON string? Write the proper condition using `jsonb_typeof`.

### Exercise 39. Analyzing a buggy SQL query

A developer writes:

```sql
UPDATE profiles
SET email = COALESCE(patch_doc ->> 'email', email);
```

expecting `{"email":null}` to clear `email`. Explain the bug and show how to fix it.

### Exercise 40. Designing test cases

Design at least eight test cases for an endpoint accepting a JSONB `email` field, ensuring it never merges SQL NULL, JSON null, missing, string `"null"`, empty string, boolean `false`, number `0`, and nested fields into a single state.

## 36. Suggested solutions

### Solution 1. Three concepts

- `NULL::jsonb`: SQL NULL for the entire document; no JSON value at the expression level.
- `'null'::jsonb`: a valid JSON document whose root has JSON type `null`.
- `'{}'::jsonb`: an empty JSON object that exists yet lacks the `email` key.

Calling `->'email'` yields SQL NULL on all three, but for **three different reasons**. Inspect root type and key presence to distinguish them.

### Solution 2. IS NULL

`a=TRUE`, `b=FALSE`, `c=FALSE`. Both JSON null and an empty object are **non-SQL-NULL jsonb values**.

### Solution 3. jsonb_typeof

`jsonb_typeof('null'::jsonb)` returns SQL text `null`. `jsonb_typeof(NULL::jsonb)` returns SQL NULL because there is no JSONB input value to inspect.

### Solution 4. JSON string vs. JSON null

```sql
SELECT
    jsonb_typeof('{"k":"null"}'::jsonb -> 'k')
        AS string_type,
    jsonb_typeof('{"k":null}'::jsonb -> 'k')
        AS null_type;
```

Outputs are text `string` and `null`; they are unequal.

### Solution 5. -> IS NULL

`a=FALSE` because `->` returns an existing JSONB null value. `b=TRUE` because key `k` is missing and `->` returns SQL NULL.

### Solution 6. ->> to text

`->>` returns SQL text. JSON null converts to SQL NULL, and a missing key has no value so it also yields SQL NULL. Once you only hold a nullable text value, presence is lost.

### Solution 7. Key presence

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
ORDER BY id;
```

IDs 4, 5, 6, 7, 8, 17, 18.

### Solution 8. Explicit JSON null

```sql
SELECT id, doc
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND doc ? 'email'
  AND jsonb_typeof(doc -> 'email') = 'null';
```

Only `id=4` on the original lab table.

### Solution 9. Email missing on an object

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND NOT (doc ? 'email')
ORDER BY id;
```

IDs 3, 9, 10, 11, 12. It **excludes** `id=1` (SQL NULL document) and `id=2` (JSON scalar null), because neither root is an object.

### Solution 10. UNKNOWN

`'{}'::jsonb -> 'email'` is SQL NULL. Inequality against `'null'::jsonb` returns UNKNOWN, so `WHERE` skips the row because the predicate is not TRUE.

### Solution 11. IS DISTINCT FROM

Returns TRUE because SQL NULL differs from a JSONB null value. However, it only compares two values without proving the key existed in an object.

### Solution 12. COALESCE with ->

Returns **JSON null**. The result of `-> 'k'` is an existing JSONB null, not SQL NULL, so `COALESCE` stops at the first argument.

### Solution 13. COALESCE with ->>

Returns SQL text `fallback`, because `->>` converts JSON null to SQL NULL. A missing key also yields the fallback; explicit null vs. missing is lost.

### Solution 14. Nested path

- `{"profile":{"email":null}}` → JSONB null.
- `{"profile":{}}` → SQL NULL because `email` is missing.
- `{"profile":null}` → SQL NULL because traversal cannot continue past a JSON scalar null.

### Solution 15. ? top-level vs. nested

`a=FALSE`, `b=TRUE`. The `email` key is not at the root document's top level; it sits inside the `profile` object.

### Solution 16. Array indexing

- `'[null]'::jsonb -> 0`: JSONB null.
- `'[null]'::jsonb -> 1`: SQL NULL (out-of-bounds index).
- `'["null"]'::jsonb -> 0`: JSONB string `"null"`.

### Solution 17. Length

Result is 2. JSON null is still an existing array element and counts toward `jsonb_array_length`.

### Solution 18. ? on arrays

TRUE, because the array holds the JSON string `"null"`. If the array contained only literal JSON null without the string `"null"`, `? 'null'` would return FALSE.

### Solution 19. Lab COUNTs

Across the unmodified 18 rows:

| Aggregate | Result |
| --- | ---: |
| `COUNT(*)` | 18 |
| `COUNT(doc)` | 17 |
| `COUNT(doc -> 'email')` | 7 |
| `COUNT(doc ->> 'email')` | 6 |

`->` preserves JSON null as a non-SQL-NULL value, while `->>` turns it into SQL NULL. `COUNT(expression)` skips SQL NULLs.

### Solution 20. Containment

```sql
SELECT id
FROM json_null_lab.documents
WHERE doc @> '{"email":null}'::jsonb;
```

Selects `id=4` in the lab. An object lacking `email` does not contain `{"email":null}`, so it is excluded.

### Solution 21. jsonb_each

`jsonb_each('{"k":null}'::jsonb)` emits one row with key `k` and value **JSONB null**; `jsonb_each('{}'::jsonb)` emits 0 rows. Switching to `jsonb_each_text` converts `k`'s value to SQL NULL.

### Solution 22. Record conversion

When projecting into an SQL `email text` column, both omitted fields and explicit JSON nulls turn into SQL NULL. Save an additional flag such as `email_present = doc ? 'email'`, an action enum, or the raw JSON payload to separate them.

### Solution 23. Setting JSON null vs. deleting

```sql
SELECT
    jsonb_set(
        '{"email":"old"}'::jsonb,
        '{email}',
        'null'::jsonb,
        true
    ) AS keep_key_with_json_null,
    '{"email":"old"}'::jsonb - 'email'
        AS remove_key;
```

Outputs are `{"email":null}` and `{}` respectively—two semantically different changes.

### Solution 24. jsonb_set_lax

On PostgreSQL 13+:

- `use_json_null`: converts an SQL NULL `new_value` into JSON null on the key.
- `delete_key`: removes the key/path when applicable.
- `return_target`: leaves the JSON document unchanged.

`raise_exception` rejects an SQL NULL `new_value` with an error. These modes take effect specifically when `new_value` is SQL NULL.

### Solution 25. jsonb_strip_nulls

With standard single-argument invocation:

```json
{"a":[null],"profile":{}}
```

Top-level `email` and `profile.phone` are stripped because they are object fields holding JSON null; the JSON null element inside array `a` stays. On a PATCH payload, an explicit null `email` becomes indistinguishable from missing, breaking clear/delete intent.

### Solution 26. Broken CHECK

When `email` is missing or JSON null, `doc->>'email'` is SQL NULL, making `NULL <> ''` evaluate to UNKNOWN. Because `CHECK` rejects only FALSE, those rows pass through. To require a non-empty string email, check presence, type, non-emptiness, and `doc NOT NULL`.

### Solution 27. Allowing objects only

```sql
CREATE TABLE json_null_lab.only_objects (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object')
);
```

`NOT NULL` blocks SQL NULL; `CHECK` blocks JSONB scalar null, arrays, strings, numbers, and booleans.

### Solution 28. Optional email

```sql
CREATE TABLE json_null_lab.optional_email_example (
    id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object'),
    CHECK (
        NOT (doc ? 'email')
        OR jsonb_typeof(doc -> 'email')
            IN ('string', 'null')
    )
);
```

Missing email is valid, JSON null email is valid, and JSON string email is valid; booleans, numbers, objects, and arrays for `email` are rejected.

### Solution 29. NOT NULL

Yes. `'null'::jsonb` is a valid JSONB value and satisfies `NOT NULL`. To accept only JSON objects, add `CHECK(jsonb_typeof(doc)='object')`.

### Solution 30. PATCH

Per the specified contract:

- `{}` → `email` stays `old@example.com`.
- `{"email":null}` → `email` becomes SQL NULL in a nullable relational column or runs the corresponding clear action.
- `{"email":"new@example.com"}` → `email` becomes `new@example.com`.

You must check key presence before calling `->>`; `COALESCE` alone cannot distinguish `{}` from `{"email":null}`.

### Solution 31. Jackson

- `root.get("email")` returns Java `null` when missing.
- `root.path("email")` returns `MissingNode` when missing.
- When the field holds JSON null, both return a `NullNode`; check `.isNull()`.

With `get`, always check `email != null` before calling methods on the node.

### Solution 32. JDBC

SQL NULL in `doc` surfaces as Java `null` from `rs.getString`. JSONB null is a genuine value whose JSON text serialization is the four characters `null`, which parsers like Jackson read into a `NullNode`. Never write `"null".equals(jsonText)` to test for SQL NULL.

### Solution 33. JSONPath

On PostgreSQL 12+:

```sql
SELECT
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email'
    ) AS path_exists,
    jsonb_path_exists(
        '{"email":null}'::jsonb,
        '$.email ? (@ == null)'
    ) AS path_has_json_null;
```

Both return TRUE. On `{}`, both return FALSE.

### Solution 34. GIN operator class

`jsonb_ops` supports key-existence operators like `?`; `jsonb_path_ops` does not support `?` in the same way. Picking `jsonb_path_ops` for a `?`-heavy workload leaves the index unused for that operator. Check operator support and verify plans.

### Solution 35. Native SQL array

No. `ARRAY[NULL::integer,7]` is SQL `integer[]`; `'[null,7]'::jsonb` is a `jsonb` array. `jsonb_array_length` accepts `jsonb` arrays, not native `integer[]`. For native SQL arrays, use `array_length` or `cardinality`.

### Solution 36. Pipeline

- `{"changes":{}}` → `UNCHANGED`.
- `{"changes":{"phone":null}}` → `CLEAR`.
- `{"changes":{"phone":"123"}}` → `SET`.

If stored only in a single nullable `phone text` column, the first two collapse to identical SQL NULLs despite having opposite actions. Retain raw JSON, presence flags, or explicit actions.

### Solution 37. jsonb_build_object

```sql
SELECT
    jsonb_build_object('email', NULL::text)
        AS from_sql_null,
    jsonb_build_object('email', 'null'::jsonb)
        AS from_json_null,
    jsonb_build_object('email', 'null'::text)
        AS from_text;
```

The first two output `{"email":null}`, while the last outputs `{"email":"null"}`. From the first two identical JSON strings alone, you cannot determine whether the input was SQL NULL or JSON null.

### Solution 38. Checking for JSON strings

`->>` coerces JSON booleans and numbers to text, so `IS NOT NULL` accepts non-string types too. Instead use:

```sql
SELECT id
FROM json_null_lab.documents
WHERE jsonb_typeof(doc) = 'object'
  AND jsonb_typeof(doc -> 'email') = 'string';
```

Add `length(doc ->> 'email') > 0` for non-empty strings, plus domain validation for valid email addresses.

### Solution 39. PATCH with COALESCE

`patch_doc ->> 'email'` evaluates to SQL NULL for both JSON null and missing; `COALESCE(..., email)` preserves the old email in both cases, **failing to clear** on `{"email":null}`.

Correct contract implementation:

```sql
SET email =
    CASE
        WHEN patch_doc ? 'email'
            THEN patch_doc ->> 'email'
        ELSE email
    END
```

This shows only the `SET` clause; a complete `UPDATE` must also validate that `patch_doc` is an object, `email` is a string or null, permissions hold, and the right row is targeted.

### Solution 40. Test suite

| Input | Expected classification | Meaning |
| --- | --- | --- |
| SQL NULL document | `SQL_NULL_DOCUMENT` | Missing SQL document. |
| JSON document `null` | `NOT_AN_OBJECT` or `DOCUMENT_JSON_NULL` | Root is JSON null, not an object patch. |
| `{}` | `MISSING` | `email` absent. |
| `{"email":null}` | `JSON_NULL` | Client sent explicit JSON null. |
| `{"email":"null"}` | `STRING` | Literal text `"null"`, not auto-cleared. |
| `{"email":""}` | `EMPTY_STRING` | Present empty string; allow or reject per policy. |
| `{"email":false}` | `OTHER_JSON_VALUE` | JSON boolean, usually rejected for email. |
| `{"email":0}` | `OTHER_JSON_VALUE` | JSON number, usually rejected. |
| `{"profile":{"email":null}}` | Top-level `email` `MISSING` | Nested `email` is not top-level `email`. |
| `{"email":{}}` | `OTHER_JSON_VALUE` | Empty JSON object is not an email string. |

Automated tests should assert **the persisted post-UPDATE value**, **key presence state**, and **HTTP error behavior** for each case—not merely that a text column turned into SQL NULL.

## 37. Project checklist for handling JSON null, SQL NULL, and missing

1. **Identify the data layer:** are you inspecting an SQL column, JSON root, object key, nested path, or array index?
2. **Never confuse literals:** JSON `null` differs from JSON string `"null"`.
3. **Never confuse roots:** `NULL::jsonb` differs from `'null'::jsonb` and `'{}'::jsonb`.
4. **Pick the right operator:** `->`/`#>` preserve JSONB types; `->>`/`#>>` return SQL text.
5. **Verify root type first:** check `jsonb_typeof(doc)='object'` before testing object keys.
6. **Check key presence first:** use `doc ? 'key'` or path checks whenever missing differs from null.
7. **Check JSON type explicitly:** `jsonb_typeof(doc->'key')='null'` for JSON null, `='string'` for strings.
8. **Never use `= NULL`:** use `IS NULL` for SQL NULL, and compare JSONB against `'null'::jsonb` when checking JSON null.
9. **Respect UNKNOWN:** `WHERE` excludes UNKNOWN predicates, whereas `CHECK` permits UNKNOWN.
10. **Use `COALESCE` intentionally:** it handles SQL NULL and leaves JSONB null untouched.
11. **Preserve presence before mapping:** `jsonb_to_record` and nullable DTOs erase missing-key status.
12. **Count carefully:** `COUNT(doc->'key')` and `COUNT(doc->>'key')` diverge when JSON null appears.
13. **Distinguish array slots:** a JSON null element exists and counts toward length; out-of-range indexes do not.
14. **Do not misuse `?` for nested keys:** extract the parent object or use JSONPath.
15. **Do not treat lax JSONPath as a schema validator:** inspect `jsonb_typeof` at required depths.
16. **Setting null differs from key removal:** `jsonb_set(...,'null'::jsonb)` vs. `-`/`#-`.
17. **Watch out for SQL NULL `new_value`:** use `jsonb_set_lax` with explicit modes on supported versions.
18. **Never strip nulls unconditionally:** it can erase explicit nulls from API requests or events.
19. **Layer your constraints:** `NOT NULL` for SQL NULL, object-type `CHECK`, and field presence/type/format checks.
20. **Index matching real semantics:** GIN `jsonb_ops` for `?` queries, expression indexes for `->>` when warranted.
21. **Clarify PATCH protocols:** JSON Merge Patch, JSON Patch, and custom PATCH treat null differently.
22. **Separate states in Java:** distinguish Java `null`, Jackson `NullNode`, and `MissingNode`.
23. **Handle JDBC carefully:** `getString` SQL NULL differs from JSON text `null`.
24. **Preserve intent in pipelines:** retain presence or action metadata whenever missing ≠ clear.
25. **Test all edge states:** SQL NULL, JSON null, missing, `"null"`, `""`, `false`, `0`, arrays, nested paths, and wrong types.
26. **Remember security and concurrency:** valid key presence is never enough without authorization, validation, versioning, and transaction safety.

## 38. Summary

In PostgreSQL, **SQL NULL**, **JSON null**, and **missing JSON elements** are three distinct concepts:

- **SQL NULL**: absence of an SQL value, such as `NULL::jsonb` or extracting a non-existent key/path.
- **JSON null**: an actual JSON value of type `null`, such as `'null'::jsonb` or `'{"email":null}'::jsonb -> 'email'`.
- **Missing**: an object lacks a key or an array lacks an index. PostgreSQL represents missing extraction outputs using **SQL NULL**, while presence itself remains testable via `?`, structural checks, or JSONPath.

Rules to remember:

- **`->` and `#>` preserve JSON types:** JSON null remains a non-SQL-NULL JSONB value.
- **`->>` and `#>>` extract text:** both JSON null and missing turn into SQL NULL.
- **`jsonb_typeof(...) = 'null'`** checks for JSON null; `IS NULL` checks for expression SQL NULL.
- **`doc ? 'key'`** separates top-level key presence from missing keys; JSON null values still count as present keys.
- **`@> '{"key":null}'::jsonb`** tests containment of JSON null, completely distinct from checking general key presence.
- **`COALESCE` acts on SQL NULL**, not JSONB null; applying it after `->>` merges missing and JSON null together.
- **`jsonb_set` writes values**, `-`/`#-` delete keys/paths, and `jsonb_set_lax` defines behavior for SQL NULL `new_value` on PostgreSQL 13+.
- **`CHECK` and `COUNT` follow SQL NULL rules**, not business-specific JSON null meanings.
- **PATCH APIs and data pipelines need a presence bit** whenever missing means “unchanged” and JSON null means “clear/delete.”

One simple rule prevents most bugs:

> **Before converting JSON into plain text or a nullable DTO, determine whether the field was supplied; only then inspect its type and value.**

When you consistently separate **“does the element exist?”** from **“if it exists, what JSON value does it hold?”**, you will handle JSONB accurately across SQL queries, table constraints, and application update flows.
