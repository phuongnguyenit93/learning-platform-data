# Controlled Changes, Baselines, and Rollback Conditions in Apache Cassandra

> **Chapter:** Resource Tuning  
> **Focus:** Designing a verifiable and safely reversible resource change on Apache Cassandra: establishing a baseline, stating a hypothesis, modifying one clearly scoped parameter, canary/ramp-up, multi-layer monitoring, defining rollback gates, and post-deployment evaluation. Examples reference Cassandra 4.1/5.0 and Java Driver 4.x; always verify syntax/configs against your running version.

## 1. Learning Objectives

After this lesson, you can:

1. Define a **baseline** using pre-change data covering SLOs, workload, CPU, heap/GC, disk, network, memtables, compaction, and read/write consistency levels.
2. Write a **falsifiable tuning hypothesis**, such as whether raising the compaction throughput cap shrinks backlog without degrading tail latency.
3. Classify which operations are **runtime knobs**, which require **rolling restarts**, and which trigger **data/ring changes** that cannot be rolled back simply by reverting a config file.
4. Build a **canary → evaluate → expand → monitor** plan, avoiding changing multiple variables at once so improvements or regressions stay attributable.
5. Set **stop and rollback thresholds** measurable via p95/p99, timeouts, availability, disk headroom, backlogs, GC, and replica health.
6. Run a lab observing before/after states of a compaction-limit change on a test node, recording the old value, reverting, and verifying the rollback actually took effect.
7. Design Java Driver monitoring accounting for retries, CL, request families, schema/partition keys, and distributed impact across replicas.

**Core idea:** Tuning is not a game of "pick a new number and watch one metric drop". A tuning change succeeds only when **workload and data results remain equivalent**, the target bottleneck eases, consistency/availability do not regress, and a tested rollback path exists.

## 2. Why Does Cassandra Need Controlled Changes?

In Cassandra, a request passes through multiple components sharing resources:

~~~text
Java Application / CQL request
          |
          v
   Driver load balancing
          |
      Coordinator
          |
      Replica set
      /     |     \
    Node A Node B Node C
      |      |      |
    Commit log + memtable
      |      |      |
    Flush -> SSTable
      |      |      |
    Compaction / repair
      |      |      |
   CPU, memory, disk, network

      User SLOs, CL, RF
       govern everything
~~~

An edit on one node or component can ripple across many others:

- **Raising compaction throughput** may shrink pending compactions yet pit disk I/O against reads/flushes, spiking p99.
- **Adding flush writers** may drain memtables faster yet spawn more SSTables, adding compaction work.
- **Enlarging the JVM heap** may ease allocation pressure yet alter GC pauses; starving off-heap RAM or the page cache still slows disk reads.
- **Boosting Java Driver retries/speculative execution** may rescue a few tail requests yet multiply real requests hitting coordinators/replicas, creating an overload spiral.
- **Lowering consistency level** may make latency look prettier yet changes the data contract, risking stale reads and weaker write guarantees; it does not count as equivalent resource tuning.
- **Adding nodes or changing RF** alters replica ownership/streaming—not an isolated single-machine knob tweak.

### 2.1. Three Very Different Outcomes

| Outcome | Example | Is It Successful Tuning? |
|---|---|---|
| **Faster and safer** | Read p99 drops, disk wait and timeouts do not rise, data stays correct | Potentially yes, if stable under equivalent workload |
| **Faster yet riskier** | P99 drops because `LOCAL_QUORUM` was downgraded to `ONE` | **No**, if original consistency requirements forbid it |
| **One metric looks better while overall system degrades** | Pending compactions drop, yet write timeouts and GC spike | **No**, failed acceptance criteria |

Practical rule: **define what must not degrade before opening the change**, never invent rollback criteria after an incident has already hit.

### 2.2. Tuning Differs from Capacity Expansion and Data Migration

- **Tuning:** changing a runtime parameter or policy to improve resource utilization within the same business model and topology.
- **Capacity expansion:** adding nodes, disks, or upgrading host specs; may trigger bootstrap/streaming and driver metadata refreshes.
- **Data-model migration:** building query-driven tables or changing partition keys via new tables/backfills; involves dual-write phases and divergence risk.
- **Recovery:** fixing failed nodes/data via repair/restore/replace; never bundle into pure tuning.

One change request may span multiple types, yet must be **broken into separate checkpointed steps**. Changing compaction concurrency while simultaneously altering RF and doing a rolling restart makes attribution nearly impossible.

## 3. What Is a Baseline and Why Isn't One Snapshot Enough?

A **baseline** is a reference dataset representing the **system prior to the change**, covering workload profile, cluster health, data correctness, and acceptance boundaries. A baseline is not a single `nodetool status` command or one average CPU number at a random moment.

### 3.1. Five Mandatory Baseline Dimensions

| Dimension | Information to Record | Why It Matters |
|---|---|---|
| **Workload** | Mean/peak QPS, read:write ratio, query families, partition sizes, hot keys, batch jobs | To compare before/after under equivalent load |
| **SLOs and outcomes** | p50/p95/p99, timeout/unavailable rates, success rate, correctness, CL | Better metrics mean nothing if requests fail or read stale/wrong data |
| **Resources** | CPU, heap/off-heap, GC pauses, disk IOPS/latency/free, network, queues | Identifies which physical constraint limits the system |
| **Storage engine** | Memtables, pending flushes, commit log, SSTable count, pending compactions, tombstones/read | Understands the causal chain so you don't tune the wrong layer |
| **Cluster / config** | Cassandra version, node/DC/rack, RF, ring, replica health, configs, Java Driver | Compares matching topology and enables restoring old settings |

In Cassandra with RF=3, a `LOCAL_QUORUM` write succeeds once **two replicas ACK** in the local DC. Looking only at application latency can hide a third node that is overloaded. Baselines must be captured **per node**, never from cluster-wide averages alone.

### 3.2. Three Reference Time Windows

| Window | Purpose | Notes |
|---|---|---|
| **Steady state** | Normal traffic after warm-up | Maintain cache state; never compare cold against warm |
| **Business peak** | Verify real headroom and tail latency | Needs sufficient samples at matching day/hour in the cycle |
| **Maintenance / batch** | Observe repair, backups, streaming, bulk ingest | Do not exclude these from baselines if they are recurring operational work |

A practical baseline might span **7–14 days** to capture seasonality plus detailed **30–60 minute** peak snapshots for canary comparisons. These are planning examples, **not Cassandra-mandated durations**. Periodic batch services may require longer windows.

### 3.3. Baselines Must Capture Samples and Scope

Example **hypothetical** table across three nodes in one DC:

| Metric | Node A | Node B | Node C | Interpretation |
|---|---:|---:|---:|---|
| CPU p95 | 62% | 58% | 61% | Moderate headroom remains |
| Disk read p99 | 12 ms | 9 ms | 11 ms | No major per-node skew seen |
| Free disk | 42% | 39% | 41% | Room for temporary SSTables |
| Pending compactions | 18 | 20 | 17 | Backlog requires checking **trend** |
| Pending flushes | 0 | 1 | 0 | No sign of sustained flush stall |
| Application write p99 | \- | \- | \- | 75 ms on app histogram |
| Timeout rate | \- | \- | \- | 0.05% of total peak requests |

Never infer "pending compactions=20 means overload" from this table alone. Track whether it is **accumulating**, real compaction throughput, disk latency, and SLAs; STCS/LCS/TWCS/UCS also give pending estimates different meanings.

### 3.4. Factors to Lock Down Before Testing

- Old config: actual runtime values, active `cassandra.yaml`/JVM flags, Java Driver config, and app version.
- Topology: node count, token ranges, per-DC RF, nodes down/joining/leaving, repaired ranges if relevant.
- Load: read/write ratio, per-query-family QPS, payload/partition sizes, CL, page size, retries, background jobs.
- Data state: sample keys and business outputs, TTL/tombstones if storage behavior is affected.
- Time: unified UTC clock, measurement window, clock skew status, other deploy/compaction/repair schedules.

A config committed in Git **may not match active runtime values**: parameters can be overridden by system properties/JMX, some changes require restarts, and others reload at different times. Whenever possible, read active values directly via `nodetool get...` or JMX.

## 4. Layered Baselines: App, Driver, Coordinator, Replica, and OS

### 4.1. Java-Side Metrics

| Group | Source | What to Track |
|---|---|---|
| **Business SLO** | API timers/histograms | p95/p99, error budget, timeout rate, user-visible failures |
| **Query family** | Repository instrumentation | Query counts, QPS, duration, rows/pages, per-operation success/failure |
| **Driver session** | Java Driver 4.x metrics | `cql-requests`, `cql-client-timeouts`, connected nodes |
| **Driver node** | Java Driver metrics | `cql-messages`, pool in-flight/open connections, retries/connections |
| **Application runtime** | JVM/Micrometer/OpenTelemetry | CPU, heap, allocations, GC, thread pools, queues, network |

One `session.execute()` or `executeAsync()` call may involve retries/speculative execution; **logical app QPS does not equal physical coordinator attempts**. Monitor both sides so you don't improve surface latency while hammering Cassandra with extra load.

### 4.2. Cassandra-Side Metrics

| Group | Data to Record | How to Read |
|---|---|---|
| `ClientRequest.Read/Write.Latency` | Coordinator latency per request type | Not automatically split by query family |
| `ClientRequest.Timeouts/Unavailables` | Error rates per node and request type | Pair with CL/RF and node outage timestamps |
| `Table.ReadLatency/WriteLatency` | Local table latency on replicas | Not identical to end-to-end Java p99 |
| `Table.SSTablesPerReadHistogram` | Read amplification | Rises from lagging compaction or bad query shape |
| `Table.TombstoneScannedHistogram` | Tombstones traversed on read path | Driven by DELETE/TTL/partition modeling |
| `Table.PendingFlushes` | Queued flush work | Check trend with flush pools—never judge from one sample |
| `Table.PendingCompactions`, `Compaction.PendingTasks` | Compaction backlog estimate | Gauge/estimate; not an ETA |
| `Compaction.BytesCompacted` | Bytes processed | Compute rate accounting for restart resets |
| `CommitLog.WaitingOnSegmentAllocation` | Segment allocation pressure | Can relate to flushing or commit log disk |
| `ThreadPools.*.PendingTasks/ActiveTasks` | Queues/workers per stage | Diagnoses read/write/flush/compaction bottlenecks |

Read JMX metrics by **node**, **keyspace**, and **table**. Exporters can rename or reshape metrics, so verify mappings before writing alerts. **Never average per-node p99s to compute cluster p99**: percentiles must be aggregated from histograms or raw distributions.

### 4.3. Operating System Baselines

~~~bash
# Observation commands on Linux only; tools depend on OS.
iostat -xz 1 5
vmstat 1 5
df -h
~~~

Disk latency, IOPS, throughput, queue depth, `%iowait`, and CPU throttling must be viewed alongside Cassandra metrics. **High idle CPU does not mean storage has headroom**: the system may be disk-bound. High `%util` on SSD/NVMe does not automatically prove saturation; check latency and throughput too.

### 4.4. Logging Baselines via `nodetool`

~~~bash
# Read-only status commands; run per authorized access policies.
nodetool version
nodetool status
nodetool describecluster
nodetool info
nodetool tablestats
nodetool tpstats
nodetool compactionstats
nodetool netstats
nodetool gcstats
nodetool getcompactionthroughput
~~~

`tablestats` can print huge output across many tables; in production filter to **key tables** and save outputs with UTC timestamps and release versions. `nodetool status` from one node is only that node's view of the ring at that instant—it does not verify each replica is repaired or data-consistent.

## 5. From Symptoms to a Falsifiable Hypothesis

Before changing any parameter, write the statement in this form:

> **Under [workload and topology], because of [bottleneck evidence], changing [one variable X from value A to B] will improve [target metric] by at least [quantified amount] without violating [guardrails].**

Example:

~~~text
Symptom:
  Compaction.PendingTasks climbs across multiple daily peaks.
  SSTablesPerReadHistogram and read p99 rise.

Hypothesis:
  Compaction is hitting the configured throughput cap.
  Disk/CPU still retain headroom while compaction is active.

Intervention:
  Raise throughput cap on 1 canary node from old runtime
  value C0 to C1, without changing concurrency.

Target:
  Pending compactions trend downward without increasing
  read/write p99, timeouts, disk await, or disk usage.

Falsification condition:
  Pending does not drop despite throughput staying below cap,
  or p99/disk await worsen right as the cap rises.
~~~

If you have not verified compaction is actually **hitting its cap**, you have no solid basis to raise it. If the disk is already saturated, the hypothesis "raising compaction throughput speeds things up" can actually invert in reality.

### 5.1. "One Variable" Is Not Always Just "One Number"

Editing `cassandra.yaml` may require a **node restart**: the restart itself empties caches, forces connection pool rebuilds, and temporarily reduces replica availability. Then the test mixes **tuning + restart effects**; you need warm-up time and suitable control nodes.

Likewise, changing cache size affects page cache/GC over time; raising concurrent compaction workers impacts both CPU and disk. Never use a 30-second window right after a restart as your "post-tuning" result.

### 5.2. Every Hypothesis Needs Negative Guardrail Metrics

Do not list only the metric you want to improve; list the metrics that **must not degrade**:

- `PendingCompactions` drops while `read p99` climbs → fail.
- `MemtablePool.BlockedOnAllocation` drops while `SSTable count` and disk backlog grow unchecked → fail.
- CPU utilization climbs without higher **completed throughput** while errors rise → fail.
- Java client timeouts drop via aggressive retries that overload the cluster → must inspect physical attempts.

## 6. Classify Reversibility Before Making Changes

| Change Class | Examples | How to Revert | Commonly Overlooked Risk |
|---|---|---|---|
| **Runtime setting with symmetric API** | `nodetool setcompactionthroughput` | Re-apply the **previously read value** and verify via `get` | Runtime value may differ from YAML; restarts can revert it |
| **File/JVM setting requiring restart** | Memtable allocation, heap/GC flags, some thread counts | Restore old config, **controlled rolling restart** | Cold caches, reduced UP replicas, recovery time |
| **Java Driver / app setting** | Retries, pools, timeouts, page size, metrics | Feature flag/redeploy/config reload per app support | Connection storms, retry storms, altered CL |
| **Table schema / compaction strategy** | `ALTER TABLE ... WITH compaction = ...` | Not a simple "flip back": SSTables/data may already be rewritten | Background compaction, I/O, file formats, existing data |
| **Data model / TTL / retention** | New tables, changed TTLs, deletes | Requires backfill/restore from source of truth | Purged data and tombstones do not return automatically |
| **Topology / RF** | Bootstrap/decommission, `ALTER KEYSPACE` | Dedicated data workflow: streaming, repair/rebuild | Config rollback does not restore prior replica placement |

**A rollback is a second production change.** For simple runtime knobs, fast reversal is straightforward. For schemas, data, and topology, simply "restoring the old number" may **not restore** prior data layout or state.

### 6.1. Defining Rollback Precisely

- **Configuration rollback:** reverting runtime/file/driver parameters.
- **Operational rollback:** halting rollout without touching more nodes; possibly restoring prior capacity or traffic modes.
- **Data rollback:** returning data to valid logical state via source of truth/backups/replay—never an automatic config step.
- **Forward fix:** when reversing is unsafe, hold state and deploy a dedicated forward remediation plan.

Every change request must specify the **applicable rollback class** and escalation triggers if safe reversal isn't possible.

## 7. Designing a Controlled Change Experiment

### 7.1. Seven Components of an Auditable Change Proposal

An auditable proposal should specify at least:

1. **Component and scope:** Cassandra version, DC/node/rack/table/JVM service, config file or runtime API.
2. **Actual observed old value:** e.g., runtime throughput cap `C0`, not just what docs say.
3. **New value and rationale:** `C1` grounded in capacity measurements, not a number that "sounds fast".
4. **Falsifiable hypothesis:** target metric and concrete evidence that would disprove the prediction.
5. **Baseline and comparison:** workload window, SLOs, histograms, node/resource metrics, data checks.
6. **Execution / observation:** owner, concurrency limits, canary, and expansion plan.
7. **Rollback / escalation:** measurable triggers, exact revert commands/paths, verification steps, and stop criteria.

This is the structure of a rigorous experiment, not bureaucratic paperwork. If targets and rollback triggers are undefined, **do not deploy**.

### 7.2. Controlled Rollout Order Across Nodes and Racks

~~~text
                           PROPOSAL
                              |
                    Baseline + value C0
                              |
                      Preflight checks
                              |
                    +---------+--------+
                    |                  |
                  PASS               FAIL
                    |                  |
                 Canary          ABORT/DEFER
                 1 node
                    |
           Observe guardrails over enough samples
               /                \
             PASS              BREACH
              |                  |
          Expand by            Revert C0
          batch/rack           and verify
              |                  |
        Re-check workload     Investigate root cause
              |
         Complete + document
~~~

**Never deploy simultaneously to all replicas of the same token range.** For instance, with RF=3 in one DC, if restarts are required, take down at most one node at a time while ensuring the remaining two replicas are healthy enough for `LOCAL_QUORUM`. Check rack/DC placement and any degraded nodes rather than judging risk solely from "we have three nodes".

Even for non-restarting runtime knobs, canarying one node still affects **queries hitting replicas on that node**; remaining nodes are **not an isolated control group**, because they replicate data together and share coordinators/traffic.

### 7.3. Why Compare Under Equivalent Workload?

Suppose pre-tuning saw 1,000 QPS at 100 ms p99, and post-tuning saw 250 QPS at 40 ms p99. That proves nothing about tuning: a 4x QPS drop explains most of the difference.

A rigorous comparison requires:

- Matching **query families** and read/write mix, not just aggregate QPS.
- Bounding variance in **peak QPS, payloads, hot partitions, page size, and consistency level**.
- Matching **warm cache** state, or explicitly separating cold vs warm runs.
- Sufficient sample counts for p99—never publish p99 from a few dozen requests.
- Tracking background work: repair, compaction, bootstrap, backups, streaming, and OS cron jobs.
- Watching resource pressure on **both the canary node and peer nodes**.

When production loads aren't comparable, run **staging benchmarks on representative datasets**, then canary carefully in production—never inject artificial massive traffic into live production just to get a clean benchmark.

### 7.4. Controlling Confounders

| Confounder | Impact | Mitigation |
|---|---|---|
| Mandatory rolling restart | Cold caches, rebuilt pools | Allow warm-up; never measure right after node UP |
| Compaction nearly finished pre-change | Pending may drain naturally | Use control windows; watch throughput and task counts |
| Concurrent node repair/bootstrap | Consumes disk/network outside baseline | Defer or record as an independent variable |
| App traffic dropped during rollout | P99 improves organically | Compare matching traffic buckets / peak hours |
| Different daily TTL/delete bursts | Different tombstones and disk scans | Check dataset/time buckets and workload mix |
| Java retry policy changed simultaneously | Physical attempts change | Freeze driver policies while testing server knobs |
| Raising RF or changing CL | Changes replica read/write count | Never treat as an apples-to-apples comparison |

## 8. Defining Stop/Rollback Criteria Before Making Changes

### 8.1. Three Guardrail Tiers

| Tier | Example Condition | Action |
|---|---|---|
| **Data safety / quorum** | Missing replicas prevent target CL, wrong reads/writes, unexpected node DOWN | **Stop immediately** and escalate to incident runbook; roll back only if reversal is safe |
| **Application SLO** | P99 breaches SLO; timeout rate climbs steadily; `Unavailable` errors | Halt expansion and roll back canary per approved thresholds |
| **Resources** | Free disk critically low, disk await/GC spikes, non-draining queues, sustained CPU throttling | Halt expansion; analyze and roll back if caused by the change |

**A critical safety trigger may demand immediate rollback**, without waiting three windows. Conversely, a slightly elevated p99 histogram across 20 samples may not justify rollback; specify minimum sample counts, severity, and observation intervals.

### 8.2. Example Rollback Thresholds with Units and Time Windows

Assuming **hypothetical figures** for family `order.getById` at peak:

| Metric | Baseline | Illustrative Canary Guardrail |
|---|---:|---|
| `read p99` | 85 ms | Stop if `>120 ms` across **three 5-minute windows** at equal load, or hard SLO breach |
| `write p99` | 75 ms | Stop if `>110 ms` across **three 5-minute windows** |
| `client timeout rate` | 0.05% | Roll back if `>0.5%` across **two 5-minute windows** with sufficient samples |
| `Unavailable errors` | ≈0 | Investigate immediately on abnormal spikes affecting CL |
| `disk await p95` | 8 ms | Halt expansion if sustained `>18 ms` alongside growing compaction |
| `free disk` | 40% | Do not proceed if dropping below approved safety floor (e.g., 25%) |
| `Compaction.PendingTasks` | 20, oscillating with bursts | Target downward trend; never treat one 20→19 tick as proof |
| `GC pause p99` | 15 ms | Stop if exceeding approved GC budget |
| `node UP/NORMAL` | 3/3 | Do not proceed if any node goes down unexpectedly |

These figures are **purely illustrative** to show a guardrail has **units, baseline, threshold, window, and action**. They are **not Apache recommendations**. Financial/real-time systems may enforce far tighter triggers; batch clusters may differ.

**Key point:** Even if `read p99=125 ms` still sits below an absolute `150 ms` SLO, it can violate the tuning **non-regression threshold**. The goal is not burning an API's entire error budget to flatter another metric.

### 8.3. Linking Thresholds to Causal Relationships

A good trigger links **the change** to **target signals and side effects**:

~~~text
Tuning: raise compaction throughput C0 -> C1

Acceptance criteria:
  pending compactions drop steadily across multiple windows
  AND compaction bytes/sec rises meaningfully
  AND read/write p99 do not degrade
  AND disk await/free and timeouts stay inside guardrails

Rollback:
  p99 or disk latency breaches threshold long enough
  OR any serious safety violation appears
  OR throughput cap rises without draining backlog
     while resource cost clearly climbs
~~~

Avoid vague triggers like "system feels sluggish" or "pending isn't 0 after two minutes". Large SSTable compactions can run for hours; pending is a **task estimate**, not a precise ETA.

### 8.4. Rollback Plans Need "Do-Not-Auto-Rollback" Conditions

Not every failure should blindly execute the reverse command right away:

- Node is mid-**bootstrap/decommission**: reversing topology mid-flight can spawn extra streaming and ownership chaos.
- **Wrong data or tombstone** issue occurred: config rollback will not recreate deleted data.
- A node is DOWN and quorum is degraded: rolling-restarting "to restore a config file" can make the cluster **even more unavailable**.
- A compaction/schema change already wrote new SSTables: flipping the strategy back does not instantaneously revert rewritten files.

In those cases, **halt rollout, preserve state, declare an incident, and follow dedicated recovery runbooks**. "Rollback" must never be an unconditional shell script fired by an alert.

## 9. Which Setting to Try First? Resource-Based Risk Matrix

### 9.1. Pre-Tuning Decision Table

| Suspected Bottleneck / Resource | Supporting Signals | Possible Change Direction | Risks / What to Check |
|---|---|---|---|
| Compaction capped too low | `PendingTasks` rises, throughput hits cap, disk/CPU have headroom | Moderately raise `compaction_throughput` | Contending with reads/flushes and SLA |
| Disk genuinely saturated | High disk await and queues, I/O contention | Throttle/schedule background jobs, inspect capacity/disk layout | **Never** raise all throughput caps |
| Memtable flushing lagging | `PendingFlushes`, `MemtablePool.BlockedOnAllocation`, flush pool pending rise | Inspect disk, memtable budgets; consider `memtable_flush_writers` | More flush writers can multiply small SSTables/compaction |
| Compaction concurrency short | Pending tasks climb, disk/CPU have headroom, few active tasks | Check `concurrent_compactors` per version | CPU/disk saturation, concurrent multi-file writes |
| Large GC pauses, heap pressure | High GC pause p99, heap occupancy, allocation pressure | Review heap sizing/GC flags/JDK per runbook | Restarts, cold caches, smaller off-heap/page cache |
| Commit log waits | `CommitLog.WaitingOnCommit`/`WaitingOnSegmentAllocation` rise | Inspect commit log disk, sync mode, and space | Changing durability/sync requires validating data guarantees |
| Cache misses / high read I/O | High read p99 and disk reads, low key cache hits | Review key/row cache suited to workload | Caches eat RAM; cold restarts |
| Java Driver pool/in-flight overloaded | High pool in-flight/retries/client timeouts | Cap concurrency, tune pools/retries with evidence | Retry storms, inflated attempts, changed CL |
| Hot partition / wide rows | A few token ranges very hot, high tombstones/read | Redesign partition/bucket/schema | Backfill/dual-write/semantics—not just a knob |
| Node/rack lacks capacity | Multiple nodes above disk/CPU ceilings | Scale capacity per runbook | Bootstrap/streaming and metadata refresh |

**There is no universal parameter tuning order for every cluster.** A time-series TTL/TWCS workload differs completely from transactional point lookups under LCS; follow evidence, not "top 10 configs to crank up".

### 9.2. Runtime Example: Compaction Throughput

~~~bash
# Observe the CURRENTLY ACTIVE value on the exact canary node.
nodetool getcompactionthroughput

# Check your running version's syntax, units, and limits.
nodetool help setcompactionthroughput
~~~

In Cassandra 5.0, `nodetool setcompactionthroughput` takes limits in **MiB/s**, and `0` typically **disables throttling** (unlimited)—not "stop compaction". Older releases display/name units differently; verify before executing.

**Reference lab command, not a recommended production value:**

~~~bash
# Only after recording C0 and holding operational authorization.
nodetool setcompactionthroughput 32

# Verify runtime actually accepted C1.
nodetool getcompactionthroughput
~~~

Changing a throughput cap **creates zero physical bandwidth**. If the disk is saturated, raising the cap simply increases contention with CQL/flushes. Conversely, if the cap is genuinely too low while disks sit idle, a moderate bump can drain backlogs.

### 9.3. Example Requiring Restart: Memtable Flush Writers

Some flush/JVM limits live in `cassandra.yaml`/JVM options. Applying them can require a **node restart**, and defaults vary across Cassandra versions:

~~~yaml
# Syntax illustration to spot in config; DO NOT copy this number
# to production without evaluating data directories and disks.
memtable_flush_writers: 2
~~~

Before changing, verify:

- Flush queues are **genuinely** climbing and `BlockedOnAllocation` occurs.
- Writers are actually saturated rather than disks or post-flush stages being slow.
- Each disk/data directory's real performance.
- Whether more writers create smaller SSTables and inflate `PendingCompactions`.
- Whether rolling restarts preserve RF/CL and allow proper warm-up time.

Never treat a parameter's presence in a file as proof it **hot-reloads**; verify exact restart requirements for your version.

### 9.4. JVM Heap/GC and Off-Heap Data

For example, an 8 GiB JVM heap **does not mean** Cassandra uses only 8 GiB of RAM. Off-heap memtables/buffers, OS page cache, direct memory, and native overhead also consume RAM. Enlarging the heap can shrink effective page cache and make SSTable reads slower.

Any heap/JDK/GC change:

1. Must verify JVM flags, container/cgroup limits, OS RAM, and page cache.
2. Needs baselines for allocation rate, GC pauses, heap occupancy, and direct memory.
3. Requires rolling restarts—never edit multiple nodes simultaneously if replica safety is tight.
4. Must not compare p99 immediately after restart against pre-change warm-cache numbers.
5. May require rollback if GC pressure eases yet disk read latency climbs persistently.

**Never swap GC collectors using one flag from an old blog post**: Cassandra versions and JDK compatibility must match official operational docs.

### 9.5. Driver Tuning Also Needs Baselines

For Java Driver 4.x:

- `request.timeout`: never raise unboundedly to mask bottlenecks.
- Page size: balance fetch round trips against response size and client memory.
- Retry policy / speculative execution: verify **idempotency** and physical attempt counts.
- Pools / concurrency: track in-flight load, saturation, and reconnects.
- CL / serial CL: keep aligned with the data contract—never "tune" by weakening guarantees.
- Local DC / token map: routing bugs can send queries cross-DC or to suboptimal coordinators.

When editing Java Driver settings, verify whether they reload dynamically or require **session rebuild / app redeploy**. Editing an external file does not guarantee a running driver session picks it up.

## 10. Is a Single-Node Canary Always Safe?

No. Canarying aims to **limit blast radius**, yet Cassandra uses **replication** and shared workloads:

~~~text
                       RF=3, DC=dc1
                      query tenant-a
                            |
                      Coordinator B
                            |
                 +----------+----------+
                 |          |          |
             Replica A  Replica B  Replica C
               canary      old        old
               cap C1    cap C0     cap C0
                 |          |          |
                Disk       Disk       Disk

A coordinator may wait on replica A for quorum.
Canary A affects end-to-end queries even when the app
never sends CQL directly to A.
~~~

### 10.1. How to Select a Canary Node

- Node is UP/NORMAL with no active streaming, repair, or failing disk.
- Representative hardware, disk tier, data directories, and workload of target nodes.
- Per-node metrics and verifiable partition/query sets are available.
- Not in a rack/DC already short on replicas or scheduled for maintenance.
- On-call operator available with a tested rollback path ready.
- Does not hold the sole surviving copy of critical data peers cannot recover.

On tiny clusters with RF=1 or RF=2, rolling restart impact differs sharply. Never follow an RF=3 canary playbook while ignoring actual replica placement.

### 10.2. Recommended Rollout Sequence

| Phase | Scope | Gate to Advance |
|---|---|---|
| Baseline | No changes | Sufficient per-node/query-family data and `C0` recorded |
| Canary | One node or one controlled app instance | Zero guardrail breaches; enough samples and load |
| Comparison | Canary vs baseline + peer nodes | Primary gain measured with zero adverse side effects |
| Batch 1 | Small subset across safe racks/replicas | Quorum and capacity remain safe; metrics steady |
| Next batches | Monitored expansion | Zero accumulating errors over time |
| Completion | Full target scope | Consistent runtime configs, stable SLOs, no missed nodes |

Some adjustments show **delayed** effects (cache warm-up, compaction backlogs, SSTable rewrites). Canary duration must be long enough to expose those effects—never apply a rigid "5 minutes is enough" rule to every knob.

## 11. Proper Rollback: Restoring Operational State, Not Just Running the Reverse Command

### 11.1. Rollback Flow for a Runtime Knob

~~~text
Metric breaches guardrail or experiment fails
                         |
                   HALT RAMP-UP
                         |
           Verify node/quorum safety first
                /                   \
              YES                   NO
               |                     |
      Re-apply runtime C0      Separate incident response:
               |               do not restart/stream blindly
        Read effective value         |
               |                  Escalation
       Wait for settling time
               |
       Measure SLO + resources
               |
        Recovered to baseline?
          /            \
        YES            NO
         |              |
   Record rollback   Continue investigating
     succeeded       the real bottleneck
~~~

**Distinguish "set command returned success" from "system recovered".** If a compaction backlog accumulated or disks filled up, restoring the cap may not return p99 to baseline instantly. Already-scheduled tasks need time to drain. Always monitor post-rollback recovery.

### 11.2. Runtime Rollback of Compaction Throughput

Suppose pre-canary `nodetool getcompactionthroughput` confirmed `C0=64 MiB/s` (illustrative), and you tested `C1=96 MiB/s` on node A:

~~~bash
# Approved change:
nodetool setcompactionthroughput 96
nodetool getcompactionthroughput

# When guardrail breaches:
nodetool setcompactionthroughput 64
nodetool getcompactionthroughput
~~~

**Never** copy 64/96 into production unless those were the exact values read. Success means **effective runtime cap returned to C0** on the right node while p99, timeouts, disk await, and backlog recover as expected. If `C0=0` meant unlimited beforehand, understand the consequences before restoring. Save *verbatim output* of the old value with units and version.

### 11.3. Rollback for Configs Requiring Rolling Restarts

~~~text
Canary node A updated cassandra.yaml and restarted.
Experiment fails.

1. Halt rollout to B/C.
2. Verify cluster retains enough replicas to restart A again.
3. Restore backed-up/committed old config on A.
4. Verify config diff and version restart rules.
5. Perform controlled restart of A (never take B/C down too).
6. Wait for A UP/NORMAL, client pools healthy, warm caches.
7. Verify effective runtime value, SLOs, disk/GC, and data.
~~~

If node A fails to return UP/NORMAL or CL can no longer be met, **stop restarting any other nodes**. Open an availability incident and protect replicas before touching anything else.

### 11.4. Rollback for Java Driver Settings

If testing higher retries or pool sizes in a Java service:

1. Halt rollout/canary and record commit/config versions and feature flags.
2. Revert config values or redeploy the previous release per procedure.
3. Verify sessions applied the config; editing a file doesn't guarantee live sessions reload it.
4. Monitor `connected-nodes`, pool in-flight, physical attempts, client timeouts, and latency.
5. Avoid **restarting all instances at once**, which triggers connection storms and spikes Cassandra load.

For `consistency level` or mutation retry changes, assess **which requests may have executed despite client timeouts** before re-running anything; rely on idempotency and business auditing.

### 11.5. When "Rollback" Must Become Recovery

| Change | Why Reverting Old Config Isn't Enough | Action Path |
|---|---|---|
| `ALTER KEYSPACE` changing RF | Replica sets/data moved; new copies need repair/streaming | Use dedicated replication runbook; verify full data before/after |
| Decommission / replace node | Token ownership and data streamed | Use safe bootstrap/rebuild/replace; never re-attach old node blindly |
| Lowering `gc_grace_seconds` then compaction purges tombstones | Deletion markers may already be gone | Investigate zombies; repair/restore from source of truth |
| Schema drop / TTL delete | Deleted data does not regenerate | Backups/CDC/audits, backfill, or selective restore |
| Changing compaction strategy | SSTables already rewritten in background | Verify compatibility, reverse migration plan, and headroom |
| Changing partition key via new table | Old/new tables hold separate data and write streams | Dual-write/dual-read, backfill, reconciliation, and feature flags |

**Never mark a data-affecting change as "fully reversible" just because CQL `ALTER TABLE` accepts the old setting.**

## 12. Production Runbook: Before, During, and After Tuning

### 12.1. Preflight: Prerequisites to Start

1. **System healthy:** no nodes unexpectedly down, mid-bootstrap/replace, or failing critical repairs.
2. **Configs confirmed:** old value `C0` read from both runtime and config management, knowing precedence/JVM overrides.
3. **Time-series baseline:** matching workload, QPS/CL, latency histograms, errors, CPU/disk/GC, queues, and free disk.
4. **Data risk check:** does the change touch RF, tombstones, TTLs, schema, or cleanup? If yes, separate runbooks.
5. **Proper approvals:** especially for runtime JMX, config restarts, network changes, or data-touching tasks.
6. **Rollback rehearsed:** exact commands/configs to restore `C0`, assigned owner, and non-reversible escalation path.
7. **Sensible change freeze:** avoid overlapping bulk ingests, migrations, topology shifts, or another tuning test that muddies comparisons.
8. **Observability and comms:** per-node/DC dashboards, business owner, on-call engineer, and decision checkpoints.

### 12.2. During Execution

~~~text
T0  Capture baseline + verify C0 on node
T1  Preflight: ring/replicas/disk/CL pass
T2  Apply C1 change on canary
T3  Read back effective value; log event/UTC timestamp
T4  Observe warm-up/batches for enough samples per knob type
T5  Cross-check SLOs, resources, and correctness
T6  If passing: expand in small batches, repeating T3–T5
T7  If failing: halt expansion, roll back, or escalate
T8  Complete: verify config consistency across all nodes, long-term monitor
~~~

Never hardcode T3–T5 as "wait exactly 60 seconds": caches, compaction, and periodic traffic react on different timescales. **Sufficient samples and representative workload coverage** matter far more than a fixed timer.

### 12.3. Decision States

| State | Evidence | Action |
|---|---|---|
| `GO` | Valid baseline; canary better/non-regressing; zero guardrails tripped | Expand batch-by-batch |
| `HOLD` | Insufficient samples, workload shifted, conflicting signals | Keep canary scope, continue observing/investigating |
| `ROLLBACK` | Clear side effects, quantitative trigger fired, and config reversal is safe | Restore `C0`, verify runtime and SLOs |
| `ESCALATE` | Quorum/replicas at risk, wrong data, mid-stream/schema change, or rollback unsafe | Stop; handle via dedicated incident runbook |
| `CANCEL` | Hypothesis disproven or benefit too minor | Do not roll out; record lessons |

### 12.4. Closing the Change

Close only when:

- Every target node/JVM has its **effective config** verified—not just a Git commit.
- Target metrics improved or met defined thresholds.
- Zero SLO or resource regressions in other query families.
- Ring/replicas/repair show no new errors.
- Sample CQL queries return correct results against business truth.
- If rolled back: `C0` verified active and system recovered—not just the set command exiting 0.
- Final report covers root cause, results, remaining growth headroom, and ongoing monitoring plan.

## 13. Quantifying Results Without Confusing Latency with CPU

### 13.1. Pairing Target + Guardrail Metrics

Example for compaction tuning:

~~~text
Primary objective:
  Per-node/table pending compactions drop toward baseline
  or stop climbing during business peaks.

Supporting:
  Compaction bytes/sec increases when cap rises.
  Live SSTable count / SSTablesPerRead do not worsen.

Guardrails:
  Read/write p95/p99 and timeouts stay within limits.
  Disk await, free disk, CPU, GC, memtable flushes stay safe.
  Zero UNAVAILABLE replicas; no node drops from the ring.
~~~

One target metric dropping is insufficient: if `PendingCompactions` fell because **compaction was disabled or ingest stopped**, that is not tuning success.

### 13.2. Distinguishing Rates from Point-in-Time Gauges

| Metric | Typical Type | Proper Analysis |
|---|---|---|
| `Compaction.PendingTasks` | Gauge/estimate | Trend, max, backlog duration |
| `Table.PendingFlushes` | Pending metric with version/exporter-specific semantics | Track pending counts and flush pools; never apply blind rates |
| `Compaction.BytesCompacted` | Counter | Bytes/sec across samples, handling restart resets |
| `ThreadPools.CompletedTasks` | Counter | Tasks/sec per exact pool |
| `ClientRequest.*.Timeouts` | Counter/meter per exporter | Error rate/sec or ratio over request count |
| CPU | Gauge (% or normalized cores) | p95/windowed; never confuse host vs container |
| Free disk | Gauge (bytes, %) | Absolute headroom and trend |
| p95/p99 latency | Histogram/timer/distribution | Properly merge histograms with sample counts |

**Never average per-pod p99s** to report service p99, and never subtract percentiles from different layers to compute network latency. Use correlated traces/metrics over the same requests and time windows.

### 13.3. Intuitive Queue Model

If compaction tasks arrive at `λ` tasks/s and drain at `μ` tasks/s, backlog grows when `λ > μ` persists. Yet tasks vary widely in bytes/cost, so `PendingTasks / completed_tasks_per_second` **is not a reliable ETA in all cases**.

Better checks:

1. Compare **bytes compacted/sec**, CPU/disk throughput, and compaction types.
2. Track SSTable counts and per-table read amplification.
3. Verify whether backlogs actually drain after peak workloads.
4. Watch client p99 and timeouts in the same window.
5. Accept that one huge long-running compaction can keep pending counts low while still burning I/O.

### 13.4. Illustrative Before/After Chart

| Metric | Baseline | Canary C1 | Post-Rollback C0 | Hypothetical Conclusion |
|---|---:|---:|---:|---|
| Pending compactions post-peak | 30 | 12 | 29 | C1 shrunk backlog |
| Compaction bytes/sec | 40 MiB/s | 80 MiB/s | 42 MiB/s | C1 raised throughput |
| Read p99 | 85 ms | 160 ms | 88 ms | **Breached guardrail**, rollback needed |
| Write p99 | 75 ms | 115 ms | 76 ms | Worsened and recovered after rollback |
| Disk await p95 | 8 ms | 25 ms | 9 ms | Strong I/O contention hypothesis |
| Timeout rate | 0.05% | 0.6% | 0.07% | Climbed past threshold |

**All figures are purely hypothetical.** The trial failed even though compaction backlog dropped. The right call is restoring C0 and investigating storage capacity/traffic—never claiming "compaction tuned" from one isolated metric.

## 14. CQL/`nodetool` Lab: Changing Compaction Cap and Reverting

**Objective:** Practice the sequence **baseline → record C0 → set C1 → verify runtime → measure → restore C0 → verify rollback** on a test node. You do not need to force a backlog: a tiny lab cluster may show 0 pending compactions in both states. Lab success is **mastering the controlled workflow**, not manufacturing I/O saturation.

**Environment:** Cassandra 4.1/5.0 **single-node lab cluster**, `cqlsh`, `nodetool` with admin access to that node. Never alter production throughput just as an exercise. If running a Cassandra version with different unit conventions, follow `nodetool help` and that version's docs.

### Step 1 — Create Isolated Data Separate from Other Systems

~~~sql
CREATE KEYSPACE IF NOT EXISTS resource_tuning_lab
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS resource_tuning_lab.events_by_tenant_day (
    tenant_id text,
    day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);

CONSISTENCY ONE;

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
        11111111-1111-1111-1111-111111111111, 'created');

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
        22222222-2222-2222-2222-222222222222, 'paid');

INSERT INTO resource_tuning_lab.events_by_tenant_day
    (tenant_id, day, event_time, event_id, payload)
VALUES ('tenant-b', '2026-11-21', '2026-11-21T08:10:00Z',
        33333333-3333-3333-3333-333333333333, 'created');

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';
~~~

**Limitation:** `SimpleStrategy` RF=1 is only for a single-node lab cluster. Multi-DC production requires `NetworkTopologyStrategy`/proper RF and app-aligned CL. With three tiny rows, there is **insufficient** data for real compaction benchmarking.

### Step 2 — Capture Baseline and Back Up the Old Value

~~~bash
nodetool version
nodetool status
nodetool getcompactionthroughput
nodetool compactionstats
nodetool tpstats
nodetool tablestats resource_tuning_lab.events_by_tenant_day
~~~

Save verbatim outputs, UTC timestamp, and `C0` from `getcompactionthroughput`. If `C0` is "unlimited" or 0, **record that explicitly**—never replace it with a guessed number. Add snapshots of free disk, CPU, GC, and CQL reads.

~~~text
LAB SHEET — lines to fill with real observations
  Node:
  Cassandra version:
  Effective C0 + units:
  Baseline timestamp:
  Pending compactions:
  Free disk / CPU / I/O:
  SELECT tenant-a result:
~~~

### Step 3 — Verify Commands on Your Exact Version

~~~bash
nodetool help setcompactionthroughput
nodetool help getcompactionthroughput
~~~

If your binary lacks the command, JMX permissions fail, or the node is unhealthy, **stop the lab** and complete only the analysis section. Never pivot to tweaking another config without knowing its rollback.

### Step 4 — Change One Runtime Knob in the Lab

~~~bash
# Example C1=32 MiB/s using Cassandra 5.0 syntax.
# DO NOT use this C1 as a recommendation for real clusters.
nodetool setcompactionthroughput 32

# Mandatory read-back of the active effective value.
nodetool getcompactionthroughput
~~~

**Do not** touch `concurrent_compactors`, `memtable_flush_writers`, CL, retry policies, or compaction strategy at the same time. Measuring real performance differences requires a large staging dataset and separate load test—never flood the lab disk to full capacity.

### Step 5 — Observe After the Change

~~~bash
nodetool compactionstats
nodetool tpstats
nodetool tablestats resource_tuning_lab.events_by_tenant_day
nodetool getcompactionthroughput
~~~

In `cqlsh`:

~~~sql
CONSISTENCY ONE;

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, payload
FROM resource_tuning_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Seeing `pending tasks = 0` at both points is **normal** for a tiny lab. The parameter changed, yet there isn't enough background work to produce a visible shift. Never conclude "32 MiB/s is optimal" or "the change does nothing" from three rows.

### Step 6 — Revert to C0, Never Use a Hardcoded Sample Value

Example **only if you recorded `C0=64 MiB/s` in baseline**:

~~~bash
# 64 only illustrates C0; replace with your ACTUAL C0 value.
nodetool setcompactionthroughput 64
nodetool getcompactionthroughput
~~~

If `C0` was not 64, that command **fails to revert properly**! Substitute the exact original value you recorded, or stop for assistance if `C0` is unknown. **Never skip the read-back step**, since command exit 0 does not guarantee you targeted the intended node.

### Step 7 — Compare Results and Write Conclusion

| Field | Before C0 | During C1 | After Rollback C0 | To Record |
|---|---|---|---|---|
| Time / Node | Baseline UTC | UTC after set | UTC after restore | Fill in |
| Effective throughput cap | C0 | C1 | **Equals C0** | PASS/FAIL |
| `PendingCompactions` | Snapshot | Snapshot | Snapshot | Trend if enough samples |
| `BytesCompacted/sec` | If compacting | If compacting | If compacting | Do not guess |
| Free disk / await | Baseline | Observed | Observed | No regression |
| CQL SELECT results | 2 / 1 sample rows | Unchanged | Unchanged | Correctness |
| Errors / Timeouts | Baseline | Observed | Observed | No increase |

**Lab passes when:** C0 was saved, C1 took effect, C0 was restored and verified, and CQL data stayed accurate. **Never** force a "C1 improved 20%" claim when data is insufficient.

## 15. Java Driver: Measuring the Same Request Before and After

Java apps should keep a fixed **query family** and identical CL/page size across baseline comparisons. The example below uses Java Driver 4.x; `CqlSession` is created once and reused across requests.

### 15.1. Sample Code Timing the Full Query, Not Just Request Start

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

public final class TuningReadProbe {
    public record ReadSample(
            long elapsedNanos,
            int returnedRows,
            List<String> payloads) {}

    private final CqlSession session;
    private final PreparedStatement readByDay;

    public TuningReadProbe(CqlSession session) {
        this.session = session;
        this.readByDay = session.prepare(
            "SELECT payload FROM resource_tuning_lab.events_by_tenant_day " +
            "WHERE tenant_id = ? AND day = ?");
    }

    public ReadSample readAll(String tenantId, LocalDate day) {
        BoundStatement statement = readByDay.bind(tenantId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE)
            .setPageSize(50);

        long start = System.nanoTime();
        ResultSet result = session.execute(statement);
        List<String> payloads = new ArrayList<>();
        for (Row row : result) {
            payloads.add(row.getString("payload"));
        }
        long elapsed = System.nanoTime() - start;
        return new ReadSample(elapsed, payloads.size(), payloads);
    }

    public static double elapsedMillis(ReadSample sample) {
        return sample.elapsedNanos() / 1_000_000.0;
    }
}
~~~

Example invocation given an initialized `session`:

~~~java
TuningReadProbe probe = new TuningReadProbe(session);
TuningReadProbe.ReadSample measured = probe.readAll(
    "tenant-a", LocalDate.parse("2026-11-21"));

System.out.printf(
    "duration_ms=%.3f rows=%d values=%s%n",
    TuningReadProbe.elapsedMillis(measured),
    measured.returnedRows(),
    measured.payloads());
~~~

Points to explain:

1. `System.nanoTime()` measures **elapsed duration** without wall-clock NTP jumps.
2. Iterating `ResultSet` fetches every required page to populate the list; timing only `execute()` misses subsequent page fetches.
3. `PreparedStatement` is prepared once; binding the partition key supplies routing information to the driver.
4. `CL=ONE` is **strictly for the RF=1 lab**—never use it by default when production requires `LOCAL_QUORUM`.
5. One sample is not p99. Emit **statistically sufficient histograms** to your metrics backend grouped by query family, DC, and outcome—including timeouts and failures.
6. This method **does not read Cassandra compaction metrics**. Pair it with JMX/`nodetool`, disk stats, and config change markers.

### 15.2. What Must Stay Constant During A/B

| Property | Why It Must Not Change Mid-Test |
|---|---|
| `LOCAL_QUORUM` / `ONE` | Changing CL alters replica contracts and latency |
| Page size, `LIMIT` | Changes row counts and network round trips |
| Prepared vs simple statement | Changes routing key / token-aware behavior |
| Driver retry / speculative policy | Changes attempt counts and server load |
| Local datacenter | May shift requests to another DC |
| Dataset size / hot-key distribution | Changes read amplification and caches |
| JVM version / service release | Alters GC/connection behavior and app overhead |

**Never treat faster queries after lowering CL as proof compaction tuning helped.** When testing compaction caps, freeze CL and statements.

### 15.3. Export Histograms Instead of Printing One Line

In real apps, use Micrometer/OpenTelemetry/driver metrics cleanly. Per-query-family metrics may look like:

~~~text
app_cql_requests_total{service,query_family,outcome,dc}
app_cql_duration_seconds_bucket{service,query_family,dc,le}
app_cql_timeouts_total{service,query_family,dc}

datastax_driver_session_cql_requests_... (name depends on exporter)
datastax_driver_node_cql_messages_...   (name depends on exporter)
~~~

These names are **design patterns**, not a claim that exporters produce these exact series automatically. Never put raw CQL, partition keys, emails, or tenant IDs in metric labels due to cardinality and privacy risks.

When building dashboards:

- Aggregate histograms properly across JVMs; **never** average per-JVM p99 values.
- Annotate canary/rollback timestamps; compare at matching load and sample counts.
- Count errors/timeouts separately; success-only histograms hide outages.
- Track retries and pool in-flight counts to catch driver load amplification.
- Pair with coordinator/table p99 and CPU/disk/GC on natural replicas.

## 16. Case Studies: Choosing GO, HOLD, ROLLBACK, or ESCALATE

### Case A — Higher Compaction Cap Shrinks Backlog Yet Raises Read Latency

**Hypothetical baseline:** Node A has 25–35 pending compactions; disk await p95 ~8 ms; read p99 ~85 ms. Compaction throughput hits its cap while CPU/disk show headroom in some windows.

**Canary:** Step up the cap once. Pending drops to 12, yet disk await climbs to 25 ms and read p99 hits 160 ms. Timeout rate rises.

**Decision:** `ROLLBACK` to C0. "Shrinking pending" is insufficient when SLOs and storage resources breach guardrails. Inspect disk throughput, compaction type, peak overlap, and task spread; you may need to **reschedule heavy compaction or upgrade capacity** rather than raising the cap further.

**Lesson:** The real bottleneck is **serving queries under total load**, not merely SSTable cleanup speed.

### Case B — Flush Backlog Drops Yet Tiny SSTables Multiply

**Baseline:** `MemtablePool.BlockedOnAllocation` appears, pending flushes grow in bursts, and operators suspect too few flush writers.

**Canary:** Raise flush writers and restart one node. In the first hour pending flushes drop, yet `LiveSSTableCount` and `PendingCompactions` start climbing sharply; read p99 worsens hours later.

**Decision:** If guardrails tripped, `ROLLBACK` the config via controlled rolling restart. If headroom remains and triggers weren't crossed, `HOLD` to gather more data since compaction reacts slowly. Never roll out cluster-wide based on the first 15 minutes.

**Lesson:** Tuning that **clears an upstream queue** can create **downstream** debt in an LSM engine.

### Case C — Bigger Heap Cuts GC Pauses Yet Increases Disk Reads

**Baseline:** High GC pause p99 and heap occupancy. Node has decent total RAM, yet the OS page cache had been serving hot SSTable reads.

**Canary:** Larger heap, restart node. GC pauses drop, yet disk read latency and `Table.ReadLatency` stay elevated post-warmup because page cache shrank.

**Decision:** `HOLD` to rule out temporary cold-cache warm-up; if sustained and SLOs breach, `ROLLBACK` JVM settings via rolling restart. Do not push heap higher.

**Lesson:** **JVM heap is not all of Cassandra's memory.** Balance heap, off-heap, and the OS page cache.

### Case D — Timeouts Drop After Aggressive Retries, Physical Attempts Surge

**Baseline:** Java service has read p99 near SLO with peak timeouts. A team enables broader retries/speculative execution without caps.

**Canary:** Client-visible timeouts drop slightly, yet `cql-messages`/`cql-requests` jump, pool in-flight and coordinator CPU surge, and node p99 worsens.

**Decision:** Halt rollout and roll back the policy or tighten concurrency per plan. Fix the real network/replica/storage bottleneck; for mutations, verify **idempotency** before retrying.

**Lesson:** Fewer client errors may merely mean **pushing cost onto the server**. Track both logical requests and physical attempts.

### Case E — File Config Updated Yet Runtime Still Holds Old Value

**Symptom:** `cassandra.yaml` holds the new cap/setting, yet `nodetool get...` still returns C0; operator concludes tuning had no effect.

**Likely causes:** Setting does not hot-reload, is overridden by JMX/system property, file wasn't deployed to the node, or node hasn't restarted.

**Decision:** `HOLD`, verify effective config and reload semantics on your exact version. **Never** tweak extra knobs just to make p99 move. If restart is required, redo preflight/rolling restart and warm-up; if unsafe, `CANCEL`.

**Lesson:** **Config source-of-truth** must be paired with **proof of effective runtime values**.

### Case F — Canary Node Fails and the Whole App Starts Timing Out

**Context:** RF=3, app uses `LOCAL_QUORUM`. Right as the canary restarts, another replica loses connectivity.

**Outcome:** Only one healthy replica remains for some ranges; `LOCAL_QUORUM` fails and requests time out / return `Unavailable`.

**Decision:** `ESCALATE` under the availability runbook. Stop all further rolling restarts; restore replica/driver connectivity first. Never "roll back by restarting another node", and never lower CL hastily.

**Lesson:** A restart-based rollback plan is safe only when **replica state at rollback time** permits it.

### Case G — Non-Comparable Baseline Because Bulk Ingest Ended During Canary

**Context:** Pre-tuning CPU p95 was 90%, post-tuning 50%. However, a bulk ingest job ended between windows.

**Decision:** `HOLD` or `CANCEL` performance claims; re-run under equivalent load. Never advertise a "40-point CPU drop" as a win from the new knob.

**Lesson:** Temporal correlation **is not enough** for attribution. Change markers and workload mix are mandatory baseline metadata.

### Case H — Lowering `gc_grace_seconds` to Free Disk Quickly

**Context:** Free disk shrinks; someone proposes lowering grace to purge tombstones sooner.

**Risk:** A replica that missed a `DELETE` may still hold stale data; if tombstones purge prematurely, repair **loses the deletion proof**, causing zombie data.

**Decision:** Do not treat this as simple reversible tuning. `CANCEL` or open a separate retention/repair and capacity workflow. Restoring grace afterward **cannot bring back purged tombstones**.

**Lesson:** Never trade **data correctness** for a prettier disk-usage graph.

## 17. Change Record Template and Post-Change Report

A change ticket should let someone uninvolved **reconstruct the exact decision**:

~~~text
CHANGE_ID: CASSANDRA-TUNE-EXAMPLE-017
OWNER / ONCALL: <assigned engineer/team per system>
ENV: staging
CLUSTER / DC / NODE: test-ring / dc1 / node-a
CASSANDRA / JDK / DRIVER: <exact versions>
CHANGE_CLASS: runtime-setting
SETTING: compaction throughput cap
PREVIOUS_EFFECTIVE_VALUE: C0 (read via nodetool)
PROPOSED_VALUE: C1 (per storage headroom)
WORKLOAD_WINDOW: equivalent peak (UTC, query families, QPS)
DEPENDENCIES: no overlapping topology/repair/backup changes

HYPOTHESIS:
  Throughput is hitting cap while disk still has headroom;
  raising cap will shrink pending compaction without hurting SLOs.

BASELINE:
  read/write p99, timeout%, QPS, physical attempts
  compaction pending + bytes/sec, SSTablesPerRead
  disk await/free, CPU, GC, memtable/commitlog
  ring status + RF/CL + sample CQL results

GUARDRAILS:
  sufficient sample counts, p99 non-regression threshold
  timeouts/unavailables, disk await/free, GC, replica health

CANARY PLAN:
  single node A; operator on-call; timestamp/command log
  change no other parameters simultaneously

ROLLBACK:
  set runtime back to exact C0; verify effective value
  verify ring, SLOs, and backlog post-rollback
  if quorum or data is at risk: ESCALATE

RESULT:
  GO / HOLD / ROLLBACK / ESCALATE / CANCEL
  effects/side effects by node and query family
  evidence links, residual risks, next review
~~~

Fields in `<...>` are **for operators to fill in**, not ready-to-run shell commands or outputs. Never store passwords, tokens, or raw CQL containing sensitive data in templates.

### 17.1. Example Completed Rollback Report

~~~text
CHANGE_ID: CASSANDRA-TUNE-EXAMPLE-018 (hypothetical)
Change: C0=64 MiB/s -> C1=96 MiB/s on node-a
Baseline peak:
  Read p99=85ms, timeout=0.05%, disk await p95=8ms
Canary (sufficient sample window):
  Read p99=160ms, timeout=0.60%, disk await p95=25ms
  Pending compactions 30 -> 12
Guardrail:
  p99 >120ms sustained; timeout >0.5%
Action:
  Halted rollout; setcompactionthroughput 64; verified C0
Post-rollback:
  Read p99=88ms, timeout=0.07%, disk await p95=9ms
Conclusion:
  Runtime ROLLBACK succeeded, SLOs recovering.
  Not rolled out to remaining nodes.
Residual risk:
  Backlog still grows at peak; needs capacity/compaction review.
~~~

All numbers above are **illustrative**, not real operational evidence. For real incidents, owners must attach metric links, traces/alerts, config diffs, and UTC timestamps.

### 17.2. What Proves "Rollback Is Complete"?

1. Effective values **returned to exact C0 across the entire modified scope**.
2. Nodes/ring/replicas remain available with no newly broken streams/repairs.
3. Query SLOs, timeouts, and resources returned to baseline—or any lingering drain is clearly accounted for.
4. Critical query families and data samples still return accurate results.
5. No config file or deploy pipeline will **re-apply C1 on the next restart**.
6. An owner is assigned to watch lingering backlogs/repairs.

If rollback updated only runtime state while config management still holds C1, nodes can **snap back to C1** on the next restart. Sync the source-of-truth config per policy, within authorized scope and permissions.

## 18. Common Mistakes During Tuning

| Mistake | Consequence | How to Avoid |
|---|---|---|
| Changing multiple parameters at once | Impossible to isolate causality | Test one variable per phase, log markers |
| Failing to record effective C0 | Unknown what value to restore | Read runtime and snapshot configs upfront |
| Comparing p99 once | Sampling bias, mismatched peaks | Multiple windows, sample counts, equivalent load |
| Excluding failures from histograms | P99 looks artificially better as timeouts climb | Pair error rates with latencies |
| Watching only cluster averages | Hot nodes / failing disks get masked | Drill down per node/DC/table |
| Raising all throughput caps | Intensifies disk/CPU contention | Identify real bottleneck and headroom |
| Raising flush writers on a saturated disk | Spawns extra SSTables, shifts backlog to compaction | Check disk/post-flush/blocked memory first |
| Watching only `PendingCompactions` | Hides task sizes and real I/O | Check progress, bytes/sec, `SSTablesPerRead` |
| Enabling unbounded retries | Retry storms and duplicate writes | Check idempotency, attempt counts, concurrency |
| Lowering CL to cut latency | Breaks consistency contracts | Keep CL fixed in equivalent tuning tests |
| Restarting all replicas together | Quorum loss / `Unavailable` | Rolling restart respecting topology and node health |
| Treating config files as runtime truth | Misreads active settings | Query live effective values |
| Changing `gc_grace_seconds` to reclaim faster | Zombie data risk | Use repair/capacity runbooks; protect tombstones |
| Running `nodetool compact` to "clear queues" | Major compaction spikes disk/I/O | Use only intentionally with ample headroom |
| Treating schema/RF rollback as one-line revert | Data/ownership already changed | Maintain dedicated migration/recovery plans |
| Stopping checks right after setting C0 | Backlogs/SLOs may not have recovered | Verify effective value and post-rollback trends |
| Failing to sync config management | Next restart silently re-applies C1 | Update source-of-truth and verify config diffs |
| Skipping data correctness checks | Fast system serving wrong data | Validate sample CQL, consistency, and business logic |

## 19. Operational Checklist: From Baseline to Safe Rollback

### 19.1. Before the Change

- [ ] Pinpointed the **bottleneck**, not merely noticed one elevated metric.
- [ ] Wrote a falsifiable **if X then Y** hypothesis grounded in metrics.
- [ ] Scoped **one knob** and explicit node/DC/service targets.
- [ ] Recorded Cassandra/JDK/Java Driver versions, RF, CL, data directories, and compaction strategy.
- [ ] Saved **effective C0**, config files/JVM flags/driver config, and rollback path.
- [ ] Baseline includes QPS, peak, query families, latency histograms, errors/timeouts, and resource metrics.
- [ ] Captured **per-node/table** breakdowns rather than cluster-wide averages alone.
- [ ] No active node/quorum faults, unfinished repair/streaming, or missing disk headroom.
- [ ] Data correctness checked against expected keys/samples from source truth.
- [ ] Defined guardrails with **thresholds, units, windows, and decision owners**.
- [ ] Distinguished config-only rollback from data/topology recovery.
- [ ] Planned canary, warm-up, batch expansion, and on-call coverage.

### 19.2. During Canary

- [ ] Annotated canary start on dashboards and logged exact commands.
- [ ] Read back **effective C1** to prove the knob actually changed.
- [ ] Collected enough samples/workload steady state; never compared cold vs warm cache.
- [ ] Watched both primary metric and side-effect metrics over the same window.
- [ ] Tracked physical retries/requests in Java Driver, not just logical QPS.
- [ ] Verified replica health and quorum after every restart step.
- [ ] Avoided concurrently raising concurrency or altering schema/CL outside test design.
- [ ] Ready to pick `GO`, `HOLD`, `ROLLBACK`, or `ESCALATE` strictly from data.

### 19.3. Post-Rollout or Rollback

- [ ] Verified every node in target scope holds the exact expected effective setting.
- [ ] Confirmed p95/p99, timeouts, error budgets, and CQL data show zero regression.
- [ ] Checked disk await/free, CPU, heap/GC, memtables, commit log, and compaction backlog.
- [ ] Observed long enough for delayed effects: compaction, caches, SSTables.
- [ ] If rolled back, confirmed C0 via GET and ensured config management won't overwrite it back to C1.
- [ ] If recovery was needed, opened a dedicated ticket/runbook—never marked "rollback complete" without proof.
- [ ] Published change report, lessons learned, and next review date.

## 20. Self-Assessment Questions

**Question 1.** Why doesn't read p99 dropping after QPS falls by half prove tuning succeeded?  
**Guidance:** Workload was not equivalent; lower load independently explains lower latency.

**Question 2.** If `PendingCompactions` drops while `read p99` and timeouts climb, can you pick `GO`?  
**Guidance:** No; guardrails were breached—trigger appropriate rollback or escalation.

**Question 3.** Why must you run `getcompactionthroughput` before `setcompactionthroughput`?  
**Guidance:** You must know the **currently active** C0 and exact unit to revert accurately; YAML files alone aren't enough.

**Question 4.** One node runs C1 while peer nodes keep C0. Can you compare that node against peers as a completely independent A/B test?  
**Guidance:** No; replicated reads/writes, coordinators, and traffic couple multiple nodes together.

**Question 5.** With RF=3 and `LOCAL_QUORUM`, what happens if the canary restarts right as another replica goes down?  
**Guidance:** Two replicas may no longer be reachable, causing `Unavailable`; halt rolling restarts.

**Question 6.** Why shouldn't you increase `memtable_flush_writers` when the disk is already saturated?  
**Guidance:** Extra workers add zero disk bandwidth and can multiply small SSTables and compaction contention.

**Question 7.** Why can enlarging the JVM heap sometimes worsen read p99?  
**Guidance:** Competes for RAM with off-heap/OS page cache, alters GC, and introduces cold-restart effects.

**Question 8.** Why shouldn't `Compaction.PendingTasks` be treated as seconds of backlog remaining?  
**Guidance:** Tasks vary widely in size; pending is an estimate—inspect progress, bytes/sec, and strategy.

**Question 9.** Does `nodetool setcompactionthroughput 0` "stop compaction"?  
**Guidance:** On documented versions, `0` **removes the throughput cap** (unlimited), rather than stopping compaction.

**Question 10.** `cassandra.yaml` was edited yet runtime GET still returns C0. Should you declare tuning failed?  
**Guidance:** Not yet; check reload/restart rules and overrides, and confirm the change actually took effect.

**Question 11.** Is lowering consistency level to hit target p99 an equivalent tuning comparison?  
**Guidance:** No; it alters data/replica guarantees and must be evaluated as a consistency contract change.

**Question 12.** Why can't you roll back lowering `gc_grace_seconds` merely by restoring the old number?  
**Guidance:** Already-purged tombstones do not return, leaving zombie data risk intact.

**Question 13.** If a canary required a node restart, when should you measure post-change p99?  
**Guidance:** Only after the node/pools are healthy and caches/workloads stabilize—never during cold start.

**Question 14.** Should you measure client retries and physical attempts when tuning driver configs?  
**Guidance:** Yes; retries can hide user timeouts while driving up server load and peer latency.

**Question 15.** Runtime rollback restored C0 yet p99 remains degraded. Can you mark "fully recovered"?  
**Guidance:** No; find why degradation persists and verify SLOs, resources, and data correctness.

**Question 16.** Why is reverting to C0 via JMX while leaving C1 in config management dangerous?  
**Guidance:** The next restart or deploy will silently re-apply C1, causing a repeat regression.

**Question 17.** When should you choose `HOLD` instead of `GO` or `ROLLBACK`?  
**Guidance:** Insufficient samples, mismatched load, caches still warming, missing data, or conflicting signals.

**Question 18.** Is shrinking a backlog via a one-off `nodetool compact` in production safe tuning?  
**Guidance:** No; forced major compaction can consume massive I/O/disk and needs clear justification, headroom, and a dedicated runbook.

**Question 19.** A Java query calls `execute()` and then iterates 20 pages. Where is a timer stopping right after `execute()` wrong?  
**Guidance:** It measures only up to the first page, omitting the cost of fetching the remaining pages.

**Question 20.** What minimum evidence proves a rollback succeeded?  
**Guidance:** Effective C0 restored, node health/quorum intact, SLOs/resources back in bounds, data accurate, and config management won't re-apply C1.

## 21. Summary

~~~text
                       RESOURCE TUNING
                              |
                     Capture BASELINE
                 workload / SLO / resources
                              |
                   State clear HYPOTHESIS
                         X: C0 -> C1
                              |
                 Guardrails and ROLLBACK
                    defined BEFORE T2
                              |
                          Preflight
                   node / replica / disk
                              |
                          CANARY C1
                              |
                   Read effective value
                              |
                 Enough samples / same load?
                   /                  \
                  NO                  YES
                  |                    |
                 HOLD             Check gates
                              /       |         \
                          DATA      SLO       RESOURCE
                              \       |         /
                                 Decision
                          /        |         \
                         GO     ROLLBACK    ESCALATE
                         |         |            |
                     Expand in   Restore C0   Recovery runbook
                      batches    + check SLO  when unsafe
                         |         |
                    Post-change monitoring
                              |
                  Evidence-backed report
~~~

**Core principle:** A Cassandra config change has value only when **you know how the system behaved beforehand**, **measure the cause and effect of the change**, **preserve data/consistency guarantees**, and **can restore a safe operational state** if results fall short. Sound tuning is not driving pending counts down at all costs; it is improving request service under representative load **without harming SLOs, replica health, data correctness, or incident recoverability**.

## References

- [Apache Cassandra — Configuration file (cassandra.yaml)](https://cassandra.apache.org/doc/stable/cassandra/managing/configuration/cass_yaml_file.html) — memtable, compaction, commit log, cache parameters, and version-specific changes.
- [Apache Cassandra — Monitoring metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html) — JMX Table, ClientRequest, CommitLog, Compaction, ThreadPools, and JVM metrics.
- [Apache Cassandra — Storage engine](https://cassandra.apache.org/doc/stable/cassandra/architecture/storage-engine.html) — commit log, memtables, SSTables, flushing, and compaction.
- [Apache Cassandra — Compaction overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html) — strategies, compaction overhead, and throughput.
- [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html) — replica synchronization, tombstone grace, and repair scope.
- [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) — zombie risk when tombstones are purged prematurely.
- [Apache Cassandra — Node operations / topology changes](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/topo_changes.html) — bootstrap, decommission, replace, streaming, and ring-change risks.
- [Apache Cassandra — nodetool getcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/getcompactionthroughput.html) — reading active compaction throttle.
- [Apache Cassandra — nodetool setcompactionthroughput](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/setcompactionthroughput.html) — setting compaction throttle and meaning of `0`.
- [Apache Cassandra — nodetool compactionstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/compactionstats.html) — backlogs and active tasks.
- [Apache Cassandra — nodetool tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html) — per-table metrics for before/after comparison.
- [Apache Cassandra — nodetool tpstats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tpstats.html) — flush, compaction, and request stage queues.
- [DataStax Java Driver 4.17 — Metrics](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/metrics/) — session/node metrics and enabling them.
- [DataStax Java Driver 4.17 — Configuration](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/configuration/) — session config, timeouts, pooling, and version-dependent runtime mutability.
- [DataStax Java Driver 4.17 — Speculative execution](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/speculative_execution/) — trade-off between tail latency and extra physical attempts.
