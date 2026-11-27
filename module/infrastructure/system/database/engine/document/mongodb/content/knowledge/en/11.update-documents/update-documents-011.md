# `findOneAndUpdate`, `findOneAndReplace`, and Choosing the Returned Document in MongoDB

When an application updates a document in MongoDB, sometimes it only needs to know whether the operation succeeded. Other times, the application needs **the exact document before or after the change**: for instance, returning a newly transitioned order, inspecting old values before writing an audit history, or claiming a pending task for a worker to process.

MongoDB provides two methods suited for finding, modifying, and returning a single document:

- **`findOneAndUpdate()`**: finds one document and **updates** specified fields using operators such as `$set`, `$inc`, `$unset`, `$push`, or a supported update pipeline.
- **`findOneAndReplace()`**: finds one document and **replaces the document body** with a new replacement document, still respecting `_id` rules.

By default, both return **the document before the modification**. To receive the version **after the modification**, specify `returnDocument: "after"`. This is the most important detail for reading the result correctly.

This lesson covers `mongosh` syntax, query/update scenarios, `upsert`, selecting a document via `sort`, returning a subset of fields via `projection`, Java MongoDB Sync Driver examples, and avoiding data loss when replacing documents.

## 1. Position of These Two Methods Among Update Operations

First, distinguish four commonly used methods:

| Method | Effect on Data | Typical Return Value | When to Use? |
| --- | --- | --- | --- |
| `updateOne(filter, update)` | Updates one document | Result metadata such as `matchedCount`, `modifiedCount`, `upsertedId` | When you only need to know how many documents matched or changed |
| `replaceOne(filter, replacement)` | Replaces one document | Update result metadata | When replacing the whole content without needing the document back |
| `findOneAndUpdate(filter, update, options)` | Finds and updates one document | Before/after document, or `null` when nothing is returned | When you need the document involved in the update |
| `findOneAndReplace(filter, replacement, options)` | Finds and replaces one document | Before/after document, or `null` when nothing is returned | When you need the document involved in the replacement |

The `findOneAnd...` prefix highlights **finding and modifying one document while optionally returning a snapshot of that document**. They are not equivalent to two separate application-level queries:

```javascript
// Two independent operations: there is a time gap between read and update
const oldOrder = db.orders.findOne({ _id: "ord-101" });
db.orders.updateOne(
  { _id: "ord-101" },
  { $set: { status: "paid" } }
);
```

Between `findOne()` and `updateOne()`, another application could modify the document. `findOneAndUpdate()` finds and modifies **one document** as a single document-level atomic operation, binding the condition and returned snapshot directly to that operation.

High-level diagram:

```text
filter + update/replacement + options
                   |
                   v
           Find matching doc
                   |
         +---------+----------+
         |                    |
     Doc found            No match
         |                    |
    Update/replace        upsert?
         |              /           \
         |           false          true
         |             |              |
         v            no            insert
    Select before /   update          |
    after snapshot     |              |
         +-------------+--------------+
                       |
            Return document or null
```

**Atomicity scope:** one document. If business logic requires updating multiple documents or collections as a single unit, `findOneAndUpdate()` alone does not create a multi-document transaction.

## 2. Practice Data

Select a dedicated database in `mongosh`:

```javascript
use mongo_update_lab
```

Create the `orders` collection with illustrative data:

```javascript
db.orders.insertMany([
  {
    _id: "ord-101",
    customerId: "u101",
    status: "pending",
    total: 150,
    priority: 2,
    shipping: {
      city: "Hanoi",
      method: "standard"
    },
    items: [
      { sku: "P-1", qty: 2 },
      { sku: "P-2", qty: 1 }
    ]
  },
  {
    _id: "ord-102",
    customerId: "u101",
    status: "pending",
    total: 90,
    priority: 1,
    shipping: {
      city: "Hue",
      method: "express"
    },
    items: [
      { sku: "P-3", qty: 1 }
    ]
  },
  {
    _id: "ord-103",
    customerId: "u102",
    status: "paid",
    total: 220,
    priority: 3,
    shipping: {
      city: "Da Nang",
      method: "standard"
    },
    items: [
      { sku: "P-4", qty: 2 }
    ]
  }
])
```

Commands in this lesson **modify data**, so example outputs assume starting from the dataset above. Running multiple examples sequentially alters document states; check current state with `findOne()` or use a separate lab dataset per example. Never drop a collection containing real data merely to re-run a lesson.

## 3. `findOneAndUpdate()`: Partially Updating a Document

### 3.1. General Syntax

```javascript
db.collection.findOneAndUpdate(
  filter,
  update,
  options
)
```

Where:

- **`filter`**: condition to locate the document, identical to `find()` filters.
- **`update`**: document containing update operators (`$set`, `$inc`, etc.) or a supported update pipeline.
- **`options`**: before/after snapshot selection, `sort`, `projection`, `upsert`, `arrayFilters`, and version-compatible options.

Example: transition an order from `pending` to `paid` and record the update timestamp:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101", status: "pending" },
  {
    $set: { status: "paid" },
    $currentDate: { updatedAt: true }
  }
)
```

Assuming the initial dataset is unmodified, `ord-101` matches the filter. MongoDB updates `status` and `updatedAt`, yet because no return option was specified, the returned value is the **pre-update snapshot**:

```javascript
{
  _id: "ord-101",
  customerId: "u101",
  status: "pending",
  total: 150,
  priority: 2,
  shipping: { city: "Hanoi", method: "standard" },
  items: [
    { sku: "P-1", qty: 2 },
    { sku: "P-2", qty: 1 }
  ]
}
```

Seeing `status: "pending"` in the returned document **does not mean the update failed**. That is the *before* snapshot; verify the stored document:

```javascript
db.orders.findOne({ _id: "ord-101" })
```

The stored document now has `status: "paid"` and a Date-typed `updatedAt` field.

### 3.2. Returning the Post-Update Document

To receive the updated document directly, pass `returnDocument: "after"`:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-102", status: "pending" },
  {
    $set: {
      status: "packed",
      "shipping.method": "priority"
    },
    $currentDate: { updatedAt: true }
  },
  { returnDocument: "after" }
)
```

When the filter matches, the returned document has `status: "packed"`, `shipping.method: "priority"`, and the server-assigned `updatedAt` timestamp. Other document fields such as `total`, `priority`, and `items` remain intact.

This is because `findOneAndUpdate()` with `$set` modifies only the specified paths; it does not replace the whole document.

### 3.3. `returnDocument`: Two Core Choices

| Setting | Meaning | Returned Document on Match |
| --- | --- | --- |
| Omitted | Defaults to `"before"` | Snapshot **before** the operation |
| `returnDocument: "before"` | Explicitly requests the before snapshot | Snapshot **before** the operation |
| `returnDocument: "after"` | Requests the after snapshot | Snapshot **after** the operation |

```javascript
// Document before update
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $inc: { total: 10 } },
  { returnDocument: "before" }
)

// Document after update
db.orders.findOneAndUpdate(
  { _id: "ord-102" },
  { $inc: { total: 10 } },
  { returnDocument: "after" }
)
```

The two independent commands above intentionally modify two different documents for clear observation. `$inc` adds to the current numeric value; running the command again on the same document keeps increasing `total`. Never blindly repeat increment/decrement commands as if they were idempotent updates.

The `returnDocument` option in `mongosh` uses **`"before"`** or **`"after"`**. Older shell/driver versions offered options such as `returnNewDocument` or `new`; in new code, follow the API documented for your current version and avoid mixing option names across drivers.

## 4. Using Update Operators Appropriately

Update operators let you target fields precisely:

| Operator | Purpose | Example |
| --- | --- | --- |
| `$set` | Assigns a value to a field or nested path | `{ $set: { status: "paid" } }` |
| `$unset` | Removes a field from the document | `{ $unset: { temporaryNote: "" } }` |
| `$inc` | Adds a numeric amount | `{ $inc: { total: 5 } }` |
| `$currentDate` | Sets a field to the current date/time | `{ $currentDate: { updatedAt: true } }` |
| `$push` | Appends an element to an array | `{ $push: { auditTags: "reviewed" } }` |
| `$addToSet` | Adds a value to an array if no equivalent value exists | `{ $addToSet: { auditTags: "reviewed" } }` |
| `$pull` | Removes array elements matching a condition | `{ $pull: { auditTags: "obsolete" } }` |

Example updating two fields inside a nested object without losing sibling fields:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  {
    $set: {
      "shipping.city": "Hai Phong",
      "shipping.method": "express"
    }
  },
  { returnDocument: "after" }
)
```

`shipping.city` and `shipping.method` use **dot notation**. If `shipping` also has a `trackingCode` field, `$set` on those two leaf paths preserves it. Conversely, `$set: { shipping: { city: "Hai Phong" } }` **replaces the entire `shipping` object** with a new object containing only `city`.

### Updating an Array Element with `arrayFilters`

Suppose you need to increment `qty` for item `P-2` in `ord-101`:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $inc: { "items.$[item].qty": 1 } },
  {
    arrayFilters: [{ "item.sku": "P-2" }],
    returnDocument: "after"
  }
)
```

`$[item]` selects elements of `items` matching `item.sku: "P-2"`. This does not require `P-2` to stay at index `1`; if multiple elements share the same code, all matching elements are updated. `arrayFilters` is an option for **update** operations, not part of a replacement document.

On MongoDB versions supporting **aggregation pipeline updates**, the `update` argument can be a pipeline of permitted stages such as `$set` or `$unset` in pipeline form. That is a distinct syntax from update operator documents; never assume every aggregation stage is valid inside an update.

## 5. `findOneAndReplace()`: Replacing the Entire Document Body

`findOneAndReplace()` accepts a **replacement document** instead of an update operator document.

```javascript
db.collection.findOneAndReplace(
  filter,
  replacement,
  options
)
```

Example using a new order in `pending` status:

```javascript
db.orders.insertOne({
  _id: "ord-201",
  customerId: "u201",
  status: "pending",
  total: 80,
  shipping: { city: "Hanoi", method: "standard" },
  items: [{ sku: "P-5", qty: 1 }],
  internalNote: "Needs confirmation"
})
```

To replace the document with a confirmed version:

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "confirmed",
    total: 80,
    shipping: { city: "Hanoi", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "after" }
)
```

After replacement, **`internalNote` is gone** because it was omitted from the replacement. This is a critical difference from `$set` in `findOneAndUpdate()`.

### 5.1. A Replacement Is a Complete Document

Suppose the old document is:

```javascript
{
  _id: "x1",
  name: "Binh",
  active: true,
  profile: { city: "Hue", language: "vi" }
}
```

If the replacement is:

```javascript
{
  name: "Binh",
  active: false
}
```

then after replacement, the document no longer has `profile`. If `_id` is omitted from the replacement, MongoDB preserves the existing `_id` of the replaced document; if `_id` is provided, it must not alter the immutable `_id` of the existing document.

Treat a replacement as **a complete specification of the desired document**, rather than a list of fields to modify.

### 5.2. Never Pass `$set` as a Replacement

The following is **wrong** for `findOneAndReplace()`:

```javascript
// WRONG: replacement must not contain update operators
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  { $set: { status: "paid" } }
)
```

To update only `status`, use `findOneAndUpdate()` with `$set`. To replace the whole document, pass a replacement object containing all fields to preserve.

MongoDB enforces rules on field names and replacement structure; do not treat a replacement as an update pipeline. Edge cases like field names containing dots or `$` characters must follow your MongoDB version's field-naming rules.

### 5.3. `_id` Cannot Change During Document Replacement

Example:

```javascript
// Invalid if the matched document has _id = "ord-201"
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-999",
    status: "confirmed"
  }
)
```

`_id` is an immutable identifier. If the application needs a different identifier, decide whether it should be a separate mutable business field or whether to create a new document and manage the old document's lifecycle per business rules.

## 6. Choosing the Returned Document with `findOneAndReplace()`

`findOneAndReplace()` follows the same snapshot selection rules as `findOneAndUpdate()`:

```javascript
// Return the document before replacement
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "shipped",
    total: 80,
    shipping: { city: "Hanoi", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "before" }
)
```

Assuming `ord-201` had `status: "confirmed"` beforehand, the returned document shows that status while the newly stored document has `"shipped"`.

```javascript
// Return the document after replacement
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "delivered",
    total: 80,
    shipping: { city: "Hanoi", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "after" }
)
```

This time the returned value contains `status: "delivered"`. Notice these examples modify `ord-201` sequentially; if run independently on different data, before/after snapshots reflect the actual state in the collection.

| Scenario | `findOneAndUpdate()` | `findOneAndReplace()` |
| --- | --- | --- |
| Document matches, `"before"` | Returns pre-update snapshot | Returns pre-replacement snapshot |
| Document matches, `"after"` | Returns post-update snapshot | Returns post-replacement snapshot |
| No match and `upsert: false` | `null` | `null` |
| No match, `upsert: true`, `"before"` | `null` because no prior snapshot exists | `null` because no prior snapshot exists |
| No match, `upsert: true`, `"after"` | Returns newly created document | Returns newly created document |

**Rule:** When the result is `null`, do not immediately conclude the operation failed. `null` also occurs when `upsert` inserts a new document while the caller requested the **before** snapshot, which did not exist.

## 7. `upsert`: Insert a New Document If None Matches

Normally both methods modify only existing documents. Set `upsert: true` to insert a new document when no matching document exists.

### 7.1. Upsert with `findOneAndUpdate()`

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-301" },
  {
    $set: {
      customerId: "u301",
      status: "pending",
      total: 60
    },
    $setOnInsert: {
      createdBy: "lab"
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)
```

If `ord-301` does not exist yet, MongoDB creates the new document and returns it. Here `createdBy` is added via `$setOnInsert`, which runs only when the **insert** branch of the upsert executes.

If re-run once `ord-301` already exists, `$set` updates its listed fields while `$setOnInsert` does not run again. Inspect the actual document to verify values; `$setOnInsert` alone does not replace full business deduplication.

### 7.2. Upsert with `findOneAndReplace()`

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-302" },
  {
    _id: "ord-302",
    customerId: "u302",
    status: "pending",
    total: 75,
    shipping: { city: "Da Nang", method: "standard" },
    items: []
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)
```

When `ord-302` does not exist, the replacement document is inserted. If it already exists, **its old content is replaced** by the replacement. You cannot put `$setOnInsert` inside a replacement like an update operator; if insert-only field logic is required, `findOneAndUpdate()` is usually a better fit.

### 7.3. Why Can `upsert` + Before Snapshot Return `null`?

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-303" },
  {
    $set: {
      customerId: "u303",
      status: "pending"
    }
  },
  {
    upsert: true,
    returnDocument: "before"
  }
)
```

When `ord-303` does not exist yet, the return value is `null` even though the new record was successfully inserted. The same applies to `findOneAndReplace()`.

| Caller Goal | Recommended Option |
| --- | --- |
| Need the old snapshot to compare values prior to edit | `returnDocument: "before"` |
| Need the updated object immediately for an API response | `returnDocument: "after"` |
| Upserting and need the newly created record | `upsert: true, returnDocument: "after"` |
| Need only matched/modified counts or upserted ID | Consider `updateOne()` or `replaceOne()` |

When upserting by a business key (not `_id`), create an appropriate **unique index** to handle concurrent requests trying to insert the same record simultaneously. `upsert` does not guarantee business-key uniqueness without an index constraint.

## 8. `sort`: Choosing Which Document When the Filter Matches Multiple Records

The `findOne...` name means at most one document is modified. But if `filter` matches multiple documents, **which one** gets chosen?

For instance, both `ord-101` and `ord-102` initially have `status: "pending"`. The filter:

```javascript
{ status: "pending" }
```

does not uniquely identify a single document. Without specifying `sort`, never rely on storage order or natural order to guess which document is picked.

Select the document with the highest `priority`:

```javascript
db.orders.findOneAndUpdate(
  { status: "pending" },
  {
    $set: { status: "processing" },
    $currentDate: { pickedAt: true }
  },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

In `sort`:

- `priority: -1`: prioritize higher values first.
- `_id: 1`: when `priority` ties, use `_id` as a deterministic tie-breaker.

Here `sort` **selects the target document** rather than sorting a result list, because the method returns at most one document.

With `findOneAndReplace()`, `sort` can also select which document to replace. However, the replacement must contain all fields to retain on that selected document. When a filter can match multiple distinct documents, be extra careful: a fixed replacement can wipe out fields or overwrite data the application never read. For queue claiming or job selection, `findOneAndUpdate()` with update operators is usually cleaner and safer.

### Update Conditions Must Bind to the Expected State

Example preventing two workers from claiming the same job:

```javascript
db.jobs.findOneAndUpdate(
  { state: "queued" },
  {
    $set: { state: "running", owner: "worker-A" },
    $currentDate: { startedAt: true }
  },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

Each call finds and updates one qualifying document atomically at the document level. When no `queued` job remains, the result is `null`. This example assumes the `jobs` collection contains documents with a matching schema.

In real distributed queues, you also need worker crash recovery, retries, and leases/timeouts. Atomically claiming a job handles only the **claim** step, not full job lifecycle management.

## 9. `projection`: Selecting Which Fields Are Returned

When a document has many fields, the caller may want only a subset of fields in the returned snapshot:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $set: { status: "packed" } },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      status: 1,
      total: 1
    }
  }
)
```

The returned value contains only the requested fields (if present), such as:

```javascript
{
  _id: "ord-101",
  status: "packed",
  total: 150
}
```

However, the document **stored in the collection is not stripped down to three fields**. `projection` limits only the shape of the returned snapshot, not the write operation itself.

The same holds for `findOneAndReplace()`:

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-302" },
  {
    _id: "ord-302",
    customerId: "u302",
    status: "confirmed",
    total: 75,
    shipping: { city: "Da Nang", method: "express" },
    items: []
  },
  {
    returnDocument: "after",
    projection: { status: 1, total: 1, _id: 0 }
  }
)
```

The output shows only `status` and `total`. Underneath, the replacement still stores `customerId`, `shipping`, and `items`.

**Do not confuse `projection` with `replacement`:** `projection` controls what is read back in the returned snapshot; `replacement` is the complete new document written to disk.

## 10. No Matching Document, `null`, and Interpreting Results

With a non-matching filter:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-999" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
)
```

Because `upsert` defaults to disabled, no `ord-999` document is created and the return value is `null`.

Handling it in `mongosh`:

```javascript
const result = db.orders.findOneAndUpdate(
  { _id: "ord-999", status: "pending" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
);

if (result === null) {
  print("No matching document to update");
} else {
  print("Updated: " + result._id);
  printjson(result);
}
```

This interpretation holds when `upsert: false`. When `upsert: true` and `returnDocument: "before"`, `null` **can also mean an insert just succeeded**. To distinguish branches reliably, design callers to request `"after"`, or use an API that returns operation metadata.

In a web application, when no order matches the expected state, translate `null` into a meaningful business response—such as "Order does not exist or is no longer pending"—rather than throwing a generic database error.

## 11. Atomicity and State-Guard Conditions

The strength of `findOneAndUpdate()` lies not only in returning before/after snapshots, but also in checking **conditions on the target document** atomically alongside the update.

### 11.1. Conditional State Transition

```javascript
db.orders.findOneAndUpdate(
  {
    _id: "ord-101",
    status: "pending"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  },
  { returnDocument: "after" }
)
```

If another request already moved `ord-101` to `cancelled`, the filter requiring `status: "pending"` no longer matches. This prevents accidentally marking a cancelled order as `paid`.

This pattern is known as a **conditional state-transition update**. It eliminates running `findOne()` and checking in Java before sending an update, which opens a window for concurrent races.

### 11.2. Incrementing Counters with a Capacity Guard

Suppose an event document exists:

```javascript
{
  _id: "event-101",
  capacity: 50,
  booked: 49
}
```

To increment `booked` only while seats remain:

```javascript
db.events.findOneAndUpdate(
  {
    _id: "event-101",
    $expr: { $lt: ["$booked", "$capacity"] }
  },
  { $inc: { booked: 1 } },
  { returnDocument: "after" }
)
```

With `booked: 49` and `capacity: 50`, the operation returns the updated document with `booked: 50`. The next request fails the `$expr` check. This assumes the document exists in `db.events` with compatible numeric fields.

This enforces the constraint **within one document**; if each booking also creates payments or seat reservations in other collections, add appropriate multi-document consistency mechanisms.

### 11.3. Why Read-Then-Write Is Not Equivalent

```javascript
// Prone to race condition between the two commands:
const event = db.events.findOne({ _id: "event-101" });
if (event && event.booked < event.capacity) {
  db.events.updateOne(
    { _id: "event-101" },
    { $inc: { booked: 1 } }
  );
}
```

Two concurrent requests can both read the remaining capacity before either writes. Checking `booked < capacity` only on the client without putting it in the update filter allows overbooking.

Placing the guard directly inside `findOneAndUpdate()` (or `updateOne()` when the document is not needed back) solves conditional updates at the document level.

## 12. Java MongoDB Sync Driver: The `ReturnDocument` Option

In the Java Sync Driver, the corresponding methods live on `MongoCollection<TDocument>`. Instead of `"before"`/`"after"` strings in `mongosh`, the driver uses the enum **`ReturnDocument.BEFORE`** or **`ReturnDocument.AFTER`**.

Configuration classes:

- `FindOneAndUpdateOptions`: for `findOneAndUpdate()`.
- `FindOneAndReplaceOptions`: for `findOneAndReplace()`.
- `ReturnDocument`: selects the before or after snapshot.

Complete example with `Document`:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.FindOneAndReplaceOptions;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public class FindAndModifyExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("mongo_update_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            // 1) Update and receive the post-operation document
            FindOneAndUpdateOptions updateOptions =
                new FindOneAndUpdateOptions()
                    .returnDocument(ReturnDocument.AFTER)
                    .projection(
                        Projections.include("_id", "status", "updatedAt")
                    );

            Document updated = orders.findOneAndUpdate(
                Filters.and(
                    Filters.eq("_id", "ord-101"),
                    Filters.eq("status", "pending")
                ),
                Updates.combine(
                    Updates.set("status", "paid"),
                    Updates.currentDate("updatedAt")
                ),
                updateOptions
            );

            if (updated == null) {
                System.out.println(
                    "No matching pending order found"
                );
            } else {
                System.out.println("After update: " + updated.toJson());
            }

            // 2) Replace the entire document, receive the pre-replacement snapshot
            Document replacement = new Document("_id", "ord-103")
                .append("customerId", "u102")
                .append("status", "archived")
                .append("total", 220)
                .append("priority", 3)
                .append(
                    "shipping",
                    new Document("city", "Da Nang")
                        .append("method", "standard")
                )
                .append(
                    "items",
                    java.util.List.of(
                        new Document("sku", "P-4")
                            .append("qty", 2)
                    )
                );

            FindOneAndReplaceOptions replaceOptions =
                new FindOneAndReplaceOptions()
                    .returnDocument(ReturnDocument.BEFORE);

            Document beforeReplacement = orders.findOneAndReplace(
                Filters.eq("_id", "ord-103"),
                replacement,
                replaceOptions
            );

            if (beforeReplacement == null) {
                System.out.println("No order found to replace");
            } else {
                System.out.println(
                    "Before replace: " + beforeReplacement.toJson()
                );
            }
        }
    }
}
```

Running this example requires a compatible MongoDB Java Sync Driver dependency, reachable MongoDB server, write privileges on the database, and the `MONGODB_URI` environment variable. The `orders` dataset from section 2 must exist; otherwise both operations return `null` due to no matching documents.

**Note:** The Java Sync Driver returns `Document` or `null` synchronously in this example; the reactive driver exposes asynchronous APIs with different return types. Never copy-paste exact enum/option syntax blindly between Java and `mongosh`: each API has its own syntax for expressing the same before/after choice.

### 12.1. `sort`, `projection`, and `upsert` in Java

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Sorts;

FindOneAndUpdateOptions options = new FindOneAndUpdateOptions()
    .sort(
        Sorts.orderBy(
            Sorts.descending("priority"),
            Sorts.ascending("_id")
        )
    )
    .projection(Projections.include("_id", "status", "priority"))
    .upsert(false)
    .returnDocument(ReturnDocument.AFTER);
```

In Java, `Sorts.descending("priority")` picks the highest-priority document when multiple records match; `Projections.include(...)` restricts fields in the returned snapshot; `upsert(false)` forbids creating new records.

### 12.2. Distinguishing Document Results from `UpdateResult`

```java
// Returns matched/modified/upserted metadata:
var updateResult = orders.updateOne(
    Filters.eq("_id", "ord-101"),
    Updates.set("status", "paid")
);
System.out.println(updateResult.getMatchedCount());

// Returns a before/after document or null:
Document changedOrder = orders.findOneAndUpdate(
    Filters.eq("_id", "ord-101"),
    Updates.set("status", "paid"),
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);
```

With `findOneAndUpdate()`, you do **not** receive an `UpdateResult` with `getMatchedCount()`. When business logic needs matched/modified counts or an upserted ID via metadata, `updateOne()` is often more appropriate.

## 13. Common Mistakes and Reading Results

| Scenario | Cause / Meaning | Resolution |
| --- | --- | --- |
| Updated succeeded yet old `status` returned | Defaults to **before** snapshot | Pass `returnDocument: "after"` to receive the new version |
| Result is `null` with upsert off | No document matched the filter | Check `_id`, status, and filter predicates |
| `upsert: true` yet still returns `null` | Inserted a new doc while requesting **before** snapshot | Use `"after"` to receive the newly inserted document |
| Old fields vanish after `findOneAndReplace()` | Replacement omitted those fields | Supply complete fields or use update operators |
| Passing `{$set: ...}` to `findOneAndReplace()` | Replacement cannot use update operators | Use `findOneAndUpdate()` |
| Attempting to change `_id` in replacement | `_id` is immutable | Keep existing `_id` or design a separate migration |
| Uncertain which doc changed on broad filter | Filter matched multiple records without deterministic sort | Narrow the filter and add `sort` with a tie-breaker |
| `projection` omits fields in result | Only requested subset in returned snapshot | Check projection; stored document is not stripped |
| Repeated `$inc` keeps growing the value | Increment operator is **not idempotent** | Design retry/deduplication safeguards if needed |
| Updated the wrong array element | Hardcoded index or imprecise filter | Use positional operators/`arrayFilters` as required |
| `findOne()` then `updateOne()` overwrote new state | Two separate commands create a race window | Put expected state inside the update filter |
| Expecting `findOneAndUpdate()` to edit multiple docs | Method modifies at most one document | Use `updateMany()` or a multi-document transaction |

### Write Failures Caused by Other Rules

A matching filter does not guarantee the write succeeds: MongoDB still enforces unique indexes, schema validation, privileges, BSON limits, connection state, and other constraints. For example, a replacement violating a validator or attempting to change `_id` throws an error instead of returning a document.

When handling exceptions in applications, separate:

- **`null` as a valid result**: no matching document or no prior snapshot on an upsert.
- **Execution errors**: unique/schema violations, insufficient privileges, timeouts, or network errors.

Never lump both into a single `catch` block and interpret everything as "document not found".

## 14. Choosing a Method by Business Requirement

| Requirement | Suggested Choice | Reason |
| --- | --- | --- |
| Change `status` and return the new document | `findOneAndUpdate()` + `"after"` | Edits specific fields and returns the post-update snapshot |
| Capture old document before modifying | `findOneAndUpdate()` + `"before"` | Atomically retrieves the pre-update snapshot |
| Replace entire object from approved data and return new version | `findOneAndReplace()` + `"after"` | Replacement specifies the entire desired body |
| Replace entire object while needing only match count | `replaceOne()` | Returns write metadata instead of a document |
| Increment a value and check only `matchedCount` | `updateOne()` | Avoids fetching the entire document |
| Create if missing, always return document with latest data | `findOneAndUpdate()` or `findOneAndReplace()` with `upsert: true`, `"after"` | Returns the inserted or updated record |
| Claim one highest-priority pending job | `findOneAndUpdate()` with status filter and `sort` | Atomically claims a single qualifying document |
| Bulk-update hundreds of documents | `updateMany()` | `findOneAndUpdate()` updates at most one document |

No single method fits every case by default. Start with three questions: **(1) must unlisted fields be preserved, (2) does the caller need the document returned, and (3) before or after snapshot?** The answers determine update vs. replacement and `returnDocument`.

## 15. Practice Exercises

These exercises assume a dedicated collection with intact or freshly seeded data. Updates mutate data; when testing multiple solutions sequentially, isolate each exercise in its own lab collection.

### Exercise 1. Returning the Post-Update Document

Given:

```javascript
{
  _id: "order-A",
  status: "pending",
  total: 120,
  customerId: "u1"
}
```

Change `status` to `paid`, returning the new document while preserving `total` and `customerId`.

**Answer:**

```javascript
db.orders.findOneAndUpdate(
  { _id: "order-A", status: "pending" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
)
```

Because `$set` is used, other fields remain intact. Including `status: "pending"` ensures the transition occurs only while the order is pending.

### Exercise 2. Explaining Why the Result Shows the Old Status

```javascript
db.orders.findOneAndUpdate(
  { _id: "order-B" },
  { $set: { status: "shipped" } }
)
```

The command returns a document with `status: "packed"`. Did the update definitely fail?

**Answer:** No. If `order-B` had `status: "packed"` before running, that is simply the default **before** snapshot. The stored document was updated to `status: "shipped"`. Pass `returnDocument: "after"` to receive the updated version.

### Exercise 3. Avoiding Field Loss on Replacement

Old document:

```javascript
{
  _id: "u5",
  name: "An",
  active: true,
  profile: { city: "Hanoi" }
}
```

If you call:

```javascript
db.users.findOneAndReplace(
  { _id: "u5" },
  { name: "An", active: false },
  { returnDocument: "after" }
)
```

Does `profile` remain? Is `_id` lost?

**Answer:** `profile` is removed because the replacement omits it. The existing document's `_id` is preserved; replacements cannot alter `_id`. To change only `active`, use `findOneAndUpdate()` with `$set`.

### Exercise 4. Upsert and Returned Snapshot

The collection does not contain `{_id:"x10"}`. Command:

```javascript
db.settings.findOneAndUpdate(
  { _id: "x10" },
  { $set: { enabled: true } },
  { upsert: true, returnDocument: "before" }
)
```

What is the expected return value? Is `x10` created?

**Answer:** The return value is `null` because no document existed prior to the operation; the new `x10` document is still created if the upsert succeeds. Pass `returnDocument: "after"` to receive the newly created document.

### Exercise 5. Claiming a Priority Task

A `jobs` collection holds multiple documents with `state: "queued"`, each having a `priority`. Claim the highest-priority job and transition it to `running` in one operation.

**Answer:**

```javascript
db.jobs.findOneAndUpdate(
  { state: "queued" },
  { $set: { state: "running" } },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

Putting the state in the filter and specifying `sort` picks the desired job and returns the updated job snapshot.

### Exercise 6. Updating While Under Capacity

Given `{_id:"event-1", capacity:10, booked:9}`, increment `booked` by 1 **only if capacity remains**, returning the post-update document.

**Answer:**

```javascript
db.events.findOneAndUpdate(
  {
    _id: "event-1",
    $expr: { $lt: ["$booked", "$capacity"] }
  },
  { $inc: { booked: 1 } },
  { returnDocument: "after" }
)
```

After a successful run, `booked` becomes 10; the next attempt with the same condition matches nothing.

## 16. Remembering Before/After Snapshot Selection

**`findOneAndUpdate()`** is the natural choice when editing part of a document while preserving other fields; **`findOneAndReplace()`** is for cases where you truly want to replace the entire document body. Both can return either snapshot via `returnDocument`. The default is **before**; pass **after** whenever the application needs the updated document back.

When writing production queries, carefully verify **filters**, multi-match selection with `sort`, state guards to prevent race conditions, the difference between `null` from a non-match vs. `null` from an upsert with `"before"`, and which fields vanish in a replacement. Distinguishing **update operators**, **replacements**, **returned snapshots**, and **operation metadata** ensures your MongoDB updates behave accurately without misreading results.
