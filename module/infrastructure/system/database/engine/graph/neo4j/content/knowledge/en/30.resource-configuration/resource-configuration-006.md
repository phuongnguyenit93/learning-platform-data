# Managing Transaction Logs, Checkpoints, and Log Retention Policies

## 1. Why Are Transaction Logs a Critical Resource in Neo4j?

In a system using **DATABASE_ENGINE_GRAPH_NEO4J**, Java Driver or Spring Data Neo4j applications may continuously create **Order** nodes, update **Customer** properties, and write relationships between entities. Every committed write transaction must guarantee **durability**: if the Neo4j process stops abruptly, committed data must still be recoverable.

Neo4j uses **transaction logs** under *write-ahead logging* principles to record transaction mutations before they are fully reflected in the graph store files (*store files*). When a crash occurs, Neo4j can use the logs to restore a consistent state. However, keeping logs forever consumes disk space, whereas keeping too few can break **differential backups**, **cluster catch-up**, and **Change Data Capture (CDC)**.

In the **Resource Configuration** chapter, this lesson addresses five questions:

1. What do **transaction logs** store, and how do they differ from **query logs**, **debug logs**, and **Raft logs**?
2. How do **checkpoints** affect crash recovery and eligibility for pruning old logs?
3. What do **rotation size**, **retention policy**, and **checkpoint policy** settings control?
4. How do you balance **disk capacity**, **RPO/RTO**, **backups**, **CDC**, and cluster synchronization?
5. When the transaction log directory grows rapidly, what **safe** steps should you follow to diagnose and resolve it?

> **Operational warning:** Never manually delete, move, compress, or replace transaction log files managed by Neo4j to "free disk space." Neo4j tracks which checkpoints are complete and which logs remain necessary for recovery. Manual deletion is not a supported pruning method and can render a database unrecoverable.

## 2. Transaction Logs in the Lifecycle of a Transaction

Suppose a service creates an order:

~~~cypher
MERGE (o:DemoResourceOrder {orderId: $orderId})
ON CREATE SET o.status = 'CREATED', o.createdAt = datetime()
RETURN o.orderId;
~~~

On a properly configured database, a successful write transaction follows this conceptual flow:

~~~mermaid
flowchart TD
  A["Application sends Cypher transaction"] --> B["Neo4j processes graph mutations"]
  B --> C["Write transaction record to transaction log"]
  C --> D["Commit succeeds / acknowledged to application"]
  D --> E["Store pages may still need flushing from page cache"]
  E --> F["Checkpoint completes: safe recovery marker"]
  F --> G["Pruning of eligible rotated old log files"]
~~~

This diagram is a logical view, not a literal representation of every disk write or internal ordering in every version. Key points:

- **Transaction logs** store recorded mutations for the database, including necessary information about data, index, and constraint changes.
- **Successful commit** does not mean every store page has already been checkpointed when returning to the application.
- **Checkpoints** force pending dirty pages out to the store files and establish a marker so recovery does not have to replay from the beginning of transaction history.
- **Pruning** removes log files that have **already rotated** and are **no longer needed** by either checkpoints or retention policies.

### 2.1. When the Database Crashes

~~~mermaid
sequenceDiagram
  participant App as Java Driver
  participant DB as Neo4j
  participant Log as Transaction log
  participant Store as Store files
  App->>DB: T1: create Order
  DB->>Log: Write transaction mutations
  DB-->>App: T1 commit
  Note over DB,Store: Store pages may not all be flushed yet
  DB->>Store: Checkpoint: flush pages
  Note over DB,Store: Crash occurs after checkpoint
  DB->>Log: Read records needed for recovery
  DB->>Store: Restore to a consistent state
~~~

If a crash occurs **after commit but before the next checkpoint**, the transaction log is required to bring the store back to a state containing committed transactions. **The farther apart checkpoints are**, the **more log replay work** may be needed on restart. Conversely, overly frequent or aggressive checkpoints can increase I/O pressure.

**A checkpoint is not a backup.** It does not create an independent copy to recover from total disk failure or accidental database deletion. A restore-tested backup remains mandatory in any disaster recovery strategy.

## 3. Distinguishing Four Easily Confused Log Types

| Component | Purpose | Usable as an Independent Backup? | Should It Be Deleted Manually? |
|---|---|---|---|
| **Transaction log** | Records transaction mutations; recovery, backup support, and cluster sync | **No**; requires stores/backups and an intact chain | **No** |
| **Query log** | Tracks queries, latency, and plans/diagnostics | **No** | Managed via its own log rotation settings |
| **Debug / server log** | Records events, errors, checkpoints, operational warnings | **No** | Uses separate log retention policies |
| **Raft log** (cluster) | Consensus state/data across primary cluster members | **No** | **Do not** intervene manually |

The default transaction log path in self-managed Neo4j is typically:

~~~text
<NEO4J_HOME>/data/transactions/<database-name>
~~~

The root directory can be changed via **server.directories.transaction.logs.root**. Meanwhile, **query/debug/server logs** normally reside under the log directory controlled by **server.directories.logs**. In a cluster, members keep their own data and logs; never assume all logs live on a shared volume.

**Do not try to solve a full transaction log disk by adjusting query log rotation.** The two log types serve different purposes and follow separate deletion mechanisms.

## 4. Rotation, Checkpoints, and Pruning: Three Distinct Yet Linked Mechanisms

### 4.1. Rotation: Switching to a New Log File

Neo4j writes transaction logs as sequential files. When the active file reaches a size threshold, the engine **rotates** and continues writing to a new file. Setting:

~~~properties
# neo4j.conf – example default value in current Neo4j documentation
db.tx_log.rotation.size=256MiB
~~~

**256 MiB** is the current default rotation threshold, **not a guarantee that every file stays strictly at or below 256 MiB**. A single large transaction can push a file past the threshold before rotation occurs; the engine does not split one transaction arbitrarily just to fit the cap.

Lowering rotation size produces more, smaller files, letting pruning reclaim space in finer increments. However, it also creates more files and increases rotation frequency. Increasing file size reduces file count, but keeps a **single large file from being pruned** until checkpoint and rotation conditions are met.

### 4.2. Checkpoints: Marking Flushed Data Boundaries

A checkpoint is the process where Neo4j flushes pending changes from the page cache to **store files** and records a recovery marker. It can be triggered by schedule, transaction count, log volume, or certain operational events.

Current default policy:

~~~properties
db.checkpoint=PERIODIC
db.checkpoint.interval.time=15m
db.checkpoint.interval.tx=100000
~~~

Under the **PERIODIC** policy, Neo4j evaluates checkpoint conditions by time and transaction count; once a threshold is reached and there is data to flush, a checkpoint runs. **15 minutes is not a promise that a checkpoint finishes strictly every 15 minutes**: actual duration depends on I/O, dirty page volume, and system load.

### 4.3. Pruning: Deleting Only Eligible Files

**Pruning** is the automatic removal of old transaction logs. A log file can only be safely pruned once foundational conditions are met:

1. The file has **rotated** and is no longer the active write file.
2. There is a **completed checkpoint in a newer log file**, so recovery no longer depends on the old file.
3. The file falls **outside the retention window** defined by the retention policy; backup/cluster dependencies must also be accounted for when designing the policy.

Neo4j triggers pruning evaluation **after a checkpoint**. Therefore, lowering retention from 7 days to 2 days **does not necessarily shrink disk usage immediately**. If no checkpoint has occurred yet, or if entries still sit inside a large active file, seemingly "old enough" files may not yet be reclaimed.

~~~mermaid
flowchart LR
  L0["Log 0: rotated"] --> L1["Log 1: rotated"]
  L1 --> L2["Log 2: active write"]
  C["New checkpoint completed in newer log"] --> P{"Old log outside retention?"}
  P -->|"Yes and safe"| D["Neo4j prunes automatically"]
  P -->|"Not yet"| K["Retained"]
~~~

**Rotation** only switches files, **checkpoints** set recovery markers, and **retention** decides how much history to keep. Tuning one parameter does not substitute for the other two mechanisms.

## 5. Retention Policy: How Much Transaction Log to Keep?

The main setting is **db.tx_log.rotation.retention_policy**. The default in current Neo4j documentation is **2 days 2G**; earlier versions may differ. Always **inspect the running config** instead of assuming your deployed version matches the latest docs.

### 5.1. Common Policy Formats

| Value in neo4j.conf | Meaning | Notes |
|---|---|---|
| **2 days 2G** | Retains logs up to roughly **2 days** and caps log space near **2 GiB** via pruning | Does not guarantee 48 hours under high write load |
| **7 days** | Retains logs containing transactions within a 7-day time policy | Disk usage can grow huge under heavy writes |
| **10 files** | Retains the most recent count of log files per pruning | Time window varies with write rate |
| **500M size** | Retains log files up to a 500 MiB size threshold | Cannot directly infer hours of history |
| **500k txs** | Retains roughly the last 500,000 transactions across log files | Byte footprint can vary widely |
| **keep_all** or **true** | Disables normal time/size/count pruning | Easily grows unbounded; unsuitable as a production default |
| **keep_none** or **false** | Retains only the bare minimum, including the latest non-empty log needed | Can break differential backups and efficient cluster catch-up |

**Syntax note:** formats like **2 days 2G** combine time and size bounds. Do not invent arbitrary forms like **2 years 2G** expecting support; valid units and combinations depend on version. Certain releases starting from **2026.04** added new backup-related policy forms, so inspect the server's **validValues** before using syntax absent from your running release.

### 5.2. Why "2 days 2G" Does Not Promise Two Full Days

Suppose an application writes an average of **1 GiB of transaction logs per hour**. With **2 days 2G**, retaining 48 hours at that rate would require roughly **48 GiB** before overhead; the 2 GiB cap causes older history to be pruned **much sooner than 48 hours**. Conversely, if the database barely writes, retained logs may take very few bytes.

Time and size clauses must be read as **policy bounds**, not an SLA guaranteeing logs always reach back exactly 48 hours or occupy exactly 2 GiB. Actual byte usage is also affected by the active file, rotation size, checkpoints, large transactions, and pruning timing.

### 5.3. Both keep_all and keep_none Carry Risks

**keep_all** sounds safe for recovery, yet it is not a backup strategy: the disk can fill up, writes can halt, and losing the volume loses both stores and logs. Rotated log files must also never be archived away and deleted manually by external scripts; pruning depends on checkpoint awareness.

**keep_none** saves space, but systems relying on **differential backups**, **cluster catch-up**, or **CDC** may need longer transaction history to recover or synchronize. In production Neo4j Enterprise environments, never enable `keep_none` without proving backups, recovery, and downstream consumers still meet requirements.

## 6. Key Settings and Their Resource Impact

| Setting | Role | Default in Current Documentation |
|---|---|---|
| **db.tx_log.rotation.size** | Rotation threshold for transaction log files | **256 MiB** |
| **db.tx_log.rotation.retention_policy** | Log history retained after pruning | **2 days 2G** |
| **db.tx_log.preallocate** | Attempts to preallocate log file space to reduce fragmentation and out-of-space surprises | **true** |
| **server.directories.transaction.logs.root** | Root directory for transaction logs | Depends on data directory location |
| **db.checkpoint** | Checkpoint trigger strategy | **PERIODIC** |
| **db.checkpoint.interval.time** | Time interval for PERIODIC | **15m** |
| **db.checkpoint.interval.tx** | Transaction count interval for PERIODIC | **100000** |
| **db.checkpoint.interval.volume** | Log volume threshold when using VOLUME | **250 MiB** |
| **db.checkpoint.iops.limit** | Best-effort checkpoint I/O cap, Enterprise Edition | **600** |

These values serve as baseline references from current Neo4j documentation. **Always verify against your actual server/edition**, since defaults, setting names, or policies can change across versions.

### 6.1. Checkpoint Modes

| Mode | Mechanism | Best Fit |
|---|---|---|
| **PERIODIC** | Triggered by time and transaction count thresholds | Default choice, sufficient for many systems |
| **VOLUME** | Triggered by generated transaction log volume | When tying checkpoint cadence to write volume |
| **CONTINUOUS** | Runs checkpoints continuously, **Enterprise Edition** | Specialized workloads needing smooth I/O and bounded recovery time |
| **VOLUMETRIC** | Adapts checkpoint/pruning to keep prunable logs aligned, **Enterprise Edition** | Workloads aiming to keep log footprint tight to policy |

**No single policy fits every database.** More frequent checkpoints can reduce crash replay work and allow earlier pruning, but increase flush I/O. Less frequent checkpoints ease short-term I/O pressure at the cost of longer recovery and more logs retained between checkpoints.

### 6.2. Checkpoint I/O Limits

In Neo4j Enterprise Edition, **db.checkpoint.iops.limit** caps the background I/O operations per second that checkpointing attempts to consume. Setting it too low can make checkpoints drag on, accumulating logs and lengthening recovery. Setting it too high can cause flushes to contend with live query I/O.

Starting in **Neo4j 2025.07**, **db.checkpoint.throughput.limit** was added to cap flush speed in bytes/second where supported. Do not copy this parameter into older Neo4j versions; in Neo4j Community, checkpoint I/O throttling does not apply the same way as in Enterprise.

Before tuning thresholds, measure **checkpoint duration**, **pages/bytes flushed**, **log append rate**, **disk I/O**, **query p95**, and **recovery time**. Never raise IOPS solely hoping to delete files faster when the real issue is writers generating logs faster than provisioned disk capacity.

## 7. Designing Retention Around Recovery and Synchronization Needs

To choose a policy, do not just ask "how much disk is free?" Identify every consumer relying on transaction history:

| Dependency | Why It Needs Logs | Risk If Pruned Too Early |
|---|---|---|
| **Crash recovery** | Replays committed transactions not yet fully reflected in store files | Missing logs needed to open the database consistently |
| **Differential backup** | Captures changes since the last backup instead of copying the full store | Change chain broken; may force a full backup or fail the job |
| **Cluster catch-up** | Lagging member receives unapplied transactions | Member may require a heavy store copy/reseeding workflow |
| **CDC consumer** | Reads unconsumed mutations from enriched transaction logs | Consumer cursor/change ID points to pruned history |
| **Incident analysis** | Provides a window to investigate and pinpoint relevant transactions | Insufficient history to audit or recover within system capabilities |

**Retention alone does not provide point-in-time recovery (PITR).** Restoring to a specific timestamp or transaction requires a **valid backup**, an intact backup/log chain, and restore tooling supported by your version/edition. Keeping transaction logs on the same disk as the database does not protect against volume loss or physical corruption.

### 7.1. RPO, RTO, and Transaction Logs

- **RPO (*Recovery Point Objective*)**: maximum data loss acceptable to the business in a disaster.
- **RTO (*Recovery Time Objective*)**: maximum acceptable time to restore service operation.
- **Checkpointing** directly affects crash-replay workload, which influences RTO.
- **Backup cadence, backup availability, and log chains** determine the recoverable point after disaster, influencing RPO.
- **Transaction log retention** must cover log-dependent backups and consumers, but **never replaces backups**.

For example, setting **db.tx_log.rotation.retention_policy=7 days** does not mean you automatically have 7-day backups or can restore to any second within 7 days. Without a usable backup, long retention still cannot recover from total store loss.

### 7.2. Estimating a Disk Capacity Budget

A **rough planning baseline**, not an official sizing rule:

\[
\text{Log budget} \approx
\text{Peak log rate} \times
\text{Required retention window}
\times \text{Headroom factor}
\]

For instance, if a system generates **1.5 GiB of logs/hour** at peak, the longest-lagging consumer needs **24 hours** of history, and ops chooses a **1.5** headroom factor:

\[
1.5 \times 24 \times 1.5 = 54\;\text{GiB}
\]

**54 GiB is a worked arithmetic example**, not a Neo4j requirement. Adjust for reality: log rates spike, transaction sizes vary, CDC log enrichment inflates log bytes, and checkpoints plus rotation cause disk usage to fluctuate. Also budget separately for **store files, indexes, backup staging, the OS, and other logs**.

### 7.3. Two Policy Selection Scenarios

**Scenario A — Standalone instance with daily backups:** if backups can be delayed by a day and write traffic is high, a **2 days 2G** policy may fail to retain enough history for the next differential backup. Measure log volume generated between **two successful backups**, add buffer for a failed backup cycle, and pick retention matching SLAs and disk capacity.

**Scenario B — Cluster + CDC:** if a downstream CDC consumer can pause for **36 hours** and a cluster member might need to catch up after **48 hours**, a **1-day** retention policy is too short for those dependencies. Retention must account for the **longest wait window**, peak write rate, and disk limits; if storage cannot grow, adjust backup/consumer/catch-up designs instead of blindly shrinking retention.

With CDC, remember **CDC must be enabled/enriched** on supported databases. Enabling CDC increases bytes written to the transaction log, causing size-capped retention policies to rotate/prune faster. If a consumer's change ID falls outside retained logs, you cannot fix it simply by re-running an old query without a proper **resnapshot/reseed** plan.

## 8. Inspecting Effective Configuration with Cypher

### 8.1. SHOW SETTINGS as a Safe Observation Step

On self-managed Neo4j with config inspection privileges:

~~~cypher
SHOW SETTINGS
YIELD name, value, defaultValue, isDynamic
WHERE name STARTS WITH 'db.tx_log.'
   OR name STARTS WITH 'db.checkpoint'
   OR name = 'server.directories.transaction.logs.root'
RETURN name, value, defaultValue, isDynamic
ORDER BY name;
~~~

The output shows **active values** on the **executing server**, which is more reliable than just reading **neo4j.conf**. The **isDynamic** column tells you whether a setting can be updated at runtime in supported environments.

**Privilege and environment notes:**

- **SHOW SETTINGS** requires appropriate privileges; ordinary application users may not be allowed to view all settings.
- This command is **not available on Aura** per current admin documentation; Aura manages underlying resources and operational parameters internally.
- In a **cluster**, the command displays settings for the **server executing it**. To compare members, administrators should connect directly to each server using supported methods to check for config drift.

### 8.2. Example neo4j.conf for a Test Environment

~~~properties
# Custom example. DO NOT copy blindly to production.
db.tx_log.rotation.size=256MiB
db.tx_log.rotation.retention_policy=7 days

db.checkpoint=PERIODIC
db.checkpoint.interval.time=15m
db.checkpoint.interval.tx=100000
~~~

This is an **illustrative configuration**; choose 7 days only after measuring log rates and backup/catch-up/CDC dependencies. Depending on organizational policy, you can combine time and size retention, provided the size cap is large enough not to truncate the required time window.

Do not move **server.directories.transaction.logs.root** onto another drive just because you heard it is "faster." Placing logs on separate storage requires verifying reliability, latency, bandwidth, backup synchronization, and full-dataset recovery. Losing either the **store or log** volume can prevent the database from opening.

### 8.3. Dynamic Changes (Enterprise Edition)

Parameters such as **db.tx_log.rotation.retention_policy** and **db.tx_log.rotation.size** are marked **Dynamic**. In **Neo4j Enterprise Edition**, administrators can update dynamic settings on a running server:

~~~cypher
// Example exclusively for test environments and admin accounts.
CALL dbms.setConfigValue(
  'db.tx_log.rotation.retention_policy',
  '7 days'
);
~~~

However:

1. This dynamic command affects **only the target server** and **does not propagate automatically** across all cluster members.
2. Runtime changes are **not automatically persisted** into **neo4j.conf**. Update your deployment configuration management as well, or values will revert on restart.
3. Shortening retention can cause old logs to be pruned at the next checkpoint; that decision may be **irreversible**.
4. For non-dynamic settings, follow the supported config update and restart workflow instead of trying procedure calls.

**Safe practice:** start with **SHOW SETTINGS** and dependency assessment, test changes in staging, then roll out through configuration management with approval and per-server verification.

## 9. Triggering a Manual Checkpoint: Only with Good Reason

Neo4j provides the procedure:

~~~cypher
CALL db.checkpoint();
~~~

This procedure requires appropriate privileges and can trigger **heavy I/O flushing** if many dirty pages are buffered. It can help confirm a checkpoint completes and subsequently trigger pruning checks, yet **it does not guarantee immediate disk savings** if retained files are not yet eligible for deletion.

Never run **CALL db.checkpoint()** repeatedly in production to "cure" a filling log disk without checking:

- Are logs growing rapidly due to an active import or batch job?
- Does the retention policy still require holding logs for backups/CDC/clustering?
- Have the log files rotated yet?
- Are prior checkpoints stalling or failing due to I/O?
- Does the disk still have enough safe headroom to keep committing, rotating, and flushing?

If a database is missing logs or fails recovery, calling checkpoint **is not** a way to reconstruct lost transactions.

## 10. Monitoring Transaction Logs, Checkpoints, and Disk Space

Track measurements together across the **filesystem**, **Neo4j metrics**, and **backup/CDC jobs**.

| Signal | What You Need to Know | Warning Condition |
|---|---|---|
| **Disk free / used** on log volume | Is there enough space for peak writes and rotation? | Free space dropping fast, disk-full risk |
| **Transaction log bytes appended** | Hourly/daily log generation rate | Log rate spiking abnormally above baseline |
| **Log rotation events / duration** | Rotation frequency and operation time | Rapid continuous rotation, rising latency |
| **Checkpoint events / duration** | Are checkpoints running and completing steadily? | Long gaps between checkpoints, growing duration |
| **Checkpoint bytes flushed / I/O limiter** | Flush pressure on disk | Frequent checkpoint throttling or saturated disks |
| **Last committed tx ID** | How far a member has progressed on the tx stream | A cluster member lagging persistently |
| **Lowest available committed tx ID** | Transaction window still present in logs (where supported) | Remaining window too short for backup/catch-up |
| **Backup age + result** | Most recent successful backup and chain validity | Consecutive backup failures |
| **CDC lag / cursor** | How far behind committed changes a consumer sits | Cursor at risk of falling past retained log window |

In Neo4j Enterprise, **metrics** can be exported via supported monitoring integrations. Reference metric names include **log.appended_bytes**, **log.rotation_events**, **check_point.duration**, **check_point.events**, and **transaction.last_committed_tx_id**; exact prefixes and availability depend on version/edition. **transaction.lowest_available_committed_tx_id** was introduced in modern releases—do not assume it exists on every server.

### 10.1. Diagnosing via Checkpoint Logs

Neo4j logs **checkpoint started/completed** events along with duration, pages flushed, and I/O limiter details to operational logs. Use them to distinguish:

- **No new checkpoints:** inspect checkpoint policy, service health, I/O permissions, or logs.
- **Very slow checkpoints:** may indicate heavy write load, slow disks, or an overly tight IOPS limit.
- **Checkpoints complete yet logs stay large:** retention still holds them, a large file is not yet eligible for pruning, or new writes replace pruned space.
- **Log growth jumps after enabling CDC:** log enrichment increases bytes written per transaction; update sizing.

If checkpoints fail or storage throws I/O errors, prioritize data safety and infrastructure investigation rather than deleting files.

## 11. Runbook: Abnormal Transaction Log Growth

When alerted that a log volume is filling up, follow a conditional workflow:

~~~mermaid
flowchart TD
  A["Alert: transaction log growth / low disk free"] --> B["Confirm exact volume and database"]
  B --> C["Measure log write rate, rotation, checkpoints"]
  C --> D{"Are checkpoints completing?"}
  D -->|"No"| E["Investigate I/O errors, flush latency, resource limits"]
  D -->|"Yes"| F{"Is retention holding logs for backup/CDC/cluster?"}
  F -->|"Yes"| G["Check backup/consumer lag and expand storage if needed"]
  F -->|"No or misconfigured"| H["Evaluate new policy in staging and roll out safely"]
  E --> I["Restore operational capacity per approved runbook"]
  G --> I
  H --> I
  I --> J["Verify backups, recovery, and alerts after changes"]
~~~

### Step 1 — Confirm the Scope

Identify the exact **database**, server/cluster member, transaction log path, volume, and growth rate. Distinguish that database's logs from **query/debug logs**, backup staging, or Raft data. With multiple databases, each maintains its own logs, so never treat server-wide disk usage as proof that one specific database is misbehaving.

### Step 2 — Inspect Configuration and Backup State

Run **SHOW SETTINGS** for **db.tx_log** and **db.checkpoint**. Check whether policy changed in a recent deploy; verify the **last successful backup**, next scheduled backup, **CDC** requirements, and cluster member health. Never lower retention until you answer: "who still depends on the logs about to be pruned?"

### Step 3 — Inspect Rotation and Checkpoints

Compare **log appended rate**, rotation size, latest checkpoint log entries, checkpoint duration, and bytes flushed. If checkpoints are stuck or incomplete, shortening retention will not immediately reclaim space.

### Step 4 — Choose the Lowest-Risk Action

- **If logs grew from a sudden write burst:** throttle batches/imports, consider lowering write concurrency, or expand storage safely.
- **If checkpoints are I/O-bound:** investigate disk latency, throughput/IOPS caps, page cache, and query load; do not force repeated checkpoints.
- **If retention exceeds actual needs:** after verifying backup/CDC/cluster safety, get approval for a revised policy, schedule the change, and monitor pruning.
- **If backup/CDC already fell outside the log window:** execute a **fresh full backup** or **resnapshot/reseed** per supported procedures; lengthening retention **after logs have been pruned** cannot resurrect old transactions.
- **If disk is critically full:** trigger the storage and backup incident runbook and pause write workloads if operationally authorized; **never delete transaction log files manually**.

### Step 5 — Post-Remediation Verification

Confirm the database reads and writes cleanly, transactions commit without errors, checkpoints complete, log usage stabilizes, the next backup succeeds, and consumers/cluster members stay able to catch up. Record config changes and before/after metrics for operational regression checks.

## 12. Testing Policy Changes Before Production

A test environment with realistic traffic helps evaluate not only log byte totals, but also recovery and backup impact.

### 12.1. Generating Controlled Write Load

In a test database, create a constraint:

~~~cypher
CREATE CONSTRAINT demo_resource_order_unique IF NOT EXISTS
FOR (o:DemoResourceOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

Run a controlled identifier batch via Java Driver or a load tool, for example:

~~~cypher
UNWIND $orderIds AS orderId
MERGE (o:DemoResourceOrder {orderId: orderId})
ON CREATE SET
  o.status = 'CREATED',
  o.createdAt = datetime()
SET o.lastMeasuredAt = datetime();
~~~

Here **$orderIds** is an ID list from a load generator, not arbitrary user input. **MERGE** prevents duplicate nodes per ID on re-runs, though **SET o.lastMeasuredAt** still writes mutations when properties change. To compare log rates fairly, keep batch count, transaction count, total duration, and payload size consistent across test runs.

Never run load-generation tests in production or on a Neo4j Aura tier without operational authorization for those resources.

### 12.2. Test Matrix

| Test | What to Observe | Evaluation Criteria |
|---|---|---|
| **Old vs. new retention** | Log footprint across checkpoints | Retains required window for backup/CDC/catch-up |
| **Rotation 256MiB vs. alternate** | File count, rotation frequency, pruning | No unnecessary file/rotation overhead |
| **Checkpoint PERIODIC vs. VOLUME** | Duration, log growth, query p95 | Balances recovery time and I/O pressure |
| **Differential backup after delay** | Can backup still continue incrementally? | Valid backup chain, no unexpected full fallback |
| **Restart after safely simulated crash** | Recovery time and committed data | Zero loss of acknowledged committed data |
| **Paused CDC consumer** | Can it resume from its old cursor? | Within SLA-backed retention window |
| **Controlled offline cluster member** | Catch-up on rejoin | No unexpected store copy required |

Tests involving **crashes**, **failover**, or **stopping members** must only run in isolated environments with recovery plans and operator approval. Never kill a production Neo4j process just to measure checkpointing.

### 12.3. Post-Restart Data Reconciliation

~~~cypher
MATCH (o:DemoResourceOrder)
RETURN count(o) AS totalOrders;
~~~

~~~cypher
MATCH (o:DemoResourceOrder)
WHERE o.orderId IS NULL
RETURN count(o) AS missingIds;
~~~

These two queries provide only **partial evidence**. Also verify the exact **orderIds acknowledged as committed by the app**, expected properties and relationships, failed transaction counts, recovery log messages, and backup integrity. A matching node count is not enough if properties were corrupted or relationships are missing.

## 13. Version, Cluster, and Managed Service Compatibility

### 13.1. Neo4j 4.x, 5.x, and Calendar-Versioned Releases

The setting examples in this lesson target **Neo4j 5 and current releases**. Older releases (especially Neo4j 4.x) use **different setting names**, such as the **dbms.tx_log...** family. When upgrading, never copy an old **neo4j.conf** verbatim assuming every key remains valid.

Recommended sequence:

1. Check **source/target versions** and the migration guide.
2. Check **changed/removed settings** tables and valid retention syntax.
3. Verify using **SHOW SETTINGS** or configuration docs for the target server.
4. Validate in staging under realistic data and write volumes.
5. Roll out to production only after verifying backup/restore, checkpoints, and log retention.

### 13.2. Clusters Require Per-Member Control

Runtime dynamic updates may affect **only one server**. If members run with mismatched retention, **catch-up**, backup, and CDC behavior can diverge. Manage every member through cluster-wide configuration rules and drift checks.

**Transaction logs and Raft logs are not the same.** Raising transaction log retention does not alter Raft log pruning, and manually deleting Raft logs will not fix transaction log incidents.

### 13.3. Docker and Aura

In self-managed Neo4j Docker, settings can be supplied via **neo4j.conf**, managed images, or environment variables. When converting setting names to environment variables, underscores in the **original setting name** require escaping per Neo4j's image rules; never guess env var names by replacing every dot with a single underscore when underscores exist in the key.

On **Aura**, transaction log and checkpoint settings are largely platform-managed; users do not have the same direct control over **neo4j.conf**, filesystems, or checkpoints as on self-managed servers. Rely on Aura SLAs, backup/restore features, and official Aura documentation rather than OS-level file deletion or config runbooks.

## 14. Common Misconceptions

1. **"If commit succeeded, store files are already checkpointed."** False; durability and store flushing operate on distinct lifecycles.
2. **"A checkpoint is a backup."** False; checkpoints do not create independent copies isolated from the active disk.
3. **"Rotation deletes old files."** False; rotation only switches files, whereas pruning requires checkpoints and retention rules.
4. **"2 days 2G guarantees a full 48 hours."** False; the size cap can truncate the history window early.
5. **"Lowering retention immediately frees disk space."** Not guaranteed; logs are pruned only when safe checkpoint and rotation conditions are met.
6. **"Old logs can be deleted with rm/Explorer."** False; unsupported by Neo4j and can destroy recoverability.
7. **"Keeping all logs counts as a backup."** False; losing the volume loses both databases and logs.
8. **"keep_none is always optimal."** False; it can break differential backups, CDC, and cluster catch-up.
9. **"Increasing checkpoints infinitely always speeds things up."** False; checkpoints consume I/O and can contend with live queries.
10. **"SHOW SETTINGS on one server represents the whole cluster."** False; inspect each server and deployment config.
11. **"Query logs and transaction logs are the same thing."** False; they serve different purposes with separate rotation policies.
12. **"Raising retention after CDC loses its cursor recovers old data."** False; already-pruned logs cannot be recreated by changing config.
13. **"Disabling db.recovery.fail_on_missing_files repairs a database."** False; bypassing missing-log checks risks data integrity and is not a standard recovery procedure.

## 15. Practice Exercises

### Exercise 1 — Classifying Logs

A Neo4j host sees **debug.log** growing rapidly, while another database accumulates many files under **data/transactions**. Explain why the two issues require different policies and diagnostic tools, and identify which log type is needed for crash recovery.

### Exercise 2 — Retention Too Short for Backup Window

A system generates an average of **800 MiB of transaction logs/hour**, runs differential backups every **12 hours**, but occasionally experiences **24-hour** delays. Assess the risk of keeping **2 days 2G**. Propose the measurements, retention window, and headroom to evaluate without picking a rigid config before knowing disk size and SLAs.

### Exercise 3 — Rotation, Checkpoints, and Pruning

Suppose Log 4 has rotated, Log 5 is currently active, and the latest checkpoint resides in Log 4. Can Log 4 be deleted immediately? What condition must occur for safe pruning? Once a checkpoint completes in Log 5, if policy requires keeping more history, will Log 4 be deleted right away?

### Exercise 4 — Dynamic Configuration

A cluster administrator changes retention on server A via **dbms.setConfigValue**, then server A restarts and reverts to the old value. Explain both causes: **per-server scope** and **runtime changes not persisting to neo4j.conf**. Design a config-drift check step.

### Exercise 5 — Lagging CDC Consumer

A CDC consumer stops for 30 hours, while logs only retain roughly 12 hours of history due to a size cap. Identify the risk to the old cursor, the appropriate resnapshot/reseed workflow, and how to size a new retention policy.

### Exercise 6 — Checkpoints Slowing Down Queries

After lowering checkpoint thresholds, test recovery duration improves, yet production query p95 climbs. List the metrics to collect to determine whether checkpoints are saturating I/O bandwidth. Should **db.checkpoint.iops.limit** be raised indefinitely?

### Exercise 7 — Writing a Safe Runbook

The transaction log volume reaches 95%, the latest backup failed, and the database is still accepting writes. Draft a runbook ordered by priority: **protect data → identify root cause → reduce disk-full risk → restore healthy backups → post-fix reconciliation**. Explain why manually deleting logs is unacceptable.

## 16. Conclusion

**Transaction logs**, **checkpoints**, and **retention policies** are three distinct mechanisms working together so Neo4j can recover from crashes, preserve necessary change history, and avoid unbounded disk growth.

- **Transaction logs** record mutations to protect committed transactions and support differential backups, cluster catch-up, and CDC.
- **Checkpoints** flush data to store files, set recovery markers, and enable pruning checks.
- **Rotation** splits logs into files; **retention** decides how much history to preserve; **pruning** removes only logs meeting safety criteria.
- **Policy design** must reflect log rate, backup/CDC/cluster lag, RPO/RTO targets, and storage budgets—never a blindly copied default.
- **Safe operations** start with inspecting config and metrics, never manual file deletion.

Before any production change, test under a representative workload, verify backup restorability, and confirm that every system depending on transaction logs continues operating normally after pruning.

### Official Neo4j Documentation

- [Neo4j Operations Manual – Transaction logging](https://neo4j.com/docs/operations-manual/current/database-internals/transaction-logs/)
- [Neo4j Operations Manual – Checkpointing and log pruning](https://neo4j.com/docs/operations-manual/current/database-internals/checkpointing/)
- [Neo4j Operations Manual – Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)
- [Neo4j Operations Manual – Show configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/show-settings/)
- [Neo4j Operations Manual – Update dynamic settings](https://neo4j.com/docs/operations-manual/current/configuration/dynamic-settings/)
- [Neo4j Operations Manual – Database backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual – Online backup](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual – Metrics reference](https://neo4j.com/docs/operations-manual/current/monitoring/metrics/reference/)
- [Neo4j Change Data Capture – CDC on Neo4j DBMS](https://neo4j.com/docs/cdc/current/get-started/self-managed/)
- [Neo4j Change Data Capture – Troubleshooting](https://neo4j.com/docs/cdc/current/troubleshooting/)
