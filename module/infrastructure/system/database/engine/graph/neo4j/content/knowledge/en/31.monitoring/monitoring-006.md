# Monitoring Data Size, Indexes, and Transaction Logs

A Neo4j database can continue answering Cypher queries normally while its storage partition is nearly full, an index has failed to finish building, or transaction log files are growing faster than planned. By the time the application begins hitting write errors, severe query latency spikes, or backup failures, the safe remediation window may already be very narrow. **Capacity monitoring must clearly separate durable data, indexes, transaction logs, and infrastructure resources—never rely solely on total node count.**

This lesson belongs to the **Monitoring** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j organizes connected data as a **property graph**, supporting node, relationship, and path queries with Cypher, indexes/constraints for lookups, and the Java Driver and Spring Data Neo4j for application integration. These components produce distinct read, write, and growth patterns; therefore operators must track **store size, index state and size, transaction logs, growth rates, remaining disk space, and recovery readiness**.

After this lesson, you will be able to:

- Explain the difference between **data store**, **indexes**, **transaction logs**, **query logs**, and **page cache** memory.
- Collect capacity metrics on self-managed deployments and understand monitoring limits in managed Neo4j tiers.
- Use `SHOW INDEXES` to track `ONLINE`/`POPULATING`/`FAILED` states, paired with `EXPLAIN`/`PROFILE` to verify indexes actually serve queries.
- Inspect and verify transaction log **rotation/retention** policies without manually deleting log files.
- Design charts, alert thresholds, disk exhaustion forecasts, and incident response runbooks.
- Test a monitoring setup with realistic data, generated logs, and missing-privilege or missing-metrics scenarios.

> **Version scope:** Setting names, metrics, privileges, and dashboards vary across Neo4j versions, Community/Enterprise Editions, cluster topologies, and Aura tiers. Cypher examples target Neo4j 5.x and newer releases supporting the corresponding commands. Verify your exact version and deployment documentation before copying administrative commands to production.

## 1. Three Critical Capacity Components

Simple model:

~~~text
Java / Spring Data Neo4j Application
                 |
                 v
          Cypher read / write
                 |
        +--------+----------+
        |                   |
        v                   v
    Data store           Index store
  node, relation,      range, lookup,
  property, metadata   text, point,
                      full-text, vector...
        |                   |
        +--------+----------+
                 |
         Transaction commit
                 |
                 v
       Transaction log files
           rotation / pruning
                 |
                 v
     Recovery, backup, and catch-up
       capability per deployment
~~~

| Component | What Does It Contain? | Why Can It Grow? | Can It Be Deleted Directly to Free Disk? |
| --- | --- | --- | --- |
| **Data store** | Durable node, relationship, property, and metadata structures. | Loading nodes/relationships, growing properties, model changes. | **No.** Must use supported data operations and proper operational procedures. |
| **Index store** | Lookup structures for labels/types, properties, full-text, vector, and constraint-backing indexes. | Creating indexes, adding indexed data, updating values, rebuilding. | **No.** Managed via schema commands and supported procedures. |
| **Transaction log** | Records of transactional mutations required for recovery and progress tracking, depending on config. | High write rates, large transactions, rotation/retention, recovery/backup/catch-up demands. | **Never delete via file manager while the database is running.** |

In self-managed Neo4j, these files may reside on different paths or volumes. **Total database size does not necessarily equal the sum of files under one single directory.** You must know the configured locations of the store, transaction logs, and backup staging for your exact deployment.

### 1.1. Transaction Logs Are Not Query Logs

- **Transaction logs** belong to the database transaction and recovery engine; they govern post-commit durability.
- **Query logs** record executed Cypher statements per logging policy, typically used for performance and operational diagnostics.
- **Security/debug/server logs** cover authentication, errors, or operational events depending on version/edition capabilities.

Never infer transaction log retention from `query.log` rotation policies. Never use total transaction log size to estimate read query volume directly; a read-only query does not generate mutation records like a write transaction.

### 1.2. On-Disk Storage vs. Working Memory

Neo4j also uses the **page cache** to keep hot data/index pages in memory. Page cache size is not a duplicate file copy added to disk usage; caching a page does not double the data store on disk.

In addition, there are **heap**, native memory, transaction/query memory, and projected graph memory in **Graph Data Science** if GDS is deployed. Store files can be much larger than RAM and still run, while performance depends on the working set, page cache hits/misses, and I/O throughput.

**Principle:** when investigating "out of disk space", inspect disks/volumes. When investigating slow queries despite plenty of free disk, inspect page cache, CPU, I/O, query plans, locking, and graph structure. Both signal groups relate, yet they are not interchangeable.

## 2. Define Scope and Units Before Building Dashboards

Before reading numbers, document:

1. **Deployment:** self-managed or Aura, Community or Enterprise, single instance or cluster.
2. **Database and instances:** which database name, how many servers hold replicas, and leader/follower roles.
3. **Volumes:** do data store, transaction logs, backups, OS logs, and temp filesystems share one disk?
4. **Units:** bytes, base-1024 MiB/GiB vs. base-1000 MB/GB.
5. **Measurement timestamps:** were values sampled in the same time window and on the same instance?
6. **Collection health:** are there dropped samples, permission-blocked metrics, instance restarts, or stopped collectors?

Distinctions to preserve:

| Measure | Meaning | How Can It Be Misread? |
| --- | --- | --- |
| Total store file bytes | Physical space currently used by the measured store. | Not the exact byte count of "live" business payloads. |
| Index size | On-disk bytes consumed by measured indexes. | Does not scale strictly linearly with node count. |
| Transaction log bytes | Bytes of currently retained transaction log files. | Does not equal the entire mutation history of the system. |
| Disk free bytes | Remaining allocatable filesystem bytes on that volume. | A database may use a different volume or separate quota. |
| Logical data counts | Number of nodes, relationships, or records matching a filter. | Cannot directly deduce exact GB on disk. |
| Write rate | Transactions/sec, bytes written/sec, changes over time. | Steady small writes vs. huge bursts create very different pressure. |

**Never sum the sizes of each cluster replica and call it "one logical database's size".** If three servers hold three replicas, infrastructure footprint equals the sum across three copies, yet the database's logical size remains one replicated dataset. Dashboards should provide both **per-database** and **per-instance/volume** views.

## 3. Measurement Sources on Self-Managed and Aura

| Source | Self-Managed | Managed / Aura | Notes |
| --- | --- | --- | --- |
| OS / filesystem stats | Disk free/used, latency, inodes, directory sizes when authorized. | Typically no direct host OS access. | Inspect the actual volume, not just the app disk. |
| Neo4j metrics / monitoring endpoint | Exportable via version/edition monitoring mechanisms, Prometheus/JMX/CSV if supported. | Dashboards/metrics and export features provided by service tier. | **Metric names change across versions**; never invent names. |
| Cypher admin commands | `SHOW DATABASES`, `SHOW INDEXES`, `SHOW SETTINGS`, `SHOW TRANSACTIONS` per privileges. | Commands permitted by the service; may be restricted. | Not every command returns byte sizes. |
| Neo4j logs | Observe errors, index population, transactions/backups per logging config. | Service logs accessible via console/API per tier. | Logs may lag or be filtered; protect sensitive data. |
| Backup service / object storage | Backup size, last successful timestamp, restore readiness. | Provider-supported backup dashboards/policies. | A completed backup does not prove a tested restore. |

### 3.1. Never Assume One Universal Metric Name Across Versions

For example, a Prometheus setup might track the following logical series:

~~~text
neo4j_database=neo4j
instance=graph-01
measure=store_bytes | index_bytes | tx_log_bytes
sample_time=...
value_bytes=...
~~~

This is an **illustrative internal naming/labeling model**, not built-in Neo4j Prometheus metric names. During real setup, pull the metric catalog **from the actual exporter/endpoint of your running version** and map it into consistent dashboard panels. If an exporter lacks a field, supplement with a filesystem collector or another authorized measurement source.

For Aura, never assume you can edit `neo4j.conf` or browse data directories. Use metrics, alerts, and scaling workflows provided by your tier; if a requested detail is not exposed, document the observability gap rather than fabricating numbers.

## 4. Measuring Store Size and Logical Data Volume

### 4.1. Checking Disk/Volume on Self-Managed Systems

Shell examples **on a self-managed Linux host** with appropriate privileges, after verifying exact paths from active configuration:

~~~bash
# Replace example paths with verified live paths.
df -h /var/lib/neo4j/data
du -sh /var/lib/neo4j/data/databases/neo4j
du -sh /var/lib/neo4j/data/transactions/neo4j
~~~

These illustrate OS-level measurement—**not commands to run inside Cypher**. Transaction logs may be configured onto a separate volume; containers, Kubernetes, Windows, or network storage use different mounts. Read paths from the actual installation rather than guessing defaults.

Discrepancies to account for:

- `du` sums visible files in a directory tree, while `df` reports remaining filesystem space. The two do not reconcile trivially due to metadata, snapshots, reserved blocks, other files, and deleted files still held open by processes.
- A large file unlinked from a directory while still held open by a file handle keeps `df` free space from increasing as expected.
- Filesystem compression, thin provisioning, snapshots, or storage quotas can make "logical size", "allocated size", and "physical size" diverge.
- Indexes may live inside the store directory or be included in store totals, so **never double-count two overlapping metrics**.
- Disk usage from app logs or backups can compete directly with data even when the database store itself isn't growing.

**Never modify or delete database/log files via OS commands** to "clean up" a running Neo4j instance. File-level database changes require backup/restore procedures or supported Neo4j tooling.

### 4.2. Inspecting Running Databases

Database status check command:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
RETURN name, currentStatus, requestedStatus
ORDER BY name;
~~~

This command reports status, **not byte size**. Never treat `currentStatus = 'online'` as proof that enough disk remains to commit a large transaction.

Logical count queries:

~~~cypher
MATCH (n:Customer)
RETURN count(n) AS customerCount;
~~~

~~~cypher
MATCH ()-[r:PLACED]->()
RETURN count(r) AS placedRelationships;
~~~

These two examples assume the `Customer` label and `PLACED` relationship type exist; they do not mutate data. Results help track growth by **business entity**, yet do not replace on-disk store/index sizes.

For certain simple `count` patterns, Neo4j can read count store statistics; with complex filters, traversals, or `DISTINCT`, counting queries can become very expensive. Never run full-graph inventory scans every few seconds in production. Prefer low-cost metrics, scheduled reports, and reliably maintained statistics.

### 4.3. Reading Growth Rates by Data Layer

Track at minimum:

- `storeBytes`: data store size from a consistent source.
- `indexBytes`: index size, avoiding double-counting inside store.
- `txLogBytes`: total retained transaction logs.
- `freeBytes`: remaining space on the corresponding filesystem.
- `nodeCount` and `relationshipCount` for key labels/types when an inexpensive source exists.
- New write rate, transaction commits, and import volume over time.

Breaking down by tenant, label, relationship type, or ingestion date helps locate growth sources, yet **Neo4j does not natively report exact byte size per label**. One node carrying huge properties can consume more bytes than hundreds of tiny nodes. If exact per-tenant cost attribution is needed, build a custom estimation method and document its margin of error.

## 5. Monitoring Indexes: Existence, State, and Effectiveness

An index is not merely "present or absent". It has a build state, type, label/relationship scope, and direct impact on both query speed and disk usage.

### 5.1. Listing and Monitoring States

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties,
      state, populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties,
       state, populationPercent
ORDER BY name;
~~~

These fields are used in Neo4j versions supporting `SHOW INDEXES`. Depending on version, edition, and index state, extra columns may appear such as provider, owning constraint, failure message, read count, or last read timestamp. **Do not assume every extra column exists across all versions.**

| Common State | Interpretation | How to Respond |
| --- | --- | --- |
| `ONLINE` | Index is ready to serve as supported by the database. | Inspect query plans to verify queries actually use it. |
| `POPULATING` | Neo4j is building/populating the index. | Monitor progress, duration, CPU/I/O, and disk space; do not treat as ready. |
| `FAILED` | Index did not complete or hit an error and is unusable. | Gather failure reason, logs, and resource state; remediate per runbook. |

Indexes span **lookup, range, text, point, full-text, and vector** types per version features. Each type serves specific query patterns; no single index optimizes every Cypher operation.

### 5.2. Pairing Indexes with Constraints

A uniqueness constraint uses a backing index for enforcement. For example, keying customers by tenant and customer ID:

~~~cypher
CREATE CONSTRAINT mon_demo_customer_unique IF NOT EXISTS
FOR (c:MonDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

This command **alters schema**; run it only on a practice database with appropriate privileges. If the schema contains constraints/indexes protecting business keys, never drop an index merely because it appears "rarely read". Dropping a constraint removes uniqueness enforcement and can alter query execution plans.

For constraint-owned indexes, check ownership in `SHOW INDEXES`/`SHOW CONSTRAINTS` per your version, and evaluate critical queries and write costs before modifying anything.

### 5.3. Having an Index Does Not Guarantee Queries Use It

Example looking up a customer within a tenant:

~~~cypher
EXPLAIN
MATCH (c:MonDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.displayName AS name;
~~~

If actual execution cost is needed:

~~~cypher
PROFILE
MATCH (c:MonDemoCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.displayName AS name;
~~~

`EXPLAIN` builds the predicted plan without executing; `PROFILE` **executes the query** and displays stats like `Rows` and `DB Hits` as supported by the version/runtime. Run `PROFILE` only on representative read queries under safe conditions; never run it recklessly on write/destructive statements in production.

Observe:

1. Does the query start with an appropriate index seek/scan or scan excessive nodes?
2. Where are tenant filters applied?
3. Does it expand millions of relationships after locating the right starting node?
4. Is there a large `Sort`/`Aggregation` at the end?
5. Is the index `ONLINE` yet slow due to data skew, fan-out, network, or page cache misses?

**A new index increases storage size and write cost**, yet helps nothing if queries lack matching predicates. Conversely, a query that finds its starting node accurately via index but stalls during traversal needs data-model/query fixes rather than blindly adding more indexes.

## 6. Monitoring Index Creation and Rebuilds

On large databases, creating range/full-text/vector indexes can consume substantial **CPU, I/O, memory, and temporary disk space** during population. Watch both **state** and **resources**.

| Metric | What Does It Tell You? |
| --- | --- |
| `POPULATING` state, `populationPercent` | Confirms the index is building and shows reported progress. |
| Elapsed time since start | Is the build taking abnormally long for the dataset and hardware? |
| Free bytes and space change rate | Is there enough headroom for the new index, incoming writes, and logs simultaneously? |
| CPU/I/O and page-cache pressure | Is population degrading application query SLOs? |
| Index-related DB/log errors | Is there an explicit reason for `FAILED` or stalled population? |
| Transaction write rate | Is data mutating heavily during build, affecting progress? |

### 6.1. When an Index Stays in POPULATING Too Long

Do not reflexively drop and recreate. First:

- Verify whether progress is genuinely advancing or merely updating slowly.
- Read available error messages and authorized system logs.
- Verify sufficient disk space and absence of I/O saturation.
- Check indexed nodes/relationships, property sizes, type compatibility, and version/provider behavior.
- Assess the impact of concurrent imports and writes.
- Choose a proper change window, rollback plan, and backup before recreating.

Every rebuild creates its own **disk usage spike** and repeats expensive work. A `FAILED` index must have its root cause resolved before retrying so the failure doesn't repeat.

### 6.2. Don't Treat Low Read Counts as Sufficient Reason to Drop

An index might serve a critical scheduled job that runs infrequently, or back a constraint. If your version exposes `readCount`, `lastRead`, or similar metrics, combine **query frequency, SLOs, data-integrity rules, and write overhead**. Avoid drawing conclusions from a single week of observation that missed peak periods or monthly reporting cycles.

## 7. Transaction Logs: Role and Lifecycle

Transaction logs record mutations so Neo4j can ensure **durability/recovery** and other supported coordination mechanisms. They directly govern:

- State recovery after a crash or unclean restart.
- Transaction progress management and replayability of changes.
- Backup/restore and recovery history retention per feature and architecture.
- In clusters, catch-up/replication needs depend on member states and how Neo4j stores/retains logs; never copy a single-instance policy blindly to a cluster.

### 7.1. Rotation and Retention Are Two Different Things

**Rotation** creates a new log file according to policy (e.g., file size threshold). **Retention/pruning** determines which older files may be kept or deleted according to policy and engine safety constraints.

~~~text
Transaction commits
       |
       v
 tx-log-file-N      (actively writing)
       |
       +--- rotation --->
       |
 tx-log-file-N+1    (actively writing)
       |
   older files
       |
 retention / safe pruning
       |
 eligible for deletion when engine allows
~~~

Therefore:

- Rotation happening **does not mean** transaction log disk usage drops immediately.
- Setting a shorter retention **does not guarantee** old files vanish the instant config changes.
- Retaining more transaction logs supports certain recovery/catch-up scenarios while raising disk requirements.
- An overly aggressive retention policy may limit log-based recovery or force fallback to full backups/snapshots depending on architecture.

**Never delete, rename, or compress Neo4j-managed transaction log files via OS filesystem actions.** Doing so can prevent database startup, break recovery, break cluster catch-up, or corrupt the required log chain.

### 7.2. Inspecting Current Settings

On versions supporting `SHOW SETTINGS` with an authorized account:

~~~cypher
SHOW SETTINGS
YIELD name, value
WHERE name STARTS WITH 'db.tx_log.'
RETURN name, value
ORDER BY name;
~~~

Modern Neo4j releases provide settings for **rotation size** and **rotation retention policy** (e.g., `db.tx_log.rotation.size` and `db.tx_log.rotation.retention_policy`). Older releases may use different prefixes. If a setting does not appear, check docs for your exact version and verify privileges; never assume retention is disabled.

An illustrative policy syntax from supported version docs:

~~~properties
# Learning example: NOT a universal production recommendation.
db.tx_log.rotation.retention_policy=7 days
~~~

`7 days` illustrates syntax only. **There is no single log retention period right for every system.** Your choice must account for backups, recovery goals (RPO/RTO), write rate, maximum expected member downtime for catch-up, disk capacity, and operational requirements.

Never assume a dynamic setting change takes effect instantaneously across every cluster member or survives restarts without verifying update mechanics, dynamic/static scope, and active target scope.

### 7.3. Why Do Transaction Logs Balloon?

| Scenario | What to Verify |
| --- | --- |
| Bulk imports, backfills, or mass updates | Did write rate and log bytes spike strictly during the import window? |
| Huge transactions | Are batch sizes reasonable or is one transaction running far too long? |
| Long retention policy | Does expected log footprint match write rate × retained days? |
| Pruning stalled or deferred | Are recovery/backup/cluster conditions pinning logs, or checkpoint/system errors occurring? |
| Server/volume nearly out of space | Can the filesystem still append new logs and checkpoint safely? |
| Unexplained growth | Are retry loops, buggy updaters, abnormal batches, or new app features generating extra writes? |

Do not treat every case of "large logs" as a bug. During an approved data load, rapid log growth may be completely expected; the real question is whether **adequate headroom was reserved for the peak and growth returns to baseline afterward**.

## 8. Checking Transactions and Related Operational Factors

With an authorized admin/monitoring account per version:

~~~cypher
SHOW TRANSACTIONS
YIELD transactionId, database, username, elapsedTime, status
RETURN transactionId, database, username,
       elapsedTime, status
ORDER BY elapsedTime DESC
LIMIT 20;
~~~

This helps investigate **long-lived transactions**, though it does not measure total transaction log size. Displayed columns and visibility privileges vary across Neo4j versions. Never log raw `currentQuery` or parameters if they risk exposing sensitive data.

Supporting metrics worth watching:

- Active transactions, commits/rollbacks over time.
- Long transaction durations and wait/lock states if supported by metrics.
- Transaction log append rate, rotation frequency, and pruning intervals if reliably exposed.
- Checkpoint timing/duration, backup duration, and latest backup status.
- In clusters, catch-up lag, member states, and risk of a stopped member falling behind retained logs.
- Disk latency, fsync/write latency, IOPS, and free space on the log volume.

A single long transaction is not necessarily the sole reason pruning is blocked; inspect exact version metrics and logs. Never rush to run `TERMINATE TRANSACTIONS` in production simply upon seeing a long transaction: it may be a legitimate business job whose mid-flight abort disrupts an important pipeline.

## 9. Calculating Growth Rate and Forecasting Disk Exhaustion

A useful dashboard doesn't just say "20 GiB free". It must tell you **how long that 20 GiB will last given actual growth rates and expected peaks**.

Suppose:

- The volume holding store and transaction logs has **120 GiB** free.
- You reserve an **operational headroom floor of 40 GiB** so the database, backups/checkpoints, logs, and OS always have room to operate.
- Recently, net usage has grown by an average of **8 GiB/day**.

Usable space before touching the operational reserve is `120 - 40 = 80 GiB`. At the assumed constant rate, time to reserve threshold is roughly `80 / 8 = 10 days`. This is an **example**, not a guarantee the system can run cleanly for 10 days; imports, index builds, snapshots, and retention shifts can trigger sudden spikes.

### 9.1. Window-Based Formulas

Given two reliable measurements:

\[
\text{growthBytesPerDay} =
\frac{\text{usedBytes}_{t_2}-\text{usedBytes}_{t_1}}
{t_2-t_1\text{ (days)}}.
\]

When net growth is positive and a reserve exists:

\[
\text{daysToHeadroom} \approx
\frac{\text{freeBytes}-\text{reserveBytes}}
{\text{growthBytesPerDay}}.
\]

If growth is zero or negative, never divide by zero or report "infinite days"—state that current extrapolation **cannot estimate an exhaustion date**. If `freeBytes <= reserveBytes`, the system is already inside the alert zone requiring action.

### 9.2. Measuring Growth Across Multiple Windows

| Window | Good for Detecting | Risk If Used Alone |
| --- | --- | --- |
| 5–15 minutes | Write bursts, abnormal log spikes, I/O peaks. | Sensitive to short-term noise, prone to false alarms. |
| 24 hours | Daily net growth, nightly jobs, and backup cycles. | Misses weekly patterns or reporting cycles. |
| 7 days | Day-of-week patterns, sustained growth trends. | Misses monthly special events. |
| 30–90 days | Long-term capacity/budget forecasting. | Reacts too slowly to newly introduced regressions. |

Measure **separate deltas** for store, indexes, and transaction logs. For example, total disk usage jumping 100 GiB after building a vector index is completely different from transaction logs jumping 100 GiB due to a replay job. Risks and fixes differ accordingly.

**Forecasts must include peak overhead**: before importing 500 GiB of new data, budget for data, indexes, transaction logs, population overhead, temporary backups, and operational headroom—not just projected node count.

## 10. Minimum Capacity Dashboard for Neo4j

An operational dashboard should include the panels below, labeled by **database, instance, cluster/region, and volume** when supported:

| Group | Charts / Metrics | Question Answered |
| --- | --- | --- |
| Capacity | Used/free bytes per volume; percent used | Which limit are we approaching? |
| Growth | Daily store size, GiB/day growth rate | Is demand growing steadily or bursting? |
| Indexes | Total index size, `ONLINE/POPULATING/FAILED` states | Are any indexes unusable or populating too long? |
| Transaction logs | Total log bytes, rotation/pruning, and log growth rate where exposed | Are logs retained per plan or growing out of control? |
| Transactions | Commit/rollback rates, long transactions, lock waits | Are write rates or long transactions abnormal? |
| Resources | Disk latency, CPU, memory/page-cache pressure | Is the bottleneck I/O or memory rather than disk space? |
| Availability | Database status, cluster health, member lag | Are all replicas serving and keeping up? |
| Recovery | Last successful backup, backup age, restore drills | Is there a reliable recovery path if disaster strikes? |
| Collection | Scrape success, collector lag, metric staleness | Do flat lines mean stability or a dead collector? |

**Always monitor for missing monitoring data.** A flat line on a chart may mean a failed exporter rather than zero database growth.

### 10.1. Example Snapshot Schema per Collection Cycle

~~~text
timestamp_utc | database | instance | store_bytes |
index_bytes | tx_log_bytes | volume_free_bytes |
db_status | index_failed_count | backup_age_hours
~~~

This is an **illustrative internal schema**, not direct Neo4j output. When combining metrics from multiple sources, record both `source` and timestamp; never mix store bytes from instance A with free disk from instance B and produce bogus forecasts.

### 10.2. Observations from the Java Driver and Spring Data Neo4j

In Java applications, additionally track:

- Request duration and p95/p99 of critical Cypher queries.
- Mutation/import throughput, updated record counts, and batch commit duration.
- `TransientException` counts, timeouts, and retries by root-cause category.
- Connection pool usage and connection acquisition wait times if supported by driver/instrumentation.
- Replication/ingestion lag between source commits and graph writes in CDC pipelines.

These are **complementary application metrics**, not a replacement for Neo4j or infrastructure disk metrics. Never grant administrative privileges to every application instance just to run `SHOW INDEXES`; use a dedicated least-privilege monitoring account/mechanism.

Example using the Java Driver to read index states under a monitor role:

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Record;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class Neo4jIndexMonitor {
    private final Driver monitoringDriver;

    public Neo4jIndexMonitor(Driver monitoringDriver) {
        this.monitoringDriver = monitoringDriver;
    }

    public List<Record> indexStates() {
        try (Session session = monitoringDriver.session(
                SessionConfig.forDatabase("neo4j"))) {
            return session.run("""
                SHOW INDEXES
                YIELD name, type, state, populationPercent
                RETURN name, type, state, populationPercent
                ORDER BY name
                """).list();
        }
    }
}
~~~

This is a read pattern for modern Java Driver releases. In production, map results to DTOs/metrics containing no sensitive info, specify the target database, grant minimal privileges, verify the `SHOW INDEXES` schema for your version, and never share a single `Session` across threads.

## 11. Alert Thresholds: Early Enough to Act

Thresholds below are **directional guidelines only**; calibrate them to write volume, growth rate, reserve margin, SLA, storage type, and expansion lead time.

| Alert | Illustrative Condition | First Action |
| --- | --- | --- |
| Disk warning | Free space below 25% **and** trending downward. | Identify which volume and whether store/index/log/backup is growing. |
| Headroom forecast | `daysToHeadroom < 7` over a reliable window. | Schedule capacity expansion or throttle growth before an outage. |
| Disk critical | Free space below approved minimum reserve floor. | Activate incident runbook, protect writes and recovery readiness. |
| Index FAILED | Count of `FAILED` indexes > 0. | Identify impacted queries/constraints and gather failure cause. |
| Prolonged POPULATING | Index build duration exceeds baseline for type and data size. | Check progress, disk/CPU/I/O, and population errors. |
| Abnormal tx log growth | Log growth rate exceeds baseline outside approved jobs. | Compare write rate, retention, pruning, and cluster/backup state. |
| Overdue backup | Age of last successful backup breaches RPO/ops policy. | Inspect backup pipeline, disk space, and restore readiness. |
| Collector missing data | Metrics missing for multiple scrape cycles. | Fix monitoring pipeline; never assume the DB is "stable". |

Values like `25%` or `7 days` are **not official defaults or recommendations for every Neo4j system**. 10% free on a 100 TiB volume leaves huge absolute space, whereas 30% free on a 20 GiB volume may still fail a scheduled import. Combine **percentages, absolute bytes, workload peaks, and time-to-threshold**.

### 11.1. Contextual and Noise-Resistant Alerts

A well-designed rule includes:

- Sustained duration above threshold to avoid paging on a single noisy sample.
- Scheduled maintenance/exception windows for index builds or bulk imports, **without ever muting disk-critical alerts**.
- Impact-based severity: a failed index backing a primary search API differs from one serving an optional report.
- Explicit instance/database/volume labels and direct runbook links.
- Escalation if unacknowledged, plus a separate dead-man's-switch alert for broken monitoring pipelines.

## 12. Runbook A — Volume Nearly Out of Space

**Symptoms:** free disk dropping rapidly, failing transactions, stalled indexes, or abnormally slow write throughput.

### 12.1. Confirm and Isolate

1. Identify the exact **affected volume, instance, and database**; verify true available bytes.
2. Compare trends of `storeBytes`, `indexBytes`, `txLogBytes`, and other consumers on the same disk (backups, OS logs, snapshots).
3. Pinpoint when growth started and whether it aligns with imports, migrations, index builds, or unusual load.
4. Check database/cluster state, disk errors, and timestamp of the latest backup.
5. Estimate time to reserve threshold using **recent growth rates**, not just monthly averages.

### 12.2. Safety-First Actions

- If infrastructure permits, **expand the volume/quota** via tested procedures, coordinating storage and database teams.
- Throttle or pause non-essential import/backfill jobs to slow write rates, respecting business ordering and downstream requirements.
- Clean up files **outside Neo4j's data directories** only after confirming ownership and safe deletion policies—such as expired archived logs/backups.
- Verify your latest backup and restore readiness; never gamble on risky changes just to reclaim a few GB.
- On managed services, execute scaling or file support requests via Aura or provider mechanisms.

**Do NOT:** delete store, index, or transaction log files; kill the process abnormally to "free space"; slash retention recklessly without considering recovery/backup/cluster catch-up; or run `DETACH DELETE` on millions of nodes without planning transactions, indexes, and log impact.

### 12.3. When Past the Danger Threshold

If the database starts rejecting writes or the volume is critically full:

1. Declare an incident and shed/throttle write requests at the application tier.
2. Keep database/log files intact and engage operators authorized to manage storage.
3. Ensure disk space needed for recovery/checkpoints is protected per Neo4j guidance.
4. Once headroom is restored, verify the database is online, new transactions commit, no indexes are `FAILED`, and backups/replication are healthy.
5. Conduct root-cause analysis and update forecasts/alerts to prevent recurrence.

Do not declare recovery solely because `df` shows free space again: both the application and Neo4j must be verified for **consistency, read/write health, and backup/cluster progress**.

## 13. Runbook B — Index FAILED or Population Stalled

**Symptoms:** `SHOW INDEXES` reports `FAILED`, `POPULATING` lingers excessively, or queries show unexpected DB Hits/latency spikes after a migration.

1. Record index name, type, label/type, properties, state, and population percentage.
2. Read available error messages and authorized system logs; do not guess the cause from `FAILED` alone.
3. Check **disk space** and I/O during index population; the root cause may be resource exhaustion rather than Cypher.
4. Determine whether the index backs a **constraint** or critical query; run `EXPLAIN`/`PROFILE` on safe read queries.
5. Choose a version-supported remediation: fix underlying data/config issues or rebuild/recreate within a proper change window.
6. Reserve adequate headroom for the new build and monitor the system throughout.
7. Once the index is `ONLINE`, verify business queries, uniqueness/constraints, and latency on representative data.

**Do not** drop an index without verifying whether it backs a uniqueness constraint. **Do not** repeatedly recreate it while the volume lacks space or the root failure remains unresolved.

## 14. Runbook C — Abnormal Transaction Log Growth

**Symptoms:** transaction log footprint climbs steadily, rotation accelerates beyond normal, or logs consume most of the volume.

### 14.1. Separating Planned Growth from Abnormal Growth

| Observation | Initial Hypothesis | Verification |
| --- | --- | --- |
| Logs grow during scheduled ingestion hours | Planned bulk import/backfill. | Cross-check job schedule, write rate, and ingested volume. |
| Logs spike after an app release | Retry/update loops, write amplification. | Compare deployment timing, error rates, and transaction counts. |
| Logs remain large despite low current writes | Long retention, deferred pruning, or leftover logs from earlier bursts. | Inspect settings, rotation/pruning timestamps, and recovery/backup state. |
| Logs grow alongside replica/catch-up lag | Lagging cluster member may require logs for catch-up per deployment rules. | Check cluster health/catch-up and ops guidance for your version. |
| Logs grow while DB slows or times out | Disk I/O saturation, oversized transactions, or resource contention. | Monitor disk latency, transaction duration, and logging overhead. |

### 14.2. Remediation Sequence

1. Identify the transaction log volume path and actual growth rate, avoiding confusion with `query.log`.
2. Record database state, version, and active rotation/retention settings.
3. Check recent imports/replays/deployments, long-running transactions, and unintended write bursts.
4. Check backup/recovery/cluster catch-up states and any conditions preventing pruning from releasing files.
5. Secure **safe disk headroom first**, by expanding storage or throttling writes if necessary.
6. Adjust retention only after evaluating RPO/RTO, backups, and cluster impact, using supported configuration mechanisms.
7. Observe log stabilization across an appropriate cycle and confirm restore/catch-up remain intact.

**Never delete transaction log files manually**, even files with old timestamps; never use OS file operations to "repair" a database log chain. If retention is properly configured yet logs still aren't pruned, investigate why rather than forcing deletion.

## 15. Pairing Monitoring with Backups and Recovery Strategy

Sufficient disk space today does not guarantee recoverability after an outage. Monitor:

| Factor | Question |
| --- | --- |
| Backup frequency & RPO | If the database is lost right now, what is the maximum data loss? |
| Restore speed & RTO | Does a full restore test meet committed recovery time targets? |
| Backup footprint | Do backups share a volume with store/logs and risk filling the disk? |
| Transaction log retention | Is enough history kept for the designed recovery/catch-up procedures? |
| Cluster lag | Can a disrupted member catch up within retained logs and available resources? |
| Post-restore index rebuilds | Are index rebuild space and duration accounted for in recovery plans? |

Depending on deployment model, online backups, full/incremental backups, and point-in-time recovery have specific prerequisites and tools. **Never promise point-in-time recovery merely because transaction log files exist.** Restore capability must be backed by version/edition documentation and **regular restore drills with consistency checks**.

### 15.1. Deleting Data Does Not Immediately Shrink the Store

Neo4j can reuse freed internal storage slots after node/relationship deletion rather than immediately shrinking physical store files. Therefore:

- Dropping logical node counts **does not guarantee** store `du` drops immediately.
- Deleting millions of nodes also generates transactions, logs, and index updates—which can **temporarily increase disk usage**.
- Reclaiming physical file size may require supported compaction/export/import/rebuild workflows depending on version and goals.
- Never kick off massive "data cleanup" deletes on a nearly full disk without estimating peak transaction log and resource requirements.

Monitoring must distinguish **reusable internal store space** from **filesystem free bytes**. The two are not interchangeable.

## 16. Integrated Analysis Scenario

Suppose on Monday a system shows:

| Metric | Illustrative Value |
| --- | ---: |
| Data store | 280 GiB |
| Index size | 55 GiB |
| Transaction logs | 22 GiB |
| Data volume free space | 160 GiB |

On Tuesday, after an import:

| Metric | Illustrative Value |
| --- | ---: |
| Data store | 350 GiB |
| Index size | 76 GiB |
| Transaction logs | 96 GiB |
| Data volume free space | 15 GiB |

These are **hypothetical numbers** for analytical practice. Beyond the steep drop in free space, transaction logs jumped sharply and indexes expanded due to the import. You cannot conclude "transaction log retention bug" from two snapshots alone, because log growth may match the legitimate import volume.

Reasonable investigation sequence:

1. Verify metrics share the same measurement source, instance, and volume, with no store/index double-counting.
2. Check whether the import is still running, inspect write rates, and project time to exhaustion.
3. Check the status of newly created/populating indexes.
4. Check rotation/retention policies, backup status, and replication/catch-up if clustered.
5. With only 15 GiB free, consider invoking the disk capacity runbook before running any further disk-heavy tasks like index rebuilds or bulk deletes.
6. Once stabilized, inspect finer-grained time series to separate transient import spikes from long-term trends.

A valid operational finding pairs **evidence with impact**: which index, which volume, write volume from which job, and whether recovery guarantees remain compliant.

## 17. Testing Your Monitoring Setup

You do not need to fill a production disk or delete live logs to verify dashboards work. Test in an isolated environment using synthetic data, simulated metric records, and safe schema changes.

| ID | Scenario | Expected Behavior |
| --- | --- | --- |
| M01 | Database online while free space drops below threshold. | Storage alert fires even though `SHOW DATABASES` reports `ONLINE`. |
| M02 | An index is `POPULATING`. | Dashboard shows state/percentage and does not mark it ready. |
| M03 | Simulated `FAILED` index metric in collector/test. | Alert includes index name, database, instance, and runbook. |
| M04 | Test bulk import drives transaction log growth. | Log growth is visible, tied to the job, and not misclassified as an error if planned. |
| M05 | Metric collector is stopped. | Missing-data alert fires; charts do not silently treat stale samples as current. |
| M06 | Test backup job fails. | Backup age alert fires and flags RPO risk. |
| M07 | Data store grows while node count barely changes. | Investigate properties/relationships/indexes rather than relying on node count alone. |
| M08 | Test data deleted yet store files do not shrink. | Dashboard separates logical counts from physical bytes. |
| M09 | Run indexed vs. unindexed queries on fixtures. | `EXPLAIN`/`PROFILE` distinguishes plans; readiness is not judged solely by `ONLINE` index state. |
| M10 | Simulate one cluster instance losing scrapes. | Aggregation neither corrupts cluster totals nor hides that instance's free space. |
| M11 | High 15-minute growth rate vs. flat 7-day baseline. | Burst alerts and capacity forecasts remain distinct, avoiding false long-term exhaustion alarms from brief spikes. |
| M12 | Sensitive parameters placed in test fixtures/logs. | Monitoring keeps sensitive values off dashboards and alerts. |

### 17.1. Conceptual Threshold Evaluation Pseudocode

This is **pseudocode**, not Neo4j metric names or APIs:

~~~text
if no_recent_samples(instance, volume):
    alert("MONITORING_DATA_MISSING")

if free_bytes < reserved_bytes:
    alert("DISK_CRITICAL")

growth = moving_growth_bytes_per_day(used_bytes, window="7d")
if growth > 0:
    days_to_reserve = max(0, free_bytes - reserved_bytes) / growth
    if days_to_reserve < planning_days:
        alert("DISK_CAPACITY_PLANNING")

if any(index.state == "FAILED"):
    alert("NEO4J_INDEX_FAILED")

if tx_log_growth_unexpected and not approved_bulk_job:
    alert("NEO4J_TX_LOG_GROWTH")
~~~

Every alert branch must use metrics from the **same volume, sufficiently fresh, with consistent units**. `approved_bulk_job` provides classification context only—it must never suppress disk-exhaustion or database-unavailable alerts.

## 18. Common Mistakes

| Misconception | Reality to Remember |
| --- | --- |
| "If node count isn't growing, database size must be flat." | Large properties, relationships, indexes, and logs can still grow. |
| "If an index is ONLINE, queries are definitely fast." | Queries may not use the index or may spend most cost in traversal/aggregation. |
| "Transaction logs are the same as query logs." | Transaction logs serve durability/recovery; query logs observe executed statements. |
| "Once logs rotate, disk bytes must drop immediately." | Rotation splits files; pruning still depends on retention and safety constraints. |
| "Deleting old tx log files fixes a full disk." | Can destroy recovery, backups, or catch-up. Never touch files manually. |
| "Deleting nodes increases `df` free space proportionally." | Store reuses internal slots without shrinking files; deletes also generate logs. |
| "Adding store bytes and index bytes is always right." | Some store metrics already include indexes; verify metric definitions. |
| "Use an 80% disk threshold for every system." | Must factor in absolute headroom, growth rate, volume size, and peak workloads. |
| "Today's dashboard snapshot suffices for a 6-month forecast." | Need sufficient history, seasonality, and planned import/index schedules. |
| "You can SSH into Aura to check the data directory." | Managed services restrict OS access; use supported metrics/consoles. |
| "A successful backup guarantees a working restore." | Regularly test restores and data consistency. |
| "No data points on a chart means the metric is 0." | The exporter/collector may be disconnected or lack permissions. |
| "A 3-replica cluster means multiplying by 3 for logical database size." | Separate logical dataset size from physical per-replica footprint. |

## 19. Practice Exercises

**Exercise 1 — Resource classification.** A Neo4j database reports 90 GiB data store, 28 GiB indexes, and 12 GiB transaction logs across different telemetry sources. Explain when summing them to 130 GiB is valid and when it double-counts. Add how to measure filesystem free bytes.

**Exercise 2 — Index states.** On a practice database, create a uniqueness constraint on `MonDemoCustomer(tenantId, customerId)`, run `SHOW INDEXES`, identify the backing index, and use `EXPLAIN`/`PROFILE` to verify a lookup filtering by both keys. Explain why you should not drop that index solely due to low read counts.

**Exercise 3 — Capacity forecasting.** A volume has 200 GiB free, policy requires keeping at least 50 GiB reserve, and average net growth is 12 GiB/day. Compute days to reserve using Section 9 formulas. Then simulate an index rebuild requiring 80 GiB temporary space in one day and explain why average-based forecasts can mislead.

**Exercise 4 — Post-import log growth.** An ingestion job causes transaction logs to grow by 40 GiB over three hours. Write an investigation checklist distinguishing expected growth, transaction retry loops, deferred pruning, and insufficient headroom; state which action is **forbidden**.

**Exercise 5 — Cluster alerting.** A three-instance cluster has two instances at 35% free disk while the third is down to 7%. Design dashboards and alerts so cluster averages never mask single-member disk risk.

**Exercise 6 — Backup catch-up.** Suppose the latest backup breached RPO and someone proposes cutting transaction log retention from 7 days to 1 day. Which prerequisites regarding backups, restores, catch-up, and write volume must be verified before changing it?

**Exercise 7 — Logical vs. physical storage.** Deleting 100,000 nodes in test reduces node count while filesystem free bytes stay nearly flat. Explain the difference between reusable internal space and physical store file shrinking, and why bulk deletes on a nearly full disk can backfire.

**Exercise 8 — Missing metric samples.** An exporter degrades to sending samples every ten minutes instead of every 15 seconds, creating misleading flat segments on the transaction log chart. Describe how to detect staleness, preserve an "insufficient data" state, and restore the monitoring pipeline without backfilling zeros.

## 20. Operations Checklist

1. **Know your exact scope:** database, instance, edition, version, cluster/replicas, volumes, quotas, and environment.
2. **Separate capacities:** store, indexes, transaction logs, backups, server logs; avoid double-counting.
3. **Maintain time series:** used/free bytes, multi-window growth rates, forecasts to reserve thresholds.
4. **Monitor indexes:** state, population progress, errors, workload usage, and query plans; never drop constraint-owned indexes carelessly.
5. **Monitor transaction logs:** rotation, retention, write rate, pruning, backups, and cluster catch-up per deployment support.
6. **Maintain headroom:** budget for imports, index builds, recovery, peak transaction logs, and co-located files.
7. **Layer alerts:** byte/% thresholds, time-to-threshold, index failures, overdue backups, and collector outages.
8. **Keep runbooks safe:** never delete store/index/transaction log files via OS to "rescue" a running database.
9. **Test recoverability:** validate successful backups with restore drills and cover cluster/node failure modes.
10. **Connect performance with capacity:** analyze `PROFILE`, page cache, I/O, and transaction durations alongside storage metrics.
11. **Protect telemetry:** least-privilege monitoring accounts, PII-free logs/traces, and missing-data alerts on monitoring pipelines.
12. **Re-verify after changes:** confirm indexes are `ONLINE`, log growth returns to baseline, disk headroom is sufficient, and business queries meet SLOs.

**Conclusion:** Monitoring Neo4j capacity is never about watching a single "database size" number. You must combine **data store, indexes, transaction logs, disks/volumes, write rates, backups, and cluster state** to understand real demand. `SHOW INDEXES` catches unready indexes; `EXPLAIN`/`PROFILE` validates index effectiveness; transaction log rotation/retention policies must preserve recovery requirements rather than relying on manual file deletion. Good monitoring forecasts risk **before space runs out**, alerts on missing telemetry, and guides operators to safe runbooks.
