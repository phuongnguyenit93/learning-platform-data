# SimpleStatement and Synchronous Query Execution

## Learning Objectives

Apache Cassandra uses CQL (*Cassandra Query Language*) to read and write data by **partition key**, clustering key, and the wide-column model. In a Java application, the Cassandra Java Driver turns a CQL statement into a request sent to a **coordinator**, collects responses according to the **consistency level**, and maps returned data to Java types.

This lesson belongs to the **Java Driver Basics** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. Its focus is using **`SimpleStatement`** and synchronous **`CqlSession.execute(...)`**: constructing queries, passing typed parameters, reading `ResultSet`, handling errors, configuring consistency and paging, and verifying data. These examples also reinforce partition keys, query-driven table design, replication, compaction, repair, and error diagnosis.

After this lesson, you will be able to:

1. Describe the relationship among `CqlSession`, `SimpleStatement`, coordinator, replicas, and `ResultSet`.
2. Create a `SimpleStatement` via `newInstance(...)` or builder, passing **positional values** instead of concatenating user input strings.
3. Execute synchronously with `session.execute(statement)`, reading a single row or iterating multiple rows without accidentally loading an entire partition.
4. Read CQL types accurately: `text` → `String`, `uuid` → `UUID`, `timestamp` → `Instant`, `date` → `LocalDate`, `bigint` → `long`, and `decimal` → `BigDecimal`.
5. Set `LOCAL_QUORUM`, `pageSize`, and `idempotence`, and understand the limits of each option.
6. Distinguish **no row found**, **read error**, **uncertain write outcome**, and **acknowledged write**.
7. Know when `SimpleStatement` is appropriate and when to switch to `PreparedStatement` or asynchronous execution.

> **Version scope:** sample code uses the **Cassandra Java Driver 4.x** API with `com.datastax.oss.driver.api.core...` packages and Java 17. Specific driver distribution/version, dependency coordinates, JDK, TLS, and protocol must follow your active cluster's compatibility matrix. Only run write examples on authorized **lab/staging** environments.

## 1. Where Does SimpleStatement Sit in a Query Path?

A Java application does not send `SELECT` directly to every replica. It sends the statement via the driver to a node chosen as **coordinator**. The coordinator identifies the partition's replicas from the token and replication strategy, contacts the required replicas, and returns the result to the driver.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant Session as CqlSession / Driver
    participant Coord as Cassandra Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    App->>Session: SimpleStatement + execute()
    Session->>Coord: Native CQL request
    Coord->>R1: Data request
    Coord->>R2: Digest / data request
    R1-->>Coord: Data response
    R2-->>Coord: Digest / data response
    Coord-->>Session: CQL rows / error
    Session-->>App: ResultSet or exception
~~~

This diagram is a simplified read model; replica counts and request types vary by **RF, read CL, node health, speculative execution, and Cassandra version**. `LOCAL_ONE` can complete from one replica, whereas `LOCAL_QUORUM` with RF=3 in a DC needs two local responses. **Do not treat one Java call as strictly one network message between nodes.**

### Three Core Objects

| Object | Role | Notes |
| --- | --- | --- |
| `CqlSession` | Manages connections, cluster metadata, node discovery, routing, execution | **Long-lived reuse**; never create per HTTP request |
| `SimpleStatement` | Describes a CQL query, values, and execution options | Does not require a prior `PREPARE` step before sending |
| `ResultSet` / `Row` | Reads successful query results and execution metadata | Results can be **paged**; reading everything may trigger follow-up requests |

Besides `SimpleStatement`, the driver offers `PreparedStatement`/`BoundStatement`. `SimpleStatement` suits **one-off queries, admin tools, or exercises**; for repeated query shapes under heavy load, prepared statements usually win on metadata caching, binding, and server-side parsing.

### How Does Synchronous Differ from Asynchronous?

~~~text
Synchronous:
  ResultSet rs = session.execute(statement);
  // Calling thread blocks until the request returns results/first page or fails.

Asynchronous:
  CompletionStage<AsyncResultSet> future = session.executeAsync(statement);
  // Can proceed with other work without blocking the current thread.
~~~

`execute(...)` **blocks the calling Java thread**. However, it does not necessarily fetch **every page** of the result in one shot. As code iterates `ResultSet`, the driver may **fetch subsequent pages** and block the thread again at those boundaries.

Synchronous execution is simple and clear for labs, bounded tasks, and low-concurrency apps. In event-loop/reactive frameworks, never call `execute` directly on an event-loop thread: blocking stalls unrelated requests.

## 2. Preparing the Java Environment and Cluster

### 2.1. Dependencies and Compatibility Requirements

Pick a **Java Driver 4.x** release supported by vendor/community documentation for your Cassandra version and JVM. Many 4.x releases share the API package:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
~~~

**Do not confuse API packages with fixed Maven coordinates**: DataStax and Apache Cassandra Java Driver releases have different group/artifact/version coordinates. Use the dependency matching your approved release; never blindly pick the latest version if your cluster uses an older protocol/version.

Verify at minimum:

- Java runtime supports the chosen driver version.
- Server has **native transport** enabled on the expected CQL port (typically TCP `9042`).
- Contact points are reachable; after discovery, advertised peer endpoints must also be reachable.
- **Local datacenter** name matches Cassandra metadata/snitch.
- Production uses TLS, authentication, secret management, and a **least-privilege** role; never disable certificate verification to work around network errors.
- Timeouts, concurrency limits, and metrics are configured for your workload.

### 2.2. Inspecting the Lab Cluster with cqlsh

Assume the lab has **three nodes** in a DC named `datacenter1`. On an administrative node:

~~~bash
nodetool status
~~~

All three nodes should show `UN` before testing RF3. In `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` only describes the node answering the query; to verify every node's version, check each node or use the appropriate topology tool.

**If your lab lacks three nodes**, adjust RF and consistency level to match actual replicas. Never set RF3 on a single node expecting `LOCAL_QUORUM` to work with two non-existent replicas.

## 3. Creating a Query-Driven Lab Table for Java

The application wants to read **events for a tenant on a given day**, ordered by descending time, and read a specific event by its full key.

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_driver_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS java_driver_lab.events_by_tenant_day (
    tenant_id text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    amount_minor bigint,
    note text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

### Explaining the Primary Key

- `(tenant_id, event_day)` is the **composite partition key**. Cassandra hashes the pair to find the token; **both** must be known to read a partition.
- `event_time` and `event_id` are **clustering keys**, ordering rows within the partition; `event_id` disambiguates events sharing a timestamp.
- `event_type`, `amount_minor`, and `note` are regular columns. List APIs can select only the first two columns to cut payload size.
- `amount_minor bigint` stores money in minor units so monetary values never pass through `double`.
- Daily bucketing bounds partition size **when daily event volume is reasonable**. Very hot tenants may still require hourly buckets or query-aligned sharding.

`IF NOT EXISTS` does not modify an existing keyspace/table. Confirm the lab actually uses RF3:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'java_driver_lab';
~~~

### Inserting Two Sample Records

In `cqlsh` on a healthy RF3 cluster, set:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO java_driver_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id,
     event_type, amount_minor, note)
VALUES (
    'tenant-lab', '2026-11-21', '2026-11-21T09:00:00Z',
    11111111-1111-4111-8111-111111111111,
    'CREATED', 25000, 'New order'
);

INSERT INTO java_driver_lab.events_by_tenant_day
    (tenant_id, event_day, event_time, event_id,
     event_type, amount_minor, note)
VALUES (
    'tenant-lab', '2026-11-21', '2026-11-21T09:05:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAID', 25000, 'Payment completed'
);
~~~

Only consider a write **acknowledged** if `cqlsh` succeeds at the chosen CL. On a timeout, never conclude the mutation definitely was not written.

~~~sql
SELECT event_time, event_id, event_type, amount_minor
FROM java_driver_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-lab'
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

With the sample data, the expected output has two events, `PAID` before `CREATED` per `event_time DESC`. If concurrent writes occur in a shared lab, results can differ; use a fresh partition/run ID to isolate experiments.

## 4. Creating and Managing CqlSession Properly

`CqlSession` manages connection pools, metadata, and routing. Initialization is expensive; therefore **never create a new session for every `SELECT` or every HTTP request**.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class LabSession {
    public static CqlSession open() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

These IP addresses are **examples**—replace with your lab cluster's endpoints. Contact points aid node **discovery**; they are not a hardcoded list of every coordinator the driver will ever use. After discovery, the driver routes to other nodes per load balancing/routing policies.

In a short command-line program:

~~~java
try (CqlSession session = LabSession.open()) {
    // Execute synchronous CQL.
} // Session closes upon exiting the block.
~~~

In a long-lived Java service, tie the session to the **application lifecycle**, share it across components, and close it gracefully on shutdown. Never call `close()` after individual queries while the session is still needed.

**Production security:** instead of hardcoding secrets, load authentication/TLS from a secret manager and truststore, verify SAN/hostnames, and restrict CQL permissions per keyspace/table. A successful TCP connection does not prove TLS or authorization is properly configured.

## 5. Two Ways to Construct a SimpleStatement

### 5.1. Concise Form: SimpleStatement.newInstance

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.LocalDate;

SimpleStatement list = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type, amount_minor " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setPageSize(20)
 .setIdempotence(true);
~~~

**The two `?` markers are bind markers for values**, not string substitution via `String.replace`. The driver receives `String` and `LocalDate`, encodes them per CQL types, and sends them over the native protocol.

### 5.2. Use a Builder When Setting Many Options

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import java.time.LocalDate;

SimpleStatement list = SimpleStatement.builder(
        "SELECT event_time, event_id, event_type, amount_minor " +
        "FROM java_driver_lab.events_by_tenant_day " +
        "WHERE tenant_id = ? AND event_day = ? LIMIT 20")
    .addPositionalValue("tenant-lab")
    .addPositionalValue(LocalDate.of(2026, 11, 21))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(20)
    .setIdempotence(true)
    .build();
~~~

Both approaches represent the **exact same query shape and values**. The builder is easier to read when configuring many options or assembling statements from validated values. Creating a new statement for different parameter sets does not require creating a new `CqlSession`.

### Key Options to Know

| Option | Meaning | What Not to Infer |
| --- | --- | --- |
| `setConsistencyLevel(LOCAL_QUORUM)` | Requires a quorum in the local DC | Every replica in every DC has converged |
| `setPageSize(20)` | Target rows per returned page | Caps **total** rows at 20 |
| `setIdempotence(true)` | Tells driver/policies the statement is safe to retry per app semantics | Driver guarantees retries or exactly-once writes |
| `setTimeout(...)` if supported by API/version | Client-side deadline for the request | Every mutation cancelled when the deadline expires |
| `setExecutionProfileName(...)` | Selects config profile for this request type | Changes schema, RF, or CQL permissions |

Final behavior also depends on **driver configuration, retry policy, speculative execution, schema, and cluster health**. Marking a statement idempotent does not make a business write idempotent.

## 6. Passing Parameters Safely: Bind Markers, Never String Concatenation

### Anti-Example: Concatenating User Input into CQL

~~~java
String tenantFromHttp = requestTenant;  // Example API input.
String cql = "SELECT * FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = '" + tenantFromHttp + "'";
// DO NOT USE: missing full partition key, unsafe string concatenation.
~~~

This snippet has two flaws:

1. **Missing `event_day`**, so the query lacks the full partition key; `ALLOW FILTERING` cannot replace query-driven design.
2. User input is interpolated into CQL text, risking broken escaping and CQL injection.

Replace with positional values:

~~~java
SimpleStatement safe = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    tenantFromHttp,
    dayFromRequest
);
~~~

`dayFromRequest` must be a parsed, validated `LocalDate`. Parameters only bind **data values**; `?` cannot bind **table names, column names, keywords, or CQL clauses**.

If an app genuinely must pick a table dynamically, use a **fixed server-managed allowlist** (e.g., two predefined table names), rather than accepting raw table names or `WHERE` fragments from users.

### How Does SimpleStatement Differ from PreparedStatement?

~~~text
SimpleStatement:
  Client sends query string + values on every execution.
  No prior server-side prepare step required.

PreparedStatement:
  Client prepares query shape; server returns metadata/prepared ID.
  Each call uses BoundStatement to bind values and execute.
  Ideal when the same query shape runs repeatedly.
~~~

**`SimpleStatement` still supports values via bind markers**, avoiding literal concatenation into CQL. However, for high-frequency production workloads, prefer `PreparedStatement` to reuse query shape and metadata and avoid repeated protocol/server parsing.

## 7. Executing Synchronous SELECT and Reading ResultSet

### 7.1. Reading One Row by Full Key

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventLookup {
    public static void readOne(CqlSession session) {
        SimpleStatement query = SimpleStatement.newInstance(
            "SELECT event_type, amount_minor, note " +
            "FROM java_driver_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? " +
            "AND event_time = ? AND event_id = ?",
            "tenant-lab",
            LocalDate.of(2026, 11, 21),
            Instant.parse("2026-11-21T09:05:00Z"),
            UUID.fromString("22222222-2222-4222-8222-222222222222")
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotence(true);

        ResultSet result = session.execute(query);
        Row row = result.one();

        if (row == null) {
            System.out.println("Query succeeded, no matching row");
            return;
        }

        String eventType = row.getString("event_type");
        Long amount = row.isNull("amount_minor")
            ? null : row.getLong("amount_minor");
        String note = row.getString("note");

        System.out.printf("type=%s amount_minor=%s note=%s%n",
            eventType, amount, note);
    }
}
~~~

**Why does `one() == null` not mean the query failed?** When `execute` returns a `ResultSet` cleanly with no matching row for the key, `one()` returns `null`. Conversely, on insufficient replicas, timeouts, authorization failures, or invalid queries, `execute` **throws an exception**; never translate those errors into "data does not exist".

### 7.2. Reading Multiple Rows with Explicit Bounds

~~~java
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import java.time.LocalDate;

SimpleStatement query = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type, amount_minor " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 20",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setPageSize(10)
 .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotence(true);

ResultSet rows = session.execute(query);
for (Row row : rows) {
    System.out.printf("%s %s %s%n",
        row.getInstant("event_time"),
        row.getUuid("event_id"),
        row.getString("event_type"));
}
~~~

CQL `LIMIT 20` is the **total row cap returned by the query**, whereas `setPageSize(10)` is the **target rows per page**. When 20 rows exist and the server sends pages of 10, the `for` loop triggers a fetch for the second page during iteration.

**Important consequence:** `session.execute(...)` returns `ResultSet` once the **first page** arrives; iterating to the end triggers additional round trips and blocks the thread again. Never run `for (Row row : result)` on an unbounded or unkeyed query thinking it only reads 10 rows.

### 7.3. Narrow Projections and Result Size

If a list API only needs time, ID, and status, `SELECT` only those three columns; never fetch `note` or huge blobs only to discard them in Java. `SELECT *` inflates response sizes and GC pressure, especially on wide text/blob columns.

Measure optimizations across all dimensions:

- CQL query count from the application;
- Rows and pages actually fetched;
- Response byte size;
- p50/p95/p99 latency, timeouts, retries;
- Java CPU/GC and replica read latency/tombstone scans.

Narrowing projections cannot fix missing partition keys, hot partitions, compaction backlogs, or slow replicas.

## 8. Data Types and Nulls When Reading a Row

A `Row` follows a **CQL schema**, not an arbitrary JSON map. Use matching getters to avoid precision loss, timezone confusion, or codec errors.

| CQL | Typical Java Driver 4.x Type | Example Getter |
| --- | --- | --- |
| `text` / `varchar` / `ascii` | `String` | `row.getString("event_type")` |
| `uuid` | `UUID` | `row.getUuid("event_id")` |
| `timestamp` | `Instant` | `row.getInstant("event_time")` |
| `date` | `LocalDate` | `row.getLocalDate("event_day")` |
| `time` | `LocalTime` | `row.getLocalTime("clock_time")` |
| `int` | `int` | `row.getInt("version")` |
| `bigint` | `long` | `row.getLong("amount_minor")` |
| `decimal` | `BigDecimal` | `row.getBigDecimal("amount")` |
| `varint` | `BigInteger` | `row.getBigInteger("sequence_no")` |
| `boolean` | `boolean` | `row.getBoolean("enabled")` |

Columns `clock_time`, `version`, `amount`, `sequence_no`, and `enabled` above **only illustrate getter names**; they are not in the current lab schema.

### Nulls and Unselected Fields

- `row == null`: query succeeded, **no matching row**.
- `row.isNull("amount_minor")`: row exists, **selected cell is null**.
- `row.getString("note")` returns `null` if the text column is null.
- Accessing a column **omitted from the projection** is a mapping bug, not "Cassandra lost the column".
- For primitive getters like `getLong`, check `isNull` first when the schema allows nulls and business logic distinguishes null from `0`.

CQL `timestamp` stores an **instant** at millisecond precision, without preserving an original IANA timezone name. Never compare timestamps using client-timezone-formatted strings; compare `Instant` or epoch milliseconds when reconciling.

For money, never convert `decimal` to `double` for exact arithmetic. Use `BigDecimal` with consistent scale/rounding rules. For UUIDs, keep `UUID` values stable so retries never mint new primary keys.

## 9. Synchronous INSERT: Acknowledged Differs from Stored on Every Replica

`SimpleStatement` also works for `INSERT` and `UPDATE`. Example adding a new event with a known identity key:

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

SimpleStatement insert = SimpleStatement.newInstance(
    "INSERT INTO java_driver_lab.events_by_tenant_day " +
    "(tenant_id, event_day, event_time, event_id, " +
    "event_type, amount_minor, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
    "tenant-lab",
    LocalDate.of(2026, 11, 21),
    Instant.parse("2026-11-21T09:10:00Z"),
    UUID.fromString("33333333-3333-4333-8333-333333333333"),
    "SHIPPED",
    25000L,
    "Order shipped"
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setIdempotence(false);

session.execute(insert);
// If no exception thrown: server acknowledged the write at requested CL.
~~~

**`INSERT` is not "insert only if absent" by default**. In Cassandra, writing the same primary key updates/overwrites columns by timestamp. To write only when absent, study **LWT: `INSERT ... IF NOT EXISTS`** along with its consistency and latency trade-offs.

### RF/CL and Write Outcomes

Assume `NetworkTopologyStrategy` with **RF=3 in datacenter1**:

| Write CL | Minimum ACKs in Local DC | Guarantee on Success |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 | At least one local replica responded per CL |
| `LOCAL_QUORUM` | 2 | Local quorum ACKed; does not require all three |
| `ALL` | 3 | All three RF replicas ACKed |

The required ACK count is **not** the number of replicas the coordinator tries to contact. Remaining replicas catch up via hints/repair/replication depending on network health. If one node is temporarily down, a `LOCAL_QUORUM` write can still succeed when the two remaining local replicas ACK.

### Write Timeouts and the Retry Problem

If `session.execute(insert)` times out, actual state may be:

~~~text
UNKNOWN_WRITE:
    client did not receive ACKs for CL before deadline
    -> some replicas may already have written the mutation
    -> cannot safely conclude "not written"
~~~

For **upserts on the same primary key with identical values** and no concurrent writers, retrying can be safe if timestamps/TTLs and idempotency are properly defined. With concurrent writers, counters, LWT, fresh IDs generated per attempt, or external side effects, blind retries corrupt state. **Never enable `setIdempotence(true)` on every write just to make the driver retry faster.**

## 10. Distinguishing Sync Errors from Data Outcomes

An application should never collapse outcomes into just "success" and "no data". At minimum, distinguish:

| App Outcome | Condition | Decision |
| --- | --- | --- |
| `READ_MATCH` | `SELECT` completed and row matches expectation | PASS for tested key/CL |
| `READ_MISSING` | `SELECT` completed, `one() == null` | Check key, TTL, `DELETE`, and manifest |
| `READ_MISMATCH` | `SELECT` completed, value differs from expectation | Investigate timestamps, writers, and replicas |
| `READ_ERROR` | `SELECT` threw timeout/unavailable/driver exception | Cannot conclude whether row exists |
| `WRITE_ACKNOWLEDGED` | `INSERT`/`UPDATE` completed at CL | Record ACK with CL/timestamp |
| `UNKNOWN_WRITE` | Write failed to return success after sending | Reconcile before bounded retry |
| `VALIDATION_ERROR` | Invalid input type/PK/null/format before sending | Fix caller; do not retry like a network error |

### Common Failure Classes

| Symptom | First Suspect | Evidence to Check |
| --- | --- | --- |
| Cannot open `CqlSession` | Contact points, firewall, TLS/auth, local DC | Endpoints, certs, driver logs, node listeners |
| `InvalidQuery` | Invalid CQL, missing partition key, schema mismatch | Secret-free query text, `system_schema` |
| `Unauthorized` | Role lacks permission or auth failed | Role grants, identity, audit logs |
| `Unavailable` | Insufficient live replicas for CL | RF, DC, `nodetool status` |
| `ReadTimeout` | Replicas responded too slowly/insufficiently before deadline | Trace, I/O/compaction, CL, network |
| `WriteTimeout` | Insufficient write ACKs before deadline | Record `UNKNOWN`, check replica health |
| `ReadFailure/WriteFailure` | Replica reported execution error | Node logs, storage/network |
| Divergent read data | Low CL, replica lag, concurrent writes, TTL | Manifest, timestamps, tracing, repair |
| Codec error | Java type/codec mismatches CQL column type | Schema and bound/get Java types |

Exact exception class names vary across driver versions, so classify by **actual exception type, error code, and context** rather than matching message strings alone. Never log passwords, full CQL values, or sensitive PII during exception handling.

### Example Measuring Read Outcomes with Error Classification

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class SyncReadProbe {
    public enum State { MATCH, MISSING, MISMATCH, READ_ERROR }
    public record Outcome(
        State state, long latencyMicros,
        String coordinator, String errorType) {}

    public static Outcome check(
            CqlSession session, String tenant, LocalDate day,
            Instant time, UUID eventId, String expectedType) {
        SimpleStatement query = SimpleStatement.newInstance(
            "SELECT event_type FROM java_driver_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND event_day = ? " +
            "AND event_time = ? AND event_id = ?",
            tenant, day, time, eventId
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotence(true);

        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(query);
            ExecutionInfo info = result.getExecutionInfo();
            String coordinator = info.getCoordinator() == null
                ? "unknown" : info.getCoordinator().getEndPoint().toString();
            Row row = result.one();
            long us = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
            if (row == null) {
                return new Outcome(State.MISSING, us, coordinator, null);
            }
            State state = expectedType.equals(row.getString("event_type"))
                ? State.MATCH : State.MISMATCH;
            return new Outcome(state, us, coordinator, null);
        } catch (RuntimeException error) {
            long us = TimeUnit.NANOSECONDS.toMicros(
                System.nanoTime() - started);
            return new Outcome(
                State.READ_ERROR, us, "unknown",
                error.getClass().getSimpleName());
        }
    }
}
~~~

Here, `expectedType` must come from a **manifest or trusted external source**, not the `SELECT` output itself. `MATCH` only confirms a single key's value at the active CL/moment; it does not prove all replicas have converged.

The probe uses `System.nanoTime()` for elapsed duration (immune to wall-clock adjustments). Computing p95/p99 requires **many samples under representative load**, grouped by query and tracking **error rates separately**—never average only successful requests and ignore timeouts.

## 11. Paging During Synchronous Execution

### 11.1. LIMIT Differs from Page Size

~~~java
SimpleStatement query = SimpleStatement.newInstance(
    "SELECT event_time, event_id, event_type " +
    "FROM java_driver_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND event_day = ? LIMIT 50",
    "tenant-lab",
    LocalDate.of(2026, 11, 21)
).setPageSize(10);
~~~

The query's total cap is **50 rows**, while the target size **per page** is 10 rows. If enough rows exist, reading all of them requires multiple fetches. The server may also return a page smaller than `pageSize` due to query/server limits, so **never conclude "fewer than 10 rows means no more data"**.

### 11.2. Avoid Fetching All Pages When Only the First Page Is Needed

~~~java
// Anti-pattern for large result sets:
// List<Row> everything = session.execute(query).all();
// all() can fetch every remaining page.

ResultSet result = session.execute(query);
int available = result.getAvailableWithoutFetching();
java.util.Iterator<Row> current = result.iterator();
for (int i = 0; i < available; i++) {
    Row row = current.next();
    // Process only rows already buffered in the current page.
}
~~~

`getAvailableWithoutFetching()` reports how many rows are buffered locally without another fetch at that moment. Here, that count is captured **before iterating**, and the loop calls `next()` strictly that many times without calling `hasNext()` across a page boundary. For production cursor-based pagination APIs, manage the **opaque paging state** and its contract explicitly; never invent `OFFSET` or treat paging state as a page number.

**Loop caution:** a standard `for-each` loop automatically fetches subsequent pages at page boundaries. For APIs returning one page and waiting for the user to click "Next", use the driver's paging-state API rather than iterating the entire `ResultSet` and slicing `subList` in Java.

### 11.3. Paging State Is Not a Transactional Snapshot

Treat paging state as an **opaque token** bound to the query, parameters, and protocol. Never give one tenant's token to another tenant, never mutate bytes, and never assume tokens remain valid indefinitely or portable across all Cassandra/driver versions.

If underlying data changes between pages, results differ from an immutable snapshot. When business logic requires reconciling all events without gaps or duplicates, fix the data window/identifiers and compare against a manifest after reading.

## 12. Choosing Consistency Levels per Business Requirement

### 12.1. Read-After-Write in the Same DC

With RF3 in `datacenter1`:

~~~text
Application:
    INSERT @ LOCAL_QUORUM -> waits for 2/3 local ACKs
    SELECT @ LOCAL_QUORUM -> waits for 2/3 local replicas
~~~

Without concurrent conflicting writes or rare failures, quorum reads/writes reduce stale reads compared to `ONE`. However, this **does not turn Cassandra into a serializable transactional database**, prevent lost updates, or replace LWT/version checks under concurrent writes.

`LOCAL_QUORUM` in DC A **never borrows ACKs from DC B** to form a local quorum. Nor does it guarantee a locally ACKed write has already reached every replica in a remote DC. If the Java Driver specifies the wrong local DC, it can pick coordinators in an unintended DC, incurring WAN latency and altering consistency behavior.

### 12.2. Never Lower CL Just to Dodge Timeouts

| Choice | Potential Benefit | Trade-Off |
| --- | --- | --- |
| `LOCAL_ONE` | Faster reads and higher availability when some replicas lag | Risk of reading stale data |
| `LOCAL_QUORUM` | Strong overlap within the local DC | Pays quorum latency; times out if too few replicas respond |
| `ALL` | Requires all replicas to respond | Sensitive to any single slow/down replica; poor general default |

Select CL from RF, DC topology, data semantics, and SLAs. **Never judge lab query speed and arbitrarily lower production consistency levels.**

## 13. Common SimpleStatement Mistakes

| Mistake | Consequence | Right Practice |
| --- | --- | --- |
| New `CqlSession` per request | Handshakes, pool churn, CPU/GC spikes | Reuse one session |
| String-concatenating user input into CQL | Broken escaping, injection risk | Positional values with `?` |
| `SELECT *` with no PK `WHERE` | Rejected query or wide scan if filtering | Query-driven tables with full partition key |
| Using `ALLOW FILTERING` to "fix" missing keys | Reads excessive partitions/SSTables, timeouts | Fix primary key, table, or index design |
| `LIMIT 20` on rows with huge blobs | 20 rows still produce huge responses | Narrow projections, split list vs. detail |
| Treating `setPageSize(10)` as total row limit | Loop fetches multiple pages | Combine `LIMIT` and app bounds |
| Calling `all()` on large results | Fetches all pages, spikes RAM/GC | Bounded iteration or cursors |
| Treating `row == null` and exceptions identically | Misreports errors as missing data | Separate `MISSING` from `READ_ERROR` |
| Retrying `INSERT` blindly after timeout | Duplicate/overwritten writes or repeated side effects | `UNKNOWN_WRITE`, idempotency, reconciliation |
| Using `double` for money | Binary floating-point rounding loss | `bigint` minor units or `decimal` |
| Treating `timestamp` as preserving origin timezone | Display/reconciliation mismatches | `Instant` + explicit business zone ID |
| Synchronous `execute` on event loops | Stalls event loop, delays unrelated requests | Use `executeAsync` or proper worker threads |
| Enabling idempotence on every write | Retries/speculation corrupt non-idempotent ops | Evaluate per statement |
| Trusting `nodetool status UN` as data proof | Replicas may still be out of sync | Reconcile via CL/manifest, run repair when needed |

## 14. Complete Hands-On Workflow

### Step 1 — Initialize

Verify the lab Cassandra cluster, DC name, and CQL connectivity; create `java_driver_lab.events_by_tenant_day`. Insert two marker rows via `cqlsh` and record **event IDs, timestamps, and expected statuses**. For Java write tests, use a fixed new event ID; never generate a fresh UUID when retrying the same event.

### Step 2 — Create Session

Open one `CqlSession` with the exact **local DC**. If TLS/auth is required, load config from authorized environment sources. Measure initialization time **separately** from query latency so benchmarks stay accurate.

### Step 3 — Read One Row

Build `SimpleStatement.newInstance(...)` with **all four key parts**: tenant, day, timestamp, and UUID. Call `execute(...)` then `one()`, classify `FOUND`/`MISSING`/`READ_ERROR`, and read typed columns.

### Step 4 — Read a List

Build `SimpleStatement.builder(...)` for one tenant/day partition with a narrow projection, `LIMIT 20`, and `pageSize 10`. Iterate `ResultSet` and observe row counts, clustering order, and pages fetched (via metrics/instrumentation).

### Step 5 — Execute an INSERT

Write a new event using positional parameters. Report `ACKNOWLEDGED` only if `execute` finishes cleanly at the chosen CL; on timeout, record `UNKNOWN_WRITE`. Then read back by the **exact primary key**.

### Step 6 — Practice Failure Safely

On an RF3 **lab** with runbook approval, temporarily stop one replica and compare `LOCAL_QUORUM` vs. `ALL` reads. Never induce network partitions or stop nodes in production. Observe `nodetool status`, errors, latency, and the difference among **`Unavailable`**, **`ReadTimeout`**, and **`MISSING`**.

### Step 7 — Report

~~~text
Lab name: java-driver-basics-008
Driver version: <actual version>
Cassandra version / DC / RF: <actual>
Query shape: point-read / list-read / insert
CL: LOCAL_QUORUM or chosen value
Partition key: tenant_id + event_day
Rows returned: <measured count>
Page size / pages fetched: <measured count>
Client latency p50/p95/p99: <measured>
READ_MATCH: <verified count>
READ_MISSING: <verified count>
READ_ERROR: <verified count>
WRITE_ACKNOWLEDGED: <verified count>
UNKNOWN_WRITE: <verified count>
Coordinator / DC: <from ExecutionInfo and metadata>
Conclusion: PASS / GAP / NEEDS_INVESTIGATION
~~~

The lines above are **placeholders**; never fabricate latency numbers. Measuring p99 requires sufficient samples of the same workload, representative load, and excluding session startup time from request latency. Never use one fast `cqlsh` query to claim a Java service meets its SLO.

## 15. Self-Check Questions and Exercises

**Exercise 1 — Session lifecycle.** Why shouldn't a service create/close a `CqlSession` per HTTP request? Are contact points a fixed coordinator list after discovery?

**Exercise 2 — Statement creation.** Write two equivalent versions of a single-partition `SELECT` using `SimpleStatement.newInstance` and `SimpleStatement.builder`. Identify positional values and consistency level.

**Exercise 3 — Partition key.** For `events_by_tenant_day`, why is filtering only on `tenant_id` insufficient? Does `SELECT * ... ALLOW FILTERING` become efficient?

**Exercise 4 — Nulls and errors.** Compare `row == null`, `row.isNull("amount_minor")`, and an exception from `session.execute`. Which is `MISSING` and which is `READ_ERROR`?

**Exercise 5 — Paging.** How do `LIMIT 50` and `pageSize 10` differ? Why can `for (Row row : result)` still block after `execute` already returned `ResultSet`?

**Exercise 6 — Projection.** A list API only needs `event_id` and `event_type`. Why can returning `note` and blobs raise p95 even with the right partition key?

**Exercise 7 — Consistency.** With RF=3 in `datacenter1` and one replica down, can `LOCAL_QUORUM` `SELECT` succeed? What about `ALL`? Do reads in another DC count toward this DC's `LOCAL_QUORUM`?

**Exercise 8 — Retries.** An `INSERT` times out, yet a replica partially applied it. Why must you not generate a new event ID and retry? Propose how to distinguish `UNKNOWN_WRITE` from never-sent.

**Exercise 9 — Data types.** What risks arise from reading `amount_minor bigint` as `double`? Why does a CQL `timestamp` read as `Instant` not preserve the origin timezone name?

**Exercise 10 — Sync and concurrency.** A web endpoint serves many requests on an event loop. What happens if it calls synchronous `session.execute` on that event loop? When should you switch to `executeAsync`?

**Exercise 11 — Measurement.** Write a probe recording `latencyMicros`, `coordinator`, and `MATCH`/`MISMATCH`/`MISSING`/`READ_ERROR` for the same primary key before/after stopping a lab node. Why shouldn't `READ_ERROR` be counted as `MISSING`?

**Exercise 12 — Simple vs. prepared.** A query shape runs 10,000 times/second with varying parameters. Why is `PreparedStatement`/`BoundStatement` usually better than `SimpleStatement`, and why must partition key, CL, `LIMIT`, and page size still be right?

## Key Takeaways

**`SimpleStatement` describes a parameterized CQL query and execution settings; `CqlSession.execute(...)` runs synchronously, returning a `ResultSet` or throwing an error.** Always **reuse `CqlSession`**, bind values with `?` instead of string concatenation, query with full partition keys, set explicit projections/`LIMIT`/page size, read `Row` columns with matching types, and pick CL aligned with RF and local DC. **`one() == null` is not a read timeout; a write timeout does not prove the mutation was not applied.** For high-volume repeated query shapes, consider `PreparedStatement` and asynchronous execution while preserving **idempotency, retry budgets, latency measurement, and data verification** per application contract.
