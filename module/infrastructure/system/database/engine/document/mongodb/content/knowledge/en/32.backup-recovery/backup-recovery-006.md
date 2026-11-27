# Distinguishing `mongoexport`/`mongoimport` From Full Backup Tools in MongoDB

## 1. Learning Objectives

Suppose a MongoDB system stores orders, customers, transactions, and administrative data. You need to:

- Send an orders table to the analytics team as **CSV**.
- Transfer a subset of documents to a test collection as **JSON**.
- Migrate data from an old environment to a new one while preserving BSON types and indexes.
- **Recover from an accidental deletion** at 14:20 while preserving valid prior changes.
- Restore an entire **replica set** or **sharded cluster** after an infrastructure outage.
- Prove **RPO** and **RTO** for operational requirements.

You cannot assume one `mongoexport` command solves all of these.

MongoDB provides distinct tool groups:

1. **`mongoexport` and `mongoimport`**: export/import **document data** between MongoDB and JSON/CSV/TSV for data interchange, integration, cleansing, or ingestion.
2. **`mongodump` and `mongorestore`**: create/restore **logical dumps in BSON format**, including appropriate collection/index metadata; supports oplog capture for consistent dumps of a **replica set** under defined conditions.
3. **Filesystem/cloud snapshots and coordinated backup services**: deployment-level backup solutions that can combine snapshots, oplogs, multi-copy storage, and **point-in-time recovery** (PITR) across a configured retention window.

> **Key takeaway:** Official MongoDB documentation states explicitly: **`mongoexport` is not a tool for backing up a deployment**. It does not carry enough state and metadata to restore a MongoDB system to its exact prior operational state.

After this lesson, you can:

- Pick the right tool for **export**, **migration**, **logical backup**, **snapshot backup**, or **PITR**.
- Understand the differences between JSON/CSV, **Extended JSON**, and BSON.
- Practice `mongoexport`, `mongoimport`, `mongodump`, and `mongorestore` on a lab database.
- Identify metadata lost when transferring documents alone: indexes, unique constraints, collection options, validators, views, users, and roles.
- Understand the limits of `mongodump --oplog`/`mongorestore --oplogReplay` and why full sharded-cluster backups require coordination.
- Evaluate snapshots, Atlas Cloud Backups, Continuous Cloud Backups, RPO/RTO, security, and cost.
- Design a **verifiable recovery**, rather than merely producing a file named "backup."

---

## 2. Four Concepts to Distinguish

### 2.1. Data Export

**Data export** converts data into another format, such as JSON or CSV.

Example:

```text
MongoDB orders collection
        |
    mongoexport
        |
     orders.csv
        |
   BI / spreadsheet
```

Commonly used for:

- Reporting and analytics.
- Exchanging data with external applications.
- Exporting a filtered subset.
- Controlled investigations.
- Loading test datasets.

A CSV file may suffice for sales analysis, yet it **knows nothing** about the collection's unique indexes, TTL indexes, schema validators, access controls, or storage rules.

### 2.2. Data Import

**Data import** loads documents from JSON/CSV/TSV into a MongoDB collection.

```text
orders.json
    |
 mongoimport
    |
 MongoDB collection
```

It fits:

- Ingesting partner feeds.
- Loading seed data.
- Transferring JSON/CSV datasets.
- Merging/upserting by explicitly designed keys.

**Importing is not a full system restore.** It operates at the document layer and does not recreate full database design automatically.

### 2.3. Logical Backup

**Logical backup** stores documents and metadata at the database level, rather than copying raw storage engine files.

```text
MongoDB collection + BSON + metadata
                 |
             mongodump
                 |
          *.bson + *.metadata.json
                 |
             mongorestore
                 |
           MongoDB restored data
```

With proper options, `mongodump` captures BSON documents and collection/index metadata, useful for database recovery or compatible migrations.

However, a **plain logical dump** is not necessarily consistent under concurrent writes; pay attention to replica sets, oplogs, sharded-cluster restrictions, and users/roles permissions.

### 2.4. Deployment Backup / Disaster Recovery

A real **deployment backup** must account for:

- Full data in scope.
- Metadata, configuration, indexes, users/roles, and external dependencies.
- **Point-in-time consistency**.
- Recovery point and recovery time objectives.
- Secure, versioned copies outside production's failure domain.
- Recoverability, verification, and application resumption.
- Backup retention, auditing, encryption, and access controls.

Tools can include:

- MongoDB Atlas Cloud Backups / Continuous Cloud Backups.
- Coordinated backup solutions such as supported MongoDB services.
- Properly executed filesystem snapshots.
- Logical dumps under appropriate conditions.
- Multi-layered combinations meeting organizational policy.

**A backup is not defined by a `.json`, `.bson`, or `.zip` file extension; it is defined by the ability to restore the required state.**

---

## 3. Quick Decision Matrix

| Criterion | `mongoexport` | `mongoimport` | `mongodump` | `mongorestore` | Snapshot/Managed Backup |
| --- | --- | --- | --- | --- | --- |
| Role | Export documents | Import documents | Create logical dump | Restore logical dump | Create/restore deployment backup |
| Primary format | Extended JSON, CSV | JSON, CSV, TSV | BSON + metadata, archive | BSON/metadata dump | Storage snapshot + system metadata/oplog |
| For BI/Excel | Fits well with CSV | Not primary purpose | Not directly | Not directly | No |
| Preserves BSON types | Extended JSON can preserve via encoding | Extended JSON can reconstruct types | **Yes** in BSON format | **Yes** when restore is compatible | **Yes** in valid snapshots |
| Preserves collection/index metadata | **No** | **No** built from export | **Within supported scope** | Recreates from metadata when present | Per backup coverage |
| Preserves users/roles | No | No | Depends on scope/options | Depends on dump and restore options | Per backup scope |
| Captures concurrent changes | Not guaranteed | N/A | `--oplog` option for replica sets | `--oplogReplay` for eligible dumps | PITR if service-supported |
| Consistent sharded-cluster backup | **No** | No | **Not with `--oplog` alone via `mongos`** | Sharded `--oplogReplay` unsupported | Requires coordinated workflow |
| Restore to arbitrary timestamp | No | No | Only limited dump oplog window | Not full continuous PITR | Continuous backup with PIT window |
| Suitable for production DR | No | No | Can be one piece with proper design | Restore component | Usually the primary choice |
| Operational risks | Exposing PII, missing data | Duplicates/dropping collections, type drift | Load spike, inconsistent dump | Overwriting/dropping target data | Wrong target/point, losing newer data |

Note: `mongodump` and `mongorestore` belong to **MongoDB Database Tools** and do not automatically prove that topology, secrets, deployment config, or search indexes are restored.

---

## 4. Where Do MongoDB Database Tools Run?

`mongoexport`, `mongoimport`, `mongodump`, and `mongorestore` are **OS command-line programs**.

Do not run them as JavaScript inside `mongosh`:

```javascript
// WRONG if typed directly inside mongosh:
mongoexport --db=shop --collection=orders;
```

Instead, open a terminal:

```bash
mongoexport --version
mongoimport --version
mongodump --version
mongorestore --version
```

Across modern MongoDB versions, Database Tools use independent release numbering, such as `100.x`, **not identical to the MongoDB Server version**. Check the compatibility matrix, especially when dumping/restoring across versions or FCVs.

### 4.1. Connections and Credentials

Local unauthenticated lab example:

```bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders \
  --out=orders.json
```

In production:

- Use TLS and verify CA/hostnames.
- Use least-privilege accounts.
- Never hardcode passwords in URIs committed to Git.
- Avoid putting passwords into process arguments or shell history.
- Use interactive password prompts or `--config` per Database Tools docs, with strict file permissions.
- Never upload exports containing sensitive data to unauthorized external tools.

`--config` is the secret-handling pattern for modern Database Tools, though **never include password values** in instructional examples.

### 4.2. Directories and Shells

The shell examples below use Bash syntax on Linux/macOS or compatible terminals. On Windows PowerShell, line continuations, quoting, paths, and `$` expansion behave differently; avoid pasting JSON query commands verbatim without adapting for your shell.

---

## 5. Lab: Creating Data With Multiple BSON Types and Metadata

To see how export/import differs from backups, the lab needs both **data** and **collection rules**.

Open `mongosh` connected to the local lab. `drop()` commands are only for the test database; **never run on production**.

```javascript
const lab = db.getSiblingDB("export_backup_lab");

lab.orders.drop();
lab.orders_from_json.drop();
lab.orders_from_csv.drop();
lab.orders_from_bson.drop();

lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "orderId",
        "createdAt",
        "amount",
        "status"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        orderId: { bsonType: "string" },
        createdAt: { bsonType: "date" },
        amount: { bsonType: "decimal" },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});

lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "uq_tenant_order" }
);

lab.orders.createIndex(
  { createdAt: -1 },
  { name: "ix_createdAt_desc" }
);

lab.orders.insertMany([
  {
    _id: ObjectId("650000000000000000000001"),
    tenantId: "tenant-A",
    orderId: "A-100",
    createdAt: ISODate("2026-11-14T08:00:00Z"),
    amount: NumberDecimal("125.50"),
    status: "PAID",
    quantity: NumberInt(2),
    sequence: NumberLong("9007199254740993"),
    shipping: {
      city: "Hanoi",
      region: "Northern Vietnam"
    },
    tags: ["vip", "online"]
  },
  {
    _id: ObjectId("650000000000000000000002"),
    tenantId: "tenant-A",
    orderId: "A-101",
    createdAt: ISODate("2026-11-14T08:05:00Z"),
    amount: NumberDecimal("0.99"),
    status: "NEW",
    quantity: NumberInt(1),
    sequence: NumberLong("9007199254740994"),
    shipping: { city: "Da Nang" },
    tags: ["online"]
  },
  {
    _id: ObjectId("650000000000000000000003"),
    tenantId: "tenant-B",
    orderId: "B-200",
    createdAt: ISODate("2026-11-14T08:12:00Z"),
    amount: NumberDecimal("99999.01"),
    status: "CANCELLED",
    quantity: NumberInt(3),
    sequence: NumberLong("9007199254740995"),
    shipping: { city: "Ho Chi Minh City" },
    tags: []
  },
  {
    _id: ObjectId("650000000000000000000004"),
    tenantId: "tenant-B",
    orderId: "B-201",
    createdAt: ISODate("2026-11-14T08:20:00Z"),
    amount: NumberDecimal("45.00"),
    status: "PAID",
    quantity: NumberInt(1),
    sequence: NumberLong("9007199254740996"),
    shipping: {
      city: "Can Tho",
      region: "Mekong Delta"
    },
    tags: ["app"]
  }
]);

lab.orders.countDocuments({});
// 4
```

The four records contain:

- `_id` of type **ObjectId**.
- `createdAt` of type **Date**.
- `amount` of type **Decimal128**.
- `quantity` of type **Int32**.
- `sequence` of type **Int64**, deliberately larger than JavaScript's safe integer limit.
- Nested object and array.
- Unique index, secondary index, and `$jsonSchema` validator.

If a method preserves only **text data**, protective collection rules can vanish even though the document count remains 4.

### 5.1. Checking BSON Types and Indexes

```javascript
lab.orders.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      idType: { $type: "$_id" },
      amountType: { $type: "$amount" },
      dateType: { $type: "$createdAt" },
      quantityType: { $type: "$quantity" },
      sequenceType: { $type: "$sequence" }
    }
  }
]).toArray();

lab.orders.getIndexes();
lab.getCollectionInfos({ name: "orders" });
```

The first command reveals types like `objectId`, `decimal`, `date`, `int`, and `long`. The others inspect index definitions and collection options/validators.

---

## 6. `mongoexport`: Exporting JSON for Data Interchange

In the terminal:

```bash
mongoexport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders \
  --type=json \
  --out=orders.json
```

By default, modern Database Tools JSON exports use **Extended JSON v2, relaxed mode**. Under the default format, each document is written on **one JSON line** (JSON Lines/NDJSON-like), not as a single JSON array.

Date/ObjectId values look like:

```json
{
  "_id": { "$oid": "650000000000000000000001" },
  "createdAt": { "$date": "2026-11-14T08:00:00Z" },
  "amount": { "$numberDecimal": "125.50" }
}
```

**This example shows only part of a document**; the real exported file contains other fields and typically puts one document per line.

### 6.1. Extended JSON Is Not Plain Business JSON

BSON has types that standard JSON cannot represent directly:

- `ObjectId`.
- `Date`.
- `Decimal128`.
- `Int32` and `Int64`.
- `Timestamp`.
- `Binary`.
- `RegularExpression`, `MinKey`, `MaxKey`...

MongoDB **Extended JSON** uses wrappers such as:

```json
{ "$oid": "650000000000000000000001" }
```

```json
{ "$date": "2026-11-14T08:00:00Z" }
```

```json
{ "$numberDecimal": "125.50" }
```

```json
{ "$numberLong": "9007199254740993" }
```

When imported with `mongoimport` supporting the matching Extended JSON version/format, these wrappers reconstruct BSON types. However, an external system expecting plain JSON treats those wrappers as ordinary nested objects and may not understand MongoDB types.

### 6.2. Canonical vs. Relaxed

Depending on goal:

```bash
# Default: Extended JSON relaxed.
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --out=orders-relaxed.json
```

```bash
# Canonical: expresses BSON types more explicitly.
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --jsonFormat=canonical \
  --out=orders-canonical.json
```

Canonical preserves Int32/Int64/Double representations more explicitly:

```json
{ "quantity": { "$numberInt": "2" } }
```

```json
{ "sequence": { "$numberLong": "9007199254740993" } }
```

**Recommendation:** If transferring data with critical BSON types via JSON, prefer **Extended JSON canonical** and test with `mongoimport` from the same Database Tools version. For BI consumption, relaxed JSON/CSV may be easier to parse, provided a clear type contract exists.

### 6.3. A Single JSON Array Instead of One Object per Line

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --jsonArray \
  --out=orders-array.json
```

Exports omit `--jsonArray` by default. If importing a JSON array file, pass `mongoimport --jsonArray` to match.

### 6.4. Exporting a Subset

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --query='{"status":"PAID"}' \
  --out=paid-orders.json
```

On the fixture, this yields **2 PAID orders**.

A date filter requires Extended JSON for `Date`:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --query='{"createdAt":{"$gte":{"$date":"2026-11-14T08:10:00Z"}}}' \
  --out=recent-orders.json
```

On the fixture, this yields **2 documents** created from 08:10 UTC onward.

**Shell note:** In Bash, single quotes protect `$gte` and `$date` from variable expansion. PowerShell/Windows quoting must be adapted to the shell.

### 6.5. Exporting With `--queryFile`

For complex queries, place the Extended JSON filter in a file:

```json
{
  "status": "PAID",
  "createdAt": {
    "$gte": {
      "$date": "2026-11-14T08:00:00Z"
    }
  }
}
```

Then run:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --queryFile=paid-after-date.json \
  --out=paid-orders-filtered.json
```

Query files may contain sensitive criteria. Control paths and read permissions.

### 6.6. Sort, Limit, and Skip

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --sort='{"createdAt":1,"_id":1}' \
  --limit=2 \
  --out=first-two.json
```

If paginating exports, enforce a **deterministic sort order** and handle concurrent changes to avoid skips or duplicates. Deep `--skip` is costly and provides no snapshot consistency.

**Never** split an actively written production collection into chunks using `--skip`/`--limit` and call that a full backup. Documents inserted or deleted between batches shift positions.

---

## 7. `mongoexport` to CSV: Convenient Yet Loses Type Metadata

Export analytics-friendly columns:

```bash
mongoexport \
  --db=export_backup_lab \
  --collection=orders \
  --type=csv \
  --fields=tenantId,orderId,status,amount,createdAt \
  --out=orders.csv
```

For CSV, **you must specify fields** via `--fields` or `--fieldFile`.

The file contains columns like:

```csv
tenantId,orderId,status,amount,createdAt
tenant-A,A-100,PAID,125.50,2026-11-14T08:00:00.000Z
```

This is an **illustrative format**; exact value formatting depends on Database Tools version and type serialization. Crucially, **CSV carries no BSON type tags** and stores no collection rules.

### 7.1. What CSV Can Lose

- Cannot distinguish string `"0012"` from number `12` without an external schema.
- Lacks ObjectId/Date/Decimal128 type wrappers.
- Cannot naturally preserve nested objects/arrays like BSON structures.
- Lacks indexes, collection validators, and view definitions.
- Cannot reliably distinguish null, missing, and blank in all cases.
- Can hit Unicode/encoding issues in consumer tools.
- Spreadsheets may silently convert long numeric strings into floats/scientific notation.

For example, `sequence = 9007199254740993` exceeds JavaScript's safe integer limit. Any consumer parsing CSV via IEEE-754 floating-point without explicit type rules will corrupt the value.

### 7.2. CSV Is a Data Contract, Not a BSON Copy

When sharing CSVs, maintain a separate schema document:

| Field | Business Type | Rule |
| --- | --- | --- |
| `tenantId` | String | Must not be missing |
| `orderId` | String | Preserve leading zeros if any |
| `amount` | Decimal string | Do not convert via binary float when monetary precision matters |
| `createdAt` | ISO 8601 UTC | Never guess timezone |
| `status` | Enum | NEW/PAID/CANCELLED |

If recipients open CSVs in spreadsheets, watch out for **CSV formula injection**: user-supplied values starting with `=`, `+`, `-`, or `@` may be interpreted as formulas by spreadsheet software. Sanitize exports shared externally, especially free-text fields.

---

## 8. `mongoimport`: Importing JSON/CSV Does Not Recreate the Database

### 8.1. Importing JSON Into Another Collection

```bash
mongoimport \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --type=json \
  --file=orders-canonical.json
```

In this lab, the new target collection starts empty, yielding **4 documents**. `mongoimport` parses Extended JSON v2 Canonical/Relaxed and creates corresponding BSON types.

Verify in `mongosh`:

```javascript
const lab = db.getSiblingDB("export_backup_lab");

lab.orders_from_json.countDocuments({});
// 4

lab.orders_from_json.aggregate([
  {
    $project: {
      _id: 0,
      orderId: 1,
      amountType: { $type: "$amount" },
      createdAtType: { $type: "$createdAt" },
      sequenceType: { $type: "$sequence" }
    }
  }
]).toArray();
```

**Now compare metadata:**

```javascript
lab.orders.getIndexes();
lab.orders_from_json.getIndexes();

lab.getCollectionInfos({ name: "orders" });
lab.getCollectionInfos({ name: "orders_from_json" });
```

`orders_from_json` has only the **default `_id` index**, lacking `uq_tenant_order`, `ix_createdAt_desc`, and the `$jsonSchema` validator defined on the source.

### 8.2. Importing a JSON Array

If the source was exported with `--jsonArray`:

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --type=json \
  --jsonArray \
  --file=orders-array.json
```

Running this into a collection already containing matching `_id` values causes duplicate key errors or conflicts; **do not use this example to overwrite an already-populated collection**. In the lab, pick another target collection or intentionally drop the lab collection first.

### 8.3. Importing CSV

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_csv \
  --type=csv \
  --headerline \
  --file=orders.csv
```

`--headerline` tells the tool the first row holds field names. Omitting it can import the header as data or require separate field configuration.

After import, **never assume** `amount` became Decimal128, `createdAt` became Date, and `sequence` became Int64. CSV lacks type metadata; you must use `--columnsHaveTypes`, explicit field conversions, or custom ETL validation/transforms per Database Tools docs.

Inspect:

```javascript
lab.orders_from_csv.find(
  {},
  { _id: 0, orderId: 1, amount: 1, createdAt: 1 }
).limit(4).toArray();

lab.orders_from_csv.aggregate([
  {
    $project: {
      orderId: 1,
      amountType: { $type: "$amount" },
      dateType: { $type: "$createdAt" }
    }
  }
]).toArray();
```

This is why CSV fits **data interchange** rather than backups.

### 8.4. Import Modes and Idempotency

`mongoimport` supports `--mode` to control duplicate handling:

- `insert`: inserts documents; duplicate keys error.
- `upsert`: updates/inserts by upsert key.
- `merge`: merges fields for matching keys.
- `delete`: deletes records matching input/keys per version semantics.

Example when the target already has a **unique index** on `(tenantId,orderId)` and you want to upsert by that pair:

```bash
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_json \
  --file=orders-canonical.json \
  --mode=upsert \
  --upsertFields=tenantId,orderId
```

**Verify upfront:**

1. Upsert key fields exist in every document.
2. The target has a matching unique index and business uniqueness scope.
3. Update semantics fit (replace vs. merge behave differently).
4. Stale import data will not overwrite newer production edits.
5. Rollback and post-import reconciliation exist.

`--mode=upsert` does not turn an import file into a consistent restore or an exactly-once migration under concurrent writes.

### 8.5. `--drop` Can Destroy Target Data

```bash
# LAB ONLY, NEVER RUN IN PRODUCTION:
mongoimport \
  --db=export_backup_lab \
  --collection=orders_from_csv \
  --drop \
  --type=csv \
  --headerline \
  --file=orders.csv
```

`--drop` deletes the target collection and its indexes prior to importing. **There is no undo** in the import command itself.

Never run `--drop` on a production collection without maintenance approval, a recoverable backup, and traffic halted.

---

## 9. Why Are `mongoexport`/`mongoimport` Not a Complete Backup?

### 9.1. Metadata Loss

`mongoexport` primarily exports **document data**.

Do not expect it to carry:

- Index definitions and compound indexes.
- `unique`, `partialFilterExpression`, and TTL index settings.
- Collection validators and collection options.
- Collection-level default collation.
- Views and view pipelines.
- Users, roles, and privilege assignments.
- Replica set configuration/topology.
- Shard keys, chunk placement, and config metadata.
- Internal credentials, TLS certificates, and encryption keys.
- Backup policies, oplog continuity, and restore checkpoints.

Much of this must be backed up, restored, or redeployed via **other mechanisms** even when using a logical dump.

### 9.2. Broken Data Invariants

Suppose the source collection has:

```javascript
lab.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true }
);
```

Importing JSON into a new collection does not recreate that index. Two documents with identical `(tenantId,orderId)` and different `_id` values can now be inserted, violating source constraints.

That is a business bug that matching `countDocuments()` **completely misses**.

### 9.3. No Cross-Collection Consistency

Suppose:

```text
10:00:00  Export orders starts
10:00:30  Application creates an invoice for a new order
10:01:00  Export invoices starts
```

Exported files may contain an invoice without its corresponding order, or vice versa. JSON files captured at different instants **do not form a cluster-wide point-in-time snapshot**.

`mongoexport` does not capture and replay an oplog to bring multiple collections to a shared timestamp.

### 9.4. Inadequate DR for Full Deployment Loss

Even with millions of exported JSON documents, you still must:

- Provision the new MongoDB server version/topology.
- Configure users/roles, network/TLS/keys.
- Recreate collection schemas/indexes.
- Handle data that mutated mid-export.
- Verify transaction/business consistency.
- Verify application startup/connectivity.
- Absorb slow re-ingestion time.

An export file is great for ETL, yet **fails RTO/RPO** if restoring takes days.

---

## 10. `mongodump`: Logical BSON Backup

`mongodump` is a **MongoDB Database Tools** utility for creating logical dumps.

Unlike JSON exports, dumps store documents in **BSON** alongside metadata files so `mongorestore` can recreate collections and index options.

### 10.1. Dumping the Lab Database

Terminal:

```bash
mongodump \
  --uri="mongodb://127.0.0.1:27017" \
  --db=export_backup_lab \
  --out=./dump-lab
```

Example output structure:

```text
dump-lab/
  export_backup_lab/
    orders.bson
    orders.metadata.json
    orders_from_json.bson
    orders_from_json.metadata.json
    orders_from_csv.bson
    orders_from_csv.metadata.json
```

Only collections existing at dump time appear. Filenames may be encoded per Database Tools conventions.

Distinguish:

- `.bson` holds BSON documents.
- `.metadata.json` holds index definitions and collection metadata (in Extended JSON).
- A logical dump is **not raw WiredTiger data files**.

### 10.2. Why Is BSON Better Than CSV for Logical Backups?

BSON natively preserves `ObjectId`, `Date`, `Decimal128`, `Int32`, `Int64`, binary, and nested fields in MongoDB's format.

`mongodump` also saves collection/index metadata so `mongorestore` restores collection options, rather than flattening everything into a table.

**Still:** a BSON dump remains a logical dump; it omits cluster/infrastructure state (network rules, certs, external passwords, automation config, Search index data, backup retention...).

### 10.3. Dumping a Single Collection

```bash
mongodump \
  --db=export_backup_lab \
  --collection=orders \
  --out=./dump-orders
```

Handy for moving or recovering a small subset, yet not a consistent multi-collection snapshot during active writes.

### 10.4. Archives and gzip

```bash
mongodump \
  --db=export_backup_lab \
  --archive=orders-lab.archive.gz \
  --gzip
```

Writes a single compressed archive instead of a directory tree. `--archive` and `--out` cannot be combined in the same command.

Note that gzip compression **is not encryption**. Backup files holding sensitive data still require encryption, access control, and retention management.

### 10.5. Capacity and Performance of `mongodump`

On heavy workloads, `mongodump` can:

- Read large data volumes from storage.
- Consume significant CPU/network/I/O.
- Compete for cache/resources with production queries.
- Generate huge dump files on destination disks.
- Stretch backup windows as datasets grow.
- Fail strict RTO/RPO goals on multi-TB systems.

For large production systems, prefer coordinated filesystem/cloud snapshots and **PITR** when operational targets demand them. Benchmark both dump and restore on representative datasets, not just backup speed.

---

## 11. `mongorestore`: Restoring BSON and Metadata

Unlike `mongoimport`, `mongorestore` understands `mongodump` structures and recreates collection/index metadata when present.

### 11.1. Restoring to Another Database in the Lab

Assuming you already ran:

```bash
mongodump \
  --db=export_backup_lab \
  --out=./dump-lab
```

Restore into an **empty** `restore_lab`:

```bash
mongorestore \
  --uri="mongodb://127.0.0.1:27017" \
  --dir=./dump-lab \
  --nsInclude='export_backup_lab.*' \
  --nsFrom='export_backup_lab.*' \
  --nsTo='restore_lab.*'
```

**Prerequisite:** destination namespaces contain no conflicting data. `--nsFrom`/`--nsTo` remap namespaces, not individual `_id` fields.

In `mongosh`:

```javascript
const restored = db.getSiblingDB("restore_lab");

restored.orders.countDocuments({});
// 4, if dumped after inserting the 4 orders.

restored.orders.getIndexes();
restored.getCollectionInfos({ name: "orders" });
```

Compared to a JSON `mongoimport`, logical BSON restore recovers the **unique index, `ix_createdAt_desc`, validator, and collection options** from metadata.

### 11.2. Restoring a Compressed Archive

```bash
mongorestore \
  --uri="mongodb://127.0.0.1:27017" \
  --archive=orders-lab.archive.gz \
  --gzip \
  --nsFrom='export_backup_lab.*' \
  --nsTo='restore_lab.*'
```

Restore into a fresh target/database for verification first. If `restore_lab` already exists, make an explicit merge/replace decision; never treat repeated runs as idempotent by default.

### 11.3. `--drop` in `mongorestore` Is Also Dangerous

```bash
# Example ONLY for a lab target:
mongorestore \
  --db=restore_lab \
  --drop \
  ./dump-lab/export_backup_lab
```

Check exact syntax/namespace mapping for your Database Tools version when passing `--db` on a dump directory. **More importantly:** `--drop` deletes the target collection before restoring, risking production data loss.

In real DR recovery, prefer **restoring into an isolated environment**, validating, and cutting over instead of running directly against live production.

### 11.4. Users, Roles, and Database Scope

Users/roles have dedicated backup/restore flags. For example:

- Full-deployment dumps vs. single-database dumps do not always cover the same users/roles.
- `mongodump --dumpDbUsersAndRoles` captures database-scoped users/roles when dumping one DB under supported conditions.
- `mongorestore --restoreDbUsersAndRoles` restores users/roles from a matching dump.
- Restoring the `admin` database follows distinct user/role semantics; follow official docs and permissions strictly.

**Never** assume `mongodump --db shop` captures all cluster-wide users/roles. MongoDB authentication may rely on external auth or certificate identities not stored in business collections.

---

## 12. Consistency When Backing Up an Actively Written Replica Set

Suppose while a dump runs, the app continues creating orders and payments.

```text
t0: mongodump starts
t1: order A is written
t2: payment A is written
t3: mongodump finishes
```

If `mongodump` reads `orders` at t0 and `payments` at t2, the output can reflect **two different points in time**.

### 12.1. What Is `mongodump --oplog`?

On a **replica set member with an oplog**, `mongodump --oplog` captures oplog entries generated during the dump so a restore can reconstruct a consistent state within the dump interval.

Example **on an authorized replica set only, not `mongos`**:

```bash
mongodump \
  --uri="mongodb://rs1.example.net:27017/?directConnection=true" \
  --oplog \
  --archive=rs-backup.archive.gz \
  --gzip
```

Depending on version/URI and topology, connect to an eligible replica set member maintaining an oplog per Database Tools docs.

The dump contains:

- BSON/metadata for all eligible databases in the full dump.
- Oplog entries from the dump window, such as top-level `oplog.bson` in directory mode.

**Without `--oplog`:** if writes occur, the dump is not guaranteed to reflect a single point in time.

### 12.2. Restoring With `--oplogReplay`

Example restoring a **full replica set dump** to an isolated, compatible target:

```bash
mongorestore \
  --uri="mongodb://restore-rs.example.net:27017" \
  --archive=rs-backup.archive.gz \
  --gzip \
  --oplogReplay
```

Follow MongoDB's full tutorial to ensure a fresh target, proper backup ownership, privileges, and restore semantics. The example above **is not for running against live populated production**.

### 12.3. Mandatory Limitations of `--oplog`

Per MongoDB Database Tools:

- Works only on nodes **with an oplog**, such as replica set members.
- Requires a **full dump** of the replica set member.
- **Cannot** combine `--oplog` with `--db`, `--collection`, `--query`, or `--dumpDbUsersAndRoles`.
- `mongodump --oplog` **does not produce a consistent backup of an entire sharded cluster via `mongos`**.
- Certain DDL/config changes mid-dump cause `mongodump --oplog` to fail, such as `renameCollection`, certain `$out`/role changes, and cluster-wide settings.
- The oplog must remain available without rolling over in a way that breaks consistency.

**Never write:**

```bash
# Wrong expectation: --oplog is unsupported with --db filtering.
mongodump --db=shop --oplog --out=./backup
```

### 12.4. Limitations of `--oplogReplay`

Per `mongorestore`:

- Requires a matching full dump created with `--oplog`.
- Cannot arbitrarily combine `--db`, `--collection`, `--nsInclude`, `--nsExclude`, `--nsFrom`, or `--nsTo` with `--oplogReplay`.
- **Sharded clusters do not support `mongorestore --oplogReplay`**.
- Manual `--oplogFile`/`--oplogLimit` requires exact oplog mastery, carrying corruption warnings if misused.

`mongodump --oplog` + `mongorestore --oplogReplay` provides consistency **within the captured full replica set dump**, yet **is not a continuous backup system** retaining days/weeks of oplog for arbitrary PITR.

### 12.5. Oplog Window and FCV

The oplog has finite retention. A long dump where required oplog entries roll off threatens consistency. Also avoid changing **Feature Compatibility Version (FCV)** during dump/restore per version constraints—particularly across time-series format conversions between MongoDB 8.x and 9.0.

Before upgrading, check compatibility across Database Tools, server, FCV, dump, and replay. Never trust an ancient `mongodump` from a much older version without a restore rehearsal.

---

## 13. Sharded Cluster Backups Differ From Replica Set Backups

A sharded cluster distributes data across shards alongside config server metadata.

```text
                      mongos
                        |
           +------------+------------+
           |            |            |
       Shard A RS   Shard B RS    Config RS
        orders A     orders B      routing/
        + indexes    + indexes     chunks
```

Dumping only Shard A misses Shard B. Unsynchronized snapshots across shards allow cross-shard transactions or chunk migrations to cause **missing or duplicate** records when stitched together.

### 13.1. Why Not Just Run `mongodump --oplog` Through `mongos`?

`mongos` is a router and **does not maintain a cluster-wide oplog**. MongoDB documentation explicitly warns against using `mongodump --oplog` for sharded-cluster backups, and `mongorestore --oplogReplay` does not support sharded clusters.

There is no single `oplog.bson` capable of replaying cross-shard transactions and routing changes like a standalone replica set.

### 13.2. Manual Backups Require Coordination

Tutorials for self-managed sharded cluster backups via dumps or filesystem snapshots include sensitive steps:

- Stop the balancer and wait for chunk migrations to finish.
- Pause writes/schema transformations per procedure.
- Ensure consistent state across **every shard** and the CSRS.
- Back up all required components.
- Keep metadata and data restorable together.
- Re-enable components in the documented sequence.
- Verify chunk ownership, routing, and application consistency.

**Never** reduce this to a `mongodump --uri=mongos...` script running while writes and balancing continue and call it a consistent backup.

### 13.3. Managed/Coordinated Backups

MongoDB Atlas and supported coordinated backup solutions handle cluster-wide consistent backups alongside normal cluster activity per feature/version, without manually stopping the balancer like DIY backups.

Still review **exact backup coverage**, retention, PIT availability, restore target limits, and post-restore steps like Search index rebuilds.

### 13.4. Shard Keys and Metadata Are Not CSV

Sharding relies on:

- Collection shard keys.
- Chunks/ranges and placement.
- Config metadata.
- Indexes supporting shard keys and queries.
- Cluster topology and routing.

CSV is just rows of data. Even if you import every document, you **have not restored a sharded deployment** without the right topology, metadata, shard config, and constraints.

---

## 14. Filesystem Snapshots and Physical Backups

A filesystem snapshot captures **block/storage files** at a point in time per filesystem/storage provider mechanics.

Examples:

- LVM snapshots.
- Cloud block-volume snapshots.
- Storage appliance snapshots.
- MongoDB Atlas managed snapshots.

### 14.1. Advantages

- Fast snapshot point creation compared to scanning every collection.
- No serialization of BSON documents to text.
- Preserves internal storage structures intact when valid.
- Better suited to low RTO on large deployments than logical dumps.
- Can integrate with incremental snapshots and PIT recovery.

### 14.2. Crucial Consistency Conditions

**Never** copy `dbPath` with `cp` while `mongod` is running and treat it as a safe physical backup.

Snapshots must follow MongoDB procedures for the storage engine, filesystem, journals, and all volumes. If data and journal reside on separate volumes, they require coordinated snapshot consistency. Sharded clusters additionally require cluster-wide coordination.

A volume snapshot can be **crash-consistent**, yet still fail application/cluster-wide consistency if multiple volumes or shards are captured out of sync.

### 14.3. `fsyncLock()` and Backups

MongoDB offers workflows using `fsync`/`db.fsyncLock()` to pause writes for snapshots in supported scenarios. Because this impacts availability:

- Execute only inside an approved runbook.
- Know the unlock/recovery path.
- Never experiment on production.
- Check version/topology docs.
- Verify in-flight operations/transactions.

**The more shards and volumes involved, the stronger the coordination needed**; never stitch independent snapshots by guesswork.

---

## 15. MongoDB Atlas Cloud Backups and Continuous Cloud Backups

For eligible Atlas deployments/tiers:

### 15.1. Cloud Backups

Atlas provides policy-driven snapshots with hourly/daily/weekly/monthly/yearly retention as configured and supports restores per service terms.

A snapshot captures state at one point. With periodic snapshots alone, writes after the latest snapshot are absent from recovery.

### 15.2. Continuous Cloud Backups (PITR)

Continuous Cloud Backups combine snapshots and oplog history to restore to **a timestamp within the configured restore window**.

Example:

```text
09:00  Latest snapshot
10:00  Orders writes
11:00  Payments writes
14:20  Collection accidentally deleted
14:21  Incident detected
```

With **continuous backup and a PIT window** spanning this interval, you can select a time right before the error at the granularity/scope Atlas supports.

**Do not assume** every Atlas cluster has Continuous Cloud Backups enabled, every project has PITR, or timestamps resolve to arbitrary milliseconds; verify tier, backup policy, retention, and restore mode.

### 15.3. Impact on Search Indexes After Restore

Per Atlas docs, eligible restores preserve **MongoDB Search index definitions**, yet **do not restore prebuilt index data**; Search processes must **initial sync/rebuild** indexes.

This means:

- Source BSON documents may already be restored.
- `$search`/`$vectorSearch` queries may be unavailable or incomplete while indexes rebuild.
- RTO for search-dependent apps must include **index rebuild time**, not just database restore time.

Exact behavior depends on restore type and tier, so rehearse on your actual architecture.

### 15.4. Restore Points and Restore Windows

PITR allows selecting timestamps **within the restore window**. If data was accidentally deleted 40 days ago while PIT history covers only 7 days, you cannot automatically rewind to that exact point.

Backup policy is a **business decision** made before incidents, not something added after data is lost.

---

## 16. RPO and RTO: Choosing Tools by Measurement

### 16.1. RPO — Recovery Point Objective

**RPO** is the maximum acceptable data loss measured in time.

Suppose the business requires:

```text
RPO <= 15 minutes
```

With **6-hour snapshots** and no PIT/continuous oplog coverage, restoring to the latest snapshot can lose nearly six hours of changes—**missing the 15-minute RPO**.

A nightly `mongoexport` has an effective RPO of up to a day and lacks snapshot consistency.

### 16.2. RTO — Recovery Time Objective

**RTO** is the maximum time to restore service to acceptable levels.

RTO is more than `mongorestore` runtime. It includes:

```text
Detect incident
  + Decide restore point/target
  + Provision infrastructure
  + Transfer/restore data
  + Rebuild indexes/Search indexes
  + Reconfigure credentials/network
  + Validate data and business invariants
  + Reconnect applications
  + Resume service
```

If dumping 1 TB takes 2 hours while restoring + rebuilding indexes takes 20 hours, a "fast backup" says nothing about RTO.

### 16.3. RPO Calculation Example

```text
09:00  Snapshot backup
14:20  Incident
14:21  Incident detected
```

Restoring the 09:00 snapshot risks losing **5 hours 20 minutes** of valid writes between 09:00 and 14:20.

Do not say "the system's RPO is 5 hours 20 minutes" from one incident alone. That is the **data loss exposure of that scenario**; RPO is the business target that backup frequency and architecture must meet.

### 16.4. Tool Selection Matrix by RPO/RTO

| Need | Candidate Tool/Approach | Condition |
| --- | --- | --- |
| Weekly data export for BI | `mongoexport` CSV | Non-point-in-time snapshot acceptable |
| Load seed data | `mongoimport` JSON | Schema/indexes prepared separately |
| Restore a small test database | `mongodump`/`mongorestore` | Metadata, types, and target compatible |
| Consistent replica set dump during writes | `mongodump --oplog`/`mongorestore --oplogReplay` | Full dump, oplog, no blocking DDL |
| Sharded cluster production DR | Coordinated backup/snapshot | Cluster-wide consistency, config metadata |
| 15-minute PITR | Continuous backup with oplog history | Restore window, tier, policy, drills |
| Predictable RTO for very large datasets | Snapshots/managed backups | Restore throughput, index rebuilds, network |
| Security compliance and long-term archival | Encrypted/immutable/offsite backups | Retention, auditing, recovery drills |

---

## 17. Business Consistency Is More Than Document Counts

Suppose the system stores:

```javascript
// An order.
{
  _id: "order-100",
  amount: NumberDecimal("100.00"),
  status: "PAID"
}
```

```javascript
// A linked payment.
{
  _id: "payment-100",
  orderId: "order-100",
  amount: NumberDecimal("100.00")
}
```

If you export `orders` at 09:00 and `payments` at 09:05, a transaction occurring in between leaves the files inconsistent.

Invariants to verify post-restore:

- Every payment has a matching order.
- Amounts and currency mappings match.
- Unique business keys have no duplicates.
- Foreign/reference relationships are valid.
- Sequence/version counters have not regressed.
- Users/roles hold proper privileges.
- Indexes, validators, and TTL rules work.
- Report aggregates fall within expected bounds.
- Change streams/consumers have checkpoint resume/rebuild plans.

Checking only that `countDocuments()` matches pre-backup numbers **is insufficient**. With TTL or post-restore-point writes, differing counts can even be expected; always reconcile against the exact snapshot timestamp.

---

## 18. Strategy for Verifying a Backup

### 18.1. Backup Artifact Inventory

Every backup should have a manifest/metadata tracked separately from raw data:

```yaml
backupId: "backup-2026-11-14-0900"
environment: "staging"
deploymentType: "replicaSet"
sourceCluster: "rs0"
backupMethod: "mongodump-with-oplog"
startedAtUtc: "2026-11-14T09:00:00Z"
completedAtUtc: "2026-11-14T09:03:42Z"
mongodbVersion: "document-from-source"
databaseToolsVersion: "document-from-tools"
format: "archive-gzip"
encryptedAtRest: true
checksumAlgorithm: "SHA-256"
retentionClass: "daily"
restoreTestStatus: "pending"
```

This is an **example manifest**, not an automatic MongoDB output format. Record real timestamps and versions, never hardcoded placeholders.

### 18.2. Technical Artifact Checks

- Backup command exited cleanly.
- Output file exists, reasonable size, not abnormally 0 bytes.
- Destination storage has enough capacity.
- Checksum computed and stored outside the artifact directory.
- File is encrypted with proper access controls.
- No secrets leaked in logs.
- Retention job will not prematurely purge the backup.
- If oplog is included, dump and oplog segment replay cleanly.

Still, **a valid checksum does not prove a backup is restorable**.

### 18.3. Restore Rehearsal

Reliable test workflow:

1. Provision an isolated target cluster matching required version/topology.
2. Provide proper credentials/secrets and restrict network access.
3. Restore the artifact to the target.
4. Verify BSON types and document counts as of snapshot time.
5. Verify indexes, validators, views, TTL, and users/roles.
6. Run application smoke tests.
7. Verify business invariants.
8. Test search/index readiness if using `$search`/`$vectorSearch`.
9. Measure elapsed time from simulated incident to service-ready.
10. Document results, failures, and runbook updates.

A backup has value only once the team **has proven it can restore**.

### 18.4. Items to Track Outside the MongoDB Dump

- Secret manager references, certificate rotation plans.
- TLS CA/public trust chains and recovery access to private keys.
- Infrastructure as Code, firewalls/DNS/load balancers.
- Authentication provider mappings.
- KMS configuration and encryption key recovery.
- Application schema migration versions.
- Job schedulers, Kafka offsets/consumer checkpoints, integration configs.
- Search index definitions per backup coverage.
- Monitoring/alerting and backup retention policies.

Never drop private keys into an unencrypted backup folder and call it a "full backup."

---

## 19. Security for Exported Data and Backups

### 19.1. JSON/CSV Exports Are Also Sensitive Data

A `users.csv` file can hold emails, phone numbers, addresses, order history, and internal fields. It risks being:

- Emailed to the wrong recipient.
- Uploaded to a public Drive/bucket.
- Committed to a repository.
- Saved on an unencrypted laptop.
- Loaded into an unprotected BI demo/test environment.
- Opened in a spreadsheet vulnerable to formula injection.

**Data exports are never exempt from PII protection policies.**

### 19.2. Backups Require Dedicated Protection

- Encryption at rest and in transit.
- Least-privilege access control.
- Audited retention policies.
- Copies stored outside the production failure domain.
- Immutable/WORM or backup compliance controls where required.
- Separation between deleting production data and deleting backups.
- Verified recoverability of encryption keys.
- Zero user credentials exposed in backup scripts.

### 19.3. The 3-2-1 Rule

A common guideline:

- **3 copies** of data.
- **2 media/storage types** or independent failure domains.
- **1 offsite copy**.

This is an operational principle, not an automatic MongoDB setting. For cloud-managed backups, assess regions, account/project isolation, immutable retention, and ransomware recoverability.

---

## 20. Tool Selection Scenarios

### 20.1. Sending a Sales Report to Finance

**Requirement:** CSV containing `orderId`, `createdAt`, `amount`, `status`; no indexes, validators, or users needed.

**Choice:** `mongoexport --type=csv --fields=...` with required filtering/anonymization.

**Watch out for:** Currency precision/Decimal128, timezones, formula injection, and schema mapping.

### 20.2. Ingesting a Partner Catalog

**Requirement:** Receive JSON/CSV files and upsert by product SKU.

**Choice:** ETL validation + `mongoimport` or an ingestion service; create the unique index first and define explicit upsert semantics.

**Watch out for:** Product SKU collisions, stale data overwriting newer edits, missing validation, and lack of automatic cross-collection transactions.

### 20.3. Moving One Collection Between Lab Databases

**Requirement:** Preserve BSON types and indexes.

**Choice:** `mongodump --db ... --collection ...` + `mongorestore` as appropriate, or a migration tool.

**Watch out for:** Namespace mapping, metadata versions, and target schema compatibility.

### 20.4. Daily Backup of a Small Replica Set

**Requirement:** Consistent logical dump while writes continue, with tolerable RTO.

**Choice:** `mongodump --oplog` + `mongorestore --oplogReplay` on a full replica set member dump, meeting all prerequisites and limits.

**Watch out for:** Do not combine `--db`, avoid concurrent DDL/user-role changes during dump, watch oplog window, and test restores.

### 20.5. Sharded Cluster With Cross-Shard Transactions

**Requirement:** Consistent backup without prolonged downtime.

**Choice:** Coordinated backup service (Atlas or supported platform) and formal backup policy.

**Watch out for:** Never rely on `mongodump --oplog` via `mongos`; manual backups require stopping balancer/writes/schema changes per docs.

### 20.6. Recovering to Seconds/Minutes Before Accidental Deletion

**Requirement:** PITR within a restore window and acceptable recovery time.

**Choice:** Continuous Cloud Backup/PIT service per availability and policy.

**Watch out for:** Periodic snapshots alone do not provide PITR; oplog retention/history must suffice, target must be approved, and search indexes may rebuild.

### 20.7. Multi-TB Dataset, 30-Minute RTO

**Requirement:** Faster restore than logical dump/import.

**Choice:** Evaluate snapshot/direct-attach/managed backup topologies suited to scale.

**Watch out for:** Only an end-to-end benchmark proves RTO is achievable; index rebuilds, replica sync, network, and app validation still take time.

---

## 21. Estimating Cost and Duration

A rough throughput formula:

\[
T_{\mathrm{transfer}} =
\frac{\mathrm{BackupSizeBytes}}{\mathrm{EffectiveBytesPerSecond}}
\]

**Hypothetical** example:

- Backup artifact: **800 GB**.
- Effective restore throughput: **100 MB/s** (decimal).

\[
T = \frac{800{,}000\ \mathrm{MB}}{100\ \mathrm{MB/s}}
  = 8{,}000\ \mathrm{s} \approx 2.22\ \mathrm{hours}
\]

Transferring/writing 800 GB alone takes over two hours under these assumptions, excluding:

- Cluster provisioning.
- BSON decoding during restore.
- Index rebuilds.
- Replica sync.
- Search index initial sync.
- Business validation.
- App reconnection.

If RTO is 30 minutes, this approach **fails**, regardless of how simple the backup command is.

### 21.1. Total Cost of Ownership

A TCO model:

```text
Monthly backup TCO =
   snapshot/object storage
 + replication / cross-region copies
 + oplog/continuous backup retention
 + data transfer / egress
 + encryption / KMS
 + restore test infrastructure
 + monitoring / alerting
 + operator engineering / on-call
```

`mongoexport` produces cheap, readable files, yet **cannot** substitute for these investments when disaster recovery is required.

### 21.2. Cost Scales With RPO/RTO

- Lower RPO typically requires continuous change capture.
- Lower RTO often demands faster restore mechanisms, warm standbys, or pre-provisioned capacity.
- Longer retention increases storage and compliance complexity.
- Running restore rehearsals adds cost while preventing unrecoverable failures.

Do not optimize only for backup creation cost; optimize **cost vs. recoverability** against SLOs.

---

## 22. Before-and-After Import/Restore Comparison Lab

### 22.1. Execution Steps

1. Create `export_backup_lab.orders` with 4 documents, a validator, and two indexes.
2. Run `mongoexport --jsonFormat=canonical` to `orders-canonical.json`.
3. Run `mongoimport` to `orders_from_json`.
4. Run `mongodump --db export_backup_lab --out dump-lab`.
5. Run `mongorestore` into an empty `restore_lab` database.
6. Use `mongosh` to compare document counts, types, indexes, and collection options.

### 22.2. Verifying Document Counts

```javascript
const source = db.getSiblingDB("export_backup_lab");
const restored = db.getSiblingDB("restore_lab");

printjson({
  source: source.orders.countDocuments({}),
  importedJson: source.orders_from_json.countDocuments({}),
  restoredBson: restored.orders.countDocuments({})
});
```

Starting from the clean fixture with each step run once into an empty target:

```javascript
{
  source: 4,
  importedJson: 4,
  restoredBson: 4
}
```

**Matching counts do not certify a complete backup.**

### 22.3. Checking Data Types

```javascript
function typesFor(dbRef, collection) {
  return dbRef.getCollection(collection).aggregate([
    {
      $project: {
        _id: 0,
        orderId: 1,
        amountType: { $type: "$amount" },
        dateType: { $type: "$createdAt" },
        sequenceType: { $type: "$sequence" }
      }
    },
    { $sort: { orderId: 1 } }
  ]).toArray();
}

printjson(typesFor(source, "orders"));
printjson(typesFor(source, "orders_from_json"));
printjson(typesFor(restored, "orders"));
```

Extended JSON canonical preserves BSON types on JSON import if no lossy transformation occurs in between. BSON dump/restore preserves native types.

### 22.4. Checking Indexes and Validators

```javascript
printjson(source.orders.getIndexes());
printjson(source.orders_from_json.getIndexes());
printjson(restored.orders.getIndexes());

printjson(source.getCollectionInfos({ name: "orders" }));
printjson(source.getCollectionInfos({ name: "orders_from_json" }));
printjson(restored.getCollectionInfos({ name: "orders" }));
```

Expected:

- **Source:** `_id`, `uq_tenant_order`, `ix_createdAt_desc`, and validator.
- **JSON import:** only default `_id`, missing source validator and indexes.
- **BSON restore:** compatible metadata from the dump rebuilds indexes/validators when restored with proper options.

Exact restore details can vary by version, namespace remapping, and metadata compatibility; always inspect empirically rather than assuming identical properties.

### 22.5. Testing the Unique Invariant

On `orders_from_json` (lab only), since it lacks the unique `(tenantId,orderId)` index:

```javascript
const imported = source.orders_from_json;
const copy = imported.findOne({ orderId: "A-100" });

// Same logical business key, new _id.
imported.insertOne({
  ...copy,
  _id: new ObjectId()
});
```

The second document succeeds because the imported collection lacks `uq_tenant_order`. The exact same insert against the source triggers `E11000` (assuming validator passes).

This demonstrates how **losing metadata alters business correctness** even when BSON types stay intact.

---

## 23. Automating Backups: Beyond Running Cron

A production job needs these stages:

```text
Scheduled trigger
       |
Preflight health/capacity
       |
Create backup artifact
       |
Check exit status + artifact manifest
       |
Encrypt / upload / immutability
       |
Verify checksum/inventory
       |
Retention / lifecycle
       |
Periodic isolated restore test
       |
Measure RPO/RTO and alert on failures
```

### 23.1. Preflight Conditions

- Cluster/quorum is healthy.
- Credentials and TLS are valid.
- Destination disk has sufficient free space.
- If dumping a replica set: sufficient oplog window, no incompatible DDL.
- If manual sharded backup: balancer/write pauses properly satisfied.
- Backup destination is not the same single production volume.
- No secrets exposed in logs or command lines against policy.

### 23.2. Monitoring

| Metric | Why It Matters |
| --- | --- |
| Timestamp of last successful backup | Tracks RPO compliance |
| Backup duration | Detects growth or throughput degradation |
| Artifact size | Catches abnormally empty/truncated outputs |
| Checksum/verification | Detects file corruption |
| Backup job failure rate | Detects coverage gaps |
| Restore rehearsal duration | Measures real RTO |
| Oplog/PIT retention window | Shows earliest recoverable point |
| Storage/backup cost | Tracks capacity and budget |
| Number of isolated copies | Protects against shared failure domains |
| Search index rebuild time | Determines end-to-end app readiness |

### 23.3. Alerting

Do not alert solely on `job exit code != 0`. Alert on:

- No successful backup within the **expected window**.
- Abnormally small or suspicious backup artifact.
- Snapshot/PIT retention falling short of RPO.
- Failed restore drill.
- Expiring KMS keys/credentials.
- Backup storage full or write-permission lost.
- Restore duration exceeding RTO.
- Failed offsite replication.

---

## 24. Common Mistakes

| Mistake | Reality | Remediation |
| --- | --- | --- |
| "Daily `mongoexport` equals a full backup" | Exports lack full metadata/consistency | Adopt a real backup strategy |
| "JSON always loses all BSON types" | Extended JSON wraps many types | Use Canonical + round-trip tests |
| "CSV preserves Date/Decimal128 like BSON" | CSV has no type tags | Define explicit schema and conversions |
| "`mongoexport` preserves indexes" | Exports documents only | Use dump/restore or IaC index creation |
| "`mongoimport` recreates validators" | Not from JSON exports | Provision schemas/indexes separately |
| "`mongoimport` is always idempotent" | Inserts can duplicate or error | Use upsert keys/unique indexes and retry plans |
| "`--drop` deletes only documents" | Drops the collection and its indexes before import/restore | Use only intentionally |
| "Plain `mongodump` is consistent across writes" | Without `--oplog`, scans span multiple times | Replica set full dump + oplog or managed backup |
| "`mongodump --db x --oplog` is valid" | `--oplog` requires a full dump | Do not pass scope-limiting options |
| "`--oplog` on `mongos` backs up all shards" | No shared cluster oplog exists | Use coordinated sharded backups |
| "`mongorestore --oplogReplay` works on sharded clusters" | Unsupported | Use sharded-compatible restore workflows |
| "A BSON dump is a filesystem copy" | Logical, not raw WiredTiger files | Distinguish logical vs. physical |
| "Copying `dbPath` while running is a snapshot" | Not guaranteed consistent | Follow official snapshot docs |
| "Stopping the balancer suffices for sharded backups" | Writes, schema ops, and transactions continue | Follow full end-to-end tutorial |
| "Every Atlas cluster automatically has PITR" | Depends on tier and backup policy | Verify continuous backup settings |
| "Having a backup guarantees it restores" | Files may be corrupt or missing keys/metadata | Run restore rehearsals |
| "RPO and RTO are the same" | RPO = data loss; RTO = downtime | Measure separately |
| "Daily snapshots satisfy a 15-minute RPO" | Gap between snapshots is too wide | Use continuous oplog/PIT |
| "Once DB restores, the app works immediately" | Index builds, Search sync, and migrations take time | Measure end-to-end RTO |
| "Backups on the same disk as production are safe" | Disk/region outage wipes out both | Keep offsite/isolated copies |
| "Gzip is encryption" | Gzip only compresses | Encrypt + enforce access controls |
| "No need to track CA/KMS/secret recovery" | Backups may be unreadable | Maintain external DR inventory |
| "Matching counts mean a clean restore" | Types, indexes, and links may still be broken | Run integrity checks |
| "Internal CSVs have no security risk" | Contain PII and formula-injection risk | Enforce data governance |

---

## 25. Practice Exercises

### Exercise 1 — Tool Classification

Pick `mongoexport`, `mongoimport`, `mongodump`/`mongorestore`, or managed backup:

1. Send orders CSV to BI.
2. Load a JSON catalog into a lab collection.
3. Move a test database preserving BSON/indexes.
4. Recover an entire sharded cluster to before an incident.

**Answer:** 1 export, 2 import, 3 dump/restore, 4 coordinated backup/PITR per deployment.

### Exercise 2 — Role of `mongoexport`

Why does MongoDB state `mongoexport` is **not a deployment backup tool**? Name at least six metadata/system states absent from CSV exports.

### Exercise 3 — Extended JSON

Write Extended JSON canonical representations for:

- `_id = ObjectId("650000000000000000000001")`.
- `amount = Decimal128("125.50")`.
- `quantity = Int32(2)`.
- `sequence = Int64("9007199254740993")`.

**Hint:** Use `$oid`, `$numberDecimal`, `$numberInt`, `$numberLong`.

### Exercise 4 — Relaxed vs. Canonical

Why is Canonical better than relaxed JSON when BSON type fidelity matters? Does Canonical carry collection indexes?

**Answer:** Canonical encodes more types explicitly, and **does not** carry index metadata.

### Exercise 5 — Importing a JSON Array

If exported with `--jsonArray`, which flag is needed on import?

**Answer:** `mongoimport --jsonArray`.

### Exercise 6 — CSV Schema

Export `amount`, `createdAt`, and `sequence` to CSV. Name three failure modes when a recipient reads the file without a schema contract.

**Hint:** Decimal precision, Date timezone/type, Int64 overflow.

### Exercise 7 — Exporting PAID Orders

Write `mongoexport --query` fetching only `status: "PAID"` from the lab collection. How many documents are in the fixture?

**Answer:** **2**.

### Exercise 8 — Importing With a Unique Business Key

The source has unique `(tenantId,orderId)`, while the newly imported collection has only the `_id` index. What duplicate can the target now accept?

**Answer:** Two different `_id` values sharing the same `(tenantId,orderId)`.

### Exercise 9 — `--drop`

If you run `mongoimport --drop` on a production collection, what happens to existing indexes and documents?

**Answer:** The collection is dropped, deleting both existing indexes and documents prior to import.

### Exercise 10 — Dump Output

What file types does `mongodump --db=export_backup_lab --out=./dump-lab` typically create? What does each contain?

**Answer:** `.bson` holds documents; `.metadata.json` holds metadata/index options.

### Exercise 11 — BSON vs. CSV

Why is BSON better than CSV for restoring Decimal128/Date/ObjectId? Why is a BSON dump still not a physical snapshot?

### Exercise 12 — Actively Written Replica Set

A full `mongodump` runs while writes continue. Without `--oplog`, are collections guaranteed to reflect a single timestamp?

**Answer:** No. Use `--oplog` when replica set prerequisites are met, or another consistent backup mechanism.

### Exercise 13 — Oplog Constraints

Is the following command valid?

```bash
mongodump --db=shop --oplog --out=./backup
```

**Answer:** No. `--oplog` requires a full replica set member dump and cannot be combined with `--db`.

### Exercise 14 — Oplog Replay

A full replica set dump was created with `--oplog`. Which tool/flag replays the oplog on restore?

**Answer:** `mongorestore --oplogReplay` on a supported topology.

### Exercise 15 — Sharded Cluster

Why doesn't `mongodump --oplog` through `mongos` provide a consistent whole-cluster backup? Which components must be coordinated?

**Hint:** Shards, CSRS, balancer, concurrent writes/schema operations, and restore metadata.

### Exercise 16 — Filesystem Snapshot

Why is running `cp -r /var/lib/mongodb` while `mongod` runs not equivalent to a consistent storage snapshot?

### Exercise 17 — RPO

Last snapshot at 09:00, incident at 14:20, no PIT coverage. How much valid data could be lost?

**Answer:** Up to **5 hours 20 minutes** since the snapshot in this scenario.

### Exercise 18 — RTO

Restoring requires transferring 800 GB at 100 MB/s effective speed. How long does transfer alone take?

**Answer:** 8,000 seconds ≈ **2 hours 13 minutes 20 seconds**.

### Exercise 19 — Atlas PITR

What prerequisites are required to recover right before an accidental delete at 14:20? Why do 6-hour snapshots fail a 15-minute RPO?

### Exercise 20 — Search Indexes After Restore

A system uses MongoDB Vector Search. Source BSON restores, yet Search index rebuild takes 45 minutes. When should RTO for the search API stop?

**Answer:** Only when search/indexes are queryable and the API meets SLOs—not merely when MongoDB source documents finish restoring.

### Exercise 21 — Restore Verification

Design an at-least-eight-step checklist: documents, types, indexes, validators, roles, relationships, app smoke tests, monitoring, Search freshness, and RTO.

### Exercise 22 — Backup Security

A backup archive is gzipped and stored on the same disk as production. List at least four risks.

**Hint:** Unencrypted, shared failure domain, ransomware, missing offsite retention, missing access controls.

### Exercise 23 — Backing Up Users/Roles

Does `mongodump --db shop` automatically back up all users/roles across every database? Name options or procedures to check.

**Answer:** Not by default. Check `--dumpDbUsersAndRoles`/`--restoreDbUsersAndRoles` and how the `admin` database is handled per docs.

### Exercise 24 — Full Backup vs. Data Export?

A team runs `mongoexport` on every collection over several minutes and verifies counts match. What evidence is still missing before calling this a production backup?

**Hint:** Consistency, metadata, PIT capability, RBAC, topology, secrets, RPO/RTO, and rehearsals.

### Exercise 25 — Three-Environment Strategy

Design policies for:

- Dev: non-sensitive sample data, reproducible.
- Staging: needs test data and schema replay.
- Production: 15-minute RPO, 1-hour RTO, sharded cluster with Search indexes.

Select tools, retention, monitoring, and restore verification.

### Exercise 26 — Comparing TCO

A logical dump is cheap to produce yet takes 12 hours to restore; a snapshot service costs more yet restores in 45 minutes. If max RTO is one hour, which is viable?

**Answer:** The option with a proven sub-one-hour RTO; lower creation cost never compensates for violating a mandatory SLA.

### Exercise 27 — Indexes/Validators After Import

Run the lab: `orders` → JSON export/import → BSON dump/restore. Compare `getIndexes()` and `getCollectionInfos()`. Explain why the same four documents behave differently.

### Exercise 28 — Real-World DR Plan

Write a runbook for an accidental collection drop in production:

1. Halt ongoing damage.
2. Identify the last safe timestamp.
3. Choose the backup/restore point.
4. Restore to an isolated target.
5. Verify data and metadata.
6. Select cutover/migration strategy.
7. Verify application operation.
8. Record data loss and recovery duration.
9. Update policies/automation.

Explain which steps **cannot be replaced by `mongoimport` of a CSV file**.

---

## 26. Summary

To choose the right MongoDB backup/restore tool, start with the **business objective**:

1. **`mongoexport`** exports JSON/CSV — ideal for integration, reporting, and data transfer; **not a deployment backup**.
2. **`mongoimport`** ingests JSON/CSV/TSV into a collection — requires managing BSON types, indexes, uniqueness, validation, and import modes; does not restore topology.
3. **`mongodump`** creates BSON logical dumps and metadata; **`mongorestore`** rebuilds collection/index options within supported scope.
4. **`mongodump --oplog`** with **`mongorestore --oplogReplay`** supports consistent full dumps of a **replica set member** under strict constraints; never combine with database/collection filtering flags.
5. **Sharded clusters** require coordinated backup/restore, never `--oplog` via `mongos` as if a shared oplog existed.
6. **Snapshots/managed backups** suit larger deployments and lower RTOs, provided proper filesystem/cluster consistency procedures are followed.
7. **PITR** requires continuous history/retention and eligible continuous backup capabilities—not just JSON/BSON files.
8. **RPO and RTO** drive strategy; saving a file does not guarantee restoring a service.
9. **Backup security** requires encryption, offsite/immutable copies, access controls, and key recovery.
10. **Restore rehearsals** are the ultimate proof: verify data types, indexes, validators, users/roles, business invariants, and application readiness.

**The final question is never "did we export the same row count?" — it is "if production goes down, can we restore the exact data, metadata, and service within our committed RPO/RTO?"**

### Official MongoDB Documentation

- [mongoexport — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongoexport/) — JSON/CSV export; docs confirm it is **not a deployment backup tool**.
- [mongoimport — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongoimport/) — importing JSON/CSV/TSV, modes, `--drop`, `--headerline`.
- [mongoimport Examples](https://www.mongodb.com/docs/database-tools/mongoimport/mongoimport-guide/) — BSON-specific types via Extended JSON.
- [MongoDB Extended JSON v2](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/) — Canonical/Relaxed and BSON representations.
- [mongodump — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongodump/) — BSON backup, `--archive`, `--gzip`, `--oplog`.
- [mongorestore — MongoDB Database Tools](https://www.mongodb.com/docs/database-tools/mongorestore/) — metadata restore, oplog replay, and limitations.
- [Back Up and Restore with MongoDB Tools](https://www.mongodb.com/docs/manual/tutorial/backup-and-restore-tools/) — logical backup workflows.
- [Back Up Self-Managed Deployment with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-with-filesystem-snapshots/) — block-level backups and consistency.
- [Back Up Sharded Cluster with Database Dump](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-database-dumps/) — requirements for manual sharded backups.
- [Back Up Sharded Cluster with Filesystem Snapshots](https://www.mongodb.com/docs/manual/tutorial/backup-sharded-cluster-with-filesystem-snapshots/) — stopping writes/balancer and coordination.
- [Manage Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/tutorial/manage-sharded-cluster-balancer/) — pausing balancing for manual backups.
- [Atlas Backup Guidance](https://www.mongodb.com/docs/atlas/architecture/current/backups/) — Cloud Backups, continuous backups, RPO/RTO.
- [Restore from Continuous Cloud Backup](https://www.mongodb.com/docs/atlas/backup/cloud-backup/restore-from-continuous/) — PIT recovery and Search index rebuild considerations.
- [Recover a Point in Time](https://www.mongodb.com/docs/atlas/recover-pit-continuous-cloud-backup/) — restore window, timestamps, and requirements.
