# Choosing Relational Tables, jsonb, or a Hybrid Model

An e-commerce platform sells phones, shoes, and books. Every product has a SKU, selling price, status, and owning unit. However, phones have RAM capacity and screen type; shoes have size and material; books have ISBN, author, and page count. Should you create hundreds of nullable columns in one table, create a separate table for each type, or put all the information into a single `jsonb` column?

In another system, each order needs to store the shipping address **at the time of purchase**, which must not automatically change when the customer updates their profile. An integration system receives webhooks whose structure changes across API versions. Meanwhile, an accounting workflow must guarantee totals, foreign keys, and transaction ID uniqueness. These three scenarios have **different data requirements**, so there is no single "always use relational" or "always use JSON" answer for all of them.

PostgreSQL allows combining the properties of a relational database with the **`jsonb`** data type — JSON parsed into a binary representation that can be queried and indexed. A good choice depends not only on whether the schema is flexible, but also on **data invariants, access patterns, concurrent updates, growth, indexability, history, and operational cost**.

In this lesson, we will:

1. Determine when to choose **relational tables/columns**, **`jsonb`**, or a **hybrid model**.
2. Distinguish between `json`, `jsonb`, SQL arrays, child tables, and many-to-many junction tables.
3. Design a **multi-tenant product catalog** using all three approaches and state their trade-offs.
4. Use `->`, `->>`, `#>`, `#>>`, `?`, `@>`, JSONPath, and `jsonb_set`.
5. Examine `NULL` types, missing JSON keys, validation, and the limitations of `CHECK`.
6. Create **B-tree expression/generated column** indexes, **GIN `jsonb_ops`/`jsonb_path_ops`** indexes, and partial indexes.
7. Query JSON arrays and compare them with SQL arrays and junction tables.
8. Handle concurrent updates, payload structure evolution, snapshots, and history.
9. Analyze `TOAST`, MVCC/WAL, statistics, the query planner, migrations, and JDBC/Spring.
10. Complete a PostgreSQL lab and modeling exercises based on business requirements.

> **Environment:** Examples target modern PostgreSQL. Some syntax such as JSONPath requires PostgreSQL 12+, while generated columns and planner/index capabilities vary by version. Run the table creation, update, and migration statements in a practice database. The goal is to choose the right structure and understand the consequences, not to assume JSONB is always faster or slower than relational modeling across all workloads.

## 1. What Problems Do Relational Models and jsonb Solve?

**The relational model** stores data in tables with explicitly typed columns. PostgreSQL can directly enforce:

- `PRIMARY KEY` and `UNIQUE`.
- `NOT NULL` and `CHECK`.
- `FOREIGN KEY` constraints across tables.
- Transaction rules, isolation, and locking.
- B-tree, GiST, GIN, and other indexes on columns or expressions.
- Planner statistics on columns and configured column combinations.

**`jsonb`** stores JSON values in a PostgreSQL column:

```json
{
  "color": "black",
  "screen_inches": 6.7,
  "connectivity": ["wifi", "5g"],
  "warranty": {
    "months": 24,
    "provider": "manufacturer"
  }
}
```

JSON values can be **object**, **array**, **string**, **number**, **boolean**, or **JSON null**. PostgreSQL provides operators and functions to read, filter, and modify that structure.

**The hybrid model** keeps structured data and strong constraints in relational columns while using one or more `jsonb` columns for variable attributes or snapshots:

```text
products
├── product_id           BIGINT PRIMARY KEY
├── tenant_id            BIGINT NOT NULL
├── sku                  TEXT NOT NULL
├── name                 TEXT NOT NULL
├── current_price        NUMERIC NOT NULL
├── status               TEXT NOT NULL
├── category_id          BIGINT (FOREIGN KEY)
└── attributes           JSONB NOT NULL
    ├── color
    ├── size
    └── category-specific keys
```

Do not pick a data type first and then try to force every business rule into it. Identify **the rules that must be guaranteed** first.

## 2. Three Choices, Not Three Opposing Camps

| Criterion | Relational | `jsonb` as Primary Data | Hybrid |
|---|---|---|---|
| Stable structure shared across all rows | Very well suited | Usable, but easy to lose control | Put in standard columns |
| Custom/frequently changing attributes | Requires many schema migrations or child tables | Flexible | Often the best fit |
| Strong PK/FK/UNIQUE/NOT NULL | Directly supported | Requires extra design/workarounds | Applied to core columns |
| Multi-entity JOIN queries | Natural | Nested queries are harder | Relational for identities/relations |
| Document read/written as a whole | May require splitting across tables | Convenient | JSON snapshot/metadata |
| Frequent updates to a small field | Natural per column | Can create a new version of the entire JSON value | Extract hot fields to columns |
| Statistics/filtering/ranges/sorting | Easy to optimize per column | Requires suitable expressions/generated columns/indexes | Proactively choose what to optimize |
| Schema evolution | Controlled migrations | Flexible, but prone to schema drift | Separate stable and volatile changes |
| Reporting, BI, analytics | Convenient | Requires extraction/casting/normalization | Promote key dimensions to columns |

### Pragmatic Rule

If an attribute is an **identifier**, a **referencing key**, the **subject of a strong constraint**, or **very frequently filtered/sorted/joined**, start with an **explicitly typed relational column**.

If an attribute is an **unpredictable payload**, **optional metadata**, a **structure inherited from an external API**, or a **snapshot that preserves context**, `jsonb` can be a reasonable choice.

If an entity contains **both kinds**, a hybrid model is usually better than forcing all data onto one side.

## 3. Questions to Answer Before Designing

1. **What data appears on every record?** For example, SKU, status, tenant.
2. **What data is mandatory?** Are `NOT NULL`/`CHECK` or numeric constraints required?
3. **What data acts as a referencing key?** Are there FKs to customer, product, or warehouse?
4. **How high is the variability?** 5 stable product types or 500 types with open-ended attributes?
5. **What queries are common?** Lookup by SKU, filter by RAM, sort by price, search inside tag arrays, full-text?
6. **What is the update frequency?** Price and stock change every minute, while technical descriptions change monthly?
7. **Is historical querying required?** Do you need a snapshot at order time or only the current state?
8. **Will the data be analyzed by SQL/BI?** Will there be GROUP BY, SUM, or JOINs on attributes?
9. **Who controls the schema?** The backend team, external integrators, or individual tenants?
10. **What is the cost of bad data?** An invalid price or non-existent `customer_id` is different from a missing UI preference.
11. **What are the size and growth characteristics?** Documents of a few KB or multi-MB payloads?
12. **How long is backward compatibility needed?** Which JSON versions do older clients still send?

A good decision can usually be explained **directly from these questions**, rather than from a slogan like "NoSQL is more flexible."

## 4. How Does PostgreSQL json Differ from jsonb?

PostgreSQL has two types: `json` and `jsonb`.

| Property | `json` | `jsonb` |
|---|---|---|
| Storage format | Valid JSON input text | Parsed binary representation |
| Preserves input whitespace/formatting | Yes, stores original text | No |
| Object key ordering | Preserves input representation | Not guaranteed |
| Duplicate object keys | Original text may retain duplicates | Duplicate keys are merged; the last value wins |
| Structural querying/processing | Certain functions/operators available | More specialized operators/indexing |
| GIN indexing of documents | Not equivalent to `jsonb` | Supported |
| Documents with queries/updates | Usually less convenient | Usually the primary choice |

Example:

```sql
SELECT
    '{"b":2, "a":1, "a":3}'::json  AS original_json,
    '{"b":2, "a":1, "a":3}'::jsonb AS parsed_jsonb;
```

With `jsonb`, objects no longer preserve the exact original formatting and duplicate keys. If the system must preserve the **verbatim payload**, byte-string signature, whitespace, or key ordering for auditing or signature verification, you may need to store **raw text/bytes** separately.

### Do Not Equate JSONB with "Schema-Free"

`jsonb` only allows storing flexible structures. The application still has a **de facto schema**: it expects keys, data types, versions, required rules, and compatibility. Failing to declare them explicitly can turn the schema into hidden assumptions scattered throughout the code.

## 5. Value Types Inside jsonb

```sql
SELECT
    jsonb_typeof('{}'::jsonb) AS object_type,
    jsonb_typeof('[]'::jsonb) AS array_type,
    jsonb_typeof('"hello"'::jsonb) AS string_type,
    jsonb_typeof('10'::jsonb) AS number_type,
    jsonb_typeof('true'::jsonb) AS bool_type,
    jsonb_typeof('null'::jsonb) AS json_null_type;
```

The results are `object`, `array`, `string`, `number`, `boolean`, and `null` respectively (the type names are returned as text).

Common points of confusion:

- **SQL `NULL`** represents the absence of a value in a SQL cell.
- **JSON `null`** is a JSON value **inside the document**.
- **Missing key** is the state where an object does not contain that key.

These three states can carry different business meanings.

## 6. Distinguishing SQL NULL, JSON null, and a Missing Key

```sql
SELECT
    jsonb_typeof('null'::jsonb) AS json_null_kind,
    jsonb_typeof(NULL::jsonb)   AS sql_null_kind,
    ('{"color":null}'::jsonb ? 'color') AS has_color_key,
    ('{}'::jsonb ? 'color') AS missing_color_key,
    '{"color":null}'::jsonb -> 'color' AS color_json,
    '{"color":null}'::jsonb ->> 'color' AS color_text;
```

Explanation:

- `jsonb_typeof('null'::jsonb)` returns the text string `'null'`.
- `jsonb_typeof(NULL::jsonb)` returns SQL NULL.
- `? 'color'` is true if the key exists, **even when the value is JSON null**.
- `->` keeps the result as JSON/JSONB; a missing key returns SQL NULL.
- `->>` converts to text; both JSON null and a missing key produce SQL NULL when extracting text.

### Design Consequence

If business logic needs to distinguish:

1. "The client did not send the `color` field."
2. "The client **intentionally cleared** `color` using JSON null."

then `attributes->>'color' IS NULL` alone cannot tell them apart. You need to inspect `attributes ? 'color'` or use a PATCH protocol with clear semantics.

## 7. Sample Problem: Multi-Tenant Product Catalog

A system has:

- **Core data:** `product_id`, `tenant_id`, SKU, name, category, status, price.
- **Variable attributes:** color, RAM, size, material, battery specs, page count.
- **Relationships:** a product belongs to a category; a product has many tags; inventory is tracked per warehouse.
- **Snapshots:** name/price/tax/address data captured at order placement time.

Design diagram:

```text
tenants ──┐
          │
categories ├── products
           │    ├── typed columns: sku, price, status, ...
           │    └── attributes JSONB: color, ram, ...
           │
           ├── product_tags ── tags
           │
           └── inventory (product_id, warehouse_id, quantity)

orders ── order_items
             ├── product_id (FK to product)
             ├── unit_price NUMERIC
             └── product_snapshot JSONB
```

This is a **hybrid** model: it does not use one giant JSON document to replace every entity and relationship.

## 8. Preparing the Lab Schema

```sql
CREATE SCHEMA IF NOT EXISTS lesson_model_choice;

CREATE TABLE lesson_model_choice.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.categories (
    category_id BIGINT PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);

INSERT INTO lesson_model_choice.tenants (
    tenant_id, tenant_name
)
VALUES
    (1, 'Tenant One'),
    (2, 'Tenant Two');

INSERT INTO lesson_model_choice.categories (
    category_id, category_name
)
VALUES
    (10, 'Phone'),
    (20, 'Shoes'),
    (30, 'Books');
```

The sample data uses synthetic IDs and names and does not represent real customer data.

## 9. Option A — Pure Relational Table

One approach is to declare common columns across all product types:

```sql
CREATE TABLE lesson_model_choice.products_wide (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    phone_ram_gb INTEGER,
    shoe_size_eu NUMERIC(4,1),
    book_isbn TEXT,
    book_pages INTEGER,
    color TEXT,
    material TEXT,
    CONSTRAINT uq_products_wide_tenant_sku
        UNIQUE (tenant_id, sku)
);
```

### Advantages

- Columns are strongly typed; `price` is numeric, `phone_ram_gb` is integer.
- Easy to define `CHECK` constraints and direct indexes.
- BI/reporting queries are typically straightforward.
- PostgreSQL collects statistics on regular columns.

### Disadvantages

- Most rows have many inapplicable columns set to `NULL`.
- Each new product type with new attributes can require DDL changes.
- Rules like "this column applies only to category X" require complex constraints.
- The table schema can bloat and become harder to govern.

**Do not assume a wide table is always wrong.** If there are only a few stable attributes, several nullable columns can still be simpler and more efficient than complex JSONB.

## 10. Option A2 — Separate Child Tables per Type

You can keep a shared core table and create child tables:

```sql
CREATE TABLE lesson_model_choice.products_base (
    product_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0),
    UNIQUE (tenant_id, sku)
);

CREATE TABLE lesson_model_choice.phone_details (
    product_id BIGINT PRIMARY KEY
        REFERENCES lesson_model_choice.products_base(product_id)
        ON DELETE CASCADE,
    ram_gb INTEGER NOT NULL CHECK (ram_gb > 0),
    screen_inches NUMERIC(4,1) NOT NULL
        CHECK (screen_inches > 0)
);

CREATE TABLE lesson_model_choice.book_details (
    product_id BIGINT PRIMARY KEY
        REFERENCES lesson_model_choice.products_base(product_id)
        ON DELETE CASCADE,
    isbn TEXT NOT NULL,
    page_count INTEGER NOT NULL CHECK (page_count > 0)
);
```

### When Is This Good?

- There is a small number of product types with fairly stable structures.
- Each type has its own data invariants and is queried frequently.
- FK/UNIQUE constraints are needed on specialized attributes.
- Strong type enforcement at the database level is desired.

### Be Careful

A foreign key on `phone_details.product_id` guarantees that the parent row exists, but **does not automatically prove `parent.category_id = 10`**. If you need strict cross-table "matching type" enforcement, you must design an additional mechanism (composite keys, controlled constraints/triggers, or another structure).

Do not use table inheritance as a shortcut that automatically replaces all classification constraints.

## 11. Option B — Whole Document in jsonb

```sql
CREATE TABLE lesson_model_choice.products_document (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

Example document:

```sql
INSERT INTO lesson_model_choice.products_document(payload)
VALUES (
    '{
      "tenant_id": 1,
      "sku": "PHONE-A",
      "name": "Phone A",
      "category": "phone",
      "price": 12990000,
      "attributes": {
        "ram_gb": 8,
        "screen_inches": 6.5
      }
    }'::jsonb
);
```

### Advantages

- Easy to accept and store documents from external APIs.
- Each document can have a different structure.
- New keys can be added without `ALTER TABLE`.
- Convenient to return the JSON payload back to clients.

### Risks

- `tenant_id`, `sku`, and `price` live inside JSON, so they do not automatically get FK/UNIQUE/NOT NULL enforcement with the intended semantics.
- The same key might be a number in one row and a string in another.
- Querying and indexing nested keys require extra design.
- Small updates can rewrite the entire JSONB value/tuple version.
- BI queries, joins, and casts grow increasingly complex.
- The effective schema can drift across different producers.

**The document model is a deliberate choice**, appropriate when the document is the primary unit and few cross-document invariants are needed; it is not a free way to avoid schema design.

## 12. Option C — The Hybrid Model

Create a products table with core typed columns and `attributes`:

```sql
CREATE TABLE lesson_model_choice.products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    category_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.categories(category_id),
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'INACTIVE')),
    price NUMERIC(12,2) NOT NULL
        CHECK (price >= 0),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_products_tenant_sku
        UNIQUE (tenant_id, sku)
);
```

### Why Were These Columns Chosen?

- `product_id`: stable technical identifier, PK.
- `tenant_id`: ownership scope and FK.
- `category_id`: classification relationship to the category table.
- `sku`: business key unique **within a tenant**.
- `product_name`: core data frequently displayed.
- `status`: lifecycle with a controlled set of values.
- `price`: numeric used for arithmetic/range/sorting, requiring a CHECK constraint.
- `attributes`: technical attributes that vary by category.

Do not let critical financial fields "sink" into JSON merely because they can be represented as JSON numbers.

## 13. Sample Data for the Hybrid Model

```sql
INSERT INTO lesson_model_choice.products (
    tenant_id, category_id, sku,
    product_name, price, attributes
)
VALUES
    (
      1, 10, 'PHONE-A', 'Phone A', 12990000,
      '{
        "brand":"Acme",
        "color":"black",
        "ram_gb":8,
        "screen_inches":6.5,
        "connectivity":["wifi","5g"],
        "warranty":{"months":24,"provider":"manufacturer"}
      }'::jsonb
    ),
    (
      1, 10, 'PHONE-B', 'Phone B', 18990000,
      '{
        "brand":"Acme",
        "color":"silver",
        "ram_gb":16,
        "screen_inches":6.7,
        "connectivity":["wifi","bluetooth","5g"],
        "warranty":{"months":36}
      }'::jsonb
    ),
    (
      1, 20, 'SHOE-A', 'Shoe A', 1250000,
      '{
        "brand":"FootCo",
        "color":"black",
        "sizes_eu":[39,40,41,42],
        "material":"leather"
      }'::jsonb
    ),
    (
      1, 30, 'BOOK-A', 'Book A', 185000,
      '{
        "isbn":"9780000000001",
        "author":"Author A",
        "pages":320,
        "language":"en"
      }'::jsonb
    ),
    (
      2, 10, 'PHONE-A', 'Tenant 2 Phone', 15990000,
      '{
        "brand":"OtherBrand",
        "color":"blue",
        "ram_gb":12
      }'::jsonb
    );
```

Two tenants are allowed to use the same SKU because the unique key is `(tenant_id, sku)`, not `sku` alone.

## 14. Querying Core Columns Like a Standard Relational Table

```sql
SELECT
    product_id,
    tenant_id,
    sku,
    product_name,
    price,
    status
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND status = 'ACTIVE'
  AND price BETWEEN 1000000 AND 15000000
ORDER BY price, product_id;
```

Because `price` is `NUMERIC`, PostgreSQL compares numerically; there is no need to extract text from JSON and cast it inside every predicate.

### Suitable B-tree Index

```sql
CREATE INDEX ix_products_tenant_status_price
ON lesson_model_choice.products (
    tenant_id,
    status,
    price
);
```

This index can support filtering on tenant/status and price range/sorting when the planner deems it appropriate.

Do not assume that having an index means a query will always use it. On a very small table, a Seq Scan can be cheaper.

## 15. Reading JSON Keys with -> and ->>

`->` extracts an element as JSONB, whereas `->>` extracts it as SQL text.

```sql
SELECT
    sku,
    attributes -> 'brand' AS brand_json,
    attributes ->> 'brand' AS brand_text,
    attributes -> 'ram_gb' AS ram_json,
    attributes ->> 'ram_gb' AS ram_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

If `attributes` contains:

```json
{"brand":"Acme","ram_gb":16}
```

then:

- `attributes->'brand'` is the JSON string `"Acme"`.
- `attributes->>'brand'` is the SQL text `Acme`.
- `attributes->'ram_gb'` is the JSON number `16`.
- `attributes->>'ram_gb'` is the SQL text `16`.

### Why Does the Difference Matter?

```sql
WHERE attributes ->> 'ram_gb' = '16'
```

performs a **text** comparison, not a numeric one. If you want numeric comparisons, you need an appropriate type or cast and must ensure the data is valid.

## 16. Querying Nested JSON with #> and #>>

`#>` / `#>>` accept a path as a text array:

```sql
SELECT
    sku,
    attributes #> '{warranty,months}'
        AS months_json,
    attributes #>> '{warranty,provider}'
        AS provider_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

This is equivalent to stepping down level by level:

```sql
SELECT
    sku,
    attributes -> 'warranty' ->> 'months'
        AS warranty_months_text
FROM lesson_model_choice.products
WHERE category_id = 10;
```

### Non-Existent Keys

If `warranty.provider` does not exist, extraction normally returns SQL NULL instead of throwing a missing-key error. This is convenient for optional data, but it can **mask data quality issues** when business logic considers that field mandatory.

### Do Not Blindly Cast Nested Values

`(attributes #>> '{warranty,months}')::int` can fail if a producer sends `"unknown"` or an object instead of a number or numeric string. If that field becomes important, enforce the schema and create an appropriate typed or generated column.

## 17. jsonb_typeof and Lightweight Validation

Suppose phones require `ram_gb` to be a number; you can check:

```sql
SELECT
    sku,
    jsonb_typeof(attributes -> 'ram_gb') AS ram_type,
    attributes -> 'ram_gb' AS ram_value
FROM lesson_model_choice.products
WHERE category_id = 10;
```

If the key is missing, `jsonb_typeof(attributes -> 'ram_gb')` is SQL NULL.

### Basic CHECK for a JSON Object

In the hybrid table we already have:

```sql
attributes JSONB NOT NULL
CHECK (jsonb_typeof(attributes) = 'object')
```

This blocks a top-level array/string/number payload, but **does not block** an object document that is missing required business keys.

### Watch SQL CHECK Semantics

A `CHECK` constraint only rejects a row when the expression evaluates to **FALSE**. If the expression evaluates to **SQL NULL/UNKNOWN**, the constraint is treated as not violated. For example:

```sql
CHECK (jsonb_typeof(attributes -> 'ram_gb') = 'number')
```

is not strong enough on its own to require the `ram_gb` key to exist, because a missing key causes the expression to return NULL. To require it:

```sql
CHECK (
    attributes ? 'ram_gb'
    AND jsonb_typeof(attributes -> 'ram_gb') = 'number'
)
```

When an attribute applies only to phones, you need to add a condition on category, while also considering what happens if the category changes.

## 18. Per-Category Validation: What Are the Limits?

A desired rule:

```text
If category=PHONE:
  ram_gb must be a JSON number > 0
  screen_inches must be a JSON number > 0

If category=BOOK:
  isbn must have a valid format
  pages must be an integer > 0
```

With a small, fixed set of three product types, constraints in dedicated tables like `phone_details` can be much clearer.

With hundreds of evolving types, you can use:

- Versioned application-side schema validation.
- PostgreSQL constraints for simple core invariants.
- Triggers or extensions that validate JSON Schema where the environment permits.
- Category attribute definition tables combined with validation logic.
- Ingestion validation pipelines and contract tests.

**PostgreSQL does not automatically guarantee that every document in a `jsonb` column conforms to a full JSON Schema just because the column type is `jsonb`.** JSONB guarantees valid JSON syntax and values, not your business rules.

## 19. Checking Key Existence with ? and Values with @>

`?` checks for a key **at the top level** of an object or as a matching string element of an array; it does not automatically search keys at arbitrary nesting depths.

```sql
SELECT
    sku,
    attributes ? 'brand' AS has_brand,
    attributes ? 'warranty' AS has_warranty,
    attributes ? 'months' AS has_top_level_months
FROM lesson_model_choice.products;
```

In a document containing `{"warranty":{"months":24}}`, `attributes ? 'months'` evaluates to FALSE because `months` is **inside `warranty`**, not at the top level.

### JSONB Containment

```sql
SELECT sku, product_name
FROM lesson_model_choice.products
WHERE attributes @> '{"brand":"Acme"}'::jsonb;
```

`@>` checks whether the left-hand document **contains the JSON structure/value** on the right according to `jsonb` containment rules.

For a nested object:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes @> '{"warranty":{"months":24}}'::jsonb;
```

### Matching JSON Types

`{"ram_gb":16}` differs from `{"ram_gb":"16"}` in type (number vs. string). Do not rely on containment queries with numbers to find data that a producer accidentally wrote as strings and assume both are equivalent.

## 20. Querying JSON Arrays

Document:

```json
{
  "connectivity": ["wifi", "bluetooth", "5g"]
}
```

Filter products that have `wifi`:

```sql
SELECT sku, product_name
FROM lesson_model_choice.products
WHERE attributes @> '{"connectivity":["wifi"]}'::jsonb;
```

With containment, array element order is not required to match positionally as in an exact array equality comparison. It fits the intent "contains element" rather than "is this exact ordered list."

### Checking Elements in a Nested Array

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes -> 'connectivity' ? '5g';
```

Here `?` applies to the **extracted array**, not the top-level object.

If `connectivity` is missing or not an array as expected, address data quality directly; do not treat an empty query result as proof that payloads conform to the schema.

## 21. Expanding Arrays into Rows with jsonb_array_elements

```sql
SELECT
    p.sku,
    entry.value AS connectivity_value
FROM lesson_model_choice.products AS p
CROSS JOIN LATERAL jsonb_array_elements(
    p.attributes -> 'connectivity'
) AS entry(value)
WHERE p.category_id = 10
  AND jsonb_typeof(
      p.attributes -> 'connectivity'
  ) = 'array'
ORDER BY p.sku, entry.value;
```

`LATERAL` allows the right-hand function to reference `p.attributes`. Each JSON array element becomes one row.

### Caution with Dirty Data

`jsonb_array_elements` requires its input to be a JSON array; if it encounters a JSON scalar or object, it raises an error. A SQL `WHERE` filter should not be assumed to guarantee evaluation order that keeps every expression safe in every plan. For untrusted data, normalize the input to an array using `CASE`:

```sql
SELECT
    p.sku,
    x.value
FROM lesson_model_choice.products AS p
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
      WHEN jsonb_typeof(
          p.attributes -> 'connectivity'
      ) = 'array'
      THEN p.attributes -> 'connectivity'
      ELSE '[]'::jsonb
    END
) AS x(value);
```

This query yields an empty result for keys that are not arrays, but **does not replace validation**: malformed data should be recorded and fixed at ingestion.

## 22. JSON Values Do Not Always Belong in Separate Tables

If a document has:

```json
{
  "resolution": {"width": 2560, "height": 1440},
  "certifications": ["A", "B"],
  "ui_hints": {"badge": "new"}
}
```

and the application only displays the full metadata on a detail screen without **filtering, joining, or aggregating** on those attributes, `jsonb` can be a great fit.

Splitting every key into a separate table causes:

- Many JOINs just to render one document.
- DDL changes for attributes that evolve constantly.
- Unnecessary association rows and indexes.
- Added code/ORM complexity.

**Normalization is a tool for managing invariants and relationships, not a mandate to split every JSON object into tables even when there is no benefit.**

## 23. Values Used for JOINs Need Careful Consideration

If JSON contains:

```json
{"supplier_id": 1001}
```

and `supplier_id` must reference the `suppliers` table, keeping it only inside JSON will not automatically give you a standard **FOREIGN KEY** on the nested field.

A manageable design:

```sql
CREATE TABLE lesson_model_choice.suppliers (
    supplier_id BIGINT PRIMARY KEY,
    supplier_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.product_suppliers (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    supplier_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.suppliers(supplier_id),
    PRIMARY KEY (product_id, supplier_id)
);
```

### Benefits

- Referential integrity.
- One product can have multiple suppliers.
- Querying all products for a supplier is straightforward.
- Indexes and query plans work on relational keys.
- Prevents `supplier_id` from pointing to a non-existent entity.

If supplier is merely a **raw display name from an external payload** rather than a local entity with a FK, storing it in JSON may still be reasonable.

## 24. Many-to-Many Relationships: Junction Table or JSON Array?

Suppose products have tags used by filters, administration, and analytics.

**JSON array option:**

```json
{"tags": ["new", "featured", "seasonal"]}
```

**Relational option:**

```sql
CREATE TABLE lesson_model_choice.tags (
    tag_id BIGINT PRIMARY KEY,
    tag_code TEXT NOT NULL UNIQUE
);

CREATE TABLE lesson_model_choice.product_tags (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id)
        ON DELETE CASCADE,
    tag_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tags(tag_id),
    PRIMARY KEY (product_id, tag_id)
);
```

### When to Use a Junction Table?

- A tag is an entity with its own metadata, permissions, or status.
- Tags need to be renamed without updating every document.
- FK, uniqueness, and product-count-per-tag reports are required.
- There is a true many-to-many relationship.
- The tag list grows and changes continuously.

### When Is a JSON Array Still Suitable?

- Tags are purely display/custom metadata.
- There is no central tag dictionary.
- No FK or separate governance is needed.
- You primarily read the whole document and occasionally filter with containment.

There is no single answer; the decision depends on **the role of the elements in the array**.

## 25. SQL Arrays and JSON Arrays Are Different

PostgreSQL also has SQL arrays, such as `TEXT[]`:

```sql
CREATE TABLE lesson_model_choice.article_labels (
    article_id BIGINT PRIMARY KEY,
    labels TEXT[] NOT NULL DEFAULT ARRAY[]::text[]
);

INSERT INTO lesson_model_choice.article_labels (
    article_id, labels
)
VALUES
    (1, ARRAY['postgresql','database']),
    (2, ARRAY['json','postgresql']);
```

Query:

```sql
SELECT *
FROM lesson_model_choice.article_labels
WHERE labels @> ARRAY['postgresql']::text[];
```

With SQL arrays:

- Uniform element type (`TEXT[]`).
- Supports array operators and GIN indexes when needed.
- Does not automatically enforce FKs on individual array elements.
- Does not automatically guarantee each element appears only once.
- Not suitable for replacing every relationship that has its own attributes.

With JSON arrays:

- Can contain nested objects and mixed JSON types within a document.
- Suitable for document payloads.
- Requires validation to avoid unexpected mixed element types.
- Querying, extraction, and casting differ from SQL arrays.

**If elements have foreign keys, status, business ordering, permissions, or their own lifecycle, consider a child table or junction table** rather than either a SQL array or a JSON array.

## 26. Ordered Arrays vs. Set-Like Arrays

A list:

```json
["first","second","third"]
```

can carry **ordering** semantics (workflow steps).

Whereas a list:

```json
["wifi","5g","bluetooth"]
```

may simply be a **set of features** where order does not matter.

If order is a critical invariant and each element has attributes, a table:

```sql
CREATE TABLE lesson_model_choice.workflow_steps (
    workflow_id BIGINT NOT NULL,
    step_no INTEGER NOT NULL CHECK (step_no > 0),
    step_code TEXT NOT NULL,
    PRIMARY KEY (workflow_id, step_no)
);
```

may be more suitable for enforcing step numbers and querying individual steps.

### JSONB Containment Pitfall

`@>` on JSONB arrays checks containment; it does not guarantee that the array has the exact **order** shown on the right-hand side. If a workflow requires order, containment is not an equivalence check for the entire step sequence.

## 27. JSONB Indexing: Start from Actual Queries

Do not create a GIN index on `attributes` merely because "we are using JSONB."

First categorize your queries:

1. `WHERE tenant_id = ? AND sku = ?` -> Unique B-tree on relational columns.
2. `WHERE price BETWEEN ? AND ?` -> B-tree on typed columns.
3. `WHERE attributes @> '{"brand":"Acme"}'` -> GIN can support containment.
4. `WHERE attributes ? 'color'` -> GIN with an operator class supporting key existence.
5. `WHERE attributes->>'brand' = 'Acme'` -> Expression B-tree may fit.
6. `ORDER BY (attributes->>'ram_gb')::integer` -> Expression/generated typed column and suitable index.

An index matches **the query's operators and expressions**. A GIN index does not automatically make every nested JSON range comparison or sort efficient.

## 28. GIN Index on jsonb

```sql
CREATE INDEX ix_products_attributes_gin
ON lesson_model_choice.products
USING GIN (attributes);
```

The default operator class for `jsonb` is **`jsonb_ops`**. It supports multiple operators, including containment and key existence within the scope of that operator class.

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, sku
FROM lesson_model_choice.products
WHERE attributes @> '{"brand":"Acme"}'::jsonb;
```

When data volume is large enough and the predicate is selective enough, the planner may consider the GIN index. With 5 lab products, a Seq Scan is usually still optimal.

### GIN Does Not Turn JSONB into an "Implicitly Columnar Table"

GIN creates index entries to serve matching search operators, but it:

- Does not enforce key types or schema.
- Does not provide FKs or UNIQUE constraints on nested values.
- Does not help every numeric range `ORDER BY`.
- Has memory, disk, WAL, and insert/update maintenance costs.

## 29. jsonb_ops and jsonb_path_ops

PostgreSQL provides two primary GIN operator classes:

| Property | `jsonb_ops` | `jsonb_path_ops` |
|---|---|---|
| Default for `jsonb` GIN | Yes | No |
| `@>` containment | Supported | Supported |
| `?`, `?|`, `?&` key existence | Supported | Does not support these operators |
| JSONPath `@?`, `@@` in supported versions | Supported | Supported per index rules |
| Size and specificity | Can be larger due to more entries | Often smaller/more selective for containment |
| Searching empty structures | Different behavior | Notable limitations with structures containing no values |

Index with `jsonb_path_ops`:

```sql
CREATE INDEX ix_products_attrs_path
ON lesson_model_choice.products
USING GIN (attributes jsonb_path_ops);
```

**In the lab, you do not necessarily need to keep both GIN indexes simultaneously** if they serve overlapping workloads. The choice should be based on actual operators used, index size, and read/write performance.

### Selection Rule

If the application relies directly on `attributes ? 'key'`, `jsonb_path_ops` cannot completely replace `jsonb_ops`.

If the workload is primarily `@>` containment and needs a more compact/selective index, `jsonb_path_ops` may be worth testing. However, it has limitations when matching empty structures and requires verifying specific conditions.

## 30. Full-Document GIN or an Expression Index for One Key?

Suppose this query runs very frequently:

```sql
SELECT product_id, sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND attributes->>'brand' = 'Acme';
```

An expression B-tree index:

```sql
CREATE INDEX ix_products_tenant_brand
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'brand')
);
```

This matches equality predicates on the expression `attributes->>'brand'` scoped by tenant.

### Comparison

**Full-document GIN** suits many keys and diverse containment queries.

**Expression B-tree** suits a few stable keys frequently filtered by equality, range, or sorting.

**Generated column** suits a key that has become core and needs explicit typing and constraints.

Do not keep both a GIN index and dozens of expression indexes if write overhead and storage outweigh query gains. Let the real workload decide.

## 31. Indexing Numbers Inside JSONB

Suppose phones need filtering by RAM:

```sql
SELECT
    sku,
    (attributes ->> 'ram_gb')::integer AS ram_gb
FROM lesson_model_choice.products
WHERE category_id = 10
  AND (attributes ->> 'ram_gb')::integer >= 12;
```

The value extracted via `->>` is text, so a cast is needed.

An index:

```sql
CREATE INDEX ix_products_phone_ram
ON lesson_model_choice.products (
    ((attributes ->> 'ram_gb')::integer)
)
WHERE category_id = 10;
```

### Mandatory Condition

All rows matching the partial index predicate must have a value that can cast to integer or be NULL as semantically allowed. If a phone product contains:

```json
{"ram_gb": "unknown"}
```

then creating or updating the index can fail due to an invalid cast. **Do not use an expression index to "hope data is typed correctly"**; validate data beforehand.

### Why a Partial Index?

`ram_gb` is only meaningful for phones (`category_id = 10`). A full-table index on an expression that is NULL for most categories can be less suitable than a partial index.

### When to Promote It to a Real Column?

If RAM is an important filter/sort criterion, used in reporting, and requires per-type checks/ranges, a typed/generated column or a `phone_details` table can be much simpler in the long run.

## 32. Generated Columns to Expose a JSON Key as a Typed Column

PostgreSQL supports generated columns according to version capabilities. With a **stored generated column**:

```sql
CREATE TABLE lesson_model_choice.devices (
    device_id BIGINT PRIMARY KEY,
    details JSONB NOT NULL
        CHECK (jsonb_typeof(details) = 'object'),
    brand TEXT GENERATED ALWAYS AS (
        details ->> 'brand'
    ) STORED
);

CREATE INDEX ix_devices_brand
ON lesson_model_choice.devices (brand);
```

When `details` changes, `brand` is computed from the expression according to generated column rules.

### Benefits

- Clear `WHERE brand = ?` queries.
- Statistics and indexes on a typed column.
- No manual duplication of two values during updates.
- Column-level constraints can be added as appropriate.

### Limitations

- The generated expression must obey PostgreSQL rules on immutability, references, and types.
- A stored column has storage and recomputation costs.
- Dirty data or invalid casts can cause writes or migrations to fail.
- Some generated column variants differ across PostgreSQL major versions.

If a field is already sufficiently stable, sometimes **turning it into a normal column** is even easier to understand.

## 33. JSONPath for Complex Nested Queries

PostgreSQL 12+ supports SQL/JSON path expressions.

Example:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE attributes @? '$.warranty.months ? (@ >= 24)';
```

`@?` checks whether the JSONPath expression produces a matching result.

### Why Use JSONPath?

Queries over nested arrays and objects with complex structural conditions are sometimes clearer with JSONPath.

### Indexing Caveats

GIN jsonb indexes can support **certain forms of JSONPath conditions** depending on the operator class and version, but that does not mean every JSONPath expression with ranges or computations is indexable.

Read `EXPLAIN` and test real queries instead of assuming `@?` guarantees index usage.

### JSONPath Is Not Automatic Validation

A query like "find documents with `warranty.months >= 24`" does not ensure that documents missing that field are valid according to business rules. Schema validation remains separate.

## 34. Updating a Key with jsonb_set

To change the color:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('red'::text),
        true
    ),
    updated_at = now()
WHERE tenant_id = 1
  AND sku = 'PHONE-A';
```

Explanation:

- `attributes` is the current document.
- `'{color}'` is a `text[]` path.
- `to_jsonb('red'::text)` produces a JSON string value.
- The `true` parameter allows adding the final key if it is missing when the parent path is valid.

### Do Not Think of This as an In-Place Single-Byte Physical Update

At the SQL level, you update one key. However, PostgreSQL uses MVCC: an `UPDATE` creates a new row version; the `jsonb` value may be reconstructed and incur corresponding write, TOAST, and index maintenance costs.

If a field is updated **continuously at high frequency**, placing it inside a large JSON document can cost more than using a typed column or a separate relational table.

## 35. jsonb_set with Nested Paths and Missing Parent Keys

`jsonb_set` has specific rules regarding existing path components. For example:

```sql
SELECT jsonb_set(
    '{}'::jsonb,
    '{warranty,months}',
    '24'::jsonb,
    true
);
```

Do not assume the statement above automatically creates every intermediate `warranty` object in all cases. The `create_if_missing` parameter does not mean "build the entire object tree when all ancestors are missing."

If you want to construct the object explicitly:

```sql
SELECT
    '{}'::jsonb ||
    jsonb_build_object(
        'warranty',
        jsonb_build_object('months', 24)
    ) AS merged;
```

### The || Operator Only Merges at the Top Level

`jsonb || jsonb` concatenates or merges structures according to operator rules; it is **not a recursive deep merge**. For two objects containing the same `warranty` key, the right-hand object replaces the entire value of that key rather than merging just one subkey.

When updating nested objects while preserving sibling keys, use `jsonb_set` or controlled construction.

## 36. Removing a Key with the - Operator

```sql
SELECT
    '{"color":"red","brand":"Acme"}'::jsonb
      - 'color' AS without_color;
```

Conceptual JSONB result:

```json
{"brand":"Acme"}
```

You can update a table row:

```sql
UPDATE lesson_model_choice.products
SET attributes = attributes - 'color',
    updated_at = now()
WHERE tenant_id = 1
  AND sku = 'PHONE-A';
```

For nested paths, PostgreSQL also supports `#-` with a `text[]` path:

```sql
SELECT
    '{"warranty":{"months":24,"provider":"Acme"}}'::jsonb
      #- '{warranty,provider}';
```

### Removing a Key vs. Assigning JSON null

`attributes - 'color'` results in a **missing key**.

`jsonb_set(attributes,'{color}','null'::jsonb)` leaves the key present with a JSON null value. PATCH APIs, validation logic, and `?` queries can distinguish these two states.

## 37. JSONB and Concurrency: Lost Updates in the Application

A common bug:

```text
T1 reads attributes = {"views": 10, "color": "black"}
T2 reads attributes = {"views": 10, "color": "black"}

T1 modifies color on the object in Java and UPDATEs the whole attributes column
T2 increments views on the stale object and UPDATEs the whole attributes column

The final result can lose either T1's or T2's change.
```

### What Is Wrong

Performing read-modify-write on the entire JSON document in the application without appropriate transaction isolation or optimistic locking.

### A Better Approach When Updating One Key

Use an `UPDATE` that computes the new value from the **current column in the database**:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('blue'::text),
        true
    )
WHERE product_id = 1;
```

When multiple updates target the same row, PostgreSQL coordinates row-level locking and evaluates the expression against the appropriate row version according to isolation semantics. This is far safer than overwriting the entire document with a stale client snapshot.

**However**, if business logic must guarantee complex conditions across multiple rows, you still need appropriate transactions, locking, or constraints; `jsonb_set` alone does not solve every race condition.

## 38. Incrementing a JSON Counter in a Single UPDATE

Example of a `views` counter inside a document:

```sql
UPDATE lesson_model_choice.products
SET attributes = jsonb_set(
        attributes,
        '{views}',
        to_jsonb(
            COALESCE(
                (attributes ->> 'views')::bigint,
                0
            ) + 1
        ),
        true
    )
WHERE product_id = 1;
```

This increments the value from the current document in a single statement, rather than reading 10 into Java and writing 11 regardless of other transactions.

### Should Views Be Stored in JSONB?

If views increment thousands of times per second, every UPDATE touches the JSONB row and creates lock/MVCC/WAL pressure. It is usually better to:

- Use a dedicated counter column where appropriate.
- Use a sharded/partitioned counter table to avoid hot rows.
- Batch events and flush updates periodically.
- Store events for aggregation in an analytics system.

**Just because something can be written as JSONB does not mean it is the optimal storage for high update frequency.**

## 39. Optimistic Locking with a Version Column

In a hybrid model, you can add a version column to detect updates against stale documents:

```sql
CREATE TABLE lesson_model_choice.editable_documents (
    document_id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL DEFAULT 0,
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

When a client has read `version = 5`:

```sql
UPDATE lesson_model_choice.editable_documents
SET payload = '{"color":"blue"}'::jsonb,
    version = version + 1
WHERE document_id = 10
  AND version = 5
RETURNING version;
```

If 0 rows are updated, the version has changed or the document does not exist; the application must distinguish those cases and handle the conflict (reload, merge, or retry appropriately).

### Do Not Retry Blindly

If two users edited semantically different fields, conflicts need a merge/UX policy. Blindly overwriting with a fresh read without considering user intent can lose data.

## 40. Why Can a Large JSONB Document Cost More Than Many Small Columns?

PostgreSQL stores rows using MVCC. When a row is updated:

- A new row version is created.
- The modified JSONB value may have to be rebuilt.
- WAL may be generated for the heap, indexes, or TOAST.
- TOASTed data chunks may need to be rewritten depending on storage and operations.
- Dead tuples and VACUUM demand can increase.

A JSONB object with 200 attributes where the application updates 1 attribute every second can incur higher overhead than separating hot fields into dedicated columns or tables.

### Do Not Interpret This as "Every UPDATE Always Writes All 200 Attributes to Disk"

Actual physical cost depends on size, compression/TOAST, HOT update eligibility, index entries, and storage details. PostgreSQL applies internal optimizations; to draw conclusions, measure with `EXPLAIN (ANALYZE, BUFFERS, WAL)` and storage statistics.

The design rule is to **weigh update frequency and document size**, rather than relying on an absolute statement about byte counts.

## 41. TOAST and JSONB Size

PostgreSQL uses **TOAST** to handle large column values, compressing or storing them out-of-line from the main heap page depending on storage strategy and size.

To inspect representation size:

```sql
SELECT
    sku,
    pg_column_size(attributes) AS stored_value_bytes
FROM lesson_model_choice.products
ORDER BY stored_value_bytes DESC;
```

### Understanding Size Metrics

`pg_column_size` reflects the stored value size according to PostgreSQL's storage mechanism, including details related to compression/TOAST. Do not treat it as identical to the serialized HTTP JSON string length or total bytes written on each UPDATE.

### When Documents Grow Too Large

- Reading a few keys may require accessing TOAST structures and decompressing depending on the case.
- Frequent updates can generate WAL and bloat.
- Fetching the whole document over JDBC increases network payload.
- GIN indexes across many keys and values can grow large.
- Backups and replication carry overhead proportional to updated data.

Do not embed large images, videos, or base64 blobs inside JSONB when object storage or a dedicated large-object design fits the system better.

## 42. HOT Updates and Indexes on jsonb

PostgreSQL supports **Heap-Only Tuple (HOT) updates** under suitable conditions, avoiding index entry updates when relevant criteria are met.

If you have a GIN index over all of `attributes` and constantly update `attributes`, HOT update eligibility can be lost because an indexed column changes.

### Comparing Models

**Single table:**

```text
products(product_id, price, stock, attributes JSONB)
GIN(attributes)
```

**Extracting hot fields:**

```text
products(product_id, price, attributes JSONB)
inventory(product_id, warehouse_id, quantity)
```

When stock updates continuously and attributes rarely change, splitting can:

- Reduce row width on the hot-updated table.
- Avoid stock updates impacting the `attributes` GIN index.
- Improve lock granularity per warehouse.
- Preserve relational semantics for warehouses.

Never assume splitting is always faster by default; benchmark and evaluate JOIN overhead and lifecycle complexity.

## 43. Inventory Should Be Relational, Not a Deeply Nested Object

This pattern is common but hard to constrain:

```json
{
  "inventory": {
    "warehouse_10": 20,
    "warehouse_11": 15
  }
}
```

The system needs:

- Foreign key ensuring the warehouse exists.
- `quantity >= 0`.
- Only one inventory row per product/warehouse.
- Transactional stock deduction per warehouse to prevent overselling.

Relational design:

```sql
CREATE TABLE lesson_model_choice.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

CREATE TABLE lesson_model_choice.inventory (
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    warehouse_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.warehouses(warehouse_id),
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (product_id, warehouse_id)
);
```

### Atomic Stock Deduction

```sql
UPDATE lesson_model_choice.inventory
SET quantity = quantity - 1
WHERE product_id = 1
  AND warehouse_id = 10
  AND quantity >= 1
RETURNING quantity;
```

If 0 rows are returned, the deduction did not occur because the warehouse/product did not match or stock was insufficient; the application handles it according to business rules.

This scenario requires **reliable locks and constraints**, not merely flexible schemas.

## 44. Orders: JSONB Snapshot Combined with Relational Columns

A confirmed order must preserve the **price and product details at the time of purchase**, even after the catalog changes.

```sql
CREATE TABLE lesson_model_choice.orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    order_status TEXT NOT NULL
        CHECK (order_status IN ('NEW','PAID','CANCELLED'))
);

CREATE TABLE lesson_model_choice.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL
        CHECK (unit_price >= 0),
    product_snapshot JSONB NOT NULL
        CHECK (jsonb_typeof(product_snapshot) = 'object'),
    PRIMARY KEY (order_id, line_no)
);
```

### Why Store Both product_id and a Snapshot?

- `product_id` is an FK to the current product for relational queries.
- `unit_price` is the locked-in price for accurate financial calculations.
- `product_snapshot` stores the name, specs, images, and metadata at purchase time.
- `quantity` is a constrained integer.

If you only stored `product_id` and queried `products.price` when displaying old orders, prices could change — corrupting transaction history. If you put everything into JSON without a typed `unit_price` column, revenue and tax calculations become harder to govern.

### Snapshots Should Be Business-Immutable

The application must define when a snapshot may be edited (for instance, before payment) and ensure it is never overwritten with newer catalog data once the order is finalized.

## 45. Creating an Order Item with a Consistent Snapshot

Example order insert:

```sql
INSERT INTO lesson_model_choice.orders (
    order_id, tenant_id, order_status
)
VALUES (1001, 1, 'NEW');
```

Add a product item and build its snapshot:

```sql
INSERT INTO lesson_model_choice.order_items (
    order_id, line_no,
    product_id, quantity,
    unit_price, product_snapshot
)
SELECT
    1001,
    1,
    p.product_id,
    2,
    p.price,
    jsonb_build_object(
        'sku', p.sku,
        'name', p.product_name,
        'attributes', p.attributes
    )
FROM lesson_model_choice.products AS p
WHERE p.tenant_id = 1
  AND p.sku = 'PHONE-A';
```

### Real Checkout Transactions Are More Complex

This example demonstrates building a snapshot, **not a complete checkout transaction**. A real system must consider:

- Inventory checks and reservations.
- Tax, discount, and shipping calculations at confirmation time.
- Tenant integrity between order and product.
- Concurrent price changes.
- Request idempotency.
- Commit/rollback interaction with external payment steps.

A JSONB snapshot does not automatically provide atomicity between checkout and a payment gateway.

## 46. Storing Webhook Events: jsonb Is Usually a Strong Fit

Partner payload:

```json
{
  "event_id": "evt_123",
  "event_type": "shipment.delivered",
  "version": "2026-01",
  "occurred_at": "2026-11-14T03:00:00Z",
  "data": {
    "shipment_id": "ship_99",
    "carrier": "Carrier A",
    "delivered_at": "2026-11-14T02:59:00Z"
  }
}
```

Design:

```sql
CREATE TABLE lesson_model_choice.webhook_events (
    inbound_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object'),
    processing_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (processing_status IN (
            'PENDING','PROCESSED','FAILED'
        )),
    UNIQUE (provider, external_event_id)
);
```

### Why Is Hybrid Good Here?

- `provider` / `external_event_id`: typed and unique idempotency key.
- `event_type`: filtering and job routing.
- `received_at`: indexing, range queries, and retention.
- `processing_status`: worker state.
- `payload`: stores external documents that vary by version.

You do not need to flatten every nested event field into columns immediately at ingestion, especially before the event is validated and normalized.

## 47. Storing Raw Payloads and Signatures: Is jsonb Enough?

Many webhook providers compute signatures over the **original raw HTTP body byte string**. JSONB can:

- Strip whitespace.
- Reorder object keys on output.
- Deduplicate repeated keys.
- Normalize numeric representations according to JSONB rules.

Therefore, **do not use `payload::text` from jsonb to re-verify a signature that requires the original raw bytes**.

Store raw payload bytes or text separately when audit or signature verification requires it:

```sql
-- Example dedicated schema for raw storage requirements:
CREATE TABLE lesson_model_choice.raw_inbound_payloads (
    inbound_id BIGINT PRIMARY KEY,
    raw_body BYTEA NOT NULL,
    parsed_body JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Signature verification must follow the provider's specification, using the raw bytes and appropriate cryptographic algorithms.

## 48. JSONB and Schema Evolution

Initially a document has:

```json
{"brand":"Acme","ram_gb":8}
```

Later a new version introduces:

```json
{"brand":"Acme","memory":{"ram_gb":8,"storage_gb":256}}
```

An old query:

```sql
WHERE (attributes->>'ram_gb')::integer >= 8
```

may miss the new records because `ram_gb` moved under `memory`.

**"No ALTER TABLE needed" does not mean "no migration needed."** You still have to manage:

- Payload schema/version.
- Old and new readers.
- Index definitions.
- Validation.
- Backfilling historical data.
- BI/reporting.
- Older mobile or client apps.

Attach an explicit version whenever structures undergo breaking changes.

## 49. Managing JSON Schema Versions

One approach:

```json
{
  "schema_version": 2,
  "memory": {
    "ram_gb": 8,
    "storage_gb": 256
  }
}
```

However, if version is a system field queried or routed very frequently, making it a **relational column** can also be appropriate:

```sql
CREATE TABLE lesson_model_choice.versioned_payloads (
    payload_id BIGINT PRIMARY KEY,
    schema_version INTEGER NOT NULL
        CHECK (schema_version > 0),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);
```

### Reading Strategy

- Parsers know which versions remain supported.
- Normalize older versions into a unified data transfer model.
- Bound the support window for very old versions.
- Fail or send to a dead-letter queue if the version is unrecognized.
- Never silently treat a missing key as `0` when doing so alters business meaning.

## 50. Migrating from JSONB to a Relational Column

An attribute starts as metadata and later becomes a major filter.

Example `brand`:

**Step 1 — Add the new column:**

```sql
ALTER TABLE lesson_model_choice.products
ADD COLUMN brand TEXT;
```

**Step 2 — Backfill from JSON:**

```sql
UPDATE lesson_model_choice.products
SET brand = attributes ->> 'brand'
WHERE brand IS NULL
  AND attributes ? 'brand';
```

**Step 3 — Verify:**

```sql
SELECT
    product_id,
    sku,
    brand,
    attributes ->> 'brand' AS brand_in_json
FROM lesson_model_choice.products
ORDER BY product_id;
```

**Step 4 — Design dual-read/dual-write or a controlled cutover.**

**Step 5 — Switch queries and indexes to the column.**

**Step 6 — Once verified and data is valid, add `NOT NULL`/`CHECK`/`UNIQUE` if needed.**

### Race Condition Warning During Migration

If producers are still writing to `attributes.brand` during backfill, the `brand` column can become stale. You need a consistency plan:

- Pause writes at cutover time.
- Dual-write within an appropriate transaction.
- Use a controlled synchronization trigger.
- Backfill, reconcile discrepancies, and then switch the source of truth.

Do not copy once and assume both copies will stay in sync forever.

## 51. Reverse Migration: From Relational Columns to JSONB

Suppose a group of attributes is rarely used and now changes rapidly. You can:

1. Add a `metadata JSONB NOT NULL DEFAULT '{}'` column.
2. Backfill from existing columns using `jsonb_build_object`.
3. Switch readers and writers.
4. Monitor consistency.
5. Drop old columns only when a rollback plan exists and no dependencies remain.

Example:

```sql
SELECT jsonb_build_object(
    'sku', sku,
    'display_name', product_name,
    'price', price
)
FROM lesson_model_choice.products
LIMIT 3;
```

This illustrates constructing JSON, **not a recommendation to move SKU or price out of relational columns**. Those are core values in the sample model.

### Type Conversion Must Account for Existing Data

Not every `TEXT` value is valid JSON; do not blindly apply `::jsonb` to columns holding plain strings. To store a text string as a JSON string, use `to_jsonb(text_column)` instead of treating plain text as a JSON document.

## 52. Choosing the Source of Truth

A hybrid model trap:

```text
products.price = 100
attributes.price = 120
```

The UI displays 120 while checkout charges 100. This bug stems from a **duplicate source of truth**.

Principles:

- Every important business attribute should have **one authoritative source**.
- If copied for caching or snapshots, document the semantics and timestamp.
- A historical snapshot must never be mistaken for the current price.
- A generated column can avoid dual-writes when expressions permit.
- If temporarily dual-writing during a migration, define reconciliation rules and a plan to retire one copy.

### A Clear Model

```text
current_price in products.price
  └── source of truth for current price

product_snapshot.price in order_items
  └── immutable snapshot of a past transaction
```

Two differing values are **intentionally correct** when they belong to different points in time, not an inconsistency.

## 53. JSONB and Audit/History

A JSONB record may be edited multiple times. If you need to know:

- Who changed the price?
- Which attributes changed?
- From what value to what value?
- Effective from what timestamp?

then a single current `attributes` column is insufficient.

Dedicated history design:

```sql
CREATE TABLE lesson_model_choice.product_attribute_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.products(product_id),
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    old_attributes JSONB NOT NULL,
    new_attributes JSONB NOT NULL
);
```

### Snapshots vs. Events

Storing **full old/new documents** is easy to audit but can consume significant storage. Storing **patches/diffs** saves space in some workloads, but makes replay and historical queries more complex.

Choose based on:

- Legal/audit requirements.
- Retention period.
- Reconstruction needs.
- Change frequency.
- Storage size and point-in-time query patterns.

Do not assume JSONB automatically provides an auditing system with actors and accurate timestamps.

## 54. Multi-Tenant Integrity Constraints

If `products` has `tenant_id` and `orders` also has `tenant_id`, a single-column `FOREIGN KEY (product_id)` does not prevent an order from tenant 1 from referencing a product belonging to tenant 2.

You can design **composite keys and FKs**:

```sql
ALTER TABLE lesson_model_choice.products
ADD CONSTRAINT uq_products_tenant_id_product_id
UNIQUE (tenant_id, product_id);
```

A referencing table includes both tenant and product columns plus a composite FK:

```sql
CREATE TABLE lesson_model_choice.tenant_product_watchlist (
    tenant_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, product_id),
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES lesson_model_choice.products(
            tenant_id, product_id
        )
);
```

### Why Not Keep tenant_id Only in JSON?

Tenant scope is a **security and integrity** boundary. If it lives only inside nested JSON, FKs, composite uniqueness, and RLS policies become harder to enforce and reason about.

**Do not treat a matching `tenant_id` inside JSON as authorization control.** Row-level security and application authorization must be designed and tested independently.

## 55. Choosing a Schema for BI and Reporting Queries

A summary report by tenant and category:

```sql
SELECT
    p.tenant_id,
    p.category_id,
    COUNT(*) AS product_count,
    AVG(p.price) AS average_price
FROM lesson_model_choice.products AS p
GROUP BY p.tenant_id, p.category_id
ORDER BY p.tenant_id, p.category_id;
```

Relational columns give filters and aggregates clear types.

If you need a report of average phone RAM:

```sql
SELECT
    p.tenant_id,
    AVG((p.attributes ->> 'ram_gb')::numeric)
        AS average_ram_gb
FROM lesson_model_choice.products AS p
WHERE p.category_id = 10
  AND jsonb_typeof(
      p.attributes -> 'ram_gb'
  ) = 'number'
GROUP BY p.tenant_id;
```

### Data Quality Issues

If a phone row contains `"ram_gb":"unknown"`, casting in the query can still fail if executed on a plan path that does not guarantee valid data first; validate and normalize before running reports on untrusted data. For official BI metrics, promoting fields to typed columns or validated staging tables is usually much easier to govern.

### Does BI Need JSONB?

Raw JSONB remains useful for auditing and integration. However, reporting marts/tables with typed columns usually make SQL and BI tools simpler and more stable.

## 56. Is EAV (Entity–Attribute–Value) a Replacement for JSONB?

The EAV model:

```text
product_id | attribute_name | attribute_value
-----------+----------------+----------------
1          | color          | black
1          | ram_gb         | 8
1          | screen_inches  | 6.5
```

It is very flexible, but introduces trade-offs:

- Many rows and JOINs/pivots for a single product.
- Values often have to be stored as text, losing type safety without complex design.
- Hard to write per-type CHECK constraints and semantic unique constraints.
- Numeric range sorting on text is error-prone.
- Queries filtering on multiple attributes can become expensive.

**EAV is not inherently superior to JSONB or relational child tables.** It can fit when attributes have independent governance metadata/lifecycles, are queried independently, and are carefully modeled.

### When Attributes Are Business-Defined Metadata

An `attribute_definitions` table with type, unit, and allowed values can help validate both EAV and JSONB; however, dynamic validation in the database usually requires more logic than basic constraints.

## 57. Indexing and Query Plans on JSONB

Use:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    product_id,
    sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND attributes @> '{"brand":"Acme"}'::jsonb;
```

Check:

- `Seq Scan` or `Bitmap Index Scan` / `Bitmap Heap Scan`?
- Is the GIN index used?
- Estimated rows vs. actual rows?
- Shared buffer reads/hits?
- Where are filter predicates applied?
- Planning and execution time?

On a 5-row sample table, **`Seq Scan` may be optimal**. Do not take the planner skipping GIN on tiny tables as proof that the index is broken.

### Practical Limitations

GIN works well for many existence/containment checks, but does not automatically turn every range query:

```sql
WHERE (attributes->>'ram_gb')::int >= 12
ORDER BY (attributes->>'ram_gb')::int
```

into an index range scan. For that workload, a B-tree expression index or generated typed column is a better fit.

## 58. Multi-Predicate JSONB Queries

Example:

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND category_id = 10
  AND attributes @> '{"brand":"Acme"}'::jsonb
  AND (attributes ->> 'ram_gb')::integer >= 8;
```

The planner may use:

- A B-tree for tenant/category filtering.
- A GIN containment index for brand.
- An expression B-tree for RAM.
- Bitmap index combinations in some cases.
- Or a Seq Scan if the table is small or selectivity is low.

**No single index optimizes every condition.** When a workload is critical, consider promoting key filter fields to typed columns so condition/index combinations remain predictable.

### Do Not Explode Indexes Across Every JSON Key

If customers have 500 custom attributes, creating 500 B-tree indexes is very expensive. Tier your data:

1. Core fields are always typed columns.
2. 5–10 common JSON keys get targeted indexes.
3. Rarely searched metadata stays in JSONB only.
4. Broad search use cases may need a dedicated search index/service if PostgreSQL can no longer serve them reasonably.

## 59. JSONB and Planner Statistics

PostgreSQL collects statistics for relational columns like `price` and `tenant_id`, and for some expressions when suitable indexes or extended statistics exist. For arbitrary keys nested inside JSONB, cardinality and selectivity estimates can be much harder.

Consequences:

- The planner may misestimate brand or category ratios.
- It may choose a Seq Scan instead of an index scan, or vice versa.
- Inaccurate cardinality estimates degrade joins and aggregates.

### How to Improve

- Run `ANALYZE` after significant data changes.
- Create expression indexes or statistics for important keys.
- Use generated typed columns with column statistics.
- Write predicates matching the index operators.
- Inspect `EXPLAIN (ANALYZE, BUFFERS)` on representative data.

Do not blindly raise `default_statistics_target` server-wide when the bottleneck comes from query design or JSON key extraction.

## 60. GIN Indexes and Write Cost

A GIN index on `attributes` enables diverse searches, but carries costs:

- Index creation takes time and storage space.
- Inserts and updates must maintain index entries.
- WAL, index bloat, and vacuum/maintenance can be affected.
- Under very frequent document updates, write overhead can be substantial.
- GIN settings such as `fastupdate` and pending list behavior must be understood when tuning for a workload.

### An Index Is Not a Free Optimization

For a product catalog where `attributes` is read thousands of times and updated a few times a day, GIN can be well worth it.

For counters or inventory updated thousands of times per second, JSONB + GIN on every update is usually a choice that needs reconsideration.

**Read/write ratio is part of the modeling decision**, not just index selection.

## 61. Using Partial Indexes for JSONB

Suppose only active products need brand filtering:

```sql
CREATE INDEX ix_active_products_brand
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'brand')
)
WHERE status = 'ACTIVE';
```

The index can be much smaller if many products are inactive.

### Queries Must Match the Predicate

```sql
SELECT sku
FROM lesson_model_choice.products
WHERE tenant_id = 1
  AND status = 'ACTIVE'
  AND attributes ->> 'brand' = 'Acme';
```

The planner can use the index if it can prove that the query predicate implies the partial index's `WHERE status = 'ACTIVE'` clause.

### Prepared Statements

A generic query with `status = $1` cannot always be proven equivalent to the specific predicate in a generic plan. Measure real queries using your driver and server's prepared-statement behavior.

## 62. Unique Constraints on a Nested JSON Key

If `external_code` lives inside JSON and must be unique per tenant, you can create a unique expression index:

```sql
CREATE UNIQUE INDEX ux_products_tenant_external_code
ON lesson_model_choice.products (
    tenant_id,
    (attributes ->> 'external_code')
);
```

### NULL Semantics

If the key is missing or its value is JSON null, `->>` returns SQL NULL. By default, unique indexes allow multiple NULLs; therefore, the index above does not enforce **at most one document missing `external_code`**.

On PostgreSQL 15+, you can consider `NULLS NOT DISTINCT` if business logic truly wants missing/null treated as a duplicate key. Still, check the semantics: both a missing key and an explicit JSON null extract to SQL NULL.

### Should It Become a Column?

If `external_code` is a required business key, referenced by FKs, or heavily used in UPSERTs, a typed column with `NOT NULL`/`UNIQUE` is usually clearer than an expression index hiding uniqueness inside nested JSON.

## 63. Full-Text Search and JSONB

Do not use `attributes @> ...` to replace every text search problem.

For example, if products need keyword search across names and descriptions:

- B-tree fits equality, ranges, and ordering.
- `pg_trgm` (extension) helps substring and `ILIKE` matching.
- Full-text search with `tsvector`/GIN fits linguistic search needs.
- GIN on `jsonb` fits JSON containment/existence, and does not turn itself into a linguistic search engine.

### When Metadata Has Many Text Fields

You can build a normalized search document from core columns and searchable text attributes, then index it with the appropriate full-text mechanism.

Do not create a full-document JSONB GIN index and expect every `ILIKE '%term%'` query on a nested field to run fast.

## 64. API Design: Serializing JSONB and Typed Fields

An API might return:

```json
{
  "id": 42,
  "sku": "PHONE-A",
  "name": "Phone A",
  "price": "12990000.00",
  "status": "ACTIVE",
  "attributes": {
    "brand": "Acme",
    "ram_gb": 8
  }
}
```

### Why Is price Sometimes a String in a JSON API?

An API may intentionally serialize decimals as strings to avoid precision loss in clients using IEEE-754 floating point; that is a **wire-protocol choice**. Inside PostgreSQL, `price` remains `NUMERIC` — an API returning strings does not mean the database should store text.

### Avoid Exposing Raw JSON Directly to APIs

If raw `attributes` contains internal fields:

```json
{"internal_cost": 9000000, "supplier_token": "..."}
```

returning the entire document to clients leaks sensitive data. Use selective DTOs/serialization and proper authorization.

**JSONB does not provide automatic per-key field-level access control** just because the column is a document type.

## 65. JDBC: Storing JSONB with PreparedStatement

With the PostgreSQL JDBC driver, an application can use `PGobject` to bind JSONB:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import org.postgresql.util.PGobject;

public final class ProductWriter {
    public static void insert(
            Connection conn,
            long tenantId,
            long categoryId,
            String sku,
            String name,
            java.math.BigDecimal price,
            String attributesJson
    ) throws SQLException {
        PGobject json = new PGobject();
        json.setType("jsonb");
        json.setValue(attributesJson);

        String sql = """
            INSERT INTO lesson_model_choice.products(
                tenant_id, category_id, sku,
                product_name, price, attributes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, tenantId);
            ps.setLong(2, categoryId);
            ps.setString(3, sku);
            ps.setString(4, name);
            ps.setBigDecimal(5, price);
            ps.setObject(6, json);
            ps.executeUpdate();
        }
    }
}
```

This assumes an active PG JDBC driver, connection, and appropriate transaction handling. `PGobject` simply informs the driver of the parameter type; PostgreSQL still parses and validates the JSON according to `jsonb` rules.

### Do Not Concatenate JSON Directly into SQL Strings

Do not write:

```java
String sql = "INSERT ... VALUES ('" + rawJson + "')";
```

This invites SQL injection and escaping bugs and bypasses prepared statements. Bind JSON values as parameters.

## 66. JDBC: Reading JSONB and Parsing with Jackson

`ResultSet.getString(...)` retrieves the JSON text representation for the column, which Jackson can parse:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import com.fasterxml.jackson.core.JsonProcessingException;

public final class ProductReader {
    private static final ObjectMapper JSON =
        new ObjectMapper();

    public static JsonNode readAttributes(
            Connection connection,
            long productId
    ) throws SQLException, JsonProcessingException {
        String sql = """
            SELECT attributes
            FROM lesson_model_choice.products
            WHERE product_id = ?
            """;

        try (PreparedStatement ps =
                connection.prepareStatement(sql)) {
            ps.setLong(1, productId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Product not found.
                }
                return JSON.readTree(
                    rs.getString("attributes")
                );
            }
        }
    }
}
```

### Notes

- Jackson's `JsonNode` is an in-memory Java tree, not an automatic row schema.
- Check types, missing keys, nulls, and `schema_version`.
- Do not fetch multi-MB documents if an endpoint only needs `product_name` and `price`.
- Do not return all attributes to clients if they include internal data.
- `PreparedStatement` must bind all input values rather than concatenating strings.

## 67. JDBC: Safe Queries on Nested JSON

Example filtering by brand:

```java
String sql = """
    SELECT product_id, sku
    FROM lesson_model_choice.products
    WHERE tenant_id = ?
      AND attributes ->> 'brand' = ?
    ORDER BY product_id
    """;

try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, brand);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("product_id");
            String sku = rs.getString("sku");
            // Process data.
        }
    }
}
```

### Dynamic JSON Keys/Paths

Never concatenate arbitrary user-supplied JSON keys or SQL identifiers into SQL. If dynamic attribute filtering is needed:

- Use a whitelist of supported keys.
- Use functions/operators that accept paths or values as parameters where appropriate.
- Limit path depth and length.
- Never accept arbitrary SQL fragments from clients.
- Validate data types and limits to prevent overly expensive queries.

**Parameterized values protect literal values; dynamic SQL structure and identifiers still require strict validation.**

## 68. Spring/JPA and JSONB: Choosing a Sensible Mapping

A Spring application can:

- Use JDBC/`JdbcTemplate` and Jackson.
- Use Hibernate JSON mappings supported by the specific ORM version.
- Store attributes as a JSON string or `JsonNode` depending on the mapping layer.
- Use native SQL for operators like `@>`, `?`, and `jsonb_set` where appropriate.

### Avoid Assuming the ORM Enforces Constraints Automatically

A Java field `Map<String,Object> attributes` does not automatically provide:

- A `CHECK` ensuring a JSON object.
- FKs for nested IDs.
- Unique constraints for business keys.
- Versioned JSON schema validation.
- Concurrency safety for read-modify-write.

Database constraints and migrations remain essential.

### Dirty Checking and Overwrites

An ORM may re-serialize and rewrite the entire document whenever the object changes. Under concurrent workloads, understand transaction isolation, optimistic locking (`@Version`), and the `UPDATE` statements the ORM generates.

Never catch an exception and continue using a failed Hibernate transaction without rolling back.

## 69. Security: JSONB Does Not Replace RLS

A multi-tenant table should separate:

- **Authentication:** who is logged in?
- **Authorization:** which tenants/products may the user access?
- **RLS/SQL filters:** database-level data isolation.
- **JSON validation:** does the payload have a valid shape and values?

When `tenant_id` is a typed column, PostgreSQL can apply RLS policies and indexes cleanly. Putting `tenant_id` inside `attributes.tenant_id` does not make authorization safe.

### Data Type Does Not Determine Access Control

JSONB is a storage representation, not a security layer. Keys like internal notes, cost price, or access tokens must be separated or protected according to sensitivity and access policies.

### SQL Auditing

Do not log unredacted documents if they contain tokens or PII. Log only identifiers, schema versions, hashes, or approved fields per retention policy.

## 70. Sensitive Data and Encryption

If payloads contain personal data or secrets:

- Avoid putting tokens or passwords into plain-text JSONB unnecessarily.
- Enforce database and application permissions.
- Use encryption at rest, encryption in transit, and proper key management when required.
- Consider application-level field encryption.
- Do not put a GIN index on sensitive data and open arbitrary query access to it.

**Encryption has trade-offs:** encrypted data cannot support standard JSONB containment or range queries. Decisions must prioritize security needs first rather than compromising sensitive data just to make indexing easier.

## 71. Schema Drift: When the Same Key Changes Type

Example:

```json
{"ram_gb": 8}
```

and:

```json
{"ram_gb": "8 GB"}
```

or:

```json
{"ram_gb": null}
```

If a query runs:

```sql
(attributes ->> 'ram_gb')::integer
```

then `"8 GB"` throws a cast error. An entire SQL report can fail simply because one producer emitted the wrong type.

### Mitigations

1. Define schema and key types per version.
2. Validate on ingestion.
3. Reject invalid payloads or route them to quarantine.
4. Backfill and repair historical data.
5. Promote critical keys to typed columns.
6. Monitor missing and mistyped key rates.

**Do not use `COALESCE(..., 0)` to mask bad data**, especially for financial or technical numbers that must be accurate.

## 72. Modeling Historical Events

For event sourcing or event logs:

```sql
CREATE TABLE lesson_model_choice.business_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_version INTEGER NOT NULL CHECK (event_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload JSONB NOT NULL
        CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX ix_business_events_aggregate_time
ON lesson_model_choice.business_events (
    tenant_id,
    aggregate_type,
    aggregate_id,
    occurred_at
);
```

This is hybrid:

- Typed envelope metadata for filtering, routing, and time ordering.
- Event payload document varying by event type and version.

### Event Logs Differ from Current-State Tables

An append-only event table can hold many events for the same aggregate, while current state is a separate projection. Do not use JSONB payloads as an excuse to skip idempotency, ordering, or versioning rules.

## 73. Defining Tenant-Customizable Metadata

A platform lets each tenant define custom product attributes:

```text
Tenant 1:
  custom.color
  custom.shipping_class

Tenant 2:
  custom.material
  custom.certification
```

JSONB provides flexible storage:

```json
{
  "custom": {
    "shipping_class": "fragile",
    "color": "black"
  }
}
```

Yet you still need a tenant-level **attribute definition registry**:

```sql
CREATE TABLE lesson_model_choice.attribute_definitions (
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_model_choice.tenants(tenant_id),
    attribute_code TEXT NOT NULL,
    value_type TEXT NOT NULL
        CHECK (value_type IN (
            'string','number','boolean','array'
        )),
    is_required BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, attribute_code)
);
```

### Why Is a Registry Needed?

- The UI knows each field's type.
- Validation knows the allowed values.
- Search knows which fields are filterable.
- Governance can enforce permissions and attribute quotas.
- Data quality can be measured.

The registry **does not automatically create dynamic CHECK constraints on every JSON key** just by existing; application logic, triggers, or validation pipelines must still enforce the rules.

## 74. Bounding Customization to Prevent Unbounded Document Growth

A system allowing arbitrary keys needs limits on:

- Number of keys per document.
- Nesting depth.
- Payload size.
- Value types and maximum array length.
- Valid key names.
- Which keys may be used in filters.
- Permissions to modify certain keys.
- Update frequency.

Without limits, one customer can create huge documents, inflating:

- Table and TOAST storage.
- WAL volume on updates.
- Parse and serialization time.
- GIN index size.
- Query, backup, and replication costs.

**Flexible schemas require matching governance.**

## 75. Versioning and Migration in Multi-Service Environments

A producer service starts sending `memory.ram_gb` instead of `ram_gb`. An older consumer service still reads the old key.

Safe strategy:

1. Define the new schema version.
2. Update consumers to read **both old and new** formats based on version.
3. Update producers to emit the new format.
4. Backfill old documents as needed.
5. Check remaining data and traffic still using the old version.
6. Retire support for the old format only once conditions are met.

### Can Temporary Dual Fields Be Used?

Yes, provided they are time-bounded and have a clear source of truth:

```json
{
  "schema_version": 2,
  "ram_gb": 8,
  "memory": {"ram_gb": 8}
}
```

The two fields can contradict each other if producers fall out of sync. Explicit version conversion logic is better than keeping duplication permanently.

## 76. JSONB Does Not Automatically Reduce JOINs in a Beneficial Way

One rationale for JSONB is "fetch one document without JOINs." That can hold for snapshot views, but **denormalization** carries costs:

- When a supplier's name or price changes, many documents must be updated.
- Risk of stale data.
- No FK to nested IDs.
- Large documents sent over the network.
- Listing products by supplier can be slower than an indexed join.

### When Denormalization Helps

- The data is a historical snapshot and **must not update when the source changes**.
- The payload is read together very frequently.
- The number of copies is bounded.
- Update and caching rules are explicit.

Do not use JSONB to duplicate the entire catalog, suppliers, warehouses, and inventory just to avoid a few JOINs.

## 77. Hybrid Models and Transactions

PostgreSQL provides ACID transactions across both typed columns and `jsonb` in the same transaction:

```sql
BEGIN;

UPDATE lesson_model_choice.products
SET price = price + 100000,
    attributes = jsonb_set(
        attributes,
        '{promotion_note}',
        to_jsonb('price updated'::text),
        true
    )
WHERE tenant_id = 1
  AND sku = 'PHONE-A';

COMMIT;
```

If the transaction rolls back, changes to both columns in the row roll back together under PostgreSQL's transaction mechanism. JSONB is not "outside transactions" simply because it stores a document structure.

### External Side Effects Are Different

HTTP calls, emails, or operations in external systems do not roll back with a PostgreSQL transaction. Use an outbox pattern and idempotency when consistency between the database and external systems is required.

## 78. The Query Planner Does Not Know the Business Meaning of a JSON Key

A key:

```json
{"stock": 5}
```

does not automatically tell PostgreSQL that:

- Stock cannot be negative.
- Stock belongs to a warehouse.
- There is only one stock row per product/warehouse.
- Updates must prevent overselling.

Similarly, `{"price": 100}` does not inherently carry numeric precision or currency semantics.

**Business constraints are an explicit design step.** For fields where mistakes carry high impact, typed columns and constraints move enforcement closer to the data.

## 79. Decision Matrix: Choosing Across 6 Criteria

A scorecard table:

| Question | Relational Strong | JSONB Strong | Hybrid |
|---|---|---|---|
| Strict invariants with FK/UNIQUE/CHECK? | Yes | Not a default strength | Core in columns |
| Structure varies per tenant/version? | Costly schemas/migrations | Yes | Attributes in JSONB |
| Frequent range/sort/aggregate queries? | Yes | Requires casts/indexes | Hot query keys in columns |
| Frequent whole-payload read/write? | Must reconstruct | Yes | Snapshot/payload |
| Continuous updates to a hot field? | Easy to isolate/lock cleanly | Document updates carry cost | Hot field in column/table |
| Heavy BI/FK/join analytics? | Yes | More complex | Relational for dimensions |

### A Short Rule of Thumb

> **Put core invariants and inter-entity relationships into the relational schema; put variable, lightly constrained metadata and snapshots into `jsonb`; only move data across that boundary with clear evidence from requirements or performance.**

This is a guideline, not an absolute law. A document-centric system may reasonably use `jsonb` as its primary store; a transactional accounting system typically requires much more relational structure.

## 80. Common Mistakes

**"With JSONB, you don't need a schema."** False. The schema still exists as a contract across applications, producers, and consumers and needs versioning and validation.

**"JSONB is always faster than JOINs."** No. It depends on data volume, indexes, update rate, and query patterns.

**"PostgreSQL JSONB is a NoSQL database completely separate from ACID."** No. JSONB is a data type inside PostgreSQL's transactional engine.

**"JSONB preserves exact raw JSON bytes and key order."** No. Use raw text or `bytea` if you need signature verification or exact input preservation.

**"A JSON number and a JSON string are automatically equal."** No. `{"ram":8}` and `{"ram":"8"}` have different types.

**"A missing key and `key: null` are identical."** No. `?` can distinguish key existence.

**"SQL NULL and JSON null are the same thing."** No. They have distinct semantics.

**"`attributes->>'ram_gb'` is already an integer."** No. `->>` returns SQL text.

**"Casting JSON text to `int` is always safe."** No. Mistyped values or non-numeric strings will raise errors.

**"`CHECK(jsonb_typeof(x->'k')='number')` requires the key to exist."** Insufficient; a missing key returns SQL NULL and `CHECK` does not reject UNKNOWN.

**"A GIN index makes every JSON condition fast."** No. Operator class, expression structure, and filter selectivity determine effectiveness.

**"`jsonb_path_ops` supports all operators of `jsonb_ops`."** No. Key-existence operators `?`/`?|`/`?&` behave differently.

**"A GIN index efficiently supports `ORDER BY (json->>'score')::int`."** Not by default. Consider a B-tree expression index or a generated typed column.

**"An expression index cast will clean dirty data."** No. It fails when an invalid cast is encountered.

**"A partial index works for every parameterized query."** No. The planner must prove the query predicate implies the index predicate; generic plans have limits.

**"`jsonb_set` modifies a single byte in place without WAL."** No. `UPDATE` follows MVCC and incurs storage, index, and TOAST costs.

**"Putting stock in JSONB avoids race conditions."** No. Race conditions and lost updates still require transactions, atomic UPDATEs, or locking.

**"JSONB automatically enforces foreign keys to nested `supplier_id`."** No. Explicit relational keys and constraints are needed.

**"JSON arrays replace all junction tables."** No. Many-to-many relationships with metadata, FKs, or independent lifecycles usually belong in junction tables.

**"SQL arrays automatically enforce FKs on each element."** No.

**"Adding a column and backfilling once completes the migration."** Not if old writers or consumers are still active.

**"A `schema_version` inside JSON automatically makes clients compatible."** No. Conversion, validation, and rollout plans are still required.

**"Duplicating `price` in both a column and JSON has no downside."** False if both are treated as the current source of truth.

**"JSONB is an automatic audit log."** No. You need actors, timestamps, and history or event records.

**"CTE/GIN/JSONB is always optimal."** No. Measure plans, memory, CPU, WAL, disk, and concurrency.

**"JSONB is best for all metadata because it avoids migrations."** No. Metadata frequently used in filters, sorts, or constraints may belong in first-class columns.

**"Every field should be normalized because relational is standard."** No. Documents and snapshots rarely queried independently may belong in JSONB.

## 81. Design Review Checklist

Before approving a schema containing `jsonb`, answer:

1. Are core keys and relationships extracted into typed columns with PK/FK/UNIQUE constraints?
2. Which JSON keys are required, and what are their types and allowed values?
3. Is the distinction between a missing key, JSON null, and SQL NULL defined?
4. Are versioning and backward-compatibility policies in place?
5. Which operators do critical queries use, and are matching indexes present?
6. Are there numeric JSON searches, ranges, or sorts that should be promoted to typed fields?
7. Does the document contain foreign IDs or collections that should become junction tables?
8. Are any fields updated very frequently?
9. How will document size and GIN index size grow across many tenants?
10. Are there planner statistics and benchmarks on representative data distributions?
11. Is current state clearly separated from immutable snapshots?
12. Is there a single source of truth for price, status, and identity?
13. Are idempotency/unique keys and concurrency policies defined?
14. How will migrations, backfills, and rollbacks work as the schema evolves?
15. Does JSONB contain secrets or fields that must not be returned to clients?

This is a **system design** checklist and does not replace separate QA stages for logic and lesson content quality.

## 82. Process for Solving a Real Modeling Problem

### Step 1 — Write Down Invariants First

For example: "No tenant may have two identical SKUs," "current price is always >= 0," "each product/warehouse has one stock count," "orders must preserve the price at purchase time."

### Step 2 — Identify Entities and Relationships

Tenant, product, category, supplier, warehouse, order, order item, tag.

### Step 3 — Group Attributes

- Core typed.
- Optional but stable.
- Category-specific metadata.
- Snapshot/historical.
- Event/raw inbound.

### Step 4 — Choose the Schema

Put keys, relationships, and hot fields into columns/tables; put variable parts into `jsonb` when there is a real benefit.

### Step 5 — Design Validation

DB constraints for core data; schema versions and validation contracts for JSON keys.

### Step 6 — Design Indexes Around the Workload

B-tree for lookups/ranges/ordering, GIN for containment/existence, expression/generated columns for heavily used keys.

### Step 7 — Account for Write Amplification and Concurrency

Evaluate document size, update frequency, HOT/TOAST/WAL, lost-update protection, and connection pooling.

### Step 8 — Test Schema Evolution

Old/new producers, missing keys, explicit nulls, wrong types, backfills, and rollbacks.

### Step 9 — Run Benchmarks

Measure latency, buffer usage, index size, WAL, locks, and throughput with representative data.

### Step 10 — Review Operations

Retention/audit, security, migrations, backups, and query observability.

## 83. Practice Exercises

### Exercise 1 — Choosing a Model

A customer table has `customer_id`, email, name, registration date, and arbitrary JSON preferences. Propose a schema and explain which fields should be relational columns and which should be JSONB.

### Exercise 2 — Distinguishing json and jsonb

Run `SELECT '{"a":1,"a":2}'::json` and the corresponding `::jsonb`. Describe the differences in duplicate keys and input preservation.

### Exercise 3 — JSON Types

Use `jsonb_typeof` with object, array, string, number, boolean, and JSON null. Compare with SQL NULL.

### Exercise 4 — Missing Key

Given `{"color":null}` and `{}`. Use `?`, `->`, and `->>` to distinguish a present-but-null key from a missing key.

### Exercise 5 — CHECK JSON Object

Create a table with `attributes JSONB NOT NULL CHECK(jsonb_typeof(attributes)='object')`. Try inserting an array, a number, and an object. Which cases succeed?

### Exercise 6 — CHECK Requiring a Key

Write a CHECK requiring `attributes ? 'ram_gb'` and `jsonb_typeof(attributes->'ram_gb')='number'`. Explain why comparing `jsonb_typeof` alone is not enough.

### Exercise 7 — Wide Relational Table

Analyze `products_wide` with `phone_ram_gb`, `shoe_size_eu`, and `book_isbn`. When are multiple nullable columns simpler than `jsonb`?

### Exercise 8 — Per-Type Child Tables

Design `products_base` and `phone_details` with FK/PK/CHECK. What must be added if you want to guarantee a `phone_details` row always references a product in category PHONE?

### Exercise 9 — Hybrid Catalog

Use the sample `products` table. Insert a "shoes" product with its own attributes while keeping SKU/price/status in typed columns. Explain why no `ALTER TABLE` is needed.

### Exercise 10 — Reading Nested Keys

Retrieve `warranty.months` and `warranty.provider` from `attributes` using `#>` / `#>>`. When `provider` is missing, what does the query return?

### Exercise 11 — Containment Filtering

Write a query to find products of brand Acme using `@>`. Test querying the same key with a mismatched number vs. string type; describe the result.

### Exercise 12 — Array Containment

Find phones whose `connectivity` contains `wifi` using `@>`. Why is containment not an exact ordered array comparison?

### Exercise 13 — LATERAL Unnesting JSON

Use `jsonb_array_elements` to expand `connectivity` into multiple rows. How do you handle missing or non-array keys to avoid errors on untrusted data?

### Exercise 14 — SQL Array

Create a table with `labels TEXT[]`. Compare array containment filtering with JSON arrays. Why do neither automatically enforce FKs to a `labels` table?

### Exercise 15 — Junction Table

Design `tags` and `product_tags`. State at least three business requirements that make a junction table better than a JSON array.

### Exercise 16 — GIN Index

Create a GIN index on `attributes` and run `EXPLAIN (ANALYZE, BUFFERS)` with an `@>` predicate. Why might the planner still choose Seq Scan on 5 rows?

### Exercise 17 — jsonb_ops / jsonb_path_ops

Compare supported operators. If an API uses `attributes ? 'color'` very frequently, what assumption about `jsonb_path_ops` should you avoid?

### Exercise 18 — Expression B-tree

Create an index on `(tenant_id, attributes->>'brand')` and run a query filtering on the same expression. When can an expression index outperform a full-document GIN index?

### Exercise 19 — Numeric Key

Create a partial expression index for `(attributes->>'ram_gb')::integer` on phones. Why must types be validated before creating or updating the index?

### Exercise 20 — Generated Column

Create a `devices` table with `details` JSONB and a `brand` stored generated column. Compare this with the application dual-writing `brand` to both a column and JSONB.

### Exercise 21 — JSONPath

Filter `warranty.months >= 24` using `@?`. Explain why GIN does not guarantee efficient indexing for every JSONPath condition.

### Exercise 22 — jsonb_set

Change the color of `PHONE-A` with `jsonb_set`. Why does a small logical change still incur MVCC/TOAST/WAL costs?

### Exercise 23 — Nested Update

Try updating `warranty.months` when the entire `warranty` key does not exist yet. Explain the limitation of `create_if_missing` and how to build the parent object explicitly.

### Exercise 24 — Deleting a Key

Compare `attributes - 'color'` with setting `"color": null`. In a PATCH API, what distinct meanings should these two operations carry?

### Exercise 25 — Concurrent JSON Updates

Two clients read the same document and write back the entire document. Describe the lost update. Propose an atomic `UPDATE` using `jsonb_set` or a version column.

### Exercise 26 — Hot Counter

A `views` field inside JSONB with a GIN index increments 1,000 times per second. Propose an alternative design and explain the write amplification cost.

### Exercise 27 — Inventory

Design `inventory(product_id, warehouse_id, quantity)` with FK/PK/CHECK. Write an `UPDATE` that deducts one unit only when `quantity >= 1`.

### Exercise 28 — Order Snapshot

Explain why `order_items` stores the FK `product_id`, `unit_price`, and `product_snapshot JSONB`. If the catalog changes a product's name or price after purchase, which data is used to render the historical invoice?

### Exercise 29 — Webhook Payload

Design a webhook table storing `provider`, unique `external_event_id`, `event_type`, `received_at`, and JSONB `payload`. Why should business keys not live solely inside JSON?

### Exercise 30 — Raw Signature

A webhook provider signs the raw HTTP body. Why can you not rely on `payload::text` from JSONB to verify the signature of the original bytes?

### Exercise 31 — Schema Versioning

A producer moves `ram_gb` to `memory.ram_gb`. Plan the consumer rollout, backfill, and deprecation of the old version.

### Exercise 32 — Promoting a JSON Key to a Column

`brand` becomes a filter queried thousands of times per second. Describe adding the column, backfilling, syncing with writers, indexing/cutover, and rollback strategy.

### Exercise 33 — Source of Truth

If price exists in both `products.price` and `attributes.price`, how do you prevent inconsistency? Why can `order_items.unit_price` differ from the current product price without being a bug?

### Exercise 34 — EAV

Propose three criteria that make EAV suitable, three risks of a text-based EAV model, and compare it against JSONB and child tables.

### Exercise 35 — BI/Reporting

Write a query computing product count and average price by tenant/category using relational columns. Then write a report for average phone RAM from JSONB, and analyze data quality and casting issues.

### Exercise 36 — Query Performance

Compare `EXPLAIN` output for SKU lookup, brand containment, and numeric RAM range queries. Recommend the appropriate index for each query.

### Exercise 37 — Partial Index

Create a partial index for `brand` on ACTIVE products. Why might a generic prepared statement with `status = $1` fail to use the index as expected?

### Exercise 38 — UNIQUE Nested Key

Create a unique expression index for `external_code` inside JSON per tenant. When the key is missing or JSON null, what are the default UNIQUE semantics?

### Exercise 39 — Data Security

A JSONB `attributes` column contains `supplier_token` and `internal_cost`. Design DTOs and access controls so these keys are never exposed when the API returns a product.

### Exercise 40 — Architecture Synthesis

A multi-tenant platform requires:

- SKU and `external_id` unique within each tenant.
- Tightly constrained price and inventory.
- Thousands of attributes varying by category/tenant.
- Filters by brand, RAM, price, and active status.
- Order storage with name/price/specs at purchase time.
- Receiving webhooks from multiple providers with differing schema versions.
- Inventory updates thousands of times per minute.

Design a **hybrid model**, explaining the placement of typed columns/FKs/JSONB/arrays/tables, indexes, schema validation, migration strategy, concurrency, and audit/snapshots. Also list at least three cases where you would **not** choose JSONB even though the data could be represented as JSON.

## Conclusion

**Relational tables, `jsonb`, and hybrid models are complementary choices.** Data with identity, foreign keys, uniqueness rules, exact numeric types, many-to-many relationships, and high update rates should generally be modeled with typed tables and columns. Flexible metadata, structures varying by category or tenant, external API payloads, and historical snapshots are areas where `jsonb` shines. SQL arrays can suit simple homogeneous element lists, while junction tables are better when elements have relationships and lifecycles of their own.

In PostgreSQL, `jsonb` is **not unconstrained unstructured data**. You must still decide required keys, distinguish SQL NULL, JSON null, and missing keys, guard data types, define schema versions, and handle concurrent updates. Operators such as `->`, `->>`, `?`, `@>`, JSONPath, and `jsonb_set`, together with GIN and expression indexes, offer strong querying capabilities, but they do not replace `PRIMARY KEY`, `FOREIGN KEY`, `CHECK`, or promoting key attributes to typed columns.

The **hybrid** model is strongest when the boundary is clear: **relational core data acts as the source of truth for invariants and JOINs; JSONB holds variable parts or contracted snapshots; hot fields heavily used in BI and search are modeled and indexed appropriately**. Never disguise a duplicate source of truth by storing the same data in multiple places without clear semantics.

Finally, any choice must be validated against the **actual workload**, not merely how convenient it is to `INSERT` a document: examine filtering needs, indexes, planner statistics, row width/TOAST, MVCC/WAL under updates, access control, migrations, payload versioning, and concurrency pressure. A good design lets PostgreSQL enforce what must be right while staying flexible enough to evolve data without turning JSONB into an ungoverned dumping ground.
