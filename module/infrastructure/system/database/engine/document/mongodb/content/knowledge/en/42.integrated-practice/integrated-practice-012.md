# Backup, Restore, Access Verification, and Operational Checklists in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Integrated Practice  
> **Lesson:** Backup, Restore, Access Verification, and Operational Checklists

## 1. Scenario: Sales Data Must Be Recoverable and Accessible Only to Authorized Actors

Suppose you operate a sales application backed by database `sales_lab` or `sales_prod` containing collections `customers`, `products`, `inventory`, `orders`, `payments`, and `outbox`. One morning, an operations engineer accidentally runs an erroneous update across thousands of orders. You discover last night's backup file exists, yet nobody has ever tested restoring it. Meanwhile, the application account has been granted `root` "for convenience".

Four questions must be answered before calling the system operationally safe:

1. **Is the backup actually usable?** A file existing with a valid checksum is not enough; you must test restoring it and verify documents, indexes, schemas, point-in-time boundaries, and the application.
2. **How far back can we recover?** Is the backup a snapshot from 00:00, or can you restore to 09:57 right before the erroneous write? This is a matter of RPO and point-in-time recovery.
3. **Who is allowed to do what?** Does the application account need privileges to manage users, drop databases, or run restores? Does a report reader need to modify orders?
4. **How do we keep operations repeatable?** Are there backup schedules, restore drills, storage/oplog monitoring, alert handling, and change logs?

This lesson covers a hands-on workflow from logical backups to isolated restores, RBAC, privilege verification, and recurring operational checklists. Examples run against local MongoDB, while production guidance is marked separately because backup and restore actions directly affect data safety.

### 1.1. Learning Objectives

After this lesson, you will be able to:

- Distinguish logical dumps, storage snapshots, continuous backups, and disaster recovery.
- Explain RPO, RTO, retention, restore points, and consistency.
- Use `mongodump`/`mongorestore` with `--archive` and `--gzip`.
- Recognize the limitations of a database-only dump while writes continue.
- Use `--oplog`/`--oplogReplay` properly on a **full replica set dump**, without miscombining them with `--db` or namespace remapping.
- Restore a database into a **different namespace** to avoid overwriting source data.
- Verify checksums, document counts, indexes, BSON types, and business invariants.
- Verify authentication and authorization with `connectionStatus`, `getUser()`, and negative privilege tests.
- Design least-privilege roles for applications, reporting, backups, and restores.
- Establish daily/weekly/monthly, pre/post-deploy, backup incident, and restore drill checklists.
- Record auditable recovery evidence.

### 1.2. Safety Rules for This Lesson

- **Never run `mongorestore --drop` on production or any active database.**
- **Never use a `root` account as an API's regular connection identity.**
- **Never commit URIs containing passwords to Git, shell history, or logs.**
- **Never use production backups containing PII as ad hoc fixtures on laptops or in CI.**
- **Never assume a successful backup file guarantees restore works.**
- **Never launch production replica set security by copying an unauthenticated, non-TLS lab configuration.**
- Practice restores into a **separate** namespace or deployment without touching the source.
- Sample data here is purely synthetic and contains no real card numbers, bank accounts, or customer PII.

---

## 2. End-to-End Data Protection Architecture

```text
               API / Workers
                 │      │
            App DB user  Report DB user
                 │      │
                 ▼      ▼
        ┌───────────────────────┐
        │ MongoDB deployment    │
        │ orders / payments /   │
        │ inventory / outbox    │
        └──────────┬────────────┘
                   │
             Backup process
                   │
            (service identity)
                   │
          ┌────────▼─────────┐
          │ Backup artifact  │
          │ + metadata       │
          │ + checksum       │
          └────────┬─────────┘
                   │
         Encrypted immutable/offsite copy
                   │
               Restore drill
                   │
          ┌────────▼─────────┐
          │ Isolated restore │
          │ + verification   │
          └────────┬─────────┘
                   │
       Counts / indexes / BSON / invariants
                   │
                   ▼
         Recovery acceptance record
```

A trustworthy system governs the **write path**, **backup creation path**, **backup read permissions**, **restore path**, and **verifiable proof that data recovered cleanly**.

---

## 3. Core Terminology

| Term | Meaning |
|---|---|
| Backup | A copy usable to recover data after an incident |
| Restore | Loading data from a backup into a target system |
| Recovery | Restoring full service operation: data, permissions, connections, apps, and downstream dependencies |
| RPO | Recovery Point Objective: maximum acceptable data loss measured in time |
| RTO | Recovery Time Objective: maximum target time allowed to restore service |
| Retention | How long backups and snapshots are retained |
| PITR | Point-in-Time Recovery: recovering to a supported timestamp inside a recovery window |
| Consistent backup | A copy representing a consistent state at a point in time with well-defined semantics |
| Restore drill | Periodic test restore into an isolated environment to validate recoverability |
| Principle of least privilege | Granting each actor only the minimum permissions actually required |
| Backup integrity | Verifying an artifact is uncorrupted and untampered, e.g., via hashes and encryption/signatures |
| Application-level consistency | Invariants across orders, payments, inventory, and outbox hold true after restore |

### 3.1. RPO Differs from RTO

Example:

```text
RPO = 15 minutes
RTO = 2 hours
```

When an incident hits at 10:00:

- The target is to recover state **no older than roughly 09:45**, matching the approved RPO.
- Service must resume by roughly 12:00, matching the approved RTO.

However, if you only back up once nightly at 00:00, you **cannot promise a 15-minute RPO** without continuous backup or compatible transaction-history capture/replay.

### 3.2. Backup Frequency Must Match RPO

| Policy | Potential Data Loss |
|---|---|
| One snapshot per day | Could lose nearly a full day's writes since the last snapshot |
| Hourly snapshot | Could lose up to nearly an hour, depending on timing and semantics |
| Snapshot + continuous oplog archiving/PITR | Can recover within the recovery window subject to solution granularity and limits |
| No backup, replica set only | Zero recovery history against intentional deletes or bad updates |

A replica set **does not replace backups**: a valid `deleteMany({})` command replicates faithfully to every member.

### 3.3. RTO Must Account for the Entire Chain

```text
Detection → verification → choosing restore point
→ provisioning target environment/compute → downloading/decrypting backup
→ restoring data and indexes → verifying permissions
→ running application smoke tests → shifting traffic
→ monitoring and confirming recovery
```

Never estimate RTO solely from `mongorestore` runtime.

---

## 4. Choosing a MongoDB Backup Strategy

### 4.1. Logical Backup: `mongodump`/`mongorestore`

Advantages:

- Simple to understand and practice.
- Exports BSON data along with required metadata and index definitions.
- Can export a single database or selected namespaces.
- Convenient for lab restores, migrations, and small-to-medium datasets.

Limitations:

- Incurs read, serialization, CPU, network, and storage overhead.
- A collection/database dump taken during active writes does not guarantee a cross-collection transactionally consistent snapshot.
- Not a complete continuous PITR system.
- Restoring very large datasets can take a long time.
- Must verify server/tools/FCV version compatibility.
- Users/roles, topology settings, and secrets require separate backup planning.

### 4.2. Storage/Physical Snapshots

Advantages:

- Better suited to very large databases and tighter RTOs than logical restore.
- When properly engineered, avoids full BSON dump/restore serialization costs.

Requirements:

- Filesystem/storage snapshots must be consistent across all required volumes.
- Account for WiredTiger data files, journal, checkpoints, and topology.
- Follow MongoDB-supported snapshot procedures; never copy a live `/data/db` directory ad hoc and call it a valid backup.
- Test the restore workflow on the exact platform and storage version.

### 4.3. MongoDB Atlas Cloud Backup

On supported Atlas deployments, manage snapshots and retention via backup policies. Continuous Cloud Backup, when enabled and supported for your deployment/tier, pairs snapshots with oplog data to restore to a point within the PITR window. Availability, cost, granularity, and limits depend on server/cluster types per current Atlas documentation.

### 4.4. A Replica Set Is Not a Snapshot

A replica set provides high availability and failover, not an independent history protecting against:

- Human error.
- Buggy migrations.
- Ransomware or account compromise.
- Bulk update logic bugs.
- Schema corruption replicated to every node.
- Cluster-wide failures.

Backups must reside outside the database's failure domain.

### 4.5. Decision Matrix

| Workload | Starting Approach | Mandatory Additions |
|---|---|---|
| Local learning | `mongodump` of lab database | Practice restore to another namespace |
| Integration tests | Deterministic seeds/fixtures | No production backups needed |
| Small self-managed replica set | Logical backup or supported snapshots | Restore drills, offsite copies, RPO/RTO |
| Large self-managed cluster | Suitable storage/enterprise backup solution | Snapshot consistency, PITR, monitoring |
| Sharded cluster | Sharding-aware backup solution | Consistent point across shards and config metadata |
| Atlas production | Cloud Backup / Continuous Backup where supported | Retention/PITR policy, restore tests, access controls |

Never choose a backup strategy merely because "it writes a file"; always validate restore time and consistency.

---

## 5. Lab Environment and Practice Scope

This lesson uses a `sales_lab` database with several collections:

```text
sales_lab
  categories
  customers
  products
  inventory
  orders
  payments
  outbox
```

You can use the sales application's synthetic dataset or seed a small sample. The commands below prioritize **preserving** existing data.

### 5.1. Local MongoDB

Assume a local MongoDB instance runs at `127.0.0.1:27017` with read/write access to `sales_lab`. If running via Docker and a single-node replica set:

```powershell
docker ps --filter name=sales-mongo
docker exec -it sales-mongo mongosh
```

In `mongosh`:

```javascript
db.adminCommand({ ping: 1 });
db.adminCommand({ hello: 1 });
```

### 5.2. Creating a Sample If `sales_lab` Does Not Exist Yet

Execute only on a lab database you own:

```javascript
const lab = db.getSiblingDB("sales_lab");
const fixed = ISODate("2026-01-01T00:00:00Z");

lab.customers.updateOne(
  { _id: "CUS-001" },
  {
    $setOnInsert: {
      fullName: "Sample Customer",
      email: "customer001@example.test",
      createdAt: fixed
    }
  },
  { upsert: true }
);

lab.products.updateOne(
  { _id: "SKU-001" },
  {
    $setOnInsert: {
      name: "Sample Product",
      unitPriceVnd: NumberLong("80000"),
      active: true,
      createdAt: fixed
    }
  },
  { upsert: true }
);

lab.orders.updateOne(
  { _id: "ORD-0001" },
  {
    $setOnInsert: {
      requestId: "REQ-0001",
      customerId: "CUS-001",
      status: "PAID",
      totalVnd: NumberLong("160000"),
      items: [
        {
          sku: "SKU-001",
          quantity: 2,
          unitPriceVnd: NumberLong("80000"),
          lineTotalVnd: NumberLong("160000")
        }
      ],
      createdAt: fixed
    }
  },
  { upsert: true }
);
```

This snippet inserts missing records by `_id` without overwriting existing ones on reruns.

### 5.3. Confirm It Is Not Production

Before any backup or restore command:

```javascript
db.getName();
db.adminCommand({ hello: 1 });
db.getSiblingDB("sales_lab").getCollectionNames();
```

Record the environment, endpoint, owner, ticket, and approved action. Never run a "quick test" restore against a production application URI.

---

## 6. `mongodump` and `mongorestore` Are MongoDB Database Tools

These two utilities ship in **MongoDB Database Tools**, versioned independently of MongoDB Server.

### 6.1. Check Tool Versions

On a host with tools installed:

```bash
mongodump --version
mongorestore --version
```

If running via a container bundling the tools:

```bash
docker exec sales-mongo mongodump --version
docker exec sales-mongo mongorestore --version
```

Not every custom container image bundles Database Tools; if missing, install compatible tools in a separate environment or use a controlled utilities container.

### 6.2. Version Compatibility

Record:

- MongoDB Server version and Feature Compatibility Version (FCV).
- MongoDB Database Tools version.
- Source and target deployment versions.
- Special features: time series, encrypted collections, views, sharding.

Never assume a dump from any server major version restores cleanly into any target version.

### 6.3. What a Dump Contains

A logical dump captures collection data and metadata needed to recreate collections and indexes. It **does not back up your full operational environment**, such as Kubernetes YAML, TLS certificates, secrets, firewall rules, audit policies, app configuration, or cloud backup policies.

Dumping only a single database also omits **user and role definitions** stored at the deployment level. Plan identity and access-control backups separately.

---

## 7. Backing Up a Single Database to Practice Restoration

This is the safest pattern for practice: back up `sales_lab`, then restore it to `sales_lab_restore`.

### 7.1. Backing Up with `mongodump` on the Host

With MongoDB Database Tools installed on the host, run from a directory **outside any Git repository**:

```powershell
mongodump --uri="mongodb://127.0.0.1:27017/" --db=sales_lab --archive="sales_lab.archive.gz" --gzip
```

Use an unauthenticated URI only for private local development instances. Against secured deployments, use a properly scoped backup account, authentication database, and secure secret injection.

### 7.2. Backing Up When Tools Run Inside Docker

On Windows PowerShell:

```powershell
docker exec sales-mongo mongodump --host 127.0.0.1 --port 27017 --db sales_lab --archive=/tmp/sales_lab.archive.gz --gzip
docker cp sales-mongo:/tmp/sales_lab.archive.gz .\sales_lab.archive.gz
```

The first command writes the archive **inside the container**; the second copies it to your host's current working directory.

### 7.3. Flag Meanings

| Flag | Meaning |
|---|---|
| `--db sales_lab` | Select a single database |
| `--archive=...` | Write a single archive stream/file |
| `--gzip` | Compress the archive with gzip |
| `--uri` or `--host/--port` | Connect to the source deployment |
| `--username`/auth settings | Use only with authorized accounts; avoid passing passwords via CLI args |

Do not combine `--out` and `--archive` in the same command.

### 7.4. Consistency Limitations

**Important:** `mongodump --db=sales_lab` while the API actively writes **does not guarantee a transactionally consistent snapshot across multiple collections**. For example:

```text
10:00:00 mongodump starts reading orders
10:00:01 checkout updates inventory
10:00:02 checkout inserts order
10:00:03 mongodump reads inventory
```

The restore can reflect `orders` and `inventory` at two different points in time.

In a quiet lab without concurrent writes, this risk is tiny. Production requires a supported consistent backup mechanism (full replica set oplog, physical snapshot/Atlas backup, or an appropriate maintenance window).

### 7.5. Never Claim `--db` + `--oplog` Is a Point-in-Time Backup

MongoDB Database Tools require a **full dump of a replica set member** when using `--oplog`. Scoping options such as `--db` or `--collection` are invalid alongside `--oplog`.

This command is **invalid**:

```bash
mongodump --db sales_lab --oplog --archive=sales.archive.gz
```

---

## 8. Naming, Manifests, and Protecting Backup Files

### 8.1. File Naming

Example:

```text
sales_lab-2026-11-14T060000Z-logic-v1.archive.gz
```

Filenames should encode deployment, UTC timestamp, scope, format, and schema/plan version. Never put customer PII inside filenames.

### 8.2. Metadata Manifest

An externally managed backup catalog or manifest (without creating extra repo files for this exercise) should capture:

```yaml
backupId: sales-lab-20261114-060000
sourceEnvironment: lab
sourceNamespace: sales_lab
backupType: logical-database
startedAtUtc: "2026-11-14T06:00:00Z"
completedAtUtc: "2026-11-14T06:00:08Z"
consistentPointInTime: false
tool: mongodump
compression: gzip
archiveName: sales_lab.archive.gz
sha256: "<verified hash>"
retentionClass: lab-short-lived
restoreLastTestedAtUtc: null
owner: database-operations
```

Never mark `consistentPointInTime: true` simply because the command exited with code 0.

### 8.3. SHA-256 on Windows

```powershell
Get-FileHash -LiteralPath .\sales_lab.archive.gz -Algorithm SHA256
```

On Linux:

```bash
sha256sum sales_lab.archive.gz
```

Store the hash and re-verify it after file transfer. A hash only proves **bytes did not change relative to a trusted hash**—it does not guarantee the data is restorable.

### 8.4. Gzip Integrity vs. Restore Validity

A readable gzip file is not sufficient: BSON may fail validation on the target version, lack required indexes, or miss application-critical collections. A real restore drill is mandatory.

### 8.5. Protecting Sensitive Data Inside Backups

Backups can hold:

- Emails and transaction details.
- Addresses and PII.
- Internal audit logs.
- Password hashes if a full dump includes system user records.
- Access tokens/secrets if mistakenly stored in the DB.

Enforce encryption at rest and in transit, restricted storage ACLs, proper secret/KMS management, access auditing, defined retention, and secure deletion.

### 8.6. Never Store Archives Inside a Source Repository

A Git working tree is not backup storage: archives can be huge, contain PII, and get committed by accident. Use dedicated backup storage under least privilege.

---

## 9. Restoring a Database to a Different Name to Avoid Touching Source

Goal: read `sales_lab.archive.gz` and restore collections into **`sales_lab_restore`**.

### 9.1. Preparation

Use a separate lab MongoDB instance—or the same instance only after confirming `sales_lab_restore` does not exist and no application reads it.

Do not restore into the original `sales_lab` at this step.

### 9.2. Preview the Plan with Dry Run

If Database Tools are on the host:

```powershell
mongorestore --uri="mongodb://127.0.0.1:27017/" --archive="sales_lab.archive.gz" --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*" --dryRun --verbose
```

`--dryRun` prints planned restore actions **without importing data**. It does not replace an actual restore and validation.

### 9.3. Restore on the Host

```powershell
mongorestore --uri="mongodb://127.0.0.1:27017/" --archive="sales_lab.archive.gz" --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*"
```

### 9.4. Restore Using Docker

Copy the archive into the container if needed:

```powershell
docker cp .\sales_lab.archive.gz sales-mongo:/tmp/sales_lab.archive.gz
```

Dry run:

```powershell
docker exec sales-mongo mongorestore --host 127.0.0.1 --port 27017 --archive=/tmp/sales_lab.archive.gz --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*" --dryRun --verbose
```

Restore:

```powershell
docker exec sales-mongo mongorestore --host 127.0.0.1 --port 27017 --archive=/tmp/sales_lab.archive.gz --gzip "--nsFrom=sales_lab.*" "--nsTo=sales_lab_restore.*"
```

### 9.5. Why Use `nsFrom`/`nsTo`?

A logical MongoDB backup archive stores original namespaces such as `sales_lab.orders`. Remapping:

```text
sales_lab.orders       → sales_lab_restore.orders
sales_lab.customers    → sales_lab_restore.customers
sales_lab.inventory    → sales_lab_restore.inventory
```

prevents overwriting the source database and enables side-by-side comparison. Note that this namespace-remapping approach cannot be combined with `mongorestore --oplogReplay`.

### 9.6. Do Not Use `--drop` on Your First Lab Restore

`--drop` instructs `mongorestore` to drop matching target collections before importing. If the target accidentally points at the source, data loss or downtime occurs.

Into a fresh empty target, `--drop` is unnecessary. If re-running a test restore into the same target hits duplicate-key errors, use a **fresh target namespace** or clean the verified disposable target deliberately.

### 9.7. Expected Result

After restoring:

```javascript
const restored = db.getSiblingDB("sales_lab_restore");

printjson(restored.getCollectionNames());
printjson({
  customers: restored.customers.countDocuments({}),
  products: restored.products.countDocuments({}),
  orders: restored.orders.countDocuments({})
});
```

Never hardcode expectations like 24/30/120 if your source dataset differs; compare against the backup manifest or counts captured at backup time.

---

## 10. Verifying Restored Data: Look Beyond Exit Codes

### 10.1. Compare Counts

```javascript
const source = db.getSiblingDB("sales_lab");
const target = db.getSiblingDB("sales_lab_restore");

const names = [
  "categories", "customers", "products",
  "inventory", "orders", "payments", "outbox"
];

for (const name of names) {
  printjson({
    collection: name,
    sourceNow: source.getCollection(name).countDocuments({}),
    restored: target.getCollection(name).countDocuments({})
  });
}
```

**Caution:** if the source continued accepting writes after backup, current counts differing from restored counts is normal. Compare against the backup snapshot manifest or cut point—never compare two different points in time and wrongly declare the restore broken.

### 10.2. Compare Key Samples

```javascript
const restored = db.getSiblingDB("sales_lab_restore");

printjson(restored.orders.findOne({ _id: "ORD-0001" }));
printjson(restored.customers.findOne({ _id: "CUS-001" }));
printjson(restored.products.findOne({ _id: "SKU-001" }));
```

### 10.3. Verify Indexes

```javascript
printjson(restored.orders.getIndexes());
printjson(restored.customers.getIndexes());
printjson(restored.products.getIndexes());
```

Check:

- `_id` index.
- Business unique indexes.
- Compound index key ordering.
- Collation, partial filter, and sparse options where used.
- Indexes are not unexpectedly marked `hidden`.

### 10.4. Verify BSON Types

```javascript
restored.orders.aggregate([
  {
    $group: {
      _id: {
        createdAt: { $type: "$createdAt" },
        total: { $type: "$totalVnd" }
      },
      count: { $sum: 1 }
    }
  }
]);
```

If your data standard requires BSON `Date` and `Int64`, verify no unexpected String dates or String monetary fields exist.

### 10.5. Verify Business Invariants

For example, order line totals:

```javascript
restored.orders.aggregate([
  {
    $project: {
      _id: 1,
      totalVnd: 1,
      calculated: { $sum: "$items.lineTotalVnd" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$totalVnd", "$calculated"] }
    }
  }
]);
```

Expected: zero mismatches for a cleanly seeded dataset.

### 10.6. Check for Orphan References

```javascript
restored.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
    }
  },
  { $match: { customer: { $size: 0 } } },
  { $project: { _id: 1, customerId: 1 } }
]);
```

This is an application-level consistency check, not a MongoDB foreign-key constraint.

### 10.7. Application Smoke Test

Connect a schema-compatible build of the application to the **restore target** and execute read-only API checks:

- Fetch order by ID.
- List orders by customer.
- Render product prices.
- Run aggregation/reporting queries.
- Verify authentication and tenant isolation.
- Inspect application logs and compatibility.

Switch live traffic only after formal recovery sign-off, proper credentials/roles/config, and active monitoring.

---

## 11. Full Replica Set Backup with `--oplog`

A database-only backup teaches namespace restoration, yet a production replica set accepting concurrent writes may need a point-in-time consistent logical dump.

### 11.1. What Does `--oplog` Do?

On a **full dump of a replica set member**, `mongodump --oplog` captures oplog entries written during the dump, allowing `mongorestore --oplogReplay` to bring the restore to a consistent state corresponding to that dump within supported limits.

### 11.2. Example Command on a Self-Managed Replica Set

In an **isolated environment authorized for a full instance backup**, without filtering to a single database:

```bash
mongodump --uri="mongodb://127.0.0.1:27017/?replicaSet=rs0" --archive=rs0-full.archive.gz --gzip --oplog
```

If running against a local Docker replica set:

```powershell
docker exec sales-mongo mongodump --host 127.0.0.1 --port 27017 --archive=/tmp/rs0-full.archive.gz --gzip --oplog
docker cp sales-mongo:/tmp/rs0-full.archive.gz .\rs0-full.archive.gz
```

### 11.3. Do Not Combine with Data-Limiting Flags

With `--oplog`, MongoDB Database Tools require a full replica-set-member dump. Never pass:

- `--db`.
- `--collection`.
- `--query`.
- `--dumpDbUsersAndRoles`.

Never run `--oplog` against `mongos` expecting a cluster-consistent full sharded backup: sharded clusters operate differently and have specific constraints.

### 11.4. Operations That Can Still Fail the Dump

Per Database Tools documentation, operations such as collection renames, `$out`, user/role/privilege modifications, or cluster-wide settings changes during the dump can cause `mongodump --oplog` to fail.

Avoid schema or security migrations during backup windows, and always inspect exit codes and logs instead of assuming any generated file is valid.

### 11.5. Oplog Window

A replica set's oplog has finite retention based on configured size and write throughput. If a dump takes longer than the oplog retains needed entries, the backup must be treated as failed. Monitor write rate, oplog window, and backup duration.

### 11.6. Backing Up from a Secondary?

Taking backups from a secondary can offload the primary under supported topology/tool options, provided you:

- Check replication lag.
- Confirm the secondary is an eligible source.
- Review backup tool and `readPreference` policies.
- Control I/O impact on the node.
- Record the exact backup timestamp and RPO achieved.

Never assume a secondary is always completely caught up.

---

## 12. Full Restore with Oplog Replay: Only into an Empty Isolated Deployment

### 12.1. Logical Workflow

```text
Full replica set dump (--oplog)
          │
          ▼
Encrypted archive + checksum
          │
          ▼
Fresh isolated restore deployment
          │
          ▼
mongorestore --oplogReplay
          │
          ▼
Verify data / users / indexes / app
          │
          ▼
Recovery acceptance
```

### 12.2. Example Command

In a dedicated restore environment using a target-specific URI:

```bash
mongorestore --uri="mongodb://RESTORE_TARGET_HOST:27017/" --archive=rs0-full.archive.gz --gzip --oplogReplay
```

**This is a template command—never copy placeholder hostnames verbatim.** Verify the target is empty/disposable and compatible, never the production source.

### 12.3. Do Not Combine `nsFrom`/`nsTo` or Namespace Filters

`--oplogReplay` on a full dump does not support combining options such as:

- `--db`.
- `--collection`.
- `--nsInclude` or `--nsExclude`.
- `--nsFrom` or `--nsTo`.

To restore only `sales_lab` into `sales_lab_restore`, use the **database-only dump without `--oplog`** from earlier in this lab, with its consistency trade-offs clearly documented.

### 12.4. Why Omit `--drop` Here?

A full dump can include `admin` and user/role collections. `mongorestore --drop` drops and recreates collections, potentially altering the very users you are authenticated with mid-restore and locking you out. On shared or production deployments, this is dangerous.

Use `--drop` only under an approved restoration plan with current backups, verified break-glass recovery credentials, a change window, and double-checked target identity. A fresh empty target is the safer learning choice.

### 12.5. Oplog Replay Is Not an Unlimited "Time Machine"

`mongodump --oplog` captures only writes **occurring during the dump itself**—it does not retain days of continuous transaction history. You cannot arbitrarily restore to 16:37 last week without an appropriate backup chain and PITR infrastructure.

### 12.6. Time Series and FCV Compatibility

Newer MongoDB releases can alter the internal format of time series collections across FCV transitions. Oplog replay across format boundaries has restrictions; consult version-specific Database Tools and Server docs, particularly when upgrading MongoDB 8.x/9.x.

---

## 13. Sharded Clusters and Consistent Backups

### 13.1. Why This Differs from a Single Replica Set

A sharded cluster consists of:

```text
mongos routers
    │
    ├── shard A replica set
    ├── shard B replica set
    ├── shard C replica set
    └── config server replica set
```

Data and cluster metadata mutate across multiple shards alongside chunk migrations and distributed transactions.

### 13.2. Never Run `mongodump --oplog` Through `mongos` Expecting a Cluster-Consistent Snapshot

MongoDB Database Tools do not support `--oplog` for full sharded-cluster backups the way they do on a single replica set member. A command completing without error does not guarantee cluster-wide consistency.

### 13.3. Recommendations

- Atlas: use managed backups and PITR when supported for your tier/topology.
- Self-managed sharded clusters: use a **MongoDB-supported sharded backup procedure** or version-compatible enterprise solution.
- Capture config server metadata alongside coordinated shard snapshots.
- Account for chunk migrations, distributed transactions, and cluster-wide settings.
- Conduct restore drills against a **sharded test topology** when production uses sharding.

### 13.4. Manual Shard-by-Shard Backups Risk Inconsistency

Snapshotting shard A at 10:00, shard B at 10:05, and config metadata at 10:08 produces routing and data skew. Never stitch uncoordinated replica set dumps together claiming a "cluster-consistent backup".

### 13.5. Shard Keys and Restore Validation

After restoring a sharded cluster, verify:

- Shard and catalog metadata.
- Chunk distribution.
- Sharded index rules.
- Query routing, reads, and writes.
- Distributed transaction behavior.
- Cluster balancer state.
- Application workloads.

---

## 14. Point-in-Time Recovery with Cloud Backup

### 14.1. What Is PITR?

PITR lets you pick a recovery timestamp within a supported backup history window:

```text
Snapshot S0 ── oplog/change history ──→ T1 ──→ T2 ──→ T3
                                        ▲
                                        │
                               choose restore point
```

For instance, if someone runs a bad `updateMany` at 10:12, and the recovery window covers it, restore to a point immediately preceding that write within system granularity limits.

### 14.2. Atlas Continuous Cloud Backup

MongoDB Atlas offers continuous cloud backup on supported deployments, combining snapshots and oplog history to restore to a specific point in time. Availability and limits depend on tier/cluster type, retention policies, restore windows, server versions, and billing.

### 14.3. Never Guess the Restore Timestamp

Before executing:

1. Verify the incident timeline.
2. Confirm exact UTC timestamps and time zones.
3. Check the available recovery window.
4. Inspect snapshot boundaries and the latest recoverable timestamp.
5. Restore to an isolated target first.
6. Verify data consistency and application invariants.
7. Execute cutover only after review.

### 14.4. A Minute-Level RPO Still Has Real Limits

Even continuous backups depend on whether recent writes persisted to backup storage, plus backup windows and restore granularity. Document the true "latest recoverable timestamp".

### 14.5. PITR Does Not Solve Every Incident Automatically

If a logic bug went unnoticed for weeks, rolling the entire cluster back days would wipe out valid orders. **Selective data repair**—reading from an isolated snapshot restore and reconciling affected records—is often better than a full cluster rollback.

---

## 15. RBAC: Authentication Differs from Authorization

- **Authentication:** proves "who is connecting?".
- **Authorization:** defines what that user may do on a database, collection, or cluster.

A successful connection does not imply the user has least-privilege permissions.

### 15.1. Roles to Consider

| Actor | Need | Suggested Role |
|---|---|---|
| Sales API | CRUD on owned collections | Custom role or database-scoped `readWrite` where appropriate |
| Read-only dashboard | Analytical queries | `read` or custom role granting `find` |
| Outbox worker | Read/update outbox | Custom collection-level actions |
| DBA operator | DDL, indexes, diagnostics | Task-scoped, time-bound admin role |
| Backup service | Read data/metadata for backups | `backup` role or minimum custom scope |
| Restore operator | Recreate data on target | `restore` role plus extra actions when required |
| Root / break-glass | Disaster / emergency admin | Strictly controlled; never an app account |

Verify exact privileges against your MongoDB version and commands; operations like restoring users/roles or replaying oplog require broader permissions than regular data restores.

### 15.2. Principle of Least Privilege

Never grant:

```javascript
roles: ["root"]
```

to an API user that only reads and writes orders. Pair role scoping with network restrictions, TLS, secret management, audit logs, and credential rotation.

### 15.3. Built-In Roles Have Defined Scopes

- `read` on `sales_lab`: read access within that database per role actions.
- `readWrite` on `sales_lab`: read/write and related operations across the database; still overly broad for an API needing only one collection.
- `dbAdmin`: manages database metadata and indexes; does not grant universal data read/write.
- `userAdmin`: manages users and roles within scope.
- `backup`/`restore`: built-in roles defined on the `admin` database for backup and restore jobs per MongoDB documentation.
- `clusterMonitor`: monitoring access, not a data writer.

"Safe-sounding" roles still carry privilege-escalation risks if they allow managing users or roles. Audit full effective privileges.

---

## 16. Spin Up a Separate RBAC Lab Instead of Modifying an Existing Lab Instance

An unauthenticated local MongoDB instance cannot **demonstrate access enforcement**. To practice RBAC, run a **separate container** on host port 27019 using standalone `mongod --auth`. Standalone mode does not support multi-document transactions, yet it suffices for practicing users and roles.

### 16.1. Launch the Isolated Auth Lab

Windows PowerShell:

```powershell
docker run -d --name sales-rbac-lab -p 127.0.0.1:27019:27017 -v sales-rbac-data:/data/db mongo:8.0 --auth
```

**Use solely on a personal development host.** Never use this container as a source for production backups or restores.

### 16.2. Create the Initial Admin User

When a deployment has zero users, MongoDB's localhost exception allows creating **the first user or role** from localhost under supported conditions. From inside the container:

```powershell
docker exec -it sales-rbac-lab mongosh
```

In `mongosh`:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "lab_admin",
  pwd: passwordPrompt(),
  roles: [
    { role: "root", db: "admin" }
  ]
});
```

`passwordPrompt()` lets you type the password interactively rather than saving plaintext in scripts or shell history.

**Root is strictly for this lab's admin user**, never an application identity. Enabling authorization on a multi-node production replica set also requires internal member authentication (keyFile or x.509) plus TLS and network rules; **never copy standalone `--auth` blindly onto a multi-node replica set** without internal auth.

### 16.3. Authenticate as Administrator

```powershell
docker exec -it sales-rbac-lab mongosh --username lab_admin --authenticationDatabase admin --password
```

`mongosh` prompts interactively for the password depending on client version. Never pass passwords as shell command arguments.

### 16.4. Practicing RBAC on an Already-Secured Deployment

If you already have a secured dev deployment, you do not need a new container—provided you hold permission to manage test users/roles and never grant or revoke `root` on production accounts.

---

## 17. Create Application and Reporting Users

Authenticate as `lab_admin` against `sales-rbac-lab` first, then run:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createUser({
  user: "sales_app",
  pwd: passwordPrompt(),
  roles: [
    { role: "readWrite", db: "sales_lab" }
  ]
});

sales.createUser({
  user: "sales_reporter",
  pwd: passwordPrompt(),
  roles: [
    { role: "read", db: "sales_lab" }
  ]
});
```

### 17.1. Why Is `readWrite` Still Called a Demo?

Database-wide `readWrite` can be excessive for a microservice touching only specific collections. The lab uses it for basic RBAC mechanics; production should evaluate custom roles, per-service identities, and collection-scoped actions.

### 17.2. Authentication Database

Both users live in `sales_lab`, so their authentication database (`authSource`) is `sales_lab`:

```text
mongodb://HOST:27019/sales_lab?authSource=sales_lab
```

Never put passwords inside committed URIs. In `mongosh`:

```powershell
docker exec -it sales-rbac-lab mongosh --username sales_reporter --authenticationDatabase sales_lab --password
```

### 17.3. Users Gain Zero Automatic Access to `admin`

A user holding `read` on `sales_lab` does not receive `root`, `userAdminAnyDatabase`, or read access to other databases.

### 17.4. Role Scopes Do Not Replace Network Isolation

Even read-only accounts must connect over TLS and restricted allowlists on shared deployments. RBAC cannot prevent network access or data exfiltration if read credentials leak.

---

## 18. Create a Custom Read-Only Role for `orders`

While authenticated as `lab_admin`:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createRole({
  role: "ordersReader",
  privileges: [
    {
      resource: { db: "sales_lab", collection: "orders" },
      actions: ["find"]
    }
  ],
  roles: []
});

sales.createUser({
  user: "orders_reporter",
  pwd: passwordPrompt(),
  roles: [
    { role: "ordersReader", db: "sales_lab" }
  ]
});
```

### 18.1. When Are Custom Roles Useful?

When a reporting job only needs to read `orders` and must be blocked from customer or payment PII, collection-scoped privileges shrink the blast radius.

### 18.2. `find` Grants Nothing Else

A custom role granting only `find` on `orders` cannot build indexes, insert, delete, manage users, or read other collections. Specialized queries may need additional actions—grant them strictly from real business needs and verify with privilege tests.

### 18.3. Scope Roles to the Right Database

This custom role is defined inside `sales_lab`. When granting it, specify `{role:"ordersReader",db:"sales_lab"}`. Never confuse the role's database with another account's authentication database.

### 18.4. Never Trust Role Names Alone

A role named `ordersReader` becomes dangerous if someone edits it to include `dropDatabase` or `anyAction`. Inspect effective privileges and review role definitions like code.

---

## 19. Verify Who the Current Session Is Authenticated As

### 19.1. `connectionStatus`

Authenticate as the actor under test and run:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

`authInfo` returns:

- `authenticatedUsers`.
- `authenticatedUserRoles`.
- `authenticatedUserPrivileges` when `showPrivileges: true`.

### 19.2. Listing Role Names Is Not Always Enough

Effective privileges can come from inherited roles. Inspect the actual `(resource, actions)` grants rather than trusting names like `read` or `ordersReader`.

### 19.3. Inspect User Definitions

With appropriate admin privileges on the database owning the user:

```javascript
const sales = db.getSiblingDB("sales_lab");

printjson(sales.getUser("sales_reporter", {
  showPrivileges: true,
  showCredentials: false
}));
```

Never enable `showCredentials: true` during routine troubleshooting—it exposes unnecessary password-hash metadata.

### 19.4. List Users

```javascript
db.getSiblingDB("sales_lab").getUsers();
```

Do not assume `getUsers()` in `sales_lab` lists MongoDB users defined in other authentication databases.

### 19.5. Atlas Manages Users Differently from Self-Managed Clusters

MongoDB Atlas manages database users, roles, and project access via the Atlas UI/API; some `usersInfo` management commands behave differently from self-managed clusters. Use Atlas-provided governance tools and policy checks.

---

## 20. Positive and Negative Privilege Tests

An access-control test suite must verify both:

- **Permitted** actions succeed.
- **Forbidden** actions are genuinely rejected.

### 20.1. Positive Test for `sales_reporter`

Authenticate as `sales_reporter`:

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.orders.findOne({});
sales.orders.countDocuments({});
```

In an empty RBAC lab, `findOne` returns `null` without throwing `Unauthorized`, proving read permission works.

### 20.2. Negative Test for `sales_reporter`

Strictly inside the disposable lab, try:

```javascript
db.getSiblingDB("sales_lab").orders.insertOne({
  _id: "DENIED-TEST-001",
  marker: "write-should-be-denied"
});
```

Expect an `Unauthorized` error (or equivalent) because `sales_reporter` only has `read`. If the write unexpectedly succeeds, **halt testing**, inspect user roles, and remove the test record using an administrator account. Never run negative write tests in production.

### 20.3. Negative Test for Custom Role

Authenticate as `orders_reporter`:

- `sales_lab.orders.findOne()`: allowed.
- `sales_lab.customers.findOne()`: denied unless another role grants access.
- `sales_lab.orders.deleteOne()`: denied.

### 20.4. Distinguish Real Error Causes

Separate:

- Authentication failed (wrong user, password, or `authSource`).
- Unauthorized (authenticated, yet lacking the required action).
- Network or TLS failure.
- Non-existent namespace.
- Driver/server incompatibility.

A read returning `null` on an empty collection is not a privilege denial.

---

## 21. Backup Service Identities and Restore Operators

### 21.1. Backup User

On the self-managed RBAC lab, authenticated as admin:

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "backup_agent",
  pwd: passwordPrompt(),
  roles: [
    { role: "backup", db: "admin" }
  ]
});
```

The built-in `backup` role is tailored for backup jobs. Depending on specialized data types, encryption, and `mongodump` options, verify additional required privileges in official docs.

### 21.2. Restore User

```javascript
const admin = db.getSiblingDB("admin");

admin.createUser({
  user: "restore_operator",
  pwd: passwordPrompt(),
  roles: [
    { role: "restore", db: "admin" }
  ]
});
```

Restoring users/roles or replaying the oplog can require additional privileges. Avoid granting unbounded `root`; prefer approved, time-bounded accounts/tokens revoked after the incident.

### 21.3. Backup Privileges Should Not Grant Restore Privileges

Separating backup and restore identities limits risk: a nightly automated backup service needs to read data, never drop or overwrite live databases.

### 21.4. Recovery Credentials

Maintain a secure break-glass process with audited usage, post-incident rotation, and periodic access tests. Never encrypt backups without recoverable decryption keys.

### 21.5. Privilege Validation

Authenticated as the backup user:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Verify backup actions exist without unnecessary write or drop privileges. For restore operators, verify target namespaces and workflow-scoped permissions.

---

## 22. Why Not Enable Authorization Recklessly on an Old Lab Replica Set?

### 22.1. Replica Sets Require Internal Authentication

A multi-node replica set requires members to authenticate to one another when security authorization is enabled, typically using a `keyFile` or x.509 certificates with TLS and network controls. Simply appending `--auth` to a `mongod --replSet` instance without internal auth and secret provisioning can break cluster membership.

### 22.2. Avoid Locking Yourself Out of Admin Access

Enabling auth before properly creating an admin user can lock you out, aside from narrow localhost-exception rules. Production security enablement must follow a tested runbook with backups, rollback steps, and a change window.

### 22.3. The Local RBAC Lab Is Intentionally Standalone

Container `sales-rbac-lab` uses standalone `--auth` purely to practice users and roles. It does not replace a replica set lab for transactions and oplog backups.

### 22.4. Never Put Keyfiles or Credentials in a Repository

Keyfiles, passwords, and TLS private keys belong in properly secured secret storage. Never paste them into Markdown tutorials or Git even "just to test".

---

## 23. Verifying Backup Compatibility with Active Permissions

During disaster recovery, data may restore cleanly yet applications still fail to connect because:

- User/role definitions were omitted from the backup or restore.
- Authentication database names differ.
- Secrets rotated since the backup.
- Target TLS CA or hostnames differ.
- Cloud project or IAM policies changed.
- Network allowlists omit the target environment.
- App accounts end up over- or under-privileged.
- The database namespace changed while app URIs still point to the old name.

### 23.1. Separate Data Recovery from Access Recovery

```text
Data Recovery
  ├── Data documents
  ├── Indexes and collection options
  └── Schema validation / TTL / views

Access Recovery
  ├── Database users and roles
  ├── Secrets and KMS keys
  ├── TLS / network policy
  ├── Service identities
  └── Application connection configuration
```

Never blindly copy production user credentials into shared staging without policy review. A restore target needs minimal scoped identities for validation and application smoke tests.

### 23.2. Verify Effective Privileges After Restore

When authorized:

```javascript
db.getSiblingDB("admin").runCommand({
  connectionStatus: 1,
  showPrivileges: true
});
```

Then run read/write tests under each service identity against allowed test namespaces.

---

## 24. Securing Backup Storage Against Unauthorized Deletion or Tampering

### 24.1. Encrypt

Backups can contain your entire business dataset. Enforce:

- Encryption in transit (TLS).
- Encryption at rest using managed keys.
- Access auditing.
- Proper secret/KMS key governance.
- Key recovery procedures.

### 24.2. Immutable Copies

A backup stored on the same server or volume as the database can be wiped out together by disk failure, hardware loss, or ransomware. Keep offsite copies in a separate failure domain, and evaluate Object Lock / WORM / immutable retention where supported.

### 24.3. Separate Backup Deletion Permissions

The service writing daily backups should not necessarily hold permission to purge historical copies. Separate retention/purge roles and require approval where appropriate.

### 24.4. Retention Policy

Example policy subject to organizational approval:

| Tier | Frequency | Retention |
|---|---|---|
| Operational | Daily | 14 days |
| Recovery | Weekly | 8 weeks |
| Audit / Compliance | Monthly / Yearly | Per regulatory and contractual mandates |
| PITR | Continuous window | Per RPO and budget |

This table is **illustrative**, not a legal standard. Tailor retention to regulatory, privacy, contractual, and budget constraints.

### 24.5. Data Erasure Requests vs. Backup Retention

When handling personal-data deletion requests, define policies covering backup expiration, legal holds, and re-introduction prevention upon restore. Never promise "instant deletion everywhere" if immutable backups persist through a retention window.

---

## 25. Backup Monitoring: Look Beyond Cron Exit Status

A backup job reporting "exit code 0" can still miss your RPO or fail to restore due to missing keys or metadata.

### 25.1. Metrics

- Last successful backup timestamp.
- Backup duration.
- Output artifact size.
- Snapshot/backup age.
- Upload completion status.
- Checksum verification status.
- Oplog window duration.
- Replication lag.
- Last restore drill status.
- Available disk/bucket capacity.
- Encryption/KMS key accessibility.
- Errors and retries.
- Backup service identity/credential expiration.

### 25.2. Essential Alerts

- No successful backup within the scheduled threshold.
- Backup age exceeding RPO limits.
- Sudden unexplained shrink or spike in archive size.
- Oplog window shorter than backup duration.
- Backup storage nearing capacity quota.
- Restore drill overdue in its cycle.
- Backup account authentication or authorization failures.
- Encryption/decryption key unavailable.

### 25.3. Sensitive Data in Backup Logs

Never log full MongoDB URIs containing passwords, never dump customer documents, and never copy backup archives into public CI artifact stores.

### 25.4. A Partial File Does Not Equal Success

Tools can create an output file and then exit non-zero. Mark a job "SUCCESS" only after the command exits cleanly, artifact checksums match, and policy checks pass.

---

## 26. Restore Drills: Acceptance Criteria

A meaningful restore drill needs **acceptance criteria** defined before starting.

### 26.1. Minimum Steps

1. Identify `backupId` and source timestamp.
2. Download/decrypt the archive as an authorized operator.
3. Verify the checksum.
4. Restore into an isolated environment.
5. Verify collection counts and sample IDs.
6. Verify indexes and collection options.
7. Verify BSON types and unique constraints.
8. Verify business invariants.
9. Run application smoke tests with realistic auth/roles.
10. Measure elapsed recovery time.
11. Document discovered gaps.
12. Confirm the drill target is properly decommissioned/cleaned per retention rules afterward.

### 26.2. Restore Evidence Record

An evidence record might capture:

```yaml
drillId: restore-drill-20261114
backupId: sales-lab-20261114-060000
sourceVersion: "MongoDB version captured in manifest"
targetVersion: "MongoDB version captured during drill"
restoreTarget: isolated-lab-restore
requestedPointUtc: "2026-11-14T06:00:00Z"
actualRecoveredPointUtc: "from backup metadata"
checksumVerified: true
restoreExitCode: 0
collectionChecks: pass
indexChecks: pass
bsonTypeChecks: pass
businessInvariantChecks: pass
rbacChecks: pass
appSmokeTests: pass
observedRtoMinutes: 12
approval: "<responsible reviewer>"
```

Values above are illustrative. Never record `pass` before gathering actual verification evidence.

### 26.3. Verify Metadata Issues Too

A restore containing every document yet missing indexes will pass basic data checks while failing catastrophically under production query load. Verify both index definitions and critical query plans.

### 26.4. Rotate Drill Operators

So recovery knowledge does not live solely in one DBA's head, occasionally have another engineer execute the drill using the runbook. Whenever they get stuck, improve the documentation and access setup.

---

## 27. Recovering from Accidental Order Deletion: Best Approach

### 27.1. Scenario

At 10:12, a faulty deployment runs:

```javascript
db.orders.deleteMany({ status: "PAID" });
```

At 10:20, the team detects it and halts the offending writers.

### 27.2. Do Not Blindly Restore Over the Live Database

First:

- Determine the exact scope of deleted data.
- Preserve incident evidence.
- Record affected collections and IDs.
- Stop or throttle harmful writers per incident policy.
- Identify the latest clean restore point.
- Estimate collateral loss of a full cluster rollback (valid writes made between 10:12 and now).
- Use an **isolated restore** to inspect and extract pre-incident data.

### 27.3. Selective Repair Often Beats Full Rollback

If valid new orders arrived between 10:12 and 10:20, a full PITR rollback to 10:11 would erase those legitimate orders. Instead, restore the snapshot to an isolated environment and **reconcile/merge** affected documents per business rules with approvals and transactional safety.

### 27.4. Check Business Invariants

Restoring an order may touch:

- Payment captures at the gateway.
- Inventory deductions.
- Outbox events.
- Warehouse shipment fulfillment.

Never reinsert order documents into production while ignoring downstream state. Reconcile across systems.

### 27.5. Audit Trail and Idempotency

Log all restored IDs, old/new ID mappings, operator identity, timestamps, approvals, and rerun safety. Running the repair script twice must never create duplicate orders or payments.

---

## 28. Recovering from Ransomware or Credential Compromise

More severe than an accidental delete:

1. Revoke access for compromised credentials and identities immediately.
2. Isolate the affected environment and preserve forensic evidence.
3. Rotate credentials, TLS certificates, and KMS access per security policy.
4. Determine the last known clean timestamp before compromise.
5. Select an immutable/offsite backup untampered by attackers.
6. Restore onto **clean infrastructure**—never reuse uncleaned compromised hosts.
7. Audit database users/roles, application binaries, and infrastructure configs.
8. Validate data consistency, indexes/schemas, and audit logs.
9. Cut over only with formal approval.
10. Monitor closely for anomalies and complete the incident postmortem.

Never restore data while leaving exposed admin passwords unchanged.

---

## 29. Changing Backup Policies Safely

### 29.1. Before Modifying

- Confirm owners, RPO/RTO targets, and compliance constraints.
- Review storage costs and retention rules.
- Verify backup service permissions.
- Assess performance impact on primaries/secondaries.
- Review oplog window margins.
- Confirm a recent passing restore drill.

### 29.2. Controlled Rollout

- Version policy-as-code where possible.
- Validate changes in staging/test first.
- Monitor backup success and resource overhead.
- Verify the latest recoverable backup timestamp.
- Retain a known-good backup prior to changing policy.

### 29.3. After Modifying

- Execute a restore drill.
- Measure observed RTO.
- Verify alerting thresholds.
- Update operational runbooks.
- Document rollback steps if the change causes errors or excessive cost.

---

## 30. Daily Checklist

An operator or automated check should verify:

- [ ] MongoDB cluster is healthy with expected members and states.
- [ ] Latest scheduled backup job completed on time.
- [ ] Age of latest successful backup satisfies RPO policy.
- [ ] Checksums/metadata recorded and uploads completed.
- [ ] Backup size has no anomalous drop relative to baseline.
- [ ] No unexpected authorization failures on the backup service.
- [ ] No replication lag or oplog window alerts.
- [ ] CPU, memory, cache, disk, and connections within bounds.
- [ ] Slow-operation rates show no sudden spike.
- [ ] No index builds or schema migrations colliding with backup windows.
- [ ] Outbox/payment queues show no abnormal backlog.
- [ ] Backup storage destinations remain safely below quota.
- [ ] No credentials or secrets are nearing expiration.

### 30.1. Document Failures Rigorously

Any failed check needs an owner, timestamp, severity, evidence link, and next action. Never check boxes as "verified" without backing data.

---

## 31. Weekly Checklist

- [ ] Review backup retention compliance and offsite copies.
- [ ] Spot-check a random archive against its manifest checksum.
- [ ] Review backup error/retry logs and duration trends.
- [ ] Review oplog window margins and replication events.
- [ ] Inspect backup storage access logs.
- [ ] Audit newly created or modified user accounts and privileges.
- [ ] Verify application accounts have not drifted into excess privileges.
- [ ] Review index additions and storage growth.
- [ ] Review restore drill schedules and open findings.
- [ ] Confirm cloud/provider backup policies remain active.
- [ ] Review lifecycle tiers and storage cost of backup copies.
- [ ] Verify runbook links and on-call contacts.

### 31.1. Weekly Restore Policy

For critical systems, automate periodic test restores into an isolated environment (cadence driven by RPO/RTO and budget) and run canary queries. Still, never equate a green cron schedule with verified recoverability.

---

## 32. Monthly or Pre-Major-Release Checklist

- [ ] Conduct a full restore or PITR drill per risk profile.
- [ ] Measure actual RTO and compare against target SLA.
- [ ] Randomly select a different historical backup and test restoring it.
- [ ] Confirm archived encryption keys remain accessible.
- [ ] Review break-glass account usage and rotate credentials.
- [ ] Audit collection and database privilege grants.
- [ ] Remove accounts belonging to departed personnel or retired services.
- [ ] Review MongoDB Server, cluster, and Database Tools compatibility.
- [ ] Run application smoke tests against sanitized restored data.
- [ ] Compare data growth against capacity forecasts.
- [ ] Review index cardinality/storage and critical query plans.
- [ ] Audit permissions on automated and cross-account backups.
- [ ] Update incident escalation contacts, runbooks, and ownership records.

### 32.1. After Major Schema Migrations

If a migration changes BSON types, collection options, time series configs, indexes/collations, or FCV, perform a **backup/restore compatibility rehearsal** on the target version rather than testing CRUD alone.

---

## 33. Pre-Deploy and Schema Change Checklist

### 33.1. Before Deploy

- [ ] Valid, recent backup/snapshot exists.
- [ ] Exact pre-deploy backup timestamp recorded.
- [ ] Clear rollback strategy defined for app, schema, and data.
- [ ] Data migrations tested on staging with representative data.
- [ ] Migrations are idempotent or safely resumable.
- [ ] Capacity, locking, and index-build impact assessed.
- [ ] Migration user holds only minimum required privileges.
- [ ] API does not use a `root` account.
- [ ] Compatibility between old and new app versions verified.
- [ ] Monitoring thresholds and abort criteria established.

### 33.2. After Deploy

- [ ] Application API smoke tests pass.
- [ ] Data invariants remain intact.
- [ ] Index catalog and validation rules match expectations.
- [ ] No unexpected `Unauthorized` errors appear.
- [ ] Scheduled backup jobs continue succeeding.
- [ ] RPO recovery window remains unaffected.
- [ ] Query p95/p99 and write error rates stay healthy.
- [ ] Data growth, disk usage, and replication lag monitored.
- [ ] Change completion record archived.

---

## 34. Incident Recovery Checklist

### 34.1. Triage

- [ ] Log incident ID, owner, and severity.
- [ ] Pinpoint exact incident timeline in UTC.
- [ ] Scope affected namespaces and records.
- [ ] Preserve evidence/logs and stop ongoing damage.
- [ ] Identify backup sets and latest clean recoverable point.
- [ ] Select recovery approach: PITR, full restore, or selective repair.
- [ ] Verify backup checksums, decryption keys, and operator permissions.

### 34.2. Restore

- [ ] Confirm target is isolated, clean, and approved.
- [ ] Double-check commands do not target live source.
- [ ] Restore the verified backup, version, and namespaces.
- [ ] Avoid arbitrary `--drop` usage.
- [ ] Archive command logs, exit codes, and timestamps.
- [ ] Run document, index, and BSON type checks.
- [ ] Execute application smoke tests.
- [ ] Verify RBAC, secrets, and network policies.
- [ ] Record actual RTO and any data loss relative to RPO.

### 34.3. Cutover

- [ ] Obtain formal approval and notify affected teams.
- [ ] Switch application connections and traffic per runbook.
- [ ] Re-enable writers, consumers, and outbox workers safely.
- [ ] Prevent duplicate side effects on replay.
- [ ] Verify monitoring and alerting are active.
- [ ] Obtain business owner sign-off on restored state.
- [ ] Complete postmortem with lessons learned and follow-up tasks.

---

## 35. Protecting Credentials and Secrets

### 35.1. Avoid CLI Password Arguments Whenever Possible

Wrong:

```bash
mongodump --username=backup_agent --password=plaintext-password --uri="mongodb://host/db"
```

Command-line arguments leak through shell history, process listings (`ps`), and automation logs.

### 35.2. Use Interactive Prompts or Secret Injection

Depending on Database Tools version, omitting the password value prompts interactively or follows tool-specific options. For automation, use a secret manager or secure injection mechanism that keeps secrets out of CLI arguments and logs. Verify your exact tool version's behavior before deploying.

### 35.3. Rotation

- Application credentials.
- Backup service credentials.
- Restore / break-glass identities.
- KMS and decryption keys.
- TLS certificates.

Ensure key rotation never breaks scheduled backups or prevents decrypting older retained archives.

### 35.4. URI Encoding

When injecting passwords into connection strings, percent-encode reserved URL characters properly rather than concatenating raw strings and breaking URI parsing.

### 35.5. CI Boundaries

CI pipelines must run against disposable MongoDB instances with synthetic fixtures and never hold access to production backups. Whenever anonymized production data is strictly needed for testing, enforce formal sanitization and approval.

---

## 36. Least Privilege for Applications: Choosing the Right Roles

### 36.1. No One-Size-Fits-All "App" Role

Different services require distinct permissions:

```text
product-catalog-api:
  read products/categories

checkout-api:
  read products, update inventory, insert orders/outbox

reporting-service:
  read orders/payments, no update

outbox-publisher:
  find/update outbox, no access customers
```

### 36.2. Collection-Scoped Custom Roles

Illustrative checkout role (evaluate exact actions against actual API queries):

```javascript
const sales = db.getSiblingDB("sales_lab");

sales.createRole({
  role: "checkoutService",
  privileges: [
    {
      resource: { db: "sales_lab", collection: "products" },
      actions: ["find"]
    },
    {
      resource: { db: "sales_lab", collection: "inventory" },
      actions: ["find", "update"]
    },
    {
      resource: { db: "sales_lab", collection: "orders" },
      actions: ["find", "insert"]
    },
    {
      resource: { db: "sales_lab", collection: "outbox" },
      actions: ["insert"]
    }
  ],
  roles: []
});
```

This role cannot run `dropDatabase`, manage users, or dump other databases. Operations such as upserts, index builds, or `$out`/`$merge` aggregations may require extra actions—test real commands and grant only justified actions.

### 36.3. Do Not Guess That an App Only Needs `insert`

A checkout endpoint often checks `orders` by idempotency key before inserting. Without `find`, it fails with `Unauthorized` even though `insert` is granted. Run integration tests under the actual service identity instead of testing as admin and assuming permissions suffice.

### 36.4. Database RBAC Does Not Replace Business Authorization

A MongoDB role may let `checkoutService` read every order in `orders`, yet customer A must still be blocked from viewing customer B's orders. Tenant and user isolation belong in application authorization, scoped queries, audits, and security tests.

---

## 37. Verifying Access with a Privilege Test Matrix

| Account | Find `orders` | Insert `orders` | Delete `orders` | Find `customers` | Create user |
|---|---|---|---|---|---|
| `sales_reporter` (DB `read`) | Allowed | Denied | Denied | Allowed | Denied |
| `orders_reporter` (custom) | Allowed | Denied | Denied | Denied | Denied |
| `sales_app` (DB `readWrite`) | Allowed | Allowed | Typically allowed by role | Allowed | Denied (no `userAdmin`) |
| `backup_agent` | Per `backup` role | Do not assume | Unnecessary | Per `backup` role | Unnecessary |
| `restore_operator` | Per `restore` role | Depends on restore actions | Depends on restore actions | Not an app identity | Not granted by default |
| `lab_admin` (`root`) | Allowed | Allowed | Allowed | Allowed | Allowed |

This matrix illustrates baseline expectations and **never replaces checking effective privileges** via `connectionStatus` (`showPrivileges: true`) on your target server version.

### 37.1. Test Both Permitted and Denied Operations

Under each individual identity:

- Permitted operations pass.
- Forbidden operations return `Unauthorized`.
- Error logs expose zero secrets.
- No unexpected privileges leak via inherited roles.

### 37.2. Never Run Destructive Negative Tests in Production

If a "supposed-to-fail" `deleteMany({})` unexpectedly succeeds because of misconfigured roles, live data is gone. Execute write-denial tests solely against controlled disposable labs.

---

## 38. Operator Accountability and Action Auditing

An operational change record should capture:

```text
Change ID: CHG-2026-001
Actor: database-operations service account
Action: backup policy update / user grant / restore
Target: named environment and database
Approved by: change owner
Timestamp UTC: ...
Reason: ...
Before/after: ...
Validation evidence: ...
Rollback: ...
```

### 38.1. Database Audit Logs

Depending on deployment and edition, MongoDB provides security auditing for admin and access events. Configure log storage, retention, and privacy controls to comply with organizational policy.

### 38.2. Application Audits Differ from Operational Audits

- Application audit: who changed an order's status, when, and old/new values.
- Operational audit: who created a DB user, modified a role, restored a backup, or changed backup retention.

An `updatedBy` field on `orders` never substitutes for operational audit logs.

### 38.3. Backup Access Is a Security-Sensitive Event

Downloading a full backup can expose every customer and payment record at once. Log and alert on unusual backup downloads or copies.

---

## 39. When Restore Succeeds Yet the Application Still Fails

Example:

```text
mongorestore exit code 0
collections present
application still failing
```

Common culprits:

- App URI targets the wrong database or hostname.
- Missing or mismatched authentication DB and user definitions.
- App role missing required actions.
- Missing or broken indexes.
- Incompatible application schema version.
- App expects fields added in a later migration.
- Out-of-sync external payment references.
- Outbox consumers replaying non-idempotent events.
- Search indexes, caches, or reporting views not rebuilt.
- Missing TLS truststore or network allowlists.
- Mismatched read preference or replica topology.

### 39.1. Recovery Drills Must Include the Application

Never stop at document counts. Run smoke tests, privilege checks, worker readiness checks, and measure end-to-end RTO.

### 39.2. Do Not Unleash All Writers Immediately

After a restore, bring services online in a controlled sequence with idempotency and reconciliation active before processing backlogs.

---

## 40. Why Restoring Orders Does Not Restore Full Business State

An order typically spans:

```text
MongoDB order document
      │
      ├── Payment capture at gateway
      ├── Inventory movement
      ├── Warehouse shipment
      ├── Email/SMS confirmation
      └── Outbox → broker → consumers
```

A MongoDB backup does not back up external payment gateways, warehouses, or message brokers. Restoring a document never undoes external side effects already executed.

### 40.1. Design Reconciliation

- Query payment gateway statuses by payment ID.
- Check warehouse fulfillment states.
- Reconcile inventory snapshots and ledgers.
- Deduplicate outbox events.
- Record approved compensation or recovery adjustments.

### 40.2. Never Blindly Resend Messages After Restore

If restored outbox records revert to `processed: false`, workers could rebroadcast previously sent events. Enforce stable event IDs and consumer deduplication.

### 40.3. Point-in-Time Consistency Stops at System Boundaries

A MongoDB-consistent restore timestamp does not rewind external services to that exact instant. Recovery requires a cross-system business recovery plan.

---

## 41. Testing Upgrade Compatibility Through Backup and Restore

### 41.1. Before a Major Upgrade

- Record current MongoDB Server, FCV, and Database Tools versions.
- Verify backup compatibility with the target version.
- Check special collections (time series, encrypted, special indexes).
- Test restoring into an isolated instance running the target version.
- Run schema, index, RBAC, and business invariant checks.
- Benchmark critical queries.
- Confirm your rollback plan actually works.

### 41.2. Time Series and FCV Nuances

Replaying oplogs across certain FCV transitions involving time series format changes has restrictions and may be rejected by tools. Never rely on full dump + oplog as an automatic downgrade path without consulting release notes.

### 41.3. Backups Are Not a Binary Downgrade Mechanism

MongoDB does not guarantee data files or logical dumps can always restore onto older major versions. Test cross-version restores explicitly rather than assuming `mongorestore` handles arbitrary downgrades.

---

## 42. Exercise 1: Back Up `sales_lab`

1. Verify the running MongoDB instance and target namespace.
2. Check current collection document counts.
3. Generate `sales_lab.archive.gz` using `mongodump --db --archive --gzip`.
4. Record exit code, elapsed duration, and file size.
5. Compute its SHA-256 hash.
6. Record a manifest explicitly noting **no point-in-time consistency guarantee if writes occurred**.
7. Confirm the archive is outside any Git repository containing project code.

Question: if the API continued processing checkouts during the dump, can you guarantee `orders` and `inventory` match the same point in time?

---

## 43. Exercise 2: Isolated Restore

1. Prepare an empty target database `sales_lab_restore`.
2. Run `mongorestore --dryRun --verbose`.
3. Restore using `--nsFrom` and `--nsTo`.
4. Omit `--drop`.
5. Inspect `getCollectionNames()`.
6. Verify counts and sample IDs.
7. Verify index definitions.
8. Record observed restore duration.

Question: if the source receives new orders after the backup completed, why does a mismatch between `sourceNow` and `target` counts not prove the restore failed?

---

## 44. Exercise 3: Checksum and Integrity Verification

1. Compute SHA-256 before transferring the backup.
2. Copy the artifact to secure storage.
3. Recompute SHA-256 after download.
4. Compare both hashes.
5. Execute a real restore.
6. Verify indexes, BSON types, and business invariants.

Explain why a matching checksum alone does not guarantee the database will recover cleanly.

---

## 45. Exercise 4: Distinguishing RPO and RTO

A business sets targets:

```text
RPO 5 minutes
RTO 1 hour
```

Yet operations currently runs `mongodump` once daily at 02:00.

Tasks:

1. Explain why this fails the RPO requirement.
2. Propose a backup/PITR architecture.
3. Break down every component of RTO.
4. Design a restore drill.
5. Define backup-age alerting.
6. Propose a retention policy.

---

## 46. Exercise 5: Full Replica Set Backup

1. Use a self-managed replica set lab.
2. Run a full `mongodump --oplog --archive --gzip`.
3. Explain why `--db` cannot be used with `--oplog`.
4. Identify which oplog interval this dump contains.
5. Plan restoring into a clean disposable target.
6. Explain why `--oplogReplay` cannot combine with `--nsFrom`/`--nsTo`.
7. Explain why this alone does not provide a 7-day PITR window.

---

## 47. Exercise 6: Testing a Read-Only Role

In the RBAC lab:

1. Create `sales_reporter` with `read` on `sales_lab`.
2. Authenticate as that user.
3. Run `findOne` on `orders`: verify no `Unauthorized` error.
4. Attempt `insertOne` with a test marker: verify `Unauthorized` rejection.
5. Run `connectionStatus({showPrivileges:true})`.
6. Document granted actions per resource.
7. Confirm no reporting account uses `root`.

---

## 48. Exercise 7: Custom Collection Role

1. Create `ordersReader` granting `find` on `sales_lab.orders`.
2. Create user `orders_reporter`.
3. Verify reading `orders` succeeds.
4. Verify reading `customers` is denied.
5. Verify deleting from `orders` is denied.
6. Explain how this differs from database-wide `read`.
7. Determine what reporting queries might require additional actions.

---

## 49. Exercise 8: Backup and Restore Identities

1. Create separate `backup_agent` and `restore_operator` identities.
2. Verify their effective privileges.
3. Identify what privileges `mongodump` requires.
4. Identify what extra privileges restoring users/roles needs beyond ordinary data restores.
5. Describe the security risks of full dumps containing `admin`.
6. Write a break-glass and credential-rotation plan.
7. Design operations so `root` is never used routinely.

---

## 50. Exercise 9: Incident — Accidental Deletion of `PAID` Orders

A faulty deploy executes `deleteMany({status:"PAID"})` in production. A PITR window covers the time just before the delete, yet 300 valid orders arrived afterward.

1. Choose the restore point and target environment.
2. Explain why rolling production straight back would cause collateral loss.
3. Design a selective repair plan.
4. Reconcile payments, inventory, and outbox records.
5. Guarantee idempotency if repair scripts rerun.
6. Record evidence and approvals.

---

## 51. Exercise 10: Simulated Ransomware Recovery

1. Locate an immutable offsite backup.
2. Locate decryption keys.
3. Provision clean replacement infrastructure.
4. Rotate all credentials.
5. Restore and audit roles/users.
6. Validate data and business invariants.
7. Run application smoke tests and execute controlled cutover.
8. Record the incident timeline and observed RTO.

---

## 52. Exercise 11: Backups Across FCV Upgrades

1. Record current Server, FCV, and Database Tools versions.
2. Inventory any time series collections.
3. Check oplog replay limitations across format conversions.
4. Test restoring onto the target version in isolation.
5. Verify indexes, schemas, and roles.
6. Assess rollback feasibility.
7. Draft an upgrade checklist and backup window plan.

---

## 53. Exercise 12: Author an Operational SOP for Your Team

Draft a minimum Standard Operating Procedure covering:

- Daily backup verification.
- Weekly storage and access reviews.
- Monthly restore drills.
- Incident escalation and contacts.
- Approval gates for restore and cutover.
- Evidence recording template.
- Retention and key management.
- Recovery acceptance criteria.

Every item must assign an owner, measurement method, pass/fail threshold, and remediation action on failure.

---

## 54. Common Pitfalls and Troubleshooting Table

| Error / Symptom | Likely Cause | Investigation |
|---|---|---|
| `mongodump` authentication failed | Wrong user, password, or `authSource` | Verify connection options and user database |
| `mongodump` unauthorized | Backup role missing required actions | Inspect `connectionStatus` / `getUser` |
| Backup file unexpectedly tiny | Dumped wrong DB or aborted early | Check exit code, logs, and namespaces |
| Backup file exists yet corrupt | Partial archive or truncated transfer | Verify SHA-256 and test real restore |
| `--oplog` rejected | Combined with `--db` or not a full replica member | Check CLI flags and topology |
| `--oplogReplay` fails with `nsFrom` | Oplog replay does not support namespace renaming | Restore full dump to fresh deployment |
| Duplicate key during restore | Target already holds documents | Use an empty target instead of hasty `--drop` |
| Restored into live source by mistake | Wrong URI or namespace | Halt immediately and follow incident runbook |
| `--drop` wiped user accounts | `admin` database included in restore | Recover access via break-glass runbook |
| Counts match yet queries crawl | Missing indexes or collations | Check `getIndexes()` and `explain` |
| App cannot sign in post-restore | Users, roles, or `authSource` missing/mismatched | Verify RBAC definitions and secrets |
| App hits `Unauthorized` after restore | Missing effective privileges | Check `connectionStatus` and test service identity |
| Restored data misses recent writes | Stale backup point or RPO gap | Inspect timestamps and PITR window |
| `sourceNow` count differs from target | Source took new writes after backup | Compare against backup manifest timestamp |
| Desired PITR timestamp unavailable | Outside window, retention, or granularity | Review backup policy and actual bounds |
| Backup job timed out | Network bottleneck, disk saturation, or heavy load | Inspect logs, duration, and node metrics |
| Oplog window too small | High write volume or slow dump | Monitor oplog retention and disk capacity |
| Missing cluster-wide sharded backup | Misused `mongodump` via `mongos` | Adopt sharding-supported backup tooling |
| Role named read-only can delete | Inherited roles or excessive grants | Inspect effective privileges |
| Unauthenticated Docker RBAC test passes falsely | `--auth` not enabled | Use dedicated `--auth` RBAC lab container |
| Post-restore payment mismatch | MongoDB backup excludes external gateways | Run cross-system business reconciliation |
| Backups deleted alongside DB | Same failure domain or overly broad delete permissions | Enforce immutable offsite copies |
| Restore exceeds RTO target | Huge archive or slow index rebuilds | Benchmark in drills and size compute/IOPS |

---

## 55. Production Readiness Master Checklist

### 55.1. Backup and RPO/RTO

- [ ] RPO and RTO formally approved by business stakeholders.
- [ ] Backup strategy fits deployment topology and data volume.
- [ ] Latest successful backup timestamp tracked.
- [ ] Backup/continuous history covers required RPO.
- [ ] Retention, offsite copies, and immutability configured.
- [ ] Backup encryption and KMS keys tested for recoverability.
- [ ] Monitoring and alerting active on all backup jobs.
- [ ] `mongodump`/`mongorestore` versions tracked for compatibility.
- [ ] Replica sets are never treated as backups.

### 55.2. Restore and Verification

- [ ] Isolated restore target provisioned and documented.
- [ ] Restore runbook enforces URI and namespace verification.
- [ ] Checksum validation enforced before restores.
- [ ] Real restore drills executed regularly—never `dryRun` alone.
- [ ] Collection counts, sample IDs, and BSON types verified.
- [ ] Indexes, options, and schema validators verified.
- [ ] Business invariants verified.
- [ ] Application smoke tests pass under real service accounts.
- [ ] Observed RTO measured and logged.
- [ ] Recovery acceptance sign-off archived.

### 55.3. Access Control and Security

- [ ] Authentication enabled appropriately for the topology.
- [ ] Replica set internal auth and TLS properly configured.
- [ ] Applications never use `root`.
- [ ] Reporting accounts restricted to scoped read access.
- [ ] Backup and restore identities separated.
- [ ] Custom RBAC roles audited for exact actions and resources.
- [ ] Positive and negative privilege tests executed.
- [ ] Zero secrets or keys stored in Git or logs.
- [ ] Break-glass credentials secured and rotated.
- [ ] Access to backup storage audited.

### 55.4. Operations and Incident Readiness

- [ ] Daily, weekly, and monthly checklists assigned to owners.
- [ ] Pre-migration backups and rollback plans required before DDL/schema changes.
- [ ] Replication lag, oplog window, cache, and disk alerts monitored.
- [ ] Incident escalation paths and contacts current.
- [ ] Recovery decisions account for external downstream systems.
- [ ] Outbox and event replay pipelines enforce idempotency.
- [ ] Backup compatibility re-verified after upgrades.
- [ ] Restore drill findings tracked to closure.
- [ ] Postmortems conducted after real incidents.

---

## 56. Official References

Consult the references below against your active MongoDB Server, Database Tools, and deployment edition:

- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Manual — Back Up and Restore](https://www.mongodb.com/docs/manual/core/backups/)
- [MongoDB Manual — Deploy a Replica Set](https://www.mongodb.com/docs/manual/tutorial/deploy-replica-set/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Authentication](https://www.mongodb.com/docs/manual/core/authentication/)
- [MongoDB Manual — Role-Based Access Control](https://www.mongodb.com/docs/manual/core/authorization/)
- [MongoDB Manual — Built-In Roles](https://www.mongodb.com/docs/manual/reference/built-in-roles/)
- [MongoDB Manual — Create a User](https://www.mongodb.com/docs/manual/tutorial/create-users/)
- [MongoDB Manual — Create a Role](https://www.mongodb.com/docs/manual/tutorial/define-roles/)
- [MongoDB Manual — connectionStatus command](https://www.mongodb.com/docs/manual/reference/command/connectionStatus/)
- [MongoDB Manual — db.getUser()](https://www.mongodb.com/docs/manual/reference/method/db.getUser/)
- [MongoDB Manual — db.getUsers()](https://www.mongodb.com/docs/manual/reference/method/db.getUsers/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Query Explain](https://www.mongodb.com/docs/manual/reference/explain-results/)
- [MongoDB Atlas — Backup Overview](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
- [MongoDB Atlas — Point-in-Time Restore](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/)
- [MongoDB Atlas — Backup Guidance](https://www.mongodb.com/docs/atlas/architecture/current/backups/)

**Note:** `mongodump --oplog`, `--oplogReplay`, sharded backups, user/role restoration, FCV transitions, and Atlas PITR carry version, topology, and edition-specific constraints. Never run full production backup/restore commands without consulting matching documentation and holding approved maintenance authorization.

---

## 57. Summary

1. **A backup does not guarantee recovery:** even when files and checksums exist, you still need real restore drills verifying indexes, documents, schemas, permissions, and application smoke tests.
2. **RPO and RTO are business targets** that dictate backup frequency, retention, PITR architecture, and restore throughput. A single nightly dump cannot meet a minute-scale RPO.
3. **`mongodump --db --archive --gzip`** works well for single-database lab restores, yet does not capture a consistent point across collections receiving concurrent writes.
4. **`mongodump --oplog`** requires a full replica-set-member dump without `--db` or `--collection`. **`mongorestore --oplogReplay`** pairs with that full dump and disallows namespace filters or remapping.
5. **Sharded clusters** require dedicated cluster-consistent backup/restore mechanisms; never run an oplog dump through `mongos` assuming cluster-wide consistency.
6. **Least privilege** requires separating application, reporting, backup, restore, and administrator identities—verified via `connectionStatus` plus positive and negative tests on an authorization-enabled instance.
7. **Always rehearse restores on isolated targets**, avoiding hasty `--drop` flags and wrong URIs while validating business invariants, external system reconciliation, and worker idempotency before reopening writes.
8. **Daily, weekly, monthly, and incident checklists** turn backup and recovery from ad hoc commands into an auditable operational discipline with owners, evidence, and pass/fail thresholds.

**Final principle:** A well-operated MongoDB deployment does more than keep copies of data; it maintains **clear recovery points, least-privilege access control, backups isolated from the primary failure domain, rehearsed restore runbooks, and verifiable proof that applications can resume safely**.
