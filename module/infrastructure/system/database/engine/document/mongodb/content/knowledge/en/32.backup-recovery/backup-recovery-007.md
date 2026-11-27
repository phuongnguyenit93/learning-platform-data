# Selective Recovery, Namespaces, Indexes, and Schema Validation in MongoDB

Imagine an e-commerce service using MongoDB with multiple collections: `customers`, `orders`, `payments`, and `products`. An erroneous operation deletes some orders, while the other collections keep running normally and accepting new data. Restoring the **entire database** from an older backup could overwrite newer orders, customers, or payments created after the backup timestamp. Restoring a single collection without checking data relationships could leave **orders pointing to nonexistent customers or payments**. Moreover, restoring documents alone is not enough: **indexes**, **collection options**, and **schema validators** directly affect post-restore correctness and performance.

In the **Backup and Recovery** chapter of the **Database Engine Document MongoDB** module, this lesson explains **selective recovery**, scoping by **namespace**, handling **indexes** and **schema validation**, and building a safe operational workflow when recovering partial data from a backup.

Objectives:

1. Distinguish full cluster, single database, single collection, and document-subset recovery.
2. Use `mongodump`/`mongorestore` with `--nsInclude`, `--nsExclude`, `--nsFrom`, and `--nsTo`.
3. Understand when `--drop` destroys existing data and why restoring into a **staging namespace** first is safer.
4. Understand how backup metadata relates to **indexes, collation, collection options, and validators**.
5. Distinguish restoring **data** from restoring **schema/configuration** and handle legacy data failing current validators.
6. Verify recovery results across **counts, integrity, indexes, business relationships, and access controls**.
7. Recognize limits of selective restore regarding **point-in-time consistency**, Atlas, sharded clusters, and actively written workloads.

> **Safety first:** commands capable of modifying or deleting data in this lesson are set in a lab database context. Never run `mongorestore --drop`, `collMod`, or data copies into production without verifying namespace, backup, affected targets, and rollback plans.

## 1. What Are the Levels of "Selective Recovery"?

Not every "partial restore" request operates at the same level.

| Level | Question | Tool/Approach |
| --- | --- | --- |
| **Full deployment/cluster** | Restore system state after a major outage | Snapshot/cluster restore, suitable backup platform |
| **Single database** | Recover only the `shop_app` database | Logical dump/restore scoped by namespace |
| **Single collection** | Recover only `shop_app.orders` | `mongorestore --nsInclude` |
| **Group of collections** | Recover `orders` and `payments` | Multiple `--nsInclude` flags or matching patterns |
| **Rename database/collection on restore** | Load `shop_app.orders` as `restore_review.orders` | `--nsFrom` / `--nsTo` |
| **Document subset by filter** | Rescue only order `ORD-1001` | Restore collection to staging, then filter/copy safely |
| **Index/validator structure only** | Reapply metadata without replacing data | Compare metadata, then create indexes/`collMod` carefully |
| **State at a specific timestamp** | Recover to before a bad operation occurred | Point-in-time restore via suitable backup + logs/snapshot |

**Key distinction:** `mongorestore` scopes by **namespace**; it does not provide a general `--query='{orderNo:...}'` flag to pull arbitrary documents from a BSON dump and merge them safely into production. When only a few documents are needed, the standard pattern is **restoring the whole collection into staging** and using a query/app migration to bring those documents back.

## 2. What Is a Namespace in MongoDB?

A **namespace** identifies a collection within a database, typically written as:

```text
<database>.<collection>
```

Examples:

```text
shop_app.orders
shop_app.customers
shop_app.payments
audit.events
restore_review.orders
```

Here:

- `shop_app` or `restore_review` is the database name.
- `orders` is the collection name.
- `shop_app.orders` and `restore_review.orders` are **two distinct namespaces**, despite sharing the collection name `orders`.

### Source Namespace vs. Destination Namespace

During restore:

```text
Backup contains:
  shop_app.orders
          |
          | --nsFrom shop_app.orders
          | --nsTo   restore_review.orders
          v
Target MongoDB:
  restore_review.orders
```

Renaming namespaces lets you inspect backup data **without replacing the live `shop_app.orders` collection**.

### Namespaces Are Not Access Control

A namespace is only a data identifier. Restoring into a database named `restore_review` **does not automatically isolate read access to sensitive data**: check user roles, network access, target environment, and data policies, especially if backups hold PII or secrets.

## 3. Logical Backup: What Does `mongodump` Store?

`mongodump` belongs to **MongoDB Database Tools**. It exports MongoDB data as a BSON dump; in directory mode, it typically writes files such as:

```text
dump/
  shop_app/
    orders.bson
    orders.metadata.json
    customers.bson
    customers.metadata.json
    payments.bson
    payments.metadata.json
```

Meaning:

- `orders.bson`: dumped **documents** for the collection.
- `orders.metadata.json`: **metadata** for restoration, generally including collection options and index definitions when captured.
- Corresponding files for other collections.

In practice, filenames and layouts depend on dump mode, collection type, tool, and version. Never hand-edit backup BSON/metadata files like plain text JSON and expect `mongorestore` to accept arbitrary modifications.

### Archive Backups

Instead of a directory, you can write an **archive**:

```bash
# Run on an authorized backup host, passing URI via secure environment variable.
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --archive="shop_app.archive" \
  --gzip
```

`--archive` stores dump contents in Database Tools' archive format; `--gzip` compresses the stream. This is **not a generic ZIP file you can unzip and edit like an SQL backup**. Restores must pass the matching archive/gzip flags.

### A Dump Is Not Automatically an App-Consistent Snapshot

If multiple collections receive writes during backup, documents read at different times may not form **an atomic database-wide business state**. Modes like `mongodump --oplog` or backup platforms with point-in-time capabilities have specific prerequisites and limits. Never call a selective dump "an exact millisecond snapshot of every collection" without verifying backup methodology and workload.

## 4. How Does `mongorestore` Read BSON and Metadata?

`mongorestore` re-imports BSON data and can apply accompanying collection metadata/indexes depending on flags. Components:

```text
mongodump output
  |
  +-- BSON document data --------> collection documents
  |
  +-- collection options --------> collection configuration
  |                                 (when metadata exists and is supported)
  |
  +-- index specifications ------> index definitions/builds
                                    (when selected for restoration)
```

Therefore, "documents finished restoring" **does not equal**:

- All indexes exist and built cleanly.
- Unique constraints match the old database.
- Default collation matches the old setup.
- `validator`, `validationLevel`, and `validationAction` match the source environment.
- Data satisfies all current business rules.

You must **inspect command output and verify post-restore state**. Reported inserted document counts do not substitute for confirming index builds and collection options.

### Tools, Server, and Versions

MongoDB Database Tools carry their own version independent of MongoDB Server. Across different server/tool versions, certain features or index/collection options may have compatibility constraints. Always check:

```bash
mongodump --version
mongorestore --version
```

And record:

```javascript
db.version()
```

When restoring to MongoDB Atlas or a different-version cluster, check MongoDB Database Tools/driver/server compatibility docs before running.

## 5. End-to-End Scenario: Recovering Specific Orders

Suppose the source database `shop_app` has:

```text
shop_app
  ├── customers
  ├── orders
  ├── payments
  └── products
```

An accidental delete removes order `ORD-1001`. Other production orders keep receiving writes. We do not want to overwrite all of `shop_app.orders`.

Safe workflow:

```text
Backup shop_app.orders
        |
        v
Restore to restore_review.orders
        |
        v
Review data / indexes / validator
        |
        v
Locate ORD-1001 and dependencies
        |
        v
Controlled selective copy plan
        |
        v
Monitor / reconcile production
```

**The restored copy must live in a namespace that never collides with active data.** This minimizes the risk of overwriting via mistaken flags.

### Sample Data Definition

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  orderNo: "ORD-1001",
  customerId: "CUS-01",
  status: "PAID",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  items: [
    { sku: "SKU-A", quantity: 2, unitPrice: NumberDecimal("50000.00") },
    { sku: "SKU-B", quantity: 1, unitPrice: NumberDecimal("25000.00") }
  ]
}
```

If `shop_app.orders` has a unique index on `orderNo`, restoring the old document into the live collection requires checking whether that order was already recreated under a different `_id`. Blindly inserting risks duplicate key errors or logical duplication.

## 6. Creating a Sample Backup in an Authorized Environment

### 6.1. Dumping One Database

In a Bash-like shell, `SOURCE_URI` is an environment variable keeping plaintext passwords out of source code:

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --out="./dump_lab"
```

For an archive:

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --archive="./shop_app.archive" \
  --gzip
```

For actively changing production data, a simple dump must be evaluated for consistency and RPO/RTO requirements. Never treat these two commands as a complete production backup strategy.

### 6.2. Dumping a Single Collection

```bash
mongodump \
  --uri="$SOURCE_URI" \
  --db="shop_app" \
  --collection="orders" \
  --out="./orders_dump"
```

This is a form of **selective backup**: backing up only one collection. Similarly, namespaces can be filtered at dump time using options supported by your Database Tools release. Distinguish:

- **Selecting at dump time**: the backup **excludes** out-of-scope collections.
- **Selecting at restore time**: the backup holds multiple collections, yet you **restore only selected ones**.

During an incident when you only have a full-database backup, use `--nsInclude` at restore time rather than having to dump again.

## 7. Selecting Namespaces With `--nsInclude`

Suppose a directory dump contains `shop_app.orders`, `shop_app.customers`, and `shop_app.payments`.

To restore only `shop_app.orders` into an **empty or isolated lab environment**:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.orders" \
  "./dump_lab"
```

`--nsInclude` filters source namespaces from the dump. It **does not filter documents by query** and does not rename collections.

### Selecting Multiple Namespaces

For example, restoring only `orders` and `payments`:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.orders" \
  --nsInclude="shop_app.payments" \
  "./dump_lab"
```

You can use matching patterns such as `shop_app.*` to include collections within a database. **Broad patterns need careful review** because newly added collections in the backup can widen restore scope unexpectedly.

### Selecting From a Compressed Archive

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders"
```

`--gzip` matches the gzip-compressed archive. Target namespaces come from the URI and namespace mapping; without renaming, backup namespaces collide with existing target collections. **Never run this example on live production unless the target namespace is verified.**

## 8. Excluding Namespaces With `--nsExclude`

When restoring almost an entire database while skipping a collection like `auditLogs`:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --nsInclude="shop_app.*" \
  --nsExclude="shop_app.auditLogs" \
  "./dump_lab"
```

`--nsExclude` omits unwanted collections from the selection. However:

- It does not resolve cross-collection dependencies.
- It does not select specific documents within a collection.
- It does not automatically protect other collections if the include pattern is too broad.
- Pay attention to views, special collections, and metadata when present in the backup.

### Avoid Broad Patterns Out of Habit

```bash
# Can be overly broad in multi-database environments.
mongorestore --uri="$TARGET_URI" --nsInclude="*.*" "./dump_lab"
```

Wildcards matching many namespaces can restore beyond the intended business scope. During incident recovery, start with the **narrowest namespace** and expand only with justification.

## 9. Renaming During Restore With `--nsFrom` and `--nsTo`

This is one of the most important techniques for **safe recovery**: loading backup data into a new namespace for inspection.

Example:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

Expected result:

```text
Source in archive:
  shop_app.orders

Target in MongoDB:
  restore_review.orders

Left untouched:
  shop_app.orders
```

**`--nsInclude` selects source namespaces** from the backup; **`--nsFrom` / `--nsTo` map source namespaces to target namespaces**. Each Database Tools version has specific syntax/wildcard rules; for high-risk commands, spell out explicit namespaces and test in an isolated environment first.

### Renaming an Entire Database With Patterns

Conceptual example keeping collection names while changing the database:

```bash
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.*" \
  --nsFrom="shop_app.*" \
  --nsTo="restore_review.*"
```

With compatible patterns, `shop_app.orders` becomes `restore_review.orders`, `shop_app.customers` becomes `restore_review.customers`, etc.

**Use explicit names whenever scope could be destructive.** Wildcards are convenient yet can pull in extra collections if backup contents or naming conventions evolve.

## 10. Why Is Staging Restore Usually Mandatory?

A direct workflow:

```text
Old backup --> mongorestore --drop --> Production orders
```

can wipe out the entire live `orders` collection before restoring backup data, erasing orders created after the backup.

Staging workflow:

```text
Old backup
    |
    v
restore_review.orders
    |
    +--> count / schema / index review
    +--> locate documents to rescue
    +--> inspect dependencies
    +--> business approval
    |
    v
Controlled selective copy with idempotency + rollback
    |
    v
Production orders
```

Advantages:

- Confirms which data actually resides in the backup.
- Allows querying and diffing without halting production.
- Lets you test transforming legacy data before promotion.
- Exposes differences between backup and target indexes/validators.
- Reduces the risk of running `--drop` against a live collection by mistake.

**Staging still holds real data**, so enforce access controls, retention limits, and cleanup once the incident closes. Never place sensitive production copies into public dev environments.

## 11. `--drop`: An Option Requiring Thorough Understanding

With `mongorestore --drop`, the tool **drops each corresponding target collection before restoring that collection** within scope. This prevents mixing with stale data and restores compatible metadata/indexes, yet deletes existing target data.

Example **only inside a review lab database**, once confirmed the staging collection can be replaced:

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --drop
```

**Never swap `restore_review.orders` for `shop_app.orders` and run it on production** just to preserve indexes: `--drop` deletes writes recorded after the backup timestamp.

### `--drop` Does Not Mean "Delete Only Matching Documents"

`--drop` operates at the **collection** level, not as a filter deleting documents with matching `_id`s. It also affects existing indexes/options because the target collection is dropped and recreated per restore behavior.

Before running, verify:

1. Which exact target URI/cluster?
2. Which source namespaces are selected by `--nsInclude`?
3. Which target namespaces do `--nsFrom` / `--nsTo` produce?
4. Does the target collection hold newer data or serve live apps?
5. Do you have a backup/rollback of the current target state?
6. Do views, triggers, jobs, CDC pipelines, or references depend on that collection?

### What Happens Without `--drop`?

If the target collection already holds documents, `mongorestore` attempts inserts and hits **duplicate key** errors on `_id` or unique indexes. It is **not a smart upsert** that compares old vs. new state and picks the business winner.

To recover individual lost orders, **never rely on `mongorestore` key-collision behavior to merge into production**. Restore to staging and implement explicit document-selection logic.

## 12. Document-Level Recovery: Why Is a Second Step Needed?

Suppose a backup holds 1 million orders, yet production lost only `ORD-1001` and `ORD-1002`. You restored into `restore_review.orders`.

Inspect staging:

```javascript
const review = db.getSiblingDB("restore_review");

review.orders.find({
  orderNo: { $in: ["ORD-1001", "ORD-1002"] }
}, {
  orderNo: 1,
  customerId: 1,
  status: 1,
  total: 1,
  createdAt: 1
});
```

Then compare with production:

```javascript
const production = db.getSiblingDB("shop_app");

production.orders.find({
  orderNo: { $in: ["ORD-1001", "ORD-1002"] }
}, {
  orderNo: 1,
  customerId: 1,
  status: 1,
  total: 1,
  createdAt: 1
});
```

These are **read-only queries**. Do not modify production until analyzing:

- Is the document truly missing, or did its ID/status change?
- Does `orderNo` have a unique index, and does another record already hold that key?
- Does `customerId` exist and remain valid to link?
- Have `payments` and `inventory` changed since the backup?
- Does the document require a **schema migration** to match the current version?
- Would restoring it verbatim trigger downstream workflows again?

### `--nsInclude` Cannot Filter by Document Fields

`--nsInclude="shop_app.orders"` selects the **entire collection**. There is no `where orderNo in (...)` semantics on that option.

When only a few documents are needed, the proper workflow is:

1. Restore the source collection to staging.
2. Query to identify documents requiring recovery.
3. Review with the business owner.
4. Copy via **insert-only** or **conditional upsert** per policy, with uniqueness/idempotency safeguards.
5. Reconcile before and after copying.

If writing a driver-based copy script, build an **application-level dry-run**, an approved ID allowlist, and detailed logging. Do not expect `mongorestore` to provide a business-level dry-run.

## 13. How Do Indexes Affect Post-Restore State?

MongoDB indexes provide:

- Query/filter/sort optimization.
- **Unique** constraint enforcement.
- TTL-based expiration and cleanup.
- Partial indexes, collations, and specialized index types.

Suppose `orders` has:

```javascript
db.orders.createIndex(
  { orderNo: 1 },
  { unique: true, name: "uk_order_no" }
);

db.orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
```

Restoring data without the second index slows down the customer order-history API. Restoring without the first unique index lets the system create **two documents with the same `orderNo`**, breaking a core business invariant.

Hence, after restoring, never verify documents alone. Inspect the **entire index set**, including unique, collation, partial filter, TTL, and hidden options.

### Inspecting Indexes

```javascript
use restore_review

db.orders.getIndexes();
```

Compare against the application's schema/index spec or backup metadata—do not merely count indexes. Two indexes with identical key patterns yet differing `unique` or `collation` settings are **not behaviorally equivalent**.

## 14. Index Metadata in `mongodump`

When `mongodump` writes collection metadata in directory mode, the metadata file typically looks like:

```json
{
  "options": {
    "validator": {
      "$jsonSchema": {
        "bsonType": "object",
        "required": ["orderNo", "total"]
      }
    }
  },
  "indexes": [
    {
      "key": {"_id": 1},
      "name": "_id_"
    },
    {
      "key": {"orderNo": 1},
      "name": "uk_order_no",
      "unique": true
    }
  ]
}
```

This is a **simplified illustration**, not guaranteed identical output across every version. Real metadata may hold additional options or specific BSON/Extended JSON fields.

When `mongorestore` reads a dump with metadata, it attempts by default to restore supported definitions **unless excluded by flags** or failing on errors. Indexes incompatible with the target server or violated by existing data may fail to build.

## 15. `--noIndexRestore` and `--noOptionsRestore`

These two flags control two separate scopes:

| Flag | What Is Skipped on Restore? | Risk to Know |
| --- | --- | --- |
| `--noIndexRestore` | Skips restoring index definitions from backup | Target may lack indexes and unique constraints |
| `--noOptionsRestore` | Skips restoring collection options from backup | Target may lack validators, default collation, or other options |

### Restoring Data Only to a Lab Collection Without Backup Config

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --noIndexRestore \
  --noOptionsRestore
```

Useful if the team only wants to **inspect and analyze raw BSON** in staging while managing collection settings manually. However, the staging collection can **behave differently from the source**:

- Queries run slower without indexes.
- Duplicate data can be inserted without unique index enforcement from the backup.
- New writes may bypass schema validators.
- Default collation may differ, altering query/sort/uniqueness behavior.

**Never use these two flags out of habit and claim a "complete restore."** Label it explicitly as a **data-only restore** and plan to reapply indexes/options if needed.

### Is Skipping Indexes to Restore Faster Safe?

Occasionally you may defer index creation to reduce ingestion overhead. Yet on business collections, temporarily missing unique/TTL/partial indexes changes production semantics. If separating data and indexes:

1. Restore into isolated staging.
2. Inspect data and resolve duplicates.
3. Build indexes under a controlled procedure.
4. Confirm all index builds finish before enabling traffic.

Never trade away data constraints for restore speed without explicit sign-off.

## 16. Unique Indexes: Restores Can Fail Due to Duplicate Data

Suppose a backup contains:

```javascript
[
  { _id: 1, orderNo: "ORD-1001" },
  { _id: 2, orderNo: "ORD-1001" }
]
```

If creating:

```javascript
db.orders.createIndex(
  { orderNo: 1 },
  { unique: true }
);
```

the index build fails because **two documents share the same key**. This can happen when:

- The backup already contained dirty data predating the unique index.
- The restore merges into a target collection holding conflicting data.
- Source and target use different collations, causing previously distinct strings to compare equal.
- A prior migration introduced duplicate keys.

### Finding Duplicates in Staging Before Applying Unique Constraints

```javascript
db.getSiblingDB("restore_review").orders.aggregate([
  {
    $group: {
      _id: "$orderNo",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 100 }
]);
```

This pipeline is purely for **analysis**. On very large datasets, `$push`ing all IDs for extremely high-cardinality or skewed groups can hit document size limits; adapt pipelines/reporting to scale in production.

Never delete duplicates automatically without knowing which record is authoritative; have the business owner define the reconciliation policy.

## 17. TTL Indexes: Restoring an Index Can Make Data Vanish

A TTL index automatically deletes expired documents based on time/retention settings.

Example:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

If you restore an older backup of `sessions` and recreate/restore this TTL index, documents whose `expiresAt` is already in the past are soon purged by the TTL monitor. Operators may mistakenly think "the restore lost data," when **retention is simply executing**.

### Safe Approach

- Restore into an environment isolated from unwanted jobs and TTL policies if investigating historical data.
- Inspect index definitions and collection options before deciding whether to keep TTL active.
- If the goal is restoring active sessions, records expired days ago usually shouldn't be resurrected anyway.
- If the goal is forensics, use an appropriate environment where background cleanup cannot destroy evidence.

**Never drop a TTL index in production just to "preserve restored data" without approval**, as that alters retention across the entire collection.

## 18. Partial, Sparse, Hidden Indexes, and Collation

Beyond unique/TTL, pay attention to:

| Index Property | Role | Risk If Missing/Wrong After Restore |
| --- | --- | --- |
| `partialFilterExpression` | Indexes only documents matching a filter | Query planner and uniqueness scope differ |
| `sparse` | Omits documents missing the indexed field | Coverage and uniqueness behavior change |
| `hidden` | Index exists yet is ignored by the planner by default | Query plans diverge from source environment |
| `collation` | String comparison, case, and locale rules | Uniqueness and sort order can differ |
| `expireAfterSeconds` | TTL retention window | Old documents purged or retained unexpectedly |
| `unique` | Prevents duplicate keys per index semantics | Data invariants can be violated |

### Collection-Level Collation Also Matters

Suppose the source collection had a case-insensitive English collation or custom locale, yet staging was created without that option. Equality queries, sorts, and uniqueness behave differently even with identical documents.

Default collection collation is part of **collection options**, not a visible field inside documents. Do not assume every collection property can be patched in place via `collMod`; changing default collation usually requires recreating the collection properly.

### Inspect Full Definitions Rather Than Index Names Alone

```javascript
const review = db.getSiblingDB("restore_review");
printjson(review.orders.getIndexes());
printjson(review.getCollectionInfos({ name: "orders" }));
```

These two calls return index specs and collection options to compare against the backup and target environment.

## 19. What Is Schema Validation in MongoDB?

**Schema validation** defines rules that documents must satisfy on insert/update, usually via `$jsonSchema` or supported query expressions.

For example, the app expects every order to have:

- `orderNo` as a string.
- `total` as a BSON numeric type.
- `createdAt` as a BSON Date.
- `status` as one of the allowed enum values.

A validator might look like:

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["orderNo", "total", "createdAt"],
    properties: {
      orderNo: {
        bsonType: "string"
      },
      total: {
        bsonType: ["int", "long", "double", "decimal"]
      },
      createdAt: {
        bsonType: "date"
      },
      status: {
        enum: ["NEW", "PAID", "CANCELLED"]
      }
    }
  }
};
```

Here:

- `required` mandates that specified fields exist.
- `bsonType` enforces exact BSON types, not just API-layer JSON strings/numbers.
- `enum` constrains allowed values when the field is present.

If business policy requires `status` to always be present, add `status` to `required`; `enum` alone does not make a field mandatory.

### Schema Validation Is Not Type Conversion

A document:

```javascript
{
  orderNo: "ORD-1001",
  total: "125000.00",
  createdAt: "2026-11-14"
}
```

has `total` and `createdAt` as **strings**. A validator will not convert them into `Decimal128` and `Date`. If the current schema requires numeric/BSON Date types, the document must be migrated or handled per policy.

## 20. Creating a Collection With a Validator

In an empty lab database:

```javascript
use restore_validation_lab

db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "total", "createdAt"],
      properties: {
        orderNo: { bsonType: "string" },
        total: { bsonType: ["int", "long", "double", "decimal"] },
        createdAt: { bsonType: "date" },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Inserting a valid document:

```javascript
db.orders.insertOne({
  orderNo: "ORD-OK",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  status: "PAID"
});
```

Invalid document:

```javascript
db.orders.insertOne({
  orderNo: "ORD-BAD",
  total: "125000.00",
  createdAt: "2026-11-14",
  status: "UNKNOWN"
});
```

With `strict` + `error`, the second insert is rejected for wrong types and enum value. **This demonstrates validation behavior**—do not run in production.

### `validationLevel` and `validationAction` Differ

| Option | Example | Meaning |
| --- | --- | --- |
| `validationLevel: "strict"` | Strict | Applies validation to inserts and updates per validator rules |
| `validationLevel: "moderate"` | Moderate | Inserts are checked; updates to pre-existing invalid documents may not be rejected similarly |
| `validationAction: "error"` | Error | Rejects invalid writes |
| `validationAction: "warn"` | Warn | Allows the write while logging a warning per server behavior |

Additional logging/modes may vary by MongoDB version. When restoring to a new environment, verify **actual values of both level and action**, rather than assuming presence of `validator` means strict enforcement.

## 21. Schema Validation During Restore: Four Scenarios

### A. Restoring Into a New Collection With Complete Metadata

The new collection can be created with the backup's collection options/validator (if metadata exists, is compatible, and isn't disabled by flags). Restored documents are checked against the validator during writes.

### B. Restoring Into an Existing Collection With a Stricter New Validator

The source backup holds legacy documents that fail the newer schema. When restoring without `--drop`, inserts can fail due to **document validation** even though the backup was completely valid when created.

### C. Restoring With `--noOptionsRestore`

Skips restoring collection options from the backup. If a new collection is created with defaults, it lacks a validator; if the collection already exists, the target's existing validator keeps applying. Never assume `--noOptionsRestore` means "disable validation in all cases."

### D. Restoring With `--drop`

If the target collection is dropped, existing validator/index configs are lost and recreated from backup metadata (if present and applied). This can **bring back an older validator** or wipe out newer schema changes on the target.

**Conclusion:** data restoration strategy and schema restoration strategy must be decided separately, and both verified against the target.

## 22. `--bypassDocumentValidation`: Useful Yet Dangerous If Misunderstood

`mongorestore` supports `--bypassDocumentValidation` under appropriate version/privilege conditions. It lets the restore bypass **document validation checks** when writing, useful for loading legacy documents into a collection to clean up afterward.

Example **strictly in an isolated recovery environment**:

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders" \
  --bypassDocumentValidation
```

**Avoid these misconceptions:**

- Bypassing validation does not auto-fix malformed field types.
- Bypassing does not drop unique indexes or allow duplicate `_id`s.
- Bypassing does not override authorization/privilege requirements.
- Invalid inserted documents remain stored once the validator resumes normal enforcement.
- Applications may later crash when reading/writing documents missing fields or carrying wrong types.

Use this only alongside a **data-cleansing and validator re-check plan**, never as a shortcut to ignore errors and rush production back online.

### Distinguishing Bypass From Modifying the Validator

`--bypassDocumentValidation` applies to a **specific write operation**, whereas changing `validator` or `validationAction` on the collection alters **collection-wide policy** for subsequent operations.

On a live production database, flipping `validationAction` to `warn` just to "let the restore through" lets **other application writes** slip in invalid data too. That blast radius is far wider than handling data in staging.

## 23. Checking Whether Legacy Data Satisfies the Current Schema

After restoring to staging, you can test documents against the same `$jsonSchema` logic.

Example:

```javascript
const schema = {
  bsonType: "object",
  required: ["orderNo", "total", "createdAt"],
  properties: {
    orderNo: { bsonType: "string" },
    total: {
      bsonType: ["int", "long", "double", "decimal"]
    },
    createdAt: { bsonType: "date" }
  }
};

const reviewOrders = db
  .getSiblingDB("restore_review")
  .getCollection("orders");

reviewOrders.find({
  $nor: [{ $jsonSchema: schema }]
}, {
  orderNo: 1,
  total: 1,
  createdAt: 1
}).limit(100);
```

This query **identifies documents failing an illustrative validator**, not an auto-repair command. In real environments, use your exact target validator, additional constraints, level/action settings, and business rules.

### Be Careful When Migrating

Example:

```javascript
// Legacy format
{
  orderNo: "ORD-1001",
  total: "125000.00",
  createdAt: "2026-11-14"
}

// Desired target format
{
  orderNo: "ORD-1001",
  total: NumberDecimal("125000.00"),
  createdAt: ISODate("2026-11-14T00:00:00Z")
}
```

Converting a date string to UTC midnight is a **business assumption**. If the original timestamp represented local time or transaction time, picking UTC midnight alters its meaning. Migrations need explicit rules for timezones, currency units, nulls, and numeric types.

## 24. `collMod` to Modify Validators: Different From Restoring Documents

MongoDB provides `collMod` to modify certain collection options depending on version, including schema validation.

Example **in a lab**:

```javascript
db.getSiblingDB("restore_validation_lab").runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "total", "createdAt"],
      properties: {
        orderNo: { bsonType: "string" },
        total: {
          bsonType: ["int", "long", "double", "decimal"]
        },
        createdAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Do not treat `collMod` as a blanket way to "update every schema and index." Indexes must be managed through appropriate APIs; some collection options cannot change in place. In production, changing a validator requires:

1. Auditing how many existing documents are invalid.
2. Checking which app versions still write legacy shapes.
3. Testing write and update paths.
4. Planning phased rollout and backfill.
5. Monitoring validation errors and keeping a rollback plan.

**Changing a validator does not repair existing data.** Pre-existing invalid documents stay invalid until updated or processed per policy.

## 25. Inspecting Collection Metadata After Restore

In `mongosh`:

```javascript
const review = db.getSiblingDB("restore_review");

printjson(
  review.getCollectionInfos({ name: "orders" })
);

printjson(
  review.orders.getIndexes()
);
```

Check:

- Does the collection exist with the right name and type?
- Does `validator` match expected rules?
- Are `validationLevel` and `validationAction` set appropriately?
- Are default collation and key collection options accurate?
- Did unique, TTL, partial, text, wildcard, or specialized indexes build cleanly?
- Are there indexes sharing the same name yet differing in keys or options?

### Distinguishing Schema Validation From Storage Validation

The command:

```javascript
db.getSiblingDB("restore_review").runCommand({
  validate: "orders",
  full: true
});
```

checks **storage-level structural integrity** per server mechanics; it **does not substitute** for querying whether documents satisfy a new business `$jsonSchema`. The two checks serve entirely different purposes.

## 26. Restore Backup Indexes or Keep Target Indexes?

No single answer fits every scenario.

| Scenario | Typical Approach | Why |
| --- | --- | --- |
| Restoring a collection verbatim into a same-version lab cluster | Restore metadata/indexes from backup | Reproduces source behavior |
| Rescuing a few documents into production with newer schema/indexes | Restore to staging; **keep target indexes** | Avoids reverting to old indexes/validators |
| Historical data analysis without query benchmarking | May skip index restore in staging | Saves index build cost, knowing limitations |
| Migrating to another MongoDB version | Review/recreate indexes per target capabilities | Index options may differ |
| Building a new collection for the current app | Apply **target** schema/indexes, then load cleaned data | Optimized for running code |
| Preserving forensic evidence prior to recovery | Keep an independent backup copy under retention | Avoids altering investigative data |

### Index Restoration Is Not "Restore Just One Index"

If production is simply missing one index, **recreate that index from its approved definition** rather than restoring an entire collection just for its index metadata.

Example:

```javascript
// Only in an authorized, approved environment.
db.getSiblingDB("shop_app").orders.createIndex(
  { customerId: 1, createdAt: -1 },
  { name: "idx_customer_created" }
);
```

Before running in production, check existing indexes, data cardinality, build resource cost, workload impact, and version restrictions. Ignoring an index build failure can leave a deployment looking successful while missing performance or uniqueness enforcement.

## 27. A Data-Only Restore Is Not an Accurate Restore

A common mistake:

```text
mongorestore --noIndexRestore --noOptionsRestore
                |
                v
Documents are present
                |
                v
Conclusion: recovery completely succeeded
```

That conclusion is premature because:

- Unique indexes are unverified.
- Validators may be absent.
- Collation/TTL may differ from source.
- The application may depend on specific indexes to meet SLAs.
- Data may fail the current domain model.

**Technical success of data ingestion** is only part of **post-recovery business success**.

### Three Verification Layers

1. **Physical/logical data restore:** namespaces and documents exist; zero unhandled restore errors.
2. **Metadata/schema restore:** indexes, options, and validators align with policy.
3. **Business recovery:** data completeness, dependency consistency, API/query correctness, and no unintended side effects.

A system passing only layer 1 may still be unsafe to put into service.

## 28. Selective Restore and Cross-Collection Consistency

Example:

```text
customers:
  CUS-01  [updated after backup]

orders:
  ORD-1001 -> CUS-01  [old copy]

payments:
  PAY-77 -> ORD-1001  [refunded after backup]
```

If you restore only `orders` from a week-old backup:

- `ORD-1001` may still show the **old PAID status**, even though the payment was later refunded.
- `customerId` may reference a merged or deleted customer.
- An outbox event or inventory reservation may already have been processed and must not re-fire.

### Selective Restore Does Not "Rewind the System to the Past"

Restoring a single namespace only retrieves that namespace's data at backup time. It **does not roll other collections back to matching states**. Furthermore, a logical backup captured mid-writes may have internal skew if an appropriate consistency method wasn't used.

Therefore you must:

1. Identify **invariants** across collections.
2. List dependencies of documents being rescued.
3. Compare current production state against the backup.
4. Decide which fields come from the old copy vs. keeping current state.
5. Choose full-document insertion vs. field-level patching.
6. Mark/audit correction events.

Never blindly restore payment states by copying an old document when real financial state is involved.

## 29. Point-in-Time Recovery: What Goes Beyond `--nsInclude`?

**RPO** (*Recovery Point Objective*) is maximum target data loss; **RTO** (*Recovery Time Objective*) is maximum target recovery duration.

A backup taken at 01:00 does not contain changes from 01:01–03:00. If an accidental deletion happens at 03:00, `--nsInclude` cannot magically "retrieve state as of 02:59" from a 01:00 BSON file.

### PIT Restores Require Proper Change History

A point-in-time recovery workflow relies on:

- A consistent base backup via a supported method.
- Oplog/change history or a backup service covering the target point.
- Compatible topology, tool flags, and server versions.
- Ability to restore the required scope in exact operation order.

**Never arbitrarily combine `--nsInclude` with oplog replay and claim point-in-time consistency for a few collections.** The oplog spans multiple namespaces, transactions, and dependencies; Database Tools flags/restrictions must be checked strictly. When needing the exact instant before an accidental deletion, run a supported PIT restore in an isolated environment and then selectively promote documents to production.

### Atlas Snapshots Differ From `mongodump`

MongoDB Atlas provides backup/snapshot/restore capabilities depending on tier and policy. Snapshot restores operate at cluster or service-supported scopes—not as files you directly point `mongorestore --nsInclude` at. Recovering one collection from a snapshot may require restoring to a **temporary cluster** first and then exporting/migrating by namespace.

Never assume Atlas backups universally support arbitrary per-document restores or identical PIT features across every tier/version.

## 30. Restoring to Atlas: What Must Be Prepared?

When targeting Atlas, `mongorestore` from an authorized client/runner remains viable for logical BSON data, provided you verify:

1. **Network path:** Atlas IP Access List for public egress or private endpoints.
2. **TLS:** valid URI/CA/hostname verification.
3. **Database role:** user needs privileges to create collections, insert documents, build indexes, or alter collection options per restore scope.
4. **Tool compatibility:** Database Tools version compatible with the target deployment.
5. **Cluster capacity:** storage, CPU, RAM, connection limits, and index build resources.
6. **Sharding/topology:** if targeting a sharded cluster, evaluate shard keys and distribution.
7. **Backup policy:** avoid inadvertently altering production backup/retention policies.
8. **Secrets:** never hardcode credentials in scripts or shell history.

### URI Placeholder

```bash
# Retrieve SOURCE_URI and TARGET_URI from secret management.
mongorestore \
  --uri="$TARGET_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

Run only when `TARGET_URI` points to an **approved staging/target environment**. If targeting a production Atlas cluster directly, creating a `restore_review` database still stores sensitive data and consumes resources on the live cluster.

## 31. Sharding, Views, and Special Collection Types

### Sharded Collections

Restoring logical data into a sharded cluster interacts with shard keys, unique index rules, chunk distribution, and routing. Namespace mapping alone does not recreate source sharding metadata and topology.

Before restoring:

- Check whether the target collection is sharded.
- Check shard key and unique index compatibility.
- Assess cardinality/distribution and write hot spots.
- Consider restoring into an unsharded staging collection first for inspection.
- Verify version, topology, and backup tool recommendations.

### Views

A view is a query definition over another collection. Restoring only view metadata without source data, or remapping namespaces inconsistently, breaks the view.

### Time Series, Capped, and Clustered Collections

These collection types have distinct options and restrictions. Using `--noOptionsRestore` and letting the tool create a standard collection **cannot be treated as structurally equivalent**. For time-series or special collections, verify document/collection representations and Database Tools version support.

### GridFS

GridFS uses paired collections, such as `fs.files` and `fs.chunks`. Restoring only `fs.files` brings back metadata without file bytes; restoring only `fs.chunks` leaves orphan chunks. Recovering a specific file requires restoring both collections alongside business references using proper GridFS workflows.

This is a textbook example of why **technically selecting one collection is insufficient for business consistency**.

## 32. Verifying Document Counts

After staging restore:

```javascript
const review = db.getSiblingDB("restore_review");

print("orders:", review.orders.countDocuments({}));
print("indexes:", review.orders.getIndexes().length);
```

If expected counts exist from the backup source or report, reconcile:

- Total documents dumped.
- Total documents successfully restored.
- Error counts (duplicate keys, validation failures, namespace conflicts).
- Actual post-restore document count.

### Why Matching Counts Are Still Not Enough

Two collections can both hold 100,000 documents while one is missing `ORD-1001` and has a duplicate `ORD-2001` under another ID. Counts do not prove identical contents.

For critical data, compare **key sets, well-designed hashes/fingerprints, business fields, relationships, and sample queries**. Never compute a single SHA-256 over arbitrarily ordered JSON documents as proof, since BSON types, field order, serialization, and document order can vary.

### Sampling Business Keys

```javascript
review.orders.find(
  { orderNo: { $in: ["ORD-1001", "ORD-1002"] } },
  { orderNo: 1, status: 1, total: 1, createdAt: 1 }
).sort({ orderNo: 1 });
```

When auditing millions of documents, reconcile in batches/key ranges to bound memory usage and protect production.

## 33. Checking Queries and Indexes With `explain`

After restoring indexes, do not inspect `getIndexes()` alone and assume query performance matches production.

Example:

```javascript
review.orders.find({
  customerId: "CUS-01",
  createdAt: {
    $gte: ISODate("2026-11-01T00:00:00Z"),
    $lt: ISODate("2026-12-01T00:00:00Z")
  }
}).sort({ createdAt: -1 }).limit(20)
  .explain("executionStats");
```

Evaluate:

- Does an index match the filter/sort?
- Does the query hit `COLLSCAN` or an expensive in-memory sort unexpectedly?
- Are `totalKeysExamined` and `totalDocsExamined` proportional to returned documents?
- Does collation match application queries?
- Does the target have different index configs from source due to version/mapping differences?

Never compare latency on a tiny staging cluster against high-load production and call it a fair benchmark; simulate representative load.

## 34. Collection Metadata Can Have Side Effects

Beyond indexes and validators, collection options affect:

- **Default collation**: case/locale sensitivity in queries, sorts, and uniqueness.
- **Capped behavior**: size bounds and insertion ordering on capped collections.
- **Time-series options**: measurement bucketing and retention.
- **Change stream pre/post-image options** in supported environments.
- **TTL/retention** and auxiliary settings.

A historical backup may carry metadata valid **at that earlier time** yet incompatible with current schemas. Thus restoring all metadata blindly is not always right; nor is skipping metadata and restoring raw documents alone.

### Decision Rule

Separate:

```text
Goal A: reproduce the historical system for investigation
  -> prefer metadata from backup time

Goal B: promote specific documents into the live app
  -> prefer current target schema/indexes
     after transforming data appropriately
```

These two goals often require **two separate environments** or a two-stage restore.

## 35. Selective Data Recovery via Application Scripts

Once staging is verified, bringing a subset of documents back into production should be engineered as a **data-repair operation**.

A practical workflow:

1. Build the list of keys to recover, e.g., `["ORD-1001","ORD-1002"]`.
2. Query backup/staging for source documents.
3. Query production to confirm records are missing or in a repairable state.
4. Reconcile customer/payment/inventory state against current production.
5. Migrate schemas if needed without stripping newer fields or reverting business state.
6. Dry-run on a lab database and record before/after diffs.
7. Execute writes using a least-privilege identity in small batches.
8. Log audit/correlation IDs, checking errors and results.
9. Protect against retries via idempotency/unique business keys.
10. Reconcile post-change and monitor application health.

### Why Not Run `replaceOne` From Backup for Every ID?

An order may have mutated after the backup. Replacing with the old document can:

- Erase new fields added by the application.
- Overwrite a newer status with an obsolete status.
- Revert payment/inventory references to stale values.
- Accidentally re-trigger workflows or corrupt business state.

Partial recovery requires a **field-level policy**: which documents are inserted whole, which are patched, and which only generate correction/audit events.

### Can You Use Aggregation `$merge`?

`$merge` writes aggregation output to a target collection, governed by `on`, `whenMatched`, `whenNotMatched`, and specific index/namespace rules. It does not resolve business conflicts automatically. If used, test **staging-to-staging** first and define exact handling for existing records.

Never run `$merge` from backup directly into production with `whenMatched:"replace"` merely because it feels quicker than writing an application script.

## 36. Building a Safe Recovery Runbook

### Phase A — Scope the Incident

Answer:

- Which collections lost or corrupted data?
- When did corruption start and when was it detected?
- Are writes still hitting the same namespace?
- Which business keys/documents are affected?
- Are snapshots/PITR available?
- What are RPO/RTO and recovery priorities?

### Phase B — Preserve Current State

Before changing anything:

- Back up or snapshot current state per approved methods.
- Keep original backups untouched; avoid overwriting archives or metadata.
- Assign an incident/change ID and accountable owner.
- If forensic evidence is needed, lock down access and retention.

### Phase C — Staging Restore

```bash
mongorestore \
  --uri="$LAB_URI" \
  --archive="./shop_app.archive" \
  --gzip \
  --nsInclude="shop_app.orders" \
  --nsFrom="shop_app.orders" \
  --nsTo="restore_review.orders"
```

**Do not pass `--drop` unless the staging collection is confirmed safe to replace.**

### Phase D — Inspect Data and Metadata

```javascript
const r = db.getSiblingDB("restore_review");

printjson(r.getCollectionInfos({ name: "orders" }));
printjson(r.orders.getIndexes());
print("documents =", r.orders.countDocuments({}));
```

Then inspect related documents, unique keys, validators, collation, TTL, dependencies, and validation errors.

### Phase E — Repair and Approval

Prepare:

```text
Incident ID:
Source backup timestamp:
Source namespace:
Staging namespace:
Destination namespace:
Document keys:
Data transformation:
Target indexes/validator:
Dependencies:
Expected changes:
Rollback:
Approver:
```

Execute writes only after the exact plan is reviewed and authorized per organizational process.

### Phase F — Verification and Cleanup

- Reconcile keys, counts, fields, and relationships.
- Monitor application errors and query latency.
- Confirm indexes and validation enforce properly.
- Archive the recovery audit report.
- Purge staging per retention policy when no longer needed; do not leave sensitive copies lying around.

## 37. Failed Restores: Diagnosing Root Causes

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `namespace not found` / collection missing from dump | Wrong source namespace or incomplete backup | Check manifest/dump source and spelling |
| Restored into wrong database | Wrong `--nsFrom`/`--nsTo` or target URI | Halt immediately; verify mapping and environment |
| `duplicate key error` | `_id`/unique key already exists on target or duplicate in backup | Stage, reconcile keys; never ignore blindly |
| `Document failed validation` | Legacy BSON fails current validator | Analyze fields/types; migrate in staging |
| `not authorized` | User lacks create/index/collMod/write privileges | Grant operation-specific privileges; avoid default `root` |
| Index build failed | Duplicate keys, unsupported option, collation mismatch | Inspect data/index specs and version |
| Slow queries after restore | Indexes not restored/built, different stats/workload | Check `getIndexes()`, `explain()`, and benchmark |
| Data vanishes after restore | TTL index or retention job purging old records | Inspect TTL/options and background jobs |
| Count lower than backup | Restore errors, filters, wrong namespace, TTL | Inspect logs, namespaces, and metadata |
| Matching count yet wrong orders | Stale data or mismatched business state | Compare business keys and dependencies |
| View fails to query | Missing underlying collection or broken mapping | Restore/fix dependencies |
| GridFS shows filenames, downloads fail | Restored `files` without `chunks` | Restore both collections consistently |
| Atlas TCP timeout | Network access, NAT, DNS, private endpoint | Debug network path before auth |
| URI connects yet inserts rejected | AuthZ/validator/unique constraints | Inspect detailed nested errors |
| Legacy data mismatches current app | Schema drift and unrun migrations | Apply data transforms/versioning policy |
| Failures after restart/failover | Topology/HA, write concern, session state | Inspect replica set health and write results |

**Never ignore errors just because some documents restored.** An errored run can leave partial data behind; confirm exact state before retrying.

## 38. Common Misconceptions

| Statement | Why Is It Wrong? | Correct Understanding |
| --- | --- | --- |
| "Restoring one collection restores all dependencies" | References live in other collections | Reconcile business relationships |
| "`--nsInclude` filters documents by field" | It selects namespaces, not query predicates | Restore to staging, then filter documents |
| "`--nsTo` automatically adapts schema for target" | It only remaps namespace names | Run schema migrations separately |
| "`--drop` deletes only duplicate documents" | It drops the entire target collection | Risks losing newer data |
| "Omitting `--drop` is always 100% safe" | Can hit duplicate/validation errors and partial writes | Still requires staging and review |
| "Once data restores, indexes are definitely right" | Index builds may fail or be skipped | Verify `getIndexes()` and logs |
| "`--noIndexRestore` doesn't affect correctness" | Unique constraints may be missing | Reapply indexes in a controlled manner |
| "`--noOptionsRestore` only suppresses logs" | It skips restoring collection options | Validators/collation can differ |
| "`--bypassDocumentValidation` converts types automatically" | Bypassing does not transform data | Migrate types explicitly |
| "A new validator auto-repairs old documents" | Validation does not auto-repair | Run data cleanup/backfill |
| "Previously valid data is always valid on newer servers" | Schemas and versions evolve | Check against target schema |
| "Physical `validate` proves JSON Schema compliance" | Different validation layers | Query `$jsonSchema` separately |
| "Matching counts mean complete correctness" | Keys may be missing or wrong | Verify business keys and links |
| "TTL affects only newly inserted data" | TTL cleans old restored docs too | Review TTL beforehand |
| "A BSON dump is always cluster-consistent" | Concurrent writes can span times | Use proper backup/PIT strategies |
| "Partial restore always gives point-in-time" | Namespace filtering does not replay history | PIT requires dedicated mechanisms |
| "Atlas snapshot restore equals `mongorestore` on an archive" | Different scopes and capabilities | Check Atlas backup docs |
| "One GridFS collection suffices to download files" | Data and metadata span two collections | Restore both `files` and `chunks` |
| "Same index name means identical semantics" | Unique/collation/partial/TTL may differ | Compare full index definitions |
| "Copy backup to production with `replaceOne` everywhere" | Overwrites newer state and side effects | Build a key-level data-repair plan |

## 39. Practice Exercises With Solutions

### Exercise 1. Namespaces

In MongoDB, are `shop_app.orders` and `restore_review.orders` the same namespace?

**Answer:** No. A namespace combines database and collection; different databases mean different namespaces.

### Exercise 2. Selecting One Collection

An archive contains `shop_app.orders`, `shop_app.customers`, and `shop_app.payments`. You need to restore only `orders`. Which option do you use?

**Answer:** `--nsInclude="shop_app.orders"`, with the proper source dump and target URI. Avoid `shop_app.*` if only one collection is desired.

### Exercise 3. Renaming on Restore

You want to load `shop_app.orders` as `restore_review.orders`. Which flags do you pass?

**Answer:** Combine `--nsInclude="shop_app.orders"` with `--nsFrom="shop_app.orders"` and `--nsTo="restore_review.orders"`, tested in a lab environment.

### Exercise 4. Extracting Two Documents

You want to rescue only `ORD-1001` and `ORD-1002`. Can `--nsInclude` filter directly on `orderNo`?

**Answer:** No. Restore the entire collection to staging, query the two documents by key, and copy them under controlled logic.

### Exercise 5. `--drop`

A backup was taken at 01:00, and production received new data at 02:00. What is the risk of running `mongorestore --drop` on production `orders`?

**Answer:** The target collection is dropped before restoring, wiping out post-backup data. Restore to staging and use a data-repair plan instead.

### Exercise 6. Without `--drop`

The target already holds `_id: 1`, and the backup also has `_id: 1`. Does `mongorestore` automatically merge fields to keep newer values?

**Answer:** Not by default. Duplicate key errors occur; merge semantics and conflict policies must be implemented at the application level.

### Exercise 7. Metadata

In a dump folder you see `orders.bson` and `orders.metadata.json`. What role does each file play?

**Answer:** `.bson` holds documents; `.metadata.json` holds collection options and index specs for restoration per tool/version.

### Exercise 8. Disabling Index Restore

You restore with `--noIndexRestore` into a new collection. Is the unique `orderNo` key guaranteed to be protected?

**Answer:** No. You must create/verify the unique index on the target; never treat a data-only restore as full schema recreation.

### Exercise 9. Disabling Options Restore

You restore with `--noOptionsRestore` into a new collection. Is the old validator guaranteed to be restored?

**Answer:** No. That flag skips collection options from the backup, including any validator stored in options; configure the target schema explicitly.

### Exercise 10. Unique Index Failure

A backup contains two documents with the same `orderNo`, while the target wants a unique index on `orderNo`. What can happen?

**Answer:** The index build or insert fails with a duplicate key error. Analyze and resolve duplicates per business rules in staging.

### Exercise 11. TTL After Restore

You restore a collection with `expireAfterSeconds: 0` on `expiresAt`, where most dates are in the past. Why might documents quickly vanish?

**Answer:** The TTL monitor cleans up expired documents. Verify retention/index rules and recovery goals beforehand.

### Exercise 12. BSON Types

The validator requires `total` to be Decimal128, yet the backup holds `total: "125000.00"`. Does bypassing validation convert the string to Decimal128?

**Answer:** No. Bypassing only skips validation checks during writes; the value remains a string and requires migration.

### Exercise 13. Strict vs. Moderate

What is the fundamental difference between `validationLevel: "strict"` and `"moderate"`?

**Answer:** Strict applies validation to inserts and updates per rules; moderate is more lenient on updates to pre-existing invalid documents, while inserts remain subject to the validator/action.

### Exercise 14. Error vs. Warn

Does `validationAction: "warn"` block schema-violating documents from being written?

**Answer:** No. Warn permits the write while logging a warning per server behavior; `error` rejects invalid writes.

### Exercise 15. Physical Validation Check

Does `db.runCommand({validate:"orders", full:true})` prove every order satisfies a new business JSON Schema?

**Answer:** No. Storage validation and schema/business validation are two distinct checks.

### Exercise 16. Single Missing Index

You only need to restore one missing secondary index in production. Should you drop the collection and restore a dump to get the index back?

**Answer:** No. Fetch the approved index definition, assess build impact, and recreate the index directly on the live collection under an approved procedure.

### Exercise 17. Data Consistency

The backed-up order has status `PAID`, while the live payment is now `REFUNDED`. Is copying the old order back into production safe?

**Answer:** No. Reconcile dependencies and business policies; you may need to patch only specific fields or emit a correction event.

### Exercise 18. Point in Time

Can a dump created at 01:00 restore the exact state at 02:59 just by using `--nsInclude`?

**Answer:** No. Namespace selection does not create post-backup change history. PIT requires a suitable backup/history mechanism.

### Exercise 19. Atlas Snapshots

Is an Atlas snapshot equivalent to an archive you can pass directly to `mongorestore --nsInclude`?

**Answer:** No. Snapshot/backup services and Database Tools archives are separate mechanisms; selective restore support depends on method and tier.

### Exercise 20. GridFS

Is restoring `fs.files` without `fs.chunks` enough to download large files?

**Answer:** No. `files` holds metadata; `chunks` holds file bytes. Both must be restored consistently with references.

### Exercise 21. Counts

The backup has 10,000 documents and the restored target also has 10,000 documents. Does that prove a valid recovery?

**Answer:** Not yet. Compare IDs/business keys, contents, schemas, indexes, and dependencies; counts can match even when data is wrong.

### Exercise 22. Using `--bypassDocumentValidation`

When restoring a production collection, a team wants to enable bypass so all legacy docs insert quickly. What is the problem?

**Answer:** It introduces schema-invalid data into the live app environment while unique/other constraints still apply. Handle cleansing and migration in staging instead.

### Exercise 23. Restoring After a Faulty Deployment

A rollout adds a new validator that rejects incoming imports. Should you immediately delete the validator in production?

**Answer:** No. Diagnose schema mismatches, app versions, legacy data, and rollout rollback options in staging; altering a production validator affects all writes.

### Exercise 24. Strategy Selection

An application writes continuously; only two orders were lost after backup. What is the safest recovery strategy?

**Answer:** Preserve live production, restore the collection into a staging namespace, inspect the two orders and their dependencies, migrate schema if needed, run approved idempotent inserts/patches, and verify results.

## 40. Technical Checklist Before, During, and After Restore

### Before Restore

- [ ] Incident/change ID, owner, and recovery scope defined.
- [ ] **Source backup**, timestamp, and backup reliability confirmed.
- [ ] **Target URI/database/collection** unambiguously verified.
- [ ] Current production state backed up/captured if rollback is needed.
- [ ] Exact namespace patterns and mappings reviewed.
- [ ] Database Tools/server versions and topology verified.
- [ ] RPO/RTO, downtime, and consistency expectations defined.
- [ ] Decided whether PIT restore/temp cluster vs. BSON dump is needed.
- [ ] Access to staging holding sensitive data strictly controlled.

### During Staging Restore

- [ ] `--drop` never used outside approved replaceable environments/collections.
- [ ] Only necessary namespaces selected.
- [ ] `mongorestore` output reviewed and errors/warnings saved.
- [ ] Expected dump/metadata files verified as present and processed.
- [ ] Counts and sample business keys verified.
- [ ] `getIndexes()`, unique/TTL/partial/collation verified.
- [ ] Collection options and validators verified.
- [ ] Legacy documents failing target schema identified.
- [ ] Cross-collection dependencies reconciled.

### Before Promoting Data to Production

- [ ] Approved list of exact records/fields prepared.
- [ ] Insert/patch/conflict/idempotency policy finalized.
- [ ] Schema/types/units/timezones migrated where needed.
- [ ] Tested staging-to-staging under production-like conditions.
- [ ] Target unique constraints and authorization verified.
- [ ] Rollback plan prepared for each write operation.
- [ ] Safeguards in place for payments/outbox/notification workflows.

### After Recovery

- [ ] Data reconciled via business keys and key relationships.
- [ ] Indexes and query performance verified.
- [ ] Schema validation and application behavior verified.
- [ ] Errors, duplicate keys, and TTL/retention monitored.
- [ ] Audit log/recovery report archived per policy.
- [ ] Staging and temporary access removed once no longer needed.
- [ ] Runbook updated to prevent recurrence.

## 41. Summary

**Selective recovery** in MongoDB is a multi-decision workflow, not a single `mongorestore` flag. `--nsInclude` and `--nsExclude` restrict which **source namespaces** are restored; `--nsFrom` and `--nsTo` **rename target databases/collections**, making them ideal for **staging**. They **do not filter documents by business queries**.

**`--drop`** can replace an entire target collection in restore scope and must never be used to merge old and new data. When rescuing only a few documents, restore to staging, inspect business keys and dependencies, and copy under controlled logic.

**Indexes and collection options** are vital parts of recovery output. `--noIndexRestore` and `--noOptionsRestore` skip portions of metadata yet can alter **unique constraints, TTL, collation, schema validators, and query performance**. `--bypassDocumentValidation` helps load legacy data under controlled conditions, but never turns malformed types into valid data.

The safe workflow is **preserve current state → restore to an isolated namespace → inspect documents/indexes/validators → reconcile business dependencies → apply approved repairs → verify and clean up staging**. If the goal is state at an exact past timestamp, evaluate **point-in-time recovery** and backup platform capabilities rather than confusing it with namespace filtering.

### Official References

- [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/)
- [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB Manual — Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/)
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/)
- [MongoDB Manual — Modify Collection Validation](https://www.mongodb.com/docs/manual/core/schema-validation/modify-schema-validation/)
- [MongoDB Atlas — Backup and Restore](https://www.mongodb.com/docs/atlas/backup-restore-cluster/)
