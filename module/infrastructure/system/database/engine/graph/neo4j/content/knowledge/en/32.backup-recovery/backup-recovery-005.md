# Verifying Backup Consistency and Usability

## 1. A Backup File Existing Does Not Mean You Have Recovery Capability

In **DATABASE_ENGINE_GRAPH_NEO4J** systems, nodes, relationships, indexes, constraints, and transactions form the data powering Java Driver applications, Spring Data Neo4j, and Cypher queries. When disk failures, accidental deletions, ransomware attacks, or failed upgrades strike, a backup is valuable only if it can be **restored into a consistent database that starts cleanly and returns accurate results to the application**.

Distinguish states that are too often conflated:

1. **Backup job reports success:** the backup process exited per tool rules.
2. **Artifact exists and is reachable:** the file or file set can be listed, read, and downloaded.
3. **Valid backup chain:** a full backup and required differentials share the same database ID with contiguous transaction ranges.
4. **Consistency check passes:** graph storage structures, indexes, and inspected components show no tool-detected errors.
5. **Restore succeeds:** the backup creates a database on a valid target Neo4j instance.
6. **Application can use it:** the database reaches serving state; data, permissions, queries, and critical business rules all pass.

A system may pass steps 1–2 yet fail at step 3, or pass a consistency check while missing business relationships because the data was already wrong **before the backup**. Therefore, the goal of this lesson in the **Backup and Recovery** chapter is to produce **proven recoverability evidence**, not merely a file ending in **.backup**.

> **Safety rule:** All restore, aggregation, and consistency-check examples in this lesson are for an **isolated testing environment**. Never use options that overwrite a production database, never delete files from the original backup chain, and never start an unverified copy directly to serve live traffic.

## 2. Which Layers Must Be Checked?

| Verification layer | Question | Evidence / tool |
|---|---|---|
| **Inventory** | Do we have a copy of the right database at the right timestamp? | Artifact listing, sizes, backup job ID, timestamp |
| **Metadata & chain** | Do full/differential artifacts share the same database ID and contiguous tx ranges? | **neo4j-admin backup inspect** |
| **Artifact integrity** | Was any file truncated, replaced, or corrupted in transit? | Independent checksum/hash, download and file access check |
| **Physical consistency** | Are nodes/relationships/properties/indexes/count-store structurally valid? | **neo4j-admin database check** |
| **Restore drill** | Can we restore, replay logs, and bring the database ONLINE? | **neo4j-admin database restore**, **CREATE DATABASE**, **SHOW DATABASES** |
| **Logical/business integrity** | Does the graph still satisfy business rules? | Cypher assertions on identifiers, counts, relationship directions, and tenants |
| **Application usability** | Can Java Driver/SDN query with proper permissions and schema? | Smoke/integration tests, auth, index state, latency |
| **Recoverability/SLO** | Can we recover within committed time and data-loss targets? | RPO/RTO measured from drills, logs, reconciliation reports |

**A consistency check does not replace business validation.** An **Order** node missing its relationship to a **Customer** can still be a structurally valid graph on disk. The tool does not know your domain requires every Order to link to exactly one Customer.

**A restore drill also does not replace a consistency check.** A database can start up and answer a few simple queries while an index or a rarely accessed region of data harbors an undetected structural corruption.

### 2.1. Backups Are Different from Replicas

A **backup artifact** is recovery material managed separately from the live database. A **cluster replica/secondary** is a member serving replication and reads, not automatically an independent backup: logic bugs, accidental deletions, and bad writes replicate to replicas as well.

Never use "we have a three-member cluster" as justification to skip backup schedules. If you need to restore to a state prior to a committed accidental deletion, healthy replicas will likely have already applied that exact unwanted change.

## 3. Defining RPO, RTO, and the Recovery Point Under Test

- **RPO — Recovery Point Objective:** maximum acceptable data loss; for instance, recovering to a state no more than **15 minutes** before an incident.
- **RTO — Recovery Time Objective:** maximum total time from incident start until the service is usable again; for instance, **60 minutes**.
- **Actual recovery point:** the last transaction/timestamp present in a **verified backup chain**, not merely when the job started.

Suppose a full backup finishes at 01:00, the final differential contains data up to 01:45, and an incident hits at 02:00. If you restore to 01:45, time-based data loss is about **15 minutes**. To claim RPO compliance, you must prove **01:45 is genuinely the recovered transaction point**, not just a timestamp in a filename.

Similarly, RTO is not just the runtime of the **restore** command. It also includes downloading artifacts from storage, decrypting, recovering transactions, starting the database, verifying permissions, re-pointing applications, and running smoke tests.

A **consistent and restorable** copy that takes 4 hours to recover still fails a system's 1-hour RTO.

## 4. Understanding Backup Types and Edition Limits

Neo4j provides different backup mechanisms by edition:

| Mechanism | Typical scope | What to remember during verification |
|---|---|---|
| **Online backup** via **neo4j-admin database backup** | Self-managed **Enterprise Edition** | Produces full/differential artifacts; requires backup service, source, and proper permissions |
| **Offline dump** via **neo4j-admin database dump** | Includes Community scenarios | Source database must be inactive when dumping; test dump/restore per running version's workflow |
| **Managed service backups** | E.g., Neo4j Aura | Uses provider-documented snapshot/restore features, retention, and tier limits |
| **Filesystem/infrastructure snapshots** | Deployment-dependent | Supported as a backup only with a consistent procedure covering both store and transaction logs |

In **Enterprise**, a **full** backup holds the base database store required for recovery. A **differential** backup holds new transactions relative to an eligible earlier point and **is not an independent database you can run consistency checks on directly**.

**Never hot-copy the data directory and transaction logs via arbitrary file copy** and assume you have a consistent backup. Neo4j's backup mechanism must coordinate storage data with ongoing transactions.

### 4.1. Online Backup Example — Use Only with an Authorized Server and Permissions

~~~bash
# Example on a Neo4j Enterprise backup client host.
# Replace address with the backup endpoint published by your administrator.
bin/neo4j-admin database backup \
  --from=backup-server.example:6362 \
  --to-path=/srv/neo4j-backups \
  --type=FULL \
  neo4j
~~~

This is a **syntax template**, not a command executed in this lesson. The backup address and port must be configured and reachable; run under the appropriate OS account per documentation. Use **--type=FULL** to establish a baseline point; subsequent backups can create **DIFF** or **AUTO** per policy.

In **Aura**, users do not run this command on service hosts. Follow the backup/restore documentation for your specific Aura tier.

## 5. Tier 1 — Checking Backup Inventory and Metadata

### 5.1. Reading Metadata with Inspect

On **current Neo4j Enterprise**:

~~~bash
bin/neo4j-admin backup inspect /srv/neo4j-backups
~~~

Inspect only the **latest backup chain** of the `neo4j` database:

~~~bash
bin/neo4j-admin backup inspect /srv/neo4j-backups \
  --database=neo4j --latest-chain
~~~

You can use **--format=JSON** so automated test tooling reads structured metadata instead of parsing human-readable tables whose formatting may change.

Fields to record in your report:

| Metadata field | Verification question |
|---|---|
| **DATABASE** | Does it match the intended database to restore? |
| **DATABASE ID** | Do full/differential pieces belong to the same physical database, not just share a name? |
| **TIME (UTC)** | Does the backup timestamp coverage meet the schedule? |
| **FULL** | Does the chain start from a valid full backup? |
| **LOWEST TX / HIGHEST TX** | Are transaction ranges contiguous with no missing gaps? |
| **RECOVERED** | Is the full artifact already in a recovered state for direct checking? |
| **COMPRESSED** | Does the verification environment support decompression and have enough temp space? |

**Neo4j releases prior to 2025.07** may require **--show-metadata** to display metadata; newer builds display it by default. Never assume all options behave identically across Neo4j 4.x or 5.x.

### 5.2. Illustrating a Complete Chain vs. Broken Chains

~~~text
Chain A — valid:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=XYZ  tx=[101..140]
  diff-2    db-id=XYZ  tx=[141..170]

Chain B — has a gap:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=XYZ  tx=[101..140]
  diff-2    db-id=XYZ  tx=[151..170]  <-- missing 141..150

Chain C — different database:
  full      db-id=XYZ  tx=[1..100]
  diff-1    db-id=ABC  tx=[101..140]  <-- mismatched DATABASE ID
~~~

Chain A meets metadata prerequisites for further verification. Chains B and C are not valid restore paths merely because they live in the same folder or share a database name. Backup/aggregate tools perform additional checks when reading real artifacts.

An **empty differential** can also appear if no new transactions occurred. Do not automatically treat every numeric gap or empty transaction file as data loss; understand the metadata and rules of your installed version.

### 5.3. Metadata Does Not Guarantee Byte-Level Integrity

**backup inspect** reads descriptive headers and identifies chains; it does not guarantee every byte inside an artifact is uncorrupted or every property graph invariant holds.

When transferring backups from a server to object storage:

1. Record **size**, transfer date, and source/destination paths.
2. Compute **SHA-256/checksums** at copy time or upon immutable locking.
3. Store checksums/manifests in a separate trusted channel or store so an attacker cannot silently alter both artifact and manifest together.
4. Periodically **download back to a recovery environment**, verify hashes, and use Neo4j tooling to check/restore.
5. For **multi-part backup artifacts** (a newer Neo4j feature), ensure **all parts** are stored together and verified; missing a single part means the backup is incomplete.

**A matching SHA-256 only proves the downloaded copy matches what was hashed at the trusted source.** If the source data was already logically wrong or the hash was computed after file corruption, checksums cannot catch that. Consistency checks and restore drills remain essential.

## 6. Tier 2 — Preparing a Recovered Full Backup Before Checking

Neo4j supports **neo4j-admin database check** against a stopped database, a dump, or a **recovered full backup**. The tool **cannot run directly** against a standalone differential backup or an unrecovered full backup.

If you have a **full + multiple differentials** chain, merge and replay them into a recovered full artifact via **aggregate** before running consistency checks. In testing environments, work on a **copy of the artifacts** or keep the original chain intact.

### 6.1. Aggregating a Backup Chain

~~~bash
# Neo4j Enterprise: create a full backup with transactions replayed.
# Keep the original chain for verification and drill rollback.
bin/neo4j-admin backup aggregate \
  --from-path=/srv/neo4j-backups \
  --keep-old-backup=true \
  neo4j
~~~

**Important:** the default for **--keep-old-backup** is **false** in current releases, so if operations must preserve the existing chain, explicitly pass **--keep-old-backup=true** and drill in a test repository. Aggregation can consume **significant temporary space, CPU, I/O, and time** to replay transactions.

Starting in **Neo4j 2025.11**, online full backups can be created with **--skip-recovery=true** to speed up backups, deferring recovery to aggregate/restore time. Thus, **FULL=true** in metadata does not always imply **RECOVERED=true**.

After aggregating, inspect the target artifact again and confirm a **recovered full** matches the database and recovery point under test. When validating a specific historical checkpoint, **do not simply pick the newest file** out of convenience.

### 6.2. Do Not Confuse Aggregate with Restore

**Aggregate** merges a chain into a single artifact for faster checking and recovery. **Restore** materializes database files at a target server location. Even if aggregation succeeds, a restore drill is still required to prove the artifact boots cleanly on an actual Neo4j server and configuration.

## 7. Tier 3 — Running the Neo4j Consistency Checker

### 7.1. Checking Directly Against a Recovered Full Backup

In **Neo4j 2025.09 and later**, `--from-path` on `database check` accepts the path to a specific artifact or directory containing an artifact:

~~~bash
# Replace filename with the inspected recovered full artifact.
# Run on a test host with adequate CPU/RAM/disk.
bin/neo4j-admin database check \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  --report-path=/srv/neo4j-verify/reports \
  neo4j
~~~

**The filename in this example is a placeholder**—not a pre-created file provided by this lesson. Pick the actual artifact generated by aggregate. On older Neo4j versions without `--from-path` support as shown, follow that version's **database check** docs after creating an offline restored copy.

Another option (on a **stopped database**) is:

~~~bash
bin/neo4j-admin database check neo4j
~~~

**Never run the consistency checker directly on a live database in use.** In production, check artifacts or restored databases in an isolated environment so the live service stays up. Never run the checker on an inconsistent snapshot captured mid-write as if it were a clean offline database.

### 7.2. What the Consistency Checker Can Detect

| Check group | Purpose |
|---|---|
| **Graph records** | Structural consistency of nodes, relationships, properties, types, and record links |
| **Index consistency** | Indexes match stored data structures and relationships |
| **Counts** | Element count stores match the graph |
| **Property ownership** | Additional checks on property ownership chains across store records |

Example options:

~~~bash
bin/neo4j-admin database check \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  --check-graph=true \
  --check-indexes=true \
  --check-counts=true \
  --check-property-owners=true \
  --report-path=/srv/neo4j-verify/reports \
  neo4j
~~~

**--check-property-owners** can substantially increase check cost; it is not enabled by default in current docs. For large databases, bound **--threads** and **--max-off-heap-memory** to match test resources; never disable critical checks just to speed up reporting without documenting the reduced scope.

### 7.3. Reading Results Properly

When no inconsistencies are found, the tool typically exits with **exit code 0** and generates no error report. If errors are found, it returns a **non-zero exit code** and may write files like **inconsistencies-*.report** under **--report-path**.

Automated test suites should record:

- Command line and **neo4j-admin** version.
- Checked artifact, hash, and database ID.
- Exit code, tail logs, and report path.
- Which check flags were enabled or disabled.
- Host resources and elapsed duration.

**Do not just grep for "success" in stdout.** Inspect the actual exit code and report, and verify the job did not time out or OOM. An incomplete checker run **must never be marked PASS**.

**Limit of PASS:** the checker confirms the inspected structures have no detected storage errors. It does not prove enough business data exists, does not replace schema constraint checks, and does not prove Java APIs work.

## 8. Tier 4 — Restore Drill into an Isolated Database

A **restore drill** is the strongest test for the question: "If the primary database vanishes, can operations actually bring the system back online?"

### 8.1. Setting Up the Test Environment Before Restore

1. Choose a **standalone Neo4j Enterprise** test instance at the same or a supported newer version per upgrade paths.
2. Provision space for **artifacts, temp files, restored store, transaction logs, and indexes**, not just the compressed archive size.
3. Ensure the target database **does not exist**; never reuse a production database name if any shared network connections exist.
4. Disable or isolate **workers, schedulers, webhooks, and connectors** that could trigger external side effects if restoring production data.
5. Control credentials and sensitive data; test networks must never reach live payment gateways or real email servers.

**Never enable --overwrite-destination=true** in routine drills; overwriting can wipe a target database if a name or path is mistyped. In a cluster, direct overwrites also risk cluster state mismatch; follow dedicated cluster recovery workflows.

### 8.2. Restoring from an Artifact — Enterprise Edition

Assuming a verified backup exists at **/srv/neo4j-verify/neo4j-recovered.backup**:

~~~bash
# Run when database restore_check does not exist / is not in use.
# Execute under the neo4j OS account per documentation.
bin/neo4j-admin database restore \
  --from-path=/srv/neo4j-verify/neo4j-recovered.backup \
  restore_check
~~~

On a server where **database restore_check** was freshly restored, connect to the **system** database with admin privileges after restore completes and create the database:

~~~cypher
CREATE DATABASE restore_check;
~~~

Then:

~~~cypher
SHOW DATABASES
YIELD name, currentStatus, requestedStatus
WHERE name = 'restore_check'
RETURN name, currentStatus, requestedStatus;
~~~

Count it as "started cleanly" only once the database reaches the expected serving status with no recovery/index errors in logs. **The name restore_check** is for this drill, not a mandatory Neo4j name.

**Version/edition note:** syntax and recovery mechanisms evolve. Starting in **Neo4j 2026.03**, **neo4j-admin database copy** is also available in certain workflows. This lesson uses **database restore** because it directly demonstrates restoring a backup artifact. Never run Enterprise commands on Community or Aura assuming identical support.

### 8.3. Backup Chains and PITR

If the input is the **final differential of a chain**, **database restore** can locate the full and intermediate differentials to replay. For a specific point in time, the tool supports **--restore-until** (depending on format and version):

~~~bash
# Skeleton example: apply all transactions committed before the UTC timestamp.
bin/neo4j-admin database restore \
  --from-path=/srv/neo4j-backups/last-differential.backup \
  --restore-until="2026-11-20 09:00:00" \
  restore_pitr_check
~~~

**The source chain and timestamp are illustrative; pick real artifacts containing the transactions to recover.** With a transaction ID `n`, Neo4j restores up to **before transaction `n`** when using ID criteria, not "inclusive of `n`." Similarly, with a UTC timestamp, only transactions committed **before** the chosen timestamp are included in the recovery point.

Never assume retaining a single full backup lets you restore to any minute of the day; you need the corresponding logs/differentials and a retention plan built for your RPO.

## 9. Tier 5 — Verifying Graph Logic After Restore

Once **restore_check** is ONLINE, use **Cypher** to verify business invariants. The queries below assume labels **DemoBackupCustomer**, **DemoBackupOrder**, and relationship **DEMO_BACKUP_PLACED**. **This is illustrative sample data**, not mandatory Neo4j tables.

### 9.1. Sample Fixture to Build a Golden Result

On an **isolated test database**, to create sample data, run once:

~~~cypher
CREATE CONSTRAINT demo_backup_customer_unique IF NOT EXISTS
FOR (c:DemoBackupCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_backup_order_unique IF NOT EXISTS
FOR (o:DemoBackupOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE
  (c1:DemoBackupCustomer {tenantId: 'shop-a', customerId: 'C-1'}),
  (c2:DemoBackupCustomer {tenantId: 'shop-b', customerId: 'C-1'}),
  (o1:DemoBackupOrder {tenantId: 'shop-a', orderId: 'O-1', amountMinor: 15000}),
  (o2:DemoBackupOrder {tenantId: 'shop-a', orderId: 'O-2', amountMinor: 8000}),
  (o3:DemoBackupOrder {tenantId: 'shop-b', orderId: 'O-1', amountMinor: 9000}),
  (c1)-[:DEMO_BACKUP_PLACED]->(o1),
  (c1)-[:DEMO_BACKUP_PLACED]->(o2),
  (c2)-[:DEMO_BACKUP_PLACED]->(o3);
~~~

This sample has **2 Customers, 3 Orders, and 3 relationships**, intentionally sharing **customerId/orderId** values across two tenants to catch queries that omit tenant filtering. Do not re-run the **CREATE** block on a database that already holds the fixture; it can fail uniqueness constraints or create duplicate relationships. During backup drills, seed the fixture **before taking the backup** if using it as a golden result.

### 9.2. Checking Counts and Identifier Lists

~~~cypher
MATCH (c:DemoBackupCustomer)
RETURN count(c) AS customerCount;
~~~

~~~cypher
MATCH (o:DemoBackupOrder)
RETURN o.tenantId AS tenant,
       o.orderId AS orderId,
       o.amountMinor AS amountMinor
ORDER BY tenant, orderId;
~~~

With the fixture above, expect **customerCount = 2** and the Order list:

~~~text
shop-a  O-1  15000
shop-a  O-2   8000
shop-b  O-1   9000
~~~

**Never compare a restored database against live production if production continued receiving writes after the recovery point.** Expectations must match the **snapshot/golden manifest at the exact backup timestamp**.

### 9.3. Checking Duplicate Business Keys

~~~cypher
MATCH (o:DemoBackupOrder)
WITH o.tenantId AS tenant,
     o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenant, orderId, copies;
~~~

This must return **zero rows** if uniqueness is properly enforced. A **uniqueness constraint** prevents duplicates when properties are present, yet does not automatically ensure every node has required IDs:

~~~cypher
MATCH (o:DemoBackupOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS missingBusinessIds;
~~~

Expect **0**. Nodes missing business keys represent a logic/data-quality bug even though the physical consistency checker can still PASS.

### 9.4. Checking Relationships and Tenant Isolation

~~~cypher
MATCH (c:DemoBackupCustomer {
  tenantId: 'shop-a',
  customerId: 'C-1'
})-[:DEMO_BACKUP_PLACED]->(o:DemoBackupOrder)
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Expect **O-1, O-2**. To detect cross-tenant links:

~~~cypher
MATCH (c:DemoBackupCustomer)-[r:DEMO_BACKUP_PLACED]->
      (o:DemoBackupOrder)
WHERE c.tenantId <> o.tenantId
RETURN count(r) AS crossTenantRelationships;
~~~

Expect **0**. To detect Orders with **zero or more than one** placing Customer:

~~~cypher
MATCH (o:DemoBackupOrder)
OPTIONAL MATCH (c:DemoBackupCustomer)-[:DEMO_BACKUP_PLACED]->(o)
WITH o, count(c) AS owners
WHERE owners <> 1
RETURN o.tenantId AS tenant, o.orderId AS orderId, owners;
~~~

This must return **zero rows** if the business contract requires each Order to belong to exactly one Customer. If your domain allows multiple customers per order, adapt the assertion to the domain rather than imposing it blindly.

### 9.5. Checking Schema and Indexes

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, state, populationPercent
RETURN name, type, state, populationPercent
ORDER BY name;
~~~

Do not just count indexes. Confirm **names/types, labels, properties, and ONLINE state** per application requirements. **POPULATING** indexes may need time to finish after restore; **FAILED** indexes must be investigated before serving traffic.

After restore, also run the application's critical **golden Cypher queries**: lookups by key, path traversals, tenant filters, idempotent MERGE on test databases, and queries involving multiple relationships and NULLs.

## 10. Tier 6 — Verifying Application Access to the Restored Copy

The database may be ONLINE and manual queries may succeed while Java Driver or Spring Data Neo4j still fail because:

- DNS, Bolt URI, TLS, or certificates are wrong.
- Application accounts were not created/granted expected roles.
- Driver/SDN points to the wrong database or cluster.
- **APOC/GDS** required by Cypher queries is missing or blocked by allowlists.
- A changed constraint/index breaks repository mapping or queries.
- Background jobs accidentally send real emails/payments once the restored environment comes up.

### 10.1. Smoke Test with Java Driver

The Java snippet below is **read-only** against the test restored database, using modern Java Driver idioms. The Driver is created once and sessions are properly closed.

~~~java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.SessionConfig;

String uri = System.getenv("RESTORE_NEO4J_URI");
String user = System.getenv("RESTORE_NEO4J_USERNAME");
String password = System.getenv("RESTORE_NEO4J_PASSWORD");

try (var driver = GraphDatabase.driver(
        uri, AuthTokens.basic(user, password))) {

    driver.verifyConnectivity();

    try (var session = driver.session(
            SessionConfig.forDatabase("restore_check"))) {
        var orders = session.executeRead(tx -> tx.run("""
            MATCH (c:DemoBackupCustomer {
                tenantId: $tenant, customerId: $customer
            })-[:DEMO_BACKUP_PLACED]->(o:DemoBackupOrder)
            RETURN o.orderId AS orderId
            ORDER BY orderId
            """, Map.of("tenant", "shop-a", "customer", "C-1"))
            .list(row -> row.get("orderId").asString()));

        if (!orders.equals(java.util.List.of("O-1", "O-2"))) {
            throw new IllegalStateException("Restore smoke test failed");
        }
    }
}
~~~

**Run prerequisites:** the fixture was included in the backup beforehand and restored, environment variables point to the **testing environment**, and the user has read permissions. If a real backup lacks demo labels, substitute a **golden query against real business data**—never insert demo nodes after restoring and claim that proves the backup contained them.

**Additional Spring Data Neo4j checks:** execute key repository queries and transaction boundaries against the test connection config, especially composite business keys, relationship mapping, lazy/eager loading, and custom Cypher queries. Never call only **driver.verifyConnectivity()** and assume the entire application is ready.

### 10.2. Security and the `system` Database

In Neo4j Enterprise, user/role metadata has dedicated backup/restore mechanisms. After restoring a data backup, **never assume all users, roles, and privileges were automatically applied to the new DBMS**. Restore documentation notes you may need to execute **restore_metadata.cypher** against the **system database** to restore privileges.

Distinguish:

1. **Data database:** nodes, relationships, indexes/constraints, and transactional state.
2. **System database / metadata:** database definitions, privileges, and DBMS-scoped admin components.
3. **Runtime environment:** plugin JARs, environment variables, `neo4j.conf`, TLS, secrets, DNS, and topology.

Components outside data artifacts require **runbooks/configuration as code** and separate drills. Restoring the graph while forgetting access controls can break the application or leave the environment overly permissive.

## 11. PASS/FAIL Criteria for a Restore Drill

| Check | PASS when | FAIL/BLOCKED when |
|---|---|---|
| **Artifact** | All files/parts readable; checksums match trusted manifest | Missing files, hash mismatch, download error |
| **Chain** | Matching database ID and contiguous transactions to recovery point | Missing differential, mismatched database ID |
| **Consistency** | Checker completes, exit code 0, checked scope recorded | Non-zero exit code, incomplete run, inconsistency reported |
| **Restore** | Restores into new database cleanly without unintended overwrite | Replay error, insufficient disk, bad permissions/version |
| **Availability** | Database ONLINE, Bolt/TLS and app permissions work | Fails to start, auth error, queries fail |
| **Graph invariants** | Golden queries, IDs, counts, relationships, and tenant scope match | Missing/duplicate data or bad links |
| **RPO** | Recovery point falls within data-loss budget | Missing history or recovery point too stale |
| **RTO** | End-to-end duration within approved SLO | Restore or warm-up too slow |
| **Security** | No data leaks, no live production side effects, proper roles | Test environment accidentally accesses real external systems |

**A technical PASS does not mean the whole system is safe.** For example, if the checker PASSES yet business validation FAILS, the overall drill result must be **FAIL**, not a "partial PASS" for production readiness.

### 11.1. Measuring RPO and RTO with Evidence

Record timestamps:

~~~text
incident_reference_at        = 2026-11-20T10:00:00Z
backup_recovery_point_at     = 2026-11-20T09:47:00Z
restore_drill_started_at     = 2026-11-20T10:05:00Z
database_online_at          = 2026-11-20T10:29:00Z
smoke_tests_passed_at       = 2026-11-20T10:35:00Z
~~~

In this example, **estimated time-based data loss = 13 minutes**. Elapsed time from **drill start to smoke-test pass = 30 minutes**, while elapsed time from **incident reference to smoke-test pass = 35 minutes**. Your organization's RTO definition must state clearly when the clock starts; never mix measurement definitions across reports.

If you only have a **transaction ID** without an exact commit timestamp, measure RPO in data/transaction units and corroborate timing with auxiliary evidence; never fabricate minute lags from IDs.

## 12. Negative Tests That Catch Unusable Backups

Beyond happy-path drills, run negative tests on a **test copy**, never damaging original backup artifacts.

| Simulated failure scenario | What must be proven |
|---|---|
| **Missing a differential** | Inspect/aggregate/restore does not mistakenly treat the chain as complete |
| **Truncated file** | Checksum or read/recovery detects corruption; pipeline FAILS |
| **Mismatched database ID** | Backups are not chained together merely because database names match |
| **Unrecovered full only** | Consistency check is not run directly with a false PASS recorded |
| **Multi-part artifact missing a part** | Inventory detects missing part instead of attempting blind restore |
| **Colliding target database name** | Unintended overwrite is blocked |
| **Insufficient temp/disk** | Runbook reports resource blocker without corrupting source copies |
| **App role lacks READ** | Smoke test under the application account FAILS properly |
| **Target Neo4j older than source** | Detects unsupported downgrade/restore to older version |
| **Backup holds logically bad data** | Consistency check may PASS while graph assertions FAIL |

**Not all negative tests belong in production.** Simulated missing files or byte corruption run on a **copy** in an isolated test area. The goal is verifying **error detection**, not causing a real outage.

## 13. Check Schedule and CI/CD Integration

An appropriate schedule depends on database criticality, backup size, RPO/RTO, and upgrade cadence. Illustrative policy example:

| Suggested cadence | Activity | Evidence to store |
|---|---|---|
| **Every backup** | Verify job, inventory, database ID, tx-range, checksum | Backup manifest and logs |
| **Daily** | Inspect latest chain; alert on missed runs or broken chains | Chain report, backup age |
| **Weekly** | Aggregate/consistency check on selected backup | Exit code, report, checked scope |
| **Monthly** | Restore drill into isolated environment + golden queries | RPO/RTO and smoke-test report |
| **Before major upgrade/migration** | Restore old-version artifact and test upgrade/schema | Compatibility result and rollback plan |
| **After major changes** | Targeted drill for security, RBAC, cluster/CDC if used | Evidence from matching workload/topology |

Cadences are **process suggestions**, not official Neo4j guarantees. Critical databases may need more frequent drills; very large databases can sample checkpoints while ensuring full-chain coverage over a defined period.

### 13.1. Conceptual Verification Pipeline

~~~text
Backup job completes
  -> Verify artifact presence and checksum
  -> neo4j-admin backup inspect: database ID, TX range, chain
  -> Copy chain to staging, preserving originals
  -> Aggregate into recovered full (if needed)
  -> neo4j-admin database check: exit code, report
  -> Restore into isolated database
  -> CREATE DATABASE and wait for ONLINE
  -> Cypher assertions + Java Driver/SDN smoke tests
  -> Measure recovery point, RPO/RTO
  -> Store PASS/FAIL result + artifact hashes
  -> Safely tear down test database after saving evidence
~~~

If an earlier step FAILS, **do not** mark downstream steps PASS just because "a few queries still ran." Pipelines must support a **BLOCKED** state when permissions, resources, fixtures, or suitable test environments are missing.

### 13.2. Manifest and Drill Log

Store one report per **database + recovery point**:

~~~yaml
# Example report format; NOT a Neo4j configuration file.
database: neo4j
source_neo4j_version: "2026.10.2"
restore_neo4j_version: "2026.10.2"
backup_type: "full-plus-differential"
database_id: "example-database-id"
last_transaction_id: 170
artifact_sha256_verified: true
chain_verified: true
consistency_exit_code: 0
restore_online: true
business_invariants_passed: true
application_smoke_passed: true
measured_rpo_minutes: 13
measured_rto_minutes: 35
result: PASS
~~~

These numbers are **illustrative**; never cite them as evidence for a real backup. For production reports, include hashes/IDs, actual storage paths, and real UTC timestamps; never store secrets in manifests.

## 14. Version Compatibility, Clusters, and Aura

### 14.1. Neo4j 5.x vs. Calendar-Versioned Releases

Modern commands like **neo4j-admin backup inspect**, **backup aggregate**, and **database check --from-path** evolved in names/options across releases. Notably:

- **database check --from-path** accepts artifacts directly starting in **2025.09**.
- **backup inspect** shows metadata by default starting in **2025.07**.
- **--skip-recovery** on online full backups was introduced in **2025.11**.
- Some modern releases support **split backup archives**; all parts must be retained.

Therefore **always check `neo4j-admin --help` on both source and target versions** and read the migration guide. Commands in this lesson cannot be copied unmodified onto Neo4j 4.x.

**Restoring a backup into a Neo4j version older than the one that created it is unsupported.** Practice on compatible versions per upgrade docs; never attempt to "roll back by opening a newer store with an older binary" instead of restoring a pre-upgrade backup.

### 14.2. Clusters Are More Than Restoring onto One Arbitrary Node

In a Neo4j cluster, databases also carry allocation, consensus, and topology state. Restoring directly onto one member with **--overwrite-destination** is not the standard way to replace a cluster-wide database. Neo4j docs define procedures such as **recreate database from URI**, **designated seeder**, or version-specific cluster restores.

A **standalone restore drill** proves artifact health, consistency, and many business queries, yet **does not test failover, catch-up, leader election, or routing**. If SLAs require post-outage cluster availability, run dedicated topology drills.

### 14.3. Neo4j Aura

In **Aura**, manage snapshots/backups and restores via service capabilities rather than logging into servers to run **neo4j-admin database restore** or edit filesystems. Required evidence stays similar: backup point, trial restore to a supported test instance, verification queries, connectivity permissions, and RPO/RTO measured per service tier.

Do not assume Aura shares the same CLI syntax or privileges as self-managed Enterprise. Retention windows, restore quotas, point-in-time recovery support, and backup options are governed by your **tier and current Aura documentation**.

## 15. Common Errors and Remediation

| Symptom | Possible cause | Action |
|---|---|---|
| Backup job SUCCESS yet cannot restore | Missing chain file, corrupt artifact, version mismatch | Inspect chain, checksums, aggregate, and run restore drill |
| Full backup rejected by consistency check | Artifact has **RECOVERED=false** | Aggregate/recover before checking |
| Differential only | Missing eligible base full backup | Fetch full chain; never assume a standalone diff is usable |
| Unclear which database backup belongs to | Same name but different database ID | Inspect metadata, select matching database ID |
| Check reports inconsistencies | Inconsistent store/index/counts/properties | Preserve report, quarantine artifact, investigate root cause; do not serve |
| Restore fails on disk space | Insufficient temp/staging/store space | Expand staging per plan; never delete original backups |
| Database ONLINE yet app cannot log in | User/role metadata, TLS, or secrets mismatch | Check `system`/auth and connection settings |
| Counts match yet data is wrong | Asserted only total node counts | Compare business key sets, relationships, tenants, and golden queries |
| Restore succeeds yet very slow | Replaying many differentials, slow download, index/page-cache warm-up | Measure each RTO stage; consider periodic aggregation |
| Smoke test on restore triggers real events | Test workers/connectors not isolated | Disable external side effects; use sandbox/stubs |
| Backup exists in storage but cannot download | Cloud permissions, encryption keys, retention tier, or lost credentials | Drill fetching copies using the actual recovery account |
| Need timestamp recovery with no matching tx | Chain lacks recovery point or logs were pruned | Pick available point, report actual RPO; fix backup policy |

## 16. Practice Exercises

### Exercise 1 — Backup Chain Metadata

Given full **tx 1–80**, differential A **81–100**, and differential B **111–130**, can this be called a complete chain up to tx 130? Identify the missing range and what other metadata fields beyond transaction IDs must be compared.

### Exercise 2 — Unrecovered Full

A job creates a full backup with **RECOVERED=false**. An operator runs **neo4j-admin database check** directly on the artifact and it fails. Describe the correct **inspect → aggregate/recovery → check** sequence and why the failed result must not be overridden to PASS.

### Exercise 3 — Separating Structural Consistency from Business Invariants

A backup passes the consistency checker, yet Order O-1 lacks a Customer. Write a Cypher query to find Orders without a **DEMO_BACKUP_PLACED** relationship and explain why the checker can still PASS.

### Exercise 4 — Designing a Restore Drill

You are handed a backup chain in object storage. List the steps to verify hashes, chain, restore, access permissions, ONLINE status, and two critical business queries. At which step must you guarantee the environment cannot send real emails or payments?

### Exercise 5 — RPO/RTO

An incident occurs at 13:00 UTC, the last recovery point is 12:48 UTC, and the service returns with passing smoke tests at 13:42 UTC. Calculate time-based data loss and RTO measured from incident start; determine whether the system meets a **15-minute RPO** and **45-minute RTO**.

### Exercise 6 — Verifying Tenant Isolation

The fixture contains **shop-a / C-1** and **shop-b / C-1**. Write queries to compare Orders per tenant, detect relationships linking two different tenants, and detect duplicate business keys **within the same tenant**.

### Exercise 7 — Valid Backup, Unready Operations

A backup aggregated and passed consistency check. The restored database is ONLINE, yet Spring Data Neo4j fails because the account lacks read privileges and APOC procedures did not load. Distinguish **artifact correctness** from **service readiness**, and propose a checklist to move from BLOCKED to PASS.

## 17. Summary

For Neo4j, a **trustworthy backup** is one whose **source chain and metadata have been inspected**, **byte integrity verified**, **consistency checked**, **restored into an isolated database**, and **verified at both graph and application levels**.

Pipeline to remember:

**Inventory & checksum → inspect database ID/transaction chain → aggregate into recovered full → database check → restore drill → graph invariants → Java Driver/SDN smoke test → RPO/RTO evidence.**

In production, never substitute a green backup job or a node count for the entire pipeline; above all, never overwrite a live database for a test. Backup schedules must be paired with **recovery drill schedules**, because the ultimate goal is not accumulating files, but **restoring accurate data and bringing the service back within committed limits**.

### Official Neo4j Documentation

- [Neo4j Operations Manual – Backup and restore](https://neo4j.com/docs/operations-manual/current/backup-restore/)
- [Neo4j Operations Manual – Back up an online database](https://neo4j.com/docs/operations-manual/current/backup-restore/online-backup/)
- [Neo4j Operations Manual – Inspect the metadata of a backup file](https://neo4j.com/docs/operations-manual/current/backup-restore/inspect/)
- [Neo4j Operations Manual – Aggregate a backup chain](https://neo4j.com/docs/operations-manual/current/backup-restore/aggregate/)
- [Neo4j Operations Manual – Check database consistency](https://neo4j.com/docs/operations-manual/current/backup-restore/consistency-checker/)
- [Neo4j Operations Manual – Restore a database backup](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-backup/)
- [Neo4j Operations Manual – Back up an offline database](https://neo4j.com/docs/operations-manual/current/backup-restore/offline-backup/)
- [Neo4j Operations Manual – Restore a database dump](https://neo4j.com/docs/operations-manual/current/backup-restore/restore-dump/)
- [Neo4j Java Driver Manual – Connect to the database](https://neo4j.com/docs/java-manual/current/connect/)
