# jsonb Containment, Existence, and Comparison Operators in PostgreSQL

A `jsonb` column allows PostgreSQL to store semi-structured data such as product attributes, configuration, metadata, or event payloads. However, **having a key**, **having a value**, **containing a JSON structure**, and **comparing two JSON documents** are distinct questions.

For example, consider the document:

~~~json
{
  "sku": "KB-01",
  "active": true,
  "tags": ["tech", "sale"],
  "vendor": {"name": "A", "country": "VN"},
  "notes": null
}
~~~

You must distinguish between:

~~~sql
-- Does top-level key "vendor" exist?
doc ? 'vendor'

-- Does the document contain a vendor object with country = VN?
doc @> '{"vendor":{"country":"VN"}}'::jsonb

-- Does the vendor object have key "country"?
(doc -> 'vendor') ? 'country'

-- Does tags contain the string value "sale"?
doc @> '{"tags":["sale"]}'::jsonb

-- Does key notes exist with JSON null?
doc @> '{"notes":null}'::jsonb
~~~

All of these are valid expressions, yet they are **not synonymous**. A subtle mistake can drop matching rows, compare the wrong types, or build an index that never gets used.

This lesson explains three main operator groups:

1. **Containment:** `@>` and `<@`, including specific rules for objects and arrays.
2. **Existence:** `?`, `?|`, and `?&` to test object keys or string elements at the current level.
3. **Comparison:** `=`, `<>`, `<`, `<=`, `>`, `>=` and issues involving structure, JSON types, B-tree ordering, and SQL `NULL`.

In addition, the lesson introduces SQL/JSON path `@?` / `@@`, leveraging GIN `jsonb_ops` / `jsonb_path_ops`, B-tree and expression indexes, `EXPLAIN`, lab work, and exercises with reference solutions.

## 1. Learning Objectives

After this lesson, you will be able to:

1. State the differences between the `json` and `jsonb` types in PostgreSQL.
2. Use `@>` and `<@` to query documents containing objects, arrays, and nested structures.
3. Understand why element order and duplicate elements in arrays behave differently under containment vs. equality.
4. Use `?`, `?|`, and `?&` at the proper JSON nesting level.
5. Distinguish missing keys, keys with `null` values, and SQL `NULL` expressions.
6. Compare two `jsonb` values without arbitrarily converting them to text.
7. Understand the default ordering of JSON types in B-tree indexes or `ORDER BY` on `jsonb`.
8. Use JSONPath operators `@?` and `@@` when deeper structural checks are needed.
9. Choose the GIN operator class matching the operators used by your application.
10. Know when an expression index or B-tree is needed instead of a full-document GIN index.
11. Read `EXPLAIN (ANALYZE, BUFFERS)` to verify whether an index is actually used.
12. Recognize the limits of JSONB and when explicitly typed relational columns should be used.

## 2. How Does JSON Differ from JSONB?

PostgreSQL provides two familiar JSON data types:

| Criterion | `json` | `jsonb` |
| --- | --- | --- |
| Storage | Keeps the validated JSON text representation | Stores a parsed binary representation |
| Whitespace and input key order | Preserved in the original representation | Not preserved as in the original string |
| Duplicate keys in objects | May retain duplicate keys in stored input | Keeps one value per key, typically the last occurrence |
| Containment operator `@>` | Does not have the same direct operator set as JSONB | Supported |
| Equality/ordering comparisons | `json` has no standard B-tree comparison set | `jsonb` supports equality and B-tree ordering |
| GIN indexing | Typically requires casts/expressions as needed | Has dedicated GIN opclasses |
| Whole-document updates | Must process JSON value | Must construct a new `jsonb` value on change |

Example:

~~~sql
SELECT
    '{"a":1,"a":2}'::json AS raw_json,
    '{"a":1,"a":2}'::jsonb AS normalized_jsonb;
~~~

With `jsonb`, the result retains only one value for key `a`, corresponding to the last value. Do not rely on JSONB **key order** when serializing outward.

### 2.1. JSONB Is Not a Perfect Mini Relational Table

JSONB is useful for flexible attributes, yet it does not automatically provide:

- Separate column types per key.
- Per-field `NOT NULL` and `CHECK` unless explicitly declared.
- Automatic foreign keys on IDs nested deep inside JSON.
- Column-equivalent planner statistics for every JSON path.

For stable business data such as `customer_id`, `amount`, and `created_at`, relational tables and explicitly typed columns still usually offer advantages in constraints, querying, and statistics.

### 2.2. Use JSONB When Structural Semantics Are Needed

When the goal is to ask "does the document contain these attributes?" or "does this key exist?", `jsonb` and its specialized operators and indexes are a strong choice.

## 3. Preparing the Lab Schema and Dataset

These examples use a **lab database**; do not write to production systems. To reproduce from scratch, create a dedicated schema.

~~~sql
CREATE SCHEMA json_lab;

CREATE TABLE json_lab.products (
    product_id integer PRIMARY KEY,
    doc jsonb NOT NULL,
    created_at timestamptz NOT NULL
);
~~~

Meaning:

- `product_id`: relational ID with `PRIMARY KEY`.
- `doc`: JSONB document, required not to be **SQL NULL**.
- `created_at`: explicitly typed timestamp column for filtering and sorting.

### 3.1. Inserting Ten Documents with Varying Structures

~~~sql
INSERT INTO json_lab.products
    (product_id, doc, created_at)
VALUES
    (
      1,
      '{
        "sku":"KB-01",
        "category":"keyboard",
        "price":120,
        "active":true,
        "tags":["tech","sale"],
        "stock":12,
        "vendor":{"name":"A","country":"VN"},
        "notes":null
      }'::jsonb,
      '2026-01-01 10:00:00+00'
    ),
    (
      2,
      '{
        "sku":"MS-02",
        "category":"mouse",
        "price":45,
        "active":true,
        "tags":["tech"],
        "stock":0,
        "vendor":{"name":"B","country":"VN"}
      }'::jsonb,
      '2026-01-02 10:00:00+00'
    ),
    (
      3,
      '{
        "sku":"BK-03",
        "category":"book",
        "price":18,
        "active":false,
        "tags":["education","sale"],
        "vendor":{"name":"A","country":"US"},
        "notes":"used"
      }'::jsonb,
      '2026-01-03 10:00:00+00'
    ),
    (
      4,
      '{
        "sku":"MN-04",
        "category":"monitor",
        "price":300,
        "active":true,
        "tags":["tech","office"],
        "stock":3,
        "vendor":{"name":"C","country":"JP"},
        "attributes":{"dimensions":{"width":24}}
      }'::jsonb,
      '2026-01-04 10:00:00+00'
    ),
    (
      5,
      '{
        "sku":"PN-05",
        "category":"pen",
        "price":2.5,
        "active":true,
        "tags":["office"],
        "stock":null,
        "vendor":{"name":"B","country":"VN"}
      }'::jsonb,
      '2026-01-05 10:00:00+00'
    ),
    (
      6,
      '{
        "sku":"HD-06",
        "category":"headphones",
        "price":80,
        "active":false,
        "tags":[],
        "stock":4,
        "vendor":{"name":"A","country":"VN"}
      }'::jsonb,
      '2026-01-06 10:00:00+00'
    ),
    (
      7,
      '{
        "sku":"ST-07",
        "category":"stand",
        "price":70,
        "active":true,
        "tags":["office","sale"],
        "stock":6,
        "vendor":{"name":"C","country":"VN"}
      }'::jsonb,
      '2026-01-07 10:00:00+00'
    ),
    (
      8,
      '{
        "sku":"CB-08",
        "category":"cable",
        "price":"20",
        "active":true,
        "tags":["tech"],
        "stock":10,
        "vendor":{"name":"D","country":"VN"}
      }'::jsonb,
      '2026-01-08 10:00:00+00'
    ),
    (
      9,
      '{
        "sku":"MT-09",
        "category":"mount",
        "price":90,
        "active":true,
        "tags":["tech","sale"],
        "stock":null,
        "notes":null
      }'::jsonb,
      '2026-01-09 10:00:00+00'
    ),
    (
      10,
      '{
        "sku":"PL-10",
        "category":"planner",
        "price":15,
        "active":true,
        "tags":["office"],
        "stock":3,
        "vendor":{"name":"C","country":"VN"},
        "attributes":{
          "sizes":[
            {"name":"small","units":2},
            {"name":"large","units":5}
          ]
        }
      }'::jsonb,
      '2026-01-10 10:00:00+00'
    );
~~~

The dataset intentionally includes:

- `tags` as a JSON array of strings.
- `vendor` as a nested object.
- `notes` **missing** in some documents and **JSON null** in others.
- `stock` as a number, JSON null, or missing.
- `price` mostly as a JSON number, while `CB-08` stores the string `"20"` to illustrate type inconsistency bugs.
- Document `MT-09` missing the `vendor` key.

### 3.2. Inspecting the Data

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    doc -> 'price' AS json_price,
    jsonb_typeof(doc -> 'price') AS price_type
FROM json_lab.products
ORDER BY product_id;
~~~

### 3.3. How to Read the Examples

When the lesson states "returns IDs," that result is based on **the ten documents just inserted**. If you modify the lab data, results may change. `EXPLAIN` plans depend on the environment; do not expect a fixed scan type on a ten-row table.

## 4. Overview of Core JSONB Operators

| Group | Operator | Meaning |
| --- | --- | --- |
| Containment | `left @> right` | Left JSONB contains right JSONB |
| Contained by | `left <@ right` | Left JSONB is contained by right JSONB |
| Existence | `value ? text` | Object key or array string element exists **at the current level** |
| Any exists | `value ?| text[]` | At least one key/element from the list exists |
| All exist | `value ?& text[]` | All keys/elements from the list exist |
| Equality | `left = right` | Two JSONB values are structurally equal |
| Inequality | `left <> right` | Two JSONB values are not equal |
| Ordering | `<`, `<=`, `>`, `>=` | Compares according to JSONB B-tree ordering |
| JSONPath existence | `value @? jsonpath` | Whether any item matches the path expression |
| JSONPath predicate | `value @@ jsonpath` | Evaluates the boolean predicate result of JSONPath |

Extraction operators:

~~~sql
doc ->  'key'
doc ->> 'key'
doc #>  '{path,to,key}'
doc #>> '{path,to,key}'
~~~

do not belong to the existence/containment group, but are essential for **navigating down to a nested object or array to inspect it**.

## 5. Containment Operator @>: Basic Meaning

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
    @> '{"a":1}'::jsonb AS contains_a;
~~~

The result is `true`: the left-hand object has every key/value pair required by the right-hand object.

### 5.1. Containment Does Not Mean Equality

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb
        AS contains_subset,
    '{"a":1,"b":2}'::jsonb = '{"a":1}'::jsonb
        AS structurally_equal;
~~~

Result:

- `contains_subset = true`.
- `structurally_equal = false`.

The left-hand object is allowed to **have additional keys** under `@>`.

### 5.2. Containing a Key with a Different Value Is False

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
    @> '{"a":3}'::jsonb AS contains_wrong_value;
~~~

Result `false`: simply having key `a` is not enough; **its value** must match as well.

### 5.3. Querying Products by Attribute

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"active":true}'::jsonb
ORDER BY product_id;
~~~

The predicate finds documents whose `active` key has the exact JSON boolean `true`, **not** the string `"true"` or the number `1`.

### 5.4. JSON Numbers Differ from JSON Strings

~~~sql
SELECT
    '{"price":20}'::jsonb
      @> '{"price":20}'::jsonb AS number_matches,
    '{"price":"20"}'::jsonb
      @> '{"price":20}'::jsonb AS text_vs_number;
~~~

Results are `true` and `false` respectively. PostgreSQL does not coerce the string `"20"` into the number `20` to satisfy containment.

## 6. Containment of Nested Structures

JSONB containment operates **structurally**.

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{
  "vendor": {
    "country": "VN"
  }
}'::jsonb
ORDER BY product_id;
~~~

The predicate only requires `vendor` to be an object containing `country = 'VN'`. The `vendor` object may have additional keys like `name`.

### 6.1. Why Does This Containment Match?

In document `KB-01`:

~~~json
{"vendor":{"name":"A","country":"VN"}}
~~~

The `vendor` object genuinely contains:

~~~json
{"country":"VN"}
~~~

as a subset of key/value pairs.

### 6.2. Does Not Traverse Arbitrary Levels When RHS Has a Different Structure

~~~sql
SELECT
    '{"vendor":{"country":"VN"}}'::jsonb
    @> '{"country":"VN"}'::jsonb
    AS top_level_contains_country;
~~~

Result `false`. The key `country` is inside `vendor`, not at the top level. `@>` **does not search for matching key names at arbitrary depths**.

### 6.3. Querying Deeper by Specifying the Full Structure

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{
  "attributes": {
    "dimensions": {"width":24}
  }
}'::jsonb;
~~~

This query matches `MN-04` at path `attributes.dimensions.width` with JSON number `24`.

### 6.4. Never Substitute Text Matching for Deep Search

~~~sql
WHERE doc::text LIKE '%"country": "VN"%'
~~~

is not an equivalent substitute for containment. Key ordering, whitespace, data types, escaped strings, and performance all make searching the serialized text representation fragile.

## 7. Containment with JSON Arrays

Consider:

~~~sql
SELECT
    '["tech","sale","office"]'::jsonb
      @> '["sale"]'::jsonb
      AS contains_sale,
    '["tech","sale"]'::jsonb
      @> '["office"]'::jsonb
      AS contains_office;
~~~

Results: `true` and `false`.

### 7.1. Element Order Does Not Matter for Containment

~~~sql
SELECT
    '["tech","sale"]'::jsonb
      @> '["sale","tech"]'::jsonb
      AS contains_reordered;
~~~

Result `true`: under `@>`, array element order does not determine the result the way equality does.

### 7.2. Duplicate Elements Count Once in Containment

~~~sql
SELECT
    '["sale"]'::jsonb
      @> '["sale","sale"]'::jsonb
      AS contains_repeated;
~~~

Result `true` under JSONB containment semantics. Repeating an element in the right-hand array does not create a requirement that it "appear twice."

**Do not carry this conclusion over to equality (`=`)**: two arrays with different element counts or ordering are not equal.

### 7.3. Element Types Must Match

~~~sql
SELECT
    '[1,2,3]'::jsonb @> '[2]'::jsonb AS number_two,
    '[1,2,3]'::jsonb @> '["2"]'::jsonb AS string_two;
~~~

Results: `true` and `false`.

### 7.4. Querying Tags

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb
ORDER BY product_id;
~~~

On the lab data, this returns `product_id` **1, 3, 7, 9**.

### 7.5. Matching Multiple Tags Together

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"tags":["tech","sale"]}'::jsonb
ORDER BY product_id;
~~~

This requires the `tags` array to contain **both** `tech` and `sale` (in any position/order).

## 8. Exception: An Array Can Contain a Primitive Value

PostgreSQL supports a special containment case: **an array can contain a primitive value**.

~~~sql
SELECT
    '["tech","sale"]'::jsonb @> '"sale"'::jsonb
      AS array_contains_primitive,
    '"sale"'::jsonb @> '["sale"]'::jsonb
      AS primitive_contains_array;
~~~

Typical results:

- Array contains primitive `"sale"`: `true`.
- Primitive contains array `["sale"]`: `false`.

This does **not** mean an arbitrary object contains a primitive buried deep inside that object.

### 8.1. Why Structured RHS Is Still Recommended

When filtering a table:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

clearly expresses "key `tags` contains `sale`", avoiding confusion about whether `sale` could appear elsewhere.

### 8.2. Containment Is Not Substring Search

~~~sql
SELECT
    '["sale"]'::jsonb @> '["sal"]'::jsonb AS substring_match;
~~~

Result `false`. JSONB containment checks **values/elements**, not substrings. For substring search, use appropriate text search operators, optionally paired with expression or trigram indexes depending on the workload.

## 9. Containment of Arrays Containing Objects

An application might store:

~~~json
{
  "lines": [
    {"sku":"A-01","qty":2,"price":50},
    {"sku":"B-02","qty":1,"price":80}
  ]
}
~~~

Query:

~~~sql
SELECT
    '{
      "lines": [
        {"sku":"A-01","qty":2,"price":50},
        {"sku":"B-02","qty":1,"price":80}
      ]
    }'::jsonb
    @> '{
      "lines": [
        {"sku":"A-01","qty":2}
      ]
    }'::jsonb
    AS has_matching_line;
~~~

Result `true`. The RHS only requires an object element with those minimal fields; the object on the left may have extra fields like `price`.

### 9.1. Do Not Confuse "Same Element Object" with Two Independent Elements

If business logic requires **the same line item to have SKU A-01 and qty 2**, writing:

~~~sql
WHERE doc @> '{"lines":[{"sku":"A-01","qty":2}]}'::jsonb
~~~

clearly states both conditions on **one line object**.

Do not replace it with two separate conditions like:

~~~sql
WHERE doc @> '{"lines":[{"sku":"A-01"}]}'::jsonb
  AND doc @> '{"lines":[{"qty":2}]}'::jsonb
~~~

because the SKU condition and the qty condition could be satisfied by **two different line objects**.

### 9.2. A Common Logic Bug

The best approach is to express the structure and co-occurrence of conditions accurately. For complex conditions, use JSONPath filters on the **same item** or normalize the array into a child table.

## 10. The Contained-By Operator <@

`left <@ right` is the reverse direction of `right @> left`.

~~~sql
SELECT
    '{"country":"VN"}'::jsonb
      <@ '{"country":"VN","name":"A"}'::jsonb
      AS subset_of_object;
~~~

Result `true`.

### 10.1. Two Equivalent Directions

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      @> '{"a":1}'::jsonb AS left_contains_right,
    '{"a":1}'::jsonb
      <@ '{"a":1,"b":2}'::jsonb AS right_is_contained;
~~~

Both test the same containment relationship, with **the operands swapped**.

### 10.2. Watch Index Selection

A GIN index on `doc` supports the **operators and operand side supported by its operator class**. The query:

~~~sql
WHERE doc @> '{"active":true}'::jsonb
~~~

is the natural pattern for a GIN index on `doc`.

Do not assume:

~~~sql
WHERE '{"active":true}'::jsonb @> doc
~~~

or rewriting with `doc <@ ...` will use the same index in the same way. Both semantics and index usage depend on **operator direction**.

### 10.3. <@ Is Useful for Subset Checks

~~~sql
SELECT
    '["sale"]'::jsonb <@ '["tech","sale"]'::jsonb
      AS sale_is_subset;
~~~

However, do not treat `<@` as a dedicated "key lookup" operator; for simple key existence checks, `?` is usually clearer.

## 11. Existence Operator ?: Keys at the Current Level

~~~sql
SELECT
    '{"sku":"KB-01","price":120}'::jsonb
      ? 'sku' AS sku_exists,
    '{"sku":"KB-01"}'::jsonb
      ? 'vendor' AS vendor_exists;
~~~

Results: `true` and `false`.

### 11.1. Checks the Key Only, Not the Value

~~~sql
SELECT
    '{"notes":null}'::jsonb ? 'notes'
      AS notes_key_exists,
    '{"notes":null}'::jsonb
      @> '{"notes":null}'::jsonb
      AS notes_is_json_null;
~~~

Both are `true`, yet they ask different questions:

- `? 'notes'`: the key is present, **regardless of its value**.
- `@> '{"notes":null}'`: the key is present and its value is **JSON null**.

### 11.2. ? Does Not Recurse Automatically

~~~sql
SELECT
    '{"vendor":{"country":"VN"}}'::jsonb
      ? 'country' AS top_level_country;
~~~

Result `false` because `country` is only inside the nested object.

### 11.3. Querying the Lab Table

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ? 'vendor'
ORDER BY product_id;
~~~

Selects documents that have a top-level `vendor` key, regardless of which keys exist inside `vendor`.

## 12. ? with JSON Arrays

On a **JSON array**, `?` checks for **string elements at the current level**.

~~~sql
SELECT
    '["tech","sale"]'::jsonb ? 'sale'
      AS array_has_sale,
    '["tech","sale"]'::jsonb ? 'office'
      AS array_has_office;
~~~

Results: `true`, `false`.

### 12.1. Do Not Expect ? to Match JSON Numbers

~~~sql
SELECT
    '[1,2,3]'::jsonb ? '2'
      AS numeric_array_has_text_two,
    '[1,2,3]'::jsonb @> '2'::jsonb
      AS numeric_array_contains_number_two;
~~~

`? '2'` checks for the **string** `"2"`, not the JSON number `2`. `@> '2'::jsonb` is appropriate when checking containment for a numeric value.

### 12.2. Does Not Inspect Keys Inside Array Objects

~~~sql
SELECT
    '[{"sku":"A-01"}]'::jsonb
    ? 'sku' AS array_of_objects_has_sku_at_top;
~~~

This does not look for `sku` inside each nested object. For that structure, use containment:

~~~sql
SELECT
    '[{"sku":"A-01"}]'::jsonb
    @> '[{"sku":"A-01"}]'::jsonb
    AS object_present;
~~~

### 12.3. Existence Operators Depend on Nesting Level

If `doc` is an object containing key `tags`, the predicate:

~~~sql
WHERE doc ? 'sale'
~~~

is **not** equivalent to:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

The first checks for a top-level key `sale` inside `doc`; the second checks for the string `sale` inside the `tags` array.

## 13. The ?| Operator: Any Key/Element Exists

`?|` takes a PostgreSQL `text[]` list and checks whether **at least one** key or string element exists at the current level.

~~~sql
SELECT
    '{"sku":"KB-01","price":120}'::jsonb
      ?| ARRAY['sku','name']
      AS has_sku_or_name;
~~~

Result `true`, because `sku` exists.

### 13.1. Finding Documents with vendor or notes

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ?| ARRAY['vendor','notes']
ORDER BY product_id;
~~~

The condition only requires **one** of the two keys.

### 13.2. Using with tags

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE (doc -> 'tags') ?| ARRAY['sale','office']
ORDER BY product_id;
~~~

This means: the `tags` array contains `sale` **or** `office`.

### 13.3. Operand Type Must Match

The right-hand side must be `text[]`:

~~~sql
-- PostgreSQL array type, not a JSON array:
ARRAY['sale','office']
~~~

Do not confuse:

~~~sql
'["sale","office"]'::jsonb
~~~

with `text[]`. PostgreSQL SQL arrays and JSONB arrays are different types.

## 14. The ?& Operator: All Keys/Elements Exist

~~~sql
SELECT
    '{"sku":"KB-01","price":120,"active":true}'::jsonb
      ?& ARRAY['sku','price']
      AS has_both_fields;
~~~

Result `true` because the object contains both `sku` and `price`.

### 14.1. Matching Multiple Tags Together

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE (doc -> 'tags') ?& ARRAY['tech','sale']
ORDER BY product_id;
~~~

In the lab, products `KB-01` and `MT-09` have both tags.

### 14.2. ?| and ?& Differ Only in Logical Quantifier

| Expression | Meaning |
| --- | --- |
| `? 'tech'` | Has `tech` |
| `?| ARRAY['tech','sale']` | Has `tech` **or** `sale` |
| `?& ARRAY['tech','sale']` | Has `tech` **and** `sale` |

### 14.3. Do Not Confuse ?& with Array Equality

~~~sql
SELECT
    '["tech","sale","office"]'::jsonb
      ?& ARRAY['tech','sale'] AS all_exist;
~~~

Result `true` even though the left-hand array also contains `office`. `?&` checks whether all listed string elements exist, not whether the two arrays are equal.

### 14.4. Empty Input Lists

Under logical quantifiers, "at least one in an empty list" has no element to satisfy it, whereas "all elements in an empty list" is vacuously true. In production SQL, handle empty input lists **explicitly according to business rules**, rather than letting operator edge cases surprise callers.

## 15. Operators and Nesting Levels: Comparison Table

Suppose:

~~~json
{
  "sku": "KB-01",
  "tags": ["tech", "sale"],
  "vendor": {
    "country": "VN"
  }
}
~~~

| Condition | True/False | Why? |
| --- | --- | --- |
| `doc ? 'sku'` | True | Top-level key `sku` |
| `doc ? 'country'` | False | `country` is nested inside `vendor` |
| `(doc -> 'vendor') ? 'country'` | True | Navigated to the `vendor` object |
| `doc ? 'sale'` | False | `sale` is not a top-level key |
| `(doc -> 'tags') ? 'sale'` | True | `sale` is a string element of `tags` |
| `doc @> '{"tags":["sale"]}'` | True | Structural containment |
| `doc @> '{"vendor":{"country":"VN"}}'` | True | Nested object containment |
| `doc @> '{"country":"VN"}'` | False | RHS requires `country` at top level |
| `doc ?& ARRAY['sku','tags']` | True | Both top-level keys are present |
| `doc ?| ARRAY['discount','sku']` | True | At least `sku` is present |

**Quick rule:** `?`, `?|`, and `?&` inspect the **current level**; `@>` matches the **RHS structure**, including any nested structures described.

## 16. Drilling Down with ->, ->>, #>, and #>>

| Operator | Return Type | When to Use |
| --- | --- | --- |
| `doc -> 'key'` | `jsonb` | Extract a key's JSONB value to continue using JSONB operators |
| `doc ->> 'key'` | `text` | Extract the value as plain text |
| `doc #> '{a,b}'` | `jsonb` | Extract JSONB at a multi-level path |
| `doc #>> '{a,b}'` | `text` | Extract text at a multi-level path |

### 16.1. Extracting a Sub-Object to Check a Key

~~~sql
SELECT
    product_id,
    doc #> '{vendor}' AS vendor_doc
FROM json_lab.products
WHERE (doc #> '{vendor}') ? 'country';
~~~

### 16.2. Extracting a Nested Field as Text for Comparison

~~~sql
SELECT
    product_id,
    doc #>> '{vendor,country}' AS vendor_country
FROM json_lab.products
WHERE doc #>> '{vendor,country}' = 'VN'
ORDER BY product_id;
~~~

### 16.3. Comparing Text vs. a JSONB String

~~~sql
SELECT
    '"VN"'::jsonb AS jsonb_string,
    ('"VN"'::jsonb #>> '{}') AS text_value;
~~~

One is a JSONB string and the other is SQL text. In applications, bind parameters and use the operator matching the type rather than mixing text and JSONB arbitrarily.

### 16.4. Invalid Paths Normally Return SQL NULL

When a field or element does not exist or the structure does not match, JSON access operators normally return **SQL NULL** rather than raising an error for a missing key. Keep this in mind when checking `IS NULL`.

## 17. Three States: Missing Key, JSON null, and SQL NULL

A very common logic bug is treating these three states as identical:

1. Document **does not have the key**.
2. Document **has the key** with value JSON `null`.
3. The entire column/expression is **SQL `NULL`**.

Example:

~~~sql
SELECT
    '{}'::jsonb ? 'notes'
      AS missing_has_key,
    '{"notes":null}'::jsonb ? 'notes'
      AS json_null_has_key;
~~~

Results: `false` and `true`.

### 17.1. Checking with -> and IS NULL

~~~sql
SELECT
    ('{}'::jsonb -> 'notes') IS NULL
      AS missing_is_sql_null,
    ('{"notes":null}'::jsonb -> 'notes') IS NULL
      AS json_null_is_sql_null;
~~~

Result:

- Missing key: `->` returns **SQL NULL**, so `IS NULL` is `true`.
- Key with JSON null: `->` returns a **JSONB null value**, not SQL NULL, so `IS NULL` is `false`.

### 17.2. ->> Loses Part of This Distinction

~~~sql
SELECT
    ('{}'::jsonb ->> 'notes') IS NULL
      AS missing_text_null,
    ('{"notes":null}'::jsonb ->> 'notes') IS NULL
      AS json_null_text_null;
~~~

With `->>`, both a missing key and JSON null evaluate to SQL NULL. Therefore, when you must distinguish **missing key** from **null key**, use `?` and/or `->` appropriately.

### 17.3. Checking JSON null via JSONB Equality

~~~sql
SELECT
    ('{"notes":null}'::jsonb -> 'notes')
      = 'null'::jsonb AS is_json_null;
~~~

Result `true`. This differs from:

~~~sql
WHERE (doc -> 'notes') IS NULL
~~~

which finds cases where the expression returns SQL NULL.

### 17.4. Querying All Three Cases on the Lab Table

Documents **having key `notes`**:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'notes'
ORDER BY product_id;
~~~

Documents with **JSON null** in `notes`:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"notes":null}'::jsonb
ORDER BY product_id;
~~~

Documents **missing key `notes`**:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE NOT (doc ? 'notes')
ORDER BY product_id;
~~~

Documents whose `notes` key holds JSON null are `1` and `9`. Document `3` has `notes` equal to the string `"used"`. The remaining documents lack `notes`.

### 17.5. A NOT NULL doc Column Still Allows JSON null

`doc jsonb NOT NULL` only forbids **SQL NULL for the entire `doc` column**. It does not prevent:

~~~sql
INSERT INTO json_lab.products(product_id, doc, created_at)
VALUES (
    11,
    'null'::jsonb,
    now()
);
~~~

The value `'null'::jsonb` is a valid JSONB document (JSON null), **distinct from SQL NULL**. If the application requires `doc` to be an object, add a constraint such as `CHECK (jsonb_typeof(doc) = 'object')`.

## 18. jsonb_typeof Helps Verify Types

The `jsonb_typeof(jsonb)` function returns the JSON type name:

~~~sql
SELECT
    jsonb_typeof('{"a":1}'::jsonb) AS object_type,
    jsonb_typeof('[1,2]'::jsonb) AS array_type,
    jsonb_typeof('"hello"'::jsonb) AS string_type,
    jsonb_typeof('42'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS boolean_type,
    jsonb_typeof('null'::jsonb) AS json_null_type;
~~~

Corresponding type names:

~~~text
object, array, string, number, boolean, null
~~~

### 18.1. SQL NULL Input

~~~sql
SELECT jsonb_typeof(NULL::jsonb) AS sql_null_type;
~~~

Result is SQL NULL (not the string `'null'`).

### 18.2. Checking That price Is a JSON Number

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    jsonb_typeof(doc -> 'price') AS price_type
FROM json_lab.products
ORDER BY product_id;
~~~

In the lab, `CB-08` has `price_type = 'string'`, while most other rows have `'number'`.

### 18.3. CHECK Constraints Protecting Types

For a system requiring `price` to be a number, you can add CHECK constraints:

~~~sql
CREATE TABLE json_lab.validated_docs (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CONSTRAINT doc_is_object
      CHECK (jsonb_typeof(doc) = 'object'),
    CONSTRAINT doc_has_numeric_price
      CHECK (
        doc ? 'price'
        AND jsonb_typeof(doc -> 'price') = 'number'
      )
);
~~~

This catches mistyped input early. For more complex rules, combine application-layer schema validation with database constraints.

## 19. The Equality Operator = on JSONB

JSONB supports equality by **structural value**, without requiring identical original JSON text.

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      = '{"b":2,"a":1}'::jsonb
      AS same_object_different_key_order;
~~~

Result `true`. The order in which keys are written in an object does not make two JSONB values unequal.

### 19.1. Equality Differs from Containment

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb
      = '{"a":1}'::jsonb
      AS same_value,
    '{"a":1,"b":2}'::jsonb
      @> '{"a":1}'::jsonb
      AS contains;
~~~

`same_value = false`, while `contains = true`.

### 19.2. Array Equality Respects Order

~~~sql
SELECT
    '["tech","sale"]'::jsonb
      = '["sale","tech"]'::jsonb
      AS equal_arrays,
    '["tech","sale"]'::jsonb
      @> '["sale","tech"]'::jsonb
      AS containing_arrays;
~~~

Results: `false` and `true`.

### 19.3. Array Equality Respects Multiplicity

~~~sql
SELECT
    '["sale"]'::jsonb
      = '["sale","sale"]'::jsonb
      AS equality_with_duplicates,
    '["sale"]'::jsonb
      @> '["sale","sale"]'::jsonb
      AS containment_with_duplicates;
~~~

Results: `false` and `true`. **Do not use `@>` in place of `=` when exact array matching is required.**

### 19.4. JSONB Numeric Normalization

~~~sql
SELECT
    '{"qty":1}'::jsonb
      = '{"qty":1.0}'::jsonb
      AS numeric_value_equal;
~~~

Under JSONB number comparison semantics, `1` and `1.0` are treated as **the same numeric value**. This differs from byte-for-byte comparison of original JSON text.

### 19.5. A JSONB String Never Equals a JSONB Number

~~~sql
SELECT
    '"1"'::jsonb = '1'::jsonb AS string_equals_number;
~~~

Result `false`. Never assume a numeric string equals a JSON number.

## 20. Inequality <> and NULL-Aware Comparisons

~~~sql
SELECT
    '{"a":1}'::jsonb
      <> '{"a":2}'::jsonb
      AS different_values;
~~~

Result `true`.

### 20.1. SQL NULL Makes Standard Comparisons Unknown

~~~sql
SELECT
    NULL::jsonb = '{"a":1}'::jsonb
      AS normal_equal,
    NULL::jsonb <> '{"a":1}'::jsonb
      AS normal_not_equal;
~~~

Both results are **SQL NULL/unknown**, not false or true.

### 20.2. IS DISTINCT FROM for Null-Safe Comparison

~~~sql
SELECT
    NULL::jsonb IS DISTINCT FROM '{"a":1}'::jsonb
      AS null_differs_from_object,
    NULL::jsonb IS NOT DISTINCT FROM NULL::jsonb
      AS both_sql_null;
~~~

These SQL comparisons handle SQL NULL intentionally.

### 20.3. JSON null Does Not Equal SQL NULL

~~~sql
SELECT
    'null'::jsonb IS DISTINCT FROM NULL::jsonb
      AS json_null_differs_from_sql_null;
~~~

Result `true`.

### 20.4. When to Use =

Use equality when comparing an **entire JSONB value**:

~~~sql
WHERE doc -> 'active' = 'true'::jsonb
~~~

However, when targeting one field inside a very large object, scalar extraction or containment:

~~~sql
WHERE doc @> '{"active":true}'::jsonb
~~~

may fit a **full-document GIN index** better.

## 21. Ordering Operators <, <=, >, >=

PostgreSQL defines **B-tree comparison semantics** for `jsonb`, allowing comparisons:

~~~sql
SELECT
    '2'::jsonb < '10'::jsonb AS two_lt_ten,
    '"2"'::jsonb < '"10"'::jsonb AS text_two_lt_ten;
~~~

For JSONB numbers, `2 < 10` is `true`. For JSONB strings, string comparison follows text rules rather than numeric rules; do not treat `"2"` and `"10"` as numbers.

### 21.1. Ordering Across JSONB Types

Under JSONB B-tree ordering rules, type groups follow the general precedence:

~~~text
Object > Array > Boolean > Number > String > JSON null
~~~

Within the same group, PostgreSQL compares as follows:

- Numbers compare numerically.
- Strings compare using appropriate string comparison semantics.
- Booleans compare by boolean value (`true > false`).
- Arrays compare by structure, element types, and order.
- Objects compare by normalized key/value structure.

### 21.2. Do Not Use JSONB Type Ordering as Business Ordering

~~~sql
SELECT product_id, doc -> 'price' AS price
FROM json_lab.products
ORDER BY doc -> 'price';
~~~

This query sorts by **JSONB values**, not a uniformly typed `numeric` column. If rows mix JSON numbers and JSON strings, cross-type ordering will not match real numeric prices.

### 21.3. Comparing Values of the Same Type

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
ORDER BY product_id;
~~~

Here both valid document `price` values and the RHS are JSON numbers. The condition excludes rows with JSON string prices.

### 21.4. Never Skip Type Checks on Heterogeneous Data

~~~sql
WHERE (doc -> 'price') > '50'::jsonb
~~~

can produce surprising results if `price` is a string, boolean, object, or array, because JSONB defines **cross-type ordering** across different JSON types.

For monetary amounts and quantities, a constrained `numeric` column is usually clearer and easier to optimize when the field is core to business logic.

## 22. Avoid Comparing Numbers as Text

~~~sql
SELECT
    '100'::text > '20'::text AS lexical_comparison,
    100::numeric > 20::numeric AS numeric_comparison;
~~~

Text comparison yields lexicographical order, not numerical order.

### 22.1. When ->> Returns Text

~~~sql
SELECT
    product_id,
    doc ->> 'price' AS text_price
FROM json_lab.products
ORDER BY doc ->> 'price';
~~~

This `ORDER BY` sorts as strings. Never use it for accurate price reports when numbers vary in digit count.

### 22.2. A Safe Approach Accepting Only JSON Numbers

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
      ELSE NULL
    END AS numeric_price
FROM json_lab.products
ORDER BY numeric_price DESC NULLS LAST;
~~~

The `CASE` expression states the conversion branch explicitly. Do not cast arbitrary strings to `numeric` without input validation rules.

### 22.3. Using a More Stable Column Type

In real applications, consider:

~~~sql
CREATE TABLE json_lab.stock_items (
    item_id bigint PRIMARY KEY,
    price numeric(12,2) NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Prices are enforced by PostgreSQL as `numeric`, while flexible attributes stay in JSONB. This avoids heterogeneous comparisons and provides better index and statistics support.

## 23. Sets, GROUP BY, and DISTINCT with JSONB

Because JSONB has equality semantics, you can use:

~~~sql
SELECT
    doc -> 'active' AS active_jsonb,
    COUNT(*) AS n
FROM json_lab.products
GROUP BY doc -> 'active'
ORDER BY active_jsonb;
~~~

### 23.1. GROUP BY on Structures

~~~sql
SELECT
    doc -> 'vendor' AS vendor,
    COUNT(*) AS n
FROM json_lab.products
GROUP BY doc -> 'vendor';
~~~

Two `vendor` objects that are equal under JSONB equality are grouped together regardless of key order in the original JSON text.

### 23.2. COUNT(DISTINCT ...)

~~~sql
SELECT
    COUNT(DISTINCT doc -> 'category') AS categories
FROM json_lab.products;
~~~

Counts distinct `category` values as JSONB expressions.

### 23.3. SQL NULL and GROUP BY

When a path is missing, `doc -> 'vendor'` returns SQL NULL, so rows missing `vendor` are grouped into the SQL NULL bucket. A document with `"vendor": null` yields **JSONB null**, forming a separate bucket from SQL NULL.

If business logic distinguishes "missing key" from "null key," preserve `doc ? 'vendor'` in your grouping expression or filter.

## 24. JSONPath When Conditions Go Deeper Than Containment

PostgreSQL supports **SQL/JSON path** expressions to select items and evaluate conditions on nested elements. Two important operators for `jsonb` are:

- `@?`: asks whether any item matches the path/filter expression.
- `@@`: evaluates a JSONPath predicate to a boolean result (or SQL NULL if the path expression does not return a boolean as expected).

### 24.1. JSONPath Existence

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @? '$.tags[*] ? (@ == "sale")'
ORDER BY product_id;
~~~

Meaning:

1. `$.tags` accesses `tags` from the root.
2. `[*]` iterates over elements in the array.
3. `? (@ == "sale")` retains elements matching the string `"sale"`.
4. `@?` returns true if at least one item matches.

### 24.2. Filtering Within the Same Element Object

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
ORDER BY product_id;
~~~

On the lab data, document `PL-10` contains a size with `units = 5` and matches.

Crucial point: the filter `@.units >= 5` applies to **each individual size object**, without accidentally mixing `units` across separate objects.

### 24.3. Using @@ with a Predicate

~~~sql
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @@ '$.price > 50'
ORDER BY product_id;
~~~

`@@` evaluates a JSONPath **predicate** expression. With heterogeneous data like `"price":"20"`, understand JSONPath type rules and validate input; do not assume numeric strings behave like JSON numbers.

### 24.4. @? and @@ Cannot Be Swapped Mechanically

~~~sql
doc @? '$.tags[*] ? (@ == "sale")'
~~~

means "the path yields at least one matching item."

~~~sql
doc @@ '$.active == true'
~~~

means "the JSONPath predicate expression evaluates to true."

JSONPath has specific modes and rules for multiple results and missing fields. Never swap `@?` and `@@` while keeping the exact same path expression and assume identical behavior.

### 24.5. Some Errors Are Suppressed

`@?` and `@@` suppress certain structural and type errors inside JSONPath according to PostgreSQL's documented semantics, which can be handy on heterogeneous data. Still, never rely on that in place of proper schema validation or to hide ingestion errors.

## 25. When Is @> Enough, and When Is JSONPath Needed?

| Requirement | Sensible Expression |
| --- | --- |
| `vendor.country = VN` | `doc @> '{"vendor":{"country":"VN"}}'` |
| `tags` contains `sale` | `doc @> '{"tags":["sale"]}'` |
| Top-level key `notes` exists | `doc ? 'notes'` |
| Nested `vendor` has key `country` | `(doc -> 'vendor') ? 'country'` |
| Has a size with `units >= 5` | `doc @? '$.attributes.sizes[*] ? (@.units >= 5)'` |
| Compare JSON number `price > 50` | JSONPath predicate or type-checked numeric expression |
| Whole document equals structure X | `doc = X::jsonb` |

### 25.1. @> Is Readable for Exact Structure Matching

When every condition is "contains these key/value pairs," `@>` is concise, clear, and well supported by GIN indexes.

### 25.2. JSONPath Is Stronger but Requires Care

JSONPath can express ranges, array filters, deep existence, and multi-branch paths. In return:

- You must learn path and type semantics.
- Not every JSONPath expression is efficiently indexed.
- Complex queries are harder to verify than simple containment expressions.

### 25.3. Relational Tables May Still Be Better

If you frequently filter `size.units >= 5` and join `size_id` to another table, extracting lines/sizes into a relational child table with foreign keys and numeric indexes can beat repeatedly scanning large JSONB arrays.

## 26. GIN Indexes for JSONB

PostgreSQL provides the **GIN (Generalized Inverted Index)** access method, suited for values like JSONB that contain many searchable components.

~~~sql
CREATE INDEX idx_products_doc_gin
ON json_lab.products
USING gin (doc);
~~~

For `jsonb` with GIN, the default opclass is `jsonb_ops`.

### 26.1. Which Operators Does GIN Help?

GIN `jsonb_ops` supports commonly used operators:

- `@>`.
- `?`, `?|`, `?&`.
- `@?`, `@@` for supported JSONPath patterns.

Do not assume GIN accelerates **every JSONB-related expression** such as whole-document equality, arbitrary ordering comparisons, or text casts.

### 26.2. Containment Queries Can Use GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb;
~~~

When the planner estimates it is beneficial, the plan may show `Bitmap Index Scan` on GIN paired with `Bitmap Heap Scan` to fetch tuples.

### 26.3. Existence Queries Can Use GIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc ?& ARRAY['sku','price'];
~~~

GIN `jsonb_ops` supports the `?&` operator.

### 26.4. Tiny Tables Still Use Seq Scan

With only ten rows, PostgreSQL rightly chooses `Seq Scan` because reading the entire table is cheaper. **Skipping an index on a small table does not prove the index is broken.**

## 27. jsonb_ops and jsonb_path_ops

Two common GIN operator classes:

~~~sql
-- Default opclass, supporting a broad set of operators:
CREATE INDEX idx_products_doc_ops
ON json_lab.products
USING gin (doc jsonb_ops);

-- Alternative opclass, narrower operator set:
CREATE INDEX idx_products_doc_path
ON json_lab.products
USING gin (doc jsonb_path_ops);
~~~

### 27.1. Key Support Matrix

| Index-Supported Operator | GIN `jsonb_ops` | GIN `jsonb_path_ops` |
| --- | :---: | :---: |
| `@>` | Yes | Yes |
| `?` | Yes | No |
| `?|` | Yes | No |
| `?&` | Yes | No |
| `@?` | Yes, depending on path | Yes, depending on path |
| `@@` | Yes, depending on path | Yes, depending on path |
| Whole-doc JSONB equality `=` | Not a matching GIN strategy | No |
| JSONB ordering `<` / `>` | No | No |

### 27.2. Why Is jsonb_path_ops Useful?

`jsonb_path_ops` indexes hashed value paths in a specialized way, often making it **smaller and more selective** for matching containment and path queries.

However, it **lacks** top-level key-existence support like `jsonb_ops`.

### 27.3. Choosing by Workload

If the application primarily runs:

~~~sql
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
~~~

then either opclass is a candidate.

If the application frequently runs:

~~~sql
WHERE doc ? 'vendor'
WHERE doc ?| ARRAY['stock','notes']
~~~

then `jsonb_ops` has the required operator support.

### 27.4. Conditions with Empty Objects

Structures such as:

~~~sql
WHERE doc @> '{"attributes":{}}'::jsonb
~~~

require special evaluation. `jsonb_path_ops` does not emit entries for certain empty structures with no leaf values, so queries like this can be inefficient despite a smaller index.

### 27.5. Do Not Maintain All Indexes Without Justification

In this lesson we create multiple indexes for illustration. In production, every index adds:

- Storage footprint.
- Insert, update, and delete overhead.
- GIN maintenance and WAL volume.
- Cache pressure and rebuild time.

Choose an index set based on **query frequency, selectivity, write rate, and `EXPLAIN` metrics**.

## 28. Full-Document GIN vs. Expression GIN

Suppose you have:

~~~sql
CREATE INDEX idx_products_doc_gin
ON json_lab.products USING gin (doc);
~~~

The query:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

applies `@>` directly to the `doc` column, matching the full-document index.

However:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

applies `?` to the **expression `doc -> 'tags'`**, not directly to `doc`. The planner will not automatically use the full-document GIN index for that expression.

### 28.1. Expression GIN Index

~~~sql
CREATE INDEX idx_products_tags_gin
ON json_lab.products
USING gin ((doc -> 'tags'));
~~~

Matching query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE (doc -> 'tags') ? 'sale';
~~~

This is an important demonstration that **the indexed expression must match the SQL operand being queried**.

### 28.2. Choosing Between the Two Query Forms

To find `sale` tags, you can write:

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

to use the full-document GIN index, or:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

with a dedicated index on `tags`.

Both can return the same rows **when the schema guarantees `tags` is always a string array**, but do not treat them as identical on heterogeneous JSON (missing `tags`, `tags` as an object, or non-string values).

### 28.3. Does an Expression Index Save or Add Cost?

A targeted index on `tags` can be smaller than a full-document index if `tags` is a small fraction of the document. Yet if you also query `vendor`, `attributes`, and other keys frequently, maintaining many separate expression indexes also carries overhead.

## 29. B-tree Indexes for Equality and Ordering

JSONB has B-tree comparison semantics, so a B-tree index can be created:

~~~sql
CREATE INDEX idx_products_doc_btree
ON json_lab.products USING btree (doc);
~~~

### 29.1. Whole-Document Equality Lookup

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc = '{"sku":"ONLY","active":true}'::jsonb;
~~~

At the operator level, B-tree supports equality on JSONB. However, JSONB values can be large and change often: **a B-tree on the entire document is rarely the right first choice** for querying individual attributes.

### 29.2. B-tree for ORDER BY doc

~~~sql
SELECT product_id, doc
FROM json_lab.products
ORDER BY doc
LIMIT 5;
~~~

This SQL is valid under **JSONB B-tree ordering**, though that order rarely matches business ordering by product name, price, or timestamp.

### 29.3. GIN Does Not Provide Sorting Like B-tree

GIN `jsonb_ops` does not provide sort order for:

~~~sql
ORDER BY doc ->> 'sku'
~~~

If workloads frequently sort by SKU, consider a **dedicated column or B-tree expression index** on SKU.

### 29.4. Index Entry Size Limits

Large JSONB documents can exceed B-tree index entry size limits in addition to bloating storage and overhead. Never create a whole-document B-tree just because JSONB supports `=`.

## 30. B-tree Expression Index for a Text Key

~~~sql
CREATE INDEX idx_products_sku
ON json_lab.products ((doc ->> 'sku'));
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc ->> 'sku' = 'KB-01';
~~~

### 30.1. Text Equality Differs from Containment

~~~sql
WHERE doc ->> 'sku' = 'KB-01'
~~~

can be served by a B-tree expression index on `doc ->> 'sku'`.

~~~sql
WHERE doc @> '{"sku":"KB-01"}'::jsonb
~~~

is a containment check that can be served by a full-document GIN index.

Both queries match the same records on clean structures, but their **access paths** and behavior on heterogeneous data differ.

### 30.2. Indexing a Nested Scalar

~~~sql
CREATE INDEX idx_products_vendor_country
ON json_lab.products (
    (doc #>> '{vendor,country}')
);
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc #>> '{vendor,country}' = 'VN';
~~~

### 30.3. One Logical Filter Can Have Multiple Access Paths

Filtering by vendor country could use either full-document GIN containment or a scalar B-tree expression index. Which performs better depends on data size, selectivity, projected output, and index footprints.

## 31. Numeric Expression Indexes and Heterogeneous Data

Some applications need:

~~~sql
WHERE price_numeric > 50
ORDER BY price_numeric DESC
~~~

If `price` is inside JSONB, control its type.

### 31.1. JSON Number Type

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
ORDER BY product_id;
~~~

This uses the JSONB comparison operator when both sides are numbers. When arithmetic or price sorting is needed, a `numeric` column is usually much easier to maintain.

### 31.2. Guarded Type Conversion

~~~sql
SELECT
    product_id,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
      ELSE NULL
    END AS price_numeric
FROM json_lab.products
ORDER BY price_numeric DESC NULLS LAST;
~~~

### 31.3. Generated Column or Relational Column

If price is heavily filtered and sorted, consider promoting `price` to a constrained `numeric` column; if JSONB remains the source, you can evaluate a generated column/validation subject to PostgreSQL version and immutability rules.

Never treat a JSONB GIN index as a drop-in replacement for a B-tree range index on numbers.

## 32. Partial Indexes and Existence Conditions

Suppose only 10% of documents in a real system have a `vendor` key, and queries frequently read that subset:

~~~sql
CREATE INDEX idx_products_has_vendor
ON json_lab.products (created_at)
WHERE doc ? 'vendor';
~~~

Query:

~~~sql
SELECT product_id, created_at
FROM json_lab.products
WHERE doc ? 'vendor'
ORDER BY created_at DESC;
~~~

The planner can consider this partial B-tree index if the query implies the predicate and benefits from the sort order.

### 32.1. A Partial Index Is Not GIN

The index above uses B-tree key `created_at`, while `doc ? 'vendor'` is the **predicate selecting which rows belong in the index**.

### 32.2. Queries Must Imply the Predicate

If a query does not include a condition from which the planner can prove `doc ? 'vendor'`, PostgreSQL cannot safely ignore rows excluded from the partial index.

### 32.3. Avoid Many Rarely Used Partial Indexes

Even a partial index consumes storage and write maintenance. Do not create a partial index for **every JSON key** without real workload justification.

## 33. JSONPath and GIN: Not Every Path Is Optimized

GIN `jsonb_ops` and `jsonb_path_ops` support `@?` / `@@` for certain JSONPath forms. In practice, PostgreSQL can extract specific equality clauses such as:

~~~text
accessor_chain == constant
~~~

to build GIN search keys.

### 33.1. Indexable Equality Example

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @? '$.vendor.country ? (@ == "VN")';
~~~

This path applies a constant equality condition on an explicit path; GIN can support it depending on opclass and plan.

### 33.2. Complex Range Comparisons

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

may not extract search keys as effectively as equality. **Valid JSONPath syntax does not guarantee an index will reduce rows scanned.**

### 33.3. Operators Inside JSONPath Differ from SQL Operators

Inside a JSONPath string:

~~~text
$.price > 50
~~~

is a JSONPath expression, not SQL:

~~~sql
(doc -> 'price') > '50'::jsonb
~~~

The two mechanisms have different semantics, types, and indexability. Do not swap them just because both use `>`.

### 33.4. Inspect the Real Plan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @? '$.tags[*] ? (@ == "sale")';
~~~

Look for `Bitmap Index Scan`, `Index Cond`, `Recheck Cond`, `Filter`, and `Buffers` when applicable. On 10 rows, `Seq Scan` is completely normal.

## 34. Using EXPLAIN ANALYZE Properly

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb;
~~~

Fields to inspect:

| Field | Operational Meaning |
| --- | --- |
| `Seq Scan` | Sequential scan; often optimal for small tables or high match rates |
| `Bitmap Index Scan` | Uses index to collect matching tuple locations |
| `Bitmap Heap Scan` | Fetches heap rows from the bitmap |
| `Index Cond` | Condition enforced by the index access path |
| `Recheck Cond` | Condition re-verified per plan/index rules |
| `Filter` | Additional predicate checked on fetched rows |
| `Rows Removed by Filter` | Rows discarded at that node |
| `actual rows`, `loops` | Average actual rows per loop and number of loops |
| `Buffers: shared hit/read` | Shared buffer block hits and disk/OS reads |
| `Planning Time` / `Execution Time` | Measured planning and execution durations |

### 34.1. Why Does Recheck Cond Appear?

Some GIN/bitmap access paths must recheck predicates on candidate tuples depending on the operator and bitmap granularity (such as lossy pages). Never conclude GIN "is not working" just because `Recheck Cond` appears.

### 34.2. Buffers Are Not Row Counts

`shared hit=25` does not mean PostgreSQL read 25 products. One page holds multiple tuples, and index and heap pages incur separate buffer accesses.

### 34.3. Execution Time Is Not API Latency

`EXPLAIN ANALYZE` runs server-side with timing instrumentation overhead; full API latency also includes network transit, driver decoding, JSON serialization, and application work.

### 34.4. Do Not Decide from a Single Run

Run multiple trials on production-like data. Cache warmth, document count, JSON nesting depth, and key frequency strongly influence GIN effectiveness.

## 35. Generating More Data to Observe Index Behavior

A 10-row lab is too small to draw performance conclusions. To test with **20,000 synthetic documents**, run only in a lab database:

~~~sql
INSERT INTO json_lab.products (
    product_id, doc, created_at
)
SELECT
    g + 1000,
    jsonb_build_object(
      'sku', 'AUTO-' || lpad(g::text, 6, '0'),
      'active', g % 5 <> 0,
      'price', 10 + (g % 1000),
      'tags',
        CASE
          WHEN g % 10 = 0
          THEN jsonb_build_array('tech','sale')
          ELSE jsonb_build_array('tech')
        END,
      'vendor', jsonb_build_object(
        'country',
        CASE
          WHEN g % 20 = 0 THEN 'VN'
          ELSE 'US'
        END,
        'name', 'auto-vendor'
      )
    ),
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
       + g * INTERVAL '1 second'
FROM generate_series(1, 20000) AS s(g);

ANALYZE json_lab.products;
~~~

### 35.1. Selectivity Matters

In this generated dataset:

- Roughly 10% have tag `sale`.
- Roughly 5% have `vendor.country = VN`.
- Nearly all have key `vendor`.

GIN helps much more when filtering on a rare attribute than on an attribute present in nearly every row.

### 35.2. Limitations of Synthetic Data

Uniform generated data has few anomalies. Production may have:

- Very large documents with hundreds of keys.
- Rare keys, skewed common keys, nested arrays.
- Frequent updates.
- Mixed value types from inconsistent producers.

Measure on real or representative data before committing to an index.

### 35.3. Comparing Opclasses

If a workload mixes containment and key existence:

1. Measure a baseline with current indexes.
2. Measure in the lab with GIN `jsonb_ops`.
3. Measure in the lab with `jsonb_path_ops` for containment.
4. Compare key-existence queries (which `path_ops` does not support).
5. Weigh index size, write speed, and cache usage.

Do not measure a single fast `@>` query and conclude `jsonb_path_ops` is better for the whole system.

## 36. Choosing Operators Based on Business Requirements

### 36.1. Is vendor Information Present?

~~~sql
WHERE doc ? 'vendor'
~~~

No need to check which vendor.

### 36.2. Is Vendor Country VN?

~~~sql
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
~~~

Or scalar comparison:

~~~sql
WHERE doc #>> '{vendor,country}' = 'VN'
~~~

### 36.3. Does It Have Tag sale?

~~~sql
WHERE doc @> '{"tags":["sale"]}'::jsonb
~~~

Or:

~~~sql
WHERE (doc -> 'tags') ? 'sale'
~~~

### 36.4. Does Either Key Exist?

~~~sql
WHERE doc ?| ARRAY['notes','vendor']
~~~

### 36.5. Are All Required Keys Present?

~~~sql
WHERE doc ?& ARRAY['sku','active','price']
~~~

**This only checks key existence**, not that each key's type or value is valid. When schema validation is required, add `CHECK` constraints or appropriate JSON schema validation.

### 36.6. Is Price Numeric and Greater Than 50?

~~~sql
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND (doc -> 'price') > '50'::jsonb
~~~

When accurate arithmetic is required, a `numeric` column with ingestion validation is usually a safer design.

### 36.7. Is There a size Element with units >= 5?

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

Do not split conditions across separate array elements when business rules require the same element to satisfy both.

## 37. Comparing @>, ?, and = in One Example

Document:

~~~json
{"a":1,"b":2}
~~~

| Expression | Result | Meaning |
| --- | --- | --- |
| `doc ? 'a'` | true | Key `a` exists |
| `doc ? 'c'` | false | Key `c` does not exist |
| `doc @> '{"a":1}'` | true | Contains pair `a=1` |
| `doc @> '{"a":3}'` | false | `a` exists but has a different value |
| `doc = '{"a":1}'` | false | Whole object also has `b` |
| `doc = '{"b":2,"a":1}'` | true | Equal objects, ignoring key order |
| `doc <@ '{"a":1,"b":2,"c":3}'` | true | `doc` is a structural subset |

### 37.1. Get the Logic Right Before Optimizing

Do not replace `doc ? 'a'` with `doc @> '{"a":null}'`, because the second only matches key `a` **with value JSON null**.

Do not replace `doc = X` with `doc @> X` if business rules require **the document to have no extra keys**.

## 38. Data Type Issues and Validation

JSONB flexibility also means the same key can carry different types:

~~~json
{"price":20}
{"price":"20"}
{"price":null}
{"price":{"amount":20}}
~~~

A query:

~~~sql
WHERE doc ? 'price'
~~~

matches **all four** because it only checks key existence.

~~~sql
WHERE doc @> '{"price":20}'::jsonb
~~~

matches only the JSON number `20`, not the string `"20"`.

### 38.1. JSON Schema at Ingestion

Define:

- Which fields are mandatory?
- Which JSON types are allowed?
- What does NULL mean? Is it distinct from missing?
- Can arrays be empty?
- What bounds apply to numeric values?
- Should objects reject extra keys?

### 38.2. Simple CHECK Constraints

~~~sql
CREATE TABLE json_lab.events_checked (
    event_id bigint PRIMARY KEY,
    payload jsonb NOT NULL,
    CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (payload ?& ARRAY['type','version']),
    CHECK (jsonb_typeof(payload -> 'version') = 'number')
);
~~~

This validates only part of the schema. A row with `type` set to JSON null still has the `type` key and passes the second CHECK unless additional constraints are added.

### 38.3. JSONB Does Not Replace Foreign Keys

If:

~~~json
{"customer_id":1234}
~~~

is stored inside JSONB, PostgreSQL **does not automatically verify** that customer 1234 exists in `customers` the way a `FOREIGN KEY` on a relational column does.

When referential integrity matters, keep foreign keys in explicitly typed columns or design an enforcement mechanism that is genuinely sound.

## 39. Parameterized Queries and JSONB

Applications should bind parameters rather than concatenating JSON strings into SQL.

Example with a prepared statement:

~~~sql
PREPARE find_matching_docs(jsonb) AS
SELECT
    product_id,
    doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> $1;

EXECUTE find_matching_docs(
    '{"vendor":{"country":"VN"}}'::jsonb
);
~~~

### 39.1. Bind with the Proper jsonb Type

When a driver receives JSON input as a string, ensure PostgreSQL knows the parameter is `jsonb` for `@>`. Many drivers provide dedicated JSONB binding APIs, or SQL can cast the parameter cleanly.

### 39.2. Never Build SQL from Untrusted Keys

Never write:

~~~text
"... WHERE doc ? '" + userInput + "'"
~~~

as it introduces SQL injection vulnerabilities. Use bind variables with fixed queries and validate application keys/paths.

### 39.3. Generic Plans and Selectivity

Prepared statements may use generic or custom plans depending on context. If one JSONB predicate is rare and another is very common, a single generic plan might not be optimal for every parameter value. Test real workloads and plans rather than abandoning parameterization.

### 39.4. User-Supplied JSONPath

If users are allowed to submit arbitrary JSONPath expressions, limit scope, cost, and permitted paths. Parameterization prevents SQL injection, but **does not prevent CPU-heavy queries or scanning huge documents**.

## 40. Common Mistakes

### Mistake 1. Thinking @> Only Checks Key Existence

`@> '{"k":1}'` checks the value `1` as well; `? 'k'` checks key existence alone.

### Mistake 2. Thinking ? Traverses All JSON Levels

`doc ? 'country'` does not find `country` nested under `vendor`. Use `(doc->'vendor') ? 'country'` or structural containment.

### Mistake 3. Using doc ? 'sale' to Find a Tag

`sale` is inside the `tags` array, not a top-level key. Use `(doc->'tags') ? 'sale'` or `@> '{"tags":["sale"]}'`.

### Mistake 4. Thinking ? Finds a JSON Number in an Array

`'[1,2]'::jsonb ? '2'` looks for the string `"2"`, not the number `2`. Use containment with a JSON number of the right type.

### Mistake 5. Confusing ?| and ?&

`?|` requires **at least one**; `?&` requires **all**.

### Mistake 6. Passing a JSON Array Instead of text[] to ?| / ?&

The RHS of both operators is PostgreSQL `text[]`, such as `ARRAY['a','b']`.

### Mistake 7. Assuming Array Order Affects Containment

`["a","b"] @> ["b","a"]` is true, whereas equality between arrays in different orders is false.

### Mistake 8. Counting Duplicate Elements with @>

JSONB containment does not express full multiset multiplicity on arrays. If you need "two occurrences of `sale`," write logic that actually counts elements.

### Mistake 9. Matching a Nested Object with a Top-Level Object

`{"vendor":{"country":"VN"}} @> {"country":"VN"}` is false. The RHS must mirror the nested path.

### Mistake 10. Confusing Missing Keys with JSON null

`doc ? 'notes'` is true when `notes` is JSON null, and false when the key is missing.

### Mistake 11. Using ->> IS NULL to Distinguish Missing vs. JSON null

`->>` returns SQL NULL in both cases. Combine `?` or `->` when the distinction matters.

### Mistake 12. Thinking NOT NULL on a jsonb Column Forbids JSON null

`NOT NULL` forbids SQL NULL for the column; `'null'::jsonb` is still a valid JSONB value.

### Mistake 13. Comparing Numeric Strings with Numbers

JSON string `"20"` differs from JSON number `20`. Price queries must validate types or use a `numeric` column.

### Mistake 14. Using ORDER BY doc to Sort Prices

JSONB B-tree ordering follows JSONB type/structure rules, not business pricing or product-name rules.

### Mistake 15. Thinking GIN Supports JSONB = and ORDER BY

GIN `jsonb_ops` focuses on containment/existence/path operators; it does not replace B-tree equality, range, or sort indexes.

### Mistake 16. Choosing jsonb_path_ops and Still Using ?

`jsonb_path_ops` does not index `?`, `?|`, or `?&`. If the workload needs those operators, consider `jsonb_ops`.

### Mistake 17. Thinking Expression ? Automatically Uses Full-Document GIN

`(doc->'tags') ? 'sale'` operates on an expression. A GIN index on `doc` does not necessarily serve it; create a matching expression index or rewrite as doc containment.

### Mistake 18. Thinking Every JSONPath @? / @@ Uses an Index

Only certain path patterns yield GIN search keys. Complex ranges or paths may still scan heavily.

### Mistake 19. Creating Many GIN Indexes Without Workload Justification

Each GIN index consumes storage, write throughput, WAL, and maintenance. Keep only indexes proven useful.

### Mistake 20. Judging Indexes from a Ten-Row Table

Seq Scan is usually cheapest on tiny tables. Benchmark on representative data.

### Mistake 21. Replacing Every Relational Column with JSONB

Lacking explicit constraints, FKs, and statistics can make data unreliable and queries hard to optimize.

### Mistake 22. Concatenating Input JSON into SQL Strings

Creates SQL injection risk and quoting bugs. Use parameter binding with the proper `jsonb` type.

### Mistake 23. Using @> Instead of = to Check Exact Document Equality

Containment allows extra keys or array elements. Equality tests exact structural value equivalence.

### Mistake 24. Comparing Null Using = NULL

`= NULL` evaluates to unknown. Use `IS NULL` or `IS DISTINCT FROM` for SQL NULL, and `'null'::jsonb` for JSON null.

## 41. Practice Exercises

Exercises use the `json_lab` schema. For index exercises, run them only in a lab database; production requires benchmarks and proper DDL procedures.

### Exercise 1. Distinguishing @> and =

Explain the output:

~~~sql
SELECT
  '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb,
  '{"a":1,"b":2}'::jsonb =  '{"a":1}'::jsonb;
~~~

### Exercise 2. Nested Vendor

Write a query finding products with `vendor.country = 'VN'` using containment.

### Exercise 3. Top-Level Key

Write a query finding documents that have the `vendor` key regardless of value.

### Exercise 4. Key Inside vendor

Explain why `doc ? 'country'` fails to find `country` inside `vendor`. Write the correct query.

### Exercise 5. Tag sale

Write two ways to find products with tag `sale`: one using `@>`, and one using `?` on the child array.

### Exercise 6. Either Tag

Write a condition matching tag `tech` **or** `office` using `?|`.

### Exercise 7. Both Tags

Write a condition matching tag `tech` **and** `sale` using `?&`.

### Exercise 8. Required Keys

Write a condition checking that the JSON object has all three top-level keys `sku`, `price`, and `active`.

### Exercise 9. RHS Type of ?|

Why does `ARRAY['sku','vendor']` differ from `'["sku","vendor"]'::jsonb`? Which type is used with `?|`?

### Exercise 10. Array Order

Is `'["a","b"]'::jsonb @> '["b","a"]'::jsonb` true or false? What about `=`?

### Exercise 11. Array Duplicates

What does `'["a"]'::jsonb @> '["a","a"]'::jsonb` show about multiplicity?

### Exercise 12. Primitive in Array

Explain the results of `'[1,2,3]'::jsonb @> '2'::jsonb` and `'[1,2,3]'::jsonb ? '2'`.

### Exercise 13. Missing Key vs. JSON null

Write a query finding documents where `notes` is **JSON null**, distinct from `notes` being missing.

### Exercise 14. SQL NULL

Why does `NULL::jsonb = 'null'::jsonb` return SQL NULL instead of false?

### Exercise 15. IS DISTINCT FROM

Write an expression verifying that SQL NULL and JSON null are two distinct states.

### Exercise 16. Price Type

Write a query listing products whose `price` is a JSON string rather than a number.

### Exercise 17. Filtering Numeric Price

Write a query finding products with a JSON number `price` greater than 50, excluding the string `"20"`.

### Exercise 18. ORDER BY Price

Why can `ORDER BY doc->>'price'` produce the wrong order? Suggest a rewrite.

### Exercise 19. Object Equality

Explain why two objects with the same key/value pairs in different key order are still equal under `jsonb =`.

### Exercise 20. JSONPath Tags

Write a JSONPath `@?` query finding documents with tag `sale`.

### Exercise 21. JSONPath Array of Objects

Write a JSONPath query finding documents containing an `attributes.sizes` element with `units >= 5`.

### Exercise 22. JSONPath Predicate

Write an example using `@@` to check JSONB `price > 50` and note the data-type caveats.

### Exercise 23. GIN Opclasses

Identify which operator classes support `doc ? 'vendor'` and `doc @> '{"active":true}'`.

### Exercise 24. GIN Expression Index

Create a GIN index on `doc -> 'tags'` to support `(doc->'tags') ? 'sale'`.

### Exercise 25. B-tree Expression Index

Create a B-tree expression index to support exact lookup `doc->>'sku' = 'KB-01'`.

### Exercise 26. JSONB Equality Index

Which index type can support whole-document equality? Why is it not generally recommended on a column storing very large JSONB documents?

### Exercise 27. Partial Index

Create a partial index on `created_at` covering only documents that have key `vendor`.

### Exercise 28. EXPLAIN

Write an `EXPLAIN (ANALYZE, BUFFERS)` query for `vendor.country = VN` containment, and list the fields to inspect.

### Exercise 29. CHECK Type

Write CHECK constraints ensuring `doc` is a JSON object and has a `price` key of JSON number type.

### Exercise 30. Prepared Statement

Write a prepared statement accepting one `jsonb` parameter and finding documents containing that parameter.

### Exercise 31. Comparing <@

Write two ways to express "`{"a":1}` is contained within `{"a":1,"b":2}`".

### Exercise 32. Relational Columns

If an application constantly filters, sorts, and aggregates by `price` and needs an FK on `vendor_id`, would you keep everything in JSONB or extract typed columns? Explain.

## 42. Reference Solutions

### Exercise 1. @> and =

`@>` returns `true` because the left object contains `a=1`; `=` returns `false` because the left object also has key `b`.

### Exercise 2. Vendor Country

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb
ORDER BY product_id;
~~~

### Exercise 3. Vendor Exists

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'vendor';
~~~

### Exercise 4. Nested Key

`?` does not search across nesting levels automatically. Correct form:

~~~sql
SELECT product_id
FROM json_lab.products
WHERE (doc -> 'vendor') ? 'country';
~~~

### Exercise 5. Tag sale

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"tags":["sale"]}'::jsonb;

SELECT product_id
FROM json_lab.products
WHERE (doc -> 'tags') ? 'sale';
~~~

### Exercise 6–7. ANY/ALL

~~~sql
-- At least one tag:
WHERE (doc -> 'tags') ?| ARRAY['tech','office']

-- Both tags:
WHERE (doc -> 'tags') ?& ARRAY['tech','sale']
~~~

### Exercise 8–9. Key List

~~~sql
WHERE doc ?& ARRAY['sku','price','active']
~~~

`?|` / `?&` accept PostgreSQL `text[]`, not a JSONB array on the RHS.

### Exercise 10–11. Array Containment

`@>` with reordered arrays returns true, whereas equality returns false. Containment does not enforce duplicate multiplicity; `["a"] @> ["a","a"]` returns true.

### Exercise 12. Primitive and ?

`[1,2,3] @> 2` returns true for the JSON number; `[1,2,3] ? '2'` finds no JSON string element `"2"` and returns false.

### Exercise 13. Notes JSON null

~~~sql
SELECT product_id
FROM json_lab.products
WHERE doc ? 'notes'
  AND doc -> 'notes' = 'null'::jsonb;
~~~

Or using containment:

~~~sql
WHERE doc @> '{"notes":null}'::jsonb
~~~

### Exercise 14–15. SQL NULL

Normal comparisons with SQL NULL yield unknown. Distinguish them with:

~~~sql
SELECT
    NULL::jsonb IS DISTINCT FROM 'null'::jsonb;
~~~

Result is true.

### Exercise 16. Price Is a String

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'string';
~~~

In the lab, this returns `CB-08`.

### Exercise 17. Numeric Price

~~~sql
SELECT product_id, doc ->> 'sku' AS sku
FROM json_lab.products
WHERE jsonb_typeof(doc -> 'price') = 'number'
  AND doc -> 'price' > '50'::jsonb;
~~~

The type condition prevents `"20"` from participating in numeric comparison as a JSONB string.

### Exercise 18. ORDER BY Numeric

`doc->>'price'` is text, so it sorts lexicographically. Use `CASE` to cast only when `price` is a JSON number:

~~~sql
SELECT
    product_id,
    CASE
      WHEN jsonb_typeof(doc -> 'price') = 'number'
      THEN (doc ->> 'price')::numeric
    END AS numeric_price
FROM json_lab.products
ORDER BY numeric_price DESC NULLS LAST;
~~~

### Exercise 19. Object Equality

JSONB normalizes object key/value pairs, so key order in the input JSON text does not affect object equality.

### Exercise 20–21. JSONPath Existence

~~~sql
WHERE doc @? '$.tags[*] ? (@ == "sale")'
~~~

~~~sql
WHERE doc @? '$.attributes.sizes[*] ? (@.units >= 5)'
~~~

### Exercise 22. JSONPath Predicate

~~~sql
WHERE doc @@ '$.price > 50'
~~~

You must account for `price` potentially being a number, string, null, or missing, and verify semantics and plans. Do not assume numeric JSON strings are auto-cast.

### Exercise 23. GIN Opclasses

`jsonb_ops` supports `?` and `@>`; `jsonb_path_ops` supports `@>` but does not support `?`.

### Exercise 24. Expression GIN

~~~sql
CREATE INDEX idx_products_tags_answer
ON json_lab.products
USING gin ((doc -> 'tags'));
~~~

### Exercise 25. Expression B-tree

~~~sql
CREATE INDEX idx_products_sku_answer
ON json_lab.products ((doc ->> 'sku'));
~~~

### Exercise 26. Whole-Document Equality

A B-tree index can support `doc = value::jsonb`, but index keys are large, JSONB documents change frequently, and queries usually target specific fields. Do not default to building a whole-document B-tree.

### Exercise 27. Partial B-tree

~~~sql
CREATE INDEX idx_products_vendor_recent_answer
ON json_lab.products (created_at)
WHERE doc ? 'vendor';
~~~

### Exercise 28. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id
FROM json_lab.products
WHERE doc @> '{"vendor":{"country":"VN"}}'::jsonb;
~~~

Inspect the scan type, `Index Cond`/`Recheck Cond`/`Filter`, `actual rows`, `loops`, `Buffers`, and `Execution Time`.

### Exercise 29. CHECK JSON Structure

~~~sql
CREATE TABLE json_lab.checked_product_docs (
    id bigint PRIMARY KEY,
    doc jsonb NOT NULL,
    CHECK (jsonb_typeof(doc) = 'object'),
    CHECK (
      doc ? 'price'
      AND jsonb_typeof(doc -> 'price') = 'number'
    )
);
~~~

### Exercise 30. Prepared Statement

~~~sql
PREPARE product_contains(jsonb) AS
SELECT product_id
FROM json_lab.products
WHERE doc @> $1;

EXECUTE product_contains('{"active":true}'::jsonb);
~~~

### Exercise 31. Two Containment Directions

~~~sql
SELECT
    '{"a":1,"b":2}'::jsonb @> '{"a":1}'::jsonb,
    '{"a":1}'::jsonb <@ '{"a":1,"b":2}'::jsonb;
~~~

Both return true.

### Exercise 32. Extracting Typed Columns

If `price` is frequently filtered, sorted, or used in calculations, use a `numeric` column with appropriate CHECKs and precision. If `vendor_id` requires a foreign key, use a relational column with an FK. Keep flexible metadata that does not need a fixed schema in JSONB. This prevents heterogeneous comparisons and gives clear constraints, statistics, and indexes.

## 43. Quick Reference Table

| Question | Operator / Expression |
| --- | --- |
| Left JSONB contains right JSONB? | `left @> right` |
| Left JSONB is inside right JSONB? | `left <@ right` |
| Has top-level key `sku`? | `doc ? 'sku'` |
| Has at least one of two keys? | `doc ?| ARRAY['a','b']` |
| Has both keys? | `doc ?& ARRAY['a','b']` |
| Has tag `sale`? | `doc @> '{"tags":["sale"]}'::jsonb` |
| Has tag `sale` via child array? | `(doc->'tags') ? 'sale'` |
| `vendor.country = VN`? | `doc @> '{"vendor":{"country":"VN"}}'::jsonb` |
| `country` key inside `vendor`? | `(doc->'vendor') ? 'country'` |
| Has `notes` key regardless of value? | `doc ? 'notes'` |
| `notes` is JSON null? | `doc @> '{"notes":null}'::jsonb` |
| `notes` key is missing? | `NOT (doc ? 'notes')` |
| JSONB values equal? | `doc1 = doc2` |
| JSONB values not equal? | `doc1 <> doc2` |
| Null-safe SQL NULL comparison? | `IS [NOT] DISTINCT FROM` |
| JSON type of `price`? | `jsonb_typeof(doc->'price')` |
| Traverse array with JSONPath? | `doc @? '$.tags[*] ? (...)'` |
| Evaluate JSONPath predicate? | `doc @@ '$.price > 50'` |
| GIN supporting containment and key existence? | `USING gin (doc jsonb_ops)` |
| GIN focused on containment/path? | `USING gin (doc jsonb_path_ops)` |
| GIN on `tags` expression? | `USING gin ((doc->'tags'))` |
| Exact scalar `sku` lookup? | B-tree on `(doc->>'sku')` |
| Compare prices numerically? | Guarded cast or `numeric` column |
| Inspect index and plan? | `EXPLAIN (ANALYZE, BUFFERS)` |

## 44. Checklist Before Using JSONB Queries in Applications

1. **Are you asking for containment, key existence, or equality?** Did you choose the operator with the right semantics?
2. **At what level is the key?** Is `?` applied to the exact object or array you mean to check?
3. **Is the path in the RHS of `@>` complete?** Did you accidentally place a nested field at the top level?
4. **Does the array require order or element multiplicity?** `@>` does not replace equality or multiplicity checks.
5. **Do all literals have the right JSON type?** Number `20` differs from string `"20"`; `true` differs from `"true"`.
6. **Can keys be missing?** Do you need to distinguish missing, JSON null, and SQL NULL?
7. **Is schema validation present?** `?&` only checks key existence, not valid types or values.
8. **Are you converting text to numbers for `ORDER BY`?** Use casting rules/checks or a `numeric` column.
9. **Does the query use `@>`, `?`, `?|`, `?&`, `@?`, `@@`, or `=`/`<`/`>`?** Does the chosen opclass support that operator?
10. **Does GIN on `doc` match the query expression?** Or do you need GIN on `doc->'tags'`?
11. **Are you using `jsonb_path_ops` while needing `?`?** If so, switch the index choice.
12. **Does JSONPath extract GIN search keys effectively?** Did you check `EXPLAIN`?
13. **Are there redundant or unused indexes?** Have write impact, WAL, and storage been evaluated?
14. **Is Seq Scan reasonable because the table is small?** Do not force indexes just for plan aesthetics.
15. **Did you test on a representative data distribution?** Rare keys, common keys, nested arrays, varying JSON sizes.
16. **Is the query parameterized?** Never concatenate user input directly into SQL.
17. **Are strong FKs, constraints, or aggregations needed on a field?** Should it be extracted to a relational column?
18. **Are nulls and types tested in the application?** Especially when parsing JSON from multiple producers.
19. **Did you inspect `Index Cond`, `Filter`, `Recheck Cond`, and `Buffers`?** Don't look solely at `Execution Time`.
20. **Did optimization preserve meaning?** Verify identical semantics before and after rewriting.

## 45. Summary

JSONB operators in PostgreSQL are powerful, but they only work well when you know **the exact question you are asking**:

- **`@>` and `<@`** test **structural** containment. An object may contain extra keys beyond those requested; array containment ignores order and does not count duplicates as a multiset, whereas array equality still checks order and element count.
- **`?`, `?|`, `?&`** test the existence of object keys or array string elements **at the current level**, corresponding to one, any, or all keys in the list. They do not automatically recurse into nested objects.
- **`=`, `<>`, and ordering operators** compare JSONB values according to PostgreSQL semantics. JSONB numbers differ from JSONB strings; SQL NULL differs from JSON null; JSONB B-tree ordering is not business ordering for prices or product names.
- **`@?` and `@@`** extend querying with JSONPath, especially when filtering inside nested arrays and objects, though not every path has an efficient index strategy.

For optimization, GIN **`jsonb_ops`** supports containment, key existence, and certain JSONPath patterns; **`jsonb_path_ops`** focuses on containment/path matching, can be smaller, but does not support `?`, `?|`, or `?&`. B-tree and expression indexes serve equality, scalar comparisons, and `ORDER BY` when needed.

Start every query by asking **"Do I need key existence, structural containment, or whole-document equality?"** Then verify the path, JSON types, and null semantics, write the accurate predicate, and finally check index usage with `EXPLAIN (ANALYZE, BUFFERS)` on representative data. This avoids both **wrong results** and **optimizing the wrong operator**.
