# `delete`, `deleteById`, `deleteAllById`, and `deleteAll` in Spring Data MongoDB

> **Chapter:** Repository CRUD  
> **Module:** `SPRING_DATA_MONGODB` — connecting, document mapping, and operating on MongoDB via `MongoTemplate` or repositories; extending to query design, testing, transactions, and performance diagnostics.  
> **Objectives:** Choose the right delete API by entity, single ID, multiple IDs, or entire collection; understand `@Version`, behavior when not found, bulk deletion risks, and how to confirm deleted document counts.

## 1. Four method names, different semantics

`MongoRepository<T, ID>` provides CRUD operations inherited from Spring Data Commons. Within the same repository, the following calls are all valid, yet **differ in scope and how deletion conditions are checked**:

~~~java
orders.delete(order);                           // Delete one entity.
orders.deleteById("o101");                       // Delete by one ID.
orders.deleteAllById(List.of("o102", "o103"));    // Delete by a group of IDs.
orders.deleteAll();                              // Delete the entire repository collection.
orders.deleteAll(List.of(order1, order2));       // Delete the supplied entities.
~~~

| API | Argument | Scope | Return type | Notable behavior |
| --- | --- | --- | --- | --- |
| `delete(T entity)` | Entity with ID | One document matching the entity | `void` | With `@Version`, checks the entity's version |
| `deleteById(ID id)` | Single ID | Document with matching `_id` | `void` | Does not require loading the entity; skips version check |
| `deleteAllById(Iterable<? extends ID> ids)` | Multiple IDs | Set of documents whose `_id` is in the list | `void` | MongoDB repository implements via ID filter; does not check per-entity version |
| `deleteAll()` | None | **Every document** in the repository's collection | `void` | Very dangerous if executed against the wrong environment |
| `deleteAll(Iterable<? extends T> entities)` | Multiple entities | The passed-in entities | `void` | MongoDB repository calls `delete(entity)` sequentially; can raise version errors |

In the current `SimpleMongoRepository`, `deleteById`, `deleteAllById`, and `deleteAll()` are implemented via `MongoOperations.remove(Query, ...)`. `delete(T entity)` deletes based on the entity and inspects the deletion result when the entity has `@Version`. Implementation details can vary between Spring Data versions; when upgrading, check your project's dependency version and documentation.

**Do not confuse with JPA:** APIs such as `deleteAllByIdInBatch` belong to Spring Data JPA; they are not default methods to use in `MongoRepository`.

## 2. Preparing the entity and practice dataset

### 2.1. Java entity

The example uses a simple entity with its ID stored strictly as BSON `string` via `@MongoId(FieldType.STRING)`. The `@Version` field will be used in the concurrent update/delete section.

~~~java
package com.example.orders;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_delete_demo_006")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    private String state;
    private long totalVnd;

    @Version
    private Long version;

    protected OrderDocument() { }

    public OrderDocument(String id, String state, long totalVnd) {
        this.id = id;
        this.state = state;
        this.totalVnd = totalVnd;
    }

    public String getId() { return id; }
    public String getState() { return state; }
    public long getTotalVnd() { return totalVnd; }
    public Long getVersion() { return version; }
    public void setState(String state) { this.state = state; }
}
~~~

~~~java
package com.example.orders;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {

    long countByState(String state);

    boolean existsByState(String state);
}
~~~

`String` in `MongoRepository<OrderDocument, String>` is the ID type in the Java API. The entity's mapping determines the BSON `_id` type. If `@Id String` were used instead of `@MongoId(FieldType.STRING)`, a valid 24-character hex string might be converted by Spring Data into a BSON `ObjectId`, causing ID queries/deletes to miss documents stored as strings.

### 2.2. Initial MongoDB data

Open `mongosh` on a **dedicated practice database**:

~~~javascript
use spring_data_mongodb_lab

const orders = db.orders_delete_demo_006;

orders.insertMany([
  { _id: "o101", state: "NEW",       totalVnd: 100000, version: NumberLong(0) },
  { _id: "o102", state: "CANCELLED", totalVnd: 200000, version: NumberLong(0) },
  { _id: "o103", state: "CANCELLED", totalVnd: 300000, version: NumberLong(0) },
  { _id: "o104", state: "PAID",      totalVnd: 400000, version: NumberLong(0) },
  { _id: "o105", state: "ARCHIVED",  totalVnd: 500000, version: NumberLong(0) },
  { _id: "o106", state: "NEW",       totalVnd: 600000, version: NumberLong(0) }
]);

orders.find({}, { _id: 1, state: 1, version: 1 }).sort({ _id: 1 });
orders.countDocuments({}); // 6
~~~

`NumberLong(0)` gives the MongoDB field the same 64-bit integer type as `Long version`. The dataset uses fixed keys; running `insertMany` again on a non-empty collection raises `E11000 duplicate key`. Expected outcomes in this lesson **assume starting independently from the initial dataset**, unless a section explicitly indicates sequential execution.

To replay a scenario, use a **fresh test collection** or reset data you are authorized to manage. Never run `deleteAll()` on a repository pointing to a shared database just to "reset" an exercise.

## 3. `delete(T entity)`: deleting by object

When you already hold an entity from a query or business flow, use:

~~~java
OrderDocument order = repository.findById("o101")
    .orElseThrow(() -> new IllegalArgumentException("Order not found"));

repository.delete(order);
~~~

In this example, `repository` is an injected `OrderRepository` field. For an entity with `@Version`, Spring Data MongoDB uses **the object's ID and version** to ensure you do not accidentally delete a version modified by someone else.

### 3.1. Why pass the entity instead of the ID?

`delete(order)` is useful when:

- You just loaded the entity and need to verify business rules, such as allowing deletion only for `NEW` orders.
- The entity has `@Version` and deletion must obey **optimistic locking**.
- You want to clearly express "delete this exact loaded and validated object".

~~~java
public void deleteDraftOrder(String id) {
    OrderDocument order = repository.findById(id)
        .orElseThrow(() -> new IllegalArgumentException("Order not found"));

    if (!"NEW".equals(order.getState())) {
        throw new IllegalStateException(
            "Only NEW orders can be deleted"
        );
    }

    repository.delete(order);
}
~~~

This is an example method inside a service with an `OrderRepository repository` field. If another client modifies the document through a `version`-updating operation between read and delete, `delete(order)` will not silently remove the updated record; a version mismatch can throw `OptimisticLockingFailureException`. This does not replace authorization rules, referential checks, or other business conditions.

### 3.2. When the document is already gone

With `@Version`, `delete(entity)` inspects the deletion result **acknowledged by the server**. When the deleted count is 0 due to a version mismatch or a missing document, Spring Data can throw `OptimisticLockingFailureException`.

For entities **without** `@Version`, do not assume such an exception will be thrown when deleting a missing document. If business logic must distinguish "deleted" from "not found", design a method returning an explicit result (section 10).

## 4. `deleteById(ID id)`: deleting by a single key

~~~java
repository.deleteById("o102");
~~~

With `OrderDocument`'s mapping, this targets the document whose BSON string `_id` is `"o102"`. You do not need to load the entity beforehand. In the current MongoDB implementation, the method builds an ID filter and calls `MongoOperations.remove(Query, ...)`; the entity version is **not included in the delete condition**.

### 4.1. When the ID does not exist

~~~java
repository.deleteById("o999");
// No o999: per the CRUD contract, missing IDs are ignored.
~~~

`deleteById` returns `void`, so it does not report how many documents were deleted. The Spring Data Commons contract specifies that a non-existent ID is **silently ignored**. `null` is an invalid input:

~~~java
repository.deleteById(null);
// IllegalArgumentException.
~~~

Do not interpret "no exception thrown" as "one document was deleted". When an API must report the exact number of deleted documents, use `MongoTemplate.remove(Query, Entity.class)` and inspect `DeleteResult`.

### 4.2. `deleteById` differs from `delete(entity)` with `@Version`

Suppose entity `o101` was loaded at version 0, and someone else later updated it to version 1:

- `repository.delete(staleEntity)` uses ID **and version 0**; MongoDB finds no matching document, and Spring Data raises an optimistic locking error.
- `repository.deleteById("o101")` uses **only the ID**; if the document still exists, it is deleted even though its version is now 1.

Therefore, **do not substitute `deleteById` for `delete(entity)` in flows requiring version control**. This is a concrete detail of Spring Data MongoDB; the general `CrudRepository` Javadoc covers multiple stores, so when nuances differ, consult the MongoDB documentation and repository implementation.

## 5. `deleteAllById(Iterable<ID>)`: deleting by a list of keys

~~~java
repository.deleteAllById(List.of("o102", "o103", "o999"));
~~~

If the initial dataset contains `o102` and `o103`, both are removed; `o999` does not exist and is ignored. The API returns `void` and does not report "2 of 3 IDs deleted".

In the current `SimpleMongoRepository`, `deleteAllById` builds a filter from the IDs and executes a query-based remove operation, conceptually equivalent to:

~~~javascript
// Illustrative BSON filter; do not run after the repository call above.
orders.deleteMany({ _id: { $in: ["o102", "o103", "o999"] } });
~~~

For entities with `@Version`, this **ID-set deletion** does not check each document's version individually. If per-object optimistic locking is required, load the relevant entities and call `deleteAll(entities)` or `delete(entity)`, while recognizing that multiple individual operations do not form an atomic transaction by themselves.

### 5.1. Edge cases

~~~java
repository.deleteAllById(List.of()); // Empty list: no IDs to delete.

repository.deleteAllById(List.of("o101", "o101"));
// Duplicate IDs do not mean deleting the same document twice.

repository.deleteAllById(null);
// IllegalArgumentException.
~~~

The Spring Data Commons contract requires the `Iterable` to be non-null and contain no `null` elements. Java's `List.of(...)` forbids null elements; if taking IDs from external input, filter and validate before calling. Do not depend on how a specific version handles null items.

If a list contains many thousands or millions of IDs, building a massive `$in` query can cause command size, memory, performance, and BSON limit problems. Split into **bounded batches**, track outcomes, and cap input size.

### 5.2. Is a multi-ID delete a transaction?

No. `deleteAllById` may execute as a single MongoDB multi-document delete call, yet **it does not make the entire document set an atomic unit**. MongoDB guarantees per-document atomicity; cross-document atomicity requires a transaction on a supported topology.

With a `void` API, you also cannot tell which exact IDs were deleted when some were absent. If auditing is needed, query/verify explicitly or record business logs.

## 6. `deleteAll()`: deleting every document in the collection

~~~java
repository.deleteAll();
~~~

No arguments means **delete all documents in the collection mapped by the repository**, such as `orders_delete_demo_006`. It does not delete only orders loaded in memory, nor only records filtered in a UI, nor does it care about `NEW`/`CANCELLED` states.

On the original 6-order dataset, after calling:

~~~javascript
orders.countDocuments({}); // 0
~~~

`deleteAll()` issues an unfiltered remove query across the collection's documents. It is **not** `dropCollection()`: the collection and its indexes can remain intact. Nor does it "reset the database to a clean baseline"; metadata, indexes, concurrent writers, and other collections are untouched.

### 6.1. When should it be used?

Reasonable scenarios include isolated test databases, regenerable scratch data, or an explicitly designed workflow intended to wipe an entire collection.

In business APIs, narrower filters are usually appropriate, such as purging old `CANCELLED` orders. `MongoRepository.deleteAll()` takes no filter parameter; when criteria are needed, use a query with `MongoTemplate` or a properly declared repository delete query.

### 6.2. Deleting all and `@Version`

`deleteAll()` **does not read each entity** to verify `version`. In the current implementation, it issues a remove command with an empty query. Do not expect per-document optimistic locking or entity-level callbacks like `delete(entity)`.

**Safeguard rules:** isolate test databases/collections; verify active profiles, database URIs, collection names, and credentials before any full-collection deletion.

## 7. An easily confused overload: `deleteAll(Iterable<? extends T> entities)`

~~~java
List<OrderDocument> selected = repository.findAllById(
    List.of("o101", "o104")
);

repository.deleteAll(selected);
~~~

This is **not** the parameterless `deleteAll()`. It deletes only the **passed-in entities**. In `SimpleMongoRepository`'s implementation, this overload iterates the list and invokes `delete(entity)` on each element:

~~~java
// Conceptual implementation, not framework replacement code:
for (OrderDocument order : selected) {
    repository.delete(order);
}
~~~

As a result:

- `@Version` checks can be applied to each entity.
- Multiple delete calls may be issued instead of a single `$in` query.
- If a failure occurs midway, entities deleted earlier are **not automatically restored**.
- If deleting all items must succeed or fail as one transaction, use `MongoTransactionManager` and supported transactions, factoring in limits and overhead.

`deleteAllById(ids)` and `deleteAll(entities)` differ in both **argument type** and **versioning/per-entity processing semantics**. Switching from one to the other merely to reduce query count can alter data consistency behavior.

## 8. Direct comparison with `MongoTemplate`

Repositories streamline CRUD, but all the delete methods above return `void`. `MongoTemplate` provides entity/query deletion APIs that return the MongoDB driver's `DeleteResult`:

~~~java
import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Assume template is injected into a service.
DeleteResult one = template.remove(
    Query.query(Criteria.where("id").is("o101")),
    OrderDocument.class
);

long deleted = one.getDeletedCount();
~~~

Note that `DeleteResult` requires writes to be **acknowledged** to reliably read counts. With `WriteConcern.UNACKNOWLEDGED`, do not expect result checks or optimistic locking to work as they do under server acknowledgement.

| Repository | Conceptual MongoDB / `MongoTemplate` equivalent | Notes |
| --- | --- | --- |
| `delete(entity)` | `template.remove(entity)` | Deletes by entity; can include `@Version` check |
| `deleteById(id)` | `template.remove(Query by id, Entity.class)` | Queries by ID; no version check |
| `deleteAllById(ids)` | `template.remove(Query by id list, Entity.class)` | Single multi-ID query; no per-entity version check |
| `deleteAll()` | `template.remove(new Query(), Entity.class)` | Unfiltered; deletes whole collection |
| `deleteAll(entities)` | Loop `template.remove(entity)` | Deletes per entity; can fail midway |

### 8.1. Deleting by business condition

For example, deleting all orders in `CANCELLED` state:

~~~java
Query cancelled = Query.query(
    Criteria.where("state").is("CANCELLED")
);

DeleteResult result = template.remove(
    cancelled,
    OrderDocument.class
);

long numberDeleted = result.getDeletedCount();
~~~

Before deleting, you can count to preview the scale:

~~~java
long candidates = template.count(
    cancelled,
    OrderDocument.class
);
~~~

**Concurrency warning:** the `candidates` count read beforehand can differ from `numberDeleted` if data changes concurrently; the two calls do not automatically execute inside a transactional snapshot. `DeleteResult.getDeletedCount()` tells you how many documents the server reported deleting, whereas `void` repository methods do not expose this directly.

### 8.2. Deleting by ID only when in the expected state

When business rules allow deleting only `NEW` orders, a query with **two criteria** checks and deletes one document in a single operation:

~~~java
Query safeDelete = Query.query(
    Criteria.where("id").is("o101")
        .and("state").is("NEW")
);

DeleteResult result = template.remove(
    safeDelete,
    OrderDocument.class
);

if (result.getDeletedCount() == 0) {
    // Order missing, or no longer in NEW state.
    throw new IllegalStateException(
        "Order not found or state no longer allows deletion"
    );
}
~~~

This performs an **atomic conditional deletion on a single document** without needing a separate read before deciding to delete. It does not check `@Version` automatically unless you include a version criterion in the `Query`.

### 8.3. When you need the deleted document returned

If auditing requires the deleted document itself rather than just a count, use `MongoTemplate.findAndRemove(Query, Class)`:

~~~java
OrderDocument deletedOrder = template.findAndRemove(
    Query.query(Criteria.where("id").is("o101")),
    OrderDocument.class
);
// deletedOrder == null when no document matches.
~~~

For a single document, find-and-remove is atomic on MongoDB's side. If an independent audit log must be written in another collection, writing the audit entry and deleting the order are **two distinct operations**, requiring a transaction or outbox pattern per requirements.

## 9. `@Version` and optimistic locking during deletion

Spring Data MongoDB supports optimistic locking via `@Version`. When saving an existing entity, Spring Data normally includes the prior version in the update filter and increments the version. Likewise, when deleting **by entity**, version metadata detects a stale object.

### 9.1. Two concurrent editors scenario

Suppose `o101` initially has `version = 0`:

~~~java
OrderDocument stale = repository.findById("o101").orElseThrow();
OrderDocument current = repository.findById("o101").orElseThrow();

current.setState("PAID");
repository.save(current); // Version in MongoDB typically increments 0 -> 1.

repository.delete(stale);
// With write acknowledgement: OptimisticLockingFailureException.
~~~

Because `stale` holds version 0, entity deletion does not match the document whose version incremented. Proper business handling usually reloads the entity, surfaces the conflict to the client, or retries under defined rules; **do not switch to `deleteById` just to bypass versioning**.

Conversely:

~~~java
repository.deleteById("o101");
// Deletes by ID if the document exists, even though current version is 1.
~~~

These two snippets represent **two competing branches for comparison**. Do not run them sequentially expecting the document to remain so both outcomes can be demonstrated together.

### 9.2. Impact table for `@Version`

| MongoDB repository API | Under current MongoDB implementation |
| --- | --- |
| `delete(entity)` | Checks ID + version; can throw `OptimisticLockingFailureException` |
| `deleteById(id)` | Does not check version |
| `deleteAllById(ids)` | Does not check version per entity |
| `deleteAll(entities)` | Calls per-entity delete, so can trigger optimistic locking |
| `deleteAll()` | Deletes via empty query; does not check version |

Spring Data Commons documentation defines a shared CRUD contract across multiple data stores and describes optimistic locking capabilities in general terms. For **MongoDB**, official documentation explicitly notes that `CrudRepository.deleteById(ID)` deletes **without checking version**; `SimpleMongoRepository` likewise builds an ID-only query.

### 9.3. Acknowledged write concern is required

Optimistic locking verification relies on the server reporting the affected document count. With `WriteConcern.UNACKNOWLEDGED`, the application cannot rely on returned counts to catch conflicts. For business data requiring integrity, use a write concern suited to your durability and error-visibility needs.

## 10. Building deletion APIs with meaningful responses

### 10.1. Idempotent endpoints vs. "not found"

In REST, `DELETE /orders/o101` can follow one of two styles:

- **State-idempotent:** delete the ID if present; if already deleted, still return a success response such as `204 No Content`.
- **Distinguishing absence:** return `404 Not Found` when the order does not exist, or `409 Conflict` when state/version forbids deletion.

`deleteById` suits the first variant because it returns no count. For the second variant, use a conditional query with `DeleteResult` or design explicit checks. A pair of `existsById()` followed by `deleteById()` has a **race condition**: the document can change between the two steps.

### 10.2. Example service with clear deletion status

~~~java
package com.example.orders;

import com.mongodb.client.result.DeleteResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class OrderDeletionService {
    private final MongoTemplate template;

    public OrderDeletionService(MongoTemplate template) {
        this.template = template;
    }

    public boolean deleteNewOrder(String orderId) {
        Query query = Query.query(
            Criteria.where("id").is(orderId)
                .and("state").is("NEW")
        );

        DeleteResult result = template.remove(query, OrderDocument.class);
        return result.getDeletedCount() == 1;
    }
}
~~~

Here `false` means **no document matched both ID and `state=NEW` simultaneously**. It does not itself distinguish "ID missing" from "state already changed"; the service/caller decides how to map that into an API response. The example also assumes write acknowledgement and that the collection points to the intended database.

For "delete only if the client saw version N", add `and("version").is(expectedVersion)` to the query. After a failed delete, you can look up the document again to distinguish stale version from non-existence, keeping in mind data can still change between calls outside a transaction.

## 11. Deleting related data: repositories do not cascade automatically

MongoDB does not enforce foreign keys for manual references. Spring Data MongoDB also does not cascade deletes across collections simply because an entity uses `@DBRef` or `@DocumentReference`.

Example:

~~~javascript
// customers
{ _id: "c001", name: "An" }

// orders
{ _id: "o101", customerId: "c001" }
~~~

If `customerRepository.deleteById("c001")` is called, the order document can retain `customerId: "c001"`, becoming a dangling reference. Decide a policy before deleting a parent entity:

| Policy | Meaning |
| --- | --- |
| `RESTRICT` | Block deletion while dependent documents exist |
| `CASCADE` | Delete dependent documents according to business rules |
| `DETACH / SET NULL` | Clear the reference on dependent documents |
| `SOFT DELETE` | Keep the document, mark it inactive/deleted |
| `RETAIN SNAPSHOT` | Keep required historical data embedded on dependent documents |

Never use `deleteAll()` to "clean up" a dependent collection without an explicit policy. Cross-collection deletions **are not automatically atomic**. When cross-document consistency is required, consider MongoDB transactions on a supported topology, while handling races with concurrent writers creating new links.

## 12. Soft delete vs. hard delete

The `delete...` methods above perform **hard deletes**: documents are no longer returned by ordinary queries. If history, auditing, or recovery is needed, use **soft delete**:

~~~javascript
orders.updateOne(
  { _id: "o101", deletedAt: { $exists: false } },
  { $set: { deletedAt: new Date() } }
);
~~~

In Java:

~~~java
Query active = Query.query(
    Criteria.where("id").is("o101")
        .and("deletedAt").exists(false)
);

template.updateFirst(
    active,
    new org.springframework.data.mongodb.core.query.Update()
        .set("deletedAt", java.time.Instant.now()),
    OrderDocument.class
);
~~~

To store `deletedAt` cleanly through entity mapping, declare the property on the class or manage converters; calling `MongoTemplate.updateFirst` alone can still write the BSON field, yet a subsequent `save(entity)` could affect unmapped fields. Declare `deletedAt` and standardize query rules if soft delete is part of your design.

**Note:** adding `deletedAt` to an entity does not make `findAll`/`findById` automatically hide deleted records. You must design consistent filters/queries or repository abstractions—including counts, indexes, and relationship handling.

## 13. Performance and large-scale deletions

### 13.1. Deleting a single document

Lookups by `_id` generally leverage MongoDB's default index. `deleteById(id)` skips loading the entity first, avoiding an extra round trip compared to manual `findById` then `delete(entity)`; in exchange, it skips version checking.

### 13.2. Deleting many IDs

`deleteAllById(ids)` works well when you know the exact key list. For very large lists, consider:

- `$in`/BSON command size and application memory.
- Write pressure, I/O, and replication lag from mass deletions.
- The possibility that some IDs do not exist or are concurrently created/updated.
- Recording per-batch results for idempotent retries.

A practical pattern with a validated list:

~~~java
// Batching pseudocode; batchSize should be tuned for your system.
int batchSize = 500;

for (int from = 0; from < ids.size(); from += batchSize) {
    int to = Math.min(ids.size(), from + batchSize);
    repository.deleteAllById(ids.subList(from, to));
}
~~~

Here `ids` is a deduplicated, validated `List<String>`, not raw user input. The loop does not create a transaction spanning all batches. A failure midway leaves earlier batches deleted while later batches remain; retry workflows must account for that state.

### 13.3. Deleting by status and age

To purge `CANCELLED` orders past a retention window:

~~~java
Query expired = Query.query(
    Criteria.where("state").is("CANCELLED")
        .and("createdAt").lt(cutoff)
);

DeleteResult result = template.remove(expired, OrderDocument.class);
~~~

Here `cutoff` is an `Instant` or a time type with an appropriate converter; the model must include `createdAt`. Add an index matching the query, test on small data, and inspect `explain("executionStats")` for the find predicate. Never use `deleteAll()` followed by re-inserting recent records just to implement retention.

With a **TTL index**, MongoDB can automatically remove expired documents, though TTL removal runs asynchronously with lag, does not replace all business policies, and is not suited to every collection.

### 13.4. Events and auditing

Query/bulk deletes do not materialize a full Java entity for every deleted document. If business rules require emitting events or audits containing each deleted order's payload, design explicitly: capture snapshots before deleting (mindful of races), use change streams, or apply a transactional/outbox pattern. Do not assume `deleteAllById` or `deleteAll()` automatically fires per-entity domain events.

## 14. Reactive repositories: similar semantics, different execution

With `ReactiveMongoRepository<OrderDocument, String>`, the corresponding delete APIs return publishers, typically `Mono<Void>`:

~~~java
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, String> {
}
~~~

~~~java
import reactor.core.publisher.Mono;

Mono<Void> deletedOne = reactiveRepository.deleteById("o101");
Mono<Void> deletedMany = reactiveRepository.deleteAllById(
    List.of("o102", "o103")
);
Mono<Void> deletedAll = reactiveRepository.deleteAll();
~~~

These `Mono` instances are **lazy**: they must be subscribed to by a reactive chain before any command executes. Never call `block()` on an event loop. Like the synchronous API, `Mono<Void>` does not return the deleted count; when a count is needed, use `ReactiveMongoTemplate.remove(Query, Class)`, which returns `Mono<DeleteResult>`, and map `getDeletedCount()`.

Note: reactive APIs also provide overloads accepting `Publisher`, and behavior details can depend on version. Do not treat `Mono<Void>` as a `Boolean` meaning "successfully deleted one document"; it signals only completion or error.

## 15. Testing deletions

Because deletion directly interacts with MongoDB and Spring Data mapping/`@Version`, core cases should use **integration tests** on MongoDB Testcontainers or an isolated test database. Repository mocks typically miss BSON ID type mismatches or differences between overloads.

### 15.1. Essential test matrix

| Test | What to assert |
| --- | --- |
| `delete(entity)` with current version | Document is deleted |
| `delete(entity)` with stale version | Throws `OptimisticLockingFailureException`; newer document remains |
| `deleteById(id)` with valid ID | Document with matching ID is deleted |
| `deleteById(missingId)` | Leaves other documents intact; does not error |
| `deleteAllById` with existing + missing IDs | Only matching documents are deleted |
| `deleteAll(entities)` with a stale entity | Optimistic locking error may occur; confirm no automatic rollback assumed |
| `deleteAll()` on a test collection | Document count drops to 0; collection is not dropped |
| Conditional delete query by state | Deletes only target state, preserving others |
| Hex-shaped ID stored as BSON string | Delete query matches type correctly via `@MongoId` mapping |

### 15.2. Example test avoiding `deleteAll()` for fixture cleanup

~~~java
package com.example.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderRepositoryDeletionTest {
    @Autowired OrderRepository repository;

    @Test
    void deletesSelectedIdsAndIgnoresMissingId() {
        // Run only against an isolated test database.
        String first = "fixture-006-a";
        String second = "fixture-006-b";

        repository.deleteAllById(List.of(first, second));
        try {
            repository.save(new OrderDocument(first, "NEW", 100));
            repository.save(new OrderDocument(second, "NEW", 200));

            repository.deleteAllById(
                List.of(first, "fixture-006-missing")
            );

            assertThat(repository.existsById(first)).isFalse();
            assertThat(repository.existsById(second)).isTrue();
        } finally {
            repository.deleteAllById(List.of(first, second));
        }
    }
}
~~~

This example assumes no other concurrent test shares those fixture IDs and documents can be persisted independently. To test `deleteAll()`, use a repository targeting a **collection dedicated solely to that test**; never run it against a shared collection or shared environment. For transaction behavior, tests must use a MongoDB topology that supports transactions.

### 15.3. Testing optimistic locking

A test should create a `@Version` entity, load two Java copies, save one to bump the version, and then call `delete(stale)`. Assert:

~~~java
assertThatThrownBy(() -> repository.delete(stale))
    .isInstanceOf(OptimisticLockingFailureException.class);
~~~

This snippet requires `import static org.assertj.core.api.Assertions.assertThatThrownBy;` and `import org.springframework.dao.OptimisticLockingFailureException;`; `stale` is read from the test database before the version bump. Verifying the newer record still exists distinguishes an optimistic locking failure from a connection failure.

## 16. Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Document remains after `deleteById` | Wrong database/collection; BSON ID type mismatch; ID absent | Check `@Document`, `@Id`/`@MongoId`, inspect in `mongosh` |
| `deleteById` throws no error when ID is missing | Expected CRUD contract; missing IDs are silently ignored | Use `DeleteResult` when deleted count is needed |
| `delete(entity)` throws `OptimisticLockingFailureException` | Stale entity, version changed, or document already deleted | Reload and resolve conflict; do not drop versioning casually |
| `deleteAllById` deletes fewer items than passed IDs | Duplicate IDs, missing IDs, ID mapping mismatch, or concurrent changes | Validate IDs and use `MongoTemplate` when counts matter |
| `deleteAll()` wipes unintended data | Repository pointed at wrong database or shared collection | Isolate environments, restrict credentials, verify config before calling |
| Deletes some entities then stops | `deleteAll(entities)` deletes sequentially and fails midway | Consider transactions or retry/compensation workflows |
| Deleting parent leaves dangling child references | No automatic cascade across collections | Enforce RESTRICT/DETACH/CASCADE/soft delete per policy |
| Bulk delete query is slow | Unindexed filter, high document count, heavy write/replication load | Add matching indexes, batch deletions, measure plan/latency |
| Repository delete gives no count | Repository delete methods above return `void` | Use `MongoTemplate.remove` and inspect `DeleteResult` |
| Reactive delete has no effect | `Mono` was never subscribed to | Wire into reactive pipeline / `StepVerifier` in tests |

## 17. Practice exercises

The exercises below assume you re-seed the 6 initial documents in the practice collection (section 2.2) **before each exercise**.

### Exercise 1 — Deleting one order by ID

Write repository code to delete `o102`, then verify `o104` still exists.

~~~java
repository.deleteById("o102");

boolean targetDeleted = !repository.existsById("o102");
boolean unrelatedRemains = repository.existsById("o104");
// targetDeleted=true, unrelatedRemains=true on the initial fixture.
~~~

**Question:** If `o102` never existed in the first place, does `targetDeleted=true` prove the delete removed a document? **No**. Checking post-condition non-existence differs from observing the actual deleted document count.

### Exercise 2 — Deleting multiple IDs

Delete `o102`, `o103`, and `o999` in a single repository call. How many documents from the original dataset remain?

~~~java
repository.deleteAllById(
    List.of("o102", "o103", "o999")
);
// 4 documents remain: o101, o104, o105, o106.
~~~

`o999` does not exist and is not counted as a deleted document.

### Exercise 3 — Comparing the two `deleteAll` overloads

~~~java
List<OrderDocument> selected = repository.findAllById(
    List.of("o101", "o106")
);
repository.deleteAll(selected);
~~~

Question: Why is this call different from `repository.deleteAll()`?

**Answer:** `deleteAll(selected)` operates only on the entities inside `selected`, can check `@Version`, and deletes entity by entity. `deleteAll()` deletes every document in the repository's collection without taking a list and without per-entity version checks.

### Exercise 4 — Preventing deletion of paid orders

Requirement: only `NEW` orders may be deleted. Write a `MongoTemplate` call checking both ID and status, then read the deleted count.

~~~java
DeleteResult result = template.remove(
    Query.query(
        Criteria.where("id").is("o101").and("state").is("NEW")
    ),
    OrderDocument.class
);

long deletedCount = result.getDeletedCount(); // 1 on the original dataset.
~~~

If `o101` is changed to `PAID` beforehand, `deletedCount` will be 0. That is the intended behavior of conditional deletion.

### Exercise 5 — Version contention

Two requests read order `o101` at version 0. Request A saves an update, bumping version to 1. Request B calls `delete(staleEntity)`. What happens? What if B switches to `deleteById("o101")`?

**Answer:** With `delete(staleEntity)`, Spring Data MongoDB compares version 0 and does not delete the newer record; when acknowledged by the server, it throws `OptimisticLockingFailureException`. `deleteById` filters solely by ID, so it can still delete the newer document if present. Do not switch to that API when concurrent update protection is required.

## References

- [Spring Data Commons — `CrudRepository` API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html): delete overloads, parameters, and contract for non-existent IDs.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): `MongoTemplate.remove`, delete operations, and `@Version`.
- [Spring Data MongoDB — `SimpleMongoRepository` source](https://github.com/spring-projects/spring-data-mongodb/blob/main/spring-data-mongodb/src/main/java/org/springframework/data/mongodb/repository/support/SimpleMongoRepository.java): implementation of `delete`, `deleteById`, `deleteAllById`, and `deleteAll`.
- [Spring Data MongoDB — Repositories](https://docs.spring.io/spring-data/mongodb/reference/repositories.html): repository model and MongoDB queries.
- [MongoDB Manual — Delete Documents](https://www.mongodb.com/docs/manual/tutorial/remove-documents/): `deleteOne()`/`deleteMany()`, delete command behavior.
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomicity and multi-document transactions.
