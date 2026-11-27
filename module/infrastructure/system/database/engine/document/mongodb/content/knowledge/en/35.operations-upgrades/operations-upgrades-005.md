# Upgrade Preparation: Backups, Compatibility Matrices, and Testing

Upgrading MongoDB is more than changing the `mongod` version number and restarting. For a system serving live users, an upgrade can affect **data, availability, driver wire protocols, replication, sharding, indexes, transactions, security features, and the ability to recover if an incident occurs**.

An upgrade can succeed at the infrastructure level—every process running the new binary—and still break the system:

- An application uses an older MongoDB Driver incompatible with the new server.
- An aggregation stage or query planner change degrades p99 latency.
- A scheduled job relies on a deprecated API.
- A replica set loses quorum when operators restart nodes in the wrong order.
- A backup exists, yet cannot restore within the committed RTO.
- The new version enables a feature incompatible with the old binary, invalidating a "quick downgrade" plan.
- Atlas Search/Vector Search indexes must rebuild or lack readiness in the target deployment setup.
- Administrative accounts lack permissions to inspect or execute specific upgrade steps.
- Testing on 1,000 documents fails to predict behavior on a production collection of hundreds of millions of documents.

Therefore, **upgrade preparation** is an evidence-driven decision workflow built on three pillars:

1. **Backups and recoverability:** can we restore accurate data and system state if the upgrade fails?
2. **Compatibility matrix:** does every component support the target version and chosen transition order?
3. **Testing:** on a representative environment, do correctness, performance, failover, and operations meet requirements?

This lesson, **"Upgrade Preparation: Backups, Compatibility Matrices, and Testing"**, belongs to the **Operations and Upgrades** chapter in the **Database Engine Document MongoDB** module. It covers both **MongoDB Atlas** and **self-managed MongoDB**, including standalone, replica set, and sharded cluster topologies with their respective nuances.

> **Core principle:** Approve a production upgrade only with an **officially documented supported upgrade path**, a **restore-tested backup**, a **representative test environment passing acceptance criteria**, and an **approved stop/recovery plan**. "Having a backup", "the binary starts", and "a few queries pass" are not enough.

---

## 1. Distinguishing Upgrade Objectives

Multiple types of changes are often lumped together as an "upgrade".

| Change Type | Example | Primary Risk |
|---|---|---|
| Patch upgrade | Upgrading patch version within the same server series | Regression, restart/failover |
| Major version upgrade | Moving across MongoDB Server release lines | Compatibility, FCV, deprecated features |
| MongoDB Driver upgrade | Newer Java Sync / Node / Python driver | API, TLS, retries, serializers, connection pools |
| OS/container upgrade | Newer Linux distribution, kernel, base image | Library support, certificates, filesystems |
| Atlas cluster tier change | Changing tier, region, or topology | Capacity, networking, SLA, cost |
| Replica set topology change | Adding, removing, or relocating members | Quorum, replication lag, availability |
| Sharded cluster upgrade | `mongos`, config servers, shards | Version ordering, balancer, routing |
| Storage/index change | Index rebuild, shard key, collation | Query performance, disk headroom |
| Security mechanism change | TLS CA, auth, KMS, key rotation | Client/member connectivity |
| Search/Vector Search change | Search nodes, mappings, embedding models | Indexing lag, search compatibility |

**Do not bundle unrelated changes into the same upgrade window** when they can be separated. Upgrading the server, rotating the TLS CA, bumping the driver, migrating regions, and modifying dozens of indexes at once makes root-cause analysis far harder.

### 1.1. Patch Upgrades Are Not "Zero-Risk"

Patch releases target bug fixes, security updates, and stability improvements, yet can still introduce regressions on a specific workload or environment.

Therefore:

- Read release notes;
- Review known issues;
- Verify driver and tooling versions;
- Run canary/staging tests;
- Plan restarts/failovers;
- Define explicit rollback/restore decision rules.

### 1.2. Major Upgrades Require Checking FCV Too

MongoDB distinguishes:

- **Binary version:** the running `mongod`/`mongos` executable version.
- **Feature Compatibility Version (FCV):** the setting controlling which features and on-disk formats are enabled, affecting upgrade and downgrade compatibility.

A deployment can run new binaries while **FCV intentionally stays at the previous level** as a staged phase of the upgrade process.

Never equate "new binaries running" with "all major upgrade steps complete".

### 1.3. Release-Time Assumptions

Details regarding version support, FCV, operating systems, drivers, and Atlas tiers evolve across MongoDB releases. Accordingly, this guide states **principles and structural examples**, while exact minimum versions and transition paths must be verified against the **Upgrade Procedures, Compatibility Matrix, Release Notes, and Atlas upgrade policies** matching your target date and release.

Never assume you can skip multiple major versions directly or downgrade simply by reinstalling an old binary.

## 2. Upgrade Objectives and Success Criteria

Before touching anything, answer:

1. Why are we upgrading?
2. What are the source and target versions?
3. Which features will be enabled post-upgrade?
4. Is downtime acceptable, or what maintenance window applies?
5. What are acceptable thresholds for errors, latency, and replication lag?
6. What are our RPO and RTO?
7. If something fails, when and how do we roll back?
8. Who holds GO/NO-GO authority?

### 2.1. Example Measurable Objectives

A team might define:

```text
Reason:
  Migrate from source release to supported target release,
  receive security fixes and newer query capabilities.

RPO:
  <= 15 minutes for declared disaster scenarios.

RTO:
  <= 2 hours to restore critical operations.

Availability:
  Critical API error rate within existing SLO.

Performance:
  Read p95 and write p95 regress no more than approved budget.
  No sustained p99 latency spike beyond release guardrail.

Correctness:
  No data loss, incorrect writes, cross-tenant access, or failed invariants.

Recovery:
  Restore drill completed and evidence approved.
```

These thresholds are **examples**; every product needs concrete goals matching its criticality. For a payment system, "no lost transactions" requires a stricter contract than a transient data service.

### 2.2. Completion Criteria

An upgrade is complete only when:

- All target components run the intended version;
- Topology is healthy and replication is stable;
- FCV is at the approved planned level;
- Applications and drivers are functioning;
- Business smoke tests and regression tests pass;
- Query latency and error rates stay within guardrails;
- Backups and monitoring remain operational;
- Search/Vector/CDC features are verified where applicable;
- Runbooks and system inventory are updated.

"No errors in startup logs" is not enough.

## 3. Building a Pre-Upgrade System Inventory

Inventory the **entire system**, not just `db.version()`.

Example:

```text
Environment: production
Platform: MongoDB Atlas / self-managed
Topology: replica set / sharded
Source MongoDB Server version:
Target MongoDB Server version:
Current FCV:
Target FCV:
Operating systems / images:
MongoDB Drivers and versions:
Backup method:
PITR availability:
Recovery objectives:
Authentication and TLS:
KMS / encryption:
Search / Vector Search:
Change streams / CDC:
Analytics / BI consumers:
Data size / index size:
Current p95/p99:
Owners / approval:
```

### 3.1. Commonly Forgotten Components

- `mongod` primary and secondaries;
- `mongos` routers;
- Config server replica set;
- Hidden, delayed, and analytics members;
- Backup agents and monitoring exporters;
- Java/Python/Node/Go drivers;
- `mongosh` and MongoDB Database Tools;
- MongoDB Compass;
- ODMs/frameworks such as Spring Data MongoDB;
- Custom serializers and codecs;
- Change stream consumers and resume token stores;
- Atlas Search / Vector Search;
- Infrequently scheduled jobs;
- Third-party connectors, BI tools, and stream processors;
- Authentication integrations, certificates, and KMS;
- Kubernetes Operators or automation tools if used.

An upgrade tested only against primary APIs while ignoring month-end reporting jobs can miss critical compatibility breaks.

### 3.2. Collecting Versions with Read-Only Commands

In `mongosh`, when authorized:

```javascript
db.version();
```

Inspect server build metadata:

```javascript
db.adminCommand({
  buildInfo: 1
});
```

Check FCV:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

On the appropriate deployment, check topology:

```javascript
db.hello();
```

In a replica set:

```javascript
rs.status();
```

In a sharded cluster via `mongos`:

```javascript
sh.status();
```

These commands are **read-only**, though many require privileges. Never post raw outputs in public channels, as they can leak hostnames, topology, user/role metadata, or operational details.

### 3.3. Do Not Rely Only on the Connected Node's Version

If a client connects to one secondary or `mongos`, `db.version()` reflects only that server endpoint—it **does not prove every component in the cluster runs the same version**.

Verify every node/component group via monitoring, automation, and topology checks.

## 4. Capturing a Pre-Change Baseline

Without knowing how fast and stable the system was **before the upgrade**, spotting a post-upgrade regression is difficult.

### 4.1. Mandatory Baseline

| Category | Metrics to Record |
|---|---|
| Data | Document counts, logical size, storage/index sizes |
| Reads | Read ops/s, query p50/p95/p99, slow query rate |
| Writes | Insert/update/delete throughput, write p50/p95/p99 |
| Errors | HTTP/database error rates, retries, timeout breakdown |
| Connections | Current/active/available, pool waits, connection churn |
| Cache | WiredTiger cache/eviction, dirty pages, cache misses |
| CPU/I/O | CPU, memory, disk IOPS/latency, free disk |
| Replica set | Member health, elections, replication lag, oplog window |
| Sharding | Per-shard load, chunk distribution, routing, balancer |
| Backup | Last successful backup, retention, last restore drill |
| Search | Search/Vector index readiness, indexing lag |
| CDC | Change stream consumer lag and error rate |
| Business | Checkout/search/order metrics, background jobs |

### 4.2. Capture Hourly and Daily Variations

An evening peak can differ vastly from daytime averages. Sample representative baselines across:

- Normal hours;
- Peak hours;
- Weekends;
- Reporting/batch days;
- Imports/exports;
- Flash sales or campaign events;
- Large vs. small tenants.

Never benchmark at 03:00 and conclude the upgrade has no impact on 20:00 peak traffic.

### 4.3. Check Free Capacity

Upgrades, restarts, initial syncs, index builds, and restores all consume disk headroom. A volume sitting at a few percent free space must be addressed beforehand, even if queries currently succeed.

Questions to ask:

- How fast do datasets and indexes grow?
- Is space needed for temp files, journal, or backup staging?
- Is there enough room for rollback or restore?
- Does the new storage engine/version change footprint?
- Can disk capacity be expanded safely?
- Are disk pressure alerts active?

## 5. Backups: Protecting Data Before Upgrading

A critical rule:

> **Never start a critical production data upgrade merely because a dashboard says "backup job SUCCESS".** You must confirm the backup **covers the full scope**, **maintains consistency**, **has passed a restore test**, and **has accessible encryption keys and permissions**.

### 5.1. Backup Methods

| Method | Characteristics | Upgrade Notes |
|---|---|---|
| Atlas Cloud Backup / snapshots | Managed backups per tier/policy | Verify retention, restore target, region, PITR |
| Filesystem/block snapshots | Point-in-time infrastructure snapshot | Requires a consistent procedure for MongoDB topology |
| `mongodump` / `mongorestore` | Logical BSON export/import | Does not guarantee point-in-time consistency on all workloads/topologies |
| Oplog / PITR | Restores to a timestamp within supported retention | Needs base backup, oplog coverage, and compatible tools |
| Third-party backup agent | Vendor/tool-managed backup | Verify certification, encryption, and restore semantics |

No single method fits every deployment. Choice depends on RPO/RTO, Atlas tier, collection size, sharding, write throughput, and compliance rules.

### 5.2. Logical Backups Are Not Automatically Consistent Snapshots

Example tool usage:

```bash
mongodump \
  --uri "$MONGODB_URI" \
  --archive="/secure-backups/preupgrade.archive.gz" \
  --gzip
```

This is an **illustrative command**, not something to run directly on production without planning. The syntax uses Unix shell line continuations; Windows PowerShell syntax and environment variables differ.

While data is actively changing, a logical dump can capture collections at slightly different timestamps. Flags such as `--oplog` have **specific deployment conditions and limits** and do not apply universally to every sharded cluster or scenario. To obtain a consistent restore point, follow the **official backup procedure for your topology**.

### 5.3. Backing Up a Sharded Cluster

A sharded cluster consists of:

```text
mongos
   ├── Config server replica set
   ├── Shard A replica set
   ├── Shard B replica set
   └── Shard C replica set
```

You cannot snap individual shards at arbitrary timestamps and assume the resulting snapshots form a cluster-consistent image.

Use a procedure supported by MongoDB or your backup vendor that coordinates:

- Config server metadata;
- Data across all shards;
- Active transactions and chunk migrations;
- Snapshot ordering/timing;
- PITR availability;
- Restore topology.

### 5.4. Backup Files Are Sensitive Data

Backups may contain every collection, user record, and data no longer exposed by the application.

Therefore enforce:

- Encryption at rest;
- TLS in transit;
- Least-privilege IAM/ACLs;
- KMS keys and rotation policies;
- Non-public storage;
- Retention and deletion policies;
- Access auditing;
- Immutability / tamper protection where required;
- Placement outside the primary failure domain;
- Integrity verification.

Never store temporary backups on a personal laptop or a public bucket just because it is "a test copy".

## 6. RPO, RTO, and Recovery Points

Before upgrading, align on:

- **RPO (Recovery Point Objective):** maximum acceptable data loss in a declared failure scenario.
- **RTO (Recovery Time Objective):** maximum acceptable time to restore critical service operations.

Example:

```text
Business RPO: 15 minutes
Business RTO: 2 hours
Last snapshot: 12 hours ago
PITR: None
```

In a cluster-wide data loss scenario, this system **has no evidence of meeting a 15-minute RPO** with only a 12-hour-old snapshot.

### 6.1. Recovery Model

```text
Base backup at T0
        │
        ├── Oplog/continuous changes T0 → T1
        ├── Oplog/continuous changes T1 → T2
        └── Target recovery point T2
```

PITR is available only when the backup tool, cluster tier, and retention support it with sufficient change-log coverage. It is not an automatic property of every MongoDB deployment.

### 6.2. Recoverability Also Depends on Keys

If data is encrypted, valid **KMS/encryption keys must be usable** during restore.

An encrypted backup whose key is lost or revoked cannot be restored. Your upgrade plan must safeguard:

- Backup artifacts;
- Encryption keys;
- TLS/authentication secrets needed for restore;
- Connectivity and access permissions to the restore environment;
- Network/DNS dependencies for the restored system.

### 6.3. Backup Success Differs from Restore Success

These are two separate questions:

1. Did the tool produce a backup artifact?
2. From that artifact, can we restore complete, accurate, accessible data fast enough?

Only the second proves recoverability.

## 7. Restore Drill: Testing Recovery Before Upgrading

A **restore drill** is a structured recovery test in an isolated environment using data governed by appropriate security controls and clear measurement targets.

```text
Approved backup artifact
          │
          ▼
Isolated restore environment
          │
          ▼
Restore database/topology
          │
          ▼
Validate integrity and consistency
          │
          ▼
Run application smoke tests
          │
          ▼
Measure RPO/RTO
          │
          ▼
Record evidence and remediation
```

### 7.1. Steps

1. Select the latest backup within scope.
2. Record backup ID, timestamp, cluster/version, and retention.
3. Prepare an isolated restore target with equivalent security controls.
4. Verify KMS keys, credentials, and networking.
5. Restore using the approved tool and procedure.
6. Verify collections, indexes, sample records, and invariants.
7. Run application smoke tests.
8. Measure elapsed time from recovery start to serviceable state.
9. Record potential data loss relative to the actual recovery point.
10. Store redacted evidence and review findings.

### 7.2. `mongorestore` Example — Isolated Target Only

```bash
mongorestore \
  --uri "$ISOLATED_RESTORE_URI" \
  --archive="/secure-backups/preupgrade.archive.gz" \
  --gzip
```

**Never aim this command at production as a test.** Flags like `--drop` delete collections on the restore target; use them only when understood and after verifying the target URI.

Restored data must be protected from unauthorized access, especially if it contains PII. Never load raw production data into staging without masking policies or proper controls.

### 7.3. Post-Restore Data Validation

Checks include:

- Required collections exist;
- Document counts align with the recovery point;
- Unique constraints hold;
- Indexes exist or rebuild cleanly;
- Accounts/roles and encryption work in the restored setup;
- Application reads/writes succeed on valid test records;
- Transactions and business invariants pass;
- Replication/sharding topology is healthy;
- Search/Vector indexes become ready where required;
- Background consumers work;
- RPO/RTO goals are met.

**`db.stats()` succeeding alone does not prove recovery is complete.**

## 8. Backups Must Align with Your Rollback Plan

Do not wait until an upgrade fails to ask "which server version can this backup restore into?".

Verify upfront:

- Which server versions does the backup tool support for restore?
- Can a backup from the new version be restored to the old version?
- Did metadata or index definitions change post-upgrade?
- Must the entire cluster be restored rather than a single database?
- Must dependent downstream systems restore to the same timestamp?
- How are replication and change stream resume tokens handled post-restore?
- If the new app wrote data in a new schema, can the old app read it?
- If new server features were used, can the old binary parse the data/config?

Downgrade paths are supported only under **specific upgrade paths, FCV states, and conditions**; they are not equivalent to restoring from a proven pre-upgrade backup.

### 8.1. Snapshot Before Every Irreversible Milestone

A multi-stage upgrade may pass these milestones:

```text
Baseline backup / restore verified
          │
          ▼
Upgrade binaries
          │
          ▼
Verify mixed-version behavior
          │
          ▼
Set target FCV
          │
          ▼
Enable new-only features
```

Before any milestone that makes **downgrade difficult or unsupported**, capture an appropriate backup/recovery point and secure explicit sign-off.

### 8.2. Post-Upgrade Backups Matter Too

After confirming stability, verify that backups and PITR continue running successfully on the upgraded deployment. Never treat pre-upgrade backups as sufficient for ongoing operations afterward.

## 9. Compatibility Matrix: Beyond Server and Driver

A **compatibility matrix** documents every component, its current version, target version, support evidence, and owner.

Template:

| Component | Current | Target | Checks Needed | Status |
|---|---|---|---|---|
| MongoDB Server | A | B | Supported upgrade path, release notes | PENDING |
| FCV | A | B | Preconditions and `setFCV` order | PENDING |
| Java Driver | X | Y / keep X | Server compatibility, TLS, API changes | PENDING |
| Spring Data / ODM | X | Y | Driver range, codecs, transactions | PENDING |
| OS / container | X | Y | Supported platform, CPU, libraries | PENDING |
| Atlas tier / region | Current | Target | Version availability, maintenance policy | PENDING |
| MongoDB Tools | X | Y | Backup/restore feature compatibility | PENDING |
| Search / Vector Search | X | Y | Index/feature support, `mongot` | PENDING |
| Authentication | Current | Target | SCRAM, X.509, OIDC, LDAP/Kerberos as used | PENDING |
| Encryption / KMS | Current | Target | Queryable Encryption, keys, TLS | PENDING |
| CDC / BI connectors | X | Y | Change streams, resume tokens, FCV | PENDING |
| Monitoring / backup agent | X | Y | Server API / support matrix | PENDING |

`A, B, X, Y` are placeholders for your actual **inventory**. Never treat this template as a claim that any given driver supports every future server release.

### 9.1. Three Levels of Compatibility

Distinguish:

1. **Connectable:** the driver completes handshake and `ping`.
2. **Vendor-supported:** the combination sits inside the official support matrix.
3. **Workload-verified:** data, queries, codecs, concurrency, and security all behave properly.

A combination can pass `ping` yet sit outside the support matrix or fail on less common code paths.

### 9.2. Include Sources and Verification Dates

Record:

```text
Component:
Current version:
Target version:
Compatibility documentation:
Release note / advisory:
Checked on:
Verified by:
Evidence link:
Result: PASS / FAIL / UNKNOWN
```

If a source or exact version is missing, mark it `UNKNOWN`; never mark `PASS` from memory or major version assumptions.

## 10. MongoDB Server Upgrade Paths and Intermediate Hops

MongoDB defines **officially supported major-version upgrade paths**, and does not always allow jumping straight from an arbitrary old release to the latest release.

A plan may require stepping through intermediate major versions:

```text
Source version
    │
    ▼
Supported intermediate release
    │
    ▼
Next supported release
    │
    ▼
Target version
```

For each hop, consult the exact **Upgrade a Replica Set** or **Upgrade a Sharded Cluster** guide for the target release.

### 10.1. Why Can't You Just "Copy the Latest Binary"?

Changes across releases can involve:

- WiredTiger/storage metadata;
- Feature Compatibility Version;
- Replication protocol and behavior;
- Index/catalog metadata;
- Query planner and aggregation semantics;
- Deprecated options;
- Driver wire protocol compatibility;
- Sharding metadata;
- Authentication defaults;
- Version-specific feature behaviors.

**Skipping multiple versions at once destroys the ability to validate and recover cleanly across supported boundaries.**

### 10.2. Example Scenario

A team runs MongoDB release line A and wants to reach line C. Proper workflow:

1. Check whether direct A→C upgrade is officially supported.
2. If not, plan A→B and B→C per documentation.
3. Check FCV preconditions at each hop.
4. Test each hop in staging.
5. Verify backups/restores before critical milestones.
6. Record timing and Go/No-Go criteria for every hop.

Never invent an unsupported jump just because a package manager lets you install the newest package.

## 11. Feature Compatibility Version: Why a Separate Step Matters

**FCV** lets MongoDB gate features and data/metadata format behaviors during a major upgrade.

General flow:

```text
All nodes on old binary + old FCV
                  │
                  ▼
Rolling upgrade binaries to new version
                  │
                  ▼
All nodes on new binary + old FCV
                  │
        Validation / hold window
                  ▼
Set FCV to target version
                  │
                  ▼
Validation after FCV
```

This is a **conceptual diagram**. Exact requirements, command flags, and wait windows depend on the release. Some releases impose extra steps; never apply one static diagram mechanically to every upgrade.

### 11.1. Check FCV Before Upgrading

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Requires proper connectivity and privileges. Archive output securely as evidence.

### 11.2. Do Not Raise FCV Immediately After Upgrading Binaries

Once binaries reach the target version, complete required validation first, especially:

- Cluster stability;
- No remaining nodes on old binaries;
- Healthy replication;
- Critical queries passing;
- Driver compatibility;
- Backup paths working;
- Rollback decision sign-off.

**Raising FCV can enable on-disk states/features that restrict downgrade options.** Never treat it as harmless housekeeping.

### 11.3. `setFeatureCompatibilityVersion` Is a State-Changing Operation

Historical syntax looks like:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "<target-version>",
  confirm: true
});
```

`confirm` and exact requirements vary across MongoDB versions. **This is an illustrative example, not a copy-paste command**: always use the exact command, options, and official procedure for your specific release. This command can affect data compatibility across the entire deployment.

### 11.4. Downgrading FCV Does Not Guarantee Binary Downgrade Is Supported

An operator might lower FCV successfully while binary downgrade still remains bound by the release support matrix, persisted data state, and feature usage. **Never treat an FCV downgrade test alone as proof of full rollback capability.**

## 12. MongoDB Drivers and Applications: A Critical Compatibility Layer

Applications may use the Java Sync Driver, Reactive Streams, Spring Data, Node.js Driver, PyMongo, or other connectors.

### 12.1. What to Verify

- Does the driver version support the target server release?
- Are authentication mechanisms and TLS/ciphers still compatible?
- Can the driver connect to the upgraded topology?
- Do read/write concerns or retry behaviors differ?
- Is Stable API / Server API version configured?
- Do BSON codecs/serializers decode existing data identically?
- Have transaction/session behaviors changed?
- Do change streams and resume token handling work?
- Are pool settings, server selection, timeouts, and monitoring events healthy?
- Does an ORM/ODM framework pin an older driver version?

### 12.2. How Does MongoDB Stable API Help?

MongoDB provides the **Stable API** to maintain consistent behavior for covered commands under a declared API version. Selecting Server API V1 can reduce upgrade risk.

However, Stable API **does not guarantee**:

- Identical query plans;
- Unchanged performance metrics;
- Coverage for features outside the Stable API;
- Indefinite support for every server/driver pairing;
- Elimination of integration tests;
- Immunity from data, cache, or replication changes.

Treat Stable API as a **risk-reduction mechanism**, not an exemption from regression testing.

### 12.3. Java Example Configuring Stable API

Reference structure with a supporting MongoDB Java Sync Driver version:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

String uri = System.getenv("MONGODB_URI");

if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("MONGODB_URI is required");
}

ServerApi serverApi = ServerApi.builder()
    .version(ServerApiVersion.V1)
    .build();

MongoClientSettings settings = MongoClientSettings.builder()
    .applyConnectionString(new ConnectionString(uri))
    .serverApi(serverApi)
    .build();

try (MongoClient client = MongoClients.create(settings)) {
    var db = client.getDatabase("app");
    var result = db.runCommand(
        new org.bson.Document("ping", 1)
    );
    System.out.println(result.get("ok"));
}
```

This example uses `ping` solely to test connectivity. It does not replace business integration tests.

### 12.4. Strict and Deprecation Options

Server API offers strictness and deprecation-error flags in supporting drivers. In staging, these help catch calls outside the API contract or relying on deprecated features—provided you test real workloads.

Do not enable strict checks that break legacy APIs in production without a migration plan.

## 13. Frameworks, ODMs, and BSON Compatibility

A Java application using Spring Data MongoDB adds extra layers:

```text
Application repository / templates
           │
       Spring Data
           │
   MongoDB Java Driver
           │
      MongoDB Server
```

When changing server or driver versions:

- Check the Spring Data compatibility matrix;
- Verify serialization of `LocalDateTime`, `Instant`, `BigDecimal`, and UUIDs;
- Verify `@Id`, enum, and polymorphic mappings;
- Verify `Decimal128` and custom codecs;
- Check for deprecated BSON types;
- Verify null vs. missing field semantics;
- Inspect query pipelines generated by the framework;
- Verify optimistic locking / `@Version` fields;
- Check exception mapping and retries.

Integration tests must **read and write real documents** across critical field types—not merely call `ping`.

### 13.1. BSON Round-Trip Test Example

```java
Document sample = new Document("_id", "UPGRADE-TEST-001")
    .append("tenantId", "T-01")
    .append("amount", new org.bson.types.Decimal128(
        new java.math.BigDecimal("12345.67")
    ))
    .append("createdAt", new java.util.Date())
    .append("active", true);
```

In staging, write this document to a dedicated test collection, read it back, and compare serialized types and values. Never run write tests in production outside an approved change window with controlled test data.

### 13.2. Avoid Changing Serializers Simultaneously with Server Upgrades Unless Required

Upgrading MongoDB major versions while simultaneously changing UUID representation, timezone handling, and schema migrations makes isolating faults very difficult. Separate independent changes or ensure dedicated test coverage per layer.

## 14. OS, CPU, Package, and Runtime Compatibility

Self-managed deployments must check **supported platforms** for the target MongoDB Server release.

Key dimensions:

- Linux distribution/version;
- CPU architecture and instruction set;
- Kernel and shared library requirements;
- OpenSSL/TLS libraries;
- Filesystem/storage support;
- Container base image;
- Kubernetes/Operator version;
- Disk format/mount options;
- System limits (`ulimit`, file descriptors);
- Clock synchronization;
- Monitoring and backup tooling.

Never assume a newer MongoDB binary supports every Linux distribution the previous version ran on.

### 14.1. Package Manager Warning

Package managers can automatically pull newer MongoDB versions when repositories update. Before upgrading:

- Pin exact packages and repositories;
- Confirm the target build;
- Check dependencies;
- Keep supported rollback package artifacts ready;
- Know service unit and config paths;
- Never run uncontrolled blanket upgrades.

### 14.2. Client Runtime

Java runtimes, TLS truststores, DNS resolvers, connection pools, and native libraries also impact connectivity. Upgrading the server while clients run outdated JREs or drivers can trigger TLS handshake or authentication failures.

## 15. MongoDB Atlas: Specific Preparation Considerations

In **MongoDB Atlas**, binary provisioning and rolling restarts are managed by the service, yet your organization remains responsible for **compatibility, testing, release windows, and data**.

### 15.1. What to Check in Atlas

1. Does your Atlas tier and region support the target MongoDB version?
2. Is the cluster eligible for upgrade?
3. What maintenance window and auto-upgrade policies apply?
4. Are backups, snapshots, and PITR enabled with adequate retention?
5. Can you choose the upgrade timing, or does the tier restrict scheduling?
6. Will regional or network settings affect client connectivity?
7. Do Search Nodes or Vector Search impose feature restrictions?
8. Are Global Clusters, multi-cloud, sharding, or private endpoints involved?
9. Are KMS / customer-managed encryption keys properly configured?
10. Are alerts and on-call engineers assigned during the upgrade window?

Auto-upgrade behavior, version availability, and backup retention depend on tier, region, and current Atlas policy. Never apply self-managed `apt upgrade` instructions to Atlas workflows.

### 15.2. Cluster Tier Affects Rehearsal Fidelity

A Free or Flex development cluster does not accurately model:

- Replica set capacity;
- Dedicated Search Nodes;
- IOPS, CPU, and memory;
- HA/failover behavior;
- Atlas monitoring/profiler detail;
- Backup/PITR features;
- Production network topology.

To predict production behavior, staging should approximate real **topology, tier, and data scale**—or explicitly document rehearsal limitations.

### 15.3. Do Not Guess Atlas Rollback Behavior from the UI

Version rollback or restore options depend on cluster tier and upgrade state. When planning, verify **what Atlas actually supports** and the impact of a restore on URIs, data loss windows, Search indexes, users/roles, and linked services.

## 16. Self-Managed Replica Set: Sequential Upgrade Flow

A typical replica set:

```text
         Application
              │
              ▼
      MongoDB Replica Set
        ├── Primary P
        ├── Secondary S1
        └── Secondary S2
```

A MongoDB-supported **rolling upgrade** generally follows this logic:

1. Verify backups, FCV, and preconditions.
2. Upgrade secondaries in the procedure's specified order.
3. Wait for each member to recover and sync before advancing.
4. Upgrade the primary once quorum/secondaries are ready, typically via controlled stepdown per runbook.
5. Confirm all members run the target binary.
6. Verify clients, replication, latency, and error rates.
7. Raise FCV only after meeting all release conditions.

### 16.1. Never Restart All Members Simultaneously

If a three-voter cluster restarts every node at once, it loses majority and becomes unavailable. Rolling upgrades preserve availability within supported limits, though brief failover blips still occur.

### 16.2. Upgrading a Member Is Not Enough

After upgrading a secondary, confirm:

- Process runs the exact target binary;
- Member state is `SECONDARY`;
- Replication lag is acceptable;
- No authentication/TLS errors;
- No disk or resource exhaustion;
- No index or query failures;
- Monitoring and backup connections remain healthy.

Do not advance to the next node merely because `systemctl` reports the service started.

### 16.3. Primary Stepdown Can Cause Transient Errors

Some operations may be interrupted, retried, or hit server selection delays. Test client/driver settings beforehand:

- Retryable writes;
- Retryable reads for supported commands;
- Transactions;
- Timeouts;
- Connection pool behavior;
- Read/write concerns;
- Business idempotency.

Never promise **absolute zero downtime** for a rolling upgrade. It minimizes impact and preserves availability when preconditions hold, yet primary transitions and transient errors can still occur.

## 17. Self-Managed Sharded Cluster: Multi-Tier Dependencies

A sharded deployment:

```text
Client
   │
 mongos
   │
   ├── Config Server Replica Set
   ├── Shard A Replica Set
   ├── Shard B Replica Set
   └── Shard C Replica Set
```

Sharded cluster major upgrades enforce a strict release-specific sequence. Typical official workflows coordinate **balancer/chunk migrations, config servers, each shard replica set, `mongos` routers, and FCV**, though you **must verify the exact sequence and details for your target version**.

### 17.1. Why Does Ordering Matter?

Components coordinate across metadata/config, chunk routing, and wire protocols. Mixed-version states are supported **only during the rolling upgrade window**, never as a long-term steady state.

### 17.2. Sharding-Specific Tests

- Targeted queries using the shard key;
- Scatter-gather queries;
- Cross-shard aggregations;
- Cross-shard transactions;
- Balancer and chunk migrations;
- Change streams;
- Shard key and unique index constraints;
- Queries routed across multiple `mongos` instances;
- Replication lag per shard;
- Metadata/config server health.

### 17.3. Never Toggle the Balancer Casually During Peak Hours

Stopping/starting the balancer or altering chunk migrations has operational impact. Never experiment casually; follow an owner-approved runbook and version-specific guide.

### 17.4. Verify Every Router

If multiple `mongos` routers sit behind a load balancer, inspect all of them. Leaving one router on an old version creates an unsupported mixed state even if most traffic succeeds.

## 18. Compatibility with Replication, Oplog, and Change Streams

Downstream services may depend on the oplog and change streams:

```text
MongoDB → Change Stream Consumer → Queue → Data Warehouse
```

During upgrades, verify:

- Resume token persistence;
- Consumer reconnect/resume across elections;
- Maintenance duration vs. oplog window;
- Pre- and post-images if used;
- Transaction events and ordering;
- Connector/SDK versions;
- Idempotency and duplicate delivery handling;
- Error/retry policies;
- CDC lag.

### 18.1. The Oplog Window Is a Hard Boundary

If a consumer stays paused too long during maintenance and its resume token falls out of the oplog window, it cannot resume automatically.

Before upgrading, verify oplog **retention/window**, consumer lag, and resnapshot/reconciliation procedures.

### 18.2. Do Not Treat Change Stream Events as Exactly-Once End-to-End

A consumer can receive duplicate events upon reconnect/retry. Downstream writes should be idempotent or deduplicated. Upgrade testing must cover restarts and resumption.

## 19. Compatibility with Transactions

If applications use multi-document transactions:

- Verify driver sessions continue working;
- Verify retry labels and retry policies;
- Verify commit/abort semantics remain intact;
- Verify write concern / read concern support;
- Test failover mid-transaction;
- Check transaction timeout/lifetime settings;
- Check version/topology constraints for sharded transactions;
- Avoid long-running open transactions during the upgrade window.

### 19.1. Example Transaction Test Scenario

In staging:

```text
1. Create an order.
2. Decrement inventory inside the same transaction.
3. Commit successfully.
4. Confirm both changes persist together.
5. Inject an intentional failure and verify rollback.
6. Run an authorized primary stepdown test.
7. Verify the app retries cleanly without creating duplicate orders.
```

Never inject intentional failovers in production just to test transaction retries without an approved change window.

## 20. Index and Query Plan Compatibility

A server upgrade can alter the query optimizer, index selection, or execution engine even when APIs and data stay unchanged.

### 20.1. Inventory Index Definitions

```javascript
db.getSiblingDB("app")
  .orders.getIndexes();
```

Document:

- Single and compound indexes;
- Unique, partial, and sparse indexes;
- TTL indexes;
- Multikey indexes;
- Collations;
- Hidden indexes;
- Text, geospatial, hashed, and wildcard indexes;
- Shard-key-related requirements.

If an index needs rebuilding or changes behavior across versions, add it to the compatibility matrix.

### 20.2. Select Representative Query Shapes

A test suite should include:

- Hot point lookups by `_id`;
- Compound filter/sort/limit queries;
- Range queries;
- Aggregations and `$lookup`;
- Multikey `$elemMatch`;
- Collation-sensitive searches;
- Partial index predicates;
- Pagination (`skip` and keyset);
- Transactional reads/writes;
- Reporting queries;
- Geospatial/text/Search/Vector Search queries if used.

### 20.3. Use `explain` Properly

Read-only example:

```javascript
db.getSiblingDB("app").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Inspect:

```text
winningPlan
nReturned
totalKeysExamined
totalDocsExamined
executionTimeMillis
SORT / FETCH / IXSCAN / COLLSCAN per plan format
```

Stage names can differ between classic, SBE, and server versions; avoid brittle tests that assert raw stage string names while ignoring execution semantics.

### 20.4. A Changed Query Plan Is Not Automatically Bad

If the new version picks a different plan with better latency and lower resource cost, that is an improvement. Conversely, a plan still using `IXSCAN` while `keysExamined` skyrockets still warrants investigation.

Rely on **measurements** under realistic workloads rather than demanding identical plan shapes.

## 21. Data Model, Validation, and BSON Compatibility

A version upgrade can affect:

- Schema validation behavior;
- BSON type handling;
- Driver date/timezone conversions;
- `Decimal128`;
- UUID encoding;
- `ObjectId`;
- Null vs. missing fields;
- Collation;
- Query expressions;
- Data migrations;
- Unique constraint enforcement.

### 21.1. Test Diverse Data Fixtures

Do not test only "clean" documents. Include fixtures like:

```javascript
{
  _id: "MIGRATION-FIXTURE-1",
  tenantId: "T-01",
  amount: NumberDecimal("12345.67"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  tags: ["priority", "fragile"],
  attrs: { color: null },
  archived: false
}
```

Verify:

- Read/write round trips;
- Decimal precision;
- Dates and timezones;
- Nested objects and arrays;
- Optional and missing fields;
- Validation rejection paths;
- Unique constraints;
- BSON codec compatibility.

### 21.2. Decouple Schema Migrations from Server Upgrades

If schema migrations occur within the same project, apply an **expand-and-contract** pattern where suitable:

```text
Old app compatible with old schema
         │
Add new optional schema fields
         │
Deploy dual-compatible app
         │
Backfill source data
         │
Upgrade server
         │
Validate both paths
         │
Remove obsolete fields after rollback window
```

Exact steps depend on data and application design; the goal is **not breaking the old app's ability to read data before you know the server upgrade is stable**.

## 22. Search and Vector Search Capabilities

MongoDB Search / Atlas Search and Vector Search rely on Search indexes with lifecycles independent of database B-tree indexes.

During an upgrade, check:

- MongoDB Server version support for `$search`, `$searchMeta`, and `$vectorSearch`;
- Atlas tier/region/feature restrictions;
- `mongot` compatibility if self-managed;
- Search index definitions;
- Search Node sizing/topology;
- Lucene indexing lag;
- Search index rebuild/readiness;
- Embedding models/vector dimensions if applicable;
- Data access/ACL filters;
- Search relevance and latency.

### 22.1. Search Indexes Can Lag After Restore or Topology Changes

After a change, source documents may be queryable via `find()`, while the Search index is still running initial sync or rebuilding.

Verify all of:

```text
Source data available
Search index queryable
Search index caught up
Search result correctness
Search API latency
Authorization behavior
```

### 22.2. Listing Search Indexes

Where supported by your deployment/version:

```javascript
db.getSiblingDB("app").articles.aggregate([
  {
    $listSearchIndexes: {}
  }
]);
```

This checks status and index definitions, without replacing end-to-end Search query and indexing-lag verification.

### 22.3. Never Use Search Indexes as the Source of Truth for Permissions

A permission recently revoked on the source collection might not yet reflect in a lagging Search index. Regardless of server version, applications must enforce **current authorization** before returning sensitive content. Upgrade tests should cover permission revocation under Search lag.

## 23. Matrix of Deprecated or Changed Features

A major upgrade can:

- Remove legacy commands or options;
- Change default behaviors;
- Alter the query execution engine;
- Restrict specific collection or index options;
- Change driver retryable operation handling;
- Deprecate or alter authentication mechanisms;
- Change Search/Vector support tiers;
- Require configuration or monitoring exporter updates.

### 23.1. Do Not Skip Release Notes

For every intermediate and target release, maintain a table:

| Release Change | Used by App? | Impact | Test |
|---|---|---|---|
| Deprecated command | Unknown | Could fail | Static search + integration |
| FCV requirement | Yes | Upgrade workflow | FCV preflight |
| Query behavior | Yes | Results/performance | Regression dataset |
| Index changes | Yes | Query plans, disk | Explain + benchmark |
| Auth/TLS updates | Yes | Connectivity | Driver/CA tests |
| Backup tooling | Yes | Recovery | Restore drill |
| Search version | Yes | Index readiness | Search smoke/lag |
| Connector change | Yes | CDC continuity | Resume/restart test |

Any row marked `Unknown` is an **investigation action item**, never an assumption of zero impact.

### 23.2. Audit Application Code for Deprecations

Use:

- Static code searches for command names;
- Driver warnings and deprecation logs;
- Automated test suites;
- Query logs/profiler per policy;
- Framework compatibility notes;
- API strict/deprecation flags in staging where suitable.

Rarely invoked legacy commands in code may never appear in daily production metrics—be sure to test infrequent paths too.

## 24. Designing Production-Like Staging

**Staging** is where you validate the upgrade procedure before touching production data.

### 24.1. What Should Match Production

- MongoDB source version and FCV;
- Target version;
- Topology (replica set vs. sharded);
- Driver and ODM versions;
- Authentication, TLS, and KMS;
- Query indexes;
- Realistic data size and distribution;
- Application version;
- Background jobs;
- Read/write traffic ratio;
- Shard key distribution;
- Search / Vector Search;
- Monitoring and backup agents.

If staging is a tiny standalone instance while production is a multi-tenant sharded cluster, **it cannot test sharding or failover risks**.

### 24.2. Real Data vs. Synthetic Data

Use representative data while protecting privacy:

- De-identified/masked datasets where policy permits;
- Synthetic data reproducing cardinality and skew;
- Edge cases captured from past incidents;
- Sufficient volume for performance testing;
- Never place secrets or PII into lower-security environments.

Masking must preserve field correlations needed to test query behavior. Wiping diversity or collapsing all tenants into one value skews benchmarks.

### 24.3. Do Not Extrapolate Production Latency from Mismatched Tiers

An undersized staging cluster can be far slower than production, while a tiny staging dataset can make every query look artificially fast. Document limitations and run proper **load and capacity tests**.

## 25. Functional Testing: From Smoke to Regression

Organize testing in layers.

### 25.1. Smoke Test

Minimum questions:

- Can the app connect?
- Do authentication and TLS succeed?
- Do `ping` and health checks pass?
- Can documents be read by `_id`?
- Do test writes succeed in a staging collection?
- Do critical indexed queries succeed?
- Does a sample transaction work?
- Do change stream consumers resume?
- Do backup and monitoring agents work?

Smoke tests verify basic readiness; they **do not prove the application is free of regressions**.

### 25.2. Functional Regression Tests

Include:

- CRUD;
- Bulk writes;
- Aggregations;
- Pagination and sorting;
- Unique constraints;
- TTL-dependent behavior;
- Transactions;
- Change streams;
- Search/Vector queries;
- Multi-tenant ACLs;
- Error handling paths;
- Driver retry behavior;
- Background batch jobs.

### 25.3. Business Regression Tests

For an e-commerce platform:

```text
Create order
→ Reserve inventory
→ Confirm payment
→ Update order status
→ Query customer history
→ Generate invoice
→ Fulfill or refund
```

Validate complete end-to-end workflows, not merely isolated MongoDB calls.

### 25.4. Verify Data Completeness and Invariants

Beyond document counts, check:

- Referential/business relationships;
- Uniqueness;
- Monetary totals;
- Status transition rules;
- Numeric/`Decimal128` precision;
- Date/timezone rules;
- Tenant isolation;
- Idempotency;
- Soft deletes and retention.

Matching counts alone do not prove data correctness.

## 26. Performance Testing: Apples-to-Apples Comparisons

A clean benchmark design:

```text
Baseline: current server + current app
Candidate: target server + same app/config
Optional: target server + new driver (separate comparison)
```

The goal is **isolating variables**.

### 26.1. Metrics to Measure

| Metric | Why It Matters |
|---|---|
| Read p50/p95/p99 | Query user experience |
| Write p50/p95/p99 | Write overhead |
| Throughput | Processing capacity |
| HTTP/business errors | User impact |
| Driver command failures/retries | Compatibility and topology behavior |
| Connection pool wait | Client-side bottlenecks |
| CPU, disk latency, WiredTiger cache | Resource pressure |
| Replication lag | Secondary catch-up capacity |
| Query targeting | Index and query plan efficiency |
| Index sizes | Storage footprint |
| Search QPS/lag | Derived search readiness |
| Backup/restore duration | Recovery budget |

### 26.2. Do Not Measure Average Latency Alone

An upgrade might hold average read latency at 20 ms while p99 climbs from 200 ms to 2 seconds. Under high traffic, tail latency can break SLAs.

### 26.3. Test Warm Cache and Cold Cache

- **Cold cache:** simulates post-restart or disk-bound reads.
- **Warm cache:** steady-state workload.
- **Mixed load:** realistic concurrent reads, writes, and aggregations.
- **Peak load:** business traffic spikes.
- **Background jobs:** backups, index builds, CDC, and reports.

Never certify performance based on the single fastest run.

### 26.4. Inspect Query Plans

Example:

```javascript
db.getSiblingDB("app").orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Compare `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and latency. When a plan changes, evaluate whether it is an improvement or a regression against real targets.

## 27. Testing Failover and High Availability

Major upgrade validation is incomplete if tested only when all nodes are healthy with zero elections.

### 27.1. Staging Scenarios

- Restarting a secondary;
- Controlled primary stepdown per runbook;
- Driver reconnection;
- In-flight transactions during election;
- Retryable writes;
- Change stream reconnect/resume;
- Read preferences when a secondary is down;
- Network interruptions;
- Temporary loss of one shard;
- Search index rebuilding;
- Backup/monitoring agent restarts.

**Run disruptive tests only in staging or approved environments.** Never run `rs.stepDown()` in production just to experiment without an approved change window.

### 27.2. Verify All Timeout Layers

Timeouts span multiple layers:

- Server selection timeout;
- Connection pool checkout timeout;
- Connect/socket timeouts;
- MongoDB operation `maxTimeMS`;
- HTTP/API timeouts;
- Transaction lifetime;
- CDC resume/retry policies.

Do not inflate every timeout arbitrarily just to "eliminate errors". Excessive timeouts mask incidents and hold requests open too long.

### 27.3. Verify Idempotency

During failover and retries, applications must avoid creating duplicate orders or double charges. A retryable error does not guarantee the operation failed on the server. Test business idempotency keys and reconciliation.

## 28. Security Testing During Upgrades

An upgrade can change:

- TLS libraries and cipher suites;
- Certificate validation;
- Supported authentication mechanisms;
- Driver auth defaults;
- User/role behavior;
- OIDC/LDAP/Kerberos integrations;
- KMS / Queryable Encryption compatibility;
- Audit log formats;
- Network / private endpoint connectivity.

### 28.1. Mandatory Questions

1. Do TLS certificates remain valid with hostname verification enforced?
2. Do both service accounts and admin accounts work properly?
3. Can any account escalate privileges?
4. Do role scopes remain intact?
5. Do tenant isolation tests pass?
6. Are secrets absent from logs?
7. Are KMS keys accessible when reading encrypted data?
8. Are required audit events still recorded?
9. Is backup encryption unaffected?
10. Do all connectors enforce TLS and least privilege?

### 28.2. Never "Fix" Connection Errors by Disabling TLS Checks

Options such as:

```text
tlsAllowInvalidCertificates=true
tlsAllowInvalidHostnames=true
tlsInsecure=true
```

are never acceptable for passing a production upgrade gate. Fix the CA, SANs, truststore, DNS, and certificates properly.

## 29. Post-Upgrade Backup and Restore Testing

A commonly missed failure is **succeeding on the database upgrade while the backup agent becomes incompatible**.

After upgrading staging, test:

1. Creating a backup with the official tool.
2. Restoring to an isolated target.
3. Verifying data integrity.
4. Verifying collections and indexes.
5. Verifying Search/Vector Search if used.
6. Measuring RTO and recovery point.
7. Verifying keys, permissions, and application smoke tests.
8. Archiving evidence.

If backup tooling does not yet support the target version, that is a **BLOCKER** for any system requiring backups.

## 30. Load Testing: Catching Regressions at Scale

A load test plan should specify:

```text
Dataset size and distribution:
Index definitions:
Traffic mix:
Read/write concurrency:
Duration:
Warm-up:
Ramp-up:
Peak:
Success/error definitions:
p95/p99 thresholds:
Cluster tier:
CPU/disk/network capacity:
```

### 30.1. Example Read/Write Mix

Suppose production runs:

```text
Read operations: 70%
Write operations: 25%
Other/aggregation: 5%
```

A 100% read load test cannot verify write latency or replication lag under real workload pressure.

### 30.2. Data Skew Changes Behavior

One tenant holding 80% of records can trigger hotspots or different query plans. Uniformly distributed synthetic data misses this issue.

Include:

- Large and small tenants;
- Hot partitions;
- Missing and null fields;
- Arrays;
- Rare statuses;
- Old and recent timestamps;
- Long and short strings;
- Mixed BSON types.

### 30.3. Define Acceptance Thresholds Before Running

Deciding after the test that "a 1.5-second p99 seems fine" removes objectivity. Lock down guardrails and owners beforehand.

## 31. Canary Rollout: Limiting Blast Radius

Where infrastructure and apps permit, upgrade a lower-risk environment/cluster first or run a planned application canary.

However, **not every MongoDB major upgrade permits arbitrary per-node or per-tenant canaries**. Mixed-version topologies are supported only within rolling upgrade rules—never run them as long-term A/B server tests unless officially supported.

### 31.1. Forms of Canary Testing

- Production-like staging;
- Internal or test-tenant traffic;
- A lower-criticality replica set;
- A secondary cluster in a multi-cluster architecture;
- Application canary following a server upgrade;
- Read-only shadow traffic with protected data.

### 31.2. Shadow Queries and Sensitive Data

Never replay queries containing PII to staging or a lower-security test cluster. If replaying production traffic, enforce data masking and strict access controls.

### 31.3. Gating Before Expansion

```text
Canary pass
     │
     ├── Errors within SLO
     ├── Latency within guardrail
     ├── No data integrity failure
     ├── No tenant/ACL regression
     ├── Replication stable
     ├── Backup working
     └── No serious new warnings
           │
           ▼
       Wider rollout
```

Never ramp traffic merely because nobody complained yet; wait for metrics and an adequate observation window.

## 32. Rollback Planning: Three Distinct Concepts

Beginners often say "if it fails, roll back". Rollback can mean three very different actions:

1. **Application rollback:** redeploying the previous app version.
2. **MongoDB binary/FCV downgrade:** returning to the prior server version via a supported procedure.
3. **Data restore:** restoring the deployment from a backup/recovery point.

These three are **not equivalent**.

### 32.1. Application Rollback

Often faster if schemas and drivers remain backward-compatible. However, if the new app wrote data in a schema the old app cannot parse, rolling back the app can fail.

### 32.2. MongoDB Downgrade

Not always supported, especially when:

- FCV has already been raised;
- New features have been enabled or used;
- Internal metadata or storage formats changed;
- The release requires intermediate steps;
- Drivers/tooling are incompatible;
- Post-upgrade data cannot be read by the older binary.

Check the exact **downgrade procedure** for your source/target versions and never promise binary downgrade capability without verifying it.

### 32.3. Restore from Backup

Restoring recovers a pre-upgrade state, yet can lose writes committed after the recovery point without PITR or reconciliation.

To recover behavior without losing new data, plan carefully:

```text
Post-upgrade writes
        │
        ├── Can they be safely replayed/reconciled?
        ├── Are changes backed up?
        └── Is idempotency guaranteed?
```

Never assume "restoring the pre-upgrade snapshot" is a **zero-data-loss rollback** by default.

### 32.4. Rehearse Rollback Too

In staging, test the chosen recovery path:

- Revert to the old app version;
- Confirm schemas remain readable;
- Verify binary/FCV downgrade only if supported by docs;
- Or restore and replay per RPO;
- Check indexes, permissions, and CDC;
- Time the full execution.

If a rollback plan has never been rehearsed, mark it **unproven**.

## 33. Decision Gates You Must Not Cross Without Approval

An upgrade proceeds through explicit **decision gates**:

```text
GATE 0: Inventory + compatibility known
                 │
GATE 1: Backup and restore proven
                 │
GATE 2: Staging functional/performance/security pass
                 │
GATE 3: Production change window approved
                 │
GATE 4: Binary upgrade validation
                 │
GATE 5: FCV / new feature activation approved
                 │
GATE 6: Post-upgrade stabilization complete
```

GATE 5 is especially critical because raising FCV or enabling new features can restrict downgrade paths. Never let automation auto-enable features before rollback windows and approvals are settled.

## 34. Pre-Upgrade Read-Only Inspection Checklist Commands

`mongosh` examples to collect evidence on authorized deployments:

### 34.1. Server Identity/Version

```javascript
const dbAdmin = db.getSiblingDB("admin");

printjson({
  version: db.version(),
  hello: db.hello()
});
```

### 34.2. FCV

```javascript
printjson(
  db.getSiblingDB("admin").runCommand({
    getParameter: 1,
    featureCompatibilityVersion: 1
  })
);
```

### 34.3. Replica Set

```javascript
rs.status();
```

Run only on appropriate topologies and never publish outputs openly.

### 34.4. Sharding

```javascript
sh.status();
```

Run via `mongos` on sharded clusters.

### 34.5. Collections/Indexes

```javascript
const app = db.getSiblingDB("app");

printjson(app.orders.getIndexes());
printjson(app.orders.stats({ scale: 1024 * 1024 }));
```

### 34.6. Server Status — Minimal Metrics

```javascript
const s = db.serverStatus();

printjson({
  localTime: s.localTime,
  uptime: s.uptime,
  opcounters: s.opcounters,
  connections: s.connections,
  opLatencies: s.opLatencies
});
```

Output varies by version and privileges; some counters are **cumulative since server startup**, not instantaneous QPS or latency percentiles.

### 34.7. Current Authentication Session

```javascript
db.runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

### 34.8. Search Indexes

When Search is enabled and privileges permit:

```javascript
db.getSiblingDB("app").articles.aggregate([
  { $listSearchIndexes: {} }
]);
```

### 34.9. Sensitive Data in Outputs

Inventory outputs can expose hostnames, node addresses, users/roles, collection names, or query metadata. Store them securely and redact sensitive details before sharing reports.

**Never turn a preflight script into an auto-restart, FCV-bump, index-drop, or credential-change tool.** Those require dedicated change workflows.

## 35. Phased Upgrade Plan

A detailed plan can span seven phases.

### Phase A — Request Initiation

- Select target version;
- Document security/support rationale;
- Identify environments;
- Assign owners;
- Propose schedule;
- Lock change scope;
- Define RPO/RTO and SLOs.

### Phase B — Inventory and Compatibility

- List server members, routers, and config servers;
- Record current binary/FCV;
- Verify supported upgrade path;
- Complete driver/ODM/OS/tooling matrix;
- Verify TLS/KMS/auth;
- Cover Search/Vector/CDC;
- Review release notes and deprecations.

### Phase C — Data Protection

- Verify backup policies and retention;
- Establish a valid restore point;
- Complete restore drill;
- Validate data integrity;
- Verify PITR/oplog coverage;
- Confirm key recovery;
- Record achieved RPO/RTO.

### Phase D — Testing

- Run staging upgrade per runbook;
- Run functional tests;
- Run performance/load tests;
- Run failover tests;
- Run security regression tests;
- Test backup/restore post-upgrade;
- Rehearse rollback;
- Obtain sign-off.

### Phase E — Production Change Window

- Freeze unrelated changes;
- Notify stakeholders and on-call;
- Run preflight backup/health checks;
- Execute approved steps sequentially;
- Log timestamps, commands/versions, and outcomes;
- Halt if any gate fails.

### Phase F — Post-Upgrade Validation

- Verify binaries, FCV, and topology;
- Verify replica/shard health;
- Run app smoke and regression checks;
- Verify query latency and error rates;
- Verify CDC, Search, and indexes;
- Verify backups and monitoring;
- Verify security controls.

### Phase G — Stabilization and Closure

- Observe through peak and batch workloads;
- Update inventory and architecture docs;
- Record incident lessons;
- Hand over updated runbooks;
- Enable new features only per separate approval;
- Close the rollback window on an evidence-based decision.

## 36. Production Runbook: What Must Be Documented

A good runbook can be executed cleanly by someone other than its author.

Template:

```text
CHANGE: MongoDB Server Upgrade

Change ID:
Source version/FCV:
Target version/FCV:
Deployment type/topology:
Change window:
Business impact:
RPO/RTO:
Owner:
DBA lead:
Security reviewer:
Application owner:
On-call:
Communication channel:

Preconditions:
  [ ] Approved compatibility matrix
  [ ] Version-specific official upgrade guide attached
  [ ] Backup validated
  [ ] Restore drill passed
  [ ] Staging test evidence approved
  [ ] Capacity headroom available
  [ ] Monitoring/alerts enabled
  [ ] Credentials/permissions verified
  [ ] Rollback decision points documented

Execution:
  Step ID:
  Target node/component:
  Preconditions:
  Command or Atlas action reference:
  Expected state:
  Evidence:
  Timeout:
  Stop condition:
  Rollback action:
  Approver:

Validation:
  [ ] Binary versions correct
  [ ] FCV expected
  [ ] Replica/shard health stable
  [ ] API smoke tests passed
  [ ] Latency/error guardrails met
  [ ] CDC/Search verified
  [ ] Backup/restore path checked

Decision:
  GO / HOLD / ROLLBACK / RECOVER

Closure:
  Owner sign-off:
  Post-upgrade monitoring:
  Incident findings:
```

### 36.1. Never Put Secrets in Runbooks

Runbooks should reference approved secret locations—never raw passwords, TLS private keys, or Atlas API keys.

### 36.2. Every Step Needs a Stop Condition

Example:

```text
If secondary does not return to SECONDARY
or replication lag exceeds approved threshold
within the declared observation window:
  STOP before touching next member.
```

Never write a "upgrade node by node" checklist lacking concrete criteria for whether advancing to the next node is safe.

## 37. Go/No-Go Matrix

| Item | PASS Criteria | NO-GO Criteria |
|---|---|---|
| Upgrade path | Official guide exists for every hop | Supported path unconfirmed |
| FCV | Preconditions and separate gate defined | Current FCV ineligible |
| Compatibility | Drivers/OS/tools supported | Critical component incompatible |
| Backup | Valid restore point, verified integrity | Backup missing or failing |
| Restore | Restore drill met RPO/RTO | Untested or failed |
| Data integrity | Regression and data checks pass | Corrupted or lost data |
| Performance | SLOs/guardrails met | Tail latency or throughput breaches threshold |
| Replica/sharding | Health and failover tests pass | Quorum, lag, or topology errors |
| Security | Auth/TLS/KMS/RBAC working | Broken encryption or wrong permissions |
| CDC/Search | Consumers and indexes healthy | Severe event loss or search outage |
| Rollback | Viable, rehearsed recovery plan | No feasible recovery path |
| Ownership | Approved sign-off and on-call staffed | No accountable owner |

An `UNKNOWN` entry for a critical component must never be marked `PASS` just to fill out green checkboxes.

### 37.1. Controlled Exceptions

Occasionally, a minor risk may be accepted temporarily. An exception requires:

- Clear description;
- Owner;
- Risk assessment;
- Compensating controls;
- Expiration date;
- Authorized approval.

Never use open-ended exceptions to skip backups, recoverability, or severe security fixes.

## 38. Failure Scenarios and Response Plans

### 38.1. A Secondary Fails to Catch Up

Symptoms:

```text
Secondary restarted on target binary
  ↓
Replication lag increases
  ↓
Node remains RECOVERING
```

Actions:

1. Halt before upgrading other nodes.
2. Inspect logs, network, disk, FCV, and compatibility.
3. Confirm remaining quorum is healthy.
4. Consult the official procedure.
5. Resume or recover only after an explicit decision.

### 38.2. Driver Connections Fail After Binary Upgrade

Symptoms:

```text
Server healthy
Application sees server selection timeout / TLS handshake error
```

Check:

- Driver/version compatibility;
- TLS CA and certificate SANs;
- Authentication mechanisms;
- DNS and seed lists;
- Network/firewall rules;
- Topology discovery;
- Connection pool state.

**Never disable TLS verification** to work around connection failures.

### 38.3. Read p99 Rises While Writes Stay Normal

Check:

- Changed query plans;
- Indexes and collations;
- Cold vs. warm cache;
- Disk I/O;
- Aggregation stages;
- Application concurrency;
- Pool wait times;
- Background index builds.

Do not rush to roll back the server if the true cause is connection pool sizing or a concurrently deployed query; gather evidence first.

### 38.4. Write p99 Rises After Raising FCV

Check:

- Replication lag;
- Storage and cache pressure;
- Transactions and workload shifts;
- Index maintenance;
- Write concerns;
- Background operations;
- Release notes / known issues.

If stop thresholds are breached, execute the **supported rollback/recovery path**—never attempt ad-hoc FCV downgrades blindly.

### 38.5. Backup Agent Fails After Upgrade

This can block closing the change. Check backup tool compatibility, credentials, storage/KMS access, APIs, and run another restore drill as needed.

### 38.6. Search Queries Miss Recently Written Data

Search indexes synchronize asynchronously. Check index status, lag, `mongot`/Search Nodes, mappings, and permissions. Never assume source data is lost based solely on empty Search results.

## 39. Dangerous Anti-Patterns

| Anti-pattern | Risk | Right Practice |
|---|---|---|
| Upgrading without backups | No restore path | Backups + restore drill |
| Treating "backup SUCCESS" as sufficient | Artifact might not restore | Measure real RPO/RTO |
| Not knowing current FCV | Invalid preconditions | Inventory FCV |
| Skipping major versions arbitrarily | Unsupported upgrade path | Follow official upgrade path |
| Upgrading all replica members together | Quorum loss | Rolling procedure |
| Upgrading sharded components in random order | Routing/metadata incompatibility | Version-specific order |
| Raising FCV right after startup | Restricts rollback | Validation gate |
| Running an old binary on new data arbitrarily | Corruption / incompatibility | Official downgrade procedure |
| Treating app rollback as DB rollback | Schema/FCV mismatch | Separate rollback plans |
| Skipping change stream tests | Consumers lose events | Resume/retry tests |
| Skipping transaction/failover tests | Duplicate/lost writes | Fault-injection in staging |
| Testing only 1,000 docs | Unrepresentative | Realistic dataset with skew |
| Testing only `ping` | Does not validate workload | Functional/regression/load tests |
| Ignoring p95/p99 | Hides tail regressions | Metrics and tracing |
| Changing schema, driver, and server together | Hard to isolate faults | Phased rollout |
| Disabling TLS validation on errors | MITM exposure | Fix CA/cert/DNS |
| Skipping KMS verification | Restores/encryption may fail | Key recovery drill |
| Ignoring Search/Vector | Search outage / rebuilds | Feature-specific tests |
| No on-call owner | Slow incident response | Runbook + staffing |
| No stop criteria | Continuing through instability | Gates and hold conditions |
| Relying on staging with wrong topology | Misses sharding/failover risks | Production-like staging |
| Benchmarking only warm cache | Masks cold-start regressions | Warm/cold/mixed tests |
| Restoring without checking permissions | Potential data leaks | Auth/RBAC smoke tests |
| Skipping release notes | Misses deprecations | Compatibility matrix |
| Assuming Atlas managed needs no testing | App/data risks remain | Shared-responsibility review |

## 40. Hands-On Exercises

### Exercise 1 — Categorizing Changes

A project plans to do all of the following simultaneously:

- Upgrade MongoDB major version;
- Upgrade the Java Driver;
- Rotate the TLS CA;
- Modify indexes on `orders`;
- Migrate Atlas regions.

Classify the risk of each change and propose a phased ordering, test plan, and rollback checkpoints.

### Exercise 2 — Checking Inventory

Given:

```text
Primary MongoDB: A
Secondary 1: A
Secondary 2: A
FCV: Unknown
Java Driver: X
Backup agent: Y
CDC connector: Z
```

1. Is this information sufficient to upgrade?
2. Which additional components need inventorying?
3. Why cannot FCV remain `Unknown`?
4. What evidence sources are appropriate?
5. Can you decide based solely on `db.version()` on the primary?

### Exercise 3 — Compatibility Matrix

Build a table covering MongoDB Server, FCV, Java Driver, Spring Data, OS, backup tools, TLS/auth, and Search. For each row record current, target, docs source, and PASS/FAIL/UNKNOWN.

Explain why one critical `Unknown` row can trigger a NO-GO.

### Exercise 4 — Backups and RPO

A system has:

```text
RPO = 15 minutes
RTO = 2 hours
Nightly backup
No PITR
```

1. Can the 15-minute RPO be proven?
2. What type of backup/continuous recovery is required?
3. What is the difference between a replica set and a backup?
4. Why is the mere existence of a backup file insufficient?
5. When encryption is used, how critical is key recovery?

### Exercise 5 — Restore Drill

Design a pre-upgrade restore drill:

1. Select backup ID and target;
2. Protect staging data;
3. Restore source;
4. Verify collections and indexes;
5. Run business smoke tests;
6. Measure RPO/RTO;
7. Archive evidence and approval.

### Exercise 6 — FCV and Binaries

Explain:

```text
Binaries upgraded to target version
FCV kept at old value
```

1. Why does this phase exist?
2. When is it safe to raise FCV?
3. Does downgrading FCV guarantee binary downgrade works?
4. Can new features be used before this gate?
5. What evidence is required?

### Exercise 7 — Rolling Replica Set

A replica set has P, S1, and S2.

1. Propose the high-level upgrade order per official guidance.
2. What must be verified after upgrading S1?
3. What happens if P, S1, and S2 restart together?
4. How does the driver handle the election?
5. Write stop criteria for high replication lag.

### Exercise 8 — Sharded Cluster

A cluster has 3 `mongos`, a config server replica set, and 4 shard replica sets.

1. Why cannot a single replica set sequence be applied across the whole cluster?
2. Which components need inventorying?
3. What balancer/chunk migration details matter?
4. How do you test query targeting and cross-shard transactions?
5. Must all three `mongos` routers be checked?

### Exercise 9 — Driver Test

A Java app connects to the target MongoDB and `ping` returns OK.

1. Is this enough to declare compatibility?
2. Which BSON types should be tested?
3. How should transactions, change streams, and retries be tested?
4. What does Stable API solve?
5. What role do frameworks/ODMs play?

### Exercise 10 — Query Plan Regression

Before upgrade:

```text
Read p95 = 40 ms
Docs examined = 25
```

After upgrade:

```text
Read p95 = 350 ms
Docs examined = 150000
```

1. What do you suspect?
2. How do you inspect indexes, collations, and query shapes?
3. How do you compare `explain` outputs?
4. Should you immediately force `hint` in production?
5. When do you HOLD or roll back?

### Exercise 11 — TLS Security

After an upgrade, a Java service connects only when setting:

```text
tlsAllowInvalidHostnames=true
```

1. Why is this a blocker?
2. What CA/SAN/DNS settings must be checked?
3. Could upgrading the driver or truststore resolve it?
4. Why must insecure flags never ship to production?
5. How do you test certificate rotation beforehand?

### Exercise 12 — CDC Resume

A change stream consumer was stopped for 3 hours while the oplog window is 2 hours.

1. Can it resume automatically using its token?
2. What resnapshot/reconciliation plan is needed?
3. How do you prevent duplicate processing?
4. Which metrics should be monitored?
5. Why must consumers be tested alongside main APIs?

### Exercise 13 — Search/Vector Readiness

MongoDB `find()` works after an upgrade, yet `$vectorSearch` reports the index is unavailable.

1. Is source data necessarily lost?
2. Which Search index statuses must be checked?
3. Must model dimensions and mappings be checked?
4. How should the API fall back?
5. Why must indexing lag be measured?

### Exercise 14 — Performance Plan

Design a benchmark with:

```text
Dataset: 10 million documents
Traffic: 70% read, 25% write, 5% aggregation
Peak: 1500 operations/s
Target: p95 read < 100 ms, p95 write < 120 ms
```

Specify warm-up, peak duration, data skew, metrics, and stop criteria.

### Exercise 15 — Rollback Plan

Suppose both the new app and new MongoDB were deployed to production, and a schema change was written that only the new app understands.

1. Can you simply redeploy the old app?
2. Is server downgrade guaranteed?
3. Which writes could be lost if restoring the pre-upgrade snapshot?
4. What data replay/reconciliation is required?
5. When should expand-and-contract be used?

### Exercise 16 — Go/No-Go

Checklist:

```text
Compatibility matrix: PASS
Staging functional tests: PASS
Staging load tests: PASS
Backup: SUCCESS
Restore drill: NOT DONE
Rollback procedure: UNKNOWN
On-call owner: READY
```

1. Decision: GO or NO-GO?
2. Why is `Backup: SUCCESS` insufficient?
3. What must be done to turn statuses green?
4. Who holds authority to accept risk?
5. How should evidence be recorded?

### Exercise 17 — Release Runbook

Draft a runbook covering:

- Source/target versions and FCV;
- Nodes and components;
- Backup ID and recovery point;
- Official upgrade procedure links;
- Upgrade sequence;
- PASS criteria for each step;
- Stop conditions;
- Rollback/recovery actions;
- Monitoring and alerts;
- Owners and approvals.

### Exercise 18 — Post-Upgrade Validation

One day after the upgrade, APIs look normal yet the backup agent repeatedly fails.

1. Can the change be closed?
2. Which recovery metrics are impacted?
3. How should compatibility be resolved?
4. Should another restore drill be run?
5. How do you monitor until the system stabilizes?

## 41. Full Pre-Upgrade Checklist

### Inventory and Compatibility

- [ ] Current and target MongoDB Server versions known for all components.
- [ ] Current FCV and target FCV documented.
- [ ] Official upgrade path confirmed for every hop.
- [ ] Release notes and known issues reviewed.
- [ ] OS/CPU/container support verified.
- [ ] Drivers/ODMs/frameworks compatible.
- [ ] MongoDB Tools, backup, and monitoring versions compatible.
- [ ] TLS/auth/KMS/Queryable Encryption compatible.
- [ ] Search/Vector/CDC consumers included in scope.
- [ ] Replica set / sharded cluster topology inventoried.

### Backups and Restore

- [ ] Latest backup succeeded per policy.
- [ ] Valid recovery point identified.
- [ ] PITR/oplog coverage satisfies RPO.
- [ ] Backup encryption and keys verified.
- [ ] Backups isolated from primary failure domain where required.
- [ ] Restore drill completed.
- [ ] Post-restore data integrity verified.
- [ ] RPO/RTO measured and approved.
- [ ] Restore target, capacity, and credentials ready.
- [ ] Security policy protecting restored data in place.

### Testing and Operations

- [ ] Staging adequately represents topology, data, and workload.
- [ ] Functional and regression tests pass.
- [ ] Business invariants and tenant ACL tests pass.
- [ ] Transaction, retry, and failover tests pass.
- [ ] CDC resume tests pass.
- [ ] Search/Vector query and index tests pass if applicable.
- [ ] Read/write p95/p99 and errors stay within budget.
- [ ] Resource and capacity headroom sufficient.
- [ ] Change window and freeze scope established.
- [ ] Rollback/recovery rehearsed to the extent supported.
- [ ] Stop criteria and decision-makers assigned.
- [ ] Alerts, on-call, and communication channels ready.
- [ ] FCV raised only at its approved gate.
- [ ] Post-upgrade monitoring and closure criteria defined.

## 42. Official Reference Documentation

For a **real production upgrade**, always consult the official documentation for your **exact target MongoDB release, source version, and deployment topology**, rather than relying solely on general principles in this lesson.

- [MongoDB Upgrade Procedures](https://www.mongodb.com/docs/manual/release-notes/upgrade/)
- [MongoDB Release Notes](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB `getParameter`](https://www.mongodb.com/docs/manual/reference/command/getParameter/)
- [MongoDB Compatibility Changes](https://www.mongodb.com/docs/manual/release-notes/)
- [MongoDB Platform Support](https://www.mongodb.com/docs/manual/administration/production-notes/)
- [MongoDB Drivers](https://www.mongodb.com/docs/drivers/)
- [MongoDB Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/)
- [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB `mongodump`](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB `mongorestore`](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Replica Set Administration](https://www.mongodb.com/docs/manual/administration/replica-set-deployment/)
- [MongoDB Sharded Cluster Administration](https://www.mongodb.com/docs/manual/administration/sharded-cluster-administration/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Query Plans and Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)

## Conclusion

**MongoDB upgrade preparation** protects the **correctness, availability, and recoverability** of the entire system—not merely installing a new binary.

A safe plan begins with **inventory and baseline**: knowing MongoDB Server versions, FCV, topology, drivers, frameworks, OS, indexes, backup agents, Search/Vector Search, CDC, and critical query shapes. From there, build a **compatibility matrix with sources and verification dates**, confirming the official upgrade path and component ordering.

**Backups** prove their value only once the organization has **run a restore drill**, measured RPO/RTO, validated data integrity, and confirmed encryption keys, access, and capacity for recovery. **Application rollback, MongoDB downgrade, and backup restore** are three separate strategies with distinct limits and risks; "having a snapshot" never guarantees a zero-data-loss return.

Finally, **test in a production-like environment** with representative data and workloads: CRUD, aggregations, indexes, transactions, change streams, Search/Vector Search, auth/TLS, failovers, and p95/p99 latency. Before every production step, enforce **GO/NO-GO gates**, clear owners, continuous observability, and explicit stop criteria. Above all, **never raise FCV or enable new features solely because binaries started** before completing verification and recovery sign-off.

**A successful upgrade is not defined by the server printing a new version number. It succeeds when data stays accurate, users remain served within SLOs, backups keep running, and the operations team knows exactly what to do if any step fails.**

