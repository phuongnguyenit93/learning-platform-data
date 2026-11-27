# sstabledump, sstableverify, and Tool-Specific Usage Conditions

## Objectives and Scope

Apache Cassandra writes data into a **memtable** and flushes it into **immutable SSTables** on disk. When reading or repairing data, Cassandra must evaluate multiple row/column versions, timestamps, TTLs, and tombstones across SSTables. When the system exhibits anomalous data, SSTable read errors, or suspected file corruption, operators must distinguish two questions:

1. **What is inside a specific SSTable?** — use `sstabledump` to inspect data encoded in the file in human-readable form.
2. **Do a table's SSTables pass integrity validation?** — use `sstableverify` following the supported **offline** verification procedure.

Both tools belong to the **local SSTable toolset**, distinct from `cqlsh` and `nodetool repair`. They **do not** synchronize replicas automatically, prove all business data is complete, or repair files. In particular, running the wrong tool while Cassandra is compacting or replacing files can yield misleading conclusions or operational risk.

This lesson belongs to the **Operational Tools** chapter in the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module. It connects wide-column architecture, partition-key and query-driven table design, CQL write/read paths, replication/consistency, compaction, repair, failure handling, and how Java applications observe expected data.

After this lesson, you will be able to:

- Identify `Data.db`, companion SSTable components, and the limits of an SSTable snapshot compared to CQL state.
- Choose `sstabledump` when reading one SSTable's contents and `sstableverify` when validating a table's SSTables.
- Distinguish **reading a snapshot while Cassandra is running** from **offline verification requiring Cassandra stopped on the target node**.
- Plan access permissions, version compatibility, disk/I/O, backups, remaining live replicas, and impact scope.
- Practice creating CQL data, flushing/snapshotting, dumping SSTables, and interpreting timestamps/tombstones without mistaking "physical values" for "live rows".
- Handle suspected corruption via evidence preservation, independent verification, restore/replace, and controlled repair.

> **Safety principle:** all illustrated commands are for labs or approved maintenance. Never stop a production node, delete/move/modify SSTables, run `scrub`, or force compaction simply because dump output looks confusing. Exact instructions and CLI flags must be verified against the **exact Cassandra version and distribution** in use.

## 1. An SSTable Consists of Multiple Components

An SSTable is a set of files on disk typically sharing a common **descriptor** and component suffixes. A familiar form is `<descriptor>-Data.db`. Depending on version/format, alongside the data component sit index, statistics, Bloom filter, compression, and table-of-contents components.

~~~text
/var/lib/cassandra/data/
  sstable_lab/
    events_by_run-<table_uuid>/
      <descriptor>-Data.db
      <descriptor>-Index.db
      <descriptor>-Summary.db
      <descriptor>-Filter.db
      <descriptor>-Statistics.db
      <descriptor>-TOC.txt
      ... components depending on version/format ...
      snapshots/
        inspect-01/
          <descriptor>-Data.db
          <descriptor>-Index.db
          ...
~~~

This path only **illustrates a typical Linux installation**; Cassandra can use custom data directories, multiple data volumes, or different layouts/formats. `<table_uuid>` is the table's physical directory ID, **not a partition key**. Never guess directory names solely from `keyspace.table` if a table was ever dropped and recreated.

| Component | Typical Role | Is It the Sole Source of Truth? |
| --- | --- | --- |
| `Data.db` | Serialized data: partitions, rows, cells, tombstones, and attached metadata | No; mutations may also live in memtables and other SSTables |
| `Index.db` | Helps locate partitions/offsets within data | Does not prove logical data across all replicas |
| `Summary.db` and `Filter.db` | Helps locate/skip irrelevant SSTables during reads | Can vary across formats/versions |
| `Statistics.db` | SSTable metadata/statistics, repair/compaction state | Not full CQL contents |
| `CompressionInfo.db` and others | Describes layout/compression/checksums per format | Not every component exists in every setup |

**`sstabledump` does not read the entire cluster directly.** It decodes a single SSTable specified by file path, does not automatically open all SSTables of a table, and does not read uncommitted in-memory memtable changes. One partition can span multiple SSTables and multiple nodes/replicas; dumping one file is a **physical slice**, not the final `SELECT` result.

~~~mermaid
flowchart LR
    W["CQL Mutation"] --> M["Commit log + memtable"]
    M -->|Flush| A["SSTable A"]
    M -->|Later flush| B["SSTable B"]
    A --> C["Compaction"]
    B --> C
    C --> N["New SSTable"]
    A -. "Dump one file" .-> D["sstabledump"]
    N -. "Dump one file" .-> D
    A -. "Inspect on disk" .-> V["sstableverify offline"]
    B -.-> V
    N -.-> V
~~~

Compaction creates new SSTables and removes input files once safe. Therefore, **reading live file paths during compaction** risks files vanishing or changing state mid-read. Using a **named snapshot** keeps the SSTable components referenced by that snapshot stable during analysis.

## 2. Choosing the Tool by Diagnostic Question

| Need | Preferred Tool | Key Preconditions | Conclusion Limits |
| --- | --- | --- | --- |
| Inspect cells, timestamps, deletion info, TTL in **one SSTable** | `sstabledump` | Valid `Data.db` path, format-compatible tool | Not the post-reconciliation CQL result across SSTables/replicas |
| Inspect an SSTable while the node is serving | `sstabledump` **on a stable snapshot/copy** | Snapshot created safely; permissions/paths/I/O controlled | Snapshot only reflects SSTables in scope at capture time |
| Suspect SSTables of **a table on one node** are corrupt | `sstableverify` | **Offline** workflow: stop Cassandra on target node, have backups and resource budget | PASS does not prove other replicas match; FAIL does not dictate the fix automatically |
| View SSTable metadata | `sstablemetadata` (if provided by version) | Valid file, compatible tool/version | Metadata does not replace cell contents or full validation |
| Check SSTables while Cassandra stays running | `nodetool verify` per version | Evaluate load impact and version-specific flags | Differs from offline `sstableverify`; does not replace repair |
| Sync diverged replicas | Planned `nodetool repair` | RF/DC, token ranges, I/O/network load, tombstones, replica health | Not a tool to arbitrarily fix corrupt SSTable bytes |
| Fix/rebuild damaged SSTables | **Approved** restore/replace/scrub procedure | Assess data loss and integrity first | `scrub` can alter/discard data; not a read-only operation |

**Distinguish impact levels:** `sstabledump` is a **viewing** tool; `sstableverify` is a **checking** tool; `repair` is a replica **synchronization** task; `scrub` is a risky **SSTable-mutating/repairing** operation. Tools are never interchangeable just because they share "SSTable" in the name.

### A Brief Decision Tree

~~~mermaid
flowchart TD
    A["Abnormal CQL results or storage errors seen"] --> B{"What do you want to know?"}
    B -->|What does a file contain| C["Create stable snapshot\nRun sstabledump"]
    B -->|Are files valid| D["Evaluate online nodetool verify\nor offline sstableverify"]
    B -->|Do replicas differ| E["Check RF/CL, hints\nand anti-entropy repair"]
    B -->|Missing business data| F["Reconcile manifest/outbox/backup"]
    C --> G["Read output + CQL/logs"]
    D --> G
    E --> G
    F --> G
    G --> H{"Evidence of corruption or data loss?"}
    H -->|Yes| I["Stop ad-hoc changes\nPlan restore/replace"]
    H -->|Unclear| J["Gather bounded extra evidence"]
~~~

## 3. Conditions for Using `sstabledump`

`sstabledump` takes **the path to an SSTable Data component** and prints its decoded contents, typically as JSON or an output variant controlled by flags/version. Useful when investigating:

- Whether an old or new timestamp was persisted into a given SSTable.
- How row/column/partition tombstones appear inside the file.
- Whether partitions or clustering rows show anomalies, expired TTLs, or records no longer visible to `SELECT`.
- Findings requiring comparison with metadata, mutation logs, CQL, and compaction/repair history.

### 3.1. Conditions That Must Be Met

1. **Know the exact node, keyspace/table, and `Data.db`:** the path belongs to the target table's SSTable. With RF > 1, one node's output does not represent all replicas.
2. **Use a stable file:** prefer a locked snapshot/copy; never chase live paths actively rotated by compaction.
3. **Match version and format:** run the tool packaged with the SSTable-compatible Cassandra release/distribution; never feed a newer format to an older binary.
4. **Sufficient read permissions and resources:** the tool can read many bytes and consume CPU/RAM/I/O; large files generate huge JSON outputs.
5. **Control sensitive data:** dumps can expose plaintext column values; restrict access, logs, output files, and retention.
6. **Understand data scope:** SSTables exclude unflushed memtable mutations, and one record can span multiple SSTables with different timestamps/tombstones.

**Must the node be stopped?** When reading a **stable snapshot**, you can inspect SSTables while Cassandra keeps serving on that node if operational policy and I/O headroom permit. Avoid reading or touching live files that could be replaced mid-flight; to diagnose table-wide corruption, use an appropriate verify workflow instead.

### 3.2. Check Syntax for Your Exact Version

~~~bash
# Run on a host with compatible Cassandra tools installed.
sstabledump --help

# Input is typically the full path to the Data.db component.
sstabledump "/path/to/snapshot/<descriptor>-Data.db"
~~~

Some versions support key filtering or output formatting flags; **flag names and JSON layouts are not guaranteed identical across Cassandra 3.x, 4.x, and 5.x**. Before passing flags, check `sstabledump --help` on the target host and verify exact partition key encoding.

**Never paste raw output into public issue trackers or chats**: `payload` fields, customer identifiers, access tokens, or business JSON may appear in dumps even when CQL hides columns at the application layer.

## 4. Conditions for Using `sstableverify`

`sstableverify` checks SSTables for **a local keyspace/table on one node**. It uses Cassandra libraries/metadata to read and validate SSTables found for that table; verification levels or flags ("quick/extended", if present) depend on version.

The paramount operational condition is **offline execution**: schedule **stopping the Cassandra process on the target node** so no flush, compaction, streaming, or background task modifies the SSTable set while verification runs. Never run `sstableverify` against a data directory actively used by a running Cassandra node without a verified compatible procedure.

### 4.1. Checklist Before Stopping a Node

- **RF/CL status:** after taking the node out of service, will remaining replicas satisfy live workloads? With RF=3, `LOCAL_QUORUM` needs two local replicas; if another node is already down, stopping one more breaks quorum.
- **Operational headroom:** sufficient free disk, I/O, and CPU on remaining nodes to absorb shifted load; avoid stopping multiple nodes concurrently.
- **Trusted backup/snapshot:** a restore/replace path exists if corruption is found; snapshotting an already corrupt file does not create a healthy copy.
- **Rollback criteria and owner:** maintenance window, monitoring, restart plan, config/version docs, and escalation path.
- **No concurrent topology changes:** bootstrap, decommission, remove, streaming, heavy repair, or unusual compaction increases risk and clouds diagnosis.
- **Version and paths:** matching tool version, Cassandra home/config, and exact keyspace/table on the node.
- **Permissions and logs:** the tool needs read access to the data dir; save exit code, stdout/stderr, version, timestamps, and node name.

### 4.2. Illustrative Offline Workflow

~~~bash
# EXAMPLE ONLY FOR LABS / APPROVED MAINTENANCE.
# 1. On a healthy node, capture baseline:
nodetool status

# 2. Stop the Cassandra service on the target node via service manager.
# The line below illustrates Linux with systemd only:
sudo systemctl stop cassandra

# 3. Confirm the process has stopped completely, with no writes/compaction active.
# Exact check depends on OS, container runtime, or distribution.
sudo systemctl is-active cassandra

# 4. Run the tool from the matching package while the node is offline:
sstableverify sstable_lab events_by_run

# 5. Capture exit code/logs and evaluate results before a controlled restart.
# Do not restart automatically if suspected corruption requires preserving evidence.
~~~

**Before step 2, production operations must follow an approved drain/shutdown procedure**, verify the process genuinely stopped, and assess the impact of losing one node in the DC. `nodetool drain` prepares for controlled shutdown, not corruption verification; draining can alter flush state, so record exact snapshot/manifest timestamps.

`sstableverify sstable_lab events_by_run` is a **common syntax pattern**. Some distributions/versions have different flags or data-directory lookup rules; check `sstableverify --help` before running. Do not assume it automatically checks all keyspaces/tables across the cluster.

### 4.3. What Do PASS and FAIL Mean?

| Result | What You Can Conclude | What You Cannot Conclude |
| --- | --- | --- |
| Verify completes cleanly | The SSTables actually checked passed the criteria enabled by version/flags | All replicas match, all business events exist, or data cannot be lost later |
| Verify reports checksum/index/decode/error | Anomaly detected warranting investigation in the indicated file/component/scope | It can be safely fixed by deleting a file manually |
| Verify aborts due to version/schema/permission | Tool/process did not finish; result is **UNKNOWN** | The file is definitely corrupt |
| Verify takes long / heavy I/O | Heavy read/decode workload may occur | Faster completion means more thorough checking |

**Verify does not fix data.** If corruption is detected, the next steps are **preserving evidence, isolating scope, identifying trusted copies, and selecting a recovery path**; never treat FAIL as an instruction to immediately run `scrub`.

## 5. CQL Lab: Creating Data, Tombstones, and Snapshots

### 5.1. Lab Prerequisites

Prepare Cassandra with DC named `datacenter1`, ideally three nodes/RF=3; if single-node, adjust keyspace replication to reflect actual topology rather than forcing RF=3. Only run the lab where flush/snapshot operations are allowed with ample disk.

~~~bash
nodetool status
~~~

Verify the DC name from `nodetool status` and connected node info:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

Create keyspace and table with partition key `run_id` and clustering key `item_id`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS sstable_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS sstable_lab.events_by_run (
    run_id text,
    item_id int,
    value text,
    updated_at timestamp,
    PRIMARY KEY ((run_id), item_id)
) WITH gc_grace_seconds = 864000;
~~~

`run_id` isolates each test run in its own partition; `item_id` identifies a row within the partition. `updated_at` is purely a **business column**, **not Cassandra's internal mutation timestamp** used for conflict resolution. When analyzing write/delete timestamps, inspect the internal metadata in the dump.

If `IF NOT EXISTS` encounters a pre-existing keyspace/table, old schemas **do not update automatically**. Check replication/grace before interpreting results:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'sstable_lab';

SELECT table_name, gc_grace_seconds
FROM system_schema.tables
WHERE keyspace_name = 'sstable_lab'
  AND table_name = 'events_by_run';
~~~

### 5.2. Writing and Updating a Key

~~~sql
INSERT INTO sstable_lab.events_by_run
    (run_id, item_id, value, updated_at)
VALUES ('dump-demo-01', 1, 'DRAFT',
        '2026-11-21T09:00:00Z');

INSERT INTO sstable_lab.events_by_run
    (run_id, item_id, value, updated_at)
VALUES ('dump-demo-01', 2, 'CONTROL',
        '2026-11-21T09:00:00Z');
~~~

In the **lab**, you can create SSTable boundaries by flushing:

~~~bash
# Intentional flush to obtain separate SSTables cleanly; never use as
# an unconditional routine task in production.
nodetool flush sstable_lab events_by_run
~~~

Continue:

~~~sql
UPDATE sstable_lab.events_by_run
SET value = 'PAID',
    updated_at = '2026-11-21T09:05:00Z'
WHERE run_id = 'dump-demo-01' AND item_id = 1;

DELETE FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01' AND item_id = 2;
~~~

Flush again in the lab:

~~~bash
nodetool flush sstable_lab events_by_run
~~~

This creates an **opportunity** to have multiple SSTables holding different states. It **does not guarantee** the two SSTables stay separate forever: background compaction may merge them. When exact point-in-time evidence is needed, take before/after snapshots per lab procedure instead of guessing from current file counts.

Read the logical result via CQL:

~~~sql
SELECT item_id, value, updated_at
FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01';
~~~

If all mutations succeeded without concurrent writes, expect row `item_id=1` with `PAID` and **no row** for `item_id=2`. Yet the older SSTable can still hold `DRAFT` or `CONTROL`, while the newer SSTable carries the newer timestamp or tombstone. **Seeing an old value in a dump does not prove Cassandra returned stale data to clients.**

### 5.3. Creating a Safe Snapshot to Dump

~~~bash
# Snapshot only the lab table with an explicit tag.
nodetool snapshot -t inspect-01 -cf events_by_run sstable_lab
~~~

This illustrates common syntax; `-cf`/`--table`, keyspace argument order, and permissions can vary by version, so run `nodetool help snapshot` on your cluster first. Snapshots typically reference on-disk SSTables via hard links or filesystem equivalents; they are **not independent restore-tested backups**.

Locate the **exact table directory** via configured data directories and `events_by_run-<table_uuid>`, then find `snapshots/inspect-01`. Never inspect a snapshot directory from an earlier test sharing the same table name.

**Memtable note:** snapshots capture SSTables existing at capture time per version/flag behavior; if unflushed mutations exist and the snapshot did not flush them, dump contents may exclude recent mutations. In this lab, two `nodetool flush` calls separated the test milestones; never assume every production snapshot automatically includes all in-memory mutations.

### 5.4. Running sstabledump on the Snapshot File

~~~bash
# Replace all placeholders with verified actual paths.
sstabledump \
  "/var/lib/cassandra/data/sstable_lab/events_by_run-<table_uuid>/snapshots/inspect-01/<descriptor>-Data.db"
~~~

A single snapshot can contain **multiple descriptors**; to inspect all relevant SSTables thoroughly, list and dump every file in scope rather than checking only the first file and claiming the whole table was inspected.

Output can be lengthy: use organization-approved log storage/redaction or key-filtering flags **confirmed in `sstabledump --help`** for your version. Do not assume CQL-like `WHERE` parameters exist. Always strip payloads/PII before sharing results.

## 6. Interpreting Dumps Accurately: Timestamps, Tombstones, and Stale Values

### 6.1. Expected Content Structure

JSON produced by `sstabledump` typically describes **partitions**, **rows**, **clustering**, **cells**, and liveness/deletion metadata. Below is a **conceptual illustration**, not exact JSON schema for every release:

~~~text
Older SSTable:
  partition key = dump-demo-01
  row item_id=1: value="DRAFT", timestamp=t1
  row item_id=2: value="CONTROL", timestamp=t1

Newer SSTable:
  partition key = dump-demo-01
  row item_id=1: value="PAID", timestamp=t2 > t1
  row item_id=2: tombstone, deletion timestamp=t3 > t1

SELECT result after reconciliation:
  item_id=1 -> PAID
  item_id=2 -> no row returned
~~~

**Values in an older SSTable are not "zombie data" by definition.** Cassandra stores older versions in immutable SSTables and reconciles them on read, while compaction purges them only when eligible. Zombie data happens when old records **can genuinely reappear** after tombstones are purged before a replica that missed `DELETE` is synchronized—not simply because `sstabledump` prints the word `CONTROL`.

### 6.2. Distinguishing Three Timestamps

| Information | Meaning | What Not to Infer |
| --- | --- | --- |
| `updated_at` in CQL | Business column sent by application | Not automatically equal to internal write timestamp |
| **Write timestamp / deletion timestamp** | Used to reconcile mutations/cells/tombstones per Cassandra rules | Does not itself prove the client received an ACK |
| **Local deletion time / TTL expiration** | Participates in expiration/reclamation eligibility | Does not mean data is physically deleted the instant it expires |

Cassandra works with microsecond-resolution timestamps; dump representation varies by flag/version. When comparing values, explicitly record **units**, timezone, timestamp source, and whether client-side timestamps were used. Avoid directly comparing a microsecond epoch with a CQL date-time column without converting.

### 6.3. Reading a Dump Cannot Replace SELECT at Desired CL

`sstabledump` shows **one SSTable on one node**. By contrast, a `SELECT` query can:

1. Be sent by the coordinator to one or more replicas per CL.
2. Read data from memtables **and** multiple SSTables.
3. Reconcile timestamps, tombstones, TTLs, and relevant cells.
4. Return logical results after projection and partition/clustering range filtering.

With RF=3 and `LOCAL_QUORUM`, clients require two local replicas to respond; dumping one replica cannot verify query consistency, the second replica's state, or read-repair outcomes. Concluding replica divergence requires cross-checking tracing/repair/metrics and scoped CQL results.

## 7. Practicing Offline sstableverify on the Lab Table

### 7.1. Preparing the Scenario

In an RF=3 lab, choose one specific node to check, e.g., `cass-3`. Before stopping it, record:

~~~bash
nodetool status
nodetool tablestats sstable_lab.events_by_run
nodetool compactionstats
~~~

Confirm **the remaining two replicas for relevant partitions are healthy** if test apps require `LOCAL_QUORUM`. Never stop two nodes simultaneously in a three-node/RF3 cluster. In a single-node lab, you cannot stop the node and expect CQL to stay available; that reflects topology semantics, not a verify bug.

### 7.2. Stopping and Running the Tool

~~~bash
# Run only inside the lab on the chosen node.
# Actual stop command depends on systemd, Docker, Kubernetes, or supervisor.
sudo systemctl stop cassandra

# Confirm the process exited; do not rely solely on DN status.
sudo systemctl is-active cassandra

# Tool package must match the on-disk SSTables/metadata.
sstableverify sstable_lab events_by_run
~~~

In containers, stop the service in a way matching the image/runtime; **never run `systemctl` blindly inside an image without systemd**. Since verify can read many SSTables and run deeper checks depending on flags, record duration, I/O, exit code, and error messages.

### 7.3. After Verification

If PASS and no other risk signals appear, restart per environment runbook, watch the node return to `UN`, check hints/repair, and read markers via CQL. If FAIL or the tool cannot read a file, **do not automatically restart/repair without assessing the error type and integrity of surviving replicas**; preserve evidence and plan restore/replace.

Example post-restart checks on a live node:

~~~bash
nodetool status
nodetool netstats
nodetool compactionstats
~~~

Re-read logical data:

~~~sql
SELECT item_id, value
FROM sstable_lab.events_by_run
WHERE run_id = 'dump-demo-01';
~~~

**Accurate conclusion:** verify evaluates integrity of checked SSTables on **one node**, CQL returns results at **a specific CL and instant**, and repair checks/synchronizes **ranges across replicas**. These three pieces of evidence complement one another; none alone proves the entire system suffered zero data loss.

## 8. Comparison with nodetool verify, scrub, and repair

| Tool | Online/Offline | Intentionally Modifies Data? | When to Consider |
| --- | --- | --- | --- |
| `sstabledump` | Reads snapshot while node is online; prefer stable copy | No | Inspecting one SSTable, timestamps, tombstones, physical values |
| `sstableverify` | **Offline** per safety procedure | No | Suspected corrupt table SSTables on a node; controlled local validation needed |
| `nodetool verify` | Runs against live Cassandra node | Not a data-recovery command | Validating SSTables online within supported capabilities/flags |
| `nodetool scrub` / `sstablescrub` | Tool/version-dependent, offline conditions | **Can alter data/SSTables** | Only after assessing corruption, backups, replicas, and data-loss risk |
| `nodetool repair` | Coordinates nodes/replicas per scope | **Streams/fixes replica differences** | Diverged replicas or scheduled anti-entropy repair |
| `nodetool snapshot` | Typically run while node is online | Creates data-referencing snapshot | Freezing SSTables for inspection/backup per procedure |

**Why not use scrub as an "advanced verify"?** Scrub can discard corrupted chunks or rewrite storage files; if other replicas lack matching data, the loss can be irreversible. On real failures, evaluate **source data trustworthiness**, not merely turning a tool green.

**Why does repair not replace verify?** Repair compares and exchanges data across replicas. It does not certify on-disk file components pass all verify checks, and can fail or propagate anomalies when source files are corrupt. Conversely, verify PASS on every node does not prove replicas hold **the same mutation versions**.

## 9. Diagnostic Workflow When Suspecting SSTable Corruption

A realistic incident: a Java app occasionally sees read failures querying partition `customer-X`, and one node's logs mention checksum/SSTable read errors. Never immediately delete the file named in logs.

### Step 1 — Verify Symptoms

- Record **request ID**, query shape, anonymized partition key, CL, error timestamp, coordinator/node, and driver message.
- Check node status, disk errors, filesystem/I/O, CPU, and active compaction/repair.
- Classify errors: `ReadTimeout`, `ReadFailure`, `Unavailable`, and app exceptions are distinct; only **evidence in files/logs** justifies suspecting corruption.

### Step 2 — Isolate the SSTable and Preserve Evidence

- Record keyspace/table, node, reported SSTable descriptor/files, Cassandra version, data path, and timestamp.
- Evaluate stable snapshots/copies; if the data file itself is suspected corrupt, hard-linked snapshots **may point to the exact same corrupt bytes**. Rely on independent backups/replicas for recovery.
- Prevent logs and dumps containing sensitive data from leaking outside authorized scope.

### Step 3 — Pick Tools with Appropriate Risk

- Need to inspect data, timestamps/tombstones: `sstabledump` on a stable snapshot, recognizing the tool **may fail to decode a corrupt file**.
- Need to check files while the node remains online: evaluate `nodetool verify` considering resource cost on your version.
- Need deeper offline validation: schedule downtime, verify RF/CL and restore sources, then run version-accurate `sstableverify`.

### Step 4 — Interpret Without Rushing to Modify

| Observed Result | Sound Interpretation | Next Action |
| --- | --- | --- |
| Dump decodes contents | One file is decodable; valuable for inspecting timestamps/tombstones | Cross-check CQL and other SSTables; do not declare the whole table healthy |
| Dump fails to decode | Could be version/path/component mismatch or file corruption | Check compatibility and logs; do not delete the file |
| Offline verify FAIL | Evidence warranting investigation at the flagged file/checkpoint | Assess backups/replicas; restore/replace/scrub per runbook |
| Verify PASS yet SELECT misses rows | Could be CL, tombstones, un-ACKed writes, or missing data on all replicas | Reconcile manifests, queries, and repair; verify does not recreate data |
| SELECT succeeds at quorum while one node errors | Other replicas satisfied CL | Isolate the failing node, plan fix/replace; avoid declaring the cluster healthy |

### Step 5 — Recover from Trusted Sources

If files need recovery, identify healthy replicas, restorable snapshots/backups, token ranges, and tombstone/repair schedules. You may need **node replace/rebuild** or supported scrub/restore workflows; choice depends on corruption severity and Cassandra version. Plan carefully so **stale replicas** are never brought back after tombstones were purged (zombie risk).

### Step 6 — Post-Remediation Verification

Read target partitions at appropriate CL and compare against **off-cluster ACKed event/operation ID manifests**. Classify separately as `FOUND_MATCH`, `MISSING`, `MISMATCH`, and `READ_ERROR`. Also inspect repair coverage, node state, I/O, and Cassandra errors. Never rely on full-table `COUNT(*)` to prove data integrity, as it scans broadly and two differing datasets can share identical counts.

## 10. Java: Capturing Logical Read Evidence Alongside Tool Output

The two SSTable tools analyze **files on a node**, whereas the Java Driver tests **what real applications observe**. The Java Driver 4.x example below queries a known partition/clustering key without full-table scans and without conflating read errors with "no data".

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class SstableEvidenceProbe {
    public enum Outcome { MATCH, MISSING, MISMATCH, READ_ERROR }

    private final CqlSession session;
    private final PreparedStatement read;

    public SstableEvidenceProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT value FROM sstable_lab.events_by_run " +
            "WHERE run_id = ? AND item_id = ?");
    }

    public Outcome verify(String runId, int itemId, String expectedValue) {
        BoundStatement statement = read.bind(runId, itemId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);
        try {
            Row row = session.execute(statement).one();
            if (row == null) {
                return Outcome.MISSING;
            }
            String actual = row.getString("value");
            return expectedValue.equals(actual)
                ? Outcome.MATCH : Outcome.MISMATCH;
        } catch (RuntimeException error) {
            System.err.printf(
                "READ_ERROR run=%s item=%d cause=%s%n",
                runId, itemId, error.getClass().getSimpleName());
            return Outcome.READ_ERROR;
        }
    }
}
~~~

Key points:

- `MATCH` means **SELECT at `LOCAL_QUORUM`** returned the expected value, not that every SSTable on every node has been verified.
- `MISSING` only means the CQL query completed with no row; if the row was `DELETE`d, this can be **correct**. Expected manifests must also track **ACKed DELETEs** to avoid false missing alerts.
- `MISMATCH` may stem from different write timestamps, unconverged replicas, wrong keys, or stale expected sources; **do not assume corruption automatically**.
- `READ_ERROR` covers timeouts, unavailable errors, or other failures; **never lump it into `MISSING`** when quantifying data loss.
- `LOCAL_QUORUM` assumes sufficient replicas exist in the local DC and the client set local DC accurately. While one node is offline for verification, remaining replicas must meet demand.
- Reuse `CqlSession` and `PreparedStatement`; example code should not generate heavy load and does not replace backups/repair.

During an incident, log at least: `operation_id`, keyspace.table, anonymized primary key, CL, timestamp, coordinator, exception type, reconciliation outcome, plus node/descriptor names from SSTable tool logs. **Never log confidential payload values**; log only markers or safe hashes to prove findings.

## 11. Evidence Boundaries: Four Things You Cannot Infer

### 11.1. Seeing Data in a Dump Does Not Mean SELECT Must Return It

One SSTable may hold `DRAFT` while a newer SSTable holds `PAID` with a higher timestamp, or a tombstone may mask `DRAFT`. CQL results reflect reconciliation under Cassandra rules, not picking a row from an arbitrary file.

### 11.2. Verify PASS Does Not Mean Replicas Have Converged

Two nodes can each hold completely valid SSTables containing different mutation versions. `sstableverify` checks files locally; `nodetool repair` and CL/manifest reconciliation answer replica divergence and expected-data questions.

### 11.3. Zero Verify Errors Does Not Prove Zero Business Data Loss

If an event was never successfully persisted to Cassandra, every SSTable can be valid while all miss that event. You need event logs/outboxes/backups or trusted upstream sources to establish **expected IDs**, not only inspect existing data.

### 11.4. Tool Failure Does Not Prove Data File Corruption

Wrong Cassandra version, file permissions, classpath/config, schema mismatch, or wrong paths can also prevent `sstabledump`/`sstableverify` from finishing. Keep **TOOL_ERROR/INCOMPLETE** distinct from **VERIFIED_CORRUPTION** based on concrete evidence.

## 12. SSTable Diagnostic Report Template

| Field | Example / What to Record |
| --- | --- |
| Incident / request ID | `INC-...` or monitoring alert ID |
| Cassandra version / SSTable format | Actual version on each node, descriptor |
| Keyspace/table | `sstable_lab.events_by_run` |
| Node/DC/rack | Inspected node name and topology |
| Timestamps | Error time, snapshot time, verify time, timezone |
| Consistency level | `LOCAL_QUORUM` for CQL check, relevant RF/DC |
| File/snapshot path | Verified `<descriptor>-Data.db` path |
| Tool/flags | `sstabledump` or `sstableverify` and exact flags used |
| Node state during run | Online snapshot / offline verify; process confirmed stopped? |
| Result | SUCCESS, FAIL with message, TOOL_ERROR, or INCOMPLETE |
| Resource impact | I/O, CPU, snapshot size, duration |
| Logical reconciliation | Expected/actual markers, found/missing/mismatch/read error |
| Next action | Leave intact, repair, restore, replace, or justified escalation |

Store reports outside the node being rescued, restrict access to dump outputs, and remember **controlled snapshot cleanup** once evidence retention ends. Snapshots pin SSTables via hard links, preventing space reclamation even after compaction replaces files. Never wipe all snapshots in a keyspace just to recover a few GiB in a lab.

## 13. Practice Exercises

**Exercise 1 — Choosing the right tool.** A customer reports `SELECT` returns `PAID`, yet one node still has an SSTable containing `DRAFT`. Should you run `sstabledump` or `sstableverify` first? Explain why seeing `DRAFT` on disk does not prove a bug.

**Exercise 2 — Snapshots and scope.** Insert, update, and then delete a row in the lab table. Flush and snapshot, then run `sstabledump` on the corresponding `Data.db` files. Record **how many SSTables** you read and the snapshot timestamp; compare with a partition-key CQL query.

**Exercise 3 — Offline conditions.** A three-node RF3 cluster already has one node down. Should you stop another node to run `sstableverify` if the app requires `LOCAL_QUORUM`? Calculate remaining available replicas and outline a stop/defer plan.

**Exercise 4 — Verify output.** The tool errors complaining it cannot find schema metadata or read the data directory. Can you declare corruption? What details must you collect to separate `TOOL_ERROR` from a damaged file?

**Exercise 5 — Tombstones and zombies.** A replica was down longer than `gc_grace_seconds`, and its dump still holds old rows; other nodes may have purged tombstones. Why must you not bring the old node back or blindly repair? Propose conditions for rebuild/replace from trusted sources.

**Exercise 6 — Restore.** `sstableverify` FAILs on an SSTable on node A, while B and C still read correct data at `LOCAL_QUORUM`. What must be verified before replacing/rebuilding A? Why does one successful query not prove B and C hold all data?

**Exercise 7 — Security.** `sstabledump` output contains `email`, tokens, or customer payloads. Design a redaction, access-control, temporary storage, deletion deadline, and incident-log procedure to preserve evidence without leaking data.

**Exercise 8 — Measuring tool cost.** In the lab, dump one small SSTable and one large SSTable; measure duration/I/O and output size. Why should you dump only suspect files/partitions rather than exporting every SSTable during an active incident?

## Remember

**`sstabledump` lets you inspect the physical contents of one SSTable; `sstableverify` validates a node's SSTables following an offline procedure.** Dumping should run on a **stable snapshot/copy** and be interpreted alongside timestamps, tombstones, TTLs, and sibling SSTables. Verifying requires stopping Cassandra on the target node, evaluating RF/CL/downtime, having trusted backups/replicas, and saving full logs/exit codes. Neither tool **modifies data, replaces anti-entropy repair, or proves full business-data completeness**. Safe diagnosis cross-checks **files + CQL + topology + off-cluster manifests** before deciding on version-appropriate restore, replace, or remediation.
