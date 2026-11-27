# mongodump, mongorestore, and Tool Compatibility Requirements in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Backup and Recovery

## 1. Why Must You Understand Both Tools and Versions Before Restoring?

An ordering system using MongoDB hits an incident: an employee accidentally drops a collection, a new deployment writes corrupted data, or the team needs a staging environment containing a production data copy sanitized per security policy. The operations team has a `backup.archive.gz` file created with `mongodump` and plans to run `mongorestore`.

The questions you must answer **before** running the command are:

1. Is the backup a **logical** copy or a physical snapshot? Was it consistent while writes were occurring?
2. Which **MongoDB Database Tools version** created the backup file?
3. Which MongoDB Server versions and **Feature Compatibility Version (FCV)** are running on the source and target?
4. Is the backup of the entire deployment, a single database, or a single collection? Does it include `oplog.bson`?
5. Is the source a standalone instance, a replica set, or a sharded cluster?
6. Was the archive created with `--gzip`? Does the target support the same metadata/index types?
7. Should the restore **drop existing collections with `--drop`** or preserve existing data?
8. Does the user have the appropriate `backup`/`restore` privileges? Does the connection use TLS?
9. Do you have a backup checksum, readback check, data verification, and rollback procedure?
10. Is the actual goal post-incident data recovery, data migration, or a **major version upgrade**? Those three goals require different procedures.

The tools follow this flow:

```text
          Source MongoDB
                │
           mongodump
                │
     ┌──────────┴───────────┐
     │                      │
BSON + metadata          archive
by directory           (optionally gzip)
     │                      │
     └──────────┬───────────┘
                │
       storage/verification
        checksum/retention
                │
          mongorestore
                │
          Target MongoDB
                │
       verify count/index/
     query/role/application
```

**Key takeaway:** `mongodump` and `mongorestore` are **logical backup/restore** tools; they do not automatically become a full disaster recovery solution, physical snapshot, point-in-time recovery, or MongoDB Server upgrade mechanism.

This lesson builds a safe mindset and workflow for backup/restore operations, accompanied by `mongosh` exercises, shell commands, and Java application workflows.

---

## 2. What Are MongoDB Database Tools?

**MongoDB Database Tools** are a suite of separately distributed command-line programs, including:

- `mongodump`: exports MongoDB data as BSON and metadata for restoration.
- `mongorestore`: loads data back from a BSON dump, archive, or standard input.
- `bsondump`: reads/converts BSON data to inspect it in human-readable text.
- `mongoexport` / `mongoimport`: exports/imports data in JSON or CSV format for data interchange.
- `mongostat`, `mongotop`: observe operational statistics.

Starting with MongoDB 4.4, Database Tools have been **released independently from MongoDB Server**, following the `100.x` version branch; the tools do not necessarily share the same version number as the server.

Illustrative example:

```text
MongoDB Server:         8.0.x
MongoDB Database Tools: 100.x.y
mongosh:                2.x
Java Sync Driver:       5.x
```

These four version lines are **not the same product**. They have their own compatibility matrices and release schedules.

### 2.1. Checking the Versions in Use

In a terminal on the machine where Database Tools are installed:

```bash
mongodump --version
mongorestore --version
bsondump --version
```

In `mongosh` connected to MongoDB Server:

```javascript
db.version();

db.adminCommand({ buildInfo: 1 });
```

To inspect the FCV if the account has permission:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

**Do not compare `mongodump 100.20.1` with `MongoDB Server 9.0` and conclude they are incompatible just because the numbers do not match.** Check the Server Compatibility table for your exact Database Tools release.

### 2.2. Downloading and Installing

Install MongoDB Database Tools from the package or distribution for your OS/architecture via the official pages:

- <https://www.mongodb.com/docs/database-tools/installation/>
- <https://www.mongodb.com/try/download/database-tools>

Installing MongoDB Server or `mongosh` **does not guarantee** that Database Tools are present on every system. Check `mongodump --version` instead of checking only `mongod --version`.

### 2.3. Version-Specific Documentation

Tools may add options, change behavior, or deprecate support across releases. For production commands:

1. Record the exact version of `mongodump`.
2. Record the exact version of `mongorestore`.
3. Read the documentation/release notes for that exact release.
4. Test against an isolated restore target.
5. Record the versions in the backup manifest.

Do not design automation based on documentation for a newer release while the host runs an older binary.

---

## 3. How Does Logical Backup Differ from Physical Backup?

### 3.1. Logical Backup

`mongodump` queries data from MongoDB and writes:

- BSON documents.
- Collection metadata.
- Index definitions and supported collection options.
- Users/roles information when dumped with the appropriate scope and options.
- Oplog entries when eligible to use `--oplog`.

Benefits:

- Can select specific databases/collections/namespaces.
- Easy to clone a subset of data into a lab.
- Fairly independent of the underlying storage engine file layout.
- Supports archives and gzip.

Limitations:

- Can place significant CPU/I/O/network load on the source.
- Restore must parse BSON, build collections/indexes, and execute writes.
- Takes a long time for multi-TB datasets.
- Not a consistent snapshot by default when data is changing concurrently.
- Not a complete copy of OS configuration, secrets, network policies, or cluster topology.

### 3.2. Physical Backup/Snapshot

A physical snapshot typically copies the state of files/volumes using a mechanism that preserves consistency for the storage engine/backup service.

Benefits can include:

- Faster restore for large datasets under certain workloads.
- Suitable when the backup engine properly manages transaction/storage consistency.
- Can integrate with point-in-time recovery or incremental backups.

Trade-offs: depends on snapshot technology, topology, filesystem, journal, encryption, and supported recovery procedures.

**Never copy a running WiredTiger directory with a standard file copy command and treat it as a valid backup.** Follow MongoDB-supported snapshot/backup guides and tools.

### 3.3. The Goal Determines the Tool

| Purpose | Tool/Strategy to Consider |
|---|---|
| Clone a small database to a lab | `mongodump` + `mongorestore` |
| Back up one collection to test a migration | Partial logical dump |
| Consistently restore an actively written replica set | Full dump + `--oplog`/`--oplogReplay` if conditions are met |
| Back up an actively written sharded cluster | Cluster-aware procedure or managed backup; not just `--oplog` |
| RPO measured in minutes/seconds | Appropriate PITR/continuous backup |
| Restore tens of TB with a low RTO | Evaluate snapshot/managed backup |
| Major MongoDB Server upgrade | Supported upgrade procedure; do not assume dump/restore is the upgrade path |
| CSV/JSON data interchange | `mongoexport`/`mongoimport` if appropriate, not a replacement for BSON backup |

---

## 4. Output Formats of mongodump

### 4.1. Directory Dump

A basic lab command:

```bash
mongodump --host 127.0.0.1 --port 27017 --db inventory_lab --out ./backups/inventory-001
```

Typical structure:

```text
backups/
└── inventory-001/
    └── inventory_lab/
        ├── products.bson
        ├── products.metadata.json
        ├── orders.bson
        ├── orders.metadata.json
        └── ...
```

- `products.bson` contains BSON documents.
- `products.metadata.json` contains metadata needed to recreate the collection/indexes where supported.
- Metadata files are not a JSON export of all documents.

Exact structure and contents may vary by collection type, namespace, or tool version.

### 4.2. Archive Dump

```bash
mongodump --host 127.0.0.1 --port 27017 --db inventory_lab --archive=./backups/inventory.archive
```

An archive bundles the dump into a single file for convenient transport/storage. It is **not a tar or zip file**; `mongorestore --archive` understands the archive format created by `mongodump`.

Do not run:

```text
unzip inventory.archive
```

and expect to get BSON files in ZIP format.

### 4.3. Compressing with gzip

For an archive:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --archive=./backups/inventory.archive.gz --gzip
```

Corresponding restore:

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive.gz --gzip
```

For a directory dump:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --out ./backups/inventory-gz --gzip
```

Restore:

```bash
mongorestore --host 127.0.0.1 --gzip ./backups/inventory-gz
```

**You must pass `--gzip` when the input was actually created with `--gzip`.** Renaming a file extension to `.gz` does not turn it into a gzip file.

### 4.4. Do Not Mix Conflicting Output Flags

With `mongodump`, do not combine `--archive=<file>` and `--out=<directory>` in the same command.

Choose **one format** per backup job, record it clearly in the manifest, and use the matching parameter pair when restoring.

### 4.5. Archive via stdin/stdout

MongoDB supports:

```bash
mongodump --archive | mongorestore --archive
```

but this is a direct stream transfer between two processes; it **does not create a retained backup** unless you also write and preserve the archive.

Warnings:

- In shells that treat pipelines as text streams rather than byte streams, a binary archive can be corrupted.
- In particular, avoid blindly using this binary pipeline pattern in **Windows PowerShell 5.1** without a verified binary-safe mechanism.
- The pipe can break; check the exit codes of both processes.
- If auditing/retention is required, prefer writing an archive file, computing a checksum, and restoring from the file.

---

## 5. mongodump: Scope Options

### 5.1. Dump the Entire Connected Instance

```bash
mongodump --host 127.0.0.1 --port 27017 --out ./backups/instance-001
```

Which scopes and system collections the tool exports depends on privileges, MongoDB topology, and options. Do not interpret "full dump" as a snapshot of all network configurations, keyfiles, certificates, storage engine settings, or OS configuration.

### 5.2. Dump a Single Database

```bash
mongodump --host 127.0.0.1 --db inventory_lab --out ./backups/inventory-001
```

Suitable for cloning/backing up one database in a lab or when the application has a controlled write-freeze/synchronization window.

### 5.3. Dump a Single Collection

```bash
mongodump --host 127.0.0.1 --db inventory_lab --collection products --out ./backups/products-001
```

If the collection references other collections, backing up only one collection may be insufficient for business recovery.

Example:

```text
orders.customerId → customers._id
orders.items[].sku → products.sku
```

Dumping only `orders` can leave the restored data missing related records.

### 5.4. Filtering with a Query

On supported versions:

```bash
mongodump --host 127.0.0.1 --db inventory_lab --collection orders --query='{"status":"CLOSED"}' --out ./backups/closed-orders
```

Rules:

- `--query` applies to a specific collection.
- The query must be valid JSON as required by the tool.
- On Windows shells, quoting rules differ from Bash; consider `--queryFile` to avoid escaping errors.
- A partial dump does not automatically preserve referential relationships or cross-collection consistency.

**Never treat a selective query dump as a complete backup of the entire database.**

### 5.5. Access Limits and Data Sensitivity

A dump may contain:

- Customer information.
- Financial/business data.
- PII.
- Application tokens or secrets if stored in MongoDB.
- User/role metadata in certain backup scopes.

Therefore, backups must be encrypted at rest, access-controlled, audited, governed by retention policies, and purged upon expiration.

`--gzip` is only **compression**, not **encryption**.

---

## 6. Connecting with Authentication and TLS

### 6.1. SCRAM and the Authentication Database

A user with the `backup` role created in `admin` can be used with Database Tools:

```bash
mongodump \
  --host mongo1.example.internal \
  --port 27017 \
  --username backup_operator \
  --authenticationDatabase admin \
  --password \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

Passing `--password` without a secret prompts interactively for a password on supported tool versions. In production automation, prefer `--config` with strict permissions or proper secret injection rather than exposing passwords in process arguments.

If the user is created in `admin` while dumping the `inventory_lab` database:

```text
--authenticationDatabase admin
--db inventory_lab
```

that is a valid configuration. **The authentication database does not have to match the database being dumped.**

### 6.2. Connection URI

```bash
mongodump \
  --uri="mongodb://mongo1.example.internal:27017/?authSource=admin&tls=true" \
  --username backup_operator \
  --password \
  --archive=./backups/full.archive.gz \
  --gzip
```

Avoid putting passwords directly in the URI or on the command line. If a URI contains a username/password, properly URL-encode special characters and control exposure via shell history/process listings.

Do not mix a URI and flags with conflicting values for `authSource`, `host`, `TLS`, or `username`; the tool may error rather than silently choosing one.

### 6.3. TLS and CA

Tools can use `tls=true` in the connection string or the corresponding TLS options for the release, along with a CA file if needed.

Illustrative example:

```bash
mongodump \
  --host mongo1.example.internal \
  --port 27017 \
  --ssl \
  --sslCAFile /secure/certs/root-ca.pem \
  --username backup_operator \
  --authenticationDatabase admin \
  --password \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz
```

TLS flag names and aliases can vary across versions. Check `mongodump --help` for the exact binary in use.

**Never use `--sslAllowInvalidCertificates` or mechanisms that skip hostname verification in production just to get a backup job to run.** Instead, fix the CA trust, certificate chain, or DNS/SAN.

### 6.4. Config File Containing Secrets

Recent Database Tools versions support `--config=<yaml>` to pass sensitive options such as a password or URI, avoiding exposure on the process command line.

**Illustrative structure — never commit real secrets**:

```yaml
uri: mongodb://mongo1.example.internal:27017/?authSource=admin&tls=true
password: REPLACE_BY_SECRET_IN_SECURE_ENVIRONMENT
```

Restrict permissions strictly to the backup service account, delete according to policy, and never commit the file to a repository.

On Windows, apply ACLs; on Linux/Unix, set appropriate owner and mode. Never treat a YAML file containing a password as safe merely because it sits outside the URI.

### 6.5. Roles for Backup and Restore

MongoDB provides built-in roles such as:

- `backup`: read privileges required for backups within the appropriate scope.
- `restore`: restore privileges within the appropriate scope.

However, a specific workflow may require additional privileges:

- Reading user/role metadata.
- Restoring indexes and collection options.
- Creating/dropping collections.
- Replaying the oplog.
- Operating on system or special namespaces.

In practice, verify the **required access** of `mongodump` and `mongorestore` for the exact job scope.

Do not grant `root` to automation by default. Separate backup-only and restore-only accounts, and test job execution in a lab.

---

## 7. mongorestore: Understanding Behavior Before Running

`mongorestore` reads a BSON dump/metadata/archive and writes to the target deployment.

### 7.1. Restoring a Directory Dump

Suppose `./backups/inventory-001` contains the `inventory_lab` subdirectory:

```bash
mongorestore --host 127.0.0.1 ./backups/inventory-001
```

If the target database/collection does not exist, the tool creates the necessary namespaces where supported.

### 7.2. Restoring an Archive

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive
```

If the file is gzipped:

```bash
mongorestore --host 127.0.0.1 --archive=./backups/inventory.archive.gz --gzip
```

### 7.3. Restoring Without --drop

By default, `mongorestore` **does not drop the target collection first** just because you are restoring from a backup.

If the collection already contains documents with matching `_id` values:

- Duplicate key errors may occur.
- Some documents may be inserted while others fail.
- The outcome is not an automatic "replace entire database" operation.
- Do not expect the tool to merge/update by business key automatically.

In current versions, `mongorestore` may **continue** by default after duplicate key or document validation errors. To stop on such errors, consider `--stopOnError`.

### 7.4. Restoring with --drop

```bash
mongorestore --host 127.0.0.1 --drop ./backups/inventory-001
```

`--drop` means: **before restoring a collection present in the dump, drop the corresponding collection on the target**.

Key points:

- Existing data in the target collection is deleted if that collection is part of the restore scope.
- Collections **not present in the dump** are not automatically dropped.
- It is not a command to drop the entire database/cluster.
- Indexes/options are recreated per metadata, supported capabilities, and flags.
- If the restore fails midway, a dropped collection may end up only partially restored.

**Never run `--drop` on production without an approved plan and explicit confirmation of the target namespaces.**

### 7.5. Special Warning When Restoring admin

When a restore includes the `admin` database and uses `--drop`, the process can replace existing user credentials and roles. This may cause the account running the restore to **lose privileges or fail authentication** mid-restore.

This is a sensitive operation requiring a dedicated runbook:

- Identify which users/roles are inside the backup.
- Ensure a way to continue authenticating after drop/recreate.
- Test in an isolated environment.
- Have a recovery path following security procedures.
- Never blindly run `mongorestore --drop` across an entire deployment.

### 7.6. --stopOnError

```bash
mongorestore --host 127.0.0.1 --stopOnError ./backups/inventory-001
```

This flag forces the restore to halt upon encountering insert/validation errors handled by the tool's rules, rather than continuing and leaving some records missing.

Note: `--stopOnError` does not make the entire restore an **atomic transaction**. Writes already committed before the error may remain on the target.

### 7.7. --dryRun

On supported Database Tools versions:

```bash
mongorestore --host 127.0.0.1 --dryRun --verbose ./backups/inventory-001
```

`--dryRun` previews the restore plan/summary **without actually importing data**. It is useful before the real run, but it does not prove that:

- Every BSON file is completely valid.
- All indexes will build cleanly.
- The target has enough disk/RAM.
- Document validation/permissions will allow every document.
- The restore will hit no runtime errors.

**A dry run does not replace an actual test restore into an isolated target.**

---

## 8. Namespaces: Selective Restore and Database Renaming

### 8.1. What Is a Namespace?

A namespace typically has the form:

```text
<database>.<collection>
```

Examples:

```text
inventory_lab.products
inventory_lab.orders
commerce.customers
```

When restoring from a directory/archive, use these options:

- `--nsInclude`: restore only matching namespaces.
- `--nsExclude`: skip matching namespaces.
- `--nsFrom`/`--nsTo`: rename namespaces during restore.

The `--db` and `--collection` flags when restoring from a directory/archive are documented as **deprecated** in Database Tools for this context; they still have use cases when restoring from a single BSON file.

### 8.2. Restoring a Single Collection

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.products"
```

Only `inventory_lab.products` is selected via the namespace pattern. There is no need to split the archive file manually.

### 8.3. Restoring a Single Database

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/instance.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.*"
```

The wildcard pattern selects all collections in the database.

### 8.4. Restoring to a New Database

A safe way to verify a backup is restoring it into a staging database:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsFrom="inventory_lab.*" \
  --nsTo="inventory_restore_test.*" \
  --stopOnError
```

This example maps:

```text
inventory_lab.products
    ↓
inventory_restore_test.products

inventory_lab.orders
    ↓
inventory_restore_test.orders
```

**Do not use the same namespace name if you intend to preserve the running source database.**

### 8.5. Restoring One Collection Under a Different Name

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsInclude="inventory_lab.products" \
  --nsFrom="inventory_lab.products" \
  --nsTo="inventory_restore_test.products_copy"
```

Depending on the dump and namespace rules, check with a dry-run/test restore to confirm the mapping behaves as expected.

### 8.6. Precedence of Include/Exclude

If you pass both:

```text
--nsInclude="inventory_lab.*"
--nsExclude="inventory_lab.sensitive"
```

the `--nsExclude` pattern excludes matching namespaces even when `--nsInclude` also matches them.

### 8.7. Watch Out for Shell Wildcards

In Bash and PowerShell, `*` and `$` can have special meaning to the shell. Quote namespace patterns appropriately for your shell.

In Bash:

```bash
--nsInclude='inventory_lab.*'
```

In PowerShell, use proper quoting so the shell does not expand wildcards into filenames.

---

## 9. Consistent Backups While MongoDB Receives Writes: The Snapshot Problem

### 9.1. Why Can a Plain Dump Be Inconsistent?

Suppose an application has two collections:

```text
orders:    customer orders
payments:  payment statuses
```

While `mongodump` is reading `orders`, the application updates an order. Later, while reading `payments`, the application writes a payment.

Because the dump reads collections at different points in time, the copy may contain:

- An order as of time T1.
- A payment as of time T2.
- State that does not correspond to any single logical point in time.

Therefore, a dump taken while writes are occurring **is not by default a consistent point-in-time snapshot**.

### 9.2. Solutions

- Pause/freeze writes within a controlled window.
- Use `--oplog` for a full dump of a **replica set member** when conditions are met.
- Use a snapshot/managed backup with topology-appropriate consistency guarantees.
- For a sharded cluster, use a cluster-aware backup procedure rather than mechanically dumping a single node.

### 9.3. Define RPO and RTO

- **RPO – Recovery Point Objective:** maximum data loss measured in time.
- **RTO – Recovery Time Objective:** how quickly the service must be restored.

Example:

```text
Nightly backup at 02:00
Incident occurs at 17:30
→ With only the 02:00 full dump, actual RPO
   can be nearly 15 hours 30 minutes.

Restoring 200 GB takes 2 hours
→ If the application must return within 15 minutes,
   this strategy fails RTO.
```

These numbers are illustrative only. You must measure restore times empirically based on data size, indexes, throughput, and target infrastructure.

---

## 10. mongodump --oplog on a Replica Set

MongoDB supports:

```bash
mongodump --oplog --out ./backups/rs-full-001
```

when connected to a **replica set member** to create a full dump under supported conditions.

During the dump, the tool records the oplog entries needed for replay, allowing the restore to reflect a consistent point within the feature's scope.

### 10.1. What Is the Oplog?

The **oplog** is the replication operations log used by replica set members to synchronize writes.

Inside the backup directory, `mongodump --oplog` can write:

```text
backups/
└── rs-full-001/
    ├── admin/
    ├── commerce/
    ├── inventory_lab/
    ├── ...
    └── oplog.bson
```

When dumping to an archive, the oplog entries are stored inside the archive.

**The `mongodump` oplog is not simply a raw copy of all of `local.oplog.rs`**; the tool collects entries needed to restore to a consistent point.

### 10.2. Restoring with --oplogReplay

```bash
mongorestore \
  --host 127.0.0.1 \
  --oplogReplay \
  ./backups/rs-full-001
```

With an archive:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/rs-full.archive.gz \
  --gzip \
  --oplogReplay
```

**Run these commands only on an isolated target prepared for a full deployment restore.** Be especially cautious with users/roles and `--drop` when `admin` is included in the dump.

### 10.3. --oplog Only Works for Eligible Full Dumps

Per current Database Tools documentation, `mongodump --oplog` requires:

- The source is a replica set member maintaining an oplog.
- A **full dump** of the member.

It cannot be combined with scope-limiting flags such as:

- `--db`.
- `--collection`.
- `--query`.
- `--dumpDbUsersAndRoles`.

**Invalid** example:

```bash
mongodump --db commerce --oplog --out ./backups/invalid
```

Do not assume `--oplog` automatically guarantees consistency for a selective collection dump.

### 10.4. mongorestore --oplogReplay Also Has Scope Restrictions

For a full replica set dump with an oplog, do not combine `--oplogReplay` with namespace filtering/remapping flags such as:

- `--nsInclude`.
- `--nsExclude`.
- `--nsFrom`.
- `--nsTo`.
- `--db`.
- `--collection`.

This is especially important because many people want **full dump + oplogReplay + rename database**. That is **not** a supported workflow by combining all options in one command.

If the goal is simply cloning one database to another name, create a selective backup during an appropriate maintenance window or via a separate snapshot/consistency strategy, then restore with namespace mapping.

### 10.5. Limitations Remain Even With the Oplog

`mongodump --oplog` cannot handle every concurrent change type.

Operations such as:

- `renameCollection`.
- Aggregation with `$out`.
- Certain modifications to users/roles/privileges.
- Certain cluster-wide settings changes.

can cause a full dump with oplog to fail per documentation.

The oplog window must be long enough to cover the dump duration, and the source must have sufficient resources. If needed oplog entries roll off or unsupported changes occur, the job fails to meet the consistent backup goal.

### 10.6. Oplog Replay Is Not Arbitrary PITR

`mongorestore` offers `--oplogLimit` for specific scenarios, but using the wrong cutoff or forcing incompatible entries can cause inconsistency or data corruption.

Do not treat `--oplogReplay` as a continuous point-in-time recovery solution equivalent to Atlas PITR/backup services.

### 10.7. Compatibility Warning Regarding Time Series and FCV

In MongoDB Server 9.0, changing FCV between 8.x and 9.0 can trigger **time-series bucket format conversion**.

MongoDB documentation warns that `mongorestore --oplogReplay` cannot replay an oplog range spanning this format conversion. Newer Database Tools releases added checks to prevent creating unrestorable dumps in affected scenarios.

Therefore, **do not run `mongodump --oplog` across such an FCV transition/format conversion**. Freeze/coordinate backups and upgrades according to the version-specific runbook.

---

## 11. Standalone, Replica Set, and Sharded Cluster: Choosing the Right Procedure

| Source | Standard mongodump | --oplog | What to Watch Out For |
|---|---|---|---|
| Standalone | Usable | No, no replica set oplog | Stop writes or choose another consistency strategy |
| Replica set member | Yes | Supported for eligible full dumps | Check oplog window/DDL/FCV |
| Replica set via seed list | Yes | Must connect appropriately to a member with an oplog | Understand read preference and topology |
| Sharded cluster via mongos | Has documented dump workflows | No cluster-consistent `--oplog` via mongos | Coordination/balancer/writes/metadata |
| Atlas managed deployment | Usable within service-allowed scope | Depends on topology and connection path | Consider Atlas Backup/PITR |

### 11.1. Should You Dump from a Secondary?

Dumping from a secondary can offload some reads from the primary, but:

- The secondary still incurs CPU/I/O/disk/network load.
- Read consistency/replication lag must be understood.
- The backup may lag behind the primary's state.
- Required oplog entries must still exist.
- Topology failover can interrupt the session.

Do not assume "the secondary isn't serving users so we can dump it without limits." Capacity planning and monitoring are required.

### 11.2. Sharded Cluster: The mongos --oplog Trap

MongoDB documentation explicitly states that `--oplog` **does not provide cluster-wide consistency benefits when dumping through `mongos`**, and should not be used to back up an entire sharded cluster.

Why?

- Shards have independent oplogs and transaction histories.
- Chunks can migrate.
- Sharding configuration metadata can change.
- Multi-shard writes require a consistent point across all components.

A collection of per-shard dumps **does not automatically** form a cluster-wide coordinated snapshot.

### 11.3. Procedures Require Cluster Awareness

For a self-managed sharded cluster, read the official documentation carefully:

- Back Up a Self-Managed Sharded Cluster with a Database Dump.
- Procedures covering the balancer, writes, snapshot windows, and metadata.
- Operation ordering, cluster state, backup privileges, and restore verification.

If uncertain, choose a managed backup/backup solution that natively supports cluster consistency rather than scripting parallel shell commands across shards.

### 11.4. Atlas Backup and mongodump

Atlas provides snapshot/continuous backup services depending on tier and features. For DR or low RPO goals, prioritize evaluating Atlas Backup/PITR supported by your cluster plan.

Using `mongodump` to export a collection or seed an environment can be appropriate, but do not assume it is the optimal DR strategy for Atlas production.

---

## 12. Tool Compatibility: Three Dimensions to Verify

This is the core section of the lesson.

### 12.1. Dimension 1: Database Tools and MongoDB Server

Each Database Tools release lists supported server versions. For example, Database Tools `100.20.1` documentation lists support for MongoDB Server releases from `4.2` through newer releases such as `8.x` and `9.0` per its specific compatibility list.

That does **not** imply:

- Every `100.x` Database Tools release can connect to every MongoDB Server.
- If a tool version can connect, every restore operation is automatically compatible.
- A newer tool version always supports restoring metadata from a newer server source to a very old destination.
- Using v100 tools removes the need to check server features/FCV.

**Mandatory step:** check the compatibility matrix for the **exact tool binary** you are running.

### 12.2. Dimension 2: Source Server and Target Server

`mongodump/mongorestore` documentation emphasizes that a full restore requires **major version** or **Feature Compatibility Version (FCV)** compatibility between source and target.

Reasons:

- BSON document representation may use server-version-specific features.
- Index options and collection metadata can change.
- UUIDs, validators, and time-series collection options can change.
- Oplog entries have semantics/version constraints.
- Newer features may be rejected by an older server.

**Safest approach:** test-restore into a server with the same major version and matching FCV as the source, then follow the official upgrade procedure if you need a newer version.

### 12.3. Dimension 3: mongodump and mongorestore

MongoDB docs recommend using **the same Database Tools version for both steps**.

Example:

```text
mongodump:    100.20.1
mongorestore: 100.20.1
```

Dumping with an older release and restoring with a newer one may work for much data, but if dump/archive formats or metadata handling changed, the process can fail or load data incorrectly.

Therefore, record the binary versions in the backup manifest alongside the archive.

### 12.4. Distinguishing BSON Data from Metadata/Archive/Oplog

This is a critical distinction.

MongoDB documentation distinguishes:

- **BSON data files** may have some ability to restore from an older source to a newer server.
- **Metadata, archive, and oplog replay files** do not carry the same cross-version guarantees.

For instance, restoring BSON documents into a newer deployment **is not the recommended path to upgrade MongoDB**, and does not guarantee that index definitions, collection options, user metadata, or oplogs can be safely converted in the same way.

**Do not infer from "documents inserted successfully" that "production backup/restore is fully compatible."**

### 12.5. Reference Version Matrix

| Scenario | Assessment |
|---|---|
| Dump/restore with the same Database Tools version; source/target servers on same version/FCV | Clearest compatible path |
| Older source server, newer target server | Must check upgrade path, metadata/index features, and docs; do not treat dump/restore as a standard upgrade |
| Newer source server, older target server | Risk of unsupported features, BSON, metadata, and indexes; not valid by default |
| Same server versions but different dump/restore tool versions | Format mismatch possible; prefer matching tool versions |
| Moving an archive from a different major/FCV to target | Lacks the same guarantees as BSON-only restore |
| Replaying oplog across an FCV/time-series format conversion | May be unsupported and fail |
| Target is a sharded cluster, dump has standalone/replica oplog | Do not use `--oplogReplay` directly through mongos |
| Source collection uses new features unsupported on target | Restore may fail when creating metadata/indexes/collections |

### 12.6. FCV Is Not the Server Binary Version

Suppose:

```text
Server binary: 9.0
FCV:           8.0
```

when an upgrade is in its compatibility stage.

FCV controls certain compatibility-related capabilities and formats, but it does not turn a 9.0 server into an 8.0 server in every respect. **Do not look solely at FCV while ignoring server binaries, tool versions, and feature usage.**

### 12.7. Recording Versions in the Manifest

Example:

```yaml
backupId: 2026-11-14T02-00Z-inventory
source:
  topology: replicaSet
  serverVersion: "example-server-version"
  featureCompatibilityVersion: "example-fcv"
tools:
  mongodump: "100.x.y"
  plannedMongorestore: "100.x.y"
format:
  kind: archive
  gzip: true
  includeOplog: false
scope:
  databases:
    - inventory_lab
file:
  path: inventory.archive.gz
  sha256: "FILL_WITH_REAL_CHECKSUM"
createdAt: "2026-11-14T02:00:00Z"
```

This metadata supports backup governance and compatibility; it does not need to live inside the BSON archive. Store the manifest alongside the backup with integrity controls.

---

## 13. Data Types and Collection Metadata During Restore

### 13.1. BSON Preserves Types That JSON/CSV Can Lose

MongoDB BSON supports types such as:

- ObjectId.
- BSON Date.
- Decimal128.
- Binary.
- Timestamp.
- Arrays/embedded documents.
- GeoJSON objects and many application types.

A logical BSON dump is much better suited for MongoDB backup/restore than using CSV as a general-purpose data copy.

### 13.2. Why Doesn't mongoexport/mongoimport Replace mongodump?

`mongoexport` converts data to JSON/CSV for interchange. Conversely, `mongodump` writes BSON and metadata for restoration.

Using export/import can:

- Lose or require remapping certain types.
- Fail to preserve index definitions/collection options.
- Omit full users/roles metadata.
- Lack an equivalent `--oplog` mechanism for consistent dumps.
- Require handling Extended JSON formats on round-trips.

Never treat a CSV file as a "complete production backup" just because it has the same row count.

### 13.3. Index Definitions Can Be Recreated

A dump directory can contain `collection.metadata.json` with index specs. `mongorestore` generally attempts to recreate dumped indexes/options unless skipped via flags.

Issues that can arise:

- Unsupported index keys/options on the target.
- Unique index build failure due to duplicate data.
- Different collation/schema restrictions.
- Deprecated or changed index features.
- Disk/cache pressure when building large indexes.
- Index format/feature compatibility mismatches.

Do not compare only document counts; check `getIndexes()` and query `explain` after restoring.

### 13.4. Intentionally Skipping Index/Option Restoration

Available flags:

```text
--noIndexRestore
--noOptionsRestore
```

These can be useful for lab migrations when you only want raw data, but carry trade-offs:

- Skipping indexes alters query performance and uniqueness constraints.
- Skipping collection options can alter validation, collation, capped behavior, or other properties.
- Certain special collection types should not be restored without their metadata.

**Never use these flags as a "fix for every restore error" without understanding whether the target data remains equivalent to the source.**

### 13.5. Time Series Collections

Time-series collections have bucket metadata and version-specific constraints. Across server major/FCV boundaries, never assume raw BSON and metadata are unconditionally portable across all versions.

Pay special attention to:

- `timeField` and `metaField`.
- Bucket granularity/span.
- Index support.
- TTL.
- Oplog replay across format conversions.
- Metadata/options supported by the target server.

### 13.6. Views and Collection Options

Views are query definitions, not regular document-storing collections. Restoration must account for view metadata and dependencies on underlying source collections.

A view can fail if:

- The underlying collection has not been restored yet.
- Aggregation operators are unsupported on the target version.
- Collation/namespace mappings differ.
- Application permissions are misaligned.

Therefore, verify both views and application queries.

### 13.7. TTL After Restore

If a backup includes a collection with a TTL index, restored historical data may **be deleted shortly after the TTL monitor runs** if documents are already past the expiration threshold.

This may be correct behavior in production, yet undesirable in staging when testing historical data.

Never disable TTL in production without reviewing retention/legal requirements; if a lab needs different retention, configure a separate environment and indexes and document the deviation.

---

## 14. Users, Roles, and Authentication: A Common Pitfall in Restores

### 14.1. Dumping One Database Does Not Back Up All Users/Roles by Default

Users belong to their authentication database. When dumping a single database, do not assume the dump file contains all cluster-wide users/roles.

Database Tools provide related options:

- `--dumpDbUsersAndRoles` when dumping a database within supported scope.
- `--restoreDbUsersAndRoles` when restoring from a matching dump.

Eligibility for these options depends on `--db` scope and tool version.

### 14.2. Restoring admin Requires Caution for Deployment-Wide Users/Roles

If a backup includes the `admin` database, `mongorestore --drop` can overwrite user credentials. If the account executing the restore gets overwritten or loses authentication, the job can fail midway.

Before a full restore:

1. Inspect the users/roles scope inside the dump.
2. Verify which account can continue authenticating after replacement.
3. Prepare an appropriate rescue/recovery procedure.
4. Never test directly against production.
5. Verify privileges/roles after restore.

### 14.3. backup/restore Roles Do Not Grant Every Privilege by Default

A backup operator typically only needs to read authorized sources and required metadata.

A restore operator may need actions such as:

- Create/drop collections.
- Insert documents.
- Build indexes.
- Apply collection options.
- Restore users/roles.
- Apply oplog operations.

Grant privileges per the **required access** of your tool version and runbook, rather than assigning `root` to a generic service account by default.

### 14.4. AuthSource Differs from the Database Being Dumped

Example:

```text
--username backup_operator
--authenticationDatabase admin
--db commerce
```

means the user authenticates against `admin` and reads `commerce` using its granted privileges.

If you change `--authenticationDatabase commerce` without a matching user there, the tool can fail with authentication failed even if the password is correct for the user in `admin`.

---

## 15. Performance: Cost of mongodump on the Source

### 15.1. How Does mongodump Generate Load?

A logical dump requires reading data, serializing BSON, and writing to disk/network. Depending on workload:

- CPU increases from serialization/compression.
- Disk I/O increases from storage reads and backup writes.
- WiredTiger cache is impacted by collection scans.
- Network throughput increases.
- Secondary lag may rise if dumping from a secondary.
- User-facing queries may experience elevated p95/p99 latency.

### 15.2. Compression Is Not Free

`--gzip` reduces storage/transfer size for compressible data, at the expense of CPU.

If storage/network is the bottleneck, gzip can help. If CPU is already saturated, gzip can prolong backups or degrade application latency.

### 15.3. Limit Parallelism Based on Resources

Database Tools provide options to tune parallel dump/restore operations depending on version. Do not max out concurrency solely in pursuit of speed.

An overly aggressive restore write load can:

- Saturate disk.
- Increase replication lag.
- Cause cache pressure.
- Consume heavy CPU during index builds.
- Slow down application queries.
- Trigger storage quota exceeded errors.

### 15.4. Should You Dump from a Secondary?

One option is dumping from an eligible secondary to reduce load on the primary, provided you:

- Check replication lag.
- Ensure read preference/target selection is accurate.
- Monitor the oplog window.
- Assess impact on failover readiness.
- Measure CPU/I/O and network on the secondary.

Never assume a secondary is "idle" and always safe to back up under heavy load.

### 15.5. Backup Window and SLA

For a cluster:

```text
Backup size:     200 GB
Read throughput: 100 MB/s effective

Approximate minimum read time:
200000 MB / 100 MB/s = 2000 seconds ≈ 33 minutes
```

This is only a rough estimate excluding index metadata, compression, networking, filesystem overhead, oplog, and concurrent load. Real datasets must be benchmarked.

---

## 16. Performance: mongorestore and Index Build Speed

### 16.1. Restoring Is Usually Heavier Than File Copying

Restoring may involve:

1. Creating databases/collections.
2. Inserting BSON documents.
3. Restoring collection options.
4. Building indexes.
5. Applying oplog entries.
6. Replicating writes to members per write concern.

The process is not merely copying an archive into `mongod`'s data directory.

### 16.2. numParallelCollections

Depending on the Database Tools release:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --numParallelCollections=4
```

Increasing concurrent collections can speed up restoration if the target has sufficient resources, but also increases I/O contention.

### 16.3. numInsertionWorkersPerCollection

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --numInsertionWorkersPerCollection=2
```

Adding workers can help large collections, but monitor latency, replication lag, and disk saturation.

### 16.4. maintainInsertionOrder

There is an option:

```text
--maintainInsertionOrder
```

to preserve insertion order from the input, within tool limits. Per documentation, this option also enables `--stopOnError` and limits insertion workers per collection.

It **does not guarantee that applications will receive results in the same order when querying without `sort()`**. A BSON collection does not maintain a guaranteed business order merely because restore inserted rows sequentially.

### 16.5. Write Concern

Restoring is a write workload. MongoDB Database Tools can accept `--writeConcern` depending on version:

```bash
mongorestore \
  --host 127.0.0.1 \
  --writeConcern="{w:'majority'}" \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

Write concern impacts write acknowledgment, durability, throughput, and RTO. Do not blindly lower write concern solely for speed; weigh topology and recovery goals.

### 16.6. Bulk/Duplicate Errors

Without `--drop`, an already populated target easily triggers duplicate `_id` errors. Use `--stopOnError` for fail-fast jobs, while still planning cleanup of any partial writes committed before the error.

For idempotent restores, it is generally better to restore to a fresh target database and cut over rather than re-running repeatedly into an existing populated collection.

---

## 17. Backup/Restore Is Not a Cluster-Wide Transaction

A common misconception:

> "I dumped all databases, so restoring will return the cluster to an exact single point in time."

That holds true only when the backup was created with **real consistency guarantees** matching the topology/conditions, and the restore is executed properly.

### 17.1. Cross-Collection Invariants

Example:

```text
customers.balance = 100
payments:
  payment #1 deducted 20
orders:
  order #1 paid
```

If a backup reads collections at different times, invariants can break. Raw document counts should never be used to conclude that restored data is business-consistent.

### 17.2. Multi-Document Transactions

A transaction can modify multiple documents/collections. A dump lacking consistency guarantees may fail to represent a single global point in transaction history.

Do not assume that because MongoDB supports transactions, `mongodump` automatically captures a transactional snapshot in every backup mode.

### 17.3. Sharded Transactions

Cross-shard consistency is even more complex. You need a backup policy that handles topology, transaction metadata, and sharding state.

---

## 18. Lab Practice: Creating MongoDB Data and Dumping

Lab goal: create a small database, back it up as both a directory and an archive, restore to another database, and verify counts and indexes.

### 18.1. Creating Data

In `mongosh`, requiring no server config changes:

```javascript
const lab = db.getSiblingDB("inventory_lab");

lab.products.insertMany([
  {
    _id: "P-100",
    name: "Keyboard",
    price: NumberDecimal("299000.00"),
    tags: ["computer", "accessory"],
    createdAt: ISODate("2026-11-14T08:00:00Z")
  },
  {
    _id: "P-101",
    name: "Wireless Mouse",
    price: NumberDecimal("199000.00"),
    tags: ["computer", "accessory"],
    createdAt: ISODate("2026-11-14T08:01:00Z")
  },
  {
    _id: "P-102",
    name: "Monitor",
    price: NumberDecimal("2499000.00"),
    tags: ["display"],
    createdAt: ISODate("2026-11-14T08:02:00Z")
  }
]);

lab.orders.insertMany([
  {
    _id: "O-1",
    productId: "P-100",
    quantity: 2,
    status: "PAID"
  },
  {
    _id: "O-2",
    productId: "P-102",
    quantity: 1,
    status: "NEW"
  }
]);

lab.products.createIndex(
  { name: 1 },
  { name: "idx_product_name" }
);

lab.orders.createIndex(
  { status: 1, productId: 1 },
  { name: "idx_status_product" }
);

printjson({
  productCount: lab.products.countDocuments({}),
  orderCount: lab.orders.countDocuments({})
});
```

Expected output:

```text
productCount: 3
orderCount:   2
```

Run this only in an empty lab database; re-running `insertMany` with the same `_id` values will hit duplicate key errors.

### 18.2. Directory Backup

In a shell/terminal on the machine with Database Tools installed:

```bash
mongodump \
  --host 127.0.0.1 \
  --port 27017 \
  --db inventory_lab \
  --out ./backups/inventory-directory
```

In a localhost lab without auth/TLS, the simple command suffices. On secured deployments, add the appropriate authentication/TLS options.

### 18.3. Archive Backup

```bash
mongodump \
  --host 127.0.0.1 \
  --db inventory_lab \
  --archive=./backups/inventory.archive.gz \
  --gzip
```

You do not need both directory and archive formats in a real job; the lab creates both solely for comparison.

### 18.4. Lab Consistency Note

During the dump, **do not issue additional writes/DDL**. This small exercise teaches the mechanics, not proving consistent backup under load.

---

## 19. Lab Practice: Restoring to a Verification Database

### 19.1. Restore Archive and Remap Namespace

In the terminal:

```bash
mongorestore \
  --host 127.0.0.1 \
  --archive=./backups/inventory.archive.gz \
  --gzip \
  --nsFrom="inventory_lab.*" \
  --nsTo="inventory_restore_test.*" \
  --stopOnError
```

The command attempts to restore:

```text
inventory_lab.products → inventory_restore_test.products
inventory_lab.orders   → inventory_restore_test.orders
```

Pick a new target namespace to avoid overwriting `inventory_lab`.

### 19.2. Verifying Data

In `mongosh`:

```javascript
const original = db.getSiblingDB("inventory_lab");
const restored = db.getSiblingDB("inventory_restore_test");

printjson({
  sourceProducts: original.products.countDocuments({}),
  restoredProducts: restored.products.countDocuments({}),
  sourceOrders: original.orders.countDocuments({}),
  restoredOrders: restored.orders.countDocuments({})
});

printjson(restored.products.getIndexes());
printjson(restored.orders.getIndexes());

printjson(restored.products.findOne({ _id: "P-100" }));
```

Expected:

- Products: 3 in both source and restored.
- Orders: 2 in both source and restored.
- Corresponding indexes recreated if metadata/target are compatible and index restoration was not skipped.
- Document `P-100` retains `Decimal128` for `price` and BSON Date for `createdAt`.

### 19.3. Checking Types

In `mongosh`:

```javascript
const item = db
  .getSiblingDB("inventory_restore_test")
  .products.findOne({ _id: "P-100" });

printjson(item.price);
printjson(item.createdAt);
```

Do not compare only JSON text; verify BSON types if business logic relies on Decimal128/Date/ObjectId.

### 19.4. Checking Query Patterns

```javascript
const testDb = db.getSiblingDB("inventory_restore_test");

testDb.products.find({
  name: "Keyboard"
}).explain("executionStats");

testDb.orders.find({
  status: "PAID"
}).explain("executionStats");
```

Small collections may legitimately choose COLLSCAN; the goal is confirming queries execute, indexes exist, and the application encounters no metadata errors.

### 19.5. Do Not Measure RTO From a 5-Document Lab

Restoring 5 documents is vastly different from restoring hundreds of GB with large indexes, replica set write concern, storage quotas, and concurrent application traffic.

Use the lab to learn options; for capacity planning, measure against representative data volume and shape.

---

## 20. Pre-Restore Compatibility Checklist

Before executing, gather:

### 20.1. Source

- Source Server version.
- Source FCV.
- Topology: standalone/replica set/sharded.
- Namespace scope.
- MongoDB features in use.
- Whether users/roles are required.
- Whether the dump includes `--oplog`.
- State of writes/DDL during the backup window.

### 20.2. Tools

- `mongodump --version`.
- `mongorestore --version`.
- Backup format: directory/archive/gzip.
- Support for `--dryRun`/namespace flags/cluster topology per docs version.
- Whether matching tool versions are recorded.
- Whether the binary matches OS/architecture.

### 20.3. Target

- Target Server version.
- Target FCV.
- Support for BSON/metadata/index features present in the dump.
- Sufficient disk, IOPS, CPU, and memory.
- AuthSource/backup-restore roles prepared.
- TLS trust/hostname matching.
- Whether collections already exist.
- Whether TTL indexes/validation affect restored data.
- Whether user/role restoration could impact current accounts.
- Whether restoring into `mongos` or an eligible replica set member.

### 20.4. Business Readiness

- RPO and RTO defined.
- Approved restore window.
- Original backup preserved immutably.
- Isolated target available for testing.
- Reconciliation datasets/sample queries ready.
- Backout/cutover plan in place.
- App writers controlled where necessary.
- Encryption and auditing addressed.

---

## 21. Backup Manifest, Checksums, and Secure Storage

A backup file does not prove its own readability. Store metadata:

```yaml
backupId: inventory-lab-20261114-0200
source:
  topology: standalone
  serverVersion: "record-actual-value"
  fcv: "record-actual-value"
tool:
  mongodumpVersion: "record-actual-value"
  expectedMongorestoreVersion: "same-release-recommended"
format:
  type: archive
  gzip: true
  withOplog: false
  scope: inventory_lab
file:
  name: inventory.archive.gz
  sha256: "record-real-checksum"
policy:
  retentionDays: 30
  encryptedAtRest: true
  access: restricted
validation:
  restoreTested: false
```

### 21.1. Hashing the File

Linux:

```bash
sha256sum ./backups/inventory.archive.gz
```

PowerShell:

```powershell
Get-FileHash -LiteralPath ".\backups\inventory.archive.gz" -Algorithm SHA256
```

Store the checksum externally from the backup alongside the protected manifest.

### 21.2. Verifying After Transfer

After uploading/downloading or copying between hosts:

1. Compute SHA-256 of the file at the source.
2. Compute SHA-256 at the destination.
3. Compare for an exact match.
4. Check file size.
5. Perform a test restore on an isolated target.

A checksum confirms the file has not changed since hashing; **it does not prove the source dump was consistent or that application data can be fully recovered**.

### 21.3. Encryption and Retention

Backups contain sensitive data. Require:

- Encryption at rest.
- Encryption in transit.
- RBAC and restricted access.
- Secret/key management separated from the archive.
- Retention/lifecycle policies.
- Auditing for access/download/delete.
- Periodic restore drills.
- Immutable/offline/offsite copies according to risk model.

Never treat gzip as encryption.

### 21.4. Do Not Store Binary Dumps in Git

Git is unsuitable for large BSON dumps that may contain secrets/PII. Use object storage/a backup repository with appropriate access controls and retention.

---

## 22. Large Data Recovery: Pre-, During-, and Post-Restore Runbook

### 22.1. Pre-Restore

1. Confirm business requirements and recovery point.
2. Select a checksum-verified backup.
3. Verify tool versions and source/target server/FCV.
4. Confirm topology/namespace mapping.
5. Analyze whether `admin`/users/roles are in restore scope.
6. Provision disk (data + indexes + temporary headroom), CPU, and time.
7. Plan networking and write concerns.
8. Select an isolated target or maintenance window.
9. Pause/throttle writers if required by the procedure.
10. Run dry-run and test restore if supported.
11. Enable monitoring for CPU/I/O/lag/latency.
12. Prepare rollback plan.

### 22.2. During Restore

- Log commands **with secrets redacted** and tool versions.
- Record start and end timestamps.
- Monitor restored/failed document counts.
- Monitor disk space, CPU, I/O latency, and cache.
- Monitor replication lag if the target is a replica set.
- Do not crank up concurrency excessively if overload appears.
- Never run parallel `--drop` restores on overlapping namespaces.
- Halt and investigate on duplicate/schema/index/authentication errors.
- Do not treat process exit code 0 as sole proof of correctness.

### 22.3. Post-Restore

- Review exit code and log summary.
- Check collections/views/indexes/options.
- Reconcile document counts per namespace.
- Inspect critical sample documents and BSON types.
- Verify business invariants/cross-collection references.
- Run application smoke tests.
- Measure query explain/index usage.
- Verify roles/authentication.
- Observe TTL/retention behavior.
- Check monitoring/alerts.
- Cut over only after acceptance criteria are met.
- Record actual RTO and lessons learned.

### 22.4. Stop Criteria

If any of the following occurs:

- Tool/server compatibility is unconfirmed.
- Backup checksum mismatch.
- Loss of recovery privileges due to `admin` user restoration.
- Insufficient disk space.
- Restored data fails validation.
- Unsafe replication/shard topology.
- No rollback path remains.
- RPO/RTO targets are missed and require a business decision.

halt and switch to the appropriate recovery runbook; do not escalate privileges or enable insecure options just to push past errors.

---

## 23. What Should a Java Application Do in a Backup/Restore Workflow?

`mongodump` and `mongorestore` are **CLI tools**, not methods in the MongoDB Java Sync Driver.

A Java application can:

- Seed lab data.
- Run read-only checks on data before/after restore.
- Record/reconcile business counts/invariants.
- Query the new database for smoke tests.
- Participate in cutover via configuration/feature flags.
- In some operational platforms, trigger a managed automation job (public HTTP requests must never run arbitrary backup commands).

### 23.1. Do Not Build a Fake mongodump Using find()

A Java program running:

```java
collection.find()
```

and writing JSON to a file **is not equivalent** to `mongodump`. It fails to back up:

- All exact BSON types.
- Collection metadata.
- Index definitions.
- Users/roles.
- Oplog consistency.
- Other namespaces.

If a logical backup tool is needed, invoke standard `mongodump` through trusted operational automation instead of rolling a custom document-only copy.

### 23.2. Java Smoke Test After Restore

Example using the MongoDB Java Sync Driver:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class RestoreSmokeTest {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_RESTORE_TEST_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing MONGODB_RESTORE_TEST_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db =
                    client.getDatabase("inventory_restore_test");

            long productCount =
                    db.getCollection("products").countDocuments();

            long orderCount =
                    db.getCollection("orders").countDocuments();

            System.out.println(
                    "products=" + productCount
                    + ", orders=" + orderCount
            );

            Document product =
                    db.getCollection("products")
                      .find(new Document("_id", "P-100"))
                      .first();

            if (product == null) {
                throw new IllegalStateException(
                        "Restored product P-100 missing");
            }

            System.out.println(
                    "Restore smoke test passed");
        }
    }
}
```

This is only a smoke test. Production validation requires business queries, index checks, role checks, and consistency reconciliation.

### 23.3. Inspecting Indexes After Restore

```java
import com.mongodb.client.MongoCollection;
import org.bson.Document;

MongoCollection<Document> products =
        database.getCollection("products");

for (Document index : products.listIndexes()) {
    System.out.println(index.toJson());
}
```

Use this method in a properly authorized application/admin test. Compare names, key patterns, and important options.

### 23.4. Why Not Invoke ProcessBuilder Arbitrarily From an API Request?

Allowing a user to upload a URI/filename and having the Java backend execute:

```text
mongorestore --drop <untrusted-input>
```

can lead to:

- Shell/command argument injection if commands are constructed improperly.
- Restoring into the wrong namespace.
- Leaking backups/passwords.
- Production data loss.
- Disk/network/CPU exhaustion.

If designing a backup service, enforce **whitelisted jobs**, fixed target scopes, approval/authorization, auditing, secret injection, and sandboxed execution. Never turn `mongorestore` into an arbitrary command-execution endpoint.

---

## 24. Real-World Errors and Diagnostics

### 24.1. Command not found

Symptom:

```text
mongodump: command not found
```

Causes:

- Database Tools not installed.
- Binary not in `PATH`.
- `mongosh` installed without Database Tools.
- Container image lacks tools.

Resolution: check installation, `mongodump --version`, and binary path.

### 24.2. Authentication failed

Causes:

- Wrong username/password.
- Wrong `--authenticationDatabase`/`authSource`.
- Incompatible authentication mechanism.
- Secret contains unencoded URI special characters.
- Server/DB user does not exist.

Resolution: verify user/source/mechanism; never grant `root` or disable auth to bypass the error.

### 24.3. Not authorized to execute command

Authentication succeeded, but the role lacks permissions to read/back up/restore a namespace or metadata.

Resolution: compare required privileges against the operation/namespace and grant least privilege per version docs.

### 24.4. TLS certificate validation failed

Causes:

- Untrusted CA chain.
- Hostname/SAN mismatch.
- Expired certificate.
- Incompatible client/server TLS configuration.

Resolution: fix trust store/CA/certificate/hostname; never enable invalid certificate bypass in production.

### 24.5. Duplicate key during restore

Target data already has matching `_id` or unique index keys.

Resolution:

- Restore into a new database/namespace.
- If intentional replacement is desired, evaluate `--drop` after review.
- Use `--stopOnError` to fail fast.
- Do not delete production data without a recovery plan.

### 24.6. Index build failed

Causes:

- Duplicate data.
- Unsupported index option.
- Incompatible target Server/FCV.
- Insufficient disk/CPU.
- Different collation/index metadata.

Resolution: identify the specific failing index and check compatibility. Never blindly skip all index restoration and declare the system fully recovered.

### 24.7. Wrong namespace restored

Causes:

- Using `--db`/`--collection` on an archive in a deprecated/incorrect way.
- `--nsInclude` pattern mismatch.
- Wrong `--nsFrom`/`--nsTo` mapping.
- Shell expanding `*` or `$`.
- Source backup lacks the target namespace.

Resolution: inspect dry-run output, archive structure, and explicit namespace patterns.

### 24.8. Unexpected zero documents restored

Possible causes:

- Empty dump.
- Non-matching `nsInclude`.
- Wrong input file.
- Restore failed due to permissions while a script ignored the exit code.
- Tool skipped collections per flags.
- Archive not decompressed/read in the right format.

Never treat 0 restored documents as success when data is expected.

### 24.9. Unsupported BSON/metadata

Causes:

- Source/target server major/FCV mismatch outside supported range.
- Newer index/collection feature absent on target.
- Mismatched dump/archive/tool versions.
- Oplog replay across an incompatible transition.

Resolution: check the version matrix and run a test restore; do not arbitrarily strip metadata.

### 24.10. Data disappears again after restore

May be caused by a TTL index and documents already past the retention period.

Resolution: inspect index definitions and TTL policy; if staging must retain historical data, use a test environment with policy-controlled retention.

### 24.11. Sharded backup inconsistency

Backing up via `mongos` while chunk migrations/writes are active can lack cluster-wide consistency guarantees.

Resolution: use an official sharded backup workflow or managed backup; do not merely add `--oplog` to a `mongos` command and assume it is sufficient.

### 24.12. Slow restore or disk full

Causes:

- Many indexes.
- Large data volume.
- Low network/disk throughput.
- Too many insertion workers.
- Replication lag/write concern.
- Compression CPU overhead.
- Insufficient storage headroom.

Resolution: capacity plan, tune concurrency, monitor metrics, and test restores with representative datasets.

---

## 25. Common Misconceptions

| Misconception | Reality |
|---|---|
| `mongodump` is a filesystem snapshot | It is a logical backup |
| Dumping the whole deployment backs up all infra config | No; network/secrets/storage settings are not automatically preserved |
| Having BSON is enough to recover the whole app | You also need indexes, metadata, users, roles, and business links |
| `mongodump` is automatically consistent with concurrent writes | Not by default; appropriate consistency guarantees are required |
| `--oplog` works with `--db` | Not supported per replica set full-dump rules |
| `--oplog` guarantees consistency for a sharded cluster via mongos | No |
| `--oplogReplay` works with `--nsFrom`/`--nsTo` | Not with the full oplog restore workflow |
| `--drop` drops the entire database | It drops target collections present in the dump, not every other collection |
| `mongorestore` always replaces documents | No; duplicate key errors can occur if the collection already has data |
| Restore is an atomic transaction | No; partial data may remain on failure |
| `--stopOnError` rolls back everything | It only halts; it does not roll back already-committed writes |
| `--dryRun` proves recovery works | It does not replace a real test restore |
| `--gzip` encrypts backups | Gzip is compression, not encryption |
| Tools 100.x must match Server 100.x | Tools and Server are released independently |
| A tool that connects to any server makes cross-version dump/restore safe | Source/target FCV, metadata, archive, and oplog rules still apply |
| Restoring BSON to a new version is a standard upgrade | MongoDB docs do not recommend dump/restore as an upgrade replacement |
| Different `mongodump`/`mongorestore` versions are always compatible | Use the same release to avoid format mismatches |
| `mongoexport` is a full substitute for `mongodump` | No; semantics and metadata differ |
| `--noIndexRestore` only speeds things up with no side effects | Can lose indexes, constraints, and query performance |
| `readWrite` is enough for a full restore | Privileges depend on namespaces, users/roles, and oplog |
| `ping` succeeding proves backup permissions | You must verify required access |
| Matching restored counts mean data is correct | BSON types, indexes, and business invariants also matter |
| Fast restore on 5 documents means RTO is met | Must benchmark on production-like data |
| Dumping on a secondary has zero impact on production | Secondary lag/I/O can impact HA |
| Downloading an archive completes DR | Checksums, encryption, offsite storage, and restore drills are needed |
| TTL does not affect restored data | TTL can delete historical records per policy |

---

## 26. Practice Exercises

### Exercise A — Install and Check Compatibility

1. Run `mongodump --version` and `mongorestore --version`.
2. In `mongosh`, run `db.version()`.
3. If authorized, check FCV.
4. Look up Server Compatibility for your exact Database Tools release.
5. Explain why tool versions and Server versions do not need identical numbers.

### Exercise B — Directory vs Archive

1. Create `inventory_lab` using the sample data.
2. Dump to a directory.
3. Dump to an archive.
4. Dump to an archive + gzip.
5. Compare file layout, sizes, and required restore flags.
6. Explain why `--gzip` does not mean the backup is encrypted.

### Exercise C — Restore to a Different Database

1. Dump `inventory_lab`.
2. Restore with `--nsFrom/--nsTo` into `inventory_restore_test`.
3. Verify `productCount`/`orderCount`.
4. Verify indexes.
5. Compare Decimal128/Date values.
6. Do not use `--drop` on the original database.

### Exercise D — Duplicate Key and --stopOnError

In a lab:

1. Restore an archive into a target that still has data from a previous restore.
2. Observe duplicate errors.
3. Re-run with `--stopOnError`.
4. Explain why some writes committed before the error may still remain.
5. Design an idempotent restore workflow using a fresh target.

### Exercise E — Partial Dump and Consistency

Suppose you have `orders` and `payments`. If you dump each collection while the application updates both, what inconsistencies can occur? How do you build a consistent backup given topology and RPO requirements?

### Exercise F — Replica Set Oplog

1. Explain the full-dump requirement of `--oplog`.
2. Explain why `--db commerce --oplog` is not supported.
3. Describe the `oplog.bson` file.
4. Describe `--oplogReplay`.
5. Explain why `--oplogReplay` is not combined with `--nsTo`.
6. State the risks of DDL and FCV transitions.

Only run an actual oplog backup/restore on a lab replica set with an appropriate runbook.

### Exercise G — Sharded Cluster

Explain why a `mongos` lacks a single shared oplog for creating a consistent backup with `--oplog`. List the elements that must be coordinated across shards, balancer, metadata, and writers.

### Exercise H — Version Migration

Source runs Server major version A, target runs major version B.

1. Gather Server versions and FCV.
2. Gather Database Tools versions.
3. Distinguish BSON data vs metadata/archive/oplog.
4. Check compatibility docs.
5. Choose a same-version restored target or a supported upgrade procedure.
6. Perform a test restore and verify indexes/collections.

### Exercise I — Authentication/Roles

A `backup_operator` user is created in `admin` and needs to dump `commerce`.

- What should `--authenticationDatabase` be?
- What should `--db` be?
- Which role is appropriate?
- Why is `root` unnecessary?
- Why should the password not be placed on the command line?

### Exercise J — TTL After Restore

A backup contains an `events` collection with a 30-day TTL. Restoring 6-month-old data to staging makes the data disappear. Explain why and design a safe lab retention plan to test historical data.

### Exercise K — RPO/RTO

A system backs up daily at 02:00, and an incident hits at 18:00. Restoring the full dump takes 3 hours. Estimate the maximum data-loss window and actual recovery time from these facts, then propose when continuous backup is needed.

### Exercise L — Safe Runbook

Write a runbook containing:

- Scope and owner.
- Backup identifier/checksum.
- Source/target Server versions and FCV.
- Tool versions.
- TLS/authSource and privileges.
- Dump format/flags.
- DDL/writes management.
- Test restore, smoke tests.
- Observability.
- Cutover/rollback.
- Retention/encryption.

---

## 27. Quick Decision Rules

| Question | Action |
|---|---|
| Want to copy a small database to a lab? | Dump database, restore to a new namespace |
| Backing up while receiving writes on a replica set? | Evaluate full `--oplog` under supported conditions |
| Source is an actively written sharded cluster? | Use a cluster-aware/managed backup workflow |
| Want to restore one collection from an archive? | `--nsInclude` |
| Want to rename a database during restore? | `--nsFrom`/`--nsTo` |
| Want to replace the target collection? | Review `--drop` and ensure a backup/cutover plan |
| Want to keep the old target intact? | Restore to a different namespace |
| Seeing duplicate key errors? | Clarify merge/replace goal; consider `--stopOnError` |
| Have BSON but incompatible metadata? | Do not treat inserted documents as a full restore |
| Tool versions do not match? | Prefer matching release; test restore first |
| Source/target servers differ in major/FCV? | Consult compatibility docs and upgrade path |
| Need a very low RPO? | Appropriate PITR/continuous backup |
| Only have a dump file never test-restored? | Recovery readiness is unproven |

---

## 28. Official Documentation

- [MongoDB Database Tools documentation](https://www.mongodb.com/docs/database-tools/)
- [MongoDB Database Tools installation](https://www.mongodb.com/docs/database-tools/installation/)
- [MongoDB Database Tools release notes](https://www.mongodb.com/docs/database-tools/release-notes/database-tools-changelog/)
- [mongodump reference](https://www.mongodb.com/docs/database-tools/mongodump/)
- [mongodump behavior and compatibility](https://www.mongodb.com/docs/database-tools/mongodump/mongodump-behavior/)
- [mongorestore reference](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [mongorestore behavior and compatibility](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-behavior-access-usage/)
- [mongorestore compatibility and installation](https://www.mongodb.com/docs/database-tools/mongorestore/mongorestore-compatibility-and-installation/)
- [Back Up and Restore Self-Managed Deployments](https://www.mongodb.com/docs/manual/core/backups/)
- [Back Up a Self-Managed Sharded Cluster with a Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/)
- [Feature Compatibility Version](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/)
- [MongoDB Atlas Backup](https://www.mongodb.com/docs/atlas/backup/)
- [MongoDB Java Sync Driver documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)

> **Note:** Database Tools are released independently of the server. Examples like `100.20.1` in official documentation reflect a specific release point; during deployment, always check the compatibility matrix and behavior page of the **exact binary/tool/server versions** you are using. Do not treat version limits as immutable constants over time.

## 29. Summary

1. `mongodump` exports **logical BSON data and metadata**, while `mongorestore` reloads data/indexes/options within supported limits.
2. Database Tools have **their own versioning** (the `100.x` branch) and must be checked for compatibility with source/destination MongoDB Servers.
3. Distinguish **Server version, FCV, Database Tools version, and backup format**; being able to restore BSON does not mean metadata/archives/oplogs are safe across versions.
4. **Prefer using the same `mongodump` and `mongorestore` release**, and test-restore to a target with a compatible version/FCV.
5. A plain dump during concurrent writes **is not a consistent point-in-time snapshot by default**.
6. `--oplog`/`--oplogReplay` helps for **full replica set dumps**, but cannot be combined with `--db`/`--collection` scoping or namespace remapping during replay.
7. `--oplog` **does not** turn a `mongos` dump into a consistent full sharded-cluster backup.
8. `--drop` drops only target collections restored from the dump, yet can cause data loss and is especially dangerous for `admin` users/roles.
9. `--nsInclude` and `--nsFrom/--nsTo` enable safer selective restores and database renames, provided the workflow does not use oplog replay.
10. Gzip reduces size, **not encrypt**; backups require checksums, encryption, RBAC, retention, and restore drills.
11. Post-restore verification must check **documents, BSON types, indexes, collection options, roles, and business invariants**, not just exit codes or counts.
12. For strict RPO/RTO requirements or large clusters, evaluate supported backup/snapshot/PITR solutions rather than relying solely on a daily `mongodump`.

**Conclusion:** A dump becomes a reliable recovery asset only when it has **the right format, compatible tool/server/FCV versions, topology-appropriate consistency, secret protection, and a proven test restore**. Runbook design starts from RPO/RTO and tool compatibility—not from immediately running `mongorestore --drop`.
