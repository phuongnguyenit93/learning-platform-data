# LOCAL_ONE, LOCAL_QUORUM, and the Scope of Counted Responses

## Goal and Context

When Apache Cassandra is deployed across **multiple datacenters (DCs)**, data can have replicas in multiple geographic regions. To balance latency and fault tolerance, applications often select `LOCAL_ONE` or `LOCAL_QUORUM` as the **consistency level (CL)** for individual CQL statements. The keyword **LOCAL** has a very specific meaning: **the required response count is calculated within the coordinator's local datacenter**, not across all replicas in every DC.

This lesson belongs to the **Multi-Datacenter Deployment** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects distributed architecture, the wide-column model, partition keys, query-driven table design, replication, read/write consistency levels, repair/compaction, error handling, and Java Driver connectivity.

Upon completing this lesson, you will be able to:

1. Calculate the exact number of replicas required to respond for `LOCAL_ONE` and `LOCAL_QUORUM` when each DC has a different RF.
2. Explain the difference between a **write ACK** and the **responses needed to complete a read**.
3. Distinguish `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM`, and `ALL` in a multi-DC cluster.
4. Explain why a write acknowledged in DC A **does not automatically guarantee** that an immediate read in DC B sees that write.
5. Route a Java client to the intended datacenter, configure consistency per business requirements, and verify errors/latency.
6. Design a lab using CQL, fixed markers, and DC failure scenarios with clear observability criteria.

## 1. Where Is "Local" Determined?

Before discussing consistency, separate three concepts:

- **Node's datacenter**: determined by Cassandra via the snitch/topology; for example, `dc_hn` (Hanoi) and `dc_sg` (Saigon).
- **Coordinator**: the node receiving the CQL request from the client and coordinating reads/writes across replicas.
- **Operation's local DC**: the DC **of the coordinator** serving the request—not necessarily where the end user's device or Java application server is deployed.

Suppose an application runs in Singapore but connects to a coordinator in `dc_hn`. For that request, `LOCAL_QUORUM` is evaluated in **`dc_hn`**. It is **not** calculated from the JVM's geographic location. To make operations use `dc_sg` as the local DC, the application must route to coordinators in `dc_sg` and configure the driver accordingly.

~~~mermaid
flowchart LR
    APP1["Java client using dc_hn"] --> C1["Coordinator in dc_hn"]
    C1 --> H1["Replica H1"]
    C1 --> H2["Replica H2"]
    C1 --> H3["Replica H3"]
    C1 -. "Replication sent to remote DC" .-> S1["Replica S1"]
    C1 -.-> S2["Replica S2"]
    C1 -.-> S3["Replica S3"]
    APP2["Java client using dc_sg"] --> C2["Coordinator in dc_sg"]
    C2 --> S1
    C2 --> S2
    C2 --> S3
~~~

In Cassandra, replicas located in another DC are still members of the **same cluster** and can receive mutations on writes. However, with `LOCAL_ONE` or `LOCAL_QUORUM`, **ACKs from remote replicas do not count toward the local DC's success threshold**. This does not mean Cassandra skips replicating to the other DC.

> Crucial distinction: **the scope of counted responses** is not **the only list of nodes that may be contacted**. The write path can send mutations to remote replicas, and the read path can perform extra work depending on version/strategy; the completion threshold for `LOCAL_*` is still evaluated within the local DC.

## 2. Per-DC Replication Factor

Use `NetworkTopologyStrategy` to specify the number of copies in each datacenter:

~~~sql
CREATE KEYSPACE IF NOT EXISTS mdc_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hn': 3,
    'dc_sg': 3
}
AND durable_writes = true;
~~~

This example assumes **at least three nodes in each DC** with proper rack/placement configuration. If your actual cluster uses `datacenter1`, `dc1`, or another name, you must use the exact **DC name returned by `nodetool status` and topology**. Never alter production keyspaces just to run a lab exercise.

Inspect the configuration:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'mdc_lab';
~~~

In the RF=3+3 example, each partition has **6 total replicas**: three in `dc_hn` and three in `dc_sg`. Replicas of the same partition can reside on different nodes according to tokens, snitch, and racks. All six replicas are not necessarily identical instantaneously when failures occur or replication is catching up.

`IF NOT EXISTS` only avoids duplicate-creation errors; **it does not modify an existing keyspace**. If re-running a lab, verify `replication` and `durable_writes` before interpreting ACK counts.

### Asymmetric RF Example

Suppose another keyspace has `dc_hn: 3` and `dc_sg: 2`. There is no "single cluster-wide `LOCAL_QUORUM`"; the quorum threshold is calculated **independently from the local DC's RF**:

\[
\operatorname{localQuorum}(RF_{DC})=\left\lfloor\frac{RF_{DC}}{2}\right\rfloor+1
\]

| RF in Coordinator's DC | `LOCAL_ONE` | `LOCAL_QUORUM` |
| ---: | ---: | ---: |
| 1 | 1 | 1 |
| 2 | 1 | 2 |
| 3 | 1 | 2 |
| 4 | 1 | 3 |
| 5 | 1 | 3 |

With RF=1, `LOCAL_QUORUM` only needs one replica, **providing no extra fault tolerance**. With RF=2, quorum is two, so losing one replica can prevent `LOCAL_QUORUM` from being satisfied. RF=3 with quorum of two is usually the clearest starting example.

## 3. LOCAL_ONE: Only One Local Response Required

### On Write

With a coordinator in `dc_hn` and keyspace `mdc_lab` at RF=3+3, `LOCAL_ONE` requires at least **one replica in `dc_hn`** to return a successful write acknowledgment.

~~~text
Client -> dc_hn coordinator
           |-- H1: ACK   <- enough to return LOCAL_ONE success
           |-- H2: may receive, not yet ACKed
           |-- H3: may receive, not yet ACKed
           |-- S1/S2/S3: remote replication, ACKs do not count toward LOCAL_ONE
~~~

The coordinator still forwards the mutation to the other replicas. `LOCAL_ONE` only specifies **the response threshold the client must receive**; it does not mean only one copy is written, does not mean all replicas are updated, and does not guarantee data has been fsynced on every storage device.

### On Read

`LOCAL_ONE` requires a sufficient response from **one replica in the local DC** to complete the query. If the selected replica is lagging behind, the result can be older than a mutation already stored on another replica. This is especially noticeable right after a write in another DC, when a node is down, or while synchronization sessions are incomplete.

**Trade-off:** low latency and minimal response requirements, allowing continued responses when the local DC has only one eligible replica left. In return, the likelihood of immediately reading the latest version is weaker than `LOCAL_QUORUM` when data has not yet converged.

## 4. LOCAL_QUORUM: Majority of Replicas in the Local DC

With `RF_dc_hn=3`, `LOCAL_QUORUM` requires **2 replicas in `dc_hn`** to acknowledge. With `RF_dc_sg=3`, the same requirement applies in `dc_sg` when the coordinator is in `dc_sg`.

### On Write

~~~mermaid
sequenceDiagram
    participant A as Java client
    participant C as Coordinator dc_hn
    participant H1 as H1 in dc_hn
    participant H2 as H2 in dc_hn
    participant H3 as H3 in dc_hn
    participant S as dc_sg replicas
    A->>C: INSERT (LOCAL_QUORUM)
    par Distribute mutation
        C->>H1: Mutation
        C->>H2: Mutation
        C->>H3: Mutation
        C->>S: Mutation to remote DC
    end
    H1-->>C: ACK
    H2-->>C: ACK
    C-->>A: Success: 2/3 local ACKs met
    Note over S: May receive after or before local ACK
~~~

Only two **local** ACKs are required. An ACK from `dc_sg` **cannot substitute** for a missing ACK in `dc_hn`. This allows requests to complete quickly within one DC even when the WAN link to another DC is slow, provided the local DC still has enough responding replicas.

### On Read

`LOCAL_QUORUM` requires reading from a **local replica quorum** according to Cassandra's read and reconciliation protocol. The coordinator may fetch data/digests, resolve discrepancies, and return the valid row per timestamp/tombstone rules. Do not describe this as "reading exactly two physical copies and comparing bytes."

Some versions/configurations may send extra requests or perform read repair; **the threshold required to respond remains the local quorum**. A successful read at `LOCAL_QUORUM` also does not prove that the third copy in the DC is synchronized.

### When Does W + R > RF Help?

Within a single DC with RF=3:

\[
W_{\text{local}}=2,\qquad R_{\text{local}}=2,\qquad W+R=4>3
\]

The set of two replicas that ACKed the write and the set of two replicas answering the read **must intersect** on at least one replica. For a record with no concurrent updates/deletes, no special timestamp skew anomalies, and successful responses, this reasoning explains why **writing at `LOCAL_QUORUM` and reading at `LOCAL_QUORUM` within the same DC** provides stronger guarantees than reading at `LOCAL_ONE`.

However, **do not extrapolate this into arbitrary linearizable transactions**: Cassandra reconciles by timestamp and is still subject to concurrent writes, tombstones, timeouts, and per-operation consistency semantics. When you must verify "update only if version has not changed," you need **LWT/`IF`** and the corresponding serial consistency—do not substitute `W+R>RF` arithmetic.

## 5. Two DCs: Local Quorum in DC A Is Not Quorum in DC B

This is the most important boundary of the word `LOCAL`.

Suppose both Hanoi DC and Saigon DC have RF=3. Application A sends an `INSERT` in `dc_hn` at `LOCAL_QUORUM` and gets ACKs from H1 and H2. Immediately afterward, Application B reads in `dc_sg` at `LOCAL_QUORUM`:

~~~text
dc_hn: H1 = new (ACK), H2 = new (ACK), H3 = maybe
dc_sg: S1 = old?, S2 = old?, S3 = old?

WRITE LOCAL_QUORUM in dc_hn: SUCCEEDED
READ  LOCAL_QUORUM in dc_sg: NOT GUARANTEED to see the new value
~~~

In practice, remote replicas often update very quickly and the read in `dc_sg` **may still see the new data**. However, the ACK in `dc_hn` **does not require** a `dc_sg` quorum to reply, so local CL alone gives no guarantee that the data reached enough remote replicas by that exact moment.

~~~mermaid
sequenceDiagram
    participant A as Client A in dc_hn
    participant H as Coordinator dc_hn
    participant H2 as Quorum dc_hn
    participant S as Replica dc_sg
    participant B as Client B in dc_sg
    A->>H: WRITE (LOCAL_QUORUM)
    H->>H2: Write to local replicas
    H-->>S: Remote mutation (unconfirmed in local condition)
    H2-->>H: 2 local ACKs
    H-->>A: Success
    B->>S: READ (LOCAL_QUORUM in dc_sg)
    Note over S: Enough replicas may not yet have the new write
    S-->>B: Result depends on dc_sg sync state
~~~

**Common misconception:** "Writing at `LOCAL_QUORUM` anywhere means reading at `LOCAL_QUORUM` everywhere immediately sees the latest value." The `W+R>RF` argument does not apply when **the write quorum and read quorum belong to two different replica sets in two different DCs**; they are not guaranteed to intersect.

If an application needs immediate *read-your-writes* behavior for a user, you can route subsequent reads through **the same DC** where the write was ACKed, or design cross-DC acknowledgment/synchronization matching business requirements. Never claim that picking `QUORUM` in all cases gives absolute "strong consistency," and never trade off WAN latency without measuring it.

## 6. Comparing LOCAL_ONE, LOCAL_QUORUM, and Other CLs

Assume `NetworkTopologyStrategy` is configured with `dc_hn:3` and `dc_sg:3`, for a total RF=6.

| Consistency Level | Required Responses for **Write** | Required Responses for **Read** | Scope |
| --- | --- | --- | --- |
| `LOCAL_ONE` | 1 replica in local DC | 1 replica in local DC | Local to coordinator |
| `LOCAL_QUORUM` | 2/3 in local DC | 2/3 in local DC | Majority within local DC |
| `ONE` | 1 replica | 1 replica | Does not restrict CL semantics to the local DC |
| `QUORUM` | 4/6 replicas | 4/6 replicas | Majority over **total keyspace RF** |
| `EACH_QUORUM` | 2/3 **in each DC**: 4 ACKs total | **Not used for regular reads** | Per-DC quorum; primarily for writes |
| `ALL` | 6/6 replicas | 6/6 replicas | Every configured replica |

**Cluster-wide `QUORUM` is not `EACH_QUORUM`:** `QUORUM` needs 4/6 total responses, which could be 3 in `dc_hn` and 1 in `dc_sg`; `EACH_QUORUM` requires at least 2 from **each** DC. `EACH_QUORUM` is for writes, not a drop-in replacement for `LOCAL_QUORUM` on reads.

**`ALL` reduces availability when any replica is down.** In multi-DC setups, it also depends on WAN link quality. If an application only needs local performance and tolerates eventual remote convergence, `LOCAL_QUORUM` is typically easier to operate than CLs requiring multi-DC responses; however, the final choice must follow business goals, staleness tolerance, and failure requirements.

For asymmetric-RF keyspaces, always **recompute from each DC's RF** rather than copying the 2/3 and 4/6 numbers from this table.

## 7. Failure Scenarios and Response Scopes

### Failure 1: Slow or Disconnected WAN Between Two DCs

If `dc_hn` still has two healthy replicas and clients use a coordinator in `dc_hn`, `LOCAL_QUORUM` can continue succeeding **without ACKs from `dc_sg`**. However, mutations to the remote DC may be delayed or missed; monitor hints, write timeouts, and run repair once the network recovers.

**Do not treat a local ACK as confirmation of remote durability.** If the application has DR (disaster recovery) requirements to survive complete loss of a DC immediately after an ACK, evaluate multi-DC consistency/replication, RPO/RTO, recovery procedures, and dedicated verification schedules.

### Failure 2: Local DC Has Two Live Nodes at RF=3

`LOCAL_ONE` can still succeed with one response, while `LOCAL_QUORUM` needs both live replicas for the partition; any second failure can prevent local quorum from responding. `ALL` cannot succeed if the partition's third replica is down.

### Failure 3: Local DC Has Only One Live Replica at RF=3

`LOCAL_ONE` can continue responding, but `LOCAL_QUORUM` **cannot reach 2/3**. Even if the remote DC has three healthy replicas, remote ACKs cannot be added to satisfy local quorum. To shift traffic to the remote DC, you must change the **local coordinator** and reroute clients, while assessing whether remote data has caught up and meets business requirements.

### Failure 4: Client Fails Over from DC A to DC B

If the last write was only ACKed in `dc_hn` before the entire DC went down, `dc_sg` is **not guaranteed** to have the latest data. When switching the Java client to `dc_sg`, the new `LOCAL_QUORUM` is computed against `dc_sg`—it does not retroactively make prior writes "become quorum in B."

Missing events may need to be recovered from surviving replicas, event logs, outboxes, or backups. Changing the driver's local DC is **not** a mechanism to recover data that no longer exists on any replica.

### Failure 5: Read/Write Timeouts

`WriteTimeout` can occur after some replicas have already processed the mutation; the business state is **indeterminate**. `ReadTimeout` or `Unavailable` does not mean the row does not exist. Applications must distinguish:

- **ACKNOWLEDGED**: the client received success at the requested CL.
- **UNKNOWN_WRITE**: write error/timeout; unknown how many replicas received the mutation.
- **FOUND / MISSING / READ_ERROR**: read outcome for the specified key/CL; a read error must not be treated as missing.

Never retry counter increments or external side effects just because the previous call timed out.

## 8. CQL Lab: Self-Verification Across Two Datacenters

### 8.1. Topology Setup

An ideal lab has at least **three nodes per DC**, e.g., `dc_hn` with H1/H2/H3 and `dc_sg` with S1/S2/S3. Never use a production cluster to inject intentional faults.

~~~bash
# Run on a node with access to nodetool.
nodetool status
~~~

Confirm that nodes are grouped into the exact two DCs, most are `UN`, and no major bootstrap/decommission/repair is running. In `cqlsh` connected to **a `dc_hn` node**:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` reflects **the node answering the query**. If the application or `cqlsh` switches coordinators, verify the actual DC again. The `dc_hn`/`dc_sg` names in these examples must match the snitch values verbatim.

### 8.2. Create a Query-Driven Table

Use the `mdc_lab` keyspace from Section 2. The table uses a bounded partition key for verification:

~~~sql
CREATE TABLE IF NOT EXISTS mdc_lab.events_by_run (
    run_id text,
    event_id uuid,
    marker text,
    payload text,
    source_dc text,
    PRIMARY KEY ((run_id), event_id)
);
~~~

`run_id` is the **partition key**, and `event_id` is the clustering key. Each test run should use a new `run_id`, a fixed `event_id`, and an expected `marker` recorded in an **external manifest outside Cassandra**. Do not run cluster-wide `COUNT(*)` or scan many partitions just to verify a single event.

### 8.3. Write in Local DC Hanoi

Connect `cqlsh` to a node in `dc_hn`. `CONSISTENCY` below is a **cqlsh command**, not a CQL statement:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
INSERT INTO mdc_lab.events_by_run
    (run_id, event_id, marker, payload, source_dc)
VALUES (
    'mdc-trial-01',
    11111111-1111-4111-8111-111111111111,
    'expected-A',
    'written-from-dc-hn',
    'dc_hn'
);
~~~

If successful, record in your manifest: **ACK_LOCAL_QUORUM**, coordinator `dc_hn`, timestamp, `run_id`, `event_id`, `marker`. On timeout, record **UNKNOWN**; never treat a subsequent read as proof that the client received the earlier ACK.

### 8.4. Read in the Same DC with Two CLs

~~~text
CONSISTENCY LOCAL_ONE
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

When the cluster is healthy, both queries will likely return marker `expected-A`. **Identical results in a single test run do not mean the two CLs offer identical guarantees.** The goal is to record the requested CL and the condition a read must satisfy, not to force stale reads by polling continuously.

### 8.5. Read in DC Saigon Immediately After Writing

Connect **a separate `cqlsh` session** to a `dc_sg` node and set:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_id, marker, payload, source_dc
FROM mdc_lab.events_by_run
WHERE run_id = 'mdc-trial-01';
~~~

Important observations to record in your report:

- If `expected-A` is seen: **the data was observed** at local quorum in `dc_sg`; this does not imply the initial write ACK waited for the remote DC.
- If not seen: this can be consistent with the remote DC not yet having received the mutation; inspect logs, timing, topology, and other writes/deletes.
- If timeout/unavailable: record `READ_ERROR`; **do not** count it as lost data.
- If remote delivery is so fast that you cannot reproduce a stale read, **do not** rewrite the theory as "cross-DC `LOCAL_QUORUM`."

To verify the system after an outage or replication lag, inspect hint/repair logs/metrics and reconcile a stable set of markers. Avoid intentionally cutting WAN links on real infrastructure just to demonstrate the mechanism.

## 9. Java Driver 4.x: Local Datacenter and Consistency

With Java Driver 4.x, applications should configure the appropriate **local datacenter** and contact points. The DC name in `withLocalDatacenter(...)` must match the topology seen by the driver. For example, two regionally deployed services will have **separate session configurations** rather than dynamically flipping the local DC on a shared session serving the entire workload.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

import java.net.InetSocketAddress;

public final class CassandraSessionFactory {
    public static CqlSession connectHanoi() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.20.0.11", 9042))
            .withLocalDatacenter("dc_hn")
            .withKeyspace("mdc_lab")
            .build();
    }

    public static CqlSession connectSaigon() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.30.0.11", 9042))
            .withLocalDatacenter("dc_sg")
            .withKeyspace("mdc_lab")
            .build();
    }
}
~~~

The IPs above are **illustrative lab addresses only**; replace them with real contact points. Depending on your environment, the driver will also need authentication, TLS, profile tuning, and multiple contact points to avoid depending on a single node. The driver discovers topology and handles load balancing; do not build your own random IP loop across two DCs when you rely on consistent `LOCAL_*` semantics.

### Example Write-Then-Read with Explicit CL

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;

public final class LocalConsistencyProbe {
    public enum WriteResult { ACKNOWLEDGED, UNKNOWN }
    public enum ReadResult { FOUND_MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement read;

    public LocalConsistencyProbe(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO mdc_lab.events_by_run " +
            "(run_id, event_id, marker, payload, source_dc) " +
            "VALUES (?, ?, ?, ?, ?)");
        this.read = session.prepare(
            "SELECT marker FROM mdc_lab.events_by_run " +
            "WHERE run_id = ? AND event_id = ?");
    }

    public WriteResult insertAtLocalQuorum(
            String runId, UUID eventId, String marker,
            String payload, String sourceDc) {
        try {
            session.execute(insert.bind(
                    runId, eventId, marker, payload, sourceDc)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotence(false));
            System.out.printf("ACK LOCAL_QUORUM run=%s id=%s%n",
                runId, eventId);
            return WriteResult.ACKNOWLEDGED;
        } catch (RuntimeException error) {
            System.err.printf("UNKNOWN_WRITE run=%s cause=%s%n",
                runId, error.getClass().getSimpleName());
            return WriteResult.UNKNOWN;
        }
    }

    public ReadResult verify(
            String runId, UUID eventId, String expectedMarker,
            DefaultConsistencyLevel readCl) {
        try {
            Row row = session.execute(read.bind(runId, eventId)
                    .setConsistencyLevel(readCl))
                .one();
            if (row == null) return ReadResult.MISSING;
            return expectedMarker.equals(row.getString("marker"))
                ? ReadResult.FOUND_MATCH : ReadResult.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf("READ_ERROR CL=%s id=%s cause=%s%n",
                readCl, eventId, error.getClass().getSimpleName());
            return ReadResult.READ_ERROR;
        }
    }
}
~~~

Usage:

~~~java
// Two sessions pointing to two different local DCs; close sessions when finished.
try (CqlSession hn = CassandraSessionFactory.connectHanoi();
     CqlSession sg = CassandraSessionFactory.connectSaigon()) {

    UUID eventId = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    LocalConsistencyProbe writer = new LocalConsistencyProbe(hn);
    LocalConsistencyProbe remoteReader = new LocalConsistencyProbe(sg);

    writer.insertAtLocalQuorum(
        "mdc-trial-java-01", eventId, "expected-A", "demo", "dc_hn");

    LocalConsistencyProbe.ReadResult result = remoteReader.verify(
        "mdc-trial-java-01", eventId, "expected-A",
        DefaultConsistencyLevel.LOCAL_QUORUM);
    System.out.println("dc_sg read=" + result);
}
~~~

**Pitfalls to avoid when interpreting this example:**

- `insertAtLocalQuorum` records ACK when `execute` returns successfully. An `UNKNOWN` outcome does not prove the mutation does not exist; production code must distinguish timeouts, `Unavailable`, and configuration errors.
- `remoteReader` uses local DC `dc_sg`, so the **read** `LOCAL_QUORUM` is computed in `dc_sg`. This differs from the **write** `LOCAL_QUORUM` in `dc_hn`.
- `FOUND_MATCH` is simply the value read at the chosen CL; it does **not** confirm every remote replica already persists the data or that the initial write ACK included remote replicas.
- `MISSING` must be distinguished from `READ_ERROR`. When logging the source manifest, only mark an event as "write ACKed" if the client actually received success.
- `setIdempotence(false)` reflects a cautious lab policy against automatic retries on indeterminate outcomes. For plain `INSERT`s using stable keys and values, an application can define its own idempotency policy after considering timestamps, TTLs, and concurrent operations.
- A production application should never open/close a `CqlSession` per request; the two sessions above only illustrate DC boundaries in a short lab program.

## 10. Monitoring and Verifying Cross-Datacenter Replication

**Do not measure convergence by running full-table `COUNT(*)` across two DCs.** Instead, prepare markers/event IDs from an independent source, query by partition key or primary key, and monitor operational signals:

| Metric / Signal | Why It Is Useful | Limitations |
| --- | --- | --- |
| `nodetool status` per DC | Confirms `UN`/`DN` node counts and topology | An `UN` node does not prove every replica has caught up |
| Hint logs/metrics | Identifies mutations queued, failed, or delivered | Absence of hints does not prove data is identical |
| `nodetool netstats` | Observes streaming during repair/bootstrap | Not a gauge for every remote mutation |
| Repair sessions/coverage | Verifies token ranges/replicas reconciled successfully | A single repair session may not cover the whole cluster/DC |
| Per-DC p50/p95/p99 and timeouts | Detects WAN impact, DC issues, or overly strict CL | Latency does not prove data completeness |
| Expected manifest vs. actual | Detects missing events or mismatched markers | Manifest must be trustworthy; avoid confusing read errors with missing data |
| Business pipeline sync lag | Shows data freshness served by standby DC | Requires a source of truth, checkpoints, and watermark definitions |

Basic tools:

~~~bash
# Run on an appropriate node in the lab; one command does not replace cluster-wide checks.
nodetool status
nodetool netstats
nodetool compactionstats
~~~

After a network or replica outage, evaluate **repair** according to version, token ranges, keyspace, DC, and maintenance schedule. Repair consumes network bandwidth, disk I/O, and compaction capacity; never run it indiscriminately during peak hours. Repair cannot recreate an event lost from **all** replicas and data sources, so strict RPO targets still require reliable logs, backups, or outboxes.

### Two Reasoning Errors to Avoid

**Error 1:** "Reading in `dc_sg` sees the data, so the earlier `LOCAL_QUORUM` write must have waited for `dc_sg` ACKs." **False**: replication can reach the remote DC before the read runs; the initial ACK condition still only counted `dc_hn`.

**Error 2:** "`LOCAL_QUORUM` in `dc_sg` did not see the data, so Cassandra definitely lost data." **False**: this could be replication lag, different topology/CL, concurrent operations, deletes/TTLs, or read issues. Verify the expected source, timing, CL/RF, logs, and repair state.

## 11. Practice Exercises and Review Questions

**Exercise 1 — Quorum math across two DCs.** With `dc_hn:3` and `dc_sg:3`, compute the ACKs required for `LOCAL_ONE`, `LOCAL_QUORUM`, `QUORUM`, `EACH_QUORUM`, and `ALL`. Explain why `QUORUM=4/6` is not equivalent to `EACH_QUORUM=2+2`.

**Exercise 2 — Asymmetric RF.** A keyspace has `dc_hn:3` and `dc_sg:2`. How many local replicas does a `LOCAL_QUORUM` query executed by a coordinator in `dc_sg` require? If one `dc_sg` replica goes down, can `LOCAL_QUORUM` still be satisfied? Why don't `dc_hn` replicas help meet this local threshold?

**Exercise 3 — Read-your-writes.** Client A writes at `LOCAL_QUORUM` in `dc_hn` and receives an ACK. Client B immediately reads at `LOCAL_QUORUM` in `dc_sg`. Does `W+R>RF` guarantee B sees the new record? Sketch a routing/synchronization approach if the product requires read-your-writes.

**Exercise 4 — WAN outage.** The `dc_hn` ↔ `dc_sg` link is severed, and all three `dc_hn` replicas are alive. Predict the outcome of `LOCAL_ONE` and `LOCAL_QUORUM` writes via a `dc_hn` coordinator, noting the remote state and the risk if `dc_hn` fails completely before syncing.

**Exercise 5 — Failover.** `dc_hn` has only one local replica left, while `dc_sg` has three healthy replicas. Why does `LOCAL_QUORUM` through a `dc_hn` coordinator fail? What must change in the driver/routing to operate in `dc_sg`, and what risk remains regarding unreplicated data?

**Exercise 6 — Java verification.** Create two `CqlSession` instances with different local DCs, write an event with a fixed marker in `dc_hn`, then read in both DCs. Record `ACKNOWLEDGED`, `FOUND_MATCH`, `MISSING`, and `READ_ERROR` with timestamps. Why does a successful read in the remote DC not change the definition of the local write ACK?

**Exercise 7 — Distinguishing LWT.** A development team proposes using `LOCAL_QUORUM` instead of `IF version = ?` to prevent concurrent update races. Explain why these solve two different problems, and note that serial consistency (`LOCAL_SERIAL`/`SERIAL`) is an additional setting when using LWT.

## Key Takeaway

**`LOCAL_ONE` requires one response and `LOCAL_QUORUM` requires a majority of responses within the coordinator's DC; ACKs from other DCs do not count toward the local threshold.** With RF3 per DC, `LOCAL_QUORUM` is 2/3 **within whichever DC coordinates the request**, not 2/6 cluster-wide. A successful write in `dc_hn` does not automatically guarantee immediate visibility in `dc_sg`; manage local boundaries via routing/Java Driver configuration, measure replication lag, reconcile markers, and prepare repair/failover procedures aligned with your system's RPO/RTO.
