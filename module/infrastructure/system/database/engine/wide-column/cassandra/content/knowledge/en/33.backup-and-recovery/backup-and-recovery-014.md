# Recovery Drills, Timing Measurements, and Updating the Runbook

> **Chapter:** Backup and Recovery  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra, distributed wide-column architecture, partition keys, query-driven table design, replication, consistency levels, CQL, compaction, repair, troubleshooting, and Java applications.

## 1. From "Having Backups" to "Being Recoverable"

A Cassandra system can take daily snapshots, copy files to object storage, and display green backup statuses yet still **fail to restore service** when an incident hits. For example: missing snapshots on some nodes, missing schema, lacking decryption permissions, SSTables incompatible with the target cluster, or nobody knowing where to point the Java application after loading data.

A **recovery drill** is the controlled execution of all or part of an incident response procedure in a test environment, timing every stage, verifying data, and recording needed improvements into the **operational runbook**. The goal is not merely making restore commands exit cleanly, but proving the system and application can actually resume serving per defined objectives.

A worthwhile drill must answer:

1. **Restore from what?** Which backup, which data cutoff, and are all nodes/token ranges, schemas, SSTables, and decryption keys present?
2. **Restore to where?** A new cluster, a replacement node, or an isolated environment; is it compatible with running Cassandra, JDK, and configs?
3. **What was recovered?** Partition data, business correctness, TTLs/tombstones, related tables, and post-backup changes.
4. **How long did it take?** From service impact onset until users can use it again—not just file download duration.
5. **How much data was lost?** Are valid ACKed writes after the recovery point still present or requiring compensation?
6. **How do we do better next time?** Refine procedures, automation, access permissions, alerts, and the next drill schedule.

> **Practice rule:** drill on an isolated cluster or dedicated test resources; never drop tables, overwrite SSTables, or shift production traffic merely to test a runbook.

## 2. Distinguishing RPO/RTO Targets from Observed Measurements

### 2.1. Two Primary Metrics

| Metric | Question | Meaning |
|---|---|---|
| **RPO — Recovery Point Objective** | How far back in time can data loss go? | Maximum acceptable data rollback window; must anchor to a recoverable data cutoff |
| **RTO — Recovery Time Objective** | After an incident, how soon must service work? | Maximum duration from **defined disruption start** until **restored service passes acceptance criteria** |

These are **targets**, not measurement results. Reports must also state:

- **Actual / estimated RPO after restore:** the newest valid write proven to reside in the recovered state relative to incident onset. When cluster-wide snapshots lack a uniform cutoff, report an uncertainty range rather than a fabricated exact figure.
- **Measured actual RTO:** from disruption onset until data and application access paths pass acceptance—including detection, decision-making, provisioning, backup download, restore, verification, and traffic cutover.
- **Count of missing or needing-replay business changes:** ACKed orders/events absent from recovered data. Time metrics never substitute for data-loss reconciliation.

Illustrative formulas:

~~~text
Cutoff-based estimated RPO = T_incident - T_recovered_cutoff

Measured RTO = T_service_accepted - T_disruption_started

Backup creation latency ≠ service recovery time
Upload completion time ≠ latest data timestamp inside backup
~~~

Use **UTC** consistently across event timestamps and system clocks. To measure stage durations, use monitoring timers/monotonic clocks where possible to avoid drift from unsynced node clocks or timezone changes.

### 2.2. Why Must Start and End Points Be Explicitly Defined?

Measuring solely from starting backup download until SSTable loading finishes skips **incident detection, decryption approval, infrastructure provisioning, business validation, and application recovery**. Record milestones:

- **T0 — impact begins:** per synthetic incident or defined real incident.
- **T1 — detected:** alert, dashboard, or on-call confirmation.
- **T2 — decision made:** select backup/recovery point and open runbook.
- **T3 — target environment ready:** nodes, networking, version config, and keys.
- **T4 — data transferred to target:** including checksums/manifests.
- **T5 — cluster readable:** load/streaming complete; nodes reach valid states.
- **T6 — data and application accepted:** queries, business invariants, latency, errors, and consistency meet thresholds.
- **T7 — serving access path open:** RTO endpoint when acceptance criteria require live user access.

For drills that do not shift real traffic, mark **T7 as simulated**, and separate **measured RTO** from **estimated traffic-cutover time**. Never claim a proven production RTO without rehearsing those dependencies.

## 3. Selecting Drill Scenarios by Failure Domain

Cassandra provides replication to survive replica failures, yet replication **does not store data history prior to erroneous deletes or overwrites**. Snapshots keep SSTable references per node and must leave the failure domain to survive node/region loss. Every drill should specify the **incident type** before picking a recovery method.

| Scenario | Test Objective | Primary Mechanism | Acceptance Result |
|---|---|---|---|
| Single node lost, other replicas healthy | Does the replacement node receive full tokens/data and cluster keep serving? | Replace/bootstrap/streaming, replication | Replacement node healthy; target CL met; no old-data restore needed |
| Subset of data accidentally deleted | Can pre-error data be retrieved? | Pre-incident snapshot/backup, selective restore | Clean records intact; valid post-cutoff changes reconciled |
| Entire cluster or region lost | Can a new cluster be built from off-domain copies? | Independent backup + schema/config + restore | Application accesses data and meets RPO/RTO targets |
| Replicas diverged after failure | Are discrepancies detected and fixed per workflow? | Repair and consistency monitoring | Replicas converge within Cassandra's mechanism limits |
| Backup incomplete or undecryptable | Caught early and switched to fallback? | Manifest, checksum, permissions, and fallback backup checks | Clear error report, known last-good point, runbook updated |

**Repair does not replace restoring from backups.** Running repair after a propagated valid `DELETE` cannot deduce that the record should be "undone." Likewise, do not force a restore when only one node died while surviving replicas hold the newest data; match the mechanism to the failure mode.

### 3.1. Choosing Drill Realism Tier

Three common tiers:

1. **Tabletop:** walk through decisions, contacts, permissions, and planned commands; great for finding runbook gaps, yet **does not prove real RTO**.
2. **Technical restore on an isolated cluster:** download backups, build schema, load data, time each stage, and run CQL/Java checks; proves most technical recovery steps.
3. **End-to-end near-production:** includes simulated alerts, infrastructure provisioning, data recovery, application cutover, latency/error checks, and rollback. Best compares against business RTO.

Reports must explicitly state which tier was drilled. Never extrapolate a tiny few-MiB restore duration to claim RTO compliance for a multi-tens-of-TiB cluster.

## 4. Preparation and Safety Preconditions

### 4.1. Mandatory Input Checklist

Before starting, the drill team needs:

- **Scope:** keyspaces, tables, environment, token ranges, data timeframe, and related Java services.
- **Backup set:** ID/tag, node list, relevant snapshots/incremental SSTables/commitlogs, manifests and checksums, verified **COMPLETE** status.
- **Schema and topology:** CQL definitions for keyspaces/tables, UDTs, partitioner, replication strategy, RF, DC/rack, Cassandra/JDK/SSTable format, security config.
- **Target infra:** network, storage, headroom for data loading and compaction, node count, backup read access.
- **Keys / secrets:** KMS/secret manager references and pre-tested decryption rights; never paste secrets into reports.
- **Data boundary:** cutoff backed by backup workflow, application watermarks if any, list of business operations for reconciliation.
- **Acceptance criteria:** expected tables/partitions, sample row counts, business invariants, read/write CLs, latency/error thresholds.
- **Stop and rollback gates:** who holds abort authority, when to isolate the cluster, and traffic rollback steps if app configs were touched.

Cassandra snapshots generally hold hard links to SSTables on **each node**; taking a snapshot on one node **does not automatically cover the entire cluster**. A backup might rely on a proven sufficient subset of replicas/token ranges, yet simpler, auditable workflows coordinate snapshots across all nodes in scope. Distributed snapshots **are not automatically cluster-wide atomic** while writes continue.

### 4.2. Production Protection Boundaries

- Use a **separate restore cluster**, DNS, service accounts, and endpoints distinct from production.
- Restrict network egress from the drill environment so test jobs cannot send writes to production.
- If backups contain sensitive data, enforce purpose-scoped access, encryption, and masking/retention policies.
- Set budget and lifetime limits on test infrastructure, without under-sizing resources so severely that timing loses representativeness.
- For **region-loss** drills, prove backup read and decryption permissions do not depend on resources assumed lost.
- Never delete production snapshots, clusters, buckets, or data as a simulation step; simulate failures via isolation, access blocks, or dedicated environments whenever possible.

## 5. Verification Dataset: Tied to Partition Keys and CQL

A compact sample dataset tests both recovery execution and Cassandra semantics. Suppose a Java app stores order events by customer/day. Create **in the drill environment**:

~~~sql
-- dc1 and RF = 3 apply only when the environment has matching replicas
-- and topology. Adjust when building the test cluster.
CREATE KEYSPACE IF NOT EXISTS restore_drill
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS restore_drill.events_by_customer_day (
    customer_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    order_id uuid,
    event_type text,
    amount decimal,
    PRIMARY KEY ((customer_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

The partition key is **(customer_id, event_day)**. Since Cassandra routes by partition key token, checks must span **multiple partitions across different token ranges**—avoid reading one customer and declaring all data recovered.

Sample seed data:

~~~sql
INSERT INTO restore_drill.events_by_customer_day
    (customer_id, event_day, occurred_at, event_id, order_id,
     event_type, amount)
VALUES
    (11111111-1111-4111-8111-111111111111, '2026-11-21',
     '2026-11-21T08:10:00Z',
     22222222-2222-4222-8222-222222222222,
     33333333-3333-4333-8333-333333333333,
     'ORDER_CREATED', 120.50);

INSERT INTO restore_drill.events_by_customer_day
    (customer_id, event_day, occurred_at, event_id, order_id,
     event_type, amount)
VALUES
    (44444444-4444-4444-8444-444444444444, '2026-11-21',
     '2026-11-21T08:20:00Z',
     55555555-5555-4555-8555-555555555555,
     66666666-6666-4666-8666-666666666666,
     'ORDER_PAID', 275.00);
~~~

In real environments, generate diverse customer/event IDs and maintain a **reconciliation ledger** recording (partition key, clustering key, event_type, amount, confirmed write timestamp). Have the application check **watermarks or business ID sequences** to detect post-backup missing events. One readable row does not prove a multi-partition table fully recovered.

Post-restore CQL check:

~~~sql
SELECT occurred_at, event_id, order_id, event_type, amount
FROM restore_drill.events_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 100;
~~~

Avoid using **full-table `SELECT COUNT(*)` on production-sized tables** as a default check: it can overload resources, and identical totals can mask missing rows alongside corrupted writes. On small fixtures you can check counts, yet verifying **exact keys and values** matters far more.

### 5.1. Adding Tough Test Cases

The drill dataset should include at least:

- One tiny partition and one multi-row partition across distinct token ranges.
- One row **`UPDATE`d** before cutoff to verify the right value version wins.
- One row validly **`DELETE`d** before cutoff to confirm restore does not unexpectedly resurrect old data.
- Intentional TTLs, checking expired values do not count as live.
- Data with UDTs, collections, or TTL/tombstones if used in production schemas.
- Some valid writes **after** cutoff to measure data needing reconciliation or accepted as lost.

Cassandra resolves versions via timestamps/tombstones/TTLs, so **mixing SSTables from different times into a cluster holding newer writes** can yield surprises. Restoring first in isolation and checking delete/expiry semantics is mandatory.

## 6. End-to-End Recovery Drill Workflow

### 6.1. Task Flow and Checkpoints

~~~mermaid
flowchart TD
    A["Trigger scenario and record T0"] --> B["Identify backup/cutoff, lock criteria"]
    B --> C["Stand up isolated recovery cluster"]
    C --> D["Download backups, manifest, schema, keys"]
    D --> E{"Checksums and data scope complete?"}
    E -->|No| X["Stop or pick fallback backup; log blocker"]
    E -->|Yes| F["Create schema and load SSTables per version runbook"]
    F --> G{"Nodes, schema, tokens, and data valid?"}
    G -->|No| X
    G -->|Yes| H["Run CQL, Java, and business invariant tests"]
    H --> I{"Meets acceptance criteria?"}
    I -->|No| X
    I -->|Yes| J["Rehearse app connectivity and simulated traffic cutover"]
    J --> K["Record T7, compute RPO/RTO, update runbook"]
~~~

### 6.2. Actionable Execution Steps

**Step 0 — Confirm the charter.** Assign drill ID, incident coordinator, Cassandra operator, Java service owner, and approver. State incident type: **full cluster loss**, **logical deletion**, or **node loss**. Lock T0 and target RPO/RTO before starting; otherwise pass/fail cannot be judged fairly.

**Step 1 — Pick the recovery point.** Fetch a backup set marked `COMPLETE` with its true data timestamp. Inspect per-node snapshot timestamps, application barriers if any, upload statuses, checksums, schema, and keys. Never treat "upload finished" as the recovery point.

**Step 2 — Provision the target environment.** Provision compatible Cassandra/JDK, replication strategy, partitioner, and sufficient storage. Place nodes in exact DCs/racks; check node-to-node and client-to-node networking, download access, TLS certs, and auth config. Never load an old cluster's system keyspaces into a new cluster outside a proven runbook.

**Step 3 — Restore data.** Choose a version-compatible method: restore SSTables onto prepared nodes/clusters per compatible workflow, or create schemas on a new cluster and **stream SSTables using tools like `sstableloader`** where appropriate. Execute real commands only after checking **your exact Cassandra version's** documentation, folder/table-ID layouts, and required SSTable list. Keep a manifest of loaded files to avoid gaps or duplicates.

**Step 4 — Restore and verify consistency.** Wait for the cluster to stabilize operationally, check node/token ownership, verify replica counts per RF, and apply target CL on verification queries. **Repair** may be needed at the right stage to resolve replica drift, yet it is not an auto-fix for bad deletions; never run repair blindly before knowing what data needs recovering.

**Step 5 — Verify data.** Reconcile `event_id`/`order_id` and fields, pre/post-cutoff records, `DELETE`/TTL rows, metadata/schema, and multiple token ranges. For query-denormalized tables, verify cross-table business invariants; Cassandra does not guarantee distinct query tables match after asynchronous snapshots.

**Step 6 — Verify the Java application.** Point **only a test application instance** at the restore cluster; verify auth, TLS, prepared statements, partition-key reads, new test writes, paged queries, and consistency levels. Watch timeouts, error rates, throughput, and latency. Confirm contact-point/DNS cutover procedures truly pick up the new config.

**Step 7 — Close out and clean up.** Archive acceptance timestamps, logs, and encountered issues; compare against targets. Tear down test environments only after preserving evidence and getting owner sign-off per workflow. Never alter or prune original backups just because the drill finished.

### 6.3. Illustrative Inspection Commands

Run only on the **drill cluster** with authorized privileges, checking syntax against your running release:

~~~bash
# Inspect topology, node states, and token ownership.
nodetool status

# Inspect snapshots on the source node; command is node-local.
nodetool listsnapshots

# When preparing a test snapshot on a source node:
# (must coordinate across all nodes to build a cluster-wide backup set)
nodetool snapshot -t drill_20261121T0800Z restore_drill

# Inspect node info after restore.
nodetool info

# Check whether compaction consumes resources during acceptance.
nodetool compactionstats

# Per-table statistics on supporting versions.
nodetool tablestats restore_drill.events_by_customer_day
~~~

**`nodetool snapshot`** can flush memtables per version behavior unless skip-flush is passed. It **does not upload files to object storage** and **does not take simultaneous snapshots across all nodes**. Record exit code, start/end times, target node, and tag per run. If data spans other keyspaces, capture the entire backup scope.

Loading SSTables into a target cluster varies widely by version, table ID, schema, and tooling. Production runbooks must contain **commands specifically tested for that cluster**; generic examples must never encourage copying snapshot files straight into live serving node data directories.

## 7. Post-Restore Verification with a Java Application

Manual CQL checks answer only part of the picture. The Java application must prove its driver connects to the right recovery cluster, prepares statements cleanly, and reads partition data at the chosen consistency level.

~~~java
import java.net.InetSocketAddress;
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

public class CassandraRestoreVerification {
    public static void main(String[] args) {
        UUID customerId = UUID.fromString(
                "11111111-1111-4111-8111-111111111111");
        LocalDate eventDay = LocalDate.of(2026, 11, 21);
        UUID expectedEventId = UUID.fromString(
                "22222222-2222-4222-8222-222222222222");

        // Switch contact point/DC to the RECOVERY CLUSTER, never production.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement query = session.prepare(
                "SELECT event_id, order_id, event_type, amount " +
                "FROM restore_drill.events_by_customer_day " +
                "WHERE customer_id = ? AND event_day = ? LIMIT ?");

            ResultSet result = session.execute(
                query.bind(customerId, eventDay, 100)
                     .setConsistencyLevel(
                         DefaultConsistencyLevel.LOCAL_QUORUM));

            boolean found = false;
            for (Row row : result) {
                if (expectedEventId.equals(row.getUuid("event_id"))
                    && "ORDER_CREATED".equals(row.getString("event_type"))
                    && row.getBigDecimal("amount")
                          .compareTo(new java.math.BigDecimal("120.50")) == 0) {
                    found = true;
                    break;
                }
            }
            if (!found) {
                throw new IllegalStateException(
                    "Expected data not found after restore");
            }
            System.out.println("PASS: sample event has expected keys and values");
        }
    }
}
~~~

This snippet uses **Java Driver 4.x** and the test data from Section 5. **`LOCAL_QUORUM`** works only when enough replicas exist in the local DC; on a single-node drill cluster, match RF/CL appropriately and document differences from production. **`LIMIT 100`** and one sample record do not prove full recovery; combine with multi-partition lists and owner-supplied invariants.

Additional verification should cover:

- **New test reads and writes:** only after validating recovered data, test writes on a dedicated test partition—never overwrite evidence records.
- **Timeouts / error rates:** connection failures, unavailable exceptions, read/write timeouts, auth/TLS failures.
- **Driver metadata:** prepared queries, routing keys, and schema changes; ensure no stale session still points to production.
- **Business integrity:** order counts per customer/day, monetary totals, order states, and cross-references across denormalized tables.
- **Replica synchronization:** read at target CL; verify replica states and repair when required by runbook.

## 8. Timing RTO by Phase: Numeric Example

**Hypothetical scenario:** simulated total cluster loss at **09:00 UTC**; clean backup holds an **application cutoff confirmed at 08:40 UTC**. Backup upload completed at 08:50 UTC with all components intact. Pre-drill targets: **RPO ≤ 30 minutes, RTO ≤ 120 minutes**.

| Milestone | UTC Timestamp | Interpretation | Phase Duration |
|---|---|---|---:|
| T0 | 09:00 | Service impact begins | — |
| T1 | 09:06 | Alert fires; on-call confirms | 6 minutes |
| T2 | 09:18 | Select 08:40 backup and launch runbook | 12 minutes |
| T3 | 09:40 | Recovery cluster and access permissions ready | 22 minutes |
| T4 | 10:12 | File downloads + checksums finish | 32 minutes |
| T5 | 11:04 | SSTables, schema loaded; nodes readable | 52 minutes |
| T6 | 11:40 | CQL/Java and data reconciliation accepted | 36 minutes |
| T7 | 12:00 | Simulated traffic cutover complete; test service active | 20 minutes |

Results:

~~~text
Cutoff-based RPO = 09:00 - 08:40 = 20 minutes
Drill RTO        = 12:00 - 09:00 = 180 minutes = 3 hours

RPO <= 30 minutes target   → MET if cutoff/reconciliation proven
RTO <= 120 minutes target  → NOT MET; exceeded by 60 minutes
~~~

**Interpretation:** 08:50 is upload completion, not data cutoff. For writes after 08:40, reconcile ACKed pre-incident event IDs to count **actual missing events** and replay sources. If the snapshot lacks proof of a uniform cutoff, report only **estimated RPO** with explicit uncertainty.

Because T7 is a **simulated traffic cutover**, reports must label it **drill RTO under stated conditions**. Unverified dependencies still remain—such as production DNS TTLs, KMS access during primary-region loss, multi-tens-of-TiB download throughput, and Java clients across multiple networks.

### 8.1. Reading Bottlenecks from the Timeline

In this example:

- **T4 → T5 = 52 minutes:** longest data-loading stage. Causes may include bandwidth, SSTable counts, disks, streaming, compaction, or topology.
- **T5 → T6 = 36 minutes:** slow verification; may lack automated fixtures, sample queries, or ready approvers.
- **T2 → T3 = 22 minutes:** infra/permissions bring-up; improvable via IaC, pre-validated images, and standby decryption access.

Never jump to conclusions solely from duration numbers. Cross-check CPU, disk throughput/latency, network bandwidth, cluster status, driver metrics, logs, and cgroup/OOM events to pinpoint root causes. Then pick **one or more accountable improvements with verification steps**, rather than blindly cranking thread concurrency without measuring resources.

## 9. Drill Record Sheet and Evidence

Every drill needs a **unique record** carrying an ID, runbook version, and full timestamps. Template:

~~~yaml
drill_id: "cassandra-restore-2026-11-21-01"
scenario: "loss-of-primary-cluster"
environment: "isolated-restore-cluster"
runbook_version_used: "v1.4"
owner_role: "database-oncall"
application_owner_role: "orders-service"
scope:
  keyspaces: ["restore_drill"]
  cassandra_version: "<actual-version>"
  local_datacenter: "dc1"
backup:
  backup_id: "<verified-backup-id>"
  status: "COMPLETE"
  cutoff_utc: "2026-11-21T08:40:00Z"
  uploaded_utc: "2026-11-21T08:50:00Z"
  manifest_checksum: "<verified-digest>"
  schema_location: "<reference>"
targets:
  rpo_minutes: 30
  rto_minutes: 120
measured:
  impact_started_utc: "2026-11-21T09:00:00Z"
  detected_utc: "2026-11-21T09:06:00Z"
  decision_utc: "2026-11-21T09:18:00Z"
  environment_ready_utc: "2026-11-21T09:40:00Z"
  download_verified_utc: "2026-11-21T10:12:00Z"
  data_loaded_utc: "2026-11-21T11:04:00Z"
  application_validated_utc: "2026-11-21T11:40:00Z"
  simulated_traffic_ready_utc: "2026-11-21T12:00:00Z"
  rpo_estimate_minutes: 20
  rto_drill_minutes: 180
validation:
  token_coverage: "verified"
  schema_compatible: true
  backup_integrity: "verified"
  business_invariants: "passed-for-defined-fixtures"
  production_cutover_tested: false
result: "PARTIAL_FAIL_RTO"
findings_reference: "<ticket-or-document>"
next_drill_due: "<approved-date>"
~~~

This YAML is an **illustrative team-authored record**, not Cassandra configuration and not required in any special cluster file. Replace versions, IDs, timestamps, outcomes, and roles with real observed figures. Never embed access tokens, passwords, or private keys in the record.

A good record includes **supporting evidence**: manifest checksums, command logs with exit codes, timestamped metric screenshots, reconciled row/invariant lists, blocker tickets, config changes, and acceptance sign-offs. Restrict access to evidence by sensitivity, and scrub customer data from logs.

## 10. Updating the Runbook After the Drill

A **runbook** must contain steps concrete enough for a different on-call engineer to execute under incident pressure—not merely theoretical prose. After the drill, the owner updates it based on recorded failures and evidence.

### 10.1. Suggested Runbook Structure

| Runbook Section | Required Contents |
|---|---|
| **Purpose and triggers** | Incident types, when to restore vs. replace node/repair, in-scope systems |
| **Roles and authority** | Incident commander, Cassandra on-call, Java service owner, security, approver |
| **Pre-run inputs** | Cluster/version/DC, keyspaces, snapshot/backup IDs, cutoff, manifest, schema, KMS rights, RPO/RTO |
| **Safe abort gates** | Criteria rejecting incomplete backups, bad checksums, schema mismatches, missing keys, or missing replicas |
| **Verified commands and flags** | Exact for Cassandra/JDK version, placeholders, target hosts, expected exit codes |
| **Per-step evidence** | T0–T7, logs, metrics, checksums, query/invariant outputs, and sign-offs |
| **Traffic cutover / rollback** | Driver/secret/DNS/TLS configs, write-stop plan, rollback, and post-cutover tests |
| **Environment differences** | Smaller data scale vs. production, RF/CL, storage, network, unsimulated KMS regions |
| **Postmortem and lifecycle** | Drill date, outcome, open issues, owners, due dates, new runbook version |

### 10.2. Example Runbook Revision by Root Cause

**Finding:** at T3, the drill team lost 15 minutes because bucket read credentials and KMS permissions had expired.

**Before revision:**

> Download snapshot from object storage and restore onto the cluster.

**After revision:**

1. Before drills and periodically ahead of incidents, test that the recovery role can **list, read objects, and decrypt** a canary file in the target domain.
2. Document **role name, grant workflow, activation prerequisites, and escalation channel** in the runbook. Never store secrets directly.
3. Prior to T4, verify manifests alongside decryption access; if blocked beyond threshold, escalate and switch to fallback backups/roles.
4. Add milestone **T3a — decryption permissions ready**, with timestamp and evidence.
5. Assign a concrete ticket to the IAM/KMS owner and re-verify with a short mini-drill after fixing.

This change directly addresses an observed blocker. **A revised runbook that has not been re-tested** is merely a hypothesis of improvement.

### 10.3. Versioning, Reviews, and Re-Drill Cadence

When publishing a new runbook version, record:

~~~text
Version: v1.5
Change: added pre-restore bucket/KMS permission check
Reason: 2026-11-21 drill uncovered a 15-minute delay
Owner: database-oncall + security/IAM owner
Verification: tested canary file decryption and manifest download in recovery domain
Status: pending validation / verified
Rollback: revert to last verified procedure if the new step causes issues
Next review date: per operations team policy
~~~

Drill cadence should reflect **committed RPO/RTO, system change velocity, and recovery-failure impact**. For instance, run frequent tabletops, monthly/quarterly selective restores, and full drills after major Cassandra/JDK, topology, backup service, IAM/KMS, or Java driver upgrades. This is a **scheduling suggestion**, not a mandatory frequency for every organization.

## 11. Cassandra-Specific Failures Often Surfaced During Drills

### 11.1. Backup Missing Token Ranges or Nodes

RF = 3 does not mean one node holds 100% of a keyspace's data. Snapshotting only node A can omit many token ranges entirely.

**Detection:** reconcile manifests against node/token ownership and test widely distributed partitions. **Fix:** fix snapshot/copy jobs to guarantee full data coverage per backup design, then re-drill.

### 11.2. Incompatible Schema, Table ID, or SSTable Format

SSTables bind to a specific table/schema/version; restoring onto another cluster with mismatched table IDs, UDTs, column types, or formats can fail loading or yield unpredictable results.

**Detection:** inspect restore tool logs, version info, CQL schema, and table names/IDs in manifests. **Fix:** keep schema/config paired with backups and use version-compatible restore/streaming workflows—never rename folders/SSTables arbitrarily to mask errors.

### 11.3. Data Deleted Before Cutoff Reappears

Restoring an old snapshot and mixing it improperly with newer writes can leave valid `DELETE` tombstones missing, resurrecting deleted data. TTLs, **`gc_grace_seconds`**, and repair timing affect this.

**Detection:** include `DELETE`/TTL fixtures and verify the *absence* of rows that should stay deleted. **Fix:** restore in isolation at a clean cutoff, apply proper replay/reconciliation mechanics, and never shrink `gc_grace` or force compaction as a shortcut.

### 11.4. Snapshots Exist Yet Off-Domain Backups Are Incomplete

**`nodetool snapshot`** typically creates local hard links; all SSTable components, schemas, and metadata must copy to safe storage with checksum checks. Missing one file often surfaces only when restore is actually attempted.

**Detection:** check manifests, node/table/file counts, checksums, and decryption rights in the target domain. **Fix:** mark `COMPLETE` only after verifying every component, and never let retention purge earlier clean backups when a new job fails.

### 11.5. Trying to Use Repair to "Recover" an Accidental DELETE

Repair syncs replica state per Cassandra mechanics. It does not know whether a deletion was a business mistake, and cannot roll back to old snapshots when no backup exists.

**Detection:** data is deleted across all replicas with no historical copy remaining. **Fix:** pull pre-error state from independent backups or business event logs, then restore in a controlled manner.

### 11.6. Target Cluster Has Data Yet the Java Service Still Errors

A cluster may hold all SSTables while the Java app still uses stale contact points, wrong local DC, unsynced schema, unrefreshed prepared statements, invalid TLS/ACLs, or partition-key queries returning wrong-cutoff data.

**Detection:** run tests from the application environment itself, checking connectivity, consistency, queries, and latency. **Fix:** add driver configuration and end-to-end validation steps to the runbook—never stop at nodes being **`UN` (Up/Normal)**.

## 12. Measuring Capacity and Background Work During Restore

Cassandra may continue running **compaction, repair, streaming, and replica sync** after initial data loads. These background tasks affect RTO and real service health.

| Activity | Metrics to Watch | Risk to RTO |
|---|---|---|
| Downloading from backup store | Throughput, checksums, network latency, retries | Network/KMS/bandwidth limits; missing files |
| SSTable loading / streaming | Load rate, file count, disk throughput, pending tasks | Large data volumes, many SSTables, CPU/disk saturation |
| Compaction | Backlog, write amplification, free disk, latency | Read/write contention, running out of temp disk |
| Repair | Task status, progress, network/disk, replica health | Extends convergence phase; must not mask bad data |
| JVM, heap/off-heap, and OS | GC pauses, RSS, MemAvailable/page cache, OOM | Node restarts/OOM, high latency |
| Java clients | p95/p99 latency, timeouts, retries, connection counts, CL | Service unready even though cluster booted |

Test results must record **data volume and matching hardware specs**. Restoring 1 GiB on a test box does not linearly extrapolate to promising RTO for 30 TiB across multi-region production. Make preliminary estimates from measured throughput, add overhead, and confirm with representative-scale drills.

## 13. Pass/Fail Criteria and Follow-Up Actions

A drill **PASSES** when **all conditions within the declared scope** are met:

- Backups are valid, complete, and decryptable via independent scenario-appropriate procedures.
- Schemas/tables/partitions restore accurately; fixtures, TTL/`DELETE`s, and business invariants pass thresholds.
- Cassandra satisfies the application's required replication/consistency levels in the target environment.
- Java services read and write cleanly against the target cluster within error/latency acceptance criteria.
- RPO and RTO measured per agreed definitions are **both within limits**.
- Evidence, timelines, uncertainties, and test limitations are recorded.

Mark **PARTIAL** or **FAIL** if any part went untested or any mandatory criterion failed. Reports must separate data bugs, process gaps, performance bottlenecks, and test coverage holes.

In Section 8's example, **cutoff RPO achieved 20 minutes**, yet **drill RTO of 180 minutes exceeded the 120-minute target**, yielding **FAIL on RTO**. Create action items with owners, due dates, and verification checks:

| Finding | Action | Post-Fix Verification |
|---|---|---|
| T4 → T5 took 52 minutes | Profile download/load rates, SSTable counts, disk/network, controlled parallelization | Re-measure at realistic backup volume/topology |
| T5 → T6 took 36 minutes | Automate sample partition checks, event IDs, and Java invariants | Run test suite; measure false-positive rate and runtime |
| T2 → T3 took 22 minutes | Pre-stage IaC/images, KMS grants, and target networking | Provision from scratch in the next drill |

Never mark "updated documentation" as mitigating risk. Close issues only once post-fix drill evidence proves the outcome.

## 14. Hands-On Exercises

### Exercise 1 — Upload Timestamp vs. Data Timestamp

A complete snapshot has a verified cutoff at **01:00 UTC** and finishes uploading to an independent domain at **01:25**. The cluster fails at **04:10**. No incremental or commitlog archive exists.

**Questions:** What is the cutoff-based RPO? Can 01:25 be used as the recovery point?

**Hint:** **3 hours 10 minutes (190 minutes).** Upload completion does not prove the backup holds data up to 01:25. Reconcile valid writes after 01:00 and replay sources if any.

### Exercise 2 — Calculating RTO with Proper Scope

A drill logs these timestamps:

~~~text
10:00 - incident begins
10:08 - detected
10:24 - recovery decision made
10:50 - target environment ready
11:35 - SSTables finish loading
12:20 - app and data accepted
12:30 - serving access path opened
~~~

**Questions:** What is RTO from incident onset until serving readiness? If someone reports only "restore took 45 minutes" from 10:50 to 11:35, what is omitted?

**Hint:** **150 minutes.** The 45-minute figure covers data loading only, omitting detection, decision-making, cluster provisioning, validation, and traffic cutover.

### Exercise 3 — Cluster UP Is Not Enough Evidence

After restore, **`nodetool status`** shows every node **`UN`**, yet the Java service reports **`LOCAL_QUORUM`** read timeouts and misses several order IDs.

**Questions:** Can PASS be declared? What should be checked next?

**Hint:** No. Check RF/DC/rack, CL, token coverage, schema, per-partition data, backup manifests, disk/network, driver connections, and order IDs written before cutoff. `UN` status does not guarantee accurate data.

### Exercise 4 — Writing a Measurable Runbook Revision

A drill missed RTO because finding someone with backup decryption permissions took 25 minutes.

**Requirement:** Write a concrete change covering pre-recovery permission checks, owner, evidence, and how to verify in the next drill.

**Hint:** Add periodic preflights for restore roles, KMS, secret paths, and escalation; record permission-verification time, IAM owner, and ticket link. Execute from a role-authorized recovery account and measure T3a.

### Exercise 5 — Choosing the Right Mechanism

Two incidents occur:

- **A:** One node fails, RF = 3, and surviving replicas hold the newest data.
- **B:** An erroneous `DELETE` replicated to all three replicas.

**Questions:** When do you prioritize replace/streaming, and when do you need backups?

**Hint:** A: replace the node, stream from replicas, and verify consistency. B: requires a clean pre-`DELETE` backup or independent historical source; repair only syncs copies and never undoes bad operations.

## 15. Pre-Declaration Checklist for "Recovery Ready"

- [ ] Defined **incident type, failure domain, keyspace/table scope**, and drill realism tier.
- [ ] Have one or more **COMPLETE** backups with full node/token-range coverage, checksums, schema, and decryption keys.
- [ ] Recovery permissions work assuming the primary domain is gone; download/decryption tested.
- [ ] Isolated environment matches Cassandra/JDK versions with sufficient storage/network.
- [ ] Reconciliation fixtures cover **partition keys** including `UPDATE`, `DELETE`, TTL, and multiple token ranges.
- [ ] Runbook contains commands verified for exact version, target hosts, owners, abort gates, and rollback.
- [ ] Measured **T0–T7**, separating data cutoff from upload completion and flagging simulated milestones.
- [ ] CQL and Java services tested at target **consistency levels** with business reconciliation.
- [ ] Evaluated compaction/repair/streaming impact and resource limits on recovery duration.
- [ ] Recorded **measured RPO/RTO**, transparent PASS/FAIL verdict, and supporting evidence.
- [ ] Every finding has an owner, priority, due date, and re-test plan.
- [ ] Runbook version/review incremented and next drill scheduled per operational policy.

## 16. Summary

Cassandra recovery drills test **data, infrastructure, applications, and people together**. Replicas survive node failures without undoing erroneous `DELETE`s; snapshots hold SSTables at a point in time yet must be preserved outside the failure domain; backups have value only once data, schemas, keys, and loading workflows are all proven.

A strong drill picks the right scenario, locks RPO/RTO upfront, restores into isolation, verifies data by partition key, and tests Java applications at the intended consistency level. Every milestone is timed against targets; findings translate into **owned runbook revisions with re-test evidence**. Only then does "having backups" move closer to "restoring service within acceptable time."
