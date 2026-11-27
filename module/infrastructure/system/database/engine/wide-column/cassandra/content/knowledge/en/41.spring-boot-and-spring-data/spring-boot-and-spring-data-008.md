# `CassandraTemplate` / `CassandraOperations` and CQL Control

> **Chapter:** Spring Boot and Spring Data  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — exploring distributed Apache Cassandra and the wide-column model; partition keys, query-driven table design, consistency levels, CQL, replication, compaction, repair, error handling, and Java application integration.

A Spring Boot service can access Cassandra through a repository, `CassandraTemplate`, `CassandraOperations`, `CqlTemplate`, or `CqlSession` directly. Everything ultimately sends CQL through the Java Driver, yet each layer controls a different part of the execution path. A Java line like `template.select(query, Job.class)` does not turn Cassandra into a relational database: **you still must query the right partition key, respect clustering rules, RF/CL, and SSTable read costs**.

This lesson answers: **when should Spring Data generate and map CQL; when must you write explicit CQL; and how do you verify the statements, consistency, timeouts, paging, and results actually sent to Cassandra?**

> **Important boundary:** `CassandraTemplate` is a concrete **implementation**, while `CassandraOperations` is the **interface** applications should depend on. `CqlTemplate`/`CqlOperations` operate closer to raw CQL and rows. `CqlSession` is the low-level Java Driver API. Picking an abstraction never changes partitioning mechanics, LWT consensus, or durability.

Examples use Spring Data Cassandra **4.5.x** paired with Spring Boot **3.5.x**, Java 17, and Java Driver 4.x as the illustrative baseline; newer Spring Data/Boot branches may change APIs, BOMs, and packages. **Never mix Spring Data 5.x arbitrarily into Boot 3.5**; verify actual resolved dependency versions before running code in your environment.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Trace the path `Spring Boot → CassandraOperations/Template → CqlTemplate/Driver → coordinator → replicas`.
2. Distinguish repositories, mapping templates, CQL templates, and the raw driver; pick the right abstraction for a business need.
3. Map entities with `@Table`, `@PrimaryKey`, and `@Column`, understanding differences between Java properties and CQL column names.
4. Build valid `Query`/`Criteria` queries around partition keys, understanding `limit`, projections, ranges, and `ALLOW FILTERING` limits.
5. Use `QueryOptions`, `InsertOptions`, and `UpdateOptions` to control CL, timeouts, page size, idempotency, TTL, and LWT.
6. Run parameterized CQL via `CqlOperations` or `CqlSession` when needing `TTL()`, `WRITETIME()`, native paging, tracing, or detailed CAS results.
7. Interpret `wasApplied`/booleans on unconditional operations and recognize timeouts with **indeterminate** write outcomes.
8. Design labs/tests verifying actual emitted CQL, avoiding full scans, duplicate data, and wrong consistency levels.

## 2. Picture of the Data Access Layers

~~~mermaid
flowchart TD
    A["Spring Boot HTTP/Job/Service"] --> B{"What control level is needed?"}
    B --> C["Repository<br/>Common CRUD/queries"]
    B --> D["CassandraOperations<br/>Query/Criteria + entity mapping"]
    B --> E["CqlOperations<br/>CQL + bind + RowMapper"]
    B --> F["Java Driver 4.x CqlSession<br/>Prepared/BoundStatement, metadata"]
    C --> D
    D --> G["CassandraTemplate"]
    G --> H["CqlTemplate / statement factory"]
    E --> H
    H --> F
    F --> I["Native protocol, load balancing, retry, TLS"]
    I --> J["Cassandra coordinator"]
    J --> K["Replicas per token, RF, and consistency"]
~~~

### 2.1. Choosing an Abstraction Intentionally

| Need | Suitable API | Benefits | Notes |
|---|---|---|---|
| PK CRUD, clear entity mapping | Repository | Minimal boilerplate, clean domain grouping | Method names do not remove CQL restrictions |
| Dynamic PK queries, projection control, paging | `CassandraOperations` / `CassandraTemplate` | `Query/Criteria`, mapping, exception translation | Inspect generated CQL and `QueryOptions` |
| Custom CQL, `TTL/WRITETIME`, narrow column reads | `CqlOperations` / `CqlTemplate` | Visible CQL, binding, `RowMapper` | Responsible for schema/query design |
| Routing metadata, tokens, paging state, execution info, CAS current values | `CqlSession` | Full `Prepared/BoundStatement` and driver result control | More boilerplate and error-mapping logic |
| End-to-end reactive | `ReactiveCassandraOperations` | `Flux/Mono`, non-blocking pipeline | Never call blocking templates on the event loop |
| Bulk export and exact page processing | Driver paging or tested `stream/slice` | Avoids loading everything into a huge `List` | Deadlines, memory, retries, and CL still apply |

`CassandraTemplate` implements `CassandraOperations`, uses `MappingCassandraConverter` to convert row ↔ entity, and translates driver exceptions into the `org.springframework.dao.DataAccessException` hierarchy. Configured as a bean, the template is **safe to share across threads**; never instantiate a new Template and `CqlSession` per HTTP request.

### 2.2. Why Should Services Depend on the Interface?

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.stereotype.Service;

@Service
public final class JobQueryService {
    private final CassandraOperations cassandra;

    public JobQueryService(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    // Methods using CassandraOperations appear in later sections.
}
~~~

Spring Boot can auto-configure template/session beans from the starter. With **multiple keyspaces or sessions**, use `@Qualifier` to pick the right bean. Never leave two ambiguously named beans and accept queries hitting the wrong keyspace.

**Note:** depending on an interface decouples implementation and eases mocking, yet **mocked unit tests never prove real CQL runs correctly**. Integration tests against real/ephemeral Cassandra are mandatory.

## 3. Spring Boot Configuration and Checking the BOM

### 3.1. Starter and Java Runtime

Abbreviated Maven example; Spring Boot 3.5.x requires Java **17+**. The parent version below illustrates alignment; **choose an approved, security-patched release** for deployment:

~~~xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.5.0</version>
  <relativePath/>
</parent>
<properties>
  <java.version>17</java.version>
</properties>
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-cassandra</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Do not arbitrarily add `com.datastax.oss:java-driver-core` alongside `org.apache.cassandra:java-driver-core` just to "get a newer driver"; the two coordinates can supply overlapping classes and trigger classpath conflicts. Inspect the **effective POM, dependency tree, Spring Boot BOM, and actually resolved Java Driver version**. If upgrading the driver for Cassandra 5.0 features, verify compatibility across both Spring Data and Java Driver.

### 3.2. Minimal Connection Config

~~~yaml
spring:
  cassandra:
    contact-points:
      - "db1.dc1.internal.example:9042"
      - "db2.dc1.internal.example:9042"
    local-datacenter: "dc1"
    keyspace-name: "spring_lab"
    port: 9042
    # Auth/TLS options must come from a secret manager/driver config.
~~~

These addresses are **samples**, not a live cluster. Verify the real DC via `nodetool status`; a wrong `dc1` prevents the driver from selecting local nodes. Where environments require TLS, hostname verification, and role/password auth, never leave them blank in production. Prefer secret injection and **never commit passwords or private keys** to repositories.

`spring.cassandra.*` properties belong to Spring Boot 3.x; Spring Boot allows driver customization via `DriverConfigLoader`, customizers, or custom HOCON. When multiple layers set timeout/consistency, determine the **final runtime precedence**.

### 3.3. Distinguish Three Connection Timeouts

| Setting | Meaning | Do Not Confuse With |
|---|---|---|
| Connection timeout | Time to establish a node connection | Not a `SELECT` query timeout |
| Driver request timeout / statement timeout | Driver wait cap per CQL request/execute | Does not automatically bound an entire HTTP workflow |
| Business deadline | Total budget across auth, caches, CQL, serialization, retries | Does not reset on each repository call |

Never raise all timeouts to mask `LOCAL_QUORUM` unavailability, schema mismatches, or compaction backlogs.

## 4. Cassandra Lab Using Query-Driven Table Design

### 4.1. Assumed Topology

The lab assumes Cassandra 4.x/5.x and keyspace `spring_lab` in DC `dc1` with **three nodes, RF=3**, supporting `LOCAL_QUORUM`. If running one node, adjust RF and consistency to match topology; **never** configure RF3 and expect a single-node cluster to serve quorum queries.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

In `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS spring_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;
~~~

### 4.2. Two Tables Representing Two Needs

**Look up job status by ID** — simple partition key, ideal for Entity + `CassandraOperations`:

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.jobs_by_id (
  job_id uuid PRIMARY KEY,
  status text,
  version bigint,
  expires_at timestamp,
  last_error text
) WITH default_time_to_live = 0;
~~~

**Read events per device/day, newest first** — composite partition key, ideal for prepared CQL and paging:

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.events_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  event_id uuid,
  payload text,
  PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Two valid queries:

~~~sql
SELECT job_id, status, version, expires_at, last_error
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;

SELECT event_time, event_id, payload
FROM spring_lab.events_by_device_day
WHERE device_id = 22222222-2222-4222-8222-222222222222
  AND event_day = '2026-11-21'
  AND event_time >= '2026-11-21T08:00:00Z'
  AND event_time < '2026-11-21T10:00:00Z'
LIMIT 100;
~~~

**Why:** `job_id` hits one partition; the event query hits one `(device_id, event_day)` partition bounded by clustering `event_time`. Writing `WHERE status = 'FAILED'` on `jobs_by_id` **never** becomes efficient just by using `Criteria.where("status")`. If the business frequently queries failed jobs, design **another query-driven table by status** and manage synchronization.

`IF NOT EXISTS` in DDL **does not modify an existing table**. After running, verify:

~~~text
DESCRIBE KEYSPACE spring_lab;
DESCRIBE TABLE spring_lab.jobs_by_id;
DESCRIBE TABLE spring_lab.events_by_device_day;
~~~

### 4.3. Sample Data

~~~sql
INSERT INTO spring_lab.jobs_by_id
  (job_id, status, version, expires_at, last_error)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'PENDING', 1, '2026-11-22T08:00:00Z', null
);

INSERT INTO spring_lab.events_by_device_day
  (device_id, event_day, event_time, event_id, payload)
VALUES (
  22222222-2222-4222-8222-222222222222,
  '2026-11-21', '2026-11-21T08:30:00Z',
  33333333-3333-4333-8333-333333333333,
  'sample-event'
);
~~~

These examples use synthetic IDs/accounts and must not run on production. `expires_at` is an application-level deadline; **writing it does not make Cassandra TTL expire the row**. For automatic storage expiration, configure TTL and cleanup policies explicitly.

## 5. Mapping Domain Objects with Spring Data Cassandra

### 5.1. Entity with Explicit Column Names

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("jobs_by_id")
public class JobRow {
    @PrimaryKey("job_id")
    private UUID jobId;

    @Column("status")
    private String status;

    @Column("version")
    private Long version;

    @Column("expires_at")
    private Instant expiresAt;

    @Column("last_error")
    private String lastError;

    public JobRow() {}

    public JobRow(UUID jobId, String status, Long version,
                  Instant expiresAt, String lastError) {
        this.jobId = jobId;
        this.status = status;
        this.version = version;
        this.expiresAt = expiresAt;
        this.lastError = lastError;
    }

    public UUID getJobId() { return jobId; }
    public void setJobId(UUID id) { this.jobId = id; }
    public String getStatus() { return status; }
    public void setStatus(String value) { this.status = value; }
    public Long getVersion() { return version; }
    public void setVersion(Long value) { this.version = value; }
    public Instant getExpiresAt() { return expiresAt; }
    public void setExpiresAt(Instant value) { this.expiresAt = value; }
    public String getLastError() { return lastError; }
    public void setLastError(String value) { this.lastError = value; }
}
~~~

Annotations align table/column names with CQL, reducing reliance on default naming strategies. `UUID` maps `uuid`, `Instant` maps `timestamp`, and `Long` maps `bigint`. For UDTs, collections, custom codecs, and converters, test real value round-trips; Spring converters cannot rescue incompatible Java/CQL types.

**Do not put `@Version` on this field in the basic example**, as it enables LWT optimistic locking on certain entity operations, altering semantics and cost compared to regular updates. LWT is covered separately below.

### 5.2. Null, Absent, and `DELETE` Are Not Identical

Cassandra is wide-column: an unset cell, a `null` Java field, CQL `null`, `UNSET` on bind, and `DELETE` produce different behaviors and tombstones. When calling `template.save(entity)` or `template.update(entity)`, inspect your exact version's **insert/update null-handling options** rather than assuming all nulls are "preserved" or "deleted".

A service updating only `status` should prefer an update targeting **only that column** instead of serializing a whole entity full of null fields. This avoids needless mutations/tombstones and prevents overwriting newer values in other columns.

## 6. `CassandraOperations` with `Query` and `Criteria`

### 6.1. `SELECT` by Primary Key

Spring Data Cassandra uses `org.springframework.data.cassandra.core.query.Query` and `Criteria`. Example:

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Query;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

public final class JobReader {
    private final CassandraOperations operations;

    public JobReader(CassandraOperations operations) {
        this.operations = operations;
    }

    public Optional<JobRow> find(UUID jobId) {
        Query q = query(where("job_id").is(jobId)).limit(1);
        return Optional.ofNullable(operations.selectOne(q, JobRow.class));
    }
}
~~~

`selectOne` maps a row to the entity and returns `null` if absent. `limit(1)` fits a single PK; it **does not** make a query missing the partition key efficient.

**Mapping:** this example uses the CQL column name `job_id` directly in `Criteria`; with complex property-to-column mappings or naming strategies, inspect the generated statement and run integration tests on your actual Spring Data version. If code writes `where("jobId")`, verify it maps accurately to `job_id`.

### 6.2. `Query` and `Criteria` Are Immutable Objects

~~~java
Query q1 = query(where("job_id").is(jobId));
Query q2 = q1.limit(1);

// Must pass q2 because q1 is not mutated in place.
JobRow job = operations.selectOne(q2, JobRow.class);
~~~

Methods like `and(...)`, `queryOptions(...)`, `withAllowFiltering()`, and `sort(...)` likewise return a new `Query`. In Java Driver 4.x, `BoundStatement.setConsistencyLevel(...)` / `setTimeout(...)` also return new instances — the exact same trap.

### 6.3. Query DSL Does Not Remove CQL Limits

| Criteria / API | CQL / Semantics | When Appropriate |
|---|---|---|
| `where("job_id").is(uuid)` | `job_id = ?` | Single-partition key lookup |
| `where("event_time").gte(from)` | `event_time >= ?` | Efficient only when partition key is constrained and `event_time` is clustering |
| `where("event_time").lt(until)` | `event_time < ?` | Clustering range inside a partition |
| `where("status").is("FAILED")` | `status = ?` | **Invalid / suboptimal** on `jobs_by_id` without a matching index or table |
| `Query.limit(100)` | `LIMIT 100` | Caps returned rows; does not guarantee small disk scans |
| `Query.withAllowFiltering()` | `ALLOW FILTERING` | Can force broad server scans; not an "optimization" |

Spring Data generates **CQL syntax**, not partition keys, replication, indexes, SAI, clustering order, or query workloads. A query missing the full partition key can be rejected by Cassandra even though the Java compiles cleanly.

### 6.4. Projections and `SELECT *`

By default, templates often select all mapped columns; with large payloads, `SELECT *` inflates network traffic, codec CPU, and data exposure risk. If a screen only needs status:

~~~sql
SELECT status
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

Use DTO/interface projections via fluent templates/repositories, or explicit CQL with `CqlOperations`. **Never treat a partially projected entity lacking identity/fields as a full record**: calling update/`save` on it later can write nulls or overwrite existing values.

### 6.5. Turning a Status Lookup Problem into Table Design

Instead of calling:

~~~java
// Do NOT treat this as a solution on jobs_by_id:
// operations.select(query(where("status").is("FAILED"))
//     .withAllowFiltering(), JobRow.class);
~~~

design a table around the query "list failed jobs for a tenant by day":

~~~sql
CREATE TABLE IF NOT EXISTS spring_lab.failed_jobs_by_tenant_day (
    tenant_id uuid,
    job_day date,
    failed_at timestamp,
    job_id uuid,
    summary text,
    PRIMARY KEY ((tenant_id, job_day), failed_at, job_id)
) WITH CLUSTERING ORDER BY (failed_at DESC, job_id ASC);
~~~

Denormalization gives reads a deterministic partition key, yet requires updating/fixing/deleting across related tables via workflows with reconciliation. Updating multiple tables in different partitions **does not** become an ACID transaction merely by using the same `CassandraOperations`.

## 7. `QueryOptions`: Controlling Driver Execution of CQL

### 7.1. Consistency, Timeout, Page Size, and Idempotency

`QueryOptions` lets you set per-request execution options:

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.cql.QueryOptions;
import org.springframework.data.cassandra.core.query.Query;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

QueryOptions opts = QueryOptions.builder()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(600))
    .pageSize(100)
    .idempotent(true)
    .build();

Query q = query(where("job_id").is(jobId))
    .queryOptions(opts)
    .limit(1);

JobRow job = operations.selectOne(q, JobRow.class);
~~~

`LOCAL_QUORUM` depends on local DC RF; `timeout` bounds a single driver request per version, not the full HTTP deadline; `pageSize` sets target rows per page, **distinct** from `LIMIT`; `idempotent(true)` fits pure `SELECT`s yet must never be applied mechanically to counter increments, LWTs, or side-effectful writes.

### 7.2. Selecting an Execution Profile

~~~java
QueryOptions shortRead = QueryOptions.builder()
    .executionProfile("short-read")
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(350))
    .build();
~~~

The profile name must be declared in the active driver config/HOCON. Defaults, templates, profiles, and statement overrides interact; **verify the runtime statement** on your exact Spring Data/Driver versions instead of guessing override precedence.

### 7.3. CL Is Not a Transaction Lock or a Timeout Cure

| CL | Simple Meaning in an RF=3 DC | Risk If Chosen Wrongly |
|---|---|---|
| `LOCAL_ONE` | One local replica suffices | May read stale, unsynchronized replica data |
| `LOCAL_QUORUM` | Two local replicas must respond per CL | Timeouts/unavailable if replicas are missing |
| `QUORUM` | Quorum across total RF/topology | Can incur cross-DC WAN RTT depending on setup |
| `SERIAL/LOCAL_SERIAL` | Serial phase for LWT/serial reads | Does not replace regular consistency |

**Never automatically downgrade `LOCAL_QUORUM → LOCAL_ONE`** just to make timeout dashboards look quieter if it violates invariants. If an HTTP workflow has only 150 ms left before its deadline, do not issue a template query with a 600 ms timeout pretending it will finish in time; compute `min(configuredCeiling, remaining - responseReserve)` and fail fast when needed.

### 7.4. Idempotency, Retries, and TTL

An `UPDATE SET status='DONE'` may be value-idempotent, yet retrying with a newer write timestamp can overwrite a concurrent update. Re-sending `INSERT USING TTL 600` minutes later **extends expiration**; counter increments are completely non-idempotent. Never enable `idempotent(true)` blindly across all mutations, and never stack unbounded retries across gateway + service + Spring Retry + Java Driver — one business request can amplify into dozens of CQL attempts.

## 8. Prepared Statements and CQL Injection

### 8.1. `CassandraTemplate` Has Built-In Prepared Statement Support

Spring Data Cassandra 4.x normally enables prepared statements on `CassandraTemplate` by default, exposing `setUsePreparedStatements(boolean)` for control. Java Driver 4.x maintains a prepared statement cache in `CqlSession`, so adding a custom CQL-text cache is unnecessary without a clear reason.

**Use bind markers for values**, avoiding varying the statement string per UUID. Changing CQL text per request forces the driver and server to cache far more prepared IDs and increases injection risk.

### 8.2. Safe Parameterized CQL with `CqlOperations`

Wrong:

~~~java
// Never concatenate HTTP input into a CQL string:
String unsafe = "SELECT status FROM spring_lab.jobs_by_id " +
    "WHERE job_id = " + request.getParameter("jobId");
~~~

Right:

~~~java
UUID jobId = UUID.fromString(request.getParameter("jobId"));

String status = operations.getCqlOperations().queryForObject(
    "SELECT status FROM spring_lab.jobs_by_id WHERE job_id = ?",
    String.class,
    jobId
);
~~~

`queryForObject(String, Class, Object...)` is a `CqlTemplate`/`CqlOperations` API using prepared binding; handle empty or multi-row results appropriately.

**Bind markers are for values only, never table/column names.** If an app genuinely needs dynamic table selection, use a static allowlist of CQL names and never let clients inject identifiers into query text.

### 8.3. Comparing Prepared Execution Paths

| API | Where CQL Is Built | Who Maps Results? |
|---|---|---|
| `operations.select(Query, JobRow.class)` | Template constructs and prepares CQL per config | `MappingCassandraConverter` |
| `operations.select(SimpleStatement, JobRow.class)` | Template can prepare/bind from `SimpleStatement` | Converter |
| `operations.getCqlOperations().queryForObject(cql,type,args...)` | Static CQL + bound args | `CqlTemplate` scalar extraction |
| `CqlSession.prepare(...).bind(...)` | App controls CQL, codecs, CL, and routing directly | App reads `Row`/`ResultSet` |

When needing `TTL(status)`, `WRITETIME(status)`, tracing, or detailed retry/metadata, `CqlOperations` or `CqlSession` fits better than full-entity mapping.

## 9. Writes, TTL, LWT, and Interpreting Results

### 9.1. `InsertOptions` for TTL and CL

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.data.cassandra.core.InsertOptions;

InsertOptions options = InsertOptions.builder()
    .ttl(Duration.ofMinutes(10))
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .timeout(Duration.ofMillis(800))
    .build();

JobRow row = new JobRow(jobId, "PENDING", 1L, expiresAt, null);
operations.insert(row, options);
~~~

TTL is a **relative lifetime** measured at cell write time. Re-writing the same TTL after a timeout extends expiration; `expiresAt` in the entity is a business field and does not auto-sync with Cassandra TTL. `USING TTL 0` means **no TTL**, not immediate deletion. Honoring a fixed retention deadline requires computing remaining TTL and controlling retries.

### 9.2. Single-Column `UPDATE` Avoids Overwriting the Whole Entity

~~~java
import org.springframework.data.cassandra.core.query.Update;
import static org.springframework.data.cassandra.core.query.Query.query;
import static org.springframework.data.cassandra.core.query.Criteria.where;

boolean applied = operations.update(
    query(where("job_id").is(jobId)),
    Update.update("status", "RUNNING"),
    JobRow.class);
~~~

**The boolean from an unconditional `UPDATE` does not prove the row existed or that compare-and-set succeeded.** Cassandra performs upserts; Java Driver `wasApplied` returns `true` by convention for non-LWT mutations. Updating only if a row exists or matches a version requires conditional CQL/LWT.

### 9.3. `Insert IF NOT EXISTS` via `InsertOptions`

~~~java
InsertOptions conditional = InsertOptions.builder()
    .withIfNotExists()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .serialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL)
    .timeout(Duration.ofMillis(1200))
    .build();

var result = operations.insert(row, conditional);
if (!result.wasApplied()) {
    // IF NOT EXISTS condition failed; report business conflict.
    // result.getRows() may hold existing row columns.
}
// When detailed current row data is needed, inspect getRows()/ColumnDefinitions
// or use low-level ResultSet per your version.
~~~

`IF NOT EXISTS` uses LWT/Paxos and checks the **exact primary key**, not arbitrary unique constraints on `status`. `[applied]=false` indicates a conditional conflict; a timeout is an **unknown outcome** — never coerce it to `false` or retry blindly forever.

### 9.4. `@Version` Enables Optimistic Locking

Spring Data Cassandra supports `@Version` on entities, using LWT for single-entity operations. Example of a **separate** entity designed for it:

~~~java
// @Table("state_by_id")
// public class StateById {
//   @PrimaryKey("id") UUID id;
//   @Version Long version;
//   String state;
// }
~~~

Versioned conditional updates/deletes can throw `OptimisticLockingFailureException`. Never slap `@Version` onto every field named `version` just to map a `bigint`; it changes semantics and Paxos cost, and still does not create multi-partition transactions.

### 9.5. `DELETE` and Tombstones

~~~java
boolean deleted = operations.delete(
    query(where("job_id").is(jobId)), JobRow.class);
~~~

`DELETE` writes tombstones; the boolean from an unconditional delete does not prove a row previously existed or that disk space was freed. `gc_grace_seconds`, compaction, and repair are separate operational concerns.

## 10. When Direct CQL Control Is Needed

### 10.1. `CqlOperations` via `CassandraOperations`

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.CassandraOperations;

static String readStatus(CassandraOperations ops, UUID jobId) {
    return ops.getCqlOperations().queryForObject(
        "SELECT status FROM spring_lab.jobs_by_id WHERE job_id = ?",
        String.class,
        jobId
    );
}
~~~

The CQL template preserves prepared binding and exception translation without full entity mapping. For per-cell TTL/writetime or CQL functions, use `RowMapper`/`ResultSetExtractor`; for routing metadata, paging state, or detailed CAS inspection, use `CqlSession`.

### 10.2. Prepared CQL for Composite Partition Keys

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

void readRecent(CqlSession session, UUID deviceId, LocalDate day,
                Instant from, Instant until) {
    PreparedStatement prepared = session.prepare(
        "SELECT event_time, event_id, payload " +
        "FROM spring_lab.events_by_device_day " +
        "WHERE device_id = ? AND event_day = ? " +
        "AND event_time >= ? AND event_time < ? LIMIT ?");

    BoundStatement bound = prepared.bind(
            deviceId, day, from, until, 100)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setPageSize(50)
        .setIdempotent(true);

    ResultSet result = session.execute(bound);
    for (Row row : result) {
        UUID id = row.getUuid("event_id");
        Instant eventTime = row.getInstant("event_time");
        // Process within business deadline; avoid logging sensitive payloads.
    }
    System.out.println("Coordinator=" +
        result.getExecutionInfo().getCoordinator());
}
~~~

**Note:** `CqlSession` is a long-lived Spring-managed bean; never close it per HTTP request. The driver derives a routing key when a prepared query binds the **full partition key**; `setPageSize(50)` does not cap total results at 50, as the iterator fetches subsequent pages. `ExecutionInfo.getCoordinator()` does not list every replica that served the CL.

### 10.3. Raw CQL for LWT and Current Version

~~~java
PreparedStatement cas = session.prepare(
    "UPDATE spring_lab.jobs_by_id " +
    "SET status = ?, version = ? WHERE job_id = ? " +
    "IF version = ?");

BoundStatement request = cas.bind("RUNNING", 2L, jobId, 1L)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

ResultSet rs = session.execute(request);
if (rs.wasApplied()) {
    System.out.println("CAS_APPLIED");
} else {
    Row current = rs.one();
    Long versionNow = current != null
            && current.getColumnDefinitions().contains("version")
            && !current.isNull("version")
        ? current.getLong("version")
        : null;
    System.out.println("CAS_CONFLICT version=" + versionNow);
}
~~~

A `false` CAS result means the **condition was not met**. On an exception/timeout, the write may have committed while the ACK was lost: mark it unknown and reconcile, never treat it as `false` or rolled back. Across multiple tables/partitions, calling two APIs sequentially **does not** form an ACID transaction; design idempotency and reconciliation.

## 11. Paging, Streaming, and Bounding Data

### 11.1. `LIMIT`, Page Size, and Total Row Count Are Three Separate Concepts

| Mechanism | Controls | Does Not Guarantee |
|---|---|---|
| `Query.limit(100)` / CQL `LIMIT 100` | Maximum logical rows returned per CQL semantics | Does not prove disk scanned only 100 cells/tombstones |
| `QueryOptions.pageSize(50)` | Target rows per native protocol page | Does not cap total query results at 50 |
| `Slice<JobRow>` | A result slice with next-page info | Not cheap if query lacks partition key |
| `Stream<JobRow>` | Sequential/lazy row iteration | Does not protect memory if caller calls `collect(toList())` |
| `ResultSet.getExecutionInfo()` | Execution metadata for received response | Does not show all replicas or automatically span all pages |

A `SELECT` over a 10,000-row partition with page size 100 performs many network fetches; a business deadline must cover the **entire consumption loop**, never resetting a fresh budget per page.

### 11.2. Streaming with `CassandraOperations`

~~~java
import java.util.stream.Stream;
import static org.springframework.data.cassandra.core.query.Query.query;
import static org.springframework.data.cassandra.core.query.Criteria.where;

Query q = query(where("job_id").is(jobId));
try (Stream<JobRow> rows = operations.stream(q, JobRow.class)) {
    rows.forEach(job -> {
        // Process quickly; do not accumulate all entities in a huge List.
        // For sensitive data, never log raw rows.
    });
}
~~~

A single-PK example returns at most one row; it illustrates stream lifecycle. To genuinely observe paging, use a multi-row table like `events_by_device_day` with a full partition-key query as in Section 4, or use Driver async paging.

**Caution:** `Stream<T>` can hold driver-backed lazy iteration resources. Use try-with-resources as required and never let a stream outlive the HTTP request or closed context. Heavy work, blocking I/O, or per-row HTTP calls can blow deadlines and pile up request backlogs.

### 11.3. Cassandra Paging Is Not SQL `OFFSET`

Cassandra **does not** support arbitrary `OFFSET 1000000` pagination like RDBMSs. The driver uses paging states, while Spring Data offers `Slice`/`CassandraPageRequest`/scrolling per version. Never compute page 7 by re-scanning the first six pages from scratch when paging state is available.

Rules:

- Bind paging state strictly to the **exact same CQL, bind parameters, compatible query options, and schema**; never feed state from another query.
- When returning paging state to clients, consider encoding/signing, TTL, and authorization; never allow one tenant to replay another tenant's paging state.
- Paging state is not a cluster-wide transactional snapshot; rows can be inserted, deleted, or TTL-expired between pages.
- For consistent exports, design watermarks/time windows, idempotent sinks, and test for duplicate/missing rows.
- Size `LIMIT` to workload; `pageSize` only tunes batch transfer size.

### 11.4. Sorting by Clustering Keys, Not Arbitrary Columns

`ORDER BY event_time DESC` works via intra-partition clustering order, whereas sorting by arbitrary columns like `status` or `payload` is unsupported unlike SQL. `Query.sort(...)` only emits CQL; if it violates clustering rules, the server rejects it or performs poorly. The fix is **changing the data model to fit the query**, not adding `ALLOW FILTERING` everywhere.

## 12. Imperative, Async, and Reactive

### 12.1. Match the Execution Model to the Thread Model

| Environment | Suitable API | Notes |
|---|---|---|
| Spring MVC / thread-per-request service | `CassandraOperations`, `CassandraTemplate` | Blocking; monitor pools/in-flight and HTTP deadlines |
| `CompletionStage`-based service | `AsyncCassandraOperations/AsyncCassandraTemplate` or driver async | Handle completion errors; never block callbacks |
| End-to-end Spring WebFlux | `ReactiveCassandraOperations/ReactiveCassandraTemplate` | `Mono/Flux`, cancellation, bounded concurrency |
| Low-level Reactor / Driver | `CqlSession.executeReactive(...)` | `ReactiveResultSet` is cold/single-subscription with distinct metadata |

**Never** call blocking `CassandraTemplate` inside a WebFlux event-loop thread and claim the pipeline is non-blocking. If temporarily wrapping a blocking library, offload to a bounded scheduler and control concurrency; even better, use reactive operations when reactive is the approved architecture.

### 12.2. `ReactiveCassandraOperations` with `Query`

~~~java
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.query.Query;
import reactor.core.publisher.Mono;
import static org.springframework.data.cassandra.core.query.Criteria.where;
import static org.springframework.data.cassandra.core.query.Query.query;

Mono<JobRow> findReactive(
        ReactiveCassandraOperations ops, UUID jobId) {
    Query q = query(where("job_id").is(jobId)).limit(1);
    return ops.selectOne(q, JobRow.class);
}
~~~

`Mono` is a publisher: execution occurs upon subscription; never call `block()` inside a reactive controller. A Reactor `retry` **re-subscribes** and executes a fresh query, which is especially hazardous for mutations, LWTs, or side effects. Enforce deadlines and idempotency properly.

### 12.3. Using `@Async` Does Not Mean Reactive

A `@Async CompletableFuture<T>` repository method offloads blocking work to a thread pool, whereas `ReactiveCassandraOperations` uses publisher demand and backpressure semantics. Never "wrap" a blocking `CassandraTemplate` call inside `Mono.just(...)` on the event loop: the blocking call runs eagerly before `Mono` is even created. If bridging is unavoidable, use a deferred publisher on a bounded scheduler and monitor backlogs.

## 13. Verifying Exact CQL and Observing Performance

### 13.1. What Must Be Verified at the CQL Level

A call like `operations.select(query(where("job_id").is(id)), JobRow.class)` is only sound when:

1. CQL column names rendered by the converter match the real schema.
2. The `WHERE` clause supplies the full partition key.
3. CQL projection/mapping does not silently drop required fields.
4. Consistency level matches DC/RF rather than using an unintended default.
5. Page size, `LIMIT`, and timeout fit the business budget.
6. Reads/writes handle nullability, UDTs, collections, and timestamps accurately.
7. Conditional operations are clearly separated from normal upserts.

### 13.2. Logs and Tracing Must Not Leak Data

You can enable request tracing on a small sample:

~~~java
QueryOptions traced = QueryOptions.builder()
    .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .tracing(true)
    .build();
~~~

**Never enable tracing on 100% of production QPS**: tracing adds overhead, and CQL rows/logs can expose bind values, query text, and sensitive data. Use sampled traces, masking, and tight retention. At the low-level driver, `Statement.setTracing(true)` must also be verified against your version.

Useful metrics:

| Metric | Reason |
|---|---|
| Request p50/p95/p99 per CQL pattern | Detect queries missing partition/clustering keys |
| Timeouts/unavailable/retries per CL | Spot RF issues, Down nodes, and overload |
| In-flight requests, pool streams, throttling queues | Distinguish client resource exhaustion from slow backends |
| Row counts/bytes/page counts | Spot `SELECT *` or excessive payload reads |
| Tombstones scanned and SSTables per read | Explain slow reads despite valid partition-key `WHERE` |
| CAS applied/conflicts/unknown | Verify write invariants and contention |
| Partition hot-key skew (anonymized) | Explain uneven replica load |
| GC/CPU/network/compaction/repair | Assess overall cluster health |

Never log full tokens/API keys or put user UUIDs into high-cardinality metric labels. Exact logger categories depend on Spring Data, Driver, and observability versions; inspect actual config instead of turning on global `DEBUG` in production.

### 13.3. Reading `EXPLAIN` Like SQL? Do Not Assume It

Cassandra CQL does not offer a PostgreSQL-equivalent `EXPLAIN ANALYZE` for every query. Depending on version and tooling, rely on tracing, driver metrics, `nodetool tablestats`, histograms, `system_schema`/index metadata, and controlled benchmarks.

If a query only runs when adding `ALLOW FILTERING`, that is a signal to revisit your **data model/indexes**, not proof the query is optimized.

## 14. Integration Lab: From Template API to Real CQL

### 14.1. Lab Setup and Safeguards

Use the Section 4 schema on a **lab Cassandra cluster**. With RF=3/`dc1`, ensure enough nodes and verify:

~~~bash
nodetool status
nodetool describecluster
nodetool tablestats spring_lab.jobs_by_id
~~~

Use only lab addresses/credentials; never disable production firewalls or TLS for exercises. If running a single node, adjust RF=1 and consistency **before creating the keyspace**, then verify behavior directly.

### 14.2. Lab A — Reading via Three APIs

Execute:

1. With sample UUID `11111111-1111-4111-8111-111111111111`, call `operations.selectOne(query(where("job_id").is(id)), JobRow.class)`.
2. Call `operations.getCqlOperations().queryForObject("SELECT status ... WHERE job_id=?", String.class, id)`.
3. Call `CqlSession.prepare("SELECT status ... WHERE job_id=?")` and `session.execute(bound)`.
4. Compare `status`, CL, coordinator, timeout, and request counts.
5. Note differences between entity mapping, scalar extraction, and raw driver metadata.

**Expected:** identical row data, differing metadata visibility. If the three APIs diverge, check keyspace/schema, CL/replica consistency, concurrent mutations, and converters — **do not** jump to blaming framework bugs.

### 14.3. Lab B — Are `QueryOptions` Taking Effect?

1. Build `QueryOptions` with `LOCAL_QUORUM`, 500 ms timeout, and page size 50.
2. Execute a PK query and record success/timeout counts.
3. Switch to a configured execution profile (lab-only) and compare effective config.
4. Intentionally call `q.limit(1)` **without reassigning**, inspect the `Query` passed in, then fix it to `q = q.limit(1)`.
5. Use low-sample logging/tracing to inspect emitted CQL and confirm **no `ALLOW FILTERING`**.

Base conclusions on observed traces/metrics, never assuming a builder/setter mutated an object.

### 14.4. Lab C — LWT Version Conflict

On a row with version 1:

~~~sql
UPDATE spring_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Run once, then run again:

- First run, with no competing writer: `[applied]=true`.
- Second run, now that version is 2: `[applied]=false`, returning current `version=2`.
- Use raw `ResultSet.wasApplied()` to distinguish outcomes.
- Calling `operations.update(query, Update, JobRow.class)` without a condition **is not** CAS.
- On timeout, never conclude the mutation was not applied; read and reconcile.

### 14.5. Lab D — TTL and Deadline Checks

Run in the CQL lab:

~~~sql
UPDATE spring_lab.jobs_by_id USING TTL 120
SET last_error = 'temporary'
WHERE job_id = 11111111-1111-4111-8111-111111111111;

SELECT TTL(last_error), WRITETIME(last_error)
FROM spring_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

Watch TTL count down in seconds while `version` or `status` retains its own TTL. Do not assume one uniform TTL applies across all columns if apps copy/ETL cells independently. Compare `TTL()` with `expires_at` to see that **application deadlines and storage TTL are distinct**.

### 14.6. Lab E — Non-Key Anti-Pattern

Try querying `WHERE status = 'PENDING'` on `jobs_by_id`:

1. Observe how Cassandra rejects it without an index or partition key.
2. **Never** enable `withAllowFiltering()` in production as a "fix".
3. Sketch a query-driven table like `failed_jobs_by_tenant_day`.
4. Specify partition key, clustering, RF/CL, TTL, and denormalized update workflows.
5. Compare partitions/tombstones/bytes scanned against a well-keyed query rather than timing a tiny few-row dataset.

### 14.7. Experiment Results Table

| Case | API | CQL / Partition Key | CL | Rows / Pages | p95 / p99 | Business Correct? |
|---|---|---|---|---|---|---|
| A1 | `CassandraOperations` | Job ID | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| A2 | `CqlOperations` | Job ID | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| A3 | `CqlSession` | Job ID | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| B | `QueryOptions`/profile | Job ID | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| C | LWT/CAS | Job ID, version | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| D | TTL/WRITETIME | Job ID | _fill in_ | _fill in_ | _fill in_ | _fill in_ |
| E | Non-key scan | Missing partition key | _fill in_ | _fill in_ | _fill in_ | _fill in_ |

Never fabricate benchmark numbers without running tests. On a one-row lab, p99 has no statistical significance; scale partition counts and requests repeatedly in a controlled test environment before drawing performance conclusions.

## 15. Common Mistakes When Using Templates

| Misconception | Why It Is Wrong | Right Approach |
|---|---|---|
| "`CassandraTemplate` generates good queries automatically" | Query DSL does not design partition keys | Inspect CQL/`WHERE` and query-driven data models |
| "`CassandraOperations` and `CassandraTemplate` are two systems" | Interface and implementation of the same abstraction | Inject `CassandraOperations`; override implementation when needed |
| "Template is a SQL ORM with multi-table JOINs" | Cassandra has no arbitrary relational JOINs | Denormalize into query-driven tables |
| "`LIMIT 10` means reading at most 10 cells" | Tombstones/filters can force wide scans | Inspect data layout, traces, and tombstone metrics |
| "`ALLOW FILTERING` optimizes `WHERE status`" | Can trigger expensive cluster/partition scans | Design tables/indexes around the workload |
| "`pageSize=50` returns 50 rows total" | Page size differs from query limit | Consume all pages within deadlines |
| "Calling `q.limit(1)` mutated `q`" | `Query` is immutable | Assign and pass the returned `Query` |
| "`SELECT *` is free if the converter only uses 2 fields" | Server still transfers extra columns | Use projections/DTOs/explicit CQL column lists |
| "Concatenating UUIDs into CQL is handier than binding" | Injection, quoting, and prepared-cache bloat | Use prepared placeholders and typed binds |
| "Boolean `update=true` means an old row existed" | Non-LWT upsert returns `wasApplied=true` by default | Use `IF EXISTS` when existence checks matter |
| "Spring `@Version` is just field mapping" | It activates LWT optimistic locking | Use only when CAS is required and Paxos cost is acceptable |
| "`DELETE=true` means disk space was freed" | Tombstones and compaction are asynchronous | Separate logical deletion from physical purge |
| "Timeout guarantees a write did not commit" | ACK can be lost after mutation applied | Treat as UNKNOWN + idempotency/reconciliation |
| "Switching to `LOCAL_ONE` to avoid timeouts is always safe" | Can break consistency invariants | Size CL per RF and business requirements |
| "Reactive means wrapping sync template in `Mono.just`" | Blocking runs eagerly before `Mono` subscription | Use `ReactiveCassandraOperations` or a bounded bridge |
| "A fresh `CqlSession` per request is safer" | Multiplies pools, metadata, prepares, and overhead | Share one long-lived application session |
| "Spring Boot BOM supports every new Cassandra feature" | Mapping/codecs/driver patches must also match | Verify features via dependency tree and integration tests |

## 16. Questions and Applied Exercises

### Exercise 1 — Choosing an Abstraction

An application queries by `job_id` and maps the full entity. Should it use `CqlSession` directly for every query?

**Answer:** unnecessary. `CassandraOperations.selectOne(Query, JobRow.class)` fits cleanly and simplifies mapping/testing. Drop down to the raw driver when you need metadata, paging state, tracing, or data types not conveniently exposed by the template.

### Exercise 2 — Why Did the Query DSL Fail?

`query(where("status").is("FAILED"))` compiles, yet Cassandra rejects it on `jobs_by_id(job_id PRIMARY KEY, status)`. Why?

**Answer:** the predicate omits the partition key and lacks a supporting table/index. Templates do not remove Cassandra query restrictions; create a query-driven table or verified index.

### Exercise 3 — `Query.limit` Has No Effect

A developer writes `q.limit(10); operations.select(q, JobRow.class);`, yet the query runs without `LIMIT`. Why?

**Answer:** `Query` is immutable; write `q = q.limit(10)` or pass the newly returned `Query`.

### Exercise 4 — Controlling Consistency

Keyspace has RF3 in `dc1`, and the service requires local-DC read-your-writes. During node slowdowns, the team switches CL from `LOCAL_QUORUM` to `LOCAL_ONE` without checking invariants. What goes wrong?

**Answer:** weaker CL can return stale data from unsynchronized replicas; evaluate consistency guarantees, RF, repair, and availability requirements before changing CL.

### Exercise 5 — TTL on Retry

A job is written with `InsertOptions.ttl(600)`. Five minutes later, the service retries the same entity with TTL 600. How does expiration change?

**Answer:** the retried write resets TTL to 10 more minutes from the retry timestamp, unintentionally extending retention. Use an absolute deadline, compute remaining TTL, and enforce idempotency.

### Exercise 6 — CAS `false` vs. Timeout

`INSERT IF NOT EXISTS` returns `false`; another time the same request times out. Can both be handled as `ALREADY_EXISTS`?

**Answer:** no. `false` means the condition failed, whereas a timeout is an unknown outcome (the write may have committed while the ACK was lost). Distinguish conflicts from reconciliation cases.

### Exercise 7 — Missing Columns in Projection

An endpoint selects only `status`, maps it into `JobRow`, and later calls `save()` on that instance. What is the risk?

**Answer:** the entity lacks ID/other fields and can write nulls or overwrite data on `save`. Use scalar/DTO projections for partial reads and complete entities (or targeted updates) for mutations.

### Exercise 8 — WebFlux with Blocking Template

A WebFlux service writes `return Mono.just(operations.selectOne(q, JobRow.class));`. Is this non-blocking I/O?

**Answer:** no. `selectOne` blocks **before `Mono` is even constructed**. Use `ReactiveCassandraOperations` or explicitly offload onto a bounded scheduler while understanding the limits.

### Exercise 9 — `Pageable` Like SQL Offset?

A team wants to jump directly to page 100,000 in Cassandra using an offset. Is this viable?

**Answer:** Cassandra paging uses state/cursors and has no cheap arbitrary-offset scan like SQL. Design keyset pagination on clustering columns, use paging state, and bound query scope.

### Exercise 10 — `CqlSession` vs. Template

When needing `TTL(last_error)`, `WRITETIME(last_error)`, and the coordinator address for debugging, what should you choose?

**Answer:** `CqlOperations`/`RowMapper` or a `CqlSession` prepared statement inspecting `ResultSet`/`ExecutionInfo` for explicit metadata; avoid shoehorning CQL functions into entity mapping where semantics become hard to verify.

### Lesson Completion Checklist

- [ ] Distinguished Repository, `CassandraOperations`/`CassandraTemplate`, `CqlOperations`/`CqlTemplate`, and `CqlSession`.
- [ ] Understood `@Table`/`@PrimaryKey`/`@Column` mapping and verified converters.
- [ ] Designed queries around partition/clustering keys before selecting an API.
- [ ] Used `Query`/`Criteria` properly respecting immutability.
- [ ] Never used `ALLOW FILTERING` as a default optimization.
- [ ] Configured `QueryOptions` for CL, timeout, `pageSize`, idempotency, and execution profiles.
- [ ] Distinguished `LIMIT`, paging, and total result counts.
- [ ] Used prepared/bound statements; never concatenated input into CQL.
- [ ] Used `InsertOptions`/`UpdateOptions` with TTL without resetting deadlines on retries.
- [ ] Understood that unconditional updates/deletes do not prove row existence.
- [ ] Distinguished LWT `wasApplied=false` from timeout unknown outcomes.
- [ ] Used `@Version` only when Paxos optimistic locking is actually required.
- [ ] Dropped down to `CqlOperations`/`CqlSession` when explicit metadata or CQL is needed.
- [ ] Never created a new `CqlSession` per HTTP request.
- [ ] Used `ReactiveCassandraOperations` on reactive stacks without blocking the event loop.
- [ ] Wrote integration tests covering CQL/schemas, RF/CL, paging, TTL, LWT, and p95/p99.

## 17. References

1. Spring Data Cassandra — [Persisting Entities / CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): `CassandraOperations`, `Query`/`Criteria`, mapping, CRUD, optimistic locking.
2. Spring Data Cassandra — [Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html): `CassandraTemplate.setUsePreparedStatements`, `CqlTemplate`, bind markers, caching.
3. Spring Data Cassandra — [CassandraOperations API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/CassandraOperations.html): select/update/delete/stream/slice/`getCqlOperations` APIs.
4. Spring Data Cassandra — [QueryOptions.Builder API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/cql/QueryOptions.QueryOptionsBuilder.html): CL, timeout, `pageSize`, tracing, idempotency, profiles.
5. Spring Data Cassandra — [InsertOptions.Builder API 4.5](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/InsertOptions.InsertOptionsBuilder.html): TTL, `IF NOT EXISTS`, write timestamp, serial consistency.
6. Spring Data Cassandra — [Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html): `@Query`, `QueryOptions`, consistency, limit, and allow-filtering constraints.
7. Spring Boot 3.5 — [Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.cassandra.*`, local datacenter, contact-points, keyspace.
8. Spring Boot — [Cassandra auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/data/nosql.html): starter, Spring-managed `CqlSession`, injection.
9. Apache Cassandra Java Driver 4.19 — [Prepared Statements](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/prepared/) and [Paging](https://apache.github.io/cassandra-java-driver/4.19.0/core/paging/): binding, routing keys, paging state.
10. Apache Cassandra Documentation — [CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) and [DDL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): PK, clustering, TTL, LWT, consistency, schema.
11. Apache Cassandra Documentation — [Operations & Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/): replica health, repair/compaction, and operational costs.
