# Testing a Missing Replica and Converging via Hints and Repair

## 1. Scenario: Writes Succeed While a Replica Is Down, but Is the Data Synchronized?

A Java system stores device events in **Apache Cassandra**. The keyspace uses `NetworkTopologyStrategy` with **replication factor (RF) = 3** in datacenter `dc1`; the application writes at **`LOCAL_QUORUM`**. One replica node is undergoing maintenance and temporarily stops receiving mutations. The client continues writing hundreds of events, receives successful responses, and the API dashboard looks normal. A few minutes later, the node returns to `UN` state in `nodetool status`.

An operations team might rush to conclude: **“Cassandra has already finished synchronizing on its own; nothing else needs to be done.”** This is an unproven conclusion. With RF=3, `LOCAL_QUORUM` only requires **two full replicas** to respond; the third replica may still be missing some mutations. **Hinted handoff** can forward missed mutations after the node recovers, but it is strictly a **best-effort** mechanism. **Anti-entropy repair** compares data belonging to the same token ranges and streams differences; it is a required mechanism to guarantee long-term convergence, especially when hints are missing or the hint window has expired.

~~~mermaid
sequenceDiagram
    participant Java as Java Driver / Client
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3 (down)
    Java->>C: INSERT / UPDATE at LOCAL_QUORUM
    C->>R1: Mutation
    C->>R2: Mutation
    C--xR3: Unable to deliver mutation
    R1-->>C: ACK
    R2-->>C: ACK
    C-->>Java: Success with 2/3 quorum
    Note over C: If conditions permit, store a hint for R3
    Note over R3: Node recovers
    C->>R3: Replay still-valid hints
    Note over R1,R3: Repair is still needed on schedule and when divergence exists
~~~

This lesson belongs to the **Load and Distributed Fault Testing** chapter in the **`DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`** module: distributed architecture, tokens, partition keys, wide-column storage, read/write consistency, compaction/repair, and Java connectivity.

**Learning objectives:**

1. Explain **coordinator**, **natural replica**, RF, and `LOCAL_ONE`/`LOCAL_QUORUM`/`ALL` when one replica is absent.
2. Distinguish **commit log**, **hinted handoff**, **read repair**, and **full/incremental anti-entropy repair**.
3. Build or simulate a **three-node Cassandra** setup safely in a dedicated test cluster; inject a single fault with clear start/end markers and rollback.
4. Create a CQL fixture with deterministic partition keys, stable **operation IDs**, and a reconciliation ledger for counts/values/TTL/deletes.
5. Measure throughput, p95/p99, timeouts, and hint backlog **before–during–after** the fault, without treating client ACKs as proof that every replica updated.
6. Separate two experiments: **fast recovery with hints** and **absence exceeding the hint window / missing hints requiring repair**.
7. Read operational signals to know when **handoff is complete, repair is complete, and data has convergence evidence**; state the limits of each signal.
8. Handle `gc_grace_seconds`, tombstones, multiple DCs, overlapping failures, and fault-injection principles in production-like staging.

**Scope and limits:** CQL/Java examples focus on Cassandra 4.x/5.x with **full replicas** and Java Driver 4.x. `cassandra.yaml` and `nodetool` names can vary by version: Cassandra 3.x commonly uses keys ending in `_in_ms`, whereas newer versions have unit-friendly keys such as `max_hint_window`. **Do not copy configs without checking documentation for the exact version.** This is a lesson/experiment design; do not stop nodes, throttle networks, or run stress or repair tests in production.

## 2. Replica Model: Token Placement, Coordinator, and Write Success Conditions

### 2.1. Natural Replicas Are Chosen by Partition Key

With table `events_by_device_day`:

~~~sql
PRIMARY KEY ((device_id, event_day), event_time, event_id)
~~~

- `(device_id,event_day)` is the **composite partition key**. Cassandra hashes both into a token; natural replica placement depends on the keyspace strategy, topology/racks, and token ring.
- `event_time,event_id` are **clustering keys** determining ordering inside a partition; they do **not** create separate partitions.
- `NetworkTopologyStrategy` specifies RF **per DC**, not a location-agnostic global replica count.
- **Coordinator** is the node receiving the CQL request, which might **not** be a natural replica for the key. The driver selects a coordinator using load balancing/token awareness and node health; the coordinator routes to the appropriate replicas.

~~~mermaid
flowchart TD
    A["Java: partition key (device-7, 2026-11-21)"] --> B["Token via partitioner"]
    B --> C["NetworkTopologyStrategy + topology"]
    C --> R1["Full replica R1"]
    C --> R2["Full replica R2"]
    C --> R3["Full replica R3"]
    D["Coordinator receives request"] --> R1
    D --> R2
    D -.-> R3
    R1 --> E["CL decides how many ACKs suffice to reply to client"]
    R2 --> E
    R3 -.-> E
~~~

### 2.2. Single DC with RF=3

| CL | Full replica responses needed for an operation (RF=3) | When exactly one replica is unavailable |
| --- | ---: | --- |
| `LOCAL_ONE` | 1 in local DC | Can succeed if an eligible replica remains. |
| `LOCAL_QUORUM` | `floor(3/2)+1=2` in local DC | **Can succeed** with the two healthy replicas. |
| `ALL` | All three full replicas (for the single-DC example) | Typically **cannot** complete when one replica is down. |
| `ANY` (write-only special) | Can record a hint in limited circumstances | **Not** evidence that data resides on a replica or is readable; do not use it to “guarantee convergence” in this lab. |

Do not equate a **quorum ACK** with “all three copies are identical.” `LOCAL_QUORUM` provides read/write quorum intersection under proper topology and operation conditions, but a successful `SELECT LOCAL_QUORUM` **does not prove the third replica has every mutation** and does not replace repair.

### 2.3. Two DCs Do Not Share a “Global Quorum” When Using `LOCAL_QUORUM`

If `dc1:3`, `dc2:3`, a `LOCAL_QUORUM` request from `dc1` needs quorum **within `dc1`**, not any two responses split across both DCs. Replicas in `dc2` may lag or miss writes; cross-DC replication, hint configuration, and repair scope must be understood. A single-DC test **cannot** be used to claim multi-DC active-active guarantees.

## 3. Four Mechanisms Commonly Mistaken for “Cassandra Self-Healing”

| Mechanism | When does it happen? | Target / what is protected | Important limits |
| --- | --- | --- | --- |
| **Commit log** | When a node receives a valid mutation according to its write path and durability settings. | Local durability on that node, alongside memtable/SSTable. | Does not deliver missed mutations to another replica. |
| **Hinted handoff** | Coordinator fails to deliver a write to a replica while hinting is valid and within the window. | **Hints stored temporarily on another node**, replayed to the target replica when it returns. | Best-effort; hints can be missed/lost/uncreated; does not replace anti-entropy repair. |
| **Read repair** | Certain read paths detect mismatches among queried replicas, depending on CL/version/config. | Repairs differences within the scope of read data per actual behavior. | Does not scan all token ranges or ensure rarely accessed partitions converge. |
| **Anti-entropy repair** | Operations schedule or trigger repair for token ranges/tables/DCs. | Compares replica datasets using Merkle trees and streams differences. | Resource-intensive; requires coverage, healthy topology, schedule, and runbooks; cannot recover data if all copies are lost. |

**Key distinction:** **Hints shorten the divergence window; repair reduces long-term divergence risk** and is a mandatory part of eventual consistency/anti-entropy strategy. Do not say “repair is only used when hints fail”: repair is also required for deletes, writes missed for various reasons, and partitions that are never read.

## 4. Timeline of an Absent Replica

| Milestone | R1/R2/R3 | Client and coordinator | Data/repair |
| --- | --- | --- | --- |
| T0 baseline | All three `UN`. | Read/write at `LOCAL_QUORUM`. | Fixture verified; no fault injected yet. |
| T1 inject fault | R3 stopped and seen as down. | Driver picks healthy coordinators in local DC. | R3 receives no new mutations during absence. |
| T2 load during outage | R1, R2 remain active. | `LOCAL_QUORUM` can ACK 2/3. | One or more coordinators may store hints for R3. |
| T3 recovery | R3 starts, gossips back to `UN`. | Traffic continues; load may rise during handoff. | R3 **may still miss** mutations despite `UN`. |
| T4 handoff | Hints on coordinators replay per budget/throttle. | Latency can rise while serving online load plus replay. | Divergence narrows; observe pending hints/failures. |
| T5 anti-entropy | Nodes healthy enough for repair. | Backfill may be throttled to stay within SLO. | Repair compares token ranges and streams differences as needed. |
| T6 verify | Cluster stabilizes. | Compare ledger/correctness, latency, errors, topology. | Claim convergence only with evidence and tested scope. |

Never do `sleep 30` and declare handoff finished. **Node `UN` is only a membership/availability signal.** It does not prove every hint was dispatched/ACKed, all ranges were repaired, or tombstones were handled safely.

## 5. Safety Guardrails Before Running Fault Injection

**You must use an isolated test cluster or approved staging environment.** Stopping a replica in production reduces real fault tolerance, risks timeouts/data loss on a second failure, increases hint disk usage, or impacts repair, streaming, and customers.

### 5.1. Prerequisites

~~~text
[ ] Permission and dedicated test environment confirmed; cluster ID/DC verified; no real user data.
[ ] Cassandra version + JDK + Java Driver + hints/repair configuration pinned.
[ ] RF=3 full replicas in dc1 with three real Cassandra nodes, not RF3 on a single node.
[ ] Token/rack/DC metadata verified; node ID of R3 and coordinator candidates known.
[ ] Adequate disk headroom, RAM, network, logs/metrics, and synchronized clocks.
[ ] Backups/snapshots taken if persistent test volumes hold data worth preserving.
[ ] Query shape, row size, traffic rate, CL, and expected operation IDs locked.
[ ] Stop criteria defined: errors, disk, p99, pending hints, JVM OOM, replica lag.
[ ] Clear owner assigned for restoring the node, checking handoff, and running repair.
[ ] Only one fault injected at a time in the baseline test.
~~~

### 5.2. Do Not Use Destructive Operations as “Shortcuts”

- **Do not** run `nodetool truncatehints` to “clear backlog” in production; it drops undelivered hints.
- **Do not** delete `hints_directory`, commit logs, or SSTables to force recovery scenarios: that is a **different fault** carrying data-loss risk.
- **Do not** set `gc_grace_seconds=0` and force compaction to test zombies on any cluster holding real data.
- **Do not** run `docker compose down -v` if volumes/data are still needed to prove convergence; `-v` deletes volumes and changes the nature of the test.
- **Do not** run full repair on every node simultaneously right as a node comes online: it can cause I/O/network/GC contention and degrade SLOs.
- **Do not** confuse stopping a **coordinator** with stopping a natural replica of the key: the two faults affect the write path differently.

## 6. Three-Node Lab Environment: Docker Compose Model

For reproducibility, you can run three Cassandra containers on **a single test host with sufficient RAM/disk**. This is a functional availability lab and **does not simulate three physical failure domains**: if the host or Docker daemon dies, all three nodes go down.

### 6.1. Reference Compose File

~~~yaml
# Illustrative docker-compose.yml: use inside a DEDICATED lab directory.
# Pin approved image digests/patches in real CI.
services:
  cassandra1:
    image: cassandra:4.1
    hostname: cassandra1
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack1
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    volumes:
      - cassandra1-data:/var/lib/cassandra

  cassandra2:
    image: cassandra:4.1
    hostname: cassandra2
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack2
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    depends_on:
      - cassandra1
    volumes:
      - cassandra2-data:/var/lib/cassandra

  cassandra3:
    image: cassandra:4.1
    hostname: cassandra3
    environment:
      CASSANDRA_CLUSTER_NAME: fault-lab
      CASSANDRA_DC: dc1
      CASSANDRA_RACK: rack3
      CASSANDRA_ENDPOINT_SNITCH: GossipingPropertyFileSnitch
      CASSANDRA_SEEDS: cassandra1
      CASSANDRA_NUM_TOKENS: "16"
      MAX_HEAP_SIZE: 768M
      HEAP_NEWSIZE: 128M
    depends_on:
      - cassandra1
    volumes:
      - cassandra3-data:/var/lib/cassandra

volumes:
  cassandra1-data:
  cassandra2-data:
  cassandra3-data:
~~~

`depends_on` only coordinates container start order; it does **not** guarantee Cassandra has joined the ring. Use a bounded health/wait loop, run `nodetool status` from healthy nodes, and verify **three `UN` nodes in `dc1`** before creating the keyspace. If the Docker host lacks RAM, use dedicated VMs or a test cluster; **never use one node with RF=3** as a substitute for three replicas.

### 6.2. Commands in the Approved Lab Environment

~~~bash
docker compose up -d
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra1 nodetool info
docker compose exec -T cassandra2 nodetool status
docker compose exec -T cassandra3 nodetool status
~~~

Run commands inside containers to avoid driver topology issues: a Java process running **on the host** with only one forwarded port may receive unroutable internal Docker IPs from topology discovery. For Java tests, run the test runner on the **same Docker network** or configure network/port mappings compatible with Cassandra's advertised addresses. Never “fix” connectivity by disabling TLS/auth when moving from a Docker lab to staging.

## 7. CQL Fixture to Observe Missed Mutations

### 7.1. Keyspace with `NetworkTopologyStrategy` and RF=3

~~~sql
CREATE KEYSPACE IF NOT EXISTS fault_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS fault_lab.events_by_device_day (
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  deleted boolean,
  PRIMARY KEY ((device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

All three nodes in this lab are natural replicas for every partition because RF=3 across 3 nodes in a single DC. In a cluster with more than three nodes, you must identify the **natural replica set** for the tested partition; stopping an arbitrary node may not affect that key. A stable `event_id` acts as the **event deduplication/distinction key** during producer retries; never generate a new ID for the same logical operation after a timeout.

### 7.2. Verified Baseline Seed

~~~sql
-- cqlsh command; do not pass raw CONSISTENCY lines into the Java Driver.
CONSISTENCY LOCAL_QUORUM;

INSERT INTO fault_lab.events_by_device_day
  (device_id,event_day,event_time,event_id,event_type,payload,deleted)
VALUES
  ('device-7','2026-11-21','2026-11-21T08:00:00Z',
   123e4567-e89b-42d3-a456-426614174001,'BASELINE','before-fault',false);

SELECT event_time,event_id,event_type,payload
FROM fault_lab.events_by_device_day
WHERE device_id='device-7' AND event_day='2026-11-21'
LIMIT 100;
~~~

**Experimental data requires an independent source of truth:** beyond the database rows, the Java writer records an **expected-mutations ledger** containing `operationId/eventId`, primary key, value, phase (`BEFORE/DURING/AFTER`), send/ACK timestamps, exceptions, and CL. Checking only `COUNT(*)` can hide **one missing ID offset by one duplicate or overwritten ID**.

### 7.3. Table Scope

- Use a single day partition with a modest row count to inspect identities/values completely.
- Add more `device_id` values if you need to test multiple token/replica sets in clusters larger than three nodes.
- Do not use `ALLOW FILTERING` or `SELECT *` across all partitions for verification. Wide scans in Cassandra can overload the cluster under test.
- When testing TTLs/deletes, use a **separate fixture**; do not mix them with the baseline where “all events are immutable and must exist.”

## 8. Three Measurement Axes: Correctness, Availability, and Recovery

| Axis | Question to answer | Minimum signals |
| --- | --- | --- |
| **Availability** | While R3 is down, how many writes/reads succeed at the chosen CL? | Sent/ACK/fail/timeout per request, CL, p50/p95/p99, in-flight. |
| **Correctness** | Can all ACKed operations be read back completely with exact payloads/versions? | Compare **set of event IDs/values** against ledger within partition/time scope; isolate unknown timeouts. |
| **Recovery/convergence** | Has R3 caught up on missed mutations and have replicas reconciled? | Membership + hint service metrics + completed/validated repair + replica-scoped read evidence. |

**No single metric suffices on its own.** `nodetool status` `UN` only proves membership; a successful `LOCAL_QUORUM` read can be served by two healthy replicas; an empty hint queue does not prove hints were ever created; a successful repair report only covers the **token/table/DC scope processed by that job**.

## 9. Phase A — Fault-Free Baseline: All Replicas Healthy and Stable Measurement

Before stopping any node, run the **exact same workload** you will use during the outage:

~~~text
Topology:
  dc1: R1=UN, R2=UN, R3=UN
  keyspace RF=3
  write/read CL=LOCAL_QUORUM
  workload  = CQL insert events (bound PK), fixed row payload, stable UUIDs

Baseline duration:
  warmup  : bounded (e.g., 2 minutes)
  steady  : bounded (e.g., 5 minutes)
  cooldown: drain all outstanding requests

Capture:
  request rate / achieved throughput / in-flight
  p50, p95, p99 write + read latencies
  success, unavailable, timeout, client overload
  CPU/JVM GC, disk I/O, network RTT, pending queues
  hint backlog = normally negligible in a healthy cluster
  ledger of expected ACKed event IDs/values
~~~

**Durations are illustrative**, not universal benchmarks. If the baseline already misses SLOs, do not proceed to stopping a replica and debugging afterwards; fix the query model, resource saturation, driver routing, RF/CL, or schema first.

### 9.1. Load Temperature Must Be Bounded

Before injecting faults:

- Choose a **rate cap** and **bounded in-flight**, such as 100 CQL writes/s and at most 32 in-flight requests per lab runner; numbers must fit actual cluster capacity.
- Keep **row bytes, TTL, CL, and client count** constant across phases for comparison; never change multiple variables at once.
- Avoid tight `while(true)` loops firing unbounded async futures: that measures client/driver saturation before measuring replica failure.
- Add a **zero-load canary** writing a few IDs before the fault to verify test logic and ledger recording work.

## 10. Phase B — Taking R3 Out in a Controlled Way

### 10.1. Pick the Right Replica and Record Fault Markers

With three nodes and RF=3 in one DC, **every node is a natural replica** for every lab partition. If node count exceeds RF, first determine the actual replica set (using metadata, driver token map, or appropriate tooling), rather than stopping an arbitrary node.

~~~bash
# Execute ONLY on your dedicated test cluster:
docker compose exec -T cassandra1 nodetool status
docker compose stop cassandra3

# Wait with a deadline and verify remaining nodes see R3 as down:
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra2 nodetool status
~~~

**Do not assume `docker compose stop` immediately means all coordinators know the node is down.** Gossip and the failure detector take time; request timeouts can occur during the transition window. Record **`fault_start_utc`**, the timestamp when `R3=DN` is observed, and the Cassandra version.

### 10.2. Stopping a Node Differs from Cutting a Network Path

| Fault | What happens | Risk / meaning |
| --- | --- | --- |
| **Stop R3 process/container** | R3 stops ACKing and receiving direct writes. | Simple, clear recovery marker; hinting can trigger. |
| **Block traffic R3 ↔ other nodes** | R3 keeps running but is network-partitioned. | Can cause split visibility/gossip delay; all network rules must be reverted afterward. |
| **Block client → R3 while internode traffic stays open** | Driver stops using R3 as coordinator, yet R3 still receives replica mutations. | **Not** a “replica missed writes” test; only a client-path failure. |
| **One-way block coordinator → R3** | More complex due to asymmetric ACK/gossip paths. | Behavior depends on topology; requires chaos/network expertise and verification of no hidden routes. |
| **Stop R1 and R2 simultaneously** | Local quorum for RF=3 is lost. | Completely different failure mode; not a baseline fault test, likely fails writes. |

For the baseline experiment, **stop R3**. If testing a network partition, isolate it into a separate test case with a pre-tested cleanup/rollback script; **never** inject disruptive firewall rules onto production hosts.

### 10.3. Expectations While R3 Is Down

~~~text
R1  UP/NORMAL
R2  UP/NORMAL
R3  DOWN/NORMAL (observed on peers, depending on displayed state)

LOCAL_QUORUM on RF3:
  -> requires two full replica ACKs
  -> can succeed via R1/R2

ALL on RF3:
  -> requires all three ACKs
  -> cannot be satisfied while R3 is down
~~~

**Not every request will succeed smoothly:** if R1/R2 are busy, the network blips, the driver hasn't rerouted away from R3 as coordinator yet, or a second fault hits, `LOCAL_QUORUM` can still suffer timeouts or `Unavailable`.

## 11. Phase C — Writing During the Outage with Java Driver While Keeping Event Identity Stable

### 11.1. Prepared Insert Using a Single `CqlSession`

Example for Java Driver 4.x, running the client **on the same network as the contact points** or in staging where driver discovery resolves valid addresses. The client should reuse a long-lived `CqlSession` and a least-privilege account:

~~~java
// FaultEventWriter.java
package example.cassandra.faultlab;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

public final class FaultEventWriter {
    public record Event(
        String deviceId, LocalDate day, Instant at,
        UUID eventId, String type, String payload) {}

    private final CqlSession session;
    private final PreparedStatement insert;
    private final Semaphore permits = new Semaphore(16);

    public FaultEventWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO fault_lab.events_by_device_day " +
            "(device_id,event_day,event_time,event_id,event_type,payload,deleted) " +
            "VALUES (?,?,?,?,?,?,false)");
    }

    // Stable identity for retry of the SAME logical operation:
    public static UUID stableEventId(String runId, int sequence) {
        byte[] key = (runId + ":" + sequence)
            .getBytes(StandardCharsets.UTF_8);
        return UUID.nameUUIDFromBytes(key);
    }

    public CompletionStage<UUID> writeAsync(Event event) {
        if (!permits.tryAcquire()) {
            return CompletableFuture.failedFuture(
                new RejectedExecutionException("fault-lab in-flight limit"));
        }
        try {
            BoundStatement statement = insert.bind(
                    event.deviceId(), event.day(), event.at(),
                    event.eventId(), event.type(), event.payload())
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            return session.executeAsync(statement)
                .thenApply(ignored -> event.eventId())
                .whenComplete((id, error) -> permits.release());
        } catch (RuntimeException dispatchError) {
            permits.release();
            return CompletableFuture.failedFuture(dispatchError);
        }
    }
}
~~~

**Important notes:**

1. `stableEventId(runId,sequence)` ensures the same **logical event** keeps a consistent key across retries. Generating a fresh UUID per retry can inflate row counts while creating a false sense of “durable writes.”
2. `event_time` is also part of the primary key; retries **must preserve the exact timestamp and partition day**, not just the UUID.
3. `setIdempotent(true)` is a declaration to the **driver** for retry/speculative execution policies; it **does not magically make arbitrary CQL statements idempotent**. A plain insert with identical full key/values and no TTL/counter is suitable for illustration; custom timestamps, TTLs, LWTs, batches, or side effects require separate evaluation.
4. `Semaphore(16)` is an **admission gate per writer instance**, not a fleet-wide cap. Reject explicitly when slots run out instead of queuing unboundedly; tune to SLO/capacity and share budget with other workloads.
5. `whenComplete` releases the slot once the stage completes, including on exceptions. **Never block inside driver callbacks.**
6. A stage failing with `WriteTimeout` does not mean the mutation never reached any replica. The ledger must separate **ACKed**, **definitely failed**, and **unknown outcome** for reconciliation.
7. This Java class only covers the write path; closing `CqlSession` belongs to application lifecycle **after draining work**, never immediately after each async call.

### 11.2. Sending Workload During the Outage

Inside a rate-limited runner, send `Event` records after **peers have observed R3 as down**. For example:

~~~text
runId   = faultlab-20261121-A
device  = device-fault-7
day     = 2026-11-21
events  = 20..200 logical IDs (do not mint extra IDs on retry)
CL      = LOCAL_QUORUM
payload = 100..500 bytes, no TTL
rate    = capped to fit test cluster, no unbounded fan-out

Single ledger record:
  eventId       = stable UUID
  fullPK        = (deviceId, day, eventTime, eventId)
  phase         = DURING_R3_DOWN
  startUtc      = ...
  acknowledged  = true/false/unknown
  errorClass    = ...
  responseTime  = ...
  attemptedCL   = LOCAL_QUORUM
~~~

**Goal of this phase:** show that writes receiving two ACKs are still accepted by the client while R3 is down, while creating a batch of mutations that R3 **did not directly receive**. Count only **ACKed** IDs into the “definitely written at CL” set; record timeouts separately for reconciliation.

### 11.3. Do Not Ramp Speed Before Verifying Correct Behavior

Run a small batch of 20–100 events to verify correctness before increasing load for performance measurement. If the small run already shows missing IDs, unexpected `Unavailable` errors, or schema mismatches, stop and fix it; one million inserts/s only makes debugging harder.

## 12. Reading During the Outage: Seeing Data Does Not Mean R3 Has It

After `writeAsync` receives `LOCAL_QUORUM` ACKs:

~~~sql
-- Run in cqlsh from a healthy node; not embedded CQL inside Java.
CONSISTENCY LOCAL_QUORUM;

SELECT event_time,event_id,event_type,payload
FROM fault_lab.events_by_device_day
WHERE device_id='device-fault-7' AND event_day='2026-11-21'
LIMIT 500;
~~~

If all expected IDs appear, this proves **quorum reads return the expected results in this scenario**. **It does not prove R3 has the mutations**, because R3 is absent and the read was satisfied by R1/R2.

### 12.1. Why Testing `LOCAL_ONE` Is Also Insufficient

`LOCAL_ONE` can pick **any eligible full replica** in the local DC. Once R3 returns before catching up, one `LOCAL_ONE` read **might** return stale state if it hits R3, while another hitting R1/R2 returns fresh data.

However:

- Merely pinning the **coordinator node** via Java Driver `Statement.setNode` **does not guarantee** the server picks that coordinator as the **only local read replica**.
- Multiple `SELECT LOCAL_ONE` queries returning matching results do not prove all replicas have converged: they could all have been served by healthy nodes.
- `LOCAL_QUORUM` may trigger read repair on the queried data, incidentally healing the probe partition; it **does not** substitute for anti-entropy testing across the full token range.
- If you want to inspect “which cells each replica holds,” use a **purpose-built test with controlled routing/replica isolation or proper validation tooling**, rather than inferring from driver contact points without verifying the read path.

### 12.2. Distinguishing Three Layers of Evidence

~~~text
Client:
  200 OK / ACK at LOCAL_QUORUM
    => Operation met the CL contract.

Cluster service:
  Hints delivered, no pending hints reported
    => Handoff progressed within observed scope.

Replica correctness:
  Full repair/validation + replica-scoped data check
    => Stronger convergence evidence; still subject to limits under concurrent writes.
~~~

`nodetool status` does not show which keys live on each replica, and a quorum `COUNT(*)` only counts logical rows. Avoid any claim of “100% consistent replicas” without matching evidence.

## 13. Where Are Hints Created and Stored?

When a coordinator detects that a target replica missed a mutation under eligible conditions, Cassandra can store a **hint on the coordinator's own filesystem** for later delivery. Each hint references the **target replica**, serialized mutation, timestamp, and metadata. Do not describe hints as ordinary rows in the `system` keyspace or in the down replica's commit log.

### 13.1. Conditions Affecting Hints

| Condition | Meaning |
| --- | --- |
| `hinted_handoff_enabled` | Feature enabled/disabled per version/config. |
| `hinted_handoff_disabled_datacenters` | Can disable handoff for specific DCs. |
| `max_hint_window` / `max_hint_window_in_ms` | **Maximum time after a node goes down during which new hints continue to be created**, not a TTL guaranteeing hints remain or get delivered. |
| Coordinator disk/retention | Hints require local storage; disk full/corruption/loss can drop hints. |
| Coordinator lifetime | Hints can survive restarts when storage is durable and handled cleanly, though losing the coordinator/disk can also lose hints. |
| Connectivity to target replica | The replica must return and accept hint replay; network/permissions/throughput limits can slow delivery. |
| Keyspace/table mutation semantics | Hints preserve original mutation timestamps for timestamp-based reconciliation; they **cannot** fix every mismatch from expired tombstones or lost source state. |

**Rule to remember:** if R3 stays down longer than the hint window, Cassandra typically **stops creating new hints for R3**; do not assume previously created hints vanish precisely at that boundary. Conversely, hints can still be lost or omitted for operational reasons even during outages shorter than the window.

### 13.2. Version-Dependent Hint Windows

~~~yaml
# cassandra.yaml — expresses INTENT; DO NOT copy verbatim across versions.
hinted_handoff_enabled: true
hinted_handoff_disabled_datacenters: []

# Newer Cassandra versions use names like:
max_hint_window: 3h

# Older Cassandra versions may use:
# max_hint_window_in_ms: 10800000
~~~

`3h` is the documented default across many Cassandra release lines, **not a guarantee that every deployment actually uses 3 hours**. Check each node's **effective configuration**: operators can override, dynamically modify at runtime, or disable hints per DC.

### 13.3. Hints Are Not Free

Hints consume **disk** on the coordinator, CPU for serialization/compression, network bandwidth for replay, and I/O on the target. When R3 returns, replaying a large backlog can spike **online traffic p99**, especially alongside compaction and repair.

**Never treat hinted handoff as an unbounded message queue or backup system.** It is designed to reduce divergence across bounded outages, not guarantee every historical write can always be recovered from hints alone.

## 14. Hint Configuration and Inspection Commands by Version

### 14.1. Key Settings to Know

| Group | Common setting name (newer Cassandra) | Meaning |
| --- | --- | --- |
| Enable/disable | `hinted_handoff_enabled` | Whether hints are created/delivered. |
| DC policy | `hinted_handoff_disabled_datacenters` | Disables handoff to listed DCs. |
| Window | `max_hint_window` | Outage duration during which new hints continue to be stored. |
| Rate | `hinted_handoff_throttle` | Delivery rate limit, affecting catch-up time. |
| Delivery threads | `max_hints_delivery_threads` | Number of delivery threads; consider multi-DC/traffic impact. |
| Storage | `hints_directory`, `max_hints_file_size` | Storage path and hint segment file size. |
| Flush/compress | `hints_flush_period`, `hints_compression` | Storage/delivery overhead. |

In Cassandra 3.x many equivalent settings carry suffixes **`_in_ms`**, **`_in_kb`**, or **`_in_mb`**. Never read v5 docs and paste `max_hint_window` into Cassandra 3.11 without checking config parsing.

### 14.2. `nodetool` for Inspection, Not Auto-Healing

~~~bash
# Run on EACH coordinator / hint storage node in the lab cluster:
nodetool status
nodetool statushandoff
nodetool getmaxhintwindow
nodetool info
nodetool tpstats
nodetool compactionstats
~~~

`getmaxhintwindow` was added in Cassandra 4.0. `statushandoff` reflects handoff status per node; it **does not** prove all hints for R3 have been successfully replayed. Combine **hint metrics, logs, backlog, and read/repair validation**.

### 14.3. Risky State-Changing Commands

~~~text
nodetool pausehandoff       # Pauses delivery (does not automatically stop writing new hints).
nodetool resumehandoff      # Resumes delivery.
nodetool disablehandoff     # Disables hint storage/delivery per running version behavior.
nodetool enablehandoff      # Re-enables handoff.
nodetool truncatehints      # Deletes hints — DANGEROUS, do not use to clear backlog.
nodetool setmaxhintwindow   # Modifies hint window at runtime within applicable scope.
~~~

**These commands are only a functional reference**; do not alter production configuration without an approved change request. When multiple coordinators hold hints, changing only one node creates **config drift** and invalidates tests. Simulating “lost hints” via `truncatehints` is a separate **destructive test**, not a standard step in the baseline flow.

## 15. Phase D — Restoring R3 and Observing Hinted Handoff

### 15.1. Bring the Node Back with the Same Persistent Volume

~~~bash
# On the Docker lab cluster, AFTER stopping the outage-phase writer:
docker compose start cassandra3

# Wait with a deadline for ring/gossip stabilization:
docker compose exec -T cassandra1 nodetool status
docker compose exec -T cassandra2 nodetool status
docker compose exec -T cassandra3 nodetool status
~~~

**Keep the original `cassandra3-data` volume.** Deleting the volume and spinning up a fresh node turns the test into **node replacement/bootstrap**, no longer “the same replica returns and receives hints.” Replacement requires its own token/host ID/streaming/repair runbook.

Begin the recovery measurement phase only after:

1. R3 runs with the expected **cluster name**, `dc1`, rack/token/host ID and is not stuck in an unexpected join/move/replace state.
2. Native transport and internode communication are back, and peers show R3 as `UN`.
3. Disk/heap/compaction are not at critical thresholds right at startup.
4. Coordinators still hold hint files and handoff is enabled per effective config.

### 15.2. Observe Handoff on **Coordinators**, Not Just R3

~~~bash
docker compose exec -T cassandra1 nodetool statushandoff
docker compose exec -T cassandra2 nodetool statushandoff
docker compose exec -T cassandra1 nodetool tpstats
docker compose exec -T cassandra2 nodetool tpstats
docker compose exec -T cassandra3 nodetool tpstats
docker compose exec -T cassandra3 nodetool compactionstats
~~~

Once hint delivery starts, track **version-appropriate JMX/metrics and logs**:

- Total hints **created**, pending/file bytes, dispatched/received, failed/dropped, and delivery latency if available.
- Backlog per target node and **delivery bytes/s** rate.
- Disk free/headroom on coordinators and R3; CPU, GC, and compaction on R3.
- Application request throughput, error rate, and p95/p99 while handoff runs.
- If **DC hint exclusions** or paused handoff were used, verify they are restored cleanly after the test.

Exact MBean metric names vary across Cassandra 3.11/4.x/5.x; the official Hints documentation and your deployment's metrics reference are authoritative. **Never rely solely on the `hints` directory size on one node** to claim the whole cluster has caught up.

### 15.3. Serving Live Traffic While Receiving Hints

~~~mermaid
flowchart LR
    A["Normal CQL requests"] --> B["R1/R2/R3 serve workload"]
    C["Hints backlog on coordinators"] --> D["Hint delivery threads"]
    D --> E["R3 replays mutations"]
    E --> F["R3 memtable/SSTable/compaction"]
    B --> G["Shared disk/CPU/network budgets"]
    F --> G
    G --> H["p95/p99 and recovery lag"]
~~~

Replay competes for resources with reads/writes, compaction, and repair. Do not crank up `max_hints_delivery_threads` or the handoff throttle unboundedly just to go “as fast as possible”: preserve **online SLOs and disk/network headroom**. If p99 breaches stop criteria, throttle back batches/backfill or tune handoff via an approved runbook.

### 15.4. Recording Hint Catch-Up State

~~~text
R3 returned at (UTC)         = ...
R3 observed UN at            = ...
last hint queued             = ...
last hint delivered/acked    = ...
pending hint bytes per host  = ...
handoff failures/retries     = ...
ACKed event IDs from outage  = ...
validation query count/hash  = ...
repair scope/status          = ...
~~~

**Hint counters reaching 0 do not prove an un-hinted mutation was fixed**; proceed to properly scoped validation/anti-entropy steps.

## 16. Experiment A — Short Outage with Hint Replay

### 16.1. Hypothesis

When R3 is down for less than the effective `max_hint_window`, coordinators stay healthy, hints are enabled and retained, and R3 returns, hints **can** help R3 catch up on missed writes. This is a **hypothesis to measure**, not a 100% delivery guarantee from Cassandra.

### 16.2. Step-by-Step Execution

1. **Baseline:** three `UN` nodes, RF=3 keyspace and dedicated fixture; verify stable `LOCAL_QUORUM` reads/writes.
2. **Fault:** stop R3; wait for peers to mark R3 down; record UTC markers.
3. **Write:** send N event IDs during the outage at `LOCAL_QUORUM`; ledger classifies ACK/fail/unknown.
4. **Restore:** restart the exact R3 node/volume; watch membership and handoff logs/metrics on all coordinators.
5. **Wait bounded:** wait for delivery to near completion or hit the test deadline; **never** wait indefinitely.
6. **Validate:** compare ACKed IDs/values with post-recovery reads within defined scope, plus hinted delivery metrics/repair preview.
7. **Report:** document how many IDs were ACKed, hints created/delivered, duration, p99 impact, and what remains unproven.

### 16.3. Valid Conclusions from Test A

**Valid to conclude:** `LOCAL_QUORUM` maintained availability in this single-fault case, hints were created/delivered per metrics, and verified IDs read back per test contract.

**Invalid to conclude from Test A alone:** every token range/table in the cluster is repaired, all replicas are fully consistent, or R3 can stay down indefinitely and always recover using hints alone.

## 17. Experiment B — Missing or Incomplete Hints Still Require Repair

### 17.1. Two Ways to Construct This Scenario in a **Dedicated Lab**

**Approach 1: proactively disable hinted handoff on all potential coordinators**, then stop R3 and run the controlled write workload. Re-enable handoff afterward, recognizing that re-enabling **cannot retroactively generate missed hints**:

~~~bash
# ONLY in an isolated lab, BEFORE starting Case B writes:
docker compose exec -T cassandra1 nodetool disablehandoff
docker compose exec -T cassandra2 nodetool disablehandoff

docker compose stop cassandra3
# Write fixture at LOCAL_QUORUM via R1/R2, recording ledger.
docker compose start cassandra3

# Restore handoff configuration on coordinators:
docker compose exec -T cassandra1 nodetool enablehandoff
docker compose exec -T cassandra2 nodetool enablehandoff
~~~

**Approach 2:** set an intentionally **short hint window for testing** (across all coordinators), keep R3 down past that window, and send additional mutations afterward. No need to hold a production node down for 3 hours; **never lower tombstone grace** to “shorten the test.” Some versions support runtime `nodetool setmaxhintwindow`, while others require editing `cassandra.yaml` and a rolling restart prior to the test. Verify effective settings on every node.

### 17.2. Why Can Some Mutations Still Be Missing?

`disablehandoff` prevents hints from being created/delivered within the command's scope. While R3 is down, R1/R2 still satisfy `LOCAL_QUORUM`, yet R3 misses those mutations. When R3 returns, re-enabling handoff **cannot replay a hint that never existed**. Similarly, writes past the hint window typically stop creating new hints for the down endpoint.

**Still separate effects carefully:** read repair or background reads can accidentally heal probe partitions before you measure. To isolate anti-entropy repair's effect, minimize reads that could trigger read repair and log every operation run in the lab.

### 17.3. Goals of Test B

| Question | Check |
| --- | --- |
| Do quorum writes still succeed during the outage? | Ledger ACKed IDs at `LOCAL_QUORUM`. |
| Can the hint pipeline bring R3 up to date? | Effective handoff config, hint metrics, confirmed no-hint phase. |
| Are replicas still divergent before repair? | Repair preview/validation by token/table, or replica-scoped checks with verified read path. |
| Does anti-entropy repair cover the divergent scope? | Repair logs, Merkle/streaming metrics, completions, post-repair validation. |
| After repair, do client reads return accurate results? | Reconcile ACKed ledger IDs/values at proper CL and partition range; never swallow timeouts. |

**Expected outcome:** the test demonstrates that **quorum writes can succeed while a replica is down yet repair is still necessary for full convergence**. This directly shows why hints do not replace anti-entropy.

## 18. Anti-Entropy Repair: Merkle Trees, Streaming, and Scope of Work

### 18.1. Repair Is Not “Pushing the Entire DB from One Node to Another”

Cassandra repair coordinates nodes sharing the same **token ranges**, compares data—typically using **Merkle trees** per range—to detect differences, and streams only what is missing or mismatched. This differs fundamentally from hints:

~~~mermaid
flowchart TD
    A["Select keyspace/table + token ranges/DCs"] --> B["Repair session/participants"]
    B --> C["Build and compare Merkle trees"]
    C --> D{"Any differences?"}
    D -->|No| E["Complete validation for that range"]
    D -->|Yes| F["Stream mismatched data"]
    F --> G["Replicas for range catch up per repair protocol"]
    G --> H["Record repair result and advance to next range"]
~~~

Repair cannot restore an event if **no replica, backup, or upstream source still holds that event**, or if tombstones have already been purged leaving insufficient delete metadata. Therefore, correctness also depends on retention, backups, and repair cadence.

### 18.2. Full, Incremental, Preview, Validate

| Type | Actual scope | When to use |
| --- | --- | --- |
| **Incremental repair** | Tracks unrepaired data since previous incremental runs per version semantics. | Periodic anti-entropy schedules on clusters configured for incremental repair. |
| **Full repair** (`--full`) | Compares all data across selected token ranges, not just unrepaired subsets. | Reconciliation after suspected prolonged drift, disk corruption/restore, RF changes, or periodic policy. |
| **Preview repair** (`--preview`) | Builds comparisons/streaming estimates **without streaming repair data**. | Estimating divergence scope before applying repair; still incurs CPU/disk/network cost. |
| **Validation** (`--validate`) | Verifies data **already marked repaired** per tool semantics without repair streaming. | Validating repaired data or investigating issues; does not replace full repair when unrepaired ranges exist. |

In many modern Cassandra versions, `nodetool repair` defaults to **incremental**; requesting **full** requires `--full`. Never run one repair command on a single node and declare the whole cluster repaired: every command has a node/token-range/table/DC scope, and one node does not automatically cover the entire ring.

### 18.3. Lab-Only Commands

~~~bash
# Wait until R1/R2/R3 are all UN and verify RAM/disk/network headroom.
# Preview a full repair on the target table without modifying data:
docker compose exec -T cassandra1 nodetool repair --full --preview fault_lab events_by_device_day

# Full repair each node's primary token ranges:
# SCHEDULE sequentially; do not blast all three in parallel.
docker compose exec -T cassandra1 nodetool repair --full --partitioner-range fault_lab events_by_device_day
docker compose exec -T cassandra2 nodetool repair --full --partitioner-range fault_lab events_by_device_day
docker compose exec -T cassandra3 nodetool repair --full --partitioner-range fault_lab events_by_device_day
~~~

**`--partitioner-range` / `-pr`** limits repair to the primary token ranges of the invoking node, reducing redundant work when scheduled across nodes to cover the ring. If your organization uses a repair orchestrator managing token ranges globally, use that orchestrator instead of manually running three commands; ordering, concurrency, exclusions, and retries must all be controlled.

### 18.4. Do Not Overlook Multi-DC Repair Scope

`nodetool repair --in-local-dc` or DC-specific flags restrict participating replicas. If you need **convergence across two datacenters**, running local-only repair inside each DC may fail to meet cross-DC goals. Plan cross-DC repairs safely around version/topology constraints, WAN bandwidth, and SLOs; never pass `--force` to ignore down endpoints and claim all replicas converged.

### 18.5. Repair Cadence Is Not Optional in Operations

Periodic repair must run frequently enough that delete tombstones do not expire before lagging replicas reconcile, accounting for each table's `gc_grace_seconds` and outage/maintenance windows. Cassandra documentation gives example intervals, **not one-size-fits-all schedules**; large deployments should split into **token subranges**, stagger jobs, avoid overlaps/GC/disk saturation, and track **coverage**, not merely command counts.

## 19. Verifying Convergence: Know What Each Piece of Evidence Proves

### 19.1. Five Layers of Validation

| Layer | Evidence | Valid inference | Insufficient to conclude |
| --- | --- | --- | --- |
| 1. Membership | R3 `UN` on peers. | Node rejoined and peers treat it as up. | Every missed mutation is on R3. |
| 2. Client CL | `SELECT LOCAL_QUORUM` returns ACKed IDs. | Quorum reads return accurate data for checked partition/time. | R3 matches R1/R2. |
| 3. Hints | Handoff metrics show queued/delivered/failed. | Retained hints were processed within observed scope. | Hints were never missed/lost unobserved. |
| 4. Repair | Repair/preview/validate logs across right ranges/tables, finished. | Divergence among checked participants/ranges was compared/repaired per job. | Out-of-scope keyspaces/ranges or permanently lost data. |
| 5. Logical ledger | Every ACKed ID/value (including UPDATE/DELETE semantics) reconciled. | Business queries return accurate results on test dataset. | Storage of a specific replica without replica-isolated read validation. |

**Phrase conclusions accurately:** “Quorum reads passed all fixture partitions and full repair for `fault_lab.events_by_device_day` primary token ranges completed,” rather than writing vaguely “Cassandra reached 100% convergence” after checking one partition.

### 19.2. Reconciling the Ledger in Java or Bounded Queries

~~~java
// Pseudocode inside the test harness, NOT built-in Java Driver API:
Set<UUID> expectedAcked = ledger.ackedEventIds("DURING_R3_DOWN");
Set<UUID> actual = reader.selectEventIds(
    "device-fault-7", LocalDate.of(2026, 11, 21),
    DefaultConsistencyLevel.LOCAL_QUORUM);

Set<UUID> missing = new HashSet<>(expectedAcked);
missing.removeAll(actual);

assertTrue(missing.isEmpty(),
    "Missing ACKed event IDs: " + redactOrSummarize(missing));
~~~

**Clearly marked pseudocode**: `ledger`, `reader`, and `redactOrSummarize` are project harness helpers, not part of Java Driver. On small fixtures you can read the full partition and compare keys/values. On large tables, never run keyspace-wide `COUNT(*)` or unscoped `SELECT *` to “check convergence.” Reconcile across **bounded token/key ranges** against an audited ledger.

### 19.3. “Reading from R3” Is Not Simply Setting Contact Point R3

Crucial point for Java engineers: `new InetSocketAddress("cassandra3",9042)` only lets the driver **connect to discover topology**; the coordinator selected by the driver and the replicas queried by that coordinator can differ. `setNode(R3)` forces the coordinator but **does not by default restrict reads to R3's local storage**. If you need to verify R3's local storage independently, design explicit environment/replica isolation or use repair/validation tooling, document its impact on CL, and never mistake isolation test numbers for production availability metrics.

## 20. TTLs, Tombstones, and Why Late Repair Can Cause Zombie Data

### 20.1. Deleting While R3 Is Down

Suppose a row existed on R1/R2/R3 prior to the outage. While R3 is down:

~~~sql
-- Runnable CQL requiring the full primary key of the seeded row.
DELETE FROM fault_lab.events_by_device_day
WHERE device_id='device-7'
  AND event_day='2026-11-21'
  AND event_time='2026-11-21T08:00:00Z'
  AND event_id=123e4567-e89b-42d3-a456-426614174001;
~~~

If the delete achieves `LOCAL_QUORUM` on R1/R2, those replicas write a **tombstone** while R3 retains the **old live value**. When hint delivery or repair runs in time, the tombstone propagates to R3 to logically delete that row.

### 20.2. Counterexample When Tombstones Are Purged Too Early

~~~mermaid
sequenceDiagram
    participant R1 as R1
    participant R2 as R2
    participant R3 as R3 (down)
    R1->>R1: DELETE -> tombstone
    R2->>R2: DELETE -> tombstone
    Note over R3: Still holds old live row
    Note over R1,R2: No repair before gc grace expires
    Note over R1,R2: Compaction may purge the tombstone
    R3-->>R1: Stale replica returns with live row
    Note over R1,R3: Risk of zombie data resurrection
~~~

**`gc_grace_seconds`** is a safety buffer for tombstone/anti-entropy management, not “how long a row's TTL lasts.” If replicas are not repaired while delete metadata is retained, tombstones can be purged after grace/compaction and an old copy can resurrect during synchronization. That is one reason repairs must run **frequently relative to gc grace**, and extended outages require runbook handling.

### 20.3. Safe TTL and Delete Testing

| Case | What to measure | What NOT to do |
| --- | --- | --- |
| Write with `USING TTL`, R3 down. | Row lifetime, hints/repair, TTL reconciliation. | Never expect hint replay to reset TTL from replay time. |
| Delete during outage. | Tombstone propagates via handoff/repair; reads reflect deleted state at CL. | Never treat an empty `SELECT` from R1/R2 as proof R3 deleted the row. |
| Node down near grace limit. | Alert on repair deadline/lag; decide recovery vs replace. | Never slash grace to tiny values to reproduce bugs in production. |
| Repair too late. | Flag data-risk; evaluate backup/restore and full repair. | Never claim repair can restore completely purged tombstone history. |

Always use a **separate fixture** for tombstone/TTL testing, because the immutable-event ledger in earlier tests asserts “every ACKed insert must remain alive.” Do not apply that same assertion to intentionally deleted or expired records.

## 21. Multi-Datacenter: A Local Outage Does Not Prove Cross-Region Convergence

Suppose:

~~~sql
CREATE KEYSPACE IF NOT EXISTS fault_lab_multidc
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

### 21.1. `LOCAL_QUORUM` vs `QUORUM`

| CL | Requirement | Impact when the remote DC temporarily disconnects |
| --- | --- | --- |
| `LOCAL_ONE` | One full replica in local DC. | Succeeds locally while remote lags behind. |
| `LOCAL_QUORUM` | Majority of full replicas in **local DC** (2/3 in example). | Needs no remote quorum ACK, so remote DC can lag. |
| `QUORUM` | Majority of total full replicas across keyspace per operation (4 out of 6 full replicas). | May require WAN/remote replicas, changing local latency and availability. |
| `EACH_QUORUM` (write) | Majority of full replicas **in every DC**. | Fails quickly if either DC lacks quorum; does not replace persistence/repair plans. |

CL defines **required responses**, not whether hints get created or whether all replicas converge right away. Multi-DC tests must verify **DC-aware routing**, WAN latency, roles/secrets/certs, failure detectors, and DC-specific hint configs.

### 21.2. `hinted_handoff_disabled_datacenters`

Some organizations disable hinted handoff toward remote DCs for bandwidth or operational policy reasons. This makes **cross-DC anti-entropy repair** even more critical: `LOCAL_QUORUM` in `dc1` keeps ACKing writes while parts of `dc2` miss mutations.

**Do not** assume `nodetool repair --in-local-dc` inside each DC automatically synchronizes data between two DCs: local-only repair scopes can miss cross-DC divergence. Repair plans must account for **all DCs and ranges requiring convergence**.

## 22. Two Replicas Down, Lost Coordinator, and Unknown Outcomes: Tests Must Classify Them

### 22.1. Both R1 and R2 Down Under RF=3

With only one replica alive, a `LOCAL_QUORUM` write **cannot gather two full replica ACKs**. Driver or coordinator can throw `Unavailable` or timeout depending on failure detection timing and network state. Tests must separate **insufficient live replicas** from I/O or client timeouts.

### 22.2. Coordinator Crashes Mid-Request

If the coordinator forwarded the mutation to some replicas and then stopped before returning a response:

~~~text
Client sees: timeout / connection lost
Replica state: one or more replicas may have applied the write
Hint state   : may never have been stored, or lives on the down coordinator
Outcome     : unknown, DO NOT assume definitely failed
~~~

The client needs **stable primary keys/event IDs**, proper idempotent retries, and reconciliation. On resume, never mint a new random event ID for the same logical operation simply because no ACK came back. Never apply plain-insert retry assumptions to `counter` updates, conditional side effects, or mixed batches.

### 22.3. `ANY` Is Not a Workaround to Bypass Quorum

`ANY` has special write-only semantics and can return an ACK purely via a hint under specific conditions **even when no full replica is readable**. If your interface requires read-your-writes or quorum durability, never silently downgrade from `LOCAL_QUORUM` to `ANY`; doing so **alters the consistency contract**.

### 22.4. Extended Fault Matrix

| Fault | Expected CL behavior | Observed behavior to check |
| --- | --- | --- |
| One full replica R3 down, RF3. | `LOCAL_QUORUM` can still succeed. | Hints can be created and replayed. |
| Two full replicas down, RF3. | `LOCAL_QUORUM` lacks ACKs. | Unavailable/timeout per detector; no “fake success.” |
| Coordinator down, replicas healthy. | Driver reroutes/retries per policy. | Unknown write outcomes, idempotency, retries/timeouts. |
| Hints disabled or outside window. | Quorum ACKs unchanged. | R3 may stay behind until repair runs. |
| Target up but disk full. | Handoff/repair may fail or throttle. | Rising errors, stuck pending hints, storage metrics. |
| One-way network partition. | Depends on path and failure detection. | Coordinator/replica asymmetry, retry amplification. |
| Remote DC unreachable. | Local `LOCAL_QUORUM` can continue. | Cross-DC divergence and repair coverage. |

## 23. Organizing Java Integration/Fault Tests: Separating Control from Data

A test suite should separate **(a) mutation source and ledger**, **(b) a fault controller authorized to stop/start nodes**, **(c) client reader**, and **(d) validation/repair**. Never embed `docker compose stop` inside a production service method or let CI point at production instead of a test cluster.

### 23.1. Contract for a Scoped Test Harness

~~~java
// Design PSEUDOCODE for the harness; these interfaces belong to the APPLICATION,
// NOT built-in Apache Cassandra Java Driver classes.
interface FaultController {
    void assertIsDedicatedTestCluster();
    void stopReplica(String nodeId);
    void startReplica(String nodeId);
    boolean awaitNodeDown(String nodeId, java.time.Duration timeout);
    boolean awaitNodeUp(String nodeId, java.time.Duration timeout);
    boolean awaitHandoffIdle(java.time.Duration timeout);
    void ensureRestored();
}

interface EventLedger {
    void recordAttempt(String runId, java.util.UUID eventId);
    void recordAck(String runId, java.util.UUID eventId);
    void recordUnknown(String runId, java.util.UUID eventId, Throwable error);
    java.util.Set<java.util.UUID> ackedIds(String runId);
}

interface ReplicaValidation {
    void assertAckedIdsVisibleAtQuorum(
        String runId, java.util.Set<java.util.UUID> expected);
    void recordRepairScopeAndResult(String runId);
}
~~~

**Design intent:** `FaultController` must enforce a **cluster ID/DC allowlist and test lease**, bounded timeouts, guaranteed cleanup, and zero path to production. `EventLedger` should be durable across the test run so if the runner dies mid-outage you still know which mutations were ACKed; `ReplicaValidation` must never treat a single `SELECT LOCAL_QUORUM` as proof that all replicas converged.

### 23.2. JUnit Pattern with Cleanup Even When Assertions Fail

~~~java
// Test orchestration PSEUDOCODE using project harness adapters.
// Do not copy directly without implementing the interfaces above.
@Test
@Tag("destructive-isolated-cluster")
void oneReplicaOutageThenRecoveryNeedsConvergenceEvidence() {
    String runId = "fault-run-" + UUID.randomUUID();
    faults.assertIsDedicatedTestCluster();

    try {
        assertTrue(topology.allThreeReplicasUp());
        workload.writeBaseline(runId, 20);

        faults.stopReplica("R3");
        assertTrue(faults.awaitNodeDown(
            "R3", Duration.ofSeconds(60)));

        workload.writeBoundedQuorumEvents(runId, 100, ledger);
        // Do not assert all 100 succeeded: inspect accepted/failed/unknown.
        assertTrue(ledger.ackedIds(runId).size() > 0);

        faults.startReplica("R3");
        assertTrue(faults.awaitNodeUp(
            "R3", Duration.ofMinutes(5)));

        boolean hintsDrained = faults.awaitHandoffIdle(
            Duration.ofMinutes(10));
        metrics.recordHintDrainResult(runId, hintsDrained);

        validation.assertAckedIdsVisibleAtQuorum(
            runId, ledger.ackedIds(runId));
        // Anti-entropy preview/full repair and convergence scope
        // executed by a dedicated runbook/runner, recording results.
        validation.recordRepairScopeAndResult(runId);
    } finally {
        // Runs even on exceptions, escalating to an operator if restoration fails.
        faults.ensureRestored();
    }
}
~~~

`faults`, `topology`, `workload`, `ledger`, `metrics`, and `validation` are objects **supplied by the project's test framework**; this is an intentional orchestration pattern, **not a standalone compilable JUnit file**. Its goal is highlighting the sequence **stop → awaitDown → boundedWrites → start → awaitUp → handoff → ledger/repair validation**, paired with `finally` so failed CI runs never leave a node down.

### 23.3. Conditions for Safe Automated Fault Tests

| Check | Why it is mandatory |
| --- | --- |
| Cluster ID = dedicated test cluster, no production hosts allowlisted. | Prevents the fault injector from stopping a real node by mistake. |
| R1/R2/R3 all `UN` before start; RF3/DC metadata verified. | Preserves baseline comparability and the natural replica set. |
| Ledger records immediately on ACK; unknowns tracked separately. | Prevents false data-loss alerts from timeouts or new retry IDs. |
| `awaitDown`/`awaitUp` have deadlines and logs. | Prevents infinite hangs or measuring at the wrong phase boundary. |
| Cleanup/finalizer always restores R3 and handoff config. | Avoids leaving the test cluster degraded for subsequent cases. |
| Repair jobs run only when all required participants are up. | Avoids false confidence from skipping down endpoints. |
| Results tagged with version/image/config hash. | Enables reproducibility and build-to-build comparison. |

## 24. Load Methodology: Baseline, Fault, Recovery, Post-Recovery

### 24.1. Four Phases Sharing the Same Query Shape

| Phase | Conditions | Goal | What to record |
| --- | --- | --- | --- |
| **A — Baseline** | 3 `UN` replicas, negligible hint backlog. | Reference latency/throughput/correctness. | Arrival rate, achieved throughput, CL, errors, p95/p99, resources. |
| **B — Outage** | R3 down, RF3 `LOCAL_QUORUM`, hinting enabled. | Availability under single fault. | Quorum success rate, timeouts, hint creation, R1/R2 resources. |
| **C — Recovery** | R3 `UN`, handoff/repair may run. | Catch-up duration and online traffic impact. | Backlog bytes, replay rate, repair progress, p99, disk/GC. |
| **D — Stabilized** | Handoff/repair jobs completed per defined scope. | Verify post-incident data correctness and SLOs. | ACKed ledger match, full-range evidence, p99, errors. |

**Do not change CQL, compaction settings, row size, client concurrency, datacenter, or CL** between baseline and outage if you want to isolate the effect of replica failure. To test multiple load levels, execute **separate runs** with a defined sequence and fixture reset.

### 24.2. Open-Loop vs Closed-Loop Workloads

- **Closed-loop**: a client waits for the previous request to finish before sending the next. When latency climbs, offered rate drops automatically, masking backend saturation.
- **Open-loop / fixed arrival rate**: the workload dispatches requests on a target schedule; this reflects real arrival pressure better, but **must enforce bounded queues/in-flight limits and stop criteria** to avoid losing cluster control.
- **Coordinated omission**: if the load generator skips recording intervals while blocked waiting for slow responses, latency histograms look artificially optimistic. Use load tools/reporting adjusted for coordinated omission, and report both achieved rate and rejected/queued counts.

Never report “10,000 requests/s” when that was only the **generator's target rate** while only 6,000 requests/s actually completed and 4,000 were queued or rejected. Always report **offered, accepted, completed, timed-out, and rejected** separately.

### 24.3. Little's Law and In-Flight Budget

In a relatively steady state:

~~~text
L ≈ lambda × W
  L       : average number of in-flight requests
  lambda  : completed throughput per second
  W       : average request residence time (seconds)

Example at lambda=500 requests/s:
  mean W=0.040s => L≈20 requests
  mean W=0.200s => L≈100 requests
~~~

If an outage raises mean latency 5x at the same arrival rate, the in-flight concurrency needed to sustain that rate rises proportionally. Once the service saturates, steady-state equations break down; **never plug p99 into `W`** in the formula. Use actual driver/app metrics to size admission gates rather than spawning unbounded futures.

### 24.4. Do Not Change the Consistency Contract for Prettier Numbers

`LOCAL_QUORUM` on RF3 requires a different replica response count than `LOCAL_ONE`. If baseline runs `LOCAL_ONE` and outage runs `LOCAL_QUORUM`, p99 latency is no longer comparing the same workload. You can benchmark both CLs, but **record them as two separate test series** and document the correctness/availability trade-off.

### 24.5. Measure Tail Latency Rather Than Just the Mean

| Metric | Reason |
| --- | --- |
| `write_latency_p50/p95/p99` per phase/CL. | Client SLOs and tails when coordinators/replicas slow down. |
| `read_latency_p95/p99` on queried partitions. | Confirms quorums/read path remain responsive. |
| `hint_replay_duration`/bytes/s. | How long R3 takes to catch up via hints. |
| `repair_duration`/bytes streamed/ranges covered. | Repair cost and convergence progress. |
| `read/write timeout/unavailable` by type. | Separates overload, insufficient CL, and error handling. |
| `client queue/in-flight/driver retries`. | Detects backpressure and retry storms. |
| JVM heap/GC, disk await/free, network, compaction. | Distinguishes client bottlenecks from storage bottlenecks. |
| Ledger mismatch count/ID hashes. | Proves data correctness, not just speed. |

## 25. Estimating Hint Backlog and Replay Time

Suppose a replica misses mutations steadily throughout an outage. A rough approximation for **capacity budgeting**:

~~~text
estimated_hint_bytes ≈
  missed_mutations_per_sec
  × average_serialized_mutation_bytes
  × outage_seconds
  × hint_overhead_factor

replay_time_lower_bound ≈
  hint_bytes_to_deliver / effective_delivery_bytes_per_sec
~~~

This is **not** an exact Cassandra formula: coordinator/token distribution, LZ4 compression, coalescing, batching, hint eligibility, windows, node discovery, parallelism, live read/write load, and network congestion all alter actual numbers.

### 25.1. Quantitative Example

~~~text
Illustrative assumptions for study:
  1,000 mutations/sec missed by R3
  1 KiB average serialized hint (excluding overhead)
  10-minute outage = 600 seconds
  uncompressed estimate = 1,000 × 1 KiB × 600
                        ≈ 586 MiB

If effective replay is only 2 MiB/s:
  586 MiB / 2 MiB/s ≈ 293 seconds ~ 4.9 minutes
  (excluding queuing/startup/retries/compaction)
~~~

**All numbers are purely illustrative.** Actual hint streams can take much longer depending on per-delivery-thread throttles, node count, or network/target-disk saturation. Hints are also spread across multiple coordinators, so 0 bytes on one node does not mean 0 across the cluster.

### 25.2. What Happens If Recovery Falls Behind?

When R3 returns and ingests hints, it simultaneously handles client reads/writes, mutation replay, and compaction/flushes. If **new incoming work rate > total processing capacity**, backlog or p99 may fail to drop. Mitigations:

- Shed **batch/backfill/offline analytical traffic** to protect online latency.
- Check disk headroom, GC, and stream throughput before increasing handoff throttle.
- Set a **recovery deadline** and alert if backlog stops shrinking relative to baseline.
- If the hint window expired or hints were lost, switch to a **repair/replace recovery plan** instead of waiting endlessly on hints.
- Check for disk failures/corruption or missing replicas before repairing; never treat repair as an automatic cure for dead disks.

## 26. Dashboards and Layered Diagnostic Commands

### 26.1. Correlate Three Timelines: Application, Hints, and Repair

~~~mermaid
flowchart TD
    A["Fault markers UTC: R3 down/up"] --> B["Client: accepted, p95/p99, errors"]
    A --> C["Coordinators: hints created/pending/delivery"]
    A --> D["R3: disk/GC/compaction, hint replay"]
    B --> E["Same UTC window + query name + CL"]
    C --> E
    D --> E
    E --> F["Repair: token ranges, Merkle/streaming, finished/failed"]
    F --> G["Ledger: ACKed IDs and payloads, mutation/delete states"]
~~~

Every dashboard needs **fault markers** (`start/stop/startup/handoff_begin/handoff_end/repair_begin/repair_end`) and the deployment version. Without aligned time windows, it is easy to blame p99 spikes on hinted handoff when a compaction or GC pause actually started earlier.

### 26.2. Observational Data Sources

| Layer | What to measure | What NOT to infer |
| --- | --- | --- |
| **Java API/worker** | Offered/achieved RPS, ACK/timeout/unavailable, retries, queue, p95/p99, pending futures. | `HTTP 200` does not prove all replicas persisted the write. |
| **Driver 4.x** | Node/coordinator distribution, request latency, in-flight, error classes, retry/speculative attempts if enabled. | `executeAsync` calls do not equal server RPC count under retries. |
| **Hint service on R1/R2** | Hints created, pending, dispatched, failed, oldest age, delivery duration per metric version. | `statushandoff` or a zero backlog does not prove every mutation was hinted. |
| **Replica R3** | Hint receive/replay, SSTable writes, compaction/flush, disk free, CPU/GC. | R3 `UN` does not prove byte/cell parity with R1/R2. |
| **Repair** | Ranges/jobs scheduled/completed/failed, bytes streamed, preview/validate results, participant scope. | Repairing one node/table does not mean the whole cluster or all tables were compared. |
| **Data/ledger** | Set of expected ACKed IDs, values, deleted vs live, unknown outcomes. | Matching `COUNT` does not prove identical row IDs or values. |

### 26.3. Common Operational Commands

~~~bash
# On nodes with verified permissions, following the runbook:
nodetool status
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats fault_lab.events_by_device_day
nodetool statushandoff
nodetool getmaxhintwindow
~~~

- `status`: node/rack/DC/membership, not proof of data convergence.
- `netstats`: stream/network operation state per version, useful during repair/streaming.
- `tpstats`: pending/completed/dropped tasks showing queue pressure; not “which cells were read.”
- `compactionstats`: I/O pressure from compaction; correlate with disk latency/GC.
- `proxyhistograms`: coordinator request latency distribution on the node; excludes Java/HTTP app processing.
- `tablestats`: per-table statistics, SSTables, tombstones, and local data per version; **does not compare cells across replicas**.
- `getmaxhintwindow`: available only in supporting versions (4.0+); several settings changed names across releases.

**CQL roles do not grant `nodetool` permissions**: `nodetool` relies on separate JMX/OS/security controls. Never leave JMX passwords in shell history or logs, and never expose JMX ports publicly for testing.

### 26.4. Selective Use of CQL Tracing

~~~sql
-- cqlsh lab command; do not enable tracing across all production traffic.
CONSISTENCY LOCAL_QUORUM;
TRACING ON;

SELECT event_time,event_id,event_type
FROM fault_lab.events_by_device_day
WHERE device_id='device-fault-7'
  AND event_day='2026-11-21'
LIMIT 100;

TRACING OFF;
~~~

Traces reveal coordinator and replica read steps for a sampled statement, yet **do not replace** hint replay metrics, repair ranges, disk/GC stats, or ledger reconciliation. Restrict tracing to small samples when the system is under load.

## 27. Runbook When a Replica Returns Without Data Convergence

### 27.1. Symptoms and Initial Diagnosis

| Symptom | Plausible hypothesis | Verify before acting |
| --- | --- | --- |
| R3 `UN`, app reading `LOCAL_ONE` intermittently sees stale values. | One replica still lags or coordinator picks different read paths. | Query/CL/coordinator/range, hint/repair logs; never treat `UN` as enough. |
| R3 returns, pending hints do not shrink. | Delivery throttle, network, disk, overloaded node, paused/disabled handoff. | `statushandoff`, hint metrics, logs, disk free/GC, DC exclusions. |
| Hint queue empty yet repair preview reports differences. | Missed mutations had no hints, hints lost/expired window, wrong token ranges. | Effective hint config, outage duration, preview scope/participants. |
| `LOCAL_QUORUM` fails while R3 is down. | R1/R2 unhealthy/wrong CL/DC or coordinator routing failure. | `nodetool status`, driver errors, CL, CPU/GC/disk/network. |
| `LOCAL_QUORUM` read looks right yet checker flags “R3 stale.” | Quorum can read R1/R2; replica checker may observe different storage state. | Confirm checker genuinely reads R3 storage; run preview/full repair. |
| Repair drags on, streaming rises, p99 degrades. | Network/disk/compaction contention, too many concurrent ranges/jobs. | `netstats`, repair logs, disk await, GC, load plan and throttles. |
| Deleted rows reappear after a very long outage. | Tombstones no longer suppress stale replica (zombie risk). | gc grace, repair history, compaction, backups, CQL timestamps. |
| Client insert timeouts lead to unexpected row count growth. | Retries generate new UUID/timestamps or double-enqueue. | Stable primary key, ledger operation IDs, driver retry policy. |
| Multi-DC data diverges after local-only repair. | Repair scope excluded cross-DC differences. | DC participants and topology strategy in repair plan. |

### 27.2. Response Order During a Real Incident

1. **Assess safety:** how many healthy full replicas remain in each DC, disk/network/GC health, customer impact, risk of a second failure?
2. **Halt fault injection or maintenance causing the disruption**; do not keep pushing test load to “double-check” while the cluster is degraded.
3. **Shed load selectively** from backfill/analytics jobs without dropping mandatory events if pipelines rely on durable queues/ACKs.
4. **Restore the node or network link using the approved runbook**; never wipe data directories or alter host ID/tokens ad hoc.
5. **Observe hints and resource pressure** on both coordinators and target; check windows, disabled DCs, and delivery errors.
6. **Classify unknown writes** in the client ledger; never retry with newly minted event IDs while outcomes remain uncertain.
7. **Scope required anti-entropy repair:** keyspace/table/ranges/DC, preview/validate as appropriate, replication health, disk headroom, and gc grace.
8. **Run repair per approved schedule/rate**, avoiding duplicate jobs or cluster-wide simultaneous full repairs.
9. **Verify postconditions:** membership, ACKed IDs/values, hint/repair evidence, and p99/errors/GC/disk back within SLO.
10. **Close the incident** after documenting coverage/known gaps, preventive actions, and impacted customers (if any).

### 27.3. When `gc_grace_seconds` Has Already Elapsed

Do not simply run `repair --full` and declare zombie risk gone. Inspect **tombstone retention, last successful repair coverage, stale replica condition, backup/restore options, and hard-deleted datasets**. You may need a **rebuild/restore/reconciliation plan against an external source of truth**. This requires careful DBA/SRE review and approval, not a “single silver-bullet command.”

## 28. Fault/Load Test Matrix by Proof Objective

### 28.1. Zero-Fault and Single-Fault Cases

| Test ID | Fixture/fault | Valid assertions | Invalid assumptions |
| --- | --- | --- | --- |
| F01 | RF3, all three `UN`, `LOCAL_QUORUM`. | Baseline ACKed ledger = bounded reads; p99/throughput recorded. | Cluster can survive arbitrary faults. |
| F02 | Stop R3, wait for peers to mark down. | Node status matches fault marker; quorum writes can succeed. | Every single request immediately has zero errors. |
| F03 | Write 100 stable IDs during outage. | Full ACK/fail/unknown ledger; `LOCAL_QUORUM` successes read back. | `100/100` already reside on R3. |
| F04 | Restart original R3 volume. | R3 `UN`, expected host ID/token; not accidentally bootstrapped. | All hints already finished replaying. |
| F05 | Handoff enabled + short outage. | Hint metrics/lag, bounded drain wait, post-check results. | Every table/range is repaired. |
| F06 | Handoff disabled on coordinators while R3 down. | Quorum ACKs still possible; R3 lacks all missed writes just by coming up. | Re-enabling handoff recreates missing hints. |
| F07 | Short hint window, then writes outside window. | Distinguish pre- vs post-window events, metrics/handoff coverage. | All events were hinted. |
| F08 | R3 healthy, run full preview. | Inspect estimated differences and participants/scope; nothing streamed. | Preview repaired the data. |
| F09 | Full repair `--partitioner-range` across all nodes. | Job completed/ranges covered/streaming/verification. | Unselected tables were also repaired. |
| F10 | Post-repair queries against ledger. | Expected surviving ACKed IDs/values verified. | Unknown writes definitely succeeded or failed. |

### 28.2. Cases Requiring Specialized Environments

| Test ID | Fault | Key attention points |
| --- | --- | --- |
| F11 | Two full replicas down, RF3. | `LOCAL_QUORUM` lacks replicas; never downgrade CL to mask errors. |
| F12 | Coordinator loses connection after forwarding write. | Unknown outcome, stable key, idempotent retry/reconciliation. |
| F13 | R3 down during DELETE/TTL. | Tombstone propagation and gc grace; isolate into separate fixture. |
| F14 | R3 down near or past gc grace. | **Long-lived lab only** with specialists; risk/restore plan required, never force prod compaction to purge tombstones. |
| F15 | Network partition between dc1 and dc2. | Cross-DC hint/repair/CL semantics; WAN latency. |
| F16 | Oversized handoff saturates R3 disk on recovery. | Bounded replay/traffic, p99/GC, abort/slowdown criteria. |
| F17 | Hints lost due to coordinator disk loss. | Anti-entropy restoration; do not confuse with a brief target restart. |
| F18 | Repair job fails mid-token-ranges. | Track coverage and retry per range; never mark complete. |
| F19 | Node replacement instead of same-node return. | Bootstrap/streaming/different host ID; requires separate runbook. |
| F20 | Repeated fault injections. | Verify zero hidden hint backlog, post-run health/p99, no resource leaks. |

### 28.3. Publishable Pass/Fail Criteria

**Pass availability** when request success/failure counts under a single fault match RF/CL and **agreed thresholds** with no uncontrolled session loss or out-of-bounds overload. **Pass correctness** when ACKed writes in the fixture (excluding intentionally deleted/TTL-expired rows) match on ID and value, with unknown writes reported separately. **Pass recovery** when hint/repair jobs show completion evidence for the right token/table/DC scope, performance returns within baseline thresholds, and zero mismatches remain in the verified scope.

**Fail** if the only evidence is a single `SELECT LOCAL_QUORUM` returning 200 or `nodetool status` showing three `UN` rows.

## 29. Common Anti-Patterns When Testing a Missing Replica

| Anti-pattern | Why it is wrong | Replace with |
| --- | --- | --- |
| RF3 on one node, then stop the container. | Lacks two real replicas to form quorum. | Three full test replicas with proper NTS/DC. |
| Stopping a node outside the natural replica set. | Creates no missed mutations for tested partition. | Verify token placement before injecting fault. |
| Testing only `LOCAL_ONE` and declaring `LOCAL_QUORUM` passed. | Different CL availability/correctness contracts. | Test with production's actual CL. |
| Node `UN` = synchronized data. | Membership does not measure per-range data parity. | Handoff/repair validation + ledger. |
| Hints = permanent backup. | Hints are best-effort and bounded by window/storage/failures. | Repair cadence + backup/reconciliation. |
| Waiting 3 real hours to “hit repair time” in production. | Intentional outage destroys fault tolerance with high risk. | Short-window lab setup and approved runbook. |
| `truncatehints` to free disk during huge backlog. | Drops pending mutations, worsening divergence. | Throttle load/replay and execute repair plan; never wipe blindly. |
| Raising hint throttle unboundedly. | Can saturate target disk/GC/network. | Benchmark/throttle with SLOs and safety margins. |
| Single `SELECT QUORUM` proves R3 has the data. | May have read from the two healthy replicas. | Per-replica scope/repair evidence. |
| Pinning coordinator R3 = reading storage solely from R3. | Coordinator can forward reads to other replicas. | Proper replica isolation or validation tooling. |
| Running full repair in parallel on all nodes. | Redundant work and I/O/CPU/network contention. | Staggered primary ranges/subranges with controlled concurrency. |
| Re-enabling hints after disabling and expecting missed writes to replay. | Non-existent hints cannot materialize retroactively. | Anti-entropy repair and verification. |
| `--in-local-dc` handles all multi-DC divergence. | May miss replicas in other DCs. | Cross-DC repair topology plan. |
| Using raw row counts to prove row correctness. | Missing one ID plus adding another preserves count. | Ledger of full PK IDs + value digests. |
| Timeout = no mutation applied. | Replicas may have applied write prior to failure. | Unknown outcome handling, stable keys. |
| Generating fresh UUID on retry. | Creates duplicate logical events. | Reuse full primary key and idempotency contract. |
| Downgrading CL to `ANY` so all writes return 200. | Silently alters durability/read-visibility guarantees. | Keep approved CL, surface overload/unavailable clearly. |
| Shrinking `gc_grace_seconds` to purge tombstones faster. | Creates zombie data risk before replicas repair. | Proper retention and repair cadence. |
| Keyspace-wide `COUNT(*)` under load for verification. | Heavy scan overloads the test cluster itself. | Bounded queries/ledger/token scopes. |
| Leaving handoff disabled or fault active after test failure. | Leaves test cluster degraded and pollutes subsequent runs. | `finally`/teardown/alerts and verified restoration. |

## 30. Practice Exercises with Answers

**Exercise 1.** RF=3 in a single DC, client uses `LOCAL_QUORUM`. R3 is down; R1/R2 are healthy. Can writes succeed, and how many ACKs are required?

**Answer:** **Yes**, provided **two full replica ACKs** arrive from the local DC. This does not prove R3 received the mutations; hinted handoff/repair may be needed for R3 to catch up.

**Exercise 2.** Why is the coordinator not necessarily one of the key's natural replicas?

**Answer:** The coordinator is the node **receiving the CQL request** and orchestrating it; natural replicas are determined by the **partition key's token + replication strategy/topology**. Driver load balancing can pick a coordinator that does not own the key, and that coordinator routes to the replicas.

**Exercise 3.** Node R3 restarts and reports `UN`. Can we declare the data converged?

**Answer:** **No.** `UN` proves membership/availability, not that all hints delivered, repair compared all ranges, or all IDs/values match.

**Exercise 4.** A `SELECT LOCAL_QUORUM` returns all 100 event IDs after the outage. Does that prove R3 holds all 100 IDs?

**Answer:** **Not yet.** Quorum reads can be satisfied by R1/R2. You need hint/repair validation and a **properly scoped replica verification method** before claiming R3 storage caught up.

**Exercise 5.** How does hinted handoff differ from anti-entropy repair in knowing which data is missing?

**Answer:** Hints rely on mutations the coordinator knows **failed to reach a target replica** while hinting was eligible, caching and replaying them later. Repair compares **replica datasets across shared token ranges** via Merkle trees/streaming regardless of whether a hint was ever stored.

**Exercise 6.** An outage lasts longer than `max_hint_window`. Are all previously stored hints immediately deleted at that timestamp?

**Answer:** **No.** The window typically governs **how long new hints continue to be created** for a down endpoint, not a promise that existing hints purge at that exact instant. Check effective config and hint delivery state.

**Exercise 7.** While R3 is down, some hints reside on R1 and others on R2. Is seeing a 0 backlog on R1 alone sufficient?

**Answer:** **No.** You must inspect **all coordinators capable of storing hints**, delivery/failure metrics, and repair coverage; even a 0 backlog does not prove un-hinted mutations converged.

**Exercise 8.** Why does running `disablehandoff` on both R1 and R2 before the outage help demonstrate the need for repair?

**Answer:** While R3 is down, writes still succeed at `LOCAL_QUORUM` on R1/R2 yet **zero hints are recorded** for missed writes. Re-enabling handoff when R3 returns **cannot regenerate old hints**, leaving anti-entropy repair as the reconciliation mechanism.

**Exercise 9.** Is using `nodetool truncatehints` safe to relieve a nearly full disk in production?

**Answer:** **No.** It drops undelivered hints and widens divergence. Shed load/throttle replay, inspect disk headroom, and execute an approved repair plan instead of blindly wiping hints.

**Exercise 10.** When two full replicas are down in RF3, can a `LOCAL_QUORUM` write still achieve quorum?

**Answer:** **No.** A single remaining full replica cannot form a 2/3 quorum. The driver returns `Unavailable` or timeout depending on failure detection/network, and CL must not be silently downgraded just to return 200.

**Exercise 11.** `LOCAL_ONE` occasionally returns stale reads after R3 comes back. Must this be a Java Driver bug?

**Answer:** **No.** `LOCAL_ONE` only queries one replica. If it lands on a replica missing writes, it can return stale state. Investigate CL, replica divergence, hints, repair, and routing before blaming the driver.

**Exercise 12.** Why is pinning the Java statement coordinator to R3 via `setNode(R3)` insufficient to prove you are reading data strictly from R3?

**Answer:** The coordinator receiving the request can still forward the read to natural replicas per CL and read-path logic. Proving single-node storage contents requires tests that **actually isolate/observe the queried replica** or anti-entropy validation, not merely contact point/coordinator pinning.

**Exercise 13.** Does `nodetool repair --preview` stream data to fix differences?

**Answer:** **No.** Preview builds/compares estimates of streaming needed (incurring Merkle tree build cost) **without performing repair streaming**. Fixing mismatches requires an actual properly scoped repair.

**Exercise 14.** Why does running a single `nodetool repair --full` on one node not necessarily cover the whole ring?

**Answer:** It repairs token ranges associated with the **invoked node**, rather than automatically orchestrating every node in the cluster. Full-ring coverage requires scheduling across needed nodes/primary ranges or using an orchestrator with coverage tracking.

**Exercise 15.** When scheduling `nodetool repair --full --partitioner-range` across nodes, what is the benefit of `--partitioner-range`?

**Answer:** It restricts repair to the node's **primary token ranges** to minimize duplicate work; run across the necessary nodes/ranges for full coverage without launching all nodes simultaneously. Monitor failed ranges/retries and version-specific behavior.

**Exercise 16.** How do default incremental repair and full repair differ?

**Answer:** Incremental processes **unrepaired data** since prior matching incremental repairs, saving I/O when run regularly; full compares all data within the assigned token ranges. When prolonged drift or corruption is suspected, incremental alone may not suffice; run full per policy.

**Exercise 17.** Why shouldn't you raise the hint delivery throttle infinitely once R3 comes back?

**Answer:** Hint replay contends for disk, CPU, GC, and network with reads/writes, compaction, and repair. Over-throttling upward can worsen p99 and timeouts; watch target headroom and SLOs and adjust within stop criteria.

**Exercise 18.** A client writes events using a fresh UUID on every retry after `WriteTimeout`. What goes wrong in the ledger?

**Answer:** An earlier attempt may already have landed on replicas; retrying with a **new full primary key** creates a duplicate logical event. Keep `eventId,eventTime,partition` stable and classify timeouts as **unknown** until reconciled.

**Exercise 19.** Partition `COUNT(*)` is 100 before the outage and 100 after repair. Does that prove correctness?

**Answer:** **No.** ID A could be missing while ID B was added or payloads changed. Reconcile **full expected primary keys/operation IDs and value hashes**, accounting for deletes/TTLs per contract.

**Exercise 20.** R3 misses a DELETE while R1/R2 record tombstones. If R3 stays down past gc grace and tombstones get purged before repair, what is the risk?

**Answer:** **Zombie data**: the stale replica still holds the live row while other replicas lack tombstones to suppress it, allowing deleted data to resurrect. Schedule repair before gc grace and maintain a restore/reconciliation plan if exceeded.

**Exercise 21.** With `dc1:3,dc2:3`, how many ACKs from `dc2` does a `LOCAL_QUORUM` write from `dc1` require?

**Answer:** **None required from `dc2`** for local quorum in `dc1`; it needs two full replica ACKs in `dc1`. Remote DC can lag, requiring a multi-DC hint/repair plan and avoiding confusion between `LOCAL_QUORUM` and `EACH_QUORUM`.

**Exercise 22.** Should we run `nodetool repair --in-local-dc` in each DC and assume all cross-DC differences are repaired?

**Answer:** **Not by default.** Depending on repair scope/participants, local-only repairs can leave cross-DC divergence untouched. Plan cross-DC repair around WAN bandwidth, CL, and coverage.

**Exercise 23.** While R3 is down, `LOCAL_QUORUM` writes ACK 90/100 requests and 10 time out. Can we conclude the 10 events were definitely not written?

**Answer:** **No.** A timeout does not guarantee no replica received the mutation; some writes may already have applied. Mark them **unknown** in the ledger and reconcile via stable keys rather than assuming ACKed or definitely failed.

**Exercise 24.** Why can a closed-loop load tester make an outage look “mild”?

**Answer:** As latency rises, closed-loop clients naturally send fewer requests per second, reducing offered load and masking queue saturation. Report **offered vs achieved throughput, p99, and rejected/timeouts**, and consider bounded open-loop testing without coordinated omission.

**Exercise 25.** At `500 requests/s`, mean latency rises from `40 ms` to `200 ms`. Under Little's Law in steady state, what does average in-flight concurrency grow from and to?

**Answer:** `L=λW`: from `500×0.040=20` up to `500×0.200=100` requests. This is a steady-state approximation; never substitute p99 for mean or assume an overloaded system remains in steady state.

**Exercise 26.** R3 is `UN`, yet hint backlogs aren't draining and R3's disk await is high. What should you do next?

**Answer:** Inspect handoff enabled/paused state, hint delivery errors/throttles, disk/GC/compaction, network, and live load; **do not** infer convergence from `UN` or raise throttles blindly. Shed load selectively and prepare a repair plan if hints fall short.

**Exercise 27.** Why is stopping R3 and wiping its Docker volume before restart a different test?

**Answer:** Deleting the volume destroys local data, can alter node identity/tokens, and turns the scenario into **replacement/bootstrap/data-loss recovery** instead of “same replica returns and receives hints.” It demands its own runbook and backup/streaming validation.

**Exercise 28.** A team runs fault tests without recording UTC markers or saving version/config info. Why is comparing two runs difficult?

**Answer:** You cannot correlate p99 shifts with down/up/handoff/repair timestamps or tell which settings/versions changed. Always save **fault markers, Cassandra/driver versions, CL/RF, row bytes, rates, and config hashes**.

**Exercise 29.** Can hint replay act as a long-term backup instead of periodic repair?

**Answer:** **No.** Hints are best-effort, bounded by windows, storage, and node availability, and can go missing. Anti-entropy repair + backup/restore on a schedule aligned with gc grace remain operationally mandatory.

**Exercise 30.** A test checks only `nodetool status=UN` and HTTP 200 responses. What minimum types of evidence are missing?

**Answer:** It lacks an **ACKed vs unknown** ledger, expected ID/value reconciliation within query scope, hint/repair metrics with token/DC coverage, p95/p99/resource telemetry, and cleanup/restoration evidence—therefore failing to prove correctness or recovery.

## 31. Handover Checklist and Decision Flow

~~~text
CONTEXT / TEST CLUSTER
[ ] Cluster ID and environment confirmed as approved test/staging.
[ ] Cassandra/JDK/Driver/config versions pinned; no real secrets used.
[ ] RF3 full replicas in dc1 across three real nodes with verified rack/token metadata.
[ ] Partition's natural replica set verified before picking R3.
[ ] Disk/RAM/network headroom, backups, and rollback/cleanup rehearsed.

FIXTURE / CORRECTNESS
[ ] CQL schema uses partition + clustering keys matching query workload.
[ ] Event IDs, event_time, and full primary keys stay stable across retries.
[ ] Ledger classifies ACKed/unknown/definitely failed + CL/timestamp.
[ ] Fault-free baseline collected; checks IDs/values, not just row counts.
[ ] Separate TTL/delete fixture with tombstone reconciliation rules.

FAULT / AVAILABILITY
[ ] Clear fault start/end UTC markers; one replica down and peers report DN.
[ ] Tests LOCAL_QUORUM 2/3 without silently downgrading CL or changing schema mid-run.
[ ] Bounded client load, request throttling, deadlines/retry budgets.
[ ] Measures offered/achieved rate, success, timeouts, unavailable, p95/p99.
[ ] Accounts for coordinator routing/retries when a Cassandra node stops.

HINT / REPAIR
[ ] hinted_handoff_enabled, disabled DCs, and max_hint_window verified.
[ ] Hints on all relevant coordinators tracked via metrics/logs.
[ ] Node R3 restarted with original volume/identity; no hint deletion.
[ ] Separate test cases for short outage (hints) vs missing hints (repair).
[ ] Preview/full/incremental repair distinguished per version/semantics.
[ ] Repair token ranges/tables/DC participants have coverage and completion logs.
[ ] Repair schedule/cadence stays safe relative to gc_grace_seconds.
[ ] Never run full repair on all nodes simultaneously; never --force past down endpoints.

CONVERGENCE / OPERATIONS
[ ] Never declare convergence purely from R3=UN or a quorum SELECT returning rows.
[ ] Expected ACKed event IDs/values reconciled across bounded scope.
[ ] Replica-specific verification method used whenever claiming per-replica parity.
[ ] Hints + repair + ledger + performance correlated on one UTC timeline.
[ ] R3 disk/GC/compaction and client p99 return within approved limits.
[ ] Unknown writes reconciled without minting duplicate event IDs.
[ ] Local vs cross-DC repair verified in multi-DC topologies.
[ ] Handoff settings restored and fault injection stopped even on test failure.
[ ] Post-run report documents known gaps, risks, duration, rollback, and next actions.
~~~

~~~mermaid
flowchart TD
    A["Want to test missing replica R3"] --> B["Only in test cluster with RF3 full replicas"]
    B --> C["Baseline: ledger + CL + p99/metrics"]
    C --> D["Stop R3, wait for peers to see down"]
    D --> E["Write bounded LOCAL_QUORUM mutations, log ACK/unknown"]
    E --> F["Restore R3 with same volume, wait for UN"]
    F --> G{"Are hints complete and delivery succeeding?"}
    G -->|Appear sufficient| H["Verify handoff metrics + query ledger"]
    G -->|Missing/expired window/disabled| I["Preview/plan anti-entropy repair"]
    H --> J{"Policy repair coverage/validation met?"}
    I --> K["Run full/incremental repair for right token/table/DC scope"]
    K --> J
    J -->|Not yet| L["Investigate lag/disk/GC/tombstones, re-run controlled repair"]
    L --> I
    J -->|Met| M["Verify ledger IDs/values + p99 + cleanup"]
    M --> N["Report exact level of convergence evidence"]
~~~

## 32. Official References and Conclusion

Key documentation to cross-check against the exact **Cassandra version and Java Driver version** in your cluster:

1. [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, hint creation window, storage, delivery, settings, nodetool, and best-effort limits.
2. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): Merkle trees, full/incremental, repair frequency, `--partitioner-range`, `--preview`, `--validate`, token scope.
3. [Apache Cassandra — nodetool repair](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/repair.html): version-specific syntax/flags, DC/host/token scopes, and repair warnings.
4. [Apache Cassandra — Consistency Guarantees](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): Dynamo architecture, replication, coordinator, consistency, and eventual convergence.
5. [Apache Cassandra — Data replication](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): tokens/ring/natural replicas and replication strategies.
6. [Apache Cassandra — Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): compaction/tombstone retention and repair relationships; check grace guidelines per table/version.
7. [Apache Cassandra Java Driver 4.18 — Paging and Async](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): `CqlSession`, `CompletionStage`, paging, and client driver behavior.
8. [Apache Cassandra — CQL](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, TTL, and mutation/primary key semantics.

**Summary:** Testing an absent Cassandra replica does not stop at `stop` and checking `nodetool status`. With **RF=3 and `LOCAL_QUORUM`**, the coordinator can return an ACK when **two** healthy full replicas apply the mutation while the third replica misses writes. **Hinted handoff** can replay mutations buffered temporarily on coordinators once the replica returns, but it is **best-effort** with window, disk, and delivery limits; it **does not replace anti-entropy repair**. **Repair** compares datasets across token ranges using Merkle trees/streaming and requires its own schedule, coverage, resources, and monitoring to prevent prolonged drift and zombie tombstones. A rigorous fault test needs **stable operation IDs, an ACK/unknown ledger, accurate CL/topology, bounded stress, UTC fault markers, hint-backlog and repair-coverage metrics, ID/value verification, and safe cleanup**. Claim convergence only within the **exact scope supported by evidence**; never treat `UN`, a single quorum read, or a zero hint backlog as proof of full data consistency.




