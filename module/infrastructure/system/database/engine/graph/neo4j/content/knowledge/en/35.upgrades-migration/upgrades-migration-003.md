# Backup and Restore Rehearsal Before Upgrading

A Neo4j upgrade can alter the database engine, storage format, schema catalog, security configuration, plugins, and Java application compatibility. If the system encounters failures after upgrading, clicking **"restart the old version"** is rarely a viable recovery plan: the old version may not be able to read a store that was opened or converted by the new version. **A trustworthy rollback plan must start with a valid backup and a rehearsed restore procedure.**

This lesson belongs to the **Upgrades and Migration** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. Neo4j stores nodes, relationships, and properties in a **property graph** model, queries them with Cypher, protects and retrieves data via indexes/constraints, and connects applications via the Java Driver or Spring Data Neo4j. When upgrading such a system, you must protect not only records but also **links, business invariants, schemas, privileges, transaction logs, connection paths, and application recoverability**.

After this lesson, you will be able to:

- Distinguish **backup**, **restore**, **recovery**, **rollback**, **snapshot**, **replica**, and **RPO/RTO** targets.
- Select an appropriate backup method for Community/Enterprise, self-managed/cluster, or Neo4j Aura based on **the running version and service tier**.
- Build a pre-upgrade dossier, create an independent backup, and verify completeness and accessibility of the copy.
- Rehearse restoring into an isolated environment, validating nodes, relationships, properties, indexes, constraints, transactions, and applications.
- Define the exact data cutoff point, write freeze duration, cutover plan, and rollback strategy once the application has produced new transactions.
- Establish a GO/NO-GO procedure, failure testing, and recovery evidence reporting.

> **Version note:** `neo4j-admin` commands, online/incremental backup capabilities, migration/restore procedures, cluster features, and Aura backup tiers vary by version and edition. The illustrative commands below largely follow Neo4j 5.x syntax style; verify actual commands against the documentation and `--help` of **your installed version**. Never run write/delete/restore commands against production without an approved change.

## 1. Why Is a Backup Mandatory Before Upgrading?

Suppose a Neo4j service manages customers and orders:

~~~text
(:UpgradeDemoCustomer {tenantId, customerId, name})
                  |
                  | [:UPGRADE_DEMO_PLACED]
                  v
(:UpgradeDemoOrder {tenantId, orderId, status, amountMinor})
~~~

The application reads a customer along with their orders, updates statuses inside transactions, and uses indexes to look up by customer ID or order ID. An upgrade can surface failures across multiple layers:

| Layer | Upgrade risk | Required verification |
| --- | --- | --- |
| Store | Store is incompatible with the old version or migration fails. | Backup restores onto a supported version; database opens and reads/writes properly. |
| Transaction | Committed writes before failure are not recovered as expected. | Test writes, commits, restarts/restores, and read-back. |
| Node/relationship | Data is missing, labels/types changed, or edges reversed direction. | Reconcile keys, properties, edge counts, and business endpoints. |
| Index/constraint | Index is not ONLINE, constraint fails, or schema changed. | `SHOW INDEXES`, `SHOW CONSTRAINTS`, invariant queries. |
| Security | Privileges, roles, secrets, TLS, or auth providers differ from source. | Test real users/roles inside a controlled restored environment. |
| Plugin/driver | APOC, GDS, Java Driver, SDN, or Cypher are incompatible. | Smoke/integration tests and support matrices. |
| Cluster/routing | A member cannot catch up, routes wrongly, or loses quorum. | Verify topology, routing, replication, and failover per version procedures. |
| Backup/operations | Missing backup parts, lost encryption keys, or restore takes too long. | Independent rehearsal and real RTO measurement. |

**Backup file exists ≠ backup is usable.** Only after reading, restoring, opening the database, validating data, and running the application successfully do you have evidence that the copy can recover the system.

### 1.1. Two Very Different Ways to Handle Failures

~~~text
Upgrade -> failure
   |
   +-- Restart new version, fix config, and continue
   |       (not a rollback)
   |
   '-- Restore a pre-upgrade backup
           onto a compatible version
           + verify data + reopen traffic
           (this is rollback via restore)
~~~

If the application kept accepting writes after upgrading, restoring a pre-upgrade backup can **lose new transactions**. Thus, rollback decisions are not purely technical; they require **a cutoff point, a policy for keeping or replaying transactions, and an approver**.

## 2. Terminology and Recovery Objectives

| Term | Meaning | Misconception to avoid |
| --- | --- | --- |
| **Backup** | A copy of data created via a supported mechanism to recover to a defined state. | Copying raw files while the DB is writing is not automatically a consistent backup. |
| **Restore** | Loading data from a backup into an appropriate database/environment. | Running a restore command does not prove the application serves correctly. |
| **Recovery** | Returning the database to a consistent state after crash or restore, potentially replaying logs per engine rules. | Finishing startup does not mean every index/query/role works. |
| **Rollback** | Returning to an approved version/state after a failed upgrade. | Switching container tags back to the old version does not guarantee it can read a migrated store. |
| **Snapshot** | A storage- or service-level point-in-time capture. | A volume snapshot does not automatically guarantee application consistency. |
| **Replica** | A synchronized/replicated copy serving HA per architecture. | Replicas also replicate accidental deletes or business bugs; they do not replace backups. |
| **RPO** | Maximum acceptable data loss measured by recovery point time. | Not identical to the interval between scheduled backups if transaction logs or other recovery mechanisms exist. |
| **RTO** | Maximum allowed time until service recovers to the agreed level. | Measuring only file copy speed omits verification, routing, indexes, and app startup. |

For example, a business defines:

- **RPO = 15 minutes:** after an incident, the recovered state may lag behind the failure point by at most 15 minutes under the approved measurement method.
- **RTO = 60 minutes:** from incident recognition until core business operations resume takes at most 60 minutes.

Those are **example targets**, not guaranteed default capabilities of every Neo4j setup. If an actual restore rehearsal takes 95 minutes, the current approach **fails RTO**, even if the backup is readable.

### 2.1. Timeline Around an Upgrade

~~~text
T0         T1             T2                T3
|----------|--------------|-----------------|----->
tested     freeze writes  upgrade           verify
backup     + final backup and migration     + open traffic

                    \___ rollback path ___/
               restore backup with clear cutoff point
~~~

Which moment counts as the **last accepted recovery point** must be aligned across the database, applications, and integrated systems (queues/CDC, search indexes, object stores). Do not claim RPO = 0 merely because you ran "a backup right before clicking upgrade" when in-flight transactions or unapplied source events exist.

## 3. Inventory Everything That Must Be Protected

A single database dump/backup does not automatically include everything needed to run the system. Build an **inventory table** before upgrading:

| Group | Component | How to protect |
| --- | --- | --- |
| Business database | Nodes, relationships, properties, and metadata of the selected database. | Neo4j-supported backup/dump. |
| Schema | Indexes, constraints, index names, and build states. | Back up via supported mechanism plus separate Cypher/schema manifest for reconciliation. |
| `system` database | Users/roles, database metadata configuration, and administrative info stored in the system database per architecture. | Identify **the specific backup/restore procedure for the system database** per version/edition; never assume a business DB backup covers it. |
| Neo4j configuration | Server settings, memory, transaction logs, TLS, routing, backup endpoints. | Secret-scrubbed config inventory, IaC/Helm/GitOps. |
| Credentials and keys | Passwords, private keys, trust stores, encryption secrets. | Secret manager / separate key backup, access controls, and rotation plan. |
| Plugins | APOC, GDS, custom procedures, binaries, and configs. | Version pinning, trusted artifacts, and compatibility matrix. |
| Application | Java Driver, SDN, Cypher queries, services, and config. | Build/deployment artifacts, integration tests, and app rollback. |
| Integrations | CDC offsets, event IDs, outbox, broker retention, ETL checkpoints. | Cutoff plan and idempotent replay. |
| Infrastructure | DNS, LBs, certificates, disks, PV/PVCs, backup locations. | IaC, topology diagrams, permissions/connectivity, and recovery steps. |
| Monitoring/audit | Dashboards, alerts, log correlation, and change evidence. | Store separately per retention policy; never embed PII in rehearsal docs. |

**Principle:** backing up the data store protects what that mechanism covers; external configs, secrets, and operational procedures must have their own recovery sources. If the database restores cleanly yet you cannot decrypt backups, authenticate accounts, or connect drivers, the system objective is not met.

## 4. Choosing a Backup Method by Deployment and Edition

There is no single command that fits every Neo4j setup.

| Method | Characteristics | When to consider | Points to verify |
| --- | --- | --- | --- |
| **Offline dump** via supported Neo4j tool | Creates a dump when the database is not serving writes per tool/version requirements. | Small/medium databases, acceptable maintenance window, or staging. | Downtime, file size, dump format, load capability, and OS permissions. |
| **Online backup** (when edition/version supports it) | Captures backup via Neo4j's backup protocol while the database runs. | Production needing minimal downtime with eligible Enterprise backup tooling. | Server/port config, full/incremental, backup chains, permissions, consistency, and version. |
| **Neo4j Aura backup/snapshot** | Managed via console/API/service policy. | Managed deployments. | Service tier, schedule, retention, export, PITR/restore if supported, region, and roles. |
| **Storage-level snapshot** | Captures volumes at CSI/cloud/storage layer. | Supplements DR strategy when an application-consistent workflow is proven. | Consistency during writes, multi-volume alignment, transaction logs, restore tests. |
| **Manual file copy** | Copies the store directory from the filesystem. | **Do not use as an ad-hoc online backup.** | Can produce corrupted/inconsistent copies; use Neo4j-supported tools/procedures. |

### 4.1. Offline Dump and Online Backup Are Not the Same Thing

- **Offline dump** requires the database to be stopped or closed to writes per version guidance. It can increase downtime, yet the process is straightforward when downtime is acceptable.
- **Online backup** is designed to capture data while the database remains active via supported protocols. It may generate a backup chain requiring multiple parts to restore to a given point.
- **Storage snapshots** help at the filesystem level, but you cannot assume a snapshot of store files and transaction logs is consistent if Neo4j is actively writing.

Check **edition, version, permissions, backup paths, server access, networking, and plugins** before choosing. Community Edition should not be assumed to include Enterprise online backup or cluster features.

### 4.2. Illustrative Offline Dump Syntax

On a **practice database that has been properly stopped**, using `neo4j-admin` from a version supporting that syntax:

~~~bash
# Illustrative example: database is stopped and backup path is writable.
neo4j-admin database dump neo4j --to-path=/backup/drill-pre-upgrade
~~~

Use this command only when **offline conditions and version** allow it. `/backup/drill-pre-upgrade` is an example path; never place your sole backup on the same volume about to be upgraded or wiped. Save stdout/stderr, exit code, file size, checksum, and backup tool version docs.

Do not run an experimental `dump` on a live production database without confirming it is supported in that state. Verify exact syntax with:

~~~bash
neo4j-admin database dump --help
~~~

Flags and dump formats can differ across Neo4j 4.x, 5.x, and later releases. Running `dump` **does not** prove restore works; you must rehearse loading and verifying data.

### 4.3. Online Backup in Enterprise or Licensed Tiers

For supported self-managed Neo4j, use the **official backup tool of the exact deployed version**, specifying:

1. Target database, eligible server identity to serve the backup, and backup endpoint.
2. Full/incremental mechanics and restoring from a backup chain.
3. Whether the tool needs transaction logs or extra metadata during restore.
4. Retention limits, encryption, bandwidth, I/O impact, and behavior when a cluster member is unhealthy.
5. Admin/backup permissions, destination storage, and proof of clean completion.

Do not bake a hardcoded `neo4j-admin database backup` command into production automation without checking `--from`, `--to-path`, and backup behavior on your actual build. For online backups, pull commands or Helm hooks from the **exact-version Operations Manual** and rehearse them first.

### 4.4. Neo4j Aura

In a managed service, backups, restores, and point-in-time capabilities depend on **tier, region, and instance type**. Operations happen via the Aura console/API rather than `neo4j-admin`. The application team must confirm:

- Whether the current tier permits on-demand backups right before maintenance.
- Whether data can be exported or restored into a separate test instance for rehearsal.
- Whether retention and the latest recovery point meet RPO.
- Whether version changes or restores require opening a support ticket with the provider.

Do not assume a managed instance grants SSH access to inspect Neo4j directories or copy transaction logs directly.

## 5. Full, Incremental, and Point-in-Time: Verify Real Capabilities

### 5.1. Full Backup

A full backup serves as a standalone baseline recoverable via the matching mechanism and format. It can consume significant storage and time, yet avoids over-reliance on long incremental chains.

### 5.2. Incremental Backup

An incremental backup records changes since a previous backup point per the tool's design. It **cannot stand alone** if restoration requires the full baseline and intermediate chain segments.

~~~text
Full F0
  |
  +---- Incremental I1
               |
               +---- Incremental I2
                            |
                            +---- Desired restore point
~~~

If `I1` is lost or corrupted and the chain depends on it, `F0 + I2` alone is not enough. Validation must check **the entire chain**, manifests/metadata, permissions, and end-of-chain restoration.

### 5.3. Point-in-Time Recovery (PITR)

Recovering to a specific timestamp or transaction is only possible when **edition, tooling, backup/log chains, and service tier explicitly support it**. Do not claim "we have transaction logs so we can restore to any timestamp" unless the tooling provides a consistent, tested procedure.

For upgrades, two checkpoints are often helpful:

| Milestone | Meaning |
| --- | --- |
| **B0 – pre-maintenance** | Regular verified backup establishing a long-term recovery path. |
| **B1 – upgrade cutoff** | Final copy taken after freezing writes or via an agreed consistent backup mechanism. |

If the upgrade fails before reopening traffic, B1 is usually the clearest rollback candidate. If failure occurs **after reopening writes**, you must decide how to retain, copy, or replay transactions after B1, or accept the approved RPO; never silently discard them.

## 6. Inventory Neo4j State Before Maintenance

A backup plan must capture a **baseline** so post-restore validation has something to compare against. Use a monitoring account with appropriate privileges.

### 6.1. Version and Topology

Record **Neo4j server version**, edition, database count, cluster topology, plugins, and Java Driver/SDN versions. Version inspection methods vary across Neo4j lines; on releases supporting this procedure:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

In restricted deployments, the command may fail or omit details. Retrieve versions from an approved management tool or console rather than granting excessive privileges to the application.

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
RETURN name, currentStatus, requestedStatus
ORDER BY name;
~~~

`SHOW DATABASES` checks online/offline states; it neither measures disk usage nor guarantees a freshly created backup is restorable.

### 6.2. Index State

~~~cypher
SHOW INDEXES
YIELD name, type, entityType,
      labelsOrTypes, properties, state,
      populationPercent
RETURN name, type, entityType,
       labelsOrTypes, properties, state,
       populationPercent
ORDER BY name;
~~~

When capturing the baseline, record which indexes are `ONLINE`, `POPULATING`, or `FAILED`. Do not automatically mistake a `POPULATING` state after restore for **data loss**; it may simply need build time. However, business queries relying on that index may be slow or behave unexpectedly until it is ready.

### 6.3. Constraints and Business Identifiers

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Constraints on business keys are critical: two nodes sharing the same key or nodes missing key fields can break application logic even when the database reports online.

### 6.4. Record Before/After Table

| Component | Pre-upgrade | Post-restore/upgrade | Acceptable when |
| --- | --- | --- | --- |
| Database status | ONLINE | ... | Database is in expected state. |
| Nodes/relationships by key type | Counts at same cutoff | ... | Matches baseline or variance is explained with evidence. |
| Business constraints | List of names/types/properties | ... | No required constraints missing. |
| Indexes | State/type/properties | ... | Key indexes ONLINE and used by queries. |
| Security | Roles/users and auth method | ... | Real permissions tested, not just matching role names. |
| Backup | Manifest, timestamp, checksum, location | ... | Copy is readable and restorable. |
| Application | Driver/SDN, API smoke tests | ... | Read/write/transaction queries pass. |
| RPO/RTO | Approved target | Rehearsal result | Within approved targets. |

## 7. Build a Verifiable Cypher Fixture

To rehearse on an **isolated test database**, use labels/types prefixed with `UpgradeDemo`. Never load fixtures into a production database without authorization and a safe cleanup procedure.

### 7.1. Identity Keys

~~~cypher
CREATE CONSTRAINT upgrade_demo_customer_key IF NOT EXISTS
FOR (c:UpgradeDemoCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT upgrade_demo_order_key IF NOT EXISTS
FOR (o:UpgradeDemoOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

These are uniqueness constraints on property pairs when values exist. They **do not automatically enforce** that key properties always exist; when production needs both existence and uniqueness, evaluate key/existence constraints per edition/version and validate in the application.

### 7.2. Sample Data

~~~cypher
MERGE (c:UpgradeDemoCustomer {
  tenantId: 'tenant-demo',
  customerId: 'C01'
})
SET c.name = 'Test Customer'
MERGE (o1:UpgradeDemoOrder {
  tenantId: 'tenant-demo',
  orderId: 'O01'
})
SET o1.amountMinor = 125000,
    o1.status = 'PAID'
MERGE (o2:UpgradeDemoOrder {
  tenantId: 'tenant-demo',
  orderId: 'O02'
})
SET o2.amountMinor = 34000,
    o2.status = 'PENDING'
MERGE (c)-[:UPGRADE_DEMO_PLACED]->(o1)
MERGE (c)-[:UPGRADE_DEMO_PLACED]->(o2);
~~~

Running on a clean fixture yields one customer, two orders, and two correctly directed relationships.

### 7.3. Recovery Verification Oracle

~~~cypher
MATCH (c:UpgradeDemoCustomer {
  tenantId: 'tenant-demo',
  customerId: 'C01'
})
OPTIONAL MATCH (c)-[r:UPGRADE_DEMO_PLACED]->
               (o:UpgradeDemoOrder)
RETURN c.customerId AS customerId,
       count(r) AS relationshipCount,
       count(DISTINCT o) AS orderCount,
       sum(o.amountMinor) AS totalAmountMinor,
       collect(DISTINCT o.status) AS statuses;
~~~

With the sample data, expected results are:

| Check | Expected value |
| --- | --- |
| `customerId` | `C01` |
| `relationshipCount` | `2` |
| `orderCount` | `2` |
| `totalAmountMinor` | `159000` |
| `statuses` | Contains `PAID` and `PENDING` |

Check for invalid reversed direction:

~~~cypher
MATCH (o:UpgradeDemoOrder)
      -[r:UPGRADE_DEMO_PLACED]->
      (c:UpgradeDemoCustomer)
WHERE o.tenantId = 'tenant-demo'
RETURN count(r) AS reversedRelationships;
~~~

Expected result is `reversedRelationships = 0`. A restore with the exact **two order nodes** yet missing relationships or reversed edge direction still **fails**.

### 7.4. Do Not Check Only Fixtures

On a real system, build a list of representative **business invariants**:

- Every Order must belong to exactly one Customer in the same tenant when required by business rules.
- No two nodes share the same primary key within a tenant.
- Monetary/status fields have valid types and allowed ranges.
- Permission/membership edges point in the right direction without unintended cross-tenant links.
- Totals, breakdowns by type/status, and normalized checksums match at **the same cutoff point**.
- Required indexes/constraints exist and operate properly.

Matching total counts can hide a bug where "one order is missing and another extra order appeared". Reconcile by keys, properties, and relationships across critical data regions.

## 8. Pre-Upgrade Backup Runbook

**Goal:** create an independent copy, know exactly which data point is preserved, and confirm it can be restored into an appropriate environment.

### Step 1 — Preparation

Confirm:

- Source Neo4j: databases, server/cluster, edition/version, plugins, and configuration.
- Upgrade target: target version, supported upgrade path, schema/index changes, and app compatibility plan.
- RPO/RTO, maintenance window, and operational owners.
- Backup account has required permissions without excessive privileges.
- Source/target disk space suffices for backups, transaction logs, index population, and temporary files.
- Backup destination lies in an independent failure domain with encryption, retention, and access controls.
- Previous backup has already been restore-tested, or an alternative verification plan exists.

### Step 2 — Establish Cutoff and Control Writers

Depending on deployment model:

1. Announce maintenance start and instruct applications to throttle/pause mutations.
2. Stop import jobs, ETLs, crons, CDC consumers, and other write paths from creating **unplanned** data past the cutoff.
3. Wait for in-flight transactions to complete or handle them per approved rules; do not kill indiscriminately.
4. Record source watermarks/offsets and the status of events already applied in Neo4j.
5. Execute the backup method matching online/offline requirements.

Do not treat "turning off HTTP APIs" as blocking all writers: Java batches, admin scripts, queue consumers, or ops tools may still write. For online backups taken while applications continue writing, prove the exact timestamp and consistency guarantees provided by the supported tool.

### Step 3 — Run Backup via Supported Method

Record at minimum:

| Field | Example |
| --- | --- |
| `backupRunId` | `pre-upgrade-2026-11-25-a` |
| Database and instance | `neo4j` / `graph-node-1` |
| Version, edition | Verified string from source environment |
| Tool, version | Actual Neo4j Admin tool / backup tool / Aura tier |
| Cutoff point | Timestamp / watermark / transaction ID per source |
| Backup type | Offline dump, full/incremental online, managed backup |
| Destination | Approved repository, **no secrets logged** |
| Result | Exit code, completion log, size, checksum, and errors |

Include the backup ID in artifact naming to prevent accidental overwrites. Do not rely solely on a console line saying "backup started"; verify **clean completion** and the presence of every required backup chain component.

### Step 4 — Verify Artifact

- File/manifest is non-empty and reasonably sized relative to baseline.
- No I/O errors, disk full, permission denied, or mid-transfer network drops.
- All parts of a full/incremental chain include complete metadata.
- Verify checksum/hash for transit and storage; store hashes independently if needed.
- Decryption keys, recovery credentials/roles, and recovery binaries **are usable** in the drill environment.
- Backup is replicated outside the source failure domain under retention/delete protection.

**A checksum only proves bytes did not change since hashing; it does not prove a backup is application-consistent or restorable.**

### Step 5 — Update Records and Protect the Copy

A backup designated for rollback must record:

- Owner, creation timestamp, and status (`READY_FOR_RESTORE_DRILL` or `VERIFIED_RESTORABLE`).
- Secret-free storage path/ID, checksum, version, and database scope.
- Cutover point to distinguish transactions before vs. after.
- Expiration date and retention hold if needed through post-upgrade observation.
- Rehearsal results, including any variances or limitations found.

## 9. Rehearse Restore in an Isolated Environment

**Restoration is the centerpiece test.** Never restore over production just to prove a backup works.

### 9.1. Designing the Drill Environment

A proper rehearsal environment needs:

1. **Dedicated database/instance**, isolated namespace/VPC, or standalone test host.
2. A Neo4j version **compatible with the backup/store format** per supported procedures.
3. CPU, RAM, disk, throughput, and filesystem similar enough to make RTO measurements meaningful.
4. Restricted outbound connectivity: never send real emails, payments, webhooks, or external events.
5. Drill-only secrets/certificates, ensuring production credentials are never accidentally reused for external integrations.
6. Input snapshot or backup mounted **read-only if supported**, with an empty or explicitly approved target directory.
7. Synthetic test data or properly masked/anonymized data if source contains PII.

When rehearsing with real data, backups still hold sensitive data even in staging. Apply the same encryption, access limits, audit logging, and post-test deletion standards.

### 9.2. Example Restoring from an Offline Dump

On a **test instance whose target database is stopped**, using Neo4j tooling verified for your version, Neo4j 5.x releases support a command pattern similar to:

~~~bash
# Test host only; target "neo4j" is stopped as required by the tool.
neo4j-admin database load neo4j \
  --from-path=/backup/drill-pre-upgrade
~~~

Run:

~~~bash
neo4j-admin database load --help
~~~

before execution to confirm options, permissions, and file formats. If the target database already contains data, the command may refuse to overwrite; **never blindly add an overwrite option** without knowing exactly what source and target paths contain. Never rely on example syntax to run potentially destructive restores on real environments.

Once loading completes, start Neo4j per standard procedures, wait until the database enters a queryable state, and run Cypher checks. **Successful load does not mean data and applications pass.**

### 9.3. Restoring Online Backups or Managed Backups

For online backups/backup chains, use **the exact version's restore command** with complete manifests. For Aura, use restore-to-test-instance if your tier allows it. Record:

- Backup ID and chain used.
- Recovery tool, command, and version.
- Transaction log apply/recovery status reported by the tool.
- Load/restore time, startup time, and index population time.
- Settings requiring reapplication (TLS, routing, auth, plugins, data sources).
- Evidence that the database is ready to serve after restore.

**Do not open a newer Enterprise backup using an unsupported older server** just to test rollback. Once a store has been upgraded, returning to the prior version typically requires **restoring the pre-upgrade backup with a compatible tool/version**, not downgrading the engine in place.

## 10. Multi-Layer Validation of Restored Data

### 10.1. Layer A — Database Opens and Serves

Check:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus
RETURN name, currentStatus
ORDER BY name;
~~~

For the test database, confirm `ONLINE` and successful Cypher connectivity. This is only **the starting line**, insufficient to declare restore success.

### 10.2. Layer B — Schema and Indexes

Compare `SHOW CONSTRAINTS` and `SHOW INDEXES` outputs against the baseline. If an index is `POPULATING`, wait for/measure build time and confirm `ONLINE` for critical queries before opening load.

For each core query:

~~~cypher
EXPLAIN
MATCH (o:UpgradeDemoOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status, o.amountMinor AS amountMinor;
~~~

When safe on drill data:

~~~cypher
PROFILE
MATCH (o:UpgradeDemoOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status, o.amountMinor AS amountMinor;
~~~

`EXPLAIN` does not execute; `PROFILE` **executes** and reports runtime plan statistics. Across an upgrade changing planner/runtime/index providers, a query can return accurate results yet suffer severe cost spikes; measure Rows, DB Hits, and latency on representative data rather than checking only the index catalog.

### 10.3. Layer C — Business Content and Relationships

Check:

- **Keys:** duplicate or missing nodes per tenant and business ID.
- **Properties:** data types, monetary values, statuses, timezones, and nullability.
- **Edges:** types, directions, tenant-aligned endpoints, and valid relationship counts.
- **Deleted/tombstone:** deleted or soft-deleted records do not accidentally "resurrect" after restore.
- **Data rules:** aggregates by status, business reconciliations, and key ID sets.
- **Edge cases:** supernodes, parallel edges between two nodes, large values, Unicode strings, and temporal/spatial/vector values if used.

Query detecting cross-tenant relationship leaks:

~~~cypher
MATCH (c:UpgradeDemoCustomer)
      -[r:UPGRADE_DEMO_PLACED]->
      (o:UpgradeDemoOrder)
WHERE c.tenantId <> o.tenantId
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       c.tenantId AS customerTenant,
       o.tenantId AS orderTenant
LIMIT 100;
~~~

If the model mandates that every order belongs to a customer in the same tenant, expect **0 rows**. If the real system legitimately allows cross-tenant relationships, adjust the invariant instead of enforcing an inaccurate rule.

Query detecting orders missing an owner edge:

~~~cypher
MATCH (o:UpgradeDemoOrder {tenantId: $tenantId})
WHERE NOT EXISTS {
  MATCH (:UpgradeDemoCustomer)-[:UPGRADE_DEMO_PLACED]->(o)
}
RETURN o.orderId AS orderId
LIMIT 100;
~~~

This detects one class of missing links; if the domain permits customer-less orders, exclude valid cases with explicit filters.

### 10.4. Layer D — Security and Configuration

Test **effective privileges**, not just listing role names:

- Are read-only service accounts blocked from mutations?
- Do write accounts reach only the target database and permitted labels/properties?
- Do queries enforce tenant isolation without leaking cross-tenant data?
- Are TLS/certificates, DNS, and Bolt/routing URIs valid for the drill application?
- Must users/roles or external auth configs be migrated separately from `system` database/config?
- Is the backup protected in storage and is drill data shielded from unauthorized users?

### 10.5. Layer E — Post-Restore Write Transactions

A readable database can still fail on writes due to storage, permissions, or config. In the drill environment:

1. Write a test node/relationship inside a transaction.
2. Confirm commit succeeds and read it back from a new session.
3. Perform a controlled database restart.
4. Read back the committed data.
5. Verify rollback by intentionally throwing an error inside a transaction.

This is a minimal **durability and atomicity** check; it does not replace specialized crash-recovery or storage testing.

## 11. Verification with Java Driver and Spring Data Neo4j

Real Neo4j applications rarely run raw Cypher alone. After a restore or upgrade, APIs can fail due to driver incompatibility, URI/routing shifts, new certificates, or Spring Data Neo4j mapping mismatches.

### 11.1. Java Driver Smoke Test

The snippet below assumes a `Driver` is configured for the **drill database** with proper secrets and TLS; never hardcode credentials:

~~~java
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class RestoreSmokeTest {
    public static void verify(Driver driver) {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            long matches = session.executeRead(tx ->
                tx.run("""
                    MATCH (c:UpgradeDemoCustomer {
                      tenantId: $tenantId, customerId: $customerId
                    })-[r:UPGRADE_DEMO_PLACED]->
                    (o:UpgradeDemoOrder)
                    RETURN count(r) AS count
                    """, Map.of(
                    "tenantId", "tenant-demo",
                    "customerId", "C01"
                )).single().get("count").asLong());

            if (matches != 2L) {
                throw new IllegalStateException(
                    "Restore invariant failed: expected 2 links");
            }
        }
    }
}
~~~

This example checks only the fixture; real applications need broader assertions over nodes, properties, transactions, permissions, pagination, and critical queries. Verify **Java Driver, Java runtime, and Spring Data Neo4j** in compatibility matrices against the target Neo4j version rather than inferring full feature health from one passing query.

### 11.2. Spring Data Neo4j

In an SDN application, integration tests should:

- Load node entities via repositories using business keys.
- Load relationship properties if using `@RelationshipProperties`/`@TargetNode`.
- Verify `OUTGOING`/`INCOMING` directions and ensure saving does not drop relationships.
- Test `@Transactional` commit and rollback behavior.
- Use narrow update queries when aggregates are partially loaded, preventing accidental relationship deletion after restore.
- Run application migrations in **the rehearsal environment**, never directly on production just to "see if it errors".

An often-overlooked detail: after a database upgrade, legacy queries without `ORDER BY` may return rows in a different order. Tests must verify business semantics rather than blindly diffing raw JSON that relies on unguaranteed ordering.

## 12. Rehearsing the Upgrade on the Restored Copy

Restoring a backup into an isolated environment proves **the copy is usable**. Yet "pre-upgrade readiness" also requires rehearsing **the upgrade itself on that restored copy**, rather than running it for the first time in production.

~~~text
Production version A
        |
        +---- backup B1 ----> Drill A (version A)
                                  |
                                  | restore + verify baseline
                                  v
                             Upgrade A -> B
                                  |
                                  v
                       Verify graph/schema/app
                                  |
                          +-------+-------+
                          |               |
                         PASS            FAIL
                          |               |
                          v               v
                     GO process       NO-GO + fix
~~~

### 12.1. Compatibility Matrix Must Be Approved

| Component | Must verify |
| --- | --- |
| Neo4j source/target | Supported upgrade path, mandatory intermediates, store format migration. |
| Operating system/Java runtime | JDK/JVM/OS/container base image matching Neo4j version. |
| Driver/SDN | Neo4j Java Driver and Spring Data Neo4j supporting target server. |
| APOC/GDS/custom plugins | Plugin build matches engine and procedure APIs; any behavior changes? |
| Cypher/schema | Query syntax, indexes/constraints, planner, deprecations, and migration. |
| Cluster | Quorum, member topology, upgrade sequence, protocol, and routing. |
| Backup/restore | Which tool reads source artifacts; ability to roll back to version A. |
| Security | Authentication/authorization, TLS, and secret/role management. |
| Infrastructure | Heap/page cache, disk/headroom, log rotation, network/ports. |

A successful **A → B** upgrade on a tiny database does not prove a large production upgrade will finish within the maintenance window. Measure store migration, startup, index population, data verification, and application checks.

### 12.2. High-Risk Checks After Drill Upgrade

1. **Open the database** on version B without ignoring migration/index warnings.
2. **Compare invariants** against the version A drill at the same data cutoff.
3. Inspect `SHOW INDEXES`, `SHOW CONSTRAINTS`, and query plans.
4. Run smoke tests for Java Driver, SDN/GraphQL/REST if used.
5. Measure query/transaction p95/p99 under representative load.
6. Test server restart, taking a fresh backup on B, and restoring backup B into another compatible environment.
7. Test **rollback using B1 onto version A**, without trying to downgrade the migrated store B in place.
8. Record time/memory/disk deltas and update the runbook.

If B1 cannot restore onto A due to tool, format, or permission incompatibilities, **rollback is unproven**; never declare GO merely because A → B succeeded.

## 13. Data Cutoff Points and External Writers

A system typically has multiple write sources:

~~~text
HTTP API ---------+
Batch import -----+--> Neo4j database
CDC consumer -----+
Scheduled job ----+
Admin Cypher -----+
~~~

To establish a clean restore point:

1. Enumerate and pause/control **every writer** within maintenance scope.
2. Determine which transactions committed and which source events/offsets were applied.
3. Record watermarks/changelogs, checklists, and backup timestamps.
4. Ensure backup B1 reflects a unified state; if online backup runs concurrently, use tool semantics to define the exact recovery point.
5. For broker-backed systems, retain sufficient logs/source snapshots to **idempotently replay** unapplied events.
6. Reopen writers only after database B passes all checks and rollback boundaries are clearly bounded.

### 13.1. Do Not Claim "Consistent Backup" Just Because Counts Match

Suppose the source system is updating:

~~~text
T0: Customer C1 has two Orders, total 159000
T1: Order O02 changes amountMinor from 34000 to 39000
T2: CDC event reaches Neo4j
T3: Neo4j backup completes
~~~

If you read the source at T1 and Neo4j at T0, both sides can differ even when the pipeline lost zero events. Reconcile at **the same watermark** or via versioned snapshots; never diff two live mutating systems arbitrarily and blame the backup.

### 13.2. Risks at the Cutover Point

Once traffic opens to database version B, new transactions mean rolling back to B1 drops post-cutover data. Mitigate this risk via:

- A read-only **canary phase** before opening writes if the product allows it.
- Keeping writes restricted during initial verification, opening gradually after gates pass.
- Persisting events/outbox records with idempotency keys or verified replay pipelines.
- Recording **timestamps/versions of data** read by applications and mutations performed.
- Defining the point of "no quick rollback to A", switching to forward-fix or fail-forward.

**Ad-hoc dual-write** to both versions A and B easily causes divergence when one side commits and the other fails. If architecture demands dual-write, implement ordering/idempotency protocols, drift monitoring, and reconciliation; never add it casually without testing.

## 14. Rollback Plan: Technical and Business Dimensions

Rollback must answer four questions:

1. Restore **which artifact** (backup ID, version, checksum, cutoff point)?
2. Restore **where** (which host/cluster/PVC/instance, access rights, and connection path)?
3. Drop or replay **which transactions** occurred after the cutoff?
4. Who **approves** routing traffic back and signing off on data correctness?

### 14.1. Decision Matrix

| Scenario | Response | Risk |
| --- | --- | --- |
| Upgrade fails before opening writes on B | Restore B1 onto compatible A environment; test and shift traffic. | Restore duration, routing, config, and jobs still emitting events. |
| B runs, only one application query fails | Fix query/driver or roll back app without touching DB if compatible. | Must confirm old query/driver still supports server B. |
| B accepted new writes, major failure suspected | Evaluate fail-forward or rollback plus replaying post-B1 transactions. | Never silently discard changes committed on B. |
| Store B is incompatible with A | Do not open that store with A. Restore pre-upgrade backup via supported path. | Downtime and data loss if cutoff/failback plan is missing. |
| Backup B1 fails to restore | NO-GO if upgrade hasn't run; if already upgraded, trigger real-time incident recovery. | No proven rollback path exists. |
| Cluster loses quorum during upgrade | Halt further steps and follow exact-version cluster runbook. | Blind scaling/restarting can worsen cluster state. |

### 14.2. Distinguish Rollback from Fail-Forward

- **Rollback:** returning to version A / verified B1 state, potentially compensating or replaying new transactions.
- **Fail-forward:** fixing configuration, application code, migrations, or data on B to remain on version B.

Fail-forward sometimes risks less data loss if B already absorbed heavy writes; rollback is often safer before traffic opens. The incident commander decides based on **RPO/RTO, business impact, and evidence**.

## 15. Storage Space and Time Budget for Rehearsals

Restoring often requires **more free space than the backup file size** because it must unpack, load the store, write transaction logs, build indexes, and retain old copies.

| Item | Capacity to measure |
| --- | --- |
| Backup/dump file | Compressed/archived size and unpacked size if applicable. |
| Data store | Node/relationship/property and metadata size after restore. |
| Indexes | Index size and peak usage during population/rebuild. |
| Transaction logs | Space consumed during apply/recovery and new writes. |
| Temporary files | Import/restore scratch workspace, OS logs, and migration tools. |
| Headroom | Buffer for write bursts, log rotation, and rollback. |

### 15.1. Illustrative Sizing Example

Suppose after restoring into a test environment:

- Store uses 240 GiB.
- Indexes use 45 GiB **not included in that store metric**.
- Transaction logs and temp files peak at 80 GiB.
- Safety headroom is 25% over base total.

When figures do not overlap, base need is `240 + 45 + 80 = 365 GiB`. Adding 25% gives roughly `456.25 GiB`. This illustrates the calculation, **not Neo4j defaults**. If store metrics already include indexes, subtract double-counting; if store and logs reside on separate volumes, budget each volume independently.

### 15.2. Measuring Recovery Time by Component

~~~text
RTO observed =
  detect/escalate
  + provision infra/secrets/volumes
  + fetch backup
  + load/restore/apply logs
  + database startup/recovery/indexes
  + verify data/application
  + switch DNS/routing/traffic
~~~

A benchmark measuring only dump copy time while ignoring data validation and traffic switching **is not a full RTO**. If restoring on an oversized machine while production DR uses smaller nodes or slower networking, document that representativeness gap in the rehearsal report.

## 16. Protecting Backups Against Attacks and Operational Errors

A backup contains most or all sensitive data: PII, customer relationships, transactions, and potentially administrative metadata. Protect it at least as strictly as the live database.

### 16.1. Mandatory Controls

- **Encryption:** in transit and at rest, with keys managed in an approved key store.
- **Separation of duties:** whoever runs backups should not automatically have permission to delete old backups; whoever reads logs should not download PII dumps.
- **Location:** retain copies outside the failure domain of the database and cluster under upgrade.
- **Immutability:** consider object lock/retention policies or append-only storage to mitigate ransomware and accidental deletion.
- **Auditing:** track who created, accessed, downloaded, restored, or deleted a backup, when, and why.
- **Retention:** clear pre/post-upgrade retention windows, including deletion rules for sensitive data in drill environments.
- **Decryption keys:** maintain secret recovery procedures and prove backups can be opened even if the primary source is gone.

### 16.2. Do Not Let Rehearsals Cause Real-World Side Effects

An environment restored from production may contain:

- Real emails, phone numbers, and street addresses.
- "Unsent" queue/outbox events that background jobs could dispatch again.
- Webhook URLs, API keys, and external integration credentials.
- Scheduled recurring jobs.

Before starting applications in the drill environment:

1. Sever or mock all outbound write integrations.
2. Use drill-specific secrets and endpoints.
3. Disable real event schedulers/workers; enforce read-only/test flags per policy.
4. Restrict access to restored data.
5. Plan secure deletion of drill data after gathering test evidence.

**Restoring cleanly and then accidentally sending thousands of real emails or payments is an incident**, not a successful drill.

## 17. Pre-Upgrade Test Matrix

Do not intentionally break production to evaluate recoverability. Use an isolated environment and approved backups.

| ID | Scenario | Expected outcome |
| --- | --- | --- |
| U01 | Backup completes and artifact is present. | Exit status, manifest/checksum, size, and independent storage location recorded. |
| U02 | Restore from full backup into test instance. | Database ONLINE; read and write queries work. |
| U03 | Restore from full + incremental chain. | All chain segments present; exact expected recovery point reached. |
| U04 | Missing one incremental in the chain. | Incomplete restore detected; **not** marked passing. |
| U05 | Wrong/missing decryption key or credential. | Clear BLOCKER reported with valid key recovery procedure. |
| U06 | Truncated/corrupted backup in test. | Caught by tool/checksum/restore; traffic remains closed. |
| U07 | Fixture data with node and relationship properties. | Keys, values, directions, edge counts, and invariants match. |
| U08 | Index is POPULATING after restore. | Wait for key indexes ONLINE and measure queries before GO. |
| U09 | Critical constraint/key missing after restore. | Catalog reconciliation detects it; data not declared ready. |
| U10 | Read/write and transaction rollback via Java Driver. | Commits persist and rollbacks preserve invariants. |
| U11 | Spring Data Neo4j loads/saves relationship properties. | No properties/edges dropped due to incomplete mapping or load queries. |
| U12 | Read-only role and write role. | Privileges match post-restore; no cross-tenant data leakage. |
| U13 | Simulate driver disconnect during commit. | Idempotency/status lookup handles it; no duplicate side effects. |
| U14 | Upgrade drill on restored data. | Completes supported migration path; app and queries pass. |
| U15 | Rollback drill onto pre-upgrade version. | Backup B1 restores cleanly **without** reusing the upgraded store. |
| U16 | CDC/batch still has unapplied events. | Watermarks recorded; zero lost or duplicate replays post-cutover. |
| U17 | Staging environment lacks resources. | Real RTO/costs measured; root causes of timeouts/disk exhaustion documented. |
| U18 | Replica/primary fails during cluster test. | Version-appropriate quorum and restore/catch-up runbook followed; PVCs not blindly deleted. |
| U19 | Logs/metrics lost during drill. | Flagged as missing evidence with alerting; missing logs never treated as "no errors". |
| U20 | Backup expired or accidentally deleted. | Retention/immutability policies catch it and fallback copy exists. |
| U21 | Drill data contains outbound integrations. | Zero real emails, webhooks, or payments emitted. |
| U22 | Recovery under load and after restart. | Verify RPO/RTO, transactions, query p95/p99, and index readiness. |

### 17.1. Test Conclusions Must Include Metrics

Minimum rehearsal report:

| Field | Example entry |
| --- | --- |
| Test ID | `U15` |
| Source backup | `pre-upgrade-2026-11-25-a` |
| Source version / target test version | Exact strings actually tested |
| Recovered data timestamp | Watermark or timestamp confirmed by tool |
| Method | Offline dump / online backup / managed restore |
| Measured recovery time | Total from simulated incident start to service ready |
| Graph/schema checks | Counts, checksums, invariants, indexes/constraints |
| Application checks | Java Driver/SDN/API smoke and load tests |
| Result | PASS / FAIL / BLOCKED with explanation |
| Approver | Database and application owners |

Never write a generic "restore OK" without storing **timestamps, data scope, tooling, and test results**.

## 18. Upgrade Runbook with Clear Stop Gates

### Phase A — Before the Maintenance Window

1. Verify versions/edition, upgrade path, and compatibility matrices.
2. Inventory databases, schemas, system/security config, plugins, drivers, and integrations.
3. Capture data, query, index, and KPI baselines.
4. Create backup B0 per policy; run restore drill and verify.
5. Rehearse upgrading A → B on the restored copy.
6. Test rollback to A **from the pre-upgrade copy**.
7. Measure RPO/RTO and verify capacity, privileges, secrets, and runbooks.
8. Approve GO with designated owners and on-call responders.

### Phase B — During the Maintenance Window

1. Announce maintenance, check health/latest backup, and confirm support readiness.
2. Pause writers and integration jobs per plan; drain transactions.
3. Record checkpoints/watermarks and **capture final backup B1**.
4. Verify B1 readability and record cutoff point; keep B0 independent.
5. Execute upgrade following the **exact version's** runbook without ignoring warnings.
6. Verify databases, indexes, constraints, graph data, permissions, Java/SDN, and transactions.
7. Open traffic only if every gate PASSES; otherwise trigger rollback or fail-forward within approved scope.

### Phase C — After Opening Traffic

1. Monitor p95/p99, query errors, transaction rollbacks, `FAILED` indexes, and disk/log growth.
2. Track CDC lag, integration jobs, and replay idempotency.
3. Track records modified after B1 to understand remaining rollback feasibility.
4. Capture and test a fresh backup on version B per policy.
5. Close the change after observation completes, archiving results and B1 retention.

**Never skip backup B1 just because B0 passed rehearsal yesterday.** Between B0 and cutover, data likely changed; your rollback point must align with the upgrade window and RPO.

## 19. GO/NO-GO and Approval Roles

| Criterion | GO when | NO-GO when |
| --- | --- | --- |
| Restorability | Backup B1/B0 artifacts exist and restore path is verified. | No rehearsal run, or missing decryption keys / backup chain segments. |
| RPO/RTO | Drill results meet targets or written exception is approved. | Restore exceeds RTO or recovery point fails requirements. |
| Compatibility | Valid upgrade path confirmed for server, driver, plugins, schema. | Version/edition/plugin incompatible or unverified. |
| Data | Nodes/relationships/properties, constraints, and invariants pass. | Only checked database ONLINE without validating data. |
| Writers | APIs, batches, CDC, admin paths, and checkpoints controlled. | Unaccounted write sources could skew the cutoff. |
| Rollback | Know which backup restores to A and how post-cutoff writes are handled. | Plan is merely "switch back to old image/tag". |
| Security | Secrets, privileges, TLS, tenants, and backup encryption valid. | Backup exposes PII/credentials or staging can emit live events. |
| Capacity | Enough space for backups, restore, indexes, logs, and headroom. | Disk nearly full, insufficient scratch space, or non-expandable volumes. |
| Observability | Monitoring, alerts, owners, and stop criteria are in place. | Cannot measure errors or no accountable owner assigned. |
| Cluster | Quorum, member health, backup source, and upgrade order tested. | Relying purely on Kubernetes rolling restart without Neo4j cluster rules. |

**GO does not mean zero risk.** It means critical risks have been identified, controlled, backed by test evidence, and assigned accountable owners if execution must halt.

## 20. Common Mistakes When Preparing Upgrade Backups

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Checking only `ls backup-file` to see a file exists. | Backup may be corrupted or unrestorable. | Test restoring, querying data, and running transactions. |
| Copying the store directory while Neo4j is writing. | Copy may be inconsistent. | Use offline dump, online backup, or supported consistent snapshots. |
| Keeping the sole backup on the same PVC/volume. | Volume failure or PVC deletion destroys both source and backup. | Store in an independent failure domain with encryption and retention. |
| Failing to back up/inventory `system`, roles, and config. | Database recovers, yet permissions/apps fail. | Maintain full inventory and version-specific recovery plan. |
| Restoring onto production to "test". | Risks overwriting real data. | Use an isolated drill instance/database. |
| Failing to stop CDC/batch writers. | Ambiguous cutoff or stray writes enter. | Record watermarks and control every writer. |
| Checking only node counts. | Missing/wrong relationships or drifted properties hidden behind matching counts. | Validate invariants and reconcile by keys/versions. |
| Checking only that indexes exist. | Indexes may be FAILED/POPULATING or plans degraded. | Check index states and `EXPLAIN`/`PROFILE`. |
| Measuring only backup copy duration. | Overly optimistic RTO estimate. | Include startup, indexes, app warmup, DNS, and verification. |
| Rolling back container image after store migration. | Old engine may fail to read the new store. | Restore the pre-upgrade backup using compatible tools/versions. |
| Ignoring new writes after cutover. | Rollback loses committed data. | Establish explicit fail-forward/replay/RPO policy. |
| Backup lacks decryption keys or read permissions. | Data exists yet cannot be used in an emergency. | Rehearse using actual DR personnel/roles and backup key custody. |
| Enabling all staging jobs after restore. | Sends real emails, webhooks, or payments. | Isolate outbound integrations, secrets, and schedulers. |
| Testing only single-node when production is a cluster. | Misses quorum/routing/replica errors. | Rehearse matching production topology and version. |
| Assuming PVC snapshots are consistent Neo4j backups. | Restore fails due to misaligned store/log capture. | Follow supported procedures and verify via real restore. |

## 21. Practice Exercises

**Exercise 1 — Defining recovery.** A system requires a 10-minute RPO and 45-minute RTO. A full backup was taken 2 hours ago, restore takes 35 minutes, and no mechanism exists to apply changes after the backup. Evaluate both targets and propose improvements.

**Exercise 2 — Dump vs. backup.** A Community environment can accept a 90-minute outage, while an Enterprise environment must back up while live. Compare offline dump and online backup across supported features, downtime, tooling, backup chains, and restore drills.

**Exercise 3 — Graph reconciliation.** Using the fixture from section 7, create a dump/backup in a learning environment, restore into a test database, and verify `relationshipCount`, `totalAmountMinor`, edge direction, and both uniqueness constraints. Explain why matching node counts alone is insufficient.

**Exercise 4 — Broken backup chain.** Full `F0` is intact, incremental `I1` is lost, and `I2` remains. Decide what point can be recovered reliably, which data is unproven, and what the system must do to avoid misreporting RPO.

**Exercise 5 — Rollback after new writes.** B1 was captured at 00:00. Upgrade finished at 00:30; from 00:30 to 01:00, 1,000 new orders arrived. At 01:00, a critical defect is discovered. Choose rollback or fail-forward, analyzing data risk, events/outbox, and business sign-off needs.

**Exercise 6 — Choosing the DR environment.** Production runs a Neo4j cluster with GDS/APOC plugins, but the drill environment is a single small instance with no plugins. Identify which tests remain valid, which conclusions **must not** be drawn, and how to design a more representative rehearsal.

**Exercise 7 — Capacity.** The store needs 240 GiB, indexes not included in store need 45 GiB, log/temp peak needs 80 GiB, and headroom is 25%. Calculate storage needs; if store/indexes live on volume A while logs live on volume B, separate the requirements and explain why total GB alone is insufficient.

**Exercise 8 — Incorrect privilege restoration.** After restore, the database is ONLINE, yet a read-only user has write access because security config differed from source. Design a test matrix covering authorization, overlapping roles, tenant boundaries, and secret rotation before GO.

**Exercise 9 — Application failure post-upgrade.** Neo4j version B serves Cypher normally, yet Spring Data Neo4j drops relationship properties during mapping. List tests across entities, repositories, driver, schema, and queries to distinguish mapping bugs from backup corruption.

**Exercise 10 — Writing a runbook.** Draft a timeline for T-7 days, T-1 day, T-1 hour, T0, T+30 minutes, and T+1 day for a downtime upgrade. List artifacts to retain, GO/NO-GO gates, rollback points, owners, and completion evidence.

## 22. Checklist Before Pressing the Upgrade Button

1. **Clear scope:** know databases, Neo4j source/target versions, edition, cluster, plugins, Java Driver, and Spring Data Neo4j.
2. **Valid upgrade path:** checked support matrices, store compatibility, upgrade ordering, and mandatory intermediate steps.
3. **Approved RPO/RTO:** concrete targets established and confirmed by restore drills or documented exceptions.
4. **Restorable backup:** not just existing files; restored, opened DB, verified graph and transactions.
5. **Complete backup chain:** full/incremental/logs/metadata per supported method, checksums, and keys ready.
6. **Clear cutoff:** all writers, queues, CDC consumers, and in-flight transactions controlled or consistently bounded.
7. **External dependencies covered:** system/security metadata, configs, secrets, plugins, drivers, IaC, and TLS each have recovery paths.
8. **Independent copy:** backup isolated from source failure domain with encryption, least privilege, and proper retention.
9. **Upgrade rehearsed:** tested A → B on restored copy, verifying schemas/indexes/constraints and app workloads.
10. **Real rollback verified:** tested B1 → A using compatible procedures; never rely on downgrading stores in place.
11. **Post-cutover writes addressed:** accounted for data generated on the new version and replay/idempotency steps.
12. **Operational readiness:** capacity, monitoring, owners, maintenance window, communications, and halt decision points in place.
13. **Isolated drill:** never reuse live credentials/integrations to fire unintended messages, emails, or payments.
14. **Complete evidence:** backup IDs, versions, timestamps, RPO/RTO metrics, test results, and sign-off approvers archived.
15. **Post-upgrade backups active:** scheduled backups on the new version, restore tests, and post-deployment monitoring active.

**Conclusion:** backing up before an upgrade is not merely running a `dump` command or clicking create snapshot. A reliable plan must **define the data cutoff, use backup mechanisms supported by your version and edition, store copies safely, rehearse restores in an isolated environment, verify the property graph and application, and only then approve the upgrade**. By understanding RPO/RTO, store compatibility, post-cutover writes, and rollback paths, operations teams can decide to proceed, halt, or recover without sacrificing Neo4j data integrity.
