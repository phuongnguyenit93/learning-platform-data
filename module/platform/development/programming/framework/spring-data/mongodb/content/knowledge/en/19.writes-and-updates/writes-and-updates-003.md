# `updateFirst`, `updateMulti`, and Fluent Variants

> **Chapter:** Writes and Updates  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, manipulate data via `MongoTemplate` or repositories, while practicing queries, transactions, testing, and performance diagnostics.  
> **Objectives:** Distinguish single-document and multi-document updates; construct `Query` and `Update` matching the entity; write fluent API calls `.matching(...).apply(...).first()/all()/upsert()`; understand `UpdateResult`, `@Version`, atomicity, the "first document" selection problem, and testing conditional updates.

## 1. When Should You Update via `MongoTemplate`?

Suppose an order is currently in state `NEW`. You need to transition it to `PROCESSING`, increment a retry counter, add a tag, or update an embedded field **without loading the entire entity and writing a replacement**.

Spring Data MongoDB provides two API styles:

- **Direct API:** `MongoTemplate.updateFirst(Query, UpdateDefinition, ...)` and `updateMulti(Query, UpdateDefinition, ...)`.
- **Fluent API:** `template.update(OrderDocument.class).matching(...).apply(...).first()`, `.all()`, and `.upsert()`.

Both styles use MongoDB **update operators** such as `$set`, `$inc`, `$unset`, and `$addToSet`, instead of requiring the application to fetch the entire document just to change a single property.

| Need | Appropriate API | Meaning |
| --- | --- | --- |
| Change the state of a single order with a known ID | `updateFirst` or fluent `first()` | Modifies at most one matching document |
| Increment a counter across all orders matching a condition | `updateMulti` or fluent `all()` | Modifies every matching document |
| Create if missing, update if present | `upsert` or fluent `upsert()` | Updates one document or inserts a new one |
| Update one document and return its pre-/post-image | `findAndModify` | Finds and modifies one document, with optional sort |
| Multiple distinct updates for different documents | `BulkOperations` | Batches operations; not equivalent to `updateMulti` |

**Important distinction:** "first" in `updateFirst` means **one document matching the query**, not necessarily the document with the smallest `_id`, earliest creation date, or top position in a UI list when the query specifies no ordering.

## 2. Preparing Consistent Sample Data and Entities

### 2.1. Test Dataset in `mongosh`

Work in a **dedicated learning database**; the write examples in this lesson are not intended for production data.

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_updates_demo_003;

orders.insertMany([
  {
    _id: "o301", tenant_id: "t01", state_code: "NEW",
    retry_count: 0, total_vnd: 100000, version: NumberLong(0),
    tags: [], delivery: { city: "Hanoi", note: "Morning" }
  },
  {
    _id: "o302", tenant_id: "t01", state_code: "NEW",
    retry_count: 1, total_vnd: 200000, version: NumberLong(0),
    tags: ["priority"], delivery: { city: "Hanoi" }
  },
  {
    _id: "o303", tenant_id: "t01", state_code: "PAID",
    retry_count: 0, total_vnd: 350000, version: NumberLong(0),
    tags: ["paid"], delivery: { city: "Da Nang" }
  },
  {
    _id: "o304", tenant_id: "t02", state_code: "NEW",
    retry_count: 0, total_vnd: 400000, version: NumberLong(0),
    tags: [], delivery: { city: "Ho Chi Minh" }
  },
  {
    _id: "o305", tenant_id: "t01", state_code: "NEW",
    retry_count: 2, total_vnd: 500000, version: NumberLong(0),
    tags: ["manual-review"], delivery: { city: "Hue" }
  },
  {
    _id: "o306", tenant_id: "t01", state_code: "CANCELLED",
    retry_count: 0, total_vnd: 150000, version: NumberLong(0),
    tags: [], delivery: { city: "Hanoi" }
  }
]);

orders.createIndex(
  { tenant_id: 1, state_code: 1 },
  { name: "tenant_state_idx" }
);
~~~

The collection initially contains 6 documents. Within it, `t01` has **3 NEW orders** (`o301`, `o302`, `o305`), one PAID order, and one CANCELLED order; `t02` has one NEW order. Do not re-run `insertMany` while the fixture data is still present, as fixed `_id` values will trigger a duplicate key error.

Expected outcomes in each section are calculated against the initial dataset **unless the section explicitly specifies sequential execution**. Write snippets across different sections are generally **alternative scenarios**, not a single script meant to run from top to bottom.

### 2.2. Java Entity with Property Names Differing from BSON Names

~~~java
// DeliveryInfo.java
package com.example.orderupdates;

public class DeliveryInfo {
    private String city;
    private String note;

    protected DeliveryInfo() { }

    public String getCity() { return city; }
    public String getNote() { return note; }
}
~~~

~~~java
// OrderDocument.java
package com.example.orderupdates;

import java.util.List;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_updates_demo_003")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("state_code")
    private String state;

    @Field("retry_count")
    private int retryCount;

    @Field("total_vnd")
    private long totalVnd;

    private List<String> tags;
    private DeliveryInfo delivery;

    @Version
    private Long version;

    protected OrderDocument() { }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
    public int getRetryCount() { return retryCount; }
    public long getTotalVnd() { return totalVnd; }
    public List<String> getTags() { return tags; }
    public DeliveryInfo getDelivery() { return delivery; }
    public Long getVersion() { return version; }
}
~~~

Intentional design points:

- Java uses `tenantId`, `state`, `retryCount`, and `totalVnd`; MongoDB stores `tenant_id`, `state_code`, `retry_count`, and `total_vnd` respectively.
- `@MongoId(FieldType.STRING)` guarantees `_id` uses BSON string.
- `@Version Long version` represents the document version and exhibits specific update behavior worth watching.
- `delivery` is an embedded document, so Java path `delivery.city` maps to BSON `delivery.city`.

With `MongoTemplate` **and an entity class**, write queries and updates using **Java property names**; Spring Data maps them to the actual BSON field names. Do not mix `Query`/`Update` conventions with raw `Filters`/`Updates` from the MongoDB Java Driver.

### 2.3. Common Imports

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
~~~

The following code snippets assume `template` is an injected `MongoTemplate` bean in a service or integration test.

## 3. `updateFirst`: Updating at Most One Document

### 3.1. Updating One Order by ID and Current State

~~~java
Query query = Query.query(
    Criteria.where("id").is("o301")
        .and("tenantId").is("t01")
        .and("state").is("NEW")
);

Update update = new Update()
    .set("state", "PROCESSING")
    .inc("retryCount", 1);

UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);
~~~

At the BSON level, the operation expresses:

~~~javascript
orders.updateOne(
  {
    _id: "o301",
    tenant_id: "t01",
    state_code: "NEW"
  },
  {
    $set: { state_code: "PROCESSING" },
    $inc: { retry_count: 1 }
  }
);
~~~

Against the initial fixture with a server-acknowledged write concern, `matchedCount = 1`; `state_code` becomes `PROCESSING` and `retry_count` becomes 1. Because the entity has `@Version`, Spring Data also **auto-increments the version** if `version` is not explicitly mentioned in `Update` (see Section 9).

### 3.2. Why Include the State Predicate?

If you filter only by `_id`, one thread could overwrite a newer state written by another thread. Adding `state = NEW` to the query makes MongoDB update only if the document **is still in the expected state** at execution time.

An update on a **single document** is atomic in MongoDB. Therefore, combining `_id + state` in the filter and `$set` in the same command avoids the race condition of:

~~~text
READ state NEW -> run business logic -> WRITE state PROCESSING
~~~

when read and write are executed as **two** separate operations.

### 3.3. What If Multiple Documents Match?

~~~java
UpdateResult result = template.updateFirst(
    Query.query(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    ),
    new Update().set("state", "REVIEW"),
    OrderDocument.class
);
~~~

The initial fixture has **three** `t01/NEW` orders, yet `updateFirst` modifies at most **one**. You cannot rely on it choosing `o301`, `o302`, or `o305` without a supported ordering mechanism and a single-document key.

To update a specific order, prefer including `_id` in the predicate. If the task is "pick the oldest order and transition its state," see `findAndModify` with sorting in Section 10; do not rely on a collection's "natural order."

### 3.4. Practical Overloads

~~~java
// Target collection inferred from @Document on the entity.
template.updateFirst(query, update, OrderDocument.class);

// Specify both entity and collection explicitly.
template.updateFirst(
    query, update,
    OrderDocument.class, "orders_updates_demo_003"
);

// Specify only collection name, without entity class.
template.updateFirst(
    rawQuery, rawUpdate, "orders_updates_demo_003"
);
~~~

With the overload taking **only a collection name**, Spring Data has no domain class metadata to map `tenantId` to `tenant_id` or apply version handling. When using that overload, `rawQuery`/`rawUpdate` must use **actual BSON names** and you assume full responsibility for data rules.

## 4. `updateMulti`: Updating All Matching Documents

### 4.1. Example Scoped to One Tenant and One State

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);

Update update = new Update()
    .set("state", "QUEUED")
    .addToSet("tags", "batch-queued");

UpdateResult result = template.updateMulti(
    query, update, OrderDocument.class
);
~~~

Semantically equivalent in MongoDB to:

~~~javascript
orders.updateMany(
  { tenant_id: "t01", state_code: "NEW" },
  {
    $set: { state_code: "QUEUED" },
    $addToSet: { tags: "batch-queued" }
  }
);
~~~

Run against the initial fixture, **3 documents** (`o301`, `o302`, `o305`) match the filter. `o304` is also `NEW` but belongs to tenant `t02`, so it is untouched. `o303` (`PAID`) and `o306` (`CANCELLED`) are likewise untouched.

### 4.2. `updateMulti` Does Not Mean "Looping `updateFirst` in Java"

`updateMulti` sends a multi-document update command by query to MongoDB. The framework does not need to load entities and call `save` for each one. This is a major advantage when only a few fields need updating across thousands of documents.

However:

- A multi-document update **does not form an atomic transaction across the whole set**; each document is updated atomically on its own.
- `Query`-based updates do not by default trigger all entity lifecycle callbacks/auditing that converting and saving a full entity runs.
- You should inspect the matched and modified document counts rather than relying solely on no exception being thrown.
- Overly broad queries can modify data outside business boundaries; always check tenant, state, date, and authorization before running.

### 4.3. Updating Specific Fields Without Replacing the Document

~~~java
Update change = new Update()
    .set("delivery.city", "Hai Phong")
    .unset("delivery.note")
    .inc("retryCount", 1);

template.updateMulti(
    Query.query(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")),
    change,
    OrderDocument.class
);
~~~

`$set` updates `delivery.city`, `$unset` removes `delivery.note`, and `$inc` increments the counter. Other fields, such as `total_vnd` and `tags`, remain intact. This is an advantage over loading a partial entity and calling `save`: replacing an entity missing fields can drop unloaded data.

### 4.4. Multi-Document Updates and Performance

`updateMulti` works well when all matching documents need **the same set of update operators**. If each document needs distinct values, consider:

- Multiple `updateFirst` calls keyed by ID.
- `BulkOperations` to group distinct update operations.
- An aggregation pipeline update if new values depend on each document's existing fields.

Never run `updateMulti(new Query(), ...)` in production unless you intentionally want to update the entire collection. An empty `new Query()` has no bounds; a missing filter bug can be catastrophic.

## 5. Comparison Table: `updateFirst` vs. `updateMulti`

| Criterion | `updateFirst` | `updateMulti` |
| --- | --- | --- |
| Target document count | At most 1 | All matching documents |
| MongoDB equivalent | `updateOne` | `updateMany` |
| Return value | `UpdateResult` | `UpdateResult` |
| No matching documents | `matchedCount = 0` | `matchedCount = 0` |
| With `@Version` and entity metadata | Can auto-increment version | Can auto-increment version on updated documents |
| Atomicity | Atomic for the updated document | Atomic **per document**, not across the whole set |
| Limiting accidental updates | Filter by `_id` and state | Filter by tenant, state, time window, exact scope |
| When selecting by sort order | Check MongoDB version requirements; `findAndModify` is the common choice | Not an API for picking "one ordered document" |
| When inserting if missing | No; use `upsert` | No; use `upsert`, not multi |

Practical takeaway: **updating multiple documents is not synonymous with calling a single-document API repeatedly**. Choose based on **target cardinality**, **required consistency**, **conflict handling**, and **return shape**.

## 6. Fluent Update: Same Semantics, Clearer Flow

Spring Data MongoDB offers a fluent syntax starting from `MongoTemplate.update(Entity.class)`, then specifying the match predicate, update, and terminal action:

~~~java
template.update(OrderDocument.class)
    .matching(query)
    .apply(update)
    .first();
~~~

This reads sequentially:

~~~text
update(OrderDocument.class)
      .matching(condition)
      .apply(write operations)
      .first() | .all() | .upsert()
~~~

### 6.1. Fluent `.first()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("id").is("o301")
            .and("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(
        new Update()
            .set("state", "PROCESSING")
            .inc("retryCount", 1)
    )
    .first();
~~~

`.matching(...)` accepts `Criteria` or `Query` depending on the fluent overload. `.first()` performs a single-document update and returns `UpdateResult`.

**Important:** the chain **does not execute simply upon calling `apply(...)`**; in the fluent API, the terminal operation `first()` is what executes the synchronous write. This mirrors how constructing an `Update` alone only describes the operators.

### 6.2. Fluent `.all()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("tenantId").is("t01")
            .and("state").is("NEW")
    )
    .apply(
        new Update()
            .set("state", "QUEUED")
            .addToSet("tags", "batch-queued")
    )
    .all();
~~~

`.all()` is the fluent counterpart to `updateMulti`, not `findAll`. It updates every document matching the query and returns `UpdateResult`, not a reloaded `List<OrderDocument>`.

### 6.3. Fluent `.upsert()`

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(
        Criteria.where("id").is("o399")
            .and("tenantId").is("t01")
    )
    .apply(
        new Update()
            .set("state", "NEW")
            .set("totalVnd", 180000L)
            .setOnInsert("retryCount", 0)
            .setOnInsert("tags", java.util.List.of())
    )
    .upsert();
~~~

If no document matches, `upsert()` inserts a new document based on applicable equality predicates and update contents. If a match exists, it updates the matched document. `setOnInsert(...)` applies only on the **insert branch**; it does not overwrite values on existing documents.

Unlike `updateMulti`, a standard upsert is a **single-document** operation, not a request to bulk-insert documents for every possible value. Use a unique key/index and design **idempotency** to avoid logical duplicates under concurrent writes.

### 6.4. Mapping Table: Direct API ↔ Fluent API

| Direct API | Semantically Equivalent Fluent API |
| --- | --- |
| `template.updateFirst(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).first()` |
| `template.updateMulti(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).all()` |
| `template.upsert(query, update, OrderDocument.class)` | `template.update(OrderDocument.class).matching(query).apply(update).upsert()` |

The fluent API's `update(...)` method is not the `Update` object itself. The first clause selects the **entity/collection**; `.apply(new Update()...)` supplies the actual modifications.

### 6.5. When to Prefer Fluent?

Fluent style fits services with multi-step selection of collection/query/update where reading "pick domain → pick condition → apply operators → choose one/all/upsert" aids clarity.

The direct API still fits existing codebases or cases where `Query` and `Update` are built separately. Pick a consistent style for the project; do not rewrite working calls solely because "fluent looks newer" when the underlying behavior is identical.

## 7. Reading `UpdateResult`: Matched Differs from Modified

Both `updateFirst`, `updateMulti`, and fluent terminal operations return `com.mongodb.client.result.UpdateResult` in the imperative API.

~~~java
UpdateResult result = template.updateFirst(
    query, update, OrderDocument.class
);

if (!result.wasAcknowledged()) {
    throw new IllegalStateException(
        "Cannot verify unacknowledged MongoDB update"
    );
}

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
var upsertedId = result.getUpsertedId();
~~~

| Value | Interpretation |
| --- | --- |
| `wasAcknowledged()` | Did the server acknowledge the operation under the configured write concern? |
| `getMatchedCount()` | How many documents matched the **update filter** |
| `getModifiedCount()` | How many documents were actually modified |
| `getUpsertedId()` | ID of the document newly inserted by upsert, if any and reported by server |

### 7.1. Example: matched = 1 but modified = 0

An update setting a field to its already-stored value matches the document without changing data:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o303" },
  { $set: { state_code: "PAID" } }
);
// Against original data: matchedCount=1, modifiedCount=0.
~~~

When running through `MongoTemplate` with a `@Version` entity, there is an important subtlety: the framework **may auto-increment the version**, so even if `$set` writes the same value, the document still changes because `version` increases. Therefore, when checking matched/modified counts, **know whether the actual update includes version or other automatic fields**.

### 7.2. Example: matched = 0

~~~java
UpdateResult result = template.updateFirst(
    Query.query(Criteria.where("id").is("o999")),
    new Update().set("state", "PAID"),
    OrderDocument.class
);
// No o999 exists: matchedCount=0, does not insert a document.
~~~

`updateFirst` and `updateMulti` **do not upsert by default**. If you need creation when missing, call `upsert` explicitly. Never interpret "no exception thrown" as "a document was updated."

### 7.3. Using `UpdateResult` to Design Business APIs

~~~java
public boolean markProcessing(String id, MongoTemplate template) {
    UpdateResult result = template.updateFirst(
        Query.query(
            Criteria.where("id").is(id)
                .and("state").is("NEW")
        ),
        new Update().set("state", "PROCESSING"),
        OrderDocument.class
    );

    if (!result.wasAcknowledged()) {
        throw new IllegalStateException("Write not acknowledged");
    }
    return result.getMatchedCount() == 1;
}
~~~

`false` means no document matched **both ID and state NEW**. It **does not automatically distinguish** a non-existent ID from an order in another state. If an HTTP API must differentiate `404` and `409`, you can perform a follow-up read, keeping in mind that data may change further between the two operations.

## 8. Common `Update` Operators

`Update` is a builder for MongoDB operators, not a new entity:

| Spring Data `Update` | Equivalent BSON | Meaning |
| --- | --- | --- |
| `set("state", "PAID")` | `$set` | Sets/replaces field value |
| `unset("delivery.note")` | `$unset` | Deletes field from document |
| `inc("retryCount", 1)` | `$inc` | Adds to a numeric field |
| `mul("totalVnd", 2)` | `$mul` | Multiplies a numeric field |
| `addToSet("tags", "new")` | `$addToSet` | Adds element to array if not already present |
| `push("tags", "new")` | `$push` | Appends element to array, allowing duplicates |
| `pull("tags", "old")` | `$pull` | Removes matching elements |
| `setOnInsert("state", "NEW")` | `$setOnInsert` | Sets only when upsert inserts a document |
| `currentDate("updatedAt")` | `$currentDate` | Sets current date/time from MongoDB |

### 8.1. `set(null)` Differs from `unset`

~~~java
// Writes explicit BSON null.
new Update().set("delivery.note", null);

// Removes the delivery.note field from the document.
new Update().unset("delivery.note");
~~~

The two behave differently when queried with `$exists` or `$type`. Do not assume Java `null` in a PATCH API implicitly means `$unset` or `$set`; the API contract must define it explicitly.

### 8.2. Why Is `$inc` Usually Safer Than Read–Modify–Save?

Suppose two requests both read `retryCount=1` and want to increment it to 2:

~~~text
Request A reads 1 -> computes 2
Request B reads 1 -> computes 2
A writes 2, B writes 2
Result is 2 instead of 3.
~~~

With `Update.inc("retryCount", 1)`, each update is atomic on the document; if both updates succeed, the counter increments twice per MongoDB semantics. Ensure the field holds an appropriate numeric type; if stored as a string or wrong null type, `$inc` may error.

### 8.3. Updating Fields Inside Arrays

If an entity has an embedded `lines` array, MongoDB supports the positional operator to update a matching element:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o301", "lines.sku": "A" },
  { $inc: { "lines.$.quantity": 1 } }
);
~~~

This lesson's fixture does not include a `lines` field, so the snippet only **illustrates syntax** and does not modify the fixture documents. In Spring Data, you can express it with `Update.inc("lines.$.quantity", 1)` and `Criteria.where("lines.sku").is("A")` when the entity has such an array.

When you need to update multiple array elements conditionally, you can use the **filtered positional operator** `$[identifier]` with `arrayFilters`; verify MongoDB/driver version support, exact BSON field names, and test against real array data.

### 8.4. Never Modify `_id` with a Regular Update

MongoDB forbids changing `_id` on an existing document via `$set`:

~~~javascript
db.orders_updates_demo_003.updateOne(
  { _id: "o301" },
  { $set: { _id: "o999" } }
);
// Invalid: _id is an immutable identifier key.
~~~

When an identifier must change, design a migration that creates the new document, updates references, and deletes the old one according to policy. That is not what `Update.set("id", ...)` is for.

## 9. `@Version`: Incrementing Version Does Not Mean Checking Old Version

Suppose the entity declares:

~~~java
@Version
private Long version;
~~~

For update operations **given an entity class**, Spring Data MongoDB automatically increments the version property if `version` is not explicitly referenced in `Update`. This applies to `updateFirst`, `updateMulti`, and fluent updates on matching entities.

**However, separate two responsibilities:**

1. **Incrementing version:** the framework appends the version increment where applicable.
2. **Checking expected version:** the query must include the right version predicate if business logic needs to reject writers holding stale data.

An `updateFirst` filtering only by `_id` **without** constraining `version` can still update a previously modified document. Auto-incrementing the version alone does not turn it into an optimistic lock against the version the caller read.

### 9.1. Version-Conditional Update

~~~java
long expectedVersion = 0L;

Query query = Query.query(
    Criteria.where("id").is("o301")
        .and("state").is("NEW")
        .and("version").is(expectedVersion)
);

UpdateResult result = template.updateFirst(
    query,
    new Update().set("state", "PROCESSING"),
    OrderDocument.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Order not found, state changed, or stale version"
    );
}
~~~

In the initial fixture, `o301` has `version=0`. If another writer incremented version to 1, the filter with `version=0` no longer matches and the update does not run. With entity metadata, Spring Data increments version on the document when the update succeeds, provided `Update` does not explicitly touch version.

### 9.2. Comparison with `save(entity)`

When loading a `@Version` entity and calling `MongoTemplate.save(entity)`, the framework can use the loaded entity's version to guard concurrent writes and throw `OptimisticLockingFailureException` on mismatch.

Conversely, with `updateFirst(Query, Update, Class)`, the service itself **must place the expected version in the query** when stale-write protection is needed. Do not assume the template knows what version a client saw if you pass only `_id`.

### 9.3. Do Not Double-Increment the Version

If `Update` explicitly operates on the version field, Spring Data no longer applies the same default auto-increment mechanism. Standardize on a single policy:

- Let the framework auto-increment version (within supported mapped operations).
- Or manage the version field explicitly using conditional updates, verifying exact BSON types and outcomes.

Do not call `inc("version", 1)` while also adding 1 in business code across an inconsistent flow. In particular, with overloads taking **only a collection name**, there is no entity metadata, so do not expect class-based auto-versioning.

## 10. Ordering When `updateFirst` Matches Multiple Documents

A common question:

> If I want to pick the **oldest** NEW order and move it to PROCESSING, can I pass `Sort` to `updateFirst`?

Spring Data MongoDB documentation notes: **`updateFirst` does not support ordering on MongoDB prior to 8.0**. On older servers, you cannot expect `Query.with(Sort)` to determine which document `updateFirst` modifies.

To select by sort order on those versions, use `findAndModify`:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query oldest = Query.query(
    Criteria.where("tenantId").is("t01")
        .and("state").is("NEW")
);

oldest.with(
    Sort.by(Sort.Order.asc("createdAt"), Sort.Order.asc("id"))
);

OrderDocument updated = template.findAndModify(
    oldest,
    new Update().set("state", "PROCESSING"),
    FindAndModifyOptions.options().returnNew(true),
    OrderDocument.class
);
~~~

**Note:** the current fixture does not yet include `createdAt` on the entity/document. This snippet is a **design pattern for when the real model adds a valid date-typed `createdAt`**, not a copy-paste command against the seeded dataset. Design an index covering the filter and sort, plus a unique tie-breaker key.

`findAndModify` can return the entity **before** the update (default) or **after** the update (`returnNew(true)`), whereas `updateFirst` returns `UpdateResult` rather than an entity. Starting with MongoDB 8.0, `updateOne` can support sort depending on driver/server/API support; when portability across versions or returning the updated entity is needed, `findAndModify` remains the clearest choice.

**Avoid the two-step pattern:** `find(...).sort(...).first()` followed by `updateFirst(byId, ...)` when atomically claiming work, because another writer can update the document between the read and write.

## 11. `upsert` and `$setOnInsert`

`upsert` means "update or insert":

~~~java
UpdateResult result = template.upsert(
    Query.query(
        Criteria.where("id").is("o399")
            .and("tenantId").is("t01")
    ),
    new Update()
        .set("state", "NEW")
        .set("totalVnd", 180000L)
        .setOnInsert("retryCount", 0)
        .setOnInsert("tags", java.util.List.of()),
    OrderDocument.class
);
~~~

Fluent equivalent:

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399")
        .and("tenantId").is("t01"))
    .apply(new Update()
        .set("state", "NEW")
        .set("totalVnd", 180000L)
        .setOnInsert("retryCount", 0)
        .setOnInsert("tags", java.util.List.of()))
    .upsert();
~~~

If a new document is created, `getUpsertedId()` reveals the newly created `_id`, and `getMatchedCount()` is typically 0. If the document already existed, `$set` runs on the update branch while `$setOnInsert` leaves existing values untouched.

### 11.1. Choosing an Upsert Filter to Prevent Logical Duplicates

If the natural key is `externalOrderId`, define an appropriate unique index. Writing only:

~~~java
template.upsert(
    Query.query(Criteria.where("externalOrderId").is(externalId)),
    update,
    OrderDocument.class
);
~~~

is not enough by itself to prevent two concurrent requests from creating duplicate orders. A unique index on the business key makes the server reject duplicates, though callers still must handle duplicate key errors and retries appropriately.

Moreover, `upsert` does not support ordering to choose among multiple results; if sorting is needed, look at `findAndModify`. `updateMulti` is not a multi-document variant of upsert.

### 11.2. Where Are Default Values Applied?

| Way of Setting Defaults | When It Takes Effect |
| --- | --- |
| Java field initializer | When the Java object is constructed and processed by mapping |
| `new Update().setOnInsert("state", "NEW")` | Only when **upsert inserts a new document** |
| `new Update().set("state", "NEW")` | On both updates and the insert branch of an upsert |
| MongoDB `$ifNull` in aggregation | At read/computation time; does not modify the stored document |

Do not use `setOnInsert` to "fix old records missing a field"—it has no effect on existing documents. For backfills, use `updateMulti` with an intentional missing/null filter.

## 12. Aggregation Pipeline Updates When Values Depend on the Document Itself

Standard `Update` is convenient for `$set`/`$inc`, but sometimes the new value is an expression over multiple existing fields. MongoDB supports **update with aggregation pipeline** (MongoDB 4.2+), and Spring Data MongoDB provides `AggregationUpdate`.

Suppose we need to compute a processing fee equal to 5% of `totalVnd` (illustrative only, not a production currency rounding rule):

~~~java
import org.springframework.data.mongodb.core.aggregation.AggregationUpdate;

AggregationUpdate pipeline = AggregationUpdate.update()
    .set("processingFeeVnd")
    .toValue(
        org.springframework.data.mongodb.core.aggregation
            .ArithmeticOperators.Multiply.valueOf("totalVnd")
            .multiplyBy(0.05)
    );

UpdateResult changed = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("PAID"))
    .apply(pipeline)
    .all();
~~~

`processingFeeVnd` is not yet declared on the entity; this example illustrates creating a computed field. In real implementations, add the corresponding property, choose an appropriate monetary numeric type (usually `Decimal128`/`BigDecimal` instead of `double` for financial logic), and verify precision/rounding.

**Distinction:** an update pipeline evaluates per document and only permits a subset of MongoDB stages; it is not a full reporting aggregation pipeline. Use it only when computation truly depends on other document fields, rather than replacing a simple `Update.inc(...)` with an unnecessarily complex pipeline.

## 13. When to Use `@Query`/Repository?

`MongoRepository.save(entity)` fits saving a complete aggregate, whereas conditional updates of a few fields are often clearer with `MongoTemplate` or an appropriately annotated repository update method.

With repositories, distinguish method prefixes:

- `findBy...`: generates a query to find and read.
- `deleteBy...`: generates a delete operation per repository conventions.
- `@Update` on a repository method: can declare a query-based update operation, depending on Spring Data MongoDB mechanics and version.

Do not assume naming a method `updateByState(...)` will automatically tell the framework which field to `$set`. In a `MongoTemplate`-focused flow, the clearest approach is constructing `Query` and `Update` and picking `updateFirst`/`updateMulti`/fluent terminal operations. That also gives direct access to `UpdateResult`.

## 14. Atomicity, Transactions, and Bulk Updates

### 14.1. Single Document Is the Standard Atomic Unit

With `updateFirst` filtering precisely on `_id` and expected state, checking the condition and applying operators on **that document** is atomic.

With `updateMulti`, each document is updated atomically, but the whole group of documents **does not by default commit or roll back together** like a multi-document transaction. If an operation is interrupted midway, inspect results, actual state, and retry strategy.

### 14.2. Transactions When All-or-Nothing Is Required

~~~java
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MongoTxConfiguration {
    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BatchOrderService {
    private final MongoTemplate template;

    public BatchOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void markOrdersForReview(String tenantId) {
        template.updateMulti(
            Query.query(Criteria.where("tenantId").is(tenantId)
                .and("state").is("NEW")),
            new Update().set("state", "REVIEW"),
            OrderDocument.class
        );

        template.updateFirst(
            Query.query(Criteria.where("id").is("o306")
                .and("tenantId").is(tenantId)),
            new Update().addToSet("tags", "review-batch"),
            OrderDocument.class
        );
    }
}
~~~

The code above outlines **two operations inside one transaction** when properly configured. MongoDB requires a transaction-capable topology (such as a replica set or suitable sharded cluster), Spring requires `MongoTransactionManager`, and the template must use the corresponding database factory/session. Calling an internal method without passing through the Spring transaction proxy can bypass `@Transactional`.

A huge transaction updating hundreds of thousands of documents is expensive, hits time/resource limits, and should not be the default choice. Consider chunked batches, checkpointed jobs, idempotent retries, or data model adjustments when appropriate.

### 14.3. Repeated Updates and Idempotency

Consider:

~~~java
new Update().set("state", "REVIEW"); // Nearly idempotent for a single field.
new Update().inc("retryCount", 1);  // Not idempotent if re-executed.
~~~

Re-running `$set` with the same value typically leaves that field unchanged (though `@Version` and other side effects may still change). Re-running `$inc` increments the counter again. When retrying after a timeout without knowing whether the previous write committed, design an idempotency key, state predicate, or explicit "already applied" check; **never blindly retry** `$inc`.

## 15. Indexes and Performance for Query-Based Updates

MongoDB must **locate matching documents** before applying updates. For a filter like:

~~~javascript
{ tenant_id: "t01", state_code: "NEW" }
~~~

an index:

~~~javascript
orders.createIndex({
  tenant_id: 1,
  state_code: 1
});
~~~

helps locate candidates. Still, performance depends on selectivity, actual number of documents written, document size, replication, contention, and other indexes that must be updated.

### 15.1. Do Not Measure Updates Only by Returned Documents

`updateMulti` does not return a list of documents. Track:

- `getMatchedCount()` and `getModifiedCount()` (when acknowledged).
- Execution latency, p95/p99 under load.
- Document counts by tenant/state before and after when verification is needed.
- Index usage during candidate lookup, inspected via an equivalent `find` query with `explain("executionStats")` in a test environment.
- I/O pressure, oplog/replication lag, write conflicts, and index update overhead.

`explain()` on a matching `find` query helps inspect the document selection plan, but does not measure the full write cost of an update command.

### 15.2. Updating Many Documents With Different Conditions Each

If you need:

~~~text
o301 -> PROCESSING
o302 -> PAID
o305 -> MANUAL_REVIEW
~~~

then **a single** `updateMulti` cannot express three distinct `$set` values with one simple `Update`. Options include:

- Three `updateFirst` calls with ID filters.
- `BulkOperations` to group distinct commands into a bulk operation.
- A pipeline update using `$switch`/`$cond` when genuinely appropriate.

`BulkOperations` is a different tool from `updateMulti`, with its own result semantics and ordering; do not swap them without checking transaction, version, and audit requirements.

## 16. ReactiveMongoTemplate and Fluent Updates

Spring Data MongoDB provides a matching reactive API. The difference is that **the return value is a publisher**, not an immediate `UpdateResult`:

~~~java
import reactor.core.publisher.Mono;
import com.mongodb.client.result.UpdateResult;

Mono<UpdateResult> one = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o301"))
    .apply(new Update().set("state", "PROCESSING"))
    .first();

Mono<UpdateResult> all = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW"))
    .apply(new Update().set("state", "QUEUED"))
    .all();

Mono<UpdateResult> upserted = reactiveTemplate.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399"))
    .apply(new Update().set("state", "NEW"))
    .upsert();
~~~

`reactiveTemplate` is an injected `ReactiveMongoTemplate`; these publishers **execute only when subscribed to**. In WebFlux applications, return or compose the `Mono` into the reactive chain rather than calling `block()` on the event loop.

When reactive transactions are needed, use `ReactiveMongoTransactionManager` with `TransactionalOperator` or an appropriately configured `@Transactional`. Reactive does not change the semantics of `updateFirst`/`updateMulti` and does not turn multi-document writes into transactions automatically.

## 17. Real Testing Against MongoDB and Spring Data Mapping

Unit tests mocking `MongoTemplate` only verify method invocations. They **do not** prove that queries map `state → state_code`, `@Version` auto-increments, or MongoDB applies `$inc` with the right numeric type. For critical updates, write integration tests against a real MongoDB test instance or Testcontainers.

### 17.1. Testing Matrix

| Scenario | What to Verify |
| --- | --- |
| `updateFirst` by ID and state | Only one document changes |
| `updateFirst` with non-existent ID | `matchedCount=0`, no upsert |
| `updateMulti` by tenant/state | All and only documents in scope are updated |
| Fluent `first/all` | Matches direct API semantics |
| Fluent `upsert` | Inserts when unmatched, populates `getUpsertedId()` |
| `@Field("state_code")` | Query/update using Java properties maps to the right BSON field |
| `@Version` | Increments version on mapped updates when version is omitted |
| Filter with expected version | Stale version does not update |
| `set(null)` vs. `unset` | Distinguishes BSON null from missing |
| `$inc` run twice | Increments twice; retries are not treated as idempotent |
| Concurrent writes across two documents | Does not assume transactions unless configured |
| Reactive fluent update | Publisher is subscribed and emits expected `UpdateResult` |

### 17.2. Illustrative Integration Test

The test creates two fixtures under an isolated tenant, then checks one direct update and one fluent update without touching the lesson fixture documents:

~~~java
package com.example.orderupdates;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.model.Filters;

@DataMongoTest
class OrderUpdateIntegrationTest {
    @Autowired MongoTemplate template;

    @Test
    void updatesOneThenAllAndMapsFieldAliases() {
        var collection = template.getDb()
            .getCollection("orders_updates_demo_003");
        List<String> ids = List.of("fixture-003-a", "fixture-003-b");

        collection.deleteMany(Filters.in("_id", ids));
        try {
            collection.insertMany(List.of(
                new Document("_id", ids.get(0))
                    .append("tenant_id", "fixture-tenant-003")
                    .append("state_code", "NEW")
                    .append("retry_count", 0)
                    .append("version", 0L),
                new Document("_id", ids.get(1))
                    .append("tenant_id", "fixture-tenant-003")
                    .append("state_code", "NEW")
                    .append("retry_count", 0)
                    .append("version", 0L)
            ));

            var one = template.updateFirst(
                Query.query(Criteria.where("id").is(ids.get(0))),
                new Update().set("state", "PROCESSING"),
                OrderDocument.class
            );
            assertThat(one.getMatchedCount()).isEqualTo(1L);

            var all = template.update(OrderDocument.class)
                .matching(Criteria.where("tenantId")
                    .is("fixture-tenant-003")
                    .and("state").is("NEW"))
                .apply(new Update().inc("retryCount", 1))
                .all();
            assertThat(all.getMatchedCount()).isEqualTo(1L);

            Document first = collection.find(
                Filters.eq("_id", ids.get(0))
            ).first();
            Document second = collection.find(
                Filters.eq("_id", ids.get(1))
            ).first();

            assertThat(first).isNotNull();
            assertThat(first.getString("state_code"))
                .isEqualTo("PROCESSING");
            assertThat(second).isNotNull();
            assertThat(second.getInteger("retry_count"))
                .isEqualTo(1);
            assertThat(first.containsKey("state")).isFalse();
        } finally {
            collection.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

**Run only against an isolated test database**: the test deletes both fixture IDs during setup and cleanup. To fully verify optimistic locking, add a second test with expected version, read back the BSON version, and assert a stale update has `matchedCount = 0`. Transaction tests must run on a MongoDB topology that actually supports transactions.

### 17.3. Do Not Infer Raw BSON From Java Output Alone

To confirm `state` → `state_code` mapping, inspect the raw document:

~~~javascript
db.orders_updates_demo_003.findOne(
  { _id: "fixture-003-a" },
  { _id: 1, state_code: 1, state: 1, version: 1 }
);
~~~

Once the test cleans up fixtures, this query returns `null`. Use it only **while the fixture exists**, or substitute your own ID in a learning environment. Never run exploratory assumptions against production data when schemas do not match.

## 18. Troubleshooting Common Issues

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `updateFirst` modifies no document | Wrong database, collection, ID, field mapping, state, or version in filter | Check `matchedCount` and actual BSON document |
| `updateFirst` modifies an "arbitrary order" | Filter matched multiple documents without a unique key | Use `_id` or `findAndModify` with sort |
| Adding `Sort` still ignores order on older MongoDB | `updateFirst` does not support sort before MongoDB 8.0 | Use `findAndModify` |
| `updateMulti` modifies only part of expected data | Overly narrow tenant/state filter, concurrent writers, or partial failure | Check `matchedCount`, query, and post-write data |
| `modifiedCount=0` even though `matchedCount>0` | Setting the same existing value, or update caused no BSON change | Inspect operators and auto-versioning |
| An update still increments version | `@Version` is mapped and version field was omitted | Compare BSON before/after; separate auto-increment from optimistic check |
| Stale update still succeeds | Query lacks expected version condition | Add `Criteria.where("version")` |
| Raw update accidentally creates field `state` | Used Java property name directly in MongoDB driver | Use BSON field `state_code` in raw driver or use mapped updates |
| `upsert` creates unexpected documents | Confused update with upsert, or overly broad filter / missing unique key | Review `getUpsertedId`, indexes, and filter |
| `setOnInsert` does not modify existing documents | Operator runs only when upsert inserts new document | Use `set` or a conditional backfill |
| `$inc` increments counter twice | Retried without idempotency | Use state predicate/event marker or idempotency key |
| `$unset` makes field disappear | Expected semantics, unlike BSON null | Use `set(field, null)` if you want null |
| Multi-document update fails partway | No surrounding transaction | Design a transaction or retry/compensation job |
| Reactive update has no effect | `Mono` was never subscribed to | Compose/subscribe and inspect `UpdateResult` |
| State-based updates are slow | Missing index, unselective filter, or high write contention | Inspect execution plan and write metrics |

## 19. Hands-on Practice

Each exercise below assumes you re-seeded the fixture in Section 2; **do not chain update exercises sequentially on the same mutated state**.

### Exercise 1 — Choosing the API

Requirement: transition **one** order with `_id = o301` from `NEW` to `PROCESSING`. What should you use?

**Answer:**

~~~java
template.updateFirst(
    Query.query(Criteria.where("id").is("o301")
        .and("state").is("NEW")),
    new Update().set("state", "PROCESSING"),
    OrderDocument.class
);
~~~

Fluent equivalent uses `template.update(OrderDocument.class).matching(...).apply(...).first()`.

### Exercise 2 — Updating Multiple Documents by Tenant

Requirement: increment `retry_count` by 1 for **all** `NEW` orders belonging to tenant `t01`. How many documents match in the original fixture?

**Answer:**

~~~java
UpdateResult result = template.update(OrderDocument.class)
    .matching(Criteria.where("tenantId").is("t01")
        .and("state").is("NEW"))
    .apply(new Update().inc("retryCount", 1))
    .all();
// matchedCount=3 on the original fixture (o301, o302, o305).
~~~

`o304` belongs to `t02`, so it is untouched.

### Exercise 3 — Matched vs. Modified

A raw MongoDB `updateOne({ _id: "o303" }, { $set: { state_code: "PAID" } })` returns `matchedCount=1, modifiedCount=0`. Did the query fail?

**Answer:** No. The document matched, but the value was already `PAID`, so no BSON difference occurred. If the same command runs through a mapped `MongoTemplate` with `@Version`, check whether version incremented.

### Exercise 4 — True Optimistic Locking

Entity `o301` was read by a client at version 0, while another writer bumped version to 1. How do you prevent a stale update?

**Answer:** add `version=0` to the `Query` alongside the ID and business predicates. If `matchedCount=0`, nothing is written; handle the conflict afterward. `@Version` auto-increment in an update query **does not replace** an expected-version predicate.

### Exercise 5 — Upsert and Defaults

Requirement: if `o399` does not exist, insert a `t01/NEW` order with `retryCount=0`; if it already exists, change `totalVnd` without resetting `retryCount`.

**Reference answer:**

~~~java
template.update(OrderDocument.class)
    .matching(Criteria.where("id").is("o399")
        .and("tenantId").is("t01"))
    .apply(new Update()
        .set("totalVnd", 180000L)
        .setOnInsert("state", "NEW")
        .setOnInsert("retryCount", 0))
    .upsert();
~~~

`setOnInsert` applies only on the insert branch; add a unique index if there is a natural key other than `_id`.

### Exercise 6 — Sort and the "Oldest Order"

Why should you not call `updateFirst(query.with(Sort.by("createdAt")), ...)` to "claim the oldest order" on MongoDB 7.x?

**Answer:** `updateFirst` does not support selection ordering on MongoDB prior to 8.0. Use `findAndModify` with `Query.with(Sort)` to select and transition state in a single atomic document operation, given a schema with `createdAt` and a suitable index.

### Exercise 7 — Updating Part of an Embedded Document

To delete `delivery.note` while preserving `delivery.city`, which operator should you use?

**Answer:**

~~~java
template.updateFirst(
    Query.query(Criteria.where("id").is("o301")),
    new Update().unset("delivery.note"),
    OrderDocument.class
);
~~~

Do not replace the entire `delivery` object with an instance containing only `city` when the goal is merely removing the note.

### Exercise 8 — Multi-Document Update and Retry

A batch increments `retryCount` across 2,000 orders. The connection times out after sending the update; the service does not know if the server executed it. Should it immediately retry with `$inc`?

**Answer:** Do not retry blindly, because the first attempt may have committed and a retry would increment again. Design state predicates, idempotency keys, or verifiable batch checkpoints; consider transactions or compensation as required.

## References

- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `updateFirst`, `updateMulti`, fluent update, `@Version`, upsert, and `findAndModify`.
- [Spring Data MongoDB — `MongoOperations` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html): `updateFirst`/`updateMulti` overloads and return types.
- [Spring Data MongoDB — `Update` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html): builder for update operators.
- [Spring Data MongoDB — Fluent Update API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/FluentMongoOperations.html): `update(Class)`, `matching`, `apply`, and terminal operations.
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/): `updateOne`, `updateMany`, document-level atomicity, and write results.
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/): `$set`, `$inc`, `$unset`, `$setOnInsert`, and other operators.
- [MongoDB Manual — Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/): computing update values from expressions over the document.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): limits of multi-document updates and transactions.
