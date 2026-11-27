# MongoTemplate for Conditional CRUD, Bulk Operations, and Array Updates in Spring Data MongoDB

## Learning Objectives

In Spring Data MongoDB, `MongoRepository` lets developers work with entities in a familiar way, yet many business workflows must express **conditions directly at write time**: decrementing inventory only if stock is sufficient, transitioning an order from `PENDING` to `PAID` only if it has not been cancelled, syncing thousands of records from an ERP, or updating exact elements inside an array of embedded documents. Reading a document into Java, modifying it, and calling `save` is not always safe because another request may modify the document between your read and write.

**`MongoTemplate`** provides fine-grained APIs for `Query`, `Criteria`, `Update`, `findAndModify`, `upsert`, `BulkOperations`, and array updates via MongoDB positional operators.

This lesson belongs to **Database Engine Document MongoDB → Spring Data MongoDB → MongoTemplate for Conditional CRUD, Bulk Operations, and Array Updates**.

After studying this lesson, you will be able to:

- Explain the role of `MongoTemplate` compared to `MongoRepository` and the MongoDB Java Driver.
- Use `Query`/`Criteria` to filter by tenant, status, time ranges, and array elements.
- Execute `insert`, `save`, `find`, `findOne`, `exists`, `count`, and `remove`.
- Use `Update` for `$set`, `$unset`, `$inc`, `$setOnInsert`, `$push`, `$addToSet`, and `$pull`.
- Inspect `UpdateResult` to distinguish matched, modified, upserted, and no-op writes.
- Use `updateFirst`, `updateMulti`, `upsert`, and `findAndModify` to perform conditional updates.
- Design atomic conditional writes, optimistic locking, and idempotent retries.
- Distinguish `BulkOperations.BulkMode.ORDERED` from `UNORDERED` and handle partial success.
- Apply `$`, `$[]`, and `$[identifier]` to update the appropriate array elements.
- Configure `Update.filterArray` and understand mapping limits on array filters.
- Handle nested arrays, duplicate elements, missing arrays, nested field names, and schema evolution.
- Distinguish single-document atomicity, multi-document bulk operations, and MongoDB transactions.
- Evaluate indexes, performance, security, and error observability.
- Write Java examples and practice safely on lab data.

> **Core Principle:** In MongoDB, an update on a **single document** is atomic, even when modifying multiple fields or multiple elements within that document's arrays. `updateMulti` and `BulkOperations` are **not automatically atomic across multiple documents**.

---

## 1. Where Does MongoTemplate Fit in Spring Data MongoDB?

~~~text
REST API / Scheduler / Message Consumer
               |
               v
          Service Layer
               |
         +-----+------+
         |            |
         v            v
   MongoRepository  MongoTemplate
   CRUD abstraction Query/Update/Bulk
         |            |
         +-----+------+
               |
               v
       MappingMongoConverter
       @Document/@Field/@Id/@Version
               |
               v
       MongoDB Java Driver
               |
               v
       mongod / mongos / Atlas
~~~

### 1.1. MongoRepository

Repositories expose entity access through methods such as `save`, `findById`, `deleteById`, derived queries, and paging. This fits most straightforward CRUD use cases.

### 1.2. MongoTemplate

The template lets you invoke operations directly:

~~~java
mongoTemplate.find(query, Order.class);
mongoTemplate.updateFirst(query, update, Order.class);
mongoTemplate.updateMulti(query, update, Order.class);
mongoTemplate.upsert(query, update, Order.class);
mongoTemplate.findAndModify(query, update, options, Order.class);
mongoTemplate.bulkOps(BulkMode.UNORDERED, Order.class);
~~~

This enables services to update targeted fields without rewriting entire entities.

### 1.3. Native Driver and Spring Mapping

`MongoTemplate` uses Spring Data entity metadata. If a Java property is annotated with `@Field("tenant_id")`, the template translates `tenantId` to BSON field `tenant_id` in queries specifying the entity type. However, never assume **every API**—especially raw driver calls or `arrayFilters`—maps field names identically.

### 1.4. Not a Mutually Exclusive Choice

A project can use `MongoRepository` for simple queries alongside `MongoTemplate` inside custom repositories or services for conditional writes and bulk operations.

---

## 2. Setting Up Spring Boot

Illustrative Maven dependency:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-mongodb</artifactId>
</dependency>
~~~

Spring Boot normally creates `MongoTemplate` via auto-configuration when MongoDB properties are configured.

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final MongoTemplate mongoTemplate;

    public OrderService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    // Methods using template are shown in subsequent sections.
}
~~~

Method signatures and dependency versions may vary by Spring Boot/Spring Data release. Use your project's BOM/dependency management and consult the official documentation for your active version.

### 2.1. URI and Security

In deployed environments, supply the MongoDB URI via environment variables or a secret manager. Never commit passwords into config files or print full connection strings to logs.

### 2.2. Lab Database

Examples use the `mongo_template_lab` database and `orders`/`inventory` collections. Never run the lesson's update or delete commands against production.

---

## 3. Illustrative Entity and Field Name Mapping

MongoDB stores BSON:

~~~javascript
{
  _id: "ORD-101",
  tenant_id: "tenant-a",
  status: "PENDING",
  items: [
    { sku: "SKU-A", quantity: 2, unit_price_minor: NumberLong("100000") },
    { sku: "SKU-B", quantity: 1, unit_price_minor: NumberLong("200000") }
  ],
  tags: ["priority"],
  total_minor: NumberLong("400000"),
  version: NumberLong("1"),
  created_at: ISODate("2026-11-14T01:00:00Z")
}
~~~

Spring Data entity:

~~~java
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("orders")
public class Order {

    @Id
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String status;

    private List<OrderLine> items;

    private List<String> tags;

    @Field("total_minor")
    private Long totalMinor;

    @Version
    private Long version;

    @Field("created_at")
    private Instant createdAt;

    public Order() {
    }

    // Getters/setters omitted to keep focus on MongoTemplate.
}
~~~

~~~java
public class OrderLine {

    private String sku;
    private int quantity;

    @Field("unit_price_minor")
    private long unitPriceMinor;

    public OrderLine() {
    }

    // Matching getters/setters.
}
~~~

### 3.1. Java Names Differing from BSON

| Java property | MongoDB BSON field |
|---|---|
| `id` | `_id` |
| `tenantId` | `tenant_id` |
| `status` | `status` |
| `items.quantity` | `items.quantity` |
| `items.unitPriceMinor` | `items.unit_price_minor` |
| `totalMinor` | `total_minor` |
| `createdAt` | `created_at` |
| `version` | `version` |

When passing entity type `Order.class`, you can use mapped Java property paths. With raw collection names or `Update.filterArray`, know clearly which paths are mapped and which go straight to MongoDB.

### 3.2. Always Scope Queries to the Tenant

`tenantId` must never be accepted blindly from a request body. In multi-tenant applications, derive the tenant from the authenticated security context.

---

## 4. Preparing Data in mongosh

~~~javascript
use mongo_template_lab

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenant_id: "tenant-a",
    status: "PENDING",
    items: [
      { sku: "SKU-A", quantity: 2, unit_price_minor: NumberLong("100000") },
      { sku: "SKU-B", quantity: 1, unit_price_minor: NumberLong("200000") }
    ],
    tags: ["priority"],
    total_minor: NumberLong("400000"),
    version: NumberLong("1"),
    created_at: ISODate("2026-11-14T01:00:00Z")
  },
  {
    _id: "ORD-102",
    tenant_id: "tenant-a",
    status: "PAID",
    items: [
      { sku: "SKU-A", quantity: 1, unit_price_minor: NumberLong("100000") }
    ],
    tags: [],
    total_minor: NumberLong("100000"),
    version: NumberLong("2"),
    created_at: ISODate("2026-11-13T02:00:00Z")
  },
  {
    _id: "ORD-201",
    tenant_id: "tenant-b",
    status: "PENDING",
    items: [
      { sku: "SKU-A", quantity: 3, unit_price_minor: NumberLong("100000") }
    ],
    tags: [],
    total_minor: NumberLong("300000"),
    version: NumberLong("1"),
    created_at: ISODate("2026-11-14T02:00:00Z")
  }
]);

db.inventory.insertMany([
  { _id: "SKU-A", tenant_id: "tenant-a", available: 3 },
  { _id: "SKU-B", tenant_id: "tenant-a", available: 1 }
]);
~~~

**Important:** Exercises should use a clean snapshot/reset or distinct IDs per exercise so prior operations do not skew subsequent results.

---

## 5. Basic CRUD with MongoTemplate

### 5.1. Insert

~~~java
Order order = new Order();
// Set id, tenantId, status, and remaining properties.
Order saved = mongoTemplate.insert(order);
~~~

`insert` creates a new document; if `_id` already exists, the unique index raises a duplicate key error. It does not fall back to updating.

### 5.2. Save

~~~java
mongoTemplate.save(order);
~~~

`save` performs insert-or-update semantics based on ID and mapping metadata. When saving an existing entity, it may replace the **entire** document, subject to specific constraints; never treat it as an unconditional field-level `PATCH`. `@Version` provides optimistic locking where supported by Spring Data.

### 5.3. FindById

~~~java
Order found = mongoTemplate.findById(
    "ORD-101",
    Order.class
);
~~~

### 5.4. Conditional FindOne

~~~java
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Criteria;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Order order = mongoTemplate.findOne(
    query,
    Order.class
);
~~~

If multiple documents match, "first" has no deterministic business ordering. When temporal ordering is required, add an explicit sort with a tie-breaker.

### 5.5. Find, Sort, and Limit

~~~java
import org.springframework.data.domain.Sort;

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
);

query.with(
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")
    )
);
query.limit(20);

List<Order> orders = mongoTemplate.find(
    query,
    Order.class
);
~~~

### 5.6. Projection

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
);

query.fields()
    .include("id")
    .include("status")
    .include("totalMinor");
~~~

An entity loaded via a projection contains only a subset of fields. **Never pass this partial entity to `save` to replace the full document** unless explicitly intended and guarded.

### 5.7. Exists and Count

~~~java
boolean exists = mongoTemplate.exists(
    Query.query(
        Criteria.where("id").is("ORD-101")
            .and("tenantId").is("tenant-a")
    ),
    Order.class
);

long count = mongoTemplate.count(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("PENDING")
    ),
    Order.class
);
~~~

Prefer `exists` instead of loading a full entity when you only need to check existence.

---

## 6. Criteria: Making Conditions Part of Business Logic

### 6.1. Comparisons and Ranges

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").in("PENDING", "PROCESSING")
        .and("totalMinor").gte(100_000L)
);
~~~

### 6.2. Common Operators

| Method | Meaning |
|---|---|
| `is(value)` | Equals |
| `ne(value)` | Not equal |
| `gt/gte/lt/lte` | Range comparisons |
| `in/nin` | Set membership / exclusion |
| `exists` | Field presence or absence |
| `elemMatch` | Single array element satisfies all conditions |
| `andOperator` | Logical AND |
| `orOperator` | Logical OR |
| `regex` | Regex match; control input and index usage |
| `size` | Array length |

### 6.3. Explicit AND/OR

~~~java
Criteria states = new Criteria().orOperator(
    Criteria.where("status").is("PENDING"),
    Criteria.where("status").is("PROCESSING")
);

Query query = Query.query(
    new Criteria().andOperator(
        Criteria.where("tenantId").is("tenant-a"),
        states
    )
);
~~~

When combining multiple conditions on the same field, use operators that express the intended logic cleanly; avoid attaching conflicting `Criteria` clauses to the exact same BSON key.

### 6.4. Never Turn Client JSON Directly into Raw Queries

Allowing users to pass arbitrary `$where`, massive `$regex`, internal system field names, or update operators can overload queries or mutate unauthorized data. Whitelist fields, operators, sort keys, and tenant scope.

---

## 7. Motivation: Read–Modify–Save Has a Race Condition

Suppose stock for `SKU-A` is down to `1`:

~~~text
A reads available=1
B reads available=1
A decrements to 0 and saves
B decrements to 0 and saves
-> Both requests think they reserved 1 item.
~~~

The fix is placing the **precondition** inside the **same write operation**.

### 7.1. Native MongoDB

~~~javascript
db.inventory.updateOne(
  {
    _id: "SKU-A",
    tenant_id: "tenant-a",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
~~~

### 7.2. MongoTemplate Conditional Update

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

int requestedQuantity = 1;

if (requestedQuantity <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive"
    );
}

Query query = Query.query(
    Criteria.where("_id").is("SKU-A")
        .and("tenant_id").is("tenant-a")
        .and("available").gte(requestedQuantity)
);

Update update = new Update()
    .inc("available", -requestedQuantity);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    "inventory"
);

boolean reserved =
    result.wasAcknowledged()
    && result.getModifiedCount() == 1;
~~~

Here the collection name `"inventory"` and BSON field paths are used because no `Inventory.class` entity is defined. When using a typed entity, mapped Java property names can be used instead.

### 7.3. Why Does This Prevent Overselling?

The server evaluates the filter and applies the document update in one atomic step. Once A decrements stock to `0`, B's filter `available >= 1` no longer matches.

### 7.4. Transactions Are Still Needed Across Multiple Documents

If reserving inventory updates one document while creating an order writes another document, those two operations do not commit atomically together on their own. Use a transaction or compensating workflow/outbox as required.

---

## 8. Update Builder and Common Operators

### 8.1. `$set`

~~~java
Update update = new Update()
    .set("status", "PAID")
    .set("updatedAt", Instant.now());
~~~

Modifies only the specified fields. When updating with `Order.class`, `updatedAt` maps to `updated_at`.

### 8.2. `$unset`

~~~java
new Update().unset("obsoleteNote");
~~~

Removes the field from BSON entirely. Unlike `set("obsoleteNote", null)`—where `null` remains a stored BSON value—`unset` makes the field absent.

### 8.3. `$inc`

~~~java
new Update().inc("retryCount", 1);
~~~

Atomic increment at the document level. With uncontrolled retries, an operation can increment twice if a request is reprocessed independently.

### 8.4. `$min` and `$max`

~~~java
new Update()
    .min("lowestPrice", 100_000)
    .max("highestPrice", 500_000);
~~~

Do not apply these across mixed BSON numeric/string types without verifying comparison semantics.

### 8.5. `$mul`

~~~java
new Update().multiply("coefficient", 2);
~~~

Watch for overflow and floating-point precision when calculating prices.

### 8.6. `$currentDate`

~~~java
new Update().currentDate("updatedAt");
~~~

Lets the MongoDB server assign the timestamp rather than relying on individual application server clocks. Depending on auditing needs, Spring Data auditing may also be used.

### 8.7. `$setOnInsert`

~~~java
new Update()
    .set("status", "PENDING")
    .setOnInsert("createdAt", Instant.now());
~~~

`setOnInsert` applies only when an **`upsert` inserts** a new document. Never place the same field in both `set` and `setOnInsert`, as that causes a conflict.

---

## 9. `updateFirst`: Conditional State Transitions

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "PAID")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

If the order is already `CANCELLED`, the filter fails to match. This enforces a guarded state transition rather than blind overwriting.

### 9.1. `UpdateResult`

~~~java
boolean ack = result.wasAcknowledged();
long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

**Only read counts when the write is acknowledged.** With unacknowledged write concerns, count getters are unavailable.

### 9.2. Matched vs. Modified

| Matched | Modified | Interpretation |
|---:|---:|---|
| 0 | 0 | No document matched the predicate |
| 1 | 1 | One document was updated |
| 1 | 0 | Document matched, but the update produced no value change |
| N | M | Possible with `updateMulti`; matched and modified counts may differ |

Notably, `modifiedCount = 0` **does not prove the document does not exist**.

### 9.3. `First` Offers No Guaranteed Order

When a filter matches multiple documents, `updateFirst` must not be used to pick the "oldest order" based on natural order. Use a unique filter or `findAndModify` with an explicit sort for work queues.

---

## 10. `updateMulti`: Updating Multiple Documents

Example closing expired `PENDING` orders:

~~~java
Instant cutoff = Instant.parse(
    "2026-11-14T00:00:00Z"
);

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
        .and("createdAt").lt(cutoff)
);

Update update = new Update()
    .set("status", "EXPIRED")
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateMulti(
    query,
    update,
    Order.class
);
~~~

### 10.1. Per-Document Atomic, Not All-or-Nothing Across All Documents

If 10,000 orders match, some documents may already be updated before an error aborts execution. Never treat `updateMulti` as an atomic multi-document transaction.

### 10.2. Retries and Idempotency

`$set status=EXPIRED` paired with `status=PENDING` is far safer to retry than a bulk `$inc`. When business rules permit competing state transitions, enforce strict preconditions.

### 10.3. Bounding Update Scope

Batch jobs should always constrain tenant, status, date, or ID ranges, carry an audit/ticket reference, and enforce thresholds. Never allow unguarded collection-wide updates from client requests.

### 10.4. Never Assume All Indexes Will Be Used

A selective predicate with a matching index such as `(tenant_id, status, created_at)` minimizes scans; always confirm with `explain`.

---

## 11. `upsert`: Create If Absent

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("externalId").is("ERP-1001")
);

Update update = new Update()
    .set("status", "PENDING")
    .set("totalMinor", 300_000L)
    .setOnInsert("createdAt", Instant.now());

UpdateResult result = mongoTemplate.upsert(
    query,
    update,
    Order.class
);
~~~

This example assumes the entity defines an `externalId` property mapped to BSON `external_id`.

### 11.1. Unique Index Prevents Upsert Races

~~~javascript
db.orders.createIndex(
  { tenant_id: 1, external_id: 1 },
  { unique: true, name: "uk_orders_tenant_external" }
);
~~~

If two workers concurrently upsert a brand-new business key, a unique index is essential to protect identity. Handle duplicate key errors and retries appropriately.

### 11.2. Upsert with Volatile Filters Is Dangerous

Never use `upsert` for conditional stock decrements filtered by `available >= 3`. When stock is low, the filter misses and `upsert` can **insert a brand-new document**, violating business logic. Use `updateFirst` instead.

### 11.3. Distinguishing Update vs. Insert

~~~java
if (result.getUpsertedId() != null) {
    // A new document was inserted.
}
~~~

When `upsert` updates an existing record, `getUpsertedId()` is typically `null`.

### 11.4. Upsert Is Not Automatically Idempotent

An `upsert` containing `$inc` or a changing timestamp on every request is not idempotent. Define a source version or idempotency key when syncing via events or API retries.

---

## 12. `findAndModify`: Modify and Return Before/After Document

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("status", "PROCESSING");

Order updated = mongoTemplate.findAndModify(
    query,
    update,
    FindAndModifyOptions.options()
        .returnNew(true)
        .upsert(false),
    Order.class
);
~~~

- `returnNew(false)`: returns the document state before the update.
- `returnNew(true)`: returns the document state after the update.
- `upsert(false)` with no match: returns `null`.

### 12.1. Sorted Job Claiming

~~~java
Query ready = Query.query(
    Criteria.where("status").is("READY")
);
ready.with(
    Sort.by(Sort.Direction.ASC, "createdAt")
);

Job job = mongoTemplate.findAndModify(
    ready,
    new Update().set("status", "RUNNING"),
    FindAndModifyOptions.options()
        .returnNew(true),
    Job.class
);
~~~

Assume a `Job` entity is defined. Selecting and transitioning a single job is atomic at the document level; real worker queues also require leases, timeouts, heartbeats, and retry/idempotency handling.

### 12.2. Why Not Find and Then Update?

Two requests can both read the same `READY` job before either changes its status. `findAndModify` selects and transitions it atomically in one operation.

---

## 13. `@Version` and Optimistic Locking

Spring Data supports optimistic locking via `@Version` when using entity-aware operations.

~~~java
@Document("orders")
public class Order {
    @Id
    private String id;

    @Version
    private Long version;

    // ...
}
~~~

### 13.1. Save and Version

~~~text
Request A reads order, version=3
Request B reads order, version=3
A edits, saves -> version increments
B saves with stale version -> optimistic lock conflict
~~~

With acknowledged writes, Spring Data throws `OptimisticLockingFailureException` on stale versions.

### 13.2. Template Updates Do Not Automatically Add Version CAS

An `updateFirst` filtering only by ID **does not automatically append an expected version filter** just because the class carries `@Version`. Spring Data may auto-increment the version property in certain mapped update paths if not explicitly set, yet **incrementing a version is not the same as checking the prior version**.

### 13.3. Explicit Compare-and-Set (CAS)

~~~java
long expectedVersion = 3L;

Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("version").is(expectedVersion)
);

Update update = new Update()
    .set("status", "PAID")
    .inc("version", 1);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Version conflict, forbidden or missing order"
    );
}
~~~

Here the version is incremented explicitly rather than relying on untested auto-increment behavior.

### 13.4. Bulk Operations Do Not Replace Optimistic Entity Saves

`BulkOperations` does not enforce per-entity optimistic locking or callbacks the way `save` does. If CAS is needed in bulk writes, include the expected version inside each `Query` and reconcile outcomes by business key.

---

## 14. Conditional Deletes

### 14.1. Removing Multiple Documents

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("EXPIRED")
        .and("createdAt").lt(cutoff)
);

var deleteResult = mongoTemplate.remove(
    query,
    Order.class
);

System.out.println(
    deleteResult.getDeletedCount()
);
~~~

`remove(Query, Class)` can delete multiple documents. If only one document must be deleted, use a unique predicate or `findAndRemove`.

### 14.2. Soft Delete

~~~java
new Update()
    .set("deleted", true)
    .currentDate("updatedAt");
~~~

Soft deletes aid auditing and recovery, but every reader must honor the `deleted` flag, and uniqueness, TTL, and retention policies must be designed accordingly.

### 14.3. Deleting a Document vs. Removing an Array Element

`remove` deletes the entire order document. `Update.pull("items", ...)` removes only matching elements from the `items` array within a document.

### 14.4. Security

In multi-tenant systems, filters must always include the trusted tenant. Never let a caller pass another tenant's document ID for deletion without authorization.

---

## 15. BulkOperations: Optimizing Many Writes

Suppose you are syncing 30,000 changes from an ERP. Sending individual updates over the network incurs heavy round-trip overhead. `BulkOperations` batches write models together.

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED,
    Order.class
);
~~~

### 15.1. Ordered vs. Unordered

| Mode | Semantics | When to Use |
|---|---|---|
| `ORDERED` | Executed sequentially; stops on first error | Operations have dependencies |
| `UNORDERED` | Order not guaranteed; continues remaining ops on error | Independent writes, higher throughput |

**Neither mode automatically provides all-or-nothing transaction semantics.**

### 15.2. When Should You Avoid Bulk?

- You need atomic multi-document transactions without a configured transaction.
- You require per-record entity callbacks or optimistic locking paths that bulk omits.
- You need every updated entity returned immediately.
- Unbounded batches bloat the JVM heap with request objects.

### 15.3. One Bulk Operation Does Not Equal One Document

`bulk.updateMulti(query, update)` can modify thousands of documents even though it counts as a single write model appended to the builder. Always distinguish operation count from affected document count.

---

## 16. Bulk Update, Upsert, and Remove in Java

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED,
    Order.class
);

bulk.updateOne(
    Query.query(
        Criteria.where("id").is("ORD-101")
            .and("tenantId").is("tenant-a")
            .and("status").is("PENDING")
    ),
    new Update().set("status", "PROCESSING")
);

bulk.updateMulti(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("EXPIRED")
    ),
    new Update().set("status", "ARCHIVED")
);

bulk.upsert(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("externalId").is("ERP-102")
    ),
    new Update()
        .set("status", "NEW")
        .setOnInsert("createdAt", Instant.now())
);

bulk.remove(
    Query.query(
        Criteria.where("tenantId").is("tenant-a")
            .and("status").is("PURGED")
    )
);

BulkWriteResult result = bulk.execute();

System.out.println(result.getInsertedCount());
System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getDeletedCount());
~~~

### 16.1. Batch Size

The driver enforces protocol/command size limits and splits internal batches automatically. Even so, the application should chunk inputs into bounded batches (e.g., a few hundred operations based on benchmarks) to avoid holding millions of objects in heap and to simplify checkpointing and partial-failure handling.

### 16.2. Do Not Assume Callbacks, Auditing, or Versioning

Spring Data bulk operations do not invoke the full entity-save lifecycle, particularly optimistic locking and auditing callbacks. If you need `updatedAt`, `version`, or audit fields updated, specify them explicitly and test behavior.

### 16.3. Atomicity

Bulk writes boost throughput, but do not commit all operations atomically together. If a batch fails, earlier writes may already be persisted.

---

## 17. Bulk Partial Success and Error Handling

### 17.1. Ordered Bulk

If operation #12 hits a duplicate key error, subsequent operations do not execute. Previously executed operations are not rolled back automatically.

### 17.2. Unordered Bulk

MongoDB can continue processing independent operations. Never assume completion order matches append order.

### 17.3. Exceptions

Depending on the driver and Spring Data layer, errors surface as `MongoBulkWriteException` or translated Spring exceptions. Log failed operation indices, server error codes, and partial results when available instead of catching `Exception` and blindly retrying the entire batch.

### 17.4. Network Timeouts Do Not Mean Nothing Was Written

If the client times out after the server applied some or all writes, you cannot assume the batch never executed. Read current state by business key before retrying.

### 17.5. Idempotency

- Setting the same value via `$set` is easier to retry safely.
- `$inc` can double-count on retry.
- `$push` can append duplicate elements on retry.
- `upsert` paired with a unique index protects document identity.
- External side effects to message brokers or payment providers need separate idempotency keys.

### 17.6. Checkpointing

A sync job should follow:

~~~text
Read next source chunk
        |
        v
Build BulkOperations
        |
        v
Execute, record partial failures
        |
        v
Verify/reconcile affected business keys
        |
        v
Persist checkpoint
~~~

Checkpointing before writing risks data loss on crash; checkpointing after writing makes duplicate retries possible, making idempotency mandatory.

---

## 18. MongoDB's Three Positional Operators

| Operator | Meaning | Example |
|---|---|---|
| `$` | First element matching the query's array condition | `items.$.quantity` |
| `$[]` | Every element in the selected document's array | `items.$[].gift` |
| `$[line]` | Every element matching the `line` array filter | `items.$[line].quantity` |

Example array:

~~~javascript
{
  _id: "ORD-101",
  items: [
    { sku: "SKU-A", quantity: 2 },
    { sku: "SKU-B", quantity: 1 },
    { sku: "SKU-A", quantity: 4 }
  ]
}
~~~

If the array contains two `SKU-A` items:

- `$` updates **one** (the first matching item).
- `$[]` updates **all three** items.
- `$[line]` with filter `SKU-A` updates **two** items.

Confirm the exact business requirement before choosing an operator.

---

## 19. Positional `$`: Updating the First Matching Element

### 19.1. mongosh

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a",
    "items.sku": "SKU-A"
  },
  {
    $inc: { "items.$.quantity": 1 }
  }
);
~~~

### 19.2. MongoTemplate

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
        .and("items.sku").is("SKU-A")
);

Update update = new Update()
    .inc("items.$.quantity", 1);

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 19.3. A Matching Array Predicate Is Required

Selecting a document only by ID without matching an array element causes the positional operator to fail because no positional binding exists.

### 19.4. Limitations

- Updates only the first matched element.
- When a query filters multiple array paths, `$` binding can become ambiguous.
- Not suitable for upserts that arbitrarily create array elements.
- For nested arrays, prefer `$[identifier]`.

### 19.5. When an SKU Can Appear Multiple Times

`$` cannot fulfill a business rule to "update all items with this SKU." Use `$[line]` when that is the intent.

---

## 20. `$elemMatch`: Multiple Conditions on the Same Element

Given an array:

~~~javascript
items: [
  { sku: "SKU-A", quantity: 1 },
  { sku: "SKU-B", quantity: 8 }
]
~~~

This query:

~~~javascript
{
  "items.sku": "SKU-A",
  "items.quantity": { $gte: 5 }
}
~~~

matches because the two conditions are satisfied by **two different elements**.

Use `$elemMatch`:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "SKU-A",
      quantity: { $gte: 5 }
    }
  }
});
~~~

`MongoTemplate`:

~~~java
Criteria line = Criteria.where("sku")
    .is("SKU-A")
    .and("quantity").gte(5);

Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("items").elemMatch(line)
);
~~~

This binds both `sku` and `quantity` to the **same element**. That matters both for querying and for positional `$` matching.

---

## 21. All Positional `$[]`: Modifying Every Element

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", tenant_id: "tenant-a" },
  { $set: { "items.$[].gift": true } }
);
~~~

`MongoTemplate`:

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .set("items.$[].gift", true);

mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 21.1. Query Predicates Do Not Restrict `$[]` Elements

Even if the query filters `items.sku = "SKU-A"`, updating `items.$[].gift` modifies **every** element in `items`, including `SKU-B`.

### 21.2. Empty or Missing Arrays

If the array is empty, nothing changes. If the field is missing or not an array, positional updates can fail. Test behavior against realistic document shapes.

### 21.3. Upsert Constraints

When using `$[]` in an `upsert`, MongoDB enforces strict equality rules on the array field in the filter if inserting a new document. Avoid `upsert` for ordinary positional array edits when you only intend to modify existing documents.

---

## 22. Filtered Positional `$[line]` with `arrayFilters`

To increment `quantity` on **every** `SKU-A` item:

### 22.1. mongosh

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a"
  },
  {
    $inc: {
      "items.$[line].quantity": 2
    }
  },
  {
    arrayFilters: [
      { "line.sku": "SKU-A" }
    ]
  }
);
~~~

### 22.2. Spring Data

~~~java
Query query = Query.query(
    Criteria.where("id").is("ORD-101")
        .and("tenantId").is("tenant-a")
);

Update update = new Update()
    .inc("items.$[line].quantity", 2)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

UpdateResult result = mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

### 22.3. Roles of Query and `arrayFilters`

- `Query` selects **which documents** to update.
- `arrayFilters` selects **which elements** inside the array to update.

If no document matches `Query`, nothing updates. If a document matches `Query` yet no element matches `arrayFilters`, `modifiedCount` is `0`.

### 22.4. Mapping Behavior of `Update.filterArray`

Spring Data documentation notes that criteria passed to `filterArray` are forwarded directly to the driver **without entity field-name mapping**.

Suppose the entity defines:

~~~java
@Field("unit_price_minor")
private long unitPriceMinor;
~~~

To filter on the stored BSON field inside `line`, write:

~~~java
Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.unit_price_minor")
            .gte(100_000L)
    );
~~~

Do not pass `"line.unitPriceMinor"` when the database stores `unit_price_minor`.

### 22.5. Identifiers

`line` is a valid filter identifier, not a class name. It must start with a lowercase letter and conform to MongoDB's identifier rules.

### 22.6. Multiple Conditions

~~~java
Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
            .and("line.quantity").gte(2)
    );
~~~

Both `sku` and `quantity` evaluate on the same `line` element.

---

## 23. Comparing All Three Operators on the Same Data

Initial state:

~~~javascript
items: [
  { sku: "A", quantity: 1 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 3 }
]
~~~

### 23.1. `$`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101", "items.sku": "A" },
  { $inc: { "items.$.quantity": 1 } }
);
~~~

Result:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 3 }
]
~~~

### 23.2. `$[]`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $inc: { "items.$[].quantity": 1 } }
);
~~~

Result:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 3 },
  { sku: "A", quantity: 4 }
]
~~~

### 23.3. `$[line]`

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  { $inc: { "items.$[line].quantity": 1 } },
  { arrayFilters: [{ "line.sku": "A" }] }
);
~~~

Result:

~~~javascript
[
  { sku: "A", quantity: 2 },
  { sku: "B", quantity: 2 },
  { sku: "A", quantity: 4 }
]
~~~

**Run each test starting from the original document state**, rather than chaining all three commands sequentially and comparing against separate expected results.

---

## 24. Combining `updateMulti` with Filtered Positional Updates

To set `gift = true` on `SKU-A` across all `PENDING` orders for `tenant-a`:

~~~java
Query query = Query.query(
    Criteria.where("tenantId").is("tenant-a")
        .and("status").is("PENDING")
);

Update update = new Update()
    .set("items.$[line].gift", true)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

UpdateResult result = mongoTemplate.updateMulti(
    query,
    update,
    Order.class
);
~~~

### 24.1. Matched/Modified Counts Track **Documents**

If a single order has 100 `SKU-A` items updated, `modifiedCount` increments by **1** for that order—not by the number of modified array elements.

### 24.2. Not a Cross-Document Transaction

Each order updates atomically, but across 200 matching orders a mid-flight failure can leave some orders untouched. Use idempotent updates, compensation/reconciliation, or transactions where appropriate.

### 24.3. Tenant Filter Is Mandatory

`arrayFilters` selects line items, not tenants. Omitting the tenant predicate from `Query` will modify other customers' items.

---

## 25. Nested Arrays with Two Identifiers

Document:

~~~javascript
{
  _id: "CAT-1",
  warehouses: [
    {
      code: "HCM",
      bins: [
        { sku: "A", available: 10 },
        { sku: "B", available: 2 }
      ]
    },
    {
      code: "HN",
      bins: [
        { sku: "A", available: 8 }
      ]
    }
  ]
}
~~~

Decrement `SKU-A` in warehouse `HCM`:

~~~javascript
db.catalog.updateOne(
  { _id: "CAT-1" },
  {
    $inc: {
      "warehouses.$[wh].bins.$[bin].available": -1
    }
  },
  {
    arrayFilters: [
      { "wh.code": "HCM" },
      { "bin.sku": "A", "bin.available": { $gte: 1 } }
    ]
  }
);
~~~

`MongoTemplate`:

~~~java
Update update = new Update()
    .inc(
        "warehouses.$[wh].bins.$[bin].available",
        -1
    )
    .filterArray(
        Criteria.where("wh.code").is("HCM")
    )
    .filterArray(
        Criteria.where("bin.sku").is("A")
            .and("bin.available").gte(1)
    );

mongoTemplate.updateFirst(
    Query.query(
        Criteria.where("id").is("CAT-1")
    ),
    update,
    CatalogEntity.class
);
~~~

This example assumes `CatalogEntity` maps cleanly to the `catalog` collection. Real oversell prevention requires full schema invariants and concurrency strategies.

### 25.1. Duplicate Keys

If two warehouses share code `HCM` or two bins share `SKU-A`, filtered operators update **all matching elements**. If business rules allow only one, enforce subdocument IDs/validation or redesign the schema.

### 25.2. Large Nested Arrays

A single document holding thousands of hot bins suffers write contention and high serialization overhead. Consider modeling each `(warehouse, sku)` pair as its own document when workloads involve heavy concurrent updates.

---

## 26. `$push`: Appending Elements

~~~java
Update update = new Update()
    .push("tags", "priority");

mongoTemplate.updateFirst(
    query,
    update,
    Order.class
);
~~~

`$push` appends the element to the end of the array, even if an identical element already exists.

### 26.1. Pushing Multiple Elements

~~~java
Update update = new Update()
    .push("tags")
    .each("priority", "gift");
~~~

### 26.2. Modifiers

MongoDB's `$push` supports `$each`, `$position`, `$sort`, and `$slice` to insert, sort, and cap arrays. Spring Data provides matching builders; check method signatures for your dependency version.

### 26.3. Avoid Unbounded Event Arrays

Pushing every audit event onto an order document drives it toward the 16 MiB BSON size limit and creates write hotspots. Store long event histories in a separate `events` collection with a unique `eventId` and appropriate indexes.

### 26.4. Non-Idempotent Retries

If a request is retried, `$push` can append duplicate elements. For at-least-once event processing, use stable event IDs and deduplication.

---

## 27. `$addToSet`: Adding Only If Absent

~~~java
Update update = new Update()
    .addToSet("tags", "priority");
~~~

Adding multiple values:

~~~java
new Update()
    .addToSet("tags")
    .each("priority", "gift");
~~~

### 27.1. Equality Checks the Whole Element

Given embedded documents:

~~~javascript
{ sku: "A", quantity: 1 }
{ sku: "A", quantity: 2 }
~~~

These two subdocuments differ, so `$addToSet` keeps both. It **does not enforce uniqueness on a single subfield** like `sku`.

### 27.2. Does Not Replace a Unique Index

If you need line-item uniqueness per tenant + SKU across millions of records, consider separating into its own collection with a compound unique index or enforcing application invariants; `$addToSet` does not solve every case.

### 27.3. Ordering

`$addToSet` provides set-membership semantics, not a sorted list with ordering guarantees. Nor does it deduplicate pre-existing duplicates.

---

## 28. `$pull`: Removing Matching Elements

Removing a tag:

~~~java
new Update()
    .pull("tags", "priority");
~~~

Removing `SKU-B` items:

~~~java
import org.bson.Document;

Update update = new Update()
    .pull(
        "items",
        new Document("sku", "SKU-B")
    );
~~~

### 28.1. Multiple Elements Can Be Removed

If the array contains two `SKU-B` line items, `$pull` by SKU removes both. Do not mistake it for "remove only the first element."

### 28.2. `$pull` vs. `$pop` and `$unset`

- `$pull`: removes all elements matching a predicate.
- `$pop`: removes the first or last element of an array.
- `$unset` on a positional array element leaves a `null` slot rather than shrinking the array.

### 28.3. Updating Order Totals

Removing an item while leaving `total_minor` stale breaks business invariants. Use single-document aggregation pipeline updates, transactions, or server-side recalculation rather than treating array edits in isolation as sufficient.

---

## 29. Why Not Read a Java List and Call Save?

A tempting but flawed flow:

~~~text
A reads Order with items=[A,B]
B appends item C using $push
A updates item A's quantity
A saves the whole Order from its stale copy
-> Item C added by B is lost.
~~~

### 29.1. Update Only the Target Element

~~~java
Update update = new Update()
    .inc("items.$[line].quantity", 1)
    .filterArray(
        Criteria.where("line.sku").is("SKU-A")
    );

mongoTemplate.updateFirst(
    Query.query(
        Criteria.where("id").is(orderId)
            .and("tenantId").is(tenantId)
    ),
    update,
    Order.class
);
~~~

This reduces payload size and lost-update risk compared to replacing the entire array.

### 29.2. `@Version` and Save

When entity saves use proper optimistic locking, request A receives a conflict exception instead of silently dropping item C. Still, the application must handle conflicts, re-reads, and retries—never assume `save` merges lists automatically.

### 29.3. Oversized Arrays

Unbounded `items` or `events` arrays waste bandwidth and memory, increase write contention, and risk hitting the 16 MiB BSON document limit. Align schemas with query and update patterns.

---

## 30. Updates via Aggregation Pipelines

When updating multiple fields based on current values inside the same document, MongoDB supports **aggregation pipeline updates**.

`mongosh` example recomputing `total_quantity`:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-101",
    tenant_id: "tenant-a"
  },
  [
    {
      $set: {
        total_quantity: {
          $sum: "$items.quantity"
        }
      }
    }
  ]
);
~~~

Spring Data provides `AggregationUpdate` for such cases; exact builder APIs depend on the Spring Data version. For complex `$map`/`$filter` expressions, use supported DSL builders or raw BSON with careful field-name verification.

### 30.1. When It Fits

- Computing derived fields from existing fields in the same document.
- Recomputing sums across an array.
- Using `$map` to transform array elements expressionally.
- Using `$filter` to keep or drop elements with complex logic.
- Avoiding read–modify–save cycles on a single document.

### 30.2. When It Is Unnecessary

For simple increments (`$inc`), status sets (`$set`), or item removals (`$pull`), standard update operators are easier to read and profile.

### 30.3. Atomicity Remains Single-Document

An update pipeline on one document is still a single-document atomic write; it does not span multiple documents or external payment systems in a transaction.

---

## 31. Multi-Document Transactions

If placing an order must:

1. Decrement stock in `inventory`.
2. Insert into `orders`.
3. Write to `outboxEvents`.

and the business requires all-or-nothing atomicity in MongoDB, use a **multi-document transaction** on a supporting deployment.

### 31.1. MongoTransactionManager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

### 31.2. Transaction Boundary

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void reserveAndCreate(
        String tenantId,
        String sku,
        int quantity) {

    // Conditional inventory decrement.
    // Insert order.
    // Insert outbox event.
    // On failure, the transaction rolls back
    // per configured MongoDB/Spring semantics.
}
~~~

This is a pseudo-service snippet lacking full oversell/retry logic. You must check modified counts, abort when stock is insufficient, and handle transient transaction errors and unknown commit results.

### 31.3. Do Not Use Transactions for Massive Bulk Jobs

Transactions add overhead and have execution/resource limits. Backfilling millions of writes is usually better served by idempotent batches and reconciliation than one giant transaction.

### 31.4. External Systems

MongoDB transactions do not cover payment gateways, Kafka brokers, or email services atomically. Use the outbox pattern, idempotency keys, and compensating actions.

---

## 32. Indexes for Conditional CRUD and Array Queries

### 32.1. Queries by Tenant, Status, and Time

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  status: 1,
  created_at: 1
});
~~~

Useful for daily jobs expiring stale orders when query shapes align.

### 32.2. Unique Business Identity

~~~javascript
db.orders.createIndex(
  { tenant_id: 1, external_id: 1 },
  { unique: true }
);
~~~

If some documents lack `external_id`, consider a partial index or schema policy so uniqueness reflects actual business rules.

### 32.3. Multikey Array Indexes

~~~javascript
db.orders.createIndex({
  tenant_id: 1,
  "items.sku": 1
});
~~~

Helps locate documents containing an SKU, though it does not alter `arrayFilters` semantics or enforce SKU uniqueness inside the array.

### 32.4. Querying by `_id`

MongoDB already maintains a unique `_id` index. When filtering by ID and tenant, a new compound index is rarely needed for a single-document lookup, yet the tenant predicate remains mandatory for authorization.

### 32.5. Write Cost

Indexes increase insert, update, and delete overhead as well as storage footprint. Do not index every updated field mechanically.

### 32.6. Explain

~~~javascript
db.orders.find({
  tenant_id: "tenant-a",
  status: "PENDING"
}).explain("executionStats");
~~~

Examine keys/docs examined, `IXSCAN` vs. `COLLSCAN`, and execution time. A lab with a handful of documents does not reflect production behavior.

---

## 33. Bulk Jobs, Checkpoints, and Retry Strategies

A sync job should follow:

~~~text
Read source page
      |
Build operations (max batch size)
      |
Execute bulk
      |
Classify write errors and partial results
      |
Reconcile by business keys
      |
Persist checkpoint
      |
Next page
~~~

### 33.1. Why Checkpoint After Writing?

Checkpointing before executing a bulk write risks losing unapplied writes on a crash. Checkpointing after writing can trigger duplicate retries on crash—making idempotency, unique keys, and versions mandatory.

### 33.2. Never Blindly Retry `$inc`

If part of a batch's increments already succeeded, retrying the whole batch double-counts. Use source versions, contribution ledgers, or expected-state reconciliation.

### 33.3. Resource Limits

Oversized batches spike heap usage, network traffic, and lock contention, hurting online API p95 latency. Tune batch size and concurrency using real metrics.

### 33.4. Errors to Classify

- Duplicate key errors.
- Schema validation failures.
- Invalid update paths or `arrayFilters`.
- Write concern errors.
- Network timeouts.
- Permission/authorization errors.
- Optimistic locking conflicts.
- Document size limit violations.
- Transient topology changes.

Not every error should be retried immediately.

---

## 34. Observability During Data Updates

### 34.1. UpdateResult

~~~java
boolean acknowledged = result.wasAcknowledged();

if (acknowledged) {
    System.out.println(result.getMatchedCount());
    System.out.println(result.getModifiedCount());
    System.out.println(result.getUpsertedId());
}
~~~

### 34.2. BulkWriteResult

~~~java
BulkWriteResult result = bulk.execute();

System.out.println(result.getInsertedCount());
System.out.println(result.getMatchedCount());
System.out.println(result.getModifiedCount());
System.out.println(result.getDeletedCount());
System.out.println(result.getUpserts());
~~~

### 34.3. Matched/Modified Do Not Count Array Elements

An order where 10 array elements changed in one update still counts as **one modified document**.

### 34.4. Monitoring SLOs and Failures

| Suggested Metric | Purpose |
|---|---|
| `conditional_update_conflict_total` | Query no longer matched expected version/status |
| `bulk_batch_size` | Batch sizes executed |
| `bulk_partial_failure_total` | Partial write failures |
| `bulk_duplicate_key_total` | Unique constraint conflicts |
| `mongo_write_latency_p95` | Write latency |
| `array_update_noop_total` | No array element matched |
| `mongo_write_concern_error_total` | Durability acknowledgment errors |
| `reconciliation_backlog` | Records awaiting repair/replay |

These metric names are illustrative application instrumentation examples, not built-in MongoDB metric names.

---

## 35. Common Troubleshooting Scenarios

### 35.1. Positional Operator Cannot Find Element

Cause: the query lacks an array predicate while the update uses `items.$.quantity`. Add a matching array predicate or switch to a filtered positional operator with `arrayFilters`.

### 35.2. Missing or Non-Array Field

`$[]` or `$[line]` fails if the target field is missing or not an array. Apply schema validation, data migration, or explicit existence checks before updating.

### 35.3. No-Op When `arrayFilter` Does Not Match

`matchedCount=1` and `modifiedCount=0` can happen when the document matched `Query` but no element satisfied `line.sku`, or the new value equaled the existing value.

### 35.4. Wrong BSON Name Inside `arrayFilters`

`line.unitPriceMinor` fails to match if the document stores `line.unit_price_minor`. `filterArray` does not perform entity field mapping.

### 35.5. `$[]` Accidentally Modifies Too Much

Matching `items.sku=A` in `Query` does not restrict `$[]` to only `A`. Use `$[id]` when element filtering is needed.

### 35.6. `$pull` Deletes All Matching Elements

If duplicate SKUs exist in an array, all matching elements are removed. Assign subdocument IDs when targeting a single line item.

### 35.7. Bulk Does Not Stop on Error

`UNORDERED` continues running remaining operations. Inspect error lists and partial results rather than assuming batch failure rolled everything back.

### 35.8. Upsert Inserts Unwanted Records

If a filter includes volatile status or stock predicates that fail to match, `upsert` inserts a new document. Conditional business updates should use `updateFirst` without upsert.

### 35.9. Optimistic Locking Not Behaving as Expected

Having `@Version` alone does not turn every `updateFirst` into CAS. Add an explicit expected-version predicate or use supported entity save paths with acknowledged writes.

### 35.10. Projection Followed by Save Loses Data

Loading a partial entity omits other fields, and `save` overwrites the whole document. Use targeted updates or read-only DTOs.

### 35.11. Mismatched Field Names

With `@Field("tenant_id")`, querying a raw collection with `tenantId` bypasses mapping and fails to match. Inspect raw BSON and driver commands when debugging.

### 35.12. Slow Writes After Adding Indexes

Extra indexes increase write amplification and storage usage. Index only validated filter/sort paths and verify with `explain` and load tests.

---

## 36. Common Design Misconceptions

1. **"`save` is a `PATCH`."** It can replace the entire document.
2. **"Reading then writing guarantees the condition still holds."** Subject to race conditions.
3. **"`updateFirst` deterministically picks a stable record."** Never rely on natural order for business logic.
4. **"`updateMulti` is one big transaction."** False.
5. **"`upsert` prevents duplicates in all cases."** Requires a unique index.
6. **"Retrying `$inc` is automatically safe."** It can double-count.
7. **"Ordered bulk is all-or-nothing."** False.
8. **"Unordered bulk executes in append order."** Not guaranteed.
9. **"Bulk runs all `@Version` callbacks."** False.
10. **"`modifiedCount=0` means the document does not exist."** It can be a no-op match.
11. **"`$` updates every item matching the SKU."** Only the first matching element.
12. **"`$[]` only updates items matched by the `Query` array predicate."** False.
13. **"`$[line]` works without `arrayFilters`."** False.
14. **"`filterArray` automatically maps `@Field` names."** False.
15. **"Dotted predicates always match the same array item."** Use `$elemMatch` for same-element constraints.
16. **"`$push` never creates duplicates."** It can.
17. **"`$addToSet` enforces uniqueness by `subdocument.sku`."** False; it checks full-element equality.
18. **"`$pull` removes only the first matching element."** False.
19. **"Removing a line item won't affect the order total."** It can violate business invariants.
20. **"ID alone is enough in multi-tenant updates."** Tenant authorization is mandatory.
21. **"A network timeout proves the write failed."** False.
22. **"Having an index makes every array update fast."** Query plan and workload still matter.
23. **"A MongoDB transaction is atomic with the payment gateway."** False.
24. **"A database-level update succeeding means business state is valid."** Preconditions and validation are still required.
25. **"Modified document count equals modified array elements."** False.

---

## 37. Pre-Deployment Checklist

### 37.1. Queries and Mapping

- [ ] Tenant and authorization predicates are enforced.
- [ ] Typed queries use `Order.class` with aligned `@Field` mappings.
- [ ] Raw collection-name APIs use exact stored BSON field names.
- [ ] Queries enforce status/version preconditions at write time.
- [ ] Unique keys/indexes back all `upsert` operations.
- [ ] Sorts and limits never violate business correctness.

### 37.2. Atomicity and Concurrency

- [ ] Single-document invariants use conditional updates.
- [ ] `matchedCount` and `modifiedCount` are checked.
- [ ] Optimistic locking/versioning is applied where needed.
- [ ] Unprotected read–modify–save flows are eliminated.
- [ ] Multi-document invariants use transactions or compensating workflows.
- [ ] HTTP and event retries follow an idempotency policy.

### 37.3. Bulk Operations

- [ ] `ORDERED` vs. `UNORDERED` chosen according to dependencies.
- [ ] Batch sizes and concurrency are bounded.
- [ ] Partial successes and failures are explicitly handled.
- [ ] Increments and pushes are never blindly retried.
- [ ] Checkpointing and reconciliation are implemented.
- [ ] Auditing and versioning behavior verified.
- [ ] Metrics and alerts configured.

### 37.4. Arrays

- [ ] Correct choice among `$`, `$[]`, and `$[id]`.
- [ ] Query includes an array predicate whenever `$` is used.
- [ ] `$elemMatch` used when multiple predicates must match one element.
- [ ] `arrayFilters` use exact stored BSON field names.
- [ ] Missing and empty arrays are handled safely.
- [ ] Unintended elements are not modified.
- [ ] Duplicate SKU/subdocument behavior is defined.
- [ ] Dependent totals and invariants are updated alongside array edits.
- [ ] Unbounded arrays and the 16 MiB BSON limit are avoided.

---

## 38. Practice Exercises

### Exercise 1 — Basic CRUD

Create an `Order` with ID, `tenantId`, and `status`. Test `insert`, `findById`, `findOne`, and `save`; observe behavior on duplicate IDs.

### Exercise 2 — Conditional Queries

Find the 20 newest `PENDING` orders for `tenant-a`, sorted by `createdAt` and `_id`.

### Exercise 3 — Projections

Read only `id`, `status`, and `totalMinor`, then explain why that loaded entity should never be passed to `save` to replace the order.

### Exercise 4 — Inventory

Stock for `SKU-A` is `1`, and two clients concurrently decrement by `1`. Use a conditional update with `available >= 1` and demonstrate zero overselling.

### Exercise 5 — State Transitions

Transition `PENDING` to `PAID` only when tenant, ID, and status match. Distinguish `matched = 0` from `modified = 0`.

### Exercise 6 — UpdateMulti

Expire stale `PENDING` orders to `EXPIRED` strictly for `tenant-a`. Observe modified counts and retry behavior.

### Exercise 7 — Upsert

Sync ERP orders by `tenantId` + `externalId` with a unique index; simulate two concurrent writers inserting the same key.

### Exercise 8 — FindAndModify

Claim the oldest `READY` job using a sorted `Query` and `returnNew(true)`.

### Exercise 9 — @Version

Two threads concurrently load `version = 1`, then save conflicting edits. Analyze optimistic lock conflicts and acknowledged writes.

### Exercise 10 — Bulk ORDERED

Build an ordered bulk batch with a duplicate key error mid-batch. Observe which operations execute before and after the error.

### Exercise 11 — Bulk UNORDERED

Repeat Exercise 10 in unordered mode and process the partial result.

### Exercise 12 — Bulk Retries

A job incrementing counters via `$inc` hits a timeout with unknown outcome. Propose an idempotency key and reconciliation design.

### Exercise 13 — Positional $

An array contains two `SKU-A` elements. Use `items.$.quantity` to increment only the first element.

### Exercise 14 — elemMatch

One item has `sku = "SKU-A", qty = 1`, another has `sku = "SKU-B", qty = 8`. Contrast a plain dotted query with `$elemMatch` for `SKU-A` and `qty >= 5`.

### Exercise 15 — All Positional

Use `items.$[].gift = true` and verify every element updates even when the query filters on `SKU-A`.

### Exercise 16 — Filtered Positional

Use `Update.filterArray` to increment quantity on all `SKU-A` items without touching `SKU-B`.

### Exercise 17 — BSON Mapping

Java `unitPriceMinor` maps to BSON `unit_price_minor`. Write the correct `arrayFilters` condition on `line.unit_price_minor`.

### Exercise 18 — Nested Arrays

Decrement `SKU-A` in warehouse `HCM` only when `available >= 1` using two array filter identifiers.

### Exercise 19 — Missing Arrays

Test a positional update on a document missing `items`; analyze the error and schema validation approach.

### Exercise 20 — Push vs. addToSet

Append the `"priority"` tag twice using each operator and compare the resulting arrays.

### Exercise 21 — Pull

Remove `SKU-B` items and recompute `totalMinor` accurately.

### Exercise 22 — Transactions

Design a service that decrements inventory, inserts an order, and inserts an outbox event under `MongoTransactionManager`; describe mid-flight failure behavior.

### Exercise 23 — Multi-Tenant Security

Design an endpoint that transitions order status strictly for `trustedTenantId`, preventing callers from spoofing `tenantId`.

### Exercise 24 — Indexes

Create an index on `(tenant_id, status, created_at)` and use `explain` to compare plans on a sufficiently large dataset.

### Exercise 25 — Metrics

Track matched/modified/upserted/deleted counts and bulk partial failures; define an alert for rising conditional conflicts.

---

## 39. Review Questions

1. How does `MongoTemplate` differ from `MongoRepository`?
2. When should you prefer `MongoTemplate` over a repository method?
3. How does `@Field` mapping affect `Query` paths?
4. When must you use exact stored BSON names in queries?
5. Why is the tenant filter critical?
6. How do `insert` and `save` differ?
7. Why shouldn't `save` be used for partial `PATCH` updates?
8. Does `findOne` return a deterministic "first" record without a sort?
9. What kinds of conditions do `Query`/`Criteria` express?
10. How does `$set` differ from `$unset`?
11. Is `$inc` atomic at the document level?
12. Why can retrying `$inc` double-count?
13. When does `$setOnInsert` take effect?
14. How many documents does `updateFirst` modify?
15. Is `updateMulti` atomic across an entire collection?
16. How does `matchedCount` differ from `modifiedCount`?
17. What does `matched = 1, modified = 0` mean?
18. Why does `upsert` need a unique business key?
19. What risk arises from upserting with a stock condition?
20. Can `findAndModify` return the document after the update?
21. Why is `find` followed by `update` not equivalent to `findAndModify`?
22. Does `@Version` automatically add CAS checks to every `updateFirst`?
23. When is an explicit expected-version filter required?
24. How do `ORDERED` and `UNORDERED` bulk modes differ?
25. Do bulk operations replace transactions?
26. How should retries handle partial success in bulk writes?
27. Why doesn't bulk invoke per-entity auditing or optimistic locking callbacks?
28. How many matching elements does `$` modify?
29. Which elements does `$[]` modify?
30. Does `$[line]` require `arrayFilters`?
31. What does `$elemMatch` guarantee?
32. Does `Update.filterArray` map `@Field` names inside the filter?
33. How does query document selection differ from array element selection?
34. What limitation applies to positional `$` inside upserts?
35. Can nested arrays use multiple filter identifiers?
36. How does `$push` differ from `$addToSet`?
37. Does `$addToSet` enforce uniqueness by `subdocument.sku`?
38. Does `$pull` remove one or all matching elements?
39. Why can an array update leave the order total inconsistent?
40. When should you use an aggregation pipeline update?
41. What problem does `MongoTransactionManager` solve?
42. Does a MongoDB transaction cover an external payment gateway?
43. What does an unknown outcome on network timeout mean?
44. Why must you verify exact BSON field names?
45. Does a multikey index automatically make `arrayFilters` fast?
46. Should bulk checkpoints be saved before or after writing, and why?
47. Why are huge BSON arrays dangerous?
48. Which metrics help detect CAS conflicts?
49. Why are tests on 3 documents insufficient for performance conclusions?
50. When can a database-level "successful" update still be wrong business-wise?

---

## 40. Summary

**MongoTemplate** enables Spring Data MongoDB applications to express conditional writes, partial entity updates, and bulk operations where standard repository CRUD is awkward.

Three pillars to keep distinct:

1. **Conditional CRUD**: `Query`/`Criteria` enforce preconditions at write time; `Update` runs atomic document-level operators; `updateFirst`, `updateMulti`, `upsert`, and `findAndModify` carry distinct semantics.
2. **Bulk Operations**: `BulkOperations` batches write models for throughput without automatic all-or-nothing atomicity; handle ordered/unordered modes, partial success, idempotent retries, and checkpoints.
3. **Arrays**: `$` updates the first matched element, `$[]` updates all elements, and `$[identifier]` with `arrayFilters` targets filtered elements. `$elemMatch` ensures multiple predicates apply to the same element.

Operational principles:

- **Never read and save the whole entity** when concurrently updating individual fields.
- **`@Version` does not automatically turn template updates into CAS**; explicitly design version predicates.
- **Bulk does not replace transactions**, and external side effects never become atomic automatically.
- **Spring Data `filterArray` does not map entity field names**, so use exact stored BSON field names.
- **Matched and modified counts track documents**, not array elements.
- **Tenant filters, unique indexes, business invariants, retries, and observability** are core to correctness—not mere performance afterthoughts.

A reliable update must **modify the right data, only from permitted states, under concurrency, with safe failure recovery and retries**.

## References

- [Spring Data MongoDB — MongoTemplate CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html)
- [Spring Data MongoDB — Querying Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-query-operations.html)
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [Spring Data MongoDB — BulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/BulkOperations.html)
- [Spring Data MongoDB — Update API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Update.html)
- [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Update Documents](https://www.mongodb.com/docs/manual/tutorial/update-documents/)
- [MongoDB Manual — Update Operators](https://www.mongodb.com/docs/manual/reference/operator/update/)
- [MongoDB Manual — Positional $](https://www.mongodb.com/docs/manual/reference/operator/update/positional/)
- [MongoDB Manual — All Positional $[]](https://www.mongodb.com/docs/manual/reference/operator/update/positional-all/)
- [MongoDB Manual — Filtered Positional $[identifier]](https://www.mongodb.com/docs/manual/reference/operator/update/positional-filtered/)
- [MongoDB Manual — $elemMatch](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/)
- [MongoDB Manual — $push](https://www.mongodb.com/docs/manual/reference/operator/update/push/)
- [MongoDB Manual — $addToSet](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/)
- [MongoDB Manual — $pull](https://www.mongodb.com/docs/manual/reference/operator/update/pull/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
