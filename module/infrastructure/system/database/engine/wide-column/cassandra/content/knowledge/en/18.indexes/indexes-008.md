# Indexes on Collections, Maps, or Versioned Structures

> **Chapter:** Indexes  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra, a distributed wide-column database.

## Objective

In Cassandra, being able to write a `WHERE` clause does not mean the query will run efficiently on a large cluster. The partition key still determines how data is distributed across nodes; secondary indexes allow lookups on certain other columns, but carry write, storage, maintenance, and search costs. Things get trickier when a column holds a `set`, `list`, `map`, `frozen` type, or payloads whose structure evolves across application versions.

After this lesson, you will be able to:

- Determine when you can index collection elements, map keys, map values, or map key–value entries.
- Write CQL to create and query collection indexes; distinguish `CONTAINS`, `CONTAINS KEY`, and `map['key'] = value`.
- Distinguish **traditional secondary indexes (2i)** from **Storage-Attached Index (SAI)**, along with support differences across Cassandra versions and distributions.
- Understand limitations of `frozen`, UDTs, and `schema_version`-dependent payloads; decide when to create a query-driven table instead of searching via an index.
- Evaluate consequences for replication, consistency levels, TTL/tombstones, compaction, repair, and updating indexes from Java applications.

## 1. Why do collection indexes differ from single-column indexes?

A scalar `text` column holds a single value; a collection holds multiple elements. With `map<text,text>`, for example, there are at least three distinct kinds of questions:

| Business question | Illustrative CQL | Component to index |
| --- | --- | --- |
| Does the product carry tag `sale`? | `tags CONTAINS 'sale'` | Elements in a `set` / `list` |
| Do attributes include key `color`? | `attributes CONTAINS KEY 'color'` | **Keys** of the map |
| Do attributes have value `blue` under any key? | `attributes CONTAINS 'blue'` | **Values** of the map |
| Is the `color` attribute specifically `blue`? | `attributes['color'] = 'blue'` | **Key–value entries** of the map |
| Does the entire collection equal an exact value? | `frozen_attrs = {'color':'blue'}` | The **entire** `frozen` collection |

The first four predicates are not equivalent. If a map is `{'color':'blue', 'status':'active'}`, `CONTAINS 'blue'` does not prove the `color` key holds `blue`; the value `blue` could live under a different key. Conversely, `CONTAINS KEY 'color'` checks only key presence, not the value stored under that key.

### Sample data

The following examples assume a keyspace is already selected in `cqlsh`, such as `USE demo;`, and use fixed UUIDs for easy practice:

```sql
CREATE TABLE catalog_items_by_id (
    item_id uuid PRIMARY KEY,
    tags set<text>,
    revision_labels list<text>,
    attributes map<text, text>,
    schema_version int,
    title text
);

INSERT INTO catalog_items_by_id
    (item_id, tags, revision_labels, attributes, schema_version, title)
VALUES
    (11111111-1111-1111-1111-111111111111,
     {'sale', 'eco'}, ['draft', 'published'],
     {'color': 'blue', 'tier': 'premium'},
     2, 'Water Bottle');

INSERT INTO catalog_items_by_id
    (item_id, tags, revision_labels, attributes, schema_version, title)
VALUES
    (22222222-2222-2222-2222-222222222222,
     {'new'}, ['draft'],
     {'color': 'red', 'tier': 'standard'},
     1, 'Backpack');
```

**Design note:** This table intentionally uses a simple primary key to focus on index syntax. In real applications, consider `tenant_id`, partitioning, collection size, and access controls. Do not use this example as a default multi-tenant search architecture.

## 2. Indexes on `set` and `list`: finding an element

For non-`frozen` collections, membership queries commonly use `CONTAINS` backed by an index on element values:

```sql
-- Traditional secondary index (2i), illustrating non-frozen collection indexing.
CREATE INDEX catalog_tags_values_idx
ON catalog_items_by_id (VALUES(tags));

SELECT item_id, title
FROM catalog_items_by_id
WHERE tags CONTAINS 'sale';
```

Similarly, if you need to find rows containing `'published'` in `revision_labels`:

```sql
CREATE INDEX catalog_revision_values_idx
ON catalog_items_by_id (VALUES(revision_labels));

SELECT item_id, title
FROM catalog_items_by_id
WHERE revision_labels CONTAINS 'published';
```

Key points:

- A `set` is unordered and deduplicated; a `list` is ordered and allows duplicates. A membership index answers only whether a value is in the collection, not its position in the `list`.
- Large, frequently mutated collections trigger frequent index updates and create tombstones when deleting or replacing elements.
- A membership index does not automatically optimize queries like "newest element in the list," "first three labels," or positional filtering. Those are signs to model separately with clustering keys or a query-driven table.
- Never stuff thousands of elements into a collection simply to mimic a relational many-to-many table; evaluate a dedicated table whose primary key expresses the query.

If only a tiny fixed set of values exists, such as `active/inactive`, the index may scan huge numbers of matching rows across many partitions. Being able to write `CONTAINS` does not guarantee low cost.

## 3. Indexes on `map`: KEY, VALUE, and ENTRY

On `map<text,text>`, three common query patterns require three distinct indexing modes. The statements below illustrate **independent index options**; do not create all of them on one column in production merely because the syntax exists. Pick the one matching the target query and verify support in your running Cassandra version/distribution.

### 3.1. Looking up by key: `KEYS(map)`

```sql
CREATE INDEX catalog_attrs_keys_idx
ON catalog_items_by_id (KEYS(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes CONTAINS KEY 'color';
```

Results include all rows having a `color` key regardless of whether its value is `blue` or `red`. This index fits "does attribute X exist?" rather than "does X equal Y?"

### 3.2. Looking up by value: `VALUES(map)`

```sql
CREATE INDEX catalog_attrs_values_idx
ON catalog_items_by_id (VALUES(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes CONTAINS 'premium';
```

This finds any row containing at least one map value equal to `premium`; it **does not guarantee** that value lives under the `tier` key. If you care only about one fixed key, this index is semantically too broad.

### 3.3. Looking up by exact pair: `ENTRIES(map)`

```sql
CREATE INDEX catalog_attrs_entries_idx
ON catalog_items_by_id (ENTRIES(attributes));

SELECT item_id, title
FROM catalog_items_by_id
WHERE attributes['tier'] = 'premium';
```

This predicate requires specifically the `tier` key paired with the value `premium`. Its semantics differ from combining `CONTAINS KEY 'tier'` and `CONTAINS 'premium'`: both individual `CONTAINS` predicates could hold while `premium` actually belongs to a different key.

| Index | Indexed information | Predicate form |
| --- | --- | --- |
| `KEYS(attributes)` | Key names | `attributes CONTAINS KEY 'tier'` |
| `VALUES(attributes)` | Values, not tied to a specific key | `attributes CONTAINS 'premium'` |
| `ENTRIES(attributes)` | Key *and* value paired together | `attributes['tier'] = 'premium'` |

**Implementation verification point:** CQL expresses these index forms on Cassandra releases supporting collection indexes, yet available index types, multi-index support on the same column, and data-type limits can vary across Apache Cassandra, managed Cassandra services, and compatible distributions. During deployment, verify DDL directly on the target environment rather than treating examples as a universal compatibility matrix.

## 4. 2i and SAI: how do they differ by version?

**2i (legacy secondary index)** has existed since earlier Cassandra generations. Indexes are maintained locally alongside replica data; cross-partition queries can scatter across many nodes. On large datasets, low selectivity, or dense values, result scanning, fan-out, and merging costs can grow substantially.

**SAI (Storage-Attached Index)** is an indexing mechanism tied to the SSTable storage lifecycle, integrated into Apache Cassandra **5.0**. SAI suits many selective secondary queries better, yet still carries read/write costs and does not replace query-driven table design.

| Environment | What to know |
| --- | --- |
| Standard Apache Cassandra 3.x and 4.x | 2i is the traditional index option; built-in SAI as in Cassandra 5.0 is not present by default. Custom index mechanisms may appear depending on distribution. |
| Apache Cassandra 5.0+ | Includes built-in SAI; verify which data types, collection indexing targets, and option syntax your specific release supports. |
| Managed Cassandra / custom distributions | SAI, custom indexes, and limits may differ from upstream; check actual vendor docs and configuration. |

Illustrative DDL explicitly specifying SAI on a supporting version:

```sql
-- Apache Cassandra 5.0+ or distribution with compatible SAI.
-- Test on a new table or one without a competing index for the same target.
CREATE CUSTOM INDEX catalog_tags_sai_idx
ON catalog_items_by_id (VALUES(tags))
USING 'StorageAttachedIndex';

SELECT item_id, title
FROM catalog_items_by_id
WHERE tags CONTAINS 'eco';
```

If you need SAI on a map, verify whether your running Cassandra release supports the corresponding target (`KEYS`, `VALUES`, `ENTRIES`). Example DDL structure to **verify on a supporting release**:

```sql
CREATE CUSTOM INDEX catalog_attrs_entries_sai_idx
ON catalog_items_by_id (ENTRIES(attributes))
USING 'StorageAttachedIndex';
```

**Do not run SAI examples alongside 2i examples on the same column** in a shared environment: these are alternative approaches for comparison, not instructions to create them all. If DDL is rejected, read the error message and your version's support matrix; never work around it with `ALLOW FILTERING` to fake an index.

SAI does not provide a general full-text search engine for every need and does not replace keyspace partitioning, replication, or consistency levels. For high-frequency, high-load queries, a query-driven table remains more predictable.

## 5. `frozen`, UDTs, tuples, and nested structures

### 5.1. Non-frozen vs. frozen collections

Non-`frozen` collections let Cassandra manage and update individual elements; hence element-level indexes apply depending on version.

A `frozen` collection is stored and updated as **a single monolithic value**. Element membership operations or single-entry updates generally do not apply the same way as non-frozen collections; if your version allows indexing a whole frozen collection, it matches **the entire value** rather than individual map keys.

```sql
CREATE TABLE shipping_rules_by_id (
    rule_id uuid PRIMARY KEY,
    frozen_options frozen<map<text, text>>
);

-- Applies only when version/index type supports FULL on frozen collections.
CREATE INDEX shipping_frozen_options_idx
ON shipping_rules_by_id (FULL(frozen_options));

INSERT INTO shipping_rules_by_id (rule_id, frozen_options)
VALUES (
    33333333-3333-3333-3333-333333333333,
    {'carrier': 'A', 'zone': 'north'}
);

-- Matches the entire map; adding/removing one entry yields a different value.
SELECT rule_id
FROM shipping_rules_by_id
WHERE frozen_options = {'carrier': 'A', 'zone': 'north'};
```

With `frozen<map<text,text>>`, only two maps with the exact same set of key–value pairs match as equivalent values; `FULL` does not mean "index every nested attribute inside."

### 5.2. User-defined types (UDTs) or tuples

Cassandra provides UDTs and `tuple`s to group multiple fields into one column:

```sql
CREATE TYPE delivery_address (
    city text,
    district text
);

CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    address frozen<delivery_address>,
    schema_version int
);
```

Do not assume you can write `CREATE INDEX ... ON orders_by_id (address.city)` or query arbitrary JSON paths like in a document database. Index support on UDTs, tuples, nested collections, or sub-fields depends on data type and version-specific index support. If `WHERE city = ?` is a core query, promoting `city` to a dedicated column or key of a purpose-built read table is far safer.

Cassandra supports certain JSON import/export features in CQL, but that **does not** automatically make every attribute inside a JSON payload an indexed field.

## 6. Structures that evolve with `schema_version`

Suppose an application stores `attributes` where version 1 used `'colour'` and version 2 uses `'color'`. A query `attributes['color'] = 'blue'` matches only rows written under the exact key `color`; an index cannot unify two different meanings automatically.

```text
Version 1: {'colour': 'blue', 'tier': 'premium'}
Version 2: {'color': 'blue', 'tier': 'premium'}
                                 │
                                 └── Same business meaning,
                                     but different map key at query time
```

Options to handle this:

1. **Normalize at write time:** read legacy data, translate field names to one canonical form, and run controlled backfills. Define clearly how older app versions still writing data are handled.
2. **Promote stable columns:** promote `color text`, `category text`, and `schema_version int` for querying. Keep `attributes` solely for rarely queried extensions.
3. **Use a query- and version-driven table:** store derived payload attributes with a primary key tailored to queries; maintain consistency through write workflows and reconciliation.
4. **Transition period:** if both `colour` and `color` must be queried, execute two controlled queries and merge by ID in the application; plan deprecation of the old key. Never assume `OR` and `ALLOW FILTERING` will perform well across versions.

For an important query like "list products in tenant X, schema version V, category C," model a query-driven table:

```sql
CREATE TABLE items_by_tenant_category_version (
    tenant_id text,
    schema_version int,
    category text,
    item_id uuid,
    title text,
    PRIMARY KEY ((tenant_id, schema_version, category), item_id)
);

SELECT item_id, title
FROM items_by_tenant_category_version
WHERE tenant_id = 'shop-01'
  AND schema_version = 2
  AND category = 'water-bottles';
```

This `SELECT` specifies the **exact partition key**, avoiding global secondary indexes. In exchange, the application must maintain the query table when products change. If a tenant/version/category combination grows too large or hot, add an appropriate bucket inside the partition key and adjust reads accordingly.

**Rule of thumb:** volatile or sparse attributes can live in a map; attributes frequently used for filtering or sorting across many queries should usually be promoted to explicit columns or dedicated query tables. `schema_version` explains how to interpret a payload, yet indexing `schema_version` alone is rarely adequate if each version spans millions of rows.

## 7. Operational costs, consistency, and common errors

### 7.1. Indexes must be updated as data changes

Example updating a non-frozen map and set:

```sql
UPDATE catalog_items_by_id
SET attributes['color'] = 'green'
WHERE item_id = 11111111-1111-1111-1111-111111111111;

UPDATE catalog_items_by_id
SET tags = tags + {'featured'}
WHERE item_id = 11111111-1111-1111-1111-111111111111;
```

Cassandra must propagate these changes into the relevant indexes. With very large maps, frequent updates, TTLs, and continuous element deletions, index maintenance, tombstones, and compaction overhead can climb. Measure write latency, index disk usage, p95/p99 read latency, and partitions/rows scanned.

### 7.2. Indexes, replication, and consistency levels

Replication determines where data copies live; an operation's consistency level determines how many replicas must participate or acknowledge. Indexes locate records; they **do not replace** replication and consistency protocols.

- A secondary-index query may contact multiple replicas or nodes depending on index implementation, partition keys, and data distribution.
- Read freshness after writes, index build status, and behavior during node failures must be verified on a real cluster. Never assume creating an index guarantees all queries immediately see all data in every situation.
- Compaction governs SSTable/tombstone lifecycles and corresponding index data; repair reconciles replicas within Cassandra's model. Neither fixes an ill-suited query model or `schema_version` logic bugs.
- When adding an index to a populated table, monitor index build/backfill progress and node health before relying on query results for business decisions.

### 7.3. Pre-production verification checklist

| Item to verify | Specific question |
| --- | --- |
| Version | Is the cluster Apache Cassandra 4.x, 5.x, or a compatible distribution? Is SAI present? Are `FULL`, `KEYS`, `VALUES`, `ENTRIES` supported on your exact types? |
| DDL and queries | Does index creation succeed? Are intended `WHERE` clauses supported without abusing `ALLOW FILTERING`? |
| Selectivity | Does a predicate match a few rows or millions of rows? Are tenant/partition bounds clear? |
| Size and churn | How many elements per collection? Are there heavy updates/deletes, short TTLs, or accumulating tombstones? |
| Performance | Measure on realistic data sizes and concurrent write load; track p95/p99, participating nodes, CPU/disk resources, and index build cost. |
| Operations | Verify build/rebuild behavior, node failures, repair, compaction, backup/restore, and queryability across upgrades. |

Inspect schema via `DESCRIBE TABLE catalog_items_by_id;` in `cqlsh`. To check declared index state/type, inspect version-appropriate metadata in `system_schema.indexes` or cluster admin tools. Use `TRACING ON;` in test environments to inspect query execution, but never leave tracing broadly enabled in production due to its overhead.

### 7.4. Connecting with Java applications

A Java application using the Cassandra driver issues `SELECT` statements with `CONTAINS` or map-entry predicates just like manual CQL. Binding parameters does not change the underlying query mechanism:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public final class CatalogSearch {
    private final CqlSession session;
    private final PreparedStatement byTag;

    public CatalogSearch(CqlSession session) {
        this.session = session;
        this.byTag = session.prepare(
            "SELECT item_id, title FROM catalog_items_by_id " +
            "WHERE tags CONTAINS ?");
    }

    public ResultSet findByTag(String tag) {
        return session.execute(byTag.bind(tag));
    }
}
```

This example assumes the keyspace and required index are ready, and Driver 4.x is connected to the right cluster/local datacenter. Because an index query does not necessarily specify a partition key, routing and latency differ from primary-key queries. In real applications, bound page sizes, paginate properly, configure timeouts, and load-test with realistic data. Never use `ALLOW FILTERING` to force unmodeled queries through.

## 8. Design decision scenario

Suppose a system stores 30 million products, each with an attributes map across multiple tenants, and has three requirements:

1. **Fetch one product by ID:** use a table keyed by `product_id` and appropriate tenant key. Map indexes add no value for this query.
2. **Ad-hoc filtering on a few rarely used attributes:** evaluate SAI if supported by your version, selectivity is strong, and benchmarks pass. With 2i on a large table, pay close attention to fan-out and matching row counts.
3. **Frequently listing all products for a tenant and category with pagination:** build a query-driven table `items_by_tenant_category` with an appropriate partition key/bucket and clustering key for desired ordering. Do not rely on cluster-wide `CONTAINS` as a primary read path.

If map keys change across `schema_version`, normalize values or maintain derived indexes/tables over stable business fields. Seeing Cassandra return rows for one version does not prove other versions are covered.

## 9. Self-check questions

**Question 1.** Given `attributes = {'color':'blue', 'tier':'premium'}`, does `attributes CONTAINS 'premium'` prove `attributes['tier'] = 'premium'`? If not, which index accurately expresses that requirement?

**Question 2.** You have a `frozen<map<text,text>>` column; users ask to "find all maps containing key `color`, regardless of other keys." Should you use `FULL(frozen_map)` and whole-map comparison to satisfy this?

**Question 3.** A standard Cassandra 4.x system needs high-load searches across multiple secondary fields. Can you assume Apache Cassandra 5.0 SAI DDL will work out of the box? What must you check first?

**Question 4.** Two event versions store `'colour'` and `'color'` for the same concept. Does creating an `ENTRIES(attributes)` index automatically reconcile that difference? What design is more durable?

**Answer hints:**

1. No. `CONTAINS 'premium'` only confirms the value `premium` appears somewhere in the map. Use an entries index if supported by your version and query `attributes['tier'] = 'premium'`.
2. No. `FULL` on a frozen map (when supported) compares the entire map value. To look up individual keys, use a non-frozen map with a keys index, or promote the field to a separate column/query table.
3. No. Verify the distribution, whether SAI actually exists, collection/DDL support, selectivity, performance, and operational plans.
4. No. An index does not understand that two key names are synonyms. Normalize on write, migrate legacy data, or maintain query columns/tables keyed by normalized attributes and `schema_version`.

## Key takeaways

- Collection indexes answer different questions: **elements** of `set/list`, **keys**, **values**, or **entries** of `map`; choose an index matching your `WHERE` semantics.
- `FULL` on `frozen` collections (when supported) searches by **whole value**, not nested sub-fields.
- 2i exists in older Cassandra generations; SAI is built into Apache Cassandra 5.0. Syntax and collection support must be verified against your exact version/distribution.
- Indexes do not replace query-driven table design, partition keys, benchmarking, replication, or consistency levels.
- When structures evolve across versions, normalize field semantics and build migration/reconciliation flows; an index alone never knows `'colour'` and `'color'` mean the same thing.
