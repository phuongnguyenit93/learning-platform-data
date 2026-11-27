# `_id` Constraints, Unique Indexes, and Cluster-Wide Uniqueness in MongoDB Sharding

## 1. Learning objectives

In MongoDB, many applications rely on `_id`, `email`, `username`, or `orderNumber` as fields that must remain unique. On an unsharded collection, a unique index checks all documents in that collection. Once the collection is distributed across multiple shards, a critical question arises:

**If two documents share the same email yet land on two different shards, which shard detects the duplicate key?**

MongoDB addresses this through specific rules for unique indexes tied to the **shard key**. In particular, the default `_id_` unique index does not necessarily enforce `_id` uniqueness **across the entire sharded cluster** when `_id` is not the shard key.

This lesson belongs to the **Sharding** chapter of the **MongoDB Document Database Engine** module, covering **`_id` Constraints, Unique Indexes, and Cluster-Wide Uniqueness**.

After this lesson, you will be able to:

1. Distinguish uniqueness within a shard, uniqueness across a sharded collection, and uniqueness across multiple collections.
2. Explain when `_id` uniqueness is only enforced per shard.
3. Apply the **full shard-key prefix** rule when creating unique indexes.
4. Design per-tenant uniqueness versus system-wide uniqueness.
5. Create a range-sharded collection with valid compound unique indexes.
6. Identify invalid unique indexes and uniqueness restrictions on hashed indexes.
7. Design a proxy collection paired with transactions when a business key cannot be the shard key.
8. Understand how collation, missing/null values, canonicalization, and business uniqueness interact.
9. Handle duplicate key errors in `mongosh` and the Java Driver, including retried requests.
10. Anticipate impacts of shard key changes, resharding, chunk migrations, and operational steps.

**Core principle:** On a range-sharded collection, regular unique indexes must have **the entire shard key as their prefix**. The default `_id` exception may only guarantee uniqueness **within each shard** when `_id` is not the shard key.

## 2. Why does sharding complicate uniqueness?

An unsharded collection:

~~~text
Application
     |
     v
MongoDB collection
     |
     +-- unique index(email)
           checks documents in the collection
~~~

A sharded collection:

~~~text
                       Application
                            |
                            v
                           mongos
                            |
                 +----------+----------+
                 |                     |
                 v                     v
              Shard A               Shard B
           local index            local index
           user email=X           user email=X?
~~~

In a sharded collection, each shard manages the chunks of data it owns. Each shard can enforce a unique index across **its own documents**, yet cannot automatically check arbitrary values across every other shard.

To guarantee collection-wide uniqueness without an arbitrary global lookup on every insert, MongoDB requires an index structure ensuring documents with the same full unique key route under the same shard key.

### 2.1. Different scopes of uniqueness

| Scope | Meaning |
|---|---|
| Unique within a shard | Two documents on the same shard cannot share the same index key |
| Unique across a sharded collection | Two documents, regardless of shard, cannot share the same index key |
| Unique within a tenant | Cannot collide within one tenant; other tenants may reuse the value |
| System-wide unique | Cannot collide across any tenant; may require a registry |
| Unique across databases/clusters | An index on one collection does not check data in another collection or cluster |

**“Cluster-wide unique” in this lesson** primarily refers to shards holding **the same logical collection**. It does not span independent collections across multiple databases.

### 2.2. Shard key vs. unique key

The **shard key** determines how MongoDB distributes documents. The **unique key** determines which values cannot duplicate.

Both concepts can share the same field, e.g.:

~~~javascript
shardKey = { orderNumber: 1 };
uniqueKey = { orderNumber: 1 };
~~~

Or they can differ:

~~~javascript
shardKey = { tenantId: 1 };
uniqueKey = { tenantId: 1, emailKey: 1 };
~~~

The second option guarantees the **pair** `(tenantId, emailKey)` is unique, not that `emailKey` is unique cluster-wide.

## 3. What is a shard-key prefix?

Suppose a collection is sharded on:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

A compound index with the shard key as its prefix:

~~~javascript
{ tenantId: 1, regionId: 1, emailKey: 1 }
~~~

An index containing those fields in the **wrong order**:

~~~javascript
{ tenantId: 1, emailKey: 1, regionId: 1 }
~~~

An index missing part of the shard key:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

The latter two indexes do not satisfy the full shard-key prefix rule for unique indexes on shard key `{tenantId:1,regionId:1}`.

### 3.1. Must be the full prefix, not fields appearing somewhere

If the shard key has three fields:

~~~javascript
{ tenantId: 1, regionId: 1, orderType: 1 }
~~~

then a valid prefix-compatible unique index can be:

~~~javascript
{ tenantId: 1, regionId: 1, orderType: 1, orderNo: 1 }
~~~

Insufficient:

~~~javascript
{ tenantId: 1, regionId: 1, orderNo: 1 }
~~~

because `orderType` is missing from its required prefix position.

### 3.2. Why does a prefix enable uniqueness checks?

When two documents share the exact same full unique index key containing the shard key prefix, they also share the exact same shard key. By routing rules, those values belong to the same distribution scope where the owning shard can enforce uniqueness consistently.

This is why MongoDB rejects creating arbitrary unique indexes solely on non-shard-key fields in range-sharded collections.

## 4. Unique indexes permitted on a range-sharded collection

Per the MongoDB Manual, the main permitted categories are:

1. A unique index on the **shard key itself**.
2. A unique compound index starting with **the entire shard key**.
3. The default unique `_id` index — an exception, **not necessarily cluster-wide unique**.

With shard key:

~~~javascript
{ tenantId: 1 }
~~~

| Index | Unique allowed? | Meaning |
|---|---|---|
| `{tenantId:1}` | Yes | Only one document per `tenantId` |
| `{tenantId:1,emailKey:1}` | Yes | One `emailKey` per tenant |
| `{tenantId:1,orderNo:1}` | Yes | One `orderNo` per tenant |
| `{emailKey:1}` | No, with `unique=true` | Lacks shard-key prefix |
| `{emailKey:1,tenantId:1}` | No, with `unique=true` | Wrong field order |
| `{tenantId:1,emailKey:1}` | Yes if `unique=false` | Regular index, does not prevent duplicates |
| `{_id:1}` | Default unique index | May only enforce uniqueness per shard |

**Never assume** an index “having the shard key field somewhere” suffices; prefix order governs validity.

### 4.1. Compound unique indexes check combinations, not individual fields

Unique index:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

permits:

~~~javascript
{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}

{
  tenantId: "tenant-B",
  emailKey: "hello@example.test"
}
~~~

because the two **tuples** differ.

Rejects:

~~~javascript
{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}

{
  tenantId: "tenant-A",
  emailKey: "hello@example.test"
}
~~~

because the pair collides completely, even if `_id` or other fields differ.

### 4.2. Unique shard key enforces only the full tuple

With shard key:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

uniqueness on the shard key itself guarantees only that the `(tenantId, regionId)` pair is unique. It does not make `tenantId` or `regionId` unique individually.

## 5. Crucial exception: `_id` is not always unique across the whole sharded cluster

By default, every MongoDB collection has the index:

~~~javascript
{
  key: { _id: 1 },
  name: "_id_",
  unique: true
}
~~~

On an unsharded collection, this guarantees `_id` is unique within the collection.

However, if the collection is sharded on:

~~~javascript
{ tenantId: 1 }
~~~

MongoDB only enforces default `_id` uniqueness **within each shard**. There is no global check on `_id` independent of `tenantId`.

### 5.1. Example of two documents sharing `_id`

~~~javascript
{
  _id: "same-id",
  tenantId: "tenant-A",
  displayName: "Lan"
}

{
  _id: "same-id",
  tenantId: "tenant-B",
  displayName: "Minh"
}
~~~

Both documents **can** coexist if they land on two different shards. If routed to **the same shard**, that shard’s local unique `_id_` index rejects the second document.

Therefore, never write tests expecting duplicate `_id`s to **always** succeed just because `tenantId` differs. Outcome depends on chunk placement and data distribution.

### 5.2. What if `_id` itself is the shard key?

On a collection sharded strictly on:

~~~javascript
{ _id: 1 }
~~~

the `_id` value is also the shard key value. MongoDB can enforce uniqueness across the entire sharded collection via the corresponding index and routing.

This is straightforward, though ranged sharding on sequentially generated IDs must be evaluated for tail write hotspots.

### 5.3. Do `ObjectId` or UUID solve it completely?

An `ObjectId` or UUID from a reliable generator has an extremely low collision probability. This is great practice to prevent ID reuse across tenants or nodes.

~~~javascript
db.usersByTenant.insertOne({
  _id: new ObjectId(),
  tenantId: "tenant-A",
  displayName: "Lan"
});
~~~

Yet **very low collision probability is not a database-enforced global uniqueness constraint**.

If the app imports legacy data, uses reset counters, or passes a fixed ID repeatedly, cross-shard duplicates can still happen. For absolute guarantees, enforce an explicit uniqueness mechanism.

### 5.4. `_id` is immutable

Once a document exists, `_id` cannot be arbitrarily modified via a normal update:

~~~javascript
db.usersByTenant.updateOne(
  { tenantId: "tenant-A", _id: "user-001" },
  { $set: { _id: "user-002" } }
);
~~~

Changing an identifier requires a migration workflow: insert a new record, update references, and delete the old record per business guarantees.

### 5.5. Query implications

~~~javascript
db.usersByTenant.find({ _id: "same-id" });
~~~

If `_id` duplicated across shards, this query can return multiple documents. `findOne({_id:...})` is no proof of global `_id` uniqueness on a collection sharded by `tenantId`.

When identity is the `(tenant, ID)` pair, queries should carry the full scope:

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  _id: "same-id"
});
~~~

This keeps routing and authorization scoped properly, though it does not turn `_id` into a global unique constraint.

## 6. Preparing the practice environment

Sharding commands require a **sharded cluster with `mongos`**. Never use a standalone `mongod` to demonstrate cross-shard uniqueness behavior.

~~~text
mongosh / Java Driver
         |
         v
        mongos
         |
    +----+----+
    |         |
  Shard A   Shard B
    |         |
    +----+----+
         |
    Config servers
~~~

### 6.1. Verify connection

~~~javascript
db.adminCommand({ hello: 1 });
~~~

On `mongos`, the output typically includes:

~~~javascript
{
  msg: "isdbgrid"
}
~~~

You can also inspect:

~~~javascript
sh.status();
~~~

If you lack permissions to create collections or call `shardCollection`, analyze the examples conceptually. Never test on a production cluster without a runbook.

### 6.2. Sample database

~~~javascript
use sharding_unique_lab
~~~

This lesson uses:

~~~text
sharding_unique_lab.usersByTenant
sharding_unique_lab.licenseCodes
sharding_unique_lab.emailClaims
~~~

These names are strictly for a **test environment**. If collections already exist, check metadata before changing anything; never drop collections blindly just to start fresh.

## 7. Demo: enforcing unique emails per tenant

**Requirement:** Each tenant may have only one account per canonical email, while different tenants may reuse the same email.

Design:

~~~javascript
shardKey = { tenantId: 1 };
uniqueKey = { tenantId: 1, emailKey: 1 };
~~~

### 7.1. Create the collection

~~~javascript
use sharding_unique_lab

db.createCollection("usersByTenant");
~~~

If the collection already exists, do not blindly re-run DDL steps.

### 7.2. Create the shard key supporting index

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1 },
  { name: "idx_tenant" }
);
~~~

### 7.3. Create the unique compound index

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1, emailKey: 1 },
  {
    name: "uniq_tenant_email",
    unique: true
  }
);
~~~

This index constrains the **`(tenantId, emailKey)` pair**. `tenantId` leads, satisfying the full shard key prefix.

### 7.4. Shard the collection

On `mongos`:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.usersByTenant",
  { tenantId: 1 }
);
~~~

This is range sharding. The collection already has the shard key supporting index, and the unique compound index matches the shard-key prefix.

### 7.5. Insert valid values

~~~javascript
db.usersByTenant.insertMany([
  {
    _id: "user-A-1",
    tenantId: "tenant-A",
    emailKey: "lan@example.test",
    displayName: "Lan A"
  },
  {
    _id: "user-B-1",
    tenantId: "tenant-B",
    emailKey: "lan@example.test",
    displayName: "Lan B"
  },
  {
    _id: "user-A-2",
    tenantId: "tenant-A",
    emailKey: "minh@example.test",
    displayName: "Minh"
  }
]);
~~~

Two `lan@example.test` emails under two different tenants succeed. This is **correct** under the compound unique index.

### 7.6. Insert duplicate within the same tenant

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: "user-A-3",
    tenantId: "tenant-A",
    emailKey: "lan@example.test",
    displayName: "Duplicate"
  });
} catch (e) {
  print("Expected duplicate: " + e.message);
}
~~~

The new document shares `("tenant-A", "lan@example.test")` with `user-A-1`, so the unique index rejects it. The error typically carries code **11000** (`E11000 duplicate key`).

### 7.7. Query with the proper tenant

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  emailKey: "lan@example.test"
});
~~~

Having the shard key in the filter lets `mongos` target the appropriate range. It also preserves multi-tenant data isolation semantics.

## 8. Demo: unique indexes with an invalid prefix

On `usersByTenant` sharded on `{tenantId:1}`:

~~~javascript
// Rejected because it lacks the shard key prefix.
db.usersByTenant.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

Another invalid example:

~~~javascript
// Contains tenantId, but wrong field order.
db.usersByTenant.createIndex(
  { emailKey: 1, tenantId: 1 },
  { unique: true }
);
~~~

If you need an index to query by email, a **non-unique** index remains valid:

~~~javascript
db.usersByTenant.createIndex(
  { emailKey: 1 }
);
~~~

However, it will not prevent duplicate emails across tenants.

### 8.1. You cannot rely on `mongos` scanning every shard

`mongos` receives requests and routes them, but does not turn arbitrary unique indexes into global cross-shard probes. The prefix rule exists precisely because local unique indexes on each shard cannot enforce a unified constraint when colliding keys could sit on different shards.

### 8.2. What if unique indexes existed before sharding?

If an unsharded collection already had unique `{emailKey:1}` and you try to shard on `{tenantId:1}`, `sh.shardCollection` will reject it because the existing unique index lacks the shard-key prefix.

Never assume the rule applies only to indexes created **after** sharding.

## 9. Compound shard keys and uniqueness scope

Suppose the shard key is:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

| Unique index | Valid prefix? | Uniqueness scope |
|---|---|---|
| `{tenantId:1,regionId:1}` | Yes | `(tenant, region)` pair |
| `{tenantId:1,regionId:1,orderNo:1}` | Yes | `(tenant, region, orderNo)` triple |
| `{tenantId:1,orderNo:1}` | No | Missing `regionId` |
| `{tenantId:1,orderNo:1,regionId:1}` | No | Wrong prefix order |
| `{regionId:1,tenantId:1,orderNo:1}` | No | Wrong shard key order |
| `{orderNo:1}` | No | Missing shard key |

### 9.1. Should `regionId` be in the shard key?

If business rules require `orderNo` to be unique **within a tenant**, `{tenantId,regionId,orderNo}` is **insufficient**: the same `tenant`/`orderNo` can be reused across two different regions.

Example:

~~~javascript
{ tenantId: "T1", regionId: "north", orderNo: "ORD-99" }
{ tenantId: "T1", regionId: "south", orderNo: "ORD-99" }
~~~

The triples differ, so both are allowed.

Shard key design must balance data distribution, query patterns, and **business uniqueness scope** simultaneously.

## 10. Enforcing uniqueness on the range shard key itself

If every `licenseCode` must be unique collection-wide and the shard key is `licenseCode`:

~~~javascript
use sharding_unique_lab

db.createCollection("licenseCodes");

db.licenseCodes.createIndex(
  { licenseCode: 1 },
  {
    unique: true,
    name: "uniq_licenseCode"
  }
);
~~~

Then:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.licenseCodes",
  { licenseCode: 1 },
  true
);
~~~

The third argument `true` requests uniqueness on the **shard key itself**.

### 10.1. Testing a collision

~~~javascript
db.licenseCodes.insertOne({
  _id: "lic-1",
  licenseCode: "LIC-2026-001"
});

try {
  db.licenseCodes.insertOne({
    _id: "lic-2",
    licenseCode: "LIC-2026-001"
  });
} catch (e) {
  print(e.message);
}
~~~

The second insert is rejected for duplicating `licenseCode`.

### 10.2. Conditions to watch

- For a non-empty collection, prepare the matching unique shard key index beforehand.
- If a **non-unique** supporting index already exists on the shard key, the `unique` option may be rejected.
- A unique compound index prefixed by the shard key does **not** satisfy uniqueness **on the shard key itself** for `sh.shardCollection(..., true)`.
- If the collection already contains duplicate shard key values, building the unique index fails.

Never set `unique: true` on the shard key when a collection must store **multiple documents per shard key value**. For example, unique `{tenantId:1}` restricts each tenant to one single document, violating normal needs.

## 11. Verifying `_id` limitations on sharded collections

`usersByTenant` sharded on `tenantId` still retains the index:

~~~javascript
db.usersByTenant.getIndexes();
~~~

Even though `_id_` is marked unique, because the shard key is **not** `_id`, the default index does not automatically enforce global uniqueness.

### 11.1. Two documents with duplicate `_id` can occur

~~~javascript
// Illustrates the risk; outcome depends on chunk placement.
db.usersByTenant.insertOne({
  _id: "cross-shard-duplicate",
  tenantId: "tenant-A",
  emailKey: "one@example.test"
});

db.usersByTenant.insertOne({
  _id: "cross-shard-duplicate",
  tenantId: "tenant-B",
  emailKey: "two@example.test"
});
~~~

- If both land on **the same shard**, the local `_id` unique index rejects the second insert.
- If they land on **two different shards**, there may be no global constraint blocking identical `_id`s.

Do not force the balancer or move chunks in a shared environment solely to demonstrate this.

### 11.2. Not merely a theoretical concern

Cross-shard duplicate `_id`s cause real trouble during:

- Queries by `_id` alone where the application expects a single document.
- Data migrations/imports/exports.
- Chunk migrations bringing two colliding keys onto the same shard.
- Resharding under a new shard key.
- Rebuilding ID-based references.

Detecting and resolving duplicates requires a runbook that reconciles references—never randomly delete one document.

## 12. Hashed shard keys and uniqueness

Hashed sharding distributes documents by a field’s hash value:

~~~javascript
sh.shardCollection(
  "sharding_unique_lab.events",
  { eventId: "hashed" }
);
~~~

**Hashing serves distribution, not uniqueness enforcement.**

MongoDB **forbids unique hashed indexes**:

~~~javascript
// Invalid:
db.events.createIndex(
  { eventId: "hashed" },
  { unique: true }
);
~~~

Nor can you run:

~~~javascript
// Invalid: unique=true on a hashed shard key.
sh.shardCollection(
  "sharding_unique_lab.events",
  { eventId: "hashed" },
  true
);
~~~

### 12.1. If you still need a globally unique business key

Never pick a hashed shard key and assume the database enforces uniqueness. Consider a ranged shard key matching the unique key, or a proxy collection/registry.

### 12.2. Do not overgeneralize

What is certain here is that **hashed indexes do not support uniqueness** and unique hashed shard keys are restricted. Other index types on hashed-sharded collections have specific rules by key pattern and MongoDB version; check documentation before designing.

### 12.3. Ranged keys must still be checked for hotspots

Sharding sequentially on `{_id:1}` or `{orderNo:1}` can funnel writes into the newest range. Uniqueness correctness is mandatory, yet does not replace evaluating write spread and scalability.

## 13. Collation and canonical business keys

Two strings:

~~~text
Lan@Example.Test
lan@example.test
~~~

may count as the same email under application policy, yet MongoDB does not automatically normalize arbitrary strings when indexing.

### 13.1. Collation in sharded unique indexes

Per the MongoDB Manual on uniqueness in sharded clusters, uniqueness on indexed keys with collation is only guaranteed when using the **simple** collation under documented rules. Never treat a locale-specific case-insensitive unique index as a default solution for cluster-wide cross-shard uniqueness.

### 13.2. Store a canonicalized key

Store two fields:

~~~javascript
{
  tenantId: "tenant-A",
  emailDisplay: "Lan@Example.Test",
  emailKey: "lan@example.test"
}
~~~

and index:

~~~javascript
db.usersByTenant.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

`emailDisplay` is for display; `emailKey` is the canonical key generated under a consistent policy.

### 13.3. Do not assume `toLowerCase` suffices everywhere

Normalization rules may require:

- Trimming leading/trailing whitespace.
- Unicode normalization.
- Language/standard-appropriate case folding.
- Internationalized domain handling.
- Product-specific email local-part rules.
- Format validation.
- A canonical-key backfill workflow when policies evolve.

For accented Vietnamese usernames or complex Unicode, never just call lowercase and assume visually identical strings become identical bytes.

### 13.4. All writers must enforce the exact same policy

If Service A stores `Lan@Example.Test` as `lan@example.test` while Service B writes the raw string as the key, the unique index only checks whatever literal values were written. Share one canonicalization rule across APIs, background jobs, migrations, and imports.

## 14. Missing/null values and compound unique indexes

In unique indexes, missing fields are indexed according to MongoDB’s index-key rules (typically as `null`).

With:

~~~javascript
{ tenantId: 1, emailKey: 1 }
~~~

insert:

~~~javascript
db.usersByTenant.insertOne({
  _id: "missing-A-1",
  tenantId: "tenant-A",
  displayName: "No email yet"
});
~~~

A second document in the same tenant also missing `emailKey` can trigger `E11000` because both keys resolve to `("tenant-A", null)`.

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: "missing-A-2",
    tenantId: "tenant-A",
    displayName: "Also no email yet"
  });
} catch (e) {
  print(e.message);
}
~~~

Conversely, `tenant-B` missing `emailKey` produces a different tuple because `tenantId` differs.

### 14.1. If `emailKey` is required

Use schema validation, API checks, and data constraints to require a valid canonical string. A unique index does not make a field required by itself.

### 14.2. If `emailKey` is optional

Decide explicitly whether uniqueness applies only to documents with an email or also to null/missing entries. Investigate partial unique indexes within sharded collection and server version limits, or split documents/collections by domain need.

Never assume every partial index is allowed on shard keys or that `sparse: true` handles every null edge case.

## 15. Per-tenant uniqueness vs. cluster-wide uniqueness

Suppose the requirement is:

~~~text
tenant-A may have x@example.test once.
tenant-B may also have x@example.test once.
~~~

Unique `{tenantId:1,emailKey:1}` satisfies this.

Yet if the product changes the requirement to:

~~~text
Email x@example.test may be used only once
across the entire system, regardless of tenant.
~~~

the same index **no longer works** because differing `tenantId` values produce distinct unique keys.

### 15.1. Two main solutions

**Solution A — Use `emailKey` itself as the range shard key.**

~~~javascript
shardKey = { emailKey: 1 };
uniqueIndex = { emailKey: 1 };
~~~

This enforces unique emails directly, though you must evaluate cardinality, hotspots, tenant-based queries, and email-change frequency.

**Solution B — Use a global-unique proxy collection.**

Keep `users` sharded on `tenantId`, while a proxy collection stores global email claims and participates in a transaction during user creation.

Solution B usually fits better when tenant-scoped distribution and queries matter more than sharding the main collection by email.

### 15.2. Do not confuse collection-wide uniqueness with cross-collection uniqueness

A unique index on `users` does not check `admins` or `invitedUsers` in separate collections. If emails must be unique across **the entire identity system**, maintain one shared registry/source of truth across all registration flows.

## 16. Proxy collection: enforcing uniqueness when the field is not the shard key

The MongoDB Manual recommends a **proxy collection** for fields requiring uniqueness that cannot serve as the main collection’s shard key.

Diagram:

~~~text
                    Create user request
                            |
                            v
                      MongoDB transaction
                        /           \
                       v             v
                emailClaims       usersByTenant
                unique email      shard tenantId
                       \             /
                        \           /
                        commit or abort
~~~

Main collection:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-A",
  emailKey: "lan@example.test",
  displayName: "Lan"
}
~~~

The proxy collection can use `emailKey` as `_id`:

~~~javascript
{
  _id: "lan@example.test",
  userId: ObjectId("..."),
  tenantId: "tenant-A"
}
~~~

If the proxy is **unsharded**, its default unique `_id` index prevents inserting two claims with the same email.

### 16.1. Create the proxy

~~~javascript
use sharding_unique_lab
db.createCollection("emailClaims");
~~~

In this demo, the proxy stays unsharded. If the proxy must be sharded at massive scale, choose a uniqueness-compatible shard key—such as range sharding on `emailKey` itself with a matching unique index.

### 16.2. Why is a transaction needed?

If writing the proxy succeeds but inserting the user fails, the email is claimed without a user. If inserting the user succeeds but writing the proxy fails, global uniqueness is broken.

A transaction wraps both writes into **the same commit/abort unit**, preventing the two collections from diverging on partial failure.

### 16.3. Illustrative `mongosh` transaction

~~~javascript
function createUserGlobal(
  tenantId,
  emailKey,
  displayName
) {
  const s = db.getMongo().startSession({
    readPreference: { mode: "primary" }
  });

  const d = s.getDatabase("sharding_unique_lab");
  const userId = new ObjectId();

  try {
    s.startTransaction({
      readConcern: { level: "snapshot" },
      writeConcern: { w: "majority" }
    });

    // Claim email globally.
    d.emailClaims.insertOne({
      _id: emailKey,
      tenantId: tenantId,
      userId: userId
    });

    // Create user in the sharded collection.
    d.usersByTenant.insertOne({
      _id: userId,
      tenantId: tenantId,
      emailKey: emailKey,
      displayName: displayName
    });

    s.commitTransaction();
    return userId;
  } catch (e) {
    try { s.abortTransaction(); } catch (_) {}
    throw e;
  } finally {
    s.endSession();
  }
}
~~~

Assumes both collections already exist and the cluster supports multi-document transactions. This is an **instructional pattern**, not a full production handler with retry loops.

### 16.4. Test two tenants using the same email

~~~javascript
createUserGlobal(
  "tenant-A",
  "unique-global@example.test",
  "Lan"
);

try {
  createUserGlobal(
    "tenant-B",
    "unique-global@example.test",
    "Minh"
  );
} catch (e) {
  print("Global duplicate prevented: " + e.message);
}
~~~

The second request is blocked at `emailClaims` by its unique `_id`, regardless of whether the user document would live on Shard A or B.

### 16.5. Do not use two separate inserts when atomicity is required

~~~javascript
// Does NOT guarantee atomicity across both collections:
db.emailClaims.insertOne({ _id: emailKey, userId });
db.usersByTenant.insertOne({ _id: userId, tenantId, emailKey });
~~~

If the process crashes in between, the two collections fall out of sync.

If transactions cannot be used, design an explicit reservation, TTL, status, reconciliation, and compensation workflow. Never treat two separate statements as equivalent to a transaction.

## 17. Check-then-insert does not protect against races

Common buggy approach:

~~~javascript
const exists = db.usersByTenant.findOne({
  emailKey: "taken@example.test"
});

if (!exists) {
  db.usersByTenant.insertOne({
    tenantId: "tenant-A",
    emailKey: "taken@example.test"
  });
}
~~~

Timeline:

~~~text
Client A                      Client B
   |                             |
   | find(email) -> not found    |
   |                             | find(email) -> not found
   |                             |
   | insert(email)               | insert(email)
   |                             |
   +-------- both can attempt to write
~~~

Reading first and writing second are two separate operations. Without a shared constraint, both clients pass the check simultaneously.

### 17.1. Does snapshot isolation solve it?

Simply opening two snapshot transactions that both read “email not found” is insufficient if both transactions insert **two different documents** without contending on a unique key.

The proxy’s unique index creates a true contention point: only one request can claim the same `emailKey`.

### 17.2. Duplicate key is a valid concurrency outcome

When two requests race to claim a global email, one commits while the other receives `E11000`. That is business protection working properly, not necessarily a system failure.

The API layer can map that error to HTTP `409 Conflict` or an equivalent validation error.

### 17.3. Idempotency is still required

If a client times out after commit without receiving the ACK, a retry hits duplicate key. Never blindly treat every `E11000` as success; inspect `requestId`, owner, and payload hash to distinguish an already-completed request from a collision with someone else.

## 18. Changing emails or deleting users with a proxy

### 18.1. Changing email

Transactional workflow:

1. Compute `newEmailKey` using the exact same canonicalization policy.
2. Insert the new claim with the unique key.
3. Update the user document by shard key and `userId`.
4. Delete the old claim, checking `userId`/owner so you never delete someone else’s claim.
5. Commit with an appropriate write concern.

If step 2 hits a unique conflict, the transaction aborts and the user keeps the old email.

### 18.2. Deleting a user

If policy allows email reuse after deletion:

~~~text
Transaction:
  delete user matching tenant + userId
  delete claim matching emailKey + userId
  commit
~~~

If policy reserves the email after soft-delete, the proxy keeps the claim with a matching status. That is a business rule, not an automatic unique index behavior.

### 18.3. Never delete claims by email alone under concurrency

Always verify the email claim belongs to the user being updated or deleted. Otherwise, a delayed request could delete a reservation now owned by another user.

## 19. Sharding a collection that already has unique indexes

Suppose an unsharded `users` collection has:

~~~javascript
db.users.createIndex(
  { emailKey: 1 },
  { unique: true }
);

db.users.createIndex(
  { usernameKey: 1 },
  { unique: true }
);
~~~

And you want to shard on:

~~~javascript
{ tenantId: 1 }
~~~

`sh.shardCollection` will reject it because the existing unique indexes do not have `tenantId` as a prefix.

### 19.1. Simply adding a new index does not make the problem vanish

Even after adding:

~~~javascript
db.users.createIndex(
  { tenantId: 1, emailKey: 1 },
  { unique: true }
);
~~~

the older unique indexes `{emailKey:1}` and `{usernameKey:1}` remain incompatible with the new shard key.

### 19.2. Plan migrations around product requirements

If `email`/`username` must remain globally unique, never casually drop global indexes and replace them with tenant-scoped indexes.

Options include:

- Pick a shard key supporting one global unique field.
- Move other global unique fields into proxy registries.
- Separate the global identity registry from tenant profiles.
- Execute a phased migration ensuring all writers honor the new constraints.

### 19.3. Migration checklist

1. Inventory existing unique indexes on the collection.
2. Confirm global vs. per-tenant scope for every business key.
3. Finalize canonicalization rules and missing/null handling.
4. Scan for duplicates before building new indexes.
5. Plan index and shard key transitions.
6. Prevent concurrent writes from breaking invariants mid-transition.
7. Test on staging with representative data.
8. Run production DDLs only with a runbook and monitoring.
9. Verify data integrity post-migration.
10. Never drop critical constraints before replacement guarantees are active.

## 20. Resharding and existing unique constraints

Resharding changes a collection’s shard key, thereby changing the prerequisites on unique indexes.

Initial state:

~~~javascript
oldShardKey = { tenantId: 1 };
uniqueIndex = { tenantId: 1, emailKey: 1 };
~~~

Desired change:

~~~javascript
newShardKey = { regionId: 1 };
~~~

The existing unique index lacks `regionId` as a prefix. MongoDB requires the new shard key to satisfy existing unique index requirements, so this reshard plan would be rejected.

### 20.1. Duplicate `_id`s affect resharding

The MongoDB Manual notes that resharding can **fail if `_id` values are not globally unique**, to prevent data corruption. Duplicate `_id`s can also block chunk migrations.

This is a real operational consequence of the per-shard `_id` uniqueness exception.

### 20.2. Never “just reshard and clean up duplicates later”

Before resharding:

- Identify all unique indexes.
- Audit global `_id` uniqueness across existing documents.
- Verify whether the new shard key prefixes every unique index you intend to keep.
- Audit ID references from other collections/services.
- Prepare duplicate remediation and rollback/maintenance plans.

### 20.3. Do not choose a shard key solely to satisfy one index

The shard key governs query targeting, write distribution, and balancing. Changing a shard key merely to legalize one unique index can introduce severe hotspots or scatter-gather overhead.

## 21. Chunk migrations preserve uniqueness principles

Chunks move between shards to balance data. A properly prefixed unique index keeps its constraint intact as routing and chunk ownership shift.

However, pre-existing duplicate `_id`s across two shards are a different problem: when chunk migrations bring colliding `_id` documents onto the same shard, conflicts occur.

**Never intentionally create duplicate `_id`s or force chunk migrations in production** just to test this. When duplicates are discovered, remediate data via a procedure that reconciles all references.

### 21.1. Metadata and index consistency

In a sharded cluster, index builds and topology changes must be tracked cluster-wide. Never inspect `getIndexes()` on one individual shard and assume every shard matches.

Use metadata/index consistency checks supported by your organization’s MongoDB version.

## 22. `mongosh`: inspecting shard keys and unique indexes

### 22.1. Check sharding status

~~~javascript
sh.status();
~~~

Locate the namespace:

~~~text
sharding_unique_lab.usersByTenant
~~~

Verify the real shard key rather than guessing from collection names.

### 22.2. View index definitions

~~~javascript
db.usersByTenant.getIndexes();
~~~

Illustrative output:

~~~javascript
[
  {
    key: { _id: 1 },
    name: "_id_",
    unique: true
  },
  {
    key: { tenantId: 1 },
    name: "idx_tenant"
  },
  {
    key: { tenantId: 1, emailKey: 1 },
    name: "uniq_tenant_email",
    unique: true
  }
]
~~~

With shard key `{tenantId:1}`:

- `_id_`: local uniqueness, does not prove global uniqueness.
- `idx_tenant`: regular index.
- `uniq_tenant_email`: unique `(tenant, email)` pair with valid prefix.

### 22.3. Why is checking `unique: true` alone insufficient?

`unique: true` is an index property. To know its **global scope** in a sharded collection, combine it with the shard key pattern and MongoDB’s documented exceptions.

## 23. Handling `E11000` duplicate key errors

MongoDB typically returns error code **11000** when a unique index is violated:

~~~javascript
try {
  db.usersByTenant.insertOne({
    _id: new ObjectId(),
    tenantId: "tenant-A",
    emailKey: "lan@example.test"
  });
} catch (e) {
  if (e.code === 11000) {
    print("Duplicate key");
  } else {
    throw e;
  }
}
~~~

### 23.1. A collection can have multiple unique indexes

`E11000` may originate from:

- `_id_` local uniqueness.
- `uniq_tenant_email`.
- Another unique index.
- Proxy `emailClaims` `_id_`.

Never blindly return “email already exists” on every `E11000`. In real applications, identify which index/key was violated and map it against business contracts.

### 23.2. Duplicate key vs. network errors

- Duplicate key: a data constraint was violated.
- Network timeout: client may not have received the final result.
- Transient transaction error: eligible for retry per protocol.
- Unknown commit result: transaction may have committed; retry commit or reconcile.

Never retry a genuine duplicate key endlessly, and never assume every timeout means a write did not occur.

### 23.3. `requestId` and idempotency

Use a stable request ID, canonical business key, and result lookup to verify whether an operation already completed earlier.

Example retry creating a user whose email is already claimed:

1. Look up the claim by `emailKey`.
2. Check `userId` and `requestId`/`payloadHash`.
3. If it belongs to the same completed request, return the matching prior result.
4. If it belongs to a different request, return a conflict.
5. Never generate a brand-new `userId` on every retry that might create duplicate accounts.

## 24. Java Sync Driver: creating prefix-compatible indexes

Assume `database` is a `MongoDatabase` on a sharded cluster, and the collection is sharded on `{tenantId:1}`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

MongoCollection<Document> users =
    database.getCollection("usersByTenant");

String indexName = users.createIndex(
    Indexes.ascending("tenantId", "emailKey"),
    new IndexOptions()
        .name("uniq_tenant_email")
        .unique(true)
);

System.out.println(indexName);
~~~

Ensure the index does not already exist with differing options before running migration code in production.

### 24.1. Inserting and handling duplicates

~~~java
import com.mongodb.MongoWriteException;
import org.bson.Document;
import org.bson.types.ObjectId;

Document user = new Document("_id", new ObjectId())
    .append("tenantId", "tenant-A")
    .append("emailKey", "lan@example.test")
    .append("displayName", "Lan");

try {
    users.insertOne(user);
    System.out.println("User created");
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        System.out.println("Duplicate key, inspect index");
    } else {
        throw ex;
    }
}
~~~

### 24.2. Connecting through `mongos` / cluster URI

The driver must use the sharded cluster URI. Never connect directly to a shard primary to write as if it represented the whole sharded collection; route through `mongos` per deployment policy.

## 25. Java transactions with a proxy collection

Assumptions:

- `usersByTenant` is the main collection sharded by `tenantId`.
- `emailClaims` is an unsharded proxy collection with unique `_id`.
- Both collections already exist.
- `client` is `MongoClient` and `database` is `MongoDatabase`.

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.types.ObjectId;

MongoCollection<Document> claims =
    database.getCollection("emailClaims");
MongoCollection<Document> users =
    database.getCollection("usersByTenant");

TransactionOptions opts = TransactionOptions.builder()
    .readPreference(ReadPreference.primary())
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .build();

ObjectId userId = new ObjectId();
String tenantId = "tenant-A";
String emailKey = "global-new@example.test";

try (ClientSession session = client.startSession()) {
    session.startTransaction(opts);

    try {
        claims.insertOne(
            session,
            new Document("_id", emailKey)
                .append("tenantId", tenantId)
                .append("userId", userId)
        );

        users.insertOne(
            session,
            new Document("_id", userId)
                .append("tenantId", tenantId)
                .append("emailKey", emailKey)
                .append("displayName", "New User")
        );

        session.commitTransaction();
    } catch (Exception e) {
        try {
            session.abortTransaction();
        } catch (Exception ignored) {}
        throw e;
    }
}
~~~

This is a minimal technical example; production requires transaction retry loops for `TransientTransactionError` and `UnknownTransactionCommitResult`, deadlines, idempotency, and external side-effect management.

### 25.1. Why not rely on transactions alone without proxy uniqueness?

If two transactions both read “email not found” and insert two different user documents on two shards, they will not necessarily conflict without a shared unique key. The proxy’s unique `_id` provides the explicit contention point.

### 25.2. Generate `ObjectId` once per business request

Inside a retryable transaction helper, preserve request identity and reconcile prior outcomes. Never mint a fresh account ID on every retry without knowing whether the prior attempt committed.

## 26. Schema validation, nulls, and boundary data

Unique indexes do not replace schema validation.

If `emailKey` is required, validation must enforce its presence, type, and format per policy. A unique index only checks whether two documents share the same indexed key.

For instance, two documents missing `emailKey` in the same tenant collide on `(tenant-A, null)` in a unique compound index.

If email is optional, design explicitly:

- Should multiple users without emails be permitted in the same tenant?
- Is a partial unique index needed, and does it meet sharded collection limits?
- Should emails live in a separate child collection?
- Should `emailVerified` be required before claiming an email?
- Should claims be released on user soft-delete?

Never rely on default null/missing behavior without testing it.

### 26.1. Multi-tenant schema hygiene

A user document should include:

~~~javascript
{
  _id: ObjectId("..."),
  tenantId: "tenant-A",
  emailKey: "lan@example.test",
  displayName: "Lan"
}
~~~

API filters must still inject `tenantId` from the authenticated session. A unique index is not an authorization control.

## 27. Trade-offs between correctness and performance

| Design | Pros | Risks |
|---|---|---|
| Shard by `tenantId` | Tenant queries target easily; per-tenant uniqueness is natural | Very large tenants can create hotspots |
| Shard by `emailKey` | Direct global email uniqueness; email lookups target cleanly | Tenant queries may scatter-gather |
| Shard by hashed key | Good write spread for sequential keys | Hashed indexes cannot enforce uniqueness like range keys |
| Proxy global unique | Keeps main shard key optimized for workload while claiming globally | Extra collection, transaction overhead, registry load, cleanup logic |
| Distributed random `ObjectId` | Extremely low collision odds | Not an enforced global constraint if shard key differs |
| Compound unique with shard-key prefix | Enforced by MongoDB collection-wide | Scope covers the tuple only, not individual fields |

### 27.1. Unique indexes carry write cost

Unique indexes require updates, conflict checks, and extra storage/I/O. Adding many unique indexes increases write latency and complicates migrations.

### 27.2. Query optimization goes beyond unique indexes

Index keys must match filters and sorts. An index built solely for uniqueness may not serve all query shapes well.

If a collection is sharded by `tenantId`, user lookups by email should pass:

~~~javascript
db.usersByTenant.findOne({
  tenantId: "tenant-A",
  emailKey: "lan@example.test"
});
~~~

Omitting `tenantId` can hit multiple shards even with a local index on `emailKey`.

## 28. Common misconceptions

| Misconception | Correct understanding |
|---|---|
| “`_id` is always globally unique” | Default `_id` index may only enforce uniqueness per shard |
| “`unique: true` works on any field” | Sharded collections require full shard-key prefix, aside from `_id` exception |
| “Having the shard key somewhere in the index suffices” | Must match exact prefix and order |
| “Unique `tenantId+email` makes email globally unique” | It enforces uniqueness on the pair |
| “Two different tenants always live on two different shards” | No; depends on chunk placement |
| “Hashed shard keys can use `unique: true`” | Unique hashed indexes are not supported |
| “`ObjectId` guarantees zero collisions forever” | Low probability, not a formal constraint |
| “Snapshot transactions remove the need for unique indexes” | Check-then-insert still races without key contention |
| “`E11000` always means duplicate email” | Could come from `_id` or another index |
| “Dropping old unique indexes is a quick way to shard” | May break critical business invariants |
| “Resharding doesn’t touch unique indexes” | New shard key must satisfy existing unique constraints |
| “With a proxy, two separate writes suffice” | Requires a transaction or explicit sync/compensation |
| “Null values are ignored by unique indexes” | Missing/null values produce index keys that can collide |
| “Querying by `_id` always returns at most one record” | Not guaranteed if `_id` duplicated across shards |
| “Just fix the app without cleaning old data” | Existing duplicates still block migrations and index builds |

## 29. Hands-on exercises

Run DDL/write exercises on a **test sharded cluster**, never on production. Without a cluster, analyze outcomes using the rules learned.

### Exercise 1 — Identify valid unique indexes

Shard key `{tenantId:1}`. Classify:

~~~javascript
{ tenantId: 1 }
{ tenantId: 1, emailKey: 1 }
{ emailKey: 1 }
{ emailKey: 1, tenantId: 1 }
{ _id: 1 }
~~~

Explain the `_id` exception.

### Exercise 2 — Compound shard key

With shard key:

~~~javascript
{ tenantId: 1, regionId: 1 }
~~~

Identify which indexes have a valid prefix:

~~~javascript
{ tenantId: 1, regionId: 1, orderNo: 1 }
{ tenantId: 1, orderNo: 1, regionId: 1 }
{ regionId: 1, tenantId: 1, orderNo: 1 }
{ tenantId: 1, orderNo: 1 }
~~~

### Exercise 3 — Create per-tenant uniqueness

Create unique `{tenantId:1,emailKey:1}` on a collection sharded by `tenantId`. Insert two documents with the same email across two tenants, then two documents with the same email in one tenant.

**Expected:** Only the second case is rejected.

### Exercise 4 — Unique index with invalid prefix

Try:

~~~javascript
db.usersByTenant.createIndex(
  { emailKey: 1 },
  { unique: true }
);
~~~

**Question:** Why can’t `mongos` treat it as a global unique constraint?

### Exercise 5 — `_id` across two shards

Suppose a collection is sharded on `{tenantId:1}`, and two documents share the same `_id` with different tenants.

**Question:** What happens if they land on the same shard? What if on different shards? Why shouldn’t invariants rely on current chunk placement?

### Exercise 6 — `ObjectId`

An application uses `new ObjectId()` for every user. Explain its benefits and limitations compared to a database-enforced global constraint.

### Exercise 7 — Unique shard key

Create a range-sharded collection `licenseCodes` with unique `licenseCode`. Why can’t you switch the shard key to hashed and keep `unique: true`?

### Exercise 8 — Canonicalization

Two emails:

~~~text
Lan@Example.Test
lan@example.test
~~~

Propose a consistent canonicalization policy and per-tenant unique key. Why shouldn’t you casually rely on a non-simple collation on a sharded unique index?

### Exercise 9 — Null/missing

With unique `{tenantId:1,emailKey:1}`, two `tenant-A` documents both omit `emailKey`.

**Question:** Why are they treated as duplicates under the index key? How does it differ if one document belongs to `tenant-B`?

### Exercise 10 — Global email uniqueness

Choose two viable options:

A. Shard users by `tenantId`, put unique index directly on `emailKey`.

B. Shard users by `emailKey` with a unique index on `emailKey`.

C. Shard users by `tenantId`, use a unique `emailClaims` proxy and a transaction.

**Answer:** B or C depending on workload; A violates sharded unique index prerequisites.

### Exercise 11 — Proxy + transaction

Trace the steps to reserve an email claim, insert the user, and commit. If inserting the user fails after the claim was inserted, how does the transaction handle it?

### Exercise 12 — Concurrent inserts

Two requests run `findOne(email)` then `insertOne` nearly simultaneously. Why can both pass `findOne`? At which step does the unique index or proxy resolve the race?

### Exercise 13 — `E11000` and API responses

A user insert receives `E11000` without inspecting which index failed. Why shouldn’t you immediately return “email already exists”? Distinguish duplicate IDs from duplicate business keys.

### Exercise 14 — Retry after timeout

Request A commits a user successfully yet misses the ACK; its retry hits a duplicate email claim.

**Question:** How do you verify the existing claim belongs to Request A rather than someone else?

### Exercise 15 — Index migration

An unsharded collection has unique indexes on `emailKey` and `usernameKey`. You want to shard by `tenantId`.

**Question:** Why might `shardCollection` reject this? Propose a plan preserving global uniqueness.

### Exercise 16 — Resharding

A collection has unique `{tenantId:1,emailKey:1}`, and you want to reshard to `{regionId:1}`.

**Question:** Which constraint is violated? How must data and indexes be prepared?

### Exercise 17 — Chunk migration and duplicate `_id`

If data contains duplicate `_id`s across two shards, why can chunk migration or resharding fail? May you randomly delete one document?

### Exercise 18 — Multi-tenant design

Requirements:

~~~text
username unique per tenant
email unique system-wide
orderNo unique per tenant
~~~

Choose appropriate shard keys, compound indexes, and proxy collections. Distinguish the semantics of each constraint.

### Exercise 19 — Inspect metadata

Run:

~~~javascript
sh.status();
db.usersByTenant.getIndexes();
~~~

Identify the real shard key, indexes with `unique: true`, indexes carrying the full shard key prefix, and the scope of `_id_`.

### Exercise 20 — Performance trade-offs

Compare three options:

1. Shard users by `tenantId`.
2. Shard users by `emailKey`.
3. Shard users by `tenantId` + global proxy.

State impacts on routing, throughput, email uniqueness, and transaction complexity.

## 30. Pre-production checklist

### Correctness

- [ ] Uniqueness scope defined: per-tenant, collection-wide, or system-wide.
- [ ] Actual shard key verified.
- [ ] Unique indexes use the full shard key as prefix.
- [ ] Default `_id` local uniqueness is not treated as an unfounded global guarantee.
- [ ] No unique hashed indexes attempted.
- [ ] Compound tuple uniqueness distinguished from single-field uniqueness.
- [ ] Missing/null handling policy established.
- [ ] Consistent canonicalization policy enforced across all writers.
- [ ] Concurrent inserts/updates tested.
- [ ] Proxy registry designed if global uniqueness outside the shard key is needed.

### Operations

- [ ] Connected through `mongos` with proper admin privileges.
- [ ] Unique indexes inventoried before sharding/resharding.
- [ ] Existing data audited for duplicates, especially `_id`.
- [ ] Unique constraints never dropped without active replacements.
- [ ] Index-build runbook and cross-shard consistency checks in place.
- [ ] Plan prepared for chunk migrations if duplicates are discovered.
- [ ] Monitoring configured for `E11000` and transaction errors.
- [ ] Idempotency implemented for client retries.
- [ ] Update/delete lifecycle designed for email claims.
- [ ] Proxy collection bottleneck potential evaluated.

### Performance and safety

- [ ] Shard key distributes data appropriately for the workload.
- [ ] Oversized-tenant hotspot impact evaluated.
- [ ] Queries carry `tenantId`/authorization filters properly.
- [ ] Non-unique indexes added for filter/sort shapes.
- [ ] Scatter-gather and routing measured via `mongos`.
- [ ] Index footprint and write amplification monitored.
- [ ] Staging tested on representative data prior to production DDL.

## 31. Conclusion

MongoDB Sharding transforms uniqueness from a single-node check into **a constraint spanning distributed data ranges**.

- With **range sharding**, regular unique indexes must have **the entire shard key as prefix**, aside from the default `_id` index with its specific limitation.
- **`_id` may only be unique per shard** if the shard key differs from `_id`. Use controlled ID generation, and add a global mechanism if business invariants demand strict enforcement.
- **Compound unique** constrains the full tuple. `{tenantId, emailKey}` is per-tenant unique, **not** cluster-wide email unique.
- **Hashed indexes do not support unique constraints**; data spread and uniqueness are separate goals.
- **Global business keys outside the shard key** can be enforced via a proxy collection with a unique index updated inside a transaction alongside the main collection.
- **Migrations, resharding, and chunk moves** must account for all unique indexes and pre-existing duplicate data.
- **Canonicalization, null handling, concurrent writes, and idempotency** are essential parts of the design.

Choosing a solid shard key not only enables fast distributed reads and writes, but also lets MongoDB **enforce your business’s most critical uniqueness invariants**.

## Official references

- [MongoDB Manual — Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/)
- [MongoDB Manual — Shard Key Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key-indexes/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Enforce Uniqueness on the Shard Key Values](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-shard-key-values/)
- [MongoDB Manual — Enforce Uniqueness on a Field That Is Not the Shard Key](https://www.mongodb.com/docs/manual/tutorial/enforce-uniqueness-on-non-shard-key-field/)
- [MongoDB Manual — Create a Unique Index on Existing Sharded Collection](https://www.mongodb.com/docs/manual/tutorial/create-unique-index-on-sharded-collection/)
- [MongoDB Manual — Sharded Collections with Unique Indexes](https://www.mongodb.com/docs/manual/tutorial/shard-collection-with-unique-index/)
- [MongoDB Manual — Hashed Sharding](https://www.mongodb.com/docs/manual/core/hashed-sharding/)
- [MongoDB Manual — Reshard a Collection](https://www.mongodb.com/docs/manual/core/sharding-reshard-a-collection/)
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
