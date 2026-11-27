# ALTER TABLE: Adding, Dropping, Modifying Properties, and Type-Change Conditions

## 1. What Problem Does ALTER TABLE Solve?

In Apache Cassandra, `ALTER TABLE` modifies the **schema of an existing table**. Depending on the CQL version and table type, you can add or drop certain columns, rename certain columns within permitted limits, or adjust **table options** such as default TTL, compaction, compression, and comment. However, Cassandra does not treat altering a table as an operation that automatically transforms all existing rows into a new data model.

This is a lesson in the **Keyspaces and Schema** chapter of module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. For a distributed wide-column database, table design is tightly coupled to reads/writes by **partition key**, **clustering columns**, replication, and consistency level. Therefore, before modifying a schema, distinguish:

- **Metadata changes:** Cassandra updates column definitions and table options.
- **Stored data changes:** the application may have to backfill, transform data, dual-write, or create a new table.
- **Topology/replication changes:** belong to the keyspace and cluster operations, and are **not** performed with `ALTER TABLE`.

After this lesson, you should be able to explain when to use `ADD`, `DROP`, `RENAME`, and `WITH`; when a data type or primary key change requires designing a migration; and how to verify the schema before a Java application depends on it.

## 2. Commonly Used Forms of ALTER TABLE

The basic statement forms look like this:

```sql
-- Add a new column.
ALTER TABLE keyspace_name.table_name
ADD new_column text;

-- Drop an existing column, if the column is of a droppable kind.
ALTER TABLE keyspace_name.table_name
DROP old_column;

-- Rename a column of a kind permitted by the Cassandra version.
ALTER TABLE keyspace_name.table_name
RENAME old_column TO new_column;

-- Change one or more table options.
ALTER TABLE keyspace_name.table_name
WITH comment = 'Table description'
 AND default_time_to_live = 0;
```

These are **syntax templates**; do not run them verbatim against a nonexistent `keyspace_name.table_name`. Variants such as `IF EXISTS`/`IF NOT EXISTS`, modifying multiple columns at once, `RENAME` support, and supported options **depend on the Cassandra version**. When writing real migrations, check the exact syntax for the target cluster and test on a test environment of the same version.

| Change Type | Main Effect | Automatically Rewrites Historical Data? |
| --- | --- | --- |
| `ADD column` | Appends a new column definition | **No**; old rows do not automatically get a new value |
| `DROP column` | Removes a droppable column definition | **Does not immediately delete** all old bytes in SSTables |
| `RENAME column` | Renames a column within supported scope | Does not convert types or alter partition structure |
| `WITH table_option` | Changes table operational configuration | Depends on the option; usually does not immediately convert all SSTables/rows |
| Changing partition key or data type | Usually not supported as a plain `ALTER TABLE` | Must evaluate migration/new table and data transfer |

**First principle:** read the current schema before modifying it. The desired state in a migration file does not prove the actual state already matches it.

## 3. Preparing the Example: An Order Table Designed by Query

The examples below use keyspace `schema_lab` on a **test environment**. Assume `nodetool status` shows the lab node belongs to DC `datacenter1` and the lab has only one node. If the actual DC has a different name, replace it in the replication map.

```sql
CREATE KEYSPACE IF NOT EXISTS schema_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': '1'
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS schema_lab.orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    amount decimal,
    status text,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
  AND default_time_to_live = 0;
```

Inspect the schema right after creating it:

```sql
DESCRIBE TABLE schema_lab.orders_by_customer;
```

`DESCRIBE` is a `cqlsh` command. If the table already existed, `IF NOT EXISTS` **does not guarantee** the current definition matches the one just written. Cross-check the schema and avoid writing further into a structurally mismatched table.

To have test data:

```sql
INSERT INTO schema_lab.orders_by_customer (
    customer_id, created_at, order_id, amount, status
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-20T08:00:00Z',
    aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa,
    250000.00,
    'PAID'
);

SELECT created_at, order_id, amount, status
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

The table's partition key is `customer_id`, and its clustering keys are `created_at` and `order_id`. Each partition contains one customer's orders; because orders can grow over time, this is only an illustrative model. In production, evaluate partition size and consider adding a time bucket if traffic is high.

## 4. ADD: Adding a Column Without Auto-Populating Old Rows

Suppose a new requirement needs a delivery note:

```sql
ALTER TABLE schema_lab.orders_by_customer
ADD shipping_note text;
```

After the schema change completes and nodes know the new definition, you can write a value for the new column to a row:

```sql
UPDATE schema_lab.orders_by_customer
SET shipping_note = 'Deliver before 6 PM'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND created_at = '2026-11-20T08:00:00Z'
  AND order_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

SELECT created_at, order_id, shipping_note
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

**Existing rows are not automatically populated with a default value.** Cassandra does not automatically run a backfill across all partitions on `ADD`. A row that has never had `shipping_note` written will typically return `null` for that column when read.

### Limits to note when adding columns

1. `ADD` appends a new **regular column** per table rules; depending on table structure, a `static column` can be added if supported and suited to the model. Do not use `ADD` to alter components of the `PRIMARY KEY`.
2. Column names must not collide with existing columns; avoid re-adding a previously `DROP`ped name to "change its type" because of risks with metadata and old data in SSTables.
3. Before the application reads/writes the new column, wait for schema agreement and ensure the driver receives the updated metadata.
4. For large systems, if business logic requires a default value, implement a rate-limited **backfill** by partition key or via a controlled data pipeline. Do not treat `ALTER TABLE ADD` as a command that updates every record.
5. If existing Java applications map results into fixed objects, deploy code that handles `null` for the new column during the transition period.

### Does adding a column change replica distribution?

No. Cassandra selects partitions based on the partition key and places replicas based on the **keyspace's** replication strategy. Adding `shipping_note` does not change `customer_id`, add replicas, or alter `LOCAL_QUORUM` or the CL of individual statements.

## 5. DROP: Dropping a Column and Impact on Existing Data

When `shipping_note` is no longer used, you can drop this regular column:

```sql
ALTER TABLE schema_lab.orders_by_customer
DROP shipping_note;
```

Once the change takes effect, querying or writing `shipping_note` is no longer valid. However, **dropping the column definition does not mean every SSTable containing cells of that column is immediately rewritten**. Cassandra uses the schema and deletion timestamp information to prevent invalid data from surfacing, while physical space reclamation is governed by storage mechanisms, compaction, and operational tasks.

### Primary key columns cannot be dropped this way

In the example table, `customer_id` is the partition key; `created_at` and `order_id` are clustering columns. You cannot use `DROP` to remove any component of the primary key and expect Cassandra to automatically repartition the data.

If you want to change the primary key, the standard design approach is to create a **new table** with a different key, migrate data in a controlled manner, update queries, and retire the old table after verification.

### Check dependencies before DROP

A column may be referenced by:

- CQL queries, prepared statements, and mappers in Java applications.
- Indexes or materialized views, if the system uses such objects.
- ETL/CDC pipelines, reporting queries, synchronization jobs, and data-reading services.

Certain column kinds and dependent objects can cause `DROP` to be rejected depending on the Cassandra version. Do not try to bypass error checks or force schema changes; remove dependencies through an ordered migration.

**Do not use `DROP old_col` followed by `ADD old_col new_type` as a tool to force a type conversion.** Old cells may still remain in SSTables, and dropped-column metadata affects how Cassandra reads data. An intentional data migration is required.

## 6. RENAME: Renaming Does Not Mean Changing Keys, Types, or Data

Cassandra has the syntax:

```sql
ALTER TABLE schema_lab.orders_by_customer
RENAME customer_id TO buyer_id;
```

**This is an example of syntax and conditions to consider, not a mandatory step in the section 3 lab.** `RENAME` capability depends on column kind and Cassandra version. In many versions, support focuses on **primary key columns**, with restrictions involving indexes/materialized views and schema dependencies. Regular columns such as `status` generally cannot be freely renamed with `RENAME`.

If the version and actual table allow renaming `customer_id` to `buyer_id`:

- The `uuid` type and **partition key** role remain the essence of the column; the operation only changes the identifier name.
- Data is not moved to a new partition just because the name changed.
- All CQL statements, mappers, partition-key queries, and Java code must switch to `buyer_id` once the new schema takes effect.

Therefore, **renaming a primary key column does not solve a semantic partition-key change**. If you want to partition by `tenant_id` and `customer_id` instead of `customer_id` alone, you must design a different table and re-ingest data under the new key.

| Requirement | Is `RENAME` Appropriate? | Approach |
| --- | --- | --- |
| Rename a primary key column label, keeping the exact type and role | Possibly, if version and dependencies allow | Check DDL and dependencies, then update application code |
| Change `customer_id uuid` to `customer_id text` | No | Data migration / new table design |
| Move partition key from `customer_id` to `order_id` | No | Create a new query-driven table and backfill |
| Rename regular column `status` to `state` | Should not assume support | Add new column, dual-write/backfill, cut over |
| Rename a table or keyspace | No equivalent general `RENAME` table/keyspace command | Create new object and migrate |

If a name must be changed when `RENAME` is not possible, you can add a new column, backfill, and gradually migrate the application; for primary keys, creating a new table is required.

## 7. WITH: Changing Table Options and Understanding Effective Scope

`ALTER TABLE ... WITH ...` changes properties **of the table**. It does not change the keyspace's RF, does not alter the partition key, and does not guarantee that all old data is automatically recomputed under the new configuration.

### 7.1. Comment and default TTL

Example changing the description and default TTL:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH comment = 'Orders indexed by customer for recent lookups'
 AND default_time_to_live = 604800;
```

`604800` is the number of seconds in seven days. `default_time_to_live` affects **new writes that do not specify an explicit TTL** according to Cassandra rules; this change **does not retroactively add a TTL** to previously written cells. If historical data must be deleted under a new policy, a separate retention/cleanup plan is required.

Example disabling default TTL for subsequent writes:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH default_time_to_live = 0;
```

Disabling default TTL does not restore already-expired data. For business order tables, TTL must be evaluated according to retention and compliance requirements—never arbitrarily set seven days just because of an example.

### 7.2. Compaction and compression

Example adjusting the compaction strategy:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH compaction = {
    'class': 'LeveledCompactionStrategy'
};
```

This is a **syntax template**, not the optimal compaction strategy choice for every workload. Cassandra offers strategies and parameters suited to different data patterns, such as STCS/LCS/TWCS. When changing compaction, Cassandra applies the new rules to compaction work, which can generate I/O load and temporary disk usage; you cannot assume all SSTables immediately transition to the new structure.

Compression is also commonly configured via table options:

```sql
ALTER TABLE schema_lab.orders_by_customer
WITH compression = {
    'class': 'LZ4Compressor'
};
```

Compression can affect SSTables written/compacted later; account for CPU, I/O, disk space, and Cassandra version. Do not treat this as an instant compression command for all data on disk.

### 7.3. `gc_grace_seconds` and tombstone safety

`gc_grace_seconds` relates to the tombstone retention window so replicas have an opportunity to learn that data has been deleted. Arbitrarily lowering this value in a system with long-disconnected replicas or irregular repairs can cause deleted data to reappear when an old replica returns.

```sql
-- Property illustration only, not an operational recommendation:
ALTER TABLE schema_lab.orders_by_customer
WITH gc_grace_seconds = 864000;
```

The actual value should be based on Cassandra version, repair strategy, and potential replica outage duration. Do not reduce this period merely to "purge tombstones faster."

| Table Option | Primary Purpose | What to Evaluate |
| --- | --- | --- |
| `comment` | Attach a description to the table | Usually minimal impact on data |
| `default_time_to_live` | Default TTL for eligible future writes | Not retroactive; risk of data expiration |
| `compaction` | Strategy for organizing and merging SSTables | I/O, write amplification, reads, and disk space |
| `compression` | How SSTables are compressed | CPU, disk usage, query efficiency |
| `gc_grace_seconds` | Relates to the safe window for dropping tombstones | Repair, offline replicas, risk of "zombie" data returning |
| `caching` | Table caching policy | Memory, access pattern |

Not every option is valid on every table type or Cassandra version; for example, counter tables have specific restrictions regarding TTL.

## 8. Conditions for Changing Data Types: Distinguishing Syntax from Safe Conversion

A common reasoning error is assuming `ALTER TABLE` works like `ALTER COLUMN TYPE` in many relational database systems: changing the declared type and having Cassandra automatically read old data and convert every value to the new type.

**In modern Cassandra versions, there is no `ALTER TABLE` mechanism to arbitrarily convert a column's type and automatically rewrite existing data.** Type-changing syntax existed or was limited in some older CQL/Cassandra generations; you cannot assume `ALTER TABLE ... ALTER column TYPE ...` is accepted by the running version. You must check the documentation for the **exact version**, column kind, and conversion limits before planning a migration.

Even in an environment supporting a very narrow conversion, the minimum condition to evaluate is whether the **existing byte representation** is compatible with the target type. Changing metadata does not automatically transform old representations into a new encoding; you also need to assess impact on keys, collections, UDTs, indexes, and client code.

### 8.1. Examples that cannot be treated as in-place type changes

| Desired Change | Issue | Practical Approach |
| --- | --- | --- |
| `price text` → `price decimal` | Strings and decimals have different representations; some data may be unparseable | Add `price_decimal`, convert each valid value, and cut over |
| `customer_id uuid` → `customer_id text` (partition key) | Changing key type can alter representation/token and query behavior | Create a new table with the key and data migration pipeline |
| `created_at timestamp` → `created_at text` (clustering key) | Changing key type affects encoding, sort order, and query conditions | Create a new table and write data under the new design |
| `tags text` → `tags set<text>` | Changing scalar to collection alters storage/read semantics | New column or new table, transform data |
| `address frozen<address_type>` → UDT with different structure | Must check compatibility rules, frozen/non-frozen, and UDT upgrades | Design UDT/table migration per version, test with real data |
| `text` ↔ `varchar` | Equivalent type names in common CQL | Usually requires no physical type change; inspect schema representation instead of running unnecessary DDL |

In particular, **partition keys and clustering columns** are directly tied to the read/write model: never assume `ALTER TABLE` can safely add/drop/retype key components. When partition distribution or clustering order must change, create a table tailored to the new query.

### 8.2. "Expand → backfill → cutover → contract" migration for regular columns

Suppose column `status` currently stores `text`, but the new application requires an `int` status code. You can migrate in phases:

1. **Expand:** add new column `status_code int`, keeping `status text`.
2. **Dual-write:** the transitional application writes both columns, or establish a synchronization mechanism to prevent data divergence.
3. **Backfill:** convert old values according to business mapping, e.g., `PAID → 2`; run with rate limiting and resumability after errors.
4. **Verify:** validate data by partition, counts, mapping correctness, and query results at the required CL.
5. **Cutover:** switch all read paths to the new column once data and clients are ready.
6. **Contract:** drop the old column only after dependencies are gone and a recovery plan is in place.

CQL example for one row:

```sql
ALTER TABLE schema_lab.orders_by_customer
ADD status_code int;

UPDATE schema_lab.orders_by_customer
SET status_code = 2
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND created_at = '2026-11-20T08:00:00Z'
  AND order_id = aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa;

SELECT status, status_code
FROM schema_lab.orders_by_customer
WHERE customer_id = 11111111-1111-4111-8111-111111111111;
```

Cassandra does not provide a relational-SQL-style `UPDATE` that scans the entire table and converts every row. For large datasets, you typically must build a backfill tool partitioned by partition key, handling pagination, bounded retries, and result reconciliation. Do not abuse `ALLOW FILTERING` to turn a massive backfill into a direct cluster-wide query.

### 8.3. Changing the primary key requires a new table

If, starting from `orders_by_customer`, you want to look up orders directly by `order_id` with predictable latency, build a table serving that query:

```sql
CREATE TABLE IF NOT EXISTS schema_lab.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    amount decimal,
    status_code int
);
```

The new table has partition key `order_id`. Business workflows must write/synchronize tables per query needs, backfill historical data, and manage consistency across denormalized copies. `ALTER TABLE` on the old table cannot change the partition key to `order_id` or automatically create a table distributed by the new key.

## 9. Observing the Schema After ALTER TABLE

After every change, verify **what Cassandra recorded** and whether the application can rely on the new schema.

In `cqlsh`:

```sql
DESCRIBE TABLE schema_lab.orders_by_customer;
```

With metadata tables:

```sql
-- View columns, types, and roles in keys.
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'schema_lab'
  AND table_name = 'orders_by_customer';

-- View key table options.
SELECT table_name, default_time_to_live, gc_grace_seconds,
       compaction, compression, comment
FROM system_schema.tables
WHERE keyspace_name = 'schema_lab'
  AND table_name = 'orders_by_customer';
```

| Where to Check | What to Confirm |
| --- | --- |
| `system_schema.columns` | Was the column added/dropped properly? Do `kind`, `type`, and `position` match expectations? |
| `system_schema.tables` | Have default TTL, compaction, compression, and comment changed as planned? |
| `DESCRIBE TABLE` | Is the overall table DDL still compatible with the design and dependencies? |
| Schema agreement | Have nodes received the same schema version before proceeding with dependent steps? |
| Test query by partition key | Can the driver/CQL read and write the new column with the right type? |

`DESCRIBE` is a `cqlsh` utility command, not a CQL query that the Java driver necessarily executes directly. Metadata from `system_schema` can be queried by the driver, but matching metadata **does not prove historical data has been fully backfilled**.

### Schema agreement and coordinating application versions

In a multi-node cluster, schema changes propagate; an `ALTER TABLE` succeeding through a coordinator does not necessarily mean **every node is instantaneously** ready for queries depending on the new column. Monitor schema agreement through appropriate tooling/drivers; avoid running multiple interdependent schema changes concurrently.

If the Java application has multiple instances:

- Put schema migrations under a single coordination mechanism, avoiding conflicting DDL execution from every instance.
- Deploy in backward-compatible order: add column, wait for schema agreement, roll out new application version, backfill/cutover, and only then drop the old column.
- For prepared statements, ensure client code is compatible with the new schema; re-prepare statements or refresh metadata if schema-related errors occur.
- Check consistency levels for backfill and verification reads while avoiding impact on ongoing write paths, compaction, or repair.

## 10. Java Example: Checking Column Metadata Before Writing with a Prepared Statement

Example illustrating Cassandra Java Driver 4.x. Assume `CqlSession session` is already created and lifecycle-managed; column `status_code` has been added and schema agreement is complete.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.Instant;
import java.util.UUID;

// session already exists, connected to the right cluster/keyspace.
Row metadata = session.execute("""
    SELECT kind, type
    FROM system_schema.columns
    WHERE keyspace_name = 'schema_lab'
      AND table_name = 'orders_by_customer'
      AND column_name = 'status_code'
    """).one();

if (metadata == null
        || !"regular".equals(metadata.getString("kind"))
        || !"int".equals(metadata.getString("type"))) {
    throw new IllegalStateException("status_code missing or wrong type");
}

PreparedStatement update = session.prepare("""
    UPDATE schema_lab.orders_by_customer
    SET status_code = ?
    WHERE customer_id = ?
      AND created_at = ?
      AND order_id = ?
    """);

session.execute(update.bind(
    2,
    UUID.fromString("11111111-1111-4111-8111-111111111111"),
    Instant.parse("2026-11-20T08:00:00Z"),
    UUID.fromString("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
));
```

Java text blocks require Java 15 or later. Bind markers `?` are for **values**, not replacing keyspace/table/column names. If the application must support older Java versions, use ordinary Java strings with proper escaping.

This snippet only verifies one regular column. Production migrations must also verify primary keys, critical columns, table options, and data assumptions before enabling features that depend on the new schema.

## 11. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| `ADD` succeeds, but old rows return `null` | Adding a column does not backfill data | Handle `null`, run backfill when business logic requires it |
| `DROP` column fails | Column is part of the primary key or has indexes/views/dependencies | Check metadata and handle per model rules; do not force the command |
| `RENAME` is rejected | Column kind or Cassandra version does not permit it | Evaluate new-column/new-table strategy and update application |
| Attempting `ALTER COLUMN ... TYPE` fails with syntax error | Type-change syntax is unsupported in the version | Add a new column or create a new table, migrate values in a controlled way |
| Changed TTL, but old data does not auto-expire | `default_time_to_live` is not retroactive | Design separate historical data handling |
| Changed compaction and I/O spiked | SSTables need to be processed under the new strategy | Monitor compaction, disk space, and node load |
| After `ADD`, some Java instances fail with `Undefined column` | Schema has not propagated or client has not refreshed metadata | Wait for schema agreement, handle refresh/re-prepare appropriately |
| Changed `gc_grace_seconds` and deleted data reappeared | Replica missed tombstones for too long, unsuitable repair | Review configuration and repair schedule, assess recovery |
| `ALTER TABLE` finished, but queries by new key are inefficient | Cannot change partition key by adding a regular column | Design a new query-driven table and backfill |
| Table name is right, but definition differs from expected | Earlier `CREATE IF NOT EXISTS` skipped an existing schema | Read `system_schema`, evaluate drift, then run proper migration |

## 12. Self-Verifying Practice Exercise

On `schema_lab` from section 3 (or your own lab keyspace):

1. Check `DESCRIBE TABLE` and `system_schema.columns` to record the initial schema, especially `customer_id`, `created_at`, and `order_id`.
2. Add `shipping_note text` and verify the new column appears in metadata. Read a row before writing this column to observe `null`.
3. Update `shipping_note` for a row using the **full PRIMARY KEY**, read it back, and verify the contents.
4. Use `ALTER TABLE ... WITH comment = '...'` to change the description. Read `system_schema.tables.comment` to confirm.
5. Add `status_code int`, convert one `'PAID'` value to `2`, and explain why a single `ALTER` command does not automatically convert all old strings.
6. Drop `shipping_note` after confirming it is no longer needed; verify the column is gone from `system_schema.columns`.
7. Design table `orders_by_id` yourself for querying by `order_id`; explain why merely doing `ADD order_id` on another table will **not** change its partition key.

Only when lab data no longer needs to be kept can you clean up the test environment separately:

```sql
-- Warning: deletes all tables and data in schema_lab.
DROP KEYSPACE IF EXISTS schema_lab;
```

Do not execute this `DROP` statement on a keyspace containing data or used by active services.

## 13. Checklist Before Rolling Out ALTER TABLE to Production

| Question | Required Evidence |
| --- | --- |
| Are the target table and cluster right? | Fully qualified `keyspace.table`, connection environment, metadata |
| Is the change `ADD`, `DROP`, `RENAME`, or `WITH`? | Valid syntax for the exact Cassandra version |
| Does it touch partition/clustering keys? | Compare keys in `system_schema.columns`; design a new table if needed |
| Do old values need conversion? | Backfill plan, type mapping, invalid-data handling, and verification |
| Are there dependent indexes, materialized views, or Java code? | Dependency list, backward-compatible rollout order |
| Does it change TTL/compaction/compression? | Assessment of data, disk resources, I/O, and operational impact |
| Have nodes agreed on the schema? | Schema agreement and post-change metadata queries |
| When can the old column/table be dropped? | Cutover done, data reconciled, dependencies gone, recovery plan clear |
| Is availability/CL affected during migration? | Monitor errors, read/write load, replica/repair conditions |

**Remember:** `ALTER TABLE` in Cassandra primarily changes **schema metadata and table options**. Adding a column does not automatically backfill, dropping a column does not immediately purge all SSTables, changing table options is not necessarily retroactive, and changing types/primary keys typically requires a designed migration. Reading metadata, verifying schema agreement, and migrating data in phases is the safe way to coordinate CQL, replication/compaction/repair, and Java applications.
