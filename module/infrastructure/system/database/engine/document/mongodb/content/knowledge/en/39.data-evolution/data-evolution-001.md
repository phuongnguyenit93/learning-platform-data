# Schema Versioning and Old-to-New Application Compatibility in MongoDB

## Lesson Objectives

MongoDB supports flexible documents: two documents in the same collection can carry different fields, nested structures, or data types. This flexibility helps applications evolve quickly, but **it does not automatically guarantee that an older application version will understand data written by a newer version**.

For example, application V1 stores the customer's name in the `full_name` field. Application V2 wants to rename it to `display_name`, add `schema_version`, and migrate several customer statuses. During a rolling deployment, both application versions may still be serving requests, running workers, or processing events. If you only change the Java annotation and deploy, the consequences can include:

- V1 reads a new document and cannot find `full_name`.
- V2 reads an old document and `display_name` is `null`.
- V1 `save`s a document to which V2 added fields, accidentally deleting the new fields.
- V1 and V2 write to two different field names, making the data inconsistent.
- Queries/indexes/validators only know about one schema and therefore miss records.
- An incident forces a code rollback, but the data has already been converted to a format that the old code cannot read.

This lesson belongs to **Database Engine Document MongoDB → Data Evolution → Schema Versioning and Compatibility Between Old and New Applications**.

After this lesson, you will be able to:

1. Distinguish between **document schema version**, **application version**, **event/API contract version**, **MongoDB Server version**, and **Feature Compatibility Version (FCV)**.
2. Draw a V1/V2 matrix across both read and write dimensions and determine when a mixed-version deployment is safe.
3. Build an **expand → migrate → contract** process without having to convert the entire collection at once.
4. Design **dual-read**, **dual-write**, fallbacks, field aliases, and rules to determine the source of truth when old writers are present.
5. Use the `schema_version` field when needed, without treating it as a substitute for schema validation or mapping.
6. Backfill in small batches with checkpoints, safety predicates, safe retries, and reconciliation.
7. Avoid lost updates when an older application uses full-document replacement.
8. Manage `missing`, `null`, numeric types, date/time, enums, embedded objects, and arrays during schema changes.
9. Use MongoDB `$jsonSchema` validators with validation levels appropriate to each rollout phase.
10. Plan index creation/removal, unique constraint changes, and data changes in a sharded cluster.
11. Use Spring Data MongoDB `@Field`, `MongoTemplate`, conditional updates, and optimistic locking during the compatibility window.
12. Define rollback boundaries, migration completion criteria, monitoring, and recovery plans.
13. Write integration tests for every pair of application and schema versions still permitted to operate.
14. Design runbooks and rehearse data evolution without losing business correctness.

> **Principle:** A successful schema migration must preserve **correctness while both old and new code are running**, not merely allow the new code to read the data after every record has been converted.

---

## 1. What Does “MongoDB Schemaless” Actually Mean?

MongoDB does not enforce that every document in a collection must have the same structure by default. For example:

~~~javascript
db.customers.insertMany([
  {
    _id: "CUS-001",
    tenant_id: "tenant-a",
    full_name: "Nguyễn An",
    status: "ACTIVE"
  },
  {
    _id: "CUS-002",
    tenant_id: "tenant-a",
    display_name: "Trần Bình",
    schema_version: 2,
    status: "ACTIVE",
    preferred_language: "vi"
  }
]);
~~~

Both can coexist in `customers`. However:

~~~javascript
db.customers.find({
  display_name: "Nguyễn An"
});
~~~

does not find CUS-001 because that document only has `full_name`.

### 1.1. “Flexible Schema” Does Not Mean “No Schema”

Applications, queries, indexes, validators, ETL pipelines, dashboards, event consumers, and other services **all assume a shared schema**. That set of assumptions is the **data contract**, even if the database has not enabled a validator yet.

### 1.2. Schema Across Multiple Layers

| Layer | Related Contract | Example |
|---|---|---|
| BSON document | Field names, types, structure | `display_name:string` |
| Java entity | Properties, codecs/converters | `Customer.displayName` |
| Query/index | Field paths used for filtering/sorting | `display_name` |
| API JSON | Public response/request schema | `displayName` |
| Event schema | Payload emitted by producer | `customerDisplayName` |
| Report/ETL | Columns or metrics from MongoDB | `customer_name` |
| Authorization | Tenant/roles/visibility | `tenant_id` |

Changing a field name in MongoDB can impact all of the layers above, even when the Java entity compiles successfully.

---

## 2. Five Types of Versions That Are Easily Confused

### 2.1. Application version

For example, `order-service 1.12` and `order-service 2.0`. This is the version of the running binary/container. The same application version can read multiple document schema versions.

### 2.2. Document schema version

A field defined by the application, for example:

~~~javascript
{
  _id: "CUS-001",
  schema_version: 2,
  display_name: "Nguyễn An"
}
~~~

MongoDB **does not automatically add or increment** this field. Business migration or application code is responsible for it.

### 2.3. API version

`/api/v1/customers` and `/api/v2/customers` may use different DTOs while reading the same MongoDB collection. The API version **does not necessarily equal** `schema_version`.

### 2.4. Event schema version

A `CustomerUpdated` event may have `event_schema_version:3`. An event can persist for a long time in a broker or data lake, independent of the current document schema.

### 2.5. MongoDB Server/FCV

`db.version()` reports the server version, while FCV is the compatibility state of persisted features in a MongoDB deployment. FCV **is not** the `schema_version` of a business entity.

### 2.6. Comparison Table

| Version | Owner | Incremented When |
|---|---|---|
| Application | Development/deployment team | Code release |
| Document schema | Collection/domain owner | Persistent contract changes |
| API | API owner | External interface contract changes |
| Event | Event producer/contract owner | Payload semantics change |
| Server/FCV | DBA/SRE/Atlas | MongoDB engine/features are upgraded |

Do not create a rule such as “app V2 requires every document to have schema_version=2” if the application in practice accepts legacy data during the transition phase.

---

## 3. What Are Backward Compatibility and Forward Compatibility?

### 3.1. Backward compatibility

**The new application can read old data.**

~~~text
Document V1 -> Application V2 -> OK
~~~

For example, V2 reads `full_name` if `display_name` is not yet present.

### 3.2. Forward compatibility

**The old application tolerates data written by the new application**, within the designed contract.

~~~text
Document V2 -> Application V1 -> OK
~~~

If V2 only writes `display_name` while V1 only reads `full_name`, this requirement fails.

### 3.3. Write compatibility

Being able to read does not mean **being able to write safely**. An older application may decode a V2 document, yet `save` the whole document back and drop the new fields it does not know about.

### 3.4. Mixed-version window

The period during which multiple versions operate concurrently, including:

- REST API instances.
- Background workers.
- Scheduled jobs.
- Change Stream consumers.
- Mobile/offline clients (if they directly affect the contract via API).
- External services granted read/write access to the collection.
- Batch/ETL jobs running on schedules not aligned with deployments.

A migration is safe only when considering **all writers/readers**, not just the new pods of the web service.

---

## 4. Application and Document Compatibility Matrix

Assume:

- App V1 only knows `full_name`.
- App V2 understands `full_name` and `display_name`.
- Document V1 has `full_name`.
- Document V2 has `display_name`.

### 4.1. Read Matrix

| Reader | Document V1 | Document V2 |
|---|---|---|
| App V1 (full_name only) | Readable | **Error/missing name** if V2 does not keep the old field |
| App V2 (dual-read) | Readable via fallback | Readable |

### 4.2. Write Matrix

| Writer | Document V1 | Document V2 |
|---|---|---|
| App V1 (writes full_name only) | Writes old field properly | Can cause data divergence if V2 uses display_name |
| App V2 (writes both) | Preserves V1 readability | Maintains both fields, but must avoid races |

### 4.3. Minimum Conditions

For a safe deployment, explicitly state:

1. Reader V2 can read both V1 and V2 documents.
2. Reader V1 can read documents created by writer V2 while V1 is still running.
3. Writer V1 does not destroy data that V2 needs.
4. Writer V2 does not produce values that V1 cannot understand (especially enums/validation).
5. Concurrent update changes are resolved in a well-defined order.
6. Code rollback within the compatibility window can still read and write.

### 4.4. Do Not Only Check “Query Succeeded”

A query that returns no error yet yields `null`, drops a field, or skips 20% of records is still a contract failure.

---

## 5. Running Case Study: Renaming Customer Name

We use the `customers` collection.

### 5.1. Schema V1

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  full_name: "Nguyễn An",
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

### 5.2. Target Schema V2

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  display_name: "Nguyễn An",
  schema_version: 2,
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

### 5.3. Transitional Schema

~~~javascript
{
  _id: "CUS-101",
  tenant_id: "tenant-a",
  full_name: "Nguyễn An",
  display_name: "Nguyễn An",
  schema_version: 2,
  status: "ACTIVE",
  created_at: ISODate("2026-11-01T10:00:00Z")
}
~~~

The transitional schema keeps both fields. That allows the older application to continue reading, **but it does not yet solve the problem when an old writer updates only full_name**; this issue is addressed in the rollout steps.

### 5.4. Why Not `$rename` Immediately?

~~~javascript
db.customers.updateMany(
  {},
  {
    $rename: {
      full_name: "display_name"
    }
  }
);
~~~

This command removes the old field name on the modified documents. App V1 still reading `full_name` will lose data, and duplicate/target fields may be overwritten according to `$rename` semantics. Do not run it as an initial step of a zero-downtime migration.

---

## 6. Standard Strategy: expand → migrate → contract

~~~text
          V1 running
                |
                v
       EXPAND compatibility
       - V2 reads old/new schema
       - V2 writes data so V1 still understands it
       - indexes/validators temporarily support both
                |
                v
          MIGRATE data
       - backfill in batches
       - observe lag/duplicates
       - reconcile and fix drift
                |
                v
        RETIRE old writers
       - stop V1 apps/jobs writing old field
       - final reconciliation
       - switch canonical field
                |
                v
           CONTRACT
       - remove old field when safe
       - remove fallbacks/temporary code
       - tighten validator and clean up indexes
~~~

### 6.1. Expand

Expand the software to understand multiple schema versions without forcing every document to change immediately.

### 6.2. Migrate

Backfill legacy data to the new format while different versions remain active. To avoid drift, old writers must be synchronized/locked or reconciliation must be performed.

### 6.3. Contract

Only drop the old schema after **no consumer/writer needs it anymore**, the migration is complete, the rollback window has ended, and monitoring proves there are no remaining dependencies.

### 6.4. Do Not Cram All Three Phases Into One Deploy

Packing “new code + field rename + index drop + strict validator” into a single release makes rollback very difficult. Split across multiple releases with clear checkpoints.

---

## 7. Risk Classification of Schema Changes

| Change | Compatibility Risk | Approach |
|---|---|---|
| Add optional field | Usually low for readers tolerating unknown fields | Deploy reader safely; check replace writers |
| Add required field | High for old documents | Default/fallback → backfill → validator |
| Rename field | High | Dual-read/write, final sync, contract |
| Remove field | High if old consumers exist | Inventory consumers, deprecate, staged removal |
| Change BSON type | High | Dual fields/converter/backfill, test precision |
| Change enum value | High | Readers accept both old/new before writers emit new values |
| Change embedded → reference | Very high | Dual representation, consistency, and backfill |
| Split collection | High | Data ownership/cutover/transaction/outbox |
| Merge collections | High | Key collision, dedup, schema reconciliation |
| Change tenant/shard key | Very high | Changes topology/query patterns, dedicated procedures |
| Change index | Affects reads/writes and uniqueness | Create-first, validate, cutover, drop-last |
| Change validator | Can block old writes | Gradual warn/moderate/error per policy |

No change is “guaranteed safe” simply because the JSON document still parses.

---

## 8. Should You Add a `schema_version` Field to Each Document?

### 8.1. When It Is Useful

`schema_version` helps:

- Identify the codec/mapper to use for different structures.
- Count documents not yet migrated.
- Create backfill checkpoints and migration cohorts.
- Select version-specific strategies when historical data must live for a long time.
- Provide audit/provenance in ETL.

Example:

~~~javascript
{
  _id: "CUS-101",
  schema_version: 2,
  display_name: "Nguyễn An"
}
~~~

### 8.2. Not Always Necessary

If you only add an optional field and readers handle missing values well, stamping `schema_version` across the entire collection may not bring enough value.

### 8.3. Versions Must Have Semantics

Example definition:

| schema_version | Meaning |
|---|---|
| Missing or 1 | Canonical name in `full_name` |
| 2 | `display_name` populated, V2-compatible; `full_name` may remain during transition |
| 3 | Legacy field removed; `display_name` only, new constraints |

If version 2 only means “code deployed on date X”, it is meaningless to the data contract.

### 8.4. Monotonic Version or Multi-Dimensional?

Some systems have multiple bounded contexts in the same collection. A single integer may not capture independent changes. Version fields by logical sections or migration markers can be used instead.

### 8.5. Do Not Use Version as a Substitute for Field Checks

A document marked `schema_version:2` that lacks `display_name` is still broken data. During reads and backfills, inspect the **actual shape**, rather than trusting the marker alone.

### 8.6. Version Must Not Auto-Increment on Every Update

`schema_version` is the version of the **data shape**, not an optimistic locking version. Changing `status` from PENDING to PAID does not necessarily increment `schema_version`.

---

## 9. Distinguishing `schema_version` and Optimistic Version

Example:

~~~javascript
{
  _id: "CUS-101",
  schema_version: 2,
  version: NumberLong("7"),
  display_name: "Nguyễn An"
}
~~~

- `schema_version=2`: the document structure conforms to contract V2.
- `version=7`: the entity update generation, used for optimistic locking or CAS.

### 9.1. Why Does This Matter?

If a backfill changes the shape from V1 to V2 while a user edits `display_name`, concurrent updates must be protected. Use an optimistic version or conditional field predicates; do not use `schema_version` as a concurrency counter if normal operations do not manage it.

### 9.2. Version Counter Requires a Consistent Write Path

If the new app uses `@Version` but the old app writes via raw `updateOne` without incrementing version, CAS will fail to detect every write. During transition, identify all writers and update conventions.

---

## 10. Reader V2: Dual-Read with Fallback

An illustrative Java mapping:

~~~java
public final class CustomerNameView {

    private final String displayName;

    public CustomerNameView(String displayName) {
        this.displayName = displayName;
    }

    public String displayName() {
        return displayName;
    }
}
~~~

At the read model layer, we can extract both fields from raw BSON:

~~~java
import org.bson.Document;
import com.mongodb.client.MongoCollection;

MongoCollection<Document> rawCustomers =
    mongoDatabase.getCollection("customers");

Document raw = rawCustomers.find(
    new Document("_id", "CUS-101")
).first();

if (raw != null) {
    String oldName = raw.getString("full_name");
    String newName = raw.getString("display_name");

    // While V1 is still writing, full_name may
    // hold the latest value: choose an explicit policy.
    String selected = oldName != null
        ? oldName
        : newName;

    CustomerNameView view =
        new CustomerNameView(selected);
}
~~~

### 10.1. “Which Field Takes Precedence?” Is a Business Decision

If writer V1 is still allowed to update `full_name` and writer V2 always updates both `full_name`/`display_name`, reading **preferring the old field** during the mixed-version window reduces the risk of reading a stale new value after a V1 update.

Once every old writer has been stopped and final synchronization is complete, switch the reader to **prefer `display_name`**.

### 10.2. Do Not Blindly Use `display_name ?? full_name` Without Considering Writers

If V1 changes `full_name` today while `display_name` still holds yesterday's value, a reader preferring the new field will display the old name. Dual-read only solves missing fields; **it does not automatically resolve two conflicting values**.

### 10.3. Null and Empty String

An empty field `""` may be an invalid value, yet Java `null`-based fallback does not handle empty strings. Define rules:

- Missing: fallback.
- Explicit null: fallback or business-null per contract.
- Empty string: reject, normalize, or treat as a value?
- Both present but different: prioritize by writer phase, log discrepancy.

### 10.4. Do Not Silently Swallow Exceptions

If a field exists with the wrong BSON type (number instead of string), `getString` may throw. Do not catch all exceptions and default to an empty name; record a data-quality metric and handle according to policy.

---

## 11. Dual-Read in MongoDB Aggregation

Use `$ifNull` when you want a simple fallback:

~~~javascript
db.customers.aggregate([
  {
    $match: {
      tenant_id: "tenant-a"
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      resolved_name: {
        $ifNull: [
          "$display_name",
          "$full_name"
        ]
      },
      schema_version: {
        $ifNull: ["$schema_version", 1]
      }
    }
  }
]);
~~~

### 11.1. Only Use This Order When Appropriate for the Phase

The pipeline above prefers `display_name`. During a mixed writer window where V1 can still update `full_name`, you may need to reverse the order:

~~~javascript
resolved_name: {
  $ifNull: [
    "$full_name",
    "$display_name"
  ]
}
~~~

This is the difference between **presence-based fallback** and **determining the most recent source**.

### 11.2. `$ifNull` Does Not Fix the Data

It only computes a result field at read time. The collection still has a mixed schema, and queries/indexes on `display_name` still will not automatically use `full_name`.

### 11.3. Correctness of Pagination/Sort/Search

If a user sorts by the resolved name, an index solely on `display_name` may not support it efficiently when `$ifNull` must be evaluated. During transition, the API may have to query both paths or pay the sort cost; this is why migrations require an index and performance plan.

---

## 12. Writer V2: Consistent Dual-Write in One Document

During the compatibility window, every V2 name update must write **both fields in a single operation**:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    tenant_id: "tenant-a"
  },
  {
    $set: {
      full_name: "Nguyễn An New",
      display_name: "Nguyễn An New",
      schema_version: 2
    }
  }
);
~~~

### 12.1. Why a Single Operation?

If two separate commands are issued:

~~~text
set full_name
     |
request crash
     |
display_name not yet updated
~~~

the two fields can diverge even without an old writer. A single document update with `$set` on both fields is atomic in MongoDB.

### 12.2. But Writer V1 Can Still Cause Drift

V1 only runs:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-101" },
  { $set: { full_name: "Name from V1" } }
);
~~~

Result:

~~~javascript
{
  full_name: "Name from V1",
  display_name: "Nguyễn An New",
  schema_version: 2
}
~~~

The two fields differ. **V2's dual-write cannot fix a V1 writer that V2 does not control.**

### 12.3. Handling Options

1. **Prefer the old field on reads** until V1 writers completely stop.
2. **Upgrade V1 with a compatibility patch** so V1 also dual-writes, if feasible.
3. **Temporarily lock one write type** during a short window, if the business allows it.
4. **Synchronize via Change Streams/outbox** with ordering/versioning; more complex and introduces latency.
5. **Route writers**: send all name updates through a single service that already supports dual-write.

Do not choose “last write wins” based on two unreliable clocks without an explicit design.

---

## 13. Zero-Downtime Rollout Sequence

### Phase 0 — Inventory

Identify all writers/readers:

- Java API V1.
- Admin UI.
- Scheduled CRM sync.
- MongoDB migration jobs.
- Data pipelines.
- Change Stream consumers.
- Mobile/offline reconciliation.
- Direct maintenance scripts on MongoDB.

Document who reads/writes `full_name` and whether any use full replacement.

### Phase 1 — Safety release

If V1 uses full-document `save`/`replaceOne` and deletes unknown fields, you must **fix V1 to use field-level updates or preserve unknown fields** before V2 adds data. This is a mandatory prerequisite in many systems.

### Phase 2 — Expand app V2

V2:

- Reads both `full_name`/`display_name`.
- While V1 is still running, chooses read precedence matching the writer phase.
- Writes both fields when updating the name.
- Still emits enum/event payloads understood by V1.
- Does not delete the legacy field on its own.

### Phase 3 — Gradual V2 Deploy

Canary a portion of traffic and monitor errors/mismatches. The remaining V1 instances continue operating.

### Phase 4 — Backfill

Copy `full_name` to `display_name` on documents missing it, setting the `schema_version` marker with appropriate predicates.

### Phase 5 — Drain old writers

Ensure no V1 pods, workers, scheduled jobs, or scripts are writing `full_name` alone. It may be necessary to wait for in-flight requests and job leases.

### Phase 6 — Final reconciliation

Re-sync documents updated by V1 writers after the backfill, establish the canonical source, and verify counts and sample diffs.

### Phase 7 — Switch canonical

All readers use `display_name` as the primary source; V2 may continue dual-writing during the rollback window.

### Phase 8 — Contract

Once there is no V1 dependency/rollback need, remove `full_name` in a controlled manner, update validators/indexes, and remove compatibility code.

---

## 14. Backfill: Migrating Legacy Data to the New Schema

### 14.1. Why Not Run an Unbounded Command Directly in Production?

A single `updateMany` scanning tens of millions of documents can cause:

- Increased I/O and CPU.
- Spikes in oplog/change stream volume.
- Write contention.
- Disk/storage growth.
- Replica lag.
- Impact on p95/p99 latency.
- Difficulty stopping and recovering if the job fails midway.

On small datasets a single `updateMany` may work, but production usually requires **batching, rate limiting, checkpointing, and monitoring**.

### 14.2. Single-Pass Copy Using an Aggregation Update Pipeline

A conditional example targeting only documents missing the new field:

~~~javascript
db.customers.updateMany(
  {
    full_name: { $type: "string" },
    display_name: { $exists: false }
  },
  [
    {
      $set: {
        display_name: "$full_name",
        schema_version: 2
      }
    }
  ]
);
~~~

Updating with an **aggregation pipeline** allows using `"$full_name"` as an expression reading the current field's value. Using a classic update `{$set:{display_name:"$full_name"}}` would write the literal string `"$full_name"` rather than copying the content.

### 14.3. Idempotency

The filter `display_name:{$exists:false}` prevents retries from overwriting documents that already have the new field. However, if the new field already exists yet is **stale**, this step **does not fix the drift**; final reconciliation is a separate phase.

### 14.4. Null/Missing Edge Case

If `full_name` is null/missing, the `$type:"string"` filter skips the document; classify and handle it per policy instead of writing `display_name:null` and marking the migration successful.

### 14.5. Do Not Bump Version When the Contract Is Not Met

If app V2 requires both a non-empty `display_name` and a valid `tenant_id`, documents that do not meet this must enter a needs-repair state; do not simply set `schema_version:2` on every document.

---

## 15. Resumable Batched Backfill

Below is a practice example in `mongosh` to process documents missing the new field in `_id` order.

~~~javascript
use schema_evolution_lab

const batchSize = 200;
let lastId = null;
let totalModified = 0;

while (true) {
  const filter = {
    full_name: { $type: "string" },
    display_name: { $exists: false }
  };

  if (lastId !== null) {
    filter._id = { $gt: lastId };
  }

  const batch = db.customers.find(
    filter,
    { _id: 1 }
  ).sort({ _id: 1 }).limit(batchSize).toArray();

  if (batch.length === 0) {
    break;
  }

  const writes = batch.map(doc => ({
    updateOne: {
      filter: {
        _id: doc._id,
        full_name: { $type: "string" },
        display_name: { $exists: false }
      },
      update: [
        {
          $set: {
            display_name: "$full_name",
            schema_version: 2
          }
        }
      ]
    }
  }));

  const result = db.customers.bulkWrite(
    writes,
    { ordered: false }
  );

  totalModified += result.modifiedCount;
  lastId = batch[batch.length - 1]._id;

  print(
    "lastId=" + lastId
    + " modified=" + totalModified
  );
}
~~~

### 15.1. Limitations of the Illustrative Script

- Use in lab/staging or **approved** production.
- No persistent checkpoint across process restarts; production needs to store `lastId`/job version/metadata in a control collection.
- Scans only documents currently matching the filter, so new writes to `_id`s smaller than the checkpoint may appear **after the cursor has passed**; a final reconciliation pass is needed.
- Concurrent writers may alter data between finding the batch and executing the update; the filter is rechecked on write, but old writers can still introduce drift afterward.
- No built-in sleep/rate limiting; production must throttle throughput based on monitoring.
- If `_id` has mixed BSON types, `_id` comparisons must be tested to ensure consistent ordering/pagination.
- Production must handle bulk errors and partial results rather than assuming every batch succeeds.
- Bulk update pipelines require a MongoDB Server version that supports aggregation pipeline updates.

### 15.2. Safe Checkpointing

A practical design:

~~~javascript
{
  _id: "customer_name_v2_backfill",
  run_id: "MIG-2026-11-14",
  last_id: "CUS-40000",
  status: "RUNNING",
  batches_completed: 200,
  modified_total: 38950,
  updated_at: ISODate("2026-11-14T05:00:00Z")
}
~~~

The checkpoint should only advance after a batch succeeds according to chosen criteria. If an unknown write result occurs, query/reconcile before continuing to avoid misreporting.

### 15.3. Partitioning by Tenant

In multi-tenant data, you can assign tenant cohorts to limit blast radius and simplify canary/rollback. However, check for skew: a single tenant may be larger than all other tenants combined.

---

## 16. Final Reconciliation: Handling Differences Between Two Fields

After **no V1 writers remain**, establish the old field as the final source of truth under the example compatibility policy.

### 16.1. Finding Divergent Documents

~~~javascript
db.customers.aggregate([
  {
    $match: {
      full_name: { $type: "string" },
      display_name: { $type: "string" }
    }
  },
  {
    $match: {
      $expr: {
        $ne: [
          "$full_name",
          "$display_name"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      tenant_id: 1,
      full_name: 1,
      display_name: 1
    }
  },
  { $limit: 100 }
]);
~~~

### 16.2. Why Not Automatically Overwrite Everything with the New Field?

If V1 updated `full_name` after the initial backfill, `display_name` may be stale. Determine the true source from phase/writer policy or audit logs, not by assuming “the newer field name is right.”

### 16.3. Final Sync Under Old-Canonical Policy

Once certain that the **old field was authoritative** during the mixed window and no old writers remain:

~~~javascript
db.customers.updateMany(
  {
    full_name: { $type: "string" }
  },
  [
    {
      $set: {
        display_name: "$full_name",
        schema_version: 2
      }
    }
  ]
);
~~~

This command can overwrite the new field on documents holding different values; **only run it if the old-canonical policy is certain** and backups/audits exist. In production, execute in batches with checkpoints rather than always running a collection-wide `updateMany`.

### 16.4. If V2 Already Allowed Independent Writes to the New Field

When both sides write independently, there is no longer a simple canonical source. You must use versions/event ordering/audits to merge; **do not infer update order from which field exists**.

---

## 17. Spring Data MongoDB: Mapping V1 and V2

### 17.1. Entity V1

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class CustomerV1 {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("full_name")
    private String fullName;

    public CustomerV1() {}

    // Getters/setters.
}
~~~

### 17.2. Entity V2 Reading Both Fields

~~~java
@Document("customers")
public class CustomerV2 {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("full_name")
    private String legacyFullName;

    @Field("display_name")
    private String displayName;

    @Field("schema_version")
    private Integer schemaVersion;

    public CustomerV2() {}

    public String nameDuringMixedWindow() {
        return legacyFullName != null
            ? legacyFullName
            : displayName;
    }

    public String nameAfterCutover() {
        return displayName != null
            ? displayName
            : legacyFullName;
    }

    // Getters/setters for mapped fields.
}
~~~

### 17.3. Why Two Methods?

During the mixed window, the old writer may be the most recent source of the name. After stopping old writers and running final sync, the new field becomes canonical. This must be controlled by a **migration phase/feature flag**, not deployed arbitrarily per service.

### 17.4. Mapped Query Paths

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("displayName").is("Nguyễn An")
);

CustomerV2 result = mongoTemplate.findOne(
    query,
    CustomerV2.class
);
~~~

When Spring Data mapping applies, property `displayName` maps to `display_name`. With the raw driver or custom query expressions, verify the actual BSON field names.

### 17.5. Do Not Just Change the Annotation

Changing `@Field("full_name")` to `@Field("display_name")` **does not automatically migrate stored data**. Nor does it allow app V1 to read `display_name`.

---

## 18. Spring Data MongoTemplate: Atomic Dual-Write

Example V2 service updating the name:

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerRenameService {

    private final MongoTemplate template;

    public CustomerRenameService(MongoTemplate template) {
        this.template = template;
    }

    public boolean changeName(
            String trustedTenantId,
            String customerId,
            String newName) {

        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                "Name must not be blank"
            );
        }

        Query q = Query.query(
            Criteria.where("id").is(customerId)
                .and("tenantId").is(trustedTenantId)
        );

        Update u = new Update()
            .set("legacyFullName", newName)
            .set("displayName", newName)
            .set("schemaVersion", 2);

        UpdateResult r = template.updateFirst(
            q,
            u,
            CustomerV2.class
        );

        return r.wasAcknowledged()
            && r.getMatchedCount() == 1;
    }
}
~~~

### 18.1. Why Use `Update` Instead of `save`?

`Update` modifies only specific fields, avoiding replacing the entire document and dropping fields unknown to the model.

### 18.2. Check matchedCount

If the customer does not exist or the tenant does not match, do not treat the update as successful. For security, return an appropriate response without leaking whether the ID exists in another tenant.

### 18.3. Dual-Write Is Not Two Transactions

Both field names live in **the same document**, set by a single MongoDB update, so it is atomic at the document level. You do not need to open a transaction solely to update two fields in the same document.

### 18.4. When CAS Is Needed

If V1 and V2 both update the name and the business requires conflict detection, add the expected version to the Query and increment a unified optimistic version; note that **every writer** must follow the version protocol.

---

## 19. Dangerous Issue: Full-Document Replacement from the Old App

Suppose V2 writes:

~~~javascript
{
  _id: "CUS-101",
  full_name: "Nguyễn An",
  display_name: "Nguyễn An",
  schema_version: 2,
  loyalty_points: 100
}
~~~

App V1 reads the entity knowing only:

~~~text
_id
full_name
loyalty_points
~~~

Then uses `save`/`replaceOne` to replace the entire document:

~~~javascript
{
  _id: "CUS-101",
  full_name: "Nguyễn An",
  loyalty_points: 120
}
~~~

The `display_name` and `schema_version` fields can be lost.

### 19.1. How to Prevent It

- Convert V1 writes to `$set`/`$inc` on only the modified fields.
- If the old writer cannot be changed, delay rolling out the new schema or isolate records/writes.
- In some models, preserve unknown fields via extra-elements mapping, though still test carefully due to replace semantics.
- Use version/CAS or transactions if the business requires conflict detection.
- Monitor document counts per schema while V1 writes continue.

### 19.2. Do Not Assume Optimistic Locking Covers Every Actor

`@Version` in Spring Data only helps if all involved operations actually obey the version/conditional check. A raw script or legacy service that does not increment version can render that protection ineffective.

### 19.3. Partial Read Models Are Also Dangerous

Even when V2 knows all fields, if a query projection loads only a few fields and then calls `save`, the unloaded fields may disappear. Never use a partial entity for full replacement.

---

## 20. Data Cases: `missing`, `null`, and Empty

Example:

~~~javascript
{ _id: 1 }
{ _id: 2, display_name: null }
{ _id: 3, display_name: "" }
{ _id: 4, display_name: "Nguyễn An" }
~~~

These four states can carry different business meanings.

### 20.1. Existence Query

~~~javascript
db.customers.find({
  display_name: { $exists: false }
});
~~~

Finds documents that **do not have** the field.

### 20.2. Null Query

~~~javascript
db.customers.find({
  display_name: null
});
~~~

Usually matches both BSON null **and missing**. If you only want fields explicitly set to null, you can use `$type:10` per MongoDB semantics.

### 20.3. Missing Differs from Null During Migration

If `display_name` is missing, backfilling from `full_name` makes sense. If `display_name:null` means “the customer intentionally cleared their display name,” automatically backfilling could reverse that intent.

### 20.4. Null and Java Primitives

If you add an `int loyaltyPoints` field, documents lacking the field may decode as 0 in some Java mapping paths. If you need to distinguish unset from 0, use `Integer`/presence semantics and validators.

### 20.5. Fallback Does Not Fix Wrong Types

A `display_name` containing BSON number 123 does not become a valid name just because `$ifNull` does not treat it as null. Validation/data repair is required.

---

## 21. Changing BSON Types: String → Number or Double → Decimal128

### 21.1. Risky Case

V1 stores:

~~~javascript
{
  amount: "125000"
}
~~~

V2 wants:

~~~javascript
{
  amount_minor: NumberLong("125000")
}
~~~

If V2 only changes the Java property from `String` to `Long`, V1 data is still a string. Codecs/converters may fail or behave differently from what the business intends.

### 21.2. Transitional Approach

- Add a new field `amount_minor`.
- Reader V2 reads the new field if valid; otherwise parses the old field using explicit rules.
- Writer V2 writes both fields during the compatibility window when V1 needs it.
- Backfill with parse/overflow checks.
- Reconcile values and route bad records to a repair queue.
- Remove the old field only once V1 readers/writers stop.

### 21.3. Do Not Use Double Arbitrarily for Money

Binary floating-point has precision errors. For money, use `NumberLong` minor units or `Decimal128` depending on currency/rounding policy. Changing representations must consider precision, rounding, and exchange rates.

### 21.4. Converting via Aggregation Pipeline

Example for valid integer strings only:

~~~javascript
db.invoices.updateMany(
  {
    amount_minor: { $exists: false },
    amount_string: {
      $type: "string",
      $regex: /^[0-9]+$/
    }
  },
  [
    {
      $set: {
        amount_minor: {
          $toLong: "$amount_string"
        },
        schema_version: 2
      }
    }
  ]
);
~~~

**Note:** Regex does not guarantee the number fits in Int64; `$toLong` can error on overflow. In production, you can use `$convert` with `onError`/`onNull`, classify invalid data, and avoid marking success if conversion failed.

### 21.5. Numeric Comparison and Indexes

If the same field holds both string `"100"` and number `100`, sorting/filtering based on BSON type comparison differs from mathematical expectation. Avoid letting API V2 rely on an index/query assuming a uniform field type while backfill is still underway.

---

## 22. Enum and Business Status Versioning

Suppose V1 only knows:

~~~text
PENDING
PAID
CANCELLED
~~~

V2 adds:

~~~text
PARTIALLY_REFUNDED
~~~

If V2 writes `PARTIALLY_REFUNDED` while the V1 Java enum decoder does not know this value, V1 may fail to decode.

### 22.1. Expand Reader Before Writer

1. Deploy a V1.1 reader that accepts the new status while handling it via a safe fallback.
2. Confirm all consumers understand the status.
3. Enable the writer to emit the new value via a feature flag.
4. Monitor errors/backward compatibility.
5. Once migration is complete, old fallbacks can be removed if the contract allows.

### 22.2. Do Not Map Unknown Values to a State That Changes Business Meaning

For instance, mapping every unknown status to `PENDING` could cause a refunded order to be processed as unpaid. For state machines/finance, unknown values usually must be rejected/quarantined or handled under an explicit policy.

### 22.3. Event Consumers Must Also Be Compatible

If application V2 publishes `PARTIALLY_REFUNDED` to Kafka, un-updated old consumers can still break even if database queries succeed.

---

## 23. Changing Nested Objects and Array Schemas

V1:

~~~javascript
{
  shipping_address: "12 Street A, HCM"
}
~~~

V2:

~~~javascript
{
  shipping_address_v2: {
    line1: "12 Street A",
    city: "Ho Chi Minh",
    country: "VN"
  }
}
~~~

### 23.1. Why Not Overwrite the Same Field Immediately?

V1 uses `String shippingAddress`, V2 uses a nested object. If the same BSON key is sometimes a string and sometimes a document, codecs/queries can fail or lose meaning. Creating a new field during the compatibility window is usually clearer.

### 23.2. You Cannot Parse Every Address String Perfectly

Unstructured legacy addresses may lack country/city. Unconvertible records need review/manual repair rather than fabricated defaults.

### 23.3. Embedded Arrays

V1:

~~~javascript
items: [
  { sku: "SKU-1", qty: 2 }
]
~~~

V2:

~~~javascript
items_v2: [
  {
    sku: "SKU-1",
    quantity: 2,
    unit_price_minor: NumberLong("100000")
  }
]
~~~

If price is missing in legacy data, determine the source: order snapshot, product price at purchase, invoice ledger, etc. Do not arbitrarily use the current product price to reconstruct historical prices.

### 23.4. Array Update Paths

While V1/V2 coexist, one worker uses `items.$[line].qty` and V2 uses `items_v2.$[line].quantity`; without synchronization, the two structures diverge. Define the canonical representation and write compatibility strategy.

---

## 24. Embedded → Referenced Documents

For example, V1 stores shipping addresses directly inside customer:

~~~javascript
{
  _id: "CUS-101",
  addresses: [
    { id: "ADDR-1", city: "HCM" }
  ]
}
~~~

V2 wants to split them:

~~~javascript
// customers
{
  _id: "CUS-101",
  address_ids: ["ADDR-1"]
}

// addresses
{
  _id: "ADDR-1",
  customer_id: "CUS-101",
  city: "HCM"
}
~~~

### 24.1. Risks

- The two collections can become temporarily inconsistent.
- Old writers only update embedded addresses while new readers only read references.
- Delete cascades/tenant isolation change.
- One-to-many references incur eventual consistency if synced via CDC.
- Multi-document transactions carry cost/constraints.

### 24.2. Transition

- The new reader can read both embedded and referenced representations.
- Backfill addresses with stable IDs and unique keys.
- Sync writes or temporarily route ownership through a single service.
- Reconcile referential integrity.
- Once no old writers remain, switch canonical to references.
- Delete the embedded field only after the rollback window.

### 24.3. Do Not Assume Transactions Solve External Consistency

MongoDB transactions can be atomic across documents under supported deployment conditions. However, external message brokers/payment providers/HTTP callbacks still require outbox/idempotency.

---

## 25. MongoDB Schema Validation: Phased Rollout

MongoDB can enforce validators using `$jsonSchema` or query expressions. Validators **do not automatically migrate legacy data**.

### 25.1. Initial Phase: Accept Old/New Shapes

If the collection holds two schemas, you can start with a lenient validator and `validationAction:"warn"` to observe without blocking old writers.

Example:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $or: [
      { full_name: { $type: "string" } },
      { display_name: { $type: "string" } }
    ]
  },
  validationLevel: "moderate",
  validationAction: "warn"
});
~~~

This condition is only illustrative and does not check all fields/tenant rules. **`collMod` replaces the existing validator configuration**, so inspect the production validator before changing it; do not overwrite existing safeguards.

### 25.2. `validationLevel`

- `strict`: checks inserts and updates against the validator.
- `moderate`: checks inserts and updates on existing documents that are already valid; documents that are already invalid are handled more leniently per MongoDB semantics.

### 25.3. `validationAction`

- `warn`: logs warnings for violations instead of blocking writes.
- `error`: rejects violating writes when they fall under validation scope.

Choose based on data state, repair capability, and rollout goals. Do not leave `warn` enabled forever and assume the schema is enforced.

### 25.4. Post-Migration: Stricter Validator

Once all old writers have stopped and documents meet the V2 contract:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenant_id",
        "display_name",
        "schema_version"
      ],
      properties: {
        tenant_id: {
          bsonType: "string"
        },
        display_name: {
          bsonType: "string",
          minLength: 1
        },
        schema_version: {
          bsonType: "int",
          minimum: 2
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Caution:** Documents whose version is stored as Int64 instead of Int32 can be rejected by `bsonType:"int"`. When applying rules, inspect actual BSON types and choose a consistent contract.

### 25.5. Validators Do Not Guarantee Every Business Rule

They do not automatically enforce cross-collection references, business uniqueness, or external payment invariants. Use indexes/transactions/services when needed.

### 25.6. Validation Bypass

Roles/operations with `bypassDocumentValidation` privilege can skip the validator under supported conditions. Do not treat validators as the sole security mechanism; use least privilege and auditing.

---

## 26. Index Migration: Create First, Drop Last

### 26.1. V1 Queries by the Old Field

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    full_name: 1
  },
  {
    name: "idx_customer_tenant_full_name"
  }
);
~~~

### 26.2. V2 Queries by the New Field

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    display_name: 1
  },
  {
    name: "idx_customer_tenant_display_name"
  }
);
~~~

During the mixed-version phase, **both** indexes may be needed.

### 26.3. Creating an Index Does Not Mean Data Is Backfilled

An index on `display_name` will not make queries on the new field find V1 documents that only have `full_name`. You must use fallback queries/aggregations or migrate the data.

### 26.4. When to Drop the Old Index?

Only when no queries/jobs need `full_name` anymore and telemetry confirms zero remaining dependencies. Dropping early can slow down or time out app V1.

### 26.5. Write Amplification

Maintaining two fields and two indexes temporarily increases storage/write cost. This is a cost of the compatibility window that must be capacity-planned.

### 26.6. Inspecting Query Plans

~~~javascript
db.customers.find({
  tenant_id: "tenant-a",
  display_name: "Nguyễn An"
}).explain("executionStats");
~~~

Review the plan/index, documents examined, and latency. Do not rely on a lab with a few documents to draw performance conclusions.

---

## 27. Unique Constraints When Changing Business Keys

V1 is unique on `tenant_id, email_lowercase`; V2 wants unique on `tenant_id, normalized_email`.

### 27.1. Risky Sequence

Creating the new unique index immediately before legacy data is normalized can fail due to duplicates or missing/null semantics.

### 27.2. Procedure

1. Define the normalization policy (casefold, Unicode, whitespace).
2. Backfill the new field and record conflicts.
3. Resolve duplicates according to business ownership.
4. Create an appropriate unique index, using a partial filter if business uniqueness applies only when the field has a valid value.
5. Switch writers/readers to the new key.
6. Test concurrent upserts; drop the old index only after the compatibility window.

### 27.3. Partial Unique Index

For example, enforce uniqueness only for documents that already have `normalized_email` as a string:

~~~javascript
db.customers.createIndex(
  {
    tenant_id: 1,
    normalized_email: 1
  },
  {
    name: "uq_tenant_normalized_email",
    unique: true,
    partialFilterExpression: {
      normalized_email: { $type: "string" }
    }
  }
);
~~~

This does **not** protect documents not yet backfilled; ensure the application does not create duplicates during the compatibility window.

### 27.4. A Unique Index Does Not Make Two Schemas Equivalent

If V1 upserts on `email_lowercase` while V2 upserts on `normalized_email`, both can create logically duplicate records if no unified identity/key policy exists.

---

## 28. Query Compatibility During Mixed Schema

### 28.1. Finding a Customer by Name

Single-field query:

~~~javascript
db.customers.find({
  display_name: "Nguyễn An"
});
~~~

misses V1 documents.

### 28.2. Transitional Query

~~~javascript
db.customers.find({
  tenant_id: "tenant-a",
  $or: [
    { display_name: "Nguyễn An" },
    { full_name: "Nguyễn An" }
  ]
});
~~~

However, if the two fields conflict, the query may match a document via the old field even though the new canonical name differs. Query matching and read precedence must follow the same contract.

### 28.3. Sorting and Pagination

If sorting by `display_name` when only half the documents are backfilled, results can differ from sorting by the resolved name. An aggregation computing `resolved_name` can consume CPU/sort memory and cannot directly benefit from a single-field index.

### 28.4. Text/Search Indexes

If the app uses MongoDB Search/Vector Search or a text index on name, index configuration must shift to the new field alongside the rollout. Data backfills do not automatically rebuild all derived indexes instantaneously in every deployment mode.

### 28.5. Projections

Old code using projections that return only `full_name` can accidentally hide the new field; new code must verify compatible projections before falling back.

---

## 29. Change Streams and CDC in Schema Evolution

Change Streams can observe inserts/updates, but they are not a migration engine that automatically guarantees consistency.

### 29.1. Optional Architecture

~~~text
V1/V2 writes to MongoDB
        |
        v
Change Stream consumer
        |
        v
Normalization / validation / version checks
        |
        v
Repair new field or materialized projection
        |
        v
Checkpoint + monitoring
~~~

### 29.2. Latency

Because the consumer processes events after the write, a V1 update to `full_name` before `display_name` is synced creates a window of divergent data. Readers must have a fallback/consistency policy for that window.

### 29.3. Duplicate/Retry

Change Stream resume does not turn business processing into exactly-once. A consumer can reprocess events after a crash; migration repair must be idempotent or use event/version deduplication.

### 29.4. Ordering

With multiple partitioned workers, events from the same entity can arrive out of order. Use source version/sequence and conditional writes, rather than relying on worker arrival time.

### 29.5. Delete/Pre-Image

Delete events do not include the full before-document by default. If you need the old field/tenant to update a projection or clean up, you may need pre-images with suitable configuration/retention, audit logs, or a contribution ledger.

### 29.6. Lost Resume History

If the consumer is down too long, the resume token may no longer be valid. Bootstrap/reconciliation is required instead of simply starting to watch from “now” and dropping past changes.

---

## 30. Backfill and Online Writes: The Lost Update Problem

Timeline:

~~~text
T1  Migration reads full_name="An"
T2  User updates full_name="An New"
T3  Migration writes display_name="An" from T1 data
T4  Reader V2 prefers display_name -> returns old name
~~~

### 30.1. Why Are Pipeline Update Scripts Advantageous?

Using an update pipeline:

~~~javascript
[
  {
    $set: {
      display_name: "$full_name"
    }
  }
]
~~~

the server evaluates `"$full_name"` from the document's value at update time, reducing the risk of using a stale client-read snapshot. Still, V1 can write after the backfill and create drift.

### 30.2. When to Use CAS?

If a worker fetches a snapshot and must compute data client-side, use a filter on `_id + expectedVersion` or the expected old field value:

~~~javascript
db.customers.updateOne(
  {
    _id: "CUS-101",
    full_name: "An",
    display_name: { $exists: false }
  },
  {
    $set: {
      display_name: "An",
      schema_version: 2
    }
  }
);
~~~

If the user has already changed `full_name`, the filter does not match; the worker must re-read/retry instead of overwriting.

### 30.3. Do Not Rely Solely on Timestamps

Two machines can have clock skew, event time can differ from commit order, and offline data can arrive late. Use monotonic versions/sequences or compare-and-swap when determining “latest.”

### 30.4. Multi-Collection Cases

Converting embedded structures into references or spanning two aggregate collections may require transactions or outbox + reconciliation. Single-document atomicity is not enough.

---

## 31. Pausable and Resumable Migration Workflow

A production job should track:

~~~javascript
{
  _id: "customer_v2_migration",
  migration_version: 2,
  state: "RUNNING",
  owner: "data-platform",
  current_tenant: "tenant-a",
  last_id: "CUS-30000",
  examined: NumberLong("30000"),
  modified: NumberLong("28100"),
  skipped: NumberLong("1900"),
  errors: NumberLong("0"),
  started_at: ISODate("2026-11-14T01:00:00Z"),
  last_checkpoint_at: ISODate("2026-11-14T02:10:00Z")
}
~~~

### 31.1. States

- `PLANNED`.
- `RUNNING`.
- `PAUSED`.
- `FAILED_NEEDS_REPAIR`.
- `BACKFILL_COMPLETE`.
- `RECONCILED`.
- `CONTRACT_READY`.
- `DONE`.

### 31.2. One Valid Owner per Migration Run

If two workers backfill the same bucket/tenant concurrently, leases/locks or versioned CAS are needed. With idempotent updates, overlapping runs may not corrupt data, but they add load and complicate tracking.

### 31.3. Rate Limiting

Tune batch size, concurrency, sleep, and `maxTimeMS`/budgets to cluster capacity; monitor replication lag, CPU/IO, and online API latency.

### 31.4. Stop or Skip on Error?

Never auto-skip every invalid document and report 100% migration. Record the ID, reason, count, and ticket; decide on manual repair or quarantine per business policy.

### 31.5. Backfill Completion Does Not Mean Contract Ready

Finishing the cursor scan only means the job scanned the collection; you must still verify data drift, old writers, search/index state, validators, and rollback requirements.

---

## 32. Measuring Completion and Inconsistency

### 32.1. Count Documents Missing the New Field

~~~javascript
db.customers.countDocuments({
  display_name: { $exists: false }
});
~~~

### 32.2. Count Documents Where Old Field Still Exists

~~~javascript
db.customers.countDocuments({
  full_name: { $exists: true }
});
~~~

During the compatibility window, this count may remain very large **and is completely expected**.

### 32.3. Count Documents Having Both Fields with Different Values

~~~javascript
db.customers.countDocuments({
  full_name: { $type: "string" },
  display_name: { $type: "string" },
  $expr: {
    $ne: ["$full_name", "$display_name"]
  }
});
~~~

### 32.4. Count Invalid Schema Markers

~~~javascript
db.customers.countDocuments({
  schema_version: { $gte: 2 },
  display_name: { $exists: false }
});
~~~

Having a V2 marker while missing a required field → data-quality violation.

### 32.5. Do Not Only Compare Counts

Two collections can have identical document counts while holding different data values. For money, identifiers, and permissions, use checksums/bucket-level reconciliation and business invariants.

### 32.6. Recommended Metrics

| Metric | Meaning |
|---|---|
| `legacy_documents_remaining` | Documents not yet in the new shape |
| `dual_field_mismatch_count` | Old/new field discrepancies |
| `migration_processed_total` | Records inspected |
| `migration_modified_total` | Records modified |
| `migration_failed_total` | Failed records |
| `migration_checkpoint_age_seconds` | Is the job stuck? |
| `old_writer_write_rate` | Are legacy writers still active? |
| `new_reader_fallback_rate` | Does V2 still rely on the old field? |
| `schema_validation_warn_total` | Violations |
| `legacy_query_rate` | Are legacy queries still running? |
| `replica_lag_seconds` | Migration impact on replicas |
| `app_p95_latency_ms` | End-user impact |

Metric names are instrumentation suggestions, not default MongoDB metrics.

---

## 33. Rollback: When Can You Revert to the Old App?

### 33.1. Code Rollback and Data Rollback Are Different

If V2 dual-writes both `full_name`/`display_name` and V1 still reads the old field, code rollback is possible during the compatibility window **if** V1 does not break the V2 schema and no incompatible enums/types have been introduced.

Once `full_name` is removed in the contract phase, rolling back to V1 can render the app unable to read customers.

### 33.2. Marking Rollback Boundaries

~~~text
EXPAND:
  V1 rollback supported if writer compatibility preserved

MIGRATE:
  V1 rollback still supported, pending final sync,
  but must check any V2-only persisted features

CUTOVER:
  V1 rollback maybe not supported by policy

CONTRACT:
  V1 rollback unsupported unless reintroduced old shape
~~~

This is a **plan to be confirmed**, not a universal default for every system.

### 33.3. Roll Forward May Be Better Than Reverse Migration

If V2 production hits a minor bug after contract, deploying a V2.1 fix may be safer than rolling back to V1 and trying to reconstruct the old schema.

### 33.4. Do Not Restore the Whole Cluster to Undo a Field Rename

Restoring an old snapshot can wipe out valid recent writes and affect other orders/payments. Account for RPO/RTO, scope, and business approval.

### 33.5. Keep an Audit Trail for Every Phase

Who toggled the feature flag, when did V1 writers stop, what were the backfill run IDs, source/target versions, and reconciliation results? Without these logs, choosing a rollback path is very difficult.

---

## 34. Releasing with Feature Flags

App V2 behavior can be split via flags:

| Flag | Purpose |
|---|---|
| `customer_dual_read_enabled` | Read both `full_name` and `display_name` |
| `customer_dual_write_enabled` | Write both fields |
| `customer_prefer_new_name` | Choose the new canonical field |
| `customer_new_field_required` | Disallow creating documents with only the old field |
| `customer_legacy_write_disabled` | Block old-only write sources if routing supports it |

### 34.1. Do Not Enable Flags Out of Order

Enabling `prefer_new_name` before final reconciliation can show users stale names. Enabling `new_field_required` while app V1 still writes can cause the validator to reject old requests.

### 34.2. Flags Must Have Ownership

Who turns them on? Based on which metrics? Is rolling back a flag safe after the old field has been dropped? Feature flags do not solve consistency on their own.

### 34.3. Do Not Keep Compatibility Code Indefinitely

It carries per-query overhead, extra indexes, harder-to-test code paths, and risk of field divergence. Set a target deadline for contract, but execute only after all criteria are met.

---

## 35. Online Migrations During Rolling Deployments

A rolling deployment unfolds over time:

~~~text
10:00 App V1 serves 100% traffic
10:05 App V2 canary 5%
10:15 App V2 50%, V1 50%
10:30 App V2 100% REST API
10:45 Background worker V1 still runs scheduled job
11:00 Worker V1 completely stopped
11:15 Final reconciliation begins
~~~

If you mark “V1 stopped” at 10:30, you miss the worker continuing to write until 11:00.

### 35.1. Deployment Inventory

Track:

- Pod/container image digests.
- JVM build versions.
- Worker deployments.
- CronJobs/schedulers.
- CI scripts.
- External clients.
- Database users with direct write privileges.
- Lagging event consumers.
- Offline clients/event replay.

### 35.2. Mixed Reads and Writes Must Be Tested

Run concurrent V1/V2 tests in staging:

~~~text
V1 read V1 doc
V1 read transitional doc
V1 update transitional doc
V2 read V1 doc
V2 read transitional doc
V2 update V1 doc
V2 update transitional doc
V2 replace partial doc (must be forbidden/protected)
~~~

### 35.3. Canaries Must Watch for Silent Errors

Do not monitor only HTTP 500s. Track missing-name record counts, fallback rates, mismatch counts, and search results.

---

## 36. Event-Driven Architecture and Schema Versioning

A V2 service may still need to emit V1-compatible events:

~~~json
{
  "event_type": "CustomerRenamed",
  "event_schema_version": 1,
  "customer_id": "CUS-101",
  "full_name": "Nguyễn An New"
}
~~~

V2 wants:

~~~json
{
  "event_type": "CustomerRenamed",
  "event_schema_version": 2,
  "customer_id": "CUS-101",
  "display_name": "Nguyễn An New"
}
~~~

### 36.1. Do Not Change Payloads and Expect Every Consumer to Understand Immediately

If the broker retains old events for days or consumers lag, V1 and V2 payloads coexist. New consumers must accept all versions within the retention/replay window.

### 36.2. Strategies

- Event V2 retains the legacy field temporarily.
- Producers emit events on separate versioned topics/event types.
- Consumer adapters map both into a canonical internal model.
- Schema registry/contract tests aligned with the event technology in use.
- Outbox stores the event schema version independently of the document schema.

### 36.3. Replaying Old Events

If the source is backfilled to V2 and a V1 event with the old field is replayed, consumers must not drop new-only fields or silently downgrade the document.

### 36.4. Ordering and Idempotency

Events with stable IDs and aggregate versions help handle duplicates/out-of-order delivery. Never assume “the last event to arrive” is the latest in business time.

---

## 37. Materialized Views, Caches, and Downstream Projections

Schema changes on `customers` can impact:

- Search indexes pulling `full_name`.
- Aggregated `customerProfiles` collections.
- Redis caches holding raw BSON/JSON.
- BI/warehouse extract queries.
- CSV exports.
- Change Stream projection workers.
- Audit/compliance reports.

### 37.1. Read Models Need Migration Too

If a projection stores `full_name`, a V2 app querying `display_name` may find no data; rebuild/recompute or dual representation is required.

### 37.2. Cache Invalidation

If cache keys/payloads lack a schema version, rollback/cutover can serve stale payloads even though MongoDB has been updated. Version cache namespaces or invalidate per migration phase.

### 37.3. Source Count = Projection Count Is Not Enough

A profile may exist in both collections while having a different `displayName`. Compare values, checksums, or sample per the business contract.

### 37.4. Search Index Lag

After changing indexed fields, Search/Vector Search may need rebuilding/syncing. API read readiness includes search behavior, not just MongoDB CRUD.

---

## 38. Data Migration and Multi-Tenant Isolation

A shared multi-tenant collection:

~~~javascript
{
  tenant_id: "tenant-a",
  full_name: "Nguyễn An"
}
~~~

### 38.1. Backfills Must Preserve Tenant

If a script only updates name fields within the same document, the tenant ID normally stays untouched; however, when splitting/merging collections or building new documents, preserve correct tenant ownership and prevent cross-tenant mixing.

### 38.2. Per-Tenant Canary

You can migrate a pilot tenant first to observe, though tenant skew can be huge. Pick representative cohorts covering volume, document shapes, and query patterns.

### 38.3. Authorization

Never take `tenant_id` from an arbitrary user request to trigger migrations. Allow only approved admin jobs, restricted credentials, auditing, and tenant allowlists.

### 38.4. Query Scope

If a new reader uses an `$or` fallback and misplaces the tenant filter in the wrong logical branch, it can accidentally perform cross-tenant reads. Always test authorization when changing query shapes.

---

## 39. Sharded Clusters and Schema Evolution

### 39.1. A Shard Key Is Not an Arbitrarily Renameable Field

If `tenant_id` is the shard key, renaming it to `tenantId` is not an ordinary field rename; it can affect query targeting, unique indexes, routing, and sharding metadata. Dedicated shard key/resharding procedures are required if it truly must change.

### 39.2. Batching by Shard/Tenant

Backfilling across shards can incur network/merge overhead and uneven load. Including the shard key in queries when appropriate scopes the work, but verify the actual shard key and routing.

### 39.3. Feature/Version Gates

Certain aggregation update operators, transaction behaviors, time-series formats, or indexes depend on MongoDB Server/FCV. Document schema version V2 does not imply the current server supports every migration pipeline.

### 39.4. Do Not Test Only on Standalone

If production is a sharded cluster with Change Streams, transactions, and retryable writes, a local standalone staging environment will not expose all operational risks.

---

## 40. When to Use a New Collection Instead of the Same Collection?

Some changes do not fit dual fields within the same document:

- Splitting a giant document into multiple documents.
- Changing tenant partitioning/ownership.
- Rewriting the model with a new primary identifier.
- Separating sensitive data into a collection with different permissions.
- Building precomputed read models.
- Moving a large embedded array into its own line-items collection.

### 40.1. Migrating to a New Collection

~~~text
customers_v1 (source)
       |
       +-- backfill -> customers_v2
       |
       +-- CDC/dual-write during compatibility window
                           |
                           v
                    Validation/cutover
                           |
                           v
                       V2 readers
~~~

### 40.2. Questions That Must Be Answered

- Which collection is the canonical source?
- Can both receive concurrent writes?
- Are stable business IDs preserved?
- How long will backfill/copy take for large data?
- Do indexes/unique constraints work on the target?
- Are deletes/restores synchronized?
- When do query migration and routing happen?
- How does rollback differ before and after cutover?

### 40.3. Dual-Writing Two Collections Is Not Atomic by Default

Two separate writes can crash mid-way. Use transactions where appropriate or outbox/CDC + reconciliation; do not assume “both are in the same database” makes them atomic.

---

## 41. How Migrations Affect Backup and Restore

### 41.1. Old Snapshots Have the Old Schema

If restoring data from a pre-migration snapshot, App V2 must still be able to read the V1 format or have a re-backfill runbook.

### 41.2. New Snapshots Have the New Schema

If rolling back to App V1 after contract, V1 may be unable to read V2 snapshot data. Backups do not solve compatibility unless a data downgrade procedure exists.

### 41.3. RPO/RTO and Business Approval

Restoring an entire collection to pre-migration state can lose valid subsequent writes. Never use a full data rollback as an “undo schema” button without accounting for data loss and consistency across related collections.

### 41.4. Backup Keys and Metadata

When a migration alters encryption or unique indexes, restores require matching keys/index definitions. Test restores both before and after cutover.

### 41.5. Restore Drill

In staging:

1. Restore a V1 backup into an isolated target.
2. Run App V2 reader tests.
3. Run backfill resume.
4. Run validator/index migration.
5. Test app rollback while the legacy field still exists.
6. Verify business invariants.

---

## 42. Production Rollout Runbook

### Step 1 — Define the Contract

Specify V1/V2 BSON examples, required/optional fields, types, enum values, null/missing semantics, and owners.

### Step 2 — Build Inventory

List all readers/writers/indexes/jobs/consumers/reports, including operational scripts and offline clients.

### Step 3 — Risk Analysis

Identify full-document replacements, unique indexes, hot documents, shard keys, validators, security scope, and the rollback window.

### Step 4 — Baseline

Collect counts/invalid documents/mismatch rates/latency/index stats, backup state, replication lag, and current schema distribution.

### Step 5 — Safety Release

Eliminate dangerous V1 writes such as full replacements that drop unknown fields if they would break the new schema.

### Step 6 — Expand

Deploy app V2 with dual-read and compatible writes, without removing old fields or emitting unsupported new enums.

### Step 7 — Canary

Run integration tests and inspect fallback/mismatch rates, throughput, and security while both app versions coexist.

### Step 8 — Backfill

Run migration batches with checkpoints, rate limits, idempotent filters, and error quarantine.

### Step 9 — Drain Old Writers

Shut down all jobs/pods/clients still writing old-only; wait for in-flight writes to finish and confirm via metrics/audits.

### Step 10 — Final Reconciliation

Fix all drift and verify unmigratable records, counts, and business invariants.

### Step 11 — Switch Read Canonical

Switch readers to use the new field as primary while temporarily keeping dual-writes to protect rollback if policy requires.

### Step 12 — Validator/Index Migration

Enforce the V2 contract once data is ready; check duplicate/unique constraints, query plans, and downstream projections.

### Step 13 — Contract

After the rollback window and business sign-off, remove legacy fields/code/indexes in batches without losing new values.

### Step 14 — Postmortem/Close

Archive run IDs, checksums/metrics, incidents, performance deltas, and guidance so future upgrades can read remaining documents.

---

## 43. Test Matrix for V1/V2

### 43.1. Read Compatibility

| Test | Expected Result |
|---|---|
| V1 reads V1 document | OK |
| V2 reads V1 document | OK via fallback |
| V1 reads transitional document | OK |
| V2 reads transitional document | OK, correct precedence |
| V2 reads new-only document | OK after cutover |
| V1 reads new-only document | Not allowed during rollback window |
| V2 reads null/missing field | Follows contract |
| V2 reads wrong BSON type | Reports data-quality issue, does not silently fix |

### 43.2. Write Compatibility

| Test | Expected Result |
|---|---|
| V2 creates new customer in mixed window | Both fields |
| V2 renames in mixed window | Both fields atomically equal |
| V1 renames after backfill | V2 reader still returns correct name per phase |
| V1 full replace drops unknown field | Must be blocked or protected |
| V2 stale CAS update | Detects conflict |
| V2 updates old-only record | Does not lose old field |
| Backfill re-run | Does not overwrite valid new value |
| Backfill crash and resume | No lost/duplicated data |
| Validator set to warn | Logs warnings and does not block designed flows |
| Validator set to error | Blocks non-compliant writes |

### 43.3. End-to-End

- Querying and sorting by name.
- Search indexes.
- Unique keys/upserts.
- V1/V2 events.
- Offline clients.
- Transaction/order/payment invariants.
- Permissions/tenant isolation.
- Backup/restore at both stages.
- Performance under concurrent traffic.

### 43.4. Failure Injection

Simulate worker crashes mid-batch, post-update network timeouts, duplicate events, lingering old writers, and code rollbacks in the mixed phase to catch bugs before production.

---

## 44. Clarifying Rollback with a Timeline Example

~~~text
Day 1:
  V1 reads/writes full_name
  V2 not yet released

Day 2:
  V1 safety patch stops full replace
  V2 dual-read; V2 dual-write

Day 3:
  Backfill display_name for 80% of records
  V1 and V2 both writing

Day 4:
  V1 REST stopped, V1 scheduled worker still running
  prefer-new not enabled

Day 5:
  Old worker stopped; final reconciliation complete
  V2 prefers display_name

Day 6:
  Keep full_name for rollback window
  Monitoring discrepancy=0

Day 14:
  Rollback window ends
  Contract: drop full_name, old index, old fallback
~~~

### 44.1. If Rolling Back on Day 3

Reverting to V1 is possible **if** the new app has not written data V1 cannot understand and the old field remains intact. Afterward, stop/audit workers that generated V2 data rather than merely swapping container images.

### 44.2. If Rolling Back on Day 14

V1 is no longer guaranteed to work because the old field has been deleted. You must roll forward or execute a specially designed reverse migration; do not promise a quick rollback.

### 44.3. Do Not Use Calendar Days as the Sole Criterion

The timeline is illustrative only. Real gates must rely on telemetry, data quality, consumer inventory, and business approval.

---

## 45. Hands-On Exercises

### Exercise 1 — Schema Identification

Given three documents: one with `full_name`, one with `display_name`, and one with both. Determine what V1/V2 readers return in each phase.

### Exercise 2 — Compatibility Matrix

Create a 2×2 table of App V1/V2 × Document V1/V2; mark whether reads, writes, and full replacements are safe.

### Exercise 3 — Dual-Read

Write a Java method to extract the customer name from both fields. Specify precedence while old writers are active and after final reconciliation.

### Exercise 4 — Dual-Write

Use `MongoTemplate.updateFirst` to set `full_name` and `display_name` in a single operation, filtered by tenant+ID.

### Exercise 5 — Null/Missing

Create documents with missing, null, empty, and string values for `display_name`. Compare `$exists`, `$type`, and `$ifNull`.

### Exercise 6 — Schema Version

Define semantics for `schema_version`=1,2,3 during the rename process; explain why it differs from `@Version`.

### Exercise 7 — Backfill

Create 10,000 V1 documents; use a batched update pipeline to copy `full_name` to `display_name`.

### Exercise 8 — Idempotency

Run the backfill twice and confirm it does not overwrite valid newly written values when filtering on missing `display_name`.

### Exercise 9 — Race Condition

A V1 worker updates `full_name` after backfill. Demonstrate why a V2 reader preferring `display_name` can return stale data.

### Exercise 10 — CAS

Write an update filter using expected `full_name` and missing new field; prove that if the name changes concurrently, the update does not match.

### Exercise 11 — Final Sync

Assume the old field is canonical during the mixed window. Write a query to find discrepancies and a plan to fix them after V1 writers stop.

### Exercise 12 — Full Replace

Simulate app V1 reading/replacing a document that has `display_name`; observe the new field disappearing. Convert it to a field-level `$set`.

### Exercise 13 — Validator

Create a `warn` validator for old/new documents; after backfill, enforce the V2 contract with `$jsonSchema`.

### Exercise 14 — Index Migration

Create indexes on `full_name` and `display_name`. Test query plans before/after backfill; determine when to drop the legacy index.

### Exercise 15 — Unique Constraint

Change email normalization and detect duplicate keys upon normalization; propose a partial unique index and repair workflow.

### Exercise 16 — Enum Version

Add status `PARTIALLY_REFUNDED`. Design a reader-first, writer-later rollout so V1 does not fail.

### Exercise 17 — Numeric Types

Convert `amount_string` to Int64 `amount_minor`. Handle invalid strings/overflow and test precision.

### Exercise 18 — Nested Document

Change `shipping_address:string` to `shipping_address_v2:object`; identify records that cannot be parsed automatically.

### Exercise 19 — Embedded → Reference

Split addresses into a separate collection with stable IDs. Design dual-read, write ownership, and reconciliation.

### Exercise 20 — CDC

Use Change Streams/outbox to sync fields; describe retries, ordering, lag, and bootstrapping after history loss.

### Exercise 21 — Sharding

If `tenant_id` is the shard key, explain why renaming it to `tenantId` cannot be treated as an ordinary field migration.

### Exercise 22 — Multi-Tenant

Migrate by tenant cohorts. Design tenant isolation across backfill, API queries, and monitoring.

### Exercise 23 — Rollback

V2 has already deleted `full_name`. Analyze why rolling back to App V1 is unsafe and choose between roll-forward and reverse migration.

### Exercise 24 — Contract Tests

Write tests for V1/V2 applications reading/writing V1/transitional documents, plus raw BSON field assertions.

### Exercise 25 — Restore Drill

Restore an old snapshot containing the V1 schema and run V2. Prove the app can read it and the backfill can resume.

### Exercise 26 — Observability

Design a dashboard showing remaining V1 documents, fallback rate, mismatch count, old writer rate, and replication lag.

### Exercise 27 — Failed Migration Job

Simulate a crash after writing a batch but before saving the checkpoint. Explain why idempotency is required.

### Exercise 28 — Partial Backfill

A tenant is only 40% migrated while V2 searches on `display_name`. Analyze missed results and design query fallback or feature gating.

### Exercise 29 — Strict Schema Validator

A document has `schema_version:NumberLong("2")` while the validator requires BSON Int32. Analyze the failure and how to unify types.

### Exercise 30 — Complete Design

Plan an expand–migrate–contract rollout for a system with a Java API, scheduled worker, Kafka consumer, Atlas Search, and BI reports. Specify test gates, rollback boundaries, and business sign-off.

---

## 46. Review Questions

1. Why does MongoDB's schema flexibility not mean old and new applications are automatically compatible?
2. How does a document schema version differ from an application version?
3. How does MongoDB's FCV differ from `schema_version`?
4. Must API version and event schema version equal the document version?
5. What is backward compatibility in the data layer?
6. What is forward compatibility in the data layer?
7. Why is write compatibility just as important as read compatibility?
8. Which writers besides the REST API are involved in a mixed-version deployment?
9. Should `schema_version` be added to every collection?
10. Why does a schema marker not replace schema validation?
11. How does an optimistic version differ from a schema version?
12. Can you migrate a BSON field simply by changing `@Field`?
13. What phases make up expand–migrate–contract?
14. In which phase must rollback be prepared before modifying data?
15. Why not run `$rename` immediately while app V1 is still running?
16. How do dual-read and dual-write differ?
17. Does dual-write automatically synchronize V1 writers?
18. Why might reader V2 need to prefer the old field during the mixed window?
19. When is it safe to switch readers to prefer the new field?
20. Why must final reconciliation wait for old writers to stop?
21. How should `missing` and `null` be handled differently?
22. What risks arise from mixing BSON numbers and strings in the same field?
23. How can a new enum value break V1?
24. Why does nested object migration require a data-quality policy?
25. How does V1 full-document replacement cause V2 fields to be lost?
26. Does `@Version` protect you if an old raw writer does not increment the version?
27. How does backfilling with an aggregation update differ from classic `$set`?
28. Why do batch migrations need checkpoints?
29. Why is reconciliation still needed after scanning all `_id` values?
30. How do conditional updates with expected field values prevent races?
31. When should you choose validator `warn`?
32. When should you switch to `validationAction:"error"`?
33. How does `validationLevel:"moderate"` differ from `strict`?
34. Do MongoDB validators automatically transform old documents?
35. Why does creating a new index not mean the backfill is finished?
36. Which conditions allow dropping a legacy index?
37. Does a partial unique index protect records outside its filter?
38. Does a Change Stream automatically guarantee exactly-once processing?
39. How should old events be handled when replayed onto V2 data?
40. Why must cached/derived projections participate in schema migrations?
41. How does a shard key rename differ from an ordinary field rename?
42. Why do transactions not automatically solve external broker consistency?
43. How does code rollback differ from data rollback?
44. How does the contract phase make V1 rollback difficult?
45. Which metrics prove there is no remaining dependency on the old schema?
46. Why should duration alone not be used as the contract gate?
47. Which app/document version pairs must integration tests cover?
48. Which invalid documents should be quarantined instead of auto-converted?
49. How should backup snapshots and restore drills be handled during migration?
50. Can a migration that is complete by count yet still shows a high fallback rate be considered done?

---

## 47. Summary

**Schema evolution in MongoDB is a compatibility problem between producers, consumers, and existing data over time.** The database does not force every document to have the same shape, yet application code, indexes, validators, and external systems still depend on a data contract.

Key principles:

1. **Separate version types**: application, document, event, API, MongoDB Server, and FCV are not the same thing.
2. **Build a read/write matrix** between App V1/V2 and Document V1/V2; check full replacements as well.
3. **Expand → migrate → contract** instead of changing fields, data, indexes, and validators in a single release.
4. **Dual-read is not enough** if old writers keep updating the old field after the new field is backfilled; canonical precedence and final reconciliation are required.
5. **Single-document atomic dual-writes** reduce divergence from V2 writes, but do not control V1 old-only writes.
6. **Backfill with checkpoints, idempotency, rate limits, conflict handling, and repair paths**; finishing a scan is not enough.
7. **Schema version is not an optimistic lock version** and does not replace validators.
8. **Indexes, validators, Search, caches, reports, event consumers, and tenant security** are all part of the migration.
9. **Rollback boundaries must be designed before contract**, because V2 data may no longer be readable by V1.
10. **Migration completion requires evidence**: no old writers, no unresolved mismatches, low/zero fallback per policy, intact business invariants, and a verified restore path.

When designing even a small change like `full_name → display_name`, the question is not merely “Which field name does the new Java class use?” but: **While both old and new apps are running, who is the authoritative write source, which readers still rely on the old schema, how can data be recovered, and what conditions permit dropping the legacy field without losing rollback capability?**

## References

- [MongoDB Manual — Data Model Design](https://www.mongodb.com/docs/manual/data-modeling/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [MongoDB Manual — Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB Manual — Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — $rename](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — $ifNull](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifNull/)
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)
- [MongoDB Java Sync Driver — Read Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/)
