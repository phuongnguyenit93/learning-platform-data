# insert, save, findById, findOne, and find

## 1. Goal: choosing the right MongoTemplate operation

In the **MongoTemplate** chapter of the **Spring Data MongoDB** module, the five methods `insert`, `save`, `findById`, `findOne`, and `find` form the foundational group of operations for writing and reading documents. They are commonly used when query requirements or write-behavior control go beyond the derived methods of `MongoRepository`.

Suppose a retail application manages the `catalog_products` collection. We need to create new products, update an existing product's name, look up an exact product by ID, find the newest active product, and retrieve a list of in-stock products. Using the wrong API can turn a "create-only" operation into an overwriting update, or make a "get the first product" query return nondeterministic results.

| API | Question addressed | Typical result | What to watch out for |
|---|---|---|---|
| `insert(entity)` | Create a **new document** | Entity after write | Duplicate `_id` or unique key is rejected |
| `save(entity)` | Persist a new entity or the new state of an existing entity | Entity after write | Can insert/update or replace; not create-only |
| `findById(id, Type.class)` | Find one document by `_id` | Entity or `null` | Filters only by ID; does not automatically add tenant/permission checks |
| `findOne(query, Type.class)` | Find at most one document matching criteria | Entity or `null` | If multiple records match, an explicit `sort` is needed |
| `find(query, Type.class)` | Find multiple documents matching criteria | `List<Entity>`, possibly empty | Must control filter, sort, limit, and result size |

**A guiding principle:** `MongoTemplate` maps between **Java properties** and **BSON fields** when an entity type is provided. This differs from working directly on the driver's `MongoCollection<org.bson.Document>`, where you must use exact BSON field names.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and the synchronous driver. For other major versions, check your project's APIs and configuration. The code examples illustrate usage; they were not executed during the writing of this lesson.

## 2. Preparing the entity and sample data

When a project has the `spring-boot-starter-data-mongodb` dependency and a valid MongoDB URI configured, Spring Boot typically provides a `MongoTemplate` bean. The application can inject this bean into services rather than manually creating `MongoClient` and converters everywhere.

Examples in this lesson live in the `com.example.catalog` package. We choose a mutable entity to demonstrate reading, mutating properties, and saving back; the optimistic locking section introduces a separate model.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("display_name")
    private String name;

    @Field("stock_qty")
    private int stock;

    private String status;
    private String tenantId;
    private Instant createdAt;

    protected CatalogProduct() {
        // Spring Data can materialize the entity from a document.
    }

    public CatalogProduct(
            String id, String name, int stock, String status,
            String tenantId, Instant createdAt) {
        this.id = id;
        this.name = name;
        this.stock = stock;
        this.status = status;
        this.tenantId = tenantId;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public int getStock() { return stock; }
    public String getStatus() { return status; }
    public String getTenantId() { return tenantId; }
    public Instant getCreatedAt() { return createdAt; }

    public void setName(String name) { this.name = name; }
    public void setStock(int stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

Key points:

- `@Document(collection = "catalog_products")` specifies the collection for the entity.
- `@MongoId(FieldType.STRING)` maps `id` to a BSON `_id` of type String. If `@Id String` is used, Spring Data may convert strings that look like valid ObjectIds into BSON ObjectIds; design key types consistently.
- `@Field("display_name")` renames property `name` in BSON; `@Field("stock_qty")` renames `stock`.
- `createdAt` is converted by Spring Data to a BSON Date according to configured converters. BSON Date has millisecond precision.
- The model **does not yet have `@Version`**, so a `save` of a stale read can overwrite state recently updated by another worker.

A saved document looks roughly like this (omitting `_class` metadata if stored by the framework):

~~~json
{
  "_id": "p-101",
  "display_name": "Insulated Water Bottle",
  "stock_qty": 12,
  "status": "ACTIVE",
  "tenantId": "tenant-a",
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

Distinguish **Java names** (`name`, `stock`, `id`) from **stored names** (`display_name`, `stock_qty`, `_id`). Subsequent sections use this exact difference to verify query mapping.

## 3. insert: creating a new document without overwriting old ones

`MongoTemplate.insert(entity)` expresses the intent to *create new*. For an entity with an application-supplied ID:

~~~java
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;

public CatalogProduct createProduct(MongoTemplate mongo) {
    CatalogProduct product = new CatalogProduct(
            "p-101", "Insulated Water Bottle", 12, "ACTIVE",
            "tenant-a", Instant.parse("2026-11-20T08:00:00Z"));

    return mongo.insert(product);
}
~~~

This is an illustrative method placed in a service class taking `MongoTemplate`; import `CatalogProduct` accordingly if the class is in another package.

### 3.1. What happens if `_id` already exists?

MongoDB creates a unique index on `_id` for every collection. If you call again:

~~~java
mongo.insert(new CatalogProduct(
        "p-101", "Another Name", 3, "ACTIVE",
        "tenant-a", Instant.parse("2026-11-20T09:00:00Z")));
~~~

while `p-101` already exists, the insert is rejected due to a duplicate key. When using Spring Data with standard exception translation, the application receives `DuplicateKeyException`. **It does not silently modify the name or stock of the existing document.**

Do not call `existsById` or `findById` before `insert` and rely on that as a uniqueness guarantee. Two requests can both observe "not found" and then both attempt to insert. It is the **unique index at write time** that prevents two documents with the same ID.

If a business key such as `sku` or email must be unique, add a corresponding unique index rather than relying solely on `_id`. Creating a unique index on a collection that already has duplicates must be preceded by checking and cleaning up the data.

### 3.2. Auto-generated IDs and ID types

Spring Data/the driver can automatically assign IDs when an entity does not supply one, especially for `ObjectId` or `String` under supported mappings. However, ID assignment behavior for mutable classes, immutable records, or custom types can vary; verify it on your exact version and entity type.

Throughout this lesson, **IDs are supplied explicitly** (`p-101`, `p-102`, ...) so we do not depend on key-generation mechanics. If your application chooses its own UUID/String keys, ensure the key-generation process cannot reuse IDs due to logic bugs.

### 3.3. Inserting a collection of objects

`MongoTemplate` also provides overloads to insert multiple entities. This suits batch imports, but do not confuse a bulk command with an **atomic transaction for the entire batch**. When a document triggers a duplicate-key error, earlier operations in the batch may already have been written; understand how the API and driver handle batching, errors, and retries.

For idempotent import flows, design deterministic keys, unique indexes, retry policies, and checkpoints instead of just calling `insertAll` assuming "either all succeed or all are rolled back".

## 4. save: persisting current state, either updating or creating

`MongoTemplate.save(entity)` is appropriate when the application needs to **persist an entity's state**. With the non-versioned model above, `save` typically handles both the case where the document does not exist yet and the case where it already exists by ID; when it already exists, it can **replace the document's contents based on the saved object**.

Example:

~~~java
CatalogProduct product = mongo.findById(
        "p-101", CatalogProduct.class);

if (product == null) {
    throw new IllegalArgumentException("Product p-101 not found");
}

product.setName("Stainless Vacuum Flask");
CatalogProduct saved = mongo.save(product);
~~~

Expected result: MongoDB stores the new name in the `display_name` field. You do not need to construct raw BSON manually because Spring Data knows the entity metadata.

### 4.1. Why is save not a "single-field update" command?

When calling `save`, the application hands the **entire entity state** to the converter to write. For an entity without `@Version`, it may execute using document replacement/upsert semantics by ID, rather than a targeted `$set` for just the modified field.

Consequences:

- If the entity was read earlier, stale state in the object can **overwrite** newer changes in MongoDB.
- Constructing a fresh entity with only `id` and `name` populated is not a safe partial update: remaining properties may be written as defaults/nulls or removed from the document.
- Fields not mapped in the Java object may be lost when the document is replaced, depending on the write path and converter.
- Callbacks/auditing/custom converters are applied by Spring Data per API and configuration; do not treat `save` as a single raw BSON command.

If your intent is to **only decrement stock** or **only rename while preserving all other fields**, consider `updateFirst`/`findAndModify` with `Update.set`/`inc` and appropriate guard conditions.

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("id").is("p-101"));
Update rename = new Update().set("name", "Stainless Vacuum Flask");

mongo.updateFirst(byId, rename, CatalogProduct.class);
~~~

With `CatalogProduct.class`, Spring Data maps `id` to `_id` and `name` to `display_name`. The update targets only the specified field. However, this update **does not automatically prevent** concurrent requests; if business logic requires a specific version or expected status, add those conditions to `Query`.

### 4.2. upsert is not unconditional create permission

For an unversioned entity with an application-supplied ID, `save` can create a document when absent and replace it when present. Therefore:

- Want **create-only**: prefer `insert`.
- Want to **persist validated full state**: `save` can be appropriate.
- Want **update-only if existing and conditions hold**: use `updateFirst` or `findAndModify` with an explicit query.
- Want **conditional upsert modifying specific fields**: consider `upsert` with `Update`, `setOnInsert`, and an appropriate unique index; test for race conditions.

Do not assume `save` knows whether an entity is "business-new" or "already existing" simply because you instantiated it with `new`. ID, version, and new-entity detection strategies can affect Spring Data's write path.

## 5. findById: looking up strictly by the `_id` key

`findById` is the clear choice when you already have the ID:

~~~java
CatalogProduct found = mongo.findById(
        "p-101", CatalogProduct.class);

if (found == null) {
    // No document found with that ID at the time of read.
}
~~~

Common signatures:

~~~java
<T> T findById(Object id, Class<T> entityClass);
<T> T findById(Object id, Class<T> entityClass, String collectionName);
~~~

These are **signature illustrations** in documentation, not standalone Java method definitions outside an interface.

`findById` searches by `_id`, converts the Java ID according to entity mapping, materializes the result, and returns the entity or `null` if no document matches. It **does not return `Optional<T>` like `MongoRepository.findById`**. You can wrap the result in `Optional.ofNullable(...)` at the service boundary if desired.

For an entity annotated with `@Document(collection = "catalog_products")`, `findById(id, CatalogProduct.class)` knows which collection to read. The third overload lets you specify a different collection name when genuinely needed; when doing so, ensure the target collection conforms to the entity schema.

### 5.1. ID alone does not enforce tenant authorization

Suppose `p-101` belongs to `tenant-a`. The call:

~~~java
mongo.findById("p-101", CatalogProduct.class);
~~~

filters only by ID. It **does not automatically add a `tenantId` filter**. For multi-tenant data in the same collection, enforce access control—for example, using `findOne` with both ID and tenant:

~~~java
Query withinTenant = Query.query(
        Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a"));

CatalogProduct ownProduct =
        mongo.findOne(withinTenant, CatalogProduct.class);
~~~

In real code, the tenant must come from a **trusted authentication context**, never blindly trusting an arbitrary tenant string sent by a client. If every document of an entity belongs to a tenant, apply this predicate consistently across `find`, `update`, `delete`, and aggregations.

### 5.2. Being able to read does not mean safe to write later

The two steps `findById -> mutate Java object -> save` do not create an automatic transaction and do not prevent another request from updating the document in between. To guard against lost updates, consider `@Version` or a conditional update command. Reading from a secondary can also observe stale data if read preference allows it.

## 6. findOne: finding a single result from a flexible Query

`findOne(Query, Class<T>)` uses a **`Query`** built from `Criteria`, rather than being restricted to `_id`:

~~~java
Query available = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("stock").gt(0));

CatalogProduct one =
        mongo.findOne(available, CatalogProduct.class);
~~~

Equivalent BSON filter:

~~~json
{
  "status": "ACTIVE",
  "stock_qty": { "$gt": 0 }
}
~~~

If multiple documents satisfy the filter, `findOne` returns only **one** document, or `null` if none match. **Without a sort, there is no guarantee it is the newest, cheapest, or lowest-ID product.**

### 6.1. Using sort to define "the first record"

Suppose you want the newest product:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query newestActive = Query.query(Criteria.where("status").is("ACTIVE"));
newestActive.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")));

CatalogProduct newest =
        mongo.findOne(newestActive, CatalogProduct.class);
~~~

MongoDB shell equivalent:

~~~javascript
db.catalog_products.find({ status: "ACTIVE" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(1);
~~~

`createdAt DESC` puts newer products first; `id DESC` serves as a unique tie-breaker when timestamps are equal. The name `id` is translated by Spring Data to `_id` when executing a typed `Query`.

### 6.2. How does findOne differ from findById?

| Situation | API choice |
|---|---|
| ID is known and no extra conditions exist | `findById` |
| Find one record that is ACTIVE and in stock | `findOne` with `Query` |
| Find an ID **belonging to the current tenant** | `findOne` combining `id` and `tenantId` |
| Find the most recent or lowest-priced record | `findOne` with `Sort` |
| Want multiple records or a page of results | `find` with filter/sort/limit |

Calling `findOne` does not prove the predicate is unique. If business rules dictate at most one document per email/SKU, create a properly scoped unique index. **A query returning a single item is not a data uniqueness constraint.**

## 7. find: retrieving multiple results and controlling size

`find(query, Type.class)` accepts the same `Query` type as `findOne` but returns a list:

~~~java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
                .and("stock").gte(5));
query.with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("id")));
query.limit(20);

List<CatalogProduct> products =
        mongo.find(query, CatalogProduct.class);
~~~

If no documents match, `find` normally returns an **empty list**, not `null` as `findOne`/`findById` do when nothing is found. Always distinguish:

- `findById`/`findOne`: single result and can be `null`.
- `find`: list; check `isEmpty()` or `size()`.
- `count` and `exists` are separate APIs: do not load an entire list merely to count or check existence.

### 7.1. Offset pagination with Query

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

Pageable page = PageRequest.of(
        1, 10,
        Sort.by(Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

Query paged = Query.query(Criteria.where("status").is("ACTIVE"));
paged.with(page);

List<CatalogProduct> secondPage =
        mongo.find(paged, CatalogProduct.class);
~~~

`PageRequest` uses **0-based** page numbers; this example fetches the second page of size 10. `query.with(page)` configures skip/limit/sort, but since the return type is `List`, it does not automatically produce total-count metadata or `hasNext()`.

If you want a `Slice` without a total count, you can fetch `size + 1` items and trim the extra element; for `Page`, compute the total count according to matching semantics. On deep pages, `skip` can still be very expensive even with an index.

### 7.2. Do not use unbounded find on large datasets

~~~java
// Avoid in APIs over large collections without bounds:
List<CatalogProduct> everything =
        mongo.find(new Query(), CatalogProduct.class);
~~~

`find(new Query(), ...)` has no filter and can load a huge number of documents into memory at once. For exports or batch processing, consider streaming/cursors with proper resource closing, bounded pages, or reactive access as needed. A reactive pipeline also requires proper filters, limits, and backpressure; switching API styles does not make an unbounded query safe.

### 7.3. Filtering on nested fields

If a model has property `supplier.countryCode` and `@Field("country_code")` on the nested value object, you can write:

~~~java
Query byCountry = Query.query(
        Criteria.where("supplier.countryCode").is("VN"));
List<SomeProductWithSupplier> items =
        mongo.find(byCountry, SomeProductWithSupplier.class);
~~~

This is an **illustration**: `SomeProductWithSupplier` must be a separately declared entity with a `supplier` property. Do not copy this snippet into the `CatalogProduct` example without adding a supplier model. With an appropriate entity type, Spring Data maps the property path to `supplier.country_code`. With raw BSON, you must write the physical name directly.

## 8. Checking Query mapping: Java property vs BSON name

The same condition expressed two ways:

**Via MongoTemplate with entity type:**

~~~java
Query query = Query.query(
        Criteria.where("name").is("Insulated Water Bottle")
                .and("stock").gt(0));

List<CatalogProduct> result =
        mongo.find(query, CatalogProduct.class);
~~~

**Via MongoDB shell with BSON fields:**

~~~javascript
db.catalog_products.find({
  display_name: "Insulated Water Bottle",
  stock_qty: { $gt: 0 }
});
~~~

Mapping applies based on the `CatalogProduct.class` entity type. When using `mongo.getCollection("catalog_products")` for driver access, or passing a raw `Document` outside Spring Data query mapping, you must use exact BSON field names.

### 8.1. Field projection and consequences of incomplete entities

If a view only needs name and status:

~~~java
Query lightweight = Query.query(
        Criteria.where("status").is("ACTIVE"));
lightweight.fields()
        .include("id")
        .include("name")
        .include("status");
lightweight.limit(20);

List<CatalogProduct> partial =
        mongo.find(lightweight, CatalogProduct.class);
~~~

The MongoDB command can return only the selected fields, with `id` mapped to `_id` and `name` to `display_name`. However, because `CatalogProduct` is still materialized, unloaded fields like `stock` (primitive `int`) may take Java default values (`0`) in the returned object.

**Never call `save` on a partially loaded entity as if it held complete state.** Doing so can overwrite and lose unloaded data. For read-only APIs, prefer appropriate DTO/record projections or DTO mapping, and verify which BSON fields were selected.

### 8.2. Is Query immutable or mutable?

`Query` is an object that accumulates `Criteria`, sort, skip, limit, and field projections. Example code often mutates the same instance:

~~~java
Query search = Query.query(Criteria.where("status").is("ACTIVE"));
search.with(Sort.by(Sort.Order.asc("name")));
search.limit(10);
~~~

Avoid reusing a mutable `Query` across requests or threads; create a new `Query` per use or encapsulate a builder. For dynamic filters, never concatenate raw JSON from user input; use `Criteria` and validation to control operator types and field names.

## 9. Sample service using all five operations correctly

The following example places all five methods into a simple service. Accepting an input ID on a public API is purely illustrative; in a real application, enforce tenant checks, authorization, input validation, and ID generation policies.

**CatalogService.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final MongoTemplate mongo;

    public CatalogService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public CatalogProduct create(
            String id, String name, int stock, String tenantId) {
        if (id == null || id.isBlank()
                || name == null || name.isBlank() || stock < 0
                || tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid product creation input");
        }
        return mongo.insert(new CatalogProduct(
                id, name, stock, "ACTIVE", tenantId, Instant.now()));
    }

    public CatalogProduct saveFullState(CatalogProduct product) {
        // Call only with a valid aggregate under write-conflict control.
        return mongo.save(product);
    }

    public CatalogProduct getById(String id) {
        return mongo.findById(id, CatalogProduct.class);
    }

    public CatalogProduct newestActive(String tenantId) {
        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("ACTIVE"));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        return mongo.findOne(query, CatalogProduct.class);
    }

    public List<CatalogProduct> availableProducts(
            String tenantId, int minimumStock, int limit) {
        if (minimumStock < 0 || limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid search criteria");
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(minimumStock));
        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));
        query.limit(limit);
        return mongo.find(query, CatalogProduct.class);
    }
}
~~~

Inside the service:

1. `create` uses **`insert`** to reject duplicate keys.
2. `saveFullState` illustrates **`save`**, though it is not yet a safe update API for multi-tenant/concurrent environments if accepting a full entity directly from a client.
3. `getById` uses **`findById`**, convenient for internal logic where permissions are already verified. Do not expose it directly as a multi-tenant read API without adding access control.
4. `newestActive` uses **`findOne`** with a tenant filter and deterministic sort.
5. `availableProducts` uses **`find`** to return a filtered, sorted, and limited list.

This example intentionally separates CRUD mechanics from full business endpoints. For production endpoints, separate request/response DTOs, enforce authorization, and avoid a `saveFullState` method that lets clients overwrite internal fields.

## 10. Concurrent writes: @Version, duplicate keys, and conditional updates

A problem often overlooked when learning `save` is **lost update**:

~~~text
Initially: p-101 has stock = 12.
Request A reads stock = 12.
Request B reads stock = 12.
B updates stock = 11 and saves.
A edits name on its stale entity and saves.
Result may revert stock back to 12 because A saved its full stale state.
~~~

Spring Data MongoDB provides optimistic locking via `@Version` for entities mapped through compatible write paths. Use a separate model to avoid complicating the initial `CatalogProduct` example:

**VersionedProduct.java**

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

Scenario:

~~~java
mongo.insert(new VersionedProduct("v-101", "Initial Name"));

VersionedProduct a = mongo.findById("v-101", VersionedProduct.class);
VersionedProduct b = mongo.findById("v-101", VersionedProduct.class);

a.setName("Name by A");
mongo.save(a);

b.setName("Name by B");
// On an optimistic-locking write path, this save is rejected
// because b's version is stale.
mongo.save(b);
~~~

When write concern is acknowledged and the participating write paths honor versioning, saving with a stale version throws `OptimisticLockingFailureException` instead of silently overwriting. The application must classify the conflict, re-read current state, re-evaluate business rules, and only then retry if appropriate.

**Note:** If another write path uses the raw driver or an update without a version predicate, optimistic locking in repository/`save` will not protect the entire system. Never assume a single annotation resolves all concurrency hazards. For a field like inventory stock, `Update.inc` with a sufficient-stock condition can be a better fit than read-modify-save.

### 10.1. Errors go beyond duplicate keys

| Situation | Possible error/result | Appropriate response |
|---|---|---|
| `insert` with existing `_id` | `DuplicateKeyException` | Handle as a creation conflict, do not retry blindly |
| `save` with stale version | `OptimisticLockingFailureException` | Re-read and resolve the business conflict |
| `findById` finds no record | `null` | Return not found per contract, do not dereference |
| `findOne` finds no record | `null` | Handle as no result |
| `find` finds no record | Empty list | Return empty list or appropriate response |
| Query with wrong property name | Potential mapping error or empty result | Verify entity metadata and BSON |
| MongoDB connection drop/timeout | Data-access exception depending on cause | Classify transient errors, bound retries, and track latency |

Do not blindly retry `insert` or `save` on every exception. On a timeout after write, the previous request may already have been applied by MongoDB; retrying without an idempotency key or guard condition can cause unintended side effects.

## 11. Indexes, round trips, and query performance

`findById` benefits from MongoDB's default unique index on `_id`. Still, calling `findById` thousands of times incurs round-trip overhead; if you need many IDs, design a bounded `$in` query, caching, or batching as appropriate.

For `findOne`/`find` in the example, a candidate index for filtering by tenant and status and sorting by creation time is:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: -1 },
  { name: "idx_tenant_status_created_id" }
);
~~~

To filter by stock or price range, the optimal index may differ. Do not create indexes on every property indiscriminately; select them based on real queries, selectivity, sort order, and index write overhead.

Example query analysis:

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE",
  stock_qty: { $gte: 5 }
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Inspect `winningPlan`, `totalKeysExamined`, `totalDocsExamined`, latency, and documents actually returned. A query filtering on `stock_qty` when the index only covers `tenantId`/`status`/`createdAt` may still inspect many documents; tune index choices based on data distribution and workload frequency.

### 11.1. Reading fewer fields with projection

If a listing page only needs name and status:

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));
query.fields().include("id").include("name").include("status");
query.limit(20);
List<CatalogProduct> cards = mongo.find(query, CatalogProduct.class);
~~~

Depending on mapping, the find command carries a field projection specifying `_id`, `display_name`, and `status`. **Loading fewer fields does not produce a full entity safe to save.** Use DTO projections or dedicated read methods for APIs.

### 11.2. MongoTemplate or MongoRepository?

| Need | Typically suitable choice |
|---|---|
| Simple CRUD by entity and ID | `MongoRepository` |
| Dynamic queries with many optional criteria | `MongoTemplate` + `Criteria` |
| Single document by ID | `findById` on repository or template |
| Create-only, reject duplicate IDs | `MongoTemplate.insert` or suitable insert API |
| Find newest document matching criteria | `MongoTemplate.findOne` with sort |
| Conditional atomic single-field update | `MongoTemplate.updateFirst` / `findAndModify` |
| Aggregation, grouping, and calculations | `MongoTemplate.aggregate` |

You do not need to migrate an entire project from repositories to templates. Both abstractions share Spring Data's mapping infrastructure and can be combined in services as needed.

## 12. Testing the five operations against real MongoDB

A unit test mocking `MongoTemplate` only checks that code calls the right method; **it does not prove** Spring Data writes the right BSON fields, enforces duplicate keys, or applies sorting. To verify integration behavior, use a dedicated test MongoDB instance, such as via Testcontainers. `@DataMongoTest` in Spring Boot 3.x only sets up the MongoDB test slice; it does not start a MongoDB server by itself.

**CatalogMongoTemplateTest.java**

~~~java
package com.example.catalog;

import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class CatalogMongoTemplateTest {
    @Autowired
    MongoTemplate mongo;

    private CatalogProduct product(
            String id, String name, int stock, String status, int hour) {
        return new CatalogProduct(
                id, name, stock, status, "tenant-a",
                Instant.parse("2026-11-20T00:00:00Z").plusSeconds(3600L * hour));
    }

    @BeforeEach
    void clear() {
        // Run only inside an isolated test database.
        mongo.remove(new Query(), CatalogProduct.class);
    }

    @Test
    void insertCreatesAndDuplicateIdIsRejected() {
        mongo.insert(product("p-101", "Water Bottle", 12, "ACTIVE", 8));

        assertThatThrownBy(() ->
                mongo.insert(product("p-101", "Duplicate ID", 99, "ACTIVE", 9)))
                .isInstanceOf(DuplicateKeyException.class);
    }

    @Test
    void saveChangesExistingDocument() {
        mongo.insert(product("p-101", "Water Bottle", 12, "ACTIVE", 8));
        CatalogProduct existing =
                mongo.findById("p-101", CatalogProduct.class);
        assertThat(existing).isNotNull();

        existing.setName("Vacuum Flask");
        mongo.save(existing);

        Document raw = mongo.getCollection("catalog_products")
                .find(eq("_id", "p-101")).first();
        assertThat(raw).isNotNull();
        assertThat(raw.getString("display_name"))
                .isEqualTo("Vacuum Flask");
        assertThat(raw.getInteger("stock_qty")).isEqualTo(12);
        assertThat(raw.containsKey("name")).isFalse();
    }

    @Test
    void findByIdAndFindOneReturnNullWhenMissing() {
        assertThat(mongo.findById(
                "missing", CatalogProduct.class)).isNull();

        Query noMatches = Query.query(
                Criteria.where("status").is("MISSING"));
        assertThat(mongo.findOne(
                noMatches, CatalogProduct.class)).isNull();
    }

    @Test
    void findOneUsesSortAndFindReturnsList() {
        mongo.insert(product("p-101", "Older", 2, "ACTIVE", 8));
        mongo.insert(product("p-102", "Newer", 7, "ACTIVE", 9));
        mongo.insert(product("p-103", "Hidden", 5, "INACTIVE", 10));

        Query active = Query.query(
                Criteria.where("status").is("ACTIVE"));
        active.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.desc("id")));

        CatalogProduct newest =
                mongo.findOne(active, CatalogProduct.class);
        assertThat(newest).isNotNull();
        assertThat(newest.getId()).isEqualTo("p-102");

        List<CatalogProduct> found =
                mongo.find(active, CatalogProduct.class);
        assertThat(found).extracting(CatalogProduct::getId)
                .containsExactly("p-102", "p-101");
    }
}
~~~

These tests illustrate **expected behavior**. The test database must be available; if running tests in parallel, isolate collections so `remove(new Query(), ...)` does not wipe another test's data.

### 12.1. Testing lost updates

With `VersionedProduct`, an integration test can:

1. Insert a versioned document.
2. Read two instances `a` and `b` before any write.
3. Modify `a` and `save(a)` successfully.
4. Modify `b` and call `save(b)`; verify `OptimisticLockingFailureException` is thrown under the configured write path.
5. Re-read the document, verify the incremented version and that no overwrite occurred.

Prerequisites: MongoDB write concern is acknowledged and all writes go through paths supporting optimistic locking. If mixing raw driver calls or non-versioned updates, test those write paths as well.

### 12.2. Observing BSON commands

When you need to verify that `Criteria.where("name")` actually becomes `display_name`, you can attach a MongoDB Java Driver `CommandListener` via a test `MongoClientSettingsBuilderCustomizer` (Spring Boot 3.x) and inspect `CommandStartedEvent`.

An illustrative `find` command:

~~~json
{
  "find": "catalog_products",
  "filter": {
    "status": "ACTIVE",
    "stock_qty": { "$gte": 5 }
  },
  "sort": { "createdAt": -1, "_id": -1 },
  "limit": 20
}
~~~

This JSON is **not a byte-for-byte claim** for every driver version; field names and semantics are what matter. When capturing commands, do not log sensitive data in filters, inserts, or updates to production observability systems without proper protection policies.

## 13. Common pitfalls and diagnostics

| Symptom | Possible cause | Verification and fix |
|---|---|---|
| Second `insert` fails | Existing `_id` or unique business key | Check unique indexes and handle `DuplicateKeyException` as a conflict |
| `save` drops existing fields | Saved a partial entity or stale snapshot | Use field-level updates or manage `@Version`; avoid saving partial entities |
| `findById` always returns null | Wrong ID, wrong BSON `_id` type, or wrong collection | Inspect raw BSON, check `@MongoId`/`@Id` and collection |
| `findOne` returns an unexpected product | Multiple records match with no sort | Add a deterministic sort and matching index |
| `find` returns huge amounts of data | Query lacks filter/limit | Bound size, paginate, or stream with resource control |
| `name` filter fails in raw driver | BSON field is `display_name` | Use a typed `Query` or physical BSON field name |
| `Query` ignores tenant boundaries | Missing security filter in query | Attach tenant from auth context to find/update/delete |
| Saving after finding causes lost update | Two requests edited stale snapshots | Use optimistic locking or compare-and-set |
| Accurate results but slow query | Missing index, in-memory sort, or deep skip | Run `explain("executionStats")`, measure keys/docs examined |
| `@DataMongoTest` fails to connect | No MongoDB server available for tests | Provide a test database or suitable Testcontainers setup |

## 14. Practice exercises

**Exercise 1 — Insert or save?** Create document `p-101` with `insert`. Call `insert` again with the same ID and record the error. Next, read the existing entity, change its name, and call `save`; compare the BSON before and after, and explain why `save` should not be used as a create-only API.

**Exercise 2 — findById and findOne.** Create three products all with status `ACTIVE`. Use `findById` to fetch one exact ID, and use `findOne` to find the newest product by `createdAt DESC, id DESC`. Remove the sort and observe why you must not rely on the default "first record".

**Exercise 3 — find, Criteria, and mapping.** Place `@Field("stock_qty")` on the `stock` property. Query `status=ACTIVE` and `stock>=5` using `MongoTemplate`; inspect the raw BSON/filter to verify the BSON name `stock_qty` is used.

**Exercise 4 — Projection and partial entities.** Load only `id` and `name`, then inspect the `stock` value on the Java entity. Explain the risk of calling `save` on a partially loaded entity, then design a read-only DTO or `Update.set` to rename it safely.

**Exercise 5 — Lost update.** Have two requests read `p-101`, one decrementing `stock` and one changing `name`. Simulate saving two stale snapshots; add `@Version` or conditional update commands to protect changes.

**Exercise 6 — Multi-tenant.** Design APIs to read and update products strictly for the current tenant. Compare `findById(id)` against `findOne(query with id + tenantId)`; test that requests from another tenant cannot read the data.

**Exercise 7 — Indexes and performance.** Populate a sizable dataset and measure filtering by `tenantId + status`, sorting `createdAt DESC, _id DESC`, limit 20. Use `explain("executionStats")` to compare performance before and after adding a compound index; inspect `skip` cost on deep pages.

**Exercise 8 — Replayability.** A client sends a create-product command that times out after MongoDB has already accepted the insert. Design an idempotency key or lookup-by-ID check to distinguish "my previous request succeeded" from "the ID was taken by another request". Do not blindly retry every duplicate as a transient error.

## 15. Key takeaways

In **Spring Data MongoDB**, `MongoTemplate.insert` is the choice for **creating a new document and rejecting duplicate keys**; `save` persists entity state and may insert or overwrite an existing document according to mapping metadata. Never call `save` on a partially loaded entity or stale snapshot without an overwrite-control policy.

`findById` locates one document by `_id`, `findOne` selects one document via a flexible `Query`, and `find` returns a list of matching documents. With `findOne` or `find`, always specify **filter, sort, limit, and access control**; in particular, never depend on "the first document" without a sort.

Always verify **Java-property-to-BSON mapping**, `_id` types, indexes, round-trip counts, and write-concurrency scenarios. `MongoRepository` simplifies standard CRUD; `MongoTemplate` enables deliberate `Query`/`Update` construction. Correctness comes from **operation semantics and testing against real MongoDB**, not just method names.
