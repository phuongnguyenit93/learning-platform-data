# Unique Index Constraints in MongoDB Sharded Collections

## 1. Problem Statement

A multi-tenant application stores accounts in MongoDB. Initially, the collection is unsharded and uses a unique index to prevent duplicate emails within each tenant:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
```

Later, the system needs to scale horizontally via **sharding** to distribute data across multiple shards. Can the unique constraint stay as is? What if we shard by `tenantId`? What if we shard by `regionId` or `createdAt`? If email must be unique **system-wide**, rather than only per tenant, what needs to change in the design?

These questions are not only about performance—they are about **data correctness**. MongoDB cannot check arbitrary duplicate keys across multiple shards the same way it checks an unsharded collection. Unique indexes on sharded collections must obey **shard key** rules.

After this lesson, you will be able to:

1. Explain why enforcing uniqueness across a sharded cluster is harder than on a single node.
2. Identify the requirement that **the entire shard key must be a prefix of a unique index** in ranged sharding.
3. Distinguish uniqueness on a compound key from uniqueness on each individual component.
4. Understand the scope limitation of the `_id` index when `_id` is not the shard key.
5. Contrast unique ranged shard keys with hashed shard keys.
6. Design mechanisms to protect business keys outside the shard key.
7. Practice on `mongos`, inspect index metadata, and handle conflicts properly.

## 2. What Does a Unique Index Guarantee?

### 2.1. Unique Indexes

A unique index prevents documents from sharing the same index key within the scope where MongoDB enforces that constraint. For example:

```javascript
db.users.createIndex({ username: 1 }, { unique: true });
```

Once a document with `username: "minh"` exists, inserting another document with that value is rejected with a **duplicate key** error code `11000` (often displayed as `E11000`).

For a **compound unique index**:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
```

MongoDB forbids duplicating the **entire pair** `(tenantId, emailKey)`. It does not mean `tenantId` must be unique, nor does it mean `emailKey` must be unique across all tenants.

| `tenantId` | `emailKey` | Can Coexist? |
| --- | --- | --- |
| `T1` | `an@example.test` | First record is valid |
| `T1` | `binh@example.test` | Yes, different email |
| `T2` | `an@example.test` | Yes, different tenant |
| `T1` | `an@example.test` | No, key pair already exists |

**Key point:** choosing the fields in a unique key defines the scope of a business rule. An index being syntactically valid does not prove it matches the product's intended invariant.

### 2.2. Do Not Confuse Uniqueness with Other Constraints

A unique index does not guarantee:

- That the field is a syntactically valid email.
- That the document was created by a user authorized for that tenant.
- That a referenced ID points to an existing target document.
- That status transitions follow valid workflow rules.
- That two requests with the same email in different letter cases are normalized identically, unless the application or collation handles it.

MongoDB schema validation, application logic, authorization, and transactions address other concerns; they work alongside unique indexes rather than replacing them.

## 3. What Does Sharding Change?

### 3.1. Shard Keys and Data Routing

A MongoDB sharded cluster distributes documents across multiple shards, and applications typically send requests through `mongos`:

```text
Application / mongosh
        |
        v
      mongos
        |
        +----------+----------+
        |          |          |
        v          v          v
      Shard A    Shard B    Shard C
```

A **shard key** is the field or combination of fields MongoDB uses to partition and route data. For instance:

```javascript
{ tenantId: 1 }
```

MongoDB splits the shard key's value space into chunks/ranges and distributes chunks across shards. Chunk placement can shift during balancing. Nevertheless, every document with a given shard key value is routed to its corresponding key range.

Do not assume a tenant is permanently pinned to one physical server; the balancer can move chunks. Consistent routing by shard key is the key property.

### 3.2. Why Is Uniqueness on a Non-Shard-Key Field Hard to Enforce?

Suppose the shard key is `{tenantId:1}`, yet the application wants `emailKey` unique **cluster-wide**:

```javascript
{ tenantId: "T1", emailKey: "an@example.test" }
{ tenantId: "T2", emailKey: "an@example.test" }
```

Two documents with different tenants can reside on different shards. A local unique index on `emailKey` on one shard cannot automatically detect values stored on another shard.

If the index is instead `{tenantId:1,emailKey:1}`, any two documents sharing that **key pair** necessarily share the same `tenantId`; MongoDB can enforce uniqueness within the scope routed by the shard key. This is the rationale behind the shard-key-prefix rule.

## 4. The Shard Key Prefix Rule for Unique Indexes

For a **ranged sharded collection**, MongoDB can enforce uniqueness across shards when:

1. The unique index is directly on the shard key itself.
2. A compound unique index has **the entire shard key as its prefix**.
3. The default `_id` index still exists, though it carries a **scope exception** if `_id` is not the shard key.

MongoDB forbids creating an arbitrary unique index lacking the shard key prefix on a range-sharded collection. If an unsharded collection has an incompatible unique index, sharding that collection can also be rejected.

### 4.1. Single-Field Shard Key Case

With shard key:

```javascript
{ tenantId: 1 }
```

| Desired Index with `unique:true` | Supported? | What It Protects |
| --- | --- | --- |
| `{tenantId:1}` | Yes | At most one document per tenant; usually too strict |
| `{tenantId:1,emailKey:1}` | Yes | One email per tenant |
| `{tenantId:1,externalOrderId:1}` | Yes | One external order ID per tenant |
| `{emailKey:1}` | No, violates prefix rule | Missing shard key |
| `{emailKey:1,tenantId:1}` | No | Includes shard key, **not at the start** |
| `{status:1,tenantId:1}` | No | Shard key is not the prefix |

**Field order is mandatory.** Having `tenantId` appear somewhere in the index is not enough; it must form the contiguous leading prefix.

### 4.2. Multi-Field Shard Key

With shard key:

```javascript
{ tenantId: 1, monthBucket: 1 }
```

prefix-compatible indexes:

```javascript
{ tenantId: 1, monthBucket: 1 }
{ tenantId: 1, monthBucket: 1, orderId: 1 }
{ tenantId: 1, monthBucket: 1, customerId: 1 }
```

Indexes that do **not** contain the **entire** shard key as their leading prefix:

```javascript
{ tenantId: 1 }
{ tenantId: 1, orderId: 1 }
{ monthBucket: 1, tenantId: 1, orderId: 1 }
{ tenantId: 1, orderId: 1, monthBucket: 1 }
{ orderId: 1 }
```

`{tenantId,orderId}` starts with `tenantId`, yet omits `monthBucket` from the shard key. It is not a valid unique index for a sharded collection with shard key `{tenantId,monthBucket}` under these rules.

### 4.3. Uniqueness Applies to the **Entire** Combination

Suppose the valid index is:

```javascript
{ tenantId: 1, monthBucket: 1, orderId: 1 }
```

All three documents below can coexist:

```javascript
{ tenantId: "T1", monthBucket: 202610, orderId: "O-10" }
{ tenantId: "T1", monthBucket: 202611, orderId: "O-10" }
{ tenantId: "T2", monthBucket: 202611, orderId: "O-10" }
```

They do not collide on the full key. If business rules require each `orderId` to appear **only once per tenant across all months**, this unique index **does not enforce that rule**. Including `monthBucket` in the unique key satisfies the shard-key-prefix rule while changing the protected business scope.

That is why shard key selection must consider **business uniqueness**, not just data balance.

## 5. Distinguishing a Unique Shard Key from a Unique Compound Index

### 5.1. Unique Only on the Tenant + Email Pair

If each tenant has many accounts, the shard key `{tenantId:1}` must not be unique. You can create a compound unique index:

```javascript
db.accounts.createIndex({ tenantId: 1 });

db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);

// Run through mongos on the exact namespace.
sh.shardCollection("shop.accounts", { tenantId: 1 });
```

The compound index ensures the tenant + email pair is unique. It **does not restrict each tenant to one document**.

### 5.2. When the Shard Key Values Themselves Must Be Unique

In a configuration collection, each region has exactly one record. Only then might you want uniqueness on `regionId` itself:

```javascript
db.regionConfig.createIndex(
  { regionId: 1 },
  { unique: true }
);

// The third parameter of sh.shardCollection requests a unique shard key.
sh.shardCollection(
  "shop.regionConfig",
  { regionId: 1 },
  true
);
```

When requesting a unique shard key with `true`:

- If the collection is empty, MongoDB can create the unique index on the shard key if it does not exist yet.
- If the collection already has data, the unique index on the shard key must exist before sharding.
- If a non-unique index backing the shard key already exists, the operation can fail.
- A unique index `{regionId:1,emailKey:1}` **does not replace** a primary unique index on `{regionId:1}`.

`shop.regionConfig` and `shop.accounts` are two distinct collections illustrating different business requirements. Never enable a unique shard key on an `accounts` collection where multiple users belong to the same tenant.

## 6. Important Exception for the Default `_id` Index

### 6.1. When `_id` Is Not the Shard Key

In an unsharded collection, `_id` is unique across the collection. However, **if a sharded collection has a shard key other than `_id`**, MongoDB enforces uniqueness of the default `_id` index **only within each shard**, not cluster-wide by default.

Example collection sharded by `{regionId:1}`:

```javascript
// May reside on Shard A:
{ _id: "ACCOUNT-1", regionId: "north", emailKey: "a@example.test" }

// May reside on Shard B:
{ _id: "ACCOUNT-1", regionId: "south", emailKey: "b@example.test" }
```

If records live on different shards, the local `_id` index does not prevent duplicate `_id` values across shards. This is **an explicitly documented caveat**, not a pattern you should deliberately generate in test data.

### 6.2. When `_id` Is the Shard Key

If the shard key is `{_id:1}`, documents with duplicate `_id` share the same shard key; routing allows enforcing uniqueness per supported rules.

However, if the shard key is `{tenantId:1,_id:1}`, a unique compound index on `{tenantId:1,_id:1}` only protects the **pair** tenant + ID. It does not make `_id` globally unique across tenants.

### 6.3. Application Responsibility for Generating IDs

When `_id` is not the shard key, MongoDB expects the application to generate IDs that avoid cross-shard collisions, such as standard `ObjectId`, UUIDs, or a managed distributed ID generator.

A properly generated `ObjectId` has negligible collision probability, yet that is a **property of the ID-generation strategy**, not a cluster-wide unique index guarantee on `_id` under a non-`_id` shard key.

If business logic needs a server-enforced absolute invariant for an identifier independent of the shard key, reconsider the shard key or use a registry/proxy collection as in Section 9.

## 7. Hashed Shard Keys and Uniqueness Limitations

### 7.1. Difference Between Ranged and Hashed Sharding

Ranged sharding uses shard key value ranges, e.g.:

```javascript
{ accountId: 1 }
```

Hashed sharding distributes by hash value:

```javascript
{ accountId: "hashed" }
```

Hashed sharding improves write distribution for monotonically increasing keys, yet **MongoDB does not allow unique constraints on hashed indexes** and does not allow enabling the unique shard key option with a hashed shard key.

A command like the following is **unsupported** and must not be used for configuration:

```javascript
db.accounts.createIndex(
  { accountId: "hashed" },
  { unique: true }
);
```

Hashing does not automatically enforce business-key uniqueness. When cluster-wide uniqueness is critical, evaluate an appropriate ranged shard key or a dedicated registry mechanism.

### 7.2. Choosing a Shard Key Is Not Only About Load Balancing

A solid shard key must be evaluated across multiple dimensions:

| Factor | Design Question |
| --- | --- |
| Distribution | Do shard key values spread data and write load evenly? |
| Query routing | Do critical queries include the shard key to target specific shards? |
| Uniqueness | Can required unique indexes contain the full shard key as a prefix? |
| Cardinality | Do too many records share a single shard key value? |
| Key mutability | Does the shard key change frequently during a record's lifecycle? |
| Scalability | As shards and data grow, will the rule remain viable? |
| Resharding | If the key changes in the future, will unique indexes remain valid? |

Never pick a hashed shard key just for write distribution while assuming MongoDB will still enforce every business unique key automatically.

## 8. Collation, `null`, and Missing Fields

### 8.1. Unique Indexes and Collation

Collation governs language-specific string comparison, letter case, and diacritics. For unique indexes on sharded collections, MongoDB documentation specifies **simple collation** requirements where collation applies to unique index keys.

Therefore, do not copy a case-insensitive unique index from an unsharded collection to a sharded collection without checking applicable restrictions.

A practical pattern is normalizing the business key in the application:

```javascript
{
  tenantId: "TENANT-A",
  emailDisplay: "An@Example.Test",
  emailKey: "an@example.test"
}
```

If the shard key is `{tenantId:1}`, the unique index:

```javascript
db.accounts.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    unique: true,
    collation: { locale: "simple" }
  }
);
```

protects the tenant + **normalized** email key pair. Normalization rules must be consistent across all writers; international emails, Unicode, and case-folding need explicit application policies.

### 8.2. Missing and Null

For unique indexes, a missing field can enter the index key as a `null` value under MongoDB rules. For instance, with unique `{tenantId:1,emailKey:1}`, multiple documents in the same tenant missing `emailKey` can collide on the tuple containing `null`.

Enforce checks at multiple layers:

- Application validates required business keys and rejects invalid empty placeholders.
- Collection validators require fields and appropriate BSON types.
- Unique indexes enforce uniqueness among indexed documents.
- Migration procedures audit legacy documents missing fields before enabling constraints.

Never treat a unique index as a substitute for input data validation.

### 8.3. Partial/Sparse Does Not Bypass the Shard-Key-Prefix Rule

A partial unique index enforces uniqueness only within documents matching its partial filter; a sparse index has its own entry scope. Even so, they are **not a shortcut** to create a unique index without the shard key prefix on a sharded collection.

If business logic needs "unique email among active accounts", design the unique scope, reactivation rules, shard key compatibility, and specific index limitations together. Test state transitions with real data.

## 9. When Global Uniqueness Is Needed on a Non-Shard-Key Field

### 9.1. Why Is `{tenantId,emailKey}` Insufficient?

Suppose `accounts` is sharded by `{tenantId:1}`, yet the product requires **no two accounts share the same email anywhere in the system**, even across different tenants.

```javascript
// Valid under shard-key-prefix rule, but scope is too narrow.
{ tenantId: 1, emailKey: 1 }
```

That index does not prevent the same email from appearing in both `T1` and `T2`. Creating a direct unique index `{emailKey:1}` violates the shard-key-prefix rule for this collection.

You must pick a different design—not merely reorder fields while leaving the business rule unmet.

### 9.2. Option 1: Redesign the Shard Key

If you can shard by `emailKey` (ranged) with a unique index on that key, MongoDB can enforce uniqueness directly. However, sharding by email may hinder tenant-scoped queries; evaluate:

- read/write frequency by tenant;
- value distribution and hotspots;
- ability to route queries to specific shards;
- resharding or migration costs;
- whether email stays immutable or changes often.

Change the shard key only after weighing all of these factors.

### 9.3. Option 2: Proxy or Registry Collection

MongoDB documents using a separate collection as a **registry** for a globally unique key when that key cannot be the main collection's shard key:

```text
              Application
                   |
           normalizedEmail
                   |
                   v
            +-------------+
            | emailKeys   |
            | unique _id  |
            +-------------+
                   |
             if key is valid
                   v
            +-------------+
            | accounts    |
            | sharded by  |
            | tenantId    |
            +-------------+
```

Example registry document:

```javascript
{
  _id: "an@example.test",
  accountId: ObjectId("66a000000000000000000001"),
  createdAt: ISODate("2026-11-14T01:00:00Z")
}
```

Main collection document:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  tenantId: "TENANT-A",
  emailKey: "an@example.test",
  displayName: "An"
}
```

If the registry is an **unsharded collection** in the same cluster, its default `_id` unique index protects emails in the registry. If the registry itself must be sharded, choose the registry's shard key so email uniqueness remains enforceable within the rules above.

### 9.4. Writes Across Both Collections Must Be Coordinated

Inserting into the registry first and the account second can leave an "orphaned" registry entry if the second write fails. Inserting the account first and the registry second can leave an account with an unregistered email.

If both collections live in the same transaction-capable MongoDB cluster, use a **multi-document transaction** so registering the key and creating the account either both commit or both roll back.

```javascript
// Node.js MongoDB driver - illustrates the write flow.
import { ObjectId } from "mongodb";

async function createAccount(client, database, input) {
  const session = client.startSession();
  const accountId = new ObjectId();

  try {
    await session.withTransaction(async () => {
      await database.collection("emailKeys").insertOne(
        {
          _id: input.emailKey,
          accountId,
          createdAt: new Date()
        },
        { session }
      );

      await database.collection("accounts").insertOne(
        {
          _id: accountId,
          tenantId: input.tenantId,
          emailKey: input.emailKey,
          displayName: input.displayName
        },
        { session }
      );
    });

    return accountId;
  } finally {
    await session.endSession();
  }
}
```

This example assumes `emailKeys` has an appropriate unique index (here `_id` on an unsharded collection), both collections reside in the same cluster, and the API layer has authenticated the tenant and normalized inputs.

In production:

1. If two requests register the same email concurrently, one receives `E11000` from the registry; map it to a business error rather than creating a duplicate account.
2. Transactions do not replace unique constraints; the unique index on the registry is what prevents duplicates.
3. Transaction callbacks can be retried by the driver on transient errors; never invoke external email/payment services inside the callback without idempotency/outbox safeguards.
4. Define rules for email changes, releasing old keys, soft deletes, email reuse, and conflict handling.
5. When a client retries a request that may have committed despite a lost response, use a business-level idempotency key.

### 9.5. Multiple Independent Unique Keys

If both email and phone number must be globally unique while the main collection is sharded by tenant, you may need multiple registry/proxy collections with appropriate indexes and shard keys for each key. A transaction coordinates writes across the registries and the main document.

This increases operational complexity; analyze uniqueness invariants at sharding design time rather than waiting until the system holds millions of documents.

## 10. Hands-On Practice with `mongosh` on a Sharded Cluster

**Prerequisites:** a test MongoDB sharded cluster, a URI to `mongos`, and privileges to create collections, indexes, and shard namespaces. A standalone `mongod` cannot substitute for a sharded cluster across this entire lab.

Run cluster-modifying commands only on environments you are authorized to administer. Sample database name: `mongo_unique_row165_lab`.

### 10.1. Verifying Connectivity

```bash
mongosh "mongodb://router.example.internal:27017/"
```

The URI above is a placeholder; replace it with your test environment's hostname, TLS, and authentication settings. Once connected:

```javascript
sh.status();
```

Inspect the shards and sharded cluster metadata. If you lack privileges or cannot reach `mongos`, stop before modifying configurations rather than running on another environment.

### 10.2. Creating the Collection and Compatible Unique Index

This example targets a **new database/collection**. Do not re-run `createCollection` or `shardCollection` if the namespace already exists with its own configuration:

```javascript
const lab = db.getSiblingDB("mongo_unique_row165_lab");

lab.createCollection("accounts_demo");
const accounts = lab.getCollection("accounts_demo");

// Index supporting the ranged shard key.
accounts.createIndex(
  { regionId: 1 },
  { name: "region_shard_key" }
);

// Only each regionId + emailKey pair is unique.
accounts.createIndex(
  { regionId: 1, emailKey: 1 },
  { unique: true, name: "uniq_region_email" }
);

printjson(accounts.getIndexes());

sh.shardCollection(
  "mongo_unique_row165_lab.accounts_demo",
  { regionId: 1 }
);
```

Do not pass the third parameter `true` to this `sh.shardCollection` call, because one region is allowed to hold many accounts; only the region + email pair must be unique.

### 10.3. Inserting Identical Emails in Two Regions

```javascript
const runId = "row165-" + new ObjectId().toHexString();
const regionNorth = runId + "-north";
const regionSouth = runId + "-south";

const inserted = accounts.insertMany([
  {
    runId,
    regionId: regionNorth,
    emailKey: "an@example.test",
    displayName: "An North"
  },
  {
    runId,
    regionId: regionNorth,
    emailKey: "binh@example.test",
    displayName: "Binh North"
  },
  {
    runId,
    regionId: regionSouth,
    emailKey: "an@example.test",
    displayName: "An South"
  }
]);

printjson(inserted.insertedIds);
printjson(accounts.find(
  { runId },
  { _id: 1, regionId: 1, emailKey: 1 }
).toArray());
```

Two documents sharing `emailKey: "an@example.test"` in different regions are permitted because the compound key does not collide.

### 10.4. Inserting a Duplicate in the Same Region

```javascript
try {
  accounts.insertOne({
    runId,
    regionId: regionNorth,
    emailKey: "an@example.test",
    displayName: "Duplicate record"
  });
  print("Unexpected: duplicate accepted");
} catch (error) {
  print("Error code: " + error.code);
  print("Error: " + error.message);
}
```

If the index was created and the collection is healthy, the expected error code is `11000`. If you see a different error, check permissions, connectivity, and metadata before drawing conclusions.

With only a few small documents, MongoDB may not yet split or distribute them across multiple shards. This example demonstrates sharded-collection uniqueness rules, not a chunk-balancing benchmark.

### 10.5. Inspecting Metadata and Cleaning Up Your Run's Data

```javascript
sh.status();
printjson(accounts.getIndexes());

print("north/an=" + accounts.countDocuments({
  regionId: regionNorth,
  emailKey: "an@example.test"
}));

print("database=" + lab.getName());
print("runId=" + runId);

const owned = accounts.find(
  { runId },
  { _id: 1, regionId: 1, runId: 1, emailKey: 1 }
).toArray();
printjson(owned);
```

After verifying each document belongs to **your own practice run**, delete by ID, full shard key, and `runId`:

```javascript
for (const doc of owned) {
  const result = accounts.deleteOne({
    _id: doc._id,
    regionId: doc.regionId,
    runId
  });
  print(doc.emailKey + ": deleted=" + result.deletedCount);
}

print("remaining=" + accounts.countDocuments({ runId }));
```

Never run `deleteMany({})`, `drop()`, or `dropDatabase()` in a shared environment. Deleting demo documents does not remove the collection, indexes, or sharding configuration; those resources require separate administrative cleanup.

## 11. Creating a Unique Index on an **Already-Sharded** Collection

### 11.1. Verify the Shard Key Before Creating

On a collection already sharded by `{tenantId:1}`, creating a unique index for external order IDs can be done via `mongos`:

```javascript
// First inspect metadata.
sh.status();

// Select the exact database and collection.
const inventory = db.getSiblingDB("inventory");
printjson(inventory.orders.getIndexes());

// Run only if the shard key is indeed {tenantId: 1} and data is eligible.
inventory.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uniq_tenant_external" }
);
```

A unique `{externalOrderId:1}` or `{externalOrderId:1,tenantId:1}` index **is not supported** for this shard key because it lacks the proper prefix.

### 11.2. Check for Duplicates Before Creating the Index

If the collection already contains duplicate keys, creating the unique index can fail. One exploratory check:

```javascript
inventory.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $limit: 20 }
]);
```

This is an **illustrative query**: in real systems, account for BSON types, collation, aggregation resource usage, concurrent writes, and full-dataset validation rather than assuming safety just because the first 20 groups are empty.

MongoDB documentation warns that when building an index on a sharded collection where one shard has duplicate data, some shards may build the index successfully while another fails, resulting in **inconsistent indexes across shards**. After DDL operations, verify cluster state and handle errors per operational runbooks rather than assuming a returned error automatically rolled back every shard to an identical index state.

### 11.3. Collections with an Existing Unique Index Prior to Sharding

If an unsharded collection has a unique index `{emailKey:1}` and you later try to shard by `{tenantId:1}`, that plan violates the prefix rule. Sharding will be rejected.

Do not drop the old unique index merely to make `shardCollection` succeed without another mechanism preserving correctness. Choose among:

- Narrowing uniqueness to tenant + email if business rules allow.
- Changing the shard key to align with the unique key that must be preserved.
- Using a registry/proxy collection to maintain global uniqueness.
- Keeping the collection unsharded if volume permits and simplicity outweighs sharding.

### 11.4. Metadata Consistency

With multiple shards and index builds/migrations, operators must verify metadata and index consistency using tools appropriate for their MongoDB version. MongoDB provides `checkMetadataConsistency` and related options in supported versions. Consult exact syntax and privilege requirements for your specific version rather than guessing from another environment.

## 12. Resharding Can Make Unique Indexes Incompatible

Suppose initially:

```javascript
// Old shard key:
{ tenantId: 1 }

// Existing unique index:
{ tenantId: 1, emailKey: 1 }
```

Operations wants to reshard the collection by:

```javascript
{ regionId: 1 }
```

The existing unique index `{tenantId,emailKey}` does not have the new shard key `regionId` as its prefix. MongoDB requires the new shard key to satisfy active unique index constraints. Hence resharding cannot be treated as a pure data-redistribution command ignoring invariants.

A resharding plan must check:

1. Which unique indexes currently exist?
2. Which business invariants do they protect?
3. Can those invariants still be expressed under the new shard key?
4. Do we need data migration, index changes, or a registry beforehand?
5. Is the application querying/writing using the old shard key?
6. Are the commands and sequence supported by our MongoDB version?

**The shard key is a long-term architectural decision**, affecting data, indexes, performance, and APIs.

## 13. Concurrent Writes, Upserts, and `E11000` Errors

### 13.1. Having a Unique Index Does Not Make Concurrent Requests Wait Nicely

If two requests concurrently register the same `{tenantId,username}`:

```javascript
db.users.updateOne(
  { tenantId: "TENANT-A", username: "an" },
  {
    $setOnInsert: {
      displayName: "An",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

A valid unique index on `{tenantId:1,username:1}` prevents two documents with the same key tuple. Still, a race between two upserts can result in one insert and one update/no-op, or one request receiving a duplicate-key error depending on execution timing.

The application must handle:

- `upsertedCount:1`: newly created.
- `matchedCount:1`: matching document already existed.
- `11000`: reconcile whether the expected business key/payload already exists or if there is a true conflict.
- Unknown-outcome network errors: reconcile using stable keys and idempotency/retry policies.

### 13.2. Do Not Mix Arbitrary Status Conditions into Upsert Filters

When transitioning a document from `PENDING` to `ACTIVE`, use a conditional update **without upsert**:

```javascript
db.users.updateOne(
  {
    tenantId: "TENANT-A",
    username: "an",
    status: "PENDING"
  },
  { $set: { status: "ACTIVE" } }
);
```

Adding `upsert:true` to a filter containing status means that if the document already moved to another status, the command will attempt to insert a brand-new document with the same unique key and hit `11000`. That is an update-flow design bug, not a flaw in the unique index.

### 13.3. Uniqueness Does Not Replace Authorization

Requests must obtain `tenantId` from the authenticated user context rather than trusting a client-supplied tenant. The unique index guards storage constraints; authorization policies ensure callers act only within their authorized tenant.

## 14. Design Decision Matrix

| Business Rule | Shard Key | Unique Index / Solution | Actual Enforced Uniqueness |
| --- | --- | --- | --- |
| Username unique per tenant | `{tenantId:1}` | `{tenantId:1,username:1}` unique | By `(tenantId, username)` pair |
| Email unique per region | `{regionId:1}` | `{regionId:1,emailKey:1}` unique | By `(regionId, email)` pair |
| One config per region | `{regionId:1}` | `{regionId:1}` unique | One document per region |
| Order ID unique per tenant, yet sharded by tenant + month | `{tenantId:1,monthBucket:1}` | `{tenantId,monthBucket,orderId}` is **insufficient** if IDs must not repeat across months | Unique only across all three fields |
| Email unique system-wide, accounts sharded by tenant | `{tenantId:1}` | Global registry/proxy or change shard key | Global via registry if implemented properly |
| `_id` must be unique system-wide when `_id` is not shard key | `{tenantId:1}` | ID generation strategy or registry/key change | Default `_id` index is unique per shard only |
| Data sharded by hashed key | `{accountId:"hashed"}` | Cannot create unique hashed index | Needs a separate constraint design if required |

Never confuse "syntactically valid index in MongoDB" with "index protecting the right business scope". Your design must satisfy **both**.

## 15. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Putting the shard key at the end of a unique index | Violates prefix rule | Put the full shard key first in exact order |
| Using unique `{tenantId,email}` to enforce global email uniqueness | Two tenants can still hold the same email | Use a registry or change the shard key |
| Two-field shard key with only the first field in the unique index | Missing full shard key | Include the full compound shard key prefix |
| Assuming default `_id` is always cluster-wide unique | Can collide across shards | Global ID generation strategy or registry |
| Trying `unique:true` on a hashed index | Unsupported configuration | Choose a different shard/index model |
| Thinking compound unique makes each individual field unique | Enforces a scope too broad or too narrow | Analyze the full compound key tuple |
| Failing to normalize `emailKey` | Case/Unicode variants create separate keys | Normalize consistently per policy |
| Querying existence first, then inserting | Race condition between concurrent requests | Enforce uniqueness at write time |
| Failing to check null/missing | Collisions or malformed key data | Schema validation and input rules |
| Building a unique index over duplicate data | Index build fails; shards can diverge | Audit, clean duplicates, verify consistency |
| Dropping a unique index just so sharding succeeds | Loses data invariant | Design an alternative safeguard first |
| Resharding while forgetting unique indexes | New shard key becomes incompatible | Plan migration and invariants together |
| Using transactions without a unique registry | Transactions alone do not create uniqueness | Place unique index properly + coordinate in transaction |

## 16. Exercises

### Exercise A: Identify Valid Indexes

An `orders` collection is sharded by:

```javascript
{ tenantId: 1, quarter: 1 }
```

Consider the following indexes:

```javascript
// A
{ tenantId: 1, quarter: 1, orderId: 1 }
// B
{ tenantId: 1, orderId: 1 }
// C
{ quarter: 1, tenantId: 1, orderId: 1 }
// D
{ tenantId: 1, quarter: 1 }
// E
{ orderId: 1 }
```

Identify which indexes have **the entire shard key as a prefix**, and which do not. If `orderId` must be unique within a tenant **across all quarters**, why is A still insufficient?

Hint: A and D have valid prefixes. A is unique across `(tenantId, quarter, orderId)`; the same ID can still be reused in a different quarter without colliding on the full key.

### Exercise B: Analyze `_id`

A collection is sharded by `{regionId:1}`, and each region independently assigns sequential IDs starting from 1. Answer:

1. Within what scope does the default `_id` index block duplicates?
2. Why can two regions generate the same `_id`?
3. How should you change the ID generation strategy or uniqueness model to avoid errors?

### Exercise C: Globally Unique Email

An account system is sharded by tenant, yet emails must be unique application-wide. Sketch:

```text
Client -> API -> Normalize -> Registry -> Accounts
```

In your design, explain:

- Which unique key does the registry hold?
- What error can two concurrent requests with the same email trigger?
- Why must the registry and account writes be coordinated in a transaction?
- When changing an email or deleting an account, how is the old key handled?
- Why does unique `{tenantId,emailKey}` fail global uniqueness?

### Exercise D: Preparing to Shard an Existing Collection

An unsharded collection currently has a unique index `{emailKey:1}`. Operations wants to shard by `{regionId:1}`. Explain why this plan has a conflict, and propose at least two ways to preserve the email uniqueness invariant.

## 17. References

When administering real clusters, consult guides **for your exact MongoDB version**:

- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard key prefix rules and `_id` exceptions.
- [Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/) — indexes supporting shard keys.
- [Create a Unique Index on Existing Sharded Collection](https://www.mongodb.com/docs/manual/tutorial/create-unique-index-on-sharded-collection/) — adding unique indexes after sharding.
- [Enforce Uniqueness on the Shard Key Values](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-shard-key-values/) — uniqueness on the shard key itself.
- [Enforce Uniqueness on a Field That Is Not the Shard Key](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-non-shard-key-field/) — using registry/proxy collections.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness concepts, compound keys, collation, and missing fields.

## 18. Conclusion

On a **ranged sharded collection**, MongoDB enforces uniqueness across shards when a unique index is on the shard key itself or includes **the entire shard key as its prefix**. Compound index uniqueness applies to the **entire key combination**, not to individual fields. The default `_id` index does not guarantee cluster-wide uniqueness when `_id` is not the shard key, and hashed indexes do not support unique constraints.

If a business key requires system-wide uniqueness yet cannot match the shard key, revisit the sharding design or use a **registry/proxy collection** with enforced constraints, combined with transactions and idempotency where appropriate. Choosing the shard key, indexes, and constraint scope must be **one unified design decision**, not disconnected steps.
