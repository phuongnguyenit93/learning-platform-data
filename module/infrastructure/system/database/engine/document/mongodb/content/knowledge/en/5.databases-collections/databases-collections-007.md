# Modifying Collection Options with `collMod` Within Supported Scope

In MongoDB, a **collection** holds not only documents, but can also carry configurations governing document structure validation, indexes, data retention, and certain server features. These configurations are typically set when creating the collection or index. When business requirements change, you do not necessarily have to drop and recreate the collection: the **`collMod`** command lets you modify **selected MongoDB-supported options** in place on an existing collection.

The key word is **selected**. `collMod` is not a general-purpose command for changing every property of a collection; collection type, feature constraints, server version, and per-option rules govern whether a modification is permitted. This lesson focuses on identifying supported scope, operating safely, and reading results via `mongosh`.

## 1. What Is `collMod`?

`collMod` is a **database command** used to modify supported attributes of an existing collection or view in the current database.

General syntax:

```javascript
db.runCommand({
  collMod: "<collection_or_view_name>",
  // Options modifiable in your current MongoDB version
})
```

Example changing how documents failing validation rules are handled:

```javascript
use mongo_lab

db.runCommand({
  collMod: "registrations",
  validationAction: "warn"
})
```

On success, the response includes `ok: 1`. On failure, the server returns `ok: 0` along with an error code and message—such as collection not found, insufficient privileges, unsupported option, or invalid option value.

**Distinguishing three operations:**

| Operation | When to Use | Example |
| --- | --- | --- |
| `db.createCollection()` | Create a new collection with initial options | `db.createCollection("registrations", {...})` |
| `db.runCommand({ collMod: ... })` | Modify supported options on an existing collection/view | Update validator, change index TTL |
| `db.collection.updateOne()/updateMany()` | Modify **data documents** inside a collection | Change a registration's `status` |

`collMod` affects **collection or index configuration**, not automatically transforming existing stored data into a new schema. For instance, adding a validator does not populate missing fields on older documents, nor does it automatically fix mistyped values.

## 2. What Can Be Modified and What Cannot Be Changed Arbitrarily

MongoDB has expanded `collMod` capabilities across versions. The table below outlines common supported areas; the documentation for **your running server version** remains the final authority.

| Category | Typical Changes | Limitations to Remember |
| --- | --- | --- |
| Document validation | `validator`, `validationLevel`, `validationAction` | Rules affect only write operations subject to validation; does not scan/fix historical data |
| TTL index | `index.expireAfterSeconds` for eligible indexes | Must name the exact index and meet index-type criteria; data can be deleted by TTL |
| Index visibility | `index.hidden` to hide/unhide an index | Hiding from the query planner is not the same as dropping the index |
| Converting index to unique | `prepareUnique` and unique conversion flow on supported versions | Must inspect duplicate data and follow the full procedure; not every index qualifies |
| View | `viewOn`, `pipeline` | Updates the view definition without modifying source documents; subject to view restrictions |
| Newer features | Time series options, change stream pre/post images, capped collections, etc. | Depends on server version, collection type, and feature-specific constraints |

**Tasks that should NOT be assumed to be `collMod`'s job:**

- Renaming a collection: use `renameCollection` or the equivalent rename API.
- Arbitrarily converting a standard collection into a capped or time-series collection: these are constrained structural choices, not flags that toggle freely.
- Changing a collection's **default collation** after creation: not an arbitrary `collMod` option; design an appropriate new collection/index if different comparison rules are needed.
- Creating a new index or arbitrarily changing index keys: use index management commands such as `createIndex()`, and consider building a replacement index.
- Changing a shard key: must follow dedicated sharding procedures on supported versions, never `collMod` as a shortcut.
- Dropping a collection, deleting documents, or migrating database names: use the dedicated commands for each task.

For databases and collections, the rule is **confirm which options fall within supported modification scope before running the command**.

## 3. Preparing Practice Environment and Inspecting Current Configuration

Examples use the `mongo_lab` database, the `registrations` collection, and course registration documents. Only run create, write, or modify operations on a practice database where you have appropriate permissions.

```javascript
use mongo_lab

db.createCollection("registrations", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseCode", "active"],
      properties: {
        studentId: { bsonType: "string" },
        courseCode: { bsonType: "string" },
        active: { bsonType: "bool" },
        registeredAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "warn"
})
```

Because the collection uses `warn` mode, documents violating rules are still written while the server logs warnings. To practice cleanly on a controlled collection, do not re-run `createCollection()` if the collection already exists; check state first or use a different lab name.

Insert two valid documents:

```javascript
db.registrations.insertMany([
  {
    _id: "reg-101",
    studentId: "u101",
    courseCode: "MDB101",
    active: true,
    registeredAt: new Date("2026-01-10T08:00:00Z")
  },
  {
    _id: "reg-102",
    studentId: "u102",
    courseCode: "MDB101",
    active: false,
    registeredAt: new Date("2026-01-11T08:00:00Z")
  }
])
```

### Reading Back Collection Metadata

```javascript
db.getCollectionInfos({ name: "registrations" })
```

The output shows collection metadata, including `options` with configured settings such as `validator`, `validationLevel`, and `validationAction`. For cleaner inspection:

```javascript
const infos = db.getCollectionInfos({ name: "registrations" });
if (infos.length !== 1) {
  throw new Error("Expected exactly one registrations collection");
}
printjson(infos[0].options);
```

When you need to inspect indexes:

```javascript
db.registrations.getIndexes()
```

`getIndexes()` displays names, keys, uniqueness, TTL, or `hidden` status if present. This is essential context before modifying an index with `collMod`.

Beyond `db.runCommand()`, you can specify the target database explicitly:

```javascript
db.getSiblingDB("mongo_lab").runCommand({
  collMod: "registrations",
  validationAction: "warn"
})
```

This is helpful when your shell session is currently positioned on a different database, since `collMod` operates on the collection inside **the database receiving the command**.

## 4. Modifying `validator`: Adjusting Data Rules

**Document validation** controls the types and shapes of documents written to a collection. A validator can use MongoDB query expressions or `$jsonSchema`.

Suppose a new requirement arrives: in addition to the three required fields `studentId`, `courseCode`, and `active`, each registration may have a `status` matching one of `enrolled`, `completed`, or `cancelled`. We add this rule using `collMod`:

```javascript
db.runCommand({
  collMod: "registrations",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseCode", "active"],
      properties: {
        studentId: {
          bsonType: "string",
          description: "Student ID must be a string"
        },
        courseCode: {
          bsonType: "string",
          description: "Course code must be a string"
        },
        active: {
          bsonType: "bool",
          description: "Active flag must be a boolean"
        },
        registeredAt: {
          bsonType: "date"
        },
        status: {
          enum: ["enrolled", "completed", "cancelled"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "warn"
})
```

Here `status` is **not yet** in `required`; earlier documents can continue existing without `status`. The rule checks the value only when the field is present. If you change `required` to:

```javascript
required: ["studentId", "courseCode", "active", "status"]
```

then older documents missing `status` are not automatically repaired. They may be rejected during validated writes under `strict` + `error` mode.

**Note on how it applies:** When sending a new `validator`, supply the entire desired rule set. Do not assume `collMod` will "merge" only the `status` field into the old validator; the new `validator` object replaces the previous definition.

### Backfilling Fields on Older Documents Before Making Them Required

In a lab environment, you can update documents missing `status`:

```javascript
db.registrations.updateMany(
  { status: { $exists: false } },
  { $set: { status: "enrolled" } }
)
```

Only after data has been appropriately normalized should you consider adding `status` to `required` and switching to `validationAction: "error"`. On real data, default backfill values must reflect actual business state; never blindly mark every legacy registration as `enrolled` if some were actually completed or cancelled.

## 5. `validationLevel` and `validationAction`: Validation Scope and Reaction

These are two distinct option groups:

- **`validationLevel`** determines which documents are checked.
- **`validationAction`** determines what MongoDB does when a write violates the validator.

### 5.1. `validationLevel`

| Value | Typical Meaning |
| --- | --- |
| `strict` | Validates inserts and normal updates against the validator |
| `moderate` | Validates inserts and updates to currently valid documents; does not apply the same rejection to updates on already-invalid legacy documents |
| `off` | Disables document validation |

`moderate` is useful during schema transitions because it lets already-nonconforming legacy documents continue being updated. That does not mean those documents are valid or that migration is complete.

Example switching to `moderate`:

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "moderate"
})
```

If you want all subsequent writes to satisfy the validator, `strict` is the clearer choice once legacy data has been cleaned up.

### 5.2. `validationAction`

| Value | When a Document Is Invalid |
| --- | --- |
| `warn` | Allows the write and logs a validation warning to the server log |
| `error` | Rejects the write operation that violates the validator |

Newer MongoDB versions also provide additional actions, such as extra logging on rejection. Only use values documented for your running MongoDB version.

Switch to rejecting invalid data:

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "strict",
  validationAction: "error"
})
```

Now test a document with the wrong type for `active`:

```javascript
db.registrations.insertOne({
  studentId: "u103",
  courseCode: "MDB101",
  active: "true",
  status: "enrolled"
})
```

`active` is the string `"true"`, whereas the validator requires a BSON boolean `true` or `false`, so under normal circumstances document validation rejects the insert.

Fix it:

```javascript
db.registrations.insertOne({
  studentId: "u103",
  courseCode: "MDB101",
  active: true,
  status: "enrolled"
})
```

This write complies with the validator. If the collection has unique indexes or other constraints, those constraints still apply independently.

### Validation Does Not Retroactively Fix History

Switching `validationAction` from `warn` to `error` **does not retroactively scan and delete old documents**. A document inserted during `warn` mode remains in the collection after tightening enforcement, even if it fails the new validator. Such documents must be identified, evaluated, and fixed via controlled data operations.

Also note that certain privileged write operations can use `bypassDocumentValidation` under MongoDB's rules. Validators help protect data contracts, but do not replace authorization checks and application logic.

## 6. `collMod` for TTL Indexes: Changing Retention Duration

A **TTL index (Time To Live)** lets MongoDB automatically delete documents after a set period elapsed from an indexed date field. For example, a `sessionEvents` collection holds login session events initially retained for 7 days.

### Creating the Initial TTL Index

```javascript
db.sessionEvents.createIndex(
  { createdAt: 1 },
  {
    name: "createdAt_ttl",
    expireAfterSeconds: 604800
  }
)
```

`604800` is the number of seconds in 7 days. Eligible documents have a `createdAt` field of type `Date`; documents without a valid date will not be automatically deleted by TTL as expected.

Sample document:

```javascript
db.sessionEvents.insertOne({
  eventType: "login",
  userId: "u101",
  createdAt: new Date()
})
```

### Changing from 7 Days to 14 Days

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 1209600
  }
})
```

This is a classic example of modifying **an existing index's options** without dropping and rebuilding the index. The index name must match the actual index; inspect first with:

```javascript
db.sessionEvents.getIndexes()
```

On supported versions, `collMod` can also convert a qualifying single-field index into a TTL index by adding `expireAfterSeconds`. This is subject to version and index-type requirements; do not assume every index can be converted to TTL. Also do not confuse `index.expireAfterSeconds` here with collection-level TTL options specific to **time-series collections**.

### Practical Impact When Changing TTL

Suppose you shorten retention from 14 days down to 1 day:

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 86400
  }
})
```

Documents older than the new threshold rapidly become eligible for deletion by the TTL background thread. TTL deletion runs **asynchronously**, with no guarantee that each document disappears at the exact second of expiration. Lowering TTL on a large collection can trigger substantial delete volume and impact performance.

Therefore, before altering TTL in a real environment, estimate the volume of documents that will expire immediately, plan for disk, delete-throughput, and historical-retention impacts. Never use TTL where exact instantaneous expiration is required.

## 7. Hiding and Unhiding Indexes with `index.hidden`

MongoDB supports **hidden indexes** on corresponding versions. A hidden index still exists and continues to be maintained on data writes, but the query planner does not consider it when selecting query plans. This feature is useful for evaluating whether an index is still needed for queries.

Create a test index:

```javascript
db.registrations.createIndex(
  { courseCode: 1 },
  { name: "courseCode_1" }
)
```

Hide the index:

```javascript
db.runCommand({
  collMod: "registrations",
  index: {
    name: "courseCode_1",
    hidden: true
  }
})
```

Unhide it:

```javascript
db.runCommand({
  collMod: "registrations",
  index: {
    name: "courseCode_1",
    hidden: false
  }
})
```

After each step, inspect `db.registrations.getIndexes()` and verify query behavior as needed. Keep these distinctions clear:

- **Hiding an index:** the index still occupies space, continues receiving updates, and still enforces its constraints.
- **Dropping an index:** removes the index structure; it must be rebuilt from scratch if needed again later.
- **Disabling TTL:** cannot be achieved via `hidden: true`; hiding a TTL index is not a safe way to pause expiration.

Not every special index can be hidden, such as `_id`. Never attempt to modify system indexes unless explicitly supported.

## 8. Modifying View Definitions with `collMod`

A **view** presents query results over a source collection or view via an aggregation pipeline. A view does not store its own document copy like a regular collection. Within MongoDB's supported scope, `collMod` can update `viewOn` and `pipeline` on an existing view.

Create an initial view showing only active registrations:

```javascript
db.createView(
  "activeRegistrations",
  "registrations",
  [
    { $match: { active: true } },
    { $project: { studentId: 1, courseCode: 1, active: 1 } }
  ]
)
```

When a new requirement adds `status` to the output:

```javascript
db.runCommand({
  collMod: "activeRegistrations",
  viewOn: "registrations",
  pipeline: [
    { $match: { active: true } },
    {
      $project: {
        studentId: 1,
        courseCode: 1,
        active: 1,
        status: 1
      }
    }
  ]
})
```

Inspect the updated definition:

```javascript
db.getCollectionInfos({ name: "activeRegistrations" })
```

Queries via `db.activeRegistrations.find()` now return the structure produced by the updated pipeline. Documents in `registrations` **are not modified** by editing the view.

Note that views carry their own constraints on namespaces, pipelines, and permissions. Being able to swap the pipeline does not imply you can arbitrarily change a view's default collation or turn a view into a data-storing collection with `collMod`.

## 9. Version-Specific Capabilities to Verify First

Beyond validators, TTL, hidden indexes, and views, some `collMod` parameters exist only in specific release lines or apply only to specific collection types:

**Modifying time-series collection settings.** MongoDB may allow modifying certain settings such as expiration duration or bucket granularity under specific conditions. Allowed change directions, option names, and constraints vary across versions; never apply time-series syntax to a standard collection just because both use `collMod`.

**Pre/post images for change streams.** On supported versions, you can enable storing before/after document images using `changeStreamPreAndPostImages`:

```javascript
db.runCommand({
  collMod: "registrations",
  changeStreamPreAndPostImages: { enabled: true }
})
```

This feature requires a compatible version (introduced in MongoDB 6.0), appropriate retention planning, and change stream usage; do not assume it is available on every deployment.

**Converting a non-unique index to unique.** Supported MongoDB releases provide a workflow to convert an existing index via a preparation step (`prepareUnique`), checking and cleaning up duplicate values before finalizing `unique`. Never run conversion commands directly on live data without verifying server version, index eligibility, and duplicate counts.

**Capped collections.** Certain versions support adjusting the size or document limits of a capped collection via dedicated parameters. This does not grant the ability to arbitrarily convert a standard collection into a capped one.

In practice, verify your server version first using:

```javascript
db.version()
db.adminCommand({ buildInfo: 1 })
```

Then cross-check the `collMod` documentation for **your exact version and collection type** before deploying less common parameters.

## 10. Safe Procedure for Changing Options in Real Environments

For any metadata change that can affect data integrity or performance, follow an observable and reversible workflow:

1. **Confirm database, collection name, and object type.** Use `db.getName()` and `db.getCollectionInfos({name:"..."})`. Distinguish regular, time-series, capped collections, and views.
2. **Verify server version and privileges.** `collMod` requires appropriate permissions on the target namespace. When using restricted accounts, resolve `Unauthorized` errors via RBAC rather than disabling security.
3. **Record pre-change configuration.** Save `getCollectionInfos()` and `getIndexes()` output in deployment records while protecting internal details. For changes carrying data-deletion risk like TTL, ensure a backup/restore plan exists.
4. **Assess impact.** Will a new validator block current writes? Will a shorter TTL mark large numbers of documents for immediate deletion? Will hiding an index slow down critical queries? Will a new view shape break application contracts?
5. **Test in a comparable environment.** Use representative data and exercise related read/write paths. When changing a validator, test valid/invalid types and legacy documents. When modifying indexes, inspect query plans and performance.
6. **Run `collMod` during an appropriate change window.** Keep the payload minimal, containing only the options intentionally being changed. Execute through an audited channel recording operator and outcome.
7. **Re-read metadata and verify behavior.** Confirm options took effect and run relevant read/write checks. `ok: 1` only confirms command acceptance, not that business behavior is correct.
8. **Monitor and keep a rollback plan ready.** For validators or hidden indexes, you can issue another `collMod` to restore prior options if supported. Data already deleted by TTL cannot be recovered simply by raising `expireAfterSeconds` back up.

### Verification Pattern in `mongosh`

```javascript
const targetDB = db.getSiblingDB("mongo_lab");
const name = "registrations";

const metadataBefore = targetDB.getCollectionInfos({ name });
if (metadataBefore.length !== 1 || metadataBefore[0].type !== "collection") {
  throw new Error("Target collection not found");
}

print("Before change:");
printjson(metadataBefore[0].options);

const result = targetDB.runCommand({
  collMod: name,
  validationAction: "warn"
});

if (result.ok !== 1) {
  throw new Error("collMod failed: " + tojson(result));
}

print("After change:");
printjson(targetDB.getCollectionInfos({ name })[0].options);
```

This pattern intentionally reads metadata before and after so learners can observe the collection state. In automated deployment tooling, add explicit option assertions, safe logging, and proper error handling.

## 11. Common Errors When Using `collMod`

| Situation | Possible Cause | Resolution |
| --- | --- | --- |
| `NamespaceNotFound` or collection not found | Wrong database, wrong name, or collection not yet created | Verify `db.getName()` and `getCollectionInfos()` |
| `Unauthorized` | Account lacks `collMod` privileges on the namespace | Use an appropriately scoped role granted by an administrator |
| Option rejected | Unsupported MongoDB version, wrong collection type, or syntax error | Check `collMod` documentation for your exact version and inspect `type` |
| Error referencing `index` | Wrong index name, ineligible index type, or disallowed option | Run `getIndexes()`, confirm the index exists and supports the option |
| Legacy documents remain invalid | Updating a validator does not retroactively rewrite stored data | Plan a separate data migration |
| Writes fail after tightening validation | `strict` + `error` blocks non-conforming operations | Inspect validation error details; fix input payloads or update rules if requirements changed |
| Data deleted after lowering TTL | Many documents exceeded the new threshold | Restore from backup if needed; raising TTL back affects only remaining documents |
| Queries slow down after hiding an index | Query planner stopped using that index | Compare execution plans; consider `hidden: false` |
| Application errors after updating a view | New pipeline/projection omitted fields expected by the app | Restore a compatible view definition or update the application contract |

In particular, **collection options and collection data are two separate layers**. A successful `collMod` call does not guarantee every old document conforms to the schema, that TTL-deleted data can be resurrected, or that applications relying on views/indexes will keep working unchanged.

## 12. Hands-On Exercises

### Exercise 1: Switching a Validator from Warning to Error

The `registrations` collection already has a validator requiring `active` to be boolean and currently uses `validationAction: "warn"`. Write the command to reject writes that fail validation.

**Solution:**

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "strict",
  validationAction: "error"
})
```

Try inserting `{studentId:"u200", courseCode:"MDB101", active:"false"}` in your lab environment to observe the error. Replacing `"false"` with the boolean `false` satisfies the type constraint.

### Exercise 2: Changing TTL Without Recreating the Index

The `sessionEvents` collection has a TTL index named `createdAt_ttl` currently retaining data for 7 days. Change it to 30 days.

**Solution:**

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 2592000
  }
})
```

Re-read `db.sessionEvents.getIndexes()` and confirm `expireAfterSeconds` equals `2592000`. Extending the duration does not bring back documents previously deleted by TTL.

### Exercise 3: Hiding an Index to Evaluate Query Plans

The `registrations` collection has an index `courseCode_1`. Hide the index, then unhide it.

**Solution:**

```javascript
db.runCommand({
  collMod: "registrations",
  index: { name: "courseCode_1", hidden: true }
})

db.runCommand({
  collMod: "registrations",
  index: { name: "courseCode_1", hidden: false }
})
```

In real systems, observe query plans and system load between the two steps rather than running both commands back-to-back immediately.

### Exercise 4: Identifying When `collMod` Is Not Appropriate

A team wants to (a) add a required field to a validator; (b) rename `registrations` to `enrollments`; (c) convert a standard collection into a capped collection; (d) update a view pipeline.

**Solution:**

- (a) Can update the validator with `collMod`, while also accounting for legacy documents.
- (b) Use the collection rename operation, not `collMod`.
- (c) Do not treat this as an attribute toggled freely via `collMod`; redesign using an appropriate migration workflow.
- (d) Can use `collMod` on a view if MongoDB conditions are met.

## Conclusion

`collMod` is the tool for modifying **supported metadata** of an existing collection or view. Its most important practical uses are updating **document validators**, switching **`validationLevel`/`validationAction`**, adjusting **TTL index** options, **hiding/unhiding indexes**, and updating **view pipelines**. Each area carries its own restrictions based on server version and object type.

Before every `collMod` call, inspect current state, specify only the options you intend to change, anticipate impacts on data and applications, and verify metadata and behavior afterward. That way, you apply controlled configuration changes without confusing them with document updates or database restructuring operations.
