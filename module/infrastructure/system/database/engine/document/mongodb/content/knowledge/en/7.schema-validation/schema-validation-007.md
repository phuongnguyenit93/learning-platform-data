# Updating Validators, Compatible Rollouts, and bypassDocumentValidation Limits

MongoDB allows documents within a collection to have differing structures. Even so, production systems still need a data contract: which fields are required, which BSON types are valid, which values are accepted, and how historical data should be handled when that contract changes. **Schema validation** lets MongoDB enforce those rules at write time. Changing a validator is therefore a **data-compatibility change** requiring a controlled rollout, not merely an administrative command.

This lesson belongs to the **Schema validation** chapter and focuses on three interconnected topics: **updating validators with `collMod`**, **rolling out compatibly alongside existing application versions and legacy documents**, and **the limits of `bypassDocumentValidation`**. Examples use `mongosh` on the practice database `schema_lab`.

After this lesson, you will be able to:

1. Inspect and modify a collection's `validator`, `validationLevel`, and `validationAction`.
2. Explain the differences between `strict`, `moderate`, `off`, and MongoDB 9.0's `constraint` level.
3. Roll out schemas across the **expand → observe → migrate → enforce → clean up** phases.
4. Locate non-conforming documents using `$jsonSchema` combined with `$nor`.
5. Distinguish `bypassDocumentValidation` from modifying a validator, disabling validation, and bypassing other constraints.
6. Recognize risks during application rollbacks, server upgrades, data imports, and enforcement tightening.

> **Versions:** Most examples below apply to MongoDB 7.0/8.0. `validationAction: "errorAndLog"` was added in MongoDB **8.1**; `validationLevel: "constraint"` and `prepareConstraintValidationLevel` arrived in MongoDB **9.0**. For production, always verify your exact MongoDB Server version, FCV, and matching documentation branch before use.

## 1. Schema Validation in MongoDB Architecture

A **collection validator** is a logical expression used to check documents on insert/update within the configured scope. Most commonly this is `$jsonSchema`, though MongoDB also supports suitable query expressions.

~~~text
Client / Java Driver / mongosh
             |
             v
MongoDB Server receives write command
             |
             +-- check privileges and command syntax
             +-- select validation scope per validationLevel
             +-- evaluate document against validator
             |        |
             |        +-- valid -> proceed with write
             |        +-- invalid, action=error -> reject
             |        +-- invalid, action=warn -> write and log warning
             |
             +-- other constraints: unique indexes, BSON limits...
             v
      Storage engine persists data
~~~

This is a **write-time guardrail**, not an automated legacy data conversion tool. Updating a validator with `collMod` does not scan and rewrite stored documents. If a collection holds legacy documents failing the new rules, how those documents are affected depends on `validationLevel`.

### 1.1. What Can a Validator Check?

| Rule | Example |
|---|---|
| Required fields | `required: ["name", "email"]` |
| BSON types | `bsonType: "string"`, `bsonType: "date"` |
| Multiple valid types | `bsonType: ["int", "long"]` |
| Restricted values | `enum: ["ACTIVE", "DISABLED"]` |
| Numeric min/max | `minimum: 0`, `maximum: 100` |
| String length | `minLength: 3` |
| String pattern | `pattern: "^..."` |
| Nested objects | `properties.address.properties.city` |
| Arrays | `items`, `minItems`, `maxItems` |
| Logical conditions | Query operators supported inside validators. |

Example rule for a user:

~~~javascript
const userSchemaV1 = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "status"],
    properties: {
      name: {
        bsonType: "string",
        minLength: 1,
        description: "name must be a non-empty string"
      },
      status: {
        enum: ["ACTIVE", "DISABLED"]
      },
      email: {
        bsonType: "string",
        description: "email must be a string if present"
      }
    }
  }
}
~~~

Here `name` and `status` are required, whereas `email` is **optional** yet must be a string if present. Distinguishing a missing field from `email: null` is critical: `null` is a BSON type, not a string, so it fails `bsonType: "string"`. To permit null, define it explicitly—for example, `bsonType: ["string", "null"]`.

### 1.2. What Validators Do Not Guarantee by Themselves

- **Collection-wide uniqueness:** to make `email` unique, use a **unique index**; `required` does not replace a unique index.
- **Foreign keys:** storing `customerId` does not verify that a matching customer document exists.
- **Multi-document transactions:** schema validation does not make updates across two collections atomic together.
- **Access control:** validators do not replace authorization.
- **Full business logic:** rules involving payments, external services, or complex state workflows still belong in the appropriate layer.
- **Legacy data:** changing rules does not automatically backfill or certify existing documents as valid.

Even when an operation is allowed to **bypass** validation, independent constraints like unique indexes and write privileges remain in force.

## 2. The Trio: `validator`, `validationLevel`, `validationAction`

Think of the configuration as three questions:

~~~javascript
{
  validator: { /* when is a document valid? */ },
  validationLevel: "strict",      // which operations are checked?
  validationAction: "error"       // what happens on violation?
}
~~~

### 2.1. Meaning of validationLevel

| Level | New Inserts | Updates to Currently Valid Docs | Updates to Currently Invalid Docs |
|---|---|---|---|
| **`strict`** | Checked | Checked | Checked |
| **`moderate`** | Checked | Checked | Not required to pass validation |
| **`off`** | Not checked | Not checked | Not checked |
| **`constraint`** (9.0+) | Checked | Checked | No invalid documents may exist in collection once upgrade succeeds |

**`strict`** is the default. When updating a legacy document that violates a new rule, MongoDB checks the **post-update document state**. A command updating only `lastSeenAt` will still be rejected if the document continues to lack a required field.

**`moderate`** applies validation to inserts and to updates of documents that **already conform to the schema**. Documents that are **already invalid** may continue to be updated without passing validation. The goal is to keep operations running on legacy data during a transition window; it neither fixes data automatically nor guarantees invalid records eventually vanish.

**`off`** disables schema checks for inserts/updates; the validator expression may remain stored in metadata. This is a collection-wide control mode, unlike per-operation bypass.

**`constraint`** arrives in MongoDB **9.0** with a stronger invariant: upon upgrading, MongoDB checks every document in the collection and disallows `bypassDocumentValidation`. Section 9 explains the process and restrictions of this level.

### 2.2. Meaning of validationAction

| Action | Result If an In-Scope Operation Produces an Invalid Document | Version Note |
|---|---|---|
| **`error`** | Reject write. | Default and most common. |
| **`warn`** | Allow write and log warning to MongoDB log. | Suited for observation phases. |
| **`errorAndLog`** | Reject write **and** log error. | Available from MongoDB 8.1. |

`validationLevel` determines **whether to validate**; `validationAction` determines **how to handle failure**. For instance, `moderate + warn` does not mean every update to an invalid document logs a warning, because updates to already-invalid documents fall outside validation scope.

### 2.3. Comparing Combinations

| Combination | Practical Consequence |
|---|---|
| **strict + error** | Blocks new invalid inserts/updates; legacy invalid docs may persist until repaired. |
| **strict + warn** | Logs write violations while still letting invalid data enter the collection. |
| **moderate + error** | Inserts and updates to currently valid docs are checked; invalid legacy docs can still be updated. |
| **moderate + warn** | Warns only within checked scope; zero warnings does not prove data is clean. |
| **off + error** | No schema checks run, even though action remains `error`. |
| **constraint + error** (9.0+) | Entire collection is verified on upgrade; bypass is blocked. |

### 2.4. Example: New Rule Invalidating Old Documents

Initially the system allowed:

~~~javascript
{ _id: "U1", name: "An", email: "an@example.test" }
{ _id: "U2", name: "Binh" }
~~~

If the new rule requires `email`, document `U2` **does not disappear** when `collMod` runs. Under `strict + error`, an update like the following fails because the post-update result still lacks `email`:

~~~javascript
db.getSiblingDB("schema_lab").users.updateOne(
  { _id: "U2" },
  { $set: { lastSeenAt: new Date() } }
)
~~~

Under `moderate + error`, the already-invalid `U2` can be updated without fixing `email` yet. The downside is that malformed data can linger for a long time.

## 3. Inspecting Current Configuration Before Modifying

Use `getCollectionInfos` to read collection options:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const infoList = lab.getCollectionInfos({ name: "users" })

if (infoList.length === 0) {
  print("Collection users does not exist yet")
} else {
  printjson(infoList[0].options)
}
~~~

Or via database command:

~~~javascript
lab.runCommand({
  listCollections: 1,
  filter: { name: "users" }
})
~~~

The output may contain `options.validator`, `options.validationLevel`, and `options.validationAction`. Options left at default values sometimes **do not appear explicitly**; when reading back, cross-check your server version's defaults. Save the previous configuration before every rollout so you can roll back cleanly.

### 3.1. Creating a Practice Collection with an Initial Validator

Run these commands in a **test database that does not yet have a `users` collection**:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const oldValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string", minLength: 1 }
    }
  }
}

lab.createCollection("users", {
  validator: oldValidator,
  validationLevel: "strict",
  validationAction: "error"
})

lab.users.insertMany([
  { _id: "U1", name: "An", email: "an@example.test" },
  { _id: "U2", name: "Binh" },
  { _id: "U3", name: "Chi", email: 123 }
])
~~~

All three documents satisfy the **old** schema because only `name` is constrained. Under the **new** schema requiring `email` to be a string, `U2` lacks `email` and `U3` has the wrong type for `email`.

## 4. Replacing a Validator with `collMod`

For an **existing** collection, use `collMod`:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: nextValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
~~~

The command sets a **complete validator expression** and switches to warning mode for observation. `collMod` returns `ok: 1` on success; always **read back** metadata with `getCollectionInfos`.

### 4.1. `collMod` Does Not Migrate Legacy Data

Immediately after the command, `U2` and `U3` still remain with their old values. Under `strict` and `moderate`, MongoDB does not scan and rewrite old documents. The change affects **subsequent inserts and updates**.

For example, the same write producing an invalid document:

- `strict + warn`: operation succeeds and logs a warning.
- `strict + error`: operation is rejected.
- `moderate + error`: behavior depends on whether the pre-update document satisfied the rules.

### 4.2. Changing Action/Level While Keeping the Validator

To switch to rejecting invalid writes once data is cleaned up:

~~~javascript
lab.runCommand({
  collMod: "users",
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Only the specified options change. Conversely, when passing a new `validator`, treat it as **replacing the validator expression**—never assume MongoDB deep-merges `properties` or `required` from earlier rules. Maintain the **entire canonical schema** under version control in your repository to avoid accidentally dropping prior rules.

### 4.3. Reading Back Configuration

~~~javascript
const options = lab.getCollectionInfos({ name: "users" })[0].options

printjson({
  validator: options.validator,
  validationLevel: options.validationLevel,
  validationAction: options.validationAction
})
~~~

This readback proves collection options changed; it **does not** prove every stored document conforms to the new schema.

### 4.4. Privileges and Operational Impact

`collMod` requires the `collMod` privilege; the built-in `dbAdmin` role includes the necessary permissions for normal collections. According to the MongoDB Manual, this command acquires a **collection lock** while running. Assess system load and pick an appropriate maintenance window, especially alongside live traffic and other DDL operations.

Per documented restrictions, validators cannot be placed on collections in the `admin`, `local`, or `config` databases or on `system.*` collections. Specialized collections have their own constraints; never copy commands onto another namespace without checking first.

## 5. Finding Documents Violating the New Schema

MongoDB lets you use a `$jsonSchema` expression inside a query to classify documents before altering the validator:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

// Schema-valid documents:
lab.users.find(nextValidator)

// Schema-INVALID documents:
lab.users.find({ $nor: [nextValidator] })

// Count invalid documents:
lab.users.countDocuments({ $nor: [nextValidator] })
~~~

In the sample data, the invalid query returns `U2` and `U3`. `$nor` negates the full schema predicate. This is an essential tool for planning **backfills** and measuring before/after migration counts.

Diagnostic queries by field:

~~~javascript
const missingEmail = lab.users.countDocuments({
  email: { $exists: false }
})

const emailNotString = lab.users.countDocuments({
  email: { $exists: true, $not: { $type: "string" } }
})

printjson({ missingEmail, emailNotString })
~~~

Those two counts only isolate specific causes. If the schema also constrains regexes, nested objects, enums, or lengths, use the **full `$jsonSchema`** to determine the invalid set. On large collections, scanning can consume significant I/O and CPU; benchmark in a comparable environment, use sampling/batching, and avoid pulling entire documents into client memory just to count them.

### 5.1. Difference Between Auditing Data and Changing the Contract

| Operation | Modifies Validator? | Modifies Documents? | Purpose |
|---|---:|---:|---|
| `find({$nor:[schema]})` | No | No | Locate non-conforming data. |
| `countDocuments({$nor:[schema]})` | No | No | Measure remediation scope. |
| `collMod` with `validator` | Yes | No | Change write-time contract. |
| `updateOne`/backfill | No | Yes | Repair existing documents. |
| `collMod` with `validationAction` | Yes | No | Change how invalid writes are handled. |

When `collMod` returns `ok: 1`, you have only verified **metadata changed**. Never report "all data is migrated" until the data migration itself has executed and been reconciled.

## 6. Compatible Rollout: expand → observe → migrate → enforce

Suppose a production environment has multiple application instances writing to the `users` collection:

- **App v1** requires only `name`; `email` may be absent.
- **App v2** will require `email` to be mandatory and a string.
- The database already contains `U2` missing `email` and `U3` holding a numeric type.
- During a rolling deployment, **v1 and v2 run concurrently** for a window.

Enabling `strict + error` immediately for the new validator could break requests from App v1 and reject updates to legacy documents. Therefore, follow a contract transition sequence.

### 6.1. Phase 0 — Inventory and Define Invariants

Before altering collection options:

1. Define the **target schema**, noting which changes relax rules and which tighten them.
2. Inventory **all writers**: web apps, cron jobs, batch imports, ETL, data syncs, admin tools, and legacy apps.
3. Record **MongoDB Server version, FCV, driver versions**, and topology to consult exact docs.
4. Count invalid documents against the new rule, classifying missing/type/value mismatches.
5. Identify authoritative sources for backfilling. **Never fabricate values** just to pass validation.
6. Define phase gates: invalid counts, invalid write rates, writer compatibility status, latency, and error rates.
7. Save the prior validator configuration, application rollback plan, and data migration plan.

If business rules allow users who have **not completed onboarding** to lack an email, the rule "every user must always have an email" may be wrong. In that case, design a conditional schema tied to user status rather than forcing dummy emails.

### 6.2. Phase 1 — Expand Applications to Handle Both Old and New Data

Deploy application versions capable of:

- **Reading legacy data** with missing or wrong-typed `email` without crashing; handling or flagging records needing completion.
- **Writing new data** conforming to the target schema; do not wait for server rejections to fix writers.
- Providing an update path for legacy documents aligned with business policy.
- Remaining compatible during the window when **v1 and v2 coexist**.
- Updating often-overlooked producers: async consumers, import tools, scheduled jobs, and maintenance scripts.

If you only update `POST /users` while overlooking `PUT/PATCH`, `replaceOne`, or `bulkWrite` jobs, unexpected failures will appear once enforcement turns on. Do not tighten rules the moment a single v2 instance starts; ensure **all necessary writers** are compatible first.

### 6.3. Phase 2 — Install Target Schema in `strict + warn`

In the target environment, run:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: nextValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
~~~

Because the action is `warn`, invalid documents **can still be inserted/updated**. MongoDB logs warnings for operations violating validation within scope. This is a **compatibility observation** phase, not enforcement.

Track warnings by **namespace**, time, and application version where instrumented. Logs may include sensitive document/field details, so apply access restrictions and redaction policies. Use `$nor: [nextValidator]` to count actual invalid documents; **never rely solely on warning counts**.

Phase exit criteria must reflect real workloads. For example, a weekend-only batch job has not been verified by 30 minutes of morning traffic observation.

### 6.4. Phase 3 — Migrate/Backfill Legacy Data

Once you have trustworthy data sources, repair legacy documents **in batches**. In the lab database, suppose the emails for `U2` and `U3` were verified by the data owner:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

lab.users.updateOne(
  { _id: "U2", email: { $exists: false } },
  { $set: { email: "binh@example.test" } }
)

lab.users.updateOne(
  { _id: "U3", email: 123 },
  { $set: { email: "chi@example.test" } }
)

const remaining = lab.users.countDocuments({
  $nor: [nextValidator]
})
print("Remaining invalid documents: " + remaining)
~~~

**This is sample data, not guidance to invent default emails.** In real data, if the true email is unknown, establish a collection/consent workflow or model a status that explicitly allows missing email.

At multi-million-record scale, apply:

- **Batching/checkpointing** by `_id` or deterministic key ranges.
- Filter predicates protecting records concurrently updated by live clients.
- **Idempotent** backfills safe to rerun after failures without unintended side effects.
- Monitoring of read/write throughput, replication lag, storage load, and write conflicts.
- Tracking processed/failed counts and records needing manual intervention.
- Never relying on `updateMany` as an atomic collection-wide transaction.

Do not forget nested objects/arrays: changing a nested schema can invalidate large documents that are hard to backfill with a simple `$set`.

### 6.5. Phase 4 — Enforce with `strict + error`

Once all writers are compatible and invalid documents are resolved:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const invalidCount = lab.users.countDocuments({
  $nor: [nextValidator]
})

if (invalidCount > 0) {
  throw new Error("Still invalid: " + invalidCount)
}

lab.runCommand({
  collMod: "users",
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Understand the limit of counting: if an old producer can still write under `warn` **between the count and the enforce step**, new invalid documents can sneak in. Thus the gate is never just a zero count: control writers, verify rollout timing, and execute changes cleanly.

Once enforced, new invalid writes within validation scope are rejected. However, `strict + error` **does not mean the server scanned and certified all existing documents**; pre-enforcement auditing remains the rollout team's responsibility. MongoDB 9.0+ offers `constraint` for a stronger invariant.

### 6.6. Phase 5 — Monitor and Retire Legacy Support When Ready

Post-rollout:

- Monitor `DocumentValidationFailure` errors by endpoint, job, and app version.
- Track invalid document counts, lingering warning logs, and incompatible tasks.
- Keep validator and application rollback paths ready during the monitoring window.
- Remove legacy read code only after confirming no legacy data still requires support.
- Record **schema version**, deployment date, and migration reference for future operators.

In multi-service architectures, **app rollbacks** must be checked for compatibility with the **new schema**. Never blindly roll back to a v1 writer that creates email-less users while `strict + error` remains active.

## 7. `moderate` as an Alternative Transition Strategy

If legacy invalid documents are numerous yet you need to start blocking new invalid inserts immediately, `moderate + error` is a viable option:

~~~javascript
db.getSiblingDB("schema_lab").runCommand({
  collMod: "users",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "email"],
      properties: {
        name: { bsonType: "string" },
        email: { bsonType: "string" }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
})
~~~

Under this setting:

1. New **inserts** must pass the rules.
2. Updates to **currently valid** documents must produce valid documents.
3. Updates to **already invalid** documents do not have to pass validation.

For instance, if `U2` lacks `email`, a job updating only `lastSeenAt` can keep working. However, `moderate` does not guarantee `email` will ever be fixed; further updates to invalid documents could even introduce additional violations.

### 7.1. Choosing `moderate` vs. `strict + warn`

| Goal | Suitable Starting Option | Accompanying Conditions |
|---|---|---|
| Observe every write violating the new schema | **strict + warn** | Accepts invalid writes; collect logs and clean data. |
| Block new invalid docs while legacy cleanup is incomplete | **moderate + error** | Maintain backfill schedule and invalid counts; do not leave permanently. |
| All writers and data are compatible | **strict + error** | Reconcile data and monitor errors post-deploy. |
| Temporarily skip checks on inserts/updates | **off** | Only with clear justification and deadline; risks new invalid data. |
| Guarantee clean collection and block bypass, server 9.0+ | **constraint** | Scan/migrate data, run prepare step, and upgrade separately. |

Never pick `moderate` merely because it lowers error counts: lower error counts do not mean data quality improved.

## 8. `bypassDocumentValidation`: Per-Operation Exceptions

`bypassDocumentValidation` is an option on supported write commands. When enabled on an operation by an authorized user, MongoDB can **skip the collection schema validator** for that specific operation. A legitimate use case is restoring or importing historical records that do not yet match the current schema, paired with a remediation plan.

It **is not**:

- a permanent change to the collection;
- a flag automatically applied to an entire session or application;
- a way to make invalid fields valid;
- a way to bypass unique indexes, BSON limits, write privileges, or command rules;
- a substitute for controlled migrations.

### 8.1. Example: Bypassing an Insert

Suppose the collection requires `name` and `email` as strings under `strict + error`. Normally, this insert fails:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

lab.users.insertOne({
  _id: "U-LEGACY",
  name: "Legacy User"
  // Missing email.
})
// Error: Document failed validation.
~~~

An account **granted bypass privileges** can issue an `insert` command with the option:

~~~javascript
lab.runCommand({
  insert: "users",
  documents: [
    {
      _id: "U-LEGACY",
      name: "Legacy User"
    }
  ],
  bypassDocumentValidation: true
})
~~~

The invalid document is inserted provided the command meets all other rules, holds sufficient privileges, and the collection **is not in a bypass-blocking state** such as MongoDB 9.0's `constraint`.

Bypass applies only to **this operation**. A future update under `strict + error` must produce a schema-valid document or use bypass again. Once a verified email is available, fix the document:

~~~javascript
lab.users.updateOne(
  { _id: "U-LEGACY", email: { $exists: false } },
  { $set: { email: "verified@example.test" } }
)
~~~

Because the post-update state contains a string `email`, the repair succeeds even though the document was previously invalid. In production, emails must be verified; never invent fake addresses just to "pass the rule."

### 8.2. Operation Groups Supporting the Bypass Option

Per the MongoDB Database Manual, supported groups include:

| Group | Listed Commands / Methods |
|---|---|
| Inserts | `insert` command and supporting APIs. |
| Updates | `update` command and supporting APIs. |
| Find and modify | `findAndModify` command, `db.collection.findAndModify()`. |
| Writing aggregations | `aggregate` with `$out` or `$merge`. |
| Specialized tools | `applyOps`, `mapReduce` on versions still supporting it. |

Some drivers and shell helpers place options differently than raw database commands. Never assume **every CRUD method** accepts the same option signature. Always check the driver API for your exact version and the Server Manual before use.

Example `update` database command:

~~~javascript
lab.runCommand({
  update: "users",
  updates: [
    {
      q: { _id: "U-LEGACY" },
      u: { $set: { importBatch: "B-2026-11" } },
      multi: false
    }
  ],
  bypassDocumentValidation: true
})
~~~

This command modifies a field **unrelated to email** and intentionally skips validation. If the document remains invalid, adding `importBatch` does not make it valid. Every such bypass must have a documented purpose, time limit, and backlog remediation path.

### 8.3. Required Privileges

When authorization is enabled, the account needs **the required write privileges** plus the **`bypassDocumentValidation`** action on the target resource. MongoDB lists the built-in roles **`dbAdmin`** and **`restore`** as including the bypass action. However, holding the bypass action **does not grant** arbitrary write permissions on every collection: command-specific write privileges are still checked.

Normal application accounts that only read/write valid data **should not hold bypass privileges**. Use a dedicated migration/restore account scoped to the right resource, log its purpose, batch, and operator, and revoke the privilege afterward. Never fix validation errors by granting overly broad roles like `root` to an entire application.

### 8.4. Constraints Bypass Cannot Override

| Constraint | Does Bypass Skip It? |
|---|---|
| Collection validator (when level permits) | **Yes**, for that specific operation with proper privileges. |
| Unique indexes, duplicate keys | **No**. |
| 16 MiB BSON document limit | **No**. |
| Authentication / insert / update privileges | **No**. |
| Command/namespace type rules | **No**. |
| Pre-send validation in app/driver | Not necessarily. |
| Write concern, transactions, replication | **No**. |
| Foreign-key logic or business rules | Unrelated; must be handled separately. |
| MongoDB 9.0 `constraint` / `prepareConstraintValidationLevel` | **Cannot be bypassed**, even with privileges. |

If a collection has a unique index on `email`, setting `bypassDocumentValidation: true` still **will not** allow two documents with the same email. If an account lacks insert permission, holding the bypass privilege is still **not enough** to write.

### 8.5. Controlled Exception Process

A restore or migration requiring bypass should document:

1. Target collection and exact data batch permitted to bypass.
2. Rationale for retaining data prior to schema compliance.
3. Document counts, invalid fields, and post-import remediation plan.
4. Account/role used and expiration window.
5. Before/after `$nor` scans and an owned backlog list.
6. When the bypass path is shut off and verified unused by applications.

Whenever possible, import into a **staging collection** first, clean the records, and then promote into the target collection. That is usually far cleaner than leaving bypass enabled in production applications.

## 9. Bypass Restrictions in MongoDB 9.0: `constraint` Level

MongoDB 9.0 adds `validationLevel: "constraint"` to provide **stronger collection-wide guarantees**. Unlike `strict`, this level requires every existing document to pass the validator at upgrade time; the server runs a scan during the transition.

Per the MongoDB 9.0 Manual:

1. `constraint` works only with `validationAction: "error"` or `"errorAndLog"`; `warn` is invalid.
2. When level is `constraint`, **`bypassDocumentValidation` is prohibited**, even for users holding bypass privileges.
3. During `prepareConstraintValidationLevel: true`, the server also blocks writes passing `bypassDocumentValidation: true` and prevents arbitrary validator edits.
4. Bypass is rejected **even when the document itself is valid** if the command explicitly includes `bypassDocumentValidation: true`.
5. To edit a validator while in `constraint`, step down to `strict`, update the rules, and go through the `constraint` upgrade sequence again.
6. When upgrading to `constraint`, the entire collection is verified; if any document fails, the upgrade command fails.

This is a major shift from the older assumption that "having the privilege lets you bypass any validator." Never omit this version distinction from runbooks.

### 9.1. Illustrative Workflow to Upgrade to constraint

**Use only on MongoDB 9.0+** after reviewing documentation and verifying server/FCV:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

// Assumes the right validator is installed under strict + error,
// all writers are compatible, and all data conforms to the schema.

// Preparation step: block bypass and lock validator edits.
lab.runCommand({
  collMod: "users",
  prepareConstraintValidationLevel: true
})

// Upgrade step: MongoDB verifies all existing documents.
lab.runCommand({
  collMod: "users",
  validationLevel: "constraint",
  validationAction: "error"
})
~~~

Do not pass a new `validator` in the same command that upgrades to `constraint`; complete all validator updates and backfills beforehand. On large collections, the scan can take considerable time and resources, so assess maintenance windows, lock duration, replication impact, and recovery plans prior to running.

If the upgrade fails due to invalid documents, investigate and remediate those records against the schema. Do not reach for bypass, as prepare/constraint is specifically designed to **close off the bypass path**.

### 9.2. Re-Enabling Bypass Capability When Genuinely Needed

In MongoDB 9.0, documentation states that re-allowing bypass requires:

- If the collection is already in `constraint`: revert `validationLevel` back to `strict`.
- If currently in the `prepareConstraintValidationLevel: true` phase: cancel the prepare state via `collMod`.

This is a **collection policy change** with data-assurance consequences, requiring the same approval and change tracking as any validator modification. Never embed a downgrade command inside an automated import script just to push an import through.

### 9.3. Compatibility When Upgrading/Downgrading MongoDB Versions

| Feature | Release Line to Remember |
|---|---|
| `strict`, `moderate`, `off` | Available in pre-9.0 MongoDB branches, including 7.0/8.0. |
| `validationAction: "error"`, `"warn"` | Standard options in branches prior to 8.1. |
| `validationAction: "errorAndLog"` | Introduced in **MongoDB 8.1**. |
| `validationLevel: "constraint"` | Introduced in **MongoDB 9.0**. |
| `prepareConstraintValidationLevel` | Introduced in **MongoDB 9.0**. |

If a collection uses options introduced in a newer release, downgrading MongoDB Server may require altering those options first. Always read the exact version's release notes and downgrade guide; **a newer `mongosh` client does not add features missing on the server**.

## 10. Validation Errors and Application Error Handling

### 10.1. DocumentValidationFailure Differs from Write Conflict Errors

When a write is rejected under `validationAction: "error"`, MongoDB typically returns **`DocumentValidationFailure`**, code **121**. Depending on server version, error details may include `failingDocumentId`, `details`, `schemaRulesNotSatisfied`, and the failing field/rule names.

~~~javascript
const lab = db.getSiblingDB("schema_lab")

try {
  lab.users.insertOne({
    _id: "U-BAD",
    name: "Mai"
    // Missing email.
  })
} catch (err) {
  print("code=" + err.code)
  print("codeName=" + err.codeName)
  print(err.message)
}
~~~

This is a **data-contract error**, distinct from:

- **`DuplicateKey`** (usually code 11000): unique index violation.
- **Write conflict / transient transaction error**: concurrency contention, potentially retryable per context.
- **Network timeout**: unclear whether the server received or completed the operation.
- **Write concern timeout**: required write acknowledgment not met within timeout.
- **Unauthorized**: account lacks privileges.

Never infinitely retry a document that is still missing `email`. Retries help transient failures, yet cannot turn schema-invalid data into valid data. Applications must fix input or follow business-rule error handling.

### 10.2. A Batch Can Partially Succeed

`insertMany` and `bulkWrite` are not inherently atomic multi-document transactions across an entire batch. Under `strict + error`, valid documents may be written while invalid ones are rejected. Behavior depends on `ordered/unordered` mode and driver API.

~~~javascript
db.getSiblingDB("schema_lab").users.insertMany(
  [
    { _id: "U-OK-1", name: "Ha", email: "ha@example.test" },
    { _id: "U-NO-EMAIL", name: "Nam" },
    { _id: "U-OK-2", name: "Vy", email: "vy@example.test" }
  ],
  { ordered: false }
)
~~~

With `ordered: false`, valid elements still succeed even though `U-NO-EMAIL` is rejected; the driver throws an aggregate bulk write error. In migrations, inspect **per-item results** and retry idempotently by identity—never blindly resend the entire batch without checking what already persisted.

### 10.3. Post-Rollout Observability

Signals to collect:

| Source | What It Tells You | Limitation |
|---|---|---|
| MongoDB validation warning logs | Checked writes creating invalid docs under `warn`. | May contain sensitive data; not a snapshot of all legacy data. |
| `DocumentValidationFailure` errors | Writes blocked by rules under `error`. | Zero errors does not prove the whole collection is clean. |
| `$nor: [schema]` scans | Stored documents currently failing the queried schema. | Can be resource-heavy; needs periodic reconciliation. |
| `getCollectionInfos` | Active validator/level/action configured on collection. | Metadata only; does not inspect stored documents. |
| Application metrics | Endpoints/jobs/client versions triggering errors and user impact. | Needs proper correlation; avoid logging only raw message strings. |
| Bulk write results | Succeeded/failed counts inside a batch. | Must account for ordered/unordered, write concern, and retries. |

**Never conclude "zero warnings means zero invalid documents."** Legacy data may already exist; `moderate` may skip checking updates to invalid docs; or the failing batch job may not have run during the observation window.

### 10.4. Do Not Depend on Exact Error Message Strings

The shape of `errInfo`/`details` and descriptive text can change across MongoDB versions. Code should check driver error codes/exception types, use structured metadata where available, and return user-friendly responses without exposing sensitive documents or schema internals.

## 11. Common Pitfalls When Changing JSON Schemas

### 11.1. `required` and `properties` Do Two Different Things

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string" },
      email: { bsonType: "string" }
    }
  }
}
~~~

The document must contain `name`. `email` may be absent, yet if present must be a string. Adding `email` to `required` is a **breaking change** for legacy documents and producers.

### 11.2. Missing, null, and Wrong Type

Suppose rules include both `required: ["email"]` and `email: { bsonType: "string" }`:

| Document | `required` | `bsonType: "string"` | Result Under Both Rules |
|---|---|---|---|
| `{}` | Fails | Not evaluated when missing | Invalid. |
| `{email: null}` | Passes because field exists | Fails | Invalid. |
| `{email: 42}` | Passes | Fails | Invalid. |
| `{email: "a@example.test"}` | Passes | Passes | Passes both rules. |

If `null` must be tolerated during a transition phase, use `bsonType: ["string", "null"]` and tighten once no documents carry `null`. Even that requires rolling out like any other type change.

### 11.3. BSON Types Differ from JavaScript Types

`bsonType: "int"` accepts only BSON Int32; `"long"` is Int64, `"double"` is double-precision float, and `"decimal"` is Decimal128. Shells and drivers can encode numbers into different BSON types. On a collection already mixing numeric types, never tighten immediately to a narrow `bsonType` without measuring current data. Use `NumberInt`, `NumberLong`, or explicitly support multiple types per business rules:

~~~javascript
{
  $jsonSchema: {
    properties: {
      quantity: { bsonType: ["int", "long"] }
    }
  }
}
~~~

This is only a single-field snippet; a full schema must still decide `required` and bounds. Do not confuse `bsonType` with standard JSON Schema's `type`: MongoDB uses its own BSON type system.

### 11.4. `additionalProperties: false` Easily Blocks `_id`

MongoDB documents almost always contain `_id`. If a schema sets `additionalProperties: false` without declaring `_id` in `properties`, documents carrying `_id` are rejected for having an unpermitted field.

Risky example:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    properties: {
      name: { bsonType: "string" }
    }
  }
}
~~~

Adjusted example:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    properties: {
      _id: { bsonType: ["objectId", "string"] },
      name: { bsonType: "string" }
    }
  }
}
~~~

Allow only the `_id` types actually used by the collection; the snippet above illustrates syntax. Blocking unknown fields can break rolling deployments if a new app version writes a field before the validator allows it. Plan to expand the schema before deploying writers that emit new fields.

### 11.5. Regexes and Complex Conditions

`pattern` is handy for simple formatting rules, yet a regex **cannot verify whether an email belongs to a real recipient**. Likewise, validators do not create unique constraints. Overly complex expressions can also add write-path evaluation overhead. Balance **shared data constraints**, **business-layer validation**, and **performance**.

### 11.6. Updates, Replacements, and Pipelines Must All Be Compatible

Depending on `validationLevel`, MongoDB checks the **post-operation result**:

- `updateOne` touching only `lastSeenAt` can still be rejected if a legacy document lacks `email`.
- `replaceOne` can accidentally strip required fields if the replacement builder omits legacy fields.
- `findOneAndUpdate` is subject to validation just like other updates within scope.
- Aggregations ending in `$merge`/`$out` and import jobs can write into validated collections.
- Infrequent writers (maintenance scripts, restores, scheduled jobs) are still part of rollout scope.

Testing only `insertOne` after updating a validator is never enough to prove application compatibility.

## 12. Rollback and Configuration Management

### 12.1. Saving the Previous Schema Before Rollout

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const info = lab.getCollectionInfos({ name: "users" })[0]
printjson(info.options)
~~~

Keep the canonical versioned schema in source control alongside deployment date, change rationale, reconciliation results, and owner. Never rely on memory when rolling back during an incident.

### 12.2. Example: Restoring Validator v1

Suppose the initial validator only required `name`:

~~~javascript
const previousValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string", minLength: 1 }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: previousValidator,
  validationLevel: "strict",
  validationAction: "error"
})
~~~

This rolls back **validator metadata**; it **does not undo backfilled data**, delete fields written by new app versions, or revert external side effects. If a migration altered types or removed fields, maintain a dedicated data rollback plan that avoids overwriting valid user updates made after the migration.

### 12.3. Temporarily Switching to `warn` During an Incident

An emergency mitigation is switching to `warn` to stop write errors while fixing the application:

~~~javascript
lab.runCommand({
  collMod: "users",
  validationAction: "warn"
})
~~~

This **allows new invalid documents to enter**, so use it only if business and operational policies accept the risk. Establish an expiration time, owner, and cleanup workflow. Under MongoDB 9.0 `constraint`, `warn` is invalid; follow the supported downgrade-level and rule-change procedure.

### 12.4. Metadata Rollback Differs from Server Downgrade

If you used MongoDB 8.1/9.0 features such as `errorAndLog` or `constraint`, never assume a single `collMod` makes the server safe to downgrade. Consult the exact version's **upgrade/downgrade guide** and FCV rules. This is especially critical when schema changes ship alongside a MongoDB Server upgrade.

## 13. Role-Based Rollout Workflow

| Phase | Verification Items | Typical Owner |
|---|---|---|
| Design | Schema contract, breaking/non-breaking changes, BSON types, business exceptions. | Developer + data owner. |
| Inventory | All writers, server/driver versions, current validator, legacy data. | Developer + DBA/SRE. |
| Preparation | Canonical schema source, idempotent backfill scripts, test/rollback plans. | Developer + DBA. |
| Expand | Readers tolerate legacy data; new writers emit only valid data. | Application team. |
| Observe | `strict + warn`, inspect warnings and count invalid docs against new schema. | DBA/SRE + app team. |
| Migrate | Batched updates, checkpoints, authoritative source verification, reconciliation. | Data owner + migration team. |
| Enforce | All writers compatible, invalid count controlled, `strict + error`. | DBA/SRE via change plan. |
| Optional 9.0 | If stronger guarantees needed, prepare and scan to upgrade to `constraint`. | DBA/SRE. |
| Post-rollout | Monitor errors, drift, legacy cleanup, restrict bypass privileges. | Operations + application. |

To prevent validator drift, deployment pipelines can compare live collection options against versioned schemas in source control—remembering that default options may not appear explicitly in `getCollectionInfos`. Metadata readback and document reconciliation are **two distinct forms of evidence**.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "Once `collMod` runs, old data is automatically valid." | It only updates metadata; audit and backfill separately. |
| "`strict` guarantees no invalid documents remain in the collection." | Legacy documents persist until fixed; 9.0 `constraint` provides the stronger invariant. |
| "`moderate` is the same as `warn`." | `moderate` controls validation scope; `warn` controls violation handling. |
| "`warn` means no validation runs." | Validation still checks and logs violations without rejecting writes. |
| "Switching to `error` cleans up data automatically." | No; repair documents or adjust rules per business logic. |
| "Zero warnings means all data is clean." | Legacy data and unchecked operations may still exist. |
| "Bypass is a collection-wide or session-wide flag." | Bypass is a per-operation option on supported write commands. |
| "Every driver API accepts bypass identically." | Check command, driver, and server version specifics. |
| "Holding `readWrite` grants bypass permission." | Requires the explicit `bypassDocumentValidation` privilege plus write rights. |
| "Bypass skips duplicate key checks." | Unique indexes are still enforced. |
| "MongoDB 9.0 `constraint` can still be bypassed with privileges." | `constraint` and prepare block bypass by design. |
| "Rolling back a validator rolls back data." | Schema metadata and data mutations are separate operations. |
| "A field in `required` is guaranteed to have the right type." | `required` only checks existence; add type/value rules too. |
| "`additionalProperties: false` does not affect `_id`." | You must allow `_id` inside `properties`. |
| "MongoDB schema validation replaces business logic." | It is a write-time guardrail, not a substitute for all business validation. |

## 15. Self-Check Exercises

### Exercise 1 — Breaking Schema Change

App v1 creates users with `name` and may omit `email`. A new validator requires `email` and enables `strict + error` while App v1 is still running. What can happen?

**Answer:** Inserts from App v1 may be rejected, and updates to legacy documents still missing `email` may also fail. You must expand writers/readers, observe, backfill, and enforce in phases.

### Exercise 2 — Strict vs. Moderate

A document is already invalid under a new rule. A client runs `$set` on an unrelated field only. How do `strict + error` and `moderate + error` differ?

**Answer:** `strict` evaluates the post-update result and rejects it. `moderate` skips validation on updates to already-invalid documents, so the update succeeds while the document remains invalid.

### Exercise 3 — Finding Non-Conforming Data

Given a variable `nextValidator` holding `{$jsonSchema:{...}}`, write a query retrieving documents that fail the rule.

~~~javascript
db.getSiblingDB("schema_lab").users.find({
  $nor: [nextValidator]
})
~~~

`$nor` negates the entire schema predicate. To count them, use `countDocuments` with the same filter.

### Exercise 4 — Bypass and Unique Indexes

A collection has a unique index on `email`. A client attempts to insert a duplicate email with `bypassDocumentValidation: true`. Does the unique index still fire?

**Answer:** **Yes.** Bypass skips only the collection schema validator where supported; duplicate keys still raise an error.

### Exercise 5 — Bypass Privileges

An account holds standard `readWrite` privileges without the `bypassDocumentValidation` action. Can it request bypass in an `insert`?

**Answer:** In a deployment with authorization enabled, **no**; the explicit bypass privilege is required. Never grant broad administrative roles just to work around application validation errors.

### Exercise 6 — MongoDB 9.0 Constraint Mode

A collection is in `constraint` mode. An account holding bypass privileges sends a **schema-valid** write while still specifying `bypassDocumentValidation: true`. What happens?

**Answer:** The command is **rejected** because `constraint` mode forbids bypass entirely, even when the document itself is valid.

### Exercise 7 — Null vs. Missing

A schema requires `email` to exist with `bsonType: "string"`. Given three documents: `{}`, `{email:null}`, `{email:"an@example.test"}`, which satisfy both rules?

**Answer:** Only the third document. The first fails `required`; the second has the field with the wrong type.

### Exercise 8 — Application Rollback

After enabling validator v2 requiring `email`, the team wants to roll the application back to v1. Is rolling back only the application image safe?

**Answer:** **Not necessarily.** A v1 writer may generate invalid documents; you need backward-compatibility planning or an explicit metadata rollback procedure, keeping in mind migrated data will not automatically revert.

### Exercise 9 — Zero Warnings

A system enables `moderate + warn` and sees zero warnings all day. Can you conclude the collection holds no invalid data?

**Answer:** **No.** Already-invalid documents may skip validation on updates, and legacy records may never have been touched. Run a schema scan and audit all writers.

### Exercise 10 — Long-Term Bypass?

An import job needed bypass to load thousands of legacy documents. Afterward, the team wants to keep bypass enabled in all write jobs to "avoid errors." What are the risks?

**Answer:** The schema guardrail is effectively disabled for those jobs, invalid documents accumulate, future updates get rejected, and schema drift becomes invisible. Scope bypass narrowly, track invalid counts, maintain a remediation plan, and revoke privileges afterward.

## 16. Official Documentation for Deeper Reading

MongoDB documentation varies by server branch. For production systems, always open the **exact running version branch** and read release notes when adopting new features. Links under `/docs/manual/` normally resolve to the current release at lookup time.

- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — concepts and scope.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — updating an existing validator with `collMod`.
- [`collMod` database command](https://www.mongodb.com/docs/manual/reference/command/collmod/) — syntax, privileges, options, and locking behavior.
- [View Existing Validation Rules](https://www.mongodb.com/docs/manual/core/schema-validation/view-existing-validation-rules/) — `getCollectionInfos`, `listCollections`.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `strict`, `moderate`, and `constraint`.
- [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `error`, `warn`, and `errorAndLog`.
- [Query for and Modify Valid or Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/use-json-schema-query-conditions/) — using `$jsonSchema` with `$nor` to locate legacy data.
- [Bypass Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/bypass-document-validation/) — supported operations, privileges, and bypass limits.
- [Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/) — actions related to `collMod` and `bypassDocumentValidation`.
- [Tips for JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/json-schema-tips/) — BSON types, `_id`, and `additionalProperties`.
- [MongoDB 8.0 — collMod](https://www.mongodb.com/docs/v8.0/reference/command/collmod/), [8.0 — Validation Level](https://www.mongodb.com/docs/v8.0/core/schema-validation/specify-validation-level/), [8.0 — Bypass](https://www.mongodb.com/docs/v8.0/core/schema-validation/bypass-document-validation/) — pinned 8.0 references.
- [MongoDB 7.0 — collMod](https://www.mongodb.com/docs/v7.0/reference/command/collmod/) — comparison with the 7.0 branch.

A validator change is well executed when **the new contract accurately reflects business rules**, **all writers are compatible**, **legacy data has been reconciled and handled**, and **enforcement state has been read back**. `bypassDocumentValidation` is strictly a controlled exception for specific operations, never a substitute for migrations. Always keep four questions distinct: what the data rules are, which operations are checked, whether violations warn or reject, and whether your server version supports the desired policy.
