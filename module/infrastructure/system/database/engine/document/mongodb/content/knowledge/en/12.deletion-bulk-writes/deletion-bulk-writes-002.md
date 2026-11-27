# Soft Delete, Hard Delete, and Their Impact on Queries and Unique Indexes

In MongoDB, "deleting a document" can mean at least two different things:

- **Hard delete:** removes the document from the collection using `deleteOne()`, `deleteMany()`, or an equivalent delete operation. The document can no longer be queried from that collection.
- **Soft delete:** **does not remove the document**, instead updating a status field such as `isDeleted: true` or recording `deletedAt`. The application treats only active documents as existing.

These two approaches differ in recovery, storage space, queries, indexes, relationship handling, auditing, and especially **unique constraints (unique indexes)**. A soft-deleted document is still a real document in the collection. Therefore, if there is a regular unique index on `emailNormalized`, the email value of a soft-deleted record **can still block a new account registration with the same email**.

This lesson walks through the data model, delete statements, filter queries, unique index design, and the hard-delete process after a retention period. Examples use `mongosh` assuming a multi-tenant application that must avoid leaking deleted records through APIs.

## 1. The Big Picture: Soft Delete or Hard Delete?

Suppose the `users` collection has a document:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  role: "MEMBER",
  isDeleted: false,
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-02-01T09:00:00Z")
}
```

After a **soft delete**, the document still exists, but with added deletion metadata:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  role: "MEMBER",
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z"),
  deletedBy: "admin-42",
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-06-15T10:30:00Z")
}
```

With a **hard delete**, the document above is no longer returned from the `users` collection, even by admin queries that do not filter on `isDeleted`.

| Aspect | Soft delete | Hard delete |
|---|---|---|
| Document remains in collection? | Yes | No, after successful deletion |
| Can it be read again from the collection? | Yes, if the query allows it | No |
| Easy to restore the record? | Status can be toggled back, though conflicts must be checked | Requires backups, audit logs, or reconstruction if available |
| Data and index storage size | Continues to consume corresponding resources | Record and index entries are removed; OS file size may not shrink immediately |
| Standard queries | Must filter for active documents | No need to filter a deleted flag since the document is gone |
| Regular unique index | Soft-deleted records still participate | Unique value is freed after successful deletion |
| Audit | Retains partial metadata directly in the document | History must be stored separately |
| Data erasure policy compliance | May be insufficient because the data remains stored | Must account for backups, replicas, logs, and retention, not just the delete call |

**Neither option is universally better.** An account with a 30-day recovery window may fit soft delete well. Sensitive data whose retention period has expired may require hard delete or deeper erasure workflows. TTL-based logs, documents with legal retention duties, financial transactions, and user profiles may each require completely different policies.

## 2. Soft Delete Modeling: Choosing a Consistent State Contract

There are several ways to represent soft delete:

### 2.1. The `isDeleted` Flag

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

Pros: concise active condition `{ isDeleted: false }`. Cons: a Boolean alone does not tell you **who deleted it or when**.

### 2.2. The `deletedAt` Timestamp

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  deletedAt: null
}
```

A record is soft-deleted by setting `deletedAt` to a BSON Date. Pros: records the deletion timestamp and can serve as the basis for retention policies. However, `{ deletedAt: null }` in MongoDB matches both `null` values and **missing fields**, so you must clearly understand legacy data.

### 2.3. Combining a Flag and Metadata

Recommended model for the examples in this lesson:

```javascript
{
  _id: "U101",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  displayName: "An",
  isDeleted: false,
  createdAt: ISODate("2026-02-01T09:00:00Z"),
  updatedAt: ISODate("2026-02-01T09:00:00Z")
}
```

When deleting, set:

```javascript
{
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z"),
  deletedBy: "admin-42"
}
```

This structure lets **active queries and partial unique indexes share the same explicit `isDeleted: false` condition**, while recording metadata for recovery, auditing, or transitioning to hard delete after the retention window.

In return, the application must keep these fields **semantically synchronized**. If `isDeleted: false` while `deletedAt` still holds a deletion date, different endpoints can interpret the state inconsistently. Choose one field as the **canonical source of truth** (here, `isDeleted`) and enforce update/validation rules to minimize contradictory states.

### 2.4. Why Missing Fields Matter

If an older collection does not yet have `isDeleted`:

```javascript
{ _id: "U100", emailNormalized: "old@example.com" }
```

then the query:

```javascript
db.users.find({ isDeleted: false });
```

will **not** automatically treat documents missing `isDeleted` as active. This can cause legacy accounts to "vanish" from APIs after deploying the new filter.

There are two approaches: migrate all existing active records to `isDeleted: false`, or define a predicate compatible with legacy data. For systems that need a **partial unique index**, migrating to a consistent active representation is usually simpler and easier to operate.

## 3. Hard Delete with `deleteOne()` and `deleteMany()`

### 3.1. `deleteOne()`: Deleting One Matching Document

```javascript
const result = db.users.deleteOne({
  _id: "U101",
  tenantId: "TENANT-A"
});

print(result.deletedCount);
```

This deletes at most **one** document matching the filter; `deletedCount` is normally `0` or `1`. A `0` can happen because the ID does not exist, the tenant does not match, or the document was already deleted.

Filter by both a unique identifier and **access scope**. In a multi-tenant system, passing only `_id` in the filter may be insufficient to enforce authorization boundaries at the data-access layer.

### 3.2. `deleteMany()`: Deleting Multiple Matching Documents

```javascript
const result = db.sessions.deleteMany({
  tenantId: "TENANT-A",
  expiresAt: { $lt: ISODate("2026-04-01T00:00:00Z") }
});

print(result.deletedCount);
```

`deleteMany()` deletes all documents matching the condition at the time of execution according to MongoDB semantics. Using an empty filter `{}` can delete **every document in the collection**:

```javascript
// Dangerous: deletes all documents in the collection.
db.users.deleteMany({});
```

Do not run this on production data without a concrete plan. Bulk delete commands should carry explicit scopes such as `tenantId`, data type, timestamp, and status criteria; the application should log expected vs. actual deleted counts and the executing principal.

### 3.3. Hard Delete Is Not `drop()`

| Operation | Primary effect |
|---|---|
| `deleteOne(filter)` | Deletes at most one document |
| `deleteMany(filter)` | Deletes documents matching the filter |
| `deleteMany({})` | Deletes all documents in the collection while keeping the collection and indexes |
| `drop()` | Removes the entire collection and its indexes |

Do not use `drop()` as a shortcut for "clear all test data and re-import into the same collection" if you need to preserve indexes, validators, or collection options. In production environments, `drop()` has major consequences and requires separate authorization and backup procedures.

### 3.4. Hard Delete and WiredTiger Storage Space

When a hard delete succeeds, the associated records and index entries are removed from logical data structures. However, do not expect the `.wt` file size on the filesystem to shrink immediately by the exact size of the deleted documents: WiredTiger may **retain and reuse free space**. Reclaiming disk space back to the OS is a separate operational topic and depends on version, filesystem, compact/resync mechanisms, and workload.

Likewise, hard delete does not automatically mean data has disappeared from all **backups, snapshots, replicas, or downstream systems**. Data erasure policies must address those locations when required by legal or security mandates.

## 4. Soft Delete with `updateOne()`: Keep the Document, Change State

A soft-delete statement should do at least three things in **the same document update**:

1. Target only the active document for the right tenant/identifier.
2. Set `isDeleted: true`.
3. Record deletion metadata such as `deletedAt` and `deletedBy`.

Example:

```javascript
const result = db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  {
    $set: {
      isDeleted: true,
      deletedBy: "admin-42"
    },
    $currentDate: {
      deletedAt: true,
      updatedAt: true
    }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

When the document is soft-deleted for the first time, `matchedCount`/`modifiedCount` is normally `1`. If the command is repeated after `isDeleted` is already `true`, the `isDeleted: false` filter no longer matches and the result is normally `0`. This avoids overwriting `deletedAt` on routine request retries.

**The condition in the filter is part of concurrency protection.** If a client reads `isDeleted: false` and then sends an update filtering only by `_id`, it may inadvertently overwrite state modified by another concurrent request between the two steps.

### 4.1. Bulk Soft Delete

```javascript
const result = db.users.updateMany(
  {
    tenantId: "TENANT-A",
    isDeleted: false,
    inactiveSince: { $lt: ISODate("2025-01-01T00:00:00Z") }
  },
  {
    $set: {
      isDeleted: true,
      deletedBy: "retention-job"
    },
    $currentDate: { deletedAt: true, updatedAt: true }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

`updateMany()` applies changes across multiple documents. **Each individual document update is atomic**, but the batch as a whole is not by default an all-or-nothing transaction. If an error occurs midway or concurrent modifications happen, some documents may remain un-updated; jobs must be managed with logging, retries, and metrics.

If updating a parent record and multiple child records requires immediate consistency constraints, consider an appropriate transaction or design a propagation mechanism with explicit intermediate states.

### 4.2. Soft Delete vs. Business Status Changes

Not every `status: "INACTIVE"` is a soft delete. A user may have a temporarily suspended account, and an order may be cancelled yet **still required** for accounting. Collapsing "suspended," "cancelled," "archived," and "deleted" into a single Boolean makes many workflows hard to distinguish.

They can be modeled independently:

```javascript
{
  _id: "U101",
  accountStatus: "SUSPENDED", // business status
  isDeleted: false,          // logical existence status
  deletedAt: null
}
```

In some applications, a state machine with `status: "ACTIVE" | "DELETED" | "ARCHIVED"` works better than a Boolean flag, provided index definitions use the matching predicates and all write paths stay consistent.

## 5. Impact on Queries: Soft-Deleted Documents Still Appear If You Forget to Filter

This is the biggest operational difference between soft delete and hard delete:

```javascript
db.users.find({ tenantId: "TENANT-A" });
```

The query above **returns both active and soft-deleted users**, unless an automated control layer reliably injects the filter. MongoDB has no built-in mechanism that "automatically hides documents with `isDeleted: true`" for all commands.

### 5.1. Active Queries

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
});
```

To fetch a single user by email:

```javascript
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

To query deleted documents for administration:

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: true
}).sort({ deletedAt: -1, _id: 1 });
```

Separate **user-facing APIs** from **trash/admin APIs** so an unchecked flag like `includeDeleted=true` cannot leak deleted data.

### 5.2. `countDocuments()` and Pagination

If a dashboard displays the number of active accounts, do not count every document:

```javascript
// May also include soft-deleted accounts.
db.users.countDocuments({ tenantId: "TENANT-A" });

// Count only currently active accounts.
db.users.countDocuments({
  tenantId: "TENANT-A",
  isDeleted: false
});
```

Similarly, paginated queries must place the active condition in the filter **before computing pages**, so you do not end up with short or empty pages after the application layer strips out deleted documents.

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

When using cursor pagination, the sort key and filter must stay consistent across pages. Soft deletions occurring between page fetches can cause result counts to shift; do not promise an immutable snapshot unless an appropriate read mechanism is used.

### 5.3. Aggregation Does Not Automatically Add Soft-Delete Filters

Example aggregating active users by role:

```javascript
db.users.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      isDeleted: false
    }
  },
  {
    $group: {
      _id: "$role",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

If `isDeleted: false` is omitted from `$match`, soft-deleted users will be counted in the report. Placing an appropriate `$match` at the beginning of the pipeline is typically beneficial for narrowing the dataset before grouping, sorting, or joining.

### 5.4. `$lookup`: Do Not Filter Only the Parent Collection

Suppose `orders` references `customers`. Even when querying only active orders, a join can still pull in soft-deleted customers if the lookup pipeline fails to filter properly:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "TENANT-A",
      isDeleted: false
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        customerId: "$customerId",
        tenant: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$customerId"] },
                { $eq: ["$tenantId", "$$tenant"] }
              ]
            }
          }
        },
        { $match: { isDeleted: false } },
        { $project: { _id: 1, displayName: 1 } }
      ],
      as: "customer"
    }
  }
]);
```

Here both `orders` and `customers` are scoped by status and tenant according to the access policy. You may need to re-evaluate the semantics if historical orders **must preserve a snapshot of the customer's name at purchase time**, even if the customer is later soft-deleted. In that case, storing a permitted snapshot on the order may be preferable to a live join against `customers`.

### 5.5. Updates and Hard Deletes Must Also Respect Status

A classic bug:

```javascript
// May also update soft-deleted documents.
db.users.updateOne(
  { _id: "U101" },
  { $set: { displayName: "New Name" } }
);
```

For standard user-facing APIs, use:

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  { $set: { displayName: "New Name" } }
);
```

Not only `find()`, but also `updateOne()`, `replaceOne()`, `countDocuments()`, `aggregate()`, and export code paths must respect deletion status. A shared repository helper or policy-enforcing service layer helps prevent missed filters, while clearly separating active queries from administrative actions that intentionally read deleted records.

## 6. Regular Unique Indexes: Soft Delete Does Not Free the Key

This is the scenario that most often breaks when applying soft delete to emails, usernames, slugs, SKUs, or order codes.

Suppose a unique index is created:

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  { unique: true }
);
```

Initial record:

```javascript
{
  _id: "U101",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

The application soft-deletes it:

```javascript
db.users.updateOne(
  { _id: "U101" },
  {
    $set: { isDeleted: true },
    $currentDate: { deletedAt: true }
  }
);
```

Then it tries to create a new user with the same email:

```javascript
db.users.insertOne({
  _id: "U202",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

**The insert still violates the unique index**, typically raising `E11000 duplicate key error`. Why: a regular unique index still indexes document `U101` because it **has not been hard-deleted**.

There is no MongoDB rule that `isDeleted: true` automatically removes a record from a unique index. This behavior does not depend on whether APIs filter for active records: **uniqueness is enforced by the database on write**, not by a query's result set.

### 6.1. Single-Field Unique Indexes and Missing/Null Values

In a regular single-field unique index, missing or `null` values are indexed according to MongoDB's index rules; multiple documents missing the field or holding `null` can trigger duplicate key collisions. If business logic only requires uniqueness when the field is populated, consider a partial index, schema validation, or a different design.

Do not assume "no email entered" automatically permits unlimited records in a single-field unique index on email.

### 6.2. Is Adding `isDeleted` to a Compound Unique Index Enough?

A common idea:

```javascript
db.users.createIndex(
  { emailNormalized: 1, isDeleted: 1 },
  { unique: true }
);
```

This index lets an email appear once with `isDeleted: false` and once with `isDeleted: true`. However, it **does not allow multiple soft-deleted records with the same email**: after the first user is soft-deleted, if a second user with the same email is created and later soft-deleted, both produce the key `("an@example.com", true)` and collide.

Therefore, a compound unique index `{ emailNormalized, isDeleted }` is **not equivalent** to the rule "only active users' emails must be unique." It may suit a special business rule, but it is usually a poor fit for soft delete where identifiers can be reused multiple times.

## 7. Partial Unique Indexes: Enforcing Uniqueness Only for Active Documents

To allow creating a new account with the email of a soft-deleted account while still ensuring **no two active users share an email**, use a **partial unique index**:

```javascript
db.users.createIndex(
  { emailNormalized: 1 },
  {
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
```

Meaning:

- Only documents satisfying `isDeleted: false` are entered into **this unique index**.
- Two active users cannot share the same `emailNormalized`.
- Documents with `isDeleted: true` do not participate in this index's constraint.
- Multiple deleted documents can reuse the same email, provided no other constraint blocks them.
- When restoring a document back to `isDeleted: false`, the unique constraint is checked again.

**Important:** If the collection still has **an older unique index** on `emailNormalized` without a partial filter, that old index **continues blocking duplicate emails** even after you add the partial unique index. You must plan an index migration rather than just adding a new index and expecting old constraints to disappear.

### 7.1. Uniqueness in Multi-Tenant Systems

If emails are allowed to repeat across tenants but must be unique within each tenant, include `tenantId` in the index:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    name: "uniq_active_email_per_tenant",
    unique: true,
    partialFilterExpression: {
      isDeleted: false
    }
  }
);
```

Rules:

- Within `TENANT-A`, two active users cannot both have `an@example.com`.
- `TENANT-B` can have an active user with that same email.
- Multiple soft-deleted users in the same tenant can retain historical email usage.
- Every read/write operation by email should specify **tenantId** and `isDeleted: false` according to business boundaries.

Insert example:

```javascript
db.users.insertMany([
  {
    _id: "U-A1",
    tenantId: "TENANT-A",
    emailNormalized: "an@example.com",
    isDeleted: false
  },
  {
    _id: "U-B1",
    tenantId: "TENANT-B",
    emailNormalized: "an@example.com",
    isDeleted: false
  }
]);
```

Both documents satisfy the per-tenant partial unique index.

### 7.2. Queries Must Imply the Partial Index Condition

A partial index contains only the documents matching its filter expression. The MongoDB query planner can only use it for queries where using the index **will not miss results**, meaning the query must include conditions compatible with or implying the partial filter.

Example:

```javascript
// Can leverage the partial index on active users.
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Conversely:

```javascript
// To find both active and deleted users, MongoDB cannot rely solely
// on an index that excludes deleted users.
db.users.find({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com"
});
```

The planner may choose a collection scan or another index if appropriate. Partial indexes reduce storage and index-maintenance cost for a meaningful subset, but **cannot replace every index** needed for queries that also include deleted data.

### 7.3. Why Use `isDeleted: false` Instead of `deletedAt: { $exists: false }`?

MongoDB supports specific expressions in `partialFilterExpression`, such as equality, certain range comparisons, `$type`, `$in`, and `$exists: true` depending on supported versions. **Do not assume `$exists: false` is permitted in a partial filter**; it is not generally supported in the same way as `$exists: true`.

With the `isDeleted: false` active convention, a partial index is straightforward to define and query. If you choose `deletedAt: null` to represent active records, note that equality with `null` also matches documents **missing the field**, so filters, indexes, and queries must share consistent semantics. Do not mix multiple active representations in the same collection without migrating.

### 7.4. Normalization and Collation for Unique Identifiers

For emails or usernames, whether `"An@Example.com"` and `"an@example.com"` are considered duplicates depends on business policy and index/collation design.

A common approach is to store a normalized field:

```javascript
{
  email: "An@Example.com",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

The application must normalize according to the agreed product rules. Do not arbitrarily transform complex email addresses with logic that conflicts with identity policy. You can also configure a unique index with a matching collation for case-insensitive string comparison, provided both queries and indexes use the exact same collation rules.

**Partial unique indexes and collation solve two different problems:** the partial filter determines **which documents participate in the constraint**, while collation determines **how string keys are compared**.

### 7.5. Sharding and Unique Indexes

In a sharded collection, unique indexes are subject to constraints involving the **shard key** and deployment version. A unique index that does not include the required shard key may be disallowed or fail to enforce cluster-wide uniqueness as intended.

For instance, enforcing unique emails per tenant on a sharded collection requires evaluating the shard key and valid index shapes; do not assume a standalone partial unique index behaves identically across every topology. Nor is a unique constraint a substitute for a well-distributed shard key design.

## 8. What Happens When You Soft Delete and Re-Register with the Same Email?

This is the core scenario for testing a partial unique index.

**Step 1 — Existing active user:**

```javascript
{
  _id: "U101",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
}
```

**Step 2 — Soft delete U101:**

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: false
  },
  {
    $set: { isDeleted: true, deletedBy: "admin-42" },
    $currentDate: { deletedAt: true }
  }
);
```

**Step 3 — Create new account U202 with the same email:**

```javascript
db.users.insertOne({
  _id: "U202",
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

If only the active partial unique index is present (and no other unique index blocks it), Step 3 succeeds because `U101` left the active key set.

**Step 4 — Attempt to restore U101:**

```javascript
db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: true
  },
  {
    $set: { isDeleted: false },
    $unset: { deletedAt: "", deletedBy: "" }
  }
);
```

The restore command **cannot succeed** if it would produce two active users with the same email in the tenant. MongoDB enforces the unique constraint as `U101` re-enters the `isDeleted: false` subset and raises a duplicate key error.

This is not a bug in the partial index; the index is protecting the business invariant. The application needs a restore policy:

1. **Deny restore** if the email is already in use by another active account.
2. **Require selecting a new identifier**, along with ownership verification.
3. **Merge accounts** via an approved workflow rather than overwriting the new user.
4. **Reserve the identifier** during a grace period if product policy forbids immediate reuse after soft deletion.

Never automatically delete `U202` just to restore `U101`: that risks data loss and violates ownership boundaries.

### 8.1. Race Condition: Two Requests Creating the Same Email

Two requests may concurrently run:

```javascript
db.users.findOne({
  tenantId: "TENANT-A",
  emailNormalized: "an@example.com",
  isDeleted: false
});
```

Both see no active user and both call `insertOne()`. **Checking existence before inserting is insufficient to guarantee uniqueness.** The database's partial unique index is the final line of defense: one insert succeeds, while the other receives a duplicate key error. The application must catch that error and translate it into an appropriate domain response.

Similarly, concurrency between **re-registration** and **restore** is arbitrated by the unique index based on whichever write commits first.

## 9. How Soft Delete Affects Indexes and Performance

Soft delete modifies a record without removing it. Consequences:

- Document data and metadata continue to occupy collection space.
- **Regular indexes** on document fields still hold entries for deleted records.
- **Active partial indexes** remove the document from the index structure when `isDeleted` changes to `true`.
- Updating `isDeleted`, `deletedAt`, and associated indexes still generates I/O, oplog traffic, replication load, and version/page management overhead.
- Queries missing the soft-delete filter may scan many documents that are no longer active in the domain.

### 9.1. Indexes for Active Listings

Example API listing active users by creation time:

```javascript
db.users.createIndex(
  {
    tenantId: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "idx_active_users_by_created",
    partialFilterExpression: { isDeleted: false }
  }
);

db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Because the index stores only active users, it can reduce index size and scan cost for frequent application queries, especially when the deleted ratio is high. Depending on data volume, the query planner, and competing indexes, MongoDB may still select another plan.

### 9.2. Indexes for the Admin Deleted View

An active-only index **does not help list deleted users** by deletion time. If administrative workloads frequently use a "trash" view, you can create a separate index:

```javascript
db.users.createIndex(
  {
    tenantId: 1,
    deletedAt: -1,
    _id: -1
  },
  {
    name: "idx_deleted_users",
    partialFilterExpression: { isDeleted: true }
  }
);

db.users.find({
  tenantId: "TENANT-A",
  isDeleted: true
})
.sort({ deletedAt: -1, _id: -1 })
.limit(20);
```

Not every system needs this index. Every index consumes storage and maintenance overhead during inserts, updates, and deletes; base your decision on query frequency and `explain("executionStats")`.

### 9.3. Why a Composite Index with the Delete Flag Is Not Always Optimal

An index such as:

```javascript
db.users.createIndex({
  tenantId: 1,
  isDeleted: 1,
  createdAt: -1
});
```

can serve both active and deleted queries in some workloads. However, it still stores keys for **both states**, unlike a partial index containing only active records. Choosing between a composite index and a partial index depends on data distribution, query patterns, uniqueness requirements, index count, and write overhead. There is no rule that "partial indexes are always faster."

In particular, indexes used for **uniqueness** must match the invariant; an index tuned for **reads** is not necessarily suitable for enforcing uniqueness.

### 9.4. Using `explain()`

```javascript
db.users.find({
  tenantId: "TENANT-A",
  isDeleted: false,
  emailNormalized: "an@example.com"
}).explain("executionStats");
```

Check:

| Metric / concept | Question |
|---|---|
| `winningPlan` | Which plan did the query planner choose? |
| `IXSCAN` | Which index was used? |
| `COLLSCAN` | Did a collection scan occur? |
| `FETCH` | Did MongoDB need to fetch documents outside the index? |
| `totalKeysExamined` | How many index keys were examined? |
| `totalDocsExamined` | How many documents were examined? |
| `nReturned` | How many documents were returned? |

Adding `isDeleted: false` to queries is not just a business requirement; it also enables the query to satisfy the partial index predicate for the planner.

## 10. Restoring Soft-Deleted Documents

An "Undo delete" feature typically involves these steps:

1. Verify the user is authorized to restore.
2. Read or locate the document with `isDeleted: true` within the tenant scope.
3. Check retention rules, unique key collisions, account ownership, and other constraints.
4. Update the status back to active in an appropriately filtered operation.
5. Log the restoration and reconcile effects with related systems.

Example:

```javascript
const result = db.users.updateOne(
  {
    _id: "U101",
    tenantId: "TENANT-A",
    isDeleted: true
  },
  {
    $set: { isDeleted: false },
    $unset: { deletedAt: "", deletedBy: "" },
    $currentDate: {
      restoredAt: true,
      updatedAt: true
    }
  }
);
```

Here, `$unset` clears deletion metadata from the document (if you need a multi-event delete/restore history, storing separate audit events is better than losing metadata). `restoredAt` records the latest restore timestamp and can be omitted if unneeded.

If the email is currently used by another active user, the unique index will cause the update to fail. **Never catch a duplicate key error and silently report restore success.** Return the conflict state to the admin workflow and let policy dictate the resolution.

### 10.1. Restoring Does Not Automatically Restore All Relationships

If soft-deleting a user revoked tokens, stripped access permissions, archived data, or hard-deleted child records, setting `isDeleted` back to `false` does not automatically reverse those actions. Clearly define **which records can be restored**, **what cannot be restored**, and what compensating steps must run.

For parent–child relationships, reasonable policies include:

- Soft-delete the parent so children are temporarily hidden because the parent is hidden.
- Soft-delete both parent and child independently, tracking reason, timestamp, and state.
- Retain historical transactions rather than deleting them with the user when retention obligations apply, while restricting identifying data according to policy.

Never apply a blanket cascade to every document type while ignoring domain contracts.

## 11. Hard Delete After the Retention Period

Many products use a two-stage lifecycle:

```text
ACTIVE
  |
  | User deletes / admin soft-deletes
  v
SOFT_DELETED ----> RESTORED (if still allowed and no conflict)
  |
  | Retention period expires + condition checks
  v
PURGED / HARD_DELETED
```

Example policy: 30 days after `deletedAt`, a soft-deleted document becomes eligible for purging if there is no legal hold or other business restriction.

### 11.1. Active Purge Job

Example with a precomputed cutoff timestamp:

```javascript
const cutoff = new Date(
  Date.now() - 30 * 24 * 60 * 60 * 1000
);

const result = db.users.deleteMany({
  isDeleted: true,
  deletedAt: { $lte: cutoff },
  legalHold: { $ne: true }
});

print(result.deletedCount);
```

This is an example of a **30-day cutoff calculated in milliseconds** and does not replace organization-specific calendar, timezone, business-day, or legal rules. The filter `legalHold: { $ne: true }` allows documents where the field is missing; if policy requires purging only when explicitly approved via `legalHold: false`, adjust the filter accordingly.

For large collections, run in batches with checkpoints, rate limits, and pause/stop controls. **A single massive `deleteMany()` can generate heavy I/O and replication load.**

### 11.2. Using a TTL Index for Automatic Hard Delete

MongoDB supports **TTL indexes** on date fields to delete documents after an elapsed interval. For soft-deleted documents whose `deletedAt` is a BSON Date, you can create:

```javascript
db.users.createIndex(
  { deletedAt: 1 },
  {
    name: "ttl_deleted_users_after_30_days",
    expireAfterSeconds: 2592000
  }
);
```

The value `2592000` seconds corresponds to 30 days × 24 hours. Given a document:

```javascript
{
  _id: "U101",
  isDeleted: true,
  deletedAt: ISODate("2026-06-15T10:30:00Z")
}
```

TTL deletes documents once they pass the interval from `deletedAt` **via a background process**, without guaranteeing exact millisecond timing. Active documents **must never carry a `deletedAt` field with a past Date**, or TTL could delete them as well. Maintain the invariant that only documents truly eligible for purging have a TTL-monitored `deletedAt`.

A TTL index has no knowledge of domain conditions such as restore disputes, deletion approvals, legal holds, data dependencies, or external system cleanup workflows. If purge policy requires those checks, **a conditional active job** is generally safer than relying solely on TTL.

### 11.3. TTL Characteristics and Limits to Remember

- TTL runs asynchronously via a background thread; expiration does not mean instant deletion.
- TTL requires the timestamp field to be a proper BSON Date; date strings will not be processed as expected.
- A TTL index is a dedicated index type with its own constraints; do not confuse it with a partial unique index used for emails.
- TTL deletion is a **hard delete**, not an automatic update setting `isDeleted` to `true`.
- TTL can create significant delete load when many documents expire simultaneously; monitor system metrics and replication.
- When retention depends on complex conditions, design a dedicated process rather than expecting TTL to inspect business metadata.

## 12. Batch Deletion and Correctness in Bulk Processing

In the "Deletion and Bulk Writes" chapter, distinguish between **a command operating on multiple documents** and **an atomic transaction across the entire batch**.

### 12.1. Hard-Deleting a Set of IDs

```javascript
const ids = ["U101", "U102", "U103"];

const result = db.users.deleteMany({
  tenantId: "TENANT-A",
  _id: { $in: ids },
  isDeleted: true
});

print(result.deletedCount);
```

The `isDeleted: true` condition ensures the purge job only deletes records that have already passed through soft deletion. However, if retention rules apply, also include `deletedAt` and policy constraints rather than relying solely on IDs.

### 12.2. Using `bulkWrite()` for Multiple Delete Operations

```javascript
db.users.bulkWrite(
  [
    {
      deleteOne: {
        filter: {
          _id: "U101",
          tenantId: "TENANT-A",
          isDeleted: true
        }
      }
    },
    {
      deleteOne: {
        filter: {
          _id: "U102",
          tenantId: "TENANT-A",
          isDeleted: true
        }
      }
    }
  ],
  { ordered: false }
);
```

`ordered: false` allows independent operations to proceed even if one hits a write error; `ordered: true` stops according to ordered semantics upon encountering a write error. Neither **guarantees all-or-nothing atomicity** outside a transaction. Never assume a bulk command deleted every ID just because part of it succeeded.

### 12.3. Batching and Access Control

For multi-tenant data deletion, the gravest risk is forgetting scope in the filter. Example:

```javascript
// Risk: may delete another tenant's records if the ID/filter lacks scope.
db.users.deleteMany({ status: "INACTIVE" });
```

In a multi-tenant system, always inject the verified scope from a trusted context rather than taking a tenant ID solely from spoofable user input.

Large systems should follow a batching discipline:

1. Fetch eligible IDs constrained by scope and cutoff.
2. Record job/batch ID, scope, criteria, and execution authorization.
3. Delete in size-bounded batches with explicit timeouts and retry rules.
4. Log deleted counts, errors, and IDs with uncertain outcomes.
5. Reconcile data and related state.
6. Monitor impact on disk I/O, oplog/replication, and downstream jobs.

### 12.4. Are Transactions Necessary for Batch Deletes?

MongoDB supports multi-document transactions on compatible deployments. However, a transaction encompassing hundreds of thousands of deletes can consume heavy resources, run long, and hit conflicts or timeouts. When records are independent and the goal is policy-driven purging, idempotent batching is usually more effective.

Conversely, if deleting one entity must atomically update a few related documents to preserve an invariant, a small transaction may be appropriate. **Do not use a transaction merely because an operation is "bulk"**; base it on genuine business consistency needs.

## 13. Relationships, Auditing, and Security During Deletion

### 13.1. MongoDB Does Not Automatically Cascade Like Relational Foreign Keys

Suppose a user is deleted while `orders.customerId` still references that ID. Even on a hard delete of the user, orders are not automatically removed because MongoDB does not enforce foreign key cascades across standard document collections by default.

Choose an explicit policy:

- Retain order history for accounting compliance, while limiting identifying personal details.
- Soft-delete the user and keep orders with a policy-compliant snapshot of name/address.
- Delete or unlink dependent records via an approved domain workflow.
- Mark a pending status so background consumers clean up child records.

For parent–child pairs queried together, the parent's deleted state can govern child visibility. A child having `isDeleted: false` does not necessarily mean it should be exposed if its parent has been deleted.

### 13.2. Audit Events Should Be Separate from Business Documents

Soft delete lets you inspect `deletedAt` and `deletedBy`, but if the document is later hard-deleted, that metadata vanishes from the collection too. If you need proof of who requested deletion, who approved purging, when it happened, and why, record an **audit event** in an appropriate store:

```javascript
{
  _id: "audit-delete-001",
  eventType: "USER_SOFT_DELETED",
  targetCollection: "users",
  targetId: "U101",
  tenantId: "TENANT-A",
  actorId: "admin-42",
  occurredAt: ISODate("2026-06-15T10:30:00Z"),
  requestId: "req-8a4f"
}
```

Audit logs should not dump all of a user's sensitive data just "in case of restore." The logs themselves require access controls, retention limits, tamper protection, and scheduled deletion per policy.

### 13.3. Soft Delete Is Not Anonymization

When a document still holds `email`, `phone`, `address`, or other sensitive details, soft delete **does not erase the data**. It only alters application visibility rules. If the goal is privacy compliance, evaluate hard deletion, pseudonymization/anonymization where appropriate, backups, replicas, caches, and external systems.

Conversely, a hard delete directly in the database **does not by itself prove** that every copy has been purged from backups or downstream systems. A complete policy documents scope, timelines, and mandatory retention exceptions.

## 14. Migrating from a Regular Unique Index to a Partial Unique Index

Suppose a system currently has:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { name: "uniq_email_all_rows", unique: true }
);
```

Now the product wants to allow re-registering with the email of a soft-deleted account. Plan the migration carefully rather than swapping indexes blindly during peak traffic.

**Step 1 — Lock down the invariant:** emails must be unique among **active users of the same tenant**; soft-deleted users may share emails with each other and with an active user.

**Step 2 — Normalize the schema:** ensure every active user has `isDeleted: false` and every deleted user has `isDeleted: true`. Clean up missing values, `null`s, and mistyped fields before relying on a partial filter.

**Step 3 — Audit uniqueness of the active set:** find `(tenantId, emailNormalized)` pairs with more than one active user and resolve business conflicts before creating the new unique index. If records lack valid IDs, tenants, or `emailNormalized`, handle those edge cases per policy.

An illustrative aggregation:

```javascript
db.users.aggregate([
  { $match: { isDeleted: false } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        email: "$emailNormalized"
      },
      count: { $sum: 1 },
      userIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

This helps detect conflicts. On large datasets, pushing all `userIds` into an array in aggregation can pressure memory; you can count only or cap sample IDs during real audits.

**Step 4 — Create the new partial unique index:** on supported deployments and versions, create the index with a distinct name:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  {
    name: "uniq_active_email_per_tenant",
    unique: true,
    partialFilterExpression: { isDeleted: false }
  }
);
```

**Step 5 — Switch application code:** all registration, restore, existence-check, and active-query flows must adopt the new predicates and semantics. Map duplicate key errors from the unique index to proper domain error messages.

**Step 6 — Drop the old unique index when safe:** the legacy index still enforces uniqueness on deleted rows, so it must eventually be removed to allow identifier reuse. Before dropping it, verify the new index built cleanly and all write paths are compatible:

```javascript
// Execute only after verifying the exact index name and change procedure.
db.users.dropIndex("uniq_email_all_rows");
```

When two indexes share the same key pattern with different options, coexistence rules and limits depend on MongoDB version and configuration; plan an appropriate rollout, monitor index builds, and guard writes during the transition. Never run `dropIndex` blindly.

**Step 7 — Test edge cases:** soft delete followed by re-registration with the same email; creating two active users with the same email; restoring an old user after the email was reused; active and admin queries; concurrent requests; multi-tenancy; email normalization and collation rules.

## 15. Java and Spring Data MongoDB: Enforcing Soft Delete Policy

In Java applications, centralize soft-delete logic in repositories or services rather than expecting every endpoint to remember `isDeleted: false`.

### 15.1. Java Sync Driver: Conditional Soft Delete

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.currentDate;
import static com.mongodb.client.model.Updates.set;

MongoCollection<Document> users =
    database.getCollection("users");

UpdateResult result = users.updateOne(
    and(
        eq("_id", "U101"),
        eq("tenantId", "TENANT-A"),
        eq("isDeleted", false)
    ),
    combine(
        set("isDeleted", true),
        set("deletedBy", "admin-42"),
        currentDate("deletedAt"),
        currentDate("updatedAt")
    )
);

if (result.getModifiedCount() != 1) {
    // Active user not found or state has already changed.
}
```

The driver supports creating partial indexes via `IndexOptions.partialFilterExpression(...)` and unique constraints via `unique(true)`. Exact builder syntax depends on your Java Driver version.

### 15.2. Spring Data MongoDB: Explicit Active Queries and Updates

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
    Criteria.where("_id").is("U101")
        .and("tenantId").is("TENANT-A")
        .and("isDeleted").is(false)
);

Update update = new Update()
    .set("isDeleted", true)
    .set("deletedBy", "admin-42")
    .currentDate("deletedAt")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "users"
);
```

Note that built-in repository methods like `findById()` or `findAll()` **must not be assumed to automatically append a soft-delete filter** unless your codebase has implemented and verified a custom repository/query convention. Expose distinct APIs:

- `findActiveUserById(tenantId, id)`;
- `findDeletedUserForAdmin(tenantId, id)`;
- `softDeleteActiveUser(tenantId, id, actor)`;
- `restoreDeletedUser(tenantId, id, actor)`;
- `purgeExpiredDeletedUsers(cutoff)`.

These method names illustrate service design and are not built-in library methods.

## 16. Decision Matrix by Business Requirement

| Requirement | Approach to evaluate | Notes |
|---|---|---|
| Users get 30 days to recover accounts | Soft delete + metadata + post-retention purge | Email reuse and restore conflict policy |
| Expired temporary logs must be deleted | Batched hard delete or TTL | TTL timing is approximate and incurs background load |
| Email unique only among active accounts | Partial unique index with `isDeleted: false` | All active documents must carry the flag consistently |
| Email must never be reused | Regular unique index or dedicated registry | Soft delete keeping the key locked is the intended behavior |
| Cancelled orders must still be retained | Business status `CANCELLED`, not necessarily soft delete | Audit and domain compliance |
| Historical reports must include deleted records | Admin/report queries intentionally include deleted | Do not force active partial index if it would omit results |
| Public APIs must never expose deleted records | Mandatory active filter in reads/updates/aggregates | Tenant scoping and access control |
| Privacy-compliant data erasure | Policy-driven deletion across storage and backups | Soft delete alone is usually insufficient |
| Deleting an entity with related records | Workflow/transaction or reconciled background job | No default foreign-key cascade |
| Huge collection with mostly deleted rows | Active partial index and retention purge | Evaluate index size, query plans, and I/O |

## 17. Practice Exercises

### Exercise 1 — Observing Soft Delete and Hard Delete

Create a `customersLab` collection with three customers, each having `isDeleted: false`. Perform the following:

1. Soft-delete one customer using `updateOne()` with an `isDeleted: false` filter.
2. Run `find({})` and `find({ isDeleted: false })`, and explain the differing outputs.
3. Use `countDocuments()` to count active vs. deleted records.
4. Hard-delete the soft-deleted customer using `deleteOne()` with a status filter.
5. Check `deletedCount` and verify the document is no longer found in the collection.

### Exercise 2 — Legacy Unique Index Blocking Re-Registration

Create a unique index `{ emailNormalized: 1 }`. Insert `"an@example.com"`, soft-delete the user, then try inserting another user with the same email.

- Predict the error and explain why `E11000` occurs.
- Does querying with `{ isDeleted: false }` cause the unique index to ignore deleted rows?
- Why does `{ emailNormalized: 1, isDeleted: 1 }` with `unique: true` fail to allow a history of multiple soft deletions for the same email?

### Exercise 3 — Designing a Per-Tenant Partial Unique Index

Create the index `{ tenantId: 1, emailNormalized: 1 }` with `unique: true` and `partialFilterExpression: { isDeleted: false }`. Test:

1. Two different tenants having the same active email.
2. Two users in the same tenant with the same active email.
3. Soft-deleting the first user, then creating a new active user with the same email.
4. Restoring the old user while the new user is still active.

Explain why each case is accepted or rejected.

### Exercise 4 — Catching Missing Soft-Delete Filters

A reporting API uses:

```javascript
db.users.aggregate([
  { $match: { tenantId: "TENANT-A" } },
  { $group: { _id: "$role", total: { $sum: 1 } } }
]);
```

Fix it to count only active users. Then inspect an aggregation using `$lookup` from `orders` to `customers` and add appropriate deleted filters on both sides according to access policy.

### Exercise 5 — Designing a 30-Day Purge

Create a soft-deleted document with `deletedAt` as a BSON Date. Compare:

- `deleteMany()` filtering on `isDeleted: true`, `deletedAt <= cutoff`, and `legalHold`.
- A TTL index `{ deletedAt: 1 }` with `expireAfterSeconds: 2592000`.

When is an active job needed due to business conditions? Why does `expireAfterSeconds` not guarantee deletion at millisecond 2,592,000?

### Exercise 6 — Real-World Migration

A system has several million users, an old unique index on `(tenantId, emailNormalized)`, and many soft-deleted accounts. Draft a migration plan to a partial unique index covering `isDeleted` normalization, active duplicate reconciliation, handling the legacy index, code changes, race-condition testing, and rollback if errors are detected.

## 18. MongoDB Documentation References

- [Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/)
- [db.collection.deleteOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/)
- [db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/)
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/)
- [MongoDB Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/)
- [Write Operations Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)

## Conclusion

**Soft delete** is a state update, meaning the document remains in the collection and continues to affect queries, storage, indexes, and uniqueness. **Hard delete** removes the document from the collection, but does not automatically purge data from backups or downstream systems, nor guarantee immediate disk-file shrinkage. Choosing a deletion strategy is therefore a decision about **data lifecycle and business constraints**, not simply swapping `deleteOne()` for `updateOne()`.

When uniqueness is required only among **active** records, a **partial unique index** paired with a consistent active condition is a critical tool. All regular queries must filter out soft-deleted records; restores must check for unique conflicts; and purges must follow retention and authorization policies. When batching, concurrency, multi-tenancy, or auditing are involved, add logging, idempotency, reconciliation, and appropriate transaction boundaries. Done right, the system supports recovery when needed while preserving query semantics and data integrity.
