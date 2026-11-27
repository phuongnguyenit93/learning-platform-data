# Finalizing Diagrams, Design Decisions, and Runbooks with Empirical Evidence

A system built on **Apache Cassandra** is architecturally complete only when the team can explain three things: **how the system operates**, **why the current design was chosen**, and **what to do when initial assumptions no longer hold**. Diagrams, Architecture Decision Records (ADRs), and operational runbooks must all reference measured data rather than existing as three isolated, unverified documents.

This integrated practice embeds Cassandra inside a Java application flow, applying knowledge of **wide-column modeling, partition keys, query-driven tables, consistency levels, replication, compaction, repair, and failure handling**. Learners start with a candidate design, build experiments, and update all three documents from observed results. All traffic, SLO, and cost numbers below are **illustrative learning-scenario assumptions** and must not be treated as real benchmarks.

## 1. Problem Statement, Deliverables, and Completion Criteria

### 1.1. Scenario

An enterprise operates **12,000 cold-storage temperature sensors** across multiple customers and sites. Each sensor normally emits one reading **every 15 seconds**. The system exposes two APIs:

- **Q1 — Sensor history:** fetch the 100 most recent readings for a sensor, expandable across a time window of up to 48 hours.
- **Q2 — Site alerts:** fetch the 100 newest alerts for a site on a single day, supporting pagination and advancing to adjacent days.

The ingestion pipeline uses a queue or message broker to absorb traffic bursts; a Java worker writes readings into Cassandra. An alert detector consumes the same events and writes to the Q2-serving table. Because the two tables are updated asynchronously, the UI must tolerate a **small bounded synchronization lag**, with controlled retries and deduplication.

| Input parameter | Assumed value |
|---|---|
| Sensors | 12,000; average 4 readings/minute/sensor |
| Average write load | 800 readings/second |
| Peak write load to test | 5,000 readings/second for 30 minutes |
| Concurrent read load during test | 300 requests/second, mixing Q1 and Q2 |
| Reading retention | 14 days from write time |
| Alert retention | 90 days from write time |
| Write latency target | Java client p99 ≤ 100 ms at target load |
| Read latency target | API p99 ≤ 180 ms at target load |
| Steady-state error target | Request error rate < 0.1% within measurement window |
| Single-node failure test | Availability stays within approved error budget; must measure recovery time |

**Measurement note:** Java client p99 and API p99 are two distinct observation points. To claim an API SLO passes, measure end-to-end API latency, including multi-partition merging time. Because this prompt leaves specific node-failure error thresholds and recovery times unspecified, the team must agree on both values **before** executing the failure test.

### 1.2. Final Deliverables of This Practice

| ID | Deliverable | Verifiable criteria |
|---|---|---|
| D1 | Final context and deployment diagrams | Shows read/write paths, DC scope, RF, CL, retry components, and observation points |
| D2 | Query → schema → API traceability table | Q1/Q2 have matching partition keys and CQL queries |
| E1 | Experiment report | Records workload, environment, measurements, timestamps, runs, and pass/fail counts |
| A1 | Data/consistency design ADR | Documents assumptions, options, E1 evidence, decision, and review triggers |
| R1 | Operations and incident runbook | Specifies triggers, diagnostic commands, escalation thresholds, recovery criteria, and owners |
| T1 | Final traceability matrix | Maps parameters in D1/D2 to supporting sections in E1 and entries in A1/R1 |

The practice is considered complete when another engineer can **re-run the experiments**, trace evidence for each key decision, and follow the runbook to diagnose a simulated incident. Anything lacking evidence must be marked **UNVERIFIED** rather than checked off as passing.

## 2. Locking Down Requirements, Assumptions, and Fault Domains

Before drawing diagrams, fill out an assumptions register with explicit owners:

| ID | Statement to verify | Risk if false | Expected evidence source |
|---|---|---|---|
| AS-01 | Most sensors emit 4 records/minute | Oversized partitions if a sensor malfunctions | Per-`sensor_id` record distribution, p95/p99/max |
| AS-02 | Devices/producers reuse the same `event_id` on retry | One event creates duplicate rows | End-to-end trace from producer to consumer |
| AS-03 | APIs only read by sensor or site and day | Ad-hoc scatter queries emerge | Query logs and API contracts |
| AS-04 | Alert lag behind raw readings is acceptable | Divergence between the two write streams | Business lag threshold and end-to-end latency measurement |
| AS-05 | Losing one node does not cost DC quorum | `LOCAL_QUORUM` operations fail | Single-node kill test in staging |
| AS-06 | Retention runs from write time, not sensor measurement time | Late-arriving events live longer than expected | TTL and late-arrival tests |

Classify each as **confirmed**, **assumed**, **refuted**, or **untested**. If AS-02 proves false, every claim about retry safety anchored on stable IDs must be revised, including Java code and runbooks.

The exercise boundary is **a single Cassandra datacenter** of three nodes placed across three independent fault domains when infrastructure permits (e.g., three availability zones). Replication factor **RF = 3**, with candidate read/write consistency **LOCAL_QUORUM**. With three replicas in one DC, `LOCAL_QUORUM` requires two responding replicas. Single-node fault tolerance is validated only after testing under target load; never extrapolate this to surviving a full-datacenter outage. True multi-DC deployments require separate design and testing for per-DC replication, local-DC selection, and failover routing.

## 3. Candidate Architecture Diagrams: Draw What Must Be Measured

### 3.1. Data Flow and Observation Points

~~~mermaid
flowchart LR
    S["Cold-storage sensors"] --> C["Collector / Ingest API"]
    C --> B[("Broker: events with stable event_id")]
    B --> W["Java reading writer"]
    B --> A["Java alert detector"]
    W --> D[("Cassandra — dc1, RF=3")]
    A --> D
    U["Dashboard / users"] --> Q["Java Query API"]
    Q --> D
    C -.-> M["Metrics + logs + tracing"]
    W -.-> M
    A -.-> M
    Q -.-> M
    D -.-> M
    M --> O["On-call / runbook"]
~~~

In the diagram, the **broker** represents an *at-least-once* message delivery system; no specific broker product is mandated for this exercise. To benchmark Cassandra in isolation, a Java load generator may write directly via the driver using the same prepared statements. Direct benchmark numbers **do not represent** end-to-end latency through the broker pipeline.

Paths to annotate in your submitted diagram:

1. **Reading write path:** collector → broker → worker → Cassandra; acknowledge messages only after receiving a successful response per application policy.
2. **Alert generation path:** broker → detector → Cassandra; alerts may lag behind readings.
3. **Read path:** dashboard → Query API → Cassandra; API explicitly resolves target buckets and caps page/query counts.
4. **Failure path:** timeouts/duplicates → bounded retries with backoff and jitter; unprocessable messages → dead-letter queue with alerting and replay procedures.
5. **Observability path:** every request carries a `trace_id`; emit metrics for latency, timeouts, retries, consumer lag, and node/compaction health.

Mark the **start and end boundaries of every SLO measurement**. If operators see healthy Cassandra read latency while users experience high API p99 due to fan-out, the diagram must pinpoint where that missing time goes.

### 3.2. Cassandra Deployment and Fault Domains

~~~mermaid
flowchart TB
    J["Java App / driver local DC: dc1"]
    subgraph DC["Cassandra datacenter: dc1 — RF=3"]
        N1["Node 1 — rack/zone A"]
        N2["Node 2 — rack/zone B"]
        N3["Node 3 — rack/zone C"]
        N1 <-->|"Gossip + streaming as needed"| N2
        N2 <-->|"Gossip + streaming as needed"| N3
        N3 <-->|"Gossip + streaming as needed"| N1
    end
    J -->|"Token-aware routing; candidate LOCAL_QUORUM"| DC
~~~

Three nodes and rack/zone separation are **inputs to the model**, not properties automatically produced by CQL. Spreading replicas across fault domains requires aligned snitch configuration, topology, and physical placement. A real deployment diagram must also record CPU/RAM, disk type, networking, Cassandra version, Java driver version, backup mechanism, and monitoring infrastructure.

Whenever schema, RF, consistency, node count, or fault domains change, bump the **diagram version**. Record date, author, and linked experiment references so diagrams never silently describe an outdated system from months ago.

## 4. Implementing Queries with Wide-Column Modeling and CQL

### 4.1. Deriving Tables from APIs

Q1 filters by **tenant + sensor + day**, sorted by time descending. Choose a three-part partition key; clustering columns hold observation time and event ID to prevent overwriting simultaneous events. Q2 filters by **tenant + site + day**, sorted by alert time. One table cannot—and should not—try to serve both distinct query paths.

The CQL example below assumes datacenter **dc1**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS coldchain
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS coldchain.readings_by_sensor_day (
    tenant_id uuid,
    sensor_id uuid,
    event_day date,
    observed_at timestamp,
    event_id timeuuid,
    temperature_c decimal,
    battery_mv int,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        observed_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (observed_at DESC, event_id DESC)
  AND default_time_to_live = 1209600;

CREATE TABLE IF NOT EXISTS coldchain.alerts_by_site_day (
    tenant_id uuid,
    site_id uuid,
    alert_day date,
    raised_at timestamp,
    alert_id timeuuid,
    sensor_id uuid,
    severity text,
    description text,
    PRIMARY KEY (
        (tenant_id, site_id, alert_day),
        raised_at,
        alert_id
    )
) WITH CLUSTERING ORDER BY (raised_at DESC, alert_id DESC)
  AND default_time_to_live = 7776000;
~~~

For Q1's table, **1,209,600 seconds = 14 days**; for Q2's table, **7,776,000 seconds = 90 days**. Default TTL counts from **write time**, not from `observed_at`/`raised_at`. Retries or updates can shift cell expiration timestamps. Compliance or business rules tied to event occurrence time must be enforced by dedicated retention policies rather than inferred from default TTL.

Every primary key column must be non-null. **`event_id` and `alert_id` are `timeuuid`s**, not arbitrary version-4 UUIDs. Under at-least-once delivery, retries of the same business event must preserve identical IDs, partition keys, and payloads; generating a new `timeuuid` after a timeout inserts an extra row instead of rewriting the existing one.

Two representative CQL queries:

~~~sql
CONSISTENCY LOCAL_QUORUM;

-- Q1: 100 newest readings in the specified day bucket
SELECT observed_at, event_id, temperature_c, battery_mv
FROM coldchain.readings_by_sensor_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND sensor_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
LIMIT 100;

-- Q2: 100 newest alerts at a site in the specified day bucket
SELECT raised_at, alert_id, sensor_id, severity, description
FROM coldchain.alerts_by_site_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND site_id = 33333333-3333-3333-3333-333333333333
  AND alert_day = '2026-11-21'
LIMIT 100;
~~~

**Multi-day queries:** the API must compute the relevant `event_day` or `alert_day` buckets, query sequentially or with **bounded** concurrency, paginate, and merge results. `LIMIT 100` applies **per partition query**, not across the entire 48-hour result set. To return the exact 100 newest records across the window, the API must merge-sort by `observed_at` and `event_id` and trim the final list. Reject overly wide time windows at the API boundary to prevent runaway fan-out.

### 4.2. Retry-Safe Java Write Path

The Java Driver 4.x example below accepts an application-configured `CqlSession`; in real services, reuse the session across requests and close it on shutdown:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;

public final class SensorReadingRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public SensorReadingRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO coldchain.readings_by_sensor_day " +
            "(tenant_id, sensor_id, event_day, observed_at, " +
            "event_id, temperature_c, battery_mv) VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public CompletionStage<AsyncResultSet> save(
            UUID tenantId, UUID sensorId, Instant observedAt,
            UUID stableTimeUuid, BigDecimal temperatureC, int batteryMv) {
        LocalDate utcDay = observedAt.atZone(ZoneOffset.UTC).toLocalDate();
        BoundStatement statement = insert.bind(
            tenantId, sensorId, utcDay, observedAt,
            stableTimeUuid, temperatureC, batteryMv
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(true);
        return session.executeAsync(statement);
    }
}
~~~

Set **setIdempotent(true)** only when retries reuse **identical keys and values**, with no counters, additions, or non-idempotent side effects. Specifically, the producer must generate and retain the **version-1 `stableTimeUuid` (`timeuuid`)** once per event; the repository must never mint a new ID on retry. Even when the primary key stays constant, retrying at a later time refreshes the TTL; if fixed-epoch expiration is required, design explicit expiry handling.

For broker-backed workers: commit offsets only after receiving acknowledgment at the chosen CL; on `WRITE_TIMEOUT`, **never assume the mutation was not persisted**. Use stable idempotency keys, bounded retries, backoff, jitter, retry monitoring, and a dead-letter queue. Never treat two writes to two tables as a pseudo "ACID transaction." Cassandra provides no RDBMS-style multi-table transactional isolation; correctness of asynchronous alerts relies on event contracts and reconciliation jobs.

### 4.3. Architectural Variants to Compare

| Code | History partition | Potential advantage | Where it can fail |
|---|---|---|---|
| V1 | `(tenant_id, sensor_id, event_day)` | Few buckets for 48-hour Q1 | Traffic spike on one sensor produces oversized daily partition |
| V2 | `(tenant_id, sensor_id, event_hour)` | Tighter partition size cap for "hot" sensors | 48-hour Q1 may need to read up to 48 buckets |
| V3 | Daily bucket + deterministic shard from stable attribute | Spreads write load of extremely hot sensors | API must read and merge across shards, raising cost |

V2 and V3 are **candidate alternatives to benchmark**, not implemented in the V1 code sample. Adopting V2 or V3 requires updating schemas, queries, retrieval logic, and data migration plans; `ALTER TABLE` cannot alter an existing table's partition key.

## 5. Writing the Experimental Plan Before Measuring

### 5.1. Hypothesis → Experiment → Acceptance Matrix

| Test ID | Hypothesis to falsify | Action | Example criterion |
|---|---|---|---|
| EXP-01 | V1 serves Q1/Q2 under steady load | Replay 800 writes/s and 300 reads/s using real queries | Write p99 ≤ 100 ms, API read p99 ≤ 180 ms, errors < 0.1% |
| EXP-02 | V1 sustains 5,000 writes/s peak | Ramp write load for 30 min while keeping Q1/Q2 mix | Stays within agreed latency and error thresholds |
| EXP-03 | Partitions stay bounded under skew | Simulate a hot sensor at 100 writes/s for a day's volume | p99/max partition size stays under approved budget |
| EXP-04 | `LOCAL_QUORUM` survives single-node loss | Stop one node cleanly in staging while running workload | Errors and latency stay within approved failure-mode bounds |
| EXP-05 | TTL/compaction avoids runaway backlog | Observe multiple flush/compaction cycles with TTL active | Disk usage and compaction backlog stabilize as modeled |
| EXP-06 | Retries do not duplicate business records | Inject timeouts and replay messages with identical `event_id` | One event maps to one primary key |
| EXP-07 | 48-hour Q1 cost is acceptable | Read 2 days on V1; compare V2 or V3 on identical data | Total API latency and request fan-out stay within budget |
| EXP-08 | Recovery runbook is actionable | Drill one timeout fault, one node failure, and one compaction spike | Recorded diagnosis time, actions, and verified recovery |

**Partition budgets have no universal Cassandra constant.** Pick an initial hypothesis threshold based on hardware and fragmentation—e.g., an internal target of **max < 256 MiB**—explicitly marking it as a hypothesis to verify on your Cassandra version and query shapes rather than a Cassandra-guaranteed limit. Likewise, measure partitions of **`alerts_by_site_day`**: a site generating heavy alert volume can become a hotspot even when reading partitions are evenly balanced. Assuming 400 bytes per reading:

~~~text
Normal: 4 * 60 * 24 = 5,760 readings/sensor/day
Normal payload/sensor/day ≈ 5,760 * 400 B ≈ 2.20 MiB

Hot sensor at 100 readings/second:
Payload/day  = 100 * 86,400 * 400 B ≈ 3.22 GiB
Payload/hour = 100 * 3,600 * 400 B ≈ 137 MiB
~~~

These figures reflect **logical payload only**, excluding metadata, storage overhead, and compaction amplification. If experiments show hot sensors sustain this rate, V1 will likely need revision; V2 bounds hourly partition size at the cost of reading more buckets. Base final conclusions on benchmark measurements rather than back-of-the-envelope math alone.

### 5.2. Procedure for Fair Comparisons

1. **Freeze configuration:** record Cassandra/driver versions, heap/GC settings, CPU/RAM, IOPS, node count, snitch, RF, CL, retry policy, timeouts, page size, schema, TTL, compaction strategy, and load-generator commit hash.
2. **Define dataset:** tenant/site/sensor counts, hot/cold skew, payload size, late-event ratio, chronological ordering, and alert ratio. Make the dataset large enough for partitioning and compaction effects to surface.
3. **Capture baseline state:** `nodetool status`, disk headroom, GC, pending compactions, read/write metrics, and consumer lag.
4. **Warm up and stabilize:** discard startup noise and run long enough to observe flushes/compactions; never treat a few clean minutes as proof of 14-day or 90-day retention stability.
5. **Run variants:** test V1 and V2/V3 on equivalent datasets, hardware, CLs, and initial state. Change **one design variable group** per comparison and document every difference.
6. **Repeat runs:** run multiple independent trials, capturing p50/p95/p99, throughput, errors, disk usage, CPU, and backlogs; investigate outliers.
7. **Inject faults in staging:** proceed only with recovery paths and operator clearance ready; log node stop/rejoin timestamps, every error, and recovery duration.
8. **Archive raw evidence:** export raw metrics, sanitized traces, configs, logs, charts, commit hashes, and operator identity. Never alter raw data when editing reports.

Never change both CL and partitioning strategy in the same comparison and credit the difference solely to partitioning. To compare `LOCAL_ONE` against `LOCAL_QUORUM`, run a **separate experiment** on the same dataset, explicitly recording freshness and fault-tolerance differences.

### 5.3. Metrics, Observation Commands, and Telemetry Sources

| Layer | Priority observations | Source |
|---|---|---|
| API / driver | Per-Q1/Q2 p50/p95/p99, timeouts, retries, fan-out request counts | OpenTelemetry/APM, Java driver metrics |
| Ingest | End-to-end event lag, queue depth, DLQ, duplicate `event_id`s | Broker and worker apps |
| Cassandra read/write | Latency, timeouts/unavailable, pending tasks, dropped messages | JMX/metrics, `nodetool` |
| Node | CPU, heap, GC, disk, network, disk saturation | Node exporter, JMX, infra metrics |
| SSTable / partition | SSTable count, tombstones, partition size, pending compactions | `tablestats`, `compactionstats`, custom metrics |
| Recovery | Node rejoin time, hint/repair backlog, post-incident p99 | Incident timeline, `nodetool`, metrics |

Read-only **observation** commands:

~~~bash
nodetool status
nodetool tablestats coldchain.readings_by_sensor_day
nodetool tablestats coldchain.alerts_by_site_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

Exact `nodetool` flags and metric names vary across Cassandra releases; record your environment's exact version and check command help. **`nodetool status`** reports node liveness, not application request success rates. **`nodetool tablestats`** reports aggregate table metrics; evaluating p99/max partition size and hot sensors requires key-level distribution statistics or version-appropriate diagnostic tools.

Sample raw-run CSV schema:

~~~csv
run_id,at_utc,commit,schema,rf,cl_read,cl_write,write_rps,read_rps,node_failure,read_p99_ms,write_p99_ms,error_pct,partition_max_MiB,compaction_pending,disk_used_GiB
EXP-01-R1,YYYY-MM-DDTHH:MM:SSZ,<commit>,V1,3,LOCAL_QUORUM,LOCAL_QUORUM,800,300,false,<measured>,<measured>,<measured>,<measured>,<measured>,<measured>
~~~

`<measured>` placeholders mark fields to populate; this row is a **template**, not experimental output. Also save raw latency histograms for p99, window lengths, and per-query success rates; storing only a single blended p99 makes diagnosing tail latency nearly impossible.

## 6. Analyzing Consistency, Replication, and Recovery Paths

With RF = 3 in `dc1`, `LOCAL_QUORUM` requires **2 acknowledgments out of 3 replicas** for normal operations. When one replica becomes unavailable, quorum remains achievable if the other two respond in time. However, resource pressure on the two surviving nodes, network jitter, repair activity, topology, and timeouts can still breach SLOs even when quorum is theoretically available.

Absent abnormal concurrent write races, writing at W = 2 and reading at R = 2 guarantees overlap because **R + W > RF**. That forms the rationale for `LOCAL_QUORUM`, **without** turning the entire application into a linearizable transactional store: account for last-write-wins, timestamp collisions, retries, late arrivals, and multi-table updates. When conditional check-and-set updates are required, evaluate lightweight transactions (LWT) and measure their cost separately.

### 6.1. Failure Scenarios Must Appear in Diagrams

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W as Java worker
    participant C as Cassandra
    participant O as Observability
    B->>W: Stable event_id
    W->>C: INSERT, LOCAL_QUORUM
    alt Ack received
        C-->>W: OK
        W-->>B: ACK message
    else WRITE_TIMEOUT / uncertain outcome
        C--xW: Timeout
        W->>O: Metric + trace + retry count
        W->>C: Bounded retry, same key and payload
        alt Acknowledged
            C-->>W: OK
            W-->>B: ACK message
        else Retry budget exhausted
            W->>O: Alert / route to DLQ
        end
    end
~~~

**A timeout does not mean Cassandra failed to write.** Some replicas may have persisted the mutation before the client deadline expired. If an `event_id` is regenerated as a fresh ID, retries create duplicate records. In the EXP-06 report, track at minimum: unique input IDs, distinct primary keys observed after retries, DLQ counts, and total resend counts.

### 6.2. Compaction, TTL, Tombstones, and Repair Are Coupled Decisions

When benchmarking V1/V2, record the active compaction strategy:

- **SizeTieredCompactionStrategy (STCS):** generally write-friendly; can incur read amplification across many SSTables.
- **LeveledCompactionStrategy (LCS):** reduces SSTables touched per read at the cost of higher compaction/write I/O; measure disk I/O carefully.
- **TimeWindowCompactionStrategy (TWCS):** strong candidate for time-series data with uniform TTLs written sequentially in time; late writes or frequent updates to older buckets degrade expired-SSTable reclamation.

Never declare TWCS optimal merely because the schema contains a timestamp. Monitor tombstones and backlogs across multiple data lifecycles. **`gc_grace_seconds`** protects against deleted data resurrecting if a replica missed a deletion; tuning it must account for repair reliability, node recovery SLAs, and Cassandra version. TTL expiration does not immediately free bytes on disk: space is reclaimed only once compaction safely purges the SSTables.

**Repair** synchronizes replicas after disconnects or missed writes as part of routine operations. Never trigger cluster-wide repairs blindly without checking node health, outage duration, disk/network headroom, and maintenance windows. In practice, design a repair schedule matching your version and topology, and rehearse it in staging before adding commands to production runbooks.

## 7. Cost Modeling to Ground Decisions in Performance and Operability

Assume an average of **400 bytes of logical data per reading**:

~~~text
events/day = 12,000 sensors * 4/min * 1,440 min = 69,120,000
logical_data/day = 69,120,000 * 400 B ≈ 25.75 GiB
logical_data/14 days ≈ 360.49 GiB ≈ 0.352 TiB
replicated_data/RF3 ≈ 1.056 TiB
~~~

For illustration, suppose on-disk overhead is **1.30× replicated logical data** and max usable capacity is capped at **60% of provisioned storage** for compaction headroom:

~~~text
provisioned_total ≈ 1.056 TiB * 1.30 / 0.60 ≈ 2.29 TiB
provisioned_per_node (3 balanced nodes) ≈ 0.76 TiB
~~~

The **1.30×** and **60%** factors are not universal constants. Actual storage depends on compression, table metadata overhead, indexes, tombstones, compaction, repairs, snapshots, and data growth. The 90-day alerts table **is not yet included** above because alert rates and payload sizes remain unmeasured; measure and add them before procuring capacity. If choosing V3 or adding query-driven tables, calculate extra write bytes and CPU/disk impact separately.

Cost comparison template for submission:

| Line item | Formula or measurement method | V1 daily | V2 hourly | V3 daily + shard |
|---|---|---|---|---|
| Measured storage | Used GiB per node, including compaction overhead | Not yet measured | Not yet measured | Not yet measured |
| CPU/IOPS at p99 load | Node metrics in the same test window | Not yet measured | Not yet measured | Not yet measured |
| Request fan-out Q1/48h | Partitions/pages accessed | Up to 2 daily buckets | Up to 48 hourly buckets | Depends on shard count |
| API p99 latency | Same workload + CL | Not yet measured | Not yet measured | Not yet measured |
| Operational effort | Repairs, hotspot mitigation, on-call | Sourced estimate | Sourced estimate | Sourced estimate |
| Migration risk | Backfill, dual-write, rollback | Low on greenfield system | Must verify | Must verify |

Total cost of ownership must account for **nodes and storage, networking, backups, observability, on-call effort, incident remediation, and migrations**. If a cloud provider bundles storage into node pricing, do not double-count it. Table rebuild and backfill effort are frequently overlooked when an alternative looks cheaper on paper.

## 8. Turning Evidence into an Approvable ADR

An ADR must document **data supporting or refuting the decision**. Any evaluation table lacking measurements must remain unpopulated:

| Criterion | Agreed threshold | V1 | V2 | Current decision |
|---|---|---|---|---|
| p99 Q1/48h | ≤ 180 ms at API | Not yet measured | Not yet measured | Undecided |
| Peak write p99 | ≤ 100 ms at Java client | Not yet measured | Not yet measured | Undecided |
| Max partition size | Approved engineering budget | Not yet measured | Not yet measured | Undecided |
| Single-node loss errors | Approved failure-mode threshold | Not yet measured | Not yet measured | Undecided |
| Monthly cost | Within project budget cap | Not yet measured | Not yet measured | Undecided |
| Migration complexity | Acceptable per rollout plan | Not yet evaluated | Not yet evaluated | Undecided |

### Evidence-Linked ADR Template

~~~markdown
# ADR-014 — Partitioning and Consistency for coldchain

Status: Proposed
Owner: <role/team name>
Updated: <YYYY-MM-DD>
Linked diagram version: D1-v<version>

## Context
- Q1: 100 newest sensor readings, querying up to 48 hours.
- Q2: alerts by site and day.
- Retain readings 14 days; alerts 90 days.
- Product-approved SLOs: <describe measurement window>.

## Options
- V1: partition by sensor/day.
- V2: partition by sensor/hour.
- V3: partition by sensor/day + shard.
- Writes and reads: compare LOCAL_QUORUM and cases needing another CL.

## Assumptions
- AS-01 ... (status, owner, evidence)
- AS-02 ...
- AS-05 ...

## Evidence
- EXP-01: <raw metrics link, timestamps, commit, operator>
- EXP-03: <partition distribution and hot devices>
- EXP-04: <failure timeline, error count, recovery duration>
- EXP-05: <SSTables/tombstones/compaction over time>

## Decision
- Selection: UNDECIDED while critical experiments remain unexecuted.
- Once measured: specify V1/V2/V3, CL, RF, TTL/compaction, and rationale.
- Explicitly list rejected alternatives and their corresponding evidence.

## Consequences
- Fan-out and paging complexity in the Java API.
- Operational costs for repair, backup, failover, and observability.
- Partition-key immutability cost and future migration plan.

## Re-evaluation Triggers
- Changes to query shapes/SLOs, hot-device traffic, retention, or fault domains.
- p99 latency, error rate, partition size, compaction backlog, or cost
  exceeding approved budgets.

## Approval
- Owner/Reviewer: <role>
- Approval date / config version: <when finalized>
~~~

Never populate an ADR with fabricated benchmark numbers as evidence. Every citation must include a **run ID**, timestamp, configuration, software version, dataset, and raw output. If EXP-04 fails while EXP-01 passes, never write "V1 meets all requirements"; record **failed fault-tolerance criteria** or document explicit conditional scope constraints.

## 9. Runbook: Turning Incident Detection into Verifiable Actions

A strong runbook is far more than a list of `nodetool` commands. Every scenario must specify **symptoms → blast radius → verification steps → safe actions → recovery criteria → handoff**.

### 9.1. Sample Runbook — Elevated `READ_TIMEOUT` or `WRITE_TIMEOUT`

**Trigger:** sustained rise in `READ_TIMEOUT`/`WRITE_TIMEOUT` rates relative to SLO over the agreed window; alerts should attach graphs broken down by endpoint, CL, and tenant.

**Diagnostic steps:**

1. Inspect request timeouts in the Java API and driver; distinguish `READ_TIMEOUT`, `WRITE_TIMEOUT`, and `UNAVAILABLE`. Log error rates, p99, retry counts, and incident onset.
2. Run **`nodetool status`** on an appropriate admin node to spot Down/Up nodes, verify topology, and check local-DC configuration.
3. Correlate CPU, disk latency, heap/GC, dropped messages, and pending tasks via **`nodetool tpstats`** alongside observability dashboards.
4. Check **`nodetool compactionstats`**, `tablestats`, and hot sensors/partitions. When unexpected fan-out appears, inspect Q1/Q2 query shapes and requested date spans.
5. Check networking, consumer lag, and application traffic spikes; separate upstream/broker failures from Cassandra bottlenecks.

**Cause-driven actions:** shed or throttle ingest load using measurable backpressure, cap concurrency/paging, restrict overly broad queries, remediate failed nodes per approved procedures, or schedule capacity scaling. Never blindly **lower consistency levels, raise timeouts indefinitely, disable query guards, or trigger cluster-wide repairs** just to make error charts look quieter.

**Recovery verification:** p99 and error rates meet SLO over a predefined observation window; retry/compaction backlogs and consumer lag return to safe levels; audit replayed events or DLQ entries. Record the timeline, impacted queries, applied changes, and rollback steps if needed.

### 9.2. Sample Runbook — Single Node Down

**Trigger:** a node leaves Up/Normal state or triggers loss-of-contact alerts; distinguish transient network blips from actual node failure.

1. Verify infrastructure health, topology, rack/zone status, and surviving replicas; monitor `LOCAL_QUORUM` success, latency, and errors.
2. Avoid adding unnecessary background load while degraded. If business rules allow, throttle traffic or defer batch workloads.
3. Execute the root-cause node recovery procedure (service, disk, network) with a clear owner and backups ready if needed.
4. Once the node rejoins, watch streaming/hints, latency, disk usage, and background queues. Assess repair needs based on Cassandra version, outage duration, and approved policies.
5. Close the incident only after the node stabilizes, read/write verification probes pass, metrics recover, and backlogs drain.

**Do not** mark the incident "recovered" the instant `nodetool status` shows `UN`: that is only one signal. Verify data integrity, backlogs, and user-facing metrics. If the node shows disk corruption or inconsistent data, escalate to authorized operators before attempting in-place fixes.

### 9.3. Sample Runbook — Rising Disk Usage and Compaction/Tombstone Backlog

**Trigger:** projected disk usage approaches headroom limits, pending compactions remain elevated, read p99 climbs, or tombstone scan rates spike.

Diagnose growth onset, write rates, whether TTLs have actually expired, SSTable counts and sizes, late-arriving writes, recent repairs, and lingering snapshots/backups on the node. Distinguish **retaining valid data within retention** from **unreclaimed expired data stuck behind compaction**. Test compaction changes in staging with the same dataset and measure write amplification, read latency, and disk headroom.

Never manually delete SSTables or snapshots or lower `gc_grace_seconds` without an approved procedure. Mitigations may include adding disk capacity, applying ingest backpressure, deploying measured compaction tuning, checking repair health, or adjusting retention after business sign-off. Confirm disk growth rate and pending compactions stabilize at expected levels rather than dropping briefly.

### 9.4. Fill-In Runbook Entry Template

~~~text
Incident ID:
Owner / Escalation contact:
Trigger and threshold:
Dashboards / queries / diagnostic commands:
Cassandra version, topology, RF/CL:
Actions PROHIBITED without approval:
Safe mitigations verified by EXP-xx:
Rollback or fallback procedure:
Incident exit criteria:
Links to timeline / logs / raw evidence:
Last drill date and verifier:
~~~

## 10. Cross-Document Traceability: Updating Three Artifacts Together

Suppose EXP-03 proves hot sensors push daily partitions past budget. The team must not edit just one line of the ADR—propagate the decision everywhere:

| Evidence-driven change | Diagrams D1/D2 | ADR A1 | Runbook R1 |
|---|---|---|---|
| Switch hot sensors to hourly buckets | Update schema, table names, bucket logic, and Q1 query counts | Cite EXP-03/EXP-07, document fan-out and migration costs | Add bucket/request count alerts and hot-partition thresholds |
| Change CL for an API | Annotate read/write paths and measurement boundaries | Explain consistency/latency trade-offs with dedicated EXP data | Update single-node outage impact and escalation conditions |
| Change retention / compaction | Update TTL/compaction table notes and schema version | Cite EXP-05, late-arrival behavior, and storage costs | Update disk/tombstone alerts and repair review cadence |
| Add nodes or alter topology | Redraw node counts, racks, DCs, and applied RF | Cite failure/capacity tests and cost analysis | Update quorum checks and node-down recovery steps |

**Sample traceability matrix:**

| Decision | Assumptions | Experiments | Linked artifacts | Status |
|---|---|---|---|---|
| DEC-01: V1 daily bucket | AS-01, AS-03 | EXP-01, EXP-03, EXP-07 | D2-v1, ADR-014, R1-hot-partition | Pending |
| DEC-02: RF3, LOCAL_QUORUM | AS-05 | EXP-02, EXP-04 | D1-v1, ADR-014, R1-node-down | Pending |
| DEC-03: 14/90-day TTL | AS-06 | EXP-05 | D2-v1, ADR-014, R1-disk | Pending |
| DEC-04: Idempotent retry | AS-02 | EXP-06 | D1-v1, ADR-014, R1-timeout | Pending |

Never delete Pending rows just to make a report look finished. When an experiment refutes an assumption, mark status **Rejected/Needs revision**, link raw evidence, and open a replacement decision. Updated diagrams require a new revision; superseded ADRs remain preserved with status **Superseded**.

## 11. Organizing the Practice Session and Grading Results

### Phase A — Initialization

1. Confirm Q1/Q2 query contracts, SLOs, and failure-mode budgets.
2. Provision a staging Cassandra cluster, data generator, and Java driver 4.x app; never put real personal data or production tokens in reports.
3. Tag the commit/version of schemas and candidate D1/D2 diagrams. Apply schemas, smoke-test inserts/selects via prepared statements, and verify UTC bucket calculation.

### Phase B — Measurement and Fault Injection

4. Load data under both normal and skewed distributions; run EXP-01/02/03/07 under uniform conditions. Capture full histograms and errors, not averages alone.
5. Verify retries with identical `event_id` and timeouts in EXP-06; reconcile input IDs against persisted rows after message replays.
6. Inject a single-node outage in staging (EXP-04) and measure recovery; observe compaction/TTL in EXP-05 over a meaningful duration.
7. Compare V1/V2/V3 with evidence and cost tables. If time prevents running a full TTL cycle, explicitly document that testing limitation.

### Phase C — Finalization and Handover

8. Finalize D1/D2 diagrams, documenting proven decisions and remaining Pending items in the ADR.
9. Rehearse runbook R1 using two staging drills, logging time-to-diagnose and time-to-recovery; another team member must be able to follow the docs independently.
10. Complete traceability matrix T1, verify no stale schema or CL references remain, and schedule follow-up work for any Pending decisions.

### Self-Assessment Rubric

| Category | Max points | Pass indicator |
|---|---:|---|
| Sound query-driven wide-column model | 20 | No cluster-wide scans for Q1/Q2; well-chosen partition keys and bounded fan-out |
| Reproducible experimental evidence | 25 | Includes workload, environment, raw metrics, failure drill, and version tags |
| ADR with explicit assumptions & trade-offs | 20 | Separates measured facts from assumptions and defines review triggers |
| Executable, verifiable runbook | 20 | Defines triggers, diagnostics, safe actions, rollbacks, and exit criteria |
| Linkage across D1/D2 ↔ E1 ↔ A1 ↔ R1 | 15 | Every major design choice traces directly back to empirical evidence |
| **Total** | **100** | **Cannot auto-pass if any mandatory experiment remains unexecuted** |

Learners do not need every experiment to succeed. An experiment proving V1 fails under hot sensors is a **valuable result** if measured fairly, backed by preserved raw data, and used to update diagrams, ADRs, and runbooks.

## 12. End-of-Lab Critical Review Questions

1. If EXP-01 passes yet EXP-04 fails during a single-node outage, which entries in D1, the ADR, and the runbook must change?
2. If Cassandra p99 looks healthy yet API Q1/48h p99 breaches SLO, how do you measure fan-out and pagination to separate database issues from application issues?
3. If one sensor emits 100 readings/second for 24 hours, why can daily partitioning become risky even when total cluster load barely moves? What cost does hourly bucketing introduce in exchange?
4. If a producer resends an event with a **new `event_id`**, why does the ADR's "safe retry" guarantee break?
5. If disk usage keeps climbing after TTL expiration, which metrics must you inspect before concluding Cassandra failed to delete data?
6. If an operator switches CL from `LOCAL_QUORUM` to `LOCAL_ONE` to curb timeouts, what must be re-verified regarding data freshness and fault tolerance?
7. What shifts in data shape, traffic, or topology next quarter could invalidate a design decision approved in staging this month?

**Core takeaway:** diagrams describe the measurable deployment state, ADRs justify design choices, and runbooks guide action when reality diverges from assumptions. These three artifacts become **a single living system** when linked by shared decision IDs, experiment IDs, versions, and verification criteria—enabling a Cassandra architecture that can be defended, operated, and evolved with empirical evidence.
