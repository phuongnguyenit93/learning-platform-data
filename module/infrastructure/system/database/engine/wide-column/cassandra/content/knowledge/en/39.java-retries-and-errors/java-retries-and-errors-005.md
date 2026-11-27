# ReadFailure/WriteFailure, Overloaded, and Server Load

> **Chapter:** Java Retries and Errors  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Errors from the Java driver must be understood in light of partition keys, query-driven table design, replicas, consistency levels, commit logs, memtables, SSTables, compaction, and repair.

## 1. Objectives and Opening Scenario

A Java application writes events to Cassandra using **LOCAL_QUORUM**. During peak traffic, the dashboard reports three error categories: **ReadFailure**, **WriteFailure**, and **Overloaded**. One developer proposes fixing it by increasing timeouts, dropping the consistency level to **ONE**, and retrying every request aggressively.

That fix can make the incident worse:

- **ReadFailure/WriteFailure** indicates that one or more processing components reported an execution failure—not merely that the client “didn't wait long enough”.
- **Overloaded** signals that a Cassandra component cannot accept or process the current workload; immediate retries can trigger a **retry storm**.
- **WriteFailure or WriteTimeout does not prove the mutation was not applied** on any replica. Re-running a non-idempotent operation can cause duplicate records or side effects.
- Lowering the consistency level changes the API's consistency contract without addressing hotspots, I/O, GC, compaction, or the underlying traffic spike.

This lesson helps you:

1. Distinguish **ReadFailure**, **WriteFailure**, **Overloaded**, **ReadTimeout**, **WriteTimeout**, and **Unavailable**.
2. Understand the roles of the coordinator, replicas, and consistency level along the request path.
3. Implement error handling in **Java Driver 4.x** by error type and business requirements.
4. Design retries with backoff/jitter, concurrency limits, idempotency, and backpressure.
5. Diagnose server-side causes using logs, metrics, `nodetool`, and application telemetry.
6. Choose remediation paths when overload stems from hot partitions, collections, batches, compaction, repair, or system resources.

> **Version boundary:** Exact exception names, inspectable exception fields, and default retry behavior depend on your Java driver, native protocol, and Cassandra versions. Examples use **Java Driver 4.x** under the **com.datastax.oss.driver.api** namespace. Always verify documentation for your exact running release before applying production policies.

## 2. Read and Write Path Overview

Cassandra distributes rows by **partition key**; the coordinator uses the replication strategy and topology to contact the replicas owning that partition. The client specifies a **consistency level (CL)** defining how many responses are needed before treating the request as complete.

~~~mermaid
flowchart LR
    A["Java service / BoundStatement"] --> B["Driver picks coordinator"]
    B --> C["Coordinator locates partition key"]
    C --> R1["Replica 1"]
    C --> R2["Replica 2"]
    C --> R3["Replica 3"]
    R1 --> D["Commitlog + memtable / SSTable"]
    R2 --> D
    R3 --> D
    C --> E["Response or error to driver"]
~~~

For **writes**, replicas typically append to the commit log, update the memtable, and return an acknowledgment. For **reads**, replicas look up data across memtables, SSTables, indexes, and tombstones; the coordinator merges responses according to the read path. This pipeline has several failure points:

- Slow or network-partitioned nodes;
- Disk I/O or commit-log errors, full disks, GC pauses, or heap/native memory pressure;
- Excessive requests hitting one coordinator or specific replica set;
- Hot/wide partitions, heavy tombstones, or resource contention from compaction/repair;
- Values or queries exceeding version-specific limits/guardrails;
- Client-side timeout increases and retries inflating the backlog of in-flight requests.

**CL does not determine where a partition lives**; it governs response requirements. For example, with RF = 3 in a local DC, **LOCAL_QUORUM** normally requires responses from **2 of 3 replicas** in that DC. If two replicas fail or stall, requests can fail even while the third replica stays healthy.

## 3. Six Errors to Distinguish Before Retrying

| Signal | Application-level meaning | Key takeaway |
|---|---|---|
| **ReadFailure** | Coordinator/server received failure signals during read execution and could not satisfy CL | Does not mean merely waiting too briefly; find the execution failure cause |
| **WriteFailure** | Failure occurred during write processing on participating nodes and the request failed its success criteria | Some replicas may have applied the write; never assume not written |
| **Overloaded** | Server component reports insufficient capacity to accept/process the current request | Load-pressure signal; immediate retries are usually harmful |
| **ReadTimeout** | Insufficient read responses collected within the server processing timeout | Can result from slow nodes, network, tombstones, I/O, or query pressure |
| **WriteTimeout** | Insufficient write responses collected within the server processing timeout | Uncertain how far the data was persisted |
| **Unavailable** | Coordinator determines too few replicas are available to meet the requested CL | Distinct from timing out while waiting; check topology/replicas |

**Separate server errors from client-side errors.** The Java driver can also hit request timeouts, fail to reach nodes, or encounter TLS/auth errors. A **driver-side request timeout** is not the same as a **ReadTimeoutException** or **WriteTimeoutException** returned by Cassandra. Classify exceptions by exact class and error code rather than grepping for `"timeout"` in messages.

### 3.1. ReadFailure vs. ReadTimeout

**ReadTimeout** usually means the coordinator did not receive enough qualifying responses before the deadline, without necessarily receiving an explicit error from replicas. **ReadFailure** indicates an explicit processing failure was signaled during the read.

`ReadFailure` causes vary by Cassandra version—such as read-path errors, tombstone abort thresholds, or underlying I/O faults. Never guess the exact cause from the exception name alone; correlate **coordinator/replica server logs, table, partition, CL, and metrics at the exact timestamp**.

### 3.2. WriteFailure vs. WriteTimeout

**WriteTimeout** can occur when a write reached some replicas without collecting enough ACKs for the CL. **WriteFailure** reflects an explicit write-processing failure reported to the server; you must still consider whether other replicas applied the mutation.

For example, consider an `INSERT` into an RF = 3 partition at `CL = LOCAL_QUORUM`. Replica A succeeds, B fails writing to its commit log, and C has not responded yet. If the request fails, the client **cannot conclude the mutation is absent from A**. A retry generating a **new `event_id`** can create a second row instead of completing the first.

### 3.3. Overloaded vs. Unavailable

- **Overloaded:** capacity, queueing, resource saturation, or server-side load shedding. Replicas may still be UP yet lack resources to keep up with incoming rate.
- **Unavailable:** available replicas per the coordinator's view fall short of the consistency level; typically tied to node health, topology, or DC/RF.

A node marked **UP/NORMAL** can still be overloaded. Raising the replication factor or dropping CL just to silence errors does not address **traffic sources, partition distribution, or resource limits**.

### 3.4. Never infer write outcome solely from error type

| Outcome observed in Java | What can be concluded with certainty? |
|---|---|
| Write succeeds at CL | Satisfied the CL acknowledgment requirement per Cassandra semantics |
| WriteTimeout | Did not meet response criteria before deadline; write state may have changed |
| WriteFailure | Request failed per server response; must still handle partial-write possibilities |
| Overloaded | Server signaled overload; track where requests were rejected and their impact rather than assuming none persisted |
| Connection / client timeout | Client lacked a complete response; outcome may be ambiguous depending on timing |

This underpins **idempotent retries** and domain error handling. An `UPDATE` setting a deterministic value on a fixed key is far easier to reason about on retry than a counter increment, list append, or operation minting a new ID.

## 4. Consistency Level, RF, and Availability

### 4.1. Example: RF = 3, LOCAL_QUORUM

Suppose a keyspace uses **NetworkTopologyStrategy** in **dc1** with RF = 3:

~~~sql
CREATE KEYSPACE IF NOT EXISTS app_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
~~~

Run this only in an environment with matching topology and node count. With `LOCAL_QUORUM` in `dc1`, **2 responses** from the partition's replicas are normally needed. Therefore:

- One node down, two replicas healthy: `LOCAL_QUORUM` can still succeed.
- Two nodes down: insufficient replicas remain for `LOCAL_QUORUM`.
- One node down and another UP but disk-saturated: configured node count is met, yet latency/availability may still fail.
- If **LOCAL_ONE** is chosen for a read endpoint that tolerates slightly stale data, the response requirement drops, provided the business accepts that trade-off.

**Never automatically downgrade CL from LOCAL_QUORUM to LOCAL_ONE on retry** when the API promises stronger consistency. That changes data semantics and must be an intentional decision.

### 4.2. DC scope matters

**QUORUM** and **LOCAL_QUORUM** are not equivalent in multi-datacenter clusters. `LOCAL_QUORUM` counts a majority of replicas within the local DC; `QUORUM` spans replicas globally as defined by the server. Before calculating required replicas, check:

- The **keyspace** replication strategy;
- RF per DC;
- Which DC the Java driver treats as local;
- The effective CL set on the statement or execution profile;
- Inter-node connectivity and replica health.

**Consistency level is not a fix for bad schemas or queries missing a partition key.** Fix the model around access patterns first.

## 5. Distinguishing Data, Load, and Infrastructure Errors

| Symptom | Hypothesis to test | Signals / evidence |
|---|---|---|
| `ReadFailure` on a tombstone-heavy table | Scan hit tombstone abort limit or read-path failure | Server logs, tombstone metrics, `tablehistograms`, query shape |
| `ReadTimeout` rises during ingestion | Read path competing for I/O with flushes/compaction | Disk latency, `compactionstats`, GC, p99, pending tasks |
| `WriteFailure` concentrated on one node | Commit-log/disk/replica I/O or write-processing fault | Node logs, free disk, filesystem errors, JVM |
| `Overloaded` rising across multiple coordinators | Admission/backpressure limits, excessive concurrency | Driver in-flight, pending tasks, CPU/heap/native, queues/drops |
| Errors concentrated on one tenant | Hot partition or oversized partition | Per-partition-key frequency, partition size, token distribution |
| Errors spike during large `LOGGED BATCH` | Multi-partition fan-out overloading coordinator/batchlog | Batch size/partition count, write latency, warning logs |
| Load rises after mass TTLs/deletes | Tombstones and compaction/repair backlog | SSTable counts, tombstones, disk I/O |
| Java app times out with no matching server errors | Driver timeout, pool/queue/network, client load | Driver metrics/logs, client CPU/GC, network path |

These are **diagnostic hypotheses**, not 1:1 mappings from exception to root cause. One underlying issue can trigger multiple errors: a hot partition can cause read timeouts, overload coordinators/replicas, and amplify retries simultaneously.

### 5.1. Hot partitions are not split automatically by RF

Cassandra maps the partition key to a token and replica set. If 90% of writes target a single customer's partition, that partition's replica group can saturate while other nodes sit idle. **Adding more nodes does not automatically split one large partition into pieces.**

Remediation should start with:

- Analyzing access patterns (queries by tenant/day/hour/device?);
- Adding time buckets, deterministic sharding, or redesigning the primary key when needed;
- Bounding collection and payload sizes;
- Rate-limiting traffic to hot keys;
- Evaluating the fan-out trade-off when reading across multiple buckets, tested against realistic data.

### 5.2. Impact of compaction and repair

Cassandra uses an LSM storage engine: writes hit the commit log and memtable, flush to SSTables, and compact in the background. When compaction backlogs grow, read/write I/O faces contention. **Repair** consumes disk, network, and CPU—especially on large datasets or heavy tombstones.

Do not treat repair as a magic “fix-all” command whenever `ReadFailure` or `WriteFailure` appears. Repair requires scheduling, permissions, load control, and data assessment. If data was wrongly `DELETE`d, repair **will not undo that business operation**.

## 6. CQL Lab: A Query with a Proper Partition Key

Modeling events by tenant and day:

~~~sql
CREATE TABLE IF NOT EXISTS app_lab.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);
~~~

- **(tenant_id, event_day)** is the composite partition key. Both values must be computed consistently on reads and writes.
- **happened_at, event_id** are clustering columns, supporting ordered scans within the partition and unique row identification.
- A tenant generating millions of events/day can still create overly large daily partitions; measure partition size and peak rates and consider finer buckets.
- Never store unbounded events inside a single **list** merely because the Java driver can encode collections.

Insert a deterministic fixture:

~~~sql
INSERT INTO app_lab.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id,
    event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"order":"lab-001"}'
);
~~~

Read query:

~~~sql
SELECT happened_at, event_id, event_type
FROM app_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT ?;
~~~

In `cqlsh`, replace `?` with literals, or run as a prepared/bound statement from Java. **LIMIT** only bounds returned rows; it does not cure wide partitions or dense tombstones. Tests should assert **expected `event_id` values**, not merely that the query threw no exception.

## 7. Java Driver 4.x: Catching the Right Exceptions and Logging Useful Context

The example below reads a single partition at **LOCAL_QUORUM** and distinguishes server errors. This is a one-shot lab demo; long-lived applications should reuse **CqlSession** and **PreparedStatement** instances.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.servererrors.ReadFailureException;
import com.datastax.oss.driver.api.core.servererrors.ReadTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;

public class CassandraReadErrorDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement select = session.prepare(
                "SELECT happened_at, event_id, event_type " +
                "FROM app_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            BoundStatement request = select
                .bind(tenantId, eventDay, 20)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            try {
                ResultSet rows = session.execute(request);
                System.out.println(
                    "SELECT completed; rows=" + rows.all().size());
            } catch (ReadFailureException ex) {
                System.err.println(
                    "READ_FAILURE: inspect replica/server logs");
            } catch (ReadTimeoutException ex) {
                System.err.println(
                    "READ_TIMEOUT: insufficient read responses in time");
            } catch (OverloadedException ex) {
                System.err.println(
                    "OVERLOADED: shed load and apply backpressure");
            } catch (UnavailableException ex) {
                System.err.println(
                    "UNAVAILABLE: check RF/DC/live replicas and CL");
            }
        }
    }
}
~~~

**Scope and caveats:**

- Reading only **20 rows** allows `rows.all()` for illustration. On multi-page queries, `all()` fetches every page into memory; in production use bounded page processing.
- **ReadFailureException**, **ReadTimeoutException**, **OverloadedException**, and **UnavailableException** live in the driver 4.x **servererrors** package. Exact names and details depend on driver/protocol versions.
- The code logs the **error category**, avoiding real partition keys, payloads, passwords, or raw `BoundStatement` contents. Real services add operation IDs, controlled trace IDs, versions, and metrics.
- **setIdempotent(true)** applies here to a read-only `SELECT`. Never blindly mark writes with counters, list appends, or side effects as `idempotent=true`.
- Beyond these four, failures include **client-side request timeouts, network errors, authentication/TLS, schema, and codec errors**. Never catch just four and assume everything else is retryable.
- RF = 3 and `LOCAL_QUORUM` require enough replicas in **dc1**; adjust your lab if its topology differs.

### 7.1. Log by query shape, not customer data

Log like this:

~~~json
{
  "event": "cassandra_request_failed",
  "operation": "events_by_tenant_day.read",
  "error_class": "ReadFailureException",
  "consistency": "LOCAL_QUORUM",
  "query_shape": "read_one_tenant_day",
  "duration_ms": 1250,
  "retry_count": 0,
  "request_id": "req-example-31"
}
~~~

This is an **illustrative application JSON log**. Never log customer UUIDs, payloads, signed tokens, or CQL strings containing embedded user data; logs and traces must also follow access controls and retention rules.

## 8. Java: WriteFailure and Ambiguous Outcomes

For a deterministic `INSERT`, generate a stable key **before** execution so timeouts or retries do not create duplicate logical rows.

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;

UUID eventId = UUID.fromString(
    "22222222-2222-4222-8222-222222222222");
UUID tenantId = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
Instant happenedAt = Instant.parse("2026-11-21T08:00:00Z");

PreparedStatement insert = session.prepare(
    "INSERT INTO app_lab.events_by_tenant_day " +
    "(tenant_id, event_day, happened_at, event_id, " +
    "event_type, payload) VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement write = insert.bind(
        tenantId, LocalDate.of(2026, 11, 21),
        happenedAt, eventId, "ORDER_CREATED",
        "{\"order\":\"lab-001\"}")
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true);

try {
    session.execute(write);
    System.out.println("Write acknowledged at requested CL");
} catch (WriteFailureException ex) {
    System.err.println(
        "WRITE_FAILURE: outcome may be partial; investigate");
} catch (WriteTimeoutException ex) {
    System.err.println(
        "WRITE_TIMEOUT: do not assume write was not applied");
} catch (OverloadedException ex) {
    System.err.println(
        "OVERLOADED: stop flooding server; apply backpressure");
}
~~~

This snippet sits inside a method holding an initialized `CqlSession` named `session`. It performs an `INSERT` without TTL using a deterministic primary key and fixed values; marking it idempotent lets the driver consider it under retry/speculative policies, **without automatically making every retry safe in all scenarios**. On retry, keep `eventId`, `happenedAt`, and `payload` stable, and evaluate timestamps/TTLs, concurrent writes, and business side effects. An `INSERT` relying on server-generated timestamps can behave differently under concurrent writes; design idempotency end-to-end.

**Never place an immediate infinite retry loop inside `catch`**. Every failure should go through bounded retry decisions with backoff/jitter and circuit breakers/backpressure where used.

### 8.1. Avoid retrying non-idempotent operations

Hazardous example:

~~~sql
-- Do not assume safe retries when the outcome is ambiguous.
UPDATE app_lab.counters_by_tenant
SET total = total + 1
WHERE tenant_id = ?;
~~~

The syntax above illustrates a counter table **assuming `total` is defined as a counter with matching key**; it does not run against the event table in Section 6. A counter increment may have applied before a timeout, so resending it risks double-counting. Likewise, **list appends** or generating a **new `eventId`** per retry create logical duplicates.

Some use cases require event models with stable identifiers, deduplication, or conditional writes. **LWT `IF NOT EXISTS`** can also have ambiguous outcomes on timeout; a retry may return **`[applied] = false`** because the first attempt succeeded, requiring state reconciliation rather than treating `false` as an infrastructure failure.

## 9. When to Retry, When to Stop?

A sound retry strategy evaluates **request type, idempotency, error shape, deadlines, and actual load**, not exception names alone.

| Case | Cautious handling | Why |
|---|---|---|
| Idempotent `SELECT` hitting a transient fault | Bounded retries if deadline allows and server is not overloaded | Re-reading causes no writes, yet retries still consume resources |
| Repeated `ReadFailure` on the same partition | Stop bulk retries; inspect logs, table, and replicas | May stem from data corruption, tombstones, or node I/O faults |
| `WriteTimeout`/`WriteFailure` on deterministic `INSERT` | Retry **only if** write semantics are proven idempotent, with backoff and bounded attempts | First attempt may already have applied partially |
| Counter increment / list append | Do not auto-retry on ambiguous outcomes | High risk of doubling effects |
| Widespread `Overloaded` errors | Slow down, apply backpressure, shed new requests, retry very conservatively | Retry storms worsen server overload |
| `Unavailable` from missing replicas | Shedding load won't create replicas; check topology/CL and restore nodes | Immediate retries rarely change replica availability |
| Auth, schema, codec, or CQL syntax error | Never auto-retry; fix config or code | Retrying cannot fix wrong passwords or data types |
| HTTP/gRPC deadline already expired | Stop retrying immediately | Caller is gone; extra attempts waste resources |

**Never silently alter consistency levels inside a retry policy.** If an endpoint promises `LOCAL_QUORUM` reads, retrying at `LOCAL_ONE` violates correctness. Any degradation must be an explicit business policy with telemetry, not a hidden “error recovery default”.

### 9.1. Exponential backoff and jitter

Application-level algorithm example:

~~~text
base_delay = 100 ms
max_delay = 2 seconds
max_attempts = 3  (including initial attempt)

attempt 1: normal request
if error is classified as transient, request is idempotent,
deadline remains, and circuit is closed:
    delay = min(max_delay, base_delay * 2^(attempt-1))
    sleep an appropriate random duration in [0, delay]
    re-check deadline and load budget
    retry
else:
    return classified error, do not retry
~~~

Values **100 ms, 2 seconds, 3 attempts** are illustrative only; tune them to your SLO and capacity. **Jitter** prevents synchronized client wake-ups. Account for **every attempt's timeout, queueing delay, and backoff** in the total retry budget so you never exceed the business deadline.

With Java Driver 4.x, before adding an application-level retry layer, verify **the active driver retry policy, statement idempotency, and how many attempts the driver may already perform**. If both driver and application retry independently, total attempts multiply. When unsure, prefer **disabling or bounding layered retries** per an explicit design review.

### 9.2. Backpressure is more than sleeping

An overloaded server will remain flooded if the application holds an unbounded queue. Proper backpressure includes:

- Capping **in-flight** requests per application instance;
- Enforcing bounded queues that shed or degrade intentionally when full;
- Throttling per tenant or endpoint so one hot key does not starve all users;
- Propagating consistent timeouts/deadlines from caller to database;
- Enforcing a retry budget as a fraction of traffic so retries do not crowd out fresh requests;
- Monitoring pressure across **coordinators, replicas, and the Java driver connection pool**.

Never simply increase queue sizes or connection pools endlessly. Error counts may look lower for a few minutes while RAM, p99 latency, and unfinished work climb continuously.

## 10. Async Java: Bounding In-Flight Requests with a Semaphore

The example below does not implement retries; it illustrates **concurrency throttling before dispatching requests**. Each instance caps concurrent async requests awaiting responses.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedCassandraRequests {
    private final CqlSession session;
    private final Semaphore inFlight;

    public BoundedCassandraRequests(
            CqlSession session, int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrent must be positive");
        }
        this.session = session;
        this.inFlight = new Semaphore(maxConcurrent);
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {

        if (!inFlight.tryAcquire()) {
            CompletableFuture<AsyncResultSet> rejected =
                new CompletableFuture<>();
            rejected.completeExceptionally(
                new RejectedExecutionException(
                    "Cassandra client concurrency limit reached"));
            return rejected;
        }

        try {
            return session.executeAsync(statement)
                .whenComplete((result, error) ->
                    inFlight.release());
        } catch (RuntimeException error) {
            inFlight.release();
            throw error;
        }
    }
}
~~~

Key points to understand:

1. When permits are exhausted, the app **rejects predictably** instead of queueing indefinitely.
2. Permits are released when the **`executeAsync` stage completes**, whether with a result or an error.
3. For multi-page queries, the initial stage completes after the first page; subsequent page fetches must also be accounted for to bound total in-flight work.
4. This cap applies **per Java instance**, not globally across the service. With 20 instances, aggregate concurrency is 20x higher; add cluster-wide quotas or throttling where needed.
5. **`maxConcurrent`** must be tuned to topology, payload sizes, CL, latency, connection pools, and replica capacity. No single number fits all Cassandra clusters.
6. The **`RejectedExecutionException`** here is a **client-side rejection**, not an **`OverloadedException` from Cassandra**. Distinguish them in logs and metrics.

This sample covers only a simple single-page flow. Production code must integrate deadlines, cancellation/rejection, tracing, and ensure callbacks neither capture sensitive data nor feed another unbounded queue.

## 11. Server Diagnostics: Tools and Investigation Order

### 11.1. Gather evidence across three layers

**Application / driver layer:**

- Per endpoint or query shape: throughput, p95/p99, errors by exception type;
- Consistency level, local DC, execution profile, request timeout, retry policy;
- In-flight request counts, queues, rate-limit rejections, retry attempts, client count;
- Payload/batch/collection sizes and number of queried partitions;
- Incident start time and recent deploy or config changes.

**Cassandra node layer:**

- Node health, CPU, GC pauses, heap/native/RSS memory, free disk, disk latency/IOPS, network;
- Thread pools / pending tasks, dropped messages, overload/admission stats;
- Commit-log/memtable flushes, compaction backlog, repair/streaming, and tombstones;
- Server logs showing causes on coordinators and replicas at the exact incident window;
- Partition size distribution, hot keys, SSTable counts, and request frequency.

**Infrastructure layer:**

- Network between client↔coordinator and coordinator↔replica;
- Container memory / cgroup OOM kills and CPU throttling;
- Storage latency, filesystem errors, and capacity;
- Rack/DC/AZ topology and cluster changes.

**An application-facing error may originate on a replica other than the coordinator**, so avoid inspecting logs from only the first node the client talks to.

### 11.2. Illustrative `nodetool` commands

Run on authorized Cassandra nodes and verify syntax for your version:

~~~bash
# Node UP/DOWN status, tokens, and DC/rack.
nodetool status

# Individual node details.
nodetool info

# Thread pools, pending/active tasks, and dropped messages.
nodetool tpstats

# Active and pending compactions.
nodetool compactionstats

# Streaming / network tasks depending on version support.
nodetool netstats

# Table statistics, SSTables, partition sizes, and related metrics.
nodetool tablestats app_lab.events_by_tenant_day

# Partition size and row count distributions, depending on version.
nodetool tablehistograms app_lab events_by_tenant_day
~~~

Statistics are a **starting point**, not an automatic conclusion. For instance, a small **mean partition size** can hide a single massive partition. Likewise, a node with low average CPU but terrible disk latency can still trigger `WriteFailure` or `ReadTimeout`. Combine `nodetool` with logs, JMX/Prometheus metrics, and workload snapshots from the same window.

### 11.3. Eight-step investigation workflow

1. **Classify the error:** `ReadFailure`, `WriteFailure`, `Overloaded`, Timeout, `Unavailable`, or driver/network.
2. **Scope the blast radius:** single endpoint, query shape, tenant, table, DC, or all clients.
3. **Check topology and CL:** replication strategy, RF, local DC, node health, coordinator/replicas.
4. **Check load and resources:** CPU/GC/native memory, disk I/O, pending/dropped tasks, compaction/repair.
5. **Check the data model:** partition key, hot partitions, tombstones, collections, batches, and payloads.
6. **Check client amplification:** retry budget, instance count, concurrency, profiles/timeouts, queues.
7. **Relieve pressure safely:** throttle traffic / pause bulk imports, preserve SLA/consistency, recover faulty nodes/disks.
8. **Re-measure and verify:** p95/p99, error counts per class, data correctness across partitions, and post-incident repair/backups.

Do not rush to run repair or restart the whole cluster merely because reads/writes fail. If data corruption or loss is suspected, preserve evidence and recovery options before running state-mutating operations.

## 12. Root-Cause Optimization: Workload, Schema, and Capacity

### 12.1. Hot partitions / oversized partitions

Suppose a tenant emits 100 events/second at ~1 KiB per row:

~~~text
In 1 day:
100 x 86,400 x 1 KiB
= 8,640,000 KiB
≈ 8.24 GiB payload/day

In 1 hour:
100 x 3,600 x 1 KiB
= 360,000 KiB
≈ 351.56 MiB payload/hour

In 5 minutes:
100 x 300 x 1 KiB
= 30,000 KiB
≈ 29.30 MiB payload/5 minutes
~~~

These figures reflect **raw payload** before metadata, compression, tombstones, or peak skew. If daily partitions grow too large, consider hourly or 5-minute buckets and evaluate the multi-bucket read trade-off. Do not treat these numbers as official Cassandra limits.

### 12.2. Oversized batches

A **LOGGED BATCH** containing thousands of `INSERT`s across thousands of partitions puts heavy strain on the coordinator, batchlog, and replicas. CQL batches are **not a general-purpose bulk loader**.

- For independent writes across multiple partitions, **prepared statements with bounded concurrency** are usually far better than giant batches.
- When single-partition atomicity is needed, evaluate small single-partition batches per Cassandra semantics.
- Bound batches by **bytes, statement count, and partition count**, not statement count alone.
- Servers enforce version-dependent warning/failure thresholds for batches and mutations; never raise thresholds to mask poor data modeling.

### 12.3. Collections, tombstones, and TTLs

Large maps/lists/sets or frequent updates/deletes generate excessive cells and tombstones. Expiring TTLs also add read and compaction overhead. A `ReadFailure` triggered by tombstone scanning should never be “fixed” with 100 retries.

Model unbounded series as **separate rows** using clustering columns and sensible buckets; reserve collections for small bounded attributes of an entity. Track tombstones, partition histograms, compaction backlogs, and read latency per query shape.

### 12.4. Heap/native memory and disk

- **Larger JVM heaps** do not cure network overload or disk saturation; leave room for off-heap/native memory and OS page cache.
- **Free disk space** must accommodate SSTables, compaction, and repair. Full disks or I/O errors cause write failures.
- **GC pauses** make nodes stall, triggering client timeouts and retries.
- **Container memory limits** can OOM-kill Cassandra even when JVM heap metrics appear fine.
- When multiple nodes overload together, examine **aggregate client traffic, write replica fan-out, CL, and scheduled maintenance**.

## 13. Quantitative Scenario: `Overloaded` During Peak Hours

Suppose a cluster has RF = 3 in `dc1`, and a Java app uses `LOCAL_QUORUM` for most writes. The SLO targets p99 write latency under 300 ms. After autoscaling the application from 10 to 25 instances:

| Metric | Before | During incident |
|---|---:|---:|
| Write requests from app | 6,000/s | 15,000/s |
| p99 write latency | 170 ms | 1,900 ms |
| App retry rate | 1% | 25% |
| `Overloaded` errors | Very rare | Spiking sharply |
| Pending tasks | Low | High |
| Disk utilization | 55% | Near saturation |
| Compaction backlog | Steady | Continuously growing |

**Strong hypothesis:** total traffic surged, retries further multiplied load, and disk writes plus compaction fell behind. Verify with metrics and logs before ruling out other causes.

**Priority actions:**

1. Halt ingestion autoscaling or throttle **in-flight** requests per instance.
2. Curb retry amplification; never retry immediately on `Overloaded`.
3. Throttle bulk ingestion if needed and prioritize SLA-critical traffic per policy.
4. Inspect disk/GC/compaction, hot partitions, batch sizes, and write distribution.
5. Only after load stabilizes, perform capacity planning, adjust schema/buckets, or add nodes and rebalance tokens.
6. Re-measure p99, error rates, queues, dropped messages, backlog, and **effective** throughput afterward.

**Do not default to dropping CL from LOCAL_QUORUM to ONE** if the application guarantees local-quorum write durability. That alters data recovery/read guarantees without fixing the overload source.

## 14. Second Scenario: `ReadFailure` on a Single Partition

A Java app queries one customer's transaction history and receives `ReadFailure`, while other customers read fine. Telemetry shows that customer's partition is huge, spanning many SSTables with dense tombstones from deleted historical transactions.

**Diagnostic steps:**

1. Check the query shape and **full partition key**; is it using `ALLOW FILTERING` or wide range scans?
2. Inspect server logs at the `ReadFailure` timestamp, especially on the coordinator and token-owning replicas.
3. Read partition histograms, tombstone metrics, SSTable counts, and compaction stats.
4. Test a narrower range in a **permitted environment** to isolate scan scope; avoid firing floods of test queries that add load.
5. Revisit the table design: can you partition by `(tenant_id, bucket_day/hour)` with better TTL/retention?
6. Plan a query-driven table migration and validate data integrity; never try to alter a primary key in place on existing data.
7. After reducing pressure, re-measure latency/errors and coordinate compaction/repair with maintenance windows.

**Retries will not shrink a partition.** Neither should you raise guardrails or tombstone thresholds indefinitely to hide bad data modeling.

## 15. LWTs, Retries, and the Limits of “Idempotent”

### 15.1. `IF NOT EXISTS` still needs ambiguous-outcome handling

A Java service runs:

~~~sql
INSERT INTO app_lab.orders_by_id (
    tenant_id, order_id, status
) VALUES (?, ?, ?) IF NOT EXISTS;
~~~

This example targets a **separate table**, not the event table from Section 6. LWT checks conditions within Cassandra's supported scope, yet timeouts on conditional operations can still happen across multiple phases.

If the initial order creation succeeded while the client missed the response, retrying with the same order ID may return **`[applied] = false`** because the row already exists. The application must reconcile the stored order and request ID rather than blindly assuming the request failed.

### 15.2. Database-level vs. business-level idempotency

An `INSERT` with the same key and values may be idempotent for row state, yet if each client retry also sends an email, charges a card, or mints a new event ID, **the overall workflow is not idempotent**.

Typical safeguards required:

- A deterministic business key (`orderId`/`eventId`) persisted before the first attempt;
- A request-ID tracking table or deduplication mechanism by design;
- Outbox/event processing with duplicate-execution protection;
- State verification after ambiguous outcomes;
- Retry caps and dead-letter/quarantine workflows for non-self-healing errors.

The driver's **`setIdempotent(true)`** is a hint enabling driver policies; it **does not turn non-idempotent CQL into a safe operation**. Developers must prove idempotency holds.

## 16. Controlled Testing Scenarios

In staging with matching RF/DC topology and synthetic data:

1. **Baseline:** measure read/write p50/p95/p99 and error counts under normal load.
2. **One slow replica:** simulate I/O or network latency using approved test mechanisms; compare `LOCAL_ONE` and `LOCAL_QUORUM`.
3. **One unavailable replica:** observe `Unavailable`/timeouts per RF and CL; never run in production.
4. **Controlled load ramp:** identify when `Overloaded`, pending tasks, and backlogs begin rising.
5. **Retry storm:** test with a capped traffic generator; measure amplification with and without backoff jitter.
6. **Idempotent write:** use a fixed event ID, inject a timeout, apply throttled retry, and verify only one logical row exists.
7. **Non-idempotent counter/list operation:** test on lab data to demonstrate duplicate-effect hazards.
8. **Hot partition:** compare evenly spread tenants against a single-tenant spike; never assume adding nodes spreads a hot key.
9. **Compaction/repair pressure:** observe scheduled background job impact; never trigger repair purely to induce faults without a runbook.
10. **Java bounded concurrency:** verify that exhausting permits sheds/rejects client load rather than building unbounded queues.

Test conclusions must record **Cassandra/driver/JDK versions, node count, RF, CL, workload, payload, latency, error types, retry budget, server metrics, and untested scope**. A single-node lab cannot validate multi-DC production quorum behavior.

## 17. Scenario Exercises

### Exercise 1 — How does `ReadFailure` differ from `ReadTimeout`?

An app hits `ReadFailure` on a tombstone-heavy partition, while another query hits `ReadTimeout` when a replica suffers slow disk I/O.

**Question:** Why shouldn't both be handled with a tight retry loop?

**Suggested answer:** `ReadFailure` indicates an explicit read-processing failure, whereas `ReadTimeout` indicates missing responses before the deadline. Both require logs/metrics to isolate root causes; aggressive retries will not fix tombstones, disk I/O, or data models and only add load.

### Exercise 2 — Does `WriteFailure` mean nothing was written?

A `LOCAL_QUORUM` write on RF = 3 sees one replica succeed, another fail, and fails to meet required responses. The client catches `WriteFailure`.

**Question:** Can you generate a new event ID and retry?

**Suggested answer:** Not safely by default. One replica may already have applied the write. Keep the event ID stable, verify idempotency, and reconcile state when outcomes are ambiguous.

### Exercise 3 — `Overloaded` and scaling the application

A cluster enters `Overloaded` after Java instances double, with each instance allowed 1,000 in-flight requests.

**Question:** Why can adding application instances make things worse?

**Suggested answer:** Total concurrency and request rate surge while coordinators/replicas, disks, and queues do not scale automatically with clients. Enforce per-instance and global in-flight caps, apply backpressure, curb retry storms, and plan capacity.

### Exercise 4 — `LOCAL_QUORUM` requirements

RF = 3 in `dc1`. One replica is DOWN, and another is UP but frequently timing out.

**Question:** Is `LOCAL_QUORUM` still guaranteed simply because RF is configured as 3?

**Suggested answer:** No. Two responsive replicas in the local DC are needed, yet only one responds reliably. Recover the down replica or fix disk/GC/network issues; lowering CL must be a controlled business decision.

### Exercise 5 — A counter increment times out

A counter increment hits `WriteTimeout`. The driver is configured for up to 3 retries.

**Question:** What is the hazard?

**Suggested answer:** Counter increments are not idempotent; the first attempt may have applied. Retrying can double-increment. Use deduplication or an event-based model rather than tuning retry counts.

### Exercise 6 — Retry budget within a deadline

An endpoint has a 2-second deadline, and each Cassandra attempt has a 1.5-second timeout. A developer proposes 3 retries with 1-second backoff.

**Question:** Why is this plan invalid?

**Suggested answer:** Total wait time far exceeds the 2-second deadline. Budget retries across per-attempt timeouts, backoff, and processing overhead; stop retrying when insufficient time remains.

### Exercise 7 — Hot partitions and RF

One tenant drives 80% of traffic. Operations raises RF from 3 to 5 to relieve the hot partition.

**Question:** Will higher RF automatically split the partition and scale throughput by 5/3?

**Suggested answer:** No. Every replica still holds a copy of that partition, and writes require maintaining even more replicas. Redesign partition keys/buckets/shards around access patterns and re-measure load.

### Exercise 8 — Separating two overload layers

The app logs a `RejectedExecutionException` from a client semaphore when permits run out; Cassandra's `Overloaded` metric does not rise.

**Question:** Can you conclude Cassandra threw `OverloadedException`?

**Suggested answer:** No. That is **client-side admission rejection**. Distinguish it from Cassandra's `OverloadedException`; client-side load shedding may be successfully protecting the cluster.

## 18. Operations and Engineering Checklist

- [ ] Classify `ReadFailure`, `WriteFailure`, `Overloaded`, `ReadTimeout`, `WriteTimeout`, `Unavailable`, and client/network timeouts accurately.
- [ ] Record RF, topology/DC, consistency level, and replica health at incident time.
- [ ] Never treat `WriteFailure`/`WriteTimeout` as proof that **no replica applied the write**.
- [ ] Retry only when safe per business semantics, idempotency, deadlines, and retry budget.
- [ ] Never auto-retry endlessly on `Overloaded` or trigger retry storms.
- [ ] Never silently downgrade consistency levels to mask availability errors.
- [ ] Ensure prepared/bound statements include full partition keys and properly bucketed/sharded data.
- [ ] Bound collection, mutation, batch, and partition sizes.
- [ ] Configure bounded in-flight requests, finite queues, and backpressure in the Java client.
- [ ] Separate driver retries from application retries and track total attempts.
- [ ] Monitor p95/p99, timeout/error types, queues/dropped messages, disk I/O, GC, memory, and compaction.
- [ ] Inspect server logs on relevant coordinators and replicas, not just app logs.
- [ ] Maintain version-appropriate `nodetool`/metrics tooling and data-protection runbooks.
- [ ] Check TTLs/tombstones, repair, and backups when data loss or corruption risk exists.
- [ ] Test on representative topology before changing retry policies, timeouts, or concurrency in production.
- [ ] Log query shapes and operation metadata without sensitive data or raw bind values.

## 19. Summary

**ReadFailure** and **WriteFailure** signal explicit failures during server-side read/write processing; **ReadTimeout/WriteTimeout** reflect missing responses within the server deadline; and **Overloaded** reports capacity pressure. Never lump these together into “retry as fast as possible”. In particular, a failed or timed-out write has an **ambiguous outcome** from the client's perspective.

In Cassandra, effective error handling starts with **partition keys, topology/RF, consistency levels, replica health, hot partitions, tombstones, compaction, and repair**. In Java Driver 4.x, catch specific exceptions, uphold idempotency, bound retries and deadlines, throttle in-flight requests, and monitor both client and server layers. **The goal is not merely fewer logged exceptions, but restoring service with accurate data under sustainable load.**
