# Repositories, Derived Queries, `@Query`, and Expressiveness Limits in Spring Boot + Spring Data Cassandra

## 1. Objectives and Context

Apache Cassandra is a distributed **wide-column** database: data is placed onto replicas by **partition key**, rows within a partition are sorted by **clustering key**, and coordinators execute CQL queries according to the chosen **consistency level** (CL). Table design must flow from **actual queries**, not from relational normalization habits and ad-hoc querying.

When building Java apps with **Spring Boot and Spring Data Cassandra**, you can declare a repository interface and let the framework derive many queries from method names. This cuts boilerplate, yet **does not turn Cassandra into a relational database**: if a method name filters on a column lacking a valid access path, the query can be rejected by the server or consume excessive resources.

This lesson belongs to the **Spring Boot and Spring Data** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, focusing on:

1. Distinguishing `CassandraRepository`, **derived queries**, `@Query`, `CassandraTemplate`, and the Java Driver.
2. Mapping **composite primary keys** accurately between CQL and Java.
3. Knowing when `findBy...` method names suffice and when they fall short.
4. Using `@Query` to control projections, partition/clustering predicates, and `LIMIT`.
5. Explaining **CQL's limits**: no arbitrary JOINs, no SQL-like arbitrary `WHERE`/`ORDER BY`, no traditional `OFFSET` paging.
6. Controlling pagination, RF/CL, token routing, TTL, LWT, and replica load.
7. Testing generated CQL, monitoring latency/errors, and handling schema evolution.
8. Knowing when to switch to **`CassandraTemplate`, `CqlTemplate`, or `CqlSession`**.

**Version scope:** illustrative code targets Spring Boot **3.x / Spring Data Cassandra 4.x** and Java Driver 4.x managed via compatible dependencies/BOM. Never copy properties or annotations to Boot 2.x/Driver 3.x without checking the docs for that exact version pair. Do not infer exact supported combinations or "latest" numbers from the label "4.x" alone.

## 2. Application Working Layers

~~~mermaid
flowchart LR
    A["REST / Service"] --> B["Spring Data Repository"]
    B --> C["Spring Data Cassandra mapping / query creation"]
    C --> D["Java Driver CqlSession"]
    D --> E["Cassandra Coordinator"]
    E --> F["Replicas per token, RF, CL"]
    G["CassandraTemplate / CqlTemplate"] --> D
    H["Explicit @Query CQL"] --> C
~~~

| Layer | Role | Limits |
|---|---|---|
| **Spring Boot auto-configuration** | Configures connectivity, beans, and integrations per starter/version | Does not choose schemas or good partition keys |
| **`CassandraRepository<T,ID>`** | CRUD, query methods, entity mapping | Generic CRUD can be expensive or unsuitable for wide-column tables |
| **Derived queries** | Parses `findBy...` names into query predicates | Constrained by CQL and mapping metadata |
| **`@Query`** | Explicit CQL attached to a repository method | Must still obey partition key/CL/query constraints |
| **`CassandraTemplate`** | Lower-level query and object-mapping API than repositories | Requires active query design and resource control |
| **`CqlTemplate` / `CqlSession`** | Closer to CQL transport and statements | More code and manual mapping/paging/timeout decisions |
| **Cassandra cluster** | Hashes partition keys, places replicas, runs compaction/repair, enforces CL | Has no knowledge of Java repository method names |

**Key relationship:** Spring Data Repositories are a *way to invoke CQL*, not a *way to bypass CQL constraints*.

## 3. Lesson Data Model: Device Readings by Day

### 3.1. CQL Schema for Real Queries

Suppose the app reads a device's measurement history for one day, newest first:

~~~cql
-- Use only on a LAB CLUSTER with datacenter dc1 and enough replicas.
CREATE KEYSPACE telemetry_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_lab.readings_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    reading_value double,
    status text,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

In this table:

- The partition key is **`(device_id, event_day)`**. Both values together identify a logical partition.
- The clustering key is **`event_time`**, sorting rows inside a partition newest-first.
- The full primary key has **three** columns; identifying a row differs from identifying a partition.
- `reading_value` and `status` are regular columns; they **do not become arbitrary filters** without a designed index/access path.
- `NetworkTopologyStrategy` and RF=3 are lab examples; production topologies need dedicated RF/DC/rack sizing.

### 3.2. Expected Queries

| Need | Valid CQL on This Schema? | Notes |
|---|---|---|
| Fetch row for specific device/day/time | **Yes** | Full primary key supplied |
| Fetch rows for a device on one day | **Yes** | Full partition key supplied |
| Fetch 20 newest rows for device/day | **Yes** | `DESC` clustering order and `LIMIT` |
| Fetch rows in an `event_time` window for device/day | **Yes** | Clustering range inside a partition |
| Find all rows where `status = 'ALERT'` | **Not directly** | Missing partition key/access path; needs a suitable model/index |
| Find all active devices across 7 days | **Not via one point query** | Needs a query-driven table, bounded fan-out, or pipeline |
| Sort entire table by `reading_value DESC` | **Not like standard SQL** | CQL `ORDER BY` depends on schema clustering and partition |
| JOIN device table with readings table | **No server-side SQL JOIN** | Denormalization, app composition, or query-specific tables |

**Every repository example must be evaluated by its real CQL**, not just by how plausible the Java method name sounds.

### 3.3. Sample Data

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:30:00Z',
    24.6,
    'OK'
);

INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21',
    '2026-11-21T10:29:00Z',
    24.1,
    'OK'
);
~~~

Examples use fixed lab UUIDs and timestamps; never auto-create tables or run automatic DDL on production Spring Boot startup.

## 4. Safe, Version-Aligned Spring Boot Configuration

### 4.1. Dependencies via BOM

With Spring Boot, normally pick the Cassandra starter and **let the Spring Boot BOM manage compatible versions**:

~~~xml
<!-- pom.xml excerpt for a compatible Spring Boot project. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
</dependency>
~~~

Do not arbitrarily pin separate Spring Data, Cassandra Driver, and Spring Boot versions without verifying a compatibility matrix. With **reactive repositories**, starters/APIs differ; never confuse `ReactiveCassandraRepository` with `CassandraRepository` merely because both hit the same cluster.

### 4.2. Illustrative `application.yml`

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1:9042
    local-datacenter: dc1
    keyspace-name: telemetry_lab
    schema-action: NONE
~~~

These properties illustrate modern Spring Boot lines using the `spring.cassandra.*` namespace. Older lines may use `spring.data.cassandra.*`; **check configuration metadata for your actual Boot version**.

- `contact-points` let the driver bootstrap/discover the cluster; not every request goes there.
- `local-datacenter` must match the real DC discovered by the driver.
- `keyspace-name` sets the default keyspace for queries lacking fully qualified names.
- `schema-action: NONE` prevents auto-creating or altering production schemas at startup; DBAs/migration tools manage DDL separately.
- Auth, TLS, secrets, and timeout settings must come from managed configuration; **never commit passwords, private keys, or tokens** to Git.

### 4.3. Connectivity Does Not Replace Data Modeling

An app can start cleanly, create repository beans, and report health UP, yet:

- An unexercised derived method can fail when it finally emits CQL.
- The table may be missing or differ in schema on the target cluster.
- `findAll()` can scan many partitions expensively.
- Queries hitting a hot partition can time out despite a healthy pool.
- RF/CL/topology can breach SLOs when a replica goes down.

**Smoke tests must execute real query shapes**, not just check that TCP 9042 is open.

## 5. Mapping Composite Keys with `@PrimaryKeyClass` and `@PrimaryKeyColumn`

### 5.1. The Composite Key Is a Value Object

Spring Data Cassandra commonly maps composite keys using a class annotated with `@PrimaryKeyClass`, individual `@PrimaryKeyColumn` fields, and `@PrimaryKey` on the entity.

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

@PrimaryKeyClass
public class ReadingKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "device_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "event_day",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate eventDay;

    @PrimaryKeyColumn(
        name = "event_time",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant eventTime;

    public ReadingKey() {}

    public ReadingKey(UUID deviceId, LocalDate eventDay,
                      Instant eventTime) {
        this.deviceId = Objects.requireNonNull(deviceId);
        this.eventDay = Objects.requireNonNull(eventDay);
        this.eventTime = Objects.requireNonNull(eventTime);
    }

    public UUID getDeviceId() { return deviceId; }
    public void setDeviceId(UUID value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof ReadingKey other)) return false;
        return Objects.equals(deviceId, other.deviceId)
            && Objects.equals(eventDay, other.eventDay)
            && Objects.equals(eventTime, other.eventTime);
    }

    @Override
    public int hashCode() {
        return Objects.hash(deviceId, eventDay, eventTime);
    }
}
~~~

This example uses Java 16+ `instanceof ... other`; on older JDKs, use traditional Java casting. Choose your JDK per the **Spring Boot/Driver support matrix**, never upgrading JDK blindly for a snippet.

### 5.2. Why Do `ordinal` and `type` Matter?

- `PrimaryKeyType.PARTITIONED` places **`device_id`** and **`event_day`** in the partition key.
- `PrimaryKeyType.CLUSTERED` places **`event_time`** in the clustering key.
- `ordinal` and `Ordering.DESCENDING` must match the **CQL definition**.
- Java `UUID` / `LocalDate` / `Instant` must match CQL `uuid` / `date` / `timestamp`.
- `equals/hashCode` must align with key values so DTOs and domain structures behave consistently.

**A mistake in primary key annotations can emit invalid CQL or corrupt mapping**, even though the Java class compiles. Always verify against the schema and integration-test on a compatible cluster.

### 5.3. Entity Mapping

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("readings_by_device_day")
public class Reading {

    @PrimaryKey
    private ReadingKey key;

    @Column("reading_value")
    private Double readingValue;

    @Column("status")
    private String status;

    public Reading() {}

    public Reading(ReadingKey key, Double readingValue, String status) {
        this.key = key;
        this.readingValue = readingValue;
        this.status = status;
    }

    public ReadingKey getKey() { return key; }
    public void setKey(ReadingKey value) { key = value; }

    public Double getReadingValue() { return readingValue; }
    public void setReadingValue(Double value) { readingValue = value; }

    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
}
~~~

Use boxed `Double` for nullable measurements to distinguish **absent value** from `0.0`. Not every field is necessarily written on every historical row.

### 5.4. The Key for `findById` Is the **Full Primary Key**

~~~java
ReadingKey key = new ReadingKey(deviceId, day, eventTime);
Optional<Reading> found = repository.findById(key);
~~~

`findById(key)` fetches **one row matching all three primary key components**; it does not fetch every row in a day's partition. If an API needs "the 20 newest values", write a query by `device_id` and `event_day` with `LIMIT 20`.

## 6. `CassandraRepository`: Convenient CRUD, Still Must Know Costs

### 6.1. Repository Interface

~~~java
package demo.telemetry;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {
}
~~~

Through Spring Data, the repository exposes operations like `save`, `findById`, `existsById`, `deleteById`, and `findAll` (depending on superinterface and version).

Yet **an API existing does not mean calling it on a large table is reasonable**.

| Method | Appropriate When | Risks to Remember |
|---|---|---|
| `save(entity)` | Writing a row with a known primary key | Cassandra upsert, timestamp/TTL/null semantics |
| `findById(fullKey)` | Fetching one exact row | Must supply **all** partition + clustering keys |
| `existsById(fullKey)` | Checking presence of a specific row | Incurs read cost; not a uniqueness transaction |
| `deleteById(fullKey)` | Deleting one row by full ID | Tombstones, `gc_grace_seconds`, and concurrent writes |
| `findAll()` | Only tiny datasets / isolated tests | Can scan broadly across many partitions |
| `count()` | Small tables or controlled offline batches | Not a cheap cluster-wide row count |
| `deleteAll()` | Controlled admin/lab resets | Dangerous; generates huge mutations/tombstones |

Never use `findAll().stream().filter(...)` in place of a Cassandra `WHERE` clause. Data gets shipped to the client before filtering, OOMing the API and hitting replicas with full scans.

### 6.2. `save` Is Not a Multi-Table SQL Transaction

In Cassandra, `save` is typically a primary-key mutation/upsert. It does not guarantee:

- Atomic transactions across multiple partitions or tables like an RDBMS.
- Uniqueness constraints on regular columns.
- Snapshot isolation across sequential repository calls.
- Default CAS/LWT on every mutation.
- "A timeout means the mutation definitely did not apply."

When conditional business logic is needed, design **conditional writes/LWTs or versioning/invariants** explicitly and measure latency. Repository abstractions never invent distributed consensus outside Cassandra.

### 6.3. Why Does Key Design Dictate Repository Design?

For `PRIMARY KEY ((device_id, event_day), event_time)`:

- `findById` is a full-row lookup.
- Querying by `device_id + event_day` is a partition lookup.
- Querying by `device_id` alone **cannot locate a single partition**.
- Querying by `status` needs another access path; adding `findByStatus` in Java does not magically give Cassandra an index.

Designing repository interfaces **after** modeling queries is the right workflow — not writing a hundred `findBy...` methods and trying to force the schema to keep up.

## 7. Derived Queries: From Method Name to CQL

### 7.1. Principles

Spring Data parses names like `findByKeyDeviceIdAndKeyEventDay` into **property paths** on the entity and constructs queries for expressions supported by the Cassandra module.

Example:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {

    // Uses nested property paths inside the "key" field.
    // Illustrative on small partitions / labs only; unbounded result set.
    List<Reading> findByKeyDeviceIdAndKeyEventDay(
        UUID deviceId, LocalDate eventDay);
}
~~~

Intended CQL equivalent:

~~~cql
-- Target equivalent CQL form:
SELECT *
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?;
~~~

**Method names and nested property syntax must be verified with integration tests on your real Spring Data version.** If the parser fails to resolve property paths or emitted CQL mismatches key layout, use explicit `@Query` instead of guessing.

### 7.2. Long Method Names Do Not Make Queries Cheap

The method above can read **every row in the daily partition**. If a device logs a million readings per day, `List<Reading>` consumes huge memory even though it hits a single partition.

Derived queries do not know your API only wants 20 rows. Consider `@Query` with `LIMIT` or supported Cassandra pagination.

### 7.3. Distinguish Property Paths from CQL Column Names

In the Java entity:

- `Reading.key.deviceId` → CQL column `device_id`.
- `Reading.key.eventDay` → `event_day`.
- `Reading.key.eventTime` → `event_time`.
- `Reading.readingValue` → `reading_value`.

Derived method names use **Java property names**, not raw CQL snake_case like `findByDevice_id` in the signature. Mapping annotations determine the actual column names.

If property paths collide or the parser splits nested segments ambiguously, use your Spring Data version's nested-path syntax or switch to `@Query` to eliminate ambiguity.

### 7.4. Always Test Generated CQL

Never conclude a derived method works just because the project compiles:

1. Does the repository bean initialize cleanly?
2. Does invoking the method emit valid CQL?
3. Does the CQL include the **full partition key** and proper clustering order?
4. Is the query paginated/row-bounded?
5. What are the latency and real row counts on large partitions?
6. Did the server require `ALLOW FILTERING`?
7. Do results uphold the intended RF/CL guarantees?

**Runtime failures** when invoking methods must be caught via integration tests and safe logs, not mocked repository unit tests alone.

## 8. `@Query`: Expressing CQL More Clearly Than Method Names

### 8.1. Bounding to 20 Rows on the Server

~~~java
import org.springframework.data.cassandra.repository.Query;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {

    @Query(
        "SELECT device_id, event_day, event_time, " +
        "reading_value, status " +
        "FROM readings_by_device_day " +
        "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
    List<Reading> findLatest20(UUID deviceId, LocalDate eventDay);
}
~~~

Here:

- `?0` and `?1` are **Spring Data Cassandra positional bind parameters** inside `@Query` for versions supporting this syntax.
- They must match `UUID` and `LocalDate` types accurately.
- The CQL supplies the complete partition key and **`LIMIT 20`**.
- Because the table clusters by `event_time DESC`, rows inside the partition come back in that declared order.
- The projection selects all key columns and mapped fields needed to materialize `Reading`.

**Never interpolate `deviceId`/`day` into query strings.** Always use bind parameters; raw interpolation creates CQL injection risk and forfeits prepared-statement/routing reuse.

### 8.2. Range on the Clustering Key

~~~java
import java.time.Instant;

@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status " +
    "FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 " +
    "AND event_time < ?2 LIMIT 50")
List<Reading> before(
    UUID deviceId, LocalDate day, Instant exclusiveBefore);
~~~

Equivalent CQL query:

~~~cql
SELECT device_id, event_day, event_time, reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
  AND event_time < ?
LIMIT 50;
~~~

`event_time` is a clustering column; range restrictions inside a **known partition** fit this model cleanly. In tables with multiple clustering columns, CQL range restrictions follow stricter prefix rules; never assume ranges work on arbitrary columns.

### 8.3. `@Query` Does Not Bypass the CQL Server

Switching from a derived query to:

~~~java
// ANTI-PATTERN: explicit @Query, still wrong query shape.
@Query("SELECT * FROM readings_by_device_day WHERE status = ?0")
List<Reading> findAllAlerts(String status);
~~~

**does not make the query valid or efficient** merely because it uses a Java annotation. Cassandra still demands a partition key or a properly designed and verified access path. `ALLOW FILTERING` is not a default fix: it can trigger wide scans and timeouts.

### 8.4. Why Not Default to `SELECT *`?

- Pulls unused fields onto the network and heap.
- Couples mapping to schema evolution; newly added columns may be null on older rows.
- Large collections/blobs/UDTs bloat responses.
- Obscures which query contracts actually depend on which columns.
- Increases serialization cost, GC pressure, and total paged bytes.

Prefer explicit projections for APIs with stable DTO contracts. When entity mapping requires primary keys and other columns, select **only the needed columns**.

## 9. Nature of Expressiveness Limits: Spring Data Does Not Turn CQL into SQL

### 9.1. `WHERE` Predicates Must Match Keys

| Java Need | Does CQL Have an Execution Path? | Right Solution |
|---|---|---|
| `deviceId = ? AND eventDay = ?` | Yes, single partition | Derived query or `@Query` |
| `deviceId = ? AND eventDay = ? AND eventTime < ?` | Yes, clustering range | `@Query` / derived if operator supported |
| Only `deviceId` | Incomplete partition key on this table | Query-specific table, adjust access pattern |
| Only `status` | Missing partition key | Status-keyed table or evaluated index |
| `status = 'ALERT' OR status = 'WARN'` | No arbitrary SQL `OR` | Query-driven table/index/aggregation |
| JOIN two Cassandra tables | Not a CQL capability | Denormalize / compose in app layer |
| Global sort by `reading_value` | Incompatible with clustering order | Separate table or analytics/index/search |
| `OFFSET 1,000,000` | No server-side SQL `OFFSET` | Paging state or keyset/partition design |
| Continuous full-table `COUNT` | Very expensive | Counter/summary table/metrics with clear semantics |

**A verbose derived method like `findByStatusOrReadingValueGreaterThan` does not make Cassandra build an RDBMS query plan.** Check which operators Spring Data Cassandra actually supports in your version; even parser-accepted queries must still obey key restrictions.

### 9.2. `ORDER BY` Is Bound by Clustering Columns

The example table stores `event_time DESC` per partition, making newest-first reads natural. Yet you cannot pass `Sort.by("status")` expecting the framework to sort **cluster-wide** on the server.

If an API needs "top 100 devices with highest readings system-wide", build a **dedicated query-driven table or aggregation/analytics pipeline**. A Java `Sort` object does not create a global sort index.

### 9.3. Adding Indexes Does Not Rescue Every Derived Query

Index types (e.g., secondary indexes, SAI where supported) have distinct trade-offs around data shape, queries, write amplification, and cluster load. Never:

1. Write `findByStatus` without a partition key.
2. Hit an error.
3. Slap an index onto `status` in production.
4. Assume the query scales cleanly to billions of rows.

Evaluate **cardinality, selectivity, data distribution, RF/DC, query fan-out, index build/maintenance, compaction**, and Cassandra version before deciding. For fixed business lookups, a query-driven denormalized table is often far more predictable.

## 10. Pagination: `Pageable` Is Not SQL `OFFSET`

### 10.1. Why Does Cassandra Paging Differ from RDBMS?

Cassandra uses continuation/state-based paging rather than random offsets across a cluster-wide dataset. An API like:

~~~text
GET /readings?device=...&day=...&page=500000
~~~

does not mean Cassandra can skip 500,000 pages cheaply. In Spring Data Cassandra:

- `Pageable` and `Slice` may be supported depending on version and query type.
- Continuation relies on **paging state**, not SQL `OFFSET`.
- Never assume jumping directly to arbitrary page N is cheap or valid.
- Verify exact support for sorting, paging state, and mapping in your driver version.
- `Page` normally expects a total count; Cassandra cannot count vast datasets cheaply like some RDBMSs. `Slice` fits "is there a next page" much better.

### 10.2. Repository Pattern Using `Slice`

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

Slice<Reading> findByKeyDeviceIdAndKeyEventDay(
    UUID deviceId,
    LocalDate day,
    Pageable pageable);
~~~

This illustrates an interface for Spring Data Cassandra versions **supporting `Slice`/paging accordingly**. Check `CassandraPageRequest` or your version's paging token API to fetch the **next page**; never pass `PageRequest.of(1000, 20)` expecting SQL-style offset skipping.

### 10.3. `LIMIT` and Fetch Size Serve Two Different Purposes

~~~text
CQL LIMIT 20:
    Caps the total rows a query can return.

Page / fetch size = 20:
    Target rows per protocol page;
    DOES NOT cap total query rows if LIMIT is absent.
~~~

Even with small pages, a query scanning a wide partition or heavy tombstones can overload servers. Page size does not replace query modeling.

### 10.4. Never Expose Raw Paging State Everywhere

Paging state can leak sensitive query positioning details. When exposing it as an API cursor:

- Bind the cursor to the query shape/partition/filters.
- Add expiration/versioning and integrity protection if sent to untrusted clients.
- Never log raw paging tokens like request IDs.
- Never treat paging state as a **transactional snapshot** while rows mutate between pages.
- Never assume old tokens stay compatible indefinitely across driver/schema upgrades.

## 11. Optimizing Repository Queries Starts with the Partition Key

### 11.1. Good Predicate

~~~cql
SELECT device_id, event_day, event_time,
       reading_value, status
FROM telemetry_lab.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

The driver derives a routing key from the full partition key and prepared statement metadata. Coordinators typically prefer eligible local-DC replicas per load balancing, though extra network hops are not strictly eliminated in all cases.

### 11.2. Predicate Causing a Scan

~~~cql
-- Unsuitable for the demo table without another access path.
SELECT * FROM telemetry_lab.readings_by_device_day
WHERE status = 'OK';
~~~

Cassandra rejects it or requires another access path. Never add `ALLOW FILTERING` to paper over a design gap; at scale, server scan CPU/I/O dwarfs any Java micro-optimization.

### 11.3. Wide Partitions Are Expensive Even with Proper Routing

One day for a single device can hold millions of rows. A query "with the full partition key" can still:

- Touch many SSTables before compaction.
- Scan numerous tombstones / expired TTL cells.
- Generate many pages, response bytes, and client allocations.
- Amplify load on that exact replica set under retries.

Typical fixes are **smaller buckets, bounded time windows, `LIMIT`, retention/TTL tuning, and load testing** — not merely swapping `List` for `Slice`.

## 12. When Is `CassandraTemplate` Needed Instead of a Repository?

### 12.1. Decision Path

~~~mermaid
flowchart TD
    A["Cassandra read/write use case"] --> B{"Simple query, valid key?"}
    B -->|Yes| C["CassandraRepository + derived query"]
    B -->|Moderately custom| D["Repository with explicit @Query CQL"]
    B -->|Controlled dynamic options/logic| E["CassandraTemplate / CqlTemplate"]
    E --> F{"Need driver-level execution detail?"}
    F -->|Yes| G["CqlSession prepared/bound statement"]
    F -->|No| H["Spring mapping/template"]
    C --> I["Integration test CQL + replica load"]
    D --> I
    G --> I
    H --> I
~~~

Repositories and templates are not separate database engines; both talk to Cassandra via the driver and must obey CQL.

### 12.2. When Templates Shine

- Dynamic queries within a **controlled allowlist**.
- Statement/result options that do not map cleanly to repository method signatures.
- Multi-step query logic paired with dedicated object mapping.
- Token-range reads for throttled, checkpointed batch jobs.
- Reusing mapping layers without writing hundreds of long derived method names.
- Reads/writes with explicit version-verified TTL/timestamp/conditional options.

Still, **templates do not add JOINs or global `ORDER BY` to CQL**. If a query mismatches the schema, **change the table/data flow**, not just the Java API.

### 12.3. When Direct `CqlSession` Is Needed

A Java Driver 4.x example:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import java.time.LocalDate;
import java.util.UUID;

public final class ReadingCqlGateway {
    private final CqlSession session;
    private final PreparedStatement latest;

    public ReadingCqlGateway(CqlSession session) {
        this.session = session;
        this.latest = session.prepare(
            "SELECT event_time, reading_value, status " +
            "FROM telemetry_lab.readings_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 20"
        );
    }

    public ResultSet fetch(UUID deviceId, LocalDate day) {
        BoundStatement bound = latest.bind(deviceId, day)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(20);
        return session.execute(bound);
    }
}
~~~

**`CqlSession`** grants direct control over statements, CL, page size, and execution info. Never let controllers pass raw user input into CQL strings; `PreparedStatement` + typed bind values is the safe default.

When using the driver directly, the app owns `Row` mapping, null handling, paging, and retry semantics. Spring repositories handle some of that boilerplate, yet query cost does not disappear.

## 13. `@Query`, Bind Parameters, and Dynamic Identifiers

### 13.1. Bound Values Differ from Table or Column Names

Safe `@Query` usage binds **data values**:

~~~java
@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status " +
    "FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
List<Reading> findLatest20(UUID deviceId, LocalDate day);
~~~

`device_id`, `event_day`, and `readings_by_device_day` are **fixed CQL identifiers** in the query template. `?0` and `?1` are bound values.

Never use bind parameters to swap **table names, keyspaces, columns, or `ORDER BY` clauses**:

~~~text
CQL identifier:
    table_name, column_name, keyspace, ORDER BY column

CQL value:
    UUID, LocalDate, Instant, number, text

Bind parameters apply to VALUES per supported syntax;
never treat table/column names as bound values.
~~~

If an app uses separate tables per tenant or product type, **never** read a table name from an HTTP query parameter and concatenate it into CQL.

### 13.2. When Selecting Among a Few Allowed Tables Is Mandatory

Instead of concatenating raw input, use a reviewed **structural allowlist**:

~~~java
public enum ReadingView {
    BY_DEVICE_DAY,
    BY_ALERT_DAY
}
~~~

In the data-access layer, map each enum constant to a **fixed CQL template** and matching repository/gateway. Never construct `@Query` with an arbitrary table name from untrusted input.

If tables vary by tenant, evaluate **multi-tenant isolation, RBAC, connection/session lifecycle, and schema-object counts**. Never treat a regex check on table names as sufficient access control.

### 13.3. `@Query` Does Not Turn Spring Data into a SQL ORM

Never write:

~~~java
// NOT a way to get a global sort in Cassandra.
@Query(
    "SELECT * FROM readings_by_device_day " +
    "WHERE reading_value > ?0 ORDER BY status ASC")
List<Reading> globalSort(double threshold);
~~~

CQL does not support arbitrary SQL-like queries on this sample table. `@Query` submits CQL; the server still enforces Cassandra partition/clustering/index rules.

### 13.4. Avoid Concatenating Raw CQL at Runtime

`@Query` annotations hold static text. If you need dynamic optional predicates, consider:

- A few named query templates per supported access pattern.
- `CassandraTemplate` building predicates strictly from an allowed set.
- `CqlSession` prepared statements for fixed query shapes.
- Dedicated tables/indexes for new access patterns.

Never fall back to string concatenation just because a derived method name got long or `@Query` felt rigid. That usually solves the wrong problem — **the CQL data model**, not Java syntax.

## 14. CRUD Mutations, TTL, and Write Timestamps

### 14.1. `save` by Full Primary Key Is an Upsert

~~~java
ReadingKey key =
    new ReadingKey(deviceId, day, eventTime);

Reading reading = new Reading(key, 24.6, "OK");
repository.save(reading);
~~~

Writing the same key uses Cassandra mutation timestamps and reconciliation rules. It does not operate like a JPA entity manager with **dirty checking, transactional context, and automatic rollback**.

Specifically:

- Two writes to the same primary key **overwrite/merge cells** by timestamp.
- Null fields follow your version's mapping/write-options strategy; never assume all nulls are "ignored" or "deleted" without testing.
- Saving to two tables via two `save` calls is not a multi-table ACID transaction.
- A timeout does not prove the mutation was not applied.
- Retrying writes is safe only after evaluating **idempotency**.

### 14.2. TTL Belongs to Mutations, Not Auto-Generated by Repositories

Example CQL:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
USING TTL 86400;
~~~

The `86400`-second TTL here is **one day**, not a default setting. If data needs 30-day retention, enforce a deliberate policy. TTL affects row/cell expiration, tombstones, and compaction, and complicates retry semantics.

When setting per-request TTL/timestamps, use **Spring Data Cassandra template options** or driver CQL verified for your version. Never assume `repository.save()` exposes every CQL option through the same signature.

### 14.3. `DELETE` and Tombstones

~~~java
repository.deleteById(new ReadingKey(deviceId, day, eventTime));
~~~

Deletes in Cassandra normally write tombstones so replicas learn about deletions per consistency/repair rules. **Never** assume deleting a row immediately reclaims disk space; tombstones persist until compaction and safety checks clear them.

Consequences:

- Avoid re-issuing deletes with fresh timestamps amid unexamined concurrent writes.
- Never rely on `deleteById` as a rollback across multiple repository calls.
- Watch tombstone read amplification when deletes/TTLs are frequent.

## 15. LWT, Conditional Writes, and Business Consistency

### 15.1. Do Not Confuse `save` with `IF NOT EXISTS`

"Insert only if absent" **is not** `repository.save(reading)`. CQL provides conditional writes:

~~~cql
INSERT INTO telemetry_lab.readings_by_device_day
(device_id, event_day, event_time, reading_value, status)
VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

LWT incurs Paxos consensus overhead and distinct semantics; never apply it to every `INSERT` just for a "success" boolean. With the driver, inspect `ResultSet.wasApplied()` on conditional statements.

In Spring Data Cassandra, conditional-operation support and result wrappers vary across repositories, templates, and the driver; **verify your API/version**. When observing `[applied]` precisely is critical, `CqlSession` or explicit conditional template APIs are easier to verify than plain `save`.

### 15.2. Timeouts Can Occur After LWT Already Applied

Suppose the first `IF NOT EXISTS` created the row yet the client timed out. On retry, the statement returns `wasApplied() == false` because the row now exists. **That does not prove the first attempt failed.**

You need:

1. Stable logical operation IDs.
2. Verification of existing state and invariants.
3. Bounded retry budgets and timeouts.
4. No blind replay of external side effects.

### 15.3. Consistency Level Is Data Design, Not a Decorative Annotation

| CL | General Meaning at RF=3 in One DC | Impact |
|---|---|---|
| `ONE` | Needs one eligible replica response | Fewer ACKs, no quorum guarantee |
| `LOCAL_QUORUM` | Local DC quorum (2/3 in example) | Balances consistency and availability per topology |
| `ALL` | Every relevant replica | Sensitive to slow or failed nodes |
| `EACH_QUORUM` | For supported writes, quorum per DC | Higher latency/availability complexity |

**Never pick CL just because a derived method is slow.** When using consistency profiles, verify policies in Spring Data/driver, RF, and DC names for your release. `LOCAL_QUORUM` in `dc1` does not guarantee `dc2` has ACKed on success.

### 15.4. Which Layer Configures CL?

Different integration points exist:

- Driver execution profiles / session defaults.
- Statement-level consistency when using `CqlSession`.
- Operation/query options in `CassandraTemplate` where supported.
- Version-specific Spring Data annotations/options.

Never assume every repository method supports the same CL annotation across all Spring Data versions. **Integration tests and driver telemetry** must verify real runtime consistency, especially on critical reads/writes.

## 16. Imperative vs. Reactive Spring Data Cassandra

### 16.1. Two Repository Flavors

Imperative repository:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ReadingRepository
        extends CassandraRepository<Reading, ReadingKey> {
}
~~~

Reactive repository (when supported by starter/driver/framework):

~~~java
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;
import reactor.core.publisher.Flux;

public interface ReactiveReadingRepository
        extends ReactiveCassandraRepository<Reading, ReadingKey> {

    // Signature verified against Spring Data Cassandra version.
    Flux<Reading> findByKeyDeviceIdAndKeyEventDay(
        UUID deviceId, LocalDate eventDay);
}
~~~

These two examples represent an **architectural choice**, not a license to register both interfaces arbitrarily in one app. Name beans clearly and verify auto-configuration/scanning for your chosen repository model.

### 16.2. Reactive Does Not Turn CQL into an Infinite Stream

When a reactive repository returns `Flux<Reading>`:

- The query still runs against Cassandra obeying partition keys and CL.
- Paging and backpressure can help bound memory depending on the stack.
- `Flux` is not a CDC stream pushing new future rows forever.
- `Flux.collectList()` can still pull an entire partition onto the heap.
- Every subscription or retry can issue a fresh query per `Publisher` semantics.
- Cancellation does not roll back mutations already applied by replicas.

Adopt reactive only if the **entire pipeline handles nonblocking execution and bounded concurrency**. Never wrap reactive calls in `block()` on WebFlux event loops; for synchronous services, imperative repositories are often cleaner.

### 16.3. Derived Query Limits Are Identical on the Server

A reactive `findByStatus(...)` does not magically become valid if imperative `findByStatus(...)` lacks an access path. **Reactive only changes how results are consumed**, not CQL rules.

## 17. Schema Migrations and Rolling Deployments

### 17.1. Never Let Apps Auto-Recreate Schemas

In production, separate:

1. Peer-reviewed CQL definitions.
2. Planned schema changes checking **schema agreement**.
3. Rolling app deploys capable of reading old/new schemas when needed.
4. Data backfills when changing partition keys or adding query-specific tables.
5. Reconciliation before cutting over reads.
6. Dropping old tables only after retention/rollback windows expire.

Switching from `PRIMARY KEY ((device_id, event_day), event_time)` to another partition key **is not just editing `@PrimaryKeyColumn` on an entity**. Cassandra does not rewrite all SSTables to new tokens just because a Java class changed.

### 17.2. Expand / Contract for New Fields

Adding a regular column:

~~~cql
-- Run via change process after verifying CQL version.
ALTER TABLE telemetry_lab.readings_by_device_day
ADD quality text;
~~~

Afterwards:

- Old code may ignore `quality`, yet existing queries must still be tested.
- Historical rows will return `quality = null`.
- New code must not assume every row has a non-null `quality`.
- If you add `WHERE quality = 'GOOD'`, adding the column **does not create an index or access path**.
- If `quality` must become part of the partition key, create a new table and migrate.

### 17.3. Changing Query Shapes May Require a New Table

If the system starts needing "the 10 newest alert devices for a site", `readings_by_device_day` is not built to answer that directly. Create a second table:

~~~cql
-- Access-pattern example only; verify cardinality/bucketing.
CREATE TABLE telemetry_lab.alerts_by_site_day (
    site_id uuid,
    alert_day date,
    event_time timestamp,
    device_id uuid,
    message text,
    PRIMARY KEY ((site_id, alert_day), event_time, device_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC, device_id ASC
);
~~~

The app may dual-write or publish events to a writer for the new table, **yet two writes do not become a multi-table ACID transaction**. Plan idempotency, reconciliation/backfills, and rollback.

### 17.4. Compaction and Capacity During Migrations

While keeping both old and new tables:

- Physical disk usage rises with RF, compression, and token distribution.
- Memtable flushes produce additional SSTables.
- Compaction demands extra I/O and temporary disk headroom.
- Repair/streaming can contend for resources.
- Backfills must never use repository `findAll()` for unbounded scans.
- Use token ranges or partition work items with checkpoints and rate/byte limits.

Spring Data repositories tidy up Java code, yet they do not throttle replication factors, write amplification, or disk headroom.

## 18. Testing Repositories Against Real Cassandra, Not Just Mocks

### 18.1. Why Mocks Are Insufficient

A unit test like `when(repository.findLatest20(...)).thenReturn(...)` only proves **the service handles stubbed data**. It does not prove:

- Spring Data's parser understands your derived method name.
- `@Query` emits valid CQL for your CQL/server version.
- Composite key mapping preserves column order and types.
- Cassandra serves the `WHERE` clause without wide scans.
- `LIMIT`, intra-partition sorting, nulls, and paging work properly.
- Local DC, RF, and CL uphold designed correctness.

Keep unit tests for business logic, and add **integration tests against lab Cassandra** to verify mappers, repositories, and real query execution.

### 18.2. Testing with `@DataCassandraTest`

Illustrative outline for projects provisioning a Cassandra test instance or Testcontainers in their test harness:

~~~java
package demo.telemetry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest;

import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@DataCassandraTest
class ReadingRepositoryIntegrationTest {

    @Autowired
    ReadingRepository repository;

    @Test
    void queryByFullPartitionKeyAndLimit() {
        UUID device = UUID.randomUUID();
        LocalDate day = LocalDate.of(2026, 11, 21);
        Instant older = Instant.parse("2026-11-21T09:00:00Z");
        Instant newer = Instant.parse("2026-11-21T10:00:00Z");

        ReadingKey oldKey = new ReadingKey(device, day, older);
        ReadingKey newKey = new ReadingKey(device, day, newer);

        repository.save(new Reading(oldKey, 21.5, "OK"));
        repository.save(new Reading(newKey, 22.0, "OK"));

        List<Reading> latest = repository.findLatest20(device, day);

        assertEquals(2, latest.size());
        assertEquals(newer, latest.get(0).getKey().getEventTime());
        assertTrue(repository.findById(oldKey).isPresent());
    }
}
~~~

**Conditions for trustworthy tests:**

- Test slices **do not start Cassandra automatically**; provision Testcontainers or an external test cluster with matching connection settings.
- Keyspaces/tables must come from test migrations; never let tests recreate production schemas.
- RF/CL must match lab topology; RF=3 on a single node will fail `LOCAL_QUORUM`.
- Immediate read-after-write assertions require appropriate CL or test harness guarantees.
- Random UUIDs reduce test collisions; still clean up via TTL or isolated keyspaces per policy.
- `@DataCassandraTest` and repository scanning/imports vary across Spring Boot versions; verify actual bean wiring.

This shows an **integration test pattern**, not a claim that every stack runs it verbatim without setup.

### 18.3. Testing Failure Paths

| Test | Expected Behavior |
|---|---|
| Derived method with full partition key | Valid CQL emitted targeting one partition |
| Query missing a partition key component | Rejected / barred from production; never enable blind filtering |
| `@Query` with `LIMIT 20` | Never returns more than 20 rows |
| `event_time` range | Exact boundaries and clustering order |
| Query on `status` alone | Server constraint caught explicitly |
| Row missing `reading_value` | DTO keeps `null`, never coerces to `0.0` |
| `findById` with full key | Finds one row; never returns the whole partition |
| Alias/projection changes | Mapper does not silently misalign fields |
| Multi-page `Slice`/paging | No skipped/duplicated rows from app paging logic |
| New schema with optional column | Legacy rows still read cleanly |
| One replica down in lab | Designed CL/availability verified |
| Driver timeout error | HTTP does not return a fake "no rows" response |
| Multi-tenant reads/writes | Principal cannot read another tenant's partitions |
| Version upgrades | Repository parser, type codecs, and dependencies stay compatible |

Do not stress-test production by inserting millions of rows just to confirm `findAll()` is slow. Use representative volumes in an isolated environment and watch resources.

### 18.4. Testing Time and Timezones

CQL `timestamp` represents an instant, normally mapped to `Instant`. `date` represents a calendar `LocalDate`. For daily buckets, standardize the **bucketing timezone** (e.g., UTC), especially around midnight boundaries.

Never call `LocalDate.now()` using the JVM's implicit timezone assuming it matches the server or client. Writing a row into the **wrong `event_day`** makes repositories report "not found" even though the row exists in another partition.

## 19. Security: Multi-Tenancy and Access Control

### 19.1. Repository Parameters Are Not Authorization

Suppose an API exposes:

~~~text
GET /tenants/{tenantId}/devices/{deviceId}/readings
~~~

Even if the table uses `(tenant_id, device_id, event_day)` as its partition key, Spring Data **binding `tenantId`** does not prove the caller has access to that tenant.

In the service layer:

1. Authenticate and obtain a trusted principal.
2. Verify the principal is authorized for that tenant.
3. Derive tenant/roles from authenticated context or explicit authorization checks.
4. Bind the verified tenant into the query.
5. Configure Cassandra roles with **least privilege**.
6. Avoid logging sensitive data or partition keys arbitrarily.

### 19.2. `@Query` Value Binding Prevents CQL Injection, Not Broken Access Control

~~~java
@Query(
    "SELECT device_id, event_day, event_time, " +
    "reading_value, status FROM readings_by_device_day " +
    "WHERE device_id = ?0 AND event_day = ?1 LIMIT 20")
List<Reading> findLatest20(UUID deviceId, LocalDate day);
~~~

If a caller supplies someone else's device UUID and the app skips ownership checks, the query has **zero injection bugs** yet **still leaks data**.

Never treat UUID regexes or type validation as authorization.

### 19.3. Multi-Layer Access Controls

- Application principal/role and tenant authorization.
- Cassandra roles/RBAC at keyspace/table level when enabled.
- App↔cluster TLS and certificate/credential verification.
- Secret rotation and connection pool lifecycle management.
- Sanitized query/metric logging omitting bind values.
- Separation of schema-admin privileges from runtime app accounts.

In Cassandra, table/keyspace grants **do not provide per-tenant row-level security**. When multiple tenants share one table and one Cassandra role, the app must enforce isolation strictly; consider stronger architectural isolation if required.

## 20. Observability: Which Repository Method Is Slowing Cassandra Down?

### 20.1. Three Measurement Sources

| Source | Useful Metrics | Meaning |
|---|---|---|
| **Spring API / service** | Endpoint QPS, p50/p95/p99, 5xx, total rows/bytes | User impact |
| **Java Driver / Spring repository** | Query ID, in-flight, CL, timeouts, retries, coordinator, paging | Pinpoints which query shape drives load |
| **Cassandra node** | Read/write latency, compaction, SSTables per read, tombstones, disk, CPU/GC | Finds replica bottlenecks |

Assign a **stable query ID** such as `read_latest20_by_device_day` per repository method rather than logging raw queries with bind values.

### 20.2. Cluster Inspection Commands

~~~bash
# Node status, DC/rack, token ownership.
nodetool status

# Pending/active/dropped messages by stage.
nodetool tpstats

# Active compaction tasks and backlog.
nodetool compactionstats

# Per-table metrics including storage/read/write per version.
nodetool tablestats telemetry_lab.readings_by_device_day

# Per-table histograms if supported by version.
nodetool tablehistograms telemetry_lab readings_by_device_day

# Streaming during repair/bootstrap/replace.
nodetool netstats
~~~

An empty `netstats` **does not prove** Java `findAll()` isn't hammering CQL; it primarily tracks SSTable streaming. `nodetool status` showing `UN` also does not prove latencies meet SLOs.

### 20.3. Read p99 Alongside Error Rate

If `findLatest20` shows 100 ms p99 on successes while timeout rate jumps from 0.1% to 5%, the system is **not healthy**. Slow requests that timed out drop out of the success histogram.

Never compute cluster p99 by averaging per-node p99s. Use properly aggregated latency distributions alongside driver timeouts, server read/write timeouts, unavailable counts, and retry amplification.

### 20.4. Table-Level Pressure

An unbounded `findByKeyDeviceIdAndKeyEventDay(...)` can pull 500,000 rows from one partition. After deploy, dashboards might show:

~~~text
Time UTC   API p99   Response bytes   ReadStage Pending   Heap use
09:00      120 ms          10 KiB               15          35%
09:15      750 ms         900 KiB              180          68%
09:30     1800 ms           8 MiB              740          91%
~~~

**These numbers are illustrative**, not benchmarks. Check p95, request timeouts, network, GC, SSTable counts, compaction, and data skew before blaming the query alone.

## 21. Runbook A — Derived Query Compiles, Fails at Runtime as Invalid CQL

**Scenario:** After deploy, `findByStatus(String status)` is called and Cassandra rejects it for missing the partition key or lacking an access path.

1. **Verify schema:** `PRIMARY KEY`, indexed columns, table options, Cassandra version.
2. **Verify Java mapping:** property names, `@Column`, key class/ordinals.
3. **Verify real CQL:** use controlled query logging or driver instrumentation, avoiding bind values/PII.
4. **Separate parser errors from server errors:** did Spring Data generate CQL? Which clause did the server reject?
5. **Never add `ALLOW FILTERING` by default** just to "get past" the incident.
6. **Redesign the access path:** partition/bucketing, query-specific table, or evaluated index.
7. **Use `@Query` if the issue is expressiveness**, not data modeling. `@Query` cannot fix a missing access path.
8. **Load/timeout-test** with representative data before opening full traffic.

**Target outcome:** not merely "endpoint returns 200", but sound query shape, healthy p99/bytes/s, and zero cluster-wide scans.

## 22. Runbook B — Spring Boot Starts, Repository Fails with Missing Table

**Scenario:** Service deploys cleanly and connects to Cassandra, yet `findLatest20` throws "unconfigured table" or mapping errors.

1. Record Boot, Spring Data, driver, keyspace, endpoint, local DC, and change ID.
2. Verify `spring.cassandra.keyspace-name` matches the target cluster (no test/prod mix-up).
3. Confirm `readings_by_device_day` actually exists in that keyspace.
4. Compare DDL/schema agreement, column names, and quoted/unquoted identifiers.
5. Compare `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`, and `@Column` against real CQL.
6. Verify the user/role has `SELECT`; auth failures differ from missing tables.
7. Check the compatibility matrix if driver/framework or schema recently upgraded.
8. Never enable schema auto-recreate in production to fix missing tables; run schema migrations through change control.
9. Re-test `findById`, derived queries, and `@Query` against the same keyspace.

**Never drop/recreate tables without backups and rollback plans.** A Java mapping bug is not proof the Cassandra table is corrupt.

## 23. Runbook C — Repository Method Triggers Timeouts and Heap Growth

**Scenario:** Switching an API to `List<Reading> findByKeyDeviceIdAndKeyEventDay`; some partitions are huge, driving up p99 and GC.

1. **Measure row counts and response bytes** on affected partitions; identify hot/wide partitions.
2. Check whether `LIMIT`, paging, or stop conditions exist.
3. Verify the query uses the full partition key without multi-partition scans.
4. Inspect `ResultSet`/mapping: is code buffering everything into a `List` or `collectList()`?
5. Check `tpstats`, SSTables per read, tombstone warnings, compaction, and disk I/O.
6. Shed load: lower concurrency, rate-limit, and pause non-essential backfills/reports.
7. Switch to a **bounded** query (e.g., `@Query` with `LIMIT 20`), `Slice`/cursor, or finer buckets.
8. If an API needs many days or full history, use a checkpointed, quota-bounded job rather than forcing an HTTP call to load everything.
9. Re-check p99, timeouts, heap/GC, and error budget after the fix.

**Never just raise request timeouts** when a query returns excessive data — it holds memory and connections longer, worsening the outage.

## 24. Runbook D — Next Page Duplicates or Skips Rows Amid Concurrent Writes/Schema Changes

**Scenario:** A "next page" API uses SQL-like page numbers; as new data arrives or schemas change, clients observe missing or duplicate rows.

1. Verify query shape, partition key, clustering order, and active write patterns.
2. Check whether the API fakes offsets by fetching and discarding rows.
3. Check how your Spring Data Cassandra version supports `Slice`, `CassandraPageRequest`, and continuation tokens.
4. Bind cursors to query template, partition, and parameters with integrity checks and expiry.
5. For temporal stability, consider clustering-keyset pagination or a designed read snapshot.
6. Audit `<` vs. `<=` boundaries so pages neither skip nor duplicate boundary rows.
7. Test under concurrent inserts, deletes, and TTL expirations between pages.
8. Never assume old paging state stays valid across driver/server/schema changes.

**CQL paging is not a transactional snapshot.** "Page 2" in a UI needs an explicit data contract, not just an integer page number.

## 25. Query Selection Comparison

| Use Case | API to Consider | Why |
|---|---|---|
| Single-row lookup by full primary key | `repository.findById(fullKey)` | Simple, exact scope |
| Reading a small partition | Derived `findByKeyDeviceIdAndKeyEventDay` | Readable once method/parser is tested |
| Fetching 20 newest rows | `@Query` with explicit projection and `LIMIT` | Bounds rows, clear CQL |
| Time-based clustering range | `@Query` or template | Expresses range and limit clearly |
| Dynamic filters within an allowlist | `CassandraTemplate` | Flexible while keeping CQL controlled |
| Strict per-query deadlines/CL/tracing | `CqlSession` prepared/bound or template options | Driver-level control per version |
| Large continuous dataset processing | Quota-bounded paging/async/reactive + job checkpoints | Avoids buffering into `List`/HTTP |
| Multi-attribute search lacking partition key | Dedicated table/index/search/analytics | Never force `findBy...` |
| Cross-table joins | Denormalization or service-layer composition | Cassandra has no general SQL JOINs |
| Continuous change stream | CDC / event pipeline | Repository `SELECT` is not an event subscription |
| Conditional write | Supported LWT APIs | `save` is not CAS by default |
| Cluster-wide aggregate counts | Summary/counter tables or analytics | Avoid repeated `count()` on huge tables |

## 26. Common Misconceptions

| Claim | Reality |
|---|---|
| "Adding `findByStatus` makes Cassandra filter by status efficiently." | Queries need an access path, not just a Java method name |
| "Derived queries work like JPA on PostgreSQL." | Spring Data Cassandra is constrained by CQL and the partition model |
| "`@Query` allows any SQL." | It runs CQL, not general SQL |
| "Switching to `@Query` fixes full scans." | Not if `WHERE` still omits the partition key |
| "`findById` on a composite-key entity only needs `deviceId`." | Must pass the full primary key including clustering columns |
| "`List` is safe because the framework pages automatically." | It can still materialize huge row sets in memory |
| "`findAll()` is fine for exporting an entire table anytime." | Causes massive scans; requires throttled range jobs |
| "`count()` in Cassandra is always cheap." | Can trigger expensive reads depending on table and scope |
| "Spring Data adds JOINs to Cassandra." | CQL has no arbitrary server-side JOINs |
| "`ORDER BY status` works via Spring `Sort`." | CQL `ORDER BY` depends on schema clustering order |
| "Setting `pageSize=50` caps total rows at 50." | Page size only regulates individual pages |
| "`Pageable` always supports random page N like SQL." | Cassandra normally requires continuation/paging state |
| "Adding a column populates values in historical rows." | New columns read `null` on old data |
| "Editing partition key annotations automatically moves data." | Requires a new table, backfill, and cutover |
| "Repository `save` is a multi-table ACID transaction." | No; Cassandra mutations/CL/LWT have distinct semantics |
| "`save` always means `IF NOT EXISTS`." | Normally an upsert, not CAS by default |
| "TTL only affects the Java mapper." | TTL governs live data, tombstones, and compaction |
| "Spring reactive turns CQL into CDC." | Reactive queries are still finite CQL queries |
| "Enable `ALLOW FILTERING` to avoid designing tables." | Can trigger huge scans, latency, and I/O spikes |
| "Token-aware routing eliminates hot partitions." | A hot partition still concentrates load on its replica set |
| "Boot startup UP means all repository queries are valid." | Integration/smoke tests per real method are required |
| "Validating UUID syntax prevents tenant leaks." | Principal authorization and RBAC are mandatory |
| "Lowering consistency level never hurts correctness." | CL governs replica response guarantees |

## 27. Exercises and Answers

### Question 1 — Partition Key

A table has `PRIMARY KEY ((device_id, event_day), event_time)`. Which columns form the partition key?

**Answer:** `device_id` and `event_day`. `event_time` is the clustering key; the full primary key spans all three columns.

### Question 2 — `findById`

A repository uses ID type `ReadingKey`. To fetch all rows on Nov 21, should you call `findById(new ReadingKey(device, day, null))`?

**Answer:** No. The full primary key requires a valid `event_time`. Query the partition via a derived query or `@Query` taking device and day.

### Question 3 — Derived Query

`findByKeyDeviceIdAndKeyEventDay` queries inside one partition. Does it guarantee returning only 20 rows?

**Answer:** No; without `LIMIT`/pagination it can return the entire partition. Use a bounded query or pagination.

### Question 4 — Querying by `status`

A new API needs `findByStatus("ALERT")` on the example table. Is adding the method enough?

**Answer:** No. `status` is not a key component. Design another access path: a query-specific table, an evaluated index, or an appropriate pipeline.

### Question 5 — `@Query`

What does `@Query("SELECT ... WHERE device_id = ?0 ...")` give you?

**Answer:** Explicit CQL, bound values, and control over projections/`LIMIT`/conditions. It does not bypass server CQL constraints.

### Question 6 — Binding Table Names

Can you use `?0` to bind a table name from user input?

**Answer:** Not as a normal bound value. Table names are identifiers; use an enum/template allowlist and authorization checks, never raw untrusted concatenation.

### Question 7 — Clustering Order

You want the 20 newest rows for a device/day. The table has `event_time DESC`. Which query fits?

**Answer:** CQL filtering on both `device_id` and `event_day` with `LIMIT 20` and minimal column projection — no full-table sort needed.

### Question 8 — Global Sort

You want `ORDER BY reading_value DESC` across all devices. Can repository `Sort` solve this?

**Answer:** No. Cassandra does not support arbitrary global sorting like SQL; build a query-driven table, index, or analytics pipeline.

### Question 9 — Paging

Does `pageSize` 50 cap a `SELECT` at 50 rows total?

**Answer:** No. It is a per-page target; use `LIMIT`, cursors, and stop conditions for total results.

### Question 10 — Offset

A client wants to jump to page 10,000 via `PageRequest.of(10000,20)`. Should you expect Cassandra to skip efficiently like an RDBMS?

**Answer:** No. Cassandra paging uses continuation state. Design cursor/keyset pagination and verify your Spring Data version's support.

### Question 11 — TTL

What can retrying an `INSERT` with a fresh TTL alter?

**Answer:** Cell expiration time and write timestamp reconciliation; never assume retries are business-idempotent by default.

### Question 12 — LWT

Is `repository.save` equivalent to `INSERT ... IF NOT EXISTS` by default?

**Answer:** No. `save` is normally an upsert. Conditional writes require LWT-capable APIs/statements with explicit semantics.

### Question 13 — Schema Change

Does changing `event_day` to `event_month` in a Java key annotation automatically redistribute old SSTables?

**Answer:** No. Changing a partition key requires a new table, backfill, reconciliation, and cutover.

### Question 14 — Multi-Tenant

A caller passes a valid `device_id` belonging to another tenant. The query has no CQL injection. Is it secure?

**Answer:** No. Enforce principal-based ownership/authorization and tenant isolation.

### Question 15 — Error Handling

`findLatest20` times out, yet the service returns an empty `List`. Why is this dangerous?

**Answer:** It turns a database failure into "no data exists", driving wrong business decisions. Distinguish timeouts from valid empty `SELECT` results.

### Question 16 — Reactive

A reactive repository returns `Flux<Reading>`. Does that guarantee no OOMs?

**Answer:** No. `collectList`, unbounded buffers, fan-out, and huge rows can still exhaust heap; enforce backpressure and bounded concurrency.

### Question 17 — Integration Tests

A mocked repository returns the expected list. Does that prove the derived query emits valid CQL?

**Answer:** No. You need integration tests against lab Cassandra matching your versions, keyspace/schema, and data shapes.

### Question 18 — Compaction

After backfilling a new table, free disk drops and pending compactions climb. Does switching from repositories to `CqlSession` fix this?

**Answer:** No. The cause is write volume, RF, compaction, and storage headroom; throttle writes, monitor, and plan capacity.

### Question 19 — Consistency

A keyspace has RF=3, CL=`LOCAL_QUORUM`, and only one replica remains healthy in a DC. Can a Spring repository make the request succeed without changing consistency?

**Answer:** It cannot guarantee it. Local quorum requires two replicas here; restore replica health or re-evaluate CL policy as a business decision.

### Question 20 — Aggregate Queries

An API reports daily event counts per site across billions of rows. Should it call `repository.count()` on every dashboard load?

**Answer:** Usually no. Build aggregation tables, materialized counters/event processors with well-defined guarantees, or a dedicated analytics system.

## 28. Pre-Merge Checklist for Spring Data Cassandra Repositories

### 28.1. Schema and Mapping

~~~text
[ ] Real query shapes documented before adding repository methods.
[ ] Partition/clustering keys, ordinals, and types match CQL.
[ ] @PrimaryKeyClass / @PrimaryKeyColumn / @PrimaryKey mappings tested.
[ ] Entity @Table / @Column match real keyspace/table/column names.
[ ] Nullable fields and Instant/LocalDate timezones handled consistently.
[ ] DDL/schema changes managed outside production startup.
[ ] Any primary key change has a migration/backfill/cutover plan.
~~~

### 28.2. Repositories and Queries

~~~text
[ ] No unguarded findAll / count / deleteAll on large tables.
[ ] Derived property paths and emitted CQL verified by integration tests.
[ ] @Query binds values only; zero raw user input concatenation.
[ ] Projections select needed fields plus required mapping keys.
[ ] WHERE includes the full partition key or an approved access path.
[ ] LIMIT / page size / cursors defined and load-tested.
[ ] No RDBMS-style arbitrary SQL JOIN / OR / ORDER BY assumptions.
[ ] @Query never hides unbounded scans or ALLOW FILTERING.
[ ] CassandraTemplate / CqlSession used when justified and tested.
[ ] Writes, retries, LWT, TTL, and deletes have documented semantics.
~~~

### 28.3. Operations, Security, and Serviceability

~~~text
[ ] Spring Boot / Driver / Spring Data / JDK versions verified compatible.
[ ] Contact points, local DC, keyspace, auth/TLS match the environment.
[ ] Runtime role follows least privilege with separate tenant authorization.
[ ] RF / CL / replica availability meet SLOs.
[ ] Query IDs, p95/p99, errors/retries, and response bytes instrumented.
[ ] tpstats / compactionstats / tablestats / disk / GC monitored.
[ ] Raw bind values, secrets, and sensitive routing keys never logged.
[ ] Runbooks ready for invalid derived CQL, schema drift, paging, and timeouts.
[ ] Tested against large partitions, TTL/tombstones, nulls, and data mutations.
[ ] Boot health UP never treated as full repository verification.
~~~

## 29. Summary

When using **Spring Boot and Spring Data Cassandra**:

1. **`CassandraRepository` cuts CRUD boilerplate**, yet methods like `findAll()`/`count()`/`deleteAll()` can be devastating on large wide-column tables.
2. **Derived queries** translate Java method/property names into CQL; they work only when CQL/schema supports the predicates and must be tested on real Cassandra.
3. **`@Query` gives explicit CQL** for projections, `WHERE`, ranges, and `LIMIT`; it never turns CQL into SQL or invents indexes.
4. **Composite primary keys must be mapped accurately** with key classes and annotations covering partition/clustering roles, types, and ordinals.
5. **Design queries around partition keys**, clustering order, and access patterns; never expect JOINs, arbitrary `WHERE`/`OR`, global `ORDER BY`, or cheap offset pagination.
6. **Paging differs from `LIMIT`**: page/fetch size regulates transfer chunks without capping total rows or providing a snapshot.
7. **Templates/drivers are API escape hatches**, not escape hatches from data modeling or replica load.
8. **`save` is neither a transaction nor LWT by default**; TTL, `DELETE`, retries, consistency, and concurrent writes require explicit correctness analysis.
9. **Reactive repositories only change result consumption**, not CQL rules or automatic memory/concurrency safety.
10. **Integration tests and observability are mandatory** to catch methods that look clean in Java yet fail or overload Cassandra at runtime.

The right question before adding a repository method is not **"Can Spring Data parse this method name?"**, but **"What exact CQL runs, which partitions/replicas serve it, what are the maximum rows/bytes returned, and does this abstraction preserve application semantics under failures and schema evolution?"**. Answering with schemas, tests, and metrics keeps Spring Data a clean, maintainable Cassandra layer without hiding distributed-system costs.
