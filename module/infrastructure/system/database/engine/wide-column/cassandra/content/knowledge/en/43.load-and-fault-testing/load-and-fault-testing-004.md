# p50/p95/p99 Latency, Throughput, and Resource Usage in Apache Cassandra Load Testing

## 1. Goals and Context

Apache Cassandra is a distributed **wide-column** database: applications access data through partition keys, tokens, coordinators, replicas, and **consistency levels (CL)**. A CQL query can be dominated by coordinator CPU/GC, inter-datacenter networking, replica disk I/O, SSTable/tombstone counts, compaction, repair, and Java Driver request handling.

In the **Load and Distributed Fault Testing** chapter of the **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA** module, this lesson answers: **"How much work can the system process, how long does the tail of the distribution take, and how many resources are consumed to achieve that result?"**

After this lesson, learners will be able to:

1. Define and interpret **p50, p95, and p99** latency instead of looking solely at averages.
2. Distinguish **offered load, completed throughput, successful throughput, attempts, and logical operations**.
3. Understand the relationship among **arrival rate, service rate, concurrency, queuing, and resources**.
4. Explain **coordinated omission**, response-time histograms, warm-up windows, and cache bias.
5. Build a load-testing plan with realistic query patterns: read/write/mixed workloads, partition keys, RF/CL, and token distributions.
6. Measure and correlate **client/driver latency** with coordinator/replica metrics, disk I/O, CPU, GC, network, compaction, and storage.
7. Analyze the effects of **hot partitions, wide partitions, tombstones, page sizes, LWTs, repair, and node outages**.
8. Define **pass/fail criteria** aligned with SLOs and recommend load limits with headroom.
9. Write Java Driver 4.x instrumentation and understand histograms and Prometheus usage.
10. Apply troubleshooting runbooks when p99 spikes, throughput drops, or resources saturate.

**Scope:** Numbers in this lesson are **illustrative examples for calculations and experiment design**, not official Cassandra benchmarks. There is no single "Cassandra achieves X QPS" number valid across all schemas, hardware, RF, CL, and workloads. Load-generation commands must be run **only on authorized lab/staging clusters**, never on production or systems holding irreplaceable data.

## 2. Where Does a Request Travel?

~~~mermaid
flowchart LR
    A["Client / Load generator"] --> B["Java Driver pool"]
    B --> C["Coordinator"]
    C --> D["Replica 1"]
    C --> E["Replica 2"]
    C --> F["Replica 3"]
    D --> C
    E --> C
    F --> C
    C --> B
    B --> A
    G["Compaction / repair / streaming"] -. "I/O + CPU" .-> D
    G -. "I/O + CPU" .-> E
    G -. "I/O + CPU" .-> F
~~~

The latency observed by the **caller** can include:

- Waiting in the gateway/API service and admission control.
- Waiting for a driver connection or in-flight capacity.
- Sending the request over the network to the coordinator.
- Coordinator selecting replicas and executing the read/write per CL.
- Replicas reading memtables/SSTables, handling tombstones, commit logs, caches, or compaction contention.
- Replicas returning responses; coordinator completing and responding to the driver.
- Driver decoding/mapping and the application building the response.

When measuring only part of this path, **explicitly name the boundary**. For instance, `driver.executeAsync` latency excludes time an HTTP request queued before calling the driver; server-side read latency excludes Java object mapping in the API.

### 2.1. Four Time Layers to Separate

| Time Layer | Measured From → To | Who Uses This Metric |
|---|---|---|
| **End-to-end API latency** | Caller sends request → response/stream completes | Product SLO, end users |
| **Java/Driver request latency** | Statement submission → client success/error | Application / DB teams |
| **Coordinator operation latency** | Coordinator processes request per server metrics | Cassandra operators |
| **Replica/storage/queue latency** | Read/write/flush/commitlog/compaction on each node | Bottleneck isolation |

**Never add per-layer p99 values directly** to infer end-to-end p99: each layer's percentile can come from **different requests**, and layers overlap concurrently. Use distributed tracing or per-layer histograms for detailed breakdowns.

## 3. What Are p50, p95, and p99 Latencies?

### 3.1. Definitions

A **percentile** is a threshold on a value distribution:

- **p50:** roughly 50% of samples have latency **less than or equal to** this value.
- **p95:** roughly 95% of samples are at or below this value; the remaining 5% can be slower.
- **p99:** roughly 99% of samples are at or below this value; the remaining 1% can be slower.
- **p99.9:** captures a deeper tail; requires larger sample counts to stabilize.

Percentiles depend on the **computation method**: nearest-rank, interpolation, histogram bucket approximation, or t-digest/HDR histogram. Different tools produce close but not identical figures, especially with small samples. Document the method and measurement window.

### 3.2. Illustrative Distribution of 1,000 Requests

Suppose response times sorted in ascending order are:

| Latency Group | Request Count | Position in 1,000-Item Array |
|---|---:|---|
| 10 ms | 900 | 1–900 |
| 40 ms | 50 | 901–950 |
| 180 ms | 40 | 951–990 |
| 900 ms | 9 | 991–999 |
| 4,000 ms | 1 | 1,000 |

Using **nearest-rank** (1-indexed position `ceil(p × N)`):

- p50 = position 500 → **10 ms**.
- p95 = position 950 → **40 ms**.
- p99 = position 990 → **180 ms**.
- p99.9 = position 999 → **900 ms**.
- Max = **4,000 ms**.

The mean in this example is:

\[
\overline{t}=\frac{900(10)+50(40)+40(180)+9(900)+1(4000)}{1000}=30.3\text{ ms}.
\]

**A 30.3 ms average may look good**, yet 10 out of 1,000 requests take 900 ms or longer. For a service calling Cassandra multiple times per request path, tail latency impact surfaces quickly in API p99.

### 3.3. Percentiles Are Not Success Rates

A system with p99 = 80 ms **on successful requests** alongside an 8% timeout rate can be worse than a system with p99 = 150 ms and 0.01% errors.

When reporting p99, always state:

- Is it computed over **all attempts or successes only**?
- Are timed-out requests included in the histogram or tracked in a separate counter?
- How many requests and over what time window?
- Was it measured at the client, API, or coordinator?
- Is it measured per **logical request**, per **driver attempt**, or per **page**?
- Were warm-up or failover windows excluded, and why?

**Never claim "p99 meets SLO" solely from a success histogram while error rates are climbing.**

### 3.4. Measurement Windows and Representativeness

If a window has 50 requests, 1% is **half a request**, so p99 jumps erratically near max. With N=10,000, the 1% tail holds roughly 100 observations—far more stable, though you still must inspect variance, traffic distribution, and failure modes.

Never combine last week's p99 with a one-minute p99 by averaging them. Retain **histograms or raw samples** to aggregate accurately over new windows.

## 4. Good p50, Bad p99: What Is That Telling You?

Consider latency as load rises:

| Offered load (ops/s) | p50 (ms) | p95 (ms) | p99 (ms) |
|---:|---:|---:|---:|
| 500 | 8 | 15 | 24 |
| 1,000 | 9 | 20 | 35 |
| 1,500 | 10 | 40 | 120 |
| 2,000 | 12 | 100 | 600 |
| 2,500 | 15 | 300 | 1,900 |

These numbers are **hypothetical** to illustrate queuing behavior. As a workload approaches saturation, most requests stay fast while a fraction stalls in queues, waits on disk, or hits GC pauses.

Common Cassandra causes include:

- **Hot partitions:** one replica group serves a disproportionate share of queries.
- **Wide partitions / heavy tombstones:** certain keys cost far more to read than others.
- **Disk or compaction:** one node develops tail spikes during flushes or compaction.
- **GC pauses / CPU saturation:** batches of requests stall together.
- **Network retransmissions / cross-DC hops:** a subset of requests takes a slow path.
- **Retries / speculative executions:** tail latency may be masked for some requests while increasing backend load.
- **Driver pool saturation:** requests queue client-side without high server read latency.
- **Unbalanced token distribution or RF/CL:** certain coordinators/replicas are overused.

**A rising p99 is a trigger to investigate, not a root cause.** To isolate the cause, correlate timestamps with per-node latency, pending queues, disk, GC, token/partition distributions, and driver telemetry.

## 5. Histograms and Computing p99 for Dashboards

### 5.1. Why Histograms Beat Storing Only Percentiles

If individual nodes export "p99 = 150 ms" and "p99 = 400 ms", you **cannot average** them to get cluster-wide p99. Request counts, distributions, and overlaps differ.

A histogram stores **sample counts across latency buckets**; bucket counts using identical definitions can be summed across nodes/instances to approximate percentiles over arbitrary windows.

Example cumulative buckets for one query:

| Upper bound | Samples ≤ bound | Meaning |
|---|---:|---|
| 10 ms | 700 | 70% of requests ≤ 10 ms |
| 25 ms | 900 | 90% of requests ≤ 25 ms |
| 50 ms | 950 | 95% of requests ≤ 50 ms |
| 100 ms | 970 | 97% of requests ≤ 100 ms |
| 250 ms | 992 | 99.2% of requests ≤ 250 ms |
| +Inf | 1,000 | Total sample count |

Here, p99 falls inside the **100–250 ms** range, but since histograms only track bucket totals, interpolation error depends on bucket width and interpolation method. Never claim 1 ms p99 precision when the bucket spanning p99 is 150 ms wide.

### 5.2. Illustrative PromQL with Classic Histograms

Suppose an application exports `cassandra_client_request_duration_seconds_bucket` with labels `query_template` and `outcome`:

~~~promql
histogram_quantile(
  0.99,
  sum by (le, query_template) (
    rate(
      cassandra_client_request_duration_seconds_bucket{
        outcome="success"
      }[5m]
    )
  )
)
~~~

Key reminders:

- `_seconds` is in **seconds**, not milliseconds.
- `le` must be preserved when summing classic histograms.
- This gives p99 **of successes**, which must be paired with error/timeout rates.
- Use `rate(...[5m])` on **counter buckets**, never average per-instance exported p99 gauges.
- Metric names and labels are **application-defined examples**—do not assume the driver exports these names out of the box.
- With **Prometheus native histograms**, syntax and aggregation differ; verify against your actual collector/Prometheus version.
- `query_template` IDs have bounded cardinality; **never** use raw CQL, bind values, or partition keys as labels.

### 5.3. Choose Buckets Based on SLOs

If your SLO requires p99 ≤ 200 ms, buckets should be dense enough around **0.1–0.3 s** to distinguish 180 ms from 260 ms. A histogram with only 0.1 s and 1 s buckets cannot measure a 200 ms threshold accurately.

Histograms approximate; raw observations or HDRHistograms aid internal analysis if sampling and retention are sized appropriately. Never log a line for every high-QPS request just to compute percentiles if your logging pipeline cannot sustain it.

### 5.4. Latency SLOs Must Pair with Availability

Example criteria:

- **≥ 99.9%** of logical reads succeed within the window, per business requirements.
- **p99 latency ≤ 200 ms** across successful logical reads.
- **Timeouts ≤ 0.1%** and zero data correctness violations.
- **CPU/disk headroom** sufficient for a node down or traffic burst per capacity plan.

These figures are **example acceptance criteria**, not a guaranteed Cassandra baseline. A system can artificially satisfy p99 by dropping/timing out every slow request; always cap error rates to prevent misleading "metric optimization".

## 6. Throughput: Offered Load Differs from Achieved Throughput

### 6.1. Metrics That Must Be Defined Clearly

| Metric | Unit | Interpretation |
|---|---|---|
| Offered request rate | logical requests/s | Rate the load generator intends to initiate |
| Started attempts | attempts/s | Rate client/driver actually starts |
| Completed throughput | completed requests/s | Includes both successes and finished errors |
| Successful throughput | successful logical ops/s | Operations succeeding per client criteria |
| Failed/timeout rate | errors/s and % | Operations failing to complete properly |
| Read/write requests | operations/s | Must separate reads, writes, LWTs, and batches |
| Rows returned | rows/s | One SELECT can return many rows/pages |
| Bytes in/out | MiB/s or MB/s | Network/serialization volume |
| SSTable read/write bytes | MiB/s | Actual node I/O, distinct from client payload |
| Background throughput | compaction/streaming/repair MiB/s | Load competing with CQL for resources |

**"QPS" is not a single uniform unit of ops/s:** a query reading 1 row differs vastly from one reading 10,000 rows or a range scan touching many SSTables. When comparing benchmarks, document **query mix, rows/query, bytes/query, partition distribution, and CL**.

### 6.2. Offered > Completed: Is a Queue Building Up?

Suppose the load generator targets **3,000 logical requests/s**, and Cassandra completes only **2,300/s**:

~~~text
Offered load:           3000 requests/s
Completed throughput:   2300 requests/s
Difference:              700 requests/s

If arrival rate holds and there is no drop/load shedding,
backlog can grow by roughly 700 requests every second.
~~~

If admission control or shedding is active, that gap need not sit inside Cassandra queues; requests may be rejected upstream. Identify **where requests queue or drop**, rather than just subtracting two numbers.

When raising offered load leaves achieved throughput flat while p99 latency and errors keep rising, you have **reached or passed the knee of the curve**.

### 6.3. Logical Requests Differ from Driver Attempts

One HTTP logical read can trigger multiple attempts via driver retry policies, speculative execution, or application/gateway retries:

~~~text
1000 HTTP logical reads
  - 900 succeed on first attempt
  - 100 require one extra attempt

Logical reads:      1000
Driver attempts:    1100 (illustrative)
Extra backend load: 10% more attempts
~~~

With multi-layer retries, attempt counts can grow much higher. Looking solely at **logical success throughput** can hide retry-driven cluster load in reports.

**For write timeouts, never blindly retry:** mutation outcomes may be uncertain, especially for counters, LWTs, TTLs, or external side effects.

## 7. RF, CL, and Physical Replica Throughput

### 7.1. Writing One Logical Row Causes Multiple Replica Writes

With `NetworkTopologyStrategy`, RF=3 in a single DC, one logical mutation is typically replicated to three replicas per placement rules:

~~~text
Client write: 1 logical mutation
Coordinator: orchestrates request
Replica set: A, B, C

Replicas are updated targeting RF=3.
CL=ONE: may return success upon one matching ACK.
CL=LOCAL_QUORUM: 2/3 quorum ACKs.
CL=ALL: must satisfy conditions across all relevant replicas.
~~~

**CL does not equal the number of replicas ultimately written**, and ACK count does not equal I/O count. Replicas maintain commit logs, memtables, flushes, and compactions; coordinators and networks add overhead. An RF=3 write consumes **multiple times the storage of one logical record** even before compaction, hints, and repairs.

### 7.2. Replica Load Estimates Must State Assumptions

If 2,000 writes/s are replicated at RF=3, target **replica mutation deliveries** are roughly 6,000/s in steady state—**not** a claim that every node receives 6,000/s or that IOPS = 6,000. Token ownership, DC/rack layout, coordinators, batches, compaction, and networking determine true cost.

A rough capacity estimate:

\[
\text{Replica write target rate}
\approx \text{logical writes/s}\times RF.
\]

Also account for:

- Per-node token ownership and key distribution.
- **Per-DC** RF in multi-DC deployments.
- Cross-DC bandwidth, hints, and repairs.
- Bytes/cell, commit-log sync, and compaction/write amplification.
- CL, consistency availability, and fault-tolerance node count.
- p95/p99 latency of the **worst-case node**, not just cluster average.

### 7.3. Different RF/CL Settings Are Different Benchmarks

Never compare "CL=ONE reached 50k ops/s" directly against "LOCAL_QUORUM reached 30k ops/s" and conclude you should just lower CL for speed. CL is a **business consistency and availability requirement**.

Reports should include a configuration table:

| Variable | Example Setting |
|---|---|
| Keyspace RF | `dc1:3`, `dc2:3` (if multi-DC) |
| Read CL | `LOCAL_QUORUM` |
| Write CL | `LOCAL_QUORUM` |
| Serial CL | For LWTs only when used, per design |
| Driver local DC | `dc1` |
| Request timeout | Effective value, citing driver/profile |
| Retry/speculative policy | Name, max attempts, idempotency condition |
| Partition distribution | Uniform, Zipfian, or hotspot profile |
| Read/write ratio | E.g., 80/20 measured on logical requests |
| Payload | Rows/partition, bytes/row, TTL/tombstone mix |

Without documenting these variables, two QPS charts cannot be meaningfully compared.

## 8. Little's Law, Concurrency, and Queuing

### 8.1. Fundamental Relationship

In steady state, for a well-defined system/queue boundary, **Little's Law** states:

\[
L = \lambda W.
\]

Where:

- `L`: average number of items **inside the system**.
- `λ`: steady completion/arrival rate (`requests/s`).
- `W`: **average** time an item spends in the system (`seconds`).

For example, at 2,500 completed requests/s and **mean latency** of 40 ms:

\[
L=2500\times 0.040=100\text{ average in-flight requests}.
\]

**Do not substitute p99 for `W`** in this formula to infer average concurrency; Little's Law relates **mean values**.

### 8.2. Why Higher Concurrency Does Not Guarantee Higher Throughput

At low load, increasing concurrency helps utilize the server. Once CPU, disk, or a hot replica hits saturation, new requests simply wait longer in queues. Then:

- Offered load rises.
- Completed throughput flattens.
- Mean/p95/p99 latency climbs.
- Timeouts, retries, and queue depth grow.
- **Successful** throughput can drop even as attempts/s increase.

That is the saturation curve; measure where it bends sharply (**the knee**), rather than picking the highest throughput seen in a brief burst.

### 8.3. Separating Service Time from Queue Wait

~~~text
End-to-end duration =
    queue wait
  + work/service duration
  + network/client overhead
  + retry/backoff overhead (if any)
~~~

When queue wait dominates latency, raising timeouts simply traps slow requests in queues longer. Real fixes include shedding load, rate limiting, partition rebucketing, optimizing the read path, or scaling capacity at the true bottleneck.

## 9. Load Generation Models: Open-Loop vs. Closed-Loop

### 9.1. Closed-Loop

A worker sends a request, **waits for it to finish**, and then sends the next:

~~~text
worker_1: send -> wait -> response -> send -> wait
worker_2: send -> wait -> response -> send -> wait
...
~~~

Advantage: easy to bound concurrent requests and model fixed worker pools.

Risk: when Cassandra slows down, workers send fewer requests, **automatically lowering offered load**. Benchmarks may report lower throughput and a "not too bad" p99 because they fail to maintain arrival pressure during saturation.

### 9.2. Open-Loop

The generator schedules arrivals at a target rate **without waiting for prior requests to finish**:

~~~text
Scheduled arrivals at:
0 ms, 1 ms, 2 ms, 3 ms, ...

Already-sent requests may still be in flight
while new arrivals continue firing on schedule.
~~~

Advantage: tests the service under a **steady external traffic rate** even as latency climbs, matching many real-world systems.

Risk: without caps/abort guards, in-flight/queue counts explode and can crash the lab cluster. Always enforce **max outstanding requests**, generator memory limits, and stop conditions.

### 9.3. Coordinated Omission

**Coordinated omission** occurs when a harness **fails to record or generate requests that should have arrived** while the system stalled. Example:

~~~text
Target arrival: 1000 requests/s
Server pause: 2 seconds

Closed-loop worker:
  request A stalls for 2 seconds
  fails to emit the many requests due during those 2 seconds
  histogram sees only a handful of slow requests

Real-world users:
  new requests keep arriving, queuing, and timing out
  real user p99 can be far worse than the benchmark histogram.
~~~

How to address it:

- Use generators that track **scheduled arrival timestamps**.
- Record **schedule lag, queue wait, and end-to-end latency**.
- If applying coordinated-omission correction in histograms, document the method and assumptions explicitly.
- Report generator offered vs. achieved rates and missed/delayed arrivals.
- Never compare open-loop and closed-loop figures as directly equivalent.

### 9.4. Match the Method to Production Traffic

- HTTP frontends with independent users → model external arrival rates.
- Batch jobs waiting for replies before the next read → closed-loop can approximate parts of the workload.
- Kafka consumers with backlogs → producer arrival rate and consumer throughput are distinct; queues may accumulate outside Cassandra.
- Scheduled jobs/bursts → test synchronized bursts in addition to steady load.

**Describe your traffic-source model in reports**, rather than just writing "100 threads".

## 10. Preparing a Representative Workload Before Benchmarking

### 10.1. Sample Data Must Resemble Reality

Cassandra performance depends heavily on the **data model and distributions**:

| Workload Variable | What to Describe and Verify |
|---|---|
| Partition key | Full key lookups or token-range scans? |
| Partition width | Rows/partition, bytes/partition, p50/p95/p99 sizes |
| Clustering order | Latest-first, range scans, rows per query |
| Read/write mix | Logical request ratios over time |
| TTL/DELETE | Percentage of expired cells and tombstone density |
| Compaction | Strategy, backlog, SSTables/read, disk headroom |
| Cache | Cold/warm state, key cache, OS page cache |
| RF/CL | Replicas/ACK rules and DC topology |
| Consistency/failure | Node down, slow replica, retries, hints |
| Payload | Bytes/row, collections/UDTs/blobs, serialization |
| Concurrency | Offered RPS, threads, in-flight, per-client connections |
| Hotspot | Uniform vs. Zipfian/skew, hot tenant/device keys |

Testing only `SELECT` on a single cached key does not represent production with millions of partitions and a read/write/TTL mix.

### 10.2. Query-Specific Schema

Example table querying by device and day:

~~~cql
-- Lab with datacenter dc1, enough nodes for RF=3.
CREATE KEYSPACE telemetry_bench
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry_bench.readings_by_device_day (
  device_id uuid,
  event_day date,
  event_time timestamp,
  reading_value double,
  status text,
  PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Read pattern:

~~~cql
SELECT event_time, reading_value, status
FROM telemetry_bench.readings_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 20;
~~~

The `(device_id, event_day)` partition key enables token-aware routing when the driver can infer the key. Yet querying an overly wide or tombstone-heavy partition can still produce high p99.

### 10.3. Test Matrix

| Scenario | Read/Write | Data Distribution | Purpose |
|---|---|---|---|
| Baseline | 100% simple read | Uniform keys | Baseline p50/p95/p99 |
| Read/write mix | 80/20 | Uniform | Observe resource contention |
| Hot keys | 80/20 | Zipfian / hot key set | Detect replica load imbalance |
| Wide partition | Range reads | Wide partitions | SSTables/tombstones/paging cost |
| High TTL | Mixed | TTLs and expired cells | Tombstone/compaction impact |
| Write burst | 10/90 | Many partitions | Commit log, memtable flushes |
| LWT | Conditional | Select hot keys | Paxos contention / tail latency |
| Repair/streaming | Same baseline | Background I/O | Maintenance headroom |
| Failure | Same baseline | One replica/node removed in lab | Latency/error/CL under outage |

Across scenarios, keep **all other settings** fixed or document every change explicitly. Never compare a "cold-cache baseline" with a "warm-cache post-tuning run" and credit the entire difference to tuning.

## 11. Load Generation Tools and Safety Boundaries

### 11.1. `cassandra-stress` Does Not Replace Application Workloads

`cassandra-stress` generates synthetic reads/writes and is useful for exploring baselines. However, its **default schema, key distribution, and request shapes** can differ sharply from your Java API: partition widths, TTL/tombstones, clustering, RF/CL, and payloads.

Example **only on an authorized lab cluster**:

~~~bash
# Common illustrative syntax; check help for your version.
# Never point this generator at production.
cassandra-stress write n=200000 -rate threads=32 -node 127.0.0.1
~~~

The tool creates or writes to its dedicated stress keyspace/table; never accidentally target a keyspace holding real data. Depending on release, auth/TLS, CL, profile, and duration flags vary. **Do not run load tests while authoring this lesson.**

If your goal is measuring `SELECT` throughput by `(device_id, event_day)`, use a custom profile or a Java generator executing **real prepared CQL** with accurate payloads, partition distributions, read/write ratios, and consistency levels.

### 11.2. Mandatory Guardrails Before Generating Load

~~~text
[ ] Confirmed LAB/STAGING cluster, node addresses, and owner.
[ ] Using test data/keyspace and scoped RBAC permissions.
[ ] Start/stop window, operator on watch, and rollback plan ready.
[ ] Snapshots/backups taken if test touches data worth preserving.
[ ] Max offered QPS, max outstanding, and max bytes/s configured.
[ ] Stop thresholds set for p99, errors, disk, heap, and queues.
[ ] Verified ability to stop the generator and drain all requests.
[ ] Telemetry active from generator, Java driver, and all Cassandra nodes.
[ ] Zero fault injection on production.
~~~

**A benchmark is worthless if it causes an outage elsewhere.** Never push load until disk fills up just to see a "max throughput" number.

### 11.3. When Do You Need a Custom Profile?

| Requirement | Why Generic Stress Tools Fall Short |
|---|---|
| App prepared queries and codecs | Default CQL does not match |
| Zipfian / hot-key partition distribution | Uniform keys hide hotspots |
| TTL/tombstones and wide partitions | Read-path cost differs |
| CL/RF and multi-DC routing | Inter-node traffic and ACKs differ |
| Java retries, timeouts, and pooling | Generic tools omit stack behavior |
| End-to-end API p99 | `cassandra-stress` ignores HTTP/business mapping |
| Open-loop arrivals and coordinated omission | Requires knowing the generator's scheduler/mode |

With custom generators, measure **CPU, GC, NIC, and heap of the generator itself**. If the generator saturates before the cluster does, concluding "Cassandra maxes out at X ops/s" is invalid.

## 12. Repeatable Benchmarking Process

### 12.1. Five Phases

~~~mermaid
flowchart LR
    A["Preflight + seed"] --> B["Warm-up"]
    B --> C["Ramp offered load"]
    C --> D["Steady-state windows"]
    D --> E["Cool-down + recovery"]
    E --> F["Report + decision"]
~~~

**Preflight:** record server/driver/JDK versions, node count, instance types, RF/CL, topology, compaction strategy, storage, schema, dataset, read/write mix, generator profile, and timeouts/retries.

**Seed:** load enough data matching real partition/row/TTL profiles. Track disk growth, SSTables, compaction, and network so seeding does not introduce hidden variance.

**Warm-up:** give JIT, connection pools, OS page cache, and key cache time to stabilize. When testing **cold cache**, design a dedicated cold-start run instead of blending warm-up into results.

**Ramp:** step offered load up in bounded increments; hold each step long enough to observe p99/compaction/queue changes without jumping straight to disk saturation.

**Steady-state:** capture multiple measurement windows, confirming backlogs do not climb continuously rather than cherry-picking one flattering snapshot.

**Cool-down:** stop the generator and watch pending queues, compaction backlog, disk/GC, and errors return to baseline. Recovery time itself is a key result.

### 12.2. An Illustrative Schedule — Not a Universal Recommendation

| Phase | Duration | Illustrative Offered Load | What to Observe |
|---|---|---:|---|
| Seed | Dataset-dependent | Bounded writes | Data/disk/compaction |
| Warm-up | 5 minutes | 200 ops/s | Caches/pools/JIT |
| Ramp A | 10 minutes | 500 ops/s | p50/p95/p99 |
| Ramp B | 10 minutes | 1,000 ops/s | Worst-case node |
| Ramp C | 10 minutes | 1,500 ops/s | Queues/retries |
| Ramp D | 10 minutes | 2,000 ops/s | Stop if guardrails breach |
| Recovery | Until stable | 0 test traffic | Pending/disk/errors |

These numbers merely illustrate methodology. Small clusters may need much lower rates, large clusters higher. **Never infer production capacity from illustrative figures.**

### 12.3. How Do You Know It Is Steady?

- Offered and completed rates vary little across multiple windows.
- In-flight counts and queue depths **do not grow over the long term**.
- Compaction/flush/streaming backlogs do not accumulate unexpectedly.
- Error/timeout/retry rates stay stable within budget.
- Disk latency, GC, and CPU are no longer drifting from seeding/startup.
- The generator is not internally queuing or dropping requests beyond max outstanding.
- No unannounced repair, node restart, or batch job is running.

A 30-second benchmark **cannot** confirm a cluster will sustain the same load for hours once write amplification and compaction kick in.

## 13. Measuring Request Latency in Java Driver 4.x

### 13.1. `System.nanoTime()` and Asynchronous Completion

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

public final class DriverLatencyProbe {
    private final CqlSession session;
    private final LongAdder success = new LongAdder();
    private final LongAdder failed = new LongAdder();

    public DriverLatencyProbe(CqlSession session) {
        this.session = session;
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {
        long started = System.nanoTime();

        try {
            CompletionStage<AsyncResultSet> stage =
                session.executeAsync(statement);

            return stage.whenComplete((result, error) -> {
                long elapsed = System.nanoTime() - started;
                observe(elapsed, TimeUnit.NANOSECONDS);

                if (error == null) {
                    success.increment();
                } else {
                    failed.increment();
                    recordError(error);
                }
            });
        } catch (RuntimeException error) {
            observe(System.nanoTime() - started,
                    TimeUnit.NANOSECONDS);
            failed.increment();
            recordError(error);
            throw error;
        }
    }

    private void observe(long value, TimeUnit unit) {
        // Record duration into a Micrometer/HDRHistogram histogram.
        // Never log to stdout per request.
    }

    private void recordError(Throwable error) {
        // Aggregate by bounded error class and query template.
    }
}
~~~

`System.nanoTime()` is a monotonic clock for measuring **elapsed duration within the same JVM process**. Never subtract `System.currentTimeMillis()` or wall clocks across **two different machines** and call it accurate latency without synchronized clocks.

The snippet above measures time until **`executeAsync` completes the first response**, not necessarily consuming **all pages** of a large result. If the app reads 10,000 rows across pages, also track `time_to_last_row` and `bytes_processed`.

### 13.2. Metric Tags and Histograms

With Micrometer:

~~~java
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;

public final class LatencyRecorder {
    private final Timer timer;

    public LatencyRecorder(Timer timer) {
        this.timer = timer;
    }

    public void recordNanos(long nanos) {
        timer.record(nanos, TimeUnit.NANOSECONDS);
    }
}
~~~

Tag timers/histograms with **low-cardinality** dimensions: `query_template`, `operation`, `outcome`, `dc`. Never use `tenant_id`, device UUIDs, raw CQL, routing keys/tokens, or exception messages as metric labels.

Metric/exporter names and bucket configs depend on your Micrometer/Prometheus registry and driver version; **verify the actual setup** rather than assuming the driver automatically emits an example histogram name.

### 13.3. One Logical Call Can Involve Multiple Attempts

The driver may retry or trigger speculative executions depending on policy. Wrapping `executeAsync` from the application **does not reveal** how many coordinators, replicas, or network attempts occurred.

Also collect:

- Driver retry and speculative execution counts where metrics support them.
- `AllNodesFailedException.getAllErrors()` per candidate coordinator on failure.
- Query template, CL, request timeout, and local DC.
- Separate logical success/failure/timeout rates vs. achieved attempts rate.

**Never log full stack traces on the benchmark hot path:** synchronous logging can inflate p99 purely from instrumentation overhead.

## 14. Asynchronous ≠ Unlimited Concurrency

### 14.1. Anti-Pattern: Unbounded Request Dispatch

~~~java
// ANTI-PATTERN: discards futures and ignores outstanding limits.
for (UUID id : millionsOfIds) {
    session.executeAsync(buildStatement(id));
}
~~~

`executeAsync` does not block the caller thread, yet still generates CQL traffic, driver buffers, connection pool pressure, and in-flight requests. If the generator outpaces the server, memory and queues grow rapidly.

### 14.2. Bounded In-Flight Is the Minimum Requirement

A proper load generator must:

1. Enforce **max outstanding** limits sized to generator and cluster.
2. Use an explicit arrival scheduler (open-loop or closed-loop).
3. Record **scheduled, submitted, and completed** timestamps per operation.
4. Record failures, timeouts, and rejections—not only successes.
5. Count extra attempts generated by the app, gateway, or driver.
6. Stop or shed load when hitting error, disk, or GC guardrails.
7. Ensure the generator never saturates before Cassandra.

Example permit guard in **pseudocode**:

~~~java
Semaphore inFlight = new Semaphore(100);

if (!inFlight.tryAcquire()) {
    generatorRejected.increment();
    return; // Record offered-but-not-submitted.
}

long submittedAt = System.nanoTime();

try {
    session.executeAsync(statement)
        .whenComplete((result, error) -> {
            try {
                observeCompletion(
                    submittedAt, System.nanoTime(), error);
            } finally {
                inFlight.release();
            }
        });
} catch (RuntimeException error) {
    inFlight.release();
    observeSubmissionFailure(error);
}
~~~

Identifiers such as `generatorRejected` and `observeCompletion` are hypothetical instrumentation hooks. In an open-loop generator, also store **intended/scheduled arrival timestamps** to detect scheduler lag and coordinated omission.

**Generator rejections are not Cassandra `UnavailableException`s.** Meaningful measurements separate "blocked by the client generator" from "received by Cassandra and failed".

### 14.3. Generators Need Telemetry Too

- Generator CPU, CPU throttling/steal, GC pauses, and heap usage.
- Network Rx/Tx and RTT to contact points.
- Scheduler lag, scheduled rate vs. actual send rate.
- Outstanding requests, local queue length, and client rejections.
- Retry amplification and actual operation mix.
- Client connection count and pool/transport errors.

If p99 spikes while **only the generator** hits 100% CPU and Cassandra nodes remain idle, do not blame Cassandra's replicas or disks.

## 15. Per-Node Resource Checklist

### 15.1. CPU, GC, Heap, and Native Memory

| Resource | What to Observe | Why It Affects Tail Latency |
|---|---|---|
| Per-core CPU % | Busy/core saturation | One coordinator core can saturate while average CPU looks moderate |
| CPU throttling/steal | Cgroup quota / VM contention | Queues and p99 jump abruptly |
| JVM GC pauses | Count, p95/max pause, allocation rate | Groups of requests stall during GC |
| Heap occupancy | Used %, promotion/old gen, allocations | GC pressure and OOM risk |
| Off-heap/native/direct buffers | Resident memory, direct buffers | Process can run out of RAM even with low heap usage |
| OS page cache | Cache hit/miss, eviction | Read path hits physical disk more often |
| File descriptors / connections | Limits and failures | Pool/socket errors |

Never conclude "the cluster has 60% CPU headroom" from a 40% average CPU: **a single hot core or replica** may already be saturated.

### 15.2. Disk and Compaction

| Metric | Why Needed |
|---|---|
| Read/write IOPS | I/O operation rate, sensitive to request size |
| Disk MiB/s | Byte throughput, distinct from IOPS |
| Device await/latency | Read/write tail indicator |
| Queue depth/utilization | Device-level backlog |
| Free disk GB and % | Flushes, compaction, and snapshots need headroom |
| Commitlog fsync latency | Write durability path |
| SSTables per read | Read amplification |
| Compaction pending/bytes/s | Background SSTable rewrites |
| Tombstone warnings | Many expired/deleted cells scanned |

High disk utilization alone does not confirm a bottleneck; examine **latency, queue depth, throughput, node hotness, and compaction** together. HDDs, SSDs, and NVMe drives behave very differently across I/O sizes.

### 15.3. Network and Replica Load

Measure:

- Client↔coordinator Rx/Tx bytes, RTT, retries, and connection failures.
- Coordinator↔replica traffic; cross-DC bandwidth where applicable.
- TCP retransmits, packet loss, and NIC utilization.
- Background hints, streaming, and repair traffic.
- Token ownership, per-node read/write load, and hot partitions.
- TLS/auth overhead during connection churn.

One RF=3 logical write triggers multiple replica deliveries; **client payload bytes ≠ inter-node traffic**. Background tasks can still consume disk and network even after `cassandra-stress` stops.

## 16. `nodetool`, JMX, and Observation Traps

### 16.1. Observation Commands by Cassandra Version

~~~bash
# Node status, DC/rack, and token ownership.
nodetool status

# Active/pending/completed thread-pool stages and dropped messages.
nodetool tpstats

# Running and pending compactions.
nodetool compactionstats

# Table-level storage/read/write/SSTable metrics.
nodetool tablestats telemetry_bench.readings_by_device_day

# Per-table histograms, if supported by your version.
nodetool tablehistograms telemetry_bench readings_by_device_day

# SSTable streaming during bootstrap/repair/rebuild.
nodetool netstats
~~~

Output formats, stage/metric names, and flags in `nodetool` vary across Cassandra versions; verify with `nodetool help` and your JMX exporter mappings. Snapshot commands never replace time-series delta metrics over the benchmark run.

### 16.2. Cumulative Counters Are Not QPS

~~~text
Time    ReadStage Pending   Completed     READ Dropped
10:00                  80      500000                5
10:01                 980      512000               65

Delta Completed/60s = 12000/60 = 200 tasks/s
Pending +900; Dropped +60.
~~~

`Completed` is a **node-local stage task count**, **not** logical HTTP GET/s or cluster-wide SELECT/s. Counters reset on node restarts; never subtract snapshots across a restart.

### 16.3. Empty `netstats` Does Not Prove an Idle Network

`nodetool netstats` primarily reports **SSTable streaming**, not native CQL client requests. To measure CQL/network load, inspect driver metrics, native transport counters, NIC interface bytes/s, and per-node request latencies.

### 16.4. A `UN` Node Can Still Violate p99

`nodetool status` reporting Up/Normal does not guarantee:

- Low disk await.
- Healthy CPU/GC.
- Small pending queues.
- CQL requests meeting CL on time.
- Java clients in other regions can connect.
- Absence of hot partitions or tombstones.

**Availability and performance are two separate dimensions.** Know how many usable replicas exist for your RF/CL and what latency and load those replicas experience.

## 17. Reading Latency, Throughput, and Resources Together

Assuming identical schema, RF/CL, dataset, and load generator; the figures below are **hypothetical**:

| Offered ops/s | Success ops/s | p50 | p95 | p99 | Hottest-Node CPU | Disk Read Await | Error % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 500 | 498 | 8 ms | 15 ms | 24 ms | 25% | 2 ms | 0.0% |
| 1,000 | 995 | 9 ms | 20 ms | 35 ms | 41% | 4 ms | 0.1% |
| 1,500 | 1,490 | 10 ms | 40 ms | 120 ms | 62% | 9 ms | 0.2% |
| 2,000 | 1,920 | 12 ms | 100 ms | 600 ms | 83% | 24 ms | 3.0% |
| 2,500 | 1,870 | 15 ms | 300 ms | 1,900 ms | 92% | 51 ms | 14.0% |

**Explanation:** error % is computed over logical requests completed or timed out within the observation window; the gap between offered and success also includes backlogs, window-boundary in-flight work, generator errors, or rejections, so **never derive it purely by subtracting one column from another**.

If the SLO requires **p99 ≤ 200 ms** and errors ≤ 0.5%, 1,500 offered ops/s passes in this single run. Yet you cannot declare production capacity to be 1,500 without:

- Multiple repeatable runs.
- Sufficiently long steady-state windows after compaction accumulates.
- Testing node failures, repairs, traffic bursts, and headroom.
- Realistic data distributions rather than uniform random keys.
- Verifying client/generator limits alongside server metrics.

### 17.1. The "Knee of the Curve" Matters More Than Peak Throughput

From 2,000 to 2,500 offered ops/s, successful throughput drops in this example while p99 and disk await surge sharply. That signals load has exceeded sustainable capacity.

A sound capacity target sits **below the knee**, leaving headroom for:

- A node down or rolling upgrade.
- Concurrent compaction, repair, and streaming.
- Retries and client bursts pushing attempts/s above logical requests/s.
- Monthly growth in data and tombstone volume.
- Network and GC tail jitter.

**Never pick "max observed QPS" as your production limit** when error budgets and p99 fail to hold.

## 18. Stratifying Results by Query, Partition, and Node

### 18.1. Do Not Lump All Workloads into One p99

Suppose an API runs:

- Query A: single-row lookup by full primary key.
- Query B: latest 20 rows within one partition.
- Query C: multi-page range read.
- Query D: LWT conditional write.

Combining everything into one histogram lets Query A (90% of traffic) mask terrible p99 on Queries C and D.

Stratify by:

| Recommended Label | Purpose | Cardinality Bound |
|---|---|---|
| `query_template` | Compare identical CQL shapes | Fixed template names |
| `operation` | Read, write, LWT, batch | Small fixed set |
| `outcome` | Success/timeout/unavailable/error | Small fixed set |
| `consistency` | `ONE`, `LOCAL_QUORUM`, ... | Small fixed set |
| `datacenter` | Local / remote DC | Small fixed set |
| `client_region` | Identify caller network path | Small fixed set |
| `payload_band` | Small/medium/large | Finite buckets |
| `partition_size_band` | Spot wide partitions | Finite buckets |

**Never put raw primary keys, tenant UUIDs, or tokens in metric labels.** To investigate hot partitions, use permission-scoped, **sampled** tracing/logging; per-key metric labels explode cardinality and leak sensitive data.

### 18.2. Simpson's Paradox and Traffic Mix

Before a deploy, cheap Query A accounted for 90% of traffic; afterward, expensive Query B accounted for 40%. Aggregate cluster p99 can rise from the **mix shift** alone, even if neither query became slower individually.

Always compare:

1. Percentiles for the **same query template**.
2. Mix ratios and payload/rows per query.
3. Partition sizes and token distributions.
4. Offered/achieved rates per class.
5. RF/CL/driver settings and client region.
6. Background compaction/repair activity.

Never call something a "tuning regression" when the workload mix shifted substantially without normalization.

### 18.3. Per-Node Latency Matters in a Distributed Cluster

One node experiencing poor read p99 due to disk/GC or a hotspot affects every request where it acts as coordinator or replica. Looking only at cluster averages hides it:

~~~text
Node A  p99=40 ms,  read QPS=1000
Node B  p99=45 ms,  read QPS=1000
Node C  p99=800 ms, read QPS=4000  <-- hotspot
~~~

This table is hypothetical. Never compute cluster p99 as `(40 + 45 + 800) / 3`; you cannot reconstruct a combined percentile from three p99 numbers even with weights. Merge raw/bucketed per-node histograms properly and inspect **partition/token distributions**.

## 19. Fault Testing: Measuring Behavior When a Replica or Node Fails

### 19.1. Three Comparable Phases

~~~mermaid
flowchart TD
    A["Baseline: all nodes healthy"] --> B["Fault window: one authorized failure in LAB"]
    B --> C["Recovery: restore node/network"]
    C --> D["Compare p99, success, throughput, retries, backlog, data correctness"]
~~~

Run fault injection strictly on an **isolated cluster** with an owner and rollback plan. The goal is not maximizing breakage, but measuring **bounded degradation** and recovery behavior.

During the fault window, collect:

- Offered vs. successful logical ops/s.
- p50/p95/p99 and timeout/error %.
- Driver retry/speculative attempts/s.
- Coordinator/replica CPU/GC/disk/network.
- Pending/dropped messages, hints, compaction/streaming.
- Node statuses, CL, RF, and DC/rack.
- Recovery time from fault removal until SLOs restabilize.

### 19.2. RF=3, CL=`LOCAL_QUORUM` in One DC

Suppose a keyspace has RF=3 in `dc1`. Quorum requires **2 matching responses** for normal operations under CL. When one replica goes down:

- Many requests can still succeed if the two remaining replicas serve them.
- Latency may rise due to reroutes/retries, hotter remaining replicas, or deeper queues.
- If a second replica fails to respond in time, `ReadTimeoutException`, `WriteTimeoutException`, or `UnavailableException` can occur depending on state.
- Hints/repair/recovery generate extra background work once the node returns.

**Never equate "CL tolerates one node down" with "p99 will stay unchanged".** Logical availability and performance headroom are separate requirements.

### 19.3. Multi-DC and Network Partitions

With `NetworkTopologyStrategy` and a local-DC-preferring app:

- `LOCAL_QUORUM` reads/writes depend on the local DC's quorum.
- Cross-DC traffic still occurs via replication, hints, and repairs.
- Losing app→local-DC coordinator connectivity can trigger `AllNodesFailedException` even if another DC is healthy.
- `EACH_QUORUM` applies only to supported operations and requires understanding cross-DC quorum semantics.
- Cross-DC failover requires planning CL, topology, latency budgets, and data correctness.

Cross-DC fault tests belong only in multi-DC lab clusters with controlled network isolation. **Never block inter-datacenter links in production** just to gather p99 samples.

### 19.4. Falling Success p99 During a Fault Is Not Necessarily Good News

Before fault:

~~~text
success rate: 99.9%
success p99: 150 ms
timeout rate: 0.1%
~~~

During fault:

~~~text
success rate: 80%
success p99: 100 ms
timeout rate: 20%
~~~

The p99 of **surviving successes** dropped, yet the service degraded severely because slow requests were chopped off by timeouts. Always place **latency and availability side by side**, never success p99 alone.

### 19.5. Recovery Is More Than `UN`

Once a node returns to UP/NORMAL, continue tracking:

- Pending hints and hint delivery.
- Repair, rebuild, and streaming activity if applicable.
- Compaction backlog and free disk.
- Replica read/write latencies.
- Error/timeout rates and client pool reconnections.
- API SLO p99, not merely Cassandra node status.

**Service recovery time** often extends well past the moment a node flips back to `UN`.

## 20. Setting Pass/Fail and Stop Conditions Before Running

### 20.1. Illustrative Acceptance Criteria

Suppose a system defines the following targets for `latest20_by_device_day`:

| Criterion | Example Acceptance Target | How Measured |
|---|---|---|
| Successful logical reads | ≥ 99.9% | Errors/timeouts over logical requests |
| Success p99 latency | ≤ 200 ms | Client histogram window |
| Sustained offered load | 1,000 requests/s | Open-loop generator schedule |
| Completed success rate | Matches offered, stable | Client outcomes and backlogs |
| p99 under single-node fault | ≤ 400 ms | Intentional lab fault window |
| CPU headroom | No node continuously above internal threshold | Per-node CPU/core |
| Disk p95 read latency | Below device/SLO limit | Per-device |
| Compaction backlog | Not growing unboundedly | Compaction metrics over time |
| Data correctness | No PK/CL/side-effect violations | Read-backs / checksums / invariants |
| Recovery | SLO restored within defined window | API + node metrics |

These thresholds are **hypothetical examples**. Every system must set targets based on its business SLOs, hardware, and capacity budget—never treat these as default Cassandra SLAs.

### 20.2. Stop Conditions

Even in a lab, stop or throttle back load whenever:

- Generator memory or in-flight count breaches its cap.
- Error/timeout rates exceed budget across multiple windows.
- Free disk drops below safe headroom.
- Pending compactions/flushes climb with no sign of recovery.
- CPU throttling, GC pauses, or disk await spike abnormally.
- An unexpected node becomes unreachable outside the fault plan.
- Test data exceeds storage quotas or retention limits.
- The test impacts shared services outside authorized scope.

**Stopping on a guardrail is still a valuable measurement**, not a failure to hide. Report the load level reached and the trigger condition.

### 20.3. Report Sustainable Capacity, Not Just Peak

A statement such as:

> "The cluster sustained 1,500 read ops/s on workload A at RF=3/`LOCAL_QUORUM`, 1 KiB median payload, over a 4-hour sustained test with p99 = 120 ms and error = 0.2%; under single-node failure simulation, p99 = 250 ms and error = 0.3%."

is far more actionable than "Cluster hit 2,000 QPS", because it captures **context, duration, CL, and failure headroom**. These figures remain **a reporting template**, not an actual test outcome.

## 21. Runbook A — p99 Spikes While p50 Barely Moves

**Symptom:** p50 shifts from 9 to 11 ms; p99 jumps from 45 to 600 ms; successful throughput has barely dropped.

1. **Verify scope:** Was p99 measured at client or server, success-only or all outcomes, and did the window have enough samples?
2. **Stratify queries:** Group by `query_template`, CL, payload band, local DC, and read/write mix to find which query or tenant cohort drives the tail.
3. **Inspect arrival rate:** Did offered QPS spike? Did closed-loop generation mask coordinated omission?
4. **Compare per-node metrics:** Disk await, GC pauses, CPU throttling, `tpstats` Pending, and dropped messages.
5. **Inspect data shape:** Hot/wide partitions, tombstones scanned, SSTables per read, indexes/query shapes.
6. **Check background work:** Compaction, repair, bootstrap/streaming, hints, and flushes.
7. **Throttle temporarily:** Rate-limit backfill/jobs if a node nears saturation; avoid aggressive retries.
8. **Re-run controlled tests:** Keep dataset/CL fixed and vary one parameter at a time, comparing p99 + successful throughput + errors + resources.
9. **Close the investigation:** Document root cause/hypothesis, regression tests, thresholds, and rollback steps.

**Avoid concluding** "raising the driver timeout fixes p99". It often just keeps slow requests holding resources longer.

## 22. Runbook B — Throughput Saturates While Queues and Disk Latency Climb

**Symptom:** Offered QPS rises from 1,500 to 2,500, success ops/s barely rises then drops, while `tpstats` Pending and disk await surge.

1. **Locate the real bottleneck:** Device read/write IOPS, throughput, latency, disk queues; also check CPU/GC and network.
2. **Separate logical writes from replica cost:** RF, CL, mutation bytes, commitlog, flushes, and compaction overhead.
3. **Check hot nodes:** Is one replica absorbing disproportionate tokens or hot keys? Cluster averages hide hotspots.
4. **Inspect compaction:** Pending tasks, bytes read/rewritten, SSTable counts, and temporary disk headroom.
5. **Do not blindly raise client concurrency:** It usually deepens queues without lifting successful throughput.
6. **Step offered load down:** Locate the level where queues stabilize and p99 meets SLO; record the knee of the curve.
7. **Evaluate tuning:** Query modeling, time bucketing, TTL/tombstones, page size, compression/compaction strategy, disk capacity, or scaling out.
8. **Validate sustained behavior:** After tuning, run long enough for flushes/compaction to settle and verify cool-down recovery.

**Never trigger ad-hoc major compaction or repairs on production** to "fix a benchmark"; they add heavy I/O and CPU load and require proper SOPs.

## 23. Runbook C — Poor p99 Caused by the Load Generator, Not Cassandra

**Symptom:** Benchmark reports surging p99 while Cassandra CPU/disk stay low and server query latency looks fine; the load generator is at 100% CPU with heavy GC pauses.

1. **Profile the generator:** CPU/core, heap, GC, network, scheduling lag, outstanding requests, and rejections.
2. **Separate timestamps:** Scheduled arrival, submitted, and completed; if submission lags, scheduled latency looks high even when the driver replies quickly.
3. **Audit instrumentation:** Are per-request logs/metrics blocking callbacks, causing lock contention, or over-allocating?
4. **Verify pooling:** Is `CqlSession` reused? Creating a session per request is a severe anti-pattern.
5. **Bound non-Cassandra work:** JSON/protobuf serialization, fresh TLS handshakes per call, or HTTP response mapping.
6. **Check the arrival scheduler:** Did closed-loop slow down offered load, or did open-loop silently drop arrivals when permits ran out?
7. **Scale out generator hosts if needed:** Keep total rate accounting accurate and clocks synchronized.
8. **Re-run baseline:** Keep queries, data, and CL identical while fixing only the generator; compare driver/server p99 and achieved rate.

**A healthy generator is a prerequisite for diagnosing server bottlenecks.** Never trust a p99 figure without knowing where it was measured.

## 24. Runbook D — Failover Keeps Quorum, Yet Breaches Latency/Error Budgets

**Symptom:** RF=3, `LOCAL_QUORUM` cluster loses one replica in lab; most writes succeed, yet p99 jumps 6×, retry attempts climb, and compaction backlog forms after recovery.

1. **Compare baseline vs. fault vs. recovery:** Same offered QPS, query mix, and dataset.
2. **Classify errors:** `DriverTimeout`, `Read/WriteTimeout`, `Unavailable`, `AllNodesFailed`, and connection pool errors.
3. **Check RF/CL impact:** How many replicas remain available, and which DC/rack was affected?
4. **Inspect surviving nodes:** CPU/GC, disk, commitlog, network, and pending queues.
5. **Check retries/speculative execution:** Did they amplify load during the fault window?
6. **Track recovery:** Did hints/streaming/repair, compaction, and disk headroom prolong the tail?
7. **Shed offered load if guardrails breach:** Single-node-fault capacity may be lower than healthy steady-state capacity.
8. **Verify data correctness:** Confirm no lost/duplicated mutations from unsafe retries, and reconcile LWT/counter/unknown write outcomes.
9. **Report full recovery time:** Measure until API success and p99 return to SLO, not just when `nodetool status` shows `UN`.

**A cluster can maintain logical availability while failing performance SLOs.** Plan headroom and traffic policies for degraded operation, not just quorum arithmetic.

## 25. Comparable Benchmark Report Template

A useful report contains enough detail for someone else to **reproduce the exact workload**, rather than just a p99 screenshot and a QPS number.

### 25.1. Mandatory Metadata

~~~yaml
# Report example ONLY, NOT a config file to create in this step.
experiment_id: cassandra-bench-read-001
environment: isolated-staging
date_utc: "2026-11-21"
cassandra_release: "<version tested>"
java_driver_release: "<version tested>"
generator:
  model: open-loop
  offered_rps: 1200
  max_outstanding: 500
  host_count: 2
cluster:
  nodes_per_dc: 3
  datacenters: [dc1]
  replication_factor_dc1: 3
  read_consistency: LOCAL_QUORUM
  write_consistency: LOCAL_QUORUM
workload:
  query_template: latest20_by_device_day
  read_percent: 100
  write_percent: 0
  partition_distribution: "uniform on preseeded data"
  rows_per_read_limit: 20
  paging_size: 20
phases:
  warmup_minutes: 5
  steady_minutes: 30
  recovery_until_stable: true
acceptance:
  p99_success_ms_max: 200
  logical_error_rate_pct_max: 0.5
  required_recovery: "API and Cassandra metrics stable"
~~~

**All values are examples.** Fill in actual cluster release/version details during real tests; never leave placeholders like `<version tested>` in a final report.

### 25.2. Results Table to Populate

| Group | Metric | Healthy Baseline | Under Fault | Recovered |
|---|---|---:|---:|---:|
| Client | Offered logical RPS | 1,200 | 1,200 | 1,200 |
| Client | Successful RPS | 1,195 | 1,160 | 1,193 |
| Client | p50 success | 9 ms | 12 ms | 10 ms |
| Client | p95 success | 35 ms | 180 ms | 40 ms |
| Client | p99 success | 140 ms | 520 ms | 155 ms |
| Client | Timeout/error % | 0.2% | 2.7% | 0.3% |
| Driver | Retry attempts / logical request | 1.01 | 1.22 | 1.02 |
| Server | Worst-node CPU | 58% | 83% | 61% |
| Server | Worst-node disk await | 7 ms | 26 ms | 9 ms |
| Server | Pending compaction | Low/stable | Rising | Declining |
| Recovery | Time to SLO | N/A | N/A | 8 minutes |

This is a **hypothetical table**, not real measurements. Offered, success, and error figures are rounded per window and may differ slightly due to boundary in-flight work; real reports must specify the **denominator**, time window, sample counts, and rejections.

### 25.3. Illustrative Report Conclusions

- Healthy baseline met example targets **p99 ≤ 200 ms** and **errors ≤ 0.5%**.
- Under fault, p99 hit 520 ms and errors 2.7% → **FAIL** if under-fault acceptance required p99 ≤ 400 ms and errors ≤ 1%.
- Recovery took ~8 minutes, but **hints, compaction, and disk** still require verification alongside API responses.
- Production capacity targets should preserve failover headroom; tune concurrency/rate limits, inspect node hotness, and repeat tests.
- Never pick the highest offered rate from a single run as standard capacity.

### 25.4. Attach Supporting Evidence Alongside Summary Metrics

Archive in an approved report repository or results store:

- Query templates/CQL, schema, and seed data distributions.
- Driver/generator/server versions and config profiles.
- Time series of offered/achieved/errors and p50/p95/p99 histogram buckets.
- Per-node CPU/GC/disk/network, `tpstats`/compaction/streaming.
- Fault-injection and recovery timelines.
- Pass/fail status of business invariants and data consistency checks.
- Goals, PASS/FAIL decisions, caveats, owners, and action items.

Ensure logs and metrics contain zero passwords, tokens, raw tenant/device IDs, or sensitive bind values. Never embed an entire production dataset in a benchmark report.

## 26. Load-Testing Anti-Patterns to Spot

| Anti-Pattern | Why Dangerous? | Fix |
|---|---|---|
| Reporting only mean latency | Hides the slowest 1% | Always check p50/p95/p99 + errors |
| Averaging per-node p99s | Percentiles do not average linearly | Aggregate compatible histogram buckets |
| Measuring only success p99 | Timeouts vanish from the chart | Report successes, errors, and timeouts in the same window |
| Running closed-loop and claiming fixed RPS | Slow responses throttle offered rate | Track offered schedule or use capped open-loop |
| Ignoring generator saturation | You may be benchmarking the generator | Monitor generator CPU/GC/network/schedule lag |
| Using 1 cached hot key as representative | Ignores token and data distributions | Seed diverse partitions with realistic profiles |
| Treating default `cassandra-stress` schema as app benchmark | CQL/payloads differ from production | Custom profile or Java driver generator |
| Comparing cold vs. warm runs without labeling | Different cache/JIT/pool states | Explicitly document cold vs. warm state |
| Running 30 seconds and declaring max QPS | Misses compaction and recovery | Sustained windows plus cool-down |
| Adding retries to boost success without tracking attempts | Amplification hides backend load | Track attempts/logical request and retries/s |
| Lowering CL to `ONE` to boost QPS | Alters correctness and availability | Keep business CL; report changes separately |
| Ignoring bytes/row or rows/query | 1 QPS is not uniform work | Measure payload/rows/bytes per op |
| Lumping LWTs, reads, and writes into one p99 | Mix shifts skew results | Stratify by query template and operation |
| Watching only cluster average CPU | One replica or core may be pegged | Track per-node / worst-node metrics |
| Relying solely on `nodetool status = UN` | UP does not guarantee SLOs | Check latency, queues, disk, GC, network |
| Raising client concurrency on saturated disks | Deepens queues and timeouts | Reduce load, optimize read path/capacity |
| Running blind repair/compact when p99 spikes | Adds heavy I/O | Follow SOPs and check resource headroom |
| Counting retries/errors as logical successes | Corrupts denominators and rates | Separate attempts, outcomes, and rejections |
| Using raw partition keys as metric labels | Cardinality explosion and data leak | Low-cardinality bands and sampling |
| Reporting a single run | Noise, CI, caches, and clocks vary | Repeat runs and report confidence/windows |
| Missing stop conditions | Can crash labs or affect shared systems | Guardrails, owners, and rollback plans |
| Claiming better p99 during faults while errors spike | Survivorship bias | Always pair latency with availability |
| Skipping data correctness checks | High throughput with wrong mutations | Verify read-backs and invariants |
| Ignoring multi-DC networking | Real replication consumes bandwidth | Track DC topology, CL, and cross-DC metrics |

## 27. Exercises with Answers

### Q1 — p50, p95, p99

A set of 1,000 requests has 900 at 10 ms, 50 at 40 ms, 40 at 180 ms, 9 at 900 ms, and 1 at 4,000 ms. By nearest-rank, what are p95 and p99?

**Answer:** p95 at position 950 = **40 ms**; p99 at position 990 = **180 ms**. Never substitute mean or max for p99.

### Q2 — Mean Hides the Tail

What is the mean of the dataset in Q1?

**Answer:** `(900×10 + 50×40 + 40×180 + 9×900 + 1×4000) / 1000 = 30.3 ms`. A low mean does not erase the 900–4,000 ms requests.

### Q3 — p99.9

With the same 1,000 requests, what is nearest-rank p99.9?

**Answer:** `ceil(0.999 × 1000) = 999`, so position 999 gives **900 ms**. Position 1,000 at 4,000 ms is the max.

### Q4 — Insufficient Samples

A window has only 40 requests. Is its p99 as reliable as a 100,000-request window?

**Answer:** No. 1% of 40 is 0.4 requests, making p99 highly sensitive to outliers and computation method; ensure sufficient sample counts and clear windows.

### Q5 — Latency vs. Error Rate

Test A has success p99 = 70 ms with 10% timeouts. Test B has success p99 = 150 ms with 0.05% timeouts. Can you declare A better solely because of lower p99?

**Answer:** No. Success latency and availability must be evaluated together; Test A likely dropped its slowest requests as timeouts.

### Q6 — Offered vs. Achieved

A generator tries to send 3,000 requests/s; the server completes only 2,300/s. Without rejections or drops and with steady arrivals, how does the backlog behave?

**Answer:** In a simple model, backlog grows by roughly **700 requests per second**. In practice, measure where queuing, rejections, and in-flight items sit rather than assuming all queuing is inside Cassandra.

### Q7 — Little's Law

In steady state at 2,500 completed ops/s with 40 ms average latency, roughly how many requests are in the system on average?

**Answer:** `L = 2500 × 0.040 = 100`. Never plug p99 in place of mean latency in this formula.

### Q8 — RF and Replica Cost

There are 2,000 logical writes/s at RF=3 in one DC. Roughly how many target replica mutation deliveries occur in steady state?

**Answer:** Roughly **6,000/s** before accounting for retries, hints, batching, compaction, and node distribution. This does **not** mean 6,000 disk IOPS or 6,000/s on every node.

### Q9 — CL

Lowering `LOCAL_QUORUM` to `ONE` makes the benchmark faster. Should you switch just for higher throughput?

**Answer:** Not by default. CL is a consistency, availability, and correctness decision; never lower it just to hit a KPI.

### Q10 — Percentiles Across Nodes

Three nodes report p99 latencies of 40, 45, and 800 ms. Can you average them to report cluster p99?

**Answer:** No. Percentiles cannot be aggregated by averaging; combine compatible histograms or raw samples properly.

### Q11 — Histograms

You want to compute multi-instance p99 from a classic histogram in PromQL. Which labels must be kept in `sum by`?

**Answer:** Keep `le` and the desired grouping labels (such as `query_template`) when summing bucket rates, then pass to `histogram_quantile(0.99, ...)`.

### Q12 — Coordinated Omission

A synchronous worker waits for each response before sending the next request. When the server pauses for 2 seconds, the benchmark skips scheduled arrivals during those 2 seconds. What issue is this?

**Answer:** **Coordinated omission**: the true arrival schedule was not maintained or recorded, causing the histogram to understate tail latency under steady traffic.

### Q13 — Unbounded Open-Loop

An open-loop generator sends 10,000/s into a cluster handling only 1,000/s with no outstanding limit. What can happen?

**Answer:** Queues, in-flight requests, and heap grow rapidly, risking crashes on both generator and cluster. Enforce max outstanding limits, count rejections, and set stop conditions.

### Q14 — Driver Async Timing

You time how long `session.executeAsync(stmt)` takes to complete on a 10,000-row SELECT. Did you necessarily measure consuming all 10,000 rows?

**Answer:** No. That may measure only the first page; track full paging and row processing if the SLO requires the complete result.

### Q15 — Generator Bottleneck

Cassandra nodes have low CPU and disk usage while the generator hits 100% CPU with long GC pauses. Should you blame Cassandra disks?

**Answer:** No. Check generator saturation, callback/instrumentation overhead, scheduling lag, and networking first.

### Q16 — Hot Partitions

A uniform-key test shows good p99, while production shows high p99 on a few super-hot devices. How should the test profile change?

**Answer:** Add Zipfian/skewed hot-key distributions, per-node/token metrics, partition sizes, and worst-node measurements; review bucketing and data modeling.

### Q17 — Compaction

p99 climbs alongside rising `compactionstats` pending tasks and disk await. Should you immediately trigger major compaction on production?

**Answer:** No. First investigate I/O bottlenecks, compaction strategy, disk headroom, background jobs, and runbooks; major compaction can worsen load.

### Q18 — Single-Node Fault

In a lab cluster at RF=3 and `LOCAL_QUORUM`, one replica goes down. Is p99 guaranteed to stay unchanged because quorum still holds?

**Answer:** No. Surviving replicas carry shifted load, and rerouting, retries, hints, and network effects can raise p99 and errors; measure degraded capacity directly.

### Q19 — Recovery

`nodetool status` reports `UN` for a recently restarted node. Can you declare the cluster fully recovered?

**Answer:** No. Also inspect hints, repair/streaming, compaction, per-node latency, client reconnections, and API SLOs.

### Q20 — Resource Headroom

Two runs achieve identical successful throughput. Run A's hottest node is at 55% CPU and 5 ms disk await; Run B is at 90% CPU and 30 ms disk await. Do they have equal headroom?

**Answer:** No. Run B is near saturation and far more vulnerable to node faults or bursts; evaluate resource headroom alongside p99.

### Q21 — Error Denominator

The driver retries three times for one logical HTTP request. Should those 3 driver attempts count as 3 successful logical requests in the API SLO?

**Answer:** No. Logical request SLOs count one final outcome per logical operation; track attempts/s separately to measure Cassandra load and retry amplification.

### Q22 — Concluding Capacity

A 30-second burst hits 20k QPS before compaction kicks in; a 1-hour test at the same offered QPS shows rising pending queues and p99 breaching SLO. What is the sustainable capacity?

**Answer:** You cannot claim 20k from a short burst. Identify the **steady-state** load below the saturation knee where p99, error rates, resources, and failure headroom all pass, and verify across repeated runs.

## 28. Acceptance Checklist for Load and Distributed Fault Testing

### 28.1. Benchmark Design

~~~text
[ ] Workload documents schema, partition keys, query templates, and CQL.
[ ] Read/write/LWT mix, payload bytes, and rows/query recorded.
[ ] RF, CL, local DC, topology, and driver version fixed.
[ ] Data volumes, TTL/tombstones, and hot-key distributions modeled realistically.
[ ] Open-loop vs. closed-loop and coordinated omission addressed.
[ ] Generator caps max QPS/in-flight and logs rejected/missed arrivals.
[ ] Dataset, warm-up, and cache states explicitly described.
[ ] Multiple ramp steps, steady windows, and cool-down included.
[ ] Experiments run only on authorized clusters with isolated test data.
[ ] Owners, guardrails, stop conditions, and recovery/rollback plans defined.
~~~

### 28.2. Client / Driver Measurements

~~~text
[ ] p50/p95/p99 reported per query template and window with sample counts.
[ ] Mean/max and histograms specify buckets and units.
[ ] Percentiles are never averaged across nodes or windows.
[ ] Success latency paired with failure/timeout/unavailable rates.
[ ] Offered, submitted, completed, and successful throughput separated.
[ ] Logical operations and attempts/retries/s kept distinct.
[ ] Rows/s and bytes/s measured when queries return multiple rows/pages.
[ ] End-to-end API latency separated from driver first-page vs. full-consume.
[ ] Generator CPU/GC/network/schedule lag verified unsaturated.
[ ] Metrics exclude raw primary keys, tenants, tokens, and secrets.
~~~

### 28.3. Cassandra Measurements and Interpretation

~~~text
[ ] Worst-node CPU, CPU throttling, GC, and heap/off-heap monitored.
[ ] Disk free GB/%, IOPS, MiB/s, and await/queues tracked per device.
[ ] Commitlog fsync, memtable flushes, and pending compactions observed.
[ ] Read amplification tracked: SSTables/read, tombstones, row sizes.
[ ] nodetool tpstats, compactionstats, and tablestats captured over time.
[ ] Native transport and inter-DC network Rx/Tx measured.
[ ] nodetool netstats is not misused as a CQL network metric.
[ ] Per-node RF/CL/replica availability, hints, and repairs compared.
[ ] Node UN is not mistaken for full API SLO recovery.
[ ] Tests halt per guardrails on rising errors/drift rather than hiding them.
~~~

### 28.4. Analysis and Handoff

~~~text
[ ] PASS/FAIL evaluated against p99, successful throughput, and error budgets.
[ ] Baseline/fault/recovery comparison table included for fault tests.
[ ] Workloads compared under identical schema/dataset/CL without cherry-picking.
[ ] Knee-of-curve and headroom reported, not just peak QPS.
[ ] Time-series charts prove steady state without backlog drift.
[ ] Sample sizes, window lengths, units, histograms, and caveats stated.
[ ] Data correctness verified alongside performance.
[ ] Runbooks available for p99 tails, saturation, generator limits, and node faults.
[ ] Inconclusive bottlenecks and follow-up measurements clearly noted.
[ ] Do not run Gradle/benchmarks/fault injection on your own in STEP 4.
~~~

## 29. Summary

To conduct **load and distributed fault testing** on Apache Cassandra properly, treat latency, throughput, and resources as **one connected set of metrics**:

1. **p50/p95/p99** describe the latency distribution; p99 exposes tail behavior that means and p50 conceal.
2. **Never average percentiles** across nodes, instances, or windows; aggregate compatible histograms or raw observations consistently.
3. **Success latency must accompany error/timeout rates**; a falling p99 caused by slow requests timing out is not an optimization.
4. **Offered load ≠ completed/successful throughput.** Once throughput plateaus while queues, p99, and errors climb, you have crossed the safe load point.
5. **Logical operations ≠ driver attempts.** Retries and speculative executions amplify backend load and distort benchmarks if you count only HTTP outcomes.
6. **Little's Law links mean values** of concurrency, throughput, and latency in steady state; never substitute p99 for the mean.
7. **Open-loop vs. closed-loop and coordinated omission** alter latency/throughput visibility; match the generator to real traffic and count misses/rejections.
8. **RF/CL, partition keys, and data distributions** dictate replica work. Hot/wide partitions and tombstones can stall specific nodes even when cluster averages look fine.
9. **CPU/GC/heap, disk IOPS/await, network, compaction, repair, hints, and pending queues** explain why p99 rises; never rely solely on `UN`.
10. **Benchmarks require warm-up, sustained windows, guardrails, and recovery.** A brief peak QPS is not sustainable capacity.
11. **Lab fault tests** must measure pre-, during-, and post-failure SLOs, resource headroom, and data correctness; quorum availability does not guarantee unchanged p99.
12. **Reproducible reports** document schema/CQL, versions, RF/CL, workload mix, sample counts, histograms, outcomes, server resources, and conclusion boundaries.

The most important question is not **"How many QPS can Cassandra hit?"**, but rather: **"Under a defined workload, RF/CL, and data distribution, how many logical operations does the system complete within its p99 and error budget, what resources does the hottest node consume, and does sufficient headroom remain to serve accurately when part of the cluster fails?"** That is the true foundation for query tuning, capacity sizing, and SLO protection.
