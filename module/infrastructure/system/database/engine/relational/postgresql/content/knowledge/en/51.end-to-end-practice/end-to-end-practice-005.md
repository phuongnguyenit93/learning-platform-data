# Comparing Relational and `jsonb` Models on the Same Requirements

PostgreSQL supports both the traditional relational data model and the `jsonb` data type. Both storage approaches can satisfy the same business requirements, yet they differ in how they represent structure, integrity constraints, queries, indexes, updates, and schema changes. To choose effectively, you must compare them on the same dataset, the same queries, and the same workload conditions.

This practice uses a product catalog with two product categories: laptops and phones. Every product shares common fields such as SKU, name, price, currency, and availability status. Each category also has dedicated specifications: laptops have RAM, storage capacity, and screen size; phones have battery capacity and camera resolution. The system needs to search products by category, availability, price, and specifications; update a single specification; and produce summary reports.

We implement the same requirements using two models:

- **Relational model:** known attributes are stored in strongly typed columns with constraints.
- **`jsonb` document model:** common fields remain relational columns, while category-specific specifications are stored inside a JSONB object.

These are two alternative designs for the same use case. The final sections also cover how to combine them when a system has both stable attributes and frequently evolving attributes.

## 1. Defining Requirements Before Designing

A design can only be compared fairly when both approaches must satisfy the exact same data contract and query workload.

### Product Data

Every product has common fields:

| Field | Logical Type | Rules |
|---|---|---|
| `id` | 64-bit integer | Primary key |
| `sku` | String | Required, unique |
| `category` | Category code string | `'laptop'` or `'phone'` in this example |
| `name` | String | Required |
| `price` | Decimal | Non-negative |
| `currency` | Currency code | Required |
| `available` | Boolean | Default `true` |

Category-specific specifications:

| Category | Attribute | Logical Type | Example |
|---|---|---|---|
| Laptop | `ram_gb` | Integer | 16 |
| Laptop | `storage_gb` | Integer | 512 |
| Laptop | `screen_inches` | Decimal | 14.0 |
| Phone | `battery_mah` | Integer | 5000 |
| Phone | `camera_mp` | Decimal | 50.0 |

Operations to support:

1. Insert a product and enforce SKU uniqueness.
2. Validate that specification fields match the product category.
3. Find available laptops priced up to 1,500 USD with at least 16 GB of RAM.
4. Find phones with at least 5,000 mAh battery and at least 50 MP camera.
5. Update the RAM of a laptop.
6. Report product count and average price by category.
7. Extend the model when a new specification appears.

## 2. Option A: The Relational Model

For known attributes with well-defined data types, you can model them as columns. In this small example, a single table holds both common fields and category-specific columns. Constraints ensure each row carries only the specifications appropriate for its category.

### Creating the Table

```sql
CREATE SCHEMA IF NOT EXISTS catalog_rel;

CREATE TABLE catalog_rel.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL
        CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,

    ram_gb integer,
    storage_gb integer,
    screen_inches numeric(5, 2),
    battery_mah integer,
    camera_mp numeric(6, 2),

    CHECK (
        (
            category = 'laptop'
            AND ram_gb IS NOT NULL AND ram_gb BETWEEN 1 AND 512
            AND storage_gb IS NOT NULL AND storage_gb BETWEEN 32 AND 32768
            AND screen_inches IS NOT NULL AND screen_inches BETWEEN 8 AND 30
            AND battery_mah IS NULL
            AND camera_mp IS NULL
        )
        OR
        (
            category = 'phone'
            AND battery_mah IS NOT NULL AND battery_mah BETWEEN 500 AND 30000
            AND camera_mp IS NOT NULL AND camera_mp BETWEEN 1 AND 500
            AND ram_gb IS NULL
            AND storage_gb IS NULL
            AND screen_inches IS NULL
        )
    )
);
```

The final constraint requires laptops to have all three laptop specifications and no phone specifications, and phones to have both phone specifications and no laptop specifications. The `IS NOT NULL` checks are essential because PostgreSQL considers a `CHECK` expression satisfied when it evaluates to `TRUE` or `NULL`. Writing only `ram_gb BETWEEN 1 AND 512` would not forbid `NULL`.

This approach works well when the set of category-specific attributes is relatively small and stable. When there are many categories with dozens or hundreds of distinct columns, the table becomes sparse, constraints grow complex, and every structural change may require a migration. In that case, you can split into subtype tables or use a typed attribute table.

### Inserting Sample Data

```sql
INSERT INTO catalog_rel.product (
    sku, category, name, price, currency, available,
    ram_gb, storage_gb, screen_inches
)
VALUES
    ('LAP-001', 'laptop', 'Notebook A', 1299.00, 'USD', true,
     16, 512, 14.00),
    ('LAP-002', 'laptop', 'Notebook B', 999.00, 'USD', true,
     32, 1024, 16.00);

INSERT INTO catalog_rel.product (
    sku, category, name, price, currency, available,
    battery_mah, camera_mp
)
VALUES
    ('PHN-001', 'phone', 'Phone A', 799.00, 'USD', true,
     5000, 50.00),
    ('PHN-002', 'phone', 'Phone B', 599.00, 'USD', true,
     4500, 48.00);
```

If you insert a laptop missing `ram_gb`, or assign `battery_mah` to a laptop, the constraint rejects the row. PostgreSQL enforces validation inside the database so different clients must all obey the same rules.

## 3. Option B: Specifications Inside `jsonb`

In the document-hybrid approach, common fields remain relational columns to retain familiar keys, types, and indexes. Category-specific specifications live inside an `attributes` object.

### Creating the Table

```sql
CREATE SCHEMA IF NOT EXISTS catalog_doc;

CREATE TABLE catalog_doc.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL
        CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL,

    CHECK (jsonb_typeof(attributes) = 'object'),

    CHECK (
        CASE category
            WHEN 'laptop' THEN
                CASE
                    WHEN jsonb_typeof(attributes -> 'ram_gb') = 'number'
                     AND jsonb_typeof(attributes -> 'storage_gb') = 'number'
                     AND jsonb_typeof(attributes -> 'screen_inches') = 'number'
                    THEN
                        (attributes ->> 'ram_gb')::numeric BETWEEN 1 AND 512
                        AND (attributes ->> 'ram_gb')::numeric =
                            trunc((attributes ->> 'ram_gb')::numeric)
                        AND (attributes ->> 'storage_gb')::numeric BETWEEN 32 AND 32768
                        AND (attributes ->> 'storage_gb')::numeric =
                            trunc((attributes ->> 'storage_gb')::numeric)
                        AND (attributes ->> 'screen_inches')::numeric BETWEEN 8 AND 30
                    ELSE false
                END
            WHEN 'phone' THEN
                CASE
                    WHEN jsonb_typeof(attributes -> 'battery_mah') = 'number'
                     AND jsonb_typeof(attributes -> 'camera_mp') = 'number'
                    THEN
                        (attributes ->> 'battery_mah')::numeric BETWEEN 500 AND 30000
                        AND (attributes ->> 'battery_mah')::numeric =
                            trunc((attributes ->> 'battery_mah')::numeric)
                        AND (attributes ->> 'camera_mp')::numeric BETWEEN 1 AND 500
                    ELSE false
                END
            ELSE false
        END
    )
);
```

The constraint uses `jsonb_typeof` to verify JSON types before casting values to `numeric`. The `CASE` branches avoid attempting casts when a key is missing or holds an incompatible JSON type. In this example, required keys must exist with the proper types; extra keys are still permitted. If the contract forbids unknown keys, add an allowed-keys validation check.

`jsonb` stores data in a parsed binary format. It does not preserve whitespace, key ordering, or duplicate keys from the original JSON text. If you must preserve the exact raw payload for auditing or digital signatures, store the raw text separately as required.

### Inserting Sample Data

```sql
INSERT INTO catalog_doc.product (
    sku, category, name, price, currency, available, attributes
)
VALUES
    (
        'LAP-001', 'laptop', 'Notebook A', 1299.00, 'USD', true,
        '{"ram_gb": 16, "storage_gb": 512, "screen_inches": 14.00}'::jsonb
    ),
    (
        'LAP-002', 'laptop', 'Notebook B', 999.00, 'USD', true,
        '{"ram_gb": 32, "storage_gb": 1024, "screen_inches": 16.00}'::jsonb
    ),
    (
        'PHN-001', 'phone', 'Phone A', 799.00, 'USD', true,
        '{"battery_mah": 5000, "camera_mp": 50.00}'::jsonb
    ),
    (
        'PHN-002', 'phone', 'Phone B', 599.00, 'USD', true,
        '{"battery_mah": 4500, "camera_mp": 48.00}'::jsonb
    );
```

A crucial point is that database constraints still need to be designed. Using JSONB does not automatically guarantee that `ram_gb` is an integer, that `battery_mah` is within valid bounds, or that a laptop always includes all required keys.

## 4. Comparing the Same Laptop Search Query

Requirement: find up to 50 available laptops priced at most 1,500 USD with at least 16 GB of RAM, sorted by ascending price.

### Query on the Relational Model

```sql
SELECT
    id,
    sku,
    name,
    price,
    ram_gb,
    storage_gb,
    screen_inches
FROM catalog_rel.product
WHERE category = 'laptop'
  AND available
  AND currency = 'USD'
  AND price <= 1500
  AND ram_gb >= 16
ORDER BY price, id
LIMIT 50;
```

Predicates operate on strongly typed columns. The planner can leverage column statistics, standard B-tree indexes, and table constraints. The query does not need to parse strings into numbers at runtime.

### Query on the JSONB Model

```sql
SELECT
    id,
    sku,
    name,
    price,
    (attributes ->> 'ram_gb')::integer AS ram_gb,
    (attributes ->> 'storage_gb')::integer AS storage_gb,
    (attributes ->> 'screen_inches')::numeric AS screen_inches
FROM catalog_doc.product
WHERE category = 'laptop'
  AND available
  AND currency = 'USD'
  AND price <= 1500
  AND (attributes ->> 'ram_gb')::integer >= 16
ORDER BY price, id
LIMIT 50;
```

`->>` extracts the JSONB value as text, and the query casts it to an integer for comparison. Constraints ensure RAM values are valid integers within range. If legacy unvalidated data exists or constraints are absent, casting can fail at runtime on non-numeric values.

Both queries return semantically identical data. For a fair comparison, populate both tables with the same product dataset, maintain equivalent indexes, and test under identical parameters and load.

## 5. Comparing the Phone Search Query

Requirement: find available phones with at least a 5,000 mAh battery, at least a 50 MP camera, and price below 1,000 USD.

### Relational Model

```sql
SELECT id, sku, name, price, battery_mah, camera_mp
FROM catalog_rel.product
WHERE category = 'phone'
  AND available
  AND currency = 'USD'
  AND price < 1000
  AND battery_mah >= 5000
  AND camera_mp >= 50
ORDER BY price, id;
```

### JSONB Model

```sql
SELECT
    id,
    sku,
    name,
    price,
    (attributes ->> 'battery_mah')::integer AS battery_mah,
    (attributes ->> 'camera_mp')::numeric AS camera_mp
FROM catalog_doc.product
WHERE category = 'phone'
  AND available
  AND currency = 'USD'
  AND price < 1000
  AND (attributes ->> 'battery_mah')::integer >= 5000
  AND (attributes ->> 'camera_mp')::numeric >= 50
ORDER BY price, id;
```

The syntactic difference is minor, but the relational model expresses data types directly in the schema. JSONB requires the application and database to agree on key names, JSON types, and casting conventions. If a client writes `"5000"` instead of `5000`, the sample constraint rejects it because a JSON string differs from a JSON number.

## 6. Indexes for the Relational Model

Indexes should reflect filter predicates, sort order, and query frequency. For the laptop query, you can test a partial index:

```sql
CREATE INDEX product_rel_laptop_search_idx
ON catalog_rel.product (price, ram_gb, id)
WHERE category = 'laptop'
  AND available
  AND currency = 'USD';
```

For phones:

```sql
CREATE INDEX product_rel_phone_search_idx
ON catalog_rel.product (price, battery_mah, camera_mp, id)
WHERE category = 'phone'
  AND available
  AND currency = 'USD';
```

A partial index stores only rows matching its predicate, reducing index size when queries consistently include those same filters. B-tree column order matters: the leading column governs the effective scan range; when a range condition applies to the leading column, trailing columns primarily assist with filtering or ordering. Compare index column orderings with `EXPLAIN` rather than assuming a single index is optimal for every filter combination.

Standard indexes also serve SKU lookups:

```sql
-- A UNIQUE constraint already exists on sku, so PostgreSQL created a unique index.
SELECT id, name, price
FROM catalog_rel.product
WHERE sku = 'LAP-001';
```

Do not create a redundant index duplicating an existing unique index.

## 7. Indexes for JSONB

JSONB supports multiple indexing strategies. Choose the index type based on your query operators.

### GIN for Containment and Key Search

```sql
CREATE INDEX product_doc_attributes_gin_idx
ON catalog_doc.product
USING gin (attributes jsonb_path_ops);
```

GIN with `jsonb_path_ops` is well suited for `@>` containment queries and certain supported JSONPath queries. For example, checking for products matching an exact key/value set:

```sql
SELECT id, sku, name
FROM catalog_doc.product
WHERE category = 'laptop'
  AND attributes @> '{"ram_gb": 16}'::jsonb;
```

The containment query above performs equality matching; it does not express a numeric inequality like `ram_gb >= 16`. Furthermore, `jsonb_path_ops` does not support every JSONB operator; for instance, the key-exists operator `?` requires a different operator class such as `jsonb_ops`.

### B-Tree Expression Indexes for Range Predicates

GIN is not automatically the best fit for numeric greater-than/less-than comparisons. For minimum RAM queries, you can create an expression index:

```sql
CREATE INDEX product_doc_laptop_ram_price_idx
ON catalog_doc.product (
    ((attributes ->> 'ram_gb')::integer),
    price,
    id
)
WHERE category = 'laptop'
  AND available
  AND currency = 'USD';
```

The index expression must match the query expression. The constraint above ensures RAM is a valid integer before creating the index. If invalid data exists, creating the expression index can fail during casting.

For phone queries, create a corresponding expression index:

```sql
CREATE INDEX product_doc_phone_battery_price_idx
ON catalog_doc.product (
    ((attributes ->> 'battery_mah')::integer),
    price,
    id
)
WHERE category = 'phone'
  AND available
  AND currency = 'USD';
```

If queries frequently filter on camera at the same time, you can consider an additional expression index for `camera_mp`, though each index increases storage and write overhead. Benchmark to confirm real benefit.

### Generated Columns to Simplify Queries

If a JSONB key is queried frequently, you can expose it as a generated column:

```sql
ALTER TABLE catalog_doc.product
ADD COLUMN ram_gb integer
GENERATED ALWAYS AS ((attributes ->> 'ram_gb')::integer) STORED;

CREATE INDEX product_doc_ram_gb_idx
ON catalog_doc.product (ram_gb)
WHERE category = 'laptop';
```

A generated column stores a value derived from JSONB, making queries and indexes cleaner to read. Casting still requires valid source data; in our example, the constraint guarantees it. Stored generated columns consume disk space and must be factored into JSONB update cost. Support and limitations for generated columns depend on your PostgreSQL version; check the documentation for your deployed version.

## 8. Updating a Single Attribute

### Updating in the Relational Model

```sql
UPDATE catalog_rel.product
SET ram_gb = 32
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

Data type and constraints are checked directly. Out-of-range values fail the statement. The column can be referenced cleanly by name in indexes, constraints, views, and reports.

### Updating a Single Key in JSONB

```sql
UPDATE catalog_doc.product
SET attributes = jsonb_set(
    attributes,
    '{ram_gb}',
    to_jsonb(32),
    false
)
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

The final parameter `false` means do not create the key if it does not already exist. If the path is missing, `jsonb_set` returns the original value. Pass `true` when creating a new key is intended. `to_jsonb(32)` creates a JSON number; passing `'32'::text` to `to_jsonb` would produce a JSON string and fail the sample constraint.

### Updating Multiple Keys

```sql
UPDATE catalog_doc.product
SET attributes = attributes ||
    '{"ram_gb": 32, "storage_gb": 1024}'::jsonb
WHERE sku = 'LAP-001'
  AND category = 'laptop';
```

The `||` operator merges two objects at the top level; for colliding keys, the right-hand value replaces the left-hand value. This is not a recursive deep merge for nested objects. For nested updates, use `jsonb_set` with an explicit path or handle merging in the application layer.

### Update Cost

PostgreSQL uses MVCC: an `UPDATE` produces a new tuple version. Updating one key inside JSONB does not overwrite just a few bytes of that key in place. The JSONB value may be reconstructed, and any GIN or expression indexes covering JSONB must also be updated. For large documents and frequent updates, measure WAL generation, bloat, and index maintenance overhead.

In the relational model, updating a non-indexed column can benefit from HOT (Heap-Only Tuple) updates when PostgreSQL conditions are met—such as leaving all indexed columns unchanged and having free space on the heap page. HOT is not guaranteed; it depends on table layout, indexes, and `fillfactor`. JSONB updates can also qualify for HOT if indexed columns/expressions do not change and other conditions hold, but updating a key covered by a GIN or expression index generally triggers index updates.

## 9. Constraints and Data Integrity

### Relational Model

The relational model offers explicit primitives:

- `NOT NULL` for mandatory fields.
- `CHECK` for value ranges and invariants.
- `UNIQUE` for SKUs or business keys.
- `PRIMARY KEY` for row identity.
- `FOREIGN KEY` for cross-table relationships.
- Data types like `integer`, `numeric`, `date`, and `timestamptz` to reject malformed values.

Constraints are enforced by the database across all clients. When data is normalized across tables, foreign keys prevent orphaned records and support appropriate `ON DELETE`/`ON UPDATE` actions.

### JSONB Model

Common fields such as `id`, `sku`, and `category` can still use relational types and constraints. For keys inside JSONB, define:

- Whether each key is required.
- Accepted JSON types: number, string, boolean, array, object, or null.
- Allowed value bounds.
- Whether unknown keys are allowed.
- Whether a key must be unique or reference another table.
- How legacy documents are migrated when a key is renamed.

`CHECK` constraints can enforce these rules, though expressions become more verbose and may repeat casting logic. JSONB does not provide native foreign keys from a nested JSON element to another table. If an attribute requires referential integrity, promote it to a relational column or separate table.

### Checking Missing Keys, JSON `null`, and SQL `NULL`

JSONB distinguishes an object missing a key from an object containing a key set to JSON `null`. You can inspect this with:

```sql
SELECT
    attributes ? 'ram_gb' AS key_exists,
    jsonb_typeof(attributes -> 'ram_gb') AS json_value_type,
    attributes ->> 'ram_gb' AS text_value
FROM catalog_doc.product
WHERE category = 'laptop';
```

`?` checks whether a top-level key exists. If the key is absent, extraction operators typically return SQL `NULL`; if the key holds JSON `null`, `jsonb_typeof` returns the string `'null'`. Define explicit semantics in APIs and ETL pipelines: whether a missing key means "unknown", "not applicable", or "default"; what JSON `null` signifies; and whether SQL `NULL` on the entire `attributes` column is permitted.

## 10. Reporting and Aggregations

Requirement: count products and calculate average price by category.

### Relational

```sql
SELECT
    category,
    count(*) AS product_count,
    avg(price) AS average_price
FROM catalog_rel.product
GROUP BY category
ORDER BY category;
```

### JSONB

```sql
SELECT
    category,
    count(*) AS product_count,
    avg(price) AS average_price
FROM catalog_doc.product
GROUP BY category
ORDER BY category;
```

Because common fields stay as relational columns in both approaches, this aggregation query is virtually identical. This is a practical reason not to push everything into JSONB: stable attributes heavily used for joins, filters, grouping, and sorting should remain ordinary columns.

To compute average laptop RAM, the relational query uses `avg(ram_gb)`, while JSONB must extract and cast:

```sql
-- Relational
SELECT avg(ram_gb)
FROM catalog_rel.product
WHERE category = 'laptop';

-- JSONB
SELECT avg((attributes ->> 'ram_gb')::numeric)
FROM catalog_doc.product
WHERE category = 'laptop';
```

If these reports run frequently, create views, materialized views, generated columns, or targeted indexes. Do not copy complex JSONB extraction expressions across dozens of dashboards without a shared data layer.

## 11. Schema Evolution When New Specifications Arrive

Suppose laptops need a new `weight_kg` attribute.

### Relational

You can add a column:

```sql
ALTER TABLE catalog_rel.product
ADD COLUMN weight_kg numeric(5, 2);
```

Then update the application, backfill legacy rows, and add appropriate constraints once historical data is clean. For large tables, plan locks, defaults, and constraint validation according to your PostgreSQL version. Adding a column can impact consumers using `SELECT *` or positional column mapping.

### JSONB

You can add the key to new or updated documents without adding a table column:

```sql
UPDATE catalog_doc.product
SET attributes = jsonb_set(
    attributes,
    '{weight_kg}',
    to_jsonb(1.45),
    true
)
WHERE category = 'laptop'
  AND sku = 'LAP-001';
```

No DDL is needed merely to store the new key, yet applications must still align on key name, type, unit, and semantics. If queries filter or sort by `weight_kg`, evaluate adding an expression index or generated column. If the key becomes mandatory, update constraints and backfill legacy documents.

### Versioning JSON Contracts

For documents whose structure evolves over time, store a `schema_version` inside the document or in a dedicated column. When reading, the application knows which version-specific transformation applies. Never silently change the meaning of an existing key under the same name while older consumers are still reading it.

## 12. Splitting Subtype Tables Instead of Sparse Columns

If the number of product categories grows and each category has many stable fields, you can split into subtype tables:

```sql
CREATE TABLE catalog_rel.product_base (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category text NOT NULL CHECK (category IN ('laptop', 'phone')),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    UNIQUE (id, category)
);

CREATE TABLE catalog_rel.laptop_spec (
    product_id bigint PRIMARY KEY,
    category text NOT NULL DEFAULT 'laptop' CHECK (category = 'laptop'),
    ram_gb integer NOT NULL CHECK (ram_gb BETWEEN 1 AND 512),
    storage_gb integer NOT NULL CHECK (storage_gb BETWEEN 32 AND 32768),
    screen_inches numeric(5, 2) NOT NULL CHECK (screen_inches BETWEEN 8 AND 30),
    FOREIGN KEY (product_id, category)
        REFERENCES catalog_rel.product_base (id, category)
        ON DELETE CASCADE
);
```

The composite foreign key ensures a `laptop_spec` row can only reference a product with category `'laptop'`. By itself it does not guarantee every laptop product has a `laptop_spec` row; if that requirement must be enforced in the database, use an appropriate constraint trigger or controlled transactional writes. Subtype tables give each category a clean schema, though cross-category queries require joining subtypes or building a unified view.

## 13. Converting Between Relational Columns and JSONB

### Building JSON from Relational Columns

PostgreSQL can construct JSONB directly from column values:

```sql
SELECT jsonb_build_object(
    'sku', sku,
    'name', name,
    'ram_gb', ram_gb,
    'storage_gb', storage_gb,
    'screen_inches', screen_inches
) AS product_document
FROM catalog_rel.product
WHERE category = 'laptop';
```

This generates API payloads or exports on the fly. You do not need to duplicate payloads on disk if they can be built from relational columns when needed.

### Extracting JSONB into Columns

```sql
SELECT
    sku,
    attributes ->> 'ram_gb' AS ram_gb_text,
    (attributes ->> 'ram_gb')::integer AS ram_gb,
    (attributes ->> 'screen_inches')::numeric AS screen_inches
FROM catalog_doc.product
WHERE category = 'laptop';
```

When migrating data, define how to handle missing keys, JSON `null`s, wrong types, out-of-range values, and older schema versions. Do not run bulk casts before auditing the count of malformed rows.

## 14. Fair Performance Comparison

You cannot conclude whether relational or JSONB is faster solely from SQL line count or a single sample query. You must test on identical data and identical runtime conditions.

### Preparing Identical Datasets

Create one canonical source dataset, then load the exact same records into `catalog_rel.product` and `catalog_doc.product`. Verify:

- Identical product counts.
- Identical SKUs and business keys.
- Identical categories, prices, currencies, and availability flags.
- Identical specification values and units.
- Identical proportions of missing or not-applicable attributes.
- Identical hot/cold skew if tenants or categories are uneven.

If data is randomly generated independently for the two tables, distributions may diverge and invalidate the benchmark.

### Updating Statistics

After loading data and creating indexes:

```sql
ANALYZE catalog_rel.product;
ANALYZE catalog_doc.product;
```

If the dataset is large and underwent heavy updates or deletes, vacuum appropriately before measuring. Never alter `work_mem`, `shared_buffers`, cache warmth, or concurrency levels between benchmark runs.

### Measuring Plans and Buffers

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, sku, price
FROM catalog_rel.product
WHERE category = 'laptop'
  AND available
  AND price <= 1500
  AND ram_gb >= 16
ORDER BY price, id
LIMIT 50;
```

Run the equivalent query on JSONB:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT id, sku, price
FROM catalog_doc.product
WHERE category = 'laptop'
  AND available
  AND price <= 1500
  AND (attributes ->> 'ram_gb')::integer >= 16
ORDER BY price, id
LIMIT 50;
```

Compare:

- Estimated rows vs. actual rows.
- Scan types and indexes chosen.
- Whether sorting occurs and whether sorts spill to disk.
- Shared buffer hits/reads and temp blocks.
- Planning time and execution time.
- Heap/index sizes and update maintenance overhead.

`EXPLAIN ANALYZE` executes the query for real. Run it in benchmark environments and avoid running destructive DML in production merely to inspect plans.

### Measuring Multiple Workloads

| Workload | What to Compare |
|---|---|
| Insert new rows | Throughput, WAL volume, constraint cost, index maintenance |
| Update common field | HOT updates, index impact, and locking |
| Update single specification | Dedicated column vs. JSONB mutation and affected indexes |
| Equality filter | B-tree, GIN containment, and selectivity |
| Range filter | Column B-tree vs. expression index |
| Join with category/brand | Key join support and cardinality |
| Aggregation | CPU, casting cost, scan type, memory, and duration |
| Full document fetch | Payload size, TOAST access, and bytes transferred |
| Concurrent workload | p95/p99 latency, throughput, connections, and I/O |

Run multiple iterations with warm-up, capture percentiles, and record server configuration. A single fastest run is not reliable evidence.

## 15. Evaluating Storage Footprint

JSONB is neither universally smaller nor universally larger than a relational layout. Size depends on key count, key name lengths, value types, TOAST behavior, repetition, indexes, and table layout. Relational tables can waste space on sparse columns (though NULL bitmaps are compact); JSONB repeats key names across every row and incurs structural overhead.

Measure actual sizes:

```sql
SELECT
    'relational' AS model,
    pg_size_pretty(pg_relation_size('catalog_rel.product')) AS heap,
    pg_size_pretty(pg_indexes_size('catalog_rel.product')) AS indexes,
    pg_size_pretty(pg_total_relation_size('catalog_rel.product')) AS total
UNION ALL
SELECT
    'jsonb' AS model,
    pg_size_pretty(pg_relation_size('catalog_doc.product')) AS heap,
    pg_size_pretty(pg_indexes_size('catalog_doc.product')) AS indexes,
    pg_size_pretty(pg_total_relation_size('catalog_doc.product')) AS total;
```

Measure after data and indexes are fully populated, at the same vacuum state and exact same row count. If the JSONB table stores large objects, also evaluate TOAST impact and WAL amplification when updating a single key.

## 16. Consistency and Inter-Entity Relationships

The relational model excels when products reference categories, brands, suppliers, warehouses, or price books. Foreign keys enforce valid references, and transactions update multiple tables atomically.

JSONB fits a group of attributes belonging to the same aggregate that are read and written together and do not require independent foreign keys per key. If you embed category IDs or supplier IDs inside JSONB, the database does not automatically enforce foreign keys on those values. Keep relational columns as the source of truth and duplicate values inside JSONB only with a clear justification.

### Category Relationship Example

```sql
CREATE TABLE catalog_rel.category (
    category_code text PRIMARY KEY,
    category_name text NOT NULL UNIQUE
);

ALTER TABLE catalog_rel.product
ADD CONSTRAINT product_category_fk
FOREIGN KEY (category)
REFERENCES catalog_rel.category (category_code);
```

Even when using JSONB for `attributes`, you can keep `category` as a relational column and attach the foreign key above. This demonstrates that the two models compose cleanly; using JSONB does not force the entire record into a document.

## 17. Handling Nulls, Defaults, and Missing Data

In the relational model, `NULL` follows clear SQL semantics. `NOT NULL`, `DEFAULT`, `CHECK`, and three-valued logic govern behavior. Always distinguish whether `NULL` means unknown, not applicable, or not yet entered.

In JSONB, multiple states exist:

- The `attributes` column itself is SQL `NULL` (if nullable).
- The object omits the `ram_gb` key.
- The object includes `ram_gb` with JSON `null`.
- The object includes the key with the expected type, e.g. number `16`.
- The object includes the key with the wrong type, e.g. string `"16"`.

APIs must explicitly define semantics for every state. In particular, never write `COALESCE(attributes->>'x', '0')` unless a missing value truly means zero. A silent wrong default corrupts reports without raising errors.

## 18. Security and Data Governance

Do not treat JSONB as an unchecked dumping ground for arbitrary payloads. JSONB resides inside the database and is subject to table permissions, backups, replication, and logs just like any column. If payloads contain sensitive data, classify and restrict read access.

Key principles:

- Never store secrets, passwords, or access tokens inside product attributes.
- Use least-privilege roles and views to limit exposed fields.
- Validate keys and types at the database or application boundary.
- Avoid logging full JSONB payloads if they may contain personal or internal data.
- Bound document sizes to guard against anomalous payloads.
- Apply migrations and versioning processes to JSON contracts.

## 19. When to Choose the Relational Model

The relational model is usually the right fit when:

- Attributes have stable structure and are queried frequently.
- You need filtering, sorting, joining, and aggregating across multiple attributes.
- You need strict data types and database-enforced constraints.
- Attributes participate in primary keys, foreign keys, or uniqueness rules.
- Data acts as a shared contract across multiple applications.
- Reports require accurate column-level statistics.
- Schema changes must be governed by explicit migrations.

Relational tables give the planner per-column statistics and support standard index structures directly. In return, structural changes typically require migrations and coordination across consumers.

## 20. When to Choose JSONB

JSONB is usually a good fit when:

- Attributes vary frequently across object types.
- Most of the payload is read and written together as a single document.
- Many keys are rarely queried individually.
- The application needs nested structures or document-style arrays.
- Schemas are managed as versioned application contracts.
- You accept the responsibility of writing explicit constraints and indexes for hot keys.

JSONB lets you add new keys without altering table columns for every change. However, once a key becomes a primary filter, join key, or core reporting metric, it will likely need an expression index, generated column, or promotion to a relational column.

## 21. Hybrid Relational and JSONB Model

In many production systems, the most practical design keeps stable fields in relational columns and uses JSONB strictly for extensible attributes.

Example:

```sql
CREATE TABLE catalog.product (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    category_id bigint NOT NULL REFERENCES catalog.category(id),
    name text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    currency char(3) NOT NULL,
    available boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(attributes) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Common columns receive standard constraints, foreign keys, and indexes. `attributes` holds less stable extension specs. Frequently queried keys can get expression indexes or be promoted to generated or physical columns.

Deciding to promote a key from JSONB to a column should weigh query frequency, constraint needs, joins, reporting, contract stability, and migration cost. Do not promote every key just because one dashboard queried it once; conversely, do not leave a critical key buried in a document forever once it becomes core to the domain model.

## 22. Migration Path Between the Two Models

When migrating from JSONB to relational columns—or vice versa—use a multi-step rollout to minimize risk.

### From JSONB to Columns

1. Identify the key to normalize, its data type, and null/default rules.
2. Add the new column as nullable or with an appropriate default.
3. Update the application to dual-write or prioritize the new column in phases.
4. Backfill legacy JSONB data in batches with explicit cast error handling.
5. Reconcile column values against JSONB values by product key.
6. Create indexes and constraints once data is validated.
7. Switch read queries to the new column.
8. Stop writing the old key, then drop the key or retire the JSONB usage.

### From Columns to JSONB

1. Define the document contract and schema version.
2. Populate the JSONB key derived from the existing column.
3. Run time-bounded dual-read/dual-write if rolling deployments require it.
4. Reconcile data and audit all consumers.
5. Switch queries to JSONB and add required indexes.
6. Drop the old column only after zero dependent consumers remain.

In both directions, designate a single source of truth during dual-write to prevent drift between copies. Emit metrics tracking missing keys, cast errors, and value mismatches.

## 23. Side-by-Side Comparison on the Same Requirements

| Criterion | Relational Model | JSONB Model |
|---|---|---|
| Common fields | Typed columns | Can remain relational columns |
| Category-specific attributes | Columns / subtype tables / attribute tables | Keys inside JSONB object |
| Data types | Declared directly | JSON types must be validated/cast |
| Required / range rules | `NOT NULL`, `CHECK` | `CHECK` on `jsonb_typeof` and extracted values |
| Uniqueness | `UNIQUE` / index | Usually needs expression index or separate column |
| Foreign keys | Directly supported | No direct FK for keys inside document |
| Equality search | B-tree, partial index | GIN containment or expression index |
| Numeric range | Column B-tree | Expression B-tree or generated column usually preferred |
| Joins | Strongly typed key columns | Requires extraction/casting; best kept as columns |
| Adding attributes | Schema migration | Add key, though versioning/validation still required |
| Single-field update | Column update | `jsonb_set`, still writes new tuple under MVCC |
| Planner statistics | Per-column statistics | JSONB stats plus expression/index stats depending on query |
| Reading full payload | May require joining multiple tables | Can fetch a single document |
| Multi-dimensional reporting | Convenient with relational columns | Requires key extraction or modeling layer |
| Data contract | Explicit database schema | Requires explicit conventions and validation |

## 24. End-to-End Comparison Practice Workflow

To make a grounded decision for a specific system, run a reproducible benchmark:

1. **Lock the use case:** list read queries, write operations, reports, and consistency requirements.
2. **Create both schemas:** `catalog_rel` and `catalog_doc` with identical common fields and specifications.
3. **Generate one canonical fixture:** identical SKUs, prices, categories, attributes, null rates, and value distributions.
4. **Load both models:** record row counts and confirm equivalent business results.
5. **Create matching indexes:** unique SKU, partial B-trees, and necessary GIN/expression indexes.
6. **Run `ANALYZE`:** refresh planner statistics on both tables.
7. **Benchmark equality and range queries:** common values, rare values, and multi-predicate filters.
8. **Benchmark updates and inserts:** identical row counts, transaction sizes, and concurrency.
9. **Benchmark reports:** group-by, aggregates, joins, and specification filters.
10. **Measure storage:** heap, index, TOAST, and generated WAL.
11. **Evaluate operations:** migrations, validation, backup/restore, schema evolution, and access control.
12. **Document the decision:** state which workloads are prioritized, what trade-offs are accepted, and why.

Do not pick an option solely because one query had the lowest execution time. Weigh total cost: write amplification, index maintenance, storage footprint, constraint complexity, application ergonomics, and consumer coordination.

## 25. Practice Exercises

### Exercise 1: Build Both Models

Create both tables following the examples in this lesson. Load at least 100,000 products into each model from the same fixture. Reconcile row counts, SKUs, and specification values.

### Exercise 2: Test Invalid Data

Attempt to insert a laptop missing RAM, a phone containing `ram_gb`, JSONB using a string instead of a number, and a negative price. Record which constraint rejects each case.

### Exercise 3: Compare Range Queries

Run the query for laptops with at least 16 GB of RAM priced under 1,500 USD on both models. Use `EXPLAIN (ANALYZE, BUFFERS)` and compare plans before and after adding indexes.

### Exercise 4: Compare GIN vs. Expression B-Tree

Create a `jsonb_path_ops` GIN index, then create an expression B-tree index on RAM. Compare containment equality against `ram_gb >= 16`. Explain why the two index types serve different query patterns.

### Exercise 5: Measure Single-Attribute Updates

Run 10,000 RAM updates on both the relational and JSONB models. Measure duration, WAL volume, index size, and bloat after the workload. Repeat with a GIN index present on JSONB.

### Exercise 6: Add a New Attribute

Add `weight_kg` for laptops. Implement it via a relational column and via a JSONB key. Describe the migration, backfill, validation, and how older consumers continue functioning.

### Exercise 7: Distinguish Missing Keys vs. JSON `null`

Create three documents: missing `ram_gb`, `ram_gb: null`, and `ram_gb: 16`. Use `?`, `->`, and `jsonb_typeof` to distinguish the results.

### Exercise 8: Build a Hybrid Model

Keep SKU, category, price, currency, and availability as columns; move several rarely used specifications into JSONB. Create an expression index for one frequently filtered key. Evaluate the balance between flexibility and query ergonomics.

## 26. Review Questions

**1. Why must both models be compared on the exact same fixture?**

To eliminate bias from differing row counts, data distributions, and values. Only when data and workloads are identical can query and storage costs be compared fairly.

**2. Does JSONB automatically validate key data types?**

Not according to your application contract. JSONB enforces basic JSON types, but ensuring RAM is an integer within a specific range requires database constraints or application validation.

**3. When is GIN appropriate for JSONB?**

When queries use containment or other JSONB operators supported by the chosen operator class. Numeric ranges typically require expression B-trees or generated columns for effective indexing.

**4. Why must an expression index match the query expression?**

The planner must match the query predicate to the indexed expression. Differences in casts, functions, or syntax can prevent the index from being used as expected.

**5. Does updating one JSONB key rewrite only that single key in place?**

No. PostgreSQL uses MVCC, and updating a JSONB value can create a new tuple version, generate WAL, and update associated indexes.

**6. Does JSONB support foreign keys on keys inside an object?**

Not directly. If a key requires referential integrity, promote it to a relational column or separate table.

**7. When should a JSONB key be promoted to a column?**

When the key is stable, frequently used in filters/joins/grouping/sorting, requires strong constraints, or forms a core part of the data contract.

**8. Can relational columns and JSONB coexist in the same table?**

Yes. Keeping stable fields in relational columns and using JSONB for extensible attributes is a common hybrid pattern.

**9. Why distinguish a missing key from JSON `null`?**

The two states can carry different business meanings. Without explicit definitions, defaults or reports may misinterpret the data.

**10. Which metrics should be compared besides execution time?**

Throughput, p95/p99 latency, buffer hits/reads, I/O, WAL, index/heap size, update/insert cost, locking, migration duration, and operational complexity.

## 27. PostgreSQL Reference Documentation

- PostgreSQL Documentation — JSON Types: https://www.postgresql.org/docs/current/datatype-json.html
- PostgreSQL Documentation — JSON Functions and Operators: https://www.postgresql.org/docs/current/functions-json.html
- PostgreSQL Documentation — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL Documentation — Index Types: https://www.postgresql.org/docs/current/indexes-types.html
- PostgreSQL Documentation — GIN Indexes: https://www.postgresql.org/docs/current/gin.html
- PostgreSQL Documentation — Indexes on Expressions: https://www.postgresql.org/docs/current/indexes-expressional.html
- PostgreSQL Documentation — Generated Columns: https://www.postgresql.org/docs/current/ddl-generated-columns.html
- PostgreSQL Documentation — `EXPLAIN`: https://www.postgresql.org/docs/current/sql-explain.html
- PostgreSQL Documentation — Routine Vacuuming: https://www.postgresql.org/docs/current/routine-vacuuming.html
- PostgreSQL Documentation — `INSERT ... ON CONFLICT`: https://www.postgresql.org/docs/current/sql-insert.html

Comparing relational and JSONB models must be grounded in your actual query, update, and data integrity requirements. Relational columns provide direct data types, constraints, foreign keys, and planner statistics; JSONB fits flexible attributes while requiring explicit validation, casting, and query-specific indexing. For many systems, a hybrid model keeping core data in relational columns and using JSONB for extensions strikes the best balance, provided data contracts and migration workflows are clearly governed.
