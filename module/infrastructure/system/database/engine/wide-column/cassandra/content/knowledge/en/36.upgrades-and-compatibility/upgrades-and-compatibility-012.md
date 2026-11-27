# Downgrade/Rollback Limits and Stop/Continue Criteria

> **Chapter:** Upgrades and Compatibility  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Context:** Apache Cassandra is a distributed wide-column database. Upgrades must consider partition keys, query-driven table design, replication, consistency levels, CQL, compaction, repair, backups, and Java applications.

## 1. Opening Scenario and Objectives

A Cassandra cluster is upgrading node by node from version **A** to version **B**. The first node starts cleanly, accepts writes, and flushes data to SSTables. Afterward, the Java application encounters read errors. An engineer proposes downgrading the package back to A and restarting the node.

That proposal is **not safe enough to execute**. Cassandra B may have written SSTables, commitlogs, or metadata unsupported by A; schemas or connection options may also have changed. An old binary cannot automatically rewind data and cluster state back to before the upgrade.

Decisions must be separated clearly:

- **Downgrade:** running an older Cassandra binary version on an already-upgraded node.
- **Deployment rollback:** reverting application, configuration, or version changes—whichever parts remain genuinely compatible.
- **Roll forward:** fixing the bug via a supported configuration, patch, or newer version.
- **Restore/recovery:** rebuilding data from a recovery point and appropriate historical sources.
- **Pause/stop:** holding or halting the rollout before changing state on additional nodes.

Lesson objectives:

1. Explain why mixed-version compatibility **does not imply** supported binary downgrades.
2. Identify steps that can render data/binary rollback unsafe.
3. Design **GO, PAUSE, STOP, RECOVER** decision gates grounded in measured data.
4. Test CQL/Java, replication, and consistency levels during rolling upgrades.
5. Write a runbook to preserve data and recover when downgrades are impossible.
6. Read canary results and decide when advancing to the next node is safe.

> **Scope limit:** Upgrade/downgrade rules depend on the **exact** version pair, distribution, JDK, data formats, and vendor/project guidance. Versions A/B and numeric thresholds in this lesson are teaching models only. Never apply downgrade steps from another version without verifying official docs and testing in a compatible environment.

## 2. Terminology and Real Boundaries

| Term | Action | Does it auto-revert written data? | Conditions |
|---|---|---|---|
| **PAUSE** | Do not upgrade more nodes; hold state to analyze | No | Missing evidence or warnings needing investigation |
| **STOP** | Halt current rollout plan, preserve evidence, choose remediation | No | Critical gate breached |
| **App/config rollback** | Revert Java service version, feature flag, or config | No | Reverted version remains compatible with server/schema |
| **Binary downgrade** | Run Cassandra A on a node that ran B | No | Explicitly documented as supported for **current data state** |
| **Roll forward** | Apply supported patch/config or advance to fix root cause | No | Supported path, failure scenario tested |
| **Restore** | Recover data from snapshots/backups/PITR or app sources | Can return to a checkpoint | Complete backups, valid schemas/keys, RPO/RTO, and post-cutoff writes handled |

**App rollback is not a Cassandra binary downgrade.** An older Java driver may still work with the new server if the compatibility matrix allows it, whereas Cassandra binary A may fail to read SSTables written by B. Conversely, rolling back a Java driver still requires testing native protocol, TLS, prepared statements, schemas, and retries.

**Restore does not automatically mean RPO = 0.** If backups have an 08:00 cutoff while the incident happens at 10:30, valid writes acknowledged in between risk loss unless a verified replay mechanism exists.

## 3. Why Does Cassandra Have Downgrade Limits?

### 3.1. SSTables: Compatibility Is Usually Asymmetric

Cassandra flushes memtables to **immutable SSTables**, and compaction writes newer SSTables. Along a supported upgrade path, B can read A's older format. However, **A may not be able to read files written by B**.

~~~mermaid
flowchart LR
    A["SSTables written by A"] --> B["Cassandra B reads and processes"]
    B --> C["Flush or compaction"]
    C --> D["B's SSTables may use a new format"]
    D --> E{"Can A read the new files?"}
    E -->|Confirmed by guide| F["Evaluate conditional downgrade"]
    E -->|No / Unknown| G["Never install A over the data directory"]
~~~

Crucially, **never assume risk arises only after running an SSTable conversion tool**. A new node writes SSTables via normal flushes and compactions. If a version requires a post-upgrade tool such as **`nodetool upgradesstables`**, that step adds I/O and narrows fallback options; read exact docs before running it.

Mandatory questions:

1. Which SSTable formats can A read, and which formats does B write?
2. Has the node flushed or compacted data since starting B?
3. Are there post-upgrade tasks that change formats or demand large disk headroom?
4. Is binary A officially supported on that data directory?
5. If not, which Cassandra/loader version and backup set are needed for restore?

### 3.2. Commitlogs and Metadata

Other components also introduce barriers:

- **Commitlogs:** write formats, replay, or configs can differ across versions.
- **Schema/system metadata:** CQL, UDTs, indexes, table IDs, system tables, or schema versions can change.
- **Internode protocol/gossip:** cross-version node communication has bounded support.
- **Streaming, hints, and repair:** data exchange formats or maintenance state can be version-bound.
- **Configs/JVM:** supported JDKs, removed flags, Cassandra configs, TLS, and plugins differ.
- **Topology/token ownership:** if the upgrade involved node replacement, bootstrap, decommission, or RF changes, recovery is no longer a simple package swap.

**Package managers only manage binaries; they do not restore old data/metadata state.** If an older binary boots and fails on newer data, never delete commitlogs, SSTables, or system tables to force startup. Doing so drops acknowledged writes and corrupts data.

### 3.3. Mixed-Version Is Not Permission to Downgrade

An upgrade guide may allow **A and B to coexist during a rolling upgrade** to keep serving requests while swapping nodes. That **does not prove** a node that already ran B and wrote new SSTables can safely restart on A.

Verify separately:

- Is path **A → B** directly supported, or is an intermediate release required?
- How long may A/B run mixed-version, and what schema/feature restrictions apply?
- Which post-upgrade steps must wait until every node runs B?
- Is there an explicit **downgrade** guide?
- Is there a one-way point after schema migrations, SSTable conversions, or topology changes?
- Do the Java driver, native protocol, and TLS operate cleanly during mixed mode?

If docs lack an answer, mark **UNKNOWN**—never assume it is allowed.

## 4. Points That Can Become "Points of No Return"

The table below describes **evaluation gates**, without asserting every step is one-way in every Cassandra release.

| Gate | State | What must be proven before advancing |
|---|---|---|
| **G0 — pre-upgrade** | Entire cluster still on A | Backup/restore drill, upgrade path, inventory, and baseline ready |
| **G1 — first node on B** | Cluster may now be mixed-version | Internode compatibility, CL, driver, and downgrade rules |
| **G2 — B accepted writes/flushes** | New SSTables/commitlogs may exist | Docs confirm state remains backward-readable or switch to recovery plan |
| **G3 — new schema/features** | Apps may use B-only structures | Never enable against docs while A nodes remain; revert/migration plan ready |
| **G4 — post-upgrade** | `upgradesstables`, documented metadata/maintenance tasks | Dedicated sign-off for potentially one-way steps, disk headroom, backups |
| **G5 — new topology** | Added/removed nodes, DC/RF changes, or token shifts | Re-evaluate recoverability and blast radius |

No single universal "point of no return" fits all versions. Operations must record **step name, official doc reference, current data format, evidence, and accountable owner**.

**Note on compaction/repair:** these are vital distributed storage mechanisms, not business-correctness evaluators. Running repair while suspecting accidental deletes can propagate unwanted state across replicas. Never treat repair as an "undo" button.

## 5. Four Decision States: GO, PAUSE, STOP, RECOVER

### 5.1. GO — Proceed to Next Node Batch

Declare **GO** only when every locked gate passes:

- **Compatibility:** exact source/target, JDK, and distribution match; upgrade guide allows current state.
- **Topology:** node joined as expected, schema agreement is stable, and DC/rack/token ownership match.
- **Availability:** enough healthy replicas remain to satisfy required CLs once the next node enters maintenance.
- **Correctness:** CQL/Java fixtures, partition-key reads, TTL/`DELETE`s, and business invariants hold.
- **Performance:** p95/p99 latency, throughput, and timeouts/retries stay within agreed budgets.
- **Resources:** heap/GC, native RSS, disk, network, compaction, and repair/streaming retain ample headroom.
- **Recovery:** complete backups and working recoverability remain intact before risky steps.

A GO decision must record **node batch, timestamp, metrics, scope, and approver**. It never carries over automatically across the entire campaign.

### 5.2. PAUSE — Hold to Understand What Is Happening

Choose PAUSE when there is no proof of data loss/severe danger yet GO conditions are unmet, e.g.:

- p99 climbed and it is unclear whether the new version, compaction, or hot queries caused it.
- Monitoring metrics were renamed, leaving blind spots in telemetry.
- Schema agreement or node state fluctuates without clarity on persistence.
- An integration test has not finished, or unexplained startup warnings appeared.
- Backup/restore evidence is insufficient to clear a post-upgrade step.

During PAUSE, **do not upgrade the next node**. Log timelines/logs/metrics, assign an owner, set a re-evaluation deadline, and state criteria to move to GO or STOP.

### 5.3. STOP — Halt Rollout Expansion

Choose STOP immediately when evidence shows:

- Data corruption, missing rows, abnormal TTL/tombstones, or violated business invariants.
- Insufficient replicas for CL, read/write unavailable errors, or timeouts breaching stop gates.
- Upgrade path or mixed-version pairing discovered to be unsupported.
- Nodes crash-looping/OOMing, full disks, severe security bugs, or broken internode links.
- New binary wrote data/metadata that the rollback plan cannot handle.
- Clean backups or decryption access lost before a one-way step.

**STOP does not automatically mean installing the old binary.** You may keep the upgraded node to diagnose, fix configs, apply a supported patch/roll-forward, roll back apps, or restore from backups.

### 5.4. RECOVER — When Current State Cannot Safely Be Saved In Place

Choose RECOVER when data or infrastructure state must be rebuilt—such as corruption, replicated accidental deletes, missing valid replicas, or data incompatible with downgrade. Stand up an isolated recovery environment, pick a clear recovery point, load via version-compatible tools, reconcile data, measure RPO/RTO, and shift traffic only after acceptance tests pass.

~~~mermaid
flowchart TD
    A["Issue arises during upgrade"] --> B["PAUSE: do not upgrade new nodes"]
    B --> C{"Data corruption / lost quorum / severe security fault?"}
    C -->|Yes| D["STOP: preserve data and evidence"]
    C -->|No| E["Diagnose from telemetry"]
    E --> F{"All gates passed?"}
    F -->|Yes| G["GO: next batch"]
    F -->|No| H["Stay PAUSE or escalate to STOP by severity"]
    D --> I{"Supported forward-fix or partial rollback available?"}
    I -->|Yes and tested| J["Apply controlled fix, re-verify"]
    I -->|No| K["RECOVER from backup / independent source"]
~~~

## 6. Defining Evidence Gates, Baselines, and Thresholds

| Gate group | Measurement or check | Why |
|---|---|---|
| **Binary/topology** | Per-node version, `nodetool status`, schema agreement, DC/rack | Catches nodes failing to join or unintended mixed-version clusters |
| **Replication/CL** | Available replicas, per-DC read/write timeouts and unavailable | Configured RF does not prove live replicas are healthy |
| **Data** | Compare event IDs, values, clustering order, TTL/`DELETE`, sample partitions | Exception-free `SELECT`s can still return wrong data |
| **Java app** | Handshake, auth/TLS, prepared/bound, paging, retries, query correctness | Verifies critical application access paths |
| **Latency/throughput** | p50/p95/p99 per query shape, RPS, matching load | Cluster-wide averages easily hide regressions |
| **JVM/OS** | GC pauses, heap, native/RSS, cgroup, page cache, disk/network | Catches OOMs and exhausted I/O headroom |
| **Maintenance** | Compaction backlog, repair, streaming, pending tasks, hints | Background work can strip availability on the next turn |
| **Backup/restore** | Manifests, checksums, schemas, keys, restore drill results | Proves a recovery path exists when needed |

**Never use `UN` (Up/Normal) as sole evidence.** A node can look Up/Normal while missing data for some token ranges or breaking Java services.

### 6.1. Illustrative Threshold Example

Suppose operations chose workload-specific verification criteria:

~~~text
After each node, observe at least 15 stable minutes at baseline-equivalent load.
- Critical query shapes: p99 increases at most 20% above baseline.
- Read/write timeouts stay within app error budget.
- Zero fixture mismatches or business invariant violations.
- Zero lost quorum or replica availability.
- Disk, GC, streaming/compaction, and node health within internal thresholds.
- Backups/keys/restore path remain ready.

If telemetry or tests are missing => PAUSE
If data corruption, lost quorum, or severe security bug => STOP
If all pass and owners sign off => GO
~~~

**15 minutes and 20% are hypothetical practice numbers**, not standard Cassandra thresholds. Observation windows and tolerances must derive from SLOs/error budgets, load baselines, partition-size distributions, disk types, and environment stability. Severe data errors require immediate STOP without waiting out the window.

## 7. Before Canary: Inventory and Recovery Plan

### 7.1. Version and Environment Dossier

~~~text
Cluster:                   <id / environment>
Source Cassandra:          <version + build, per node>
Target Cassandra:          <version + build>
Distribution:              <Apache/vendor/managed>
Source/target server JDK:  <runtime and flags>
App driver/JDK:            <artifact + version>
DC/rack/nodes/RF/CL:       <actual config and state>
SSTable/commitlog/schema:  <current formats and states>
OS/container/config:       <image, cassandra.yaml, JVM options>
Upgrade/downgrade docs:    <official URL/section>
Mixed-version window:      <constraints per guide>
Point of no return:        <step, evidence>
Backup:                    <ID, cutoff, checksums, schema, KMS>
Restore drill:             <date, outcome, RPO/RTO>
Runbook/owner:             <version, decision-maker>
~~~

All versions must come from the live system and deployment build. If a cluster is already mixed-version from earlier maintenance, capture **every node's** exact state.

### 7.2. Read-Only Checks Before Rollout

On an authorized cluster using version-matched syntax:

~~~bash
nodetool status
nodetool info
nodetool compactionstats
nodetool tpstats
nodetool tablestats shop.events_by_tenant_day
~~~

In **cqlsh**:

~~~sql
SELECT release_version, schema_version
FROM system.local;

SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'shop';
~~~

**`system.local` reflects only the connected node**, not all nodes' versions. Collect telemetry and metadata across all relevant nodes/sources.

Never run data/topology-mutating commands like **`repair`, `upgradesstables`, `cleanup`, `decommission`** just to inspect baselines. Those require dedicated runbooks, I/O headroom, and approval.

### 7.3. Replication and Consistency Levels in Maintenance Windows

With RF = 3 in a local DC, **`LOCAL_QUORUM`** requests typically require replies from at least **two replicas** in that DC. While one node stops to upgrade, the remaining two replicas must be genuinely healthy with valid data. RF does not guarantee remaining replicas are online, free of GC pauses, or free of disk saturation.

Likewise, raising consistency levels cannot fix corrupted data already replicated. Repair syncs replicas without knowing which `DELETE` was business-erroneous.

### 7.4. Backups Before Risky Steps

A trustworthy backup must:

1. Cover all required nodes/token ranges and tables; one node's snapshot is not a cluster backup.
2. Have verified manifests, checksums, schemas, versions, decryption keys, and data cutoff.
3. Live **outside the matching failure domain** with separated read/delete permissions and retention.
4. Pass **isolated restore tests** using a version compatible with the SSTables.
5. Include a plan to reconcile/recover valid writes occurring after the backup cutoff.

If the latest backup is incomplete or undecryptable, **NO-GO** any potentially one-way step. Replicas do not replace backups when the whole cluster receives an accidental delete or overwrite.

## 8. Decision-Gated Rolling Upgrade

**Node order, mixed-version rules, stop/start commands, and post-upgrade actions must follow the exact version-pair guide.** The flow below is a control structure, not a universal command sequence for every version.

~~~mermaid
flowchart TD
    A["G0: preflight version/backup/topology"] --> B{"Prerequisites met?"}
    B -->|No| X["NO-GO: fix blockers"]
    B -->|Yes| C["Upgrade canary per upgrade guide"]
    C --> D["Check join, CQL, Java, CL, resources"]
    D --> E{"Wrong data / lost quorum?"}
    E -->|Yes| S["STOP and evaluate recovery"]
    E -->|No| F{"UNKNOWN warnings or unmet gates?"}
    F -->|Yes| P["PAUSE, do not upgrade next node"]
    F -->|No| G["GO next node"]
    G --> H{"All nodes complete?"}
    H -->|No| C
    H -->|Yes| I["Post-upgrade gate; assess one-way steps"]
    I --> J["Verify cluster + backup/restore + sign-off"]
~~~

### G0 — Before Canary

Lock down upgrade path, all known issues/removed options, cluster health, baseline, backup/restore drills, app/driver compatibility, and decision-makers. Any critical **UNKNOWN** blocks GO.

### G1 — Canary Node

After upgrading one node:

1. Confirm binary, JDK, and config match with zero unexplained startup warnings.
2. Verify node join, DC/rack/tokens, schema agreement, and gossip/internode connectivity.
3. Measure CLs, read/write timeouts, retries, p95/p99, GC, disk, compaction, and streaming.
4. Run CQL fixtures and Java integration tests across representative partition keys.
5. Check whether new SSTables/commitlogs/metadata were written to update downgrade eligibility.
6. Declare GO for the next node only after owners sign off on all gates.

### G2 — Subsequent Node Batches

Repeat checks on every batch while watching **the entire cluster**. One healthy canary does not prove stability once multiple nodes accumulate streaming, compaction, hinted handoff, or repair backlogs. Keep target-only features/schemas **disabled** if required by the upgrade guide.

### G3 — Target Completion

Verify every node runs the target version with zero unintended mixed-version nodes; re-run CQL/Java fixtures, measure SLOs, and test backups/restores plus admin tooling. Perform **potentially one-way post-upgrade actions** only under a dedicated gate with evidence and recovery plans.

## 9. Choosing App Rollback, Roll Forward, or Restore on Failure

### 9.1. Symptom-Based Decision Table

| Signal | Immediate action | Resolution after assessment |
|---|---|---|
| Java app handshake fails due to TLS/CA config | PAUSE, upgrade no more nodes | Fix config/driver; roll back app if compatible with target server |
| Canary node fails to join due to removed JVM flag | PAUSE; STOP if replica availability drops | Fix target runtime/config or follow downgrade guide |
| p99 climbs during compaction while data stays accurate | PAUSE, measure disk/GC/I/O and compare load | Shed pressure per runbook, fix root cause, or roll forward |
| Read/write unavailable, insufficient local quorum | STOP | Restore replica availability before considering resuming |
| Fixture spots corrupted data / resurrected rows | STOP immediately, preserve evidence | Analyze and choose safe restore/roll-forward per scenario |
| Old binary cannot read SSTables written by new version | Do not downgrade directly | Stay on a version that reads the data, fix/roll forward, or restore clean backup |
| Backups fail to decrypt before a one-way step | NO-GO / STOP | Restore DR capability before crossing the gate |
| Severe security bug in auth/TLS/roles | STOP | Restore access controls via supported mechanisms |

**STOP does not automatically reinstall the previous version.** An unsupported binary downgrade can worsen the outage and obstruct recovery. Follow only downgrade paths verified by documentation **for the current data state**.

### 9.2. Rolling Back Only the Java Application When Appropriate

If server B is healthy yet a Java service or driver update causes errors, rolling back the app tier alone works **only if**:

- The old driver's compatibility matrix supports server B and its native protocol.
- The old app's schemas/CQL/codecs/UDTs, prepared metadata, and paging remain valid.
- Authentication, TLS certs, hostname validation, and permissions still hold.
- Retry policies/idempotency do not duplicate records; event IDs for identical requests stay deterministic.
- Read/write tests and invariants pass after the app rollback.

This avoids downgrading Cassandra binaries whenever the fault is strictly isolated to the client.

### 9.3. When to Roll Forward?

If a **vendor/project-supported** patch or new config directly fixes the root cause, rolling forward can be safer than an incompatible data downgrade. Still check release notes, known issues, JDK/configs, mixed-version rules, backups, staging/canary tests, and stop gates. **Never assume "installing the latest patch fixes everything."**

### 9.4. When to Recover from Backups?

Choose restore when returning to a clean data checkpoint, when old binaries cannot read current state, or when replicas lost valid/available copies.

Conceptual steps:

1. Stop the source of corruption; preserve logs, backups, and incident timeline.
2. Select a **COMPLETE** backup with verified cutoff, schema, manifest, checksums, token coverage, and decryption keys.
3. Stand up an **isolated** recovery cluster with compatible Cassandra/JDK/loader versions.
4. Load SSTables, incremental sets, or commitlog archives per version-exact runbook without blindly replaying bad changes.
5. Reconcile partition keys, tombstones/TTLs, query-driven tables, and valid post-cutoff writes.
6. Run CQL/Java tests, measure real RPO/RTO, and shift traffic only in a controlled cutover.

**Never blindly copy old SSTables into a live production cluster taking writes**: mismatched timestamps cause schema/tombstone bugs and resurrect properly `DELETE`d rows. Nor can repair tell which value is business-correct.

## 10. Partition-Key CQL Verification

Consider a table for the access pattern "fetch latest events for a tenant on a given day":

~~~sql
-- Assumes keyspace shop already exists with topology-appropriate replication.
CREATE TABLE IF NOT EXISTS shop.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    happened_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), happened_at, event_id)
) WITH CLUSTERING ORDER BY (happened_at DESC, event_id ASC);

-- Fixture created only in staging/test environments.
INSERT INTO shop.events_by_tenant_day (
    tenant_id, event_day, happened_at, event_id, event_type, payload
) VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21',
    '2026-11-21T08:00:00Z',
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED',
    '{"order":"test-001"}'
);
~~~

Verification query:

~~~sql
SELECT happened_at, event_id, event_type, payload
FROM shop.events_by_tenant_day
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Both **`tenant_id`** and **`event_day`** belong to the partition key; the driver can use routing keys when prepared and fully bound, depending on metadata. **Clustering columns** govern sort order inside the partition.

Verification must compare **`event_id`, `event_type`, `payload`, and row order** against the pre-upgrade fixture. Cover multiple partitions/token ranges—not just one tenant—plus updated, `DELETE`d, TTL-expired, and collection/UDT records if used. An exception-free `SELECT` returning 0 rows **proves nothing** if fixture data ought to exist.

In production, prefer partition-keyed read checks and non-destructive invariant checks. Never run full-table scans or bulk test writes against live business tables just to check a canary.

## 11. Java Driver 4.x Rollout Gate Example

A concise smoke test should **assert expected data**, not just open a connection.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class UpgradeGoGateSmokeTest {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID expectedEventId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        LocalDate day = LocalDate.of(2026, 11, 21);

        // Point only to the test cluster, never production.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_id, event_type, payload " +
                "FROM shop.events_by_tenant_day " +
                "WHERE tenant_id = ? AND event_day = ? LIMIT ?");

            ResultSet result = session.execute(
                query.bind(tenantId, day, 20)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM));

            boolean matched = false;
            for (Row row : result) {
                if (expectedEventId.equals(row.getUuid("event_id"))
                    && "ORDER_CREATED".equals(
                        row.getString("event_type"))
                    && "{\"order\":\"test-001\"}".equals(
                        row.getString("payload"))) {
                    matched = true;
                    break;
                }
            }

            if (!matched) {
                throw new IllegalStateException(
                    "STOP: data differs from fixture after upgrade");
            }
            System.out.println("PASS: verified sample event");
        }
    }
}
~~~

**Execution conditions:**

- The example uses Java driver **4.x** packages and the schema/fixture from Section 10.
- The cluster has datacenter **`dc1`** with enough replicas for **`LOCAL_QUORUM`**; with one node, a different RF/CL model is needed and results cannot generalize to production.
- Configure authentication and TLS per real cluster policy; omitted here only to keep the query concise. Never disable certificate verification just to make tests pass.
- In real applications, reuse **`CqlSession`** and **`PreparedStatement`** rather than creating them per request.
- One passing fixture **does not** prove throughput, timeout resilience under load, large paging, or every partition's integrity. Run integration/soak tests with diverse keys and failure cases.

During supported mixed-version windows, run the exact same suite at source, after canary, and after full cluster completion. Archive exit codes, latency, retries, exception types, and approver sign-off in the gate record.

## 12. Quantitative Decision Scenario

**Hypothetical scenario:** local DC has RF = 3; Java app reads/writes at **`LOCAL_QUORUM`**. Cluster upgrades along a verified path: N1 runs B, while N2 and N3 still run A.

Before upgrading, a critical query hit **p99 = 80 ms** at **2,000 requests/sec**. Operations set a test gate: p99 must not exceed baseline by over **25%** under equivalent load, with zero lost quorum and zero data mismatches.

After upgrading N1:

| Signal | Observation | Assessment |
|---|---|---|
| N1 | UP/NORMAL, binary B | Passes only basic startup gate |
| N2 | High disk I/O, write timeouts observed | Remaining replica unhealthy |
| p99 read | Rose from 80 to 125 ms | Exceeds 100 ms threshold |
| CQL fixture | Event ID and payload match | No data errors seen in sample scope |
| Compaction | Backlog climbing on N2 | Needs I/O analysis |
| Backup | COMPLETE, restore drill PASS | Tested recovery path available |

**Decision: PAUSE; do not upgrade N2.** The p99 spike and N2 load are unexplained. Upgrading another node now could strip local quorum replicas.

Next steps:

1. Collect timelines, logs, per-query-shape p99, disk latency, compaction, and per-replica timeouts.
2. Separate a B regression from a pre-existing N2 issue.
3. If **lost quorum or corrupted data** is found, switch to **STOP** immediately.
4. Once root-caused and resolved via supported means, re-run the gate under matching load.
5. Advance to GO only after owners review evidence and confirm recovery paths remain intact.

**Never blindly downgrade N1 back to A just because p99 climbed.** First verify whether A can actually read N1's current SSTable/commitlog/schema state.

### 12.1. Second Scenario: Data Error After a One-Way Step

The cluster finished upgrading to B and ran a post-upgrade step documented as making on-disk formats incompatible with A. Afterward, fixtures show properly `DELETE`d rows reappearing.

Action:

- **STOP** all further changes and block the source of bad data.
- Preserve evidence and check scope/timing across multiple token ranges.
- **Never reinstall A** onto the format-converted data directory.
- Evaluate supported forward-fixes/patches or restoring from a clean checkpoint onto an isolated cluster.
- Account for TTLs/tombstones and valid writes arriving after the cutoff.
- Reopen traffic only after application/replica checks and invariants pass.

Running repair immediately before knowing which data is right complicates investigation. Repair converges replica state per Cassandra semantics without understanding whether a business `DELETE` was valid.

## 13. GO/PAUSE/STOP/RECOVER Decision Record Template

~~~yaml
change_id: "cassandra-upgrade-drill-2026-11-21"
environment: "staging"
source_version: "<exact-source-build>"
target_version: "<exact-target-build>"
documentation:
  upgrade_guide: "<verified-url-and-section>"
  downgrade_policy: "<verified-url-and-section>"
  mixed_version_constraints: "<documented-limit>"
node_batch:
  nodes: ["node-01"]
  started_at_utc: "<actual-time>"
  verified_at_utc: "<actual-time>"
compatibility:
  sstable_readable_by_source: "UNKNOWN"
  new_schema_feature_enabled: false
  irreversible_post_upgrade_action_done: false
recovery:
  backup_id: "<verified-backup-id>"
  cutoff_utc: "<verified-cutoff>"
  restore_drill: "PASS"
gates:
  node_health: "PASS"
  schema_agreement: "PASS"
  quorum_availability: "PASS"
  java_driver_tls_auth: "PASS"
  cql_fixture: "PASS"
  latency_error_budget: "PAUSE"
  compaction_disk_memory: "INVESTIGATE"
decision:
  state: "PAUSE"
  reason: "p99 breached threshold, old replica experiencing high I/O"
  owner: "<responsible-role>"
  evidence: "<logs-metrics-tests>"
  next_review_utc: "<scheduled-time>"
  next_action: "diagnose I/O before upgrading next node"
~~~

This is an **internal reference record template**, not Cassandra configuration. An **UNKNOWN** value in `sstable_readable_by_source` means **binary downgrade is not permitted as an approved recovery plan**.

### 13.1. Decision Roles

- **DBA/SRE:** topology, storage, replica availability, compaction, repair, and format compatibility.
- **Java/application owner:** query correctness, driver/TLS, retries/timeouts, consistency levels, and SLOs.
- **Security owner:** whenever authenticators/authorizers, certificates, KMS, or permissions change.
- **Change/incident owner:** consolidates evidence, logs timestamps, sets decision state, and coordinates remediation.

Saying "looks good to continue" without baselines, scope, versions, evidence, and owners fails audit during incidents.

## 14. Practice Exercises

### Exercise 1 — Does Mixed-Version Equal Downgrade Support?

Docs allow A and B to coexist during a rolling upgrade. Node B already wrote new SSTables, and an operator wants to reinstall A.

**Question:** Are there sufficient grounds to proceed?

**Suggested answer:** No. Verify binary downgrade support for the current SSTable/commitlog/metadata state. Mixed-version support does not guarantee B's format is backward-readable by A.

### Exercise 2 — Node Is `UN`, Yet CL Fails

N1 runs B and reports **`UN`**, N2 is flapping, and the app sees read timeouts at **`LOCAL_QUORUM`**.

**Question:** GO, PAUSE, or STOP?

**Suggested answer:** At least **PAUSE**. If quorum/availability gates are breached or faults are severe, **STOP**. N1's solo status does not prove the cluster has enough replicas.

### Exercise 3 — Rolling Back the Java Driver

Cassandra B is healthy, yet the new Java driver fails decoding a UDT. The old driver worked cleanly with A.

**Question:** Can you roll back the driver without downgrading Cassandra?

**Suggested answer:** Possibly, if the old driver is supported against B and schema/CQL/UDT/TLS/CL/paging tests pass. Never infer compatibility solely because the old driver worked with A.

### Exercise 4 — One-Way Step and Backups

A post-upgrade task is documented as writing SSTables unreadable by A. The latest off-domain backup has not had decryption or restore tested yet.

**Question:** Should you run it immediately?

**Suggested answer:** **NO-GO.** Secure a COMPLETE backup with schemas, checksums, and keys; test restore and lock RPO/RTO before crossing a one-way gate.

### Exercise 5 — Computing Latency Thresholds

Baseline p99 = 100 ms. An illustrative gate allows at most a 20% increase. Post-canary, p99 = 135 ms under equivalent load.

**Question:** Which decision applies?

**Suggested answer:** Threshold is **120 ms**. 135 ms exceeds the cap, so PAUSE to investigate; if wrong data or lost availability appears, STOP.

### Exercise 6 — Recovery Point

A clean backup has an **08:00 UTC** cutoff; the cluster fails at **10:30 UTC** with acknowledged writes in between and no supplemental logs/PITR.

**Question:** Does restore guarantee RPO = 0?

**Suggested answer:** No. Roughly **2 hours 30 minutes** of changes risk loss without an independent replay source; reconcile writes and report actual RPO.

### Exercise 7 — Can Repair Undo a `DELETE`?

During mixed-version operation, a row properly `DELETE`d pre-upgrade suddenly reappears in some read results.

**Question:** Should you run repair immediately to fix it?

**Suggested answer:** **STOP**, verify scope and true data state, and preserve evidence. Repair syncs replica state per Cassandra mechanics without knowing whether a business `DELETE` was valid or erroneous.

## 15. Per-Step Go/No-Go Checklist

- [ ] Verified actual Cassandra version/build and JDK on **every node**.
- [ ] Have upgrade/downgrade guides for **the exact version pair and distribution**.
- [ ] Direct vs. intermediate hops and mixed-version limits clearly documented.
- [ ] Identified SSTable, commitlog, schema, data format changes, and potentially one-way steps.
- [ ] No new features/schemas enabled against guidance while mixed-version.
- [ ] Java driver, CQL binds, prepared statements, TLS/auth, and native protocol all tested.
- [ ] DC/rack, RF, token ownership, schema agreement, and CLs meet targets.
- [ ] Verified data across multiple partition keys, including `UPDATE`/`DELETE`/TTL and denormalized tables.
- [ ] p95/p99 latency, timeouts, retries, and throughput within bounds under matching load.
- [ ] Heap/GC, native/RSS, disk, compaction, streaming, and repair retain ample headroom.
- [ ] COMPLETE backups, valid checksums/schemas/keys, and passing restore drill.
- [ ] Supported fix, roll-forward, app rollback, or restore plan ready—never assuming binary downgrade.
- [ ] Owners, observation windows, metrics, and **GO/PAUSE/STOP/RECOVER** criteria defined.
- [ ] Any potentially one-way post-upgrade step approved separately.
- [ ] Re-tested Java apps, backups/repairs, dashboards, and alerts after upgrading all nodes.

## 16. Summary

Cassandra downgrade limits stem from **SSTables, commitlogs, schemas/metadata, internode protocols, runtimes/configs, and client compatibility**. Supporting A/B coexistence during a rolling upgrade **does not mean** a node that wrote data on B can safely run A again. Every fallback path needs exact version documentation and evidence of actual data state.

Declare **GO** only when correctness, availability, performance, resources, and recoverability all pass. Choose **PAUSE** when diagnosis is needed and evidence is incomplete; **STOP** on severe violations; and **RECOVER** when data or infrastructure state must be rebuilt. From partition-key design, replication, and consistency levels to compaction, repair, and Java connectivity, every layer must be verified before advancing to the next node.
