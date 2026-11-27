# Coordinator Load, Replica Load, and Request Distribution Across Nodes

## Objectives and Scope

Apache Cassandra is a distributed **wide-column** database. A single CQL request can pass through a **coordinator** and be handled by multiple **replicas** based on partition key, replication factor, and consistency level. Therefore, when a node exhibits high CPU, long queues, or rising p99, the first question is not merely "how many connections does this node receive?"—it is: **how many requests is it coordinating, how much data is it serving as a replica, and why are requests routed to it?**

This lesson belongs to the **Resource Tuning** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. We connect token rings, partition keys, query-driven table design, replication, read/write consistency levels, compaction, repair, error diagnosis, and Cassandra Java Driver 4.x.

After learning this lesson, you can:

1. Distinguish resource usage when a node acts as **coordinator** versus when it acts as **replica**, including when one node plays both roles on the same request.
2. Explain **token-aware routing**, local datacenter, driver load balancing, routing keys, and the impact of speculative execution/retries.
3. Spot two kinds of imbalance: **coordinator hotness** from client routing and **replica hotness** from hot partitions or token ranges.
4. Predict required responses for `ONE`, `LOCAL_QUORUM`, and `ALL` without confusing ACK count with how many replicas may receive a mutation.
5. Design measurements spanning latency, request rates, CPU, network, thread pools, compaction, tombstones, and key distributions.
6. Practice CQL and Java to compare evenly distributed traffic against traffic concentrated on one partition, then tune under control.

> **Operational Scope:** data-generation and load-testing examples are strictly for lab/staging. Never push heavy load onto a production cluster to "test balancing", and never change replication factor or compaction strategy before gathering bottleneck evidence.

## 1. Two Different Roles Inside the Same Node

The **coordinator** is the node receiving a client request, identifying relevant replicas, sending requests to those replicas, waiting for enough responses per consistency level, reconciling results, and returning the response to the client. A **replica** is a node chosen by placement to hold a partition's data and execute reads/writes against local storage.

One node can simultaneously act as coordinator **and** one of the replicas for the queried partition. Conversely, a coordinator does not necessarily hold a replica of that partition; in that case, it must forward requests to nodes that hold the data.

~~~mermaid
flowchart LR
    J["Java client"] --> C["Coordinator C"]
    C --> R1["Replica R1"]
    C --> R2["Replica R2"]
    C --> R3["Replica R3"]
    R1 --> C
    R2 --> C
    R3 --> C
    C --> J
~~~

### Where Is Load Generated?

| Work Item | What the Coordinator Usually Bears | What a Replica Usually Bears |
| --- | --- | --- |
| Client connections / CQL protocol | Accepting, decoding requests, and sending responses | May handle other requests when coordinating for other clients |
| Routing math, endpoint selection | Resolving replicas from metadata/token | Does not independently pick all endpoints for the served request |
| Writing mutations | Distributing mutations, managing ACKs, timeouts/hints as needed | Writing commit log, updating memtable, flushing SSTables |
| Reading | Sending data/digest requests, reconciling results, optional read repair | Reading memtable/SSTables, filtering clustering slices, applying TTL/tombstones |
| Data maintenance | May coordinate other administrative activities | Compaction, flushes, repair/streaming, local disk I/O |
| Returning large payloads | Serialization/protocol/network egress to client | Reading and sending data/digests to coordinator |

**Diagnostic takeaway:** if C receives many client requests while holding little local data for those partitions, C may bottleneck on coordinator/network duties. If R2 owns heavily accessed partitions, R2 can overload **even without coordinating most requests**.

Avoid assuming "high CPU on a node means clients must be connected directly to it". High CPU can also stem from replica reads, compaction, repair, flushes, streaming, GC, or other background work.

## 2. Partition Key Determines Replicas; the Driver Picks the Coordinator

Cassandra uses the **partition key** to compute a token. Replication strategy, token ownership, datacenter, and rack determine the partition's **natural replica set**; that comes from cluster metadata/placement. The driver picks which node acts as **coordinator** for a request; the two choices are related yet **not identical**.

Suppose four nodes share one datacenter with RF=3:

~~~text
Partition P1 -> replicas: N1, N2, N3
Partition P2 -> replicas: N2, N3, N4
Partition P3 -> replicas: N1, N3, N4

Every request for P1 requires reading/writing on P1's replica set,
yet the coordinator may be N1, N2, N3, or another node depending on routing.
~~~

**Token-aware routing** is how the driver prefers a coordinator belonging to the partition's replica set (typically preferring replicas in the **local DC** when configured properly). This can eliminate an extra network hop and spread coordination across data-owning nodes. However, it **does not change P1's replica set** and **does not automatically spread P1 across every node** when P1 becomes a hot partition.

~~~mermaid
flowchart TD
    A["CQL + partition key values"] --> B{"Can driver resolve routing key?"}
    B -->|Yes| C["Fetch token-aware replica list"]
    C --> D["Prefer healthy replicas in local DC"]
    B -->|No| E["Pick coordinator via policy/fallback"]
    D --> F["Coordinator orchestrates read/write"]
    E --> F
    F --> G["Replicas execute per placement + CL"]
~~~

### Prerequisites for Token-Aware Routing to Help

- The driver holds up-to-date topology metadata and schema so it can extract the statement's **routing key**.
- The query provides all **partition key** components and uses a statement/binding the driver understands for routing—typically a **prepared statement** with `?` markers in the right positions.
- `CqlSession` configures the right **local datacenter**, and the load-balancing policy is not mis-customized.
- Replica nodes are healthy; when preferred replicas are down or unreachable, the driver falls back to another coordinator per policy.

You cannot conclude the driver "is token-aware" merely because a `SELECT` returns fast. Inspect **which coordinator is chosen per request** and correlate against partition routing, node status, topology, and metrics.

**Subtle point:** token-aware routing **spreads coordinator work** and avoids hops, yet if 90% of traffic hits one partition, that partition's replica group still handles massive load. Fixing a replica hotspot usually requires **redesigning keys/query patterns or sharding hot data**, not just tweaking connection pools.

## 3. How Much Work Does a Consistency Level Create?

With a `NetworkTopologyStrategy` keyspace at **RF=3 in one datacenter**, minimum responses required to complete:

| Consistency Level | Read Requires | Write Requires | Notes |
| --- | ---: | ---: | --- |
| `ONE`/`LOCAL_ONE` | 1 replica (local for `LOCAL_ONE`) | 1 ACK (local for `LOCAL_ONE`) | May return data not yet updated on other replicas |
| `LOCAL_QUORUM` | 2 replicas in local DC | 2 ACKs in local DC | Multiple replicas must respond; may involve digest checks/read repair |
| `ALL` | 3 replicas | 3 ACKs | Highly sensitive to one slow or down replica |

**ACKs waited for do not equal mutations sent.** Cassandra's write path normally dispatches mutations to all placement replicas even when the CL waits for only one or two ACKs; down nodes may catch up later via hinted handoff/repair under applicable conditions. Never interpret `ONE` as "only a single replica receives the data".

For `LOCAL_QUORUM` reads, the coordinator may fetch one full-data response plus a digest from another replica, then perform an **extra full read / read repair** on mismatch. Hence read load depends on **CL, data size, replica divergence, and node health**, not just raw `SELECT` counts.

### Estimation Model, Not Actual Measurement

If a hot partition is read `Q` times/sec at RF3, `LOCAL_QUORUM` requires at least two replicas to respond per successful read; total replica-side work can be roughly **2Q or higher** due to digests, retries, speculative execution, and repair. Work across the three replicas is not necessarily split an exact 1/3 each.

For writes, a mutation may be sent to **more replicas than the ACK count required**. Thus, dropping write CL from `LOCAL_QUORUM` to `ONE` does not automatically cut write I/O by a third or eliminate compaction pressure.

### Across Multiple Datacenters

`LOCAL_QUORUM` is evaluated inside the **coordinator's datacenter**, e.g., 2/3 in `dc_a`; a remote ACK from `dc_b` cannot substitute for a missing local ACK. Remote replication still runs, generating network and I/O beyond what the client waits for. If a driver running in region B routes to a coordinator in A, requests incur extra WAN RTT and add unintended coordinator load in A.

**Never lower CL to cure high CPU** when the business requires read-your-writes or defined freshness; changing CL alters consistency and availability guarantees.

## 4. Two Forms of Hotness: Coordinator Hotspot vs. Replica Hotspot

### 4.1. Coordinator Hotspot

One node receives far more client connections or requests than peers. Common causes:

- Client configured only **one contact address** and policy fails to spread load properly.
- Outdated driver / wrong local DC; custom load balancing funnels most traffic through one coordinator.
- Application continuously opens new `CqlSession` instances, causing handshake/auth/pool churn.
- Requests lack routing keys, triggering frequent coordinator → replica forwarding hops.
- Overly aggressive retries/speculative execution flood certain nodes when the system is already overloaded.

Signals to inspect are **coordinator request counts, connections, in-flight requests, CPU/GC, client-facing network traffic, and latency**—not just disk usage.

### 4.2. Replica Hotspot

Certain ultra-hot partitions always land on a fixed replica set. Causes:

- Partition key uses a constant like `tenant_id='global'` or one giant tenant dominates traffic.
- One customer/device emits massive events into the same time bucket.
- Oversized partitions, heavy tombstones, or reads touching many SSTables.
- One replica is running compaction/repair/streaming, inflating latency for the same traffic.
- Replica placement or node count cannot meet real load; vnodes/token ownership is balanced by **bytes**, not **heat**.

A node can **barely act as coordinator yet show very high CPU/disk** from reading/writing the hot partitions it owns. Adding contact points or round-robining across coordinators **does not reduce the data that replica is forced to process**.

### 4.3. Distinguishing with Evidence

| Observation | First Suspect | Additional Data Needed |
| --- | --- | --- |
| C1 gets most CQL requests, yet other replicas' CPU also rises | Uneven coordinator routing | Driver coordinator histogram, routing keys, network |
| C1 gets few CQL requests yet disk I/O / read latency is very high | Hot replica / compaction / tombstones | Partition histograms, table latency, compaction, SSTables |
| Coordinator requests look even across nodes, yet one node's CPU spikes | Placement / hot partition or background task | Token ranges, per-key traffic, node metrics |
| Cluster-wide latency rises with load, queues grow | Cluster-wide overload or retry amplification | Request rate, in-flight, dropped messages, retry counts |
| Only clients in DC B are slow | WAN / local DC routing mismatch | Coordinator DC, RTT, CL, cross-DC metrics |
| CPU normal yet p99 high | Disk I/O, timeouts, compaction, network, GC pauses | Per-stage/queue latency, I/O, GC, logs |

## 5. Even Token Distribution Does Not Guarantee Even Load

Virtual nodes (*vnodes*) help balance token-range ownership, yet **data size balance does not equal request rate balance**. A hot partition is an atomic unit of placement: its replica set does not expand simply because the cluster adds more nodes.

~~~text
Node   SSTable size     Client coordinator RPS     Replica work/CPU
N1     300 GiB          1,000                      Very high (hot partition)
N2     310 GiB          1,050                      Very high (hot partition)
N3     290 GiB            950                      Very high (hot partition)
N4     305 GiB          1,000                      Lower

=> Disk size and coordinator RPS look nearly balanced,
   yet N1/N2/N3 are the replicas of a very hot partition.
~~~

These are **hypothetical figures** solely for explanation. In real analysis, verify partitions/ranges and background tasks rather than blaming high CPU blindly on one key.

### Sound Mitigations

1. **Adjust query-driven table design:** if commonly reading "the latest 20 events for a customer/day", use a composite partition key containing tenant, customer, and bucket rather than one `global` key.
2. **Time-bucketing:** day/hour buckets matched to ingest rate and partition size. Too coarse creates hot partitions; too fine increases read fan-out.
3. **Intentional sharding:** when one partition remains too hot, add a `shard_no` to the partition key derived from a hash/event ID and cap shard count. Reads must fan out and merge results across shards.
4. **Separate list/detail or large-payload workloads:** shrink bytes read/serialized on hot API paths.
5. **Bound query fan-out:** a single HTTP request must never scan hundreds of partitions unboundedly.
6. **Add nodes / scale capacity** if total load genuinely exceeds cluster capacity and post-expansion placement relieves the bottleneck.

**Never replace a partition key with `ALLOW FILTERING`**, and never shard blindly: adding shards brings multi-partition reads, global ordering challenges, write/reconciliation overhead, and data migration. Schema changes require migrating from old keys to new keys—you cannot alter the primary key of a populated table with a simple `ALTER TABLE`.

## 6. Wide Queries and Large Payloads Overload Coordinators

Even with evenly balanced coordinators, unbounded queries exert disproportionate pressure:

- `SELECT *` on a large partition inflates response bytes and coordinator memory.
- `ALLOW FILTERING` or multi-range scans can drag many replicas into one request.
- Fetching many consecutive pages multiplies round trips; too small a `pageSize` adds round-trip overhead, while too large inflates payloads/heap/GC.
- Tombstone-heavy tables force replicas to scan lots of dead data to return a few live rows; coordinators may wait on read repair or time out.
- Broad `COUNT(*)` queries are no substitute for analytics/OLAP engines.

**Design bounded read paths:** specify partition key, clustering range, max row limit, narrow column projection, page size, and max page count. If the app needs cross-partition aggregations, consider pre-aggregation, analytics pipelines, or dedicated query tables instead of funneling everything through one coordinator.

### Costs to Separate

| Metric | What It Checks |
| --- | --- |
| Client request bytes / response bytes | Projection, payloads, row counts |
| Client request latency p50/p95/p99 | App-observed time, including network/driver |
| Coordinator requests and in-flight | Routing and request-handling bottlenecks |
| Replica read/write latency | Storage path, tombstones, SSTables, compaction |
| Internode and client-facing network | Forwarding hops, replication, multi-DC |
| Retries / speculative executions | Client-driven load amplification when nodes slow |
| Pending tasks / dropped messages | Components falling behind |

One client-side CQL request can trigger multiple internode messages. **Never equate HTTP request count with replica operations** or network packet counts.

## 7. Java Driver 4.x and Coordinator Distribution

Cassandra Java Driver 4.x performs topology-aware load balancing; proper defaults prefer local-DC replicas whenever a routing key can be resolved. Always use **prepared statements**, configure **local datacenter** explicitly, and reuse `CqlSession`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

import java.net.InetSocketAddress;

public final class CassandraConnections {
    public static CqlSession create() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

IP addresses are **lab examples**. Real apps need valid contact points, authentication, TLS, timeouts, DNS/service discovery, and a local DC matching the snitch. Contact points primarily bootstrap **cluster discovery**; they are not a hard whitelist of the only coordinators the driver uses once topology is known.

### Client-Side Choices That Break Balance

| Client-Side Design | Risk | Replace With |
| --- | --- | --- |
| Creating a new `CqlSession` per HTTP request | Handshakes, connection churn, CPU/GC | Long-lived shared session |
| Custom routing layer pinning a single node | Coordinator hotspot | Properly configured driver load-balancing policy |
| Queries missing part of the partition key | Cannot compute token, or invalid/wide scan | Prepared statements with complete keys |
| Fanning out thousands of concurrent queries | In-flight surge, saturates pools/nodes | Bounded concurrency, backpressure |
| Retrying every timeout immediately | Adds load while nodes are slow; writes uncertain | Budgeted retries, idempotency, error classification |
| Overly aggressive speculative execution | Sends duplicate requests, raises total load | Idempotent requests only, measured and conservatively tuned |
| Wrong local DC configured | WAN RTT, coordinator load in wrong region | `withLocalDatacenter` and real coordinator monitoring |

**Retries are not always safe:** on a write timeout, some replicas may have already applied it. For counters, LWTs, or external side effects, careless retries break correctness. Mark a statement idempotent only when justified, and still cap retry rates during overload.

## 8. Lab: RF=3 Across Four Nodes to Observe Work Distribution

### 8.1. Prerequisites

Prepare a **four-node single-datacenter** lab cluster named `datacenter1` with replication factor 3. If your lab DC has another name, update the keyspace creation command. Never run load tests against production tables.

~~~bash
# Run on a lab node with admin access.
nodetool status
~~~

Expect all four nodes `UN` (*Up/Normal*), with no ongoing bootstrap/decommission/major repair. Record version, CPU, RAM, disk, and network specs for context.

### 8.2. Create Keyspace and Partition-Bucketed Table

~~~sql
CREATE KEYSPACE IF NOT EXISTS resource_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS resource_lab.events_by_customer_day (
    tenant_id text,
    customer_id uuid,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((tenant_id, customer_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

In this table:

- `(tenant_id, customer_id, event_day)` is the **composite partition key**. Rows sharing tenant/customer/day share one partition.
- `event_ts` and `event_id` are clustering columns. Descending order supports reading the newest events in a partition.
- Including `event_day` bounds daily partition size, yet **does not guarantee** load balance if one customer logs tens of thousands of events per second on the same day.
- No TTL or `DELETE` is included initially to keep tombstone effects out of the baseline lab.

`IF NOT EXISTS` **will not alter** an existing keyspace/table. Verify lab replication before reasoning about CL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'resource_lab';
~~~

### 8.3. Insert Sample Data and Run Bounded Query

~~~sql
INSERT INTO resource_lab.events_by_customer_day
    (tenant_id, customer_id, event_day, event_ts, event_id,
     event_type, summary)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:30:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAYMENT', 'paid-order-01'
);
~~~

In `cqlsh`, set read consistency for the single-DC lab:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_ts, event_id, event_type, summary
FROM resource_lab.events_by_customer_day
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

The `SELECT` supplies the full partition key and caps results at 20 rows, needing no `ALLOW FILTERING`. A single sample row produces negligible load; observing hotness requires populating substantial data and driving **bounded load from a lab workload generator**—never draw conclusions from one `SELECT`.

### 8.4. Two Controlled Load Phases

To isolate key-distribution impact, hold **total QPS, query shape, page size, CL, payload, and duration** constant:

| Phase | Partition Key Distribution | Prediction |
| --- | --- | --- |
| **A — Distributed** | Many distinct `customer_id + event_day` pairs with equivalent data | Replica work spreads across multiple nodes |
| **B — Concentrated** | One or a few hot `customer_id + event_day` keys | The hot partition's replica set takes high CPU/disk |

Keep concurrency inside lab limits. Start low, step up carefully, and stop if p99, timeouts, pending tasks, or disk I/O cross defined limits. Never run both phases concurrently and compare them, as compaction/caches and resource pressure differ.

**Note:** distinct partitions do not guarantee perfectly uniform splits over short samples. Drivers may pick different coordinators; token placement, racks, caches, and node hiccups also affect results. Use many keys and multiple runs.

## 9. Java Driver: Recording Coordinator and Per-Request Latency

The snippet below illustrates a **bounded read** logging the actual coordinator reported by Java Driver 4.x on successful calls. It does not pin a single IP; the prepared statement includes the full partition key so the driver can apply token-aware routing.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class CoordinatorProbe {
    public record Observation(String coordinator, int rows, long elapsedMicros) {}

    private final CqlSession session;
    private final PreparedStatement read;

    public CoordinatorProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT event_ts, event_id, event_type, summary " +
            "FROM resource_lab.events_by_customer_day " +
            "WHERE tenant_id = ? AND customer_id = ? " +
            "AND event_day = ? LIMIT 20");
    }

    public Observation query(
            String tenantId, UUID customerId, LocalDate eventDay) {
        BoundStatement statement = read.bind(tenantId, customerId, eventDay)
            .setPageSize(20)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);

        long started = System.nanoTime();
        ResultSet result = session.execute(statement);
        ExecutionInfo info = result.getExecutionInfo();
        Node coordinator = info.getCoordinator();

        int rows = 0;
        for (Row row : result) {
            rows++;
            // Decode returned value to measure client-side read overhead.
            row.getString("summary");
        }

        long elapsedMicros = TimeUnit.NANOSECONDS.toMicros(
            System.nanoTime() - started);
        String endpoint = coordinator == null
            ? "unknown"
            : coordinator.getEndPoint().toString();

        System.out.printf(
            "key=%s day=%s coord=%s rows=%d time_us=%d%n",
            customerId, eventDay, endpoint, rows, elapsedMicros);
        return new Observation(endpoint, rows, elapsedMicros);
    }
}
~~~

**How to use for analysis:**

1. Reuse **one `CqlSession`** with the right local DC—never open a new session per loop iteration.
2. Call `query` across many `customerId` values spanning distinct partitions and tally requests per `coordinator`.
3. Call `query` repeatedly on one fixed `customerId` on the same day, then compare coordinator distribution, latency, and **replica** resources.
4. Cross-check with per-node `nodetool`/metrics; **a Java coordinator histogram is not a replica-work chart**.
5. When a statement times out, log a separate **READ_ERROR** rather than counting it as a `0`-row success.

The code above intentionally does **not** build an unbounded load generator. Real tests need rate limiters, in-flight caps, bounded runtime, warm-up control, and avoiding synchronous stdout logging burning CPU. `LIMIT 20` and `pageSize(20)` keep responses tiny, yet high request volume can still overload the cluster.

### Why Coordinator Logs Alone Are Still Not Enough

If `query` routes from different coordinators to the **same hot partition**, its replicas still endure heavy load. Conversely, one coordinator logging many requests might just be serving tiny cheap lookups. Also measure **request cost**: bytes, rows, latency, read repair, timeouts, and replica CPU/I/O.

## 10. Collecting Metrics Per Node and Per Query

### 10.1. Essential Tools

~~~bash
# Run in the lab across relevant nodes, not just one node.
nodetool status
nodetool tpstats
nodetool tablestats resource_lab.events_by_customer_day
nodetool compactionstats
nodetool netstats
~~~

Depending on Cassandra version, inspect latency histograms via `nodetool tablehistograms` or JMX metrics. Metric names, stages, and output formats can change across releases or distributions; document the exact version when building dashboards.

| Source | Metrics to Collect | Why Needed |
| --- | --- | --- |
| Java Driver / application | Request rate per coordinator, retries, speculative executions, in-flight, p95/p99 | Verify coordinator distribution and amplification |
| Cassandra client request metrics | Read/write latency, timeouts, unavailables, failures | Reflect coordination pressure and availability |
| Thread pools / messaging | Pending/active/dropped tasks/messages by group | Spot queues building when nodes lag |
| Table metrics | Read/write latency, SSTables, tombstones, partition sizes | Separate hot data from coordinator bottlenecks |
| OS / container | CPU, RSS/heap, GC pauses, disk IOPS/latency, network | Identify hardware resource bottlenecks |
| Repair / compaction / streaming | Pending compactions, bytes streamed, maintenance activity | Background tasks competing with clients |
| Topology | Node `UN`/`DN`, DC/rack, token ownership | Verify distribution capability and node outages |

**Metric caveat:** `nodetool status` reports `Load`/ownership, yet **does not directly measure per-hot-partition QPS**. `tablestats` aggregates **per table on a node**; it does not tell you whether that node handled a given request as coordinator or replica. Conclusions require **correlating multiple sources** (driver, sampled tracing, JMX, logs, CPU/disk, and per-key traffic).

### 10.2. Using Tracing Judiciously

In `cqlsh`:

~~~text
TRACING ON
~~~

~~~sql
SELECT event_ts, event_id, event_type, summary
FROM resource_lab.events_by_customer_day
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Traces reveal the coordinator, contacted replicas, data/digest requests, which step was slow, and whether extra reads/read repairs ran. **Never enable tracing on 100% of production traffic** just to count coordinators; tracing adds overhead and system-table writes. When collecting a `trace ID`, link it with timestamp, request ID, anonymized partition key, and matching metrics.

## 11. Evidence-Based Optimization Process

### Step 1 — State a Testable Hypothesis

For example:

> "P99 is high because all Java clients hit one unsuitable coordinator, adding extra hops,"

or:

> "P99 is high because one ultra-hot customer overloads that partition's three replicas, even though coordinators are evenly balanced."

These two hypotheses require **different remediations**. Never change routing, RF, page size, compaction, heap, and partition keys simultaneously, or you will not know which change worked.

### Step 2 — Capture Baseline Under Representative Load

Hold constant:

- Query shape and read/write ratio;
- RF, CL, live node count, and DC names;
- Partition key set and hotness skew, payload/row size;
- Page size, retry/speculative policies, concurrent requests;
- Major compaction/repair/streaming jobs that could distort the window.

Capture at least p50/p95/p99, error rate, in-flight counts, per-coordinator request counts, CPU/I/O, and heavily loaded replica nodes.

### Step 3 — Pick the Right Lever

| Evidenced Bottleneck | Try First | Avoid Doing |
| --- | --- | --- |
| Coordinator skew, bad driver routing | Fix local DC, policy, routing keys, contact points; reuse session | Changing PK/RF unnecessarily |
| Hot replica from one partition | Bucket/shard for read patterns, redesign table | Only adding coordinators |
| Too many rows/bytes | Narrow projection, clustering range, LIMIT/page size | Lowering CL to hide payload size |
| Surging retries/speculation | Cap retries and speculation; control in-flight | Opening more requests while nodes are overloaded |
| Compaction/tombstones/disk I/O | Analyze TTLs, schema, compaction, and repair schedules | Blindly inflating thread pools |
| Whole cluster over capacity | Add planned capacity, benchmark new placement | Assuming adding nodes fixes a hot partition |
| Cross-DC latency | Route app to local DC, verify RF/CL | Picking remote coordinators without assessing WAN/RPO |

### Step 4 — Canary and Compare

Roll out first in lab or a small controlled traffic slice while preserving the same consistency target. Compare over the same load window and include **failed requests** in stats. If throughput rises while timeouts/p99 worsen, it is not a successful optimization.

### Step 5 — Rollback Plan

Routing policy or timeout fixes revert relatively fast, whereas **changing a partition key or adding shards is a data migration**—not reversible with one CQL statement. You need controlled dual-write/read migration, verification markers, and idempotent handling. When adding nodes or changing topology, monitor streaming/repair and disk space.

## 12. Misconceptions That Lead to Bad Fixes

| Misconception | Accurate Understanding |
| --- | --- |
| "Cassandra is distributed, so every node automatically receives equal requests." | Depends on driver policy, coordinator choice, partition popularity, and replica placement. |
| "Adding more contact points spreads a hot partition across all nodes." | Contact points aid discovery/connecting; a hot partition still lives on its replica set. |
| "High CPU on a node definitely means it coordinates the most traffic." | It may be serving replica reads, compaction, repair, flushes, or GC. |
| "`ONE` writes only one copy, so it is exactly one-third the load of RF3." | Writes usually dispatch to all replicas; CL sets how many ACKs to wait for, not stored copy count. |
| "`LOCAL_QUORUM` in DC A can use a remote ACK from DC B to reach two." | Local quorum counts only replicas inside the coordinator's DC. |
| "Setting a tiny page size always cuts latency." | Can multiply fetch round trips and total RTT when reading multiple pages. |
| "Adding nodes always fixes a hot key." | A hot partition's replica set stays bounded and concentrated; consider key splitting/capacity. |
| "Even `nodetool status` Load means even CPU/QPS." | Load mainly reflects stored bytes/ownership, not hot-traffic distribution. |
| "Timeout means the query did not run on any replica." | Writes may have applied partially; read timeouts do not prove missing rows. |
| "Fast `SELECT *` in the lab proves production will be fast too." | Payloads, tombstones, concurrency, caching, and networking differ in production. |

## 13. Practical Exercises

**Exercise 1 — Separating Roles.** One node receives 15% of CQL requests from the driver yet runs at 95% CPU, while another receives 35% of requests at only 35% CPU. List at least five hypotheses and the metrics needed to distinguish coordinator load, replica hotspot, compaction, and GC.

**Exercise 2 — CL Does Not Set Stored Replicas.** With RF3 in one DC, compute required ACKs/responding replicas for `LOCAL_ONE`, `LOCAL_QUORUM`, and `ALL`. Explain why a successful `ONE` write does not mean other replicas skipped receiving the mutation.

**Exercise 3 — Token-Aware Routing.** Create a prepared statement with complete `(tenant_id, customer_id, event_day)` and log `ExecutionInfo.getCoordinator()` across many different keys. If coordinators look uneven, how do you check policy, node state, local DC, and replica sets before blaming broken routing?

**Exercise 4 — Hot Partition.** One tenant has a device sending 10,000 events/sec into partition `(tenant_id, device_id, day)`. Propose hourly bucketing or bounded sharding, detailing how the "latest 100 events" query changes and how results from multiple partitions are merged.

**Exercise 5 — Measuring Skew.** Phase A uses 1,000 customer keys and Phase B uses one customer key at identical total QPS. Describe how to compare per-node CPU, coordinator counts, replica/table latency, and p99 to catch a replica hotspot instead of looking only at request counts.

**Exercise 6 — Retry Storm.** One node slows down while the Java Driver retries and speculatively executes too aggressively. Explain the feedback loop driving up p99 and propose rate limits, retry budgets, backpressure, and criteria for marking statements idempotent.

**Exercise 7 — Multi-DC.** Clients run in `dc_b` while `CqlSession` sets local DC to `dc_a`. What happens to coordinator routing, WAN latency, and `LOCAL_QUORUM` semantics? If failing over to `dc_b`, what must you verify about remote data before admitting writes?

**Exercise 8 — Production Planning.** Pick a concrete bottleneck scenario and define baseline, hypothesis, one canary change, PASS/FAIL criteria, rollback, and change report. Never use full-table `COUNT(*)` or `ALLOW FILTERING` to build wide-scan "benchmarks".

## Takeaway

**The coordinator orchestrates the request; replicas process data for their assigned partitions.** Token-aware routing balances coordinators and avoids extra hops, yet never spreads a hot partition outside its replica set. To tune Cassandra resources effectively, measure **both per-coordinator traffic and per-replica load**, correlating partition keys, RF/CL, page sizes, retries/speculation, compaction, and topology. Fix the real cause via query-driven table design, proper local-DC routing, bounded fan-out, and controlled benchmarking—never alter consistency or scale nodes blindly.
