# E11000 Duplicate Key Errors and Upsert Data Conflicts in MongoDB

A payment-request service may receive two HTTP requests carrying the same `requestId`. Both requests call MongoDB with `upsert: true`, intending "create if absent, update if present." Sometimes both succeed; other times one request throws an error:

```text
E11000 duplicate key error collection: shop.payment_requests
index: uk_tenant_request dup key:
{ tenantId: "tenant-a", requestId: "REQ-1001" }
```

This does not necessarily mean MongoDB "lost atomicity." It is usually proof that **the unique index protected the data from two records sharing the same key**, while the lookup logic, upsert condition, or concurrent operations were not designed around the same unique key.

The lesson **"E11000 Duplicate Key Errors and Upsert Data Conflicts in MongoDB"** belongs to the **Troubleshooting** chapter of the **Database Engine Document MongoDB** module. We will progress from index mechanics and how upserts work to error investigation in `mongosh`, the Java Sync Driver, and Spring Data MongoDB; then we will build an idempotency strategy, handle race conditions, write concurrency tests, and establish a production runbook.

After this lesson, you will be able to:

1. Read **E11000 (error code 11000)** messages to identify the collection, index, and conflicting key.
2. Distinguish unique `_id`, single-field unique, compound, partial, sparse, and collation index errors.
3. Understand why **check-then-insert** is unsafe when multiple writers run concurrently.
4. Design filters/upserts matching the **business unique key** and use `$setOnInsert` properly.
5. Understand when two concurrent upserts can **insert one and update the other**, and when E11000 still occurs.
6. Handle E11000 conditionally instead of catching all duplicates and treating them as success.
7. Implement idempotency for duplicate requests and recognize ambiguous retries after network/write concern timeouts.
8. Inspect existing data, index definitions, migration/bulk write errors, and sharded cluster specifics.
9. Write integration tests simulating concurrent upserts to guarantee the "one business key — one document" invariant.

> **Operational safety:** all collections, data, and index create/drop commands in this lesson should only be practiced in a dedicated lab database. Never drop a production unique index to "silence errors," and never run bulk data updates or `drop()` in production without change approval, backups, and a rollback plan.

## 1. What Does E11000 Mean?

**E11000 duplicate key** is an error raised by MongoDB when a write produces a **key value that collides** with another document under a **unique index** constraint.

This error can occur when:

- `insertOne()` inserts a document with a duplicate `_id`.
- `insertOne()` or `insertMany()` inserts a duplicate value on a unique secondary index.
- `updateOne()` modifies a field protected by a unique index to an already-existing value.
- `replaceOne()` or `findOneAndUpdate()` causes a key collision.
- `updateOne(..., {upsert:true})` takes the insert branch and hits a unique constraint.
- `createIndex(...,{unique:true})` cannot build the index because **existing data already contains duplicate keys**.
- A migration/import/bulk write hits multiple different unique constraints.

**E11000 does not indicate which operation ran first or which document is "correct."** Handling it requires knowing the index and the business context.

### E11000 vs. Other Errors

| Error/symptom | Cause layer | Always means duplicate? |
| --- | --- | --- |
| `E11000`, code `11000` | Unique index constraint | Yes |
| `Document failed validation` | Schema validator | No |
| `WriteConflict` | Write/transaction conflict in storage engine | No |
| `Unauthorized` | Database RBAC | No |
| `NetworkTimeout` | Communication/ambiguous outcome | No |
| `WriteConcernError` | Write acknowledgment condition unmet | No |
| `OptimisticLockingFailureException` | Version predicate mismatch in Spring Data | Not necessarily |

Do not catch all write errors and convert them into HTTP 409 "duplicate." That hides genuine network, permission, and validation errors.

## 2. Unique Indexes Are Where MongoDB Protects Keys

A MongoDB collection has a default unique index on `_id`. Additionally, applications can create unique indexes:

```javascript
db.customers.createIndex(
  { email: 1 },
  { unique: true, name: "uk_customer_email" }
);
```

If `email = "alice@example.invalid"` already exists, another insert with the same value is normally rejected:

```javascript
db.customers.insertOne({
  _id: "C1",
  email: "alice@example.invalid"
});

// The following command fails with E11000 on uk_customer_email.
db.customers.insertOne({
  _id: "C2",
  email: "alice@example.invalid"
});
```

Notably, the two documents have **different** `_id` values, yet still collide on the secondary index. Therefore, changing `_id` or generating a new ObjectId **will not fix** a duplicate `email` business key error.

### Uniqueness Is Not Inferred from Field Names

A field named `email`, `externalId`, or `requestId` is not automatically unique. The constraint exists only when an index with `unique:true` has been successfully created (or the appropriate deployment unique constraint is in place).

Check:

```javascript
db.customers.getIndexes();
```

Without a suitable unique index, two concurrent upserts can **both insert** and create two logically duplicate documents.

## 3. Reading the Structure of an E11000 Error Message

Example:

```text
MongoServerError: E11000 duplicate key error
collection: shop.customers
index: uk_customer_email
dup key: { email: "alice@example.invalid" }
```

Interpretation:

| Component | Meaning |
| --- | --- |
| `E11000` / code `11000` | Unique constraint violated |
| `collection` | Namespace where the error occurred |
| `index` | Index whose uniqueness constraint triggered the error |
| `dup key` | Conflicting index key value |
| `keyPattern` (when present) | Fields belonging to the key pattern |
| `keyValue` (when present) | Duplicate key value returned by the server |

Error details and how drivers expose `keyPattern/keyValue` vary across MongoDB/driver versions; avoid writing a parser tied to a single message string when error codes and structured details are available.

### Error Messages May Contain Sensitive Data

`dup key` sometimes includes emails, identification numbers, or business keys. Do not print raw error responses to HTTP output or public logs. For observability, log the **index name, code, correlation ID, and values masked/hashed per policy**.

### Errors on `_id_`

```text
index: _id_ dup key: { _id: ObjectId("...") }
```

This states that a document with the same `_id` already exists. Possible causes include re-inserting the same object, retrying after an ambiguous result, or duplicate source data—do not assume it is a secondary index issue.

## 4. Minimal Lab Setup Procedure

In `mongosh` connected to a practice environment:

```javascript
use e11000_lab

db.customers.drop();

db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.customers.insertOne({
  _id: "customer-1",
  tenantId: "tenant-a",
  email: "alice@example.invalid",
  status: "ACTIVE"
});
```

**`drop()` is only safe in a disposable lab database** like this example; never copy it into production. Dropping a collection also removes its indexes; recreate the indexes before running scenarios.

### Attempting to Insert a Duplicate

```javascript
db.customers.insertOne({
  _id: "customer-2",
  tenantId: "tenant-a",
  email: "alice@example.invalid",
  status: "NEW"
});
```

The second command fails with E11000 because the `(tenantId,email)` pair already exists.

However:

```javascript
db.customers.insertOne({
  _id: "customer-3",
  tenantId: "tenant-b",
  email: "alice@example.invalid",
  status: "NEW"
});
```

normally succeeds because the compound unique index enforces **uniqueness of the pair**, not that `email` must be unique across all tenants.

## 5. Compound Unique Index vs. Single-Field Unique Index

These two indexes:

```javascript
{ email: 1 }                 // unique email across the entire collection

{ tenantId: 1, email: 1 }    // unique combination of tenantId + email
```

are not equivalent.

In multi-tenant SaaS:

| tenantId | email | Unique under `{tenantId,email}` |
| --- | --- | --- |
| tenant-a | a@example.invalid | Accepted first time |
| tenant-a | a@example.invalid | Duplicate |
| tenant-b | a@example.invalid | Does not conflict with tenant-a |
| tenant-b | b@example.invalid | Not duplicate |

If a service upserts by `{email}` while the unique index is `{tenantId,email}`, the filter may match a different tenant or produce out-of-scope behavior. **Business identity and database unique keys must be designed together.**

### Index Name Does Not Determine Uniqueness

`name: "uk_tenant_email"` is only a readable label. The key pattern and options such as `unique`, `partialFilterExpression`, and `collation` define the semantics.

## 6. E11000 Also Happens on UPDATE

Suppose:

```javascript
db.customers.insertOne({
  _id: "customer-4",
  tenantId: "tenant-a",
  email: "bob@example.invalid"
});
```

Operation:

```javascript
db.customers.updateOne(
  { _id: "customer-4" },
  { $set: { email: "alice@example.invalid" } }
);
```

violates unique index `uk_tenant_email` because `tenant-a` already has Alice's email.

**E11000 is not limited to inserts/upserts.** Whenever modifying part of a unique key, check all constraints and handle business conflicts.

For a single-document update, if a constraint is violated, MongoDB will not apply the invalid write result of that operation. For bulk operations, other operations in the same batch may already have succeeded; inspect each result.

## 7. How Does Upsert Work?

`upsert` combines **update** and **insert**:

```text
updateOne(filter, update, { upsert: true })
                     |
                     v
             Matching document?
               /         \
             Yes          No
             |             |
             v             v
          Update         Insert new doc from
          one doc        filter + update
```

Example:

```javascript
db.customers.updateOne(
  {
    tenantId: "tenant-a",
    email: "carol@example.invalid"
  },
  {
    $set: { status: "ACTIVE" },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
```

If no document matches, MongoDB creates a new document from suitable equality conditions and update expressions. If one exists, the update modifies the existing document.

### Upsert Does Not Mean "Insert If ID Is Missing"

Choosing the insert vs. update branch depends on the **entire filter**, not just `_id` or a single unique field. A document may already exist for the unique business key yet **fail to match the filter** because the filter includes another condition; the upsert then attempts an insert and can hit E11000.

## 8. Reading the Result of `updateOne(..., upsert:true)`

An acknowledged result may contain:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0,
  upsertedCount: 1,
  upsertedId: ObjectId("...")
}
```

Interpretation:

| Field | Meaning |
| --- | --- |
| `acknowledged` | Write acknowledged per write concern |
| `matchedCount` | Number of matched documents (0 or 1 for `updateOne`) |
| `modifiedCount` | Number of documents actually modified |
| `upsertedCount` | Number of documents inserted by upsert |
| `upsertedId` | ID of the new document if upsert inserted |

Examples:

- `matchedCount=0, upsertedCount=1`: inserted because nothing matched.
- `matchedCount=1, upsertedCount=0`: an existing document matched; `modifiedCount` can be 0 if the update changed no values.
- Command throws E11000: **there is no normal successful update result for the failed operation**.

Do not treat `modifiedCount=0` as proof that a document is missing. It can be a no-op update on a matched document.

## 9. Race Condition of Two Concurrent Upserts

Suppose the collection does not yet contain key `REQ-1001`. Two workers run nearly simultaneously:

```javascript
db.payment_requests.updateOne(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  { $setOnInsert: { status: "RECEIVED" } },
  { upsert: true }
);
```

Conceptual timeline:

```text
Worker A                            Worker B
   |                                   |
   | query: key absent                 | query: key absent
   |                                   |
   | try insert (tenant-a, REQ-1001)   | try insert same key
   |                                   |
   | INSERT succeeds                   |
   |                                   | unique index detects
   |                                   | key already exists
   v                                   v
  One document                    May update newly created
                                  doc or throw E11000
                                  depending on server conditions
```

Key takeaways:

- **MongoDB prevents two documents violating the same unique index from coexisting.**
- However, each operation is not a "distributed lock" held from query start until the business workflow finishes.
- The loser of the race may end up **updating** or receiving a **duplicate key error**, depending on the filter, unique index, update expression, and documented server conditions.
- The application must handle **both possibilities**.

## 10. Without a Unique Index, the Race Is Even More Dangerous

Example:

```javascript
use e11000_lab

db.requests_without_unique.drop();

// No unique index created on requestId.
db.requests_without_unique.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { createdAt: new Date() } },
  { upsert: true }
);
```

If multiple concurrent clients pass the lookup phase before an insert becomes visible, they can create **multiple documents with the same `requestId`**. Sequential testing may fail to reproduce duplicates; that does not prove the design is safe.

**A unique index is the database-level invariant guard.** Writing only:

```text
if (!existsByRequestId(requestId)) {
    insert(request);
}
```

does not eliminate the race because there is a gap between `exists` and `insert`.

### Single-Document Atomicity Does Not Make an Entire Workflow Atomic

MongoDB guarantees atomicity for a single-document write per supported semantics. However, two clients concurrently concluding "does not exist yet" is a race; a unique constraint is the safeguard that prevents two documents with the same business key from being created.

## 11. When Concurrent Upserts Can Converge into an UPDATE

MongoDB documented behavior states that when multiple upserts collide on a unique index, **one operation inserts** and the other operations **can update the newly inserted document** rather than always receiving E11000, provided certain conditions are met.

Key conditions include:

1. There is a **unique index** causing the collision.
2. The operation is a **single-document update** (not `updateMany`/`multi:true`).
3. The filter is an **equality predicate** or an AND of equality predicates.
4. The set of fields in the equality predicates **matches the fields of the unique index key pattern**.
5. The update **does not modify fields belonging to the unique index key pattern**.

Conceptual example:

```javascript
db.requests.createIndex(
  { requestId: 1 },
  { unique: true, name: "uk_request_id" }
);

db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { status: "RECEIVED" } },
  { upsert: true }
);
```

When two clients race, do not assume one client is guaranteed to receive E11000. Under documented conditions, the server may allow the other operation to match and update the newly inserted document.

**Even so, do not build business logic assuming "MongoDB always auto-retries every duplicate upsert."** Convergence only has a chance under those specific supported conditions; other cases can still error.

## 12. Extra Filter Conditions Break Convergence

Unique index:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true, name: "uk_email" }
);
```

Upsert:

```javascript
db.users.updateOne(
  {
    email: "alice@example.invalid",
    status: "PENDING"
  },
  {
    $set: { lastCheckedAt: new Date() }
  },
  { upsert: true }
);
```

If a document already has `email = "alice@example.invalid"` but `status = "ACTIVE"`:

- The filter **does not match** because `status` differs.
- Upsert attempts to insert a new document with Alice's email.
- Unique index `uk_email` rejects it because the email already exists.
- The operation throws **E11000**.

Here the cause **is not two threads**. Even a single request suffices to trigger the error because **the filter contains a condition that does not match the unique identity**.

### Fixing by Invariant

If the intent is to update an existing account only when `status` is `PENDING`, use a **conditional update without upsert**:

```javascript
db.users.updateOne(
  {
    email: "alice@example.invalid",
    status: "PENDING"
  },
  { $set: { lastCheckedAt: new Date() } }
);
```

If nothing matches, the application distinguishes between account not found, account status changed, or conflict per business policy. Do not use upsert to mask "record exists but is in another state."

## 13. Unique Index and Filter Must Express the Same Identity

Suppose the business identity is the pair:

```text
(tenantId, externalOrderId)
```

Create the unique index:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uk_tenant_external_order" }
);
```

And use the filter:

```javascript
{
  tenantId: "tenant-a",
  externalOrderId: "EXT-1001"
}
```

Avoid:

```javascript
{
  externalOrderId: "EXT-1001"
}
```

because it lacks tenant scope.

Also avoid adding `status`, `updatedAt`, or range predicates to the filter **when the intent is "find the exact business entity by unique identity"**; extra conditions can prevent matching an existing document and cause the upsert to attempt a duplicate insert.

**Note:** matching the filter to the unique index is essential, but it does not replace checking business invariants or potential errors from **other unique indexes**.

## 14. Difference Between `$setOnInsert` and `$set`

Example:

```javascript
db.payment_requests.updateOne(
  {
    tenantId: "tenant-a",
    requestId: "REQ-1001"
  },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      payloadHash: "fake-hash-001"
    },
    $set: {
      lastSeenAt: new Date()
    }
  },
  { upsert: true }
);
```

| Operator | On insert by upsert | On matching existing document |
| --- | --- | --- |
| `$setOnInsert` | Sets fields | Not applied |
| `$set` | Sets fields | Sets fields |
| `$inc` | Increments numeric field per rules | Increments numeric field |
| `$unset` | Removes field per rules | Removes field |

In the example:

- `status` and `createdAt` are set only upon creation.
- `lastSeenAt` is updated on both insert and match.
- `payloadHash` preserves the original source content; if a subsequent request uses the **same `requestId` with a different payload**, the application must detect and return a conflict rather than silently overwriting it.

### Do Not Write the Same Path in Conflicting Modifiers

Bad example:

```javascript
{
  $set: { status: "ACTIVE" },
  $setOnInsert: { status: "RECEIVED" }
}
```

Two operators target the same path `status`; this causes **conflicting update operators**, not E11000. Design updates cleanly: each path should be handled by one operator within the same operation.

## 15. Upsert Is Not a "Smart Merge"

Suppose the first request is:

```json
{
  "requestId": "REQ-1001",
  "amount": "100.00",
  "currency": "USD"
}
```

A subsequent request has the same ID but:

```json
{
  "requestId": "REQ-1001",
  "amount": "900.00",
  "currency": "USD"
}
```

The two payloads **differ**, despite having the same `requestId`. If the service runs:

```javascript
db.payment_requests.updateOne(
  { requestId: "REQ-1001" },
  { $set: { amount: NumberDecimal("900.00") } },
  { upsert: true }
);
```

then the second command **overwrites the first request's amount**. It does not enforce business idempotency.

A safe idempotency design typically requires:

1. **Idempotency key** agreed upon by client/server.
2. **Unique index** at the right scope (e.g., `tenant + requestId`).
3. **Canonical fingerprint/hash** of the business-significant payload.
4. Rule for same key / same payload: return the same result or existing state.
5. Rule for same key / different payload: **report a conflict**, do not overwrite.
6. Protect side effects (payments/emails/events) from executing repeatedly.

A unique index only knows **whether keys collide**, not whether two payloads are equivalent.

## 16. Designing a Collection for Idempotent Requests

Example:

```javascript
use e11000_lab

db.payment_requests.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_tenant_request"
  }
);
```

Document:

```javascript
{
  _id: ObjectId("65f000000000000000000101"),
  tenantId: "tenant-a",
  requestId: "REQ-1001",
  payloadHash: "sha256-of-canonical-request",
  amount: NumberDecimal("125000.00"),
  currency: "VND",
  status: "RECEIVED",
  createdAt: ISODate("2026-11-14T08:00:00Z"),
  resultReference: null
}
```

`payloadHash` is illustrative, not a real computed hash. In production, define canonicalization clearly (JSON field ordering, numeric types, currency, optional fields) so logically identical payloads never yield different hashes due to serialization differences.

### Create-Only Upsert

```javascript
db.payment_requests.updateOne(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  {
    $setOnInsert: {
      payloadHash: "sha256-of-canonical-request",
      amount: NumberDecimal("125000.00"),
      currency: "VND",
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

If the record already exists, `$setOnInsert` does not overwrite anything. After the write, the application reads the record by **unique key** and compares `payloadHash`/result/status. For a different payload, it returns a conflict.

### Business Work Does Not Need to Run Inside the Upsert Transaction

The idempotent record acts only as the **request-registration lock**. Executing payments, sending emails, or publishing outbox events still requires a dedicated state machine/claim/transaction strategy. Never let two workers both call a payment provider just because both read `status:"RECEIVED"`.

## 17. When One Insert and One E11000 Is Expected Behavior

If two requests use the **same business key with different payloads**, a unique index detects that two records cannot be created.

A handling strategy:

```text
Upsert/insert attempt
      |
      +--> Success
      |      |
      |      v
      |   Read/return stored result
      |
      +--> E11000
             |
             v
          Identify index and key
             |
             v
          Read by business unique key
             |
             +--> Existing payload equivalent
             |      -> apply idempotency policy
             |
             +--> Existing payload differs
             |      -> return conflict
             |
             +--> Not found / different index
                    -> preserve error, investigate / controlled retry
```

**Do not turn every E11000 into success.** A write may have collided on `_id` or another unique index, so "reading by `requestId`" would not find the conflicting record—or the record may exist with a different payload.

## 18. Why Pre-Check Followed by Insert Still Races

Anti-pattern:

```java
if (!repository.existsByRequestId(requestId)) {
    repository.insert(newRequest);
}
```

Timeline:

```text
T1: exists -> false
T2: exists -> false
T1: insert -> success
T2: insert -> E11000 (if unique index exists)
```

These two operations cannot be made atomic using Java `synchronized` when the application runs across multiple instances. A unique index plus a single atomic upsert/CAS, or insert-only with conditional duplicate handling, is far more appropriate.

### Where Is a Pre-Check Still Useful?

It can help return early feedback to the UI, but it is **not the final guard**. A database constraint must still enforce uniqueness on write. Never use a pre-check as a substitute for a unique index.

## 19. When to Use `insertOne()` Instead of Upsert

If the business semantics are **"create only; report conflict if already exists,"** `insertOne()` with a unique key can be simpler than upsert.

Example:

```javascript
db.external_events.insertOne({
  _id: "tenant-a:EVENT-1001",
  tenantId: "tenant-a",
  eventId: "EVENT-1001",
  payloadHash: "hash-001",
  receivedAt: new Date()
});
```

If the same `_id` arrives again, the server returns E11000. The application reads the existing event, compares contents, and decides between idempotent duplicate and conflict.

For create-only semantics, **insert + catch duplicate** often expresses intent more clearly than an upsert with `$set` that risks overwriting.

### Compound String `_id` Still Needs Rules

If choosing `tenantId + ":" + eventId` as `_id`, establish canonicalization and prevent collisions from delimiters/normalization. A compound unique index across two fields can be easier to manage; choose based on schema and query requirements.

## 20. E11000 Caused by a Unique Index on `null` or Missing Fields

A MongoDB **single-field** unique index has an important rule: for a regular index, a document missing the field and a document with field `null` both generate a `null` index key. Since uniqueness allows only one index entry with key `null`, inserting a second document missing the field or having `null` fails with E11000.

Lab example:

```javascript
db.contacts.drop();

db.contacts.createIndex(
  { email: 1 },
  { unique: true, name: "uk_email" }
);

db.contacts.insertOne({ _id: 1, name: "A" });

// Duplicate null key for the single-field unique index:
db.contacts.insertOne({ _id: 2, name: "B" });
```

No email was provided at all, yet it still collides due to index semantics.

### Difference with Compound Unique Indexes

With index `{tenantId:1, email:1}`, uniqueness applies to the **pair of values**. Null/missing combinations must be evaluated across the entire key pattern. Do not mechanically apply the "only one null in the entire collection" rule to every compound index.

### Do Not Fix by Setting `email = ""`

The empty string `""` is also a value that can collide, and it distorts the semantics of "no email provided." Choose a partial index, sparse index, or an appropriate data model instead.

## 21. Partial Unique Index for Optional Fields

If you want `email` to be unique **only when the field is a BSON String**:

```javascript
db.contacts.drop();

db.contacts.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uk_email_when_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Meaning:

- Documents missing `email` are not indexed under this filter.
- Documents with `email: null` do not satisfy the string condition.
- Documents with a string `email` must be unique among indexed documents.

A multi-tenant example:

```javascript
db.contacts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    name: "uk_tenant_email_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

**This is a deliberate policy choice**: an `email` field with a wrong BSON type like number/object will fall outside the unique partial index. Use schema validation to ensure only permitted types appear.

### Partial Indexes and the Query Planner

Queries intending to use a partial index must include matching predicates so they do not miss documents outside the subset. MongoDB still enforces uniqueness for documents matching the partial filter, though query performance also depends on predicates/collation/index selection.

## 22. Sparse Unique Index vs. Partial Unique Index

A sparse unique index skips documents **missing the field** per sparse semantics, but it does not necessarily skip documents where the field is explicitly present as `null`.

Example:

```javascript
db.customers.createIndex(
  { alternateEmail: 1 },
  { unique: true, sparse: true }
);
```

Compare:

| State | Regular single-field unique | Sparse unique | Partial `$type:"string"` |
| --- | --- | --- | --- |
| Missing field | Generates null key | Typically not indexed | Not indexed |
| Field = null | Generates null key | Field present; may be indexed | Not indexed |
| Field = string | Unique | Unique | Unique |

Do not replace `partialFilterExpression` with `sparse:true` without considering documents that have explicit BSON Null. MongoDB restricts certain index option combinations; check the manual for your server version.

## 23. Collation and Case-Insensitive Duplicates

Suppose:

```text
Alice@Example.invalid
alice@example.invalid
```

If the index uses a suitable case-insensitive collation, these two values are treated as duplicates:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    name: "uk_email_case_insensitive",
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
);
```

A second insert will throw E11000 even though the two strings differ in casing.

### Upsert Filters Must Also Match Collation

If the unique index is case-insensitive while the upsert filter **uses simple/default collation**, the query may fail to match the existing document, attempt an insert, and hit the unique index.

Example:

```javascript
db.users.updateOne(
  { email: "alice@example.invalid" },
  { $setOnInsert: { createdAt: new Date() } },
  {
    upsert: true,
    collation: { locale: "en", strength: 2 }
  }
);
```

Query collation must be chosen according to business identity/index strategy; do not blindly add collation everywhere expecting it to cure all E11000 errors.

### Application-Level Canonicalization

In addition to collation, the application can store a `normalizedEmail` per defined rules and place a unique index on that field. Unicode normalization, casing, whitespace, and domain-specific email rules must be tested. Never assume every email provider treats dots, plus signs, or local parts identically.

## 24. Multikey Unique Index Nuances

When an index covers an array field, MongoDB can generate multiple index keys from array elements. A unique constraint prevents **different documents** from generating the same index key. Duplicate elements within the **same document** follow specific semantics: a unique multikey index is not simply a validator saying "all elements in the array must be distinct."

Example:

```javascript
db.members.createIndex(
  { emails: 1 },
  { unique: true }
);
```

Do not assume this index will definitely reject:

```javascript
{ _id: 1, emails: ["a@example.invalid", "a@example.invalid"] }
```

just because an array contains an internal duplicate. The purpose of a unique index differs from a JSON Schema validator checking intra-array element uniqueness.

If a business rule requires a document's array to contain no duplicate elements, enforce it at the schema/application layer or use appropriate update operators/conditions.

## 25. One Document with Multiple Unique Constraints

Suppose:

```javascript
db.users.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);

db.users.createIndex(
  { tenantId: 1, externalUserId: 1 },
  { unique: true, name: "uk_tenant_external_user" }
);
```

An upsert filtering on `(tenantId,externalUserId)` may match the right business user, yet the update tries to assign an `email` already belonging to another user → E11000 on **`uk_tenant_email`**.

Therefore:

- A filter matching the right unique key **does not guarantee no error from another index**.
- Never catch E11000, read solely by `externalUserId`, and always return success.
- You must identify **which index failed** and apply the rule for resolving the corresponding business conflict.

A system with multiple external identifiers must maintain consistency among them per policy, potentially requiring transactions or a dedicated workflow when multiple documents are affected.

## 26. Sharded Clusters and Unique Constraints

On sharded collections, enforcing unique indexes across shards follows **rules tied to the shard key and unique index key pattern**. Typically, a unique index on a sharded collection must satisfy shard-key prefix requirements per server version documentation; `_id` and hashed indexes have specific nuances.

Example:

```text
Shard key: { tenantId: 1 }

Application wants uniqueness on:
  (tenantId, requestId)
```

This design requires evaluating routing and sharded collection unique index rules. Never assume global cluster-wide uniqueness of `requestId` is enforced just because a local index exists on each shard.

### Sharded Collection Upserts Have Version-Specific Behavior

MongoDB 8.0 changed certain requirements for `upsert:true` on sharded collections—for example, no longer always requiring the filter to include the full shard key. However:

- Routing conditions and shard-key modifications still carry restrictions.
- Unique enforcement still depends on index support and topology.
- The business identity filter must still be accurate, regardless of whether the server allows the operation to run.

If E11000 occurs only in a sharded deployment or during topology migration, record the **server version, shard key, unique index definitions, and routing through `mongos`**, rather than looking only at a Java method.

## 27. Errors When Creating a Unique Index on Already-Duplicated Data

A migration:

```javascript
db.customers.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, name: "uk_tenant_email" }
);
```

will fail if the collection already contains duplicates. MongoDB will not automatically pick which document to delete.

### Finding Duplicates with Aggregation

```javascript
db.customers.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$email"
      },
      count: { $sum: 1 },
      sampleIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 50 }
]);
```

**Only use this illustrative pipeline on an appropriate dataset**: `$push` on all IDs of a massive group can cause the aggregation document to exceed size limits. In production, design batch/top-N reports, bound memory usage, and export key lists securely.

### Why Not Delete Duplicate Records Immediately?

Two records sharing the same email may have:

- Different orders/payments/references.
- Different ownership or tenants due to dirty data.
- Different timestamps where the newer record is not guaranteed to be canonical.
- Sensitive payloads that must not be merged automatically.

Establish the source of truth, cross-collection references, retention/deletion policy, and audit trail. Only after cleanup should you build the unique index and test concurrent writes.

## 28. Distinguishing E11000 from BSON Type Schema Errors

Example:

```javascript
{ _id: "A", externalId: "1001" }
{ _id: "B", externalId: NumberLong("1001") }
```

These two values differ in BSON type (string vs. numeric). A unique index treats them as distinct keys, yet the application may treat them as the same external ID when converting to strings. This is a **logical duplicate** that a BSON-typed unique index may not prevent.

Conversely, MongoDB applies shared comparison rules across certain numeric BSON types; do not rely on Int32/Int64/Double being different Java classes to assume they will always be indexed as distinct unique keys.

### Lessons

1. Standardize BSON types before creating unique indexes.
2. Synchronize schemas across Java, Spring Data, APIs, and migration scripts.
3. Do not mix `ObjectId` and hex strings for the same identity field.
4. If using UUIDs, standardize BSON binary subtype and representation.
5. If using email/phone, pick an explicit normalization rule.

A unique index enforces uniqueness strictly per **actual MongoDB key semantics**, not every application-level notion of equivalence.

## 29. Java Sync Driver: Catching the Right E11000 Type

Suppose collection:

```java
MongoCollection<Document> requests =
    database.getCollection("payment_requests");
```

Java Sync Driver:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;

Document doc = new Document("tenantId", "tenant-a")
    .append("requestId", "REQ-1001")
    .append("payloadHash", "hash-001");

try {
    InsertOneResult result = requests.insertOne(doc);
    System.out.println(result.getInsertedId());
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        // Duplicate unique key: classify the key and handle business logic.
        // Do not assume success.
        throw ex;
    }
    throw ex;
}
```

Different operations throw different exceptions depending on the driver/server/API:

- `MongoWriteException` for many single-write failures.
- `MongoBulkWriteException` for bulk writes.
- `MongoCommandException` for certain command errors (e.g., index management).
- `MongoException` for the general error family.

Do not catch `Exception` and search for the substring `"E11000"` when you can inspect **error code 11000** via the structured driver API.

### Exception Types Can Be Translated by Spring

When using `MongoTemplate` or repositories, Spring Data applies exception translation. You may receive `org.springframework.dao.DuplicateKeyException` instead of the raw driver exception. Do not reuse the same `catch (MongoWriteException)` across every framework code path.

## 30. Java Sync Driver: Practical Idempotent Upsert

Example of a service trying to "register a request once," using unique index `{tenantId:1,requestId:1}`:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;

public final class RequestRegistration {

    public static Document register(
            MongoCollection<Document> collection,
            String tenantId,
            String requestId,
            String payloadHash) {

        var filter = Filters.and(
            Filters.eq("tenantId", tenantId),
            Filters.eq("requestId", requestId)
        );

        var update = Updates.combine(
            Updates.setOnInsert("payloadHash", payloadHash),
            Updates.setOnInsert("createdAt", new Date()),
            Updates.setOnInsert("status", "RECEIVED")
        );

        try {
            UpdateResult result = collection.updateOne(
                filter, update,
                new UpdateOptions().upsert(true)
            );
            // result.getUpsertedId() != null if just inserted.
        } catch (MongoWriteException ex) {
            if (ex.getError().getCode() != 11000) {
                throw ex;
            }

            // Could be a duplicate request or another unique index.
            // Re-read and compare contents before concluding.
            Document existing = collection.find(filter).first();
            if (existing == null ||
                !Objects.equals(
                    existing.getString("payloadHash"), payloadHash)) {
                throw ex;
            }

            return existing;
        }

        Document existing = collection.find(filter).first();
        if (existing == null) {
            throw new IllegalStateException(
                "Request not found after upsert");
        }

        if (!Objects.equals(
                existing.getString("payloadHash"), payloadHash)) {
            throw new IllegalStateException(
                "Same requestId with different payload");
        }

        return existing;
    }
}
```

Scope notes for this example:

- The client needs an **acknowledged write concern** to observe the result.
- The unique index must already be created before running.
- `tenantId/requestId` inputs must be properly validated and normalized.
- If the duplicate came from **another** unique index, this snippet can only treat it as idempotent if the existing document under the filter has an equivalent payload and policy allows; production code should classify the **actual index/key** instead of relying solely on a re-read.
- Between upsert and read, another worker may delete/modify the document; the service needs clear retention/state transition design.
- If the read returns `status:"RECEIVED"`, that does not mean **the payment has completed**.
- Production code needs a dedicated exception for **same key / different payload**, rather than using `IllegalStateException` as a public API contract.

### Why Doesn't This Code Execute the Payment Directly?

This is only the **request registration** step. If two workers both call the payment provider as soon as this method returns a `Document`, duplicate processing will occur. You also need an **atomic claim/state transition**, an outbox, or a dedicated transaction/workflow.

## 31. Idempotent Upsert vs. "Update on Every Arrival"

Compare:

```javascript
// Branch A: preserves original data.
db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $setOnInsert: { payloadHash: "hash-001" } },
  { upsert: true }
);
```

and:

```javascript
// Branch B: later request overwrites.
db.requests.updateOne(
  { requestId: "REQ-1001" },
  { $set: { payloadHash: "hash-002" } },
  { upsert: true }
);
```

Branch A preserves the initial payload. Branch B mutates the payload when the record already exists.

With idempotency keys, a request carrying the same key but different content should normally not overwrite original data. This does not mean state can never be updated; **status/result** can transition according to a controlled state machine, and those updates should carry explicit preconditions.

## 32. Resolving Concurrency via State Machine

Example states:

```text
RECEIVED
   |
   v
PROCESSING
   |
   +--> SUCCEEDED
   |
   +--> FAILED
```

A worker must **claim** the task using a conditional update:

```javascript
db.payment_requests.findOneAndUpdate(
  {
    tenantId: "tenant-a",
    requestId: "REQ-1001",
    status: "RECEIVED"
  },
  {
    $set: {
      status: "PROCESSING",
      workerId: "worker-a",
      claimedAt: new Date()
    }
  },
  { returnDocument: "after" }
);
```

When multiple workers race to claim, only the operation whose status predicate matches updates first via single-document atomicity.

**Do not enable `upsert:true` on this claim operation**. If the request already exists in `PROCESSING` or `SUCCEEDED`, an upsert trying to insert can hit E11000; the bug is using upsert where the state transition should strictly be a conditional update.

### Claiming Once Does Not Guarantee Exactly-Once Side Effects

If a worker crashes after calling the payment provider but before writing `SUCCEEDED`, another worker may need to retry; you cannot infer from MongoDB status alone that payment never occurred. Use provider-side idempotency keys, recovery procedures, and transactional outboxes where appropriate.

## 33. `findOneAndUpdate` with Upsert and E11000

`findOneAndUpdate()` can find/insert and return the document based on options. Example:

```javascript
db.requests.findOneAndUpdate(
  { requestId: "REQ-1001" },
  { $setOnInsert: { createdAt: new Date(), state: "NEW" } },
  { upsert: true, returnDocument: "after" }
);
```

If concurrent upserts collide on a unique index, resolution semantics mirror the upsert mechanism above: one writer inserts, while another updates or hits E11000 depending on conditions.

**`returnDocument:"after"` does not handle duplicates automatically**. When the command throws E11000, the client does not normally receive a new document as if it succeeded; code must catch, re-read, compare payloads, and classify.

### When You Only Want an Existing Record

If an operation should only update an already-existing record, use `upsert:false` and check for null/no-match. Do not enable upsert out of habit on every `findOneAndUpdate()`.

## 34. Spring Data MongoDB: Unique Index Mapping

In Spring Data, a unique index can be declared via annotations:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "payment_requests")
@CompoundIndex(
    name = "uk_tenant_request",
    def = "{'tenantId': 1, 'requestId': 1}",
    unique = true
)
public class PaymentRequest {
    @Id
    private String id;
    private String tenantId;
    private String requestId;
    private String payloadHash;

    public PaymentRequest() {}
    // Additional getters/setters or appropriate mapping declared here.
}
```

**An annotation is not proof that the index exists in production.** Spring Data has configuration flags for auto-index-creation and its own migration/index lifecycle; many applications disable auto-index-creation to control schema changes. Always verify the actual index:

```javascript
db.payment_requests.getIndexes();
```

If code deploys with the annotation while the unique index was never created, concurrent upserts can still produce duplicates.

### Index Migration

To create an index via `MongoTemplate`:

```java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("requestId", Sort.Direction.ASC)
    .unique()
    .named("uk_tenant_request");

template.indexOps("payment_requests").ensureIndex(index);
```

This command modifies schema/indexes. In production, execute it under migration policy after verifying existing data has no duplicates and sufficient privileges/resources exist.

## 35. Spring Data: Catching `DuplicateKeyException`

Spring typically translates MongoDB duplicate key errors to:

```java
import org.springframework.dao.DuplicateKeyException;
```

Example:

```java
try {
    paymentRequestRepository.insert(entity);
} catch (DuplicateKeyException ex) {
    // Confirm an existing record exists by business key,
    // compare payloadHash/status, and return the appropriate result.
    throw ex;
}
```

**Do not assume every `DuplicateKeyException` is the same request**, because it may collide on `_id` or another unique index. When you need to identify the index, inspect the root cause/structured error or sanitized logs, and compare state by business key under an explicit policy.

### `Repository.save` Is Not "Upsert by Email"

`save(entity)` typically relies on entity identity such as `_id` and mapping lifecycle. It does not automatically look up by business keys like `email` or `requestId` simply because that field has a unique index.

Two entities with different `_id` values but the same `requestId` will cause `save()` on the second entity to hit E11000; Spring does not automatically merge them into one object.

## 36. Spring Data: `MongoTemplate.upsert()`

Example:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("requestId").is("REQ-1001")
);

Update update = new Update()
    .setOnInsert("payloadHash", "hash-001")
    .setOnInsert("status", "RECEIVED")
    .setOnInsert("createdAt", new java.util.Date());

UpdateResult result = template.upsert(
    query, update, PaymentRequest.class);
```

This performs a MongoDB-level upsert using the filter expressed via Spring Data. If the unique index and query are inconsistent, E11000 will still occur.

### Be Careful with `@Version`

If an entity uses `@Version` to prevent lost updates, do not assume every `template.upsert()` or raw update enforces optimistic locking the way `repository.save(entity)` does. Some Spring Data update operations may increment the version field automatically, but **incrementing version is not the same as having an `expectedVersion` predicate**.

When CAS is needed, place `expectedVersion`/business conditions in the **same update query**. When registering a new idempotent request, clearly separate the create-only step from state-transition steps.

## 37. What Should an HTTP API Return on Duplicates?

There is no single HTTP status right for every E11000. It must reflect business semantics.

| Scenario | Typical API handling to consider |
| --- | --- |
| POST creating a new user, email belongs to someone else | `409 Conflict` |
| Idempotent POST, same key, equivalent payload, result exists | Return the prior result per contract |
| Same idempotency key, different payload | `409 Conflict` or equivalent error |
| Status update violating lifecycle | `409 Conflict` or domain error |
| E11000 from a different index unrelated to request key | Do not treat as idempotent success; investigate |
| MongoDB authentication/network failure | Infrastructure error, not a business duplicate |
| Input missing required field | Validation error, typically `400` or `422` per contract |

**Do not return raw `dup key: { email: ... }` to the client** if it could leak PII or reveal the existence of another person's account. Use a neutral message per security policy.

## 38. Retryable Writes, Timeouts, and E11000

A request may:

1. Be successfully applied by the server.
2. Lose the client connection **before receiving the acknowledgment**.
3. Be retried by the client/app.
4. Hit a duplicate key error on the retry because the record already exists.

E11000 in this scenario **does not prove the first attempt failed**. However, it also does not prove the first attempt succeeded **with the same payload**.

### Distinguishing Driver-Level vs. Application-Level Retries

MongoDB drivers support **retryable writes** under eligible deployment/operation conditions. This does not make every business operation idempotent, nor does it guarantee all failures are retried.

Application retries after an ambiguous outcome must:

- Keep the same business idempotency key.
- Re-read the result by unique key.
- Compare the canonical payload/fingerprint.
- Return a response based on processing/result state.
- Never generate a new ObjectId/`requestId` on retry when the intent is the same request.
- Never invoke external payments/emails twice without idempotency protection.

### WriteConcern Timeout Is Not a Duplicate

`wtimeout` describes the write acknowledgment condition; the operation may already have been applied. After a timeout, **do not immediately create a new document with a new key**. Reconcile by stable identity and monitor replication/commit status appropriately.

## 39. Can E11000 Occur Inside a Transaction?

Yes. A transaction can insert/update documents that violate a unique index and receive a duplicate key failure.

Transactions provide atomicity across their participating operations per supported semantics; they **do not allow bypassing unique constraints**.

Example flow:

```text
Transaction:
  insert payment_requests(key=REQ-1001)
  update orders(status=PAID)

If insert violates unique index:
  Transaction cannot be treated as a normal success.
  Must handle error/abort/retry per contract.
```

### Do Not Blindly Retry the Entire Transaction

`TransientTransactionError` and `UnknownTransactionCommitResult` have dedicated retry semantics. E11000 is a **business/data constraint violation**; never lump every E11000 into a transient retry loop.

If a server version exhibits different upsert retry behavior inside vs. outside transactions, consult the corresponding release notes. In particular, never invoke non-idempotent external side effects inside a transaction callback that may be retried.

## 40. Bulk Writes: One Error Does Not Roll Back the Entire Batch

Suppose:

```javascript
db.events.insertMany(
  [
    { _id: "E1", externalId: "A" },
    { _id: "E2", externalId: "A" },
    { _id: "E3", externalId: "B" }
  ],
  { ordered: false }
);
```

If there is a unique index on `externalId`:

- One operation creating key `A` succeeds.
- The other operation with `A` fails with E11000.
- With `ordered:false`, other operations can still execute; this is **not a batch-wide atomic transaction**.

### Ordered vs. Unordered

| Bulk mode | When encountering a write error |
| --- | --- |
| `ordered:true` | Typically stops processing subsequent operations in order |
| `ordered:false` | Can continue remaining operations; completion order is not guaranteed |

Do not look only at error count/inserted count and assume all intended records were handled. Inspect **`writeErrors` with their batch index**, successes, `writeConcernErrors`, and reconcile business keys.

### Java Driver

A bulk operation can throw `MongoBulkWriteException`, providing a list of write errors where each error includes a code and index to identify which operation failed.

Do not parse a long stack trace and delete the entire batch/collection to retry. For financial data or events, each operation needs its own idempotency key and retry policy.

## 41. Inspecting Indexes and Data Without Altering Production

**Read-only** commands:

```javascript
const target = db.getSiblingDB("shop");

target.payment_requests.getIndexes();

target.payment_requests.find(
  { tenantId: "tenant-a", requestId: "REQ-1001" },
  {
    _id: 1,
    tenantId: 1,
    requestId: 1,
    payloadHash: 1,
    status: 1
  }
);
```

Verify:

1. Does the index reported in E11000 exist?
2. What are its key pattern, `unique`, `collation`, `partialFilterExpression`, and `sparse` settings?
3. Which fields/types/normalization does the query actually use?
4. Does the existing document share the same business identity, or did it hit a different index?
5. Are there `null`/missing keys or fields written with the wrong BSON type?
6. Did server/driver versions or topology change compared to prior incidents?

**You do not need to drop a unique index to investigate.** Removing the constraint can let the application write further duplicates and make cleanup harder.

## 42. Investigating Null/Missing Data and Mixed Types

When an error reports `dup key: { email: null }`, inspect:

```javascript
db.getSiblingDB("shop").customers.find(
  { email: null },
  { _id: 1, email: 1, tenantId: 1 }
).limit(50);
```

The query `{email:null}` matches both **BSON Null and missing fields**. To distinguish them:

```javascript
// Only fields with BSON Null:
db.customers.find({ email: { $type: 10 } });

// Only missing fields:
db.customers.find({ email: { $exists: false } });
```

Check BSON types:

```javascript
db.customers.aggregate([
  {
    $project: {
      emailType: { $type: "$email" },
      tenantType: { $type: "$tenantId" }
    }
  },
  { $limit: 50 }
]);
```

If a unique key was designed for strings while data contains null/objects/arrays, address schema validation/migration rather than only changing upsert code.

## 43. Upsert Errors Caused by Status Conditions vs. Version Conflicts

A document:

```javascript
{
  _id: "order-1001",
  externalId: "EXT-1001",
  status: "SHIPPED",
  version: NumberLong("8")
}
```

The service wants to update:

```javascript
db.orders.updateOne(
  {
    externalId: "EXT-1001",
    status: "NEW",
    version: NumberLong("7")
  },
  { $set: { status: "CANCELLED" } },
  { upsert: true }
);
```

Because the document is already `SHIPPED`/version 8:

- The filter does not match.
- Upsert tries to insert a new document with `externalId:"EXT-1001"`.
- The unique index on `externalId` throws E11000.

Yet the business meaning is a **stale request or invalid state transition**, not "create another order."

### Fixing the Semantics

Use a **conditional update without upsert**:

```javascript
db.orders.updateOne(
  {
    externalId: "EXT-1001",
    status: "NEW",
    version: NumberLong("7")
  },
  {
    $set: { status: "CANCELLED" },
    $inc: { version: NumberLong("1") }
  }
);
```

If `matchedCount=0`, the API returns conflict/not-found per policy. Do not use upsert to "auto-repair" a stale version.

**Rule:** upsert fits "allowed to create if the business identity does not yet exist." State transitions on an entity that must already exist should normally **not use upsert**.

## 44. Never Drop a Unique Index to "Fix" E11000

Anti-pattern:

```javascript
// DO NOT run in production as a 'quick fix' for duplicates:
db.payment_requests.dropIndex("uk_tenant_request");
```

This removes the data safeguard:

- Two requests with the same key can create two payment intents.
- Downstream business tables can accumulate duplicates that are hard to reconcile.
- Rebuilding the index later may fail due to new duplicates.
- Other components relying on the unique invariant may break.

Better approach:

1. Record the full error and index definition.
2. Classify which duplicate key occurred.
3. Inspect request/filter/update semantics.
4. Decide whether to keep the existing record, return conflict, or migrate.
5. Update application code and test.
6. Only change the index definition when the **business requirement genuinely changes** and a rollout/cleanup plan is in place.

## 45. Step-by-Step E11000 Investigation Runbook

### Step A — Isolate the Error

Collect:

```text
Incident ID:
Timestamp:
Environment / cluster:
Namespace:
Operation: insertOne/updateOne/findOneAndUpdate/bulk/index build
Error code: 11000
Index name:
Key pattern:
Sanitized key value:
Server version/topology:
Driver/framework version:
Correlation ID:
Business request identity:
```

Do not paste raw credentials, PII, or full request bodies containing secrets into tickets.

### Step B — Classify the Operation

```text
E11000
  |
  +--> INSERT: key already exists? ambiguous retry?
  |
  +--> UPDATE: field in unique index changed to colliding key?
  |
  +--> UPSERT: filter missed even though business key exists?
  |            race across multiple writers?
  |            filter/index equality mismatch?
  |
  +--> INDEX BUILD: existing data already has duplicates?
  |
  +--> BULK: which operations failed, which succeeded?
```

### Step C — Inspect the Index

```javascript
db.getSiblingDB("shop")
  .payment_requests.getIndexes();
```

Inspect `unique`, `key`, `name`, `partialFilterExpression`, `sparse`, `collation`, and topology. Do not judge solely by index name.

### Step D — Reconcile the Existing Record

Query by the **business unique key**; when needed, query by the error's `keyValue` using a sufficiently privileged user in an approved environment. Evaluate payload hash, status, and related links.

### Step E — Determine Root Cause

Common categories:

1. Valid repeated request (retry/idempotency).
2. Concurrent upserts on the unique key.
3. Upsert filter includes `status`/`version`/range causing no-match.
4. Unique index/key scope out of sync with the tenant model.
5. Unique index on optional field with `null`/missing values.
6. Collation/normalization mismatch between query and index.
7. Code updates a unique field to an already-used value.
8. Index migration encounters pre-existing duplicate data.
9. Mixed BSON types or schema drift.
10. Ambiguous outcome after timeout/network/failover.

### Step F — Safe Recovery

- Do not delete/replace an existing document without confirmation from the business owner.
- For same key / same payload, use idempotent response/state reconciliation.
- For same key / different payload, return conflict and record appropriate audit logs.
- For migration duplicates, map references, clean up per plan, and build the index in a controlled manner.
- For systemic errors, apply bounded retry/backoff and idempotency.
- When changing upsert logic, validate in staging/load tests before production.

### Step G — Post-Fix Verification

- Unique index remains active.
- Concurrent requests do not create two documents with the same business key.
- Duplicate requests with the same payload do not execute duplicate side effects.
- Duplicate requests with different payloads are rejected.
- No validation/network/authorization errors are masked as duplicates.
- Error metrics, latency, and write throughput remain stable.

## 46. Concurrency Testing with Two Workers

An integration test should use **a real MongoDB instance with a real unique index**, not just a mocked repository.

Example structure:

```text
Setup:
  create unique index (tenantId,requestId)
  delete fixture REQ-RACE-01 in test DB

Thread A:
  await barrier
  upsert REQ-RACE-01

Thread B:
  await barrier
  upsert REQ-RACE-01

Assertions:
  countDocuments({tenantId,requestId}) == 1
  stored payloadHash matches policy
  no unwanted duplicate side effects
  each outcome is in allowed set (insert/update/handled E11000)
```

### Why Not Assert "Definitely One E11000"?

MongoDB may allow the second operation to **update the newly inserted record** when upsert and unique index conditions align. Tests should not depend on a single race ordering or a specific error type when the business invariant is simply **one record and valid responses**.

### Stable Test That Intentionally Produces E11000

To test error mapping, use a **sequential** test inserting two documents with the same unique key into a lab collection. That is far more deterministic than a random race test for proving exception translation.

### Concurrent Worker Test Details

When using Java `CountDownLatch` or `CyclicBarrier`:

- Both tasks hold client/collection handles safely per driver contract.
- Each task has its own request context.
- Share a start barrier without assuming thread scheduling order.
- Use bounded timeouts so tests cannot hang.
- Read the final count with an acknowledged read of appropriate consistency.
- Clean up test documents after both tasks finish.

## 47. Essential Upsert Test Matrix

| Case | Condition | Expected |
| --- | --- | --- |
| UPSERT-01 | Key absent, single request | Inserts one record |
| UPSERT-02 | Key present, identical payload | Preserves idempotent state, no overwrite |
| UPSERT-03 | Key present, different payload | Conflict, existing payload unchanged |
| UPSERT-04 | Two concurrent requests, same key | Only one final record |
| UPSERT-05 | Two requests, different tenants, same `requestId` | Separate record per tenant per policy |
| UPSERT-06 | Filter adds `status` causing no-match | Does not create wrong record; handles conflict |
| UPSERT-07 | Optional field `null`/missing | Unique/partial policy enforced properly |
| UPSERT-08 | Email with differing case | Follows chosen collation/normalization |
| UPSERT-09 | Duplicate from another secondary index | Not confused with idempotent request |
| UPSERT-10 | Timeout after write | Retries with same key, reconciles outcome |
| UPSERT-11 | Bulk with one duplicate | Reconciles partial successes |
| UPSERT-12 | Unique index not yet deployed | Test fails; duplicates rejected |
| UPSERT-13 | Legacy mixed BSON types | Planned migration/validation |
| UPSERT-14 | Duplicate in sharded deployment | Enforced per shard/index constraints |
| UPSERT-15 | Worker claims already `PROCESSING` status | No-match, no new upsert |

A strong test suite includes positive, negative, and concurrency cases. Never treat "ran 100 times without seeing E11000" as proof a race cannot happen.

## 48. Logging and Monitoring for Duplicate Keys

Useful metrics:

| Signal | Meaning |
| --- | --- |
| E11000 count by namespace/index | Identifies which constraint is failing |
| E11000 rate by endpoint/service | Distinguishes creation APIs from background jobs |
| Upsert inserted vs. matched ratio | Observes create/update behavior |
| Retry attempts/successes | Detects retry storms |
| Idempotency hit rate | Share of valid repeated requests |
| Same-key different-payload conflicts | Indicates bugs or API misuse |
| Duplicate key during migration | Unclean legacy data |
| Write concern/network timeouts | Potentially linked to ambiguous outcomes |
| MongoDB index build failures | Incomplete schema deployment |
| Payment/event side-effect duplicates | Critical business incident |

Example log payload:

```json
{
  "event": "MONGODB_DUPLICATE_KEY",
  "errorCode": 11000,
  "namespace": "shop.payment_requests",
  "indexName": "uk_tenant_request",
  "operation": "upsert",
  "correlationId": "req-abc123",
  "businessKeyHash": "redacted-hash",
  "handledAs": "IDEMPOTENT_REPLAY"
}
```

This is an illustrative log schema. Do not log raw emails/phones/secrets or full payloads when unauthorized. For high-volume retries, use proper aggregation/sampling and rate-based alerts rather than alerting on every expected duplicate.

## 49. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "E11000 means MongoDB wrote two duplicate records" | The unique index **prevented** the duplicate write |
| "Only inserts cause duplicates" | Updates, upserts, bulk writes, and index builds can also fail |
| "Just changing `_id` fixes the error" | A secondary unique index may be colliding |
| "A field named `requestId` is automatically unique" | An actual unique index/constraint must exist |
| "Pre-checking `exists` then inserting is safe" | Race window exists between the two operations |
| "Upsert can never trigger E11000" | Filter/index mismatches and concurrency can still fail |
| "Two upserts on the same key always yield one E11000" | Server may converge into an update when conditions hold |
| "Having a unique index makes differing payloads idempotent" | Unique index does not check payload equivalence |
| "`$set` and `$setOnInsert` behave identically" | One runs on every match, the other only on insert |
| "Every E11000 can return HTTP 200" | Could be a payload conflict or another index |
| "E11000 is always a retryable error" | Constraint violations usually need business decisions |
| "`modifiedCount=0` means no record exists" | May have matched without modifying fields |
| "Adding `status` to the upsert filter makes it safer" | Can cause no-match and duplicate insert attempts |
| "Unique `email` allows unlimited `null` values" | Single-field unique indexes limit `null`/missing keys |
| "Sparse indexes skip `null` and missing identically" | Difference exists when field is explicitly `null` |
| "Collation does not affect duplicates" | Case-insensitive unique indexes treat differing cases as duplicates |
| "A unique multikey index forbids duplicate elements in one array" | Constraint primarily spans across different documents |
| "Spring `@Indexed(unique=true)` guarantees the index is deployed" | Must verify actual index creation/migration |
| "`Repository.save` auto-upserts by email" | Saves by entity identity, not arbitrary unique fields |
| "Unacknowledged writes still report E11000 fully" | No reliable write result is returned |
| "Transactions allow bypassing unique constraints" | Unique constraints still apply |
| "If a bulk write fails, every record rolls back" | Partial successes can occur outside transactions |
| "Dropping the index is the fastest fix" | Risks creating real duplicates and breaking invariants |
| "A timeout means nothing was inserted" | The write may have succeeded while the ACK was lost |

## 50. Exercises with Answers

### Exercise 1. Reading the Error

An insert throws `E11000 ... index: _id_ dup key: {_id:"A"}`. Main conclusion?

**Answer:** The collection already has a document with `_id:"A"` or another operation created the same ID; verify before retrying or changing the ID.

### Exercise 2. Unique Secondary Index

Two documents have different `_id` values but the same `email`, and the collection has a unique index on `email`. What happens to the second insert?

**Answer:** Fails with E11000 on the unique `email` index. Different `_id` values do not make a duplicate business unique key valid.

### Exercise 3. Compound Key

Unique index `{tenantId:1,email:1}`. Do identical emails in tenant A and tenant B collide?

**Answer:** No, provided `tenantId` differs and no other unique constraint is violated.

### Exercise 4. Update Causing a Duplicate

Document C2's email is updated to match C1's email in the same tenant. Result?

**Answer:** E11000 if a unique index covers `(tenantId, email)`. Duplicates do not occur only on inserts.

### Exercise 5. Upsert Semantics

What does `upsert:true` do when the filter matches nothing?

**Answer:** MongoDB attempts to insert a new document derived from the filter and update. If the new document's unique key collides, E11000 can occur.

### Exercise 6. Race Without an Index

Two workers upsert the same `requestId` without a unique index. Can two documents be created?

**Answer:** Yes, if both pass the no-match lookup phase before seeing each other's insert.

### Exercise 7. Race With an Index

Two workers upsert the same key with a unique index. Is exactly one E11000 guaranteed?

**Answer:** No. One writer inserts, and the other may update the newly inserted document or fail per documented conditions.

### Exercise 8. Server Conditions

Unique index `{requestId:1}`, filter `{requestId:"A",status:"NEW"}`. Does it match the exact index fields for convergence?

**Answer:** No. The filter adds `status`, so it does not match the unique index field set; E11000 can occur.

### Exercise 9. Status No-Match

Alice's email record has `status: "ACTIVE"`, and an upsert filters on Alice's email + `status: "PENDING"`. Why does a duplicate error happen?

**Answer:** It fails to match the existing record due to `status`, so the insert branch uses Alice's email and hits the unique email index.

### Exercise 10. `$setOnInsert`

Does `$setOnInsert: {status:"RECEIVED"}` overwrite the status of an existing record?

**Answer:** No. It only applies when the upsert performs a new insert.

### Exercise 11. `$set`

Can `$set:{payloadHash:"new"}` in an upsert alter existing data?

**Answer:** Yes, if the filter matches an existing record. This is dangerous for idempotency keys when payloads must not change.

### Exercise 12. Dangerous Command

A team wants to drop the unique index because E11000 happens too often. What is the problem?

**Answer:** It removes the uniqueness safeguard, creates real duplicates, and may prevent rebuilding the index; investigate the root cause instead.

### Exercise 13. Null

Single-field unique index on `email`, and two documents both omit `email`. Can the second insert fail?

**Answer:** Yes, because missing/`null` values can generate the same `null` index key under unique index rules.

### Exercise 14. Partial Index

You want `email` unique only when `email` is a BSON String. What can you use?

**Answer:** A unique partial index with `partialFilterExpression: {email: {$type:"string"}}`, paired with appropriate schema validation.

### Exercise 15. Sparse Index

Does a unique sparse index always skip an explicitly present `null` field the same way as a missing field?

**Answer:** No. Sparse typically skips missing fields, whereas an explicitly present `null` field can still be indexed.

### Exercise 16. Collation

Can a case-insensitive unique email index treat `"Alice"` and `"alice"` as duplicates?

**Answer:** Yes, depending on the defined collation.

### Exercise 17. Different Unique Index

An upsert by `requestId` hits E11000 on the `email` index. Should this be treated as an idempotent replay of the same `requestId`?

**Answer:** No. Handle the `email` constraint per business policy and inspect the existing record/payload.

### Exercise 18. Retry Timeout

An insert timed out, though the server may have written it. Should a retry generate a new `requestId`?

**Answer:** No, if the intent is still the same request. Keep the stable key, reconcile existing state, and retry idempotently per policy.

### Exercise 19. Java Exception

Which exception type does the Java Sync Driver typically throw for a single-write E11000?

**Answer:** Usually `MongoWriteException` with `getError().getCode()==11000`; depending on the operation, bulk or command exceptions also exist.

### Exercise 20. Spring Data Exception

`MongoTemplate.insert()` hits a duplicate key and Spring translates the error. Which exception is typical?

**Answer:** `org.springframework.dao.DuplicateKeyException`.

### Exercise 21. `Repository.save`

Two entities have different `_id` values but the same email; does `repository.save()` merge them by email?

**Answer:** No. `save` follows entity identity; the unique email index will throw E11000.

### Exercise 22. Index Annotation

`@CompoundIndex(unique=true)` is on the Java class, yet production lacks the index. Can a race create duplicates?

**Answer:** Yes. Ensure the index is actually deployed and verified, not just annotated.

### Exercise 23. Modified Count

An upsert returns `matchedCount=1, modifiedCount=0`. Does that mean no document was found?

**Answer:** No. A document matched, but the update made no changes to its content.

### Exercise 24. Unique Multikey

Does a unique index on an array forbid duplicate elements within the same document?

**Answer:** It cannot be relied upon as an intra-array validator; a unique multikey index primarily enforces constraints across documents by index keys.

### Exercise 25. Bulk Writes

An unordered `insertMany` hits one duplicate. Could other inserts have succeeded?

**Answer:** Yes. Inspect each write error and final state rather than assuming the entire batch rolled back.

### Exercise 26. Transaction

Inside a transaction, is inserting a duplicate unique key allowed because writes are atomic?

**Answer:** No. Unique constraints still apply; errors must be handled per transaction/error contract.

### Exercise 27. Stale Version

An upsert filter contains `version:7` while the record is at version 8, keeping unique `externalId`. Why did it error?

**Answer:** No-match due to the stale version caused the upsert to attempt inserting with the same `externalId`; it should be a conditional update without upsert that returns a conflict.

### Exercise 28. Idempotency

Two requests share the same key but have different `payloadHash` values. Can you return success because the unique index prevented a duplicate?

**Answer:** No. The business requests are not equivalent; return a conflict or handle per explicit policy.

### Exercise 29. Race Test

An integration test expects two concurrent upserts on the same key to yield **one success and one E11000**. Is that a valid invariant?

**Answer:** Not as a general invariant. The server may converge into an update; the invariant should be one final record and valid side effects.

### Exercise 30. Root Cause

E11000 occurs when creating a unique index on an existing collection. Should you blindly delete all duplicate records and rebuild?

**Answer:** No. Reconcile references, business owners, and deduplication policy before cleanup.

## 51. Pre-Deployment Checklist

### Schema and Indexes

- [ ] Business identity clearly defined (`tenant`, `externalId`, `requestId`, `email`, etc.).
- [ ] Unique index actually exists and built successfully.
- [ ] Compound key properly scoped to tenant/organization.
- [ ] Clear null/missing policy for optional fields.
- [ ] Partial/sparse/collation options match data semantics.
- [ ] BSON types and canonicalization consistent across writers.
- [ ] Sharded topology supports the intended uniqueness.

### Upsert Design

- [ ] Only use `upsert:true` when creating a record if the identity is absent is permitted.
- [ ] Filter by stable identity; avoid unnecessarily adding `status`/`version`.
- [ ] Create-only fields placed inside `$setOnInsert`.
- [ ] Mutable fields in `$set/$inc` governed by explicit policy.
- [ ] Never inadvertently modify unique key fields inside an upsert.
- [ ] Never use upsert for state transitions on entities that must already exist.
- [ ] Inspect `matchedCount/upsertedId` properly without confusing no-ops.

### Conflict and Idempotency

- [ ] Idempotent response defined for same key / same payload.
- [ ] Conflict returned for same key / different payload.
- [ ] E11000 classified by index and key, not catch-all success.
- [ ] Retries preserve stable idempotency keys.
- [ ] Ambiguous timeout/write-concern outcomes reconciled before replay.
- [ ] Payment/email/event side effects protected by idempotency.
- [ ] Logging does not leak PII inside `dup key`.

### Testing and Operations

- [ ] Sequential duplicate insert test verifies error mapping.
- [ ] Concurrent upsert test runs against a real unique index.
- [ ] Filter/index mismatch test covers no-match scenarios.
- [ ] Null/missing/partial/collation behavior tested per policy.
- [ ] Bulk partial-success and retry tests implemented.
- [ ] Error monitoring broken down by namespace/index/endpoint.
- [ ] Runbook distinguishes E11000 from timeout/validation/`WriteConflict`.
- [ ] Unique indexes never dropped simply because error counts rose.

## 52. Summary

**E11000 duplicate key** is MongoDB's error indicating that a write conflicted with a **unique index**. When investigating, inspect the **collection, index, key pattern/value, and actual operation**, rather than looking at a raw message string alone. Errors can arise from inserts, updates, upserts, bulk imports, or building a unique index on already-duplicated data.

**Upsert does not guarantee "if a record exists by business key, E11000 will never occur."** If the filter adds `status`/`version` or mismatches the index, it can miss the existing document, fall back to insert, and collide with the unique constraint. When multiple upserts race, one writer inserts while another **may update the newly created record or receive a duplicate key error** per server-supported conditions. Lacking a unique index is even worse because it allows duplicate documents to be created.

A solid design requires **a stable business identity + properly scoped unique index + matching upsert filter + `$setOnInsert` for create-once fields + explicit conflict/idempotency handling**. State transitions must use conditional updates instead of indiscriminate upserts. When E11000 occurs, the application must distinguish genuine idempotent replays from differing payloads or colliding secondary indexes, without blindly retrying or suppressing all errors.

Finally, **a unique constraint is a data-integrity safeguard, not something to turn off when errors appear**. Keep the constraint, find the root cause, fix the write path, test real concurrency, and measure business impact—that is sustainable incident resolution.

### Official References

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — updateOne and Upsert](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — update (Upsert with Duplicate Values)](https://www.mongodb.com/docs/manual/reference/method/db.collection.update/)
- [MongoDB Manual — findAndModify (Upsert with Unique Index)](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/)
- [MongoDB Manual — insertOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/)
- [MongoDB Manual — $setOnInsert](https://www.mongodb.com/docs/manual/reference/operator/update/setOnInsert/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
