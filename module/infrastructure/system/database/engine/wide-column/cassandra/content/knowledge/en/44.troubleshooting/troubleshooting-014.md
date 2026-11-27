# Hint Backlog, Missing Replica Data, or Stale Reads

> **Chapter:** Troubleshooting  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — understanding Apache Cassandra's distributed architecture and wide-column model: partition keys, query-first tables, read/write consistency levels, CQL, replication, compaction, repair, distributed failure modes, and Java application integration.

A Cassandra node was down for 45 minutes and just returned with status `UN`. A Java service reading at `LOCAL_ONE` occasionally returns `status="PENDING"`, even though a user already updated it to `status="APPROVED"` and the earlier write returned success. On several nodes, hint directories look large and JMX logs delivery failures. Is this **data loss**, an application bug, or simply lagging replica synchronization?

Do not rush to restart nodes, delete hints, or trigger cluster-wide repairs. Resolving this accurately requires separating **four facts**:

1. **What was actually confirmed to the client?** Write CL, RF/DC, whether the write returned success or timed out, and serial consistency if LWT.
2. **Which replicas actually received the mutation?** Storing a hint on a coordinator for an unreachable replica does not mean that replica holds the data yet.
3. **Where does catch-up currently stand?** Hints being created, queued on hint holders, replaying, failing, past the hint window, or requiring anti-entropy repair.
4. **Who served the read, and at what consistency level?** A `SELECT` at `ONE`/`LOCAL_ONE` can read stale data while `LOCAL_QUORUM` returns fresh data; application caches, timestamps, and TTLs can also mimic identical symptoms.

This lesson walks through isolating **hint backlog – replica divergence – stale reads**, gathering evidence from Cassandra and the Java Driver, and deciding cleanly among waiting on hinted handoff, verification reads, anti-entropy repair, and state reconciliation. Examples target **Cassandra 4.1/5.0 and Java Driver 4.x** assuming a multi-node lab cluster. Exact command flags, config keys, and JMX/exporter labels vary by version; execute active interventions strictly with an approved runbook and proper authorization.

> **Safety rule:** This is a diagnostic lesson. Never stop nodes, sever networks, delete hints, change CL, slash `gc_grace_seconds`, or run compaction/repair on production merely to walk through these steps. Numbers, UUIDs, IPs, and incidents in the lab sections are **illustrative examples**, not live telemetry from an actual cluster.

## 1. Learning Objectives

After this lesson, you can:

1. Explain coordinators, natural replicas, write CL, read CL, hinted handoff, and anti-entropy repair within a single read/write lifecycle.
2. Distinguish **a queued hint awaiting delivery** from **a mutation applied on the replica**, and a **write ACK** from **every replica persisting the write**.
3. Understand that `max_hint_window` bounds **the duration new hints are generated for a Down replica**, not a promise that all hints finish replaying within that window.
4. Differentiate `ONE`/`LOCAL_ONE` stale reads, quorum read repair, cross-DC lag, and unknown outcomes after write timeouts.
5. Gather evidence from both **hint-holding nodes** and **hint-receiving target nodes**, rather than inspecting only the restarted node.
6. Track hint creation, `Hints_not_stored`, replay successes/failures/timeouts, delivery delays, disk pressure, network health, and ring membership.
7. Run `nodetool status`, `statushandoff`, `getmaxhintwindow`, `netstats`, logs, and JMX safely with tight scope.
8. Explain why anti-entropy repair scans token ranges differently from read repair, which touches only queried data.
9. Recognize the risk of **tombstone resurrection (zombie data)** when a replica remains down past `gc_grace_seconds` without timely repair.
10. Design controlled RF=3 experiments, operation/outcome ledgers, Java Driver read probes, and convergence verification plans.
11. Formulate a prioritized, low-risk incident playbook complete with stop conditions and rollbacks.
12. Close incidents with solid evidence, declare unknowns clearly, and avoid claiming "empty hint queue = all data is correct".

## 2. Three Mechanisms Frequently Conflated

### 2.1. Hinted Handoff: Forwarding Missed Mutations

In an RF=3 keyspace inside `dc1` with natural replicas N1, N2, and N3, a client writes at `LOCAL_QUORUM`:

~~~mermaid
sequenceDiagram
    participant App as Java client
    participant C as Coordinator
    participant N1 as Replica N1
    participant N2 as Replica N2 (DOWN)
    participant N3 as Replica N3
    App->>C: UPDATE k=v2 (LOCAL_QUORUM)
    C->>N1: Mutation v2
    C-xN2: Mutation v2 (unreachable)
    C->>N3: Mutation v2
    N1-->>C: ACK
    N3-->>C: ACK
    C-->>App: SUCCESS (2/3)
    Note over C: May store hint for N2 on holder's disk
    Note over N2: N2 still holds v1
    N2-->>C: Rejoins ring / detected Up
    C->>N2: Replay hints
    N2-->>C: Delivered / ACK
~~~

The coordinator can persist a hint **on the local filesystem of the hint holder node** to deliver later once the target replica returns. Hints are **not** stored on the Down node N2. Different requests hit different coordinators, so hints for N2 can sit scattered across multiple coordinators; you must inspect all relevant hint holders across the cluster.

Key takeaways:

- The client receives **SUCCESS at `LOCAL_QUORUM`** once enough natural replicas ACK—all replicas do not have to ACK.
- Creating a hint **does not immediately synchronize N2** at write time.
- Hinted handoff is **best effort**: mutations can still be missed if downtime exceeds the hint window, hint creation/storage fails, disk/network breaks, target host identity changes, or delivery fails.
- Replayed hints preserve the **original mutation write timestamp** so delayed delivery never overwrites newer writes.
- Hint replay can take substantial time when backlogs are huge; `nodetool status` showing N2 as `UN` **does not prove** N2 finished receiving all hints.

### 2.2. Read Repair: Checking Divergence on Reads

When a coordinator serves a read at a CL requiring multiple replica responses (e.g., `LOCAL_QUORUM`), it compares full data and digests. When responding replicas disagree, Cassandra reconciles cells using timestamps and tombstones and performs **read repair** per table settings.

In Cassandra 4.x/5.x, `read_repair = 'BLOCKING'` is the default table option; `'NONE'` still reconciles the returned read result without blocking on repair writes to divergent replicas in the same way. These two options trade off *monotonic quorum reads* vs. *partition-level write atomicity* (consult official docs).

**Key limitations:**

- `ONE`/`LOCAL_ONE` needs just one replica response and performs **no synchronous digest comparison** to expose mismatches like quorum reads do.
- Read repair covers **only participating replicas and queried rows**, never repairing untouched partitions in the table.
- Read repair **does not replace** anti-entropy repair; a fresh `SELECT` never proves unrelated keys on N2 have converged.
- A quorum read returns the latest timestamp **among responding replicas**; it cannot guarantee observing a write that reached only a non-responding replica—especially after an unacknowledged timed-out write.

### 2.3. Anti-Entropy Repair: Syncing Token Ranges Across Replicas

`nodetool repair` proactively compares and synchronizes token ranges and partitions sharing natural replicas via Merkle trees and data streaming. It catches mutations **missing or expired from hints**, including outages exceeding `max_hint_window`.

Repair consumes significant disk, CPU, and network bandwidth and can trigger compaction or streaming backlogs. Cassandra does not run periodic full repairs automatically simply because hints fell behind; operators must manage repair schedules and runbooks explicitly.

| Mechanism | Trigger | Scope | Guarantees / Limits |
|---|---|---|---|
| **Hinted handoff** | Write sent to an unavailable/timed-out replica within policy/window | Mutations for which hints were stored | Best effort; does not guarantee all writes |
| **Read repair** | Multi-replica read detecting a mismatch | Participating replicas and queried data | Does not heal untouched dataset; policy varies per table |
| **Anti-entropy repair** | Operator or scheduler launches repair | Selected token ranges, keyspaces, and tables | Comprehensive controlled sync; requires healthy replicas and completion |

A node rejoining the ring is a **prerequisite for recovery**, not evidence that **recovery has completed**.

## 3. Why Can Reads Return Stale Results?

### 3.1. The v1/v2 Model Across Three Replicas

Suppose a partition starts at `v1` on N1, N2, and N3. N2 goes Down, and a `LOCAL_QUORUM` write sets `v2` and returns `SUCCESS`:

| Post-mutation state | N1 | N2 | N3 |
|---|---|---|---|
| Value known to replica | `v2` | `v1` (Down) | `v2` |
| ACKed write for CL? | ACK | No | ACK |
| Hint status | May be held by coordinator for N2 | Not yet applied | May sit on N1/N3 or another coordinator |

After N2 comes Up **before all hints replay**:

- A `LOCAL_ONE` read routed to N2 **can return `v1`**.
- A `LOCAL_ONE` read routed to N1/N3 **can return `v2`**.
- A `LOCAL_QUORUM` read, assuming no competing writes and healthy quorum response, intersects the successful quorum write pair and reconciles `v2` via timestamp/read-repair rules.
- If the read times out or fails `Unavailable`, no value returns: **a read failure** is distinct from a **stale result**.

**This is probabilistic, not deterministic on every call.** Load balancing, coordinator choices, and read repair itself can make stale reads vanish intermittently after a few retries. Connecting `cqlsh` directly to N2 does not force every query to read strictly from N2's local disk; inspect traces and replica contacts.

### 3.2. Assumptions Behind `R + W > RF`

In a simplified single-DC RF=3 model:

~~~text
LOCAL_QUORUM write: W = 2
LOCAL_QUORUM read:  R = 2
2 + 2 > 3  -> responding replica sets must overlap
~~~

Conditional consequence: given an **acknowledged successful write**, no concurrent mutations, healthy timestamps/tombstones, consistent schema/topology, and fulfilled read CL, a quorum read can observe that mutation.

Never cite this inequality as proof that every operation is **strictly linearizable** or that every replica has converged. W/R counts only replica ACKs—it **does not guarantee** ordering for unacknowledged/failed writes, LWT/Paxos nuances, multi-partition statements, timeouts, TTL expirations, topology transitions, or asynchronous cross-DC replication.

### 3.3. Causes of Stale Reads Other Than Hint Backlogs

| Cause | Distinguishing clue | What to separate |
|---|---|---|
| Replica just rejoined, hints not yet replayed | Only one replica/token set lags; pending hints exist | Genuine replication lag |
| `W=ONE, R=ONE` | Quorum sets need not intersect | Configured consistency trade-off |
| Write timeout / partial ACK | Mutation may exist on subset of replicas | `UNKNOWN` outcome—never assume "write succeeded" |
| Cross-DC `LOCAL_QUORUM` | Local DC updated; remote DC still catching up | Local quorum **does not** enforce instant cross-DC visibility |
| Application / HTTP cache | Direct CQL returns latest row while API serves stale | Cache TTL, invalidation, or routing |
| Timestamp collision / clock skew | "Newer" request loses LWW comparison | Last-write-wins or client `USING TIMESTAMP` |
| TTLs and tombstones | Values vanish or revert depending on cell age | Expiration, `gc_grace`, repair, read scope |
| Misread LWT result | CAS `[applied]=false` read as success, or timeout as false | Inspect `wasApplied()` and serial consistency |
| Materialized view / projection lag | Secondary view diverges from base table | Async write pipeline or MV lag |
| Wrong partition key / bucket | Query hits wrong row, date bucket, or tenant | Prepared CQL, bind ordering, clustering predicates |

A user saying "I updated the status" only proves client intent. Cross-check **write responses, CL, query keys, timestamps, and read code paths** before blaming lagging replicas.

## 4. Isolating Timing, Scope, and Hypotheses

### 4.1. Illustrative Timeline (Hypothetical)

~~~text
09:00Z  RF3/dc1: N1 N2 N3 = UN, value=v1
09:05Z  N2 goes Down for maintenance
09:07Z  App writes v2 at LOCAL_QUORUM, returns SUCCESS
09:08Z  Holder(s) show Hints_created rising for N2
09:45Z  N2 rejoins UN
09:46Z  App reading at LOCAL_ONE intermittently sees v1
09:49Z  Hint delivery failures/timeouts climb; holder disk busy
10:10Z  HintsSucceeded climbs, yet N2 lag not yet proven zero
10:20Z  Sampled LOCAL_QUORUM read observes v2
~~~

**Build the UTC timeline from authoritative telemetry**, never concluding from a single "node Up" log line that every hint finished replaying. Separate `T_down`, `T_write_ack`, `T_up`, `T_delivery_start/end`, `T_read_stale`, and `T_repair_complete`, accounting for clock skew, log shipping delay, and metric scrape intervals.

### 4.2. Blast Radius Map

| Dimension | Cohorts to compare | Diagnostic question |
|---|---|---|
| API/client | Mobile/web, service versions, cache bypass | Is staleness from Cassandra or a cache? |
| Data model | Keyspace/table, partition/key, TTL, liveness | A handful of keys or whole tables? |
| Query shape | Point PK `SELECT`, ranges/latest-N, CL, paging | Querying the exact row and expected CL? |
| Datacenter | `dc1`/`dc2`, driver local DC, per-DC RF | Local DC lag or cross-DC lag? |
| Topology | Node Up/Down/Joining/Replacing, host IDs | Is target still the same node identity? |
| Hint holders | Coordinators active during writes/downtime | Where are the hints actually stored? |
| Hint target | Rejoining replica missing mutations | Can it receive replays cleanly? |
| Storage | Disk, GC, network, hints directory, queues | Is delivery stalled or were hints never created? |
| Client outcome | `SUCCESS`, `TIMEOUT_UNKNOWN`, `CAS_NOT_APPLIED` | Was the write truly acknowledged? |

**Never inspect just one holder:** clients spray traffic across coordinators, leaving hints across multiple holders. N2 showing Up says nothing about disk or hint backlogs sitting on N1, N3, or other coordinators.

### 4.3. Every Hypothesis Needs Falsifiers

~~~text
H1: N2 is stale because hinted handoff replay has not finished.
Predicts:
  - N2 was Down when v2 writes occurred;
  - Hints_created or hint disk files grew on one or more holders;
  - HintsSucceeded rises after N2 returns Up while pending/failed deliveries remain;
  - stale reads correlate with partitions replicated onto N2.
Falsifiers:
  - zero writes hit N2's downtime window, or zero replica divergence exists;
  - direct CQL returns v2 at target CL while app HTTP cache returns v1;
  - mutation v2 lost LWW timestamp resolution or already expired via TTL.
Low-risk checks:
  - snapshot hint metrics, node topology, and query fingerprints;
  - run controlled verification reads at approved CL with low-rate tracing.
~~~

If symptoms began **before N2 went down**, or only in one service version while direct CQL reads stay fresh, H1 weakens sharply. Never use `truncatehints` or node restarts as a "diagnostic test" for H1.

## 5. Understanding Hint Lifecycle and Backlog Causes

### 5.1. Where Do Hints Live?

In Apache Cassandra, hints persist as **files on the coordinator/hint holder's local filesystem**, typically `$CASSANDRA_HOME/data/hints` or `hints_directory`. Each hint stores target replica metadata and the mutation (retaining its original write timestamp), replayed segment-by-segment once the target becomes reachable.

~~~mermaid
flowchart LR
    A["Mutation hits coordinator"] --> B{"Target replica reachable?"}
    B -->|Yes| C["Replica applies and ACKs mutation"]
    B -->|No| D{"Hint policy + window permit?"}
    D -->|Yes| E["Hint holder buffers/writes hint file"]
    D -->|No| X["No new hint stored"]
    E --> F["Target returns Up"]
    F --> G["Delivery queue / throttle / network"]
    G --> H{"Target applies hint segment?"}
    H -->|Yes| I["ACK; segment cleaned up per policy"]
    H -->|Error / timeout| J["Retry / increment failure counter"]
    X --> K["Anti-entropy repair required to sync"]
    J --> G
~~~

A hint sitting on disk **does not mean the target replica received the write**. Conversely, hint directory bytes shrinking **do not guarantee every table synced**, since some mutations may never have generated hints.

### 5.2. `max_hint_window` Is Not a Replay Deadline

A core setting in Cassandra 4.x/5.x is `max_hint_window`, commonly defaulting to **3 hours** (earlier versions named it `max_hint_window_in_ms`). It caps how long after a target is marked Down that coordinators keep **creating new hints** for it.

Distinguish each phase:

| Event | Meaning |
|---|---|
| Target detected Down | Hint creation window clock begins per failure detection |
| Within `max_hint_window` | Coordinators can persist new hints for missed mutations |
| Target stays Down past window | **New hint creation stops** per policy; `Hints_not_stored` can rise |
| Target returns Up | **Previously saved hints** remain eligible for replay; passing the window doesn't instantly delete saved hints |
| Hint replay completes | Only stored/delivered mutations apply; does not guarantee unhinted data |

**Never assume "Down 4 hours → all hints wiped" or "Down 2 hours → 100% of writes hinted".** Verify active configs, disabled DCs, storage health, host ID changes, and per-node metrics.

### 5.3. Configuration Settings Affecting Hint Backlogs

| Setting (Cassandra 4.x/5.x) | Effect | Misconception / Risk |
|---|---|---|
| `hinted_handoff_enabled` | Toggles hinting globally | Enabled ≠ every missed write gets hinted |
| `hinted_handoff_disabled_datacenters` | Excludes specific DCs from handoff | Disabled DCs experience persistent lag without repair |
| `max_hint_window` | Caps **new hint generation** while target is Down | Not a replay timeout |
| `hinted_handoff_throttle` | Caps per-thread delivery bandwidth, scaled by cluster size | Too low prolongs backlog; too high saturates disk/NIC |
| `max_hints_delivery_threads` | Parallel hint sender threads | Raising carelessly can overwhelm returning targets |
| `hints_directory` | Filesystem path storing hint files | Full/failing disk prevents saving hints |
| `hints_flush_period` | Buffer flush interval to hint files (not strict fsync) | Not a hard durability guarantee |
| `max_hints_file_size` | Rotation size per hint segment file | Not a global quota on total backlog |
| `max_hints_size_per_host` (version-dependent) | Per-target hint storage cap | Exceeding cap drops new hint storage |

Cassandra 5.0 documentation lists common defaults: `max_hint_window=3h`, `hinted_handoff_throttle=1024KiB`, `max_hints_delivery_threads=2`, `max_hints_file_size=128MiB`. **Do not assume these exact names/values on every deployment**—Cassandra 4.0 still uses `_in_ms`/`_in_kb` suffixes on several keys. Inspect live `cassandra.yaml` and `nodetool help` for your exact release.

### 5.4. Five Causes of Growing Hint Backlogs

1. **Target still Down or flapping:** briefly returns Up then drops again, aborting and restarting deliveries.
2. **Hint creation outpaces delivery:** high write volume while replicas stay unavailable, tight throttles, slow networks, or slow target disks.
3. **Hint directory issues:** near-full disk, inode exhaustion, permissions/I/O errors, read-only mounts, or per-host caps.
4. **Network / inter-DC impairment:** packet loss, high RTT, firewall rules, internode TLS bottlenecks, NIC saturation, or split-brain partitions.
5. **Resource contention:** heavy target GC, compaction, streaming, or repair colliding with concurrent hint replays from multiple holders.

Therefore monitor **both sides**: holders storing/shipping hints and the target receiving/applying them. If the target looks `UN` yet sits at 100% disk utilization due to compaction, cranking up hint throttles can **slow overall recovery**.

### 5.5. Separating Hint Backlogs from Other Backlogs

| Signal | What it confirms | What it does NOT prove |
|---|---|---|
| Large hints directory on N1 | N1 holds hint bytes on disk | All files target N2, or all are still undelivered |
| `HintsSucceeded` rising on N1 | Hint deliveries are completing | Backlog has drained to 0 |
| `HintsFailed`/`HintsTimedOut` rising | Deliveries are failing/timing out | All hints are gone or should be deleted |
| `nodetool netstats` shows streaming | Repair/bootstrap/streaming active | Exact count of pending hints |
| High `PendingCompactions` | Compaction backlog present | Sole cause of stale reads |
| Target shows `UN` | Gossip sees target Up/Normal from queried node | Target holds all mutations |
| `LOCAL_QUORUM` read returns `v2` | Responding quorum reconciled `v2` | Every replica and partition is synchronized |

Per-peer metrics like `Hints_created-<PeerIP>` differ slightly in lifecycle and reset rules across releases. **Never blindly subtract cumulative counters to declare exact pending counts**: monitor directory bytes, delivery rates, delivery latency, and whether mutations remain undelivered.

## 6. Gathering Hint Backlog Telemetry at the Right Layer

### 6.1. Low-Impact Multi-Node Snapshots Over Time

Capture snapshots across multiple holders/nodes with UTC timestamps, hostnames, DCs, Cassandra versions, and clear intervals:

~~~bash
# Mostly READ-ONLY commands; run per permissions & runbook.
date -u +"%Y-%m-%dT%H:%M:%SZ"
nodetool status
nodetool describecluster
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
~~~

`nodetool status` reflects the **local node's gossip perspective**, which can diverge between N1 and N3 during partitions. `tpstats` tracks stage queues and dropped messages rather than global hint counts. `netstats` tracks streaming (repair/bootstrap), not hinted handoff progress.

Inspecting hinted handoff state in Cassandra 4.x/5.x:

~~~bash
nodetool statushandoff
nodetool getmaxhintwindow
nodetool handoffwindow
~~~

**Check `nodetool help <command>` first**, as exact command names and availability vary by release. The commands above read status/settings, whereas `disablehandoff`, `pausehandoff`, `sethintedhandoffthrottlekb`, `setmaxhintwindow`, and `truncatehints` **mutate cluster state**.

### 6.2. Inspecting the Hints Directory on a Holder

On an authorized Linux lab host once the real `hints_directory` is confirmed:

~~~bash
date -u +"%Y-%m-%dT%H:%M:%SZ"
df -h /var/lib/cassandra/hints
df -i /var/lib/cassandra/hints
du -sh /var/lib/cassandra/hints
ls -lah /var/lib/cassandra/hints
~~~

`/var/lib/cassandra/hints` is only a **common default example**; packages and containers relocate it frequently. Hint files contain raw mutations that may include sensitive data—never inspect contents casually, share publicly, `rm`, `chmod`, or lock the directory during replay. Even `du`/`ls` adds metadata I/O if thousands of files exist; bound polling frequency.

**Record:** byte sizes at `t0`/`t1`/`t2`, growth/drain rate, free bytes/inodes, file modification times, which holders were checked, and matching delivery metrics. Shrinking bytes can reflect segment cleanup, rotation, or eviction—always cross-check logs and counters.

### 6.3. Key Metrics in JMX / Exporters

Cassandra 4.x/5.x documents:

| Metric / group | Type & meaning | Diagnostic reading |
|---|---|---|
| `Storage.TotalHints` | Cumulative hints written since startup | Rising indicates hinting load; resets on restart |
| `Storage.TotalHintsInProgress` | Hints currently being sent (per docs) | Not total pending bytes or age |
| `HintedHandOffManager.Hints_created-<PeerIP>` | Hints created/stored for specific peer | Track per peer and trend; not exact queue length |
| `HintedHandOffManager.Hints_not_stored-<PeerIP>` | Hints skipped because target stayed Down past window | Warns **mutations likely missed hinting entirely** |
| `HintsService.HintsSucceeded` | Meter of successful hint deliveries | Shows delivery throughput, not full cluster convergence |
| `HintsService.HintsFailed` | Meter of failed hint deliveries | Delivery errors; check target, network, disk |
| `HintsService.HintsTimedOut` | Meter of timed-out hint deliveries | Target or internode link saturated |
| `HintsService.Hint_delays` | Delivery delay histogram (typically ms) | Measures tail catch-up time |
| `HintsService.Hint_delays-<PeerIP>` | Per-peer delivery delay histogram | Isolates slow target peers |

Exporters often rename JMX `org.apache.cassandra.metrics.HintsService` / `HintedHandOffManager` MBeans and labels. **Verify your live exporter mapping** rather than inventing Prometheus metric names to claim "backlog=0".

### 6.4. Measure Backlog via Rates and Age, Not One Counter

An effective triage panel tracks:

~~~text
By node holder and target peer:
  hints_written_per_second
  hints_delivery_succeeded_per_second
  hints_delivery_failed_or_timeout_per_second
  hints_not_stored_per_second
  hints_directory_bytes
  oldest_pending_hint_age (if reliably exposed)
  hint_delivery_delay_p95/p99

Alongside:
  target_Up_Down_timeline
  client_write_rate_and_CL
  target_disk_io / GC / internode_network
  repair_and_compaction_load
~~~

Not every exporter tracks `oldest_pending_hint_age`; mark `NOT_AVAILABLE` instead of guessing from `TotalHints`. Creation and delivery counters measure different event units across resets/segments—never compute `created - succeeded` and treat it as exact queue depth without verifying accounting semantics.

### 6.5. Correlating Logs Across Downtime/Rejoin Windows

Inspect logs across **every holder and target**:

~~~text
T_down  ± a few minutes: endpoint marked DOWN, hint creation starts
T_up    ± a few minutes: endpoint marked UP, hint dispatch begins
After T_up: hint replay failures/timeouts, disk/GC/network spikes
Repair window: anti-entropy repair start, progress, success/errors
~~~

In Cassandra 4.x/5.x, check `logs/system.log`, `logs/debug.log`, `journald`, or container logs. Filter by UTC timestamp and peer IP/host ID; exact log wording **is not a stable API across versions**. Never flip cluster-wide `DEBUG` logging on during disk saturation.

### 6.6. Standardized Evidence Ledger

| ID | UTC / source | Subject | Observation | What remains unproven |
|---|---|---|---|---|
| EV-H01 | N1, 09:48Z | Hint holder | `HintsSucceeded` climbing | Whether N2 received all data |
| EV-H02 | N3, 09:48Z | Hint holder | `HintsTimedOut` rising, network RTT high | Which mutations are missing |
| EV-H03 | N2, 09:49Z | Target | `UN`, disk busy 95% (example) | Whether N2 has converged |
| EV-H04 | App v27, 09:50Z | Client | `SELECT LOCAL_ONE` returned `v1` | Which replica served the read |
| EV-H05 | App v27, 09:51Z | Client | `LOCAL_QUORUM` returned `v2` | Whether every replica holds `v2` |

Replace hypothetical rows with **links to actual metrics, logs, and traces** during live incidents. Verify clock sync and scrape intervals so later events never pose as earlier causes.

## 7. First 30-Minute Triage Playbook

### 7.1. Decision Flowchart

~~~mermaid
flowchart TD
    A["API reports stale / replica lag"] --> B{"Did write ACK genuinely succeed?"}
    B -->|Unknown timeout| C["Classify UNKNOWN and reconcile operation ledger"]
    B -->|Yes| D{"Bypassed application cache on read?"}
    D -->|No| E["Bypass cache / compare direct read safely"]
    D -->|Yes| F{"Read CL and local DC appropriate?"}
    F -->|ONE/LOCAL_ONE| G["May hit lagging replica; run quorum check"]
    F -->|Quorum| H["Check timestamps, concurrent writes, read repair"]
    G --> I{"Did a replica go Down/rejoin?"}
    H --> I
    I -->|Yes| J["Inspect hint holders, backlog, window, delivery failures"]
    I -->|No| K["Inspect schema, timestamps, TTL, LWT, multi-DC lag"]
    J --> L{"Hints intact and delivering?"}
    L -->|Yes| M["Monitor convergence with explicit deadline"]
    L -->|Unclear/missing| N["Plan scoped anti-entropy repair per runbook"]
    M --> O["Data verification and integrity gate"]
    N --> O
~~~

### 7.2. Minutes 0–5: Scope Impact and Lock Evidence

Write a clear incident statement:

~~~text
INC-CASS-... (illustrative)
First known bad: 2026-11-21T09:46Z (1-min bucket)
Affected: state API, service v27, dc1, PK SELECT
Observed: stale v1 in 4 of 120 sampled reads at LOCAL_ONE
Write outcome: v2 ACK at LOCAL_QUORUM 09:07Z
Node history: N2 Down 09:05Z, Up 09:45Z
Hints evidence: not yet collected
Unknown: exact replica serving stale reads; all holders and backlogs
Risk: user-visible stale data / possible missed mutations
~~~

Check immediately for **confirmed write loss, rising `Unavailable`, full disks, or tombstone resurrection**, escalating severity as needed. Log unknowns as `UNKNOWN` rather than jumping to "database corruption".

### 7.3. Minutes 5–15: Separate Read Path and Write Path

1. Verify the client actually wrote to the **expected primary key and keyspace**, confirming `SUCCESS` vs. timeout and effective CL (not merely code defaults).
2. Compare cache vs. direct Cassandra reads using identical query fingerprints, **safely pseudonymized** bind values, buckets, and CL.
3. Segment healthy vs. affected cohorts by service version, DC, target replica (if traced), timestamps, and TTL age.
4. Run `nodetool status` across multiple nodes, noting N2 Down/Up times and any `Joining`/`Leaving`/`Moving` states.
5. Collect hint metrics and directory stats across **all likely holders**, not just N2.
6. Verify table `read_repair`, Cassandra version, `gc_grace_seconds`, `max_hint_window`, and recent changes.
7. Rate-limit diagnostic read probes so verification **never overloads an impaired cluster**.

### 7.4. Minutes 15–30: Wait for Hints vs. Run Repair

| Finding | Next diagnostic step | Action note |
|---|---|---|
| Target Up, `HintsSucceeded` climbing, zero failures, bytes dropping | Watch delay/lag; run sampled verification reads | Waiting for handoff drain may suffice |
| Target flapping, delivery timeouts climbing | Inspect target GC/I/O/network, peer connectivity, host ID | Stabilize target before tuning throughput |
| `Hints_not_stored` rising or outage exceeded hint window | Scope an anti-entropy repair plan | Waiting on hints won't recover unhinted writes |
| Holder hints disk nearly full | Treat as disk capacity incident; protect hints/commitlog/data | Never delete hints to free space |
| Node Up, hints drained, yet stale reads continue | Check CL, caches, timestamps, TTLs, missing hints, repair history | Drained hints ≠ guaranteed convergence |
| Quorum reads also return old value | Audit write outcome, winning timestamp, concurrent writes | Don't assume `v2` ACKed without write ledger proof |
| `LOCAL_ONE` returns `v1`, `LOCAL_QUORUM` returns `v2` | Replica divergence or read routing | Isolate lagging replica and track convergence |

**Never trigger `repair` reflexively on every stale read.** Repairs consume heavy resources and fail if target replicas keep flapping. Evaluate replica stability, background load, and recovery policies first.

### 7.5. Change Only One Mitigation at a Time

Where authorized under severe user impact, consider adjusting **read routing or policy** per business contract—**never silently flip `LOCAL_ONE` ↔ `LOCAL_QUORUM`** merely to turn dashboards green. Raising CL increases latency/timeouts against slow replicas; lowering CL increases stale-read exposure. Document invariants, RF, availability trade-offs, and impact beforehand.

Every mitigation needs:

~~~text
Action / approval / time window:
Prediction:
Stop condition:
Rollback:
Before metrics:
After metrics:
Data correctness check:
Residual risks:
~~~

## 8. Verifying Data via Java Driver 4.x

### 8.1. Never Try to "Read One Specific Node" Using Contact Points

Java Driver picks coordinators via query plans, local DC locality, and token-aware routing. That coordinator can forward reads to another replica; **a contact point does not force reads from that node's local SSTables**.

To inspect actual execution paths:

- Read `ExecutionInfo.getCoordinator()` on completed responses.
- Enable low-rate authorized tracing to see contacted replica endpoints.
- Audit load-balancing policies, token-aware routing, routing keys, and local DC.
- For replica-specific lab testing, use controlled fault injection and traces—never run that in production to "force stale reads".

### 8.2. Verification Queries With Full Partition Key

Example lab table:

~~~sql
CREATE TABLE IF NOT EXISTS incident_lab.state_by_account (
    account_id uuid PRIMARY KEY,
    state text,
    revision bigint,
    updated_at timestamp
) WITH read_repair = 'BLOCKING';
~~~

In an RF=3 `dc1` lab after confirming a `LOCAL_QUORUM` write succeeded for `revision=2`, probe identical keys across consistency levels:

~~~sql
-- Inside lab cqlsh; CONSISTENCY is a cqlsh shell command, not CQL DML.
CONSISTENCY LOCAL_ONE;
SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;

CONSISTENCY LOCAL_QUORUM;
SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

**Note:** A `LOCAL_ONE` read may hit a fresh replica and return `revision=2` even while N2 remains stale; meanwhile, a `LOCAL_QUORUM` read can trigger blocking read repair and silently heal participating replicas during observation. Capture baseline metrics and logs before issuing diagnostic read probes.

### 8.3. Java Code Distinguishing Consistency Level and Coordinator

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

record Probe(ConsistencyLevel cl, Long revision, String state,
             String coordinator, Instant capturedUtc, String error) {}

static Probe readState(
    CqlSession session, PreparedStatement select, UUID accountId,
    ConsistencyLevel consistency, boolean traceSample) {

    Instant captured = Instant.now();
    BoundStatement bs = select.bind(accountId)
        .setConsistencyLevel(consistency)
        .setTimeout(Duration.ofSeconds(2))
        .setTracing(traceSample)
        .setIdempotent(true);

    try {
        ResultSet rs = session.execute(bs);
        Row row = rs.one();
        ExecutionInfo ei = rs.getExecutionInfo();
        String coordinator = String.valueOf(ei.getCoordinator());
        if (row == null) {
            return new Probe(consistency, null, null, coordinator,
                             captured, null);
        }
        Long revision = row.isNull("revision")
            ? null : row.getLong("revision");
        return new Probe(consistency, revision,
            row.getString("state"), coordinator, captured, null);
    } catch (RuntimeException e) {
        return new Probe(consistency, null, null, "UNKNOWN",
                         captured, e.getClass().getName());
    }
}

// Inside a service/lab holding an initialized CqlSession and UUID accountId:
PreparedStatement select = session.prepare(
    "SELECT state, revision FROM incident_lab.state_by_account " +
    "WHERE account_id=?");

Probe one = readState(session, select, accountId,
    DefaultConsistencyLevel.LOCAL_ONE, false);
Probe quorum = readState(session, select, accountId,
    DefaultConsistencyLevel.LOCAL_QUORUM, false);
~~~

This snippet shows **illustrative helper methods/statements assuming an existing `session` and `accountId`**, not a standalone compilable file. Never log raw production account or tenant IDs. Exceptions populate the `error` field—callers must inspect errors cleanly instead of interpreting `revision=null` after a timeout as "row deleted".

**Note:** `ResultSet.one()` reads a single row; point-PK lookups return at most one row. Multi-row range reads must track page consumption and per-page `ExecutionInfo`. Enable tracing only for rare samples because traces write into `system_traces`.

### 8.4. Pair Expected Revisions With an Operation Ledger

Comparing only `state` fails under concurrent updates:

~~~text
Write W1 revision=1, timestamp=T1, ACK
Write W2 revision=2, timestamp=T2, ACK
Write W3 revision=3, timestamp=T3, UNKNOWN_TIMEOUT
Read observes revision=3
~~~

Observing `revision=3` **isn't necessarily wrong** even though W3 timed out on the client: partial replica commits happen. Conversely, a subsequent write carrying `USING TIMESTAMP` older than T2 can **lose LWW** even when returning `SUCCESS`. Revision numbers are **application columns**; absent LWTs or external serialization, Cassandra does not enforce strictly monotonic revisions across concurrent writers.

Record in the ledger:

- Operation ID, pseudonymized key, command type, intended state/revision.
- Write CL (and serial CL if LWT), outcome (`SUCCESS` / `CAS_NOT_APPLIED` / `UNKNOWN`).
- Effective timestamp and TTL deadline if app-managed.
- Read CL, UTC time, coordinator/trace ID if sampled, observed value.
- Concurrent mutations and reconciliation state.

### 8.5. Distinguishing Read Errors From Stale Reads

| Java outcome | Valid interpretation |
|---|---|
| `Row != null`, `revision=1` | Revision 1 returned for that read CL and timestamp |
| `Row != null`, `revision=2` | Revision 2 returned; does not prove all replicas hold it |
| `Row == null`, request `SUCCESS` | No live row found on that read path; could be TTL, delete, or un-replicated |
| `ReadTimeoutException` | Coordinator missed CL response threshold within timeout; **no value returned** |
| `UnavailableException` | Not enough live replicas for CL at decision time |
| `DriverTimeoutException` | Driver deadline expired; never infer storage values from it |

Never write deterministic test assertions like `assertEquals(v1, readState(LOCAL_ONE))` right after N2 rejoins: the driver may pick a fresh or already-repaired replica, making the test flaky even though stale reads are genuinely possible.

## 9. When to Wait on Hints vs. Run Anti-Entropy Repair?

### 9.1. Operational Decision Matrix

| State | Working conclusion | Next action |
|---|---|---|
| Target Down, within hint window, holders healthy | Hints likely buffering/storing | Recover target safely; track backlog/disk |
| Target Up, `HintsSucceeded` rising steadily, delay shrinking | Hinted handoff draining normally | Monitor until integrity gate passes |
| Target Up yet `HintsFailed`/`HintsTimedOut` surging | Replay congested | Fix network, disk, GC, throttle, or target health first |
| Target Down past `max_hint_window` | **Missing hints likely** for later writes | Plan scoped anti-entropy repair once target stabilizes |
| `Hints_not_stored` rising | Mutations exceeded window/policy caps | Don't rely solely on replay drain; schedule repair |
| Target replaced by new host / new identity | Old hints may not map to replacement | Follow node replacement/streaming/repair runbooks |
| All hints replayed yet stale samples remain | Possible missed hints, timestamp/TTL/cache, or older divergence | Broaden telemetry; assess repair/write semantics |
| Target Down near or past `gc_grace_seconds` | **Deleted-data resurrection risk** | Escalate to data-integrity incident; avoid blind repair |

**Never follow a rule like "small hints directory means no repair needed".** Hints are best effort; scheduled anti-entropy repairs remain mandatory independently. Zero current hint bytes also does not prove every past downtime mutation was captured.

### 9.2. Incremental vs. Full Repair

Per Cassandra 4.x/5.x architecture:

- **Incremental repair** repairs only data not yet marked repaired from prior runs; cheaper when run regularly, yet **misses corruption/loss inside already-repaired SSTables**.
- **Full repair** validates all data in scope (repaired and unrepaired); heavier in I/O, yet catches inconsistencies incremental repairs skip.
- **Primary-range repair (`-pr`)** avoids duplicate work across nodes when run sequentially across **every required node and DC**. Running `-pr` on a single node repairs only that node's primary ranges—not the whole cluster.
- Repair interactions with Paxos/LWT state and streaming depend on Cassandra version and flags; always validate flags against cluster topology.

**Command planning** example (not direct production execution instructions):

~~~bash
# Run only after change approval, maintenance window, and health preflight pass.
# Every command consumes cluster I/O and affects data state.

# Incremental primary-range repair on one table:
nodetool repair -pr incident_lab state_by_account

# Full primary-range repair on one table:
nodetool repair --full -pr incident_lab state_by_account
~~~

**Coordinate execution across nodes and DCs** per repair runbook to cover every token range; never launch simultaneous repairs everywhere or run one command on N2 and declare cluster consistency solved. Cassandra 5.x adds `--preview` to estimate divergence without streaming, though **preview still computes Merkle trees and consumes CPU/I/O**—scope and verify carefully.

### 9.3. Pre-Repair Preflight Checklist

Confirm before launching repair:

1. **Scope:** which keyspace/table/token ranges diverged? Are all required replicas Up and stable?
2. **History:** last full/incremental repair timestamp, outcome, scope, unrepaired/repaired SSTables, tombstone/grace risk?
3. **Capacity:** free disk headroom, network capacity, CPU/GC, compaction/streaming queues, maintenance window?
4. **Consistency:** RF/DC/CL intact? Any bootstrap, decommission, replacement, schema disagreement, or upgrade underway?
5. **Impact:** can client SLAs absorb read/write latency and extra I/O, and who owns stop authority?
6. **Strategy:** target specific table/ranges vs. whole cluster, incremental vs. full, concurrency/job settings?
7. **Telemetry:** matching pre/post dashboards, job IDs, errors, streamed bytes, and runtime duration?
8. **Rollback/recovery:** if overload or suspected tombstone resurrection strikes, stop per runbook and reconcile against backups/source of truth.

Repair heals replica divergence, yet **cannot undo application logic mistakes** like out-of-order client timestamps, misunderstood CAS `[applied]=false`, or bad partition keys.

### 9.4. Never Use Destructive Commands to "Clear Backlogs"

| Action | Why NOT to run arbitrarily |
|---|---|
| `nodetool truncatehints` | Wipes queued hints, destroying best-effort recovery of missed writes |
| Deleting files in `hints_directory` manually | Corrupts hint state and destroys forensic evidence |
| `nodetool disablehandoff` | Disables hinting policy, leaving future downtimes unhinted |
| `nodetool pausehandoff` | Halts delivery while hints keep piling up |
| Raising `hinted_handoff_throttle` sky-high | Saturates target disk/NIC and degrades read/write p99 |
| Restarting all hint holders | Drops volatile stats/caches, disrupts gossip, delays replay |
| Major compaction | High disk amplification; never replaces anti-entropy repair |
| Setting `gc_grace_seconds=0` | Severely raises deleted-data resurrection risk |

Specific interventions belong strictly inside **vetted, approved recovery runbooks**; never treat mutating commands as benign diagnostic steps.

### 9.5. Three Distinct Levels of "Synchronized" Verification

| Level | What it proves | What it does NOT prove |
|---|---|---|
| **Operationally Up** | Node/process is Up/Normal in gossip view | Replica holds complete up-to-date data |
| **Hint delivery completed** | Inspected holders drained queued hints in scope | Zero mutations fell outside `max_hint_window` or failed storage |
| **Replica data reconciliation** | Repair succeeded across scope + spot-verified data | Application invariants and external caches are automatically synced |

A thorough integrity gate combines **verified repair completion, accounted failures, versioned key spot checks, TTL/liveness validation, zero unresolved writes, and recovered user SLOs under representative traffic**. No lone `nodetool status` proves these criteria.

## 10. TTL, Tombstones, and Deleted-Data Resurrection Risk

### 10.1. Hints Also Carry Deletes

Cassandra writes **tombstones** on `DELETE` or TTL expiration rather than erasing bytes immediately, preventing lagging replicas from resurrecting old rows. A Down replica misses **deletes** just like updates. If tombstones get purged on healthy replicas before reaching the Down replica, the returning replica can resurrect deleted ("zombie") data.

~~~text
Initial:          N1=A      N2=A       N3=A
N2 goes Down.
DELETE ACKed:     N1=DEL    N2=A       N3=DEL
Before purge:     N1/N3 tombstones supersede N2's A by timestamp
After grace + compaction purge on N1/N3:
                  N1=none   N2=A       N3=none
N2 rejoins; read/repair can resurrect A across replicas.
~~~

This is a **logical diagram**, omitting SSTable internals, row liveness markers, and compaction purge rules. Tombstones become eligible for purge only **after `gc_grace_seconds` elapses AND safe compaction conditions hold**; data does not disappear magically the exact second grace expires.

### 10.2. Two Distinct Time Windows

| Parameter | Purpose | Typical example default |
|---|---|---|
| `max_hint_window` | How long holders **keep creating new hints** for a Down replica | ~3 hours |
| `gc_grace_seconds` | Minimum age tombstones are retained before eligible compaction purge | 864,000 seconds (10 days) |

**Never confuse these two settings.** A node Down 4 hours exceeds the default hint window yet stays well inside default `gc_grace_seconds`, so anti-entropy repair safely restores missed updates and tombstones. A node Down longer than `gc_grace_seconds` risks data resurrection if tombstones purged—requiring a **data-integrity response**, not higher hint throttles.

TTL expirations operate **per-cell** independently of app `event_time` columns. Retrying an `UPDATE` with a new TTL after a timeout extends expiry deadlines. If reads suddenly return `v1` because `v2` hit TTL right around N2's recovery, evaluate TTL expiration windows before blaming hints.

### 10.3. When Outages Exceed `gc_grace_seconds`

Before repairing or restoring a long-dead node to full traffic:

- Audit exact downtime duration, table `gc_grace_seconds`, repair history, and whether tombstones already purged via compaction.
- If resurrection is suspected, **isolate or manage the stale replica per runbook** rather than launching blind repair that spreads deleted data back to healthy nodes.
- Reconcile deleted keys against authoritative source-of-truth logs, snapshots, or backups.
- Execute version-appropriate recovery, node replacement, or rebuild procedures under proper authorization.
- Document data-integrity scope, affected keys, and delete/TTL timelines—not merely API latency.

**Crossing `gc_grace_seconds` does not guarantee resurrection occurred**: both missed deletes and tombstone purges must align. Still, drained hints never prove safe recovery when grace elapsed.

### 10.4. Supporting Tombstone Telemetry

Per target table:

~~~bash
nodetool tablestats incident_lab.state_by_account
nodetool tablehistograms incident_lab state_by_account
nodetool compactionstats
~~~

JMX/exporter equivalents include `TombstoneScannedHistogram`, `SSTablesPerReadHistogram`, partition-size histograms, compaction backlog, and disk stats. They illuminate read amplification and storage state, **never counting exact mutations missed by N2**. Never assume a single `SELECT` checks tombstones on every replica.

## 11. Multi-DC, RF, `LOCAL_QUORUM`, and Consistency

### 11.1. Local Quorum Is Local, Never Global

Suppose `NetworkTopologyStrategy` configures:

~~~sql
CREATE KEYSPACE incident_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

This is **illustrative DDL** requiring sufficient nodes in both DCs. When a `dc1` service writes at `LOCAL_QUORUM`, it awaits 2/3 natural replicas **inside `dc1`**; `dc2` replicas replicate asynchronously afterward. A client in `dc2` reading at `LOCAL_ONE` or `LOCAL_QUORUM` right after can legitimately see stale values while cross-DC replication lags. Inter-DC hints also obey `hinted_handoff_disabled_datacenters`.

**Never infer from a successful `LOCAL_QUORUM` write in `dc1` that `dc2` replicas hold it**, nor assume a `LOCAL_QUORUM` read in `dc2` immediately sees recent `dc1` writes.

### 11.2. Quorum Math by DC

| RF / scope | Read/Write CL | Replicas required | Constraint |
|---|---|---:|---|
| RF=3 in `dc1` | `LOCAL_ONE` | 1 replica in `dc1` | Can hit stale replica |
| RF=3 in `dc1` | `LOCAL_QUORUM` | 2 replicas in `dc1` | Local read/write quorums intersect on success |
| RF=3+RF=3 across `dc1`/`dc2` | `LOCAL_QUORUM` | 2 replicas in coordinator's local DC | Zero immediate cross-DC read-after-write guarantee |
| RF=3+RF=3 | `EACH_QUORUM` (writes) | Quorum in every DC | Higher latency, cross-DC availability impact |
| RF=3+RF=3 | `QUORUM` (global) | Majority of total natural replicas | Spans DCs; fails if WAN links drop |

Do not switch production apps onto `EACH_QUORUM` casually from this table; choose CLs from domain invariants, WAN RTT budgets, and DC failover tolerance. Transient replication or asymmetric RFs follow dedicated rules.

### 11.3. Java Driver Behaviors to Audit

- `withLocalDatacenter("dc1")` governs coordinator selection and must match physical topology.
- Queries inherit CL defaults from execution profiles; check **runtime executed CL**, not just comments in config.
- Retries and speculative execution fire extra coordinator attempts; never configure policies that silently weaken CL.
- `ConsistencyDowngradingRetryPolicy` undermines visibility and availability guarantees across failures/failovers—never enable it to mask stale reads.

During cross-DC isolation, **separate `Unavailable`, timeouts, and genuinely stale results**. One request cannot simultaneously return a stale row and throw a timeout—track each bucket cleanly.

### 11.4. Divergence Following Topology Transitions

`Joining`, `Leaving`, `Moving`, or **replaced** nodes shift token ownership and host UUIDs. Old hints created for a prior host identity never substitute for bootstrap streaming or replacement repairs.

Document on topology incidents:

~~~text
cluster name / partitioner / token ranges
keyspace NetworkTopologyStrategy and RF per DC
node host IDs, addresses, DC/rack, Up/Normal vs Joining/Leaving
replacement/bootstrap/decommission timeline
schema agreement and table options
hint holder/target peer IDs where available
repair/streaming status
~~~

Never delete orphaned hint files before confirming target host identity against runbooks. Legacy hint artifacts without live targets require version-specific cleanup checks—never delete files by hand simply because an IP vanished from `nodetool status`.

## 12. Sizing Hint Backlogs and Replay Bottlenecks

### 12.1. Sizing Models Guide Budgets—Not Replace Metrics

Rough creation estimate:

\[
\text{hint bytes/s}
\approx
\text{affected writes/s}
\times \text{serialized mutation bytes/write}
\times \text{missed replica copies}.
\]

Use this to budget disk and network capacity **before replay starts**, never as an exact byte counter. Hints undergo segmenting, compression, and batching with serialization overhead and policy caps; one business action may emit multiple mutations, and hints spread across coordinators.

**Hypothetical numbers**:

~~~text
Affected mutations: 1,000 writes/s
Mean serialized mutation: ~2 KiB
Missed replicas: 1
Estimated logical hint creation: ~2,000 KiB/s
~~~

Whenever delivery lags behind creation (target Down/flapping), backlog climbs. Once target stays Up, directory bytes trend downward, yet disk size alone never tells delivered writes apart from skipped/failed writes.

### 12.2. Why Cranking Up Throttles Doesn't Always Help

Suppose holders have spare CPU/NIC headroom while returning target N2 is already busy compacting or GCing:

- Faster delivery pushes more mutations onto N2 → memtable, commit log, and disk I/O surge.
- Live user reads compete against replay writes on N2.
- Target timeouts multiply → net hint delivery success rate **falls** even as configured throttle rises.
- Multiple holders replaying simultaneously can overwhelm N2's NIC, CPU, or disk.
- A massive replay triggers subsequent flushes and compactions, keeping user p99 elevated even as hint queues shrink.

Tune hint throughput only against the **proven bottleneck** (artificial throttle cap vs. target disk/network saturation), changing **one parameter at a time** with explicit stop conditions—never crank both `max_hints_delivery_threads` and throttle at once.

### 12.3. Recovery Progress Dashboard

| Phase | Observe | Healthy progression sign |
|---|---|---|
| While target Down | `Hints_created`, directory bytes, `not-stored` | Known creation rate and storage headroom |
| Immediately after Up | `HintsSucceeded`/`Failed`/`TimedOut`, target CPU/I/O | Delivery kicks off without sustained errors |
| Mid-replay | Directory bytes, `Hint_delays` p95/p99, NIC/throttle | Delay falls over time; target stays healthy |
| Post-drain | Verification reads, app errors, repair schedule | Zero stale reads across scoped checks |
| Post-repair | Repair status, range coverage, data audits | Confirmed replica reconciliation |

**Never equate hint delivery p99 with end-user request p99.** Delivery latency tracks async hint shipping; API/CQL latency tracks live user calls. Tie them together via timestamps and shared node bottlenecks, not unit equivalence.

### 12.4. Watch Metric Types and Process Resets

| Type | Examples | Trap |
|---|---|---|
| Counter | `TotalHints`, `Hints_not_stored` | Resets on node restart; never misread negative drops as "backlog cleared" |
| Meter | `HintsSucceeded`/`Failed`/`TimedOut` | Rolling rate over scrape interval, not pending queue depth |
| Histogram | `Hint_delays` | Percentiles summarize sampled deliveries, not unsent queued items |
| Gauge / file bytes | `hints_directory_bytes`, free disk | Jumps on segment flush, rotation, and deletion |
| Events | Target Down/Up, delivery errors | Log drops or clock skew can omit transitions |

Never sum p99 latencies across two holders to estimate cluster p99; aggregate histogram buckets properly. If restarting N2 or a holder wiped exporter counters back to 0, zero **never proves** the backlog resolved.

### 12.5. Pre-Agreed Recovery Budget

~~~text
Maximum user-visible stale-read rate at required CL: per SLO
Target recoverable hint age: per retention/repair policy
Maximum added disk pressure: within disk headroom
Target end-to-end recovery window: per maintenance SLA
Failed hints: zero sustained, or every failure triaged
Repair coverage: target keyspaces/tables/ranges/DCs per runbook
Outstanding UNKNOWN writes: reconciled or assigned clear owner
~~~

Where data correctness is non-negotiable, never declare incident closure solely from "p99 dropped" or "hint folder is empty". Enforce business-level data verification gates.

## 13. RF=3 Lab: Intentionally Reproducing Replica Lag Safely

### 13.1. Strict Prerequisites

Required setup:

- **Three Cassandra nodes** in a real local DC named `dc1` (Cassandra 4.1+ or 5.0), strictly an isolated learning cluster.
- Dedicated test networks/volumes holding zero production data; authority to stop/start **one lab node**, rollback runbook, and time bounds.
- `NetworkTopologyStrategy` RF=3 keyspace with verified schema agreement prior to testing.
- Client host running `cqlsh`/Java Driver plus `nodetool`/JMX access and UTC-synced clocks.
- Simple PK-only table without TTL or LWT for the baseline drill (test TTL separately).
- **Never** run node-stop or fault drills in shared staging or production.

With only a single node (RF=1), you can practice inspecting hint configs and CQL commands, yet **cannot** observe quorum writes surviving a replica outage.

### 13.2. CQL Lab Setup

In the isolated lab only, after verifying DC names:

~~~sql
CREATE KEYSPACE IF NOT EXISTS incident_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS incident_lab.state_by_account (
    account_id uuid PRIMARY KEY,
    state text,
    revision bigint,
    updated_at timestamp
) WITH read_repair = 'BLOCKING';
~~~

`IF NOT EXISTS` **never modifies** an existing mismatched keyspace or table. Verify RF, DC, and table properties via `DESCRIBE KEYSPACE incident_lab` and `DESCRIBE TABLE ...` in `cqlsh` first.

Write baseline row:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO incident_lab.state_by_account
  (account_id, state, revision, updated_at)
VALUES
  (11111111-1111-4111-8111-111111111111,
   'PENDING', 1, '2026-11-21T09:00:00Z');

SELECT state, revision, updated_at
FROM incident_lab.state_by_account
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

`updated_at` is an application column for auditing; Cassandra's internal LWW write timestamp **is separate** from this column. Never assume setting a newer `updated_at` guarantees LWW victory against concurrent writers.

### 13.3. Phased Drill

**P0 — Preflight.** All three nodes `UN`, schema agreed, `CL=LOCAL_QUORUM`. Capture `nodetool status` from at least two nodes, baseline hint metrics per holder, free disk, and client p99.

**P1 — Stop N2 (lab only).** Stop container/process per lab runbook. Wait until **N1 and N3 gossip marks N2 Down**; before failure detection settles, initial write timeouts can happen and must be logged separately.

**P2 — Write `v2` during downtime.** From a client talking to healthy N1/N3:

~~~sql
CONSISTENCY LOCAL_QUORUM;
UPDATE incident_lab.state_by_account
SET state = 'APPROVED',
    revision = 2,
    updated_at = '2026-11-21T09:07:00Z'
WHERE account_id = 11111111-1111-4111-8111-111111111111;
~~~

If `LOCAL_QUORUM` returns `SUCCESS`, record the UTC timestamp and operation ID. On timeout, **never label it a successful quorum write**; mark `UNKNOWN` and reconcile separately.

**P3 — Snapshot hints on holders.** Capture `TotalHints`, `Hints_created-<PeerIP>`, hints directory bytes, `Hints_not_stored`, disk/GC stats, and N2 Down state. Never inspect raw hint payloads or turn on cluster-wide debug logs.

**P4 — Restart N2.** Wait for N2 to return `UN`; monitor `HintsSucceeded`/`Failed`/`TimedOut`/`Hint_delays` on N1/N3 alongside N2 CPU, I/O, and network. Never restart holders or wipe hints.

**P5 — Verification reads.** Use Section 8's Java probe or `cqlsh`:

- `LOCAL_ONE` **may** return `v1` or `v2` depending on replica selection and replay timing; do not hard-assert `v1`.
- `LOCAL_QUORUM` after an ACKed `LOCAL_QUORUM` write (with no competing writes) should return `v2`.
- `BLOCKING` read repair during `LOCAL_QUORUM` queries can **heal discrepancies as you read**; collect metrics/logs prior to probing.
- Capture sampled coordinator and trace IDs without conflating coordinators with storage replicas.

**P6 — Confirm convergence.** Wait for hint drains across holders, spot-check sample keys/revisions, and verify repair needs. Never claim convergence solely from one `SELECT` or shrinking hint folder bytes.

### 13.4. Lab Observation Worksheet

| Phase | UTC | N2 state | Holder disk bytes | `HintsSucceeded` rate | Failed/Timeout rate | LQ read revision | ONE read revision |
|---|---|---|---:|---:|---:|---|---|
| P0 | _fill_ | UN | _fill_ | _fill_ | _fill_ | 1 | 1 (or matching) |
| P2 | _fill_ | DN | _fill_ | _fill_ | _fill_ | 2 if write ACKed | Nondeterministic |
| P4 | _fill_ | UN | _fill_ | _fill_ | _fill_ | 2 under baseline assumptions | 1 or 2 |
| P6 | _fill_ | UN | _fill_ | _fill_ | _fill_ | 2 (no newer updates) | 2 once replicas converged |

**Never fabricate numbers.** Even if `LOCAL_ONE` happens to return `v2` right after N2 rejoins, the drill still proves hint creation, replay, and CL behavior—and does not disprove stale reads under live production skew.

### 13.5. Extended Drill: Downtime Exceeding `max_hint_window`

This drill takes longer and adds operational load. Run only inside an **isolated lab** during an approved window, and **never** alter `gc_grace_seconds` just to rush results.

1. Write `v1` across RF=3.
2. Keep N2 Down past the **actual configured** `max_hint_window`.
3. Issue writes both before and after the window boundary, logging exact UTC times, ACKs, and CLs.
4. Track `Hints_not_stored` and hint directory growth across holders.
5. Restart N2 and inspect how later writes lacked hints.
6. Build an I/O-bounded **repair plan** once N2 stabilizes.
7. Verify ledger keys/revisions **before and after repair**—never judge repair solely by `nodetool` exit status.

**Never assume** `Hints_not_stored` increments cleanly 1:1 per write across every release/config; watch exact counters and window mechanics. If runtime limits prohibit a multi-hour test, run a labeled tabletop drill instead of weakening grace safety guards.

### 13.6. Negative Test: Timeout Outcomes

If a client write times out while N2 is Down:

~~~text
Input intended: revision=3, state='REVIEW'
Response: WriteTimeoutException at LOCAL_QUORUM
Known: coordinator, CL, required vs. received responses (if reported)
Unknown: whether N1, N3, or N2 persisted the mutation at any moment
~~~

**Never blindly replay that mutation with a fresh TTL or counter/list append** and declare consistency intact; reconciliation requires operation ID, key, value, timestamp, and verified idempotency. Timed-out writes often commit on at least one replica; reading `revision=3` later does not convert an `UNKNOWN` timeout retroactively into an ACK.

## 14. Five Solved Troubleshooting Cases

### 14.1. Case A — Node Returns `UN` Yet Hint Replay Lags

**Scenario:**

~~~text
09:05Z  N2 goes Down
09:07Z  v2 write at LOCAL_QUORUM returns SUCCESS
09:45Z  N2 returns Up; app reading LOCAL_ONE intermittently sees v1
09:47Z  HintsSucceeded climbs on N1 while N3 logs HintsTimedOut
09:50Z  N2 disk utilization high; N1 and N3 both view N2 as UN
~~~

**Diagnosis & approach:**

1. Confirm from the operation ledger that **v2 truly ACKed at `LOCAL_QUORUM`** for that PK.
2. Compare `LOCAL_ONE` vs. `LOCAL_QUORUM` on the key under approved CL/sampling with low-rate traces.
3. Inspect **both N1 and N3** as hint holders—not solely N2.
4. Rising `HintsSucceeded` confirms replay progress; rising `HintsTimedOut` alongside N2 disk saturation reveals why delivery stalls.
5. Protect headroom on N2 by inspecting disk I/O, GC, and network. Provided zero hints missed creation and steady replay continues, **observe progress cleanly** before triggering repair.
6. Pass exit criteria only when spot checks converge, stale errors drop under target CL, delivery failures clear or are accounted for, and repair schedules remain intact.

**Avoid:** cranking hint throttles 10x immediately, deleting hints, or restarting N2 again blindly.

### 14.2. Case B — `Hints_not_stored` Climbs After Extended Downtime

**Scenario:**

~~~text
T0       N2 goes Down
T0+1h    Successful LQ writes; hints stored
T0+4h    Successful LQ writes; default max_hint_window is 3h
T0+5h    N2 returns Up
T0+5h15  Later writes are likely still missing on N2
~~~

**Diagnosis & approach:**

- Check **effective** `max_hint_window` on live nodes rather than assuming 3h.
- Inspect `Hints_not_stored-<N2>` across all holders and correlate timestamps.
- Distinguish **stored hints** from the early outage vs. **unhinted mutations** written after window expiry.
- Plan a **properly scoped anti-entropy repair** once N2 stabilizes and required replicas are `UN`.
- After repair completes, audit ledger keys/revisions and cluster health—never trust exit status alone.

**Avoid:** waiting forever for uncreated hints to replay, or launching repair while N2 still flaps.

### 14.3. Case C — Replica Down 12 Days; Deleted Records Reappear

**Scenario:** Table has `gc_grace_seconds=864000` (10 days). N2 stays Down 12 days while deletes ACK on N1/N3. Compaction purges eligible tombstones. After N2 rejoins, users report deleted records reappearing.

**Diagnosis & approach:**

1. Escalate immediately as a **data-integrity incident**, not a routine hint backlog.
2. Collect delete operation IDs, timestamps, repair logs, `gc_grace` policies, SSTable/compaction records, and affected partitions.
3. **Never run blind full repair**; stale records on N2 can overwrite deletions back onto healthy nodes if tombstones already purged.
4. Reconcile authoritative state via backups, operation logs, and source-of-truth systems; isolate or rebuild N2 per approved recovery runbooks.
5. Enforce preventive repair schedules well inside `gc_grace_seconds`.

**Key takeaway:** 12 days Down **does not automatically prove** zombie data occurred—you must confirm missed deletes + purged tombstones + resurrected reads.

### 14.4. Case D — Cross-DC Stale Reads Even With Healthy Local Quorum

**Scenario:** RF=3 in both `dc1` and `dc2`. Client in `dc1` writes `v2` at `LOCAL_QUORUM` (`SUCCESS`). Immediately afterward, a `dc2` client reading at `LOCAL_QUORUM` returns `v1` while WAN latency climbs.

**Diagnosis & approach:**

- Verify each client's `localDatacenter` routing and executed CL.
- Recognize `LOCAL_QUORUM` in `dc1` never waits on `dc2` ACKs—do not assume broken hinting right away.
- Inspect cross-DC network links, `hinted_handoff_disabled_datacenters`, topology, and lag windows.
- Align cross-region read-after-write SLAs with appropriate CL/routing rather than treating independent `LOCAL_QUORUM` pools as globally serialized.
- Never enable `ConsistencyDowngradingRetryPolicy` to hide failures.

**Key takeaway:** A local quorum write in one DC never forces overlap with a separate DC's local quorum.

### 14.5. Case E — Zero Replication Lag; App Cache or Clock Skew Stale Data

**Scenario:** HTTP clients see `v1` through an API cache for 5 minutes while direct CQL reads return `v2` at both `LOCAL_ONE` and `LOCAL_QUORUM`. Alternatively, direct CQL returns `v1` because the client wrote `v2` using a manual `USING TIMESTAMP` older than `v1`'s write timestamp.

**Diagnosis & approach:**

1. Safely bypass the HTTP/app cache and diff direct CQL outputs against API payloads for identical keyspaces and PKs.
2. Inspect cache invalidation hooks, TTLs, JSON serialization, and partition-key bucketing.
3. If Cassandra itself holds `v1`, query `WRITETIME(column)` to inspect effective write timestamps and concurrent writes—never infer winners from `updated_at`.
4. Audit write CL logs and CAS outcomes; the mutation may have been ACKed yet lost LWW ordering.
5. Once zero replica divergence is confirmed, **do not** run cluster repair simply because an HTTP tier served stale JSON.

**Key takeaway:** "The user saw stale data" and "Cassandra replicas diverged" are distinct claims requiring independent proof.

### 14.6. Quick Discrimination Table

| Case | Strongest signature | Priority track |
|---|---|---|
| A | Target rejoined; hints draining alongside timeouts/I/O lag | Stabilize target disk/GC, watch replay, verify |
| B | Outage exceeded `max_hint_window`; `Hints_not_stored` rose | Scoped anti-entropy repair once target stabilizes |
| C | Outage exceeded `gc_grace_seconds`; deleted rows reappear | Data-integrity recovery; block blind repair |
| D | Write `LOCAL_QUORUM` in `dc1`, stale `LOCAL_QUORUM` in `dc2` | Fix cross-DC consistency contract / WAN lag |
| E | Direct CQL fresh while API stale, or older LWW timestamp lost | Cache/DTO/timestamp fix—stop blaming hints |

## 15. Anti-Patterns, Incident Reporting, and Recovery Sign-Off

### 15.1. Sixteen Misconceptions to Reject

| Misconception | Why it fails | Correct practice |
|---|---|---|
| "N2 is `UN` so data is synced." | Gossip liveness ≠ replica convergence | Gather hints, repair, and verification evidence |
| "`Hints_created` means target received it." | Hint sits on the coordinator/holder | Monitor actual deliveries and target state |
| "Hints vanish automatically after 3h." | `max_hint_window` governs *creation* only | Separate retained hints vs. unhinted writes |
| "One holder's hints folder is empty so none remain." | Hints scatter across coordinators | Inspect all holders across cluster |
| "`TotalHints` equals pending backlog." | Cumulative counter resetting on restarts | Pair rates, directory bytes, and per-peer stats |
| "`HintsSucceeded` climbing removes repair need." | Hints are best effort and miss edge cases | Keep scheduled repairs and integrity gates |
| "Launch repair right away while N2 is Down." | Fails or stalls quorum while burning I/O | Stabilize topology and pass preflight first |
| "Repairing one node repairs the cluster." | Scoped only to that node's token ranges | Orchestrate `-pr` across all nodes/DCs |
| "Read repair replaces full repair." | Covers queried rows/replicas only | Run scheduled anti-entropy repair |
| "`LOCAL_ONE` always returns newest writes." | Any reachable stale replica can respond | Design CL and read routing intentionally |
| "`LOCAL_QUORUM` across two DCs syncs instantaneously." | Separate local DC replica quorums | Enforce cross-DC consistency contracts |
| "`WriteTimeout` proves no replica wrote." | Partial commits succeed frequently | Record `UNKNOWN` and reconcile |
| "Higher `updated_at` wins LWW." | Cassandra uses internal write timestamps | Inspect `WRITETIME` and concurrent writes |
| "Deleting hints makes clusters cleaner." | Destroys recovery path for missed writes | Use `truncatehints` solely per recovery runbooks |
| "`gc_grace_seconds=0` fixes stale reads." | Risks zombie deleted-data resurrection | Size grace safely around repair cadence |
| "Stale API response proves stale replica." | App caches, DTOs, or timestamps often cause it | Compare direct CQL against app caches |

### 15.2. On-Call Incident Report Template

~~~markdown
# INC-... Hinted handoff / stale read

## Scope / UTC
- Last known good: ...
- First known bad: ...
- User impact: % stale responses, read errors, p99, tenant/service/DC
- Node history: N2 Down ... Up ..., gossip source nodes

## Write/read contract
- Keyspace/table/PK shape: ...
- RF by DC, write CL, read CL, serial CL if LWT: ...
- Successful writes: ...
- Unknown timeouts/outstanding operations: ...
- Cache behavior and query fingerprint: ...

## Hints and repair
- Holders inspected (names/host IDs/DCs): ...
- Target identity and state: ...
- Config: enabled, disabled DCs, max window, throttle, delivery threads
- Hints_created, Hints_not_stored, Succeeded/Failed/TimedOut rates
- Hints directory bytes and disk headroom by holder
- Last full/incremental repair scope, outcome, UTC time, and gc_grace

## Evidence
- EV-001: metric link, UTC window, units, source node, snapshot
- EV-002: log/trace ID, UTC window, redacted fields
- EV-003: sampled one/quorum reads, matching PK, results and errors

## Hypotheses and actions
- H1 ... prediction, falsifier, confidence
- H2 ... prediction, falsifier, confidence
- Action ... owner, approval, pre/post metrics, rollback, stop conditions

## Recovery gate
- User SLO under representative offered traffic: ...
- Replica convergence / repair coverage: ...
- Data integrity including deletes/TTL: ...
- Remaining unknown writes/risks and assigned owner: ...
~~~

**Never claim repairs completed or data verified solely from `UN` status.** Keep direct observations, inferences, and hypotheses cleanly separated. Redact raw user IDs and sensitive partition keys; reference pseudonymized IDs and access-controlled links.

### 15.3. Multi-Layer Recovery Gate

Mark an incident **RESOLVED** only once every defined runbook gate passes:

1. **User-facing SLO:** stale rate, errors, and p95/p99 across target queries, tenants, and DCs hold steady under representative traffic.
2. **Cluster health:** targets and holders stable, zero runaway queues, ample disk, GC, network, and compaction headroom.
3. **Hint state:** relevant holders inspected; sustained delivery failures absent; `Hints_not_stored` status explicitly checked.
4. **Data correctness:** sampled ledger keys verified per policy; all `UNKNOWN` writes reconciled or formally owned with deadlines.
5. **Repair coverage:** whenever needed, anti-entropy repair succeeded cleanly over scoped ranges, tables, and DCs.
6. **Deletion safety:** zero unresolved post-grace zombie risk; TTL/delete semantics verified as required.
7. **Operational handoff:** active mitigations/rollbacks carry owners and expiry dates; confirmed root causes or open hypotheses documented.

If p99 looks fine solely because traffic dropped 90%, or `LOCAL_ONE` got hidden behind an hour-long cache TTL, **never** cite that as genuine backend recovery.

### 15.4. Concise Shift Handoff Template

~~~text
INC ID / STATUS: ...
Last good / first bad UTC: ...
Affecting: keyspace/table/service/DC/client version ...
Write/read CL and observed outcomes: ...
Known N2 downtime, max_hint_window, gc_grace: ...
Holders checked / still unchecked: ...
Metrics: created, not-stored, succeeded, failed, timeout, disk
Leading hypothesis and falsifier: ...
What we did NOT do: truncatehints, downgrade CL, unsafe repair
Next safe check and owner: ...
Repair plan / data integrity risk / next update UTC: ...
~~~

## 16. Practice Exercises and Interview Questions

### Exercise 1 — Does Node Up Mean Replicas Caught Up?

N2 goes down 30 minutes and rejoins `UN` in `nodetool status`. Dashboards show `HintsSucceeded` starting to climb. Can you declare all replicas received every write from the downtime?

**Answer:** No. `UN` tracks gossip liveness; rising `HintsSucceeded` confirms active replay, **not complete drain or zero unhinted writes**. Track all holders/targets, failures/`not-stored`, data verification reads, and repair needs.

### Exercise 2 — `max_hint_window` vs. `gc_grace_seconds`

A node is Down 4 hours with `max_hint_window=3h` and `gc_grace_seconds=10d`. Were all hints deleted and did every delete turn into zombie data?

**Answer:** No. The 3h window limits **creating new hints** once Down; saved hints can still replay upon return. The 10-day grace protects tombstones against premature compaction purges; 4 hours alone doesn't trigger zombie data. Still, writes arriving past the 3h window likely need anti-entropy repair.

### Exercise 3 — `W=LOCAL_QUORUM` and `R=LOCAL_ONE`

RF=3 in `dc1`, N2 Down. N1 and N3 ACK `v2` at `LOCAL_QUORUM`. N2 rejoins before hints replay. What can happen if a `LOCAL_ONE` read hits N2?

**Answer:** N2 may return `v1`. Quorum write success never guarantees every replica persisted immediately. A subsequent `LOCAL_QUORUM` read (absent competing writes or clock skew) intersects the ACKed quorum and reconciles `v2`.

### Exercise 4 — "Fixed" Only by Changing CL

An app sees 5% stale reads at `LOCAL_ONE`. Operators switch every query to `LOCAL_QUORUM`; staleness drops while timeouts spike. Is that a root-cause fix?

**Answer:** No. Quorum reads mask divergence via multi-replica reconciliation while trading off latency and availability. You still need to investigate divergence sources, hint/replay/repair progress, and contract requirements; adjust CL only with business approval.

### Exercise 5 — Does Reading `v2` at Quorum Prove N2 Holds `v2`?

An app reads `LOCAL_QUORUM` and receives `v2`. Does every replica now hold `v2`?

**Answer:** No. Quorum reads need responses from only a quorum; read repair updates only participating replicas for that queried partition. Confirm convergence via holder/target hints and repair evidence.

### Exercise 6 — `HintsSucceeded` High Alongside Rising `Hints_not_stored`

After N2 returns Up, `HintsSucceeded` climbs steadily—yet N3 logged `Hints_not_stored` during the outage. Can you merely wait for replay to guarantee completeness?

**Answer:** No. Mutations that **never stored a hint** cannot replay via hints. Plan a properly scoped anti-entropy repair once topology stabilizes and verify key integrity.

### Exercise 7 — Why Inspect Multiple Holders?

An operator inspects `/var/lib/cassandra/hints` on N2, finds it empty, and declares zero hint backlog. What went wrong?

**Answer:** Hints live on **coordinators/hint holders** that handled writes while N2 was unreachable—N2 is the target, not the holder. Check N1, N3, and all active coordinators.

### Exercise 8 — Tracing From a Contact Point

You point `cqlsh` directly at N2 and read `v2` at `LOCAL_ONE`. Does that prove N2's local SSTables hold `v2`?

**Answer:** Not automatically. Even as coordinator, N2 can route or forward reads to another replica. Confirm replica contacts via controlled lab tracing or targeted verification; opening a session to N2 does not pin storage reads to N2.

### Exercise 9 — `ReadTimeoutException` vs. Stale Reads

A read throws `ReadTimeoutException`. Should you log "query returned stale state"?

**Answer:** No. A timeout means **no valid read response completed** within CL/deadline—distinct from a completed read returning `v1`. Keep failure and staleness metrics separate.

### Exercise 10 — Does Incremental Repair Replace Full Repair?

A cluster runs incremental repairs regularly. After SSTable corruption/loss inside data already marked repaired, an operator says "incremental repair will detect and fix it automatically." Why revisit that?

**Answer:** Incremental repairs skip data already marked repaired, missing corruption inside repaired SSTables. Plan a full repair or recovery workflow matching damage scope—while checking first for tombstone resurrection risks.

### Exercise 11 — Deleted Rows Reappear

N2 was Down 12 days on a table with 10-day `gc_grace_seconds`, and deleted rows reappear once N2 rejoins. Choose the safest action.

**Answer:** Escalate as a **data-integrity incident**. Audit deletion logs, tombstones, and repair history; isolate impacted replicas and reconcile from authoritative backups/sources; **never** run blind cluster-wide repair or wipe hints impulsively.

### Exercise 12 — Cross-DC Local Quorums

A `dc1` client receives `SUCCESS` for `v2` at `LOCAL_QUORUM`. Moments later, a `dc2` client reading `LOCAL_QUORUM` returns `v1`. Is this automatically a Cassandra bug?

**Answer:** No. Independent local quorums in separate DCs do not overlap; cross-DC replication may still be in flight. Verify per-DC RF, WAN links, hint policies across DCs, and cross-region CL expectations.

### Exercise 13 — Mutations With Stale Write Timestamps

An API sees `SUCCESS` for `UPDATE revision=3`, yet reads continue returning `revision=2`. The client passed `USING TIMESTAMP` older than `v2`'s timestamp. Should you blame hint backlog?

**Answer:** No. Cassandra resolves mutations via last-write-wins timestamp; an older timestamp loses and stays invisible. Inspect `WRITETIME(col)` alongside operation ledgers and concurrent writers.

### Exercise 14 — Hints Directory Grows by 5 GiB

N1's hints folder swells by 5 GiB while target N2 is `UN`, with flat `HintsSucceeded` and high `HintsTimedOut`. Should you multiply hint throttles 20x right away?

**Answer:** No. Inspect N2 disk I/O, GC, network drops, delivery threads, holder count, and blast radius first. If N2 disks are saturated, cranking throttles increases timeouts. Tune one variable at a time with stop conditions.

### Exercise 15 — TTL Expiry During Replay

An app writes a cell with a 60s TTL during downtime; N2 recovers 5 minutes later. The cell is missing on N2 after hints finish replaying. Did hinted handoff fail?

**Answer:** Not necessarily. The cell's TTL likely expired past the mutation deadline; separate **expected TTL expiration** from **missed mutations**. Check write time, TTL length, write timestamps, and tombstones rather than expecting expired rows to stay alive.

### Exercise 16 — Closing Incidents When Errors Stop

After shedding 90% of traffic, HTTP timeouts hit zero. However, `Hints_not_stored` climbed earlier and N2 hasn't been repaired yet. Can you close the incident as "resolved"?

**Answer:** No—data-correctness gates haven't passed. Verify under representative traffic, complete scoped repair/reconciliation, audit outstanding `UNKNOWN` writes, and assign explicit owners for residual risks.

### Practice Checklist

- [ ] Captured UTC timestamps: last-good, first-bad, N2 Down/Up, write ACKs, replay, repair.
- [ ] Confirmed actual **per-DC** RF and CL rather than code assumptions.
- [ ] Separated `SUCCESS`, `CAS_FALSE`, `UNKNOWN_TIMEOUT`, `UNAVAILABLE`, and `STALE_RESULT`.
- [ ] Distinguished coordinators/hint holders from target natural replicas.
- [ ] Checked `nodetool status` across multiple nodes when suspecting gossip partitions.
- [ ] Treated hints as best effort—never a substitute for anti-entropy repair.
- [ ] Kept `max_hint_window` (creation window) distinct from replay timeouts.
- [ ] Audited per-DC disabled hinting, windows, throttles, threads, caps, and real directory paths.
- [ ] Monitored `Hints_created`/`not-stored`/`Succeeded`/`Failed`/`TimedOut` and `Hint_delays` per peer.
- [ ] Tracked hint directory bytes, disk space/I/O, target GC/network, and compaction load.
- [ ] Refused to treat `created - succeeded` as exact queue depth without verified semantics.
- [ ] Never equated `UN` node state or one quorum `SUCCESS` with full replica convergence.
- [ ] Ruled out app caches, wrong PK/keyspace, timestamps, TTLs, and concurrent writes before blaming hints.
- [ ] Never assumed a contact point serves reads solely from local disk.
- [ ] Scheduled scoped anti-entropy repairs whenever hints missed writes or downtime exceeded windows.
- [ ] Distinguished incremental vs. full repairs and primary-range (`-pr`) scope across nodes/DCs.
- [ ] Evaluated tombstone/`gc_grace` zombie risks prior to repairing long downtimes.
- [ ] Avoided destructive `truncatehints`, manual file deletions, `disablehandoff`, or silent CL downgrades.
- [ ] Enforced data-integrity gates, repair proofs, SLO validation, and clear handoff ownership.

## 17. Technical References

Use these official starting points to verify details against your **exact Cassandra and Java Driver versions**. Reference docs never replace live production runbooks.

1. Apache Cassandra — [Hints / Hinted Handoff](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hint lifecycle, best-effort semantics, replay, `max_hint_window`, throttling, `nodetool statushandoff`/`pausehandoff`/`truncatehints`.
2. Apache Cassandra — [Monitoring Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): `Storage.TotalHints`, `HintedHandOffManager`, `HintsService.HintsSucceeded/Failed/TimedOut`, `Hint_delays`, and table-level read/compaction metrics.
3. Apache Cassandra — [Read Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/read_repair.html): `BLOCKING`/`NONE`, monotonic quorum reads, read repair on participating replicas/partitions, and limits.
4. Apache Cassandra — [Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, Merkle trees, incremental/full repairs, `-pr`, schedules, and tombstone safety intervals.
5. Apache Cassandra — [nodetool repair](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/repair.html): `--full`, `-pr`, `--preview`, `--validate`, and keyspace/table/range scoping.
6. Apache Cassandra — [Tombstones](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/tombstones.html): delete markers, TTLs, `gc_grace_seconds`, zombie data risks, and purge conditions.
7. Apache Cassandra — [Compaction Overview](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/overview.html): SSTables, tombstone reclamation, compaction I/O, and read latency impact.
8. Apache Cassandra — [cassandra.yaml Configuration](https://cassandra.apache.org/doc/latest/cassandra/managing/configuration/cass_yaml_file.html): hint parameters, internode networking, and release-specific key names.
9. Apache Cassandra — [Data Definition (DDL)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/ddl.html): `NetworkTopologyStrategy`, replication factors, table `read_repair`, and `gc_grace_seconds`.
10. Apache Cassandra — [Data Manipulation (DML)](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): CL, TTLs, write timestamps, `DELETE`/upserts, and conditional writes.
11. Apache Cassandra — [nodetool Status](https://cassandra.apache.org/doc/latest/cassandra/managing/tools/nodetool/status.html): Up/Down/Normal/Joining/Leaving gossip state views.
12. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): read/write timeouts, unavailable handling, default retry policy, and downgrading hazards.
13. Apache Cassandra Java Driver 4.19 — [Statement Attributes](https://apache.github.io/cassandra-java-driver/4.19.0/core/statements/): immutable statements, consistency levels, timeouts, tracing, and idempotency.
14. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): execution profiles, local DC, and default CL/timeouts.
15. Apache Cassandra Java Driver 4.19 — [Tracing](https://apache.github.io/cassandra-java-driver/4.19.0/core/tracing/): `ExecutionInfo`, per-query traces, sampling, and `system_traces`.
16. Apache Cassandra Java Driver 4.19 — [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): session/node metrics, in-flight limits, connection pools, and request attempts.

**Conclusion:** Hints help replicas catch up after outages, yet remain strictly a **best-effort recovery mechanism**. To diagnose stale reads accurately, verify **write outcomes**, **replica sets/CL**, **hint holder and target states**, and **TTL/timestamps** before choosing between **monitoring replay or scheduling anti-entropy repair**. An incident finishes only when both **user SLOs** and **data correctness** pass verification—not merely because every node returned to `UN`.
