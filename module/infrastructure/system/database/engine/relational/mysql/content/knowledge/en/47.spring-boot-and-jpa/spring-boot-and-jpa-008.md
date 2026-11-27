# IDENTITY, AUTO_INCREMENT, UUID, and Key Generation Strategies

In Spring Boot and JPA, your primary key generation strategy affects MySQL schema design, when Hibernate must send `INSERT` statements, the ability to batch writes, and InnoDB index performance. `GenerationType.IDENTITY` typically pairs with MySQL `AUTO_INCREMENT`; `GenerationType.UUID` generates UUID identifiers on the application/provider side; and `AUTO` lets the JPA provider pick a strategy based on dialect and configuration.

No single strategy fits every table. Sequential numeric keys are compact, easy to join, and usually have good locality on InnoDB. UUIDs are convenient when multiple services or nodes must generate IDs independently before writing to the database, though random keys can enlarge and fragment indexes. Decisions should rest on how data is created, writer count, batch insert needs, how IDs are exposed in APIs, and scaling plans.

## 1. What Does a Primary Key Do in InnoDB?

In InnoDB, the primary key is the clustered index: row data is physically organized by the primary key. Every secondary index also stores the primary key value to locate the corresponding row. Therefore, primary key size and insertion order affect not only the primary index but every secondary index as well.

Example orders table:

```sql
CREATE TABLE orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  customer_id BIGINT UNSIGNED NOT NULL,
  order_status VARCHAR(24) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (id),
  KEY idx_orders_customer_created (customer_id, created_at)
) ENGINE=InnoDB;
```

A good primary key typically has these characteristics:

- Non-NULL and unique.
- Immutable throughout the record's lifecycle; does not change when mutable business attributes change.
- Compact, keeping the clustered index and secondary indexes small.
- Used consistently in foreign keys across related tables.
- Generated in a way compatible with writer count and deployment topology.

A primary key does not need to carry user-facing meaning. You can use an internal surrogate key while storing business keys such as `order_number`, `email`, or partner codes in separate unique indexes. This lets business rules evolve without rewriting relationship keys across the entire system.

## 2. IDENTITY in JPA and AUTO_INCREMENT in MySQL

`GenerationType.IDENTITY` instructs the database to generate the identifier on insert. With MySQL, Hibernate normally maps this strategy to an `AUTO_INCREMENT` column.

Simple entity:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // Other properties
}
```

Corresponding DDL:

```sql
CREATE TABLE orders (
  id BIGINT NOT NULL AUTO_INCREMENT,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
```

On insert, MySQL assigns the ID value and JDBC/Hibernate retrieves the generated key. With `IDENTITY`, Hibernate typically must execute the insert early to obtain the database-assigned ID. This restricts JDBC insert batching for `IDENTITY` entities; during bulk imports, inserts may not be batched as expected.

`IDENTITY` fits when:

- The application has a single primary writer source for the table.
- You want simple key generation integrated directly with MySQL.
- Insert throughput and batching are not the primary bottleneck.
- Foreign-key child tables need the generated ID right after insert.

Never choose `GenerationType.IDENTITY` assuming it guarantees gap-free sequential IDs or reflects exact commit order. It merely provides a unique identifier assigned by MySQL.

## 3. AUTO_INCREMENT Is Not a Gap-Free Counter

MySQL allocates `AUTO_INCREMENT` values for inserts. Gaps in ID sequences are normal:

- A transaction allocates an ID and then rolls back; the allocated number may not be reused.
- Failed or ignored inserts can still advance the counter.
- Deleting rows does not cause MySQL to backfill missing numbers.
- Concurrent transactions may receive IDs in an allocation order different from commit order.
- Restarts, backup restores, or configuration changes can cause the next value to differ from assumptions based on the highest visible ID.

Accordingly, never use `AUTO_INCREMENT` to represent legally required gap-free invoice numbers or sequences where gaps are forbidden. If business rules require gap-free document numbering, build a dedicated sequence allocator with explicit locking/transactions, concurrency controls, void handling, and auditing per applicable regulations.

Never generate IDs manually by reading `MAX(id) + 1`:

```sql
-- Unsafe under concurrent transactions
SELECT MAX(id) + 1 FROM orders;
```

Two transactions can read the same value and both attempt to insert, causing duplicate key errors or retries. Use `AUTO_INCREMENT`, UUIDs, or a properly synchronized ID allocator.

To fetch a newly inserted ID, use JDBC generated keys or `LAST_INSERT_ID()` on the exact connection that performed the insert. Never query `MAX(id)` after an insert because another transaction may have already inserted a newer row.

## 4. AUTO_INCREMENT in Multi-Writer Systems

A single MySQL primary is the simplest case: all inserts go through one ID source. In multi-writer topologies—especially multi-source or multi-primary—each node may need disjoint value ranges to avoid key collisions.

MySQL provides these variables:

```sql
SHOW VARIABLES LIKE 'auto_increment_increment';
SHOW VARIABLES LIKE 'auto_increment_offset';
```

`auto_increment_increment` defines the step interval and `auto_increment_offset` sets the starting offset within the cycle. These can partition ID ranges across multi-source architectures. Configuration must account for the maximum number of writers and stay consistent as topology changes.

In multi-primary Group Replication, MySQL manages increment/offset automatically according to membership and group settings. Do not manually override values managed by Group Replication unless following your exact version's documentation. For architectures with many independent writers or needing IDs before knowing the target writer node, UUIDs or distributed ID generators may be simpler.

## 5. What Does GenerationType.AUTO Mean?

`GenerationType.AUTO` delegates strategy selection to the JPA provider. The outcome depends on the provider, Hibernate version, database dialect, and generator configuration. Do not assume `AUTO` always equals `IDENTITY` simply because the database is MySQL.

Example:

```java
@Id
@GeneratedValue(strategy = GenerationType.AUTO)
private Long id;
```

Hibernate chooses a generator based on dialect capabilities; on databases without native sequences like MySQL, implementation differs from PostgreSQL or Oracle. Certain versions/providers may select identity, a table-backed generator, or another mechanism. Inspect generated DDL, actual insert SQL, and Hibernate logs whenever upgrading provider versions.

`AUTO` is convenient when letting the provider handle details, but makes behavior implementation-dependent. When batching performance, cross-database portability, or ID generation mechanics are critical requirements, declaring an explicit strategy and testing against your exact version is clearer.

## 6. SEQUENCE and TABLE Generators in MySQL

JPA defines `GenerationType.SEQUENCE`, yet MySQL has no native sequence object like PostgreSQL or Oracle. A provider may reject it or emulate it depending on dialect/version. Never write `CREATE SEQUENCE` syntax from another database expecting MySQL to understand it.

`GenerationType.TABLE` uses a table to store ID counters. JPA example:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    @TableGenerator(
        name = "orders_id_generator",
        table = "id_generator",
        pkColumnName = "generator_name",
        valueColumnName = "next_value",
        pkColumnValue = "orders",
        allocationSize = 50
    )
    @GeneratedValue(
        strategy = GenerationType.TABLE,
        generator = "orders_id_generator"
    )
    private Long id;
}
```

The generator table may look like:

```sql
CREATE TABLE id_generator (
  generator_name VARCHAR(64) NOT NULL,
  next_value BIGINT NOT NULL,
  PRIMARY KEY (generator_name)
) ENGINE=InnoDB;
```

The provider manages locking and updating values in the generator table. `allocationSize` pre-allocates an ID range to reduce hits on the generator table, depending on provider implementation. However, the generator table can become a contention hotspot when many transactions request IDs concurrently; benchmark throughput and synchronization behavior.

Never update the generator table manually via SQL while Hibernate uses it. Setting the stored value below already-issued IDs causes duplicate key errors. Changing allocation size or resetting the generator must follow provider procedures and account for previously allocated ranges.

## 7. UUID and GenerationType.UUID

A UUID is a 128-bit identifier that can be generated in the application without querying MySQL before inserting. This helps when:

- Multiple services or nodes create records independently.
- You need the ID before writing to the database or before publishing an event.
- Data from multiple sources must synchronize without sharing a central counter.
- You prefer not to expose sequential record counts directly in APIs.

Jakarta Persistence 3.1 added `GenerationType.UUID`. Hibernate also provides UUID generator support in corresponding versions. Example using Java's `UUID` type:

```java
@Entity
@Table(name = "external_events")
public class ExternalEvent {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    // Other properties
}
```

The physical column type depends on the provider and mapping configuration. With MySQL, UUIDs may be stored as `CHAR(36)` or `BINARY(16)`. Verify actual DDL and round-trip behavior before deployment; do not assume JPA annotations guarantee a specific byte representation automatically.

With a `String` ID and character-formatted UUID, declare the column explicitly:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
@Column(name = "id", length = 36, nullable = false, updatable = false)
private String id;
```

Illustrative DDL:

```sql
CREATE TABLE external_events (
  id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`CHAR(36)` is human-readable and widely supported by tools, though larger than numeric keys and bulkier than `BINARY(16)`. Character-based storage should use ASCII charset and a consistent collation to avoid unnecessary linguistic comparison rules.

## 8. CHAR(36) or BINARY(16)?

A UUID carries 16 bytes of data. Standard string representation takes 36 characters because of hyphens. Storing `BINARY(16)` reduces key size and secondary index footprint compared to `CHAR(36)`.

| Criterion | `CHAR(36)` | `BINARY(16)` |
|---|---|---|
| Storage footprint | 36 characters | 16 bytes |
| Readability/debugging | Directly readable | Requires conversion for display |
| Comparison/index size | Consumes more space | More compact |
| Application mapping | Easy with `String`; `UUID` mapping depends on provider | Requires consistent `UUID`/byte mapping |
| External integration | Usually simpler | Requires agreed byte order and encode/decode rules |

MySQL provides conversion functions:

```sql
SELECT UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db');
SELECT BIN_TO_UUID(UUID_TO_BIN('6ccd780c-baba-1026-9564-5b8c656024db'));
```

If using `UUID_TO_BIN(uuid, 1)` to swap the time fields of a version 1 UUID for better locality, use the matching `BIN_TO_UUID(value, 1)` on read. The `swap_flag=1` option is designed for UUID v1 layout; never apply it blindly to UUID v4 or UUID v7.

Example using MySQL-generated UUID v1:

```sql
INSERT INTO event_keys (id, description)
VALUES (UUID_TO_BIN(UUID(), 1), 'source event');
```

MySQL's `UUID()` generates UUID version 1. If UUIDs are generated in Java by another generator, confirm its version and byte layout and store consistently; never swap bytes in SQL while also swapping them in the application.

## 9. UUID v4, v7, and Index Locality

Not all UUIDs share the same ordering properties:

- **UUID v4:** most bits are random. Unpredictable and easy to generate independently, yet insert order scatters across the B-tree.
- **UUID v1:** embeds timestamp and node info; MySQL can rearrange time fields via `UUID_TO_BIN(..., 1)` to improve storage ordering. UUID v1 can leak creation time and node identity.
- **UUID v7:** places a Unix timestamp in the leading bits followed by random bits, yielding near-chronological order. Requires a generator supporting UUIDv7; do not assume every JDK/JPA provider emits v7 by default.

UUID v4 scatters clustered index inserts, causing page splits and hurting locality as tables grow. UUID v7 or time-ordered UUIDs improve locality, though they do not establish strict global commit order; multiple nodes with clock skew or identical timestamps can still produce out-of-order keys.

UUID v7 reveals approximate creation timestamps. If IDs are public and creation time is sensitive, evaluate that exposure. Nor do UUIDs replace authorization checks; endpoints must still verify that callers are allowed to view or modify a record.

Measure on real workloads: insert throughput, page splits, index size, buffer pool hit rate, and join performance. Never decide based solely on in-memory UUID generation microbenchmarks.

## 10. Primary Key Overhead Propagates to Foreign Keys and Secondary Indexes

InnoDB embeds the primary key in every secondary index to locate rows. On tables with many secondary indexes, switching the primary key from an 8-byte `BIGINT` to `CHAR(36)` enlarges all those indexes as well as child tables storing matching foreign keys.

For example, suppose `order_items` has three secondary indexes and a foreign key to `orders.id`. If `orders` uses a string UUID primary key, `order_items` stores that larger key on every row. At hundreds of millions of rows, the difference substantially affects disk usage, buffer pool efficiency, and I/O.

With UUIDs, consider:

- Using `BINARY(16)` if your application stack has stable byte mapping.
- Matching exact column type, signedness, and length on foreign key columns.
- Evaluating total index footprint, not just the primary key.
- Avoiding switching primary keys to UUIDs solely for unpredictability when a separate public ID suffices.
- Testing join performance and replication after changing key types.

## 11. Generate UUIDs in Java or MySQL?

UUIDs can be generated in the application or database. What matters is having a single ID source per entity and consistent formatting across all components.

Generate in Java prior to insert:

```java
UUID id = UUID.randomUUID();
```

Java's `UUID.randomUUID()` produces UUID version 4. This lets the application know the ID before calling `persist`, emit messages/events with consistent IDs, and avoid waiting for database-generated keys.

With JPA, you can use `GenerationType.UUID` for provider-side generation:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
private UUID id;
```

Or assign the ID manually and omit `@GeneratedValue`:

```java
@Id
@Column(nullable = false, updatable = false)
private UUID id;

public ExternalEvent() {
    this.id = UUID.randomUUID();
}
```

These are two distinct ownership models. If the application assigns IDs manually, do not simultaneously configure the provider to generate IDs for the same field. If using a custom generator for UUIDv7, configure it explicitly and test uniqueness, ordering, and compatibility.

Generating UUIDs in MySQL with `UUID()` works in plain SQL or ETL pipelines. However, if Hibernate manages the entity, avoid letting the database auto-generate values when JPA mappings assume the provider already knows the ID before insert, unless appropriate generated-column/key-retrieval handling is configured.

## 12. Batching and Throughput When Choosing a Generator

A practical difference between IDENTITY and UUID is when the ID becomes known:

| Strategy | When ID Is Known | Impact on Insert Batching |
|---|---|---|
| `IDENTITY` | After MySQL executes the insert | Hibernate typically disables JDBC insert batching for `IDENTITY` entities because it needs the generated key |
| Application/provider-generated UUID | Before insert | Inserts can be batched if other Hibernate/JDBC conditions allow |
| `TABLE` generator | After fetching/allocating a range from generator table | Can pre-allocate IDs via `allocationSize`; incurs generator synchronization cost |
| Pre-assigned ID from service/segment | Before insert | Supports batching; requires collision-free, operationally sound allocation |

UUIDs do not automatically make an application faster. Random UUIDs can inflate index and storage costs. Any batching gains can be offset if the table has many indexes, transactions are oversized, or disk I/O bottlenecks.

With Hibernate, verify batching settings and emitted SQL. Example:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

These properties are configuration hints; actual batching depends on generator, dialect, driver, transactions, and entity mappings. `IDENTITY` retains its batching limitation, so setting `hibernate.jdbc.batch_size` alone will not batch identity inserts.

## 13. Choosing a Strategy by Use Case

| Context | Suitable Option | Rationale and Conditions |
|---|---|---|
| CRUD with single MySQL primary, standard transactional tables | `IDENTITY` + `BIGINT AUTO_INCREMENT` | Simple, compact keys, good locality; accept batching limitation |
| High-volume imports requiring batch inserts | Pre-generated UUID or block-allocated IDs | ID known before insert; evaluate index and generator costs |
| Multiple services/nodes creating records offline | UUID or distributed ID | No central counter round-trip at creation time |
| Compact, roughly time-ordered IDs | Single-source `BIGINT` or UUIDv7 | Account for clock skew, multi-writer effects, and timestamp exposure |
| Table needs unpredictable public ID | Separate public UUID; internal PK stays `BIGINT` | Decouples API identifier from internal join keys |
| Multi-database portability | `AUTO` or JPA/provider-supported generator | Verify chosen generator and DDL per dialect |

An often effective pattern is keeping `BIGINT AUTO_INCREMENT` as the internal primary key for compact joins/indexes while adding a `public_id BINARY(16)` or `CHAR(36)` column with a unique index for public APIs. This adds one column and one index, yet avoids bloating every foreign key with a large UUID. Evaluate the trade-off against your workload and API needs.

## 14. Migrating from AUTO_INCREMENT to UUID

Changing the primary key of a live system is a major migration because the primary key appears in secondary indexes, foreign keys, caches, messages, URLs, and application code. Never alter the column type across an entire large table in one blocking operation.

An expand-and-contract workflow can look like this:

1. Add a new nullable UUID column to the parent table and referencing child tables.
2. Deploy code compatible with both numeric keys and UUIDs; establish a single UUID generation source.
3. Backfill UUIDs in chunks with checkpoints, and create unique indexes after verifying uniqueness.
4. Keep UUIDs populated on new records during the transition via application code or tested database mechanisms.
5. Backfill matching UUID foreign keys in child tables; verify all relationships and check for orphans.
6. Cut over reads/writes service by service while monitoring join, lookup, messaging, and API errors.
7. Only after every consumer has migrated should you consider swapping foreign keys/primary keys and removing legacy compatibility paths.

Data verification queries:

```sql
SELECT COUNT(*) AS missing_public_id
FROM orders
WHERE public_id IS NULL;

SELECT public_id, COUNT(*) AS occurrences
FROM orders
WHERE public_id IS NOT NULL
GROUP BY public_id
HAVING COUNT(*) > 1;
```

Before swapping foreign keys, reconcile parent/child row counts, detect orphans, and verify every old ID maps to exactly one new ID. DDL creating indexes or altering primary keys can rebuild tables and spike replication lag; plan capacity, locking, and maintenance windows separately.

## 15. Testing and Post-Deployment Observability

Generator testing must confirm both correctness and performance:

- Create entities concurrently across multiple threads and instances; verify zero ID collisions.
- Confirm whether IDs are populated on entities before or after `persist`/`flush` per strategy.
- Verify `getGeneratedKeys` or JPA entity IDs after insert with the exact production driver.
- Measure SQL statement counts, network round-trips, and actual batch sizes.
- Measure insert throughput, primary/secondary index sizes, page splits, and buffer pool metrics.
- Test foreign keys and joins when using UUIDs.
- For multi-writer setups, test failover and node restarts to confirm no duplicate IDs are issued.
- For time-ordered UUIDs, test clock skew and simultaneous generation across nodes.

In Hibernate, enable SQL logging in staging or use a datasource proxy/APM to observe insert statements. Avoid logging bind parameters containing sensitive data in production. Use Performance Schema and `information_schema.tables` to track table/index growth alongside application-level insert and transaction latency.

## 16. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Hibernate fails to retrieve ID after insert | Generator mapping mismatches DDL or driver does not return generated keys as expected | Check annotations, DDL, dialect, and Connector/J; test insert/flush in staging |
| Bulk inserts slow despite batching enabled | Entity uses `IDENTITY`, overly frequent flushes, or broken batches | Inspect actual SQL; consider pre-generated UUIDs or pre-allocated generators if appropriate |
| `AUTO` creates an unexpected generator table | Provider/dialect selected a different strategy than assumed | Check DDL and Hibernate logs; declare an explicit strategy if needed |
| Duplicate keys in multi-writer topology | Nodes share overlapping `AUTO_INCREMENT` ranges or custom ID algorithm collides | Verify topology; partition ranges properly or use UUID/distributed IDs |
| UUID inserts slow and indexes bloated | Random UUIDs, `CHAR(36)`, and multiple secondary indexes | Benchmark `BINARY(16)` or locality-friendly UUIDs; evaluate a separate public ID |
| UUID unreadable after binary storage | Inconsistent byte order or swap flag | Standardize encode/decode; apply the exact same swap flag to both `UUID_TO_BIN` and `BIN_TO_UUID` |
| Foreign key creation fails | Mismatched column type, signedness, or length between parent and child | Align column definitions and verify indexes/storage engine |
| Gaps in ID sequence | Rollbacks, deletes, or failed inserts | Accept gaps with `AUTO_INCREMENT`; build a dedicated sequence allocator if business requires gap-free numbers |

## 17. Practice Scenario

An e-commerce Spring Boot application currently uses `Long` with `GenerationType.IDENTITY`. The system begins importing hundreds of thousands of events from multiple sources, and the team wants to generate IDs before insert to batch writes and publish messages in the same transaction.

**Step 1 — Measure the baseline.** Record current insert throughput, SQL statement counts, flush duration, index sizes, and replication lag. Confirm that `IDENTITY` prevents Hibernate from batching inserts for the imported entity.

**Step 2 — Scope the change.** Do not change the primary key of `orders` immediately. Pilot on an independent `external_events` table where UUIDs naturally identify multi-source events.

**Step 3 — Choose representation.** Generate `UUID` in the application/provider. Compare readable `CHAR(36)` against compact `BINARY(16)`; confirm Hibernate mappings and byte order.

**Step 4 — Configure batching.** Set an appropriate batch size and `order_inserts`, then inspect SQL logs to verify JDBC batching is actually occurring. Re-benchmark with comparable data volume and indexes.

**Step 5 — Test multi-instance concurrency.** Run multiple workers creating events concurrently; verify zero ID collisions, idempotent message retries without duplicates, and unique constraints protecting integrity.

**Step 6 — Reconcile performance.** Compare throughput, p95 insert latency, index footprint, page splits, and replication lag. Expand further only if batching gains outweigh UUID overhead and results stay stable.

## 18. Pre-Selection Checklist

- [ ] Writer count, topology, and ID generation location identified.
- [ ] Internal primary key distinguished from public/business identifiers.
- [ ] `IDENTITY`, `UUID`, `TABLE`, `AUTO`, or manual ID chosen for explicit requirements.
- [ ] Actual `GenerationType.AUTO` behavior verified against your Hibernate version and MySQL dialect.
- [ ] `IDENTITY` limitation on Hibernate JDBC insert batching accounted for.
- [ ] Determined whether IDs must be known prior to insert.
- [ ] If using UUIDs, version, `CHAR(36)`/`BINARY(16)` representation, and byte order standardized.
- [ ] If using `UUID_TO_BIN(..., 1)`, applied strictly to UUID v1 layout with matching decode flag.
- [ ] Data types and signedness aligned across primary keys and foreign keys.
- [ ] Concurrent ID generation tested across multiple threads/nodes and retry paths.
- [ ] Batching, insert throughput, index size, and replication lag measured.
- [ ] Migration/backfill plan prepared if changing strategies on a live table.

`IDENTITY` and `AUTO_INCREMENT` remain simple, compact defaults for many Spring Boot applications on a single MySQL primary. UUIDs fit when IDs must be generated independently across nodes or prior to database writes, provided index size and locality trade-offs are evaluated. `AUTO` depends on the JPA provider and dialect; `TABLE` generators carry their own synchronization cost. Choosing a generator based on write patterns, topology, batching needs, and how keys propagate across relationships preserves uniqueness without unexpected storage or operational overhead.
