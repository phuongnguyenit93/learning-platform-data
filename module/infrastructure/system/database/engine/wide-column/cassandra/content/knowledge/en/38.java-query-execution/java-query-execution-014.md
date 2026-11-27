# Object Mapper/DAO and Abstraction Overhead

## 1. The problem: shorter Java code, but are queries actually faster?

A **Java** service uses **Apache Cassandra** to store device events. Initially, developers wrote `PreparedStatement` and `BoundStatement` directly and extracted each field from `Row`. Once the project grew to dozens of query tables and hundreds of call sites, the team wanted to switch to an **object mapper** and **DAO (Data Access Object)** to eliminate repetitive column-conversion code, centralize access logic, and reduce maintenance errors.

The new approach looks very concise:

~~~java
EventRecord event = dao.findById(
    "device-7",
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));
~~~

After the change, however, the team noticed higher p99 latency on some APIs, larger heap allocation, and queries silently returning more columns than the UI needed. One developer concluded: "Mappers are inherently slow—just rip out the mapper." Another argued: "The DAO already optimizes CQL automatically, so there's no need to inspect the query plan." **Both conclusions lack basis.**

In the Apache Cassandra Java Driver 4.x, the mapper is typically **Java code generated at compile time from annotations**; it does not necessarily use reflection per row like a dynamic ORM. True cost must be broken down into **statement preparation, network/replica work, columns/bytes read, paging, CQL decoding, object instantiation, type conversion, and memory allocation**. A `SELECT *` or a wrong partition key can cost orders of magnitude more than any difference between the mapper and `Row`.

**Objectives of this lesson in the "Querying from Java" chapter:**

1. Understand the roles of `@Entity`, `@Dao`, `@Mapper`, and the annotation processor in Java Driver 4.x.
2. Create a query-driven CQL table, map the primary key accurately, and use a DAO for reads and writes.
3. Compare the mapper with the **Core API** (`CqlSession`, prepared/bound statements, `Row`) on identical CQL.
4. Quantify abstraction overhead: object allocation, GC, column projection, custom codecs, paging, `N+1`, prepared statements, and routing.
5. Distinguish a Cassandra DAO from a JPA/Hibernate-style ORM: **no automatic joins, transactions, lazy loading, or dirty checking**.
6. Design measurements for p95/p99, throughput, memory, and replica resources before choosing an implementation style.
7. Apply concurrency, consistency, timeout, security, and migration limits to keep DAOs correct and safe.

**Scope:** uses `com.datastax.oss.driver.api.*` APIs from Java Driver **4.x**. Dependencies, annotation packages, code generation, type-mapping capabilities, execution profiles, and option names can differ across minor releases and distributions. The code is a **demonstration lab** and must be verified against your actual version and schema. This lesson does not replace formal QA or benchmarking on the target cluster.

## 2. Placing the mapper accurately in Cassandra's architecture

~~~mermaid
flowchart TD
    A["HTTP / Java use case"] --> B["Service: validation, deadline, rate limit"]
    B --> C["DAO interface"]
    C --> D["Compile-time generated mapper implementation"]
    D --> E["Java Driver Core: CqlSession, prepared/bound statement"]
    E --> F["Routing to coordinator"]
    F --> G["Natural replicas by token, RF, CL"]
    G --> H["Memtable, SSTable, cache, commit log"]
    H --> G
    G --> F
    F --> E
    E --> I["Row decoding / Entity / DTO mapping"]
    I --> B
~~~

**There is no shortcut from `@Dao` to SSTables.** Whether you call `dao.findById()` or `session.execute()`, it still becomes a **CQL statement** sent over the native protocol to Cassandra. The driver does not bypass the coordinator, consistency level, tombstones, or disk I/O just because a mapper is used.

| Component | Primary responsibility | What it does not do for you |
| --- | --- | --- |
| **CQL schema** | Routes by partition key, orders rows by clustering columns, defines data types. | The mapper cannot change a table's primary key. |
| **Core Driver** | Connection/routing, prepare/bind/execute, paging, timeouts, retries, value decoding. | Does not guarantee that query shapes match your workload. |
| **Object mapper** | Generates code converting CQL columns to Java properties, generates DAOs and common statements. | Does not create joins, secondary indexes, snapshot transactions, or optimal projections automatically. |
| **DAO interface** | Encapsulates the data-access contract and use-case methods. | Does not guarantee every `SELECT` is a single-partition lookup. |
| **Service layer** | Validation, business authorization, bucket fan-out, deadlines, backpressure, and caching where appropriate. | Should not push business decisions or unbounded retries into the DAO. |

### 2.1. How does a Data Access Object differ from an object mapper?

- **DAO** is the **API boundary**: `findById`, `findWindow`, `insertEvent`, `markProcessed`. It can be hand-written with Core Driver or generated.
- **Object mapper** is the tool that converts **CQL rows/types ↔ Java objects** and typically supports generating DAO implementations from annotations.
- **Entity** describes how a Java bean maps to a Cassandra table; it is not necessarily a full domain object or business aggregate root.
- **DTO/projection** contains only the data the API needs; it does not have to be a full entity if reading a few columns via `Row` is more efficient.

**A well-designed DAO can combine both the mapper and Core API.** For example, `findById` uses the mapper for maintainability, while a dashboard that reads three columns across millions of records uses the Core API to avoid constructing unnecessary `payload` objects.

## 3. The 4.x mapper is not a relational JPA-style ORM

| Expectation from JPA/Hibernate | What the Cassandra Java Driver mapper does | Consequence |
| --- | --- | --- |
| `@Entity` has an identity map and dirty checking | Maps properties/columns and generates statements/DAOs; **no JPA persistence context** by default. | Mutating a Java object field does not mean Cassandra automatically runs `UPDATE`. |
| `@ManyToOne`, `JOIN FETCH` | Cassandra does not have multi-table joins in the standard CQL model. | Model tables per query or assemble results in the service layer when needed. |
| Lazy-loaded relationships | No automatic lazy proxies or relational ORM object-graph prefetching. | You must bound query counts yourself and avoid `N+1`. |
| Multi-table `@Transactional` | Cassandra has its own mutation/batch/LWT semantics, **no SQL-style multi-partition isolated transactions**. | Dual-writing two tables requires idempotency and reconciliation. |
| Changing primary key via `entity.setId()` | Partition/clustering keys identify the row and its token placement. | You must write the new key and handle the old key explicitly, not update keys in place. |
| ORM auto-generates optimal queries | The mapper builds CQL from annotations or `@Query`; it does not measure cluster state or rewrite arbitrary queries. | You must design partition keys, clustering ranges, and benchmark. |
| Automatic schema migration | The mapper does not modify production table structures automatically. | Use dedicated migration processes and schema governance. |

**Why does this matter?** If `EventRecord` has an `eventDay` property, annotating it with `@PartitionKey(1)` lets the mapper bind an existing schema structure properly; it does **not** make Cassandra automatically partition by day if the actual table schema lacks that key component.

## 4. Designing a table around queries, not object shape

### 4.1. CQL lab

Assume a lab cluster with DC `dc1` and three full replicas available:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry_mapper
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry_mapper.events_by_device_day (
    device_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

**Why does this schema fit the use case?**

1. `(device_id, event_day)` is a **composite partition key**. The same device on different days lands in separate partitions that can hash to different tokens.
2. `event_time` is the first clustering column, enabling reads over a **time range within a single partition**; `event_id` prevents two events with the same timestamp from colliding into a single primary key.
3. `CLUSTERING ORDER BY (event_time DESC, event_id ASC)` prioritizes the newest events within a day. It does not establish a global ordering across daily partitions.
4. `payload` is a regular column. If it is very large or an API only needs a timeline summary, splitting summary and detail tables can cut bytes read far more effectively than replacing the object mapper.
5. RF = 3 in `dc1` is a conditional lab setup. Do not declare an RF larger than the actual node count and expect `LOCAL_QUORUM` to always succeed.

### 4.2. Test data with deterministic identifiers

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-21', '2026-11-21T09:00:00Z',
  123e4567-e89b-42d3-a456-426614174001, 'HEARTBEAT', 'ok');

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-21', '2026-11-21T09:01:00Z',
  123e4567-e89b-42d3-a456-426614174002, 'TEMPERATURE', '21.6');

INSERT INTO telemetry_mapper.events_by_device_day
 (device_id, event_day, event_time, event_id, event_type, payload)
VALUES
 ('device-7', '2026-11-20', '2026-11-20T23:59:59Z',
  123e4567-e89b-42d3-a456-426614174003, 'HEARTBEAT', 'late');
~~~

`CONSISTENCY` is a **cqlsh** command. In the Java Driver, CL is set via the statement or execution profile. `LOCAL_QUORUM` with RF = 3 requires two replica responses in the local DC, but does not guarantee that all replicas have converged.

### 4.3. Query with sensible physical bounds

~~~sql
SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM telemetry_mapper.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

This query supplies the **full partition key**, a **half-open clustering range `[start, end)`**, and a `LIMIT`. This CQL is not optimized "more automatically" just because it runs through a mapper; most of the efficiency comes from **bounded single-partition access**.

## 5. Integrating the mapper: runtime dependency and annotation processor

Java Driver 4.x typically separates **Core Driver**, **mapper runtime**, and **annotation processor**. The annotation processor runs during compilation to generate implementations; the mapper runtime supports the generated code when the application runs.

### 5.1. Maven example

~~~xml
<!-- Version numbers are illustrative; choose a supported 4.x driver version
     available in your project and keep all artifacts aligned. -->
<properties>
    <cassandra.driver.version>4.17.0</cassandra.driver.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-core</artifactId>
        <version>${cassandra.driver.version}</version>
    </dependency>
    <dependency>
        <groupId>com.datastax.oss</groupId>
        <artifactId>java-driver-mapper-runtime</artifactId>
        <version>${cassandra.driver.version}</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.datastax.oss</groupId>
                        <artifactId>java-driver-mapper-processor</artifactId>
                        <version>${cassandra.driver.version}</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

**Checkpoints:**

- Pin a single matching **version** across `java-driver-core`, mapper runtime, and the processor; check the compatibility matrix for your Cassandra, JDK, and driver versions.
- Annotation processing must be **enabled in the build**. If disabled, generated classes such as `TelemetryMapperBuilder` will not be produced and the project may fail to compile.
- An IDE building cleanly while CI fails can happen because of **different annotation processor paths**, not a Cassandra node issue.
- Code generation **does not connect to the database at compile time** to verify that every column or table exists on the live cluster. Schema changes still require migrations, integration tests, and post-deploy verification.
- Do not treat the example version as "latest". When using another version, verify the exact **annotation names, supported return types, and mapper APIs**.

### 5.2. Do not confuse compile-time generation with "heavy reflection ORM"

Some ORMs map via runtime reflection and dynamic proxies. The Cassandra 4.x mapper **generates Java source code** for DAO and entity mapping before runtime, which generally removes dynamic reflection from the hot path. Even so:

1. Generated code still performs **CQL decoding, entity instantiation, property assignment, and null/codec handling**.
2. Instantiating many entities creates **object allocation and GC pressure**.
3. A default method returning `SELECT *` still transfers **unneeded payload bytes and columns**.
4. If one DAO call triggers multiple CQL statements, network and replica costs still accumulate.
5. Performance must be measured under the **same CQL, paging, RF/CL, and workload**—never inferred solely from codegen architecture.

## 6. `@Entity`: mapping the full partition and clustering keys

In the example below, Java field names use camelCase while Cassandra columns use snake_case. Declaring **`@CqlName` explicitly** avoids relying on naming conventions and makes the primary key visible to readers.

~~~java
// EventRecord.java
import com.datastax.oss.driver.api.mapper.annotations.CqlName;
import com.datastax.oss.driver.api.mapper.annotations.Entity;
import com.datastax.oss.driver.api.mapper.annotations.PartitionKey;
import com.datastax.oss.driver.api.mapper.annotations.ClusteringColumn;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Entity
@CqlName("events_by_device_day")
public class EventRecord {
    @PartitionKey(0)
    @CqlName("device_id")
    private String deviceId;

    @PartitionKey(1)
    @CqlName("event_day")
    private LocalDate eventDay;

    @ClusteringColumn(0)
    @CqlName("event_time")
    private Instant eventTime;

    @ClusteringColumn(1)
    @CqlName("event_id")
    private UUID eventId;

    @CqlName("event_type")
    private String eventType;

    @CqlName("payload")
    private String payload;

    public EventRecord() {}

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String value) { deviceId = value; }

    public LocalDate getEventDay() { return eventDay; }
    public void setEventDay(LocalDate value) { eventDay = value; }

    public Instant getEventTime() { return eventTime; }
    public void setEventTime(Instant value) { eventTime = value; }

    public UUID getEventId() { return eventId; }
    public void setEventId(UUID value) { eventId = value; }

    public String getEventType() { return eventType; }
    public void setEventType(String value) { eventType = value; }

    public String getPayload() { return payload; }
    public void setPayload(String value) { payload = value; }
}
~~~

**Reading the annotations accurately:**

- `@PartitionKey(0)` and `@PartitionKey(1)` mirror the **order of partition key components**. Swapping the order or dropping `eventDay` is not an optimization; it can cause incorrect binding or break query routing.
- `@ClusteringColumn(0/1)` mirrors the clustering column order on the table; having `eventTime` before `eventId` is part of the **schema contract**.
- `Instant` maps to CQL `timestamp`, `LocalDate` to `date`, and `UUID` to `uuid` in Java Driver 4.x.
- The POJO exposes a no-arg constructor and getters/setters so the mapper can instantiate and populate it. This entity is a **CQL read/write record**, not a transactional aggregate or change-tracking object.
- `@CqlName("events_by_device_day")` names the table; the **keyspace** comes from the session/config/default schema or explicit mapping setup. The lab below sets `withKeyspace("telemetry_mapper")` to avoid ambiguity.

### 6.1. Common mapping mistakes

| Mistake | Symptom | Resolution |
| --- | --- | --- |
| Treating `eventDay` as a regular column | DAO fails to match keys or queries omit part of the partition key. | Cross-check table `PRIMARY KEY` against entity annotations. |
| Mapping `timestamp` to `String` arbitrarily | Requires custom codecs or causes type errors. | Use `Instant` with an explicit UTC convention. |
| Using primitive `int` for a nullable column | Cannot represent null values. | Pick a nullable wrapper type and verify null/unset semantics. |
| Renaming a property without updating annotation/CQL | Data maps unexpectedly or causes build/runtime failures. | Use explicit column names and integration tests against the real schema. |
| Using a massive entity for an endpoint needing only 3 columns | Increases network, decoding, and allocation when all columns are selected. | Design a projection, DTO, or Core `Row` mapping. |

## 7. `@Dao`: grouping queries into a small, explicit API

~~~java
// EventDao.java
import com.datastax.oss.driver.api.core.PagingIterable;
import com.datastax.oss.driver.api.mapper.annotations.Dao;
import com.datastax.oss.driver.api.mapper.annotations.Insert;
import com.datastax.oss.driver.api.mapper.annotations.Query;
import com.datastax.oss.driver.api.mapper.annotations.Select;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

@Dao
public interface EventDao {
    // Generates a SELECT by full primary key.
    @Select
    EventRecord findById(
        String deviceId,
        LocalDate eventDay,
        Instant eventTime,
        UUID eventId);

    // Generates an INSERT from the entity properties.
    @Insert
    void insert(EventRecord event);

    // Reads a clustering range within a single partition.
    @Query(
        "SELECT device_id, event_day, event_time, event_id, " +
        "event_type, payload " +
        "FROM telemetry_mapper.events_by_device_day " +
        "WHERE device_id = :deviceId AND event_day = :eventDay " +
        "AND event_time >= :fromInclusive " +
        "AND event_time < :toExclusive LIMIT :maxRows")
    PagingIterable<EventRecord> findWindow(
        String deviceId,
        LocalDate eventDay,
        Instant fromInclusive,
        Instant toExclusive,
        int maxRows);
}
~~~

**Practical note:** `@Select` and `@Insert` generate statements from entity metadata, while `@Query` lets you specify custom CQL directly. Every method is validated at compile time against the return and parameter types supported by your mapper version. Enable the compiler option that preserves **parameter metadata** when required by the processor/library, and inspect generated sources when writing complex `@Query` methods.

| Method | Easy to use when | What to watch out for |
| --- | --- | --- |
| `findById` with `@Select` | Reading a single row by full primary key. | Do not substitute it for range queries or queries missing partition keys. |
| `insert` with `@Insert` | Writing a fully mapped entity. | Timestamp/TTL/null/unset behavior and retry idempotency; not a multi-table transaction. |
| `findWindow` with `@Query` | Reading a clustering range inside one partition. | Bound the time window, `maxRows`, paging, object mapping, and server tombstones. |
| Custom methods in DAO/service | Business queries that do not fit simple CRUD patterns. | Control the CQL statement, projection, CL, and instrumentation. |

**A DAO should never expose an unbounded `getAllEvents()` method** simply because Java interfaces make it easy to declare. In Cassandra, method signatures should enforce **partition-access constraints**: `deviceId`, `eventDay`, `from`, `to`, and `limit`.

## 8. `@Mapper`, the generated builder, and `CqlSession` lifecycle

~~~java
// TelemetryMapper.java
import com.datastax.oss.driver.api.mapper.annotations.DaoFactory;
import com.datastax.oss.driver.api.mapper.annotations.Mapper;

@Mapper
public interface TelemetryMapper {
    @DaoFactory
    EventDao eventDao();
}
~~~

When annotation processing runs properly, the build generates the implementation and builder—for example, `TelemetryMapperBuilder`. The application creates one long-lived session and obtains the DAO from it:

~~~java
// MapperDemo.java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class MapperDemo {
    public static void main(String[] args) {
        // Lab only; production requires TLS and proper authentication.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .withKeyspace("telemetry_mapper")
                .build()) {

            TelemetryMapper mapper =
                new TelemetryMapperBuilder(session).build();
            EventDao dao = mapper.eventDao();

            EventRecord event = dao.findById(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

            if (event != null) {
                System.out.println(event.getEventType());
            }

            // Single daily partition, half-open range.
            for (EventRecord row : dao.findWindow(
                "device-7",
                LocalDate.of(2026, 11, 21),
                Instant.parse("2026-11-21T09:00:00Z"),
                Instant.parse("2026-11-21T10:00:00Z"),
                100)) {
                System.out.println(
                    row.getEventTime() + " " + row.getEventId());
            }
        }
    }
}
~~~

### 8.1. Notes when running the example

1. Instantiate `CqlSession` **once per service lifecycle**, never inside individual HTTP handlers. The session is thread-safe across concurrent requests and manages connection pools, routing, and metadata.
2. `TelemetryMapperBuilder` is **build-generated code**, so if the IDE cannot resolve it, check Maven/Gradle annotation processing settings and generated-sources directories.
3. The default keyspace must be explicit and accurate. An entity carrying only `@CqlName("events_by_device_day")` should not implicitly depend on whatever keyspace was last selected in `cqlsh`.
4. **Consistency level** on DAO queries comes from driver config/profiles or statement attributes depending on mapper version; never assume `@Select` implies `LOCAL_QUORUM`. Check the effective configuration—such as `basic.request.consistency = LOCAL_QUORUM` when policy requires it.
5. `PagingIterable` is consumed via an iterator; **iterating to the end** may fetch multiple pages. `dao.findWindow(..., 100)` caps returned rows at 100 (`LIMIT`) but does not cap physical tombstones scanned beforehand.
6. Each row creates an entity object as it is mapped. If many rows or large payloads are returned, avoid accumulating every `EventRecord` in an unbounded `List`.
7. `@Insert` **does not automatically make an entire workflow idempotent**. A write timeout can still occur after a subset of replicas persisted the mutation.

## 9. Same CQL with the Core API reading and mapping a DTO directly

For an apples-to-apples comparison, keep the **same schema, partition key, clustering range, column projection, CL, page size, and `LIMIT`**, changing only how rows become Java objects. Core Driver example:

~~~java
// CoreReadExample.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class CoreReadExample {
    public static final class EventSummary {
        public final Instant eventTime;
        public final UUID eventId;
        public final String eventType;

        public EventSummary(Instant time, UUID id, String type) {
            eventTime = time;
            eventId = id;
            eventType = type;
        }
    }

    public static List<EventSummary> findSummary(
            CqlSession session,
            PreparedStatement prepared,
            String deviceId,
            LocalDate day,
            Instant from,
            Instant until) {

        BoundStatement statement = prepared.bind(
                deviceId, day, from, until)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        List<EventSummary> output = new ArrayList<>();
        ResultSet result = session.execute(statement);
        for (Row row : result) {
            output.add(new EventSummary(
                row.getInstant("event_time"),
                row.getUuid("event_id"),
                row.getString("event_type")));
        }
        return output;
    }

    public static PreparedStatement prepare(CqlSession session) {
        return session.prepare(
            "SELECT event_time, event_id, event_type " +
            "FROM telemetry_mapper.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? " +
            "AND event_time >= ? AND event_time < ? LIMIT 100");
    }
}
~~~

**Key difference:** this Core example **reads only three columns**, skipping `payload` and not building a full `EventRecord`. If a benchmark shows it beating the DAO from Section 8, **you cannot attribute the entire gap to the mapper**, because the projections differ. To isolate pure mapping overhead, both paths must select the **same columns**; to evaluate the architectural benefit for a summary endpoint, compare realistic versions matching actual data requirements.

### 9.1. Comparing the two approaches on the right criteria

| Criterion | Mapper/DAO | Core `Row`/prepared | Decision guidance |
| --- | --- | --- | --- |
| Boilerplate | Low for common CRUD/lookups. | Explicit binding and getters for every query. | DAOs shine with many tables and long-term maintenance. |
| Type safety/mapping | Annotation-driven with codegen; easy to read entities. | Column names and types live at call sites; needs tests. | Both break if runtime schema diverges. |
| Column projection | Optimizable via `@Query`, projections, or narrow DTOs. | Easy to select exact subsets of columns. | Select **only the required columns** on hot paths. |
| Object allocation | Entity plus property allocations. | Implementation-dependent; can avoid DTOs or use tiny DTOs. | Benchmark real allocation and GC behavior. |
| Paging | Handled by core driver; mapper wraps result API. | Direct core driver paging. | Bound page size and total rows in both. |
| CQL/routing | Depends on the query emitted by the DAO. | Depends on the query written by the developer. | Verify full partition keys are bound. |
| Schema migration | Entity/DAO must be updated and recompiled. | Queries and `Row` mappings must also be updated. | Run integration tests pinned to schema versions. |
| Instrumentation | May need interceptors, wrappers, profiles, or query names. | Easy to wrap statements and measure fine-grained steps. | Ensure observability stays transparent. |

**There is no universal rule that "Core is always faster" or "mapper is always free."** Execution shape, column count, and row count usually dominate abstraction overhead, though on ultra-hot read paths, per-row object allocation can become significant.

## 10. Abstraction overhead: six components to separate

A useful mental model:

~~~text
Total Java call time
  ≈ admission / queue wait
  + statement preparation / binding
  + routing + network to coordinator
  + coordinator / replica read-write work
  + response transfer and paging
  + CQL decode + Row -> Entity/DTO conversion
  + post-mapping business logic

Across multiple pages or statements, multiple rounds of
network, paging, query execution, and mapping add up.
~~~

This breakdown is a **qualitative model**; it does not claim every phase is strictly sequential or linearly additive in every implementation. With async concurrency, stages overlap and require tracing or profiling to isolate.

### 10.1. Cost 1 — Prepared statements and initialization

The mapper prepares/caches statements internally; the Core API should likewise **prepare once and reuse**. If one side is benchmarked including prepare/initialization overhead while the other uses already-warmed prepared statements, the comparison is skewed.

**How to measure:** separate **cold-start/warm-up** from steady-state hot-path requests; warm both the mapper DAO and Core prepared statements before recording steady-state p99. For startup latency, measure `CqlSession` creation, mapper initialization, metadata loading, and query preparation independently.

### 10.2. Cost 2 — Object instantiation and allocation

Suppose a query returns **5,000 rows** and the mapper allocates 5,000 `EventRecord` instances, plus per-field objects (`String`, `UUID`, `Instant`, codec outputs):

~~~text
5,000 rows × 1 entity/row  = 5,000 entity objects
10,000 requests/min        = 50 million entity objects/min
                             (if every request returns 5,000 rows)
~~~

This multiplication is an **extreme illustration**—it excludes underlying `String`, `UUID`, `Instant`, and buffer allocations, and does not imply all objects remain live simultaneously. Still, if an application only needs a count or three fields, full-row entity mapping introduces unnecessary GC pressure.

### 10.3. Cost 3 — Column projection and payload

**`SELECT *`** forces the server to ship columns the caller never uses; the mapper cannot "un-receive payload bytes" after Cassandra sends them. If `payload` is 100 KiB of text per row and the API only needs `event_time`:

~~~text
100 rows × 100 KiB payload ≈ 9.8 MiB of payload data
Selecting only 3 small columns ≪ 9.8 MiB (depending on actual sizes)
~~~

**Do not blame the mapper when `SELECT *` is the culprit.** Consider **`@Query` with an explicit column list**, a narrow DTO, or a separate query-driven summary table. Partial-column entities must have explicit semantics—never write a **partially populated entity** back as if it represented the complete row.

### 10.4. Cost 4 — Codecs and type conversion

Driver built-ins handle `timestamp` ↔ `Instant`, `date` ↔ `LocalDate`, and `uuid` ↔ `UUID`. With UDTs, nested collections, JSON, enum/domain conversions, or custom codecs, CPU and allocation can outweigh simple field assignment.

- Do not parse large JSON inside an entity getter on every response serialization.
- Do not copy large `blob` columns into multiple byte arrays if only metadata is required.
- Benchmark custom codecs using realistic data and nesting depths.
- Register codecs according to your driver version's mechanism; a type-mapping error is not a Cassandra consistency bug.

### 10.5. Cost 5 — Paging and retaining results in memory

`PagingIterable<EventRecord>` does not necessarily hold every row in RAM upon creation. However, if the service runs:

~~~java
List<EventRecord> all = new ArrayList<>();
for (EventRecord row : dao.findWindow(
        deviceId, day, from, until, maxRows)) {
    all.add(row);
}
~~~

then **the service itself retains every object** until `all` is released. Under large `LIMIT` values, high concurrency, and heavy payloads, peak heap grows rapidly. Page size chunks network fetches, **not total rows buffered by the service**.

### 10.6. Cost 6 — Multiple DAO calls (`N+1`) and fan-out

Example anti-pattern:

~~~java
for (Device device : devices) {
    // One query per device; 10,000 devices -> 10,000 queries.
    EventRecord event = dao.findById(
        device.getId(), day, timestamp, eventId);
    // ...
}
~~~

Easy-to-call DAO methods can **hide round-trip counts**. If you need a timeline across 10,000 devices, design a table or projection keyed by `site_id`/bucket or a precomputed rollup; do not patch it with `ALLOW FILTERING` or unbounded `CompletableFuture` fan-out. When fan-out is unavoidable, enforce strict caps on **concurrency, partition count, deadline, and bytes**, and measure p99 and replica load.

## 11. `@Query` does not turn a bad query into a good one

A mapper can generate type-safe Java code, but **the CQL emitted by the DAO must still fit Cassandra's query model**.

### 11.1. Anti-pattern example: missing partition key

~~~java
// ANTI-PATTERN: DO NOT use on large production tables.
@Query(
    "SELECT device_id, event_day, event_time, event_id, " +
    "event_type, payload FROM telemetry_mapper.events_by_device_day " +
    "WHERE event_type = :type ALLOW FILTERING")
PagingIterable<EventRecord> findAllOfType(String type);
~~~

Because `event_type` is not part of the partition key or an appropriate index/access path, this query can trigger a **distributed scan across many partitions** only to filter down to a small subset. Even though `dao.findAllOfType("ALARM")` looks clean in Java, coordinator and replica costs can be severe.

**Do not treat `ALLOW FILTERING` as an optimizer hint.** It merely overrides Cassandra's refusal to run queries that risk full-cluster/multi-partition scans; it does not build an index or shrink fan-out. If the business needs alarms across all devices by site and hour, build a dedicated projection table and size its partitions, RF, and hotness properly.

### 11.2. `@Select` for primary-key lookups, `@Query` for specific access patterns

| Use case | Suitable DAO/CQL | Risk if misused |
| --- | --- | --- |
| Look up one event by full primary key | `@Select` with all of `deviceId, eventDay, eventTime, eventId`. | Low fan-out risk, though network/CL/timeouts still apply. |
| Read the 20 latest events for a day | `@Query` with full partition key + `LIMIT 20`. | Can still scan tombstones before finding 20 live rows. |
| Read a 2-hour window in a day | `@Query` with clustering range `>= start AND < end`. | Wide ranges or hot partitions still require measurement. |
| Read 3 consecutive days | **Three or four buckets** depending on boundaries and span length. | The mapper does not auto-merge or cross-partition sort. |
| Read alarms by site/hour | Separate projection table keyed by site and time bucket. | Do not abuse `ALLOW FILTERING`. |
| Monthly totals across 1 million devices | Dedicated rollup or analytics data model. | Never scan raw events via `dao.findAll()`. |

### 11.3. Half-open ranges and multi-bucket queries

Suppose an endpoint requests events in **[2026-11-20T23:45:00Z, 2026-11-21T00:15:00Z)**. The DAO's `findWindow` query reads only **one** `eventDay` at a time because `eventDay` is part of the partition key.

~~~text
Partition (device-7, 2026-11-20)
  [23:45:00Z, 2026-11-21T00:00:00Z)

Partition (device-7, 2026-11-21)
  [00:00:00Z, 2026-11-21T00:15:00Z)

Then the service merges rows by (event_time DESC, event_id tie-breaker).
~~~

When the API needs the **global top 50**, you cannot read just one bucket and return it as the top 50 for the whole range. When data is bucketed by canonical UTC day, you query the overlapping buckets, **cap the bucket count**, select per-bucket candidates, and merge them. Any `event_id` tie-breaker must align between Cassandra's clustering comparator and Java sorting; for UUIDs, verify comparator/serialization behavior rather than assuming `UUID.compareTo` matches every CQL UUID/timeuuid ordering rule.

**Maximum bucket count** is also an API guardrail. If a caller passes a 5-year range against 15-minute buckets, the mapper will not stop your service from querying tens of thousands of partitions.

### 11.4. Token-aware routing still depends on the statement

The driver can use a **fully bound partition key** for token-aware routing, choosing a coordinator close to an eligible natural replica depending on load-balancing policy and topology. The `@Dao` annotation itself does **not** guarantee good routing:

- A query omitting any component of a composite partition key cannot route as a single-partition lookup.
- Complex statements or custom CQL missing routing metadata can prevent the driver from computing the target token.
- `localDatacenter`, contact points, load-balancing policies, and replica availability still govern coordinator selection.
- `LOCAL_QUORUM` may read from multiple local-DC replicas; it does not mean "the driver contacts only a single replica directly."

If a DAO method suddenly slows down, inspect the **actual CQL, bound key shape, coordinator, RF/CL, and server metrics** before blaming annotation mapping.

## 12. Updates, `null`, `UNSET`, TTL, and tombstones: cost goes beyond CPU

In Cassandra, `INSERT` generally behaves as an **upsert**, unlike relational SQL `INSERT` statements that reject duplicate primary keys by default. Updates and deletes reconcile using mutation timestamps. Using a mapper does **not** make those semantics disappear.

### 12.1. Distinguishing "no value," "do not update," and "delete"

| Business intent | CQL/driver semantics to understand | Consequence if mis-mapped |
| --- | --- | --- |
| Keep existing column intact | Keep bind marker **UNSET** where supported by operation/version, or omit column from `UPDATE`. | Writing `null` can create unintended tombstones. |
| Clear a column value | Write `null` or issue an explicit `DELETE`. | Can unintentionally erase prior values. |
| Set a new value | Bind the new value with an appropriate mutation timestamp and TTL. | If timestamp is lower than the existing cell, the write will not win. |
| Value unknown from partial projection | Java field may be `null` because the column was not selected. | Saving a partial entity back can wipe data if nulls are written. |

In CQL, writing `null` to a column can act as a **cell deletion**, generating a tombstone; **UNSET** in the driver means "do not write this field" where supported. Mapper **null-saving strategy** annotations and options vary by method and version. **Never guess the default**; inspect generated statements, review annotation settings, and write integration tests covering null fields.

### 12.2. Example single-column scoped update

~~~sql
UPDATE telemetry_mapper.events_by_device_day
SET payload = '21.7'
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:01:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174002;
~~~

An `UPDATE` targeting **only the changed column** avoids accidentally overwriting other null Java properties. You can expose it on the DAO with a targeted `@Query` when the use case calls for it:

~~~java
// Additional method on EventDao:
@Query(
    "UPDATE telemetry_mapper.events_by_device_day SET payload = :payload " +
    "WHERE device_id = :deviceId AND event_day = :eventDay " +
    "AND event_time = :eventTime AND event_id = :eventId")
void updatePayload(
    String payload,
    String deviceId,
    LocalDate eventDay,
    Instant eventTime,
    UUID eventId);
~~~

**Never call `@Update` on a partial entity holding only two loaded fields and assume the remaining null fields will be left untouched.** Actual behavior depends on the null-saving strategy, annotations, and generated CQL. Partial updates require an explicit contract between service and DAO.

### 12.3. TTL is not automatically derived from `event_time`

~~~sql
-- Example writing a new value with a 3600-second time-to-live.
UPDATE telemetry_mapper.events_by_device_day
USING TTL 3600
SET payload = 'temporary reading'
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time = '2026-11-21T09:01:00Z'
  AND event_id = 123e4567-e89b-42d3-a456-426614174002;
~~~

TTL is calculated **from when the mutation is written** under Cassandra semantics—it is **not automatically computed from the `event_time` column**. If a DAO calls `@Insert` again on an old row with a new TTL, retention gets extended. If data undergoes deletes/TTLs and the mapper does not preserve original mutation timestamps, backfills or retries can resurrect stale data by overwriting tombstones.

### 12.4. LWTs, counters, and batches are not ORM transactions

- `IF NOT EXISTS` or `UPDATE ... IF ...` triggers **lightweight transactions (CAS)** where needed, carrying coordination and latency costs. The mapper does not make CAS free.
- `counter` columns have different semantics and retry risks than idempotent upserts; never blindly re-increment a counter after an ambiguous timeout.
- `BEGIN BATCH` provides Cassandra's specific batch atomicity guarantees, **not JPA-style multi-partition isolation**, and large multi-partition batches can overload coordinators.
- Calling `dao.insertA()` followed by `dao.insertB()` in a service does not create an atomic transaction; keeping two tables consistent requires event logs, idempotency, or reconciliation.

**Right mindset:** a DAO hides statement construction boilerplate; it **does not hide Cassandra's mutation and consistency model**.

## 13. Mapping collections, UDTs, enums, and custom types

Cassandra supports `list`, `set`, `map`, tuples, UDTs, blobs, and primitives. These types are useful, but they are not an unrestricted relational ORM "object graph."

### 13.1. Budgeting cost when collections are present

Suppose an entity includes a `map<text, text>` containing 20,000 entries. A query only wants `eventType`, yet the entity/statement selects the large map as well:

- Nodes must transfer significantly more bytes.
- The driver must decode the map and allocate Java collections/entries.
- GC pressure and HTTP/JSON serialization CPU rise.
- Updating large collections or deleting many elements incurs dedicated storage and tombstone overhead.

**Do not model an unbounded one-to-many relationship as a collection inside one Cassandra row.** Usually, modeling **multiple rows via clustering keys** yields predictable partition sizing and bounded range reads.

### 13.2. UDTs and custom codecs

| Requirement | Recommended approach | What to measure |
| --- | --- | --- |
| Small, stable UDT | Declare driver-compatible UDT mapping/codec. | Decode CPU, null fields, schema evolution. |
| Application enum | String/int mapping or explicitly versioned codec. | Compatibility when adding new enum values. |
| Large JSON payload | Store as text/blob and parse only when needed. | Network bytes, JSON parser allocation, and GC. |
| Currency / high-precision numbers | Matching CQL/Java decimal types; avoid careless conversion to float. | Correctness, rounding, and schema compatibility. |
| Multi-MB blobs | Consider object storage plus metadata in Cassandra. | Message size, row size, heap/direct memory, and latency. |

**Warning:** custom codecs can throw runtime failures when columns or schemas change. Compile-time mapper generation validates Java/annotation structure; it **does not prove every real-world data value will decode cleanly**. Integration tests must cover `null`, empty/large collections, legacy records, and mixed UDT versions.

## 14. Synchronous, asynchronous, and concurrency bounds

Synchronous DAO methods can be simple and sufficient for short lookups. However, an API reading dozens of buckets or a producer ingesting high-volume events must track **in-flight statements**. The mapper does not enforce service-level concurrency limits automatically.

### 14.1. Asynchronous Core Driver interface

~~~java
// Same CqlSession and PreparedStatement; only the execution path changes.
CompletionStage<AsyncResultSet> future = session.executeAsync(boundStatement);
future.whenComplete((page, error) -> {
    if (error != null) {
        // Log error_type/correlation ID; never log credentials or payloads.
        return;
    }
    // page is an async result page; for multi-page SELECTs,
    // call fetchNextPage() per your API/version rather than assuming all rows arrived.
});
~~~

This snippet is an **in-method illustration** assuming `CompletionStage`, `AsyncResultSet`, and a bound `boundStatement`. Your DAO/mapper version may also support async return types; use **return types officially supported by the processor** rather than assuming any `CompletableFuture` signature will compile cleanly.

### 14.2. Writing with bounded concurrency

The example below uses the Core Driver to demonstrate **bounded in-flight execution** even in applications where most reads go through the mapper:

~~~java
// BoundedEventWriter.java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public final class BoundedEventWriter {
    private static final int MAX_IN_FLIGHT = 8;

    public static void writeLabBatch(
            CqlSession session, List<EventRecord> events)
            throws InterruptedException {

        PreparedStatement insert = session.prepare(
            "INSERT INTO telemetry_mapper.events_by_device_day " +
            "(device_id, event_day, event_time, event_id, event_type, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");

        Semaphore permits = new Semaphore(MAX_IN_FLIGHT);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger uncertain = new AtomicInteger();
        List<CompletableFuture<Void>> completions = new ArrayList<>();

        for (EventRecord e : events) {
            // Blocks the caller thread, NEVER a driver I/O callback thread.
            permits.acquire();
            BoundStatement write = insert.bind(
                    e.getDeviceId(), e.getEventDay(),
                    e.getEventTime(), e.getEventId(),
                    e.getEventType(), e.getPayload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            CompletableFuture<Void> done = new CompletableFuture<>();
            completions.add(done);
            try {
                session.executeAsync(write).whenComplete((result, error) -> {
                    try {
                        if (error == null) {
                            success.incrementAndGet();
                            done.complete(null);
                        } else {
                            uncertain.incrementAndGet();
                            done.completeExceptionally(error);
                        }
                    } finally {
                        permits.release();
                    }
                });
            } catch (RuntimeException dispatchError) {
                uncertain.incrementAndGet();
                done.completeExceptionally(dispatchError);
                permits.release();
            }
        }

        try {
            CompletableFuture.allOf(
                completions.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException ex) {
            System.err.println("At least one write did not ACK");
        }
        System.out.println("acked=" + success.get()
            + " failed_or_unknown=" + uncertain.get());
    }
}
~~~

**What this code accomplishes:** caps async writes at eight in flight within this loop; callbacks stay lightweight and never block I/O threads; `PreparedStatement` is reused. **What it does not provide:** durable retry queues, per-tenant or global rate limits, API deadlines, cancellation, TTL/timestamp preservation, idempotency, or crash recovery. Do not drop it unmodified into a lossless production ingestion pipeline.

A `WriteTimeout` represents an **ambiguous partial-write outcome**, not proof that nothing was written. Retrying with a freshly generated `eventId` can create duplicates; safe retries require deterministic primary keys and consistent mutation timestamp/TTL handling.

### 14.3. Multi-layer concurrency limits

~~~text
API admission capacity   : 100 requests/process (example)
API waiting queue        : max 200 requests (example)
DB in-flight per process : max 32 statements (example)
Driver request throttler : separate budget if enabled
Global fleet             : sum across N pods and all workloads
~~~

If a service runs 30 pods and each allows 32 in-flight DB statements, the simple ceiling is **30 × 32 = 960** fleet-wide in-flight statements—before counting retries, batch jobs, speculative execution, or neighboring services. This is **not** TCP connection count or requests/second. Benchmark **coordinator and replica capacity** before raising these limits.

## 15. Fair benchmarking: mapper overhead or CQL overhead?

### 15.1. Defining three isolated experiments

| Test | CQL/column projection | Java mapping | Question answered |
| --- | --- | --- | --- |
| **A. Mapper full entity** | All six columns, proper partition/range, `LIMIT 100`. | `Row → EventRecord` via generated mapper. | What is the cost of the current mapper endpoint? |
| **B. Core full entity** | **Same six columns** as A, same CL/page/limit. | Populate `EventRecord` with manual Core code. | What is the **mapping implementation** delta with CQL held constant? |
| **C. Core narrow DTO** | Only `event_time, event_id, event_type`. | `Row → EventSummary` narrow DTO. | How much does narrowing projection save for this endpoint? |

If C beats A dramatically while B tracks close to A, the likely explanation is **excess payload/column reads**, not "the mapper is slow." Conversely, only if A trails B under identical CQL, row counts, and GC conditions should you investigate generated mapper/codec/allocation overhead.

### 15.2. Controlling confounding variables

1. **Identical Cassandra, driver, and JDK versions**, hardware, CL, RF, DC, TLS, request timeouts, and retry policies.
2. **Identical data and query shapes**, including hot/cold partitions, TTL/tombstones, and payload sizes.
3. **Prepare and warm up both paths**; do not fold cold-start mapper initialization into steady-state latency and compare it against a warmed Core prepared statement.
4. **Identical page size**, row limits, and **consume the exact same number of pages**. Never compare time-to-first-page against full-result consumption.
5. **Isolate warm caches vs. cold disk** or randomize test order; later runs can benefit from caches populated by earlier runs.
6. **Hold concurrency steady**, along with pod count, request mix, burst profile, rate limiting, retries, and sampling.
7. Measure **allocation/GC, CPU, bytes received, rows/sec, and p50/p95/p99 latency** alongside server metrics simultaneously.
8. Verify **logical output equivalence**; a path that looks faster because it drops columns or rows is an invalid comparison.
9. Run across sufficient samples and time windows for stability; **100 requests cannot establish a reliable p99**.
10. Treat **JMH microbenchmarks at the Java mapping layer** and **end-to-end load tests** as separate disciplines: JMH does not reflect network or replica behavior.

### 15.3. Simulated result table for practicing interpretation

| Metric | Mapper full A | Core full B | Core narrow C |
| --- | ---: | ---: | ---: |
| `LIMIT` | 100 | 100 | 100 |
| Bytes/response (test estimate) | 900 KiB | 900 KiB | 45 KiB |
| Client p99 | 32 ms | 30 ms | 16 ms |
| Mapping CPU/row | 1.2 simulated units | 1.0 unit | 0.6 units |
| Allocation/request | 450 KiB | 410 KiB | 110 KiB |
| Data logically equivalent? | Yes | Yes | Yes, per summary contract |

**These numbers are purely illustrative**, not an actual benchmark of Cassandra or the Java Driver. The example shows how **reducing returned data** can outweigh switching from a mapper to hand-written Core code. There are also workloads where object mapping becomes material—for instance, tiny cached rows streamed at very high rows/second.

### 15.4. Estimating impact at scale

~~~text
Assume:
  each request adds 100 KiB of mapping allocation
  2,000 requests/s

Additional allocation rate ≈ 200,000 KiB/s ≈ 195 MiB/s
  (not long-lived heap; this is allocation rate).

If GC and application heap are near saturation, this added rate
can degrade p99 even while Cassandra server latency stays flat.
~~~

Allocation rate differs from **live heap size** and from driver direct/off-heap buffers; confirm with **JFR, allocation profilers, and GC logs** rather than relying solely on back-of-the-envelope formulas.

## 16. Tracing, metrics, and layered p99 analysis

### 16.1. Cassandra-side commands and observations

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool proxyhistograms
nodetool tablestats telemetry_mapper.events_by_device_day
nodetool tablehistograms telemetry_mapper events_by_device_day
nodetool gcstats
~~~

Quick reference:

| Tool/metric | Signals to watch |
| --- | --- |
| `tpstats` | Pending, blocked, or dropped tasks; is the coordinator or replica overloaded? |
| `compactionstats` | Pending compactions; does disk pressure line up with p99 spikes? |
| `tablestats` | SSTable counts, partition/tombstone/latency statistics by version. |
| `tablehistograms` | Per-table latency distribution, partition size, and cell-count histograms. |
| `proxyhistograms` | Coordinator-side latency compared against client p99. |
| `gcstats`/JVM logs | Do GC pauses correlate with slow queries? |
| Client metrics | In-flight requests, driver queues, retries, page fetches, and mapping CPU. |

Command names, arguments, and metric outputs vary across Cassandra versions. Never compare cumulative `nodetool` counters since node startup directly against a 5-minute p99 window without normalizing time intervals.

### 16.2. Tracing a query in the lab

~~~sql
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT device_id, event_day, event_time, event_id, event_type, payload
FROM telemetry_mapper.events_by_device_day
WHERE device_id = 'device-7'
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T09:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;

TRACING OFF;
~~~

`TRACING` and `CONSISTENCY` are **cqlsh commands**; in the Java Driver, enable tracing via statement options supported by your version. Tracing reveals coordinator/replica execution steps for a single statement, **not the CPU spent instantiating `EventRecord` in your application JVM**.

**To tell whether mapper decoding is slow**, measure from the client:

- Time to first page and time to consume all results.
- Rows and bytes received.
- CPU samples and allocation hot spots inside generated DAOs and mapping code.
- Driver retries, speculative executions, queue waits, and network RTT.
- DAO call count per API transaction (`N+1`).

### 16.3. Instrument by query template, not individual partition keys

Suggested telemetry event format:

~~~text
timestamp_utc     = 2026-11-21T09:05:00Z
service           = telemetry-api
query_name        = events_find_window_mapper
path              = mapper | core
environment       = staging
local_dc          = dc1
consistency       = LOCAL_QUORUM
result_rows       = 50
result_bytes      = measured-or-estimated
pages_fetched     = 1
elapsed_ms        = 25
error_type        = none
~~~

Never put `device_id`, `event_id`, request UUIDs, or raw CQL containing private literals into metric labels: **cardinality and data-leakage risk** explode. Keep access to raw logs restricted; metric labels must remain low-cardinality and bounded. Correlation IDs belong in logs or traces per policy, not p99 histogram labels.

## 17. Correctness testing and schema regression checks

A clean annotation-processor compile proves only that Java and mapper constraints match **source code and annotations**. It does not prove production schemas, roles, RF, or real data match the code.

### 17.1. Recommended test suite

| Test | Scenario | Expected outcome |
| --- | --- | --- |
| **Mapper generation** | Clean build with annotation processor enabled. | `TelemetryMapperBuilder` is generated with zero processor errors. |
| **Column/key mapping** | Load `device-7` for Nov 21 using full PK. | Every field matches its type; partition/clustering keys are not swapped. |
| **Composite key mismatch** | Query with wrong `eventDay` or missing key part. | Must never silently read the wrong partition or scan the cluster. |
| **Time boundary** | Ranges `[23:59:59Z, 00:00:00Z)` and the next day. | No double-counting and no dropped events at UTC boundaries. |
| **Null/unset** | Update one field while other fields are null. | No unintended deletes; only the target cell is modified. |
| **TTL** | Backfill or re-insert expiring records. | Retention is not unintentionally extended against business rules. |
| **Schema drift** | Staging drops or renames a column. | Integration test fails with a clear diagnostic message. |
| **RBAC** | Readonly role attempts `SELECT`, then `INSERT`/`DELETE` in lab. | Proper allow/deny behavior; never run as superuser. |
| **CL/replica failure** | RF=3, `LOCAL_QUORUM`, one replica slowed or stopped cleanly. | Expected error handling and SLO compliance; no retry storm. |
| **Paging/memory** | 10,000 tiny rows and 100 large-payload rows. | Bounded heap, measured consumption time, no OOM. |
| **High concurrency** | Parallel DAO calls with pool and rate limits active. | Queues stay bounded and p99 meets SLO. |
| **Migration** | Rolling column, UDT, or driver version upgrades. | Generated mapper stays compatible across old/new clients. |

### 17.2. Testing mapping at the service boundary

~~~java
// Pseudo-test structure, independent of any specific test framework:
EventRecord actual = dao.findById(
    "device-7", LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:00:00Z"),
    UUID.fromString("123e4567-e89b-42d3-a456-426614174001"));

if (actual == null
        || !"HEARTBEAT".equals(actual.getEventType())
        || !"ok".equals(actual.getPayload())) {
    throw new AssertionError("Cassandra mapper mapping mismatch");
}
~~~

This is only a **single-row smoke check**, not full table verification. Integration tests should run against controlled Cassandra versions, schemas, and DC names using lab datasets isolated from production.

### 17.3. Equivalence tests for a Core API replacement

If a hot path switches from the mapper to Core `Row`, verify **functional equivalence** across edge cases:

- `null` and empty column values.
- Events sharing an `eventTime` but differing in `eventId`.
- Time windows straddling day/bucket boundaries.
- Expired TTLs/tombstones, retries, and write timeouts.
- Newly added columns or UDT fields in the schema.
- Multi-page iteration with a partially filled final page.

If Core code is faster because it misorders events or drops meaningful fields, it is **not a valid optimization**.

## 18. Security: a clean DAO does not replace authorization

Exposing only `findById` and `insert` on a DAO helps prevent arbitrary queries in application code. Still, **Cassandra enforces authorization on CQL resources**:

1. The Java service uses a **dedicated least-privilege identity** granted only `SELECT`/`MODIFY` on required tables—never a shared superuser.
2. CQL native connections use TLS with proper server/certificate verification; never disable peer validation to silence errors.
3. CQL authorization governs **tables/keyspaces**, not tenant ownership encoded inside a partition key. The service must authorize tenant access before binding `deviceId`.
4. `@Query` uses named or positional bind markers rather than concatenating user input into CQL strings.
5. JMX/`nodetool`, OS/filesystem access, and backups use separate permission models; `SELECT` access never implies administrative rights.
6. Never log passwords, access tokens, raw payloads, or personal data in exceptions, logs, or traces.

### 18.1. Enforcing tenant isolation at the service layer

~~~java
// Service-boundary illustration; the mapper does not enforce tenant security:
public EventRecord readAuthorizedEvent(
        Caller caller, String deviceId, LocalDate day,
        Instant time, UUID eventId) {
    if (!authorizationService.canReadDevice(caller, deviceId)) {
        throw new SecurityException("not authorized for this device");
    }
    return dao.findById(deviceId, day, time, eventId);
}
~~~

This example assumes application-provided `Caller`, `authorizationService`, and `dao`. **Never** expose `dao.findById` directly in an endpoint assuming table-level RBAC stops one tenant from querying another tenant's devices.

## 19. Classifying DAO errors: `null` means not found, timeout does not

When a single-row lookup returns an entity or `null`, services often translate that into HTTP 200 or 404 per the API contract. That is fundamentally different from **Cassandra failing to respond in time**.

| Condition | Meaning | Business handling |
| --- | --- | --- |
| `@Select` returns `null` after a successful read | No live row matched the query at that CL at read time. | Returning 404 is appropriate if aligned with the API contract. |
| Server `ReadTimeout` | Coordinator failed to gather enough replica responses/data before timeout. | Return temporary error/503 or retry within budget if safe; never turn into 404. |
| Driver request timeout | Driver exceeded its request or attempt timeout semantics. | Inspect deadlines, queues, network, and retries; do not assume the row is missing. |
| `Unavailable` | Fewer live replicas available than required by CL. | Check RF, DC health, and nodes; raising timeouts will not create replicas. |
| `Unauthorized` | Service identity lacks permission on the table/resource. | Fix RBAC/provisioning; never swap to a superuser account. |
| `CodecNotFound`/mapping error (name varies by version) | Unable to convert between CQL and Java types. | Check schema, annotations, codecs, and stored data. |
| `WriteTimeout` | Did not receive enough ACKs within the timeout. | Mutation state is ambiguous; requires idempotency and reconciliation. |

### 19.1. Do not swallow exceptions into empty results

~~~java
// ANTI-PATTERN: masks database failures as "record does not exist."
try {
    return dao.findById(deviceId, day, time, eventId);
} catch (RuntimeException ignored) {
    return null;
}
~~~

That method causes **false 404 responses** during Cassandra timeouts or revoked credentials. Better practice:

1. Catch and classify **exception types** at the service boundary or API exception mapper.
2. Record `query_name`, request correlation ID, and UTC timestamp without exposing sensitive partition keys.
3. Drive retry policy from **operation type (read/write), idempotency, CL, and remaining deadline**.
4. Never endlessly retry auth, permission, or schema-validation errors.
5. Distinguish **not found, temporarily unavailable, permanent bad request, and unknown write outcome** in the API contract.

**The mapper does not alter error semantics**—only how results are represented in Java.

### 19.2. Query timeouts through the mapper vs. total API time

If a DAO issues three `findWindow` calls across three buckets, each with a 2-second statement timeout, that **does not mean the API finishes in 2 seconds**. Sequential execution compounds latency, and each statement triggers separate page fetches. The service must enforce:

- An **overall request deadline** measured from admission, covering queue wait, DAO calls, and merge/sort.
- A **cap on bucket/shard count** queried per request.
- **Bounded concurrency**, never firing hundreds of parallel DAO calls per request.
- A **retry budget** bounded by remaining deadline time.
- **Byte/row thresholds** to prevent unbounded payload responses.

Upon timeout, client-side cancellation **does not guarantee replicas stop work immediately**, so admission control and backpressure remain essential.

## 20. Evolving schemas and DAOs: safe rollout workflow

A mapper compiled against an old schema can **build cleanly** even after columns, UDTs, or primary keys changed in a running Cassandra cluster. Without ordered rollouts between schema changes and Java deployments, failures surface only under live traffic.

### 20.1. Expand–migrate–contract

~~~mermaid
flowchart TD
    A["Table V1 + DAO V1 serving traffic"] --> B["EXPAND: add compatible columns / V2 table"]
    B --> C["Deploy read/write-compatible code"]
    C --> D["Backfill + dual-write/CDC if primary key changes"]
    D --> E["Reconcile keys/values, TTLs/deletes, and late events"]
    E --> F["Shadow reads + canary DAO V2"]
    F --> G{"Correctness, p99, GC, RF/CL met?"}
    G -->|No| H["Stay on V1, fix mapping/pipeline and retest"]
    H --> D
    G -->|Yes| I["Switch reads to V2, keep rollback path"]
    I --> J["Retire V1 after backup and approval"]
~~~

| Schema change | Action needed in entity/DAO | Risk |
| --- | --- | --- |
| Add a regular column | Add property/annotation if read/written; test `null` on legacy rows. | Old rows return `null`, and full-entity queries pull more bytes. |
| Rename a column | Coordinate schema change with `@CqlName` and query templates. | Mixed-version clients referencing the old name will break. |
| Change `text` to UDT/collection | Usually needs a schema migration / new table and codec. | Decoding, correctness, and performance—never auto-cast blindly. |
| Change partition or clustering key | **New table + data migration**, plus new DAO. | Token/replica placement, backfill, updates/deletes/TTL, and rollback. |
| Add query-specific projection | Separate DAO/query plus projection update pipeline. | Partial failure during dual-writes causes data drift. |

**Never expect `ALTER TABLE` to reshape an existing primary key.** Cassandra places data by partition-key token, so changing keys alters storage layout and query direction. Under active writes, dual-writes require durable mutation capture/catch-up; two `dao.insert()` calls across two tables are **not automatically atomic**.

### 20.2. Mapper version and driver version

For every release:

1. Pin the exact **driver core + mapper runtime + mapper processor** versions alongside the JDK version.
2. Build generated code from a **clean build**, never stale generated sources on a developer workstation.
3. Test against the target Cassandra version, CQL schema, and feature set.
4. Order rollouts properly: prepare schema first, deploy compatible client code next, and drop old columns/tables last.
5. In staging, run **allow/deny CQL RBAC tests**, prepared-query tests, null/UDT/paging tests, and load tests.
6. Canary a small subset of Java instances, tagging `mapper_version` and `driver_version` as low-cardinality deployment/metric metadata.
7. Remove legacy DAO methods only after **every client and batch job** has migrated, including daily or monthly scheduled jobs.

### 20.3. Treating the DAO interface as a versioned contract

A signature like `findWindow(deviceId, day, start, end, maxRows)` is a **query contract**. When migrating from daily buckets to hourly buckets, do not keep the exact signature and silently derive a single `eventHour` from `day`, or the API will drop data. Instead:

- Introduce `EventDaoV2` alongside a service read router controlled by a migration feature flag; or
- Keep a domain-level `EventRepository` interface backed by the new DAO, verified by **integration tests spanning full time ranges**.

Never mistake changing a Java annotation for completing a schema migration.

## 21. Case study: timeline API slows down 2× after adopting the mapper

Suppose an API returns a device's 20 latest events. Before the change, the Core Driver path selected only `event_time, event_id, event_type` into a compact DTO. After adopting the mapper, the code switched to a full-entity `@Select`/query fetching `payload` as well, then serialized only summary fields for HTTP.

### 21.1. Simulated evidence

| Observation | Before (Core narrow) | After (Mapper full) | Clue |
| --- | ---: | ---: | --- |
| Columns selected | 3 | 6 | **The two setups differ in projection**. |
| Bytes/response | 20 KiB | 600 KiB | Payload likely dominates network and decoding. |
| Coordinator read latency p99 | 14 ms | 16 ms | Small server increase; check other layers. |
| Client full-consume p99 | 25 ms | 53 ms | Client/network/mapping layers added overhead. |
| Allocation/request | 120 KiB | 1.2 MiB | Can trigger GC pressure under high concurrency. |
| API response bytes | 5 KiB | 5 KiB | Payload was fetched from Cassandra and then discarded. |

**These figures are illustrative only.** Do not cite them as real benchmarks or conclude that mappers always double latency.

### 21.2. Investigation workflow

1. **Inspect the actual CQL on both paths**, comparing projection, partition key, clustering range, `LIMIT`, CL, and page size.
2. Check driver request counts, retries/speculative attempts, and time to first vs. final page.
3. Measure response bytes, row counts, allocation/GC, JSON serialization CPU, and payload size.
4. Compare server latency, tombstones, and SSTable/compaction pressure; if server latency jumped too, **do not tune only Java objects**.
5. Test a `@Query` returning only required columns or a summary table/DTO, while keeping the mapper for standard CRUD/lookups.
6. Run the **three A/B/C experiments from Section 15**, roll out a controlled canary, and verify p99 and correctness.
7. Maintain a rollback feature flag or previous artifact, and observe peak traffic instead of a three-row `main()` smoke test.

**The fix may be keeping the DAO and tightening its projection**, rather than ripping out the entire abstraction layer. In large codebases, losing maintainability and duplicating CQL carries real long-term cost; base the trade-off on measurements.

### 21.3. When should you bypass the mapper on one hot path?

Consider a pipeline streaming millions of small rows/second strictly to compute an aggregate. If:

- `@Query` already minimizes columns, server latency is stable, and network is not the bottleneck;
- Profiling proves mapper bean instantiation and codecs consume substantial CPU/GC;
- The Core API can stream `Row` directly and eliminate per-row entity allocations;
- Integration tests and benchmarks confirm identical functional output;

then using the **Core API selectively on that hot path** is justified. **DAOs are not inherently slow**; the point is having evidence that mapping adds avoidable cost without matching value on that workload.

## 22. Decision matrix: mapper, Core API, or projection table?

| Situation | Approach worth considering | Rationale |
| --- | --- | --- |
| Full primary-key CRUD/lookups across a multi-person team | **Mapper/DAO** | Clear code, low boilerplate, easy schema/mapping tests. |
| A few custom queries with clear partition/range keys | **`@Query` inside DAO** | Keeps a domain-friendly API while keeping CQL explicit. |
| Streaming or aggregating millions of tiny rows | **Core `Row` or lightweight DTO** | Reduces allocations once confirmed by a profiler. |
| Endpoint needs only 3 of 20 columns | **Narrow projection** via `@Query`, Core, or summary table | Cut wire bytes before debating mapper overhead. |
| Querying across hundreds of buckets | **Data model / rollup redesign + bounded fan-out** | Neither mapper nor Core fixes multi-partition scan cost. |
| Filtering on a non-partition-key column | **Query-specific table or evaluated index** | `ALLOW FILTERING` never creates a cheap access path. |
| Domain requires joins, graph traversal, or multi-partition ACID | **Re-evaluate storage architecture and fit** | Cassandra's mapper does not turn Cassandra into an RDBMS. |
| Optimizing without measurements | **Keep the simpler path and measure first** | Avoid invasive rewrites that miss the actual bottleneck. |

### 22.1. Team-level checklist for choosing an abstraction

Ask these questions in order:

1. **Does the Cassandra query hit the right partition/range with bounded rows and minimal columns?**
2. **Is the CQL round-trip count per API call reasonable?**
3. **Is the client reusing `CqlSession`, prepared statements, and proper paging?**
4. **Are server p99, compaction, or tombstones the true bottleneck?**
5. **Does profiling prove mapping/GC accounts for a significant share?**
6. **How much testing and maintenance complexity does Core API code add?**

Only after questions 1–4 are settled and question 5 has clear profiler evidence should stripping away the abstraction layer become a priority.

## 23. Runbook when DAO errors occur or p99 spikes

~~~mermaid
flowchart TD
    A["DAO error / p99 regression"] --> B{"Build mapping or runtime?"}
    B -->|Build| C["Processor / dependencies / generated sources"]
    B -->|Runtime| D["Capture query name, CQL shape, error class, DC/CL"]
    D --> E{"Auth/Unauthorized/Schema/Codec error?"}
    E -->|Yes| F["Check identity, schema, CQL types, mapper annotations"]
    E -->|No| G["Compare app/driver/coordinator/replica latency"]
    G --> H{"Server scan/disk/replica slow?"}
    H -->|Yes| I["Fix query/data model, curb fan-out, compaction/repair"]
    H -->|No| J["Measure projection/bytes, mapping CPU, allocation, and GC"]
    J --> K["Compare Mapper full / Core full / narrow DTO"]
    C --> L["Integration tests + load test + canary"]
    F --> L
    I --> L
    K --> L
    L --> M{"SLO + correctness + resources met?"}
    M -->|No| N["Roll back change, keep incident open"]
    M -->|Yes| O["Document evidence, roll out safely"]
~~~

### 23.1. Priority diagnostic checklist

1. **Confirm environment:** exact Driver/Core/mapper-processor versions, Cassandra version, schema, JDK, keyspace, local DC, and RF/CL.
2. **Classify the error:** mapping/build, codec, auth, unavailable, read/write timeout, overload, tombstones, or application exception.
3. **Inspect the emitted statement:** does `SELECT` use `*`, does `WHERE` supply the full partition key, and what are `LIMIT`, clustering range, bucket count, and page size?
4. **Measure client behavior:** request rate, in-flight count, driver throttling/queueing, retries, bytes/rows, time to first/all pages, allocation, and GC.
5. **Measure server behavior:** `tpstats`, `compactionstats`, tombstone/partition stats, disk latency, replica health, and inter-DC network.
6. **Verify correctness:** null-field mapping, UUID/timestamp/UTC handling, TTL, deletes, data shapes, and boundary conditions.
7. **Apply the minimal fix:** trim columns/bytes, fix CQL, bound fan-out, or add a narrow projection; drop down to custom Core code only when profiling points squarely at mapping.
8. **Run staging + canary:** match production traffic and data shapes, and observe p95/p99, throughput, and errors long enough to be meaningful.
9. **Prepare rollback:** retain prior artifacts/versions, feature flags, data hygiene, and a mutation-handling plan for table migrations.
10. **Record post-check evidence:** confirm latency, memory/GC, server resources, and correctness—never rely on `HTTP 200` alone.

## 24. Self-check exercises with answers

**Exercise 1.** Does the 4.x mapper necessarily use Java reflection on every field of every row like a dynamic ORM?

**Answer:** **No.** The mapper uses annotation processing to generate code at compile time. Even so, the generated code still performs decoding, object allocation, and field assignment, which can drive allocation and GC.

**Exercise 2.** An entity has `@PartitionKey(0) deviceId` and `@PartitionKey(1) eventDay`. If `findWindow` omits `eventDay`, will the mapper automatically scan all days?

**Answer:** **No.** A composite partition key requires every component for deterministic routing; querying across multiple days requires explicit bucket traversal or a dedicated table/projection.

**Exercise 3.** A team migrates a 3-column Core query to a 6-column full-entity mapper query and observes an 80% latency increase. Can they conclude that 80% comes from object mapping?

**Answer:** **No.** The experiment changed both projection/bytes and mapping implementation. They must benchmark **Core full vs. mapper full on identical CQL** alongside allocation profiling, then measure the narrow DTO separately.

**Exercise 4.** How does `dao.findById(...)` returning `null` after a successful read differ from a `ReadTimeout`?

**Answer:** `null` indicates no live row matched the lookup according to the read response; `ReadTimeout` means the read failed to finish before the deadline and **must never be converted into an empty/404 result**.

**Exercise 5.** Cassandra uses `PRIMARY KEY ((device_id, event_day), event_time, event_id)`. An API asks for `23:45` on Nov 20 to `00:15` on Nov 21 UTC. Is a single `findWindow` for Nov 20 sufficient?

**Answer:** **No.** Events on Nov 21 live in a different partition. You must query both buckets with appropriate half-open ranges, then merge/sort and apply any global limit.

**Exercise 6.** A service runs 25 pods, each capped at 40 in-flight CQL statements. Under this simple model, what is the fleet-wide concurrency ceiling?

**Answer:** `25 × 40 = 1,000` in-flight statements across the fleet, excluding other services, retries, or speculative executions. This is neither TCP connection count nor requests/s throughput.

**Exercise 7.** An object mapper maps a 100 KiB `payload`, while the UI only needs `event_time` and `event_type`. What should you consider first?

**Answer:** **Narrow the column projection**, returning a compact DTO or reading from an appropriate summary table, because eliminating unnecessary bytes transferred and decoded usually matters far more than changing how Java objects are built.

**Exercise 8.** An entity was loaded by a query selecting only two columns, leaving all other fields `null`. Is it safe to call `@Insert` or `@Update` with that object to modify just those two columns?

**Answer:** **Do not assume it is safe.** Depending on the generated statement and null-saving strategy, `null` can issue cell deletes and tombstones. Use an explicit column-scoped update or verify `UNSET` configuration with integration tests.

**Exercise 9.** A mapper `@Query` using `WHERE event_type = :type ALLOW FILTERING` runs slowly. Will enlarging the connection pool and rewriting in Core API fix the read path?

**Answer:** **No.** It still lacks a partition key or proper index and can scan many partitions. You need a query-driven table model or a strictly bounded analytics path.

**Exercise 10.** A DAO write fails with `WriteTimeout`. Can you safely retry immediately with a new `eventId` to "make sure the next write succeeds"?

**Answer:** **No.** Some replicas may already have applied the write. Retrying with a new ID creates duplicates; you need stable keys, idempotency, and business-level reconciliation.

**Exercise 11.** When comparing the mapper with Core, why must both be warmed up, use identical page sizes, and consume the exact same number of pages?

**Answer:** If one path absorbs prepare/cold-start overhead or stops after the first page, the test no longer compares **equal work**, making it invalid to blame latency gaps on mapping alone.

**Exercise 12.** A DAO method uses `@Select` and supplies the full primary key. What can still make that lookup slow?

**Answer:** Down/slow replicas or JVM GC, SSTable/disk I/O, tombstones, network latency, CL, high concurrency, and overloaded queues. A well-keyed partition lookup **is not immune to resource contention**.

**Exercise 13.** Java source uses `@Dao` and `@Mapper`, yet the CI build reports `TelemetryMapperBuilder` cannot be found. Name one likely cause.

**Answer:** Annotation processing is disabled or misconfigured in CI, processor/runtime dependency versions mismatch, or generated sources are excluded from compilation. Check the build setup before blaming Cassandra servers.

**Exercise 14.** A service holds `SELECT` privileges on the whole table, and tenant A passes tenant B's `deviceId` into the DAO. Does the mapper block it automatically?

**Answer:** **No.** CQL RBAC operates on table/resource privileges rather than tenant ownership inside `deviceId`; the service must enforce business authorization before binding parameters.

**Exercise 15.** On the same cluster, mapper full-entity p99 is 35 ms, Core full-entity p99 is 33 ms, and Core narrow-DTO p99 is 15 ms. Is there evidence that the mapper is the main bottleneck?

**Answer:** **Not yet.** Mapper full and Core full perform similarly while the narrow DTO is much faster, pointing to projection/bytes and server/network work first. Even then, results are valid only with adequate sample size, matching CL/page size, identical workload, warm-up, and verified output equivalence.

## 25. Production DAO deployment checklist

~~~text
SCHEMA / QUERY
[ ] Entity/DAO matches CQL partition keys and clustering columns accurately.
[ ] Every method defines an explicit query contract: keys, time window, LIMIT, ordering.
[ ] No unbounded getAll() or ALLOW FILTERING on hot paths.
[ ] SELECT queries fetch only columns needed by the API, not SELECT * by default.
[ ] Multi-bucket queries enforce bounded fan-out, proper merging, and pagination.

MAPPER / JAVA
[ ] Core, mapper runtime, and processor use a compatible, pinned version set.
[ ] Annotation processing runs in CI; generated sources are verified.
[ ] Keyspace, @CqlName, and Java/CQL types are covered by integration tests.
[ ] CqlSession is shared; prepared statements are reused and warmed appropriately.
[ ] Null/UNSET/TTL/updates do not silently delete or extend data unintentionally.
[ ] Codecs, UDTs, and large collections are benchmarked realistically.
[ ] Mapper hot paths are compared against Core on identical CQL before tuning.

RESOURCE / FAILURE
[ ] Rows, bytes, page size, concurrency, and API deadlines are capped.
[ ] Async code never dispatches unbounded futures or blocks I/O callbacks.
[ ] Retry and idempotency policies are explicit for reads, writes, counters, and LWTs.
[ ] Timeout/unavailable/authorization failures are handled distinctly from "not found."
[ ] Monitor p50/p95/p99, full-consume time, allocations/GC, and driver queues.
[ ] Monitor replica I/O, SSTables/tombstones, compaction, RF/CL, and topology.

SECURITY / RELEASE
[ ] Service runs with a least-privilege identity; no superuser or shared secrets.
[ ] TLS validates peers; secrets stay out of logs and metrics.
[ ] Tenant authorization lives in the service layer, never delegated to @Dao.
[ ] Staging covers schema/version/TTL/delete/large-payload integration tests.
[ ] Canary, performance/correctness gates, and rollback path are ready.
~~~

~~~mermaid
flowchart TD
    A["Need to read/write Cassandra from Java"] --> B["Design CQL by partition + clustering"]
    B --> C["Choose API: mapper DAO or Core"]
    C --> D{"Standard query, clear entity, maintainability priority?"}
    D -->|Yes| E["@Entity + @Dao + @Mapper codegen"]
    D -->|No / streaming hot path| F["Core PreparedStatement + lightweight Row/DTO"]
    E --> G["Bound projection, paging, concurrency, deadline"]
    F --> G
    G --> H["Test nulls, TTL, errors, RF/CL, schema, and security"]
    H --> I["Benchmark identical CQL + allocation/GC + server latency"]
    I --> J{"SLO and data correctness met?"}
    J -->|No| K["Fix data model / bytes / overhead, retry"]
    K --> C
    J -->|Yes| L["Canary and observe before full rollout"]
~~~

**Conclusion:** the Apache Cassandra Java Driver 4.x object mapper and DAO let you **define clear data-access contracts, cut boilerplate, and generate mapping code at compile time**. However, they are not relational ORMs with joins, transactions, or dirty checking, and **they do not optimize CQL or expand Cassandra capacity**. True cost spans **partition/range shape, statement counts, projection bytes, page fetches, network/replica latency, codecs, object allocation, and GC**. Use the mapper for well-scoped, maintainable queries; reserve Core API or narrow DTOs for hot paths **only when fair benchmarks demonstrate real benefit**. Before declaring "the mapper is slow," always inspect the **emitted CQL, data volume, RF/CL, timeouts, backpressure, and result correctness**.
