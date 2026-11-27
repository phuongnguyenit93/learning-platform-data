# Testing Data Migrations and Backup Restores

A MongoDB migration can exit cleanly in the terminal with zero errors and still lose data, generate duplicate records, corrupt BSON types, or leave the application unable to meet target latencies. Likewise, a backup can report `SUCCESS` yet **fail to restore to the required point in time, with the right permissions, or within the timeframe demanded by the business**.

Therefore, testing migrations and restores is never just about running `mongodump`, `mongorestore`, or comparing total document counts. You must verify **the entire data and availability contract**: accurate data, consistent state, intact indexes/constraints/metadata, working application connectivity, uninterrupted change streams, acceptable performance, and proven recoverability according to plan.

This lesson, **"Testing Data Migrations and Backup Restores,"** in the **Testing** chapter builds a practical framework applicable to MongoDB standalone, replica set, sharded cluster, Atlas, and self-managed deployments. It focuses on test design methodology, preparation steps, observability commands, failure scenarios, RPO/RTO evaluation, and evidence for **GO/NO-GO** decisions.

> **Definition of success:** A data migration succeeds when **the target dataset matches the committed source state at the comparison baseline**, critical invariants and metadata are preserved, and the application operates normally. A backup restore succeeds when **a guaranteed state can be rebuilt at the chosen recovery point**, the data is usable, and RPO/RTO targets are met. Both criteria must be verified independently.

---

## 1. Distinguishing Migrations, Backups, and Restores

| Activity | Primary Goal | Typical Risks |
|---|---|---|
| Data migration | Move data to a target system, version, schema, or cluster | Missing/duplicate/corrupted data, conversion bugs, lost writes during cutover |
| Schema migration | Evolve document structures or constraints | Dropped fields, wrong types, duplicate keys, mismatched indexes |
| Version upgrade | Change MongoDB version and compatible components | FCV issues, behavior shifts, driver/OS incompatibility |
| Backup | Produce a recovery artifact / restore point | Inconsistent backup, missing collections, inaccessible encryption keys |
| Restore | Recover data from a backup | Wrong recovery point, broken indexes/metadata, exceeded RTO |
| Disaster recovery | Restore full service after a broad outage | DNS, app configs, external dependencies, excessive loss window |
| Reconciliation | Verify source vs. target data parity | Missing discrepancies when comparing only total counts |
| Cutover | Switch clients and traffic to the target | Split-brain writes, stale reads, difficult rollback |

Several of these activities may occur within the same project, yet each needs **dedicated test cases and acceptance criteria**. Migrating to a new cluster does not automatically prove backups on the new cluster can restore. A successful restore does not automatically prove the business application runs cleanly on a new schema.

## 2. Common MongoDB Scenarios Requiring Testing

1. **MongoDB self-managed -> MongoDB Atlas**.
2. **Atlas cluster A -> Atlas cluster B** across regions or topologies.
3. **Standalone -> replica set** following a supported procedure.
4. **Replica set -> sharded cluster** with deliberate shard-key design.
5. **Major MongoDB Server version upgrades**, including controlled FCV updates.
6. **BSON schema changes**: renaming fields, splitting, or merging collections.
7. **Historical data backfills** or moving records into new collections.
8. **Logical export/import** across collections or services.
9. **Pre-release backup restores**.
10. **Point-in-Time Recovery (PITR)** after accidental deletion or logic corruption.
11. **Cross-region recovery** when a primary region fails.
12. **Disaster recovery drills** verifying actual recovery timelines.
13. **Partial collection recovery** for investigation or targeted repair.
14. **Transitioning from one encryption/KMS configuration to another supported setup**.
15. **Restoring Search/Vector Search workloads** where indexes must resynchronize.

Never rely on one trivial demo scenario for everything: a 1,000-document collection on a standalone node cannot simulate sharded transactions, replication lag, background index builds, or hundreds of GiB of data.

## 3. Ownership Model and Scope

Before running tests, clarify roles:

```text
Business owner
     │
     ├── Confirms critical data scope and RPO/RTO
     │
Application team
     │
     ├── Tests schemas, queries, transactions, workflows
     │
DBA / Database platform
     │
     ├── Backup/restore, topology, indexes, consistency
     │
Security team
     │
     ├── Data masking, IAM, KMS, TLS, auditing
     │
SRE / Operations
     │
     ├── Load/failover, runbooks, monitoring, GO/NO-GO
     │
     ▼
Verified migration / restore
```

On smaller teams one person may wear multiple hats, yet **testing accountability and sign-off approvers** must remain explicit.

### 3.1. What Must Be Documented

- Source deployment, databases, and collections;
- Target deployment, databases, and collections;
- Current and target MongoDB structures;
- MongoDB Server versions and Feature Compatibility Versions (FCV);
- Application, driver, and ODM versions;
- Schema transformations;
- Replica-set / sharding topologies;
- Document counts, data sizes, and index sizes;
- Rules for handling new writes during copying;
- RPO/RTO targets;
- Maintenance window / cutover plan;
- Rollback / recovery strategy;
- Data security scope during testing;
- Stop criteria and owners.

## 4. Defining Three Levels of Correctness

Every migration or restore should be validated at three levels.

### 4.1. Structural Correctness

- Target databases and collections exist;
- Correct collection types (regular, time-series, capped, etc.) where applicable;
- Correct document validation rules;
- Exact index definitions;
- Correct unique, TTL, and partial index semantics;
- Matching collation settings;
- Valid view definitions;
- Accurate sharding and shard-key metadata;
- Planned users and roles provisioned properly.

### 4.2. Data Correctness

- Zero missing documents as of the baseline point;
- Zero duplicate business keys;
- Zero out-of-scope stray records;
- Accurate `_id`, `tenantId`, and relationships;
- Complete nested documents and arrays;
- Exact types for `Decimal128`, `NumberLong`, `Date`, and `ObjectId`;
- Null fields and missing fields preserved distinctly;
- Deletions or tombstones reflected accurately;
- Totals, statuses, balances, and business invariants hold.

### 4.3. Operational Correctness

- Application queries execute cleanly;
- Authentication and authorization succeed with real service accounts;
- Read/write concerns and transactions function properly;
- Change streams or CDC pipelines resume cleanly;
- Subsequent backups run properly on the target;
- Performance and resource consumption meet expectations;
- Failover, rollback, and recovery procedures work;
- Search/Vector Search indexes are ready if product workflows depend on them.

**Matching total document counts never proves these three categories are satisfied.**

## 5. Defining the Baseline Data State to Compare

A critical question:

> At **which exact moment** must source and target match?

If the source keeps receiving writes during a multi-hour copy, comparing the live source now against a target whose initial copy just finished will show **expected** differences.

Example timeline:

```text
12:00    T0: start snapshot/copy
12:10        10,000 new writes occur
13:00    T1: initial copy completes
13:15        CDC catches up to watermark W
13:20    T2: cutover with write fence
13:25        Target becomes source of truth
```

Tests must explicitly state:

- Snapshot time `T0`;
- CDC resume point / watermark `W`;
- Cutover instant `T2`;
- Which writes fall before vs. after the boundary;
- When the source freezes writes or stops receiving traffic;
- Which official state serves as the reconciliation truth.

### 5.1. Do Not Substitute Application Clock Time for Database Consistency

Clock skew across app nodes can prevent `createdAt` or `updatedAt` from reflecting true commit order. When capturing change streams accurately, use MongoDB-supported mechanisms such as the oplog, change streams, and resume tokens — never just "every document with `updatedAt` greater than local wall time."

### 5.2. Create a Reconciliation Contract

Example:

```yaml
migrationId: customer-move-2026-11
sourceCluster: cluster-A
targetCluster: cluster-B
sourceNamespace: commerce.orders
targetNamespace: commerce.orders
scope:
  tenants: all
  status: all
pointOfComparison:
  type: snapshot-plus-cdc-watermark
expected:
  documentIdentity: [tenantId, orderId]
  preserveFields: [amountCents, status, createdAt]
  transformVersion: v2
  uniqueConstraints: [tenantId, orderId]
  allowedDifferences:
    - migrationAudit.generatedAt
```

This is an **illustrative contract**, not a built-in MongoDB format. It aligns everyone on **what is permitted to differ and what must match identically**.

## 6. RPO, RTO, and RLO Metrics

- **RPO (Recovery Point Objective):** maximum tolerable data loss measured in time.
- **RTO (Recovery Time Objective):** maximum tolerable duration to restore business functionality.
- **RLO (Recovery Level Objective):** sometimes used internally to specify minimum degraded service capability during recovery; not every organization uses this term.

Example:

```text
RPO: 10 minutes
RTO: 60 minutes

Incident time: 14:00
Recovered to: 13:56
Service operational at: 14:42
```

When measured accurately, a 4-minute loss window and a 42-minute recovery time fall within target. Still, verify the **actual commit point**, not just the timestamp in a backup filename or the moment an operator clicked Restore.

### 6.1. Recovery Is More Than a Running Server

RTO should typically be measured until **critical customer services can actually serve requests**:

```text
Incident declared
     │
     ▼
Recovery triggered
     │
     ▼
MongoDB data restored
     │
     ▼
Indexes / auth / networking ready
     │
     ▼
Application smoke tests pass
     │
     ▼
Critical customer workflows available  <- RTO endpoint
```

If the database TCP port opens while critical indexes are missing, CDC has not resumed, and payment flows fail, the service has not recovered.

## 7. Testing Backups Differs from Running Backup Jobs

A backup artifact may:

- Miss namespaces;
- Capture inconsistent state;
- Lack oplog history needed for PITR;
- Be incompatible with target servers or tools;
- Be encrypted with a lost or inaccessible KMS key;
- Be corrupted or only partially uploaded;
- Contain documents while omitting required users and roles;
- Miss or fail to restore components outside MongoDB;
- Be too massive to restore within RTO.

Testing must cover **backup generation -> artifact verification -> restore -> integrity/functional validation -> timing measurement**.

### 7.1. A "SUCCESS" Job Status Is Only a Starting Signal

A backup tool reporting `SUCCESS` only confirms the job finished its own internal checks. Never extrapolate that:

- RTO is met;
- The recovery point is accurate;
- All business invariants hold;
- All KMS keys remain accessible;
- MongoDB Search indexes rebuild in time;
- The same procedure scales to a sharded cluster.

**A restore drill is far stronger evidence than a backup job status.**

## 8. MongoDB Backup Methods Requiring Distinct Tests

| Method | High-Level Behavior | Key Verification Points |
|---|---|---|
| Atlas Cloud Backup | Tier- and config-dependent snapshots/continuous backup | Retention policies, restore targets, PITR support |
| `mongodump`/`mongorestore` | Logical BSON dump/restore | Snapshot consistency, namespaces, metadata, indexes |
| Filesystem/block snapshot | Physical storage-volume snapshot | Quiescence/consistency, journal inclusion, complete file set |
| Oplog-based/PITR | Base backup plus change log replay | Oplog window, recovery point accuracy, operation ordering |
| Backup agent/vendor | Vendor-specific workflow | Compatibility, encryption, restore drills |
| Application-level export | CSV/JSON/custom pipeline | Type fidelity, completeness, metadata preservation |

### 8.1. Logical Dumps Are Not Automatically Consistent

While `mongodump` reads a collection, clients may concurrently insert, update, or delete records. Without a supported point-in-time snapshot mechanism, a dump can reflect **inconsistent points in time**.

Options like `mongodump --oplog` provide oplog-based consistency under **specific deployment conditions**, yet are not a universal solution across every topology or sharded cluster. Consult official MongoDB Database Tools and backup documentation for your deployment architecture.

### 8.2. Volume Snapshots Also Require Consistency

Snapshotting data files while `mongod` is actively writing without following a supported procedure can yield unrecoverable artifacts. On sharded clusters, snapshotting shards at unsynchronized instants creates cross-shard data and metadata inconsistencies.

Never build a DR policy around "our cloud disk has a snapshot button" without running a topology-accurate restore drill.

### 8.3. Replication Is Not a Backup

Three replicas faithfully mirroring an accidental deletion or destructive update cannot restore the state prior to that committed command. Replication provides availability; **backups and PITR** provide point-in-time state recovery.

## 9. Building a Test Matrix

A practical matrix:

| Test Group | Objective | Evidence | Priority |
|---|---|---|---|
| Inventory | No missing collections/indexes/views | Source/target catalogs | Critical |
| Document counts | Zero losses or unintended duplicates | Namespace and tenant counts | Critical |
| Field/type fidelity | Preserve BSON semantics | Golden records, type counts | Critical |
| Business invariants | Totals/balances/states match | Aggregation reconciliation | Critical |
| Index constraints | Unique/TTL/partial rules intact | `listIndexes` + negative tests | Critical |
| Writes during copy | Zero lost delta changes | Watermark/CDC replay checks | Critical |
| Cutover | No dual primary writers | Write fences and audit logs | Critical |
| Backup restore | Recoverable valid artifact | Restore drill logs | Critical |
| RPO/RTO | Meet stated business SLAs | Timeline and commit watermarks | Critical |
| Authorization | Zero tenant/PII exposure | Security test suite | Critical |
| Driver/API | Connectivity, CRUD, transactions | Integration tests | High |
| Query performance | No severe latency/scan regressions | p95/p99, explain metrics | High |
| Failover | Survive node/member loss | Staging chaos tests | High |
| Search/CDC | Index and event catch-up | Lag and consumer checks | High if used |
| Batch/report jobs | Run cleanly post-move | Job execution logs | Medium/High |
| Rare edge cases | Nulls, arrays, large docs | Edge-case fixtures | High |

Adjust weights to your domain. A financial ledger prioritizes balance and transaction invariants far above auxiliary reporting pages.

## 10. Preparing an Isolated Test Environment

Never restore production copies directly over a cluster serving other live data.

A safe test environment includes:

```text
Dedicated restore target
   │
   ├── No public inbound access
   ├── Least-privilege RBAC
   ├── Encryption / TLS / KMS
   ├── Network routing isolated from production
   ├── Adequate disk / CPU / RAM
   ├── Compatible drivers / DB Tools
   ├── Monitoring and alerting
   └── Cleanup and retention policies
```

### 10.1. Double-Check Target Namespaces

Commands like `mongorestore --drop`, `db.dropDatabase()`, or index rebuilds modify or erase data. Before executing, verify:

- The MongoDB URI targets the intended test cluster;
- Database names are exact;
- Namespace mappings are accurate;
- Credentials carry restricted scope;
- Zero production application traffic routes there;
- Pre-change target snapshots exist if preserving target state matters.

### 10.2. Protecting PII

Production data copied into staging or DR drills remains sensitive data. If real data is used, enforce policy approval, masking, encryption, strict access controls, and bounded retention.

Never paste sample documents containing emails, phone numbers, addresses, secrets, or payment data into tickets or shared logs.

## 11. Source Data Inventory

Before migrating, catalog everything moving:

```text
Databases
 Collections
  - Collection options / validators
  - Document counts and sizes
  - Indexes and constraints
  - Collation
  - Views
  - Time-series / capped settings
 Users / roles (per backup/migration scope)
 Sharding metadata
 GridFS / file buckets if used
 Search / Vector indexes
 Change stream consumers
 External dependencies
```

### 11.1. Read-Only `mongosh` Inspection

```javascript
const dbSource = db.getSiblingDB("commerce");

printjson(dbSource.getCollectionNames());
printjson(dbSource.getCollectionInfos());

printjson(dbSource.orders.getIndexes());

printjson(dbSource.runCommand({
  collStats: "orders",
  scale: 1024 * 1024
}));
```

Command permissions and support vary by deployment and version. `collStats` reports storage-engine sizing semantics, not a transactional snapshot guarantee.

### 11.2. Never Inspect Just One Node and Assume It Represents the Cluster

On replica sets, observe replication lag and member health. On sharded clusters, query data and metadata through supported paths (`mongos`) and inspect individual shards when necessary.

### 11.3. Inventories Must Carry Timestamps

If the source grows by 10,000 documents per minute, yesterday's count is useless for today's migration. Record:

```text
UTC timestamp
Topology
Source version / FCV
Namespace
Counting method
Filters
Snapshot / watermark
Measurement owner
```

## 12. Fixtures: Essential Edge-Case Datasets

Suites containing only "clean" happy-path documents miss conversion bugs.

Include:

- `_id` types (`ObjectId`, String, or whatever the business uses);
- `NumberInt`, `NumberLong`, `Double`, `Decimal128`;
- Pre-1970 dates, timezone shifts, and daylight saving transitions (if relevant);
- Explicit `null` vs. missing fields;
- Empty arrays, long arrays, deeply nested objects;
- Vietnamese Unicode, emojis, and combining characters;
- Empty/long strings and collation-sensitive strings;
- Negative, zero, and extreme numeric bounds;
- Intentional duplicate business keys inside error fixtures;
- Soft-deleted records;
- Expired and near-expiry TTL records;
- BSON documents near size limits;
- Multi-document transactions;
- Identical business keys across distinct tenants;
- Documents spanning multiple shard keys;
- Schema-valid and legacy invalid records per lifecycle phase.

### 12.1. Example Fixture

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "T-01",
  orderNo: "A-0001",
  amount: NumberDecimal("999999999.9999"),
  quantity: NumberLong("9007199254740993"),
  createdAt: ISODate("2026-11-14T02:30:00.000Z"),
  note: "Order – Unicode test 🧪",
  optionalValue: null,
  tags: ["priority", "gift"],
  nested: {
    flag: true,
    code: 0
  }
}
```

The `quantity` value exceeds JavaScript `Number` safe integer precision. Exporting through plain JSON and parsing as a floating-point `Number` silently rounds it, whereas BSON `Long` preserves exact precision.

### 12.2. `null` vs. Missing Fields

```javascript
{ _id: 1, x: null }
{ _id: 2 }
```

These two documents are structurally distinct. A faulty migration can turn missing fields into `null` or vice versa, silently altering partial indexes, schema validation, and queries.

## 13. Testing Lossless BSON Conversion

MongoDB stores BSON natively; exporting through plain JSON/CSV or external languages frequently mutates types.

| Source Value | Common Pitfall | Consequence |
|---|---|---|
| `ObjectId` | Unintentionally cast to String | `_id` joins/lookups fail |
| Large `NumberLong` | Converted to JS double | Silent precision loss |
| `Decimal128` | Parsed as `double` | Monetary rounding errors |
| `Date` | Formatted as local-timezone string | Shifted timestamps |
| Binary / UUID | Altered subtype/representation | Unreadable IDs |
| `null` / missing | Auto-filled with defaults | Query & partial-index behavior changes |
| Arrays | Flattened or reordered | Corrupted business semantics |
| Nested documents | Partially renamed fields | Application deserialization breaks |
| Collation-sensitive strings | Naively lowercased | Original data unrecoverable |
| Timestamp / special BSON types | Coerced to strings | Lost BSON semantics |

### 13.1. Extended JSON

MongoDB defines **Extended JSON** to preserve BSON type metadata inside JSON text. Whenever text export is unavoidable, pick canonical vs. relaxed mode intentionally and test round-trip fidelity:

```text
BSON source
   -> Extended JSON (chosen mode)
   -> Parser
   -> BSON target
   -> Type and value comparison
```

Never mistake `JSON.stringify` for a BSON-preserving MongoDB backup mechanism.

### 13.2. Round-Trip Test

A solid test:

1. Inserts edge-case fixtures into a test collection.
2. Reads them back via the MongoDB Driver.
3. Runs export and import through the migration path.
4. Reads target documents.
5. Compares both **values and BSON types**.
6. Executes representative queries to compare behavior.
7. Verifies indexes and unique constraints.

## 14. Comparing Document Counts: First Step, Not Final Proof

Run:

```javascript
db.getSiblingDB("commerce").orders.countDocuments({
  tenantId: "T-01"
});
```

When frozen at the same snapshot or watermark, source and target counts should align after accounting for approved transformation rules.

### 14.1. When Counts Differ by Design

A migration may intentionally:

- Drop expired records;
- Deduplicate records per business policy;
- Split one document into several documents;
- Retire obsolete fields or collections;
- Route certain records to cold archives.

Define an **expected transformation formula**:

```text
Source eligible documents: 1,000,000
Excluded by approved retention: 20,000
Rejected with documented invalid data: 30
Expected target documents: 979,970
```

Never shrug off 30 missing records and declare PASS unless those exact rejections follow approved policy and evidence.

### 14.2. Counts Fluctuate Under Active Writes

While the source handles writes and the target replays CDC events, instant count mismatches do not prove data loss. Compare at the **same logical point** or reconcile up to a shared watermark.

### 14.3. Never Use `estimatedDocumentCount()` for Exact Reconciliation

Estimated counts rely on collection metadata — handy for quick sanity checks, useless for proving completeness against a snapshot or predicate. Because `countDocuments()` can be heavy on large collections, schedule it wisely with appropriate indexes and windows.

## 15. Comparing Distributions Instead of Just Totals

Suppose:

```text
Source total: 10,000,000
Target total: 10,000,000
```

You could still be missing 5,000 records for Tenant A while holding 5,000 extra records for Tenant B.

Group comparison:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Group similarly across:

- Tenant;
- Status;
- Day/month buckets;
- Shard-key ranges;
- Document types;
- Product categories;
- Soft-delete flags.

### 15.1. Aggregate Business Totals

Example:

```javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      totalAmount: { $sum: "$amount" }
    }
  },
  { $sort: { _id: 1 } }
]);
```

Reconciling `totalAmount` is only valid when currency units, eligibility criteria, and comparison checkpoints align — preserving `Decimal128` precision throughout.

### 15.2. Standardize Automated Reconciliation Reports

```text
count_by_tenant
count_by_status
count_by_day
amount_sum_by_currency
min/max_createdAt
duplicates_by_business_key
missing_required_fields
null/type_distribution
```

Pretty dashboards cannot replace an auditable table of `expected / actual / diff`.

## 16. Detecting Missing or Duplicate Records via Business Keys

Suppose the business key of `orders` is `(tenantId, orderNo)`.

### 16.1. Detecting Target Duplicates

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        orderNo: "$orderNo"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
```

Although read-only, this aggregation scans extensive data and stresses the cluster; schedule carefully and leverage supporting indexes.

### 16.2. Comparing Key Sets

Conceptually:

```text
sourceKeys = set of business keys on source at watermark W
targetKeys = set of business keys on target at watermark W

missing = sourceKeys - targetKeys
extra   = targetKeys - sourceKeys
```

At scale, never load hundreds of millions of keys into JVM heap. Instead:

- Partition by key ranges or tenants;
- Hash canonical records per partition;
- Use external sort/merge joins;
- Run dedicated reconciliation pipelines;
- Export key lists only to secured storage;
- Retain detailed diagnostics for mismatched partitions.

### 16.3. Anti-Pattern: Spot-Checking Only the First 100 Records

Seeing `find().limit(100)` match proves 100 records match, not 100 million records. Sampling complements reconciliation but never replaces **full verification** when business criticality demands completeness.

## 17. Canonical Hashing and Checksums

Hashing compares partition contents efficiently without printing every record.

Reliable hashes require deterministic **canonical serialization**:

1. Include only the scoped comparison fields;
2. Apply approved migration transformations uniformly;
3. Preserve BSON type distinctions;
4. Enforce deterministic key ordering during serialization;
5. Preserve array element order where semantically meaningful;
6. Distinguish missing fields from explicit `null`;
7. Normalize timezones and decimal scales consistently;
8. Use a strong hash algorithm such as SHA-256.

### 17.1. Conceptual Example

```text
Partition: tenant T-01, createdAt 2026-11-14
Source:
  record_count = 50,000
  canonical_hash = abc...

Target:
  record_count = 50,000
  canonical_hash = abc...
```

When both sides follow identical canonicalization rules, matching partition hashes provide far stronger confidence than counts alone — yet still do not replace business-logic checks, index/metadata validation, or point-in-time consistency guarantees.

### 17.2. Never Hash Raw Plain JSON Strings

Two logically identical documents with different key ordering or different `NumberLong`/`Decimal128` serialization produce different JSON strings, while plain JSON parsers can round large numbers. Build versioned canonicalizers and validate them with golden fixtures.

### 17.3. Do Not Rely Exclusively on `dbHash`

MongoDB offers the `dbHash` command in certain contexts and versions, yet it carries strict usage constraints — especially under active writes or sharded topologies. Never treat `dbHash` as a universal verification silver bullet across topologies and schema transformations.

### 17.4. Store Hash Evidence Securely

Low-entropy partition inputs can allow guessing from hashes. Never expose raw keys or PII in public reports; store reconciliation evidence behind strict access controls.

## 18. Verifying Indexes, Validators, and Collection Options

Complete data with missing indexes degrades queries from milliseconds to seconds or leaves unique constraints unenforced.

### 18.1. Inspection Commands

```javascript
const targetDb = db.getSiblingDB("commerce");

printjson(targetDb.orders.getIndexes());

printjson(targetDb.getCollectionInfos({
  name: "orders"
}));
```

Compare:

- Index keys in **exact order**;
- `unique`, `sparse`, and partial filter expressions;
- `expireAfterSeconds`;
- `collation`;
- `hidden` and version-specific options;
- Collection validators;
- Time-series / capped options;
- Sharding metadata;
- Views;
- Dedicated Search indexes.

### 18.2. Never Compare Indexes by Name Alone

Two indexes sharing the same name with different key orders or options are not equivalent. Altering field names or key ordering breaks query plans and uniqueness rules.

### 18.3. Source and Target Indexes May Differ Intentionally

If a migration tunes query performance, the target index list may intentionally evolve. Compare targets against the **intended target index manifest**, not blindly byte-for-byte against the legacy source.

### 18.4. Did Index Builds Finish?

A migration is incomplete while critical index builds remain in progress or failed. Wait for build completion per server/version semantics and verify via both catalog checks and workload tests.

## 19. Testing Unique Indexes with Negative Cases

For a unique `(tenantId, orderNo)` index, test duplicate rejection in an isolated **staging** collection:

```javascript
db.orders_test.insertOne({
  _id: "TEST-UQ-1",
  tenantId: "T-01",
  orderNo: "A-001"
});

db.orders_test.insertOne({
  _id: "TEST-UQ-2",
  tenantId: "T-01",
  orderNo: "A-001"
});
```

When the unique compound index is active, the second insert must fail with a duplicate-key constraint error. Because this is a **write test**, run it solely against a dedicated test collection with strict cleanup.

### 19.1. Multi-Tenant Scope Checks

```text
T-01 / A-001
T-02 / A-001
```

should be permitted when uniqueness is scoped per tenant — or rejected if global uniqueness is required. Write explicit positive/negative cases for your exact policy.

### 19.2. Nulls, Missing Fields, and Partial Unique Indexes

Unique indexes follow specific semantics for `null` and missing fields, while partial unique indexes enforce uniqueness only over matching subsets. Test records entering and leaving partial filter boundaries as well as duplicates after soft-delete/restore flows.

## 20. TTL: A Major Pitfall in Restore Drills

If a backup contains documents whose `expiresAt` timestamp lies in the past relative to restore time, an active TTL index will cause MongoDB to delete them soon after restore.

Example:

```javascript
{
  _id: "SESSION-001",
  expiresAt: ISODate("2026-11-01T00:00:00Z")
}
```

Restoring on November 14, 2026 with a TTL of `expireAfterSeconds: 0` marks that document immediately eligible for deletion. Counting documents minutes later will show shrinking counts even though the restore originally loaded every record accurately.

### 20.1. Questions to Verify

- Does a TTL index exist in the backup or target?
- How many documents are already past expiration?
- Does the recovery aim to restore **historical audit state** or current active records?
- Does policy allow inspecting restored data before TTL sweeps run?
- Can an isolated forensic environment follow an approved procedure?
- Should restore evidence be captured prior to TTL sweeps?
- Does your backup/restore workflow handle TTL behavior as required?

### 20.2. Never Arbitrarily Disable Production TTL Policies

Disabling TTL violates data retention policies or resurrects expired sessions. Adjust test environments and verification timing deliberately rather than tampering with sensitive retention policies just to make counts match.

### 20.3. TTL Does Not Fire on Exact Milliseconds

The MongoDB TTL monitor runs periodically in the background. Never write assertions demanding a document vanish on an exact millisecond boundary.

## 21. Checking Users, Roles, and Security Post-Migration/Restore

A data restore does **not automatically guarantee** every user account and connection path still works identically.

Verify according to your backup/migration method:

- Were database users and custom roles copied?
- Do app service accounts hold exact least-privilege roles?
- Do SCRAM/X.509/OIDC/LDAP/Kerberos flows work?
- Are TLS certificates, CA truststores, and SAN hostnames valid?
- Are KMS/encryption keys accessible?
- Does Client-Side Field Level Encryption / Queryable Encryption metadata align?
- Are Atlas project network rules and private endpoints configured?
- Is audit logging still enabled?
- Did the restore target accidentally inherit overly broad permissions?

### 21.1. Never Use Root to Mask RBAC Failures

If the app fails to query under its service account, testing with root hides the RBAC defect. Run smoke checks with the **real service identity** or an identically scoped test identity.

### 21.2. Negative Authorization Tests

For multi-tenant systems, verify:

```text
Tenant A reads only Tenant A records.
Tenant A cannot query Tenant B records.
A service without index-admin rights cannot drop indexes.
Untrusted users cannot read backup artifacts.
```

Verify not only that legitimate reads succeed, but that **unauthorized actions are denied**.

## 22. Offline Migrations: Simpler Verification

An **offline migration** introduces a write freeze window:

```text
Stop/fence writes
      │
      ▼
Take consistent backup/export
      │
      ▼
Copy to target
      │
      ▼
Restore/import
      │
      ▼
Run reconciliation
      │
      ▼
Application smoke/performance
      │
      ▼
Switch traffic
      │
      ▼
Resume writes on target
```

Advantages:

- Straightforward frozen source state;
- Easy count and hash reconciliation;
- Minimal CDC and conflict complexity;
- Easier rollback before enabling target writes.

Drawbacks:

- Requires downtime / maintenance window;
- Large datasets may make copy/restore exceed RTO;
- Every background writer must truly be fenced;
- External services require coordinated pausing.

### 22.1. "Stopping the API" Rarely Stops All Writes

Look out for:

- Scheduled jobs;
- Kafka consumers;
- Change stream processors;
- Batch imports;
- Cron maintenance scripts;
- Other microservices;
- Ad-hoc admin scripts;
- TTL deletions.

Enforce a reliable **write fence** and monitor metrics proving zero stray writers remain active.

## 23. Online Migrations: Snapshot Plus CDC

**Online migrations** let the source keep accepting writes during the initial copy.

Architecture:

```text
                        Source MongoDB
                              │
             ┌────────────────┴─────────────────┐
             ▼                                  ▼
       Initial copy                       Change stream / CDC
             │                                  │
             ▼                                  ▼
       Target MongoDB <────────────────── Delta apply
             │
             ▼
       Reconciliation to watermark
             │
             ▼
        Write fence / cutover
             │
             ▼
      Target becomes authoritative
```

### 23.1. Mandatory Test Cases

- Initial snapshot captures a consistent state per the chosen method;
- CDC begins at a point guaranteeing zero missed deltas;
- Inserts, updates, and deletes all apply accurately;
- Event ordering is preserved where business semantics demand it;
- Retries produce zero duplicate side effects;
- Resume tokens persist safely;
- Temporary network disconnects recover cleanly;
- Oplog retention window covers outages comfortably;
- Multiple rapid mutations to the same document converge properly;
- Multi-document transaction events preserve atomicity/ordering semantics;
- Before cutover, the target catches up to the committed watermark;
- After cutover, zero writes reach the old source.

### 23.2. Relying Only on `updatedAt` Is Insufficient

`updatedAt` can:

- Be skipped by certain write paths;
- Drift under server clock skew;
- Fail to represent physical deletes;
- Lose transaction commit ordering;
- Collide across identical timestamps.

Design proper change capture using resume tokens, operation ordering, and explicit reconciliation.

## 24. Change Streams and Resume Tests

A MongoDB change-stream consumer reads change events appropriate for the topology and version.

`mongosh` structural sketch:

```javascript
const stream = db.getSiblingDB("commerce")
  .orders.watch();

try {
  // In staging, consumer calls next/tryNext per test workflow.
  // Persist resume token safely only after applying to target.
} finally {
  stream.close();
}
```

This snippet illustrates the API only. Production pipelines require durable consumers, checkpoints, bounded retries, and security hardening.

### 24.1. Resume Tokens Are Critical State

Consumers must persist checkpoints only **after successfully applying events** so restarts do not skip changes. Checkpointing before writing to the target risks permanently dropping events on crash.

### 24.2. Inject Failures Right at Checkpoint Boundaries

In staging:

```text
Read event E1
  │
  ▼
Apply E1 to target
  │
  ▼
Crash before checkpoint
```

Upon restart, `E1` will be redelivered. Target writes must be idempotent or guarded by deduplication/version checks.

### 24.3. Oplog Window Limits

If a consumer stops long enough for its resume token to age out of the oplog, a full resnapshot and reconciliation may be required. Never assume `resumeAfter` works indefinitely under all outages.

### 24.4. Transactions and Ordering

One transaction can emit multiple change events. Applying them out of transaction boundaries can briefly or permanently expose invalid states on the target. Test transaction commits, aborts, and ordering where supported.

## 25. Dual Writes: Preventing Split Brain

Some migrations configure applications to dual-write simultaneously to source and target:

```text
Application
   ├── write source
   └── write target
```

Simple on a whiteboard, hazardous in reality:

```text
Source write: SUCCESS
Target write: TIMEOUT
Application: return HTTP 200 or 500?
```

Or vice versa.

### 25.1. Separate Clusters Do Not Share an Atomic Distributed Transaction

Independent source and target clusters do not share an automatic atomic transaction across both writes.

### 25.2. Risk Mitigation Strategies

- Prefer CDC or transactional outbox patterns over naive dual writes where viable;
- Idempotency keys;
- Versioned writes;
- Durable retry queues;
- Write-ahead event logs;
- Automated reconciliation;
- Chaos/failure injection testing;
- One explicitly designated authoritative source per migration phase.

### 25.3. Never Allow Concurrent Primary Writers Post-Cutover

Allowing writes on both sides without strict conflict resolution causes split-brain divergence. Cutover must enforce clear **write ownership** and fence legacy writers.

## 26. Cutover Testing: The Highest-Risk Moment

Outline of a controlled cutover:

```text
1. Confirm target baseline healthy
2. Confirm CDC lag below approved threshold
3. Announce change window
4. Fence/pause source writes
5. Drain in-flight requests and consumers
6. Apply final deltas to watermark W
7. Run critical reconciliation
8. Switch app routing/connection configuration
9. Validate target smoke + business invariants
10. Resume writes only on target
11. Monitor stabilization
```

### 26.1. Define Per-Step Stop Criteria

For example:

```text
If CDC cannot reach watermark W
or duplicate-key/data-integrity discrepancy remains:
  NO-GO; do not enable target writes.
```

### 26.2. DNS TTLs and Connection Pools

Updating DNS records or URIs does not instantly redirect every live application socket. Drivers maintain connection pools, topology monitors, and retry loops. Verify:

- Old app pods/workers drain cleanly;
- All worker processes use the new target URI;
- Zero residual writes land on the old source;
- Read/write metrics are monitored on both clusters;
- Secret rotations and config reloads take effect cleanly;
- Background jobs and external connectors switch together.

### 26.3. Cutover Is Not Complete Just Because One API Endpoint Returns 200

An API returning 200 could still read stale caches, return incomplete search results, or serve an unmigrated tenant. Test critical workflows across namespaces and tenants.

## 27. Rollback vs. Restore

Keep three concepts distinct:

- **App rollback:** reverting application code or config.
- **Migration rollback:** reverting traffic to the legacy source or executing a reverse sync.
- **Backup restore:** rebuilding state from a backup point.

### 27.1. Once the Target Has Accepted New Writes

If the target becomes authoritative at 15:00 and handles 10,000 new writes, pointing DNS back to the legacy source at 15:20 without replaying changes **loses 10,000 writes**.

Safe rollback typically requires:

- Fencing target writes;
- Capturing target-only deltas;
- Reconciling and replaying deltas back to the legacy source;
- Verifying parity;
- Confirming old application/schema compatibility;
- Switching routing;
- Close monitoring.

Never promise that rollback is merely "swapping the connection string back."

### 27.2. New Schemas May Break Old Application Code

If migration changed BSON types, renamed fields, or tightened constraints, the previous app version may fail to read target documents. Use **expand-and-contract migrations** or maintain backward compatibility throughout the rollback window.

### 27.3. Restoring a Pre-Cutover Backup Also Discards Post-Snapshot Writes

Rolling back via a pre-cutover snapshot reverts data to that snapshot's time; newer writes are lost unless recovered via PITR, replay, or reconciliation.

## 28. Structured Testing for `mongodump` and `mongorestore`

Illustrative commands **in an authorized test environment**:

### 28.1. Creating a Logical Backup

Unix-like shell:

```bash
mongodump \
  --uri "$SOURCE_MONGODB_URI" \
  --db "commerce" \
  --archive="/secure-backups/commerce-test.archive.gz" \
  --gzip
```

This command **does not automatically guarantee** point-in-time consistency if the source is under active writes; selecting a consistent backup method depends on topology and Database Tools documentation. Because archive files hold sensitive data, encrypt and protect them properly.

### 28.2. Restoring to an Empty, Isolated Target

```bash
mongorestore \
  --uri "$ISOLATED_TARGET_MONGODB_URI" \
  --archive="/secure-backups/commerce-test.archive.gz" \
  --gzip
```

This example assumes an eligible empty target without live data to preserve. On Windows PowerShell, environment variable syntax differs from `$SOURCE_MONGODB_URI`.

**Never add `--drop` or target production during a restore test**, as doing so can wipe live collections. Any handling of pre-existing collections must follow an approved runbook.

### 28.3. Mandatory Post-Restore Checks

- Dump/restore tool exit status;
- Error/warning logs;
- Archive file size and checksum;
- Namespace mapping;
- Complete collection list;
- Counts and partition checks;
- Index builds and unique constraints;
- Views and collection options;
- Sample documents and BSON type fixtures;
- Application smoke tests;
- KMS, auth, TLS, and RBAC checks per method;
- End-to-end measured RTO.

### 28.4. Never Assume Users and Roles Transfer Automatically

Database-scoped `mongodump` and other tools handle users/roles differently depending on flags and scope. Explicitly confirm whether your backup artifact and restore procedure **include security metadata**, rather than assuming a dump of `commerce` clones the whole cluster.

## 29. Oplog-Consistent Logical Backups: Known Limits

Some replica-set backup workflows use oplog options to capture recovery-consistent logical dumps, subject to strict conditions:

- Source topology;
- Dump scope;
- Tool and server versions;
- Oplog retention capacity;
- Concurrent write volume;
- Unsupported operations occurring during the dump window;
- Target restore steps.

Never treat `mongodump --oplog` as a magic consistency switch across sharded clusters.

### 29.1. Seed Boundary Marker Writes

In staging:

```text
Before backup window:
  Write marker PRE

During backup window:
  Write marker MID

After chosen recovery point:
  Write marker POST
```

After restoring, confirm only the expected markers appear for the requested recovery point — verifying actual commit/transaction semantics rather than trusting app clock timestamps blindly.

### 29.2. Oplog Replay Can Fail Too

Gaps in oplog history, mismatched tool versions, or missing metadata can break oplog replay. A successful base dump alone does not prove PITR restoration works end-to-end.

## 30. Atlas Backup / PITR Restore Drills

In MongoDB Atlas, backup/restore and PITR capabilities depend on **cluster tier, enabled features, region, retention, and configuration**. Never assume Free/Flex/Dedicated tiers expose identical SLAs or restore mechanisms.

Drill workflow:

1. Confirm backup policy and tier support.
2. Select a valid snapshot or PITR timestamp within retention.
3. Choose an isolated target cluster and region.
4. Verify project, networking, IAM, and KMS setup.
5. Trigger restore via supported Atlas workflows.
6. Wait for cluster, data, and index readiness.
7. Verify `db.version()`, FCV, and driver compatibility where relevant.
8. Validate integrity, uniqueness, queries, Search, and CDC.
9. Measure actual RPO and RTO.
10. Archive redacted evidence and tear down the temporary target per policy.

### 30.1. KMS Is a Recovery Dependency

If an encrypted backup cannot be decrypted because a customer-managed key was revoked or permissions broke, the artifact is effectively unusable. Exercise restores using genuine recovery keys and permissions rather than a pre-authorized admin session that bypasses real IAM/KMS paths.

### 30.2. Restored Targets Often Have Different Connection Strings

Post-restore, update app configs, IP allowlists, and private endpoints. Verify full network connectivity and TLS hostname verification — never mask config bugs with `tlsInsecure=true`.

### 30.3. Search Index Readiness

When using Atlas Search or Vector Search, restored collection documents becoming readable does not mean Search indexes are synced and queryable yet. Factor index readiness into your service RTO whenever user workflows depend on Search.

## 31. Restoring Sharded Clusters: Harder Than Single Replica Sets

A sharded cluster consists of multiple coordinated sets:

```text
Application
     │
   mongos
     │
     ├── Config server replica set
     ├── Shard A replica set
     ├── Shard B replica set
     └── Shard C replica set
```

Taking independent per-shard snapshots at arbitrary times without supported cluster-wide coordination causes metadata and data skew.

### 31.1. Verification Points

- Config metadata restored consistently;
- Shard keys intact;
- Chunk ranges and metadata coherent;
- `mongos` routing healthy;
- Sharded collection identities preserved;
- Cross-shard reads and aggregations accurate;
- Distributed transactions succeed;
- Unique constraints enforced;
- Balancer / chunk migrations operate cleanly;
- Data consistency verified across shards;
- Backup/PITR point globally meaningful across the cluster.

### 31.2. "I Saw the Document on One Shard" Does Not Prove Cluster Health

Always query through `mongos` along the production app path. Confirm every shard and member is healthy and avoid manually editing config metadata.

### 31.3. Never Hand-Roll Naive Per-Shard Snapshot Scripts

Cluster-wide sharded backups demand precise consistency protocols. Use methods officially supported by MongoDB, Atlas, or qualified backup vendors for your topology and version, and test them with real restore drills.

## 32. Replica Sets: Verifying Data and Availability

On a replica set, post-migration/restore checks must verify:

- Primary and secondary roles;
- Healthy replica members;
- Minimal replication lag;
- Majority commit availability;
- Expected `writeConcern` behavior;
- Expected `readPreference` routing;
- Sufficient oplog window;
- Clean elections and failover;
- Backup agent connectivity.

Read-only inspection:

```javascript
rs.status();
```

Run only against authorized deployments with appropriate privileges.

### 32.1. When Read-After-Write Differs

Apps reading from secondaries can observe stale state due to replication lag immediately after primary writes. Reconciliation suites querying secondaries must declare read preference, read concern, and baseline watermarks explicitly.

### 32.2. Never Test Recovery by Restarting a Live Production Replica Set

Chaos and failover drills belong in staging or strictly approved windows with clear abort conditions and on-call coverage. Testing high availability must never trigger a real outage.

## 33. Point-in-Time Recovery (PITR) Testing

A proper PITR drill must prove recovery to a **precise timestamp before a destructive error**, not just restoring an arbitrary daily snapshot.

Scenario:

```text
09:00  Snapshot base
09:10  Order A committed
09:20  Order B committed
09:30  Accidental delete of order collection
09:40  Incident detected
09:50  Desired recovery point = 09:29
```

Expected state:

- Order A exists;
- Order B exists;
- The 09:30 deletion is absent;
- Writes after 09:29 are excluded;
- In-flight transactions obey the recovery method's commit semantics.

### 33.1. Pick Achievable PITR Targets

Not every arbitrary second is recoverable: the target must sit inside continuous backup/oplog retention with intact coverage and supported tooling.

### 33.2. Clocks and Commit Points

Verify the recovered timestamp from MongoDB/backup tool metadata rather than trusting a client clock alone. Clock skew, transaction commit times, and timezones all affect boundaries.

### 33.3. Boundary Tests

Test records and transactions spanning:

- Committed cleanly before boundary;
- Committed right on the boundary;
- Committed after boundary;
- Transaction started before yet committed after;
- Deletes before vs. after;
- TTL / background sweeps.

Define expected results precisely according to your PITR tool's semantics.

## 34. Failure Injection Testing: Finding Bugs Before Production

A migration that cruises smoothly under ideal conditions often breaks under packet drops or worker crashes.

Exercise in staging:

| Simulated Failure | What It Must Prove |
|---|---|
| Kill/restart migration worker | Resumes cleanly without dropping records |
| Temporary MongoDB disconnect | Bounded retries and clean reconnect |
| Primary stepdown / failover | Driver recovers without duplicate writes |
| Cursor timeout | Safe checkpoint / keyset resume |
| CDC consumer crash | Safe token checkpoint and idempotent replay |
| Concurrent source writes during copy | Final reconciliation converges |
| Target disk near full | Halts safely without marking COMPLETE |
| Duplicate unique key | Rejected records captured cleanly |
| KMS/key permission revoked | Fails cleanly without bypassing security |
| Restored target missing an index | Post-condition gate fails cleanly |
| Search index still rebuilding | Readiness gate blocks premature traffic |
| Corrupted backup artifact | Integrity check catches corruption |
| Crash after target write before checkpoint | Replay produces zero duplicate side effects |

### 34.1. Never Retry Infinitely

Structure retry policies clearly:

```text
Transient errors -> bounded exponential backoff + jitter
Permanent data errors -> dead-letter queue / remediation
Authentication errors -> halt / security review
Disk full -> halt / capacity recovery
Unknown write outcome -> reconciliation / idempotency check
```

### 34.2. Never Assume a Network Timeout Means "Not Written"

The server may have committed the write before the ACK got lost in transit. Retrying `$inc` blindly as a fresh write double-counts balances or counters. Use idempotency keys, version guards, and state verification.

## 35. Designing Idempotent Migrations

An idempotent operation can replay the same input repeatedly without unintended side effects.

Example upsert keyed on business identity:

```javascript
db.order_exports.updateOne(
  {
    _id: {
      tenantId: "T-01",
      orderNo: "A-0001"
    }
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong("249900")
    }
  },
  { upsert: true }
);
```

For fixed inputs, `$set` upserts converge to the exact same state.

### 35.1. `$inc` Is Not Inherently Idempotent

```javascript
db.totals.updateOne(
  { _id: "T-01" },
  { $inc: { amountCents: 249900 } }
);
```

Replaying twice adds the value twice. When computing totals, `$set` precomputed watermarked totals or pair mutations with event-ID deduplication.

### 35.2. Upserts Still Need Supporting Unique Indexes

Two concurrent workers upserting against a filter without a unique index can both insert duplicate documents. Enforce unique business keys and verify concurrent upserts under test.

### 35.3. Never Overwrite Newer Versions with Stale Writes

If a batch backfill reads revision 7 while CDC has already committed revision 8, the backfill worker must never clobber revision 8. Enforce atomic compare-and-set version guards or strict ordering, and test the race explicitly.

## 36. Testing Schema Transformations

Example conversion from:

```javascript
{
  _id: "ORDER-1",
  total: 249900,
  customerEmail: "alice@example.com"
}
```

to:

```javascript
{
  _id: "ORDER-1",
  amount: {
    value: NumberDecimal("2499.00"),
    currency: "VND"
  },
  customer: {
    emailNormalized: "alice@example.com"
  }
}
```

Converting an integer `total=249900` into `"2499.00"` depends strictly on **currency minor units** and rounding policy (for example, VND typically has zero decimal places, unlike USD cents). Define currency rules explicitly; this snippet illustrates structural mapping only.

### 36.1. Golden Transformation Test Table

| Input | Expected Output |
|---|---|
| Missing `customerEmail` | Absent or `null` strictly per contract |
| Mixed-case / Unicode email | Normalized per policy |
| Zero amount | Exact zero with target BSON type |
| Large amount | Zero overflow or precision loss |
| Nested objects | Zero dropped fields |
| Unknown enum value | Rejected or retained per policy |
| Soft-deleted record | Preserved or archived per rule |
| Invalid date | Explicit error / dead-letter record |

### 36.2. Never Silently Rewrite Bad Data Without Reporting

Log and expose exact counts of adjusted or rejected records. Even when policy drops malformed rows, verify exact rejection counts, owners, and audit evidence rather than swallowing BSON parse failures and marking the job `COMPLETED`.

### 36.3. Expand-and-Contract

When old and new application versions coexist:

```text
Expand schema
    ↓
Deploy app reading both formats
    ↓
Backfill / migrate data
    ↓
Verify correctness
    ↓
Switch reads/writes
    ↓
Contract / drop legacy fields later
```

This dramatically lowers rollback risk, though dual-read/dual-write windows still require thorough race testing.

## 37. Testing Index Performance Post-Migration/Restore

Indexes may exist yet produce shifted query plans.

Query:

```javascript
db.orders.find({
  tenantId: "T-01",
  status: "PAID"
})
.sort({ createdAt: -1 })
.limit(20)
.explain("executionStats");
```

Inspect:

- `winningPlan`;
- `IXSCAN`/`COLLSCAN` or equivalent stages;
- `totalKeysExamined`;
- `totalDocsExamined`;
- `nReturned`;
- Blocking sort stages;
- Execution time;
- Shard targeting.

### 37.1. Different Engines/Versions Reshape Plan Trees

Do not enforce identical internal stage names across MongoDB major versions. Focus on query correctness, scan budgets, and SLO compliance.

### 37.2. Warm vs. Cold Cache

Freshly restored clusters start with cold WiredTiger caches, making initial reads slower. Test:

- Cold-start latency;
- Warm-cache steady state;
- Mixed read/write traffic;
- Peak concurrency;
- Background index builds;
- Replication catch-up;
- Search index readiness.

### 37.3. Do Not Track Only Mean Latency

p95/p99 tail latency can spike dramatically even while averages stay flat. A restored service whose API responds yet breaches p99 SLOs has not fully recovered.

## 38. Application Smoke Flows Post-Restore

Minimum smoke suite:

1. App connects with real target URI, TLS, and service auth;
2. Meaningful health/readiness check passes;
3. Real persisted records read back cleanly;
4. Authorized write succeeds on permitted collection;
5. Unique constraints and tenant scoping hold;
6. Representative aggregations/reports run cleanly;
7. Multi-document transactions commit/abort properly;
8. Pagination and sorting behave accurately;
9. Search / Vector Search queries return results if enabled;
10. Background consumers / CDC resume cleanly;
11. Target backup agent runs properly;
12. End-to-end critical business flow succeeds.

Domain flow example:

```text
Create order
    ↓
Reserve inventory
    ↓
Confirm payment
    ↓
Update order status
    ↓
Read customer history
    ↓
Generate invoice
```

Never trigger real financial charges or customer emails during restore drills. Use sandbox gateways and test identities.

## 39. Testing Related Systems Outside MongoDB

Applications rarely consist of MongoDB alone:

```text
MongoDB
  ├── Search index
  ├── Redis cache
  ├── Kafka topics
  ├── Object storage / GridFS
  ├── Data warehouse
  ├── Notification service
  ├── Payment provider
  └── Analytics dashboards
```

Restoring MongoDB to an earlier timestamp while Kafka offsets or warehouses remain ahead creates cross-system inconsistency.

### 39.1. External Consistency Plan

Explicitly plan:

- Cache invalidation or rebuilds;
- Search index rebuilds or catch-up;
- CDC reset or reseed procedures;
- Warehouse reconciliation;
- Compensating actions for external side effects;
- Job scheduler watermarks;
- Payment provider reconciliation;
- Verification that referenced external blobs/files exist.

### 39.2. Partial Collection Restores Can Break Referential Parity

Restoring only `orders` to yesterday while leaving `payments` at today produces orphaned or mismatched order/payment states. Define your **recovery consistency domain** around coupled business transactions.

## 40. GridFS, Binary Files, and Multi-Chunk Storage

When storing large files in GridFS, validate both metadata and chunk collections per bucket naming conventions.

Never verify `fs.files` counts while forgetting `fs.chunks`.

Verify:

- File counts;
- Complete chunk sequences;
- File checksums/hashes matching app expectations;
- End-to-end streaming of both small and large files;
- MIME types and custom metadata;
- File access controls;
- Absence of orphaned chunks;
- Delete behavior.

Ensure backup and migration filters include GridFS namespaces rather than copying only business document collections.

## 41. Time-Series / Capped Collections and Special Limits

When migrating or restoring time-series or capped collections, verify:

- Exact collection options;
- `timeField` and `metaField` definitions;
- TTL and retention rules;
- Underlying bucket storage;
- Version-specific index support;
- Compression and storage footprint;
- Query semantics;
- Ingestion ordering and timestamps;
- Capped rollover/truncation behavior.

Never accidentally convert a time-series collection into a standard collection and treat it as equivalent if workloads depend on time-series semantics.

### 41.1. Expired Data in Restored Time-Series Collections

If restoring historical logs into an active TTL policy drops old buckets, factor approved retention into expected counts — never accidentally let TTL purge forensic evidence during an investigation drill.

## 42. Data Privacy and Securing Backup Artifacts

Backup and restore testing routinely touches full customer datasets.

Mandatory controls:

- Encryption at rest;
- Encryption in transit;
- Strict KMS / key custody;
- Access logging;
- Least privilege;
- Network isolation;
- Approved data masking whenever operating outside production;
- Defined retention and deletion of temporary restore targets;
- No shared un-audited admin accounts;
- Zero secrets in scripts or CI logs;
- Zero raw PII pasted into tickets;
- Public bucket access explicitly blocked;
- Incident protocol if tests uncover data exposure.

### 42.1. Testing Key Recoverability

An encrypted backup whose recovery environment lacks KMS decryption rights cannot restore. DR drills must exercise **genuine key permissions and access paths**, not just file bytes.

### 42.2. Restore Tests Write Sensitive Data to a New System

Even without touching the source cluster, restoring creates live records in the target environment. Secure formal approvals and enforce strict post-drill teardown.

## 43. Tracking Migration Metrics

Operational dashboard metrics:

| Metric | Meaning |
|---|---|
| Source documents eligible | Total source scope per contract |
| Documents copied | Records read/transferred |
| Documents acknowledged | Writes confirmed by target |
| Failed/rejected records | Records needing remediation |
| CDC lag | Target delay behind live source |
| Last applied resume token | Change-stream checkpoint |
| Throughput (docs/s) | Migration transfer rate |
| Network bytes/s | Bandwidth utilization |
| Read/write p95/p99 | Latency impact |
| Connection pool wait | Driver pooling bottleneck |
| CPU, disk IOPS/latency | Hardware saturation |
| Replication lag | Impact on replica set secondaries |
| Index build progress | Target index readiness |
| Reconciliation mismatches | Data parity discrepancies |
| RPO estimate | Potential data loss window |
| Restore elapsed time | Progress against RTO |
| Search indexing lag | Search index readiness |

### 43.1. Distinguish Copied from Committed

Reading 1,000,000 documents while receiving target write ACKs for only 980,000 must never report 100% completion.

### 43.2. Counters Are Cumulative

Calculate throughput from deltas:

\[
\text{documents/s} = \frac{\Delta \text{acknowledged documents}}{\Delta t}
\]

Handle counter resets on worker restarts and tag metrics per job, worker, and collection.

### 43.3. Monitor Both Source and Target

Driving 90% disk utilization on the source cluster degrades production APIs even when the target looks calm. Monitor CPU, cache, disk, and network across **both clusters** and codify throttling limits in runbooks.

## 44. Measuring Recovery Speed Structurally

Realistic incident timeline:

```text
14:00 Incident declared
14:05 Recovery decision approved
14:10 Restore target provisioned
14:15 Restore initiated
14:38 Data copy completed
14:45 Indexes verified
14:50 Security/network ready
14:57 App smoke tests passed
15:05 Critical business operations restored
```

When RTO is defined from incident declaration until critical business operations resume, measured RTO is **65 minutes**, **not the 23 minutes** spent copying bytes.

### 44.1. Define Exact Start and End Markers

Depending on your DR SLA, timers may start at incident detection, declaration, or recovery activation — publish definitions upfront and apply them consistently across drills.

### 44.2. Data Size Heavily Drives Restore Duration

Restoring 10 GiB proves very little about meeting RTO on 10 TiB. Test representative data scales or validate projections using full-scale drills.

### 44.3. DR Drills Must Include Realistic Friction

Switching URIs onto a pre-warmed, pre-restored standby cluster does not test the real-world time required to **provision infrastructure, pull backups, decrypt, restore, build indexes, and validate**.

## 45. Safe Automation Scripts and Safeguards

Good candidates for automation:

- Source/target inventories;
- Read-only catalog diffs;
- Partition counts and aggregations;
- Canonical hash reports;
- Backup artifact checksum checks;
- Staging restore orchestration;
- Smoke tests;
- Telemetry collection;
- Evidence bundling;
- Alert gating.

Destructive actions such as:

```text
dropDatabase
drop collection
mongorestore --drop
shard metadata changes
setFeatureCompatibilityVersion
rs.stepDown
```

require explicit approvals, strict guardrails, and isolated environments.

### 45.1. Separate `DRY_RUN` and `APPLY`

```text
DRY_RUN:
  read configuration
  inspect source and target
  generate plan and risk report
  perform no mutations

APPLY:
  validate approved change ID
  confirm target identity
  execute procedure
  collect evidence
  validate postconditions
```

### 45.2. Never Equate "Script Exit Code 0" with Valid Data

Scripts must evaluate postconditions and exit non-zero if reconciliation or business checks fail. Distinguish:

- Command execution success;
- Byte transfer completion;
- Data completeness;
- Data correctness;
- Application readiness.

## 46. Example Data Audit Table for `orders`

| Check | Source at Watermark W | Target at Watermark W | Result |
|---|---|---|---|
| Total eligible orders | 5,000,000 | 5,000,000 | PASS |
| Tenant T-01 orders | 1,200,000 | 1,200,000 | PASS |
| PAID orders | 3,600,000 | 3,599,999 | FAIL |
| PAID total amount | 900,000,000,000 | 899,999,750,100 | FAIL |
| Duplicate `(tenantId, orderNo)` | 0 | 0 | PASS |
| Null/missing `currency` | 21 | 25 | FAIL |
| Unique index | Present | Present | PASS |
| App read smoke | Passed | Passed | PASS |
| App write smoke | Passed | Passed | PASS |

**Numbers are illustrative.** Never declare a migration PASS just because total counts match while partition counts, monetary sums, or null distributions diverge.

### 46.1. Triaging Mismatches

Record every discrepancy cleanly:

```text
Mismatch ID
Namespace + partition
Expected vs actual
Impact
Suspected cause
Owner
Remediation plan
Re-test result
Approval
```

### 46.2. Never Silently Patch Target Records Without Traceability

Ad-hoc edits to force counts to line up without lineage create hidden bugs. Any repair must be idempotent, audited, and consistent with the source/target contract.

## 47. Writing a Recovery Runbook

Compact template:

```text
CHANGE / DRILL ID:
DATE:
BUSINESS OWNER:
DBA OWNER:
SRE ON-CALL:

SOURCE:
  Cluster / topology:
  MongoDB version / FCV:
  Namespace scope:
  Write status:
  Backup source:

TARGET:
  Isolated cluster:
  Version / FCV:
  Region:
  Storage / capacity:
  Security configuration:

RECOVERY:
  Backup artifact ID:
  Snapshot timestamp:
  PITR target:
  Expected RPO:
  Expected RTO:
  KMS/access prerequisites:

EXECUTION:
  Preconditions:
  Exact approved procedure:
  Stop conditions:
  Rollback actions:
  Communication:

VALIDATION:
  Data counts:
  Partition reconciliation:
  BSON type checks:
  Business invariants:
  Indexes / validators:
  Auth / tenant isolation:
  App smoke:
  Search / CDC:
  p95/p99:
  Actual RPO/RTO:

DECISION:
  GO / HOLD / NO-GO / RECOVER

EVIDENCE:
  Logs (redacted):
  Metric snapshots:
  Reconciliation report:
  Approvals:
```

### 47.1. Runbooks Need Clear Ownership

A static README is useless if nobody knows who has authority to shift traffic, fence source writers, or unlock KMS keys during an incident.

### 47.2. Never Store Passwords in Runbooks

Reference secret managers, IAM/workload identities, and strict access controls. Treat backup bucket names and private network details as sensitive metadata too.

## 48. GO / NO-GO Gates

| Gate | GO When | NO-GO When |
|---|---|---|
| Backup artifact | Exists and integrity verified | Missing or corrupted |
| Restore drill | Completed cleanly | Skipped or failed |
| RPO | Recovery point within target | Loss window exceeds budget |
| RTO | Service restored on time | Exceeds recovery time budget |
| Data completeness | Key sets match cleanly | Unexplained missing/extra records |
| Data correctness | Types and invariants hold | Mismatched totals, states, or links |
| Index/metadata | Matches target manifest | Missing unique/TTL/validators |
| CDC | Lag caught up to watermark | Unresolved delta gap |
| Cutover | Single authoritative writer | Split-brain active writes |
| Driver/app | Critical workflows pass | API or mapping errors |
| Security | TLS/auth/KMS/ACLs pass | Leaks or bypassed checks |
| Search/analytics | Meets feature SLO | Indexes unready with no fallback |
| Performance | p95/p99 within guardrails | Severe latency/scan regression |
| Rollback | Tested path with clear steps | No control over post-cutover writes |
| Ownership | Approver & on-call assigned | No clear decision owner |

An `UNKNOWN` row on any critical item must never be treated as `PASS`.

## 49. Post-Cutover / Post-Restore Stabilization Window

Even when every cutover test passes, closely monitor:

- Residual writes hitting the legacy source;
- Target CDC lag and checkpoints;
- Query p95/p99 latency;
- Error rates and retries;
- Replication health;
- Disk, cache, and CPU usage;
- Target backup and PITR jobs;
- TTL sweep behavior;
- Search/Vector index synchronization;
- Batch, BI, and ETL pipelines;
- Business financial totals;
- User bug reports;
- Network and authentication alerts.

### 49.1. Observe Across Multiple Business Cycles

Nightly batch jobs surface issues 24 hours later; month-end billing surfaces issues once a month. Size stabilization windows to match real business cycles, not just 10 minutes post-deploy.

### 49.2. When Can the Legacy Source Be Decommissioned?

Only after:

- The rollback window has closed;
- The target is proven authoritative;
- All migrations and backfills are complete;
- All consumers no longer touch the legacy source;
- Target backups and restore drills have succeeded;
- Retention and legal holds are satisfied;
- Formal sign-offs are recorded.

Never drop the legacy source cluster minutes after an initial smoke test passes.

## 50. Anti-Patterns to Avoid

| Mistake | Why It Is Dangerous | Fix |
|---|---|---|
| Comparing only total counts | Equal missing and extra counts cancel out | Partition and key-set reconciliation |
| Comparing two different points in time | False discrepancies | Fixed snapshot or watermark |
| Exporting BSON through plain JSON | Drops `Decimal128`, `Long`, `Date` precision | BSON or Extended JSON fidelity |
| Spot-checking 100 docs and passing | Leaves millions unverified | Representative or full reconciliation |
| Using `estimatedDocumentCount` as proof | Metadata approximations aren't exact | Exact scoped counts and partitions |
| Backup SUCCESS = recovery PASS | Never tested real restore | Run real restore drills |
| Replica set = backup | Deletes and bad writes replicate too | Independent backups / PITR |
| Snapshotting shards at random times | Cross-shard metadata skew | Supported cluster-consistent backup |
| Omitting KMS keys from DR tests | Backups fail to decrypt under incident | Test full KMS access paths |
| Running app smoke tests as root | Masks RBAC failures | Use real service identities |
| Skipping negative authorization tests | Risks cross-tenant exposure | Run explicit ACL deny tests |
| Ignoring TTL during restores | Records vanish post-import | Pre-check TTL candidates |
| Legacy writers active post-cutover | Split-brain data corruption | Enforce write fences and alerts |
| Copying snapshot only without CDC | Loses writes made during copy | Snapshot + CDC + catch-up |
| Checkpointing before target ACK | Skips events on worker crash | Commit-then-checkpoint |
| Blindly retrying `$inc` | Duplicate balance increments | Idempotency keys and dedup |
| Ignoring deletes | Stale ghost records on target | Propagate tombstones/CDC deletes |
| Ignoring Search/Vector indexes | Empty search responses post-cutover | Check readiness and lag gates |
| Skipping GridFS chunk collections | Corrupted or unreadable files | Validate files, chunks, and hashes |
| Restoring orders without payments | Broken cross-collection invariants | Define coupled recovery domain |
| Measuring only raw data copy time | Underestimates true RTO | Time incident-to-service restoration |
| Tiny staging dataset | Unrealistic RTO and plans | Size representative drill data |
| No rollback plan | Trapped after cutover | Define write ownership and replay |
| Claiming rollback = swapping URI | Drops target-only writes | Plan reconciliation / reverse sync |
| Skipping index options diff | Silently drops unique/TTL constraints | Diff full catalog definitions |
| Skipping backups after server upgrade | Incompatible backup agents | Re-run post-upgrade restore drill |
| Pasting raw PII in audit reports | Privacy breach | Redact logs and secure reports |
| Missing stop criteria | Pushes ahead despite data loss | Enforce clear GO/NO-GO gates |

## 51. Practice Exercises

### Exercise 1 — Defining a Migration Contract

`orders` migrates from Cluster A to Cluster B.

1. Define document identity.
2. Select a migration watermark.
3. List mandatory preserved fields.
4. Specify allowed transformations.
5. Assign business invariants and owners.

### Exercise 2 — Counts Alone Are Never Enough

Source has 1,000,000 documents; target also has 1,000,000.

1. Can you mark the migration PASS?
2. Design grouped counts by tenant, status, and date.
3. Detect duplicate business keys.
4. Compare monetary totals.
5. How would you locate missing/extra keys across huge datasets?

### Exercise 3 — BSON `Long` Overflow

A fixture carries `NumberLong("9007199254740993")`.

1. What goes wrong if exported as a plain JSON/JavaScript `Number`?
2. How does Extended JSON/BSON preserve it?
3. What type-fidelity check catches this?
4. Why is comparing raw JSON strings unreliable?
5. When should `Decimal128` be used instead?

### Exercise 4 — `null` vs. Missing Fields

Source:

```javascript
{ _id: 1, x: null }
{ _id: 2 }
```

Target stores both documents with `x: null`.

1. Do document counts match?
2. Is the data structurally accurate?
3. How do you test field presence vs. `null`?
4. How are partial indexes affected?

### Exercise 5 — Unique, Partial, and TTL Indexes

A collection has a unique index for active users and a TTL index for sessions.

1. Write a tenant-scoped uniqueness test.
2. Test soft-deleted records.
3. Inspect expired TTL candidates before running a restore.
4. Why isn't post-restore TTL cleanup a backup bug?
5. When does it reveal a retention policy mismatch?

### Exercise 6 — `mongodump` Restore

In staging:

1. Seed a test collection;
2. Dump using a consistent scope;
3. Restore to an empty isolated target;
4. Diff documents and indexes;
5. Run app read/write smoke tests;
6. Record measured RTO and evidence.

### Exercise 7 — RPO/RTO

An app has `RPO = 5 minutes`, `RTO = 45 minutes`.

```text
14:00 incident
14:12 recovery triggered
14:50 database restored
15:00 app healthy
last recovered commit = 13:57
```

1. What is the actual loss window?
2. What is the RTO measured from incident declaration?
3. Did it meet both SLOs?
4. Why is measuring only database copy time misleading?

### Exercise 8 — PITR Boundaries

Choose a recovery point right before an accidental delete.

1. Seed marker writes before and after.
2. Specify expected restored documents.
3. How are transactions committing after the boundary handled?
4. What oplog coverage is needed?
5. What evidence proves the true recovered commit point?

### Exercise 9 — Replica Sets and Sharding

1. Why doesn't a replica set replace backups?
2. How must config metadata align in sharded cluster restores?
3. Can you snapshot shards independently at random moments?
4. Which cross-shard transaction cases need validation?
5. How does `readPreference` affect reconciliation?

### Exercise 10 — CDC Crash

A consumer applies event `E1` to the target and crashes before saving its checkpoint.

1. Will `E1` reappear on restart?
2. How do you deduplicate or make writes idempotent?
3. Why shouldn't you checkpoint before applying?
4. How does the oplog window constrain downtime?
5. What happens if the resume token expires?

### Exercise 11 — Concurrent Source Writes During Copy

Initial copy runs from `T0` to `T1`, with cutover at `T2`.

1. Which writes risk getting missed?
2. Where must CDC begin reading?
3. How do you define the final watermark?
4. How do you verify zero remaining consumer lag?
5. When is it safe to fence source writes?

### Exercise 12 — Post-Cutover Rollback

The target accepts 20,000 new writes over 30 minutes.

1. Can you simply revert the URI back to the source?
2. How must those 20,000 new writes be handled?
3. Outline a reverse replay workflow.
4. How do you enforce single write ownership?
5. Can old app binaries read a newer target schema?

### Exercise 13 — Search Indexes

All documents restored cleanly, yet `$search` queries return incomplete results.

1. Was collection data lost?
2. Which Search index statuses/lag metrics should you check?
3. How do you trigger or await catch-up/rebuilds?
4. When should the API declare readiness?
5. How should Search authorization still be verified?

### Exercise 14 — Security Restore Drill

1. Verify encrypted backup decryption and KMS access.
2. Run app smoke tests as the real service account instead of root.
3. Verify tenant isolation.
4. Verify private endpoints and TLS validation.
5. Enforce restore-target teardown policies.

### Exercise 15 — Reconciliation Hashing

Design canonical partition hashing per tenant and time bucket.

1. Choose fields.
2. Preserve BSON types.
3. Distinguish `null` from missing fields.
4. Decide array ordering semantics.
5. How do you drill down when a partition hash differs?

### Exercise 16 — Performance Regression

Post-migration metrics:

```text
Read p95: 80 ms -> 420 ms
Write p95: 120 ms -> 115 ms
Total docs: equal
```

1. Should you declare GO?
2. Inspect index catalogs and `explain`.
3. Check cold caches and changed plans.
4. Inspect p99, API error rates, and CPU/disk saturation.
5. Choose between index remediation and rollback.

### Exercise 17 — Failure Injection

Simulate in staging:

- Worker killed at 60% progress;
- DB connection drop;
- Cursor timeout;
- Duplicate key collision;
- Partial bulk failure;
- Simulated full disk on an isolated target;
- Corrupted backup artifact.

For each case, document expected recovery, idempotency, and pass/fail criteria.

### Exercise 18 — DR Runbook Decision

Status summary:

```text
Backup artifact exists: YES
Restore drill: NOT DONE
RPO proof: UNKNOWN
Index catalog: PASS
Business invariant: FAIL
Rollback: UNKNOWN
On-call owner: READY
```

1. GO or NO-GO?
2. List the exact blockers.
3. Design the missing restore drill.
4. Who must sign off?
5. What evidence must be archived before cutover?

## 52. Migration Testing Checklist

### Before Migration

- [ ] Source, target, and topologies documented.
- [ ] Business owner, DBA/SRE, and on-call assigned.
- [ ] Snapshot/watermark point defined.
- [ ] RPO/RTO and downtime budget agreed.
- [ ] Collections, indexes, validators, views, and users/roles inventoried.
- [ ] BSON types and edge-case fixtures tested.
- [ ] Representative staging dataset prepared.
- [ ] Verified backup and recovery plan in place.
- [ ] Strategy defined for writes arriving during copying.
- [ ] Security and tenant isolation tests ready.
- [ ] Resource headroom and throttling limits defined.
- [ ] Explicit stop and rollback gates established.

### During Migration

- [ ] Track documents copied, acknowledged, and failed.
- [ ] Persist resume tokens/checkpoints safely.
- [ ] Enforce bounded, idempotent retries.
- [ ] Monitor CDC lag and oplog window margin.
- [ ] Prevent unplanned dual primary writers.
- [ ] Record clear error and rejection details.
- [ ] Watch latency, CPU, disk, and replication across both clusters.
- [ ] Keep PII and credentials out of logs.

### After Migration

- [ ] Counts and key sets verified at watermark.
- [ ] Partition hashes and business totals match.
- [ ] BSON types and nested structures intact.
- [ ] Unique, TTL, and partial indexes verified.
- [ ] Validators, views, and sharding metadata intact.
- [ ] App smoke, transactions, CDC, and Search pass.
- [ ] p95/p99 and error rates within guardrails.
- [ ] Target backups work and restore drill passes.
- [ ] Legacy source shows zero unexpected writes.
- [ ] Stabilization and rollback window actively managed.

## 53. Restore / DR Testing Checklist

- [ ] Backup artifact ID, timestamp, and scope recorded.
- [ ] Artifact integrity and encryption verified.
- [ ] KMS keys and access paths validated.
- [ ] PITR target falls within retention window.
- [ ] RPO/RTO defined upfront.
- [ ] Isolated target provisioned with sufficient capacity.
- [ ] DB Tools and server versions compatible.
- [ ] Procedure matches replica-set or sharded topology.
- [ ] Safeguards prevent `--drop` on wrong environments.
- [ ] Collections, indexes, and metadata restored per scope.
- [ ] Counts and business invariants pass.
- [ ] TTL expiration behavior evaluated.
- [ ] Service auth, RBAC, and TLS verified.
- [ ] Search, Vector Search, CDC, and GridFS verified if used.
- [ ] Critical app workflows pass.
- [ ] True recovery point verified.
- [ ] True end-to-end RTO measured.
- [ ] Post-drill report and remediation items logged.
- [ ] Temporary restore target and PII cleaned up per policy.

## 54. Official References

Always cross-check against your exact **MongoDB Server version, Database Tools version, Atlas tier, and deployment topology**:

- [MongoDB Back Up and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB `mongodump`](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB `mongorestore`](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Atlas Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/overview/)
- [MongoDB Atlas Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Replica Set Backups](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/)
- [MongoDB Sharded Cluster Backup and Restore](https://www.mongodb.com/docs/manual/core/backups/#backup-and-restore-sharded-clusters)
- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitoring-alerts/)
- [MongoDB Search](https://www.mongodb.com/docs/search/)
- [MongoDB Vector Search](https://www.mongodb.com/docs/vector-search/)

## Conclusion

Testing MongoDB data migrations and backup restores must serve as **end-to-end proof of system correctness and recoverability**, never merely checking whether a CLI command returned exit code 0.

For **data migrations**, anchor comparisons to a concrete snapshot or watermark, then reconcile key sets, partitions, BSON types, business invariants, uniqueness, index metadata, and coupled dependencies. When the source accepts writes during copying, pair snapshots with **CDC catch-up, idempotency, durable checkpoints, and a strict write fence** at cutover; copying a snapshot and swapping a connection string alone cannot guarantee zero data loss.

For **backup restores**, conduct **genuine restore drills** in isolated environments — validating artifacts and KMS keys, data, indexes, users/roles, Search/Vector/CDC integrations, application flows, and **RPO/RTO measured to the true commit point and full service restoration**. Account upfront for risks like post-restore TTL deletions, omitted cluster security metadata, unsynchronized sharded snapshots, and schema incompatibilities with rollback codebases.

Ultimately, **GO/NO-GO decisions must rest on verifiable test evidence**. Whenever critical data mismatches persist, no restore drill has run, or rollback ownership remains unclear, you do not yet have enough evidence to cut over production traffic.

**A successful migration means accurate data and a healthy application. A successful backup means proven, complete, and timely recovery — even when failure strikes at the worst possible moment.**
