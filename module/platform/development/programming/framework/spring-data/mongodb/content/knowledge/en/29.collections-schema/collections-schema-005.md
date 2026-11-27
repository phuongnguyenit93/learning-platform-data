# required, validationLevel, and validationAction

> **Chapter:** Collections and Schema  
> **Module:** `SPRING_DATA_MONGODB`

MongoDB allows documents in the same collection to have different structures. This flexibility helps when data models evolve rapidly, but it does not mean an application should accept arbitrary data shapes. When multiple services write orders, a writer that accidentally omits `tenantId`, stores `totalMinor` as a String instead of a number, or writes an unsupported `status` can cause repositories to fail reading, aggregations to miscalculate totals, and updates to break. **Collection validation** pushes core invariants down to MongoDB so they apply whether the writer uses a repository, `MongoTemplate`, or the driver directly.

MongoDB lets you declare a `validator` on a collection—typically `$jsonSchema`—alongside two control options: **`validationLevel`** and **`validationAction`**. These three serve distinct roles:

- **`required`** in `$jsonSchema`: fields that must **appear** in the document or corresponding object.
- **`validationLevel`**: when MongoDB applies validator checks to insert/update commands, especially for legacy data that already violates the schema.
- **`validationAction`**: when validation detects a violation, whether the server **rejects the write** or **permits it while logging a warning**.

This lesson sits in the `SPRING_DATA_MONGODB` module, covering connection and document mapping, operating on MongoDB via `MongoTemplate` or repositories, queries, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics. The focus here is creating, operating, and testing a **collection validator** consistent with the Java model and actual stored data.

## 1. Learning Objectives

After studying this lesson, you will be able to:

1. Write `$jsonSchema` with `bsonType`, `required`, `properties`, `enum`, and numeric constraints; distinguish **missing field**, **null value**, and **wrong BSON type**.
2. Explain accurately the behavior of `strict`, `moderate`, and `off` for `validationLevel`.
3. Distinguish `validationAction: "error"` from `"warn"`, and understand the risks of using `warn` in production.
4. Create a collection with a validator, modify settings via `collMod`, read back `listCollections`, and audit legacy documents.
5. Integrate schema validation with Spring Data MongoDB without confusing it with `@Document`, `@Field`, Bean Validation, or unique indexes.
6. Write integration tests confirming the server actually rejects or permits writes across each configuration combination.
7. Plan a phased rollout that neither locks out legacy data unintentionally nor lets bad data keep accumulating.

## 2. Three Control Layers Are Three Independent Questions

Suppose the system requires every order to have `tenantId`, `orderNo`, `status`, and `totalMinor`. We need to answer:

| Component | Question It Resolves | Example |
| --- | --- | --- |
| `validator` / `$jsonSchema.required` | What does a valid document look like? | Must have `tenantId`, `orderNo`, `status`, `totalMinor` |
| `validationLevel` | Which write operations undergo validator checks? | `strict` checks even updates on invalid legacy documents |
| `validationAction` | When the validator flags a violation, how does MongoDB respond? | `error` rejects the write; `warn` allows the write while emitting a server warning |

Diagram:

```text
Application / repository / MongoTemplate / driver
                     |
                     v
              INSERT or UPDATE
                     |
                     v
         validationLevel applies?
             |                |
            No               Yes
             |                |
             v                v
      Normal write path   Evaluate validator
                              |
                        +-----+------+
                        |            |
                      Valid       Violates
                        |            |
                        v            v
                 Normal write   validationAction
                                     |
                          +----------+----------+
                          |                     |
                        error                 warn
                          |                     |
                          v                     v
                    Reject write         Written, emits warning
```

This diagram shows **validation behavior** and does not replace other independent checks. For example, an insert under `validationAction:"warn"` with a duplicate `_id` still fails due to `_id`'s unique index. Validators do not disable access control, unique indexes, write concern, or MongoDB's core invariants.

## 3. Running Dataset

Collection `orders` in a multi-tenant application stores each order as a document:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  status: "NEW",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  metadata: {
    source: "checkout",
    importedBy: "service-order"
  }
}
```

Lesson conventions:

- `_id` is a BSON String with stable values such as `"ORD-101"`, avoiding implicit conversion to ObjectId.
- `tenantId` and `orderNo` are **required** Strings; the tenant must be verified via server-side authorization.
- `status` must belong to a defined set of states, such as `NEW`, `PAID`, `CANCELLED`.
- `totalMinor` is a non-negative BSON **Int64 (long)** representing the system's smallest integer currency unit.
- `createdAt` is a BSON Date (UTC instant), unlike a String holding date text.
- `metadata` is an optional object; if present, required inner fields are checked.

This is an **illustrative lesson schema**, not a recommendation that every project use String IDs or only three statuses. In production, finalize schemas from business contracts, currency precision, data conversions, and compatibility requirements.

## 4. Building `$jsonSchema` with `required` and `bsonType`

MongoDB supports a subset/variant of JSON Schema tailored for BSON via `$jsonSchema`. Common properties include `bsonType`, `required`, `properties`, `enum`, `minimum`, and `maximum`.

A simple validator:

```javascript
const orderSchema = {
  bsonType: "object",
  required: [
    "tenantId",
    "orderNo",
    "status",
    "totalMinor",
    "createdAt"
  ],
  properties: {
    _id: {
      bsonType: "string",
      description: "Order ID per the active contract"
    },
    tenantId: {
      bsonType: "string",
      minLength: 1
    },
    orderNo: {
      bsonType: "string",
      minLength: 1
    },
    status: {
      bsonType: "string",
      enum: ["NEW", "PAID", "CANCELLED"]
    },
    totalMinor: {
      bsonType: "long",
      minimum: 0
    },
    createdAt: {
      bsonType: "date"
    },
    metadata: {
      bsonType: "object",
      properties: {
        source: { bsonType: "string" },
        importedBy: { bsonType: "string" }
      }
    }
  }
};
```

### 4.1. `required` Is an Array of Field Names, Not a Per-Property Flag

In MongoDB's `$jsonSchema`:

```javascript
{
  bsonType: "object",
  required: ["tenantId", "status"],
  properties: {
    tenantId: { bsonType: "string" },
    status: { bsonType: "string" }
  }
}
```

Both fields must be present on the **current object**. Never write:

```javascript
// ANTI-PATTERN: not valid JSON Schema required syntax.
{
  properties: {
    status: {
      required: true
    }
  }
}
```

`required` in JSON Schema is **a list of field names** on its enclosing object; if fields inside a nested object must be mandatory, declare `required` inside the **child object's** schema.

### 4.2. `required` Does Not Mean Non-Null

Example:

```javascript
{
  bsonType: "object",
  required: ["reviewerNote"],
  properties: {
    reviewerNote: { }
  }
}
```

Document `{ reviewerNote: null }` still satisfies **field presence**, because the schema does not forbid BSON null. To require **presence and a String**, combine `required` with `bsonType`:

```javascript
{
  bsonType: "object",
  required: ["reviewerNote"],
  properties: {
    reviewerNote: { bsonType: "string" }
  }
}
```

Outcomes:

| Input Value | `required` Satisfied? | `bsonType:"string"` Satisfied? | Conclusion |
| --- | --- | --- | --- |
| Missing `reviewerNote` | No | Type check skipped on absent field | Invalid |
| `reviewerNote: null` | Yes | No | Invalid |
| `reviewerNote: 123` | Yes | No | Invalid |
| `reviewerNote: ""` | Yes | Yes | Type-valid, though empty string is still allowed |
| `reviewerNote: "OK"` | Yes | Yes | Valid |

If empty strings are also unacceptable, add `minLength: 1` and whitespace-handling rules per business policy; `minLength` does not trim strings automatically.

### 4.3. Required Fields Inside Nested Objects

Suppose `metadata` is optional; however, **if `metadata` is present**, `source` is required:

```javascript
{
  bsonType: "object",
  properties: {
    metadata: {
      bsonType: "object",
      required: ["source"],
      properties: {
        source: { bsonType: "string", minLength: 1 },
        importedBy: { bsonType: "string" }
      }
    }
  }
}
```

Because `metadata` is not in the root `required` array, a document omitting `metadata` altogether is valid. Yet `metadata: {}` is invalid because it lacks `source`. This expresses **conditions inside an object** independently from requiring the outer object itself.

### 4.4. `bsonType` Is BSON, Not Java Types

Common mappings:

| MongoDB `bsonType` | BSON Example | Common Java/Spring Data Type |
| --- | --- | --- |
| `string` | `"ORD-101"` | `String` |
| `bool` | `true` / `false` | `Boolean` / `boolean` |
| `int` | BSON Int32 | `Integer` / `int` |
| `long` | BSON Int64 | `Long` / `long` |
| `double` | BSON Double | `Double` / `double` |
| `decimal` | BSON Decimal128 | `Decimal128` / `BigDecimal` with matching converter |
| `date` | BSON Date | `Instant` / `Date` with matching mapping |
| `objectId` | BSON ObjectId | `ObjectId`; `String` IDs may convert depending on annotations/mapping |
| `object` | BSON subdocument | Java object/record |
| `array` | BSON array | `List<T>` |

**Common pitfall:** JSON `150000` and Java `long` do not guarantee every writer/driver produces the same BSON type. For instance, some paths store small integers as BSON Int32, which `bsonType:"long"` rejects. To permit both Int32 and Int64 during migration, you can temporarily use `bsonType: ["int","long"]`, then standardize on one canonical type. For currency, verify exact numeric types and rounding carefully.

### 4.5. Should You Use `additionalProperties: false`?

`additionalProperties: false` forbids any field outside the schema's allowed list. It helps in systems with very tight data contracts, yet can **break compatibility** when frameworks write fields like `_class` or another service stores legitimate metadata unknown to the schema.

In this lesson, we **do not enable** `additionalProperties:false`. If you enable it, list all permitted fields including `_id` and any discriminator/mapping fields produced by Spring Data or the platform, and plan rollouts when expanding schemas. Never enable it merely to "make the schema clean" without knowing every writer.

## 5. Creating a Collection with a Validator

On the practice database `shop`, use `db.createCollection`:

```javascript
use shop

db.createCollection("orders", {
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Here `orderSchema` is the object declared in section 4, executed in the same `mongosh` session. Creation must happen **before a collection with that name exists**; if `orders` already exists, do not use `createCollection` to overwrite it. For live collections, use `collMod` after planning data changes.

Insert a valid document:

```javascript
db.orders.insertOne({
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  status: "NEW",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z")
})
```

Violating case:

```javascript
// Missing status => fails required.
db.orders.insertOne({
  _id: "ORD-BAD-1",
  tenantId: "TENANT-A",
  orderNo: "A-BAD-1",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z")
})
```

With `validationLevel:"strict"` and `validationAction:"error"`, MongoDB rejects the invalid insert. The error is typically **document failed validation**, with error code `121` in common cases; details may show which validator rule failed. Never build business logic by parsing a fixed-format error message string; use error types/codes and structured metadata where provided by the API/driver.

### 5.1. Validators Are Not Unique Indexes

Even with `orderNo` marked `required` and `bsonType:"string"`, two orders can share the same `orderNo` unless a uniqueness constraint exists. If business rules require per-tenant uniqueness:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order_no" }
)
```

This is a **separate index**. A duplicate `orderNo` fails due to the unique index even when the document completely satisfies `$jsonSchema`. If legacy data already contains duplicate keys, index creation fails until duplicates are resolved.

## 6. `validationLevel`: `strict`, `moderate`, and `off`

`validationLevel` answers: **which write commands must be evaluated against the validator?** MongoDB provides these core levels:

| validationLevel | New Insert | Update Currently **Valid** Doc | Update Currently **Invalid** Doc |
| --- | --- | --- | --- |
| `strict` | Checked | Checked | **Checked** |
| `moderate` | Checked | Checked | **Skips validator checks** for documents already invalid |
| `off` | Skips validator | Skips validator | Skips validator |

**Key point:** `moderate` **does not mean warn-only**. It controls **validation scope**. When a previously valid document is updated into an invalid state, `moderate` still checks it and handles the failure per `validationAction`.

### 6.1. `strict`: Checks All Relevant Inserts and Updates

With a collection configured as:

```javascript
{
  validationLevel: "strict",
  validationAction: "error"
}
```

A legacy document missing `status` can still **exist** if created before the validator was enabled. Yet when the application updates it, MongoDB validates the **post-update document**. If it still lacks `status`, the invalid update is rejected.

Example:

```javascript
// Assuming ORD-LEGACY was created before enabling the validator,
// without status in BSON.
db.orders.updateOne(
  { _id: "ORD-LEGACY" },
  { $set: { note: "Legacy data reviewed" } }
)
```

If the output still violates the schema, `strict + error` rejects even updating `note`. This is why migrations can hit "update path locked" errors if `strict` is turned on prematurely.

Conversely, if an update **simultaneously supplies all missing/wrong fields** so the resulting document satisfies the validator, a valid command can succeed. Thus `strict` does not mandate deleting all old documents beforehand, provided repair updates leave documents in a valid final state.

### 6.2. `moderate`: Supports Legacy Transition Periods

With:

```javascript
{
  validationLevel: "moderate",
  validationAction: "error"
}
```

MongoDB still rejects **invalid new inserts**. It also prevents **corrupting an already-valid document**. However, if a document **was already invalid prior to the update**, updates on it are not blocked by the validator under `moderate`.

Visualization:

```text
LEGACY-1 (missing status, already invalid)
   |
   +-- $set note = "processed"
   |      moderate: skips validator check
   |      => write allowed (unless blocked by another constraint)
   |
   +-- $set status = "NEW", all other fields also valid
          => document becomes valid
          => subsequent updates are checked.

ORD-101 (initially valid)
   |
   +-- $unset status
          moderate: checked because document was initially valid
          => violates required; error rejects.
```

**Risk:** `moderate` allows older writers to keep updating **invalid legacy documents** without repairing schema errors. Therefore it is only one part of a transition strategy, not an automatic data-cleaning mechanism.

### 6.3. `off`: Disables Collection Validation

`validationLevel:"off"` disables validator enforcement for those write operations. It does not remove the validator definition from the collection, but skips schema checking while active. That differs from setting `validationAction:"warn"`: `warn` still evaluates the validator and logs warnings on violations.

Do not leave `off` enabled indefinitely once a schema contract is established. When temporarily pausing validation for migration, bound the time window, restrict privileges, log changes, and monitor incoming data.

### 6.4. `validationLevel` Does Not Validate the Whole Collection Immediately

Switching to `strict` or `moderate` does not cause MongoDB to scan and fix all stored documents. Invalid documents **remain stored** until repaired or deleted; enabling a validator mainly affects **subsequent write operations**. Separate audit tools and migration plans are required.

## 7. `validationAction`: `error` and `warn`

When `validationLevel` causes an operation to be checked and it fails, `validationAction` determines the response.

### 7.1. `error`: Rejects Violations

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
})
```

For an insert/update evaluated as invalid, MongoDB rejects the change. In the driver, the write usually throws an exception, and the application must return an appropriate business error instead of acting as if the write succeeded.

Do not assume a multi-document bulk write automatically rolls back everything because one document failed the validator. A non-transactional bulk write can still succeed **partially**; validation only rejects offending operations.

### 7.2. `warn`: Permits Writes While Warning

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "warn"
})
```

When a document violates the validator:

- MongoDB **permits** the write (unless another constraint blocks it).
- The server logs a validation failure warning via its logging mechanism.
- The driver can report **write success**: the application receives no exception solely for failing the validator.

**Do not confuse `warn` with "log error and still reject."** `warn` is not a mode for blocking bad data. Thus, when introducing `warn` during rollout, include **monitoring** and a schedule to remediate data; never let it serve as the sole guard for critical data.

### 7.3. Combined Scenario Table

| validationLevel | validationAction | Violating New Doc | Updating Already-Invalid Legacy Doc | Use When |
| --- | --- | --- | --- | --- |
| `strict` | `error` | Rejected | Rejected if result remains invalid | Contract is fully enforced |
| `strict` | `warn` | Allowed, warned | Allowed, warned if result remains invalid | Observing violation rates before blocking |
| `moderate` | `error` | Rejected | Allowed because already invalid | Gradual migration, protecting new and clean data |
| `moderate` | `warn` | Allowed, warned | Allowed without validator check | Special transition phase requiring close monitoring |
| `off` | `error` or `warn` | Schema unchecked | Schema unchecked | Temporarily disabling validation under control |

This table describes **validator outcomes**, excluding duplicate key, permissions, immutable fields, or independent BSON formatting errors. Under `moderate + warn`, updating an already-invalid document does not necessarily emit a schema warning, because the operation can fall **outside evaluation scope**.

### 7.4. Note on Server Versions

`error` and `warn` are the two core actions covered here. Newer MongoDB releases may add other values/behaviors depending on server version and deployment environment; when using newer options, consult the **documentation for your exact running MongoDB version**, rather than assuming every cluster supports them.

## 8. Updating Validator and Policies with `collMod`

Existing collections must be modified via `collMod` (with appropriate privileges):

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "moderate",
  validationAction: "warn"
})
```

After auditing data and completing writer fixes:

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "moderate",
  validationAction: "error"
})
```

Once legacy data has been standardized:

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
})
```

These examples use `orderSchema` from section 4. To **change the validator**, supply a new `validator` field; to change only level/action, send just the fields being changed. Test the impact in staging: older writer versions may start failing or experience altered data semantics as validation tightens.

### 8.1. Inspecting Active Server Configuration

```javascript
db.getCollectionInfos({ name: "orders" })
```

Inspect the returned collection settings, typically `options.validator`, `options.validationLevel`, and `options.validationAction` when set. Avoid looking only at Java config files and assuming the collection is protected: migrations may not have run or an environment may have been created earlier with a different validator.

Across multiple environments, maintain a versioned **schema deployment process**, comparing the desired validator definition against the live definition in MongoDB.

### 8.2. `collMod` Does Not Fix Stored Documents

After `collMod`:

```javascript
db.orders.findOne({ _id: "ORD-LEGACY" })
```

if `ORD-LEGACY` was missing `status`, that field is still missing; `collMod` only updates **future evaluation rules**, never backfilling fields automatically. Reaching a fully strict state requires **inventorying, backfilling, normalizing, and verifying** each data group before tightening enforcement.

## 9. Updates Are Also Evaluated on the Final Document

A common misconception is that `required` only applies to `insertOne`, while a `$set` modifying a single field is exempt.

Suppose `ORD-101` is valid:

```javascript
db.orders.updateOne(
  { _id: "ORD-101", tenantId: "TENANT-A" },
  { $unset: { status: "" } }
)
```

Under `strict + error` (or `moderate + error` since `ORD-101` was valid), this command violates `required:["status"]` and is rejected. MongoDB evaluates the **document after applying the update**, not merely whether `status` appeared in `$set`.

### 9.1. `$set` null on a Required Field

```javascript
db.orders.updateOne(
  { _id: "ORD-101", tenantId: "TENANT-A" },
  { $set: { status: null } }
)
```

The `status` field still exists, passing `required`, **but violates `bsonType:"string"` and `enum`**. This shows why presence checks, BSON types, and value constraints must be combined.

### 9.2. ReplaceOne and Spring Data `save`

A replacement containing only:

```javascript
{
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  totalMinor: NumberLong(150000)
}
```

lacks `status` and `createdAt`. If used to replace a valid order, the validator rejects it when validation applies and action is `error`. Furthermore, full replacements can **drop legacy/unknown fields** if the Java entity does not map all existing fields.

Validators help reject **some** schema-invalid replacements, but **do not guarantee** preserving fields the schema does not require. When updating only `status` or metadata, prefer conditional `$set` and optimistic locking/CAS as needed; do not rely on validators to prevent lost updates.

### 9.3. Deletes and Reads Are Not Inserts/Updates

Collection validators govern **inserting new documents and updating documents**; they do not hide schema-invalid documents from `find`/aggregations, nor do they apply authorization filters. Deletion follows separate permission/retention rules. Even after enabling `strict`, legacy records remain readable, meaning downstream readers must handle null/missing fields until migration completes.

## 10. `bypassDocumentValidation`: Controlled Exceptions

Several MongoDB write commands accept `bypassDocumentValidation`. When the caller holds **appropriate privileges** and explicitly sets this option, validation can be skipped for that specific task, depending on command and server version.

Illustrative example showing how a command carries the option:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "ORD-IMPORT",
      tenantId: "TENANT-A",
      orderNo: "A-IMPORT",
      status: "NEW",
      totalMinor: NumberLong(5000),
      createdAt: ISODate("2026-11-20T04:00:00Z")
    }
  ],
  bypassDocumentValidation: true
})
```

The document in this example is **already valid** so as not to encourage writing bad data. `bypassDocumentValidation` is not a routine fix for schema errors; enabling it casually undermines the guarantees the application expects from collection validators.

Operational rules:

- Grant bypass privileges only to migration/operational roles that truly require them.
- Log who ran it, data range, purpose, and timestamp.
- Verify post-migration and **bring data into schema compliance**.
- Never enable bypass by default for repositories or `MongoTemplate` in normal APIs.

Never treat collection validation as tenant security/authorization: validators do not prove a user is permitted to modify a given `tenantId`. Authorization, tenant filters, indexes, and validators must be designed **to complement one another**.

## 11. Auditing Legacy Data Before Switching to `strict`

Before enabling `strict + error` on a long-lived collection, determine **how many invalid documents exist** and what they violate.

### 11.1. Using the Same `$jsonSchema` to Find Non-Conforming Documents

`$jsonSchema` can be used as a query predicate. With `orderSchema` defined in `mongosh`:

```javascript
// Count documents currently failing the schema.
db.orders.countDocuments({
  $nor: [
    { $jsonSchema: orderSchema }
  ]
})
```

And inspect samples to plan migration:

```javascript
db.orders.find(
  {
    $nor: [
      { $jsonSchema: orderSchema }
    ]
  },
  {
    tenantId: 1,
    orderNo: 1,
    status: 1,
    totalMinor: 1,
    createdAt: 1
  }
).limit(20)
```

`$nor` here selects **documents that fail the validator**. This command is **read-only** and does not make documents valid. On large collections, scanning fully with `$jsonSchema` can be resource-heavy: schedule it, measure cost, and sample per tenant/batch as appropriate.

### 11.2. Summarizing BSON Types of Key Fields

If `totalMinor` was variously stored as numbers, Strings, or BSON Decimal128:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        statusType: { $type: "$status" },
        amountType: { $type: "$totalMinor" }
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
])
```

The output separates `missing`, `null`, `string`, `int`, `long`, `decimal`, etc. Never assume data is clean merely because Java converters currently parse some values: MongoDB validators check the **actual BSON stored on the server**, not DTO types after conversion.

### 11.3. Do Not Backfill with Guessed Values

A document missing `status` is not necessarily in `NEW` state. It might come from an old system with another state, or be a record needing manual investigation. Before populating values:

- Identify the source of truth for `status` and `createdAt`.
- Check financial rules for `totalMinor`, currency unit, fees, and refunds.
- Flag unrecoverable records for separate handling rather than legitimizing them with fake data.
- Maintain checkpoints, before/after counts, and recovery procedures if migration fails.

Once a subset is proven to lack only information **that can be derived with certainty**, run a filtered update:

```javascript
// ONLY when proven that data from LEGACY-X
// missing status always maps to NEW.
db.orders.updateMany(
  {
    legacySource: "LEGACY-X",
    status: { $exists: false }
  },
  {
    $set: { status: "NEW" }
  }
)
```

On a collection with `strict + error`, the update still fails if the document has flaws in **other fields**. During migration, either normalize **all flawed fields together** or follow a transitional process with `moderate`/controlled bypass privileges. Avoid patching one field at a time expecting the validator to ignore remaining invalid fields.

### 11.4. Should You Convert `totalMinor` from String to Long?

Legacy document example:

```javascript
{
  _id: "ORD-OLD-2",
  tenantId: "TENANT-A",
  orderNo: "A-OLD-2",
  status: "PAID",
  totalMinor: "150000",
  createdAt: ISODate("2026-11-01T02:00:00Z")
}
```

`$toLong` or `$convert` in an update pipeline can normalize values, but **not every String converts cleanly**. Verify non-negative values, overflow risk, currency units, and error handling:

```javascript
// Use ONLY on a batch verified to contain valid Strings.
db.orders.updateMany(
  {
    totalMinor: { $type: "string" },
    legacySource: "LEGACY-X"
  },
  [
    {
      $set: {
        totalMinor: { $toLong: "$totalMinor" }
      }
    }
  ]
)
```

If a String like `"unknown"` cannot convert, the command fails. For dirty data migrations, use a **quarantine/reconciliation** flow or `$convert` with an explicit `onError` policy; **never** default failures to 0 and call it a valid monetary amount.

## 12. Incremental Rollout Strategy

For a collection with multiple writers, a phased rollout avoids breaking older services unexpectedly:

**Phase A — Survey.** Read current settings, measure schema violation rates, list all writers, finalize the canonical schema and valid exception list.

**Phase B — Update writers.** Ensure repositories, `MongoTemplate`, import jobs, and legacy services write schema-compliant documents. Add CI integration tests; check mappings for Long, Date, enum, null, and system-generated fields.

**Phase C — Observe with `warn`.** Enable `strict + warn` if the goal is to **spot every invalid new write and update**, including legacy documents. Add log/metric alerts and reconcile against audits.

**Phase D — Block bad new writes via `moderate + error`.** Once confident new writers comply, enable `moderate + error` if invalid legacy documents remain and still need updates. Updates modifying already-valid documents must still pass the validator.

**Phase E — Repair legacy data.** Run batched migrations, eliminate missing/mistyped BSON fields, re-verify via `$jsonSchema`, and reconcile business totals. Check for any un-upgraded writers.

**Phase F — Lock down `strict + error`.** Enable `strict + error` once no unhandled exceptions remain, backed by tests and an approved rollback plan. Monitor validation errors post-deploy.

These phases are a **reference roadmap**, not a mandatory sequence for every deployment. A brand-new collection with no legacy data can launch straight into `strict + error`. If sensitive data cannot tolerate bad writes even during observation, vet writers in staging and enable blocking directly rather than defaulting to `warn` in production.

### 12.1. Why Multi-Version Rollouts Are Tricky

Suppose two services write concurrently:

```text
Order Service V2: writes totalMinor as BSON Long, includes createdAt.
Order Service V1: writes totalMinor as BSON String, omits createdAt.
                 |
                 v
        Validator strict + error
                 |
             V2 succeeds
             V1 write rejected
```

Deploying the collection validator **before all writers upgrade** causes production errors in V1. Treat schema validation as a **shared system contract change**, not just a Java annotation edit.

### 12.2. Rollback Is Not "Disable and Forget"

When a validator causes an outage, rollback may involve switching `validationAction` to `warn` or temporarily adjusting `validationLevel` with operational approval, but you must:

- Record exact before/after configurations.
- Identify the window and scope of bad data written during relaxation.
- Audit and repair those documents before re-enabling enforcement.
- Prevent the rollback state from becoming permanent.

If the root cause was a misconfigured schema (e.g., accidentally forbidding `_class`), **fix the schema** and test first rather than leaving `off`.

## 13. Spring Data MongoDB: Mapping Does Not Replace Collection Validation

In Java, `@Document` names the collection, `@Id` marks the identifier, `@Field` maps properties, and Bean Validation (when configured) runs on specific application call paths. None of these annotations **automatically installs `$jsonSchema` in MongoDB**.

### 13.1. Corresponding Java Model

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String orderNo,
    String status,
    Long totalMinor,
    Instant createdAt
) {}
```

This model works well with repositories and `MongoTemplate`. Yet if code calls:

```java
OrderDocument invalid = new OrderDocument(
    "ORD-INVALID",
    "TENANT-A",
    "A-INVALID",
    null,               // status missing semantically
    150000L,
    Instant.parse("2026-11-20T02:00:00Z"));

repository.save(invalid);
```

depending on mapping/configuration, Java may omit the null field or send BSON null. Either way, with a validator requiring `status` to be a valid String, MongoDB **rejects the write** under `strict + error`. This provides server-side protection even when an application path forgets validation.

### 13.2. Bean Validation and MongoDB Validators Differ

| Criterion | Bean Validation (e.g., `@NotNull`) | MongoDB `$jsonSchema` |
| --- | --- | --- |
| Execution location | JVM, on paths invoking validation | MongoDB server, on writes within validation scope |
| Data evaluated | Java properties and constraint validators | Actual BSON stored in MongoDB |
| Protects non-Java writers? | No | Yes, unless bypassed or excluded by level |
| Does `@NotNull` install `required` on collection? | Not by default | `required` must be configured on the server |
| Checks partial updates from driver? | No unless validation is invoked manually | Yes, on post-update document when level applies |
| User-friendly error reporting | Typically maps cleanly to input fields | Server errors must be translated to business responses |

For REST APIs, application-layer validation remains essential for clear user feedback, authorization checks, and business rules inexpressible in JSON Schema. MongoDB validators are a **persistence safety net**, not a reason to drop service validation.

### 13.3. `@Id String` and `_id`'s `bsonType`

An entity with `@Id String id` can be converted by Spring Data MongoDB into a BSON ObjectId if the string matches ObjectId format under default mapping. If the collection validator requires:

```javascript
_id: { bsonType: "string" }
```

yet the writer stores `_id` as BSON ObjectId, writes will be rejected. To keep schema and Java aligned, choose an ID strategy and test raw BSON. To enforce String IDs, Spring Data offers explicit declarations such as `@MongoId`; verify target type and mapping behavior in your framework version.

### 13.4. `createdAt`: BSON Date vs. String

`Instant` is normally stored by Spring Data's converter as BSON Date under standard mapping. However, a raw JSON ingestion job might send:

```javascript
{ createdAt: "2026-11-20T02:00:00Z" }
```

That is a **String**, not a BSON Date. Under `bsonType:"date"`, the validator rejects it. When ingesting external payloads, parse dates per product timezone policies before writing; do not rely on strings that look like ISO timestamps.

## 14. Configuring Collection Validators via MongoTemplate / MongoDB Driver

Schema validation lives in the **database**, typically managed via migration/deployment scripts. Spring Data MongoDB provides schema/collection option APIs in corresponding versions; an explicit way to see the exact server commands is issuing `create` or `collMod` via `MongoTemplate.getDb().runCommand(...)`.

### 14.1. Applying Configuration to an Existing Collection

File `OrderSchemaMaintenance.java` (illustrative snippet for an authorized migration program):

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class OrderSchemaMaintenance {

    private OrderSchemaMaintenance() {}

    public static Document schema() {
        return new Document("bsonType", "object")
            .append("required", List.of(
                "tenantId", "orderNo", "status",
                "totalMinor", "createdAt"))
            .append("properties", new Document()
                .append("tenantId",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("orderNo",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("status",
                    new Document("bsonType", "string")
                        .append("enum", List.of(
                            "NEW", "PAID", "CANCELLED")))
                .append("totalMinor",
                    new Document("bsonType", "long")
                        .append("minimum", 0))
                .append("createdAt",
                    new Document("bsonType", "date")));
    }

    public static void enableStrictValidation(
            MongoTemplate template) {

        Document command = new Document("collMod", "orders")
            .append("validator",
                new Document("$jsonSchema", schema()))
            .append("validationLevel", "strict")
            .append("validationAction", "error");

        template.getDb().runCommand(command);
    }
}
```

This code does not create the collection. If `orders` does not exist yet, `collMod` is not the way to initialize it; create the collection with a validator as in section 5 or run the corresponding `create` command. If the collection exists, the migration must verify privileges, schema definition, data compatibility, and deployment versioning before calling `enableStrictValidation(...)`.

To read the current configuration in Java:

```java
Document info = template.getDb()
    .listCollections()
    .filter(new Document("name", "orders"))
    .first();

if (info == null) {
    throw new IllegalStateException(
        "Collection orders does not exist yet");
}

Document options = info.get("options", Document.class);
System.out.println(options);
```

This snippet assumes an injected `template`. `listCollections` is returned by the driver; option structure varies depending on configured options and server version. Never write sensitive details or internal schemas uncontrolled to production logs.

### 14.2. Never Run `collMod` on Every HTTP Request

`collMod` is a collection-level schema admin command, not a normal domain write. **Never** call `enableStrictValidation` inside a controller handling order creation, nor on every repository query.

Instead:

1. Manage schemas as versioned changes in a deploy/migration workflow.
2. Execute via an appropriately privileged account with logging/approval.
3. Verify `listCollections`/audits to confirm environments match the desired state.
4. Separate routine application accounts from schema administration privileges where security permits.

### 14.3. `MongoJsonSchema` and `CollectionOptions`

In supported Spring Data MongoDB versions, `MongoJsonSchema` and `CollectionOptions` let you define schemas/options via a DSL instead of manual BSON documents. However, **server semantics remain `$jsonSchema` + `validationLevel` + `validationAction`**. Always verify exact builder APIs against your Spring Data version before copying code; overloads or enum types in newer versions may differ from older ones.

This lesson intentionally shows explicit BSON commands so they compare directly with real MongoDB settings rather than assuming every Spring Data version shares the same fluent DSL.

## 15. Integration Testing Against Real MongoDB

Testing `OrderDocument` only in Java does not prove the server has a `validator`. Your model and Bean Validation may reject bad data in the JVM while another writer using the raw driver writes invalid records. **Integration tests must create/update the validator on real MongoDB**, send inserts/updates **via the raw driver**, and verify errors or stored documents.

Examples use JUnit 5, AssertJ, MongoDB Java Driver, and Spring Boot `@DataMongoTest`. Annotation packages below follow common Spring Boot 3.x conventions; verify packages/dependencies for other major versions. Configure an isolated test MongoDB (e.g., Testcontainers) with privileges to create/drop/`collMod` collections in the test database.

### 15.1. Fixtures, Schema, and Policy Helpers

File `OrderCollectionValidationIntegrationTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderCollectionValidationIntegrationTest {

    @Autowired
    MongoTemplate template;

    private MongoCollection<Document> collection() {
        return template.getCollection("orders");
    }

    private static Document schema() {
        return new Document("bsonType", "object")
            .append("required", List.of(
                "tenantId", "orderNo", "status",
                "totalMinor", "createdAt"))
            .append("properties", new Document()
                .append("tenantId",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("orderNo",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("status",
                    new Document("bsonType", "string")
                        .append("enum", List.of(
                            "NEW", "PAID", "CANCELLED")))
                .append("totalMinor",
                    new Document("bsonType", "long")
                        .append("minimum", 0))
                .append("createdAt",
                    new Document("bsonType", "date")));
    }

    private static Document validOrder(String id) {
        return new Document("_id", id)
            .append("tenantId", "TENANT-A")
            .append("orderNo", "A-" + id)
            .append("status", "NEW")
            .append("totalMinor", 150000L)
            .append("createdAt", Date.from(
                Instant.parse("2026-11-20T02:00:00Z")));
    }

    private void configure(String level, String action) {
        template.getDb().runCommand(
            new Document("collMod", "orders")
                .append("validator",
                    new Document("$jsonSchema", schema()))
                .append("validationLevel", level)
                .append("validationAction", action));
    }

    private Document findById(String id) {
        return collection()
            .find(Filters.eq("_id", id))
            .first();
    }

    @BeforeEach
    void startWithCollectionWithoutValidator() {
        // STRICTLY use an isolated TEST database only.
        collection().drop();
        template.getDb().runCommand(
            new Document("create", "orders"));
    }

    @Test
    void strictErrorAcceptsValidAndRejectsMissingRequiredField() {
        configure("strict", "error");

        collection().insertOne(validOrder("ORD-OK"));
        assertThat(findById("ORD-OK")).isNotNull();

        Document missingStatus = validOrder("ORD-NO-STATUS");
        missingStatus.remove("status");

        assertThatThrownBy(
            () -> collection().insertOne(missingStatus))
            .isInstanceOfSatisfying(
                MongoWriteException.class,
                ex -> assertThat(ex.getError().getCode())
                    .isEqualTo(121));

        assertThat(findById("ORD-NO-STATUS")).isNull();
    }

    @Test
    void requiredPlusBsonTypeRejectsNullAndWrongNumericType() {
        configure("strict", "error");

        Document nullStatus = validOrder("ORD-NULL");
        nullStatus.put("status", null);

        assertThatThrownBy(
            () -> collection().insertOne(nullStatus))
            .isInstanceOf(MongoWriteException.class);

        Document wrongAmount = validOrder("ORD-STRING-AMOUNT");
        wrongAmount.put("totalMinor", "150000");

        assertThatThrownBy(
            () -> collection().insertOne(wrongAmount))
            .isInstanceOf(MongoWriteException.class);

        Document int32Amount = validOrder("ORD-INT-AMOUNT");
        int32Amount.put("totalMinor", 150000); // Java Integer -> BSON Int32

        assertThatThrownBy(
            () -> collection().insertOne(int32Amount))
            .isInstanceOf(MongoWriteException.class);
    }

    @Test
    void strictErrorRejectsUpdatingAnAlreadyInvalidLegacyDocument() {
        // Legacy seeded BEFORE enabling validator.
        Document legacy = validOrder("ORD-LEGACY-STRICT");
        legacy.remove("status");
        collection().insertOne(legacy);

        configure("strict", "error");

        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-LEGACY-STRICT"),
            Updates.set("note", "attempted")))
            .isInstanceOf(MongoWriteException.class);

        Document stored = findById("ORD-LEGACY-STRICT");
        assertThat(stored).isNotNull();
        assertThat(stored.containsKey("note")).isFalse();
        assertThat(stored.containsKey("status")).isFalse();
    }

    @Test
    void moderateErrorAllowsUpdatingExistingInvalidLegacyDocument() {
        Document legacy = validOrder("ORD-LEGACY-MODERATE");
        legacy.remove("status");
        collection().insertOne(legacy);

        configure("moderate", "error");

        UpdateResult updated = collection().updateOne(
            Filters.eq("_id", "ORD-LEGACY-MODERATE"),
            Updates.set("note", "permitted-in-moderate"));

        assertThat(updated.getMatchedCount()).isEqualTo(1L);
        assertThat(findById("ORD-LEGACY-MODERATE")
            .getString("note"))
            .isEqualTo("permitted-in-moderate");

        // moderate still validates new INSERTS.
        Document newInvalid = validOrder("ORD-NEW-INVALID");
        newInvalid.remove("status");
        assertThatThrownBy(
            () -> collection().insertOne(newInvalid))
            .isInstanceOf(MongoWriteException.class);
    }

    @Test
    void moderateErrorStillProtectsValidDocumentsFromBecomingInvalid() {
        configure("moderate", "error");
        collection().insertOne(validOrder("ORD-VALID"));

        // Document IS valid, so updates are still checked.
        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-VALID"),
            Updates.unset("status")))
            .isInstanceOf(MongoWriteException.class);

        assertThat(findById("ORD-VALID").getString("status"))
            .isEqualTo("NEW");
    }

    @Test
    void strictWarnAllowsInvalidDocumentToBeWritten() {
        configure("strict", "warn");

        Document missingStatus = validOrder("ORD-WARN");
        missingStatus.remove("status");
        collection().insertOne(missingStatus);

        // No exception: warn does NOT block invalid writes.
        assertThat(findById("ORD-WARN")).isNotNull();
        assertThat(findById("ORD-WARN")
            .containsKey("status")).isFalse();

        // Warnings live in MongoDB server logs;
        // this test does not assume the driver returns a warning directly.
    }

    @Test
    void strictErrorRejectsUnsetOnExistingValidDocument() {
        configure("strict", "error");
        collection().insertOne(validOrder("ORD-UNSET"));

        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-UNSET"),
            Updates.unset("tenantId")))
            .isInstanceOf(MongoWriteException.class);

        assertThat(findById("ORD-UNSET")
            .getString("tenantId"))
            .isEqualTo("TENANT-A");
    }

    @Test
    void collectionOptionsAreStoredOnMongoDbServer() {
        configure("strict", "error");

        Document info = template.getDb()
            .listCollections()
            .filter(Filters.eq("name", "orders"))
            .first();

        assertThat(info).isNotNull();
        Document options = info.get("options", Document.class);
        assertThat(options).isNotNull();
        assertThat(options.getString("validationLevel"))
            .isEqualTo("strict");
        assertThat(options.getString("validationAction"))
            .isEqualTo("error");
        assertThat(options).containsKey("validator");
    }
}
```

**Mandatory warning:** `collection().drop()` in `@BeforeEach` **deletes the entire `orders` collection in the connected database**. Only run when the test profile is guaranteed to target an **isolated** MongoDB/database not shared with other developers and never pointing at production. If tests run in parallel against the same database, drops will collide; configure test isolation per class/job.

Here we do not assert MongoDB server log contents in the `warn` test because validator warnings happen server-side. In production, configure log/metric monitoring properly rather than treating a successful insert as proof the validator approved the data per contract.

### 15.2. What the Tests Prove

| Test | Verification Guarantee |
| --- | --- |
| `strictErrorAcceptsValid...` | Schema-compliant doc writes; missing required field rejected |
| `requiredPlusBsonType...` | `null`, String, and Int32 are not accepted as valid BSON String/Long |
| `strictErrorRejectsUpdating...` | Invalid legacy doc checked by strict on update |
| `moderateErrorAllowsUpdating...` | Invalid legacy doc can update under moderate, yet invalid new inserts still blocked |
| `moderateErrorStillProtects...` | Valid doc cannot be updated into an invalid state |
| `strictWarnAllowsInvalid...` | Warn does not block violating writes |
| `strictErrorRejectsUnset...` | Updates must also preserve required fields |
| `collectionOptionsAreStored...` | Real server settings hold validator, level, and action |

### 15.3. Testing the Spring Data Application

Once raw-driver tests confirm the server works, add tests invoking `MongoTemplate.insert(...)` or `OrderRepository.save(...)` with valid/invalid entities. Example:

```java
OrderDocument valid = new OrderDocument(
    "ORD-SPRING",
    "TENANT-A",
    "A-SPRING",
    "NEW",
    50000L,
    Instant.parse("2026-11-20T02:00:00Z"));

template.insert(valid);

Document stored = template.getCollection("orders")
    .find(new Document("_id", "ORD-SPRING"))
    .first();

assertThat(stored).isNotNull();
assertThat(stored.get("totalMinor"))
    .isInstanceOf(Long.class);
assertThat(stored.get("createdAt"))
    .isInstanceOf(Date.class);
```

This snippet is **part of a test placed in the right context**, with `template`, `OrderDocument`, `Instant`, `Date`, and `assertThat` imported. The test can fail if the real converter behaves differently than expected; that is the point—to verify that BSON written by the application satisfies the validator.

### 15.4. Additional Test Matrix

| Case | Expectation |
| --- | --- |
| `required` with empty String field | `required` passes; `minLength` needed to reject empty |
| Optional field set to null | Depends on field schema; optional does not mean null is valid |
| `metadata` object with nested required field | Missing child field must be blocked when object exists |
| `_id` field converted by mapper | Raw BSON and schema must align |
| ISO date String instead of BSON Date | Rejected with `bsonType:"date"` |
| `status` outside enum | Rejected when validation applies and action is error |
| Negative `totalMinor` | Rejected by `minimum:0` |
| `moderate` updates legacy from invalid to valid | Document can be repaired; subsequent updates must satisfy schema |
| `off` allows invalid write | Proves validator no longer blocks under off |
| `strict+warn` updates invalid document | Written, logs warning when checked and violating |
| Writer with bypass privilege | Used only when authorized and audited |
| Bulk write of multiple docs with one invalid | Does not roll back whole bulk without a transaction |
| Changing `collMod` across tests/environments | Re-read level/action rather than assuming |

## 16. Handling Server Errors in Java Services

Under `validationAction:"error"`, writes are rejected on the server. Depending on whether you call the raw driver, `MongoTemplate`, or repositories, the application may catch different exception classes due to **Spring Data exception translation**.

Therefore, services should:

1. Identify validation failures using **structured details** provided by the driver/Spring (such as server error code `121` when present), rather than matching exact error message text.
2. Never report success or emit business success events when the insert/update failed.
3. Return an appropriate client error reflecting schema failure without leaking sensitive internal validators.
4. Preserve IDs/correlation IDs to investigate offending writers; log safely.
5. Distinguish validation errors from duplicate key `11000`, write concern failures, network timeouts, and optimistic-lock conflicts; each requires distinct handling.

### 16.1. An Anti-Pattern to Avoid

```java
// ANTI-PATTERN: catching every write error and treating it as duplicate ID.
try {
    repository.save(order);
} catch (RuntimeException ex) {
    throw new IllegalArgumentException(
        "Order already exists", ex);
}
```

This conflates duplicate keys, validators, connectivity, and operational failures. A request missing `status` is not "order already exists." Classify errors properly rather than assuming every MongoDB write exception represents the same conflict.

### 16.2. Never Log Full Failing Documents

Validator details can include field names or offending data fragments. Restrict logs to internal identifiers, error categories, and correlation IDs; never dump payloads containing personal data, tokens, or sensitive fields into unredacted monitoring logs.

## 17. Common Misconceptions About Schema Validation

| Misconception | Reality |
| --- | --- |
| `required: ["status"]` forbids null | `required` only mandates field presence; use `bsonType`/constraints to forbid null |
| Having `properties.status.bsonType:"string"` makes it required | `properties` checks type when present; add `status` to `required` to forbid absence |
| `validationLevel:"moderate"` only logs and allows all writes | Moderate controls **which updates are checked**; `validationAction` controls reject vs. warn |
| `moderate + error` allows invalid new inserts | New inserts are still checked and rejected |
| `moderate + error` never blocks updates | Updates on already-valid documents are still checked |
| `strict` automatically fixes legacy documents | No; it applies rules to subsequent writes |
| `warn` rejects invalid writes and logs | `warn` allows violating writes while logging warnings |
| `validationLevel:"off"` removes the schema from the collection | The validator remains defined, while validation checks are skipped |
| Only `insert` is validated, `$set` is exempt | Updates in validation scope are evaluated on the post-write document |
| `@Document` installs a server validator | No; explicit collection configuration is required |
| `@NotNull` protects non-Java writers | No; Bean Validation runs in the JVM along invoked paths |
| `bsonType:"long"` accepts any integer | It only accepts BSON Int64, not Int32 or String |
| Validator ensures `orderNo` uniqueness | Uniqueness is the responsibility of a unique index |
| Validator ensures callers only write their own tenant | Authorization and tenant-scoped queries must be implemented separately |
| Enabling `additionalProperties:false` is always better | Can block `_class`, extensible metadata, and valid producers |
| Driver returning insert success means validator passed | Under `warn`, invalid writes can still succeed |
| Running `collMod` means old documents are valid | Separate auditing, migration, and verification are required |

### 17.1. Defaults Should Not Be Left Implicit

When options are omitted, MongoDB applies server defaults for validation level/action; standard deployments default to `strict` and `error`. Still, deployment scripts and migrations should **specify both options explicitly** so reviewers never have to guess, and **read back collection settings**.

### 17.2. BSON Validators Are Not Arbitrary Web JSON Schemas

MongoDB `$jsonSchema` uses JSON Schema adapted for BSON and the keyword subset supported by your server version. Never paste a schema from an HTTP JSON Schema tool expecting every keyword to work in MongoDB. For example, `bsonType` is BSON-specific; several standard JSON Schema keywords are unsupported or behave differently.

When generating schemas from Java, inspect the BSON output, enums/nested types, and real behavior in integration tests. Never trust a schema-generator class name without inspecting the actual validator on MongoDB.

## 18. Performance, Indexes, and Deployment Limits

Server-side validation adds work to checked insert/update operations. The more complex the schema, the larger the document, and the higher the write rate, the more noticeable validation overhead can become. **There is no universal rule that validation is always negligible or always slow**; measure on representative workloads.

### 18.1. What to Measure

- Insert/update/replace throughput and latency before and after enabling the validator.
- Validator error rates by collection, writer, service version, and violating field.
- Remaining invalid legacy count and backfill throughput.
- Bulk write overhead and **partial success** rates when one operation fails.
- Impact of new collection schemas on migrations, imports, and batch data jobs.
- Document sizes, array/object nesting depth, and number of validated fields.

### 18.2. Validators Do Not Replace Indexes

A rule requiring `tenantId` to be a non-empty String **does not speed up querying by tenant**. If an API frequently queries:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
})
```

design indexes for the read pattern, such as candidate:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
)
```

This is an index for **query performance**, not a schema validator. Weigh write overhead when adding indexes and verify with `explain("executionStats")` on representative data.

### 18.3. Schema Checks Do Not Guarantee Multi-Document Consistency

If creating an Order also writes a Payment in another collection, each validator checks only **documents in its own collection**. It does not guarantee both writes commit together. For multi-document atomicity, design MongoDB transactions (when supported by your deployment) or an appropriate eventual-consistency/outbox mechanism.

Validators also do not update `@Version`, prevent lost updates across writers, or enforce business state transitions. Those require expected-version/CAS, transactions, or service-level state machines.

### 18.4. Overly Strict Schemas Can Block Data Evolution

Suppose a new service adds a `shippingPreferences` field. If the validator sets `additionalProperties:false` without permitting the new field, that service's writes will fail. When evolving schemas:

1. Plan compatibility for **old readers / new writers**.
2. Expand the schema to allow new fields before writers start emitting them.
3. Retain old fields during transition.
4. Backfill and test data if new `required` constraints are added.
5. Tighten the schema only once all writers and readers are coordinated.

This is the **expand → migrate → contract** approach, well suited when multiple services share a collection.

## 19. Operational Checklist Before Enabling `strict + error`

1. **Clear contract:** define required fields, optional fields, nullability, enums, BSON types, and currency units.
2. **Existing schema audited:** know how many documents are missing/null/mistyped and which writers produced them.
3. **Real collection verified:** `listCollections` matches the intended migration configuration.
4. **Null vs. missing distinguished:** both `required` and `bsonType` tested.
5. **Nested objects accounted for:** `required` placed at the right nesting level without accidental expansion.
6. **Legacy plan ready:** know which updates `strict` would block and how data will be repaired.
7. **All writers aligned:** Java repositories, raw driver, imports, batch jobs, integrations, operational scripts.
8. **Regression tests present:** insert, update, replace, bulk, null, wrong BSON, strict/moderate/warn.
9. **Warn monitoring active:** never rely solely on driver write-success statuses.
10. **Bypass privileges controlled:** normal accounts cannot bypass validation arbitrarily.
11. **Unique/indexes distinguished:** validators do not enforce business key uniqueness.
12. **Controlled rollback ready:** know how to revert policy and audit data written during the rollback window.
13. **Schema evolution path defined:** write new fields, backfill, and drop old fields in proper order.
14. **Write cost measured:** verify validation overhead is acceptable under realistic load.
15. **Never test on production:** especially tests invoking `drop()`, `deleteMany`, or `collMod`.

## 20. Applied Exercises

An inventory system uses collection `stock_movements`. Each document has the shape:

```javascript
{
  _id: "MOVE-001",
  tenantId: "TENANT-X",
  sku: "SKU-001",
  movementType: "IN",
  quantity: NumberLong(10),
  occurredAt: ISODate("2026-11-20T02:00:00Z"),
  source: {
    system: "warehouse",
    batchId: "IMPORT-18"
  }
}
```

Requirements:

1. Write `$jsonSchema` requiring `tenantId`, `sku`, `movementType`, `quantity`, `occurredAt`. Require `tenantId/sku` to be non-empty Strings, `quantity` to be a positive BSON Int64, and `occurredAt` to be a BSON Date.
2. Restrict `movementType` to `IN`, `OUT`, `ADJUST`. Explain why `required` does not replace `enum`.
3. `source` may be omitted; if present, require `source.system`. Place `required` at the right nesting level.
4. Create the collection with `validationLevel:"strict"`, `validationAction:"error"`.
5. Try inserting documents missing `sku`, with `sku:null`, `sku:""`, `quantity:"10"`, and `quantity:NumberLong(-1)`. Predict which constraint fails each.
6. Suppose before enabling the validator a document existed missing `movementType`. Compare `strict+error` and `moderate+error` when running `$set:{note:"reviewed"}` on that document.
7. Use `collMod` to switch to `strict+warn`, try writing an invalid document, and explain why the driver can report success.
8. Write an audit query using `$nor + $jsonSchema` to count schema-violating documents.
9. Write a `MongoTemplate` migration helper to switch level/action; read back options to confirm server configuration.
10. Write integration tests covering valid documents, wrong types, invalid legacy records, and updates removing required fields; ensure they run against a test database.
11. Design a multi-version rollout where an older warehouse service writes `quantity` as BSON Int32 and a newer service writes BSON Int64.
12. Propose an appropriate unique key/index if `movementId` must be unique per tenant, and explain why a validator cannot replace an index.

### 20.1. Suggested Schema

```javascript
const movementSchema = {
  bsonType: "object",
  required: [
    "tenantId", "sku", "movementType", "quantity", "occurredAt"
  ],
  properties: {
    tenantId: { bsonType: "string", minLength: 1 },
    sku: { bsonType: "string", minLength: 1 },
    movementType: {
      bsonType: "string",
      enum: ["IN", "OUT", "ADJUST"]
    },
    quantity: { bsonType: "long", minimum: 1 },
    occurredAt: { bsonType: "date" },
    source: {
      bsonType: "object",
      required: ["system"],
      properties: {
        system: { bsonType: "string", minLength: 1 },
        batchId: { bsonType: "string" }
      }
    }
  }
};
```

This schema specifies positive `quantity` for all movement types. If `ADJUST` needs negative values, update the contract to validate conditionally by `movementType` or introduce a separate `direction` field. Never change `minimum:-999999` just to make tests pass without settling the business meaning.

## 21. References

- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/): overview of validating documents on write.
- MongoDB Manual — [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/): `strict`, `moderate`, and behavior on legacy documents.
- MongoDB Manual — [Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/): how MongoDB reacts to validator violations.
- MongoDB Manual — [`$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/): schema syntax and keywords.
- MongoDB Manual — [`db.createCollection()`](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): creating collections with validators and options.
- MongoDB Manual — [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/): modifying collection configurations.
- MongoDB Manual — [`bypassDocumentValidation`](https://www.mongodb.com/docs/manual/core/schema-validation/bypass-document-validation/): document validation bypass and privileges.
- Spring Data MongoDB — [Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): `MongoTemplate`, mapping, collection schemas, and MongoDB integration.
- Spring Data MongoDB — [MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): executing data operations, database access, and related APIs.

## Key Takeaways

**`required` defines which fields must exist; `validationLevel` determines which inserts/updates are checked; `validationAction` determines whether violations are rejected or only warned.** In MongoDB, `required` **does not automatically forbid null** without a type constraint; `strict` evaluates updates even on invalid legacy documents, whereas `moderate` permits updating already-invalid documents without applying validator checks, while still checking new inserts and updates to valid documents. `warn` allows violating writes and never replaces `error`. With Spring Data MongoDB, always verify real BSON, apply validators via controlled migrations, audit/backfill legacy data, and confirm server configuration before enabling strict policies in production.
