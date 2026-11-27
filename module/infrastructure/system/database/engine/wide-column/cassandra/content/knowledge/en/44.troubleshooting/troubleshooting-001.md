# Isolating Timing, Scope, Recent Changes, and Evidence

> **Chapter:** Troubleshooting  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — understanding Apache Cassandra's distributed architecture and wide-column model, partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, distributed failures, and Java application connectivity.

A Java service reports "Cassandra is slow" after a deployment. The application team sees HTTP p99 increasing, the database team sees `nodetool status` reporting all nodes as `UN`, and the infrastructure team sees free disk space remaining. All three observations **may be accurate**, yet they do not tell us when the failure started, which queries are affected, whether it impacts one DC or the entire cluster, whether it is related to the deployment, or which component is introducing latency.

**Effective troubleshooting begins with four evidence-backed questions:**

1. **Timing:** when did the symptoms appear; when was it last known to be normal; how wide is the uncertainty window?
2. **Scope:** which users/APIs, service versions, AZs/DCs, keyspaces/tables, query shapes, partitions, coordinators, or replica sets are affected?
3. **Recent changes:** were there any prior deployments, schema migrations, CL/TTL changes, traffic increases, node restarts, repairs, compactions, certificate rotations, or network changes?
4. **Evidence:** which metrics, logs, traces, `nodetool` outputs, CQL data, or driver errors confirm or refute the hypothesis; what are their sources, timestamps, and reliability?

This lesson builds a **workflow for isolating scope and preserving evidence**, not a list of commands to run blindly. The goal is to narrow the search space and avoid turning a minor incident into a wider outage through hasty actions.

> **Versions and safety:** examples target Cassandra 4.x–5.x, Java Driver 4.x (4.19 reference), Linux, and common observability stacks. Commands are predominantly **read-only**; exact syntax, metrics, and log paths vary by packaging/exporter. All cluster names, numbers, timestamps, and UUIDs in scenarios are **illustrative**, not measurements from a live system. For production, follow your organization's incident runbook, access controls, and change management process.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Write a **falsifiable incident statement**: symptoms, timing, scope, impact, and level of uncertainty.
2. Distinguish between when **customers see errors**, when **monitoring fires an alert**, when a **deployment happens**, when **a node fails**, and when **evidence collection starts**.
3. Build a UTC-normalized timeline with `last-known-good`, `first-known-bad`, metric resolution, and clock skew.
4. Build an impact matrix across service/API, query, partition key, keyspace/table, coordinator, replica set, DC/rack, and client version.
5. Use `nodetool status/tpstats/proxyhistograms/tablehistograms/tablestats/compactionstats/netstats` for their intended purpose without mistaking a single snapshot for the whole truth.
6. Read `system.log`, `debug.log`, GC logs, driver metrics, and query traces **within bounded time windows** instead of grepping everything and guessing the cause.
7. Compare recent changes against symptoms based on **temporal order, scope alignment, and technical mechanism**; avoid the "after deploy therefore caused by deploy" fallacy.
8. Maintain an evidence ledger recording source, timestamp, units, collection method, and system impact.
9. Propose hypotheses with falsifiable tests; separate **observations**, **inferences**, and **mitigation decisions**.
10. Produce an incident handoff thorough enough for the next on-call engineer or post-incident review to continue without repeating completed steps.

## 2. Four Investigation Axes You Must Not Miss

~~~mermaid
flowchart TD
    A["Signal: Cassandra slow / errors"] --> B["TIMING<br/>last good, first bad, window"]
    A --> C["SCOPE<br/>client → query → coordinator → replica/DC"]
    A --> D["CHANGES<br/>deploy, config, schema, capacity, background"]
    A --> E["EVIDENCE<br/>metrics, logs, traces, nodetool"]
    B --> F["Falsifiable hypotheses"]
    C --> F
    D --> F
    E --> F
    F --> G["Low-impact checks"]
    G --> H{"Corroborated across independent sources?"}
    H -->|Yes| I["Controlled mitigation + verification"]
    H -->|Not yet| J["Collect more data, update uncertainty"]
    J --> B
    I --> K["Timeline and post-incident evidence"]
~~~

### 2.1. Four Answers Must Go Together

| Question | Incomplete Answer | Actionable Answer |
|---|---|---|
| When? | "Since this morning" | "p99 began breaching SLO in the 09:42–09:43 UTC bucket; last normal 09:40–09:41; alert fired 09:45" |
| Where? | "Cassandra is slow" | "Only `GET /devices/{id}/events` from deployment v28 in dc1; read p99 on 2/3 coordinators elevated, dc2 normal" |
| After what change? | "There was a deploy" | "v28 ramped to 20% traffic at 09:39; query started omitting event_day in prepared CQL or added filtering — **unverified**" |
| Evidence? | "Dashboard is red" | "HTTP p99, DriverTimeoutException count, sampled SELECT trace, server coordinator histograms; timestamps and artifact links" |

The numbers in the example are **not universal SLAs**. An incident statement should include timestamps, query fingerprint, CL, and error rate, even if initially marked "unknown".

### 2.2. Three Layers to Separate Immediately

1. **User-facing symptoms:** HTTP 5xx, timeouts, missing data, stale reads, high latency.
2. **Driver/coordinator signals:** connection/pool exhaustion, retries/speculation, request timeouts, unavailable, throttling, write/read timeouts.
3. **Replica/storage state:** node Down/Joining, GC, disk queue, tombstone scans, compaction backlog, schema/version mismatch.

Do not jump directly from `HTTP 504` to "a replica is dead". An HTTP timeout can originate from the gateway, queue, auth, service thread pool, Driver throttler, network, or Cassandra. Likewise, do not infer from all nodes being `UN` that all queries are healthy: a hot partition, heavy tombstones, or pool contention can still cause terrible p99.

## 3. 0–5–15–30 Minutes: Initial Isolation Sequence

### 3.1. Minutes 0–5: Preserve State and Assess Severity

Write down **a one-line status block** first:

~~~text
INC-2026-11-21-01 (example)
Detected: 2026-11-21T09:45:00Z
Symptom: GET /events p99 breaching SLO, 2.7% timeouts
Affected: service-events v28, dc1; dc2 unknown
Start: first-bad in [09:42,09:43] UTC (1-minute bucket)
Last-known-good: [09:40,09:41] UTC
Change candidates: deploy v28 at 09:39; compaction at 09:41
Evidence links: dashboard snapshot #1, driver logs #2, node metrics #3
Severity/owner: per internal runbook
Confidence: LOW; cause unknown
~~~

**Immediate priorities:** detect data-loss risk, write outages, security issues, full disks, widespread Down nodes, or severe SLO breaches. Mitigation may need to run in parallel with investigation, but still capture **a minimal pre-change snapshot** if safe; do not delay emergency action just to produce a polished report.

### 3.2. Minutes 5–15: Narrow the Scope

- Compare a **healthy cohort** and an **affected cohort**: same query with different client versions, same service in different DCs, or same DC across different tables.
- Inspect **last-known-good → first-bad** on a dashboard using a consistent timezone.
- Collect `nodetool status` from **more than one node** when suspecting gossip/network partition.
- Distinguish driver/server timeout types; do not conflate `DriverTimeoutException` with `ReadTimeoutException`.
- Check whether recent changes match the **time window and scope**.
- Write "not yet checked" rather than leaving blank fields that mislead others into assuming something was checked and normal.

### 3.3. Minutes 15–30: Test Hypotheses and Apply Controlled Mitigation

Formulate at most a few weighted hypotheses, each containing:

~~~text
Hypothesis H1: v28 increases page size / query fan-out
Predicts: only v28 affected; rows/page and bytes/request increase;
          Cassandra coordinator read latency or pool pressure increases
Falsifier: v27/v28 have identical payloads, identical latency/errors, unchanged query shape
Low-risk check: compare query fingerprints, per-deployment metrics, prepared CQL
Mitigation candidate: controlled rollback/traffic shift once evidence suffices
Owner / timestamp / decision record: ...
~~~

Do not apply multiple "fixes" simultaneously—such as restarting nodes, changing CL, raising timeouts, triggering major compaction, and rolling back the service—as it becomes very difficult to tell which action caused the change and risks destabilizing the cluster.

### 3.4. Responsibility Matrix

| Role | Do | Avoid |
|---|---|---|
| Incident commander | Scope/severity, decisions, timeline sync | Guessing root cause without evidence |
| Application owner | HTTP/driver traces, deploy diffs, request fingerprints | Blaming Cassandra based solely on HTTP 504 |
| Cassandra operator | Node/DC, gossip, JMX, storage, logs, and repair state | Running state-mutating actions before capturing snapshots |
| SRE/Infrastructure | Network, disk, CPU, DNS/TLS, host/container events | Checking only average CPU and declaring hosts healthy |
| Scribe/evidence owner | UTC timestamps, sources, links, action impact | Writing "fixed" with no before/after data |

In a lab environment, one person may wear all hats; in a production incident, responsibilities and change permissions must follow operational runbooks.

## 4. Isolating **Timing** at the Right Resolution

### 4.1. Four Milestones Frequently Conflated

| Milestone | Explanation | How to Collect |
|---|---|---|
| `T_last_good` | Last bucket/point with evidence of normal behavior | SLO/error/latency time series |
| `T_first_bad` | First bucket/point with evidence of threshold breach | Raw metrics or windowed histograms |
| `T_alert` | When the alerting system fired | Alert evaluation time + pending/for duration |
| `T_detected` | When a human/system acknowledged the incident | Pager/incident channel |
| `T_change` | When a candidate change started or completed | Deployment/migration/host event log |
| `T_collection` | When an investigator captured a snapshot | Capture time + source clock |

**`T_alert` does not necessarily equal `T_first_bad`.** For example, if an alert evaluates every minute and requires a 5-minute pending duration, the alert fires several minutes after the failure began. If you only know "first bad" occurred within the 09:42–09:43 bucket, do not fabricate a precise timestamp like 09:42:13.

### 4.2. Always Use UTC in the Incident Log

On Linux hosts where reading time is permitted:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
date +"%Y-%m-%dT%H:%M:%S%z"
timedatectl status
~~~

Many application logs use local timezones, some dashboards use the browser timezone, and Cassandra's `system.log` uses its own logback configuration format. Convert everything to **UTC with explicit offsets recorded**, while preserving the original source timestamps in artifacts. Never assume two hosts have perfectly synchronized clocks: check NTP/chrony and clock offsets if event ordering looks anomalous.

### 4.3. Wall Clock vs. Monotonic Duration

To measure **elapsed time** in a Java application, use `System.nanoTime()` (monotonic relative clock); to attach a UTC timestamp to logs, use `Instant.now()` or a timezone-aware telemetry timestamp.

~~~java
import java.time.Instant;
import java.util.concurrent.TimeUnit;

Instant startedUtc = Instant.now();
long begin = System.nanoTime();
try {
    // Call repository/driver instrumented in the real codebase.
} finally {
    long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - begin);
    System.out.printf("started_utc=%s elapsed_ms=%d%n",
        startedUtc, elapsedMs);
}
~~~

Do not call `Instant.now()` twice and subtract for very short latencies if the wall clock can be stepped. Conversely, a `nanoTime()` value **is not a UTC timestamp for correlating across hosts**.

### 4.4. Uncertainty Interval

If a metric is only sampled every 60 seconds:

~~~text
Last good bucket       09:40–09:41 UTC
First bad bucket       09:42–09:43 UTC
Unknown transition     between after last-good and first-bad
Deploy started         09:39 UTC
Node GC pause observed 09:42:10 UTC (clock offset needs check)
~~~

We cannot yet tell whether the deploy caused GC or GC happened to coincide. Gather finer-grained logs/traces and cross-check per instance to narrow the window. **A high-precision log timestamp is not automatically more trustworthy than a coarse metric** if the clock source is unsynchronized or the event occurred after the symptom.

### 4.5. Narrowing the Window by Looking Before and After

A sensible window:

~~~text
T_pre   = last-good minus 30–60 minutes (or one meaningful background cycle)
T_fault = first-bad to current time
T_post  = after mitigation / after recovery
~~~

Choose a width appropriate to system history. For compaction/repair or TTL aging, you may need **hours or days of prior history**; for TLS certificate rotation, you may need specific expiry timestamps. Do not capture only the 5 red minutes—losing the baseline makes every metric look "high" without knowing high relative to what.

## 5. Isolating **Scope** Across Cassandra Layers

### 5.1. Map from User to Replica

~~~mermaid
flowchart TD
    A["User/Request/Region"] --> B["Gateway / API instance"]
    B --> C["Repository / CqlSession"]
    C --> D["Driver pool, LB policy, retry, TLS, local DC"]
    D --> E["Coordinator node"]
    E --> F["Replica set by partition token + RF/DC"]
    F --> G["Memtable / SSTables / tombstones / IO"]
    H["Query shape + partition key + CL + page size"] --> D
    I["Topology/gossip/repair/compaction"] --> E
    I --> F
~~~

A query may be sent to a coordinator that does not own the partition key, after which the coordinator contacts replicas based on the token and replication strategy. **A slow coordinator is not necessarily the replica holding bad data**. Gather both client-side execution info/coordinator data and server-side replica observations (when available) before concluding "node X holds the failing key".

### 5.2. Mandatory Blast Radius Matrix

| Dimension | Cohorts to Compare | Diagnostic Signal |
|---|---|---|
| **Users** | Tenant/region/device type, traffic volume | One hot tenant or all users |
| **API/use case** | GET latest-N vs range export vs INSERT/LWT | One query pattern/filtering or all CQL |
| **Service** | App instance/pod, deployment version, JVM | Errors only on v28, different driver config |
| **Connection path** | Source AZ/VPC, LB, TLS/auth, driver pool | A group of instances losing connectivity |
| **CQL** | Prepared fingerprint, table/keyspace, CL, page size | One keyspace or one statement regression |
| **Data** | Partition/bucket age, hot keys, tombstone density | A few large keys/partitions |
| **Coordinator** | Node chosen by the driver | One slow node or all coordinators |
| **Replicas** | Token range, RF, DC/rack replica placement | Replica-set overlap / DC outage |
| **Infrastructure** | Disk/device, CPU/GC, network/switch/AZ | Specific zone/node impact |
| **Time** | Peak hour, repair, compaction, TTL burst | Coincides with background tasks or burst load |

Common narrowing order: **user/API → app version/DC → query fingerprint → partition → coordinator/replicas → storage/hardware**. Investigating at only one layer risks missing adjacent causes.

### 5.3. Distinguishing "One Node" vs. "One Replica Set"

In a keyspace using NetworkTopologyStrategy, the partition token determines the replicas; RF/CL determine how many replicas must respond. A read query failing on a single partition while all nodes are `UN` can involve:

- The partition contains too many tombstones, making that specific read scan slowly.
- The replica set for that token experiences slow IO/GC on one or more nodes.
- `LOCAL_QUORUM` fails to get enough responses within the timeout when one replica is slow.
- A hot key saturates the replicas serving that key.
- An unstable coordinator/pool route, even when replicas are healthy.

Do not blame everything on the `coordinator IP`, and do not lump all queries against a table into a single execution path.

### 5.4. Useful "Healthy Control" Comparisons

| Comparison | If Only Group A Fails | Priority Hypothesis |
|---|---|---|
| Service v27 vs v28, same DC/query | Only v28 | Deploy/config/driver behavior |
| Same service/query, dc1 vs dc2 | Only dc1 | DC-local topology/network/CL |
| Same table, point lookup vs range scan | Only range | Partition width, pagination, tombstones |
| Same query, hot key vs cold key | Only hot | Token/replica skew or hot partition |
| Same host, one keyspace vs all | One keyspace | Schema/index/compaction/query distribution |
| Same driver instance, pool node A vs node B | Only A | Connection/node/coordinator behavior |

Do not pick a healthy control with completely different traffic, payloads, or CL and treat the difference as causal proof. For cross-DC comparisons, align query consistency and routing topology before drawing conclusions.

## 6. Isolating **Recent Changes** Without Causal Fallacy

### 6.1. Multi-Layer Change Inventory

Do not just ask "was there a deploy?". Within the same timeframe, Cassandra can experience **direct changes, background changes, or workload changes**.

| Layer | Changes to Cross-Check | Mechanism That Can Produce Symptoms |
|---|---|---|
| Application | API release, query shape, mapping, cache, concurrency, pagination | N+1 queries, page fan-out, SELECT *, hot key |
| Java Driver | Driver version, local DC, timeouts, retry/speculation, pool, TLS | Coordinator selection, pool queues, error amplification |
| CQL schema | CREATE/ALTER, table/index/SAI, UDT, TTL, compaction config | Schema disagreement, index behavior, read/write amplification |
| Keyspace | RF, NetworkTopologyStrategy, CL policy, serial CL | Availability and read/write consistency |
| Cassandra server | Rolling restart/upgrade, JVM flags, heap, native protocol | GC, compatibility, connection reconnection |
| Maintenance | Repair, bootstrap, rebuild, cleanup, compaction, backup/snapshot | Streaming, disk IO, cache churn, network bandwidth |
| Data/workload | New hot tenant, TTL expiration burst, import/delete, daily peak | Tombstones, partition skew, increased writes/s |
| Network/infra | DNS, NAT, firewall, AZ routing, TLS cert rotation, disk resize | Connection handshake, packet loss, disk saturation |
| Observability | Exporter/sampling/metric relabel, dashboard timezone | Looks "red" due to measurement/display error, not necessarily app failure |

**Background changes** are still changes: no deploy occurred, yet data volume grew, a TTL cohort expired, or a node started a long compaction. Record explicitly "no app deploy observed", which is different from "no changes occurred".

### 6.2. A Change Timeline Has Duration, Not Just a Single Dot

~~~text
09:38  v28 rollout begins (0% -> 20%)
09:41  compaction backlog rises on node N2
09:42  first-bad API p99 on v28
09:47  v28 rollout reaches 50%
09:48  error rate increases further
09:52  rollback v28 to 0%
09:54  API p99 recovers (hypothetical)
~~~

If rolling back and p99 recovery coincide, **the association grows stronger**, yet you must still verify: did compaction just finish, did traffic just drop, or did dashboard aggregation delay the appearance of recovery? On distributed infrastructure, **correlation is not a substitute for technical mechanism**.

### 6.3. Scoring a Change with Three Checks

1. **Temporal fit:** the change occurred **before** the symptom with a plausible lag (gradual deployment, TTL age, repair, restart).
2. **Scope fit:** the changed subsystem matches the failing subsystem (v28 pods in dc1, one keyspace, one rack); are unchanged cohorts healthy?
3. **Mechanism fit:** a credible technical pathway exists (larger page size → more bytes/read → pool/GC; missing partition key → query rejected; new TLS truststore → SSL handshake failure).

A change that satisfies only temporal fit without scope/mechanism fit is a **candidate**, not a root cause.

### 6.4. Find Auditable Changes, Don't Rely on Memory

Collect from available authorized sources:

- Deployment events: release ID, image digest, config hash, rollout start/end, canary pods, rollbacks.
- DB migration logs: migration ID, executed CQL, schema agreement, and timestamps.
- Cassandra `system.log`: node join/leave, schema changes, startups, GC messages.
- Infrastructure audit: maintenance, network policies, storage latency incidents, host reboots.
- Workload: QPS, write bytes, input event bursts, export jobs, TTL expiration windows.
- Feature flags: enabled/disabled per tenant/DC, **actual effective timestamp**, not just commit timestamp.

Avoid recording secrets or credential values in the change inventory. For config diffs, retain **hashes, setting names, and redacted values**; if raw values are needed for root cause analysis, store them in an access-controlled system.

### 6.5. Test One Variable at a Time with Guardrails

If v28 differs from v27 in `pageSize`, prefer a canary comparison or controlled rollback **on the same request cohort**. If compaction is suspected, collect metrics first—**do not stop compaction recklessly**. If schema disagreement is suspected, verify schema and errors first—**do not run experimental ALTER TABLE statements in production**.

A well-formed test records:

~~~text
Hypothesis: v28 increases page fetches for latest-N.
Before: v27 p99 75ms, v28 p99 260ms (example, same query class).
Action: shift 10% of v28 traffic back to v27 per runbook.
Prediction: errors/latency for the shifted cohort drop; total load change is accounted for.
Observation: fill from actual metrics, not projections.
Decision: continue rollback / hold / investigate elsewhere.
~~~

Never treat "downgrading CL from LOCAL_QUORUM to ONE" as a harmless A/B test: it alters the **consistency contract** and can introduce stale reads. Changing TTL, `gc_grace`, or compaction also carries long-term consequences and requires formal change review.

## 7. **Evidence**: Reliability, Provenance, and Collection Impact

### 7.1. Hierarchy of Evidence

| Level | Examples | Limitations |
|---|---|---|
| A — Direct observation | Driver exception type + timestamp/request ID; node logs; CQL response with CL/trace ID | A single sample does not represent all traffic |
| B — Contextualized metric | 1m error rate, p99 per query, per-node JMX, disk IO | Requires understanding buckets, counter resets, units, scrape lag |
| C — Change event | Rollout event, schema migration log, node restart record | Temporally close to the fault but does not prove causality |
| D — Inference | "Likely compaction" from pending queue | Only a hypothesis; needs further testing |
| E — Hearsay/recall | "Same thing last time, must be disk" | Insufficient basis for risky actions |

Do not treat Level A as "root cause proven": a `ReadTimeoutException` confirms the read did not satisfy its CL within its deadline, **not which specific disk caused the slowdown**. Strong evidence usually consists of **two or more independent sources** aligned across time window, scope, and mechanism.

### 7.2. Auditable Evidence Ledger

~~~markdown
| Evidence ID | Captured UTC | Source clock / offset | Scope |
|---|---|---|---|
| EV-001 | 09:48:22Z | dashboard scrape 30s | HTTP p99 per v27/v28 |
| EV-002 | 09:49:05Z | node N2 clock +40ms | N2 system.log 09:38–09:49 |
| EV-003 | 09:49:31Z | nodetool run UTC | N1,N2 status views |
| EV-004 | 09:50:12Z | driver app UTC | Errors by class, coordinator |

Each artifact includes: access-controlled URI, collector, query/command,
unit/bucket, checksum if needed, reliability, capture impact.
~~~

Keep both **raw log/metric exports** and a summary. A dashboard screenshot alone is insufficient if it lacks timezone, query filters, axis units, and the time window. If links expire after metric retention ends, preserve snapshots/artifacts per policy.

### 7.3. Before and After an Action

Immediately before mitigation:

~~~text
UTC timestamp
Node/cluster/version/config state
Error rate, p95/p99, in-flight, CPU/disk, compaction backlog
Identified queries and sample IDs
Action owner, rationale, rollback plan, predicted metric changes
~~~

After mitigation, collect **the same set of metrics/filters** over a long enough window, and note concurrent changes. Do not just say "nodes are green again"; verify user impact, request success, data consistency, and recovery.

### 7.4. Collection Order to Avoid Destroying Evidence

**First:** collect logs and events around the incident, metrics/counters, driver errors, status/schema snapshots, topology, and disk state. **Only then** consider state-altering actions such as restarts, flushes, rolling upgrades, repairs, compaction changes, or schema migrations.

Even read operations carry overhead:

- `nodetool` uses JMX, which can be slow or time out on an overloaded node.
- CQL tracing writes to system trace tables and adds overhead.
- Debug/TRACE logging increases disk IO and may expose sensitive payloads.
- Scanning SSTables, taking heap dumps, or packet captures consumes resources and contains sensitive data.

Bound your sampling rate, iteration count, and duration. If a node is nearly out of disk space, **do not** turn on heavy logging or tracing that worsens the situation.

### 7.5. Separating Evidence Gathering from Actions

| Operation | Category | Caveat |
|---|---|---|
| `nodetool status`, `tpstats`, `compactionstats` | Mostly observational | JMX has overhead; output is per-node/point-in-time |
| `SELECT ... FROM system.local`, `DESCRIBE TABLE` | Metadata read | Verify target keyspace/DC |
| Reading `system.log`, `debug.log`, metrics | Observational | Redact secrets; verify timezone/log rotation |
| Enabling tracing on one query | Observational **with system writes** | Small sample only; never enable on every request |
| `setlogginglevel TRACE` | Mutates logging behavior | Can increase IO; always have a revert plan |
| `flush`, `repair`, `cleanup`, major compaction | **Intervention** | IO/disk/topology effects; requires runbook |
| `truncate`, `drop`, deleting SSTables/hints | **Destructive** | Never use as a routine "diagnostic" step |
| Node restart | **Intervention** | Destroys volatile evidence; alters cluster state |

**Never assume an apparently "read-only" operation is completely free**; weigh it against current load. Classifying impact properly helps coordinators prioritize by incident severity.

## 8. Collecting **Cassandra** Evidence Across Nodes and Layers

### 8.1. Topology State Snapshot

On an authorized administrative node:

~~~bash
nodetool status
nodetool describecluster
nodetool info
nodetool gossipinfo
~~~

`nodetool status` shows Up/Down, Normal/Joining/Leaving/Moving, DC/rack, host ID, and estimated load; **the gossip view is from the perspective of the node you query**. When suspecting a network partition, compare outputs from **at least two nodes in different zones** rather than concluding from a single node. `UN` does not prove queries are succeeding or replicas are repaired.

`describecluster` helps inspect cluster name and schema/partitioner versions; `info` reports node state and load; `gossipinfo` can be verbose and contain internal addresses. Collect within a labeled host/timestamp window and do not post to public logs.

### 8.2. Thread Pools and Backlogs

~~~bash
nodetool tpstats
nodetool netstats
nodetool compactionstats
~~~

`tpstats` can display Active/Pending/Completed/Blocked counts and dropped messages per thread pool; pool names vary by Cassandra version. `netstats` is useful for active streaming/repair/bootstrap and network streaming state; **it is not proof that all native protocol connections are healthy**. `compactionstats` shows pending/running compactions and progress/estimates.

**Do not read Pending counts from a single snapshot as the whole story**: inspect time series and derivatives of Completed/Blocked/Dropped. A queue showing pending=0 at capture time could have been saturated 5 minutes earlier before draining when load fell or clients timed out.

### 8.3. Distinguishing Coordinator Latency from Local Storage Latency

~~~bash
nodetool proxyhistograms
nodetool tablehistograms <keyspace> <table>
nodetool tablestats <keyspace>.<table>
~~~

- `proxyhistograms`: latency **at the coordinator** by request type (read/write/range/CAS depending on version).
- `tablehistograms`: table-local metrics such as read/write latency, SSTables per read, partition size/cell count, depending on Cassandra version.
- `tablestats`: table statistics for reads/writes, disk usage, estimated partitions, tombstones, and SSTables.

If **client** p99 is high while coordinator p99 is low, inspect network, driver queues, application thread pools, and percentile aggregation first. If coordinator p99 is high while local table read latency on the coordinator node is not, the bottleneck may lie on **other replicas or inter-node networking**, not necessarily the coordinator's disk.

**Watch the units:** many Cassandra latency metrics are in microseconds, exporters may convert them to seconds, and drivers/HTTP typically report milliseconds. Compare time series only after normalizing units, histogram buckets/windows, and latency definitions.

### 8.4. Storage and Tombstone Evidence

| Signal | Usage | Interpretation Trap |
|---|---|---|
| `EstimatedPartitionSizeHistogram` | Partition size tail | An estimate, not an exact full scan |
| `SSTablesPerReadHistogram` | Read amplification | Does not mean every SSTable holds live rows |
| `TombstoneScannedHistogram` | Tombstone overhead per query/table | Even a small partition can scan many tombstones |
| `LiveSSTableCount` | Increase/decrease in SSTables | Changes with compaction/flush cycles |
| `PendingCompactions` | Compaction backlog | Needs trend and disk/CPU correlation |
| `LiveDiskSpaceUsed`/`TotalDiskSpaceUsed` | Live vs. obsolete SSTables | Excludes snapshots, commitlog, hints |
| GC pause/heap usage | Stop-the-world/GC pressure | Healthy heap does not guarantee healthy disk/network |

Compare per-table and per-node over the same timeframe. Never treat a high compaction backlog **alone** as the root cause; verify whether it began before p99 spiked, whether IO saturation exists, and whether query impact aligns.

### 8.5. Correlating Logs with the Timeline

Cassandra distributions typically write to:

~~~text
<CASSANDRA_HOME>/logs/system.log
<CASSANDRA_HOME>/logs/debug.log
<CASSANDRA_HOME>/logs/gc.log
~~~

Linux packages may place logs under `/var/log/cassandra` or send them to journald/container logs depending on `logback.xml`, JVM GC flags, and infrastructure. **Confirm the actual path before running commands**. `system.log` records startups, exceptions, GCInspector warnings, and schema/topology changes; `debug.log` can contain detailed flush/compaction logs and far higher volume. Docs: <https://cassandra.apache.org/doc/latest/cassandra/troubleshooting/reading_logs.html>.

~~~bash
# Example: permissions/paths and log timezone already verified.
grep -E 'WARN|ERROR|GCInspector|Exception' /var/log/cassandra/system.log
grep -E 'Compaction|Flushing|Gossip|Schema' /var/log/cassandra/debug.log
# For rotated/compressed logs, check the corresponding archived files first.
~~~

**Do not only `grep ERROR`.** For example, GC pauses, status transitions, or compaction queues may be logged at INFO/WARN. Conversely, grepping a year of logs and finding an old ERROR **does not** prove it relates to the incident; match timestamps and node IDs.

### 8.6. Illustrative Multi-Node Snapshot

~~~text
N1 at 09:50Z: status N1=UN N2=UN N3=UN
N2 at 09:50Z: status N1=UN N2=DN N3=UN
N3 at 09:50Z: status N1=UN N2=UN N3=UN
~~~

This is an **illustrative conflicting gossip view**, enough to prioritize a network/gossip/topology hypothesis, but **not enough** to conclude N2 is actually Down for all clients. Cross-check network metrics, logs, driver topology events, host process uptime, and membership update timestamps.

### 8.7. Do Not Use "Cleanup" Commands as Evidence-Gathering Steps

Avoid executing without a runbook and impact assessment:

~~~text
nodetool flush
nodetool cleanup
nodetool repair
nodetool compact
nodetool drain
nodetool stopdaemon
nodetool truncatehints
~~~

These commands **mutate state or generate heavy load**, and some cause data or availability loss if misused. This lesson **does not ask you to run** them; they are listed to distinguish them from initial observational steps.

## 9. Collecting **Java Driver and Application** Evidence

### 9.1. Four Types of "Timeout" Can Mean Different Things

| Signal/Exception | Who Reports It? | Next Question |
|---|---|---|
| HTTP/gateway 504 | Gateway or application | Did the request reach the app? Was CQL sent? Where was the time budget spent? |
| `DriverTimeoutException` | Driver deadline exceeded waiting for response | Which stage stalled: throttler, pool, network, or coordinator? |
| `ReadTimeoutException` | Coordinator returned READ_TIMEOUT | Required/received replicas, data present, slow replica? |
| `WriteTimeoutException` | Coordinator returned WRITE_TIMEOUT | CL, required/received, write type, **unknown outcome**? |
| `UnavailableException` | Coordinator knows too few live replicas for CL | RF, DC, membership, Down nodes? |
| `RequestThrottlingException` | Driver rejected enqueue/dispatch per throttling policy | Client overload, queue max, offered QPS? |
| `AllNodesFailedException` | Every tried coordinator failed | Are per-node errors pool, TLS, connectivity, or server errors? |
| `InvalidQueryException` / `UnauthorizedException` | Server validation/authz | Query/schema/role migration? Do **not** auto-retry as transient |

Driver 4.19 documentation distinguishes `ReadTimeoutException` (coordinator replied with an error) from `DriverTimeoutException` (driver received no response before its deadline). `WriteTimeoutException` does **not** mean all replicas failed to apply the mutation; the write may have committed while the acknowledgement was lost. Therefore, log the **actual exception class**, not just a generic "timeout" string.

### 9.2. Application Log Fields Worth Capturing

A redacted request log/trace should contain:

~~~text
request_id, trace_id             : correlation IDs without customer data
utc_timestamp, elapsed_ms       : timestamp and duration
service_version, instance, AZ/DC: cohort
cql_fingerprint                 : normalized CQL, NO bound values
keyspace, table, operation      : query scope
consistency, serial_consistency : execution contract
page_size, pages_consumed       : paging cost
driver_timeout_ms               : effective configured timeout
coordinator_endpoint (if known) : node-specific analysis
exception_class, error_details  : error type, not just "database failed"
retry_count, speculative_count  : executions amplifying load
~~~

On success, `ExecutionInfo` provides the coordinator, tracing ID (if enabled), server warnings, and request metadata per the API. On exception, **complete `ExecutionInfo` is not always available**, since a query may fail before selecting a coordinator; capture context from the statement, request ID, and exception rather than faking a coordinator field.

### 9.3. Java Driver 4.x Example: Controlled Query Metadata Logging

Assuming the keyspace/table from the section 14 lab exists and `CqlSession` is shared; the SELECT is prepared once before handling requests:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import java.time.Duration;
import java.time.LocalDate;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

static void sampleRead(
        CqlSession session, PreparedStatement prepared,
        UUID deviceId, LocalDate eventDay, boolean sampledTrace) {

    BoundStatement statement = prepared.bind(deviceId, eventDay)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofMillis(800))
        .setPageSize(100)
        .setIdempotent(true)
        .setTracing(sampledTrace);

    Instant startedUtc = Instant.now();
    long startedNano = System.nanoTime();
    try {
        ResultSet rs = session.execute(statement);
        int received = 0;
        for (var row : rs) {
            received++;
            // In production: map row/DTO, do not log full payloads.
        }
        ExecutionInfo info = rs.getExecutionInfo();
        System.out.printf(
            "utc=%s elapsed_ms=%d rows=%d coordinator=%s trace_id=%s%n",
            startedUtc,
            TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNano),
            received,
            info.getCoordinator(),
            info.getTracingId());
    } catch (RuntimeException error) {
        System.err.printf(
            "utc=%s elapsed_ms=%d error_type=%s%n",
            startedUtc,
            TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startedNano),
            error.getClass().getName());
        throw error;
    }
}
~~~

Prepared CQL:

~~~java
PreparedStatement prepared = session.prepare(
    "SELECT event_time, event_id, payload " +
    "FROM triage_lab.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? LIMIT 100");
~~~

**Example limitations:**

- `getExecutionInfo()` on a synchronous result typically reflects the execution of the observed page; when consuming multiple pages, capture per-page execution info via the appropriate API instead of assuming one coordinator served every page. `getAllExecutionInfo()` can be used with `ResultSet` where appropriate for your Driver version.
- `setTracing(true)` creates additional server-side work; use only small samples in labs or approved production checks. `getTracingId()` can be null when tracing is disabled.
- `System.out/err` is for illustration only; production should use structured logging, sampling, redaction, and avoid hot-path logging that adds latency.
- This is a SELECT with a known PK. Do not trace `SELECT *` missing a partition key or export millions of rows during an incident just to capture a trace.
- `LOCAL_QUORUM` in a lab requires matching RF/DC; on a single-node RF1 lab, the operation still achieves quorum=1 but **does not validate high availability**.

### 9.4. Driver Metrics Must Be Enabled to Be Observable

Java Driver 4.x typically **disables metrics by default**. Reference configuration for Driver 4.19:

~~~hocon
datastax-java-driver.advanced.metrics {
  session.enabled = [cql-requests]
  node.enabled = [pool.open-connections, pool.in-flight]
}
~~~

The application also needs an integrated metrics registry/exporter and sensible label cardinality. Metric names and units depend on the registry and mapping; check the driver config API in use. Do not assume `pool.in-flight` exists in Prometheus if the config does not enable it or the exporter is not wired up.

**During investigation:**

- In-flight climbing before timeouts? Requests/queues may be backing up.
- Errors isolated to one node pool? Check connections, idle heartbeats, TLS certificates, and node state.
- Retries/speculative executions increasing? Actual CQL attempts may exceed incoming HTTP requests.
- `RequestThrottlingException` appearing? The driver may be rejecting requests **before sending** them to Cassandra.
- Server p99 normal while HTTP p99 is bad? Check driver/client queues, GC, thread pools, serialization, and network.

**Do not enable all metrics/tracing while the cluster is already saturated** without evaluating overhead: several metric trackers sit on the Driver's hot path.

### 9.5. Requests May Hit Multiple Coordinators

One business request can generate multiple executions due to retries or speculative execution. Hence:

~~~text
HTTP requests/s  = 3,000
Driver CQL attempts/s = 4,800 (hypothetical)
Cassandra coordinator requests/s = depends on routing/metrics
~~~

The gap can come from retries/speculation or one HTTP request issuing multiple CQL calls; **do not automatically conclude** the difference is only retries. Measure attempts per request and N+1 CQL calls in application traces.

Avoid stacking retries simultaneously at the gateway, service, Spring Retry, and Driver layers when diagnosing overload. Each layer can multiply total attempts and worsen tail latency.

### 9.6. Query Traces Are Valuable When Sampled Carefully

With `Statement.setTracing(true)`, Driver 4.x exposes a tracing ID via `ExecutionInfo.getTracingId()`; `getQueryTrace()` retrieves coordinator/replica events. Traces are written into `system_traces` and incur overhead and availability lag.

Never trace 100% of QPS or log bind values/PII. Instead:

1. Pick **one fingerprint, one authorized sample key, one CL, and one time window**.
2. Measure the same query without tracing as a control.
3. Enable tracing for **a small percentage** within an approved budget.
4. Record the trace ID in the incident ledger.
5. Stop sampling once enough data is collected; never leave tracing flags enabled long-term.

If a query fails before the coordinator processes the request, a server-side trace may **not exist**. Absence of a trace **does not** prove Cassandra is healthy or that the bug is client-side.

## 10. CQL and Data Model Evidence: Isolating Queries and Partitions

### 10.1. Do Not Investigate Keyless Queries by Scanning the Whole Table

On a **lab cluster** or authorized environment, read metadata safely:

~~~sql
SELECT cluster_name, data_center, release_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'triage_lab';
~~~

This confirms the node responds and shows replication metadata, **but does not automatically prove** all nodes share the same schema version or that the cluster is healthy. For the target table:

~~~text
cqlsh: DESCRIBE KEYSPACE triage_lab;
cqlsh: DESCRIBE TABLE triage_lab.events_by_device_day;
~~~

This is `cqlsh` syntax, not a CQL statement accepted verbatim by every Java API. Before running CQL read samples, verify PK and clustering columns so you do not accidentally trigger a full scan or `ALLOW FILTERING`.

### 10.2. Same Table, Different Query Shapes

Example schema **intended solely for a dedicated lab cluster**. If the lab has three nodes in `dc1`, use RF3; for a single-node lab, use the actual RF1/DC and do not use it to evaluate fault tolerance:

~~~sql
CREATE KEYSPACE IF NOT EXISTS triage_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS triage_lab.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Verify the actual DC name `dc1` via `nodetool status`/metadata rather than assuming Cassandra containers always use that name. `IF NOT EXISTS` does not alter an existing schema; inspect `DESCRIBE TABLE` before concluding query and schema match.

Valid query:

~~~sql
SELECT event_time, event_id, payload
FROM triage_lab.events_by_device_day
WHERE device_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

If v27 queried with `device_id + event_day` and v28 queries only with `device_id` or adds `ALLOW FILTERING`, it changes scope/cost and may be rejected by CQL. Failures affecting only very old `event_day` partitions can stem from TTL/tombstones or compaction rather than a code deploy.

### 10.3. Partition Size and TTL History Can Turn One Query into an Outlier

Check these dimensions:

~~~text
partition key / clustering range
rows/partition and bytes/partition (p50/p95/p99/max)
TTL and tombstone age
SSTables per read
page size and actual pages consumed
whether filtering/index/SAI is used
RF/CL, DC-local replicas
~~~

A latest-N query with `LIMIT 20` can still scan huge numbers of tombstones before finding enough live rows. A hot partition receiving high read concurrency can slow down even with a small row count. **Distinguish "big partition", "hot partition", and "tombstone-heavy partition"** — same table name, but different mechanisms and verification steps.

### 10.4. When a Write Fails, Do Not Use SELECT to Claim Rollback

After a `WriteTimeoutException`, reading the row back can aid reconciliation but **does not** prove an operation was not applied, especially with concurrent writers, TTL, low CL, or competing write timestamps.

Business workflows need:

- An operation ID or idempotency key to identify a logical mutation.
- Key/CL and readable scope permitted for verification.
- Distinct `SUCCESS / FAILED_VALIDATION / UNKNOWN_TIMEOUT` states.
- Re-checking with appropriate consistency/serial semantics for LWT.
- Avoiding replaying list appends, counter increments, or TTL resets without confirmed idempotency.

**Observable fact**: "in a SELECT at CL X at time T, the column held value Y". **Do not** extrapolate to "all replicas have converged" without additional evidence.

## 11. Reading Metrics and Logs Without Introducing Bias

### 11.1. Counters, Gauges, Histograms, and Timers Differ

| Type | Examples | Proper Reading |
|---|---|---|
| Counter | ClientRequest.Read.Timeouts, bytes flushed | Rate of increase over a window; account for restarts resetting counters |
| Gauge | PendingCompactions, pool.in-flight, disk free | Snapshot/time series; do not take blind derivatives |
| Histogram | SSTablesPerReadHistogram, partition-size histogram | Distribution tail; understand buckets/units and sample counts |
| Timer/Latency | ReadLatency, CoordinatorReadLatency | p95/p99/rate by library/interval; do not merge incompatibly |
| Event log | NodeDown, GC pause, deploy | Point-in-time events; unlogged events may be missing |

If a counter drops to 0 after a restart, **do not** compute it as "negative errors"; use `rate/increase` that handles resets per your exporter and scrape data. If a metric stays flat, confirm it is still being scraped and labels/targets are valid before assuming "the system is stable".

### 11.2. Never Average Percentiles

~~~text
Node N1 p99 = 10ms, 10,000 requests
Node N2 p99 = 500ms, 100 requests

(10 + 500) / 2 = 255ms is NOT the cluster-wide p99.
~~~

A combined percentile must be estimated from an underlying distribution or compatible histogram samples (e.g., merged buckets with a shared definition), never by taking the arithmetic mean of individual p99s. Even summing driver + coordinator + network p99s to get end-to-end p99 is **mathematically invalid**.

### 11.3. Illustrative PromQL Patterns

Exporter metric names **vary**; this snippet uses **hypothetical** names and will not run verbatim unless your mapping actually exposes them:

~~~promql
# HTTP errors per second by deployment over 5 minutes.
sum by (deployment) (
  rate(http_requests_errors_total{service="events"}[5m])
)

# Error ratio over request rate, when sharing identical labels and data:
sum(rate(http_requests_errors_total{service="events"}[5m]))
/
sum(rate(http_requests_total{service="events"}[5m]))
~~~

**Do not** rely on `rate(...[5m])` to locate a 5-second burst without checking raw samples; smoothing can mask the onset. For Cassandra JMX metrics, exporters depend on deployment configuration—read the real mapping instead of pasting imagined PromQL names into production dashboards.

### 11.4. Lag Between Incident and Metrics

Monitoring pipelines can:

- Scrape every 15–60 seconds.
- Buffer remote-write/aggregation for tens of seconds.
- Drop samples when a node is Down or an exporter is overloaded.
- Evaluate alerts over moving windows with a pending period.
- Downsample historical data, erasing short spikes.

Record both **event timestamp** and **ingestion/capture timestamp**. A gap in a metric time series can indicate missing telemetry, **not** necessarily zero errors.

### 11.5. Failures in the Observability Tooling Itself

A dashboard changing a label, an exporter renaming a metric, or a new app disabling driver metrics can make a series drop to zero. Cross-check user-facing SLOs against **sample counts and UP targets**. If a dashboard claims "p99 jumped 10x" while raw app and log latencies look normal, check seconds/milliseconds/microseconds units and the query expression.

Never use "monitoring looks green" as an excuse to dismiss reproducible customer errors.

## 12. From Symptoms to Falsifiable Hypotheses

### 12.1. Initial Decision Tree

~~~mermaid
flowchart TD
    A["HTTP latency/errors rising"] --> B{"Did the driver send CQL?"}
    B -->|No / unclear| C["Gateway, queue, thread pool, auth,<br/>driver throttler/connectivity"]
    B -->|Yes| D{"What did Cassandra return?"}
    D -->|Unavailable| E["RF/CL, gossip, replica liveness,<br/>DC/rack topology"]
    D -->|Read/WriteTimeout| F["Coordinator/replica latency,<br/>IO, GC, tombstones, network"]
    D -->|DriverTimeout| G["Driver pool/queue + network<br/>or unresponsive coordinator"]
    D -->|Validation/Auth| H["Query/schema/role/config diff"]
    D -->|Success but HTTP slow| I["Paging, mapping, serialization,<br/>post-processing, client network"]
    C --> J["Narrow cohort and time window"]
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
    J --> K["Correlate changes + evidence,<br/>test falsifiable predictions"]
~~~

This is a **guide for selecting checks**, not an algorithm that guarantees a single root cause. One request can experience driver pool pressure and a slow replica simultaneously; branches are not mutually exclusive.

### 12.2. Template for a Good Hypothesis

~~~text
ID: H-02
Claim: Tombstones in tenant A's partition cause high latest-N read p99.
Window: first-bad after TTL cohort expiration, 09:40–09:45 UTC.
Scope: only tenant A's latest-N query; tenant B point reads unaffected.
Predictions:
  - table TombstoneScannedHistogram rises on nodes owning that token
  - sampled query trace shows scanning many rows/tombstones
  - p99 is high on that partition, much lower on healthy partitions
Falsifiers:
  - same failure across all partitions and all tables on the same nodes, with no scan skew
  - query does not read the tombstone-heavy partition/data
Evidence needed: EV-012 tablehistograms, EV-013 trace, EV-014 query fingerprint.
Risks of verification: tracing overhead, PII in partition key.
Next action: inspect metrics/trace safely; do not run compact/repair yet.
~~~

A hypothesis grows stronger when a test distinguishes it from competing hypotheses. "Maybe it's Cassandra" is **not** a sharp enough hypothesis.

### 12.3. Guide from Signal to First Evidence

| Primary Signal | Collect Immediately | Do Not Rush Into |
|---|---|---|
| One app deployment failing | Version, config hash, query fingerprint, driver metrics | Restarting the entire cluster |
| One DC failing, other DC healthy | Driver local DC, CL, coordinator, `nodetool status` on multiple nodes | Lowering CL or RF |
| All queries slow, high CPU/disk | GC, disk IO, queues, memtable/compaction, offered QPS | Raising timeouts indefinitely |
| Only one table/range slow | Partition histogram, tombstone metrics, paging, data age | Adding ALLOW FILTERING |
| ReadTimeout rising, Unavailable low | Replica response/GC/IO, request CL, coordinator | Concluding enough replicas means healthy |
| Unavailable rising | RF/CL, node liveness, DC/rack, network | Blind retries across all nodes |
| DriverTimeout rising, server latencies low | Driver queue/connection pool/client GC/network | Tuning compaction alone |
| TLS handshake failing from one app version | Truststore/CA/SAN, certificate chain, DNS, cert timestamps | Disabling TLS/hostname verification |
| InvalidQuery/Unauthorized rising after deploy | CQL schema/role changes, prepared statements, grants | Retrying until errors clear |
| Write timeout yet data exists | Outcome ambiguity, write type, idempotency ledger | Arbitrarily replaying counter/list appends |

**Timing, scope, and changes** determine which branch you take; the exception class is only one piece of data.

### 12.4. Do Not Substitute "No Evidence Yet" for "No Problem"

~~~text
No GC log seen                != no GC pause occurred
No server ReadTimeout seen    != all reads succeeded
One node status UN            != all nodes share the same gossip view
No trace ID                   != coordinator never processed the request
No recent deploy              != no workload/TTL/network change
No errors after rollback      != data integrity verified
~~~

Mark sources as `NOT_COLLECTED`, `EMPTY_WITH_COVERAGE`, or `UNAVAILABLE`. Only when you know an exporter or log is active and covers the exact window can absence serve as supporting evidence.

## 13. Four End-to-End Investigation Scenarios

### 13.1. Scenario A — Only a New Application Version Times Out

**Assumptions:**

~~~text
09:39 UTC: events API v28 rolled out to 20% in dc1
09:42 UTC: first-bad: v28 read p99 climbs from 70 to 270ms
09:43 UTC: DriverTimeoutException spikes on v28
09:45 UTC: Cassandra nodes remain UN
09:47 UTC: v27 deployment in the same DC is healthy
~~~

**Isolation:**

1. Compare v27/v28 query fingerprints and bind patterns without logging user values.
2. Compare `pageSize`, CL, request timeout, retry/speculation, and connection pools.
3. Check whether v28 added extra CQL calls per request or subscribed to a `Flux` twice.
4. Compare Driver pool in-flight/pending metrics with coordinator p99. If server p99 is flat while client p99 rises, suspect client queueing/serialization.
5. Record actual deployment progress; canary/rollback only with proper authorization.

**Competing hypotheses:**

| H | Prediction | Falsifier |
|---|---|---|
| H1: v28 fetches more pages | Rows/pages/request rise only in v28 | Query and page consumption match v27 identically |
| H2: v28 driver pool sized too small | Pool in-flight/available-streams degrade only in v28 | Pool metrics healthy while coordinator p99 rises concurrently |
| H3: N2 compaction | Queries from all versions hitting N2 slow down | v27 hitting N2 remains healthy with identical payloads |

**Properly framed conclusion:** "Current observations support H1 with MEDIUM confidence; an A/B comparison on the same query shape is needed to raise confidence." Never write "100% Cassandra" or "100% deploy" before running a discriminating test.

### 13.2. Scenario B — DC-Scoped Failures with Inconsistent Status Views

**Assumptions:**

~~~text
11:00 UTC: dc1 service hits UnavailableException (LOCAL_QUORUM)
11:00 UTC: dc2 service still reads the keyspace under its own configured CL
11:02 UTC: nodetool status on N1 shows N2 UN
11:02 UTC: nodetool status on N3 shows N2 DN
11:04 UTC: network packet loss spikes on an inter-rack link
~~~

**Isolation:**

1. Confirm client local DC/routing, keyspace replication, and effective CL.
2. Collect `nodetool status/gossipinfo` from multiple nodes with source/timestamp.
3. Correlate server `Unavailable` with driver `AllNodesFailed` and coordinator endpoints.
4. Gather network packet loss/latency, GC, and host health in the same window.
5. Check network policy/host maintenance events — do not conclude from a single `UN` view.

**Risk of wrong action:** dropping `LOCAL_QUORUM` to `LOCAL_ONE` can expose stale reads; changing RF during a network partition is even riskier. Balancing availability vs. consistency belongs in runbooks and business invariants.

**Required exit evidence:** node views converge, network stabilizes, request success matches target CL, and integrity/repair state is checked—not just all nodes turning "green".

### 13.3. Scenario C — Only Old Data Slows Down After a TTL Wave

**Assumptions:**

~~~text
02:00 UTC: 7-day TTL cohort of an event batch expires
02:04 UTC: latest-N queries on older partitions see p99 rise
02:06 UTC: TombstoneScannedHistogram rises on the affected table
02:07 UTC: compaction backlog grows; point reads on new partitions remain normal
~~~

**Isolation:**

- Check TTL policies/data age; do not assume an old `event_time` means TTL expired.
- Compare old vs. new partitions using the same query/CL and comparable live row counts.
- Record SSTables/read, tombstone histograms, and disk/IO; avoid concluding from compaction backlog alone.
- Check whether `UPDATE`s modified TTL'd cells, creating mixed expiration timestamps.
- If using TWCS/UCS, check strategy/maintenance windows and repair history.

**Do not unilaterally run** major compaction or lower `gc_grace` to "wipe out tombstones" in production. These can be dangerous interventions that destroy evidence; they require strategy review, safety checks, and isolated testing.

### 13.4. Scenario D — SSL Failures After Certificate Rotation

**Assumptions:**

~~~text
13:10 UTC: new service truststore partially rolled out
13:12 UTC: only new pods experience TLS handshake errors
13:13 UTC: Cassandra cqlsh from an internal bastion still connects normally
13:14 UTC: older service pods still query the same DC successfully
~~~

**Isolation:**

1. Distinguish `SSLHandshakeException`/trust chain errors from CQL `UnauthorizedException`.
2. Compare fingerprints/expiry/SANs of server certificates, CA chains, and truststore versions per policy (never export private keys).
3. Verify client TLS endpoint verification, hostname vs. IP, DNS/SNI, and system time.
4. Compare source AZ/DC, port 9042, firewalls, or LBs; do not use successful `cqlsh` from **a different host** to claim all app pods share the same network/trust path.
5. Capture cert/truststore rollout timing and first handshake failure, accounting for clock skew.

**Do not use** "temporarily disable SSL verification" as a default mitigation; roll back the truststore/certificate properly or fix configuration safely per runbook.

### 13.5. What All Four Examples Teach Together

A single signal is **never enough**. `UN` does not rule out tombstones/GC/networking. A deploy near the fault time does not prove the deploy caused it. A timeout does not prove a write wasn't applied. **Timing + scope + changes + multi-layer evidence** form a testable causal chain.

## 14. Investigation Lab: Isolate Before Acting

### 14.1. Goals and Prerequisites

The lab includes a **cluster-free tabletop portion** and an **optional Cassandra lab** to practice safe evidence collection. **Never perform fault injection on production**. Even without a Cassandra cluster, learners can complete the full timeline/matrix and evidence ledger exercises.

Scenario:

~~~text
Keyspace: triage_lab
Table: events_by_device_day
3 nodes in dc1, RF=3, read CL=LOCAL_QUORUM
Service: events-api v27 and v28, Java Driver 4.x
Symptom: GET latest events p99 rising and timing out on v28
SLO: p99 <= 200ms; success >= 99.9% (hypothetical lab targets)
~~~

**Reminder:** wording, timestamps, and metrics in the lab are **simulated inputs**, not live observations. Never present them as Cassandra benchmark results.

### 14.2. Tabletop Dataset

| UTC window | Cohort | Requests | p99 successful latency | Error % | Evidence |
|---|---|---:|---:|---:|---|
| 09:35–09:40 | v27/dc1 | 15,000 | 78 ms | 0.02% | A1 app metrics |
| 09:40–09:42 | v27/dc1 | 6,000 | 81 ms | 0.02% | A2 app metrics |
| 09:40–09:42 | v28/dc1 | 1,200 | 86 ms | 0.08% | A3 canary metrics |
| 09:42–09:45 | v27/dc1 | 9,000 | 83 ms | 0.03% | A4 app metrics |
| 09:42–09:45 | v28/dc1 | 4,000 | 312 ms | 3.6% | A5 app metrics |
| 09:42–09:45 | v27/dc2 | 5,000 | 90 ms | 0.04% | A6 app metrics |
| 09:42–09:45 | v28/dc2 | 0 | N/A | N/A | Not rolled out to dc2 |

Change events:

~~~text
09:39:20Z  v28 rollout 0 -> 20% in dc1
09:41:15Z  N2 compaction pending tasks rise from 3 to 12
09:42:00Z  Start of v28 first-bad bucket
09:43:10Z  v28 driver throttler queue grows; v27 normal
09:45:00Z  Alert fires; 2-minute pending period
09:46:30Z  Scribe begins collecting evidence
~~~

Driver CQL observations:

~~~text
v27: /events -> 1 prepared SELECT with LIMIT 100, pageSize=100
v28: /events -> 1 prepared SELECT with LIMIT 1000, pageSize=100
v27: mean returned rows/request 83
v28: mean returned rows/request 580
v28: requests consume several pages; retry/attempt count increases
Coordinator proxy read p99: rose only slightly over baseline
N2: compaction backlog higher than baseline
~~~

### 14.3. Exercise A — Pinpoint Onset Without Fabricating Precision

Tasks:

1. Record `last-known-good` and `first-known-bad` using the actual buckets.
2. Record `T_alert` and explain why it does not equal `T_first_bad`.
3. State the uncertainty interval during the transition.
4. Choose a log collection window starting before 09:39 and extending past 09:46, explaining why.
5. Label your report "simulated data" upon submission.

**Answer guide:** last normal includes the v28 09:40–09:42 bucket (per hypothetical thresholds); first bad is 09:42–09:45; alert at 09:45 due to pending/evaluation period. You cannot assert the exact second the regression occurred from multi-minute bucketed data.

### 14.4. Exercise B — Impact Matrix

Fill in:

| Dimension | Affected | Healthy/control | Unknown |
|---|---|---|---|
| App version | v28/dc1 | v27/dc1 | other versions |
| Region/DC | dc1 with v28 | v27/dc2 | v28/dc2 not rolled out |
| Query shape | LIMIT 1000 and multi-page | LIMIT 100 | other queries |
| Table | events_by_device_day | no control table yet | other tables |
| Node | no node blamed yet | undetermined | replica/coordinator mapping |
| Maintenance | N2 compaction backlog up | N1/N3 metrics missing | causal role |

**Hint:** the "query returning more rows/pages" mechanism matches version, scope, and timing, so H1 takes priority. N2's compaction backlog overlaps in time but could be a secondary effect or independent; evidence is insufficient to declare "N2 is the root cause".

### 14.5. Exercise C — Rank Hypotheses

Score H1 (query regression), H2 (N2 compaction), and H3 (network) in the table:

| Hypothesis | Temporal fit | Scope fit | Mechanism fit | Missing evidence |
|---|---|---|---|---|
| H1: query LIMIT/page behavior | Yes | High | High | Per-request pages & bytes, rollback/canary |
| H2: N2 compaction | Yes | Unclear | Possible | Per-node IO/GC, query routing overlap |
| H3: dc1-wide packet loss | Not yet | Low since v27 is healthy | Possible | Network telemetry, per-node driver errors |

Write **one falsifier** for each H and the risk level of the test. Do not declare a "root cause" while evidence is still missing.

### 14.6. Exercise D — Safe Cassandra Snapshots in the Lab

If you have a Cassandra lab with the schema from section 10, run observational commands **on a test node**:

~~~bash
nodetool status
nodetool proxyhistograms
nodetool tpstats
nodetool compactionstats
nodetool tablehistograms triage_lab events_by_device_day
nodetool tablestats triage_lab.events_by_device_day
~~~

On a single-node lab, the commands still teach syntax and metrics; **do not interpret the output as proving RF3 outage behavior**. Before running, check `nodetool help <command>` for your version; some builds/roles restrict remote JMX or expose no metrics. Never leave admin credentials in shell history.

In `cqlsh` with read-only access:

~~~sql
SELECT cluster_name, data_center, release_version FROM system.local;
SELECT keyspace_name, replication
FROM system_schema.keyspaces WHERE keyspace_name = 'triage_lab';
~~~

If the table does not exist yet, create the schema **only in the lab** and seed a few events with a sample partition key, then run a SELECT specifying both `device_id` and `event_day`. Do not generate millions of rows or scan the whole keyspace just to practice triage.

### 14.7. Exercise E — Evidence Collection and Redaction

Create the table:

| ID | Source | Time UTC | Query/filter/command | Scope | Supported conclusion | Limitations |
|---|---|---|---|---|---|---|
| EV-01 | App metrics | _fill in_ | deployment=v28 | dc1 | v28 p99 elevated | 3m aggregated |
| EV-02 | Driver logs | _fill in_ | error_class | v28 | _fill in_ | Sampling |
| EV-03 | Node metrics | _fill in_ | compaction pending | N2 | _fill in_ | Correlation only |
| EV-04 | Deploy audit | _fill in_ | image digest | v28 | _fill in_ | Does not prove cause |

**Do not record** full bind parameters, raw tenant IDs, access tokens, or unauthorized packet payloads. For hot partition keys, substitute a keyed hash (HMAC) using a properly managed secret key; a plain hash of a guessable ID is **insufficient** for privacy.

### 14.8. Exercise F — Mitigation and Verification

Assuming permission to reduce v28 traffic / canary rollback in the test environment:

1. Save before-snapshots and the v28 request rate.
2. Change **one variable**: shift v28 traffic from 20% → 0% per runbook.
3. Compare per-cohort p99/errors, total traffic, and per-node metrics after rollback.
4. Only if actual metrics match predictions should you raise confidence in v28's contribution.
5. Keep monitoring TTL/compaction/N2: rollback may relieve symptoms while another risk persists.
6. Record data state and any in-flight/unknown writes if write errors occurred — an app rollback does not repair data automatically.

If you cannot roll back or lack authorization, write only the **plan + expected observation**; never claim an action was executed when it wasn't.

## 15. Incident Report, Handoff, and Recovery Verification

### 15.1. Short On-Call Incident Report Template

~~~markdown
# Incident INC-... — Cassandra read latency in service ...

## Status
- Status: INVESTIGATING / MITIGATED / MONITORING / RESOLVED
- Started window (UTC): [last-known-good, first-known-bad]
- Detected / alert time (UTC): ...
- Severity / impact: users, error %, p99, affected operations
- Owner / next update UTC: ...

## Proven Scope
- Affected: app versions, DCs, keyspaces, tables, CQL fingerprint
- Healthy controls: ...
- Unknown/not yet verified: ...

## Recent Changes
- Change ID, effective time, rollout %, app/config/CQL/network/maintenance
- Temporal fit / scope fit / mechanism fit: ...
- Concurrent unrelated changes: ...

## Evidence
- EV-001 ... source, timestamp, query/command, unit, scope, link
- EV-002 ...
- Clock skew/data gaps/sampling: ...

## Hypotheses
- H1, prediction, falsifier, evidence for/against, confidence
- H2, prediction, falsifier, evidence for/against, confidence

## Actions and Outcomes
- At UTC ... actor ... did ... with approval ...
- Expected ... / observed ... / rollback state ...

## Recovery Verification
- User SLO + error rates back in range for agreed window?
- Same CL / semantics / query results preserved?
- Cluster node/DC + repair/integrity conditions verified?
- Known unknowns and follow-up owners ...
~~~

**Do not mark root cause "CONFIRMED" just because p99 dropped.** Symptom relief after a rollback may be temporary mitigation; root cause requires an evidence chain and a verified mechanism, especially when multiple changes overlap in time.

### 15.2. Writing a Falsifiable Incident Statement

Compare:

> *Weak:* "Cassandra broke because of the deploy and is fine now."

> *Better:* "In dc1, 3.6% of requests from service-events v28 timed out during 09:42–09:45Z; v27 in the same DC saw 0.03%; v28 increased LIMIT from 100 to 1,000 and mean rows/request from 83 to 580. Rolling back v28 is under evaluation. There is not yet evidence that node N2 compaction is a direct cause."

In the better version, every claim carries **source/UTC/scope** and can be verified or falsified. If data comes from a hypothetical lab, mark it **SIMULATED**.

### 15.3. Exit Criteria Are More Than All Nodes Being UN

An incident can transition from **MITIGATED** to **RESOLVED** after meeting pre-defined criteria:

| Category | Reference Criteria | Why |
|---|---|---|
| User impact | Error rate/latency recovered over a sufficiently long window | Ensures real symptoms have cleared |
| Offered traffic | Traffic has returned to representative levels, not just 10% | Avoids looking "healthy" only because load dropped |
| Driver | Retry/throttling/pool errors back to normal | Prevents issues from hiding behind queues |
| Cassandra | Node/DC health, latency, disk/GC/compaction trends stable | Does not ignore background stressors |
| Data integrity | Unknown writes/LWT/TTL and repair/reconciliation addressed | API success does not prove data correctness |
| Operational | Mitigation config has owner/expiry and clear follow-ups | Prevents temporary workarounds from becoming permanent |

The observation window must exceed alert/scrape cycles, and if the incident involved TTL/compaction/repair, monitoring may need longer than a few minutes. **Do not define a single universal number for every cluster**; follow the specific SLO, workload, and runbook.

### 15.4. Shift Handoff Without Making the Next Engineer Start Over

~~~text
CURRENT STATE:
  Severity: SEV-... / owner ...
  Scope: v28/dc1 GET latest-N; other cohorts ...
  Last good & first bad: ... UTC, source ...
  Best hypotheses: H1 ..., H2 ..., confidence ...
  Collected evidence: EV-001..EV-012 (links)
  Actions already taken: command/change ID/UTC/outcome
  Explicitly NOT done: repair, major compaction, CL downgrade
  Risks: disk headroom, unknown writes, data integrity ...
  Next safe check: ...; expected result if H1 vs H2
  Rollback/stop condition: ...
  Next status update: ... UTC
~~~

Document **what was NOT done** so the incoming engineer does not mistakenly assume a branch was ruled out. If a branch is blocked by missing permissions or telemetry, note the blocker and who owns access.

### 15.5. Post-Incident: Root Cause Analysis and Observability Improvements

A post-incident review should not just list "add more alerts". It should answer:

1. Why was detection slower than first-bad?
2. Why was scope hard to isolate — missing query fingerprint, deployment, DC, or coordinator labels?
3. Were change diffs tracked with effective timestamps?
4. What evidence was lost to restarts, log rotation, or retention?
5. Did we confuse HTTP p99 with coordinator p99, or misread units?
6. Did mitigation create unknown writes or consistency downgrades?
7. What tests can reproduce the mechanism in a lab without copying real data?
8. What questions or guardrails should the runbook add to speed up next time?

When the cause cannot be determined, record **root cause = unresolved with remaining hypotheses** rather than fabricating an overconfident story. A postmortem aims to reduce detection time and impact, not assign personal blame.

## 16. Self-Assessment Questions and On-Call Checklists

### Exercise 1 — Late Alert

Dashboard p99 breached the threshold starting in the 10:00–10:01Z bucket, but the pager fired at 10:06Z. Should we record "incident started at 10:06Z"?

**Answer:** no. Distinguish **first-known-bad** from **alert fired**. Alerts have evaluation/pending intervals plus scrape and ingestion lag; exact onset precision also depends on source resolution.

### Exercise 2 — Two Nodes Report Different States

N1 reports N2 `UN`, while N3 reports N2 `DN`. Can we assert the whole cluster is consistent and N2 is healthy?

**Answer:** no. `nodetool status` reflects the gossip view of the queried node. Gather multi-node outputs at aligned UTC times, and inspect networking, driver topology, host/process health, and membership timestamps.

### Exercise 3 — Does AllNodesFailed Mean the Whole Cluster Is Down?

An application sees `AllNodesFailedException`. Is it valid to conclude the entire Cassandra cluster is Down?

**Answer:** not yet. The driver may fail to use coordinators in its query plan due to pool exhaustion, TLS, network addressing, throttling/stream exhaustion, or server errors. Inspect per-node causes, other apps, local DC, and node health.

### Exercise 4 — Healthy Coordinator, Slow HTTP

HTTP p99 is 800ms; `nodetool proxyhistograms` shows coordinator read p99 at only a few ms. Does that prove poor application code?

**Answer:** not yet. Compare aligned time windows, query cohorts, and percentiles, and check driver queues, connection pools, networking, paging, serialization, callback threads, and the HTTP gateway. Two p99s from mismatched distributions cannot be compared directly.

### Exercise 5 — Deploy After Onset

Reliable first-bad is 09:42Z; a deploy started at 09:48Z. Should the deploy be called the initiating cause?

**Answer:** no, unless timestamps/telemetry are wrong or the deploy had an unrecorded earlier step. A change occurring **after** onset cannot be the initiating cause under the current timeline, though it may worsen or mitigate the issue.

### Exercise 6 — Same Query, Only One Partition Is Slow

All node statuses are `UN`, yet tenant A's partition has a 2-second SELECT p99 while tenant B on the same table sees 30ms. Where should you look?

**Answer:** compare partition rows/bytes/tombstones, hot-key request share, token/replica set, clustering range, paging, and a sampled query trace. Do not restart every node because of one slow key.

### Exercise 7 — Concurrent Compaction Backlog

N2 pending compactions rise at the same time API errors appear. Is this definitely the root cause?

**Answer:** no. Check temporal order, IO/GC correlation, request routing through N2, and healthy controls; compaction may be a consequence of a write burst or a secondary factor.

### Exercise 8 — Reporting Percentiles

Someone averages the p99 of N1 and N2 to report cluster p99. What is the flaw?

**Answer:** percentiles cannot be summed or averaged like request totals. Use histogram buckets/sample distributions with shared semantics and windows, or report per-node p99 alongside traffic share.

### Exercise 9 — Treating WriteTimeout as a Rollback

An app hits `WriteTimeoutException` and automatically retries `counter + 1` three times. Why is this dangerous?

**Answer:** the write may have committed while the ACK was lost; counter increments are non-idempotent and can be multiplied. Record an UNKNOWN outcome, and use operation IDs/reconciliation and an explicitly designed retry policy.

### Exercise 10 — Tracing 100% of Traffic

The team enables `setTracing(true)` on 100% of CQL requests to "get more evidence". Should they do this?

**Answer:** no. Tracing adds overhead and writes to `system_traces`, which can degrade an already stressed cluster. Use small authorized samples for a specific fingerprint/CL, then turn it off.

### Exercise 11 — Errors Drop After Shedding Load

After throttling offered requests/s from 5,000 down to 500, p99 recovers and timeouts disappear. Does this mean the cluster is fixed?

**Answer:** not yet. Load may simply have dropped below the overload threshold. RESOLVED criteria must check user SLO **at representative traffic**, along with data/integrity/repair state and root-cause follow-up.

### Exercise 12 — Missing Telemetry

Grafana shows zero `DriverTimeoutException` since the deploy, yet exceptions still appear in application logs. How do you investigate?

**Answer:** check whether the metric is enabled, exporter/label mappings, scrape gaps, process restarts, and units/types. "No series" or a zero series does not prove zero errors.

### 0–5 Minute Checklist

- [ ] Record current UTC, owner, severity, and user impact.
- [ ] Identify first-known-bad and last-known-good **with uncertainty interval**.
- [ ] Do not equate alert time with onset time.
- [ ] Explicitly note unknown queries/services/DCs; do not assume everything is failing.
- [ ] Check for data loss risk, full disks, or widespread unavailability and prioritize mitigation per runbook.
- [ ] Capture minimal snapshots **before** interventions whenever safe.

### 5–15 Minute Checklist

- [ ] Compare healthy and affected cohorts by version, DC, API, query, and key.
- [ ] Classify exceptions: driver/server/gateway/validation/throttling.
- [ ] Distinguish the coordinator node from the replica set without conflating roles.
- [ ] Collect status from multiple nodes if suspecting gossip/network partition.
- [ ] Inspect logs/metrics in the same window with normalized timezone and units.
- [ ] Build the change inventory (deploy, schema, CL, TLS, repair, compaction, network, workload).
- [ ] Save evidence IDs/links, source clock/offset, sampling, and data gaps.

### 15–30 Minute and Handoff Checklist

- [ ] Write at most a few hypotheses with prediction/falsifier/risk.
- [ ] Evaluate temporal fit, scope fit, and mechanism fit.
- [ ] Separate facts from inferences and state confidence.
- [ ] Run low-impact checks first; do not run repair/major compaction/truncate without cause.
- [ ] For any mitigation, ensure approval, rollback plan, and before/after comparisons using identical metrics/filters.
- [ ] Track errors/timeouts **alongside** p95/p99; do not hide errors inside latency.
- [ ] Ensure CL/TTL/LWT semantics and unknown writes are respected.
- [ ] Report observed results, unknowns, and the owner for next steps.
- [ ] Define exit criteria: SLO + representative traffic + health + integrity, not just `UN`.

## 17. References

1. Apache Cassandra — [Troubleshooting](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/): methodology for isolating hosts/nodes, logs, and tools.
2. Apache Cassandra — [Use Nodetool](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/use_nodetool.html): per-node `status` views, `proxyhistograms`, `tablehistograms`, `tpstats`, `compactionstats`.
3. Apache Cassandra — [Reading Cassandra Logs](https://cassandra.apache.org/doc/stable/cassandra/troubleshooting/reading_logs.html): `system.log`, `debug.log`, `gc.log`, logback, and reading logs by event.
4. Apache Cassandra — [Monitoring](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): Table/ClientRequest/DroppedMessage/Compaction/CommitLog/JMX metrics and units.
5. Apache Cassandra — [nodetool Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): checking version-accurate command syntax and distinguishing read vs. write operations.
6. Apache Cassandra — [tablehistograms](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablehistograms.html) and [tablestats](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/tablestats.html): partition size, SSTables/read, latency, and data statistics.
7. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): READ_TIMEOUT, WRITE_TIMEOUT, UNAVAILABLE, error-response classes, and retry semantics.
8. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): driver session/node metrics configuration, pooling, and measuring attempts.
9. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): per-statement query trace, `ExecutionInfo.getTracingId()`, and sampling limits.
10. Apache Cassandra Java Driver 4.19 — [Performance](https://apache.github.io/cassandra-java-driver/4.19.0/core/performance/): Netty hot path, driver tracking, metrics overhead, throttling.
11. Apache Cassandra Java Driver 4.19 — [Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/) and [Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): driver queues/timeouts and additional executions.
12. Apache Cassandra Java Driver 4.19 — [Statement Attributes](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, CL, tracing, timeout, page size, routing, and profiles.
13. Apache Cassandra — [Data Modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/): partition keys, clustering, query-first modeling, and signs of bad partitions.
14. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html) and [Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): TTL, deletion markers, repair/grace, and read amplification.
