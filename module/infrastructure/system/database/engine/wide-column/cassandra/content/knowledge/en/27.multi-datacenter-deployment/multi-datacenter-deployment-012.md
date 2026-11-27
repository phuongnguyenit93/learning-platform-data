# Regional Failover Drills and Measuring Affected Data Scope and Latency

## Goal and Scope

Deploying Apache Cassandra across multiple **datacenters (DCs)** distributes replicas and supports continued operations when one region fails. However, having replicas in a standby DC **does not automatically mean** an application can fail over immediately without data loss or latency spikes. You must separate: data **ACKed in the source DC**, data **converged in the target DC**, applications **routed to the right coordinator**, and services **recovered to acceptable levels**.

This lesson belongs to the **Multi-Datacenter Deployment** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It draws on partition keys, query-driven table design, replication, consistency levels, CQL, streaming, repair, compaction, error handling, and the Java Driver. The focus is on **regional failover drills and evidence-based impact measurement**, not merely flipping a configuration switch.

After this lesson, you will be able to:

1. Build a plan to shift application access from **DC A to DC B** without confusing client routing with changing replication factors.
2. Define and measure **RTO** (recovery time), **RPO** (data potentially at risk), alongside p95/p99 latency and error rates.
3. Reconcile expected data against actual reads in the target DC using an **external manifest of ACKed writes**.
4. Classify outcomes as **FOUND, MISSING, MISMATCH, READ_ERROR, UNKNOWN_WRITE** rather than lumping every error into data loss.
5. Select read/write consistency levels aligned with WAN outage tolerance and recovery requirements.
6. Practice CQL/Java in a multi-DC lab and plan **fencing, failback, repair, and backfill** after incidents.

> **Safety:** only intentionally sever networks, stop DCs, or shift traffic in **lab/staging environments authorized for fault injection**. In production, follow approved runbooks with monitoring, stop thresholds, rollback paths, and designated owners. Addresses, DC names, and timestamps in this lesson are illustrative only.

## 1. Reference Architecture and Three Failover Layers

Consider a Cassandra cluster with **two DCs**, three nodes each:

| Component | DC A: `dc_a` | DC B: `dc_b` |
| --- | --- | --- |
| Nodes | A1, A2, A3 | B1, B2, B3 |
| Keyspace RF | 3 | 3 |
| Initial applications | Handles primary traffic | Standby, or handles dedicated traffic |
| Illustrative default CL | `LOCAL_QUORUM` | `LOCAL_QUORUM` after failover |
| Condition to meet local quorum | 2 ACKs/responses in `dc_a` | 2 ACKs/responses in `dc_b` |

Normal and failover flow diagram:

~~~mermaid
flowchart LR
    U["Client / API Gateway"] --> R{"Traffic routing"}
    R -->|Before failover| AA["Application A"]
    R -. "After failover decision" .-> AB["Application B"]
    AA --> CA["Cassandra Coordinator dc_a"]
    AB --> CB["Cassandra Coordinator dc_b"]
    CA --> RA["Replicas A1, A2, A3"]
    CB --> RB["Replicas B1, B2, B3"]
    RA <-. "Cross-DC replication & repair" .-> RB
    LOG["Independent manifest / event log"] -. "Reconcile by marker" .-> AB
~~~

A drill spans at least **three layers**:

1. **Application and networking:** DNS/load balancers, API gateways, endpoints, sessions, TLS, secrets, connection pools, and external dependencies.
2. **Cassandra:** which DC holds the coordinator, local RF/CL, whether remote data arrived, hints/repair, and query serving capacity.
3. **Business data:** which writes were confirmed before the outage; after failing over, which markers are readable, missing, or divergent; and whether missing records can be replayed from external sources.

Merely flipping DNS or Java Driver config does not stream missing data from A to B. Conversely, having complete data on B's replicas before applications switch routes does **not achieve RTO** either.

## 2. Verifying RF and ACK Scope Before a Drill

The keyspace uses `NetworkTopologyStrategy` with per-DC replication factors:

~~~sql
CREATE KEYSPACE IF NOT EXISTS regional_dr_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_a': 3,
    'dc_b': 3
}
AND durable_writes = true;
~~~

Verify on the test cluster:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'regional_dr_lab';

SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` only describes **the responding node**, not the entire cluster. Run `nodetool status` on appropriate nodes to verify DC names and `UN` (*Up/Normal*) states; `dc_a`/`dc_b` must match snitch settings. `IF NOT EXISTS` does not alter an existing keyspace, so never assume RF=3+3 blindly after running the creation script.

### Comparing Consistency Levels Under RF 3+3

| CL | Write: Where Responses Come From | Read: Where Responses Come From | Impact on RPO/RTO |
| --- | --- | --- | --- |
| `LOCAL_ONE` | At least 1 replica in coordinator's DC | At least 1 local replica | Fast, minimal guarantees on copies and freshness |
| `LOCAL_QUORUM` | At least 2/3 local replicas | Local 2/3 quorum | Does not require remote DC confirmation before returning ACK |
| `QUORUM` | 4/6 replicas regardless of split across DCs | 4/6 replicas | Contacts more replicas, but does not guarantee quorum in **each** DC |
| `EACH_QUORUM` | 2/3 in **each DC**, at least 4 ACKs total | Not used for regular `SELECT` | Enables writes requiring quorum in both DCs, at the cost of WAN dependency |
| `ALL` | 6/6 replicas | 6/6 replicas | Strong threshold, poor availability on any node/DC failure |

**Important:** `LOCAL_QUORUM` in `dc_a` is **not** a quorum in `dc_b`. If A1 and A2 confirm a write before B1/B2/B3 receive the mutation, the client in A still gets success. Therefore, if **all of `dc_a` fails immediately after the ACK**, reads in `dc_b` are not guaranteed to see the newest record from local CL alone.

Stating "RF=3+3 means we never lose data if one DC fails" is incomplete: you must factor in chosen CL, replication state at failure time, commit-log/disk durability, and whether data exists in an independent source.

To target a tighter RPO, evaluate `EACH_QUORUM` writes or durable confirmation in the target DC **before returning success**. The trade-off is WAN latency and reduced write availability when a DC fails; even then, backups, commit-log checks, and realistic failure modeling remain essential.

## 3. RTO, RPO, and Latency: Define Before Measuring

### 3.1. RTO: How Long Until Service Is Restored?

**Recovery Time Objective (RTO)** is the maximum acceptable outage duration. In a drill, define exact start and end timestamps:

- `T_impact`: when the fault **begins impacting users** or external health probes fail valid requests.
- `T_detect`: when monitoring detects the incident.
- `T_decide`: when operators/automation decide to fail over.
- `T_route`: when routing changes take effect at applications/coordinators in B.
- `T_recovered`: when real traffic or synthetic checks in B meet **read/write success and latency** criteria over a defined observation window.

~~~text
RTO_observed = T_recovered - T_impact
              = detection time + decision time
                + routing shift + stabilization/verification
~~~

Never take `T_route - T_detect` and report it as RTO if applications are still erroring or breaching latency SLAs when routes switch. Conversely, a **non-disruptive routing-only** drill may report "no downtime observed within measurement resolution," without implying real disasters have zero RTO.

### 3.2. RPO: Data Potentially Absent in the Target DC

**Recovery Point Objective (RPO)** is the **maximum acceptable data loss**, commonly expressed as a time window prior to the outage. Distinguish **target RPO** from **observed data gap**:

1. Collect all operations **actually ACKed** in DC A before `T_impact` from an independent log/manifest.
2. For each key, read in DC B **after failover** at the designated CL.
3. Classify each record as **FOUND_MATCH**, **MISSING_AT_CL**, **MISMATCH**, or **READ_ERROR**.
4. Use only **successful** reads to identify temporarily absent data; read timeouts or `Unavailable` are **not proof of data loss**.
5. When reporting time-based RPO, identify the **latest continuously recovered ACK timestamp** in an ordered event stream; report both the missing ACK window and any **non-contiguous gaps**.

~~~text
Example (ACK timestamps recorded by an independent log, illustrative only):
10:00:00  event A  ACKed in dc_a  -> FOUND in dc_b
10:00:20  event B  ACKed in dc_a  -> FOUND in dc_b
10:00:40  event C  ACKed in dc_a  -> MISSING in dc_b
10:00:50  event D  ACKed in dc_a  -> MISSING in dc_b
10:01:00  T_impact

At this check, B lacks C and D even though A/B both use RF=3.
If the ACK stream is ordered with no gaps before B, the last
continuously observed point is 10:00:20; the gap until impact
is 40 seconds. Also report 2 missing events.
~~~

**Do not equate "MISSING at check time" with "permanently lost."** Once WAN/DC A recovers, hints or repair can restore the rows. If DC A never returns and no external source holds those records, it becomes true data loss. RPO reports should state exact check times, methodology, key sets, and sync status; for scattered missing events, a single seconds figure fails to capture the full impact.

Alongside seconds of lag, always report **the count of missing ACKed operations**, grouped by tenant/partition and business impact. One missing ACKed payment event can matter far more than many reproducible telemetry events.

### 3.3. Latency and Error Rates

RTO/RPO do not replace **service-quality observability**:

| Metric Group | Measure Before, During, and After Failover |
| --- | --- |
| API / Java | Read and write p50/p95/p99 latency; throughput; timeouts/unavailables; connection pools |
| Cassandra | Actual CL used; `UN` node count per DC; read/write timeouts, unavailables, per-node/DC latency |
| Synchronization | Pending/delivered/failed hints, repair/streaming status, event-source backlog |
| Data | Expected ACKed IDs, found/missing/mismatch/read errors, affected tenants/buckets |
| Infrastructure | CPU, RAM, disk I/O, free disk, WAN network, compaction/streaming load |
| User experience | Request success rate, read/write capability in standby region, SLO alerts |

Do not compare pre/post p99 if load, partition distribution, request mix, or concurrency shifted drastically. Measure request durations with a **monotonic clock** inside the same process; synchronize NTP/clocks when comparing timestamps across hosts/DCs.

## 4. Choosing Drill Intensity and Stop Criteria

You do not need to take down an entire DC on your very first drill. Escalate progressively:

| Drill Level | Impact | Objective |
| --- | --- | --- |
| **Read-only rehearsal** | Validation reads in B while A serves primary traffic | Measure remote data completeness and B latency without disruption |
| **Routing-only failover** | Shift synthetic/canary traffic to B without faulting nodes | Verify drivers, DNS/gateway, auth, secrets, and local CL in B |
| **Controlled traffic switch** | Drain/stop new writes in A, shift partial/full writes to B | Test fencing, cutover duration, client retries, backpressure |
| **Lab DC outage drill** | Isolate or stop all of DC A after preparation | Measure RTO/RPO when A truly stops responding |
| **Failback rehearsal** | Recover A and return traffic after reconciliation | Validate repair, data sources, and write re-enablement gates |

Advance to stronger tests only after the prior level passes. If **missing ACKed data exceeds thresholds**, p99 breaches SLAs, disk/CPU/streaming threatens cluster stability, or fencing A is uncertain, **halt escalation** and preserve evidence for analysis.

## 5. Fencing: Preventing Unintended Dual-Region Writes

Harder than switching routes is preventing **both sides from accepting conflicting business writes**. During a WAN partition, A may still serve some clients while B is activated for others. Cassandra uses timestamps and reconciliation for regular writes; it does not resolve business races like "deduct inventory twice" or "confirm an order in two regions."

A controlled failover procedure should include:

1. **Clear write ownership:** define which region may accept mutations in each phase.
2. **Fencing or leases in a trusted coordination layer:** ensure the old writer cannot apply valid mutations before the new writer starts, or use operation IDs/idempotency with conflict handling.
3. **Drain in-flight requests:** stop accepting new writes in A and await/log whether in-flight requests ACKed.
4. **Attach stable operation IDs:** a retry after timeout must never turn into a brand-new transaction.
5. **Switch read/write routing and local DC:** Application B must actually use coordinators in `dc_b`.
6. **Verify data and service health:** ramp traffic only after checking RPO/RTO/latency criteria.

> Fencing cannot be guaranteed solely by a flag stored inside the very Cassandra cluster being partitioned. For workflows demanding strict single-owner/exactly-once semantics, use a control plane/lease with fitting consistency or a verified mechanism blocking the old writer; if reliable fencing is impossible, **do not accept conflicting writes in both regions**.

~~~mermaid
sequenceDiagram
    participant O as Orchestration / Ops
    participant A as API + coordinator dc_a
    participant B as API + coordinator dc_b
    participant M as Independent Manifest
    O->>A: Stop new writes / fence writer A
    A-->>O: Report in-flight, ACK/UNKNOWN
    O->>M: Lock manifest and T_impact/cutover mark
    O->>B: Check B health, CL, and required data
    O->>B: Enable writer B and shift traffic
    B-->>O: Synthetic checks pass, latency within threshold
    O->>M: Reconcile A ACKs against B reads
    O-->>O: Report RTO, missing data, and go/no-go decision
~~~

## 6. Preparing a Two-DC Lab and Verification Dataset

### 6.1. Check Topology and Configuration

The sample lab uses `dc_a` with A1/A2/A3 and `dc_b` with B1/B2/B3. Each DC holds three replicas for `regional_dr_lab`. Before testing:

~~~bash
# Run on appropriate lab nodes.
nodetool status
nodetool describecluster
nodetool netstats
nodetool compactionstats
~~~

Confirm required nodes are `UN`, schemas agree, and no unrelated heavy repair/streaming is running. Open two `cqlsh` sessions connected separately to a `dc_a` coordinator and a `dc_b` coordinator. Run `SELECT data_center FROM system.local` in each session to confirm its local DC.

### 6.2. Create a Table with an Explicit Partition Key

~~~sql
CREATE TABLE IF NOT EXISTS regional_dr_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    origin_dc text,
    emitted_at timestamp,
    payload text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` is the **partition key** for querying a single drill run's events; `event_id` is the clustering key providing stable identification. The lab places a few dozen markers in one partition. **Never** dump all production events across all tenants into a single `run_id` partition: in production, bucket by tenant/time and design partition keys to fit load without unbounded partitions.

`emitted_at` is an application timestamp aiding reconciliation, **not commit/ACK proof emitted by Cassandra**. Client ACK logs must be stored externally; cross-DC timestamp comparisons require clock synchronization.

### 6.3. External Manifest Outside Cassandra

Prepare an expected-events table before inducing any outage, stored in logs or a reliable source **independent of reading the failed DC A**:

| run_id | event_id | marker | ACKed in A? | ACK Time | Read Result in B |
| --- | --- | --- | --- | --- | --- |
| `dr-20261121-01` | `11111111-1111-4111-8111-111111111111` | `base-A` | Untested | — | — |
| `dr-20261121-01` | `22222222-2222-4222-8222-222222222222` | `recent-B` | Untested | — | — |
| `dr-20261121-01` | `33333333-3333-4333-8333-333333333333` | `recent-C` | Untested | — | — |

During real runs, replace "Untested" with the **actual observed ACK, UNKNOWN, or ERROR**, never assuming all succeeded. If a separate business event log (outbox/event log) exists, record source IDs and states as well to measure *completeness*, not just requests that reached Cassandra.

## 7. CQL Scenario: Write in A, Read in B, and Observe Before Failover

### 7.1. Write Through a Coordinator in `dc_a`

In the verified `dc_a` `cqlsh` session:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    11111111-1111-4111-8111-111111111111,
    'base-A', 'dc_a', '2026-11-21T09:00:00Z', 'first-event'
);

INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    22222222-2222-4222-8222-222222222222,
    'recent-B', 'dc_a', '2026-11-21T09:01:00Z', 'second-event'
);

INSERT INTO regional_dr_lab.events_by_run
    (run_id, event_id, marker, origin_dc, emitted_at, payload)
VALUES (
    'dr-20261121-01',
    33333333-3333-4333-8333-333333333333,
    'recent-C', 'dc_a', '2026-11-21T09:01:10Z', 'third-event'
);
~~~

`CONSISTENCY` is a **cqlsh command**, not a CQL query. Record an ACK in the manifest only if each `INSERT` returned success to the client. With RF=3 in `dc_a`, `LOCAL_QUORUM` requires two local replica ACKs; B1/B2/B3 are not required to have received the data yet.

In this lab, `emitted_at` values are fixed for readability, whereas **actual ACK timestamps** must be recorded by the client at execution time. Never treat these three sample timestamps as measured RPO data.

### 7.2. Reconcile Reads Through a Coordinator in `dc_b`

In the `cqlsh` session connected to a `dc_b` node:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, origin_dc, emitted_at
FROM regional_dr_lab.events_by_run
WHERE run_id = 'dr-20261121-01';
~~~

If all three markers appear in B, that is an **observation that data reached B at the chosen CL**, not proof that A's writes waited for B's ACKs. If a marker is missing, record **MISSING_AT_DC_B_AT_TIME_T** and investigate: replication lag, node fault, timestamp skew, conflicting delete, wrong run ID, or connectivity error.

Checking a single key specifically avoids inferring from row counts:

~~~sql
SELECT marker, origin_dc
FROM regional_dr_lab.events_by_run
WHERE run_id = 'dr-20261121-01'
  AND event_id = 33333333-3333-4333-8333-333333333333;
~~~

Reading at `LOCAL_ONE` may be cheaper, yet can reflect one lagging local replica; when measuring convergence, record CL explicitly and choose `LOCAL_QUORUM` or suitable admin/repair checks. **Connecting directly to B1 does not force Cassandra to read only B1's local copy**: B1 still acts as coordinator and contacts other replicas.

## 8. Phased Regional Failover Drill

### Phase 0 — Baseline

Measure over a window representative of the application's request mix:

- Read/write success rates and p50/p95/p99 latency in DC A.
- Count of ACKs and `UNKNOWN_WRITE`s in the manifest.
- Health of both DCs, hints, read/write timeouts, free disk, compaction backlog.
- Set of ACKed markers and their read status in B.
- Readiness of dependencies: API gateway, certificates, secrets, DNS, service discovery, queues, caches.

State concrete sample targets: **RTO ≤ 5 minutes, target RPO ≤ 30 seconds, post-failover p95 ≤ 1.5x baseline**. These thresholds are **lab examples only**, not universal recommendations; ops teams must define their own SLAs and data requirements.

### Phase 1 — Fencing and Locking the Observation Point

In a controlled lab, stop new writers in A, record in-flight requests, lock the manifest, and note `T_impact`/`T_detect` plus the authoritative ID list for reconciliation. If simulating a **sudden DC loss**, external fencing of A may be impossible; design anti-split-brain routing/write ownership **before** testing that case.

If a write times out during cutover, mark it **UNKNOWN_WRITE**. Never assume it was ACKed or definitely dropped; retrying via B requires operation IDs and idempotency logic.

### Phase 2 — Switching Coordinator/App to B

Update gateway/orchestrator routing and **Service B's** Java Driver config to use `dc_b` as local datacenter. Never just change hostnames while leaving the driver's local DC as `dc_a`. Verify new requests hit coordinators in B while blocking stray write traffic to A.

Immediately after cutover, run synthetic checks:

1. Read an existing baseline marker.
2. Write **a new event ID** in B at `LOCAL_QUORUM` and wait for ACK.
3. Read that event back in B at `LOCAL_QUORUM`.
4. Verify p95/p99 and error rates over the defined window.

Mark `T_recovered` only once the application serves both **reads and writes** within defined criteria—not merely when DNS updates.

### Phase 3 — RPO Reconciliation

Using a local session in B, read every `event_id` ACKed in A prior to impact, plus new events ACKed in B. Report clearly:

~~~text
expected_acked_count       = events confirmed in manifest
found_match_count          = events returning matching marker in dc_b
missing_at_selected_cl     = events where read succeeded with no row
mismatch_count             = events returning wrong marker
read_error_count           = checks failing with error/timeout
unknown_write_count        = writes with indeterminate initial outcome
checked_at                 = reconciliation time / window
consistency                = LOCAL_QUORUM on dc_b coordinator
~~~

`FOUND_MATCH + MISSING + MISMATCH` covers only keys whose reads **succeeded**; never add `READ_ERROR` into `MISSING`. For missing markers, **preserve both IDs and ACK timestamps** to estimate RPO and impacted data scope—never report a table-wide `COUNT(*)`.

### Phase 4 — True DC A Down Scenario (Lab Only)

After rehearsing routing/fencing, you can test a complete failure domain by rendering **DC A's lab nodes** unable to serve requests under operator control. Never corrupt disks/data intentionally; simulate a network cut or stop lab services/containers cleanly.

Observe:

- Does B still meet `LOCAL_QUORUM` for B's RF3?
- Do new writes in B ACK while A is unresponsive?
- Are any requests misrouted to A due to stale pools or routes?
- Are any events ACKed in A still absent in B?
- If A were unrecoverable, do trusted logs/backups exist to backfill?

With `LOCAL_QUORUM` in B, **ACKs from A are not needed** for B to reply; however, if old data existed only on A, B cannot conjure it up. Never force `QUORUM` or `ALL` to "verify" while A is down: those levels increase errors/unavailability without fixing missing data.

## 9. Java Driver 4.x: Separating Sessions per DC and Measuring Results

Java apps use `CqlSession` with an **explicit local datacenter**. The example below uses Java 17 and Apache Cassandra Java Driver 4.x. IPs are private lab examples; real configs need TLS, authentication, redundant contact points, load balancing, and tuned timeouts.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class MultiDcFailoverProbe {
    public record Event(String runId, UUID eventId,
                        String marker, String originDc, Instant emittedAt) {}
    public enum WriteState { ACKNOWLEDGED, UNKNOWN_WRITE }
    public enum ReadState { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }
    public record ReadSample(ReadState state, long latencyMillis) {}

    private final CqlSession session;
    private final PreparedStatement put;
    private final PreparedStatement get;

    public static CqlSession connect(String ip, String localDc) {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress(ip, 9042))
            .withLocalDatacenter(localDc)
            .withKeyspace("regional_dr_lab")
            .build();
    }

    public MultiDcFailoverProbe(CqlSession session) {
        this.session = session;
        this.put = session.prepare(
            "INSERT INTO regional_dr_lab.events_by_run " +
            "(run_id, event_id, marker, origin_dc, emitted_at, payload) " +
            "VALUES (?, ?, ?, ?, ?, ?)");
        this.get = session.prepare(
            "SELECT marker FROM regional_dr_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteState writeAtLocalQuorum(Event event, String payload) {
        BoundStatement statement = put.bind(
                event.runId(), event.eventId(), event.marker(),
                event.originDc(), event.emittedAt(), payload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false);
        try {
            session.execute(statement);
            System.out.printf("ACK run=%s id=%s at=%s%n",
                event.runId(), event.eventId(), Instant.now());
            return WriteState.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("UNKNOWN_WRITE run=%s id=%s error=%s%n",
                event.runId(), event.eventId(),
                error.getClass().getSimpleName());
            return WriteState.UNKNOWN_WRITE;
        }
    }

    public ReadSample verifyAtLocalQuorum(Event expected) {
        long started = System.nanoTime();
        try {
            Row row = session.execute(get.bind(
                    expected.runId(), expected.eventId())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            ReadState state = row == null
                ? ReadState.MISSING
                : expected.marker().equals(row.getString("marker"))
                    ? ReadState.FOUND_MATCH : ReadState.MISMATCH;

            return new ReadSample(state, elapsedMillis(started));
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR event=%s error=%s%n",
                expected.eventId(), error.getClass().getSimpleName());
            return new ReadSample(ReadState.READ_ERROR, elapsedMillis(started));
        }
    }

    private static long elapsedMillis(long started) {
        return TimeUnit.NANOSECONDS.toMillis(
            System.nanoTime() - started);
    }
}
~~~

Illustrating two sessions targeting two local DCs:

~~~java
try (CqlSession a = MultiDcFailoverProbe.connect("10.10.0.11", "dc_a");
     CqlSession b = MultiDcFailoverProbe.connect("10.20.0.11", "dc_b")) {

    MultiDcFailoverProbe writerA = new MultiDcFailoverProbe(a);
    MultiDcFailoverProbe readerB = new MultiDcFailoverProbe(b);

    var event = new MultiDcFailoverProbe.Event(
        "dr-java-01",
        UUID.fromString("44444444-4444-4444-8444-444444444444"),
        "check-001",
        "dc_a",
        Instant.now()
    );

    var ack = writerA.writeAtLocalQuorum(event, "lab-payload");
    var observation = readerB.verifyAtLocalQuorum(event);
    System.out.printf("write=%s remoteRead=%s latencyMs=%d%n",
        ack, observation.state(), observation.latencyMillis());
}
~~~

**Notes on this code:**

- `withLocalDatacenter("dc_a")` or `"dc_b"` governs load balancing and local-DC awareness; connecting to a random IP in DC A while expecting `LOCAL_QUORUM` to compute in B is wrong.
- `CqlSession` must be **reused** in real services. Never open/close sessions per request; the snippet merely demonstrates two DC configs in one short program.
- `writeAtLocalQuorum` returns `ACKNOWLEDGED` only on success. `UNKNOWN_WRITE` must be logged to the manifest and handled by idempotency policy rather than assuming it was not written.
- `verifyAtLocalQuorum` returns `MISSING` when the query succeeded with no row; on timeouts it returns `READ_ERROR`, **never marking it as lost data**.
- `latencyMillis` measures duration via a monotonic clock, yet **one sample is not p95/p99**; collect many samples under consistent load and across timestamps.
- `origin_dc` is only client-supplied metadata, not proof of which DC coordinated the call. Verify topology/driver metrics and routing directly.
- The manifest must be stored in an **independent, durable system**; console logging here is not a production audit solution.

## 10. Sample Report on RTO, RPO, and Blast Radius

Suppose lab targets are RTO ≤ 5 minutes, RPO ≤ 30 seconds, and post-failover p95 latency ≤ 1.5x baseline. **All numbers below are hypothetical calculations, not live Cassandra benchmark results.**

| Hypothetical Observation | Value |
| --- | --- |
| `T_impact` | 10:00:00 |
| `T_detect` | 10:00:20 |
| `T_route` | 10:01:10 |
| `T_recovered` | 10:02:00 |
| **Observed RTO** | **120 seconds** |
| Pre-fault ACKed writes in manifest | 1,000 |
| Reads in B: found match | 995 |
| Reads in B: missing | 3 |
| Reads in B: mismatch | 0 |
| Reads in B: read error | 2 |
| Writes without ACK before fault | 4, **not merged** into 1,000 |
| Read p95 before / after | 18 ms / 31 ms |

Interpretation:

- **120-second RTO**: meets the 5-minute target assuming `T_impact` and `T_recovered` definitions were agreed upon.
- **p95 latency rising from 18 to 31 ms**: ~1.72x increase, **failing** the 1.5x drill threshold; investigate load, cold caches, and B's capacity.
- **3 MISSING**: previously ACKed rows not visible in B at the tested CL/time; check IDs/ACK timestamps, replication lag, repair, and recovery sources. Do not prematurely mark "permanently lost."
- **2 READ_ERROR**: inconclusive; run controlled verification retries after stabilization.
- **4 UNKNOWN_WRITE**: neither counted as ACKed nor lost; look up operation IDs, event sources, and execute controlled retries.
- **Time-based RPO**: cannot be computed from aggregate counts alone without the **ACK timestamps and sequence** of the three `MISSING` events. Open the manifest to pinpoint the missing interval and any gaps.

A complete report adds: which DC failed, affected services/tenants, recovery timestamps, missing keys, per-flow measured RPO if applicable, backfill sources, unverified items, and runbook improvements.

## 11. Failback and Post-Drill Data Recovery

**Failback** (returning traffic from B to A) is a new operation, not simply flipping DNS back once A reports `UN`. While A was down, B likely accepted many new writes that A does not yet hold.

Safe sequence:

1. **Confirm A genuinely recovered:** healthy nodes/replicas, clean disks and commit logs, stable WAN link—do not just glance at one `UN` node.
2. **Reconcile bidirectionally:** are events ACKed in A before failover present in B? Are events ACKed while B served present in A?
3. **Run repair/hints/streaming:** monitor scope, errors, latency, and resources; never treat one `SELECT` or `nodetool status` as proof that every replica converged.
4. **Check tombstones/TTLs:** if a DC was offline too long—especially past `gc_grace_seconds` where tombstones may have purged—**never let stale replicas rejoin casually** to avoid zombie data. Evaluate rebuild/replace per version runbook.
5. **Backfill missing data from trusted sources:** only when events exist in business sources yet are absent from Cassandra; use stable IDs and safeguards against overwriting newer data.
6. **Fence writer B and transfer ownership back:** stop new writes in B per procedure, drain in-flight work, then shift requests to A.
7. **Synthetic checks and monitoring:** write ACK and read marker checks in A, p95/p99, error rates, lag, and system health post-cutover.

`nodetool repair` consumes CPU/disk/network and must run over the right token ranges for your version/topology. **Repair cannot recreate data absent from every surviving trusted replica**, nor fix a missing external event log. Never fire off massive full repairs during peak traffic just to check a box.

### Common Errors to Avoid

| Misconception | Correct Understanding |
| --- | --- |
| "RF=3 per DC means failover always gives RPO=0." | `LOCAL_QUORUM` in A does not wait for B ACKs; measure actual data in B. |
| "Just point the driver IP to B." | Must align **local DC, coordinator routing, app/gateway, auth**, and read/write paths. |
| "DNS switched means RTO is complete." | RTO ends only when the service meets defined recovery criteria. |
| "A read timeout in B proves the event is lost." | That is **READ_ERROR**, not `MISSING`. |
| "Equal `COUNT(*)` in both DCs means zero missing data." | Counts hide missing/mismatched IDs, and full-table scans waste resources. |
| "Seeing the marker in B means A's write waited for B's ACK." | Remote replicas can receive data before or after local ACK; ACK rules still only counted A. |
| "A returned to `UN`, so fail back immediately." | Reconcile B→A data, repair/hints/TTLs, and fence writers first. |
| "Global `QUORUM` over RF6 guarantees quorum in both DCs." | `QUORUM` can reach 4/6 without 2 ACKs per DC; `EACH_QUORUM` enforces different rules. |

## 12. Practice Exercises

**Exercise 1 — Calculating ACK scope.** A cluster has `dc_a:3` and `dc_b:3`. A executes `INSERT LOCAL_QUORUM` and gets ACKs from A1/A2. What can you conclude about B1/B2/B3? If writes must get two ACKs in each DC, which CL should you evaluate and what is the WAN trade-off?

**Exercise 2 — Failover runbook.** Sketch a timeline with `T_impact`, `T_detect`, `T_decide`, `T_route`, and `T_recovered` for a hypothetical outage. List how you verify writer A is fenced before B accepts writes and compute observed RTO.

**Exercise 3 — Manifest analysis.** A stream had 200 ACKed events in A; B read 197 with matching markers, one missing, and two read errors. Compute the **verified accurate** count and explain why you cannot claim three permanently lost events or derive time-based RPO from those numbers alone.

**Exercise 4 — Testing routing.** Use two Java `CqlSession` instances with `withLocalDatacenter("dc_a")` and `"dc_b"`. Write an event in A, read it in B, and log latency plus `FOUND_MATCH/MISSING/READ_ERROR`. Why doesn't a successful remote read change the definition of the local write ACK?

**Exercise 5 — WAN partition.** Suppose both A and B retain three healthy local replicas while WAN communication is severed. Can `LOCAL_QUORUM` in B continue accepting new writes? What happens if both regions concurrently write conflicting values to the same primary key? Propose fencing and conflict-handling mechanisms.

**Exercise 6 — Measuring p95/p99.** Baseline read p95 is 20 ms; after failover, p95 is 48 ms under the same request mix, while p99 spikes due to compaction and cold caches. Define criteria for declaring recovery: merely "readable" or meeting latency, throughput, and error-rate SLOs?

**Exercise 7 — Safe failback.** DC A returns after a prolonged outage, having likely missed many `DELETE`s while some tombstones passed grace. Why must writer A not be enabled immediately? Outline the verification, rebuild/repair, and data reconciliation plan before failback.

## Key Takeaway

**A regional failover drill tests availability, routing, and data completeness together.** With `LOCAL_ONE` or `LOCAL_QUORUM`, ACKs are counted in the coordinator's DC; a write ACKed in DC A is not guaranteed to appear instantaneously in DC B. Therefore, define **RTO/RPO** targets, store an external manifest of ACKed events, measure target-DC data availability by specific keys and CL, separate missing rows from read errors, monitor p95/p99, and enforce **fencing + reconciliation + repair/backfill** before allowing bidirectional writes or failback.
