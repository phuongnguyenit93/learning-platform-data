# Adding, Renaming, and Dropping Fields via a Multi-Phase Deployment Process in MongoDB

In MongoDB, documents are not required to share the same set of fields. A collection can simultaneously hold legacy documents with the **name** field and newer documents with the **displayName** field. This flexibility helps systems evolve rapidly, yet also introduces an operational risk: **if an application is running across multiple versions and the schema changes too early, part of the system may misread data, write incomplete fields, lose data, or become unable to roll back**.

For example, a development team wants to make three changes to the **customers** collection:

- **Add** the **preferredLocale** field to store the display language.
- **Rename** the **name** field to **displayName**.
- **Drop** the **legacyTag** field that is no longer used.

A migration like:

~~~javascript
db.customers.updateMany({}, { $rename: { name: "displayName" } });
db.customers.updateMany({}, { $set: { preferredLocale: "vi-VN" } });
db.customers.updateMany({}, { $unset: { legacyTag: "" } });
~~~

may work in a simple environment, but **it is not safe to run directly in production by default** when legacy services still query by **name**, old writers keep writing **name**, multiple workers process asynchronously, or validators/indexes rely on the old schema.

Instead of “changing fields all at once,” the standard approach is **expand → migrate → contract**:

~~~text
Old schema
   |
   v
EXPAND
 App reads old + new
 Transitional writer can write both fields
   |
   v
MIGRATE
 Backfill historical data
 Control old writers, reconcile data
   |
   v
SWITCH
 App uses new field as primary source
 Monitor and maintain appropriate rollback window
   |
   v
CONTRACT
 Stop depending on old field
 Drop old field/index/schema validation
   |
   v
New schema
~~~

This lesson walks through how to design and operate each phase, including **mongosh**, **MongoDB Java Driver**, and **Spring Data MongoDB** examples, testing checklists, monitoring, rollback, and scenario exercises.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between **logical schema changes in the application** and **physical data changes in MongoDB**.
2. Design a **compatibility contract** across old readers, new readers, old writers, and new writers.
3. Perform **add field** using a default policy, optional reads, and conditional backfills.
4. Perform **rename field** through a dual-read/dual-write phase rather than running **$rename** too early.
5. **Drop fields** only after proving zero remaining dependencies and completing the appropriate rollback window.
6. Write **idempotent**, throttled batch migrations that do not overwrite newer updates.
7. Use **$set**, **$unset**, **$rename**, aggregation pipeline updates, and **bulkWrite** with accurate semantics.
8. Adjust indexes, validators, unique constraints, and schema serialization in the right order.
9. Coordinate with **Java/Spring Data MongoDB**, service versions, CDC/change streams, and background jobs.
10. Test and operate schema evolution during multi-replica deployments, rollbacks, or traffic shifts.

**Scope:** MongoDB document collections and common APIs in Java/Spring Data. Examples use a dedicated test database and must not be applied automatically to production. Specific features (such as aggregation pipeline updates, change streams, or validator settings) must be verified against the actual MongoDB server and driver versions.

## 2. Why Does MongoDB Still Need Schema Migrations?

MongoDB does not enforce that every document in a collection has the same structure. For example:

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  name: "An",
  legacyTag: "old-import"
}
~~~

and:

~~~javascript
{
  _id: "C-102",
  tenantId: "T-A",
  displayName: "Bình",
  preferredLocale: "vi-VN"
}
~~~

can both exist in a collection without a strict validator. However:

- A Java class declaring only **name** will read **displayName** as null.
- A report grouping by **name** will miss documents with the renamed field.
- A unique index or filter can behave differently when a field is missing.
- A REST API may need to return the old field to old clients and the new field to new clients.
- An old background worker might **write name back** after a batch migration switched to displayName.
- A schema validator might reject writes from old code.

**A schema is not just a structure inside the database.** It is also a contract across all involved readers, writers, indexes, validators, events, API responses, and jobs.

### 2.1. Physical Schema and Logical Schema

The **physical schema** consists of the BSON fields stored in documents:

~~~text
customer.name
customer.displayName
customer.preferredLocale
customer.legacyTag
~~~

The **logical schema** is how the application interprets that information:

~~~text
What is the customer's official display name?
What does the default language mean?
Who is allowed to change the name?
When name and displayName differ, which one wins?
~~~

A migration can be **syntactically valid** yet violate business logic if this interpretation is undefined.

### 2.2. Four Actors to Consider

| Component | Example | Risk if Field Changes Abruptly |
|---|---|---|
| Old reader | API version A reading name | Returns null once only displayName remains |
| New reader | API version B reading displayName | Misses un-backfilled documents |
| Old writer | Consumer version A updating name | Recreates old field or leaves displayName stale |
| New writer | Service version B writing displayName | Old reader misses new updates |

During a rolling deployment, **all four actors can coexist** for some time. Never assume that deploying a new version means all old processes disappear immediately.

## 3. Running Case Study

The **app_lab.customers** collection contains:

~~~javascript
use app_lab

db.customers.insertMany([
  {
    _id: "C-101",
    tenantId: "T-A",
    name: "An",
    legacyTag: "import-2024",
    updatedAt: ISODate("2026-10-01T00:00:00Z")
  },
  {
    _id: "C-102",
    tenantId: "T-A",
    name: "Bình",
    legacyTag: "import-2024",
    updatedAt: ISODate("2026-10-02T00:00:00Z")
  },
  {
    _id: "C-103",
    tenantId: "T-B",
    name: "Chi",
    legacyTag: "import-2025",
    updatedAt: ISODate("2026-10-03T00:00:00Z")
  }
]);
~~~

This is **synthetic** data containing no real customer records. Run it only once on a clean test collection; fixed **_id** values mean re-running insertMany will hit duplicate key errors.

### 3.1. End Goal

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  displayName: "An",
  preferredLocale: "vi-VN",
  updatedAt: ISODate("2026-10-01T00:00:00Z")
}
~~~

Desired outcome:

- **displayName** completely replaces **name**.
- **preferredLocale** has an explicit default policy, e.g., **vi-VN** when business rules allow.
- **legacyTag** no longer exists in new or legacy documents.
- No name updates occurring **during the migration** are lost.
- Services continue operating during rolling deployments with a step-by-step rollback plan.

### 3.2. Assumptions to Make Explicit

To keep the example clear:

- **name** is a String representing the display name.
- The new **displayName** is also a String with **the same business meaning** as name during transition.
- **preferredLocale** is permitted by lab policy to default to **vi-VN**; production must determine appropriate defaults per tenant/user.
- **legacyTag** is no longer needed by business logic, yet is dropped only after completing dependency inventory and satisfying retention policies.
- Multiple API instances and background consumers exist, so **old writers may exist** during rolling deployment.

Do not turn lab assumptions into universal rules: **a rename does not always mean the value semantics stay identical**. If the new field changes meaning or units (e.g., pre-tax price to post-tax price), a dedicated transformation migration is required.

## 4. Expand – Migrate – Contract

Each phase has a goal and completion criteria.

| Phase | Database May Contain | Reader | Writer | Goal |
|---|---|---|---|---|
| Before change | name, legacyTag | name | name | Baseline |
| Expand 1 | name, displayName?, preferredLocale? | name-first, fallback new | old or dual-write | Preserve compatibility with old deployment |
| Expand 2 | name, displayName, preferredLocale? | supports both | all writers dual-writing | Eliminate old-only writers |
| Migrate | mixed data, converging to full new fields | still compatible | dual-write | Backfill and reconcile |
| Switch | both fields, values synced | displayName-first, fallback name | dual-write | Switch primary read source |
| Contract prep | name still present alongside new fields | new-only | new-only | Remove old dependencies |
| Contract data | new fields only | new-only | new-only | Drop name/legacyTag and old indexes |

The **?** mark means the field may **not yet exist**. During mixed-schema phases, the application must handle both states.

### 4.1. Why Separate Expand and Switch?

While an old writer is still active:

~~~text
T0: name="An", displayName="An"
T1: old writer updates name="An New"
T2: displayName is still "An" (stale)
~~~

If the new reader **prefers displayName too early**, it reads a stale value. While old-only writers still exist, you may need to temporarily treat **name as the primary source** or use a synchronization mechanism with its own guarantees. Only after all old-only writers are drained and reconciliation completes should you switch to **displayName-first**.

### 4.2. Backfill Is Not a Single Button

Backfilling millions of documents can take a long time, and meanwhile:

- Users update their profiles.
- The app still creates new documents.
- Consumers process delayed messages.
- Scheduled jobs execute.
- Replicas run different application versions.

Therefore, migrations require **idempotency, write-time update conditions, checkpoints, and resumability**. Never scan a list of IDs and blindly overwrite documents with stale snapshot data.

### 4.3. Contract Is a Compatibility-Breaking Step

Removing old fields, stopping dual-writes, or tightening validators to **require displayName** can make rolling back to the old application version **unsafe**. These steps therefore require gates, observation windows, and dedicated recovery plans.

## 5. Preparation Step: Inventory Every Field Read and Write Location

Before running **$set**, **$rename**, or **$unset**, list all dependencies:

| Component Group | Questions to Verify |
|---|---|
| REST/GraphQL APIs | Which request/response DTOs still use name? |
| Java/Spring Data entities | Which @Field, constructors, or mappers point to name? |
| Batch jobs | Which jobs read/write/overwrite full documents? |
| Consumers | Do consumers expect the old or new message schema? |
| Aggregation/reports | Are any grouping/projecting/sorting on name? |
| MongoDB indexes | Which regular/unique/partial/TTL indexes are involved? |
| Validators | Do $jsonSchema required/properties still reference old fields? |
| CDC/change streams | Do downstreams consume the old change payload? |
| Exports/ETL | Do data warehouses/search indexes map name? |
| Search/filters | Does the UI still search, sort, or collate on name? |
| Permissions | Do field-level policies still use old field names? |
| Backup/restore | Does rollback require keeping the old values? |

**All writers** include services, cron jobs, ad-hoc scripts, data repair tools, and integration adapters. If a monthly end-of-month script still writes **name**, a migration completed mid-month can be broken on its next run.

### 5.1. Build a Version Compatibility Table

| Component | V1 (old) | V2 (transitional) | V3 (final) |
|---|---|---|---|
| Reader | name-only | reads name and displayName | displayName-only |
| Writer | writes name | dual-writes name/displayName | writes displayName |
| Locale | unaware of preferredLocale | falls back and writes new field | requires preferredLocale |
| legacyTag | may read | removes dependency | no longer used |
| Rollback | V1 | V1 still needs name | V1 unsafe after contract |

Version labels are **deployment plan milestones**, not necessarily identical to codebase semantic versions.

### 5.2. Measure the Baseline Before Migration

~~~javascript
db.customers.countDocuments({ name: { $exists: true } });
db.customers.countDocuments({ displayName: { $exists: true } });
db.customers.countDocuments({ preferredLocale: { $exists: true } });
db.customers.countDocuments({ legacyTag: { $exists: true } });
~~~

**countDocuments** calls can be expensive on large collections, especially with **$exists** and unsuited indexes. In production, limit frequency, inspect query plans, or use controlled monitoring/counters.

Counting **existing** fields differs from counting fields with **valid values**. For instance, **displayName: null** still satisfies **$exists: true**.

### 5.3. Detect Anomalous Data

~~~javascript
db.customers.find(
  {
    name: {
      $exists: true,
      $not: { $type: "string" }
    }
  },
  { _id: 1, name: 1 }
).limit(20);
~~~

If null/Number/array values exist instead of Strings, do not blindly copy them to displayName. Establish a data-cleansing policy and record unconvertible records.

### 5.4. Are Defaults Permitted?

A value like **preferredLocale: "vi-VN"** is a business decision, not something MongoDB chooses on its own. Defaults may need to vary by tenant, account, user preference, or an UNKNOWN value.

A migration must not assign **vi-VN** to everyone if doing so breaks user experience or storage policies.

## 6. Adding a New Field: Compatibility from Reader to Writer

Adding a field is typically less risky than renaming or dropping, yet not completely harmless.

### 6.1. Phase A — Reader Accepts Missing Field

Application V2 should implement a fallback policy:

~~~text
If preferredLocale is valid -> use it.
If missing -> apply business-approved default.
If wrong data type -> record data error, do not silently assume.
~~~

Java example:

~~~java
import org.bson.Document;

public final class CustomerLocalePolicy {
    private CustomerLocalePolicy() {}

    public static String resolveLocale(
            Document customer,
            String approvedDefaultLocale) {
        Object raw = customer.get("preferredLocale");
        if (raw == null) {
            return approvedDefaultLocale;
        }
        if (raw instanceof String value && !value.isBlank()) {
            return value;
        }
        throw new IllegalStateException(
                "Invalid preferredLocale BSON value");
    }
}
~~~

This example treats **missing/null** on the same default branch. If null carries a distinct meaning from missing, check **containsKey** or query separately.

### 6.2. Phase B — All New Writes Include the New Field

~~~javascript
db.customers.insertOne({
  _id: "C-104",
  tenantId: "T-A",
  name: "Dung",
  displayName: "Dung",
  preferredLocale: "vi-VN"
});
~~~

Both **name** and **displayName** are still written to maintain compatibility with old readers.

### 6.3. Phase C — Backfill Missing Fields

If **vi-VN** is business-approved:

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $exists: false } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

The **$exists: false** filter protects users who already selected their preferredLocale from being overwritten. Never run:

~~~javascript
// Dangerous: overwrites every user's choice.
db.customers.updateMany(
  {},
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

### 6.4. Missing and Null Are Different

~~~javascript
{ _id: "C-201", preferredLocale: null }
{ _id: "C-202" }
~~~

**$exists: false** only matches documents lacking the field. If business treats null as unassigned, run a separate step:

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $type: "null" } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

Do not conflate null and missing if **null** is intentional, such as a user explicitly declining to select a language.

### 6.5. When to Require the New Field?

Only enable a validator with **required: ["preferredLocale"]** after:

1. All writers populate the new field.
2. Backfill is finished or a policy covers legacy documents.
3. Replacement/upsert paths have been checked.
4. The validator has been tested against representative data.
5. A rollback plan exists if writes get rejected.

Requiring the field too early can cause old writers or replaceOne calls to be rejected.

## 7. Renaming a Field: Why Not Do It in One Command Immediately?

MongoDB supports:

~~~javascript
db.customers.updateMany(
  {},
  { $rename: { name: "displayName" } }
);
~~~

However, during a rolling deployment:

~~~text
T0: Document has name
T1: MongoDB $rename name -> displayName
T2: Old API GET only reads name -> null
T3: Old worker writes new name into document
T4: New API GET only reads displayName -> stale value
~~~

**A successful $rename does not prove the system migrated safely.** A lower-risk approach is to copy to the new field, operate compatibly, and drop the old field last.

### 7.1. Does the Rename Change Value Semantics?

If only **name** changes to **displayName** with unchanged semantics, backfill can copy the String verbatim.

If changing:

~~~text
old field: amountCents
new field: amount
~~~

you must know whether **amount** stores cents or major currency units. If units change, the migration needs numeric conversion and precision/overflow testing, not just a rename.

### 7.2. Canonical Source Rules Across Phases

While old-only writers remain active:

~~~text
Canonical value = name
displayName is the transitional copy
~~~

Once sure all old-only writers are gone and data is reconciled:

~~~text
Canonical value = displayName
name is retained temporarily for rollback
~~~

Never let readers pick arbitrarily when the two values differ. Each phase needs an explicit **canonical source rule**.

## 8. Dual-Read: Reading Both Schemas

A reader can apply phase-dependent policies:

~~~java
import org.bson.Document;

public final class CustomerNameReader {
    private CustomerNameReader() {}

    public static String beforeCutover(Document customer) {
        String oldName = customer.getString("name");
        if (oldName != null && !oldName.isBlank()) {
            return oldName;
        }
        return customer.getString("displayName");
    }

    public static String afterCutover(Document customer) {
        String newName = customer.getString("displayName");
        if (newName != null && !newName.isBlank()) {
            return newName;
        }
        return customer.getString("name");
    }
}
~~~

**The two methods differ in precedence.** Never use `afterCutover` while old-only writers remain active without a guaranteed sync mechanism.

### 8.1. Fallbacks Must Emit Telemetry

An indefinite fallback can mask unmigrated documents and drift between fields. Track **PII-free** counters:

~~~text
customer_name_legacy_fallback_total
customer_name_conflicting_values_total
customer_name_missing_both_total
~~~

Tag by application version and appropriate scope; avoid customer ID/email labels that blow up metric cardinality and leak data.

### 8.2. Database Schema and API Contract Are Separate Layers

While the database holds both name and displayName, the API can return:

~~~javascript
{
  customerId: "C-101",
  displayName: "An"
}
~~~

or support both API property names during a deprecation period. Never expose raw BSON Documents over REST just for compatibility. If external clients still use the **name** property, version/deprecate the **API contract** independently from the internal migration.

### 8.3. Querying Mixed Schemas

During the dual-field search phase:

~~~javascript
db.customers.find({
  tenantId: "T-A",
  $or: [
    { name: "An" },
    { displayName: "An" }
  ]
});
~~~

This query avoids missing records, yet can also match **drifted** documents (where name differs from displayName). It does not distinguish which name is currently canonical; on large datasets, plan indexes per branch or a controlled search cutover phase.

### 8.4. Projections to Avoid Missing Data

In document-reading queries, include both fields until rollback/fallbacks are no longer needed:

~~~javascript
db.customers.find(
  { tenantId: "T-A" },
  {
    _id: 1,
    tenantId: 1,
    name: 1,
    displayName: 1,
    preferredLocale: 1
  }
);
~~~

If a projection fetches only displayName while code attempts to fall back to name, the fallback **will never trigger** even when name exists in the database.

## 9. Dual-Write: Writing Both Fields in One Operation

When the new service writes a name update, it can execute:

~~~javascript
db.customers.updateOne(
  { _id: "C-101", tenantId: "T-A" },
  {
    $set: {
      name: "An New",
      displayName: "An New",
      updatedAt: new Date()
    }
  }
);
~~~

Within **a single document**, `updateOne` with one update operator updates both fields **atomically** under MongoDB single-document atomicity. Readers will never observe a half-applied state from **that update command**.

### 9.1. Do Not Split Into Two `updateOne` Calls When Avoidable

Avoid:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { name: "An New" } }
);

db.customers.updateOne(
  { _id: "C-101" },
  { $set: { displayName: "An New" } }
);
~~~

Between the two commands, the service could crash, the network could fail, or a reader could see out-of-sync data. Writing both fields in **a single updateOne** on the same document is simpler. This does **not** automatically make updates across multiple documents a transaction.

### 9.2. Old Writers Remain a Risk

New writers dual-writing do not stop old writers from writing **name** alone:

~~~text
New writer: set name=A, displayName=A
Old writer: set name=B
Result: name=B, displayName=A
~~~

Thus before cutover, prove **no old-only writers remain** or enforce a reliable sync/write-block mechanism. Do not rely solely on a one-off backfill.

### 9.3. When Rollback Windows Are Extended

If operations want V1 rollback capability for several weeks, you may need to **maintain dual-writes** longer. That incurs:

- Extra storage and write overhead.
- Periodic reconciliation.
- Detection of old-only writes.
- Holding off on dropping the name field.

Alternatively, pick a cutoff date to end V1 rollback once V2/V3 stabilize. That is a product/operational decision, not purely technical.

## 10. Preventing Lost Updates with Version Conditions

When users update the same profile concurrently, use a version or suitable concurrency control.

Document:

~~~javascript
{
  _id: "C-101",
  tenantId: "T-A",
  name: "An",
  displayName: "An",
  version: 7
}
~~~

Update:

~~~javascript
const result = db.customers.updateOne(
  {
    _id: "C-101",
    tenantId: "T-A",
    version: 7
  },
  {
    $set: {
      name: "An New",
      displayName: "An New"
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount !== 1) {
  throw new Error("Concurrent update: reload and retry");
}
~~~

If another writer incremented the version first, `version=7` does not match. The application must reload, revalidate business logic, and retry only when safe.

**Limitation:** this only protects when **all participating writers** follow version discipline. If an old writer updates name without incrementing version, new writers cannot rely on version to detect all changes. Therefore, version control **does not replace retiring old-only writers**.

### 10.1. Be Careful with `replaceOne`

A service reading a snapshot:

~~~javascript
{ name: "An", displayName: "An", preferredLocale: "vi-VN" }
~~~

then rebuilding a document containing only:

~~~javascript
{ name: "An New" }
~~~

and calling **replaceOne** can wipe out **displayName/preferredLocale**, because replacement swaps the entire document (except `_id` per MongoDB rules).

During mixed-schema periods, prefer **targeted $set/$unset** on changed fields or build a complete replacement DTO with all fields and version checks. Never do “read then full replace” from an old DTO on a document containing new fields.

## 11. Rename Backfill via Aggregation Pipeline Update

Once new writers are deployed and no old-only writers remain, copy **name** to **displayName** for historical documents.

### 11.1. Why Not `$set` with a Literal?

The command:

~~~javascript
db.customers.updateMany(
  { displayName: { $exists: false } },
  { $set: { displayName: "name" } }
);
~~~

writes the **literal string "name"** into every document rather than copying the **name** field's value.

To reference another field's value within the same document, use an **aggregation pipeline update** (MongoDB 4.2+):

~~~javascript
db.customers.updateMany(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  [
    {
      $set: {
        displayName: "$name"
      }
    }
  ]
);
~~~

In the update pipeline:

- **"$name"** is an expression referencing the document's name field value.
- Checking **displayName missing** prevents overwriting an already-populated new field.
- Checking **name is String** avoids copying malformed values.
- Each document updates **atomically**, though **updateMany is not a collection-wide atomic transaction**.

### 11.2. Why Is It Idempotent?

First run:

~~~text
Before: { name: "An" }
After : { name: "An", displayName: "An" }
~~~

On a second run, **displayName: {$exists:false}** no longer matches, so the document is untouched. If a new writer already populated displayName before the migration ran, that document is not overwritten either.

**Still, idempotency does not solve all races**: if an old-only writer updates **name** after backfill, name and displayName can diverge. Hence disabling old-only writers or maintaining continuous sync is mandatory.

### 11.3. Do Not Blindly Overwrite Conflicts

If:

~~~javascript
{
  name: "An Old",
  displayName: "An New"
}
~~~

the command above **will not modify it** because displayName already exists. This is safer than overwriting without knowing which field is right, yet you still must **classify and resolve conflicts**.

Before switching, check:

~~~javascript
db.customers.countDocuments({
  name: { $type: "string" },
  displayName: { $type: "string" },
  $expr: { $ne: ["$name", "$displayName"] }
});
~~~

On large production data this can trigger a collection scan; run it bounded/off-peak or via a checkpointed reconciliation job emitting aggregate metrics.

### 11.4. Backfill Differs from Read Repair

A common suggestion is:

~~~text
On every legacy document read:
  -> if displayName is missing, write it immediately
~~~

This is **read repair**, which can help in some designs, yet turns reads into writes, adds latency, and risks concurrent write races. Never use read repair as the sole mechanism when cold documents exist or read-only callers lack write permissions.

A **dedicated backfill job** makes throttling, telemetry, and completion verification far easier.

## 12. Bounded Batched Backfill

A **collection-wide updateMany** can spike I/O, replication load, and latency. For large datasets, split into small batches and track progress.

### 12.1. `mongosh` Pattern Using `bulkWrite`

The example below processes **at most 200 candidates per iteration** in a test database:

~~~javascript
const batchSize = 200;
let examined = 0;
let totalModified = 0;

while (true) {
  const candidates = db.customers
    .find(
      {
        displayName: { $exists: false },
        name: { $type: "string" }
      },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .limit(batchSize)
    .toArray();

  if (candidates.length === 0) {
    break;
  }

  const operations = candidates.map(doc => ({
    updateOne: {
      filter: {
        _id: doc._id,
        displayName: { $exists: false },
        name: { $type: "string" }
      },
      update: [
        { $set: { displayName: "$name" } }
      ]
    }
  }));

  const result = db.customers.bulkWrite(
    operations, { ordered: false }
  );

  examined += candidates.length;
  totalModified += result.modifiedCount;
  printjson({
    examined,
    totalModified,
    batchMatched: result.matchedCount,
    batchModified: result.modifiedCount
  });

  sleep(100); // Lab: rate limit between batches.
}
~~~

**Concurrency-safety implications:**

- The job only reads candidate **_id**s.
- During `updateOne`, the filter still requires **displayName to be absent**.
- **$set: "$name"** reads the current name at update time rather than a pre-fetched String snapshot.
- If a new writer already set displayName, `updateOne` will not match, preventing overwrites.
- If the job crashes mid-run, re-running is safe for already-updated documents.

### 12.2. Production Batching Needs Additional Safeguards

The illustrative script is not a complete production migration system. A real job needs:

1. **Durable checkpoints** persisted outside RAM.
2. **Leader/lock/lease** to prevent two migration workers from unintentionally running the same slice.
3. **Timeouts, bounded retries, and idempotency** for partial bulk errors.
4. **Throttling** tied to replication lag, server CPU/IO, and pool pressure.
5. **Per-tenant constraints** when data spans different authorization scopes.
6. **Dead-letter/quarantine** for documents with invalid data types.
7. **Resume/reconcile capability** after deployments or network failures.
8. **Auditing** of operator, script version, and completion timestamp.

### 12.3. Checkpointing by `_id`

Documents can be scanned in ascending **_id** order:

~~~javascript
const page = db.customers.find(
  {
    _id: { $gt: lastProcessedId },
    displayName: { $exists: false }
  },
  { _id: 1 }
).sort({ _id: 1 }).limit(200).toArray();
~~~

However, **_id does not always reflect update order**; a new document may be inserted with an `_id` smaller than the checkpoint, or fields may change after the cursor passed. Hence beyond checkpoint scanning, a **reconciliation/final sweep** is needed after writers have switched.

Never assume that **ObjectId always reflects global commit order** for every collection or every `_id` type.

### 12.4. When `bulkWrite` Fails Mid-Batch

With **ordered:false**, the driver processes remaining operations even when one fails; the outcome can be partial success. You must:

- Record matched/modified counts and error categories.
- Avoid treating the whole batch failure as zero documents updated.
- Retry failed candidates using **guarded filters**.
- Never log sensitive document contents.

An idempotent backfill makes retries safer, yet you still must inspect validation errors, permissions, and resource limits.

## 13. Gate to Switch from Old-First to New-First

Switch the source of truth only with concrete evidence:

| Requirement | Evidence |
|---|---|
| No old-only writers remain | Deployment inventory, version telemetry, upgraded jobs/consumers |
| New writers dual-write accurately | Integration tests and write-path metrics |
| Backfill complete | Missing displayName drops to 0 in scope |
| Zero drift | Reconciliation on name/field versions |
| New queries/indexes ready | Explain plans, load tests, latency |
| Old readers still have rollback path | name remains populated and synchronized |
| API/CDC consumers compatible | Contract tests, monitoring |

Then deploy the **displayName-first** reader version. Feature flags/canaries can phase the rollout, though flags only control app behavior; they do not maintain field consistency on their own.

### 13.1. Canary in Rolling Deployments

A rollout plan:

~~~text
0% new-first readers
  -> 1% canary
  -> 10%
  -> 50%
  -> 100%
~~~

At each step, monitor:

- Missing displayName.
- Drift between name/displayName.
- API error/empty name rates.
- Latency of new queries/indexes.
- Data from delayed consumers.

Do not ramp traffic solely on request success rates if the new field returns **a valid String that is the wrong value**.

### 13.2. Backfill After Cutover?

You can keep a job fixing **remaining missing** values during the rollback window, but stop backfilling from name once displayName is canonical, since name may now be merely a temporary copy. Update reconciler rules to match each phase's source of truth.

## 14. When to Use `$rename` Directly?

MongoDB provides the **$rename** operator when you truly want to rename a field inside a document.

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  {
    $rename: {
      name: "displayName"
    }
  }
);
~~~

### 14.1. Key Behaviors of `$rename`

- If the source field **does not exist**, nothing is moved.
- If the target field already exists, **$rename overwrites the target**, risking loss of canonical data.
- `$rename` moves the field rather than copying it to keep both simultaneously.
- MongoDB does not guarantee preserving **field ordering** inside the document after a rename.
- `$rename` cannot be used arbitrarily on **fields inside array elements**.
- On a single document update, atomicity follows **single-document atomic update** rules.
- With `updateMany`, there is no collection-wide atomicity.

**Never run `$rename` indiscriminately** on a collection already containing both name and displayName if displayName might hold newer values.

### 14.2. `$rename` Does Not Replace Multi-Version Migrations

It fits better in a controlled batch/offline scenario where:

1. All services have stopped reading/writing the source field.
2. The target field does not exist yet or overwriting it is explicitly allowed by policy.
3. No mixed state exists that would cause conflicts.
4. Backups/checkpoints exist and staging tests passed.

In rolling deployments with multiple old/new writers, **copying fields with conditional updates** is usually safer.

### 14.3. Dotted Nested Fields

Example:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  {
    $rename: {
      "profile.name": "profile.displayName"
    }
  }
);
~~~

This renames a field inside a **regular embedded document**. Do not assume it works on every object inside an array **profiles[]**. Renaming keys inside array elements requires a dedicated migration strategy (an aggregation pipeline with **$map/$mergeObjects** or targeted updates for supported elements and fields).

### 14.4. Renaming Fields Inside an Array of Documents

Example:

~~~javascript
{
  _id: "C-301",
  contacts: [
    { type: "HOME", phone: "000-111" },
    { type: "WORK", phone: "000-222" }
  ]
}
~~~

Do not use `$rename` with path **contacts.$[].phone** assuming every array element will rename safely. A thorough migration typically involves:

- Building a transformed **newContacts** array in the application or aggregation pipeline.
- Keeping both old and new fields while old readers depend on them.
- Backfilling per document with version/guarded conditions.
- Verifying array length, order, and elements missing `phone`.
- Dropping the legacy `phone` field last.

If transforming via pipeline **$map**, handle null, empty arrays, and preserve all sibling fields; naive mapping expressions can strip metadata from each contact.

## 15. Dropping a Field: Three Distinct Actions

“Dropping a field” can mean three different things:

1. **Remove from API/DTO**: the application stops returning that field.
2. **Stop reading/writing in the application**: the field may still remain in old documents.
3. **Physically delete from MongoDB**: update documents via `$unset` or an equivalent migration.

These three steps **do not have to happen at the same time**.

### 15.1. Field Deprecation Phase

Suppose **legacyTag** is no longer read or written by code. Before deleting it:

- All APIs/reports/batch jobs have removed their dependency.
- Metrics confirm zero expected accesses.
- No consumers rely on change events carrying legacyTag.
- Schema validators do not require legacyTag.
- No rollback version requires legacyTag.
- No audit/retention policy requires keeping it.

You cannot prove a field is unused merely by **grepping a single source code repository**: other scripts, BI tools, ETL jobs, admin queries, or external apps might still access it.

### 15.2. Stop Writing Before Deleting

If service V2 still has:

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { legacyTag: "import-2026" } }
);
~~~

then a job removing all legacyTag values only works temporarily—writers will recreate the field afterward.

Proper sequence:

~~~text
Deploy readers not using legacyTag
         |
         v
Deploy writers not creating legacyTag
         |
         v
Verify no legacy writers
         |
         v
Wait required rollback/retention window
         |
         v
$unset legacyTag in batches
         |
         v
Verify no recurrence
~~~

### 15.3. Deleting Data with `$unset`

~~~javascript
db.customers.updateMany(
  { legacyTag: { $exists: true } },
  { $unset: { legacyTag: "" } }
);
~~~

**$unset** removes the field from the document. The **""** value is a syntax placeholder in the update operator; it does not mean MongoDB sets the field to an empty String.

Example:

~~~text
Before: { _id:"C-101", legacyTag:"import-2024" }
After : { _id:"C-101" }
~~~

Do not confuse **$unset** with **$set: {legacyTag:null}**. With `$set null`, the field still **exists** with type Null, affecting `$exists`, indexes, serialization, and validators.

### 15.4. Why Not Delete `name` Immediately After Copying?

After backfill:

~~~javascript
{ name: "An", displayName: "An" }
~~~

operators may still want to roll back to V1, which only reads name. Deleting name immediately would cause a rollback to return null or require an emergency reverse migration.

Hence you can retain **name** through a **clearly defined rollback window**. Only after deciding direct rollback to V1 is no longer supported do you proceed to contract via `$unset`.

### 15.5. Dropping a Field Does Not Erase All Historical Copies

When removing legacyTag:

- Replication logs may still hold historical data within retention limits.
- Old backups/snapshots still contain records.
- Warehouses, caches, search indexes, or exports may retain the field.
- Audit logs may contain related details.

If a field must be purged for privacy retention/erasure, execute deletion across **the entire data lifecycle**, not just an `$unset` on the primary collection.

## 16. Dropping the `name` Field in the Contract Phase

Only after all readers/writers use displayName and V1 rollback no longer needs name:

~~~javascript
db.customers.updateMany(
  { name: { $exists: true } },
  { $unset: { name: "" } }
);
~~~

Then verify:

~~~javascript
db.customers.countDocuments({
  name: { $exists: true }
});
~~~

The target result is 0 within migrated scope. After deletion, watch for **field reappearance** from delayed writers, admin jobs, or external connectors.

### 16.1. Do Not Clean Documents Yet Forget Code

If a Java DTO still contains:

~~~java
@Field("name")
private String name;
~~~

the code may still write the name field during upserts/replacements. Coordinate mapping updates in source code and database migrations in the **same release plan**, not just collection edits.

### 16.2. Drop Old Indexes After the Last Dependency

If you previously had:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "tenant_name_v1" }
);
~~~

once all queries use displayName and the new index is ready, consider:

~~~javascript
db.customers.dropIndex("tenant_name_v1");
~~~

Do not drop the old index at the start of dual-read, since legacy queries may still depend on it. On large systems, building/dropping indexes impacts resources and needs its own operational plan.

### 16.3. Avoid Renaming the Collection Simultaneously Unless Necessary

Changing **collection**, **field**, and **database namespace** in the same release multiplies compatibility and rollback paths. Separate independent changes into distinct phases, or establish a dedicated data replication/cutover strategy with clear gates.

## 17. Schema Validators: Changing in Multiple Steps

MongoDB supports collection validators, commonly using **$jsonSchema** to check document shapes on insert/update operations per validation settings.

### 17.1. Do Not Require `displayName` While Old Writers Remain

A premature validator:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["displayName"],
    properties: {
      displayName: { bsonType: "string" }
    }
  }
}
~~~

can reject legacy inserts that only include name. A `replaceOne` from an old client can also be blocked for omitting the new field.

### 17.2. Validator Expansion Phase

During expand, the validator should accept both old and new schema shapes per business rules:

~~~javascript
// Illustrative fragment of a validator accepting name or displayName.
{
  $jsonSchema: {
    bsonType: "object",
    anyOf: [
      { required: ["name"] },
      { required: ["displayName"] }
    ],
    properties: {
      name: { bsonType: "string" },
      displayName: { bsonType: "string" },
      preferredLocale: { bsonType: "string" }
    }
  }
}
~~~

**anyOf** does not enforce equality if both fields coexist. Cross-field equality or canonical-source policies belong in the application/migration layer. Production validators must preserve all existing constraints.

### 17.3. Observe Before Tightening

Example **collMod** command:

~~~javascript
db.runCommand({
  collMod: "customers",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["displayName"],
      properties: {
        displayName: { bsonType: "string" },
        preferredLocale: { bsonType: "string" }
      }
    }
  },
  validationAction: "warn",
  validationLevel: "moderate"
});
~~~

**warn** allows non-compliant writes while logging warnings; **moderate** applies specific semantics to already-invalid existing documents. Neither guarantees all legacy documents already comply with the new schema.

After backfill, compatible writers, and ending V1 rollback, tighten:

~~~javascript
db.runCommand({
  collMod: "customers",
  validationAction: "error",
  validationLevel: "strict"
});
~~~

This is a **sequential example**. If the collection already has a validator, a new **collMod validator** command **replaces the previous validator expression**. Always combine all prior constraints rather than accidentally dropping checks on `tenantId` or other fields.

### 17.4. Validation Does Not Fix Legacy Data

Validators check write operations per validation policy; they **do not backfill** existing documents.

After enabling **strict/error**, continue to:

- Report existing documents that do not yet match the schema.
- Control **bypassDocumentValidation** privileges.
- Ensure ETL/admin writers do not bypass arbitrarily.
- Test against representative data and monitor error rates.

### 17.5. Validators Can Break Rollback

If V1 only writes **name** and the new validator requires **displayName**, rolling back to the V1 binary after enabling strict/error can cause writes to fail. Tightening the validator is a **compatibility gate**, not harmless cleanup.

## 18. Phased Index Migration

While both fields exist:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, name: 1 },
  { name: "tenant_name_v1" }
);

db.customers.createIndex(
  { tenantId: 1, displayName: 1 },
  { name: "tenant_displayName_v2" }
);
~~~

### 18.1. Expand Indexes Before Switching Read Paths

Sequence:

1. Identify queries/filters/sorts on displayName.
2. Create the new index in an appropriate change plan.
3. Monitor index build, storage, and write overhead.
4. Validate with **explain** and load tests.
5. Enable new-first readers/canaries once the index is ready.
6. Retain the old index through the rollback window.
7. Drop the old index once all old readers/writers stop.

**A new index is not automatically faster**: performance depends on selectivity, cardinality, filters, collation, and data distribution.

### 18.2. Unique Indexes and Mixed-Schema Data

Suppose the business needs **externalCode** unique per tenant. Running immediately:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, externalCode: 1 },
  { unique: true }
);
~~~

can fail or enforce unintended constraints when many documents lack externalCode.

A transitional approach can be a **unique partial index** for documents that already have a String:

~~~javascript
db.customers.createIndex(
  { tenantId: 1, externalCode: 1 },
  {
    name: "tenant_externalCode_v2",
    unique: true,
    partialFilterExpression: {
      externalCode: { $type: "string" }
    }
  }
);
~~~

This only guarantees uniqueness for **documents matching the partial filter**. It does not ensure documents lacking externalCode satisfy business invariants.

Before building a unique index:

- Standardize types and normalization.
- Detect duplicates and verify collation.
- Ensure new writers do not insert duplicates.
- Define uniqueness scope per tenant/sharding topology.
- Prepare a fallback plan if index build fails.

### 18.3. A Rename Can Change Query Cardinality

If name has many null/missing entries whereas displayName is fully populated, the new index has a different key distribution from the old index. Query plans can shift even when application logic is unchanged. Measure actual stats after backfill.

### 18.4. Collation Must Stay Consistent

If the old index uses a different collation than the new index, equality and sorting may differ on case and diacritics.

Document explicitly in the migration plan:

~~~text
old query collation:
new query collation:
new index collation:
normalization policy:
~~~

and test names differing in case and accents. Never silently alter collation or canonicalization during a rename without an explicit decision.

## 19. Distinguishing Additive and Breaking Changes

| Operation | Primary Risk | Appropriate Phase |
|---|---|---|
| Add optional field | Missing in old data | Expand |
| New writer writes optional field | Old reader may ignore it | Expand |
| Require new field via validator | Old writers may be blocked | Post-migrate/gate |
| Copy name to displayName | Duplicate data, drift | Migrate |
| Prefer displayName on reads | Old writers make new values stale | Switch after old-writer drain |
| Run `$rename name → displayName` | Old readers lose field, target overwritten | Only under full control |
| Delete name via `$unset` | V1 rollback may break | Contract |
| Delete legacyTag via `$unset` | Historical data/consumer dependency loss | Contract after retention |
| Drop old index | Old queries slow down | Late contract |
| Remove field from DTO/API | External clients may fail | Independent API migration |

Adding an optional field is typically an **additive change**, easier to roll out than deleting a field still used by old readers.

### 19.1. Changing Data Types Is Harder Than Renaming

Example:

~~~text
old: price = "120.50" (String)
new: amount = NumberDecimal("120.50")
~~~

Requires parsing, rounding, invalid value handling, query/index updates, and type conversion. Never just copy the String to a new field and consider it converted to Decimal128.

### 19.2. Moving Fields to Nested Paths

If moving:

~~~text
old: customer.name
new: customer.profile.displayName
~~~

check ancestor objects: profile could be missing, null, Array, or String. Using **$set with dotted paths** creates the embedded object appropriately, yet fails if an ancestor has an incompatible type. Detect and repair anomalous records first.

### 19.3. Sensitive Fields

When migrations involve PII:

- Do not log mismatched values.
- Do not copy data into unauthorized reporting stores.
- Do not dump plaintext into CI artifacts or laptops.
- Account for KMS/CSFLE/Queryable Encryption if fields are encrypted.

For **client-side encrypted fields**, server-side `$rename`/`$set` operations do not automatically ensure the new encryption schema/index works. An authorized client may need to **decrypt/re-encrypt** via a specialized cryptographic migration.

## 20. Java MongoDB Sync Driver: Dual-Writing Both Fields

A repository should receive an injected **MongoCollection<Document>** from a shared application-scoped MongoClient.

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class CustomerRepository {
    private final MongoCollection<Document> customers;

    public CustomerRepository(
            MongoCollection<Document> customers) {
        this.customers = customers;
    }

    public boolean renameForTransition(
            String trustedTenantId,
            String customerId,
            String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name required");
        }

        UpdateResult result = customers.updateOne(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("_id", customerId)
                ),
                Updates.combine(
                        Updates.set("name", newName),
                        Updates.set("displayName", newName)
                )
        );

        return result.getMatchedCount() == 1;
    }

    public Document findById(
            String trustedTenantId,
            String customerId) {
        return customers.find(
                Filters.and(
                        Filters.eq("tenantId", trustedTenantId),
                        Filters.eq("_id", customerId)
                )
        ).first();
    }
}
~~~

This performs a **transitional dual-write** for one document. It does not by itself resolve:

- Concurrent old-only writers.
- Lost updates when multiple new requests change the name simultaneously.
- Business validation/authorization.
- Events/CDC/analytics needing the new field name.

Those constraints must be handled in the application workflow and rollout plan.

### 20.1. Optimistic Locking in Java

If all writers already use a version field:

~~~java
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;

public boolean renameIfVersion(
        String tenantId,
        String customerId,
        int expectedVersion,
        String newName) {

    var result = customers.updateOne(
            Filters.and(
                    Filters.eq("_id", customerId),
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("version", expectedVersion)
            ),
            Updates.combine(
                    Updates.set("name", newName),
                    Updates.set("displayName", newName),
                    Updates.inc("version", 1)
            )
    );
    return result.getMatchedCount() == 1;
}
~~~

This example is a **method within the same repository**, using the injected `customers` field. Version must be a shared contract among all writers; while an old writer does not increment version, optimistic locking cannot guard against all legacy operations.

### 20.2. Reading the Canonical Value by Phase

~~~java
public String getCustomerDisplayName(
        String trustedTenantId,
        String customerId,
        boolean newFieldIsCanonical) {

    Document customer = findById(
            trustedTenantId, customerId);
    if (customer == null) {
        return null;
    }

    String oldValue = customer.getString("name");
    String newValue = customer.getString("displayName");

    if (newFieldIsCanonical) {
        return newValue != null ? newValue : oldValue;
    }
    return oldValue != null ? oldValue : newValue;
}
~~~

The **newFieldIsCanonical** flag must be a reliable rollout config backed by gates before flipping. In production code, prefer non-blank/validity checks and emit metrics on fallbacks or conflicts.

### 20.3. Do Not Create a New `MongoClient` per Batch

A Java backfill worker should use a single `MongoClient` created once for the job, reusing its connection pool, setting **BulkWriteOptions**/timeouts, and closing resources at the end of the workflow. Never create tens of thousands of `MongoClient` instances per customer.

## 21. Java Batched Backfill with Guarded Pipeline Update

In the Java Sync Driver, an update pipeline can be expressed as a **List<Bson>** where supported by driver/server versions:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.BulkWriteOptions;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;

public final class CustomerBackfillJob {
    private final MongoCollection<Document> customers;

    public CustomerBackfillJob(
            MongoCollection<Document> customers) {
        this.customers = customers;
    }

    public long runOneBatch(int batchSize) {
        List<Document> candidates = customers.find(
                Filters.and(
                        Filters.exists("displayName", false),
                        Filters.type("name",
                                org.bson.BsonType.STRING)
                )
        ).projection(new Document("_id", 1))
         .sort(new Document("_id", 1))
         .limit(batchSize)
         .into(new ArrayList<>());

        if (candidates.isEmpty()) {
            return 0L;
        }

        List<WriteModel<Document>> operations =
                new ArrayList<>();

        for (Document candidate : candidates) {
            Bson guardedFilter = Filters.and(
                    Filters.eq("_id", candidate.get("_id")),
                    Filters.exists("displayName", false),
                    Filters.type("name",
                            org.bson.BsonType.STRING)
            );

            List<Bson> updatePipeline = List.of(
                    new Document("$set",
                            new Document("displayName", "$name"))
            );

            operations.add(new UpdateOneModel<>(
                    guardedFilter, updatePipeline));
        }

        return customers.bulkWrite(
                operations,
                new BulkWriteOptions().ordered(false)
        ).getModifiedCount();
    }
}
~~~

**Note:** this is **one batch method**, not complete job orchestration. It uses:

- `_id`-only projection to reduce network traffic.
- Write-time filter to prevent overwriting displayName.
- Pipeline update reading the **current value** of name.
- Unordered `bulkWrite` so one error does not halt remaining operations.

A production Java job also needs an outer loop, durable checkpoints, rate limiting, timeouts, bounded retries, error classification, dead-letter handling, and metrics. If invalid documents prevent creating displayName, the job must record errors rather than spinning forever.

### 21.1. Raw `Document` vs. Typed Mapping Risks

In the native Java Driver, field names like **name**, **displayName**, and **tenantId** are **literal BSON field names**. If a Spring Data Entity uses **@Field("customer_name")** on a Java property, the raw driver is unaware of that Spring Data annotation.

Therefore, when backfilling via the native driver, rely on the **physical BSON schema**, never blindly assuming Java property names.

### 21.2. Using `bulkWrite` Does Not Make the Whole Batch Atomic

A single `updateOne` is atomic per document. A bulk batch of 200 `updateOne`s **does not update 200 documents in a single transaction**. On partial failures, retrying with guarded filters is typically more appropriate than expecting full-batch rollback.

## 22. Spring Data MongoDB: Entities and Field Mapping During Transition

Suppose an application uses Spring Boot + Spring Data MongoDB:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("customers")
public class CustomerDocument {
    @Id
    private String id;

    private String tenantId;

    @Field("name")
    private String legacyName;

    @Field("displayName")
    private String displayName;

    private String preferredLocale;

    private String legacyTag;

    public CustomerDocument() {
    }

    // Getters/setters or constructor binding per project standards.
}
~~~

Entity V2 retains **both legacyName and displayName**, enabling mixed-schema reads. Java property **legacyName** maps to BSON field **name**. You cannot simply change:

~~~java
private String name;
~~~

to:

~~~java
private String displayName;
~~~

and expect Spring Data to automatically copy legacy collection data.

### 22.1. Reader Normalizes Data at the Service Layer

A service/read mapper can return a response DTO:

~~~java
public record CustomerResponse(
        String id,
        String displayName,
        String preferredLocale
) {}
~~~

In the old-first phase:

~~~java
String effectiveName =
        entity.getLegacyName() != null
                ? entity.getLegacyName()
                : entity.getDisplayName();
~~~

In the new-first phase:

~~~java
String effectiveName =
        entity.getDisplayName() != null
                ? entity.getDisplayName()
                : entity.getLegacyName();
~~~

The snippet assumes corresponding getters exist. Production code must handle empty Strings, validation, and metrics; precedence must be driven by the **migration phase**.

### 22.2. Dual-Write with `MongoTemplate`

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public final class CustomerTransitionWriter {
    private final MongoTemplate template;

    public CustomerTransitionWriter(MongoTemplate template) {
        this.template = template;
    }

    public boolean changeName(
            String trustedTenantId,
            String customerId,
            String newName) {

        Query query = new Query(Criteria.where("_id").is(customerId)
                .and("tenantId").is(trustedTenantId));

        Update update = new Update()
                .set("name", newName)
                .set("displayName", newName);

        UpdateResult result =
                template.updateFirst(query, update, "customers");

        return result.getMatchedCount() == 1;
    }
}
~~~

With the overload taking only a **collection name**, the code uses raw BSON fields **name** and **displayName** directly. With overloads taking an **entity class**, Spring Data applies mapping metadata. Never mix Java/BSON names across the two call styles without verifying the actual emitted query.

### 22.3. `@Version` and Optimistic Locking

Spring Data supports **@Version** on entities for optimistic locking in supported save/update flows.

~~~java
import org.springframework.data.annotation.Version;

@Version
private Long version;
~~~

However:

- All writers must obey the version contract.
- An old writer that fails to increment version breaks the guarantee.
- Native MongoDB writes or manual updates must be designed compatibly with versioning.
- A version field only manages concurrency, not whether the schema has migrated.

Never reuse the same **version** field for both optimistic locking and **schemaVersion** without separating their meanings.

### 22.4. Beware of `repository.save()`

A Spring Data repository may call:

~~~java
customerRepository.save(customer);
~~~

When saving an entity via replacement semantics, fields **absent from the entity/serializer** can disappear. In a mixed schema, a worker using entity V1 without displayName can **overwrite the whole document and drop displayName**.

Therefore:

- Audit all **save/replaceOne/upsert** code paths.
- During transition, prefer targeted updates where appropriate.
- Only use full-document save with an entity containing all retained fields and proper optimistic locking.
- Never assume controller-level dual-writes are enough if a background `repository.save()` still uses an old model.

### 22.5. Spring Data `@Field` Is Not a Migration Engine

The **@Field("displayName")** annotation only instructs the converter how to map a Java property to a BSON field. It does not:

- Populate displayName on documents that have name.
- Remove old name from the database.
- Create/move old indexes to the new field.
- Update validators automatically per policy.
- Migrate search pipelines/aggregations referencing name.
- Guarantee event consumers already use the new schema.

Dedicated application compatibility code and data migrations are still required.

## 23. Is Using `schemaVersion` Necessary?

A system can stamp:

~~~javascript
{
  _id: "C-101",
  schemaVersion: 2,
  displayName: "An",
  preferredLocale: "vi-VN"
}
~~~

Benefits:

- Enables diagnostics and migration routing.
- Helps read multiple distinct formats.
- Helps track version adoption.

However, **schemaVersion=2 does not prove every document field is valid**. A buggy writer can still produce:

~~~javascript
{
  schemaVersion: 2,
  name: "An"
}
~~~

or a document can undergo partial updates leaving schemaVersion and fields out of sync.

### 23.1. When Should It Be Used?

`schemaVersion` is useful when there are **meaningfully distinct document shapes** or data must traverse multiple versions. Yet for a single optional new field, **field-existence + validation** may be simpler and sufficient.

Do not add `schemaVersion` to every document merely to tag a `$set` run; if you add it, clearly define **who updates the version, under what conditions, and what it signifies**.

### 23.2. Schema Version and Optimistic Version Differ

| Field | Purpose | Example |
|---|---|---|
| schemaVersion | Document format/semantics | 1, 2, 3 |
| version or revision | Concurrent write control | 10, 11, 12 |
| migrationId | Job/batch audit trail if needed | Migration run UUID |

Do not increment **schemaVersion** every time a user changes their name unless the document actually transitions to a different logical schema.

### 23.3. Dedicated Migration State

For complex migrations, maintain a migration worker metadata collection:

~~~javascript
{
  _id: "customers-name-to-displayName-v2",
  phase: "BACKFILL",
  lastProcessedId: "C-500000",
  startedAt: ISODate("2026-11-01T00:00:00Z"),
  updatedAt: ISODate("2026-11-14T00:00:00Z")
}
~~~

This is **orchestration state**, not a required field inside every customer document. Checkpoint storage requires dedicated permissions and safe updates so two workers do not overwrite each other's progress.

### 23.4. Do Not Treat Checkpoints as Final Proof

A checkpoint only says a job traversed a range of data; it does not prove:

- No late documents were inserted with old IDs.
- No old writer recreated name.
- No conflicts exist.
- No documents were skipped due to invalid types.

You still need **final reconciliation** and post-cutover observation.

## 24. Multi-Service and Message/Event Schemas

An API is not the entire system. An event-driven system may include:

~~~text
Customer API V2
      |
      v
MongoDB customers
      |
      +--> Change stream consumer
      +--> Search index worker
      +--> Data warehouse ETL
      +--> Invoice service
      +--> Notification service
~~~

If downstream consumers still expect **name**, a database change keeping only **displayName** can break them even when the new API works fine.

### 24.1. Version Event Contracts Independently

A transitional event may look like:

~~~javascript
{
  eventType: "CustomerProfileChanged",
  eventVersion: 2,
  customerId: "C-101",
  name: "An New",
  displayName: "An New"
}
~~~

After consumers migrate:

~~~javascript
{
  eventType: "CustomerProfileChanged",
  eventVersion: 3,
  customerId: "C-101",
  displayName: "An New"
}
~~~

Do not claim **eventVersion=3** is automatically generated just because the database document has schemaVersion=3. The two contracts can follow separate rollout schedules.

### 24.2. Change Streams and Migration Writes

Backfilling one million documents generates a burst of update events in replication/change streams. Consumers might:

- Receive massive events unexpected by business logic.
- Reindex huge datasets.
- Trigger redundant notifications if migration updates are not distinguished.
- Lag or lose their resume position past the retention window.

Plan event filtering, consumer behavior, and capacity before running large jobs. For change streams:

- Ensure the deployment supports the feature.
- Handle resume tokens/checkpoints properly.
- Do not assume every event always contains the latest `fullDocument` at exact update time.
- Distinguish **updateDescription.updatedFields**, **removedFields**, and document lookup semantics by version.

### 24.3. Delayed Jobs Are Old Writers in Disguise

A message queued last week containing:

~~~javascript
{
  customerId: "C-101",
  name: "An Old"
}
~~~

if processed by a V1 consumer after cutover, can write **name** back or overwrite new data.

Before switching:

- Inspect consumer lag and dead-letter queues.
- Upgrade consumers to a compatible model.
- Define semantics for processing stale events.
- Apply version/timestamp/sequence guards where needed to prevent stale event overwrites.

A **complete drain** must account for queued work, not merely running pod counts.

## 25. Rollback: Reversibility by Phase

“Having a backup” does not mean “rolling back to V1 without data loss.” Different app versions expect different schemas while the system continues receiving writes during recovery.

### 25.1. Phase-by-Phase Rollback Table

| Deployed Phase | Direct V1 Rollback Possible? | Conditions |
|---|---|---|
| Expand tolerant reader | Usually yes | name remains and V1 writers operate |
| V2 dual-write | Possible | name stays synced and validator allows V1 |
| Backfill, both fields kept | Possible | name intact, not stale, old indexes/contracts preserved |
| Switch read displayName-first | Possible if name still accurate | Reconcile; V2 still dual-writes |
| Stop dual-writing name | Not automatically guaranteed | name may be stale relative to displayName |
| `$unset name` | Not directly | Requires reverse migration or forward-fix |
| Strict validator requiring displayName | V1 may be blocked | Must relax validator and restore old field |
| Drop old index | V1 queries may degrade | Must rebuild index before/during rollback |

### 25.2. Rollback Before Contract

If name has always been kept updated by new writers and not yet deleted:

~~~text
New reader returns displayName
       |
       v
Incident detected
       |
       v
Flag back to name-first reader
       |
       v
Keep dual-write during investigation
~~~

This rollback is relatively lightweight, yet safe only if **name remained synchronized** and all validators/indexes/consumers remain compatible.

### 25.3. Reverse Backfill After `name` Was Deleted

If displayName is accurate and writers can be paused/coordinated, restoring the old field name may look like:

~~~javascript
db.customers.updateMany(
  {
    name: { $exists: false },
    displayName: { $type: "string" }
  },
  [
    {
      $set: {
        name: "$displayName"
      }
    }
  ]
);
~~~

This is a **conditional reverse copy**, not a full rollback plan. You must also:

1. Ensure apps writing displayName do not immediately leave name stale after reverse backfill.
2. Adjust validators so V1 writes pass.
3. Rebuild old indexes if V1 query patterns require them.
4. Verify data, versions, and permissions.
5. Shift traffic safely.
6. Restore compatible workers/events.

Never run reverse backfill automatically when both fields conflict without first establishing the canonical source.

### 25.4. Forward Fix or Rollback?

Once past contract where data loss is non-trivial to reverse, a **forward fix** (patching V3) may carry lower risk than reverting to V1. Base the decision on:

- Incident severity.
- Availability of a trustworthy canonical data source.
- Whether the migration altered semantics/units.
- Acceptable recovery time.
- Backup/restore points and tolerable data loss.

Never design rollback as **restoring the entire database from an old backup** if doing so wipes out valid user updates made after the snapshot.

### 25.5. Do Not Purge Old Copies Before Retention Ends

One organization may mandate keeping records for audit/backup policies; another mandates deleting PII on schedule. Separate **rollback windows** from **data retention obligations**; do not keep old name copies indefinitely simply because rollback closure was neglected.

## 26. Transactions, Atomicity, and Migrations

MongoDB guarantees atomicity at the **single-document** level for appropriate update operations. With `updateMany` or `bulkWrite`, each document updates atomically, yet **there is no collection-wide atomic switch point** by default.

### 26.1. When Are Transactions Needed?

Suppose an invariant spans **two collections**:

~~~text
customers.displayName
customer_search.displayName
~~~

If the product requires both records to change together in one unit, evaluate **multi-document transactions** on a supported topology or an event/outbox pattern with suitable consistency.

However, never wrap **millions of updates** in a single transaction:

- Long transactions increase load and lock contention.
- Subject to operation, lifetime, and oplog/replication limits.
- Complex transient error/retry handling.
- Can severely impact live production workloads.

Idempotent batched backfills are usually the right operational choice for large-collection schema evolution.

### 26.2. Dual-Write Atomicity Within One Document

~~~javascript
db.customers.updateOne(
  { _id: "C-101" },
  { $set: { name: "An", displayName: "An" } }
);
~~~

Here both fields in the same document change atomically via a single update. A multi-document transaction is unnecessary just to write **two fields in the same document** together.

### 26.3. Schema Changes in Sharded Clusters

In a sharded cluster:

- Migrations can distribute across multiple shards.
- Queries including the shard key target specific shards more accurately.
- Collection scans/multi-updates can consume cluster-wide resources.
- Unique indexes carry shard key and topology constraints.
- Balancer/chunk migrations and replication lag must be monitored.

Never treat `updateMany` on a sharded collection as a cluster-wide transaction. Check compatibility and operational limits for your server version.

### 26.4. A Migration Must Not Saturate the Pool

If live services and migration workers share a cluster, throttle migration concurrency. Huge thread counts or connection pools do not guarantee faster backfills—they can push production traffic into wait queues and cause timeouts.

Operate based on measured telemetry:

~~~text
low concurrency
  -> monitor p95 latency, CPU/IO, replication lag
  -> increase gradually if headroom exists
  -> pause when SLO deteriorates
~~~

Never pick the largest `batchSize`/concurrency simply because a dev machine handled it.

## 27. Monitoring and Migration Metrics

Maintain dashboards broken down by **phase** and **deployment version**, not just a single “migration done” log line.

| Metric | Meaning |
|---|---|
| legacy_read_fallback_total | How many requests fell back to name |
| dual_write_success_total | Writes updating both fields successfully |
| old_only_writer_detected_total | Sources still writing only name detected |
| missing_displayName_count | Documents lacking the new field |
| invalid_displayName_count | New field exists yet wrong type/empty |
| name_displayName_drift_count | Two values out of sync during sync phase |
| preferredLocale_missing_count | Documents missing the new field |
| legacyTag_remaining_count | Documents not yet cleaned up |
| migration_batch_duration_ms | Processing latency per batch |
| migration_batch_modified | Documents modified per batch |
| migration_error_count | Errors by category |
| change_stream_lag | Lag on consumers/CDCs if present |
| app_read_error_rate | Reader/canary error rate |
| app_write_error_rate | Writer/validator error rate |
| db_replication_lag | Impact on replica set |

Metric names in this table are **system instrumentation suggestions**, not built-in MongoDB metrics with those exact names.

### 27.1. Query to Spot Unmigrated Documents

~~~javascript
db.customers.find(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  { _id: 1, tenantId: 1 }
).limit(20);
~~~

### 27.2. Query to Spot Conflicts

~~~javascript
db.customers.aggregate([
  {
    $match: {
      name: { $type: "string" },
      displayName: { $type: "string" }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$name", "$displayName"] }
    }
  },
  {
    $project: {
      _id: 1,
      tenantId: 1
    }
  },
  { $limit: 20 }
]);
~~~

The projection outputs only **_id** and **tenantId**, avoiding printing actual names into migration logs. If `tenantId` is also sensitive, mask or narrow observability scope accordingly.

### 27.3. Do Not Just Count—Check Quality

**missing_displayName_count = 0** still does not prove a migration succeeded if:

- The field holds an empty String.
- The field holds a stale copy.
- Values have wrong normalization.
- Some clients no longer read properly.
- Index/collation semantics differ.

Add **validity, drift, and functional checks**.

### 27.4. When to Halt the Migration?

Pause on alerts when:

- p95/p99 latency breaches SLO.
- Replication lag climbs.
- Bulk errors spike.
- Validator errors emerge from an old service version.
- Downstream consumers overload.
- `name`/`displayName` divergence increases instead of shrinking.

Never let a job keep running while data invariants are actively breaking.

## 28. Common Pitfalls in Multi-Phase Rollouts

### 28.1. Changing `@Field` in Java and Assuming MongoDB Renamed the Field

**Symptom:** new entity defines `displayName` but reads `null` on old documents.

**Cause:** `@Field` only controls mapping; physical data still uses `name`.

**Fix:** compatible reader, conditional backfill, then gated read-path switch.

### 28.2. Running `$rename` Once and Breaking Old APIs

**Cause:** `$rename` moves the field without leaving a copy for old readers.

**Fix:** use expand/dual-read/dual-write then contract. If already renamed, plan restoring `name` and handling old writers.

### 28.3. `$rename` Overwrites Newer `displayName` Values

**Cause:** target field existed with newer information, yet `$rename` ran indiscriminately.

**Fix:** stop the job, establish source of truth, recover from event logs/backups if needed; never blindly rerun.

### 28.4. Backfill Writes Literal `"name"` Into `displayName`

**Cause:** used update document **$set: {displayName:"name"}** instead of an aggregation pipeline update.

**Fix:** understand literal vs. expression **"$name"**, isolate corrupted documents, and repair under control.

### 28.5. Backfill Overwrites a User's Recent Name Update

**Cause:** job read an old snapshot and wrote a stale String without checking target field/version at write time.

**Fix:** use server-side guarded updates/pipeline references, optimistic versions, or proper concurrency control.

### 28.6. New Reader Switched to `displayName` While Old Writer Still Updates `name`

**Cause:** premature phase switch.

**Fix:** revert read preference to name-first if safe; upgrade/drain old writers and reconcile before switching again.

### 28.7. Re-Running Migration Mutates Data Further

**Cause:** non-idempotent migration, e.g., incrementing numbers, appending to arrays, or stamping new timestamps each run.

**Fix:** define migrated state, conditional filters, and checkpoints. Verify retries produce no duplicate side effects.

### 28.8. Job Skips Documents with `name: null`

**Cause:** filter matched only Strings, excluding invalid/empty data from the candidate set.

**Fix:** classify anomalies separately rather than coercing all nulls to empty Strings. Establish explicit repair rules.

### 28.9. Enabling Strict Validator Too Early

**Cause:** old writers do not yet populate `preferredLocale`/`displayName`.

**Fix:** adjust validator to a compatible phase, upgrade writers, backfill, and tighten only at the gate.

### 28.10. New Index Does Not Speed Up Queries

**Cause:** query targets the wrong field, different collation, unaligned query shape, or skewed data distribution.

**Fix:** run `explain`, inspect query plans/keys examined, and fix the index/query rather than adding more indexes blindly.

### 28.11. New Unique Index Fails to Build

**Cause:** duplicates, missing values, collation/normalization mismatches, or sharding constraints.

**Fix:** investigate duplicates and scope; use a partial unique index during transition if semantics fit, and clean data before tightening.

### 28.12. Old Background Job Makes `name` Reappear

**Cause:** scheduler/consumer was outside the main API rolling deployment.

**Fix:** inventory and upgrade all writers, drain queues/dead-letters, and monitor for field reappearance.

### 28.13. Full-Document Save Drops New Fields

**Cause:** V1 entity lacks `displayName`/`preferredLocale` and saves/replaces the whole document.

**Fix:** targeted updates, compatible V2 models, and concurrency controls; avoid old DTOs for full replacement.

### 28.14. Old and New Counts Match Yet Data Is Wrong

**Cause:** both fields exist on documents while holding different values.

**Fix:** reconcile **value equality** and canonical rules, not just `$exists` counts.

### 28.15. Multiple Migration Workers Run Overlapping Work

**Cause:** job scheduler spawned multiple instances without leases or checkpoint synchronization.

**Fix:** leader election/leases or idempotent design with partitioned ownership, tracking partial failures.

### 28.16. Rolling Back After Dropping `name` Breaks API V1

**Cause:** V1 only knows `name`, while documents now only have `displayName`.

**Fix:** do not roll back directly to the V1 binary; run a gated reverse migration or forward fix with validator/index compatibility.

### 28.17. Changing API Fields Before External Clients Upgrade

**Cause:** coupling database schema migration with a public API breaking change.

**Fix:** version the API, apply deprecation policies, return compatibility responses, and notify consumers.

### 28.18. CDC Consumer Lags After Backfilling Millions of Documents

**Cause:** migration caused a write/event burst the consumer could not keep up with.

**Fix:** rate limit, monitor lag and resume tokens, and evaluate how to distinguish migration events from business events.

### 28.19. Sensitive Field Removed via `$unset` Still Lives in Backups

**Cause:** `$unset` only affects current documents, not historical copies.

**Fix:** enforce retention/erasure policies across backups, exports, warehouses, logs, and caches with controlled recovery.

### 28.20. Renaming Fields Inside Arrays via `$rename` Fails

**Cause:** `$rename` does not support arbitrary renaming across array elements.

**Fix:** use array-aware transformations preserving elements/fields, testing missing/null cases and version concurrency.

## 29. Reference Deployment Runbook

A production runbook should break work into **verifiable gates** with clear owners:

### Phase 0 — Design and Baseline

1. Write an ADR documenting scope: **name → displayName, add preferredLocale, drop legacyTag**.
2. Define defaults/normalization, permissions, and retention.
3. Inventory all readers/writers/consumers/jobs.
4. Measure baseline field distribution, data types, latency, and indexes.
5. Verify backup/restore strategy and migration worker privileges.
6. Finalize rollback window and feature flags.

### Phase 1 — Expand

1. Deploy V2 readers handling old/new fields, preferring `name`.
2. Deploy V2 writers updating `name` and `displayName` in the same update.
3. Include `preferredLocale` on new creates where business defaults apply.
4. Expand validator to accept mixed state.
5. Create `displayName` indexes needed for future queries.
6. Monitor application versions, writes, and errors.

**Gate 1:** no code paths require `displayName` immediately before backfill; V1 keeps working during rolling deploys.

### Phase 2 — Retire Old-Only Writers

1. Upgrade main API replicas.
2. Upgrade consumers and batch jobs.
3. Stop or drain queued work using the old schema.
4. Verify old-version telemetry.
5. Revoke execution privileges for retired old scripts.

**Gate 2:** no independent source produces **name-only changes** unless covered by a reliable forwarding mechanism.

### Phase 3 — Migrate Data

1. Backfill missing `preferredLocale` per policy.
2. Backfill `displayName` where missing and `name` is valid.
3. Use guarded operations, batching, checkpoints, and retries.
4. Monitor replication lag and latency.
5. Quarantine/analyze invalid records.
6. Reconcile `name`/`displayName` conflicts.

**Gate 3:** new fields hold valid values, conflicts are resolved, and metrics meet switch criteria.

### Phase 4 — Switch

1. Canary `displayName`-first readers.
2. Compare response payloads, errors, and latency.
3. Ramp rollout progressively.
4. Continue dual-writing throughout the rollback window.
5. Confirm Search, analytics, and API contracts all use the new fields.

**Gate 4:** new read path is stable and rollback remains safe per plan.

### Phase 5 — Contract

1. Decide to end V1 rollback support.
2. Switch writers to new-only.
3. Remove `name` fallback in readers when no longer needed.
4. Stop requiring `name`/`legacyTag` in events/APIs.
5. Enable strict new validator if required by policy.
6. Remove `name`/`legacyTag` in guarded batches.
7. Drop old indexes after verifying query dependencies.
8. Monitor for field reappearance and downstream lag.

**Gate 5:** zero old dependencies remain; documents, indexes, validators, and events conform to the new schema.

### Phase 6 — Close Migration

1. Record outcomes, durations, errors, and accepted exceptions.
2. Archive migration scripts, ADRs, and rollback limitations.
3. Remove transitional flags and dual-write code once safe.
4. Audit migration account permissions, secrets, and legacy jobs.
5. Reconcile retention/backups/warehouse state.

**Never execute contract based purely on a hard calendar date** if data correctness and writer drainage gates have not passed.

## 30. Testing Compatibility Across Multiple Application Versions

A migration test suite must verify not only well-formed documents, but **multiple application versions running concurrently** against a mixed-schema collection.

### 30.1. Read/Write Matrix

| Data | V1 Reader name-only | V2 Reader old-first | V3 Reader new-first |
|---|---|---|---|
| `name` only | Readable | Readable | Readable via fallback if kept |
| Both `name` and `displayName` identical | Readable | Readable | Readable |
| Both differ | Reads `name` | Reads `name` | Reads `displayName` |
| `displayName` only | Cannot read name | Readable via fallback | Readable |
| Both missing | No name | Error/fallback per policy | Error/fallback per policy |

The **both differ** row is critical while old-only writers exist: it proves why new-first cannot be enabled too early.

### 30.2. Testing Concurrent Document Updates

~~~text
Document: name=A, displayName=A, version=1

Request 1: read version=1
Request 2: read version=1

Request 1: update to B with version=1 -> success
Request 2: update to C with version=1 -> matchedCount=0
~~~

Expected valid result:

~~~text
name=B, displayName=B, version=2
~~~

Request 2 must reload/revalidate rather than silently overwriting B. Such tests require a real MongoDB instance or integration environment with proper concurrency semantics; pure unit-test mocks are usually insufficient.

### 30.3. Testing Concurrent Backfill and User Updates

~~~text
T0: name=A, displayName missing
T1: backfill selects _id
T2: new app updates name=B, displayName=B
T3: backfill updates with filter displayName missing
~~~

Result: backfill does not match anymore, preserving B. This is why **write-time guarded filters** matter more than reading candidates once.

### 30.4. Testing Lingering Old Writers

~~~text
T0: name=A, displayName=A
T1: old writer sets name=B
T2: new-first reader returns A
~~~

This is a **risk-detection test**, not desired behavior. The switch gate must remain closed while an old writer exists without synchronization.

### 30.5. Testing `replaceOne` with Old DTOs

A V1 entity only has `name`. After V2 populates `displayName`, run a V1-shaped save/replace to verify:

- Does `displayName` disappear?
- Does `preferredLocale` disappear?
- Does `version` protect the update?
- Does the validator block the replacement?

Run this only in an integration dataset, never against real data.

### 30.6. Testing Data Validation

Create documents:

~~~javascript
{ _id: "CASE-1", name: "An" }
{ _id: "CASE-2", name: null }
{ _id: "CASE-3", name: 123 }
{ _id: "CASE-4", displayName: "An" }
{ _id: "CASE-5", name: "An", displayName: "An New" }
{ _id: "CASE-6", name: "" }
~~~

Verify:

- CASE-1 is backfilled.
- CASE-2/3 are quarantined for handling.
- CASE-4 is not overwritten.
- CASE-5 is flagged as a conflict.
- Whether CASE-6 is a valid name per business rules.

### 30.7. Testing Phased Rollback

A staging test:

1. Deploy compatible V2.
2. Migrate a subset.
3. Switch to new-first.
4. Roll back reader to old-first while `name` is still accurate.
5. Issue a follow-up write.
6. Verify old/new values remain synchronized.

Post-contract rollback tests must cover the **reverse migration/validator/index plan**, not merely rolling back the Docker image.

## 31. Hands-On Exercises and Scenarios

Exercises use the **app_lab** database and **customers** collection from Section 3. Never use a production database to test `$rename`/`$unset` commands.

### Exercise 1. Add Field Without Overwriting User Preferences

One document has `preferredLocale="en-US"`, another lacks `preferredLocale`.

**Task:** write an update that assigns `vi-VN` only to documents missing the field.

**Answer:**

~~~javascript
db.customers.updateMany(
  { preferredLocale: { $exists: false } },
  { $set: { preferredLocale: "vi-VN" } }
);
~~~

### Exercise 2. Missing vs. Null

Two documents:

~~~javascript
{ _id: "X", preferredLocale: null }
{ _id: "Y" }
~~~

**Question:** which document matches `preferredLocale: {$exists:false}`?

**Answer:** only Y. X has the field present with value null.

### Exercise 3. Is a One-Step Rename Safe?

The app still has 5 V1 pods reading `name`. A DBA runs `$rename name→displayName` across all documents.

**Question:** what happens?

**Answer:** V1 readers will fail to find `name`; V1 writers may recreate `name`. Reader/writer compatibility is required before removing the old field.

### Exercise 4. Copy Field via Pipeline Update

Document:

~~~javascript
{ _id: "X", name: "An" }
~~~

**Task:** populate `displayName` from `name` without overwriting an existing `displayName`.

**Answer:**

~~~javascript
db.customers.updateMany(
  {
    displayName: { $exists: false },
    name: { $type: "string" }
  },
  [
    { $set: { displayName: "$name" } }
  ]
);
~~~

### Exercise 5. Literal vs. Field Reference

~~~javascript
{ $set: { displayName: "name" } }
~~~

versus:

~~~javascript
[ { $set: { displayName: "$name" } } ]
~~~

**Answer:** the first update document assigns the literal string `"name"`; the second aggregation pipeline update reads the value from the `name` field.

### Exercise 6. Atomic Dual-Write

**Task:** update both `name` and `displayName` in a single command.

**Answer:**

~~~javascript
db.customers.updateOne(
  { _id: "C-101", tenantId: "T-A" },
  {
    $set: {
      name: "An New",
      displayName: "An New"
    }
  }
);
~~~

### Exercise 7. Old Writer Causes Drift

~~~text
T0: name=A, displayName=A
T1: old writer sets name=B
~~~

**Question:** what does a new-first reader return? Is it safe?

**Answer:** returns A even though the old writer wrote B. Unsafe unless old-only writers are eliminated or synchronized.

### Exercise 8. Choosing the Source of Truth

**Question:** while V1 writers remain, why might you prefer `name`? After old writers stop, what should be preferred?

**Answer:** `name` is the only field updated by all writers initially; once dual-write is universal, backfill finishes, and reconciliation passes, `displayName` becomes the primary source.

### Exercise 9. Backfill Idempotency

**Question:** why does filtering on missing `displayName` make re-running the migration safe?

**Answer:** already-backfilled documents no longer match; the job avoids overwriting newly created/updated new fields.

### Exercise 10. Conflicting Data

~~~javascript
{ name: "An Old", displayName: "An New" }
~~~

**Question:** should you run `$rename name→displayName`?

**Answer:** no, because the target would be overwritten. Classify conflicts and determine the canonical field by phase, history/version, and business rules.

### Exercise 11. Is `updateMany` Atomic Across the Collection?

**Question:** does updating one million documents via `updateMany` guarantee every document transitions to the new schema simultaneously?

**Answer:** no. MongoDB provides per-document atomicity, not a collection-wide atomic cutover point by default.

### Exercise 12. Batch Checkpoints

A job scanned `_id` up to `C-5000`. Later, a new document with `_id` `C-0400` is inserted using the old schema.

**Question:** is resuming from `lastProcessedId` guaranteed to process `C-0400`?

**Answer:** no. A final reconciliation/sweep is needed, along with ensuring new writers emit the right schema.

### Exercise 13. Renaming Fields in Arrays

A document has `contacts` as an array of objects, each with `phone`.

**Question:** can you simply use `$rename contacts.$[].phone→contacts.$[].contactPhone`?

**Answer:** no. `$rename` has restrictions on fields inside arrays. Use a controlled transformation preserving each element and handling concurrency.

### Exercise 14. Dropping a Field via `$unset`

**Task:** remove `legacyTag` from documents containing it.

~~~javascript
db.customers.updateMany(
  { legacyTag: { $exists: true } },
  { $unset: { legacyTag: "" } }
);
~~~

### Exercise 15. Null Instead of Unset

**Question:** is `$set legacyTag:null` equivalent to `$unset legacyTag`?

**Answer:** no. `$set null` keeps the field present; `$unset` removes the field from the document.

### Exercise 16. Premature Validator

V1 writers only populate `name`, while an admin enables validator **required: ["displayName"]**, `action=error`.

**Question:** what can happen?

**Answer:** old inserts/replacements may be rejected. Expand the validator or upgrade writers before tightening to strict/error.

### Exercise 17. `warn` and `moderate` Validation

**Question:** after enabling `validationAction=warn`, `validationLevel=moderate`, can you conclude every document satisfies the schema?

**Answer:** no. `warn` does not block invalid data; `moderate` applies specific semantics to already-invalid records. Validators do not backfill.

### Exercise 18. Partial Unique Index

One million documents lack `externalCode`, while new writers require unique `externalCode` per tenant.

**Question:** what are the benefits and limits of a partial unique index?

**Answer:** it enforces uniqueness for the subset having valid `externalCode` per the filter; it does not ensure all documents have the field or that the full business invariant holds globally.

### Exercise 19. Old and New Indexes

V2 readers still query `name`; V3 readers query `displayName`.

**Question:** when should `tenant_name_v1` be dropped?

**Answer:** after no readers use `name` and V1 rollback no longer needs the old index; keep both during transition and monitor dual-index overhead.

### Exercise 20. DTO Using `@Field`

Old Java entity has:

~~~java
@Field("name")
private String customerName;
~~~

A developer changes it to:

~~~java
@Field("displayName")
private String customerName;
~~~

**Question:** has Spring Data migrated all MongoDB data?

**Answer:** no. `@Field` only affects converter mapping on read/write; it does not migrate stored documents.

### Exercise 21. Full-Document Save

After V2 adds `displayName`, a V1 job reads a customer into an entity with only `name`, then saves the whole document.

**Question:** what is the risk?

**Answer:** replacement can drop `displayName`/`preferredLocale` because the V1 model is unaware of those fields. Upgrade the job or switch to targeted updates.

### Exercise 22. `schemaVersion` vs. Optimistic Version

Document:

~~~javascript
{ schemaVersion: 2, version: 19 }
~~~

**Question:** how do these two fields differ?

**Answer:** `schemaVersion` describes the document format; `version`/`revision` controls concurrent writes. Do not bump `schemaVersion` on every name edit if the schema has not changed.

### Exercise 23. Rollback Feasibility

V3 stopped dual-writes, deleted `name`, and enabled a strict validator requiring `displayName`. Ops wants to roll back to the V1 binary immediately.

**Question:** is this safe?

**Answer:** no. V1 lacks read/write fields, and validators/indexes may be incompatible. You need a reverse migration, validator/index restoration, or a forward fix.

### Exercise 24. Change Streams and Migration Traffic

Backfilling two million documents triggers a flood of update events.

**Question:** which downstream components are affected?

**Answer:** CDC, search indexers, caches, analytics, and notification workers. Monitor lag, rate limit, and avoid triggering unintended business actions.

### Exercise 25. Stale Messages in Queues

After switching, a consumer receives an old message with `name="An Old"` and writes `name` to the database.

**Question:** why is having zero V1 pods not enough?

**Answer:** old queued messages and delayed jobs still have impact. Drain queues, deploy schema-aware handlers, or add version/sequence guards.

### Exercise 26. PII After `$unset`

The system drops `legacyTag` from MongoDB, yet backups and warehouses still contain the field.

**Question:** can you declare the data erased everywhere?

**Answer:** no. Check retention/erasure obligations and handle copies, exports, caches, and logs accordingly.

### Exercise 27. Conflicting Data During Rollback

Before rollback:

~~~javascript
{ name: "An Old", displayName: "An New" }
~~~

**Question:** what should reverse backfill do?

**Answer:** never blindly copy one field to the other without identifying the canonical source. Inspect phase, event history, and conflict policy.

### Exercise 28. Changing Data Units

Field `oldPriceCents=12345`, new field `newPrice` in major currency units.

**Question:** can `$rename` alone do this?

**Answer:** no. You need `/100` conversion, Decimal types, rounding policies, overflow checks, and currency handling.

### Exercise 29. Designing a Full Phased Rollout

Requirements:

~~~text
old field: email
new field: contact.emailAddress
old readers: 12 pods remaining
old writers: nightly batch job
new API: needs search on contact.emailAddress
rollback requirement: 7 days
~~~

**Assignment:** design the steps:

1. Expand readers/serializers.
2. Dual-write `email` and `contact.emailAddress`.
3. Upgrade the nightly batch job.
4. Backfill with guarded conditions.
5. Create indexes on the new field.
6. Switch search paths.
7. Retain the old field across the rollback window.
8. Contract and drop old indexes.

**Guidance:** do not remove `email` or switch to new-only writers while the old batch job still runs. For emails, account for uniqueness, normalization, security/PII, external APIs, and duplicate handling.

### Exercise 30. Post-Cutover Incident

At 10% canary:

~~~text
missing displayName count = 0
name/displayName drift count = 500
read error rate = 0
~~~

**Question:** can you ramp to 100%?

**Answer:** no. Zero HTTP errors do not prove data correctness; 500 conflicts must be explained and resolved before ramping.

### Exercise 31. Partial Batch Failure

A `bulkWrite` runs 200 `updateOne`s, `modifiedCount=192`, and 3 documents fail validation.

**Question:** should you rerun the entire batch with an unfiltered update to be sure?

**Answer:** no. Classify matched/modified/errors, retry conditionally, quarantine invalid documents, and preserve idempotency.

### Exercise 32. Assessing Completion

Dashboard:

~~~text
displayName missing = 0
preferredLocale missing = 0
legacyTag remaining = 0
V1 pods = 0
V1 queued messages = 1000
~~~

**Question:** can you declare contract complete?

**Answer:** no. Those 1,000 V1 queued messages can still emit old writes; drain/migrate the messages and watch for field reappearance.

## 32. Practical Implementation Checklist

### 32.1. Before Deploying

- [ ] Documented old/new field map and canonical source per phase.
- [ ] Inventoried all readers, writers, batch jobs, consumers, and external clients.
- [ ] Sample test cases covering missing/null/invalid/conflict states.
- [ ] Approved policies for defaults, normalization, and type conversion.
- [ ] Assigned migration owner, gate checklist, and rollback window.
- [ ] Prepared new indexes and retention plan for old indexes.
- [ ] Planned schema validator and unique constraint updates.
- [ ] Least-privilege migration permissions and backup/restore plan ready.

### 32.2. During Expand

- [ ] Readers tolerate both old and new shapes.
- [ ] Old-first source active while old-only writers exist.
- [ ] New writers populate `name`/`displayName` in the **same update**.
- [ ] No full-document replacements wipe new fields.
- [ ] API event/CDC consumers prepared.
- [ ] Metrics tracking missing/fallback/drift available.

### 32.3. During Migrate

- [ ] Backfill uses guarded filters, idempotency, and sensible batch sizes.
- [ ] Job includes checkpoints, retries, dead-lettering, and throttling.
- [ ] Anomalies handled separately without overwriting valid data.
- [ ] Proven all old writers upgraded/drained.
- [ ] Monitored replication lag, p95 latency, write errors.
- [ ] Reconciliation verifies **values**, not just `$exists`.

### 32.4. During Switch and Contract

- [ ] Canary new-first readers passed gates.
- [ ] Rollback compatibility defined and time-bounded.
- [ ] Zero V1 binaries, queued messages, or admin scripts can write the old field.
- [ ] New-only writers ready.
- [ ] Strict/error validator enabled where appropriate.
- [ ] Old fields/indexes removed after zero dependencies remain.
- [ ] Monitoring field reappearance and downstream copies post-contract.

## 33. Quick Reference Table

| Need | Tool / Approach |
|---|---|
| Add field with default | `$set` + filter `$exists:false` |
| Distinguish missing and null | `$exists` and `$type` |
| Copy value from another field | Aggregation pipeline update with field reference |
| One-step rename with no mixed clients | `$rename` under controlled conditions |
| Keep old/new readers concurrently | Dual-read with phase-driven source of truth |
| Keep old/new writers concurrently | Single-document dual-write |
| Prevent lost updates | Version condition / optimistic locking |
| Backfill millions of records | Guarded batches, checkpoints, retries, throttling |
| Physically delete field | `$unset` during contract |
| Tighten schema enforcement | Phased `collMod` validator |
| Search on new field | Build new index before read cutover |
| Drop old index | After old queries and rollback need end |
| Roll back after source deletion | Planned reverse migration / forward fix |
| Monitor consistency | Missing/invalid/drift counters and reconciliation |
| Avoid breaking event consumers | Version/deprecate event contracts and drain queues |

## 34. References

Always verify official docs against your exact **MongoDB server version**, **Java Driver version**, and **Spring Data MongoDB version**:

- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — $set](https://www.mongodb.com/docs/manual/reference/operator/update/set/)
- [MongoDB Manual — $unset](https://www.mongodb.com/docs/manual/reference/operator/update/unset/)
- [MongoDB Manual — $rename](https://www.mongodb.com/docs/manual/reference/operator/update/rename/)
- [MongoDB Manual — Updates with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Manual — updateMany](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Java Sync Driver — CRUD Update](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/)
- [Spring Data MongoDB — Template API](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking)

MongoDB and Spring Data APIs/semantics evolve across versions. Before running any production script, verify behavior against your deployment's documentation, especially for **array updates, validator behavior, sharding, and transaction limits**.

## 35. Conclusion

Changing a MongoDB field looks like a simple CRUD operation, yet in a running system it is actually **a transition of a data contract across multiple software versions**.

~~~text
                    BEFORE
              customers.name
                    |
                    v
               EXPAND READERS
          old-first, accept both
                    |
                    v
                DUAL-WRITE
             name + displayName
                    |
                    v
               DRAIN V1 WRITERS
                    |
                    v
                  BACKFILL
     guarded $set + batch + checkpoint
                    |
                    v
                RECONCILE
    missing=0, invalid=0, drift resolved
                    |
                    v
                 SWITCH READ
              displayName-first
                    |
                    v
               ROLLBACK WINDOW
         keep old copy while needed
                    |
                    v
                  CONTRACT
        stop old writes/read fallback
        $unset old fields, drop index
                    |
                    v
                    AFTER
          customers.displayName
~~~

**Ten principles to remember:**

1. **Adding fields** starts with optional readers and updated writers; require them only after data and code are compatible.
2. **Renaming fields** in a rolling deployment is usually **copy → dual-run → switch → delete**, not an immediate `$rename`.
3. **Old-only writers can make new copies stale**; do not switch to new-first until that risk is eliminated.
4. **Dual-writing two fields in the same document in one update** is simpler and safer than two separate updates.
5. **Backfills must be idempotent and guarded**; never overwrite new fields that already have valid values.
6. **`$rename` can overwrite targets**; never use it carelessly on documents with conflicting old/new fields.
7. **`$unset` belongs in the contract phase**, once no old readers/writers remain and rollback no longer needs the old field.
8. **Indexes, validators, events, DTOs, and background jobs are all part of schema migration**, not just documents.
9. **Measure correctness**, including missing, invalid, drift, and queued old events—not merely whether the app throws errors.
10. **Rollback is a design requirement from day one**. Once dual-writes stop, old fields are dropped, or validators tighten, reverting to an old binary typically requires a reverse data migration or a forward fix.

Done right, MongoDB enables schema evolution with near-zero user disruption: application versions expand read support first, writers and data transition gradually, and only then does the system contract onto the new schema. **The secret is changing in verified phases with clear gates, never letting a data update outpace system-wide compatibility.**
