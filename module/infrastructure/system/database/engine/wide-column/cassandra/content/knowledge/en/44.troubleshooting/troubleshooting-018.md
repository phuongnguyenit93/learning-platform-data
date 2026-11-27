# Impact Assessment Before Restart, Scrub, Compact, or Limit Changes

## 1. A "Quick Fix" Command Can Become a Bigger Incident

A six-node **Apache Cassandra** cluster spans two datacenters, serving a Java application writing device telemetry and reading device status. Dashboards show p99 surging on several queries; one node logs SSTable checksum errors while other nodes lose free disk due to compaction backlogs. Four suggestions arrive at once:

- "Restart the slow node to clear caches and refresh connections."
- "Run `nodetool scrub` on the affected table so Cassandra repairs itself."
- "Run `nodetool compact` across the whole table to clear out tombstones."
- "Raise timeouts or tombstone failure thresholds so requests stop failing."

These four actions carry **completely different targets, scopes, side effects, and recovery characteristics**. Restarting never heals a corrupt SSTable on disk. Scrubbing rewrites files and—depending on corruption handling modes—can induce **local data loss**. Major compaction consumes heavy I/O and temporary disk and **never guarantees safe tombstone purging**. Raising timeouts or guardrail thresholds turns fast failures into long-lived resource-hogging queries, pushing the entire cluster into saturation.

~~~mermaid
flowchart TD
    A["Read timeouts / corrupt SSTable / disk pressure detected"] --> B["Isolate symptoms, causes, and blast radius"]
    B --> C{"Enough evidence to assess change impact?"}
    C -->|No| D["Capture metrics, logs, RF/CL, SSTables, repair/backup, capacity"]
    D --> C
    C -->|Yes| E{"Choose action matched to verified root cause"}
    E --> F["Controlled rolling restart"]
    E --> G["Narrowly scoped table/SSTable scrub"]
    E --> H["Compaction aligned with strategy and budget"]
    E --> I["Targeted limit / guardrail / timeout change"]
    F --> J["Canary + measure + verify data correctness"]
    G --> J
    H --> J
    I --> J
    J --> K{"Pass SLOs and safety gates?"}
    K -->|No| L["Halt, contain impact, and recover per runbook"]
    K -->|Yes| M["Expand step-by-step, log audit trail, and follow up"]
~~~

This lesson belongs to the **Troubleshooting** chapter of module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. The module builds mastery of Cassandra's distributed wide-column architecture—especially **partition keys, query-first table design, read/write consistency levels, CQL, replication, compaction, repair, error handling, and the Java Driver**. Operational choices must connect **infrastructure signals** directly to **application read/write contracts**, rather than checking only whether a node booted back up or a CLI exited 0.

**After this lesson, learners can:**

1. State the **expected impact** of restarting, scrubbing, compacting, and modifying limits on availability, durability, consistency, throughput, disk, and rollback.
2. Calculate required quorum from RF/CL, pinpoint natural replicas, and inspect peer health **before taking a replica offline**.
3. Capture an evidence-backed baseline across `nodetool`, logs, JMX, driver metrics, synthetic canary queries, and a data ledger.
4. Distinguish **online `nodetool scrub`** from **offline `sstablescrub`**, normal background compaction from manual major compaction, and protective guardrails from timeouts/throttles.
5. Identify when **NOT** to restart, scrub, major-compact, or loosen guardrails.
6. Design scoped canaries, stop criteria, backup/repair/restore plans, and post-change verification.
7. Write isolated CQL/Java Driver verification checks detecting missing IDs, duplicate writes, consistency regressions, and retry storms.
8. Author auditable change records distinguishing **config rollback** from **data recovery** whenever SSTables were altered.

**Scope:** Examples reflect Cassandra 4.x/5.x, Java Driver 4.x, and standard CQL. Exact `nodetool` flags, config keys, default thresholds, and dynamic reload rules vary across versions, distributions, and Kubernetes operators. **Always check exact-version help and docs in authorized environments before running commands.** This is an impact-assessment guide, not authorization to mutate production systems.

## 2. Four Intervention Categories: Blast Radius and Reversibility

| Operation | Affected system layers | Potential data loss or mutation? | Practical recovery path |
| --- | --- | --- | --- |
| **Restart a Cassandra node** | Process/JVM, connections, memtable flush/replay, gossip, caches, routing, hint catch-up. | Usually preserves persisted writes, **yet drops temporary availability and exposes weak replication/durability**. | Restart process and verify replica catch-up; booting cleanly never closes the incident alone. |
| **`nodetool scrub`** | Table SSTables on target node; verifies/rewrites corrupt records per tool mode. | **Yes**: unrecoverable corrupt rows/partitions may be skipped in certain modes; SSTables and metadata rewrite. | Verified snapshot/backup, healthy peer replicas, repair, or restore; **no** built-in undo button. |
| **`nodetool compact` / major compaction** | SSTables, disk I/O, CPU, compaction debt, read/write amplification, tombstone purge eligibility. | Doesn't delete live cells intentionally, yet rewrites files and purges eligible tombstones (risky if delete sync lagged). | No "uncompact"; reverting bytes requires snapshot/restore (usually unneeded if correctness holds). |
| **Change limits** | CQL guardrails, tombstone thresholds, timeouts, batch/mutation caps, client throttling, compaction throughput. | Usually doesn't alter stored bytes directly, **yet alters fail-fast safety**; can trigger OOM, overload, stale reads, or retry storms. | Revert config/runtime settings **across all nodes/apps**, sometimes needing rolling restarts; reverting config never undoes writes/timeouts already emitted. |

**Reversibility sits on a spectrum:** restarting a process is cleaner to reverse than scrubbing SSTables, yet if a restart interrupts an unacknowledged coordinator write, apps still handle **unknown outcomes**. Config `rollback` never restores pre-scrub SSTable bytes, and `nodetool stop COMPACTION` does not roll back compacted files like a SQL transaction abort.

## 3. Pre-Command Risk Assessment

### 3.1. Six Dimensions to Evaluate

| Dimension | Essential questions to answer |
| --- | --- |
| **Availability** | With one node down, do `LOCAL_QUORUM`/`QUORUM`/`ALL` workloads still retain enough full replicas? Is a second failure looming? |
| **Correctness / durability** | Do hints, repairs, commit logs, disks, and backups prevent losing the sole intact copy of data or tombstones? |
| **Latency / throughput** | Will the action spike SSTables scanned, CPU/GC, disk await, network traffic, request queues, or client retries? |
| **Storage / headroom** | How much temporary disk do rewritten SSTables require? Do snapshot hardlinks, compaction leftovers, hints, and commit logs share that volume? |
| **Scope / blast radius** | One table on one node, one token range, one DC, entire cluster, whole service fleet, or every query sharing a guardrail? |
| **Reversibility / evidence** | Do tested restore backups, rollback steps, stop criteria, clear owners, deadlines, and pre/post metrics exist? |

### 3.2. Assigning **GO / NO-GO / ESCALATE** Status

- **GO for scoped canary:** healthy topology, intact replica coverage, verified readable/restorable backups, ample disk/GC headroom, isolated root cause, clear owner, zero overlapping maintenance jobs.
- **NO-GO:** insufficient live full replicas for active CL contracts; tight disk unable to cover rewrites; zero verified clean backup/replica copy of corrupt ranges; unclear scope; zombie tombstone exposure; missing metrics or abort controls.
- **ESCALATE:** suspected multi-replica corruption on shared token ranges, outages surpassing `gc_grace_seconds`, unconverged schema migrations, multi-DC partitions, unknown-outcome writes, or sole authoritative compliance/legal records affected.

Never treat `nodetool status = UN` as an automatic green light: `UN` merely reports **gossip liveness**, never proving intact SSTables, consistent deletions across replicas, or complete range repairs.

## 4. Topology Preflight: Compute Quorum Before Taking Any Replica Offline

### 4.1. RF=3 Within One Datacenter

Assume `NetworkTopologyStrategy` with three full replicas for a partition inside `dc1`:

~~~text
R1  UN   rack-a
R2  UN   rack-b
R3  UN   rack-c

RF(dc1) = 3
LOCAL_ONE    needs 1 full replica response in dc1
LOCAL_QUORUM needs floor(3/2)+1 = 2 responses in dc1
ALL          needs 3 responses (single-DC keyspace)
~~~

| Cluster posture when stopping one node | `LOCAL_ONE` | `LOCAL_QUORUM` | `ALL` |
| --- | --- | --- | --- |
| R1/R2/R3 all healthy; stop R3 | Satisfiable | **Satisfiable** via R1/R2 | Typically fails (misses 3rd response) |
| R2 already Down; plan to stop R3 | Only R1 left | **Fails** (needs 2 replicas) | Fails |
| R2 `UN` yet choking on timeouts/full disk | May succeed depending on routing | **High risk**—lacks healthy quorum capacity | High risk |

**Distinguish full replicas, transient replicas, and release-specific CL semantics.** This table assumes standard **full RF=3**; never apply naive arithmetic to transient replication without accounting for each replica type and CL explicitly.

### 4.2. Coordinators Differ From Natural Replicas

Java Driver selects a **coordinator** per CQL request—which need not own the target partition's token. Restarting a coordinator disrupts active connections and inflight futures, whereas restarting a **natural replica** directly subtracts quorum capacity for every key it owns. On clusters larger than RF, **stopping one arbitrary node doesn't remove a replica for every single key**.

~~~mermaid
flowchart LR
    A["App CqlSession"] --> B["Coordinator (may not hold replica)"]
    B --> R1["Natural replica R1"]
    B --> R2["Natural replica R2"]
    B --> R3["Natural replica R3"]
    R1 --> C["CL ACKs, latency, and timeouts"]
    R2 --> C
    R3 --> C
~~~

### 4.3. Multi-Datacenter Math

Keyspace `dc1:3, dc2:3`: a `LOCAL_QUORUM` write in `dc1` demands **two full replicas inside `dc1`**—it cannot substitute one replica from `dc2`. Global `QUORUM` across six total replicas needs four; `EACH_QUORUM` (writes) demands local quorum inside every DC. `ALL` breaks whenever any required replica drops. When planning restarts, capture **DC, rack, local-coordinator routing, WAN health, RF, and executed CL per workload**—never extrapolate single-DC tables cluster-wide.

### 4.4. One Node Down Removes Spare Fault Tolerance

At RF=3/`LOCAL_QUORUM`, surviving on two healthy replicas while R3 restarts leaves **zero spare fault margin** for affected token ranges. Never overlap additional restarts, scrubs, heavy repairs, or JDK upgrades on R1/R2 merely because APIs still return HTTP 200.

## 5. Pre/Post Baseline Capture: Never Skip Telemetry

### 5.1. Capture Structured Evidence in UTC

~~~text
Change ID              : CHG-... (lab/production per env)
Incident / hypothesis   : ...
Cluster/DC/keyspace     : ...
Cassandra/JDK/driver    : exact versions ...
Affected node/table     : ...
Observed root symptom   : ...
RF, local CL, serial CL : ...
Start/stop UTC          : ...
Current node/rack health: ...
Last successful repair  : scope/time...
Backup/snapshot tested? : ...
Disk free/GC baseline   : ...
Latency p50/p95/p99     : ...
Offered/achieved QPS    : ...
Timeout/retry counters  : ...
Expected ID/value set   : ...
Operator/rollback owner : ...
~~~

Pair **exact UTC timestamps and versions** before and after changes—never judge "looks faster now" if request mix or throughput dropped simultaneously.

### 5.2. Standard Read-Only Diagnostic Commands

~~~bash
# Run on authorized nodes/clusters, preferring READ-ONLY commands:
nodetool status
nodetool info
nodetool tpstats
nodetool netstats
nodetool compactionstats
nodetool gcstats
nodetool proxyhistograms
nodetool tablestats telemetry_ops.events_by_device_day
nodetool tablehistograms telemetry_ops events_by_device_day
~~~

Exact subcommands and output format vary across Cassandra releases. `tablestats` reports local node/table metrics rather than cluster-wide replica equivalence; `netstats` captures active streaming rather than historical completeness; `compactionstats` never proves safe tombstone purges. If JMX times out on an impaired node, gather server/OS logs instead—**never treat a hung `nodetool` command as permission to fire intrusive commands blindly**.

### 5.3. Inspecting Server Warnings and Per-Query Metrics

| Signal | What it identifies |
| --- | --- |
| `system.log` / GC logs / kernel logs | SSTable checksum corruption, OOMs, disk hardware I/O errors, GC pauses, startup/shutdown failures |
| Read/Write `Latency` and `Timeout` counters | Per-node/per-operation blast radius correlated against app errors |
| `TombstoneScannedHistogram` / `LiveScannedHistogram` | Excessive deletion markers scanned per read (where exposed) |
| `SSTablesPerReadHistogram`, partition size estimates | Read amplification and partition bloat (distinct from total logical rows) |
| `PendingTasks` / `DroppedTasks` | Saturated compaction, read, or write executor queues |
| Driver retries, in-flight, coordinator distribution | Client load shifts during node state changes; retry storm detection |
| Hints pending/delivered, last repair coverage | Catch-up capacity post-restart and deletion-divergence exposure |

Keep raw `tenant_id`, `device_id`, JWTs, cursors, and payloads out of high-cardinality metric labels; aggregate cleanly using `query_name`, endpoint, DC, environment, and error class alongside protected forensic log samples.

## 6. Storage Dependencies: Commit Log, Hints, Repair, and Tombstones

| Mechanism | Primary guarantee / purpose | Maintenance pitfall |
| --- | --- | --- |
| **Commit log + memtable + SSTable** | Local write durability per `commitlog_sync` and flush path | Sudden kills trigger commit log replay; disk/commitlog faults are distinct from JVM process restarts |
| **Hinted handoff** | Coordinators buffer and replay missed mutations for absent peers when allowed | Bounded by window/disk/best-effort; prolonged restarts pile up hints and **never replace repair** |
| **Read repair** | Multi-replica reads reconcile divergences inside queried rows (per CL/version) | Never scans untouched ranges or replaces full anti-entropy repair |
| **Anti-entropy repair** | Compares and syncs token ranges via Merkle trees and streams | Heavy CPU/disk/network cost; cannot resurrect data lost across all replicas |
| **Tombstones + `gc_grace_seconds`** | Protects delete markers while replicas lag or go down | Slashing grace or forcing premature purges creates **zombie data** |
| **Snapshots / backups** | Captures immutable point-in-time SSTable hardlinks and backup manifests | Local hardlinks sit on the same disk—not off-cluster backups or globally consistent SQL snapshots |

**Takeaway:** Assessing a restart, scrub, or compaction always requires checking **surviving peers** and **repair/backup posture**—not just one node's disk or heap. Healthy peer replicas enable healing after scrubbing only when those peers haven't dropped records or purged tombstones prematurely.

## 7. Quick Decision Matrix: Matching Symptoms to Safe Actions

| Evidenced symptom | Restart? | Scrub? | Compact? | Raise limits? |
| --- | --- | --- | --- | --- |
| GC pauses / hung JVM / suspected post-deploy heap leak | **Candidate**, after verifying capacity & code/JDK rollback | Wrong tool | Usually worsens I/O | Raising heap/timeouts often masks bugs |
| Logs prove SSTable checksum corruption on one node/table | **Won't fix** disk corruption | **Evaluate**, after verified clean peers/backups | Doesn't heal corrupt bytes safely | Ineffective |
| Oversized partition with wide range queries | Doesn't alter schema | Doesn't fix partition keys | Doesn't split partition keys | Higher timeouts pin heavy queries longer |
| Heavy tombstone scans from TTL/range deletes | Doesn't cut tombstones | Never scrub to "wipe tombstones" | Helpful when safe, never guaranteed | Raising failure limits risks cluster overload |
| Compaction backlog from I/O starvation & tight disk | Restarts clear caches & inflate queues | **NO-GO** lacking temp disk headroom | **NO-GO** major compaction without headroom | Tune throttles/capacity carefully—never open uncapped |
| `Unavailable` from insufficient full replicas | Restart other nodes **only after** quorum returns | Never run on sole healthy replica | Avoid heavy I/O on surviving replicas | Never silently drop CL to fake green |
| Oversized app `INSERT`/batch warnings | Won't fix producer bugs | Wrong tool | Won't reshape payloads | Raising mutation/batch caps is hazardous; fix writers |
| Read timeouts from client retry storm | Doesn't alter driver retry policy | Wrong tool | Can worsen read stalls | Bigger timeouts/pools worsen storm; cap retries & backpressure |

Use this matrix as an **initial triage map**, never proof by itself. Confirm next: **does this specific command fix the isolated bottleneck without breaking data invariants or SLOs?**

## 8. Restart: Resets Process/JVM State—Never Fixes Corrupt Data on Disk

Restarting a Cassandra daemon drops active native client connections, detaches briefly from gossip/internode channels, then triggers commit-log replay, SSTable loading, cold cache warm-up, and pending hint catch-up while Java Driver reroutes or retries requests.

### 8.1. When Can Restart Help?

- A node sits wedged in a diagnosed JVM/process state after collecting heap/GC/thread telemetry and validating temporary quorum availability.
- Applying **restart-required** `cassandra.yaml` or JVM flag diffs vetted against official version docs.
- Rotating binaries, JDK builds, TLS certificates, or listeners under a checked **compatibility matrix** and approval.
- Only when **disks, peer replicas, and backups** safely cover one node leaving temporarily.

### 8.2. What Restart **Never** Fixes

- Corrupt SSTables or hardware storage errors on disk.
- Bad partition keys growing massive unbounded partitions.
- Excessive tombstones, misconfigured `gc_grace_seconds`, repair lag, or missing hints.
- Slow `ALLOW FILTERING` or unbounded CQL range scans.
- Driver retry storms or buggy application code writing `null` cells.
- Exhausted physical disks, wiped commit logs, or sole-copy data loss.

If restarting brings only minutes of relief before p99 climbs again, return immediately to root cause (GC, compaction, disk, queries, queues) rather than entering a **reboot loop** churning cold caches and hint queues.

## 9. Controlled Single-Node Rolling Restart Runbook

### 9.1. Per-Node Preflight (Run Before *Every* Node)

~~~text
Target node    : R3, dc1/rack-c, host-id verified
Scope          : strictly one process—never multiple pods simultaneously
RF/CL          : full RF=3 in dc1, app uses LOCAL_QUORUM
Remaining      : R1/R2 healthy, responsive, ample disk/CPU/GC headroom
In progress?   : no overlapping repair, bootstrap, streaming, or major compaction
Hints/repair   : handoff active/healthy; downtime fits inside budget
Config/binary  : verified pre/post digests and Java/JDK/driver compatibility
Rollback       : prior binary image/config, owner, and credentials ready
SLO stop gates : read/write errors, p99, R1/R2 stage queues, free disk
~~~

If R2 is already Down or R1/R2 throw `LOCAL_QUORUM` timeouts, **NO-GO** on restarting R3. Never treat a disk-stalled `UN` peer as reliable quorum capacity under load.

### 9.2. Illustrative Lab Commands on Approved Clusters

~~~bash
# 1) Capture pre-restart health from peer nodes:
nodetool status
nodetool tpstats
nodetool netstats
nodetool compactionstats

# 2) Inside an intentional runbook sequence:
nodetool drain

# 3) Operator/orchestrator then stops/starts the target Cassandra process
#    (exact commands depend on systemd/Kubernetes/Docker).
#    Never fire these concurrently across multiple nodes.
~~~

`nodetool drain` flushes memtables and stops client/internode service **requiring a subsequent process restart**—it is not a temporary pause/resume toggle. Some Kubernetes operators manage drain and shutdown internally; **do not double-issue `drain`** without checking operator semantics first.

### 9.3. Step Node-by-Node Only After Verification Gates Pass

1. Log **Change ID + UTC timestamp**, baseline snapshots, and exact host/IP/DC/rack/volume bindings.
2. Confirm **surviving replicas** absorb full traffic at active CL cleanly.
3. Drain/stop only the target node per approved SOP—**never** wipe commit logs, hints, or data volumes.
4. During downtime, watch p95/p99, errors, offered/achieved RPS, pending hints, and disk/GC on R1/R2.
5. Boot the node back with exact matching binary, JDK, config, volumes, host ID, and tokens; watch startup and commit-log replay logs.
6. Wait for peers to report `UN`, native transport listening, schema/ring converged, and clean logs.
7. Monitor hint catch-up, needed repairs, SSTables/compaction, and post-warm-up p99.
8. Run synthetic **full-CL read/write canary checks** validating expected IDs and payloads—never stop at `UN`.
9. Move to the next node only once error budgets and recovery stats stabilize cleanly.

### 9.4. Slow Startups: Don't "Re-Bounce to Speed It Up"

Replaying commit logs, opening thousands of SSTables, initializing metadata, syncing schema, and receiving hints take time. Killing a node 30 seconds into startup due to impatient health probes creates destructive reboot loops. Size startup deadlines generously for dataset/version reality, monitor logs and progress, and **escalate per runbook** if genuinely wedged—never wipe data volumes to force a "clean start".

### 9.5. Kubernetes Operators and Concurrency Controls

For StatefulSets and Cassandra operators, verify:

- **`PodDisruptionBudget` / `maxUnavailable`** match actual RF/CL contracts (PDBs never verify disk or data integrity).
- **InitContainers and liveness/readiness probes** won't prematurely kill slow legitimate commit-log replays.
- **`PersistentVolumeClaim`** mounts stay pinned to exact ordinals and host identities—never swap empty volumes accidentally.
- Operator **rolling-restart, repair, and config-sync rules**.
- **Rack/DC-aware ordering** so two natural replicas of any key never restart concurrently.

**Kubernetes `Ready` never equals Cassandra `UN` + replica convergence**—check both layers.

## 10. Signals Requiring Restart Deferral (`NO-GO`)

| `NO-GO` evidence | Why dangerous | Safer alternative |
| --- | --- | --- |
| Only two full replicas healthy in RF=3/`LOCAL_QUORUM` and planning to restart one | Loses quorum across those keys | Heal the third replica first; halt parallel work |
| Full disks/commitlogs or storage read errors | Restarts don't add disk and risk failed startup | Resolve disk/capacity via runbooks and backups |
| Active bootstrap, replace, decommission, or critical streaming | Ownership and handoffs unsettled | Finish or recover topology operation first |
| Repairs lagging near or past `gc_grace_seconds` | Returning node may hold stale deleted records (zombie risk) | Audit repair/restore/replace plans carefully |
| Unsure which replica holds clean copy after SSTable corruption | Taking down the lone clean copy destroys recoverability | Verify backups/peers first to locate source of truth |
| Surviving healthy peers already timing out `LOCAL_QUORUM` | Pulling another node worsens overload | Shed non-critical load and heal GC/disk bottlenecks |
| Binary/config/JDK rollback untested | Restart can lock in breaking incompatibility | Verify compatibility matrix and release notes |

## 11. Scrub: When Needed and What It Does **Not** Do

**Scrub** reprocesses/validates SSTables for diagnosed data/format corruption on **one node and selected tables**. Certain modes skip unrecoverable corrupt records—making it **neither a tombstone-cleanup tool nor routine compaction maintenance**.

### 11.1. Valid Scenarios to Consider Scrubbing

- Server logs or tools confirm **SSTable checksum, serialization, or format corruption** on specific files/tables/nodes.
- Queries fail reading specific corrupted token ranges, backed by **verified clean peer replicas** or off-cluster backups ready to restore any skipped rows.
- Cassandra/vendor engineering guides specify version-exact scrubbing for a documented SSTable format issue—never triggered merely from app `InvalidQueryException`s.

### 11.2. Scenarios Where Scrub Is the **Wrong** First Move

- Giant partitions or missing clustering ranges: scrub never alters primary keys.
- `ReadTimeout` driven by hot keys, driver throttling, or compaction debt: scrub adds heavy disk I/O.
- Dense legitimate TTL/delete tombstones: scrub isn't designed to purge valid deletion history unsafely.
- Suspected corruption spanning **all replicas and backups** with no clean truth source: rewriting destroys forensic bytes.
- Tight free disk unable to absorb rewritten SSTables and snapshots: scrub risks triggering disk full (`ENOSPC`).

### 11.3. `nodetool scrub` vs. Offline `sstablescrub`

| Tool | Execution model | Primary risk |
| --- | --- | --- |
| **`nodetool scrub`** | Runs online via JMX on a live Cassandra daemon against targeted table(s) | Rewrites SSTables on a serving node; I/O, disk, and data-drop risks |
| **`sstablescrub`** | **Offline** CLI utility operating directly on disk files once Cassandra is cleanly stopped | Risk of hitting wrong paths or corrupting files if Cassandra still runs; strict version/keyspace flags |
| **`nodetool verify` / SSTable verification** | Validates CRCs and structure without necessarily modifying data | Still incurs heavy read I/O; detects faults without replacing repair or restore |

**Never invoke offline `sstablescrub` on live directories** while Cassandra writes or compacts. Never assume identical flags across both tools—verify exact options via `nodetool help scrub` and release-matched CLI help.

## 12. Pre-Scrub Impact Assessment: From Checksum Errors to Clean Recovery Sources

### 12.1. Pin the Exact Blast Radius

~~~text
Affected node        = R3
Keyspace / table     = telemetry_ops.events_by_device_day
SSTable / generation = ... (from verified logs)
Checksum / format    = ... (from verified logs)
Relevant token range = ...
Replica set for keys = R1/R2/R3 (full RF3 example)
Other replicas       = R1/R2 integrity and repair state VERIFIED?
Disk free            = ...
Last full backup     = ...
Last successful repair scope/time = ...
Potential missing mutations/deletes = ...
~~~

One corrupt SSTable spans **numerous partition keys**, so one failing key query never defines full exposure. Log exact table, SSTable generations, ranges, and replica health—never scrub "the entire keyspace just to be sure" blindly.

### 12.2. Protect Data First

1. **Corroborate logs/metrics:** verify checksum/corrupt blocks or physical drive errors vs. driver codec or CQL bugs.
2. **Audit volume health:** if physical storage throws I/O errors, rewriting SSTables onto failing disks worsens damage—plan disk replacement or full node rebuild/restore.
3. **Confirm R1/R2 hold intact data** for impacted ranges via proper verification; one passing `LOCAL_QUORUM` read never verifies R3 or every key across the table.
4. **Take an off-node snapshot/backup with manifests and checksums** while files stay readable. Note local snapshot hardlinks retain **corrupt bytes too**—never mistake local hardlinks for clean off-cluster backups.
5. **Audit repair, TTL, tombstone, and `gc_grace` status:** dropping corrupt tombstones via scrub risks resurrecting older copies from other nodes.
6. **Budget peak free disk** for old SSTables + rewritten output + snapshot hardlinks + commitlog/hints—never size disk from logical CQL row bytes.
7. **Prepare an expected ID/value/delete ledger**, an off-cluster truth/backup source, and clear owner sign-off should scrub discard unrecoverable partitions.

### 12.3. Illustrative Lab Sequence on an **Isolated** Redundant Cluster

~~~bash
# APPROVED LAB EXPERIMENT ONLY; never run blindly in production.
nodetool status
nodetool tablestats telemetry_ops.events_by_device_day
nodetool compactionstats

# Always check release-exact flags FIRST:
nodetool help scrub

# Create tagged snapshot and copy off-node per runbook:
nodetool snapshot -t before-scrub-chg-001 telemetry_ops
nodetool listsnapshots

# ONLY AFTER formal approval and verified off-node backup:
nodetool scrub telemetry_ops events_by_device_day
~~~

**Warning:** Snapshot/scrub flags vary across releases; check live CLI help rather than copying cheat sheets. `nodetool scrub` accepts different options than offline `sstablescrub`. Options like `--skip-corrupted` intentionally **discard corrupt records**: require explicit approval for potential data loss plus post-scrub reconciliation—never enable data-skipping flags merely to get exit code 0.

### 12.4. Critical Snapshot Caveats

Local Cassandra snapshots use filesystem **hard links** to existing SSTables—they are neither full cluster backups nor globally consistent transaction snapshots. Because snapshots pin old files, disk usage may **not drop after compaction or scrub** until snapshot cleanup runs safely. **Never delete snapshots impulsively just because disk fills** if that snapshot guards your sole forensic or rollback copy.

## 13. Post-Scrub Next Steps: Repair, Rebuild, or Restore?

### 13.1. Four Possible Outcomes

| Scrub outcome | Required evidence | Next step |
| --- | --- | --- |
| Finished cleanly with zero discarded data | Scrub logs, disk stats, CQL checks, sampled IDs | Run scoped repair/validation; monitor p99, GC, compaction |
| Skipped/discarded corrupt rows or partitions | Counts/IDs/ranges dropped, corruption logs, loss approval | Recover missing keys via **clean replicas, off-cluster backup, or replay**, then run scoped anti-entropy repair—never equate scrub success with data completeness |
| Aborted due to disk/format/severe corruption | Error logs, temp file status, headroom, snapshot posture | Stop retries; switch to storage replacement, node rebuild, or restore runbook |
| Finished cleanly yet reads still time out | Query shapes, tombstone stats, `SSTablesPerRead`, p99 | Fix root cause (queries, data model, overload)—scrub never cures overload |

### 13.2. Why Repair Helps—Yet Isn't a Magic Bullet

If R1 and R2 retain **every intact cell and tombstone**, anti-entropy repair restores missing ranges onto R3 cleanly. Whenever every replica lost a record or purged tombstones, repair **cannot invent missing history**—you must restore from off-cluster backups, CDC logs, or event replays. Remember too that running repair on one node never covers unaffected tables or remote DCs automatically.

### 13.3. You Cannot "Undo Scrub" via Node Restart

Running `systemctl restart cassandra` never reverts rewritten SSTables. Returning to pre-scrub bytes requires **verified snapshots/backups** restored via release-safe procedures matching SSTable format, permissions, tokens, and replica state. **Never `cp` SSTables straight into live data directories** expecting hot reloads.

### 13.4. Report Outcomes Accurately

Report precisely: "Scrub completed on table X / node R3 with 0 tool errors logged; `LOCAL_QUORUM` ledger spot-checks matched; anti-entropy repair finished across token ranges Y"—**never** claim "all cluster data is 100% clean" purely from `nodetool scrub` exit code 0.

## 14. Automatic Background Compaction vs. Manual Major Compaction

Cassandra writes via an LSM engine: commit logs + memtables flush into immutable SSTables, and automatic compaction merges/rewrites SSTables per configured strategy while enforcing tombstone safety guards. **Manual major compaction** merges vast SSTable sets aggressively at heavy temporary resource cost.

### 14.1. Scenarios Where Manual Compaction May Be Considered

- Proven read amplification / SSTable layout issues backed by benchmarks confirming major compaction actually helps.
- Release- and vendor-documented data maintenance procedures targeting exact tables and versions.
- Post-migration/repair cleanup run under **approved maintenance windows**, ample disk/I/O headroom, and strict canaries.

### 14.2. What Compaction **Never** Guarantees

- Never repairs **corrupt SSTable bytes** safely like a controlled scrub/restore.
- Never splits an oversized device partition across additional tokens/buckets.
- Never unconditionally wipes all tombstones right away: `gc_grace_seconds`, overlap, repaired status, shadowed cells, and strategy still govern purging.
- Never frees disk immediately while snapshots hard-link input SSTables.
- Never runs free of p99 impact: compaction I/O, CPU, and GC compete directly with live reads/writes.
- Never creates global snapshot consistency or replaces anti-entropy repair across diverged replicas.

## 15. Compaction Strategies Dictate Trade-Offs—There Is No Universal "Compact Best" Button

| Strategy | Typical target pattern | Evaluate before manual major compaction |
| --- | --- | --- |
| **STCS** (Size-Tiered) | Merges similarly sized SSTables; favors write-heavy traffic | Read amplification, SSTable counts, giant single output files requiring 2x temp disk, snapshot pin risk |
| **LCS** (Leveled) | Organizes fixed-size SSTables into levels capping reads/SSTable | Write amplification and I/O keeping levels balanced; release-specific major compaction impact |
| **TWCS** (Time-Window) | Mostly append-ordered time-series with uniform TTLs; drops whole expired SSTables cleanly | Major compaction merges across time buckets, breaking isolated whole-SSTable drops; audit late writes/deletes carefully |
| **UCS** (Unified) | Adaptive workloads where Cassandra version/distro supports UCS | Check version-specific params rather than applying legacy STCS/LCS/TWCS habits |

Switching from STCS to TWCS or UCS is **not** a lightweight config tweak: legacy SSTables, compaction scheduling, and resource demand shift over time. Before switching strategies, verify **write timestamp source (server vs. client), TTL uniformity, late arrivals, update/delete patterns**, snapshots, and schemas. **Only redesigning partition buckets** relocates keys across tokens—compaction strategies never alter partition ownership.

### 15.1. Why Major Compaction on TWCS Often Backfires

TWCS isolates SSTables by time window so completely expired files vanish cheaply without touching neighbors. Reckless major compaction collapses time buckets together, letting late writes or un-expired rows pin huge merged files on disk indefinitely. **Never assume "fewer files is always better"** on TTL-driven tables—check exact version behavior and benchmark canaries first.

### 15.2. Tombstone Purge Requires Multiple Conditions

~~~mermaid
flowchart TD
    A["Tombstone exists"] --> B{"Passed gc_grace / retention rule?"}
    B -->|No| C["Retain marker per policy"]
    B -->|Yes| D{"Could overlapping SSTables / older live data resurrect?"}
    D -->|Yes| E["Block unsafe purge"]
    D -->|No| F["Eligible for purge per compaction/repair rules"]
    F --> G["Physically dropped only during qualifying compaction/SSTable drop"]
~~~

This conceptual diagram simplifies Cassandra's full logic (which also weighs repaired state, timestamps, shadowed values, and version flags). **Never** assume every tombstone vanishes the exact second `gc_grace_seconds` passes.

## 16. Resource Budgeting Before `nodetool compact`

### 16.1. Never Size Disk Headroom From Logical CQL Data Bytes

Compaction writes new SSTables **before** deleting inputs. Peak physical storage holds **input SSTables + output under construction + snapshot hardlinks + commitlog/hints + concurrent compactions**. When snapshots pin input blocks, deleting old metadata after compaction returns zero disk space.

~~~text
Illustrative example (not an exact formula):

Table SSTable inputs                 = 420 GiB
Estimated rewritten output           = ~350 GiB (estimate)
Existing snapshots pinning old blocks = 200 GiB linked data
Commitlog / hints / parallel tasks   = 60 GiB

Peak physical storage demand far exceeds
"the table only holds 420 GiB".
~~~

**Account accurately for hardlinks:** while untouched, snapshots share existing blocks with active SSTables—yet **during compaction rewrites**, snapshots hold old blocks while compaction allocates brand-new blocks, spiking **peak used bytes**. Rely on actual filesystem free stats and conservative margins rather than optimistic back-of-the-envelope ratios.

### 16.2. CPU, Disk I/O, and Foreground Traffic Overlap

| Resource | Risk | Metrics to watch |
| --- | --- | --- |
| Disk bandwidth / await | Compaction read/write I/O starves live queries | Disk util/await, read/write p99, pending compactions |
| CPU | Compression, decompression, CRC checks, row merges | CPU saturation, context switches, throttler queues |
| Heap / GC / direct memory | Buffers, bloom filters, metadata alongside active requests | GC pauses, OOM risks, off-heap buffers |
| Free space | Rewrites + snapshot hardlinks exhaust volume | Used/free trends; reserve for commitlog & hints |
| Network (if paired with repair/streaming) | Overlapping background jobs saturate NICs | `nodetool netstats`, repair backlog, RTT, retransmits |
| Recovery window | Long-running or aborted major compaction stalls | Task progress, leftover temp files, SLO impact |

### 16.3. Avoid Concurrent Heavy Operations

Best practice starts with a **single-node/single-table canary**, isolating heavy compaction away from repairs, streaming, upgrades, off-node snapshot transfers, and traffic peaks. When scaling across ranges or nodes, enforce **orchestrated concurrency caps and abort gates**—never fire an unthrottled `for node in cluster: nodetool compact` loop.

## 17. Controlled Manual Major Compaction Runbook

### 17.1. Pre-Run Checks

1. Verify **root cause** genuinely stems from SSTables/read amplification or layout debt—never compact reflexively over random warnings.
2. Audit strategy, version, TTL/delete mix, repaired/unrepaired split, snapshot retention, and `gc_grace_seconds`.
3. Capture free disk headroom, OS I/O, GC, `compactionstats`, `tablestats`, client p95/p99, and CL.
4. Lock exact **node and table** scope (starting with one canary node/table).
5. Verify repair schedules and surviving peer health—never overload sole quorum survivors while another replica sits Down.
6. Confirm **off-cluster backups, rollback/risk plans**, operator stop authority, and hard `NO-GO` thresholds.

### 17.2. Illustrative Single-Table Lab Sequence

~~~bash
# READ-ONLY FIRST:
nodetool compactionstats
nodetool tablestats telemetry_ops.events_by_device_day
nodetool help compact

# ONLY WITH APPROVED CHANGE, ON ONE NODE:
nodetool compact telemetry_ops events_by_device_day

# MONITOR CLOSELY:
nodetool compactionstats
nodetool tpstats
nodetool gcstats
~~~

`nodetool compact` supports release-specific flags (e.g., `-s` split output or user-defined file lists); **never borrow flags blindly** across versions. Expect compaction duration to scale with file size, disk throughput, and strategy—not always finish in one minute.

### 17.3. If Compaction Must Be Aborted

Certain versions offer `nodetool stop COMPACTION` to cancel active tasks cleanly—verify exact syntax, targeted scopes, temp-file cleanup, and post-stop checks for your release. **`stop` is not a transaction rollback** and can leave partial compaction artifacts needing cleanup per runbook. Never `kill -9` Cassandra and manually delete temp files during data issues.

### 17.4. Post-Compaction Validation

- Compare **pre/post baselines** at matching traffic: `SSTablesPerRead`, p95/p99 latency, tombstones scanned, disk usage, GC, and pending tasks.
- Verify event IDs, values, deletes, and TTL states across representative partitions at required CL.
- Confirm whether snapshot hardlinks still hold disk high; expire snapshots solely per retention policies.
- If read latency didn't budge, audit partition keys, clustering ranges, TTL/delete logic, and hot keys instead of repeating major compaction endlessly.

## 18. "Changing Limits" Spans Very Different Mechanisms

### 18.1. Categorizing Limits by Control Layer

| Limit category | Conceptual examples | Side effects when raised blindly |
| --- | --- | --- |
| **Server protective thresholds** | Tombstone warn/fail thresholds, partition-size guardrails, query limits | Permits abusive scans/writes to burn CPU, disk, and RAM longer, impacting shared tenants |
| **Request timeouts** | Server read/write/range timeouts, driver request timeouts | Extends request lifetimes, bloats in-flight/queues, widens write `UNKNOWN` windows |
| **Mutation / batch size caps** | Batch warn/fail thresholds, max mutation size, collection/cell caps | Slams commitlog, memtable, network frames, heap, and compaction—never fixes schema |
| **Throughput / capacity throttles** | Compaction throughput, concurrent compactors, hint/stream throttles | Too low builds backlogs; too high starves foreground latency and disk |
| **Driver / client throttling** | In-flight limits, pool sizes, page sizes, retries, speculative execution | Drives retry storms, hot-replica overload, heap/network strain, and tail spikes |
| **Java / JVM / container limits** | Heap `-Xmx`, GC tuning, cgroup CPU/RAM caps, thread pools | Triggers `OOMKilled`, prolonged STW pauses, or host swap contention |

**Two commonly conflated moves:** raising a **guardrail failure threshold** lets previously blocked queries run deeper; raising a **timeout** keeps slow requests alive longer. Both widen **blast radius** even if HTTP 5xx counts appear to dip initially.

### 18.2. Server Limits, Driver Limits, and HTTP Limits Form Three Tiers

~~~mermaid
flowchart LR
    A["Browser / API timeout"] --> B["Java service admission, retries, validation"]
    B --> C["Java Driver request timeout, page size, pools"]
    C --> D["Cassandra server guardrails & timeouts"]
    D --> E["Coordinator + replica CPU, disk, SSTables"]
~~~

If queries scan 100,000 tombstones on disk, raising the **HTTP timeout** never scans fewer markers. Raising **driver page size** trims round trips while ballooning bytes/heap without fixing partition size. Tuning one tier alone often makes adjacent tiers time out unexpectedly—design a cohesive **end-to-end latency budget**.

### 18.3. Config Keys and Units Shift Across Releases

Cassandra 3.x, 4.x, and 5.x altered **property keys, duration/byte units (`_in_ms` vs `ms`), guardrail flags, dynamic JMX reloadability, and defaults**. Never paste a 5.0 `cassandra.yaml` onto 4.0, and never assume `nodetool set...` commands exist or survive restarts. For every setting change, capture:

~~~text
Setting key        : exact property name in deployed version
Scope              : node / DC / cluster / application
Old value/unit     : ...
New value/unit     : ...
Source of truth    : cassandra.yaml / operator CRD / JMX runtime / app config
Dynamic?           : verified against exact server release
Persistence        : survives restart? reconciled by operator?
Rolling restart?   : yes/no per official docs/operator
Rollback command   : ...
Evidence           : pre/post effective values across all affected nodes
~~~

## 19. Tombstone Warning/Failure Thresholds: Case Study in Guardrail Trade-Offs

In supporting Cassandra versions, `tombstone_warn_threshold` and `tombstone_failure_threshold` cap **tombstones scanned during one read query**, not total tombstones on disk. Common historical defaults like 1,000 / 100,000 vary by release—**verify live cluster configs instead of assuming numbers**.

### 19.1. What Happens When You Raise `tombstone_failure_threshold`?

Suppose `SELECT ... LIMIT 20` scans 120,000 tombstones hunting live cells and hits the failure threshold. Raising the threshold unblocks errors superficially—yet forces queries to churn disk, CPU, and heap much longer, risking cascading timeouts across multi-tenant clusters once fail-fast protection vanishes.

| Evaluation factor | What to check |
| --- | --- |
| CQL query shape | Does `WHERE` bind full partition key + narrow clustering bounds? Any `ALLOW FILTERING` or wide scan? |
| Data lifecycle | Are tombstones from TTLs, broad deletes, explicit `null` binds, or unbounded partitions? |
| Per-read resource cost | Tombstones/live cells scanned, `SSTablesPerRead`, CPU/disk/GC, and latency on that key |
| Blast radius | How many tenants/endpoints run that query, retry rate, and shared SLA? |
| Structural fix | Time bucketing, query-first schema redesign, valid compaction/repair cadence |
| Canary if temporary relief forced | Strictly scoped test/timebox with explicit deadline, telemetry, and approved rollback |

**Never** raise guardrails permanently to legitimize broken queries—failure thresholds are **safety circuit breakers**, not pagination tuning knobs.

## 20. Timeouts and Batch/Mutation Sizes: Why "Zero Errors" Isn't Automatically Healthier

### 20.1. Timeouts and Little's Law

In steady state, average concurrent in-flight requests approximate:

\[
L \approx \lambda W
\]

where `lambda` is completed requests/sec, `W` is mean request lifetime (seconds), and `L` is average concurrent requests in flight.

~~~text
Hypothetical example:
500 completed requests/s × 0.05 s mean = 25 in-flight
500 completed requests/s × 0.50 s mean = 250 in-flight
~~~

Whenever raising timeouts pushes **mean request lifetime** up 10x at constant throughput, concurrency, queue depth, and heap occupancy climb proportionally. Remember Little's Law assumes steady state—never substitute **p99** for mean latency or trust it once clusters tip into saturation.

### 20.2. Timed-Out Retries Carry `UNKNOWN` Outcomes

~~~text
Client sends INSERT event_id=E1 at LOCAL_QUORUM
Coordinator forwards mutation to replicas
Response times out / socket drops

Outcome: mutation may have persisted partially or at CL while ACK vanished.
~~~

Never generate a brand-new `UUID` to retry the identical logical event blindly—that creates duplicate business records. Preserve **stable full primary keys**, verified idempotency contracts, and an `ACKED / UNKNOWN / DEFINITELY_REJECTED` ledger. Never mark counters, LWTs, TTL-resetting writes, timestamps, batches, or external-side-effect calls idempotent carelessly.

### 20.3. Larger `BATCH` Sizes Do Not Equal Higher Throughput

CQL `BATCH` **is not a bulk-throughput accelerator** across independent partitions. Multi-partition batches escalate coordinator fan-out, batchlog writes, memtable pressure, and heap demand—loosening batch thresholds just hides structural abuse. Prefer **prepared unbatched statements with bounded async concurrency and stable event IDs**, reserving batches strictly for narrow single-partition atomicity or vetted log contracts.

### 20.4. Enforce End-to-End Deadline Budgets

If an HTTP gateway aborts at 800 ms while the Java Driver waits 5 seconds, orphan `CompletableFuture`s keep burning Cassandra capacity after callers gave up. Enforce:

- Holistic API deadlines with cancellation and backpressure.
- Aligned driver and server timeouts matched to operation CLs.
- Hard retry caps + jitter + global retry budgets—never infinite loops.
- Circuit breakers and admission controls grounded in true capacity rather than returning empty success on errors.
- Telemetry tracking **request rate × physical attempts**, queue depth, p99, timeouts, and exception classes.

## 21. Configuration Changes: Diffs, Effective Values, Canaries, and Rollbacks

### 21.1. One Setting Can Come From Multiple Sources

In live clusters, effective values originate from:

- `cassandra.yaml` and release-specific config files.
- Kubernetes operator CRDs, Helm charts, ConfigMaps, or VM config management.
- Dynamic `nodetool set...` / JMX overrides (where supported).
- JVM flags, OS limits, container quotas, and cgroups.
- Java Driver configs (`application.conf`/`reference.conf`), programmatic overrides, and per-statement attributes.

**Source of truth beats ad-hoc runtime edits.** Kubernetes operators reconciling Git state overwrite JMX tweaks on restart, while editing YAML files stays **inactive** until restart for static settings. Record **effective live before/after values**, not just Git diffs.

### 21.2. Change Plan Matrix for One Setting

| Question | Sample entry |
| --- | --- |
| Cluster & versions | Cassandra 4.1.x, certified JDK, Java Driver 4.x |
| Exact setting & unit | Verified property path (`ms`, `s`, bytes, KiB, or count—never guess names) |
| Source of truth | Operator CRD or config file + authorized approver |
| Dynamic vs. restart-only? | Verified in official docs/binary; if restart needed, layer in **per-node outage risk** |
| Target scope | One canary node, one DC, full cluster, or all Java pods |
| Behavior changed | Fail-fast guardrail, timeout, compaction throttle, or client retry/in-flight cap? |
| Safety gates | RF/CL, free disk, p99, queue depth, safe tombstone/repair bounds |
| Acceptance proof | Identical traffic mix, matching expected IDs/values, errors inside budget, stable resources |
| Rollback | Prior value, source repo, exact revert steps, and **time to take effect** |

### 21.3. Rollout Procedure

1. Capture exact **config diffs** and live effective values across all affected nodes and services.
2. Check if restarts are needed; if so, chain strictly with Section 9's **rolling-restart runbook**.
3. Benchmark **staging/load** on matching Cassandra versions and query mixes with clear pre/post baselines.
4. Roll out to a **tight initial scope** where safe without inducing long config drift across coordinator/replica paths.
5. Watch traffic mix, error classes, p95/p99, retry attempts, JVM/OS disk/GC, and client queues over a sustained window.
6. Verify **domain correctness**: read/write CL, expected event IDs, TTL/deletes/liveness, and authorization rules.
7. Expand node/DC/pod gradually with hard stop gates; on rollback, revert **both source-of-truth config and live runtime overrides**.
8. Re-verify effective settings post-restart/reconciliation, record the change ID, and clean temporary overrides.

### 21.4. Beware Scoped Single-Node Config Canaries

A CQL request hits arbitrary coordinators and multiple replicas. Altering a guardrail or timeout on only one node makes **request behavior depend randomly on routing**, breeding intermittent bugs. Always align routing/observation strictly to canary scope and converge cluster-wide config cleanly post-validation.

## 22. Java Driver Verification: Real Read/Write Canaries Over `SELECT 1`

### 22.1. Full-Partition-Key Canaries

Verify user-facing correctness using a **dedicated probe keyspace** or approved synthetic IDs—never inject test rows casually into production business tables. Strong canaries combine:

- **Deterministic write with stable event ID & full PK** at `LOCAL_QUORUM`, classifying ACK vs. `UNKNOWN`.
- **Verification read on the exact key** at target CL, validating **ID and payload** (not merely HTTP 200).
- **Tight deadlines**, bounded row counts, payloads, and page sizes.
- **Identical query shapes** pre- and post-change to spot regressions reliably.
- Structured telemetry by `query_name`, DC, error class, attempt count, and p95/p99—without logging raw PII.

### 22.2. Dedicated Lab Verification Schema

~~~sql
-- STRICTLY on a test cluster with THREE full replicas in dc1:
CREATE KEYSPACE IF NOT EXISTS ops_preflight
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS ops_preflight.events_by_device_day (
  tenant_id text,
  device_id text,
  event_day date,
  event_time timestamp,
  event_id uuid,
  event_type text,
  payload text,
  PRIMARY KEY ((tenant_id,device_id,event_day),event_time,event_id)
) WITH CLUSTERING ORDER BY (event_time DESC,event_id ASC);
~~~

**Never define `RF=3` on a single-node container** expecting valid `LOCAL_QUORUM` tests—real quorums demand distinct physical replicas. Use **RF=1 in matching local DC** + `LOCAL_ONE` solely for single-container syntax tests, then test RF=3/`LOCAL_QUORUM` on a multi-node cluster.

### 22.3. Java Driver 4.x Canary Probe (Java 17)

~~~java
// CassandraChangeCanary.java
package example.cassandra.ops;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class CassandraChangeCanary {
    private final CqlSession session;
    private final PreparedStatement insert;
    private final PreparedStatement lookup;

    public CassandraChangeCanary(CqlSession session) {
        this.session = session; // Long-lived application-managed session.
        this.insert = session.prepare(
            "INSERT INTO ops_preflight.events_by_device_day " +
            "(tenant_id,device_id,event_day,event_time,event_id,event_type,payload) " +
            "VALUES (?,?,?,?,?,?,?)");
        this.lookup = session.prepare(
            "SELECT event_id,payload,event_type " +
            "FROM ops_preflight.events_by_device_day " +
            "WHERE tenant_id=? AND device_id=? AND event_day=? " +
            "AND event_time=? AND event_id=?");
    }

    public void verify(String runId) {
        String tenant = "lab-tenant";
        String device = "canary-" + runId;
        LocalDate day = LocalDate.of(2026, 11, 21);
        Instant at = Instant.parse("2026-11-21T08:00:00Z");
        UUID id = UUID.nameUUIDFromBytes(
            ("change-canary:" + runId).getBytes(
                java.nio.charset.StandardCharsets.UTF_8));
        String expectedPayload = "alive-" + runId;

        BoundStatement write = insert.bind(
                tenant, device, day, at, id, "PROBE", expectedPayload)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setIdempotent(true);
        session.execute(write); // Exceptions/timeouts require outcome classification.

        BoundStatement read = lookup.bind(
                tenant, device, day, at, id)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setTimeout(Duration.ofSeconds(2))
            .setPageSize(1);
        ResultSet result = session.execute(read);
        Row actual = result.one();
        if (actual == null
                || !id.equals(actual.getUuid("event_id"))
                || !expectedPayload.equals(actual.getString("payload"))) {
            throw new IllegalStateException("Canary value mismatch");
        }
    }
}
~~~

**Conditions on this probe:** the fixture uses **no TTL**, deterministic PK/values on retries, and zero competing writers, justifying `setIdempotent(true)`. Still audit driver retry policies: `WriteTimeout` produces an **unknown outcome** requiring reuse of identical `runId` rather than minting new IDs. Keep `CqlSession` shared across app lifecycle, and treat `Duration.ofSeconds(2)` strictly as an example deadline.

### 22.4. Do Not Misinterpret Canary Results

One passing `LOCAL_QUORUM` read on a synthetic partition **never proves remaining replicas repaired all token ranges**. Canaries will **not** spot SSTable corruption sitting in unrelated ranges/files—combine them with `verify`, repairs, server logs, and broader ledger checks. Furthermore, swallowing errors via `catch(Exception){return List.of();}` renders any canary blind.

## 23. Safe Lab Testbed: Isolated Cluster, Zero Live Production Data

### 23.1. Lab Blueprint

~~~text
Cluster            : dedicated testing Cassandra cluster, zero production data
Nodes              : R1, R2, R3 (full replicas, dc1, distinct rack metadata)
NTS RF(dc1)        : 3
Read/write CL      : LOCAL_QUORUM (3-node test)
Java Driver        : 4.x, single managed CqlSession, bounded concurrency
Table              : ops_preflight.events_by_device_day
Data identity      : deterministic runId/eventId, fixed event_time
Observability      : per-node metrics/logs, UTC markers, CQL ledger
Storage            : ample headroom, separate snapshot/backup mounts
Recovery           : scripted start/stop, verified intact data volumes
No-go              : any endpoint/cluster-ID mismatch against prod
~~~

Remember three Docker containers on one laptop simulate three **processes/replicas** without providing three physical hardware **failure domains**—losing that host kills all three. Verify true rack, DC, storage, and network separation for production-grade drills.

### 23.2. Four Isolated Experimental Runs

| Run | Single isolated change | What must be verified |
| --- | --- | --- |
| **R1** | Restart node R3 while R1/R2 remain healthy | Client CL succeeds cleanly; R3 rejoins & catches up; p99/errors/hints stay in budget |
| **R2** | Scrub a **deliberately corrupted lab table** with clean backups & peers | Live data stays intact; corruption logged; repair/restore cleanly recovers skipped rows |
| **R3** | Major-compact one bounded yet substantial test table/node | Disk headroom, p99/GC bounds, IDs/TTLs/deletes preserved, SSTable deltas measured |
| **R4** | Loosen one guardrail/timeout **in lab** | Quantify fail-fast loss vs. load growth, config scope, rollback, intact CL |

**Never combine all four at once.** Hold fixture shapes, queries, CL, and offered QPS constant to isolate causality accurately.

### 23.3. Abort & Stop Rules Inside Tests

- Fault scripts must whitelist exact **cluster ID and node list**, holding zero credentials for production hosts.
- Assign hard **deadlines** and cleanup hooks restoring processes/configs automatically on test failure.
- Whenever disk headroom drops below safety floors, p99/errors breach budgets, or quorum weakens, **halt expansion and restore availability first**.
- Never auto-run `docker compose down -v` blindly if volumes hold forensic evidence needed after failures.
- Never fire `nodetool scrub` on the only copy of a corruption fixture without snapshots/clean copies first.

## 24. Correctness Verification Pre-, Mid-, and Post-Change

### 24.1. Verify With Ledgers, Not Row Counts Alone

~~~text
run_id:                CHG-001-LAB
operation_id:          stable event UUID
full_partition_key:    (tenant, device, event_day)
full_clustering_key:   (event_time, event_id)
expected_event_type:   PROBE
expected_payload_hash: SHA-256 of payload
write_acked:           true / false / unknown
expected_liveness:     live | deleted | expired
expected_ttl_expiry:   if applicable
consistency_level:     LOCAL_QUORUM
phase:                 baseline | during | recovery | after
~~~

Even when a `DELETE` hides a row at `LOCAL_QUORUM`, **that alone never proves all replicas received the tombstone**—verify repair coverage too. Likewise, `COUNT(*)` can read unchanged even while Event A vanished and Event B duplicated—ledgers must verify **exact IDs, payload hashes, and delete/TTL states**.

### 24.2. Verification Matrix

| Check | Pre-change | Mid-change | Post-change |
| --- | --- | --- | --- |
| RF / CL / ring | R1/R2/R3, tokens, racks intact | Survivors maintain CL cleanly | Target `UN`, zero unexpected Down nodes |
| CQL reads/writes | Baseline IDs/values verified | ACKs, timeouts, `Unavailable` classified accurately | All ACKed IDs/values readable at target CL |
| TTL / deletes | Fixture expiry & deletes valid | Zero grace cuts or stale resurrection | Zero zombie or retention regressions in scope |
| Performance | p95/p99, offered/achieved RPS, CPU/disk/GC | Errors/latency inside stop budget | Returns to baseline under matching traffic |
| Maintenance | Zero conflicting background jobs | Tasks, hints, compaction, streaming advance | Coverage, cleanup, and effective configs verified |
| Rollback | Prior config & tested backup verified | Operator able to halt expansion cleanly | Revert/restore proved successful with evidence |

### 24.3. Mandatory Negative Test Cases

1. **Pre-existing dead replica:** attempting to restart a second replica must trigger **`NO-GO`**.
2. **Tight disk headroom:** scrub and major compaction must block pre-execution.
3. **Unrestorable backup:** destructive `--skip-corrupted` scrub must fail gates.
4. **`CL=ALL`:** stopping one node noticeably breaks availability (unlike `LOCAL_QUORUM`).
5. **Write timeout mid-restart:** ledger marks `unknown`; recovery retries using **identical full PK** without duplicating logical events.
6. **Config drift:** one node holds mismatched tombstone thresholds; canaries expose inconsistent node failures.
7. **Unknown `gc_grace_seconds` / repair lag:** block blind purges/compactions and escalate.
8. **Node returns `UN` with large pending hints:** block restarting the next node solely on `UN` status.

## 25. Measuring Load Without Confusing Offered vs. Achieved Throughput

### 25.1. Hold Workload Shape Constant

~~~text
Query mix   : 70% bounded reads, 30% idempotent inserts (illustrative)
Partition   : device/day telemetry with realistic key skew
Row bytes   : fixed distribution including wide payload tail
CL          : LOCAL_QUORUM, RF=3 full replicas in dc1
Driver      : identical release, pool, retry, and page size per run
Rate        : bounded open-loop arrival schedule with backpressure
Duration    : warmup + steady + change + recovery (UTC markers)
Evidence    : offered/completed RPS, errors, p99, queue/futures,
              disk/GC, hints, compaction, and data ledger
~~~

70/30 splits and sample rates are **pedagogical examples**, not fixed Cassandra defaults. Substitute real workload shapes while keeping them identical across baseline and canary runs.

### 25.2. Closed-Loop Benchmarks Mask Overload

Closed-loop clients wait for each response before firing the next request; whenever Cassandra slows down, **offered rate quietly throttles itself**, hiding runaway p99 under realistic constant user arrivals. Prefer bounded open-loop schedules with explicit in-flight safety caps, reporting coordinated omission, offered vs. achieved throughput, rejections, timeouts, and retries—never load-generator RPS alone.

### 25.3. Performance KPIs Must Require Data Correctness

A change fails regardless of improved p99 if:

- `LOCAL_QUORUM` silently weakened to `LOCAL_ONE`.
- ACKed event IDs disappeared, payloads corrupted, or deleted records resurrected.
- Scrub dropped corrupt records without verified restore/reconciliation.
- Backups or snapshots fail restore verification.
- Config drift causes coordinator-dependent inconsistent errors.
- Compaction exhausts free disk and stalls unrelated writes.

## 26. Observability: Correlating One UTC Timeline Across Nodes and Layers

~~~mermaid
flowchart TD
    A["Change marker UTC"] --> B["HTTP latency, errors, throughput, retries"]
    A --> C["Driver coordinators, in-flight, timeouts, queues"]
    A --> D["Node JVM/OS: GC, disk, CPU, network"]
    A --> E["SSTables, compaction, hints, repairs"]
    B --> F["Correlate by query_name, CL, node/DC in matching window"]
    C --> F
    D --> F
    E --> F
    F --> G["Data ledger, health gates, and next decision"]
~~~

| Source | What it captures | Limit |
| --- | --- | --- |
| API telemetry | p50/p95/p99, HTTP timeouts, cancellations, retries, payload bytes | HTTP 200 never proves all replicas converged |
| Java Driver | Physical CQL attempts, coordinator shares, CL, in-flight, throttler, warnings | Contact point need not be natural replica |
| Cassandra read/write | Latency, `Unavailable`/timeouts, queued/dropped tasks, tombstone/SSTable histograms | One node's histogram doesn't describe all peers |
| Compaction stats | Active/pending tasks, throughput, SSTables | Completing compaction doesn't prove safe purges |
| Hint/repair logs | Hint queues/deliveries, token ranges, streams, failures | Empty hint folder ≠ zero missed downtime mutations |
| OS / JVM | Free disk, await, CPU, GC pauses, off-heap, network RTT | Doesn't identify which CQL query drove load |
| CQL data ledger | Expected ACKed IDs, values, and liveness per key | Spot-checked partitions don't prove every token range |

**Control metric cardinality:** use `query_name`, `change_id`, `local_dc`, `node`, `operation`, and `outcome`; never stick raw `tenant_id`, `device_id`, per-request UUIDs, or payloads into Prometheus labels. Sample/redact forensic IDs strictly in access-controlled logs.

## 27. On-Call Action Selection Flow

~~~mermaid
flowchart TD
    A["Incident: Cassandra errors / p99 / disk / GC"] --> B["Gather evidence: logs, RF/CL, data health, metrics"]
    B --> C{"Enough full replicas for single-node maintenance?"}
    C -->|No| D["NO-GO: restore availability and data sources first"]
    C -->|Yes| E{"Root cause confirmed?"}
    E -->|JVM/process hung| F["Review rolling restart; check binary/config/startup"]
    E -->|SSTable corruption| G["Check backups/peer integrity, scrub/restore options"]
    E -->|SSTable layout / compaction debt| H["Check compaction strategy, disk/I/O headroom"]
    E -->|Guardrail / timeout / batch| I["Audit query/schema/resource budgets before loosening"]
    E -->|Unclear| J["Run bounded diagnostics; keep variables frozen"]
    J --> B
    F --> K["Canary single node/table/config scope"]
    G --> K
    H --> K
    I --> K
    K --> L{"Correctness + p99 + headroom + repair gates pass?"}
    L -->|No| M["STOP, restore availability / revert / restore data"]
    L -->|Yes| N["Expand controlled rollout; audit & follow up"]
~~~

### 27.1. Never Turn This Flowchart Into Blind Automation

Never create an auto-remediation rule like "on corrupt SSTable log → run scrub immediately". Every branch still requires checking **clean replica sources**, tested off-node backups, exact release syntax, and data-loss approvals—and restarts still require **RF/CL** verification with zero overlapping maintenance.

## 28. Case Study A — Restarting a Node Almost Destroys Quorum

### 28.1. Hypothetical Context

`dc1` runs RF=3 for `telemetry_ops`. `R1=UN`, `R2=UN` yet frequently times out reads from disk latency, and `R3=DN` from a network fault. The Java app enforces `LOCAL_QUORUM`, and an engineer proposes **restarting R2 to clear disk stalls**.

| Pre-change telemetry | Observation | Meaning |
| --- | --- | --- |
| R3 `DN` | One full replica offline | Already missing one RF=3 copy |
| R1 `UN` | One healthy replica | Insufficient alone for `LOCAL_QUORUM` |
| R2 `UN`, high disk await/p99 | Running yet degraded | Fragile remaining quorum partner |
| `LOCAL_QUORUM` reads/writes | Demands two full replicas | Stopping R2 immediately breaks quorum |

**Decision:** **`NO-GO` on restarting R2** until R3 recovers or an explicit availability runbook approves failover. First shed non-critical load, diagnose R2 disk/network health, recover R3, confirm R1+R3 sustain quorum cleanly, and only then reconsider R2.

### 28.2. What Happens If Someone Restarts R2 Anyway?

- `LOCAL_QUORUM` reads and writes fail with `UnavailableException` or timeouts while only R1 stays up.
- Driver retries across live coordinators **cannot conjure a second storage replica**.
- Dropping CL quickly to `LOCAL_ONE` restores writes while **violating consistency/durability contracts**—requiring formal incident approval rather than silent tampering.
- Once R2 and R3 return `UN`, check hints, repairs, commit-log replay, and **ACKed/unknown ledger entries**—`UN` alone proves zero convergence.

### 28.3. Lesson

A seemingly routine restart carries a **blast radius dictated by topology and CL**, not familiarity with `systemctl restart`.

## 29. Case Study B — Scrubbing Corruption Without a Recovery Source

Node `R3` logs checksum errors inside one SSTable of the device-state table, while `LOCAL_QUORUM` reads on sampled keys still work. An on-call engineer proposes `nodetool scrub --skip-corrupted` to clear the bad file and silence pages.

### 29.1. Known vs. Unknown Facts

**Known:** R3 holds a corrupt SSTable; sampled quorum reads still pass.

**Unknown:**

- Do R1 and R2 definitely hold every intact cell and tombstone across **all partitions/ranges** inside that SSTable?
- Did missing hints, delayed repairs, or expired `gc_grace` leave R1/R2 diverged?
- Are prior snapshots and off-cluster backups genuinely readable and restorable?
- Did software bugs, storage hardware failures, or version metadata mismatches cause the checksum fault?
- Does the chosen scrub flag **drop corrupt partitions**, and has the business approved that loss?

### 29.2. Decision

**`NO-GO` on potentially lossy scrubbing** prior to verifying trusted recovery copies and a rollback path. Run read-only verification/log checks first, isolate bad hardware if failing, protect files and metadata, and verify clean backups/peers. Only once approved, scrub the exact scoped table/node, record skipped rows/ranges, and restore/repair from verified clean sources.

### 29.3. False Success

Seeing `scrub exit 0` + `nodetool status UN` + `SELECT LIMIT 1` return rows **never proves** skipped corrupt records returned. Audit **expected IDs, values, tombstone states**, logs, repair coverage, and affected partitions directly.

## 30. Case Study C — Major Compaction Fills the Disk Despite Fewer SSTables

### 30.1. Hypothetical Numbers

A node holds a time-series table using 500 GiB across SSTables with 180 GiB free space left on the data volume, plus snapshots holding 250 GiB of older hardlinked blocks. Read p99 climbs alongside high `SSTablesPerRead`, so engineers propose major-compacting the whole table hoping fewer SSTables will immediately shrink used disk.

**Risks:**

- Rewritten output files can demand **hundreds of GiB** before inputs delete.
- Snapshot hardlinks pin input blocks on disk, preventing **any reclaimed space** post-compaction.
- Compaction I/O and CPU spike write latency while commit logs and hints continue consuming storage.
- Under TWCS/time-window TTLs, manual major compaction merges windows and alters expiration drops.

### 30.2. Decision

**`NO-GO` on major compaction without verified peak disk headroom.** Collect `compactionstats`, snapshot inventory, physical free disk, realistic compaction output ratios, `SSTablesPerRead`/tombstones, and staging benchmarks. Prefer:

1. Throttling non-critical batches, backfills, or heavy read queries per policy.
2. Tuning **automatic compaction throughput/concurrency** cautiously so backlogs drain steadily without saturation.
3. Pruning expired snapshots strictly **against verified backup retention rules**—never deleting sole copies carelessly.
4. Expanding storage volumes or migrating skewed schemas onto proper time-bucketed tables.
5. Running scoped compaction afterward only once disk budgets and trade-offs pass review.

### 30.3. Lesson

"Lower SSTable file count" is a secondary internal stat; **disk reserves, I/O headroom, data correctness, and live user p99** remain the real acceptance gates.

## 31. Case Study D — Loosening Timeouts/Guardrails Hides Retry Storms Deeper

A Java API reads 20 events yet scans tens of thousands of tombstones per call. `tombstone_failure_threshold` begins blocking abusive queries cleanly, surfacing HTTP 5xx alerts. One fix proposes multiplying the failure limit 10x and raising driver timeouts from 1s to 15s.

| Hypothetical metric | Pre-change | After raising limits without fixing queries |
| --- | ---: | ---: |
| Offered API requests/s | 600 | 600 |
| Cassandra attempts/s (including retries) | 750 | 1,450 |
| Mean request lifetime | 120 ms | 850 ms |
| Estimated steady-state concurrent requests | Lower | Far higher |
| Tombstones scanned per query | Unchanged | Unchanged |
| Hot-replica CPU / disk / GC | High | Higher |
| Fast HTTP failures | Clear & fast | Fewer initially, yet tail latency & queues degrade |

**Numbers are wholly synthetic**, not real benchmarks. Dropping fail-fast guards lets heavy queries burn cluster resources longer while mismatched client/HTTP deadlines trigger **retry amplification** even as tombstone-error alerts dip.

**Correct remediation:** audit CQL `WHERE`/clustering bounds, partition bucketing, TTL/range-`DELETE`/ORM `null` writes, and compaction/repair posture; cap API ingress, projection fan-out, page sizes, retries, and in-flight limits. Whenever temporary threshold relief is unavoidable under emergency approval, attach hard expiry tickets, canary bounds, p99/error/disk/GC stop triggers, and verified rollback—never labeling it a root-cause fix.

## 32. "Rollback" Carries Four Distinct Meanings—Be Exact

| Change executed | True "rollback" reality | What you must NEVER promise |
| --- | --- | --- |
| Node restart (unchanged binary/config) | Boot node cleanly, restore prior config/image if altered, verify ring, hints, repairs, and canaries | That starting cleanly implies zero missed writes or unknown mutations |
| SSTable scrub | Restore from tested off-node backups/snapshots or healthy peers per runbook + repair/reconcile | Any `nodetool undo scrub` command or node restart restoring old bytes |
| Manual major compaction | Stop ongoing tasks, clean safe temp artifacts, rebalance auto compaction/disk | `stop COMPACTION` restoring the exact pre-compaction SSTable layout |
| Runtime guardrail / timeout change | Restore prior effective values across every node/app, sync source-of-truth repos, verify post-restart | Rolling back writes, deletes, or timeouts emitted while the looser limit ran |
| Compaction strategy change | Revert schema/config under approval and re-plan compaction on already-rewritten SSTables | Instant reversal of physical SSTable file structure |
| Snapshot cleanup / backup deletion | Recoverable solely from surviving off-node replicas/archives | Any "undo delete backup" once storage blocks are gone |

### 32.1. Recovery ≠ Restart ≠ Repair ≠ Restore

- **Restart:** restores process availability without recreating missing cells.
- **Repair:** compares and syncs existing values/tombstones across token ranges—never restores data lost across every replica.
- **Restore:** recovers SSTables/logical records from verified backups matching version, schema, and cutoffs via approved import/streaming—never copy raw files directly into live mutating directories.
- **Rebuild / replace:** topology-level host recovery per version rules—not restarting the exact impaired daemon.
- **Config rollback:** shapes future behavior from rollback onward without rewinding historical mutations.

### 32.2. Stop / Rollback Record Template

~~~text
Reason          : Free disk below floor / quorum lost / data mismatch
Change ID       : ...
Time UTC        : ...
Affected scope  : node / table / config key / cluster ...
Action halted   : ...
Data rewritten? : yes / no / unknown
Backup          : manifest / checksum / restore tested? ...
Restore path    : replica repair / snapshot import / node replace / none
Owner           : ...
Next safe step  : ...
Evidence        : logs, pre/post metrics, expected IDs/values
~~~

**Never hide data gaps behind "rollback succeeded"** when all you did was revert a YAML setting or restart a JVM. Report explicitly **which data state recovered and what scope remains unverified**.

## 33. Operational Anti-Patterns to Avoid

| Anti-pattern | Why harmful | Proper practice |
| --- | --- | --- |
| Restart multiple nodes together ("only takes a few minutes") | Drops quorum, floods hints, cools caches, shifts traffic | Step one node/rack/DC at a time per RF/CL gates |
| Start next node restart right upon seeing `UN` | Hints, repair catch-up, and cache warm-up stay incomplete | Verify catch-up completion and stable SLOs first |
| Run `nodetool drain` expecting auto-resume without restart | Drain halts service intentionally awaiting restart | Follow complete shutdown/restart runbook |
| Restart node to cure SSTable checksum errors | Disk corruption stays intact across restarts | Audit storage/backups/peers; plan verify/scrub/restore |
| Scrub all tables routinely "to keep disk tidy" | Heavy I/O plus data-drop risks | Scrub strictly tables/nodes with proven corruption |
| Run offline `sstablescrub` against live Cassandra data | Concurrent flushes/compaction corrupt files | Stop process cleanly per version offline procedures |
| Pass `--skip-corrupted` reflexively to exit 0 | Silently discards rows/partitions | Require loss approvals, truth ledgers, and restore plans |
| Treat local snapshot hardlinks as hardware-failure backups | Same physical storage can die or store corrupt blocks | Maintain off-cluster checksummed, restore-tested backups |
| Run cluster-wide major compaction near disk full | Demands massive temp output while snapshots pin old blocks | Enforce capacity preflight and scoped single-node canaries |
| Major-compact TWCS tables "down to one file" | Breaks isolated time-window expiration drops | Benchmark release-specific TWCS and late-write patterns |
| Assume `nodetool stop COMPACTION` reverts SSTables | Halts tasks mid-flight without restoring prior files | Verify file state; use tested backups if rollback needed |
| Set `gc_grace_seconds=0` to trim tombstones | Resurrects zombie data whenever replicas miss deletes | Size grace safely around real repair and outage SLAs |
| Raise `tombstone_failure_threshold` to quiet API 5xx | Disables fail-fast, overloading cluster on massive scans | Fix queries, retention, and partition modeling |
| Raise driver timeout far past API gateway deadline | Orphan CQL futures burn DB resources after client aborts | Align end-to-end budgets, cancellation, and backpressure |
| Expand pools/connections infinitely to fix timeouts | Floods hot replicas and queues deeper | Apply admission control, bounded in-flight, and capacity sizing |
| Batch 1,000 partitions in one CQL `BATCH` for speed | Inflates batchlog, coordinator fan-out, and memory | Use prepared unbatched async writes with bounded concurrency |
| Raise CQL mutation caps instead of splitting giant blobs | Struggles commitlog, memtables, frames, and GC | Chunk payloads, normalize, or offload big blobs |
| Tweak JMX runtime settings without updating source-of-truth | Operator reconciles or restarts revert changes silently (drift) | Track desired + live effective configs together |
| Claim `SELECT LOCAL_QUORUM` passing proves R3 synced | Quorum succeeded via healthy peers while R3 lagged | Verify peer-specific hints, repairs, and convergence |
| Claim matching `COUNT(*)` proves zero data loss | Missing ID A + duplicate ID B yield identical counts | Reconcile exact PKs, values, and delete states in ledgers |
| Turn on full tracing across all production requests on overload | Adds severe I/O and `system_traces` bloat | Sample selectively with safe redacted structured logging |
| Run scrub, compact, repair, and upgrades concurrently | Impossible to isolate causality; multiplies I/O storms | Separate phases, enforce stop gates, change one variable |
| Report p99 drop while ignoring halved offered throughput | Coordinated omission / lower load skews closed-loop tests | Keep query mix, offered vs. achieved QPS, and errors constant |
| Catch `Exception` and return empty `[]` on timeouts | Masks DB outages as empty datasets, breaking correctness | Propagate classified errors and clear HTTP contracts |

## 34. True/False Diagnostics to Prevent On-Call Mistakes

| Statement | True / False | Reason |
| --- | --- | --- |
| "`nodetool status UN` proves all replicas converged." | **False** | Gossip membership never proves complete hints, repairs, or sync |
| "`RF=3`/`LOCAL_QUORUM` needs two full replica replies in the local DC." | **True** | Standard behavior for single-DC full RF=3 under `LOCAL_QUORUM` |
| "R3 is Down and R1/R2 are Up; restarting R2 keeps quorum." | **False** | Leaves only R1—one replica short of 2/3 `LOCAL_QUORUM` |
| "Restarting Cassandra repairs corrupt SSTables automatically." | **False** | Disk corruption demands storage verification, scrubbing, or restore |
| "`nodetool drain` pauses traffic temporarily without needing restart." | **False** | Drain shuts down traffic handling cleanly awaiting a process restart |
| "Scrub can rewrite data and demands clean backups or peers first." | **True** | Lossy modes can skip corrupt records irrevocably |
| "Offline `sstablescrub` is safe while live compaction runs." | **False** | Process must stop cleanly per offline SOPs first |
| "Local snapshots guarantee protection against full-disk hardware failure." | **False** | Hardlinks share the failing volume and may preserve corrupt blocks |
| "When corruption hits all replicas, repair recreates lost rows." | **False** | Repair cannot conjure rows missing from every replica |
| "Major compaction consumes heavy temp disk and can hurt p99." | **True** | Output rewrites compete for disk/CPU/I/O while snapshots pin old blocks |
| "Compaction automatically drops every tombstone right at `gc_grace_seconds`." | **False** | Overlap, repaired state, strategy, and compaction schedules govern purges |
| "TWCS always benefits from major-compacting all files into one." | **False** | Merges windows and hurts isolated expired-SSTable drops |
| "Changing compaction strategy changes partition key hashing." | **False** | Storage compaction never alters token assignment |
| "Higher failure thresholds widen the blast radius of expensive queries." | **True** | Disables fail-fast so bad scans tie up cluster resources longer |
| "Driver page size=20 caps replica tombstone scans to 20 markers." | **False** | Page size bounds network round-trip rows, not storage cells scanned |
| "Increasing driver timeouts doesn't optimize the underlying CQL query." | **True** | Simply waits longer while inflating concurrent in-flight pressure |
| "Larger multi-partition CQL `BATCH`es always increase throughput." | **False** | Multi-partition batches add batchlog and fan-out drag |
| "Write timeouts always prove the mutation never applied." | **False** | Outcome stays unknown; replicas may have persisted it |
| "Reverting a JMX threshold undoes mutations emitted while it was raised." | **False** | Runtime configs never roll back historical writes or deletions |
| "Correctness checks must compare exact IDs/values, not row counts alone." | **True** | Counts stay identical across matched drops + duplicates |
| "Repairing one table/range equals a full-cluster repair." | **False** | Must verify full token/table/DC/participant coverage |
| "A single passing canary read proves zero corrupt SSTables remain." | **False** | Unread token ranges and SSTables remain unverified |
| "Adding nodes splits one hot partition evenly across all nodes." | **False** | Single partition hashes to fixed replicas; fix keys/schema |
| "Config rollback, backup restore, and node rebuild are distinct operations." | **True** | Differ vastly in scope, resource cost, and data recovery guarantees |

## 35. Scenario Exercises and Suggested Answers

**Q1.** A single DC uses RF=3 full replicas with `LOCAL_QUORUM`. R3 is Down while R1 and R2 stay healthy. Maintenance wants to stop R2 now—safe to proceed?  
**A:** **No.** `LOCAL_QUORUM` requires two full replicas. Stopping R2 leaves only R1 and breaks quorum. Recover R3 or get explicit availability-window approval first—never silently drop CL.

**Q2.** An RF=3 keyspace writes with `CL=ALL`. R3 stops for a rolling restart while R1/R2 stay Up. Do writes keep succeeding at `ALL`?  
**A:** **No.** `ALL` demands all three full replica replies, so any single-node outage blocks writes—illustrating why restart risk depends on **per-workload CL**, not just node counts.

**Q3.** Why isn't restarting a coordinator equivalent to restarting a key's natural replica?  
**A:** Coordinators handle client routing and fan-out, whereas natural replicas store the partition's token. Drivers often pick coordinators outside the replica set, yet that coordinator still relies on the key's natural replicas.

**Q4.** `nodetool status` shows all three nodes `UN`. Does that prove full data convergence post-outage?  
**A:** **No.** `UN` reflects gossip liveness only—verify hinted handoff drain, scoped repair completion, tombstone/delete safety, and verification ledgers.

**Q5.** During rolling restarts, why wait for startup exceptions, hint queues, and p99 to settle before touching the next node?  
**A:** `UN` appears while caches sit cold and hints/compaction still catch up. Stepping early strips fault headroom and overloads survivors—always confirm **quorum and resource stability** first.

**Q6.** After running `nodetool drain`, will the node resume serving automatically after a few minutes?  
**A:** **No.** Drain flushes memtables and shuts down normal serving pending an intentional process restart—never treat it as a temporary pause/resume button.

**Q7.** R3 reports an SSTable checksum error while `LOCAL_QUORUM` `SELECT` succeeds on one sample key. Are R1 and R2 guaranteed to hold every record from that corrupt SSTable?  
**A:** **No.** Querying one key never checks every partition range, cell, or tombstone. Validate clean peers, backups, and corruption scope prior to scrubbing.

**Q8.** Key difference between `nodetool scrub` and `sstablescrub`?  
**A:** `nodetool scrub` orchestrates over JMX on a running node, whereas `sstablescrub` runs **offline** directly against SSTable files after cleanly stopping Cassandra. Flags/options vary by release, and both require verified backups first.

**Q9.** If a lossy scrub mode exits 0 after discarding corrupt rows, is data recovery done?  
**A:** **No.** Exit 0 only reports the tool finished under its flags—reconcile expected IDs/values and repair/restore discarded data from healthy peers or backups.

**Q10.** Why isn't a local pre-scrub snapshot automatically a sufficient backup?  
**A:** Local SSTable hardlinks share the **same storage** and retain the **exact corrupt bytes**; always back up off-cluster with verified checksums and restore drills.

**Q11.** Post-scrub, R3 dropped a row missing from all peers and backups too. Can full repair recreate it?  
**A:** **No.** Repair replicates surviving data only; lacking any cluster copy requires external CDC/event logs/backups or formal data-loss accounting.

**Q12.** Major-compacting a 420 GiB table with 80 GiB free disk—is headroom sufficient?  
**A:** **Cannot assume sufficient**; rewritten output can demand well past 80 GiB before inputs clear, plus snapshots/commitlog/hints share space. Hold **`NO-GO`** pending proper capacity headroom.

**Q13.** Snapshots hard-link older SSTables. Why doesn't used disk shrink post-major-compaction?  
**A:** Snapshot hardlinks hold references to obsolete input blocks, preventing filesystem reclamation until snapshots expire safely per retention rules.

**Q14.** Should a TWCS TTL table be major-compacted down to one file regularly?  
**A:** **No by default.** TWCS relies on separated time windows to drop expired SSTables cleanly; cross-window rewrites and late writes disrupt retention/I/O. Check exact version rules and benchmark first.

**Q15.** Once a tombstone passes `gc_grace_seconds`, is it guaranteed gone from disk immediately?  
**A:** **No.** Physical erasure awaits qualifying compactions, non-overlapping SSTable checks, repaired state, and purge guards—grace is never an instant cleanup timer.

**Q16.** A replica missed a `DELETE`, and surviving peers purged tombstones prematurely. What risks happening?  
**A:** **Zombie data**—deleted records resurrect upon node return or repair. Maintain repair cadence well inside safe `gc_grace_seconds` rather than cutting grace blindly.

**Q17.** `SELECT ... LIMIT 20` scans 100,000 tombstones. Does raising `tombstone_failure_threshold` make Cassandra scan fewer tombstones?  
**A:** **No.** It merely removes fail-fast protection so queries burn CPU, disk, and latency scanning all 100,000+ markers.

**Q18.** Risk of raising driver timeouts from 1s to 15s while HTTP gateway deadlines remain 800 ms?  
**A:** In-flight CQL requests stay active long after callers abandon them, compounding server load when gateways retry—enforce aligned end-to-end deadlines and cancellation.

**Q19.** Steady 400 req/s sees mean response latency rise from 50 ms to 200 ms. How does average in-flight load shift?  
**A:** Via Little's Law (`L ≈ λW`), concurrency climbs 4x from `400 × 0.05 = 20` to `400 × 0.20 = 80` in-flight requests (valid for steady state using mean latency, never p99).

**Q20.** Why shouldn't teams send thousand-partition CQL `BATCH`es and just raise `batch_size_fail_threshold`?  
**A:** Cross-partition batches amplify fan-out, batchlogs, and heap without boosting bulk speed; switch to prepared unbatched async writes with bounded concurrency instead.

**Q21.** An operator edits `cassandra.yaml` yet sees no runtime behavioral change. Why?  
**A:** Settings may be static (restart-required) or overridden by Kubernetes operator CRDs/JMX. Check release docs for dynamic vs. restart flags and reconcile desired source-of-truth state.

**Q22.** One node runs a tuned threshold while peers hold legacy thresholds. Could queries behave unpredictably?  
**A:** **Yes.** Depending on which coordinator or replica routes a request, identical CQL queries pass or fail inconsistently—always clean up config drift post-canary.

**Q23.** Canary `LOCAL_QUORUM` query passes on a test partition. Does that prove zero corrupt SSTables exist anywhere in the table?  
**A:** **No.** A single partition misses unvisited SSTables and token ranges; run verification, repairs, and broader ledger checks across affected ranges.

**Q24.** Does a `WriteTimeout` during a coordinator restart prove the mutation failed to apply?  
**A:** **No.** Outcome stays `UNKNOWN`; preserve stable full primary keys/event IDs and reconcile rather than generating fresh UUIDs to retry.

**Q25.** Does `nodetool stop COMPACTION` undo rewritten SSTable bytes?  
**A:** **No.** It cancels running compaction tasks per version without reverting completed files; audit temp files and use backups if data rollback is needed.

**Q26.** A tuning change halves p99 while offered throughput also halves. Did performance genuinely improve?  
**A:** **Unproven.** Compare identical query mixes, offered vs. achieved RPS, CL, retries, and payloads without closed-loop omission masking saturation.

**Q27.** Why doesn't a clean repair report on `tableA` prove `tableB` or remote DCs converged?  
**A:** Repairs enforce strict **token, table, participant, and DC scope**—schedule remaining scopes explicitly rather than extrapolating globally.

**Q28.** `LOCAL_ONE` yields faster p99 than `LOCAL_QUORUM`—can operators switch CL mid-incident without review?  
**A:** **No.** Altering CL mutates staleness, durability, and business invariants; require formal domain review and rollback plans.

**Q29.** Running `for node in nodes: nodetool compact` simultaneously causes free disk to plummet. What failed?  
**A:** Uncapped parallelism plus missing peak output/snapshot disk math collided with competing jobs—halt expansion, restore headroom, and step one canary node/table at a time.

**Q30.** Minimum checklist for approving `GO` to scrub a corrupt table?  
**A:** Confirmed node/SSTable/token scope; disk hardware vs. format root cause isolated; clean peers and restore-tested off-cluster backups verified; ample temp disk headroom; `gc_grace`/repair health audited; expected ID/value/delete ledger ready; release-matched CLI flags verified; and explicit loss approval obtained if skipping corrupt data.

**Q31.** Why doesn't rolling back `tombstone_failure_threshold` after an hour erase its past side effects?  
**A:** Config reverts apply strictly forward in time—earlier CPU/GC storms, timeouts, and retries already impacted users and queues; audit cluster SLOs and backlogs post-revert.

**Q32.** An engineer closes an incident citing "`nodetool status UN` and HTTP 200". What proof is still missing?  
**A:** Verified RF/CL headroom, hints/repair/compaction drain, expected ID/value/TTL/delete ledger checks, offered vs. achieved throughput, p95/p99, disk/GC stability, backup readiness, and rollback confirmation.

## 36. Pre-, Mid-, and Post-Change Checklists

### 36.1. Universal Preflight

~~~text
CONTEXT / TOPOLOGY
[ ] Exact cluster ID, environment, DC/rack, host IDs, and ownership confirmed.
[ ] Cassandra, JDK, Java Driver, operator versions, and config source-of-truth pinned.
[ ] Full RF plus normal/serial CL verified across workloads.
[ ] Natural replica sets mapped for impacted token ranges.
[ ] Confirmed zero concurrent Down/lagging replicas would break quorum during node removal.
[ ] Active repair, hints, streaming, and compaction queues inspected.

DATA SAFETY
[ ] CQL schemas, partition keys, query shapes, and target tables documented.
[ ] Expected event IDs/values, TTL/delete expectations, and ACK/unknown ledger ready.
[ ] Last successful repair coverage across tokens, DCs, and gc_grace_seconds checked.
[ ] Snapshot/backup checksums, off-cluster copies, and restore tests verified.
[ ] Verified operation cannot destroy the sole surviving copy of any data.
[ ] Explicit risk approval and recovery source secured if corrupt data could be skipped.

CAPACITY / SLO
[ ] Peak temporary disk + snapshot hardlinks + hints/commitlog headroom calculated.
[ ] CPU, disk await/free, GC, compaction queues, and network retain spare headroom.
[ ] Baseline client p50/p95/p99, offered/achieved RPS, and retries/errors recorded.
[ ] Hard stop criteria and error budgets agreed pre-execution.
[ ] Scoped strictly to single-node/table/config canary with zero overlapping maintenance.

OPERATIONS
[ ] Exact commands/options verified against running version CLI help/docs.
[ ] Change ID, UTC timeline, owner, observer, and escalation chain assigned.
[ ] Explicit abort and availability-restoration procedures prepared.
[ ] Config/binary rollback cleanly separated from data restoration.
[ ] Required logs, telemetry, and backup keys accessible under least privilege.
~~~

### 36.2. Specific to **Restart**

~~~text
[ ] Taking node offline never leaves insufficient full replicas for active CL.
[ ] Surviving replicas show zero disk, GC, or compaction saturation.
[ ] Pre/post binary/JDK/config compatibility verified with tested rollback image.
[ ] Drain/stop/start follows exact operator/systemd/container SOP.
[ ] Persistent volumes, host IDs, tokens, and DC/rack metadata stay unchanged.
[ ] Startup timeout accounts realistically for commit-log replay, cold caches, and hints.
[ ] Wait cleanly for UN + native transport/schema stability + data/SLI validation.
[ ] Block advancing to next node while catch-up hints or p99 remain unsettled.
~~~

### 36.3. Specific to **Scrub**

~~~text
[ ] Exact corruption evidence tied to node, SSTable, table, and token range.
[ ] Ruled out unrelated CQL, codec, or driver bugs.
[ ] Underlying disk hardware health and clean peer/backup sources verified.
[ ] Tested off-cluster backup/restore verified (not merely local hardlinks).
[ ] Online scrub vs. offline sstablescrub selected intentionally.
[ ] Release-exact behavior of skip-corrupted/no-snapshot options verified.
[ ] Zero partition skipping unless formal data-loss approval exists.
[ ] Post-scrub ledger IDs/values/deletes and repair/restore coverage confirmed.
~~~

### 36.4. Specific to **Major Compaction**

~~~text
[ ] Root cause tied to proven SSTable layout / read amplification / debt issues.
[ ] Reviewed STCS/LCS/TWCS/UCS alongside TTL, late-write, and delete patterns.
[ ] Peak physical disk computed including snapshot hardlink retention.
[ ] Zero overlap with heavy streaming, repairs, upgrades, or multi-node compaction.
[ ] Scoped to one canary node/table with disk, GC, and p99 stop triggers.
[ ] Never assume all post-grace tombstones auto-purge instantly.
[ ] Post-compaction SSTablesPerRead, tombstones, p99, disk, and IDs measured.
[ ] Abort handling planned cleanly (stop COMPACTION ≠ rollback).
~~~

### 36.5. Specific to **Limit Changes**

~~~text
[ ] Exact setting name, unit, default, version, and dynamic/static behavior verified.
[ ] Confirmed config source-of-truth (JMX/file/operator/app) preventing drift.
[ ] Distinguished server guardrails, timeouts, mutation caps, throttles, and driver limits.
[ ] When raising thresholds, underlying query/schema causes measured/addressed first.
[ ] When raising timeouts, in-flight, retry, and memory pressure tracked across API/Driver/DB.
[ ] When raising batch/mutation caps, workload justification and commitlog/memtable headroom proved.
[ ] When tuning client retries/pools, global budgets and hot-key pressure verified.
[ ] Canary scoped cleanly so coordinator routing causes zero unpredictable errors.
[ ] Live effective values audited across every node/pod post-rollout and post-rollback.
~~~

### 36.6. Post-Change Verification

~~~text
[ ] Target node/table/setting finished cleanly inside scope with zero unexpected errors.
[ ] RF/CL and DC-aware routing match contracts (or approved changes verified).
[ ] Expected event IDs, values, deletes, and TTL expirations pass verification.
[ ] Hints, repairs, compaction, and streaming hold no runaway backlogs.
[ ] p95/p99, offered/achieved RPS, timeouts, retries, GC, and disk meet SLOs.
[ ] Snapshot/backup/restore pipelines remain intact under retention rules.
[ ] Effective config diffs stayed aligned without accidental operator overrides.
[ ] Change ID, UTC timestamps, outcomes, gaps, and follow-up owners archived.
[ ] Maintenance locks lifted and steady-state ownership returned to operations.
~~~

## 37. Technical References and Conclusion

Verify details against your **exact Cassandra release, distribution, JDK, Java Driver, and operator**. Use official documentation as authoritative baselines (never extrapolate legacy version defaults straight from `stable` URLs):

1. [Apache Cassandra — Documentation](https://cassandra.apache.org/doc/stable/): architecture, replication/consistency, configs, operations, and version compatibility.
2. [Apache Cassandra — nodetool commands](https://cassandra.apache.org/doc/stable/cassandra/managing/tools/nodetool/nodetool.html): `status`, `drain`, `scrub`, `compact`, `repair`, `tablestats`, `tpstats`, and live CLI help.
3. [Apache Cassandra — Compaction](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/compaction/index.html): STCS, LCS, TWCS/UCS (where supported), tombstone eligibility, and compaction costs.
4. [Apache Cassandra — Repair](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/repair.html): anti-entropy, Merkle trees, incremental/full repair, and token/DC scopes.
5. [Apache Cassandra — Hints](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/hints.html): hinted handoff, hint windows, delivery throttles, and best-effort boundaries.
6. [Apache Cassandra — CQL DML](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): `INSERT`, `UPDATE`, `DELETE`, `LIMIT`, TTL, and batch semantics.
7. [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/): prepared/bound CQL reuse and statement attributes.
8. [Apache Cassandra Java Driver 4.18 — Paging](https://apache.github.io/cassandra-java-driver/4.18.0/core/paging/): page sizes, paging state, and application fetch behavior.
9. [Spring Data Cassandra — Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html): persistence/query mapping, generated CQL, and entity lifecycles (pair with your exact BOM).

**Conclusion:** Before **restarting**, calculate **RF/CL and surviving quorum capacity**, audit JVM/GC/commitlog/hints, and enforce rolling-restart stop criteria. Before **scrubbing**, confirm physical SSTable corruption, **off-cluster backups and healthy peer sources**, narrow table/node scope, and accept potential record loss in lossy modes—never mistaking exit code 0 for verified completeness. Before **major compaction**, budget peak disk including **input + rewritten SSTables + snapshot hardlinks**, evaluate STCS/LCS/TWCS/UCS, `gc_grace_seconds`, and live user p99 impact. Before **loosening limits**, separate guardrails, timeouts, mutation caps, and driver throttling—knowing threshold tweaks never fix broken schemas or tombstone-heavy scans. A change earns **`GO`** only with **scoped impact predictions, verified clean recovery sources, representative canaries, passing SLO/correctness gates, and realistic recovery paths**. Never mistake **node `UN`**, a single passing read, or a config revert for proven cluster convergence and root-cause resolution.
