# Testing Unique Indexes, TTL, and Asynchronous Behaviors in MongoDB

## 1. Introduction: Same MongoDB, Different Observation Timing

Suppose a Java system uses MongoDB for three tasks:

1. Account registration: each account's `emailNormalized` must be unique.
2. Storing verification codes: documents must disappear automatically once expired.
3. Emitting events: after writing an order, a background worker updates a status collection or publishes a message.

Across these three cases, testing **differs in when outcomes become observable**.

- **Unique indexes** block duplicate writes at the moment the server enforces the constraint, once the index is ready. Tests must verify the second write fails with a duplicate-key error rather than waiting for a background worker to detect duplicates.
- **TTL indexes** mark documents eligible for expiration based on date/time fields, yet physically delete documents via a background process. Tests must never expect a document to vanish at the exact second it expires.
- **Other asynchronous behaviors** such as outbox workers, secondary replication, Search indexing, Change Streams consumers, and event-driven projections carry their own latencies and failure modes. Tests must wait for **the business condition** to converge within a reasonable deadline.

```text
                    A business operation
                           |
          +----------------+------------------+
          |                |                  |
          v                v                  v
    Unique index       TTL index        Background worker
          |                |                  |
    Duplicate write?   expiresAt passed?  Job/event exists?
          |                |                  |
    Server rejects     TTL monitor        Worker runs
    on write           checks periodically when scheduled
          |                |                  |
    Assert error       Poll until         Poll until output
    or success         actually deleted   state stabilizes
```

> **Core principle:** testing a **synchronous constraint** checks the immediate outcome of the operation; testing an **asynchronous system** checks convergence toward the expected state within a time window rather than guessing the exact moment it occurs.

---

## 2. Learning Objectives

After this lesson, you will be able to:

- Create and test single-field, compound, sparse, and partial unique indexes.
- Verify `E11000` errors on inserts, updates, upserts, and concurrent writes.
- Distinguish unique indexes from application-level query-before-insert checks.
- Test semantics for `null`, missing fields, collation, and tenant scoping.
- Understand TTL `expireAfterSeconds`, BSON Date types, and UTC clocks.
- Write flake-resistant TTL integration tests using deadline-bounded polling.
- Know why `Thread.sleep(1000)` never proves TTL is broken.
- Structure MongoDB Testcontainers/JUnit integration tests.
- Test eventual consistency, retries, idempotency, workers, and “never happens” invariants.
- Separate unit, integration, and end-to-end tests for these features.
- Diagnose test failures caused by logic bugs, infrastructure, timing, or scheduling.

---

## 3. Three Behavior Groups to Test

| Group | Examples | Verification approach |
| --- | --- | --- |
| Enforced immediately on write | Unique indexes, schema validation | Assert write succeeds or throws specific error |
| MongoDB-side asynchronous | TTL deletion, secondary replication, Search indexing | Poll observable condition from the right read source |
| Application-side asynchronous | Outbox consumer, background exports, retry queues | Poll business state, enforce timeouts, check idempotency |

### 3.1. Do Not Confuse “Command Accepted” with “System Converged”

A successful `insertOne` does not prove a message appeared in Kafka. A document with `expiresAt` in the past does not prove the TTL monitor finished deleting it. An unfinished `createIndex` call does not prove the unique constraint is active yet.

### 3.2. Bounded Eventual Consistency

“Eventual” does not mean waiting forever. Every test must have:

- An observable **condition**.
- A **deadline** large enough for the environment and SLA.
- A sensible polling interval.
- Isolated data and namespaces.
- Diagnostics when the deadline expires.
- Resource cleanup even when the test fails.

---

## 4. Example Data Model

Use an `accounts` collection:

```javascript
{
  _id: ObjectId("691800000000000000000001"),
  tenantId: "tenant-A",
  emailNormalized: "user@example.com",
  active: true,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

A `verificationCodes` collection:

```javascript
{
  _id: ObjectId("691800000000000000000002"),
  accountId: ObjectId("691800000000000000000001"),
  codeHash: "hash-not-raw-secret",
  expiresAt: ISODate("2026-11-14T08:05:00Z")
}
```

And an `outbox` collection:

```javascript
{
  _id: "event-1001",
  aggregateId: "order-1001",
  eventType: "ORDER_CREATED",
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

Examples use a **dedicated test database**. Never run `drop()`, create/drop indexes, or insert fake data in production.

---

# PART I — TESTING UNIQUE INDEXES

## 5. What Does a Unique Index Guarantee?

A unique index enforces a constraint at the MongoDB layer: **two distinct documents cannot share the same index key** according to the index specification, collation, and filter expression.

Example:

```javascript
db.accounts.createIndex(
  { emailNormalized: 1 },
  { unique: true, name: "uq_email_normalized" }
);
```

If the collection already contains:

```javascript
{
  _id: 1,
  emailNormalized: "alice@example.com"
}
```

inserting another document:

```javascript
{
  _id: 2,
  emailNormalized: "alice@example.com"
}
```

is rejected with a duplicate-key error.

### 5.1. A Unique Index Differs from `findOne()` Before Insert

Code like:

```java
if (accounts.find(eq("emailNormalized", email)).first()
        == null) {
    accounts.insertOne(document);
}
```

**Does not guarantee uniqueness under concurrency**. Two requests can both read “not found” and then both insert.

```text
Request A                  Request B
---------                  ---------
find -> no email           find -> no email
       |                          |
       +-----------+--------------+
                   |
             both insert
```

With a unique index, one operation is accepted and the duplicate is rejected by server-enforced constraints.

### 5.2. Tests Should Check More Than Final Data

Verify **all three**:

1. The first write is accepted.
2. The second write throws the expected duplicate-key error.
3. The collection retains the exact expected document count and data.

---

## 6. Mongosh Test: Duplicate Insert

```javascript
use mongo_index_test;

db.accounts.drop();

db.accounts.createIndex(
  { emailNormalized: 1 },
  { unique: true, name: "uq_email_normalized" }
);

db.accounts.insertOne({
  _id: "acct-1",
  emailNormalized: "alice@example.com"
});

db.accounts.insertOne({
  _id: "acct-2",
  emailNormalized: "alice@example.com"
});
```

The second insert fails with an error similar to:

```text
E11000 duplicate key error
```

The standard duplicate-key error code is **11000**. Do not compare the entire error message verbatim, as formatting varies across MongoDB versions and drivers.

### 6.1. Distinguish Duplicate `_id` from Duplicate Field

If a test accidentally reuses the same `_id`, the server raises an error on the `_id_` index rather than on the unique `emailNormalized` index.

**Correct approach:** two documents with **distinct `_id`s**, yet identical `emailNormalized` values.

---

## 7. JUnit 5: Asserting Unique Errors with the Java Sync Driver

With `org.mongodb:mongodb-driver-sync` and JUnit 5:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

public class UniqueIndexTest {

    private MongoCollection<Document> accounts;

    @Test
    void duplicateEmailIsRejected() {
        accounts.createIndex(
            Indexes.ascending("emailNormalized"),
            new IndexOptions()
                .unique(true)
                .name("uq_email_normalized")
        );

        accounts.insertOne(
            new Document("_id", "acct-1")
                .append("emailNormalized",
                        "alice@example.com")
        );

        MongoWriteException error =
            assertThrows(
                MongoWriteException.class,
                () -> accounts.insertOne(
                    new Document("_id", "acct-2")
                        .append("emailNormalized",
                                "alice@example.com")
                )
            );

        assertEquals(11000, error.getError().getCode());
        assertEquals(
            1,
            accounts.countDocuments()
        );
    }
}
```

`accounts` must be initialized by the test class fixture; the snippet illustrates the test method itself. A full Testcontainers/JUnit setup appears later.

### 7.1. Why Not Assert Exact Message Text?

Avoid:

```java
assertEquals(
    "E11000 duplicate key error collection: ...",
    error.getMessage()
);
```

Messages embed namespace, index name, key values, and release-dependent formatting. Prefer checking:

- Error category/type.
- Error code 11000.
- Collection state.
- Index metadata when proving which constraint triggered the failure.

### 7.2. Different Operations Throw Different Exception Classes

- `insertOne()` duplicates typically throw `MongoWriteException`.
- `bulkWrite()` can throw `MongoBulkWriteException`.
- `createIndex()` failing on pre-existing duplicates can throw `MongoCommandException` or a driver-specific subclass.
- Never wrap every operation in `assertThrows(MongoWriteException.class, ...)` when the API does not guarantee that exact exception type.

---

## 8. Testing Uniqueness on UPDATE

A unique index checks both inserts **and updates**.

Given:

```javascript
{ _id: "A", emailNormalized: "a@example.com" }
{ _id: "B", emailNormalized: "b@example.com" }
```

The operation:

```javascript
db.accounts.updateOne(
  { _id: "B" },
  { $set: { emailNormalized: "a@example.com" } }
);
```

must be rejected while the unique index exists.

### 8.1. Java Example

```java
accounts.createIndex(
    Indexes.ascending("emailNormalized"),
    new IndexOptions().unique(true)
);

accounts.insertOne(
    new Document("_id", "A")
        .append("emailNormalized", "a@example.com")
);

accounts.insertOne(
    new Document("_id", "B")
        .append("emailNormalized", "b@example.com")
);

MongoWriteException error = assertThrows(
    MongoWriteException.class,
    () -> accounts.updateOne(
        Filters.eq("_id", "B"),
        Updates.set("emailNormalized",
                    "a@example.com")
    )
);

assertEquals(11000, error.getError().getCode());

Document unchanged = accounts.find(
    Filters.eq("_id", "B")
).first();

assertEquals(
    "b@example.com",
    unchanged.getString("emailNormalized")
);
```

### 8.2. Why Assert the Document Remained Unchanged?

The test must prove the update was rejected without altering the target field. Asserting only on the thrown error can overlook corrupted state from setup bugs.

---

## 9. Compound Unique Index: Uniqueness per Tenant

In multi-tenant SaaS, emails are often unique **within a tenant**, rather than globally.

Index:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true, name: "uq_tenant_email" }
);
```

Expected table:

| Document | tenantId | emailNormalized | Outcome |
| --- | --- | --- | --- |
| A | T1 | a@example.com | Written |
| B | T1 | a@example.com | Rejected |
| C | T2 | a@example.com | Written |
| D | T1 | b@example.com | Written |

### 9.1. Java Test

```java
accounts.createIndex(
    Indexes.compoundIndex(
        Indexes.ascending("tenantId"),
        Indexes.ascending("emailNormalized")
    ),
    new IndexOptions().unique(true)
);

accounts.insertOne(
    new Document("_id", "A")
        .append("tenantId", "T1")
        .append("emailNormalized", "a@example.com")
);

assertThrows(
    MongoWriteException.class,
    () -> accounts.insertOne(
        new Document("_id", "B")
            .append("tenantId", "T1")
            .append("emailNormalized", "a@example.com")
    )
);

assertDoesNotThrow(
    () -> accounts.insertOne(
        new Document("_id", "C")
            .append("tenantId", "T2")
            .append("emailNormalized", "a@example.com")
    )
);
```

### 9.2. Additional Checks

- `tenantId` is neither missing nor null if the domain forbids it.
- Create the index before writing data.
- Tenant-isolation queries never drop `tenantId`.
- If the collection is sharded, the unique index must satisfy sharding restrictions; see the dedicated section.

---

## 10. Single-Field Unique Indexes and Null/Missing

This case is notoriously easy to get wrong in tests.

With a **non-sparse single-field unique index**:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

MongoDB documents that a record where `email` is **missing** or `email: null` produces a null index key. Under uniqueness, at most one document can hold that null key in the index.

```javascript
db.users.insertOne({ _id: 1 });
// Succeeds if no null key exists yet.

db.users.insertOne({ _id: 2 });
// Duplicate key, because missing email -> null key.
```

### 10.1. Tests Must Include Missing Fields

Do not test only two identical strings. If an API treats email as optional, clarify whether the domain allows:

- Multiple users without an email?
- One document with `email: null` being valid?
- If yes, should the index be sparse or partial?
- Must missing be distinguished from explicit null?

### 10.2. Compound Unique Null Semantics

With compound index `{ tenantId: 1, email: 1 }`, the constraint applies to the **key tuple**.

Two documents:

```javascript
{ tenantId: "T1", email: null }
{ tenantId: "T2", email: null }
```

form distinct tuples and can coexist.

However, two documents both with `tenantId: "T1"` and missing/null `email` collide.

Never assume a compound unique index permits only one document missing `email` across the **entire collection**: evaluate the full index tuple.

---

## 11. Sparse Unique Indexes

A sparse index omits documents **missing** the indexed field.

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "uq_optional_email_sparse"
  }
);
```

Expected:

```javascript
db.users.insertOne({ _id: 1 });
db.users.insertOne({ _id: 2 });
// Both lack email: both succeed.

db.users.insertOne({ _id: 3, email: null });
// Creates a null index entry and succeeds.

db.users.insertOne({ _id: 4, email: null });
// Collides on the null key -> rejected.
```

### 11.1. Sparse Does Not Mean Ignoring Null

A field that **is present with value null** is still indexed by a sparse index. Thus, sparse unique allows multiple documents **missing** `email`, yet rejects multiple explicit `null`s.

### 11.2. Compound Sparse Behavior Is More Complex

Compound sparse indexes select documents based on rules across key types. Never mechanically extrapolate single-field sparse rules to every compound index.

---

## 12. Partial Unique Indexes: Controlling Which Documents Are Constrained

A partial index indexes only documents matching `partialFilterExpression`.

Example enforcing uniqueness only on string `email` values:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_string",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Consequently:

- Two documents missing `email` are allowed.
- Two documents with `email: null` fall outside the filter.
- Two documents with the same **string** email are rejected.

### 12.1. Why Use `$type: "string"`?

It avoids confusion among:

- `email` missing.
- `email: null`.
- `email` present as a string.

Applications should still enforce schema validation to prevent `email` from being a number or array if forbidden.

### 12.2. Creating a Partial Unique Index in Java

```java
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

IndexOptions options = new IndexOptions()
    .unique(true)
    .name("uq_email_string")
    .partialFilterExpression(
        new Document(
            "email",
            new Document("$type", "string")
        )
    );

users.createIndex(
    Indexes.ascending("email"),
    options
);
```

### 12.3. Test All Three Groups

1. Document matches the filter with a fresh key → succeeds.
2. Document matches the filter with a duplicate key → duplicate-key error.
3. Document falls outside the filter → not constrained by this index.

---

## 13. Soft Delete and Partial Uniqueness

If an account can be soft-deleted and its email reused, filter on `active`:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    unique: true,
    name: "uq_active_tenant_email",
    partialFilterExpression: { active: true }
  }
);
```

Test sequence:

```text
1. Insert active=true, T1, a@example.com       -> SUCCESS
2. Insert active=true, T1, a@example.com       -> DUPLICATE
3. Change first account active=false           -> SUCCESS
4. Insert new active=true, T1, a@example.com   -> SUCCESS
5. Change old account active=true              -> DUPLICATE
```

### 13.1. Test State Transitions

A partial unique constraint applies to documents **currently matching the filter**. Test updates that move a document **into** the filtered set, not just inserts.

### 13.2. The Domain Must Define `active` Explicitly

A document missing `active` does not match `{active: true}`. If business logic assumes “missing `active` means active” while the index does not, duplicates can slip through. Enforce required fields or schema validation.

---

## 14. Collation and Case-Insensitive Testing

By default, a simple binary collation treats:

```text
Alice@Example.com
alice@example.com
```

as two distinct strings.

If the domain needs case-insensitive equality, create the unique index with an appropriate collation:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "uq_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
```

`strength: 2` is a common collation setting distinguishing accents/diacritics while ignoring case differences for that locale.

### 14.1. Test

```javascript
db.users.insertOne({
  _id: "U1",
  email: "Alice@example.com"
});

db.users.insertOne({
  _id: "U2",
  email: "alice@example.com"
});
// Triggers E11000 because both share the same collation key.
```

### 14.2. Never Oversimplify Email Rules

Email canonicalization policies vary across domains and providers. Never blindly lowercase or strip dots/accents unless the business policy explicitly specifies it.

### 14.3. Query Collation and Index Collation

A query seeking to use a collated index must specify a matching collation unless the collection default already matches. Test both uniqueness and query/index plans when endpoints depend on index performance.

---

## 15. Unique Multikey: Intra-Document vs Inter-Document Duplicates

When an indexed field is an array, MongoDB creates a **multikey index**.

With a unique multikey index, the constraint applies across index keys **between separate documents**. One document holding duplicate values inside its own array does not automatically violate uniqueness solely due to intra-document duplicates.

Example:

```javascript
db.groups.createIndex(
  { aliases: 1 },
  { unique: true }
);
```

A document:

```javascript
{
  _id: "G1",
  aliases: ["red", "red", "blue"]
}
```

is accepted; MongoDB does not treat identical keys within the same document as a cross-document collision. However, another document containing alias `"red"` will violate the constraint.

### 15.1. Do Not Substitute Unique Multikey for Application Validation

If business rules forbid duplicate elements **within the same array**, add dedicated schema or application validation. Unique multikey indexes do not enforce that invariant.

### 15.2. Compound Multikey Limitations

A compound multikey index cannot index documents where more than one indexed field is an array under MongoDB rules. Write dedicated tests for multi-array schemas.

---

## 16. Index Builds: Test Preconditions Before Writing

If the collection already contains duplicate data:

```javascript
db.users.insertMany([
  { _id: "U1", email: "a@example.com" },
  { _id: "U2", email: "a@example.com" }
]);
```

running:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

fails when MongoDB detects duplicate keys during the index build/commit.

### 16.1. Do Not Test Only Inserts After Index Creation

Cover two distinct scenarios:

1. Empty/clean collection → build succeeds → constraint is active.
2. Collection already has duplicates → index build fails → never assume the index exists.

### 16.2. Java Test Sketch

```java
users.insertMany(List.of(
    new Document("_id", "U1").append("email", "a@x.test"),
    new Document("_id", "U2").append("email", "a@x.test")
));

assertThrows(
    com.mongodb.MongoCommandException.class,
    () -> users.createIndex(
        Indexes.ascending("email"),
        new IndexOptions().unique(true)
    )
);
```

Driver versions/APIs may throw a specific subclass of `MongoCommandException`. For more stable tests, verify **error code 11000 and that the index is not present/ready** rather than matching exact message text.

### 16.3. Replica Set Index Builds Use Commit Quorum

Modern index builds on replica sets follow commit quorum rules. Never launch test writes assuming “once `createIndex` started, uniqueness is enforced.” Begin test writes only after `createIndex` returns successfully or the fixture confirms the index is ready.

---

## 17. Testing Concurrent Inserts: Exactly One Winner

This test is crucial because `findOne()`-then-`insertOne()` suffers from race conditions.

### 17.1. Objective

Two threads simultaneously attempt to insert the same `emailNormalized` within the same tenant:

- **One operation succeeds.**
- **One operation fails with duplicate key (11000).**
- The collection ends with **exactly one** document for that key.
- Never assume thread A always wins.

### 17.2. Java/JUnit 5 Code

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

public class ConcurrentUniqueTest {

    private MongoCollection<Document> accounts;

    @Test
    void concurrentCreateExactlyOneWinner() throws Exception {
        accounts.createIndex(
            Indexes.compoundIndex(
                Indexes.ascending("tenantId"),
                Indexes.ascending("emailNormalized")
            ),
            new IndexOptions().unique(true)
        );

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        ExecutorService pool =
            Executors.newFixedThreadPool(2);

        try {
            Callable<Boolean> write = () -> {
                ready.countDown();

                if (!start.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Start barrier timed out"
                    );
                }

                String id = java.util.UUID.randomUUID()
                    .toString();

                try {
                    accounts.insertOne(
                        new Document("_id", id)
                            .append("tenantId", "T1")
                            .append("emailNormalized",
                                    "race@example.com")
                    );
                    return true;
                } catch (MongoWriteException e) {
                    if (e.getError().getCode() == 11000) {
                        return false;
                    }
                    throw e;
                }
            };

            Future<Boolean> first = pool.submit(write);
            Future<Boolean> second = pool.submit(write);

            assertTrue(
                ready.await(10, TimeUnit.SECONDS),
                "Workers did not become ready"
            );

            start.countDown();

            boolean a = first.get(20, TimeUnit.SECONDS);
            boolean b = second.get(20, TimeUnit.SECONDS);

            assertNotEquals(
                a, b,
                "Exactly one write must succeed"
            );

            assertEquals(
                1,
                accounts.countDocuments(
                    new Document("tenantId", "T1")
                        .append(
                            "emailNormalized",
                            "race@example.com"
                        )
                )
            );
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

### 17.3. Note on Determinism

`CountDownLatch` brings both threads close to the same starting gate; it **does not guarantee** the server receives both packets at the exact same nanosecond. What is tested is that the invariant holds under any interleaving.

### 17.4. Never Assert `first == true`

Thread scheduling, networking, and server execution order are not guaranteed. Asserting a specific thread always wins produces flaky tests.

---

## 18. Bulk Writes and Duplicate Keys

With a bulk insert:

```java
List<Document> data = List.of(
    new Document("_id", "A").append("email", "a@example.com"),
    new Document("_id", "B").append("email", "a@example.com"),
    new Document("_id", "C").append("email", "c@example.com")
);
```

When `email` has a unique index:

- `ordered` stops processing subsequent operations after an error.
- `unordered` continues executing remaining operations.
- A bulk operation can **partially succeed**.
- The exception thrown is `MongoBulkWriteException`, not merely `MongoWriteException`.

### 18.1. Tests Must Verify Final State

Do not assert “bulk threw an exception so zero records were written.” Verify:

- Which documents were actually persisted.
- That the duplicate record was blocked.
- Total record/key counts.
- Error codes inside `getWriteErrors()`.
- Ordered vs unordered behavior for your driver/server version.

### 18.2. Retrying After a Bulk Failure

Retrying the whole batch without an idempotency key can hit duplicate errors on records that succeeded earlier. Retry tests should use stable `_id`/business keys and verify final state.

---

## 19. Upserts and Unique Indexes

When two concurrent requests run `updateOne(..., upsert=true)` for the same business key, a unique index remains essential.

Example:

```java
accounts.updateOne(
    Filters.and(
        Filters.eq("tenantId", "T1"),
        Filters.eq("externalId", "E100")
    ),
    Updates.setOnInsert("status", "NEW"),
    new UpdateOptions().upsert(true)
);
```

With a compound unique index `{tenantId: 1, externalId: 1}`, racing requests cannot insert two documents with the same unique key.

### 19.1. Not Every Concurrent Upsert Succeeds Silently

Depending on filter/update shape and driver retry behavior, one racing upsert can still throw a duplicate-key error. Applications need a policy (re-read state, bounded retry, or return conflict). Never assume all concurrent upserts automatically succeed via the same path.

### 19.2. Tests Must Assert Domain Invariants

- At most one document per business key.
- Calling an idempotent operation again creates no duplicate state.
- Zero duplicate side effects (emails, payments, messages).
- Exceptions/retry outcomes match policy.

---

## 20. Sharded Clusters and Unique Indexes

In sharded collections, unique indexes carry restrictions.

Key point: cross-shard uniqueness is supported by MongoDB only when the unique index is the shard key or **has the shard key as a prefix**, subject to index-type and topology rules. Hashed indexes do not support `unique: true`.

For instance, if sharded on `{tenantId: 1}`, `{tenantId: 1, email: 1}` is a valid prefix, though additional shard-key and index-option constraints still apply.

### 20.1. Replica Set Tests Do Not Prove Sharded Compatibility

If production runs a sharded cluster, standalone or replica set tests only verify uniqueness logic within that topology—they do not prove the exact index can be created on a sharded collection.

### 20.2. Choosing Test Layers

- Unit: domain key composition.
- Integration: unique enforcement on a replica set.
- Environment compatibility: shard-key/index restrictions on sharded staging.
- E2E: writers across multiple `mongos` routers create zero duplicates.

### 20.3. Never Define Unique on a Hashed Index

If you need hash-based sharding alongside business-key uniqueness, consult MongoDB rules and design an appropriate shard key/index structure—never attempt `unique: true` on a hashed index.

---

# PART II — TESTING TTL INDEXES

## 21. What Is a TTL Index?

A **Time-To-Live (TTL)** index lets MongoDB automatically delete expired documents, commonly used for:

- Session records.
- One-time verification tokens.
- Temporary logs.
- Short-lived telemetry data.
- Bounded-retention retry metadata.
- Reconstructible cache documents.

Example:

```javascript
db.verificationCodes.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expires_at"
  }
);
```

With `expireAfterSeconds: 0`, a document becomes eligible for expiration once the timestamp in `expiresAt` passes, according to server time and TTL semantics.

Another example:

```javascript
db.auditEvents.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 }
);
```

The document becomes eligible approximately one day after `createdAt`.

### 21.1. TTL Performs Physical Cleanup

It deletes the **entire document** from the collection rather than removing one field or toggling `active: false`.

### 21.2. TTL Is Not a Millisecond-Exact Timer

The TTL monitor runs in the background on a periodic schedule. Reaching expiration **does not mean immediate deletion**.

---

## 22. TTL Requires BSON Date, Not Date Strings

Valid example:

```javascript
db.verificationCodes.insertOne({
  _id: "V1",
  expiresAt: ISODate("2026-11-14T08:00:00Z")
});
```

Invalid example for a TTL field:

```javascript
db.verificationCodes.insertOne({
  _id: "V2",
  expiresAt: "2026-11-14T08:00:00Z"
});
```

In the second example, `expiresAt` is a **string**, not a BSON Date. The TTL index does not parse ISO strings into Dates for deletion.

### 22.1. Testing BSON Type

```javascript
db.verificationCodes.find({
  _id: "V1",
  expiresAt: { $type: "date" }
});
```

Or in Java:

```java
Date expiresAt =
    document.getDate("expiresAt");
```

If fields can be null, missing, or mistyped, test both schema validation and TTL behavior.

### 22.2. TTL with Arrays

If the indexed field is an array of multiple BSON Dates, MongoDB uses the **earliest Date value** in the array to compute expiration. This is a critical edge case—never assume it uses the latest date.

### 22.3. Missing or Null Fields

If a document lacks the indexed field or holds a non-Date value, the TTL index has no valid date to expire the document. This easily creates “immortal documents” when an application accidentally writes the wrong type.

---

## 23. The TTL Monitor Is Asynchronous

Per MongoDB documentation:

- The TTL monitor runs in the background.
- It normally runs roughly every **60 seconds**.
- Deletion can occur anywhere within 0–60 seconds after a document becomes eligible and the monitor executes.
- Under backlogs, heavy load, failovers, or resource pressure, deletion can lag beyond that interval.
- On a replica set, the **primary** performs TTL deletes; secondaries replicate the delete operations.
- After a new TTL index finishes building, the monitor begins processing already-expired documents in the collection.

### 23.1. Illustrative Timeline

```text
12:00:00  Document expiresAt reached
12:00:01  Application find() may still return the document
12:00:30  TTL monitor has not run its next pass yet
12:01:00  TTL monitor scans and begins deleting
12:01:02  Document is finally gone
```

There is no exact per-document deletion timestamp guarantee.

### 23.2. Never Test with Fixed Sleeps

Poor practice:

```java
Thread.sleep(1500);
assertNull(codes.find(eq("_id", id)).first());
```

Even with working code, the TTL monitor may not have run yet; the test will flake or fail unpredictably across fast and slow machines.

### 23.3. Use Deadline-Bounded Polling

```text
insert expired document
       |
       v
assert exists immediately
       |
       v
poll every 1 second
       |
       +--> deleted? PASS
       |
       +--> deadline? FAIL with diagnostics
```

An integration test deadline usually needs to exceed the default TTL cycle—for example, 2–3 minutes; this is an **environment-based test budget**, not an SLA guaranteeing MongoDB deletes within 3 minutes.

---

## 24. `expireAfterSeconds`: Computing Expiration Time

With TTL index:

```javascript
db.events.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 3600 }
);
```

Document:

```javascript
{
  _id: "E100",
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

becomes eligible for expiration after roughly:

```text
createdAt + 3600 seconds
= 2026-11-14T11:00:00Z
```

Physical deletion still occurs asynchronously afterward.

### 24.1. Using `expiresAt` with TTL 0

When each document has a different lifetime:

```javascript
db.codes.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0 }
);
```

Each document carries its own expiration timestamp. This pattern fits OTPs and password-reset tokens well.

### 24.2. Never Confuse Timezones

BSON Date stores a UTC instant. Applications should use `Instant` or UTC conventions rather than manually adding 7 hours to a Java `Date`.

### 24.3. Pick Explicitly Expired Dates for Tests

To avoid waiting out real business durations:

```java
Date expired = Date.from(
    Instant.now().minusSeconds(300)
);
```

Using a timestamp 5 minutes in the past ensures the document is eligible immediately upon insert; the test only waits for the monitor pass.

---

## 25. TTL Integration Testing with Awaitility

This snippet assumes dependencies:

- Java MongoDB Sync Driver.
- JUnit 5.
- Awaitility.
- A real MongoDB instance via Testcontainers or an isolated test environment.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import static com.mongodb.client.model.Filters.eq;
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.*;

public class TtlIndexTest {

    private MongoCollection<Document> codes;

    @Test
    void expiredDocumentIsEventuallyDeleted() {
        codes.createIndex(
            Indexes.ascending("expiresAt"),
            new IndexOptions()
                .expireAfter(0L, java.util.concurrent.TimeUnit.SECONDS)
                .name("ttl_expires_at")
        );

        String id = "expired-" + java.util.UUID.randomUUID();

        codes.insertOne(
            new Document("_id", id)
                .append(
                    "expiresAt",
                    Date.from(Instant.now().minusSeconds(300))
                )
        );

        // Insert was acknowledged; the document was just created.
        // Do not assume TTL has not already swept it within a tiny window.
        await()
            .atMost(Duration.ofMinutes(3))
            .pollInterval(Duration.ofSeconds(1))
            .until(
                () -> codes.find(eq("_id", id)).first() == null
            );
    }
}
```

**API note:** Java Sync Driver versions provide `IndexOptions.expireAfter(Long, TimeUnit)` or newer duration APIs. Check the Javadocs for your exact driver version; if that overload differs, use the matching `.expireAfter(...)` signature for your release. In Java driver 5.x, this form is typical.

### 25.1. Why Not Assert the Document “Must Still Exist 100 ms After Insert”?

The TTL monitor might happen to run right during the insert, sweeping the expired document very quickly. Asserting “still exists” right after insert can flake. If you must confirm insert acknowledgment, inspect the insert result or test non-expired data separately.

### 25.2. This Test Does Not Prove a 3-Minute SLA

It only proves that in the running test environment, TTL deletion completes within the test's time budget. If it fails, inspect the TTL monitor, primary status, and IOPS rather than concluding MongoDB guarantees a 3-minute deletion SLA.

---

## 26. A Clearer TTL Test Pattern: Expired and Non-Expired

In the same test collection, create two documents:

```java
Date past = Date.from(
    Instant.now().minusSeconds(600)
);

Date future = Date.from(
    Instant.now().plusSeconds(3600)
);

codes.insertMany(List.of(
    new Document("_id", "expired")
        .append("expiresAt", past),
    new Document("_id", "fresh")
        .append("expiresAt", future)
));
```

Then:

1. Poll until `"expired"` is deleted.
2. Assert `"fresh"` still exists.
3. Verify the TTL index configuration specifies `expireAfterSeconds: 0`.

Example:

```java
await()
    .atMost(Duration.ofMinutes(3))
    .pollInterval(Duration.ofSeconds(1))
    .until(
        () -> codes.find(eq("_id", "expired")).first() == null
    );

assertNotNull(
    codes.find(eq("_id", "fresh")).first()
);
```

### 26.1. Why Must `future` Be Far Enough Ahead?

If you pick `future = now + 1 second`, the document will also be expired by the time the monitor runs. The “fresh not deleted” assertion would fail due to bad setup rather than a MongoDB bug.

### 26.2. Do Not Prove “Never” with One Query

Asserting `future` exists after 90 seconds proves it survived up to the **observation point**, not that it can never be deleted prematurely. With a sufficiently distant TTL Date, the test checks expected retention across the run window.

---

## 27. Verifying the TTL Index Exists with the Right Options

A TTL test that only polls for disappearance could pass accidentally if unrelated code deleted the document. Verify the fixture metadata as well:

```javascript
db.verificationCodes.getIndexes();
```

Expected index:

```javascript
{
  key: { expiresAt: 1 },
  name: "ttl_expires_at",
  expireAfterSeconds: 0
}
```

This is partial illustrative metadata; real output includes additional fields.

Java:

```java
boolean found = false;

for (Document index : codes.listIndexes()) {
    if ("ttl_expires_at".equals(index.getString("name"))) {
        Number ttl = (Number) index.get("expireAfterSeconds");
        assertNotNull(ttl);
        assertEquals(0L, ttl.longValue());
        found = true;
    }
}

assertTrue(found, "Expected TTL index was not created");
```

### 27.1. Verify Index Creation Before Testing Deletion

If `createIndex()` failed silently, polling would time out while the real root cause was broken fixture setup. Separating index setup checks from TTL behavior assertions makes diagnostics clear.

---

## 28. Important TTL Index Restrictions

Typical rules from the MongoDB Manual:

- Standard TTL indexes are **single-field indexes**.
- Compound indexes do not support standard TTL behavior; `expireAfterSeconds` may be ignored or rejected on compound specs.
- `_id` cannot be used as a TTL index key.
- TTL requires a BSON Date field or an array containing Dates.
- Missing or non-Date fields never expire.
- Lowering the TTL duration on a large collection can make many documents eligible at once, creating heavy delete load.
- Time-series collections have specific bucket and partial TTL rules depending on server version.

### 28.1. Tests Preventing Misconfiguration

If the application relies on TTL on `expiresAt`, tests should verify the exact index key and `expireAfterSeconds` option—not merely that “some index exists.”

### 28.2. Never Treat `expireAfterSeconds` as Milliseconds

```javascript
{ expireAfterSeconds: 60 }
```

means **60 seconds**, not 60 milliseconds. In Java, double-check the `TimeUnit` or duration overload used.

---

## 29. TTL on Time-Series Collections

Time-series collections follow distinct semantics:

- `expireAfterSeconds` can be configured at collection creation.
- TTL operates on **buckets** once all measurements inside a bucket expire.
- Bucket retention can keep individual measurements alive longer than the per-measurement threshold.
- Starting in MongoDB 7.0, **partial TTL indexes** based on `metaField` are supported on time-series collections under documented conditions.
- Never apply standard-collection timing assumptions to assert an individual time-series measurement vanishes at its exact threshold.

### 29.1. Bucket Behavior Example

```text
Bucket spans time 10:00 to 10:59
expireAfterSeconds = 300

A measurement from 10:00 may not be deleted
alone at 10:05 while the bucket still holds
newer, unexpired measurements.
```

### 29.2. What Layers Should Be Tested?

- Index/collection metadata.
- Timestamp types and granularity.
- Bucket aging across an appropriate window.
- Eventual disappearance once the entire bucket becomes eligible.
- Actual MongoDB version behavior.

### 29.3. Avoid Overly Short Time-Series TTL Tests

A test waiting 10–20 seconds on a time-series collection with a one-hour bucket span can fail even when the system works properly. Set test fixtures far enough in the past and review bucket max span by granularity.

---

## 30. TTL on Replica Sets: Only the Primary Executes Deletes

On a replica set:

```text
MongoDB PRIMARY
    |
    | TTL monitor identifies expired docs
    v
DELETE operation
    |
    | replication/oplog
    v
MongoDB SECONDARIES
```

Therefore:

- Only the primary actively runs TTL deletes.
- Secondaries apply deletes via replication.
- Tests reading from a secondary may still observe expired documents during replication lag.
- After failover, there may be a delay before the new primary runs its TTL pass.
- A single standalone container can differ from a production replica set in these respects.

### 30.1. Read from the Primary When Testing Basic TTL

Use the default primary read preference to eliminate a second source of eventual delay.

### 30.2. Test Replication Separately

If the application intentionally reads from secondaries, write a dedicated test checking “after primary deletes, secondary eventually reflects the deletion” with a deadline. Do not mix TTL delay and replication lag into one ambiguous test.

---

## 31. TTL Does Not Replace Application-Level Expiration Checks

This is a vital security rule.

An OTP code expired at 10:00, yet the TTL monitor does not delete it until 10:00:45. If the application checks only:

```java
codes.find(Filters.eq("codeHash", hash)).first();
```

and accepts the code simply because the document still exists, an expired code gets accepted.

### 31.1. Correct Business Query

```java
Date now = new Date();

Document usable = codes.find(
    Filters.and(
        Filters.eq("codeHash", hash),
        Filters.gt("expiresAt", now)
    )
).first();
```

TTL handles storage cleanup only; the application enforces logical expiration deadlines.

### 31.2. Split Tests Into Two Parts

**Unit/integration business test:**

- Insert a code with `expiresAt` in the past.
- Call the verification API immediately.
- Expect rejection **without waiting for the TTL monitor**.

**TTL integration test:**

- Insert an expired code.
- Poll until MongoDB physically cleans up the document.
- Never treat physical deletion as the logical validity guard.

---

## 32. Testing Clocks and Time Skew

In Java, generate expiration timestamps using `Instant` and `Clock`:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-14T10:00:00Z"),
    ZoneOffset.UTC
);

Instant expiresAt = Instant.parse(
    "2026-11-14T09:59:59Z"
);

boolean expired =
    !expiresAt.isAfter(fixed.instant());

assertTrue(expired);
```

### 32.1. Injectable Clocks Make Unit Tests Deterministic

Boundary cases:

- 1 ms before expiration.
- Exact expiration timestamp.
- 1 ms after expiration.
- Day/month/year rollovers.
- UTC timezone handling.
- Verifying the saved Date keeps the right BSON type.

### 32.2. You Cannot Fake the Java Clock to Force MongoDB's TTL Monitor

The MongoDB server has its own clock. `Clock.fixed` shifts only the Java test's clock, **not the server clock**.

Therefore:

- Unit test deadline logic with a fake `Clock`.
- Run TTL integration tests with Dates well behind the server wall clock.
- Never alter OS or Docker host clocks during shared test runs.

---

## 33. TTL Monitor Metrics and Diagnostics

MongoDB reports:

```javascript
db.serverStatus().metrics.ttl;
```

Depending on version, fields include:

- `deletedDocuments`: documents deleted by TTL since process startup.
- `passes`: number of TTL monitor passes.
- `subPasses`: number of sub-passes.
- Additional counters such as `deletedKeys`, `examinedDocuments`, `examinedKeys`, and `invalidTTLIndexSkips` depending on version.

### 33.1. Counters Are Server-Wide

Never conclude:

```text
metrics.ttl.deletedDocuments increased by 1
=> my test document was definitely deleted
```

The server might have deleted a document in another collection. To verify your test record, **query by its specific ID**.

### 33.2. Use Deltas for Investigation

```text
before: metrics.ttl.passes = 100
after:  metrics.ttl.passes = 102
```

The delta confirms monitor passes occurred; if your test document still exists, inspect:

- Index key/options.
- BSON Date type.
- Date value.
- Primary status.
- Read preference.
- Collection name.
- Server version.
- TTL monitor backlog.

### 33.3. Never Rely on Metrics as the Sole Source of Truth

Some Atlas tiers or user roles restrict access to `serverStatus` fields. Tests must rely on core business assertions, using metrics purely as diagnostics when available.

---

## 34. Modifying a TTL Index Option

If a TTL index already exists and you need to change `expireAfterSeconds`, MongoDB documentation requires using `collMod` rather than simply calling `createIndex()` on the same key with a new option.

Example syntax:

```javascript
db.runCommand({
  collMod: "verificationCodes",
  index: {
    keyPattern: { expiresAt: 1 },
    expireAfterSeconds: 3600
  }
});
```

### 34.1. Testing Index Migration

When changing a retention policy, test:

1. Existing index has the old configuration.
2. Migration runs `collMod` successfully on the supported release.
3. `getIndexes()` reports the new option.
4. Updated expiration boundary dates behave properly.
5. Production data is not unexpectedly wiped.

### 34.2. Risk When Shortening TTL

Reducing retention from 30 days to 1 hour can immediately mark huge volumes of documents as expired. The TTL monitor will delete them gradually, potentially impacting IOPS and latency. Never deploy retention migrations without testing performance impact.

---

# PART III — TEST ENVIRONMENTS AND TEST PATTERNS

## 35. The Test Pyramid

Three sensible layers:

| Layer | Used to test | Characteristics |
| --- | --- | --- |
| Unit | Computing `expiresAt`, canonicalization, validation, retry policy | Fast, deterministic, no MongoDB required |
| Integration | Index constraints, TTL deletion, queries, writes | Requires real MongoDB; TTL tests can be slow |
| End-to-end | Registration API, workers, messaging, secondary reads | Tests full flow, resource-intensive |

### 35.1. Never Mock MongoDB to Prove a Unique Index

A mocked repository configured to throw duplicate-key only proves the application handles that exception—**it does not prove the server index was created properly**.

### 35.2. Never Make the Unit Suite Wait 60 Seconds for TTL

Business expiration rules can be unit tested with an injected `Clock` in milliseconds. Only a small set of integration tests need to wait for the real TTL monitor.

### 35.3. Test Tags

Use JUnit tags:

```java
@Tag("integration")
@Tag("slow-ttl")
@Test
void expiredDocumentEventuallyRemoved() {
    // ...
}
```

CI can run the slow TTL suite on an appropriate schedule/profile, but never skip it permanently if data retention is critical.

---

## 36. Testcontainers + JUnit 5 for Real MongoDB

Example using the common Testcontainers 1.x API style:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.TestInstance;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import java.util.UUID;

public abstract class MongoIntegrationFixture {

    private static final MongoDBContainer MONGO =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    static {
        MONGO.start();
    }

    private static final MongoClient CLIENT =
        MongoClients.create(
            MONGO.getReplicaSetUrl()
        );

    protected MongoCollection<Document> collection;
    protected String collectionName;

    @BeforeEach
    void newCollection() {
        collectionName = "case_" + UUID.randomUUID()
            .toString()
            .replace("-", "");

        MongoDatabase database =
            CLIENT.getDatabase("mongo_testing");

        collection = database.getCollection(collectionName);
    }

    @AfterEach
    void cleanup() {
        if (collection != null) {
            collection.drop();
        }
    }
}
```

Notes:

- Code illustrates Testcontainers versions providing `org.testcontainers.containers.MongoDBContainer`.
- Newer Testcontainers releases may change package/module APIs; check your dependency's release notes.
- Pick an image version that **supports** the feature under test; `mongo:7.0` is just an example.
- This fixture illustrates lifecycle only, omitting build/dependency config; CI needs a working Docker runtime and permissions.
- Because it runs in an isolated test environment, `drop()` targets only randomly named collections in the test database.
- MongoDB transaction/change stream tests require a replica set; `getReplicaSetUrl()` connects to Testcontainers' replica set in supported APIs.

### 36.1. Never Run TTL Tests on In-Memory Mocks

The TTL monitor is a server subsystem. In-memory mocks do not accurately emulate background deletion schedules or full index semantics.

### 36.2. Never Use a Production Cluster as an Integration Fixture

Unique/TTL tests create and drop indexes, insert duplicate keys, wait for deletions, and drop collections. Always use an isolated environment—never reuse a production namespace.

---

## 37. Isolating Fixtures to Prevent Cross-Test Interference

Common sources of flakiness:

- Two tests sharing the same `users` collection.
- Test A calling `drop()` while Test B inserts.
- The TTL monitor deleting leftover records from an earlier test.
- One test adding a unique index while another expects an unindexed collection.
- Background workers from a previous test still running when the next test starts.
- A test picking a future Date that is too close to now.

### 37.1. One Collection per Test

```java
String name = "ttl_" +
    UUID.randomUUID().toString().replace("-", "");

MongoCollection<Document> codes =
    database.getCollection(name);
```

In `@AfterEach`, drop only the collection owned by that test.

### 37.2. Do Not Rely Solely on Collection Cleanup

If a test launches Kafka consumers, scheduled workers, HTTP servers, or executor threads, shut them down after the test—otherwise events from an old test leak side effects into the next test.

### 37.3. Test Parallelism

Unit tests can run freely in parallel. For integration tests relying on the MongoDB TTL monitor or Docker resources, bound parallelism sensibly. The TTL monitor is a shared background thread inside `mongod`, not a dedicated thread per test collection.

---

## 38. Awaitility: Waiting for State Instead of Fixed Delays

For asynchronous work:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(200))
    .untilAsserted(() -> {
        assertEquals(
            "COMPLETED",
            jobs.find(eq("_id", jobId))
                .first()
                .getString("status")
        );
    });
```

### 38.1. Advantages

- Passes immediately once the condition holds.
- Never stalls tests unnecessarily when the system is fast.
- Enforces a clear deadline and timeout error.
- Handles complex assertions cleanly via `untilAsserted`.

### 38.2. Polling Must Be Safe

The polled expression must be **read-only**. Never do:

```java
await().until(() -> sendEmailAgain());
```

because every poll cycle triggers a side effect.

### 38.3. Null-Safe Polling

If the record may not exist yet:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .until(() -> {
        Document job =
            jobs.find(eq("_id", jobId)).first();
        return job != null
            && "COMPLETED".equals(job.getString("status"));
    });
```

Avoid calling `job.getString(...)` when `job == null`, which fails with an unrelated `NullPointerException`.

---

## 39. Choosing Timeouts Based on Each Behavior's Characteristics

| Behavior | Characteristics | Suggested test deadline |
| --- | --- | --- |
| Unique duplicate insert | Synchronous constraint | Assert exception immediately on operation |
| In-memory worker | Fast scheduling, non-deterministic | A few seconds |
| Outbox consumer via broker | Network/consumer scheduling | Tens of seconds |
| Secondary replication | Lag depends on topology/load | Per test SLO |
| TTL deletion | ~60 s periodic monitor + backlog | A few minutes for integration |
| Time-series TTL | Bucket granularity + monitor | Based on bucket span |
| Search indexing | Syncing data to separate search index | Based on data/index size |
| Backup/index build | Long, volume-dependent | Goal-specific, never a short blanket timeout |

These are **test budget design examples**, not MongoDB SLA guarantees.

### 39.1. Do Not Copy-Paste a 1-Second Timeout Everywhere

If CI is busy or containers cold-start, 1 second may be too short for a worker. Conversely, setting 10 minutes everywhere delays feedback on real logic bugs.

### 39.2. Observe Real p95/p99 Latencies

Measure async job completion latencies in staging/CI and choose budgets with sensible headroom. Never size timeouts solely from one developer laptop.

---

## 40. Testing “Eventually” vs “Never”

**Eventually:** a condition must become true over time.

```text
TTL: document must eventually be deleted.
Outbox: event must eventually become PROCESSED.
```

**Never:** a forbidden event must not happen during an observation window.

```text
Never allow two active accounts with the same email in one tenant.
Never send the same payment twice.
```

### 40.1. Direct Invariants Are Easier to Prove

Unique indexes make MongoDB reject duplicates immediately. Testing two concurrent writes plus the final count directly proves the tested race case.

### 40.2. For Async “Never,” a Single Query Is Insufficient

To confirm no duplicate messages are sent within 5 seconds, observe across the **entire window**, not solely at second 1.

Awaitility offers `during`/`atLeast` patterns depending on version, or you can collect events via an observer and assert after a bounded observation window. Even so, a finite test can never prove an event will **never** happen after the test finishes; production still requires idempotency and unique constraints.

---

## 41. Testing State Transitions

A background job state machine:

```text
PENDING -> RUNNING -> COMPLETED
                   \-> FAILED -> RETRY_WAIT -> RUNNING
```

Do not test only the `COMPLETED` outcome. Verify:

- One job is never simultaneously in two states.
- Two workers never hold the same lease.
- State transitions are recorded accurately.
- Retries obey limits and backoff.
- Permanently failed events are quarantined.
- Duplicate events produce no duplicate side effects.
- Once `COMPLETED`, no arbitrary reprocessing occurs.

### 41.1. Testing Worker Success

```java
String jobId = createTestJob();

await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(200))
    .until(() -> {
        Document job = jobs.find(eq("_id", jobId)).first();
        return job != null
            && "COMPLETED".equals(job.getString("state"));
    });
```

### 41.2. Testing Error Paths

Do not wait for a worker to reach `COMPLETED` when business rules dictate `FAILED`. Drive the state machine and assert error metadata and retry counts.

---

## 42. Outbox and Idempotency Tests

Flow:

```text
Order created
     |
     v
Insert outbox event
     |
     v
Worker publishes event
     |
     v
Mark outbox PROCESSED
```

If the worker publishes successfully and crashes before marking `PROCESSED`, the event may be republished.

### 42.1. Test Design

1. Create an order and a fixed outbox event ID.
2. Let the worker publish once.
3. Simulate a crash between publish and checkpoint.
4. Restart the worker.
5. Verify downstream idempotency by event ID.
6. Verify zero duplicate business side effects.
7. Check outbox state after retry.

### 42.2. Unique Index on Event ID

A unique index on `eventId` in a downstream inbox blocks reprocessing duplicate events. External side effects (payments/emails) still need dedicated idempotency policies.

### 42.3. Never Test by Guessing Worker Schedule with Sleep

Avoid:

```java
sendEvent();
Thread.sleep(500);
assertEquals(1, countProcessed());
```

Instead, poll by event/job ID within a deadline.

---

## 43. Change Streams and Eventual Event Tests

Change Streams allow subscribing to MongoDB changes when supported by the deployment.

Key considerations:

- Change Streams require a supporting topology (replica set or sharded cluster).
- The listener must **be established before** the triggering write if the test expects to observe that event.
- Opening a cursor/subscription does not automatically mean the worker is ready.
- A `resume token` differs from a server cursor ID.
- `tryNext()` returning null simply means no event arrived yet, not that the stream ended.
- Close cursors/subscriptions when the test ends.

### 43.1. The “Subscribe vs Publish” Race

Flawed:

```text
startListenerAsync()
insertDocument()
assertListenerSawEvent()
```

if `startListenerAsync()` returns before the listener actually subscribes.

### 43.2. Correct Test with a Readiness Barrier

```text
start listener
wait listener READY
insert document with correlation ID
await event with matching ID
close listener
```

### 43.3. Never Assert Global Order Across Distributed Sources

With multiple partitions, shards, or consumers, ordering guarantees have narrow scopes. Assert only ordering guarantees the system actually promises.

---

## 44. Replication Lag and Read Preference in Integration Tests

On a replica set:

- Primary processes writes.
- Secondaries fetch and apply the oplog.
- Reading from a secondary can return stale state.

### 44.1. Write Then Read from Primary

When testing basic unique/TTL logic, prefer primary reads to avoid replica lag interference.

### 44.2. Testing Read-Your-Writes

If business logic requires immediately seeing a completed write, choose the proper read preference, read concern, and session semantics. Never assume `secondaryPreferred` sees writes immediately.

### 44.3. Testing Eventual Secondary Consistency

1. Write the document on the primary.
2. Poll on a secondary using the configured read preference.
3. Base the deadline on environment/lag SLA.
4. Capture lag diagnostics on timeout.
5. Never conflate replication lag with TTL monitor lag.

---

## 45. TTL Deletion in Replicated Applications

When a document expires:

```text
Primary TTL delete
        |
        v
Secondary replay delete
```

A `find()` targeting a secondary can still see the document even after the primary deleted it. When such a test fails:

1. Check whether the primary already deleted it.
2. Check the test's read preference.
3. Check secondary replication lag.
4. Check TTL metrics.
5. Check Date values and index metadata.

Never paper over a wrong read source by blindly increasing timeouts.

---

## 46. Testing TTL Negative Paths

Cases to include:

| Document | Meaning | Expected |
| --- | --- | --- |
| `expiresAt` past Date | Eligible for TTL | Eventually deleted |
| `expiresAt` far-future Date | Not yet expired | Not deleted within test window |
| Missing `expiresAt` | No indexed Date | Not deleted by TTL |
| `expiresAt` as string | Wrong BSON type | Not deleted by TTL |
| `expiresAt: null` | No Date value | Not deleted by TTL |
| Array of multiple Dates | Uses earliest date | Eventually expires per earliest Date |
| Index `expireAfterSeconds: 0` | Expires at absolute Date | Past Date deleted after monitor pass |
| Index `expireAfterSeconds: 3600` | Expires at Date + duration | Before/at/after boundary accurate |

### 46.1. Never Use TTL to Prove Validation

If an application **must reject** a string in `expiresAt`, schema validation or application validation tests must assert the write fails. TTL simply ignores strings—that is not validation.

### 46.2. Testing “Not Deleted” Needs an Observation Window

An instantaneous check on a future Date proves only that the document exists right now. For retention policy tests, combine metadata checks, expiration-calculation logic tests, and an observation window aligned with the monitor schedule.

---

## 47. Testing Time Boundaries with Clock

Isolate domain logic from TTL:

```java
public final class CodeExpiryService {
    private final Clock clock;

    public CodeExpiryService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant expiresAt) {
        return !expiresAt.isAfter(clock.instant());
    }
}
```

Unit test:

```java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-14T10:00:00Z"),
    ZoneOffset.UTC
);

CodeExpiryService service =
    new CodeExpiryService(fixed);

assertFalse(
    service.isExpired(
        Instant.parse("2026-11-14T10:00:00.001Z")
    )
);

assertTrue(
    service.isExpired(
        Instant.parse("2026-11-14T10:00:00Z")
    )
);

assertTrue(
    service.isExpired(
        Instant.parse("2026-11-14T09:59:59.999Z")
    )
);
```

### 47.1. Precision Note

BSON Date stores milliseconds since the Unix epoch. If domain logic tracks nanoseconds, agree on rounding/truncation to milliseconds before comparing against persisted dates.

### 47.2. Server Clock Is Separate

A Java `Clock` never changes the MongoDB TTL monitor's wall clock. TTL integration tests use clearly past or future timestamps so system clocks never need adjustment.

---

## 48. Avoiding Common Sources of Async Test Flakiness

Common anti-patterns:

1. Using `Thread.sleep(100)` instead of conditions.
2. Not waiting for index builds to finish.
3. Sharing databases/collections across parallel tests.
4. Querying secondaries when asserting primary state.
5. Choosing Dates only milliseconds away from now.
6. Not waiting for worker/subscriber readiness before publishing.
7. Depending on thread scheduling order between two threads.
8. Reusing identical document IDs across tests.
9. Failing to clean up jobs/threads after failures.
10. Mixing unique indexes, TTL, and external retries into one tangled test.
11. Timeouts shorter than the TTL monitor cycle.
12. Excessively long timeouts that hide bugs for minutes.
13. Waiting for a side effect while the worker is actually stopped.
14. Omitting correlation IDs from logs.
15. Using mocks to draw conclusions about MongoDB server behavior.

### 48.1. Test Deterministically First

Whenever possible, push time math and state transitions into pure functions and unit test them. Reserve integration tests strictly for truly asynchronous or DB-dependent behavior.

---

## 49. Diagnosing TTL Integration Test Timeouts

Suppose an expired document remains after three minutes.

Check in order:

1. Is the test connected to the right URI/database/collection?
2. Does `getIndexes()` show the right key and TTL option?
3. Is `expiresAt` truly a BSON Date?
4. Is the Date genuinely in the past relative to the server clock?
5. Is `expireAfterSeconds` in **seconds**, not milliseconds?
6. Is the collection a time-series collection with bucket semantics?
7. Does MongoDB have a PRIMARY with the TTL monitor running?
8. Did read preference accidentally target a secondary?
9. Is there a huge TTL backlog from other tests?
10. Did index creation succeed before the insert?
11. Is server-side `metrics.ttl.passes` incrementing?
12. Is `deletedDocuments` incrementing (diagnostic only)?
13. Did a migration or index modification conflict?
14. Did another test re-insert the same `_id`?
15. Did an external cleanup worker interfere?
16. Is the Docker host or CI starved of IOPS/CPU?

### 49.1. Never Fix Flakes with Infinite Timeouts

If every TTL test takes 10 minutes on a tiny collection and keeps timing out, investigate the monitor and fixture before raising timeouts further.

---

## 50. Diagnosing Unique Index Test Failures

Common causes:

- Index was never created or failed to build due to existing duplicates.
- Test hit duplicate `_id` instead of the protected field.
- Index is compound, and the test omitted part of the key.
- Index is sparse/partial, and the document did not match the filter.
- Test collation does not match index collation.
- Shared test collection retained stale documents.
- Sharded cluster rejects that index specification.
- Writes use mismatched `w`/acknowledgment policies.
- Retry logic swallowed duplicate-key and reported false success.
- BulkWrite threw a different exception than `MongoWriteException`.
- Fixture built the index after workers had already started.

### 50.1. Inspect Metadata, Not Just Exception Text

```javascript
db.accounts.getIndexes();
```

Verify:

- `key`.
- `unique`.
- `partialFilterExpression`.
- `sparse`.
- `collation`.
- `name`.

---

## 51. Testing Retries and Idempotency Goes Beyond Request Counting

A job may be delivered multiple times. Verify:

- No extra record is created for the same business key.
- External payments are never sent twice.
- Two `COMPLETED` events are never emitted for one operation.
- Retry counts obey policy.
- Duplicate calls record idempotent success or domain conflict appropriately.
- Final state is queryable.
- Resources/leases are not held indefinitely after timeouts.

### 51.1. Unique Indexes Do Not Protect All Side Effects

A unique index on `eventId` prevents duplicate MongoDB writes, yet cannot stop a second email if the application calls the email service **before** writing the inbox marker. Integration tests must simulate real failure points in sequence.

---

## 52. Observability for Asynchronous Tests

To make failures easy to triage, log:

```text
testCaseId
collection namespace
document _id / correlationId
index name/key/options
event createdAt / expiresAt
observed state during polls
worker attempt count
last poll timestamp
deadline
MongoDB server version/topology
TTL passes/deletedDocuments if available
```

### 52.1. Avoid Logging Secrets

When testing tokens or OTPs, log hashes or correlation IDs—never raw verification codes or personal information.

### 52.2. Do Not Poll `serverStatus` Every 10 ms

Monitoring queries carry cost and require privileges. Collect metrics on timeout or at modest intervals.

### 52.3. The Target Poll Condition Matters Most

A TTL test can log five server metrics and still fail if it forgets to assert the **test's own document** was deleted.

---

## 53. Using `@Timeout` with JUnit

Set an overall test timeout to prevent hanging suites:

```java
@Tag("slow-ttl")
@Timeout(value = 4, unit = TimeUnit.MINUTES)
@Test
void ttlEventuallyDeletes() {
    // Awaitility deadline 3 minutes.
}
```

Notes:

- JUnit's `@Timeout` and Awaitility's timeout operate at different scopes.
- Thread interruption can occur on blocked calls; ensure cleanup uses `finally`/try-with-resources.
- Never set JUnit's timeout **shorter** than Awaitility's deadline plus container/fixture startup overhead.

### 53.1. Never Use a 1-Minute Timeout for a 60-Second TTL

If container startup and index builds take several seconds and the TTL monitor waits nearly 60 seconds, a 1-minute total budget can fail even when the server is completely healthy.

---

## 54. `await().untilAsserted()` and Timeout Diagnostics

Background job test example:

```java
await()
    .atMost(Duration.ofSeconds(30))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        Document job = jobs.find(eq("_id", jobId)).first();

        assertNotNull(job);
        assertEquals("COMPLETED", job.getString("state"));
        assertEquals(0, job.getInteger("errorCount", 0));
    });
```

On deadline expiration, the failure pinpoints which assertion did not pass.

### 54.1. Beware Poll Exceptions

Transient network errors during polling can be handled differently by Awaitility than assertion failures. Never blanket-ignore all exceptions if a test ought to fail when the DB is unreachable; ignore only exceptions **genuinely classified as transient** per policy.

### 54.2. Capture Diagnostics at Timeout

When a timeout hits, inspect documents/job state/metrics per permissions and attach them to CI artifacts (stripped of secrets). Never downgrade a test failure to a warning just to keep the build green.

---

## 55. Eventual Deletion Tests Masked by Another Job

Suppose a test runs:

```java
await().until(() -> codes.find(eq("_id", id)).first() == null);
```

while an application cleanup scheduler also deletes expired documents.

The test passes even if the TTL index is broken.

### 55.1. How to Isolate

- Run TTL integration tests in a namespace cleaned solely by the MongoDB TTL monitor.
- Disable application cleanup workers against the test collection.
- Verify TTL index metadata and BSON Dates.
- Inspect TTL metrics when diagnosing.
- Test application cleanup workers separately.

### 55.2. Never Run Both Mechanisms and Claim Each Was Proven

If the goal is testing TTL, the fixture must guarantee exclusive ownership: no other background worker may delete the same records.

---

## 56. Race Between TTL and Application Reads

Scenario:

```text
10:00:00 Token expires.
10:00:01 User submits token.
10:00:02 TTL has not deleted the document.
```

If the application checks only whether the token exists, a user can redeem an expired token.

Tests should verify:

1. Insert a token with `expiresAt` in the past.
2. Call the verification API **immediately**, without waiting for TTL.
3. Expect an expired/invalid response.
4. In a separate TTL integration test, verify the token is eventually swept.
5. If single-use, test two concurrent redeems and verify at most one succeeds.

### 56.1. Atomic Single-Use Consumption

A common design uses `findOneAndDelete` or a conditional update filtering `expiresAt > now` and an unused state when appropriate for the business/security model. Concurrent tests must prove two redeems can never both succeed.

### 56.2. TTL Does Not Provide Atomicity

TTL only performs cleanup; it does not provide transactional “consume exactly once” guarantees. These are two separate concerns.

---

## 57. Testing Concurrent Token Consumption

Domain example where each code can be redeemed once:

```text
Request A            Request B
    |                    |
find token             find token
    |                    |
redeem?                redeem?
```

If both requests simply `find` then update, a race lets both succeed.

An atomic operation:

```java
Document consumed =
    codes.findOneAndDelete(
        Filters.and(
            Filters.eq("_id", codeId),
            Filters.gt("expiresAt", new Date())
        )
    );
```

For the same `_id`, one request deletes and receives the document, while the other receives `null`. Concurrent tests verify **exactly one** succeeds.

### 57.1. Notes

- Never expose raw OTPs in logs or assertions.
- Production filters may also require `accountId`, hash, and security state.
- If redemption triggers external side effects, idempotency is still needed.
- Account for clock skew or rely on server-side time rules when clients supply timestamps.
- The TTL monitor might sweep an already-expired token before either request arrives; that is valid behavior.

---

## 58. Test Data Setup for TTL and Unique Indexes Together

An integration test combining unique and TTL indexes:

```javascript
db.oneTimeCodes.createIndex(
  { accountId: 1, purpose: 1 },
  {
    unique: true,
    name: "uq_account_purpose"
  }
);

db.oneTimeCodes.createIndex(
  { expiresAt: 1 },
  {
    expireAfterSeconds: 0,
    name: "ttl_expires_at"
  }
);
```

### 58.1. Understanding Both Indexes Together

- The unique index forbids **two documents with the same `accountId`/`purpose` at the same time**, regardless of whether `expiresAt` has passed.
- The TTL index cleans up expired documents asynchronously, **not instantaneously**.
- Consequently, issuing a new code for the same `accountId`/`purpose` before the TTL monitor sweeps the old one can trigger `E11000`.

### 58.2. This Is a Real Business Race

Assuming “the old code expired so the unique key is free” causes intermittent production failures.

Design options:

1. Update/upsert **the same document** to reissue a code, replacing `expiresAt`.
2. Conditionally delete the old code before inserting a new one, accounting for concurrency.
3. Include a generation ID in the business key, allowing only one active code via constraints.
4. Use a partial unique index on `active` and manage transitions atomically where appropriate.
5. Maintain a single record with a conditionally updated version/nonce.

### 58.3. Required Test Cases

- Initial code creation.
- Reissue immediately after logical expiration before TTL cleanup runs.
- Two concurrent code-issue requests.
- Old code cannot be redeemed after expiration.
- New code works.
- TTL eventually cleans up expired records per policy.

---

## 59. Comprehensive Testing Matrix

| Case | Setup | Action | Expected |
| --- | --- | --- | --- |
| Unique insert | Index ready, key A | Insert key A twice | E11000 |
| Unique update | Two keys A/B | Update B→A | E11000; B unchanged |
| Compound unique | T1/A exists | Insert T2/A | Success |
| Compound duplicate | T1/A exists | Insert T1/A | E11000 |
| Single unique missing | One doc missing field | Second doc missing field | Duplicate |
| Sparse unique missing | Two docs missing field | Insert both | Success |
| Sparse explicit null | One null exists | Insert another null | Duplicate |
| Partial unique | Only active indexed | Inactive duplicate | Success |
| Partial promotion | Inactive duplicate | Set active:true | Duplicate |
| Case-insensitive unique | Collation strength 2 | Differing case | Duplicate |
| Multikey unique | Duplicate in one doc | Insert one doc | Succeeds |
| Multikey across docs | Alias A exists | Another doc with alias A | Duplicate |
| Index build duplicate | Data has duplicates | Create unique index | Build fails |
| Concurrent insert | Two writers, same key | Barrier start | One winner |
| TTL expired | Past Date | Wait/poll | Eventually absent |
| TTL future | Far-future Date | Observe | Remains during window |
| TTL wrong type | String Date | Wait | Not deleted by TTL |
| TTL missing | Missing field | Wait | Not deleted by TTL |
| TTL array | Two Date values | Wait | Expires per earliest Date |
| TTL + unique | Old expired, not yet swept | Insert same unique key | Can throw E11000 |
| Worker eventual | Job PENDING | Trigger processing | Eventually COMPLETED |
| Worker failure | Dependency fails | Trigger | FAILED/RETRY per policy |
| Worker duplicate | Same event sent twice | Retry | No duplicate effect |
| Change stream | Subscriber READY | Insert | Event eventually arrives |
| Secondary read | Primary write | Read secondary | Eventually visible |
| Token one-time | Two redeem requests | Concurrent | One winner |
| Cursor/listener cancel | Job running | Cancel | Resources cleaned up |
| Test isolation | Two parallel tests | Same suite | Zero interference |

---

## 60. Exercise 1: Why Is Check-Then-Insert Wrong?

Code:

```java
if (accounts.find(eq("email", email)).first() == null) {
    accounts.insertOne(
        new Document("email", email)
    );
}
```

Two requests with the same email execute concurrently.

**Question:** Why can duplicates be created?

**Answer:** Both requests can read “not found” before either inserts. Concurrency tests must include a real **unique index** and assert one winner and one duplicate-key failure.

---

## 61. Exercise 2: Unique Index on Optional Email

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

Two users lack the `email` field.

**Answer:** With a non-sparse single-field unique index, both produce the same null index key and cannot coexist. If email is optional in the domain, consider a partial unique index on string emails.

---

## 62. Exercise 3: Sparse Unique with Null

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  { sparse: true, unique: true }
);
```

Two documents have `email: null`.

**Answer:** Sparse skips missing fields, yet explicit `null` is still indexed; two nulls collide on key and are rejected.

---

## 63. Exercise 4: Partial Unique for Active Users

Index:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: { active: true }
  }
);
```

User A is inactive and User B is active with the same email.

**Answer:** Both can coexist because only B is indexed. Updating A to `active: true` while B remains active fails with duplicate key.

---

## 64. Exercise 5: TTL After One Second

Set `expiresAt = now + 1s`, sleep 1500 ms, assert null.

**Answer:** Flaky. MongoDB's TTL monitor does not guarantee immediate deletion upon expiration; poll with a deadline and use a clearly past Date to test the monitor directly.

---

## 65. Exercise 6: What Unit Does the TTL Option Use?

```javascript
db.tokens.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 600 }
);
```

**Answer:** The document becomes eligible 600 seconds (~10 minutes) after the BSON Date field, not 600 milliseconds.

---

## 66. Exercise 7: BSON Date or String?

Document:

```javascript
{ _id: "V1", expiresAt: "2026-11-14T10:00:00Z" }
```

**Answer:** `expiresAt` is a string; MongoDB TTL does not parse strings to expire documents. Fix application serialization and schema validation.

---

## 67. Exercise 8: TTL Expired Yet Token Remains in Collection

The business API finds the token and allows access.

**Answer:** Broken security model. The API must enforce `expiresAt > now` and single-use consumption; TTL handles cleanup only.

---

## 68. Exercise 9: Unique and TTL on the Same Collection

Unique on `{accountId: 1, purpose: 1}`, TTL on `expiresAt`. Old token expired; new token with the same key hits `E11000`.

**Answer:** TTL does not clean up instantaneously; the unique constraint still covers the lingering old document. Update/upsert the existing record or change the schema/issuance policy instead of relying on luck.

---

## 69. Exercise 10: TTL on a Replica Set

Primary deleted the token, yet a `secondaryPreferred` query still sees it.

**Answer:** Likely replication lag. Basic TTL tests should read from the primary; test secondary consistency separately.

---

## 70. Exercise 11: Concurrent Winners

Two threads insert the same unique key; the test expects thread A to always succeed.

**Answer:** Flaky due to thread scheduling. Assert only that exactly one write succeeds and one hits duplicate key, regardless of which thread wins.

---

## 71. Exercise 12: Index Build on Duplicate Data

The collection already contains two duplicate emails, then runs `createIndex(...unique: true)`.

**Answer:** Index build fails upon detecting duplicates. Never assume the constraint is active.

---

## 72. Exercise 13: Async Worker

A job typically finishes in 200 ms. The test sleeps 250 ms and asserts completed.

**Answer:** Unstable under CI load. Poll by job ID within a deadline based on SLO/test budget.

---

## 73. Exercise 14: Polling with Side Effects

A test invokes `sendEvent()` inside every poll iteration.

**Answer:** Wrong. Polling must be a read-only condition while the trigger executes once. Otherwise the test itself generates duplicate events.

---

## 74. Exercise 15: Testing Zero Duplicate Side Effects

At second 1, `count == 1`, so the test passes. A worker retries at second 5, making `count == 2`.

**Answer:** A single instantaneous assertion never proves “never duplicates.” Verify idempotency invariants across an observation window covering the retry schedule.

---

## 75. Exercise 16: Change Stream Subscribe Race

The test starts the consumer asynchronously and inserts immediately. The consumer misses the event.

**Answer:** Wait until the consumer signals READY before publishing; use correlation IDs and poll for the matching event.

---

## 76. Exercise 17: Schema Validation and TTL

Documents missing `expiresAt` stick around indefinitely, and the team assumes TTL is broken.

**Answer:** TTL never deletes documents lacking a Date field; tests must verify BSON types, and a schema validator should enforce presence and type.

---

## 77. Exercise 18: Partial TTL in Time-Series

One measurement expired, yet its bucket contains newer measurements.

**Answer:** Time-series TTL expires whole buckets based on bucket granularity/expiration, never deleting individual measurements early.

---

## 78. Exercise 19: Testing with Mocked MongoDB

A mock returns `E11000` on duplicate email.

**Answer:** Proves only application error handling, not that the unique index exists and is enforced by real MongoDB. An integration test is needed.

---

## 79. Exercise 20: Persistent CI TTL Flakes

TTL tests keep timing out despite past Dates.

**Answer:** Check the TTL monitor, primary status, index metadata, test isolation, Docker CPU/IOPS, and deadlines before blindly raising timeouts.

---

## 80. Pre-Production Testing Checklist

### Unique Index

- [ ] Index created with the right key and `unique` option.
- [ ] Index build finishes before test writes begin.
- [ ] Duplicate inserts return error code 11000.
- [ ] Updates creating duplicates are blocked and leave the original document intact.
- [ ] Compound unique tests include cross-tenant cases.
- [ ] Missing/null behavior matches domain rules.
- [ ] Sparse/partial filters tested for both matching and non-matching cases.
- [ ] Collation/canonicalization tested.
- [ ] Multikey semantics understood properly.
- [ ] Index build fails when pre-existing duplicates exist.
- [ ] Concurrent inserts produce exactly one winner.
- [ ] Bulk partial successes handled properly.
- [ ] Upsert/race paths covered by an idempotency policy.
- [ ] Sharded uniqueness satisfies shard-key prefix constraints.

### TTL

- [ ] `expiresAt`/`createdAt` stored as BSON Date.
- [ ] Single-field TTL index configured with the right options.
- [ ] `expireAfterSeconds` specified in seconds.
- [ ] Clearly past Dates used for E2E TTL tests.
- [ ] Deadline exceeds monitor interval with headroom.
- [ ] Polling used instead of fixed sleeps.
- [ ] Future-dated records remain intact throughout the observation window.
- [ ] Missing/null/wrong-type fields tested.
- [ ] Arrays tested per earliest-Date behavior.
- [ ] Time-series bucket semantics tested separately.
- [ ] Primary vs secondary TTL read behavior checked.
- [ ] TTL metrics used for diagnostics, not as replacements for document assertions.
- [ ] Security/business expiration tested independently.
- [ ] TTL not mistaken for instant release of unique keys.

### Async Behavior

- [ ] Correlation ID or unique test ID present.
- [ ] Trigger once, poll read-only.
- [ ] Wait for consumer/worker readiness before emitting events.
- [ ] Bounded waits and informative failure messages.
- [ ] Zero reliance on specific thread scheduling.
- [ ] Retries and duplicate events verified idempotent.
- [ ] Partial failures tested.
- [ ] Explicit cancellation and cleanup.
- [ ] Test data isolated and parallelism bounded.
- [ ] Never substitute mocks for server integration.
- [ ] Clear unit/integration/end-to-end separation.
- [ ] Never confuse eventually-complete with immediately-complete.
- [ ] Never use one snapshot count to prove “never.”
- [ ] Diagnostics captured on CI timeouts.
- [ ] Never touch production namespaces directly.

---

## 81. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “Unique indexes are checked by a scheduled job.” | Uniqueness is enforced synchronously in write/index state, not via TTL-like background cleanup. |
| “Querying before inserting prevents duplicates.” | Concurrent writers still race; a unique index is required. |
| “Both threads must win or both lose.” | With the same unique key and a ready index, one succeeds and one hits duplicate key. |
| “Declaring a unique index in code means it exists in the DB.” | Migrations/fixtures must actually build the index successfully. |
| “E11000 always means email collided.” | It could be `_id` or another index; inspect the key/index. |
| “Sparse unique skips all nulls.” | Sparse skips missing fields; explicit `null` is still indexed. |
| “Partial unique applies even to non-matching documents.” | Only documents matching the filter expression are constrained. |
| “Compound unique means each field is individually unique.” | The constraint applies to the **tuple** of indexed values. |
| “Duplicate elements inside one document's array violate unique multikey.” | Not automatically; uniqueness applies across documents by index keys. |
| “Creating a unique index on dirty data cleans duplicates.” | The build fails; MongoDB never auto-deletes duplicate records. |
| “Unique indexes on sharded clusters match replica sets completely.” | Sharded clusters impose shard-key prefix and index-type restrictions. |
| “TTL deletes at the exact second of `expiresAt`.” | Cleanup runs asynchronously in the background with delay. |
| “A 60-second TTL means waiting 60 seconds and asserting.” | The monitor has scheduling/backlog latency; use polling. |
| “An ISO string works in a TTL field.” | Requires BSON Date or an array of Dates. |
| “TTL deletes documents missing the Date field.” | No. |
| “`expireAfterSeconds` is in milliseconds.” | It is in seconds. |
| “Compound TTL works normally.” | Standard TTL supports single-field indexes only. |
| “TTL runs deletes independently on every secondary.” | Primary deletes; secondaries replicate. |
| “If the document still exists, the token is not expired.” | Logical expiration differs from physical cleanup. |
| “BSON Date uses local timezone.” | Dates store UTC instants; UI formatting is separate. |
| “Time-series TTL deletes individual measurements on time.” | Deletion follows bucket semantics. |
| “Mocks can prove the TTL monitor runs.” | Requires real MongoDB. |
| “Sleeping long enough makes async tests deterministic.” | Still unreliable under variable load. |
| “You can poll by re-triggering the write.” | Polling must be read-only. |
| “One-time success means duplicates never happen.” | Requires invariants/idempotency and an observation window. |
| “Starting a Change Stream listener means the consumer is ready.” | Needs an explicit readiness barrier. |
| “Reading a secondary right after a primary write always sees it.” | Subject to replication lag and read concern settings. |
| “Raising timeouts fixes all flakes.” | Must fix test isolation, setup, and root causes. |
| “Unique + TTL means the unique key frees up upon expiration.” | No; the lingering document still occupies the key. |

---

## 82. Official MongoDB References

1. [Unique Indexes and Duplicate Values — MongoDB Manual](https://www.mongodb.com/docs/manual/core/index-unique/) — unique constraints, null/missing, compound, multikey, and sharded restrictions.
2. [Unique Indexes and Schema Validation](https://www.mongodb.com/docs/manual/tutorial/unique-indexes-schema-validation/) — compound/missing scenarios and partial uniqueness.
3. [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — distinguishing missing from explicit null.
4. [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — filter expressions and unique scope.
5. [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — index setup, Dates, TTL monitor scheduling, and restrictions.
6. [Set up Automatic Removal for Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/) — bucket granularity and cleanup.
7. [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — index builds and commit quorum.
8. [Create Indexes — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/) — `IndexOptions` and unique exceptions.
9. [CRUD Insert — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/insert/) — insert operations and errors.
10. [Bulk Write — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — ordered/unordered execution and partial failures.
11. [serverStatus](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — `metrics.ttl` and other counters.
12. [Sharded Cluster Unique Constraints](https://www.mongodb.com/docs/manual/tutorial/unique-constraints-on-arbitrary-fields/) — designing uniqueness across shards.
13. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — running real MongoDB in integration tests.
14. [Awaitility Documentation](https://github.com/awaitility/awaitility/wiki/Usage) — deadline polling, `until`/`untilAsserted`.
15. [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — lifecycle, `assertThrows`, timeouts, and test tags.

Details regarding time-series partial TTL, TTL monitor metrics, index builds, driver exceptions, and Testcontainers package names can vary by version. When applying these patterns, consult the documentation matching your exact MongoDB Server, Java driver, Testcontainers, Awaitility, and JUnit versions.

---

## 83. Conclusion

**Testing unique indexes** must prove **data integrity enforced by MongoDB**: duplicate keys cannot slip through even under concurrency. Test not only inserts, but also updates, compound keys, null/missing, partial/sparse indexes, collation, and index readiness.

**Testing TTL** must embrace **asynchronous deletion**: expiration timestamps merely mark documents eligible, while the TTL monitor sweeps them later. Use BSON Dates, proper indexes, deadline-bounded polling, and ID-specific queries; never rely on short sleeps or treat TTL as a substitute for business expiration checks.

**Testing async behaviors** requires checking convergence, timeouts, retry/idempotency, data isolation, and side effects. Read-only polling and readiness barriers make tests far more reliable than arbitrary delays.

Finally, never overlook how the two features interact: **a logically expired document not yet swept by TTL still occupies its unique key**. Application design must handle this via atomic updates, idempotency, or an appropriate data model.

**A trustworthy test never tries to force an asynchronous system to act “instantaneously”; it verifies the exact guarantees MongoDB and the application provide, with explicit observation deadlines and isolated test data.**
