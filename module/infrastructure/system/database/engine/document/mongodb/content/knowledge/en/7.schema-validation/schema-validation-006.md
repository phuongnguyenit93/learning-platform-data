# validationLevel, validationAction, and Handling Legacy Documents in MongoDB

## 1. The Problem: New Schema Meets Legacy Data

MongoDB allows documents in the same collection to have different structures. This flexibility helps when moving quickly or evolving a data model, yet it also introduces risks: one application might write a monetary amount as a string, another might write it as Decimal128, or some documents might lack a required status field.

Suppose the **orders** collection already holds millions of historical documents. The engineering team wants to enforce new rules:

- Every order must have **orderNo**, **tenantId**, **status**, **amount**, and **placedAt**.
- `status` must be one of **pending**, **paid**, or **cancelled**.
- `amount` must be a non-negative BSON **Decimal128**.
- `placedAt` must be of BSON type **Date**.

The challenge is that some legacy orders lack `status` or store `amount` as a String. Enabling strict enforcement immediately could block applications from updating old orders—even when simply editing an unrelated note field. Conversely, letting every malformed write pass allows bad new data to keep accumulating.

MongoDB handles rule enforcement through a **collection validator** paired with two options:

- **validationLevel:** determines **which operations/documents are checked**.
- **validationAction:** determines **how MongoDB handles a checked operation that produces an invalid document**.

Understanding each option individually and understanding **how they combine** is essential when introducing schema validation onto a collection that already contains data.

## 2. The Three Components of Collection Validation

Illustrative definition:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "status", "amount"],
      properties: {
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

This configuration block is used when **creating a new collection**, so in practice choose a collection name that does not yet exist. For an existing collection, use the **collMod** command shown later to update the validator without dropping the collection.

| Property | Question Answered | Examples |
| --- | --- | --- |
| **validator** | What shape/values must a valid document have? | `$jsonSchema` requires `status` to be in the allowed list |
| **validationLevel** | Which operations/documents does MongoDB check? | `strict`, `moderate`, `off`; `constraint` starting in MongoDB 9.0 |
| **validationAction** | If invalid, reject or merely warn? | `error`, `warn`; `errorAndLog` starting in MongoDB 8.1 |

**$jsonSchema** is a popular way to declare BSON types, required fields, enum values, numeric bounds, and field conditions. MongoDB also supports many query expressions suitable inside validators. Schema validation is a database-level data protection layer; it does not fully replace business validation or access control in the application.

**Common defaults:** when unspecified, `validationLevel` defaults to **strict** and `validationAction` defaults to **error**. Rules apply only when a validator is configured; never assume setting `strict` without rules gives the system automatic awareness of business structure.

## 3. validationLevel: Choosing the Validation Scope

### 3.1. strict

**strict** applies the validator to **all inserts** and **all updates**. For a document currently violating the schema:

1. Legacy documents **are not automatically deleted or repaired** when `strict` is enabled.
2. MongoDB checks a document only when a relevant write operation occurs.
3. If an update leaves the document invalid, whether it succeeds or fails depends on `validationAction`.
4. If an update simultaneously fixes enough errors so the post-update document is valid, the operation succeeds even if the pre-update document was invalid.

Legacy document example:

~~~javascript
{
  _id: "old-001",
  orderNo: "SO-001",
  amount: NumberDecimal("150000.00")
  // Missing status.
}
~~~

Assuming the validator requires `status`, `strict` + `error` blocks an operation that only adds a note:

~~~javascript
db.orders.updateOne(
  { _id: "old-001" },
  { $set: { note: "Address confirmed" } }
);
~~~

The reason is not that `note` is wrong, but because **the post-update document is still missing `status`**. If the same update also sets a valid `status`, the result satisfies the validator.

`strict` is appropriate once the team has cleaned up malformed data and wants every subsequent write to obey the rules.

### 3.2. moderate

**moderate** still validates **all inserts**. For updates, MongoDB applies the validator to documents that **already passed the current schema before the update**; updates to documents that are **already invalid** are not required to pass that check.

This enables a transitional path:

- New documents remain constrained when paired with `validationAction: "error"`.
- Existing valid documents cannot be degraded into invalid documents.
- Existing invalid documents can still be updated during migration, even if a given update does not fix all violations at once.

Using the same status-missing document above:

~~~javascript
db.orders.updateOne(
  { _id: "old-001" },
  { $set: { note: "Address confirmed" } }
);
~~~

With **moderate + error**, this operation succeeds because the pre-update document did not match the schema and is skipped from validation on update.

Misconception to avoid: **moderate does not mean warn-only**, nor does it mean skipping all legacy documents. It distinguishes based on **the existing document's validity status** prior to the update. An already-valid old document is still checked on update; an already-invalid document can stay invalid if left unfixed. Thus `moderate` is a **transitional compatibility mechanism**, not an automatic data-cleaning plan.

### 3.3. off

**off** disables schema validation for inserts and updates. The validator may still remain stored in collection metadata, yet MongoDB skips executing validator checks while `validationLevel` is `off`.

Example configuration change:

~~~javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "off"
});
~~~

`off` can help during controlled migrations, but it removes the database guardrail. Never switch to `off` merely to hide a schema design flaw or a persistent write bug.

### 3.4. constraint in MongoDB 9.0+

**MongoDB 9.0** introduces the **constraint** level. This level validates all inserts/updates **and guarantees the entire collection conforms to the validator**: when upgrading an existing collection to `constraint`, MongoDB scans existing documents and rejects the upgrade if any document fails the schema.

`constraint` has additional requirements:

- `validationAction` must be **error** or **errorAndLog**.
- Bypassing document validation is disallowed while in `constraint` mode.
- The validator cannot be edited directly while in `constraint`; you must step down to `strict` to change rules, then repeat the upgrade process.
- The collection scan during upgrade can consume significant resources on large datasets.

For existing collections, the standard upgrade path starts at `strict`, runs `collMod` with **prepareConstraintValidationLevel: true**, and only then changes `validationLevel` to `constraint`. Use this only when your server version supports it; the main lab examples in this lesson use `strict`/`moderate`/`off` for broad version compatibility.

### 3.5. Comparing Levels

| validationLevel | New Inserts | Updates to Currently Valid Docs | Updates to Currently Invalid Docs | Checks Old Data Immediately on Enable? |
| --- | --- | --- | --- | --- |
| **off** | Not checked | Not checked | Not checked | No |
| **moderate** | Checked | Checked | Checks not required | No |
| **strict** | Checked | Checked | Checked | No |
| **constraint (9.0+)** | Checked | Checked | Checked | **Yes**, on collection upgrade and must PASS |

In this table, "Checked" refers solely to whether the validator runs. **Whether a failed check blocks the operation depends on `validationAction`**. Even when `validationLevel` is `off`, other constraints such as unique indexes, immutable `_id`, and access permissions remain active.

## 4. validationAction: Handling Violating Operations

### 4.1. error

**error** is the default action. If a checked operation produces an invalid document, MongoDB **rejects the write operation**. Applications typically receive error code **121 (DocumentValidationFailure)**.

~~~javascript
db.runCommand({
  collMod: "orders",
  validationAction: "error"
});
~~~

This is the right choice when you want to prevent new or updated documents from drifting off schema. Test compatibility across all write paths before enabling on a production collection.

### 4.2. warn

**warn** allows operations that violate the validator to proceed while logging warning details to the **MongoDB server log**. Depending on log visibility, the caller simply sees the write succeed; never assume warnings appear immediately in `mongosh` or API responses.

~~~javascript
db.runCommand({
  collMod: "orders",
  validationAction: "warn"
});
~~~

`warn` is useful for **observing before blocking**: the team can identify which paths generate malformed documents, deploy application fixes, and then switch to `error`. However, `warn` **does not make data valid** and does not eliminate bad records. You still need queries/counts to locate schema-invalid documents.

### 4.3. errorAndLog Starting in MongoDB 8.1

Starting in **MongoDB 8.1**, you can use **errorAndLog** to **reject violating operations and log the error to the `mongod` log**. This helps when you need both hard enforcement and server-log observability.

~~~javascript
// Only use on MongoDB 8.1+.
db.runCommand({
  collMod: "orders",
  validationAction: "errorAndLog"
});
~~~

Do not configure this value on unsupported versions. If planning a MongoDB downgrade, review `errorAndLog` compatibility first; changing the setting may be a prerequisite for downgrading.

### 4.4. Combination Matrix

| validationLevel + validationAction | Invalid Insert | Update Valid Doc to Invalid | Update Already-Invalid Legacy Doc That Stays Invalid |
| --- | --- | --- | --- |
| **strict + error** | Rejected | Rejected | Rejected |
| **strict + warn** | Allowed, warning logged | Allowed, warning logged | Allowed, warning logged |
| **moderate + error** | Rejected | Rejected | Allowed because update falls outside validation scope |
| **moderate + warn** | Allowed, warning logged | Allowed, warning logged | Allowed; update is not checked under `moderate` |
| **off + error/warn** | Schema not checked | Schema not checked | Schema not checked |
| **constraint + error (9.0+)** | Rejected | Rejected | No invalid documents can exist if upgrade succeeded |

With **errorAndLog**, blocking behavior matches `error` while also logging checked violations. With **constraint**, only `error` or `errorAndLog` is valid.

A common pitfall: **validationAction does not widen validation scope**. Setting `error` under `moderate` does not make MongoDB start validating updates to already-invalid legacy documents. Conversely, `warn` under `strict` still runs the validator on every insert/update, yet permits violating documents to be saved.

## 5. Why Enabling a New Schema Does Not Fix Legacy Documents

When you add a validator via `collMod`, MongoDB changes **rules for future write operations**. Under `strict` or `moderate`, the command does not scan and repair existing stored documents. Consequently:

- Documents missing required fields remain in place.
- Documents with String `amount` keep their old type.
- Standard read queries still return those documents.
- Future updates may be blocked under `strict + error` if the post-update document remains invalid.
- If an application never touches an old document, that document can stay schema-invalid indefinitely.

That is why "collMod succeeded" is never proof that the entire collection conforms. To know how many documents are currently invalid, you must **query directly for documents failing the validator**.

### 5.1. Transitioning Schemas Without Data Loss

For a collection holding multiple generations of documents, a transition plan typically includes:

1. Build a validator reflecting the target schema, paying close attention to actual BSON types (String, Decimal128, Date, Array, ...).
2. Measure violation counts and root-cause categories across current data.
3. Identify which application versions or jobs still write legacy schemas.
4. Choose an appropriate mode to observe/transition without disrupting critical write paths.
5. Write **rerunnable** migrations with bounded scope, before/after counts, and no guessing of missing values.
6. Recheck invalid document counts, update applications, and step up to stricter enforcement.

Remediation may require multiple steps depending on business rules. For instance, a missing `status` might be reliably derived from payment history, whereas you must never blindly set every missing status to `paid`. If no authoritative derivation exists, define a custom handling rule or a manual review queue.

## 6. mongosh Lab: Creating Legacy Data and Observing moderate/strict

To observe exact behavior, use the **mongo_validation_lab** database and the **lab_orders_legacy** collection. This collection is dedicated to the lab. The script below uses fixed `_id` values so it can be re-run; it deletes only documents tagged **dataset: "schema-legacy-v1"**. Do not run this on databases or collections shared with production data.

### 6.1. Creating Three Documents: One Valid, Two Invalid Legacy

Paste the entire block below into `mongosh`. If the collection does not exist yet, the script creates it. It then sets `validationLevel` to `off` to insert simulated pre-rule data, and finally switches to **moderate + error**.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const name = "lab_orders_legacy";
  const tag = "schema-legacy-v1";

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  if (!lab.getCollectionNames().includes(name)) {
    lab.createCollection(name);
  }

  const orders = lab.getCollection(name);

  function setValidation(level, action) {
    const outcome = lab.runCommand({
      collMod: name,
      validator: validator,
      validationLevel: level,
      validationAction: action
    });
    if (outcome.ok !== 1) {
      throw new Error("collMod failed: " + JSON.stringify(outcome));
    }
  }

  // Simulate the phase before validation was applied to the collection.
  setValidation("off", "error");
  orders.deleteMany({ dataset: tag });

  orders.insertMany([
    {
      _id: "old-missing-status",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-LEGACY-001",
      amount: NumberDecimal("120000.00"),
      placedAt: ISODate("2025-11-01T08:00:00.000Z")
      // Missing status.
    },
    {
      _id: "old-wrong-amount",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-LEGACY-002",
      status: "pending",
      amount: "50000.00", // String, not Decimal128.
      placedAt: ISODate("2025-11-02T08:00:00.000Z")
    },
    {
      _id: "current-valid",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-2026-001",
      status: "paid",
      amount: NumberDecimal("98000.00"),
      placedAt: ISODate("2026-01-10T08:00:00.000Z")
    }
  ]);

  // Enable validator to guard inserts and updates to valid documents.
  setValidation("moderate", "error");

  print("Total lab documents: " +
    orders.countDocuments({ dataset: tag }));
  print("Invalid documents: " +
    orders.countDocuments({
      dataset: tag,
      $nor: [validator]
    }));
})();
~~~

**Expected result:** total dataset count is **3**; **2** documents are invalid. The dataset contains:

| _id | Status | Violation |
| --- | --- | --- |
| old-missing-status | Invalid | Missing required `status` |
| old-wrong-amount | Invalid | `amount` is String instead of Decimal128 |
| current-valid | Valid | All required fields and right BSON types |

The **decimal** rule on `amount` is deliberate: a `NumberInt` or `String` even with content `"50000"` does not satisfy BSON Decimal128. In MongoDB, schema validation checks the **actual BSON data type**, not merely how a value renders on screen.

### 6.2. Observing moderate + error

Run this snippet after completing Section 6.1:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_validation_lab")
    .getCollection("lab_orders_legacy");

  function attempt(label, operation) {
    try {
      const result = operation();
      print(label + ": SUCCEEDED");
      printjson(result);
    } catch (error) {
      print(label + ": REJECTED");
      print("code=" + error.code + ", message=" + error.message);
    }
  }

  // A. Invalid insert: must be rejected.
  attempt("A - insert missing status", () => orders.insertOne({
    _id: "new-invalid",
    dataset: "schema-legacy-v1",
    tenantId: "tenant-01",
    orderNo: "SO-2026-002",
    amount: NumberDecimal("45000.00"),
    placedAt: ISODate("2026-01-11T08:00:00.000Z")
  }));

  // B. Update valid document into invalid: rejected.
  attempt("B - change valid amount to String", () => orders.updateOne(
    { _id: "current-valid" },
    { $set: { amount: "98000.00" } }
  ));

  // C. Update document already missing status:
  // moderate skips validation on already-invalid documents.
  attempt("C - add note to invalid legacy doc", () => orders.updateOne(
    { _id: "old-missing-status" },
    { $set: { migrationNote: "Under review" } }
  ));
})();
~~~

Expected outcomes:

- **A:** rejected because new inserts are always checked.
- **B:** rejected because the pre-update document was valid while the post-update document is invalid.
- **C:** succeeds because the legacy document was already invalid, so `moderate` does not enforce the validator on this update.

After C, `old-missing-status` **remains invalid**. This clearly demonstrates that **moderate + error prevents many new errors yet does not automatically fix old ones**.

### 6.3. Switching to strict + error

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const change = lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "error"
  });
  printjson(change);

  const orders = lab.getCollection("lab_orders_legacy");

  print("Legacy doc still exists: " +
    orders.countDocuments({ _id: "old-missing-status" }));

  try {
    orders.updateOne(
      { _id: "old-missing-status" },
      { $set: { migrationNote: "Only updating note" } }
    );
    print("Unexpected: update succeeded");
  } catch (error) {
    print("Strict blocked legacy update: code=" + error.code);
  }
})();
~~~

Expected result: `old-missing-status` **still exists** after `collMod`; however, an update adding only a note is blocked because the post-image still lacks `status`. Enabling `strict` is not a legacy data migration step.

### 6.4. Switching to strict + warn for Observation

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  printjson(lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "warn"
  }));

  const result = lab.getCollection("lab_orders_legacy").updateOne(
    { _id: "old-missing-status" },
    { $set: { migrationNote: "Warn for observation" } }
  );
  printjson(result);
})();
~~~

The update is **allowed** under `warn` policy even though the document still lacks `status`. When a checked operation violates the rules, MongoDB logs a warning in the **server log**; whether you see that warning depends on your deployment and log access. Never treat an acknowledged update as proof that the document conforms to the schema.

If the collection has a unique index or other constraints, an operation can still fail due to those constraints even when `validationAction` is `warn`.

### 6.5. Finding Invalid Documents Before Migrating

MongoDB supports **$jsonSchema** as a query predicate. Pair it with **$nor** to select documents that **do not match** the schema.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const tag = "schema-legacy-v1";

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  const orders = lab.getCollection("lab_orders_legacy");
  const invalidFilter = {
    dataset: tag,
    $nor: [validator]
  };

  print("Invalid document count: " +
    orders.countDocuments(invalidFilter));

  printjson(
    orders.find(
      invalidFilter,
      { _id: 1, orderNo: 1, status: 1, amount: 1 }
    ).toArray()
  );
})();
~~~

At this point the result should still show **2 schema-invalid documents**. The **$nor: [validator]** condition is evaluated at query time; it does not depend on whether `validationLevel` or `validationAction` is currently blocking or allowing writes.

In production systems, aggregate counts by **error category** and scope rather than pulling millions of documents into client memory. On large collections, batch by `_id`, plan resources carefully, and avoid unbounded `toArray()` calls. If a collection validator combines multiple expressions, ensure your audit query uses the **exact active rules**.

### 6.6. Fixing Legacy Data and Enabling Enforcement

In this sample dataset, we **know** how to restore both values:

- `old-missing-status` corresponds to an unpaid order, so the valid sample status is `pending`.
- `old-wrong-amount` holds decimal string `"50000.00"`, which can be deliberately converted to Decimal128 without altering its numeric value.

With real production data, never guess status or price; rely on authoritative business sources and retain an audit trail of conversions.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const orders = lab.getCollection("lab_orders_legacy");
  const tag = "schema-legacy-v1";

  // Lock out new errors in the example, fixing each document directly
  // so each update's post-image satisfies the validator.
  printjson(lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "error"
  }));

  printjson(orders.updateOne(
    { _id: "old-missing-status", dataset: tag },
    { $set: { status: "pending" } }
  ));

  printjson(orders.updateOne(
    { _id: "old-wrong-amount", dataset: tag },
    { $set: { amount: NumberDecimal("50000.00") } }
  ));

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  const stillInvalid = orders.countDocuments({
    dataset: tag,
    $nor: [validator]
  });
  print("Remaining schema-invalid documents: " + stillInvalid);
})();
~~~

**Expected result:** both updates succeed and remaining invalid document count is **0**. Fixing all missing/invalid fields in a single update works under `strict + error` because MongoDB evaluates the **post-update document**.

This example has only three documents. A production migration should process in batches, record before/after counts, filter specifically for target values, support safe resumption on errors, and be validated on copied data or staging first.

## 7. Applying Validation to an Existing Collection with collMod

For an **existing** collection, you do not recreate it. Use **collMod**:

~~~javascript
db.getSiblingDB("mongo_validation_lab").runCommand({
  collMod: "lab_orders_legacy",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "status", "amount"],
      properties: {
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: { bsonType: "decimal" }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
});
~~~

This is a **shorter illustrative validator** than the Section 6 lab validator. Running it **replaces** the validator on that collection. Run it only when you intend to change the rules; if continuing from Section 6, reuse the full validator to preserve the same data contract. For real migrations, manage versioned validator definitions as source code rather than manually copying variants.

Inspect collection configuration:

~~~javascript
db.getSiblingDB("mongo_validation_lab").getCollectionInfos({
  name: "lab_orders_legacy"
});
~~~

The **options** object of the collection displays the configured `validator`, `validationLevel`, and `validationAction`. Always distinguish **configured rules** from **compliant data**: `getCollectionInfos` does not replace querying for invalid documents.

### 7.1. Reminder on additionalProperties

In JSON Schema, **additionalProperties: false** helps block unknown fields, yet you must account for **_id** and metadata fields added by applications or drivers. Failing to declare `_id` as an allowed property causes an overly strict schema to reject normal documents simply for having `_id`. Additionally, changing application schemas without updating the validator can cause sudden write failures.

Example strict schema:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["orderNo", "status"],
    additionalProperties: false,
    properties: {
      _id: {},
      orderNo: { bsonType: "string" },
      status: { enum: ["pending", "paid", "cancelled"] }
    }
  }
}
~~~

This is merely a two-field example; do not copy it verbatim to overwrite a production validator that also requires `tenantId`, `amount`, `placedAt`, `schemaVersion`, or other domain fields.

### 7.2. bypassDocumentValidation

Certain write operations can specify **bypassDocumentValidation** if the user/role has the required privilege. Consequently, under standard levels, schema validation does not replace authorization and account governance. Grant bypass privileges only to controlled administrative/migration tasks, and log the reason and scope. In MongoDB 9.0 under **constraint** mode, bypass is prohibited per that level's contract.

Never use bypass to make bad data disappear from error reports: bypass lets invalid data into the collection, and those records still need to be audited and remediated.

## 8. Rollout Roadmap in Production Systems

A collection written to by multiple services usually needs a phased rollout:

### Phase 1 — Observe Before Blocking

Define the target schema, check existing BSON types, count invalid documents, and identify which services produce them. You can temporarily use **strict + warn** to observe inserts/updates that produce invalid post-images. Ensure you have server log access and warning aggregation; remember that warning count is not the same as existing invalid document count.

In this phase, fix write code in services, migration tools, import jobs, and legacy clients. If an app still inserts `amount` as a String, jumping straight to `strict + error` turns a data issue into an operational outage.

### Phase 2 — Block New Errors, Allow Legacy Fixes

Once new write paths are compatible, **moderate + error** is often a helpful transitional phase:

- Invalid new inserts are blocked.
- Currently valid documents cannot be broken.
- Updates to currently invalid documents can still proceed for legacy workflows and migrations.

However, manage a migration backlog because `moderate` **does not push** legacy documents toward compliance on its own.

### Phase 3 — Clean Up Legacy Data

Query invalid documents using **$nor** and the target schema, group by root cause, apply conditional updates, and verify results. Watch for these scenarios:

| Violation Type | Example | Remediation Approach |
| --- | --- | --- |
| Missing required field | Missing `status` | Derive from authoritative business sources; never backfill arbitrary values |
| Wrong data type | `amount` stored as String | Parse explicit format, store Decimal128, handle unparseable strings |
| Out-of-domain value | `status = old_state` | Build controlled mapping table or version the schema |
| Wrong date type | `placedAt` is String | Confirm timezone and format; never guess ambiguous dates |
| Document from older schema version | Missing multiple new fields | Multi-step migration or transitional version-aware schema rules |
| Duplicate business keys | Two `orderNo`s per tenant | Analyze and deduplicate before creating unique index; never delete blindly |

With millions of documents, a single collection-wide `updateMany` can cause heavy write pressure, replication lag, and massive churn. Design batched jobs with rate limits, error tracking, checkpoints, and safe idempotent reruns.

### Phase 4 — Full Enforcement

Once applications and legacy data conform, switch to **strict + error** (or **errorAndLog** on supported versions). Here, `strict` prevents bad inserts/updates, yet **does not prove all existing documents are valid** because `strict` does not scan backward. Continue running audit queries and tracking invalid counts after switching.

On MongoDB 9.0+, if business needs demand **collection-wide** validation guarantees at a higher level, consider `constraint` after evaluating scan cost and preparation steps.

### Phase 5 — Maintaining Across Schema Versions

Every time a validator becomes stricter (e.g., adding a required field), previously valid documents can become invalid. Prepare by:

- Deploying code that reads both old and new shapes during the transition window.
- Establishing defaults or business-backed migrations.
- Versioning schemas when a collection intentionally stores multiple variants.
- Scheduling validator updates after all writers are upgraded.
- Monitoring invalid document metrics by day, tenant, app version, and error type.

Never simultaneously require new fields, drop legacy read support, and turn on strict enforcement in a single unphased deployment.

## 9. Advanced constraint Mode in MongoDB 9.0+

On MongoDB 9.0 or newer, once a collection is on **strict + error** and all data is valid, upgrading to higher assurance can look like:

~~~javascript
const lab = db.getSiblingDB("mongo_validation_lab");

// 1. Validator must already be configured accurately under strict.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  validationLevel: "strict",
  validationAction: "error"
}));

// 2. Prepare upgrade: block bypass and disallow validator edits.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  prepareConstraintValidationLevel: true
}));

// 3. MongoDB scans the collection during upgrade; fails if invalid docs remain.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  validationLevel: "constraint",
  validationAction: "error"
}));
~~~

**This snippet is an optional extension, outside Section 6's lab flow.** Do not run on MongoDB older than 9.0. Before upgrading a live collection, assess full-collection scan impact, admin privileges, active writers, and rollback plans. Once in `constraint` mode, you must step back to `strict` before modifying the validator; do not pass a new validator in the same command that upgrades to `constraint`.

## 10. Distinguishing Validators from Other Integrity Mechanisms

Schema validation governs **document shape and intra-document conditions**, yet it does not replace the following:

| Need | Appropriate Mechanism | Why Validation Alone Is Insufficient |
| --- | --- | --- |
| Unique `orderNo` per tenant | Unique compound index | Validators cannot check uniqueness across multiple documents |
| `customerId` points to existing customer | App logic / suitable transactions | No automatic cross-collection foreign keys |
| Prevent users viewing other tenants' orders | Authentication, authorization, tenant filters | Validators do not know who is authorized to read |
| Protect concurrent updates | State/version filters, transactions | Schema-valid updates can still cause logical overwrites |
| Ensure order total matches line calculations | Business validation, server-side calculation | Valid Decimal128 type does not prove the sum formula is right |
| Write Order and AuditEvent atomically | Multi-document transactions / outbox pattern | Per-document validation provides no cross-collection atomicity |
| Fast lookup by `customerId`, `placedAt` | Compound indexes and query tuning | Validators do not replace read indexes |

For example, even though a validator allows `status = paid`, transitioning directly from `cancelled` to `paid` may still be forbidden by **business logic**. Both pre- and post-update documents are schema-valid, yet the state transition is invalid.

## 11. Common Issues and Diagnostics

| Symptom | Typical Cause | Investigation Steps |
| --- | --- | --- |
| Insert fails with code 121 | Document failed validator under `error` action | Check error message, active schema, BSON types, and required fields |
| Updating only `note` fails with code 121 | `strict` validates entire post-image of an already-invalid legacy doc | Find old violations; fix all violations in update or follow migration plan |
| `moderate + error` still allows updating invalid doc | `moderate` skips validation on updates to already-invalid docs | Designed behavior; run separate migration and audit |
| `warn` shows no error to client | `warn` lets writes succeed and logs to server log | Check `mongod` logs/monitoring; query invalid documents |
| `collMod` to `strict` succeeds, yet bad data remains | `strict` does not scan existing documents backward | Use `$nor` + validator to count invalid documents |
| Data-fix command fails despite `validationLevel: "off"` | Another constraint applies (unique index, immutable `_id`, privileges) | Read exact error code; do not blame every failure on validator |
| BSON type mismatch | String/Double/Int64 differs from Decimal128 | Inspect with `$type` and perform deliberate conversion |
| `constraint` upgrade fails | Invalid documents remain or prepare step was skipped | Audit invalid docs, confirm 9.0+ version and prepare steps |
| Changing validator breaks old apps | Multiple writers incompatible with new schema | Inventory write paths and roll out in phases |
| Setting `validationAction: "errorAndLog"` rejected | Unsupported MongoDB version or incompatible config | Check `db.version()` and server capabilities |
| TTL/unique index still enforces with `validationLevel: "off"` | Indexes operate independently of schema validation | Inspect `getIndexes()` and collection-specific rules |

### 11.1. Inspecting BSON Types

When asking "why is `amount` rejected even though it looks like a number?", run an aggregation:

~~~javascript
db.getSiblingDB("mongo_validation_lab")
  .getCollection("lab_orders_legacy")
  .aggregate([
    { $match: { dataset: "schema-legacy-v1" } },
    {
      $project: {
        _id: 1,
        amountType: { $type: "$amount" },
        statusType: { $type: "$status" },
        placedAtType: { $type: "$placedAt" }
      }
    }
  ]).toArray();
~~~

MongoDB distinguishes **decimal**, **string**, **int**, **long**, **double**, and **date**. Defining **bsonType: "decimal"** rejects a string even if it contains digits. Type consistency is vital when data arrives from multiple drivers and languages.

### 11.2. When Should You Check Bypass Privileges?

If invalid data still enters despite `strict + error`, verify:

1. The application actually writes to the **exact database and collection** holding the validator.
2. No privileged operation or account is passing **bypassDocumentValidation**.
3. `getCollectionInfos` confirms the expected active `validationLevel` and `validationAction`.
4. Whether those documents predate the validator or were newly written.
5. Whether the active schema checks the intended data types and `required` properties.

Never conclude MongoDB has a bug just from reading an invalid document; `strict` does not scan and repair legacy documents.

## 12. Practice Exercises

**Exercise 1 — Policy Matrix.** Using the three lab documents, predict whether an insert missing `status`, an update changing `current-valid`'s `amount` to String, and an update adding a note to `old-missing-status` will be accepted or rejected under each combination: `strict/error`, `strict/warn`, `moderate/error`, `moderate/warn`, and `off/error`. Explain in order: **whether it is checked**, then **how violations are handled**.

**Exercise 2 — Migrating from a Legacy Schema.** Insert an additional legacy document with `placedAt` as an ISO String, then locate it using `$nor` + `$jsonSchema`. Define rules to convert the String to a BSON Date with explicit timezone handling; handle empty strings, unparseable strings, and missing timezones. Update only when input is valid.

**Exercise 3 — Partial Updates.** Under `strict + error`, why did an update modifying only `migrationNote` on `old-missing-status` initially fail? Write a single update fixing `status` and `migrationNote` together. Observe whether the post-image satisfies the validator.

**Exercise 4 — Phased Rollout.** A collection holds 10 million documents; 2% lack `status`; 100,000 new orders arrive daily. Write a migration plan moving from no validation to `strict + error`, including metrics to monitor, auditing, fixing writers, and exit criteria.

**Exercise 5 — New Schema Version.** A new schema adds a required `currency` field. Analyze why enabling `strict + error` immediately can break legacy updates. Compare two strategies: supporting old and new shapes simultaneously during transition, versus backfilling `currency` across all documents before adding it to `required`.

**Exercise 6 — Logging vs. Enforcement.** Contrast the goals of `warn` and `errorAndLog`. If an application reports successful writes while monitoring flags schema warnings, which `validationAction` is likely configured? What additional checks are needed before enabling write rejection?

**Exercise 7 — Constraint Mode (MongoDB 9.0+).** Explain why upgrading `strict` to `constraint` requires a full collection scan, why `warn` is forbidden in `constraint`, and why preparation is required before upgrading. List potential impacts if the collection is very large under active write load.

## 13. References

- MongoDB Manual — [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/).
- MongoDB Manual — [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/).
- MongoDB Manual — [Query for and Modify Valid or Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/use-json-schema-query-conditions/).
- MongoDB Manual — [collMod command](https://www.mongodb.com/docs/manual/reference/command/collmod/).

**Practical takeaway:** **validationLevel** decides *when the validator runs*; **validationAction** decides *the consequence of a failed check*. Existing documents are not automatically repaired when adding a validator under `strict` or `moderate`. For collections with existing data, audit errors and writers, clean data using reliable business rules, and step up enforcement deliberately. Only when both new write paths and historical data satisfy the schema contract does strict enforcement protect data without breaking critical workflows.
