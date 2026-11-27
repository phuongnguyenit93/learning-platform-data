# Basic `find`, `insert`, `update`, `replace`, and `delete` Commands

> **Chapter:** MongoDB Foundations  
> **Scope:** MongoDB CRUD and how it relates to **Spring Data MongoDB** (`MongoTemplate`, repositories).  
> **Goal:** Know how to choose the right operation to read, insert, update individual fields, replace an entire document, and delete; write accurate filters, inspect returned results, and avoid accidentally modifying or deleting data.

## 1. What does CRUD in MongoDB work with?

MongoDB stores data as **BSON documents** inside **collections**. A document looks similar to a JSON object and can contain nested fields and arrays. Every document has a `_id` field that is unique within its collection; MongoDB auto-generates an `ObjectId` if `_id` is not supplied at insert time.

| Need | Command in `mongosh` | Meaning |
| --- | --- | --- |
| Read | `find()`, `findOne()` | Returns documents matching the filter |
| Insert | `insertOne()`, `insertMany()` | Creates one or more documents |
| Update fields | `updateOne()`, `updateMany()` | Modifies fields using operators such as `$set`, `$inc` |
| Replace document | `replaceOne()` | Replaces the contents of one document while preserving `_id` |
| Delete | `deleteOne()`, `deleteMany()` | Deletes documents matching the condition |

`find` is a read operation. The other four groups are write operations. MongoDB guarantees that a write operation on a **single document** is atomic, even when modifying multiple fields of that document; `updateMany()` or `deleteMany()` does not turn the entire set of documents into a single atomic transaction.

### 1.1. Creating a practice dataset

Open `mongosh` and select a **learning database**—do not run delete examples on real data:

~~~javascript
use spring_data_mongodb_lab

// Alias to make the following examples easier to read.
const products = db.products_crud_demo_006;

products.insertMany([
  {
    _id: "p001",
    sku: "SP-001",
    name: "Mechanical Keyboard",
    category: "accessory",
    priceVnd: 1200000,
    stock: 12,
    active: true,
    tags: ["office", "wired"],
    supplier: { city: "Ha Noi" }
  },
  {
    _id: "p002",
    sku: "SP-002",
    name: "Wireless Mouse",
    category: "accessory",
    priceVnd: 450000,
    stock: 0,
    active: true,
    tags: ["office", "wireless"],
    supplier: { city: "Da Nang" }
  },
  {
    _id: "p003",
    sku: "SP-003",
    name: "Laptop Stand",
    category: "desk",
    priceVnd: 550000,
    stock: 8,
    active: true,
    tags: ["office"],
    supplier: { city: "Ha Noi" }
  },
  {
    _id: "p004",
    sku: "SP-004",
    name: "USB-C Cable",
    category: "accessory",
    priceVnd: 150000,
    stock: 25,
    active: false,
    tags: ["cable"],
    supplier: { city: "Ho Chi Minh" }
  }
]);
~~~

The following examples assume the initial dataset contains exactly these four documents. Running `insertMany` again with the same `_id` values will produce a duplicate key error; use a fresh test collection if you need to start over.

## 2. Reading documents with `find`

### 2.1. Syntax and filters

~~~javascript
db.collection.find(filter, projection)
db.collection.findOne(filter, projection)
~~~

- `filter` is a document describing the criteria; `{}` means no filter.
- `projection` selects which fields to return.
- `find()` returns a **cursor**, allowing iteration over multiple documents; `findOne()` returns one document or `null` if not found.
- When multiple documents satisfy the condition, do not assume result ordering without calling `sort()`.

~~~javascript
// All products.
products.find({});

// One product with a specific _id.
products.findOne({ _id: "p001" });

// Conditions at the same level are combined with AND.
products.find({
  category: "accessory",
  active: true,
  priceVnd: { $lte: 500000 }
});
// On the original dataset: p002.

// OR condition.
products.find({
  $or: [{ stock: 0 }, { active: false }]
});
// On the original dataset: p002 and p004.
~~~

Common filter operators:

| Operator | Example | Interpretation |
| --- | --- | --- |
| `$eq`, `$ne` | `{ active: { $ne: false } }` | Equal / not equal; `$ne` can also match documents missing the field |
| `$gt`, `$gte` | `{ stock: { $gt: 0 } }` | Greater than / greater than or equal |
| `$lt`, `$lte` | `{ priceVnd: { $lte: 500000 } }` | Less than / less than or equal |
| `$in` | `{ category: { $in: ["desk", "accessory"] } }` | Belongs to a set of values |
| `$or`, `$and` | `{ $or: [{ stock: 0 }, { active: false }] }` | Combine conditions |
| `$exists` | `{ updatedAt: { $exists: true } }` | Whether the field exists |

Nested fields use **dot notation**; for arrays of scalar values, matching against a single element value is enough:

~~~javascript
// Documents with supplier.city = "Ha Noi": p001, p003.
products.find({ "supplier.city": "Ha Noi" });

// Documents whose tags array contains "office": p001, p002, p003.
products.find({ tags: "office" });

// Find SKUs in a given list.
products.find({ sku: { $in: ["SP-001", "SP-003"] } });
~~~

**Watch data types:** `"1200000"` (string) differs from `1200000` (number). `"p001"` also differs from an `ObjectId` formatted as a string. A filter with the wrong type usually returns nothing even when values look alike.

### 2.2. Projection, sorting, and pagination

~~~javascript
// Return only name, SKU, and price; exclude _id.
products.find(
  { active: true },
  { _id: 0, sku: 1, name: 1, priceVnd: 1 }
);

// In-stock items: ascending price, _id as tie-breaker.
products.find({ stock: { $gt: 0 } })
  .sort({ priceVnd: 1, _id: 1 })
  .skip(0)
  .limit(2);

// Count active products.
products.countDocuments({ active: true });
~~~

`1` in a projection means **include field**, `0` means **exclude field**. Normally you do not mix inclusion and exclusion in the same projection, with `_id: 0` being the common exception. In `sort()`, `1` is ascending and `-1` is descending. `skip()` skips the first N documents and `limit()` caps the count; deep pagination with `skip` can be expensive, so consider keyset pagination on an indexed key when performance matters.

A query returning few results is not guaranteed to be fast: MongoDB may still scan many documents. For frequently run filters, consider indexes and inspect the execution plan using `find(filter).explain("executionStats")`; that belongs to query optimization covered next.

## 3. Adding documents with `insert`

### 3.1. `insertOne()` and `insertMany()`

~~~javascript
// Create one document.
products.insertOne({
  _id: "p005",
  sku: "SP-005",
  name: "Headphone Stand",
  category: "desk",
  priceVnd: 290000,
  stock: 4,
  active: true,
  tags: ["office"],
  supplier: { city: "Ha Noi" }
});

// Create multiple documents in one call.
products.insertMany([
  {
    _id: "p006",
    sku: "SP-006",
    name: "Desk Mat",
    category: "desk",
    priceVnd: 200000,
    stock: 15,
    active: true
  },
  {
    _id: "p007",
    sku: "SP-007",
    name: "Cable Clip",
    category: "accessory",
    priceVnd: 50000,
    stock: 30,
    active: true
  }
]);
~~~

A successful result includes `acknowledged` and `insertedId` (single document) or `insertedIds` (multiple documents). If `_id` is not passed, MongoDB generates a default value.

MongoDB creates a **unique index** on `_id` by default. Inserting `_id: "p005"` again raises `E11000 duplicate key`. The `sku` field in this example is just a regular field; to enforce uniqueness on it, create a dedicated unique index, such as:

~~~javascript
products.createIndex({ sku: 1 }, { unique: true });
~~~

With `insertMany()`, the default `ordered: true` stops processing subsequent items on a write error. The `{ ordered: false }` option continues attempting the remaining documents, but it does **not** make the batch atomic. For production data, define a policy for handling partial success.

## 4. Modifying individual fields with `update`

### 4.1. Why use update operators?

`updateOne(filter, update, options)` modifies at most **one** matching document; `updateMany(filter, update, options)` modifies **all** matching documents. When using an update document, the `update` argument contains operators such as `$set` or `$inc`.

~~~javascript
// Ship 2 units of p001 if stock is still sufficient.
const updateResult = products.updateOne(
  { _id: "p001", stock: { $gte: 2 } },
  {
    $inc: { stock: -2 },
    $set: { updatedAt: new Date() }
  }
);

printjson(updateResult);
// If run once from initial data: p001 stock goes from 12 to 10.

// Mark all active accessories as on promotion.
products.updateMany(
  { category: "accessory", active: true },
  { $set: { promotion: true } }
);
// If run after the example above: p001 and p002 get promotion: true.
~~~

Putting `stock: { $gte: 2 }` in the same `updateOne()` filter alongside `$inc` checks and deducts inventory on **a single document** in one atomic operation. Reading stock into the application, subtracting in memory, and writing back risks lost updates under concurrent requests.

| Update operator | Effect | Example argument |
| --- | --- | --- |
| `$set` | Sets field value (creates field if absent) | `{ $set: { active: false } }` |
| `$unset` | Removes a field completely | `{ $unset: { promotion: "" } }` |
| `$inc` | Adds a positive/negative number to a numeric field | `{ $inc: { stock: 3 } }` |
| `$push` | Appends an element to an array, allowing duplicates | `{ $push: { tags: "new" } }` |
| `$addToSet` | Adds an element to an array only if no equal element exists | `{ $addToSet: { tags: "new" } }` |
| `$pull` | Removes array elements matching a condition | `{ $pull: { tags: "wired" } }` |
| `$setOnInsert` | Sets a field only when `upsert` creates a new document | `{ $setOnInsert: { createdAt: new Date() } }` |

Examples of modifying nested fields and arrays specifically:

~~~javascript
// Keep other fields of supplier, change only city.
products.updateOne(
  { _id: "p002" },
  {
    $set: { "supplier.city": "Hai Phong" },
    $addToSet: { tags: "featured" }
  }
);

// Remove a field that is no longer needed.
products.updateOne(
  { _id: "p002" },
  { $unset: { promotion: "" } }
);
~~~

`$set: { supplier: { city: "Hai Phong" } }` replaces the **entire** `supplier` subdocument; use `"supplier.city"` when you only want to change one child attribute.

### 4.2. Reading results and using `upsert`

An update result typically includes:

- `matchedCount`: number of documents matching the filter.
- `modifiedCount`: number of documents actually modified; can be `0` even when `matchedCount = 1` if the new value equals the existing value.
- `upsertedCount` and `upsertedId`: count/`_id` inserted when `upsert` is enabled.
- `acknowledged`: whether the server acknowledged the operation per the applied write concern.

~~~javascript
// Create if SP-009 is not found; otherwise update the fields in $set.
products.updateOne(
  { sku: "SP-009" },
  {
    $set: {
      name: "Mouse Pad",
      category: "accessory",
      priceVnd: 90000,
      stock: 20,
      active: true
    },
    $setOnInsert: { createdAt: new Date() }
  },
  { upsert: true }
);
~~~

By default `upsert: false`: if no document matches, nothing changes. With `upsert: true`, the operation can insert a new document; design the filter on a reliable identifier key (usually one backed by a unique index) to avoid duplicate records under concurrent requests. In this example, `SP-009` gets an auto-generated `_id` because `_id` is not specified.

## 5. Replacing a whole document with `replace`

`replaceOne(filter, replacement, options)` replaces the content of at most one document with a **replacement document**. Unlike `updateOne`, a replacement **does not use** `$set`, `$inc`, or other update operators. Any old field omitted from the replacement **disappears**; the existing document's `_id` must remain unchanged.

~~~javascript
products.replaceOne(
  { _id: "p003" },
  {
    _id: "p003",            // Keep _id unchanged.
    sku: "SP-003",
    name: "Aluminum Laptop Stand",
    category: "desk",
    priceVnd: 590000,
    stock: 8,
    active: true,
    tags: ["office", "aluminum"],
    supplier: { city: "Ha Noi" }
  }
);

products.findOne({ _id: "p003" });
~~~

This operation replaces document `p003` with the new version. If the replacement omits `tags`, `supplier`, or another existing field, those fields are gone after replacement. You may **omit `_id` from the replacement** so MongoDB keeps the existing `_id`; never attempt to change `_id` to a different value.

`replaceOne()` also supports `{ upsert: true }`. Use it only when the full new document data and identity rules are clearly defined. When editing only a few fields, prefer `updateOne()` with `$set`, `$inc` to avoid unintended data loss.

## 6. Deleting documents with `delete`

`deleteOne(filter)` deletes at most one matching document, and `deleteMany(filter)` deletes all matching documents. The result includes `deletedCount`.

~~~javascript
// Delete one specific document by unique key.
products.deleteOne({ _id: "p007" });

// Delete only products marked inactive.
products.deleteMany({ active: false });
// If active was not changed elsewhere, p004 is deleted.
~~~

**Before bulk-deleting**, run the exact same filter with `find()` or `countDocuments()`:

~~~javascript
const filter = { active: false, category: "accessory" };
products.find(filter, { _id: 1, sku: 1, name: 1 });
products.countDocuments(filter);

// Execute only after confirming the matched set is right.
products.deleteMany(filter);
~~~

`deleteMany({})` deletes **every** document in the collection; `deleteOne({})` deletes an arbitrary document if the condition is not specific enough. Deleting a document does not provide built-in undo or soft delete. If business logic needs history, consider flagging `active: false` or `deletedAt` and designing queries to fetch only active records.

## 7. Comparing `update` and `replace` on the same scenario

Suppose an existing document is:

~~~javascript
{
  _id: "p010",
  name: "Mouse",
  priceVnd: 300000,
  stock: 5,
  tags: ["wireless"]
}
~~~

If you call:

~~~javascript
products.updateOne(
  { _id: "p010" },
  { $set: { priceVnd: 280000 } }
);
~~~

then only `priceVnd` changes; `name`, `stock`, and `tags` remain intact. Conversely:

~~~javascript
products.replaceOne(
  { _id: "p010" },
  { _id: "p010", name: "Mouse", priceVnd: 280000 }
);
~~~

then `stock` and `tags` are dropped from the document. These two commands are **hypothetical comparison examples**: insert `p010` first if you want to run them for real.

| Criterion | `updateOne()` with operators | `replaceOne()` |
| --- | --- | --- |
| Input payload | Changes via `$set`, `$inc`, etc. | Complete replacement document |
| Unmentioned fields | Preserved | Removed from document |
| `_id` | Cannot be modified | Must match the existing document |
| Best fit | Updating price, deducting stock, adding tags | Re-syncing an entire record from a complete source |

## 8. Direct connection to Spring Data MongoDB

Spring Data MongoDB maps documents ↔ Java objects via `@Document`, `@Id`, and mapping rules. `MongoTemplate` provides operations closely aligned with native MongoDB, while `MongoRepository` is convenient for entity-based CRUD and derived query methods.

### 8.1. Mapping model

The Java 17+ example below uses `record` types to keep focus on data operations. In a real application, equivalent POJO classes can be used:

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products_crud_demo_006")
public record Product(
    @Id String id,
    String sku,
    String name,
    String category,
    long priceVnd,
    int stock,
    boolean active,
    List<String> tags,
    Supplier supplier
) {
    public record Supplier(String city) {}
}
~~~

`id` is the Java property mapped to `_id` in MongoDB. A document with a string `_id` like `"p001"` differs from an `ObjectId`, so standardize how identifiers are stored and read. The shell examples above intentionally use short strings for easy practice.

### 8.2. Corresponding commands in `MongoTemplate`

The following Java snippets can be placed inside a service injected with `MongoTemplate template`. They illustrate API calls and do not require running the earlier `mongosh` examples sequentially.

~~~java
import com.mongodb.client.result.DeleteResult;
import com.mongodb.client.result.UpdateResult;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.ReplaceOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

// READ: find(filter).sort(...).limit(...)
Query inStockQuery = Query.query(
    Criteria.where("active").is(true).and("stock").gt(0)
).with(Sort.by(Sort.Order.asc("priceVnd"), Sort.Order.asc("id")))
 .limit(10);
List<Product> inStock = template.find(inStockQuery, Product.class);

// INSERT: equivalent to insertOne().
Product newProduct = new Product(
    "p008", "SP-008", "USB-C Hub", "accessory",
    390000L, 5, true, List.of("office"),
    new Product.Supplier("Ha Noi")
);
Product inserted = template.insert(newProduct);

// UPDATE ONE: modify only stock, with a condition to avoid negative inventory.
UpdateResult updated = template.updateFirst(
    Query.query(Criteria.where("id").is("p008").and("stock").gte(1)),
    new Update().inc("stock", -1),
    Product.class
);

// UPDATE MANY: apply the same change to all matching documents.
UpdateResult updatedMany = template.updateMulti(
    Query.query(Criteria.where("category").is("accessory")
                         .and("active").is(false)),
    new Update().set("active", true),
    Product.class
);

// REPLACE ONE: pass an object holding all information to keep.
Product replacement = new Product(
    "p008", "SP-008", "6-Port USB-C Hub", "accessory",
    490000L, 4, true, List.of("office", "usb-c"),
    new Product.Supplier("Ha Noi")
);
UpdateResult replaced = template.replace(
    Query.query(Criteria.where("id").is("p008")),
    replacement,
    ReplaceOptions.none()
);

// DELETE: remove(Query, Class) deletes documents matching the filter.
DeleteResult deleted = template.remove(
    Query.query(Criteria.where("id").is("p008")),
    Product.class
);
~~~

In Spring Data, `Criteria.where("id")` is mapped via `@Id` to `_id` when querying with entity `Product`. `updateFirst` corresponds to `updateOne`; `updateMulti` corresponds to `updateMany`; `replace` corresponds to `replaceOne`. With `template.remove(Query, Product.class)`, every document matching `Query` can be deleted, so the example uses a unique `id` condition.

**Important point about replacement:** the replacement object must have a complete set of fields and a valid `id`. Per the Spring Data API, `replace` cannot be used to change the `_id` of an existing document. When combining `replace` + `upsert` on an entity using a custom id type, control `_id` in the query or replacement to avoid generating an unexpected `ObjectId` type.

### 8.3. Using `MongoRepository` for entity-based operations

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository extends MongoRepository<Product, String> {
    Optional<Product> findBySku(String sku);
    List<Product> findByActiveTrueAndStockGreaterThan(int minStock);
}
~~~

~~~java
// Example inside a service injected with ProductRepository repository.
Optional<Product> one = repository.findById("p001");
List<Product> available = repository.findByActiveTrueAndStockGreaterThan(0);

// save() inserts if new; when _id already exists, it rewrites the entity state.
Product saved = repository.save(newProduct);
repository.deleteById("p008");
~~~

`save()` is not a copy of `$set`: when saving an existing entity, rewriting the document can drop fields not mapped onto the entity. When you need to increment/decrement a field, require an atomic conditional update, or want to edit specific fields, use `MongoTemplate.updateFirst` / `updateMulti` or an appropriate update query.

In **reactive** flows, `ReactiveMongoTemplate` and `ReactiveMongoRepository` provide similar operations returning `Mono` / `Flux`. Publishers must be subscribed to by the reactive pipeline to execute; do not apply the synchronous assumption that "calling the method means the write has already happened."

## 9. Common errors and self-checks

| Symptom | Common cause | How to check / handle |
| --- | --- | --- |
| `find()` returns empty despite seeing data | Wrong database, collection, field name, `_id` type, data type, or letter casing | `db.getName()`, `products.findOne({})`, compare with matching types |
| `E11000 duplicate key` on insert | Duplicate `_id` or field with unique index | Check values and `products.getIndexes()`; use a new key or handle creation flow |
| `matchedCount: 1`, `modifiedCount: 0` | Value already equals desired value | Read document after update; do not treat as an error by default |
| `matchedCount: 0` | No matching document, or concurrent condition (like `stock >= 2`) no longer holds | Run `findOne(filter)` with the exact update filter |
| Fields lost after edit | Used `replaceOne` or `save` with an object missing properties | Switch to `$set` / `$inc` when modifying only a few fields |
| Modified/deleted too many documents | Broad filter or `{}` | Run `find(filter)` and `countDocuments(filter)` before writing |
| Slow query | Collection scan, unindexed sort, deep `skip` | Inspect `explain("executionStats")` and index based on real queries |

When modifying multiple related documents, do not assume individual CRUD commands ensure cross-document consistency. Use transactions only when business requirements truly demand them and your MongoDB deployment supports them; transactions, advanced indexing, aggregation, and deep performance analysis are subsequent topics in the Spring Data MongoDB module.

## 10. Short practice exercise

Try three queries **right after loading the initial four documents** from section 1, before running later write commands:

1. Fetch `sku`, `name`, and `stock` of products that are active and in stock, without returning `_id`.
2. Find active accessories priced at no more than 500,000 VND.
3. List products whose `supplier.city` is `"Ha Noi"`, sorted by descending price.

**Reference solutions:**

~~~javascript
// 1. Expected: p001 and p003.
products.find(
  { active: true, stock: { $gt: 0 } },
  { _id: 0, sku: 1, name: 1, stock: 1 }
);

// 2. Expected: p002.
products.find({
  category: "accessory",
  active: true,
  priceVnd: { $lte: 500000 }
});

// 3. Expected: p001 then p003.
products.find({ "supplier.city": "Ha Noi" })
  .sort({ priceVnd: -1, _id: 1 });
~~~

Next, write an `updateOne()` yourself that decrements `p003` stock by 1 **only if `stock > 0`**, read `matchedCount`, and verify the remaining stock using `findOne()`. Try writing a `replaceOne()` for `p003` with one field omitted in the replacement and observe the difference compared to `updateOne()` on a test collection.

## References

- [MongoDB Manual — CRUD Operations](https://www.mongodb.com/docs/manual/crud/): read/write commands and operation atomicity.
- [MongoDB Manual — Update Methods](https://www.mongodb.com/docs/manual/reference/update-methods/): distinguishing `updateOne`, `updateMany`, and `replaceOne`.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate`, update, replace, delete, and related APIs.
