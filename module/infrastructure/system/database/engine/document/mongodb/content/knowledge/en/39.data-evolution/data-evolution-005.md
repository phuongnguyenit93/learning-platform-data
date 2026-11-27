# Enforcing New Constraints After Cleaning Legacy Data in MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Data Evolution  
> **Lesson:** Enforcing New Constraints After Cleaning Legacy Data

## 1. The Problem: Existing Data Does Not Conform to the New Contract

An order system has operated for several years with an `orders` collection. Initially, the application allowed flexible documents:

```javascript
// Document written by the old application version
{
  _id: ObjectId("66a000000000000000000427"),
  tenantId: "TENANT-01",
  externalOrderId: "ORD-100",
  status: "paid",
  amountCents: "150000",
  email: null
}

// Document written by the new application version
{
  _id: ObjectId("66a000000000000000000428"),
  tenantId: "TENANT-01",
  externalOrderId: "ORD-100",
  status: "PAID",
  amountCents: NumberLong("150000"),
  email: "customer@example.test",
  schemaVersion: NumberInt(2)
}
```

Both documents carry the **same order key** within one tenant. They also differ in BSON types and enum values. Going forward, the engineering team wants to guarantee:

1. `externalOrderId` is a non-empty String and **unique per tenant**.
2. `status` belongs strictly to `CREATED`, `PAID`, or `CANCELLED`.
3. `amountCents` is BSON Int64, non-negative, and unrounded.
4. `tenantId` is mandatory.
5. Legacy data must retain its true business meaning—never deleted or misconverted just to pass a validator.

Trying immediately:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

fails due to duplicate keys. Meanwhile, adding a `strict + error` validator causes APIs updating legacy documents to start throwing `DocumentValidationFailure`, **even though MongoDB does not automatically inspect or repair old documents merely by adding a validator**.

This lesson centers on one operational question:

> **How do you transition a collection with existing legacy data and continuous write traffic onto a new data contract, ensuring no new bad data enters, no existing data is lost, and recovery remains possible if an incident occurs?**

The answer is not “run constraint DDL right after one `updateMany`”; it is **define rules → audit → block new violations → clean legacy data in batches → re-verify → tighten constraints → monitor**.

### 1.1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish MongoDB constraint layers: `$jsonSchema`, unique/partial unique indexes, TTL, shard-key rules, and cross-document business invariants outside the database.
- Audit existing data for missing fields, `null`, wrong BSON types, invalid enums, and duplicate keys.
- Determine authority for “fix,” “merge,” “quarantine,” or “retain” rather than deleting arbitrarily.
- Build an **expand–migrate–contract** workflow while multiple app versions coexist.
- Guard against races where fresh bad data arrives while a backfill is still running.
- Use `prepareUnique` → `dryRun` → `unique` to convert an existing index to unique on supported MongoDB versions.
- Stage `validationAction:"warn"/"error"` and `validationLevel:"moderate"/"strict"` across rollout phases.
- Understand MongoDB 9.0's `validationLevel:"constraint"` and its version boundaries.
- Design idempotent, compare-and-set, batched migrations with metrics and crash resumability.
- Handle null/missing, collation, compound keys, sharded collections, TTL, and sensitive data.
- Practice the entire workflow on an **isolated MongoDB test namespace** with scoped cleanup.
- Plan risk assessment, rollout, monitoring, and rollback/forward-fix strategies.

## 2. What Counts as a “Constraint” in MongoDB?

In relational databases, engineers are used to `NOT NULL`, `UNIQUE`, `CHECK`, and `FOREIGN KEY`. MongoDB offers partial equivalents, though the boundaries are not identical.

| Requirement | MongoDB Tool | Notes |
| --- | --- | --- |
| Required field presence | `$jsonSchema.required` | `required` **does not forbid null by itself** |
| Exact BSON type | `$jsonSchema.properties.<field>.bsonType` | `int` differs from `long`, `double`, `decimal` |
| Enum or value bounds | `enum`, `minimum`, `maximum`, `minLength` | Enforced only on validated operations |
| Nested object/array shape | `properties`, `items`, `minItems` | Check null/missing arrays and mixed types |
| Uniqueness across documents | Unique index | Specific rules for null/missing/collation/sharding |
| Uniqueness over a subset | Partial unique index | Constrains only documents matching filter |
| Automatic data expiration | TTL index | A deletion policy, not merely schema validation |
| Safe conditional updates | Atomic updates, version/CAS | Essential under competing writers |
| Cross-document invariants | Transactions / business logic | Validators do not enforce foreign keys |
| Tenant access control | RBAC + application authorization | Never infer authorization from validators |

### 2.1. Structural Constraints vs. Business Constraints

Example:

```javascript
{
  amountCents: NumberLong("150000"),
  status: "PAID",
  tenantId: "TENANT-01"
}
```

A validator can prove `amountCents` is a non-negative Int64. It cannot prove a real payment settled or that the total matches line items in another collection. An invariant like “no order is marked paid twice” requires unique business IDs, transactions, idempotency, and external payment reconciliation.

### 2.2. “Clean Data” Must Be Defined Against the Target Constraint

There is no absolute “clean.” String `"42"` is valid as an identifier, invalid if the contract demands BSON Int64. Email `null` may be valid if optional, or a violation if mandatory.

Before migrating, write down:

- Which fields are required?
- Do missing and explicit `null` carry different meanings?
- Which BSON types are accepted?
- Is uniqueness global, per-tenant, or restricted to active records?
- Are legacy exceptions preserved?
- What constitutes an un-auto-fixable error?
- What are the cutover criteria for the new constraints?

If you cannot answer these yet, **do not run bulk updates or unique index builds**.

## 3. Initial State: Mapping Data Before Mutating It

### 3.1. Transformation Flow

```text
                       Existing Collection
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
            Audit shape                Audit uniqueness
      missing/null/type/enum        duplicate/collation/tenant
                 |                             |
                 +--------------+--------------+
                                |
                         Business Policy
                     fix / merge / quarantine
                                |
                      Block new bad writes
                   app writer + validator/index
                                |
                       Controlled backfill
                                |
                    Independent reconciliation
                                |
                   Enable final target constraints
                                |
                   Monitoring and rollback plan
```

Separate **detection**, **business adjudication**, and **remediation execution**. DBAs should never decide “the second record is a duplicate so delete it” when data involves payments, ledgers, or legal audit trails.

### 3.2. Scoped Metadata Collection

On an authorized database and collection:

```javascript
const d = db.getSiblingDB("commerce");
const c = d.getCollection("orders");

printjson({
  database: d.getName(),
  collection: c.getName(),
  countEstimate: c.estimatedDocumentCount(),
  indexes: c.getIndexes()
});

printjson(d.getCollectionInfos({ name: "orders" }));
```

Record:

- MongoDB server version, FCV, and topology.
- Index key patterns, unique/partial/sparse/TTL flags, collations, and index names.
- Current validator, `validationLevel`, and `validationAction`.
- Sharding status, shard key, and chunk/data distribution.
- Document count and growth rate.
- Read/write p95/p99, write errors, CPU/RAM/IOPS/free disk, and replication lag.
- All applications, batch jobs, ETLs, and admin scripts with write access.
- Backup/PITR procedures and restore drill status.

`estimatedDocumentCount()` is a metadata **estimate**; never substitute it for exact count reconciliation when accuracy matters.

### 3.3. Inventory Coexisting Schema Versions

Document evolution might look like:

| Version | Data | Writer |
| --- | --- | --- |
| v1 | `status:"paid"`, `amount:"1500"` | Old application |
| v2 | `status:"PAID"`, `amountCents:Int64` | New API |
| v2-beta | `amountCents:Double` | Buggy import job |
| Unversioned | Missing fields | Archive/legacy data |

`schemaVersion` is application-managed metadata. When old documents lack it, never infer versions solely from a single field if multiple similar shapes exist.

### 3.4. Check Permissions and Scope

Test collections are the right place to learn; production requires change owners and approvals. Never create test data in `admin`/`local`/`config`. Never dump entire customer documents into logs. Audits should record aggregate counts and masked sample IDs.

## 4. Auditing Missing Fields, `null`, and Wrong BSON Types

### 4.1. `null` and Missing Are Not Identical

Dataset:

```javascript
[
  { _id: "missing" },
  { _id: "explicit-null", externalOrderId: null },
  { _id: "empty", externalOrderId: "" },
  { _id: "valid", externalOrderId: "A-100" },
  { _id: "wrong-type", externalOrderId: NumberInt(100) }
]
```

Queries:

```javascript
// Matches both missing and explicit null in scalar fixtures:
db.orders.find({ externalOrderId: null });

// Only when the field does not exist:
db.orders.find({
  externalOrderId: { $exists: false }
});

// Field present, including null:
db.orders.find({
  externalOrderId: { $exists: true }
});

// Actual BSON null in scalar fixtures:
db.orders.find({
  externalOrderId: { $type: "null" }
});
```

To audit dirty data, count separately:

1. Missing.
2. Explicit null.
3. Empty String.
4. Whitespace-only String.
5. Non-String types.
6. Valid Strings with duplicate business keys.
7. Strings violating casing/Unicode contracts.

Never treat `{externalOrderId:null}` as a count of explicit nulls alone.

### 4.2. Counting Missing Fields and Wrong Types

```javascript
const missingId = c.countDocuments({
  externalOrderId: { $exists: false }
});

const explicitNullId = c.countDocuments({
  externalOrderId: { $type: "null" }
});

const emptyId = c.countDocuments({
  externalOrderId: ""
});

printjson({
  missingId,
  explicitNullId,
  emptyId
});
```

On collections with array fields, `$type` in queries can match **array element** types. Combine top-level BSON type checks with validators to avoid conflating cases.

### 4.3. Inspecting BSON Type Distribution via Aggregation

```javascript
c.aggregate([
  {
    $group: {
      _id: { $type: "$amountCents" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

The aggregation **`$type`** operator returns `"missing"` for absent fields, `"null"` for BSON Null, and `"int"`, `"long"`, `"double"`, `"decimal"`, or `"string"` matching the stored BSON type.

This aggregation can scan large datasets; in production:

- Run during off-peak hours or against a suitable analytical replica/snapshot.
- Partition by tenant/time/`_id` if needed.
- Set `maxTimeMS` and monitor I/O.
- Avoid scheduling overlapping full scans every minute.
- Store aggregate counts rather than raw PII.

### 4.4. Auditing Enums

```javascript
c.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

You may uncover `PAID`, `paid`, `Paid`, `SETTLED`, `" "`, `null`, and missing. Never blindly run `$toUpper` across the database and declare data clean: `SETTLED` may differ in meaning from `PAID`, and historical statuses may not exist in the new enum.

### 4.5. Auditing Against the Target Validator

Once an agreed **target validator** exists, find non-conforming documents:

```javascript
const targetValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      }
    }
  }
};

// On a properly scoped collection:
c.find({
  $nor: [targetValidator]
}).limit(20);

const totalInvalid = c.countDocuments({
  $nor: [targetValidator]
});
```

`$nor` negates the `$jsonSchema` query predicate, assessing **document-level validity**. Still, counting across very large collections is scan-heavy; budget counts per capacity plan.

**Never use invalid-doc queries to infer uniqueness**: `$jsonSchema` evaluates each document individually and knows nothing about duplicate keys across records.

## 5. Auditing Duplicate Keys Before Creating a Unique Index

### 5.1. Define the Business Key

Requirement example: no two orders in the same tenant may share `externalOrderId`.

The key must be:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

rather than:

```javascript
{ externalOrderId: 1 }
```

if different tenants can use the same `ORD-100` code.

### 5.2. Auditing Duplicates with Aggregation

```javascript
c.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      exampleId: { $first: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 50 }
], { allowDiskUse: true });
```

This is an **illustrative audit**, not something to fire unthrottled on production. `$group` scans the collection, consuming CPU/RAM/temp disk; output can also include null/missing keys and wrong-type records.

Avoid unbounded `$push:"$_id"` on groups with millions of duplicates; BSON documents have size limits. To collect IDs, partition by group/batch or query per flagged key.

### 5.3. Key Normalization and Collation Issues

Three Strings:

```text
"  ORD-100 "
"ord-100"
"ORD-100"
```

might represent the same business ID **if** the contract specifies trim + uppercase; MongoDB's default binary string comparison does not enforce business normalization automatically.

Two options:

- **Canonical field:** store `externalOrderIdCanonical` normalized via a versioned algorithm, and enforce uniqueness on it.
- **Collation index:** use a matching collation when case/accent comparison fits supported collation rules.

Before adopting collation, test Unicode, locales, whitespace trimming, normalization, and diacritics. Collation does not replace all business normalization.

### 5.4. Duplicates Do Not Mean “Delete”

Suppose two orders share a key yet point to different payment references:

```javascript
[
  {
    _id: ObjectId("66a000000000000000000427"),
    tenantId: "T-1",
    externalOrderId: "ORD-100",
    paymentId: "PAY-A",
    status: "PAID"
  },
  {
    _id: ObjectId("66a000000000000000000428"),
    tenantId: "T-1",
    externalOrderId: "ORD-100",
    paymentId: "PAY-B",
    status: "PAID"
  }
]
```

There is not enough context here to tell whether this was a duplicate retry or two distinct transactions assigned the same ID. Involve the domain owner, payment ledger, audit trail, and reconciliation/compensation processes.

## 6. Classifying Errors and Deciding Remediation

A helpful remediation matrix:

| Category | Example | Remediation Requiring Verification |
| --- | --- | --- |
| Safely convertible value | `amountCents:"1500"` confirmed as cents | Parse String → Int64 with range checks |
| Well-defined enum casing | `"paid"` proven equal to `"PAID"` | Versioned mapping with logging |
| Missing required field derivable from source | `tenantId` traceable from authoritative account | Backfill from source, verify ownership |
| Missing undeterminable field | No order code exists anywhere | Quarantine / manual decision |
| Duplicate key for same business record | Retry created two copies of one order | Reconcile/pick canonical with references |
| Duplicate key across distinct records | Two separate payments share external ID | Assign distinct IDs / adjust contract with owner |
| Anomalous financial values | Negative amount or unknown currency unit | Investigate; never coerce to 0 to “pass” |
| Ambiguous date string/timezone | `"14/11/26"` | Confirm locale/zone; never guess |
| Sensitive garbage fields | Tokens/PII inside notes | Remediate per security policy |
| Retained legacy exceptions | Archived events outside current schema | Versioned validator or separate collection |

### 6.1. Three Remediation Outcomes

Every record should land in one of three auditable states:

1. **FIXED:** converted under an explicit rule with reconciled values.
2. **QUARANTINED:** lacking evidence; routed to manual review or tagged appropriately so it does not pollute the new contract.
3. **BLOCKED:** prerequisites for enabling the constraint are unmet; do not force rollout.

“Quarantine” does not always mean moving documents to another collection. If moving, use a transactional/cutover protocol to preserve references—never `deleteMany` by gut feeling.

### 6.2. Never Fudge Data Just to Make Metrics Look Clean

Wrong:

```javascript
// DO NOT run on real data:
db.orders.updateMany(
  { amountCents: { $exists: false } },
  { $set: { amountCents: NumberLong(0) } }
);
```

Setting 0 corrupts revenue figures and changes business meaning.

Better: verify authoritative sources, currency units, valid ranges, lineage, and policy; if unknown, send records to manual review and **hold the contract cutover**.

## 7. Defining the Target Contract with `$jsonSchema`

### 7.1. A Clear Validator

Example target schema:

```javascript
const targetOrderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1,
        maxLength: 100
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      },
      email: {
        bsonType: ["string", "null"]
      },
      createdAt: {
        bsonType: "date"
      }
    }
  }
};
```

Key details:

- `required` checks field presence; **it does not disallow null**.
- `amountCents` accepts only BSON Int64, rejecting Int32/Double/String.
- `email` is optional, yet if present must be String or BSON Null.
- `createdAt` is optional here; if mandatory, add it to `required`.
- Fields unlisted in `properties` remain permitted because `additionalProperties:false` is omitted.
- Never lock down unknown fields before auditing `_id`, `schemaVersion`, and legacy client metadata.

### 7.2. Required vs. Nullable Are Independent Choices

| Schema | Missing | Explicit Null | String |
| --- | --- | --- | --- |
| Optional `bsonType:"string"` | Valid | Rejected | Valid |
| Required `bsonType:"string"` | Rejected | Rejected | Valid |
| Optional `bsonType:["string","null"]` | Valid | Valid | Valid |
| Required `bsonType:["string","null"]` | Rejected | Valid | Valid |

Before cleaning, ask: **are `null` fields actually errors?** If not, avoid replacing them with empty Strings that collide in unique indexes.

### 7.3. Currency and Numeric Types

If data contains:

```javascript
{ amountCents: NumberInt(1500) }
{ amountCents: NumberLong("1500") }
{ amountCents: NumberDouble("1500") }
{ amountCents: "1500" }
```

and the contract demands `bsonType:"long"`, migrate the other three shapes. Never use `NumberLong(parseFloat(...))` on values exceeding JavaScript's safe integer range. For money, evaluate decimal representations, units, and value bounds.

### 7.4. Arrays and Nested Objects Need Dedicated Rules

Example orders with line items:

```javascript
{
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ]
}
```

Can extend the target:

```javascript
const lineRules = {
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "object",
    required: ["sku", "quantity"],
    properties: {
      sku: {
        bsonType: "string",
        minLength: 1
      },
      quantity: {
        bsonType: "int",
        minimum: 1
      }
    }
  }
};
```

Legacy `lines:[]`, `lines:null`, or `lines:[{quantity:"2"}]` will fail. This raises the **compatibility bar**; never bundle it with other constraints before auditing.

### 7.5. `$jsonSchema` Does Not Enforce Uniqueness

Two individually valid documents can still share the same `externalOrderId`. Validators are **document-level constraints**; unique indexes enforce uniqueness across records.

## 8. Sequencing Changes Under Continuous Write Traffic

### 8.1. Why Audit-Then-Cleanup Alone Fails

```text
T0: Audit -> finds 40 duplicate groups
T1: Migration resolves 40 groups
T2: Old app inserts a new duplicate
T3: create unique index -> duplicate key error
```

Even with a flawless T1 migration, the data became dirty again. This is the **race between cleanup and ongoing writes**.

### 8.2. The “Lock the Door, Then Clean the House” Principle

To reach the target state:

1. Deploy writers obeying the new contract, including batch jobs/importers.
2. Enable server-side guards blocking new violations as early as possible.
3. Only then clean historical violations.
4. Re-audit data while live writes continue.
5. Finalize constraints with server-side race protection.
6. Keep monitoring because rare code paths can surface days later.

For an **already-existing non-unique index**, `prepareUnique` (MongoDB 6.0+) blocks new duplicate keys while legacy duplicates remain. For schemas, `validationLevel:"moderate"` + `validationAction:"error"` blocks new invalid inserts and prevents valid documents from becoming invalid, while permitting updates that repair already-invalid documents.

### 8.3. Not Every Constraint Has a Built-In “Prepare” Mode

If no matching non-unique index exists yet, you can:

- Build the non-unique index first per supported process;
- inspect data;
- finalize uniqueness once zero duplicates exist;
- or schedule a write quiesce/pause window if races cannot otherwise be eliminated.

Never rely on application-level `findOne` followed by `insertOne` for uniqueness: two concurrent requests both see zero matches and insert duplicates. You need a unique index or an equivalent atomic protocol.

## 9. Converting a Non-Unique Index to Unique with `prepareUnique`

### 9.1. Version and Index Prerequisites

MongoDB **6.0+** supports converting an existing non-unique index to unique via `collMod`.

Operational prerequisites:

- Existing index has a known key pattern and name.
- Not an unsupported index/time-series case for `prepareUnique`.
- Satisfies topology unique index rules, especially on sharded collections.
- Existing duplicates may remain while `prepareUnique:true`; resolve all duplicates before finalizing.
- Do not modify or drop the index concurrently during conversion.
- Appropriate `collMod` privileges.

Do not run these commands on older MongoDB versions or unsupported tiers.

### 9.2. Step A — Inspect Existing Indexes

```javascript
db.orders.getIndexes();
```

Suppose you see:

```javascript
{
  name: "tenant_external_lookup",
  key: { tenantId: 1, externalOrderId: 1 }
}
```

Never recreate an index with the same key/name blindly. Record its exact definition and verify namespace, collation, and `partialFilterExpression`.

### 9.3. Step B — Block New Duplicates

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    prepareUnique: true
  }
});
```

Once this succeeds, MongoDB **rejects writes introducing new duplicate index-key values**, even while old duplicates remain.

**Important:** `prepareUnique:true` neither repairs nor deletes existing duplicate documents. Also, issue it as its own `collMod` command: do not combine `prepareUnique` with other index changes in one command.

### 9.4. Step C — Dry Run to Detect Duplicates

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});
```

If duplicates exist, MongoDB returns `CannotConvertIndexToUnique` along with conflict details when possible. If the conflict list exceeds the response limit (current docs note ~8 MB), the server reports too many conflicts rather than returning all IDs.

Therefore, never treat `dryRun` output as your sole large-scale duplicate audit system.

### 9.5. Step D — Resolve Historical Conflicts

Every conflict requires a business decision. Options:

- Fix a corrupted key to the true key from an authoritative source.
- Merge duplicate records when proven to represent the same business entity.
- Mark one record as audit/legacy and move namespaces if policy allows.
- Abort unique enforcement if the records actually represent two unmergeable entities.

**Never run `deleteOne()` on real orders/payments simply because `dryRun` flagged a duplicate.**

### 9.6. Step E — Re-Run Dry Run and Finalize

```javascript
// Conflicts resolved, re-verify:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

// Once the above succeeds and change ticket approves:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  }
});
```

Finalization scans and verifies per server semantics. Confirm `getIndexes()` shows `unique:true`, run negative integration tests in a lab namespace, and watch for `DuplicateKey` errors from apps.

### 9.7. Aborting Conversion If Not Ready

If `prepareUnique` is active yet conversion cannot finish, never leave the intermediate state forgotten. Track owner, ticket TTL, current index definition, and remaining conflicts.

On supported versions, you can revert preparation via:

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    prepareUnique: false
  }
});
```

This **rolls back the preparation stage** and permits new duplicates again; require explicit approval. You cannot toggle `unique:false` to casually disable a finalized unique index—dropping/rebuilding the index under a separate plan may be required.

## 10. Building a Brand-New Unique Index from Scratch

Not every collection starts with a matching non-unique index. For instance:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  {
    name: "tenant_external_unique",
    unique: true
  }
);
```

If duplicates exist, the build fails. If writers insert duplicates mid-build, outcomes depend on timing races. Safe procedure:

1. Deploy compliant writers.
2. Audit and clean duplicates in batches.
3. Apply serialization/quiesce if races cannot be eliminated otherwise.
4. Budget memory, CPU, disk, IOPS, replication, and commit quorum for the build.
5. Run `createIndex` on the approved namespace.
6. Verify success, index definition, and behavior.
7. Monitor write errors caused by the new unique constraint.

An **online index build** still takes brief locks at start/end, consumes resources, and coordinates across replicas. Never launch a heavy DDL build during peak traffic simply because it is labeled “online.”

### 10.1. Hidden Indexes Do Not Disable Uniqueness

A hidden index still:

- Updates on every write.
- Consumes disk and memory.
- Enforces uniqueness if configured `unique:true`.
- Triggers TTL expiration if configured as TTL.

Hiding only **prevents the query planner from selecting the index**. It does not let you “test unique without affecting writes”—a hidden unique index still rejects duplicate writes.

## 11. Null, Missing, Optional IDs, and Unique Indexes

### 11.1. Single-Field Unique Index

With a standard index:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

MongoDB maps both missing and BSON Null into null index keys. A single-field unique index allows **at most one document with a null index entry**. Multiple users lacking emails cause the index build to fail.

Never blindly add a unique `email` index on a collection with millions of optional-email users.

### 11.2. Compound Unique Index

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

Uniqueness applies to the **tuple of key values**. A missing field becomes a null-like component. `{tenantId:"T1",externalOrderId:null}` collides with another document having the same `tenantId` and missing `externalOrderId`.

Audit duplicates over the exact compound key, not just global null counts.

### 11.3. Partial Unique Index for Optional Business Fields

If many users lack emails yet every **provided String email** must be unique:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    name: "unique_string_email",
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Uniqueness applies only to documents matching the partial filter. Missing/Null values stay out of the index, while non-String types still need a validator.

This contract differs from “every user must have an email.” Never use partial unique indexes to evade required-field rules. For per-tenant uniqueness, use compound `{tenantId:1,email:1}` and verify shard-key constraints.

### 11.4. Sparse Unique Is Not Equivalent to Partial Unique

Sparse indexes skip documents lacking the indexed field, yet still index documents where the field is explicitly `null`. Thus `sparse:true` does not allow unlimited `{email:null}` documents.

Partial filters express constrained subsets much more explicitly, though you must check server versions and query coverage: the query planner will not use a partial index unless the query guarantees matching its filter.

### 11.5. Arrays and Multikey Unique Indexes

A multikey unique index enforces uniqueness **across documents**, not within a single document's array elements. If arrays cannot contain duplicate elements, enforce `uniqueItems:true` in the validator and write logic rather than relying on a unique index alone.

## 12. Sharded Collections: Uniqueness Constraints

On sharded collections, unique indexes have strict **shard key** rules. Under ranged sharding, valid unique indexes are typically:

- An index on the shard key;
- a compound index where the shard key is a **prefix**;
- the `_id` index under special semantics: if `_id` is not the shard key, uniqueness may be enforced only per shard.

For example, if the shard key is:

```javascript
{ tenantId: 1 }
```

a valid unique candidate is:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

Yet if the shard key is `{region:1,tenantId:1}`, `{tenantId:1,externalOrderId:1}` **lacks the shard key prefix**. Never claim it enforces global uniqueness without checking topology and server rules.

Additionally:

- Hashed indexes do not support arbitrary `unique:true`.
- Shard key refinement/resharding affects allowed unique indexes.
- Compound/multikey/partial index restrictions further narrow options.
- In a sharded cluster, execute DDL via `mongos` and verify across all shards.
- `prepareUnique` can reject indexes incompatible with the shard key.

**Never turn a “global unique” business requirement into shard-local uniqueness without redesigning the invariant.**

## 13. Phased Rollout of Schema Validation

### 13.1. Validation Actions and Levels

| Setting | Value | Effect |
| --- | --- | --- |
| `validationAction` | `warn` | Permits invalid writes while logging warnings |
| `validationAction` | `error` | Rejects invalid writes |
| `validationAction` | `errorAndLog` | Rejects and logs; MongoDB 8.1+ |
| `validationLevel` | `moderate` | Validates inserts and updates on currently valid docs |
| `validationLevel` | `strict` | Validates all inserts/updates; no retro-scan on enable |
| `validationLevel` | `constraint` | MongoDB 9.0+, guarantees all documents conform after upgrade |

`warn` does not enforce invariants; it is an **observation phase**. `moderate` allows gradual cleanup while existing invalid documents still receive updates.

### 13.2. Phase A — Writers Emit the New Schema

First:

- Deploy API/server/batch writers emitting correct fields and BSON types.
- Allow readers to handle both old and new data during transition.
- Stamp `schemaVersion` when an explicit contract exists.
- Update import jobs, admin scripts, and driver mappings.
- Use feature flags/canaries for write paths.
- Implement idempotent retries and handle validator/duplicate-key errors.
- Check whether rolling back to the old app could re-emit legacy schemas.

Never enable strict validation in production while active old writers will be rejected.

### 13.3. Phase B — Observe with `warn`

```javascript
db.runCommand({
  collMod: "orders",
  validator: targetOrderValidator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

This illustrates sequencing. Under `moderate`, updates on **already-invalid documents** bypass validation, so warning logs will not surface every legacy update.

If your goal is observing **all writes** to spot buggy clients, consider `strict + warn` in controlled staging/production; it never blocks writes, though log volume rises. Pick level/action based on goals, traffic, and PII logging policies.

### 13.4. Phase C — Block New Bad Data

```javascript
db.runCommand({
  collMod: "orders",
  validator: targetOrderValidator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Semantics:

- New invalid inserts are rejected.
- Updating a **currently valid** document into an invalid state is rejected.
- Updating an existing invalid document is permitted so remediation can fix it.

This phase beats waiting until all history is clean before blocking new violations.

### 13.5. Phase D — Backfill and Re-Audit

While in `moderate + error`:

- Clean legacy data under explicit rules.
- Watch for false positives/negatives in the target validator.
- Count remaining invalids per partition and collection-wide.
- Monitor writer errors.
- Never rely on `bypassDocumentValidation` as a permanent crutch.
- Never let “unfixable” rows vanish from audit tracking.

### 13.6. Phase E — Switch to `strict + error`

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
});
```

Recommended gates:

- Invalid document count = 0 per trusted audit.
- All writers/ETLs confirmed compatible.
- Negative tests prove invalid writes get rejected.
- Error rates near baseline with headroom.
- Recovery plan ready if rare code paths break.

**`strict` does not automatically inspect or repair old documents on switch.** Remaining legacy invalid docs stay in place, yet any future update on them will fail.

### 13.7. MongoDB 9.0: `constraint` for Collection-Wide Guarantees

MongoDB 9.0 introduces `validationLevel:"constraint"`:

- Guarantees every document in the collection conforms to the validator after upgrade succeeds.
- On existing collections, prepare first with `prepareConstraintValidationLevel:true`.
- Upgrading scans existing documents and fails if any invalid document exists.
- `validationAction` must be `error` or `errorAndLog`.
- While at `constraint`, you cannot swap the validator directly; downgrade the level per documentation first.
- Validation bypass is restricted.

Example **exclusively for MongoDB 9.0+ after auditing**:

```javascript
db.runCommand({
  collMod: "orders",
  prepareConstraintValidationLevel: true
});

db.runCommand({
  collMod: "orders",
  validationLevel: "constraint",
  validationAction: "error"
});
```

Never combine validator changes into the `constraint` upgrade command, and never copy this onto MongoDB 6/7/8. The full-collection scan carries CPU/I/O cost; schedule per change window and metrics.

## 14. `moderate` vs. `strict` on Legacy Documents

Suppose:

```javascript
{
  _id: "legacy-1",
  status: "paid",
  amountCents: "1500"
}
```

New validator requires uppercase enums and Int64 amounts.

| Operation | `moderate+error` | `strict+error` |
| --- | --- | --- |
| Insert valid new doc | Accept | Accept |
| Insert invalid new doc | Reject | Reject |
| Update valid doc to invalid | Reject | Reject |
| Update legacy invalid doc touching only `reviewedAt` | May accept | Reject |
| Update legacy invalid doc into valid shape | Accept | Accept |
| Untouched legacy doc | Still exists | Still exists |
| Apply new rule via `collMod` | Does not auto-fix legacy | Does not auto-fix legacy |

Understand carefully: `moderate` evaluates updates based on the **pre-update document state**. Do not assume “all invalid updates are blocked” right after enabling `moderate`.

## 15. Safe Backfill: One Document, One Decision, Conditional

### 15.1. Do Not Blindly Mutate with `updateMany({})`

Dangerous example:

```javascript
// Wrong for real data: can change monetary meaning.
db.orders.updateMany(
  {},
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong(0)
    }
  }
);
```

No single blanket value fits every order. Unclassified bulk updates break business invariants and spike oplog, replication lag, and disk IOPS.

### 15.2. Compare-and-Set on Old Value / Version

A record:

```javascript
{
  _id: ObjectId("66a000000000000000000427"),
  tenantId: "T-1",
  externalOrderId: "A-100",
  status: "paid",
  amountCents: "1500",
  version: NumberInt(7)
}
```

Once verified `"1500"` genuinely represents convertible cents:

```javascript
const updateResult = db.orders.updateOne(
  {
    _id: ObjectId("66a000000000000000000427"),
    tenantId: "T-1",
    status: "paid",
    amountCents: "1500",
    version: NumberInt(7)
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong("1500"),
      migrationVersion: "constraint-v2"
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  matched: updateResult.matchedCount,
  modified: updateResult.modifiedCount
});
```

`matchedCount:0` indicates the record changed or was already migrated—never a reason to drop CAS and overwrite blindly. Re-read, compare new state, and choose retry/skip/conflict.

### 15.3. Write Strictly Bounded Conversion Functions

Java 17 example:

```java
import java.math.BigInteger;

static long parseCents(String raw) {
    if (raw == null || !raw.matches("^[0-9]+$")) {
        throw new IllegalArgumentException(
            "Cents must be a nonnegative integer string"
        );
    }

    return new BigInteger(raw).longValueExact();
}
```

`longValueExact()` throws on Int64 overflow—far better than silent truncation. Still, even when parsing succeeds, confirm **the input unit is cents**, not VND or dollars.

### 15.4. Side-Effect-Free Repeatable Migrations

An idempotent migration typically has:

- Filters selecting only unmigrated records.
- A `migrationVersion` or marker field.
- CAS on old values/versions.
- Deterministic transformations.
- Key-based progress checkpoints.
- Bounded retries.
- Logging of conflict IDs and reason codes.
- Zero email/payment side effects inside bulk retry callbacks.

Never rely on natural collection order or `skip` pagination on live datasets; use `_id` keyset pagination or indexed partitions/windows.

### 15.5. Batch Model

```text
Read <= N candidates by _id/partition
               |
               v
Transform using audited rule
               |
               v
Validate transformed BSON
               |
               v
Write CAS updates (bounded bulk)
               |
       +-------+-------+
       |               |
       v               v
    Modified         Conflict/no-match
       |               |
       v               v
   Record success    Re-read/review
       |
       v
Persist progress checkpoint
       |
       v
Throttle, monitor, next batch
```

Only checkpoint migration progress once updates confirm per your durability contract. On crash between partial writes and checkpointing, CAS/idempotency ensures replay neither duplicates nor overwrites.

## 16. Cleaning Duplicates: Business Adjudication Before Writing

### 16.1. Four Questions

When two documents share a key:

1. Do they share the same semantic identity?
2. Are they part of the same payment/order lifecycle?
3. Do other collections/services reference them?
4. If merged or re-keyed, do downstream systems know the mapping?

Never pick “keep lowest `_id`” as a blanket rule when `_id` reflects only insertion time rather than business accuracy.

### 16.2. Safe Resolution Patterns

| Scenario | Approach |
| --- | --- |
| Identical copies from retry | Pick canonical via audit, update references, retain lineage |
| Distinct entities colliding due to import bug | Assign true business ID from audited source |
| One is retained legacy history | Separate active/current vs. historical schema or version |
| Cannot distinguish | Block conversion and route to manual review |
| Duplicates from normalization | Normalize keys under one contract, re-audit newly surfaced conflicts |

### 16.3. Re-Keying a Document Requires CAS

```javascript
db.orders.updateOne(
  {
    _id: legacyId,
    tenantId: "T-1",
    externalOrderId: "A-100",
    version: NumberInt(3)
  },
  {
    $set: {
      externalOrderId: "A-100-LEGACY",
      duplicateResolutionId: "resolution-ticket-427"
    },
    $inc: { version: 1 }
  }
);
```

Here `A-100-LEGACY` is strictly an **illustrative** name after the domain owner chose the exact new key. **Never** auto-append suffixes to all production duplicates and claim business conflicts are solved.

### 16.4. When Two Documents Must Merge

Design:

- Multi-document transactions across related MongoDB docs where topology supports them.
- Mapping `old _id → canonical _id`.
- Reference reconciliation.
- Audit/history retention.
- Idempotency on transaction or job retries.
- Compensation for external side effects outside MongoDB.
- Legal/audit sign-off before deleting real records.

A unique index prevents future duplicates; **it does not decide which existing record is canonical**.

## 17. Expand–Migrate–Contract Rollout Sequence

### 17.1. Expand: Backward-Compatible Application

In Release A:

- Readers accept both `status:"paid"` and `status:"PAID"`.
- New writers emit `"PAID"` and Int64 amounts.
- Downstream consumers accept both forms during transition.
- Emit telemetry on malformed writes and duplicate attempts.
- Make new fields optional initially.
- Build non-unique indexes for auditing/`prepareUnique` if needed.
- Use validation `warn` to surface bad writes.

### 17.2. Guard: Block New Violations Before Cleaning

In Release B:

- Confirm all active writers upgraded.
- Enable `moderate + error` on the schema.
- Enable `prepareUnique` on eligible indexes.
- Watch validation failures and `DuplicateKey` errors.
- Proceed only once old clients are upgraded or unaffected.
- Keep a rollback plan for this stage.

### 17.3. Migrate: Clean Historical Data

In Release C:

- Audit and partition candidates.
- Backfill per business rules.
- Quarantine unfixable records.
- Resolve unique conflicts.
- Re-run `dryRun` and audits repeatedly.
- Compare before/after counts, value totals, and relationships.

### 17.4. Contract: Tighten Constraints

In Release D:

- Finalize the unique index.
- Switch validator to `strict + error`.
- On MongoDB 9.0+ needing an all-existing-valid guarantee, evaluate `constraint` once ready.
- Retire old write paths and fallback code once proven unused.
- Maintain prior version/read compatibility through the planned rollback window.
- Observe through at least one major business cycle.

### 17.5. Why Multiple Releases?

During rolling deployments, app v1 and v2 coexist. Tightening database constraints before v1 stops writing causes v1 failures. Removing legacy read logic before backfill finishes breaks API reads.

```text
        Application v1 ---------+
                                |
        Application v2 ---------+---> MongoDB
                                |
        Backfill job -----------+
                                |
        Reporting/ETL ----------+
```

Every **writer** must be inventoried—not just the main web API.

## 18. Multi-Version Writers and Ongoing Mutations

### 18.1. Dual-Read and Dual-Write Need Clear Contracts

During transition:

```javascript
{
  amount: "1500",
  amountCents: NumberLong("1500")
}
```

dual-writes may be needed. Yet updating one field without the other creates inconsistency.

Options:

- Designate one field canonical; maintain the legacy field solely for compatibility.
- Use transactions or single-document atomic updates when dual-writing.
- Monitor reconciliation metrics between both fields.
- Never backfill blindly over a new field already updated by another writer.

### 18.2. Change Streams Do Not Replace Audits and Gap Recovery

When backfilling a live collection, change streams help track concurrent writes and reconcile. However, resume tokens work only while oplog history remains, consumers need checkpoints/idempotency, and zero gaps must exist.

Never rely on “scan once then watch from now” if a gap exists between the scan and stream start. For critical migrations, use a verified cutover/backfill protocol or write quiesce when necessary.

### 18.3. Giant Transactions Are Not the Default Solution

A collection-wide transaction can:

- run for hours;
- pin old snapshots/history;
- spike cache/disk pressure;
- trigger write conflicts;
- hinder operations and failovers.

Usually prefer **small atomic CAS updates**, checkpoints, and reconciliation. Reserve short transactions for groups of operations that truly must commit atomically.

## 19. Preventing Violations from Reappearing Post-Migration

A classic failure: reporting “invalid count = 0” at 12:00 while an old writer creates bad records at 12:05. Prevent it via:

- Server-side validators enforced across writers per policy.
- Unique indexes blocking duplicate keys.
- Minimally scoped `bypassDocumentValidation` grants.
- Time-bound, audited exception workflows.
- Continuous error-rate monitoring, not one-off counts.
- Auditing legacy app versions, import scripts, and admin tools.
- Locking contracts into integration/CI tests.
- Versioned deployment checklists before app rollbacks.

### 19.1. Validation Bypass

Certain MongoDB operations support `bypassDocumentValidation` when roles permit it. If an approved migration job uses bypass:

1. Scope tightly by account and duration.
2. Audit every operation.
3. Never grant bypass to general application accounts.
4. Run reconciliation after the job finishes.
5. Note MongoDB 9.0 `constraint` limits: bypass is restricted under that level's semantics.

Using bypass just to “make writes pass” defeats the goal of durable clean data.

### 19.2. Error Codes and Classification

| Error | Common Meaning | Response |
| --- | --- | --- |
| `DuplicateKey` / E11000 | Unique index blocked duplicate key | Check business ID, idempotency, existing record |
| `DocumentValidationFailure` / code 121 | Validator rejected document | Classify field/type and client version |
| `CannotConvertIndexToUnique` | Existing duplicate entries | Audit/remediate, re-run `dryRun` |
| Write concern timeout | Desired acknowledgment unmet | Never assume write rolled back; read back/reconcile |
| Network/server selection error | Operation outcome uncertain | Retry with idempotency and backoff |
| Permission/unsupported option | Wrong role, version, or tier/topology | Halt rollout; never bypass via ad-hoc admin grants |

Never build production logic parsing literal error text; drivers/servers can change wording. Rely on error classes, `codeName`/`code`, and context.

## 20. TTL: Retention Constraints Can Lose Data

Not every “constraint” merely rejects writes. TTL indexes **delete documents** upon expiration.

Example:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "session_ttl",
    expireAfterSeconds: 0
  }
);
```

Before enabling on legacy data:

- Confirm `expiresAt` is BSON Date, not String.
- Understand how missing/null fields behave (they do not expire like valid Dates).
- Verify UTC/timezones and backfilled dates carry real business meaning.
- Estimate how many documents become immediately eligible for deletion upon create/modify.
- Verify legal holds and retention mandates.
- Account for IOPS/replication lag during mass deletes.
- Back up legally required records.

Shortening TTL from 90 days to 7 days can make huge batches immediately eligible for deletion, causing I/O bursts. Rolling back the TTL setting later **cannot restore deleted documents**.

The lab **does not create a TTL index** because automatic deletion is unnecessary to demonstrate post-cleanup constraint enforcement.

## 21. Choosing `strict` vs. `constraint` After Cleanup

| Criterion | `strict + error` | `constraint + error` (9.0+) |
| --- | --- | --- |
| New invalid inserts | Blocked | Blocked |
| Invalid updates | Blocked | Blocked |
| Scans all existing docs on level upgrade | No | Yes, during upgrade procedure |
| Guarantees all existing docs conform | Not merely by setting `strict` | Yes, after successful upgrade |
| Direct validator edits | Possible via `collMod` | Must downgrade to `strict` first |
| Role-based validation bypass | Possible per operation/role | Restricted |
| Upgrade cost on huge collections | No default retro-scan | Can trigger resource-heavy full scan |

Decision guide:

- On MongoDB 8.0 or earlier: `constraint` is unavailable; combine audit/reconciliation with `strict`.
- On MongoDB 9.0+ needing strong guarantees: prepare, audit, capacity-plan, and upgrade per docs.
- While legacy invalid docs remain: `constraint` upgrade fails; finish cleaning or adjust the valid contract.

## 22. Rollback Planning Before Enabling Constraints

### 22.1. Rolling Back Schema Validators

Before changing anything, export:

```javascript
db.getCollectionInfos({ name: "orders" });
```

Save verbatim:

- previous `validator`;
- `validationLevel`;
- `validationAction`;
- related options.

To roll back, restore the prior definition via `collMod`. Note that rejected writes **do not automatically replay**; apps need idempotent retries or reconciliation.

### 22.2. Rolling Back `prepareUnique`

Before finalizing, you can revert with `prepareUnique:false` where versions/conditions permit. Understand this allows new duplicates again and decide whether that state is acceptable.

### 22.3. Rolling Back a Finalized Unique Index

Never treat `unique:false` as a simple flag toggle. Removing a finalized unique constraint may require dropping/rebuilding a non-unique index, causing I/O and temporarily losing uniqueness. In production, design changes for **forward-fix capability** rather than assuming instant constraint reversal.

### 22.4. Rolling Back Transformed Data

Converting `amount:"1500"` to `amountCents:Long(1500)` is reversible if source semantics remain 1-to-1. However, if you:

- normalized multiple Strings to one canonical value;
- merged duplicates;
- deleted fields or records;
- converted ambiguous timestamps;
- recalculated money under lossy rules;

a quick reverse script cannot undo it. Rely on backups/PITR, lineage, and business-level compensation.

### 22.5. Distinguish “Deployment Rollback” from “Data Rollback”

Rolling back app code does not revert migrated documents to old shapes. Before redeploying an old app version, verify it **can read migrated data** and that its writes will not be blocked by validators.

## 23. Monitoring and Phase-Gate Criteria

### 23.1. Suggested Dashboard

```text
+-----------------------------+-----------------------------+
| Invalid docs remaining      | Duplicate key groups        |
+-----------------------------+-----------------------------+
| Backfill rows/s & conflicts | Job retries / stalled       |
+-----------------------------+-----------------------------+
| Validation failures/min     | DuplicateKey errors/min     |
+-----------------------------+-----------------------------+
| Application write p95/p99   | API error rate              |
+-----------------------------+-----------------------------+
| CPU / WiredTiger cache      | Disk IOPS / queue / free    |
+-----------------------------+-----------------------------+
| Replication lag             | Index conversion state      |
+-----------------------------+-----------------------------+
| Schema versions observed    | Legacy writer requests      |
+-----------------------------+-----------------------------+
| Reconciliation mismatches   | Business-level totals       |
+-----------------------------+-----------------------------+
```

### 23.2. Illustrative Application Metrics

```text
mongo_data_migration_candidates_total
mongo_data_migration_processed_total
mongo_data_migration_conflicts_total
mongo_data_migration_manual_review_total
mongo_data_invalid_documents
mongo_data_duplicate_key_groups
mongo_data_schema_version_distribution
mongo_validation_errors_total
mongo_duplicate_key_errors_total
mongo_migration_write_latency_seconds
mongo_migration_last_success_timestamp_seconds
mongo_migration_reconciliation_mismatches
```

These are **user-defined names**, not built-in MongoDB metrics. When counting invalid docs requires full scans, avoid running heavy counts every few seconds; combine migration counters/sampling with scheduled audits.

### 23.3. “Go/No-Go” Criteria

Must pass before `strict + error`:

- Zero active writers emitting the old schema.
- Invalid record count = 0 per scoped audit.
- Zero duplicate groups matching the target unique key.
- Migration conflicts and manual-review backlogs adjudicated.
- Index conversion `dryRun` succeeded.
- No abnormal replication lag.
- Write p95/p99 within SLO.
- Backups and realistic data recovery plans verified.
- Critical tenants/partitions reconciled.
- Negative tests confirm bad writes fail in a comparable environment.

**These are production deployment gates**, not documentation QA checks.

## 24. Safe Lab: From Duplicates to Unique + Strict Validator

### 24.1. Prerequisites

This lab requires:

- MongoDB **6.0+** self-managed test instance or service supporting `collMod.prepareUnique`.
- Privileges to create collections, indexes, run `collMod`, and CRUD on a **test database**.
- Never use production collections or alter server/FCV settings.
- Keep dataset tiny and avoid disk pressure.
- Use a **randomized collection name** and unique `runId` per run.
- Mutate/delete only records matching your run's `_id` and `runId`.
- Never run `dropDatabase()` or unbounded cleanups.

**All commands below are for authorized test deployments**, never to be blindly pasted onto production.

### 24.2. Create an Isolated Namespace

```javascript
const lab = db.getSiblingDB("mongo_evolution_row427_lab");
const runId = "row427_" + new ObjectId().toHexString();
const name = "orders_" + runId;
const tenantId = "tenant_" + runId;

if (lab.getCollectionNames().includes(name)) {
  throw new Error("Namespace already exists; refuse overwrite");
}

lab.createCollection(name);
const orders = lab.getCollection(name);

printjson({
  database: lab.getName(),
  collection: orders.getName(),
  tenantId,
  runId
});
```

Keep variables in the same `mongosh` session. If the shell reconnects, verify your run's namespace/`runId` before continuing; never guess a tenant.

### 24.3. Insert Three Documents: One Schema-Invalid and One Duplicate

```javascript
const legacyId = new ObjectId();
const canonicalId = new ObjectId();
const thirdId = new ObjectId();

orders.insertMany([
  {
    _id: legacyId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "paid",
    amountCents: "1500",
    schemaVersion: NumberInt(1)
  },
  {
    _id: canonicalId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "PAID",
    amountCents: NumberLong("1500"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: thirdId,
    runId,
    tenantId,
    externalOrderId: "A-200",
    status: "CREATED",
    amountCents: NumberLong("2500"),
    schemaVersion: NumberInt(2)
  }
]);

print("ownedDocuments=" +
  orders.countDocuments({ runId }));
```

In this lab, we **predefine** the two `A-100` documents as synthetic fixtures so re-keying the legacy one is an approved demo step. Production requires business-owner sign-off.

### 24.4. Build the Non-Unique Index First

```javascript
orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { name: "tenant_external_lookup" }
);

printjson(orders.getIndexes());
```

This index supports lookups without enforcing uniqueness yet.

### 24.5. Scoped Duplicate Audit

```javascript
const duplicates = orders.aggregate([
  { $match: { runId, tenantId } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
]).toArray();

printjson(duplicates);

if (duplicates.length !== 1 ||
    duplicates[0].count !== 2) {
  throw new Error("Unexpected lab duplicates");
}
```

Each run isolates its own random tenant, avoiding collisions with other runs. The dataset is only 3 records.

### 24.6. Define Target Validator

```javascript
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "runId",
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      runId: {
        bsonType: "string"
      },
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      }
    }
  }
};
```

### 24.7. Stage `warn` to Observe Legacy Invalids

```javascript
const warnResult = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "strict",
  validationAction: "warn"
});

if (warnResult.ok !== 1) {
  throw new Error("Cannot activate validator warning phase");
}

const invalidBefore = orders.countDocuments({
  runId,
  $nor: [validator]
});

print("invalidBefore=" + invalidBefore);

if (invalidBefore !== 1) {
  throw new Error("Expected one legacy invalid doc");
}
```

Here `strict+warn` logs warnings on any invalid write during testing. `collMod` does not mutate old documents. In production, warning logs can expose sensitive data and grow log volume.

### 24.8. Block New Invalid Writes While Allowing Legacy Cleanup

```javascript
const guardResult = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});

if (guardResult.ok !== 1) {
  throw new Error("Cannot activate moderate error phase");
}
```

New invalid inserts are rejected, while existing invalid records can still be migrated toward validity.

### 24.9. Prepare Index for Unique Conversion

```javascript
const prepare = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    prepareUnique: true
  }
});

if (prepare.ok !== 1) {
  throw new Error("Cannot prepare unique conversion");
}
```

**After this step, new duplicate keys are blocked**, while the old `A-100` pair remains until migration resolves it.

### 24.10. Verify New Duplicates Are Blocked

```javascript
let duplicateBlocked = false;

try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "CREATED",
    amountCents: NumberLong("100")
  });
} catch (e) {
  if (e.code === 11000) {
    duplicateBlocked = true;
  } else {
    throw e;
  }
}

if (!duplicateBlocked) {
  throw new Error("Expected DuplicateKey after prepareUnique");
}

print("PASS: duplicate new insert blocked");
```

In this test, error code 11000 indicates `DuplicateKey`. In production, handle driver error categories rather than parsing error message strings.

### 24.11. Verify Unique Dry Run Reports Conflicts

```javascript
const dryBefore = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

printjson({
  ok: dryBefore.ok,
  codeName: dryBefore.codeName
});

if (dryBefore.ok === 1) {
  throw new Error(
    "Expected existing duplicate to prevent finalization"
  );
}
```

Do not hardcode exact message text parsing; output formatting varies across versions and conflict counts.

### 24.12. Fix the Legacy Record in the Lab

For our demo data, we defined that legacy `A-100` should become `A-100-LEGACY` with normalized amount and status.

```javascript
const updateLegacy = orders.updateOne(
  {
    _id: legacyId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "paid",
    amountCents: "1500",
    schemaVersion: NumberInt(1)
  },
  {
    $set: {
      externalOrderId: "A-100-LEGACY",
      status: "PAID",
      amountCents: NumberLong("1500"),
      schemaVersion: NumberInt(2)
    }
  }
);

printjson({
  matched: updateLegacy.matchedCount,
  modified: updateLegacy.modifiedCount
});

if (updateLegacy.matchedCount !== 1) {
  throw new Error("Legacy record changed; stop and inspect");
}
```

Note: every update filters by `_id` + `runId` + old values. This is a **demo rule**, not license to auto-suffix production duplicates.

### 24.13. Re-Audit After Cleanup

```javascript
const invalidAfter = orders.countDocuments({
  runId,
  $nor: [validator]
});

const dupAfter = orders.aggregate([
  { $match: { runId, tenantId } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
]).toArray();

printjson({
  invalidAfter,
  duplicateGroups: dupAfter.length,
  ownedDocuments: orders.countDocuments({ runId })
});

if (invalidAfter !== 0 || dupAfter.length !== 0) {
  throw new Error("Do not finalize constraints");
}
```

Confirm both schema validity and key uniqueness. Production requires additional checks on business invariants, cross-collection references, and concurrency.

### 24.14. Passing Dry Run and Finalizing Unique

```javascript
const dryAfter = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

if (dryAfter.ok !== 1) {
  throw new Error("Unique dry run still failed");
}

const finalize = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  }
});

if (finalize.ok !== 1) {
  throw new Error("Unique conversion failed");
}

printjson(orders.getIndexes());
```

Only after finalization succeeds does the index carry `unique:true`. From this point on, do not treat rollback as flipping a single flag.

### 24.15. Enable Strict Validator

```javascript
const strict = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "strict",
  validationAction: "error"
});

if (strict.ok !== 1) {
  throw new Error("Cannot activate strict validator");
}

printjson(
  lab.getCollectionInfos({ name })
);
```

All subsequent inserts and updates face strict rule enforcement.

### 24.16. Negative Tests for New Constraints

```javascript
// 1. Duplicate keys must be blocked.
let duplicateRejected = false;
try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-200",
    status: "PAID",
    amountCents: NumberLong("10")
  });
} catch (e) {
  if (e.code !== 11000) throw e;
  duplicateRejected = true;
}

if (!duplicateRejected) {
  throw new Error("Unique index did not reject duplicate");
}

// 2. Wrong BSON type/enum must be blocked.
let invalidRejected = false;
try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-300",
    status: "paid",
    amountCents: "100"
  });
} catch (e) {
  if (e.code !== 121) throw e;
  invalidRejected = true;
}

if (!invalidRejected) {
  throw new Error("Validator did not reject bad document");
}

print("PASS: unique and strict validator reject bad writes");
```

These errors are **expected inside the test namespace**. Never run tests that deliberately insert duplicates or invalid records against production collections.

### 24.17. Ownership-Scoped Cleanup

First print the scope:

```javascript
print("DB=" + lab.getName());
print("COLLECTION=" + orders.getName());
print("RUN=" + runId);
print("TENANT=" + tenantId);

const owned = orders.find(
  { runId, tenantId },
  { _id: 1, runId: 1, tenantId: 1 }
).toArray();

printjson({
  ownedCount: owned.length,
  ownedIds: owned.map((d) => d._id)
});
```

After confirming exactly the 3 documents created by this run:

```javascript
for (const item of owned) {
  orders.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

print("remaining=" +
  orders.countDocuments({ runId, tenantId }));
```

Never run `dropDatabase()` or `deleteMany({})` on a shared database. The demo collection/index/validator remains after document cleanup; test environments typically reclaim randomized namespaces per owner/retention rules. Only authorized lab admins should drop the collection once confirmed unused.

## 25. Designing a Compatible Java Migration Worker and Rollback

### 25.1. Separate Transformation Logic from MongoDB Commands

An application migration worker should separate:

```text
CandidateReader
   -> BusinessRuleResolver
   -> BsonTypeConverter
   -> ValidationChecker
   -> ConditionalMongoWriter
   -> ProgressStore
   -> Metrics/AuditLogger
```

Avoid cramming everything into a hard-to-review aggregation update pipeline when conversions carry business exceptions.

### 25.2. Java Sync Driver Example Using CAS

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

static UpdateResult migrateOne(
        MongoCollection<Document> orders,
        Object id,
        String tenantId,
        String oldAmount,
        int expectedVersion,
        long exactCents) {

    return orders.updateOne(
        and(
            eq("_id", id),
            eq("tenantId", tenantId),
            eq("amountCents", oldAmount),
            eq("version", expectedVersion)
        ),
        combine(
            set("amountCents", exactCents),
            set("migrationVersion", "constraint-v2"),
            inc("version", 1)
        )
    );
}
```

Primitive `long` in the Java Driver normally serializes to BSON Int64. Verify via `BsonDocument` or `$type` readback when the contract requires strict precision.

### 25.3. When `matchedCount == 0`

Possible reasons:

- Another worker already migrated the record.
- The application updated amount/status concurrently.
- Version incremented.
- The document was deleted or changed owner.
- The migration's mapping assumption no longer holds.

Re-read and classify. Never retry infinitely using an `_id`-only filter, which risks overwriting fresher data.

### 25.4. Writers Remain Active During Migration

Coordinate the contract:

- New writers emit the valid schema.
- Legacy readers tolerate both shapes.
- Backfills mutate records only when expected old fields match.
- If a concurrent write updated the record, the migration skips or reconciles.
- Contract only when `invalid == 0` and all writers are migrated.
- If using change streams/outbox, preserve checkpoints without losing oplog history.

## 26. Regression Testing Before and After Constraints

The tests below belong to **the system strategy described in this lesson**.

### 26.1. Insert/Update Matrix

| Test | Expected After Strict + Unique |
| --- | --- |
| Insert valid schema, new key | Success |
| Insert lowercase status | Validator rejects |
| Insert String amount | Validator rejects |
| Insert negative amount | Validator rejects |
| Insert missing `tenantId` | Validator rejects |
| Insert null `externalOrderId` | Validator rejects |
| Insert duplicate `tenant+externalOrderId` | `DuplicateKey` |
| Insert same `externalOrderId` in different tenant | Success if per-tenant contract |
| Update valid → invalid | Validator rejects |
| Update legacy invalid after `strict` | Rejected until repaired to valid |
| Update amount with Int32 when target is Long | Rejected |
| Upsert omitting required fields | Validator rejects insert branch |
| Replace omitting required fields | Rejected |
| Concurrent duplicate inserts | Only one key accepted |
| Retry with same idempotency key | No duplicate business effect |

### 26.2. Data Correctness Verification

- Order counts before/after.
- Revenue/amount totals per tenant reconciled against authoritative sources.
- Count of re-keyed records and justification for each.
- Quarantined record count.
- Validation/index error rates.
- Unmigrated document count.
- Cross-collection references.
- Timestamp and actor for every remediation.
- Reconciliation of downstream projections.

Never treat `invalid count = 0` as sufficient proof if records were “cleaned” by deleting millions of documents.

### 26.3. Mandatory Boundary Tests

- Null vs. missing.
- Empty/whitespace Strings.
- Case/accent/Unicode normalization.
- `NumberInt` vs. `NumberLong` vs. `Decimal128`/`Double`.
- Int64 overflow/precision.
- Missing required fields in upserts.
- Parallel inserts with identical keys.
- Key edits creating duplicates.
- Legacy invalid documents during `moderate` phase.
- Index build/`dryRun` while duplicates exist.
- App version rollback after `strict` is enabled.

## 27. Common Incident Runbooks

### 27.1. Unique Conversion Returns `CannotConvertIndexToUnique`

**Symptom:** `dryRun` or finalization fails.

**Investigation:**

1. Verify exact index name/`keyPattern` and namespace.
2. Check duplicate groups, null/missing values, and normalization.
3. Verify shard key and unique index restrictions.
4. Check for concurrent writes or index operations.
5. If conflicts are numerous, do not rely solely on error responses.
6. Keep `prepareUnique` active if already enabled to block new duplicates.
7. Execute domain-approved remediation and re-run `dryRun`.

Never relax the unique requirement without business-owner approval.

### 27.2. Enabling Validator Triggers Code 121 Errors in API

**Symptom:** `DocumentValidationFailure` spikes post-rollout.

**Investigation:**

- Which app version is writing?
- Is the operation insert, update, replace, or upsert?
- Was the document valid or invalid before the update?
- Which field/type/enum failed?
- Are imports, ETLs, or cron jobs still writing the old format?
- Was `strict` enabled too early?
- Is PII leaking into error logs?

**Mitigation:** roll back writer code, fix schema mappings, or temporarily step back validator level/action if approved. Never grant blanket bypass across all clients.

### 27.3. New Duplicates Appear After Audit

This signals missing guards or uninventoried writers. Check:

- Does the index have `prepareUnique` or full `unique`?
- Is the index scoped properly by tenant?
- Is `partialFilterExpression` accidentally skipping records?
- Are other collections/shards outside scope?
- Are admin jobs bypassing or writing directly?
- Do app and database normalizations match?

Never simply re-run audits and proceed; **stop the source emitting bad writes**.

### 27.4. Migration Increases Replication Lag

Actions:

- Reduce batch size/throughput.
- Check write concern and secondary I/O.
- Pause competing batch jobs.
- Preserve headroom for oplog, journal, and indexes.
- Never scale concurrency blindly.
- Resume from checkpoint once the cluster stabilizes.

Never reflexively weaken durability/write concern if business correctness requires majority acknowledgment.

### 27.5. Changing Unique Keys Breaks Downstream Links

Symptom: read models, reports, or partners cannot locate orders by old `externalOrderId`.

Cause: migration altered business IDs without a mapping or cutover plan.

Recovery requires:

- `oldKey → newKey` mapping.
- Reconciling references, caches, and search indexes.
- Audit events or outbox updates per policy.
- Idempotent reprocessing.
- If rolling back, accounting for fresh writes emitted after the key change.

### 27.6. `strict` Leaves Invalid Docs Undetected at Enable Time

Not a bug. `strict` does not retro-scan existing documents on enable. Only an update touching an invalid document triggers the error. Audit with `$nor:[validator]` or, on MongoDB 9.0+, evaluate `constraint` for collection-wide guarantees.

## 28. Sample Production Change Plan

```yaml
changeId: mongo-orders-constraint-v2
owner: orders-platform
scope:
  database: commerce
  collection: orders
  environment: production
objective:
  - tenant_external_order_id_unique
  - strict_order_schema
preconditions:
  - verified_server_fcv_topology
  - inventory_all_writers
  - backup_restore_tested
  - no_unrelated_major_ddl
  - capacity_headroom
  - migration_rules_approved
baseline:
  - p95_read_write
  - validation_failure_rate
  - duplicate_groups
  - invalid_documents
  - replication_lag
  - disk_free_iops
phases:
  - expand_application_read_write
  - schema_warn
  - schema_moderate_error
  - prepare_unique
  - backfill_and_resolve_conflicts
  - audit_and_unique_dry_run
  - finalize_unique
  - schema_strict_error
successCriteria:
  - zero_invalid_documents
  - zero_duplicate_groups
  - no_unexpected_write_errors
  - business_reconciliation_pass
rollback:
  - restore_previous_validator_if_required
  - revert_prepare_unique_before_finalization_if_approved
  - plan_forward_fix_after_unique_finalization
  - restore_data_using_backup_or_lineage_when_needed
```

This is a human-managed **change ticket template**, not an executable MongoDB file. Prior to execution, attach exact commands/definitions, timestamps, and approvers; never copy generic templates without deployment-specific guards.

## 29. Self-Study Exercises

### Exercise A — Required or Nullable?

A collection contains:

```javascript
{}
{email:null}
{email:""}
{email:"a@example.test"}
```

Design validators for two contracts:

1. Email is optional, yet if present must be a non-empty String.
2. Email is required, allowing Null during transition.

Explain how `required`, `bsonType`, and `minLength` behave on each document.

### Exercise B — Per-Tenant Uniqueness

```javascript
[
  {tenantId:"T1", code:"A"},
  {tenantId:"T2", code:"A"},
  {tenantId:"T1", code:"A"}
]
```

1. How many duplicate groups exist on `{tenantId,code}`?
2. If you create a unique index solely on `{code:1}`, which documents collide?
3. If the collection is sharded on `{region:1,tenantId:1}`, what must the unique key consider?
4. Why can you not fix duplicates simply with a `deleteMany`?

### Exercise C — `prepareUnique`

Suppose you have a non-unique index and 500 duplicates:

1. Does `prepareUnique:true` let you keep the 500 existing duplicates temporarily?
2. Are new duplicates blocked?
3. What does `dryRun:true` do?
4. When do you run `unique:true`?
5. If pausing before finalization, how do you roll back preparation?

### Exercise D — Wrong BSON Types

Given:

```javascript
{amountCents:"1000"}
{amountCents:NumberInt(1000)}
{amountCents:NumberLong("1000")}
{amountCents:NumberDouble("1000")}
```

The contract requires non-negative Int64. Design the audit, overflow/precision-checked conversions, and post-readback tests.

### Exercise E — Race Between Cleanup and Writes

```text
12:00 Audit duplicates=20
12:05 Fix duplicates=0
12:06 Old app inserts new duplicate
12:07 Unique build fails
```

Sequence deploying writers, validators, index preparation, and migration to eliminate the race.

### Exercise F — Currency Migration

A record stores `amount:"1500"` with unclear units. Why can `NumberLong("1500")` pass type checks yet still be wrong for business? What sources and approvals are needed?

### Exercise G — Partial Unique Email

Many users have no email, some have `email:null`, and others have Strings. Create an index enforcing uniqueness only on String emails, and list what validators/normalization still must enforce.

### Exercise H — `moderate` and `strict`

An existing invalid document is updated solely on `reviewedAt`. Predict behavior under:

- `moderate + error`;
- `strict + error`;
- `strict + warn`;
- `constraint + error` on MongoDB 9.0 after a successful upgrade.

### Exercise I — Data Cleanup Idempotency

A migration job crashes after fixing 60/100 records before saving its checkpoint. Upon restart:

1. How do you avoid overwriting already-migrated records?
2. Are version/old-value filters needed?
3. Why avoid `skip` pagination on mutating collections?
4. What progress/audit record structure helps?

### Exercise J — Changing Enums

Legacy data has `"paid"`, `"settled"`, `"PAID"`, `"refund"`. Design mappings only once the business owner confirms each meaning. How should unmapped values be handled?

### Exercise K — Success Metrics

After cleanup, invalid count drops from 80,000 to 0, yet total document count also dropped by 80,000. Is that a success? Propose business and lineage reconciliation steps.

### Exercise L — TTL on Legacy Data

Many session records have String/Null `expiresAt`, while some Dates are over 30 days old.

1. Does adding a TTL index delete every record immediately?
2. What is the risk of lowering TTL from 90 days to 7 days?
3. Can a validator protect the Date type?
4. Why does rolling back a TTL setting not restore lost data?

### Exercise M — Rolling Back to an Old App

After enabling a strict validator, the new app fails and the team wants to roll back to V1, which writes `amountCents` as a String.

1. What happens to writes?
2. Can `validationAction` be lowered during an incident? At what risk?
3. How should expand/contract be designed for safe code rollbacks?
4. When is a forward-fix better than rolling back?

### Exercise N — MongoDB 9.0 `constraint`

A collection has 2 million documents, a `strict` validator, and an audit shows 30 invalid documents.

1. Can you upgrade to `constraint` immediately?
2. What is `prepareConstraintValidationLevel` for?
3. Does upgrading scan the whole collection?
4. Why forecast CPU/I/O and duration?
5. How do you change the validator after `constraint` is active?

### Exercise O — Uniqueness Incident on a Sharded Cluster

A collection is sharded on `{tenantId:1}`. The team wants `externalOrderId` globally unique across all tenants.

1. Which invariant does unique `{tenantId:1,externalOrderId:1}` guarantee?
2. Does it enforce global `externalOrderId` uniqueness?
3. Why do shard key rules matter?
4. Could you evaluate a centralized identity collection/transaction or alternative routing design?

### Exercise P — Preparing a Change Ticket

Design completely:

- Snapshot of current DDL, validators, and indexes.
- Business-owner remediation decisions.
- Tests and environments.
- Deployment sequence.
- Migration progress/metrics.
- Rollback/forward-fix plan.
- Go/no-go gates.
- Backup and restore drills.
- Change closure criteria.

## 30. Official MongoDB References

When implementing, check **your exact server version, `featureCompatibilityVersion`, sharding topology, driver, and privileges**:

- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — MongoDB validator model.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `moderate`, `strict`, and MongoDB 9.0+ `constraint`.
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `warn`, `error`, and MongoDB 8.1+ `errorAndLog`.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — changing rules via `collMod`.
- [`$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — enforcing BSON types, `required`, enums, and nested fields.
- [Find Documents that Don't Match Schema](https://www.mongodb.com/docs/manual/core/schema-validation/query-for-schema-validation/) — auditing existing documents against rules.
- [Convert Existing Index to Unique Index](https://www.mongodb.com/docs/manual/core/index-unique/convert-to-unique/) — `prepareUnique`, `dryRun`, and finalization.
- [`collMod` Command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — index/validator/TTL options.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — missing/null, compound uniqueness, and multikeys.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — `partialFilterExpression` and partial uniqueness.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard key prefixes and unique restrictions.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — automatic expiration and retention-change risks.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — resource costs, locking, and replicated builds.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Int32, Int64, Decimal128, Date, Null, and others.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgment semantics and ambiguous timeouts.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomic changes when warranted.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — resource monitoring on managed deployments.

**Version note:** converting non-unique indexes to unique via `collMod` is supported from MongoDB 6.0; `validationAction:"errorAndLog"` from MongoDB 8.1; `validationLevel:"constraint"` from MongoDB 9.0. Always verify your cluster's version, FCV, and tier before production runs.

## 31. Conclusion

Enforcing constraints on a populated MongoDB collection is **both a technical migration and a business-contract transition**.

1. **Define exact invariants** before mutating anything: required/nullable/BSON types, per-tenant uniqueness, retention, and exception policies.
2. **Audit by category**: missing, null, wrong types, enums, normalization, and duplicates; never rely on a single `countDocuments` number as complete proof.
3. **Block new violations** before finishing historical cleanup: deploy compliant writers, and use `moderate + error` and `prepareUnique` where supported.
4. **Clean according to business sources of truth**, never auto-deleting duplicates or replacing monetary values with 0. Backfill in batches with CAS, idempotency, and checkpoints.
5. **Re-verify** document validity, uniqueness, business totals, and references; audit records requiring manual resolution.
6. **Enable target constraints deliberately**: `unique:true` after `dryRun`; `strict + error` after audit; evaluate `constraint` on MongoDB 9.0+ when full-collection guarantees are needed.
7. **Maintain recoverability**: backups/restore, config rollbacks, and forward-fixes; understand that deleted/merged records and finalized unique constraints do not revert at the push of a button.
8. **Monitor post-rollout**: validator/duplicate errors, p95/p99, replication, disk, schema versions, and business outcomes.

**Core principle:** new constraints are not an “automatic garbage-cleanup command.” They are a long-term commitment that **historical data has been reconciled and every future write path obeys the exact same contract**—across deployments, rollbacks, retries, scale-outs, and incidents.
