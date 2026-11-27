# SELECT Structure, Column Selection, and Result Expressions in Apache Cassandra

## Learning Objectives

After this lesson, you will be able to:

1. Read and write `SELECT` statements in Cassandra Query Language (CQL), distinguishing the **data selection** part from the **result column projection** part.
2. Select specific columns, use `*`, assign aliases with `AS`, and understand the shape of the returned data.
3. Build result expressions using arithmetic operators, `CAST`, scalar functions, `WRITETIME`, `TTL`, and aggregate functions.
4. Distinguish between `SELECT JSON`, `toJson()`, and `SELECT DISTINCT`, and recognize their limitations.
5. Identify a `SELECT` statement that is syntactically valid yet unsuited to Cassandra's partitioning model.

This lesson belongs to the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. In a distributed wide-column database like Apache Cassandra, `SELECT` must be considered within the context of **partition keys, clustering columns, query-driven table design, replication, and consistency**. Specifying the list of columns to return is no substitute for identifying the partition to read.

## 1. Mental Model: Find the Rows First, Shape the Result Second

For a CQL query, separate two questions:

- **Which rows are read?** `FROM` identifies the table; `WHERE` identifies the partition and the subset of rows within the partition; `ORDER BY` and `LIMIT` narrow or order the result within Cassandra's constraints.
- **What is returned from those rows?** The part between `SELECT` and `FROM` is the *selection clause* (also called projection): column names, `*`, aliases, functions, or expressions that produce the result columns.

Example:

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
LIMIT 20;
```

In this example, the `(customer_id, order_day)` pair in `WHERE` locates **a single partition**; the `ordered_at, status, amount_cents` list only specifies the **three columns appearing in the result**. Even though `customer_id` is used for filtering, it does not automatically appear in the result unless listed in `SELECT`.

> Practical rule: design tables around your queries and partition keys first; only then decide which columns to project for each API or screen.

## 2. General SELECT Syntax

Common syntax structure in CQL:

```sql
SELECT [JSON | DISTINCT] (* | selector [AS alias] [, selector [AS alias] ...])
FROM [keyspace_name.]table_name
[WHERE condition [AND condition ...]]
[GROUP BY column_name [, column_name ...]]
[ORDER BY clustering_column [ASC | DESC] [, ...]]
[PER PARTITION LIMIT n]
[LIMIT n]
[ALLOW FILTERING];
```

Components:

| Component | Role | Key point to remember in Cassandra |
| --- | --- | --- |
| `SELECT ...` | Specifies result columns and expressions | Can use `*` or a list of selectors. |
| `JSON` | Encodes each result row as a JSON object | Placed right after `SELECT`; different from calling `toJson()` on a single column. |
| `DISTINCT` | Retrieves distinct results by partition | Not arbitrary `DISTINCT` on any column like in relational SQL. |
| `FROM` | Selects exactly one table (optionally with keyspace) | CQL `SELECT` does not support `JOIN` or subqueries in `FROM`. |
| `WHERE` | Specifies the partition and data slice | Usually starts with the partition key; conditions on clustering keys must follow key order. |
| `GROUP BY` | Groups rows and applies aggregate functions | Constrained by primary key columns and their order. |
| `ORDER BY` | Sorts by clustering columns | Constrained by the table's clustering order; cannot arbitrarily sort by regular columns. |
| `PER PARTITION LIMIT` | Limits the number of rows per partition | Different from limiting the total number of rows. |
| `LIMIT` | Limits the total number of result rows | Not equivalent to page size or SQL `OFFSET`. |
| `ALLOW FILTERING` | Permits certain queries requiring broad filtering/scanning | Can incur unpredictable read costs; not a fix for table design. |

`JSON` and `DISTINCT` occupy the same optional slot in the syntax; do not combine them as `SELECT JSON DISTINCT ...`. This lesson focuses on the **selection clause** and result expressions; filtering conditions, ordering, and paging will be analyzed in detail in separate lessons.

## 3. Practice Table for cqlsh

Suppose an e-commerce application needs to display orders for **one customer on one day**. Each day for a customer is a partition; `ordered_at` is a clustering column to sort newest orders first.

```sql
-- Only use replication_factor = 1 for a single-node learning environment.
CREATE KEYSPACE IF NOT EXISTS cql_select_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE cql_select_lab;

CREATE TABLE IF NOT EXISTS orders_by_customer (
    customer_id uuid,
    order_day date,
    ordered_at timeuuid,
    status text,
    amount_cents bigint,
    note text,
    tags set<text>,
    attributes map<text, text>,
    PRIMARY KEY ((customer_id, order_day), ordered_at)
) WITH CLUSTERING ORDER BY (ordered_at DESC);

INSERT INTO orders_by_customer
    (customer_id, order_day, ordered_at, status, amount_cents, note, tags, attributes)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', now(), 'CREATED', 125050, 'Deliver during business hours',
     {'online'}, {'channel': 'web'});

INSERT INTO orders_by_customer
    (customer_id, order_day, ordered_at, status, amount_cents, note, tags, attributes)
VALUES
    (11111111-1111-4111-8111-111111111111,
     '2026-11-20', now(), 'PAID', 259900, 'Paid',
     {'mobile', 'priority'}, {'channel': 'app'});
```

**Design explanation:**

- `PRIMARY KEY ((customer_id, order_day), ordered_at)`: the two columns inside the inner parentheses form a **composite partition key**; each `ordered_at` value distinguishes rows within the partition.
- `ordered_at timeuuid` with `now()` generates time-ordered values; `CLUSTERING ORDER BY (ordered_at DESC)` defines the default read order within a partition.
- `status`, `amount_cents`, `note`, `tags`, and `attributes` are regular data columns; selecting them in `SELECT` does not turn them into keys.
- `SimpleStrategy` with one replica is only convenient for a lab. In multi-node or multi-datacenter deployments, choose an appropriate replication strategy (typically `NetworkTopologyStrategy`) and configure consistency in cqlsh/driver according to system requirements; consistency is not part of the selector list.

The two `INSERT` statements use `now()`, so the actual `ordered_at` values differ across runs. The query examples below use a known partition without needing to guess the newly generated time UUID.

## 4. Selecting Columns and Assigning Aliases

### 4.1. Selecting Only the Needed Columns

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

The result has **three columns** matching the `SELECT` list. For an order history screen, this is good practice to avoid sending `note`, `tags`, or `attributes` when they are not yet needed. Selecting fewer columns generally reduces network payload and mapping work in the Java application; actual disk read savings depend on storage layout and the specific query.

```sql
SELECT *
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`*` returns all columns defined in the table. It is convenient when exploring data in cqlsh, but has three drawbacks for long-lived APIs: payloads can become large, schema changes can alter the returned column set, and the application easily becomes coupled to columns it does not actually need.

**Note:** `SELECT *` with a `WHERE` clause targeting a single partition is still very different from `SELECT * FROM orders_by_customer;` without `WHERE`. The latter may have to scan data across multiple nodes; replacing `*` with two columns does not automatically make a full-table scan safe.

### 4.2. Aliases with AS

```sql
SELECT ordered_at AS created_time,
       amount_cents AS total_in_cents,
       status AS order_status
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`AS` renames **the column in the result set**, not in the table schema, and does not alter stored data. This provides clearer names for DTOs or for expressions with hard-to-read default names.

You cannot use an alias as a source column name in `WHERE` or `ORDER BY` of the same statement:

```sql
-- Wrong: "order_status" is only a result alias, not a table column.
SELECT status AS order_status
FROM orders_by_customer
WHERE order_status = 'PAID';

-- Valid in terms of column name reference; filtering by status
-- must still align with keys/indexes and the query plan.
SELECT status AS order_status
FROM orders_by_customer
WHERE status = 'PAID' ALLOW FILTERING;
```

The second example only illustrates referencing the **original column name**, not a recommended query: scanning/filtering by `status` on this table can be very expensive. In an application, you typically need a dedicated table modeled for status queries if you must find orders by status across many customers/days.

Unquoted names are treated case-insensitively by CQL. For case-sensitive display names, you can use a double-quoted alias:

```sql
SELECT amount_cents AS "amountCents"
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

## 5. Result Expressions: What Values Can a Selector Return?

A selector can be a **column name**, **literal/term**, **type cast**, **arithmetic operation**, **function**, or **aggregate function**. CQL has rich expression capabilities, but they follow data type rules and scope constraints different from general-purpose SQL.

| Selector form | Example in `SELECT` list | Meaning |
| --- | --- | --- |
| Base column | `status` | The stored value of the column. |
| Constant literal | `'orders' AS source` | Same literal for each returned row; does not generate extra rows by itself. |
| Arithmetic operation | `amount_cents / 100` | Computes a value from operands according to CQL type rules. |
| Type cast | `CAST(amount_cents AS decimal)` | Converts to a compatible type. |
| Scalar function | `abs(amount_cents)` | Applied to the value of each row. |
| Metadata function | `ttl(note)`, `writetime(status)` | Reads TTL/timestamp metadata of the corresponding cell. |
| Aggregate function | `count(*)`, `sum(amount_cents)` | Combines multiple rows into a single aggregate value. |

### 5.1. Arithmetic Operations and Precedence

Since Apache Cassandra **4.0**, CQL supports `+`, `-`, `*`, `/`, `%` on compatible numeric types as well as unary `-`. `*`, `/`, `%` have higher precedence than `+`, `-`; use parentheses to express intent clearly.

```sql
SELECT ordered_at,
       amount_cents,
       amount_cents / 100 AS units_truncated,
       CAST(amount_cents AS decimal) / 100 AS units_decimal
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

With `amount_cents = 125050` (type `bigint`):

- `amount_cents / 100` performs integer division and yields `1250`, losing the fractional part.
- `CAST(amount_cents AS decimal) / 100` computes in decimal arithmetic, yielding `1250.5`.

Therefore, if you need ratios, prices, or percentages, consider the **operand types** before choosing division. `CAST` cannot recover lost decimal precision if applied *after* integer division. For currency, consider storing the smallest integer unit (such as cents) in the raw data and converting units only at the presentation layer.

### 5.2. Scalar Functions and CAST

```sql
SELECT ordered_at,
       CAST(amount_cents AS text) AS amount_text,
       abs(amount_cents) AS absolute_amount
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`CAST(selector AS type)` only supports **valid type conversion pairs**, not arbitrary conversions between any types. Function names and return types are determined by the Cassandra version and function signatures. User-defined functions (UDFs) also depend on whether UDFs are enabled in the cluster configuration; do not assume they are always available.

When reading results in the Java driver, the CQL type of the **post-conversion expression** determines the corresponding getter method; for example, a selector returning `decimal` is mapped differently from one returning `bigint`.

### 5.3. Reading Cell TTL and Write Timestamp

```sql
SELECT ordered_at,
       status,
       writetime(status) AS status_write_us,
       ttl(note) AS note_ttl_seconds
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

- `writetime(status)` is the write timestamp of the **`status` column value** in microseconds since the Unix epoch; it is not necessarily the order creation time and may differ from the timestamps of other columns in the same row.
- `ttl(note)` is the **remaining seconds** before the `note` value expires; if the value has no TTL, the result is `null`.
- Do not arbitrarily apply `writetime`/`ttl` to primary key columns. Special types such as counters and multi-cell collections/UDTs have version-specific rules; the example above intentionally uses simple `text` columns.
- Apache Cassandra 5.0 also provides `maxwritetime(column)` to retrieve the maximum write timestamp when a column spans multiple cells; when compatibility with older versions is required, verify the syntax supported by the cluster.

At the distributed level, which value is read also depends on the **consistency level** configured for the query, replica state, and write conflicts. `WRITETIME` lets you inspect metadata of the returned value, not prove that all replicas are in sync.

### 5.4. Selecting Collection Elements and Returning Column JSON

The example table has `attributes map<text,text>` and `tags set<text>`. With CQL collection element selector support, you can retrieve a map element by key:

```sql
SELECT ordered_at,
       attributes['channel'] AS sales_channel,
       toJson(tags) AS tags_json
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`attributes['channel']` retrieves the value associated with the key `channel` (or `null` if absent). `toJson(tags)` returns a **JSON-encoded text string** for the `tags` column alone, for example `["mobile","priority"]`. The display order of set elements is not the insertion order used by the application.

The `toJson()` function name works on earlier Cassandra versions; in Cassandra 5.0, the `to_json()` alias also exists. When using collection selectors, slices, or UDT field selectors, check the capabilities of the specific Cassandra version and driver, especially on older clusters.

### 5.5. COUNT and Aggregate Functions

```sql
SELECT count(*) AS total_orders,
       min(amount_cents) AS min_amount,
       max(amount_cents) AS max_amount,
       sum(amount_cents) AS sum_amount,
       avg(CAST(amount_cents AS decimal)) AS avg_amount
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

`COUNT(*)` counts rows matching the query. `COUNT(column)` counts non-null values of that column; `MIN`, `MAX`, `SUM`, and `AVG` aggregate matching values. `CAST` before `AVG` avoids precision loss from integer types. Aggregation runs over the rows read; Cassandra does not maintain an instantaneous exact counter for arbitrary queries.

Aggregate queries **over a partition of controlled size** are far more predictable than full-table statistical queries. Do not run `COUNT(*)` on a large table in a real-time request just to display a total order count; consider a summary table or a separate counter/aggregation pipeline.

If you mix regular columns with aggregate functions without corresponding grouping, Cassandra may pick the regular column value from the **first row** of the aggregated set. For example, `SELECT status, count(*) ...` does not mean counting per `status`; if you need counts grouped by status, you must design a data model tailored to that query pattern.

## 6. SELECT JSON and DISTINCT: Two Special Output Forms

### 6.1. SELECT JSON: Each Row as a JSON Object

```sql
SELECT JSON ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

Each row in the result set has a single JSON field (typically displayed as `[json]` in cqlsh) containing a **JSON object encoding the selectors**. It does not turn Cassandra into a document database and does not change the schema. Compare:

| Statement | Returned data shape |
| --- | --- |
| `SELECT status, tags ...` | Two CQL columns with native types `text`, `set<text>`. |
| `SELECT status, toJson(tags) AS tags_json ...` | One `text` column and one `text` column containing a JSON string. |
| `SELECT JSON status, tags ...` | One column containing a JSON string representing the entire selected row. |

In a Java application, regular `SELECT` with native CQL types provides clean type mapping. `SELECT JSON` is convenient for integration or inspecting data, but consider serialization/deserialization overhead and JSON key naming conventions.

### 6.2. SELECT DISTINCT: Only on Appropriate Columns

```sql
-- These two columns form the partition key of the example table.
SELECT DISTINCT customer_id, order_day
FROM orders_by_customer;
```

Cassandra's `DISTINCT` is primarily used to retrieve unique **partition key** values (and in valid cases may include static columns). It cannot be applied arbitrarily like `SELECT DISTINCT status FROM ...` to list distinct statuses. The example above does not restrict the partition, so it can still scan data across multiple nodes; only use it when data size and operational impact are well understood.

## 7. Relationship Between SELECT Expressions and Paging

Distinguish three concepts:

1. **Projection**: `SELECT ordered_at, status` chooses which columns to output.
2. **Query limits**: `LIMIT 20` caps total result rows; `PER PARTITION LIMIT 20` caps rows per partition.
3. **Paging**: Java driver applications typically read results across multiple pages using a configured page size and paging state. Page size is not the maximum row count of the entire query.

Example retrieving up to 20 orders in a day, newest first:

```sql
SELECT ordered_at, status, amount_cents
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
ORDER BY ordered_at DESC
LIMIT 20;
```

In a table defined with `CLUSTERING ORDER BY (ordered_at DESC)`, that order aligns with the clustering order. Cassandra does not provide a SQL-style `LIMIT 20 OFFSET 20` model for arbitrary deep pagination. When building a Java API, use the driver's paging mechanism and store the paging state appropriately for the query; keep in mind that the underlying dataset may change between page reads.

## 8. Common Misconceptions

| Wrong expectation or syntax | Issue | How to handle it |
| --- | --- | --- |
| `SELECT *` is always efficient if `LIMIT 10` is present | It may still touch multiple partitions or scan data to find 10 rows. | Query by partition key, bound the partition, and select only needed columns. |
| `SELECT status FROM ... WHERE status = 'PAID'` | `status` is not in the example table's key; this query has no suitable access path. | Create a table serving status-based queries or evaluate a targeted index and its read plan. |
| `SELECT status AS s ... WHERE s = 'PAID'` | An alias is only a result name and cannot be used in `WHERE`. | Use the original column name and valid filter conditions. |
| `ORDER BY amount_cents DESC` | `amount_cents` is a regular column, not a clustering key. | Design an additional table with the corresponding clustering key if this ordering is genuinely needed. |
| `SELECT DISTINCT status FROM ...` | `DISTINCT` cannot be used arbitrarily on non-key columns. | Design a lookup/summary table or pipeline for the set of status values. |
| `amount_cents / 100` always produces a decimal | Dividing two integers drops the fractional part. | Use `CAST(amount_cents AS decimal) / 100` before dividing. |
| Full-table `COUNT(*)` is cheap because it returns one cell | Cassandra still has to read the relevant rows to count them. | Scope the dataset or maintain pre-aggregated metrics. |
| `ALLOW FILTERING` makes queries on any column fast | It can allow broad scans with unstable latency. | Fix the query pattern, schema, and indexes appropriately. |
| `SELECT JSON` is equivalent to `toJson(tags)` | One encodes the entire row; the other encodes a single value. | Choose the response structure that fits the API. |

Another important consequence: changing the column list in `SELECT` **does not change which partition the query is routed to**. Cassandra's efficiency comes primarily from targeting the right partition, avoiding overly large partitions, minimizing unnecessary scans, and choosing a consistency level that meets read requirements.

## 9. Short Practice Exercises and Suggested Solutions

**Exercise 1.** From the partition for customer `11111111-1111-4111-8111-111111111111` on `2026-11-20`, return `ordered_at`, `status` aliased as `state`, up to 10 rows.

```sql
SELECT ordered_at, status AS state
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20'
LIMIT 10;
```

**Exercise 2.** Return the amount in units larger than `cents`, preserving the decimal part.

```sql
SELECT ordered_at,
       CAST(amount_cents AS decimal) / 100 AS amount_units
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

**Exercise 3.** Inspect the most recent write timestamp of `status` and the remaining TTL of `note`.

```sql
SELECT ordered_at,
       writetime(status) AS write_timestamp_us,
       ttl(note) AS remaining_ttl_s
FROM orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_day = '2026-11-20';
```

**Self-check:** Why can't `SELECT status FROM orders_by_customer WHERE status = 'PAID'` be fixed simply by adding `LIMIT 10`? Because `LIMIT` caps the **result**, but provides neither a partition key nor an access path by `status`. To query across many customers/days by `status` with predictable latency, you must design storage and access patterns accordingly.

## 10. Notes for Use in Java Applications

A `SELECT` statement can return raw columns, aliased columns, or expressions with **new result types**. When implementing with the Java driver:

- Prepare statements with `?` bind markers for values like `customer_id` and `order_day`; never concatenate user input into CQL strings.
- Map CQL types accurately, e.g., `uuid` → `UUID`, `date` → `LocalDate`, `bigint` → `long`/`Long`, `decimal` → `BigDecimal`.
- Configure consistency level and page size at the driver/request layer; the selector list does not control them.
- When changing aliases or expression types, check the code reading columns from `Row`/mapper because returned column names and types may change.

The key mindset to retain is: **`WHERE` determines the read scope based on the data model; `SELECT` determines the structure and transformations of the result**. Both parts must work together for a specific use case, especially when Cassandra is partitioned and replicated across multiple nodes.

## References

- [Apache Cassandra 5.0 — CQL Data Manipulation: SELECT](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/dml.html)
- [Apache Cassandra 5.0 — CQL Functions](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/functions.html)
- [Apache Cassandra 5.0 — Arithmetic Operators](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/operators.html)
- [Apache Cassandra 5.0 — JSON Support](https://cassandra.apache.org/doc/5.0/cassandra/developing/cql/json.html)
- [Apache Cassandra — Using Arithmetic Operators in Cassandra 4.0](https://cassandra.apache.org/_/blog/Using-Arithmetic-Operators-in-Cassandra-4.0.html)
