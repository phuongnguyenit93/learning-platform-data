# Limits of DBRef, Document References, and Sync-Only Features

## 1. Problem: Migrating a MongoDB System from Blocking to Reactive

An ordering system uses Spring Data MongoDB with **`MongoRepository`** and **`MongoTemplate`**. Inside the `Order` entity, developers previously declared relationships to `Customer`/`Product` via **`@DBRef`** or **`@DocumentReference`**, then accessed properties as if those related Java objects were already loaded from other collections.

When migrating to **`ReactiveMongoRepository`** and **`ReactiveMongoTemplate`**, one change looks deceptively simple:

~~~java
// Initially: blocking repository.
interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {}

// After switching: reactive repository.
interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {}
~~~

However, **changing return types to `Mono`/`Flux` does not automatically make the mapping layer's relationship resolution non-blocking**. Specifically, Spring Data MongoDB's automatic resolution of **DBRef/document references** has explicit limits in reactive infrastructure. Continuing to rely on lazy reference resolution as in the blocking stack can cause mapping errors, unresolved fields, or designs that accidentally inject blocking I/O into Reactor threads.

In this lesson, we will build explicit reactive reading of Orders with Customers and Products:

- Store **`customerId`** and **`productIds`** in BSON instead of relying on relationship proxies.
- Use **`flatMap`**, **`Mono.zip`**, **`findById`/`findAllById`**, and tenant-scoped queries to fetch references reactively.
- Choose **`$lookup` aggregation** when server-side joining fits the workload.
- Distinguish features that are **unsupported**, have **different APIs**, or are **conditionally supported** across the two stacks.
- Avoid **`block()`**, manual **`subscribe()`**, or calling blocking repositories inside reactive flows.

**Limits of DBRef, Document References, and Sync-Only Features** belongs to the **Reactive access** chapter of the **SPRING_DATA_MONGODB** module. The module scope covers connecting and mapping documents, operating on MongoDB via repositories or `MongoTemplate`, query design, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **`@DBRef`**, **`@DocumentReference`**, **plain reference IDs**, and embedded documents.
2. Explain why **automatic reference reading and dereferencing** must not be expected in reactive mapping.
3. Design entities and DTOs suited to asynchronous reference loading.
4. Write tenant-safe reactive queries, preserve reference order, and handle missing references.
5. Avoid N+1 queries, uncontrolled concurrency, and unbounded memory accumulation.
6. Choose **`$lookup`** or denormalization when appropriate.
7. Identify limitations across **repositories, templates, sessions, AOT, and return types** by Spring Data version.
8. Write integration tests against real MongoDB with **`StepVerifier`**.

## 2. Where Do the Two Spring Data MongoDB Stacks Differ?

An application can contain both API sets during migration, yet they are not directly interchangeable.

| Aspect | Imperative / Blocking | Reactive / Non-Blocking |
| --- | --- | --- |
| Typical Boot dependency | `spring-boot-starter-data-mongodb` | `spring-boot-starter-data-mongodb-reactive` |
| Template | `MongoTemplate` | `ReactiveMongoTemplate` |
| Repository | `MongoRepository` | `ReactiveMongoRepository` |
| Find by ID return | `Optional`/object per API | `Mono<Entity>` |
| Multi-result query | `List`/`Stream`/`Iterable` | `Flux<Entity>` |
| I/O driver | Blocking MongoDB Java Driver | MongoDB Reactive Streams Driver |
| Query execution | Synchronous when method runs/consumes | Publisher usually **lazy**, runs on subscription |
| Transaction participation | `MongoTransactionManager` | `ReactiveMongoTransactionManager` |
| Transaction context | Thread-bound | Reactor Context |
| Automatic reference mapping | `DBRef`/`DocumentReference` support dereferencing | Automatic reference resolution is not supported |

**Reactive is not a toggle activated by putting `Reactive` in front of `Mongo`.** If a component still calls a blocking `MongoRepository`, JDBC, or a synchronous HTTP client on an event loop, requests still block even if the outer return type is `Mono`.

### 2.1. Both Still Use the Same MongoDB Server

Both stacks send commands to the same MongoDB server and share:

- Collections, BSON documents, and indexes.
- MongoDB CRUD and aggregation capabilities exposed by the corresponding driver/API.
- Query/filter semantics, write concerns, and server-side transactions.
- Security, multi-tenancy, and consistency principles.

What differs is **I/O lifecycle and timing, publishers, conversion, and API integration**. Never claim MongoDB Server “cannot join” just because the reactive Java mapping layer lacks an automatic convenience annotation.

### 2.2. Quick Decision Matrix

| Problem | Approach |
| --- | --- |
| Read standalone entity by ID | `ReactiveMongoRepository.findById` |
| Read an entity then fetch a reference by key | `flatMap` + repository/template |
| Read multiple reference IDs | `Query` with `$in` or `findAllById`, then restore order |
| Return combined related data in one pipeline | MongoDB `$lookup` via `ReactiveMongoTemplate` |
| Relationship is always needed, small, and co-mutated | Consider an embedded document |
| Legacy code requiring lazy `@DBRef` proxies | Keep behind a controlled blocking boundary or refactor to IDs |
| Need reactive MongoDB transactions | `ReactiveMongoTransactionManager` / `TransactionalOperator` |
| Need a sync-only convenience feature | Build a dedicated adapter, avoid blocking the event loop, check version docs |

## 3. What Is `@DBRef`?

MongoDB defines a reference storage convention called **DBRef**, represented as a special subdocument containing fields like **`$ref`** and **`$id`**, and optionally **`$db`**.

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

In the Java blocking stack:

~~~java
import org.springframework.data.mongodb.core.mapping.DBRef;

@Document(collection = "orders")
class BlockingOrder {

    @Id ObjectId id;
    String tenantId;

    @DBRef
    CustomerDocument customer;
}
~~~

The Spring Data mapping layer resolves the DBRef by querying the target document. With **`@DBRef(lazy = true)`**, the blocking stack can create a lazy proxy that loads the target only when the caller accesses the property.

### 3.1. DBRef Is Not a Foreign Key

DBRef does not create foreign-key constraints like SQL relations. MongoDB does not automatically:

- Guarantee the referenced Customer document exists.
- Cascade-delete when the Order is deleted.
- Save Customer automatically on `save(Order)`.
- Enforce tenant access control on the referenced target document.

**A reference merely records a link; lifecycle integrity remains the application's responsibility.**

### 3.2. Lazy DBRef in the Blocking Stack

~~~java
@DBRef(lazy = true)
private CustomerDocument customer;
~~~

Code that looks like an ordinary getter:

~~~java
String name = order.getCustomer().getName();
~~~

can trigger a **synchronous** MongoDB query to fetch the Customer. This easily causes hidden I/O, hard-to-spot N+1 queries, and tangled `ClientSession` lifetimes.

Under modern Java and JDK strong encapsulation, lazy proxies can also face class/proxy/reflection restrictions. Never design WebFlux applications assuming the JVM will allow arbitrary lazy DBRef proxies.

## 4. How Does `@DocumentReference` Differ from DBRef?

Spring Data MongoDB also provides **`@DocumentReference`**, storing a more flexible pointer/reference than the DBRef subdocument format.

Blocking entity illustration:

~~~java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "orders")
class BlockingOrder {

    @Id ObjectId id;
    String tenantId;

    @DocumentReference
    CustomerDocument customer;
}
~~~

By default (ID-based), BSON stores:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  customer: ObjectId("507f1f77bcf86cd799439011")
}
~~~

This stores **just a key value**, not a DBRef with `$ref`/`$id`. Even so, the annotation still asks Spring Data to **fetch the target document and map it to `CustomerDocument`** when loading the Order.

### 4.1. Flexibility of Document References

Depending on the Spring Data version, `@DocumentReference` supports options like:

- Target collection/database name.
- Custom **lookup** expressions.
- **sort** for collection references.
- **lazy**.
- Custom document pointers/converters.

These options serve the **mapping layer's dereferencing mechanism**. Never assume reactive infrastructure executes them automatically.

### 4.2. A Plain Pointer vs `@DocumentReference`

If the Java entity declares:

~~~java
ObjectId customerId;
~~~

the property is read as a plain `ObjectId`. The application **explicitly** decides whether and when to query `customers`.

Conversely:

~~~java
@DocumentReference
CustomerDocument customer;
~~~

asks the mapping layer to turn a stored pointer into a target entity, so it is no longer a plain field read.

**Switching `@DBRef` to `@DocumentReference` does not solve reactive reference-reading limitations.**

## 5. Core Limit: Reactive Does Not Automatically Resolve References

Spring Data MongoDB documentation for DBRefs and document references explicitly states that **reading document references is not supported by reactive infrastructure**. Likewise, reactive/Querydsl docs note that **DBRef joins are not supported in Reactive MongoDB**.

This leads to a clear design rule:

> **When reading entities via `ReactiveMongoTemplate`/`ReactiveMongoRepository`, never rely on `@DBRef` or `@DocumentReference` automatically resolving into target entities.**

Do not treat an entity that compiles, saves, or stores a BSON pointer as proof that **reactive reads will populate the referenced object**.

### 5.1. Common Sources of Confusion

**Case A — Saving succeeds, yet reading leaves linked entities unresolved.**

The app saves an Order containing a pointer to a Customer, yet on reactive read the `customer` field is not resolved as expected. That does not mean the target document vanished; inspect raw BSON and check mapping capabilities.

**Case B — Setting `lazy = true` hoping to avoid blocking.**

In the blocking stack, a lazy property can issue synchronous I/O when its getter runs. Reactivity does not become non-blocking just because a property is accessed later.

**Case C — Swapping annotations without changing design.**

`@DocumentReference` changes the BSON format compared to `@DBRef`, yet the underlying issue remains: the mapping converter would need to issue extra reads during conversion.

**Case D — Wrapping a lazy-proxy object in `Mono.just`.**

~~~java
// Mono.just does not make blocking I/O inside the getter reactive.
return Mono.just(blockingOrder.getCustomer().getName());
~~~

Arguments to `Mono.just` evaluate eagerly, so the getter can block right on the calling thread.

### 5.2. A Spring Data Limit Is Not a MongoDB `$lookup` Limit

MongoDB Server still supports **`$lookup`** for joining collections. `ReactiveMongoTemplate` can send an aggregation pipeline containing `$lookup` and stream results as a `Flux`.

Avoid blanket statements like “reactive MongoDB cannot join.” More accurately:

- **Do not expect converters to auto-resolve `@DBRef`/`@DocumentReference` reactively.**
- **Query explicitly through reactive repositories or templates.**
- **Use server-side `$lookup` when data shapes and query costs fit.**

### 5.3. Check Compatibility per Version

Spring Data capabilities evolve across releases. For any specific build, check the documentation for **that exact version**. This lesson teaches a safe pattern that never depends on automatic reference resolution.

## 6. Four Ways to Model Relationships in Reactive MongoDB

| Model | Example BSON | Pros | Considerations |
| --- | --- | --- | --- |
| Embedded | `order.customerSnapshot` | Single read, data co-located with order | Data duplication; snapshot must fit business semantics |
| Plain ID reference | `order.customerId` | Simple mapping, explicit fetching | Service must query Customer explicitly |
| List of ID references | `order.productIds` | Flexible, supports batch `$in` fetch | Must handle ordering and missing IDs |
| Server-side `$lookup` | Pipeline joining orders/products | Consolidates queries and projections | Join cost, indexes, memory, server limits |

**No single choice fits every relationship.** Ask:

1. Do Customer and Product change independently?
2. Should Order preserve historical snapshots or reflect live updates?
3. How large can the reference list in one Order grow?
4. Which APIs genuinely require the joined fields?
5. What tenant, status, and temporal invariants apply?

### 6.1. When Does Embedding Fit?

For shipping addresses or item prices at purchase time, snapshots are usually right:

~~~javascript
{
  orderNo: "ORD-001",
  shippingAddress: {
    recipient: "A",
    city: "Ha Noi"
  },
  items: [
    { sku: "BOOK-101", quantity: 2, priceMinor: NumberLong("120000") }
  ]
}
~~~

A historical order's address or purchase price **should not silently change** when a customer updates their address book or catalog prices change. Embedding is a domain decision, not just a workaround for avoiding DBRef.

### 6.2. When Does an ID Reference Fit?

When you need to navigate from Order to the current live Customer, store `customerId` and query when needed:

~~~javascript
{
  orderNo: "ORD-001",
  tenantId: "shop-a",
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

The key is stored as an ordinary BSON value and requires zero automatic dereferencing by converters.

## 7. Sample Domain Without `@DBRef` / `@DocumentReference`

Define three collections: **customers**, **products**, and **orders**.

~~~javascript
// customers
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  displayName: "Customer A",
  active: true
}
~~~

~~~javascript
// products
{
  _id: ObjectId("507f1f77bcf86cd799439021"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  name: "Spring Data MongoDB",
  active: true
}
~~~

~~~javascript
// orders
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  tenantId: "shop-a",
  customerId: ObjectId("507f1f77bcf86cd799439011"),
  productIds: [ObjectId("507f1f77bcf86cd799439021")],
  status: "PAID"
}
~~~

These are **application-defined BSON key pointers**, not DBRefs. Every Order also carries `tenantId` to enforce query isolation.

### 7.1. Java Entities Using `ObjectId`

~~~java
package com.example.reactiveorders;

import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public record CustomerDocument(
    @Id ObjectId id,
    String tenantId,
    String displayName,
    boolean active
) {}

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    String name,
    boolean active
) {}

@Document(collection = "orders")
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    ObjectId customerId,
    List<ObjectId> productIds,
    String status
) {}
~~~

Each **public record** must live in its own `.java` file per Java rules; they are shown together here for readability.

### 7.2. Do Not Swap `ObjectId` for `String` Carelessly

MongoDB `ObjectId` and `String` look similar when serialized to hex, yet have **different BSON types**. If `Customer._id` is `ObjectId`, querying a plain `String` field with a 24-hex string will not match `ObjectId` documents.

Even if Spring Data auto-converts `@Id String` to `ObjectId` in certain cases, do not assume every `String` reference field receives identical conversion. Match BSON types across IDs and foreign-key fields, or register explicit converters and test them.

### 7.3. Do You Need DBRef to Use `$lookup`?

**No.** `$lookup` joins cleanly on plain fields such as `customerId ↔ _id` or `productIds ↔ _id`. Plain keys are generally simpler for reactive workloads than DBRefs.

## 8. Reactive Repositories: Key-Based Queries

~~~java
package com.example.reactiveorders;

import java.util.Collection;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Mono<OrderDocument> findByIdAndTenantId(
        ObjectId id, String tenantId
    );
}

public interface ReactiveCustomerRepository
        extends ReactiveMongoRepository<CustomerDocument, ObjectId> {

    Mono<CustomerDocument> findByIdAndTenantId(
        ObjectId id, String tenantId
    );
}

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId> {

    Flux<ProductDocument> findByTenantIdAndIdIn(
        String tenantId, Collection<ObjectId> ids
    );
}
~~~

As with the entities, place each public interface in its own source file in a real project.

Adding **`tenantId`** to derived queries provides vital isolation: calling plain `findById` on a target collection could return another tenant's document if a caller knows or guesses an `ObjectId`.

### 8.1. Do Not Expect `customerId()` to Fetch Anything

~~~java
OrderDocument order = ...;
ObjectId customerId = order.customerId();
~~~

`customerId()` **merely returns an `ObjectId`** without hitting the database. If the API needs Customer fields, the service must call `customerRepository` or `ReactiveMongoTemplate` explicitly.

### 8.2. Lazy Publisher Semantics

~~~java
Mono<OrderDocument> order =
    orderRepository.findByIdAndTenantId(id, tenantId);
~~~

This Publisher describes the lookup, which starts upon subscription. Never call a repository method and discard the `Mono` thinking data was loaded, and never call `subscribe()` in a service just to force execution.

## 9. Loading Order + Customer with `flatMap`

Result DTOs:

~~~java
package com.example.reactiveorders;

public record CustomerSummary(
    ObjectId id,
    String displayName
) {}

public record OrderWithCustomer(
    ObjectId id,
    String status,
    CustomerSummary customer
) {}
~~~

Service:

~~~java
package com.example.reactiveorders;

import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderReadService {

    private final ReactiveOrderRepository orders;
    private final ReactiveCustomerRepository customers;

    public OrderReadService(
            ReactiveOrderRepository orders,
            ReactiveCustomerRepository customers) {
        this.orders = orders;
        this.customers = customers;
    }

    public Mono<OrderWithCustomer> read(
            ObjectId orderId,
            String authenticatedTenantId) {

        return orders.findByIdAndTenantId(
                orderId, authenticatedTenantId)
            .flatMap(order ->
                customers.findByIdAndTenantId(
                        order.customerId(), authenticatedTenantId)
                    .map(customer ->
                        new OrderWithCustomer(
                            order.id(),
                            order.status(),
                            new CustomerSummary(
                                customer.id(), customer.displayName()
                            )
                        )
                    )
            );
    }
}
~~~

**How it works:**

1. Fetch the tenant-scoped Order.
2. When emitted, read **`customerId`** from the Order.
3. Query Customer within the same tenant using a second `Mono`.
4. Combine both results into the DTO.
5. If either Order or Customer is missing, this basic pipeline completes empty; services should define explicit contracts for each case.

### 9.1. Handling Missing References

Never let **`Mono.empty()`** silently look like “Order does not exist” when the Customer was actually deleted or inaccessible due to tenant mismatch. Emit explicit domain errors:

~~~java
return orders.findByIdAndTenantId(orderId, tenantId)
    .switchIfEmpty(Mono.error(new OrderNotFoundException()))
    .flatMap(order ->
        customers.findByIdAndTenantId(
                order.customerId(), tenantId)
            .switchIfEmpty(
                Mono.error(new MissingReferenceException(
                    "Customer unavailable")))
            .map(customer -> toDto(order, customer))
    );
~~~

`OrderNotFoundException`, `MissingReferenceException`, and `toDto` are illustrative application components to define separately. Whether a missing reference should error, return `null`, or use a fallback depends on the API contract.

### 9.2. When Only a Subset of Customer Fields Is Needed

If callers only need `displayName`, avoid fetching addresses, permissions, or preferences. Consider a projection DTO or `Query.fields().include(...)` to cut payload size and avoid exposing sensitive fields.

### 9.3. `flatMap` Does Not Create a Transaction

Two reads chained via `flatMap` **do not automatically run inside one transaction or snapshot**. The Customer could change or be deleted between reads. When strict consistency is required, configure transactions, read concern, or snapshots rather than treating a Reactor chain as atomic.

## 10. `Mono.zip`: When Queries Are Independent

When all target IDs are already known, combine independent Publishers:

~~~java
Mono<CustomerDocument> customer =
    customerRepository.findByIdAndTenantId(customerId, tenantId);

Mono<ProductDocument> product =
    productRepository.findById(productId);

Mono.zip(customer, product)
    .map(tuple -> new OverviewDto(
        tuple.getT1().displayName(),
        tuple.getT2().name()
    ));
~~~

`OverviewDto` is an illustrative DTO; scope product lookups by tenant too in multi-tenant APIs. **`Mono.zip`** is great when two Publishers are independent, yet never use it to skip authorization or treat two separate reads as a consistent snapshot.

### 10.1. `Mono.zip` with Empty Sources

If either `Mono` completes empty, **`Mono.zip` completes empty** without producing a DTO. To handle missing references explicitly, attach `switchIfEmpty` to each source before zipping.

### 10.2. Never Combine Results Using `block()`

~~~java
// Avoid in WebFlux/reactive services.
CustomerDocument customer = customerRepository
    .findById(customerId)
    .block();
~~~

`block()` turns waiting for I/O into a synchronous wait; on event loops it stalls requests or throws exceptions.

### 10.3. Do Not Abuse `subscribe()`

~~~java
// Do not do this to assign Customer asynchronously to a mutable field.
customerRepository.findById(customerId)
    .subscribe(customer -> order.setCustomer(customer));
return Mono.just(order);
~~~

`Mono.just(order)` can emit **before** the `subscribe` callback executes, and spawns a detached subscription with no cancellation/error linkage. Always **return the `flatMap`/`map` chain** so the caller owns a single subscription.

## 11. An Order with Many `productIds`: Batch Lookup Instead of N+1

Given an Order:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  tenantId: "shop-a",
  productIds: [
    ObjectId("507f1f77bcf86cd799439021"),
    ObjectId("507f1f77bcf86cd799439022"),
    ObjectId("507f1f77bcf86cd799439023")
  ]
}
~~~

The naive approach queries one ID at a time:

~~~java
Flux<ProductDocument> products = Flux
    .fromIterable(order.productIds())
    .concatMap(productId ->
        productRepository.findById(productId)
    );
~~~

If an Order holds **N `productIds`**, this sends **N MongoDB queries**. Worse, unscoped `findById` risks reading another tenant's product.

### 11.1. Batching All IDs in One Query

Repository:

~~~java
Flux<ProductDocument> findByTenantIdAndIdIn(
    String tenantId,
    Collection<ObjectId> ids
);
~~~

Service:

~~~java
return orderRepository.findByIdAndTenantId(orderId, tenantId)
    .flatMap(order ->
        productRepository
            .findByTenantIdAndIdIn(
                tenantId, order.productIds())
            .collectList()
            .map(products -> toOrderDetails(order, products))
    );
~~~

`toOrderDetails` is an application DTO mapper. Equivalent MongoDB query:

~~~javascript
db.products.find({
  tenantId: "shop-a",
  _id: { $in: [productIdA, productIdB, productIdC] }
});
~~~

**Benefits:** a single query to `products` fetches all matching IDs, leveraging `_id`'s unique index while enforcing tenant scoping.

### 11.2. Keep `collectList` Explicitly Bounded

**`collectList()`** holds every product result for that Order in RAM. This is safe when products per Order are capped by business rules (e.g., at most 50 or 100 IDs).

Never call `collectList` on a `Flux` that could emit millions of products or an unbounded change stream. For very large sets, chunk queries or design memory-bounded aggregations.

### 11.3. Duplicate IDs, Missing IDs, and Ordering

An **`$in` query** does not guarantee returning products in the order listed in `productIds`. Furthermore:

- Repeated IDs in `productIds` may carry quantity/line semantics.
- A deleted Product will be omitted from `$in` results.
- A Product belonging to another tenant is excluded by the tenant filter.
- An inactive Product might need exclusion or preservation depending on historical order rules.

Never return the `List` of products in whatever order MongoDB returned them assuming it matches the Order's item positions.

## 12. Restoring Reference Order with an Explicit DTO

API responses normally need line items in the Order's original sequence. To avoid depending on `$in` return order, index loaded products by ID and iterate over the original ID list.

~~~java
package com.example.reactiveorders;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.bson.types.ObjectId;

public record ProductSummary(
    ObjectId id,
    String sku,
    String name
) {}

public record OrderDetails(
    ObjectId id,
    String status,
    List<ProductSummary> products
) {}

public final class OrderDetailsMapper {

    private OrderDetailsMapper() {}

    public static OrderDetails map(
            OrderDocument order,
            List<ProductDocument> loaded) {

        Map<ObjectId, ProductDocument> byId = new HashMap<>();
        for (ProductDocument product : loaded) {
            byId.put(product.id(), product);
        }

        List<ProductSummary> ordered = new ArrayList<>();
        for (ObjectId id : order.productIds()) {
            ProductDocument product = byId.get(id);

            if (product == null) {
                throw new IllegalStateException(
                    "A referenced product is missing or inaccessible");
            }

            ordered.add(new ProductSummary(
                product.id(),
                product.sku(),
                product.name()
            ));
        }

        return new OrderDetails(
            order.id(),
            order.status(),
            List.copyOf(ordered)
        );
    }
}
~~~

Place each public record/class in its own `.java` file in real projects. Flow above:

1. Query products by **tenantId + ID set**.
2. Build an ID → document lookup map.
3. Walk `order.productIds()` in original order to restore sequence.
4. Detect missing or cross-tenant documents.
5. Return an explicit DTO.

### 12.1. Duplicate References

If `productIds` lists the same ID twice, the loop emits two `ProductSummary` entries. If Orders can hold multiple lines for the same SKU with distinct quantities, store structured **order items** (`productId`, `quantity`, `priceAtOrder`) rather than a raw ID array.

### 12.2. Missing-Reference Policies

Choose an explicit contract:

- **Strict:** any missing reference fails with an integrity error.
- **Tolerant:** substitute an “unavailable” marker preserving the original ID.
- **Snapshot:** render embedded product details saved at order creation instead of requiring the live Product.

Never assume a missing lookup means the Product does not exist when a **tenant filter** blocked access. Public errors must never disclose cross-tenant existence.

### 12.3. Why Use DTOs?

DTOs decouple **stored documents** from **API response models**. Never attach fetched `ProductDocument`s onto a transient field of `OrderDocument` and then call `repository.save(order)` where mapping might persist unintended data.

## 13. ReactiveMongoTemplate: Explicit BSON Paths and Projections

When you don't want to declare derived repository methods for every filter variation:

~~~java
import java.util.Collection;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public Flux<ProductDocument> loadProducts(
        ReactiveMongoTemplate template,
        String tenantId,
        Collection<ObjectId> productIds) {

    if (tenantId == null || tenantId.isBlank()) {
        return Flux.error(
            new IllegalArgumentException("Tenant required"));
    }

    if (productIds == null || productIds.isEmpty()) {
        return Flux.empty();
    }

    Query query = Query.query(
        Criteria.where("tenantId").is(tenantId)
            .and("_id").in(productIds)
    );

    query.fields()
        .include("_id")
        .include("tenantId")
        .include("sku")
        .include("name")
        .include("active");

    return template.find(query, ProductDocument.class);
}
~~~

This is an **explicit reactive find**. There is no `@DBRef`, no `@DocumentReference`, and no lazy proxy.

### 13.1. Java/BSON Mapping

If `ProductDocument` uses **`@Field("tenant_id")`**, typed template queries map the Java property `tenantId` to the corresponding BSON field. In raw `Document` queries, always use physical BSON names rather than assuming automatic `Criteria` entity mapping.

### 13.2. Projections and Saving Partial Entities

Queries using `Query.fields()` populate only projected fields, leaving excluded fields at defaults/null in `ProductDocument`. **Never save a partially loaded entity back to MongoDB**, or you risk wiping fields.

When building read views, prefer projection DTOs over treating partially populated entities as complete.

### 13.3. Indexes

MongoDB maintains a default unique index on **`_id`**, so `$in` lookups over `ObjectId`s perform well when the ID list is small. A compound index on `(tenantId, _id)` isn't always superior; verify with **`explain`** on real workloads.

When joining by a non-`_id` business key such as `sku`, ensure an appropriate index and uniqueness scope within the tenant.

## 14. N+1 Queries When Reading Many Orders from a Flux

Reading 1 Order then 1 Customer issues two queries—often fine. Reading 1,000 Orders and calling `customerRepository` for each triggers N+1 queries:

~~~java
Flux<OrderWithCustomer> data =
    orderRepository.findAll()
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> toDto(order, customer))
        );
~~~

Beyond N+1, there are three bugs here:

- **`findAll()` lacks a tenant filter**, exposing all orders.
- **`findById()` lacks a tenant filter** on Customers.
- **Unbounded `flatMap()` concurrency** can blast too many simultaneous queries if upstream emits rapidly.

### 14.1. Minimum Fix: Tenant Filter and Bounded Concurrency

~~~java
Flux<OrderWithCustomer> data =
    orderRepository.findByTenantId(tenantId)
        .flatMap(
            order -> customerRepository
                .findByIdAndTenantId(order.customerId(), tenantId)
                .map(customer -> toDto(order, customer)),
            8
        );
~~~

This assumes `findByTenantId(String)` and `toDto` exist. `concurrency=8` is an illustrative cap to tune against pool sizes, load, and DB capacity.

**This does not eliminate N+1**—it merely bounds simultaneous queries and enforces tenant isolation.

### 14.2. `flatMap` vs `concatMap`

| Operator | Behavior |
| --- | --- |
| `flatMap` | Subscribes to multiple inner Publishers concurrently; output order is not guaranteed |
| `concatMap` | Executes inner Publishers sequentially; preserves input order with lower throughput |
| `flatMapSequential` | Executes concurrently while buffering to emit in input order |

Never choose an operator purely by “which is faster.” Decide ordering, concurrency, and memory requirements first, then benchmark.

### 14.3. Page-Level Batching

A cleaner approach for paginated APIs:

1. Load a **bounded page of Orders** for the tenant.
2. Extract unique `customerId`s from that page.
3. Query Customers with **`$in`** and the same tenant.
4. Index Customers into a `Map` by ID.
5. Assemble DTOs preserving the sorted Order sequence.

For pages of 20–50 Orders, buffering **one small page** is reasonable and slashes round trips. Never collect an entire historical collection into an unbounded `List` just to dodge N+1.

### 14.4. Caching Customers by ID?

Caching reduces repeated lookups, provided cache keys include **`tenantId + customerId`** along with TTL/invalidation and authorization rules. Never cache globally by `customerId` alone if keys or access rules could span tenants.

## 15. When Is `$lookup` Better Than Multiple Client-Side Queries?

**`$lookup`** is MongoDB Server's aggregation stage for joining related collections. It requires no Java converter resolving DBRefs.

Goal: read an Order by ID + tenant along with its Customer in the same tenant.

~~~javascript
db.orders.aggregate([
  {
    $match: {
      _id: ObjectId("507f1f77bcf86cd799439031"),
      tenantId: "shop-a"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        cid: "$customerId",
        owner: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$owner"] }
              ]
            }
          }
        },
        {
          $project: {
            displayName: 1
          }
        }
      ],
      as: "customerRows"
    }
  },
  {
    $unwind: {
      path: "$customerRows",
      preserveNullAndEmptyArrays: false
    }
  },
  {
    $project: {
      _id: 1,
      status: 1,
      customerName: "$customerRows.displayName"
    }
  }
]);
~~~

### 15.1. Why Does the Lookup Filter by Tenant?

Joining on `customerId` alone could leak data if an Order held a corrupted pointer to another tenant's Customer. The pipeline enforces:

\[
\text{customers.\_id}=\text{orders.customerId}
\quad \land \quad
\text{customers.tenantId}=\text{orders.tenantId}.
\]

**`$lookup` does not enforce authorization automatically.** Apply tenant filters on both the root collection and the joined target pipeline.

### 15.2. `preserveNullAndEmptyArrays = false`

When no Customer matches, `$unwind` with `preserveNullAndEmptyArrays: false` drops the Order from results—giving **inner join semantics**. If the API should still return the Order with a missing Customer, set preserve accordingly and handle `null` in the DTO.

### 15.3. `$lookup` vs Lazy Loading

`$lookup` runs as **one aggregation command** across server-side stages. The reactive Java client receives results via a Publisher without lazy property proxies.

Server-side joins still carry significant cost. Inspect **`executionStats`**, root document counts, target indexes, memory, and latency before replacing two simple queries with `$lookup`.

## 16. `$lookup` with `ReactiveMongoTemplate`

A controlled approach uses **`AggregationOperation`** to define BSON stages passed to `ReactiveMongoTemplate.aggregate`:

~~~java
import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import reactor.core.publisher.Mono;

public Mono<Document> readOrderCustomer(
        ReactiveMongoTemplate template,
        ObjectId orderId,
        String tenantId) {

    AggregationOperation match = ctx ->
        new Document("$match",
            new Document("_id", orderId)
                .append("tenantId", tenantId));

    Document customerMatch = new Document("$expr",
        new Document("$and", List.of(
            new Document("$eq", List.of("$_id", "$$cid")),
            new Document("$eq", List.of("$tenantId", "$$owner"))
        )));

    AggregationOperation lookup = ctx ->
        new Document("$lookup",
            new Document("from", "customers")
                .append("let",
                    new Document("cid", "$customerId")
                        .append("owner", "$tenantId"))
                .append("pipeline", List.of(
                    new Document("$match", customerMatch),
                    new Document("$project",
                        new Document("displayName", 1))
                ))
                .append("as", "customerRows"));

    AggregationOperation unwind = ctx ->
        new Document("$unwind",
            new Document("path", "$customerRows")
                .append("preserveNullAndEmptyArrays", false));

    AggregationOperation project = ctx ->
        new Document("$project",
            new Document("_id", 1)
                .append("status", 1)
                .append("customerName",
                    "$customerRows.displayName"));

    Aggregation pipeline = Aggregation.newAggregation(
        match, lookup, unwind, project);

    return template.aggregate(
        pipeline, "orders", Document.class
    ).next();
}
~~~

**Note:** raw `Document` stages use **physical BSON field names**, without automatic translation of Java `@Field` names as entity-typed builders provide. This example assumes `tenantId`, `customerId`, and `displayName` match the BSON names shown earlier.

### 16.1. Never Assume Every `$lookup` Uses Indexes Optimally

`$lookup` pipelines with **`$expr`** and **`let`** follow version-dependent MongoDB index rules based on operators and data shapes. Never assume `$expr` lookups match simple `_id` `find` performance; run `explain` on real data.

### 16.2. Order of `productIds` After `$lookup`

When joining an array like `productIds`, `$lookup` output **does not automatically preserve the array's original order**. To preserve order, either use array operators in the pipeline or restore order in Java using an ID → Product map as in section 12.

### 16.3. `$lookup` Does Not Replace Transactions

`$lookup` combines data for a read pipeline; it does not make separate writes transactional. Configure read concerns/snapshots if point-in-time consistency is required.

## 17. Choosing Between Two Queries and `$lookup`

| Criterion | Service `flatMap` / Batch Lookup | Server-Side `$lookup` |
| --- | --- | --- |
| Java logic flexibility | High; easy business rules and fallbacks | Join/filter logic lives inside pipeline |
| Network round trips | 2 or more; reducible via batching | Usually one aggregation command (potentially multiple batches) |
| Mapping | Explicit Java DTOs | Aggregation projection / DTO |
| Tenant policy | Filter on each query | Filter both root and lookup pipeline |
| N+1 risk | Yes if looping per ID; mitigated by batching | Avoids client-side query loops, though server still executes joins |
| Reference ordering | Restored easily in Java | Requires `$sort`/`$map`/array pipeline logic |
| Query plan | Easy to explain per query | Must inspect full pipeline explain |
| Best fit | Few references, explicit business rules | Read models/reports joining multiple fields centrally |

“$lookup is always faster than two queries” is false. If Customers are cached, `$lookup` can cost more. Conversely, if an API only needs a Customer name alongside Order fields, a concise pipeline can beat multiple round trips.

## 18. Actively Avoid Blocking I/O in Converters and Callbacks

A tempting workaround when `@DBRef` isn't supported is writing a **`@ReadingConverter`** or entity callback that calls a blocking repository to load the reference:

~~~java
// Anti-pattern: never perform blocking MongoDB I/O inside a converter.
public OrderDocument convert(Document raw) {
    OrderDocument order = ...;
    CustomerDocument customer =
        blockingCustomerRepository.findById(...).orElseThrow();
    return order;
}
~~~

Converters run during document materialization; if one blocks, the reactive driver stalls until it finishes before emitting the item. Consequences:

- Forfeits non-blocking I/O benefits.
- Can block event-loop or driver execution threads.
- Creates hidden N+1 queries invisible to the service layer.
- Breaks error, cancellation, and transaction context propagation.

### 18.1. What Should Converters Do?

Converters are meant for **pure in-memory data transformations** such as:

- Mapping BSON string codes to enums.
- Mapping embedded value objects.
- Normalizing structures already inside the document.

**Never** turn converters into I/O-performing repositories or services.

### 18.2. Entity Lifecycle Callbacks Do Not Replace Reactive Composition

Never call `subscribe()` inside a callback to fetch references and mutate the entity. Detached subscriptions lack linkage to the primary publisher's lifecycle and errors, risking partially populated entities reaching consumers.

Build composite read models explicitly in services using `flatMap`/`zip` or aggregations.

## 19. Deep Relationship Graphs: Avoiding Nested N+1 Chains

Consider:

~~~text
Order
  -> Customer
      -> DefaultAddress
  -> Products[]
      -> Categories[]
~~~

If every relationship getter queries the database, loading one Order triggers dozens or hundreds of queries. Reactivity does not make those round trips disappear.

### 19.1. Design Endpoint-Specific Read Models

An Order detail endpoint rarely needs every Category, Supplier, Customer preference, and warehouse stock figure. Identify **the exact fields needed by the response** before designing fetches.

Example:

~~~java
public record OrderDetailView(
    ObjectId orderId,
    String customerName,
    List<ProductSummary> items
) {}
~~~

Rather than returning an entire entity graph like JPA hoping serialization avoids lazy queries, assemble an explicit DTO.

### 19.2. Bound Reference Counts

An Order holding 100,000 `productIds` signals a schema problem:

- BSON document size limits.
- Heap spikes under `collectList`.
- Oversized `$in` queries.
- Join and serialization overhead.
- Whether `order_items` should be its own paginated collection.

Never load unbounded ID lists inside a single WebFlux request.

### 19.3. Never Serialize Raw Entity Graphs Directly

Passing entities loaded with rich references or mutable fields straight to JSON serializers can:

- Trigger lazy loading in blocking stacks.
- Over-expose internal fields.
- Accidentally leak fields from unchecked references.
- Cause circular reference errors on cyclic graphs.

Explicit DTOs provide a strong data boundary in both sync and reactive architectures.

## 20. Consistency and Transactions When Reading References

Suppose an Order is read right before a Product is deleted prior to the Product query:

~~~text
T0: read Order.productIds = [P1, P2]
T1: another service deletes P2
T2: products query ({_id: {$in: [P1, P2]}}) returns only P1
~~~

This is not a Reactor bug. **Two separate queries do not automatically share a snapshot.**

### 20.1. When True Snapshot Consistency Is Required

When business rules require multi-document consistency:

- Ensure a transaction-capable MongoDB topology.
- Use **`ReactiveMongoTransactionManager`** for reactive transactions.
- Compose all queries in one reactive chain with appropriate read concern/transaction options.
- Keep transactions short; never hold them open across long HTTP streaming responses.

Configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveTransactionsConfig {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager mongoTx(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

Usage:

~~~java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager",
    readOnly = true
)
public Mono<OrderDetails> readConsistentOrder(...) {
    // Return one Publisher composing all related queries.
    return ...;
}
~~~

This illustrates the **transaction boundary**, not a complete implementation. `readOnly` metadata in Spring Data MongoDB can still start a server transaction; verify read concerns and resource costs for your exact version.

### 20.2. Do Not Confuse the Session API with `@Transactional`

Spring Data MongoDB distinguishes:

- **Manual `ClientSession`** on the reactive template (`withSession`).
- **Managed transactions** via `ReactiveMongoTransactionManager` bound to Reactor Context.

Documentation notes that **explicit reactive `ClientSession` integration is scoped to the Template API, rather than a direct manual session API on reactive repositories**. That **does not mean** `ReactiveMongoRepository` cannot participate in transactions managed by the reactive transaction manager.

Never call `template.withSession(...)` expecting repository calls outside that callback to inherit that manual session automatically.

### 20.3. When Are Order Snapshots Sufficient?

For transaction history, embedding `customerName`, `productName`, or `priceAtOrder` directly in the Order is often superior to querying live Customer/Product documents. Base the model on business correctness, not merely reactive convenience.

## 21. Identifying API Limits and Differences Accurately

Avoid sweeping claims about “everything reactive lacks.” Many features exist in reactive form under different class names or return types. The table below classifies features directly tied to this lesson.

| Feature / Pattern | Blocking API | Reactive API / Limitation |
| --- | --- | --- |
| Auto-reading `@DBRef` target | DBRef mapping and conditional lazy proxies | **No equivalent DBRef join resolution** |
| Auto-reading `@DocumentReference` target | Pointer/lookup-based reference mapping | **Reading document references is not supported by reactive infrastructure** in current docs |
| Plain ID pointers | Read ID then fetch manually | **Supported**; use `Mono`/`Flux` and explicit queries |
| `$lookup` aggregation | `MongoTemplate.aggregate` | **Supported** via `ReactiveMongoTemplate.aggregate` |
| Java `Stream` from cursor | `Stream<T>`, must close | Use **`Flux<T>`** with subscription/cancellation |
| Automatic `Page<T>` from reactive repository | Sync repositories can return `Page` | **`Mono<Page<T>>` is not supported** as a reactive repository return type |
| `Pageable` on `find` queries | Supported | **Supported as a parameter** for sort/skip/limit, returning `Flux` |
| `GeoPage` / `GeoResults` | Pre-aggregated geo result types for sync use | Do not treat precomputed containers like `GeoPage` as reactive streams; check version API |
| Explicit `ClientSession` `withSession` | `MongoTemplate` API | `ReactiveMongoTemplate` API; **no matching manual session API on reactive repositories** |
| Managed transactions | `MongoTransactionManager` | **`ReactiveMongoTransactionManager`** supported |
| Querydsl predicates | `QuerydslPredicateExecutor` | **`ReactiveQuerydslPredicateExecutor` is supported in current releases** |
| GridFS | `GridFsTemplate` | **`ReactiveGridFsTemplate`** supported |
| Bulk updates | `BulkOperations` | **`ReactiveBulkOperations`** supported in compatible versions |
| Change streams / tailable cursors | Sync APIs or integrations | Reactive APIs supported; not sync-only |
| Repository AOT optimizations | Certain query methods supported by AOT | Spring Data repository AOT docs note **reactive repository interfaces are not yet supported by AOT repository optimizations** in corresponding releases |

### 21.1. Why Track Exact Versions?

Older Spring Data MongoDB articles may claim reactive Querydsl is unsupported, whereas current releases provide **`ReactiveQuerydslPredicateExecutor`**. Likewise, bulk, session, AOT, and overload APIs evolve over time.

When documenting architecture decisions:

1. Record the Spring Boot version.
2. Record the actual Spring Data MongoDB version.
3. Record the MongoDB Reactive Streams Driver and Server versions.
4. Consult the API reference for that exact release.
5. Write integration tests proving the features your service relies upon.

**Never rely on years-old blog posts for absolute claims about current releases.**

### 21.2. Distinguish “Unsupported” from “Do Not Do”

- **Unsupported**: automatic document-reference reading in reactive mapping lacks support per official docs.
- **Different API**: `ReactiveMongoTemplate.aggregate` instead of `MongoTemplate.aggregate`; `Flux` instead of `Stream`.
- **Do not do**: calling a blocking repository on the event loop even though it compiles.
- **Conditional**: AOT support, session integration, transaction propagation, and index APIs depend on version and topology.

These are distinct constraints—never lump them together as “ReactiveMongoDB can't do anything.”

## 22. `Page`, `Slice`, `Flux`, and Return Types

A blocking repository can declare:

~~~java
Page<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
~~~

Reactive repositories do not directly support **`Mono<Page<OrderDocument>>`** to fetch content + total automatically like imperative `Page`.

Instead:

~~~java
Flux<OrderDocument> findByTenantId(
    String tenantId, Pageable pageable);
~~~

`Pageable` still pushes sort, skip, and limit to MongoDB, returning a `Flux` of the page's documents.

### 22.1. When an API Truly Needs Total Count?

Compose two explicit queries:

~~~java
Mono<List<OrderDocument>> content = orderRepository
    .findByTenantId(tenantId, pageable)
    .collectList();

Mono<Long> total =
    orderRepository.countByTenantId(tenantId);

return Mono.zip(content, total)
    .map(tuple -> new PageResponse<>(
        tuple.getT1(),
        tuple.getT2(),
        pageable.getPageNumber(),
        pageable.getPageSize()
    ));
~~~

`PageResponse` is an application DTO, and **`countByTenantId`** is a derived repository method you declare. This adds an extra count query, and the two queries do not automatically share a snapshot.

### 22.2. When Exact Totals Are Unnecessary

Returning a **`Slice`-style response** or cursor/keyset continuation token avoids counting the entire collection. A common technique fetches up to **`pageSize + 1`** rows to determine whether a next page exists, writing explicit queries and limits.

Never assume calling `collectList` on an arbitrary `Flux` constructs a valid `Page`.

### 22.3. `GeoPage` and `GeoResults`

Blocking container types like **`GeoPage`** or **`GeoResults`** eagerly package aggregates/averages that do not match reactive streaming contracts. Reactive geo queries normally work with individual **`GeoResult<T>`** emissions in a `Flux` or custom DTOs, depending on version.

Do not conclude **reactive lacks geospatial queries**—the limitation is in eager aggregate containers and deferred result representation.

## 23. Querydsl, GridFS, Bulk: Stop Calling Them Sync-Only

These capabilities have reactive equivalents in modern Spring Data:

### 23.1. Reactive Querydsl

~~~java
import org.springframework.data.querydsl.ReactiveQuerydslPredicateExecutor;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

interface ReactiveProductSearchRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId>,
                ReactiveQuerydslPredicateExecutor<ProductDocument> {
}
~~~

With a generated Q-type from a compatible annotation processor:

~~~java
QProductDocument product = QProductDocument.productDocument;

Flux<ProductDocument> rows =
    repository.findAll(
        product.sku.startsWith("BOOK")
    );
~~~

`QProductDocument` is an illustrative generated class; exact naming depends on package, class, and processor settings. **Reactive Querydsl only solves typed predicates**—it does not enable DBRef joins in reactive mapping.

### 23.2. Reactive GridFS

Spring Data provides **`ReactiveGridFsTemplate`** for storing and reading GridFS files reactively using Publishers, separate from synchronous `GridFsTemplate`.

Not every synchronous helper on `GridFsTemplate` has an identical reactive overload—check the API before use.

### 23.3. Reactive Bulk Operations

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Mono<?> result = reactiveTemplate
    .bulkOps(
        BulkOperations.BulkMode.ORDERED,
        ProductDocument.class
    )
    .updateOne(
        Query.query(Criteria.where("sku").is("BOOK-101")),
        new Update().set("active", false)
    )
    .execute();
~~~

**`ReactiveBulkOperations`** exists in compatible releases; note that bulk operations bypass some entity callbacks and `@Version` checks compared to `save`. Never equate bulk semantics with `repository.save` or single-document optimistic locking.

### 23.4. Change Streams and Tailable Cursors

Reactive MongoDB exposes `Flux` streams for change streams and tailable queries on supporting topologies. These publishers can run indefinitely, meaning they should never be materialized into a `List`.

**Never call `collectList()` on an unbounded publisher** expecting it to finish.

## 24. Mixing Sync and Reactive: Technical Boundaries

An application can include both starters and both MongoDB clients. However, **`MongoTemplate`** and **`ReactiveMongoTemplate`** do not share session or transaction context merely by pointing to the same URI.

~~~java
// Anti-pattern: blocking MongoRepository inside a reactive handler.
public Mono<OrderDetails> load(ObjectId id) {
    OrderDocument order = blockingOrderRepository
        .findById(id).orElseThrow();

    return Mono.just(convert(order));
}
~~~

The blocking repository call runs **before the `Mono` is even returned**, potentially right on the HTTP event loop, introducing unpredictable latency.

### 24.1. When You Must Call a Legacy Blocking API

During migration, isolate blocking I/O onto a suitable scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<LegacyResult> callLegacy(ObjectId id) {
    return Mono.fromCallable(() ->
            legacyBlockingService.load(id)
        )
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

**`boundedElastic` does not make MongoDB calls non-blocking**. It merely moves blocking work off the event loop onto a bounded thread pool, still consuming threads and connections. This is a **transitional measure**, not a way to do reactive `@DBRef` dereferencing.

### 24.2. Never Expect Transaction Context to Span Two Drivers

If a reactive `@Transactional` method invokes synchronous `MongoTemplate` via `boundedElastic`, the synchronous call **does not automatically join** `ReactiveMongoTransactionManager`. Design separate consistency boundaries or consolidate transactional writes onto a single stack.

### 24.3. `ThreadLocal` Is Not Reactor Context

In imperative transactions, sessions attach to threads. In reactive transactions, context follows the Publisher/Subscriber chain. Never read a `ThreadLocal` populated by a synchronous HTTP filter assuming it stays intact across `publishOn`/`subscribeOn`.

### 24.4. Never Run Heavy Work Inside `map`

~~~java
return products.findAll()
    .map(product ->
        blockingPricingService.calculate(product));
~~~

If `calculate` performs blocking I/O, it stalls the event loop. Replace it with a reactive pricing API composed via `flatMap`, or isolate on a proper executor until migrated.

## 25. Migrating from `@DBRef` to IDs in a Reactive Architecture

A legacy collection may store DBRefs:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  customer: {
    $ref: "customers",
    $id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

Target schema:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439031"),
  customerId: ObjectId("507f1f77bcf86cd799439011")
}
~~~

**Changing Java annotations alone will not convert legacy BSON documents.** Those are two distinct storage formats requiring an explicit migration plan.

### 25.1. Recommended Migration Process

1. **Audit real schema:** sample legacy BSON and list all `@DBRef`/`@DocumentReference` usages.
2. **Standardize ID types:** `ObjectId`, `String`, `UUID`, or custom keys; eliminate ambiguous conversions.
3. **Add new fields** like `customerId`/`productIds` to entities and schemas.
4. **Batch backfill** from `DBRef.$id` or legacy pointers into the new ID fields.
5. **Audit missing/orphaned links**: references pointing to deleted documents, wrong tenants, or unexpected collections.
6. **Controlled dual reads** during cutover if backward compatibility is required.
7. **Switch write paths** to plain IDs (or short-lived dual writes with a consistency plan).
8. **Switch read paths** to explicit reactive fetches or `$lookup`.
9. **Compare outputs** between legacy blocking endpoints and new reactive endpoints on test data.
10. **Cut over cleanly**, removing `@DBRef` dependencies once verified with a rollback plan.

### 25.2. Backfilling a DBRef into an `ObjectId`

When DBRef fields follow a uniform shape, a `mongosh` migration concept looks like:

~~~javascript
db.orders.updateMany(
  {
    customerId: { $exists: false },
    customer: { $type: "object" }
  },
  [
    {
      $set: {
        customerId: {
          $getField: {
            field: { $literal: "$id" },
            input: "$customer"
          }
        }
      }
    }
  ]
);
~~~

**This illustrates an idea on sample data, not a copy-paste production script.** `$getField` requires MongoDB 5.0+, and `$literal` is needed because DBRef's **`$id`** key starts with `$`. Checking `customer: { $type: "object" }` alone does not prove every object is a valid DBRef: audit data first, verify `$id` BSON types, rehearse on a staging copy, and resolve missing or malformed records before rollout. Dynamic document references can store entirely different structures.

### 25.3. What If `@DocumentReference` Already Stores an `ObjectId` Directly?

When legacy BSON looks like:

~~~javascript
{ customer: ObjectId("507f1f77bcf86cd799439011") }
~~~

you may only need to rename the field or align the Java property name. Still, custom lookups or document pointers can store **complex `Document`s**, so never assume every `@DocumentReference` is a plain `ObjectId`.

### 25.4. Migration Must Preserve Tenant Boundaries

During backfills, never assume an existing target ID is valid to expose. Verify the referenced Customer belongs to **the same tenant** or satisfies an explicit cross-tenant sharing policy. If legacy data contains cross-tenant links, clean or classify them before enabling new reactive APIs.

## 26. Integration Testing: Explicit References with `ReactiveMongoRepository`

An integration test should prove:

- Orders save with `customerId` without `@DBRef`.
- The service loads Order and then Customer via reactive repositories.
- Every query enforces tenant filtering.
- The Publisher completes and returns the expected DTO.

### 26.1. `@DataMongoTest` and `StepVerifier` Example

~~~java
package com.example.reactiveorders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
class ReactiveReferenceIntegrationTest {

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveOrderRepository orders;
    @Autowired ReactiveCustomerRepository customers;

    @Test
    void loadsCustomerExplicitlyByIdAndTenant() {
        String tenant = "TEST-" + UUID.randomUUID();
        ObjectId customerId = new ObjectId();
        ObjectId orderId = new ObjectId();

        CustomerDocument customer = new CustomerDocument(
            customerId, tenant, "Customer A", true
        );

        OrderDocument order = new OrderDocument(
            orderId,
            tenant,
            customerId,
            List.of(),
            "PAID"
        );

        Mono<OrderWithCustomer> scenario = template
            .insert(customer)
            .then(template.insert(order))
            .then(orders.findByIdAndTenantId(orderId, tenant))
            .flatMap(savedOrder ->
                customers.findByIdAndTenantId(
                        savedOrder.customerId(), tenant)
                    .map(savedCustomer ->
                        new OrderWithCustomer(
                            savedOrder.id(),
                            savedOrder.status(),
                            new CustomerSummary(
                                savedCustomer.id(),
                                savedCustomer.displayName()
                            )
                        )
                    )
            );

        StepVerifier.create(scenario)
            .assertNext(view -> {
                assertThat(view.id()).isEqualTo(orderId);
                assertThat(view.status()).isEqualTo("PAID");
                assertThat(view.customer().id())
                    .isEqualTo(customerId);
                assertThat(view.customer().displayName())
                    .isEqualTo("Customer A");
            })
            .verifyComplete();
    }
}
~~~

This assumes a **Spring Boot test slice with reactive Mongo infrastructure**, `reactor-test`/JUnit/AssertJ, and a dedicated test MongoDB instance. Verify `@DataMongoTest` package and scanning configuration for your exact Spring Boot version.

### 26.2. Why Is `@DBRef` Unnecessary?

Customer is fetched explicitly via:

~~~java
customers.findByIdAndTenantId(
    savedOrder.customerId(), tenant
);
~~~

This is a MongoDB query expressed as a Publisher; the mapping layer does not resolve references automatically. The test confirms the DTO populates via explicit fetching.

### 26.3. Cleaning Up Test Data

Tests should run against a dedicated test database or random tenants/IDs, cleaning fixtures via **`ReactiveMongoTemplate.remove`** afterward. Remember that `StepVerifier` or subscription is required for cleanup `remove` commands to execute too.

**Never run these tests against a production database.** To keep parallel suites isolated, use a separate database per suite or a Testcontainers MongoDB instance.

### 26.4. Measuring Query Counts

For one Order and one Customer, two reads make sense. To verify N+1 elimination when loading 100 Orders, instrument MongoDB command counts with command monitoring/metrics and compare:

- One Customer query per Order: queries scale linearly with N.
- One Customer `$in` batch per page of Orders: far fewer secondary queries.
- A `$lookup` aggregation: single command shape, shifting join work to the server.

Never claim improvements solely from changing `List` to `Flux`.

## 27. Testing Missing References, Wrong Tenants, and `productIds` Order

Testing only the happy path is insufficient. Explicit reference loading must cover data anomalies and authorization edge cases.

### 27.1. Customer Belonging to Another Tenant

Seed:

~~~text
Order: tenantId=shop-a, customerId=C1
Customer C1: tenantId=shop-b
~~~

Query:

~~~java
customers.findByIdAndTenantId(C1, "shop-a")
~~~

must complete **empty**. The service must never load `shop-b`'s Customer and return it to `shop-a`.

`StepVerifier` test:

~~~java
StepVerifier.create(
    customers.findByIdAndTenantId(
        customerIdFromAnotherTenant, "shop-a")
)
.verifyComplete();
~~~

When the service applies `switchIfEmpty(Mono.error(...))`, assert the **business error** rather than asserting empty completion.

### 27.2. Deleted Customer

Seed an Order with `customerId` where no matching Customer exists. Verify:

- The repository query returns `Mono.empty()`.
- The service enforces the chosen **missing-reference policy**.
- No unhandled `NullPointerException` is thrown.
- No fake Customer is synthesized outside business rules.

### 27.3. Mismatched ID BSON Types

An Order stores `customerId` as a `String` from legacy data while `customers._id` is an `ObjectId`. Queries may fail to match due to type mismatch. Tests should inspect raw BSON to distinguish mapping bugs from missing documents.

### 27.4. Order of Multiple Products

`Order.productIds = [P3, P1, P2]`, yet MongoDB `$in` may return `[P1, P2, P3]`. After assembling the DTO:

~~~text
DTO.products = [P3, P1, P2]
~~~

Tests should deliberately seed shuffled IDs to catch ordering bugs instead of testing with a single product.

### 27.5. Duplicate `productId`

`Order.productIds = [P1, P1]` may represent two items referencing the same product. Confirm whether DTOs preserve both slots per contract rather than accidentally deduplicating via a `Set`.

### 27.6. Cancellation and Errors

For a `Flux` loading multiple IDs, test:

- Client cancelling mid-stream after a few items.
- MongoDB query failures.
- A missing reference mid-batch.
- Bounded concurrency actually holding.
- Zero detached `subscribe()` calls keeping work running after cancellation.

**`StepVerifier` verifies Reactor signals**, while verifying server cursor closure requires driver metrics or command monitoring if governed by SLAs.

## 28. Performance and Observability When Loading Reactive Relationships

For read models resolving references, monitor both **MongoDB latency** and **Reactor pipeline behavior**.

### 28.1. Key Metrics to Track

| Metric | Meaning |
| --- | --- |
| MongoDB commands/request | Detects N+1 queries |
| Command latency | Identifies slow queries |
| Documents scanned | Checks index coverage |
| Query payload / response size | Flags over-fetching unused fields |
| Pool wait / checked-out connections | Detects excessive concurrency or undersized pools |
| Reactor subscriptions | Spots double subscriptions / repeated queries |
| Cancellations / timeouts | Tracks client aborts and slow queries |
| Collected list sizes | Catches large reference lists in RAM |
| Missing-reference counts | Reveals orphaned links, ID type mismatches, or auth denials |
| `$lookup` `executionStats` | Measures server-side join efficiency |

### 28.2. Indexes for References

For `ObjectId` references, MongoDB already maintains a unique index on `_id` in normal collections. When joining by a business key such as:

~~~javascript
{ tenantId: "shop-a", externalCode: "CUST-001" }
~~~

create an appropriate compound index, especially when `externalCode` is unique only per tenant.

### 28.3. Never Trade Security for Performance

Never drop the tenant filter just because `findById` looks shorter or `_id` already has an index. If you ever look up by `_id` first and check tenant in Java, you must guarantee nothing logs or serializes cross-tenant data and test that policy rigorously. Filtering by tenant directly in the query is far safer.

### 28.4. Caching and Denormalization

If a Customer's name appears across 1,000 Orders, reduce round trips using:

- Tenant-scoped Customer caching.
- Per-page batch ID lookups.
- Embedded snapshots inside Orders.
- Server-side `$lookup`.

Each option carries its own freshness, invalidation, and consistency rules. **Never treat denormalization as automatic data synchronization**; updating a Customer does not automatically rewrite snapshots inside historical Orders.

### 28.5. Bounding Memory and Concurrency

~~~java
return orders.findByTenantId(tenantId)
    .flatMap(order -> loadDetails(order), 8);
~~~

Capping concurrency avoids excessive simultaneous inner subscriptions. Yet if **`loadDetails`** returns large payloads or collects huge lists, heap still grows. Bound input counts, references per order, and response sizes.

## 29. Common Troubleshooting Matrix

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| Reactive entity with `@DBRef` fails to load Customer | Automatic DBRef resolution is unsupported like in blocking stack | Store `customerId` and fetch explicitly |
| Switching to `@DocumentReference` still doesn't load target | Reactive infrastructure does not auto-read document references | Use plain IDs + explicit queries or `$lookup` |
| Getter suddenly makes requests slow | Blocking lazy proxy or hidden I/O | Remove proxies; build explicit DTOs |
| `Mono` completes empty when Customer is missing | `flatMap` chained off `Mono.empty()` | Add `switchIfEmpty` per policy |
| One API triggers hundreds of MongoDB commands | N+1 reference fetches | Batch with `$in`, paginate, or use `$lookup` |
| Products appear in wrong order | `$in` does not preserve input ID order | Map ID → entity, then walk original ID list |
| Cross-tenant Product appears in response | `findById` lacked tenant filter | Filter by tenant on both root and target queries |
| Query misses even though IDs look identical | String vs BSON `ObjectId` type mismatch | Standardize ID types; inspect raw BSON |
| `block()` hangs or throws in Reactor | Blocking on event loop | Compose with `flatMap`/`zip`; eliminate blocking calls |
| Query runs twice | Manual `subscribe()` plus WebFlux subscribing | Return one single Publisher |
| `Mono.zip` emits no DTO | One source completed empty | Handle missing references before zipping |
| Application overloaded | `flatMap` concurrency too high | Bound concurrency; tune pool and latency |
| Heap grows despite `Flux` | `collectList`/sort/buffer on huge sets | Bound batches/pages; avoid unbounded accumulation |
| `$lookup` slow or returns huge payloads | Join lacks filters, indexes, or projections | Run `explain`, filter tenants, reduce root scope |
| `@Transactional` misses queries | Wrong manager, context, or scope | Use `ReactiveMongoTransactionManager`; keep in one chain |
| Legacy converter still calls blocking repo | Hidden blocking I/O during mapping | Move reference loading to explicit service logic |
| `Mono<Page>` fails | Reactive repositories do not support `Page` returns | Combine `Flux` + separate count / DTO |
| Cannot find Reactive Querydsl | Reading outdated docs or missing APT/dependencies | Check release and `ReactiveQuerydslPredicateExecutor` |
| Reactive bulk API missing | Older Spring Data version | Check API version and plan upgrade |
| Reactive repository AOT code missing | Release-specific repository AOT limits | Check AOT docs; keep runtime repository implementations |
| Legacy DBRefs not migrated to IDs | Changed annotations without BSON migration | Run tested backfill and cutover |
| Queries keep running after client cancels | Detached subscription/callback outside request lifecycle | Avoid manual `subscribe()`; verify cancellation |

### 29.1. Quick Investigation Flow

1. Inspect the raw BSON field: is it DBRef, `ObjectId` pointer, `String`, or embedded?
2. Check if the Java property uses **`@DBRef`/`@DocumentReference`** or just a plain ID.
3. Verify whether the read path uses `MongoTemplate` or `ReactiveMongoTemplate`.
4. Confirm reference feature support for your **Spring Data MongoDB version**.
5. For reactive paths, verify explicit queries compose cleanly in `Mono`/`Flux`.
6. Verify tenant filters and missing-reference policies.
7. Count MongoDB commands per request to catch N+1 queries.
8. Check ID types, indexes, and `explain`.
9. Audit for `block()`, manual `subscribe()`, high concurrency, and buffering operators.
10. Test on a test MongoDB instance with `StepVerifier` and real BSON data.

## 30. Practice Exercises

### Exercise 1: DBRef and Reactive

An Order has:

~~~java
@DBRef(lazy = true)
CustomerDocument customer;
~~~

If you convert its repository to `ReactiveMongoRepository`, will `customer` automatically resolve non-blocking?

**Answer:** No. Reactive mapping does not provide blocking-style DBRef join resolution. Store `customerId` and query `Customer` explicitly.

### Exercise 2: `@DocumentReference`

Does switching `@DBRef` to `@DocumentReference` make reactive loading populate `CustomerDocument` automatically?

**Answer:** No. Even though the stored reference format is more flexible, Spring Data docs state reactive infrastructure does not support reading document references.

### Exercise 3: DBRef vs ID Pointer

Distinguish:

~~~javascript
{ customer: { $ref: "customers", $id: ObjectId("507f1f77bcf86cd799439011") } }
{ customerId: ObjectId("507f1f77bcf86cd799439011") }
~~~

**Answer:** The first uses MongoDB's DBRef subdocument convention; the second is an application-defined plain ID pointer. Reactive services can use `customerId` directly to issue explicit Customer queries.

### Exercise 4: `flatMap`

Write a reactive flow that reads an Order, takes `customerId`, and loads the Customer:

~~~java
return orders.findByIdAndTenantId(orderId, tenantId)
    .flatMap(order ->
        customers.findByIdAndTenantId(
            order.customerId(), tenantId)
    );
~~~

**Explanation:** `flatMap` is used when the second Publisher depends on the emission of the first Publisher.

### Exercise 5: `Mono.zip`

Given two independent queries whose IDs are already known, should you chain them sequentially with `flatMap` or use `Mono.zip`?

**Answer:** You can use `Mono.zip` to combine independent query results. Still handle `Mono.empty` and tenant scoping on both sources.

### Exercise 6: The `block` Mistake

~~~java
CustomerDocument customer =
    customers.findById(customerId).block();
~~~

Why avoid this inside a WebFlux request?

**Answer:** It blocks the thread waiting for I/O, stalling the event loop or violating Reactor's non-blocking thread checks. Return a `Mono` composed with `flatMap`.

### Exercise 7: Detached `subscribe`

A service calls `subscribe()` to populate `customer` onto an `Order` and returns `Mono.just(order)`. What is the bug?

**Answer:** Two unsynchronized lifecycles: `Order` can emit before `customer` loads, and errors/cancellations are lost. Use `map`/`flatMap` in one single pipeline.

### Exercise 8: N+1

A page of 50 Orders runs `findById(Customer)` once per Order. How many extra queries can execute?

**Answer:** Up to 50 extra queries; batching `customerIds` with `$in` reduces round trips when appropriate.

### Exercise 9: ID Ordering

`Order.productIds = [P3, P1, P2]`, and `$in` returns `[P1, P2, P3]`. Is response order guaranteed to match the Order?

**Answer:** No. Map ID → Product and rebuild the list in the original ID order, or design explicit pipeline ordering.

### Exercise 10: Missing Reference

An Order holds `customerId`, yet the Customer was deleted. How should the response behave?

**Answer:** Follow the API contract: fail with a missing-reference error, return an “unavailable” marker, or fall back to an embedded snapshot. Never let `Mono.empty` silently masquerade as something else if the API needs the Order.

### Exercise 11: Tenant Safety

An Order belongs to `shop-a`, yet its `customerId` points to a Customer owned by `shop-b`. How do you prevent data leaks?

**Answer:** Filter by tenant on both the Order query and the Customer query; in server-side `$lookup`, also match tenant inside the inner lookup pipeline.

### Exercise 12: `$lookup`

True or false: Reactive MongoDB cannot join collections because it lacks DBRef resolution.

**Answer:** False. MongoDB Server provides `$lookup` and `ReactiveMongoTemplate` executes aggregations; the limit is strictly in automatic entity-reference mapping.

### Exercise 13: Transactions

Does `flatMap` from an Order query to a Customer query create a snapshot transaction?

**Answer:** No. Reactor composition does not open a MongoDB transaction; use `ReactiveMongoTransactionManager`/`TransactionalOperator` and suitable options when strict consistency is required.

### Exercise 14: `Page`

Can a reactive repository return `Mono<Page<OrderDocument>>` just like `MongoRepository` returns `Page<OrderDocument>`?

**Answer:** Not per reactive repository contracts. Return `Flux` with `Pageable`, and execute a separate count query/DTO assembly when totals are needed.

### Exercise 15: Querydsl

True or false: No version of `ReactiveMongoRepository` supports Querydsl.

**Answer:** False. Modern Spring Data MongoDB provides `ReactiveQuerydslPredicateExecutor`. Verify your version and annotation processing, while remembering it still does not enable DBRef joins.

### Exercise 16: GridFS and Bulk

Can we claim GridFS and bulk operations exist only in synchronous `MongoTemplate`?

**Answer:** No. `ReactiveGridFsTemplate` and `ReactiveBulkOperations` exist in compatible releases.

### Exercise 17: Manual `ClientSession`

`ReactiveMongoTemplate.withSession` is called, and then a reactive repository is called outside the callback. Will the repository automatically pick up that explicit session?

**Answer:** No. Documentation distinguishes manual session integration on the reactive Template API from managed transaction context. Never assume a repository outside the callback inherits an explicit `ClientSession`.

### Exercise 18: Migration

A legacy Order stores `customer` as a DBRef, while the new entity uses `customerId` (`ObjectId`). Is deploying the new entity enough?

**Answer:** No. You must migrate BSON documents, standardize ID types, audit dangling links, perform dual reads/cutover, and test thoroughly.

### Exercise 19: Embedded Snapshots

An Order must preserve the paid price even if `Product.price` later changes. Should you always look up the live Product price?

**Answer:** No. Storing **`priceAtOrder`** inside Order items is right for transaction history; use references only when live data is actually desired.

### Exercise 20: AOT

A reactive app runs fine at runtime, and the team wants to turn on repository AOT optimizations. Can you assume every reactive repository is supported?

**Answer:** No. Read the AOT documentation for your exact Spring Data version; certain releases limit support for reactive repository interfaces even though runtime reactive repositories work normally.

## 31. Pre-Production Checklist

- **Schema:** do you know whether BSON fields are DBRefs, plain ID pointers, or embedded?
- **Reactive references:** are you completely free of `@DBRef`/`@DocumentReference` auto-read assumptions?
- **ID types:** are `ObjectId`/`String`/`UUID` consistent across IDs and foreign keys?
- **Migration:** have legacy references been backfilled and reconciled?
- **Ownership:** are tenant/ACL filters enforced on both root and target collections?
- **Missing links:** is there an explicit policy for deleted, hidden, or cross-tenant references?
- **API contract:** does the endpoint need historical snapshots or live data?
- **DTOs:** are you avoiding returning raw entity graphs or lazy proxies?
- **Publishers:** are services free of `block()` and manual `subscribe()` calls?
- **Mapping:** are converters and entity callbacks free of blocking I/O?
- **N+1:** have you measured MongoDB commands per request?
- **Batching:** are `$in` lookups bounded in ID count with original ordering restored?
- **Concurrency:** is `flatMap` capped appropriately for your database pool?
- **Memory:** are `collectList`/buffers restricted to strictly bounded sets?
- **`$lookup`:** are root/target tenant filters, projections, and indexes verified?
- **Query plans:** have you checked `explain` for lookups and find queries?
- **`Page`:** are you avoiding `Mono<Page>` as a reactive repository contract?
- **Versions:** have you checked current docs before ruling out `ReactiveQuerydsl`, GridFS, or bulk?
- **Sessions:** do you distinguish explicit reactive Template sessions from managed transactions?
- **Consistency:** do separated reads require snapshot isolation or transactions?
- **AOT:** have you verified repository AOT support for your exact Spring Data version?
- **Cancellation:** are there zero detached subscriptions escaping request lifecycles?
- **Tests:** have you tested missing links, cross-tenant isolation, ID types, reference ordering, and N+1?
- **Observability:** are commands, latency, missing links, heap, and cancellations metered?
- **Security:** are target documents protected from enumeration by raw ID?

## 32. Summary

1. **`@DBRef`** stores a BSON DBRef subdocument and relies on blocking mapping resolution/lazy proxies; it is not a foreign-key constraint.
2. **`@DocumentReference`** allows more flexible pointers, yet automatic target loading still relies on the mapping resolver.
3. **Reactive infrastructure does not support automatically reading document references** as in blocking stacks; DBRef joins are likewise unsupported in traditional reactive mapping.
4. **Store plain IDs and query explicitly** as the clean, controllable, testable strategy for reactive MongoDB.
5. Use **`flatMap`** for dependent reference reads and **`Mono.zip`** for independent queries.
6. **Batch lookups with `$in`** reduce N+1 queries, provided you preserve tenant filters, handle missing/duplicate IDs, and restore original order.
7. **`ReactiveMongoTemplate.aggregate` + `$lookup`** supports server-side joins; do not equate converter limits with MongoDB server limits.
8. **Never perform blocking I/O inside converters or callbacks**, and never spawn detached subscriptions to mutate entity references.
9. **Explicit DTOs, embedded snapshots, and pagination** select only needed fields and prevent tight coupling to entity graphs.
10. **Reactive `Page`, manual session integration, and repository AOT** have specific API/version constraints.
11. **Do not mislabel Querydsl, GridFS, bulk, or change streams as sync-only** when modern Spring Data releases provide reactive APIs.
12. **Managed reactive transactions** rely on `ReactiveMongoTransactionManager` and Reactor Context—never created implicitly by a `flatMap` chain.
13. **Migrating DBRefs to plain IDs requires BSON data migration and verification**, not merely editing Java annotations.
14. **Measure performance by round trips, query plans, and memory/concurrency bounds**, never by the `Flux` return type alone.
15. **`StepVerifier` and MongoDB integration tests** validate tenant scoping, missing links, BSON mapping, and Publisher completion.

Understanding the **limits of DBRef, document references, and sync-only features** helps **`SPRING_DATA_MONGODB`** teams adopt reactive properly: every linked read becomes explicit, concurrency-bounded, tenant-safe, and consistency-aware instead of relying on hidden blocking lazy loading.

### Reference Documentation

- [Spring Data MongoDB — Using DBRefs and Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html) — DBRef storage formats, `@DocumentReference`, and reactive reading limits.
- [Spring Data MongoDB — Spring Data Extensions / Querydsl](https://docs.spring.io/spring-data/mongodb/reference/repositories/core-extensions.html) — `ReactiveQuerydslPredicateExecutor` and DBRef join limits.
- [Spring Data MongoDB — MongoDB-specific Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — reactive repository return types, `Pageable`, and DBRef.
- [Spring Data MongoDB — MongoDB Repositories](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/repositories.html) — `MongoRepository` vs `ReactiveMongoRepository` and reactive driver configuration.
- [Spring Data MongoDB — Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — manual `ClientSession` vs `ReactiveMongoTransactionManager`.
- [Spring Data MongoDB — GridFS Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-gridfs.html) — `GridFsTemplate` and `ReactiveGridFsTemplate`.
- [Spring Data MongoDB — Repository AOT](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aot.html) — repository AOT optimization scope by version.
- [Spring Data MongoDB — ReactiveBulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveBulkOperations.html) — reactive bulk operations.
- [MongoDB Manual — $lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — server-side joins on MongoDB.
