# Unique Indexes, Duplicate Data, and Missing or Null Values

> **Chapter:** Indexes  
> **Module:** `SPRING_DATA_MONGODB` — connecting with Spring Data MongoDB, mapping documents, and manipulating data via `MongoTemplate` or repositories; practicing query design, aggregation, indexing, transactions, reactive access, testing, and data performance diagnostics.  
> **Objectives:** Understand uniqueness constraints in MongoDB; distinguish single-field unique, compound unique, sparse unique, and partial unique indexes; accurately explain missing fields, BSON `null`, and empty values; detect duplicate data before building an index; apply via `@Indexed`/`@CompoundIndex` and `MongoTemplate.indexOps()`; test `E11000` errors, concurrent updates, and safe migrations.

## 1. Business Scenario: Unique Emails That May Not Yet Be Provided

Suppose a customer system allows creating accounts **without an email**. Once a customer supplies a valid email, the application wants to guarantee that no two accounts in the same tenant share the same normalized email.

A seemingly simple definition:

~~~javascript
db.customers.createIndex(
  { email_norm: 1 },
  { unique: true }
);
~~~

However, the collection may contain:

~~~javascript
{ _id: "c101", name: "An", email_norm: "an@example.test" }
{ _id: "c102", name: "Binh" }                    // missing email_norm
{ _id: "c103", name: "Chi", email_norm: null }   // has email_norm, value null
{ _id: "c104", name: "Dung" }                    // also missing email_norm
~~~

**A standard single-field unique index does not allow this state**: both **missing** fields and BSON `null` generate an index key with value `null`. Having more than one document with a `null` key causes **unique index creation to fail** or **new writes to be rejected** if the index already exists.

This is not a Spring Data-specific quirk. It is **MongoDB server-side semantics**. `@Indexed(unique = true)` does not turn `null` into "skip uniqueness check".

### 1.1. Four Questions to Answer Before Creating the Index

1. **At what scope is uniqueness enforced?** Across the whole collection or per `tenantId`?
2. **Documents without a value**: are multiple allowed, or only one?
3. **Are `null`, missing, `""`, and whitespace-only strings** treated as equivalent?
4. **Does normalization/casing** affect equality?

No single `unique: true` option satisfies all of these policies. You must choose the right **index keys**, **partial filter or sparse**, **data types**, **collation**, and **normalization rules**.

## 2. How Unique Indexes Work and What They Do Not Guarantee

A unique index ensures no **two distinct documents** share the same index key within the constraint scope. MongoDB creates a unique index by default on `_id`.

~~~javascript
// Collection-wide unique key:
db.customers.createIndex({ email_norm: 1 }, { unique: true });

// Compound unique key:
db.customers.createIndex(
  { tenant_id: 1, email_norm: 1 },
  { unique: true }
);
~~~

| Index | Disallowed duplicates | Allowed cases |
| --- | --- | --- |
| `{email_norm:1}` unique | Identical email across entire collection | Different emails |
| `{tenant_id:1,email_norm:1}` unique | Same tenant/email **pair** | Same email across **two different tenants** |
| `{email_norm:1}` unique sparse | Identical email among documents **having email_norm field** | Multiple documents missing the field |
| `{email_norm:1}` unique partial with `$type:"string"` | Identical email string among indexed documents | Multiple missing/null documents excluded from filter |

### 2.1. Uniqueness Is a Data Constraint, Not Just an Optimizer Hint

Regular indexes help speed up queries. **A unique index also rejects writes violating uniqueness** on inserts, updates, or upserts, even when writes go directly through the MongoDB Java Driver instead of Spring Data repositories.

An empty result from `findByEmailNorm(...)` **does not replace** a unique index:

~~~text
Request A: find(email) -> not found
Request B: find(email) -> not found
Request A: insert(email) -> succeeds
Request B: insert(email) -> WITHOUT a unique index, can also succeed
~~~

A unique index protects at the **server write step**. Pre-checks before writing remain useful for friendly error messages, but an index is required to prevent races between concurrent writers.

### 2.2. Unique Does Not Mean the Data Is Already Clean

An index **does not automatically delete** existing duplicate documents. If the collection contains two violating keys, `createIndex(..., {unique:true})` will **fail**; you must clean data and control writers before creating it successfully.

A unique index also **does not replace**:

- BSON type validation (email must be a string, not an array).
- Normalizing emails, order codes, or phone numbers before saving.
- Tenant authorization.
- Cross-collection referential constraints.
- Business rules such as "one verified customer may have only one active email".

## 3. Self-Verification: Single-Field Unique with Missing and Null Values

All examples use an **isolated test collection** inside `spring_data_mongodb_lab`. Do not run `drop()` on real application collections.

### 3.1. Creating a Collection Without a Unique Index

~~~javascript
use spring_data_mongodb_lab

const legacy = db.customers_unique_legacy_004;

legacy.insertMany([
  { _id: "l401", tenant_id: "t01", email_norm: "an@example.test" },
  { _id: "l402", tenant_id: "t01", email_norm: "an@example.test" },
  { _id: "l403", tenant_id: "t01", email_norm: null },
  { _id: "l404", tenant_id: "t01" },
  { _id: "l405", tenant_id: "t02" },
  { _id: "l406", tenant_id: "t01", email_norm: "" }
]);
~~~

This collection intentionally includes two kinds of potentially violating data:

- `l401/l402` duplicate an actual email.
- `l403` has `email: null`, while `l404/l405` **omit the email field**.

`l406` has the **empty string** `""`; this value is **not** BSON `null`. However, if another document has email `""`, a unique index treats that as a duplicate empty-string key.

### 3.2. Attempting to Create a Unique Index and Reading the Error

~~~javascript
legacy.createIndex(
  { email_norm: 1 },
  { unique: true, name: "ux_email_norm" }
);
// Existing data has duplicate keys -> index build fails,
// typically returning an E11000 duplicate key error.
~~~

An index cannot be assumed created simply because code called `createIndex`. Check the command result and index metadata:

~~~javascript
legacy.getIndexes();
// Verify whether ux_email_norm with unique:true actually appears.
~~~

**Note:** inserts with fixed IDs run only once on a clean fixture. Treat subsequent examples as independent scenarios; to re-run, use a fresh test collection or clean up only documents you own.

### 3.3. Single-Field Unique: Missing and Null Share the Same Index Key

Suppose a new collection already has a unique index on `email_norm`:

~~~javascript
const strict = db.customers_unique_strict_004;
strict.createIndex(
  { email_norm: 1 },
  { unique: true, name: "ux_email_strict" }
);

strict.insertOne({ _id: "s401", email_norm: "a@example.test" });
strict.insertOne({ _id: "s402", email_norm: null });

// The FOLLOWING operations are expected to fail while the index remains:
strict.insertOne({ _id: "s403" });                 // missing -> null key
strict.insertOne({ _id: "s404", email_norm: null }); // explicit null
strict.insertOne({ _id: "s405", email_norm: "a@example.test" });
~~~

After `s402`, both a new missing field and a new explicit null collide with the existing `null` key. If tested in the reverse order, the first missing document takes the `null` key and the subsequent explicit null fails. The constraint is **at most one document with a `null` unique key**, not "at most one missing plus one null".

### 3.4. Result Matrix for Single-Field Unique

| New document | Allowed with non-sparse single-field unique? | Reason |
| --- | --- | --- |
| One document with `"a@example.test"` | Yes, if that key does not exist yet | Distinct value |
| Second document with `"a@example.test"` | **No** | Duplicate string key |
| One document with missing email | Yes, if no null key exists yet | Missing is indexed as null |
| Second document with missing email | **No** | Duplicate null key |
| One document with `null` after missing | **No** | Same null key |
| One document with `""` | Yes, if no `""` exists yet | Empty string is a string value |
| Second document with `""` | **No** | Duplicate empty string |

This is important to remember when a Java model has nullable `String email`: having multiple entities with Java `null` does not mean MongoDB lets them coexist in a non-sparse unique index.

## 4. Missing, Null, and Empty String Are Three Distinct States

MongoDB distinguishes **an absent field**, **a field with BSON null**, and **a field with an empty string**. When querying, know which comparison matches which case:

~~~javascript
// Matches explicit null AND missing:
legacy.find({ email_norm: null });

// Only absent field:
legacy.find({ email_norm: { $exists: false } });

// Only field with BSON null type:
legacy.find({ email_norm: { $type: "null" } });

// Has field containing an empty string:
legacy.find({ email_norm: "" });
~~~

### 4.1. States and Index Impact

| BSON | `{email_norm:null}` | `{$exists:false}` | `{$type:"null"}` |
| --- | --- | --- | --- |
| No `email_norm` | Yes | Yes | No |
| `email_norm:null` | Yes | No | Yes |
| `email_norm:""` | No | No | No |
| `email_norm:"an@example.test"` | No | No | No |

`{email_norm:{$exists:true}}` matches both strings and explicit null. That is why **`$exists:true` does not mean "email is not null"**.

### 4.2. `null` in Java Does Not Fully Describe BSON Storage

A Java object:

~~~java
class Customer {
    private String emailNorm; // null
}
~~~

may be written by the converter as a missing field or an explicit BSON null depending on annotations, configuration, or write path. Yet a **standard single-field unique index treats both cases as the null key**. When APIs need to distinguish them, establish a clear data contract:

- **Missing:** customer has not provided an email.
- **Explicit null:** email was removed or the system intentionally stores null.
- **Empty string:** zero-length string; usually input data that should be normalized or rejected.

In real systems, **standardize on one policy** rather than letting all three representations of "no email" appear randomly.

### 4.3. Other Special States

`"   "` (all whitespace) is also **a distinct string different from `""`** unless normalized. `"An@Example.test"` and `"an@example.test"` are two distinct strings under default binary comparison. Numbers or arrays must not appear in an email field if the schema expects a string.

A unique index does not validate email syntax or equate the values above by default. Define a normalization policy and add application/MongoDB validation.

## 5. `unique + sparse`: Skips Missing, Does NOT Skip Null

A **single-field** sparse index only indexes documents **containing that field**. When combined with `unique:true`, duplicates among indexed documents are still rejected.

~~~javascript
const sparse = db.customers_unique_sparse_004;

sparse.createIndex(
  { email_norm: 1 },
  {
    unique: true,
    sparse: true,
    name: "ux_email_sparse"
  }
);

sparse.insertOne({ _id: "p401" });                // succeeds: missing
sparse.insertOne({ _id: "p402" });                // succeeds: missing
sparse.insertOne({ _id: "p403", email_norm: null }); // succeeds: first null

// The following writes will be rejected:
sparse.insertOne({ _id: "p404", email_norm: null });

sparse.insertOne({ _id: "p405", email_norm: "a@example.test" });
sparse.insertOne({ _id: "p406", email_norm: "a@example.test" });
// p405 succeeds; p406 fails with duplicate key.
~~~

**Key difference:** multiple missing documents are permitted, but **at most one explicit null** is allowed in a single-field unique sparse index (because null is still indexed).

### 5.1. Decision Table: Regular Unique vs. Single-Field Unique Sparse

| Scenario | Regular unique | Single-field unique sparse |
| --- | --- | --- |
| Multiple docs missing email | No | **Yes** |
| Multiple docs with explicit null email | No | No |
| Multiple docs with email `""` | No | No |
| Multiple docs with same valid email | No | No |
| Docs with distinct emails | Yes | Yes |

If the policy is **"allow multiple customers with missing or null email"**, enabling `sparse:true` alone **is not enough**.

### 5.2. Sparse Also Affects Query Plans

A sparse index omits documents missing the field. MongoDB typically avoids using it for queries that might require **documents with missing fields**, since scanning the index would yield incomplete results. Forcing `hint()` on a sparse index to count/find across the collection can return incomplete results.

Indexes serve two roles: **write constraints** and **read optimization**. Evaluate both when choosing sparse.

## 6. `unique + partialFilterExpression`: Constrain Only the Target Subset

A partial index indexes **only documents matching a filter**. With `unique:true`, uniqueness applies **only across the indexed subset**.

### 6.1. Allowing Both Multiple Missing and Multiple Explicit Null

A common policy:

> Only customers whose `email_norm` is a **BSON string** must have a unique email; accounts missing an email or with null email may coexist.

~~~javascript
const partial = db.customers_unique_partial_004;

partial.createIndex(
  { email_norm: 1 },
  {
    name: "ux_email_nonnull_string",
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);

partial.insertOne({ _id: "q401" });                  // missing
partial.insertOne({ _id: "q402" });                  // missing
partial.insertOne({ _id: "q403", email_norm: null }); // null
partial.insertOne({ _id: "q404", email_norm: null }); // null
partial.insertOne({ _id: "q405", email_norm: "a@example.test" });

// Fails due to duplicate string:
partial.insertOne({ _id: "q406", email_norm: "a@example.test" });
~~~

`$type:"string"` is supported by MongoDB in partial filters. Documents missing the field or having BSON null fail the filter and are not constrained by this unique index.

**Caution:** MongoDB `$type` queries on an array field match when **an element of the array** has the specified type. Therefore, a policy requiring "email must be a scalar string" should combine **schema validation** and a properly typed Java model rather than relying solely on a partial filter to block arrays or wrong types.

### 6.2. Do Not Use `$exists:true` to Exclude Null

Wrong if the goal is to skip null:

~~~javascript
partialFilterExpression: {
  email_norm: { $exists: true }
}
~~~

Because an explicit null is still an **existing field**, this filter indexes null. If the collection has two documents with explicit null, a unique partial index with this filter will fail with `E11000`.

Comparison:

| Filter | Missing | Explicit null | String |
| --- | --- | --- | --- |
| `{$exists:true}` | Skipped | **Indexed** | Indexed |
| `{$type:"string"}` | Skipped | Skipped | **Indexed** |
| `{email_norm:"verified@example.test"}` | Skipped | Skipped | Only emails matching that value |

`$type:"string"` is commonly used to enforce uniqueness for supplied values, though `""` and whitespace strings must still be handled.

### 6.3. Partial Unique for Active Accounts

Another policy:

> Emails only need to be unique among `ACTIVE` accounts; `DELETED` accounts may retain duplicate historical emails.

~~~javascript
db.customers_unique_active_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_active_tenant_email",
    partialFilterExpression: {
      status: "ACTIVE",
      email_norm: { $type: "string" }
    }
  }
);
~~~

This index enforces uniqueness for the tenant/email pair **only when** `status = ACTIVE` and email is a string.

If you transition a DELETED document to ACTIVE, MongoDB must insert a new index entry. If an ACTIVE account already holds that tenant/email pair, the **state transition itself fails with E11000**. Partial unique is not an insert-only check; it applies to **every write that moves a document into or out of the indexed subset**.

### 6.4. Partial Indexes and Query Coverage

MongoDB will not use a partial index for a query if doing so would omit documents the query requires. For instance, an index covering only `status:"ACTIVE"` is insufficient to return **all** customers of a tenant if the query does not restrict status.

~~~javascript
// Eligible for the partial index:
db.customers_unique_active_004.find({
  tenant_id: "t01",
  status: "ACTIVE",
  email_norm: "a@example.test"
});

// Not eligible by default: includes DELETED.
db.customers_unique_active_004.find({
  tenant_id: "t01"
});
~~~

Use `explain("executionStats")` to verify planner selection on real workloads; do not force `hint` arbitrarily.

### 6.5. Sparse and Partial Cannot Be Combined in One Definition

MongoDB and Spring Data index definitions **do not allow combining** `sparse:true` with `partialFilterExpression` on the same index as a way to "AND both conditions". Pick **one** mechanism. Partial can usually express richer conditions than sparse; test carefully with missing and null data.

## 7. Compound Unique Indexes: Uniqueness by Tenant and Email

In multi-tenant applications, "unique email" usually means:

~~~text
(tenant_id, email_norm) must be unique
~~~

rather than unique across **all tenants**.

~~~javascript
const tenants = db.customers_unique_tenants_004;

tenants.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_tenant_email"
  }
);

tenants.insertOne({
  _id: "t401",
  tenant_id: "t01",
  email_norm: "an@example.test"
});

tenants.insertOne({
  _id: "t402",
  tenant_id: "t02",
  email_norm: "an@example.test"
});
// Succeeds: same email, different tenant.

tenants.insertOne({
  _id: "t403",
  tenant_id: "t01",
  email_norm: "an@example.test"
});
// E11000: duplicate (t01, an@example.test) pair.
~~~

### 7.1. Compound Unique Does Not Automatically Skip Null/Missing Components

If you have:

~~~javascript
{ _id: "t404", tenant_id: "t01" }
{ _id: "t405", tenant_id: "t01", email_norm: null }
~~~

then with a regular compound unique index, both share the equivalent key pair:

~~~javascript
{ tenant_id: "t01", email_norm: null }
~~~

Only one document in the collection can hold **that key pair**, if not already taken. However, another tenant can hold `(t02, null)` because the **combination** differs.

The core point is that **compound unique checks the combined key**, without requiring every key component to be non-null.

### 7.2. Pitfall: Compound Unique Sparse Still Indexes Missing Emails

A very common mistake:

~~~javascript
db.customers.createIndex(
  { tenant_id: 1, email_norm: 1 },
  { unique: true, sparse: true }
);
~~~

Authors assume sparse will skip every document missing `email_norm`. However, for a **compound sparse index with standard ascending/descending fields**, MongoDB indexes a document if **at least one key field is present**.

If `tenant_id` is always present, nearly every document gets an index entry even when `email_norm` is missing. Two documents in the same tenant without an email end up sharing `(t01, null)` and **still violate uniqueness**.

**Conclusion:** Do not use `unique+sparse` on `(tenant_id,email_norm)` as a default way to allow multiple customers without emails in the same tenant.

### 7.3. The Right Design: Compound Unique Partial

~~~javascript
db.customers_unique_tenant_partial_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_tenant_email_present",
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

Achieved policy:

- `t01 + a@example.test`: at most one document.
- `t02 + a@example.test`: allowed (different tenant).
- `t01` missing email: multiple documents allowed.
- `t01` explicit null email: multiple documents allowed.
- Empty string `""` **is still a string**, so at most one document per tenant can have `""` unless validation blocks it beforehand.

If `tenant_id` itself could be missing/null, normalize and validate tenant separately: a partial filter checking only email **does not** replace the requirement for a valid tenant, and key pairs with a null tenant could still occur.

## 8. Case-Insensitive Uniqueness, Collation, and Normalization

A default index distinguishes:

~~~text
An@Example.test
an@example.test
~~~

using binary comparison. If the product treats these two values as the **same email identity**, the policy must be explicitly modeled.

### 8.1. Approach A: Store a Normalized Key

For example, the application stores:

~~~javascript
{
  email: "An@Example.test",     // display value
  email_norm: "an@example.test" // key used for uniqueness checks
}
~~~

with a unique index on `email_norm`. All writes must pass through the same normalization/validation logic.

**Business note:** Email local-part rules can depend on providers and system policies; do not arbitrarily strip dots, plus-tags, or alter Unicode normalization. Define normalization consistently and test it. Without an explicit policy, **do not** assume all emails are case-insensitive in every component.

### 8.2. Approach B: Unique Collation

MongoDB supports collation to specify string comparison rules. Example locale-based case-insensitive collation:

~~~javascript
db.customers_collation_004.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "ux_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

At strength 2, comparisons usually ignore case differences while still distinguishing certain other differences per locale. Exact behavior depends on the collation and characters. If two emails differ only by case, unique collation prevents the second document.

When querying to leverage this collated index:

~~~javascript
db.customers_collation_004.find(
  { email: "AN@example.test" }
).collation({
  locale: "en",
  strength: 2
});
~~~

If a query lacks a compatible collation, the optimizer may not use the index for string comparison as expected. Distinguish between **the index's uniqueness rules** and **how queries compare strings**.

### 8.3. Pick One Clear Strategy

Do not normalize one way while creating a collation with different comparison rules without defining equivalence. Changing normalization or collation policies can create **newly colliding keys** in legacy data and cause unique index migrations to fail.

## 9. Unique Multikey Indexes and Arrays: Important Limitations

An indexed field may be an array:

~~~javascript
db.accounts_arrays_004.createIndex(
  { aliases: 1 },
  { unique: true }
);
~~~

A unique multikey index prevents **two distinct documents** from containing the same index key. However, within a **single document**, repeated elements may produce only one index entry:

~~~javascript
// If no document in the collection has alias "a":
db.accounts_arrays_004.insertOne({
  _id: "a401",
  aliases: ["a", "a", "b"]
});
// Unique multikey does not catch duplicate "a" elements within the same document.
~~~

Inserting another document:

~~~javascript
db.accounts_arrays_004.insertOne({
  _id: "a402",
  aliases: ["b", "c"]
});
// E11000 because alias "b" already belongs to another document.
~~~

Therefore, **unique multikey does not guarantee "no duplicate elements within a single document's array"**. If business rules require that, add validation or update operators like `$addToSet` (which has its own nuances for object equality) and appropriate tests.

MongoDB also imposes constraints on compound multikey indexes when multiple indexed fields are arrays; do not index "parallel arrays" expecting the server to accept arbitrary schemas. That topic is separate from scalar email uniqueness and requires reviewing dedicated multikey documentation.

## 10. Detecting Duplicates Before Building a Unique Index

Converting a non-unique index or a legacy collection to unique must start with **the data**, not annotations.

### 10.1. Finding Real Duplicate Emails (Strings Only)

~~~javascript
legacy.aggregate([
  {
    $match: {
      email_norm: { $type: "string" }
    }
  },
  {
    $group: {
      _id: "$email_norm",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]);
// On fixture: an@example.test has l401 and l402.
~~~

This checks **currently stored** values. If the policy will lowercase or trim whitespace, check duplicates **against the post-migration normalized key**, not just raw current strings.

### 10.2. Detecting Duplicate Tenant + Email Pairs

~~~javascript
legacy.aggregate([
  { $match: { email_norm: { $type: "string" } } },
  {
    $group: {
      _id: {
        tenant: "$tenant_id",
        email: "$email_norm"
      },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
~~~

When the target index is compound unique partial, the audit must share the exact **scope**: tenant + (normalized) email + partial filter policy. Do not check email alone when the same email across two tenants is valid.

### 10.3. Finding Missing and Null Values

~~~javascript
// Documents missing the field completely:
legacy.find({ email_norm: { $exists: false } });

// Documents with explicit BSON null:
legacy.find({ email_norm: { $type: "null" } });

// All documents with null or missing email:
legacy.find({ email_norm: null });
~~~

For a **non-partial** single-field index, count documents in `email_norm:null` per null-key uniqueness rules. For a string-only unique partial index, missing/null documents fall outside the index scope, though schema and business policies still need checking.

### 10.4. Avoid Grouping Null Without Distinguishing States

~~~javascript
legacy.aggregate([
  {
    $group: {
      _id: "$email_norm",
      count: { $sum: 1 }
    }
  }
]);
~~~

Grouping directly on a field containing both missing values and BSON null merges them into one `_id:null` group, making it easy to assume all of them are explicit null. To **distinguish them**, project `$type` before grouping or run separate `$exists:false` and `$type:"null"` queries.

## 11. Migration Workflow for Duplicate Data Before Enabling Constraints

A sound production plan must address **both historical data and live concurrent writers**. The steps below illustrate the design; never delete production data automatically.

<escape>1.</escape> **Define the uniqueness contract.** Choose global vs. tenant-scoped unique; whether multiple missing/null emails are allowed; what the normalized form is; whether soft-deleted accounts participate.

<escape>2.</escape> **Assess collection and workload.** Measure document count, existing indexes, sharding, replication, index permissions, write volume, deployment windows, and rollback feasibility.

<escape>3.</escape> **Audit duplicates under the target key.** Produce a report with `_id`, tenant, raw/normalized value, status, and cause; avoid logging unnecessary PII.

<escape>4.</escape> **Decide resolution per duplicate group.** Is merging accounts permitted? Are there order references to reassign? Which document is canonical? Never arbitrarily `deleteMany` or keep the first document without a business decision.

<escape>5.</escape> **Deploy validation/normalization first.** Ensure all new writes obey the policy; manage transition races, using write gating, maintenance windows, or coordination as needed.

<escape>6.</escape> **Backfill with checkpoints.** Batch updates, log business actions, handle errors idempotently, check related references, and never discard data solely because an email collided.

<escape>7.</escape> **Re-audit, then create the index.** If `createIndex` returns `E11000`, do not mark migration successful. Stop, locate remaining duplicates or conflicting new writes, resolve, and retry.

<escape>8.</escape> **Verify metadata and behavior.** Use `getIndexes()`, targeted duplicate insert/update tests, duplicate-error metrics, and verify the application surfaces appropriate exceptions.

<escape>9.</escape> **Monitor post-deployment.** Ensure signup, email update, upsert, account activation, and migration jobs do not fail with unhandled exceptions.

### 11.1. Do Not Rely on Automatic "Drop Duplicates"

Modern MongoDB unique indexes offer no safe "enable unique and let the server delete duplicates" flag. Old options like `dropDups` from legacy APIs are no longer a valid migration mechanism. Merging two customer records is a **business decision**, not an index build side effect.

### 11.2. Never Fix Duplicates by Running `deleteMany` on a Key Without Review

Wrong:

~~~javascript
// DO NOT USE in production:
// db.customers.deleteMany({ email_norm: "an@example.test" });
~~~

That command deletes both the canonical record and the duplicate. The right approach is to list canonical IDs, verify references, apply only approved edits, and keep backups and a rollback strategy.

### 11.3. Concurrent Writes During Index Build

An audit query might come back clean at 10:00, yet a live writer inserts a duplicate before the index build finishes. Therefore, you need a plan to **prevent violating writes during migration**, rather than treating an earlier count query as a guarantee.

In replica sets and sharded clusters, follow MongoDB's supported index-build procedures and understand rolling index-build limitations. Never manually build indexes node-by-node without ensuring data consistency per deployment guidelines.

## 12. Java Spring Data: `@Indexed(unique = true)`

### 12.1. Entity with a Single-Field Unique Index

~~~java
// CustomerDocument.java
package com.example.mongoindexes;

import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "customers_spring_index_004")
public class CustomerDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("email_norm")
    @Indexed(unique = true, name = "ux_email_norm_global")
    private String emailNorm;

    protected CustomerDocument() { }

    public CustomerDocument(
            String id, String tenantId, String emailNorm) {
        this.id = id;
        this.tenantId = tenantId;
        this.emailNorm = emailNorm;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getEmailNorm() { return emailNorm; }
}
~~~

`@Indexed(unique=true)` declares the **intent to create a unique index** on that field. Because the entity specifies `@Field("email_norm")`, Spring Data knows the BSON field is `email_norm` when resolving index metadata.

**Warning:** this example defines a **global single-field unique** index. It **does not satisfy** the policy "one email per tenant, allowing multiple missing/null values". Choose the index matching requirements; do not copy this annotation to production if compound partial is needed.

### 12.2. Auto-Index Creation Is Disabled by Default

Since Spring Data MongoDB **3.0**, automatic index creation at startup or first entity access **is disabled by default** to avoid unintended impacts on data and performance. Simply adding `@Indexed` **is not proof that the server has a unique index**.

Two strategies exist:

1. **Coordinated migrations** executing index creation after auditing duplicates—recommended for production.
2. **Explicitly configured index creation** via Spring Data/`IndexResolver` in appropriate environments and timing.

If auto-index is enabled on duplicate data, application startup or index initialization may **fail**. Never respond by deleting data or swallowing exceptions to bypass uniqueness.

### 12.3. Unique Sparse Annotation

~~~java
@Field("email_norm")
@Indexed(
    name = "ux_email_sparse",
    unique = true,
    sparse = true
)
private String emailNorm;
~~~

This index allows multiple documents **missing the email field**, but still limits to **one explicit null** under single-field unique sparse rules. Use only when that matches the exact policy.

### 12.4. Unique Partial Annotation

~~~java
@Field("email_norm")
@Indexed(
    name = "ux_email_nonnull",
    unique = true,
    partialFilter = "{ 'email_norm': { '$type': 'string' } }"
)
private String emailNorm;
~~~

`partialFilter` is a JSON expression for a MongoDB partial index. Use exact BSON field names inside the filter expression and verify the actual index definition on the server. `@Indexed` does not allow combining `sparse=true` and `partialFilter` in the same annotation.

**Important:** the three annotation declarations in sections 12.1–12.4 are **alternatives**—**do not** place them simultaneously on the same field to create conflicting unique indexes without a migration plan.

## 13. Compound Unique and `@CompoundIndex`

If the policy requires per-tenant uniqueness:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers_spring_tenant_004")
@CompoundIndex(
    name = "ux_tenant_email",
    def = "{ 'tenantId': 1, 'emailNorm': 1 }",
    unique = true
)
public class CustomerByTenant {
    @org.springframework.data.mongodb.core.mapping.MongoId(
        org.springframework.data.mongodb.core.mapping.FieldType.STRING)
    private String id;

    @org.springframework.data.mongodb.core.mapping.Field("tenant_id")
    private String tenantId;

    @org.springframework.data.mongodb.core.mapping.Field("email_norm")
    private String emailNorm;

    protected CustomerByTenant() { }
}
~~~

`@CompoundIndex` is placed on the class. `def` in this example uses **Java property names** so Spring Data mapping resolves them to BSON `tenant_id/email_norm` when building the index definition. Verify `getIndexes()` in test/prod to avoid path mismatches when custom converters are involved.

**Warning:** compound unique **does not automatically skip null/missing**. To support optional emails per tenant, you can:

- Create a compound unique **partial** index via an explicit MongoDB migration.
- Or use `IndexOperations`/`Index` with a partial filter, then verify server index options.

Do not blindly switch to `sparse=true` on the compound index, because `tenant_id` is always present and still causes documents missing email to be indexed.

## 14. `MongoTemplate.indexOps()` for Explicit Index Creation

### 14.1. Single-Field Unique via Spring Data

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public void ensureEmailUniqueIndex(MongoTemplate template) {
    template.indexOps(CustomerDocument.class)
        .ensureIndex(
            new Index()
                .on("emailNorm", Sort.Direction.ASC)
                .unique()
                .named("ux_email_norm_global")
        );
}
~~~

`indexOps(CustomerDocument.class)` gives Spring Data the domain class metadata and field mapping. However, `ensureIndex(...)` succeeds only if existing data **does not violate** the unique index. It also does not automatically convert an existing index with the same name but different options to match the new policy—manage migrations and metadata explicitly.

### 14.2. Compound Partial via `Index` and `PartialIndexFilter`

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

public void ensureOptionalTenantEmailIndex(
        MongoTemplate template) {
    Index unique = new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("emailNorm", Sort.Direction.ASC)
        .unique()
        .named("ux_tenant_email_present")
        .partial(
            PartialIndexFilter.of(
                Criteria.where("email_norm").type(2)
                // BSON type 2 = string.
            )
        );

    template.indexOps(CustomerDocument.class)
        .ensureIndex(unique);
}
~~~

The names in `.on("tenantId")` and `.on("emailNorm")` are **Java properties** mapped using entity metadata; when building a partial filter, understand `PartialIndexFilter`/mapped options and verify the resulting BSON. Here `email_norm` matches the fixture's physical BSON field. Use raw MongoDB migrations if you want to avoid any ambiguity about partial-filter mapping across Spring Data versions.

**Do not keep both the global unique index `ux_email_norm_global` and the compound partial index** when the goal is to allow the same email in two tenants or multiple missing/null values: the global index will keep rejecting those writes. Changing an index policy requires reviewing **all existing unique indexes**.

### 14.3. Inspecting Index Metadata

In `mongosh`:

~~~javascript
db.customers_spring_index_004.getIndexes();
~~~

Expected for global unique:

~~~javascript
{
  key: { email_norm: 1 },
  name: "ux_email_norm_global",
  unique: true
}
~~~

For partial indexes, you must see `partialFilterExpression`. For compound indexes, verify `key: {tenant_id:1,email_norm:1}`. **Index name alone does not prove options are right**.

### 14.4. `IndexResolver` with Annotations

Spring Data provides `MongoPersistentEntityIndexResolver` to extract definitions from `@Indexed`, `@CompoundIndex`, and other annotations. An application coordinating annotation-based creation can do:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.IndexResolver;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;

public void resolveAndEnsure(MongoTemplate template) {
    var mappingContext =
        template.getConverter().getMappingContext();

    IndexResolver resolver =
        new MongoPersistentEntityIndexResolver(mappingContext);

    resolver.resolveIndexFor(CustomerDocument.class)
        .forEach(
            definition -> template
                .indexOps(CustomerDocument.class)
                .ensureIndex(definition)
        );
}
~~~

This illustrates the **resolver mechanism**, not a recommendation to create production unique indexes arbitrarily without data checks. If startup tries to build a global unique index from annotations while violating data exists, the app may fail to boot; index migrations should be coordinated.

## 15. `E11000` Errors and Java Exceptions

When an insert or update violates a unique constraint, MongoDB typically returns a duplicate key error with code **11000** along with the violated index and key details.

Example message (structure illustration only):

~~~text
E11000 duplicate key error collection: ...
index: ux_tenant_email_present
dup key: { tenant_id: "t01", email_norm: "an@example.test" }
~~~

Do not parse English error message strings to drive business logic—formatting can change across server/driver versions or configurations. In Spring Data, the exception is translated to `org.springframework.dao.DuplicateKeyException` along supported repository/`MongoTemplate` paths.

### 15.1. Catching at an Appropriate Service Layer

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final CustomerRepository repository;

    public CustomerRegistrationService(
            CustomerRepository repository) {
        this.repository = repository;
    }

    public CustomerDocument register(
            CustomerDocument newCustomer) {
        try {
            return repository.insert(newCustomer);
        } catch (DuplicateKeyException duplicate) {
            // Translate into a domain/API error, e.g. HTTP 409,
            // after confirming this corresponds to the expected business index.
            throw new CustomerEmailAlreadyUsedException(duplicate);
        }
    }
}
~~~

Here `CustomerRepository` is `MongoRepository<CustomerDocument,String>`. `CustomerEmailAlreadyUsedException` is a **project-defined domain exception** (not declared in the snippet). The snippet focuses on error handling and needs appropriate exception classes and domain mapping in real usage.

**Do not assume every `DuplicateKeyException` is a duplicate email**: it could also be `_id` or another unique index. In production, identify the violated constraint using structured error metadata when available, log safely, and handle accordingly.

### 15.2. Pre-Checking Before Insert Does Not Close the Race

~~~java
if (!repository.existsByTenantIdAndEmailNorm(
        tenantId, emailNorm)) {
    repository.insert(customer);
}
~~~

This snippet has a race between `exists` and `insert`. Only a server-side unique index prevents two concurrent writers from inserting the same key. You can keep `exists` for UX feedback, but **must catch duplicate errors at write time**.

### 15.3. Upserts and Email Updates Can Still Collide

~~~javascript
db.customers_unique_tenant_partial_004.updateOne(
  { _id: "customer-123", tenant_id: "t01" },
  { $set: { email_norm: "an@example.test" } }
);
~~~

If `(t01, an@example.test)` already belongs to another customer, `$set` fails. Uniqueness is not enforced only on insert.

Similarly, `upsert:true` with a filter lacking a unique key or sufficient constraints can trigger duplicate collisions under concurrency. A unique index is the safety net, but services still need proper idempotency/retry handling and must never blindly retry every `E11000`.

## 16. Transactions, Bulk Writes, and Concurrency

### 16.1. Transactions Do Not Replace Unique Indexes

A MongoDB transaction provides all-or-nothing writes across operations when supported by the topology and driver. However, if two concurrent transactions try to insert the same tenant/email pair, the unique index remains the final arbiter deciding which write succeeds.

Do not rely on `@Transactional` to guarantee uniqueness if the database **lacks a unique constraint**. Check-then-insert inside a transaction can still suffer write skew or different isolation/locking semantics; enforce uniqueness with indexes whenever possible.

### 16.2. Bulk Importing Legacy Data

When bulk-inserting into a collection with a unique index, part of the batch may succeed before an error depending on ordered/unordered mode and transactions. Do not assume an entire batch rolls back on a single duplicate document.

Import workflows need:

- Recording succeeded IDs and rejected IDs.
- Idempotent retries for transient errors.
- Distinguishing expected duplicates from connection or write-concern failures.
- Never automatically deleting existing duplicate records.
- Testing error handling for ordered/unordered bulk writes and transactions if used.

### 16.3. Unique Indexes on Sharded Collections

Sharding imposes **specific restrictions** on unique indexes: a unique index on a sharded collection generally must include the **shard key as a prefix** (subject to specific exceptions/policies such as the `_id` index, depending on where uniqueness is enforced). Do not assume global email uniqueness can be created on arbitrary sharded collections.

Before designing global uniqueness on a sharded cluster, verify shard key choices, MongoDB version, permitted index structures, and how uniqueness is enforced across shards.

MongoDB also **does not support `unique` on hashed indexes**. If uniqueness is needed on a key, you cannot switch it to hashed and add `unique:true`.

## 17. Case Study: Per-Tenant Email Policy with Missing Data

Requirement:

> A tenant may have multiple customers who have not provided an email. When an email is provided as a valid string, it must be unique **within that tenant**. Customers in different tenants may share the same email.

Recommended design:

1. **Schema:** `tenant_id` required, valid string; `email_norm` normalized string or missing/null per policy; disallow arrays/objects.
2. **Index:** compound unique partial `(tenant_id, email_norm)` filtering for string emails only.
3. **Application:** normalize and validate email before every insert/update; obtain tenant from security context.
4. **Migration:** find duplicates on the exact **post-normalization** compound key; clean data before building the index.
5. **Write handling:** catch `DuplicateKeyException` cleanly and return a domain conflict.
6. **Tests:** cover multiple missing/nulls, duplicate email within one tenant, same email across two tenants, and conflicting updates.

### 17.1. MongoDB Index Matching the Policy

~~~javascript
db.customers_policy_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    name: "ux_policy_tenant_email",
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

### 17.2. Behavioral Test Suite

~~~javascript
const c = db.customers_policy_004;

c.insertOne({ _id: "x401", tenant_id: "t01" });
c.insertOne({ _id: "x402", tenant_id: "t01" });
// Multiple missing: succeeds.

c.insertOne({ _id: "x403", tenant_id: "t01", email_norm: null });
c.insertOne({ _id: "x404", tenant_id: "t01", email_norm: null });
// Multiple explicit null: succeeds.

c.insertOne({
  _id: "x405", tenant_id: "t01",
  email_norm: "an@example.test"
});
c.insertOne({
  _id: "x406", tenant_id: "t02",
  email_norm: "an@example.test"
});
// Same email, different tenant: succeeds.

c.insertOne({
  _id: "x407", tenant_id: "t01",
  email_norm: "an@example.test"
});
// E11000: duplicate within the same tenant.
~~~

### 17.3. When Policy Allows Removing an Email

If a customer removes their email, you can choose:

~~~javascript
// Remove field: document exits the partial index:
c.updateOne({ _id: "x405" }, { $unset: { email_norm: "" } });

// Or set null, also excluded by partial $type:string:
c.updateOne({ _id: "x405" }, { $set: { email_norm: null } });
~~~

Pick **one consistent semantics** for "email removed". Both remove the old string key from the unique partial index, allowing another document to use the old email. If the product requires holding a released email for a cooldown period, build a separate **reservation/history rule**; unique partial indexes do not "hold" released values.

## 18. Integration Tests with Real MongoDB and Spring Data

Unit tests mocking `MongoRepository` neither prove MongoDB rejects duplicates nor verify the real index. Tests need a real MongoDB test instance or Testcontainers and must create indexes **before inserting data**.

### 18.1. Mandatory Test Matrix

| Test | Expectation |
| --- | --- |
| Global unique, same email | Duplicate key |
| Global unique, missing then null | Only one null key total |
| Unique sparse, two missing | Allowed |
| Unique sparse, two explicit null | Duplicate key |
| Unique partial `$type:"string"`, two missing | Allowed |
| Unique partial `$type:"string"`, two null | Allowed |
| Unique partial, two identical email strings | Duplicate key |
| Compound unique, same email across tenants | Allowed |
| Compound unique, same tenant/email | Duplicate key |
| Compound sparse when tenant is always present | Must not assume missing email is skipped |
| Compound partial with missing email in same tenant | Allowed |
| Update a customer to an already-used email | Duplicate key |
| Using `@Field("email_norm")` | Index targets exact BSON field |
| Auto-index creation off | Annotation does not mean index exists |
| Insert via `MongoTemplate` | `DuplicateKeyException` translated properly |
| Normalization/collation | Policy-equivalent values blocked |
| Index build on legacy duplicates | Fails without deleting data |

### 18.2. Illustrative Integration Test for Unique Partial

The test uses a **dedicated collection**, cleans only the IDs it creates, and runs only against an isolated test MongoDB instance.

~~~java
package com.example.mongoindexes;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.IndexOptions;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@DataMongoTest
class UniquePartialIndexTest {
    @Autowired MongoTemplate template;

    @org.springframework.data.mongodb.core.mapping.Document(
        collection = "customers_test_unique_004")
    static class TestCustomer {
        @MongoId(FieldType.STRING)
        private String id;

        @Field("email_norm")
        private String emailNorm;

        protected TestCustomer() { }

        TestCustomer(String id, String emailNorm) {
            this.id = id;
            this.emailNorm = emailNorm;
        }
    }

    @Test
    void partialUniqueAllowsMissingAndNullButRejectsDuplicateString() {
        var coll = template.getDb()
            .getCollection("customers_test_unique_004");
        List<String> ids = List.of(
            "fixture-u004-a",
            "fixture-u004-b",
            "fixture-u004-c",
            "fixture-u004-d",
            "fixture-u004-email",
            "fixture-u004-dup"
        );

        coll.createIndex(
            new org.bson.Document("email_norm", 1),
            new IndexOptions()
                .name("ux_test_email_string_004")
                .unique(true)
                .partialFilterExpression(
                    new org.bson.Document(
                        "email_norm",
                        new org.bson.Document("$type", "string")
                    )
                )
        );

        coll.deleteMany(Filters.in("_id", ids));
        try {
            coll.insertMany(List.of(
                new org.bson.Document("_id", ids.get(0)),
                new org.bson.Document("_id", ids.get(1)),
                new org.bson.Document("_id", ids.get(2))
                    .append("email_norm", null),
                new org.bson.Document("_id", ids.get(3))
                    .append("email_norm", null),
                new org.bson.Document("_id", ids.get(4))
                    .append("email_norm", "a@example.test")
            ));

            assertThat(coll.countDocuments(
                Filters.in("_id", ids.subList(0, 5))
            )).isEqualTo(5L);

            assertThatThrownBy(() ->
                template.insert(
                    new TestCustomer(
                        "fixture-u004-dup", "a@example.test")
                )
            ).isInstanceOf(DuplicateKeyException.class);

            assertThat(coll.countDocuments(
                Filters.eq("email_norm", "a@example.test")
            )).isEqualTo(1L);
        } finally {
            coll.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

In this example, `TestCustomer` maps to the test collection **without relying on automatic `@Indexed`**; the index is created via the driver with explicit options. `MongoTemplate.insert(...)` performs the write through Spring Data so `DuplicateKeyException` is observed on violation.

**Import note:** the test uses the fully qualified `org.springframework.data.mongodb.core.mapping.Document` on the class to avoid colliding with `org.bson.Document` used for BSON; avoid importing both simple names together. Manage fixtures and test databases so parallel tests never share collections or IDs.

### 18.3. Dedicated Test for Compound Partial

Use test collection `customers_policy_004` with `{tenant_id:1,email_norm:1}` unique partial. Test:

~~~text
t01, missing                  -> PASS
t01, missing (2nd document)   -> PASS
t01, null                     -> PASS
t01, null (2nd document)      -> PASS
t01, an@example.test          -> PASS
t02, an@example.test          -> PASS
t01, an@example.test 2nd time -> E11000
~~~

Test **both inserts and updates** moving into an existing key. A test that only inserts two different emails has not verified the core constraint.

### 18.4. Asserting Index Metadata

Beyond insert behavior, check `getIndexes()` for:

- Correct `key`: `email_norm` or `tenant_id + email_norm`.
- `unique:true`.
- `partialFilterExpression` matching the designed filter.
- `collation` if the product uses case-insensitive comparison.

Do not assert only the index name, because an index with the same name but different configuration/options may fail to enforce the policy. Verify the migration ran and no lingering **other global unique index** accidentally blocks cross-tenant usage.

## 19. Troubleshooting Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Cannot create unique index | Collection already has duplicate keys, including missing/null | Aggregate duplicates by target key and resolve per business rules |
| Two documents missing email rejected | Single-field unique without sparse | Revisit policy; consider partial unique |
| Unique sparse still fails on multiple nulls | Sparse index still indexes explicit null | Use a partial filter excluding null if policy allows |
| Compound unique sparse rejects two missing emails in same tenant | Tenant field is present so compound sparse indexes the doc | Use compound unique partial on string email |
| `$exists:true` still hits duplicate null | Explicit null satisfies `$exists:true` | Use `$type:"string"` when null must be excluded |
| Two customers with `""` email fail | Empty string is a real string value | Validate/normalize or reject empty strings |
| `An@...` and `an@...` coexist | Default binary index is case-sensitive | Normalize or use unique collation per policy |
| Same email in different tenant rejected | Global unique index still exists on email | Migrate safely to per-tenant compound unique |
| `@Indexed(unique=true)` has no effect | Auto-index creation is off or migration didn't run | Create index explicitly; check `getIndexes()` |
| App startup fails after enabling auto-index | Legacy duplicate data | Halt rollout, audit duplicates, clean before building |
| `save(entity)` throws `DuplicateKeyException` | Collision on `_id` or another unique key | Identify violated index/key; do not assume email error |
| Updating DELETED to ACTIVE fails | Document enters the partial unique index | Handle status/email conflict in business logic |
| Query ignores partial index | Query filter does not guarantee subset membership | Check `explain()` and query predicates |
| Collated query misses index | Query collation mismatches index collation | Ensure query uses the exact index collation |
| Unique multikey ignores repeated values in one array | Uniqueness applies across documents | Add separate array validation |
| Bulk import inserts partial batch before failing | Bulk is not atomic across whole batch by default | Track per-item results, retry/idempotency, transactions if needed |
| Duplicates slip past `existsBy...` check | Race between read and write | Server-side unique index + catch error on write |
| Sharded collection rejects arbitrary unique index | Shard-key prefix or index-type restrictions | Check sharding/index rules per version |

## 20. Pre-Deployment Checklist for Unique Indexes

1. **State the policy clearly**: global, per-tenant, ACTIVE-only, or non-null emails only.
2. **Define missing/null/empty semantics** in data and validation, not by inferring from Java null.
3. **Choose single-field or compound keys** matching the exact business scope.
4. **Choose sparse or partial correctly**; remember single-field sparse still indexes explicit null, and compound sparse behaves differently when tenant is present.
5. **Normalize strings** with a consistent policy, considering collation where needed.
6. **Audit duplicates on the target key**, including normalized values, tenant, and partial filter.
7. **Never auto-delete or auto-merge duplicates**: require canonical decisions, reference updates, and a rollback plan.
8. **Control concurrent writers** during migration and index builds.
9. **Never trust annotations alone**: verify the index exists on the server with exact options.
10. **Catch `DuplicateKeyException` on writes**, instead of relying on pre-checks to prevent races.
11. **Test inserts, updates, upserts, and bulk writes**, not only finds.
12. **Measure index impact** on write latency, storage, and query performance.
13. **Check sharding and index types** before relying on uniqueness in distributed clusters.
14. **Monitor post-rollout**: E11000 errors, conflict rates, legacy data, and active-account transitions.

## 21. Practice Exercises and Answers

### Exercise 1 — Two Documents Missing Email

A non-sparse unique index `{email_norm:1}` exists. Can you insert **two documents both lacking `email_norm`**?

**Answer:** No. Missing generates a null index key; at most one document can hold the null key. The second document violates uniqueness.

### Exercise 2 — Missing and Explicit Null

Document A lacks email, document B has `email_norm:null`. With a standard single-field unique index, can both coexist?

**Answer:** No. Both produce a null key. There are not separate quotas for missing and explicit null.

### Exercise 3 — Unique Sparse

How many missing-email documents does a single-field unique sparse index on email allow? How many explicit nulls?

**Answer:** Many missing documents because they are omitted from the index; at most one explicit null because null is a present field and gets indexed.

### Exercise 4 — Partial Filter Excluding Null

Write a unique index covering only string emails.

**Answer:**

~~~javascript
db.customers.createIndex(
  { email_norm: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

Schema validation is still needed to prevent unintended arrays/objects and to reject `""`.

### Exercise 5 — Why Is `$exists:true` Wrong Here?

Does partial filter `{email_norm:{$exists:true}}` exclude explicit null?

**Answer:** No. Null is still an existing field, so null documents are indexed and can trigger duplicate-key errors.

### Exercise 6 — Per-Tenant Unique

Are `t01` and `t02` having the same email `"an@example.test"` valid under compound unique `(tenant_id,email_norm)`?

**Answer:** Yes. The constraint applies to the **combination**. Two documents within `t01` sharing that email will be rejected.

### Exercise 7 — Compound Sparse Trap

Why can `{tenant_id:1,email_norm:1}` with `unique:true,sparse:true` still reject two customers in `t01` who both lack email?

**Answer:** Compound sparse indexes on regular ascending/descending fields index a document when **at least one indexed field is present**. Since tenant is always present, both get indexed with `(t01,null)` and collide.

### Exercise 8 — Case-Insensitive

Are `"An@Example.test"` and `"an@example.test"` always treated as duplicates by a regular unique index?

**Answer:** No. Under default binary comparison, they are distinct strings. You must implement normalization or a unique collation matching the policy.

### Exercise 9 — Duplicates in Legacy Data

Before creating a unique index on `email_norm` with 1 million documents, what command finds string duplicates?

**Answer:** Use an aggregation with `$match` for string type, `$group` by email, `count`, and `$match count > 1` as in section 10; repeat using normalized keys and compound keys if applicable.

### Exercise 10 — Safe Migration

Two customers sharing an email both have orders and history. Should you pick the first customer and delete the second just to build the index?

**Answer:** No. Business decisions are required regarding canonical account selection, references, auditing, access control, backups, and rollback. A unique index does not merge data.

### Exercise 11 — Spring Data Annotations

Does adding `@Indexed(unique=true)` guarantee the server immediately has a unique index?

**Answer:** No. Spring Data MongoDB 3.0+ disables auto-index creation by default; you need migrations/`indexOps` or explicit configuration, plus server index metadata verification.

### Exercise 12 — Error on Update

`(t01,an@example.test)` already exists. What happens when updating another `t01` customer's email to that value?

**Answer:** Rejected by the unique index just like an insert; typically returns E11000 and translates to `DuplicateKeyException` through Spring Data APIs.

### Exercise 13 — Check Before Write

Two requests both observe `existsByTenantIdAndEmailNorm(...) == false`. Can both inserts succeed without a unique index?

**Answer:** Yes. Pre-checks have race conditions. The database unique index is the primary enforcement boundary.

### Exercise 14 — Multikey

A document has `aliases:["a","a"]`. Does unique multikey automatically deduplicate elements inside the array?

**Answer:** No. Unique multikey enforces uniqueness **across documents**, not uniqueness of elements within a single document.

### Exercise 15 — ACTIVE Accounts

A unique partial index indexes only `status:"ACTIVE"`. Can two DELETED accounts share the same email? What if both transition to ACTIVE?

**Answer:** Both DELETED documents lie outside the filter and can coexist. When transitioning to ACTIVE, the index checks uniqueness; both cannot become ACTIVE with colliding keys.

### Exercise 16 — Lingering Global Index

You added a per-tenant compound unique partial index, yet the system still holds an older unique `{email_norm:1}` index. Can two tenants share an email yet?

**Answer:** Not yet, because the **old global unique index still enforces uniqueness**. Review all index definitions and migrate/drop the old index safely; do not auto-drop indexes from production application startup.

## References

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): single/compound unique, missing/null fields, duplicate data, multikey, and sharding limitations.
- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/): sparse vs. missing/null, compound sparse, and combining with unique.
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): `partialFilterExpression`, unique partial, query coverage.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): string comparison, locale, and strength.
- [MongoDB Manual — `$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/): BSON type checks and array element behavior.
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): unique multikey and indexed array constraints.
- [MongoDB Manual — Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/): building indexes on populated collections, operations, and error handling.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): auto-index off by default, IndexResolver, and IndexOperations.
- [Spring Data MongoDB — `@Indexed` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Indexed.html): `unique`, `sparse`, `partialFilter`, `collation`.
- [Spring Data MongoDB — `@CompoundIndex` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/CompoundIndex.html): compound indexes and key definitions.
- [Spring Data MongoDB — `Index` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Index.html): fluent `on`, `unique`, `sparse`, `partial`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Document`, `@Field`, `@MongoId`, and BSON types.
