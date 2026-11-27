# Distinguishing Multi-Document Insert, saveAll, and Bulk Operations

## 1. The Problem: Writing Thousands of Documents Is Not Just a Loop

In the **Bulk Writes** chapter of **Spring Data MongoDB**, common requirements include synchronizing a catalog from an ERP, importing many rows from CSV, or updating inventory counts for thousands of products. Developers may encounter several APIs that appear to do the same job:

- `MongoTemplate.insert(Collection, Entity.class)` or `insertAll(...)` to add multiple documents.
- `MongoRepository.saveAll(Iterable)` to save a collection of new or existing entities.
- `MongoTemplate.bulkOps(...)` to put multiple `insert`, `updateOne`, `updateMulti`, `remove`, and `upsert` operations into a bulk write plan.
- MongoDB Java Driver `MongoCollection.insertMany(...)` and `bulkWrite(...)` when working directly with BSON/driver APIs.

These APIs are **not semantically equivalent**. If you use `saveAll` for data that is required to be *create-only*, an existing record may be overwritten depending on how Spring Data identifies the entity and chooses the write path. Conversely, using `insert` for data that needs updating will trigger a duplicate key error. With bulk operations, the result can be **partially successful**, and callbacks or optimistic locking cannot be assumed to behave the same as single-entity `save`.

The goal is to know how to choose the right API based on **operation type, key immutability, error behavior, execution order, performance, versioning, and retryability**.

Running example: a system imports products into the `catalog_products` collection, which has an internal key `_id`, a business key (`tenantId`, `sku`), a product name, a status, and a stock quantity. After the initial import, another flow can send stock updates for existing products.

> This lesson uses Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and a compatible MongoDB version. The implementation behavior of `saveAll`, exception translation, lifecycle callbacks, and bulk APIs may vary across versions. Implementation-dependent aspects are explained separately; integration testing on the target deployment version is essential before going to production.

## 2. Quick Comparison Table

| Criterion | Multi-Document Insert | Repository `saveAll` | `BulkOperations` |
|---|---|---|---|
| Primary intent | **Create-only** | Save new/**existing** entities | Combine multiple explicitly specified write commands |
| Supported operations | Insert | Insert or save based on entity identification | Insert, update, upsert, replace, delete per API |
| On `_id` collision | Duplicate key error | May save/update existing entity or fail depending on version/entity state | Depends on each insert/upsert/update command and unique indexes |
| Automatically **one** MongoDB command? | Not guaranteed for every batch/size | **No** | Driver may split into multiple batches/commands |
| Automatically a transaction? | No | No | No |
| Supports ordered/unordered? | Driver insertMany has options; standard Spring Data insert does not expose the same bulk plan | Not an API for configuring `BulkMode` | Supports `BulkMode.ORDERED` or `UNORDERED` |
| `@Version`/entity lifecycle | Need to check the insert path and corresponding callbacks | Has entity save mechanism and appropriate optimistic locking | **Do not assume** bulk handles version/callbacks like single-entity save |
| Return value | Collection of entities or insert result depending on API | Iterable/List of saved entities depending on version | Aggregated `BulkWriteResult` counts |
| Best used for | Create-only seeding/importing | Saving a set of entities in an application workflow | Mixed insert/update/upsert/delete imports, efficient bulk updates |

The core point: **“sending multiple items” does not automatically mean “atomically writing all data”**. MongoDB guarantees atomicity for each write operation on a **single document**, but different documents within the same batch can have different outcomes when an error occurs.

### Write Strategy Selection Flow

~~~mermaid
flowchart TD
    A["Need to write multiple documents"] --> B{"Create-only, must not overwrite?"}
    B -->|"Yes"| C["MongoTemplate.insert / insertAll"]
    B -->|"No"| D{"Each entity already has full state, save as entities?"}
    D -->|"Yes"| E["Repository.saveAll + @Version control"]
    D -->|"No"| F{"Need update/upsert/delete by specific queries?"}
    F -->|"Yes"| G["MongoTemplate.bulkOps"]
    F -->|"No"| H["Review business contract and data model"]
    C --> I["Unique index + batch + retry policy"]
    E --> I
    G --> J["ORDERED/UNORDERED + result + partial failure"]
    J --> I
~~~

## 3. Sample Entity, Identity, and Unique Business Key

To keep the examples clear, we use a mutable Java class because `saveAll` with existing entities needs to demonstrate modifying state and then saving. All classes live in package `com.example.catalog`; Spring Boot must scan this package and have a valid MongoDB connection.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String sku;

    @Field("display_name")
    private String name;

    @Field("stock_qty")
    private long stock;

    private String status;

    @Version
    private Long version;

    protected CatalogProduct() {}

    public CatalogProduct(
            String id, String tenantId, String sku,
            String name, long stock, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.stock = stock;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public long getStock() { return stock; }
    public String getStatus() { return status; }
    public Long getVersion() { return version; }

    public void setName(String name) { this.name = name; }
    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

In MongoDB, the document has the following shape (omitting `_class` if present):

~~~json
{
  "_id": "prd-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Water Bottle 500 ml",
  "stock_qty": 20,
  "status": "ACTIVE",
  "version": 0
}
~~~

`@MongoId(FieldType.STRING)` requires the ID to be stored as a BSON String; `id` in Java maps to `_id`. `@Field("display_name")` and `@Field("stock_qty")` illustrate that typed queries/updates must map Java properties to their BSON field names.

**The `_id` key** is protected by MongoDB's default unique index on the collection. However, if the same tenant cannot have two products with the same SKU, a **compound** unique index is needed:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uq_product_tenant_sku" }
);
~~~

Before applying the index in production, you must check for existing duplicates, SKU normalization rules, how null/missing fields are handled, and tenant policies. Do not treat `existsByTenantIdAndSku` as a uniqueness constraint: two requests can both see that a record does not exist yet and write concurrently.

**Corresponding repository:**

~~~java
package com.example.catalog;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    Optional<CatalogProduct> findByTenantIdAndSku(
            String tenantId, String sku);
}
~~~

Because the entity has `@Version Long`, saved records carry a version for optimistic locking on supported write paths. The presence of this annotation is a **design constraint when comparing write APIs**, not a guarantee that every bulk operation will automatically enforce version checks.

## 4. Inserting Multiple Documents with MongoTemplate

### 4.1. One Collection, One Set of New Objects

When business logic requires **creating all items as new**, you can use `MongoTemplate.insert(Collection, Entity.class)`:

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductInsertService {
    private final MongoTemplate mongo;

    public ProductInsertService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public Collection<CatalogProduct> seedProducts() {
        List<CatalogProduct> products = List.of(
                new CatalogProduct(
                        "prd-101", "tenant-a", "BOTTLE-500",
                        "Water Bottle 500 ml", 20, "ACTIVE"),
                new CatalogProduct(
                        "prd-102", "tenant-a", "MUG-250",
                        "Ceramic Mug 250 ml", 35, "ACTIVE"));

        return mongo.insert(products, CatalogProduct.class);
    }
}
~~~

`mongo.insert(products, CatalogProduct.class)` uses the metadata of `CatalogProduct` to determine the collection and mapping. New documents are created; IDs that collide with a unique index are rejected by MongoDB. For version fields, verify how your framework version initializes the version on the insert path.

Key points to remember:

- Insert is **not** a way to update the price or stock of an existing product.
- A batch may be split by the driver into multiple write groups when exceeding server/driver limits.
- A batch containing multiple commands does not imply rolling back everything if one document fails.
- The method returns a collection of processed objects, **not** a per-document detailed report like `BulkWriteResult`.

### 4.2. insertAll: Collection Determined by Each Entity

`MongoTemplate.insertAll(Collection<? extends T>)` is useful when inserting multiple Spring Data objects; the write path can **group by collection** inferred from entity mapping.

~~~java
List<CatalogProduct> input = List.of(
        new CatalogProduct(
                "prd-201", "tenant-a", "NOTE-01",
                "Notebook", 14, "ACTIVE"),
        new CatalogProduct(
                "prd-202", "tenant-a", "PEN-01",
                "Fountain Pen", 60, "ACTIVE"));

Collection<CatalogProduct> inserted = mongo.insertAll(input);
~~~

When all items are `CatalogProduct`, the result is documents in `catalog_products`. If the collection contains multiple entity types targeting different collections, grouping and command ordering can differ; **do not use `insertAll` as a cross-collection transaction**.

`insertAll` and `insert(collection, Entity.class)` have different contracts for specifying the entity/collection. When you want the target collection and type of the entire batch to be explicit, the `insert(..., CatalogProduct.class)` overload is usually easier to control.

### 4.3. MongoDB Driver insertMany

At the driver level, the conceptual equivalent is:

~~~javascript
db.catalog_products.insertMany(
  [
    {
      _id: "prd-101",
      tenantId: "tenant-a",
      sku: "BOTTLE-500",
      display_name: "Water Bottle 500 ml",
      stock_qty: 20,
      status: "ACTIVE"
    },
    {
      _id: "prd-102",
      tenantId: "tenant-a",
      sku: "MUG-250",
      display_name: "Ceramic Mug 250 ml",
      stock_qty: 35,
      status: "ACTIVE"
    }
  ],
  { ordered: true }
);
~~~

With `MongoCollection<Document>.insertMany(...)` in the Java Driver, you can configure `InsertManyOptions.ordered(boolean)`. That is a **driver API**, not a `BulkMode` parameter of `MongoTemplate.insert(...)`. When working directly with raw `Document`, you must use the BSON field names `display_name` and `stock_qty`; there is no automatic mapping from Java entity properties unless routed through the corresponding converter.

## 5. saveAll: Saving New or Existing Entities

`MongoRepository.saveAll(Iterable)` belongs to the repository model and **does not mean “insertMany by another name”**. An entity can be identified as new or existing depending on metadata such as ID, `@Version`, and the `isNew` strategy.

### 5.1. Saving New Entities

~~~java
List<CatalogProduct> drafts = List.of(
        new CatalogProduct(
                "prd-301", "tenant-a", "BAG-01",
                "Canvas Bag", 10, "DRAFT"),
        new CatalogProduct(
                "prd-302", "tenant-a", "BAG-02",
                "Travel Bag", 5, "DRAFT"));

Iterable<CatalogProduct> saved = repository.saveAll(drafts);
~~~

`repository` is a bean of type `CatalogProductRepository`. When all entities are identified as **new**, the Spring Data MongoDB implementation in common versions may optimize the write path by batching inserts instead of calling save individually for each item. **Do not write tests or business designs that rely on a guarantee that `saveAll` always issues a single `insertMany` command.**

Because `@Version` is declared with nullable `Long`, an entity whose version is `null` is typically recognized by Spring Data as **new**. This is a critical detail: merely supplying an ID on an object is **not enough** to imply Spring Data will update an existing document.

### 5.2. Saving Existing Entities

~~~java
CatalogProduct existing = repository.findById("prd-101")
        .orElseThrow();

existing.setName("Insulated Bottle 500 ml");
existing.setStock(18);

repository.saveAll(List.of(existing));
~~~

On an existing-entity `save` write path, Spring Data can check the version and reject stale records via optimistic locking. If another request updated `prd-101` after we read it, you must handle `OptimisticLockingFailureException` according to business policy.

**Do not use `saveAll` to update a collection of incomplete entities** containing only an ID and a name. When the framework saves entity state, unloaded fields or fields holding default values can overwrite existing values. If the goal is to change a single field, use `Update.set` with an appropriate guard condition.

### 5.3. Why saveAll Might Not “Batch” the Way You Think

In many versions of Spring Data MongoDB, the implementation optimizes the case where **all entities are new**; when existing entities or a mixed set are present, saving may fall back to **multiple individual saves** rather than a single bulk write.

This can lead to:

- Round-trip counts depending on the number of entities and framework version.
- `@Version`, callbacks/auditing, and new/existing classification affecting the write path.
- Processing time for a mixed set of 1,000 entities differing significantly from 1,000 new documents.
- If one item fails, previously saved items **not being automatically rolled back**.

Therefore, `saveAll` prioritizes **entity-saving semantics**, not a bulk performance guarantee for every workload.

### 5.4. Do Not Replace Create-Only with exists + saveAll

The following pattern does not guarantee uniqueness:

~~~java
if (repository.findById("prd-301").isEmpty()) {
    repository.saveAll(List.of(
            new CatalogProduct(
                    "prd-301", "tenant-a", "BAG-01",
                    "Canvas Bag", 10, "ACTIVE")));
}
~~~

Two requests can both observe that the ID does not yet exist. Moreover, the entity's `isNew` state and `@Version` also affect save behavior. Use **insert + unique index** when business logic requires create-only; use an idempotency key or conditional upsert when handling replayed requests.

## 6. BulkOperations: Planning Multiple Write Operations

`MongoTemplate.bulkOps(BulkMode, Entity.class)` returns a `BulkOperations` builder. You add each operation to the plan, then call `execute()` to send them to MongoDB:

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        CatalogProduct.class);

bulk.insert(new CatalogProduct(
        "prd-401", "tenant-a", "PENCIL-01",
        "Pencil", 100, "ACTIVE"));

bulk.updateOne(
        Query.query(Criteria.where("id").is("prd-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("name", "Insulated Bottle New Edition"));

BulkWriteResult result = bulk.execute();
~~~

Required imports:

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
~~~

This example combines **insert and updateOne** in the same plan. When `execute()` is called, Spring Data translates the requests into write models/driver calls; the driver/server may split batches depending on limits and runtime conditions.

Commonly available operations:

| BulkOperations Method | Purpose |
|---|---|
| `insert(entity)` or `insert(List<?>)` | Add documents |
| `updateOne(query, update)` | Update one document matching the filter |
| `updateMulti(query, update)` | Update all documents matching the filter |
| `upsert(query, update)` | Update if matched, insert if not matched |
| `replaceOne(query, replacement)` | Replace a document with a new object matching the condition, with caveats around ID and schema |
| `remove(query)` | Delete documents matching the filter |
| `execute()` | Execute accumulated operations and return the aggregated result |

Choose the API based on need: bulk can handle **a heterogeneous list of operations**, not necessarily all inserts or saves of the same entity.

### 6.1. Example of a Conditional Bulk Stock Update

In sales workflows, you want to deduct stock only when **sufficient quantity is available**, never letting `stock` go negative. For each command, place the stock condition in the query and decrement with `$inc` directly on the server:

**StockDeduction.java**

~~~java
package com.example.catalog;

public record StockDeduction(
        String id, String tenantId, long amount,
        long expectedVersion) {
}
~~~

**StockBulkService.java**

~~~java
package com.example.catalog;

import com.mongodb.bulk.BulkWriteResult;
import java.util.List;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class StockBulkService {
    private final MongoTemplate mongo;

    public StockBulkService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public BulkWriteResult deduct(List<StockDeduction> commands) {
        if (commands == null || commands.isEmpty()) {
            throw new IllegalArgumentException("Batch must not be empty");
        }

        BulkOperations bulk = mongo.bulkOps(
                BulkOperations.BulkMode.UNORDERED,
                CatalogProduct.class);

        for (StockDeduction command : commands) {
            if (command.id() == null || command.tenantId() == null
                    || command.amount() <= 0
                    || command.expectedVersion() < 0) {
                throw new IllegalArgumentException(
                        "Invalid StockDeduction");
            }

            Query query = Query.query(
                    Criteria.where("id").is(command.id())
                            .and("tenantId").is(command.tenantId())
                            .and("version").is(command.expectedVersion())
                            .and("stock").gte(command.amount()));

            Update update = new Update()
                    .inc("stock", -command.amount())
                    .inc("version", 1);

            bulk.updateOne(query, update);
        }

        return bulk.execute();
    }
}
~~~

In the code, `Criteria` and `Update` use the Java property `stock`, while MongoDB actually stores `stock_qty`. Because the bulk is declared for `CatalogProduct.class`, Spring Data's mapping can translate the criteria and update to the corresponding BSON field names.

Conditions on the **same document** are evaluated at write time:

- `id` and `tenantId` identify the correct resource belonging to the tenant.
- `version = expectedVersion` performs **compare-and-set** against the revision that was read.
- `stock >= amount` prevents deducting from an insufficient quantity.
- `Update.inc("stock", -amount)` and `inc("version", 1)` change stock and version in the same operation.

**Do not rely on the framework to infer optimistic locking in bulk.** This snippet intentionally specifies the condition and increments `version` explicitly; test on your target Spring Data version, especially when other write paths also use `save`. Keep version usage consistent across all write paths.

`BulkWriteResult.getMatchedCount()` and `getModifiedCount()` are **aggregated counts**; if 10 commands only match 8, the result does not immediately indicate **which two commands** did not match. For APIs that need per-item feedback, you must maintain command IDs, run reconciliation, or use a dedicated tracking mechanism instead of assuming per-item results exist.

### 6.2. Why Does the Example Code Use UNORDERED?

In this example, each command is assumed to be independent on a single product. `UNORDERED` gives the driver/server ordering flexibility, which can improve performance and allow independent operations to keep executing even if some commands fail.

**Additional business constraint:** the `commands` list must not contain two conflicting operations on the same product/version or have ordering dependencies. Do not use `UNORDERED` to express “create then update” or “deduct stock then delete” when ordering is mandatory.

If two commands target the same document with different expected states, `UNORDERED` may execute them in an unpredictable order. Even `ORDERED` does not create a transaction; it only governs ordering/error handling within **a single bulk plan**.

## 7. ORDERED and UNORDERED: Behavior When Errors Occur

### 7.1. Ordered

With `BulkMode.ORDERED`, writes are requested to execute in the declared order; upon encountering a write error, the bulk normally stops processing subsequent operations according to ordered semantics.

~~~text
Input:  [insert A] [insert B] [insert C] [insert D]
                  ^
               B has duplicate _id

Ordered:
  A may have been inserted;
  B is rejected;
  C and D are not processed under the ordered flow.
~~~

Crucial point: **A is not automatically rolled back**. Ordered does not turn the entire sequence of operations into “all-or-nothing”.

### 7.2. Unordered

With `BulkMode.UNORDERED`, independent operations may be executed without guaranteeing declared order; if one operation fails, other operations may still be attempted.

~~~text
Input:  [insert A] [insert B] [insert C] [insert D]
                  ^
               B has duplicate _id

Unordered:
  B may fail;
  A, C, D may succeed;
  Do not rely on completion order.
~~~

Outcomes depend on the server, topology, other errors, and how batches are split. Do not assume all other operations *definitely* succeeded; inspect the actual state and exception/result.

### 7.3. Scenario Table

| Scenario | ORDERED | UNORDERED |
|---|---|---|
| **Order-dependent** steps | Better fit, still not a transaction | Unsuitable if order affects logic |
| Thousands of independent upserts | May be slower due to ordering constraints | Usually the performance candidate |
| Duplicate key mid-batch | Typically stops operations after error | Typically continues attempting other commands |
| Rollback of completed writes | None | None |
| Detailed per-command result | Not guaranteed from aggregated `BulkWriteResult` | Same |
| Correctness under concurrent writes | Needs appropriate filters/indexes/versions | Still needs the same mechanisms |

In a system with multiple consumers, choosing a bulk mode is only **part** of concurrency design. An ORDERED batch can still contend with requests from another process.

## 8. BulkWriteResult and Bulk Write Errors

`BulkOperations.execute()` returns a `BulkWriteResult` when execution succeeds. Values to inspect:

~~~java
BulkWriteResult result = bulk.execute();

int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserts = result.getUpserts().size();
~~~

For example, a batch with 2 inserts, 3 updateOne operations (only 2 matching documents), and 1 delete (no matching document) might report:

~~~text
insertedCount = 2
matchedCount  = 2
modifiedCount = 2 (if both updates actually changed data)
deletedCount  = 0
upserts       = 0
~~~

This is a **hypothetical example**, not a fixed result for every batch.

Important explanations:

- `matchedCount` counts update operations that matched documents, **not** necessarily the number of commands added.
- `modifiedCount` can be smaller than `matchedCount` if the new value equals the existing value.
- `getUpserts()` contains metadata for upserts that created new documents, but it is not a per-command business acknowledgement.
- When a bulk operation encounters an error, `execute()` may **throw an exception** instead of returning normally; you cannot always expect a complete `BulkWriteResult` from the success path.

In Spring Data, the exact exception class and error details depend on exception translation and version; you may see exceptions related to `BulkOperationException`, `BulkWriteException`, or translated data access exceptions. Do not write `catch(Exception e) { retryAll(); }` assuming no commands were executed.

### Partial Success Scenario

~~~mermaid
flowchart TD
    A["Bulk request with 4 operations"] --> B["One insert succeeds"]
    B --> C["One operation hits unique index error"]
    C --> D{"Bulk mode?"}
    D -->|"ORDERED"| E["Subsequent operations may stop"]
    D -->|"UNORDERED"| F["Other operations may still be attempted"]
    E --> G["Need to reconcile actual state"]
    F --> G
    G --> H["Safe retry by ID/event/version"]
~~~

If a batch contains operations that **increment quantities**, retrying the entire batch after an error can increment **twice** for items that already succeeded. With operations that **assign fixed values**, retrying may be safer for final state, yet you must still account for auditing, timestamps, and side effects. Every retry strategy must rely on business idempotency rather than solely on bulk ordered/unordered properties.

## 9. Bulk Upsert: Syncing Records by Business Key

If imported data from an external source has a natural key `(tenantId, sku)`, many systems want “update if present, insert if absent”. `BulkOperations.upsert(...)` is a candidate:

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.UNORDERED, CatalogProduct.class);

for (IncomingProduct incoming : sourceProducts) {
    Query query = Query.query(
            Criteria.where("tenantId").is(incoming.tenantId())
                    .and("sku").is(incoming.sku()));

    Update update = new Update()
            .set("name", incoming.name())
            .set("status", "ACTIVE")
            .setOnInsert("createdAt", importStartedAt);

    bulk.upsert(query, update);
}

BulkWriteResult result = bulk.execute();
~~~

Here `IncomingProduct` is a validated input DTO, `sourceProducts` is a collection of DTOs, and `importStartedAt` is the shared timestamp of the import run. **This is an illustrative snippet meant to sit inside a service**, not a complete class. If `CatalogProduct` does not declare a `createdAt` property as in the Section 3 model, extend the model or remove `setOnInsert("createdAt", ...)` before using it; do not add out-of-schema fields unthinkingly.

### 9.1. Upsert Design Considerations

1. Have a unique index `{ tenantId: 1, sku: 1 }` to prevent two concurrent imports from creating duplicate business keys.
2. Decide on IDs: the Section 3 model uses `@MongoId(FieldType.STRING)`, yet an upsert filtering only by business key without specifying `_id` can cause MongoDB to auto-generate an ObjectId. Keep ID schema, queries, filters, and upserts consistent, or use a stable application-assigned `_id`.
3. Do not let incoming data overwrite fields **not owned by the external source** (e.g., internal stock or user permissions).
4. Choose an explicit `null` policy: `set("name", null)` may write null rather than meaning “leave unchanged”.
5. Out-of-order import events require a reliable revision/timestamp, conditional updates, or a reconciliation strategy; a plain upsert can allow an older event to overwrite a newer one.
6. `upsert` does not imply automatic optimistic locking via entity `@Version` or related cascade saves.

In a lab exercise, you may simplify by storing IDs derived from the source namespace and inspecting raw BSON. In production systems, IDs should remain stable across imports and never depend on mutable names or attributes.

### 9.2. Difference Between upsert and saveAll

`saveAll` works on **entities** and new/existing detection; `BulkOperations.upsert` uses a **query specifying the target document** and an `Update` defining which fields to modify on match, plus fields set only on insert. Upsert is powerful for partial-field imports, provided indexes and concurrency are tightly managed.

## 10. @Version, Auditing, Callbacks, and Special Write Paths

A common misconception: “Since `@Version`/`@LastModifiedDate` is annotated on the entity, bulk operations automatically inherit all behaviors of repository save.”

**Do not assume this.** Spring Data MongoDB describes bulk operations as an API focused on write models; they **do not provide the full entity-level lifecycle events/callbacks and optimistic locking semantics of single-entity saves**. For batches containing updates, versioning must be explicitly designed and tested:

- Use a `version = expectedVersion` condition when business logic requires compare-and-set.
- Increment version according to a single consistent rule; avoid calling `inc("version", 1)` manually while another mechanism accidentally increments it again.
- Check `matchedCount`, because a version mismatch may not throw `OptimisticLockingFailureException` and instead simply skip updating.
- If an audit timestamp is needed, consider explicitly putting it in `Update.set("updatedAt", now)` in a controlled way; do not rely on callbacks running automatically in bulk.
- If business logic requires entity callbacks, complex validation, or per-entity domain events, you may need `saveAll`/`save` or a dedicated pipeline.

**Be cautious in the opposite direction as well:** callbacks may be involved in certain insert paths in the framework, yet you must not infer that every batch API triggers the exact same callback chain as `save`. Write tests for auditing, initial version assignment, and events against the exact write path in use.

### Avoid Updating from Partially Loaded Entities

If you need to update 100,000 product prices, you do not necessarily have to load 100,000 full entities and call `saveAll`. Using `bulkOps.updateOne` with `Update.set("price", ...)` and an appropriate filter typically reduces transferred data and avoids clobbering other fields. Conversely, if aggregate invariants must be enforced through the domain model with per-entity optimistic locking, that benefit may outweigh maximizing raw throughput.

## 11. Transactions, Atomicity, and Write Concern

### 11.1. Bulk Does Not Automatically Create a Transaction

A bulk command with multiple write models **is not automatically wrapped in a transaction**. Even with `BulkMode.ORDERED`, if the third operation fails, the first two operations can remain in the database.

If business logic requires multiple documents to succeed or roll back together, you need a properly configured MongoDB transaction (session, `MongoTransactionManager` or equivalent driver/session API, and a supported topology). Transactions add overhead and do not eliminate the need for error classification/retries; use them only when cross-document invariants genuinely demand them.

A multi-document transaction **can enclose** bulk operations on the same session when supported and properly configured by the framework; do not assume merely adding `@Transactional` is sufficient if the system lacks a transaction manager or compatible topology.

### 11.2. Write Concern and Retryable Writes

MongoDB-acknowledged operations can still time out on the client side after the server has already written the data. In that situation, the application may **not know for sure** whether the write succeeded.

- Write concern determines the level of acknowledgement and affects durability and latency.
- Driver retryable writes have their own scope and support conditions; they do not replace **business idempotency**.
- When a bulk contains `$inc`, `$push`, or state-dependent side effects, blindly retrying the entire batch can apply them twice.
- Use a unique request/event ID, stable business key, version/compare-and-set, checkpoint, or reconciliation to decide which operations can be re-executed.

### 11.3. Ordering and Transactions Are Two Different Concepts

| Concept | Question It Answers | What It Does Not Guarantee |
|---|---|---|
| `ORDERED` | Processing order of operations within the bulk plan | Rolling back earlier operations |
| `UNORDERED` | Allows independent commands to be processed flexibly | Ordering or that every command succeeds |
| Unique index | Prevents two documents from sharing a unique key | Atomicity of the entire batch |
| Optimistic locking | Prevents writing against a stale version on compliant paths | Automatic enforcement across every bulk update |
| Transaction | Commit/rollback scope of a properly configured transaction | Automatic activation simply from using bulk |
| Idempotency key | Allows a business intent to be safely reprocessed | Automatic provision merely from driver retry support |

## 12. Batch Splitting: Limits, Memory, and Recoverability

An import can contain millions of rows. Do not build a `List` of millions of entities and call `saveAll`, or construct a giant `BulkOperations` without memory bounds.

### 12.1. Splitting into Small Chunks

Example of a method that processes already-chunked input batches:

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class ProductBatchWriter {
    private final MongoTemplate mongo;

    public ProductBatchWriter(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void insertChunk(List<CatalogProduct> chunk) {
        if (chunk == null || chunk.isEmpty()) {
            return;
        }
        if (chunk.size() > 500) {
            throw new IllegalArgumentException(
                    "Batch convention allows at most 500 elements");
        }

        mongo.insert(chunk, CatalogProduct.class);
    }
}
~~~

The number **500 is an application-level limit example**, not a mandatory MongoDB maximum for all batches. Drivers/servers impose limits on operation counts and message sizes, and a single BSON document cannot exceed **16 MiB**. Even when a submission limit is exceeded, the driver may split requests; the result does not turn into a transaction.

In real import systems, the reader should stream/partition data from the source into chunks rather than loading the entire file into RAM. Chunk size should be tuned based on document size, network latency, database quotas, and error-handling cost.

### 12.2. Checkpointing and Reconciliation

An import pipeline might consist of:

~~~mermaid
flowchart LR
    R["Read source"] --> V["Validate & normalize"]
    V --> P["Bounded batch splitting"]
    P --> W["Insert / SaveAll / BulkOps"]
    W --> C{"Outcome"}
    C -->|"PASS"| K["Write checkpoint"]
    C -->|"Partial/unknown"| E["Reconcile by ID/revision"]
    E --> T["Safely retry eligible items"]
    T --> K
~~~

A checkpoint should only be marked once there is sufficient evidence confirming the outcome of the corresponding set, or when ambiguous items can be verified. Do not merely record the source offset and assume every item in the batch succeeded; on server errors or timeouts, you may need to re-query by ID/event.

For imports from external systems:

1. Use stable `sourceSystem` and `externalId` values, optionally adding a tenant namespace.
2. Normalize and validate IDs and business keys before writing.
3. Distinguish **create** events from **update** events.
4. If source revisions exist, check for out-of-order delivery and apply only newer events.
5. For sensitive data, redact logs and protect traces containing import payloads.
6. Measure duplicate rates, transient errors, validation errors, and actual processing throughput.

## 13. Performance: Not Just Counting API Calls

To know which API fits best, measure the **actual write path**:

| Component | What to Observe |
|---|---|
| Round-trip count | Does the repository call save per entity or batch inserts? |
| Payload size | Full document or partial update? |
| Indexes | How many indexes must each insert/update maintain? Does any unique index create a hotspot? |
| Server resources | CPU, I/O, lock contention, cache, and write amplification |
| Latency | p50/p95/p99 by batch size |
| Error impact | Number of partially succeeded documents; retry/reconciliation cost |
| Version/callbacks | Are callbacks or per-entity stale-write checks involved? |
| Ordering | Are there dependencies between operations or conflicting writes to the same ID within one batch? |

For brand-new data, `MongoTemplate.insert` or the optimized insert path of `saveAll` can be faster than calling `save` item by item. For updating a few fields on existing documents, `BulkOperations.updateOne` can significantly reduce payload size and round trips. However, this is **not a universal law**: for small documents, small item counts, or logic requiring callbacks/optimistic locking, overall performance can differ.

### Indexes Also Affect Write Performance

A unique index on (`tenantId`, `sku`) protects invariants but increases the cost of every insert. Secondary indexes such as `status` and `stock_qty` also have to be updated when those fields change. Do not add indexes solely to speed up reads without measuring their impact on the bulk write pipeline.

If a batch performs many updates on a **hot document**, performance can be bottlenecked by contention on that document. Batch splitting does not eliminate contention; partition the data or redesign the write pattern appropriately.

## 14. Testing Against Real MongoDB

Mocking a repository or `MongoTemplate` only proves your code invokes the API—it **does not** verify duplicate keys, BSON types, partial success, or event/version behavior. Write integration tests against a dedicated test MongoDB instance, such as Testcontainers. In Spring Boot 3.x, `@DataMongoTest` sets up the MongoDB test slice context but **does not automatically start a MongoDB server**.

### 14.1. Testing Multi-Document Insert and saveAll

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DataAccessException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

@DataMongoTest
class ProductBatchWriteTest {
    @Autowired MongoTemplate mongo;
    @Autowired CatalogProductRepository repository;

    private CatalogProduct product(
            String id, String sku, long stock) {
        return new CatalogProduct(
                id, "tenant-a", sku, sku, stock, "ACTIVE");
    }

    @BeforeEach
    void prepare() {
        // Run only on an isolated test database.
        mongo.dropCollection(CatalogProduct.class);
        mongo.indexOps(CatalogProduct.class).ensureIndex(
                new Index()
                        .on("tenantId", Sort.Direction.ASC)
                        .on("sku", Sort.Direction.ASC)
                        .unique());
    }

    @Test
    void batchInsertIsCreateOnly() {
        mongo.insert(List.of(
                product("p-1", "SKU-1", 5),
                product("p-2", "SKU-2", 7)), CatalogProduct.class);

        assertThat(repository.count()).isEqualTo(2);

        // Duplicate ID; insert must not replace an existing document.
        assertThatThrownBy(() -> mongo.insert(
                List.of(product("p-1", "SKU-3", 99)),
                CatalogProduct.class))
                .isInstanceOf(DataAccessException.class);

        assertThat(repository.findById("p-1").orElseThrow().getStock())
                .isEqualTo(5);
    }

    @Test
    void saveAllUpdatesAnExistingVersionedEntity() {
        mongo.insert(product("p-1", "SKU-1", 5));

        CatalogProduct current =
                repository.findById("p-1").orElseThrow();
        current.setStock(9);
        repository.saveAll(List.of(current));

        CatalogProduct after =
                repository.findById("p-1").orElseThrow();
        assertThat(after.getStock()).isEqualTo(9);
        assertThat(after.getVersion()).isNotNull();
    }
}
~~~

The test uses `@Version` and an entity loaded from the database so that `saveAll` saves an **existing record**, avoiding constructing an object with an existing ID but a null version and mistakenly assuming the framework will treat it as an update.

**Never run `dropCollection` or `deleteAll` on a shared database.** For concurrent test runs, use a separate database or collection per test suite; these setup steps are only safe in an isolated environment.

### 14.2. Testing Bulk Update with Version and Stock Conditions

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.bulk.BulkWriteResult;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(StockBulkService.class)
class StockBulkServiceTest {
    @Autowired MongoTemplate mongo;
    @Autowired StockBulkService stockBulk;

    @Test
    void deductsOnlyWhenVersionAndStockMatch() {
        mongo.insert(new CatalogProduct(
                "stock-1", "tenant-a", "STOCK-1",
                "Water Bottle", 5, "ACTIVE"));

        CatalogProduct before =
                mongo.findById("stock-1", CatalogProduct.class);
        assertThat(before).isNotNull();
        assertThat(before.getVersion()).isNotNull();

        BulkWriteResult result = stockBulk.deduct(List.of(
                new StockDeduction(
                        "stock-1", "tenant-a", 3, before.getVersion()),
                new StockDeduction(
                        "stock-1", "tenant-a", 4, before.getVersion())));

        // Both commands have the same expected version; only one command matches.
        assertThat(result.getMatchedCount()).isEqualTo(1);

        CatalogProduct after =
                mongo.findById("stock-1", CatalogProduct.class);
        assertThat(after).isNotNull();
        assertThat(after.getStock()).isBetween(1L, 2L);
        assertThat(after.getVersion())
                .isEqualTo(before.getVersion() + 1);
    }
}
~~~

**Test explanation:** Because the bulk is `UNORDERED`, either command can win, so the final stock may be **2** if 3 was deducted or **1** if 4 was deducted. The record cannot be deducted twice against the same version when the filter and version update are applied properly. The test intentionally asserts the **invariant** without enforcing execution order.

In a real project, combine this test with tests simulating two concurrent requests from separate processes, because a single-threaded UNORDERED bulk covers only part of concurrency behavior.

### 14.3. Additional Failure Cases to Cover

| Scenario | What to Verify |
|---|---|
| Insert 3 documents, 2nd has duplicate ID | Which ones were written, which were not, under ordered/unordered |
| Insert duplicate business key with different ID | Compound unique index enforces protection accurately |
| saveAll with mixed new and existing entities | Command count, version handling, and performance |
| Bulk update with wrong expected version | `matchedCount` does not increase, data remains unchanged |
| Bulk update with insufficient stock | Does not make stock negative |
| Bulk upsert same business key from two workers | No duplicates; race errors handled |
| Bulk error/timeout after partial write | Reconciliation exists, safe per-item retry |
| Custom callbacks or auditing | Verify which APIs actually invoke callbacks |
| Multiple documents across multiple collections | Do not confuse grouped inserts with a transaction |
| Large documents and large batches | Chunking, memory usage, and latency checks |

### 14.4. Observing Actual Commands

The MongoDB Java Driver provides `CommandListener` to capture `CommandStartedEvent` in test environments. Inspect the commands:

- `insert` for lists of new documents;
- `update` with update models, `multi`, `upsert`;
- `delete` with corresponding conditions.

Do not deduce round-trip counts solely from calling a single Java method: the driver may split batches and the framework may execute different calls depending on `isNew`. When enabling command capture, filter by collection and mask sensitive data; never log raw business payloads in uncontrolled production environments.

## 15. Common Design Pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Assuming `saveAll` always equals insertMany | May update or save entities one by one | Check `isNew`, version, and actual commands |
| Assuming `saveAll` is always a single round trip | Large loads may be unexpectedly slow | Measure driver commands, chunk, choose bulk if appropriate |
| Calling `insert` for records needing updates | Duplicate key on re-imports | Separate create-only from update/upsert |
| Calling `saveAll` with entities having only ID + one field | Unloaded data can be lost | Update specific fields; do not save partial entities |
| Believing `ORDERED` means transaction | Writes before the error are not rolled back | Design a transaction if all-or-nothing is needed |
| Believing `UNORDERED` always runs in source order | Dependent updates yield wrong results | Use only for independent operations |
| Assuming bulk handles `@Version` optimistic locking automatically | Stale updates may slip through | Put version in filter and increment explicitly |
| Reading `BulkWriteResult` as per-row results | Cannot tell which command failed to match | Attach IDs, reconcile, and report per-item results |
| Retrying the entire `$inc` batch after timeout | May increment/decrement twice | Idempotency key, event revision, reconciliation |
| Missing unique business key | Two concurrent upserts can create duplicates | Create unique index in the proper namespace |
| Upsert without consistent `_id` type | BSON ObjectId/String mismatch, mapping errors | Design ID/Query/`setOnInsert` consistently |
| Unbounded batch size and RAM | OOM, oversized payloads, hard retries | Chunk and checkpoint |
| Confusing zero matched with write error | False business success reporting | Inspect matched/modified counts and reconcile |
| Forgetting callbacks/auditing when switching to bulk | Missing metadata and side effects | Test or manage explicitly |
| Testing only with mocks | Misses unique indexes/partial success | Integration test against real MongoDB |

## 16. Practice Exercises

**Exercise 1 — Choosing the right API.** You have three workflows: seeding 500 new products, saving 20 existing entities modified in the domain model, and importing 2,000 price updates by SKU. Choose `insert`, `saveAll`, or `BulkOperations` for each workflow and explain the trade-offs.

**Exercise 2 — Multi-document insert.** Insert three entities with distinct IDs. Repeat one ID and record the error. Verify whether the existing document was overwritten. Try both `insertAll` and `insert(collection, class)` on a test database.

**Exercise 3 — saveAll and isNew.** Create an entity with an application-assigned ID and `@Version Long`. Call `saveAll` while version is null, then read the entity back, change its name, and call `saveAll` again. Observe the BSON/commands and explain why “having an ID” does not always mean “existing entity”.

**Exercise 4 — ORDERED/UNORDERED.** Create a bulk with four inserts where the second collides on a unique key. Run each mode separately on two test databases and compare which documents succeed. Do not assume rollback for completed writes.

**Exercise 5 — Stock CAS.** Use `StockBulkService` with two commands having the same version and initial stock of 5. Verify that at most one operation matches; test insufficient stock and wrong tenant cases.

**Exercise 6 — Upsert from ERP.** Use `tenantId + sku` as the business key. Design an update touching only ERP-owned fields, using `setOnInsert` for creation fields, a unique index against duplicates, and a strategy for stale event revisions.

**Exercise 7 — Partial success and retry.** Simulate a batch of three operations: one already written, one hitting a duplicate, and one in an unknown state due to timeout. Design an item ID tracking table, checkpoints, reconciliation, and a retry method that never increments stock twice.

**Exercise 8 — Callbacks and versioning.** Create an entity with `@Version` and auditing timestamps. Compare insert, repository saveAll, and bulk update; write integration tests to verify whether version/timestamps actually change on each path.

**Exercise 9 — Benchmark.** Generate 50,000 test products (isolated data) and compare per-item `save`, `saveAll`, chunked `mongo.insert` of 500, and chunked `bulkOps` updateOne. Measure round trips, p95, throughput, memory, and exception counts; draw conclusions based on the workload rather than API names alone.

## 17. Key Takeaways

In **Spring Data MongoDB**, **multi-document insert** expresses **create-only** semantics and relies on unique indexes to reject duplicates. **`MongoRepository.saveAll`** expresses **saving an entity collection**, where new/existing detection, `@Version`, and implementation details determine whether it issues batched inserts or individual saves. **`MongoTemplate.bulkOps`** expresses **a plan of explicit write operations** such as insert/update/upsert/delete, with a choice of `ORDERED` or `UNORDERED`.

None of these options automatically turns thousands of writes into **an atomic transaction**. With bulk writes, inspect `BulkWriteResult` and exceptions, acknowledge **partial success**, define a retry/idempotency policy, and verify version/callback behavior instead of inferring it from entity annotations. For high-volume imports, **split into chunks, use stable unique keys, validate input, record checkpoints, and reconcile items with unknown outcomes**.

Finally, choose your API by **business semantics first, performance second**: use insert for create-only, saveAll for entity saves when appropriate, and consider bulk operations for conditional updates/upserts at scale. Only integration tests against real MongoDB and workload measurements can verify the true behavior of your write path.
