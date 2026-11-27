# Write Overload, Queues, and Version-Specific Throttling Mechanisms

> **Chapter:** Write Path and Durability  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — distributed architecture and wide-column model of Apache Cassandra, from partition keys, query-driven table design, and read/write consistency to CQL, replication, compaction, repair, error handling, and Java application integration.

Apache Cassandra is optimized for high write throughput, yet **fast writes do not mean infinite ingestion capacity**. When an application produces mutations faster than coordinators, replicas, commit logs, memtable flushes, or disks can handle, queues grow. The result can be spiking p99 latency, timed-out requests, overload errors, and cascading failures from client retries. Results from a single successful `INSERT` under low load do not predict cluster behavior at peak load.

This lesson focuses on **write overload mechanics, where queues form, how to observe and throttle load**, and highlights **key differences across Cassandra 3.11, 4.0, 4.1, and 5.x**. Configuration names are not an immutable API: during operations, always cross-check the exact version and distribution you are running. The overload experiments below belong strictly in an isolated lab cluster with clear stop thresholds.

## 1. Learning Objectives

After finishing this lesson, you will be able to:

1. Diagram and explain the write flow from Java client to coordinator, replicas, commit log, memtable, and SSTables; pinpoint where bottlenecks occur.
2. Distinguish **backlog**, **backpressure**, **rate limiting**, **load shedding**, **timeout**, and **retry**.
3. Interpret `nodetool tpstats`, `compactionstats`, JMX/metrics, and Java driver stats to isolate bottlenecks.
4. Explain why Cassandra 3.11 backpressure docs must **not** be copied verbatim to 4.x/5.x; understand the scope of native transport rate limiting in 4.1/5.x.
5. Design bounded load tests; propose application-side throttling and operational actions to protect availability, latency, and data durability.
6. Handle **ambiguous** write outcomes upon timeouts without introducing business errors from blind retries.

## 2. Write Path and Where Queues Form

### 2.1. Flow of a Normal Mutation

~~~mermaid
flowchart TD
    A["Java app: producer and internal queues"] --> B["Driver: pool, in-flight limit, timeouts"]
    B --> C["Coordinator: native transport and request handling"]
    C --> D["Select replicas via token, RF, and topology"]
    D --> E["Internode messaging: send mutation"]
    E --> F1["Replica 1"]
    E --> F2["Replica 2"]
    E --> F3["Replica 3"]
    F1 --> G1["Commit log + memtable"]
    F2 --> G2["Commit log + memtable"]
    F3 --> G3["Commit log + memtable"]
    G1 --> H["Coordinator collects enough ACKs per CL"]
    G2 --> H
    G3 --> H
    H --> I["Response to Java client"]
    G1 -. "Background flush" .-> J["SSTable on disk"]
    G2 -. "Background flush" .-> J
    G3 -. "Background flush" .-> J
    J -. "Background compaction" .-> K["Merged SSTables"]
~~~

**High-level steps:**

1. The application sends CQL `INSERT`/`UPDATE`/`DELETE` over the native protocol. The receiving node acts as **coordinator**; it does not have to be a replica storing the partition.
2. The coordinator computes the partition location from the **partition key**, identifies replicas per the replication strategy, and sends the mutation over internode networking.
3. Each replica receives the mutation, writes to the **commit log**, and updates its **memtable**; commit log sync details prior to acknowledging depend on `commitlog_sync`.
4. The coordinator waits for enough replica responses per the request's **consistency level (CL)**. Work off the response path can continue asynchronously.
5. Memtables flush to **SSTables**, and compaction runs later in the background. **Not every write waits for an SSTable flush** before replying to the client.

A queue at any point in this diagram can inflate end-to-end latency. For example, if the commit log stays writable while flushes fall behind, memtables and commit log segments accumulate and block writes; adding more request-handling threads can simply make queues **longer** without lifting the I/O ceiling. <a id="writepath"></a>

### 2.2. Write Durability and Replica Acknowledgment Are Two Orthogonal Axes

With `durable_writes: true` on the keyspace, Cassandra uses the commit log per the configured durability policy. Distinguish:

| Axis | Example setting | What it controls |
|---|---|---|
| **Replicas required to acknowledge** | `ONE`, `LOCAL_QUORUM`, `QUORUM`, `ALL` | When the coordinator can return **success** per consistency requirements |
| **Commit log sync** | `commitlog_sync: periodic` or `batch` | When each replica's log is fsynced relative to its sync schedule / ACK path |
| **Memtable flush** | Automatic at memory / commit log thresholds | When mutations move into SSTables |
| **Replication / repair** | RF, strategy, hinted handoff, repair | Which nodes hold copies and how copies converge |

- With commit log **`batch` mode**, Cassandra waits for commit log fsync before acknowledging the mutation locally, strengthening node-level durability at the potential cost of higher write latency.
- With **`periodic`**, writes can be acknowledged before the next periodic fsync finishes; a sudden outage can lose recent un-fsynced entries on affected replicas. The at-risk window does not strictly equal the configured interval if fsync stalls.
- Higher CL raises the replica response requirement; it does **not** turn `periodic` into `batch`. Conversely, `batch` commit log sync does not create a quorum on its own.

**Note:** the word "batch" in `commitlog_sync: batch` **differs** from the CQL `BEGIN BATCH` statement. Using CQL batches to bundle rows across many partitions does not make Cassandra write faster automatically; multi-partition batches incur extra coordinator/batchlog overhead.

## 3. Overload Mechanics: Arrival Rate, Service Rate, and Backlog

Notation:

- `λ`: incoming write request rate, e.g., 2,000 requests/sec.
- `μ`: sustained processing throughput under current conditions, e.g., 1,500 requests/sec.
- `Q(t)`: number of requests waiting at a stage.

If incoming load **sustainedly exceeds** service rate, backlog grows roughly by `(λ − μ) × Δt` before blocking or shedding kicks in. For instance:

~~~text
Arrival rate (λ)         2,000 writes/s
Service rate (μ)         1,500 writes/s
Excess                     500 writes/s
Added backlog after 30s 15,000 requests (theoretical estimate)
~~~

This illustrates **flow balance**, not an exact prediction for a Cassandra cluster: coordinator/replicas, mutation size, timeouts, driver, network, and queue bounds all cause `μ` to vary. Still, it states a firm rule: **no finite queue can absorb overload indefinitely**.

At steady state, Little's Law `L = λ × W` relates items in the system (L), throughput (λ), and average residence time (W). For example, holding 1,000 requests in-flight while achieving 2,000 requests/s implies an average residence time around 0.5 seconds; raising the in-flight cap will not make physical disks serve any faster.

### 3.1. Distinguishing Five Phenomena

| Term | Meaning | Typical manifestation |
|---|---|---|
| **Queue/backlog** | Work accepted but waiting for execution | Rising `Pending`, long tail latency |
| **Backpressure** | Slowing the **sender** down because the receiver cannot keep up | Client blocked/throttled reading from sockets, or producer pauses ingestion |
| **Rate limiting** | Capping admission/send rate over time | QPS is bounded; excess is delayed or rejected depending on mechanism |
| **Load shedding/reject** | Rejecting part of incoming work to protect the system | Explicit overload errors, rising rejection rate |
| **Timeout** | Result did not arrive before deadline | Can happen even after some replicas already applied the mutation |

These are **not synonymous**. Backpressure may raise latency while curbing immediate errors; load shedding keeps the system healthy for remaining traffic. A timeout is an observed symptom of a delayed call, not a diagnosis of its cause.

### 3.2. Why Unbounded Retries Trigger a "Retry Storm"

Suppose a client sends 1,000 mutations in one second, 10% time out, and each timeout is immediately retried twice. Incoming load jumps by up to 200 requests precisely when the cluster is already slow; if those retries time out too, load keeps snowballing. Older requests may still be executing on replicas while duplicates arrive.

**Practical rule:** keep retry budgets small, use exponential backoff with jitter, bound both **in-flight** requests and send rate, and apply circuit breakers/load shedding at the application edge when needed. Only auto-retry when **business semantics and statement type** permit; a write timeout can leave an **ambiguous** result.

## 4. Where Is the Bottleneck? Observe Before Tuning Config

### 4.1. Queues at Client and Coordinator

**Java client/driver:**

- A producer pulling events from HTTP/Kafka can build a backlog **ahead of the driver**; the request count Cassandra sees is smaller than what the application has queued.
- The driver uses connection pools and caps concurrent requests per connection. When callers submit too rapidly, pool acquisition waits and request timeouts can spike even before Cassandra touches them.
- With large payloads or concurrent batches, **in-flight bytes** matter as much as request count; looking solely at requests/s misses oversized payloads.

**Coordinator:**

- Native transport accepts and schedules requests; if ingress is too high, requests queue or get throttled depending on version and config.
- The coordinator may wait on ACKs from multiple replicas; `LOCAL_QUORUM` with RF = 3 in the local DC typically needs two replicas, while `ONE` needs one. Raising CL can stretch the "awaiting replicas" portion when one replica slows down.
- Not every coordinator is equally busy. Token-aware routing and partition key distribution affect where work lands, while hot partitions overheat a specific replica group.

**Signals to correlate:** client pending/latency, in-flight request count, coordinator write latency, thread-pool wait times, and write load balance across nodes.

### 4.2. Queues in Internode Messaging, Replicas, and the Storage Engine

| Bottleneck | Practical symptom | Possible causes |
|---|---|---|
| Internode mutation delivery | Network latency spikes, expired/dropped messages | Network congestion, excessive requests, slow replicas |
| Mutation workers | `MutationStage`/corresponding pool shows rising `Pending` and `Blocked` over time | CPU/GC, write volume, lock/resource contention |
| Commit log | Rising `CommitLog.PendingTasks`, `WaitingOnCommit`, `WaitingOnSegmentAllocation` | Slow fsync, disk I/O, or waiting for segments |
| Memtable/flush | Rising `PendingFlushes`, memtable bytes, and flush duration | Slow disk, flush writers falling behind |
| Compaction | Rising `Compaction.PendingTasks` and SSTable backlog | Write amplification, disk/CPU limits, throttled compaction |
| Disk capacity | Disk near full, I/O errors, commit log/flush/compaction out of space | Insufficient capacity or growing data/tombstones/SSTables |
| Post-outage hints | Hints accumulating, slow delivery, or window expiring | Down nodes, network issues, high mutation volume |

Often the **true bottleneck is the disk**, while the first visible symptom is `Pending` in a thread pool. Correlate metrics across **the same time window**: seeing "1,000 pending mutations" does not prove you should raise thread counts. Raising concurrency usually worsens disk/GC saturation when I/O is the ceiling.

Several Cassandra metrics report **cumulative totals since node startup** rather than current queue depth; for counters, compute per-minute rates/deltas and compare per node. Stage names, metric paths, and exact meanings vary across versions.

## 5. Version Differences: Never Copy Config Recipes Blindly

### 5.1. Version Orientation Table

| Apache Cassandra branch | Mechanisms / points to know | What must NOT be inferred |
|---|---|---|
| **3.11** | Official docs include `back_pressure_enabled` and `back_pressure_strategy` (*RateBasedBackPressure*) so coordinators throttle mutations sent to replicas | Do not assume it is enabled; documented default is `false`. Do not apply legacy key names to newer branches |
| **4.0** | Internode messaging and execution architecture changed substantially from 3.11; rely on 4.0-appropriate metrics and limits | Do not assume a native transport request-per-second limiter sharing 4.1 keys exists if 4.0 docs do not list it |
| **4.1** | `cassandra.yaml` docs document `native_transport_rate_limiting_enabled` and `native_transport_max_requests_per_second`; behavior depends on client connection's `THROW_ON_OVERLOAD` option | This controls **native transport ingress** on a node, not RF/CL guarantees or write IOPS caps across all replicas |
| **5.0 / 5.x** | Retains native transport rate limiting and overload-related native protocol metadata; memory metrics/limits and config keys may differ | Do not assume 5.x field names, defaults, or syntax are valid across all 3.x/4.x clusters or custom distributions |

**Reference before editing:** [Cassandra 3.11 `cassandra.yaml`](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html), [4.0](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html), [4.1](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html), [5.0](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html). Always verify your running version with `SELECT release_version FROM system.local;` and inspect **your distribution's actual config file**.

### 5.2. Legacy Mechanism: RateBasedBackPressure in Cassandra 3.11

The 3.11 documentation describes these keys:

~~~yaml
# Excerpt of option names for Apache Cassandra 3.11; DO NOT use verbatim
# as a configuration guide on 4.x/5.x.
back_pressure_enabled: false
# back_pressure_strategy: ...
~~~

When configured, coordinators could throttle how fast mutations were pushed to replicas based on request/response ratios per the strategy. Yet this was only **one link in the chain**: if the application kept pushing unbounded load, backlogs simply shifted from replicas back to coordinators or the application. Never treat this as a guarantee that the cluster "absorbs any burst."

**Important:** `cassandra.yaml` docs for 4.0, 4.1, and 5.0 do not list `back_pressure_enabled`/`back_pressure_strategy` as in 3.11. Therefore, on newer branches **do not paste** 3.11 config into `cassandra.yaml` expecting it to take effect. Changes to internode messaging and throttling must follow version-specific documentation, metrics, and load tests.

### 5.3. Native Transport Rate Limiting in Cassandra 4.1 and 5.x

The snippet below is **syntax illustration** from 4.1/5.x docs, not a configuration to enable as-is:

~~~yaml
# Version-specific reference; set in a lab only after verifying
# syntax, client impact, defaults, and active configuration.
native_transport_rate_limiting_enabled: true
native_transport_max_requests_per_second: 10000
~~~

The number 10,000 requests/s is a **lab placeholder**, not a default recommendation. It represents a limit on **requests admitted via native transport on a single node**, not cluster-wide successful writes or physical disk speed.

Native protocol and `cassandra.yaml` docs describe two response behaviors when the limit is exceeded:

1. If the client connection negotiated `THROW_ON_OVERLOAD`, the server can **return `OverloadedException`** for requests exceeding the limit.
2. Otherwise, the server can **pause reading messages from the socket** to exert backpressure; the application may observe rising queues/latency instead of immediate overload errors.

The driver and native protocol version must support negotiating the corresponding behavior. **Do not assume** your Java application enables `THROW_ON_OVERLOAD` just because the cluster supports it. Check driver version, effective configuration, load test behavior, and logs. A timeout under backpressure configuration **does not mean** the mutation was never processed.

**Protection boundary:** a native transport ingress limiter caps request admission rate on the coordinator node; however, one request can fan out into multiple replica messages, multiple mutations, or widely varying I/O costs. Hence per-node request/s rate limiting is only one safeguard—not a substitute for controlling in-flight work, mutation sizes, partition design, disk monitoring, and CL planning.

### 5.4. Other Throttle Points to Distinguish

| Location | Mechanism | Notes |
|---|---|---|
| Producer/API/Kafka consumer | Token-bucket QPS caps, bounded queues, pause/resume consumption | Usually the closest point to the source and easiest to control |
| Java driver | Async in-flight limits, pools, sensible timeouts, retry budgets | Connection count is not operations/s; avoid creating a new session per write |
| Coordinator native transport | Admission rate limits, overload errors, or socket read pausing per version | Monitor both server **and** client latency/queues |
| Internode messaging | Memory/bandwidth limits, message management, timeouts/drops | Config keys and metric names vary by version |
| Commit log/memtable/flush | Throttling/blocking writes under resource pressure | Disk/flush is a physical ceiling; never "fix" by raising threads blindly |
| Compaction | Throughput throttling, concurrent compactors | Too low builds SSTable debt; too high steals foreground I/O |
| Business admission policy | Return HTTP 429/503, ask callers to retry later, prioritize critical tasks | Protects user-facing requests when demand exceeds real capacity |

Verify exact names, units, and defaults for `concurrent_compactors`, `compaction_throughput`, memtable/flush settings, and commit log settings against your exact release. Raising a limit before isolating the bottleneck usually just **pushes the queue down to a lower layer**.

## 6. Practice: Establishing a Baseline and Bounded Overload Testing

### 6.1. Lab Prerequisites

Set up a test Cassandra cluster—multi-node if you want to observe internode paths and CL—along with `cqlsh`, `nodetool`, the Java driver, or a QPS-controlled load generator. Record:

- Actual Cassandra version, node/DC/rack counts, CPU/RAM/disk specs, RF, and CL.
- Commit log sync mode (`periodic`/`batch`), native transport settings, and in-flight caps.
- Compaction strategy, background load, disk capacity, and node health.
- Client connection count, mutation sizes, request types, and read/write ratio.

Run strictly on clusters with **no production data**, and never run destructive commands to "clean up quickly." Define test stop criteria upfront: if p99 breaches your lab SLO across multiple measurement windows, errors spike, disks near capacity, or `Pending` climbs without recovering, throttle/stop the producer and watch the cluster drain its backlog.

### 6.2. Create a Table with an Appropriate Partition Key

In `cqlsh`, verify the DC name via `nodetool status` and choose an RF matching actual node count. The example below applies only to a DC named `dc1` with at least three nodes:

~~~sql
CREATE KEYSPACE IF NOT EXISTS write_overload_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS write_overload_lab.events_by_tenant_day (
    tenant_id uuid,
    day_bucket date,
    event_id uuid,
    occurred_at timestamp,
    payload text,
    PRIMARY KEY ((tenant_id, day_bucket), event_id)
);
~~~

Explanation: `tenant_id, day_bucket` is a compound partition key; `event_id` is the clustering key, identifying each event stably within a tenant/day. Using many tenants and days exercises load distribution. One huge tenant can still create a **hot partition** per day; if so, split into smaller buckets or add intentional sharding rather than adding threads to mask symptoms.

Sample mutation:

~~~sql
INSERT INTO write_overload_lab.events_by_tenant_day
    (tenant_id, day_bucket, event_id, occurred_at, payload)
VALUES (
    5bd928ad-a5aa-4eb9-8c12-bfda73571a70,
    '2026-11-21',
    b399f6fb-1fa1-49e2-b56e-3455412a66dd,
    '2026-11-21T09:00:00Z',
    'sample-001'
);
~~~

Each benchmark event should use a **stable ID** across retries; log partition distribution ratios and payload sizes. Never funnel millions of mutations into **one** `(tenant_id, day_bucket)` if the goal is measuring cluster-wide throughput: that tests a hot partition rather than distributed cluster capacity.

### 6.3. Load Phases and Metrics to Record

Step through bounded stages using **hypothetical test rates** like those below; never assume these are real hardware capacities:

| Phase | Hypothetical input | Goal | Observations |
|---|---|---|---|
| Baseline | 200 writes/s, bounded concurrency | Establish latency and resource baseline | p50/p95/p99, disk, Pending, errors |
| Controlled ramp | 400 then 600 writes/s | Find where queues start growing | Offered λ, successful throughput, p99 |
| Short burst | 2× baseline in a brief window | Observe burst absorption | Queue depth, recovery time |
| Recovery | Return to 200 writes/s | Confirm backlog drains | Pending returns to baseline, latency/errors stabilize |
| Throttled control | Same workload with source in-flight & QPS caps | Verify impact of application backpressure | Client/server queues and success rate |

Design both measurement styles:

- **Open-loop:** load generator attempts to dispatch at a target QPS; best for exposing overload. Always record **offered load** even when the server cannot accept or process it.
- **Closed-loop:** sends the next request only after a prior one completes or an in-flight slot opens; good for measuring latency at fixed concurrency, though it naturally slows QPS when the system degrades.

Never compare open-loop and closed-loop runs as if they were the same test. A slowing system can look "stable" in a closed-loop run merely because the send rate automatically collapsed.

Run long enough to observe queue trends (and recovery), but enforce **stop limits**; never push overload until nodes crash. Document warm-up conditions, compaction/GC activity, and disk I/O separately.

### 6.4. Collecting Data with nodetool

During measurement windows, on **each node**:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats write_overload_lab.events_by_tenant_day
nodetool netstats
~~~

Some versions support extra flags or display different pool names; `nodetool help` on your running version is the source of truth for syntax. These commands are read-only and delete no data.

**Reading `tpstats` properly:** compare `Active`, `Pending`, `Completed`, `Blocked`, and `All time blocked` across time windows, not from one snapshot. The `Dropped Messages` section usually reports **cumulative counters**; compute deltas per window. Rising dropped `MUTATION` messages warrant investigation, yet do **not** automatically mean each dropped mutation lost data permanently or that confirmed writes failed.

**Reading `compactionstats` properly:** steadily rising pending compactions can signal write amplification and disk pressure. Yet never treat `pending > 0` alone as an error; check sustained growth, data state, and foreground throughput/latency together.

### 6.5. JMX Metrics to Correlate

Per [Cassandra Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html), key groups to track:

| Metric / group name | Meaning when suspecting write overload |
|---|---|
| `ClientRequest.Write.Latency`, `Timeouts`, `Failures`, `Unavailables` | Are coordinators experiencing higher write latency and errors? |
| `ThreadPools.*.PendingTasks`, `ActiveTasks`, `CurrentlyBlockedTasks` (names may vary) | Which execution stage is backing up? |
| `DroppedMessage.MUTATION.Dropped` and related message types | Did messages time out or get dropped during the window? |
| `CommitLog.PendingTasks`, `WaitingOnCommit`, `WaitingOnSegmentAllocation` | Is the commit log waiting on fsync or segments? |
| `Table.PendingFlushes`, `MemtableLiveDataSize`, `WriteLatency` | Are memtable flushes keeping pace with writes? |
| `Compaction.PendingTasks`, `Table.PendingCompactions` | Is background compaction work accumulating? |
| `Storage.TotalHints`, HintsService metrics | Are hints piling up due to unhealthy replicas? |
| OS CPU, GC, disk IOPS/latency, filesystem free space, network | Identify physical resource ceilings |

Metric names in the table are **reference groups/indicators**, not necessarily exact JMX paths across every distribution; confirm against your exporter/JMX tree. Server histograms and application latency measure different spans, so numbers can differ substantially.

## 7. Java Example: Bounding In-Flight Mutations

Java Driver 4.x provides async APIs; calling `executeAsync` in an unbounded loop can swamp connection pools and servers. The pattern below uses a `Semaphore` to **block the producer once 32 requests are awaiting completion**.

Java 17+ snippet assuming an initialized `CqlSession session`, `events` list, and proper CL environment. This illustrates an ingestion policy, not a standalone application:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.Semaphore;

record WriteEvent(UUID tenantId, LocalDate dayBucket, UUID eventId,
                  Instant occurredAt, String payload) {}

static void writeBounded(CqlSession session, List<WriteEvent> events)
        throws InterruptedException {
    PreparedStatement ps = session.prepare(
        "INSERT INTO write_overload_lab.events_by_tenant_day " +
        "(tenant_id, day_bucket, event_id, occurred_at, payload) " +
        "VALUES (?, ?, ?, ?, ?)");

    int maxInFlight = 32; // Test limit only; benchmark to choose real value.
    Semaphore permits = new Semaphore(maxInFlight);
    ConcurrentLinkedQueue<Throwable> errors = new ConcurrentLinkedQueue<>();

    for (WriteEvent e : events) {
        permits.acquire(); // Wait for a slot rather than flooding the driver.
        try {
            BoundStatement statement = ps.bind(
                    e.tenantId(), e.dayBucket(), e.eventId(),
                    e.occurredAt(), e.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.executeAsync(statement).whenComplete((result, error) -> {
                try {
                    if (error != null) errors.add(error);
                    // Record application latency/error metrics here.
                } finally {
                    permits.release();
                }
            });
        } catch (RuntimeException submissionError) {
            permits.release();
            throw submissionError;
        }
    }

    // Valid only when this method is the sole producer using permits above.
    permits.acquire(maxInFlight);
    permits.release(maxInFlight);
    if (!errors.isEmpty()) {
        throw new IllegalStateException(
            errors.size() + " mutations were not acknowledged");
    }
}
~~~

**Explanation and limitations of the example:**

- A semaphore enforces an **in-flight limit**; capping QPS below a rate additionally requires a **rate limiter/token bucket** at the producer. The two mechanisms control two distinct quantities.
- `setIdempotent(true)` here assumes inserting the same **primary key and immutable payload** aligns with business semantics. It does not make every CQL statement idempotent: `UPDATE counter`, dynamic timestamps/TTLs, conditional updates, and external side effects require separate evaluation.
- The code uses `LOCAL_QUORUM`: it assumes valid RF and DC naming and a properly configured local datacenter on the driver. Never lower CL to "fix" overload without aligning on product consistency needs.
- In production, track latency, classify exceptions, and combine deadlines, jittered retry budgets, HTTP/Kafka flow control, and cancellation/resource management. Never buffer unbounded requests in RAM while downstream is overloaded.
- Log errors as "unacknowledged" rather than "unwritten," since mutations may have been applied even when the client times out.

At large scale, rather than loading millions of events into a giant `List`, stream/poll with pause/resume; prefer **backpressure at the source** so application memory queues do not become the next point of failure.

## 8. Timeout Does Not Mean Rollback: Retries and Business Correctness

Consider RF = 3 where `LOCAL_QUORUM` needs two replica responses. A mutation may have been applied by one or more replicas while the coordinator failed to collect enough replies in time. The client sees `WriteTimeoutException`; this **does not prove the mutation was not written**. Re-sending the exact request can:

- Be acceptable for **idempotent** mutations with identical key/values and appropriate timestamp/TTL strategies.
- Double-count **counter increments**, corrupt balances, or repeat side-effecting events when operations lack idempotency keys.
- Cause unintended update ordering when multiple writers issue differing timestamps or write concurrently.
- Add extra load onto an already overloaded cluster, even if the first mutation eventually completed.

### 8.1. Classify Errors Before Acting

| Client outcome | Interpretation | Response direction |
|---|---|---|
| **Success** at requested CL | Received enough CL acknowledgments; fsync durability depends on config | Record success; keep monitoring cost |
| **Write timeout** | Insufficient acknowledgments arrived **before deadline**; write outcome ambiguous | Verify idempotency, apply small retry budget or key reconciliation |
| **Unavailable** | Insufficient live replicas to meet CL before normal execution | Investigate nodes/DC/RF/CL; do not spam retries |
| **Write failure** | Replicas returned errors or storage write failed during processing | Investigate root cause before retrying |
| **Overloaded / rate-limited** | System rejected/throttled due to crossing an execution limit | Slow down source, backoff with jitter, raise capacity alerts |

Java driver exception names and retry mechanics may vary across major versions. Careless retry policies can mask overload and worsen p99; track attempt counts, **successful logical mutations**, and physical requests sent.

### 8.2. Hinted Handoff and Repair Are Not Throughput Tools

When a replica disconnects while CL can still succeed, **hinted handoff** may buffer hints to redeliver mutations within supported windows/configs. Yet hints are not an infinite queue and do not replace **anti-entropy repair**; when hint windows expire or nodes stay down too long, run repair/sync runbooks.

**Repair** resolves replica data divergence; **compaction** merges local SSTables as storage maintenance. Running cluster-wide repair or major compaction during peak overload adds heavy I/O and can worsen outages. Schedule them around actual resources and cluster health.

## 9. Step-by-Step Diagnosis When Write p99 Spikes

### 9.1. Rapid Investigation Workflow

1. **Pinpoint symptoms and timeline:** offered QPS, successful QPS, p50/p95/p99, timeouts, error codes, and start time. Separate client, coordinator, and replica errors.
2. **Check topology:** `nodetool status` from multiple nodes if views differ; inspect down replicas, DC/rack changes, RF/CL, and hot nodes caused by partition keys.
3. **Measure per-node queues:** `nodetool tpstats` across multiple intervals. Watch `MutationStage` (or equivalent stage), `Pending`, and `Blocked`. Compare coordinators vs. replicas to separate network delivery stalls from local write stalls.
4. **Drill into commit log/memtable/compaction:** inspect `WaitingOnCommit`, `PendingFlushes`, compaction backlog, disk latency, free space, and GC. Pinpoint resource-level causes.
5. **Verify version and active throttling:** is 3.11 legacy backpressure active, is 4.1+/5.x native transport limiting enabled, and did clients negotiate `THROW_ON_OVERLOAD`?
6. **Apply controlled source throttling:** lower offered load, cap in-flight requests, halt cascading retries; verify queue recovery and actual effectiveness.
7. **Remediate the proven bottleneck:** e.g., expand disk capacity, split hot partitions, tune compaction per metrics, or rebalance coordinators; then re-test with the same workload to verify.

### 9.2. Diagnostic Matrix

| Observed symptom | Primary hypothesis | Confirming evidence | Initial action |
|---|---|---|---|
| p99 spikes, driver pending rises, Cassandra CPU low | Client/connection pool is the bottleneck or experiencing backpressure | Driver metrics, socket/reads, offered load | Lower source QPS/in-flight; check pool and deadlines |
| `MutationStage.Pending` rises on a few replicas | Specific replicas overloaded, hot partition, or slow node disk | Per-node disk latency, partition distribution, GC | Shed load, inspect partition key / hot keys |
| `CommitLog.WaitingOnCommit` rises, slow disk fsync | Commit log I/O ceiling | OS disk queue/fsync, commitlog metrics | Check disk health/capacity; avoid pushing more load |
| `PendingFlushes` rises, large memtables | Flushes falling behind writes | Memtable/flush metrics, disk throughput | Reduce ingest; inspect flushes/disks |
| Compaction backlog grows after burst | Background work not catching up fast enough | `compactionstats`, SSD utilization, SSTable count | Evaluate compaction throughput in steady-state window |
| `DroppedMessage.MUTATION` rises with timeouts | Messages expiring in queues or network congestion | Dropped delta, coordinator latency, network | Curb retries/QPS; locate slow node or network fault |
| One DC down, `LOCAL_QUORUM` fails | Insufficient local replicas | `nodetool status`, per-DC RF | Recover DC; verify CL feasibility |
| `OverloadedException` spikes after enabling limiter | Ingress exceeds admission policy | QPS per coordinator, config, and client flags | Lower source rate; align routing/limits with capacity |

**What NOT to do impulsively:** bump every thread pool, disable durability/commit logs, retry infinitely, raise timeouts to hide errors, run `nodetool repair` or `compact` everywhere at once, or lower CL without aligning consistency requirements. Those shortcuts trade performance risk for durability or correctness failures.

## 10. Choosing Throttling Aligned with Operational Goals

### 10.1. Prioritize by Layer of Impact

**Layer 1 — application:** cap in-flight requests, smooth bursts when consumers pull from queues, use bounded queues with explicit full-queue policies (wait/429/503/dead-letter per business rules), and stop unnecessary retries. This is the best layer to enforce **business priorities** and controlled admission.

**Layer 2 — driver/coordinator:** check connection pools, request timeouts, overload errors, and routing; enable version-appropriate native transport limiting if benchmarks show clear gains. The goal is preventing overload from flooding executors/replicas without starving priority traffic.

**Layer 3 — storage/cluster:** if disk, flushing, or compaction is the bottleneck, right-size hardware and compaction, verify node/partition/RF counts, and inspect the commit log path. Adding nodes to a cluster does not automatically cool down a single hot partition key, and raising RF increases write amplification.

### 10.2. Acceptance Criteria After Changes

Never evaluate a change solely by a drop in `WRITE TIMEOUT` count; verify:

- Successful logical mutation throughput meets real targets at the chosen CL and durability settings.
- Client p95/p99 stays within SLO, including pre-driver queueing if user-facing.
- Overload/rejection errors are explicit and **bounded**, never turning into unbounded queues.
- Pending/blocked tasks, disk/flush/compaction backlogs do not grow continuously under target load, and recover after bursts.
- Retry counts, duplicate/ambiguous effects, and data consistency are verified.
- Results are repeatable for the given version/config/schema/seed/workload, even with one slow replica or background GC/compaction.

**Hypothetical** lab target example: sustain 500 logical mutations/s at p99 ≤ 150 ms, < 0.1% errors, and backlog recovery within 60 seconds after a burst. These thresholds only teach how to frame SLOs; they are not universal Cassandra operational recommendations.

## 11. Scenario Exercises

**Scenario A — longer queues make things slower.** A client pushes 1,800 requests/s while the cluster completes only 1,200 requests/s on saturated disks. After 20 seconds, how much theoretical backlog accumulates without backpressure/rejection/timeouts? Does doubling the timeout make disks serve faster?

<details>
<summary>Answer hint</summary>

The deficit of 600 requests/s × 20 seconds = **12,000 queued requests** under the simplified model. Raising timeouts does not add disk capacity; it only lets requests wait longer and hold resources longer.
</details>

**Scenario B — version-specific config.** A 3.11 doc suggests trying `back_pressure_enabled`; your cluster runs 5.0. Should you paste that parameter into `cassandra.yaml`?

<details>
<summary>Answer hint</summary>

**No.** Check 5.0 documentation and configuration, as legacy 3.11 keys are not listed in 5.0 configs. To limit native transport in 5.0, evaluate `native_transport_rate_limiting_enabled` and `THROW_ON_OVERLOAD` driver behavior, test in a lab, and measure both latency and errors.
</details>

**Scenario C — timeout yet data appears.** A Java client gets a write timeout, then queries by key and sees the new value. Is this a contradiction? How should retries be handled?

<details>
<summary>Answer hint</summary>

No contradiction: a timeout means insufficient acknowledgments arrived before the deadline, while the mutation may still have been applied. Design mutations idempotently around stable keys, classify errors, reconcile when needed, and bound retries with backoff/jitter and a strict budget.
</details>

**Scenario D — lowering latency by lowering CL.** An RF = 3 cluster writes at `LOCAL_QUORUM`; one slow replica pushes p99 up. Is switching to `ONE` a sufficient fix?

<details>
<summary>Answer hint</summary>

Changing CL changes **acknowledgment semantics** and may shorten wait times for some calls, yet it does not fix the slow replica/disk and may violate consistency requirements. Identify the root cause, capacity, and data SLA before negotiating CL changes with product owners.
</details>

### Lab Completion Checklist

- [ ] Verified Cassandra version, topology, RF/CL, and commit log settings.
- [ ] Identified every point where work can queue from Java client to flush/compaction.
- [ ] Compared `Pending`, `Dropped`, and p99 across load windows instead of relying on one snapshot.
- [ ] Distinguished 4.1+/5.x native transport rate limiting from 3.11 legacy backpressure.
- [ ] Tested bounding in-flight work and/or source QPS and measured queue recovery speed.
- [ ] Explained write timeouts as ambiguous outcomes and implemented idempotent retry handling.
- [ ] Based decisions on SLOs, successful throughput, disk health, and data durability requirements.

## 12. References

1. Apache Cassandra — [Storage Engine: commit log, memtables, flush, and durability](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html).
2. Apache Cassandra — [Monitoring: ClientRequest, ThreadPool, CommitLog, DroppedMessage, Compaction, and Table metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html).
3. Apache Cassandra — [Use Nodetool: status, tpstats, compactionstats](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html).
4. Apache Cassandra — [Cassandra 3.11 cassandra.yaml](https://cassandra.apache.org/doc/3.11/cassandra/configuration/cass_yaml_file.html) and [4.0 cassandra.yaml](https://cassandra.apache.org/doc/4.0/cassandra/configuration/cass_yaml_file.html).
5. Apache Cassandra — [Cassandra 4.1 cassandra.yaml](https://cassandra.apache.org/doc/4.1/cassandra/configuration/cass_yaml_file.html), [5.0 cassandra.yaml](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html), and [Native protocol: THROW_ON_OVERLOAD](https://cassandra.apache.org/doc/stable/cassandra/reference/native-protocol.html).
