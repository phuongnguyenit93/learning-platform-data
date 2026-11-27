# Completing CRUD, Array Updates, and Stable Pagination in MongoDB

## 1. Integrated Practice Exercise: Managing Rental Property Listings

In a home-rental service, the **listings** collection stores property listings across multiple tenants. Each listing has a publish status, creation date, monthly rent, tags, and a list of rooms. The API must perform three groups of functions:

1. **CRUD:** create listings, read within the right tenant, perform partial updates, and archive/delete in a controlled manner.
2. **Array updates:** add/remove tags, update a specific room or multiple rooms matching a condition, and avoid replacing the entire array.
3. **Stable pagination:** return pages in an order with a clear tie-breaker, without duplicates or omissions simply because multiple records share the same timestamp; understand the limits when data changes between requests.

If implemented carelessly, common bugs include:

- Updating/deleting based on **_id** while forgetting `tenantId`, leading to modifying another tenant's data.
- **replaceOne** dropping unloaded fields or arrays recently edited by someone else.
- Two requests reading the same document and overwriting each other.
- Using dotted conditions on an **array of embedded documents** while assuming two conditions always apply to the same element.
- Updating **rooms.$** on the wrong element or using **$[]** when intending to modify a single room.
- Using **skip/limit** with a non-unique sort, causing duplicate rows across pages or skipped records during inserts.
- Returning `nextCursor` from the **(pageSize+1)th** document instead of the last returned element, causing skipped records.
- Listings sharing the same timestamp but sorting only by **createdAt**, lacking a total order.

This lesson implements a unified model and dataset that can be run step by step in **mongosh**, then connects it to API/Java design, indexes, concurrency, and testing.

### Objectives

After completing this lesson, you can:

1. Design a document containing embedded rooms, tags, revision, and timestamps.
2. Seed lab data **idempotently** without touching external data.
3. Distinguish **insertOne, find/findOne, updateOne, updateMany, replaceOne, deleteOne**, their results, and side effects.
4. Use **$set, $unset, $inc, $currentDate, $setOnInsert, $push, $addToSet, $pull** for their intended purposes.
5. Use **$elemMatch, positional $ , $[] and $[identifier] + arrayFilters** to query/update array elements.
6. Protect updates using tenant predicates, status predicates, and **revision optimistic locking**.
7. Design **keyset/cursor pagination** with **createdAt DESC, _id DESC** sorting, filters, and a suitable compound index.
8. Distinguish **deterministic pagination order** from **snapshot consistency** when data is concurrently inserted/deleted/edited.
9. Design an opaque, API-verified cursor, cap `pageSize`, and never trust client-modified parameters.
10. Verify behavior, indexes/explain plans, and edge cases using a test matrix.

> **Environment:** Examples use modern MongoDB and `mongosh`, a dedicated database **mongo_crud_pagination_lab_458**, and collection **listings_458**. Each lab document has `labTag` **crud458-v1** and `_id` starting with **l458-**. Never run `deleteMany({})` or drop a collection in a shared environment. Java/Spring Data sections are illustrative application examples; driver/API behavior may vary by version.

## 2. Data Contract and Business Invariants

### 2.1. A Sample Document

~~~javascript
{
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  title: "Apartment 001-01",
  cityCode: "HCM",
  status: "PUBLISHED",
  monthlyRentVnd: NumberDecimal("9250000.00"),
  tags: ["FURNISHED", "HCM"],
  rooms: [
    {
      roomId: "bed-1",
      type: "BEDROOM",
      areaSqm: 17,
      available: false,
      amenities: ["WIFI", "AC"]
    },
    {
      roomId: "kitchen-1",
      type: "KITCHEN",
      areaSqm: 8,
      available: true,
      amenities: ["STOVE"]
    }
  ],
  createdAt: ISODate("2026-01-15T09:00:00Z"),
  updatedAt: ISODate("2026-01-15T09:00:00Z"),
  revision: NumberLong("1")
}
~~~

### 2.2. Rules of the Lesson

| Field | Meaning | Rule |
| --- | --- | --- |
| **_id** | Collection identifier key | Fixed String in the lab, unique |
| **labTag** | Distinguishes lab exercise data | Always scope lab commands |
| **tenantId** | Business access partition | Read/write queries must take it from a trusted auth context |
| **title** | Listing title | Non-empty; validate before writing |
| **cityCode** | City code | Allowed code set per application |
| **status** | DRAFT/PUBLISHED/ARCHIVED | Transition only through valid workflow |
| **monthlyRentVnd** | Monthly rent in VND | Decimal128, non-negative |
| **tags** | Array of String tags | Avoid duplicates when using set semantics |
| **rooms** | Array of embedded rooms | `roomId` unique within one listing per business rule |
| **createdAt** | Creation timestamp | **Immutable** after insert, used as sort key |
| **updatedAt** | Modification timestamp | Updated on write |
| **revision** | Optimistic concurrency token | All cooperating writers must increment properly |
| **deletedAt** | Soft-delete timestamp (if any) | Missing field means not deleted in the lab |

**Note:** MongoDB does not automatically enforce uniqueness of `roomId` **within the same array** via a unique multikey index alone. If each listing must have unique `roomId` values, enforce it in validation/domain logic or adjust the data model accordingly.

### 2.3. Why Choose String _ids?

IDs like **l458-001-01**, **l458-001-02**, ... are zero-padded strings, making lexicographical ordering easy to see in exercises and avoiding confusion with BSON ObjectIds.

In production, ObjectId/UUID/domain IDs can be used. What matters is:

- Using the same BSON type when comparing/querying cursors.
- Sorting `_id` in a stable order.
- Never arbitrarily converting a String ID that looks like an ObjectId into an ObjectId.
- Never relying on predictable IDs as an authorization mechanism.

### 2.4. Root Document and Array Elements

~~~text
Listing document
   |
   +-- _id
   +-- tenantId
   +-- createdAt
   +-- rooms[] ---------------------+
        |                           |
        +-- roomId: "bed-1"         +-- roomId: "kitchen-1"
        +-- type: "BEDROOM"          +-- type: "KITCHEN"
        +-- areaSqm: 17              +-- areaSqm: 8
        +-- available: false         +-- available: true
        +-- amenities[]              +-- amenities[]
~~~

An **updateOne** on a listing has **single-document** atomicity, including changes to `rooms` within the same command. However, two separate updates can still conflict or overwrite each other without proper guards.

## 3. Setting Up an Isolated Lab and Seeding 24 Listings

### 3.1. Dedicated Database and Collection

Open `mongosh` against a local lab MongoDB or an authorized test cluster:

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");
~~~

Do not use a real customer collection.

### 3.2. Seeding Three Tenants, Eight Listings Each

~~~javascript
(() => {
  const lab = db.getSiblingDB(
    "mongo_crud_pagination_lab_458"
  );
  const listings = lab.getCollection("listings_458");
  const tag = "crud458-v1";
  const ops = [];

  for (let tenantNo = 1; tenantNo <= 3; tenantNo++) {
    const code = String(tenantNo).padStart(3, "0");
    const tenantId = "tenant-" + code;

    for (let i = 1; i <= 8; i++) {
      const number = String(i).padStart(2, "0");
      const id = "l458-" + code + "-" + number;
      const cityCode = ["HCM", "HN", "DN"][
        (tenantNo + i) % 3
      ];

      // Two documents share createdAt to practice the tie-breaker.
      const hour = 8 + Math.floor((i - 1) / 2);
      const createdAt = new Date(
        Date.UTC(2026, 0, 15, hour, 0, 0)
      );

      const doc = {
        _id: id,
        labTag: tag,
        tenantId,
        title: "Apartment " + code + "-" + number,
        cityCode,
        status: i % 3 === 0 ? "DRAFT" : "PUBLISHED",
        monthlyRentVnd: NumberDecimal(
          String(8000000 + tenantNo * 1000000
            + i * 250000) + ".00"
        ),
        tags: ["FURNISHED", cityCode],
        rooms: [
          {
            roomId: "bed-1",
            type: "BEDROOM",
            areaSqm: 16 + i,
            available: i % 2 === 0,
            amenities: ["WIFI", "AC"]
          },
          {
            roomId: "kitchen-1",
            type: "KITCHEN",
            areaSqm: 8,
            available: true,
            amenities: ["STOVE"]
          }
        ],
        createdAt,
        updatedAt: createdAt,
        revision: NumberLong("1")
      };

      ops.push({
        replaceOne: {
          filter: { _id: id, labTag: tag },
          replacement: doc,
          upsert: true
        }
      });
    }
  }

  const result = listings.bulkWrite(
    ops, { ordered: false }
  );

  printjson({
    matched: result.matchedCount,
    insertedByUpsert: result.upsertedCount,
    labDocuments: listings.countDocuments({
      labTag: tag
    })
  });
})();
~~~

Expected result on an empty lab collection: **24 documents**, three tenants, eight documents per tenant. There are **two documents sharing each `createdAt`** hourly mark within a tenant. Each tenant has **six PUBLISHED and two DRAFT** listings because `i=3,6` are `DRAFT`.

The script is re-runnable: it replaces only documents matching both `_id` **and** `labTag` with the initial fixture. This **resets any changes you made to those fixtures**, so re-run it only when you want to reset the lab. If another document shares `_id` without `labTag`, upsert may fail with a duplicate-key error rather than overwriting it. Do not drop the collection to bypass such conflicts.

### 3.3. Checking Distribution

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");

printjson(listings.aggregate([
  { $match: { labTag: "crud458-v1" } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        status: "$status"
      },
      n: { $sum: 1 }
    }
  },
  { $sort: { "_id.tenantId": 1, "_id.status": 1 } }
]).toArray());
~~~

Expected:

~~~text
tenant-001: DRAFT 2, PUBLISHED 6
tenant-002: DRAFT 2, PUBLISHED 6
tenant-003: DRAFT 2, PUBLISHED 6
~~~

### 3.4. Checking Duplicate Timestamps

~~~javascript
printjson(listings.aggregate([
  {
    $match: {
      labTag: "crud458-v1",
      tenantId: "tenant-001"
    }
  },
  {
    $group: {
      _id: "$createdAt",
      n: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray());
~~~

Each `createdAt` has two `_id`s. The dataset is intentionally structured this way to demonstrate that sorting by timestamp alone is insufficient for stable pagination.

## 4. Access Control and Safety Rules Before Any CRUD

### 4.1. Always Scope by Tenant

**Insufficient:**

~~~javascript
listings.updateOne(
  { _id: "l458-002-01" },
  { $set: { title: "Modified" } }
);
~~~

If a request belongs to `tenant-001` and guesses an `_id` from `tenant-002`, this command could modify another tenant's data.

**Correct in the lab:**

~~~javascript
listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  { $set: { title: "Updated Title" } }
);
~~~

In a real product, `tenantId` must be obtained from a **server-verified security principal/session/token**. Client-supplied `tenantId` parameters or self-declared headers are never authorization.

### 4.2. The deletedAt Condition

In the lab, non-deleted documents **do not have the `deletedAt` field**. Therefore, "active" queries can use:

~~~javascript
{ deletedAt: { $exists: false } }
~~~

This **differs** from:

~~~javascript
{ deletedAt: null }
~~~

because `null` equality matches both explicit `null` and missing fields. Define a single consistent state from initial schema design to avoid drift.

### 4.3. ID Types and Input Validation

Block bad inputs:

- Empty or malformed IDs.
- Empty `tenantId` or one not belonging to the principal.
- Overly long or empty `title`.
- Negative price, wrong currency, or wrong BSON type.
- Duplicate `roomId`.
- Overly large `pageSize`.
- Arbitrary sort fields causing heavy scans.
- Client-supplied raw MongoDB operators.

Never merge raw request JSON into filter/update objects without whitelisting field names. Prevent **NoSQL injection/operator injection** with typed DTOs, validation, and safe query builders.

### 4.4. Do Not Treat matchedCount == 0 as Always Not Found

An update with filter:

~~~javascript
{
  _id: id,
  tenantId,
  revision: NumberLong("3")
}
~~~

returns `matchedCount=0` when:

- The document does not exist.
- The document belongs to another tenant.
- The document was soft-deleted.
- The revision changed.
- The status does not satisfy the predicate.

The API may return 404/409 per policy, while distinguishing behaviors cleanly and avoiding cross-tenant data leakage.

## 5. CREATE: insertOne and Duplicate Key Control

### 5.1. Creating a Well-Typed Document

In the lab, create a new listing outside the seed set:

~~~javascript
const created = {
  _id: "l458-created-001",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  title: "New Studio",
  cityCode: "HCM",
  status: "DRAFT",
  monthlyRentVnd: NumberDecimal("11000000.00"),
  tags: ["FURNISHED"],
  rooms: [
    {
      roomId: "bed-1",
      type: "BEDROOM",
      areaSqm: 20,
      available: true,
      amenities: ["WIFI"]
    }
  ],
  createdAt: ISODate("2026-01-16T08:00:00Z"),
  updatedAt: ISODate("2026-01-16T08:00:00Z"),
  revision: NumberLong("1")
};

printjson(listings.insertOne(created));
~~~

This operation has a **side effect** in the lab database. Running it twice with the same `_id` triggers a **duplicate key** error rather than creating a second document. A deterministic `_id` is used here for easy observation.

### 5.2. Do Not Use ObjectId to Replace Business Validation

MongoDB automatically generates an `_id` if you omit it; ObjectId has very high uniqueness and is convenient, but:

- It does not validate ownership.
- It does not protect against duplicate business requests.
- It does not guarantee POST idempotency.

If a client retries creating a booking/listing after a timeout, the server can create two documents with different `_id`s unless an **idempotency key** or business uniqueness constraint is designed.

### 5.3. Insert, Save, and Upsert Differ

| Operation | Prior Document with `_id` | Behavior |
| --- | --- | --- |
| **insertOne** | If `_id` collides | Duplicate key error |
| **replaceOne** without upsert | Matches filter | Replaces content of matched document |
| **updateOne** without upsert | Matches filter | Modifies specified fields/operators |
| **updateOne** with `upsert:true` | No match | Creates document from filter and update per upsert rules |

An application using an ORM/repository **save** may issue either an insert or a replace/upsert by ID. Do not use full-entity `save` as a safe substitute for partial updates when concurrent writers exist.

### 5.4. Idempotent Create Using a Request Key

In production, if business rules require one request to create at most one listing, you can:

- Derive `idempotencyKey` from the validated client request.
- Store **tenantId + idempotencyKey** with a matching unique index.
- On retry, return the existing result if the request body matches the contract.
- Never turn every duplicate-key error into success: verify payload and authorization.

Example index design:

~~~javascript
// Illustrative only when the entire collection follows the request-key schema/policy.
// Do not run immediately on the lab collection if documents lack the key:
// { tenantId: 1, idempotencyKey: 1 }, unique: true
~~~

Unique indexes on missing/null fields have semantics that must be handled with schema validation or a **partial unique index** with proper criteria. Do not add a unique index on two missing fields to an existing collection expecting legacy documents to automatically comply.

## 6. READ: Filter, Projection, Count, and Sort

### 6.1. Reading One Listing Scoped by Tenant

~~~javascript
printjson(listings.findOne({
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  deletedAt: { $exists: false }
}));
~~~

Filter by tenant server-side directly in MongoDB; do not fetch by `_id` and check tenant in Java unnecessarily.

### 6.2. Fetching Only Needed Fields

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  deletedAt: { $exists: false }
}, {
  _id: 1,
  title: 1,
  cityCode: 1,
  monthlyRentVnd: 1,
  createdAt: 1
}).sort({
  createdAt: -1,
  _id: -1
}).toArray());
~~~

Projection reduces data transferred to the client. MongoDB always includes **_id** in projections unless you explicitly specify **_id:0**.

### 6.3. Exact Count by Filter

~~~javascript
printjson({
  publishedTenant1: listings.countDocuments({
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  })
});
~~~

In the freshly seeded lab, the result is **6**. If you modify statuses or soft-delete records in later steps, this count may change.

**estimatedDocumentCount()** is a collection-level estimate and does not replace filtered `countDocuments` when the API needs the count matching a tenant/status.

### 6.4. Nested Queries Must Distinguish Same-Element Matching

~~~javascript
// Can match type from room A and area from room B:
{
  "rooms.type": "BEDROOM",
  "rooms.areaSqm": { $gte: 20 }
}
~~~

If you require **the same room to be both a BEDROOM and have area >= 20**, use:

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  rooms: {
    $elemMatch: {
      type: "BEDROOM",
      areaSqm: { $gte: 20 }
    }
  }
}, {
  _id: 1, title: 1, rooms: 1
}).toArray());
~~~

This is a semantic difference, not merely a performance one.

## 7. UPDATE: Modifying Only Needed Fields

### 7.1. $set and $currentDate

Example renaming listing **l458-created-001**:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      title: "New Studio Near Park"
    },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

If you haven't run the CREATE step yet, `matchedCount=0`; that is not a syntax error.

### 7.2. $unset Removes a Field

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $unset: { optionalNote: "" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Calling `$unset` on a nonexistent field makes no change to that field; with `$inc`/`$currentDate`, the document is still updated. Do not confuse missing fields with explicit `null`.

### 7.3. Avoid Creating Unintended Fields via Typos in $set Paths

If code accidentally writes:

~~~javascript
{ $set: { monhtlyRentVnd: NumberDecimal("10000000") } }
~~~

MongoDB may create a **misspelled field** instead of updating `monthlyRentVnd`. Use typed DTOs, constants, schema validation, and integration tests to catch field name errors.

### 7.4. updateOne vs. updateMany

**updateOne** modifies at most one matching document. **updateMany** modifies all matches, suited for controlled batch operations with explicit predicates:

~~~javascript
// Run intentionally in the lab only:
printjson(listings.updateMany(
  {
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "DRAFT",
    deletedAt: { $exists: false }
  },
  {
    $set: { reviewState: "PENDING" },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

The command does not affect other tenants, though it may modify both DRAFT listings of `tenant-001`. In production, consider batch sizes, write pressure, and concurrent updates.

### 7.5. matchedCount and modifiedCount

`UpdateResult` typically includes:

- **matchedCount:** number of documents matching the filter.
- **modifiedCount:** number of documents actually modified.
- **upsertedId:** ID of the newly created document if an upsert inserted one.

A `$set` setting the exact same existing value can yield `matchedCount=1` and `modifiedCount=0` if nothing else changed. In examples that include `$inc`, `revision` increments so `modifiedCount` is typically `1`.

## 8. replaceOne: Valid, but Understand the Risks

### 8.1. Replacement Differs from Update

~~~javascript
// DO NOT run on a listing fixture unless you intentionally want
// to replace the entire document:
listings.replaceOne(
  { _id: "l458-001-01", tenantId: "tenant-001" },
  {
    _id: "l458-001-01",
    tenantId: "tenant-001",
    title: "Only a few fields left"
  }
);
~~~

If matched, fields like `rooms`, `createdAt`, `revision`, and `labTag` will be **lost**. Replacement semantics are completely different from `$set` on `title`.

### 8.2. When Is Replacement Appropriate?

- Replacing the entire document under an explicit contract.
- Data is lock/version-guarded to prevent lost updates.
- Validation ensures all required fields are preserved.
- Handling of unknown fields/schema evolution is well-defined.

Replacing a nested object behaves similarly:

~~~javascript
{ $set: { rooms: [] } }
~~~

**replaces the entire array**, rather than modifying one room.

## 9. Atomicity and Optimistic Concurrency with Revision

### 9.1. A Single Update Command on One Document Is Atomic

~~~javascript
listings.updateOne(
  { _id: id, tenantId: tenant },
  {
    $set: {
      title: newTitle,
      status: "PUBLISHED"
    },
    $inc: { revision: NumberLong("1") }
  }
);
~~~

Changes to the same document within a single valid update are applied atomically. However, **two separate requests** can still race against each other.

### 9.2. Lost Update

~~~text
T0: Request A reads revision=3
T1: Request B reads revision=3
T2: Request A writes title "A", revision=4
T3: Request B replaces entire document from stale snapshot
    -> title "A" may be lost
~~~

### 9.3. Compare-and-Set (CAS)

Example on a fixture still at `revision=1` after seeding:

~~~javascript
const result = listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    revision: NumberLong("1"),
    deletedAt: { $exists: false }
  },
  {
    $set: {
      title: "Revision-guarded update"
    },
    $inc: {
      revision: NumberLong("1")
    },
    $currentDate: { updatedAt: true }
  }
);

printjson(result);
~~~

The first run yields `matchedCount=1` if the fixture hasn't been edited. On the second run, `revision` is now `2`, so `matchedCount=0`. That is a **conflict/no-match**—never blindly retry with `revision=1`.

### 9.4. When matchedCount == 0

A service typically:

1. Checks whether the document exists within the tenant, following policies that never leak cross-tenant existence.
2. If the record exists with a different revision, returns **409 Conflict** or reloads and reapplies the business command if valid.
3. Never drops the revision predicate just to "force the update to succeed."

### 9.5. Revision Only Works If All Writers Comply

If an admin script edits `rooms` **without incrementing `revision`**, service-level CAS cannot detect the change. Every write path must follow the contract: APIs, workers, batch importers, migrations, and support tooling.

### 9.6. Conditional State Transitions

Allow publishing only from `DRAFT`:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "DRAFT",
    deletedAt: { $exists: false }
  },
  {
    $set: { status: "PUBLISHED" },
    $currentDate: { updatedAt: true },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

The filter guards the business transition inside the atomic update: if two requests attempt to publish the same listing concurrently, at most one can match `DRAFT`.

## 10. Tags Array: $push, $addToSet, and $pull

### 10.1. $push Allows Duplicates

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $push: { tags: "NEAR_PARK" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Running this again appends **NEAR_PARK** multiple times.

### 10.2. $addToSet for Value-Based Uniqueness

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $addToSet: {
      tags: { $each: ["NEAR_PARK", "BALCONY"] }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

`$addToSet` prevents inserting **equal values** into an array, though it does not deduplicate preexisting duplicates. For embedded documents, equality depends on full document structure/values, not uniqueness of a single field such as `roomId`.

### 10.3. $pull Removes by Value

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: { tags: "NEAR_PARK" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

`$pull` removes matching elements; if duplicates already existed, it removes **all matching elements**.

### 10.4. $push Modifiers

MongoDB supports modifiers for `$push` such as:

- **$each:** append multiple elements.
- **$slice:** cap the array size after pushing.
- **$sort:** sort the array during the operation.
- **$position:** insertion index.

Example keeping the **five most recent changes** in a small bounded array when approved by design:

~~~javascript
{
  $push: {
    recentNotes: {
      $each: ["Updated title"],
      $slice: -5
    }
  }
}
~~~

Never embed unbounded event histories inside a listing. If a listing can accumulate millions of events, use a separate collection instead of an array that could exceed 16 MiB.

## 11. Rooms Array: Matching a Single Element with $elemMatch

### 11.1. Querying for at Least One Large Room

~~~javascript
printjson(listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  rooms: {
    $elemMatch: {
      type: "BEDROOM",
      areaSqm: { $gte: 20 },
      available: true
    }
  }
}, {
  _id: 1,
  title: 1,
  rooms: 1
}).toArray());
~~~

`$elemMatch` requires all conditions to hold on the **same array element**, unlike multiple separate dotted predicates.

### 11.2. Do Not Use Whole-Document Equality When Filtering Only by roomId

Wrong way to search by `roomId`:

~~~javascript
{ rooms: { roomId: "bed-1" } }
~~~

This compares against the **entire array/embedded document value**, and does not mean "some element in `rooms` has `roomId` `bed-1`" as beginners often expect.

Use:

~~~javascript
{ "rooms.roomId": "bed-1" }
~~~

or `$elemMatch` when multiple conditions must apply to the same element.

## 12. Positional $: Updating a Matched Array Element

### 12.1. First $

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    "rooms.roomId": "bed-1"
  },
  {
    $set: {
      "rooms.$.available": true
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

Positional **$** refers to the **first array element matched by the query** in supported scenarios. The query must include a matching array condition. Do not use `$` without identifying the array element in the filter.

### 12.2. Limitations of Positional $

- If multiple elements share the same `roomId`, only one matching element is updated.
- If the query has multiple array conditions, matching semantics can become complex or ambiguous.
- Not suitable for all nested arrays or operations meant to update multiple matching elements.
- Does not replace business validation of **unique `roomId`**.

When you need explicit element selection criteria and want to update one or multiple elements, use **$[identifier] + arrayFilters**.

## 13. Filtered Positional: $[room] and arrayFilters

### 13.1. Updating a Room by roomId

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      "rooms.$[room].areaSqm": 24
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "room.roomId": "bed-1" }
    ]
  }
));
~~~

**rooms.$[room].areaSqm** updates `areaSqm` on every `rooms` element aliased as **room** that matches `arrayFilters`.

If two elements share the same `roomId`, both will be updated. Therefore:

- Validate `roomId` uniqueness within a listing.
- Do not expect positional syntax to enforce uniqueness automatically.
- If business logic requires updating exactly one element, its identifier must be unique.

### 13.2. Multiple Conditions on the Same Room

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $set: {
      "rooms.$[r].available": false
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      {
        "r.type": "BEDROOM",
        "r.areaSqm": { $gte: 18 }
      }
    ]
  }
));
~~~

Conditions sharing identifier `r` apply to **a single room element**. `updateOne` only limits the number of **root documents** modified; it does not limit modification to **one matching array element** if `arrayFilters` matches multiple elements.

### 13.3. arrayFilters and Restricted Operators

Not every MongoDB expression is valid inside `arrayFilters`; documentation restricts operators such as **$expr, $text, $where**. Check your server version and use supported predicates rather than copying raw user expressions into `arrayFilters`.

### 13.4. Nested Room Amenities Array

Add amenities to `bed-1` without duplicating String values:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $addToSet: {
      "rooms.$[r].amenities": {
        $each: ["WIFI", "ELEVATOR"]
      }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.roomId": "bed-1" }
    ]
  }
));
~~~

This updates an embedded array field of the matching room without replacing the entire `rooms` array.

### 13.5. $pull an Amenity from a Room

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-01",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: {
      "rooms.$[r].amenities": "AC"
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.roomId": "bed-1" }
    ]
  }
));
~~~

Never remove the entire room just to delete one amenity element.

## 14. All Positional: $[] and Updating Multiple Elements

### 14.1. Updating Every Room in a Listing

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $set: {
      "rooms.$[].available": false
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

**$[]** affects **every element in `rooms`** within the matched document, not just `BEDROOM`s. Use it only when the true business intent is "close all rooms."

### 14.2. $[] vs. $[r]

| Syntax | Scope |
| --- | --- |
| **rooms.$.available** | First array element matched by the query per positional semantics |
| **rooms.$[].available** | Every element in `rooms` |
| **rooms.$[r].available** | Every element matching `arrayFilters` for `r` |

Never use `$[]` for an operation targeting a specific `roomId`.

### 14.3. updateMany and arrayFilters

If you want to update all `BEDROOM`s across **all listings in `tenant-001`**, carefully choose the root scope:

~~~javascript
// Lab only; has side effects across multiple listings:
printjson(listings.updateMany(
  {
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: {
      "rooms.$[r].available": true
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    arrayFilters: [
      { "r.type": "BEDROOM" }
    ]
  }
));
~~~

The impact spans **multiple root documents and matching room elements**. Using `updateMany` requires careful scope review because a missing tenant predicate can alter data very broadly.

### 14.4. Removing a Room Element by Condition

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-001-02",
    labTag: "crud458-v1",
    tenantId: "tenant-001"
  },
  {
    $pull: {
      rooms: { roomId: "kitchen-1" }
    },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  }
));
~~~

This removes **every room element** with `roomId` `kitchen-1`, rather than deleting the collection document. In real business logic, check invariants like "a listing must have at least one room" or existing references before removing.

## 15. Atomic Read-and-Update with findOneAndUpdate

### 15.1. When You Want the Updated Document Returned

~~~javascript
const updated = listings.findOneAndUpdate(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: { title: "Edited Studio" },
    $inc: { revision: NumberLong("1") },
    $currentDate: { updatedAt: true }
  },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      tenantId: 1,
      title: 1,
      revision: 1,
      updatedAt: 1
    }
  }
);

printjson(updated);
~~~

Exact return behavior depends on mongosh/driver versions; in standard mongosh APIs, **returnDocument:"after"** returns the post-update document. If no document matches, the result may be `null`. Never blindly treat `null` as success.

### 15.2. Benefits

- Filtering and updating execute as a single atomic operation on one root document.
- Eliminates read-then-update-then-read across three round-trips just to obtain the post-write state.
- Can combine `revision` and `status` predicates.

### 15.3. Limitations

`findOneAndUpdate` does not provide a multi-document transaction. If the operation must also write an audit event to another collection, design appropriate consistency/transaction/outbox handling.

## 16. DELETE: Soft Delete and Hard Delete

### 16.1. Soft Delete Is Preferred When Recovery/Audit Is Needed

Example soft-deleting the listing just created:

~~~javascript
printjson(listings.updateOne(
  {
    _id: "l458-created-001",
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    deletedAt: { $exists: false }
  },
  {
    $set: { status: "ARCHIVED" },
    $currentDate: {
      deletedAt: true,
      updatedAt: true
    },
    $inc: { revision: NumberLong("1") }
  }
));
~~~

The document remains in MongoDB; active queries using `deletedAt: { $exists: false }` will exclude it.

### 16.2. Soft Delete Does Not Automatically Protect Every Query

If a read API queries only:

~~~javascript
{ _id: "l458-created-001" }
~~~

it will still return the `ARCHIVED`/soft-deleted document. Apply active filters consistently across all query paths and control access to archived records.

### 16.3. Conditional Hard Delete

In the lab only, e.g. deleting the document you created:

~~~javascript
printjson(listings.deleteOne({
  _id: "l458-created-001",
  labTag: "crud458-v1",
  tenantId: "tenant-001"
}));
~~~

The result has `deletedCount` of `1` if matched; running it again yields `0`. Never use `deleteMany({})` to reset production.

### 16.4. Bulk Deletion

`deleteMany` can remove many documents; use it only in approved jobs with strict filters and backups/audits. Risks include:

- Filters missing `tenantId`.
- Existing relationships/references left dangling.
- Change Streams, replication lag, and write load.
- Races with concurrent inserts.
- No rollback without backups/retention.

For lab cleanup, prefer **resetting only the seeded IDs** rather than wiping unfamiliar collections.

## 17. Bulk Writes and Partial Error Handling

### 17.1. Why Use Bulk?

Operations updating many listings can use **bulkWrite** to reduce round-trips, though it is not automatically a multi-document transaction.

~~~javascript
const bulkResult = listings.bulkWrite([
  {
    updateOne: {
      filter: {
        _id: "l458-001-04",
        labTag: "crud458-v1",
        tenantId: "tenant-001"
      },
      update: {
        $set: { reviewState: "CHECKED" },
        $inc: { revision: NumberLong("1") }
      }
    }
  },
  {
    updateOne: {
      filter: {
        _id: "l458-001-05",
        labTag: "crud458-v1",
        tenantId: "tenant-001"
      },
      update: {
        $set: { reviewState: "CHECKED" },
        $inc: { revision: NumberLong("1") }
      }
    }
  }
], {
  ordered: false
});

printjson(bulkResult);
~~~

### 17.2. Ordered vs. Unordered

- **ordered:true:** operations execute sequentially and stop on error per bulk semantics.
- **ordered:false:** MongoDB may continue executing remaining operations; do not assume execution order.

If an operation fails, inspect **writeErrors/partial results** rather than assuming total success or full rollback.

### 17.3. When a Transaction Is Needed

A listing and an audit document in two collections may require an **all-commit or all-rollback** invariant. On a MongoDB deployment supporting multi-document transactions, transactions can be used—provided you account for performance, retry semantics, session/transaction options, and topology constraints.

Multiple updates within **the same document** are already atomic; never use a multi-document transaction just because two fields inside `rooms` are updated.

## 18. Pagination with skip/limit: Simple but Flawed

### 18.1. Offset Formula

~~~javascript
const pageNumber = 3;
const pageSize = 2;

const rows = listings.find({
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED",
  deletedAt: { $exists: false }
}, {
  _id: 1, title: 1, createdAt: 1
})
.sort({ createdAt: -1, _id: -1 })
.skip((pageNumber - 1) * pageSize)
.limit(pageSize)
.toArray();

printjson(rows);
~~~

Offset pagination suits small datasets or admin UIs with few pages. Drawbacks:

- Large skips must traverse many index keys/records.
- When documents are inserted or deleted before the offset, later pages can show duplicates or skip items.
- Without a unique tie-breaker in the sort, order among records sharing `createdAt` is nondeterministic.

### 18.2. Example of Duplicate Page Items on New Insert

Page 1 at T0:

~~~text
Sort descending:
  A, B, C, D, E, F

Page size=2
Page 1: A, B
~~~

Before fetching page 2, a new listing X is inserted at the top:

~~~text
X, A, B, C, D, E, F
~~~

Querying **skip(2).limit(2)** at T1 returns:

~~~text
B, C
~~~

B appears twice. This instability comes from **offset shifting**, even when the sort has a tie-breaker.

### 18.3. Always Define a Total Sort Order First

Even if you keep using offset pagination, define a deterministic sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

Never use only:

~~~javascript
{ createdAt: -1 }
~~~

because multiple records can share the exact same timestamp.

## 19. Keyset/Cursor Pagination: Filtering by the Last Page Key

### 19.1. Core Idea

With sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

we take **`createdAt` and `_id` of the last record on the current page**, then query for records appearing **after** it in descending order.

Example:

~~~text
createdAt DESC, _id DESC

10:00, ID=F
10:00, ID=E
09:00, ID=D
09:00, ID=C
08:00, ID=B
08:00, ID=A

Page size 2:
  Page 1 = F, E
  after = (10:00, E)

Page 2:
  09:00 D, 09:00 C
~~~

When `createdAt` ties, `_id DESC` preserves order.

### 19.2. "Less Than Last Tuple" Condition for DESC/DESC

Given cursor **lastAt, lastId**, subsequent records satisfy:

~~~javascript
{
  $or: [
    {
      createdAt: { $lt: lastAt }
    },
    {
      createdAt: lastAt,
      _id: { $lt: lastId }
    }
  ]
}
~~~

This is a lexicographical tuple comparison:

~~~text
(createdAt, _id) < (lastAt, lastId)
~~~

when **both fields are sorted descending**.

If either sort direction changes to ASC, the comparison operator must flip accordingly; never copy the DESC/DESC predicate blindly for other sort directions.

### 19.3. Why Is _id Necessary?

Two documents sharing `createdAt`:

~~~text
2026-01-15 11:00Z, l458-001-07
2026-01-15 11:00Z, l458-001-08
~~~

If the cursor only stores `lastAt` and queries **`createdAt < lastAt`**, documents sharing the same timestamp across a page boundary are skipped. `_id` provides a unique tie-breaker.

### 19.4. Conditions for Deterministic Ordering

- **createdAt** must exist and be a valid BSON Date.
- **_id** must be unique with a consistent BSON type.
- Sort keys must be stored and immutable throughout the document's lifecycle.
- Filters (tenant/status/etc.) must remain consistent across pages.
- Cursor must carry the exact last returned tuple.
- Sort direction must not change between requests.

This gives **deterministic ordering** when reading a set of documents at a point in time. It **does not automatically provide a frozen snapshot across multiple HTTP requests**.

## 20. Keyset Pagination Lab: Runnable mongosh Function

### 20.1. The getPage458 Function

The function below uses **stored BSON field names** and returns the next cursor as a plain JavaScript object for learning. Production backends should sign/opaque-encode tokens.

~~~javascript
function getPage458(
    listings,
    tenantId,
    pageSize,
    after = null) {
  if (!/^tenant-[0-9]{3}$/.test(tenantId)) {
    throw new Error("Invalid tenantId");
  }
  if (!Number.isInteger(pageSize)
      || pageSize < 1 || pageSize > 10) {
    throw new Error("pageSize must be 1..10");
  }

  const base = {
    labTag: "crud458-v1",
    tenantId,
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  };

  let filter = base;
  if (after !== null) {
    if (!(after.createdAt instanceof Date)
        || Number.isNaN(after.createdAt.getTime())
        || typeof after.id !== "string"
        || !after.id) {
      throw new Error("Invalid cursor");
    }

    filter = {
      $and: [
        base,
        {
          $or: [
            {
              createdAt: { $lt: after.createdAt }
            },
            {
              createdAt: after.createdAt,
              _id: { $lt: after.id }
            }
          ]
        }
      ]
    };
  }

  const rows = listings.find(filter, {
    _id: 1,
    tenantId: 1,
    title: 1,
    status: 1,
    createdAt: 1
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize + 1)
  .toArray();

  const hasNext = rows.length > pageSize;
  const items = rows.slice(0, pageSize);
  const last = items[items.length - 1];

  return {
    items,
    hasNext,
    nextAfter: hasNext && last ? {
      createdAt: last.createdAt,
      id: last._id
    } : null
  };
}
~~~

### 20.2. Fetching Pages 1, 2, 3

~~~javascript
const lab = db.getSiblingDB(
  "mongo_crud_pagination_lab_458"
);
const listings = lab.getCollection("listings_458");

const p1 = getPage458(
  listings, "tenant-001", 2
);
printjson(p1);

if (p1.nextAfter) {
  const p2 = getPage458(
    listings,
    "tenant-001",
    2,
    p1.nextAfter
  );
  printjson(p2);

  if (p2.nextAfter) {
    const p3 = getPage458(
      listings,
      "tenant-001",
      2,
      p2.nextAfter
    );
    printjson(p3);
  }
}
~~~

With the **original seed**, each tenant has six PUBLISHED documents, so `pageSize=2` yields **three pages of two items**. The third page has no `nextAfter`.

If you modified statuses, deleted documents, or ran earlier update exercises, counts may differ. Re-run the seed script when comparing against baseline numbers (seeding resets fixture documents).

### 20.3. The pageSize+1 Rule

To know whether another page exists:

1. Query **pageSize + 1** records.
2. Return at most the first **pageSize** records.
3. **hasNext = true** if an extra record was retrieved.
4. **nextAfter** must be the key of the **last returned record**.

Never use the tuple of the **extra record** (the `(pageSize+1)th` element) as `nextAfter`, because it has not been sent to the client and would be skipped on the next request.

### 20.4. The Final Page Cursor

If there is no extra record, **`hasNext=false, nextAfter=null`**. There is no need to issue a next token. Do not assume "another page exists" simply because the response has exactly `pageSize` items—it might be the final page.

### 20.5. A Cursor Is Query Data, Not Authorization

In the lab, the caller can freely edit the `after` object. In production, never let clients alter tokens to bypass access controls; always enforce **tenantId from the auth principal**, and validate cursor integrity and filter compatibility.

## 21. Compound Index for Keyset Pagination

### 21.1. Index for the Standard Query

~~~javascript
listings.createIndex(
  {
    labTag: 1,
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  {
    name: "ix458_lab_tenant_status_created_id"
  }
);
~~~

Because the lab query filters with equality on **labTag, tenantId, status** and sorts **createdAt DESC, _id DESC**, this index is an appropriate candidate. Run `explain` to inspect the actual plan.

`deletedAt: { $exists: false }` is still evaluated; since this index does not include `deletedAt`, a `FETCH` stage may be required to check that predicate depending on the plan. Do not assume the query is fully covered.

### 21.2. Checking getIndexes

~~~javascript
printjson(listings.getIndexes());
~~~

### 21.3. Explaining the First Page

~~~javascript
printjson(
  listings.find({
    labTag: "crud458-v1",
    tenantId: "tenant-001",
    status: "PUBLISHED",
    deletedAt: { $exists: false }
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

Observe:

- `winningPlan`.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- `executionTimeMillis`.
- Whether there is a blocking `SORT` stage or index-ordered traversal.

With 24 documents, `explain` only illustrates semantics; it **does not prove** optimal index behavior over millions of records.

### 21.4. Explaining Subsequent Pages

~~~javascript
const lastAt = ISODate(
  "2026-01-15T11:00:00Z"
);
const lastId = "l458-001-08";

printjson(
  listings.find({
    $and: [
      {
        labTag: "crud458-v1",
        tenantId: "tenant-001",
        status: "PUBLISHED",
        deletedAt: { $exists: false }
      },
      {
        $or: [
          { createdAt: { $lt: lastAt } },
          {
            createdAt: lastAt,
            _id: { $lt: lastId }
          }
        ]
      }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(3)
  .explain("executionStats")
);
~~~

The tuple in the example simply illustrates the cursor query; in an application, always use the **actual tuple of the last returned record**, never hardcode an ID that might not match the timestamp.

### 21.5. Indexes May Need Adjustment When Filters Change

If the API also filters by `cityCode` and a price range, redesign indexes around actual query patterns:

~~~javascript
{
  tenantId: 1,
  status: 1,
  cityCode: 1,
  createdAt: -1,
  _id: -1
}
~~~

This example suits equality on `cityCode`; a price range may affect index ordering and sort support. Do not build an index for every unused filter combination; measure selectivity, workload, and write overhead.

## 22. Stable Order Does Not Mean Snapshot

### 22.1. Keyset Avoids Offset Drift from Head Inserts

Once page 1 returns the two newest documents, a newly inserted document with a timestamp newer than the end of page 1 will **not match the `after` predicate** on page 2. This eliminates offset-shift duplicates caused by `skip`.

### 22.2. Yet Keyset Does Not Freeze Data

Between two pages:

- A document after the cursor is deleted: it disappears.
- A `DRAFT` is published and falls after the cursor: it may appear.
- A `PUBLISHED` listing is archived: it may no longer appear.
- A document is inserted **backdated** past the cursor: it may appear.
- A document's **createdAt** is changed (if permitted): it may be duplicated or skipped.

Therefore, describe keyset as **deterministic-order pagination**, never claim it provides an **immutable snapshot** across multiple requests.

### 22.3. Immutability of the Sort Key

Simple rule: set `createdAt` once and **never update `createdAt`**. Keep `updatedAt` for display rather than pagination keys if you want to minimize item shifting.

If sorting by **updatedAt DESC**, a single edit moves a listing to the top of the list, removing it from its old position. If "recently updated" is the goal, that behavior is intentional, but pagination consumers must accept or handle it explicitly.

### 22.4. High-Water Anchor

Some APIs record an **anchor tuple** of the first item when browsing begins and restrict subsequent pages to items at or after that anchor in sort order. This prevents newly inserted records **newer than the anchor** from entering results.

However:

- A backdated insert can still appear.
- Deletions and status changes still affect membership.
- An anchor **does not replace snapshot reads**.

When exporting an exact fixed dataset, consider snapshot-consistent operations or materialized job results based on MongoDB deployment/version, `readConcern`, and retention requirements.

### 22.5. Snapshot Consistency Has Trade-offs

MongoDB supports read concerns, transactions, and snapshot reads under appropriate versions and conditions. However, holding a snapshot across multiple HTTP requests requires session/timestamp management, history retention bounds, resource overhead, and retry policies. Never assume simply passing a cursor token gives snapshot isolation.

For standard listing APIs, keyset + immutable sort keys is usually the right balance; for financial/audit/consistent exports, stronger guarantees are needed.

## 23. Opaque Cursors in Production APIs

### 23.1. Do Not Expose Raw Cursor Objects as a Fixed Contract

API sample:

~~~json
{
  "items": [
    {
      "id": "l458-001-08",
      "title": "Apartment 001-08",
      "createdAt": "2026-01-15T11:00:00Z"
    }
  ],
  "hasNext": true,
  "nextCursor": "opaque-token"
}
~~~

**opaque-token** here is a placeholder illustrating response shape; it is not a real token.

### 23.2. Logical Token Payload

A token may represent:

~~~json
{
  "v": 1,
  "sort": "createdAt_desc_id_desc",
  "lastCreatedAt": "2026-01-15T11:00:00Z",
  "lastId": "l458-001-08",
  "tenantId": "tenant-001",
  "status": "PUBLISHED",
  "filterHash": "hash-of-canonical-filters",
  "pageSize": 20,
  "expiresAt": "2026-01-16T00:00:00Z"
}
~~~

Timestamps and IDs in this example are illustrative; never accept expired tokens.

### 23.3. Signing Tokens

The backend can:

1. Serialize a versioned payload in canonical JSON format.
2. Compute an **HMAC-SHA-256** signature using a server secret key.
3. Encode payload + MAC using Base64url or your chosen token format.
4. On receipt, verify the MAC using a constant-time comparison.
5. Validate expiry, token schema version, sort, page size, tenant, and filter fingerprint.
6. Convert the tuple to the exact BSON Date/ID types and build a query with a trusted tenant predicate.

**Base64 is not encryption and does not guarantee integrity.** If the payload contains sensitive data, avoid storing it there or use authenticated encryption. HMAC prevents tampering, not confidentiality disclosure.

### 23.4. Binding the Cursor to the Filter

Client filters page 1 with:

~~~text
tenant=001, status=PUBLISHED, city=HCM
~~~

and then sends that cursor with filter:

~~~text
tenant=002, status=DRAFT
~~~

If the server fails to verify filter binding, the cursor can break pagination order/correctness or introduce cross-tenant risks. Always validate **tenant from the security context** and hash canonical filters and sort specifications.

### 23.5. Page-Size Limits

Never allow callers to request `pageSize=1,000,000` to dump the entire collection. Example policy:

~~~text
defaultPageSize = 20
maxPageSize = 100
~~~

This cap is an application API/performance choice, not a fixed limit imposed by MongoDB.

## 24. Java: Outlining Safe Data Access

### 24.1. Never Mix Raw HTTP Input into Queries

Java service example using the MongoDB Sync Driver: accepts a trusted `tenantId` from the principal and a verified cursor; BSON field names are controlled by code:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.ArrayList;
import java.util.List;
import java.util.Date;

record PageKey(Date createdAt, String id) {}

record ListingPage(
    List<Document> items,
    boolean hasNext,
    PageKey nextKey
) {}

ListingPage listPublished(
        MongoCollection<Document> coll,
        String trustedTenant,
        int pageSize,
        PageKey after) {
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid pageSize");
    }

    Bson base = Filters.and(
        Filters.eq("labTag", "crud458-v1"),
        Filters.eq("tenantId", trustedTenant),
        Filters.eq("status", "PUBLISHED"),
        Filters.exists("deletedAt", false)
    );

    Bson filter = base;
    if (after != null) {
        filter = Filters.and(
            base,
            Filters.or(
                Filters.lt("createdAt", after.createdAt()),
                Filters.and(
                    Filters.eq(
                        "createdAt", after.createdAt()
                    ),
                    Filters.lt("_id", after.id())
                )
            )
        );
    }

    List<Document> fetched = coll.find(filter)
        .sort(Sorts.orderBy(
            Sorts.descending("createdAt"),
            Sorts.descending("_id")
        ))
        .limit(pageSize + 1)
        .into(new ArrayList<>());

    boolean hasNext = fetched.size() > pageSize;
    List<Document> items = new ArrayList<>(
        fetched.subList(
            0, Math.min(pageSize, fetched.size())
        )
    );

    Document last = items.isEmpty()
        ? null : items.get(items.size() - 1);

    PageKey nextKey = hasNext && last != null
        ? new PageKey(
            last.getDate("createdAt"),
            last.getString("_id")
        )
        : null;

    return new ListingPage(items, hasNext, nextKey);
}
~~~

This is an **illustrative Java method snippet** that must be placed in a class/service with proper driver setup to run. Using `into(ArrayList)` here is **bounded by `pageSize+1` (at most 101)**, not loading the full collection.

### 24.2. Include Tenant in the Base Filter

`trustedTenant` must come from the backend security context. IDs can be guessed and cursors replayed; only enforcing tenant and permissions inside the query guarantees isolation.

### 24.3. Handling Date and ID Types

The Java snippet assumes `_id` is a BSON String and `createdAt` is a BSON Date, matching the lab. If switched to ObjectId, `PageKey` must carry `ObjectId` or convert to the proper type before querying. Never compare a String ObjectId against a BSON ObjectId expecting MongoDB to match.

### 24.4. Do Not Return Raw Documents Directly from APIs

APIs should map results to whitelisted DTO fields, hiding `labTag`, internal `revision`, audit metadata, or private fields. Opaque cursors store properly typed tuples and filter contracts.

## 25. Spring Data MongoDB: Mapping and Query Paths

A minimal entity:

~~~java
@Document(collection = "listings_458")
public class ListingDocument {
    @Id
    private String id;
    private String tenantId;
    private String title;
    private String status;
    private Instant createdAt;
    private List<Room> rooms;

    @Version
    private Long revision;
}
~~~

**This is an illustrative excerpt only**, not a full class with constructors/getters/imports. Spring Data supports **@Version** optimistic locking through its supported APIs. However:

- It does not guarantee raw MongoDB driver updates also increment version.
- It does not prevent races if another writer skips the version check.
- It does not replace business status predicates.
- It does not replace API authorization.

Typed `MongoTemplate` maps Java property paths to stored BSON field paths when entities use `@Field` aliases. `mongosh` and the raw driver must use the **actual BSON field names**.

### 25.1. Updating a Room via MongoTemplate

Concept:

~~~java
Query query = new Query(
    Criteria.where("id").is(listingId)
        .and("tenantId").is(trustedTenant)
);

Update update = new Update()
    .set("rooms.$[r].available", true)
    .filterArray(
        Criteria.where("r.roomId").is("bed-1")
    );

mongoTemplate.updateFirst(
    query, update, ListingDocument.class
);
~~~

This illustrates the API direction; verify `arrayFilters` mapping, `@Version` behavior, and your actual Spring Data version. For concurrency-critical updates, add revision/status guards and inspect `matchedCount`.

## 26. Testing CRUD and Array Updates

### 26.1. Functional Test Matrix

| Scenario | Expected |
| --- | --- |
| Insert valid new listing | One document with initial ID and revision |
| Insert duplicate `_id` | Duplicate key error, no second document |
| Read matching tenant | Document returned |
| Read different tenant | No data returned |
| Update title matching tenant | Only title/updatedAt/revision change |
| Update with stale revision | `matchedCount=0` or 409 |
| Publish DRAFT | Only one valid transition succeeds |
| Publish PUBLISHED again | No-op or conflict per contract |
| `addToSet` existing tag | Tag not duplicated |
| `push` same tag twice | Can duplicate |
| `pull` tag | Matching elements removed |
| Update `rooms.$` by `roomId` | Matched element updated |
| Update `rooms.$[r]` | Elements matching `arrayFilters` updated |
| Update `rooms.$[]` | All rooms updated |
| Pull kitchen room | Only kitchen element removed |
| Soft delete | Document remains, excluded from active queries |
| Hard delete matching ID/tenant | `deletedCount=1` if present |
| Hard delete different tenant | `deletedCount=0` |

### 26.2. Integration Tests Require Real MongoDB

Mocked repositories do not verify:

- BSON Decimal128 vs. Double/String.
- `$elemMatch` semantics.
- Correct `arrayFilters` behavior.
- Unique `_id`/indexes.
- Index plans/explain output.
- CAS atomicity.

Use MongoDB Testcontainers or an isolated managed test database to verify these points.

### 26.3. Unit Tests Still Have Value

Unit test:

- Validation of title, rent, and `roomId`.
- State transition `DRAFT → PUBLISHED`.
- Cursor payload parsing and HMAC verification.
- Page size bounds/`filterHash`.
- 404/409 error mapping.
- DTO whitelisted fields.

### 26.4. Inspect the Result, Not Only matchedCount

After an array update, read the actual document back:

~~~javascript
printjson(listings.findOne({
  _id: "l458-001-01",
  labTag: "crud458-v1",
  tenantId: "tenant-001"
}, {
  _id: 1,
  revision: 1,
  rooms: 1
}));
~~~

Verify other rooms **were not unintentionally modified**.

## 27. Testing Stable Pagination and Changing Data

### 27.1. Fixtures with Identical createdAt

The seed contains pairs of documents sharing the same timestamp. Tests must verify:

- Sort **createdAt DESC, _id DESC** establishes a total order.
- A page boundary can fall between two documents with identical `createdAt`.
- A cursor with a tie-breaker does not skip the remaining document.

### 27.2. Collecting All Pages and Comparing IDs

An integration test can:

1. Read the first page.
2. Follow `nextAfter` until `null`.
3. Collect returned `_id`s.
4. Assert zero duplicate `_id`s.
5. Assert total collected IDs equals `countDocuments` for a **static dataset** during the test.
6. Assert tuples appear in strictly descending order.

Only compare against `countDocuments` like this when the dataset is **unchanged during the test run**. Under concurrent writes, count and pages may observe different points in time.

### 27.3. New Insert Between Pages 1 and 2

Insert a document with a `createdAt` newer than the last cursor. Keyset page 2 must not repeat an item already returned on page 1 simply because the new insert landed at the head.

### 27.4. Backdated Insert

Insert a new document with a `createdAt` older than the last cursor. It may appear on a subsequent page; this does not violate keyset semantics. If an API promises a frozen snapshot, a different mechanism is required.

### 27.5. Soft Delete Between Pages

Soft-delete an item not yet visited; it disappears from subsequent pages. Do not treat this as a pagination bug if the API provides a **live view**.

### 27.6. Changing Filters

Generate a page 1 token with `status=PUBLISHED`, then request page 2 with `status=DRAFT`. The backend must **reject the mismatched filter cursor** instead of continuing into a different subset.

### 27.7. Cursor Security

Test:

- Single-character token tampering → invalid signature.
- Expired token → rejected.
- Token from another tenant → rejected.
- Different `filterHash` → rejected.
- Wrong sort ID type → rejected.
- `pageSize` exceeding max → rejected.
- Future token version → graceful unsupported error.

## 28. Query Performance and Access Patterns

### 28.1. Counts Can Be Expensive

A keyset API does not need to run a filtered **`countDocuments`** over millions of records on every page. It can return:

~~~json
{
  "items": [],
  "hasNext": false,
  "nextCursor": null
}
~~~

and expose `totalCount` via a reporting endpoint or an explicitly priced option.

### 28.2. Indexes Must Match Filters and Sort Order

Query:

~~~javascript
{
  labTag: "crud458-v1",
  tenantId: "tenant-001",
  status: "PUBLISHED"
}
~~~

sort:

~~~javascript
{ createdAt: -1, _id: -1 }
~~~

candidate index:

~~~javascript
{
  labTag: 1,
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
}
~~~

In production without `labTag`, drop that prefix and design the real index for tenant/status/time. When queries combine optional filters, benchmark candidate indexes rather than creating every permutation.

### 28.3. Keyset Is Not Free

With tuple range predicates and multiple optional filters, MongoDB may use OR branches or additional index scans. Run `explain` on cursor pages too, not just the first page.

### 28.4. Project Only Needed Fields

A list endpoint does not need the entire `rooms` array for every item. Fetch only `id/title/rent/city/status/createdAt`; let the detail endpoint return `rooms`. This saves network bandwidth, client memory, and reduces unnecessary data exposure.

### 28.5. API Quotas

Enforce limits on:

- Page size.
- Query time window if applicable.
- Allowed sort fields.
- Max concurrent exports.
- Per-tenant rate/quota limits.
- Cursor TTL.
- Request timeout/`maxTimeMS`.

Do not let clients pick arbitrary sort fields and force the backend to index every combination.

## 29. Common Errors and Remedies

| Symptom | Cause | Remedy |
| --- | --- | --- |
| Update succeeds on wrong tenant | Filter only has `_id` | Add `tenantId` from principal |
| `matchedCount=0` | Wrong ID, wrong tenant, status/revision conflict | Classify and return 404/409 per policy |
| `replaceOne` loses `rooms` | Incomplete replacement document | Use targeted `$set` |
| `$set` misspells field name | Typo creates a new field | Schema validation/typed mapping |
| `$push` duplicates tags | `$push` does not check uniqueness | Use `$addToSet` for set semantics |
| `$addToSet` embedded doc duplicates `roomId` | Compares whole doc, not `roomId` uniqueness | Enforce separate domain invariant |
| `$pull` deletes more than intended | Multiple array elements match | Validate identifiers and filters |
| `rooms.$` updates wrong element | Ambiguous array query match | `$elemMatch` or `$[r] + arrayFilters` |
| `rooms.$[]` modifies every room | Used all-positional instead of filtered | Use `$[r]` |
| Array filter fails to match | Wrong field path/type | Inspect raw BSON document |
| Two updates overwrite each other | Read-modify-save without revision guard | CAS, targeted updates |
| `revision` still fails to protect | Another writer omitted version bump | Enforce convention across all write paths |
| `DRAFT` published twice | Missing status predicate | Atomic state transition filter |
| Soft-deleted docs still read | Missing `deletedAt` filter | Centralize active query criteria |
| Duplicate items across pages | Skip offset shifted on insert | Keyset pagination |
| Skipped item with same timestamp | Only stored `createdAt` | Add `_id` tie-breaker |
| Skipped item at boundary | Cursor took `(pageSize+1)th` row | Use last returned row |
| Final page reports wrong `hasNext` | Checked `items.length == pageSize` | Fetch `pageSize+1` |
| Another tenant's token works | Cursor/auth filter not bound | Verify signed token/context |
| Live data shifts between pages | Keyset is not a snapshot | Document contract, use snapshot when required |
| Cursor compares String ID to ObjectId | Mismatched BSON types | Standardize types |
| Sorting by `updatedAt` repeats items | Mutable sort key | Use immutable key or accept live semantics |
| Slow queries on deep pages | Large skip / suboptimal index | Keyset + compound index |
| Count too expensive | Counting on every page | Consider omitting `totalCount` |
| Client OOM | Materializing entire cursor | Bound results and page size |
| Broken unique index undetected | Only mocked repository in tests | Integration tests against real MongoDB |

## 30. Deployment and Production API Verification Runbook

### Phase A — Preparing the Contract

1. Define collection schema and required fields.
2. Define tenant authorization boundaries.
3. Choose `_id` BSON type, immutable `createdAt`, and `revision` contract.
4. Establish `roomId` uniqueness and array length limits.
5. Define status workflow and soft-delete rules.
6. Define sort tuple and cursor token format.

### Phase B — Data Access

1. Write CRUD operations with tenant filters.
2. Use targeted updates instead of `replace` unless business requires replacement.
3. Scope array operations accurately.
4. Handle `matchedCount`/`modifiedCount`/conflicts.
5. Establish controlled migration/validation/index deployment.

### Phase C — Indexes and Performance

1. Analyze query patterns.
2. Create matching indexes.
3. Explain both first page and cursor pages.
4. Measure p50/p95/p99 latency.
5. Cap page sizes and query windows.
6. Optimize projections and counts.

### Phase D — Testing

1. Unit test validation, state transitions, and cursor integrity.
2. Integration test BSON CRUD, `arrayFilters`, `revision`, and indexes.
3. E2E test tenant isolation and API responses.
4. Test pagination with duplicate timestamps.
5. Test inserts/deletes/status changes between pages.
6. Test concurrency, idempotency, and timeouts.

### Phase E — Release

1. Canary deployment.
2. Monitor duplicate-key/409/404 rates.
3. Monitor pagination latency and `keysExamined`.
4. Monitor array update errors and unexpected bulk effects.
5. Maintain rollback plans for code, index, and schema changes.

## 31. Practice Exercises

### Exercise 1 — Schema

Design a `Listing` with `_id`, `tenantId`, `status`, `createdAt`, `updatedAt`, `revision`, `tags`, and `rooms`. Explain why `roomId` is not the root `_id`.

### Exercise 2 — Seed

Run the 24-document seed. Confirm there are three tenants, eight listings per tenant, six `PUBLISHED` and two `DRAFT`.

### Exercise 3 — Duplicate Timestamps

Use an aggregation grouping by `createdAt` to prove two documents share the same creation time. Why is sorting by `createdAt` alone insufficient?

### Exercise 4 — Create

Create `l458-created-001` and run `insertOne` a second time. How does MongoDB respond? Why shouldn't a duplicate-key error be treated unconditionally as success?

### Exercise 5 — Read

Write a `findOne` using `_id`, `tenantId`, and the active condition. What should querying the same `_id` with a different `tenantId` return?

### Exercise 6 — Projection

Fetch 10 published listings returning only `_id/title/createdAt`. Why doesn't a list API necessarily load `rooms`?

### Exercise 7 — Count

Compare filtered `countDocuments` against `estimatedDocumentCount`; when is `totalCount` needed?

### Exercise 8 — Set

Update `title` while incrementing `revision` and updating `updatedAt`. Inspect `matchedCount`/`modifiedCount`.

### Exercise 9 — Unset

Remove `optionalNote`. Distinguish a missing field from `field:null`.

### Exercise 10 — Replace

Explain why a `replaceOne` containing only `title` and `_id` can wipe `rooms`/`tags` from an existing document.

### Exercise 11 — Multi-update

Write an `updateMany` for `DRAFT` listings of `tenant-001`; analyze the risk if `tenantId` is omitted.

### Exercise 12 — CAS

Starting from `revision=1`, update to `revision=2`. Calling again with filter `revision=1` produces what `matchedCount`? What API error should be returned?

### Exercise 13 — Concurrent Writes

Two requests both read `revision=2` and edit `title`. Design a flow that avoids silently overwriting the newer change.

### Exercise 14 — State Transition

Write an `updateOne` that transitions only `DRAFT → PUBLISHED`. Why must the status filter accompany the update?

### Exercise 15 — $push

Add tag `"BALCONY"` twice using `$push`. What does the resulting array look like?

### Exercise 16 — $addToSet

Add `"BALCONY"` twice using `$addToSet`. Does it automatically remove preexisting duplicates?

### Exercise 17 — $pull

Remove tag `"BALCONY"` from the listing. If three identical elements existed, what happens?

### Exercise 18 — $elemMatch

A listing has an 18 m² bedroom and a 25 m² kitchen. Explain the difference between dotted predicates and `$elemMatch` when searching for a bedroom >= 20 m².

### Exercise 19 — Positional $

Write an update setting `available` for `roomId` `bed-1` using `rooms.$`. Why must the filter match the array element?

### Exercise 20 — Filtered Positional

Use `rooms.$[r].areaSqm` with `arrayFilters` to set `bed-1`'s area to 24.

### Exercise 21 — Multiple Conditions on the Same Room

Use `arrayFilters` to find a `BEDROOM` with `areaSqm >= 18` and update `available`.

### Exercise 22 — $[]

Write an update setting `available=false` for all rooms of a listing. Why shouldn't `$[]` be used when only editing `bed-1`?

### Exercise 23 — Nested Amenities

Add `ELEVATOR` to `bed-1`'s amenities using `$addToSet` and `arrayFilters`; avoid duplicating `WIFI`.

### Exercise 24 — $pull Room

Remove `kitchen-1` from `rooms`. Which business invariants should be checked beforehand?

### Exercise 25 — Array Uniqueness

Why don't `$addToSet` on embedded documents and a unique multikey index guarantee `roomId` uniqueness within a single listing?

### Exercise 26 — FindOneAndUpdate

Use `returnDocument:"after"` to get `title`/`revision` after updating. What happens when the filter matches nothing?

### Exercise 27 — Soft Delete

Store `deletedAt` and status `ARCHIVED`. Why must the active filter appear in both detail and list APIs?

### Exercise 28 — Hard Delete

`deleteOne` by `_id + tenantId + labTag`. Distinguish `deletedCount=0` from unauthorized documents.

### Exercise 29 — Bulk

Write a `bulkWrite` with two different `updateOne` operations. Explain why `ordered:false` does not create a transaction.

### Exercise 30 — Offset Pagination

Diagram an offset page before/after an insert at the head of the list and explain why a record repeats.

### Exercise 31 — Keyset Tuple

Sort `createdAt DESC, _id DESC`. Write the predicate for elements appearing after `(lastAt,lastId)`.

### Exercise 32 — Tie-Breaker

Given two documents with the same `createdAt`, prove that querying only `createdAt<lastAt` can skip a document.

### Exercise 33 — pageSize+1

Suppose `pageSize=3` and the query fetches four documents. How many items are returned? Which document provides `nextAfter`?

### Exercise 34 — Final Page

When a query returns exactly `pageSize` documents and there is no `(pageSize+1)th` element, what is `hasNext`?

### Exercise 35 — Pagination Lab

Run `getPage458` with `pageSize=2` for `tenant-001`. Collect all six published IDs, proving no duplicates and descending order.

### Exercise 36 — Index

Design an index for `tenantId + status` equality and `createdAt DESC, _id DESC` sort. Run `explain` on both first and subsequent pages.

### Exercise 37 — Cursor Filter

A cursor was issued for `tenant-001/status=PUBLISHED` but a client passes it with `tenant-002/status=DRAFT`. What must the backend do?

### Exercise 38 — Cursor HMAC

Outline a versioned payload, MAC verification, expiry, tenant binding, `filterHash`, and page-size limit. Why doesn't Base64 alone protect integrity?

### Exercise 39 — Live Data

Between pages 1 and 2, a new listing appears with a `createdAt` newer than the cursor. How does keyset handle it? What if an old `DRAFT` is published past the cursor?

### Exercise 40 — Snapshot

Why doesn't keyset guarantee a snapshot? When is a snapshot-consistent export or fixed result-set job required?

### Exercise 41 — Mutable Sort Key

If an API sorts by `updatedAt DESC` and a user updates a document on a later page, what is the risk of duplicates/omissions?

### Exercise 42 — ID BSON Type

If switching `_id` from String to ObjectId, how must cursor serialization/comparison and query filters change?

### Exercise 43 — Spring Data Integration

Write an entity with `@Document`, `@Id`, `@Version`, and `rooms`. Design a safe `MongoTemplate` `arrayFilters` update with a tenant predicate.

### Exercise 44 — Tenant Security

A user knows an `_id` belonging to another tenant. Why don't unique `_id`s and HMAC cursors replace authorization in MongoDB queries?

### Exercise 45 — Capstone

Design a CRUD API for millions of listings across multiple tenants with `rooms` and `tags`; require auditing, optimistic locking, soft delete, stable keyset pagination, HMAC cursors, indexes, integration tests, and a release runbook. Explain each invariant and snapshot limitation.

## 32. References

- MongoDB Manual — [CRUD Operations](https://www.mongodb.com/docs/manual/crud/).
- MongoDB Manual — [Insert Documents](https://www.mongodb.com/docs/manual/tutorial/insert-documents/).
- MongoDB Manual — [Query Documents](https://www.mongodb.com/docs/manual/tutorial/query-documents/).
- MongoDB Manual — [Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/).
- MongoDB Manual — [Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [$set](https://www.mongodb.com/docs/manual/reference/operator/update/set/).
- MongoDB Manual — [$inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/).
- MongoDB Manual — [$push](https://www.mongodb.com/docs/manual/reference/operator/update/push/).
- MongoDB Manual — [$addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/).
- MongoDB Manual — [$pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/).
- MongoDB Manual — [Positional $ Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional/).
- MongoDB Manual — [All Positional $[] Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/).
- MongoDB Manual — [Filtered Positional $[identifier] Operator](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/).
- MongoDB Manual — [$elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/).
- MongoDB Manual — [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/).
- MongoDB Manual — [Sort and Index Use](https://www.mongodb.com/docs/manual/tutorial/sort-results-with-indexes/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).
- MongoDB Manual — [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/).
- MongoDB Java Sync Driver — [CRUD](https://www.mongodb.com/docs/drivers/java/sync/current/crud/).
- Spring Data MongoDB — [Template CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html).
- Spring Data MongoDB — [Querying](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html).

**Conclusion:** A MongoDB CRUD implementation is only complete when it goes beyond basic insert/find/update/delete on a sample document. You must enforce **tenant authorization, schema/BSON types, atomic updates, optimistic concurrency, deletion state, and array element invariants**. For **rooms**, `$elemMatch` ensures conditions apply to the same element; positional **$**, **$[]**, and **$[identifier] + arrayFilters** have distinct update scopes, so choose according to business intent and inspect the actual result. For large lists, sorting by **createdAt DESC + _id DESC**, tuple keyset predicates, and **pageSize+1** preserve deterministic order and avoid head-insert offset drift; however, **keyset does not freeze a snapshot while data changes**. Production design requires **query-aligned compound indexes, integrity/tenant/filter-verified cursors, page limits, telemetry, integration tests, and rollback plans** so CRUD, array updates, and pagination all stay correct under load and concurrency.
