# Warm-Up Phases and Cache/Compaction State in Apache Cassandra Load and Fault Testing

> **Chapter:** Load and Distributed Fault Testing  
> **Audience:** Java engineers, SREs, DBAs, and engineers building performance/fault-injection tests on Apache Cassandra 4.x/5.x. This lesson focuses on designing **verified warm-up**, measuring **cold-start and steady-state** separately, recognizing hot/cold cache states, memtable flushes, SSTables/compaction, and avoiding false conclusions about p95/p99 or fault tolerance. Run all load-generation or fault-injection commands **only on approved lab/staging environments**, never by default against production.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain why **JVM/driver warm-up**, **Cassandra/OS cache warm-up**, and **compaction catch-up** are **three distinct processes**.
2. Distinguish **cold**, **warm-up/transient**, **steady-state**, and **post-fault recovery** latencies instead of collapsing everything into a single p99 figure.
3. Explain the impact of **key cache, row cache, chunk cache/OS page cache, memtable, SSTables, and bloom filters** on the read path.
4. Explain the write path **commit log → memtable → flush → SSTables → compaction**, and its impact on CPU/disk I/O, write amplification, read amplification, and tombstones.
5. Interpret metrics such as `KeyCacheHitRate`, `RowCacheHitRate`, `SSTablesPerReadHistogram`, `LiveSSTableCount`, `PendingCompactions`/`PendingTasks`, `CompactionBytesWritten`, pending flushes, GC, and disk await in proper context.
6. Design a **warm-up plan driven by query mix, throughput, working set, CL/RF, partition size, and TTL**, rather than a fixed sleep duration.
7. Define a **steady-state gate** using rolling windows across QPS, p95/p99, cache hits/misses, compaction backlog, SSTable count, GC, I/O, and resource headroom.
8. Design **A/B experiments with identical datasets and environmental conditions**, knowing when cold data must be included in the workload to avoid overfitting hot caches.
9. Write a CQL/Java Driver 4.x lab distinguishing **repeated hot-key reads** from **multi-partition reads**, while recording metadata and latency in a controlled way.
10. Use `cassandra-stress` as an illustrative tool, understanding the limitations of its default schema and distributions compared to Java application traffic.
11. Build a load- and fault-testing runbook covering **baseline → warm-up → steady → fault → recovery → post-recovery**, with GO/HOLD/STOP criteria and rollback.
12. Distinguish "node is UP" from "cache/compaction have stabilized" and "queries at the business consistency level truly meet SLOs".

**Module context (`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`):** Cassandra is a distributed wide-column database; the partition key determines the token and natural replicas, the replication factor (RF) determines replica count, and the consistency level (CL) specifies required responses/ACKs. Query-driven design, partition data, memtable/SSTable/compaction, and the Java Driver all jointly affect performance. Load testing is meaningful only when **these layers are separated** and the application's consistency contract is preserved.

## 2. What Is Warm-Up, and Why Is Mis-Sampling Data Dangerous?

**Warm-up** is a controlled workload window allowing history-dependent components to reach representative state: JIT compiles hot paths, connections and prepared statements are established, caches populate frequently used keys/pages, memtables/SSTables move past initial states, and preparation-phase flushes/compactions are accounted for.

Warm-up **does not mean** "all data is in RAM", "all compactions have finished", or "the cluster is automatically production-ready". Under sustained writes, background compaction runs continuously even in steady state. A stable system is one that **does not accumulate unbounded backlog**, not one where `PendingCompactions=0` every second.

### 2.1. Timeline of a Load Test

~~~text
T0  Create cluster or restart service
    |
    v
BOOT: JVM, native port, gossip, driver metadata, schema
    |
    v
SEED: load dataset with target volume/partitions/TTL, await initial flush
    |
    v
WARM-UP: controlled request mix
    |     driver JIT + connections + prepared statements
    |     key/row/chunk/page cache warming
    |     memtable/SSTable transitions + compaction catch-up
    v
STEADY BASELINE: rolling metrics/throughput/latency stabilized
    |
    v
MEASUREMENT: capture p50/p95/p99, errors, CL, CPU/IO/GC
    |
    v
FAULT (if applicable): node/network/latency/replica disruption
    |
    v
RECOVERY: ring + replica availability + cache + compaction
    |
    v
POST-RECOVERY STEADY: measure recovery capability and backlog
~~~

**Typical mistake:** Test A starts with caches still hot from the previous run, whereas Test B starts on a fresh dataset with a cold OS page cache. Concluding "A is faster than B" may merely measure **different cache histories**, not the effect of a code or compaction-strategy change.

### 2.2. Separating Two Measurement Goals

| Goal | Exclude Warm-Up from Primary Metrics? | What Must Be Reported? |
|---|---|---|
| **Cold-start SLA** (starting after an outage) | **No** | Time-to-first-success, p95/p99 right after startup, cache recovery time |
| **Steady-state capacity** | Can **exclude from primary KPI window** once gate passes | QPS/p95/p99/errors/resources under proven steady state |
| **Failover/recovery SLA** | **Do not** exclude fault/recovery windows | Time-to-recover at required CL, error budget, backlog drain |
| **Compaction strategy comparison** | Separate phases, but report catch-up cost too | Steady throughput, read/write amp, disk space, recovery time |
| **Production-like workload** | Cannot warm up beyond reality | Hit ratios, active working set, temporal skew matching production |

Never blend cold-start latency and steady latency into a single p99 without stating phase proportions. Conversely, **never hide an ugly recovery phase** when the SLA requires recovering within minutes of a restart.

### 2.3. "Warm for 5 Minutes" Is Not a Law

Warm-up duration depends on:

- **Working-set size:** 10 thousand hot partitions differ from 100 million partitions.
- **Access distribution:** hot 1% keys (Zipfian) differ from uniform random.
- **QPS and concurrency:** a 50 RPS warm-up does not mirror 5,000 RPS production traffic.
- **Read/write mix, ranges/paging**, partition width, and cache admission/eviction.
- **Memory/OS cache** relative to dataset size; whether seeding, flushing, and compaction are complete.
- **Compaction strategy, disk throughput, tombstones/TTL, repair, RF/CL.**
- **Driver/JVM:** JIT, metadata, prepared cache, connection pool, Netty event loops, and GC.

A fixed duration like 5 minutes can only be a **minimum time budget** for a specific experiment, never a substitute for **observing actual state**.

## 3. Multiple "Caches" Live at Different Layers

~~~text
Client / Java application
  - HTTP/service caches and object pools (if any)
  - JVM JIT, class loading, GC
  - Java Driver CqlSession, connections, metadata, prepared cache
                   |
                   | CQL QUERY/EXECUTE
                   v
Cassandra coordinator
  - Request parsing/prepared metadata
  - Scheduling, replica requests, hints/retries (as applicable)
                   |
                   v
Natural replicas (by partition token + RF)
  - Memtable: latest writes, checked/merged on read path
  - Key cache: faster partition/index position lookup
  - Row cache: cached hot row/partition data if enabled
  - Chunk cache: SSTable compression chunks in supporting versions
  - OS page cache: SSTable/index file pages retained by the kernel
  - SSTable bloom filters, index summaries, partition index
  - SSTables + compaction + disk filesystem
~~~

**Do not conflate** "Java Driver prepared statement cached" with "partition data resident in OS page cache". Both may warm up during repeated SELECTs, yet they are measured by different metrics and reset by different events.

### 3.1. Comparison of Warm-Up Layers

| Layer | Changes While Warming | Reset / Affected By | Useful Metrics / Signals |
|---|---|---|---|
| **App JVM** | JIT hot code, allocation patterns, heap | JVM restart, GC, new workload | JFR, GC pauses, CPU, allocation |
| **Driver** | Connections/pools, metadata, prepared statements, token-aware routing | Service/session restart, node topology | Pool open connections, in-flight, retries, request latency |
| **Cassandra JVM** | Class loading/JIT, allocations, GC | Node restart, workload/heap pressure | GC pauses, CPU, thread pool pending |
| **Key cache** | Hot partition/index lookup caching | Cache size, eviction, restart/saved caches | Hit rate, entries, size/capacity |
| **Row cache** | Cached row/partition content when enabled | Disabled/default, TTL/invalidations, memory | Hit rate, entries, hit/miss |
| **Chunk cache** | Hot compressed SSTable chunks (implementation-dependent) | Cache size, restart, compaction rewriting chunks | Hit/miss/evictions where exposed |
| **OS page cache** | Hot SSTable/index disk pages | Host memory pressure, host reboot, file churn | Disk read bytes/ops, major faults, page-cache residency |
| **Memtable** | Recent writes still in memory | Flush thresholds, flush/truncate/rollback | Memtable size/flush metrics |
| **SSTable set** | Count/tiers/size of SSTables and lookup work | Flushes, compaction, repair, restore | `LiveSSTableCount`, `SSTablesPerReadHistogram` |
| **Compaction** | Merges/rewrites SSTables, processes tombstones | Strategy, write rate, sizes/tombstones | Pending tasks/bytes, compaction throughput, disk/CPU |

**Important:** Not every Cassandra deployment enables `row cache`. In many Cassandra 4.x/5.x setups, row cache is **disabled or very small** by default; key cache and OS page cache matter more for most workloads. `Chunk cache` behavior and metric names vary by version and settings. Always inspect **the effective `cassandra.yaml` + actual JMX/metrics** before claiming a cache is "warm".

### 3.2. A Warm Cache Is Not Just a "High Hit Rate"

A cache showing a 99% hit rate over 100 reads of **the same partition** can be nearly useless for a production workload reading 10 million distinct partitions. Always pair hit ratios with:

- **Query family**, number of distinct partition keys, and key distribution.
- **Data volume read:** 1 KB/partition differs from 5 MB/partition.
- **Costly cache misses:** disk I/O, SSTables accessed, and tombstones scanned.
- **Evictions/capacity:** temporarily high hit rates alongside cache churn cause unstable p99.

Cache hit rates cannot substitute for p95/p99 or correctness verification at the required CL. Nodes that are not natural replicas of a hot partition have different cache contents, so the same SELECT routed via different coordinators may experience different latencies.

## 4. Cassandra Read Path: Warm Caches and Amplification

### 4.1. What Does a Partition Read Traverse?

~~~text
SELECT ... WHERE partition_key = ?
               |
         coordinator
               |
        choose replicas by CL
               |
         replica read path
               |
       Memtable + row cache (if enabled)
               |
         SSTable candidates
               |
       Bloom filters/index summary
               |
     Key cache / partition index search
               |
      OS page cache or physical disk
               |
        Data blocks / decompression
               |
       Reconcile timestamps/tombstones
               |
        Coordinator merges responses
               |
             ResultSet
~~~

This is a **conceptual diagram**, not a rigid execution sequence for every version and query. Bloom filters and key cache help skip or accelerate SSTable index lookups, yet a query may still read multiple SSTables even on a key-cache hit.

### 4.2. Key Cache

Key cache primarily reduces the cost of locating **partition/index offsets** inside SSTables. When hot, it cuts down disk index lookups, especially on point-lookup workloads. However:

- **A key cache hit is not a data cache hit:** reading SSTable data blocks may still hit disk.
- A partition spread across many SSTables after repeated flushes/compactions still triggers multiple lookups.
- Key cache does not make `ALLOW FILTERING` or wide range scans cheap.
- Cache state depends on restarts/saved caches and compaction; do not assume a restart always leaves key cache completely empty.

### 4.3. Row Cache

When enabled, row cache stores frequently read row/partition data to bypass SSTable I/O, depending on cache strategy and partition layout. In return, it consumes memory, requires invalidation/updates on writes, and can become ineffective when:

- Access keys are broadly scattered without a hot set.
- Partitions exceed row-cache capacity limits.
- Continuous writes to the same partitions cause cache churn.

Never enable row cache just to get a pretty benchmark p99 and then compare it against production where row cache is disabled.

### 4.4. OS Page Cache and Chunk Cache

The Linux/Windows kernel retains recently read file pages in RAM. Cassandra relies heavily on the OS page cache for SSTable I/O. Depending on version and compression config, the chunk cache may retain decompressed/read chunks to reduce I/O and CPU.

**Three distinct facts:**

1. Reading the same partition a second time may avoid physical disk I/O thanks to the page cache.
2. Restarting the **Cassandra JVM** on the same host may **not clear** the kernel page cache.
3. Compaction writes new SSTables, changing file paths/layouts and making older cached pages less useful.

Consequently, assuming "restarting the Docker container = cold disk cache" is **unreliable** when the container shares the host's page cache and volumes.

### 4.5. SSTables-per-Read: An Indicator of Read Amplification

Suppose one partition has data fragmented across 12 SSTables after multiple flushes:

~~~text
Read P -> examine SSTable S1, S2, ..., S12
             |
        merge cells/timestamps
             |
          1 row returned
~~~

After appropriate compaction, a read may need to inspect fewer SSTables. Yet "fewer SSTables" does not guarantee faster reads in every case: background compaction also consumes disk/CPU, and tombstone density or page-cache residency strongly influences speed. Pair `SSTablesPerReadHistogram` with read latency, scanned/returned rows, disk I/O, and key-cache metrics.

## 5. Write Path: Memtables, Flushes, and Where Compaction Begins

### 5.1. A CQL Write Does Not Wait for Compaction

~~~text
Java Driver: INSERT/UPDATE at CL LOCAL_QUORUM
                  |
              Coordinator
                  |
         Natural replicas RF3
             /     |     \
            A      B      C
            |      |      |
      Commitlog + Memtable  (on each replica)
            |      |      |
          ACK    ACK    ...
             \     /
       CL satisfied -> client success
                  |
             Later over time
                  |
           Memtable flush -> SSTables
                  |
           Compaction rewrites SSTables
~~~

An `INSERT` ACK at `LOCAL_QUORUM` does not mean SSTables have flushed or compaction has finished. Cassandra uses the write-ahead commit log and memtable to complete the write path; flushing and compaction happen asynchronously later. Write benchmarks often show **very high initial throughput** while most data stays in memtable/commitlog, then drop once flushes and compactions kick in and real disk capacity is exercised.

### 5.2. "Measuring Writes Right After Table Creation" Is Usually Too Optimistic

~~~text
Time      Data path                          Measurement Risk
0-2 min   Memtable receiving new writes      Few SSTables on disk, high throughput
2-5 min   Memtable flush -> SSTables         Disk writes rise, p99 fluctuates
5-15 min  Compaction starts/catches up       CPU/IO amplification appears
15+ min   May stabilize or build backlog     Depends on load, disk, strategy
~~~

These timestamps are **illustrative**, not fixed Cassandra timings. With very large datasets, background compaction can run for hours; with small data and fast RAM/disks, it can finish much sooner.

### 5.3. When Do Memtables Flush?

Memtables have dedicated budgets and flush when triggered by conditions such as memory/commitlog pressure, manual flushes, or specific lifecycle events. Flushing turns memtable contents into immutable SSTables. Never believe a load test has "reached write steady state" if:

- Memtable size is still climbing rapidly without representative flush cycles.
- Commitlog/disk queues are accumulating.
- Disk flush throughput has not reached the workload's normal pace.
- The test ends before compaction triggered by the seeded data has a chance to run.

**Do not run `nodetool flush` to "patch a benchmark"** when the experiment requires natural flushing; a manual flush alters SSTable count/tiers and invalidates fair comparisons. Only use manual flush in **purpose-built labs**, documenting it explicitly as a controlled variable.

### 5.4. Metric Distinctions: Memtable vs. Flush Queue vs. Compaction

| Signal | Meaning | If Rising Continuously |
|---|---|---|
| Memtable on/off-heap size | Recent write data in memory | Receiving fast writes; watch flush cadence |
| Pending flushes / flush writer queues | Unfinished work writing SSTables | Disk/flush throughput cannot keep up |
| Commitlog activity / disk bytes | Write-ahead log I/O and segment pressure | Disk or commitlog flush/recycle bottleneck |
| Live SSTable count | Existing SSTables for the table | Many files can increase read amplification |
| Pending compaction tasks | Queued compaction jobs | Compaction capacity may be insufficient |
| Compaction bytes processed/written | I/O spent merging/rewriting | Overhead can scale with write load |
| Disk utilization / await | Physical I/O resource pressure | Read/write p99 may spike |
| GC pauses / CPU steal | JVM/host contention | Can trigger false timeouts from backlog |

One pending compaction task does not represent a fixed unit of data; comparing **raw task counts alone** across tables or strategies can mislead. Combine task counts with bytes remaining, SSTable sizes, and throughput over time.

## 6. How Compaction Strategies Alter Steady State

**Compaction** selects and merges SSTables, reconciles cell versions and tombstones per Cassandra rules, and reduces read probes at the cost of read/write I/O, CPU, and temporary disk space amplification. Different strategies optimize for different trade-offs; never do a "before/after" comparison while dataset, TTL, and query mix change simultaneously.

### 6.1. Common Strategies

| Strategy | Typical Fit | Characteristic Cost Profile | Testing Notes |
|---|---|---|---|
| **STCS** — SizeTieredCompactionStrategy | Write-heavy, size-tiered merges | Groups similar-sized SSTables; read amplification can grow | Requires enough data to form realistic size tiers |
| **LCS** — LeveledCompactionStrategy | Read-heavy / point lookups needing bounded SSTable overlap | Higher write amplification and rewrite I/O | Measure compaction CPU/bytes rewritten, not just read p99 |
| **TWCS** — TimeWindowCompactionStrategy | Time-series / TTL with matching time buckets | Compacts within time windows; late/out-of-order timestamps cause issues | Check time distribution, TTLs, window size, late arrivals |
| **UCS** — UnifiedCompactionStrategy | Supporting Cassandra versions, balanced workloads | Tuning/overhead varies by level/shape | Document version and config; do not assume availability on 4.x |

**Never claim "LCS is always faster than STCS" or "TWCS always has fewer tombstones".** Outcomes depend on partition cardinality, key distribution, TTLs, hardware, read/write ratios, and test duration.

### 6.2. Why Multiple Flush/Compaction Cycles Are Needed

Suppose we compare two designs:

~~~text
Test A: STCS, 3-minute run, 1 SSTable after a single flush
Test B: LCS, 3-minute run, 1 SSTable after a single flush

Result: nearly identical.

Wrong conclusion: "Strategy makes no difference."
Right conclusion: "Measured too early; no compaction regime formed yet."
~~~

For a stable comparison, ensure **representative SSTable counts/levels, compaction backlogs, and test durations**. For LCS, inspect SSTables **per level**; for TWCS, populate data spanning multiple **time windows** aligned with retention and late-arrival policies.

### 6.3. Continuous Compaction Is Not Necessarily an Incident

Under sustained writes, having `CompactionExecutor` continuously active is normal. The goal is balance:

\[
\text{compaction work arriving per second}
\;\lesssim\;
\text{sustainable compaction work served per second}.
\]

If the arrival rate persistently exceeds capacity, backlog, SSTable count, and space amplification grow and p99 trends upward. If they oscillate around a stable band with workload cycles, that can be a **steady state with ongoing background work**. A gate requiring "`PendingCompactions=0` for 60 seconds" is usually unrealistic for production-like sustained writes.

### 6.4. Tombstones, TTLs, and Long Horizons

A 10-minute stress test on a table with a 30-day TTL **cannot** expose the expiration and tombstone churn of 30 days of production traffic. Conversely, setting a 30-second TTL to "simulate" 30 days can produce unrealistic compaction dynamics.

~~~text
Time-series:
Day 0: write events, TTL ~ 30 days
Day 1..30: continuous late writes + reads
Day 31: expiry, compaction/tombstone reclamation

10-minute benchmark:
  has not traversed the corresponding expiry/compaction lifecycle
~~~

Tombstones can be purged only once safety conditions hold, depending on repaired state, SSTable overlap, and `gc_grace_seconds` (or newer version modes). Never force `nodetool compact` continuously on production to flatter metrics; artificial compaction diverges from real load and risks exhausting disk space.

### 6.5. Free Disk Space Is Also a Compaction Limit

Compaction must **read old SSTables and write new SSTables** before releasing the inputs; temporary space overhead depends on the strategy and active task. If the disk fills up, compaction fails and triggers a domino effect:

~~~text
Heavy writes -> many SSTables
             -> compaction needs extra disk space
             -> available disk drops
             -> compaction fails / backlog grows
             -> read amplification + latency rise
             -> retries spike -> load increases further
~~~

Load tests must enforce **disk headroom**, not just CPU/RAM checks. Never run stress tests to the point of filling disks on shared or production clusters.

## 7. Defining Measurement States: COLD, WARMING, STEADY, SATURATING, RECOVERING

| State | Indicators | Which KPIs Include It? |
|---|---|---|
| **COLD** | Fresh JVM/driver, few hot-key hits, unrepresentative caches | Cold-start latency / SLA |
| **WARMING** | Hit ratios, JIT/CPU, SSTables/flushes changing rapidly | Time-to-warm, transient cost |
| **STEADY** | Target throughput met; latency, errors, cache churn, backlog **not drifting** | Steady-state capacity / SLO |
| **SATURATING** | Queues/in-flight/disk await/backlog rise with p99 while QPS stalls | Saturation knee / capacity limit |
| **FAULTED** | Node/rack/latency failure, CL unmet or retries surging | Availability / failure window |
| **RECOVERING** | Node UP, but cold caches or elevated streaming/repair/compaction backlog | Recovery SLO, post-fault warm-up |
| **POST-RECOVERY STEADY** | CL/data oracle/SLOs and background work back in representative bounds | Return-to-service criteria |

**States can differ by query family and by node.** A hot partition on Node A may have a warm cache, while reads hitting Replica B or C after failover can behave as cold starts. Client pools on a newly started service pod can also be cold even while Cassandra replicas remain warm.

### 7.1. State Transitions and Confounding Factors

~~~text
COLD --warm workload--> WARMING --gate PASS--> STEADY
                             |                    |
                   compaction/backlog?           | fault
                             v                    v
                         SATURATING <-------- FAULTED
                             |                    |
                         backpressure             v
                             |                RECOVERING
                             |                    |
                             +----> STEADY <------+
                                       |
                               POST-RECOVERY REPORT
~~~

Do not label a window `STEADY` merely because **the configured warm-up timer elapsed**. Use sufficiently long observation windows and verify stability quantitatively.

### 7.2. Do Not Confuse "Cache Steady" with "Data Steady"

- Cache hit/miss temporarily stabilizes while ongoing writes still add SSTables and grow compaction backlog.
- Compaction backlog stabilizes while caches thrash because the working set exceeds RAM.
- Both cache and compaction are stable while the Java app experiences GC/JIT stalls or connection retries.
- Both client and server look stable only because CL was silently **lowered** below business requirements.

Therefore, a **steady-state gate** must be a conjunction of multiple conditions, never a single metric.

## 8. Designing a Steady-State Gate with Rolling Windows

### 8.1. An Illustrative Measurable Gate

Suppose a staging 70/30 read/write workload targets **2,000 logical CQL requests/s**, maximum p99 latency SLO of **80 ms**, CL `LOCAL_QUORUM`, and RF3 in one DC. The numbers below are **examples for learning how to construct gates**, not universal defaults for every cluster:

| Condition | How to Measure | Example Lab Threshold |
|---|---|---|
| Throughput | Completed requests/s by query mix | Within ±5% of target across **5 consecutive 60s windows** |
| Latency | p95/p99 per query family, sufficient histogram samples | p99 ≤ 80 ms; no upward drift across windows |
| Errors/timeouts | Errors, `UNAVAILABLE`, read/write timeouts, client timeouts | No abnormal spikes; business correctness errors = 0 |
| Key/row/chunk cache | Hit ratio, entries, evictions per node | Small variance / no heavy churn, or explicitly noted working set > cache |
| SSTables-per-read | Histogram/quartiles per table | Not climbing steadily across windows |
| Compaction backlog | Pending tasks/bytes, throughput, age | Not accumulating continuously; may remain > 0 |
| Memtable flush | Flush queue and bytes/s | Representative cycles; queue not growing unboundedly |
| Disk | Read/write IOPS, throughput, await, free space | Headroom intact, no sustained saturation |
| CPU/GC | CPU%, GC pauses, allocation | No pause/CPU saturation causing p99 spikes |
| Driver/client | Pool in-flight, retries, connection churn, JVM GC | Stable, request profile/CL unchanged |

**Verify adequate sample counts for p99.** If a query family has only 100 requests in a window, p99 is nearly a single extreme observation; do not report the same confidence as with 100,000 requests. For low-QPS classes, widen the window or report distributions/raw samples instead of forcing a noisy p99.

### 8.2. Evaluating "No Drift" Instead of a Single Snapshot

Suppose pending compactions over 5 minutes are:

~~~text
Window 1:  10
Window 2:  12
Window 3:  10
Window 4:  11
Window 5:  10
=> oscillates around a level; likely stable.

Window 1:  10
Window 2:  25
Window 3:  50
Window 4:  85
Window 5: 130
=> backlog accumulating; NOT steady yet.
~~~

Do not inspect `PendingTasks` alone; a 100 MB task and a 100 GB task differ enormously. Use **bytes remaining/throughput** where your version exposes them, combined with SSTable counts/levels, disk await, and p99 trends.

### 8.3. Rolling-Window Gates Avoid Periodic Artifacts

Flushes and compactions often occur in cycles. If you only sample a **30-second window right between compactions**, latency looks great yet misrepresents the next 10 minutes. Choose a measurement window covering **at least several operational cycles** expected from the workload and hardware; save the raw timeline alongside compaction start/finish markers.

Example:

~~~text
00:00-05:00  preload/cold state
05:00-11:00  warm-up
11:00-16:00  rolling steady gate
16:00-36:00  primary measurement
36:00-...    drain/recovery check

Use these milestones only if metrics confirm the expected state.
~~~

If a TWCS table uses daily windows or long TTLs, a 20-minute test cannot cover the full lifecycle. Document that **coverage gap** in the results.

### 8.4. Different Gates for Read-Heavy vs. Write-Heavy Workloads

**Read-heavy:** prioritize working-set coverage, page cache, key cache, SSTables-per-read, tombstones, and read p99.  
**Write-heavy:** prioritize sustained bytes/s, memtable flush cycles, commitlog latency, compaction backlog, disk free space, and write p99.  
**Mixed workload:** measure **both read and write p99**; a single combined metric can mask degrading read p99 while write throughput looks fine.

### 8.5. Sample Sufficiency and Uncertainty

Never compare p99 across two phases with significantly different request mixes. Record:

- **Count** and **duration** of each window.
- Histogram bins/precision and percentile tool (HDR Histogram, Prometheus histogram, driver timer).
- Scope: **client end-to-end** vs. **server coordinator**.
- Attempt/retry counts and timeouts (failed requests lacking a success latency may be omitted from success histograms).
- Whether the workload generator enforces an open-loop target rate or closed-loop "send as fast as possible".

A falling success-only p99 while **timeouts rise** is not a performance gain. Whenever slow requests time out and drop out of latency histograms, report **error rates and timeout counts** right alongside p99.

## 9. Working Set, Hit Ratio, and Hot-Key vs. Uniform-Key Differences

### 9.1. Working Set ≠ Total Table Size

The **working set** comprises the keys/partitions/pages accessed frequently enough within a window to influence caching. A 2 TB table can have a 2 GB hot working set; conversely, a 20 GB table queried uniformly across all rows/columns can force reading most of the dataset.

~~~text
Production:
  table size        = 1 TB
  top 1% partitions = 70% reads
  24h distinct PKs  = 4,000,000

Fake benchmark:
  table size        = 1 TB (fully seeded)
  100 fixed keys    = 100% reads
  ==> artificially high cache hit, artificially low p99
~~~

Seeding plenty of data **on disk** while querying only 100 keys still produces a "hot-cache-only" benchmark. Measure and generate **realistic key distributions**.

### 9.2. Uniform, Zipfian, and Churn

| Pattern | Characteristics | Consequence |
|---|---|---|
| Uniform random | Every key roughly equally likely | Lower hit ratio if working set is large |
| Zipfian/hotspot | Few keys read heavily | Clear cache and replica hotspots |
| Sequential/range | Adjacent keys or clustering slices | Prefetch/page locality differs from point reads |
| Temporal locality | Recently written keys are read soon after | Memtable/page cache makes queries fast |
| Churned hot set | Hot keys rotate hourly/daily | Yesterday's warm-up does not cover today |
| Multi-tenant skew | Large tenants dominate traffic | Partition hotspots, noisy neighbors |

**Never deliberately create one massive hot partition** just to "keep caches warm" and report cluster-wide throughput. That saturates a single replica set while leaving other nodes idle—which is a separate **hotspot failure** experiment.

### 9.3. Quick Estimate of Keys Touched

Suppose you run **m=300,000** independent uniform random point reads across **N=1,000,000 keys**. The expected number of distinct keys touched is approximately:

\[
E[D] = N\left(1-\left(1-\frac{1}{N}\right)^m\right)
\approx N\left(1-e^{-m/N}\right).
\]

Substituting numbers:

\[
E[D] \approx 10^6(1-e^{-0.3}) \approx 259{,}182.
\]

**Only about 26% of keys** have been touched even once under that model. You cannot claim "all 1 million keys are warmed" merely because you ran for 5 minutes at 1,000 reads/s. And that counts only keys—not index chunks/pages, nor datasets exceeding RAM.

### 9.4. When the Working Set Exceeds Available Memory

Example:

~~~text
Hot disk pages needed frequently: 40 GiB
Memory available for OS page cache: 16 GiB

No warm-up duration can keep all 40 GiB resident
in a 16 GiB cache sustainably.
~~~

The steady state here is **steady cache turnover/thrashing depending on access patterns**, measurable via stable hit/miss ratios and disk read rates. Do not "wait until hit ratio reaches 95%" when probability and memory capacity make it physically impossible.

### 9.5. Data Growth and TTLs Shift the Working Set

For time-bucketed tables, production workloads often favor "today" and "the last 7 days", whereas a test might seed all rows into an old date. TWCS, TTLs, and partition bucketing can completely skew results. Seed across realistic **event time, ingest time, and late arrivals** matching your query mix. Even when focusing on Cassandra's engine, test data must reflect the **query-driven wide-column model**.

## 10. Open-Loop vs. Closed-Loop: How Warm-Up Can Hide Saturation

### 10.1. Closed-Loop Clients

~~~text
N workers:
  send request
  wait for response
  then send next

Throughput is bounded by worker count and latency.
When Cassandra slows down, clients automatically send less.
~~~

Closed-loop tests help find maximum throughput at fixed concurrency, but suffer from **coordinated omission**: when the server stalls for 2 seconds, the generator stops issuing requests that real-time users would still have sent during those two seconds.

### 10.2. Open-Loop Arrivals

~~~text
Arrival schedule: 1000 requests/s regardless of latency
  t=0, 1ms, 2ms, ...

If the server slows down, queues/in-flight work grow.
Must enforce bounded queues, admission control, and deadlines.
~~~

Open-loop arrivals mirror time-based API QPS more closely, but without backpressure/rate caps they can overwhelm the cluster. Run them only under a staging capacity plan with **hard stops** and client queue metrics.

### 10.3. Little's Law Does Not Replace Mean with p99

In steady state, the average number of requests in service/waiting is:

\[
L = \lambda W
\]

where `λ` is average arrival/throughput rate and `W` is **average response time**. For example, at 1,000 req/s and 20 ms mean latency, `L ≈ 20` in-flight requests within the same measurement boundary. **Do not** plug in `p99 = 200 ms` to claim `L = 200` as an identity; p99 is a tail metric, not the mean.

If backlogs grow continuously, Little's Law's steady-state assumption no longer holds in practice. Measure queue growth and overload directly rather than using the formula to "prove capacity".

### 10.4. Remember Client-Side Limits

The Java application can bottleneck before Cassandra:

- JVM GC, thread pools / Netty event loops.
- Driver request throttler, connection pool in-flight limits, max streams, retries/speculation.
- Serialization/codecs, TLS/auth overhead.
- Load generator CPU or network/NIC saturation.
- Heavy logging/tracing.

Therefore, client **and** server warm-up must be measured separately. Low QPS is not automatically a compaction bottleneck; the load generator may have hit 100% CPU.

## 11. Metric Systems: You Must See Caches, SSTables, and Compaction

### 11.1. Measurement Sources

| Source | What It Captures | What Not to Conclude from It Alone |
|---|---|---|
| Load generator / JMeter / Gatling / NoSQLBench | Offered load, completed QPS, p50/p95/p99, errors | Do not treat as Cassandra-only latency |
| Java Driver 4.x metrics | Session CQL requests, per-node messages, pool in-flight, retries/client timeouts | Does not replace server compaction metrics |
| Cassandra JMX/Metrics | Read/write latency, key/row cache, memtables, SSTables-per-read, compaction, pending tasks | Does not know full HTTP business SLO |
| `nodetool info/tablestats/compactionstats/tpstats` | Point-in-time node/table/threadpool/task state | Does not replace continuous 1-minute histograms |
| Host metrics | CPU, RSS, GC, disk IOPS/await, page faults, network | Does not verify expected values or CL correctness |
| Business correctness probes | Read/write CL and data oracle | Does not measure cluster-wide saturation |

Never subtract **server coordinator latency** from **client p99** (which includes pooling, queueing, network, and retries) to compute network time. Percentiles from two separate sample sets **cannot be subtracted** to derive exact network latency.

### 11.2. Cassandra Metrics You Should Understand

| Group | Common Metric Names | Question It Answers |
|---|---|---|
| Cache | `KeyCacheHitRate`, `KeyCacheHits`, `KeyCacheRequests` | Are partition/index lookups hitting more, or only on a fake hot key? |
| Cache | `RowCacheHitRate`, `RowCacheHits` | Is row cache enabled? Do hits reflect real key distribution? |
| Cache | Chunk cache hit/miss/capacity (if exposed) | Is page/chunk cache warm or thrashing? |
| Table read | `ReadLatency`, `SSTablesPerReadHistogram` | Are read amp and tail latency moving together? |
| Table write | `WriteLatency`, memtable size / pending flushes | Is the write path stalling on flushes? |
| SSTables | `LiveSSTableCount`, live/total disk space | Are data/SSTables growing unboundedly? |
| Compaction | `PendingTasks`, `BytesCompacted`, active tasks, throughput | Are merges keeping pace with writes and TTL lifecycle? |
| Tombstones | Tombstone scanned histogram, warnings/failures | Is tombstone density causing read amplification? |
| Coordinator | ClientRequest Read/Write Latency, Timeouts, Unavailables | Are CL requests failing due to replicas? |
| JVM/host | GC pauses, CPU%, disk await, I/O bytes/s | Are caches and compaction competing for resources? |

**Metric naming note:** JMX MBeans live under `org.apache.cassandra.metrics` with scopes like `Cache`, `Table`, or `Compaction`, which often differ from Grafana/Prometheus exporter series names. Your Cassandra version, exporter, and configuration dictate which metrics actually exist. **Verify against live JMX/endpoints**; never write alerts referencing unexported series.

### 11.3. Non-Destructive `nodetool` Commands

~~~bash
# Only on authorized Cassandra lab/staging clusters
nodetool status
nodetool info
nodetool tablestats perf_lab.events_by_tenant_day
nodetool compactionstats
nodetool tpstats
nodetool netstats
nodetool gcstats
~~~

Meaning:

- `nodetool info` gives snapshot cache sizes/hits and node state.
- `nodetool tablestats` shows per-table SSTable counts, latencies, disk usage, bloom filters, and tombstone metrics (version-dependent).
- `nodetool compactionstats` shows active/pending compaction tasks and throughput.
- `nodetool tpstats` shows thread-pool active/pending/dropped messages.
- `nodetool status` shows ring/gossip state, not proof that data serves at the required CL.

These commands are **read-only observations** by intent; they do not replace continuous time-series collection. A snapshot showing 0 pending tasks after the test ends **does not** prove compaction did not spike p99 during the preceding 20 minutes.

### 11.4. Break Down Metrics by Node, Table, and Query Family

~~~text
query_family = events.byTenantDay
table        = perf_lab.events_by_tenant_day
CL           = LOCAL_QUORUM
DC           = dc1

client:
  request latency p99 / throughput / timeouts / retries

node A:
  key cache hit rate, SSTables-per-read, compaction bytes/s

node B:
  same metrics

node C:
  same metrics
~~~

If you inspect only Node A while hot partitions reside mostly on Nodes B and C, you misread cache state. At `LOCAL_QUORUM`, coordinators involve multiple replicas per request, so you need **per-node** charts and token distribution visibility.

### 11.5. Prometheus — Conceptual Example, Not Guaranteed Series Names

Assuming your exporter exposes specific counters and latency histograms, a report should compute:

\[
qps = \frac{\Delta \text{completed requests}}{\Delta t},\quad
timeoutRate = \frac{\Delta \text{timeouts}}{\Delta \text{requests}}.
\]

If a Prometheus histogram provides standard `*_bucket` series, you can use `histogram_quantile(0.99, sum by (le, query_family)(rate(..._bucket[5m])))`. However, Java Driver timers may be exported as summaries/snapshots or custom registries rather than Prometheus histograms. **Never copy hypothetical PromQL verbatim into production without verifying exported series.**

### 11.6. A Replayable Log Sample

~~~text
run_id=lab-2026-11-21-r1
phase=WARMING
query_family=events.byTenantDay
CL=ONE
target_rps=500
completed_rps=490
latency_p95_ms=18.1
latency_p99_ms=39.6
key_cache_hit_rate=0.74
sstables_per_read_p95=4
pending_compactions=12
disk_read_mb_s=80
disk_write_mb_s=45
gc_pause_ms_per_min=80
~~~

These numbers are **synthetic examples illustrating the format**, not real test outputs. In production, never log raw partition keys, user IDs, payment IDs, or PII; use low-cardinality labels (`query_family`/`CL`/`DC`/`status`) and controlled trace IDs.

## 12. What Should an Experiment Manifest Record?

### 12.1. Environment Section

~~~yaml
experiment:
  id: cassandra-warm-cache-v1
  purpose: compare cold_and_steady_reads
  environment: isolated_staging
  cassandra_version: "5.0.x"
  java_driver_version: "4.18.x"
  topology:
    dcs: {dc1: 3}
    full_rf: 3
    consistency_read: LOCAL_QUORUM
    consistency_write: LOCAL_QUORUM
  hardware:
    cpu_cores_per_node: 8
    memory_gib_per_node: 32
    disk_type: dedicated_ssd
    disk_headroom_target_percent: 30
  table:
    compaction: STCS
    compression: enabled
    row_cache: disabled
    keys: 5000000
    ttl: none
  workload:
    read_percent: 70
    write_percent: 30
    access_distribution: zipf_like
    target_rps: 2000
    page_size: 100
    bounded_inflight: true
  phases:
    baseline_seconds: 120
    warmup_minimum_seconds: 300
    warmup_maximum_seconds: 1800
    steady_window_seconds: 60
    steady_windows_required: 5
    measure_seconds: 1200
  checks:
    record_cache_metrics: true
    record_sstable_and_compaction_metrics: true
    verify_data_oracle: true
    abort_on_disk_pressure: true
~~~

This is an **illustrative manifest in Markdown**, not a standard Cassandra config or a file you must create. Values must be tailored to your cluster, SLOs, active dataset, and operational permissions; never treat `30% disk headroom` as a universal rule across different compaction strategies or deployments.

### 12.2. Variables That Must Remain Constant in A/B Comparisons

| Group | Keep Constant or Report Separately |
|---|---|
| Topology | Node count, DC/rack, RF, CL, token ownership |
| Software | Cassandra, JDK, driver, JVM flags, GC, OS/kernel |
| Hardware | CPU/RAM/storage class, noisy neighbors, network |
| Cassandra | Memtable/commitlog/cache sizes, compaction strategy, compression |
| Dataset | Partition count, rows/partition, bytes/row, TTL, tombstones, timestamp age |
| Workload | Query mix, QPS schedule, concurrency, key distribution, page size |
| Timeline | Preload/flush/compaction, warm-up start, measurement, fault, recovery |
| Metrics | Histogram backend, sampling resolution, error handling |
| Driver | Consistency, timeouts, retries, speculative execution, pooling |
| State | Cold/warm cache, SSTable count/levels, pending compactions |

Even with only one variable changed, you still must measure **run-to-run variance**. Randomize A/B order or run multiple repetitions from a verified reset state; avoid always running B right after A when B inherits A's warm caches.

### 12.3. Prefer a Stabilized Seeded Dataset

If the goal is comparing **read latency**, seed the dataset first, allow data and compaction to reach the target state, and then warm up reads. If measuring **mixed read/write steady state**, keep writes running throughout the measurement window and include compaction as part of the workload—do not stop writes until compaction drains before measuring reads.

Two distinct questions:

~~~text
Q1: How fast is a read-only query on a settled dataset?
Q2: How fast is the same query while continuous writes/flushes/compactions run?
~~~

You cannot answer Q2 by running Q1 and appending a few seconds of writes at the end.

## 13. Standard Experiment Phasing: Preflight → Seed → Warm → Measure

### 13.1. Preflight Gate

- Confirm the environment is **not production**, with an explicit owner and stop authority.
- Verify cluster nodes are `UN` (or expected degraded mode) with no unplanned bootstrap/repair running.
- Lock RF/CL/table schema/compaction strategy and driver local DC.
- Confirm free disk space, CPU/memory, traffic isolation, and generator capacity.
- Capture baseline errors/timeouts/retries/GC, table SSTable counts, caches, and compaction backlog.
- Verify query correctness on known-key sentinels, not just `SELECT system.local`.
- Ensure a kill switch, rate cap, bounded in-flight limits, and abort alerts for disk/latency degradation.

### 13.2. Seed / Preload

1. Generate data with realistic partition cardinality, timestamps, and TTLs—not a single hot partition.
2. Verify row counts via **source manifest / sampled known keys**, not hours-long full-table `COUNT(*)`.
3. Observe flushes, SSTable creation, and compaction during seeding.
4. Wait for or document **preload stabilization** before target measurements.
5. Snapshot metrics before starting warm-up.

### 13.3. Warm-Up with the Real Query Mix

1. Start the generator at a **controlled rate**, e.g., ramping 20% → 50% → 100% of target.
2. Use the representative hot/cold key distribution and read/write mix.
3. Measure **client app JVM/driver**: prepared statements, pools, JIT, GC.
4. Measure **Cassandra replicas**: cache hits/churn, disk reads, SSTables-per-read.
5. Measure **write path**: flush/compaction backlog across multiple windows.
6. Proceed to measurement only after the steady-state gate PASSES; if the max warm-up budget expires without passing, report **`NOT_STEADY`** rather than hiding the numbers.

### 13.4. Measurement

~~~text
Warm-up gate PASS
   |
Start measurement window + mark timestamp
   |
Keep target distribution/rate and CL unchanged
   |
Collect p50/p95/p99 + successes/errors/timeouts
   |
Collect node/cache/flush/SSTable/compaction metrics
   |
Collect data-correctness canaries
   |
Stop generator safely at end
   |
Continue observing backlog drain if relevant
~~~

**Do not switch from 500 RPS / 100 hot keys during warm-up to 5,000 RPS / 1 million keys at measurement start** and assume caches are appropriately warm. If your goal is studying a *cold-miss shock*, explicitly label it as a transition measurement.

### 13.5. Comparing Phases by Timestamps and Raw Data

Keep phases separated:

~~~text
boot_phase.csv
seed_phase.csv
warmup_phase.csv
steady_phase.csv
fault_phase.csv
recovery_phase.csv
~~~

These filenames are **illustrative of how to separate results**, not a requirement to create files in the repository. You can use Prometheus recording rules, time-range tags, or test harness metadata equivalently. Never delete warm-up metrics simply because they look worse; report them under cold/warm/recovery sections for transparency.

## 14. Lab A — CQL: Hot Partition vs. Diverse Partition Set

**Goal:** Create a small dataset illustrating **hot-key repetition** and **distributed reads**, verifying query correctness before measuring latency. This lab **does not contain enough data to benchmark OS page cache or compaction**: 16 rows can fit inside a single memory page and do not represent GB/TB workloads. Later stress/soak sections address real load testing.

### 14.1. Environment

- Apache Cassandra 4.1 or 5.0, **single-node lab**.
- `cqlsh` and permission to create an isolated keyspace/table; never use a production keyspace.
- Java Driver 4.x if running Lab B.
- Use `ONE` on RF1; testing RF3/`LOCAL_QUORUM` requires a real multi-node fixture.
- Do not run multiple competing load generators on a weak dev laptop and call the result "Cassandra capacity".

### 14.2. Create a Simple Schema with the Right Partition Key

~~~sql
CREATE KEYSPACE IF NOT EXISTS perf_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS perf_lab.events_by_tenant_day (
  tenant_id text,
  event_day date,
  event_id uuid,
  status text,
  score int,
  received_at timestamp,
  PRIMARY KEY ((tenant_id, event_day), event_id)
) WITH CLUSTERING ORDER BY (event_id ASC)
  AND compaction = {
    'class': 'SizeTieredCompactionStrategy'
  };

CONSISTENCY ONE;
~~~

**Model:** `(tenant_id, event_day)` is the composite partition key and `event_id` is the clustering key. Perform point lookups and in-partition range reads, avoiding `ALLOW FILTERING` during warm-up comparisons so full scans are not mixed with cache effects. STCS is chosen **for this lab**, not as a universal default recommendation for every workload.

### 14.3. Seed 8 Rows in One Hot Partition

~~~sql
INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000001,'OK',1,
        '2026-11-21T00:00:01Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000002,'OK',2,
        '2026-11-21T00:00:02Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000003,'OK',3,
        '2026-11-21T00:00:03Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000004,'OK',4,
        '2026-11-21T00:00:04Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000005,'OK',5,
        '2026-11-21T00:00:05Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000006,'OK',6,
        '2026-11-21T00:00:06Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000007,'OK',7,
        '2026-11-21T00:00:07Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-hot','2026-11-21',
        00000000-0000-0000-0000-000000000008,'OK',8,
        '2026-11-21T00:00:08Z');
~~~

### 14.4. Seed 8 Rows Across 8 Distinct Partitions

~~~sql
INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-01','2026-11-21',
        00000000-0000-0000-0000-000000000001,'OK',101,
        '2026-11-21T00:01:01Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-02','2026-11-21',
        00000000-0000-0000-0000-000000000002,'OK',102,
        '2026-11-21T00:01:02Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-03','2026-11-21',
        00000000-0000-0000-0000-000000000003,'OK',103,
        '2026-11-21T00:01:03Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-04','2026-11-21',
        00000000-0000-0000-0000-000000000004,'OK',104,
        '2026-11-21T00:01:04Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-05','2026-11-21',
        00000000-0000-0000-0000-000000000005,'OK',105,
        '2026-11-21T00:01:05Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-06','2026-11-21',
        00000000-0000-0000-0000-000000000006,'OK',106,
        '2026-11-21T00:01:06Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-07','2026-11-21',
        00000000-0000-0000-0000-000000000007,'OK',107,
        '2026-11-21T00:01:07Z');

INSERT INTO perf_lab.events_by_tenant_day
  (tenant_id,event_day,event_id,status,score,received_at)
VALUES ('tenant-08','2026-11-21',
        00000000-0000-0000-0000-000000000008,'OK',108,
        '2026-11-21T00:01:08Z');
~~~

### 14.5. Two Query Patterns to Compare

~~~sql
-- Point lookup (hot key; try calling the same statement repeatedly)
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-hot'
  AND event_day = '2026-11-21'
  AND event_id =
      00000000-0000-0000-0000-000000000001;

-- Bounded partition range/scan
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-hot'
  AND event_day = '2026-11-21'
LIMIT 8;

-- Another partition (cycling through tenant-01..08)
SELECT event_id, status, score
FROM perf_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-08'
  AND event_day = '2026-11-21';
~~~

**Expected:** Point lookup returns `score=1`; hot-partition range returns 8 rows; `tenant-08` returns one row with `score=108`. If not, **stop the benchmark first**: never compare latencies of broken queries. And never combine point lookups and range scans into a single p99.

### 14.6. Note on Caching with a Small Dataset

With 16 rows, the working set is almost certainly too small to distinguish physical disk cold vs. warm reliably. Use this lab strictly to practice:

- Keeping statement/query family and CL consistent.
- Separating hot-key vs. colder-key **distributions** without making physical-cache claims.
- Verifying CQL shape, partition keys, and expected values.
- Understanding why real benchmarks need **millions of partitions and GBs of data** to generate representative cache misses.

Never run `nodetool invalidatekeycache`, shrink cache capacity, drop OS page caches, or restart nodes on a shared cluster just to make a 16-row experiment "cold".

## 15. Lab B — Java Driver 4.x: Bounded Warm-Up and Point-Read Measurement

### 15.1. Goals and Principles

The following Java 17 example **does not benchmark capacity**. It shows learners how to:

1. Prepare CQL once and reuse a single `CqlSession` throughout.
2. Keep the exact same query shape across requests.
3. Verify row/score correctness rather than silently timing empty responses.
4. Separate the **warm-up loop** from the **measurement loop** and record p50/p95/p99 latencies.
5. Run two clearly controlled access patterns.

On a tiny lab, p99 is mostly JIT, OS scheduler, and Java overhead noise—never call it "production Cassandra p99". For real load testing, run representative concurrency, dataset size, and duration using proper histograms with sample counts and saturation metrics.

### 15.2. Complete Java 17 Program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.Arrays;
import java.util.UUID;

public final class CassandraWarmupLab {
    private CassandraWarmupLab() {}

    static final LocalDate DAY = LocalDate.parse("2026-11-21");
    static final UUID HOT_ID = UUID.fromString(
        "00000000-0000-0000-0000-000000000001");

    record Stats(String name, int samples,
                 double p50Ms, double p95Ms, double p99Ms,
                 double maxMs) {}

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            PreparedStatement point = session.prepare(
                "SELECT score FROM perf_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? " +
                "AND event_id = ?");

            // Pattern A: intentional hot key, warm up then measure.
            BoundStatement hot = point.bind(
                    "tenant-hot", DAY, HOT_ID)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);

            warm(session, hot, 500);
            Stats hotStats = measure(
                "hot-point-read", session, point, true, 1000);
            System.out.println(hotStats);

            // Pattern B: cycles across 8 distinct partitions,
            // still FAR TOO SMALL a dataset for a cache benchmark.
            warmVaried(session, point, 500);
            Stats variedStats = measure(
                "varied-point-read", session, point, false, 1000);
            System.out.println(variedStats);

            System.out.println(
                "Do not compare as real cold-vs-warm capacity");
        }
    }

    static BoundStatement select(
            PreparedStatement p, boolean hot, int i) {
        if (hot) {
            return p.bind("tenant-hot", DAY, HOT_ID)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setIdempotent(true);
        }

        int id = i % 8 + 1;
        String tenant = String.format("tenant-%02d", id);
        UUID eventId = UUID.fromString(String.format(
            "00000000-0000-0000-0000-%012d", id));
        return p.bind(tenant, DAY, eventId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setIdempotent(true);
    }

    static void warm(
            CqlSession s, BoundStatement b, int iterations) {
        for (int i = 0; i < iterations; i++) {
            Row row = s.execute(b).one();
            if (row == null || row.getInt("score") != 1) {
                throw new IllegalStateException(
                    "Wrong hot key/value during warmup");
            }
        }
    }

    static void warmVaried(
            CqlSession s, PreparedStatement p, int iterations) {
        for (int i = 0; i < iterations; i++) {
            Row row = s.execute(select(p, false, i)).one();
            int expected = i % 8 + 101;
            if (row == null || row.getInt("score") != expected) {
                throw new IllegalStateException(
                    "Wrong varied key/value during warmup");
            }
        }
    }

    static Stats measure(
            String name, CqlSession s, PreparedStatement p,
            boolean hot, int iterations) {

        long[] nanos = new long[iterations];
        for (int i = 0; i < iterations; i++) {
            BoundStatement req = select(p, hot, i);
            long t0 = System.nanoTime();
            Row row = s.execute(req).one();
            nanos[i] = System.nanoTime() - t0;

            int expected = hot ? 1 : (i % 8 + 101);
            if (row == null || row.getInt("score") != expected) {
                throw new IllegalStateException(
                    "Data oracle failed during measurement");
            }
        }

        Arrays.sort(nanos);
        return new Stats(name, iterations,
            nthMs(nanos, 0.50), nthMs(nanos, 0.95),
            nthMs(nanos, 0.99), nanos[iterations - 1] / 1e6);
    }

    static double nthMs(long[] sorted, double percentile) {
        int index = Math.max(0, Math.min(sorted.length - 1,
            (int) Math.ceil(percentile * sorted.length) - 1));
        return sorted[index] / 1e6;
    }
}
~~~

### 15.3. How to Read the Lab Output

Hypothetical output:

~~~text
Stats[name=hot-point-read, samples=1000,
      p50Ms=1.8, p95Ms=3.1, p99Ms=5.5, maxMs=9.1]
Stats[name=varied-point-read, samples=1000,
      p50Ms=2.0, p95Ms=3.8, p99Ms=6.7, maxMs=13.0]
Do not compare as real cold-vs-warm capacity
~~~

These numbers are **format examples only**, not an executed benchmark. Even if hot reads look faster than varied reads, you cannot attribute it solely to caching or compaction because Java allocations (`String.format`/`UUID.fromString`), network scheduling, and key placement also differ. Production benchmarks require a proper workload harness, sufficient histogram samples, identical offered load, and CPU/RAM/I/O metrics.

### 15.4. Why Synchronous Code Is Pedagogical but Does Not Measure Max Throughput

The loop above sends **one request and waits for completion**—closed-loop concurrency ≈ 1. It works well for teaching **warm-up vs. measurement and data correctness**, yet cannot exercise saturation knees, pool backpressure, or concurrent compactions under heavy load. Production Java applications typically need:

- `executeAsync` with appropriate in-flight/backpressure bounds.
- Reused prepared statements and typed CQL values.
- Histograms/timers tagged by **query family**, never raw user IDs.
- Load generators isolated from Cassandra hosts so they do not contend for CPU/disk.
- Production CL/RF/DC settings rather than extrapolating from an RF1/`ONE` lab.

### 15.5. A Measurement Trap in the Demo Code

The code measures **from right before `session.execute` until the row arrives**, including Java result handling, network, driver, and coordination. It does **not** isolate pure server SSTable read time, and it excludes `BoundStatement` construction before `t0`. For client end-to-end timing, decide whether to start at HTTP arrival or after binding, and document the scope. For paginated queries, measure "first page" and "full result" separately.

## 16. Lab C — `cassandra-stress`: Workloads with Clear Durations and Phases

### 16.1. What Is the Tool Used For?

`cassandra-stress` supports write/read/mixed workloads on a tool-generated schema as well as **user mode** for custom schemas, offering `-pop`, `-rate`, `-node`, `-schema`, `-sample`, and latency reporting options. In Cassandra 5.0 documentation, this tool is marked **deprecated**, and Apache recommends **NoSQLBench** as the preferred choice for new Cassandra benchmarks. See [Cassandra Stress — Apache Cassandra](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html).

Accordingly:

- **Simple/legacy labs:** `cassandra-stress` is handy for learning data loading, warm-up, and histogram interpretation.
- **Serious benchmarks:** prefer NoSQLBench or a generator aligned with your query model/Java app, pinning versions, workload specs, and metric backends.
- **Regardless of tool:** keep dataset, CL, key distribution, QPS, phase markers, and server metrics consistent across A/B comparisons.

### 16.2. Check Version Help Before Running

~~~bash
cassandra-stress help
cassandra-stress help write
cassandra-stress help read
cassandra-stress help mixed
cassandra-stress help -rate
cassandra-stress help -pop
~~~

**This step is mandatory:** flags and sub-options vary between Cassandra versions. Never copy a 3.x command into Cassandra 5.x without inspecting `help` output. When using passwords, TLS, or JMX, pass `-mode`/`-transport`/`-credentials-file` per your running version's docs, and **never hardcode secrets into shell history**.

### 16.3. Illustrative Command Sequence on an Isolated Lab

~~~bash
# 1. Generates data only in the tool-managed stress schema/keyspace.
#    NEVER target production nodes.
cassandra-stress write n=100000 \
  -rate threads=16 \
  -node 127.0.0.1

# 2. Warm read: same key population created in step 1.
cassandra-stress read duration=5m \
  -pop dist=UNIFORM(1..100000) \
  -rate threads=16 \
  -node 127.0.0.1

# 3. Measure read with identical distribution + concurrency.
cassandra-stress read duration=10m \
  -pop dist=UNIFORM(1..100000) \
  -rate threads=16 \
  -node 127.0.0.1
~~~

**Explanation:**

- These commands are **illustrative syntax examples**; verify against your tool's actual `help`. `UNIFORM(1..100000)` produces more cache misses than a fixed hot key, yet still may not represent production.
- `n=100000` caps seeded operation count; `duration=5m`/`10m` bounds run duration.
- `-rate threads=16` bounds tool concurrency; it **does not hold completed QPS fixed** if the backend slows down. To target an RPS, use throttling/rate flags supported by your tool version.
- Seed and read runs might not touch the exact same key set if generator/schema/options differ; verify row/key populations and correctness.
- By default, `cassandra-stress` **does not model `perf_lab.events_by_tenant_day`**. It uses its own schema unless configured in user mode, so never treat default outputs as an application query benchmark.
- **Never** treat `-pop` as simulating RF or CL; it defines key distribution. RF/CL must be configured via schema/options and explicitly verified.

### 16.4. Why Must You Watch Compaction Across All Three Steps?

~~~text
WRITE/SEED:
  disk writes and memtable flushes rise
  -> SSTable count/compaction backlog changes

WARM READ:
  key/OS caches gradually populate hot keys
  -> meanwhile compaction from SEED may still be running

MEASURE READ:
  to measure "read-only steady", know what compaction remains,
  never assume compaction stopped just because writes stopped.
~~~

If seeding ends immediately before measurement, a "cold vs. warm read" test may actually compare **reads during active compaction vs. reads after compaction finishes**. To isolate cache effects, keep compaction/I/O state comparable or explicitly document the confounder.

### 16.5. User Mode vs. Built-In Schema

To stress your application's actual CQL/partition model, use a supported **user profile** (YAML) defining:

~~~yaml
specname: events_profile
keyspace: perf_lab
table: events_by_tenant_day
# column specifications and query bindings depend on your schema:
queries:
  by_tenant_day:
    cql: "SELECT event_id, status FROM events_by_tenant_day WHERE tenant_id = ? AND event_day = ?"
    fields: samerow
~~~

This snippet **only illustrates the concept**: a complete profile also requires `columnspec`, data generators, and insert definitions matching your column types and stress version; it is **not a runnable file as-is**. Build and validate a proper user profile in the lab, seed data first, and then run the workload. Do not create extra profile files inside this Markdown exercise.

**Safety warning:** Some online stress examples include `truncate=once` in user mode; that **wipes the entire table** and must never be copied onto shared or production keyspaces. Use it only on dedicated, intentionally disposable lab tables.

### 16.6. Value of `cassandra-stress` and Limitations to State in Reports

| Useful For | Does Not Prove on Its Own |
|---|---|
| Seeding/loading large volumes into the stress schema | Application query model has the same partition shape |
| Measuring throughput/latency under concurrency/rate limits | End-to-end Java service SLOs |
| Testing read population distributions | Production-accurate data/time/TTL/tombstones |
| Controlling warm-up vs. measurement durations | That caches/compaction actually reached steady state |
| Controlled version/strategy comparisons | Production-wide tenant/token/rack fault tolerance |

## 17. Designing a Warm-Up and Compaction Dashboard

### 17.1. Charts That Should Share the Same Time Axis

Panel A — Offered RPS / Completed QPS / Errors / Timeouts.  
Panel B — App p50/p95/p99 by query family and CL.  
Panel C — Java Driver logical `cql-requests`, node `cql-messages`, retries.  
Panel D — Key cache / row cache / chunk cache hits-misses, entries/evictions.  
Panel E — SSTables-per-read, live SSTables, tombstones scanned.  
Panel F — Memtable / flush pending, compaction pending / active bytes.  
Panel G — Disk read/write MB/s, IOPS/await, free space.  
Panel H — CPU/GC, Netty pool in-flight, queues, network.  
Panel I — Event markers: SEED/WARM/STEADY/FAULT/RECOVER.

This is a **dashboard layout sketch**, not a request to create dashboard files. Related panels must share the **exact same time window**, otherwise it is hard to see which compaction coincided with a p99 spike.

### 17.2. Distinguish Gauges, Counters, and Histograms

| Metric Type | Examples | How to Compute / Interpret |
|---|---|---|
| Counter | `BytesCompacted`, total requests | Use `rate`/`increase` over time; never read raw totals as QPS |
| Gauge | `PendingTasks`, memtable size, disk free | Track level and slope/trend |
| Histogram/timer | `ReadLatency`, driver `cql-requests` | Percentiles/quantiles with counts and proper buckets |
| Ratio | Key cache hits / requests | Use identical time windows, filter by read ops, avoid tiny-sample division |
| Derived trend | SSTable count slope, backlog growth | Stable oscillation vs. continuous accumulation |

For instance, `BytesCompacted = 5 TB` is a cumulative counter since node startup, **not** 5 TB compacted in the last 5 minutes. Compute deltas over timestamps and handle counter resets on process restarts.

### 17.3. Good p99 While the System Quietly Degrades

~~~text
Window       QPS    p99 read   PendingCompactions  Disk free
  1          2000     50ms          15               43%
  2          2000     53ms          40               40%
  3          2000     57ms          80               36%
  4          2000     65ms         150               31%
  5          2000     78ms         240               26%

SLO p99 <= 80ms: approaching breach.
Yet state is NOT STEADY because backlog is growing rapidly.
~~~

This is **hypothetical data** for illustration. Inspecting only the last 5 minutes might earn a temporary PASS, yet 30 minutes later the node hits its limits. Forecast and alert on **trends**.

### 17.4. Did Latency Rise Because of Cache Misses or Compaction?

| Evidence | Points Toward Cache Misses | Points Toward Compaction Pressure |
|---|---|---|
| Key/OS cache hits | Drops sharply as working set expands | May stay stable |
| Disk read I/O | Spikes alongside cache misses | May rise due to compaction reads |
| Disk write I/O | Need not rise | Typically rises due to SSTable rewrites |
| Pending compactions | May stay unchanged | Usually rises, or active bytes/s is high |
| SSTables-per-read | May stay stable | Can rise before compaction or drop after merge |
| Read p99 | Rises as misses hit disk | Rises from disk/CPU contention |
| Writer throughput | Need not change | May drop as flushes/compaction contend for I/O |

Never diagnose from **one** metric alone. Compaction can also **evict the OS page cache**, causing cache misses and compaction pressure **simultaneously**. Correlate on a shared timeline and run controlled A/B tests.

## 18. Never Force a "Cold Cache" with Destructive Actions on Shared Clusters

### 18.1. Common Misconceptions About Forcing Cold State

| Action | Problem |
|---|---|
| Restart Java service | Cools JVM/driver; Cassandra and host page cache may remain warm |
| Restart Cassandra process/container | JVM caches may reset; host OS page cache may persist |
| Reboot dedicated host | Clears OS page cache, but changes many variables (boot, I/O, gossip) |
| Disable key/row cache | **Changes config/algorithm**, rather than merely cooling state |
| Linux `drop_caches` | Host-wide impact affecting other processes; unrepresentative of steady production |
| `nodetool invalidatekeycache`/`invalidate...` | Artificially alters cache state unlike natural workloads |
| `nodetool compact` | Forces rewrite/I/O, alters SSTable layout and page cache; not a neutral warm step |
| `TRUNCATE` and re-seed | Alters data, SSTables, TTLs, timestamps; risks data loss |

**Never run** cache invalidations, host `drop_caches`, node restarts/kills, compaction strategy flips, or `TRUNCATE` on shared or production clusters merely to "measure cold".

### 18.2. Safer Alternatives

**Option A — Measure natural cold start:** Capture a timeline on a **freshly provisioned lab cluster** using a clear snapshot/seed manifest; accept that all layers start cold, because that matches an actual RTO scenario.

**Option B — Small vs. large cache residency:** Compare a **working set fitting in RAM** against a **working set larger than RAM** on a lab cluster with identical schema, disks, and CL; use cache hits and disk reads to explain the difference.

**Option C — Workload shift:** Create two non-overlapping partition key sets, switch from set A to set B at a marker timestamp, and measure transient p99 and time-to-new-steady—without flushing the entire host's page cache.

**Option D — App-only restart:** Restart the load generator/client service in the lab while leaving Cassandra untouched to isolate JIT/driver warm-up.

### 18.3. Do Not Call Option C "100% Cold OS Cache"

Two disjoint key sets do not guarantee disjoint SSTable/index file pages, especially when keys share SSTables or index summaries. Describe it accurately as a **controlled working-set shift** and verify with physical disk/cache metrics, rather than claiming a full page-cache flush.

## 19. Fault Testing: A Node Returning UP Does Not Mean Cache/Compaction Have Recovered

### 19.1. Report Two Recovery Times Separately

After a node or network link recovers:

1. **Functional recovery:** Queries at the required CL begin succeeding and the data oracle passes.
2. **Performance recovery:** p95/p99, retries, cache hits/churn, flush/compaction backlog, and disk resources return to the recognized SLO/steady band.

These two milestones can differ by minutes or more. A node showing `UN` and a successful `ONE` read **does not** prove `LOCAL_QUORUM` read p99 has returned to baseline.

Define milestones:

\[
RTO_{\mathrm{CL}} =
t_{\mathrm{first\ sustained\ CL\ success}}-t_{\mathrm{fault\ onset}},
\]

\[
RTO_{\mathrm{perf}} =
t_{\mathrm{steady\ gate\ recovered}}-t_{\mathrm{fault\ removed}}.
\]

**Notice the reference points!** Reports must explicitly state whether RTO is measured from fault onset, failover start, or fault removal. Never mix the two numbers or claim full recovery prematurely.

### 19.2. Example: One Node Lost in RF3 at `LOCAL_QUORUM`

~~~text
dc1 RF3, natural replicas A/B/C
CL LOCAL_QUORUM = 2

Warm baseline:
  A/B/C UP
  hot keys cached across A/B/C
  read p99 = 25ms

Fault:
  C unavailable
  A/B still satisfy quorum
  read p99 = 55ms, retries/queues rise

Recovery:
  C UP/UN, needs catch-up (hints/repair/streaming per scenario)
  C's cache and local disk I/O differ from baseline
  compaction/repair compete for disk
  read p99 = 90ms temporarily

Post-recovery steady:
  data oracle at LOCAL_QUORUM PASS
  p99 stabilizes back within SLO
  backlog no longer growing
~~~

These p99 numbers are **illustrative assumptions**. Do not assume every node failure raises p99 uniformly; if Node C did not serve hot keys or quorum queries happened to pick A/B, the impact may look very different.

### 19.3. Controlled Failure Matrix

| Fault | What Can Cool Down or Shift | Mandatory Observations | Safety Boundary |
|---|---|---|---|
| Restart **Java service** | JIT, driver pools, prepared caches | Client p99, connection churn, node messages | Dedicated staging service only |
| Restart one **Cassandra process** | Server JVM/JIT/caches, gossip/pools, commitlog replay | CL availability, Cassandra GC/caches, data oracle | Dedicated fault lab cluster only |
| Reboot **host** | OS page cache and many system variables | Cold start + disk I/O + quorum | High risk; dedicated lab/approval |
| Inject network latency to one node | Retry/CL selection, in-flight count | Timeouts, data correctness, tail latency | Fault proxy/throttling in lab |
| Stop one natural replica | Quorum headroom, coordinator routing | Unavailable/timeouts per token/DC | Never on production |
| Heavy write surge | Memtable/flush/compaction | Pending tasks/bytes, disk p99 | Hard rate cap / abort limit |
| Run staging repair | Streaming/anticompaction/disk/GC | Data oracle, backlog, `RTO_perf` | Dedicated owner/runbook |
| Shift hot-key distribution | Cache residency, hotspots | Cache misses, read p99, token skew | Can run without killing nodes |

**Fault injection does not always require taking a node DOWN.** Shifting from hot working set A to B can test cache-warm recovery without touching topology. When testing CL availability under node failure, verify the **natural replicas** of probe keys; stopping a node outside that replica set may produce zero errors.

### 19.4. Safe Fault-Testing Workflow

~~~text
Preflight:
  isolated staging + permissions + rollback owner
  RF/CL known, representative token keys
  disk/CPU/network headroom
  rate/timeout/in-flight hard limits
  health checks and data oracle baseline
      |
Steady-state gate PASS
      |
Mark T_fault_onset and inject ONE fault
      |
Observe CL success/errors/retries/p99, resources
      |
Mark T_fault_removed
      |
Wait for node/ring/streaming/repair as appropriate
      |
Observe cache/flush/SSTable/compaction recovery
      |
Post-recovery steady-state gate PASS or timeout
      |
Restore original configuration and archive evidence
~~~

**Never change multiple variables at once** (e.g., killing a node, altering RF, and increasing load 10×) if your goal is isolating why p99 shifted. Test one fault class at a time against a control baseline.

### 19.5. Consistency and Unknown Write Outcomes During Fault Tests

A `WriteTimeoutException`/`DriverTimeoutException` can occur after the coordinator already forwarded the mutation to some replicas. Never count every timeout as a "guaranteed failed write" and blindly replay it with a new UUID, creating duplicate business records.

Fault tests require:

- A stable operation/event ID for every logical write.
- A data oracle / post-fault and post-repair reconciliation at the proper CL.
- Separate tracking of `acknowledged`, `unknown`, `reconciled`, and `failed-confirmed`.
- Never enabling speculative execution on counters, list appends, or non-idempotent writes.
- Never treating lower error rates achieved by **lowering CL** as benchmark improvement.

### 19.6. Keep Measuring Compaction After Recovery

A node can come back UP and satisfy `LOCAL_QUORUM`, yet still process received hints/streamed data requiring flushes and compaction. Stopping telemetry the instant `nodetool status` flips to `UN` **misses the recovery cost**. Keep monitoring until:

1. Data oracle passes on representative keys.
2. Read/write p99 and timeouts remain within target bounds across consecutive windows.
3. Compaction/flush backlogs are not accumulating.
4. Free disk, await, and GC retain headroom without abnormal drift.
5. No unaccounted streaming, repair, or decommissioning remains active.

## 20. A/B Compaction/Cache Testing: Avoiding False Conclusions

### 20.1. Both Variants Need Clear Controls

Suppose you want to compare STCS and LCS on a read-heavy workload:

~~~text
Cluster A:
  STCS, dataset S, RF3, LOCAL_QUORUM
  Java load Q, partitions/TTL distribution D

Cluster B:
  LCS, dataset S, RF3, LOCAL_QUORUM
  Java load Q, partitions/TTL distribution D

Primary differing variable:
  compaction strategy

Measure:
  steady read p99, write p99, CPU, disk I/O,
  SSTables-per-read, compaction bytes, disk space, RTO
~~~

True **identical A/B clusters** are hard to achieve if hardware, data history, SSTable layout, compaction timing, and OS caches differ. When testing sequentially on the same cluster, enforce a verified **reset-to-baseline procedure**. Altering compaction strategy via `ALTER TABLE` and measuring immediately often measures the **transient rewrite backlog**, not the strategy's steady state.

### 20.2. Pre-Conclusion Questionnaire

| Question | If the Answer Is "Unknown" |
|---|---|
| Did both run the same QPS/mix/CL/RF? | Cannot attribute differences to strategy |
| Are datasets identical in rows/TTL/tombstones? | Data-shape confounder present |
| Did both A and B complete representative flush/compaction cycles? | May have measured startup regime only |
| Were cache hits/misses and OS disk reads comparable or reported separately? | Uncontrolled cache bias |
| Did SSTable count/levels/overlap reach the expected regime? | Strategy had not stabilized |
| Did compaction backlog stay non-drifting during measurement? | Throughput may be unsustainable |
| Did p99 have sufficient samples and matching histogram precision? | Percentile comparison lacks statistical confidence |
| Were errors/timeouts/retries accounted for? | Clean numbers may reflect dropped failures |
| Were runs repeated or order randomized? | Results may reflect run order or host noise |
| Were data correctness and CL preserved? | Never trade consistency for latency |

### 20.3. Capture Baselines at Multiple Milestones

~~~text
B0: before seed
B1: after seed/preload stabilization
B2: after cache warm-up gate
B3: steady measurement end
B4: after fault removed (if applicable)
B5: after post-recovery steady gate
~~~

If compaction bytes or write MB/s differ sharply between B2 and B3, a 2-minute window is likely too short. Report the full evolution, not merely average latency.

### 20.4. Should You Disable Compaction to "Measure Read Cache in Isolation"?

**Not recommended** as a representative performance measurement. Disabling auto-compaction grows SSTable counts and distorts read amplification and capacity dynamics; re-enabling it later can unleash a **compaction storm** unlike normal operation. Only do this in **dedicated lab experiments** designed to isolate mechanics, with snapshots/rollback and ample disk headroom—never on production.

### 20.5. A/B Tests Must Report the Cost of Speed

One strategy might:

- Lower read p99 while increasing write I/O/CPU and compaction bytes.
- Reduce disk space amplification while increasing write amplification.
- Excel at hot-cache point reads while suffering on uniform scans.
- Perform well in steady state while taking longer to recover after faults.

Never crown a "winning strategy" just because one SELECT's p99 dropped by 10%. Weigh **read/write SLAs, disk cost, maintenance/RTO, and correctness** together.

## 21. Diagnosing p99 Spikes: Cache Miss, Compaction, GC, or Query Shape?

### 21.1. Decision Tree

~~~text
App p99 rises / timeouts increase
             |
     Did offered QPS change?
      /                \
    YES                 NO
     |                   |
Rate/load shape?    Did query mix/keys/CL change?
     |                     |
     +----------+----------+
                |
      Did Cassandra server p99 rise?
          /                 \
        YES                  NO
         |                    |
  Per-node disk/GC       Driver pool/queue/JIT
  compaction metrics     network/TLS/codec
         |
  Did cache hit/miss change?
      /         \
    YES          NO
     |            |
Working set?    Did pending compaction/flush rise?
     |            /           \
Read I/O up?    YES            NO
     |           |              |
Cache/eviction  SSTables/IO    Hot partition?
                backlog        Tombstone scans?
                    \           /
                     Data model / query profile
                              |
               Run controlled single-variable test
~~~

This tree **guides investigation**; it does not prove causality. For example, compaction can evict the OS page cache, causing cache misses and disk contention simultaneously. Rely on timelines, traces/samples, and controlled experiments.

### 21.2. Hypothesis → Required Evidence Matrix

| Hypothesis | Supporting Evidence | Refuting / Missing Evidence |
|---|---|---|
| JVM/JIT warm-up | Client CPU/allocation spikes initially, server latency flat | Server p99 spikes at the same time |
| Cold driver pool | Open connections/routing/handshakes shift, requests queue | Pool stable while disk reads climb |
| Key-cache miss | Key cache hit ratio falls, partition/index lookups get costlier | Hit ratio unchanged while disk writes rise |
| OS page-cache miss | Physical disk read bytes/await rise as key span widens | Disk reads flat despite rising client p99 |
| Memtable flush contention | Pending flushes, disk writes, commitlog/memtable pressure rise | No flush or I/O changes |
| Compaction contention | Pending/active compactions, bytes rewritten, disk await rise | Compaction idle while read-only p99 climbs |
| SSTable read amplification | SSTables-per-read, SSTable count/overlap rise | Only JIT/connections changed |
| Tombstones/TTL | Tombstones scanned, read timeouts/warnings, expired data rise | No deletes/TTL, scans low |
| Hot partition | Clear CPU/IO skew on a few natural replicas | All nodes evenly loaded |
| Replica/DC/CL issue | `UNAVAILABLE`, retries, coordinator/replica-specific errors | CL, RF/routing unchanged, no error rise |
| Load generator saturated | Generator CPU at 100%, offered vs. completed QPS diverge | Generator has headroom, server queues grow |

### 21.3. Investigation Workflow After an Anomaly

1. **Confirm scope:** One query family or the whole app? One node/token/DC or all replicas?
2. **Build a timeline:** Mark seed, warm, measurement, fault, compaction, repair, and client deploys.
3. **Check for changes:** Did query shapes, CL, partition distribution, or TTLs shift?
4. **Compare throughput and errors:** Did completed-request p99 exclude timeouts?
5. **Inspect cache and I/O:** Key/row/chunk hits, physical disk reads vs. writes, SSTables.
6. **Inspect background work:** Flushes, compaction, streaming, GC, repairs.
7. **Test one hypothesis and one variable:** Never tweak 4 settings and credit one setting for the entire gain.
8. **Verify correctness:** Reads/writes still honor CL without stale/corrupt results.

### 21.4. When Direct OS Cache Metrics Are Missing

Kernel page caches rarely expose per-table hit rates. Use **indirect signals**: cache residency tools if available, major/minor page faults, filesystem/disk reads, throughput, hot-key distributions, and read latency comparisons. **Never declare "page cache hit = 100%" solely because disk await is low**: fast NVMe SSDs, read-ahead, or Cassandra's chunk cache can also explain low await.

### 21.5. Counters Reset on Process Restart

Many counters like `BytesCompacted`, total requests, and GC counts **reset to 0 on process restart**. Dashboards computing rates/derivatives must handle counter resets; comparing raw totals across a restart makes compaction or workload appear to "drop 99%" when the counter merely reset. Use proper timestamps, process uptime, and rate functions.

## 22. Twenty Real-World Scenarios on Warm-Up, Caching, and Compaction

### Case 1 — First Read Slow, Second Read Fast on One Partition

**Observation:** First point lookup takes 80 ms; the next 100 take 5 ms.

**Possible causes:** Cold driver/JIT/connection, key/index/OS page cache miss, coordinator/replica lookup, GC.  
**Do not conclude:** "Key cache handled the entire read."  
**Verify:** Driver pool/JIT warm-up, Cassandra key-cache hits, physical disk reads, and SSTables-per-read at the same timestamps.

### Case 2 — Newer Benchmark Always Runs Faster Than Older One

**Observation:** Run B beats Run A despite identical code and target rate.

**Possible causes:** Run B inherited kernel page cache, prepared statements, or compaction that finished after Run A.  
**Fix:** Randomize A/B order, snapshot state, verify warm-up gates before each run, and report state differences.

### Case 3 — Hot Latency Persists After Container Restart

**Observation:** Docker restarts Cassandra, yet reads stay near hot speed.

**Explanation:** The host's OS page cache may still retain pages; saved caches and fast SSDs also contribute.  
**Do not conclude:** "Cassandra booted with full caches."  
**Fix:** Record restart scope, measure file I/O and cache metrics, and never treat container restart as a cold-cache oracle.

### Case 4 — Write QPS Looks Great for 3 Minutes, Then Drops

**Observation:** 25k writes/s initially, dropping to 8k after 10 minutes as pending compactions rise.

**Explanation:** Memtables/commitlog absorb the initial burst; once flushes and compaction kick in and contend for disk/CPU, the workload enters its sustained I/O regime.  
**Fix:** Measure throughput across sufficient flush/compaction cycles and disk headroom; never report the initial burst as sustainable throughput.

### Case 5 — `PendingCompactions=0` Yet Read p99 Is High

**Explanation:** Zero queued compactions does not guarantee healthy disk/cache/partitions; OS page misses, tombstones, hot partitions, or suboptimal SSTable layouts from past compaction can still hurt reads.

**Verify:** SSTables-per-read, page cache/disk reads, per-key read latency, row size/TTL, and driver queues.

### Case 6 — Compaction Is Always Active, Yet Latency Is Stable

**Explanation:** Continuous writes require ongoing background maintenance; active compaction threads are normal.  
**Decision:** Can still be **`STEADY`** if QPS/p99/errors meet SLOs, backlog/space are not drifting, and disk headroom holds. Pending need not equal 0.

### Case 7 — Switching from 100 Hot Keys to 1 Million Keys Spikes p99

**Explanation:** Working set expands, key/index/OS caches miss, and physical disk reads surge.  
**Fix:** Report the **workload-shift transient** separately; if production has long-tail keys, include them in warm-up and measurement mixes.

### Case 8 — 99% Cache Hit Rate, Yet One Tenant Still Times Out

**Explanation:** Aggregate hit ratio is dominated by hot keys; that tenant may have a wide/tombstone-heavy partition or congested natural replicas.  
**Fix:** Break down by query family/tenant tier (without logging raw tenant IDs), per-replica metrics, partition size, and tombstone scans.

### Case 9 — Comparing STCS and LCS After One Flush Shows Identical Results

**Explanation:** Compaction strategies have not entered their steady regimes; too few SSTables/levels exist.  
**Fix:** Run longer across multiple flush cycles with identical data/TTL/query mixes, and measure write amplification and SSTables-per-read.

### Case 10 — Enabling LCS Improves Read p99, While Disk Writes Surge

**Explanation:** LCS reduces read amplification in exchange for higher rewrite I/O.  
**Fix:** Report both read and write SLOs, compaction bytes, free disk, and recovery time—not just one p99.

### Case 11 — A 15-Minute TWCS Test Exposes No Tombstone/TTL Issues

**Explanation:** Production uses 30-day retention/time windows, whereas the short test never reached expiry or late-event arrivals.  
**Fix:** Run longer soaks or time-aware datasets/controlled retention scenarios and state coverage gaps. Never force absurd TTLs as a stand-in for 30 days.

### Case 12 — Cassandra Node Is `UN` After Restart, Yet App Remains Slow

**Explanation:** Cold JVM/OS caches, driver reconnects, hints/streaming/repair, and compaction I/O may still be active.  
**Fix:** Separate time-to-CL-success from time-to-p99-baseline and monitor post-recovery trends.

### Case 13 — Node Failover Slows Down a Hot Partition

**Explanation:** Coordinator/Replica B previously received fewer reads, leaving its key/page caches cold; routing, CL paths, and retries also shift.  
**Fix:** Inspect per-replica cache metrics, coordinator traces, RF3/`LOCAL_QUORUM` data oracle, and `RTO_perf`.

### Case 14 — Higher Concurrency Lowers Completed QPS

**Explanation:** Saturation, queuing/backpressure, disk/compaction overload; closed-loop generators may also throttle offered load automatically as latency climbs.  
**Fix:** Plot offered vs. completed QPS and in-flight/queue depths to locate the saturation knee instead of just adding threads.

### Case 15 — App p99 Rises While Cassandra Server p99 Stays Flat

**Explanation:** JVM GC, connection pool/throttling, network/TLS, serialization/binding, or client retries.  
**Fix:** Capture driver `cql-requests`, node `cql-messages`, JFR, and pool metrics; do not blindly raise `compaction_throughput`.

### Case 16 — Cassandra Server Read p99 Spikes During Backup/Repair

**Explanation:** Snapshots, repair streaming, anti-compaction, and reads contend for disk and CPU.  
**Fix:** Add maintenance event markers and measure normal baseline vs. maintenance-under-load SLOs separately; do not strip all maintenance from tests if production runs it routinely.

### Case 17 — `cassandra-stress` Reports 5× Higher Speed Than the Java App

**Explanation:** Stress uses a different schema, distribution, and row size, skips HTTP/business logic, and may use a different CL.  
**Fix:** Run stress user mode or NoSQLBench with an equivalent CQL profile; align offered load, CL, page size, retries, and data cardinality.

### Case 18 — Error Rate Rises While Success-Only p99 Drops

**Explanation:** The slowest requests timed out and dropped out of the success histogram, shrinking the percentile of surviving requests.  
**Fix:** Report failures/timeouts, end-to-end deadlines, SLO success latency, and censored samples; never claim an optimization.

### Case 19 — Flush Queue Grows After Bulk Import; Import Stops, Yet p99 Stays Bad

**Explanation:** Background SSTable flushes and compaction are still paying down the write-burst "debt".  
**Fix:** Continue measuring drain, pending/active tasks, disk writes, and read p99; separate workload recovery from steady-state acceptance.

### Case 20 — Compaction Benchmark "Passes" Because Disk Fills Up at Test End

**Wrong:** The generator ran for the configured duration, so the run is marked PASS despite critically low free disk or compaction failures.  
**Right:** STOP, protect the cluster, record parameters, and follow the rollback/resume runbook; never drive load until writes or scaling fail. **Sustained load capability** matters more than transient numbers.

## 23. GO/HOLD/STOP Runbook for Warm-Up and Fault Tests

### 23.1. Pre-Run Prerequisites

1. **Explicit authorization and scope:** Dedicated lab/staging cluster/namespace with an approved window if applicable.
2. **Designated owners:** Owners for the Cassandra cluster, application, load generator, and rollback.
3. **Dataset manifest:** Partition cardinality, distributions, TTL/tombstones, row sizes, and compaction policy.
4. **Topology contract:** RF per DC, read/write CL, app local DC, and token coverage.
5. **Workload contract:** Query families, QPS/concurrency, rate cap, error budget, duration, first-page vs. full-page rules.
6. **Complete telemetry:** Client requests/attempts, server JMX, disk/CPU/GC, cache/SSTable/compaction metrics.
7. **Stop thresholds:** Disk free/await, error rate, timeouts, GC pauses, backlog growth, and data mismatches.
8. **Test oracle:** Known keys and values/versions so correctness is never traded for throughput.
9. **Restore plan:** No reckless `TRUNCATE`/kills/disabling compaction; authority to stop generators and restore setup.

### 23.2. Phased Execution Protocol

~~~text
START
  |
  v
PREFLIGHT: ENV + CL + RF + DATA ORACLE
  |
  +-- FAIL --> STOP / FIX CONFIG
  |
  v
SEED / PRELOAD at controlled rate
  |
  v
WAIT: initial flush/compaction observation
  |
  v
WARM-UP: same query mix & key distribution
  |
  v
STEADY-STATE GATE?
  |                    |
 FAIL/BUDGET EXPIRED  PASS
  |                    |
 HOLD: NOT_STEADY      v
  |                 MEASURE
  |                    |
  |                 FAULT? -- NO --> REPORT
  |                    |
  |                   YES
  |                    |
  |            INJECT ONE CONTROLLED FAULT
  |                    |
  |             OBSERVE CL + ERRORS + p99
  |                    |
  |             RESTORE FAULT CONDITION
  |                    |
  |             POST-RECOVERY GATE?
  |                   /            \
  |                PASS             FAIL
  |                  |               |
  +--------------->REPORT      STOP + ESCALATE
                     |
         Archive phase metrics and limits
~~~

Never waive a failed warm-up gate simply because the timer expired. Label it honestly as `NOT_STEADY_WITHIN_BUDGET`; that itself **is a key finding** about capacity, working set, or non-representative workload design.

### 23.3. GO / HOLD / STOP Decisions

| Observation | Action | Reason |
|---|---|---|
| Preflight: wrong CL/DC, schema/data mismatch | **STOP** | Never benchmark under the wrong consistency contract |
| Dataset lacks target cardinality/time distribution | **HOLD** | Cache results may be artificially optimistic |
| Cold metrics captured, caches still warming | **HOLD** | System has not reached target state yet |
| Warm-up budget expired while compaction backlog keeps climbing | **HOLD / NOT_STEADY** | Sustained throughput is unproven |
| Cache steady, compaction stable, p99/errors meet target across windows | **GO** | Evidence confirms test criteria met |
| Driver request timeouts rise while success p99 drops | **HOLD / STOP** | Slow requests are likely censored |
| Free disk falls below guardrail or compaction fails | **STOP immediately** | Risk to data and recovery capability |
| Fault too severe, nodes lose CL and data oracle fails | **STOP fault, restore** | Do not continue destructive experiments |
| Node UP, but post-recovery p99/backlog have not stabilized | **HOLD** | Functional recovery ≠ performance recovery |
| Post-recovery gates/accuracy/SLOs pass across consecutive windows | **GO report** | Evidence confirms full recovery |

**There is no universal threshold** like "p99 ≤ 100 ms" or "disk free ≥ 30%" for every cluster. Guardrails must reflect your SLOs, storage class capacity, compaction strategy, RF/CL, and approved baseline.

### 23.4. Immediate ABORT Conditions

In a dedicated lab, halt the generator and fault injection if any of the following occur:

- Data oracle failures, tombstone resurrection, or severe data corruption.
- Unexpected node failures or CL loss beyond the test's intended scope.
- Full disk, read-only filesystem, commitlog write failures, or compaction errors.
- GC/OOM/CPU throttling breaching guardrails and threatening cluster/data health.
- Test tool targeting **the wrong cluster/IP/keyspace** outside the allowlist.
- Credentials or PII logged, or unauthorized mutations executed.

Never "temporarily lower CL" to keep a benchmark running once the consistency contract breaks. Mark the run FAIL or INCONCLUSIVE and execute the recovery runbook.

### 23.5. Recovery and Handoff

After stopping the workload:

1. Record exact timestamps for generator stop and fault removal.
2. Verify nodes/ring, RF/CL data oracle, and unknown write outcomes.
3. Monitor flush/compaction/repair/streaming backlogs until gated recovery or budget expiry.
4. Confirm disk headroom and physical I/O return to safe ranges.
5. Separate `RTO_CL` and `RTO_perf`; never rely solely on `nodetool status UN`.
6. Archive raw metrics, sample counts, histogram method, and manifest versions.
7. Restore system settings to baseline strictly per runbook/owner; **never manually delete SSTables or snapshots**.
8. Document limitations: small dataset, insufficient time windows, incomplete token/DC coverage, or transient replication if applicable.

### 23.6. Result Template That Does Not Hide Ugly Phases

~~~text
EXPERIMENT_ID:
OWNER / UTC START:
CLUSTER / CASSANDRA VERSION / DRIVER:
RF PER DC / READ CL / WRITE CL:
QUERY FAMILIES / QPS TARGET / GENERATOR:
DATASET: partition_count, rows_per_partition, bytes, TTL
COMPACTION: strategy, settings, initial SSTables
CACHE: key/row/chunk config, working set estimate

COLD PHASE:
  duration, latency p50/p95/p99, errors
  cache misses, disk reads, JIT/GC

WARM-UP PHASE:
  actual duration, gate PASS/NOT_STEADY
  cache hit trend, compaction/flush trend

STEADY MEASUREMENT:
  completed/target QPS, latency hist counts
  p50/p95/p99 by query family
  retries/timeouts/unknown outcomes
  SSTables-per-read, compaction bytes/queues
  physical disk I/O, GC, disk headroom

FAULT PHASE (if any):
  fault type/scope, T_fault_onset, T_fault_removed
  CL availability, p99/error, data oracle

RECOVERY PHASE:
  RTO_CL, RTO_perf, repairs/streaming
  cache state, compaction backlog, disk headroom

RESULT: GO / HOLD / STOP
LIMITATIONS / DATA CORRECTNESS / NEXT ACTION:
~~~

These lines are a **report content template**, not an instruction to create extra files in the module directory. The final conclusion must state **scope**: query families, dataset, topology, offered QPS, CL, duration, hardware, and warm/cold state.

## 24. Code-Review Checklist for a Load/Fault Test Plan

### 24.1. Reproducibility

- [ ] Cassandra, JDK, Java Driver, and load generator versions pinned.
- [ ] Node count/DC/rack/RF/CL and table schema explicitly recorded.
- [ ] Compaction strategy/config, compression, and cache configs snapshotted.
- [ ] Dataset cardinality, row size, TTL, tombstones, and partition width captured in a manifest.
- [ ] Workload key distribution (hot/uniform/range/temporal) reflects production.
- [ ] Rate schedule, concurrency, queue/in-flight limits, and test duration defined.
- [ ] A/B comparisons hold non-target variables equal.
- [ ] Multiple runs, randomized order, or verified state resets included.
- [ ] Container restarts are not assumed to guarantee a cold OS page cache.
- [ ] Client JVM/driver warm-up and load-generator headroom accounted for.

### 24.2. Read Path

- [ ] Queries match partition keys and clustering patterns; no unintended `ALLOW FILTERING`.
- [ ] Read CL set explicitly rather than silently falling back to a default profile.
- [ ] p50/p95/p99 measured separately per query family (and page 1 vs. full result where needed).
- [ ] Cache hits/misses include sample counts, node scope, and working-set context.
- [ ] Physical disk reads / page-cache evidence collected appropriately.
- [ ] `SSTablesPerReadHistogram`, SSTable counts, and tombstone scans captured.
- [ ] Point lookups and table/range scans are not merged into one percentile.
- [ ] Hot-key-only tests are not labeled as random production benchmarks.
- [ ] Data oracle verifies exact PK/value/version, not merely "no exceptions thrown".

### 24.3. Write Path / Compaction

- [ ] Representative memtable flush cycles occur during measurement (or limitations stated).
- [ ] Commitlog, memtable, pending flushes, and disk write throughput measured.
- [ ] Compaction backlog, bytes, and SSTable counts/levels do not grow unboundedly at steady target.
- [ ] "`PendingCompactions=0`" is not treated as the sole acceptance condition.
- [ ] Disk headroom reserved for compaction output and repair; never run to 100% disk.
- [ ] TTL, tombstone, and late-arrival patterns match the data lifecycle.
- [ ] Auto-compaction is not disabled merely to inflate short-term throughput.
- [ ] Manual major compaction or `TRUNCATE` is never run arbitrarily on shared clusters.
- [ ] Both read/write amplification and maintenance/recovery costs reported.

### 24.4. Latency / Statistics

- [ ] Offered QPS and completed QPS recorded separately.
- [ ] QPS stability verified across multiple rolling windows, not a single snapshot.
- [ ] p99 backed by sufficient samples and documented histogram methodology.
- [ ] Errors, timeouts, and canceled requests are not excluded from SLO reporting.
- [ ] Client and server percentiles are never subtracted to "compute network time".
- [ ] Cache, compaction, GC, disk, and latency metrics share aligned timestamps.
- [ ] Driver retries and speculative executions included in physical load accounting.
- [ ] Little's Law applied only with mean latency in steady state; never substitute p99 for mean.
- [ ] COLD/WARM/STEADY/FAULT/RECOVERY phases separated with actual durations recorded.
- [ ] Never label a phase `STEADY` while backlogs grow or caches continuously drift.

### 24.5. Safety and Fault Testing

- [ ] Test cluster is on an allowlist, never a production or shared environment.
- [ ] Authorized owners designated for fault injection, rollback, and test abort.
- [ ] Stop criteria set for data mismatch, disk pressure, node failure, and timeout spikes.
- [ ] Fault injection varies **one primary variable** at a time when establishing causality.
- [ ] Natural replicas and CL verified before stopping a node in a dedicated lab.
- [ ] Both CL recovery and performance/compaction recovery measured after restarts.
- [ ] Write timeouts handle unknown outcomes and idempotency keys properly.
- [ ] CL is never lowered and retries are never abused to flatter reports.
- [ ] No arbitrary host `drop_caches`, kills, `iptables`, or `TRUNCATE` commands.
- [ ] Raw credentials, PII, bind values, and high-cardinality IDs excluded from dashboards.
- [ ] Conclusions stay strictly within measured scope, noting limitations and next validation steps.

## 25. Self-Check Questions and Suggested Answers

**Q1.** Why is dropping the first 30 seconds and calling everything afterward "steady state" wrong?  
**Hint:** JIT, caches, flushes, and compaction may still be transitioning; stability must pass a quantitative rolling-window gate.

**Q2.** Is Java Driver warm-up the same as OS page-cache warm-up?  
**Hint:** No; prepared statements, connections, metadata, and JIT on the client differ from data/index pages on the server.

**Q3.** Can reading the same partition 1,000 times prove a random production workload is warmed up?  
**Hint:** No; key distributions and working sets differ completely.

**Q4.** Does a key-cache hit prove SSTable data is in RAM?  
**Hint:** No; key cache mostly speeds up partition/index lookups, while data blocks may still require disk reads.

**Q5.** Is row cache enabled by default and beneficial for every query?  
**Hint:** No; it depends on config/version, hot partitions, write invalidations, and memory limits.

**Q6.** Does restarting a Cassandra container guarantee a cold OS page cache?  
**Hint:** No; the host kernel page cache can survive process and container restarts.

**Q7.** Why can compaction cause cache hit rates to drop?  
**Hint:** New SSTables alter file layouts, and compaction I/O competes with and evicts OS page-cache pages.

**Q8.** Does Cassandra write directly to an SSTable before ACKing a CQL INSERT?  
**Hint:** Normally mutations go to the commit log and memtable; SSTable flushes happen asynchronously later.

**Q9.** Does a successful write ACK at QUORUM mean compaction is finished?  
**Hint:** No; write CL acknowledgment is separate from background flush and compaction lifecycles.

**Q10.** Why is write throughput at the start of a test often higher than sustained throughput?  
**Hint:** Memtables and the commit log initially absorb bursts before flush and compaction I/O saturate disks/CPU.

**Q11.** If pending compactions are non-zero, is the system definitely `NOT_STEADY`?  
**Hint:** No; sustained writes continuously generate compaction work. What matters is backlog trend and SLO stability.

**Q12.** If pending compactions climb 10 → 25 → 50 → 100, can the system be called steady?  
**Hint:** No, if climbing continuously under constant load, even if p99 has not breached its threshold yet.

**Q13.** Is `BytesCompacted` a counter or a gauge?  
**Hint:** A counter; take rates/deltas over time and account for resets on node restarts.

**Q14.** Does `PendingTasks` measure bytes awaiting compaction?  
**Hint:** No; it is an estimated task count, and individual compaction tasks vary widely in size.

**Q15.** Why monitor `SSTablesPerReadHistogram`?  
**Hint:** It measures read amplification—how many SSTables a read must inspect.

**Q16.** Which workloads suit STCS, LCS, and TWCS?  
**Hint:** STCS suits write-heavy/general workloads, LCS suits read-heavy/update-heavy lookups, and TWCS suits mostly immutable TTL time-series; always benchmark on your version.

**Q17.** Can UCS be enabled on every Cassandra 4.x release?  
**Hint:** No; verify version availability and configuration, especially since UCS was introduced for Cassandra 5.x.

**Q18.** Why does a 10-minute TWCS test fail to validate a 30-day TTL lifecycle?  
**Hint:** It does not traverse real expirations, late writes, or multi-window compaction transitions.

**Q19.** Should you set a 1-second TTL to "simulate" 30-day retention?  
**Hint:** No; it creates unrealistic churn and tombstone dynamics unrepresentative of production.

**Q20.** Can a 1 TB table have a 2 GB working set?  
**Hint:** Yes; working set depends on access distribution, not total table size.

**Q21.** With 40 GiB of active pages and 16 GiB of page-cache RAM, will warming up longer fit all 40 GiB in cache?  
**Hint:** No; the steady behavior will be turnover/thrashing, so measure miss rates directly.

**Q22.** Do uniform random and Zipfian distributions exhibit the same cache behavior?  
**Hint:** No; Zipfian concentrates hits on hot keys while uniform spreads across a much wider key space.

**Q23.** After 300k uniform reads across 1 million keys, have all 1 million keys been touched?  
**Hint:** No; expected distinct keys touched is ~259k, even before accounting for pages and indexes.

**Q24.** Why does a hot partition skew a cluster-wide benchmark?  
**Hint:** A few natural replicas saturate while other nodes remain idle.

**Q25.** How does a closed-loop generator adjust offered load when latency spikes?  
**Hint:** Offered rate drops automatically as workers wait on responses, causing coordinated omission.

**Q26.** Do open-loop loads require queue and in-flight limits?  
**Hint:** Yes; if Cassandra slows down, unbounded requests pile up, so enforce hard stops and backpressure.

**Q27.** Can p99 replace mean latency in Little's Law `L = λW`?  
**Hint:** No; `W` is the steady-state mean response time.

**Q28.** If success-only p99 drops while timeouts climb, did performance improve?  
**Hint:** No; slow requests failed and dropped out of the success histogram.

**Q29.** Why must sample counts be reported alongside p99?  
**Hint:** Small sample counts make tail percentiles noisy and easy to misinterpret.

**Q30.** Can you compute network latency as `app p99 − Cassandra server p99`?  
**Hint:** No; percentiles from separate distributions do not add or subtract linearly like means.

**Q31.** What metric groups should a warm-up gate check?  
**Hint:** QPS, p95/p99, errors, caches, SSTables-per-read, flush/compaction backlogs, disk/CPU/GC, and driver metrics.

**Q32.** If compaction backlog rises while client p99 looks fine for now, what should you do?  
**Hint:** `HOLD`/`NOT_STEADY`; do not mark sustained capacity PASS.

**Q33.** Why must measurement windows span multiple flush cycles?  
**Hint:** Initial write bursts hide the long-term I/O cost of SSTable flushes and compaction.

**Q34.** What must remain equal when comparing compaction strategies?  
**Hint:** Dataset, workload mix, CL/RF, hardware, OS/driver settings, warm state, and histogram methodology.

**Q35.** Should you disable auto-compaction to get a "clean" read benchmark?  
**Hint:** Not if measuring production-like steady state; disabling it alters SSTable evolution and risks a compaction storm afterward.

**Q36.** Is `cassandra-stress` still the recommended primary benchmarking tool in Cassandra 5.0?  
**Hint:** Documentation marks it deprecated and recommends NoSQLBench; it remains useful in labs if you understand its limits.

**Q37.** Does built-in `cassandra-stress` automatically model your application's tables and order API?  
**Hint:** No; you need user mode, custom workloads, NoSQLBench, or a Java generator matching your schema and queries.

**Q38.** Why can running stress writes and immediately switching to reads distort a cache test?  
**Hint:** Compaction and flushes from seeding are still changing SSTables and evicting OS caches.

**Q39.** Is running `drop_caches` on a shared host an acceptable default way to benchmark cold state?  
**Hint:** No; it disrupts other processes, adds risk, and differs from production; only use it in dedicated labs under policy.

**Q40.** Does shifting from hot set A to B prove 100% of B's OS cache pages are cold?  
**Hint:** No; SSTable data and index pages can overlap, so measure physical disk and cache metrics directly.

**Q41.** Why can a Cassandra node showing `UN` after restart still cause high app p99?  
**Hint:** JIT, caches, driver pools, streaming, repair, and compaction may still be catching up.

**Q42.** How do `RTO_CL` and `RTO_perf` differ?  
**Hint:** One measures restoring correct query responses at the required CL; the other measures restoring steady-state SLOs, caches, and compaction.

**Q43.** Under RF3 `LOCAL_QUORUM`, does stopping one replica guarantee all queries fail?  
**Hint:** No; the two remaining replicas can satisfy quorum, depending on replica placement and latency.

**Q44.** Why should you never generate a fresh UUID to blindly retry after a write timeout?  
**Hint:** The mutation may already have applied (unknown outcome), and a new ID can duplicate business data.

**Q45.** If free disk drops low and compaction fails, should you finish the remaining test duration?  
**Hint:** No; STOP immediately, protect data, and follow the recovery runbook.

**Q46.** If app p99 climbs while server read latency stays flat, what should you inspect first?  
**Hint:** Driver pools/throttling/retries, JVM JIT/GC, network/TLS, serialization, and generator saturation.

**Q47.** Key-cache hits stay steady while physical disk reads rise—what could explain this?  
**Hint:** Key cache only speeds up index lookups; data blocks/chunks are still missing cache, or compaction is competing for I/O.

**Q48.** How should a final conclusion be phrased?  
**Hint:** "Query family X on dataset D, topology T, CL Y, at QPS Z met p99 SLO across N windows with stable background backlogs within the tested scope"—never claim "Cassandra is universally fast".

## 26. Summary: Warm-Up Is a State Measurement, Not a Button

~~~text
                     CASSANDRA LOAD / FAULT TEST
                                 |
                      1. Define contract
          dataset + partition pattern + RF/CL + query mix
                                 |
                     2. Isolate environment
                versions + hardware + stop limits
                                 |
                     3. Seed known data
               verify oracle + observe flush/SSTables
                                 |
                     4. Controlled warm-up
                Java/driver/JVM + server caches
                memtables/flush/compaction lifecycle
                                 |
               +-----------------+-----------------+
               |                                   |
          Gate NOT_STEADY                       Gate PASS
               |                                   |
        HOLD and explain                      5. Measure
        capacity/workload                   p99 + errors
        or coverage gap                    cache + SSTables
               |                           compaction + disk
               |                                   |
               |                              6. Fault?
               |                             /       \
               |                           NO        YES
               |                           |          |
               |                         REPORT   Inject one fault
               |                                      |
               |                                  CL recovery
               |                                      |
               |                                 Perf recovery
               |                                      |
               +----------------+---------------------+
                                |
                        7. GO / HOLD / STOP
                      with honest limitations
~~~

### 26.1. Five Mandatory Rules to Remember

1. **Do not lump all warm-up together:** JVM/driver caches, Cassandra key/row/chunk caches, OS page cache, and SSTable/compaction states warm on different timelines and triggers.
2. **Do not just wait a fixed timer:** Verify steady state across multiple rolling windows alongside backlog and resource trends.
3. **Do not benchmark a hot key and call it production:** Working set, key/tenant distribution, TTLs, partition sizes, and CL must be representative.
4. **Do not ignore maintenance costs:** Flushes, compaction, and repair can degrade p99 even after the load generator stops or a node reports `UN`.
5. **Do not watch p99 alone:** Track errors, timeouts, correctness, RF/CL, driver attempts, disk headroom, and RTO.

**Core takeaway:** In Apache Cassandra, warm-up can simultaneously **reduce latency** as caches absorb hot keys and **increase latency** as flushes and compaction begin paying down the cost of prior writes. A trustworthy benchmark **must state the exact state it measured**, covering client/driver caches, data working set, SSTable/compaction lifecycle, consistency level, and observation window. Reporting a bare p99 without this context easily leads to flawed capacity and failover decisions.

## References

- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — JMX metrics for Cache, Table, Compaction, client requests, tombstones, and streaming.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — memtable → SSTable, compaction lifecycle, strategies, tombstones, read/write amplification.
- [Apache Cassandra — Cassandra Stress](https://cassandra.apache.org/doc/stable/cassandra/tooling/cassandra-stress.html) — commands, options, user mode, deprecation note, and NoSQLBench.
- [Apache Cassandra — Nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — active/pending compaction and throughput.
- [Apache Cassandra — Nodetool overview](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/nodetool.html) — `tablestats`, `tpstats`, `compactionstats`, observational and controlled operations.
- [Apache Cassandra — Use nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html) — compaction state, read/write performance, dropped messages, and disk troubleshooting.
- [Apache Cassandra — Dynamo architecture](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — coordinators, tokens, replicas, RF, and consistency levels.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — query-first partition design, replication, and access patterns.
- [Apache Cassandra Java Driver 4.18 — Metrics](https://apache.github.io/cassandra-java-driver/4.18.0/core/metrics/) — session/node timers, pooling, metrics backends, and percentiles.
- [Apache Cassandra Java Driver 4.18 — Pooling](https://apache.github.io/cassandra-java-driver/4.18.0/core/pooling/) — in-flight streams, connections, and request multiplexing.
- [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — server/client prepared caches and re-preparing.
- [Apache Cassandra Java Driver 4.18 — Retry policies](https://apache.github.io/cassandra-java-driver/4.18.1/core/retries/) — retry policies, faults, and workload amplification.
- [Apache Cassandra Java Driver 4.18 — Request throttling](https://apache.github.io/cassandra-java-driver/4.18.0/core/throttling/) — admission control, client queues, and timeouts.
- [NoSQLBench](https://docs.nosqlbench.io/) — modern workload-based benchmarking; check its documentation for syntax and scenarios.
- [OpenJDK JFR](https://docs.oracle.com/en/java/javase/17/jfapi/flight-recorder.html) — Java Flight Recorder for tracking JIT/GC/allocation and JVM events.
- [Gil Tene — How NOT to Measure Latency](https://www.infoq.com/presentations/latency-response-time/) — coordinated omission and statistical pitfalls in latency measurement.
