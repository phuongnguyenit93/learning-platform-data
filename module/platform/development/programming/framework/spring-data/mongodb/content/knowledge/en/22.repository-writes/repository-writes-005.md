# Return Types and Modified Document Counts

## 1. The critical question after a write operation

In the **Repository Writes** chapter of **Spring Data MongoDB**, a repository method can return an **entity**, a **list of entities**, a **boolean**, an **integer**, or **no result** (`void`). A common misconception is assuming the return type **tells the whole story** about how many documents actually changed in MongoDB.

For example, an e-commerce system needs to satisfy these requirements:

1. Save a product and return the product mapped by Spring Data.
2. Save a batch of products and know which entities were processed.
3. Transition products belonging to a tenant from `PENDING` to `ACTIVE`.
4. Delete products marked `DELETED` and report how many documents were deleted.
5. Distinguish **no matching documents**, **matching documents whose values did not change**, and **successful writes modifying documents**.

These requirements do not share the same answer. `save(...)` returns the saved entity; `saveAll(...)` returns an iterable of entities; `deleteById(...)` typically returns `void`; a **derived delete query** can return `long`; and an `@Update` method can return the number of updated documents. When you need detailed **matched/modified/upserted** counts, `MongoTemplate` with `UpdateResult` is usually the more direct choice.

### Lesson objectives

- Accurately read the return-type contracts of repository write operations.
- Distinguish **returned entity**, **matched document count**, **actually modified document count**, and **deleted document count**.
- Use derived deletes, `@Update`, `MongoRepository.save/saveAll`, and `MongoTemplate` for their intended purposes.
- Design APIs that report write outcomes clearly without inferring success from `void` or an inappropriate count.
- Understand the impact of versioning, concurrent writes, no-op updates, upserts, tenants, and idempotency.
- Test results against real MongoDB to catch discrepancies caused by mapping and execution paths.

> Context: Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x. Repository APIs and error behaviors can differ across versions; when you need an exact count guarantee, test the write path and inspect MongoDB commands/results on your target deployment version.

## 2. Overview table: return type does not equal count type

| API/method | Common return type | Primary meaning | Returns modified document count? |
|---|---|---|---|
| `repository.save(entity)` | `S extends T` | Entity after save operation | **No** |
| `repository.saveAll(entities)` | `Iterable<S>` or more specific type | Entities after saving | **Not directly** |
| `repository.deleteById(id)` | `void` | Request deletion by ID | **No** |
| `repository.delete(entity)` | `void` | Request deletion of entity | **No** |
| `repository.deleteAll(...)` | `void` | Request deletion of multiple entities | **No** |
| Derived `long deleteByStatus(status)` | `long` | Number of documents deleted by query | **Yes, per delete semantics** |
| Derived `List<T> removeByStatus(status)` | `List<T>` | Entities selected for deletion | **Returns entities, not a count** |
| Repository method with `@Update` | `void` or `long/Long` | Executes query-based update | **Can return update count** |
| `mongo.updateFirst/updateMulti` | `UpdateResult` | MongoDB update result | **Provides both matched and modified** |
| `mongo.remove(query, Type.class)` | `DeleteResult` | Query-based deletion result | **Provides `deletedCount`** |
| `mongo.findAndModify(...)` | Entity or `null` | Atomically finds and modifies one document | **Returns document, not count** |

In the table, "updated document count" for repository `@Update` must be understood according to the **API/version contract**, rather than automatically assuming it equals the filter-matched record count. When business logic needs both `matchedCount` and `modifiedCount`, obtain MongoDB-level results via `MongoTemplate`.

**First key distinction:** an operation returning **one entity** does not prove only one document was involved across the entire request; and an operation returning `void` does not mean "0 documents were modified".

## 3. Defining four metrics and two result types

A MongoDB update command can produce the following metrics:

| Concept | Typical API name | How to interpret |
|---|---|---|
**Matched** | `UpdateResult.getMatchedCount()` | How many documents matched the update filter |
**Modified** | `UpdateResult.getModifiedCount()` | How many documents actually changed due to the update |
**Upserted** | `UpdateResult.getUpsertedId()` | Newly created ID on upsert, if any |
**Deleted** | `DeleteResult.getDeletedCount()` | How many documents were actually deleted |
**Saved entity** | Result of `save(...)` | Java object returned after saving, not a count |
**Saved entities** | Result of `saveAll(...)` | Iterable of Java objects after saving, no command-level count guarantee |

Suppose three documents have `status = ACTIVE`. Calling:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { $set: { status: "ACTIVE" } }
);
~~~

Assuming no other field changes, you may get:

~~~text
matchedCount  = 3
modifiedCount = 0
~~~

MongoDB **found three documents**, but assigning the exact same value meant **zero documents changed**. Never treat `modifiedCount = 0` as synonymous with "no document exists" or "query failed".

Another example:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "ACTIVE" } }
);
~~~

If two documents were `PENDING` and updated successfully, `matchedCount` and `modifiedCount` can both equal 2. Still, those metrics only reflect the **executed command**, not whether the API sent emails, recorded audit events, or completed the whole business workflow.

**Document count** differs from **number of operations sent**. One `updateMulti` is one command that can modify many documents; a bulk plan with 10 write models does not guarantee 10 modified documents.

## 4. Sample entity and repository

Examples use the `catalog_products` collection. Each product belongs to a single tenant; name and stock quantity have BSON field names differing from Java properties to illustrate Spring Data mapping.

**CatalogProduct.java**

~~~java
package com.example.catalog;

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

    protected CatalogProduct() {
        // For Spring Data materialization.
    }

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

    public void setName(String name) { this.name = name; }
    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

`@MongoId(FieldType.STRING)` fixes `_id`'s BSON type as String. `@Field("stock_qty")` renames `stock` to `stock_qty`, and `name` to `display_name`. Typed queries using `CatalogProduct.class` can use Java property names; raw MongoDB shell or raw driver calls must use BSON names.

A document:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Water Bottle 500 ml",
  "stock_qty": 12,
  "status": "PENDING"
}
~~~

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    // Derived delete: returns deleted document count.
    long deleteByTenantIdAndStatus(String tenantId, String status);

    // Derived delete: returns entities selected for deletion.
    List<CatalogProduct> removeByTenantIdAndStatus(
            String tenantId, String status);

    // Repository update: query selects documents, update modifies them.
    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    @Update("{ '$set': { 'status': ?2 } }")
    long changeStatus(
            String tenantId, String previousStatus, String nextStatus);
}
~~~

In this example, `@Update` imports `org.springframework.data.mongodb.repository.Update`, **not** the `org.springframework.data.mongodb.core.query.Update` class used with `MongoTemplate`. Both share the same simple name yet serve different purposes; check imports carefully.

`changeStatus` uses `@Query` to specify the filter, because `changeStatus` is not a derived query method name like `findBy...`. Placeholders `?0`, `?1`, `?2` bind by parameter order.

## 5. save: returns the entity, not the modified document count

`MongoRepository.save(S entity)` has the return signature:

~~~java
<S extends T> S save(S entity);
~~~

When creating a new document:

~~~java
CatalogProduct created = products.save(new CatalogProduct(
        "p-101", "tenant-a", "BOTTLE-500",
        "Water Bottle 500 ml", 12, "PENDING"));

String id = created.getId();
~~~

Here `products` is the `CatalogProductRepository` bean. The result `created` is the **post-save entity**, not a value `1` indicating one inserted document.

### 5.1. Why is returning the entity useful?

- The ID may be generated or populated during saving depending on key type and mapping.
- Certain metadata may be set by the framework while saving, such as version or auditing when configured.
- The service can build a response DTO directly from the returned object.
- The contract is cleaner than calling `save` and discarding the result when the app needs the generated ID.

However, **the returned entity is not an immutable snapshot** of MongoDB under concurrency. Another request can update the document right after `save` completes. Do not use the returned object to assume state will stay unchanged.

### 5.2. Save can insert or overwrite an existing document

~~~java
CatalogProduct existing = products.findById("p-101")
        .orElseThrow();
existing.setName("Insulated Bottle 500 ml");

CatalogProduct saved = products.save(existing);
~~~

The result is still `CatalogProduct`, not a modified document count. For an entity without `@Version` as in Section 4, saving stale state can **overwrite** another request's changes; `save` does not express "modify only the `name` field".

Never construct an object containing only ID and name and call `save` to update one field. If `save` performs a document replacement, other fields can be wiped out or reset to defaults. Use conditional update commands when the intent is modifying only part of a document.

### 5.3. What if you need to know whether a document changed?

`save` returns neither `matchedCount` nor `modifiedCount`. When business logic needs to distinguish:

- No matching ID exists;
- ID exists and the value is already the desired value;
- ID exists and the field actually changed;

switch to `MongoTemplate.updateFirst(...)` returning `UpdateResult`, or design a dedicated response based on verified write results. **Never check `save(...) != null` and treat it as "one document was modified".**

## 6. saveAll: returns an entity collection, not a modifiedCount report

`saveAll(Iterable<S> entities)` returns an `Iterable<S>` or a more specific collection type depending on interface/implementation. Example:

~~~java
List<CatalogProduct> input = List.of(
        new CatalogProduct("p-201", "tenant-a", "SKU-201",
                "Ceramic Mug", 20, "PENDING"),
        new CatalogProduct("p-202", "tenant-a", "SKU-202",
                "Notebook", 15, "PENDING"));

Iterable<CatalogProduct> result = products.saveAll(input);
~~~

This is the collection of entities returned after saving. **The size of the iterable is not `modifiedCount`**:

- The batch may contain both new and existing entities.
- Entities may be saved even when values did not change.
- `saveAll` has no contract returning a MongoDB total of matched/modified documents.
- An error mid-batch can leave earlier documents persisted before the exception occurred, unless wrapped in an appropriate transaction.
- Implementations may optimize when all entities are new or issue multiple individual saves when existing entities are present; do not assume every call always emits a single MongoDB bulk command.

If you need to update thousands of documents with varying conditions and collect aggregate write statistics, consider `BulkOperations` or split into conditional updates. Even then, **`BulkWriteResult` is not a per-ID result list**; build reconciliation when item-level feedback is required.

### 6.1. Do not infer count from input size

~~~java
int requested = input.size();
Iterable<CatalogProduct> returned = products.saveAll(input);

// requested is the number of submitted objects, NOT actually modified documents.
~~~

With 100 objects, you cannot claim 100 documents changed simply because `requested = 100` and the method returned normally. Furthermore, if multiple objects share the same ID, duplicate handling, versioning, and save order also affect the outcome.

## 7. deleteById/delete/deleteAll return void: deletedCount is unknown

Operations inherited from `CrudRepository`/`MongoRepository` such as:

~~~java
products.deleteById("p-101");
products.delete(existing);
products.deleteAll();
~~~

usually have a `void` return type. The caller receives no direct count of deleted documents:

- `deleteById("p-101")` does not return 1 or 0 to show whether the ID existed.
- `delete(existing)` does not return total deleted documents.
- `deleteAll()` does not return total documents removed from the collection.

You cannot write:

~~~java
// Invalid: deleteById returns void.
long deleted = products.deleteById("p-101");
~~~

A `deleteById` call completing without throwing an exception **does not mean** the document existed beforehand. Different deletion paths may also handle versioning and lifecycles differently; when using `@Version`, clearly distinguish deleting by **loaded entity** vs. deleting **only by ID**. In Spring Data MongoDB, deleting by ID can bypass optimistic locking checks that entity deletion enforces.

### 7.1. Do not add existsById just to measure deleted count

The following pattern is **unreliable under concurrency**:

~~~java
boolean existed = products.existsById("p-101");
products.deleteById("p-101");

// existed reflects an earlier read, NOT deletedCount.
~~~

Another request may delete the document between the two operations. If you need the count actually deleted by **the delete command itself**, use a count-returning derived delete or `MongoTemplate.remove(...)` returning `DeleteResult`. Never infer counts from a preceding read.

## 8. Derived delete queries: choosing count vs. deleted entities

Spring Data MongoDB can derive deletion operations from method names like `deleteBy...` or `removeBy...`. **The return type** determines how the application receives the outcome.

### 8.1. Returning the number of deleted documents

Repository:

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);
~~~

Service:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;

@Service
public class CatalogCleanupService {
    private final CatalogProductRepository products;

    public CatalogCleanupService(CatalogProductRepository products) {
        this.products = products;
    }

    public long purgeDeleted(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        return products.deleteByTenantIdAndStatus(tenantId, "DELETED");
    }
}
~~~

The return value expresses the **number of documents deleted by the query**, not the number of API calls or client-supplied entities. A result of `0` can simply mean no `DELETED` records matched at execution time.

### 8.2. Returning the entities selected for deletion

The repository can also declare:

~~~java
List<CatalogProduct> removeByTenantIdAndStatus(
        String tenantId, String status);
~~~

This form serves cases where **the data of entities chosen for deletion** is needed for downstream processing. However, returning entities may require reading/materializing documents prior to deletion rather than returning a cheap `deletedCount`.

Consequences:

- With tens of thousands of documents, holding all entities in a `List` consumes memory and adds round-trip cost.
- The gap between reading data to return and executing deletion can experience concurrent writes; **do not treat the returned entity list as an atomically consistent audit log in all cases**.
- If lossless history is required, design an audit/outbox table or proper transaction rather than assuming "returning deleted entities" is a durable receipt.
- If you only need the deletion count, choose `long` instead of fetching a list and calling `size()`.

**Syntax note:** `deleteBy` and `removeBy` play equivalent roles in query naming, while the return type determines whether the caller receives a count or entities. Verify the specification for your Spring Data version, especially when combining with projections or custom queries.

## 9. @Update on repositories: returns void or updated document count

Unlike default CRUD operations that only offer entities or void, Spring Data MongoDB supports **repository update methods** via the `@Update` annotation.

Already declared example:

~~~java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
long changeStatus(
        String tenantId, String previousStatus, String nextStatus);
~~~

If `tenant-a` has three `PENDING` products, calling:

~~~java
long updated =
        products.changeStatus("tenant-a", "PENDING", "ACTIVE");
~~~

returns the updated document count per the framework's `@Update` contract; in typical Spring Data MongoDB 4.x implementations, `long` reflects the **number of modified documents**, not a collection of new entities.

### 9.1. @Update can modify multiple documents

In MongoDB repositories, `@Update` describes an update applied to **all documents matching the query**, not implicitly limited to one document because a method name uses singular phrasing. Understand it under the API's **multi-update** semantics and filter carefully:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "ACTIVE" } }
);
~~~

If the filter only checks `status = "PENDING"` in a multi-tenant app, the command can modify **products across every tenant**. Tenant and permission conditions must live inside the write query itself, not only be checked afterward.

### 9.2. Why isn't @Update's long return sufficient in every case?

With a constant assignment, this can occur:

~~~text
Filter matches:     3 documents
Value to assign:    status = "ACTIVE"
Existing value:     "ACTIVE" on all 3 documents

matchedCount  = 3
modifiedCount = 0
~~~

Thus you need to know **which metric the API reports**. `@Update` reports the update count per its contract, but does not return `matchedCount` and `modifiedCount` side-by-side on one object like `UpdateResult`. When you must distinguish "matched but unchanged", use `MongoTemplate` as in Section 10.

### 9.3. Returning void is also valid when no count is needed

Example repository method:

~~~java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
void changeStatusWithoutCount(
        String tenantId, String previousStatus, String nextStatus);
~~~

This snippet belongs **inside the same repository interface**, not as a standalone Java method. Returning `void` fits when the caller does not care about affected counts, though it can mask business failures like "no record was in the expected state".

In flows requiring confirmation or state transitions, prefer returning the count or using `UpdateResult` to classify the outcome instead of calling a `void` method and reporting unconditional success.

### 9.4. @Update does not return the modified entity

Do not declare `CatalogProduct` or `List<CatalogProduct>` as the return type of an `@Update` method expecting the framework to perform the update and return post-images of all documents. Different needs call for different APIs:

- Need **updated document count**: `@Update` returning `long` or `MongoTemplate.update...`.
- Need **one entity atomically post-update**: `MongoTemplate.findAndModify(...)` with `FindAndModifyOptions.returnNew(true)`.
- Need **list of entities post-update**: design an additional read step, understanding data may change between update and read without proper isolation.
- Need **item-by-item update report**: record operation IDs or reconcile by key; a single aggregate count is insufficient.

## 10. MongoTemplate.UpdateResult: separating matchedCount and modifiedCount

When business logic needs a fuller answer from MongoDB, `MongoTemplate` takes a `Query` and `Update` and returns `UpdateResult`.

**CatalogUpdateService.java**

~~~java
package com.example.catalog;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class CatalogUpdateService {
    private final MongoTemplate mongo;

    public CatalogUpdateService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public UpdateResult activatePending(String tenantId) {
        Query filter = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PENDING"));

        Update update = new Update().set("status", "ACTIVE");
        return mongo.updateMulti(filter, update, CatalogProduct.class);
    }

    public UpdateResult renameProduct(
            String tenantId, String id, String name) {
        Query filter = Query.query(
                Criteria.where("id").is(id)
                        .and("tenantId").is(tenantId));
        return mongo.updateFirst(
                filter, new Update().set("name", name),
                CatalogProduct.class);
    }
}
~~~

`mongo.updateMulti(...)` can update many documents; `updateFirst(...)` updates at most one matching document. In `renameProduct`, Spring Data maps `Criteria.where("id")` to BSON `_id` and `Update.set("name", ...)` to `display_name` when using `CatalogProduct.class`.

Reading the result:

~~~java
UpdateResult result =
        catalogUpdateService.activatePending("tenant-a");

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

### 10.1. Interpreting each combination

| Matched | Modified | Possible meaning | Next action |
|---:|---:|---|---|
0 | 0 | No document matched the filter | Check ID/tenant/expected status if distinction is needed |
1 | 1 | One document matched and changed | Return success per contract |
1 | 0 | Document matched but needed no value change | Can return "no changes", not necessarily an error |
5 | 3 | Five documents matched, three actually changed | Understand the query/update and affected fields |

Not every combination arises in every use case. Filtering `status = PENDING` and setting `status = ACTIVE` typically modifies every matching document unless something else interferes. Conversely, filtering by tenant and setting an already-present status easily produces `matchedCount > modifiedCount`.

If the write concern is **unacknowledged**, detailed metrics may be unavailable or unreliable. Systems needing accurate counts must configure an appropriate write concern; never disable acknowledgements for throughput and still promise exact update counts.

### 10.2. Updating a field with its existing value

~~~java
Query allActive = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("ACTIVE"));

Update sameValue = new Update().set("status", "ACTIVE");

UpdateResult result = mongo.updateMulti(
        allActive, sameValue, CatalogProduct.class);
~~~

Assuming three tenant documents are already `ACTIVE` and the entity has no auxiliary write hook changing other fields, the expected result is **matched = 3, modified = 0**. This clearly illustrates why we should avoid lumping both concepts under the single word "updated".

### 10.3. Find-and-modify one document, returning the post-image

When the client needs the updated object rather than just a number:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query filter = Query.query(
        Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a"));

CatalogProduct after = mongo.findAndModify(
        filter,
        new Update().set("name", "New Name"),
        FindAndModifyOptions.options().returnNew(true),
        CatalogProduct.class);
~~~

`after` can be `null` when no document matches. Handle `null` and return an appropriate response. `findAndModify` is atomic for one document, yet **does not produce a collection-wide count**.

## 11. DeleteResult: deleted document count differs from modifiedCount

With explicit deletion in the template:

~~~java
import com.mongodb.client.result.DeleteResult;

Query deletedItems = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("DELETED"));

DeleteResult result = mongo.remove(
        deletedItems, CatalogProduct.class);

long deleted = result.getDeletedCount();
~~~

`deletedCount` is the number of documents actually removed by the command, **not** modified-field count. A soft-delete:

~~~java
UpdateResult softDeleted = mongo.updateMulti(
        Query.query(Criteria.where("tenantId").is("tenant-a")
                .and("status").ne("DELETED")),
        new Update().set("status", "DELETED"),
        CatalogProduct.class);
~~~

modifies a field inside documents; it is an **update**, not a physical delete, so it uses `matchedCount/modifiedCount` rather than `deletedCount`.

Deletion policies matter too: if other documents reference a product, deleting does not automatically perform foreign-key cascades. When auditing, soft-delete, TTL, or relationship reconciliation are required, never treat `deletedCount` as proof that all business constraints are satisfied.

## 12. Do not use repository.count() to measure updates

`repository.count()` returns the **number of existing documents** in the collection per repository semantics, not the number of documents changed by the latest command.

Example:

~~~java
long before = products.count();
products.changeStatus("tenant-a", "PENDING", "ACTIVE");
long after = products.count();
long difference = after - before;
~~~

Getting `difference = 0` is completely normal even when 100 documents changed `status`; total document count does not change when updating a field.

Even if counting by status:

~~~java
long pendingBefore = /* count query for status PENDING */;
// Execute update ...
long pendingAfter = /* count query again */;
~~~

the difference **may not equal the documents modified by this request** if concurrent requests inserted, deleted, or changed status. This is a *time-of-check/time-of-use* and read-visibility issue.

Measure results using the **write operation's return count** or **MongoDB write result**, never by subtracting two before/after count queries. For multi-step workflows, store operation IDs and proper business logs/audits when reconciliation is needed.

## 13. Concurrency: counts do not replace write preconditions

Suppose a stock decrement must satisfy:

\[
\text{stock}_{\text{before}} \ge \text{quantityToSell}.
\]

Do not write:

~~~java
CatalogProduct product = products.findById("p-101").orElseThrow();
if (product.getStock() >= 3) {
    product.setStock(product.getStock() - 3);
    products.save(product);
}
~~~

Two requests can both read `stock = 5`, both subtract 3, and both write back `stock = 2`; the system accepted two orders while deducting stock only once. **Returning an entity from `save` does not detect this bug** without locking/versioning.

### 13.1. Conditional update in MongoTemplate

~~~java
package com.example.catalog;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class StockWriteService {
    private final MongoTemplate mongo;

    public StockWriteService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean deduct(
            String tenantId, String id, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }

        Query filter = Query.query(
                Criteria.where("id").is(id)
                        .and("tenantId").is(tenantId)
                        .and("stock").gte(amount));

        UpdateResult result = mongo.updateFirst(
                filter,
                new Update().inc("stock", -amount),
                CatalogProduct.class);

        return result.getMatchedCount() == 1;
    }
}
~~~

MongoDB evaluates the **sufficient stock condition** and executes `$inc` on **the same document** in a single atomic operation. Two requests cannot both deduct 3 from stock 5 and both match on the same document. With a non-zero `inc`, a matching document will also be modified, yet the API should still align with the exact semantics it needs to report.

`matchedCount == 0` can mean ID does not exist, wrong tenant, or insufficient stock. If the client needs to distinguish the exact cause, perform a follow-up read **after** the write fails to explain it—never rely on a pre-read to guard the write itself.

### 13.2. Optimistic locking with @Version

With `@Version` on an entity, repository `save` can detect when the object changed since it was read:

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "versioned_products")
public class VersionedProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    @Version
    private Long version;

    protected VersionedProduct() {}

    public VersionedProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public Long getVersion() { return version; }
    public void setName(String name) { this.name = name; }
}
~~~

Illustrative service/test:

~~~java
VersionedProduct saved =
        mongo.insert(new VersionedProduct("v-101", "Initial"));

VersionedProduct a =
        mongo.findById("v-101", VersionedProduct.class);
VersionedProduct b =
        mongo.findById("v-101", VersionedProduct.class);

a.setName("Request A");
mongo.save(a);

b.setName("Request B");
// With optimistic locking and acknowledged writes, this save
// can throw OptimisticLockingFailureException due to stale version.
mongo.save(b);
~~~

You must use an acknowledged write concern and write paths that honor versioning. Custom update commands or raw driver calls can bypass version checks unless explicitly conditioned. Repository `@Update` does not automatically turn every update into compare-and-set against a client DTO version.

**Return type implication:** `save` still returns an entity on success or throws an exception on optimistic locking conflict; it **does not turn into a `boolean`** indicating whether the version was valid. The service layer must translate the exception into a conflict response or controlled retry.

## 14. Upserts and bulk writes: aggregate numbers can hide details

### 14.1. Upserts can create new documents instead of modifying

`MongoTemplate.upsert(query, update, Type.class)` tells MongoDB to update if a matching document exists, or create a new document otherwise.

~~~java
Query byBusinessKey = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("sku").is("BOTTLE-500"));

Update update = new Update()
        .set("name", "Water Bottle")
        .setOnInsert("status", "PENDING");

UpdateResult result = mongo.upsert(
        byBusinessKey, update, CatalogProduct.class);
~~~

If the update matches an existing document, `matchedCount` can be 1; if it **inserts a new document** via upsert, `getUpsertedId()` reports the generated ID per driver results. When an upsert inserts a new document, **do not fold `upserted = 1` into `modifiedCount`** and label it a "modified" document.

For models using `@MongoId(FieldType.STRING)`, define a clear ID policy: when upserting by (`tenantId`, `sku`) without supplying `_id`, MongoDB may generate a BSON ObjectId. That can clash with the entity's String ID expectation. In production, establish deterministic keys, unique indexes, and schema-compliant ID generation before deploying bulk upserts.

### 14.2. BulkWriteResult aggregates multiple commands

If the application uses `MongoTemplate.bulkOps(...)`, `execute()` returns `BulkWriteResult` on the success path. A batch might contain 2 inserts, 3 updates, and 1 delete. Aggregate metrics include:

~~~java
int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserted = result.getUpserts().size();
~~~

This snippet assumes an existing `result` variable of type `com.mongodb.bulk.BulkWriteResult` rather than full bulk construction code. These totals do not identify **which specific document ID** failed or failed to match. On partial failures, an exception may be thrown instead of returning a complete success result.

Never retry an entire `$inc` batch after a timeout without idempotency, as previously updated items may be incremented/decremented twice. If business logic needs per-item reporting, use event IDs, checkpoints, reconciliation, and conditional retries.

## 15. Presenting write results at the API layer

In REST APIs, avoid returning raw MongoDB numbers without defining their semantics. For instance, a response might publish:

~~~json
{
  "requestedStatus": "ACTIVE",
  "matchedDocuments": 12,
  "modifiedDocuments": 10
}
~~~

However, such a response is only truthful when the service **actually has both matched and modified** from `UpdateResult`; never fabricate `matchedDocuments` from a repository `@Update`'s `long` return value.

A clear DTO:

~~~java
package com.example.catalog;

public record WriteSummary(
        long matchedDocuments,
        long modifiedDocuments) {
}
~~~

Service building the response:

~~~java
public WriteSummary activate(String tenantId) {
    UpdateResult result = catalogUpdateService.activatePending(tenantId);
    return new WriteSummary(
            result.getMatchedCount(),
            result.getModifiedCount());
}
~~~

This snippet illustrates a service method using the `catalogUpdateService` bean of type `CatalogUpdateService` defined in Section 10. The DTO avoids exposing IDs or document details when the endpoint only needs statistics.

### 15.1. Distinguishing technical outcomes from business outcomes

| Information | Can it be concluded from a write result? |
|---|---|
A document matched the filter | Yes, from `matchedCount` when acknowledged |
A document's value changed | Yes, from `modifiedCount` when supported |
A new document was upserted | Yes, from `upsertedId` |
How many documents were deleted | Yes, from `deletedCount` |
Confirmation email was sent successfully | **No** |
Multi-collection transaction completed | **No**, from a single write result alone |
No other request can modify the document | **No** |
Clients immediately see new data on every replica | **No**, depends on read preference/consistency |

A backend should name API fields strictly according to their semantics. For example, `modifiedDocuments` should not be named `processedOrders` if an order must pass through additional steps outside MongoDB.

### 15.2. Returning 0 can still be a valid outcome

A repeated request to "transition all `PENDING` products to `ACTIVE`" may return `0` because no `PENDING` documents remain. That can be an **idempotent success** under the business contract rather than HTTP 404 or 409.

Conversely, a request to "confirm one specific order by ID and expected version" that matches zero documents may need to return **409 Conflict** or **404 Not Found** depending on diagnosability and security policy. There is no single default HTTP mapping for every zero count.

## 16. Performance, indexes, and actual query counts

The goal of `@Update` or derived deletes returning a count is usually to avoid **loading entire documents into Java** merely to learn how many records were affected. Still, update cost depends on filters and indexes.

Example:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);
~~~

This index helps locate a tenant's products by status. Yet if each update modifies `status` itself, MongoDB must also update the index entries. Create indexes only after evaluating read/write ratios and selectivity across the workload.

### 16.1. Observing actual commands

In integration tests, MongoDB Java Driver's `CommandListener` can capture `CommandStartedEvent` and the `update`/`delete` command payload:

~~~json
{
  "update": "catalog_products",
  "updates": [
    {
      "q": {
        "tenantId": "tenant-a",
        "status": "PENDING"
      },
      "u": { "$set": { "status": "ACTIVE" } },
      "multi": true
    }
  ]
}
~~~

This is an **illustrative BSON command**, omitting auxiliary driver fields; it is not a byte-for-byte guarantee. Repository queries may be optimized by implementations, and actual commands may be dispatched differently.

Also observe:

- Number of commands sent to the server and round trips.
- `matchedCount`, `modifiedCount`, `deletedCount`, plus exceptions on error paths.
- Query plans, documents examined, and indexes used.
- p95 latency, write concern, replication lag, and server load.
- For deletes returning entity lists, whether a pre-delete find step occurred and the payload size generated.

Never enable raw BSON logging in production if filters or updates contain emails, sensitive IDs, financial data, or unmasked PII.

### 16.2. A count does not turn updateMany into a transaction

A method updating 1,000 documents can return a modified count on success; it **does not guarantee** all documents updated atomically as one unit. MongoDB guarantees atomicity **per document**; across multiple documents, configure a proper transaction if all-or-nothing semantics are required.

Even with transactions, handle uncertain commit outcomes, conditional retries, and post-commit reads. A count returned from an update command never substitutes for confirming an entire cross-collection workflow.

## 17. Testing with real MongoDB

Mocking a repository only proves the service invoked the right method; it **does not verify** whether derived delete returns a real count, how many documents `@Update` affects, BSON mapping, or matched vs. modified differences. Test against a real MongoDB instance, e.g., using Testcontainers. In Spring Boot 3.x, `@DataMongoTest` loads the MongoDB test slice, but **does not start a MongoDB server on its own**.

### 17.1. Integration tests for saveAll, @Update, and derived delete

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

@DataMongoTest
class RepositoryWriteCountTest {
    @Autowired CatalogProductRepository products;
    @Autowired MongoTemplate mongo;

    private CatalogProduct item(String id, String tenant, String status) {
        return new CatalogProduct(
                id, tenant, id, "Product " + id, 10, status);
    }

    @BeforeEach
    void prepare() {
        // Run ONLY against an isolated test MongoDB.
        products.deleteAll();
        products.saveAll(List.of(
                item("p-1", "tenant-a", "PENDING"),
                item("p-2", "tenant-a", "PENDING"),
                item("p-3", "tenant-a", "ACTIVE"),
                item("p-4", "tenant-b", "PENDING")));
    }

    @Test
    void saveReturnsEntityAndSaveAllDoesNotReturnModifiedCount() {
        CatalogProduct created = products.save(
                item("p-5", "tenant-a", "PENDING"));
        assertThat(created.getId()).isEqualTo("p-5");

        Iterable<CatalogProduct> returned = products.saveAll(List.of(
                item("p-6", "tenant-a", "ACTIVE"),
                item("p-7", "tenant-a", "ACTIVE")));
        assertThat(returned).hasSize(2);
        // The 2 here is the number of returned entities,
        // not modifiedCount in an UpdateResult.
    }

    @Test
    void annotatedUpdateReportsAffectedDocuments() {
        long changed = products.changeStatus(
                "tenant-a", "PENDING", "ACTIVE");
        assertThat(changed).isEqualTo(2);

        long repeated = products.changeStatus(
                "tenant-a", "PENDING", "ACTIVE");
        assertThat(repeated).isZero();

        assertThat(products.findById("p-4").orElseThrow().getStatus())
                .isEqualTo("PENDING");
    }

    @Test
    void matchedAndModifiedCanDiffer() {
        Query allActive = Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is("ACTIVE"));
        UpdateResult result = mongo.updateMulti(
                allActive,
                new Update().set("status", "ACTIVE"),
                CatalogProduct.class);

        assertThat(result.getMatchedCount()).isEqualTo(1);
        assertThat(result.getModifiedCount()).isZero();
    }

    @Test
    void derivedDeleteReturnsCountOfDeletedDocuments() {
        long removed = products.deleteByTenantIdAndStatus(
                "tenant-a", "PENDING");

        assertThat(removed).isEqualTo(2);
        assertThat(products.findById("p-1")).isEmpty();
        assertThat(products.findById("p-2")).isEmpty();
        assertThat(products.findById("p-4")).isPresent();
    }
}
~~~

Key points of the test:

- Only the two `PENDING` documents belonging to `tenant-a` are updated; `tenant-b`'s `p-4` is untouched.
- Re-running the update with `PENDING` matches nothing, returning count 0.
- Setting `ACTIVE` again on a document already `ACTIVE` yields matched = 1 but modified = 0.
- Derived delete returns the deleted document count, whereas `saveAll` returns entities.

The `@Update` test here checks only the case where **values actually change**; that avoids confusion when testing modified vs. matched on no-op assignments.

### 17.2. Testing entity-returning deletes and concurrent data

Additional tests:

1. Use `removeByTenantIdAndStatus` on a small set; inspect returned entities and verify documents are actually gone.
2. Seed several thousand documents and compare memory/command counts for `List`-returning vs. `long`-returning derived deletes.
3. Have two requests concurrently delete by condition; do not assume both receive the same deleted count.
4. For `@Version` entities, test stale `save` and differences from ID-based deletion.
5. Have one request alter `status` while another updates by `previousStatus`; verify only documents still matching the condition get modified.
6. Test insert-path upserts and compare `getUpsertedId()` with `matchedCount/modifiedCount`.
7. Attach a `CommandListener` to inspect real repository update/delete commands, especially tenant filters and `multi`.
8. Test unacknowledged/timeouts only in an appropriately designed test environment; never use unsafe write settings in production for ad-hoc testing.

When running tests in parallel, **never let `deleteAll()` wipe a shared collection across tests**. Isolate databases, collections, or document IDs per test. These examples are intended for dedicated test environments.

## 18. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Treating `save` returning an entity as "1 document modified" | Misclassifies inserts/updates/no-ops | Read `save` semantics; use `UpdateResult` for counts |
Treating `saveAll` output size as `modifiedCount` | Reports wrong modified count | Separate entity results from write metrics |
Treating `deleteById` returning `void` as deleting 1 document | Unknown whether ID existed | Use derived delete count or `DeleteResult` |
Comparing `count()` before/after to infer modified count | Updates don't change total; concurrency skews delta | Use the write result directly |
Confusing `matchedCount` with `modifiedCount` | No-op updates misread as not found | Design responses exposing both metrics |
Omitting `tenantId` in `@Update` query | Modifies other tenants' data | Put trusted tenant in the filter |
Assuming `@Update` updates one document by default | Modifies all matching records | Understand multi-update and test affected counts |
Declaring entity return type on `@Update` | Incompatible contract | Use `long`/`void` or `findAndModify` |
Using `List`-returning derived delete just to call `.size()` | Loads many entities, wastes memory | Use `long` when only deleted count is needed |
Assuming `@Version` protects all custom updates | Lost updates or overwrites from other write paths | Filter on expected version and inspect results |
Failing to distinguish upsert inserts from existing updates | Inaccurate modification statistics | Check `upsertedId` separately |
Retrying entire counter-increment batch on timeout | Can apply increments twice | Use idempotency/event IDs/reconciliation |
Mapping `modifiedCount = 0` to 404 in all APIs | Document exists but value was unchanged | Define no-op/idempotent semantics |
Testing only with mocked repositories | Misses real BSON and affected counts | Write integration tests against real MongoDB |
Assuming count proves the entire workflow finished | Missing audit/email/transaction | Separate technical write result from business result |

## 19. Applied exercises

**Exercise 1 — Classifying return types.** For `save`, `saveAll`, `deleteById`, `deleteByTenantIdAndStatus`, and `changeStatus`, build a table showing the Java type, observable outcome, and what cannot be inferred from the return value.

**Exercise 2 — Matched and modified.** Seed 3 `ACTIVE` products for the same tenant. Call `MongoTemplate.updateMulti` setting `ACTIVE` again and explain why `matched = 3`, `modified = 0` when no auxiliary field updates.

**Exercise 3 — @Update and multi-update.** Create two `PENDING` products for `tenant-a` and one `PENDING` product for `tenant-b`. Call `changeStatus`, then verify the count, final statuses of all three, and the `multi` flag on the command.

**Exercise 4 — Derived delete.** Try two status-based delete methods: one returning `long`, one returning `List<CatalogProduct>`. Compare outputs, query counts, and memory as document count grows. Explain when a separate audit log is needed.

**Exercise 5 — Void is not zero.** Call `deleteById` with an existing ID and a nonexistent ID. Write a service returning deleted count using `MongoTemplate.remove` instead of assuming results from `void`.

**Exercise 6 — Concurrency.** With initial stock 5, two requests both try to deduct 3. Compare unversioned read-modify-save with `updateFirst` checking `stock >= 3`. Write a concurrent test proving only one request deducts stock.

**Exercise 7 — Optimistic locking.** Add a model with `@Version Long`. Have two threads read the same version, save sequentially, and observe the optimistic locking exception. Design how to translate it into an appropriate 409 response.

**Exercise 8 — Upserts and metrics.** Run `upsert` on a nonexistent business key, then run it again once it exists. Record `matchedCount`, `modifiedCount`, and `upsertedId`. Add a unique index to test concurrent creation.

**Exercise 9 — API contract.** Write a response DTO for bulk status updates containing `matchedDocuments`/`modifiedDocuments`. Specify responses when both are 0, when matched exceeds modified, and on write timeouts.

**Exercise 10 — Performance.** Seed tens of thousands of documents in an isolated test and compare entity-list derived delete, `long` derived delete, and `MongoTemplate.remove`. Measure command counts, memory, latency, and ensure no cross-tenant leakage.

## 20. Key takeaways

**Repository return types express an API contract, not automatically a modified document count.** `save` returns an entity, `saveAll` returns entities, and default CRUD deletes usually return `void`. **Derived deletes** can return `long` for deleted counts or return entities selected for deletion; **`@Update`** can return `long/Long` when the updated document count is needed per framework semantics.

When you need to distinguish **query-matched documents** from **actually changed documents**, use `MongoTemplate` with `UpdateResult.getMatchedCount()/getModifiedCount()`. For physical deletes, use `DeleteResult.getDeletedCount()`; for insert-path upserts, inspect `getUpsertedId()` separately. Never use before/after `count()` calls to measure updates.

Under concurrent writes, **conditional filters, unique indexes, optimistic locking, acknowledged write concern, and idempotency** determine correctness. Always define explicit responses when `modified = 0`, guard against cross-tenant edits, and verify BSON/metrics via integration tests on real MongoDB. A document count is only meaningful when readers know precisely whether it measures **matched, modified, inserted, upserted, or deleted**.
