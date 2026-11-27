# Representing and Resolving @DBRef

> **Chapter:** Document References  
> **Module:** `SPRING_DATA_MONGODB`

In MongoDB, a document can **embed** related data or hold a **reference** to another document. When a Java application using Spring Data MongoDB wants to map an object-typed property while storing it as a reference, the `@DBRef` annotation is one option. Instead of storing the entire referenced document, Spring Data stores a value formatted as a **DBRef** containing the collection name and identifier key. When reading, Spring Data can use that information to locate and map the target document back into a Java object.

A key distinction to make from the start: **DBRef is a BSON convention for representing references, not a MongoDB foreign key, and it does not automatically trigger server-side joins**. Spring Data MongoDB is the component that resolves references when using `MongoTemplate` or repositories. Understanding this mechanism helps avoid mistakes with query counts, deleted target documents, and false assumptions about automatic cascading saves.

This lesson belongs to the `SPRING_DATA_MONGODB` module, where learners connect to MongoDB, map documents, use `MongoTemplate` or repositories, and continue with queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics. The content here focuses directly on **representing and resolving `@DBRef`**, laying the groundwork for choosing how to design relationships between documents.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Read the BSON structure of a DBRef with `$ref`, `$id`, and `$db`, and distinguish it from plain IDs and embedded documents.
2. Declare `@DBRef` in Java entities, save related data in the proper order, and read it back with Spring Data MongoDB.
3. Explain the query execution path when resolving references, both in the default mode and with `lazy = true`.
4. Recognize limitations regarding cascades, referential integrity, transactions, N+1 queries, circular references, and JSON serialization.
5. Compare `@DBRef` with document embedding, manual ID storage, and `@DocumentReference` to select an appropriate solution.

## 2. From Business Relationships to MongoDB References

Suppose a sales system has two types of data:

- **Customer:** a customer profile that can be used across many orders.
- **Order:** an order with status, creation timestamp, amount, and associated customer information.

The two documents have different lifecycles. One customer can have thousands of orders; embedding the full order history inside the customer easily creates large arrays and update contention. Conversely, embedding the entire customer profile into every order leads to duplicated data that is hard to update consistently. For some workflows, storing a reference from the order to the customer is a reasonable choice.

```text
Database: shop

customers                          orders
┌───────────────────────┐          ┌────────────────────────────┐
│ _id: ObjectId(C1)     │          │ _id: ObjectId(O1)          │
│ name: "An"            │ <------- │ customer: DBRef(C1)        │
│ email: "an@..."       │          │ orderCode: "ORD-001"       │
└───────────────────────┘          │ totalMinor: 450000         │
                                   └────────────────────────────┘

One customer can be referenced by many orders.
```

MongoDB does not enforce cross-collection document dependencies like SQL foreign keys. If a customer is deleted, a DBRef in an order can still remain and become a **dangling reference** (a reference whose target no longer exists).

## 3. BSON DBRef Format: $ref, $id, and $db

A DBRef has the following logical structure:

```javascript
{
  "$ref": "customers",
  "$id": ObjectId("66a000000000000000000101"),
  "$db": "shop"
}
```

Where:

| Component | Required? | Meaning | Example |
| --- | --- | --- | --- |
| `$ref` | Yes | Name of the **target collection** | `"customers"` |
| `$id` | Yes | **`_id` value of the target document**, preserving the key's BSON type | `ObjectId("...")`, string, number... |
| `$db` | No | Name of the **target database** if explicitly specified | `"shop"` |

DBRef control fields are typically ordered as `$ref`, `$id`, and then `$db` if present. The MongoDB driver and some tools may display a helper representation like `DBRef("customers", ObjectId("..."))`; this is still the same reference concept, not an embedded customer document.

Example of two collections in the same database:

```javascript
use shop

db.customers.insertOne({
  _id: ObjectId("66a000000000000000000101"),
  name: "Nguyen An",
  email: "an@example.com"
})

db.orders.insertOne({
  _id: ObjectId("66a000000000000000000201"),
  orderCode: "ORD-001",
  totalMinor: NumberLong(450000),
  customer: {
    "$ref": "customers",
    "$id": ObjectId("66a000000000000000000101")
  }
})
```

These are `mongosh` commands creating sample data. The `customer` value in `orders` **does not contain** `name` or `email`. Simply reading `orders` at the MongoDB level does not yet yield the full customer details.

### 3.1. Illustrating Manual Dereferencing

```javascript
const order = db.orders.findOne({ orderCode: "ORD-001" });

// By DBRef convention, the collection in $ref and id in $id
// identify where to read the target document.
const customer = db.customers.findOne({
  _id: order.customer.$id
});

printjson(customer);
```

Reading the customer is a separate query operation. In this example, we already **know** the target collection is `customers`; when writing general-purpose DBRef tooling, do not take an untrusted `$ref` value and execute queries against arbitrary collections without validation.

**Unlike DBRef**, if `orders` only holds `customerId: ObjectId("...")`, the application must itself know that the ID belongs to the `customers` collection. DBRef carries collection metadata; a plain ID does not.

### 3.2. What Does $db Mean?

When `$db` is omitted, the reference is normally interpreted within the current database of the read operation. When `$db` is present, a DBRef can point to a collection in another database within **the same compatible MongoDB connection scope**. It **does not** contain a URI, credentials, or the address of an independent MongoDB cluster.

Spring Data must have an appropriate driver configuration, permissions, and DBRef resolver to read the target. A DBRef with `$db` does not mean MongoDB opens a connection to another server or automatically grants access to the database named in the metadata.

### 3.3. How DBRef Differs from Foreign Keys and $lookup

- DBRef is **reference data**; MongoDB does not automatically verify that `$id` exists on write.
- `MongoTemplate`/repositories use mapping metadata to read the target during BSON → Java conversion.
- `$lookup` is a **server-side MongoDB aggregation stage** for joining data; DBRef **does not** automatically generate `$lookup` for every query.
- There is no automatic cascade save/delete or foreign key constraint solely from `@DBRef`.

Therefore, your data design must specify how to handle deleted target documents, network errors during resolution, and latency limits when many references exist.

## 4. Mapping @DBRef in Spring Data MongoDB

A self-contained example using Java, Spring Data MongoDB, and standard repositories.

### 4.1. Customer Entity

File `Customer.java`:

```java
package com.example.shop.customer;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers")
public class Customer {
    @Id
    private ObjectId id;

    private String name;
    private String email;

    protected Customer() {}

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public ObjectId getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

`@Document(collection = "customers")` specifies the collection and `@Id` maps `id` to `_id`. The example uses `ObjectId` explicitly to avoid confusion between string IDs and BSON ObjectId when inspecting the `$id` structure.

### 4.2. Order Entity with @DBRef

File `Order.java`:

```java
package com.example.shop.order;

import com.example.shop.customer.Customer;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.DBRef;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class Order {
    @Id
    private ObjectId id;

    private String orderCode;
    private long totalMinor;

    @DBRef
    private Customer customer;

    protected Order() {}

    public Order(String orderCode, long totalMinor, Customer customer) {
        this.orderCode = orderCode;
        this.totalMinor = totalMinor;
        this.customer = customer;
    }

    public ObjectId getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public long getTotalMinor() {
        return totalMinor;
    }

    public Customer getCustomer() {
        return customer;
    }
}
```

`@DBRef` is placed on the `customer` field, whose Java type is `Customer`. When saving `Order`, Spring Data uses the `@Document` metadata and the customer's ID to construct a DBRef inside the order document. When reading `Order`, the converter can fetch the target customer document and map it back into `Customer`.

In this design, `Customer` must be saved and have a valid ID **before** saving `Order`; the annotation does not automatically invoke `save(customer)`.

### 4.3. Declaring Repositories

File `CustomerRepository.java`:

```java
package com.example.shop.customer;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository
        extends MongoRepository<Customer, ObjectId> {
}
```

File `OrderRepository.java`:

```java
package com.example.shop.order;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<Order, ObjectId> {
}
```

Both repositories work with their respective collections. Whether they are registered in the Spring context depends on the application's repository scan/auto-configuration setup; `@DBRef` does not declare or register repositories on its own.

### 4.4. Saving in the Right Order and Reading Back

File `OrderApplicationService.java`:

```java
package com.example.shop.order;

import com.example.shop.customer.Customer;
import com.example.shop.customer.CustomerRepository;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;

@Service
public class OrderApplicationService {
    private final CustomerRepository customers;
    private final OrderRepository orders;

    public OrderApplicationService(
            CustomerRepository customers,
            OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    public Order createExampleOrder() {
        Customer customer = customers.save(
            new Customer("Nguyen An", "an@example.com")
        );

        // customer now has an _id so the DBRef has a valid target key.
        Order order = new Order("ORD-002", 450000L, customer);
        return orders.save(order);
    }

    public String customerName(ObjectId orderId) {
        Order order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId));

        Customer customer = order.getCustomer();
        if (customer == null) {
            throw new IllegalStateException(
                "Order is missing a valid customer reference");
        }
        return customer.getName();
    }
}
```

With default mapping, the persisted document looks similar to:

```javascript
{
  _id: ObjectId("66a000000000000000000202"),
  orderCode: "ORD-002",
  totalMinor: NumberLong(450000),
  customer: {
    "$ref": "customers",
    "$id": ObjectId("66a000000000000000000102")
  },
  _class: "com.example.shop.order.Order"
}
```

The ObjectId values in the BSON example only illustrate structure, not necessarily the exact IDs generated by the `save` call above. The `_class` field is Spring Data's default mapping metadata (which can change with custom type mapping configuration); it is **not part of the DBRef**.

## 5. How Does Spring Data Resolve DBRef?

When reading an `Order` via a repository or `MongoTemplate`, the general flow is:

```text
OrderRepository.findById(orderId)
        │
        ▼
MongoDB: find in orders collection
        │
        ▼
BSON { customer: { $ref: "customers", $id: C1 } }
        │
        ▼
MappingMongoConverter recognizes @DBRef field
        │
        ├── Default eager: fetch Customer(C1) while mapping Order
        │
        └── lazy=true: create proxy, defer fetching Customer
        │
        ▼
Order.getCustomer() → resolved Customer or proxy
```

When **eager** (the default), the converter needs to read the target document while converting data to Java. Each DBRef usually leads to a need for additional data retrieval, though the actual number of commands may vary depending on how Spring Data batches loads, the number of collection types, caching, and the access path.

Spring Data uses the `$ref` and `$id` metadata to locate the target and convert its BSON into the corresponding class; the MongoDB server does not replace the DBRef with the target document during a `find` on `orders`.

### 5.1. Resolving a Single Reference

For example, the order document contains:

```javascript
customer: {
  "$ref": "customers",
  "$id": ObjectId("66a000000000000000000101")
}
```

Resolving it requires finding the document with the matching `_id` in `customers`:

```javascript
db.customers.findOne({
  _id: ObjectId("66a000000000000000000101")
})
```

MongoDB creates a unique index on `_id` in standard collections, so fetching **one** document by ID is usually efficient. However, if the application has to resolve thousands of references, costs can arise from **call count, network round trips, mapping overhead, and returned payload size**, not just single-`_id` lookup speed.

### 5.2. Reading a Document Does Not Mean the Target Always Exists

A syntactically valid DBRef does not guarantee the target document exists or that the user has permission to read it. You may encounter:

- The ID was deleted or data is mid-migration.
- The specified collection or database differs from expectations.
- The target data does not match the current Java model.
- Access fails due to connection errors, permissions, or lazy dereference mode.

Do not assume a missing reference will always return `null` uniformly across every configuration, version, and access point. Define a business policy for missing targets and write integration tests for this case.

## 6. Eager vs. Lazy: Differences in Query Timing

### 6.1. Default: Eager

```java
@DBRef
private Customer customer;
```

Spring Data attempts to resolve the reference while reading the enclosing object. When a list view only displays `orderCode` and `totalMinor`, eager loading `customer` can generate unnecessary I/O.

### 6.2. Deferring with lazy = true

```java
@DBRef(lazy = true)
private Customer customer;
```

With supported lazy reference mechanisms, Spring Data places a **proxy** into the property. Customer data may not be queried immediately when reading the order; calling a method that requires the actual customer content can trigger the query.

Conceptual example:

```java
Order order = orders.findById(orderId).orElseThrow();

// May not touch customer data yet:
String code = order.getOrderCode();

// May trigger resolution of the customer proxy:
String name = order.getCustomer().getName();
```

The two lines above merely illustrate when access happens, where `orders` is an `OrderRepository` and `orderId` is valid.

**Limitations to remember:**

- A lazy proxy does not turn DBRef into a MongoDB-handled join. It only defers when the data is fetched.
- Debugging, calling `toString()`, logging, JSON serialization, or inspecting properties in a debugger can trigger the proxy unintentionally.
- Proxy creation capability depends on the property type, constructors/finality, and proxy mechanisms available in the running Spring Data/Java version. Interfaces may be easier to proxy than certain non-extensible types.
- When accessing the proxy, MongoDB access resources and application configuration must still be usable. Do not equate Spring Data MongoDB lazy behavior with Hibernate lazy loading.
- Lazy loading must be **measured and tested**; do not assume every conversion or serialization path defers I/O identically.

### 6.3. Choosing Eager or Lazy?

| Criterion | Eager `@DBRef` | Lazy `@DBRef(lazy=true)` |
| --- | --- | --- |
| Typical target fetch timing | When reading the referencing object | When the proxy requires actual data |
| Useful when | Customer is almost always needed with the order | Many flows only use order fields |
| Risk | Unnecessary queries, higher read latency | Queries triggered late, hard to spot from callers |
| API/serialization | Data may already be loaded | Serializer may trigger proxies and read the database |
| Guarantees avoiding N+1 | No | **No**, only shifts when queries occur |

To reliably reduce read costs, use **projections**, DTOs, or queries designed explicitly for the required fields. Lazy is an execution choice, not a substitute for query design.

## 7. @DBRef on Collections/Arrays

An order may hold references to multiple attachments:

```java
import java.util.List;
import org.springframework.data.mongodb.core.mapping.DBRef;

@DBRef(lazy = true)
private List<Attachment> attachments;
```

Suppose `Attachment` is a `@Document(collection = "attachments")` entity with saved IDs. BSON in the order document may look like:

```javascript
attachments: [
  { "$ref": "attachments", "$id": ObjectId("66a000000000000000000301") },
  { "$ref": "attachments", "$id": ObjectId("66a000000000000000000302") }
]
```

Spring Data can optimize loading a **collection of references to the same collection** by batching IDs into an appropriate query. Conversely, a reference collection mixing multiple target collections is harder to batch together; overhead can be higher. That is why you should avoid DBRef lists mixing multiple document/collection types without a clear need.

**Do not embed an unbounded array using DBRef and assume it is cost-free:** even though each element only stores a reference, array growth enlarges the root document and resolving many elements still costs I/O. For unbounded one-to-many relationships, consider having the child collection store `orderId` and querying with pagination.

## 8. @DBRef Does Not Automatically Cascade Saves

A common mistake is creating a customer without an ID and saving only the order:

```java
Customer unsaved = new Customer(
    "Nguyen An", "an@example.com");
Order order = new Order("ORD-003", 450000L, unsaved);

// No cascade save from @DBRef.
orders.save(order);
```

This is an **anti-pattern and should not be used**: referencing an unsaved object can lead to mapping/write errors or invalid state. Spring Data does not automatically insert `customer` and assign an ID just because `order` has a `@DBRef` field.

The proper flow saves the target first:

```java
Customer savedCustomer = customers.save(
    new Customer("Nguyen An", "an@example.com"));

Order savedOrder = orders.save(
    new Order("ORD-003", 450000L, savedCustomer));
```

Similarly, modifying a customer referenced by an order **does not** mean `orders.save(order)` updates the customer:

```java
// When you want to update customer data, call:
customers.save(customer);
```

In the snippet above, `customer` is assumed to be an entity with a valid ID modified through appropriate setters/services. Any multi-document synchronized save, delete, or update case must be designed explicitly.

### 8.1. Atomicity and Transactions

MongoDB guarantees that a write operation on **one document** is atomic. However:

1. Writing the customer.
2. Writing the order containing a DBRef to the customer.

are two operations on two different documents. If step 1 succeeds but step 2 fails, a customer unattached to any order may remain. If business requirements demand both changes succeed or fail together, consider **multi-document transactions on a supported MongoDB deployment** with proper session and transaction manager configuration in Spring Data MongoDB.

Transactions are not automatically enabled by `@DBRef`. In many situations, ensuring **idempotent** operations, using clear business keys, and having reconciliation for incomplete data are better fits than long-lived transactions.

### 8.2. Deleting a Referenced Document

If you delete a customer that still has orders pointing to it, DBRef does not prevent the deletion. Options include:

- **Block deletion** if related records remain.
- **Soft delete** the customer to retain history and comply with access policies.
- **Store a snapshot** of the customer's name/address at transaction time right inside the order, since invoices should not change if the customer profile is later edited.
- **Clean up references or reconcile periodically** when business rules allow.

None of these are performed automatically by MongoDB solely because of `@DBRef`.

## 9. Performance: N+1, Circular References, and Returned Data

Suppose a page reads 100 orders, each containing a `@DBRef Customer`. With eager loading, the application may have to read customers for those orders; with lazy loading, the cost appears when the caller accesses `getCustomer()`.

If the implementation triggers one query for 100 orders and many separate queries for customers, you hit a form of the **N+1 problem**. However, **do not assume it is strictly 101 queries**: Spring Data may batch loads in some cases, the same customer may appear multiple times, and the query count depends on version, usage pattern, and reference structure.

### 9.1. Strategies for Improvement

1. **Read only what is needed:** use projections to exclude `@DBRef` fields when a list page does not need the customer.
2. **Limit orders per page:** use pagination and appropriate filter criteria.
3. **Consider snapshotting key data:** for example, `customerNameAtPurchase` in the order enables fast, point-in-time historical views.
4. **Store explicit IDs and batch lookup:** extract unique `customerId`s, query `customers` with `_id: { $in: [...] }`, and combine in the service layer.
5. **Consider `$lookup` aggregation:** when server-side joins are truly needed and the data model/key paths support it, use an explicit pipeline. Because DBRef fields contain keys starting with `$`, writing pipelines that access those fields requires careful attention to MongoDB syntax/version; there is no automatic join just from an annotation.
6. **Measure actual driver commands:** use command monitoring, profiling, and latency metrics rather than optimizing based on guessed reference counts.

Projections should be tested with the exact query type used. Some Spring Data projection techniques may still instantiate the full entity and handle references differently than expected; if only a few fields are needed, use DTO projections or appropriate raw queries and measure them.

### 9.2. Avoiding Unintentional Circular References

If both `Order` points to `Customer` and `Customer` holds a `List<Order>` via DBRef, traversing a bidirectional graph can create complex dereferencing chains, or even infinite loops when `toString()` or a JSON serializer walks the object graph.

```text
Order --@DBRef--> Customer
  ^                   |
  |                   |
  +------@DBRef-------+
```

Keep reference direction minimal according to real query flows. For a customer's order history page, it is usually simpler to query `orders` by `customerId` instead of embedding an ever-growing DBRef list inside the customer document.

### 9.3. Where Do Indexes Go?

Target documents are usually fetched by `_id`, leveraging the default `_id` index. But when you need to **list a customer's orders**, an index on the `customers` collection **does not speed up filtering orders**. You need an appropriate query path and index on `orders`.

Because DBRef uses special `$ref`/`$id` subfields, query expressions and indexes on those subfields can be sensitive to MongoDB version, `$`-prefixed field syntax, and the mapping layer. If querying by customer key is a primary requirement, **storing `customerId` directly** on the order usually makes indexing, querying, and aggregation much simpler:

```javascript
// Alternative explicit-ID model instead of @DBRef:
db.orders.createIndex({ customerId: 1, createdAt: -1 })

db.orders
  .find({ customerId: ObjectId("66a000000000000000000101") })
  .sort({ createdAt: -1 })
  .limit(20)
```

This is an **alternative model**; the index and query commands only make sense if order documents actually contain `customerId`. With the `@DBRef` entity from section 4, documents store `customer` as a DBRef, so you cannot copy this query verbatim and expect results.

## 10. Comparing @DBRef, Plain IDs, @DocumentReference, and Embedding

Spring Data MongoDB provides multiple ways to represent a relationship. No single option is always optimal for every scenario.

| Approach | BSON stored in order | Who fetches customer? | Trade-offs |
| --- | --- | --- | --- |
| **Embed document** | `customer: {name, email, ...}` | Already in the order | Fast read with order; duplicated data that can go stale |
| **Plain ID** | `customerId: ObjectId(...)` | Service queries manually or via aggregation | Easy to index and batch; must write target-fetching logic |
| **`@DBRef`** | `customer: {$ref, $id, [$db]}` | Spring Data resolves DBRef | Carries collection metadata; incurs lookups, no cascade |
| **`@DocumentReference`** | By default usually stores target ID | Spring Data resolves per lookup config | Flexible storage/lookup; must understand version and config |

### 10.1. When Should You Embed?

Embed if child data is always read with the parent document, has a lifecycle dependent on the parent, and does not grow without bound. For example, **the shipping address confirmed at checkout** is usually a good fit for embedding in the order. Storing a DBRef to the current address record could misrepresent shipping history when the user later edits their address.

### 10.2. When Should You Store Plain IDs?

If the application queries frequently by `customerId`, needs pagination, bulk updates, or interoperates across multiple services/languages, plain IDs keep the schema simple:

```java
@Document(collection = "orders")
public class OrderWithCustomerId {
    @Id
    private ObjectId id;
    private ObjectId customerId;
    private String orderCode;
}
```

With this model, the service can load the customer explicitly:

```java
Customer customer = customers.findById(order.getCustomerId())
    .orElseThrow(() -> new IllegalStateException(
        "Customer was deleted or does not exist"));
```

The second snippet illustrates service code where `customers` is a `CustomerRepository` and `order` is an object with `getCustomerId()`. When the same customer appears across multiple orders, you can batch by unique IDs instead of performing one lookup per order.

### 10.3. How @DocumentReference Differs from @DBRef in Representation

With Spring Data MongoDB supporting `@DocumentReference`, you can map:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@DocumentReference
private Customer customer;
```

When using the default `_id` lookup mechanism, the BSON reference field is typically the **direct ID value**, for example:

```javascript
{ customer: ObjectId("66a000000000000000000101") }
```

Important distinction: `@DocumentReference` allows customizing the lookup and stored value type without requiring the traditional `$ref`/`$id` structure. It also **does not automatically provide foreign keys or cascade writes**. Availability and exact configuration syntax should be checked against your project's Spring Data MongoDB version.

### 10.4. Choosing via Business Questions

| Question | Direction to consider |
| --- | --- |
| Do you need a data snapshot at transaction time? | Embed the historical fields that must remain unchanged |
| Is the target shared by many documents and updated independently? | ID or reference |
| Do you need to read records in bulk and filter by target ID? | Plain ID and explicit indexes |
| Do you genuinely want Spring Data to manage dereferencing? | `@DBRef` or `@DocumentReference` with tests |
| Do multiple languages/services share the BSON? | Consider avoiding metadata/behavior specific to one mapper |
| Are latency requirements strict? | Measure query counts and payload sizes; consider snapshots/denormalization |

## 11. Querying with MongoTemplate or Repositories

In Spring Data MongoDB, both repositories and `MongoTemplate` can read entities containing `@DBRef`:

```java
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// Example method placed inside a service:
public List<Order> recentOrders(MongoTemplate mongoTemplate) {
    Query query = Query.query(
            Criteria.where("totalMinor").gte(100000L))
        .with(Sort.by(Sort.Direction.DESC, "orderCode"))
        .limit(20);

    return mongoTemplate.find(query, Order.class);
}
```

In this example, the main query runs against the `orders` collection; `customer` is still handled by Spring Data according to the entity's `@DBRef` rules when mapping results. If a page only needs order codes and amounts, consider a projection or dedicated read entity/DTO to avoid unnecessary dereferencing.

Analytical queries such as total revenue, status breakdowns, or index-backed queries normally operate directly on MongoDB fields. The presence of `@DBRef` **does not make every aggregation understand the Java object graph**; pipelines and data sources must be declared explicitly.

## 12. Issues in Reactive Access

Synchronous `@DBRef` is typically illustrated with `MongoTemplate`/`MongoRepository` and object proxy mechanisms. When an application uses `ReactiveMongoTemplate` or `ReactiveMongoRepository`, do not assume you can carry imperative proxy/lazy dereferencing straight into reactive flows without behavioral differences.

Check reference resolution support for your **Spring Data MongoDB version**, then choose the corresponding query pattern. A controllable design in reactive pipelines is storing plain IDs, fetching target data with reactive repositories/templates, and combining results using appropriate Reactor operators. That approach makes I/O trips, concurrency, and missing-target handling explicit.

**Conceptual example:**

```java
import reactor.core.publisher.Mono;

// customers: ReactiveCustomerRepository
public Mono<Customer> loadCustomer(ObjectId customerId) {
    return customers.findById(customerId)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("Customer does not exist")));
}
```

The method above is an example inside a service with an injected reactive `customers` repository; the `ObjectId` parameter requires importing `org.bson.types.ObjectId`. It demonstrates **intentional ID-based access**, not a `@DBRef` resolution hidden behind a getter.

## 13. Testing Persistence and Resolution Behavior

Unit tests that merely mock repositories neither prove that DBRef is written in the right BSON format nor measure the number of commands issued during resolution. You should write integration tests against an isolated MongoDB instance matching your deployment version.

### 13.1. Round-Trip: BSON Contains DBRef and Reads Back Correctly

JUnit 5 / Spring Boot Test example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.bson.BsonObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class OrderDbRefIntegrationTest {
    @Autowired
    CustomerRepository customers;

    @Autowired
    OrderRepository orders;

    @Autowired
    MongoTemplate template;

    @Test
    void writesAndResolvesCustomerReference() {
        Customer customer = customers.save(
            new Customer("An", "an@example.com"));
        Order saved = orders.save(
            new Order("TEST-ORD-DBREF-001", 450000L, customer));

        BsonDocument stored = template.getCollection("orders")
            .withDocumentClass(BsonDocument.class)
            .find(new BsonDocument(
                "_id", new BsonObjectId(saved.getId())))
            .first();

        assertThat(stored).isNotNull();
        BsonDocument ref = stored.getDocument("customer");
        assertThat(ref.getString("$ref").getValue())
            .isEqualTo("customers");
        assertThat(ref.getObjectId("$id").getValue())
            .isEqualTo(customer.getId());

        Order restored = orders.findById(saved.getId()).orElseThrow();
        assertThat(restored.getCustomer()).isNotNull();
        assertThat(restored.getCustomer().getName()).isEqualTo("An");
    }
}
```

In this example, `@Id ObjectId` keeps the same BSON ID type in Java and MongoDB. Calling `withDocumentClass(BsonDocument.class)` reads the raw BSON structure directly to verify `$ref` and `$id`, avoiding reliance on whether the driver returns DBRef as a specialized Java type or `Document`. If you replace `ObjectId` with String or UUID, the BSON `$id` type assertions must also change accordingly.

To verify **no cascading**, you can create a saved customer and order, modify the customer through an appropriate service layer, and verify that saving the order does not automatically update the customer document. You should also test an order document referencing a deleted target ID to observe how the application responds under your policy.

### 13.2. Verifying Eager/Lazy and N+1 with Measurements

A measurement test can:

1. Seed 50 orders, with many orders sharing the same customer.
2. Read the order list and record the number of MongoDB commands emitted by the driver.
3. Repeat with `@DBRef(lazy=true)`, first **without** calling the customer getter.
4. Then access `getCustomer().getName()` on every order and measure again.
5. Compare command counts, network round trips, and total latency; test both homogeneous reference lists and targets spread across multiple collections.

To observe commands, use MongoDB driver command monitoring or the profiler in a controlled test environment; `explain("executionStats")` only describes the plan of **a single query**, not the aggregate of all queries emitted by the mapper. In production, avoid leaving unbounded profiling or verbose query logging enabled.

### 13.3. Cases to Include in Your Test Matrix

| Case | Verification expectation |
| --- | --- |
| Save customer before order | BSON contains exact `$ref` and `$id`, without embedding the full customer |
| Read order via repository | `customer` maps back to `Customer` with matching ID and fields |
| Lazy getter not called | No unexpected early target lookup in supported configurations |
| Lazy getter called | Target query occurs and error handling is controlled |
| Customer deleted | Application handles dangling reference per business policy |
| Same customer referenced by many orders | No flood of redundant queries, or measured cost is acceptable |
| Insufficient permission to read target collection | Error is caught and reported at the proper service boundary |
| Save order after modifying customer in memory | No unintended cascade update |
| Cross-database reference | Verify `$db`, permissions, and actual read configuration |

## 14. Common Pitfalls

| Issue | Cause | Resolution |
| --- | --- | --- |
| Thinking `@DBRef` is a server-side join | Confusing BSON references with aggregation | Understand resolution occurs via Spring Data; measure actual queries |
| Saving order referencing an unsaved customer | `@DBRef` does not cascade customer creation | Save target, verify ID, then save referencing document |
| Customer details change but order does not “auto-update” | Saving order does not cascade to customer | Save customer separately; snapshot if historical data is needed |
| Deleting customer breaks order UI reads | MongoDB has no automatic foreign keys | Block delete, soft delete, snapshot, or handle dangling references |
| Eager DBRef slows list pages | Loads target even when screen does not need it | Projections, explicit IDs, batch lookups, or another model |
| Lazy loading still triggers many queries | Getters/serializers/debuggers trigger proxies | Measure queries, avoid direct object-graph serialization, use DTOs |
| Bidirectional circular references | Unnecessary bidirectional relationship design | Minimize reference direction; query by child's foreign key |
| Confusing `$db` with a MongoDB URI | DBRef only stores a database name, not an independent connection | Configure client/permissions explicitly |
| Indexing customer expecting order-by-customer queries to speed up | Index placed on the wrong collection | Choose query keys and indexes directly on `orders`, or design appropriate aggregations |
| Using `@DBRef` with reactive and assuming synchronous proxies | Two different access infrastructures | Verify version support and use explicit reactive lookups when appropriate |

## 15. Practice Exercise

A library application has `Book`, `Author`, and `Borrowing`:

- One author can write many books.
- One book can have many authors.
- When creating a borrowing record, the system must preserve **the book title and book code at the time of borrowing** for historical records.
- The borrowings list page usually displays only the book title and borrow date; only the detail page needs author information.

Design:

1. Which collections should exist and which document should store snapshot data?
2. Should `@DBRef` be used from `Book` to `Author`? If yes, when should it be lazy?
3. If a list of hundreds of books must display author names, how do you avoid queries growing with the book count?
4. When deleting an author while books still exist, what policy does the application need?
5. Write how to test BSON `$ref`, `$id`, and reading back via `MongoTemplate` or a repository.

**Hint:** keep `authors` and `books` as independent entities; borrowing records can store `bookTitleAtBorrow` and `bookCodeAtBorrow` snapshots to preserve history. `@DBRef` for authors should only be used if you specifically want Spring Data to dereference objects; when book lists are long and need filtering/sorting by author key, storing IDs and querying/batching lookups can be more convenient. Measure emitted commands before deciding between lazy and eager.

## 16. Key Takeaways

- **DBRef** is represented by `$ref` (collection), `$id` (target key), and `$db` (optional database).
- **`@DBRef`** lets Spring Data MongoDB map BSON references and resolve Java objects on read; MongoDB server does not automatically join documents on `find`.
- **There is no automatic cascade or foreign key**. Targets must have a valid ID before saving references; the application is responsible for data integrity and multi-document operations.
- **Eager/lazy is a decision about I/O timing**, not a way to eliminate resolution cost or guarantee avoiding N+1.
- For queries by target ID, immutable historical data, polyglot applications, or high load, consider **plain IDs, snapshots/embedding, or `@DocumentReference`** before choosing `@DBRef`.

When using Spring Data MongoDB, evaluate references by query needs, update patterns, read cost, and consistency boundaries. Testing BSON ↔ Java round-trips and observing actual MongoDB command counts are two critical steps before putting any reference structure into production.
