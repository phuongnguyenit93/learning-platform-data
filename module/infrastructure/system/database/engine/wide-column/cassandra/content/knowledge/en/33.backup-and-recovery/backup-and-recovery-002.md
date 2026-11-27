# Distinguishing Replicas, Snapshots, and Off-Failure-Domain Copies

> **Chapter:** Backup and Recovery  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Scope:** Apache Cassandra — distributed wide-column database; connecting partition keys, query-driven table design, consistency levels, CQL, replication, compaction, repair, troubleshooting, and Java applications.

## 1. Why Does Replication Not Equal Backup?

Suppose an order system uses Cassandra with **replication factor (RF) = 3**. An operator accidentally runs a command that deletes the wrong data. Within seconds, all three replicas receive the same delete operation. The cluster still has three synchronized copies as designed, yet **all three simultaneously no longer contain the valid data version the application needs**.

If a **snapshot** was taken before the incident, remained undeleted, and was transferred to a **storage store independent of the cluster**, the operations team has a path to restore the older data. If only the three live replicas exist, raising the consistency level or running repair cannot automatically recreate a validly deleted record across all replicas.

The three mechanisms answer three different questions:

1. **Replica:** can data continue serving when one or more nodes, disks, or failure domains go down?
2. **Snapshot:** is a prior data state preserved before an incident for restoration?
3. **Off-failure-domain copy:** when the entire cluster, infrastructure region, operator account, or admin credentials fail, does the backup still exist and remain accessible?

This lesson aims to clearly distinguish these three concepts, choose among them by **incident type**, understand their impact on **RPO/RTO**, practice basic snapshot operations, and build a verifiable backup/restore workflow.

## 2. What Is a Failure Domain?

A **failure domain** is a set of resources that can be affected together by a single cause: a disk, a host, a rack, an availability zone (AZ), a datacenter, a region, a cloud account, a key management system, or an operator's permission set.

| Failure Domain | Example | Corresponding Measure |
|---|---|---|
| Disk / node | SSD failure, JVM fails to start, machine powered off | Replicas on other nodes; replace node and stream/synchronize data |
| Rack / AZ | Power or network outage in a zone | Place replicas across different racks/AZs when topology supports it |
| Datacenter / region | Widespread outage, network or storage loss across a whole region | Data/cluster copy in another infrastructure domain; traffic failover plan |
| Logical / application | Wrong CQL DELETE, TRUNCATE, bug overwriting data, misconfigured TTL | Versioned backups from **prior to** the bad operation and a recovery procedure |
| Admin privileges / security | Account compromised, deleting both the cluster and backup bucket in the same account | Copies with isolated permissions, encryption keys, retention, and delete controls |
| Combined disaster | Region lost while a snapshot is in progress or backup upload is incomplete | Multiple **completed and verified** recovery copies in an independent domain |

**"Outside the failure domain" is always scenario-dependent:** a replica in another AZ can survive an AZ outage but remains exposed to logical data deletion. An object storage bucket in the same region isolates disk failures but falls short if the goal is surviving a full-region outage. A copy in another region that shares the same delete permissions and inaccessible encryption keys is still not administratively independent.

## 3. Replica: Serving Ongoing Availability and Fault Tolerance

### 3.1. How Does Cassandra Distribute Replicas?

The **partition key** determines a token, and the replication strategy plus topology choose the nodes storing that partition's data. Within a datacenter, multiple replicas are logical copies of the same partition, not shards split across replicas.

Keyspace illustration:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};

CREATE TABLE IF NOT EXISTS shop.orders_by_customer_month (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

**Assumption:** datacenter **dc1** has enough nodes/racks suitable for RF = 3; production requires properly configuring snitch, topology, and actual node counts. Querying by **(customer_id, order_month)** locates a partition, while **created_at/order_id** orders orders within the partition. Month bucketing is just an example and must be adjusted if a single customer has too many orders.

With replicas distributed across racks/AZs, a node that loses local data can be replaced and receive data from surviving replicas through standard procedures such as bootstrap/replace/streaming or rebuild depending on the situation. **Never take SSTables from a single arbitrary node and assume they contain the entire keyspace.**

### 3.2. How Does Consistency Level Relate?

On a write, the coordinator contacts replicas and waits for enough responses per the request's **consistency level (CL)**. With RF = 3 in a local datacenter:

- **ONE:** typically requires one replica acknowledgment; latency/availability may be better, but a recent write is not guaranteed to be acknowledged on other replicas if an immediate failure occurs.
- **LOCAL_QUORUM:** requires a majority of replicas in the local DC, i.e., **2/3**; fits many read/write workloads requiring quorum overlap within the local DC.
- **ALL:** requires responses from all involved replicas; availability degrades when a node fails.

Java driver 4.x example:

~~~java
BoundStatement write = preparedInsert.bind(
        customerId, orderMonth, createdAt, orderId, "PAID", amount)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(write);
~~~

This snippet assumes a program with **session**, **preparedInsert**, and variables already initialized. CL governs response requirements—it **does not create versioned backups**. A valid **UPDATE** or **DELETE** statement is replicated as well.

### 3.3. Replicas Do Not Protect Against All Data Loss

- **Wrong delete/overwrite:** bad operations are replicated just like valid ones.
- **TTL:** values expire per TTL across replicas; there is no "rewind time" feature.
- **Application bugs:** writing malformed data or wrong partition keys propagates to replicas.
- **Simultaneous failures:** if too many replicas in a shared failure domain are lost before another copy holds the data, recovery from replication alone may be impossible.
- **Security incidents:** anyone with cluster deletion rights can wipe all replicas.

**Repair** reconciles and synchronizes data differences among replicas via Cassandra's anti-entropy mechanism; it is **not a backup** and can even help propagate valid delete operations to missing replicas. **Hints** can deliver missed writes within operational limits, but likewise do not store history capable of replacing backups.

## 4. Snapshot: A Point-in-Time Copy of Each Node's SSTables

### 4.1. What Is a Cassandra Snapshot Actually?

Cassandra persists data in immutable **SSTables**. When creating a snapshot, Cassandra retains references to the set of SSTable files at that moment, typically as **hard links** on the node's filesystem rather than immediately copying all bytes to another disk.

Usually **nodetool snapshot** flushes relevant memtables before creating the snapshot so in-memory data reaches SSTables; options such as **--skip-flush** (if supported by the version) alter the scope of captured data. Therefore, check your exact version and flags; **a snapshot does not automatically carry commitlog contents to provide complete point-in-time recovery**.

~~~mermaid
flowchart TD
    M["Memtable with unflushed writes"] -->|Default snapshot triggers flush depending on version| S["Immutable SSTable"]
    S --> L["Snapshot: hard links to SSTable files"]
    S --> C["SSTable actively used by Cassandra"]
    L --> D["Still resides on node storage"]
    L --> E["Copy to independent backup store"]
    E --> V["Verify and maintain retention"]
~~~

**What a snapshot actually protects:** later compaction may replace live SSTables, yet snapshot hard links keep the old bytes until the snapshot is cleared. A local snapshot can restore SSTable state prior to a later update/delete, **provided the snapshot files still exist and cover enough data to recover**.

**What a snapshot does not protect:** complete failure of the disk/volume holding the snapshot, deletion of the node/volume, missing nodes/snapshots needed to restore the keyspace, missing schema, or lost decryption access. Local snapshots can also be wiped by cleanup commands or someone with host control.

### 4.2. CQL and nodetool Illustration

Example in a test environment where keyspace **shop** already exists:

~~~bash
# On a Cassandra node, create a snapshot with a specific tag.
# Do not run on just one node if the goal is cluster-wide backup.
nodetool snapshot -t shop_20261121T0400Z shop

# View snapshots on this specific node.
nodetool listsnapshots
~~~

**Operational meaning:** the first command creates a local snapshot on **the node nodetool connects to**. The second lists local snapshots and their associated disk usage. To back up a distributed keyspace, you must **orchestrate snapshots across all nodes/replicas holding data in the target scope**, or follow a proven full token-range coverage plan. Do not assume "running on one node captures the whole cluster."

Depending on the Cassandra version, the data path typically contains the table directory with its identifier and a **snapshots/<tag>** subdirectory. **Do not hard-code paths** when building a backup system: use the node's configured data directories and metadata, then verify the actual files.

### 4.3. Is a Snapshot a Simultaneous Cluster-Wide Image?

**Not by default.** Snapshots on individual nodes are created at different instants. In-flight writes may be observed unevenly across nodes in time; a batch or sequence of business changes across multiple partitions does not become a cluster-wide transaction merely by sharing a snapshot tag.

If the problem requires a **business-consistent recovery boundary**:

1. Identify the related keyspaces/tables and cross-table consistency requirements.
2. If feasible, pause/quiesce business writes or design an application **barrier/cutoff** and record a clear marker.
3. Coordinate snapshots across nodes, confirm **all** succeed, and record each node's timestamp.
4. Validate data after restore using business invariants—do not just run a single SELECT.

**Actual RPO** depends on the boundary supported by this process and what data is confirmed in the backup; **matching tags do not prove system-wide atomic snapshots**.

### 4.4. Snapshot Disk Usage and Compaction

Hard-link snapshots are fast to create initially, but **they are not free in disk space**:

- When compaction writes new SSTables, old SSTables still referenced by a snapshot cannot be freed from disk as they normally would.
- Uncleaned stale snapshots can fill up a disk even when live data volume is flat.
- "Total" size listed per file may differ from unique physical blocks on disk because hard links share underlying blocks.
- After snapshots have been moved outside the failure domain and **verified**, enforce controlled local retention/cleanup policies instead of keeping them indefinitely on the node.

## 5. Off-Failure-Domain Copy: Backups That Survive Larger Outages

A copy only truly meets the "off-failure-domain" goal when **the risk under consideration cannot destroy or disable both the source data and the backup via the same failure mode**.

Architecture example:

~~~mermaid
flowchart LR
    subgraph DC["Cassandra cluster in primary datacenter/region"]
        A["Replica 1"]
        B["Replica 2"]
        C["Replica 3"]
    end
    A --> SA["Node 1 snapshot"]
    B --> SB["Node 2 snapshot"]
    C --> SC["Node 3 snapshot"]
    SA --> U["Copy, manifest, and checksum workflow"]
    SB --> U
    SC --> U
    U --> O["Object storage in independent infrastructure domain"]
    O --> P["Retention/versioning/immutability"]
    O --> K["Tested decryption keys and restore permissions"]
    O --> T["Isolated test recovery cluster"]
~~~

An off-failure-domain store may be object storage, a backup service, or a dedicated repository engineered for recovery requirements. Factors to evaluate together:

| Isolation Layer | Verification Question |
|---|---|
| **Infrastructure** | Does the backup share the same host/volume/AZ/region as the cluster? Where must it live for a full-region loss? |
| **Identity/permissions** | Can a user or automation able to delete the database also delete all backups? |
| **Encryption/keys** | If KMS/secrets in the primary region are lost or revoked, can backups still be decrypted? |
| **Lifecycle** | Are versioning, retention, WORM/immutability, or non-deletable holds enforced per policy? |
| **Completeness** | Are all SSTables, schema, config, node/token lists, auxiliary files, and timestamp logs present for restore? |
| **Restorability** | Has the backup actually been downloaded, restored, and business-tested in an independent domain? |

**Copying snapshot files to a bucket is not the end of backup.** You must verify file counts and checksums, readability, encryption keys, metadata, and the ability to rebuild schema/cluster. A backup can "succeed" in upload terms yet remain unrestorable due to missing table schema or SSTable version mismatch.

### 5.1. Off-Site vs. Off-Domain

"Off-site" usually emphasizes **a different storage location**. "Outside the failure domain" requires isolating the corresponding risk; sometimes that demands separate admin accounts, delete permissions, keys, and network paths.

- A backup in a bucket **within the same account where an admin can delete both cluster and bucket** may survive disk failure but is weak against account compromise.
- A backup replicated to another region that **relies solely on a KMS key hosted in the failed region** may become unreadable during a disaster.
- An immutable backup protects against unauthorized deletion/modification, yet without restore testing it may still lack required data or config.

No single storage layout fits every organization; choose based on **scenarios to withstand, RPO/RTO, and cost**.

## 6. Direct Comparison: Replicas, Snapshots, and Off-Failure-Domain Copies

| Criterion | Replica | Local Snapshot | Off-Failure-Domain Copy |
|---|---|---|---|
| **Primary purpose** | Keep serving when replicas fail | Preserve SSTable versions at a checkpoint | Recover when primary data/nodes/domain are destroyed |
| **How is it created?** | Replication strategy + Cassandra read/write path | Snapshot of a node's SSTables | Transfer snapshots and metadata to an independent store; optionally combine incremental/PITR |
| **Data state** | Evolves with current writes/deletes | Frozen contents of captured files | Preserved copy per policy and recovery checkpoint |
| **Survives single-node loss?** | Yes, if valid replicas and CL conditions remain | No if the snapshot sits on the lost node | Yes, if backups have enough data to rebuild |
| **Survives bad delete across replicas?** | No | Potentially, if taken before and still intact | Potentially, if a clean pre-incident copy is retained |
| **Survives full-region loss?** | Only if replicas exist in a surviving domain with proper failover | No if stored only in the failed region | Yes if location, permissions, keys, and restore are all independent |
| **Instant self-recovery?** | Not entirely; a node may need replace/rebuild/repair | No; requires a restore procedure | No; requires download, schema/cluster build, data load, validation |
| **Version history?** | Not a versioning mechanism | Yes per retained snapshot/tag | Yes per backup retention policy |
| **Remaining risks** | Logic bugs, domain-wide failures, unreplicated writes | Node disk loss, incomplete snapshots, disk full | Stale/corrupted backups, missing keys, wrong permissions, missed RTO |

**Separate the questions:** "Are any nodes left to serve?" belongs to **replication/failover**. "What state do we roll back to?" belongs to **backup/restore**. "Does the rollback copy survive the same disaster as the primary system?" belongs to **failure-domain design**.

## 7. RPO and RTO: Design Selection Criteria

- **RPO (Recovery Point Objective):** maximum acceptable time-measured data loss upon recovery. For instance, RPO = 1 hour means the organization aims to restore data no older than 1 hour before the incident under committed scope and conditions.
- **RTO (Recovery Time Objective):** how quickly the system must return to serving state after an incident.

With a full snapshot every 24 hours and no mechanism to capture/restore changes between snapshots, actual RPO **can be roughly 24 hours or more** if the latest copy is incomplete or corrupted. Having **3 replicas** does not make backup RPO equal 0. If the system remains operational on surviving replicas after a single failure, **restoring from backup is usually unnecessary**; evaluating availability/failover differs from historical data recovery.

### 7.1. Example of a Policy with Concrete Numbers

Suppose:

- Full snapshots across all relevant nodes start daily at **02:00 UTC**.
- Upload to the backup store finishes and verifies at **02:30 UTC**.
- At **16:00 UTC**, an accidental delete propagates to all replicas.
- The latest clean copy is that day's backup, with its business cutoff recorded at capture time.

If you restore solely from this copy, changes acknowledged **after the cutoff** until 16:00 can be lost. **Do not treat 02:30 as having complete data up to 02:30** just because the upload finished then. If the valid cutoff is 02:00, potential data loss may be around **14 hours**.

Tightening RPO requires considering more frequent snapshots, incremental backups, and/or **controlled commitlog archiving and replay** up to an appropriate point. Point-in-time recovery (PITR) requires a **continuous, ordered, and compatible chain of baseline backups + subsequent changes**, not merely flipping a flag.

RTO includes:

~~~text
Detection + decision-making + recovery resource provisioning
+ schema/configuration and data restoration
+ replay/sync/rebalancing as needed
+ consistency validation and application testing
+ traffic cutover and monitoring
= total recovery time
~~~

Backup size, download speed, node count, SSTable count, network, disk, compaction, and repair can stretch RTO far beyond the time needed to copy a few test files.

## 8. What Roles Do Incremental Backups and Commitlog Archiving Play?

### 8.1. Incremental Backups Do Not Replace a Baseline

In Cassandra versions supporting **incremental_backups**, this feature stores local hard links/copies for **newly flushed or streamed SSTables** according to that version's mechanics. It does not mean every INSERT statement is continuously exported as a standalone backup, nor does it guarantee full history recovery without a baseline, retention, and an unbroken chain.

A typical recovery chain requires:

1. A **baseline snapshot** with a clear timestamp and inventory.
2. Valid **incremental SSTables** generated after the baseline, transferred to an independent store.
3. Metadata on ordering/checkpoints, schema, and tombstone/TTL rules to reconstruct data accurately.
4. Restore testing ensuring required data is neither missing nor duplicated.

Incremental SSTables can also **grow disk usage rapidly** on a node because retained links block freeing old blocks, so they must be monitored and pruned upon offsite confirmation.

### 8.2. Commitlog Archiving and PITR

The commitlog records mutations to support write durability on a replica. **Commitlog archiving** (where supported by version/deployment) can ship segments to another store and enable replay during recovery. However:

- Segments must be saved **completely, in order, and verified**; archiving itself can lag.
- Replaying to the wrong cutoff can **replay the very erroneous deletion** you are trying to avoid; recovery timestamp/cutoff must be precisely chosen.
- Must match schema, topology, version, and restore mechanics; concrete recovery steps require a tested runbook.
- Never conflate a **node-local commitlog** with a cluster-wide business changelog having a single perfect global order.

**CDC (Change Data Capture)** is also not automatically a backup: it provides a configured change stream with disk/retention limits and requires sufficiently durable downstream storage/offsets to serve recovery. Achieving a small RPO requires verifying **maximum data loss when the backup pipeline itself fails**.

## 9. Periodic Backup Workflow from Cassandra

A reliable operational procedure should explicitly define **scope, checkpoints, completeness, and verification**.

### 9.1. Before Taking a Snapshot

1. Record **cluster name, Cassandra version, JDK version, partitioner, token/vnode topology, snitch, DC/rack, replication strategy**, and target keyspaces/tables.
2. Export **CQL schema** for keyspaces/tables along with schema version and configuration data needed for recovery. Never assume SSTables alone suffice to recreate tables.
3. Check for special data features such as counters, materialized views, secondary indexes, UDTs, TTLs, or LWT/transactional invariants to prepare a version-compatible restore method.
4. Define an **application cutoff** if a consistent business boundary is needed; coordinate with write flows.
5. Verify sufficient free disk space to create snapshots, hold hard links, and push data offsite without filling disks via backup schedules.

### 9.2. Creating Snapshots and Moving Off-Domain

~~~mermaid
flowchart TD
    A["Assign backup ID and target cutoff"] --> B["Record metadata and schema"]
    B --> C["Coordinate snapshots across required nodes"]
    C --> D{"Did all required nodes succeed?"}
    D -->|No| X["Mark backup incomplete; handle failure"]
    D -->|Yes| E["List SSTables, build manifest and checksums"]
    E --> F["Upload/sync to independent store"]
    F --> G["Re-verify checksums, read access, decryption keys"]
    G --> H{"Is the backup set restorable?"}
    H -->|No| X
    H -->|Yes| I["Mark COMPLETE and apply retention"]
    I --> J["Clean up local snapshots per procedure"]
~~~

Only when **all mandatory steps and verifications** succeed should a backup set be declared **COMPLETE**. A failed node must never be masked by successful uploads from the remaining nodes. For backups relying on specialized token-range coverage, you must have complete proof covering the corresponding data replicas.

At minimum, a backup set manifest should include:

~~~json
{
  "backup_id": "shop_20261121T0400Z",
  "status": "COMPLETE",
  "cluster": "shop-prod-example",
  "cassandra_version": "<actual-version>",
  "scope": ["shop"],
  "application_cutoff_utc": "<recorded-if-enforced>",
  "snapshot_started_utc": "<actual-time>",
  "snapshot_finished_utc": "<actual-time>",
  "nodes": [
    {
      "node_id": "<stable-node-identifier>",
      "dc": "dc1",
      "rack": "<rack>",
      "token_coverage": "<recorded>",
      "snapshot_tag": "shop_20261121T0400Z",
      "files": [
        {
          "path": "<relative-path-in-backup>",
          "size_bytes": 123456,
          "sha256": "<verified-hex-digest>"
        }
      ]
    }
  ],
  "schema_location": "<object-key>",
  "encryption_key_reference": "<key-id-or-recovery-metadata>"
}
~~~

This is an **illustrative internal manifest format**; Cassandra does not natively generate this exact JSON. Never store raw credentials or secrets in the manifest. If no application-enforced cutoff exists, explicitly record **"not guaranteed"** rather than fabricating a consistent boundary.

### 9.3. Verifying Backups Instead of Only Verifying Uploads

- **Files:** complete set of nodes, table IDs, SSTable components; sizes and cryptographic checksums match.
- **Metadata:** schema, token/partitioner/topology, and version data present to stand up a compatible cluster.
- **Security:** backups encrypted, restore read permissions functional, independent keys accessible.
- **Completeness:** backup set marked complete only after all mandatory components are verified.
- **Restorability:** periodically stand up a test cluster from backups; verify data, tables, sample partitions, and business invariants.
- **Timing:** measure download, load, startup, verification, and traffic cutover durations; compare against RTO/RPO.

A backup is considered **usable** only when backed by actual recovery evidence, not simply because the copy tool exited with code 0.

## 10. Choosing a Recovery Strategy by Incident Type

| Incident | Priority Action | When to Use Backups? |
|---|---|---|
| Single node lost, other replicas healthy | Replace/bootstrap/streaming via Cassandra procedures; verify replication and repair | When insufficient valid copies remain or historical recovery is required |
| One AZ lost, replicas remain in other AZs and CL is met | Serve from surviving replicas, recover node/rack, maintain topology | If lost data exceeds replica recovery capability |
| Entire region down, second independent DC valid | Execute failover plan to second DC, then rebuild lost region | If second DC lacks/corrupted data or an older state is required |
| Accidental replicated DELETE/UPDATE | Stop offending source; identify clean cutoff; controlled restore | **Requires pre-incident backup** or independent historical source |
| Accidental TRUNCATE | Halt writes; check auto-snapshot prior to TRUNCATE **if enabled in config** | Use intact snapshot or off-domain backup; never assume auto-snapshot always exists |
| Both nodes/volumes and local snapshots lost | Provision replacement infrastructure per runbook | Restore from off-domain backup containing schema, data, keys, and manifest |
| Primary admin account compromised | Isolate privileges, investigate, and build a trusted environment | Immutable copies/independent credentials with still-usable keys |

**Never arbitrarily restore old SSTables directly into a cluster accepting live writes.** Doing so can mix states from different points in time, cause schema mismatches, or **resurrect deleted data** if tombstones/TTLs, repair, and gc_grace are mishandled. The safe approach is usually **restoring into an isolated environment first**, verifying, and then choosing how to cut over or re-ingest data.

### 10.1. Restoring from Snapshots: Two Implementation Approaches

**Approach A — Restoring onto a compatible node/cluster:** prepare write-paused nodes per procedure, establish matching schema/table IDs and SSTable versions, place the required files in the proper directories, and invoke that version's SSTable loading/refresh procedure. Copying, startup/refresh, and repair depend on topology and version; **never treat a generic cp + restart as a universal runbook**.

**Approach B — Loading data into a new cluster:** create compatible keyspaces/tables and use streaming tools such as **sstableloader** (where supported by the version) or a controlled logical re-ingestion workflow. Loading into a new cluster favors **selective recovery** and pre-cutover validation, but requires budgeting for streaming time, duplicate handling, and schema compatibility.

In both approaches:

- Restore the exact target schema and replication settings; **never blindly transplant system keyspaces**, token ownership, or system tables across different clusters.
- Verify checksums, SSTable format, compression, UDTs, and table IDs; these cannot be altered arbitrarily.
- Check whether data written after the snapshot needs replay/import from another source.
- For deletes/TTLs, never blend old and new data while ignoring tombstone semantics, **gc_grace_seconds**, and repair state.
- Validate both data and application functionality before opening write traffic.

## 11. Short Runbook Example for an Accidental Deletion Incident

**Scenario:** at 15:30 UTC, a buggy Java service release triggers a DELETE affecting order data in keyspace **shop**. The delete has replicated, while an off-failure-domain backup is verified at a 14:00 UTC cutoff.

1. **Stop the source of corruption:** halt the faulty write/delete feature and isolate the offending application version; record detection time and earliest potentially affected timestamp.
2. **Preserve evidence and backups:** keep clean backups untouched, lock appropriate retention; do not prune snapshots or delete relevant logs.
3. **Determine scope:** affected tables, partition keys, DELETE/TTL type, start time, order counts, and valid post-cutoff changes needing preservation.
4. **Select recovery point:** the 14:00 cutoff is safely prior to deletion; clarify business requirements for new orders between 14:00 and 15:30.
5. **Stand up an isolated recovery cluster:** load schema and data from backup; verify version and topology; **never overwrite the production cluster directly**.
6. **Verify data:** reconcile order counts per customer/month, critical order IDs, business monetary totals, and transaction states; assess tombstones/TTL and replay if applicable.
7. **Reconcile post-cutoff data:** if needed, ingest valid events from an independent data source, outbox, or verified business log. Do not blindly replay the faulty DELETE.
8. **Controlled traffic cutover:** update app/driver configs and contact points after validating reads/writes, consistency, latency, and failover.
9. **Postmortem:** record actual RPO, actual RTO, and root cause; tighten permissions, destructive SQL/CQL testing, and bulk-delete alerting.

If no independent source exists for valid changes after 14:00, **transparently report the actual data loss** rather than claiming RPO = 0. Not all data lost in that window can be reconstructed from replicas once the deletion has propagated.

### 11.1. Spot-Checking Data with CQL and Java

For the example table:

~~~sql
SELECT created_at, order_id, status, amount
FROM shop.orders_by_customer_month
WHERE customer_id = ? AND order_month = ?
LIMIT ?;
~~~

The query binds **the full composite partition key**, matching the wide-column model, to inspect sample partitions after restore. Combine file/checksum checks with business-level invariants across many partitions rather than testing only a single row.

Condensed Java driver 4.x example for post-recovery reads:

~~~java
import java.net.InetSocketAddress;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public class VerifyRecoveredOrders {
    public static void main(String[] args) {
        UUID customerId =
            UUID.fromString("11111111-1111-4111-8111-111111111111");

        // Point to the approved RECOVERY / TEST cluster.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement read = session.prepare(
                "SELECT created_at, order_id, status, amount " +
                "FROM shop.orders_by_customer_month " +
                "WHERE customer_id = ? AND order_month = ? LIMIT ?");

            ResultSet rows = session.execute(
                read.bind(customerId, "2026-11", 100)
                    .setConsistencyLevel(
                        DefaultConsistencyLevel.LOCAL_QUORUM));

            rows.forEach(row ->
                System.out.println(
                    row.getUuid("order_id") + " " +
                    row.getString("status")));
        }
    }
}
~~~

This is an **illustrative check**, not a full recovery test suite. Replace contact points/DC, ensure replica counts satisfy LOCAL_QUORUM, and use a pre-incident sample set of customers/orders. Verify **orders that should exist yet went missing**, not only orders still found. A SELECT result alone does not confirm backups cover all token ranges.

## 12. Operational Health of Snapshots and Backups

To avoid the "backups configured, but no usable restore" trap, monitor:

| Signal | Purpose |
|---|---|
| Last **COMPLETE** backup and its true data timestamp | Know current RPO without confusing upload time with cutoff |
| Completeness of node count, table count, and token ranges in manifest | Detect backups missing parts of the cluster |
| Snapshot/flush errors, stalled snapshots | Detect node or scheduler failures |
| Backup duration and upload duration | Detect slow pipelines causing RPO drift |
| Checksum failures / missing schema / missing keys | Detect unrestorable backup sets |
| Local snapshot disk usage, free disk, compaction backlog | Prevent snapshot hard links from filling disks |
| Backup retention, versioning, immutability, delete policies | Prevent accidental deletion and meet retention compliance |
| Restore drill results, measured actual RTO | Validate backup usability rather than mere file existence |
| Repair status and replica health | Ensure replication behaves as expected, separate from backup |

**Alerts should fire whenever no new COMPLETE backup exists within the allowed RPO threshold**, even if the snapshot command ran while upload or verification failed. A single failed backup run must never cause unconditional retention rules to purge the previous clean backup set.

### 12.1. Relationship Between TTL, Deletions, and Backup Retention

In Cassandra, **TTL** and **tombstones** are part of data semantics. Old backups may contain values prior to expiration or deletion; after restore, timestamps/TTLs and business policies on permissible data must be respected. If legal/privacy deletion requests apply, you cannot delete only from live tables while ignoring backup retention. Establish a compliant backup retention/deletion policy with strict access control.

**gc_grace_seconds** governs tombstone/repair mechanics, not backup retention. Lowering it or forcibly purging tombstones to save disk can harm out-of-sync replicas and never substitutes for a backup policy.

## 13. Scenario Exercises

### Exercise 1 — Three Intact Replicas Yet Data Is Lost

A table has RF = 3 and all writes/deletes use **LOCAL_QUORUM**. A faulty DELETE succeeds, and repair subsequently finishes.

**Questions:**

1. Will a LOCAL_QUORUM read automatically retrieve the deleted record?
2. Why does increasing RF from 3 to 5 after the deletion not help recover it?
3. What is needed to roll back prior to the DELETE?

**Hint:** Replicas mirror current state; they do not provide change history for undo. Repair cannot deduce that a DELETE was a business mistake. You need a clean pre-deletion snapshot/backup or an independent historical source, along with a restore procedure.

### Exercise 2 — Which Node Still Has the Snapshot?

A three-node cluster stores data and local snapshots on the same disk. The backup job runs **nodetool snapshot** only on node A. Later, all three nodes/volumes are lost in a regional storage outage.

**Questions:**

1. Does node A's snapshot still exist?
2. Even if node A survived, can we assume A's snapshot holds every partition?
3. How must the architecture change to survive a regional disaster?

**Hint:** Snapshots live on the node's volume; when the volume is lost, the snapshot is lost too. A single node normally holds replicas for only a subset of token ranges. You need full-scope snapshots, transfers of complete sets to a region-independent store, schema/checksum/key verification, and restore drills.

### Exercise 3 — Calculating Potential Data Loss Window

An application completes a full snapshot at **00:00** and finishes transferring it to an off-failure-domain store at **00:45**. No incremental or commitlog archive exists. An incident hits at **09:00**, destroying all replicas.

**Question:** If the valid snapshot cutoff is 00:00, how long is the window of changes at risk of loss? Can 00:45 be used as the recovery point?

**Hint:** Roughly **9 hours**. 00:45 is when transfer finished, which does not mean data up to 00:45 is inside the snapshot.

### Exercise 4 — Is a Bucket in Another Region Enough?

Snapshots are uploaded to another region. However, the same service account has delete permissions on both the database and the bucket, and only a KMS key in the primary region can decrypt them.

**Question:** Which failure types does this architecture survive, and what risks remain?

**Hint:** It can survive disk/local-region failures if the bucket and decryption access remain intact, but remains vulnerable to shared admin permissions and KMS dependency. Separate permissions, enforce retention/immutability as required, and test decryption/restore when the primary region is unavailable.

### Exercise 5 — Choosing Actions Across Three Incidents

| Incident | Choose Priority Mechanism |
|---|---|
| One node fails; RF still has two healthy replicas with valid data | **Replication + replace/streaming**, check replicas and CL |
| Accidental TRUNCATE reaches all replicas | **Pre-incident snapshot/backup** and controlled restore |
| Entire region lost; only independent object storage copies remain | **Off-failure-domain backup**, build new cluster, and test traffic cutover |

Explain why **not every incident should be restored from a snapshot**: for a single-node failure, replacing the node and streaming from healthy replicas is usually more appropriate and preserves the newest data.

## 14. Self-Assessment Design Checklist

- [ ] Defined the **failure domains** to withstand: node, AZ, region, human error, account compromise.
- [ ] Replication strategy, RF, topology, and consistency levels designed and monitored.
- [ ] Snapshots cover **all required nodes, keyspaces, tables, and token ranges**; recoverable data boundary recorded.
- [ ] Schema, version/partitioner/table IDs, and required metadata preserved.
- [ ] Backups reside **outside target failure domains**, checksums match, and independent permissions/decryption keys work.
- [ ] Retention, accidental-deletion protection, and post-verification local snapshot cleanup policies exist.
- [ ] Incremental/commitlog archive plan exists **if** RPO requires it, with replay tested to valid cutoffs.
- [ ] Runbooks exist for node failure, logical deletion, and region loss; isolation restore process is known.
- [ ] Restore drills executed at realistic scale, measuring RPO/RTO and verifying via Java application invariants.
- [ ] Last **COMPLETE** backup monitored, with alerts when data age exceeds limits.

## 15. Summary

**Replicas** keep Cassandra serving when infrastructure components fail, governed by partition keys, replication strategy, and consistency levels. **Snapshots** preserve SSTable files at a point in time on each node, providing historical data for recovery while remaining inside the local storage failure domain. **Off-failure-domain copies** move complete snapshots along with schema, metadata, and decryption capability to a place that survives defined disasters.

A sound design coordinates all three: replication for availability; snapshots for rollback points; and an independent backup store for survivability when primary copies are lost together. What ultimately matters is not how many backup files exist, but **knowing the recovery point, verifying data/keys, and rehearsing recovery to actually meet RPO/RTO**.
