# Writing Architecture Decisions with Experiments, Cost, and Assumptions

In systems using **Apache Cassandra**, a decision such as "partition by day," "read at LOCAL_QUORUM," or "use TimeWindowCompactionStrategy" should not rely solely on intuition or general rules of thumb. Each choice's effectiveness depends on query shapes, partition-key distribution, write throughput, consistency requirements, retention duration, and the operational capabilities of **the application itself**.

A sound architectural decision must answer four questions:

1. **What problem is being solved?** State business constraints and measurable technical targets.
2. **What are we assuming?** Document unknowns, risk levels, and how assumptions will be verified.
3. **What evidence separates the alternatives?** Design experiments capable of falsifying hypotheses.
4. **What are the costs and triggers to revisit the decision?** Include resources, operations, complexity, and recovery capability.

The outcome is typically captured in an **Architecture Decision Record (ADR)**: a concise, versioned document explaining the context, considered options, evidence, decision, and criteria for re-evaluation. This is an integral part of Cassandra application architecture design, not post-deployment paperwork.

## 1. Starting from Queries, SLOs, and Constraints

Suppose a system collects telemetry from **20,000 devices**, with each device averaging **one event per minute**. The application requires:

| Need | Illustrative Constraint to Verify with Product |
|---|---|
| Event ingestion | ~333 writes/s average, 3,000 writes/s expected peak |
| Device history view | Read the 100 newest events or a time range for a single device |
| Write latency | Application-side p99 not exceeding 80 ms at target load |
| Read latency | Application-side p99 not exceeding 150 ms at target load |
| Data retention | 30 days from write time; clarify handling of late-arriving events |
| Availability | Tolerate one node failure in a single datacenter with RF = 3, within tested load limits |
| Consistency | Define data freshness required by read screens; do not assume all read paths share identical needs |

An **SLO** (Service Level Objective) is an application target, e.g., "99% of read requests complete under 150 ms over a specified measurement window." An SLO must state the measurement point (client, API, or Cassandra coordinator), test load, allowable error budget, and node-failure conditions. Saying merely "fast queries" gives no way to judge whether an option passes.

For a projected workload, perform a back-of-the-envelope calculation first:

~~~text
events_per_day = 20,000 * 1 * 1,440 = 28,800,000
average_writes_per_second = 28,800,000 / 86,400 ≈ 333
~~~

These numbers are **assumed exercise inputs**, not benchmark results. In particular, an average of 333 writes/s reveals nothing about peak bursts, batch arrivals, skew across devices, or actual read/write ratios.

### Distinguishing Facts, Assumptions, and Decisions

| Category | Example | How to Handle |
|---|---|---|
| Verified fact | Current API queries history by device and time range | Cite traces, API specs, or logs |
| Assumption | No device sustains more than 10 events/s for extended periods | Inspect load distribution, especially p99 and per-device maxima |
| Constraint | Data may be retained for only 30 days | Confirm business rules and how the 30-day mark is calculated |
| Hypothesis | Daily bucketing keeps partition size within budget | Measure partition sizes after ingesting skewed test data |
| Decision | Use daily buckets if experimental thresholds pass | Record in ADR with evidence, consequences, and revisit triggers |

Never turn an unmeasured assumption into a "fact" merely because it appears in an architecture diagram.

## 2. Proposing Query-Driven Data Options

Cassandra is a **distributed wide-column** database. Data is distributed by **partition key**; rows within a partition are ordered by **clustering columns**. Table design must start from the queries to be served. A query unsupported by the partition key typically requires a dedicated table rather than distributed scans or relying on ALLOW FILTERING.

Consider three options for storing per-device event history:

| Option | Partition Key | Potential Benefits | Risks to Test |
|---|---|---|---|
| A — unbucketed | (tenant_id, device_id) | A single query can span long history | Partitions grow huge; reads and compaction become unpredictable |
| B — daily bucket | (tenant_id, device_id, event_day) | Bounds time per partition; clean daily queries | Multi-day reads require bounded fan-out |
| C — hourly bucket | (tenant_id, device_id, event_hour) | Shrinks partitions for high-rate devices | More partitions, more queries, requires result merging |

Do not pick C solely because "smaller partitions are always better": every extra partition adds metadata, query overhead, and coordination cost. Do not pick A merely for fewer partitions: an effectively unbounded partition is a hazard under long retention or malfunctioning noisy devices.

Illustrative schema for option B:

~~~sql
CREATE KEYSPACE IF NOT EXISTS telemetry
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS telemetry.events_by_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id timeuuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id DESC)
  AND default_time_to_live = 2592000;
~~~

**Explanation:**

- The triple **(tenant_id, device_id, event_day)** forms a partition; all three values must be supplied when querying this partition.
- **occurred_at** and **event_id** are clustering columns. **event_id** disambiguates events sharing the same timestamp; the application must preserve the same ID when retrying an event.
- A 2,592,000-second TTL equals 30 days counted from write time, **not automatically from occurred_at**. If the business requires expiration strictly by event-generation time, define a separate policy for late-arriving events.
- The value **dc1** is an illustrative datacenter name. Replace it with your actual datacenter name; setting RF = 3 in one DC does not give full-DC outage resilience.

Example key-aligned query:

~~~sql
CONSISTENCY LOCAL_QUORUM;

SELECT occurred_at, event_id, payload
FROM telemetry.events_by_device_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND device_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T08:00:00Z'
  AND occurred_at < '2026-11-22T00:00:00Z'
LIMIT 100;
~~~

Multi-day queries must identify the relevant daily buckets upfront, read with pagination, and merge chronologically in the application. Never assume one table satisfies every query type. For example, "list alerts by tenant and severity" may require another table **alerts_by_tenant_severity_day**, along with its own update rules and sync-lag tolerance.

### When Partition Assumptions Break

At an average rate of one event/minute and 1 KiB payload, one device generates roughly **1.4 MiB of payload/day**. Yet a malfunctioning device emitting **200 events/second** produces roughly **16.5 GiB of payload/day**. That is a massive difference even while average device counts look unchanged.

Therefore, measure **per-device event distribution**, not just averages. If "hot" devices occur, test hourly buckets, shorter buckets, or controlled sharding. Adding shards increases the number of partitions read; evaluate it experimentally rather than treating it as free.

## 3. Selecting Consistency Levels via Business Contracts

In Cassandra, **replication factor (RF)** specifies replica count and **consistency level (CL)** specifies how many replicas must respond successfully per operation's rules. Both choices impact latency, availability, and observed freshness.

With RF = 3 in **a single datacenter**:

| CL | Response Requirement in Example | Best Suited When | Trade-Off |
|---|---|---|---|
| LOCAL_ONE | One replica in local DC | Dashboard reads tolerating slightly stale data | May observe older values |
| LOCAL_QUORUM | Two of three replicas in local DC | Stronger guarantees needed for same-DC reads/writes | Latency and timeout probability may rise |
| ALL | All three replicas | Very rare cases requiring every replica to acknowledge | One unresponsive replica fails the operation |

If the same DC has N = 3 replicas, writing with W = 2 and reading with R = 2 satisfies **R + W > N**: the acknowledged replica sets share at least one overlapping replica under normal conditions. This is the core intuition behind picking LOCAL_QUORUM for both reads and writes. However, it **does not turn every interaction into a linearizable transaction**: concurrent writes, timestamp conflicts, replica streaming, and multi-row operations still require attention. For conditional compare-and-set, Cassandra offers **lightweight transactions (LWT)** using consensus with distinct costs; test them separately.

Two error classes must also be distinguished: **UNAVAILABLE** when insufficient replicas meet the CL condition, and **READ_TIMEOUT/WRITE_TIMEOUT** when replicas fail to respond in time. Required replica counts, network conditions, and load govern the likelihood of each error; neither can be deduced from RF alone.

A testable hypothesis:

> "LOCAL_QUORUM writes and LOCAL_QUORUM reads achieve write p99 under 80 ms and read p99 under 150 ms at 3,000 writes/s peak; when one node dies, error rates stay below the agreed SLO threshold."

Hypotheses must include **explicit error thresholds** accepted by the business. If benchmarks fall short, adjust CL or topology based on each read path's freshness requirements—never silently lower CL just to make latency charts look prettier.

## 4. Designing Experiments Capable of Falsifying Options

### 4.1. Lock Hypotheses and Criteria Before Running

A minimal experiment table:

| ID | Hypothesis | Measurement Method | Illustrative Criterion |
|---|---|---|---|
| H1 | Daily buckets fit 24-hour history queries | Replay realistic query shapes with realistic time distributions | Read p99 ≤ 150 ms at target load |
| H2 | LOCAL_QUORUM sustains peak write load | 3,000 writes/s with concurrent read workload | Write p99 ≤ 80 ms; error rate within agreed SLO |
| H3 | Partitions do not bloat under skewed load | Ingest both normal and hot devices | Max and p99 partition size stay within measured budget |
| H4 | System recovers after losing one node | Controlled stop of one node in test environment | Latency, errors, backlog, and recovery time meet thresholds |
| H5 | 30-day retention policy is operationally viable | Observe TTLs, tombstones, compaction, and repair | Disk usage stabilizes with no runaway backlog |

The 80/150 ms thresholds are **simulated exercise targets**. Partition-size and error-rate thresholds must come from business analysis, hardware capacity, and baseline measurements. There is no single "correct" partition size for every Cassandra deployment.

### 4.2. Fix Conditions for Fair Comparisons

For each option A/B/C, record:

1. Cassandra version, Java driver version, heap/GC settings, node count, CPU, RAM, disk type, network, topology, and RF.
2. Schema/CQL, read/write CL, retry policy, timeouts, page size, TTL, and compaction strategy.
3. Dataset matching production distributions for tenants, hot devices, payloads, event times, and late-arriving events.
4. Concurrent read/write workload: query mix ratios, ramp-up, run duration, connection counts, and Java client concurrency.
5. Run timestamp, warm-up state, result snapshots, environment config, and load-generator commit hash.

Never compare A running on an empty disk against B running under heavy compaction backlog. Nor compare two options where one uses LOCAL_ONE and the other uses LOCAL_QUORUM without documenting the difference; that changes **two variables at once**.

A suggested test profile: ramp up and stabilize for 20 minutes, run 60 minutes at target load, spike to peak for 30 minutes, take one node offline, and observe recovery. Repeat runs to separate config effects from random variance. Total duration must be long enough to observe flushes, compaction, and dataset behavior; a one-hour test **cannot prove** 30-day TTL behavior.

### 4.3. Measure from Both the User Perspective and Cassandra

| Measurement Group | Metrics to Capture | Why Needed |
|---|---|---|
| Java Client / API | Throughput, p50/p95/p99, timeouts, errors, retry counts | Shows real application SLO compliance |
| Queries | p99 per query shape, fan-out, page counts | Exposes bad queries hidden by averages |
| Key distribution | Partition size p95/p99/max, top hot devices, requests/key | Detects hotspots |
| Nodes | CPU, disk I/O, disk usage, network, heap, GC pauses | Pinpoints resource bottlenecks |
| Read/write paths | Pending tasks, dropped messages, read/write latencies | Reveals saturation before the API surfaces failures |
| Data lifecycle | SSTable count, tombstones, pending compactions, repair time | Evaluates long-term TTL and compaction impact |
| Node failures | Errors during incident, recovery time, post-recovery backlog | Tests fault-tolerance hypotheses |

Basic inspection commands in a **test environment**:

~~~bash
nodetool status
nodetool tablestats telemetry.events_by_device_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

These commands do not replace time-series metrics and client-side tracing. Load generators must issue realistic queries through the driver (e.g., a Java program using prepared statements); generic benchmarks lacking your application's query shapes can answer the wrong question. Keep **failure-run results** too: the load level where p99 spikes is often more informative than a clean low-load run.

For compaction, evaluate candidates such as SizeTieredCompactionStrategy, LeveledCompactionStrategy, or TimeWindowCompactionStrategy individually based on read/write profiles. **TWCS** is often considered for append-mostly time-series data with uniform TTLs and rare updates; late writes or updates mixing ages inside SSTables can degrade expiration efficiency. Setting TTL and **gc_grace_seconds** must account for repair, tombstones, and data-resurrection risks if a replica missed a delete. Never shrink gc_grace_seconds solely to reclaim disk without proving a safe repair cadence.

## 5. Putting Cost in the Same Table as Performance

Cassandra cost is more than instance rental. Account for **replication**, safe disk headroom, compaction, inter-node/cross-DC networking, backups, monitoring, on-call support, repairs, and engineering effort when one business action must write multiple tables.

### 5.1. Estimating Capacity in Explicit Units

Assume each event averages **1 KiB of logical data** retained for 30 days:

~~~text
28,800,000 events/day * 1 KiB ≈ 27.5 GiB/day
27.5 GiB/day * 30 days ≈ 824 GiB logical data
824 GiB * RF 3 ≈ 2.41 TiB replicated data
~~~

This is an **order-of-magnitude estimate**, excluding full row/column overhead, indexes, Bloom filters, memtables/SSTables, tombstones, uncompacted data, snapshots, and backups. Assuming a 1.25x storage expansion factor and targeting at most 60% disk utilization, approximate provisioned disk capacity is:

~~~text
provisioned_capacity
  ≈ 2.41 TiB * 1.25 / 0.60
  ≈ 5.02 TiB
~~~

The factors **1.25 and 60% are illustrative only**; replace them with empirical observations and your system's operational rules. If data compresses well, actual size may be smaller; with heavy tombstones/compaction or additional query tables, cost may be higher.

### 5.2. Total Cost of Ownership Model

~~~text
monthly_cost =
    node_count * node_hourly_price * hours_per_month
  + separately_billed_storage_GiB * storage_price_per_GiB_month
  + billable_network_egress_GiB * network_price_per_GiB
  + backup_and_observability_cost
  + operations_and_incident_cost
  + migration_or_development_cost_amortized
~~~

If node instance pricing includes local disks, do not double-count storage on the storage line. Add costs per DC, staging environments, and spare capacity needed to recover from node failures. When comparing A/B/C, use **the same time horizon**, growth assumptions, and risk posture; never compare only "node count today."

Aspects to make explicit in the ADR:

- **Direct costs:** node count, CPU/RAM/SSD, bandwidth, backups, monitoring.
- **Query-shape costs:** multi-bucket fan-out, duplicated tables for distinct read paths, and extra write amplification.
- **Operational costs:** repair duration, compaction backlog, node scaling, hotspot mitigation, and node replacement.
- **Change costs:** data backfills, dual-writes, reconciliation, and rollbacks if partition keys must change after launch.

An option that is a few milliseconds slower yet cheaper and simpler to operate may win if it still meets the SLO. A cheaper option that fails criteria when one node dies cannot be deemed fault-tolerant.

## 6. Turning Measurements into Decisions

After running experiments, place all options in **the same evidence table**. The numbers below are **simulated figures solely to illustrate ADR structure, not actual Cassandra benchmarks**:

| Metric Under Identical Workload | A — unbucketed | B — daily bucket | C — hourly bucket |
|---|---:|---:|---:|
| History read p99 | 220 ms | 110 ms | 98 ms |
| Write p99 | 74 ms | 70 ms | 73 ms |
| Largest partition | 8 GiB | 72 MiB | 16 MiB |
| Estimated provisioned storage | 4.9 TiB | 5.0 TiB | 5.4 TiB |
| 7-day history read | 1 partition | Up to 7 buckets | Up to 168 buckets |
| Meets 150 ms read SLO | No | Yes | Yes |

In this example, B may be a more sensible initial choice than A and C **if** fault-tolerance, consistency, and operational tests also pass. C shrinks partitions further at the cost of higher fan-out on multi-day reads. If hot devices push B's partitions past safe bounds, test an adaptive bucketing policy or option C before finalizing B.

**Do not mistake correlation for causation:** if B outperforms A, verify the difference came from the partition key rather than changes in compaction settings, caches, dataset, or disk state.

### Complete ADR Structure Template

~~~markdown
# ADR-012: Daily Bucketing for Device History

- Status: Proposed (not accepted without real evidence)
- Date: YYYY-MM-DD
- Owners: Ingestion and Query Team
- Context: 20,000 devices, history reads by device and time,
  30-day retention; read SLO p99 <= 150 ms, write p99 <= 80 ms.

## Options
- A: Partition by tenant + device, unbucketed.
- B: Partition by tenant + device + day.
- C: Partition by tenant + device + hour.

## Assumptions to Verify
- Event distribution across devices and tenants is sufficiently stable.
- 3,000 writes/s peak reflects at least the target product load.
- Queries spanning > 7 days are rare or served by a dedicated API.
- 30-day TTL from write time aligns with late-arriving events.

## Experiments and Evidence
- Links to load-test reports, cluster config, and driver version.
- Table of p95/p99/timeouts, partition sizes, compaction, and cost.
- Single-node failure test results and recovery phase metrics.
- Explicit list of untested scenarios.

## Proposed Decision
- Choose B if all locked acceptance criteria pass.
- Use prepared statements and partition-keyed queries.
- Define CL by business contract per read/write path.

## Consequences and Trade-Offs
- Cross-day reads require bounded fan-out, paging, and merging.
- Late-arriving events and hot devices need dedicated policies.
- Changing buckets later requires backfills and a data migration plan.

## Revisit Triggers
- p99 breaches SLO across multiple consecutive measurement windows.
- Partition sizes or load skew exceed budgets.
- Growth diverges significantly from assumptions, or retention/queries change.
- Operational costs exceed the approved budget.
~~~

To transition from **Proposed** to **Accepted**, replace placeholder report links with traceable data and record approvers, decision date, and measured configuration versions. When a decision is later replaced, keep the old ADR with status **Superseded** linking to the new ADR; never delete the history explaining why the system was designed that way.

## 7. Connecting Architectural Decisions to Java Code

An ADR stating "query by partition, write at LOCAL_QUORUM, and retry idempotently" must be verifiable in code. For example, with **DataStax/Apache Cassandra Java Driver 4.x**, prepare statements once and reuse them:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class EventWriter {
    private final CqlSession session;
    private final PreparedStatement insert;

    public EventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO telemetry.events_by_device_day " +
            "(tenant_id, device_id, event_day, occurred_at, event_id, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)"
        );
    }

    public void save(
            UUID tenantId,
            UUID deviceId,
            LocalDate eventDayUtc,
            Instant occurredAt,
            UUID eventId,
            String payload) {
        // eventId, timestamps, and values must remain identical across retries.
        BoundStatement statement = insert.bind(
            tenantId, deviceId, eventDayUtc, occurredAt, eventId, payload
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(true);

        session.execute(statement);
    }
}
~~~

**Limitations of the example:** the class receives a lifecycle-managed CqlSession from application startup. `eventId` must be a UUID matching the **timeuuid** column, generated **once per event** before calling `save`; never generate a fresh ID after a timeout. The **setIdempotent(true)** flag is valid only when the exact same event is rewritten with **identical primary key and payload**, with no counters or non-idempotent side effects. If the system has competing writes on the same key, complex timestamps, TTLs, or reconciliation rules, re-evaluate retry safety and retry policies.

A timeout does not prove a write failed on all replicas: replicas may have persisted it while the client missed acknowledgments. Therefore, **idempotency keys, duplicate handling, and retry observability** are architectural decisions, not mere Java driver configuration tweaks. In systems requiring "create at most once" guarantees, evaluate LWT explicitly instead of assuming a plain INSERT enforces business uniqueness.

Additionally, **date buckets must be computed consistently in UTC** from the event timestamp or agreed policy; if one service computes buckets in a device's local timezone and another uses UTC, the same event can be written to and read from two different partitions.

## 8. Review Checklist and Exercise

Before accepting a Cassandra ADR, ask yourself:

- **Queries:** Are query shapes and constraints for partition keys, clustering columns, paging, and fan-out listed?
- **Assumptions:** Are averages, p99, extreme cases, and how assumptions could be invalidated documented?
- **Consistency:** Does CL align with freshness needs, node failures, retries, and concurrent-write scenarios?
- **Experiments:** Are there production-like datasets, repeated measurements, peak loads, compaction, TTL, and failure tests?
- **Cost:** Are RF, headroom, backups, networking, operations, and multi-table write amplification included?
- **Reversibility:** Are revisit triggers, owners, migration plans, and rollback strategies defined?

**Hands-on exercise:** On the same system, suppose 1% of devices suddenly emit 50 events/second and the UI must read the last 72 hours. Complete the following: (1) recalculate maximum payload size under daily vs. hourly bucketing; (2) design an experiment comparing B against C or sharded buckets; (3) define SLOs and fan-out budgets; (4) build a cost table across three capacity tiers; (5) write a **Proposed** ADR with at least three falsifiable assumptions. Where measurements are missing, state **"no evidence yet"** explicitly rather than picking an option on gut feeling.

**Key takeaway:** A Cassandra design becomes a **defensible architectural decision** only when it states the queries it serves, the assumptions it depends on, repeatable experimental results, the costs incurred, and the conditions under which the team will revise the decision.
