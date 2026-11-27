# Schema Validation Errors, Wrong BSON Types, and Unconvertible Values

MongoDB allows flexible document schemas, yet **flexibility does not mean every value is valid in every context**. An application might write a document containing `amount: "149000"` yesterday, then get rejected today when a `$jsonSchema` validator requiring `amount` to be `Decimal128` is deployed. An aggregation might succeed across 999,999 records and abort on the one-millionth because `$toDate` cannot parse `"31/02/2026"`. A Java service might read data fine in `mongosh` yet throw `ClassCastException` when calling `Document.getLong("quantity")` on a document whose actual BSON type is Int32.

At the API layer, these failures look similar—HTTP 500, failed imports, halted jobs, or rejected writes—yet **their root causes and fixes are completely different**:

- **Schema validation:** MongoDB Server rejects an insert/update because the document fails the collection's validator.
- **Wrong BSON type:** the stored data has a different BSON type than what the query, index, aggregation, driver, or application expects.
- **Unconvertible value:** the input value cannot be converted to the target type, exceeds allowed bounds, or has an invalid representation.
- **Codec/mapping error:** the Java Driver or Spring Data cannot encode/decode or convert the data into the corresponding Java class.

The lesson **"Schema Validation Errors, Wrong BSON Types, and Unconvertible Values"** in the **Troubleshooting** chapter walks through the investigation workflow, finding mistyped documents, distinguishing easily confused error categories, repairing data in batches, rolling out schema constraints safely, and testing to prevent regressions.

> **Remediation principle:** Before changing anything, know where the error occurred, which document violated the rule, which validator/operation is active, and which input value failed conversion. Never disable validators, pass `bypassDocumentValidation`, or blindly cast values in bulk just to silence error messages.

---

## 1. Three Common Error Layers

A processing flow:

```text
HTTP / Worker / Import Job
           │
           ▼
Java application / Spring Data
           │
      BSON encode
           │
           ▼
MongoDB command
           │
      Query / Update
           │
      Schema validator
           │
           ▼
Storage / Replication
           │
      BSON decode
           │
           ▼
Application result
```

Errors can emerge at **any layer**.

| Symptom | Common origin | Example |
|---|---|---|
| `Document failed validation` | MongoDB Server | `amount` is String while validator requires Decimal128 |
| `ConversionFailure` or `$to*` error | Aggregation/update pipeline | `$toInt("N/A")` |
| `Cannot apply $inc ... non-numeric` | MongoDB update execution | `$inc` on a String field |
| `ClassCastException` | Java application | `getLong()` on BSON Int32 |
| `CodecConfigurationException` | MongoDB Java Driver | Missing codec for POJO/custom type |
| `MappingException`/conversion error | Spring Data mapping | BSON field incompatible with Java property |
| `DuplicateKey` | Unique index | Duplicate business key value |
| JSON parse error | Import/export or app parser | Extended JSON parsed as plain JSON |
| Insert too large | BSON document/message limit | Document exceeds supported size limit |

Do not treat everything as schema validation: unique indexes, authorization, document size, malformed BSON, and application mapping are separate mechanisms.

## 2. Symptoms from an Operator's Perspective

Typical signs:

```text
Sudden spike in HTTP 400/422 or 500
Bulk import stops at specific records
MongoDB write error code 121
Long-running aggregation fails reporting conversion failure
Some tenants fail while others succeed
New data writes succeed yet historical batch updates fail
New Spring Data deployment starts failing on decode
Revenue dashboard totals shift after a backfill
```

Avoid seeing "the same API is failing" and assuming the cause lives in MongoDB Server. Inspect **request traces, driver exceptions, and commands** to pinpoint the exact layer.

### 2.1. Quick Triage by Timing

- **Right before sending the command:** likely input validation, serializer, or BSON codec.
- **During insert/update on the server:** validator, unique index, update operator, or authorization.
- **During aggregation:** `$convert`, `$to*`, `$dateFromString`, `$arrayToObject`, or arithmetic.
- **When receiving results in Java:** codec/POJO mapping, type cast, or null handling.
- **Only during legacy backfill:** mixed-type data or legacy records.
- **Only after changing a validator:** new schema is incompatible with legacy data or older write paths.

This classification helps you pick the right diagnostic tool instead of changing everything at once.

## 3. First 15-Minute Incident Response Procedure

When a critical write path suddenly fails:

1. **Scope the incident:** database, collection, tenant, endpoint, error rate.
2. **Preserve evidence:** timestamp, trace ID, server version, operation type, error code/name, and readable validator details.
3. **Check recent changes:** application releases, `collMod` validator updates, migrations, driver/schema versions, imports.
4. **Separate retryable errors from permanent data errors:** never retry invalid records indefinitely.
5. **Contain impact:** pause faulty import jobs, throttle failing traffic, or roll back the release per supported plan.
6. **Inspect metadata and sample data safely:** never dump raw PII into logs.
7. **Run queries to find the affected data classes** in an authorized environment.
8. **Choose remediation:** fix producers, fix mappers, convert legacy data, or update the validator per business contract.
9. **Test on staging using anonymized reproductions of the failing fixtures.**
10. **Monitor and reconcile before closing the incident.**

Never edit a collection validator or run `updateMany` in production solely because code 121 appeared.

## 4. Running Scenario Throughout This Lesson

Collection `commerce.orders` contains documents such as:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  orderNo: "A-1001",
  amount: NumberDecimal("249900.00"),
  quantity: NumberInt(2),
  status: "PAID",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

However, legacy data might look like:

```javascript
{
  _id: "ORD-1002",
  tenantId: "T-01",
  orderNo: "A-1002",
  amount: "249900",
  quantity: "2",
  status: "paid",
  createdAt: "14/11/2026 11:00"
}
```

And malformed input data:

```javascript
{
  _id: "ORD-1003",
  tenantId: "T-02",
  orderNo: "A-1003",
  amount: "unavailable",
  quantity: 1.5,
  status: null,
  createdAt: "2026-13-40"
}
```

Goals:

- `amount` is BSON Decimal128 and non-negative;
- `quantity` is an integer appropriate for the domain;
- `status` belongs to the approved enum set;
- `createdAt` is BSON Date;
- `tenantId` and `orderNo` are non-empty Strings per business rules;
- Every conversion is audited without corrupting monetary amounts or dates.

The examples below use a **test collection** and do not require modifying production.

## 5. MongoDB Stores Types as BSON, Not How They Look on Screen

BSON includes types such as:

| BSON type | `mongosh` example | Common Java type |
|---|---|---|
| String | `"249900"` | `String` |
| Int32 | `NumberInt(2)` | `Integer` |
| Int64 | `NumberLong("9007199254740993")` | `Long` |
| Double | `2.5` | `Double` |
| Decimal128 | `NumberDecimal("249900.00")` | `Decimal128` |
| Boolean | `true` | `Boolean` |
| Date | `ISODate("2026-11-14T04:00:00Z")` | `java.util.Date` or suitable mapping |
| ObjectId | `ObjectId("507f1f77bcf86cd799439011")` | `ObjectId` |
| Array | `["a", "b"]` | `List<?>` |
| Object | `{a: 1}` | `Document` or POJO |
| Null | `null` | `null` |
| Binary | `BinData(...)` | `Binary`, UUID depending on representation |
| Timestamp | BSON Timestamp | `BsonTimestamp` |

**The value `"123"` is not the number 123** just because the UI displays digits. Similarly, `ISODate(...)` is not equivalent to a String that looks like ISO 8601.

### 5.1. `NumberInt`, `NumberLong`, `NumberDecimal`

MongoDB has multiple numeric types; applications must understand their ranges and precision:

- **Int32:** 32-bit signed integer.
- **Int64:** 64-bit signed integer.
- **Double:** binary floating-point with precision limits.
- **Decimal128:** decimal representation suitable where decimal semantics are required.

Using `Double` for currency can introduce rounding errors; using `Int32` for large counters can overflow; using JavaScript `Number` for very large Int64 values can lose precision.

### 5.2. Int64 and JavaScript `Number`

The value:

```javascript
NumberLong("9007199254740993")
```

exceeds the maximum safe integer of an IEEE 754 double (`2^53 - 1`). If an export/import script converts that value into a standard JavaScript `Number`, it can be rounded.

Do not rely on plain `JSON.stringify`/`JSON.parse` as a mechanism that preserves all BSON types.

## 6. How Does Schema Validation Work?

MongoDB supports **collection-level validation rules**, typically using `$jsonSchema` or supported query expressions.

A validator can require:

- The document is an object;
- Required fields exist;
- Fields match the expected `bsonType`;
- Values belong to an enum;
- Strings match length/pattern constraints;
- Numbers fall within min/max bounds;
- Array items match a type;
- Nested objects follow a defined structure.

Validator example:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["tenantId", "orderNo", "amount", "createdAt"],
    properties: {
      tenantId: { bsonType: "string" },
      orderNo: { bsonType: "string" },
      amount: {
        bsonType: "decimal",
        minimum: NumberDecimal("0")
      },
      quantity: { bsonType: "int" },
      createdAt: { bsonType: "date" },
      status: {
        enum: ["NEW", "PAID", "CANCELLED"]
      }
    }
  }
}
```

**A field omitted from `required` may be absent**, even if `properties` specifies the type required when the field is present.

### 6.1. MongoDB `$jsonSchema` Does Not Support Every JSON Schema Feature

MongoDB implements a supported subset of operators/keywords tailored for BSON; do not assume every external JSON Schema keyword is valid. Always consult the documentation for the exact MongoDB Server version in use.

### 6.2. Validators Differ from Unique Indexes

`$jsonSchema` can require `orderNo` to be a String, but it cannot prevent two documents from sharing the same `(tenantId, orderNo)`. A **unique index** is a separate mechanism for uniqueness and must be tested separately.

## 7. Creating a Test Collection with a Validator

**Run only in staging or an isolated lab database authorized for test data.**

```javascript
const lab = db.getSiblingDB("schema_validation_lab");

lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNo", "amount", "createdAt"],
      properties: {
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        orderNo: {
          bsonType: "string",
          minLength: 1
        },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 1
        },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        },
        createdAt: {
          bsonType: "date"
        },
        tags: {
          bsonType: "array",
          items: { bsonType: "string" }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Test inserting a valid document:

```javascript
lab.orders.insertOne({
  _id: "TEST-OK-001",
  tenantId: "T-01",
  orderNo: "A-1001",
  amount: NumberDecimal("249900.00"),
  quantity: NumberInt(2),
  status: "PAID",
  createdAt: new Date(),
  tags: ["priority"]
});
```

Test inserting an invalid document:

```javascript
lab.orders.insertOne({
  _id: "TEST-BAD-001",
  tenantId: "T-01",
  orderNo: "A-1002",
  amount: "249900",
  quantity: "2",
  status: "paid",
  createdAt: "2026-11-14"
});
```

The second document violates multiple rules and must be rejected when the validator/action is enforced. **Never run this test case against a production collection.**

## 8. Reading the Existing Validator Without Modifying Data

Before drawing conclusions, verify the validator on the actual collection:

```javascript
db.getSiblingDB("commerce").getCollectionInfos({
  name: "orders"
});
```

In the output, inspect:

```text
options.validator
options.validationLevel
options.validationAction
```

Equivalent metadata commands may be used depending on permissions and server version.

### 8.1. Why Must You Read Actual Metadata?

An application may declare Java schemas/annotations while the database never deployed that validator. Conversely, a DBA may have applied a new rule via `collMod` that the application release is unaware of.

Distinguish:

```text
Desired schema in source code
          │
          ▼
Migration deployed?
          │
          ▼
Actual collection validator
```

Only the state on MongoDB Server determines which writes the server rejects.

### 8.2. Recording Version Context

Record metadata for:

- MongoDB Server version/FCV;
- Cluster topology;
- Database/collection;
- Validator definition;
- Timestamp of change;
- Application release and driver;
- Most recent schema migrations.

An error starting after an app release does not prove that release caused it if the DB validator was modified independently.

## 9. Meaning of `DocumentValidationFailure` — Code 121

A common error when MongoDB rejects a document is:

```text
code: 121
codeName: DocumentValidationFailure
errmsg: Document failed validation
```

For inserts/updates subject to a validator, the server may return **validation details** in the error payload depending on version and call path.

Illustrative structure:

```javascript
{
  code: 121,
  codeName: "DocumentValidationFailure",
  errmsg: "Document failed validation",
  errInfo: {
    failingDocumentId: "TEST-BAD-001",
    details: {
      operatorName: "$jsonSchema",
      schemaRulesNotSatisfied: [
        {
          operatorName: "properties",
          propertiesNotSatisfied: [
            {
              propertyName: "amount",
              details: [
                {
                  operatorName: "bsonType",
                  specifiedAs: { bsonType: "decimal" },
                  reason: "type did not match",
                  consideredValue: "249900",
                  consideredType: "string"
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

**Do not hardcode assumptions around this example structure**: error details can vary across MongoDB versions, drivers, and violation types. Error payloads can also include **real data values** in `consideredValue`, so never write full raw exceptions to public logs.

### 9.1. Code 121 Only Says the Validator Rejected the Document

It does not tell you **which field to fix** until you read the details and validator. Violations can involve `required`, `bsonType`, `enum`, `additionalProperties`, `minimum`, nested objects, or combined rules.

### 9.2. A Failing Insert Does Not Mean the Database Is Broken

MongoDB is enforcing the data policy. The right fix may be repairing the application or record, not turning off validation.

### 9.3. Code 121 Is Not a Duplicate Key Error

Rejection by a unique index produces a separate duplicate key error code such as `11000`. Investigate the unique constraint rather than loosening `$jsonSchema`.

## 10. Diagnosing Validation Details Level by Level

When encountering structured errors:

```text
$jsonSchema
  └── required
         └── missingProperties: ["tenantId"]
```

=> Document is missing a required field.

```text
$jsonSchema
  └── properties
         └── amount
               └── bsonType expected decimal, actual string
```

=> Wrong type.

```text
$jsonSchema
  └── properties
         └── status
               └── enum mismatch
```

=> Value outside the allowed set.

```text
$jsonSchema
  └── properties
         └── items
               └── elementsNotSatisfied
```

=> One or more array elements failed the rule.

### 10.1. Find the Root Field, Not Just the Top-Level Message

If the validator defines nested objects:

```javascript
shipping: {
  bsonType: "object",
  required: ["address"],
  properties: {
    address: {
      bsonType: "object",
      required: ["countryCode"],
      properties: {
        countryCode: { bsonType: "string" }
      }
    }
  }
}
```

The violation may lie at `shipping.address.countryCode`, not the top-level `shipping` field. Record the **property path** in redacted diagnostics.

### 10.2. Safe Trace Logging

Safe fields to log:

```text
traceId
requestId
jobId
namespace
operation=insert/update/bulk
errorCode=121
schemaVersion
fieldPath (when permitted)
expectedType
actualType
tenant scope (per policy)
```

Never log full documents or raw `consideredValue` entries if they contain PII, tokens, addresses, or payment details.

## 11. `validationLevel`: `strict`, `moderate`, and `off`

MongoDB offers validation levels depending on release:

| Level | Behavior |
|---|---|
| `strict` | Checks all inserts and updates in scope, including updates to existing invalid docs |
| `moderate` | Checks inserts and updates to existing documents that are already valid; updates to existing invalid docs are not checked the same way |
| `off` | Collection validation rules are not applied |

`moderate` can help roll out a validator on a collection containing legacy invalid records, yet **it does not repair old records automatically**, and it permits updates to old records to remain invalid.

### 11.1. `moderate` Is Not Schema Repair

Legacy data:

```javascript
{ _id: 1, amount: "N/A" }
```

may already exist. `validationLevel: "moderate"` does not turn `"N/A"` into `Decimal128`. It only changes how rules apply to certain updates.

### 11.2. When to Consider `moderate`

During a controlled rollout:

1. Quantify the legacy invalid records.
2. Fix new write paths.
3. Temporarily use `moderate` if justified by business needs and approved.
4. Backfill/remediate legacy data in batches.
5. Verify the invalid count reaches 0 per contract.
6. Switch to `strict` per migration plan.
7. Monitor errors.

Never leave `moderate` enabled permanently just to hide inconsistent data when business rules require `strict`.

## 12. `validationAction`: `error`, `warn`, and Version-Specific Options

MongoDB separates **whether to validate schemas** from **what happens on violation**.

- `error`: rejects writes violating validation.
- `warn`: permits the write to succeed while emitting a corresponding warning per logging/observability configuration.
- Some newer releases also support combined error and logging options; verify your exact server version before using them.

### 12.1. `warn` Mode Is Useful for Shadow Validation

A rollout path:

```text
Deploy validator with warn
          │
          ▼
Observe violation rate
          │
          ▼
Fix producer and legacy cases
          │
          ▼
Test strict behavior in staging
          │
          ▼
Switch validationAction to error
```

However, using `warn` allows invalid data to keep entering the collection. Only use it when risk assessment approves and an end date is planned.

### 12.2. Warning Logs Are Not a Complete Audit Report

Logs have their own retention, sampling, and access controls; they do not guarantee every violation can be counted accurately without dedicated metrics/monitoring. Use staging tests and actual data queries to verify.

## 13. Modifying a Validator via `collMod` Is a Production Change

Example command:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "amount"],
      properties: {
        tenantId: { bsonType: "string" },
        amount: { bsonType: "decimal" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

**Do not run this command in production just to test.** `collMod` alters write acceptance rules for the entire collection.

### 13.1. Changing a Validator Does Not Fix Existing Data

A new `strict` validator can be attached to a collection that still holds invalid legacy documents. Whenever updates touch those records, writes may be rejected.

### 13.2. Do Not Deploy a Validator Before Updating All Writers

An API service may already send `Decimal128`, while an older import job still sends `String`. Enabling `strict` abruptly will break that job.

Inventory all writers:

- REST/APIs;
- Workers;
- Scheduled jobs;
- ETL/imports;
- Admin scripts;
- Change stream processors;
- Third-party connectors;
- Test automation.

### 13.3. Validator Migrations Need Their Own Rollback Plan

Reverting application code does not revert the database validator. Every `collMod` change should have an ID, owner, before/after definitions, timestamp, audit record, and rollback plan.

## 14. `bypassDocumentValidation`: Why Not Use It as a Quick Fix?

Several MongoDB write commands and drivers support a `bypassDocumentValidation` option when the caller holds sufficient privileges.

Its intended use is controlled migration/restore operations—**not a default way to skip the schema contract**.

### 14.1. Risks

- Writes records violating business invariants;
- New applications fail to decode them;
- Subsequent updates are rejected by the strict validator;
- Analytics/financial totals become wrong;
- Creates hard-to-fix data debt;
- Erodes auditability if abused.

### 14.2. When Might It Be Considered?

Only with an explicit plan:

- Data must be preserved as-is for recovery/conversion;
- Approval and access controls are in place;
- Appropriate destination/namespace is used;
- A post-import remediation plan exists;
- Post-remediation validation/reconciliation is planned;
- Never used to bypass security or business constraints.

### 14.3. Validator Options Do Not Bypass Unique Indexes

`bypassDocumentValidation` applies to collection document validation; **it does not bypass unique indexes, authorization, or other constraint types**.

## 15. Distinguishing Missing Fields from `null` Fields

Two documents:

```javascript
{ _id: 1, amount: null }
{ _id: 2 }
```

differ:

- Document 1 has an `amount` field with value BSON Null.
- Document 2 lacks the `amount` field.

Impact:

- The `required` rule checks **presence**.
- `bsonType` checks the type when the field is present.
- Equality query `amount: null` has special semantics covering both null and missing.
- Partial indexes and application mapping may treat the two cases differently.

### 15.1. Finding Missing Fields

```javascript
db.orders.find({
  amount: { $exists: false }
});
```

### 15.2. Finding Explicit `null`

```javascript
db.orders.find({
  amount: { $type: "null" }
});
```

### 15.3. Finding Both `null` and Missing via Query Semantics

```javascript
db.orders.find({
  amount: null
});
```

Do not use the third filter to count **only explicit `null` values**.

### 15.4. `required` Does Not Automatically Forbid `null`

Schema:

```javascript
required: ["amount"],
properties: {
  amount: { bsonType: ["decimal", "null"] }
}
```

permits the field to exist as `null`. If business rules require non-null `Decimal128`, declare only `"decimal"` and keep `required`.

## 16. `$type` in Queries and Aggregations

`$type` is the primary tool for locating mistyped data.

### 16.1. Querying by BSON Type

```javascript
db.orders.find({
  amount: { $type: "string" }
});
```

```javascript
db.orders.find({
  quantity: { $type: "double" }
});
```

### 16.2. Reporting Type Distribution via Aggregation

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$amountType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Records missing `amount` appear as type `"missing"` in the aggregation `$type` operator, distinguishing them from `"null"`.

### 16.3. Difference with Arrays

In a query predicate, `$type` has special array semantics: it matches if any element of the array matches the type. By contrast, the aggregation expression:

```javascript
{ $type: "$tags" }
```

returns the type of the **field value itself**, e.g., `"array"`.

Do not assume identical semantics across both contexts when profiling arrays containing mixed types.

### 16.4. Profiling Multiple Fields

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      quantityType: { $type: "$quantity" },
      createdAtType: { $type: "$createdAt" },
      statusType: { $type: "$status" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        quantity: "$quantityType",
        createdAt: "$createdAtType",
        status: "$statusType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } },
  { $limit: 100 }
]);
```

This pipeline is read-only, yet it can consume heavy CPU/I/O on large collections. Run under approved procedures, considering tenant/range filters and off-peak windows.

## 17. Checking Data That Fails `$jsonSchema`

`$jsonSchema` can be used as a query predicate within MongoDB's supported scope. In a test environment or under an approved read plan, you can locate non-conforming documents:

```javascript
const expectedSchema = {
  bsonType: "object",
  required: ["tenantId", "amount"],
  properties: {
    tenantId: { bsonType: "string" },
    amount: { bsonType: "decimal" }
  }
};

db.orders.find({
  $nor: [
    { $jsonSchema: expectedSchema }
  ]
}).limit(20);
```

Notes:

- This is an **illustrative schema**, not necessarily identical to the live validator;
- `limit(20)` returns at most 20 samples and does not show the total invalid count;
- The query may scan many documents;
- A validator may combine other operators beyond `$jsonSchema`;
- Never print full PII documents to logs.

### 17.1. Narrowing by Tenant/Range

If the error only appears for tenant `T-01`:

```javascript
db.orders.find({
  tenantId: "T-01",
  amount: { $type: "string" }
}).limit(20);
```

Start with the smallest diagnostic scope, then widen if necessary.

### 17.2. Do Not Modify Data in the Same Diagnostic Query

In the initial phase, prioritize **read-only queries** and produce a report of invalid IDs/categories. Only run update pipelines after approval.

## 18. Type Mismatches That Do Not Always Throw Errors

MongoDB may **not throw** when a comparison filter fails to match as expected.

Example:

```javascript
db.orders.find({
  amount: { $gte: NumberDecimal("100000") }
});
```

If the collection has `amount` stored as String, the query skips those records under BSON type-bracketing/comparison semantics rather than raising an "amount is string" error.

Consequences:

- Dashboards miss orders without throwing exceptions;
- Revenue totals come up short;
- Sorting mixed types yields unexpected orderings;
- Unique/partial indexes behave unexpectedly;
- Java code throws cast errors upon encountering mixed types.

**No exception does not mean the data is right.** Testing must cover type distribution and business aggregates.

## 19. Overview of Conversion Operators

MongoDB provides:

- `$convert`: converts with `onError` and `onNull` handling where supported;
- `$toInt`, `$toLong`, `$toDouble`, `$toDecimal`;
- `$toString`;
- `$toDate`;
- `$toObjectId`;
- `$toBool`;
- `$dateFromString` for parsing Strings into Dates;
- `$isNumber` to check numeric types in aggregations;
- `$type` for classification.

Most shorthand `$to*` operators **fail the entire aggregation** upon encountering an unconvertible value rather than silently returning null. `$convert` allows explicit error handling.

### 19.1. Do Not Assume `$convert` Supports Every Type Pair

Conversion support depends on the operator, input, and MongoDB version. For example, you cannot arbitrarily turn a complex object/array into an integer with `$toInt`.

### 19.2. Conversion Alters Semantics

Turning `"01"` into `1` strips the leading zero; turning `"false"` into a boolean may behave unexpectedly; Dates without a timezone may be interpreted differently. Convert only when the business contract is unambiguous.

## 20. `$convert` with `onError` and `onNull`

Example previewing `amount` conversion to Decimal128:

```javascript
db.orders.aggregate([
  {
    $project: {
      orderNo: 1,
      amountOriginal: "$amount",
      amountType: { $type: "$amount" },
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "__CONVERSION_ERROR__",
          onNull: null
        }
      }
    }
  },
  { $limit: 100 }
]);
```

Results:

| Input `amount` | Preview `amountDecimal` |
|---|---|
| `"249900.00"` | Valid Decimal128 |
| `NumberInt(12)` | Corresponding Decimal128 if supported |
| `"N/A"` | `"__CONVERSION_ERROR__"` |
| `null` | `null` |
| Missing field | `null` per `onNull` |

Use string sentinels strictly in **preview/diagnostic pipelines**. Never write `"__CONVERSION_ERROR__"` into a field where the validator requires Decimal128.

### 20.1. Why Not Use `onError: 0`?

If an unconvertible `"N/A"` becomes `0`, the system may record false revenue. "No valid value" does not automatically equal zero.

### 20.2. `onNull` Also Requires a Business Decision

If `amount` is required, returning `null` helps categorize missing records, yet it is invalid for the final target field. Those records must be remediated or quarantined.

### 20.3. `$convert` Is Not a Migration by Itself

A `$project` pipeline is read-only. Actually changing data requires an explicit update/merge/import operation with preflight checks, backups, auditing, and tests.

## 21. `$toInt`: Common Pitfalls

Try:

```javascript
db.orders.aggregate([
  {
    $project: {
      quantityAsInt: { $toInt: "$quantity" }
    }
  }
]);
```

With inputs:

```text
"2"             → Converts to Int32 2
"2.5"           → String is not a valid integer for $toInt
"N/A"           → Unconvertible
1000000000000   → Exceeds Int32 range
2.9             → Numeric conversion may truncate fractional part
null            → Follows null conversion semantics
```

**Never apply fractional truncation in a business domain where quantities must be whole numbers.** A `quantity: 2.9` may be corrupt data, not 2 items.

### 21.1. Validate Values Before Converting

```javascript
db.orders.aggregate([
  {
    $project: {
      quantityOriginal: "$quantity",
      quantityConverted: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: "__BAD_INT__",
          onNull: "__MISSING_INT__"
        }
      }
    }
  },
  {
    $match: {
      quantityConverted: {
        $in: ["__BAD_INT__", "__MISSING_INT__"]
      }
    }
  }
]);
```

Use this output to build a remediation list—do not delete records automatically.

## 22. `$toLong` and Very Large Numbers

Int64 values are useful for large counters or domain epoch timestamps, yet still have 64-bit bounds.

Preview example:

```javascript
db.orders.aggregate([
  {
    $project: {
      id: "$_id",
      original: "$quantity",
      longValue: {
        $convert: {
          input: "$quantity",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Issues:

- A String holding a number beyond Int64 range cannot convert cleanly.
- A Decimal128 with fractional digits does not cleanly represent an integer.
- A JavaScript `Number` that was already rounded cannot have its original digits restored by `$toLong`.
- A String `"000123"` loses leading zeros when converted to Long, breaking identifier semantics.

### 22.1. Do Not Convert Business IDs to Numbers Just Because They Look Numeric

An `orderNo: "000123"` should stay a String if leading zeros carry meaning. Changing the type breaks lookups and uniqueness.

## 23. Decimal128 and Monetary Values

Scenario:

```javascript
{ _id: 1, amount: NumberDecimal("123.45") }
{ _id: 2, amount: 123.45 }
{ _id: 3, amount: "123.45" }
```

Three documents use different representations. If the business requires Decimal128:

1. Profile type distribution;
2. Verify currency units;
3. Check decimal points, thousands separators, and currency symbols;
4. Handle invalid values;
5. Convert using a precision-preserving method;
6. Reconcile totals before and after;
7. Enable the validator after all writers comply.

### 23.1. Risks When the Source Is Double

Converting a `Double` to `Decimal128` does not restore the **ideal decimal value** prior to floating-point rounding. If the system previously stored money as floats, domain-specific reconciliation against a ledger/source of truth may be required.

### 23.2. Do Not Blindly Force Strings into Decimal128

Inputs like:

```text
"1,234.56"
"1.234,56"
"1 234,56"
"VND 1234"
""
"N/A"
```

may follow different locale conventions. A locale-unaware conversion will easily misinterpret values.

### 23.3. Java `BigDecimal` and `Decimal128`

If Java uses `BigDecimal`, you need codecs/converters with explicit mapping rules. A BSON Decimal128 field read via `Document` is typically decoded as `org.bson.types.Decimal128`, not `java.math.BigDecimal` by default.

## 24. `$toDate` and Invalid Date Strings

Example:

```javascript
db.orders.aggregate([
  {
    $project: {
      original: "$createdAt",
      createdAtDate: {
        $convert: {
          input: "$createdAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

`"2026-11-14T04:00:00Z"` parses per supported rules. However:

```text
"14/11/2026"
"31/02/2026"
"2026-13-01"
"next Tuesday"
```

should never be guessed automatically.

### 24.1. `$dateFromString` for Explicitly Defined Formats

When the input follows a known fixed pattern:

```javascript
db.orders.aggregate([
  {
    $project: {
      raw: "$createdAtText",
      parsed: {
        $dateFromString: {
          dateString: "$createdAtText",
          format: "%d/%m/%Y",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Only use this format/timezone if the **actual business contract** specifies dates in `dd/MM/yyyy` within that timezone.

### 24.2. Date Ambiguity

`"03/04/2026"` could mean April 3 or March 4. Never let a migration guess; verify against an authoritative source.

### 24.3. UTC vs. Local Time

MongoDB Date stores an instant in UTC, while local timezone formatting belongs to the application/UI. Timezone tests must verify the **exact instant**, not just matching formatted date strings.

### 24.4. Date Edge Cases

Test:

- Leap years;
- Non-existent calendar dates;
- DST if the locale observes it;
- Negative timestamps;
- Millisecond precision;
- Empty/null fields;
- Dates outside valid business bounds;
- Epoch seconds vs. epoch milliseconds.

Confusing epoch seconds with milliseconds yields dates in 1970 without throwing a conversion error.

## 25. `$toObjectId` and Invalid Identifiers

MongoDB `ObjectId` has a specific representation and length. A valid 24-character hex string can be converted to `ObjectId`; not every String can.

```javascript
db.orders.aggregate([
  {
    $project: {
      customerIdRaw: "$customerId",
      customerObjectId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Inputs:

```text
"507f1f77bcf86cd799439011"  → convertible
"customer-1001"             → not a hex ObjectId
""
null
```

### 25.1. Do Not Convert Every Business ID to `ObjectId`

If `customerId = "C-1001"` is an enterprise identifier, keep it as a String per schema. MongoDB does not require all IDs to be `ObjectId`.

### 25.2. Test Joins/References After Conversion

If collection A converts `customerId` from String to `ObjectId` while collection B does not, `$lookup` returns empty matches even though both look like "the same ID" in a UI. Verify BSON types on **both sides of a join**.

## 26. `$toBool`: The `"false"` String Trap

A serious mistake is treating:

```javascript
{ $toBool: "$active" }
```

like an English-word boolean parser.

In MongoDB conversion semantics, any non-empty String such as `"false"` evaluates to Boolean `true`, because `$toBool` does not behave like Java's `Boolean.parseBoolean`.

### 26.1. Safe Approach

If inputs are restricted to:

```text
"true"
"false"
"1"
"0"
```

define an explicit mapping:

```javascript
db.users.aggregate([
  {
    $project: {
      activeRaw: "$active",
      activeNormalized: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$active", "true"] },
              then: true
            },
            {
              case: { $eq: ["$active", "false"] },
              then: false
            }
          ],
          default: "__INVALID_BOOL__"
        }
      }
    }
  }
]);
```

If business rules also allow `"TRUE"`, `"False"`, or numeric `0`/`1`, add controlled mappings with tests. Never silently turn unrecognized inputs into `false`.

## 27. Array and Nested Object Mismatches

Validator example:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      tags: {
        bsonType: "array",
        items: { bsonType: "string" }
      }
    }
  }
}
```

Values:

```javascript
tags: ["priority", "gift"]   // valid
tags: "priority"             // wrong overall type
tags: ["priority", 7]        // wrong element type
tags: null                   // invalid if only array allowed
```

### 27.1. Do Not Wrap Scalars into Arrays Unless Business Rules Require It

Converting `"priority"` to `["priority"]` might seem reasonable in some schemas, yet you must verify whether it was mis-serialized data or carried a different meaning.

### 27.2. Nested Objects Missing Fields

```javascript
{
  shipping: {
    address: {
      countryCode: "VN"
    }
  }
}
```

If `shipping.address` was previously stored as a String, a migration must parse/normalize it safely. Never run `$set: {"shipping.address.countryCode":"VN"}` while `shipping.address` is a scalar because the update will fail.

### 27.3. Field Paths Containing Dots

In MongoDB, dot-notation paths like `"shipping.address"` access nested fields; however, schema/key naming has special rules for field names containing `.` or `$`. Never manipulate unusual field names by guessing; consult the rules for your server version and use appropriate migration tooling.

## 28. `additionalProperties: false`: Why Is `_id` Often Forgotten?

A strict schema:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    required: ["tenantId"],
    properties: {
      tenantId: { bsonType: "string" }
    }
  }
}
```

can reject documents because MongoDB adds `_id`, which is not listed in `properties`.

### 28.1. Defining the Proper Scope

To forbid unlisted fields, allow `_id`:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    required: ["tenantId"],
    properties: {
      _id: {},
      tenantId: { bsonType: "string" }
    }
  }
}
```

You must still account for fields added by the application/ODM, audit timestamps, version fields, and fields added during parallel rollouts.

### 28.2. Overly Strict Schemas Risk Backward Compatibility

If a new app version adds an optional field while the validator still forbids it, writes will be rejected. For rolling deployments, follow **expand → migrate → enforce** rather than locking down the schema before all writers are updated.

## 29. Mixed Numeric Types and Update Operators

Example:

```javascript
db.orders.updateOne(
  { _id: "ORD-1002" },
  { $inc: { quantity: 1 } }
);
```

If `quantity` is String `"2"`, `$inc` does not auto-parse it into a number and throws an error. If the field is missing, `$inc` creates it per operator semantics; if `null`, it is typically not treated as numeric.

### 29.1. Finding Unexpected Types Before Updating

```javascript
db.orders.aggregate([
  {
    $match: {
      quantity: { $exists: true }
    }
  },
  {
    $project: {
      quantity: 1,
      quantityType: { $type: "$quantity" }
    }
  },
  {
    $match: {
      quantityType: {
        $nin: ["int", "long"]
      }
    }
  }
]);
```

This is a read-only diagnostic query, not an automatic fix.

### 29.2. `$set` Is Not Equivalent to `$inc`

Replacing `quantity` with `0` just so `$inc` stops failing destroys real data. Recover/parse the source value properly.

### 29.3. Other Arithmetic Operators Also Have Type Requirements

`$multiply`, `$divide`, `$sum`, and others have specific non-numeric handling semantics. Do not assume every operator throws or skips invalid values identically; check the operator reference and test fixtures.

## 30. Conversion Failures in Aggregations Can Abort the Entire Job

Pipeline:

```javascript
db.orders.aggregate([
  {
    $project: {
      value: { $toDecimal: "$amount" }
    }
  },
  {
    $group: {
      _id: null,
      total: { $sum: "$value" }
    }
  }
]);
```

Upon hitting `"N/A"`, the aggregation aborts with a conversion error instead of merely skipping one record.

### 30.1. Safe Investigation Pattern

Before running `$toDecimal` across all data:

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      converted: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "__INVALID__",
          onNull: "__MISSING__"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        type: "$amountType",
        conversion: {
          $cond: [
            {
              $in: [
                "$converted",
                ["__INVALID__", "__MISSING__"]
              ]
            },
            "needs_review",
            "convertible"
          ]
        }
      },
      count: { $sum: 1 }
    }
  }
]);
```

### 30.2. Could a Sentinel Collide with Real Data?

Choose diagnostic sentinels and output schemas carefully; use tagged objects/states or type-based classification to avoid collisions with valid data. Never store a sentinel String as a final business value.

### 30.3. Large Datasets Need Resource Limits

Running `$convert` across hundreds of millions of records can be CPU-intensive. Partition by tenant/time/`_id` ranges, run a canary, monitor p99, disk/cache, and avoid peak hours.

## 31. Codec and Java Driver Errors Are Not Validator Errors

A Java program:

```java
Document order = collection.find(
    Filters.eq("_id", "ORD-1001")
).first();

Long quantity = order.getLong("quantity");
```

If BSON `quantity` is actually Int32, `Document#getLong` expects a Java `Long` and throws `ClassCastException`.

### 31.1. Check the Type Before Casting

```java
Object raw = order.get("quantity");

if (raw instanceof Integer value) {
    long quantity = value.longValue();
} else if (raw instanceof Long value) {
    long quantity = value;
} else {
    throw new IllegalArgumentException(
        "Unexpected BSON mapping for quantity: " +
        (raw == null ? "null" : raw.getClass().getSimpleName())
    );
}
```

This example uses Java pattern matching for `instanceof` where supported; on older runtimes, use traditional casts.

### 31.2. `Number` Does Not Cover Every BSON Numeric Type

`Integer`, `Long`, and `Double` implement `Number`, whereas `org.bson.types.Decimal128` has its own API to convert to `BigDecimal`. Do not cast `Decimal128` to `Number` expecting it to always work.

Example:

```java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Object rawAmount = order.get("amount");

if (rawAmount instanceof Decimal128 decimal) {
    BigDecimal amount = decimal.bigDecimalValue();
    // Validate range/scale/business invariants before use.
}
```

Special `Decimal128` values and cases not representable as `BigDecimal` must be handled per business contract rather than swallowing exceptions.

### 31.3. `getString` on a Numeric Field

```java
String amount = order.getString("amount");
```

does not cause the driver to auto-convert `Decimal128` into a String. On a type mismatch, a cast exception occurs. Use properly typed data or validated application-layer conversion.

## 32. Java BSON Encoding and Codec Errors

Other failures can happen **before MongoDB ever receives the command**:

- No suitable codec registered for a POJO/custom class;
- UUID representation not configured properly;
- Unsupported generic/complex type mapping;
- Custom codec throws an exception;
- BSON document exceeds size limits;
- Cyclic references or unencodable structures.

Example:

```java
MongoCollection<MyCustomPojo> collection = ...;
collection.insertOne(new MyCustomPojo());
```

If the codec registry does not know how to serialize `MyCustomPojo`, `CodecConfigurationException` occurs. Adding indexes or changing validators will not fix this; configure POJO codecs or mappings properly.

### 32.1. How to Distinguish

A telltale sign: **no corresponding server write command was sent** because encoding failed on the client. Use redacted driver command monitoring/tracing to verify where execution stopped instead of guessing from HTTP responses.

### 32.2. UUIDs and Binary Subtypes

UUIDs have representation/binary subtype settings in the driver. Upgrading drivers can interpret the same bytes differently if configurations mismatch. Test round-trip fixtures with anonymized real data rather than parsing UUIDs as Strings everywhere.

## 33. Spring Data MongoDB: Entities May Not Match Stored Data

Example:

```java
@Document(collection = "orders")
public class OrderEntity {

    @Id
    private String id;

    @Field("amount")
    private BigDecimal amount;

    private Integer quantity;
    private Instant createdAt;
}
```

If MongoDB contains:

```javascript
{
  _id: "ORD-1002",
  amount: "N/A",
  quantity: "2",
  createdAt: "14/11/2026"
}
```

Spring Data requires appropriate mappings/converters. Some fields may convert while others throw exceptions depending on Spring Data version, registered converters, and property types.

### 33.1. Java Bean Validation Differs from MongoDB `$jsonSchema`

Annotations such as `@NotNull`, `@Positive`, and `@Email` belong to Java/Spring validation when enabled. They **do not prevent direct MongoDB writes or scripts** from bypassing app checks.

Conversely, a MongoDB collection validator does not automatically adjust Java entity classes or conversion settings.

### 33.2. Account for `@Field` Aliases

If Java property `createdAt` maps to BSON `"created_at"`:

```java
@Field("created_at")
private Instant createdAt;
```

a MongoDB validator on `"createdAt"` checks the wrong field if stored documents use `"created_at"`. Compare physical BSON field names when designing migrations.

### 33.3. Custom Converters Can Mask Bad Types

A converter that turns any unparseable String into `0` makes the app "keep running" with corrupted data. Converters must define input domains, error behavior, auditing, and tests; for monetary/identifier data, **failing explicitly is far better than a wrong fallback**.

## 34. `MongoWriteException` and `MongoBulkWriteException`

In the Java Sync Driver, exception handling depends on API/driver version.

Single-write example:

```java
import com.mongodb.MongoWriteException;

try {
    collection.insertOne(document);
} catch (MongoWriteException ex) {
    int code = ex.getError().getCode();

    if (code == 121) {
        // Schema validation failure.
        // Log redacted metadata and return an appropriate domain validation error.
    }

    throw ex;
}
```

### 34.1. Bulk Writes Can Fail Partially

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(
        writeModels,
        new BulkWriteOptions().ordered(false)
    );
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        int requestIndex = error.getIndex();
        int code = error.getCode();

        // Map requestIndex -> business record ID safely.
        recordFailedWrite(requestIndex, code);
    }

    throw ex;
}
```

`writeModels` and `recordFailedWrite` must be implemented by the application. This emphasizes **never treating the entire batch as wholly failed or wholly succeeded** when partial success occurs.

### 34.2. Ordered vs. Unordered

- **Ordered:** stops after a write model fails, while earlier writes may have succeeded.
- **Unordered:** processes independent writes after an error and reports multiple write errors.
- **Not a batch-wide atomic transaction** unless executed inside an explicit transaction.

### 34.3. Do Not Retry Code 121 Indefinitely

Validation failures are usually permanent data/rule errors; retrying the exact same payload will fail again. Only retry after underlying data or schema has been fixed and idempotency is assured.

## 35. Other Errors That Look Like Schema Failures

| Error | Clue | Remediation direction |
|---|---|---|
| Duplicate key (`11000`) | Unique index conflict | Check business keys and duplicate data |
| Validator failure (`121`) | `$jsonSchema` or other validator | Read collection options and violation details |
| Conversion error | `$to*`/`$convert` cannot convert | Preview + classify bad values |
| Type mismatch in update | `$inc` on non-numeric field | Check `$type` of the field |
| Path conflict | Updating nested field on scalar or duplicate path | Check document structure |
| BSON encoding error | Driver cannot serialize | Codec/POJO/UUID |
| `ClassCastException` | Java reads wrong type | Check actual BSON type and mapping |
| Document too large | Exceeds BSON document limit | Redesign data model |
| `Unauthorized` | Missing permissions | Fix IAM/RBAC, do not bypass |
| Write concern error | ACK/durability condition unmet | Reconcile; do not assume not written |
| Network timeout | Write outcome unknown | Check idempotency and operation status |

Do not classify every case by searching for the substring `"validation"` in logs. Inspect error codes, commands, and timestamps.

## 36. Procedure for Finding Mistyped Legacy Data

A read-only workflow prior to making edits:

### Step 1 — Document the Desired Schema

```text
amount: Decimal128, >= 0, required
quantity: Int32 >= 1, required
createdAt: BSON Date, required
status: one of NEW, PAID, CANCELLED
```

### Step 2 — Count by Type

```javascript
db.orders.aggregate([
  { $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
  }},
  { $sort: { count: -1 } }
]);
```

### Step 3 — Fetch Restricted/Authorized Samples

```javascript
db.orders.find(
  { amount: { $type: "string" } },
  { _id: 1, tenantId: 1, amount: 1 }
).limit(20);
```

Never copy this output into public logs since `amount`/tenant values may be sensitive per policy.

### Step 4 — Preview Conversion

```javascript
db.orders.aggregate([
  { $match: { amount: { $type: "string" } } },
  { $project: {
      amountPreview: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
  }}
]);
```

### Step 5 — Classify

```text
Convertible safely
Needs locale-specific parsing
Ambiguous
Missing
Null
Out of range
Invalid business value
```

### Step 6 — Remediation + Audit

Execute updates only after approval, with appropriate backups/snapshots or recovery points and measurable record-change counts.

## 37. Two-Phase Data Migration: Preview First, Update Second

A structured pattern:

```text
Read source
    │
    ▼
Preview / parse / classify
    │
    ├── VALID_CONVERTIBLE
    ├── AMBIGUOUS
    ├── INVALID
    └── MISSING
             │
             ▼
Approved conversion plan
             │
             ▼
Staging migration
             │
             ▼
Data reconciliation
             │
             ▼
Production canary
             │
             ▼
Batch update with checkpoints
             │
             ▼
Enable strict validator
```

### 37.1. Do Not Update Everything with One Unverified Command

Bad:

```javascript
db.orders.updateMany(
  {},
  [
    { $set: { amount: { $toDecimal: "$amount" } } }
  ]
);
```

A single invalid String causes a conversion error; moreover, an unbounded update imposes heavy load and complicates recovery.

### 37.2. Filter by Type and Partition

Staging example:

```javascript
db.orders.updateMany(
  {
    tenantId: "T-01",
    amount: { $type: "string" }
  },
  [
    {
      $set: {
        amountDecimalCandidate: {
          $convert: {
            input: "$amount",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    }
  ]
);
```

This creates only a **candidate field** without overwriting the original `amount`. Still, it is a write operation: verify whether the collection validator permits the candidate field, plus write concern, capacity, and monitoring. Count `null` outputs rather than treating them as successful conversions.

### 37.3. If the Validator Forbids New Fields

You may need a staging collection, valid schema expansion, or an external migration program. Never bypass a production validator to add fields without approval.

### 37.4. Only Replace the Primary Field After Preview

A safer approach is generating a **verified mapping from input ID → parsed value**, then writing with type/version guards in the filter to avoid overwriting newer concurrent updates.

## 38. Avoiding Race Conditions Between Migration and Application

Example:

```text
T1 Migration reads amount = "100.00"
T2 User updates amount to Decimal128("120.00")
T3 Migration writes Decimal128("100.00")
```

The migration overwrote newer data.

### 38.1. Use Guards When Updating

When a business key and source version exist:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1002",
    migrationVersion: 3,
    amount: "100.00"
  },
  {
    $set: {
      amount: NumberDecimal("100.00"),
      migrationVersion: 4
    }
  }
);
```

If the document changed, the filter does not match. The application must handle `matchedCount=0` by re-reading/reclassifying rather than treating it as success.

### 38.2. Do Not Use Separate Check-Then-Update Without Guards

Reading in Java and deciding to write seconds later can operate on stale state. Put preconditions inside the **atomic operation itself** when concurrency control is needed.

### 38.3. Idempotency

A migration should be safely re-runnable without corrupting data. `$set` to a verified target value is usually easier to reason about than `$inc` or run-count-dependent updates.

## 39. Running Migrations in Batches with Checkpoints

On collections with hundreds of millions of documents:

- Partition by tenant;
- Partition by `_id` or time ranges;
- Rate-limit writes per second;
- Track attempted/acknowledged/failed record counts;
- Persist resume checkpoints after batches are acknowledged;
- Monitor CPU, cache, disk I/O, and replication lag;
- Define stop conditions and rollback procedures.

Example:

```text
Batch ID: 2026-11-14-T01-005
Range: tenant=T-01, _id from A100 to A200
Eligible: 500
Converted: 475
Invalid: 20
Ambiguous: 5
Acknowledged updates: 475
Checkpoint: committed through A200 with exception list
```

Do not advance checkpoints past unresolved records without proper retry/dead-letter tracking.

### 39.1. Bulk Partial Failures

With unordered bulk writes, some documents may be rejected by schema validation while others update. Map errors back to record IDs and persist state for retry after remediation.

### 39.2. Do Not Let Migrations Exhaust Production Resources

A job modifying millions of records impacts the journal, oplog, index maintenance, replication, and cache. Throttle throughput and stop if critical API read/write p99 exceeds thresholds.

## 40. Protecting Data Before Remediation

Before fixing types in production:

1. Ensure an appropriate backup/recovery point exists.
2. Verify restore capability meets required RPO/RTO.
3. Ensure changes stay strictly within the approved namespace/scope.
4. Capture baseline statistics beforehand.
5. Run a canary on a small set of IDs.
6. Reconcile afterward.
7. Maintain a recovery path if conversion logic is wrong.
8. Record the owner and change window.

### 40.1. Backups Are Not an Instant Per-Record Undo Button

Restoring an older snapshot can lose newer writes. If remediation goes wrong, you may need reverse patches from before-values or reconciliation rather than a full database restore.

### 40.2. Never Store Raw Before-Values Insecurely

Legacy values can contain PII/secrets. If before/after audits are required, use secured storage with strict access control and retention limits.

## 41. From Loose Schema to Strict Schema: Expand-and-Contract

A rollout strategy:

```text
Current:
  Legacy data mixed BSON types
  Old and new writers coexist
             │
             ▼
Phase 1: Observe
  type distribution + validation warn
             │
             ▼
Phase 2: Update writers
  all services produce canonical types
             │
             ▼
Phase 3: Backfill
  convert eligible legacy documents
  quarantine ambiguous records
             │
             ▼
Phase 4: Reconcile
  counts, sums, key invariants
             │
             ▼
Phase 5: Enforce
  strict validator + error action
             │
             ▼
Phase 6: Monitor
  rejects, p99, job errors
```

### 41.1. Schema Compatibility During Rolling Deploys

If older app versions still send String while newer versions send Decimal128, enabling `strict` too early breaks old pods. Switch to enforcement only after **all writers** are upgraded or retired.

### 41.2. Use Intermediate Fields When Necessary

In some migrations:

```javascript
{
  amountLegacy: "249900.00",
  amountDecimal: NumberDecimal("249900.00")
}
```

allows new app versions to read the new field while older versions still exist. Define the source of truth and conflict resolution, and avoid indefinite dual-writes.

### 41.3. Contract After the Rollback Window Closes

Only drop legacy fields and tighten `additionalProperties` once no apps/consumers depend on them, data is reconciled, and backups/rollback paths are clear.

## 42. Multiple Writers and Validator Drift

A system with:

```text
API Service A: amount Decimal128
Batch Job B: amount String
CDC Consumer C: amount Double
Admin Script D: amount NumberInt
```

If you only fix API A, errors will return.

### 42.1. Inventory Producers

Build a table:

| Producer | Current type written | Target | Owner | Status |
|---|---|---|---|---|
| Checkout API | Decimal128 | Decimal128 | Payments team | PASS |
| CSV Import | String | Decimal128 | Operations | TODO |
| CDC consumer | Double | Decimal128 | Data team | TODO |
| Admin script | Int32 | Decimal128 | DBA | TODO |
| Backfill worker | Mixed | Decimal128 | Platform | TODO |

### 42.2. Synchronize Contracts

Every producer must share a common schema contract and test fixtures. Across multiple languages/SDKs, verify each serializer; never assume a Java converter and a Node parser handle Decimal128 identically.

## 43. Invalid Data in Kafka/CDC or Restores

A new schema validator can cause **replaying historical events** to fail when older event payloads do not match the current contract.

Example:

```text
Old event: amount = "100.00"
Current MongoDB validator: amount must be Decimal128
Replay → rejected
```

### 43.1. Event Schema Versioning

Consumers should inspect event versions and transform payloads before writing to MongoDB. Never force all historical events into a current schema without a conversion plan.

### 43.2. Poison Messages

A permanently invalid event can stall an entire partition if the consumer retries infinitely. Use dead-letter queues or quarantine with reason codes, manual remediation, and controlled replay.

### 43.3. Restores Can Reintroduce Legacy Data

An older backup restored into a newer application may contain mixed BSON types; validator/index definitions also depend on the backup artifact/method. After restore, test:

- Actual schema validator;
- Type distribution;
- Java decoding;
- Unique/TTL behavior;
- Application business flows.

**A successful backup restore does not mean the new schema is compatible with the restored data.**

## 44. Testing Validation with Good and Bad Cases

A test suite should include at least:

| Case | `amount` | Expected |
|---|---|---|
| Valid | `NumberDecimal("100.00")` | Pass |
| Numeric string | `"100.00"` | Fails strict decimal |
| Int32 | `NumberInt(100)` | Fails strict decimal if schema allows only decimal |
| Null | `null` | Fails if required non-null decimal |
| Missing | field absent | Fails if required |
| Negative | `NumberDecimal("-1")` | Fails minimum 0 |
| Empty text | `""` | Fail |
| Not a number | `"N/A"` | Fail |
| Nested object | `{value:100}` | Fail |
| Array | `[100]` | Fail |
| Very large decimal | Valid Decimal128 | Depends on domain bounds |
| Duplicate business key | Same tenant + `orderNo` | Must be rejected by unique index |

### 44.1. Test at Both Layers

- **Application:** validators/mappers handle input and return clear business errors.
- **MongoDB:** database itself rejects invalid writes when bypassing the app layer, if business rules require it.

Unit tests mocking repositories do not prove collection-level `$jsonSchema` works.

### 44.2. Create a Separate Lab Collection

Tests intentionally failing inserts/updates must target a dedicated test database/collection, never writing bad data to production.

## 45. Java Integration Test for Code 121

A logical test pattern:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@Test
void rejectsWrongBsonType() {
    MongoCollection<Document> collection =
        testDatabase.getCollection("validated_orders");

    Document invalid = new Document("_id", "TEST-INVALID-1")
        .append("tenantId", "T-01")
        .append("orderNo", "A-TEST")
        .append("amount", "100.00")
        .append("createdAt", new java.util.Date());

    MongoWriteException ex = assertThrows(
        MongoWriteException.class,
        () -> collection.insertOne(invalid)
    );

    assertEquals(121, ex.getError().getCode());
}
```

This is an **illustrative test** requiring JUnit dependencies, a fixture collection with a validator, a real MongoDB server, and proper lifecycle cleanup.

### 45.1. Do Not Assert Exact Error Message Strings

Messages/nested details may differ across driver/server versions. For stable tests, assert on error code/category and expected postconditions. You can assert field paths when the application contract defines a dedicated mapping layer.

### 45.2. Include Negative Tests for Uniqueness

A write duplicating a business key is rejected by a unique index with a different error code and should not be classified as 121.

## 46. Testing Spring Data Mapping and Converters

Example entity:

```java
@Document("validated_orders")
class OrderEntity {
    @Id String id;
    String tenantId;
    BigDecimal amount;
    Integer quantity;
    Instant createdAt;
}
```

Tests should cover:

1. Java → BSON encodes to the right types.
2. BSON → Java decodes to the right classes.
3. Mixed legacy types are read or fail cleanly in a controlled manner.
4. Custom converters round-trip accurately.
5. Date timezones are accurate.
6. Decimal scale/precision is preserved per business rules.
7. Null/missing field behavior.
8. `@Field` aliases.
9. Repository queries/aggregations over mixed data.
10. Exceptions map to appropriate API errors.

### 46.1. Use Actual MongoDB for Integration Tests

A mocked `MongoTemplate` only tests Java logic; it does not prove MongoDB validators, unique indexes, or real BSON decoding. For data-integrity risks, run integration tests against a MongoDB test deployment matching production features/versions.

### 46.2. Do Not Alter Schema Just to Make a Test Pass

If a test shows `Decimal128` decoding incorrectly, fix the converter or source data per contract. Never convert all money fields to `Double` simply because a POJO currently uses `Double`.

## 47. Optimizing Queries That Scan for Bad Data

Scanning huge collections for bad types can spike CPU/I/O.

### 47.1. Partition the Scan

Example:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "T-01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $project: {
      type: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$type",
      count: { $sum: 1 }
    }
  }
]);
```

If `createdAt` itself mixes String and Date, a Date range filter will skip legacy String records. In that case, partition by `_id`/tenant/shard key or a more stable field per contract.

### 47.2. Avoid Full Collection Scans During Peak Hours

Options:

- Route to an appropriate secondary per read preference/lag if business allows;
- Run during off-peak traffic;
- Limit concurrency;
- Use statistical sampling followed by full reconciliation;
- Run against a staging copy;
- Monitor API p95/p99.

### 47.3. `limit` Does Not Replace a Full Audit

`limit(20)` provides samples, not the total count of invalid records. Maintain partition-level counts/reconciliation when hard evidence is needed.

## 48. Using `explain()` Without Assuming Every Bug Is an Index Problem

When querying a mixed-type field:

```javascript
db.orders.find({
  amount: { $gte: NumberDecimal("100000") }
}).explain("executionStats");
```

`explain` reveals the query plan, keys/docs examined, and latency, yet **it does not prove data values are valid**. A fast query may be fast simply because it skipped all String records.

Combine:

- Type distribution;
- Schema violation counts;
- Business total reconciliation;
- Query plans;
- Application integration tests.

### 48.1. Mixed Types and Sort Order

MongoDB defines a comparison order across BSON types. If a field contains both Strings and numerics, sorting may not reflect the numerical ordering expected by the business.

Do not "fix" this by adding an index before normalizing data types and defining the query contract.

## 49. Security When Investigating Data Errors

Validation details can expose values:

```text
consideredValue = "someone@example.com"
```

or nested objects holding sensitive information.

Proper incident response requires:

- Logging only field names/types/error codes whenever possible;
- Redacting raw values;
- Stripping customer identifiers from public logs;
- Using trace IDs instead of raw documents;
- Restricting full-collection read permissions;
- Never disabling TLS verification;
- Never using `root` simply because an API user lacks privileges;
- Protecting before/after exports;
- Enforcing retention on diagnostic artifacts;
- Never copying real production samples into unauthorized environments.

### 49.1. Never Turn a Schema Error into a Security Bypass

If a validator rejects documents missing `tenantId`, never "fix" it by removing `tenantId` from `required` just to import unvalidated data. That risks cross-tenant authorization and data-integrity defects.

## 50. Monitoring and Alerting for Schema/Type Incidents

A dashboard should track:

### 50.1. Error Counts and Rates

- Writes attempted/s;
- Schema validation rejects/s;
- Conversion errors/s;
- BSON codec/mapping errors/s;
- Duplicate key errors/s;
- Failed records by importer/job;
- Error rate by collection, tenant scope, and producer version.

### 50.2. Data Quality

- Type distribution per field;
- Missing/null required fields;
- Invalid enum counts;
- Decimal conversion failure counts;
- Date parse failure counts;
- Remaining legacy records;
- Partition reconciliation mismatches;
- Quarantined documents;
- Last successful schema migration.

### 50.3. Operations

- Read/write p95/p99;
- CPU/disk/cache;
- Replication lag;
- Bulk partial failures;
- Retry counts;
- Dead-letter queue depth;
- Data backfill throughput;
- Schema version deploy timeline.

### 50.4. Impact-Based Alerts

An alert rule:

```text
Schema validation failure rate > 1%
AND write traffic > minimum threshold
FOR 10 minutes
```

is only an example; set thresholds from product SLOs. For monetary writes or access-control fields, certain validation violations may warrant immediate alerting.

### 50.5. Do Not Build Dashboards from an Incomplete Source

Server logs, application exceptions, and MongoDB metrics cover different scopes. Some codec errors never reach the server, so a dashboard tracking only MongoDB code 121 will miss them entirely.

## 51. Schema Validation Incident Runbook

```text
INCIDENT ID:
TIME:
ENVIRONMENT:
NAMESPACE:
ERROR RATE:
BUSINESS IMPACT:
OWNER:

SYMPTOM:
  MongoDB 121 / conversion / Java codec / other

CHANGE HISTORY:
  App version:
  Driver/Spring version:
  Validator migration:
  Import source:

EVIDENCE:
  Trace IDs:
  Error code/name:
  Redacted details:
  Actual collection validator:
  BSON type distribution:
  Affected document keys:
  Counts by tenant/time:

CLASSIFICATION:
  Wrong producer type
  Legacy data
  Invalid business value
  Schema conflict
  Driver mapping
  Aggregation conversion
  Security / permissions

CONTAINMENT:
  Pause offending job:
  Error response:
  Retry strategy:
  Rollback criteria:

REMEDIATION:
  Data fix version:
  App fix version:
  Staging tests:
  Backup / recovery point:
  Canary range:
  Write rate limit:

POSTCONDITIONS:
  Invalid count:
  Conversion error count:
  Business totals:
  Index/validator:
  API p95/p99:
  CDC/replication:

DECISION:
  GO / HOLD / ROLLBACK / RECOVER

CLOSURE:
  Evidence links:
  Approval:
  Follow-up:
```

### 51.1. Runbooks Must Have Stop Conditions

Example:

```text
If invalid count increases,
business totals diverge,
or critical API write p99 exceeds guardrail:
  STOP data backfill.
```

### 51.2. Do Not Use One "Fix Everything" Command

Each error class needs targeted remediation. `amount:"N/A"` cannot be handled the same way as `amount:"249900.00"` without an authoritative source.

## 52. Remediation Decision Table by Root Cause

| Root cause | What to do | What not to do |
|---|---|---|
| Missing required field | Identify data source, populate per contract | Fabricate meaningless dummy values |
| Convertible numeric string | Parse with validation, audit, and benchmark | Turn all errors into `0` |
| Invalid decimal/locale | Identify locale/unit, quarantine if ambiguous | Guess commas vs. dots |
| BSON Int32 vs. Java Long | Fix mapping/converter or canonicalize type | Cast blindly without checks |
| Invalid date string | Use explicit format/timezone or reject | Parse by guessing |
| ObjectId mismatch | Keep business ID in proper type; convert if contract fits | Convert every String ID to ObjectId |
| `"false"` string | Explicit boolean mapping | Blind `$toBool` |
| Wrong enum casing | Normalize per business semantics | Lowercase/uppercase blindly without tests |
| Unique conflict | Deduplicate per policy | Arbitrarily delete records |
| Unexpected TTL | Check retention/index | Immediately disable production TTL |
| Validator drift | Versioned migration + catalog verification | Edit only Java annotations |
| Legacy invalid records | Checkpointed backfill, staging tests | Enable `strict` and ignore old data |
| Aggregation conversion failure | `$convert.onError`, classify records | Run `$to*` across everything and retry forever |
| `CodecConfigurationException` | Configure codec/POJO properly | Disable validator |
| Bulk partial failure | Map write indexes/IDs, reconcile | Report the entire batch as succeeded |
| `Unauthorized` | Fix IAM/RBAC | Use `root` long-term or bypass auth |

## 53. Testing Error Scenarios Systematically

### 53.1. Test Matrix

| Test | Input | Expected |
|---|---|---|
| Valid insert | Decimal128 + Date | Success |
| Wrong `amount` type insert | String | Code 121 under strict schema |
| Update legacy invalid | Old String document | Behavior per `validationLevel` |
| Missing required field | Missing `tenantId` | Validation failure |
| Enum out of range | `"paid"` | Validation failure |
| Negative numeric | Decimal128(-1) | Minimum rule failure |
| Wrong array element | `tags` contains number | Items rule failure |
| Additional property | Extra field | Fails if forbidden |
| Invalid conversion | `"N/A"` → decimal | `onError` branch |
| Ambiguous date | `"03/04/2026"` | Reject/parse per explicit format |
| Malformed ObjectId | `"abc"` | Conversion failure |
| Bool string | `"false"` | Not mistakenly mapped to `true` |
| Java `getLong` on Int32 | Integer | Type mismatch detected |
| Unordered bulk | One failing record | Partial errors tracked |
| Concurrent update | Revision changed | Guard prevents overwrite |
| Retry after timeout | Write outcome unknown | Reconciliation/idempotency |
| Restore legacy backup | Mixed types | Explicit migration plan |
| Re-enable `strict` | All writers upgraded | No unexpected rejects |

### 53.2. Include Both Positive and Negative Tests

Testing only valid inputs is insufficient. Prove invalid data is rejected at the right layer and the application returns clear errors without leaking data.

### 53.3. Never Run Tests Against Production

Use dedicated test databases/collections, test identities, and approved teardown. A test deliberately violating unique indexes or TTL in production can affect real data.

## 54. Exercise 1 — Identifying the Error Layer

Given four scenarios:

1. Server returns code 121 on insert.
2. Java `Document.getLong()` throws `ClassCastException`.
3. Aggregation `$toDate` fails.
4. Unique index returns `11000`.

Identify the failing layer, required evidence, and proper remediation for each. Explain why all four cannot be "fixed" with `validationAction:"warn"`.

## 55. Exercise 2 — Finding Type Distribution

Collection `orders` has mixed `amount` types.

1. Write a `$group` aggregation by `$type`.
2. Write a query to sample String values.
3. Distinguish `missing` from `null`.
4. Add per-tenant reporting.
5. How would you limit production impact?

## 56. Exercise 3 — Valid `$jsonSchema`

Write a schema requiring:

- `tenantId`: non-empty String;
- `orderNo`: String, required;
- `amount`: non-negative Decimal128;
- `quantity`: Int32 >= 1;
- `createdAt`: Date;
- `status`: one of `NEW`, `PAID`, `CANCELLED`.

Create valid/invalid input sets and state the expected error category for each.

## 57. Exercise 4 — Legacy Invalid Data and `moderate`

A collection has 2 million documents with String `amount`, yet needs a Decimal128 validator.

1. How does `strict` affect updates to old records?
2. What are the pros and cons of `moderate`?
3. Do producers need fixing first?
4. How do you measure the invalid record count?
5. When do you switch to `strict`?

## 58. Exercise 5 — Converting to Decimal128

Inputs:

```text
"249900"
"249900.00"
"249,900"
"N/A"
""
null
NumberInt(249900)
```

Design a `$convert` preview and classification table. Propose a business policy for unconvertible values; never replace them with `0` without knowing their meaning.

## 59. Exercise 6 — Dates and Timezones

Given strings:

```text
"14/11/2026"
"2026-11-14T04:00:00Z"
"03/04/2026"
"2026-02-30"
```

1. Which values are unambiguous and which are ambiguous?
2. When should `$dateFromString` be used?
3. How do you choose the timezone?
4. How do you verify the instant after conversion?
5. Why must epoch seconds vs. milliseconds be distinguished?

## 60. Exercise 7 — Boolean Trap

Source:

```javascript
{ active: "true" }
{ active: "false" }
{ active: 0 }
{ active: 1 }
{ active: "" }
{ active: null }
```

Write an explicit mapping to `true`/`false`, decide which values are invalid, and explain the risk of using `$toBool` directly.

## 61. Exercise 8 — Int32/Int64

1. Differences among Int32, Int64, Double, and Decimal128.
2. When does `2^53+1` get rounded?
3. Why should ID `"000123"` not be auto-converted to `123`?
4. Does `Document.getLong()` handle `NumberInt`?
5. Write Java mapping code with type checks.

## 62. Exercise 9 — Nested Validator

Document:

```javascript
{
  shipping: {
    address: {
      countryCode: 100
    }
  }
}
```

The schema requires `countryCode` to be String.

1. Identify the failing property path.
2. Design a safe log entry.
3. How do you avoid leaking the user's address?
4. If `shipping.address` is a scalar, what problem arises when updating the nested path?

## 63. Exercise 10 — `additionalProperties`

A schema enables `additionalProperties:false` but forgets `_id`.

1. Why can inserts fail?
2. Write the corrected schema.
3. How is a rolling deployment adding an optional field affected?
4. When should strict enforcement be turned on?
5. Can this schema replace authorization?

## 64. Exercise 11 — Bulk Partial Failure

A bulk operation has 500 `UpdateOneModel` items, 12 mistyped records, and `ordered(false)`.

1. How many records can succeed?
2. How do you inspect `MongoBulkWriteException`?
3. How do you map error indexes back to business IDs?
4. When should you retry?
5. How do you record checkpoints?

## 65. Exercise 12 — Concurrent Backfill

A worker reads String `amount` `"100.00"`; the application updates it to Decimal128 `"120.00"` before the worker writes.

1. What race condition occurred?
2. Write a filter with expected old value/revision.
3. How do you handle `matchedCount=0`?
4. Choose checkpoint/idempotency mechanics.
5. When is CDC catch-up needed?

## 66. Exercise 13 — Spring Data Mapping

Entity has `BigDecimal amount`, legacy DB has `amount:"N/A"`.

1. Determine whether the error is in the Java converter or MongoDB validator.
2. Write a BSON → Java integration test.
3. Why can a custom converter returning `BigDecimal.ZERO` be wrong?
4. How do you surface an appropriate business error?
5. Check `@Field` aliases.

## 67. Exercise 14 — Restoring from an Old Backup

After restore, a collection contains both Decimal128 and String `amount`; the new application enables a strict validator.

1. Is old data repaired automatically?
2. Why might updates fail?
3. Write a preflight scan.
4. Design a backfill and validator rollout plan.
5. Should backup tool/driver compatibility be verified?

## 68. Exercise 15 — Revenue Total Accuracy

Source:

```text
1000 valid Decimal128 orders
50 numeric String orders
10 "N/A" orders
```

An aggregation using only `$sum` on numeric values produces an undercounted total.

1. Why is the total wrong even without an error?
2. Count and reconcile each group.
3. Handle the 10 indeterminate records.
4. Which source provides the expected financial total?
5. Post-migration verification.

## 69. Exercise 16 — Monitoring

Design a dashboard tracking:

- Schema rejects/s;
- Conversion failures;
- Codec errors;
- Failed data import records;
- Type distribution;
- Retry/dead-letter;
- Application write p95/p99;
- Replication lag;
- Data completeness.

Explain which source misses errors caused by client-side BSON encoding failures.

## 70. Exercise 17 — Creating an Incident Runbook

Scenario: After deployment, the checkout API fails 8% of writes with code 121.

Write a runbook covering:

1. Scope and impact;
2. Evidence to preserve;
3. How to inspect the new validator;
4. Comparing producer versions;
5. Non-destructive containment;
6. Staging reproduction;
7. Fix/rollback gates;
8. Postconditions.

## 71. Exercise 18 — GO/NO-GO Decision

A migration reports:

```text
Producers fixed: PASS
Legacy invalid count: 2,500
Ambiguous amount: 17
Backup restore drill: NOT DONE
Business totals: MISMATCH
Strict validator ready: YES
```

1. Can production switch to `strict`?
2. What are the blockers?
3. What remediation and data approvals are needed?
4. Is a backup/restore test required?
5. When can it be declared completed?

## 72. Incident Diagnosis Checklist

### Evidence

- [ ] Recorded operation/namespace/time/tenant scope.
- [ ] Captured error code/name, not just a raw message.
- [ ] Distinguished server validation, aggregation conversion, and Java codec.
- [ ] Read actual collection validator/options.
- [ ] Recorded server/driver/Spring versions.
- [ ] Captured release/migration timeline.
- [ ] Redacted PII/secrets from logs.

### Data

- [ ] Profiled BSON type distribution.
- [ ] Distinguished `missing` from `null`.
- [ ] Checked numeric range/precision.
- [ ] Checked Date/timezone/format.
- [ ] Checked `ObjectId` and business IDs.
- [ ] Checked arrays/nested objects.
- [ ] Checked enums/unique/TTL separately.
- [ ] Classified convertible/ambiguous/invalid records.
- [ ] Defined business rules for remediation.

### Operations

- [ ] Inventoried all producers.
- [ ] Assessed write/replication impact.
- [ ] Avoided infinite retries on permanent errors.
- [ ] Avoided arbitrarily enabling bypass/disabling validators.
- [ ] Verified backups and recovery paths.
- [ ] Defined rollback/stop conditions.
- [ ] Distinguished copied/attempted/acknowledged counts.
- [ ] Assigned a responsible owner.

## 73. Pre-Backfill and Schema Hardening Checklist

- [ ] Ran conversion preview on staging.
- [ ] Prepared fixtures for tricky edge-case data.
- [ ] New producers emit canonical BSON types.
- [ ] Ambiguous data routed to a review queue.
- [ ] Batch size, rate limit, and checkpoints configured.
- [ ] Idempotency/version guards in place.
- [ ] Counts and business totals reconciled.
- [ ] Backup/restore verified where needed.
- [ ] ACL/KMS/PII requirements verified.
- [ ] Incident owner assigned.
- [ ] All writers compatible with the new validator.
- [ ] Plan ready to move `warn`/`moderate` to `strict`/`error`.
- [ ] Integration tests run against real MongoDB.
- [ ] Post-rollout monitoring active.
- [ ] Completion/rollback-window closure criteria defined.

## 74. Official References

Consult documentation for the **exact MongoDB Server, Java Driver, and Spring Data MongoDB versions**:

- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [Schema Validation Options](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB `$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB JSON Schema Validation Errors](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Comparison and Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB `$type` Query](https://www.mongodb.com/docs/manual/reference/operator/query/type/)
- [MongoDB `$type` Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB `$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB `$toInt`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toInt/)
- [MongoDB `$toLong`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/)
- [MongoDB `$toDecimal`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/)
- [MongoDB `$toDate`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [MongoDB `$toObjectId`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toObjectId/)
- [MongoDB `$toBool`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toBool/)
- [MongoDB `$dateFromString`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [MongoDB Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB `collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Driver BSON Guide](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/bson/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Data MongoDB Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Conclusion

Troubleshooting schema validation and BSON type errors in MongoDB is an exercise in **investigating the right layer, understanding the actual data, and remediating under control**.

When encountering **code 121**, inspect the actual collection validator and validation details to learn which field/rule failed. When an aggregation fails on `$to*`, use `$convert` with `onError`/`onNull` to classify inputs before deciding how to repair them—never coerce everything to `0` or `null`. When the Java Driver or Spring Data throws `ClassCastException`, `CodecConfigurationException`, or mapping errors, compare actual BSON types with classes/converters rather than assuming the database validator is at fault.

The most frequent culprits include **Strings instead of Decimal128, Int32/Int64 mismatches, Dates stored as Strings, ObjectIds confused with business IDs, `"false"` misparsed during Boolean conversion, `null`/missing fields, and malformed arrays/nested objects**. Beyond explicit exceptions, mixed types can silently cause queries/aggregations to return incomplete totals or unexpected sort orders **without raising any error**.

A resilient system requires a canonical BSON schema, all producers adhering to the contract, and legacy data converted via **preview → classify → staging → canary → batch repair → reconciliation**, backed by checkpoints, concurrency guards, backups, and rollback plans. Only after full reconciliation should you tighten the validator, paired with monitoring for code 121, conversion failures, mapping errors, p95/p99, and data quality.

**The goal is not merely to make write operations stop throwing errors, but to ensure every repaired document preserves its true business meaning, uses the right BSON type, and can be safely read and written by every application.**
