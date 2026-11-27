# GoogleSQL, Nested Fields, and Repeated Fields in BigQuery

A retail system creates orders on **Cloud Run**, processes events via **Pub/Sub**, and stores transactional data in **Cloud SQL/Spanner**. The analytics team wants to bring order data into **BigQuery** to compute revenue by product and region. Each order belongs to one customer, yet can contain **multiple line items**. Splitting everything into separate tables to `JOIN` in every report can make queries expensive to combine; completely flattening the data repeats order-level fields multiple times.

**GoogleSQL** lets you model parent–child relationships directly within a single BigQuery row using **`STRUCT`** (nested fields) and **`ARRAY`** (repeated fields). Learners need to understand **how to define schemas, access fields, unnest arrays, filter, aggregate**, and avoid pitfalls such as row multiplication after `UNNEST`.

This lesson belongs to the **BigQuery** chapter, **CLOUD_PROVIDERS_GCP** module. It connects storage, IAM, Google Cloud networking, Cloud Run/GKE, and pipelines with data governance, cost control, and reliability, while keeping the focus on **GoogleSQL, nested fields, and repeated fields**. Examples use synthetic data and contain no real customer information.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `STRUCT`/`RECORD`, `ARRAY`/`REPEATED`, and the modes `NULLABLE`, `REQUIRED`, and `REPEATED`.
2. Write GoogleSQL using dot notation to access fields, safely index array elements, and use `UNNEST`.
3. Understand when `CROSS JOIN UNNEST` **drops parent rows**, whereas `LEFT JOIN UNNEST` preserves parent rows with empty arrays.
4. Compute `COUNT`, `SUM`, and ratios accurately after unnesting arrays, avoiding row multiplication across multiple repeated fields.
5. Use `EXISTS`, `ARRAY(...)`, `ARRAY_AGG`, and `SELECT AS STRUCT` to filter and reconstruct nested data.
6. Choose appropriate denormalized schemas, load JSON from Cloud Storage, test schema evolution, and optimize BigQuery costs.
7. Handle `NULL`s, empty arrays, multi-level arrays, and protect production data and budgets.

## 2. BigQuery Data Types and Modes

### 2.1. Three Representation Forms

| Data | GoogleSQL Type | BigQuery Table Schema | Example |
| --- | --- | --- | --- |
| Single value | `STRING`, `INT64`, `NUMERIC`, `DATE`... | Scalar column with mode `NULLABLE` or `REQUIRED`. | `order_id STRING` |
| One child object | `STRUCT<customer_id STRING, city STRING>` | `RECORD` with child fields. | `customer.city` |
| Multiple values | `ARRAY<STRING>` | `REPEATED` column. | `tags = ['vip','mobile']` |
| Multiple child objects | `ARRAY<STRUCT<sku STRING, qty INT64>>` | `RECORD` with mode `REPEATED`. | An order's `items` |
| Array inside an object | `STRUCT<labels ARRAY<STRING>>` | A `RECORD` containing a `REPEATED` child field. | `customer.tags` |

**`RECORD` is the schema/API representation**, while **`STRUCT` is the GoogleSQL type**; similarly, **`REPEATED` in the schema is queried as `ARRAY` in SQL**. A `NULLABLE` field permits `NULL`, `REQUIRED` does not, and `REPEATED` holds 0 or more elements. Never assume a `RECORD` is an array unless its mode is `REPEATED`.

Diagram of a single order row:

~~~mermaid
flowchart TD
    O["Order: order_id, order_date"] --> C["customer STRUCT"]
    C --> CID["customer_id"]
    C --> CITY["city"]
    O --> I["items ARRAY of STRUCT"]
    I --> SKU["sku"]
    I --> Q["qty"]
    I --> PRICE["unit_price"]
    O --> TAG["tags ARRAY of STRING"]
~~~

Design limits: BigQuery allows **up to 15 levels of nested `RECORD`s**; it **does not support an `ARRAY` directly containing another `ARRAY`**. To represent an array of arrays, wrap the inner array in a `STRUCT`, such as `ARRAY<STRUCT<values ARRAY<INT64>>>`. You do not need to push near the maximum depth: deeply nested schemas make consumers and migrations harder.

### 2.2. `STRUCT` with Named Fields and `ARRAY` with Elements

~~~sql
-- Run directly in the BigQuery SQL editor; no dataset required.
SELECT
  STRUCT('C-01' AS customer_id, 'HCM' AS city) AS customer,
  ['web', 'mobile'] AS channels,
  [
    STRUCT('SKU-A' AS sku, 2 AS qty, NUMERIC '120000' AS unit_price),
    STRUCT('SKU-B' AS sku, 1 AS qty, NUMERIC '50000' AS unit_price)
  ] AS items;
~~~

Here `customer` is a **single** `STRUCT` value; `channels` is `ARRAY<STRING>`; `items` is `ARRAY<STRUCT<...>>`. SQL supports `STRUCT(...)` with named fields rather than JSON strings. `NUMERIC` is better suited for most monetary calculations than `FLOAT64` because it avoids unnecessary binary rounding errors; always confirm currency units and rounding rules with business requirements.

## 3. Self-Contained Practice Dataset

Use the **BigQuery multi-statement SQL script** below to create a temporary table within the same job/script. Subsequent queries assume this block has already run in the **same script/session**. If running queries in separate jobs, recreate the temp table or point to an approved real table.

~~~sql
-- Job-scoped WRITE: TEMP table creates no production table.
CREATE TEMP TABLE demo_orders AS
SELECT
  'O-1001' AS order_id,
  DATE '2026-11-18' AS order_date,
  STRUCT('C-01' AS customer_id, 'HCM' AS city) AS customer,
  [
    STRUCT('SKU-A' AS sku, 2 AS qty, NUMERIC '120000' AS unit_price),
    STRUCT('SKU-B' AS sku, 1 AS qty, NUMERIC '50000' AS unit_price)
  ] AS items,
  ['web', 'vip'] AS tags
UNION ALL
SELECT
  'O-1002',
  DATE '2026-11-19',
  STRUCT('C-02' AS customer_id, 'Da Nang' AS city),
  [STRUCT('SKU-A' AS sku, 1 AS qty, NUMERIC '120000' AS unit_price)],
  ['mobile']
UNION ALL
SELECT
  'O-1003',
  DATE '2026-11-19',
  STRUCT('C-03' AS customer_id, 'HCM' AS city),
  ARRAY<STRUCT<sku STRING, qty INT64, unit_price NUMERIC>>[],
  ARRAY<STRING>[];

-- READ: 3 orders, 3 line items total; order O-1003 has empty items.
SELECT order_id, customer.city AS city,
       ARRAY_LENGTH(items) AS item_count
FROM demo_orders
ORDER BY order_id;
~~~

Expected output:

| order_id | city | item_count |
| --- | --- | ---: |
| O-1001 | HCM | 2 |
| O-1002 | Da Nang | 1 |
| O-1003 | HCM | 0 |

All numbers and values are **synthetic**. The example includes an order with an empty `items` array so learners observe common flattening pitfalls. In real tables, `order_id` uniqueness depends on data rules and upstream deduplication; BigQuery does not automatically turn this example into an enforced primary key constraint.

## 4. Accessing Nested Fields and Repeated Elements

### 4.1. Dot Notation

When a field is **not repeated**, access child fields with dot notation:

~~~sql
SELECT
  order_id,
  customer.customer_id AS customer_id,
  customer.city AS city,
  ARRAY_LENGTH(tags) AS tag_count
FROM demo_orders
ORDER BY order_id;
~~~

**Do not write `items.sku` to read all SKUs of a repeated record as a scalar field.** Because `items` is an array, use `UNNEST(items)` or an array subquery.

### 4.2. Zero-Based Indexing and Safe Access

~~~sql
SELECT
  order_id,
  items[SAFE_OFFSET(0)].sku AS first_sku,
  tags[SAFE_ORDINAL(1)] AS first_tag,
  ARRAY_LENGTH(items) AS item_count
FROM demo_orders
ORDER BY order_id;
~~~

- `OFFSET(0)` accesses the first element using **0-based** indexing; `ORDINAL(1)` uses **1-based** indexing.
- `SAFE_OFFSET` and `SAFE_ORDINAL` return `NULL` when an **index is out of bounds**; plain `OFFSET`/`ORDINAL` raise an error.
- `ARRAY_LENGTH([]) = 0`, whereas `ARRAY_LENGTH(NULL)` returns `NULL`.
- Array order can carry business meaning, yet **`UNNEST` does not guarantee preserving that order** unless you include the offset and sort with `ORDER BY`.

Never use `items[OFFSET(0)]` across all rows when some orders may have no items.

## 5. `UNNEST`: Expanding One Order into Multiple Line-Item Rows

### 5.1. `CROSS JOIN` or `INNER JOIN UNNEST`

~~~sql
SELECT
  o.order_id,
  i.sku,
  i.qty,
  i.unit_price
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
ORDER BY o.order_id, i.sku;
~~~

Result:

| order_id | sku | qty | unit_price |
| --- | --- | ---: | ---: |
| O-1001 | SKU-A | 2 | 120000 |
| O-1001 | SKU-B | 1 | 50000 |
| O-1002 | SKU-A | 1 | 120000 |

`UNNEST` turns each item into a row **and repeats the parent order's fields on every child row**. With a correlated `CROSS JOIN`/`INNER JOIN`, `items=[]` or `items IS NULL` yields **0 child rows**, so **O-1003 disappears**. This is standard join behavior, not O-1003 being deleted from the table.

### 5.2. `LEFT JOIN UNNEST`: Keeping Orders Without Items

~~~sql
SELECT
  o.order_id,
  i.sku,
  i.qty
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
ORDER BY o.order_id, i.sku;
~~~

The output now includes **O-1003 with `sku=NULL` and `qty=NULL`**. For an empty or `NULL` array, an outer join preserves the parent row as one row with `NULL`s for the unnested columns. This behavior is critical when reporting on **all orders**, not just orders with at least one item.

### 5.3. Why Is `COUNT(*)` Easy to Get Wrong?

To count accurately after a `LEFT JOIN`, **do not** `GROUP BY` an `ARRAY` field directly (GoogleSQL does not allow grouping by `ARRAY`). Use `MAX(ARRAY_LENGTH(...))` grouped by a unique order key:

~~~sql
SELECT
  o.order_id,
  COUNT(*) AS rows_after_left_join,
  COUNT(i.sku) AS sku_count,
  MAX(ARRAY_LENGTH(o.items)) AS items_in_order
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

| order_id | rows_after_left_join | sku_count | items_in_order |
| --- | ---: | ---: | ---: |
| O-1001 | 2 | 2 | 2 |
| O-1002 | 1 | 1 | 1 |
| O-1003 | **1** | **0** | **0** |

`COUNT(*)` counts the `NULL` row introduced by `LEFT JOIN`. `COUNT(i.sku)` works in this example **because `sku` on every valid item is non-NULL**; in real data where `sku` might be `NULL`, count by a valid item definition or use `ARRAY_LENGTH` to measure element count. For total **orders**, count before `UNNEST` or use `COUNT(DISTINCT order_id)` when IDs are guaranteed unique and joins are present.

### 5.4. Preserving Element Order with `WITH OFFSET`

~~~sql
SELECT
  o.order_id, pos,
  i.sku
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i WITH OFFSET AS pos
ORDER BY o.order_id, pos;
~~~

`pos` starts at 0. When reconstructing an array in its original order, carry the offset through processing and sort explicitly; **never rely on implicit SQL output ordering**.

## 6. Filtering Arrays Without Multiplying Rows

### 6.1. `EXISTS` with `UNNEST`

Question: **Which orders contain at least one SKU-B?** You do not need to `CROSS JOIN` and then `DISTINCT`:

~~~sql
SELECT o.order_id
FROM demo_orders AS o
WHERE EXISTS (
  SELECT 1
  FROM UNNEST(o.items) AS i
  WHERE i.sku = 'SKU-B'
);
~~~

Result is only **O-1001**. `EXISTS` tests whether any element matches; when the array is empty, the subquery returns zero rows so the predicate is false. This avoids multiplying parent rows when the goal is purely an **existence check**.

For a scalar `ARRAY`:

~~~sql
-- Orders with the 'vip' tag.
SELECT order_id
FROM demo_orders
WHERE 'vip' IN UNNEST(tags);
~~~

`IN UNNEST(tags)` works well for membership tests. Be careful with **NULL elements** and `NOT IN`: SQL three-valued logic can evaluate to `NULL` instead of `TRUE`/`FALSE` as expected. To exclude values not present in an array, prefer `NOT EXISTS` with an explicit condition.

### 6.2. Computing Order Totals Per Order

A correlated scalar subquery preserves **exactly one row per order**:

~~~sql
SELECT
  o.order_id,
  COALESCE((
    SELECT SUM(i.qty * i.unit_price)
    FROM UNNEST(o.items) AS i
  ), NUMERIC '0') AS total_vnd
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

| order_id | total_vnd |
| --- | ---: |
| O-1001 | 290000 |
| O-1002 | 120000 |
| O-1003 | 0 |

`SUM` over an empty set returns `NULL`, so `COALESCE` converts itemless orders to `0` per the example rules. In production data, totals may need discounts, taxes, refunds, and currency validation; **do not treat this simple sum as the final settlement amount**.

### 6.3. Aggregating by SKU

Conversely, when the **goal is line-item reporting**, unnesting `items` is appropriate:

~~~sql
SELECT
  i.sku,
  SUM(i.qty) AS units_sold,
  SUM(i.qty * i.unit_price) AS gross_vnd
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
GROUP BY i.sku
ORDER BY i.sku;
~~~

Result:

| sku | units_sold | gross_vnd |
| --- | ---: | ---: |
| SKU-A | 3 | 360000 |
| SKU-B | 1 | 50000 |

**Distinguish the grain:** the source table is **one row per order**, whereas after `UNNEST(items)` it is **one row per item**. `SUM` and `COUNT` must always match the grain of the business question.

## 7. Rebuilding Arrays and Structures After Transformation

### 7.1. `ARRAY(SELECT AS STRUCT ...)`

To keep one row per order while retaining only items with `qty >= 2`:

~~~sql
SELECT
  o.order_id,
  ARRAY(
    SELECT AS STRUCT i.sku, i.qty, i.unit_price
    FROM UNNEST(o.items) AS i
    WHERE i.qty >= 2
    ORDER BY i.sku
  ) AS large_quantity_items
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

`ARRAY(subquery)` returns an empty array when the subquery returns no rows, **not a `NULL` array**. `SELECT AS STRUCT` preserves all three fields in each element. `ORDER BY` inside the subquery defines the resulting array's element order; without it, do not assume the original order is kept.

### 7.2. `ARRAY_AGG` and the NULL Issue

If you unnested an array in order to group:

~~~sql
SELECT
  o.order_id,
  COALESCE(
    ARRAY_AGG(i.sku IGNORE NULLS ORDER BY i.sku),
    ARRAY<STRING>[]
  ) AS sku_list
FROM demo_orders AS o
LEFT JOIN UNNEST(o.items) AS i ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

For O-1003, `LEFT JOIN` produces a row with `sku=NULL`; **`IGNORE NULLS`** prevents storing a `NULL` element in the aggregated array. BigQuery can error if an array in the **final query output** contains a `NULL` element; `ARRAY_AGG` over zero non-NULL values returns `NULL`, so `COALESCE` turns it into `[]`.

`ARRAY_AGG` supports `DISTINCT`, `ORDER BY`, and `LIMIT` when needed; verify logic carefully if prior joins multiplied rows. **Never use `ARRAY_AGG(DISTINCT ...)` to mask a row-explosion bug** when real data allows two separate items with the same SKU but different prices or quantities.

### 7.3. Nested Arrays via `STRUCT`

GoogleSQL **does not directly support**:

~~~sql
-- UNSUPPORTED SYNTAX: ARRAY<ARRAY<INT64>>
-- Shown only as what to avoid; do not execute.
~~~

To store groups of arrays, wrap the inner array in a `STRUCT`:

~~~sql
SELECT [
  STRUCT('morning' AS period, [3, 5] AS counts),
  STRUCT('evening' AS period, [6, 8] AS counts)
] AS series;
~~~

The resulting type is `ARRAY<STRUCT<period STRING, counts ARRAY<INT64>>>`. This pattern is also useful when one item has multiple promotions or one athlete has multiple competition rounds.

## 8. Avoiding Row Multiplication Across Multiple Repeated Fields

If an order has **2 items** and **2 tags**, unnesting both in the same `FROM` clause produces **4 combinations** for that single order:

~~~sql
-- Demonstrates row multiplication: O-1001 produces 2 × 2 = 4 rows.
SELECT o.order_id, i.sku, tag
FROM demo_orders AS o
CROSS JOIN UNNEST(o.items) AS i
CROSS JOIN UNNEST(o.tags) AS tag
WHERE o.order_id = 'O-1001';
~~~

This creates a **Cartesian product between two arrays from the same parent row**. Computing revenue directly on this output would count every item in O-1001 **twice**.

**Safe approach:** compute each metric at the **per-order** grain and combine, or use correlated subqueries:

~~~sql
SELECT
  o.order_id,
  (SELECT COUNT(*) FROM UNNEST(o.items)) AS item_count,
  (SELECT COUNT(*) FROM UNNEST(o.tags)) AS tag_count,
  COALESCE((
    SELECT SUM(i.qty * i.unit_price)
    FROM UNNEST(o.items) AS i
  ), NUMERIC '0') AS total_vnd
FROM demo_orders AS o
ORDER BY o.order_id;
~~~

If you need to pair two arrays **positionally** (for example `codes[j]` matching `scores[j]`) rather than forming a Cartesian product, carry `WITH OFFSET`, join on the index, and handle arrays of unequal length. Never assume two independent arrays always have the same length.

## 9. Creating Real BigQuery Schemas

### 9.1. Partitioned Table for Orders

Example DDL to run **only in a lab project** where dataset `analytics` already exists. `CREATE TABLE` mutates resources and can incur storage/query charges.

~~~sql
-- WRITE: replace project/dataset with an authorized environment.
CREATE TABLE IF NOT EXISTS `retail-lab.analytics.orders_nested` (
  order_id STRING NOT NULL,
  order_date DATE,
  customer STRUCT<customer_id STRING, city STRING>,
  items ARRAY<STRUCT<sku STRING, qty INT64, unit_price NUMERIC>>,
  tags ARRAY<STRING>
)
PARTITION BY order_date
CLUSTER BY order_id
OPTIONS(description='Orders with repeated line items');
~~~

| Design Choice | Rationale and Notes |
| --- | --- |
| `PARTITION BY order_date` | Date-range filters enable **partition pruning** when SQL uses matching predicates. |
| `CLUSTER BY order_id` | Can speed up lookups by specific order IDs on large tables, depending on data distribution and queries. |
| `items ARRAY<STRUCT<...>>` | Keeps parent–child together, avoiding separate joins for frequently co-accessed line items. |
| `unit_price NUMERIC` | Supports exact decimal arithmetic; define currency conversion rules explicitly. |
| `order_id STRING NOT NULL` | Enforces non-nullability, **does not guarantee uniqueness**. |

Choose partitioning/clustering based on **actual query patterns** rather than copying this layout blindly to every table. If most workloads group by SKU across billions of items, benchmark queries and repeated-field cardinality; an item-grain table or separate materialized/precomputed summary may perform better.

### 9.2. An ndJSON Record with Nested/Repeated Fields

One JSON object on **one line** in `orders.jsonl`:

~~~json
{"order_id":"O-1001","order_date":"2026-11-18","customer":{"customer_id":"C-01","city":"HCM"},"items":[{"sku":"SKU-A","qty":2,"unit_price":120000},{"sku":"SKU-B","qty":1,"unit_price":50000}],"tags":["web","vip"]}
~~~

`customer` is a JSON object matching `STRUCT`; `items` is a JSON array of objects matching `ARRAY<STRUCT>`; `tags` is an array of strings. **Never** write a multi-line top-level JSON array `[{...},{...}]` instead of newline-delimited JSON: every line must be **one record**.

In real environments, prefer an **explicit schema** for the data contract; autodetect can misinfer types (for example numeric-looking IDs, empty arrays, or sparsely populated fields). BigQuery supports loading nested fields from ndJSON/Parquet/Avro/ORC with matching schemas.

### 9.3. Loading from Cloud Storage via `bq`

~~~bash
# WRITE: requires existing dataset and table, and existing GCS objects.
# BigQuery job location must be compatible with dataset and bucket rules.
bq --location=asia-southeast1 load \
  --noreplace \
  --source_format=NEWLINE_DELIMITED_JSON \
  retail-lab:analytics.orders_nested \
  gs://REPLACE_WITH_BUCKET/landing/orders-*.jsonl

# READ-ONLY: inspect schema without reading customer values.
bq show --schema --format=prettyjson \
  retail-lab:analytics.orders_nested
~~~

If the table already has a schema, the load job uses the destination schema and expects compatible JSON data. For a brand-new table when testing autodetect, verify `--autodetect` carefully; in production, manage explicit schema versions and error-record policies rather than letting types drift on every load.

### 9.4. `STRUCT` vs. the `JSON` Data Type

| `STRUCT` / `ARRAY<STRUCT>` | `JSON` |
| --- | --- |
| Schema defines fields and types at table design time. | Structure can vary flexibly across records. |
| SQL field access via `customer.city`, `i.sku` with static type checking. | Uses `JSON_VALUE`, `JSON_QUERY`, etc., with explicit type casting as needed. |
| Best for transactional/event sources with stable contracts and repeated analytics. | Best for semi-structured payloads that evolve unpredictably or take many shapes. |
| Requires controlled schema evolution. | Fewer structural constraints, but shifts quality/casting checks to SQL/consumers. |

Do not turn every nested object into `JSON` just to avoid defining a schema. Conversely, do not force highly polymorphic payloads into dozens of mostly-empty nested fields when `JSON` is a cleaner fit.

## 10. Query Optimization and Cost Control

### 10.1. Nested Is Not Always Better Than `JOIN`

BigQuery stores data in columnar format; nested/repeated schemas often help when **parent–child data are queried together**, reducing `JOIN` steps and data shuffled between slots. However:

- **Many-to-many** relationships, large shared dimensions reused across many fact tables, or well-modeled **star schemas** may still be better normalized.
- Extremely long arrays inside a single row can cause **data skew** and limit parallelism; benchmark with realistic array lengths.
- If every analytical query unnest millions of elements and groups by SKU, consider a separate **item-grain** table or dedicated summary table for that workload.
- Never choose nested schemas solely to have "fewer tables"; choose based on **query patterns, update frequency, schema evolution, and testability**.

### 10.2. Reducing Bytes Scanned and Unnecessary Work

~~~sql
-- READ-ONLY: example query on a real table partitioned by order_date.
SELECT
  o.order_date,
  i.sku,
  SUM(i.qty) AS units_sold
FROM `retail-lab.analytics.orders_nested` AS o
CROSS JOIN UNNEST(o.items) AS i
WHERE o.order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-19'
GROUP BY o.order_date, i.sku
ORDER BY o.order_date, i.sku;
~~~

Guidelines:

1. **Filter on the partition column** so BigQuery can prune unneeded partitions.
2. Select only **fields actually needed**—never default to `SELECT *` on wide tables with many nested fields.
3. Do not unnest an array if you only need `ARRAY_LENGTH` or a membership check.
4. Avoid `CROSS JOIN UNNEST` across multiple independent arrays without controlling **cardinality**.
5. Inspect the **query plan, shuffle, slot time**, and bytes billed; `LIMIT 10` **does not guarantee** reduced bytes scanned on non-clustered tables.

### 10.3. Dry Run Before Heavy Queries

~~~bash
# READ-ONLY: estimates bytes processed; replace project/dataset names.
# Run in Bash; do not use sample names if resources do not exist.
bq --location=asia-southeast1 query \
  --use_legacy_sql=false \
  --dry_run \
  --format=prettyjson \
  'SELECT order_id, customer.city
   FROM `retail-lab.analytics.orders_nested`
   WHERE order_date = DATE "2026-11-19"'
~~~

Dry run validates compilation and **estimates bytes processed** without guaranteeing the final bill equals that exact figure. On-demand pricing charges per bytes billed under current rules; capacity/slot editions calculate costs differently. Verify **project, dataset location, permissions, and budgets/quotas** before running batch queries.

## 11. `NULL` Edge Cases and Schema Changes

### 11.1. `NULL` Arrays, Empty Arrays, and `NULL` Elements

~~~sql
SELECT
  ARRAY_LENGTH(ARRAY<STRING>[]) AS empty_length,
  ARRAY_LENGTH(CAST(NULL AS ARRAY<STRING>)) AS null_length;

-- Query returns three rows, one of which has a NULL element:
SELECT element
FROM UNNEST([1, NULL, 2]) AS element;
~~~

- **`[]` differs from `NULL` in SQL expressions**: `ARRAY_LENGTH([])` is 0, while `ARRAY_LENGTH(NULL)` is `NULL`.
- `UNNEST([])` and `UNNEST(NULL)` both yield **0 rows**; `UNNEST([1,NULL,2])` yields **3 rows**, including one `NULL`.
- When loading repeated fields from ndJSON, adhere to the source format's rules: **JSON arrays cannot contain `null` elements** under BigQuery's load contract for repeated fields; missing/null fields and empty arrays may be handled differently by source interfaces.
- Returning an array containing `NULL` elements from `ARRAY_AGG` in the **final query result** can fail; use `IGNORE NULLS` or filter appropriately.

Avoid assuming all `NULL` arrays are stored differently from empty arrays on disk: **materialization/table writes can normalize `NULL` arrays to `[]`**. If you need to distinguish "customer did not supply a list" from "explicitly empty list," store a dedicated business **status flag** rather than relying on array nullability alone.

### 11.2. Schema Evolution

When upstream adds a field, such as `items.discount_code`, never let load jobs mutate production schemas uncontrolled. Process:

1. **Review the contract:** is the new field optional or required, and what does it mean for historical rows?
2. **Create a compatible schema change:** add the nested field with a valid mode using a supported BigQuery schema update method.
3. **Test against historical data:** older records missing the new field still read cleanly with corresponding defaults (`NULL` for nullable fields).
4. **Roll out producers before/after per compatibility strategy:** avoid breaking SQL pipelines, Dataflow jobs, or BI consumers.
5. **Backfill or expose compatibility views** if reports expect default values; measure cost and correctness.
6. **Delete or rename legacy fields only** after verifying zero remaining consumers/dependencies and preparing a rollback plan.

BigQuery supports several in-place schema updates, yet **not every type/mode/nested structural change is backward-compatible**. If recreating a table is unavoidable, check partitioning, clustering, access policies, downstream views, and copy costs. Never treat `CREATE OR REPLACE TABLE` as a harmless rollback step.

## 12. Security, Pipelines, and Data Quality

### 12.1. Role-Separated IAM by Function

| Principal | Responsibility | Minimum Permissions to Consider |
| --- | --- | --- |
| Cloud Run/GKE producer | Writes events to Pub/Sub/GCS. | Only publish/write permissions to required targets. |
| Load-job service account | Reads GCS objects, creates jobs, writes BigQuery tables. | Storage Object Viewer on scoped bucket/prefix; BigQuery Job User and write access on target dataset/table. |
| Analyst | Queries authorized tables/regions. | BigQuery Job User and Data Viewer / authorized views on scoped resources. |
| Pipeline/CI | Deploys schemas and SQL artifacts. | Scoped dataset/table management with audit trails; never default Project Owner. |
| Auditor | Reviews config, metrics, audit trails. | Appropriate metadata/logging permissions without default PII row access. |

A `STRUCT` containing `customer_id`, location, or contact fields **is still sensitive data** if it identifies individuals. Nested fields do not hide data from anyone holding table read permissions; enforce **column-level access controls/data policies, authorized views, row access policies, or masking** as appropriate for the product and table. Never put tokens, passwords, or access keys into JSONL payloads or query logs.

### 12.2. Minimal Data Validation Checks

Run in the same script after `demo_orders` is created:

~~~sql
-- READ-ONLY: reconcile order count, line item count, and synthetic total value.
SELECT
  (SELECT COUNT(*) FROM demo_orders) AS orders,
  (SELECT COUNT(*) FROM demo_orders o
   CROSS JOIN UNNEST(o.items) AS i) AS line_items,
  (SELECT SUM(i.qty * i.unit_price)
   FROM demo_orders o CROSS JOIN UNNEST(o.items) AS i) AS gross_vnd;
~~~

Expected result: **3 orders, 3 line items, 410000 VND**. If a SQL edit changes `gross_vnd` to 700000 VND, suspect **row multiplication after `UNNEST`** before concluding revenue grew.

For real data, add checks for **required/nullable schema conformance, duplicate order IDs, quantity > 0, non-negative prices, currency codes, nested coordinates, unusually long arrays, missing fields, and late updates**. Reconcile BigQuery totals against Cloud SQL/Spanner source tables at a defined reconciliation cutoff.

## 13. Symptom-Based Troubleshooting

| Symptom | Common Cause | Where to Check |
| --- | --- | --- |
| `Cannot access field sku on a value with type ARRAY...` | Referencing `items.sku` as a scalar. | Use `UNNEST(items) AS i`, then `i.sku`. |
| Orders without items vanish | Using `CROSS`/`INNER JOIN UNNEST`. | Use `LEFT JOIN UNNEST ON TRUE` or compute on parent row. |
| `COUNT(*)` exceeds actual item count | `LEFT JOIN` keeps one NULL row for empty arrays. | Use `COUNT(i.sku)` when non-NULL, or `ARRAY_LENGTH`. |
| Revenue is doubled or tripled | Unnesting both `items` and `tags` creates a Cartesian product. | Aggregate each array in a correlated subquery or match the grain. |
| SQL throws `Array index out of bounds` | Using `OFFSET`/`ORDINAL` on an empty array. | Switch to `SAFE_OFFSET`/`SAFE_ORDINAL`. |
| Items appear out of order | Relying on implicit ordering from `UNNEST`/`ARRAY_AGG`. | Use `WITH OFFSET` and explicit `ORDER BY`. |
| `Array cannot have a null element` | `ARRAY_AGG` includes NULLs in the final output array. | Add `IGNORE NULLS`, `COALESCE`, or filter explicitly. |
| Nested data errors during JSON load | Input is not ndJSON, wrong type/mode, or JSON array contains null. | Inspect individual JSON lines, schema, and load-job error details. |
| Query job scans too much data | `SELECT *`, missing partition filter, or exploding join. | Dry run, column projection, pruning, query plan. |
| `Access Denied` on nested field | Missing BigQuery IAM/data policy/authorized view or job permission. | Effective principal, table policy, column permissions, and audit logs. |
| Adding a nested field breaks BI reports | Schema evolution incompatible with downstream consumers. | Contract tests, consumer SQL, and field mode. |

**Diagnostic order:** identify the grain (order vs. item) → check nested types/modes → inspect `UNNEST` and joins → check `NULL`/empty arrays → reconcile aggregates → review query plan/bytes → check IAM for access errors. Never mask a row-multiplication bug by slapping `DISTINCT` onto the query, because it can silently drop legitimate duplicate records.

## 14. Exercises

### Exercise 1 — Identifying Data Types

Describe the GoogleSQL type and schema mode for: (a) a `customer` containing `city`; (b) a list of `tags`; (c) a list of `items` where each element has `sku` and `qty`; (d) each item having an array of `promotion_codes`. Why can't you declare `ARRAY<ARRAY<STRING>>` directly?

### Exercise 2 — Safe Access

Write SQL selecting `order_id`, `customer.city`, the first item, and the item count from `demo_orders`. The query must still return **O-1003** without an out-of-bounds error.

### Exercise 3 — `UNNEST` Dropping Rows

Across the 3 sample orders, how many rows does `CROSS JOIN UNNEST(items)` return? How many does `LEFT JOIN UNNEST(items)` return? Explain why `COUNT(*)` on the LEFT JOIN result does not equal total items.

**Hint:** CROSS = **3 rows**; LEFT = **4 rows**, because O-1003 is preserved with a NULL item.

### Exercise 4 — Order Totals

Write a query computing `total_vnd` per order without dropping itemless orders. Then write a query summarizing `units_sold` by SKU. Reconcile the sum across orders and across SKUs to **410000 VND**.

### Exercise 5 — `EXISTS` and Array Filtering

Find orders containing `SKU-A` and orders with the `vip` tag **without expanding parent rows in the result**. Explain when to use `EXISTS` versus `IN UNNEST`.

### Exercise 6 — Row Explosion Across Two Arrays

For O-1001 with 2 items and 2 tags, if you `CROSS JOIN UNNEST` both, how many rows are produced? What erroneous total would result? Fix the query so it still returns item count, tag count, and order total.

**Hint:** 4 rows, and the total can double from **290000 to 580000 VND** when summing items over the Cartesian product.

### Exercise 7 — Reconstructing `ARRAY<STRUCT>`

Write `ARRAY(SELECT AS STRUCT ...)` retaining only items with `qty >= 2`. The output must include all three orders, with empty arrays for the two orders without matching items. Why should `ORDER BY` be included inside?

### Exercise 8 — Schema Design and Ingestion

Design `orders_nested` partitioned by `order_date` with nested `customer` and repeated `items`. Write a compatible ndJSON line, and outline how to use `bq load`, schema contracts, least-privilege IAM, and error-load testing.

### Exercise 9 — Production Optimization

A table has billions of orders averaging 3 items each, with a few orders having tens of thousands of items. A report reads only the last 7 days and groups by SKU. Choose partitioning/filtering, query design, dry run/monitoring, and discuss when to build a dedicated item-grain table. Propose one test that prevents row explosion across two arrays.

## 15. Implementation Checklist and Official Documentation

| Category | What to Verify |
| --- | --- |
| **Grain and semantics** | Is each row an order, item, or event? Do `JOIN`/`UNNEST` change the grain? |
| **Schema** | `STRUCT`/`RECORD`, `ARRAY`/`REPEATED`, field modes, and nesting depth limits are valid. |
| **SQL** | Dot notation, `SAFE_OFFSET`, `CROSS`/`LEFT UNNEST`, and `WITH OFFSET` are used correctly. |
| **Aggregates** | `COUNT`/`SUM` match the intended grain; empty/null arrays are handled intentionally. |
| **Reaggregation** | `ARRAY(SELECT AS STRUCT)`, `ARRAY_AGG IGNORE NULLS`, and element ordering are verified. |
| **Modeling** | Nested structures are used where parent–child are co-queried; extreme array lengths avoided. |
| **Ingestion** | ndJSON/Parquet/Avro schemas align; loads include logging, contracts, and tests. |
| **Performance** | Partition filters, column projection, dry runs, row-explosion checks, query plans, and costs. |
| **Security** | Job User/Data Viewer/Writer IAM, nested PII, and masking/data policies where needed. |
| **Release** | Backward-compatible schema evolution, CI tests, data reconciliation, and rollback plans. |

Official sources:

- [BigQuery — Nested and repeated columns](https://cloud.google.com/bigquery/docs/nested-repeated)
- [GoogleSQL data types](https://cloud.google.com/bigquery/docs/reference/standard-sql/data-types)
- [GoogleSQL — Work with arrays](https://cloud.google.com/bigquery/docs/arrays)
- [GoogleSQL — `UNNEST` query syntax](https://cloud.google.com/bigquery/docs/reference/standard-sql/query-syntax#unnest_operator)
- [GoogleSQL — Array functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/array_functions)
- [GoogleSQL — Aggregate functions](https://cloud.google.com/bigquery/docs/reference/standard-sql/aggregate_functions)
- [BigQuery — Best practices for nested/repeated fields](https://cloud.google.com/bigquery/docs/best-practices-performance-nested)
- [BigQuery — Load ndJSON from Cloud Storage](https://cloud.google.com/bigquery/docs/loading-data-cloud-storage-json)
- [BigQuery — Partitioned tables](https://cloud.google.com/bigquery/docs/partitioned-tables)
- [BigQuery — Query cost estimation](https://cloud.google.com/bigquery/docs/best-practices-costs)
- [BigQuery — Schema changes](https://cloud.google.com/bigquery/docs/managing-table-schemas)
- [BigQuery — Access control](https://cloud.google.com/bigquery/docs/access-control)

**Remember:** `STRUCT` models **a single nested object**, `ARRAY` models **multiple elements**, and `UNNEST` changes the **grain of the output**. Choose `CROSS JOIN` when you genuinely want one row per item, `LEFT JOIN` to keep orders with empty arrays, and `EXISTS` or correlated subqueries when you do not want row multiplication. Good schema design must go hand in hand with **result validation, partition pruning, IAM, and cost measurement**—not merely SQL that compiles and runs.
