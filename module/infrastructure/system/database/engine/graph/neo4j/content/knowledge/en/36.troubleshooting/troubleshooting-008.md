# Out of Memory, Disk Full, and Abnormal Transaction Log Growth in Neo4j

## 1. Goal of This Lesson: Recover Without Losing More Data

A Java / Spring Data Neo4j service uses a property graph to manage `(:Customer)-[:PLACED]->(:Order)` and `(:Supplier)-[:SUPPLIES]->(:Product)`. After deploying a data import job, operations observes:

- Order write APIs time out, and some requests fail with out-of-memory errors.
- Neo4j pods get `OOMKilled` or the JVM logs `OutOfMemoryError`.
- Disk space drops rapidly, especially under `data/transactions`.
- The database transitions from `ONLINE` to unavailable, while the Java application keeps retrying.

These three phenomena—**out of memory, disk full, and growing transaction logs**—can be connected, yet are **not identical**. A massive import can make transaction state exhaust heap and generate heavy transaction logs; slow checkpoints prevent log pruning; a full disk halts the database, while retrying requests compounds the overload.

This lesson belongs to the **Troubleshooting** chapter and provides:

1. A triage and classification workflow separating **JVM heap**, transaction limits, native/container memory, disk, and logs.
2. **Safe, read-only** inspection commands at the OS, Neo4j, and Java layers.
3. The transaction log **rotation → checkpoint → pruning** mechanism, why logs grow, and dangerous actions to avoid.
4. Load-shedding steps, Cypher/transaction fixes, and Java Driver / Spring Data Neo4j controls.
5. Recovery gates, integrity verification, and metric-driven prevention plans.

> Examples use Neo4j 5.x and `2025.MM`/`2026.MM` setting names. Editions, versions, AuraDB, and container setups differ. Any command modifying data or configuration must be tested and approved separately; never treat examples as emergency commands to run unconditionally in production.

## 2. First 5 Minutes: Contain Before Changing Anything

### 2.1. One Priority Decision

If you see **disk full or Neo4j unable to write**, immediately **stop non-essential write sources**: imports, batch updates, retry storms, reverse-writing CDC workers, and heavy index builds. Preserve evidence and inspect before restarting. If data loss is already possible, activate **incident response** and engage database/storage owners.

If the JVM is running out of memory, avoid raising heap, transaction limits, and concurrency all at once: doing so can trigger an earlier container or OS OOM kill.

### 2.2. Symptom Identification Table

| Signal | What to investigate | Key evidence | First action |
| --- | --- | --- | --- |
| `java.lang.OutOfMemoryError: Java heap space` | JVM heap too small for live set/query | JVM heap used/max, GC, query log, tx size | Shed load and identify high-allocating query/job |
| `Neo.TransientError.General.MemoryPoolOutOfMemoryError` | Memory pool hit configured limit | Setting message, `SHOW TRANSACTIONS`, `dbms.listPools` | Find large transactions; do not raise limits blindly |
| `OOMKilled`, exit code 137 | OS/container memory limit exceeded | Kubernetes events, cgroup, RSS, heap + page cache + native | Verify real limits; stop heavy jobs |
| `No space left on device`/`ENOSPC` | Disk, inode, quota, or volume full | `df -h`, `df -i`, PVC/volume quota, DBMS logs | Stop non-essential writes, protect store, expand disk safely |
| `data/transactions` growing steadily | High write rate, retention, slow checkpoint/pruning | Log size over time, checkpoint duration, retention, backup/CDC | Inspect log lifecycle first; **never delete files manually** |
| Rising GC pauses, higher p99, RAM not exhausted | Heap pressure or object churn | GC time, post-GC heap, allocation rate | Fix query/batching; measure live set |
| High page faults while heap looks fine | Page cache too small or queries scan too broadly | Page-cache hit/faults, `PROFILE`, disk latency | Inspect indexes/queries before adding RAM |
| DBMS reports database `OFFLINE` | Storage, recovery, config, or other fault | `SHOW DATABASES`, `neo4j.log`/`debug.log` | Do not force `START`/restarts repeatedly before fixing root cause |
| Java Driver times out while DBMS looks healthy | Pool, network, lock wait, or overloaded server | Pool wait, server transactions, query latency | Isolate client vs. server; do not blindly scale DB |

**Never turn a transient error into an infinite retry loop.** When disks are full or quorum/DBMS is unready, rapid retries across multiple Java instances make recovery harder.

## 3. Neo4j Memory and Storage Map

```text
Host RAM / container memory limit
  |
  +-- JVM heap                  <= server.memory.heap.max_size
  |    +-- Cypher execution, sort/collect, transaction state
  |    +-- GDS graph / algorithm state if used
  |    +-- Java objects, GC overhead
  |
  +-- Neo4j page cache          <= server.memory.pagecache.size
  |    +-- graph store, native indexes
  |
  +-- Native / direct / OS memory
       +-- thread stacks, metaspace, network buffers, kernel...

Disk / volumes (possibly on separate filesystems)
  |
  +-- data/databases/<database>    graph store and indexes
  +-- data/transactions/<database> transaction logs for recovery/backup
  +-- data/cluster-state/...       cluster metadata/raft logs (if applicable)
  +-- logs/                       neo4j.log, debug.log, query.log, gc.log
  +-- backups/, dumps/, imports/  depends on deployment layout
```

**Transaction logs are not query logs.**

- **Transaction logs** record committed changes to support crash recovery, differential backups, catch-up, and CDC where supported.
- **Query logs** record query execution, duration, DB Hits, page faults, and parameters per config; they cannot replay a database.
- **`debug.log` and `neo4j.log`** support software/system incident diagnostics.
- **Cluster Raft logs** drive consensus replication; they are distinct from per-database transaction logs.

Never move or delete files under `data/databases`, `data/transactions`, or `data/cluster-state` with `rm` to reclaim space. Neo4j relies on checkpoints and log ordering for consistent recovery.

## 4. Incident Runbook: Three Verifiable Phases

### Phase A — 0–10 Minutes: Stop Further Damage

1. Record incident ID, UTC timestamp, Neo4j version/edition, database, and affected services.
2. Pause **non-essential imports, batch jobs, and write jobs**; switch write APIs to maintenance mode if appropriate, without assuming every cluster replica stops writing automatically.
3. Dampen retry storms in the Java Driver/queues while keeping error logs and correlation IDs.
4. Check **space and inodes on every relevant filesystem**: database store, transaction logs, diagnostic logs, backups, temp.
5. Record database/cluster state. Never run `DROP`, restore, force checkpoint, or repeated restarts while disk is exhausted.
6. If corruption, volume loss, or repeated OOMs are suspected, preserve evidence and engage DBA/SRE/Neo4j Support.

### Phase B — 10–30 Minutes: Identify the Source of Growth

1. Separate JVM heap exhaustion, transaction caps, host OOMs, and disk quotas.
2. Check transaction log count/growth rate, actual write throughput, and checkpoint/pruning health.
3. Correlate query logs with newly deployed jobs, `SHOW TRANSACTIONS`, and safe `PROFILE` runs.
4. Identify which cluster members are affected and whether logs reside on a dedicated volume.
5. Pick **one remediation path** with a clear hypothesis and stop condition, prioritizing non-destructive actions.

### Phase C — Controlled Recovery

1. Ensure storage has enough space for **recovery, checkpoints, log rotation, and backups**, not just a few spare MBs.
2. If the DBMS is still running, plan phased write resumption after the culprit stops; if offline, follow your rehearsed startup/recovery and backup procedures.
3. Reconcile counts, constraints, graph relationships, and the last committed transactions.
4. Re-open read traffic, then rate-limited write traffic; monitor p95/p99, heap, GC, free disk, log growth, and error rates.
5. Record recovery time and evidence; close the incident only after stability holds.

**Principle:** restoring from backup is an option for corruption/data loss; **it is not the first reflex** when a query consumes excessive heap or transaction logs grow normally under heavy writes.

## 5. Checking Disk and Filesystems: Read-Only Commands

On a Linux host (do not run without operational authorization), for example:

```bash
# Actual usage across mounts.
df -h

# Inode exhaustion can also trigger ENOSPC while bytes remain free.
df -i

# Replace <NEO4J_HOME> with the actual deployment directory.
du -sh /var/lib/neo4j/data/databases/* 2>/dev/null
du -sh /var/lib/neo4j/data/transactions/* 2>/dev/null
du -sh /var/log/neo4j 2>/dev/null

# If backups/dumps live on a separate volume, check that exact mount.
```

These paths are examples for one package layout; check `server.directories.data`, `server.directories.transaction.logs.root`, `server.directories.logs`, and your deployment topology for exact paths. **Do not run wildcard `du` across huge filesystems and treat the sum as instantaneous database size**; it can burn I/O and represents only a point-in-time snapshot.

### 5.1. When `df` and `du` Disagree

Possible causes:
- Deleted files still held open by a running process descriptor.
- Snapshots/overlay filesystems or reserved blocks.
- Container writable layers vs. mounted volumes on different paths.
- Volume or project quotas.
- Inodes exhausted despite free bytes remaining.

Ask OS/storage owners to inspect open files, quotas, and mounts; **never kill Neo4j just to “release deleted files”** without assessing data loss risk.

### 5.2. Containers and Kubernetes

When running in containers, inspect simultaneously:
- Memory **requests/limits** and `OOMKilled` events; free host RAM does not prove a pod has sufficient limit.
- PVC capacity/usage and backing filesystems; the **transaction log volume** may be full while the data volume still has space.
- Node disk pressure, ephemeral storage, and container logs.
- File ownership/permissions after volume expansion or remounts.
- For crash-looping pods, previous-container logs and Kubernetes events hold crucial clues.

After expanding a PVC, verify the filesystem itself actually resized, rather than trusting control-plane capacity alone.

## 6. Inspecting Neo4j State and Effective Settings

If the DBMS still accepts administrative commands:

```cypher
SHOW DATABASES;
```

On self-managed Neo4j with proper privileges, inspect relevant settings:

```cypher
SHOW SETTINGS
YIELD name, value, isDynamic, startupValue
WHERE name IN [
  'server.memory.heap.initial_size',
  'server.memory.heap.max_size',
  'server.memory.pagecache.size',
  'dbms.memory.transaction.total.max',
  'db.memory.transaction.total.max',
  'db.memory.transaction.max',
  'server.directories.transaction.logs.root',
  'db.tx_log.preallocate',
  'db.tx_log.rotation.size',
  'db.tx_log.rotation.retention_policy',
  'db.checkpoint',
  'db.checkpoint.interval.time',
  'db.checkpoint.interval.tx'
]
RETURN name, value, isDynamic, startupValue
ORDER BY name;
```

**Do not assume `SHOW SETTINGS` is available on AuraDB.** In a cluster, output reflects **the member executing the command**; check all relevant members if configuration drift is suspected.

**Dynamic ≠ persistent:** `dbms.setConfigValue` on self-managed Enterprise alters only the current member's runtime value for dynamic settings; it does not update `neo4j.conf` or propagate cluster-wide. After the incident, review all temporary changes and manage them in versioned configuration with rollback.

## 7. Distinguishing Types of Memory Exhaustion

### 7.1. Java Heap `OutOfMemoryError`

The JVM heap holds Neo4j runtime objects, intermediate query results, transaction state, and parts of plugins like Graph Data Science. Common causes:

- One transaction calling `UNWIND` on a huge list or updating millions of nodes before commit.
- Queries using `collect(...)`, `ORDER BY`, Cartesian products, or path traversals causing `Rows` explosion.
- Many concurrent transactions holding memory/locks for too long.
- GDS projections/algorithms or plugins holding large graphs in heap.
- Heap sized too small for the workload **even after** optimizing queries and concurrency.

**Direction:** first find which queries consume heap, shrink fan-out/batches and concurrency; only then evaluate raising `server.memory.heap.initial_size` and `server.memory.heap.max_size` within real RAM budgets.

```properties
# Lab example on a machine with ample RAM, NOT a generic production config.
server.memory.heap.initial_size=8G
server.memory.heap.max_size=8G
server.memory.pagecache.size=12G
```

Do not put 8G heap + 12G page cache inside a 16G pod and expect room for JVM native memory, OS, threads, Lucene/vector indexes, and GDS. Measure **container RSS, host RAM, and GC** after changes.

### 7.2. Hitting Transaction Memory Limits

Neo4j enforces three common thresholds:

| Setting | Scope | When threshold is hit |
| --- | --- | --- |
| `dbms.memory.transaction.total.max` | Total transaction memory across the DBMS | Transactions may be terminated to protect the server |
| `db.memory.transaction.total.max` | Total transaction memory for a single database | Per-database cap |
| `db.memory.transaction.max` | A single transaction | Prevents one transaction from monopolizing memory |

**Termination by a transaction cap does not mean the JVM already hit OOM.** These caps act as guardrails. Raising limits does not add physical RAM; if a hundred transactions are all large, loosening caps can escalate a transaction error into a fatal JVM/container crash.

Neo4j tracks transaction memory using **estimates**, which can diverge from true memory when objects are shared. If you suspect false positives, test in staging with realistic data and close monitoring—never disable guardrails in production by default.

### 7.3. Container/OS `OOMKilled`

When the kernel/cgroup kills the process:
- Compare total RSS against the container memory limit, not just `heap.used`.
- Account for Neo4j page cache, off-heap memory, thread stacks, buffers, and sibling processes in the cgroup.
- Kills can happen even when heap usage sits at only 60%.
- Check CPU throttling, swap, and full volumes, as these stall transactions and retain memory longer.

Never automatically equate `OOMKilled = Java heap leak`.

### 7.4. Java Client OOM

If a Java Driver service executes:

```java
var all = session.run("MATCH (n) RETURN n").list();
```

then the **Java application's heap** can run out while materializing the whole graph, even though Neo4j's heap stays healthy. With Java Driver / SDN:
- Return use-case-specific projections/DTOs.
- Use `LIMIT` or keyset pagination to bound valid results.
- Stream results or consume in batches; never call unbounded `collectList()` in Reactor.
- Check heap usage on **both JVMs** before tuning `server.memory.heap.max_size`.

## 8. Investigating Resource-Heavy Transactions and Queries

With admin privileges on the target database:

```cypher
SHOW TRANSACTIONS
YIELD transactionId, currentQuery, status, elapsedTime,
      estimatedUsedHeapMemory
RETURN transactionId, status, elapsedTime,
       estimatedUsedHeapMemory, currentQuery
ORDER BY estimatedUsedHeapMemory DESC;
```

```cypher
CALL dbms.listPools();
```

Available fields and visibility depend on edition, version, and privileges. `estimatedUsedHeapMemory` is an **estimate** and must not be summed as exact physical RAM.

If you identify a destabilizing query or transaction, you can consider **targeted termination** using its real transaction ID after confirming it is not a backup, migration, or critical transaction:

```cypher
// Run only after approval and verifying the exact transaction.
TERMINATE TRANSACTIONS 'neo4j-transaction-123';
```

**This is an illustrative ID, not a real one.** Termination rolls back uncommitted changes and may trigger Java Driver retries, so stop the offending job from restarting simultaneously. Never terminate all transactions or run bulk destructive queries without understanding consequences.

### 8.1. Inspecting Plans for Suspect Queries

```cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})
      -[:PLACED]->(o:Order)-[:HAS_LINE]->(p:Product)
RETURN p.sku AS sku, count(*) AS lines
ORDER BY lines DESC
LIMIT 10;
```

On a test database with sample data and appropriate privileges, run `PROFILE` to inspect `Rows`, `DB Hits`, sorts/aggregations, and memory. **`PROFILE` executes the real query**; never run it on production write statements merely to inspect plans.

What to look for:
- Is there a `NodeIndexSeek` on `customerId`, or a broad label scan?
- Does `Expand(All)` generate massive intermediate rows?
- Do `collect`, `Sort`, or `EagerAggregation` buffer too much state?
- Do multiple one-to-many branches form a Cartesian product?
- Is an API firing N+1 repository queries?

Often, cutting intermediate rows from a million down to a few thousand via indexes/filters reduces both heap and transaction log pressure **without increasing server specs**.

## 9. Fix Large Transactions Before Raising Heap

### 9.1. Anti-Pattern: One Transaction Holding an Entire Import

```cypher
// Anti-pattern illustration only: $rows may hold millions of items.
UNWIND $rows AS row
MERGE (p:Product {sku: row.sku})
SET p.name = row.name;
```

A single transaction retains all uncommitted changes, index updates, and intermediate state. With oversized inputs, the query hits the transaction memory cap or causes OOM. Add an index or uniqueness constraint on `Product.sku` to avoid full label scans, though an index **cannot eliminate** the state cost of a huge transaction.

### 9.2. Batching with `CALL ... IN TRANSACTIONS`

When reading streamed rows / `LOAD CSV`:

```cypher
LOAD CSV WITH HEADERS FROM $csvUrl AS row
CALL (row) {
  MERGE (p:Product {sku: row.sku})
  SET p.name = row.name
} IN TRANSACTIONS OF 1000 ROWS;
```

**Requirements:**
- `CALL (row)` uses modern Cypher variable scope clauses; verify your version supports it.
- `CALL ... IN TRANSACTIONS` requires an **implicit/auto-commit transaction**; it cannot run inside a Java Driver `session.executeWrite(...)` managed transaction.
- Batch size 1000 is illustrative; tune for your data/I/O while measuring memory and commit latency.
- Each batch commits independently; if a job fails midway, **partial data is already committed**. Use keys/`MERGE` and checkpointing/idempotency for safe restarts.
- Smaller transactions usually cut peak heap, **yet do not necessarily reduce total transaction log bytes**. Frequent commits still generate log traffic; measure both memory and log growth rate.

### 9.3. Do Not Trade OOM for Disk Full

An unmonitored adjustment:

```text
1-million-row transaction -> heap OOM
    |
    +-- Split into 1,000 rows/batch -> heap stable
                                         |
                                         +-- Continuous commits, rapid log writes
                                         +-- Checkpoint/rotation/pruning fall behind
                                         +-- Transaction log volume fills up
```

Therefore, every import plan needs **two budgets**: peak transaction/memory budget and disk write/log-growth headroom. Factor in index builds, backups, log rotation, and checkpoint duration.

## 10. When Disk Is Full: Which Actions Are Safe?

### 10.1. Ordered Steps to Take

1. **Pause write sources** worsening the situation: imports, load tests, non-essential API writes.
2. Identify **which filesystem is full**: main store, transaction logs, diagnostic logs, backups, external mounts, or overlay.
3. Check **bytes, inodes, quotas, PVC limits**, provisioned disk size, and error logs.
4. Prioritize **expanding the volume / adding storage** per storage/Kubernetes procedures while keeping filesystem integrity intact.
5. If space must be freed urgently, touch only **artifacts outside active Neo4j internals**, such as owner-approved expired backups past retention, reconciled standalone export/temp files, or external app logs via managed rotation.
6. Give Neo4j room to run checkpointing/pruning **via its own mechanisms** where appropriate.
7. Verify startup/health, store consistency, and backups after the incident.

**Never “quick-clean” using `rm data/transactions/*`, `rm data/databases/*`, or `rm data/cluster-state/*`.** Doing so can destroy recovery, backups, CDC catch-up, or cluster consistency.

### 10.2. Why Freeing Just a Few MB Is Not Enough

Neo4j needs extra room for:
- Transaction log preallocation and rotation.
- Checkpoint flushes, recovery, and file metadata.
- Indexes, temporary spills, and active transactions.
- Diagnostic logs, backups/dumps, or index rebuilds.

Maintain **headroom proportional to actual growth rate**. If an import writes 300 MiB of logs per minute and disk only has 100 MiB free, resuming will fill the disk again almost immediately.

### 10.3. When the Database Is Already `OFFLINE`

Do not assume adding disk alone resolves everything:
- Collect `neo4j.log`, `debug.log`, and OS storage errors.
- Check for store corruption, missing transaction logs, or interrupted checkpoints.
- Restore adequate disk space, file permissions, and paths.
- Follow documented startup/recovery procedures; on integrity errors, use your rehearsed backup/recovery runbook.
- Run consistency checks only on an **offline database or eligible backup/artifact**, never on a mounted live store.
- **Never set `db.recovery.fail_on_missing_files=false` to ignore missing logs** unless executing an approved recovery procedure with full awareness of integrity risks; failing on missing required files is the safe default.

## 11. Transaction Logs: Rotation → Checkpoint → Pruning

Transaction logs record per-database mutations so Neo4j can recover from crashes and power backups, clustering, and CDC.

```text
Transaction writes
      |
      v
Active transaction log
      | (reaches db.tx_log.rotation.size)
      v
Log rotation --> new log file
      |
      v
Checkpoint: flush required dirty pages to store
      |
      v
Check retention + valid checkpoint position
      |
      v
Pruning: Neo4j automatically deletes eligible old logs
```

Two minimum conditions before a transaction log file can be pruned:

1. The file has been **rotated** and is no longer the active log.
2. A **newer checkpoint exists in another log file**, guaranteeing the store is flushed far enough that older logs are unnecessary for recovery.

Thus, **retention is a policy**, not an instantaneous hard disk cap. Neo4j evaluates pruning only after checkpoint completion; if checkpoints are slow, blocked, or failing, logs can grow **far beyond the intended retention size**.

### 11.1. Key Settings (Verify Against Your Version)

| Setting | Meaning | Notes |
| --- | --- | --- |
| `server.directories.transaction.logs.root` | Root directory for transaction logs | Can reside on a separate volume; plan config and moves |
| `db.tx_log.preallocate` | Whether to preallocate log files | Defaults to `true` in current docs |
| `db.tx_log.rotation.size` | Approximate size before rotating file | Defaults to `256 MiB`; **does not cap total logs** |
| `db.tx_log.rotation.retention_policy` | Old log retention rule | Current default `2 days 2G`; verify per version |
| `db.checkpoint` | Checkpoint strategy | Defaults to `PERIODIC` |
| `db.checkpoint.interval.time` | Time interval per policy | Current default `15m`, policy-dependent |
| `db.checkpoint.interval.tx` | Transactions between checkpoints when applicable | Current default `100000` |
| `db.checkpoint.iops.limit` | Checkpoint I/O throttle | Change only with measured IOPS budget |
| `db.transaction.timeout` | Caps long-running transactions | Does not directly fix missing checkpoints/logs |
| `dbms.memory.transaction.total.max` | Total transaction memory | Prevents OOM, does not free disk space |

**Never conclude from `retention_policy=2 days 2G` that disk usage will never exceed 2 GiB for logs.** Policy depends on checkpoint timing, rotation, and retention holds for other consumers.

### 11.2. Retention and Backup/CDC/Clustering

Transaction logs serve more than crash recovery:
- Enterprise differential backups require sufficient logs to capture changes since the last backup.
- Cluster catch-up uses relevant logs when a member lags; premature pruning can force a full store copy.
- CDC/consumers depend on retention to resume from their last read offset.

Cutting retention too aggressively can **save disk yet break differential backups, CDC catch-up, or replica catch-up**. Always check SLAs and maximum offline windows of consumers/members before changing retention.

## 12. Why Are Transaction Logs Not Pruning as Expected?

| Hypothesis | Evidence to gather | Action to take |
| --- | --- | --- |
| **Write throughput spike** | Appended bytes/sec, tx/sec, job deploys | Identify job/start time, throttle import |
| **Checkpoints not running or failing** | Checkpoint completion, errors in `debug.log` | Resolve disk, I/O, lock/OS, and storage errors first |
| **Checkpoints running too slowly** | Checkpoint duration approaching interval, disk queue | Measure IOPS/latency and competing writers |
| **Huge file has not rotated yet** | File count/size, `db.tx_log.rotation.size` | Check rotation and newer checkpoint progress |
| **Retention set to `keep_all`** | `SHOW SETTINGS`, config files | Adjust policy accounting for backup/CDC |
| **Runtime retention change not persisted** | `value` differs from `startupValue`, config management | Sync config via proper deployment process |
| **Backup/CDC/replica lag** | Backup schedule/success, CDC lag, raft/tx lag | Avoid cutting logs needed downstream; clear backlog |
| **Volume actually filled by something else** | `df` vs. `du`, backups/exports/container logs | Clean the actual culprit filesystem/artifact |
| **Log preallocation causing step jumps** | Rotation rate, new file size | Distinguish reserved space from real tx data |

**Never pick “delete the oldest log file” without proof.** The oldest OS timestamp does not indicate whether Neo4j still needs that file for crash recovery or backup chains.

## 13. Diagnosing Checkpoints and Pruning Step by Step

### 13.1. Read State First, Do Not Rush Forced Checkpoints

Inspect:
1. When did the last checkpoint succeed?
2. Is `checkpoint duration` rising alongside I/O wait?
3. Is the DBMS logging write, `fsync`, or `ENOSPC` errors?
4. Have log files rotated?
5. What are the active retention policy and backup/CDC/cluster requirements?

If a volume is **100% full**, forcing a checkpoint may also fail because flushing requires metadata/log writes. Restore sufficient free space and stability first.

### 13.2. Force a Checkpoint Only After Resolving the Cause

On the target database, once disk space is healthy, I/O works, and storage errors are gone, operators may consider:

```cypher
// Never run on a full volume or a database suffering corruption.
// Run in the target database with proper privileges and operational plan.
CALL db.checkpoint();
```

This requests a checkpoint; it **does not guarantee immediate pruning down to retention limits**—rotation and policy conditions must still be satisfied. If it fails, inspect logs and stop retrying endlessly.

If checkpoints routinely run slowly, do not blindly raise `db.checkpoint.iops.limit`: when storage is saturated, faster flushing can worsen commit or query latency. Measure IOPS headroom first.

### 13.3. Changing Retention With a Plan

Example reviewed policy change:

```properties
# neo4j.conf — example only for comparing policies.
db.tx_log.rotation.retention_policy=2 days 2G
db.tx_log.rotation.size=256M
```

Do not copy values into production just to “shrink logs”; these are close to current Neo4j defaults. Forms such as `10 files`, `30 days`, `500k txs`, or `keep_all` must be designed around RPO, backups, clusters, and CDC.

**`keep_none`/`false` is not a default emergency switch**: it keeps only minimal active logs, which can break Enterprise differential backups or CDC. If used in a risk-assessed lab import scenario, restore retention afterward and verify backups/consumers. Never use it during an incident when backup chain status is unclear.

### 13.4. Diagnostic Logs Are Not Transaction Logs

Rotation/retention for `query.log` and `debug.log` is configured via **Log4j 2** and related settings. Cleaning query logs through log management **is not the same** as deleting transaction log files. Keep `debug.log` for investigations; starting in Neo4j 2025.01 the default format is JSON, so check version compatibility for legacy log parsers.

If diagnostic logs consume excessive disk, check which log is growing, `VERBOSE`/threshold levels, and parameter logging. Never enable logging of passwords/PII or delete forensic evidence before the incident ends.

## 14. Metrics to Inspect Together

| Group | Metric / measurement | Meaning |
| --- | --- | --- |
| Host/container | Free bytes, free inodes, RSS, memory limit, swap/OOM | Real resource exhaustion risk |
| JVM heap | `dbms.vm.heap.used`, `max`, GC time/pause | Is heap saturating and GC stalling requests? |
| Page cache | `dbms.page_cache.hit_ratio`, `usage_ratio`; `page_cache.page_faults` | Undersized cache or overly broad scans |
| Transaction | Started/committed/rolled back, active, memory estimate | Rising workload or long-held transactions |
| Transaction log | `log.appended_bytes`, `log.rotation_events`, `log.rotation_duration` | Log generation rate and rotation behavior |
| Checkpoint | `database.<db>.check_point.duration` and count/events | Are checkpoints keeping up with writes? |
| Store size | `store.size.database` and `store.size.full` | Data store size vs. data + transaction logs |
| Java client | Pool wait, retries, p95/p99, request errors, JVM heap | Client-side issues or retry storms |
| Storage | IOPS, read/write await, utilization, quota | Real disk bottleneck or space exhaustion |

These names are **metric suffixes or examples**; prefixes and availability depend on Neo4j version, edition, and exporter. Neo4j Enterprise provides broader CSV/JMX/Prometheus metrics; AuraDB exposes metrics per service tier.

### 14.1. Convert Counters into Rates

```text
log_bytes_per_second =
  (log.appended_bytes at t2 - at t1) / (t2 - t1)

page_faults_per_second =
  (page_faults at t2 - at t1) / (t2 - t1)
```

**Hypothetical** example: `log.appended_bytes` grows by 9 GiB in 30 minutes, averaging roughly 307 MiB/min. With only 2 GiB left on the volume and unchanged write rate, headroom is tiny. **That is not proof log files will grow at the exact same rate**: pruning, rotation, checkpoints, and other jobs also shape real footprint.

Never infer current growth speed from a **cumulative counter** alone; take deltas over consistent windows and account for resets after restarts.

### 14.2. Alert Thresholds Need Lead Time

Set alerts on:
- Free disk bytes and **estimated time-to-full** at recent growth rates.
- Peak memory/RSS and GC pause durations.
- Checkpoint duration relative to checkpoint interval.
- Differential backup lag, CDC backlog, and replica catch-up lag.
- Request p95/p99/error SLOs and write availability.

Alert when storage risks filling within hours, **never wait for `free disk=0`**. Raw percentages ignore growth velocity: 10% free on a 10 TiB volume is totally different from 10% on 10 GiB.

## 15. Practice Scenario A: Massive `UNWIND` Causing OOM

Suppose an application sends a list of one million products in one transaction and hits the memory cap.

**Verification steps:**
1. Identify `currentQuery` and `estimatedUsedHeapMemory` of the transaction.
2. Check `EXPLAIN`, the `Product.sku` index, and cardinality.
3. Inspect GC, JVM heap, and total memory across concurrent jobs.
4. Confirm whether the transaction committed or rolled back; never guess from an error string.

**Ordered fixes:**
- Stage inputs in an authorized file/stream and process in batches.
- Choose batch size based on memory and writes/row.
- Ensure a uniqueness constraint exists on the merge key.
- Cap job concurrency.
- Monitor transaction log growth and checkpoints after switching to batches.
- Raise heap or transaction limits only after proving a legitimate workload lacks resources.

**Never use `db.memory.transaction.max=0` as a default “fix”.** Removing the cap can push the server into fatal OOM.

## 16. Practice Scenario B: Transaction Logs Grow 40 GiB Overnight

The following figures are **hypothetical**:

| Signal | Collected data |
| --- | --- |
| Database | `orders`, Enterprise, still `ONLINE` |
| Log size before batch | 3 GiB |
| Log size after batch | 43 GiB |
| Current retention | `2 days 2G` |
| Commits/sec | Increased 20x |
| Checkpoint duration | Spiked sharply; incomplete checkpoints |
| Disk free | 8 GiB |

**You cannot conclude Neo4j “ignored” retention** just because logs exceed 2 GiB. Likely factors:
- Batch writes appended transaction bytes very rapidly.
- Logs were ineligible for pruning due to slow checkpoints.
- Heavy write I/O delayed checkpoint completion.
- CDC, differential backups, or catch-up needed those logs.
- Some active files had not rotated yet.

**Action plan:**
1. Pause non-essential batch imports.
2. Collect checkpoint logs/metrics, disk status, and backup status.
3. Expand storage if headroom is too small for safe checkpointing.
4. Resolve the I/O bottleneck or job slowing down checkpoints.
5. Let rotation/checkpoint/pruning run via Neo4j's mechanism; consider `CALL db.checkpoint()` only once conditions are healthy.
6. Verify log size stabilizes, backups/CDC remain intact, and the database accepts writes.
7. Throttle batch rate and size capacity properly; never rely on a retention tweak to hide ingestion volume.

## 17. Practice Scenario C: Kubernetes `OOMKilled` While Heap Only Used 6 GiB

Assume:
- Pod memory limit: 16 GiB.
- JVM heap max: 8 GiB, peak heap used: 6 GiB.
- Page cache: 10 GiB.
- Native/JVM overhead and sidecars also consume memory.

Here, **heap max + page cache = 18 GiB already exceeds the pod limit**, even before counting native memory or sidecars. The kernel can OOM-kill the pod even though the JVM never hit `-Xmx`.

Remediation:
1. Check pod events, RSS/cgroup usage, and `OOMKilled`.
2. Pause heavy batches and reduce concurrent load while stabilizing.
3. Working down from the **pod limit**, budget heap + page cache + native + OS/sidecars.
4. Lower page cache or raise pod memory limits per cluster capacity, changing one variable cleanly.
5. Restart per runbook if needed, monitoring cache warm-up and database/recovery status.
6. Re-run load tests at representative traffic, measuring GC, page faults, p95/p99, and OOMs.

Never raise heap to 12 GiB just because you saw “OOM” in Kubernetes; that makes the total memory overshoot worse.

## 18. Java Driver / Spring Data Neo4j: Avoid Amplifying the Incident

### 18.1. Bounded Retries

Java Driver managed transactions:

```java
try (var session = driver.session(
        org.neo4j.driver.SessionConfig.forDatabase("neo4j"))) {

    session.executeWriteWithoutResult(tx ->
        tx.run("""
            MERGE (o:Order {orderId: $id})
            ON CREATE SET o.status = 'NEW'
            """, java.util.Map.of("id", "o9001"))
          .consume()
    );
}
```

The callback may be retried by the driver on transient errors, so:
- Enforce a **uniqueness constraint** on the business key.
- Never send emails or charge payments directly inside the callback.
- Bound retry budgets, concurrency, and queue depth in the application.
- When disk is full or Neo4j is offline, **fail explicitly or queue in a controlled manner** rather than letting 100 instances retry endlessly.
- If a write response is lost, verify state by business ID; a timeout does not prove the commit failed.

### 18.2. Session and Result Lifecycle

- **`Driver`** is shared and owns the connection pool.
- **`Session`** is short-lived per operation and must be closed.
- **`Result`** must be consumed within the transaction/session scope.
- In async Java Driver flows, close with `closeAsync()` once the stage completes.
- In reactive flows, tie cleanup to publisher lifecycle and cancellation.
- Never call `list()`/`collectList()` to load millions of nodes into client heap.
- With Spring Data Neo4j, avoid hydrating deep entity graphs when an API needs only a few fields; use DTOs/projections and pagination.

On a memory-constrained system, a single REST endpoint reading the whole graph or an oversized batch writer can exhaust RAM on **both client and server**.

## 19. When Are Backup/Restore and Consistency Checks Needed?

**Transaction log growth** does not by itself mean data corruption. However, if a full disk forces the database offline or logs are missing/corrupt, initiate recovery procedures.

| State | Action |
| --- | --- |
| DBMS `ONLINE`, logs growing, store healthy | Measure writes/checkpoints/pruning; manage load and capacity |
| Disk full, database cannot write | Shed load, expand disk, collect logs; verify health before resuming |
| Restart succeeded and DB returned `ONLINE` | Reconcile transactions/schemas, monitor I/O/logs, take a backup |
| Startup reports missing/corrupt transaction log | **Do not delete remaining logs**; follow recovery runbook and evaluate backups |
| Store inconsistency | Stop/clone per procedure; run `neo4j-admin database check` on an offline store or eligible artifact |
| Volume lost or database unrecoverable | Restore from a valid backup; verify consistency, schema, and app |

**Run `neo4j-admin database check` only on a database not currently in use by the DBMS**, or on an eligible backup/dump per documentation. Never treat it as a live “health query”.

In Enterprise, online full/differential backups depend on sufficiently long transaction logs; in Community, offline dump/load has different constraints. Clustering provides failover if one member suffers disk failure, yet **never replaces backups**, because valid accidental deletes replicate too.

## 20. Post-Incident Recovery and Sign-Off Checklist

### 20.1. Technical Acceptance Gates

1. Data/transactions/logs/backup filesystems have healthy headroom and normal inode/quota usage.
2. DBMS and required databases are `ONLINE` with zero corruption or missing-log errors.
3. JVM/RSS/GC are steady with no new `OOMKilled` or `OutOfMemoryError` events.
4. Transaction memory stays within budget; large jobs are throttled.
5. Checkpoints succeed and log rotation/pruning operate normally.
6. Latest backups remain restorable; CDC/replicas can catch up cleanly.
7. `SHOW INDEXES`/`SHOW CONSTRAINTS` and graph data pass domain verification.
8. Java Driver and SDN pass read/write canaries using least-privilege credentials.
9. p95/p99, throughput, and error rates meet SLOs with no retry storms.
10. Emergency config changes are persisted in config management or rolled back cleanly.

### 20.2. Incident Record Table

| Field | Illustrative example |
| --- | --- |
| Incident ID | `neo4j-disk-memory-2026-11` |
| Database/members | `orders` across 3 primaries |
| First symptom | `ENOSPC` and write timeouts |
| Detection time | UTC timestamp plus reporting timezone |
| Abnormal write source | Newly deployed batch import |
| Heap/cgroup | Used, max, RSS, pod limit |
| Disk | Free bytes/inodes, full mount |
| Transaction logs | Bytes, append rate, rotation count |
| Checkpoint | Last success, duration, errors |
| Interventions | Paused batch, expanded volume, throttled rate |
| Re-open criteria | DB `ONLINE`, stable checkpoints/logs, read/write canary PASS |
| Actual RPO/RTO | Record measured values, not target goals |
| Follow-ups | Fix job, capacity alerts, game day, and owner |

**Never close an incident simply because a few files were deleted or one request succeeded.** Prove that logs and memory stay within sustainable bounds once normal traffic resumes.

## 21. Prevention Across the Application Lifecycle

### 21.1. Before Deploying Large Jobs

- Estimate node/relationship counts, import rate, and expected transaction log bytes.
- Estimate job heap and transaction state; pick a batch size safe to roll back and retry.
- Ensure uniqueness constraints/indexes back every `MERGE` key.
- Verify free space on the **exact filesystems** for logs, store, and backups.
- Confirm checkpointing and retention support CDC, differential backups, and cluster catch-up.
- Configure concurrency limits, timeouts, rate limits, and a job pause switch.
- Test on datasets featuring high-degree nodes and large property payloads.

### 21.2. Operational Alerts

- Alert on **time-to-full** for disk/log volumes, not just percent free.
- Alert on JVM heap/GC pauses, cgroup RSS, and `OOMKilled`.
- Alert on slow checkpoints or repeated checkpoint failures.
- Alert on transaction log append rate spiking above baseline.
- Alert on backup/CDC/cluster lag when retention risks falling short.
- Alert on Java Driver retries/pool wait spiking alongside database errors.
- Test backup restores periodically rather than trusting backup job exit codes alone.

### 21.3. After Neo4j Upgrades

- Verify current setting names and `startupValue`/`value`.
- Review retention defaults and checkpoint policies in the new version.
- Check log formats and metrics export changes.
- Verify filesystem mounts, permissions, and container configs.
- Re-run realistic read/write mix benchmarks and compare before/after.

## 22. Dangerous Misconceptions

| Misconception | Reality |
| --- | --- |
| “`OutOfMemoryError` means raise `-Xmx` right away.” | Often caused by overly broad queries; raising heap merely delays failure or starves page cache |
| “`OOMKilled` means the JVM heap filled up.” | Pods/hosts cap **total RSS/cgroup**, not just heap |
| “Hitting transaction limit means the DB needs more RAM.” | The limit may be protecting the server; shrink transaction size first |
| “Unused page cache automatically feeds heap.” | Both regions are managed separately and require explicit RAM budgets |
| “Disk full? Delete the oldest log file.” | **Never manually delete transaction logs** needed for recovery/checkpoints/backups/CDC |
| “`2 days 2G` guarantees logs stay under 2 GiB.” | Pruning waits for valid checkpoints/rotations, plus active files and backlog |
| “Just raise `db.tx_log.rotation.size` for fewer logs.” | Larger log files can delay pruning eligibility |
| “Higher checkpoint IOPS is always better.” | Can contend with commits when storage is already saturated |
| “Repeatedly forcing checkpoints fixes disk full.” | When disk is full or I/O fails, checkpoints fail too |
| “Setting retention `keep_none` is harmless.” | Can break differential backups, CDC, and cluster catch-up |
| “`query.log` and transaction logs are the same.” | Query logs are for observability; transaction logs are for recovery |
| “Batching always shrinks total log bytes.” | Batching cuts peak transaction state; frequent commits still incur log overhead |
| “`SHOW SETTINGS` on one member proves the whole cluster matches.” | Runtime settings can drift across members |
| “Restart succeeded, so zero data was lost.” | Verify consistency, counts, transactions, and backups |
| “Retrying until errors clear is safe.” | Triggers retry storms, duplicate side effects, or resource exhaustion |
| “PVC expanded, so resume all jobs immediately.” | Verify filesystem resize, checkpoint/pruning health, and root cause first |

## 23. Self-Practice Exercises

1. A Neo4j pod has a 16 GiB memory limit, 8 GiB max heap, and 10 GiB page cache. Why can it get `OOMKilled` even when heap usage is only 5 GiB? State how to measure it.
2. An `UNWIND $rows` job inside a single transaction is terminated by the memory cap. Design a batched import and explain why simply raising `db.memory.transaction.max` is risky.
3. Transaction logs for database `orders` grow from 4 GiB to 34 GiB in two hours while retention is `2 days 2G`. List at least four hypotheses to check before editing config.
4. Explain the two conditions required for Neo4j to prune old transaction logs. Why is retention not a hard disk cap?
5. `df -h` reports 80% free, yet `ENOSPC` occurs. How can `df -i`, quotas, and mounted volumes explain this?
6. A team proposes `rm -rf data/transactions/orders/*` to free 20 GiB. Explain the risks and outline a safer procedure.
7. When is `CALL db.checkpoint()` reasonable, and why should it not be run when the volume is completely full?
8. A Java service calls `Result.list()` on 5 million nodes. The database JVM heap is healthy while the Java container OOMs. Which side should be fixed first?
9. Yesterday's differential backup succeeded, and a CDC consumer lags 6 hours behind. What are the consequences of setting `db.tx_log.rotation.retention_policy=keep_none`?
10. Write a `SHOW TRANSACTIONS` query to find transactions with high estimated memory and explain why that metric must not be treated as exact physical RAM.
11. Design two alert thresholds: one on **disk time-to-full** and one on **checkpoint duration**; specify conditions to avoid false positives after restarts.
12. Draft a 30-minute runbook for `disk full + write timeout`, separating permitted vs. forbidden actions and stating criteria to reopen traffic.

## 24. Key Takeaways

- **Classify the exact failure**: JVM heap OOM, transaction cap, container OOMKill, page cache starvation, and disk full are distinct problems.
- **Stop write pressure first**, preserve evidence, and measure resources per database, volume, and cluster member.
- **Never manually delete transaction logs or store files.** Rotation, checkpoints, and retention are coordinated by Neo4j for safe recovery.
- `db.tx_log.rotation.retention_policy` is a log retention policy, **not a guarantee that physical disk usage stays below the threshold** when checkpoints/rotations fall behind.
- Cutting retention too short can break **differential backups, CDC, and cluster catch-up**.
- Fix queries/indexes, shrink fan-out, batch writes, and bound concurrency **before raising heap or transaction limits arbitrarily**.
- When disks fill up, prioritize **expanding the right volume, pausing writers, and restoring safe checkpoints** instead of repeated restarts or forced checkpoints.
- Inspect `SHOW TRANSACTIONS`, `dbms.listPools`, logs, metrics, `EXPLAIN`/`PROFILE`, and Java client memory together.
- Re-open write APIs only after database health, data reconciliation, backup/CDC continuity, and metric stability are confirmed.
- **Game days and lead-time alerts** keep minor resource pressure from turning into data-loss incidents.

### Official References

- [Neo4j Operations Manual — Memory configuration](https://neo4j.com/docs/operations-manual/current/performance/memory-configuration/)
- [Neo4j Operations Manual — Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual — Checkpointing and log pruning](https://neo4j.com/docs/operations-manual/current/database-internals/checkpointing/)
- [Neo4j Operations Manual — Database transactions](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-management/)
- [Neo4j Operations Manual — Show and terminate transactions](https://neo4j.com/docs/operations-manual/current/database-internals/show-and-terminate-transactions/)
- [Neo4j Operations Manual — Essential metrics](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/essential/)
- [Neo4j Operations Manual — Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Operations Manual — Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Operations Manual — Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual — Dynamic configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual — Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual — Consistency checker](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Data Ingestion Guide — Transactional and concurrent Cypher ingestion](https://neo4j.com/docs/data-ingestion-guide/best-practices/transactional-and-concurrent-cypher-ingestion/)
- [Neo4j Java Driver Manual — Managed transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Spring Data Neo4j — Reference](https://docs.spring.io/spring-data/neo4j/reference/)
